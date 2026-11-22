# Java 10 — Chứng thư gốc: quản lý nguồn gốc và quyền sửa truststore

## 1. Mục tiêu và nguyên tắc cốt lõi

**Truststore** lưu các chứng thư hoặc thông tin **trust anchor** mà Java có thể sử dụng để xác thực chuỗi chứng thư X.509, đặc biệt trong kết nối **TLS/HTTPS**. Vì vậy, thay đổi truststore là thay đổi **ranh giới tin cậy** của ứng dụng, không phải một thao tác cấu hình vô hại.

Java 10 đưa vào **JEP 319 — Root Certificates**, cung cấp một tập root CA certificates mặc định cho các bản OpenJDK phù hợp. Nhưng JEP 319 **không** miễn trách nhiệm của tổ chức trong việc xác định **root nào đáng tin, ai được phép thêm hoặc gỡ root, dữ liệu lấy từ đâu và làm thế nào phát hiện sửa đổi trái phép**.

**Nguyên tắc:** chỉ import root CA đã được xác thực **nguồn gốc và fingerprint qua kênh tin cậy độc lập**, có sự phê duyệt thích hợp, được phát hành thành artifact có provenance rõ ràng và được bảo vệ khỏi quyền ghi của tiến trình ứng dụng.

Sau bài này, bạn có thể:
1. Phân biệt **root CA certificate**, **trust anchor**, **truststore** và **private-key keystore**.
2. Hiểu JEP 319 trong bối cảnh OpenJDK/Oracle JDK hiện đại.
3. Xác định nguồn truststore thực sự được **SunJSSE** sử dụng.
4. Kiểm tra **SHA-256 fingerprint của chứng thư** và **SHA-256 của file truststore** đúng mục đích.
5. Áp dụng **least privilege** cho truststore, thư mục cha, container image và Kubernetes resources.
6. Xây dựng PKCS#12 truststore riêng cho ứng dụng mà không sửa JDK `cacerts` dùng chung.
7. Hiểu chính sách phê duyệt, rotation, rollback, removal và incident response.
8. Chạy bốn ví dụ Java 17+ đã được kiểm chứng về audit root, `SSLContext`, file digest và default trust manager.
9. Không dùng `trust-all` hay tắt hostname verification để chữa lỗi TLS.

**Special Note:** chỉ sử dụng kiến thức còn áp dụng trên Java mới. Bài dùng **Java 17+**, `keytool`, JSSE/JCA API và tài liệu JDK 25/27; không hướng dẫn các phương pháp TLS yếu hoặc API legacy.

## 2. Vì sao Java 10 có JEP 319?

Trước khi các root certificates được phân phối thống nhất, một số bản build OpenJDK có `cacerts` rỗng hoặc không đủ root CAs như Oracle JDK. Hệ quả là một Java TLS client có thể không xây dựng được certificate chain tới trust anchor, dù server có chứng thư công khai hợp lệ.

**JEP 319** đưa root certificates thuộc chương trình Oracle Java SE Root CA vào OpenJDK nhằm cải thiện hành vi mặc định và giảm khác biệt giữa các bản phân phối.

Những điều cần hiểu đúng hiện nay:

- **`cacerts`** là tập trusted certificates được JDK/distro cung cấp theo chính sách của họ.
- Root set **có thể thay đổi** sau một JDK security update hoặc khi đổi vendor/base image.
- Một số Linux distributions hoặc runtime images có cách tích hợp root store riêng; không được mặc định mọi `cacerts` giống nhau.
- Một tổ chức có **private PKI** có thể cần CA riêng không nằm trong root set mặc định.
- Thêm CA riêng phải là quyết định bảo mật có **phạm vi** chứ không phải thao tác “import mọi thứ cho hết lỗi”.

Đường dẫn thường dùng trên JDK hiện đại:

```text
<java.home>/lib/security/cacerts
```

Ví dụ Windows:

```text
C:\Java\jdk-25\lib\security\cacerts
```

Ví dụ đường dẫn chỉ để minh họa; phải lấy **`java.home` của runtime thực tế**, nhất là với container, `jlink` image hoặc nhiều JDK cùng cài.

```bash
keytool -list -cacerts
```

Lệnh này **chỉ đọc** các entries trong `cacerts` của JDK mà `keytool` tương ứng đang dùng. Tool có thể yêu cầu password để kiểm tra integrity; tránh đưa password vào command line.

## 3. Bốn khái niệm dễ nhầm

| Khái niệm | Nghĩa | Rủi ro khi nhầm |
|---|---|---|
| **Root CA certificate** | X.509 public certificate đại diện một CA gốc | Tự ký không đồng nghĩa đã được phê duyệt |
| **Trust anchor** | Điểm tin cậy bắt đầu quá trình kiểm tra chain PKIX | Thêm nhầm anchor mở rộng trust boundary |
| **Truststore** | Tập public certificates/anchors cho `TrustManager` | Người sửa store có thể thay các quyết định tin cậy |
| **Keystore chứa private key** | Private keys/chains ứng dụng dùng để xác thực danh tính của chính nó | Rò rỉ private key nguy hiểm hơn cả lộ public root cert |

### 3.1. Root CA certificate không phải private key

Một root CA certificate chứa **public key**, chủ thể, issuer, validity, extension và chữ ký. Nó **không** chứa khóa riêng dùng để phát hành chứng thư. TLS client chỉ cần **root public certificate** hoặc trust-anchor information thích hợp để xác thực chain.

Đừng yêu cầu PKI team giao **CA private key** chỉ vì Java client cần tin một service nội bộ.

### 3.2. Tự ký không tự động đáng tin

Một attacker có thể tự tạo một chứng thư `CN=Corporate Trusted Root` rồi tự ký. Subject trông hợp lý và chữ ký tự xác minh được **không đủ** để chứng minh đó là CA thật.

Quyết định tin cậy đến từ:
- Nguồn chứng thư được xác thực độc lập;
- Fingerprint đã được một chủ thể có thẩm quyền phê duyệt;
- Chính sách tin cậy đúng ứng dụng, môi trường và mục đích sử dụng.

### 3.3. Root certificate được tin không có nghĩa mọi leaf đều tự động hợp lệ

Khi xác thực TLS, ứng dụng còn phải kiểm tra các yếu tố như **certificate chain**, chữ ký, thời hạn, hostname/SAN, EKU, algorithm constraints và revocation theo cấu hình. Tuy nhiên, thêm một root CA bất kỳ vẫn là hành động nguy hiểm vì nó tạo điều kiện để các chứng thư được CA ấy ký được xem là hợp lệ theo những kiểm tra khác.

### 3.4. `KeyStore` API bao trùm nhiều loại entry

`java.security.KeyStore` có các loại entries như:
- `trustedCertEntry`: chứng thư tin cậy, thường dùng cho truststore;
- `PrivateKeyEntry`: khóa riêng và certificate chain;
- Một số loại entry khác tùy provider/format.

Với một **app truststore chỉ chứa CA roots**, mong đợi thường là **`trustedCertEntry`**, không có private key.

## 4. Vì sao quyền sửa truststore là quyền bảo mật nhạy cảm?

