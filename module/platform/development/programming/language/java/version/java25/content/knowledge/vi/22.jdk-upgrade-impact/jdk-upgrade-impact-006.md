# Kiểm tra provider mật mã, TLS, chứng chỉ và cấu hình bảo mật đang áp dụng

## 1. Mục tiêu kiểm tra khi nâng cấp JDK

Một ứng dụng Java có thể biên dịch và khởi động thành công sau khi đổi JDK nhưng vẫn gặp lỗi khi gọi dịch vụ HTTPS, đọc private key, xác thực certificate hoặc dùng provider phần cứng. Nguyên nhân thường nằm ở cấu hình bảo mật thực tế: provider được chọn khác trước, thuật toán bị đưa vào danh sách hạn chế, truststore thay đổi, TLS handshake thương lượng khác hoặc một API bảo mật cũ không còn hoạt động.

Bài thuộc chương **Tác động nâng cấp** của module **JAVA_VERSION_JAVA25**, với đề bài **“Kiểm tra provider mật mã, TLS, chứng chỉ và cấu hình bảo mật đang áp dụng”**. Nội dung đặt Java 25 làm mốc học tập và đối chiếu các thay đổi tiếp theo đến JDK 27, là dòng GA hiện hành tại ngày biên soạn **27-11-2026**. Các thay đổi của Oracle JDK được ghi rõ theo bản phân phối; JDK vendor khác có thể đóng gói provider, truststore và security properties khác nhau.

Mục tiêu là lập được một cuộc kiểm tra trước/sau nâng cấp có thể tái lập, xác nhận provider và security properties thực sự được sử dụng, kiểm tra TLS/certificate theo đúng chính sách, rồi quyết định rollout dựa trên bằng chứng.

### Sau bài này, bạn có thể

1. Xác định chính xác JDK vendor, build, JVM và provider đang chạy.
2. Kiểm tra provider order, dịch vụ mật mã và provider thực sự được chọn cho một operation.
3. Phân biệt system properties với Java security properties.
4. Đọc và quản lý các giới hạn thuật toán cho TLS, certificate path và JCE.
5. Kiểm tra keystore, truststore, certificate chain, hostname và revocation.
6. Điều tra TLS handshake bằng JSSE debug và thông tin phiên đã thương lượng.
7. Đánh giá những thay đổi bảo mật quan trọng giữa JDK 25, 26 và 27.
8. Phát hiện code còn phụ thuộc vào Security Manager đã bị vô hiệu hóa.
9. Thiết kế test matrix và checklist rollout cho ứng dụng dùng provider tùy chỉnh, PKCS#11 hoặc HSM.

## 2. Bốn lớp cần xác minh

Khi nói “ứng dụng đang dùng provider X và TLS Y”, cần tách bốn lớp:

| Lớp | Nội dung | Ví dụ cần ghi lại |
| --- | --- | --- |
| Runtime | Binary Java thật sự khởi chạy process | JDK vendor, full version, VM name, OS, architecture |
| Provider | Các implementation JCA/JSSE được đăng ký và thứ tự ưu tiên | SUN, SunRsaSign, SunEC, SunJSSE, SunJCE, SunPKCS11 hoặc provider bên thứ ba |
| Security configuration | Chính sách và giới hạn được nạp vào JVM | security.provider.n, jdk.tls.disabledAlgorithms, jdk.certpath.disabledAlgorithms |
| Connection/trust material | Cấu hình TLS và certificate dùng trong phiên thật | SSLContext, truststore, keystore, certificate chain, protocol, cipher suite, named group |

Một máy có thể cài nhiều JDK; container có thể dùng binary khác host; một ứng dụng có thể tạo nhiều SSLContext với trust manager khác nhau. Vì vậy, kiểm tra trên máy phát triển không thay thế kiểm tra trong process production.

## 3. Xác nhận JDK, vendor và bản cập nhật đang chạy

Bắt đầu bằng chính binary trong môi trường triển khai:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Ghi lại tối thiểu các thuộc tính:

| Property | Ý nghĩa |
| --- | --- |
| java.version | Phiên bản Java |
| java.runtime.version | Full runtime version/build |
| java.vendor | Nhà cung cấp JDK |
| java.vm.name | JVM implementation |
| java.vm.vendor | Nhà cung cấp JVM |
| java.vm.version | Phiên bản/build VM |
| os.name | Hệ điều hành |
| os.arch | Kiến trúc CPU |
| java.home | Thư mục runtime thực tế |

Nếu process được khởi chạy bằng service manager, container entrypoint hoặc script riêng, xác minh executable mà process sử dụng; đừng chỉ dựa vào biến JAVA_HOME của terminal tương tác.

### Theo dõi security baseline, không chỉ major version

Bản cập nhật CPU có thể bổ sung distrust policy, thay đổi truststore và sửa lỗi bảo mật dù major version không đổi. Theo consolidated release notes của Oracle, tại ngày 17-11-2026 security baseline là:

| Oracle JRE family | Security baseline |
| --- | --- |
| JDK 27 | 27.0.1.1+4 |
| JDK 25 | 25.0.5.1+4 |
| JDK 21 | 21.0.13.1+4 |

Đây là baseline của Oracle tại thời điểm công bố; vendor khác có lịch cập nhật và số build riêng. Luôn đối chiếu security baseline của vendor và cập nhật Critical Patch Update (CPU) theo chính sách tổ chức. Không coi một bản GA ban đầu là mục tiêu triển khai lâu dài. [Oracle JDK 27 Consolidated Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)

## 4. Provider là gì và provider order ảnh hưởng ra sao?

JCA (Java Cryptography Architecture) định nghĩa các engine APIs như `Cipher`, `Signature`, `MessageDigest`, `KeyFactory`, `KeyStore` và `SecureRandom`. JSSE cung cấp các engine cho kết nối TLS như `SSLContext`, `KeyManagerFactory` và `TrustManagerFactory`. Provider cung cấp implementation cụ thể cho từng dịch vụ và thuật toán.

Một JDK thường phân chia implementation giữa nhiều provider. Ví dụ trên Oracle JDK 25, danh sách phổ biến gồm:

