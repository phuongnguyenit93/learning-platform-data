# Keystore trong Java và cách quản lý bằng keytool

## 1. Keystore là gì?

**Keystore** là kho lưu trữ bảo mật do Java Security API quản lý. Nó chứa các entry liên quan đến khóa và chứng thư số, được truy cập thông qua lớp **java.security.KeyStore** và công cụ dòng lệnh **keytool**.

Keystore thường được dùng để:

- Lưu private key cùng certificate chain của ứng dụng hoặc máy chủ.
- Lưu trusted certificate để xác minh danh tính bên ngoài.
- Lưu secret key đối xứng cho một số ứng dụng.
- Cung cấp key material cho TLS/SSL, chữ ký số và một số cơ chế bảo mật khác.

Một file keystore thường có phần mở rộng .p12, .pfx hoặc .jks, nhưng phần mở rộng không quyết định định dạng thật. Loại keystore được xác định bởi **store type** và security provider.

Keystore không tự thực hiện TLS, mã hóa dữ liệu hay xác minh chứng thư. Nó cung cấp nơi lưu trữ khóa/chứng thư; ứng dụng hoặc thư viện bảo mật sử dụng các entry đó để thực hiện thao tác tương ứng.

## 2. Các loại entry trong keystore

Một keystore có thể chứa nhiều entry. Mỗi entry được định danh bằng một **alias**.

| Entry type | Nội dung | Mục đích thường gặp |
|---|---|---|
| PrivateKeyEntry | Private key và certificate chain tương ứng. | Danh tính của server/client, ký số. |
| TrustedCertEntry | Một trusted certificate, không chứa private key. | Trust anchor hoặc chứng thư được ứng dụng tin cậy. |
| SecretKeyEntry | Secret key đối xứng như AES. | Mã hóa/giải mã dữ liệu đối xứng. |

Một PrivateKeyEntry thường chứa private key cần được bảo vệ, certificate của public key tương ứng và certificate trung gian trong chain nếu có.

Private key không được xuất ra khi dùng lệnh export certificate thông thường. **keytool -exportcert** chỉ xuất chứng thư chứa public key và thông tin xác thực; nó không xuất private key.

Một TrustedCertEntry chỉ chứa chứng thư được người quản trị hoặc ứng dụng quyết định tin cậy. Khi import một CA root certificate vào truststore, keytool thường tạo entry loại này.

Alias giúp chọn entry khi dùng keytool hoặc Java API. Nên đặt tên mô tả vai trò và môi trường, ví dụ server-prod, company-root-ca hoặc app-signing-key.

## 3. Phân biệt keystore và truststore

Trong Java TLS, hai khái niệm này mô tả hai vai trò khác nhau:

| Thành phần | Chứa gì? | Dùng để làm gì? |
|---|---|---|
| Keystore | Private key và certificate chain của chính ứng dụng. | Chứng minh danh tính khi ứng dụng đóng vai server hoặc client có mutual TLS. |
| Truststore | Các certificate mà ứng dụng chấp nhận làm điểm tin cậy. | Xác minh certificate chain của peer. |

Ví dụ khi chạy HTTPS server:

- Server keystore chứa private key và certificate của server.
- Client truststore chứa CA root hoặc certificate được dùng để xác minh server.

Với HTTPS client:

- Client thường cần truststore để xác minh certificate của server.
- Nếu server yêu cầu mutual TLS, client còn cần keystore chứa private key và certificate của client.

Keystore và truststore không phải hai định dạng file riêng. Cả hai có thể dùng PKCS12 hoặc JKS. Vai trò phụ thuộc vào cách ứng dụng nạp và sử dụng nội dung.

Có thể lưu cả identity và trusted certificates trong cùng một file, nhưng tách hai file thường dễ quản lý quyền truy cập, vòng đời và chính sách hơn.

## 4. Các định dạng keystore phổ biến

