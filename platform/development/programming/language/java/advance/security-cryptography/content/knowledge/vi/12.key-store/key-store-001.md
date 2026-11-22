# 12.1 Mô hình KeyStore và phân biệt với truststore hoặc CertStore

Trong Java Cryptography Architecture (JCA), **`KeyStore`** là một API quản lý **khóa mật mã và chứng chỉ** dưới những tên gọi (*alias*) có thể tra cứu. Trong hệ thống TLS/PKI, người ta còn nói **keystore**, **truststore** và **`CertStore`**. Ba thuật ngữ nghe gần giống, nhưng khác nhau về **loại dữ liệu**, **mục đích**, **cách sử dụng trong cơ chế xác thực** và **khái niệm tin cậy**:

- **KeyStore** (viết hoa) là **class/API JCA** `java.security.KeyStore` có các entry như private key kèm certificate chain, secret key, hoặc certificate được đánh dấu tin cậy.
- **keystore dùng làm kho danh tính** (*identity keystore*, thường viết thường) là **vai trò triển khai** của một `KeyStore`: nơi ứng dụng tìm private key và certificate chain của **chính mình** để ký/chứng minh danh tính.
- **truststore** là **vai trò triển khai** của một `KeyStore`: nơi lưu chứng chỉ/điểm tin cậy mà ứng dụng sử dụng để **đánh giá bên đối tác**. Java không có một JCA class tiêu chuẩn độc lập tên `TrustStore`.
- **`CertStore`** là **API khác** thuộc `java.security.cert`, chuyên **tìm/thu thập certificates và CRLs** làm dữ liệu *ứng viên* để xây dựng hoặc kiểm tra đường dẫn chứng chỉ. Có certificate trong `CertStore` **không khiến nó trở thành trusted**.

Bài thuộc nhóm **12. KeyStore** và hướng tới Java 17+. Ta sẽ xây dựng mental model, đối chiếu cấu trúc và luồng TLS, thực hành lưu/đọc PKCS#12, tạo identity keystore + truststore bằng `keytool`, dùng `KeyManagerFactory`, `TrustManagerFactory`, `CertStore` và `PKIXParameters`, rồi phân tích những sai lầm thường gặp trong production.

## 1. Hình dung bốn thành phần trong một kết nối TLS

Một JVM có thể đồng thời cần **chứng minh danh tính của mình** và **kiểm chứng danh tính của bên kia**. Hai trách nhiệm này đi qua những đối tượng khác nhau:

```text
                       ỨNG DỤNG JAVA / TLS
                               |
              +----------------+----------------+
              |                                 |
       "Tôi là ai?"                       "Tôi tin ai?"
              |                                 |
    Identity KeyStore                      Truststore
    +--------------------+                 +----------------------+
    | alias: server      |                 | alias: trusted-ca     |
    | PrivateKeyEntry    |                 | TrustedCertificate-   |
    | - PRIVATE KEY      |                 | Entry (CA/cert được   |
    | - leaf cert        |                 | chấp thuận)          |
    | - chain (nếu có)   |                 +----------------------+
    +--------------------+                           |
              |                                      |
    KeyManagerFactory                       TrustManagerFactory
              |                                      |
              v                                      v
        KeyManager[]                           TrustManager[]
              |                                      |
              +------------- SSLContext -------------+
                                     |
                      Handshake TLS xác thực
                                     |
                      +--------------+--------------+
                      |                             |
              certificate chain               trust anchor
                bên đối tác                    từ truststore
                      |                             |
                      v                             v
              CertPathBuilder/             CertPathValidator/
              CertPathValidator             PKIX trust policy
                      ^                             ^
                      |                             |
              CertStore (certificates/CRLs ứng viên,
              tra cứu để tìm intermediate/revocation)
```

Sơ đồ biểu diễn **vai trò logic**, không phải mọi provider hay mọi phiên TLS đều thực hiện đúng một chuỗi gọi method bên trong. Nhiều môi trường dùng KMS/HSM hoặc cấu hình JSSE mặc định thay vì các file trên đĩa.

**Câu hỏi phải đặt đúng:** *“Khóa riêng của **tôi** nằm ở đâu?”* khác với *“Tôi chấp nhận certificate **của ai**?”*; và cả hai khác với *“Tôi tìm thêm intermediate certificate/CRL **ở đâu** để đánh giá một chuỗi?”*

## 2. So sánh KeyStore, truststore và CertStore

| Tiêu chí | KeyStore (API / kho danh tính) | Truststore (vai trò của KeyStore) | CertStore (API Java) |
| --- | --- | --- | --- |
| Class | `java.security.KeyStore` | Vẫn thường là **`java.security.KeyStore`** | **`java.security.cert.CertStore`** |
| Mục đích chính | Quản lý khóa và chứng chỉ theo alias; với identity store là chứng chỉ + private key của ứng dụng | Xác định cert/trust anchor được cấu hình tin cậy khi kiểm tra đối tác | Cung cấp **certificates và CRLs ứng viên** cho tra cứu/PKIX |
| Dữ liệu | `PrivateKeyEntry`, `SecretKeyEntry`, `TrustedCertificateEntry` tùy type/provider | Chủ yếu `TrustedCertificateEntry` theo chính sách trust | `Certificate` và `CRL`, **không chứa private key** |
| Nhận diện item | Alias như `server`, `root-ca`, `jwt-signing` | Alias như `company-ca` | `CertSelector`, `CRLSelector` để lọc |
| Java gọi | `getInstance`, `load`, `getEntry`, `getKey`, `store` | `KeyStore.load` + `TrustManagerFactory.init(store)` hoặc PKIX trust anchors | `CertStore.getInstance("Collection", params)`, `getCertificates`, `getCRLs` |
| File định dạng | Thường PKCS#12 (`.p12`, `.pfx`), JKS; có backend không phải file | Có thể cũng dùng PKCS#12/JKS hoặc provider khác | Không phải một file-key-store tiêu chuẩn; có thể là Collection, LDAP hay nguồn khác |
| Trust decision? | **Không tự động**: phụ thuộc entry và API tiêu thụ | Định nghĩa/chứa **trust anchors** theo chính sách bên nhận | **Không**: tìm được certificate chưa có nghĩa nó đáng tin |
| Khi dùng TLS | `KeyManagerFactory` tạo `KeyManager` dùng private key + certificate chain | `TrustManagerFactory` tạo `TrustManager` kiểm tra peer | Có thể hỗ trợ PKIX tìm intermediate/CRL, **không thay thế TrustManager** |
| Ai cần truy cập? | Bên giữ khóa riêng/secret key; quyền rất chặt | Thành phần kiểm chứng bên đối tác; thay đổi anchor phải được kiểm soát | Thành phần PKI cần truy vấn certificate/CRL và có cơ chế kiểm tra tính xác thực |
| Lỗi tư duy hay gặp | “KeyStore chỉ là file chứa password” | “Truststore là một lớp Java hoặc thuật toán đặc biệt” | “Nhét cert vào CertStore là nó thành trusted CA” |