| Provider | Vai trò tiêu biểu |
| --- | --- |
| SUN | MessageDigest, SecureRandom, certificate/path services và các dịch vụ nền tảng |
| SunRsaSign | RSA signatures |
| SunEC | Elliptic-curve cryptography |
| SunJSSE | TLS/DTLS, SSLContext, trust/key manager factories |
| SunJCE | Cipher, MAC, SecretKeyFactory và các dịch vụ JCE |
| SunPKCS11 | Adapter tới cryptographic token/HSM thông qua native PKCS#11 library |
| SunMSCAPI / Apple | Tích hợp kho khóa hoặc dịch vụ mật mã của hệ điều hành trên nền tảng tương ứng |

Các provider thực tế phụ thuộc module, vendor và build. Không giả định mọi JDK đều có cùng danh sách hoặc cùng thứ tự.

### Provider order

Các thuộc tính `security.provider.n` trong file `java.security` xác định thứ tự provider. Khi ứng dụng gọi factory không chỉ định provider, JVM tìm implementation phù hợp theo thứ tự ưu tiên. Một provider đứng trước có thể thay đổi implementation được chọn khi nâng cấp hoặc khi thêm provider mới.

Oracle khuyến nghị ứng dụng phổ thông không pin tên provider trong mọi lời gọi `getInstance`. Cách gọi chung giúp runtime chọn implementation thích hợp, đồng thời tránh phụ thuộc vào tên provider chỉ có trên một bản phân phối. Việc pin provider vẫn có thể cần khi compliance, HSM hoặc policy yêu cầu rõ implementation; khi đó phải kiểm thử cả thuật toán và provider trên đúng môi trường triển khai. [JDK Providers Documentation](https://docs.oracle.com/en/java/javase/25/security/oracle-providers.html)

## 5. Liệt kê provider và xác nhận provider được chọn

Có thể liệt kê provider đã đăng ký bằng Java:

~~~java
import java.security.Provider;
import java.security.Security;

public class ProviderInventory {
    public static void main(String[] args) {
        int position = 1;
        for (Provider provider : Security.getProviders()) {
            System.out.printf(
                    "%d. %s %s%n",
                    position++,
                    provider.getName(),
                    provider.getVersionStr());

            provider.getServices().stream()
                    .filter(service ->
                            service.getType().equals("Cipher")
                            || service.getType().equals("Signature")
                            || service.getType().equals("KeyStore")
                            || service.getType().equals("KeyFactory")
                            || service.getType().equals("SSLContext")
                            || service.getType().equals("TrustManagerFactory"))
                    .limit(12)
                    .forEach(service -> System.out.printf(
                            "   %s.%s%n",
                            service.getType(),
                            service.getAlgorithm()));
        }
    }
}
~~~

Danh sách này cho biết provider và services được đăng ký. Nó chưa chứng minh service nào được dùng trong một operation cụ thể.

### In provider của operation thật

~~~java
import java.security.Security;
import javax.crypto.Cipher;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public class SelectedProvider {
    public static void main(String[] args) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        SSLContext sslContext = SSLContext.getInstance("TLS");
        TrustManagerFactory trustManagers =
                TrustManagerFactory.getInstance(
                        TrustManagerFactory.getDefaultAlgorithm());

        System.out.println("Cipher: " + cipher.getProvider().getName());
        System.out.println("SSLContext: " + sslContext.getProvider().getName());
        System.out.println(
                "TrustManagerFactory: "
                        + trustManagers.getProvider().getName());

        System.out.println(
                "Default KMF algorithm: "
                        + javax.net.ssl.KeyManagerFactory.getDefaultAlgorithm());
        System.out.println(
                "Default TMF algorithm: "
                        + TrustManagerFactory.getDefaultAlgorithm());
    }
}
~~~

Các factory ở ví dụ được tạo theo cơ chế lựa chọn provider mặc định. Nếu production dùng provider chỉ định tường minh, hãy thêm test cho đúng overload đó và ghi provider được trả về.

### Khi nào nên pin provider?

- Chính sách FIPS/compliance yêu cầu một cryptographic module và cấu hình đã được chứng nhận cụ thể.
- Private key nằm trong HSM và phải được thao tác thông qua provider PKCS#11 tương ứng.
- Một thuật toán cần implementation của vendor có kiểm soát.
- Ứng dụng có hợp đồng vận hành yêu cầu cố định implementation giữa các lần triển khai.

Nếu không có yêu cầu như vậy, ưu tiên cơ chế provider selection của JCA. Nếu pin provider, ghi rõ lý do, version, service/algorithm cần thiết và cách kiểm tra khi nâng JDK.

## 6. Kiểm tra provider có đúng service và algorithm

Provider có thể được đăng ký nhưng không hỗ trợ thuật toán mà ứng dụng gọi. Đừng chỉ kiểm tra provider name.

Ví dụ kiểm tra các dịch vụ thiết yếu:

~~~java
import java.security.Provider;
import java.security.Security;

public class CheckCryptoServices {
    public static void main(String[] args) {
        String[][] required = {
                {"Cipher", "AES/GCM/NoPadding"},
                {"Signature", "SHA256withRSA"},
                {"MessageDigest", "SHA-256"},
                {"KeyFactory", "RSA"},
                {"KeyStore", "PKCS12"},
                {"SSLContext", "TLS"},
                {"TrustManagerFactory", "PKIX"}
        };

        for (String[] requirement : required) {
            String type = requirement[0];
            String algorithm = requirement[1];
            boolean found = false;

            for (Provider provider : Security.getProviders()) {
                if (provider.getService(type, algorithm) != null) {
                    System.out.printf(
                            "%s.%s -> %s%n",
                            type, algorithm, provider.getName());
                    found = true;
                }
            }

            if (!found) {
                System.out.printf(
                        "MISSING: %s.%s%n", type, algorithm);
            }
        }
    }
}
~~~

Ví dụ này là inventory ban đầu. Một số provider dùng alias hoặc tên transformation khác nhau; kết quả cuối cùng vẫn phải được xác nhận bằng cách tạo engine object và chạy phép thử thực tế.

Với PKCS#11, một algorithm có thể được provider công bố nhưng token, firmware hoặc native library không hỗ trợ mechanism tương ứng. Kiểm tra cấu hình token, slot, login, key attributes và operation thật; không chỉ dựa vào danh sách service.

## 7. Đọc security properties đang có hiệu lực

Security properties khác system properties:

- `System.getProperty(...)` đọc system properties, thường được đặt bằng `-Dname=value`.
- `Security.getProperty(...)` đọc Java security properties được nạp từ file bảo mật hoặc đặt bằng `Security.setProperty(...)`.
- `System.setProperty(...)` không thay thế `Security.setProperty(...)`.
- Một số security properties được đọc và cache khi lớp `java.security.Security` khởi tạo. Đặt lại sau đó có thể không có hiệu lực và không nhất thiết ném exception.

Ví dụ đọc các giá trị liên quan:

~~~java
import java.security.Security;

public class ActiveSecurityProperties {
    public static void main(String[] args) {
        String[] names = {
                "security.provider.1",
                "security.provider.2",
                "jdk.tls.disabledAlgorithms",
                "jdk.tls.legacyAlgorithms",
                "jdk.certpath.disabledAlgorithms",
                "jdk.crypto.disabledAlgorithms",
                "jdk.security.caDistrustPolicies"
        };

        for (String name : names) {
            System.out.println(
                    name + " = " + Security.getProperty(name));
        }
    }
}
~~~

Không phải mọi property đều có trên mọi JDK release. Ví dụ `jdk.crypto.disabledAlgorithms` được bổ sung trong JDK 26; trên JDK 25, giá trị có thể là `null`. Ghi lại cả release và giá trị thực tế, không suy luận từ danh sách property trong một tài liệu khác.

### Công cụ chẩn đoán

Trên JDK 25 trở lên:

~~~bash
java -XshowSettings:security -version
~~~

Để xem quá trình đọc file và giá trị security properties:

~~~bash
java -Djava.security.debug=properties -jar app.jar
~~~

Trên JDK 27, có thể xem trực tiếp security properties của process đang chạy:

~~~bash
jcmd <pid> VM.security_properties
~~~

Đây là lệnh mới của JDK 27, hữu ích khi cần xác minh process production. Trên JDK 25, dùng `-XshowSettings:security`, debug logging hoặc đoạn Java đọc `Security.getProperty`.

Không gửi log debug rộng ra nơi công khai. Output có thể tiết lộ provider, policy, đường dẫn cấu hình và chi tiết triển khai.

## 8. File java.security và cách nạp cấu hình tùy chỉnh

File master security properties thường nằm ở:

~~~text
<java-home>/conf/security/java.security
~~~

File này chứa provider registrations, algorithm constraints và nhiều cấu hình bảo mật mặc định.

### Nạp thêm file cấu hình

Dùng system property sau lúc khởi chạy:

~~~bash
java -Djava.security.properties=file:/opt/app/security-extra.properties -jar app.jar
~~~

Một dấu bằng có nghĩa file bổ sung được nối vào master security properties. Các property trùng tên có thể ghi đè giá trị trước đó theo thứ tự xử lý.

### Thay thế toàn bộ master file

~~~bash
java -Djava.security.properties==file:/opt/app/security-replacement.properties -jar app.jar
~~~

Hai dấu bằng yêu cầu dùng file chỉ định thay cho master file. Đây là cấu hình có rủi ro cao: nếu file thay thế thiếu provider registrations hoặc các algorithm restrictions mặc định, runtime có thể thay đổi lớn hoặc yếu đi. Chỉ dùng khi tổ chức quản lý đầy đủ file và có kiểm thử chuyên biệt.

### Include file cấu hình

JDK hỗ trợ directive `include` trong security properties file. Tính năng này cho phép chia policy thành nhiều file, ví dụ profile chung và profile riêng cho từng môi trường.

~~~properties
include /opt/java-security/profiles/prod.security
~~~

File được include và toàn bộ thư mục cha phải chỉ cho tài khoản tin cậy ghi. Nếu một người dùng không được phép có thể thay file hoặc đổi thư mục cha, họ có thể ghi đè security properties và hạ mức bảo vệ của JVM.

### Thay đổi động trong code

Có thể dùng `Security.setProperty(name, value)` khi ứng dụng cần thay đổi security property trước khi thành phần tương ứng khởi tạo. Tuy nhiên, không nên xây dựng chính sách production dựa trên thay đổi động muộn vì một số giá trị đã được cache và không được đọc lại.

Ưu tiên cấu hình được quản lý ở startup, lưu phiên bản file policy, kiểm tra giá trị cuối cùng và kiểm thử đúng thứ tự khởi tạo. [The Security Properties File](https://docs.oracle.com/en/java/javase/25/security/security-properties-file.html)

## 9. Ba tầng giới hạn thuật toán cần phân biệt

Khi nâng JDK, lỗi thuật toán thường liên quan đến ba security properties khác nhau:

| Property | Tầng áp dụng | Vai trò |
| --- | --- | --- |
| `jdk.tls.disabledAlgorithms` | TLS/DTLS trong JSSE implementation | Hạn chế protocol, cipher suite, key size và signature scheme trong handshake |
| `jdk.certpath.disabledAlgorithms` | Certificate path validation | Hạn chế thuật toán chữ ký, key size và điều kiện trong chain |
| `jdk.crypto.disabledAlgorithms` | JCE services | Hạn chế thuật toán ở tầng JCE như Cipher hoặc MessageDigest |

`jdk.crypto.disabledAlgorithms` được bổ sung trong JDK 26. Khi nâng từ Java 25 lên JDK 26/27, hãy kiểm tra property mới này cùng hai property TLS/CertPath; đừng coi chúng là một danh sách chung.

Ngoài ra, `jdk.tls.legacyAlgorithms` đánh dấu các thuật toán cũ mà JSSE có thể chỉ thương lượng khi không còn lựa chọn tốt hơn. Nếu một thuật toán vừa nằm trong legacy list vừa bị disabled bởi property hoặc AlgorithmConstraints, nó sẽ không được thương lượng.

Các security properties này là chi tiết của implementation; tài liệu Oracle nói rõ implementation JSSE khác không bắt buộc phải dùng cùng property hoặc cùng semantics. Với vendor khác, đọc tài liệu của provider thực tế.

## 10. Hiểu tác động của jdk.tls.disabledAlgorithms

JDK 25 thay đổi mặc định quan trọng: SHA-1 bị vô hiệu hóa trong chữ ký handshake TLS/DTLS 1.2. Các scheme sau được thêm vào `jdk.tls.disabledAlgorithms`:

- `rsa_pkcs1_sha1 usage HandshakeSignature`
- `ecdsa_sha1 usage HandshakeSignature`
- `dsa_sha1 usage HandshakeSignature`

Điều này nhắm vào chữ ký handshake, không nên diễn giải thành một câu khẳng định rằng mọi dữ liệu SHA-1 trong mọi ngữ cảnh đều bị chặn bởi cùng một property. Certificate path có property riêng và policy riêng.

Một server cũ có thể vẫn gửi certificate chain nhưng không thể hoàn tất handshake nếu chỉ cung cấp signature scheme đã bị chặn. Cách xử lý đúng là cập nhật server/certificate/signature configuration sang thuật toán được hỗ trợ, sau đó kiểm thử tương thích với client mới.

**Không xóa SHA-1 khỏi disabled list như một cách sửa nhanh production.** Nếu buộc phải có ngoại lệ chuyển tiếp, phải có đánh giá rủi ro, phạm vi endpoint hẹp, thời hạn loại bỏ và phê duyệt security.

## 11. Kiểm tra TLS protocols và cipher suites

Với ứng dụng mới, dùng TLS 1.3 và TLS 1.2 khi cần tương thích. Không cấu hình SSLv3, TLS 1.0 hoặc TLS 1.1 làm phương án fallback.

Có thể xem protocol/cipher suite được runtime hỗ trợ bằng SSLContext:

~~~java
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;

public class TlsCapabilities {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getDefault();
        SSLParameters defaults = context.getDefaultSSLParameters();
        SSLParameters supported = context.getSupportedSSLParameters();

        System.out.println("Provider: " + context.getProvider().getName());
        System.out.println("Default protocols:");
        for (String protocol : defaults.getProtocols()) {
            System.out.println("  " + protocol);
        }

        System.out.println("Supported protocols:");
        for (String protocol : supported.getProtocols()) {
            System.out.println("  " + protocol);
        }

        System.out.println("Default cipher suites:");
        for (String suite : defaults.getCipherSuites()) {
            System.out.println("  " + suite);
        }
    }
}
~~~