| Store type | Đặc điểm | Khi nào dùng |
|---|---|---|
| PKCS12 | Định dạng tiêu chuẩn, được hỗ trợ rộng rãi giữa các nền tảng và công cụ. | Lựa chọn mặc định phù hợp cho dự án Java hiện đại. |
| JKS | Định dạng keystore truyền thống của Java, mang tính riêng của hệ sinh thái Java. | Duy trì tương thích với hệ thống cũ. |
| JCEKS | Định dạng Java cũ hỗ trợ secret key entry. | Chỉ dùng khi cần tương thích với hệ thống/provider cũ. |
| PKCS11 | Truy cập khóa qua PKCS#11 provider, thường gắn với HSM hoặc smart card. | Khi private key phải được giữ trong thiết bị bảo mật. |

Từ JDK 9, **PKCS12 là default keystore type** trong cấu hình Java mặc định. Có thể kiểm tra bằng Java API:

~~~java
System.out.println(java.security.KeyStore.getDefaultType());
~~~

Với JDK 24.0.2, kết quả là:

~~~text
pkcs12
~~~

Dù có default, nên chỉ rõ **-storetype PKCS12** trong lệnh keytool và **KeyStore.getInstance("PKCS12")** trong ứng dụng. Cách này giúp build và runtime không phụ thuộc vào cấu hình mặc định của môi trường.

Không nên đổi đuôi file từ .jks sang .p12 để chuyển định dạng. Muốn chuyển thật sự, cần import/export entry bằng keytool hoặc công cụ tương ứng.

## 5. Kiểm tra keystore bằng keytool

keytool là công cụ quản lý khóa và chứng thư đi kèm JDK.

Xem phiên bản và danh sách lệnh:

~~~bash
keytool -version
keytool -help
~~~

Liệt kê entry trong một keystore:

~~~bash
keytool -list -keystore server.p12 -storetype PKCS12
~~~

keytool sẽ yêu cầu nhập store password nếu cần. Để xem chi tiết từng entry:

~~~bash
keytool -list -v -keystore server.p12 -storetype PKCS12
~~~

Output verbose có thể cho biết alias và ngày tạo entry, entry type, độ dài certificate chain, Subject/Issuer, serial number, thời hạn hiệu lực, signature algorithm, public key algorithm, certificate fingerprint và X.509 extension như Subject Alternative Name (SAN).

Kiểm tra đúng alias:

~~~bash
keytool -list -v -alias server -keystore server.p12 -storetype PKCS12
~~~

Đừng chỉ kiểm tra file có tồn tại. Hãy xác nhận alias, loại entry, certificate chain, thời hạn và fingerprint phù hợp với mục đích sử dụng.

## 6. Tạo keystore mới với cặp khóa và self-signed certificate

Để tạo private/public key pair và certificate tự ký, dùng **-genkeypair**.

Ví dụ cho môi trường development:

~~~bash
keytool -genkeypair \
    -alias server \
    -keyalg RSA \
    -keysize 2048 \
    -dname "CN=localhost, OU=Development, O=Example, C=VN" \
    -validity 365 \
    -ext "SAN=dns:localhost,ip:127.0.0.1" \
    -keystore server.p12 \
    -storetype PKCS12
~~~

keytool sẽ yêu cầu nhập và xác nhận password. Lệnh này tạo file server.p12, alias server, private key RSA và certificate tự ký có thời hạn 365 ngày.

Ý nghĩa các tùy chọn:

- **-genkeypair:** tạo public/private key pair và certificate.
- **-alias:** tên entry trong keystore.
- **-keyalg:** thuật toán tạo khóa, ví dụ RSA hoặc EC.
- **-keysize:** kích thước khóa, áp dụng cho thuật toán hỗ trợ tùy chọn này.
- **-dname:** Distinguished Name của certificate subject.
- **-validity:** thời hạn certificate tính theo ngày.
- **-ext SAN=...:** thêm Subject Alternative Name cho DNS/IP.
- **-keystore:** đường dẫn file keystore.
- **-storetype:** định dạng keystore.

