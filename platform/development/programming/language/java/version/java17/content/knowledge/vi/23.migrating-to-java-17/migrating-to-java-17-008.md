# Đối chiếu chứng thư, giao thức và cấu hình bảo mật hiện hành

Khi nâng một ứng dụng lên Java 17, cần kiểm tra cách ứng dụng xác thực đối tác TLS, cách JVM chọn giao thức và thuật toán mật mã, cũng như nguồn truststore/keystore mà runtime thực sự sử dụng. Một ứng dụng có thể biên dịch và chạy bình thường nhưng không kết nối được với server vì certificate chain không đáng tin, hostname không khớp, chứng thư hết hạn hoặc thuật toán đã bị chính sách bảo mật chặn.

Trong Java 17, phần lớn cấu hình TLS được thực hiện qua **JSSE (Java Secure Socket Extension)**, `SSLContext`, `SSLParameters`, `KeyStore`, `TrustManagerFactory`, `KeyManagerFactory` và các security properties của JDK. Công cụ `keytool` giúp xem, tạo và nhập chứng thư. TLS 1.2 và TLS 1.3 là các phiên bản giao thức cần tập trung; không nên khôi phục SSLv3 hoặc TLS 1.0/1.1 để làm cho một kết nối cũ hoạt động.

Bài này trình bày cách phân biệt danh tính với độ tin cậy, đọc certificate chain, kiểm tra SAN và hostname, cấu hình TLS client/server và mutual TLS, quản lý truststore/keystore, hiểu các thuật toán bị vô hiệu hóa, cùng quy trình chẩn đoán khi nâng ứng dụng lên Java 17. Các ví dụ dùng API và công cụ hiện hành của JDK 17; giá trị cụ thể cần được đối chiếu với chính sách của tổ chức và bản cập nhật JDK đang triển khai.

## 1. TLS bảo vệ điều gì?

TLS (Transport Layer Security) cung cấp các thuộc tính bảo mật cho kết nối giữa hai đầu:

- **Confidentiality:** dữ liệu truyền qua kết nối được mã hóa để bên thứ ba không đọc được nội dung.
- **Integrity:** dữ liệu được bảo vệ khỏi sửa đổi mà không bị phát hiện.
- **Authentication:** một hoặc cả hai đầu có thể chứng minh danh tính bằng chứng thư số.

Trong HTTPS, TLS bảo vệ kết nối HTTP giữa client và server. TLS cũng được dùng trong nhiều giao thức khác như kết nối database, SMTP, LDAP hoặc các dịch vụ nội bộ.

Một handshake TLS thường thực hiện các việc:

1. Hai bên thương lượng phiên bản TLS và bộ thuật toán có thể sử dụng.
2. Server trình certificate chain để client xác minh danh tính.
3. Hai bên thiết lập khóa phiên bằng cơ chế trao đổi khóa phù hợp.
4. Nếu dùng mutual TLS (mTLS), server cũng yêu cầu client trình chứng thư.
5. Sau handshake, dữ liệu ứng dụng được truyền qua kênh TLS đã thiết lập.

TLS không tự xác thực quyền nghiệp vụ của người dùng. Một chứng thư hợp lệ chứng minh danh tính theo PKI và chính sách trust; ứng dụng vẫn cần xác thực, phân quyền và kiểm tra dữ liệu ở tầng phù hợp.

## 2. TLS 1.2 và TLS 1.3 trong Java 17

Java 17 hỗ trợ TLS 1.2 và TLS 1.3 thông qua JSSE. Với SunJSSE mặc định, TLS 1.3 và TLS 1.2 là các giao thức được bật cho kết nối TLS thông thường. Các bản cập nhật JDK, vendor, security properties hoặc cấu hình ứng dụng có thể thay đổi tập giao thức và thuật toán được chấp nhận.

| Giao thức | Tình trạng khi triển khai Java 17 |
| --- | --- |
| TLS 1.3 | Giao thức hiện đại, được hỗ trợ và bật mặc định trong cấu hình JSSE thông thường |
| TLS 1.2 | Vẫn được hỗ trợ rộng rãi và thường được bật mặc định |
| TLS 1.1 | Đã lỗi thời và bị vô hiệu hóa theo mặc định trong cấu hình JDK hiện hành |
| TLS 1.0 | Đã lỗi thời và bị vô hiệu hóa theo mặc định trong cấu hình JDK hiện hành |
| SSLv3 và các SSL đời cũ | Không dùng; đã bị loại khỏi cấu hình bảo mật hiện đại |

TLS 1.3 đơn giản hóa một số lựa chọn mật mã trong handshake và loại bỏ nhiều thuật toán cũ. TLS 1.2 vẫn có thể an toàn khi dùng bộ cipher suite và tham số mạnh, được cấu hình phù hợp.

### 2.1. Protocol và cipher suite là hai khái niệm khác nhau

**Protocol** xác định phiên bản và quy tắc trao đổi của TLS, ví dụ `TLSv1.2` hoặc `TLSv1.3`.

**Cipher suite** mô tả tổ hợp thuật toán dùng trong một phiên TLS. Tùy phiên bản, suite có thể bao gồm thuật toán xác thực, trao đổi khóa, mã hóa và kiểm tra toàn vẹn. Với TLS 1.3, tên cipher suite tập trung vào thuật toán mã hóa đối xứng và hash; cơ chế trao đổi khóa và xác thực được thương lượng riêng.

Một số TLS 1.3 cipher suite hiện đại thường gặp:

- `TLS_AES_128_GCM_SHA256`
- `TLS_AES_256_GCM_SHA384`
- `TLS_CHACHA20_POLY1305_SHA256`

