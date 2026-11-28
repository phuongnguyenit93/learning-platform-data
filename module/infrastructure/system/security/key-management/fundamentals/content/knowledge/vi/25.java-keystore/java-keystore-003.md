# JKS

JKS (Java KeyStore) là định dạng kho khóa truyền thống của Java, dùng để lưu trữ private key cùng certificate chain tương ứng và các chứng chỉ được tin cậy. Ứng dụng Java có thể nạp kho này để xác thực máy chủ, cung cấp danh tính TLS hoặc thực hiện các thao tác mật mã cần khóa riêng.

Trong module `SECURITY_KEY_MANAGEMENT_FUNDAMENTALS`, JKS là một ví dụ cụ thể về cách lưu trữ và cấp quyền sử dụng khóa trong ứng dụng. Kho khóa giúp đóng gói key entry và certificate entry theo alias, nhưng mức an toàn còn phụ thuộc vào mật khẩu, quyền truy cập file, cách phân phối bí mật, provider và quy trình vận hành. JKS không thay thế KMS/HSM hoặc quy trình quản lý vòng đời khóa.

## 1. JKS là gì?

JKS là một loại `KeyStore` được Java cung cấp thông qua provider. File JKS có thể chứa các entry được định danh bằng alias. Ứng dụng Java sử dụng API `java.security.KeyStore` hoặc công cụ `keytool` để tạo, đọc, liệt kê, nhập, xuất và cập nhật các entry.

JKS là định dạng riêng có nguồn gốc từ hệ sinh thái Java. Từ JDK 9, định dạng mặc định của `keytool` và `KeyStore.getDefaultType()` chuyển sang PKCS12 theo JEP 229. JKS vẫn được hỗ trợ để tương thích với hệ thống cũ, nhưng khi làm việc với file JKS cần chỉ rõ `-storetype JKS` trong `keytool` hoặc `KeyStore.getInstance("JKS")` trong Java. Không nên suy ra định dạng chỉ từ phần mở rộng `.jks`; hãy kiểm tra loại kho bằng công cụ phù hợp.

JKS là định dạng lưu trữ. Nó không phải thuật toán mã hóa, giao thức TLS hay một dịch vụ quản lý khóa tập trung. File có thể được sao chép như một tệp thông thường, vì vậy bảo vệ file và mật khẩu là một phần của thiết kế bảo mật.

## 2. Các loại entry trong JKS

JKS thường được dùng với hai loại entry chính:

| Loại entry | Nội dung | Mục đích |
|---|---|---|
| `PrivateKeyEntry` | Private key và certificate chain chứa public key tương ứng | Cung cấp danh tính cho máy chủ TLS, client TLS hoặc thao tác ký số |
| `TrustedCertificateEntry` | Một chứng chỉ được ứng dụng đánh dấu là tin cậy | Làm trust anchor hoặc chứng chỉ tin cậy trong trust store theo chính sách của ứng dụng |

Một `PrivateKeyEntry` thường chứa private key của máy chủ và chuỗi chứng chỉ từ leaf certificate đến các intermediate CA. Private key không được gửi cho peer; ứng dụng dùng nó trong quá trình TLS hoặc ký số. Certificate chain cung cấp dữ liệu công khai để peer xây dựng đường dẫn tin cậy.

Một `TrustedCertificateEntry` chỉ chứa chứng chỉ công khai. Ví dụ, trust store có thể chứa root CA nội bộ hoặc chứng chỉ của một đối tác được tổ chức phê duyệt. Việc nhập chứng chỉ vào trust store thể hiện quyết định tin cậy của ứng dụng; không nên nhập chứng chỉ chỉ vì một kết nối đang báo lỗi.

Triển khai JKS tiêu chuẩn của Java không hỗ trợ lưu `SecretKeyEntry`. Nếu cần lưu khóa bí mật đối xứng, hãy chọn định dạng/provider hỗ trợ rõ loại entry đó, chẳng hạn PKCS12 trong các phiên bản Java hiện đại hoặc giải pháp quản lý khóa chuyên dụng. JCEKS từng được dùng cho secret key trong hệ sinh thái Java cũ, nhưng không nên mặc định chọn nó cho thiết kế mới nếu PKCS12 hoặc KMS phù hợp hơn.

