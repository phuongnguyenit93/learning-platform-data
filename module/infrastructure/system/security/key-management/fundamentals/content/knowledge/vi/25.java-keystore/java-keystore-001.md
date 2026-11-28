# KeyStore trong Java

**Java KeyStore** là API và mô hình lưu trữ mà Java cung cấp để quản lý các đối tượng mật mã như private key, secret key, certificate và certificate chain. Ứng dụng có thể tra cứu entry theo alias, nạp hoặc lưu một kho khóa, lấy khóa khi được phép và cung cấp certificate cho các thành phần TLS hoặc chữ ký số.

java.security.KeyStore là lớp API chuẩn của Java Cryptography Architecture (JCA). Nó không đồng nghĩa với một định dạng file duy nhất. Một KeyStore có thể được triển khai bởi provider đọc file PKCS#12/JKS, tích hợp kho chứng thư của hệ điều hành hoặc giao tiếp với HSM qua PKCS#11. Vì vậy, khi thiết kế cần xác định cả loại keystore, provider và nơi vật liệu khóa thực sự được lưu.

Bài học thuộc phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS** và chương **Java KeyStore**. Nội dung kết nối API Java với vòng đời khóa mật mã: tạo, cấp phát, lưu trữ, sử dụng, backup, xoay vòng, thu hồi và hủy; đồng thời xét mật mã đối xứng, bất đối xứng, chữ ký số, certificate/PKI, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

## 1. Vì sao Java cần KeyStore?

Ứng dụng Java có thể cần private key để chứng minh danh tính trong TLS, secret key để mã hóa dữ liệu hoặc certificate để xác minh đối tác. Nếu khóa được đặt trực tiếp trong source code, file cấu hình hoặc tài nguyên đóng gói cùng ứng dụng, rất khó kiểm soát việc phân phối, quyền sử dụng, backup và thay thế khóa.

KeyStore tạo ra một giao diện có cấu trúc để ứng dụng:

- Lưu các key entry và certificate entry dưới những alias có thể tra cứu.
- Đọc certificate và certificate chain mà không cần tự phân tích định dạng file.
- Lấy private key hoặc secret key theo cơ chế bảo vệ của provider.
- Thêm, thay thế hoặc xóa entry khi được cấp quyền.
- Nạp và lưu kho khóa thông qua API thống nhất.
- Tích hợp với KeyManagerFactory, TrustManagerFactory, TLS và các API mật mã khác.

Ví dụ, một Java HTTPS server cần certificate để gửi danh tính và private key để ký phần handshake. Ứng dụng có thể dùng KeyStore để cung cấp cặp thông tin này cho JSSE. Nếu private key nằm trong HSM, Java có thể nhận một key object hoặc handle do provider cung cấp và yêu cầu HSM ký mà không xuất private key dạng rõ.

KeyStore giúp quản lý và truy cập entry; nó không tự động tạo ra toàn bộ chính sách quản trị khóa. Việc xác minh danh tính, phân quyền, backup, rotation, audit và destruction vẫn cần được thiết kế cùng provider và hệ thống vận hành.

## 2. KeyStore nằm ở đâu trong JCA?

Java Cryptography Architecture (JCA) định nghĩa các API mật mã và cơ chế provider. Ứng dụng gọi API chuẩn; provider cung cấp phần triển khai cụ thể.

Với KeyStore, các thành phần chính là:

| Thành phần | Vai trò |
|---|---|
| KeyStore | API thao tác với kho khóa và các entry. |
| Provider | Triển khai một loại keystore hoặc kết nối đến backend cụ thể. |
| KeyStoreSpi | Giao diện triển khai phía provider cho các thao tác của KeyStore. |
| ProtectionParameter | Cung cấp cơ chế bảo vệ khi đọc hoặc ghi entry. |
| KeyManagerFactory | Tạo key manager dùng private key/certificate trong TLS. |
| TrustManagerFactory | Tạo trust manager dùng certificate đáng tin để xác minh đối tác. |

Luồng tổng quát:

~~~mermaid
flowchart TD
    A["Ứng dụng Java"] --> B["KeyStore API"]
    B --> C["JCA Provider"]
    C --> D["PKCS12 / JKS file"]
    C --> E["OS Certificate Store"]
    C --> F["PKCS11 Provider"]
    F --> G["HSM / Token"]
    B --> H["Key / Certificate Entry"]