Với TLS 1.2, ưu tiên các suite dùng AEAD như AES-GCM hoặc ChaCha20-Poly1305, kết hợp trao đổi khóa và xác thực phù hợp. Không chọn suite chỉ dựa vào tên; hãy xem xét khả năng tương thích của hai đầu, chính sách tổ chức và cấu hình JDK.

Tránh các thuật toán đã lỗi thời hoặc yếu như RC4, DES, 3DES, MD5 và các cấu hình trao đổi khóa yếu. Không nên bật lại chúng để vượt qua lỗi handshake.

### 2.2. Kiểm tra protocol được runtime hỗ trợ và bật mặc định

Có thể xem các protocol mà SSLContext hỗ trợ và tập protocol mặc định:

~~~java
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import java.util.Arrays;

public class TlsProtocolInfo {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getDefault();

        SSLParameters supported = context.getSupportedSSLParameters();
        SSLParameters defaults = context.getDefaultSSLParameters();

        System.out.println("Supported: "
                + Arrays.toString(supported.getProtocols()));

        System.out.println("Default enabled: "
                + Arrays.toString(defaults.getProtocols()));
    }
}
~~~

`getSupportedSSLParameters()` cho biết các protocol mà provider hỗ trợ; `getDefaultSSLParameters()` cho biết các giá trị mặc định của provider tại thời điểm lấy cấu hình. Một protocol được hỗ trợ chưa chắc được phép dùng: disabled-algorithm policy và các constraint khác vẫn có thể từ chối nó.

Đừng dùng kết quả từ một máy phát triển để suy ra mọi máy production có cấu hình giống hệt. Hãy kiểm tra trên đúng vendor, bản cập nhật JDK và cấu hình runtime được triển khai.

## 3. Chứng thư số và certificate chain

Certificate (chứng thư số) liên kết một public key với danh tính được chứng thực bởi một CA hoặc một trust anchor. Chứng thư X.509 thường chứa:

- Subject: danh tính được chứng thư mô tả.
- Issuer: CA đã ký chứng thư.
- Subject Public Key Info: public key và thuật toán tương ứng.
- Validity: thời điểm bắt đầu và kết thúc hiệu lực.
- Serial number: số sê-ri của chứng thư.
- Key Usage và Extended Key Usage: mục đích sử dụng khóa.
- Subject Alternative Name (SAN): tên DNS/IP hoặc danh tính khác được chứng thư xác nhận.
- Signature Algorithm và chữ ký của issuer.
- Basic Constraints: cho biết chứng thư có đại diện CA hay không.

### 3.1. Leaf, intermediate và root CA

Một certificate chain điển hình:

~~~text
Server certificate (leaf)
          |
          | được ký bởi
          v
Intermediate CA
          |
          | được ký bởi
          v
Root CA (trust anchor)
~~~

Server thường gửi leaf certificate cùng các intermediate cần thiết. Client có root CA đáng tin trong truststore để xác minh đường dẫn chứng thư. Root certificate thường là trust anchor được cài sẵn hoặc được quản lý riêng; không nên mặc định server phải gửi root trong mọi trường hợp.

Nếu server thiếu intermediate certificate, client có thể không xây dựng được chain dù root CA đã nằm trong truststore. Đây là một nguyên nhân phổ biến của lỗi `PKIX path building failed`.

### 3.2. Kiểm tra thời hạn và mục đích sử dụng

Certificate cần thỏa mãn các điều kiện phù hợp:

- Thời điểm hiện tại nằm trong khoảng `Not Before` và `Not After`.
- Chữ ký và chain có thể được xác minh.
- Issuer dẫn đến trust anchor được chấp nhận.
- Key Usage và Extended Key Usage phù hợp vai trò.
- Key size và signature algorithm đáp ứng security policy.
- Certificate chưa bị thu hồi theo chính sách kiểm tra revocation đang áp dụng.

Một chứng thư server thường cần Extended Key Usage `serverAuth`; chứng thư client trong mTLS thường cần `clientAuth`. Key Usage cụ thể phụ thuộc loại khóa và cách triển khai TLS. Không nên tái sử dụng certificate cho nhiều vai trò chỉ vì handshake thử nghiệm thành công.

### 3.3. SAN và hostname verification

Khi kết nối tới `api.example.com`, client phải xác minh rằng chứng thư thực sự đại diện cho hostname đó. Tên DNS hoặc địa chỉ IP cần được ghi trong **Subject Alternative Name (SAN)** phù hợp.

Ví dụ SAN:

~~~text
X509v3 Subject Alternative Name:
    DNS:api.example.com
    DNS:api.internal.example.com
~~~

Nếu client truy cập bằng IP address, chứng thư cần SAN dạng IP tương ứng. Không nên dựa vào Common Name (CN) như cơ chế thay thế SAN trong thiết kế mới.

Hostname verification là bước riêng với việc xác minh chain:

- Chain hợp lệ xác nhận chứng thư được phát hành bởi trust anchor được chấp nhận.
- Hostname verification xác nhận danh tính trong chứng thư khớp với host mà client đang kết nối.

Tắt hostname verification khiến client có thể chấp nhận một chứng thư hợp lệ nhưng thuộc về server khác. Không dùng trust-all TrustManager hoặc bỏ kiểm tra hostname để sửa lỗi môi trường.

## 4. Truststore và keystore

Hai loại kho này thường bị nhầm:

- **Truststore** chứa chứng thư hoặc trust anchor mà ứng dụng tin cậy khi xác minh đối tác.
- **Keystore** chứa private key cùng certificate chain của chính ứng dụng khi ứng dụng cần chứng minh danh tính.