## 3. Alias và certificate chain

Alias là tên định danh một entry trong kho. Alias không phải danh tính đã được xác thực và không phải bí mật. Một kho có thể có các alias như `tls-server`, `internal-root-ca`, `partner-api` hoặc `signing-key`.

Với `PrivateKeyEntry`, certificate chain cần bắt đầu bằng chứng chỉ đầu cuối chứa public key tương ứng với private key. Các chứng chỉ CA trung gian tiếp theo giúp bên nhận xây dựng đường dẫn đến trust anchor. Root certificate thường không cần đưa vào chain mà máy chủ gửi trong TLS; client phải có trust anchor qua trust store được quản trị độc lập.

Với `TrustedCertificateEntry`, entry chỉ có một chứng chỉ được đánh dấu tin cậy. Ứng dụng phải quyết định chứng chỉ đó được dùng như trust anchor hay được đưa vào quy trình xác minh theo chính sách riêng. Thêm một chứng chỉ bất kỳ vào trust store có thể mở rộng đáng kể ranh giới tin cậy.

## 4. Mật khẩu và cơ chế bảo vệ của JKS

JKS thường sử dụng hai loại mật khẩu:

- **Store password (`storepass`):** dùng khi nạp hoặc lưu kho và kiểm tra tính toàn vẹn của kho theo cơ chế định dạng.
- **Key password (`keypass`):** dùng để bảo vệ hoặc truy cập private key của một key entry cụ thể.

Trong công cụ `keytool`, mật khẩu kho và mật khẩu private key có thể được đặt riêng. Điều này giúp phân tách quyền mở kho với quyền sử dụng một private key, dù nếu cùng một mật khẩu được dùng cho cả hai thì lợi ích phân tách bị mất. `TrustedCertificateEntry` không có private key nên không cần key password riêng.

Trong triển khai JKS truyền thống của Sun/Oracle, tính toàn vẹn kho dựa trên cơ chế kiểm tra mật khẩu dùng SHA-1; private key được bảo vệ bằng cơ chế PBE cũ, thường là `PBEWithMD5AndTripleDES`. Đây là chi tiết triển khai lịch sử, không nên xem như lựa chọn bảo vệ mật mã hiện đại. Các chứng chỉ công khai trong kho không được mã hóa để giữ bí mật. Vì vậy, mật khẩu kho không biến file JKS thành một vùng lưu trữ an toàn trước mọi hình thức truy cập trái phép.

Mật khẩu yếu, bị ghi trong mã nguồn, xuất hiện trong tham số dòng lệnh hoặc được dùng chung giữa nhiều môi trường có thể làm giảm mạnh mức bảo vệ. Người có quyền đọc file và biết mật khẩu thích hợp có thể trích xuất private key. Cần dùng mật khẩu mạnh, phân phối qua secret manager hoặc cơ chế bí mật được kiểm soát, giới hạn quyền đọc file và ghi log việc truy cập.

Đổi store password hoặc key password không tạo key pair mới và không thay thế việc xoay vòng khóa khi khóa bị lộ. Nếu private key đã bị xâm phạm, phải tạo khóa mới, phát hành chứng chỉ mới và thu hồi chứng chỉ cũ theo quy trình PKI.

## 5. Tạo và kiểm tra JKS bằng keytool

`keytool` đi kèm JDK, hỗ trợ quản lý keystore và chứng chỉ. Các ví dụ sau bỏ qua tùy chọn truyền mật khẩu trực tiếp để công cụ có thể yêu cầu nhập mật khẩu tương tác. Trong môi trường tự động hóa, hãy lấy bí mật từ cơ chế quản lý secret phù hợp và tránh ghi chúng vào lịch sử shell hoặc log CI.

### Tạo key pair và JKS

Lệnh sau tạo key pair RSA và một `PrivateKeyEntry` với alias `tls-server`:

```bash
keytool -genkeypair \
  -alias tls-server \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -validity 365 \
  -dname "CN=service.example.internal" \
  -keystore app.jks \
  -storetype JKS
```