Danh sách supported không đồng nghĩa danh sách enabled. Một protocol/cipher có thể tồn tại trong provider nhưng bị disabled bởi security properties hoặc không được bật mặc định.

### Không pin cipher suites quá sớm

Đặt một danh sách cipher suite cứng có thể chặn các cải tiến mặc định của JDK và làm mất tương thích khi provider thêm TLS 1.3 hoặc hybrid key exchange. Chỉ pin khi có yêu cầu interoperability/compliance rõ ràng; ưu tiên để JSSE áp dụng lựa chọn an toàn mặc định và kiểm tra negotiated session.

## 12. Bảo đảm hostname verification trong TLS client

Trust chain hợp lệ không tự chứng minh server chính là hostname mà ứng dụng muốn kết nối. HTTPS client cần endpoint identification để ngăn kết nối tới server có certificate hợp lệ nhưng sai tên.

Ví dụ dùng SSLSocket cho HTTPS:

~~~java
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSession;
import javax.net.ssl.SSLSocket;
import java.util.Arrays;

public class HttpsTlsProbe {
    public static void main(String[] args) throws Exception {
        String host = args[0];
        int port = Integer.parseInt(args[1]);

        try (SSLSocket socket = (SSLSocket) SSLContext.getDefault()
                .getSocketFactory()
                .createSocket(host, port)) {

            SSLParameters parameters = socket.getSSLParameters();
            parameters.setProtocols(new String[] {"TLSv1.3", "TLSv1.2"});
            parameters.setEndpointIdentificationAlgorithm("HTTPS");
            socket.setSSLParameters(parameters);

            socket.startHandshake();

            SSLSession session = socket.getSession();
            System.out.println("Protocol: " + session.getProtocol());
            System.out.println("Cipher: " + session.getCipherSuite());
            System.out.println("Peer: " + session.getPeerPrincipal());
        }
    }
}
~~~

Đây là probe cho HTTPS. Với giao thức TLS riêng, chọn endpoint identity policy tương ứng. Không bỏ hostname verification để làm cho certificate lỗi vẫn kết nối được.

Không cài TrustManager luôn trả lời trusted hoặc HostnameVerifier luôn trả true. Các đoạn code kiểu “trust all certificates” vô hiệu hóa mục tiêu xác thực peer và không phải giải pháp nâng cấp.

## 13. Phân biệt keystore và truststore

Hai loại store phục vụ mục đích khác nhau:

| Store | Chứa gì? | Dùng khi |
| --- | --- | --- |
| Keystore | Private key và certificate chain của chính ứng dụng; có thể chứa secret key | TLS server, mutual TLS client hoặc ký số |
| Truststore | Trusted certificate entries làm trust anchors | Xác minh certificate của peer/CA |

Trong JSSE, các system properties thường gặp:

- `javax.net.ssl.keyStore` và `javax.net.ssl.keyStoreType`: chỉ định keystore dùng cho default key managers.
- `javax.net.ssl.trustStore` và `javax.net.ssl.trustStoreType`: chỉ định truststore dùng cho default trust managers.

Nếu dùng password cho store, không nên đặt password trực tiếp trong command line hoặc script có thể bị đọc bởi process inspection/log. Ưu tiên secret manager, secret mount với quyền hạn chế hoặc callback/configuration bảo mật phù hợp.

### PKCS12

PKCS12 là default keystore type của JDK hiện đại. Kiểm tra giá trị runtime bằng:

~~~java
System.out.println(java.security.KeyStore.getDefaultType());
~~~

Khi di chuyển store cũ, chỉ chuyển đổi định dạng sau khi đã xác định loại entry, certificate chain, key password và provider hỗ trợ. Không đổi định dạng store đồng thời với việc đổi trust policy nếu muốn khoanh vùng nguyên nhân lỗi.

## 14. Kiểm tra cacerts và certificate chain

Liệt kê trust anchors mặc định của JDK:

~~~bash
keytool -list -cacerts
~~~

Kiểm tra một truststore riêng:

~~~bash
keytool -list -v -keystore truststore.p12 -storetype PKCS12
~~~

Xem certificate file trước khi import:

~~~bash
keytool -printcert -file root-ca.pem -v
~~~

Đối chiếu SHA-256 fingerprint với nguồn tin cậy độc lập của CA hoặc tổ chức phát hành. Không import certificate làm trust anchor chỉ vì nó được gửi cùng kết nối hoặc nằm trong một file cấu hình.

Khi cần thêm CA vào truststore ứng dụng:

~~~bash
keytool -importcert -alias internal-root-ca -file root-ca.pem -keystore truststore.p12 -storetype PKCS12
~~~

