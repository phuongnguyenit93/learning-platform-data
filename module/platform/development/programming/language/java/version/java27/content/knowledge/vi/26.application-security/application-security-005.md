# KeyStore, chứng thư, TLS và xác minh danh tính máy chủ

Trong ứng dụng Java 27, **HTTPS/TLS** giúp bảo vệ kết nối mạng trước hành vi nghe lén và can thiệp dữ liệu. Nhưng mã hóa đường truyền **chỉ có ý nghĩa khi ứng dụng thật sự kết nối đến đúng máy chủ đáng tin cậy**. Nếu một chương trình chấp nhận mọi chứng thư hoặc bỏ qua kiểm tra tên máy chủ để làm cho kết nối “hết lỗi SSL”, nó có thể trao dữ liệu nhạy cảm cho bên giả mạo.

Bài này thuộc chương **Bảo mật ứng dụng Java**, trình bày cách Java quản lý khóa và chứng thư qua **KeyStore**, thiết lập mối tin cậy qua **TrustManager**, triển khai TLS qua **JSSE** và xác minh danh tính endpoint qua HTTPS. Ví dụ dùng API chính thức còn áp dụng trong Java 27; không sử dụng cách cấu hình cũ yếu bảo mật hoặc thao tác vô hiệu hóa xác minh chứng thư.

Sau bài học, bạn có thể:

- Phân biệt private key, public key, chứng thư X.509, CA, trust anchor, certificate chain.
- Phân biệt *keystore chứa danh tính* và *truststore chứa căn cứ tin cậy*.
- Sử dụng **PKCS12** và **keytool** để tạo, kiểm tra, xuất, nhập chứng thư phục vụ môi trường thực hành.
- Hiểu quá trình xác thực máy chủ, bao gồm chuỗi chứng thư và **Subject Alternative Name (SAN)**.
- Dùng **HttpClient** với **SSLContext** và **TrustManagerFactory** mà vẫn giữ hostname verification.
- Cấu hình **KeyManagerFactory** khi cần trình bày chứng thư client trong **mTLS**.
- Hiểu khác biệt giữa HTTPS client cấp cao và **SSLSocket/SSLEngine** cấp thấp.
- Phân loại lỗi TLS, áp dụng các bước khắc phục an toàn và kiểm thử kết nối.

## 1. TLS bảo vệ những gì?

TLS (*Transport Layer Security*) là giao thức tạo kênh truyền được bảo vệ giữa hai đầu kết nối. Trong HTTPS, HTTP chạy phía trên TLS.

Ba mục tiêu chính:

| Mục tiêu | Diễn giải | Điều kiện |
|---|---|---|
| **Bí mật** (*confidentiality*) | Bên không có khóa phiên không đọc được dữ liệu đang truyền | Thuật toán và tham số TLS được cấu hình an toàn |
| **Toàn vẹn** (*integrity*) | Can thiệp làm thay đổi thông điệp được phát hiện | Cơ chế bảo vệ tính xác thực/toàn vẹn bản ghi |
| **Xác thực đối tác** (*authentication*) | Client có bằng chứng rằng endpoint đáp ứng danh tính mong đợi | **Chứng thư đáng tin** và **hostname phù hợp** |

TLS **không** tự quyết định một người dùng có quyền xem hóa đơn nào. Xác thực người dùng và phân quyền nghiệp vụ vẫn cần được giải quyết ở tầng ứng dụng.

TLS cũng không đảm bảo dữ liệu không bị lộ tại chính máy client/server, trong log, bộ nhớ, cơ sở dữ liệu hay một reverse proxy đã được cho phép giải mã kết nối.

### 1.1. Hình dung luồng HTTPS

~~~mermaid
flowchart LR
    C["Java HttpClient"] --> H["TLS handshake"]
    H --> V["Kiểm tra chuỗi chứng thư"]
    V --> N["Kiểm tra hostname / SAN"]
    N --> K["Xác lập khóa phiên an toàn"]
    K --> A["Gửi HTTP trong kênh TLS"]
    A --> S["HTTPS server"]
~~~

Trình tự trong thực tế có thể đan xen các bước của giao thức TLS 1.3; sơ đồ mô tả **các trách nhiệm bảo mật**, không phải toàn bộ thông điệp wire-level.

## 2. Phân biệt khóa, chứng thư và CA

### 2.1. Khóa bất đối xứng

Một cặp khóa bao gồm:

- **Private key**: bí mật; chủ thể phải bảo vệ và không gửi ra ngoài chỉ để chứng minh danh tính.
- **Public key**: có thể công bố; dùng trong các cơ chế xác minh chữ ký hoặc thỏa thuận bảo mật tương ứng.

Đối tác không nên chỉ tin public key vì ai đó tự gửi tới. Nó cần cách xác minh public key đó thuộc về chủ thể mong đợi.

### 2.2. Chứng thư X.509

Một **X.509 certificate** liên kết public key với thông tin về chủ thể, bên phát hành và các ràng buộc sử dụng. Chứng thư thường mang:

| Trường/extension | Ý nghĩa |
|---|---|
| **Subject** | Danh tính mô tả chủ thể của chứng thư |
| **Issuer** | Bên phát hành/ký chứng thư |
| **Validity (Not Before / Not After)** | Khoảng thời gian chứng thư có hiệu lực |
| **Subject Public Key Info** | Public key và thuật toán liên quan |
| **Subject Alternative Name (SAN)** | Tên DNS/IP mà chứng thư đại diện |
| **Basic Constraints** | Thông tin chứng thư có thể là CA hay không |
| **Key Usage / Extended Key Usage** | Các mục đích sử dụng khóa, ví dụ **serverAuth** |
| **Signature Algorithm** | Thuật toán dùng để ký chứng thư |

Chứng thư **không chứa private key**. Một file **.pem/.crt/.cer** chỉ chứa chứng thư công khai không phải là file có private key tương ứng.

### 2.3. CA và certificate chain

Trong mô hình PKI thông thường:

~~~text
Root CA (trust anchor được cấu hình tin cậy)
    |
    v
Intermediate CA (chứng thư CA trung gian)
    |
    v
Server certificate (leaf/end-entity)
    |
    v
Máy chủ chứng minh sở hữu private key tương ứng
~~~

Máy chủ thường gửi **leaf** và các **intermediate** cần thiết; root CA **không bắt buộc** phải xuất hiện trong chuỗi gửi qua mạng. Bên client xác thực đường dẫn chứng thư đến một **trust anchor** mà nó đã chấp nhận trước.

Một chứng thư tự ký (*self-signed*) không tự trở thành đáng tin chỉ vì chữ ký của nó hợp lệ. Để dùng trong môi trường thực hành kín, client phải tin chứng thư/CA đó một cách **có chủ đích và đã xác minh**.

## 3. Trust và hostname là hai phép kiểm tra độc lập

Khi client kết nối đến:

~~~text
https://api.example.com/orders
~~~

Nó cần trả lời hai câu hỏi riêng:

1. **Có tin chuỗi chứng thư này không?** Đường dẫn xác thực tới một CA/trust anchor được chấp nhận, chứng thư còn hiệu lực và đáp ứng các ràng buộc liên quan hay không?
2. **Chứng thư có đại diện cho api.example.com không?** Danh tính endpoint được kiểm tra theo tên host trong URL và thông tin định danh phù hợp trên chứng thư hay không?