**Điểm quyết định:** *truststore không phải một API lưu trữ mới*. Nó dùng cùng cấu trúc `KeyStore` nhưng **được giao một nhiệm vụ bảo mật khác**. Một file PKCS#12 có thể chứa nhiều loại entry, song **không nên trộn quyền sở hữu private key và trust anchors tùy tiện**, vì việc gộp làm tăng phạm vi ảnh hưởng của sự cố và khó quản lý chính sách.

## 3. Kiến trúc KeyStore: engine, type, provider, alias và entry

`KeyStore` là một **engine class** của JCA: hành vi lưu trữ phụ thuộc **type** và **provider**. Class biểu diễn **kho logic**, không ràng buộc tất cả kho phải là file trên filesystem.

```text
KeyStore.getInstance("PKCS12")
          |
          v
 JCA tìm provider hỗ trợ PKCS12
          |
          v
  KeyStore instance (chưa load)
          |
      load(inputStream, password)  hoặc load(null, password) để tạo kho mới
          |
          v
      aliases -> Entries
          |
      getEntry / getKey / getCertificate / ...
          |
      store(outputStream, password)  (với backend hỗ trợ ghi stream)
```

### 3.1 Ba Entry quan trọng

JDK định nghĩa các loại entry chính:

| Entry | Có gì bên trong? | Ví dụ | API nhận diện |
| --- | --- | --- | --- |
| **`KeyStore.PrivateKeyEntry`** | Một `PrivateKey` và **certificate chain** tương ứng với public key của private key | Khóa TLS server, client mTLS, signing key có certificate | `entryInstanceOf(alias, KeyStore.PrivateKeyEntry.class)`, `isKeyEntry(alias)` |
| **`KeyStore.SecretKeyEntry`** | Một `SecretKey` đối xứng; không có X.509 certificate chain | AES key dùng mã hóa dữ liệu khi type/provider cho phép | `entryInstanceOf(alias, KeyStore.SecretKeyEntry.class)`, `isKeyEntry(alias)` |
| **`KeyStore.TrustedCertificateEntry`** | **Một certificate** được chủ kho cấu hình tin cậy | CA root hoặc peer cert được chính sách cho phép | `entryInstanceOf(alias, KeyStore.TrustedCertificateEntry.class)`, `isCertificateEntry(alias)` |

`KeyStore.Entry` là interface cha; ba lớp trên không phải cùng một định dạng bằng bytes. Provider/type có thể giới hạn loại entry được hỗ trợ hoặc cách bảo vệ chúng.

**Một số lời gọi dễ nhầm:**

- `store.containsAlias(alias)`: kiểm tra alias có tồn tại.
- `store.aliases()`: liệt kê tên alias (không được giả định thứ tự).
- `store.isKeyEntry(alias)`: đúng cho cả `PrivateKeyEntry` và `SecretKeyEntry` trong type/provider phù hợp.
- `store.isCertificateEntry(alias)`: đúng cho **certificate-only entry**, không phải lời khẳng định mọi alias có chứa certificate.
- `store.getKey(alias, password)`: trả key cho key entry; **certificate-only entry không trả private key**.
- `store.getCertificate(alias)`: có thể trả certificate của `TrustedCertificateEntry` hoặc certificate đầu tiên trong chain của `PrivateKeyEntry`. Vì vậy **`getCertificate(alias) != null` không có nghĩa alias là trusted certificate entry**.
- `store.getCertificateChain(alias)`: dùng cho private-key entry có chain; không mặc định có cho trusted-cert entry.
- `store.getEntry(alias, protection)`: trả kiểu `KeyStore.Entry`; dùng `instanceof`/ `entryInstanceOf` để kiểm tra loại và tránh cast sai.
- `store.setEntry`, `setKeyEntry`, `setCertificateEntry`, `deleteEntry`: thao tác quản trị, có ràng buộc provider/type và quyền thay đổi.

**Alias là định danh tra cứu**, không phải hostname hoặc identity được chứng nhận bởi PKI. Một alias tên `production-root` không làm certificate trở thành CA hợp lệ; chính sách trust phải kiểm tra nguồn certificate, key usage và mục đích sử dụng. **Phân biệt chữ hoa/chữ thường trong alias tùy implementation**; không chọn hai alias chỉ khác nhau về case.

### 3.2 Keystore password và key password

Một keystore file có thể cần **store password** khi `load`/`store` để bảo vệ tính toàn vẹn hoặc cơ chế lưu trữ; từng **key entry** có thể yêu cầu password để giải mã/truy cập. Mối quan hệ này **phụ thuộc type/provider**:

```text
PKCS12 file
  |
  +-- store password      (theo định dạng/provider)
  |
  +-- alias server
        +-- PrivateKeyEntry (key password/protection khi đọc khóa)
        +-- leaf certificate
        +-- certificate chain
```

Trong nhiều cấu hình PKCS#12 thực tế, store password và key password được sử dụng giống nhau để tương thích, nhưng không được coi đây là quy tắc áp dụng cho mọi provider. `KeyManagerFactory.init(identity, keyPassword)` nhận password dùng truy cập **key entries**, trong khi `KeyStore.load(stream, storePassword)` dành cho **load kho**.

Không dùng mật khẩu demo `changeit` trong production. Với triển khai thật, lấy credential từ secret manager/cơ chế triển khai được phê duyệt, phân quyền filesystem chặt chẽ, áp dụng rotation và tránh lưu password trên command line (có thể lộ qua process listing, shell history hay pipeline logs). Password bảo vệ PKCS#12 **không thay thế** quản lý khóa trong HSM/KMS khi cần key non-exportable.

### 3.3 File store và hardware/token store

- **PKCS#12:** định dạng mang tính tương tác tốt để chứa khóa và chứng chỉ, thông dụng ở JDK hiện đại; `KeyStore.getInstance("PKCS12")`. **Đây là default type từ JDK 9** trong triển khai JDK điển hình nhưng có thể bị đổi bởi security property `keystore.type`.
- **JKS:** định dạng Java legacy; vẫn gặp trong hệ thống cũ; không nên mặc định chọn chỉ vì thói quen nếu hệ thống mới có khả năng dùng PKCS#12.
- **JCEKS:** một keystore type lịch sử của provider Java cho một số secret/private key; không nhầm với `JKS` hay PKCS#12; đánh giá lại policy và migration.
- **PKCS#11:** API/provider có thể liên kết smart card/HSM, nơi key tồn tại dưới dạng **handle**. Không có nghĩa có file `.p12` và không nhất thiết cho phép `getEncoded()` private key. `load(null, ...)` có thể là phương thức phù hợp để kết nối token trong cấu hình provider, **không** phải “tạo file keystore mới”.
- **Windows-MY/macOS keystore provider** (tùy môi trường): tích hợp kho của hệ điều hành; không phải type được bảo đảm có trên mọi JDK/Linux container.

**Điều cần nhớ:** `KeyStore.getDefaultType()` trả type theo cấu hình runtime, **không bảo đảm luôn là `"PKCS12"`** trên mọi hệ thống. Trong ví dụ và các luồng import/export, ghi type tường minh để tránh bất ngờ do cấu hình thay đổi.

