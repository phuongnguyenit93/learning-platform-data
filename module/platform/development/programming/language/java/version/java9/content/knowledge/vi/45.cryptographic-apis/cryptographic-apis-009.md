# Dùng KeyStore và keytool với định dạng PKCS12 tường minh trong Java 9+

## 1. Vì sao cần chỉ định rõ định dạng?

`KeyStore` là API Java để lưu/truy xuất khóa và chứng chỉ qua các entry có tên định danh (`alias`). `keytool` là công cụ dòng lệnh đi kèm JDK để tạo cặp khóa, kiểm tra, xuất/nhập chứng chỉ và quản lý keystore. Hai công cụ cùng dùng **kiểu keystore (`store type`)** để biết dữ liệu bên trong được đọc và ghi theo định dạng nào.

Từ **Java 9**, JDK dùng **`PKCS12`** làm định dạng keystore mặc định. Tuy vậy, mặc định có thể bị điều chỉnh bởi cấu hình security/provider hoặc môi trường triển khai. Với ứng dụng cần chạy ổn định qua các máy và bản JDK, nên ghi định dạng **tường minh ở cả công cụ và mã Java**:

- Trong lệnh `keytool` làm việc với tệp: `-storetype PKCS12` cùng `-keystore <đường-dẫn>`.
- Trong Java: `KeyStore.getInstance("PKCS12")` trước `load(...)` hoặc `store(...)`.
- Với cấu hình JSSE/TLS sử dụng system properties: chỉ định `javax.net.ssl.keyStoreType=PKCS12` và/hoặc `javax.net.ssl.trustStoreType=PKCS12` khi ứng dụng thật sự dùng các properties đó; phần ví dụ dưới đây ưu tiên API vì không cần đưa mật khẩu vào dòng lệnh Java.

**PKCS#12** là định dạng trao đổi/lưu khóa và chứng chỉ được nhiều công cụ hỗ trợ; các đuôi `.p12` và `.pfx` thường biểu thị tệp PKCS#12. **Đuôi tệp không tự quyết định định dạng**: hãy dùng `-storetype` và `getInstance`, đồng thời kiểm tra tệp do hệ thống thực sự tạo ra. Một tệp `.crt`/`.pem` chỉ chứa chứng chỉ X.509 không tự trở thành keystore PKCS#12.

Chủ đề này tập trung vào API JCA/JSSE và `keytool` vẫn được dùng trên JDK hiện đại, với ví dụ chạy được trên **Java 17+**. Các thao tác tạo chứng chỉ tự ký trong bài dùng **cho môi trường phát triển/kiểm thử**, không thay chứng chỉ được cấp và xác thực theo chính sách tin cậy của hệ thống thật.

## 2. Phân biệt keystore, truststore, key entry và certificate entry

Cùng một kiểu `PKCS12` có thể phục vụ hai vai trò khác nhau:

| Khái niệm | Chứa gì? | Dùng để làm gì? |
| --- | --- | --- |
| Identity keystore | Private key + certificate chain đi kèm | Chứng minh danh tính server hoặc client trong TLS, ký dữ liệu khi ứng dụng yêu cầu |
| Truststore | Các chứng chỉ được **chủ động tin cậy** (thường là CA trust anchors) | Xác định các nguồn cấp chứng chỉ mà client/server được phép tin |
| `PrivateKeyEntry` | `PrivateKey` + chuỗi chứng chỉ (`Certificate[]`) | Bảo vệ và sử dụng khóa riêng, ví dụ `dev-local` trong `identity.p12` |
| `TrustedCertificateEntry` | Một chứng chỉ đã được nhập làm điểm tin cậy | Ví dụ `dev-local` trong `truststore.p12` của bài thử nghiệm |
| `SecretKeyEntry` | Khóa bí mật đối xứng | Chỉ dùng khi provider/kiểu keystore và use case hỗ trợ; không liên quan trực tiếp ví dụ TLS bên dưới |