Có thể dùng EC với group phù hợp chính sách bảo mật:

~~~bash
keytool -genkeypair \
    -alias server-ec \
    -keyalg EC \
    -groupname secp256r1 \
    -dname "CN=localhost, O=Example, C=VN" \
    -validity 365 \
    -ext "SAN=dns:localhost" \
    -keystore server-ec.p12 \
    -storetype PKCS12
~~~

Self-signed certificate phù hợp cho thử nghiệm hoặc môi trường được kiểm soát. Nó không tự động được trình duyệt, hệ điều hành hay client khác tin cậy. Với dịch vụ production, thông thường cần certificate được cấp bởi CA phù hợp với chính sách tổ chức.

## 7. Vì sao Subject Alternative Name quan trọng?

Certificate TLS cần xác định hostname hoặc IP mà nó đại diện. Trường **Subject Alternative Name (SAN)** lưu tên DNS hoặc địa chỉ IP được chứng thư bảo vệ.

Ví dụ:

~~~bash
-ext "SAN=dns:api.example.com,dns:www.example.com,ip:192.0.2.10"
~~~

Có thể thêm SAN khi tạo key pair hoặc khi tạo certificate request.

Không nên chỉ dựa vào Common Name (CN) để xác minh hostname. Client TLS hiện đại dựa vào SAN cho kiểm tra danh tính máy chủ. Nếu ứng dụng kết nối bằng IP, certificate cần có SAN dạng IP tương ứng; SAN DNS không thay thế SAN IP.

Kiểm tra SAN trong certificate:

~~~bash
keytool -list -v -alias server -keystore server.p12 -storetype PKCS12
~~~

Trong output, tìm phần SubjectAlternativeName. Hãy đảm bảo mọi hostname mà ứng dụng thực sự dùng đều có trong certificate.

## 8. Tạo Certificate Signing Request (CSR)

Trong môi trường production, thường tạo key pair trước rồi gửi **Certificate Signing Request (CSR)** tới CA để xin certificate.

Tạo CSR từ alias đã có:

~~~bash
keytool -certreq \
    -alias server \
    -keystore server.p12 \
    -storetype PKCS12 \
    -file server.csr \
    -ext "SAN=dns:api.example.com,dns:www.example.com"
~~~

CSR chứa thông tin subject, public key và chữ ký tạo bằng private key tương ứng. Private key vẫn ở trong keystore và không được gửi cho CA.

Xem nội dung CSR:

~~~bash
keytool -printcertreq -file server.csr
~~~

Sau khi CA xác thực yêu cầu, CA trả về certificate của server và có thể kèm intermediate certificate chain.

Import certificate reply vào đúng alias đã tạo CSR:

~~~bash
keytool -importcert \
    -alias server \
    -file server-chain.pem \
    -keystore server.p12 \
    -storetype PKCS12
~~~

Khi alias đã là PrivateKeyEntry, keytool xử lý file certificate reply và ghép chain với private key tương ứng. Nếu alias chưa có private key, import certificate thường tạo TrustedCertEntry thay vì identity có private key.

Certificate reply phải khớp public key trong CSR và chain phải được xây dựng hợp lệ. Nếu import sai alias hoặc sai certificate, keytool có thể từ chối hoặc không tạo được chain mong muốn.

## 9. Import CA certificate vào truststore

Để ứng dụng tin cậy certificate do CA phát hành, thường thêm CA root hoặc trust anchor được tổ chức phê duyệt vào truststore.

Trước khi import, xem certificate:

~~~bash
keytool -printcert -file company-root.pem
~~~

Kiểm tra fingerprint SHA-256 qua một kênh đáng tin cậy khác, ví dụ tài liệu PKI chính thức hoặc người quản trị CA. Không nên tin một certificate chỉ vì file được gửi kèm email hoặc tải từ một URL không xác thực.

Import vào truststore riêng của ứng dụng:

~~~bash
keytool -importcert \
    -alias company-root-ca \
    -file company-root.pem \
    -keystore app-truststore.p12 \
    -storetype PKCS12
~~~

keytool hiển thị thông tin certificate và hỏi có tin cậy hay không. Chỉ xác nhận sau khi đã kiểm tra fingerprint và nguồn cấp phát.

Kiểm tra truststore sau khi import:

~~~bash
keytool -list -v \
    -keystore app-truststore.p12 \
    -storetype PKCS12
~~~

Entry vừa import thường có type TrustedCertEntry. Đối với truststore production, nên quản lý rõ CA nào được tin cậy, mục đích sử dụng và ngày hết hạn.

Tránh dùng **-noprompt** trong quy trình import certificate chưa được xác minh. Tùy chọn này bỏ bước xác nhận tương tác và chỉ phù hợp khi pipeline đã kiểm tra fingerprint bằng một cơ chế đáng tin cậy.

## 10. Export và kiểm tra certificate

Để xuất certificate từ một alias:

~~~bash
keytool -exportcert \
    -alias server \
    -keystore server.p12 \
    -storetype PKCS12 \
    -file server.der
~~~

Mặc định output là dạng binary DER. Thêm **-rfc** để xuất dạng PEM/Base64:

~~~bash
keytool -exportcert \
    -rfc \
    -alias server \
    -keystore server.p12 \
    -storetype PKCS12 \
    -file server.pem
~~~

In thông tin certificate đã xuất:

~~~bash
keytool -printcert -file server.pem
~~~

Có thể dùng -list -v để xem fingerprint trực tiếp từ keystore và so sánh với file certificate đã export.

Export certificate không làm lộ private key. Nếu cần chuyển identity sang một keystore khác, dùng quy trình importkeystore có bảo vệ password và kiểm tra kết quả, không chỉ copy certificate public.

## 11. Tạo SecretKeyEntry bằng keytool

Ngoài key pair bất đối xứng, keystore còn có thể chứa secret key đối xứng.

Ví dụ tạo AES key:

~~~bash
keytool -genseckey \
    -alias app-aes \
    -keyalg AES \
    -keysize 256 \
    -keystore secrets.p12 \
    -storetype PKCS12
~~~

Liệt kê entry:

~~~bash
keytool -list -v -keystore secrets.p12 -storetype PKCS12
~~~

Output sẽ hiển thị entry type SecretKeyEntry. Khả năng thuật toán và kích thước khóa phụ thuộc security provider, chính sách mật mã và JDK đang dùng.

Trong ứng dụng, lấy secret key qua KeyStore API và dùng với JCA Cipher phù hợp. Không in key ra log, không đưa key vào source code và không gửi key qua kênh không an toàn.

Không dùng cùng một key cho nhiều mục đích mật mã khác nhau. Thiết kế quản lý key cần quy định thuật toán, mode, IV/nonce, rotation và cách lưu trữ dữ liệu đã mã hóa.

## 12. Chuyển keystore JKS sang PKCS12

Nếu dự án còn dùng JKS, có thể chuyển entry bằng **-importkeystore**.

Ví dụ:

~~~bash
keytool -importkeystore \
    -srckeystore legacy.jks \
    -srcstoretype JKS \
    -destkeystore migrated.p12 \
    -deststoretype PKCS12
~~~

keytool yêu cầu password của keystore nguồn và đích. Có thể nhập toàn bộ entry hoặc chọn alias cụ thể bằng -srcalias và -destalias.

Sau khi chuyển, kiểm tra cả hai file:

~~~bash
keytool -list -v -keystore legacy.jks -storetype JKS
keytool -list -v -keystore migrated.p12 -storetype PKCS12
~~~

So sánh số lượng alias, entry type, certificate fingerprint và chain length, khả năng truy xuất private key và việc ứng dụng có thể nạp file mới bằng store type mới.

