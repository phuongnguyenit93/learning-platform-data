# Vai trò của tập chứng thư gốc trong bản phân phối OpenJDK

*Chủ đề Java 10 — Chứng thư gốc. Bài học giải thích **JEP 319 (Root Certificates)**, vì sao một bản phân phối OpenJDK cần một tập chứng thư gốc đáng tin cậy, cách JSSE/PKIX sử dụng trust anchor khi xác thực TLS, sự khác biệt giữa `cacerts` và truststore riêng, cùng quy trình kiểm tra/cập nhật an toàn trên Java 17+ và JDK hiện đại. Chỉ sử dụng các cơ chế hiện còn áp dụng; các ví dụ có thể chạy bằng JDK 17 trở lên.*

## 1. Trọng tâm: chứng thư gốc là điểm khởi đầu của sự tin cậy

Khi ứng dụng Java gọi một API HTTPS, bên nhận không thể quyết định “server thật” chỉ vì phía đối diện gửi một certificate có tên miền đúng. Một kẻ tấn công cũng có thể tạo certificate tự ký và ghi tên miền bất kỳ.

Để xác thực danh tính qua X.509/TLS, client cần một số **trust anchors** đã được chọn bằng chính sách tin cậy. Trong mô hình Web PKI, trust anchor thường là **chứng thư của một Root Certification Authority (Root CA)**. Tập chứng thư gốc trong bản phân phối JDK là một nguồn tin cậy mặc định được Java sử dụng qua các thành phần bảo mật như JSSE.

Chuỗi chứng thư thường có dạng:

~~~text
Truststore mà client tin cậy
  └─ Root CA (trust anchor, đã được lựa chọn từ trước)
       └─ Intermediate CA (chứng thư CA trung gian)
            └─ TLS server certificate (chứng thư đầu cuối)
                 └─ Service HTTPS: api.example.test
~~~

Khi kết nối, client cần xây dựng/kiểm tra một đường dẫn hợp lệ từ chứng thư server đến một trust anchor đáng tin, kiểm tra những ràng buộc chứng thư và **xác minh hostname** của server theo ngữ cảnh HTTPS. Một số kiểm tra bổ sung (ví dụ revocation) phụ thuộc security provider và cấu hình.

**Mấu chốt:** `cacerts` giúp trả lời “những CA nào được JDK mặc định tin cậy?”, không phải “mọi server do các CA này cấp certificate đều chắc chắn được kết nối thành công”.

## 2. JEP 319 đã thay đổi điều gì ở Java 10?

**JEP 319 — Root Certificates**, được triển khai trong **JDK 10**, đưa một tập root CA certificates có quyền phân phối phù hợp vào mã nguồn OpenJDK.

### 2.1. Trước JEP 319: bản build nguồn OpenJDK không nhất thiết có root CA sẵn

Trong lịch sử, nguồn OpenJDK có `cacerts` trống hoặc thiếu tập public roots tương đương với một số binary JDK do nhà phân phối đóng gói. Người tự build OpenJDK phải đưa chứng thư gốc vào bằng bước bổ sung, nếu không những HTTPS connections thông thường có thể không xây dựng được chuỗi tin cậy mặc định.

Hệ quả thực tế trước khi cải thiện:

- OpenJDK build có thể không có trust anchors cho các public HTTPS CA phổ biến.
- JSSE client đến nhiều website/public API bị lỗi `PKIX path building failed`.
- Nhà đóng gói/hệ điều hành phải bổ sung CA store hoặc tích hợp với kho chứng thư riêng.
- Cùng mã ứng dụng nhưng đổi JDK distribution lại có kết quả TLS khác nhau.

### 2.2. Mục tiêu JEP 319

JEP 319 mở nguồn các Root CA certificates trong chương trình Java SE Root CA liên quan, để:

1. Tạo một tập trust anchors mặc định hữu dụng cho **OpenJDK builds**.
2. Giảm chênh lệch trải nghiệm TLS giữa OpenJDK và Oracle JDK.
3. Giúp người dùng có khả năng kết nối HTTPS/TLS theo mặc định mà không phải tự đi tìm từng public CA.
4. Đưa tập certificates vào quy trình xây dựng và bảo trì JDK một cách minh bạch.

JEP 319 là một cải tiến **phân phối/tài nguyên tin cậy của JDK**, không phải một phiên bản TLS mới, không tự thêm API `RootCertificateManager` trong Java SE và không đồng nghĩa mọi OpenJDK distribution đều đóng gói chính xác cùng các roots.

### 2.3. Những gì vẫn đúng ở JDK hiện nay

Trên JDK 17/21/25 và các bản dựng OpenJDK hiện đại, thường có một tập root CA được đóng gói dưới `java.home/lib/security/cacerts` hoặc một cơ chế phân phối tương đương. Nhưng **danh sách cụ thể thay đổi theo thời gian, nhà phân phối, hệ điều hành và chính sách bảo mật**.

**Không** hardcode “OpenJDK có đúng N chứng thư gốc” hoặc “mọi JDK dùng cùng một `cacerts`”. Cách đúng là **kiểm tra bản JDK trong deployment thực tế**, cập nhật JDK theo lịch bảo mật và quản lý riêng CA nội bộ khi có.

## 3. Trust anchor, root certificate và certificate chain khác nhau thế nào?

| Khái niệm | Vai trò | Có trong truststore mặc định? |
| --- | --- | --- |
| **Root CA** | CA cấp cao, thường self-signed, có public key được chọn làm trust anchor | Có thể có nếu nằm trong root program của JDK/distribution |
| **Trust anchor** | Điểm tin cậy đã thiết lập cho việc xác nhận đường dẫn PKIX | Thường biểu diễn bởi trusted CA certificate; không bắt buộc mọi trust anchor là một self-signed root |
| **Intermediate CA** | CA trung gian ký certificate bên dưới, được root hoặc CA khác cấp | Thường do server cung cấp trong chain, có thể tải/tìm theo cấu hình |
| **Leaf/end-entity certificate** | Certificate nhận diện server/client cụ thể | Thường do peer gửi qua TLS handshake |
| **Private key** | Bí mật dùng để chứng minh sở hữu public key | **Không** nằm trong tập CA root công khai mặc định |
| **Truststore** | Kho các certificates/anchors đã tin cậy | `cacerts` hoặc file do ứng dụng chỉ định |
| **Keystore chứa private key** | Kho identity keys/certificate chain của server hoặc client mTLS | Tách khỏi nhu cầu tin cậy public roots |

Một self-signed certificate **không tự được tin cậy** chỉ vì nó tự ký hợp lệ. Nó chỉ được tin khi bạn có lý do ngoài đường truyền để chấp nhận public key/fingerprint/chính sách của CA ấy.

### 3.1. Vì sao root thường không nằm trong certificate chain server gửi?

Trong nhiều triển khai TLS, server gửi leaf và các intermediate cần thiết, còn root là điểm tin cậy có sẵn ở client. Việc server gửi kèm root không làm client tự động tin root; client phải có một trust anchor đáng tin từ nguồn độc lập.

Điều này tránh nhầm lẫn khi dùng công cụ hiển thị chuỗi certificate: nhìn thấy `Root CA` trong chuỗi do server gửi **không có nghĩa** root đã có trong truststore của Java.

### 3.2. Không phải certificate nào có trong một keystore đều là CA root

`KeyStore` là một API chứa nhiều loại entry, chẳng hạn `TrustedCertificateEntry` và `PrivateKeyEntry`. Một tệp do ứng dụng tự tạo có thể chứa chứng thư leaf, trung gian hoặc CA, thậm chí có private keys nếu dùng sai mục đích.

`cacerts` trong JDK được thiết kế như tập **CA trusted certificates**, nhưng khi tự quản lý truststore cần kiểm tra entry type, subject, issuer, Basic Constraints, Key Usage, fingerprint và chính sách tin cậy. Đừng xem “file có đuôi `.p12`” như bằng chứng nó chỉ có CA công khai.

## 4. Khi ứng dụng HTTPS dùng default truststore thì diễn ra điều gì?

Trong SunJSSE/HotSpot, Java HTTPS client thông thường dựa vào `SSLContext`, `TrustManagerFactory` và `X509TrustManager`.

Một luồng khái quát:

~~~text
Ứng dụng gửi HTTPS request
      │
      ▼
TLS handshake nhận leaf + intermediates từ server
      │
      ▼