| Kho | Nội dung điển hình | Dùng cho |
| --- | --- | --- |
| Truststore | Root CA hoặc CA nội bộ được tin cậy | Xác minh certificate chain của peer |
| Keystore | Private key và certificate chain của ứng dụng | Trình chứng thư server hoặc client |
| JDK `cacerts` | Bộ trust anchor được phân phối cùng JDK | Trust mặc định của JSSE trong nhiều cấu hình |

Ví dụ:

- Một HTTPS client cần truststore để tin CA đã cấp chứng thư cho server.
- Một HTTPS server cần keystore chứa private key và certificate chain của server.
- Với mTLS, client cần keystore có identity certificate/private key; server cần truststore tin CA cấp chứng thư client. Server cũng có keystore riêng để chứng minh danh tính của mình.

Private key phải được bảo vệ nghiêm ngặt. Không commit keystore/password vào source control, không ghi password vào log và không phân phối cùng ứng dụng desktop nếu đó là private key dùng chung cho toàn bộ người dùng.

### 4.1. Định dạng PKCS12 và JKS

Java 17 hỗ trợ cả PKCS12 và JKS. PKCS12 là định dạng mặc định của KeyStore trong các JDK hiện đại và có khả năng tương tác rộng với công cụ khác.

| Định dạng | Đặc điểm |
| --- | --- |
| PKCS12 (`.p12`, `.pfx`) | Định dạng tiêu chuẩn phổ biến, hỗ trợ private key và certificate |
| JKS (`.jks`) | Định dạng Java KeyStore cũ; vẫn có thể đọc/ghi trong Java 17 |

Khi tạo kho mới, thường nên chọn PKCS12 trừ khi có yêu cầu tương thích cụ thể. Việc một kho cũ dùng JKS không có nghĩa cần chuyển đổi ngay nếu nó vẫn được quản lý và bảo vệ đúng; hãy lên kế hoạch chuyển đổi khi có lý do vận hành hoặc tích hợp.

### 4.2. Truststore mặc định của JSSE

JSSE có cơ chế tìm truststore mặc định. Trong các cấu hình JDK phổ biến, runtime kiểm tra file `jssecacerts` trước rồi đến `cacerts` trong vùng bảo mật của JDK nếu không chỉ định truststore riêng.

Có thể xem truststore `cacerts`:

~~~bash
keytool -list -cacerts
~~~

Lệnh có thể yêu cầu password của kho. Không cần ghi password vào command line hoặc script chia sẻ.

Nếu ứng dụng đặt `javax.net.ssl.trustStore` tới một kho tùy chỉnh, kho đó trở thành nguồn truststore được cấu hình cho JSSE; đừng giả định nó tự động hợp nhất với toàn bộ CA trong `cacerts`. Nếu ứng dụng cần cả CA công khai lẫn CA nội bộ, hãy tạo và quản lý tập trust anchor kết hợp một cách có chủ đích.

Không nên sửa trực tiếp `cacerts` của JDK trên máy chủ bằng thao tác thủ công không được quản lý. Một lần cập nhật JDK hoặc thay runtime image có thể thay thế kho này. Với CA nội bộ, truststore riêng do ứng dụng hoặc hệ thống triển khai quản lý thường dễ kiểm soát hơn.

## 5. Dùng keytool để xem và quản lý certificate

`keytool` là công cụ đi kèm JDK để quản lý key pair, certificate, certificate request và keystore/truststore.

Xem certificate từ file:

~~~bash
keytool -printcert -file server-cert.pem
~~~

Liệt kê một keystore:

~~~bash
keytool -list -v -keystore server.p12 -storetype PKCS12
~~~

Xuất certificate ở dạng PEM:

~~~bash
keytool -exportcert -rfc -alias server -keystore server.p12 -storetype PKCS12 -file server-cert.pem
~~~

Các lệnh đọc kho có thể yêu cầu password. Không đưa password thật vào lịch sử terminal hoặc script dùng chung.

### 5.1. Tạo key pair cho môi trường thử nghiệm

Ví dụ tạo private key và self-signed certificate để thử nghiệm:

~~~bash
keytool -genkeypair -alias server -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 365 -dname "CN=api.example.com, O=Example, C=VN" -ext "SAN=dns:api.example.com" -keystore server.p12 -storetype PKCS12
~~~

Lệnh tạo:

- Một key pair RSA.
- Một self-signed certificate cho alias `server`.
- SAN cho hostname `api.example.com`.
- Keystore PKCS12 lưu private key và certificate.

Certificate self-signed chỉ được peer chấp nhận nếu peer chủ động trust certificate đó. Đây là cách kiểm thử trong môi trường kiểm soát, không phải quy trình phát hành chứng thư production thông thường.

### 5.2. Tạo CSR để CA ký

Trong production, private key thường được tạo và giữ trong hệ thống kiểm soát của tổ chức; public key được gửi trong Certificate Signing Request (CSR) để CA cấp chứng thư.

~~~bash
keytool -certreq -alias server -keystore server.p12 -storetype PKCS12 -file server.csr -ext "SAN=dns:api.example.com,dns:api.internal.example.com"
~~~

CSR chứa public key và thông tin yêu cầu chứng thư, không chứa private key. CA xác minh quyền sở hữu/ủy quyền hostname theo quy trình của mình rồi phát hành leaf certificate cùng chain.

Khi nhận certificate reply, cần bảo đảm chain tương ứng với key pair trong alias đã tạo. Nếu chain có intermediate CA, import CA certificate cần thiết vào keystore theo quy trình `keytool` trước khi import reply, hoặc dùng file chain do CA cung cấp theo định dạng được hỗ trợ.

### 5.3. Import CA certificate vào truststore

Ví dụ import root CA được tổ chức xác minh trước:

~~~bash
keytool -importcert -alias company-root-ca -file company-root-ca.pem -keystore truststore.p12 -storetype PKCS12
~~~