Có thể xảy ra:

| Chuỗi chứng thư | Hostname | Kết quả phù hợp |
|---|---|---|
| Đáng tin | Khớp | Có thể thiết lập TLS nếu các kiểm tra khác đạt |
| Đáng tin | **Không khớp** | **Từ chối** |
| **Không đáng tin** | Khớp | **Từ chối** |
| **Không đáng tin** | Không khớp | **Từ chối** |

Ví dụ chứng thư hợp lệ cho **payments.example.com** không phải chứng thư hợp lệ cho **api.example.com** chỉ vì cả hai cùng được một public CA cấp.

**Nhập CA vào truststore không sửa được lỗi hostname mismatch.** Cách giải quyết đúng là cấp/sử dụng chứng thư có SAN phù hợp, hoặc kết nối bằng một hostname thực sự có trong danh tính được chứng thư cấp phép.

## 4. SAN, DNS, IP, CN và SNI

### 4.1. Subject Alternative Name

Một chứng thư HTTPS hiện đại nên có extension **SAN** với các tên được hệ thống truy cập thực tế.

Ví dụ cấu hình hợp lệ về mặt ý nghĩa:

~~~text
DNS:api.internal.example
DNS:api-backup.internal.example
IP:192.0.2.10
~~~

Nếu client truy cập bằng hostname **api.internal.example**, certificate phải có danh tính DNS phù hợp.

Nếu truy cập theo địa chỉ IP, chứng thư cần có **iPAddress SAN** phù hợp, không nên cho rằng một DNS SAN hoặc trường **CN** là đủ. Địa chỉ **192.0.2.10** ở ví dụ thuộc dải dành cho tài liệu, không phải một máy chủ cần truy cập.

Với tên miền quốc tế hoặc wildcard, có các quy tắc chuẩn riêng; không tự viết phép so sánh **String.contains()**, regex tùy ý hoặc “trùng đuôi domain là đạt”. Hãy để TLS/HTTPS implementation kiểm tra tên theo tiêu chuẩn.

### 4.2. CN không thay thế SAN

**Common Name (CN)** là một phần của Subject DN. Với chứng thư máy chủ mới, phải cấu hình **SAN** thích hợp cho hostname thực tế; không thiết kế chứng thư chỉ có **CN** rồi phụ thuộc vào khả năng fallback không nhất quán giữa các client/provider.

### 4.3. SNI khác hostname verification

**Server Name Indication (SNI)** cho phép client gửi tên máy chủ dự kiến trong quá trình thiết lập TLS để server có thể chọn chứng thư phù hợp khi phục vụ nhiều website trên một địa chỉ.

**SNI không phải kiểm tra danh tính.** Client vẫn phải xác minh chứng thư được trả về có đại diện cho hostname mà nó định kết nối hay không.

## 5. KeyStore là gì?

Trong Java, **java.security.KeyStore** cung cấp API lưu và truy cập một tập các mục liên quan đến khóa và chứng thư. Nó là một **abstraction**; việc lưu trên file, token phần cứng hay nhà cung cấp bảo mật khác tùy theo kiểu keystore và provider.

Các loại entry phổ biến:

| Loại entry | Nội dung | Ví dụ |
|---|---|---|
| **PrivateKeyEntry** | Private key và certificate chain tương ứng | Danh tính HTTPS server hoặc client mTLS |
| **TrustedCertificateEntry** | Chứng thư được lưu làm đầu vào cho quyết định trust | CA riêng được phép tin |
| **SecretKeyEntry** | Symmetric secret key | Một số nhu cầu lưu khóa bí mật khác TLS danh tính |

KeyStore còn có các method như **aliases()**, **containsAlias()**, **isKeyEntry()**, **isCertificateEntry()**, **getCertificate()** và **getCertificateChain()** để kiểm tra cấu trúc lưu trữ.

### 5.1. PKCS12 là lựa chọn hiện hành

Với JDK 27, **PKCS12** là định dạng keystore mặc định và được khuyến nghị trong tài liệu JCA hiện hành.

~~~java
import java.security.KeyStore;

System.out.println(KeyStore.getDefaultType());
KeyStore store = KeyStore.getInstance("PKCS12");
~~~

Trong cấu hình JDK tiêu chuẩn, **getDefaultType()** thông thường là **pkcs12**, nhưng mã không nên giả định giá trị này bất biến khi một môi trường đã thay đổi security property **keystore.type**.

**JKS** là định dạng độc quyền cũ; hướng dẫn Java 27 khuyến nghị chuyển sang **PKCS12** cho file keystore/truststore mới. Chỉ giữ JKS nếu một hệ thống tương thích cũ bắt buộc phải dùng và có kế hoạch chuyển đổi được kiểm soát.

Không nhầm:

- **PKCS12**: định dạng container cho key/certificate entries.
- **X.509**: định dạng/chính sách chứng thư công khai.
- **PEM**: cách biểu diễn dữ liệu được mã hóa Base64 có header/footer.
- **PKCS11**: giao diện tới token/HSM, không phải cùng định dạng file PKCS12.

## 6. Keystore danh tính và truststore

Trong JSSE, hai vai trò thường được nói đến như sau:

| Vai trò | Mục đích | Entry phổ biến | Ai sử dụng |
|---|---|---|---|
| **Identity keystore** | Cung cấp chứng thư **và private key** để chứng minh danh tính của chính mình | **PrivateKeyEntry** | **KeyManager** |
| **Truststore** | Cung cấp những căn cứ chứng thư/CA được phép tin để kiểm tra đối tác | **TrustedCertificateEntry** | **TrustManager** |

**Keystore** và **truststore** không phải hai lớp Java khác nhau. Cả hai thường được nạp bằng **KeyStore**, nhưng được truyền cho hai nhà máy quản lý có nhiệm vụ khác nhau.

~~~mermaid
flowchart LR
    K["Identity PKCS12: private key + certificate chain"] --> KM["KeyManagerFactory"]
    T["Trust PKCS12: CA / trusted certificates"] --> TM["TrustManagerFactory"]
    KM --> SSL["SSLContext"]
    TM --> SSL
    SSL --> C["TLS client hoặc server"]
~~~

### 6.1. Khi nào cần keystore phía client?

Với HTTPS **một chiều** thông thường:

- Server trình bày chứng thư và chứng minh nó có private key tương ứng.
- Client xác minh danh tính và độ tin cậy của server.
- Client **không bắt buộc** phải có chứng thư riêng.

Với **mutual TLS (mTLS)**:

- Server vẫn phải xác thực đối với client.
- Server yêu cầu client trình bày chứng thư.
- Client cần có private key/certificate chain phù hợp.
- Server phải có chính sách trust dành cho chứng thư client và kiểm tra quyền ứng dụng sau khi xác thực.

Không thêm client keystore vào mọi HttpClient nếu hệ thống không dùng mTLS.

## 7. Truststore mặc định của Java

Một Java HTTPS client bình thường thường **không cần tự cấu hình truststore** khi kết nối tới server có chứng thư hợp lệ được cấp bởi public CA mà JDK đã tin cậy.