~~~

Ứng dụng có thể gọi KeyStore.getInstance("PKCS12") mà không cần tự viết bộ đọc PKCS#12. Provider được Java lựa chọn theo loại và cấu hình bảo mật. Khi cần provider cụ thể, ứng dụng có thể truyền đối tượng Provider hoặc tên provider vào getInstance.

## 3. Các loại entry trong KeyStore

Java định nghĩa ba loại entry phổ biến:

| Entry | Nội dung | Mục đích |
|---|---|---|
| PrivateKeyEntry | Private key cùng certificate chain tương ứng | TLS, ký số và xác thực danh tính. |
| SecretKeyEntry | Secret key như AES hoặc HMAC key | Mã hóa, giải mã hoặc tạo/kiểm tra MAC. |
| TrustedCertificateEntry | Một certificate công khai được lưu làm certificate đáng tin | Trust anchor hoặc certificate phục vụ xác minh. |

PrivateKeyEntry thường cần một certificate chain. Phần tử đầu tiên là certificate của chủ thể gắn với private key; các phần tử tiếp theo là certificate CA cấp trên cần thiết để xây dựng đường dẫn tin cậy. Chain không nhất thiết chứa root certificate nếu root đã có trong trust store của bên kiểm tra.

TrustedCertificateEntry chỉ chứa certificate, không có private key. Việc thêm một certificate vào trust store thể hiện quyết định tin cậy của ứng dụng hoặc tổ chức; phải xác minh nguồn gốc certificate trước khi thêm.

Khả năng lưu SecretKeyEntry phụ thuộc loại keystore và provider. Không phải mọi định dạng đều hỗ trợ mọi loại entry. Ví dụ, HSM có thể giới hạn thuật toán, thuộc tính exportability hoặc thao tác theo policy thiết bị.

## 4. Các loại KeyStore và provider

Loại keystore xác định cách dữ liệu được lưu hoặc cách Java kết nối đến backend:

| Type | Mô tả | Lưu ý |
|---|---|---|
| PKCS12 | Container tiêu chuẩn có thể chứa private key, certificate và chain | Thường là lựa chọn phù hợp cho triển khai mới và trao đổi giữa nền tảng. |
| JKS | Định dạng Java KeyStore lịch sử | Thường gặp trong hệ thống Java cũ; cân nhắc chuyển sang PKCS12 khi phù hợp. |
| JCEKS | Định dạng Java cũ có hỗ trợ secret key entry | Kiểm tra yêu cầu tương thích và chính sách của runtime/provider. |
| PKCS11 | Giao diện đến token/HSM thông qua provider PKCS11 | Không nhất thiết là file; việc load/store phụ thuộc thiết bị và provider. |
| Windows-MY, Windows-ROOT | Tích hợp kho certificate Windows qua provider tương ứng | Phụ thuộc hệ điều hành, tài khoản và quyền truy cập. |
| KeychainStore | Tích hợp Keychain trên một số runtime/nền tảng Apple | Phụ thuộc provider và môi trường chạy. |

JDK 9 trở lên thường đặt PKCS12 làm loại keystore mặc định, nhưng thuộc tính keystore.type có thể được cấu hình lại. Do đó, nên chỉ định rõ type thay vì phụ thuộc KeyStore.getDefaultType() trong ứng dụng cần hành vi nhất quán.

Định dạng và provider là hai khái niệm riêng. PKCS12 nói về định dạng container; provider quyết định cách Java triển khai API cho định dạng đó. PKCS11 thường chỉ một giao diện tới thiết bị hoặc token mật mã, không phải file PKCS11 để sao chép qua filesystem.

## 5. Tạo một KeyStore instance

Lấy instance theo type:

~~~java
import java.security.KeyStore;

KeyStore keyStore = KeyStore.getInstance("PKCS12");
~~~

Nếu cần chọn provider cụ thể:

~~~java
KeyStore keyStore = KeyStore.getInstance("PKCS12", "SUN");
~~~

Tên provider phải tồn tại trong runtime và hỗ trợ type được yêu cầu. Không nên hardcode tên provider một cách tùy tiện giữa các nền tảng; hãy kiểm tra môi trường triển khai và tài liệu JDK/provider.