Không xóa keystore cũ ngay sau khi chuyển. Giữ backup an toàn cho tới khi ứng dụng và quy trình triển khai đã xác nhận file PKCS12 hoạt động đúng.

## 13. Quản lý alias, entry và password

Một số lệnh bảo trì thường dùng:

Xóa entry:

~~~bash
keytool -delete -alias old-entry -keystore app.p12 -storetype PKCS12
~~~

Đổi alias:

~~~bash
keytool -changealias \
    -alias old-name \
    -destalias new-name \
    -keystore app.p12 \
    -storetype PKCS12
~~~

Đổi store password:

~~~bash
keytool -storepasswd -keystore app.p12 -storetype PKCS12
~~~

Đổi password bảo vệ private key entry:

~~~bash
keytool -keypasswd \
    -alias server \
    -keystore app.p12 \
    -storetype PKCS12
~~~

Các lệnh không cung cấp password trên command line sẽ yêu cầu nhập tương tác. Hành vi password riêng của entry phụ thuộc store type và provider; PKCS12 thường dùng cùng password cho store và private key entry trong cấu hình Java thông dụng. Hãy kiểm tra tương thích trước khi tự động hóa việc đổi password hoặc chuyển định dạng.

Không đặt password thật trực tiếp trong script được commit, command history hoặc log CI. Khi automation cần password, hãy lấy từ secret manager hoặc cơ chế cấp phát bảo mật của nền tảng build, hạn chế quyền đọc và không in giá trị ra log.

## 14. Đọc keystore bằng Java KeyStore API

Ứng dụng Java có thể nạp keystore bằng lớp **java.security.KeyStore**.

Ví dụ hoàn chỉnh **InspectStore.java**:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;

public class InspectStore {
    public static void main(String[] args) throws Exception {
        char[] password =
                System.getenv("STORE_PASSWORD").toCharArray();

        KeyStore store = KeyStore.getInstance("PKCS12");

        try (InputStream input =
                     Files.newInputStream(Path.of(args[0]))) {
            store.load(input, password);
        }

        String alias = "server";

        System.out.println("type=" + store.getType());
        System.out.println("contains server=" +
                store.containsAlias(alias));
        System.out.println("private key entry=" +
                store.isKeyEntry(alias));
        System.out.println("certificate entry=" +
                store.isCertificateEntry(alias));
        System.out.println("certificate present=" +
                (store.getCertificate(alias) != null));
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -encoding UTF-8 InspectStore.java
~~~

Chương trình nhận đường dẫn keystore qua tham số đầu tiên và password qua biến môi trường STORE_PASSWORD. Hãy cấp biến này từ secret manager hoặc môi trường chạy an toàn, không ghi password thật vào source hoặc shell history.

Với keystore thử nghiệm có alias server là PrivateKeyEntry, stdout của chương trình:

~~~text
type=PKCS12
contains server=true
private key entry=true
certificate entry=false
certificate present=true
~~~

Chương trình dùng KeyStore API thay vì tự đọc cấu trúc file. Không nên parse trực tiếp byte của file JKS/PKCS12 để lấy private key; hãy dùng API và security provider phù hợp.

## 15. Dùng keystore và truststore để cấu hình TLS

Trong Java Secure Socket Extension (JSSE), hai factory thường dùng là:

- **KeyManagerFactory:** tạo KeyManager từ keystore chứa identity/private key.
- **TrustManagerFactory:** tạo TrustManager từ truststore chứa trusted certificate.

Ví dụ khởi tạo SSLContext:

~~~java
KeyStore identityStore = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("server.p12"))) {
    identityStore.load(in, identityPassword);
}

KeyStore trustStore = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("truststore.p12"))) {
    trustStore.load(in, trustPassword);
}

KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(identityStore, identityPassword);

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(
        kmf.getKeyManagers(),
        tmf.getTrustManagers(),
        new java.security.SecureRandom());
~~~