Ví dụ:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

try (HttpClient client = HttpClient.newHttpClient()) {
    HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/"))
        .GET()
        .build();

    HttpResponse<Void> response = client.send(
        request, HttpResponse.BodyHandlers.discarding()
    );

    System.out.println(response.statusCode());
}
~~~

Trong môi trường có mạng, lệnh này dựa trên **SSLContext mặc định** của JDK và vẫn giữ các phép kiểm tra bảo mật chuẩn.

Trong SunJSSE, việc tìm truststore mặc định có thể dựa theo thứ tự:

1. File được chỉ định bởi system property **javax.net.ssl.trustStore** (nếu được cấu hình).
2. **java.home/lib/security/jssecacerts** nếu có.
3. **java.home/lib/security/cacerts** nếu có.

Cần chú ý:

- Nếu cấu hình **javax.net.ssl.trustStore** trỏ tới file **không tồn tại**, JSSE có thể dùng tập trust rỗng thay vì âm thầm quay lại **cacerts**.
- Truststore có thể khác nhau giữa các JDK, container image hoặc môi trường chạy.
- Không nên chỉnh sửa trực tiếp **cacerts** của JDK để giải quyết nhu cầu riêng của từng ứng dụng: nó làm khó quản lý cấu hình, nâng cấp và kiểm soát phạm vi trust.

Khi phải kết nối tới nội bộ dùng private CA, hãy quản lý truststore riêng của ứng dụng hoặc cơ chế trust tương đương được duyệt.

## 8. keytool trên Java 27

**keytool** là tiện ích chính thức của JDK để tạo khóa, CSR, kiểm tra, nhập và xuất chứng thư. Những thao tác sau chỉ là **lệnh mẫu cho người học**; chúng không được chạy trong quá trình soạn tài liệu này.

### 8.1. Kiểm tra một chứng thư nhận được

Giả sử tổ chức cung cấp file **company-ca.crt** chứa chứng thư CA.

~~~bash
keytool -printcert -file company-ca.crt
~~~

Quan sát thông tin:

- **SHA-256 fingerprint**
- Subject và Issuer.
- Thời hạn hiệu lực.
- Key Usage, Basic Constraints và các extension liên quan.

**Bước bắt buộc về tin cậy:** đối chiếu SHA-256 fingerprint với giá trị được tổ chức cung cấp qua **kênh xác thực độc lập**, không chỉ với chính email hoặc đường link có thể bị giả mạo.

Một chứng thư có thể parse được và “trông hợp lý” không đồng nghĩa nguồn phát hành đã được xác thực.

### 8.2. Tạo truststore PKCS12 riêng

Sau khi **đã xác minh** rằng chứng thư CA đúng là trust anchor mà ứng dụng được phép tin:

~~~bash
keytool -importcert -alias company-ca -file company-ca.crt -keystore app-trust.p12 -storetype PKCS12
~~~

**Không** dùng **-noprompt** trong quá trình tiếp nhận chứng thư chưa được kiểm chứng. Hãy đọc fingerprint được công cụ hiển thị, đối chiếu và chỉ xác nhận nhập khi chính xác.

Khi keytool yêu cầu password, nhập tương tác để tránh đặt bí mật trong shell history hoặc process arguments.

Kiểm tra nội dung sau khi nhập:

~~~bash
keytool -list -v -keystore app-trust.p12 -storetype PKCS12
~~~

Truststore này chỉ có các CA/certificates mà bạn đã nhập. **Nó không tự động gộp toàn bộ public roots của JDK**.

### 8.3. Tạo self-signed certificate chỉ cho môi trường thực hành

Để học TLS với máy chủ **localhost**, có thể tạo một chứng thư tự ký có SAN chính xác:

~~~bash
keytool -genkeypair -alias localhost -keyalg EC -groupname secp256r1 -sigalg SHA256withECDSA -validity 30 -dname "CN=localhost" -ext "SAN=DNS:localhost,IP:127.0.0.1" -ext "EKU=serverAuth" -keystore dev-server.p12 -storetype PKCS12
~~~

Lệnh tạo **dev-server.p12** chứa private key và chứng thư self-signed, dùng đúng cho mục đích **lab/test cục bộ**, không phải phương thức cấp chứng thư production.

Xuất **chứng thư công khai** (không xuất private key):

~~~bash
keytool -exportcert -rfc -alias localhost -keystore dev-server.p12 -storetype PKCS12 -file dev-server.crt
~~~

Kiểm tra chứng thư:

~~~bash
keytool -printcert -file dev-server.crt
~~~

Với lab này, nếu bạn đã xác minh file xuất ra từ đúng keystore vừa tạo và kiểm soát được vòng đời file, có thể nhập chứng thư này vào một truststore **riêng cho lab**:

~~~bash
keytool -importcert -alias dev-localhost -file dev-server.crt -keystore dev-trust.p12 -storetype PKCS12
~~~

Không sao chép truststore lab vào production. Không dùng việc tin một chứng thư tự ký tùy ý lấy trên mạng làm cách “sửa SSL”.

### 8.4. Kiểm tra alias và entry type

~~~bash
keytool -list -v -keystore dev-server.p12 -storetype PKCS12
keytool -list -v -keystore dev-trust.p12 -storetype PKCS12
~~~

Ở keystore server, mong đợi alias **localhost** là loại **PrivateKeyEntry** với certificate chain tương ứng.

Ở truststore lab, mong đợi alias **dev-localhost** là loại **trustedCertEntry**.

Nếu nhầm hai file, client có thể không tìm thấy trust anchor hoặc server không có private key để chứng minh danh tính.

## 9. Đọc PKCS12 KeyStore bằng Java

Ví dụ đọc tệp được bảo vệ bằng password:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;

static KeyStore loadPkcs12(
        Path path, char[] password
) throws Exception {
    KeyStore store = KeyStore.getInstance("PKCS12");

    try (InputStream input = Files.newInputStream(path)) {
        store.load(input, password);
    }

    return store;
}
~~~

**KeyStore.getInstance(...)** mới chỉ tạo abstraction; **load(...)** nạp nội dung tệp thực tế. Nếu cần tạo một keystore rỗng mới, Java cho phép **load(null, password)** theo quy tắc của implementation.

### 9.1. Đừng nhầm password với quyền truy cập

Password của PKCS12 giúp bảo vệ hoặc kiểm tra dữ liệu theo tính năng của provider/định dạng, nhưng còn cần:

- Phân quyền đọc/ghi file tại hệ điều hành và môi trường triển khai.
- Kho lưu bí mật thích hợp (secret manager, HSM/KMS khi phù hợp).
- Quản lý vòng đời và thay đổi khóa/chứng thư.
- Không ghi tệp **.p12** chứa private key vào repository hoặc artefact công khai.

### 9.2. char[] và quản lý bí mật

Trong ví dụ bảo mật, password được truyền bằng **char[]** để caller có thể xóa nội dung mảng sau khi dùng:

~~~java
char[] password = console.readPassword("Keystore password: ");

try {
    KeyStore store = loadPkcs12(path, password);
    // Sử dụng store theo yêu cầu.
} finally {
    java.util.Arrays.fill(password, '\0');
}
~~~