Trước khi trust một certificate, cần xác minh fingerprint và nguồn phát hành qua kênh đáng tin. Không chấp nhận prompt xác nhận trust chỉ vì file được gửi kèm ticket hoặc email không được xác thực.

Kiểm tra fingerprint:

~~~bash
keytool -printcert -file company-root-ca.pem
~~~

Có thể đối chiếu SHA-256 fingerprint với thông tin được công bố qua kênh độc lập của tổ chức.

### 5.4. Kiểm tra certificate chain trong keystore

~~~bash
keytool -list -v -alias server -keystore server.p12 -storetype PKCS12
~~~

Kiểm tra:

- Entry có phải `PrivateKeyEntry` khi cần private key không.
- Certificate chain có đủ leaf và intermediate cần thiết không.
- Subject, Issuer, validity và SAN có đúng không.
- Key Usage và Extended Key Usage có phù hợp không.
- Signature algorithm và key size có đáp ứng policy không.

Không hiển thị hoặc xuất private key ra file chỉ để kiểm tra thông tin certificate. `keytool -list` và `-printcert` thường đủ để quan sát metadata công khai.

## 6. Cấu hình JSSE bằng system properties

JSSE hỗ trợ các system properties phổ biến để cấu hình kho khóa và trust:

| Property | Vai trò |
| --- | --- |
| `javax.net.ssl.trustStore` | Đường dẫn truststore |
| `javax.net.ssl.trustStoreType` | Định dạng truststore, ví dụ `PKCS12` |
| `javax.net.ssl.trustStorePassword` | Password truststore |
| `javax.net.ssl.keyStore` | Đường dẫn keystore identity |
| `javax.net.ssl.keyStoreType` | Định dạng keystore |
| `javax.net.ssl.keyStorePassword` | Password keystore |
| `javax.net.ssl.keyStoreProvider` | Provider cho keystore khi cần chỉ định |

Ví dụ khởi chạy với truststore riêng:

~~~bash
java -Djavax.net.ssl.trustStore=/opt/app/security/truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12 -jar application.jar
~~~

Nếu cần client identity certificate, có thể cấu hình thêm keystore:

~~~bash
java -Djavax.net.ssl.keyStore=/opt/app/security/client.p12 -Djavax.net.ssl.keyStoreType=PKCS12 -jar application.jar
~~~

Password có thể được cung cấp theo cơ chế triển khai phù hợp, nhưng không nên đưa secret trực tiếp vào command line vì process listing, shell history hoặc log có thể làm lộ thông tin. Dùng secret manager, cơ chế mount secret và quyền file hạn chế theo chính sách hệ thống.

### 6.1. Đường dẫn và quyền file

Một cấu hình truststore đúng vẫn có thể thất bại nếu:

- File không tồn tại trong container hoặc máy chạy.
- User của process không có quyền đọc.
- Password hoặc store type không khớp.
- Alias/certificate chain không đúng.
- File bị thay thế trong lúc triển khai.

Đường dẫn nên được cấu hình theo môi trường, không hard-code vào source. Keystore chứa private key cần quyền truy cập chặt hơn truststore chỉ chứa public CA certificate.

### 6.2. Custom truststore có thay thế trust mặc định?

Có. Khi chỉ định truststore riêng qua `javax.net.ssl.trustStore`, ứng dụng không nên giả định JSSE sẽ tự ghép tất cả certificate từ `cacerts` vào kho tùy chỉnh. Nếu cần trust cả public CA lẫn CA nội bộ, cần xây dựng một truststore có đủ trust anchor hoặc thiết kế `TrustManager` có chủ đích để kết hợp nguồn trust.

Không dùng một truststore chứa mọi certificate nhận được từ bất kỳ peer nào. Truststore phải thể hiện rõ các CA mà tổ chức chủ động tin cậy.

## 7. Dùng SSLContext trong Java code

`SSLContext` là điểm cấu hình trung tâm cho các kết nối TLS. Nó chứa key managers, trust managers và nguồn random dùng cho TLS provider.

Tạo context mặc định:

~~~java
import javax.net.ssl.SSLContext;

SSLContext context = SSLContext.getDefault();
~~~

Context mặc định sử dụng cấu hình JSSE mặc định của tiến trình, bao gồm trust/key manager mặc định theo cơ chế runtime và system properties liên quan.

Có thể truyền context vào Java HTTP Client:

~~~java
import java.net.http.HttpClient;
import javax.net.ssl.SSLContext;

HttpClient client = HttpClient.newBuilder()
        .sslContext(SSLContext.getDefault())
        .build();
~~~

`HttpClient` HTTPS thực hiện xác minh hostname theo hành vi bảo mật mặc định của API. Không tắt xác minh hostname để làm cho một certificate sai tên được chấp nhận.

### 7.1. Giới hạn protocol bằng SSLParameters khi có yêu cầu

Nếu ứng dụng có yêu cầu tương thích rõ ràng, có thể cấu hình tập protocol cho client:

~~~java
import java.net.http.HttpClient;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;

SSLParameters parameters = new SSLParameters();
parameters.setProtocols(new String[] {"TLSv1.3", "TLSv1.2"});

HttpClient client = HttpClient.newBuilder()
        .sslContext(SSLContext.getDefault())
        .sslParameters(parameters)
        .build();
~~~

Đây là cấu hình minh họa cho việc chỉ định protocol hiện đại. Nếu không có yêu cầu đặc biệt, ưu tiên cấu hình mặc định đã được JDK quản lý. Không thêm protocol lỗi thời để khắc phục server cũ; cần nâng cấp server hoặc proxy để hỗ trợ TLS hiện hành.