Đây là phần cấu hình TLS có thể nhúng vào ứng dụng đã có password và xử lý resource phù hợp. Với server TLS, KeyManager cung cấp certificate/private key của server. Với client TLS, TrustManager xác minh certificate chain của server. Mutual TLS có thể cần cả hai phía cung cấp identity và xác minh peer.

Nếu chỉ cần client truststore:

~~~java
TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);

SSLContext context = SSLContext.getInstance("TLS");
context.init(null, tmf.getTrustManagers(), null);
~~~

Không tắt hostname verification để xử lý lỗi certificate. Nếu hostname không khớp, hãy cấp certificate có SAN đúng hoặc sửa endpoint mà client kết nối.

## 16. Keystore mặc định cacerts

JDK thường đi kèm truststore mặc định tên **cacerts**, chứa các CA certificate mà runtime tin cậy theo cấu hình của distribution.

Liệt kê certificate trong cacerts:

~~~bash
keytool -list -cacerts
~~~

Có thể xem chi tiết:

~~~bash
keytool -list -v -cacerts
~~~

cacerts nằm trong cây thư mục bảo mật của Java runtime. Vị trí cụ thể phụ thuộc cách cài đặt JDK/JRE và nền tảng.

Không nên sửa trực tiếp cacerts của JDK dùng chung chỉ để ứng dụng riêng tin cậy một CA. Việc cập nhật runtime có thể thay thế file này và thay đổi trust policy của nhiều ứng dụng.

Với ứng dụng cần CA riêng, thường tạo truststore riêng rồi cấu hình ứng dụng dùng file đó. Điều này giúp cập nhật trust anchor mà không ảnh hưởng các ứng dụng khác.

## 17. Password, backup và bảo vệ private key

Keystore chỉ an toàn khi file, password và quyền truy cập được quản lý đúng.

Một số nguyên tắc:

- Giới hạn quyền đọc file keystore cho đúng service account.
- Bảo vệ private key bằng password mạnh và secret manager.
- Không commit keystore production hoặc password vào Git.
- Không đưa password vào log, exception message hoặc telemetry.
- Không gửi keystore qua email/chat hoặc kho lưu trữ không mã hóa.
- Mã hóa và kiểm soát quyền truy cập bản backup.
- Kiểm tra backup có thể khôi phục trước khi cần dùng.
- Lập kế hoạch rotation key và gia hạn certificate.
- Thu hồi certificate khi private key bị lộ hoặc không còn được phép sử dụng.

Mất private key có thể khiến ứng dụng không thể tiếp tục dùng certificate hiện tại và phải tạo key pair/certificate mới. Backup phải được bảo vệ tương đương file gốc; không để bản sao nằm ở thư mục tạm hoặc máy cá nhân không được kiểm soát.

Password của keystore không thay thế quyền truy cập file ở hệ điều hành. Người có thể đọc file và biết password có thể sử dụng private key theo quyền mà ứng dụng cho phép.

Với hệ thống có yêu cầu bảo mật cao, cân nhắc HSM hoặc PKCS#11 token để private key không phải xuất ra file thông thường. Quản lý khóa phần cứng cần quy trình cấp phát, backup/recovery và quyền truy cập riêng.