Lệnh sẽ yêu cầu xác nhận tương tác. Xác minh fingerprint trước khi chấp nhận. Tránh dùng `-noprompt` cho việc import trust anchor nếu chưa có quy trình kiểm soát và xác minh độc lập.

### Các trường cần kiểm tra trong chain

- Subject và Issuer có đúng thứ tự và quan hệ mong đợi không?
- Certificate có còn trong validity period không?
- Subject Alternative Name có chứa hostname mà client kết nối không?
- Basic Constraints có đánh dấu CA đúng cho intermediate/root không?
- Key Usage và Extended Key Usage có phù hợp với server/client authentication không?
- Signature algorithm và public key size có còn được policy chấp nhận không?
- Chain có thể xây dựng tới trust anchor mà ứng dụng thực sự tin cậy không?
- Revocation policy có yêu cầu OCSP hoặc CRL không?

`keytool -list` giúp xem entry/fingerprint, nhưng parse certificate thành công không đồng nghĩa path validation hoặc hostname verification thành công.

## 15. Kiểm tra thay đổi truststore khi nâng JDK

Truststore mặc định có thể thay đổi giữa các bản update. Một kết nối thành công trên JDK cũ có thể thất bại sau nâng cấp vì CA bị distrust hoặc certificate chain đã hết hiệu lực.

Một thay đổi đáng chú ý của Oracle JDK 27:

- Hai root WISeKey Global GB và GC được thêm vào `cacerts`.
- Trong JDK 27.0.1.0.3, các root emSign/eMudhra và Comodo AAA bị loại khỏi `cacerts`.
- Các intermediate eMudhra bị xâm phạm cũng bị đưa vào danh sách blocked; certificate chain chứa các intermediate này có thể khiến TLS session không được thiết lập và JAR signature validation thất bại.

Các thay đổi này là policy trust của Oracle JDK và update cụ thể. Vendor khác có thể có truststore riêng. Khi nâng, so sánh alias/fingerprint của truststore cũ và mới, kiểm tra dependency endpoint đang dùng CA đó, rồi làm việc với CA/đơn vị vận hành để cập nhật chain hợp lệ.

Không tự thêm lại CA đã bị distrust chỉ để khôi phục kết nối. Chỉ tạo ngoại lệ nếu có đánh giá rủi ro và chính sách được phê duyệt. [Oracle JDK 27 Consolidated Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)

## 16. Certificate path, OCSP và CRL

Certificate path validation không chỉ kiểm tra chữ ký của từng certificate. Nó còn xét trust anchor, validity, basic constraints, key usage, algorithm constraints và các policy liên quan.

Nếu ứng dụng bật revocation checking, cần kiểm tra thêm:

- CRL Distribution Points và OCSP responder URI có truy cập được không?
- Timeout kết nối và timeout đọc response có hợp lý không?
- Proxy/firewall có chặn truy cập CA/OCSP/CRL không?
- CRL có quá lớn hoặc bị lỗi định dạng không?
- Ứng dụng xử lý trạng thái unknown/revoked theo đúng security policy không?

Trong JDK 27, property `com.sun.security.crl.maxSize` giới hạn kích thước CRL tải về qua URI trong certificate path validation; mặc định là 20 MiB. CRL vượt ngưỡng sẽ không được xử lý. Có thể bật `-Djava.security.debug=certpath` để xem thông tin path validation và giới hạn đang áp dụng.

Đừng vô hiệu hóa revocation checking chỉ để bỏ qua lỗi kết nối. Xác định nguyên nhân mạng, timeout hoặc CRL trước, rồi thiết kế fallback theo chính sách rủi ro của hệ thống.

## 17. Thay đổi mật mã đáng chú ý trong Java 25

JDK 25 có một số thay đổi cần đưa vào test nâng cấp:

| Thay đổi | Tác động cần kiểm tra |
| --- | --- |
| SHA-1 bị disable trong TLS/DTLS 1.2 handshake signatures | Endpoint cũ chỉ hỗ trợ SHA-1 handshake signature có thể không bắt tay được |
| SunJCE PBE SecretKeyFactory hỗ trợ password Unicode qua UTF-8 | Kiểm tra tương thích password mã hóa key giữa JDK/provider khác nhau |
| SHAKE128-256 và SHAKE256-512 được thêm vào SUN provider | Kiểm tra ứng dụng/provider lookup thuật toán digest mới nếu có sử dụng |
| SunPKCS11 bổ sung hỗ trợ HKDF | Kiểm tra native PKCS#11 library, token và mechanism thực tế |
| TLS Keying Material Exporters được hỗ trợ trong JSSE/SunJSSE | Ứng dụng có thể lấy EKM từ TLS session cho giao thức ứng dụng cần exporter |
| TLS signature schemes có thể được disable theo TLS scope | Kiểm tra policy chữ ký cho đúng mục đích handshake/certificate |
| XML Security for Java được cập nhật lên 3.0.5 và JAR validation được tăng cường | Kiểm tra XML signature và signed JAR dùng trong quy trình tích hợp |

TLS exporter trong Java 25 được cung cấp qua `ExtendedSSLSession.exportKeyingMaterialData(...)` hoặc `exportKeyingMaterialKey(...)`. Đây là key material gắn với TLS session; không tự dùng exporter output làm password hoặc khóa ứng dụng mà thiếu protocol design, label/context separation và key lifecycle rõ ràng.