Tùy chọn trong `SSLParameters` có thể tương tác với các thiết lập khác của client và provider. Hãy kiểm thử handshake thực tế trên đúng JDK 17 và endpoint mục tiêu.

## 8. Hostname verification với SSLSocket

Khi dùng API cấp thấp như `SSLSocket`, ứng dụng phải bảo đảm endpoint identification được cấu hình phù hợp. Ví dụ HTTPS:

~~~java
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;

try (SSLSocket socket = (SSLSocket) SSLContext.getDefault()
        .getSocketFactory()
        .createSocket("api.example.com", 443)) {

    SSLParameters parameters = socket.getSSLParameters();
    parameters.setProtocols(new String[] {"TLSv1.3", "TLSv1.2"});
    parameters.setEndpointIdentificationAlgorithm("HTTPS");

    socket.setSSLParameters(parameters);
    socket.startHandshake();

    System.out.println("TLS protocol: "
            + socket.getSession().getProtocol());
}
~~~

`setEndpointIdentificationAlgorithm("HTTPS")` yêu cầu kiểm tra danh tính hostname theo quy tắc HTTPS trong handshake. Nếu kết nối dùng một giao thức ứng dụng khác HTTPS, phải áp dụng cơ chế xác minh endpoint tương ứng của giao thức đó; không tự coi hostname check HTTPS là một giải pháp chung cho mọi giao thức.

Khi tạo socket bằng hostname, JSSE có thể sử dụng hostname đó cho SNI (Server Name Indication) trong handshake. SNI giúp server chọn certificate phù hợp khi nhiều hostname cùng dùng một địa chỉ IP. Nếu ứng dụng tự tạo socket hoặc dùng IP thay cho DNS name, cần hiểu cách SNI và SAN được xử lý.

## 9. Mutual TLS (mTLS)

Trong TLS thông thường, server trình chứng thư để client xác minh server. Với **mutual TLS**, server cũng yêu cầu client trình certificate để xác minh danh tính client.

~~~text
Client                              Server
  |                                   |
  | -------- ClientHello ----------> |
  | <------- Server certificate ---- |
  | -------- Client certificate ---> |  (khi server yêu cầu)
  | <------ Handshake complete ----> |
  |                                   |
  | ======= Encrypted channel ====== |
~~~

mTLS thường dùng trong service-to-service communication, API nội bộ hoặc hệ thống cần xác thực workload ở tầng transport.

### 9.1. Client cần những gì?

Client mTLS thường cần:

- Truststore tin CA cấp chứng thư server.
- Keystore chứa private key và client certificate chain.
- Key Usage/EKU của client certificate phù hợp với `clientAuth`.
- Cơ chế bảo vệ private key và password.

Server cần:

- Keystore chứa server private key và certificate chain.
- Truststore tin CA cấp client certificate.
- Cấu hình yêu cầu client authentication.
- Kiểm tra identity và authorization của client sau khi TLS handshake hoàn tất.

Một certificate được CA tin cậy không tự động có nghĩa client được phép gọi mọi API. Ứng dụng vẫn cần ánh xạ danh tính certificate sang quyền nghiệp vụ.

### 9.2. Tạo SSLContext với KeyManager và TrustManager

Ví dụ minh họa tạo SSLContext cho client mTLS. Hàm lấy secret là placeholder của ứng dụng; không đặt password thật trong source:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

char[] keyStorePassword = obtainKeyStorePassword();
char[] privateKeyPassword = obtainPrivateKeyPassword();
char[] trustStorePassword = obtainTrustStorePassword();

KeyStore identity = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("client.p12"))) {
    identity.load(in, keyStorePassword);
}

KeyManagerFactory keyManagers = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
keyManagers.init(identity, privateKeyPassword);

KeyStore trust = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("truststore.p12"))) {
    trust.load(in, trustStorePassword);
}

TrustManagerFactory trustManagers = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
trustManagers.init(trust);

SSLContext context = SSLContext.getInstance("TLS");
context.init(
        keyManagers.getKeyManagers(),
        trustManagers.getTrustManagers(),
        null
);
~~~

Sau đó truyền `context` vào client:

~~~java
HttpClient client = HttpClient.newBuilder()
        .sslContext(context)
        .build();
~~~

Ví dụ trên chỉ trình bày cách nối KeyManagerFactory và TrustManagerFactory. Trong ứng dụng thực tế, cần xử lý password theo secret management, xóa mảng `char[]` sau khi không còn cần, đóng stream, chọn đúng alias nếu keystore có nhiều identity và kiểm thử certificate chain.

### 9.3. Yêu cầu client certificate ở server

Với server dùng `SSLServerSocket`, có thể yêu cầu client certificate:

~~~java
SSLServerSocket serverSocket = (SSLServerSocket)
        context.getServerSocketFactory().createServerSocket(8443);

serverSocket.setNeedClientAuth(true);
~~~

`setNeedClientAuth(true)` yêu cầu client cung cấp certificate; handshake sẽ thất bại nếu client không trình được certificate được server chấp nhận. `setWantClientAuth(true)` chỉ yêu cầu theo chế độ không bắt buộc, vì thế không tương đương với chính sách mTLS bắt buộc.

Trong framework server thực tế, cấu hình mTLS thường được thực hiện qua connector hoặc server configuration của framework. Dù dùng API nào, cần xác minh truststore, client certificate, hostname/identity policy và authorization sau handshake.

## 10. Security properties của JDK

Ngoài system properties, Java có **security properties** được đọc từ cấu hình bảo mật của runtime. Trong JDK 17, file chính thường nằm tại:

~~~text
JAVA_HOME/conf/security/java.security
~~~

Một số security properties liên quan TLS và certificate:

| Property | Vai trò |
| --- | --- |
| `jdk.tls.disabledAlgorithms` | Các protocol, cipher, key size hoặc thuật toán TLS bị vô hiệu hóa |
| `jdk.certpath.disabledAlgorithms` | Thuật toán và tham số bị hạn chế trong quá trình xác minh certificate path |
| `jdk.jar.disabledAlgorithms` | Thuật toán bị hạn chế khi kiểm tra chữ ký JAR |
| `crypto.policy` | Chính sách giới hạn mật mã JCE; JDK hiện đại mặc định dùng chính sách unlimited |

Danh sách disabled algorithm có thể thay đổi theo bản cập nhật bảo mật của JDK. Đừng sao chép một chuỗi cấu hình từ bài viết cũ hoặc một máy khác rồi ghi đè file bảo mật mà không hiểu ý nghĩa từng mục.

### 10.1. jdk.tls.disabledAlgorithms

Property này giới hạn các protocol và thuật toán TLS không còn được chấp nhận. Ví dụ cấu hình mặc định của các bản JDK có thể chặn TLS 1.0/1.1, SSLv3, RC4, DES hoặc các cấu hình key/signature yếu.

Không nên xóa các mục bị vô hiệu hóa chỉ để kết nối được với một server cũ. Nếu server chỉ hỗ trợ TLS 1.0, cipher yếu hoặc certificate dùng thuật toán không còn được chấp nhận, hướng xử lý là nâng cấp server, certificate hoặc thiết bị trung gian.

### 10.2. jdk.certpath.disabledAlgorithms

Property này được dùng trong kiểm tra certificate path. Một certificate có thể có chain đúng về mặt hình thức nhưng vẫn bị từ chối vì thuật toán chữ ký hoặc kích thước khóa vi phạm policy.

Ví dụ, một CA cũ ký certificate bằng thuật toán yếu hoặc dùng RSA key quá ngắn có thể dẫn đến lỗi algorithm constraints. Cần phát hành lại certificate/chain với thuật toán và key size phù hợp thay vì tắt ràng buộc toàn JVM.

### 10.3. Unlimited cryptographic policy

Các JDK hiện đại, bao gồm Java 17, dùng chính sách JCE unlimited theo mặc định. Thông thường không cần tải hoặc cài thêm “unlimited strength jurisdiction policy files” như hướng dẫn cũ cho các JDK đời trước.

Nếu ứng dụng hoặc vendor runtime có cấu hình riêng, hãy xác nhận bằng runtime thực tế. Không lấy một quy trình cài policy file cũ áp dụng cho Java 17.

### 10.4. Thay đổi security properties có kiểm soát

Có thể cung cấp file security properties bổ sung qua system property `java.security.properties` khi khởi chạy JVM. Cú pháp một dấu `=` dùng file bổ sung/ghi đè các property được chỉ định; cú pháp hai dấu `==` thay thế toàn bộ security properties mặc định bằng file được chỉ định.

Ví dụ tổng quát:

~~~bash
java -Djava.security.properties=/opt/app/security/extra.security -jar application.jar
~~~

Thay thế toàn bộ security configuration bằng `==` có thể làm mất nhiều thiết lập bảo vệ của JDK. Chỉ dùng khi hiểu rõ toàn bộ cấu hình và có quy trình kiểm thử, phê duyệt, cập nhật. Với đa số ứng dụng, nên giữ baseline của JDK và chỉ bổ sung những thay đổi thật sự cần thiết.

## 11. Certificate revocation và kiểm tra trạng thái chứng thư

Xác minh certificate chain và validity không đồng nghĩa lúc nào cũng đã kiểm tra trạng thái thu hồi. PKI có thể sử dụng CRL (Certificate Revocation List) hoặc OCSP (Online Certificate Status Protocol) để công bố trạng thái certificate.

Java PKIX/JSSE có các tùy chọn và provider liên quan revocation checking, nhưng việc bật kiểm tra có thể phụ thuộc hạ tầng CA, khả năng truy cập OCSP/CRL, responder và chính sách fail-open/fail-closed.

Trước khi bật revocation checking trong production, cần xác định:

- CA có phát hành CRL hoặc OCSP responder không.
- Runtime có thể truy cập endpoint kiểm tra trong mạng thực tế không.
- Hệ thống xử lý thế nào khi responder không khả dụng.
- Độ trễ kiểm tra có ảnh hưởng handshake hay không.
- Chính sách tổ chức yêu cầu fail-closed hay cơ chế khác.

Không nên tuyên bố rằng mọi kết nối TLS của JSSE luôn kiểm tra revocation online theo cùng một cách. Hãy cấu hình và xác minh theo PKI thực tế của tổ chức.

## 12. Chẩn đoán lỗi TLS và certificate

Khi nâng ứng dụng lên Java 17, nên đọc loại lỗi cụ thể thay vì thêm nhiều JVM flags cùng lúc.

| Lỗi hoặc triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `PKIX path building failed` | Không xây dựng được chain đến trust anchor | Kiểm tra truststore, root/intermediate và certificate chain server gửi |
| `unable to find valid certification path` | CA chưa được tin cậy hoặc chain thiếu | Xác minh CA/fingerprint và import trust anchor phù hợp |
| `No subject alternative DNS name matching` | Hostname không có trong SAN | Cấp certificate có SAN đúng hostname client dùng |
| `CertificateExpiredException` | Certificate đã hết hạn | Gia hạn/reissue certificate và kiểm tra clock của máy |
| `NotBefore` chưa đến | Certificate chưa có hiệu lực hoặc clock sai | Kiểm tra thời gian hệ thống và validity |
| `protocol_version` hoặc handshake alert tương tự | Hai đầu không có protocol chung | Xác nhận server hỗ trợ TLS 1.2/1.3 và policy client |
| `handshake_failure` | Có thể do cipher, certificate, client auth hoặc policy | Bật TLS debug trong môi trường kiểm thử và xem handshake |
| `Algorithm constraints check failed` | Thuật toán/key size bị security policy chặn | Kiểm tra disabled algorithms và phát hành certificate mới phù hợp |
| `bad_certificate` | Peer từ chối certificate hoặc chain | Kiểm tra EKU, Key Usage, trust và client/server identity |
| `UnrecoverableKeyException` | Password hoặc private key entry không đúng | Kiểm tra store/key password, alias và loại entry |
| `No available authentication scheme` | Server không tìm được certificate/algorithm phù hợp | Kiểm tra key manager, key type, certificate chain và TLS version |

