# Cấp chứng thư thay thế và cập nhật thành phần TLS sử dụng

Trong chương **Chứng thư PKI**, chúng ta dùng HashiCorp Vault PKI làm nơi phát hành chứng thư X.509 cho ứng dụng Java. Một chứng thư TLS chỉ có hiệu lực trong khoảng thời gian từ `Not Before` đến `Not After`. Vì vậy, đưa chứng thư vào hệ thống mới là một nửa công việc: trước khi hết hạn, cần **cấp chứng thư thay thế, phân phối đúng cặp khóa/chứng thư, kích hoạt ở nơi sử dụng và xác minh kết nối TLS thực sự dùng chứng thư mới**.

Bài này đặt việc cấp lại chứng thư trong bối cảnh **SPRING_VAULT**: ứng dụng Java truy cập Vault qua `VaultTemplate`/`VaultOperations`, xác thực bằng workload identity, giới hạn thao tác bằng policy; đồng thời phải quản lý vòng đời token, xử lý lỗi Vault, kiểm thử tích hợp và giám sát tình trạng TLS.

Ví dụ xuyên suốt: dịch vụ Spring Boot `orders.svc.example.internal` đang sử dụng chứng thư máy chủ được cấp từ mount PKI `pki/`, role `orders-server`. Chứng thư hiện tại sắp hết hạn; mục tiêu là thay nó mà vẫn duy trì các kết nối HTTPS hợp lệ.

## 1. Vì sao phải cấp chứng thư **thay thế**?

### Chứng thư, khóa và niềm tin của máy khách

Một triển khai TLS thường liên quan đến các thành phần sau:

| Thành phần | Ý nghĩa | Có thay khi cấp lại? |
| --- | --- | --- |
| **Leaf certificate** (`tls.crt`) | Chứng thư X.509 của dịch vụ, chứa public key, DNS SAN, thời hạn và serial number | **Có**: nhận chứng thư mới với serial/thời hạn mới |
| **Private key** (`tls.key`) | Khóa bí mật tương ứng public key trên leaf certificate | **Nên có**: tạo cặp khóa mới khi rotation |
| **Intermediate CA / chain** | Chuỗi chứng thực giúp máy khách xây đường tin cậy đến CA gốc | Chỉ đổi khi issuer/chuỗi CA thay đổi |
| **Truststore** | Tập CA được máy khách tin cậy | Thường giữ nguyên nếu issuer vẫn thuộc chuỗi CA đã tin; phải cập nhật khi thay CA |
| **TLS runtime** | Web server, reverse proxy, client HTTP, gRPC client, sidecar, ingress... thực sự nạp chứng thư/khóa | **Phải xác minh đã nạp mới**, qua reload, thay SSL context, rolling restart hoặc cơ chế do sản phẩm hỗ trợ |

**Cấp mới không đồng nghĩa kích hoạt mới.** Vault có thể phát hành chứng thư thành công trong khi web server vẫn phục vụ chứng thư cũ trong bộ nhớ. Tương tự, đổi file trong container không đảm bảo mọi thư viện TLS tự động đọc lại.

X.509 không có phép “gia hạn trực tiếp” để thay `Not After` trên chứng thư đã ký. Thao tác thường gọi là *renew certificate* về mặt vận hành thực chất là **cấp chứng thư mới**, có thể bằng cách tạo khóa mới và yêu cầu phát hành, hoặc gửi CSR để CA ký.

### Không nhầm với Vault lease/token

- **Vault token**: cho phép workload gọi API của Vault; tùy loại token có thể được gia hạn hoặc cấp mới theo cơ chế auth. Token hết hạn có thể khiến lần cấp chứng thư tiếp theo bị từ chối.
- **PKI certificate**: có `Not After` độc lập, được client TLS xác minh theo thời gian và chuỗi tin cậy. `vault lease renew` không kéo dài thời hạn X.509 của leaf certificate đang dùng.
- **PKI lease**: tùy cấu hình role như `generate_lease`, Vault có thể tạo lease khi phát hành, nhưng nhiều mô hình PKI khuyến nghị quản lý vòng đời bằng thời hạn chứng thư và khả năng thu hồi theo serial. Không lấy `lease_duration` thay cho kiểm tra `X509Certificate.getNotAfter()`.

Vì thế, lịch cấp thay thế cần dựa vào **thời điểm hết hạn trên chứng thư** và lượng thời gian đủ để triển khai, thử kết nối, xử lý lỗi.

## 2. Quy trình cấp và kích hoạt không gián đoạn