Đoạn này giả định **console != null**, **password != null** và **path** đã được xác định. Ở môi trường IDE hoặc service không có terminal, **System.console()** có thể trả **null**. Khi đó lấy secret từ cơ chế bảo mật của môi trường, không hard-code vào mã nguồn.

Việc xóa **char[]** giảm thời gian bí mật còn nằm trong mảng do ứng dụng sở hữu, nhưng **không bảo đảm** mọi bản sao tạm trong provider/heap đã bị xóa.

## 10. TrustManagerFactory và KeyManagerFactory

JSSE dùng các **manager** để tách hai trách nhiệm.

### 10.1. TrustManagerFactory

~~~java
import java.security.KeyStore;
import javax.net.ssl.TrustManagerFactory;

KeyStore trustedRoots = loadPkcs12(
    Path.of("app-trust.p12"), trustPassword
);

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
    TrustManagerFactory.getDefaultAlgorithm()
);

tmf.init(trustedRoots);
~~~

Sau đó **tmf.getTrustManagers()** cung cấp những manager kiểm tra chứng thư remote theo cấu hình.

Trong bản cài JDK SunJSSE, **PKIX** là thuật toán trust manager mặc định thông thường, nhưng việc dùng **getDefaultAlgorithm()** tránh hard-code provider-specific choice.

### 10.2. KeyManagerFactory

~~~java
import javax.net.ssl.KeyManagerFactory;

KeyStore identity = loadPkcs12(
    Path.of("client-identity.p12"), storePassword
);

KeyManagerFactory kmf = KeyManagerFactory.getInstance(
    KeyManagerFactory.getDefaultAlgorithm()
);

kmf.init(identity, privateKeyPassword);
~~~

**kmf.getKeyManagers()** hỗ trợ chọn private key và certificate chain mà endpoint của bạn trình bày khi cần xác thực.

**storePassword** và **privateKeyPassword** có thể bằng nhau trong một số keystore nhưng là hai khái niệm khác nhau; đừng giả định mọi hệ thống đều dùng cùng password.

### 10.3. Bảng tóm tắt

| Thành phần | Trách nhiệm | Thông tin nguồn |
|---|---|---|
| **KeyStore** | Nạp/lưu entries | PKCS12 file hoặc provider khác |
| **KeyManagerFactory** | Tạo KeyManager | Identity keystore |
| **TrustManagerFactory** | Tạo TrustManager | Truststore hoặc trust mặc định |
| **SSLContext** | Ghép key manager, trust manager, nguồn ngẫu nhiên cho TLS | JSSE configuration |
| **SSLParameters** | Thông số TLS từng connection, gồm endpoint identification | Socket/engine hoặc client config |
| **HttpClient** | Thực hiện HTTPS và quản lý HTTP request/response | SSLContext và chính sách HTTP |

## 11. SSLContext và cấu hình TLS an toàn

**javax.net.ssl.SSLContext** là nơi ghép thành phần xác thực và cấu hình thuật toán.

~~~java
import javax.net.ssl.SSLContext;

SSLContext context = SSLContext.getInstance("TLS");

context.init(
    null,
    tmf.getTrustManagers(),
    null
);
~~~

Trong ví dụ:

- Tham số **KeyManager[] = null**: không cung cấp client identity riêng; phù hợp với HTTPS một chiều.
- Tham số **TrustManager[]**: sử dụng truststore đã kiểm chứng.
- Tham số **SecureRandom = null**: dùng nguồn mặc định được provider chọn.

Tên **"TLS"** cho phép provider chọn những phiên bản được cấu hình và cho phép theo chính sách hiện hành. Không nên chỉ định **"SSL"**, **"SSLv3"**, **"TLSv1"** hoặc **"TLSv1.1"** để cố tương thích hệ thống cũ.

Trong Java SE 27, TLS 1.2 và TLS 1.3 là các phiên bản được hỗ trợ. **TLS 1.3** thường là ưu tiên nếu các endpoint và chính sách tương thích; **TLS 1.2** vẫn là lựa chọn hiện hành trong những hệ thống cần nó. Đừng tắt các security properties **jdk.tls.disabledAlgorithms** để bật lại cipher hoặc protocol yếu.

### 11.1. Không viết trust-all

Một triển khai TrustManager mà mọi **checkServerTrusted** đều trả về bình thường sẽ phá bỏ mục tiêu xác thực server của TLS.

**Không** dùng cách đó trong mã ứng dụng, kể cả khi một chứng thư self-signed khiến kết nối thất bại. Giải pháp đúng là xác minh và cấu hình trust anchor thích hợp **đồng thời giữ hostname verification**.

### 11.2. Không gộp truststore không kiểm soát

Khi khởi tạo **TrustManagerFactory** bằng một **KeyStore cụ thể**, bộ trust manager tạo ra dựa trên tập đó. Nó không tự động cộng thêm trust mặc định của JDK.

Nếu ứng dụng cần vừa tin public CA vừa tin một private CA:

1. Thiết kế tập trust anchors theo hợp đồng và chính sách bảo mật.
2. Tạo một truststore được quản lý chứa các CA được phép tin, hoặc dùng cơ chế composite trust manager được kiểm chứng.
3. Không mở rộng vô điều kiện để chấp nhận mọi certificate.
4. Viết kiểm thử cho cả public endpoint và private endpoint đúng nhu cầu.

## 12. Ví dụ đầy đủ: HTTPS client dùng truststore riêng

Tạo tệp **TrustedHttpsClient.java**. Ví dụ này:

- Nhận đường dẫn truststore PKCS12 và URI HTTPS từ tham số dòng lệnh.
- Đọc password tương tác qua console, không hard-code.
- Dùng **TrustManagerFactory** và **SSLContext** với những CA/certificate đã xác minh.
- Tạo **java.net.http.HttpClient** và **không vô hiệu hóa hostname verification**.
- Không ghi nội dung body hay token ra log.

~~~java
import java.io.Console;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.time.Duration;
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class TrustedHttpsClient {

    private static SSLContext createSslContext(
            Path truststorePath,
            char[] password
    ) throws Exception {
        KeyStore truststore = KeyStore.getInstance("PKCS12");

        try (InputStream in = Files.newInputStream(truststorePath)) {
            truststore.load(in, password);
        }

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm()
        );

        tmf.init(truststore);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(), null);

        return context;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                "Usage: java TrustedHttpsClient trust.p12 https://host/"
            );
            return;
        }

        Path truststorePath = Path.of(args[0]);
        URI uri = URI.create(args[1]);

        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null) {
            throw new IllegalArgumentException(
                "Phải cung cấp URI HTTPS có hostname"
            );
        }

        Console console = System.console();

        if (console == null) {
            throw new IllegalStateException(
                "Cần terminal tương tác để nhập password"
            );
        }

        char[] password = console.readPassword(
            "Truststore password: "
        );

        if (password == null) {
            throw new IllegalStateException("Không nhận được password");
        }

        SSLContext tls;

        try {
            tls = createSslContext(truststorePath, password);
        } finally {
            Arrays.fill(password, '\0');
        }

        HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();

        try (HttpClient client = HttpClient.newBuilder()
                .sslContext(tls)
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build()) {

            HttpResponse<Void> response = client.send(
                request,
                HttpResponse.BodyHandlers.discarding()
            );

            System.out.println("HTTP " + response.statusCode());
            System.out.println("URI: " + response.uri());
        }
    }
}
~~~