### 12.1. Bật JSSE debug có kiểm soát

Có thể bật log handshake trong môi trường phát triển hoặc kiểm thử:

~~~bash
java -Djavax.net.debug=ssl,handshake,trustmanager -jar application.jar
~~~

Log có thể hiển thị protocol negotiation, certificate chain, trust manager decision và các bước handshake. Nó có thể rất dài, ảnh hưởng hiệu năng và chứa thông tin nhạy cảm về hạ tầng. Chỉ bật trong thời gian điều tra, giới hạn quyền truy cập log và tắt sau khi hoàn tất.

Để điều tra certificate path, có thể dùng:

~~~bash
java -Djava.security.debug=certpath -jar application.jar
~~~

Đây là log chẩn đoán sâu, không nên bật thường trực trong production nếu chưa đánh giá overhead và lượng dữ liệu phát sinh.

### 12.2. Dùng keytool để xác minh đầu vào

Trước khi thay đổi cấu hình JVM, kiểm tra certificate và store:

~~~bash
keytool -printcert -file server-cert.pem
keytool -list -v -keystore truststore.p12 -storetype PKCS12
keytool -list -v -keystore client.p12 -storetype PKCS12
~~~

Xác nhận alias, chain, validity, SAN, issuer và loại entry. Nếu certificate được lấy từ server, hãy lấy qua kênh đáng tin và đối chiếu fingerprint; không tự động import certificate chỉ vì handshake đang lỗi.

## 13. Những cấu hình cần tránh

Một số cách sửa lỗi cũ làm suy yếu bảo mật và không nên dùng trong Java 17:

- Bật lại SSLv3, TLS 1.0 hoặc TLS 1.1.
- Cho phép RC4, DES, 3DES, MD5 hoặc thuật toán chữ ký yếu.
- Tạo `TrustManager` chấp nhận mọi certificate.
- Tắt hostname verification.
- Tin một certificate chỉ vì nó được gửi cùng ứng dụng mà không xác minh fingerprint/nguồn phát hành.
- Đặt password private key/truststore trực tiếp trong source hoặc log.
- Mở rộng truststore bằng certificate không rõ nguồn.
- Ghi đè toàn bộ `java.security` chỉ để bỏ một algorithm constraint.
- Dùng private JDK internals để can thiệp TLS thay cho API JSSE công khai.

Nếu một hệ thống chỉ hoạt động khi tắt kiểm tra certificate hoặc hạ TLS xuống giao thức cũ, cần sửa certificate, PKI hoặc endpoint server. Không coi cấu hình tạm thời yếu hơn là một bản nâng cấp hoàn tất.

## 14. Quy trình rà soát khi nâng cấp lên Java 17

Có thể thực hiện theo trình tự sau:

1. **Xác nhận runtime:** ghi nhận vendor, version và update level của JDK 17 trên môi trường build, test và production.
2. **Kiểm tra protocol:** xem protocol mặc định và policy disabled algorithms trên đúng runtime.
3. **Lập danh sách endpoint:** ghi rõ hostname, port, protocol, server owner và yêu cầu mTLS nếu có.
4. **Kiểm tra certificate:** validity, SAN, EKU, Key Usage, key size, signature algorithm và chain.
5. **Kiểm tra trust:** xác định truststore nào được sử dụng; đối chiếu CA/fingerprint và intermediate chain.
6. **Kiểm tra identity:** với client/server mTLS, xác nhận keystore chứa đúng private key và certificate chain.
7. **Kiểm tra cấu hình:** rà system properties, SSLContext custom, trust/key manager và security properties.
8. **Chạy integration test:** thực hiện handshake tới từng endpoint bằng đúng JDK 17 và cấu hình triển khai.
9. **Quan sát lỗi:** dùng JSSE debug/certpath debug trong môi trường kiểm thử nếu handshake thất bại.
10. **Kiểm tra vận hành:** bảo đảm certificate renewal, secret rotation, truststore update và alert expiry có quy trình.
11. **Loại bỏ cấu hình yếu:** bỏ các exception tạm thời, protocol cũ, trust-all và hostname verification bypass.
12. **Lặp lại trên artifact cuối:** test container/runtime image/installer thực tế được triển khai, không chỉ máy developer.

### 14.1. Ma trận kiểm thử tối thiểu

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Server có certificate chain hợp lệ và SAN đúng | Handshake thành công |
| Server thiếu intermediate CA | Client từ chối hoặc báo lỗi chain; sau khi sửa chain thì thành công |
| Certificate hết hạn | Client từ chối |
| SAN không khớp hostname | Client từ chối hostname |
| Server chỉ hỗ trợ TLS 1.0/1.1 | Kết nối thất bại theo baseline bảo mật hiện hành |
| Server hỗ trợ TLS 1.2 hoặc 1.3 với suite phù hợp | Handshake thành công |
| mTLS client không có certificate khi server bắt buộc | Handshake thất bại |
| mTLS client có certificate được CA tin và đúng EKU | Handshake thành công; ứng dụng tiếp tục authorization |
| Truststore custom thiếu CA cần thiết | Client từ chối chain |
| Certificate dùng thuật toán bị disabled | Certificate/protocol bị policy từ chối |