**Private key phải được giữ bí mật.** Chứng chỉ X.509 trong `.crt` chứa khóa **công khai** và thông tin chứng thực; việc xuất `-exportcert` không xuất private key. Không chuyển file `identity.p12` cho phía cần xác thực mình: họ thường chỉ cần CA certificate/chứng chỉ công khai phù hợp với mô hình tin cậy.

Một alias có **vai trò tùy loại entry**, không tùy tên alias. Khi `keytool -importcert` chạy trên một alias đã có private key, thao tác có thể nhập **certificate reply/chain** cho private-key entry đó; khi nhập chứng chỉ vào alias mới của truststore, nó tạo trusted-certificate entry. Vì vậy phải đọc loại entry qua `keytool -list -v` hoặc `KeyStore.isKeyEntry`/`isCertificateEntry`, không suy đoán từ tên.

### Mô hình kết nối khi dùng TLS

```text
Server (hoặc client dùng mTLS)
  identity.p12  [private key + certificate chain]
         |       KeyManagerFactory
         v
      TLS endpoint  --------------------> Peer
                                            |
                         TrustManagerFactory dùng truststore
                         kiểm chứng chain / chính sách tin cậy
```

`KeyStore` tự nó **không khởi tạo HTTPS hoặc thiết lập trust**. Muốn dùng trong TLS cần đưa keystore/truststore vào `KeyManagerFactory`/`TrustManagerFactory` rồi cấu hình `SSLContext` hoặc framework phù hợp. Kiểm tra tên máy chủ, mục đích sử dụng certificate, hạn hiệu lực và chuỗi tin cậy vẫn phải được bật đúng ở tầng TLS.

## 3. Bộ công cụ và cấu trúc ví dụ

Yêu cầu: JDK 17+ có lệnh `java`, `javac`, `keytool` trong `PATH`; một thư mục làm việc riêng, chưa có các file đích bên dưới. Không cần thư viện Maven/Gradle hay server database.

```text
pkcs12-demo/
├── identity.p12       # Chứa private key + certificate của dev-local
├── dev-local.crt      # Chỉ certificate công khai ở định dạng PEM
├── truststore.p12     # Chứa trusted-certificate entry của dev-local
└── Pkcs12Inspector.java
```

Trong các lệnh sau, **`KS_PASSWORD`** là biến môi trường chứa mật khẩu thử nghiệm; hãy lấy mật khẩu từ cơ chế nhập bí mật hoặc secret manager và không in ra log. Với Bash, có thể nhập ẩn như sau:

```bash
read -r -s -p "PKCS12 password: " KS_PASSWORD
printf '\n'
export KS_PASSWORD
```

Với PowerShell, nếu chạy thử cục bộ có thể nhập bằng `Read-Host -AsSecureString` và đưa vào biến môi trường của **phiên chạy hiện tại**:

```powershell
$secret = Read-Host "PKCS12 password" -AsSecureString
$env:KS_PASSWORD = [System.Net.NetworkCredential]::new("", $secret).Password
```

Khi xong, xóa biến môi trường; ví dụ Bash `unset KS_PASSWORD` hoặc PowerShell `Remove-Item Env:\KS_PASSWORD`. Biến môi trường là giải pháp thuận tiện cho demo/CI được kiểm soát, **không phải kho bí mật tuyệt đối**: tiến trình có quyền tương ứng có thể quan sát giá trị. Trong production, ưu tiên secret manager của nền tảng và giải pháp quản lý vòng đời khóa chuyên dụng. Không ghi mật khẩu trực tiếp sau `-storepass` trong shell history hoặc đưa vào Git.

`keytool` hỗ trợ `-storepass:env KS_PASSWORD`: tham số chứa **tên biến môi trường**, không chứa mật khẩu. Có thể bỏ tùy chọn mật khẩu để `keytool` hỏi trực tiếp nếu chạy tương tác; riêng bài này dùng biến môi trường để cả quy trình và Java cùng nhận một secret.

## 4. Quy trình keytool đầy đủ với `-storetype PKCS12`

### 4.1. Tạo identity keystore và cặp khóa EC