Biên dịch:

~~~bash
javac TrustedHttpsClient.java
~~~

Với lab HTTPS của bạn tại **localhost:8443** và truststore đã xác minh:

~~~bash
java TrustedHttpsClient dev-trust.p12 https://localhost:8443/
~~~

Nếu server thật không chạy ở địa chỉ này, kết nối sẽ thất bại; chương trình không tự khởi động server. Ví dụ **không** chạy thử mạng hoặc đọc file ngoài phạm vi được giao khi biên soạn bài.

### 12.1. Vì sao ví dụ vẫn kiểm tra hostname?

**TrustManagerFactory** trả về trust manager dựa trên chuỗi chứng thư đáng tin; **HttpClient** mặc định triển khai HTTPS/TLS với kiểm tra danh tính endpoint. Việc chỉ thay **SSLContext** để thêm trust anchors **không phải** yêu cầu tắt xác minh tên máy chủ.

Để thử tình huống sai danh tính trong lab, hãy thiết lập chứng thư chỉ có **DNS:localhost** nhưng cố truy cập bằng một host không nằm trong SAN. Client phải từ chối, dù chứng thư được nhập vào truststore.

**Không** dùng các công tắc nội bộ của JDK như **jdk.internal.httpclient.disableHostnameVerification** trong ứng dụng. Đây không phải phương án sửa truststore hoặc kết nối an toàn.

### 12.2. Lưu ý về truststore riêng

**dev-trust.p12** chỉ phục vụ endpoint đã xác minh bằng file/cert trong truststore ấy. Nếu dùng nó để gọi một website public khác, website có thể bị báo không đáng tin vì root CA công khai **không nằm trong file này**. Đó là giới hạn dự kiến của việc dùng truststore riêng, không phải lý do bật trust-all.

## 13. Lab server TLS cục bộ (tùy chọn)

Để có một endpoint thử nghiệm cho đoạn code trên, có thể dựng HTTPS server đơn giản bằng **jdk.httpserver** của JDK. Nó phù hợp học tập và test tích hợp nhỏ, **không tự thay thế cấu hình production HTTPS gateway/server**.

Tạo **LocalHttpsServer.java**:

~~~java
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsServer;
import java.io.Console;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.util.Arrays;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;

public final class LocalHttpsServer {

    public static void main(String[] args) throws Exception {
        Console console = System.console();

        if (console == null) {
            throw new IllegalStateException(
                "Hãy chạy từ terminal có console tương tác"
            );
        }

        char[] password = console.readPassword(
            "Dev server keystore password: "
        );

        if (password == null) {
            throw new IllegalStateException("Thiếu password");
        }

        KeyManagerFactory kmf;

        try {
            KeyStore identity = KeyStore.getInstance("PKCS12");

            try (InputStream in = Files.newInputStream(
                    Path.of("dev-server.p12"))) {
                identity.load(in, password);
            }

            kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm()
            );

            kmf.init(identity, password);
        } finally {
            Arrays.fill(password, '\0');
        }

        SSLContext tls = SSLContext.getInstance("TLS");
        tls.init(kmf.getKeyManagers(), null, null);

        HttpsServer server = HttpsServer.create(
            new InetSocketAddress("127.0.0.1", 8443), 0
        );

        server.setHttpsConfigurator(new HttpsConfigurator(tls));

        server.createContext("/", exchange -> {
            byte[] bytes = "Hello over TLS\n"
                .getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8"
            );

            exchange.sendResponseHeaders(200, bytes.length);

            try (OutputStream body = exchange.getResponseBody()) {
                body.write(bytes);
            }
        });

        server.start();
        System.out.println("Lab HTTPS server on 127.0.0.1:8443");
    }
}
~~~

Do lớp **HttpsServer** thuộc module **jdk.httpserver**, ví dụ có thể biên dịch/chạy rõ module:

~~~bash
javac --add-modules jdk.httpserver LocalHttpsServer.java
java --add-modules jdk.httpserver LocalHttpsServer
~~~

Chạy **TrustedHttpsClient** ở một terminal khác trong lúc server còn hoạt động.

Điều kiện:

- Tệp **dev-server.p12** đã được tạo ở phần 8.3.
- Mật khẩu nhập phù hợp với keystore và private key trong lab.
- File **dev-trust.p12** đã nhập chứng thư **dev-server.crt** hợp lệ.
- Tên **localhost** có SAN phù hợp; **127.0.0.1** cũng có SAN IP trong ví dụ.
- Port **8443** chưa bị chương trình khác dùng.

Khi hoàn thành, dừng tiến trình lab server từ terminal. Mã lab cố ý đơn giản hóa quản trị thread và lifecycle; không dùng làm HTTPS server production khi chưa thiết kế đầy đủ về giới hạn tài nguyên, logging và shutdown.

## 14. mTLS: khi client cũng phải có chứng thư

**Mutual TLS** yêu cầu xác thực **hai phía**:

~~~mermaid
sequenceDiagram
    participant C as Java client
    participant S as TLS server
    C->>S: ClientHello
    S-->>C: Server certificate và yêu cầu client certificate (khi cấu hình mTLS)
    Note over C: Xác minh trust chain + hostname server
    C->>S: Client certificate và chứng minh sở hữu private key
    Note over S: Xác minh certificate chain/danh tính client
    S-->>C: Hoàn tất handshake nếu hợp lệ
    C->>S: HTTP request trong TLS session
~~~

Đây là sơ đồ khái niệm; thứ tự thông điệp TLS 1.3 thực tế chi tiết hơn.

Để client trình bày chứng thư, cần một **identity keystore** chứa **PrivateKeyEntry**. Khi tạo SSLContext:

~~~java
KeyStore clientIdentity = loadPkcs12(
    Path.of("client-identity.p12"), identityStorePassword
);

KeyManagerFactory kmf = KeyManagerFactory.getInstance(
    KeyManagerFactory.getDefaultAlgorithm()
);

kmf.init(clientIdentity, privateKeyPassword);

KeyStore remoteTrust = loadPkcs12(
    Path.of("app-trust.p12"), truststorePassword
);

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
    TrustManagerFactory.getDefaultAlgorithm()
);

tmf.init(remoteTrust);

SSLContext mtlsContext = SSLContext.getInstance("TLS");

mtlsContext.init(
    kmf.getKeyManagers(),
    tmf.getTrustManagers(),
    null
);
~~~

Đoạn code trên là một phần của method ứng dụng (các biến password đã được nạp an toàn), không phải tệp Java độc lập.

Sau đó:

~~~java
HttpClient client = HttpClient.newBuilder()
    .sslContext(mtlsContext)
    .build();
~~~

Với mTLS:

- **KeyManager** phía client xác định private key/certificate chain dùng để xác thực với server.
- **TrustManager** phía client vẫn xác minh **server**.
- Server cần cấu hình yêu cầu client certificate, trust CA cấp certificate của client và ánh xạ danh tính đó sang quyền truy cập.
- mTLS **không tự thay thế authorization**. Một client có certificate hợp lệ vẫn có thể không được quyền gọi một endpoint cụ thể.