## 4. Identity keystore và truststore trong TLS/mTLS

Với **TLS server authentication**, server thường trình bày certificate chain để client kiểm tra. **Server identity keystore** giữ private key và certificate chain. **Client truststore** chứa trust anchors/certificates mà client chấp nhận theo chính sách.

```text
SERVER                                      CLIENT
+---------------------------+               +----------------------------+
| identity KeyStore         |               | truststore (KeyStore)      |
| alias "server"            |               | trusted CA/cert           |
| PrivateKeyEntry           |               | TrustedCertificateEntry   |
| private key + cert chain  |               +----------------------------+
+---------------------------+                         |
             |                                         v
       KeyManagerFactory                       TrustManagerFactory
             |                                         |
       Server KeyManager                        Client TrustManager
             |                                         |
             +----------- TLS handshake --------------+
              server gửi certificate chain, chứng minh nắm private key
                    client xác minh certificate/path/hostname/policy
```

Với **mTLS**, client **cũng có identity keystore** để trình bày private key + certificate chain của client, và server **cũng có truststore**/trust policy để kiểm tra certificate client. Cả hai đầu có thể có cả **KeyManager** và **TrustManager**, nhưng **vai trò không đổi**.

### 4.1 KeyManagerFactory và TrustManagerFactory

| API | Nguồn chính | Chức năng |
| --- | --- | --- |
| `KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm())` | `KeyStore` chứa private key và certificate chain; `init(identityStore, keyPassword)` | Cấp `KeyManager[]` để chọn danh tính/local credentials |
| `TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm())` | `KeyStore` chứa cert/trust anchors; `init(trustStore)` | Cấp `TrustManager[]` để đánh giá chứng chỉ bên đối tác |
| `SSLContext.getInstance("TLS")` và `init(keyManagers, trustManagers, random)` | Cả hai nhóm manager | Tạo cấu hình bảo mật cho TLS sockets/engines |

**Không đảo hai factory:** thêm private key vào nơi dùng `TrustManagerFactory` không có nghĩa private key sẽ được gửi cho peer. Tương tự, chỉ thêm CA certificate vào identity store không cung cấp private key cho server để hoàn tất authenticated TLS handshake.

Trong production, tránh tự viết `X509TrustManager` bỏ qua xác thực:

```java
// ANTI-PATTERN: chấp nhận mọi server certificate để "sửa SSLHandshakeException".
// Không sử dụng trong ứng dụng thật. Đây chỉ là đoạn nhận diện lỗi.
public void checkServerTrusted(
        java.security.cert.X509Certificate[] chain, String authType) {
    // Không kiểm tra gì cả => vô hiệu hóa xác thực peer.
}
```

Đoạn trên là **method minh họa, không phải một class đầy đủ**; mục đích là nhận diện hành vi nguy hiểm. Giải pháp đúng là phân tích certificate chain, trust anchors, hostname/SAN, thời hạn, EKU, policy, revocation phù hợp, chứ không phải vô hiệu hóa `TrustManager`.

### 4.2 Truststore không tự xác thực hostname

Một certificate chain có thể bắt nguồn từ CA được tin cậy nhưng certificate cuối cùng **không dành cho hostname** mà client đang truy cập. Việc kiểm tra **danh tính điểm cuối** (ví dụ `api.example.com` so với DNS Subject Alternative Name) là một yêu cầu **riêng** phải được thực thi bởi TLS client/giao thức phù hợp.

Đặc biệt, khi tự tạo `SSLSocket` hay `SSLEngine`, kiểm tra endpoint identification đã được bật theo contract API; đừng suy ra mọi low-level TLS socket tự bật hostname verification giống `HttpsURLConnection` hoặc các HTTP client cấp cao. **Trust anchor hợp lệ không đồng nghĩa chứng chỉ khớp hostname.**

### 4.3 Truststore có thể tin root CA hoặc leaf cert

Truststore thường chứa CA root/CA chuyên dụng làm **trust anchor**. Với kiểm thử hoặc một số thiết kế pinning, người ta có thể chấp thuận trực tiếp certificate của endpoint. Hai cách có hệ quả khác nhau:

- **Tin CA root:** CA có thể cấp nhiều certificate hợp lệ theo policy/constraints; cần đánh giá chain, tên máy, thời gian, EKU, usages, revocation nếu được cấu hình.
- **Tin trực tiếp leaf:** giới hạn danh tính theo certificate cụ thể, nhưng rotation/renewal sẽ phức tạp; cách diễn giải trust anchor phụ thuộc API/policy.
- **Tin intermediate CA:** cần suy nghĩ kỹ phạm vi ủy quyền và constraints; không thêm tùy tiện chỉ vì handshake đang lỗi.

**Không nhập một certificate không rõ nguồn rồi mặc nhiên tin nó.** `keytool -importcert` thiết lập một trust decision của người quản trị, không thể thay thế bước xác minh fingerprint/CA/nguồn certificate.

## 5. CertStore là gì, và vì sao nó không phải truststore?

`java.security.cert.CertStore` cung cấp một **repository để truy xuất certificates và Certificate Revocation Lists (CRLs)**. JCA dùng nó trong các công việc liên quan **certificate path**:

```text
Peer sends leaf certificate
          |
          v
CertPathBuilder cần tìm intermediate chứng chỉ còn thiếu
          |
          +------> CertStore (Collection/LDAP/nguồn hỗ trợ)
          |             | certificates & CRLs ứng viên
          |             v
          |       lọc bằng CertSelector/CRLSelector
          v
Construct candidate certification path
          |
          v
CertPathValidator + PKIXParameters
  - trusted anchors (từ truststore / TrustAnchor)
  - algorithm and certificate constraints
  - validity, policies, optional revocation sources
          |
          v
Accept/reject path theo chính sách
```

Một certificate nằm trong **CertStore** chỉ có nghĩa nó được **cung cấp để xem xét**, không phải nó là một trust anchor. Ngược lại, việc một certificate là **trust anchor** là quyết định thuộc **PKIX parameters / truststore / policy**. Hai tập dữ liệu này có thể chứa cùng một certificate nhưng **ý nghĩa được gán bởi API sử dụng** khác nhau.

| Loại | Kết quả API | Vai trò |
| --- | --- | --- |
| `CertStore.getCertificates(CertSelector)` | Danh sách certificate phù hợp tiêu chí | Ứng viên để xây dựng/kiểm tra chain |
| `CertStore.getCRLs(CRLSelector)` | Danh sách CRL phù hợp | Dữ liệu có thể dùng trong kiểm tra thu hồi |
| `PKIXParameters(trustStore)` | Các `TrustAnchor` từ `TrustedCertificateEntry` | Cơ sở tin cậy cho PKIX |
| `PKIXParameters.addCertStore(certStore)` | Thêm nguồn tìm certificate/CRL | **Không** thêm chứng chỉ trong CertStore thành trust anchors |
| `CertPathBuilder` | Xây đường dẫn ứng viên đến trust anchor | Không tự biết trust policy nếu không có parameters |
| `CertPathValidator` | Kiểm tra đường dẫn với trust anchors và policy | Không phải công cụ lưu private key |