Một quy trình an toàn tách rõ **tạo vật liệu mật mã** và **đưa vật liệu đó vào TLS runtime**:

~~~mermaid
flowchart TD
    A[Theo dõi hạn chứng thư đang phục vụ] --> B{Đến ngưỡng thay thế?}
    B -- Chưa --> A
    B -- Có --> C[Xác thực workload, gọi Vault PKI]
    C --> D[Cấp leaf mới và khóa mới hoặc ký CSR]
    D --> E[Kiểm tra SAN, EKU, CA chain, hạn và key pair]
    E --> F{Hợp lệ?}
    F -- Không --> G[Ghi nhận lỗi, retry có giới hạn, cảnh báo]
    G --> A
    F -- Có --> H[Stage vật liệu TLS bản mới an toàn]
    H --> I[Activate qua reload hoặc rolling deployment]
    I --> J[Thử HTTPS/mTLS, đọc serial và hạn đang phục vụ]
    J --> K{Dịch vụ dùng chứng thư mới?}
    K -- Không --> L[Giữ/khôi phục cấu hình còn hợp lệ, cảnh báo]
    L --> A
    K -- Có --> M[Ghi nhận phiên bản, dọn vật liệu cũ theo chính sách]
    M --> A
~~~

Với chứng thư hợp lệ 24 giờ, có thể đặt ngưỡng cấp thay thế ở khoảng 1/2–2/3 vòng đời, kèm biên an toàn cho thời gian gián đoạn, nhiều lần retry và rollout. Đây là **ví dụ về chính sách**, không phải công thức bắt buộc; ngưỡng thực tế phụ thuộc TTL, độ ổn định Vault, số instance, tốc độ rollout và rủi ro hết hạn. Với nhiều replica, thêm jitter để tránh tất cả cùng yêu cầu cấp mới trong một giây.

Sự kiện **certificate issued** hoặc **file updated** là tín hiệu trung gian; điểm hoàn thành phải là **handshake TLS thành công với chứng thư mới trên mọi instance được kỳ vọng**.

## 3. Chuẩn bị quyền cấp chứng thư ở Vault PKI

Giả sử người quản trị đã enable mount `pki/`, cấu hình root/intermediate CA và CA chain phù hợp. Người quản trị định nghĩa một role giới hạn tên miền, mục đích và thời gian sống của chứng thư. Ví dụ cấu hình tham khảo cho **máy chủ**:

~~~bash
# Lệnh quản trị, không phải quyền của ứng dụng Spring Boot.
vault write pki/roles/orders-server \
  allowed_domains="svc.example.internal" \
  allow_subdomains=true \
  allow_bare_domains=false \
  allow_any_name=false \
  server_flag=true \
  client_flag=false \
  key_type=ec \
  key_bits=256 \
  ttl=24h \
  max_ttl=72h \
  generate_lease=false
~~~

Role giới hạn việc cấp chứng thư theo domain và EKU server authentication. Trong môi trường thực tế, hãy chọn `allowed_domains` và SAN theo tên DNS mà client **thật sự** dùng, quy định rõ wildcard/IP/URI SAN, TTL và thuật toán khóa. TTL chứng thư còn bị giới hạn bởi thời gian sống của issuer CA và cấu hình PKI.

Ứng dụng chuyên **cấp chứng thư thay thế** chỉ cần capability `update` trên endpoint role tương ứng:

~~~hcl
# Policy cho workload có quyền cấp chứng thư máy chủ.
path "pki/issue/orders-server" {
  capabilities = ["update"]
}
~~~

Nếu khóa riêng được tạo ở phía client và chỉ gửi CSR cho Vault ký, policy có thể tách riêng:

~~~hcl
# Policy cho workload sử dụng CSR.
path "pki/sign/orders-server" {
  capabilities = ["update"]
}
~~~

Không cấp quyền quản trị CA, sửa role, thay issuer hay `pki/revoke` cho workload chỉ cần yêu cầu chứng thư. `pki/revoke` có thể thu hồi chứng thư theo serial của đối tượng khác; đây là quyền nhạy cảm nên thuộc quy trình quản trị hoặc thành phần được ủy quyền phù hợp.

Token sử dụng từ Kubernetes auth, AppRole hay cơ chế workload khác phải được cấp policy đúng role và còn hợp lệ trước thời điểm rotation. Sử dụng HTTPS/TLS để kết nối Vault, xác minh danh tính máy chủ Vault, tránh lưu token cố định trong mã nguồn.

## 4. Hai cách tạo chứng thư thay thế