Có thể liệt kê provider hỗ trợ một service/type bằng Security.getProviders() và kiểm tra Provider.getServices(). Khi không tìm thấy provider phù hợp, getInstance có thể ném NoSuchAlgorithmException hoặc NoSuchProviderException tùy overload.

## 6. Nạp KeyStore từ file

Để mở keystore hiện có, tạo instance rồi gọi load với input stream và mật khẩu:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;

Path path = Path.of("config", "service-identity.p12");
char[] storePassword = passwordProvider.getStorePassword();

KeyStore keyStore = KeyStore.getInstance("PKCS12");
try {
    try (InputStream input = Files.newInputStream(path)) {
        keyStore.load(input, storePassword);
    }
    // Chỉ sử dụng entry sau khi load thành công.
} finally {
    java.util.Arrays.fill(storePassword, '\0');
}
~~~

passwordProvider trong ví dụ đại diện cho thành phần lấy bí mật từ secret manager hoặc cơ chế xác thực được quản lý. Đây không phải API Java có sẵn. Không ghi mật khẩu trực tiếp trong source code, repository, command line hoặc log.

load có thể thất bại do file không tồn tại, định dạng không đúng, mật khẩu sai, dữ liệu bị hỏng hoặc provider không hỗ trợ thao tác. Ứng dụng cần phân loại lỗi và không tiếp tục như thể keystore đã được nạp thành công.

Đóng InputStream sau khi load là cần thiết. KeyStore không giữ trách nhiệm đóng stream mà caller cung cấp.

## 7. Tạo một KeyStore rỗng

Với các loại keystore dạng file, có thể tạo store rỗng bằng cách gọi load(null, password). Sau đó thêm entry rồi ghi ra file bằng store.

~~~java
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.KeyStore;
import java.util.Arrays;

Path path = Path.of("config", "trusted-cas.p12");
char[] password = passwordProvider.getStorePassword();