JSSE TrustManager / PKIX CertPath validation
      │
      ├─ Xây đường dẫn tới trust anchor hợp lệ
      ├─ Kiểm chữ ký, hiệu lực thời gian, CA/key usage, constraints
      ├─ Kiểm thuật toán/chính sách mà JDK cho phép
      └─ Thực hiện các bước revocation theo cấu hình áp dụng
      │
      ▼
Hostname verification cho HTTPS endpoint
      │
      ├─ Đúng policy + chain hợp lệ → kết nối được
      └─ Không đạt → TLS/HTTPS validation thất bại
~~~

Từng thành phần bảo mật thực hiện kiểm tra theo hợp đồng provider và giao thức. **Trust anchor có sẵn là điều kiện cần của một đường PKIX thường gặp, không phải điều kiện đủ của một HTTPS connection an toàn.**

### 4.1. Root CA xác nhận “ai được ký”, không quyết định mọi thuộc tính server

Nếu root đã được tin, client vẫn cần kiểm tra:

- Chain có nối từ leaf qua các intermediate đến anchor không?
- Các chữ ký/thuật toán được JDK cho phép không?
- Certificate đã hết hạn, chưa có hiệu lực hoặc sai mục đích sử dụng không?
- `BasicConstraints` và `KeyUsage` của intermediate CA có hợp lệ không?
- Tên miền trong `subjectAltName` (SAN) có khớp server cần truy cập không?
- Có name constraints/algorithm constraints/distrust policy khác không?
- Nếu chính sách yêu cầu revocation, cơ chế kiểm tra có được bật và hoạt động không?

**Không** tắt hostname verification để “sửa lỗi chứng thư gốc”. Làm vậy có thể khiến client nhận một server không đúng danh tính, dù chain được ký bởi CA hợp lệ.

### 4.2. `PKIX path building failed` không luôn nghĩa root đã mất

Một số nguyên nhân thường gặp:

- Root CA chưa được tin cậy trong truststore mà **process thật** đang dùng.
- Server quên gửi intermediate certificate cần thiết.
- Truststore riêng đã **thay thế** danh sách roots mặc định.
- Certificate/chain hết hạn hoặc vi phạm policy/algorithm constraints.
- TLS interception/proxy thay certificate bằng CA nội bộ chưa được tin.
- Một container/JDK khác với máy local có root list khác.
- Path truststore sai; SunJSSE có thể khởi tạo truststore trống nếu file chỉ định không tồn tại.

Đừng thấy từ “PKIX” rồi lập tức import leaf certificate của server bất kỳ vào `cacerts`.

## 5. `cacerts` của JDK nằm ở đâu?

Trên các bản JDK hiện đại, tài liệu `keytool` mô tả:

~~~text
Linux/macOS:
  $JAVA_HOME/lib/security/cacerts

Windows:
  %JAVA_HOME%\lib\security\cacerts
~~~

Trong Java:

~~~java
String home = System.getProperty("java.home");
java.nio.file.Path cacerts =
        java.nio.file.Path.of(home, "lib", "security", "cacerts");
~~~

Đây là **đoạn code bên trong một method**, không phải chương trình độc lập.

**Phân biệt các đường dẫn:**

- `JAVA_HOME` trong shell có thể trỏ một JDK.
- `java.home` trong process chỉ runtime **đang chạy thực tế**.
- `keytool` tìm được qua `PATH` có thể thuộc JDK khác.
- Docker container thường có filesystem/JDK khác host.
- Distribution Linux có thể cung cấp file/symlink được đồng bộ từ OS CA bundle.

Vì vậy, hãy kiểm tra đúng **binary và runtime image** đang chạy ứng dụng; không suy từ cửa sổ terminal trên máy developer.

### 5.1. Kiểm tra không sửa nội dung

~~~bash
java -version
keytool -list -cacerts
~~~

Lệnh `keytool -list -cacerts` đọc danh sách trusted certificates theo JDK cung cấp `keytool`. Nó có thể yêu cầu mật khẩu integrity; nếu bỏ qua mật khẩu lúc chỉ xem, tool có thể hiển thị cảnh báo rằng integrity chưa được xác minh.

Nếu quản trị viên đã cung cấp password qua biến môi trường bảo mật:

~~~bash
keytool -list -cacerts -storepass:env CACERTS_PASS
~~~

Tùy chọn `:env` được `keytool` hiện hành hỗ trợ, giúp tránh ghi password trực tiếp vào process command line.

**Không** xem password mặc định được tài liệu nhắc tới (`changeit`) là một bí mật quản trị tuyệt đối hoặc chứng cứ JDK còn nguyên. Nó là password ban đầu phổ biến của `cacerts`; admin có thể đổi. File root CA chứa **public certificates**, còn password chủ yếu phục vụ kiểm tra integrity của keystore, không bảo vệ private root CA keys vì các keys ấy không được phân phối.

### 5.2. Xem fingerprint một CA cụ thể

~~~bash
keytool -list -v -cacerts -alias some-ca-alias
~~~

`some-ca-alias` là tên alias **phải thay bằng alias có thật** từ `keytool -list -cacerts`. Xem `SHA-256 fingerprint`, subject/issuer, thời hạn và extension. Fingerprint phải được đối chiếu với **nguồn tin cậy độc lập** khi ra quyết định thêm trust anchor mới.

### 5.3. Đừng hardcode format `cacerts`

File `cacerts` có thể được nhà phân phối tạo ở định dạng khác, ví dụ JKS hoặc PKCS12 theo cấu hình của bản dựng. `KeyStore.getDefaultType()` của JDK mới thường là `pkcs12`, nhưng **không suy ra mọi `cacerts` có định dạng PKCS12**.

`keytool -cacerts` tự dùng store mà JDK nhận diện. Khi tự tạo truststore mới, có thể chọn định dạng tường minh, ví dụ `-storetype PKCS12`, rồi khai báo chính xác trong cấu hình.

## 6. JSSE chọn truststore mặc định theo thứ tự nào?

Theo **JSSE Reference Guide JDK 25**, đối với SunJSSE khi tạo default TrustManager và không truyền `KeyStore` riêng, thứ tự tìm trust material là:

1. Nếu có `javax.net.ssl.trustStore`, thử dùng **file/path được chỉ định**.
2. Nếu không có property trên, tìm `java.home/lib/security/jssecacerts`.
3. Nếu không có `jssecacerts`, tìm `java.home/lib/security/cacerts`.
4. Nếu không tìm được, default trust material có thể là **một kho trống**, tùy provider/context.

~~~text
javax.net.ssl.trustStore được khai báo?
  ├─ Có → sử dụng nguồn được chỉ định (nếu file sai: có thể truststore trống)
  └─ Không
       ├─ java.home/lib/security/jssecacerts tồn tại? → dùng file đó
       ├─ java.home/lib/security/cacerts tồn tại?    → dùng file đó
       └─ Không có nguồn?                           → truststore trống
~~~

Đây là hành vi của **SunJSSE reference implementation**. Một custom security provider/framework/OS integration có thể áp dụng cơ chế khác; đừng biến thứ tự trên thành tuyên bố cho mọi TLS library hoặc mọi JVM không phải HotSpot.

### 6.1. Tại sao `jssecacerts` được ưu tiên?

`jssecacerts` cho phép cấu hình tập trust anchors **riêng cho JSSE/TLS** mà không phải sửa `cacerts` (nơi cũng có thể được dùng bởi các thành phần an ninh khác). Khi file này tồn tại, nó được xem trước `cacerts`.

Điều đó có thể gây bất ngờ: thêm một `jssecacerts` chỉ có một CA nội bộ, rồi ứng dụng không còn tin một số public HTTPS sites như trước. Nguyên nhân là **thay thế danh sách tin cậy**, không phải “TLS đang ngẫu nhiên chập chờn”.

### 6.2. Truststore riêng không tự động cộng gộp với `cacerts`

Khi chạy:

~~~bash
java -Djavax.net.ssl.trustStore=/opt/app/trust.p12 \
     -Djavax.net.ssl.trustStoreType=PKCS12 \
     -jar app.jar
~~~

SunJSSE sẽ chọn truststore được chỉ định cho default trust manager theo chính sách cấu hình tương ứng. **Không** mặc định gộp cả public roots từ `cacerts`.

Nếu ứng dụng vừa cần public CA roots vừa cần một internal CA, có các lựa chọn có kiểm soát:

- Tạo **bản sao** của root CA truststore được quản lý rồi thêm internal CA đã xác minh.
- Xây custom `TrustManager`/`SSLContext` để kết hợp các trust sources phù hợp, có kiểm tra chặt chẽ.
- Sử dụng distro/enterprise CA management có quy trình chuẩn và đã kiểm tra container image.
- Nếu ứng dụng chỉ gọi internal endpoints, một truststore riêng với **duy nhất các CA nội bộ cần thiết** có thể phù hợp và hạn chế trust scope.

Đừng tạo truststore với tùy chọn tin “tất cả certificate” để giữ kết nối public HTTPS.

### 6.3. Property trỏ đến file không tồn tại là lỗi nguy hiểm

Ví dụ:

~~~bash
java -Djavax.net.ssl.trustStore=/not/a/real/file.p12 MyApp
~~~

Theo SunJSSE hiện hành, khi property được đặt nhưng file không tồn tại, có thể khởi tạo **truststore trống**, không tự động quay về `cacerts`.

Hậu quả: nhiều TLS connections bắt đầu thất bại, dù JDK vẫn có `cacerts` hợp lệ. Kiểm tra mount path, file permissions, initialization log và cấu hình thực của JVM **trước khi** suy “CA bị xóa”.

### 6.4. Thời điểm cấu hình quan trọng

Nên đặt `-Djavax.net.ssl.trustStore=...` và related properties **lúc JVM khởi động**, trước khi JSSE default context/trust managers được khởi tạo. Đặt `System.setProperty` muộn sau khi TLS clients/factories đã cache `SSLContext` có thể không đổi hành vi của các client hiện hữu.

Trong code cần trust policy khác nhau theo endpoint, nên tạo các `SSLContext` riêng với `TrustManagerFactory` được init bằng truststore đã xác minh.

## 7. Chương trình Java 17+ để kiểm tra trust anchors đang được JSSE dùng

**Mục tiêu:** Không gọi Internet; chỉ quan sát `cacerts`/`jssecacerts` trên runtime thực, default `TrustManagerFactory` và một truststore CA nội bộ tách biệt. Chương trình là bài tập **chỉ đọc**, không sửa JDK.

### 7.1. File Java hoàn chỉnh

~~~java
// File: OpenJdkRootCaDemo.java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import javax.net.ssl.TrustManager;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509TrustManager;

public final class OpenJdkRootCaDemo {
    static X509TrustManager manager(KeyStore trustStore) throws Exception {
        TrustManagerFactory factory = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        factory.init(trustStore);
        return Arrays.stream(factory.getTrustManagers())
                .filter(X509TrustManager.class::isInstance)
                .map(X509TrustManager.class::cast)
                .findFirst().orElseThrow();
    }

    public static void main(String[] args) throws Exception {
        Path security = Path.of(System.getProperty("java.home"),
                "lib", "security");
        System.out.println("cacerts file exists = "
                + Files.isRegularFile(security.resolve("cacerts")));
        System.out.println("jssecacerts file exists = "
                + Files.isRegularFile(security.resolve("jssecacerts")));
        System.out.println("explicit trustStore property set = "
                + (System.getProperty("javax.net.ssl.trustStore") != null));

        X509TrustManager defaults = manager(null);
        System.out.println("default trusted issuer entries > 0 = "
                + (defaults.getAcceptedIssuers().length > 0));

        char[] password = System.getenv("DEMO_TRUSTSTORE_PASSWORD")
                .toCharArray();
        KeyStore custom = KeyStore.getInstance("PKCS12");
        try (var input = Files.newInputStream(Path.of(args[0]))) {
            custom.load(input, password);
        }
        System.out.println("custom truststore size = " + custom.size());
        System.out.println("custom entry is certificate = "
                + custom.isCertificateEntry("demo-root"));

        X509Certificate root = (X509Certificate)
                custom.getCertificate("demo-root");
        System.out.println("custom certificate is CA = "
                + (root.getBasicConstraints() >= 0));
        System.out.println("custom certificate subject = "
                + root.getSubjectX500Principal());
        X509TrustManager customManager = manager(custom);
        System.out.println("custom trusted issuer entries = "
                + customManager.getAcceptedIssuers().length);
    }
}
~~~

**Giải thích:**

- `java.home` là runtime đang chạy, không nhất thiết bằng `JAVA_HOME` của shell.
- `Files.isRegularFile` chỉ kiểm tra file tồn tại; không tự xác nhận file đang được JSSE chọn.
- `manager(null)` bảo `TrustManagerFactory` dùng **default trust material** theo provider và system properties.
- `getAcceptedIssuers()` cho một cái nhìn về các chứng thư issuer được trust manager công bố; **không** chứng minh mọi certificate chain đến các issuers đó được JSSE chấp nhận trong mọi ngữ cảnh/chính sách.
- `custom.isCertificateEntry` và `getBasicConstraints` minh họa kiểm tra một CA trong truststore riêng.
- `custom.load(input, password)` mở một **PKCS12 truststore test** dùng environment password. Trên production cần bảo vệ nguồn credentials theo secret management của hệ thống; không hardcode private-key password.

Chương trình nhận **một** đối số: đường dẫn truststore PKCS12 chỉ chứa demo CA đã tạo ở mục 8.

### 7.2. Biên dịch

~~~bash
javac --release 17 OpenJdkRootCaDemo.java
~~~

Cần JDK có compiler Java 17+ và module Java SE gồm `java.base` và `java.management`? Trong chương trình này chỉ dùng `java.base`, không cần thêm module hay thư viện.

### 7.3. Kiểm thử mặc định và với truststore riêng

Sau khi tạo `demo-trust.p12` bằng `keytool` theo mục 8 và đặt:

~~~bash
export DEMO_TRUSTSTORE_PASSWORD='local-demo-only-382'
~~~

chạy:

~~~bash
java OpenJdkRootCaDemo demo-trust.p12
~~~

Kết quả quan sát trên **JDK 24 của môi trường thử nghiệm**:

~~~text
cacerts file exists = true
jssecacerts file exists = false
explicit trustStore property set = false
default trusted issuer entries > 0 = true
custom truststore size = 1
custom entry is certificate = true
custom certificate is CA = true
custom certificate subject = CN=Demo Root CA, OU=Training, O=Local Only
custom trusted issuer entries = 1
~~~

Trên JDK và container khác, `jssecacerts` có thể tồn tại, `cacerts` có thể được thay bằng cơ chế khác và số trusted issuers thay đổi. Đừng dùng exact output này làm test portable cho mọi JDK distribution.

Dùng property để chọn truststore riêng:

~~~bash
java -Djavax.net.ssl.trustStore=demo-trust.p12 \
     -Djavax.net.ssl.trustStoreType=PKCS12 \
     -Djavax.net.ssl.trustStorePassword=local-demo-only-382 \
     OpenJdkRootCaDemo demo-trust.p12
~~~

Trong lần thử môi trường local, dòng `explicit trustStore property set` đổi sang `true`, còn default JSSE TrustManager được init theo truststore riêng. Password hiển thị ở đây **chỉ là chuỗi minh họa cho file demo đã tạo tạm**, không phải mẫu để đưa secret thật vào command line; trên production dùng secret management và cách cấp mật khẩu an toàn.

**Lưu ý:** Chương trình đang in boolean `default trusted issuer entries > 0` chứ không in số lượng. Khi test một truststore thiếu file với SunJSSE, giá trị có thể là false; ứng dụng thật phải xử lý cấu hình thiếu file như lỗi triển khai, không “tự bỏ qua TLS checks”.

## 8. Tạo Root CA giả lập tách biệt để học, không chạm vào `cacerts`

**Chỉ trên thư mục demo cách ly.** Toàn bộ certificate/private key được sinh bằng `keytool` cho mục đích test, hạn ngắn. **Không** đưa root CA/private key này vào môi trường production, không đưa private key của CA vào artifact ứng dụng, không coi auto-generated CA là đáng tin ngoài thí nghiệm.

### 8.1. Sinh một CA bằng `keytool`

Tạo thư mục demo rồi chạy ở đó. Ví dụ bash:

~~~bash
export DEMO_TRUSTSTORE_PASSWORD='local-demo-only-382'