### Cách A: Vault tạo khóa riêng và phát hành chứng thư

Gọi `POST /v1/pki/issue/orders-server`, với `common_name` và `ttl` phù hợp. Ví dụ khi dùng Vault CLI trong **môi trường thử nghiệm được bảo vệ**:

~~~bash
# Lệnh sinh ra chứng thư MỚI; response chứa PRIVATE KEY.
# Không chạy trong CI/log terminal được lưu công khai.
vault write pki/issue/orders-server \
  common_name="orders.svc.example.internal" \
  ttl=24h
~~~

Phản hồi điển hình chứa:

~~~text
certificate       -----BEGIN CERTIFICATE-----...
issuing_ca        -----BEGIN CERTIFICATE-----...
ca_chain          [các chứng thư CA theo chuỗi]
private_key       -----BEGIN PRIVATE KEY-----...
serial_number     <serial mới>
expiration        <thời điểm hết hạn>
~~~

**Lưu ý:** Vault PKI chỉ cung cấp private key được sinh ở endpoint `issue` trong phản hồi phát hành; không nên dựa vào việc đọc lại private key từ Vault về sau. Phải có kênh chuyển giao an toàn ngay tại thời điểm cấp.

Khi cần lưu các trường trong một script, chỉ thực hiện **một lần phát hành** và xử lý toàn bộ response trong bộ nhớ/điểm lưu được bảo vệ. Không gọi `pki/issue` ba lần riêng để lấy `certificate`, `private_key` và `ca_chain` vì mỗi lần sẽ tạo một chứng thư/cặp khóa **khác nhau**.

### Cách B: Tạo khóa riêng tại workload rồi gửi CSR

Nếu chính sách yêu cầu private key không rời HSM, keystore hoặc máy chủ ứng dụng, hãy sinh khóa **ở phía sử dụng**, xây PKCS#10 CSR rồi gọi `POST /v1/pki/sign/orders-server`. Vault chỉ ký CSR và trả về chứng thư cùng CA chain; private key **không được gửi lên Vault**.

Ví dụ OpenSSL đơn giản trên một máy thử nghiệm an toàn (đã cấu hình Vault CLI):

~~~bash
umask 077

openssl req -new -newkey ec \
  -pkeyopt ec_paramgen_curve:prime256v1 \
  -nodes \
  -keyout tls-next.key \
  -out tls-next.csr \
  -subj "/CN=orders.svc.example.internal" \
  -addext "subjectAltName=DNS:orders.svc.example.internal"

# Cần role cho phép dùng tên CN/SAN từ CSR.
vault write pki/sign/orders-server \
  csr=@tls-next.csr \
  ttl=24h
~~~

Trong trường hợp này, phải giữ an toàn file `tls-next.key` (hoặc giữ khóa trong thiết bị/keystore được kiểm soát), ghép chứng thư kết quả với **chính private key đã tạo CSR**. Các lựa chọn `use_csr_common_name`, `use_csr_sans` và ràng buộc của role ảnh hưởng dữ liệu thực tế trên chứng thư; sau khi ký cần **đọc lại X.509** để xác minh DNS SAN/KU/EKU, không chỉ tin vào nội dung CSR ban đầu.

| Tiêu chí | `pki/issue/<role>` | `pki/sign/<role>` |
| --- | --- | --- |
| Nơi sinh private key | Vault sinh theo request/role rồi trả về cho caller | Workload/HSM sinh và giữ khóa |
| Dữ liệu caller nhận | Chứng thư, khóa riêng, issuer/CA chain, metadata | Chứng thư đã ký, issuer/CA chain, metadata; không có private key |
| Phù hợp khi | Hệ thống quản lý và phân phối secret/keystore tập trung | Không được phép để private key rời workload hoặc HSM |
| Trách nhiệm chính | Giữ bí mật bundle trả về, phân phối đúng máy | Quản lý khóa/CSR và chứng minh key pair khớp |

### Trường hợp nào cần thay CA?

Đổi **leaf certificate** và đổi **issuing CA** là hai công việc khác nhau. Nếu cùng intermediate CA còn hợp lệ, client thường không phải đổi truststore. Khi CA/issuer thay đổi, cần triển khai trust anchor mới tới các client, thiết kế khoảng chồng lấn tin cậy, cập nhật chain được máy chủ gửi và kiểm thử cả hai phía trước khi rút CA cũ. Không tự thêm một leaf certificate đơn lẻ vào truststore để thay thế cơ chế tin cậy CA nếu thiết kế đang dùng PKI chuẩn.