Chạy tại thư mục `pkcs12-demo` sau khi đã đặt `KS_PASSWORD`:

```bash
keytool -genkeypair -alias dev-local -keyalg EC -groupname secp256r1 -sigalg SHA256withECDSA -validity 30 -dname "CN=localhost,O=Demo" -ext SAN=dns:localhost,ip:127.0.0.1 -ext EKU=serverAuth -keystore identity.p12 -storetype PKCS12 -storepass:env KS_PASSWORD
```

Giải thích các lựa chọn quan trọng:

- `-genkeypair` sinh cặp public/private key; `-alias dev-local` xác định entry.
- `-keyalg EC -groupname secp256r1` chọn elliptic curve P-256 có hỗ trợ phổ biến trên JDK hiện đại. `-sigalg SHA256withECDSA` chỉ rõ thuật toán ký chứng chỉ tự ký của ví dụ.
- `-validity 30` tạo chứng chỉ tự ký có hiệu lực 30 ngày từ thời điểm tạo. Chính sách thời hạn trong production do CA và ứng dụng quyết định.
- `-dname` đặt distinguished name; `CN=localhost` **không thay cho SAN** khi xác minh tên máy chủ.
- `-ext SAN=dns:localhost,ip:127.0.0.1` chỉ rõ DNS/IP được chứng chỉ mô tả. Trong ứng dụng thật, phải thay bằng tên máy chủ hợp lệ của dịch vụ.
- `-ext EKU=serverAuth` mô tả mục đích TLS server của chứng chỉ trong ví dụ.
- `-keystore identity.p12 -storetype PKCS12` làm cho **đường dẫn và định dạng đều rõ ràng**. Không dựa vào tên mặc định `.keystore` hoặc cấu hình máy.

Lệnh tạo **private-key entry** chứa private key và một certificate X.509 **tự ký**. Nó chưa được các client Internet tin cậy. Đây là tiền đề để học cách phân biệt identity keystore và truststore; tuyệt đối không coi bước tạo thành một chứng chỉ CA-signed dùng được ở Internet.

### 4.2. Kiểm tra keystore và chứng chỉ

```bash
keytool -list -v -alias dev-local -keystore identity.p12 -storetype PKCS12 -storepass:env KS_PASSWORD
```

Đọc các trường `Keystore type: PKCS12`, `Alias name: dev-local`, `Entry type: PrivateKeyEntry`, `Certificate chain length`, `Owner`/`Issuer`, thuật toán khóa, `Valid from ... until ...`, `SHA256` fingerprint và `SubjectAlternativeName`. Những giá trị gắn với thời điểm sinh khóa (ngày, số serial, fingerprint) sẽ **khác nhau mỗi lần chạy**, không nên chép một output mẫu cố định để so khớp.

Có thể liệt kê tất cả alias bằng cách bỏ `-alias dev-local`:

```bash
keytool -list -keystore identity.p12 -storetype PKCS12 -storepass:env KS_PASSWORD
```

Nếu alias không xuất hiện, hãy kiểm tra file được mở, định dạng, quyền đọc, mật khẩu và chữ hoa/chữ thường của alias theo provider; không tự lấy alias đầu tiên làm khóa sản xuất.

### 4.3. Chỉ xuất chứng chỉ công khai

```bash
keytool -exportcert -rfc -alias dev-local -file dev-local.crt -keystore identity.p12 -storetype PKCS12 -storepass:env KS_PASSWORD
```

`-rfc` xuất chứng chỉ X.509 dạng văn bản PEM (có các dòng `-----BEGIN CERTIFICATE-----` / `-----END CERTIFICATE-----`). File `dev-local.crt` **không chứa private key**.

Kiểm tra chứng chỉ vừa xuất:

```bash
keytool -printcert -file dev-local.crt
```

`-printcert` đọc **file chứng chỉ**, không phải file keystore nên không có `-storetype`. Kiểm tra Subject, Issuer, SAN, Key Usage/EKU, thời hạn và SHA-256 fingerprint. Khi nhập certificate do bên khác cung cấp, phải so fingerprint với một nguồn tin cậy **độc lập** trước khi tin nó; việc một file tự hiển thị fingerprint không tự xác nhận nguồn gốc.