keytool -genkeypair \
  -alias demo-ca \
  -keyalg RSA -keysize 2048 -validity 7 \
  -dname 'CN=Demo Root CA, OU=Training, O=Local Only' \
  -ext 'BC=ca:true' \
  -ext 'KU=keyCertSign,cRLSign' \
  -keystore demo-root.p12 -storetype PKCS12 \
  -storepass:env DEMO_TRUSTSTORE_PASSWORD \
  -keypass:env DEMO_TRUSTSTORE_PASSWORD
~~~

Tại đây `demo-root.p12` chứa **private key của CA** và certificate tự ký. Nó không phải truststore để distribute cho client vì có private key.

### 8.2. Xuất public certificate

~~~bash
keytool -exportcert -rfc \
  -alias demo-ca \
  -keystore demo-root.p12 \
  -storepass:env DEMO_TRUSTSTORE_PASSWORD \
  -file demo-root.pem
~~~

`demo-root.pem` là **certificate công khai**, không chứa private key của CA. Nhưng certificate công khai chưa tự trở thành đáng tin; bạn phải xác minh fingerprint/nguồn theo chính sách trước khi import vào hệ thống thật. Trong test tự sinh, ta biết nguồn vì vừa tạo CA trong workspace cách ly.

### 8.3. Import vào truststore test duy nhất

~~~bash
keytool -importcert -noprompt \
  -alias demo-root \
  -file demo-root.pem \
  -keystore demo-trust.p12 -storetype PKCS12 \
  -storepass:env DEMO_TRUSTSTORE_PASSWORD
~~~

Lệnh import sinh file `demo-trust.p12` trong thư mục hiện tại. `-noprompt` **chỉ thích hợp ở demo có CA do chính ta tạo và đã biết nguồn**. Không dùng `-noprompt` để tin một CA bên ngoài chưa kiểm fingerprint, vì thao tác import một CA là quyết định security-sensitive.

Kiểm tra:

~~~bash
keytool -list \
  -keystore demo-trust.p12 \
  -storetype PKCS12 \
  -storepass:env DEMO_TRUSTSTORE_PASSWORD
~~~

Kết quả trên môi trường thử nghiệm cho thấy **1 trustedCertEntry** tên `demo-root`. Fingerprint SHA-256 là giá trị của certificate vừa được sinh ngẫu nhiên, thay đổi mỗi lượt nên **không** được hardcode vào bài hoặc CI.

### 8.4. Trên Windows PowerShell

Thay dòng `export ...` bằng:

~~~powershell
$env:DEMO_TRUSTSTORE_PASSWORD = 'local-demo-only-382'
~~~