Đây là ví dụ tạo khóa cho môi trường phù hợp với RSA. Thuật toán, kích thước khóa, chữ ký và thời hạn phải theo chính sách mật mã hiện hành của tổ chức. Trong môi trường thực tế, tên định danh máy chủ nên được thể hiện trong Subject Alternative Name (SAN) theo yêu cầu của client; không chỉ dựa vào Common Name trong ví dụ rút gọn.

### Liệt kê và xem chi tiết entry

```bash
keytool -list \
  -keystore app.jks \
  -storetype JKS

keytool -list -v \
  -alias tls-server \
  -keystore app.jks \
  -storetype JKS
```

Chế độ `-list -v` hiển thị loại entry, subject, issuer, thời hạn, fingerprint và thông tin chain. Hãy xác minh fingerprint của chứng chỉ nhận được qua một kênh đáng tin cậy trước khi quyết định tin cậy hoặc triển khai.

### Tạo CSR và nhập chứng chỉ CA đã ký

Sau khi tạo key pair, có thể tạo Certificate Signing Request (CSR):

```bash
keytool -certreq \
  -alias tls-server \
  -file server.csr \
  -ext SAN=dns:service.example.internal \
  -keystore app.jks \
  -storetype JKS
```

Gửi CSR qua quy trình cấp chứng chỉ đã được phê duyệt. Khi nhận certificate reply chứa leaf certificate và các intermediate cần thiết, nhập phản hồi vào đúng alias của key entry:

```bash
keytool -importcert \
  -alias tls-server \
  -file server-chain.pem \
  -keystore app.jks \
  -storetype JKS
```

`keytool` đối chiếu public key trong chứng chỉ với private key tương ứng trong entry. Nếu chứng chỉ không khớp key pair hoặc chain không thể được xây dựng theo cấu hình, thao tác có thể thất bại. Không nhập một certificate reply không rõ nguồn gốc.

### Nhập chứng chỉ CA vào trust store

Để tạo một trust store chứa root CA nội bộ đã được xác minh:

```bash
keytool -importcert \
  -alias internal-root-ca \
  -file internal-root-ca.pem \
  -keystore truststore.jks \
  -storetype JKS
```

Trước khi chấp nhận xác nhận tin cậy, kiểm tra fingerprint và nguồn phân phối chứng chỉ. Chứng chỉ được import theo alias mới sẽ trở thành `TrustedCertificateEntry`.

### Xuất chứng chỉ công khai và xóa entry

```bash
keytool -exportcert -rfc \
  -alias tls-server \
  -file tls-server.pem \
  -keystore app.jks \
  -storetype JKS

keytool -delete \
  -alias old-partner-ca \
  -keystore truststore.jks \
  -storetype JKS
```

`-exportcert` xuất chứng chỉ công khai, không xuất private key. `-delete` loại entry khỏi file keystore sau khi lưu thay đổi; trước khi xóa một trust anchor, cần đánh giá dịch vụ và chứng chỉ phụ thuộc vào nó.

## 6. Đọc JKS bằng Java KeyStore API

Java cung cấp API `java.security.KeyStore` để thao tác với các định dạng keystore thông qua provider. Khi biết file có định dạng JKS, chỉ định loại rõ ràng để tránh phụ thuộc vào loại mặc định của JDK.

Ví dụ nạp kho, lấy private key entry và xem certificate chain:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.cert.Certificate;
import java.util.Arrays;

public class ReadJks {
    public static void main(String[] args) throws Exception {
        char[] storePassword = obtainStorePassword();
        char[] keyPassword = null;

        try {
            keyPassword = obtainKeyPassword();
            KeyStore keyStore = KeyStore.getInstance("JKS");
            try (InputStream input = Files.newInputStream(
                    Path.of("app.jks"))) {
                keyStore.load(input, storePassword);
            }

            String alias = "tls-server";
            KeyStore.PasswordProtection protection =
                    new KeyStore.PasswordProtection(keyPassword);
            KeyStore.Entry entry;
            try {
                entry = keyStore.getEntry(alias, protection);
            } finally {
                protection.destroy();
            }

            if (!(entry instanceof KeyStore.PrivateKeyEntry)) {
                throw new IllegalStateException(
                        "Alias does not contain a private key entry");
            }

            KeyStore.PrivateKeyEntry privateKeyEntry =
                    (KeyStore.PrivateKeyEntry) entry;
            Certificate[] chain = privateKeyEntry.getCertificateChain();

            System.out.println("Certificate chain length: " + chain.length);
            for (Certificate certificate : chain) {
                System.out.println(certificate.toString());
            }
        } finally {
            Arrays.fill(storePassword, '\0');
            if (keyPassword != null) {
                Arrays.fill(keyPassword, '\0');
            }
        }
    }