### 14.1. Certificate identity khác tài khoản ứng dụng

Trong hệ thống nội bộ, certificate có thể được gắn với workload/service hoặc tổ chức. Server phải định nghĩa chính sách nhận dạng dựa trên chứng thư và xác thực theo trust chain, EKU, các extension và identity fields thích hợp.

Đừng lấy **CN** tùy ý trong một chứng thư được cấp bởi bất kỳ CA nào rồi coi nó có toàn quyền. Cần giới hạn CA, danh tính, thời hạn và quyền truy cập theo hợp đồng ứng dụng.

## 15. HTTPS khác với raw SSLSocket

Với **HttpClient** HTTPS, JDK thực hiện nhiều việc cấp cao, gồm các quy tắc xác minh endpoint trong quá trình tạo kết nối HTTPS. Bạn thường **không phải tự viết mã so sánh SAN**.

Với **SSLSocket** hoặc **SSLEngine** sử dụng trực tiếp, JSSE **không mặc định bảo đảm hostname verification tương tự HTTPS ở tầng ứng dụng**. Vì thế cần cấu hình rõ endpoint identification.

Ví dụ **raw SSLSocket** cho client:

~~~java
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;

SSLContext context = SSLContext.getDefault();

try (SSLSocket socket = (SSLSocket)
        context.getSocketFactory().createSocket(
            "api.example.com", 443)) {

    SSLParameters parameters = socket.getSSLParameters();
    parameters.setEndpointIdentificationAlgorithm("HTTPS");
    socket.setSSLParameters(parameters);

    socket.startHandshake();

    System.out.println(
        "Protocol: " + socket.getSession().getProtocol()
    );
}
~~~

**Quan trọng:**

- Chọn đúng **hostname dự kiến** khi tạo socket.
- Gọi **setSSLParameters** **trước** khi bắt đầu TLS handshake.
- **"HTTPS"** là tên thuật toán endpoint identification chuẩn mà JSSE hỗ trợ.
- Nếu server dùng private CA, cần SSLContext đã cấu hình trust đúng như các ví dụ trước.
- Đoạn code trên chỉ trình diễn handshake; nó chưa gửi yêu cầu HTTP đúng cấu trúc.

**SSLSocket.getSession()** có thể cho biết giao thức/cipher suite sau handshake, nhưng bản thân việc nhận một session **không phải giấy chứng nhận** rằng ứng dụng đã làm mọi kiểm tra danh tính đúng. Trên raw socket, bạn phải bật endpoint identification thích hợp trước.

## 16. SSLParameters, TLS versions và hostname checking

**SSLParameters** cho phép đặt:

- Danh sách giao thức và cipher suites được phép theo policy.
- Endpoint identification algorithm.
- SNI server names.
- Một số chính sách khác cho SSLSocket, SSLEngine và các môi trường thích hợp.

~~~java
SSLParameters parameters = socket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(parameters);
~~~

Với **HttpClient.Builder.sslParameters(...)**, JDK ghi rõ một số parameters do HTTP client quản lý nội bộ có thể bị bỏ qua. Vì vậy, **đừng lấy việc gọi sslParameters() làm cơ chế duy nhất để thay đổi hoặc chứng minh chính sách hostname verification của HttpClient**. Mặc định HTTPS đúng và trust manager hợp lệ vẫn là hướng ưu tiên.

### 16.1. Không bật lại giao thức lỗi thời

Trên Java 27, JSSE áp dụng những ràng buộc an toàn thông qua các security properties, đặc biệt **jdk.tls.disabledAlgorithms**.

Nếu server bắt buộc dùng một thuật toán/chứng thư bị JDK từ chối, cách sửa đúng là **nâng cấp cấu hình và chứng thư của server**. Không tháo các ràng buộc về thuật toán yếu chỉ để kết nối thành công.

### 16.2. Một handshake thành công không thay mọi kiểm soát bảo mật

Cần đánh giá thêm:

- Chính sách certificate revocation/OCSP/CRL nếu hệ thống yêu cầu.
- Cơ chế luân chuyển và thu hồi certificate.
- Chính sách giới hạn TLS phiên bản/ciphers phù hợp với tổ chức.
- Cấu hình trust anchors và certificate issuance.
- Kiểm soát DNS/redirect khi URL do bên ngoài cung cấp.
- Xác thực và phân quyền ứng dụng sau TLS.

Không khẳng định mọi cấu hình JSSE sẽ tự kiểm tra thu hồi chứng thư. Trong cấu hình PKIX phổ biến dùng **TrustManagerFactory.init(KeyStore)**, tài liệu JSSE ghi nhận kiểm tra revocation bị tắt mặc định; muốn bảo đảm kiểm tra thu hồi, cần thiết kế và cấu hình PKIX/CRL/OCSP phù hợp, rồi kiểm chứng bằng test.

## 17. Kiểm tra chứng thư bằng X509Certificate

Java cung cấp **java.security.cert.X509Certificate** để đọc những thuộc tính của chứng thư.

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

static void inspectCertificate(Path path) throws Exception {
    CertificateFactory factory =
        CertificateFactory.getInstance("X.509");

    try (InputStream in = Files.newInputStream(path)) {
        X509Certificate certificate =
            (X509Certificate) factory.generateCertificate(in);

        System.out.println(
            "Subject: " + certificate.getSubjectX500Principal()
        );
        System.out.println(
            "Issuer: " + certificate.getIssuerX500Principal()
        );
        System.out.println(
            "NotAfter: " + certificate.getNotAfter()
        );
        System.out.println(
            "SAN: " + certificate.getSubjectAlternativeNames()
        );

        certificate.checkValidity();
    }
}
~~~

**checkValidity()** chỉ kiểm tra rằng thời điểm hiện tại nằm trong khoảng hiệu lực của certificate. Nó **không** tự động xác minh đường dẫn đến CA đáng tin, chữ ký của certificate chain, key usage, identity hostname hoặc chính sách revocation.

Cũng không nên tự viết hàm “xác minh TLS” bằng vài lần gọi **getSubjectAlternativeNames()** và **checkValidity()**. Hãy dùng JSSE TrustManager + endpoint identification chuẩn khi thiết lập kết nối thật.

## 18. Các lỗi TLS thường gặp