### 5.1 Những loại CertStore

- **`"Collection"`**: dùng `CollectionCertStoreParameters` để cung cấp một collection chứa certificates và CRLs; loại tiêu chuẩn mà Java phải hỗ trợ. Hữu ích cho ví dụ chạy tại chỗ và khi ứng dụng có sẵn tập dữ liệu.
- **LDAP/nguồn ngoài**: có thể được hỗ trợ tùy provider; cho phép tìm certificates/CRLs trong directory hay repository. Không giả định mọi JVM có provider cho tất cả type.
- **Ứng dụng có thể kết hợp nhiều CertStore** trong `PKIXParameters` để cung cấp intermediate/CRL. Bên kiểm tra vẫn cần trust anchors và các chính sách xác minh.

`CertStore` là API **đọc/truy xuất**, không có một cặp `load(file,password)` / `store(file,password)` tương đương `KeyStore`; nó không quản lý private key. Nguồn dữ liệu bên dưới có thể thay đổi hoặc không đáng tin; **người xây/kiểm tra đường dẫn phải xác thực certificate chain và CRL** theo chính sách trước khi tin kết quả.

### 5.2 CRL, OCSP và certificate revocation

Một certificate có thể còn trong hạn nhưng đã bị thu hồi. **CRL** là danh sách certificate bị thu hồi do issuer ký; **OCSP** cung cấp một cơ chế khác để hỏi trạng thái. CertStore có thể **cung cấp CRL** cho quá trình PKIX nhưng không tự gọi mọi OCSP server hoặc tự bảo đảm việc xác minh thu hồi đã được bật.

Cần cấu hình/kiểm tra **PKIX revocation policy**, nguồn dữ liệu, thời hạn/cache, xử lý lỗi mạng và quy tắc fail-open/fail-closed theo yêu cầu. **Đừng nói “có CertStore là đã kiểm tra revocation”**. Với TLS, chính sách và hành vi mặc định có thể khác nhau theo provider/JDK/client; phải đo bằng môi trường thật.

## 6. Java 17+: tạo PKCS#12 KeyStore trong bộ nhớ và nạp lại

Chương trình sau chứng minh **`KeyStore` là API quản lý entry**, không nhất thiết phải bắt đầu từ một certificate hay file. Ta sinh **AES-256 SecretKey**, lưu thành `SecretKeyEntry` trong một PKCS#12 mới, serialize vào `ByteArrayOutputStream`, nạp lại và kiểm tra key có giống ban đầu không.

Lưu tệp **`KeyStoreBasicsDemo.java`**:

```java
import java.io.*;
import java.security.*;
import java.util.*;
import javax.crypto.*;

public final class KeyStoreBasicsDemo {
    public static void main(String[] args) throws Exception {
        // Mật khẩu cố định chỉ để minh họa, KHÔNG dùng trong production.
        char[] password = "demo-changeit".toCharArray();
        try {
            KeyStore store = KeyStore.getInstance("PKCS12");
            store.load(null, password); // Kho mới rỗng, file-backed type.

            KeyGenerator generator = KeyGenerator.getInstance("AES");
            generator.init(256);
            SecretKey original = generator.generateKey();

            store.setEntry(
                    "app-aes",
                    new KeyStore.SecretKeyEntry(original),
                    new KeyStore.PasswordProtection(password));

            ByteArrayOutputStream out = new ByteArrayOutputStream();
            store.store(out, password);
            byte[] p12 = out.toByteArray();

            KeyStore restored = KeyStore.getInstance("PKCS12");
            restored.load(new ByteArrayInputStream(p12), password);

            Key recovered = restored.getKey("app-aes", password);
            System.out.println("Entry count: " + restored.size());
            System.out.println("Secret key entry: "
                    + restored.entryInstanceOf(
                            "app-aes", KeyStore.SecretKeyEntry.class));
            System.out.println("Is key entry: "
                    + restored.isKeyEntry("app-aes"));
            System.out.println("Is trusted cert entry: "
                    + restored.isCertificateEntry("app-aes"));
            System.out.println("AES key same: "
                    + MessageDigest.isEqual(
                            original.getEncoded(), recovered.getEncoded()));
            System.out.println("Encoded PKCS12 nonempty: "
                    + (p12.length > 0));
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

Biên dịch và chạy với Java 17+ và provider hỗ trợ PKCS#12 SecretKeyEntry/AES:

```bash
javac -encoding UTF-8 KeyStoreBasicsDemo.java
java KeyStoreBasicsDemo
```

Stdout ổn định:

```text
Entry count: 1
Secret key entry: true
Is key entry: true
Is trusted cert entry: false
AES key same: true
Encoded PKCS12 nonempty: true
```

**Phân tích:**

1. `KeyStore.getInstance("PKCS12")` chọn **format/provider**, chưa load. `load(null, password)` tạo kho rỗng cho file-backed store trong demo; với PKCS#11/token không được tự suy ra ý nghĩa tương tự.
2. `SecretKeyEntry` chứa AES key. `setEntry` có `PasswordProtection`; điều đó khác `setCertificateEntry` chỉ thêm certificate.
3. `store(out,password)` serialize kho thành PKCS#12 bytes. `load(in,password)` phục hồi kho; `getKey` dùng password để truy cập key.
4. `isKeyEntry` là `true`; `isCertificateEntry` là `false`, vì AES secret key **không phải X.509 trusted certificate**.
5. `MessageDigest.isEqual` kiểm tra byte key khớp khi demo cho phép export. Với HSM/non-extractable key, `getEncoded()` có thể trả null và phải test bằng **operation được cấp phép**, không ép xuất key.

**Bảo mật:** `"demo-changeit"` là mật khẩu minh họa, không dùng cho kho khóa thật. Chương trình giữ password dưới dạng `char[]` và xóa buffer cuối chương trình, nhưng key bytes/PKCS#12 bytes vẫn có bản sao trong heap; `Arrays.fill` không bảo đảm xóa mọi bản sao trong JVM/provider. Trong production, tránh lưu raw key/PKCS#12 bytes trong log, response, repository hoặc artifact không được bảo vệ.

## 7. Thực hành đầy đủ: identity keystore, truststore và CertStore

Phần này tạo **hai file PKCS#12 khác nhau** bằng công cụ `keytool` đi kèm JDK, sau đó chạy Java code kiểm tra đúng vai trò của chúng:

- `demo-identity.p12`: chứa **private key** và self-signed certificate chain dưới alias `server`.
- `demo-trust.p12`: chứa **certificate-only** dưới alias `lab-server`.
- `demo-server.crt`: bản PEM certificate được export để **chuyển certificate**, **không chứa private key**.
- Trong Java, dùng certificate từ truststore tạo **`CertStore("Collection")`** — chỉ là **nguồn candidate cert**, không phải trust anchor mới.

### 7.1 Sinh dữ liệu test với keytool

Chạy tuần tự các lệnh dưới đây trong **một thư mục test riêng** trên JDK có `keytool`. Mỗi lệnh cố ý để trên một dòng nên dùng được trong shell phổ biến; lệnh không cần network và không yêu cầu chứng chỉ CA thật.

```bash
keytool -genkeypair -alias server -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 365 -dname "CN=localhost, OU=Training, O=Demo, C=VN" -ext "SAN=dns:localhost" -keystore demo-identity.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt

keytool -exportcert -alias server -rfc -keystore demo-identity.p12 -storetype PKCS12 -storepass changeit -file demo-server.crt

keytool -importcert -alias lab-server -file demo-server.crt -keystore demo-trust.p12 -storetype PKCS12 -storepass changeit -noprompt
```

**Các lệnh chỉ dùng trong lab**: password `changeit` nằm ngay trong command line và certificate là **self-signed**. Trong production, không chấp thuận certificate bằng `-noprompt` khi chưa xác minh nguồn/fingerprint và chính sách trust; dùng secret management và quá trình cấp/luân chuyển chứng chỉ được phê duyệt. Certificate test `localhost` **không chứng minh** một CA hoặc endpoint sản xuất có danh tính hợp lệ.

Có thể kiểm tra metadata tại chỗ:

```bash
keytool -list -keystore demo-identity.p12 -storetype PKCS12 -storepass changeit
keytool -list -keystore demo-trust.p12 -storetype PKCS12 -storepass changeit
```

Kết quả `keytool -list` có thể khác phiên bản JDK, locale và thời gian cấp certificate; vì vậy không lấy một stdout cứng để làm contract. Điều quan trọng là identity store có alias **PrivateKeyEntry**, còn truststore có alias **trustedCertEntry**.

### 7.2 Java 17+: kiểm tra ba kiểu kho và cấu hình TLS

Lưu đoạn sau thành **`KeyStoreTrustCertStoreDemo.java`** trong **cùng thư mục** có hai file `.p12` vừa tạo:

```java
import java.io.*;
import java.nio.file.*;
import java.security.*;
import java.security.cert.*;
import java.util.*;
import javax.net.ssl.*;

public final class KeyStoreTrustCertStoreDemo {
    private static KeyStore load(String file, char[] password)
            throws Exception {
        KeyStore ks = KeyStore.getInstance("PKCS12");
        try (InputStream in =
                Files.newInputStream(Path.of(file))) {
            ks.load(in, password);
        }
        return ks;
    }