Giả sử người tấn công có thể thêm root của họ vào truststore ứng dụng. Khi có khả năng kiểm soát một endpoint, DNS, proxy hoặc tuyến mạng tương ứng, họ có thể cấp một server certificate do CA giả ấy ký. Nếu các kiểm tra còn lại được thỏa, client Java có thể chấp nhận chain đó và kết nối tới kẻ mạo danh.

Do đó quyền **import, delete, replace** trust anchors phải được quản trị giống một thay đổi security policy.

Một thiết kế phân quyền nên phân tách:
- **PKI/CA owner:** xác nhận CA identity và public certificate;
- **Security reviewer:** phê duyệt scope và trust boundary;
- **Build/release pipeline:** dựng artifact từ inputs đã phê duyệt;
- **Platform/SRE:** triển khai và giới hạn quyền filesystem/control plane;
- **Application service account:** **chỉ đọc** truststore được phê duyệt;
- **Auditor:** xem provenance, approval, hash, drift;
- **Incident responder:** có runbook thu hồi và rollback.

Không để service tự động sửa `cacerts` khi gặp handshake exception. Không cho mọi developers quyền thay trusted roots của production không qua review.

## 5. SunJSSE thực sự lấy truststore ở đâu?

Trong **SunJSSE reference implementation** theo tài liệu Oracle JDK 25/27, khi default `TrustManagerFactory` được khởi tạo với `null KeyStore`, thứ tự tìm trust material là:

1. Nếu đã có system property `javax.net.ssl.trustStore`, dùng file được chỉ định.
2. Nếu chưa chỉ định, ưu tiên `<java.home>/lib/security/jssecacerts` khi file này tồn tại.
3. Nếu không có `jssecacerts`, thử `<java.home>/lib/security/cacerts`.
4. Nếu không tìm được nguồn phù hợp, provider có thể tạo một tập trusted roots rỗng theo hành vi đã tài liệu hóa.

**Bẫy quan trọng:** nếu `javax.net.ssl.trustStore` **có được đặt nhưng file không tồn tại**, SunJSSE có thể tạo một `TrustManager` với **empty truststore**. Đừng giả định nó tự fallback về `cacerts`.

```text
javax.net.ssl.trustStore được khai báo?
  |
  +-- CÓ --> load đường dẫn đã chỉ định
  |            |
  |            +-- file không tồn tại --> empty trust material (SunJSSE)
  |
  +-- KHÔNG --> jssecacerts tồn tại?
                 |
                 +-- CÓ --> jssecacerts
                 |
                 +-- KHÔNG --> cacerts tồn tại?
                                |
                                +-- CÓ --> cacerts
                                +-- KHÔNG --> empty trust material
```

Lưu ý đây là cơ chế của **SunJSSE**, không phải cam kết rằng mọi custom provider/framework/HSM có cùng thứ tự.

### 5.1. Các thuộc tính cấu hình liên quan

```text
javax.net.ssl.trustStore
javax.net.ssl.trustStoreType
javax.net.ssl.trustStorePassword
javax.net.ssl.trustStoreProvider
```

Cấu hình file riêng, minh họa:

```bash
java -Djavax.net.ssl.trustStore=/opt/app/config/truststore.p12 \
     -Djavax.net.ssl.trustStoreType=PKCS12 \
     -jar app.jar
```

Cấu hình này có thể **thay thế nguồn tin cậy mặc định** đối với các client JSSE dùng default managers. Nó **không** tự động merge certificates từ `cacerts`.

### 5.2. `jssecacerts` có thể che `cacerts`

Một `jssecacerts` tùy biến được ưu tiên trước `cacerts`. Nếu ai đó tạo `jssecacerts` chỉ với một private CA, ứng dụng có thể **không còn tin public CAs** mà nó từng tin qua `cacerts`, nếu chúng không xuất hiện ở store mới.

Đừng xem `jssecacerts` là “file bổ sung” được JVM tự merge.

### 5.3. Nguồn mặc định và source thực tế có thể khác

Application frameworks có thể khởi tạo `SSLContext`/`TrustManagerFactory` riêng hoặc sử dụng providers khác. Vì vậy khi điều tra TLS:
- Xem effective system properties;
- Kiểm tra `java.home`;
- Xem cấu hình HTTP client/framework;
- Xem liệu có custom `SSLContext` hay không;
- Khi cần bật JSSE diagnostics có kiểm soát.

Không lấy `keytool -list -cacerts` là bằng chứng tuyệt đối rằng một client bất kỳ đang dùng toàn bộ roots trong file đó.

## 6. Chuỗi nguồn gốc (provenance) của root CA

Một quy trình có thể kiểm toán:

```text
Nhu cầu nghiệp vụ xác định rõ
       |
       v
PKI/CA owner cung cấp public certificate
       |
       v
Nhận fingerprint qua kênh phê duyệt ĐỘC LẬP
       |
       v
Kiểm tra SHA-256, subject, issuer, CA extensions, thời hạn
       |
       v
Security reviewer + app owner phê duyệt CA và scope
       |
       v
Tạo truststore versioned từ approved inputs
       |
       v
Kiểm tra file digest / ký release manifest
       |
       v
Deploy immutable artifact, runtime đọc-only
       |
       v
Kiểm thử TLS thật, negative tests, audit, rotation
```

**Tại sao phải xác thực ngoài kênh nhận file?**

Nếu một email chứa cả `corp-root.pem` **và** một chuỗi SHA-256, attacker có quyền thay email sẽ thay được cả hai. Hai dữ liệu khớp nhau nhưng bạn vẫn tin CA giả.

Một expected fingerprint đủ tin cậy có thể đến từ:
- Cổng PKI chính thức được kiểm soát bằng quy trình có xác thực;
- PKI owner xác minh qua kênh độc lập;
- Một manifest có chữ ký được kiểm tra bằng khóa đã được tin cậy **từ trước**;
- Security inventory có protected change history.

**Không dùng cùng file hoặc cùng kênh chưa tin cậy để sinh cả artifact và expected fingerprint** trong production.

### 6.1. Xác minh nội dung certificate

Trước phê duyệt nên xem:
- `Subject` / `Issuer`;
- SHA-256 fingerprint của certificate DER;
- `BasicConstraints` cho CA;
- `KeyUsage` và `keyCertSign` nếu có;
- `NotBefore` / `NotAfter`;
- Public key algorithm/key length;
- Certificate signature algorithm;
- `SubjectKeyIdentifier` / `AuthorityKeyIdentifier` khi cần;
- Root/intermediate hierarchy, service scope và revocation/incident status.

Các mục trên giúp phát hiện certificate không đúng kỳ vọng, nhưng không tự chứng minh **nguồn phát hành**.

## 7. Hai SHA-256 khác nhau: certificate fingerprint và truststore digest

**Certificate fingerprint** là hash của **chứng thư X.509 dạng DER**. Dùng để xác nhận CA certificate có đúng identity đã được phê duyệt không.

```bash
keytool -printcert -file corp-root.pem
```

Tìm dòng `SHA256`; đối chiếu với fingerprint được PKI owner cung cấp qua **nguồn độc lập**.

**Truststore file digest** là hash toàn bộ bytes của `truststore.p12`:

```bash
sha256sum /opt/app/config/truststore.p12
```

Dùng để xác định artifact có đúng **file đã được build/phê duyệt** không.