### 4.4. Tạo truststore PKCS12 riêng cho buổi thử

Sau khi xác nhận `dev-local.crt` đúng là chứng chỉ tự ký bạn vừa tạo, nhập nó vào **truststore thử nghiệm riêng**, giữ nguyên identity keystore:

```bash
keytool -importcert -alias dev-local -file dev-local.crt -keystore truststore.p12 -storetype PKCS12 -storepass:env KS_PASSWORD
```

`keytool` sẽ yêu cầu xác nhận có tin chứng chỉ này hay không; chỉ chấp nhận khi đã xác minh đây là certificate được phép tin. Lệnh tạo file `truststore.p12` nếu chưa tồn tại và thêm một **`TrustedCertificateEntry`**, khác với `PrivateKeyEntry` trong `identity.p12`. Kiểm tra:

```bash
keytool -list -v -alias dev-local -keystore truststore.p12 -storetype PKCS12 -storepass:env KS_PASSWORD
```

Kết quả mong đợi có `Keystore type: PKCS12` và `Entry type: trustedCertEntry`; không có private key. Việc import một **self-signed leaf certificate** làm điểm tin cậy chỉ chấp nhận được trong phạm vi thử nghiệm có kiểm soát. Production thường tin **CA trust anchors** được tổ chức phê duyệt, đồng thời xác minh chain, tên host, thời hạn và mục đích sử dụng. Không nhập bừa chứng chỉ vào `cacerts` toàn cục.

### 4.5. Kết quả có thể đối chiếu

| Tệp | Alias | Loại entry | Chứa private key? | Vai trò |
| --- | --- | --- | --- | --- |
| `identity.p12` | `dev-local` | `PrivateKeyEntry` | **Có** | Identity mẫu của server |
| `dev-local.crt` | Không áp dụng | File PEM certificate | **Không** | Certificate có thể chia sẻ |
| `truststore.p12` | `dev-local` | `TrustedCertificateEntry` | **Không** | Điểm tin cậy riêng của bài thử |

Dù hai keystore có cùng tên alias, hai entry khác nhau và được xác định bởi **file chứa nó**. Sự giống nhau của alias không tạo ra quan hệ tin cậy; quan hệ chỉ xuất hiện khi certificate phù hợp được đưa vào truststore và áp dụng trong kiểm tra TLS.

## 5. Ví dụ Java 17+ độc lập đọc hai file bằng định dạng tường minh

Chương trình sau không tự tạo certificate. Nó dùng các file từ mục 4, kiểm tra alias, phân biệt loại entry, đọc chứng chỉ và (chỉ với identity keystore) mở private key bằng mật khẩu. Đây là mã nguồn **biên dịch được độc lập** bằng thư viện chuẩn JDK.

**File: `Pkcs12Inspector.java`**

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Key;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;
import java.util.Arrays;