    private static char[] obtainStorePassword() {
        // Lấy từ secret manager hoặc nguồn bí mật được kiểm soát.
        throw new UnsupportedOperationException("Configure secret source");
    }

    private static char[] obtainKeyPassword() {
        // Lấy từ secret manager hoặc nguồn bí mật được kiểm soát.
        throw new UnsupportedOperationException("Configure secret source");
    }
}
```

Các hàm `obtainStorePassword()` và `obtainKeyPassword()` là vị trí tích hợp với secret manager của ứng dụng, không phải nơi hardcode mật khẩu. Xóa nội dung mảng `char[]` sau khi dùng là biện pháp giảm thời gian lưu bí mật trong bộ nhớ; nó không bảo đảm mọi bản sao trong JVM đã được xóa. Cũng cần giới hạn quyền đọc file JKS ở cấp hệ điều hành.

Khi nạp kho, `KeyStore.load(input, storePassword)` kiểm tra và đọc nội dung theo định dạng. Nếu truyền `null` làm password, hành vi kiểm tra tính toàn vẹn phụ thuộc loại keystore/provider; không nên dùng cách này để bỏ qua kiểm tra mật khẩu trong một hệ thống cần bảo vệ. Để tạo một keystore mới trong bộ nhớ, có thể gọi `load(null, password)` rồi thêm entry và lưu bằng `store(output, password)`.

## 7. Dùng JKS trong TLS

Ứng dụng Java thường dùng `KeyManagerFactory` để lấy private key và certificate chain từ identity keystore; dùng `TrustManagerFactory` để nạp các chứng chỉ mà ứng dụng tin cậy. Hai kho có mục đích khác nhau dù đều có thể dùng định dạng JKS.

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

KeyStore identityStore = KeyStore.getInstance("JKS");
try (InputStream input = Files.newInputStream(Path.of("server.jks"))) {
    identityStore.load(input, storePassword);
}

KeyManagerFactory keyManagers = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
keyManagers.init(identityStore, keyPassword);

KeyStore trustStore = KeyStore.getInstance("JKS");
try (InputStream input = Files.newInputStream(Path.of("truststore.jks"))) {
    trustStore.load(input, trustStorePassword);
}

TrustManagerFactory trustManagers = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
trustManagers.init(trustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(
        keyManagers.getKeyManagers(),
        trustManagers.getTrustManagers(),
        new SecureRandom());
```

Đây là đoạn mã trong phần khởi tạo TLS; `storePassword`, `keyPassword` và `trustStorePassword` là các mảng `char[]` lấy từ nguồn bí mật đã được cấu hình. Server thường dùng key managers để chứng minh danh tính của mình; client dùng trust managers để xác minh chứng chỉ peer. Trong mutual TLS, hai phía có thể vừa cung cấp danh tính vừa xác minh danh tính của bên kia.

Không nên tắt kiểm tra chứng chỉ hoặc cài một `TrustManager` chấp nhận mọi chứng chỉ để xử lý lỗi TLS. Cần sửa đúng trust store, certificate chain, hostname hoặc cấu hình chứng chỉ. Trust store tùy chỉnh cũng phải được quản trị và cập nhật khi CA thay đổi hoặc bị distrust.

## 8. JKS và PKCS12

PKCS12 là định dạng trao đổi kho khóa được chuẩn hóa và được hỗ trợ rộng rãi ngoài Java. JKS là định dạng riêng của Java, thường gặp trong các hệ thống cũ.