Các lệnh `keytool` ở trên vẫn có cùng ý nghĩa; khi cần nối dòng, PowerShell dùng dấu backtick của shell thay cho `\` trong bash, hoặc viết mỗi lệnh trên **một dòng**.

**Dọn dẹp demo sau khi học:** xóa các `.p12` và private key tạo cho test ở **đúng thư mục demo**. Không dùng câu lệnh xóa rộng trỏ vào `JAVA_HOME` hoặc truststore của ứng dụng.

## 9. Chứng minh trust anchor ảnh hưởng đến TLS thật: local HTTPS handshake

Phần này tạo một CA test, dùng nó **ký certificate leaf của localhost**, rồi thử TLS handshake trên **loopback**. Không gọi external websites hay dùng bất kỳ CA public nào.

**Mục tiêu:** Chứng minh tập root CA trong client truststore quyết định việc tin cậy đường PKIX, ngay cả khi application code và server certificate không đổi.

~~~text
Local CA (private key chỉ ở thư mục demo)
    └─ ký server leaf: SAN=dns:localhost
           └─ SSLServerSocket bound 127.0.0.1

Java client 1: SSLContext.getDefault()
    └─ không có CA test → handshake bị từ chối

Java client 2: SSLContext sử dụng client-trust.p12
    └─ có CA test → handshake thành công
~~~

### 9.1. Chuẩn bị certificate chain bằng `keytool`

Trong **thư mục demo mới** (độc lập với các file ở mục 8), dùng bash:

~~~bash
export DEMO_TLS_PASS='local-tls-demo-only'

# 1. Sinh root CA test có quyền ký certificates.
keytool -genkeypair -alias root \
  -keyalg RSA -keysize 2048 -validity 7 \
  -dname 'CN=Training CA, O=Local Only' \
  -ext 'BC=ca:true' -ext 'KU=keyCertSign,cRLSign' \
  -keystore ca.p12 -storetype PKCS12 \
  -storepass:env DEMO_TLS_PASS -keypass:env DEMO_TLS_PASS

# 2. Sinh keypair server localhost.
keytool -genkeypair -alias server \
  -keyalg RSA -keysize 2048 -validity 3 \
  -dname 'CN=localhost, O=Local Only' \
  -ext 'SAN=dns:localhost' \
  -keystore server.p12 -storetype PKCS12 \
  -storepass:env DEMO_TLS_PASS -keypass:env DEMO_TLS_PASS

# 3. Xuất public root certificate.
keytool -exportcert -alias root -rfc \
  -file root.pem -keystore ca.p12 \
  -storepass:env DEMO_TLS_PASS

# 4. Server tạo CSR.
keytool -certreq -alias server \
  -file server.csr -keystore server.p12 \
  -storepass:env DEMO_TLS_PASS

# 5. Root CA ký leaf, giữ SAN localhost và mục đích serverAuth.
keytool -gencert -alias root \
  -infile server.csr -outfile server.crt \
  -keystore ca.p12 -storepass:env DEMO_TLS_PASS \
  -ext 'SAN=dns:localhost' \
  -ext 'KU=digitalSignature,keyEncipherment' \
  -ext 'EKU=serverAuth' -validity 2

# 6. Import public root và reply vào keystore server.
keytool -importcert -noprompt -alias training-root \
  -file root.pem -keystore server.p12 \
  -storepass:env DEMO_TLS_PASS

keytool -importcert -noprompt -alias server \
  -file server.crt -keystore server.p12 \
  -storepass:env DEMO_TLS_PASS

# 7. Tạo một truststore riêng cho client, chỉ chứa public CA.
keytool -importcert -noprompt -alias training-root \
  -file root.pem -keystore client-trust.p12 \
  -storetype PKCS12 -storepass:env DEMO_TLS_PASS
~~~

**Lưu ý an toàn:**

- `ca.p12` có **root CA private key**: chỉ dùng thử nghiệm, tuyệt đối không copy vào client image.
- `server.p12` có **server private key**; dùng cho phía server TLS, không copy vào client truststore.
- `client-trust.p12` chỉ chứa certificate public của CA test.
- `-noprompt` chỉ dùng vì đang tự tạo tất cả certificates trong sandbox; quy trình sản xuất phải có xác minh fingerprint, approval và provenance.
- Certificate có hiệu lực ngắn vài ngày để hạn chế rủi ro test; không dùng hết hạn ở production.
- Nếu chạy lại, dùng thư mục trống mới; alias/file cũ có thể khiến `keytool` báo đã tồn tại hoặc không đúng chain.

### 9.2. File Java 17+ hoàn chỉnh — local TLS server và hai clients

~~~java
// File: LocalTlsTrustDemo.java
import java.net.InetAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.net.ssl.*;

public final class LocalTlsTrustDemo {
    private static final char[] PASS =
            System.getenv("DEMO_TLS_PASS").toCharArray();

    private static KeyStore store(String name) throws Exception {
        KeyStore value = KeyStore.getInstance("PKCS12");
        try (var input = Files.newInputStream(Path.of(name))) {
            value.load(input, PASS);
        }
        return value;
    }

    private static SSLContext serverContext(String path) throws Exception {
        KeyManagerFactory factory = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        factory.init(store(path), PASS);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(factory.getKeyManagers(), null, null);
        return context;
    }

    private static SSLContext clientContext(String path) throws Exception {
        TrustManagerFactory factory = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        factory.init(store(path));
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, factory.getTrustManagers(), null);
        return context;
    }

    private static boolean connect(SSLContext context, int port)
            throws Exception {
        try (SSLSocket socket = (SSLSocket)
                context.getSocketFactory().createSocket(
                        "localhost", port)) {
            socket.setSoTimeout(5000);
            SSLParameters params = socket.getSSLParameters();
            params.setEndpointIdentificationAlgorithm("HTTPS");
            socket.setSSLParameters(params);
            socket.startHandshake();
            return true;
        } catch (SSLHandshakeException expected) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        SSLContext server = serverContext(args[0]);
        SSLContext trusted = clientContext(args[1]);
        AtomicBoolean accepted = new AtomicBoolean(false);

        try (SSLServerSocket listener = (SSLServerSocket)
                server.getServerSocketFactory().createServerSocket(
                        0, 5, InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(5000);
            Thread serverThread = new Thread(() -> {
                for (int i = 0; i < 2; i++) {
                    try (SSLSocket socket = (SSLSocket)
                            listener.accept()) {
                        socket.setSoTimeout(5000);
                        socket.startHandshake();
                        if (i == 1) {
                            accepted.set(true);
                        }
                    } catch (Exception ignored) {
                        // First handshake is expected to fail at client side.
                    }
                }
            }, "tls-test-server");
            serverThread.start();

            boolean defaultWorked = connect(SSLContext.getDefault(),
                    listener.getLocalPort());
            boolean customWorked = connect(trusted,
                    listener.getLocalPort());
            serverThread.join(6000);

            System.out.println("default trust rejected local CA = "
                    + !defaultWorked);
            System.out.println("custom trust accepted signed server = "
                    + customWorked);
            System.out.println("server handshake completed = "
                    + accepted.get());
            System.out.println("server thread terminated = "
                    + !serverThread.isAlive());
        }
    }
}
~~~

### 9.3. Chạy bài kiểm thử

~~~bash
javac --release 17 LocalTlsTrustDemo.java
java LocalTlsTrustDemo server.p12 client-trust.p12
~~~

**Stdout đã được kiểm chứng trên OpenJDK/HotSpot JDK 24:**

~~~text
default trust rejected local CA = true
custom trust accepted signed server = true
server handshake completed = true
server thread terminated = true
~~~

**Giải thích:**

1. Server được cấp leaf certificate từ **CA nội bộ do demo tạo**.
2. `SSLContext.getDefault()` không có CA mới tạo trong default roots, vì vậy client thứ nhất từ chối certificate chain.
3. Client thứ hai tạo `TrustManagerFactory` từ `client-trust.p12`. Chain được xác nhận về trust anchor nội bộ; `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` cũng kích hoạt hostname verification, khớp SAN `localhost`.
4. Server hoàn tất handshake của client thứ hai và thread test kết thúc.
5. **Không có public network request**: server bound loopback và dùng cổng ngẫu nhiên do OS cấp.

Đây là **một bài thử chứng minh trust anchors ảnh hưởng tới TLS**, không phải mã nguồn server production. Phần `catch (Exception ignored)` cố ý chỉ nằm trong server thread test vì handshake đầu tiên dự kiến thất bại; code production không nên im lặng bỏ qua mọi TLS exception.

### 9.4. Những gì bài thử *không* chứng minh

- Không chứng minh CA test đủ uy tín để phát hành certificate public.
- Không chứng minh `cacerts` của mọi JDK đều có đúng tập root CA giống nhau.
- Không kiểm chứng certificate revocation qua CRL/OCSP.
- Không kiểm chứng proxy, TLS interception, mutual TLS hoặc certificate pinning.
- Không khuyến nghị import certificate của một server bất kỳ vào global `cacerts`.

**Điểm chứng minh:** chỉ thay truststore client, cùng server certificate có thể bị từ chối hoặc được tin tùy root CA anchor và validation policy.

## 10. Phân biệt truststore (tin người khác) và keystore (danh tính của mình)

| Khía cạnh | Truststore của client | Server/client identity keystore |
| --- | --- | --- |
| Mục tiêu | Quyết định CA/peer nào được tin | Cung cấp private key và certificate chain chứng minh danh tính |
| Nội dung điển hình | `TrustedCertificateEntry` của root/internal CA | `PrivateKeyEntry` + chain |
| JSSE class | `TrustManagerFactory` | `KeyManagerFactory` |
| Property | `javax.net.ssl.trustStore` | `javax.net.ssl.keyStore` |
| Ví dụ bài demo | `client-trust.p12` | `server.p12` |
| Đòi private key? | **Không** đối với public root trust anchors | **Có** để server chứng minh danh tính |
| Dùng cho mTLS? | Tin CA đã cấp client certificate ở phía server | Client cung cấp certificate và private key ở phía client |

Một ứng dụng Java gọi HTTPS thông thường **không cần private key client** nếu endpoint không yêu cầu mTLS. Nhưng nó cần cơ chế xác minh TLS server, thường là `TrustManager` có một tập CA roots tin cậy phù hợp.

**Không đặt root CA private key vào truststore/client image**. Root CA private key là tài sản cực kỳ nhạy cảm, chỉ dành cho quy trình CA có bảo vệ nghiêm ngặt.

## 11. Nhà phân phối OpenJDK, hệ điều hành và container có thể có tập CA khác nhau

**“OpenJDK” mô tả một dự án/mã nguồn JDK**, không bảo đảm mọi binary do mọi nhà cung cấp đóng gói có truststore từng byte giống nhau.

Có thể khác ở:

- CA được thêm/xóa qua các JDK CPU/PSU updates.
- Chính sách root program và điều kiện license/distribution.
- OS packages có cơ chế đồng bộ root CA hệ điều hành sang Java `cacerts`, đôi khi dùng symlink hoặc script update.
- Base image container rất gọn, runtime tạo bởi `jlink` hay custom distribution có cách đóng gói khác.
- Enterprise image có root CA nội bộ hoặc truststore riêng.
- Security properties `jdk.certpath.disabledAlgorithms` hoặc `jdk.security.caDistrustPolicies` có thể loại một số chuỗi dù certificate vẫn có mặt trên disk.
- Quy tắc DNS/hostname, network proxy hoặc custom security provider.

### 11.1. Vì sao JDK trên laptop “được” mà container “lỗi”?

Ví dụ:

~~~text
Developer laptop:
  Java runtime A
  cacerts có Root CA X
  → HTTPS hoạt động

Production container:
  Java runtime B (khác distribution/image)
  cacerts thiếu X hoặc property trỏ truststore riêng
  → PKIX validation failed
~~~

Đừng chỉ so output `java -version` ở máy developer. Phải chẩn đoán bằng **bản image/container thật**:

~~~bash
java -version
which java
which keytool
keytool -list -cacerts
~~~

Đường dẫn `which` dùng bash/Linux; PowerShell có thể dùng `Get-Command java` và `Get-Command keytool`. Kiểm tra thêm `System.getProperty("java.home")` bên trong process, không chỉ `JAVA_HOME`.

### 11.2. Đừng tự động coi OS CA store = JVM truststore

Nhiều môi trường có cả OS certificate bundle và Java `cacerts`. Nhưng liệu JDK đó đồng bộ OS roots, có symlink hay dùng SunJSSE mặc định là vấn đề **của distribution/build**. Không có quy tắc Java SE “thêm CA bằng hệ điều hành là tất cả ứng dụng Java ngay lập tức tin”.

Ví dụ nhập CA bằng một lệnh quản trị OS nhưng Java container vẫn dùng file `cacerts` cũ/khác là một lỗi triển khai dễ gặp.

### 11.3. Cập nhật roots bằng pipeline, không sửa container đang chạy tùy tiện

Nếu cần trust thêm CA nội bộ:

1. Xác minh certificate và SHA-256 fingerprint từ kênh quản trị độc lập.
2. Dùng cấu hình dựng image/secrets an toàn, tạo truststore có provenance.
3. Đảm bảo không xóa nhầm public roots cần thiết (nếu ứng dụng dùng cả public và internal HTTPS).
4. Chạy integration test đến các endpoint thực tế trong môi trường kiểm soát.
5. Build/publish phiên bản image bất biến và rolling rollout.
6. Có rollback và quy trình thu hồi root CA khi mất tin cậy.

Đừng `kubectl exec` vào pod rồi sửa `cacerts` ngẫu nhiên: thay đổi khó tái lập, có thể mất sau restart, và khó kiểm toán.

## 12. Chính sách tin cậy động: thêm root cũng không miễn kiểm tra certificate

**Security policy của JDK tiếp tục thay đổi theo các bản cập nhật.** Chẳng hạn, một root CA có thể vẫn xuất hiện trong tập certificates, nhưng một JDK build áp dụng policy **distrust** cho một số CA hoặc cho certificate được phát hành trong một khoảng thời gian nhất định.

Các property đáng biết:

~~~text
jdk.certpath.disabledAlgorithms
jdk.tls.disabledAlgorithms
jdk.security.caDistrustPolicies
~~~

Chúng thường được định nghĩa trong:

~~~text
$JAVA_HOME/conf/security/java.security
~~~

### 12.1. `jdk.certpath.disabledAlgorithms`

Giới hạn các thuật toán/chữ ký và key size không được chấp nhận trong certificate path validation theo policy. Một chain được ký bằng thuật toán yếu có thể bị từ chối dù root public key tương ứng đã có trong truststore.

### 12.2. `jdk.tls.disabledAlgorithms`

Giới hạn TLS protocols/cipher suites/algorithms mà JSSE được phép sử dụng. Không phải cứ chain đúng root là TLS handshake thành công nếu server chỉ chấp nhận protocol/cipher đã bị disabled.

### 12.3. `jdk.security.caDistrustPolicies`

Các JDK bảo mật hiện hành có thể có chính sách từ chối certificate chain dựa trên những CA nhất định và điều kiện cụ thể. **Không** dùng công thức “root nằm trong `cacerts` → luôn trusted” như một quy tắc bất biến.

Không nên “sửa” lỗi bằng cách xóa các policy bảo mật mới khỏi `java.security` hoặc bật thuật toán lỗi thời mà không có đánh giá rủi ro/chấp thuận. Thường nên sửa certificate deployment hoặc cập nhật trust chain theo CA được phép.

### 12.4. Revocation là một chính sách riêng

Certificate có thể đã bị thu hồi. Việc kiểm tra CRL/OCSP trong JSSE phụ thuộc provider, API và policy configuration; **không được giả định chỉ có `cacerts` là revocation checking đã bật và hoàn hảo**.

Đối với hệ thống có yêu cầu tuân thủ cao, nên xác định chính sách revocation/timeout/failure mode dựa trên tài liệu JSSE đúng bản JDK và quy trình quản trị PKI.

## 13. Xử lý truststore cho CA nội bộ mà không phá public trust

### 13.1. Cách 1: Truststore riêng chỉ dành cho một internal service

Một client chỉ gọi service nội bộ có thể tạo một `SSLContext` riêng:

~~~java
KeyStore trust = KeyStore.getInstance("PKCS12");
try (var input = java.nio.file.Files.newInputStream(
        java.nio.file.Path.of("/opt/app/internal-trust.p12"))) {
    trust.load(input, password);
}

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trust);

SSLContext internal = SSLContext.getInstance("TLS");
internal.init(null, tmf.getTrustManagers(), null);
~~~

Đoạn trên **nằm trong một method** với biến `password` là `char[]` do secret manager cung cấp. Nó không phải chương trình độc lập vì thiếu imports/exception handling của ứng dụng. Sử dụng `internal` chỉ cho những HTTP/TLS clients dành cho internal service; giữ default SSLContext cho các public endpoints nếu cần.

### 13.2. Cách 2: File truststore gồm cả public roots và internal root

Nếu ứng dụng cần vừa public CA vừa private PKI, có thể tạo artifact CA truststore đã **kết hợp có chủ đích** từ public trust anchor set được phân phối, rồi thêm CA nội bộ sau khi xác minh.

Cần nhớ:

- Import vào một **file khác** để không làm hỏng JDK đang dùng.
- Test TLS đến cả public và internal endpoints.
- Quản lý lifecycle/rotation của internal CA.
- Khi JDK phát hành bản update root/distrust, rebuild combined store từ source được kiểm soát. Không để combined store đứng yên mãi, vì sẽ thiếu các thay đổi root trust mới.
- Không import **leaf** certificate của từng server như phương án dài hạn nếu đã có private enterprise CA được quản lý.

### 13.3. Cách 3: OS/distribution trust management

Một số Linux JDK distributions được tích hợp với OS CA management. Sử dụng phương án này nếu vendor hướng dẫn rõ và có integration test xác nhận Java process thực dùng CA mới.

Không suy rằng mọi JDK container đều theo symlink `/etc/ssl/certs`: kiểm tra từng image.

### 13.4. Điều không nên làm

~~~java
// Ví dụ ý tưởng nguy hiểm — KHÔNG sử dụng:
// X509TrustManager checkServerTrusted(...) { /* không kiểm gì */ }
~~~

Một TrustManager “trust all” phá bỏ mục đích của PKIX và có thể tạo lỗ hổng man-in-the-middle. Tương tự, không vô hiệu hostname verification, không bật HTTPS client option “insecure” trong production để tránh lỗi chứng thư.

## 14. Troubleshooting: khi một ứng dụng OpenJDK báo TLS/PKIX error

### Bước 1 — Xác định process/runtime thực

Ghi:

~~~text
java.version
java.vendor
java.home
javax.net.ssl.trustStore
javax.net.ssl.trustStoreType
~~~

Không in mật khẩu truststore vào log. Kiểm tra các property bằng code/chẩn đoán của chính process hoặc runtime tương thích. Tránh lấy `keytool` từ JDK khác để đối chiếu tập CA.

### Bước 2 — Kiểm tra truststore đang được chọn

Thứ tự SunJSSE: explicit property → `jssecacerts` → `cacerts`. Đối chiếu file có tồn tại, quyền đọc, định dạng và nội dung certificates.

### Bước 3 — Kiểm tra chain bên server

Trên môi trường có OpenSSL:

~~~bash
openssl s_client -connect api.example.test:443 \
  -servername api.example.test -showcerts
~~~

Đây là ví dụ chẩn đoán tới hostname **cần thay bằng host được phép kiểm tra**. Không nên kết luận chỉ từ `Verify return code` của OpenSSL vì OpenSSL có thể dùng **truststore khác JDK**. Lệnh chủ yếu giúp xem server đưa ra chain nào và có thiếu intermediate không.

### Bước 4 — Bật log JSSE trong môi trường kiểm soát

~~~bash
java -Djavax.net.debug=ssl,handshake,trustmanager \
     -jar app.jar
~~~

Lệnh gợi ý debug TLS trên HotSpot; log có thể rất dài và chứa thông tin nhạy cảm về endpoint/handshake. Không bật vô hạn trên production hoặc upload log có secrets lên nơi không kiểm soát.

`javax.net.debug` dùng cho **JSSE/TLS**, khác với `-Xlog:handshake` của VM thread handshakes.

### Bước 5 — Phân biệt lớp lỗi

| Triệu chứng | Khả năng | Điều cần kiểm tra |
| --- | --- | --- |
| `PKIX path building failed` | Thiếu anchor/intermediate hoặc policy validation | Truststore thực, server chain, PKIX constraints |
| `unable to find valid certification path` | Không dựng được đường dẫn được tin | CA root, intermediate và trust manager |
| `No subject alternative DNS name matching ...` | Hostname mismatch | SAN của leaf, hostname gọi |
| `CertificateExpiredException` | Leaf/intermediate expired | Ngày, thời gian, chain mới |
| `Algorithm constraints check failed` | Algorithm/key không được phép | JDK security properties, certificate algorithm |
| `trustAnchors parameter must be non-empty` | Truststore rỗng/không có anchor phù hợp | Property file path, content, JSSE selection |
| Một máy được, một máy lỗi | JDK distro/config khác | `java.home`, `cacerts`, image, trustStore property |
| Kết nối qua proxy mới lỗi | Proxy thay TLS certificate | Enterprise CA policy, proxy behavior |
| Sau nâng JDK mới lỗi | CA program/distrust/algorithm policy đổi | JDK release/security notes, certificates |
| mTLS client auth bị từ chối | Thiếu/sai client identity keystore hoặc trust server-side | KeyManager, private key, client cert trust |

Không phải mọi thông báo trên luôn xuất hiện nguyên văn ở mọi JDK. Dùng stack trace và TLS debug context thay vì regex cứng như một cách chẩn đoán duy nhất.

### Bước 6 — Sửa theo nguyên nhân và test lại

- Root không tin và đã được phê duyệt → cấp CA anchor đúng scope.
- Missing intermediate → sửa server certificate chain để gửi intermediate.
- Hostname sai → cấp certificate có SAN đúng hoặc sửa endpoint; **không tắt kiểm tra host**.
- Hết hạn → thay/renew certificate.
- Bị distrust/algorithm policy → liên hệ CA/PKI team, chuyển sang chain/algorithm được chấp nhận.
- Truststore path sai → sửa mount/path và restart khi cần.
- JDK distro khác → quản lý root CA set theo release image, integration test.
- Có proxy → xác định trust policy của enterprise và quyền/nguồn CA proxy.
- mTLS thiếu client cert → cấu hình KeyManager/identity material, không chỉ import thêm root ở client.

## 15. Rotating CA roots và cập nhật JDK

Tập root CA **không cố định**. Có root được thêm vào chương trình tin cậy, có root hết hạn, bị loại do đánh giá rủi ro hoặc subject to distrust policy. Một ứng dụng pin toàn bộ file `cacerts` cũ trong container image nhiều năm có thể không nhận các cập nhật cần thiết.

Vận hành an toàn:

1. Theo dõi **JDK security update/release notes** từ vendor.
2. Cập nhật JDK/container base image theo kế hoạch, không chỉ update application JAR.
3. Theo dõi thay đổi `cacerts` và `java.security` để nhận biết root adds/removals/distrust.
4. Nếu dùng combined truststore riêng, rebuild/sync từ nguồn quản trị có cập nhật, tránh giữ roots lỗi thời.
5. Thử TLS đến endpoints quan trọng trước rollout.
6. Chuẩn bị quá trình chuyển CA với **overlap window** khi rotate để client không bị đứt kết nối.
7. Dỡ bỏ trust anchor đã không còn cần hoặc không còn an toàn, theo chính sách phê duyệt.
8. Không chụp toàn bộ `cacerts` từ một bản JDK rồi dùng suốt đời trên JDK khác.

### 15.1. Chứng thư “đã có trong file” nhưng không được phép làm trust anchor

Một root entry có mặt trên đĩa chưa chắc được dùng để chấp nhận kết nối: security provider có thể từ chối chain do `jdk.security.caDistrustPolicies`, `jdk.certpath.disabledAlgorithms` hoặc ràng buộc khác. Vì vậy inventory file và kết quả **TLS integration test thực tế** là hai tầng kiểm chứng khác nhau.

### 15.2. Certificate pinning không thay thế hoàn toàn quản trị CA

Pinning có thể hữu ích trong một số threat models nhưng phải được thiết kế và rotate cẩn thận, nếu không dễ gây outage khi thay certificate/key. Với root CA store của OpenJDK, mục tiêu thông thường là xác thực PKIX/hostname theo trust policy; không nên coi mọi certificate pinning thủ công là “bảo mật hơn” hoặc bắt buộc.

## 16. CA public, CA enterprise và tự ký: chọn đúng nguồn tin cậy

| Trường hợp | Trust policy khuyến nghị | Cảnh báo |
| --- | --- | --- |
| HTTPS public API có certificate public CA chuẩn | Dùng updated default roots nếu phù hợp | Vẫn kiểm chain, SAN, algorithm |
| Internal service cấp bởi enterprise CA | Import CA đã xác minh vào truststore riêng/combined store | Giữ scope theo service/organization |
| Test localhost với root do mình tạo | Dùng ephemeral CA/truststore riêng | Không copy CA key lên client, không production |
| Self-signed leaf bất kỳ từ Internet | **Không** mặc nhiên chấp nhận | Xác minh out-of-band; ưu tiên PKI được quản lý |
| TLS inspection proxy theo chính sách công ty | Xác minh enterprise root và quyền quản trị | Không tự động tin proxy ngoài kiểm soát |
| mTLS giữa services | Cả truststore và identity keystore mỗi phía theo vai trò | Trust CA không tự cấp client private key |
| Mobile app/custom HTTP client không dùng JSSE mặc định | Kiểm tra stack TLS riêng của thư viện | `cacerts` không chắc được sử dụng |
| Native library OpenSSL dùng từ Java | Theo trust config của OpenSSL/library | Không mặc định Java `cacerts` là nguồn root |

**Một câu dễ nhớ:** ai nắm **private key** chứng minh danh tính của họ; ai nắm **trust anchors** quyết định họ sẽ tin chứng thư do những CA nào xác thực. Hai nhiệm vụ đó là hai chiều khác nhau.

## 17. Quy tắc security tối thiểu khi thao tác `keytool`

- Không import CA lạ vào global `cacerts` chỉ để qua một lỗi TLS.
- Xác minh root certificate fingerprint (ưu tiên SHA-256) với kênh quản trị đáng tin **khác** kênh tải file.
- Có review/approval cho việc thêm/xóa CA; tạo trail audit.
- Không đưa **root CA private key** vào truststore/client image.
- Không hardcode production passwords trong code/git/command-line logs.
- Thực hiện import trên **copy hoặc artifact được quản lý**, không chỉnh JDK file tại runtime không tái lập.
- Kiểm tra thời hạn, CA Basic Constraints, Key Usage, naming và path restrictions của chứng thư dự định tin.
- Giữ đủ trust anchors cho những endpoints được phép; hạn chế độ rộng của internal truststore nếu phù hợp.
- Xem xét expiry/rotation/CA distrust theo cập nhật JDK.
- Đo bằng integration test có hostname verification.
- Không tắt certificate validation/hostname verification.
- Phân biệt store format `PKCS12` với kiểu entry `TrustedCertificateEntry`.

## 18. Câu hỏi và bài tập có đáp án

### Bài 1 — Mục đích của JEP 319

**Hỏi:** JEP 319 có mục tiêu chính nào?

**Đáp án:** Cung cấp một tập Root CA certificates mặc định có thể phân phối trong mã nguồn OpenJDK, giúp các bản build OpenJDK hữu dụng hơn cho TLS và giảm chênh lệch với các JDK binaries đã có roots.

### Bài 2 — Root tự ký

**Hỏi:** Chỉ thấy certificate tự ký hợp lệ có đủ tin nó không?

**Đáp án:** Không. Bất kỳ bên nào cũng có thể tự sinh keypair và tự ký. Trust anchor phải được chọn bằng nguồn/chính sách tin cậy độc lập.

### Bài 3 — Chain server

**Hỏi:** Server gửi leaf + intermediate nhưng không gửi root. Đây là lỗi TLS bắt buộc không?

**Đáp án:** Không. Root thường đã nằm ở truststore client. Quan trọng là client có đường PKIX hợp lệ đến trust anchor được tin.

### Bài 4 — `cacerts` chứa gì?

**Hỏi:** File JDK `cacerts` có private keys của public Root CAs không?

**Đáp án:** Không. Nó được dùng để lưu tập CA certificates/public keys tin cậy, không phải private keys của các CA.

### Bài 5 — `jssecacerts`

**Hỏi:** Nếu cả `jssecacerts` và `cacerts` có mặt, SunJSSE mặc định chọn file nào?

**Đáp án:** `jssecacerts` trước `cacerts`, khi không đặt trustStore property riêng.

### Bài 6 — Property truststore

**Hỏi:** Set `javax.net.ssl.trustStore=/opt/private.p12` có mặc định thêm public roots từ `cacerts` không?

**Đáp án:** Không. Với SunJSSE mặc định, file được chỉ định được dùng làm nguồn tin cậy; không tự gộp public roots.

### Bài 7 — Đường dẫn sai

**Hỏi:** Nếu trustStore property trỏ file không tồn tại, mặc định SunJSSE có luôn fallback `cacerts` không?

**Đáp án:** Không. Theo tài liệu, có thể tạo trust manager với truststore trống; cần sửa path/mount.

### Bài 8 — Distro khác nhau

**Hỏi:** Hai ứng dụng cùng Java source, nhưng chạy trên hai OpenJDK distributions khác nhau: roots luôn giống nhau?

**Đáp án:** Không. Số root, version update, CA policy, OS sync và cách đóng gói có thể khác.

### Bài 9 — CA mới được thêm

**Hỏi:** Thêm một CA vào default roots có nghĩa ứng dụng tự bỏ hostname verification không?

**Đáp án:** Không. HTTPS hostname verification vẫn là bước độc lập, cần SAN đúng.

### Bài 10 — `PKIX path building failed`

**Hỏi:** Lỗi này chứng minh root CA chắc chắn không có trong `cacerts`?

**Đáp án:** Không. Có thể thiếu intermediate, chọn nhầm truststore, policy/algorithm fail hoặc chain không hợp lệ.

### Bài 11 — `keytool` inventory

**Hỏi:** Lệnh đọc CA store của JDK mà không sửa là gì?

**Đáp án:** `keytool -list -cacerts`. Xem fingerprint chi tiết với `keytool -list -v -cacerts -alias ...`.

### Bài 12 — Private root key

**Hỏi:** File CA private key dùng ký server certificate có nên đưa lên client container để client tin server?

**Đáp án:** Không. Client chỉ cần public CA certificate được phê duyệt làm trust anchor. Root private key phải được bảo vệ riêng.

### Bài 13 — Local TLS test

**Hỏi:** Tại sao cùng server localhost, default JSSE client thất bại nhưng client dùng `client-trust.p12` thành công?

**Đáp án:** Default CA roots không có CA test, còn truststore riêng chứa root đã ký leaf. Hostname `localhost` cũng khớp SAN, nên PKIX/HTTPS policy đạt trong lượt thử.

### Bài 14 — Thay JDK

**Hỏi:** App local chạy HTTPS được, nhưng khi đổi JDK/container image thì lỗi. Nên làm gì đầu tiên?

**Đáp án:** Xác minh `java.home`, property truststore thực tế, `jssecacerts/cacerts`, CA entries, JDK security policies và server chain trong runtime image mới.

### Bài 15 — Security policy thay đổi

**Hỏi:** Một root còn trong file, nhưng TLS bị từ chối sau cập nhật JDK. Có thể do đâu?

**Đáp án:** Security policy như disabledAlgorithms/caDistrustPolicies hoặc điều kiện certificate path, không chỉ sự có mặt trong file.

### Bài 16 — Revocation

**Hỏi:** Chỉ có root CA trong `cacerts` thì OCSP/CRL luôn tự hoạt động và kiểm soát hoàn hảo?

**Đáp án:** Không. Revocation có cơ chế và chính sách riêng; xác minh với provider/JDK/cấu hình thực.

### Bài 17 — Truststore và identity keystore

**Hỏi:** Client cần xác thực server HTTPS thông thường: có nhất thiết phải có private key client không?

**Đáp án:** Không nếu không có mTLS. Client cần trust manager phù hợp; server trình certificate và chứng minh sở hữu private key phía server.

### Bài 18 — Trust all manager

**Hỏi:** Có nên viết `X509TrustManager` bỏ trống `checkServerTrusted` để xử lý lỗi SSL?

**Đáp án:** Không. Điều đó phá TLS certificate validation, tạo nguy cơ MITM; sửa truststore/chain và hostname đúng nguyên nhân.

### Bài 19 — OS CA vs Java CA

**Hỏi:** Import root CA vào OS store Linux chắc chắn khiến tất cả ứng dụng Java tin ngay không?

**Đáp án:** Không. Phụ thuộc JDK distribution/OS integration; cần xem JDK process thực đang sử dụng truststore nào.

### Bài 20 — Rotation

**Hỏi:** Một ứng dụng pin file `cacerts` của JDK cũ trong nhiều năm. Có rủi ro gì?

**Đáp án:** Bỏ lỡ bổ sung/loại bỏ root và các distrust/security updates, dẫn tới security gap hoặc lỗi TLS khi CA chuyển đổi. Cần cập nhật/quản trị trust source theo vòng đời release.

## 19. Checklist vận hành OpenJDK root certificates

- [ ] Biết JDK build/vendor/runtime image đang thực thi chương trình không?
- [ ] Có hiểu JEP 319 bổ sung public root CA certificates vào OpenJDK source từ JDK 10 không?
- [ ] Có phân biệt trust anchor/root CA với leaf/intermediate/identity private key không?
- [ ] Có hiểu certificate tự ký không tự động được tin chỉ vì nó self-signed không?
- [ ] Có xác định đúng `java.home/lib/security/cacerts` trong process không?
- [ ] Có kiểm tra `keytool` thuộc cùng JDK đang chạy không?
- [ ] Có biết trustStore property → `jssecacerts` → `cacerts` trong SunJSSE không?
- [ ] Có kiểm tra truststore path tồn tại, định dạng và quyền đọc không?
- [ ] Có tránh tin rằng truststore riêng tự động merge public roots không?
- [ ] Có chọn CA internal theo đúng scope thay vì global trust-all không?
- [ ] Có xác minh SHA-256 fingerprint bằng nguồn độc lập trước khi import CA thật không?
- [ ] Có bảo vệ Root CA private key và không đưa nó lên client image không?
- [ ] Có test cả đường PKIX/algorithm constraints và HTTPS hostname/SAN không?
- [ ] Có phân biệt vấn đề thiếu root với missing intermediate không?
- [ ] Có biết provider/app có thể dùng truststore khác JSSE mặc định không?
- [ ] Có tránh coi file `cacerts` giống nhau ở mọi JDK distribution không?
- [ ] Có theo dõi updates, root removals và `jdk.security.caDistrustPolicies` không?
- [ ] Có quyết định revocation policy nếu hệ thống cần không?
- [ ] Có quy trình rebuild combined truststore khi JDK root set cập nhật không?
- [ ] Có kiểm tra certificates trong Docker/Kubernetes runtime image chứ không chỉ trên laptop không?
- [ ] Có dùng TLS/JSSE debug có kiểm soát, không lộ secrets/log nhạy cảm không?
- [ ] Có tránh hardcode password production trên command line và source control không?
- [ ] Có theo dõi CA rotation/expiry/overlap window và test rollback không?
- [ ] Có test cả public HTTPS và internal HTTPS nếu ứng dụng cần cả hai không?
- [ ] Có không tắt hostname verification/TrustManager validation để né TLS error không?

## 20. Tài liệu chính thức và tham khảo vẫn còn áp dụng

- [JEP 319 — Root Certificates](https://openjdk.org/jeps/319): lý do OpenJDK cần tập root certificates mặc định, mục tiêu open-source root program và tác động với `cacerts`.
- [JDK 25 — Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html): thứ tự chọn `javax.net.ssl.trustStore`, `jssecacerts`, `cacerts`, `TrustManagerFactory` và `SSLContext`.
- [JDK 25 — `keytool` Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/keytool.html): `-list -cacerts`, `-printcert`, `-importcert`, `-storepass:env`, các quy tắc xác minh fingerprint.
- [Java SE 25 API — `TrustManagerFactory`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): `init(KeyStore)` và default trust manager algorithm.
- [Java SE 25 API — `X509TrustManager`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/X509TrustManager.html): `checkServerTrusted`, `getAcceptedIssuers`.
- [Java SE 25 API — `SSLContext`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLContext.html): `getDefault` và `init(KeyManager[], TrustManager[], SecureRandom)`.
- [Java SE 25 API — `PKIXParameters`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/cert/PKIXParameters.html): trust anchors, revocation-related settings trong PKIX validation.
- [Java SE 25 API — `KeyStore`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyStore.html): `TrustedCertificateEntry` và `PrivateKeyEntry`.
- [Java SE 17 API — `TrustManagerFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): tương thích với ví dụ `javac --release 17`.
- [Java SE 17 API — `SSLParameters`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): `setEndpointIdentificationAlgorithm("HTTPS")` trong demo loopback.
- [JDK 25 — Security Properties and Policies](https://docs.oracle.com/en/java/javase/25/security/java-security-overview1.html): bối cảnh cấu hình `java.security` và chính sách cryptographic algorithms.
- [JDK 25 — Release Notes](https://www.oracle.com/java/technologies/javase/25all-relnotes.html): các root CA additions/removals và distrust changes theo release/update.
- [JDK 25 — `java` Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-Djavax.net.ssl.trustStore=...` và JVM runtime configuration.
- [OpenJDK review document của JEP 319](https://cr.openjdk.org/~mullan/jeps/8191486.html): tóm tắt mục tiêu JEP 319 và lý do OpenJDK source trước đó thiếu public roots.

**Kết luận:** Tập root CA certificates có vai trò làm **điểm neo tin cậy mặc định** để JSSE/PKIX có thể xác thực certificate chains trong các kết nối TLS/HTTPS. JEP 319 của Java 10 đưa root certificates vào OpenJDK, cải thiện khả năng dùng HTTPS ngay sau khi cài JDK. Nhưng một certificate trong `cacerts` không tự bảo đảm TLS an toàn: cần chain hợp lệ, hostname verification, policy/algorithms phù hợp và quản lý trust anchors cập nhật. Vì các bản phân phối OpenJDK/container/JDK updates có thể dùng tập roots khác nhau, hãy kiểm tra **runtime thực**, dùng truststore riêng cho CA nội bộ có xác minh, và **không bao giờ** thay việc xác thực bằng TrustManager “trust all”.