    public static void main(String[] args) throws Exception {
        // Chỉ dành cho lab: password không được hardcode trong production.
        char[] pass = "changeit".toCharArray();
        try {
            KeyStore identity = load("demo-identity.p12", pass);
            KeyStore trust = load("demo-trust.p12", pass);

            System.out.println("Identity private-key entry: "
                    + identity.entryInstanceOf(
                            "server", KeyStore.PrivateKeyEntry.class));
            System.out.println("Identity certificate chain size: "
                    + identity.getCertificateChain("server").length);
            System.out.println("Truststore trusted certificate entry: "
                    + trust.isCertificateEntry("lab-server"));
            System.out.println("Truststore contains private key: "
                    + trust.isKeyEntry("lab-server"));

            X509Certificate certificate =
                    (X509Certificate)
                            trust.getCertificate("lab-server");
            CertStore candidates = CertStore.getInstance(
                    "Collection",
                    new CollectionCertStoreParameters(
                            List.of(certificate)));

            X509CertSelector selector = new X509CertSelector();
            selector.setSubject(
                    certificate.getSubjectX500Principal());
            System.out.println("CertStore matching candidates: "
                    + candidates.getCertificates(selector).size());

            PKIXParameters pkix = new PKIXParameters(trust);
            pkix.addCertStore(candidates);
            System.out.println("PKIX trust anchors: "
                    + pkix.getTrustAnchors().size());
            System.out.println("PKIX candidate stores: "
                    + pkix.getCertStores().size());

            KeyManagerFactory kmf =
                    KeyManagerFactory.getInstance(
                            KeyManagerFactory.getDefaultAlgorithm());
            kmf.init(identity, pass);

            TrustManagerFactory tmf =
                    TrustManagerFactory.getInstance(
                            TrustManagerFactory.getDefaultAlgorithm());
            tmf.init(trust);

            SSLContext ssl = SSLContext.getInstance("TLS");
            ssl.init(
                    kmf.getKeyManagers(),
                    tmf.getTrustManagers(),
                    null);
            System.out.println("TLS context initialized: "
                    + ssl.getProtocol().equals("TLS"));
        } finally {
            Arrays.fill(pass, '\0');
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 KeyStoreTrustCertStoreDemo.java
java KeyStoreTrustCertStoreDemo
```

Với các file test sinh đúng theo bước 7.1 trên provider JDK phổ biến, stdout:

```text
Identity private-key entry: true
Identity certificate chain size: 1
Truststore trusted certificate entry: true
Truststore contains private key: false
CertStore matching candidates: 1
PKIX trust anchors: 1
PKIX candidate stores: 1
TLS context initialized: true
```

**Giải thích tám kết quả:**

1. `identity` có `PrivateKeyEntry` bởi `keytool -genkeypair` tạo private key + self-signed certificate chain.
2. Certificate chain có **1** certificate trong lab vì certificate tự ký, chưa có CA trung gian; trong production, chain có thể dài hơn.
3. `trust` chứa `TrustedCertificateEntry` vì ta nhập riêng **public certificate**, không nhập private key.
4. `trust.isKeyEntry("lab-server")` là `false`: truststore không có private key của server, và **không cần** private key để kiểm tra certificate peer.
5. `CertStore("Collection")` trả **một certificate ứng viên** phù hợp `X509CertSelector`. Nó không đưa ra kết luận về trust/CA/hostname.
6. `new PKIXParameters(trust)` lấy **một trust anchor** từ trusted certificate entry trong truststore. **Đây mới là bước đưa certificate vào tập trust anchor**, hoàn toàn khác `CertStore.getCertificates`.
7. `pkix.addCertStore(candidates)` thêm một nguồn candidate certificate/CRL vào tham số kiểm tra đường dẫn, **không** tự động bổ sung trust anchor khác.
8. `SSLContext.init(keyManagers,trustManagers,null)` thiết lập một TLS context. Dòng `true` chỉ chứng minh **khởi tạo thành công**, **không thực hiện network handshake** và **không chứng minh** một endpoint thực tế sẽ qua được certificate path, hostname/SAN, EKU, revocation hoặc policy.

**Trust trong lab là quyết định có chủ ý:** ta đã nhập chính certificate tự ký vào truststore, rồi lấy nó làm anchor qua `PKIXParameters`. Một certificate self-signed do attacker tự phát hành **không được tin** chỉ vì tự ký hoặc có CN `localhost`; nó chỉ là trust anchor nếu administrator/client **cho phép** thông qua quy trình xác minh nguồn, pinning hoặc trust chính sách phù hợp.

### 7.3 Khi nào nên tách KeyStore identity và truststore?

Nên tách **vật lý hoặc tối thiểu tách quyền truy cập và cấu hình** khi có thể:

- Identity store chứa **private key** và certificate chain, nên chỉ các process/role cần dùng private key được đọc.
- Truststore chứa trust anchors/certificates, có thể được phân phối rộng hơn nhưng **quyền sửa** vẫn cực kỳ nhạy cảm: thêm CA không được phép có thể phá vỡ xác thực đối tác.
- Rotate certificate/private key không nhất thiết là rotate trust anchors; kế hoạch lifecycle và chủ sở hữu khác nhau.
- Tách các tập anchor cho **prod/staging/dev**, các tenant/partner khác nhau hoặc các trust domain khác nhau để giảm blast radius.
- Với mTLS, một app có thể cần **cả hai store**: một để trình bày danh tính của chính nó, một để xác minh client/server bên kia.

## 8. JSSE mặc định: cacerts, jssecacerts và các system properties

Trong nhiều runtime JDK, JSSE có thể tạo default `SSLContext`/`TrustManagerFactory` dựa trên cấu hình hệ thống. Đối với **SunJSSE reference implementation** (và cấu hình phù hợp), cần hiểu những tên thường gặp:

| Thuộc tính/file | Vai trò |
| --- | --- |
| `javax.net.ssl.keyStore` | Đường dẫn identity keystore cho default KeyManager theo cấu hình JSSE |
| `javax.net.ssl.keyStoreType` | Type của identity keystore (ví dụ `PKCS12`) |
| `javax.net.ssl.keyStorePassword` | Mật khẩu được default JSSE dùng theo contract |
| `javax.net.ssl.trustStore` | Đường dẫn truststore khi cấu hình tường minh |
| `javax.net.ssl.trustStoreType` | Type truststore |
| `javax.net.ssl.trustStorePassword` | Password dùng khi load/kiểm tra tính toàn vẹn store theo implementation |
| `java-home/lib/security/jssecacerts` | File truststore JSSE-specific được tìm trước `cacerts` trong logic default của SunJSSE khi không chỉ định `trustStore` |
| `java-home/lib/security/cacerts` | Tập root CA đi kèm JDK được tìm sau `jssecacerts` nếu có; nội dung có thể khác theo nhà phát hành/bản phân phối JDK |

**Không mặc định có “một truststore toàn cục áp dụng cho mọi library”.** HTTP client, framework, custom `SSLContext`, provider hoặc container có thể dùng trust source khác, ignore/override properties. Khi dùng `SSLContext.init` với `TrustManager[]` riêng, logic trust của context đó đi theo manager do ứng dụng truyền vào.

Trong SunJSSE, việc **cấu hình trustStore trỏ đến file không tồn tại** có thể dẫn đến truststore hiệu dụng **rỗng** thay vì âm thầm fallback sang `cacerts`; không sửa bằng cách tắt trust checks. Khi TLS fail, cần kiểm tra đúng path, type, password, runtime, trust anchors và certificate chain.

Một ví dụ **minh họa cấu hình** (mật khẩu phải lấy qua cơ chế secret management an toàn, không đặt hardcode như dưới đây):

```text
-Djavax.net.ssl.trustStore=/path/to/approved-trust.p12
-Djavax.net.ssl.trustStoreType=PKCS12

-Djavax.net.ssl.keyStore=/path/to/identity.p12
-Djavax.net.ssl.keyStoreType=PKCS12
```

Đây chỉ là danh sách **system properties** tùy ngữ cảnh khởi động, không phải các dòng lệnh tự chạy được. Cần password và key selection theo contract ứng dụng; đừng đưa password vào command-line production nếu có giải pháp secret injection tốt hơn.

### 8.1 Không sửa cacerts của cả JDK chỉ để chữa một ứng dụng

Thêm một CA vào `cacerts` có thể làm **nhiều ứng dụng** cùng tin nó, vượt khỏi phạm vi dịch vụ ban đầu. Một nâng cấp JDK/container image cũng có thể ghi đè thay đổi. Khi một hệ thống chỉ cần trust CA nội bộ của đối tác, thường nên cấu hình **truststore riêng cho app**, có versioning, owner, nguồn certificate kiểm chứng và kế hoạch rotation.

Không dùng các thủ thuật nguy hiểm như `trustAllCerts`, `HostnameVerifier` trả `true` vô điều kiện, tắt validation hoặc bỏ qua `SSLHandshakeException`.

## 9. Chuỗi chứng chỉ, trust anchor và certificate path

**Certificate chain** trong identity keystore và **trust anchors** của truststore là hai tập dữ liệu có quan hệ nhưng không giống nhau.

Một chain thường là:

```text
Leaf / end-entity certificate  (CN/SAN của dịch vụ)
        |
  issued by Intermediate CA
        |
  issued by Root CA
        |
Trusted anchor từ truststore / PKIX trust policy
```

- **PrivateKeyEntry** liên kết private key của leaf với certificate chain cần trình bày cho peer. Khi triển khai TLS, server thường gửi leaf và intermediate phù hợp; không nhất thiết gửi root CA.
- **Truststore** xác định nơi kết thúc chuỗi được chấp thuận, ví dụ root CA được operator tin.
- **CertStore** có thể chứa intermediate certificates và CRLs để builder/validator tìm thêm dữ liệu khi peer không cung cấp đủ chain. **CertStore không tự chọn root CA đáng tin**.
- **CertPathBuilder/Validator** dùng trusted anchors, các constraint, validity, chữ ký, policy và dữ liệu revocation theo cấu hình để quyết định có hợp lệ hay không.
- **Hostname/SAN verification** cho TLS vẫn phải đúng: một chain hợp lệ đến CA tin cậy chưa đủ nếu certificate dành cho tên host khác.
- Một certificate đã hết hạn, không hợp lệ theo EKU/key usage hoặc dùng thuật toán bị policy cấm không trở thành tốt chỉ vì có mặt trong một store.

### 9.1 PKIXParameters và TrustAnchor

`PKIXParameters(KeyStore)` đọc **trusted certificate entries** và chuyển thành trust anchors theo contract API. Nếu kho không có certificate nào thích hợp làm anchor, constructor có thể thất bại vì trust-anchor set rỗng. Điều này khác với `CertStore` chứa vô số certificate ứng viên nhưng không chỉ định được điểm bắt đầu tin cậy.

```java
// Đoạn minh họa trong phương thức đã có trustStore/candidates phù hợp.
// Không phải chương trình độc lập.
PKIXParameters parameters = new PKIXParameters(trustStore);
parameters.addCertStore(candidates);
Set<TrustAnchor> anchors = parameters.getTrustAnchors();
```

`parameters.getTrustAnchors()` và `parameters.getCertStores()` là **hai danh sách khác nhau**; thêm một `CertStore` không làm số anchors tăng.

Nếu xây certificate path phức tạp, `PKIXBuilderParameters` có mục tiêu certificate selector và trust anchors, còn `CertPathBuilder` sử dụng parameters để tìm path; `CertPathValidator` dùng path đã có để đánh giá. Không coi `PKIXParameters` khởi tạo thành công là certificate path đã được xác minh — bước xác minh thực sự phải chạy.

## 10. Chọn công cụ đúng theo tình huống

| Tình huống | Nên dùng | Không nên nhầm với |
| --- | --- | --- |
| Web server cần giữ private key để trình bày TLS certificate | Identity `KeyStore` + `KeyManagerFactory` hoặc key handle của HSM | Chỉ import public certificate vào truststore |
| Client REST cần tin CA nội bộ phục vụ `api.company` | Truststore riêng + `TrustManagerFactory` + endpoint/hostname verification | Sửa `cacerts` toàn JDK hoặc bỏ hostname check |
| mTLS: client cũng cần certificate riêng | **Client identity KeyStore** và **server truststore**; server cũng có identity và trust | Nghĩ chỉ server mới cần keystore |
| PKIX thiếu intermediate certificate khi build chain | `CertStore`/AIA/nguồn tra cứu phù hợp theo policy | Thêm intermediate thành root trust anchor tùy tiện |
| PKIX kiểm tra thu hồi | CRL/OCSP, revocation policy, optional `CertStore` chứa CRLs | Tin rằng `CertStore` tự kiểm tra thu hồi |
| Lưu AES secret key cho dữ liệu cục bộ | `KeyStore.SecretKeyEntry` nếu type/provider hỗ trợ, hoặc KMS/HSM | `TrustedCertificateEntry` |
| Xác minh chữ ký số từ certificate đối tác | Public key/cert chain + trust policy/Pkix validation khi cần | Chỉ lấy public key từ certificate không rõ nguồn rồi kết luận trusted |
| Luân chuyển private key server | Rotate identity keypair/certificate và cập nhật deployment | Tự động thay toàn bộ trusted CA của client |
| Xóa một CA không còn tin | Quản trị **trust anchors** trong truststore/policy | Xóa certificate ứng viên khỏi CertStore rồi nghĩ CA đã bị loại khỏi trust anchors |

**Mô hình tối thiểu:** private key của **bên mình** → identity keystore. Certificate của **bên được phép tin** → truststore. Certificate/CRL **chỉ để tra cứu** → CertStore. Kết quả có chấp thuận kết nối hay không còn phụ thuộc **trust manager/PKIX/endpoint policy**, không phụ thuộc một file có tên `truststore.p12` hay `certs.p12`.

## 11. Các lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `java.io.IOException` khi `KeyStore.load` | Path không tồn tại, bytes hỏng, password/type/provider không phù hợp | Kiểm tra file, type, quyền đọc, nguồn file, password; giữ cause trong log an toàn |
| `UnrecoverableKeyException` | Không thể khôi phục key entry bằng password/protection đang dùng | Phân biệt **key password** với store password; kiểm tra alias/provider |
| `KeyStoreException` | Store chưa load, alias/entry/type không hợp lệ hoặc thao tác không hỗ trợ | Gọi load trước, kiểm tra `entryInstanceOf`, provider capability |
| `NoSuchAlgorithmException` | Provider không hỗ trợ thuật toán integrity/keystore/key protection được yêu cầu | Kiểm tra JDK/provider/security policies |
| `CertificateException` | Lỗi parse/kiểm tra certificate khi load | Kiểm tra format, certificate chain và provider |
| `NoSuchProviderException` | Chỉ định provider không tồn tại qua overload/provider name | Kiểm tra registration và runtime |
| `SSLHandshakeException: PKIX path building failed` | Không có path hợp lệ tới anchor, thiếu intermediate, CA chưa trusted, constraint khác | Kiểm tra **đúng truststore hiệu dụng**, chain, issuer, ngày, usages, policy; không trust-all |
| TLS báo hostname mismatch | Certificate có chain tin cậy nhưng SAN không khớp endpoint | Kiểm tra tên host, SAN và endpoint identification |
| Server `no suitable certificate` hoặc handshake không tìm thấy key | Identity keystore thiếu PrivateKeyEntry/chain, alias sai, algorithm không phù hợp, key password không đúng | Kiểm tra identity store, `KeyManagerFactory`, certificate/key usage |
| `CertStoreException` | Truy vấn CertStore/LDAP/backend thất bại | Kiểm tra selector, kết nối, cache, quyền và xử lý timeout |
| `InvalidAlgorithmParameterException` khi tạo PKIX params | Không có trust anchors hợp lệ hoặc tham số PKIX sai | Đọc trusted entries, set TrustAnchor; không chuyển mọi candidate thành trusted |
| Private key `getEncoded() == null` | Key non-extractable hoặc provider không hỗ trợ export | Dùng operation của HSM/KMS, không bypass boundary an toàn |

Có thể dùng **debug flags của JDK** khi điều tra trong môi trường kiểm soát, ví dụ `-Djavax.net.debug=ssl,handshake` hoặc `-Djava.security.debug=certpath`. Log TLS/certpath có thể rất lớn và có thông tin cấu hình nhạy cảm; không bật vô thời hạn trong production, không paste nguyên log chứa secret nội bộ lên nơi công khai.

**Đọc đúng lỗi:** “`PKIX path building failed`” không nhất thiết là “thiếu private key”. Nếu client không tìm được CA của server, đó thường là luồng **truststore/trust manager**; nếu server không chọn được certificate của chính mình, đó thường là luồng **identity keystore/key manager**.

## 12. Sai lầm thiết kế cần tránh

1. **“Truststore là class `TrustStore`.”** Không: với Java/JSSE thường là một `KeyStore` được dùng cho chức năng trust.
2. **“Có certificate trong một file keystore nghĩa là đã trusted.”** Không: `PrivateKeyEntry` cũng có chain, nhưng `isCertificateEntry(alias)` không đúng cho key entry; trust decision phụ thuộc vai trò và policy.
3. **“CertStore chứa CA thì tự thành trust anchor.”** Không: CertStore chứa **candidate certificates/CRLs**; trust anchor được cấu hình riêng.
4. **“Khi SSLHandshakeException, thêm mọi certificate tải về vào cacerts.”** Rất nguy hiểm: chấp thuận nguồn không xác thực và làm tăng phạm vi tin cậy.
5. **“KeyStore luôn là một file `.jks`.”** Không: `PKCS12`, JKS, PKCS#11, OS-specific providers và backend hardware đều có thể xuất hiện.
6. **“Đổi alias từ `server` thành `trusted-ca` sẽ biến cert thành root CA.”** Không: alias chỉ là nhãn; ý nghĩa từ loại entry và trust policy.
7. **“CertStore kiểm tra certificate revocation tự động.”** Không: cần PKIX revocation configuration/OCSP/CRL handling đúng.
8. **“Đã tin CA thì không cần kiểm tra hostname.”** Sai: endpoint identity và chain trust là hai kiểm tra liên quan nhưng độc lập.
9. **“Password PKCS#12 là bí mật duy nhất cần quản lý.”** Sai: private key, quyền filesystem, backup, deployment, KMS/HSM, rotation và integrity đều cần bảo vệ.
10. **“Chỉ cần gọi `SSLContext.init` thành công thì TLS đã bảo mật.”** Sai: context initialized ≠ handshake/trust/hostname validation verified.
11. **“Trong mTLS, client không cần private key.”** Sai: khi server yêu cầu client certificate authentication, client cần identity credential riêng.
12. **“Có thể xuất mọi private key khỏi HSM qua `getEncoded()`.”** Không: non-exportability là tính năng bảo mật và phải được tôn trọng.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Một API server có `server.p12` chứa private key và leaf+intermediate chain, còn client có `ca-trust.p12` chứa root CA. Bên nào là identity keystore, bên nào là truststore?  
**Trả lời:** `server.p12` là **identity keystore** của server; `ca-trust.p12` là **truststore** của client. Cả hai đều có thể được đọc bằng class `KeyStore`.

**Câu 2.** Vì sao `identity.getCertificate("server") != null` không có nghĩa `server` là trusted certificate entry?  
**Trả lời:** PrivateKeyEntry cũng chứa certificate chain và `getCertificate` có thể trả leaf certificate của nó. Kiểm tra bằng `isCertificateEntry` hoặc `entryInstanceOf(TrustedCertificateEntry.class)`.

**Câu 3.** Có 100 intermediate certificates trong CertStore; có nghĩa JVM tin 100 CA đó không?  
**Trả lời:** **Không.** Chúng là ứng viên để build/validate path. Điểm tin cậy phải nằm trong **TrustAnchor/truststore/PKIX policy** được xác thực.

**Câu 4.** Nếu mTLS client cần trình bày certificate, nó chỉ cần truststore không?  
**Trả lời:** Không. Nó cần **identity credential** chứa private key + chain và key manager; còn truststore giúp nó xác minh certificate server.

**Câu 5.** `KeyStore.getInstance("PKCS12")` đã tự đọc `identity.p12` trên đĩa chưa?  
**Trả lời:** Chưa. Thông thường phải `load(inputStream,password)`; một số overload mới hỗ trợ chọn file/probe type và load ngay, nhưng `getInstance(String type)` chỉ lấy instance chưa load.

**Câu 6.** Nhập một self-signed certificate vào truststore thử nghiệm có an toàn để xác thực mọi server production không?  
**Trả lời:** Không. Đó là một quyết định tin cậy cần nguồn, fingerprint và phạm vi xác nhận; certificate demo không đại diện CA thật và không có quy trình cấp phát/thu hồi production.

**Câu 7.** Muốn tìm CRL để phục vụ PKIX revocation, dùng class nào?  
**Trả lời:** `CertStore` có thể cung cấp CRLs qua `getCRLs`, nhưng vẫn cần cấu hình PKIX revocation checker/policy và xác minh CRL đúng nguồn.

**Câu 8.** Thay đổi `javax.net.ssl.trustStore` có ảnh hưởng mọi `SSLContext` trong app không?  
**Trả lời:** Không nhất thiết. Framework hoặc context được cấu hình với trust managers riêng có thể không dùng default system properties.

**Câu 9.** Nếu một certificate đã qua chain validation nhưng SAN không khớp URL, kết nối HTTPS có nên được chấp nhận?  
**Trả lời:** **Không.** HTTPS cần kiểm tra danh tính host/endpoint phù hợp với certificate; không bỏ qua hostname verification.

**Câu 10.** Nếu private key trong HSM không xuất được, phải lưu vào PKCS#12 trước khi dùng với TLS?  
**Trả lời:** Không. Dùng KeyStore/provider/key-manager tích hợp HSM theo khả năng được cấp phép; không cố export private key.

## 14. Checklist vận hành

**Quản trị identity keys:**

- Đặt private key ở đúng boundary (keystore có kiểm soát, KMS/HSM khi phù hợp).
- Xác định alias, key type, certificate chain đầy đủ, key usage, EKU, SAN và ngày hết hạn.
- Bảo vệ key access password/role/permissions; có quy trình renew, key rotation, backup/restore và thu hồi.
- Chỉ load private key ở những process thực sự cần; không log/export/commit material.

**Quản trị trust anchors:**

- Chỉ nhập CA/peer certificate khi đã xác thực nguồn và mục đích tin cậy.
- Tách trust domain theo app/tenant/environment; tránh sửa `cacerts` toàn JVM không kiểm soát.
- Theo dõi expiry, root/intermediate rotation, algorithm deprecation, revocation policy.
- Bật endpoint identification/hostname validation cho TLS client đúng API.
- Không tắt trust checks để “giải quyết nhanh” lỗi PKIX.

**Quản trị CertStore và certificate path:**

- Phân biệt **nguồn ứng viên** với **trust anchors**.
- Giới hạn nguồn tra cứu, timeout, cache, kích thước dữ liệu, xử lý backend lỗi.
- Cấu hình đúng certpath builder/validator, EKU/policy, revocation check và trust anchor.
- Test tình huống missing intermediate, wrong CA, expired, hostname mismatch, revoked và untrusted cert.

**Triển khai Java:**

- Ghi rõ `PKCS12` hay type phù hợp thay vì phụ thuộc default không cần thiết.
- Dùng `KeyManagerFactory` với identity keystore, `TrustManagerFactory` với truststore, `CertStore` khi cần nguồn certificate/CRL ứng viên.
- Kiểm thử bằng đúng JDK/provider/container image và hệ thống TLS client/server thực.
- Kết quả `SSLContext.init` thành công chưa phải là test handshake/hostname/trust decision.

## Tài liệu chính thức

- [Java SE 21 — `KeyStore`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html): các loại Entry, alias, load/store, provider, các phương thức quản lý khóa/chứng chỉ.
- [Java SE 21 — `CertStore`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertStore.html): nguồn certificate/CRL để tra cứu, phân biệt với KeyStore.
- [Java SE 21 — `PKIXParameters`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXParameters.html): trust anchors từ KeyStore và các CertStore ứng viên.
- [Java SE 21 — `TrustAnchor`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/TrustAnchor.html): điểm tin cậy trong PKIX.
- [Java SE 21 — `KeyManagerFactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html) và [`TrustManagerFactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): identity và trust managers của TLS.
- [Java SE 21 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): SSLContext, key/truststore defaults, cacerts/jssecacerts, cấu hình và mô hình TLS.
- [Java SE 21 — Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/21/security/java-pki-programmers-guide.html): xây/kiểm tra certification path, CertStore, CRL/revocation.
- [Java `keytool` documentation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html): tạo identity keypair, export/import certificate, quản trị PKCS#12/JKS.

**Kết luận:** `KeyStore` là **API/kho quản lý khóa và chứng chỉ**; *identity keystore* dùng private key + certificate chain **của chính ứng dụng**; *truststore* cũng thường là `KeyStore` nhưng đại diện **các điểm tin cậy để kiểm tra đối tác**; `CertStore` lại là **nguồn tra cứu certificates/CRLs ứng viên**, không tự định nghĩa trust. Phân biệt đúng ba vai trò giúp thiết kế TLS, PKIX, mTLS và quản lý khóa an toàn, dễ kiểm thử và dễ vận hành.