| Thuộc tính | SHA-256 certificate DER | SHA-256 truststore file |
|---|---|---|
| Phạm vi | Một chứng thư CA | Toàn bộ file JKS/PKCS12 |
| Dùng để xác minh | CA identity được phê duyệt | Exact release artifact |
| Có thay đổi nếu repack PKCS12? | Không, nếu DER cert không đổi | Có thể đổi |
| Giá trị expected cần độc lập? | **Có** | **Có** |
| Thay cho chữ ký release manifest? | Không | Không |

Một truststore có thể chứa đúng một CA cũ nhưng thêm CA nguy hiểm khác. Kiểm tra duy nhất fingerprint của một entry **không** xác nhận toàn bộ truststore có đúng approved set.

## 8. Đọc `cacerts` và chứng thư bằng `keytool`

`keytool` vẫn được cung cấp trong JDK hiện đại.

Liệt kê roots có sẵn trong JDK:

```bash
keytool -list -cacerts
```

Xem chi tiết một alias đã biết:

```bash
keytool -list -v -cacerts -alias actual-ca-alias
```

`actual-ca-alias` chỉ là **tên minh họa**; phải lấy từ danh sách thực tế. Không có bảo đảm một alias tên cố định xuất hiện trên mọi JDK/vendor.

Kiểm tra một chứng thư **trước import**:

```bash
keytool -printcert -file corp-root.pem
```

Xem PKCS#12 riêng:

```bash
keytool -list -v \
    -keystore /opt/app/config/truststore.p12 \
    -storetype PKCS12
```

Đây là các **thao tác đọc**. Không đặt password production trực tiếp qua `-storepass <secret>` trong command line vì có thể bị lộ qua process list hoặc shell history.

### 8.1. `changeit` không phải cơ chế cấp quyền

File `cacerts` lịch sử thường có password khởi tạo `changeit`. Nó không phải rào chắn bí mật đáng tin để ngăn toàn bộ những người có quyền filesystem sửa hoặc thay file. Quyền **rename/replace**, ACL, ownership, image integrity và approval workflow mới là những lớp kiểm soát thiết yếu.

### 8.2. Cẩn trọng với `-noprompt`

`keytool -importcert -noprompt` có thể bỏ qua bước hỏi xác nhận. Chỉ sử dụng trong **pipeline đã có bước xác minh fingerprint và approval độc lập**, không dùng để import một file CA vừa tải về mà chưa kiểm chứng.

Nếu có lỗi PKIX, đừng lập tức import mọi server/leaf certificate thành trusted entry để “cho kết nối chạy”.

## 9. Nên sửa `cacerts` chung hay tạo truststore riêng?

**Ưu tiên truststore riêng cho ứng dụng** khi chỉ một service cần một private CA.

Ưu điểm:
- Hạn chế blast radius sang các ứng dụng khác dùng cùng JDK;
- Đơn giản hóa quyền đọc-only của service account;
- Có thể version, kiểm tra digest, rollback theo từng release;
- Không mất custom root vì update/reinstall JDK;
- Có thể áp dụng chính sách CA tối thiểu với một outbound client cụ thể.

```text
JDK base image
   +-- lib/security/cacerts     # vendor/JDK managed

Application release
   +-- app.jar
   +-- config/truststore.p12   # app scoped, approved
   +-- config/manifest         # signed/protected
   +-- runtime configuration   # references approved path
```

**Khi cần cả public roots lẫn private root**, phải chủ động tạo **merged approved store** hoặc dùng các scoped trust managers phù hợp. Với JSSE, `TrustManagerFactory.init(customStore)` không tự lấy thêm mọi root trong default `cacerts`.

### 9.1. Mẫu anti-pattern cần tránh

```bash
# KHÔNG chạy bừa trên JDK dùng chung:
keytool -importcert -cacerts \
  -alias unreviewed-ca -file random-download.pem
```

Đây là **ví dụ hành động không an toàn**, không phải lệnh thực hành. Nếu cần thay `cacerts` system-wide, đó là thay đổi bảo mật do platform/security owner quản lý, có backup, review và kiểm thử tác động nhiều ứng dụng.

## 10. Tạo truststore PKCS#12 thử nghiệm, tuyệt đối không dùng làm CA production

Để kiểm tra code, tạo một root CA giả định **trong workspace thử nghiệm**. Việc dùng self-signed certificate chỉ phù hợp cho lab. Không đem trust root này vào production.

### 10.1. Tạo root CA thử nghiệm

```bash
keytool -genkeypair \
  -alias training-root \
  -keyalg RSA -keysize 3072 \
  -sigalg SHA256withRSA \
  -validity 30 \
  -dname "CN=Training Root CA,O=Example Only,C=VN" \
  -ext "bc:c=ca:true" \
  -storetype PKCS12 \
  -keystore demo-issuer.p12
```

`keytool` hỏi password tương tác. File `demo-issuer.p12` chứa **private key của test CA**; tuyệt đối không ship file này cùng Java client.

Xuất **public certificate** dạng PEM và DER:

```bash
keytool -exportcert -rfc \
  -alias training-root \
  -file training-root.pem \
  -keystore demo-issuer.p12

keytool -exportcert \
  -alias training-root \
  -file training-root.der \
  -keystore demo-issuer.p12
```

Kiểm tra trước khi import:

```bash
keytool -printcert -file training-root.pem
sha256sum training-root.der
```

Trong bài test, SHA-256 của DER xác nhận cùng public certificate. Trong production, expected fingerprint **không** được lấy đơn thuần từ file đang cần kiểm tra.

### 10.2. Import vào truststore riêng

```bash
keytool -importcert \
  -alias training-root \
  -file training-root.pem \
  -storetype PKCS12 \
  -keystore training-truststore.p12
```

Xác nhận sau khi đã kiểm tra certificate. Tool có thể hỏi tạo password mới và xác nhận trust. Trong test trên OpenJDK 24.0.2, thao tác thành công và truststore có một `trustedCertEntry`.

```bash
keytool -list -v \
  -keystore training-truststore.p12 \
  -storetype PKCS12
```

**Mọi file và CA ở mục 10 là dữ liệu giả lập.** Tổ chức phải dùng PKI owner, signed approval manifest và certificate provenance thực tế khi triển khai production.

## 11. Chương trình hoàn chỉnh 1 — audit trusted root và fingerprint

Tạo tệp **`TrustedRootAuditDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Locale;

public class TrustedRootAuditDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 2)
            throw new IllegalArgumentException(
                    "truststore.p12 alias");

        String approved = System.getenv("APPROVED_CA_SHA256");
        String secret = System.getenv("TRUSTSTORE_PASSWORD");

        if (approved == null || secret == null)
            throw new IllegalStateException(
                    "Missing approved fingerprint or password");

        char[] password = secret.toCharArray();
        KeyStore store;
        try {
            store = KeyStore.getInstance(
                    Path.of(args[0]).toFile(), password);
        } finally {
            Arrays.fill(password, '\0');
        }

        String alias = args[1];
        if (!store.isCertificateEntry(alias))
            throw new IllegalStateException(
                    "Alias is not trusted certificate");

        X509Certificate cert = (X509Certificate)
                store.getCertificate(alias);

        String fingerprint =
                HexFormat.of().withUpperCase().formatHex(
                    MessageDigest.getInstance("SHA-256")
                        .digest(cert.getEncoded()));

        String approvedCanon =
                approved.replace(":", "")
                        .replace(" ", "")
                        .toUpperCase(Locale.ROOT);

        cert.checkValidity();

        System.out.println("fileExists=" +
                Files.isRegularFile(Path.of(args[0])));
        System.out.println("trustedEntry=" +
                store.isCertificateEntry(alias));
        System.out.println("isCA=" +
                (cert.getBasicConstraints() >= 0));
        System.out.println("timeValid=true");
        System.out.println("fingerprintApproved=" +
                fingerprint.equals(approvedCanon));
    }
}
```