try {
    KeyStore trustStore = KeyStore.getInstance("PKCS12");
    trustStore.load(null, password);

    // Thêm TrustedCertificateEntry trước khi lưu.
    try (OutputStream output = Files.newOutputStream(
            path, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
        trustStore.store(output, password);
    }
} finally {
    Arrays.fill(password, '\0');
}
~~~

CREATE_NEW giúp ví dụ không ghi đè một file đã tồn tại. Trong quy trình cập nhật store đang được sử dụng, nên ghi ra file tạm có quyền truy cập chặt, xác minh kết quả rồi thay thế theo cơ chế atomic move khi filesystem hỗ trợ. Không ghi trực tiếp lên file production đang được tiến trình khác sử dụng nếu chưa có kế hoạch đồng bộ và rollback.

Đối với HSM/PKCS11, load(null, pin) thường được dùng để đăng nhập hoặc mở phiên làm việc với token. Ý nghĩa cụ thể tùy provider. Không được suy luận rằng mọi provider đều tạo một keystore file rỗng khi truyền null.

## 8. Đọc alias và kiểm tra loại entry

Sau khi nạp thành công, có thể kiểm tra entry:

~~~java
if (keyStore.containsAlias("api-signing")) {
    boolean keyEntry = keyStore.isKeyEntry("api-signing");
    boolean certificateEntry = keyStore.isCertificateEntry("api-signing");
}
~~~

Các phương thức hữu ích:

| Phương thức | Kết quả |
|---|---|
| aliases() | Enumeration các alias trong store. |
| containsAlias(alias) | Kiểm tra alias có tồn tại. |
| size() | Số entry. |
| isKeyEntry(alias) | Kiểm tra alias là key entry. |
| isCertificateEntry(alias) | Kiểm tra alias là trusted certificate entry. |
| entryInstanceOf(alias, type) | Kiểm tra entry có thuộc loại cụ thể. |
| getCertificate(alias) | Lấy certificate gắn với alias nếu có. |
| getCertificateChain(alias) | Lấy certificate chain của key entry nếu có. |
| getCertificateAlias(cert) | Tìm alias chứa certificate tương ứng. |

Alias là định danh trong phạm vi một keystore/provider. Cùng một alias ở hai file hoặc hai HSM khác nhau có thể trỏ đến hai khóa hoàn toàn khác nhau. Hệ thống cần quản lý cả type, provider, môi trường, key ID và version; không dùng alias đơn lẻ làm định danh toàn cục.

## 9. Lấy private key và certificate

Đối với PrivateKeyEntry, ứng dụng có thể lấy private key bằng getKey và certificate bằng getCertificate:

~~~java
import java.security.Key;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;

String alias = "https-api";
char[] entryPassword = passwordProvider.getEntryPassword(alias);

try {
    if (!keyStore.containsAlias(alias) || !keyStore.isKeyEntry(alias)) {
        throw new IllegalStateException("Private key entry is unavailable");
    }

    Key key = keyStore.getKey(alias, entryPassword);
    if (!(key instanceof PrivateKey privateKey)) {
        throw new IllegalStateException("Entry does not contain a private key");
    }

    Certificate certificate = keyStore.getCertificate(alias);
    if (!(certificate instanceof X509Certificate x509)) {
        throw new IllegalStateException("X.509 certificate is unavailable");
    }

    Certificate[] chain = keyStore.getCertificateChain(alias);

    System.out.println("Key algorithm: " + privateKey.getAlgorithm());
    System.out.println("Subject: " + x509.getSubjectX500Principal());
    System.out.println("Chain length: " + (chain == null ? 0 : chain.length));
} finally {
    java.util.Arrays.fill(entryPassword, '\0');
}
~~~

Không gọi privateKey.getEncoded() chỉ để kiểm tra khóa và không in private key ra log. Với key object từ HSM, getEncoded() thường trả về null nếu khóa không exportable; ứng dụng nên dùng object đó trực tiếp qua Signature, Cipher hoặc API tương ứng mà provider hỗ trợ.

getCertificateChain(alias) có thể trả về null nếu alias không phải private key entry hoặc không có chain. Với certificate chain hợp lệ, phần tử đầu tiên thường là certificate của subject, sau đó là các issuer certificate theo thứ tự xây dựng chain.

## 10. Sử dụng Entry API và ProtectionParameter

Ngoài getKey, Java có API tổng quát getEntry và setEntry. API này làm rõ loại entry và cơ chế bảo vệ:

~~~java
KeyStore.ProtectionParameter protection =
        new KeyStore.PasswordProtection(entryPassword);

try {
    KeyStore.Entry entry = keyStore.getEntry(alias, protection);

    if (entry instanceof KeyStore.PrivateKeyEntry privateEntry) {
        PrivateKey privateKey = privateEntry.getPrivateKey();
        Certificate[] chain = privateEntry.getCertificateChain();
        // Sử dụng key object; không export vật liệu khóa.
    }
} finally {
    ((KeyStore.PasswordProtection) protection).destroy();
    java.util.Arrays.fill(entryPassword, '\0');
}
~~~

PasswordProtection là một implementation của ProtectionParameter dùng mật khẩu để bảo vệ entry. Provider có thể hỗ trợ thêm cơ chế bảo vệ khác, ví dụ callback hoặc xác thực token. Cần kiểm tra tài liệu provider và semantics của từng loại store.

Đoạn mã trên là phần thân của một phương thức có khai báo xử lý ngoại lệ phù hợp, vì destroy() có thể ném DestroyFailedException. Trong ứng dụng thật, phải bảo đảm việc xóa mật khẩu vẫn được thử thực hiện ngay cả khi thao tác lấy entry thất bại.

Mật khẩu store và mật khẩu entry không phải lúc nào cũng có thể tách biệt theo cùng một cách. Một số định dạng/provider hỗ trợ mật khẩu riêng cho từng private key entry; một số triển khai PKCS12 yêu cầu hoặc xử lý mật khẩu entry theo quy tắc riêng. Không giả định hành vi giống nhau giữa JKS, PKCS12 và HSM.

## 11. Thêm certificate đáng tin cậy

setCertificateEntry thêm một certificate entry không chứa private key. Đây là thao tác thường dùng để xây dựng trust store:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;

Path certificatePath = Path.of("config", "organization-root-ca.cer");
CertificateFactory factory = CertificateFactory.getInstance("X.509");
Certificate rootCertificate;

try (InputStream input = Files.newInputStream(certificatePath)) {
    rootCertificate = factory.generateCertificate(input);
}

keyStore.setCertificateEntry("organization-root-ca", rootCertificate);
~~~

Thêm certificate vào trust store là quyết định tin cậy. Trước khi thêm, cần xác minh fingerprint, nguồn phân phối, subject, issuer, Basic Constraints, Key Usage và chính sách CA. Không tự động tin mọi certificate được tải từ một endpoint hoặc đính kèm trong email.

## 12. Thêm private key cùng certificate chain

setKeyEntry lưu một private key cùng certificate chain:

~~~java
keyStore.setKeyEntry(
        "service-tls",
        privateKey,
        entryPassword,
        certificateChain);
~~~

Trong đó:

- privateKey là private key phù hợp với public key trong certificate đầu tiên.
- entryPassword là mật khẩu bảo vệ entry theo semantics của provider.
- certificateChain là chain bắt đầu bằng certificate của private key, sau đó là certificate issuer theo thứ tự.

Phải xác minh private key tương ứng với public key trong leaf certificate. Một cách kiểm tra là ký một challenge ngẫu nhiên bằng private key rồi xác minh chữ ký bằng public key trong certificate, dùng thuật toán và padding phù hợp. Không nên dựa vào việc alias có tồn tại hoặc thuật toán trùng nhau để kết luận hai khóa là một cặp.

Với private key non-exportable trong HSM, không nhất thiết có thể gọi setKeyEntry để sao chép khóa sang một file keystore. Ứng dụng cần dùng provider/handle mà HSM cung cấp và giữ key object trong backend được quản lý.

## 13. Lưu KeyStore ra file

Sau khi thay đổi entry, store ghi nội dung keystore ra OutputStream:

~~~java
try (OutputStream output = Files.newOutputStream(
        targetPath,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE)) {
    keyStore.store(output, storePassword);
}
~~~

Đối với file có private key hoặc secret key, cần:

- Giới hạn quyền đọc/ghi theo service identity và quản trị viên được ủy quyền.
- Không đặt file trong thư mục public, web root, artifact công khai hoặc repository.
- Bảo vệ thiết bị lưu trữ và bản backup.
- Không lưu mật khẩu cạnh file với cùng quyền truy cập.
- Ghi file tạm trong cùng filesystem, kiểm tra store sau khi ghi rồi thay thế theo cách atomic khi cập nhật.
- Giữ audit về người thay đổi và lý do thay đổi, không ghi mật khẩu hoặc vật liệu khóa.

store chỉ chứng minh provider đã ghi dữ liệu theo giao diện. Nó không tự chứng minh file đã được backup an toàn, quyền truy cập đúng hoặc bản sao cũ đã bị xóa.

## 14. KeyStore và TrustStore trong TLS

Trong Java Secure Socket Extension (JSSE), hai kho thường được dùng theo hai mục đích:

- KeyStore chứa private key và certificate của chính ứng dụng khi cần xác thực danh tính.
- TrustStore chứa certificate/trust anchor dùng để xác minh certificate của đối tác.

KeyManagerFactory đọc key entries để chọn danh tính TLS. TrustManagerFactory đọc trusted certificates để xây dựng chính sách xác minh certificate.

~~~mermaid
flowchart TD
    A["SSLContext"] --> B["KeyManagerFactory"]
    A --> C["TrustManagerFactory"]
    B --> D["KeyStore: private key + certificate"]
    C --> E["TrustStore: trusted CA certificates"]
    D --> F["Xác thực danh tính của ứng dụng"]
    E --> G["Xác minh danh tính đối tác"]
~~~

Một ứng dụng TLS server thường cần KeyStore để chứng minh danh tính server. Một TLS client thường cần TrustStore để xác minh server. Với mutual TLS, cả hai phía có thể cần key entry của chính mình và trust anchors để xác minh certificate của bên kia.

Không tắt hostname verification hoặc cài trust-all TrustManager để bỏ qua lỗi certificate. Nếu kết nối thất bại, hãy kiểm tra hostname/SAN, chain, thời hạn, trust anchor, trạng thái revocation và cấu hình provider.

## 15. Ví dụ cấu hình SSLContext

Đoạn mã sau minh họa cách nạp identity store và trust store cho JSSE. Các biến đường dẫn và mật khẩu được cung cấp từ cấu hình/secret manager của ứng dụng:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

KeyStore identityStore = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(identityPath)) {
    identityStore.load(input, identityStorePassword);
}