| Tiêu chí | JKS | PKCS12 |
|---|---|---|
| Nguồn gốc | Định dạng Java | Định dạng chuẩn hóa, được nhiều nền tảng hỗ trợ |
| Tương thích | Phù hợp ứng dụng Java cũ và cấu hình đã dùng JKS | Phù hợp hệ thống Java hiện đại và trao đổi với công cụ khác |
| Loại entry | Triển khai JKS chuẩn chủ yếu hỗ trợ private key và trusted certificate | Hỗ trợ private key, certificate và secret key tùy provider/phiên bản |
| Mặc định Java | Không còn là mặc định từ JDK 9 | Là mặc định từ JDK 9 |
| Bảo vệ mật mã | Cơ chế JKS truyền thống có thuật toán lịch sử | Có cơ chế bảo vệ theo PKCS12; thuật toán cụ thể phụ thuộc provider và cấu hình |
| Khuyến nghị | Duy trì khi cần tương thích với ứng dụng cũ | Ưu tiên xem xét cho hệ thống mới cần tính tương tác |

Không nên kết luận một file an toàn chỉ vì nó là PKCS12. Cần đánh giá thuật toán bảo vệ, mật khẩu, provider, quyền truy cập, cách lưu bí mật và quy trình sao lưu. Tương tự, một ứng dụng cũ có thể vẫn cần JKS vì ràng buộc tương thích; khi đó cần quản lý rủi ro định dạng và lên kế hoạch chuyển đổi.

## 9. Chuyển đổi JKS sang PKCS12

Có thể dùng `keytool -importkeystore` để chuyển các entry từ JKS sang PKCS12:

```bash
keytool -importkeystore \
  -srckeystore legacy.jks \
  -srcstoretype JKS \
  -destkeystore application.p12 \
  -deststoretype PKCS12
```

`keytool` sẽ yêu cầu mật khẩu nguồn và đích theo cấu hình. Sau khi chuyển đổi, kiểm tra số lượng alias, loại entry, certificate chain, fingerprint và khả năng nạp kho bằng đúng JDK/provider mà ứng dụng sẽ chạy. Kiểm tra riêng các private key entry và trusted certificate entry; không giả định mọi thuộc tính hay mật khẩu entry được giữ nguyên giống hệt giữa các định dạng.

Ví dụ kiểm tra kho đích:

```bash
keytool -list -v \
  -keystore application.p12 \
  -storetype PKCS12
```

Chỉ chuyển ứng dụng sang file mới sau khi xác minh nội dung và thử nghiệm kết nối trong môi trường phù hợp. Lưu bản sao lưu được bảo vệ của kho nguồn theo chính sách lưu trữ, rồi xử lý bản cũ theo quy trình thay thế và hủy an toàn. Không xóa kho cũ trước khi xác nhận các hệ thống phụ thuộc đã chuyển đổi thành công.

## 10. Rủi ro và thực hành bảo vệ JKS

JKS là file chứa vật liệu khóa nhạy cảm. Các biện pháp sau cần được kết hợp:

- **Bảo vệ file:** giới hạn quyền đọc/ghi theo tài khoản dịch vụ, tránh đặt keystore trong thư mục public, image/container layer hoặc thư mục source code.
- **Quản lý mật khẩu:** dùng secret manager hoặc hệ thống phân phối bí mật có kiểm soát; không hardcode mật khẩu trong mã nguồn, script, log hay tham số dòng lệnh có thể bị quan sát.
- **Tách môi trường:** dùng kho và key pair riêng cho development, staging và production; không sao chép private key production sang máy cá nhân hoặc môi trường thử nghiệm.
- **Giảm quyền:** chỉ tiến trình và người vận hành được ủy quyền mới có thể đọc file hoặc gọi thao tác sử dụng private key.
- **Sao lưu an toàn:** mã hóa và kiểm soát quyền truy cập bản sao lưu; ghi nhận người thực hiện, thời điểm và mục đích khôi phục; kiểm thử khả năng khôi phục.
- **Kiểm toán:** theo dõi thay đổi file, thao tác keytool, thay đổi alias, thay chứng chỉ và quyền truy cập. Không ghi nội dung private key hoặc mật khẩu vào log.
- **Xoay vòng:** theo dõi thời hạn chứng chỉ và cryptoperiod của key pair; tạo key pair mới khi đến kỳ hoặc khi có dấu hiệu xâm phạm.
- **Thu hồi:** khi private key bị lộ, thu hồi chứng chỉ tương ứng, phát hành chứng chỉ mới và kiểm tra việc thực thi trạng thái thu hồi ở client.
- **Di chuyển khỏi file keystore khi phù hợp:** với khóa có giá trị cao hoặc cần kiểm soát tập trung, cân nhắc KMS/HSM để hạn chế xuất private key và quản lý quyền sử dụng.