Test các trường hợp thất bại có chủ đích giúp xác nhận ứng dụng thật sự kiểm tra trust và hostname thay vì chỉ chạy được với endpoint hợp lệ.

## 15. Quản lý certificate và secret trong vận hành

Certificate thường có vòng đời ngắn hơn vòng đời ứng dụng. Cấu hình TLS vì vậy cần được vận hành cùng quy trình gia hạn và luân chuyển:

- Theo dõi ngày hết hạn của leaf và intermediate certificate.
- Cảnh báo trước khi certificate hết hạn đủ lâu để gia hạn và triển khai.
- Xác định ai sở hữu private key, ai cấp certificate và ai cập nhật truststore.
- Có quy trình xoay private key và thay certificate chain.
- Cập nhật truststore khi CA thay đổi theo quy trình xác minh.
- Kiểm thử rolling update để tránh các instance dùng chain hoặc trust khác nhau.
- Không ghi password/private key vào repository, image layer hoặc log.
- Phân quyền đọc keystore/truststore theo user chạy process.
- Có kế hoạch rollback certificate khi cần nhưng không quay lại thuật toán yếu.

Truststore cũng cần được cập nhật khi CA root/intermediate thay đổi hoặc chính sách trust được điều chỉnh. Không nên sao chép `cacerts` từ một JDK cũ rồi giữ cố định trong nhiều năm mà không có quy trình cập nhật security fixes.

## 16. Bài tập thực hành

### Bài 1 — Xem protocol mặc định

Chạy chương trình `TlsProtocolInfo` trên JDK 17. So sánh supported protocols với default enabled protocols. Giải thích vì sao supported không đồng nghĩa với được phép dùng theo security policy.

### Bài 2 — Kiểm tra certificate

Dùng `keytool -printcert -file` đọc một certificate. Ghi lại Subject, Issuer, validity, SAN, Key Usage, Extended Key Usage, key size và signature algorithm.

### Bài 3 — Phân biệt truststore và keystore

Tạo một PKCS12 keystore cho server thử nghiệm và một truststore riêng. Giải thích private key nằm ở đâu, CA certificate nằm ở đâu và vì sao hai kho có mục đích khác nhau.

### Bài 4 — Tạo CSR

Tạo key pair, sau đó dùng `keytool -certreq` tạo CSR với SAN. Quan sát nội dung CSR và giải thích vì sao private key không được gửi cho CA.

### Bài 5 — Kiểm tra SAN

Tạo hai hostname test, một hostname có trong SAN và một hostname không có. Kết nối bằng HTTPS client và quan sát kết quả hostname verification.

### Bài 6 — Thử mTLS

Tạo client certificate được CA test ký, cấu hình server yêu cầu client authentication và cấu hình client dùng keystore. Kiểm tra handshake khi có và khi thiếu client certificate.

### Bài 7 — Đọc disabled algorithm policy

Mở `JAVA_HOME/conf/security/java.security`, tìm `jdk.tls.disabledAlgorithms` và `jdk.certpath.disabledAlgorithms`. Ghi lại những nhóm protocol/algorithm bị hạn chế trong bản JDK đang dùng và giải thích vì sao không nên xóa chúng tùy tiện.

### Bài 8 — Điều tra handshake

Tạo một lỗi có kiểm soát như truststore thiếu CA hoặc hostname không khớp. Bật `javax.net.debug` trong môi trường test, xác định bước handshake thất bại và sửa đúng certificate/trust configuration.

## 17. Nguyên tắc cần nhớ

- Java 17 hỗ trợ TLS 1.2 và TLS 1.3; tập protocol/algorithm thực tế chịu ảnh hưởng của provider, bản cập nhật và security policy.
- TLS protocol, cipher suite, certificate path và hostname verification là các phần khác nhau của kết nối an toàn.
- Truststore xác định CA được tin; keystore giữ private key và certificate identity của ứng dụng.
- Certificate chain phải dẫn đến trust anchor được chấp nhận; server cần gửi intermediate certificate cần thiết.
- Dùng SAN đúng hostname/IP, kiểm tra validity, EKU, Key Usage, key size và signature algorithm.
- Dùng `keytool` để xem, tạo CSR, import certificate và kiểm tra keystore/truststore; xác minh fingerprint qua kênh đáng tin.
- Dùng `SSLContext`, `SSLParameters`, `KeyManagerFactory` và `TrustManagerFactory` cho cấu hình JSSE.
- Với HTTPS, không tắt hostname verification; với mTLS, xác thực certificate vẫn cần authorization ở tầng ứng dụng.
- `jdk.tls.disabledAlgorithms` và `jdk.certpath.disabledAlgorithms` là một phần của baseline bảo mật; không xóa ràng buộc để hỗ trợ endpoint lỗi thời.
- JDK 17 đã dùng unlimited cryptographic policy mặc định; không áp dụng hướng dẫn policy file cũ.
- Bật TLS debug có kiểm soát, giới hạn log và tắt sau khi điều tra.
- Lập quy trình gia hạn certificate, cập nhật truststore và luân chuyển private key.

Khi nâng lên Java 17, hãy xác minh kết nối dựa trên protocol hiện hành, certificate chain, hostname và trust policy thực tế. Quản lý keystore/truststore có chủ đích, giữ nguyên các thuật toán an toàn mặc định và kiểm thử cả trường hợp handshake thành công lẫn thất bại sẽ giúp ứng dụng duy trì kết nối TLS ổn định mà không làm suy yếu bảo mật.