KeyManagerFactory keyManagers = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
keyManagers.init(identityStore, identityEntryPassword);

KeyStore trustStore = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(trustPath)) {
    trustStore.load(input, trustStorePassword);
}

TrustManagerFactory trustManagers = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
trustManagers.init(trustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(
        keyManagers.getKeyManagers(),
        trustManagers.getTrustManagers(),
        null);
~~~

Đây là phần cấu hình nền tảng. Khi dùng SSLSocket hoặc SSLEngine, ứng dụng vẫn phải xác minh hostname theo đúng API/giao thức và đặt protocol/cipher policy phù hợp. Nếu client không cần certificate riêng, có thể không truyền key manager; với mutual TLS thì cần cấu hình identity entry tương ứng.

## 16. Dùng KeyStore với HSM qua PKCS#11

PKCS#11 là giao diện chuẩn để ứng dụng truy cập token mật mã như HSM. Trên một số JDK, provider SunPKCS11 có thể được cấu hình để kết nối thư viện PKCS#11 của thiết bị.

Ví dụ cấu hình provider có dạng:

~~~text
name = OrganizationHSM
library = /path/to/vendor-pkcs11-library
slotListIndex = 0
~~~

Ứng dụng có thể cấu hình provider rồi lấy KeyStore type PKCS11:

~~~java
import java.security.KeyStore;
import java.security.Provider;
import java.security.Security;

Provider base = Security.getProvider("SunPKCS11");
if (base == null) {
    throw new IllegalStateException("SunPKCS11 provider is unavailable");
}

Provider hsmProvider = base.configure("/etc/security/hsm-pkcs11.cfg");
Security.addProvider(hsmProvider);

KeyStore hsmKeyStore = KeyStore.getInstance("PKCS11", hsmProvider);
char[] userPin = pinProvider.getPin();
try {
    hsmKeyStore.load(null, userPin);
    // Tra cứu alias và sử dụng key object do provider trả về.
} finally {
    java.util.Arrays.fill(userPin, '\0');
}
~~~

Đường dẫn thư viện, slot, login role, PIN và thuật toán phải theo tài liệu HSM/provider thực tế. SunPKCS11 không có sẵn hoặc không hoạt động giống nhau trên mọi runtime; module hỗ trợ PKCS#11 phải có mặt và provider cần được cấu hình đúng.

Với token/HSM, load(null, pin) thường khởi tạo phiên hoặc đăng nhập vào token. store có thể không được hỗ trợ như cách ghi một file PKCS12. Việc tạo, backup, clone, restore và xóa khóa phải theo API và quy trình chính thức của thiết bị.

## 17. Bảo vệ mật khẩu và vật liệu khóa

Mật khẩu keystore bảo vệ container hoặc entry theo định dạng/provider. Nó không thay thế quyền filesystem, kiểm soát danh tính hay bảo vệ tiến trình đang sử dụng khóa.

Các nguyên tắc cần áp dụng:

- Lấy password/PIN từ secret manager hoặc cơ chế xác thực được kiểm soát.
- Dùng char[] khi API hỗ trợ và xóa mảng do ứng dụng sở hữu sau khi dùng.
- Không hardcode password, PIN hoặc passphrase trong source code.
- Không truyền secret trong command-line argument vì có thể xuất hiện trong process listing hoặc log.
- Không in PrivateKey, SecretKey, encoded bytes hoặc nội dung PKCS12 ra log.
- Hạn chế quyền đọc file keystore và quyền gọi thao tác ký/giải mã.
- Tách quyền quản trị keystore khỏi quyền sử dụng khóa trong ứng dụng.
- Cân nhắc HSM/KMS cho private key quan trọng và khóa không cần export.

Xóa mảng char[] chỉ làm sạch mảng đó do ứng dụng quản lý; JVM hoặc provider có thể đã tạo bản sao nội bộ. Đây là biện pháp giảm thời gian tồn tại của secret trong bộ nhớ, không phải bảo đảm zeroization tuyệt đối.

## 18. Phân quyền và kiểm soát sử dụng

KeyStore API cung cấp thao tác, còn quyền thực tế phụ thuộc provider, hệ điều hành, IAM và thiết bị. Nên phân biệt:

| Quyền | Ví dụ thao tác | Chính sách |
|---|---|---|
| Discover | aliases, containsAlias, size | Cấp cho thành phần kiểm kê cần thiết. |
| Read certificate | getCertificate, getCertificateChain | Có thể cấp rộng hơn nhưng phải bảo vệ tính toàn vẹn và nguồn gốc. |
| Use key | getKey, ký, giải mã, wrap/unwrap | Giới hạn theo ứng dụng, tenant, purpose và resource. |
| Import/create | setKeyEntry, setCertificateEntry | Chỉ cấp theo quy trình provisioning được duyệt. |
| Modify | deleteEntry, thay thế entry, store | Tách khỏi quyền runtime thông thường. |
| Export | Lấy encoded key hoặc xuất key package | Tắt mặc định; chỉ cho phép theo chính sách đặc biệt. |
| Administer provider/token | Cấu hình HSM, slot, policy hoặc PIN | Tách biệt với quyền dùng khóa của ứng dụng. |

Với khóa CA, code signing, ký giao dịch hoặc KEK quan trọng, cân nhắc dual control, quorum và audit bất biến. Ứng dụng runtime thường chỉ cần quyền ký hoặc giải mã trong phạm vi xác định, không cần quyền xóa, export hay thay đổi policy.

## 19. Backup và khôi phục KeyStore

Backup file keystore có thể chứa private key hoặc secret key. Nếu file và password cùng bị lộ, kẻ tấn công có thể lấy được khóa. Vì vậy:

- Xác định entry nào được phép backup; không export khóa non-exportable để né policy.
- Mã hóa backup bằng cơ chế được phê duyệt và khóa bảo vệ độc lập.
- Tách quyền tạo backup, đọc backup và restore.
- Lưu bản sao trong miền lỗi độc lập khi yêu cầu DR cần.
- Giữ metadata, alias, key ID/version và certificate chain để khôi phục đúng entry.
- Không lưu password cạnh backup hoặc trong cùng ticket/log.
- Kiểm thử restore trong môi trường cô lập và xác minh thao tác mật mã đầu cuối.

Với HSM/KMS, backup có thể là blob được bọc hoặc cơ chế backup nội bộ. Không giả định sao chép file cấu hình hoặc provider reference là đã sao lưu vật liệu khóa. Phải kiểm tra quy trình backup/restore của nhà cung cấp, yêu cầu cùng security domain, thiết bị tương thích và quorum quản trị.

## 20. Xoay vòng, thu hồi và hủy entry

KeyStore không tự động xoay vòng khóa theo cryptoperiod. Ứng dụng và hệ thống quản lý phải tổ chức quá trình:

1. Tạo key pair hoặc secret key mới theo policy.
2. Thêm entry/phiên bản mới với alias hoặc key ID rõ ràng.
3. Cấp certificate mới nếu khóa dùng cho PKI.
4. Cập nhật ứng dụng để dùng khóa mới cho thao tác mới.
5. Giữ khóa cũ trong phạm vi cần thiết để giải mã dữ liệu lịch sử hoặc xác minh chữ ký.
6. Rewrap/re-encrypt dữ liệu nếu kế hoạch yêu cầu.
7. Thu hồi certificate cũ khi cần.
8. Xóa entry và xử lý mọi backup/replica theo quy trình destruction sau khi không còn phụ thuộc.

deleteEntry(alias) loại bỏ entry khỏi keystore đang thao tác. Nó không chứng minh mọi bản sao vật lý, file backup, snapshot hoặc HSM backup blob đã bị xóa. Tương tự, revoke certificate không tự động hủy private key.

Nếu private key bị compromise, phải cô lập việc sử dụng, thu hồi certificate, cấp key pair mới và xử lý bản sao cũ theo incident response. Không restore một entry bị lộ rồi tiếp tục dùng nó chỉ vì file keystore mới đã được tạo.

## 21. Lỗi thường gặp khi dùng Java KeyStore

- Dựa vào default keystore type thay vì chỉ định rõ PKCS12/JKS/PKCS11.
- Lưu password trong source code, file cấu hình hoặc command line.
- Coi file PKCS12 có mật khẩu là an toàn tuyệt đối.
- Nhầm key store với trust store.
- Thêm certificate vào trust store mà không xác minh fingerprint và nguồn gốc.
- Giả định mọi provider hỗ trợ cùng loại entry và semantics mật khẩu.
- Cho rằng load(null, password) luôn có cùng ý nghĩa với mọi backend.
- Dùng getEncoded() hoặc log key object để debug.
- Cấp quyền export cho ứng dụng chỉ cần ký hoặc giải mã.
- Ghi đè keystore đang dùng mà không có cập nhật nguyên tử và rollback.
- Dùng alias làm định danh duy nhất mà không gắn với provider/version.
- Xóa alias rồi cho rằng mọi bản backup của key material đã biến mất.
- Không kiểm thử certificate chain, hostname hoặc trạng thái revocation khi cấu hình TLS.
- Chỉ backup file cấu hình PKCS11 mà không có kế hoạch khôi phục HSM.

## 22. Ví dụ thực tế: Java service dùng TLS và ký dữ liệu

Một service Java có hai nhu cầu:

- Cung cấp HTTPS và chứng minh danh tính máy chủ.
- Ký một thông điệp nghiệp vụ để hệ thống khác xác minh.

Thiết kế có thể gồm:

1. Tạo TLS key pair riêng, cấp certificate có SAN đúng hostname.
2. Giữ private key TLS trong PKCS12 được bảo vệ hoặc HSM.
3. Giữ certificate CA tin cậy của đối tác trong trust store.
4. Dùng KeyManagerFactory để JSSE truy cập identity entry và TrustManagerFactory để xác minh đối tác.
5. Tạo key pair ký nghiệp vụ riêng, với alias và policy tách biệt khỏi TLS key.
6. Dùng Signature cùng private key ký nghiệp vụ; bên nhận xác minh bằng public key/certificate tương ứng.
7. Ghi audit cho operation, key ID, version, workload và kết quả, không ghi vật liệu khóa.
8. Theo dõi thời hạn certificate, lên kế hoạch rotation và kiểm thử backup/restore.

Không nên tái sử dụng private key TLS cho ký nghiệp vụ chỉ để giảm số lượng khóa. Mỗi key nên có mục đích, quyền, cryptoperiod và blast radius phù hợp.

## 23. Checklist triển khai

Trước khi đưa Java KeyStore vào production, hãy xác nhận:

- [ ] Đã chọn type và provider rõ ràng, tương thích runtime.
- [ ] Đã phân biệt file keystore, OS store và HSM/KMS backend.
- [ ] Đã phân loại PrivateKeyEntry, SecretKeyEntry và TrustedCertificateEntry.
- [ ] Đã xác định alias, key ID, version, owner và purpose.
- [ ] Đã xác minh private key khớp certificate và chain đúng thứ tự.
- [ ] Đã xác minh certificate/trust anchor trước khi thêm vào trust store.
- [ ] Password/PIN lấy từ nguồn bí mật được quản lý và không hardcode.
- [ ] File permissions, IAM và quyền provider được giới hạn.
- [ ] Ứng dụng chỉ có quyền dùng khóa cần thiết; export/delete/admin tách riêng.
- [ ] Không log password, private key bytes hoặc secret key.
- [ ] TLS có hostname verification và trust validation đúng.
- [ ] Backup/restore phù hợp backend, có kiểm thử và quorum nếu cần.
- [ ] Rotation giữ được khả năng đọc dữ liệu cũ trong thời gian cần thiết.
- [ ] Revocation và destruction được quản lý như các quy trình riêng.
- [ ] Audit có thể truy vết người dùng, operation, key ID/version và kết quả.

## 24. Kết luận

java.security.KeyStore cung cấp một API thống nhất để ứng dụng Java lưu và truy cập key entry, certificate và trust material thông qua provider. Hiểu đúng type, entry, password protection, provider và backend giúp tránh nhầm lẫn giữa file keystore, trust store và HSM.

Trong hệ thống thực tế, KeyStore cần được đặt trong một thiết kế quản lý khóa đầy đủ: định danh và phiên bản rõ ràng, quyền sử dụng tối thiểu, bảo vệ private key, backup/restore đã kiểm thử, rotation có kế hoạch, revocation/destruction có kiểm soát và audit đầy đủ. API chuẩn giúp ứng dụng tích hợp; mức bảo mật cuối cùng phụ thuộc vào provider, backend và cách tổ chức vận hành vòng đời khóa.