JKS lưu private key được bảo vệ trong file, nên người có quyền truy cập và mật khẩu có thể có khả năng trích xuất khóa. HSM có thể giữ khóa trong thiết bị và cung cấp thao tác ký hoặc giải mã mà không xuất private key; đây là khác biệt kiến trúc quan trọng khi yêu cầu bảo vệ cao. Java có thể tích hợp với HSM qua provider phù hợp, nhưng cấu hình và khả năng hỗ trợ phụ thuộc nhà cung cấp.

## 11. Lỗi thường gặp khi vận hành

| Lỗi hoặc triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `Keystore was tampered with, or password was incorrect` | Sai store password, file hỏng hoặc kiểm tra toàn vẹn thất bại | Xác nhận đúng file, loại kho và mật khẩu; kiểm tra bản sao lưu nếu file hỏng |
| `UnrecoverableKeyException` | Sai key password hoặc không giải mã được private key entry | Xác nhận alias và key password của entry |
| `Invalid keystore format` | Đọc file bằng sai loại keystore hoặc file không phải keystore hợp lệ | Chỉ định `JKS`/`PKCS12` chính xác và kiểm tra nguồn file |
| `Alias ... does not exist` | Sai alias hoặc entry chưa được import | Liệt kê alias bằng `keytool -list` và kiểm tra quy trình import |
| `trustedCertEntry` được dùng như private key | Entry chỉ chứa chứng chỉ công khai | Dùng đúng `PrivateKeyEntry` trong identity keystore |
| `Certificate reply does not contain public key for ...` | Certificate reply không khớp key pair của alias | Kiểm tra CSR, alias và public key trong chứng chỉ CA trả về |
| TLS báo không tin cậy issuer | Thiếu intermediate hoặc trust anchor chưa được cấu hình | Kiểm tra chain, trust store và nguồn root CA |
| TLS báo hostname mismatch | SAN không khớp hostname đang kết nối | Cấp lại chứng chỉ với SAN phù hợp và kiểm tra tên đích |

Khi xử lý lỗi, không nên tắt xác minh TLS, nhập tùy tiện một root certificate hoặc đổi toàn bộ trust store để làm kết nối hoạt động. Hãy xác định đúng alias, loại entry, certificate chain, mật khẩu và trust anchor liên quan.

## 12. Checklist triển khai

- [ ] Xác định rõ JKS được dùng làm identity keystore hay trust store.
- [ ] Chỉ định rõ `JKS` khi nạp file JKS, không dựa vào phần mở rộng hoặc loại mặc định của JDK.
- [ ] Kiểm tra alias, loại entry, private key và certificate chain trước khi triển khai.
- [ ] Dùng mật khẩu mạnh, phân phối qua secret manager và tránh truyền mật khẩu trong dòng lệnh.
- [ ] Giới hạn quyền đọc/ghi file và bảo vệ bản sao lưu.
- [ ] Không lưu private key production trong source code, repository hoặc image không được bảo vệ.
- [ ] Kiểm tra SAN, thời hạn, issuer, fingerprint và mục đích sử dụng chứng chỉ.
- [ ] Có quy trình cấp CSR, nhập certificate reply, gia hạn, thu hồi và thay key pair.
- [ ] Đánh giá chuyển đổi sang PKCS12 hoặc KMS/HSM theo nhu cầu tương thích và mức bảo vệ.
- [ ] Kiểm thử TLS bằng đúng JDK, provider, trust store và cấu hình production dự kiến.

JKS giúp ứng dụng Java quản lý private key và chứng chỉ theo alias thông qua API thống nhất. Để sử dụng an toàn, cần hiểu loại entry, cơ chế mật khẩu, giới hạn của định dạng và vai trò riêng của identity keystore với trust store; đồng thời bảo vệ file, quản lý secret, kiểm toán và thay khóa theo vòng đời đã xác định.