Biên dịch bằng Java 17+:

```bash
javac --release 17 -encoding UTF-8 TrustedRootAuditDemo.java
```

### 11.1. Cung cấp các thông số test

Dùng Bash prompt nhập password thí nghiệm:

```bash
printf "Test truststore password: "
read -rs TRUSTSTORE_PASSWORD
printf "\n"
export TRUSTSTORE_PASSWORD

APPROVED_CA_SHA256="$(sha256sum training-root.der | awk '{print $1}')"
export APPROVED_CA_SHA256
```

**Lưu ý:** expected SHA-256 ở đây được tạo cùng file **chỉ để smoke test**. Với production, nó phải đến từ **kênh phê duyệt độc lập** hoặc signed manifest. Environment variables cũng không bí mật tuyệt đối; trong production dùng secret manager/OS protected configuration.

Chạy:

```bash
java TrustedRootAuditDemo training-truststore.p12 training-root
```

**Stdout đã kiểm chứng trên OpenJDK 24.0.2:**

```text
fileExists=true
trustedEntry=true
isCA=true
timeValid=true
fingerprintApproved=true
```

### 11.2. Những gì ví dụ thực sự chứng minh

- File tồn tại và là regular file ở thời điểm kiểm tra.
- Alias thuộc loại **certificate entry**, không phải private-key entry.
- `BasicConstraints` xác nhận certificate có CA flag.
- `checkValidity()` kiểm tra thời hạn theo ngày hiện tại.
- Fingerprint của cert DER khớp approved value đã cung cấp.

**Không chứng minh:** approved value thực sự đến từ PKI owner, certificate chưa bị revoke, TLS chain/hostname hợp lệ hoặc security policy đã được review.

### 11.3. Tại sao không dùng password string trực tiếp trong code?

Lưu password production như literal `"changeit"` hoặc in ra log là không phù hợp. Chương trình đọc từ environment **chỉ để đơn giản hóa lab**, chuyển sang `char[]` khi nạp `KeyStore` và xóa mảng sau đó.

Nhưng `System.getenv` vẫn cho `String` không thể chủ động zeroize và biến môi trường có nguy cơ lộ. Production nên sử dụng secret-management mechanism theo chính sách tổ chức.

## 12. Chương trình hoàn chỉnh 2 — `TrustManagerFactory` và `SSLContext` riêng

Tạo tệp **`ApplicationTrustContextDemo.java`**:

```java
import java.nio.file.Path;
import java.security.KeyStore;
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManager;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509TrustManager;

public class ApplicationTrustContextDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1)
            throw new IllegalArgumentException(
                    "truststore.p12");

        String secret = System.getenv("TRUSTSTORE_PASSWORD");
        if (secret == null)
            throw new IllegalStateException("Missing password");

        char[] password = secret.toCharArray();
        KeyStore store;
        try {
            store = KeyStore.getInstance(
                    Path.of(args[0]).toFile(), password);
        } finally {
            Arrays.fill(password, '\0');
        }

        TrustManagerFactory factory =
                TrustManagerFactory.getInstance(
                    TrustManagerFactory.getDefaultAlgorithm());

        factory.init(store);
        int count = 0;
        boolean found = false;

        for (TrustManager tm : factory.getTrustManagers()) {
            if (tm instanceof X509TrustManager x509) {
                found = true;
                count += x509.getAcceptedIssuers().length;
            }
        }

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(
                null, factory.getTrustManagers(), null);

        System.out.println("x509ManagerFound=" + found);
        System.out.println("trustedIssuerCount=" + count);
        System.out.println("customContextInitialized=" +
                (context.getSocketFactory() != null));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ApplicationTrustContextDemo.java
java ApplicationTrustContextDemo training-truststore.p12
```

Với test truststore chỉ chứa một root:

```text
x509ManagerFound=true
trustedIssuerCount=1
customContextInitialized=true
```

**Đã kiểm chứng trên OpenJDK 24.0.2.**

### 12.1. Vì sao app-scoped context tốt?

`TrustManagerFactory.init(store)` chỉ rõ tập trust material. `context.init(null, factory.getTrustManagers(), null)` xây dựng một context cho những TLS clients được cấu hình dùng nó. Không sửa JDK `cacerts` hoặc global `javax.net.ssl.trustStore`.

Tuy nhiên:
- Khởi tạo context thành công **chưa phải TLS handshake**.
- Chương trình chưa kiểm tra certificate path của server thật.
- Chưa bật/test hostname verification trong một HTTPS client thực tế.
- Chưa kiểm chứng CRL/OCSP policy.
- Một custom truststore **không tự merge** default public roots.

Trong ứng dụng thật phải **truyền context đúng cho HTTP/TLS client** và bảo đảm endpoint identification/hostname verification không bị tắt.

### 12.2. Truststore không chứa private signing key

File `demo-issuer.p12` trong lab chứa private key của CA; **không được đưa vào chương trình client**. `training-truststore.p12` chỉ chứa certificate công khai, đúng phạm vi TLS trust.

## 13. Chương trình hoàn chỉnh 3 — kiểm tra file artifact SHA-256

Để chống file truststore bị thay đổi trái phép so với artifact đã được phê duyệt, có thể dùng digest check.

Tạo **`TruststoreDigestGateDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public class TruststoreDigestGateDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1)
            throw new IllegalArgumentException(
                    "truststore.p12");

        String approved =
                System.getenv("APPROVED_STORE_SHA256");

        if (approved == null ||
                !approved.matches("[0-9A-Fa-f]{64}"))
            throw new IllegalStateException(
                    "Approved SHA-256 missing/invalid");

        Path path = Path.of(args[0]);
        if (!Files.isRegularFile(
                path, LinkOption.NOFOLLOW_LINKS))
            throw new IllegalStateException(
                    "Not regular non-symlink file");

        byte[] hash = MessageDigest.getInstance("SHA-256")
                .digest(Files.readAllBytes(path));

        String actual = HexFormat.of()
                .withUpperCase().formatHex(hash);

        System.out.println("regularFile=true");
        System.out.println("approvedDigest=" +
                actual.equalsIgnoreCase(approved));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 TruststoreDigestGateDemo.java

APPROVED_STORE_SHA256="$(sha256sum training-truststore.p12 | awk '{print $1}')"
export APPROVED_STORE_SHA256

java TruststoreDigestGateDemo training-truststore.p12
```

**Stdout đã kiểm chứng trên truststore thí nghiệm:**

```text
regularFile=true
approvedDigest=true
```

Thử thay **một bản sao**, không sửa file gốc:

```bash
cp training-truststore.p12 tampered.p12
printf 'X' >> tampered.p12
java TruststoreDigestGateDemo tampered.p12
```

**Stdout đã kiểm chứng tương đương:**

```text
regularFile=true
approvedDigest=false
```

### 13.1. Hash chỉ hữu ích khi approved value thực sự đáng tin