Với password PBE Unicode, Java 25 SunJCE chuyển sang UTF-8. Nếu encrypted key được tạo bởi provider hoặc implementation khác, hãy kiểm thử round-trip bằng cùng charset/algorithm parameters thay vì giả định mọi thư viện mã hóa password giống nhau. [JDK 25 Security Updates](https://docs.oracle.com/en/java/javase/25/migrate/security-updates.html) · [JDK 25 Release Notes](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html)

## 18. Thay đổi từ JDK 26 đến JDK 27

Khi JDK 25 được dùng làm mốc, các thay đổi tiếp theo có thể tác động trực tiếp tới provider và TLS.

| Release | Thay đổi | Việc cần kiểm tra |
| --- | --- | --- |
| JDK 26 | Bổ sung `jdk.crypto.disabledAlgorithms` ở tầng JCE | Các Cipher/MessageDigest bị policy mới hạn chế có thể không tạo được |
| JDK 26 | SunX509 KeyManager bổ sung algorithm constraints và certificate checks | Kiểm tra ứng dụng dùng KeyManagerFactory algorithm SunX509 tùy chỉnh |
| JDK 27 | TLS 1.3 key agreement dùng key algorithm `Generic` cho shared secret | Provider JCE bên thứ ba phải hỗ trợ Generic keys; nếu không, handshake có thể báo “Could not generate secret” |
| JDK 27 | Hybrid key exchange TLS 1.3: X25519MLKEM768, SecP256r1MLKEM768, SecP384r1MLKEM1024 | Kiểm tra negotiated named group và tương thích với peer, proxy, HSM/provider |
| JDK 27 | ffdhe6144 và ffdhe8192 bị loại khỏi danh sách named groups mặc định | Chỉ thêm lại nếu hệ thống có yêu cầu tương thích cụ thể và đánh giá chi phí |
| JDK 27 | TLS 1.3 hỗ trợ certificate compression bằng zlib, mặc định bật | Kiểm tra middlebox/peer TLS nếu có lỗi tương thích |
| JDK 27 | Cú pháp javax.net.debug được kiểm tra nghiêm hơn | Sửa script debug dùng suboption thiếu parent |
| JDK 27 | Có jcmd VM.security_properties | Có thể kiểm tra security properties của process đang chạy |
| JDK 27 | Thêm property jdk.security.password.allowSystemIn | Có thể chặn công cụ đọc password từ stdin khi không có Console |

### Hybrid key exchange không phải certificate signature hậu lượng tử

Hybrid key exchange kết hợp thuật toán cổ điển với thuật toán kháng lượng tử để bảo vệ việc thỏa thuận session key. Nó không tự thay certificate chain, chữ ký số của certificate hoặc trust anchor thành hậu lượng tử. Cần lập kế hoạch riêng cho certificate/signature migration.

Trong JDK 27, `X25519MLKEM768` được ưu tiên mặc định nếu cả hai peer hỗ trợ. Có thể xác nhận nhóm đã thương lượng bằng JSSE handshake debug và kiểm tra `key_share` trong ServerHello.

### Custom provider và Generic secret key

Với SunJSSE, thay đổi TLS 1.3 key agreement sang Generic thường trong suốt. Nếu ứng dụng thay SunJCE bằng provider JCE khác, kiểm tra provider đó có hỗ trợ key algorithm Generic. Nếu không, TLS 1.3 handshake có thể thất bại với `SSLHandshakeException` và thông báo “Could not generate secret”.

Đây là lý do cần kiểm thử cả `SSLContext`, `KeyAgreement`, `SecretKeyFactory` và `Cipher` của provider trong luồng TLS thật. Không chỉ test riêng phép mã hóa AES của ứng dụng.

## 19. Debug TLS handshake mà không hạ bảo mật

Bật debug có mục tiêu trong môi trường test/staging:

~~~bash
java -Djavax.net.debug=ssl:handshake -jar app.jar
~~~

Option này giúp xem protocol version, extension, signature schemes, named groups, certificate chain và thông tin thương lượng. Trên JDK 27, các suboptions như `verbose`, `packet` hoặc `plaintext` phải đi cùng parent option hợp lệ; cấu hình sai có thể bị bỏ qua. Có thể xem danh sách hỗ trợ bằng:

~~~bash
java -Djavax.net.debug=help -version
~~~

Không bật `plaintext` trong production hoặc gửi TLS debug logs ra kênh không kiểm soát. Debug có thể làm lộ metadata, certificate, endpoint và chi tiết cấu hình; packet/plaintext tracing có rủi ro cao hơn.

### Điều cần tìm trong handshake

- ClientHello có offer TLS 1.3/TLS 1.2 đúng policy không?
- ServerHello chọn protocol và cipher suite nào?
- Signature scheme có bị loại bởi `jdk.tls.disabledAlgorithms` không?
- Named group có được hai bên hỗ trợ không?
- Certificate chain có được gửi đầy đủ và xác minh thành công không?
- Hostname/SAN có khớp không?
- Trust anchor hoặc intermediate nào khiến path validation thất bại?
- TLS 1.3 key agreement có lỗi khi dùng custom provider không?
- Peer có hỗ trợ hybrid group hoặc certificate compression không?

Nếu lỗi xảy ra trước certificate validation, tập trung vào protocol/cipher/signature/group/provider. Nếu lỗi sau khi nhận certificate, tập trung vào truststore, chain, algorithm constraints, hostname và revocation.

## 20. Security Manager đã bị vô hiệu hóa: kiểm tra phụ thuộc cũ

Từ JDK 24, Security Manager bị vô hiệu hóa vĩnh viễn. JDK 25 không thể bật nó lúc khởi động hoặc cài custom Security Manager lúc runtime. File system policy `java.policy` của hệ thống đã bị loại bỏ; các security/system properties chỉ phục vụ Security Manager bị bỏ qua.

Vì vậy, khi nâng từ ứng dụng cũ, tìm các phụ thuộc sau:

- Khởi chạy JVM với `-Djava.security.manager` hoặc giá trị tương tự.
- Gọi `System.setSecurityManager(...)`.
- Dựa vào `SecurityManager.checkPermission` để sandbox plugin.
- Dùng `AccessController.doPrivileged` như một ranh giới bảo mật.
- Phân quyền file/network bằng policy file `java.policy`.

Các API liên quan có thể trả về null/false, thực thi action trực tiếp hoặc ném exception tùy method. `doPrivileged` không còn cung cấp ranh giới cấp quyền như trước. Thay thế bằng isolation ở OS/container, process boundary, service identity, filesystem/network permissions, secret isolation và sandbox chuyên dụng nếu ứng dụng chạy code không tin cậy.

Đây là kiểm tra tương thích bắt buộc cho hệ thống nâng từ các JDK cũ; không xây dựng thiết kế mới dựa trên Security Manager. [Security Manager Is Permanently Disabled](https://docs.oracle.com/en/java/javase/25/security/security-manager-is-permanently-disabled.html)

## 21. Quy trình kiểm tra provider, TLS và certificate trước rollout

Thực hiện theo từng bước trên cùng artifact ứng dụng và môi trường staging gần production.

### Bước 1 — Lập baseline runtime

Ghi lại:

- JDK vendor, full version, build và VM name.
- OS, CPU architecture và container image digest.
- Provider list và provider order.
- Security properties quan trọng.
- Keystore/truststore type, file checksum, aliases và certificate fingerprints.
- Các system properties JSSE và JVM flags liên quan.

### Bước 2 — Kiểm tra provider services

- Chạy inventory provider.
- Tạo Cipher, Signature, KeyFactory, SSLContext và TrustManagerFactory thực tế.
- Ghi provider trả về từ mỗi engine.
- Kiểm tra PKCS#11/HSM slot, login, mechanisms và key attributes.
- Nếu pin provider, xác nhận provider đó có đầy đủ services trong luồng thực.

### Bước 3 — So sánh security properties

So sánh ít nhất:

- `security.provider.n`
- `jdk.tls.disabledAlgorithms`
- `jdk.tls.legacyAlgorithms`
- `jdk.certpath.disabledAlgorithms`
- `jdk.crypto.disabledAlgorithms` nếu JDK mục tiêu hỗ trợ
- `jdk.security.caDistrustPolicies`
- Các property OCSP/CRL và TLS custom mà ứng dụng đang dùng.

Lưu giá trị thực tế từ process, không chỉ lưu file cấu hình dự kiến.

### Bước 4 — Kiểm tra certificate material

- So sánh truststore và cacerts aliases/fingerprints.
- Kiểm tra expiry, SAN, EKU, KeyUsage, issuer/subject, signature algorithm và key size.
- Xác minh chain từ endpoint thật.
- Kiểm tra OCSP/CRL nếu policy bật.
- Xác minh fingerprint ngoài băng trước khi import CA.
- Đánh giá thay đổi trust/distrust trong từng JDK update.

### Bước 5 — Kiểm tra TLS handshake

- Test TLS 1.3 và TLS 1.2 theo policy.
- Xác minh hostname.
- Ghi protocol, cipher suite, peer principal và named group.
- Test mutual TLS nếu có.
- Test các endpoint nội bộ, đối tác, proxy và load balancer.
- Với JDK 27, kiểm tra hybrid key exchange và custom provider Generic key support.

### Bước 6 — Chạy security regression

- Ký/xác minh dữ liệu bằng provider mục tiêu.
- Mã hóa/giải mã dữ liệu mẫu theo thuật toán đang dùng.
- Đọc keystore và private key bằng đúng provider.
- Kiểm tra TLS fail-closed khi certificate sai hostname, hết hạn, không trusted hoặc dùng thuật toán bị cấm.
- Kiểm tra signed JAR/XML signature nếu hệ thống dùng các chức năng này.
- Xác nhận log không chứa password, private key hoặc secret material.

### Bước 7 — Canary và rollback

Triển khai trên một nhóm instance nhỏ. Theo dõi TLS handshake failure rate, certificate path errors, provider exceptions, latency handshake, lỗi OCSP/CRL và tỷ lệ kết nối tới các hệ thống đối tác. Có thể quay lại JDK build trước nếu phát hiện regression, nhưng không giữ runtime có lỗ hổng đã được vá chỉ để tránh lỗi tương thích; cần cập nhật peer/configuration hoặc provider.

## 22. Các lỗi thường gặp khi nâng cấp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| `NoSuchAlgorithmException` | Provider không có service/algorithm hoặc bị policy hạn chế | Kiểm tra provider inventory, service và disabled algorithms |
| `NoSuchProviderException` | Code pin provider không tồn tại trong vendor/build mới | Xác minh provider list; cân nhắc provider selection mặc định |
| TLS handshake fails với handshake signature | Peer chỉ hỗ trợ SHA-1 TLS 1.2 signature hoặc signature scheme không còn được phép | Kiểm tra jdk.tls.disabledAlgorithms và nâng peer |
| `PKIX path building failed` | Thiếu intermediate/trust anchor, chain không đúng hoặc CA bị distrust | Xem certpath debug, truststore và certificate chain |
| `No subject alternative DNS name matching` | Hostname không có trong SAN hoặc endpoint identity sai | Cấp certificate đúng SAN, giữ hostname verification |
| TLS 1.3 báo “Could not generate secret” | Custom JCE provider không hỗ trợ Generic key algorithm trên JDK 27 | Cập nhật provider hoặc dùng build đã hỗ trợ; kiểm thử lại TLS 1.3 |
| TLS 1.3 không chọn hybrid group | Peer hoặc middlebox không hỗ trợ named group | Kiểm tra ServerHello key_share và network middleboxes |
| Import certificate thành công nhưng TLS vẫn lỗi | Import nhầm leaf cert, sai truststore hoặc path policy vẫn chặn | Kiểm tra store thực tế mà process nạp và chain validation |
| Provider PKCS#11 không thấy key | Sai slot/token/login, mechanism hoặc key attributes | Kiểm tra native library, token configuration và provider logs |
| Password prompt thất bại trong pipeline | stdin bị redirect, không có console hoặc JDK 27 password stdin policy | Kiểm tra jdk.security.password.allowSystemIn và secret input method |
| TLS debug option không có tác dụng | Cú pháp javax.net.debug không đúng quan hệ parent/suboption | Xem javax.net.debug=help trên JDK đang chạy |
| Security properties không đổi dù gọi setProperty | Property đã được đọc/cache trước đó | Cấu hình ở startup và xác minh giá trị cuối cùng |

## 23. Bài thực hành: kiểm tra một ứng dụng trước khi nâng từ Java 25 lên JDK 27

### Bối cảnh

Một dịch vụ Spring Boot dùng SunJSSE mặc định, có một provider PKCS#11 để truy cập HSM, truststore nội bộ và kết nối tới một số HTTPS endpoints. Nhóm chuẩn bị chuyển runtime từ JDK 25 sang JDK 27.

### Nhiệm vụ

1. Ghi lại Java vendor, full build, VM, OS và CPU của JDK 25 hiện tại.
2. Xuất provider list, provider order và các service cần dùng.
3. Ghi giá trị security properties đang có hiệu lực trên process.
4. Liệt kê truststore/cacerts và lưu fingerprint của các CA liên quan.
5. Kiểm tra certificate chain, SAN, EKU, expiry, algorithm constraints và revocation.
6. Chạy TLS probe cho từng endpoint và lưu protocol, cipher suite, peer principal.
7. Chạy cùng bộ test với JDK 27.0.1.1 hoặc bản CPU mới hơn của vendor mục tiêu.
8. Kiểm tra thay đổi CA truststore, đặc biệt các root/intermediate đã bị distrust.
9. Kiểm tra custom JCE provider có hỗ trợ Generic key algorithm cho TLS 1.3.
10. Xác nhận TLS hybrid key exchange khi peer hỗ trợ, đồng thời giữ test tương thích với peer chưa hỗ trợ.
11. Kiểm tra security properties mới như jdk.crypto.disabledAlgorithms và jdk.security.password.allowSystemIn.
12. Xác minh ứng dụng không còn phụ thuộc Security Manager hoặc java.policy.
13. So sánh handshake failures, provider exceptions, certpath errors, latency và CPU.
14. Viết quyết định rollout/rollback cùng các thay đổi cần thực hiện ở peer hoặc provider.

### Câu hỏi tự đánh giá

1. Vì sao provider đã đăng ký không chứng minh provider đó được dùng trong operation?
2. Provider order được điều khiển bởi security property nào?
3. Khi nào ứng dụng nên pin provider và khi nào nên để JCA tự chọn?
4. System property và security property khác nhau ở API đọc/ghi nào?
5. Dùng một dấu bằng và hai dấu bằng trong java.security.properties khác nhau ra sao?
6. jdk.tls.disabledAlgorithms và jdk.certpath.disabledAlgorithms kiểm soát những lớp nào?
7. JDK 26 bổ sung property nào để hạn chế JCE algorithms?
8. Vì sao JDK 25 có thể từ chối SHA-1 TLS 1.2 handshake dù certificate vẫn parse được?
9. Vì sao certificate chain hợp lệ vẫn có thể không khớp hostname?
10. Tại sao phải so sánh truststore khi nâng JDK update?
11. TLS hybrid key exchange bảo vệ phần nào của kết nối và không thay thế phần nào?
12. Vì sao custom provider có thể làm TLS 1.3 thất bại trên JDK 27?
13. JDK 27 có lệnh jcmd nào để xem active security properties?
14. Vì sao Security Manager không còn là sandbox khả dụng trong Java 25?

## 24. Checklist quyết định rollout

- [ ] Đã xác nhận đúng JDK vendor, full version và security baseline.
- [ ] Đã ghi provider list, provider order và provider thực sự được chọn.
- [ ] Các provider tùy chỉnh có version/build tương thích với JDK mục tiêu.
- [ ] PKCS#11/HSM token, native library và mechanism đã được kiểm tra.
- [ ] Đã ghi active security properties từ process.
- [ ] Không dùng nhầm System.setProperty để sửa Java security properties.
- [ ] Không thay toàn bộ java.security master file nếu không quản lý đủ provider và policy.
- [ ] Đã so sánh TLS, CertPath và JCE disabled algorithms.
- [ ] Đã kiểm tra TLS 1.2/1.3, cipher suite, signature schemes và named groups.
- [ ] Hostname verification vẫn được bật.
- [ ] Certificate chain, SAN, EKU, KeyUsage, validity và trust anchors hợp lệ.
- [ ] Truststore được so sánh theo alias/fingerprint giữa JDK cũ và mới.
- [ ] OCSP/CRL hoạt động và timeout/size limits phù hợp.
- [ ] Custom JCE provider hỗ trợ Generic key nếu dùng TLS 1.3 trên JDK 27.
- [ ] Đã kiểm tra hybrid key exchange khi peer hỗ trợ.
- [ ] Không còn phụ thuộc Security Manager hoặc java.policy.
- [ ] Không để password/private key xuất hiện trong command line hoặc logs.
- [ ] TLS debug chỉ bật có kiểm soát trong môi trường phù hợp.
- [ ] Có regression tests, canary metrics và rollback plan.
- [ ] Đã kiểm tra lại sau mỗi JDK CPU update và thay đổi provider.

**Tiêu chí hoàn thành:** người học có thể xác định provider và security properties thực sự được nạp, chứng minh TLS handshake và certificate validation hoạt động theo policy, giải thích những thay đổi có ảnh hưởng giữa Java 25 và JDK 27, và lập kế hoạch nâng cấp có test, canary cùng rollback. Các mặc định bảo mật hiện hành cần được giữ và kiểm thử; ngoại lệ chỉ được thêm khi có lý do, phạm vi và thời hạn rõ ràng.

## 25. Tài liệu chính thức

- [Oracle JDK 25 — Security Updates](https://docs.oracle.com/en/java/javase/25/migrate/security-updates.html): thay đổi provider, SHAKE, HKDF, TLS exporters và SHA-1 handshake restrictions.
- [Oracle JDK 25 — JDK Providers Documentation](https://docs.oracle.com/en/java/javase/25/security/oracle-providers.html): provider architecture, provider order và services của JDK.
- [Oracle JDK 25 — The Security Properties File](https://docs.oracle.com/en/java/javase/25/security/security-properties-file.html): master file, include, override và kiểm tra property đang hiệu lực.
- [Oracle JDK 25 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html): TLS, SSLContext, key/trust managers, exporters và algorithm restrictions.
- [Java SE 25 — SSLParameters](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLParameters.html): protocol, endpoint identification, named groups và signature schemes.
- [Java SE 25 — ExtendedSSLSession](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/ExtendedSSLSession.html): TLS keying material exporters.
- [Oracle JDK 25 — keytool Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/keytool.html): kiểm tra, import, export và quản lý keystore/certificate.
- [Oracle JDK 25 — Security Manager Is Permanently Disabled](https://docs.oracle.com/en/java/javase/25/security/security-manager-is-permanently-disabled.html): tác động của JEP 486.
- [Oracle JDK 26 — Security Updates](https://docs.oracle.com/en/java/javase/26/migrate/security-updates.html): property jdk.crypto.disabledAlgorithms và các thay đổi JDK 26.
- [Oracle JDK 27 — Security Updates](https://docs.oracle.com/en/java/javase/27/migrate/security-updates.html): cập nhật provider, TLS, certificate, CRL và security properties.
- [Oracle JDK 27 — Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): hybrid key exchange, Generic key algorithm và TLS changes.
- [Oracle JDK 27 — Consolidated Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html): security baseline, CA additions/removals và update-specific security fixes.

Khi áp dụng cho vendor khác Oracle, đối chiếu tài liệu provider, truststore và security properties của đúng bản phân phối. Security defaults, provider availability và certificate roots có thể khác nhau dù cùng major JDK release.