## 5. Cấp chứng thư bằng Spring Vault

Spring Vault cung cấp `VaultPkiOperations` để phát hành và ký chứng thư. Giả sử ứng dụng đã có `VaultOperations` do cấu hình Vault endpoint, TLS, workload authentication và session management cung cấp:

~~~java
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;
import java.time.Duration;
import java.util.Collection;
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultPkiOperations;
import org.springframework.vault.support.CertificateBundle;
import org.springframework.vault.support.VaultCertificateRequest;

@Service
public class OrdersCertificateIssuer {

    private static final String HOST = "orders.svc.example.internal";
    private final VaultPkiOperations pki;

    public OrdersCertificateIssuer(VaultOperations vault) {
        this.pki = vault.opsForPki("pki");
    }

    /**
     * Gọi Vault một lần và nhận một bộ chứng thư/khóa thống nhất.
     * Đối tượng trả về có PRIVATE KEY: không log, không serialize công khai.
     */
    public CertificateBundle issueReplacement() throws CertificateException {
        VaultCertificateRequest request = VaultCertificateRequest.builder()
                .commonName(HOST)
                .ttl(Duration.ofHours(24))
                .build();

        CertificateBundle bundle = pki
                .issueCertificate("orders-server", request)
                .getRequiredData();

        X509Certificate leaf = bundle.getX509Certificate();
        leaf.checkValidity(); // Kiểm tra NotBefore và NotAfter tại thời điểm cấp.

        if (!hasDnsSan(leaf, HOST)) {
            throw new CertificateException("Chứng thư không có DNS SAN mong đợi");
        }

        return bundle;
    }

    private static boolean hasDnsSan(X509Certificate cert, String dns)
            throws CertificateException {
        Collection<List<?>> names = cert.getSubjectAlternativeNames();
        if (names == null) {
            return false;
        }
        for (List<?> item : names) {
            // GeneralName dNSName có type = 2.
            if (Integer.valueOf(2).equals(item.get(0))
                    && dns.equalsIgnoreCase((String) item.get(1))) {
                return true;
            }
        }
        return false;
    }
}
~~~

Sau khi nhận `CertificateBundle`, thành phần triển khai có thể sử dụng `bundle.getCertificate()`, `bundle.getPrivateKey()`, `bundle.getCaChain()`, `bundle.getSerialNumber()` hoặc `bundle.createKeyStore(...)` để chuẩn bị vật liệu TLS. **Không ghi trực tiếp cả bundle ra log**, không trả private key qua REST endpoint, không dùng những đối tượng có `toString()` chứa khóa riêng trong log.

Ví dụ trên kiểm tra hạn và DNS SAN để minh họa, **chưa phải trình kiểm định X.509 đầy đủ**. Trong luồng cài đặt phải kiểm tra thêm mục đích `serverAuth` hoặc `clientAuth` (EKU), `KeyUsage`, chữ ký/chains, thời hạn tối thiểu còn lại và tính tương thích thuật toán; TLS handshake thật mới xác nhận cấu hình end-to-end.

Khi dùng CSR:

~~~java
import org.springframework.vault.support.Certificate;
import org.springframework.vault.support.VaultSignCertificateRequestResponse;

// csrPem chứa CSR được tạo bởi thư viện PKI/HSM bên ngoài.
VaultCertificateRequest request = VaultCertificateRequest.builder()
        .commonName("orders.svc.example.internal")
        .ttl(Duration.ofHours(24))
        .build();

VaultSignCertificateRequestResponse result = vault
        .opsForPki("pki")
        .signCertificateRequest("orders-server", csrPem, request);

Certificate signedCertificate = result.getRequiredData();
// Cài đặt chứng thư cùng private key đang nằm phía workload.
~~~

Không đồng nhất **thành công của API Spring Vault** với **chứng thư đã được runtime TLS sử dụng**. `issueReplacement()` chỉ cấp và kiểm tra dữ liệu ban đầu; cơ chế bảo quản và cập nhật thành phần TLS phải được thiết kế riêng.

## 6. Cập nhật thành phần TLS đang dùng chứng thư

### 6.1. Trường hợp HTTPS server Spring Boot

Ví dụ Spring Boot sử dụng **SSL bundle PEM** với file ở ổ đĩa/volume ngoài ứng dụng:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        orders-tls:
          reload-on-update: true
          keystore:
            certificate: "file:/run/tls/orders/fullchain.pem"
            private-key: "file:/run/tls/orders/tls.key"
server:
  port: 8443
  ssl:
    bundle: orders-tls
~~~