Nếu attacker sửa được cả file `.p12` và expected hash, chương trình có thể vẫn in true. Trong production, expected hash phải gắn với **signed release manifest**, protected approval record hoặc một control plane khác quyền.

### 13.2. Symlinks và TOCTOU

`Files.isRegularFile(path, NOFOLLOW_LINKS)` từ chối input là symlink ở path cuối trong demo, nhưng đây **không** phải yêu cầu bắt buộc của Java TLS. Kubernetes ConfigMap/Secret projected volumes thường sử dụng symlinks để cập nhật atomically; thiết kế thật phải xác minh **real target/version/permissions** theo cơ chế triển khai.

Vẫn có rủi ro **time-of-check/time-of-use (TOCTOU)** khi file được thay sau hash check trước lúc ứng dụng nạp nó. Bảo vệ bằng image/mount bất biến, quyền thư mục và pipeline, không dựa duy nhất vào một lần hash check.

## 14. Chương trình hoàn chỉnh 4 — kiểm tra default trust managers của runtime

Tạo tệp **`DefaultTrustManagerProbe.java`**:

```java
import java.security.KeyStore;
import javax.net.ssl.TrustManager;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509TrustManager;

public class DefaultTrustManagerProbe {
    public static void main(String[] args) throws Exception {
        TrustManagerFactory factory =
                TrustManagerFactory.getInstance(
                    TrustManagerFactory.getDefaultAlgorithm());

        factory.init((KeyStore) null);

        boolean found = false;
        boolean hasRoots = false;

        for (TrustManager tm : factory.getTrustManagers()) {
            if (tm instanceof X509TrustManager x509) {
                found = true;
                hasRoots |=
                    x509.getAcceptedIssuers().length > 0;
            }
        }

        System.out.println("x509ManagerFound=" + found);
        System.out.println("trustedIssuersPresent=" + hasRoots);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DefaultTrustManagerProbe.java
java DefaultTrustManagerProbe
```

**Stdout đã kiểm chứng với OpenJDK 24.0.2 không đặt truststore override:**

```text
x509ManagerFound=true
trustedIssuersPresent=true
```

Giá trị `trustedIssuersPresent` **không cố định** trên mọi runtime. Nếu trustStore property trỏ đến một file không tồn tại hoặc được cấp empty store, giá trị có thể là false.

Một tập issuers không rỗng cũng không chứng minh **TLS tới bất kỳ hostname cụ thể nào** thành công. Cần thực hiện TLS handshake/hostname/path validation thực tế.

## 15. Least privilege cho file truststore và thư mục cha

**Chỉ bảo vệ quyền ghi file là chưa đủ.** Trên nhiều filesystem, một user có quyền ghi thư mục chứa file có thể thay thế file qua rename/delete, dù file cũ đọc-only.

Ví dụ:

```text
/opt/
  app/
    config/
      truststore.p12
      approved-manifest.json
```

Cần bảo vệ:
- **File truststore**;
- **Directory chứa file**;
- Những **parent directories** có khả năng bị attacker đổi tên/thay đường dẫn;
- **Manifest** xác nhận artifact;
- **Startup arguments/system properties** quyết định đường dẫn JSSE đọc;
- CI/CD artifacts, container image và deployment configuration.

Oracle JDK 27 Security Properties File cũng nhấn mạnh quyền của parent-directory chain đối với những included security configurations, vì một user có quyền đổi file/đường dẫn có thể làm JVM sử dụng policy không được phê duyệt.

### 15.1. Linux — kiểm tra quyền read-only

```bash
ls -ld /opt /opt/app /opt/app/config
ls -l /opt/app/config/truststore.p12
namei -l /opt/app/config/truststore.p12
stat /opt/app/config/truststore.p12
```

Đây là **lệnh quan sát**, không sửa permissions. `namei` có thể chưa được cài sẵn trên một số distro.

Mô hình quyền phù hợp:
- Admin/deployment owner sở hữu thư mục;
- Service user cần **read** truststore và **traverse** các thư mục;
- Service user không được **write/replace/delete** truststore hoặc thư mục cha;
- Không cấp `world-write` cho security directory;
- Container dùng non-root service account, filesystem/mount read-only khi phù hợp.

**Không** dùng `chmod -R 777` hoặc `chown -R app:app` để chữa lỗi `Permission denied` nếu làm application có quyền sửa truststore.

### 15.2. Windows — xem NTFS ACL

```powershell
icacls "C:\app\config\truststore.p12"
icacls "C:\app\config"
```

Cần xem quyền `Read`/`Modify`/`Write`/`Delete`, nhóm kế thừa, owner và quyền thay đổi thư mục. Thuộc tính Read-only của một file **không thay thế** NTFS ACL/parent directory security.

### 15.3. Quyền của Java process

Java client chỉ cần **đọc** truststore hoặc lấy trust material qua provider/HSM được cấu hình. Nó không cần quyền `keytool -importcert`, `keytool -delete` hay sửa `java.security` trong lúc xử lý request.

Nếu ứng dụng bị khai thác và process có quyền ghi truststore, attacker có thể tạo **persistent trust-policy change** kéo dài sang những kết nối sau.

## 16. Docker, Kubernetes và root CA governance

### 16.1. Build immutable image

Với Docker:
- Pin JDK base image theo version/digest;
- Dùng file truststore app-scoped/versioned;
- Build truststore từ **approved CA certificates** tại build/release pipeline;
- Ký hoặc kiểm tra provenance của release;
- Ở runtime chỉ mount/read artifact;
- Không chạy `keytool -importcert -cacerts` mỗi lần container start;
- Mỗi JDK upgrade cần kiểm tra lại baseline roots và TLS security properties.

Không giữ private CA signing key trong image Java client.

### 16.2. Kubernetes ConfigMap vs Secret

**CA public certificate** không phải bí mật, nhưng quyền **thay nó** là quyền bảo mật.

- ConfigMap có thể chứa public roots nếu RBAC giới hạn người sửa, có admission/review và read-only mount;
- Password của truststore hoặc private-key material cần secret manager/Kubernetes Secret theo policy;
- Kubernetes Secret không tự đảm bảo provenance nếu người không được phê duyệt vẫn có quyền update resource;
- Projected volume có thể thay dữ liệu qua symlinks, cần xử lý reload/version phù hợp;
- Kiểm soát cả deployment manifest/startup command để attacker không trỏ JSSE tới store khác.

**Không** kết luận read-only mount bảo vệ được khi attacker còn có quyền update ConfigMap/Secret ở Kubernetes API control plane.

### 16.3. Rotation có version và rollout

Khi trust anchors thay đổi, tạo **truststore release mới** và rollout có kiểm soát. Nhiều TLS clients khởi tạo trust manager một lần rồi cache; thay file dưới chân process không đảm bảo mọi kết nối đang chạy tự động nhận set mới. Nếu không có cơ chế reload đáng tin, **restart/rollout** workloads theo chính sách.

## 17. Truststore password, secret handling và dữ liệu nhạy cảm

`cacerts` thường có password khởi tạo `changeit`; **đừng xem đó là secret mạnh hay cơ chế authorization duy nhất**.

Một truststore PKCS#12 có thể dùng password để kiểm tra integrity và các chức năng tùy format/provider. Dù chỉ có public certificates, **tính toàn vẹn của nội dung vẫn quan trọng**.