## 18. Lỗi thường gặp khi dùng keystore

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Keystore was tampered with, or password was incorrect | Sai store password, file hỏng hoặc sai store type/provider. | Kiểm tra password, backup và store type. |
| Alias does not exist | Chọn sai alias hoặc import nhầm file. | Dùng keytool -list -v để kiểm tra alias. |
| TrustedCertEntry được tạo thay vì PrivateKeyEntry | Import certificate vào alias mới không có private key. | Tạo key pair/CSR trước rồi import certificate reply vào đúng alias. |
| Certificate reply does not contain public key for alias | Certificate không khớp private key đã tạo CSR hoặc sai alias. | Kiểm tra CSR, alias và certificate CA trả về. |
| Certificate chain không được xây dựng | Thiếu intermediate CA hoặc chain không hợp lệ. | Nhận đủ certificate chain và import theo đúng alias. |
| Hostname verification failed | SAN không chứa hostname/IP mà client đang kết nối. | Cấp certificate có SAN đúng. |
| PKIX path building failed | Truststore thiếu CA phù hợp hoặc chain không được tin cậy. | Kiểm tra chain, trust anchor và truststore đang được ứng dụng sử dụng. |
| Keystore type không được hỗ trợ | Runtime/provider không hỗ trợ store type được chọn. | Chọn PKCS12/JKS tương thích hoặc cài provider đúng. |
| Private key password incorrect | Dùng sai password của entry hoặc định dạng không hỗ trợ cấu hình password dự kiến. | Kiểm tra store type và password entry. |
| Ứng dụng không thấy certificate mới | Ứng dụng giữ SSLContext/KeyStore đã nạp trước đó. | Reload material theo vòng đời ứng dụng hoặc restart có kiểm soát. |
| Import nhầm CA không đáng tin | Không xác minh fingerprint trước khi import. | Gỡ entry sai và xác minh certificate qua kênh độc lập. |

Không nên giải quyết lỗi TLS bằng cách tắt kiểm tra certificate hoặc hostname. Trước tiên hãy xác định file keystore/truststore, alias, chain, SAN và trust manager mà ứng dụng thực sự đang dùng.

## 19. Quy trình quản lý keystore trong dự án

Một quy trình vận hành có thể gồm:

1. Xác định vai trò của file: identity keystore, truststore hay secret-key store.
2. Chọn PKCS12 trừ khi có yêu cầu tương thích cụ thể với định dạng khác.
3. Tạo key pair và đặt alias rõ ràng.
4. Thêm SAN phù hợp với hostname/IP của dịch vụ.
5. Với production, tạo CSR và gửi CA; giữ private key trong keystore.
6. Nhận certificate reply và import vào đúng alias.
7. Import CA root đã xác minh vào truststore riêng khi cần.
8. Kiểm tra entry, fingerprint, chain, thời hạn và thuật toán bằng keytool -list -v.
9. Nạp file bằng KeyStore API và cấu hình KeyManagerFactory/TrustManagerFactory.
10. Bảo vệ password, quyền file, backup và quy trình rotation.
11. Kiểm thử TLS trên môi trường mục tiêu và xác nhận hostname verification.
12. Theo dõi ngày hết hạn certificate và lịch cập nhật CA trust.

Nên ghi nhận metadata không bí mật như alias, subject, issuer, fingerprint, ngày hết hạn, loại store và owner. Không ghi private key hoặc password vào tài liệu vận hành.

## 20. Checklist trước khi triển khai

- [ ] Đã xác định keystore dùng để lưu identity, trust anchor hay secret key.
- [ ] Đã chọn store type phù hợp, ưu tiên PKCS12 khi không có ràng buộc cũ.
- [ ] Đã dùng alias mô tả rõ vai trò và môi trường.
- [ ] Đã kiểm tra entry type và certificate chain.
- [ ] Đã kiểm tra SAN khớp DNS/IP thực tế.
- [ ] Đã xác minh certificate fingerprint qua kênh đáng tin cậy.
- [ ] Đã import certificate reply vào đúng private-key alias.
- [ ] Đã kiểm tra truststore có đúng CA cần thiết.
- [ ] Đã kiểm thử Java KeyStore API và TLS context.
- [ ] Đã bảo vệ password, file, backup và quyền truy cập.
- [ ] Đã có quy trình gia hạn, rotation và thu hồi certificate.
- [ ] Đã xác nhận không tắt certificate hoặc hostname verification.

Keystore cung cấp nơi quản lý private key, secret key và certificate cho ứng dụng Java. Khi chọn đúng store type, quản lý alias và certificate chain rõ ràng, tách identity khỏi trust khi phù hợp và bảo vệ password/private key, ứng dụng có thể dùng TLS và các cơ chế bảo mật Java một cách an toàn, dễ vận hành.