Đây là khả năng của **Spring Boot** có hỗ trợ SSL bundle reload (ví dụ các phiên bản Spring Boot 3.2+ phù hợp), **không phải chức năng tự động của Vault PKI**. Bộ file phải do một controller/agent/sidecar/quy trình cấp chứng thư khác cập nhật. Tomcat và Netty là các web server được Spring Boot hỗ trợ reload SSL bundle theo tài liệu; hãy kiểm tra đúng phiên bản Boot và server nhúng đang dùng. Với server hoặc TLS consumer không hỗ trợ reload, sử dụng rolling restart hoặc tái tạo SSL context theo cơ chế được hỗ trợ.

`fullchain.pem` thường gồm **leaf certificate trước, sau đó các intermediate certificate cần thiết**, tránh gửi root CA dư thừa khi không cần. `tls.key` phải là private key tương ứng với leaf. Cả hai file phải được phân quyền chặt, không nằm trong Git, Docker image công khai hay artefact build.

Quy trình cập nhật file:

1. Cấp chứng thư/khóa mới và nhận đủ chain từ **một** kết quả.
2. Ghi vào thư mục staging có quyền truy cập tối thiểu (thường chỉ chủ sở hữu đọc private key), không ghi đè bản đang dùng khi chưa kiểm định.
3. Kiểm tra private key khớp public key trên leaf, DNS SAN/EKU/CA chain và hạn hiệu lực.
4. Kích hoạt **theo một phiên bản nhất quán**: dùng cơ chế triển khai/secret mount hỗ trợ cập nhật có phối hợp, hoặc tạo PKCS#12 và thay một artifact thống nhất, hoặc triển khai rolling instance mới. Tránh trạng thái watcher thấy `fullchain.pem` mới nhưng `tls.key` vẫn cũ.
5. Đợi reload/rolling readiness thành công, mở kết nối TLS mới, xác nhận **serial/fingerprint** đang phục vụ thuộc chứng thư mới.
6. Chỉ hoàn tất khi instance đã cập nhật và health check đạt; giữ bản cũ còn hợp lệ trong khoảng rollback thích hợp nếu không có sự cố lộ khóa.

Với các file PEM cập nhật riêng rẽ, file watcher của Spring Boot có thuộc tính `spring.ssl.bundle.watch.file.quiet-period` để chờ file ổn định trước khi reload. Tính năng đó giúp giảm lỗi trong lúc ghi file, nhưng **không thay thế** kiểm tra sự đồng bộ của cặp khóa/chứng thư và xác minh handshake.

### 6.2. Trường hợp ứng dụng Java gọi dịch vụ khác qua mTLS

Với client mTLS, ứng dụng thường có **keystore chứa chứng thư/khóa của client**, đồng thời có **truststore tin CA phía server**. Khi cấp lại client certificate:

- Thay identity bundle (private key + leaf + chain) được HTTP/gRPC client sử dụng; áp dụng reload hoặc khởi tạo TLS client/SSL context mới theo khả năng của thư viện.
- Xác minh endpoint phía server vẫn chấp nhận chứng thư mới dựa trên CA, SAN/subject, EKU `clientAuth` và chính sách xác thực của hệ thống.
- Làm mới các connection pool, HTTP/2 connections hoặc phiên TLS sống lâu nếu cần. Kiểm thử bằng **handshake mới**; kết nối đã mở từ trước không phải bằng chứng đã cập nhật chứng thư.
- Nếu CA thay đổi, chuẩn bị truststore phía cả hai chiều trong thời gian chuyển tiếp, tránh cắt đứt mTLS giữa các service.

Ví dụ một ứng dụng dùng `SslBundle` có thể gọi `sslBundle.createSslContext()` để tạo ngữ cảnh TLS cho kết nối **mới**. Việc bundle có thể reload không đồng nghĩa thư viện client bất kỳ sẽ tự thay SSL context/connection pool; hãy làm theo hợp đồng của client thực tế.

### 6.3. Ingress, proxy, Kubernetes và các thành phần khác

Nếu TLS terminate ở ingress controller hoặc reverse proxy, việc thay chứng thư bên trong ứng dụng Spring Boot **không đổi** chứng thư trên endpoint internet. Phải cập nhật tại **đúng nơi terminate TLS**.

Trên Kubernetes, cert-manager với Vault issuer là một phương án quản lý CSR/cấp mới và Kubernetes Secret. Tuy vậy, controller chỉ bảo đảm Secret được cập nhật theo cơ chế của nó; các Pod/ingress/proxy còn cần hỗ trợ reload Secret hoặc rollout. Với mỗi tầng, ghi rõ **chủ sở hữu vật liệu TLS**, cách phát hiện thay đổi, hành động kích hoạt và bằng chứng handshake.