Không đưa password thật qua process arguments:

```bash
# Anti-pattern, KHÔNG sử dụng mật khẩu thật:
java -Djavax.net.ssl.trustStorePassword=production-password -jar app.jar
```

Giải pháp:
- Secret manager/HSM khi phù hợp;
- File cấu hình có ACL phù hợp;
- Prompt tương tác trong quản trị;
- Khởi tạo `KeyStore` và `SSLContext` theo code từ protected secret source;
- Giới hạn access tới process environment, command line, CI logs, crash dumps.

**Environment variable không bí mật tuyệt đối**. Các demo dùng env chỉ để đơn giản hóa chương trình test. `Arrays.fill(password, '\0')` xóa mảng `char[]` ở một điểm, nhưng không tự xóa `String` đã đọc từ env hoặc mọi copy trong memory.

### 17.1. Truststore password khác private-key password

Một private-key keystore cần bảo vệ cả **bí mật và toàn vẹn của khóa riêng**. Một CA truststore chỉ chứa public roots có ưu tiên lớn về **integrity, provenance và quyền sửa**, không chỉ khả năng giấu byte certificate.

Nếu một app chỉ xác thực HTTPS server, **không** cần cung cấp CA private key hay mTLS client private key một cách vô cớ.

## 18. Quy trình thêm root CA có phê duyệt

### Bước 1: xác định nhu cầu

Đừng coi mọi lỗi TLS là thiếu root. Xác nhận host/port, proxy, certificate chain, hostname/SAN, thời gian, TLS provider và thuật toán.

### Bước 2: nhận chứng thư và expected fingerprint độc lập

Nhận public certificate từ PKI owner/official repository; nhận approved fingerprint qua kênh riêng hoặc signed manifest.

### Bước 3: inspect trước khi trust

```bash
keytool -printcert -file corp-root.pem
```

Xác nhận SHA-256 fingerprint, Subject/Issuer, BasicConstraints CA, KeyUsage, validity, algorithms và service scope.

### Bước 4: import vào artifact riêng

```bash
keytool -importcert \
  -alias corp-root-approved \
  -file corp-root.pem \
  -keystore app-truststore.p12 \
  -storetype PKCS12
```

Đây là thao tác **ghi vào file ứng dụng được chỉ định**, không phải `-cacerts`. Chỉ thực hiện khi certificate và change đã được phê duyệt. Để tool hỏi password và xác nhận. Nếu pipeline cần noninteractive import, phải có independent verification **trước**.

### Bước 5: kiểm tra sau import

```bash
keytool -list -v -keystore app-truststore.p12 -storetype PKCS12
sha256sum app-truststore.p12
```

Ghi CA fingerprint, artifact digest, version và review record vào manifest có chữ ký/ACL độc lập.

### Bước 6: QA kết nối

- TLS tới endpoint được phê duyệt phải thành công;
- DNS hostname verification phải còn bật;
- Endpoint dùng CA chưa phê duyệt phải **không** tự được tin;
- Nếu dùng custom truststore, test cả public roots cần thiết;
- Không dùng `trust-all` fallback khi certificate path validation thất bại.

### Bước 7: phát hành và theo dõi

Deploy least privilege; giám sát truststore drift, failures, certificate expiry và JDK security changes. Có phương án rollback phù hợp khi CA mới gây outage.

## 19. Gỡ bỏ và rotation root CA

Khi một private PKI chuyển sang root mới:
1. PKI owner phát hành root mới và independent fingerprint;
2. Security phê duyệt overlap policy;
3. Thêm root mới vào truststore phiên bản mới;
4. Test endpoints cũ/mới;
5. Cut over servers sang chain mới;
6. Sau thời hạn policy, gỡ root cũ;
7. Test rằng old CA không được tin nếu policy yêu cầu.

Không để root cũ mãi trong truststore chỉ vì sợ thay đổi.

Ví dụ **chỉ dùng trên bản sao được quản lý**:

```bash
keytool -delete \
  -alias corp-root-obsolete \
  -keystore app-truststore.p12 \
  -storetype PKCS12
```

Lệnh thay file thật; **không chạy trên live shared `cacerts`** nếu chưa có change approval/backup/rollback. Alias là tên minh họa, phải xác minh trong store trước.

### 19.1. Nếu root bị compromise

- Kích hoạt incident response;
- Xem xét gỡ trust anchor/chain và thay certificates bị ảnh hưởng;
- Roll out truststore policy mới có ưu tiên;
- Audit nguồn cấp phát, publish, quyền ghi và log;
- Không chỉ chờ NotAfter vì rủi ro có thể tồn tại trong thời hạn certificate;
- Phối hợp revocation và endpoint changes theo chính sách PKI.

## 20. JDK update, thuật toán bị vô hiệu và trust policy

JDK updates có thể **thêm hoặc gỡ root CA certificates** và thay các security properties. Hai JDK cùng major nhưng khác build/vendor không nên bị giả định có truststore/policy giống hệt.

Những security properties quan trọng gồm:

```text
jdk.certpath.disabledAlgorithms
jdk.tls.disabledAlgorithms
ssl.TrustManagerFactory.algorithm
```

Được cấu hình trong `<java.home>/conf/security/java.security` với các cơ chế tùy bản JDK.

**Không hạ mức bảo mật** bằng cách gỡ algorithm restrictions chỉ để một certificate cũ hoạt động. Nên nâng cấp server certificate/chain và dùng thuật toán/key sizes được phép.

Một số quy tắc certificate-path áp dụng **khác nhau cho trust anchors** so với certificates trung gian; không suy từ `checkValidity()` hoặc một dòng `jdk.certpath.disabledAlgorithms` rằng mọi tiêu chí tự động được áp y hệt lên root.

### 20.1. Parent directories của security properties

Oracle JDK 27 hướng dẫn bảo vệ cả **file include** và **đường dẫn thư mục cha** của security configurations. Nếu attacker có quyền thay một included file hoặc rename directory, họ có thể hạ security policy.

Nguyên tắc tương tự áp dụng cho truststore:
- Kiểm soát file và parent directories;
- Chỉ cho pipeline/administrator đáng tin cập nhật;
- Kiểm tra startup properties để tránh trỏ file thay thế;
- Bảo vệ environment và deployment configs.

## 21. Xác thực TLS còn gì ngoài truststore?

| Điều kiện | Cần kiểm tra | Chỉ thêm CA là đủ? |
|---|---|---|
| Trust anchor | Chain nối tới CA được tin | Thêm CA thay tập anchor |
| Chain signatures | Các chứng thư trong chain có ký hợp lệ | Không |
| Time validity | NotBefore/NotAfter phù hợp | Không |
| Hostname/SAN | Host đang kết nối trùng danh tính chứng thư | Không |
| Extended Key Usage | Mục đích TLS server phù hợp | Không |
| Algorithm constraints | Signature/key strength được chấp nhận | Không |
| Revocation policy | CRL/OCSP hoặc cơ chế được tổ chức yêu cầu | Không |
| Endpoint ownership | App đang gọi đúng DNS/service/proxy | Không |

**Không viết `X509TrustManager` trả thành công vô điều kiện trong `checkServerTrusted`**, hoặc `HostnameVerifier` luôn trả true. Các workaround kiểu này biến một vấn đề certificate thành lỗ hổng MITM.