| Lỗi/dấu hiệu | Nguyên nhân có thể | Cách xử lý đúng |
|---|---|---|
| **PKIX path building failed** | Thiếu trust anchor phù hợp hoặc intermediate/chain cấu hình sai | Kiểm tra chain, issuer, truststore, CA qua kênh đáng tin |
| **unable to find valid certification path** | Trust manager không xây được đường dẫn hợp lệ | Xác minh root/intermediate và trust anchors |
| **No subject alternative DNS name matching ...** | SAN không chứa hostname yêu cầu | Cấp certificate có SAN phù hợp hoặc dùng hostname đúng |
| **No subject alternative names present** | Certificate thiếu SAN phù hợp | Cấp chứng thư mới với SAN |
| **CertificateExpiredException** | Quá **NotAfter** | Thay/luân chuyển certificate đúng hạn |
| **CertificateNotYetValidException** | Trước **NotBefore** hoặc đồng hồ sai | Kiểm tra ngày cấp và clock của hệ thống |
| **bad_certificate / certificate_unknown** | Peer từ chối certificate/chain | Kiểm tra CA, EKU, chain, client-auth policy |
| **handshake_failure** | Không khớp thuật toán/chứng thư/cipher/policy hoặc thiếu client certificate | Đối chiếu TLS config, mTLS và logs an toàn |
| **protocol_version** | Không có phiên bản giao thức cùng được phép | Nâng cấp peer để hỗ trợ TLS hiện hành |
| **UnrecoverableKeyException** | Password private key sai hoặc entry không thể nạp | Kiểm tra alias, keystore/key password |
| **KeyStoreException / IOException khi load** | Định dạng file, password, quyền truy cập hoặc file sai | Kiểm tra PKCS12, path, ACL và secret provisioning |
| Chạy được ở laptop nhưng lỗi trong container | JDK truststore khác, clock/CA/image khác | So sánh runtime và trust configuration thực tế |
| Có CA trong truststore nhưng vẫn sai hostname | Trust chain và hostname là hai phép kiểm tra riêng | Sửa SAN/hostname, không tắt hostname checking |

### 18.1. PKIX path building failed không đồng nghĩa “chỉ việc import leaf”

Nguyên nhân có thể là:

- Chứng thư được ký bởi CA mà client chưa được cấu hình tin.
- Server gửi thiếu intermediate certificate.
- Chuỗi có certificate hết hạn hoặc không hợp lệ theo policy.
- Thuật toán khóa/chữ ký bị JDK security policy loại bỏ.
- Truststore cấu hình nhầm file, nhầm password hoặc rỗng.

Chỉ nhập **một leaf certificate** nhận từ mạng vào truststore không phải giải pháp chung. Điều đó có thể biến chứng thư do attacker cung cấp thành một identity đáng tin trong cấu hình tương lai.

## 19. Chẩn đoán an toàn với keytool và JSSE debug

### 19.1. Xem certificate từ endpoint

~~~bash
keytool -printcert -sslserver api.example.com:443
~~~

Lệnh này giúp quan sát chứng thư mà endpoint trình bày tại thời điểm kết nối. **Nó không thay thế quy trình xác minh trust và hostname trong ứng dụng**.

Kiểm tra file của chính ứng dụng:

~~~bash
keytool -list -v -keystore app-trust.p12 -storetype PKCS12
~~~

Đối chiếu:

1. Có đúng trust anchor mong muốn không?
2. Chứng thư của server có SAN cho hostname thật không?
3. Thời gian hiệu lực và certificate chain có đúng không?
4. Key usage, CA basic constraints và thuật toán có hợp lệ không?
5. Có vô tình dùng truststore lab hoặc cấu hình cũ không?

### 19.2. JSSE debug

Để điều tra vấn đề handshake trong **môi trường kiểm thử được kiểm soát**, có thể bật:

~~~bash
java -Djavax.net.debug=ssl,handshake,trustmanager TrustedHttpsClient app-trust.p12 https://api.example.com/
~~~

Hoặc khi cần chẩn đoán certificate path:

~~~bash
java -Djava.security.debug=certpath TrustedHttpsClient app-trust.p12 https://api.example.com/
~~~

**Không bật log handshake chi tiết mặc định trong production.** Debug output có thể chứa thông tin certificate, endpoint, metadata kết nối hoặc dữ liệu phục vụ điều tra không nên xuất hiện trong log công khai.

Không ghi password, private key, giá trị token hoặc full request/response nhạy cảm chỉ để gỡ lỗi TLS.

## 20. Kiểm thử các trường hợp thành công và thất bại

Đối với một HTTPS client có cấu hình trust riêng, cần kiểm thử cả những gì **phải bị từ chối**.

| Test | Tình huống | Kết quả mong đợi |
|---|---|---|
| 1 | Chứng thư còn hạn, chain hợp lệ, SAN đúng, CA được phép tin | TLS thành công |
| 2 | Chứng thư do CA chưa được tin cậy cấp | TLS thất bại |
| 3 | CA được tin nhưng SAN sai hostname | TLS thất bại |
| 4 | Chứng thư hết hạn | TLS thất bại |
| 5 | Server gửi thiếu intermediate cần thiết | Thất bại nếu client không xây được path |
| 6 | Server dùng thuật toán bị policy cấm | TLS thất bại |
| 7 | mTLS server yêu cầu client certificate nhưng client không có | Handshake bị từ chối theo cấu hình |
| 8 | Client certificate hợp lệ về trust nhưng không được phép thực hiện API | Tầng authorization từ chối |
| 9 | Truststore path sai/không tồn tại | Không khởi tạo được trust config hợp lệ |
| 10 | HTTPS endpoint chuyển sang một tên khác qua redirect | Kiểm tra lại identity và policy đích |

Nên dùng một **HTTPS test server kiểm soát được**, certificate lab riêng và đồng hồ/CA fixtures thích hợp. Không xây test dựa trên việc truy cập website công cộng với certificate có thể đổi bất kỳ lúc nào.

### 20.1. Phân biệt unit test và integration test

**Unit test** có thể kiểm tra logic xác thực URI, lựa chọn truststore, kiểm tra configuration và các quy tắc nghiệp vụ.

**Integration test** cần thực hiện TLS handshake thật để chứng minh:

- JSSE trust manager thực sự từ chối certificate không đáng tin.
- Hostname verification thực sự phát hiện SAN không khớp.
- mTLS thực sự yêu cầu private key và certificate chain phù hợp.
- Cấu hình timeout, identity và HTTP request làm việc đúng với server.

Đừng mock mọi thành phần TLS rồi kết luận chắc chắn rằng chương trình đã xác thực máy chủ đúng.

## 21. Quản lý chứng thư trong production

Một thiết kế hoạt động lâu dài cần chính sách thay vì chỉ file password bảo vệ.

### 21.1. Tách trách nhiệm

- **Nhóm PKI / hạ tầng:** cấp phát, luân chuyển, thu hồi CA/leaf certificate.
- **Nhóm ứng dụng:** chọn trust anchors, cấu hình endpoint và kiểm tra quyền.
- **Nhóm vận hành:** bảo vệ private key, phân quyền file/secret và theo dõi hết hạn.
- **Nhóm an ninh:** quy định TLS version, cipher suites, revocation và audit.

### 21.2. Luân chuyển

Không chờ đến khi **NotAfter** mới đổi certificate. Lập kế hoạch cấp lại, cập nhật certificate chain và kiểm tra client interoperability trước thời hạn.

Không giả định việc ghi đè file **.p12** sẽ tự động cập nhật mọi **SSLContext/HttpClient** đã được tạo. Tùy cách nạp và cache, ứng dụng có thể cần tạo lại context/client hoặc cơ chế reload do framework cung cấp.

### 21.3. Bảo vệ private key