## 7. Kiểm tra chứng thư trước và sau khi kích hoạt

Một số kiểm tra bằng OpenSSL; các lệnh dưới đây chỉ đọc chứng thư/khóa ở **môi trường thử nghiệm có quyền hợp lệ**. Không đưa private key vào stdout/log.

~~~bash
# Xem tên, serial, hạn và SAN trên chứng thư sắp cài đặt.
openssl x509 -in fullchain.pem \
  -noout -subject -issuer -serial -dates -ext subjectAltName

# Trả về exit 0 nếu leaf chưa hết hạn trong 12 giờ tới.
openssl x509 -in fullchain.pem -checkend 43200 -noout

# Fingerprint SHA-256 của chứng thư sắp cài.
openssl x509 -in fullchain.pem -noout -fingerprint -sha256

# Kiểm tra khả năng xây chain đến CA gốc được tin cậy.
# ca-root.pem là trust anchor; intermediate.pem chứa intermediate CA.
openssl verify -CAfile ca-root.pem \
  -untrusted intermediate.pem fullchain.pem
~~~

Đối chiếu public key lấy từ chứng thư và private key tương ứng bằng digest của phần DER public key:

~~~bash
openssl x509 -in fullchain.pem -pubkey -noout \
  | openssl pkey -pubin -outform DER \
  | openssl dgst -sha256

openssl pkey -in tls.key -pubout -outform DER \
  | openssl dgst -sha256
~~~

Hai digest phải giống nhau. Đây là bước xác minh key pair; **không** so sánh chuỗi PEM vì encoding/định dạng có thể khác dù chứa cùng khóa.

Sau khi reload/rollout, kiểm tra từ mạng tới đúng endpoint đang phục vụ:

~~~bash
# Chỉ đọc chứng thư máy chủ qua một TLS handshake mới.
openssl s_client \
  -connect orders.svc.example.internal:8443 \
  -servername orders.svc.example.internal \
  -showcerts </dev/null

# Thử HTTPS thực sự, với CA đã tin cậy và hostname verification.
curl --cacert ca-root.pem \
  https://orders.svc.example.internal:8443/actuator/health
~~~

Kết quả `s_client` cần được kiểm tra chứng thư leaf, serial/fingerprint, chain và trạng thái xác minh; endpoint có thể cần cung cấp CA bằng `-CAfile`. `curl --cacert` là ví dụ xác thực CA và hostname, nhưng endpoint kiểm tra sức khỏe có thể đặt ở đường dẫn khác hoặc yêu cầu xác thực. **Không sử dụng `curl -k`/`--insecure` để tuyên bố TLS đã an toàn**.

Nếu trước ứng dụng có load balancer, một lần handshake chỉ đại diện cho backend được chọn. Cần kiểm tra từng instance hoặc dùng telemetry/health gate về phiên bản chứng thư; nếu có SNI hoặc nhiều port TLS, kiểm tra đúng hostname và port.

## 8. Thu hồi chứng thư cũ và quản lý rollback

Thay chứng thư không nhất thiết phải thu hồi ngay leaf cũ. Với vòng thay bình thường, có thể duy trì ngắn hạn hai chứng thư còn hợp lệ để hỗ trợ rollout và rollback, miễn tuân thủ chính sách bảo mật. Nếu private key cũ bị lộ, danh tính máy chủ bị chiếm dụng hoặc quy định yêu cầu chấm dứt tin cậy, việc **thu hồi** cần xử lý khẩn cấp.

Vault PKI cho phép thu hồi theo serial, ví dụ thao tác **quản trị được phân quyền riêng**:

~~~bash
vault write pki/revoke serial_number="<serial-cua-chung-thu-cu>"
~~~

Thu hồi không có nghĩa mọi TLS client lập tức biết chứng thư cũ không còn hợp lệ. Hiệu quả phụ thuộc việc máy khách tải và kiểm tra CRL/OCSP theo thiết kế PKI, thời gian cache và cách triển khai kiểm tra trạng thái thu hồi. Với chứng thư rất ngắn hạn, chính sách có thể chủ yếu dựa vào TTL và cô lập workload; quyết định cần xét yêu cầu bảo mật cụ thể.