**`SSLContext.init(...)` thành công chưa chứng minh handshake thật đã được xác thực.** Phải test TLS client dùng context mới, với hostname checking và trust policy đầy đủ.

### 21.1. Revocation không được giả định luôn bật

Certificate nằm trong truststore không chứng minh rằng mọi TLS connection đang kiểm tra OCSP/CRL. Revocation phụ thuộc provider, PKIX parameters, network settings và policy. Kiểm tra yêu cầu của ứng dụng và đúng JDK runtime; tránh khẳng định mọi JDK mặc định kiểm tra revocation giống nhau.

## 22. Xử lý `PKIX path building failed` theo thứ tự

Khi gặp TLS lỗi:

1. Xác định chính xác endpoint, DNS/port và proxy;
2. Kiểm tra server gửi đủ intermediate certificates;
3. Xác nhận hostname/SAN;
4. Xác nhận clock và validity dates;
5. Xem effective `javax.net.ssl.trustStore` và file có thật không;
6. Xem `jssecacerts` có làm thay `cacerts` không;
7. Kiểm tra CA fingerprint với approved PKI record;
8. Kiểm tra disabledAlgorithms và certificate key strengths;
9. Xem có custom `SSLContext` hoặc provider không;
10. Đối chiếu revocation/mTLS settings và security events;
11. Chỉ import CA sau khi xác định đúng nhu cầu và được phê duyệt.

Trong staging có thể dùng:

```bash
java -Djavax.net.debug=ssl,handshake,trustmanager -jar app.jar
```

Debug logs có thể chứa hostnames, chain metadata, đường dẫn và thông tin nhạy cảm, nên kiểm soát quyền đọc và tắt sau khi chẩn đoán.

**Lỗi TLS không phải lý do bỏ qua xác thực chứng thư.**

## 23. TOCTOU, signed manifest và supply-chain integrity

Một file hash đúng tại thời điểm T không bảo đảm file sẽ không đổi ở T+1. Nếu app runtime hoặc attacker có quyền thay file/symlink/parent directory sau hash check, có thể có **time-of-check/time-of-use**.

Mô hình đáng tin:

```text
Approved CA inventory -- fingerprint (cert DER)
   |
   v
Signed build manifest -- truststore file SHA-256 + version + scope
   |
   v
Immutable artifact (image / read-only volume)
   |
   v
Application reads the approved truststore
   |
   v
Runtime monitoring / rollback / incident response
```

Expected digests phải nằm trong control plane/manifest mà attacker **không sửa được cùng quyền với truststore**. Nếu attacker thay cả file và hash file, một phép so hash đơn giản không phát hiện được.

Tích hợp phù hợp:
- Protected CI/CD workflow và code review;
- Signed manifests/attestations;
- Immutable image digest và registry permissions;
- Kubernetes RBAC/admission;
- Read-only filesystem và non-root process;
- Không trao quyền write/rename cho application service;
- Audit log CA onboarding/removal.

## 24. Bảng quyết định

| Tình huống | Cách làm phù hợp | Tại sao |
|---|---|---|
| Một Java service cần private CA | App-scoped PKCS#12 truststore | Giảm blast radius |
| Một outbound client đặc thù cần CA riêng | `SSLContext` riêng cho client đó | Giữ chính sách phần còn lại không đổi |
| Nhiều services cần enterprise root | Quản lý PKI/truststore tập trung có approval | Có governance thống nhất |
| App cần cả public và internal CAs | Merged approved store hoặc scoped managers | Custom store không tự merge `cacerts` |
| Client cần mTLS certificate | Private-key keystore + `KeyManager` | Khác với truststore CA |
| Server thiếu intermediate | Sửa server chain hoặc cấu hình PKI | Không import leaf bừa |
| Root compromise | Gỡ root/rotate theo incident plan | Ngăn tiếp tục tin CA không an toàn |
| JDK nâng cấp | So root baseline và crypto policy, chạy QA | Tránh thay đổi trust ngoài ý muốn |
| Kubernetes projected truststore | RBAC, read-only volume, version/reload policy | Control plane có thể thay nội dung |
| Certificate chưa xác thực fingerprint | **Không import** | Rủi ro chèn CA giả |
| “Cho mọi TLS cert pass” | **Không được** | Loại bỏ xác thực danh tính |

## 25. Sai lầm phổ biến

| Hiểu nhầm | Sự thật |
|---|---|
| “JEP 319 làm mọi CA đáng tin.” | Không, nó cung cấp một root set mặc định trên những bản JDK phù hợp. |
| “Root tự ký là đủ đáng tin.” | Tự ký không chứng minh nguồn gốc. |
| “Public CA cert không bí mật nên ai cũng được sửa truststore.” | Integrity và quyền sửa **rất nhạy cảm**. |
| “Subject `CN` trông đúng là đủ.” | Có thể bị giả mạo; phải verify fingerprint độc lập. |
| “Fingerprint gửi cùng file là bằng chứng mạnh.” | Không nếu cùng kênh có thể bị thay cả hai. |
| “Hash `.p12` chính là fingerprint root cert.” | Không; file bytes khác certificate DER. |
| “Java có `cacerts` thì mọi HTTP client đều dùng file ấy.” | Có trustStore overrides, custom contexts/providers. |
| “`jssecacerts` luôn bổ sung vào `cacerts`.” | SunJSSE ưu tiên `jssecacerts`, không tự merge. |
| “trustStore path không tồn tại sẽ fallback.” | SunJSSE có thể tạo empty trust manager. |
| “`changeit` là đủ bảo vệ `cacerts`.” | Không; ACL/parent dirs/provenance quan trọng. |
| “chmod readonly file là đủ.” | Parent directory có thể cho quyền replace. |
| “Service cần quyền write truststore để gọi HTTPS.” | Thông thường chỉ cần read. |
| “`-noprompt` an toàn với mọi certificate.” | Chỉ dùng sau verify/approval độc lập. |
| “Lỗi `PKIX` luôn do thiếu root.” | Có thể do chain, hostname, time, crypto constraints hoặc config. |
| “`checkValidity()` chứng minh PKI chain đáng tin.” | Không, nó chỉ kiểm tra ngày hợp lệ của một cert. |
| “`SSLContext` init xong nghĩa TLS server trusted.” | Còn cần handshake và hostname verification. |
| “Root nằm trong store nghĩa OCSP luôn được kiểm tra.” | Không; revocation tùy policy/provider. |
| “Kubernetes Secret là immutable/trusted về nguồn.” | Người có quyền update vẫn có thể thay resource. |
| “Truststore hash match ngăn mọi TOCTOU.” | Không, cần hạn chế thay file sau check. |
| “Nâng JDK root set không đổi.” | JDK/vendor updates có thể thêm/gỡ root và đổi policies. |
| “Truststore để giữ private key của CA.” | Không cần private CA key để xác thực TLS. |

## 26. Checklist bảo mật trước release