- Giữ private key trong kho bí mật hoặc HSM thích hợp.
- Hạn chế ACL của file chứa private key.
- Không commit **.p12**, **.key**, private PEM hoặc password vào git.
- Không nhúng password thực vào CLI, container image hoặc log.
- Khi có dấu hiệu lộ khóa, xử lý thu hồi/luân chuyển theo quy trình sự cố.

### 21.4. Không mở rộng trust quá mức

Thêm một CA mới vào truststore có nghĩa client có thể tin những chứng thư phù hợp mà CA đó được phép cấp theo cơ chế xác thực.

Vì vậy, một truststore dành cho private service nên được thiết kế **ít quyền và có phạm vi rõ ràng**. Việc tin tất cả CA trên toàn mạng nội bộ không mặc định là chính sách tối thiểu.

## 22. Checklist bảo mật TLS

Trước khi phát hành một ứng dụng Java gọi HTTPS, hãy kiểm tra:

- [ ] Sử dụng URI **https://** và hostname mong đợi.
- [ ] Chứng thư server có **SAN** đúng theo hostname/IP truy cập.
- [ ] Chain được xác thực tới trust anchor đã được phê duyệt.
- [ ] Không có code **trust-all**, HostnameVerifier trả **true** vô điều kiện hay tùy chọn tắt hostname verification.
- [ ] Chứng thư còn hạn và phù hợp key usage/EKU.
- [ ] TLS version/algorithm tuân thủ chính sách Java 27 và tổ chức.
- [ ] Nếu dùng private CA, truststore riêng có fingerprint được kiểm tra độc lập.
- [ ] Nếu dùng mTLS, client có private key và server xác thực/ủy quyền danh tính client.
- [ ] Password và private key được cung cấp qua cơ chế bảo mật, không hard-code.
- [ ] Có chính sách rotation, certificate expiry alert và revocation khi cần.
- [ ] HTTP client có timeout, redirect policy và kiểm soát URI khi đầu vào không đáng tin.
- [ ] Integration tests kiểm tra cả chứng thư hợp lệ **và** các trường hợp phải thất bại.
- [ ] Log gỡ lỗi TLS được kiểm soát quyền truy cập và tắt sau khi điều tra.

## 23. Bài thực hành

Xây dựng một lab gồm **HTTPS server localhost**, **truststore lab** và **HttpClient**:

1. Tạo keystore **dev-server.p12** chứa private key và certificate có **SAN=DNS:localhost,IP:127.0.0.1**.
2. Xuất chứng thư công khai và kiểm tra **SHA-256 fingerprint**.
3. Nhập certificate vào **dev-trust.p12** sau khi xác minh.
4. Chạy **LocalHttpsServer** ở loopback port 8443.
5. Dùng **TrustedHttpsClient** gọi **https://localhost:8443/** và xác nhận kết nối.
6. Thử một hostname không nằm trong SAN (được lab map về server) và xác nhận TLS từ chối dù truststore không đổi.
7. Thử một truststore trống/không có certificate phù hợp và quan sát lỗi PKIX.
8. Tạo certificate mới với thời hạn và SAN khác để luyện đọc **keytool -printcert**, **-list -v**.
9. So sánh **HttpClient** với **SSLSocket** khi bật endpoint identification **HTTPS**.
10. Viết báo cáo phân biệt lý do **chain untrusted**, **hostname mismatch**, **certificate expired** và **mTLS client certificate missing**.

### Câu hỏi tự kiểm tra

1. Một truststore có private key hay chỉ có chứng thư tin cậy? Có ngoại lệ nào theo từng loại KeyStore entry?
2. Vì sao một CA đã được tin vẫn không cho phép chứng thư của website A đại diện cho website B?
3. SAN và CN khác nhau như thế nào trong chứng thư HTTPS mới?
4. Khác biệt giữa **KeyManagerFactory** và **TrustManagerFactory** là gì?
5. Client cần keystore private key trong trường hợp HTTPS nào?
6. Vì sao import bất kỳ certificate tải từ mạng là một ý tưởng nguy hiểm?
7. SSLContext được nạp với custom truststore có tự giữ các public root mặc định không?
8. Khi dùng raw **SSLSocket**, cần bật cơ chế gì trước handshake để kiểm tra hostname?
9. Vì sao **X509Certificate.checkValidity()** chưa đủ để xác minh một HTTPS endpoint?
10. Khi JVM báo **PKIX path building failed**, bạn cần điều tra những thành phần nào?

## 24. Ghi nhớ

- **TLS** cung cấp kênh truyền bảo mật; **xác minh danh tính máy chủ** đòi hỏi cả chuỗi chứng thư đáng tin và hostname phù hợp.
- **X.509 certificate** mang public key và các thông tin đã được ký; **private key** phải được giữ riêng.
- **SAN** là nơi khai báo DNS/IP mà chứng thư phục vụ; không dựa vào CN như phương án thay thế cho cấu hình mới.
- **PKCS12** là định dạng keystore được khuyến nghị trên Java 27; tránh tạo file JKS mới nếu không có yêu cầu tương thích rõ ràng.
- **KeyStore** là abstraction có thể chứa **PrivateKeyEntry**, **TrustedCertificateEntry** và các loại entry khác.
- **KeyManagerFactory** sử dụng danh tính của chính endpoint; **TrustManagerFactory** kiểm tra độ tin cậy của phía bên kia.
- **SSLContext** ghép key managers, trust managers và cấu hình TLS.
- **HttpClient** mặc định có kiểm tra HTTPS hostname; việc cấu hình custom truststore không có nghĩa được tắt hostname verification.
- **SSLSocket/SSLEngine** cấp thấp cần cấu hình endpoint identification khi muốn xác minh tên máy chủ theo HTTPS.
- **mTLS** dùng thêm client certificate/private key và yêu cầu xác thực ở server, nhưng không tự thay thế authorization.
- Không chấp nhận mọi chứng thư, tắt hostname verification hoặc bật lại giao thức/thuật toán yếu để “chữa” lỗi TLS.
- Trong production, bảo vệ private key, kiểm chứng fingerprint của CA, quản lý vòng đời chứng thư và viết test cho các trường hợp phải bị từ chối.

## Tài liệu tham khảo

- [Java SE 27 — Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/27/security/java-secure-socket-extension-jsse-reference-guide.html)
- [Java SE 27 — Java Cryptography Architecture (JCA) Reference Guide](https://docs.oracle.com/en/java/javase/27/security/java-cryptography-architecture-jca-reference-guide.html)
- [Java SE 27 API — KeyStore](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/KeyStore.html)
- [Java SE 27 — keytool Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/keytool.html)
- [Java SE 27 API — X509Certificate](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/cert/X509Certificate.html)
- [Java SE 27 API — SSLContext](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/net/ssl/SSLContext.html)
- [Java SE 27 API — SSLParameters](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/net/ssl/SSLParameters.html)
- [Java SE 27 API — KeyManagerFactory](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html)
- [Java SE 27 API — TrustManagerFactory](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html)
- [Java SE 27 API — X509ExtendedTrustManager](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/net/ssl/X509ExtendedTrustManager.html)
- [Java SE 27 API — HttpClient.Builder](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Java SE 27 — Security Providers and TLS Algorithms](https://docs.oracle.com/en/java/javase/27/security/oracle-providers.html)
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280)