Khi rotation thất bại, có thể rollback về bản cũ **nếu bản đó còn hiệu lực, khóa chưa bị lộ và policy cho phép**. Không rollback sang chứng thư đã hết hạn, bị thu hồi hoặc sai SAN chỉ để “khôi phục dịch vụ”. Nếu mọi chứng thư hiện có đều không hợp lệ, chuyển sang quy trình khôi phục sự cố và cấp vật liệu hợp lệ mới.

## 9. Lỗi thường gặp, cảnh báo và kế hoạch dự phòng

| Hiện tượng | Khả năng nguyên nhân | Hành động |
| --- | --- | --- |
| Vault trả 403 khi cấp lại | Token hết hạn, workload auth sai, policy thiếu `update` cho `pki/issue/<role>` | Kiểm tra quá trình auth/token và policy đúng endpoint; không đưa token vào log |
| Vault trả 400 | CN/SAN không được role chấp nhận, TTL vượt giới hạn, CSR không hợp lệ | Kiểm tra role, request, SAN và giới hạn của issuer |
| API trả chứng thư nhưng TLS vẫn dùng serial cũ | Chưa cập nhật nơi terminate TLS, chưa reload, một replica bị bỏ sót | Đối chiếu cert trên runtime và từng instance; kích hoạt lại theo cơ chế được hỗ trợ |
| TLS handshake lỗi ngay sau reload | Private key không khớp leaf, thiếu chain, SAN/EKU sai, CA chưa tin cậy | Validate ở staging, khôi phục bản hợp lệ và kiểm tra chain/hostname |
| Cert mới hết hạn sớm hơn dự kiến | CA sắp hết hạn, role/backend giới hạn TTL | Đọc `Not After` thực tế trên leaf và theo dõi hạn của intermediate CA |
| Rotation hàng loạt gây tải lên Vault | Mọi workload cấp lại cùng một thời điểm | Giảm tần suất phù hợp, thêm jitter, giới hạn song song và retry có backoff |
| Lỗi Vault trong lúc rotation | Timeout, 429, 5xx, mất mạng hoặc leader failover | Giữ chứng thư cũ còn hợp lệ, retry hữu hạn, phát cảnh báo trước sát hạn; fail closed khi không còn cert hợp lệ |

Giám sát cần phân biệt ít nhất ba mốc:

- **`certificate_remaining_seconds`**: thời gian còn lại của **chứng thư đang phục vụ**, không chỉ chứng thư vừa được Vault cấp.
- **`certificate_rotation_last_success_timestamp`** và số lần/thời gian lỗi cấp mới, staging, reload, handshake; log chỉ nên chứa role, hostname, issuer ID/serial/fingerprint không nhạy cảm theo chính sách.
- **Độ đồng nhất** giữa các replica: còn bao nhiêu instance dùng serial cũ, serial mới; thời gian hoàn thành rollout và cảnh báo khi vượt ngưỡng.

Các tên metric trên chỉ là ví dụ để xây hệ thống quan sát, **không mặc định là metric có sẵn của Spring Vault**. Có thể đưa vào Micrometer/Prometheus và tạo cảnh báo nhiều mức, chẳng hạn cảnh báo sớm khi chạm ngưỡng rotation, cảnh báo khẩn khi gần hết hạn hoặc lỗi toàn bộ lần retry.

## 10. Kiểm thử tích hợp theo vòng đời

Một bài lab nên sử dụng Vault test instance có cấu hình PKI/issuer/role sẵn và một ứng dụng Spring Boot test chạy HTTPS. Phân tách tài khoản quản trị PKI và tài khoản cấp chứng thư của workload.

| Tình huống | Cách thử | Điều kiện đạt |
| --- | --- | --- |
| Phát hành cơ bản | Dùng `VaultPkiOperations.issueCertificate` hai lần cùng CN | Hai lần tạo chứng thư với serial khác nhau; thông tin SAN/TTL hợp lệ |
| Không có quyền | Workload thiếu `pki/issue/orders-server` | API báo lỗi phân quyền; không tạo/triển khai chứng thư |
| CN/SAN không hợp lệ | Yêu cầu domain ngoài `allowed_domains` | Vault từ chối yêu cầu theo role |
| Thay key pair | Cấp cert + key mới, dùng OpenSSL kiểm tra | Public key trên leaf khớp private key mới; không nhầm khóa cũ |
| Reload TLS thành công | Gắn vật liệu mới vào Spring Boot SSL bundle được hỗ trợ | Handshake tới server mới nhận serial/fingerprint mới; HTTPS health OK |
| Không reload được | Giả lập consumer không hỗ trợ hoặc cố ý không kích hoạt | Hệ thống phát hiện serial runtime còn cũ, không báo rotation hoàn tất |
| Mất Vault khi còn hạn | Ngắt Vault trong cửa sổ rotation | Service vẫn dùng chứng thư cũ còn hiệu lực; retry, cảnh báo và không tạo file rỗng |
| Cấp gần hết hạn | Yêu cầu TTL/issuer sát hạn | Chính sách ngăn cài chứng thư không còn đủ thời gian phục vụ |
| Client mTLS | Thay chứng thư client, tạo kết nối mTLS mới | Server chấp nhận đúng client identity, EKU/CA và chính sách phân quyền |
| CA thay đổi | Đổi issuer theo kế hoạch, cập nhật truststore | Client tin cả chain chuyển tiếp rồi mới rút CA cũ theo gate |