- [ ] Đã mô tả rõ endpoint, environment và lý do cần CA?
- [ ] Public root certificate đến từ PKI/CA owner được xác thực?
- [ ] SHA-256 fingerprint được kiểm tra **qua kênh độc lập**?
- [ ] `BasicConstraints`, `KeyUsage`, validity, algorithms và chain scope đã được xem?
- [ ] Private key CA không nằm trong truststore artifact?
- [ ] Security/app owner đã phê duyệt thay đổi trust boundary?
- [ ] Truststore version/digest/signed manifest/provenance rõ ràng?
- [ ] Build pipeline đã kiểm tra approved CA inputs trước `importcert`?
- [ ] Application runtime không thể write/replace/rename truststore?
- [ ] Parent directories, startup config, symlinks và ownership được kiểm soát?
- [ ] Container/Kubernetes RBAC và image digest được bảo vệ?
- [ ] Password không xuất hiện trong process args, Git hoặc logs?
- [ ] Effective default trustStore/`jssecacerts`/`cacerts` đúng như mong muốn?
- [ ] Custom store không vô tình làm mất public CA roots cần thiết?
- [ ] TLS đến authorized hosts qua full chain+hostname checks thành công?
- [ ] Negative test: unauthorized root/cert bị từ chối?
- [ ] Revocation, expiry, rotation và incident response có owners?
- [ ] Đã QA JDK security update và algorithm restrictions?
- [ ] Có alert truststore drift và kế hoạch rollback?

### Nhận xét review mẫu

> “Root certificate được gửi cùng fingerprint trong một email chưa xác minh. Trước khi import, cần so SHA-256 DER fingerprint với PKI record được phê duyệt **độc lập**, tạo truststore versioned và giới hạn quyền ghi.”

Nhận xét khác:

> “File truststore readonly nhưng app UID có quyền ghi parent directory. Cần bảo vệ quyền replace/rename, chọn read-only mount và tách release pipeline khỏi runtime.”

## 27. Câu hỏi ôn tập có đáp án

**1.** Java 10 có JEP nào liên quan root CAs?

**Đáp án:** **JEP 319 — Root Certificates**.

**2.** Self-signed root certificate có tự đáng tin không?

**Đáp án:** Không. Trust là quyết định chính sách cần provenance.

**3.** Ai nên có quyền sửa truststore production?

**Đáp án:** Chỉ nhóm/pipeline quản trị được ủy quyền theo change control; process ứng dụng thường chỉ đọc.

**4.** SHA-256 certificate fingerprint khác file hash ra sao?

**Đáp án:** Một cái định danh cert DER; cái kia định danh bytes của truststore artifact.

**5.** Vì sao cần nguồn fingerprint độc lập?

**Đáp án:** Vì một attacker có thể thay cả file và fingerprint trong cùng kênh không an toàn.

**6.** SunJSSE chọn truststore theo thứ tự nào?

**Đáp án:** Explicit `javax.net.ssl.trustStore`, sau đó `jssecacerts` nếu không explicit, rồi `cacerts`.

**7.** File explicit trustStore không tồn tại có chắc fallback `cacerts` không?

**Đáp án:** Không. SunJSSE có thể tạo empty truststore.

**8.** Custom `TrustManagerFactory.init(store)` có tự cộng public roots vào không?

**Đáp án:** Không; phải thiết kế merged set hoặc scoped contexts phù hợp.

**9.** Truststore client có cần private key root CA không?

**Đáp án:** Không, public CA certificate/trust anchor là đủ.

**10.** Root CA import rồi đã bỏ được hostname checking chưa?

**Đáp án:** Không. Hostname/SAN vẫn phải được xác thực.

**11.** `cert.checkValidity()` đã kiểm tra certificate chain/revocation chưa?

**Đáp án:** Chưa. Nó chỉ kiểm tra thời hạn chứng thư.

**12.** Chỉ chmod readonly `truststore.p12` có đủ không?

**Đáp án:** Không, còn phải kiểm soát parent directories và quyền replace path.

**13.** Kubernetes ConfigMap chứa CA public root có cần RBAC không?

**Đáp án:** Có. Quyền sửa CA trong ConfigMap là quyền thay trust boundary.

**14.** `-noprompt` có an toàn mặc định không?

**Đáp án:** Không. Chỉ dùng khi fingerprint/provenance đã được xác minh độc lập.

**15.** Vì sao cần test TLS thật sau khi init `SSLContext`?

**Đáp án:** Vì init chỉ xác nhận context được tạo; còn cần chain, hostname, algorithm và endpoint validation.

**16.** Khi JDK update cần kiểm tra điều gì?

**Đáp án:** Root set, algorithm policies, provider/JSSE behavior và ảnh hưởng tới outbound services.

**17.** Root bị compromise nên đợi hết hạn?

**Đáp án:** Không. Kích hoạt incident response, gỡ/thay trust theo chính sách và cấp chứng thư mới.

**18.** File hash expected nằm cùng thư mục writable với truststore có đủ bảo vệ không?

**Đáp án:** Không. Attacker có thể thay cả hai; cần signed/independent manifest và filesystem controls.

## 28. Tài liệu chính thức

- [OpenJDK JEP 319 — Root Certificates](https://openjdk.org/jeps/319): mục tiêu đưa root CA certificates vào OpenJDK ở Java 10.
- [Oracle JDK 10 Release Notes — JEP 319](https://www.oracle.com/java/technologies/javase/10-relnote-issues.html): lịch sử root set.
- [Oracle JDK 27 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/27/security/java-secure-socket-extension-jsse-reference-guide.html): default truststore selection, `TrustManagerFactory`, `SSLContext`, trust decisions.
- [Oracle JDK 25 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html): truststore configuration và API vẫn áp dụng.
- [Oracle JDK 24 — `keytool`](https://docs.oracle.com/en/java/javase/24/docs/specs/man/keytool.html): `-list -cacerts`, `-printcert`, `-importcert` và `-delete`.
- [Oracle JDK 27 — Security Properties File](https://docs.oracle.com/en/java/javase/27/security/security-properties-file.html): `java.security`, disabled algorithms và bảo vệ parent directories.
- [Oracle Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/26/security/java-pki-programmers-guide.html): trust anchors, certification paths, algorithm constraints.
- [Oracle Java SE 25 — `KeyStore`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyStore.html): certificate entries và private-key entries.
- [Oracle Java SE 25 — `TrustManagerFactory`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): tạo trust managers từ truststore.
- [Oracle Java SE 25 — `SSLContext`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLContext.html): TLS contexts dùng riêng cho client.
- [Oracle Java SE 25 — `X509Certificate`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/cert/X509Certificate.html): `getEncoded`, `checkValidity`, `getBasicConstraints`.
- [Oracle Java SE 25 — `MessageDigest`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/MessageDigest.html): SHA-256.
- [Kubernetes — ConfigMap](https://kubernetes.io/docs/concepts/configuration/configmap/): phân phối cấu hình phải đi kèm RBAC/rollout.
- [Kubernetes — Good Practices for Secrets](https://kubernetes.io/docs/concepts/security/secrets-good-practices/): bảo vệ mật khẩu/khóa nhạy cảm.

**Kết luận:** JEP 319 làm root certificates mặc định dễ dùng hơn trong OpenJDK, nhưng **quản lý nguồn gốc và quyền sửa truststore** vẫn là trách nhiệm bảo mật chủ động. Chỉ import CA được xác minh SHA-256 từ nguồn phê duyệt **độc lập**, tạo truststore có scope rõ ràng, bảo vệ file **và thư mục cha**, giữ runtime chỉ đọc, triển khai theo signed/versioned artifacts và tuyệt đối không sửa lỗi TLS bằng trust-all hoặc tắt hostname verification.