public final class Pkcs12Inspector {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.out.println("Usage: java Pkcs12Inspector <file.p12> <alias>");
            return;
        }
        String raw = System.getenv("KS_PASSWORD");
        if (raw == null || raw.isEmpty()) {
            throw new IllegalStateException("KS_PASSWORD is not configured");
        }
        char[] password = raw.toCharArray();
        try {
            KeyStore store = KeyStore.getInstance("PKCS12");
            try (InputStream input = Files.newInputStream(Path.of(args[0]))) {
                store.load(input, password);
            }
            String alias = args[1];
            if (!store.containsAlias(alias)) {
                throw new IllegalArgumentException("Alias not found: " + alias);
            }

            System.out.println("Format: " + store.getType());
            System.out.println("Alias: " + alias);
            System.out.println("Private key entry: " + store.isKeyEntry(alias));
            System.out.println("Trusted certificate entry: " + store.isCertificateEntry(alias));

            Certificate certificate = store.getCertificate(alias);
            if (!(certificate instanceof X509Certificate x509)) {
                throw new IllegalStateException("Expected an X.509 certificate");
            }
            x509.checkValidity();
            System.out.println("Certificate type: " + x509.getType());
            System.out.println("Certificate in date range: yes");

            if (store.isKeyEntry(alias)) {
                Key key = store.getKey(alias, password);
                System.out.println("Private key: " + (key instanceof PrivateKey));
                System.out.println("Key algorithm: " + key.getAlgorithm());
                Certificate[] chain = store.getCertificateChain(alias);
                System.out.println("Chain length: " + (chain == null ? 0 : chain.length));
            }
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

Biên dịch và chạy ngay trong thư mục chứa file:

```bash
javac -encoding UTF-8 Pkcs12Inspector.java
java Pkcs12Inspector identity.p12 dev-local
java Pkcs12Inspector truststore.p12 dev-local
```

Với đúng các lệnh `keytool` ở mục 4 (chứng chỉ đang còn hạn, alias chưa bị sửa, provider JDK mặc định), đầu ra cho `identity.p12` là:

```text
Format: PKCS12
Alias: dev-local
Private key entry: true
Trusted certificate entry: false
Certificate type: X.509
Certificate in date range: yes
Private key: true
Key algorithm: EC
Chain length: 1
```

Đầu ra cho `truststore.p12` là:

```text
Format: PKCS12
Alias: dev-local
Private key entry: false
Trusted certificate entry: true
Certificate type: X.509
Certificate in date range: yes
```

Nếu không cung cấp đúng hai đối số, stdout cố định là:

```text
Usage: java Pkcs12Inspector <file.p12> <alias>
```

Những đầu ra trên đã được kiểm tra khi chạy với JDK 24 và mã biên dịch bằng `javac --release 17`. Lưu ý `x509.checkValidity()` **chỉ kiểm tra khoảng ngày hiệu lực**; nó không xác minh chứng chỉ được CA đáng tin cậy ký, không kiểm tra tên máy chủ và không thay thế xác minh chứng chỉ của TLS.

### Giải thích các API trong chương trình

- `KeyStore.getInstance("PKCS12")` tạo đối tượng xử lý **chính xác định dạng PKCS12**; tên file `.p12` chỉ là quy ước.
- `store.load(input, password)` đọc file và kiểm tra tính toàn vẹn nếu provider hỗ trợ và password thích hợp. `InputStream` được đóng bằng `try-with-resources`.
- `containsAlias` kiểm tra sự tồn tại; `isKeyEntry` phát hiện entry chứa khóa (có thể là private hoặc secret key tùy loại); `isCertificateEntry` phát hiện entry chỉ chứa trusted certificate.
- `getCertificate(alias)` đọc X.509 certificate công khai; `getKey(alias, password)` cần mật khẩu bảo vệ khóa và **trả đối tượng `Key` nhạy cảm**. Ví dụ chỉ in thuật toán, không bao giờ in nội dung private key.
- `getCertificateChain(alias)` trả chuỗi chứng chỉ của private-key entry; bài demo tự ký nên độ dài bằng 1. Khi dùng CA thật, chuỗi có thể gồm nhiều certificate.
- `Arrays.fill(password, '\0')` xóa **bản sao `char[]`** khi kết thúc. Vì `System.getenv(...)` trả `String` bất biến, cách này không thể bảo đảm xóa toàn bộ bản sao bí mật trong bộ nhớ; với ứng dụng thật nên nhận `char[]` trực tiếp từ console/secret provider và giới hạn vòng đời của nó.

Nếu chỉ muốn liệt kê alias hoặc đọc certificate công khai, ứng dụng có thể không cần gọi `getKey(...)`. Không nên nạp private key vào nơi chỉ cần truststore.

## 6. Tạo, cập nhật và ghi keystore qua Java

`KeyStore` hỗ trợ cả **đọc** và **ghi**. Mã bên dưới là **đoạn minh họa** dùng trong phương thức đã có các import `java.security.KeyStore`, `java.nio.file.*` và biến `char[] password` hợp lệ:

```java
KeyStore empty = KeyStore.getInstance("PKCS12");
empty.load(null, password);                 // Khởi tạo keystore rỗng trong bộ nhớ.
try (var out = Files.newOutputStream(Path.of("empty.p12"))) {
    empty.store(out, password);             // Ghi tệp PKCS12.
}
```

`load(null, password)` là cách **khởi tạo keystore rỗng**, còn `load(input, password)` là cách mở file hiện hữu. Cần phân biệt vì `Files.newInputStream` trên file chưa tồn tại sẽ ném `NoSuchFileException`. Chỉ lưu vào đường dẫn được phép ghi và có quyền truy cập file phù hợp; `store(...)` có thể thay nội dung file đích khi thao tác ghi được yêu cầu.

Khi cần thao tác entry trong Java:

| API | Ý nghĩa |
| --- | --- |
| `setCertificateEntry(alias, cert)` | Lưu chứng chỉ tin cậy trong keystore phù hợp; phải xác minh nguồn trust |
| `setKeyEntry(alias, privateKey, password, chain)` | Lưu private key và chuỗi chứng chỉ có liên quan |
| `getEntry(alias, new KeyStore.PasswordProtection(password))` | Đọc entry theo protection parameter; kiểm tra đúng subclass `PrivateKeyEntry`/`TrustedCertificateEntry` |
| `deleteEntry(alias)` | Xóa entry theo alias trong bộ nhớ; chỉ được lưu ra đĩa khi gọi `store(...)` |
| `aliases()`, `size()`, `containsAlias(...)` | Khám phá và kiểm tra các mục hiện có |

Với PKCS12, mức hỗ trợ các entry và thuật toán mã hóa phụ thuộc provider. Đừng mặc định rằng mọi provider hỗ trợ khóa đối xứng hoặc **mật khẩu riêng cho từng private key** giống nhau. Trong ví dụ dùng provider PKCS12 mặc định của JDK, mật khẩu được sử dụng cho cả file và entry; cách đơn giản này tránh kỳ vọng không tương thích khi chuyển công cụ.

Đối với file chứa khóa thật, tránh lưu đè trực tiếp khi đang xử lý sự cố: sao lưu an toàn, kiểm tra file mới, thay thế theo cơ chế triển khai có rollback, phân quyền chỉ cho tiến trình cần dùng và không lưu plaintext/private key vào log.

## 7. Dùng tường minh keystore và truststore trong JSSE/TLS

Java HTTPS/TLS thường cần **hai nhóm vật liệu khóa**: identity của chính endpoint và các certificate được tin cậy. Sau khi đã có hai đối tượng `KeyStore` được `load(...)` bằng `"PKCS12"`, có thể cấu hình JSSE như sau.

Đây là **đoạn minh họa để chèn vào ứng dụng** đã chuẩn bị `KeyStore identityStore`, `KeyStore trustStore` và `char[] identityPassword`, không phải chương trình chạy độc lập:

```java
import java.security.SecureRandom;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(identityStore, identityPassword);

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(kmf.getKeyManagers(), tmf.getTrustManagers(),
                new SecureRandom());
```

`KeyManagerFactory` sử dụng private key và certificate chain của identity keystore; `TrustManagerFactory` sử dụng certificate tin cậy của truststore. Khi chỉ làm **TLS client không có mutual TLS**, thường không cần identity keystore riêng và có thể dùng trust manager mặc định của nền tảng. Khi làm **server TLS**, identity private key/certificate chain là trọng tâm; cấu hình trust manager tùy việc server có xác thực client (mTLS) hay không.

**Chú ý quan trọng:** `SSLContext` tạo ra kết cấu TLS, không tự quyết định hostname validation cho mọi loại socket/client. Phải dùng API HTTP/TLS thích hợp, bật xác thực tên máy chủ, chain và mục đích certificate. Nếu chọn truststore riêng chỉ chứa một chứng chỉ dev, ứng dụng có thể **không còn tin các CA mặc định** như trước; điều đó là chủ ý trong demo nhưng có thể làm HTTPS production thất bại. Không vô hiệu hóa hostname verification hoặc trust manager để “sửa” lỗi tin cậy.

Một cách khác dành cho framework tôn trọng các system properties JSSE là chỉ rõ **kiểu keystore/truststore** trong cấu hình runtime; tuy nhiên đừng đưa plaintext password vào tham số `-D...Password=...` vì nó có thể lộ qua danh sách tiến trình/log. Ưu tiên tích hợp secret manager hoặc cấu hình bảo mật của framework.

## 8. Chứng chỉ CA-signed trong môi trường sản xuất

Cặp khóa tạo bởi `keytool -genkeypair` có thể dùng làm nền tảng tạo **certificate signing request (CSR)**, nhưng certificate tự ký ban đầu chưa phải bằng chứng được CA đáng tin xác thực. Ví dụ tạo CSR cho alias hiện có:

```bash
keytool -certreq -alias dev-local -file dev-local.csr -ext SAN=dns:localhost,ip:127.0.0.1 -keystore identity.p12 -storetype PKCS12 -storepass:env KS_PASSWORD
```

Lệnh này xuất yêu cầu ký chứng chỉ, **không xuất private key**. Với dịch vụ thật, phải tạo alias/key riêng và yêu cầu SAN khớp DNS thật; CA sẽ áp chính sách cấp chứng chỉ và extensions thích hợp. Sau khi nhận certificate response/chain:

1. Xác minh yêu cầu CSR/định danh, chứng chỉ CA và chuỗi CA theo nguồn đáng tin, không tự cấp quyền tin vì file có đuôi `.crt`.
2. Import các CA certificate cần thiết vào đúng kho tin cậy theo chính sách; đừng đổi hoặc xóa private-key alias đang chờ certificate reply.
3. Dùng `keytool -importcert` lên **chính alias có private key** để gắn certificate response/chain được ký, kiểm tra public key trong certificate trùng key pair ban đầu.
4. Xác nhận `PrivateKeyEntry` vẫn tồn tại, chain được nối đúng, SAN/EKU/validity phù hợp, rồi kiểm thử TLS với client/server thực tế.

Dùng `keytool -list -v -alias dev-local -keystore identity.p12 -storetype PKCS12 -storepass:env KS_PASSWORD` để kiểm tra sau khi thay certificate; không giả định mọi CA phát hành chain cùng định dạng hoặc cách đóng gói. Khi có key rotation, giữ cơ chế thay thế và rollback được kiểm chứng.

## 9. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `Invalid keystore format` hoặc lỗi parse | Chọn sai store type, file hỏng/trống, đọc nhầm PEM như PKCS12 | Kiểm tra nguồn file, `keytool -list -storetype PKCS12`; không chỉ nhìn extension |
| `keystore password was incorrect`/`IOException` | Sai password hoặc file/thuật toán mã hóa không tương thích provider | Xác nhận password qua nguồn bí mật, JDK/provider và file nguyên vẹn; không log password |
| `UnrecoverableKeyException` | Password giải mã private-key entry sai hoặc entry không dùng được | Kiểm tra entry type và protection parameter; đừng thử đoán hàng loạt |
| `Alias not found` | Nhập sai alias, dùng nhầm truststore/identity keystore | `keytool -list -storetype PKCS12 -keystore ...`; đối chiếu chính xác file |
| `getCertificateChain(alias)` trả `null` | Alias là certificate-only hoặc entry không có chain | Kiểm tra `isKeyEntry`/`isCertificateEntry` trước |
| Truststore có certificate nhưng HTTPS vẫn lỗi | Certificate không đúng CA/host, chain sai, hết hạn, EKU không phù hợp hoặc chưa dùng đúng truststore | Xác minh chain, SAN, thời hạn, TLS client config, trust manager thực tế |
| `SSLHandshakeException: PKIX path building failed` | Client không xây được chain tới trust anchor đáng tin | Kiểm tra CA chain và truststore có dùng thật, không tắt xác minh TLS |
| `NoSuchAlgorithmException: PKCS12` | Security provider/runtime không cung cấp kiểu chuẩn mong đợi | Kiểm tra JDK chuẩn/provider, cấu hình bảo mật; PKCS12 là kiểu keystore chuẩn của Java SE |
| Mã Java mở được nhưng `keytool` khác không mở được | Provider/JDK policy khác, cách mã hóa PKCS12 hoặc password không tương thích | Đối chiếu `java -version`, `keytool -version`, cách tạo PKCS12 và hỗ trợ công cụ đích |
| Tạo file mới nhưng `load(InputStream, ...)` báo thiếu file | Nhầm thao tác mở file với khởi tạo keystore mới | Dùng `load(null, password)` rồi `store(output, password)`, hoặc dùng `keytool -genkeypair` |

Đừng “khắc phục” lỗi TLS bằng cách chấp nhận mọi certificate, bỏ kiểm tra hostname hoặc thêm mọi cert nhìn thấy vào truststore. Cách đó làm mất mục đích của cơ chế tin cậy.

## 10. Checklist sử dụng an toàn và có thể tái hiện

1. Chọn định dạng **`PKCS12`** cho file keystore/truststore mới; ghi `-storetype PKCS12` trong mọi lệnh `keytool` đọc/ghi chúng và `KeyStore.getInstance("PKCS12")` trong Java.
2. Chỉ rõ `-keystore` và `-alias`; phân biệt tệp identity chứa **private key** với truststore chứa **certificate tin cậy**.
3. Dùng thuật toán khóa/ký được hỗ trợ hiện hành, ví dụ EC P-256 + SHA256withECDSA; chọn SAN và EKU đúng mục đích. Không dùng private key tự ký của ví dụ làm danh tính production.
4. Cung cấp password bằng cơ chế an toàn (nhập tương tác, secret manager, env được kiểm soát); hạn chế quyền file, không log private key/password và không commit `.p12` chứa secret vào Git.
5. Sau `-genkeypair`, `-importcert` hoặc cập nhật certificate chain, luôn `keytool -list -v` để kiểm tra **store type, alias, entry type, chain length, SAN, fingerprint, validity**.
6. Trong Java, mở `InputStream` bằng `try-with-resources`, xử lý ngoại lệ mở file/mật khẩu/alias rõ ràng, giải phóng bản sao `char[]` sớm nhất có thể.
7. Khi dùng JSSE, kiểm tra **cấu hình TLS thực tế**: identity từ key manager, trust từ trust manager, hostname verification và chain.
8. Theo dõi thời hạn/rotation certificate và khóa; kiểm thử trên đúng JDK, provider, TLS framework và hạ tầng triển khai; không suy luận từ phần mở rộng `.p12`.
9. Chỉ đưa certificate vào truststore sau khi xác minh nguồn gốc/fingerprint ngoài băng; giữ truststore dev tách hẳn production.

## 11. Tài liệu chuẩn còn áp dụng

- Oracle Java SE 25: [`keytool` command reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/keytool.html) — `-storetype`, `-storepass:env`, `-genkeypair`, `-list`, `-exportcert`, `-importcert`, `-certreq`, SAN/EKU.
- Oracle Java SE 26: [`java.security.KeyStore` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyStore.html) — `getInstance`, `load`, `store`, `PrivateKeyEntry`, `TrustedCertificateEntry` và kiểu chuẩn `PKCS12`.
- Oracle Java SE 25: [JCA Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-cryptography-architecture-jca-reference-guide.html) — nhà cung cấp thuật toán, quản lý khóa và chứng chỉ trong Java.
- Oracle Java SE 25: [`KeyManagerFactory`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html) và [`TrustManagerFactory`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html) — kết nối KeyStore với JSSE/TLS.
- OpenJDK: [JEP 229 — Create PKCS12 Keystores by Default](https://openjdk.org/jeps/229) — thay đổi mặc định bắt đầu từ Java 9.