Khi viết test tự động, đừng chỉ assert kết quả `issueCertificate`. Hãy chứng minh trạng thái **trước/sau** qua X.509 đọc từ socket TLS, kiểm tra riêng happy path, rollback và failure path. Test không nên phụ thuộc vào việc Vault trả đúng một số serial hay một timestamp cố định; đó là dữ liệu động.

## 11. Checklist triển khai thực tế

Trước khi rollout, người phụ trách cần trả lời được:

1. **Ai sở hữu renewal?** Scheduler trong Java, controller riêng, cert-manager, sidecar hay nền tảng vận hành? Chỉ một nơi được chủ động cấp mới cho cùng bộ vật liệu TLS.
2. **Ai sở hữu key?** Vault tạo/trao bundle, hay workload/HSM tạo key và gửi CSR? Bảo vệ private key ở điểm nào và trong bao lâu?
3. **Đường đi TLS ở đâu?** Spring Boot, ingress, proxy hay client outbound? Mỗi nơi dùng cert/keystore/truststore nào?
4. **Khi nào rotate?** Ngưỡng tính từ `Not After` thực tế, có biên an toàn, jitter, retry/backoff và cảnh báo trước hết hạn.
5. **Làm sao biết đã thành công?** Serial/fingerprint trên handshake mới, readiness và kiểm tra hostname/CA, có xác minh đủ các replica.
6. **Điều gì xảy ra khi lỗi?** Không ghi đè bản đang hoạt động trước validate; rollback chỉ về chứng thư còn tin cậy; có kịch bản khi Vault không sẵn sàng.
7. **Khi nào thu hồi cert cũ?** Quy trình vận hành bình thường khác với khóa bị lộ; quyền revoke và phân phối CRL/OCSP phải rõ ràng.

Nhớ nguyên tắc trung tâm: **Vault PKI phát hành chứng thư mới; bộ phận triển khai đưa nó vào đúng thành phần TLS; handshake thực tế xác nhận toàn bộ quá trình đã có hiệu lực.** Với Spring Vault, mọi bước đều cần tôn trọng phân quyền workload, vòng đời token, sự nhất quán key pair và khả năng hoạt động khi Vault tạm thời không truy cập được.

### Câu hỏi tự kiểm tra

1. Vì sao gọi `vault lease renew` không thể kéo dài `Not After` của chứng thư X.509 hiện đang phục vụ?
2. Hai endpoint `pki/issue/<role>` và `pki/sign/<role>` khác nhau như thế nào về vị trí của private key?
3. Sau khi `VaultPkiOperations.issueCertificate` thành công, còn những bước nào để một server Spring Boot dùng chứng thư mới?
4. Vì sao cập nhật `tls.crt` trước `tls.key` có thể gây lỗi TLS, và có những biện pháp nào để tránh?
5. Khi cùng một CA tiếp tục cấp leaf mới, có cần thay truststore client không? Trường hợp nào câu trả lời thay đổi?
6. Sự khác nhau giữa “Vault cấp cert mới”, “file đã thay” và “TLS runtime dùng cert mới” được kiểm chứng bằng chỉ số hoặc thao tác nào?

### Tài liệu tham khảo

- [HashiCorp Vault — Set up and use the PKI secrets engine](https://developer.hashicorp.com/vault/docs/secrets/pki/setup)
- [HashiCorp Vault — PKI Secrets Engine HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/pki)
- [HashiCorp Vault — PKI considerations](https://developer.hashicorp.com/vault/docs/secrets/pki/considerations)
- [Spring Vault — PKI and VaultPkiOperations](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html)
- [Spring Vault — VaultPkiOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultPkiOperations.html)
- [Spring Boot — SSL bundles and reloading](https://docs.spring.io/spring-boot/reference/features/ssl.html)
