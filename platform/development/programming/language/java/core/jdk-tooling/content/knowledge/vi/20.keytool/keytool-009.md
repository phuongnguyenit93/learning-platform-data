# Keystore format trong Java

**Keystore format** là định dạng lưu trữ các mục mật mã như private key, certificate chain, trusted certificate và, tùy provider, secret key. Công cụ `keytool` và API `java.security.KeyStore` có thể đọc, tạo, liệt kê, nhập, xuất và chuyển đổi keystore giữa các định dạng được JDK hoặc security provider hỗ trợ.

Khi làm việc với TLS, chữ ký số hoặc xác thực ứng dụng, cần chọn định dạng phù hợp với runtime và hệ thống cần tích hợp. Trong Java hiện đại, **PKCS12 là định dạng mặc định trong cấu hình JDK tiêu chuẩn từ JDK 9**; JKS vẫn gặp trong hệ thống cũ, còn JCEKS thường xuất hiện trong ứng dụng Java cần lưu secret key theo provider tương ứng.

Keystore là một container. Phần mở rộng tên file như `.jks`, `.p12` hoặc `.pfx` chỉ là quy ước; nó không chứng minh nội dung thực tế thuộc định dạng nào. Khi thao tác, hãy chỉ định rõ `-storetype` và kiểm tra bằng `keytool -list`.

## 1. Keystore lưu những loại entry nào?

Một keystore có thể chứa nhiều entry được nhận diện bằng alias. Loại entry phụ thuộc vào định dạng và provider.

| Entry type | Nội dung | Mục đích |
|---|---|---|
| `PrivateKeyEntry` | Private key cùng certificate chain tương ứng | TLS server/client authentication, ký số |
| `TrustedCertificateEntry` | Một trusted certificate, không có private key | Lưu CA hoặc certificate được tin cậy |
| `SecretKeyEntry` | Symmetric secret key | Mã hóa/giải mã dữ liệu đối xứng; phụ thuộc định dạng/provider |

Ví dụ một keystore TLS server có thể chứa alias `server` với private key và certificate chain. Một truststore có thể chứa alias `company-root-ca` với certificate của CA nội bộ.

Alias là tên dùng để truy cập entry. Một file có thể chứa nhiều alias và nhiều loại entry. Khi kiểm tra, hãy xác nhận alias, loại entry, certificate subject/issuer, thời hạn và fingerprint thay vì chỉ kiểm tra file có tồn tại.

## 2. Keystore và truststore khác nhau như thế nào?

**Keystore** thường lưu danh tính mật mã của chính ứng dụng, ví dụ private key cùng certificate chain của máy chủ.

**Truststore** thường lưu các certificate mà ứng dụng tin cậy, ví dụ root CA hoặc intermediate CA dùng để xác minh certificate của máy chủ đối tác.

Đây là vai trò sử dụng, không phải hai định dạng file khác nhau. Cả keystore và truststore đều có thể là JKS, PKCS12 hoặc định dạng khác được provider hỗ trợ.

| Thành phần | Nội dung điển hình | Dùng khi |
|---|---|---|
| Server keystore | Private key server + certificate chain | Server chứng minh danh tính với client |
| Client keystore | Private key client + certificate chain | Client xác thực bằng mutual TLS |
| Truststore | Trusted CA/certificate entries | Xác minh certificate phía bên kia |
| Application secret store | Secret key entries | Lưu khóa đối xứng nếu provider/format hỗ trợ |

Không đưa private key vào truststore chỉ vì cả hai đều chứa dữ liệu certificate. Khi triển khai, cần bảo vệ private key nghiêm ngặt hơn certificate công khai.

## 3. Các định dạng phổ biến

### 3.1. JKS

**JKS (Java KeyStore)** là định dạng keystore truyền thống gắn với hệ sinh thái Java. Nó thường được dùng trong ứng dụng Java cũ và có thể chứa private key cùng certificate chain hoặc trusted certificate entry.

Đặc điểm:

- Là định dạng Java-specific, không phải container tiêu chuẩn liên thông rộng như PKCS12.
- Thường gặp trong các file có phần mở rộng `.jks`.
- Có thể cần chuyển đổi khi tích hợp với hệ thống hoặc công cụ ngoài Java.
- Không nên giả định provider JKS hỗ trợ mọi loại entry, đặc biệt là secret key entry.

JKS từng là loại mặc định của Java trước JDK 9. Các hệ thống cũ có thể vẫn yêu cầu JKS, do đó không nên đổi định dạng chỉ dựa trên phần mở rộng file hoặc phiên bản JDK.

### 3.2. PKCS12

**PKCS12** là định dạng container tiêu chuẩn được mô tả trong RFC 7292. Nó thường được dùng để trao đổi private key và certificate chain giữa Java, web server, hệ điều hành và công cụ quản trị certificate.

Đặc điểm:

- Có khả năng tương tác tốt hơn giữa các nền tảng và công cụ.
- Thường dùng phần mở rộng `.p12` hoặc `.pfx`.
- Là loại mặc định của JDK từ Java 9 trong cấu hình tiêu chuẩn, theo security property `keystore.type`.
- Phù hợp cho nhiều tình huống TLS và lưu trữ certificate/private key.
- Khả năng lưu secret key và chi tiết bảo vệ password phụ thuộc implementation/provider và phiên bản JDK.

PKCS12 là lựa chọn hợp lý cho dự án Java mới nếu không có yêu cầu tương thích đặc biệt. Khi tích hợp hệ thống khác, vẫn cần kiểm tra thuật toán mã hóa, MAC, certificate chain và khả năng hỗ trợ của phần mềm nhận file.

### 3.3. JCEKS

**JCEKS** là định dạng keystore Java-specific được cung cấp bởi JCE provider của JDK. Nó hỗ trợ lưu secret key entry, ngoài các loại entry phù hợp khác.

Đặc điểm:

- Thường gặp trong ứng dụng Java cũ có lưu symmetric secret key.
- Không có tính liên thông rộng như PKCS12.
- Phụ thuộc provider hỗ trợ loại `JCEKS`.
- Cần đánh giá khả năng tương thích trước khi dùng trong hệ thống đa nền tảng.

Nếu ứng dụng dùng JCEKS để lưu secret key, không được chuyển sang định dạng khác rồi giả định entry sẽ được bảo toàn. Hãy thử import/export trên đúng JDK/provider và xác minh từng alias cùng loại key sau chuyển đổi.

### 3.4. So sánh nhanh

| Tiêu chí | JKS | PKCS12 | JCEKS |
|---|---|---|---|
| Nguồn gốc | Java-specific | Tiêu chuẩn PKCS #12 | Java-specific |
| Mức liên thông | Chủ yếu hệ Java | Rộng hơn giữa các nền tảng | Chủ yếu hệ Java |
| Private key + certificate chain | Có | Có | Có |
| Trusted certificate | Có | Có | Có |
| Secret key entry | Provider JKS tiêu chuẩn không hỗ trợ như JCEKS | Phụ thuộc provider/JDK | Có |
| Mặc định JDK hiện đại | Không | Có từ JDK 9 trong cấu hình tiêu chuẩn | Không |
| Khuyến nghị chung | Duy trì khi tương thích cũ yêu cầu | Lựa chọn mặc định cho phần lớn trường hợp mới | Chỉ dùng khi có yêu cầu cụ thể |

Không chọn định dạng chỉ vì phần mở rộng file. Hãy kiểm tra loại keystore thực tế, provider, entry types và yêu cầu của ứng dụng.

## 4. Default keystore type trong JDK

Từ JDK 9, default keystore type trong cấu hình bảo mật tiêu chuẩn đã chuyển từ JKS sang PKCS12. Giá trị mặc định được điều khiển bởi security property `keystore.type`.

Trong Java có thể xem giá trị mặc định:

```java
import java.security.KeyStore;

public class DefaultKeystoreType {
    public static void main(String[] args) {
        System.out.println(KeyStore.getDefaultType());
    }
}
```

Biên dịch và chạy trên JDK 17+ với cấu hình mặc định:

```sh
javac DefaultKeystoreType.java
java DefaultKeystoreType
```

Stdout trong JDK tiêu chuẩn có default property PKCS12:

```text
pkcs12
```

Giá trị có thể thay đổi nếu security configuration của JDK hoặc provider được tùy chỉnh. Vì vậy, không nên suy ra format chỉ từ phiên bản Java. Trong script triển khai, chỉ định tường minh `-storetype` để lệnh có thể tái lập.

`KeyStore.getDefaultType()` chỉ trả về default type của runtime. Nó không chứng minh file hiện có trên đĩa thực sự dùng loại đó.

## 5. Tạo PKCS12 keystore bằng keytool

Ví dụ tạo key pair RSA và certificate tự ký cho môi trường thử nghiệm:

```sh
keytool -genkeypair -alias app-server -keyalg RSA -keysize 3072 -validity 365 -dname "CN=localhost, OU=Development, O=Example, L=HCMC, C=VN" -ext "SAN=dns:localhost,ip:127.0.0.1" -keystore app-server.p12 -storetype PKCS12
```

Các tham số:

- `-genkeypair`: tạo public/private key pair và certificate.
- `-alias app-server`: tên entry trong keystore.
- `-keyalg RSA`: thuật toán tạo key pair.
- `-keysize 3072`: kích thước RSA key.
- `-validity 365`: thời hạn certificate tính theo ngày.
- `-dname`: distinguished name của subject.
- `-ext SAN=...`: thêm Subject Alternative Name cho hostname/IP trong ví dụ.
- `-keystore app-server.p12`: file đầu ra.
- `-storetype PKCS12`: chọn định dạng PKCS12.

Nếu không truyền password trên command line, `keytool` sẽ yêu cầu nhập tương tác. Đây là cách phù hợp hơn cho thao tác thủ công vì tránh để secret lộ trong lịch sử shell hoặc danh sách tiến trình.

Certificate tự ký phù hợp cho phát triển và kiểm thử có kiểm soát. Đối với production TLS, hãy tạo CSR và xin certificate từ CA phù hợp; không dùng certificate tự ký như một giải pháp tin cậy mặc định cho client bên ngoài.

## 6. Liệt kê và kiểm tra keystore

Liệt kê alias và loại entry:

```sh
keytool -list -keystore app-server.p12 -storetype PKCS12
```

Xem chi tiết certificate, subject, issuer, serial number, thời hạn và fingerprint:

```sh
keytool -list -v -keystore app-server.p12 -storetype PKCS12
```

Tùy chọn:

- `-list`: liệt kê entry.
- `-v`: hiển thị thông tin chi tiết.
- `-keystore`: chỉ định file.
- `-storetype`: chỉ định định dạng cần đọc.

Khi kiểm tra trước khi triển khai, xác nhận:

1. File được đọc bằng đúng store type.
2. Alias cần thiết tồn tại.
3. Entry là `PrivateKeyEntry` hay `trustedCertEntry` như mong đợi.
4. Certificate subject và issuer đúng.
5. Certificate còn hạn và có chain phù hợp.
6. Fingerprint khớp với giá trị đã xác minh qua kênh tin cậy.

Không chia sẻ password hoặc private key trong log, ảnh chụp màn hình hay tài liệu hướng dẫn.

## 7. Xuất certificate ra PEM

Có thể xuất certificate công khai từ một alias:

```sh
keytool -exportcert -alias app-server -keystore app-server.p12 -storetype PKCS12 -rfc -file app-server-cert.pem
```

`-rfc` yêu cầu xuất theo định dạng PEM/Base64 có header và footer. File này chứa certificate công khai, không chứa private key.

Phân biệt:

- **PKCS12** là container có thể chứa private key và certificate.
- **PEM** là cách biểu diễn văn bản Base64 cho certificate, public key hoặc private key theo cấu trúc tương ứng.
- **DER** là dạng mã hóa nhị phân ASN.1 của certificate/key structure.

Không đổi đuôi `.p12` thành `.pem` để chuyển định dạng. Cần dùng công cụ xuất/chuyển đổi phù hợp và xác minh nội dung đầu ra.

## 8. Tạo truststore và import CA certificate

Để ứng dụng tin cậy một CA, import certificate CA vào truststore:

```sh
keytool -importcert -alias company-root-ca -file company-root-ca.pem -keystore truststore.p12 -storetype PKCS12
```

`keytool` sẽ yêu cầu xác nhận certificate khi import tương tác. Trước khi chấp nhận, hãy xác minh fingerprint của CA qua một kênh độc lập đáng tin cậy, chẳng hạn tài liệu PKI chính thức hoặc quản trị viên hệ thống.

Sau khi import, kiểm tra:

```sh
keytool -list -v -keystore truststore.p12 -storetype PKCS12
```

Entry được import theo alias `company-root-ca` phải là trusted certificate entry. Truststore có thể chứa nhiều CA/certificate nếu ứng dụng cần xác minh nhiều hệ thống.

Không import certificate chỉ vì nó được gửi kèm trong email hoặc tải từ một endpoint chưa xác minh. Import certificate đồng nghĩa với việc cấu hình một điểm tin cậy; thao tác này có ảnh hưởng trực tiếp đến xác thực TLS.

## 9. Tạo certificate được CA ký

Trong production, luồng phổ biến là tạo private key trong keystore, xuất CSR, gửi CA ký rồi import certificate reply cùng chain.

### Bước 1: Tạo key pair và keystore

```sh
keytool -genkeypair -alias app-server -keyalg RSA -keysize 3072 -dname "CN=service.example.com" -keystore app-server.p12 -storetype PKCS12
```

### Bước 2: Tạo CSR

```sh
keytool -certreq -alias app-server -keystore app-server.p12 -storetype PKCS12 -file app-server.csr
```

Gửi CSR đến CA theo quy trình cấp phát certificate. CSR chứa public key và thông tin yêu cầu; nó không chứa private key.

### Bước 3: Import CA certificate/chain nếu cần

Nếu CA cung cấp root/intermediate certificate riêng, xác minh fingerprint rồi import các CA certificate vào đúng keystore/truststore theo quy trình của tổ chức. Thứ tự và cách cài chain phụ thuộc CA và cấu trúc certificate reply.

### Bước 4: Import certificate reply

```sh
keytool -importcert -alias app-server -file app-server-chain.pem -keystore app-server.p12 -storetype PKCS12
```

Khi alias đã chứa private key, `keytool` dùng certificate reply để gắn certificate và chain với private key tương ứng. Certificate phải khớp public key trong CSR; nếu không, quá trình import sẽ thất bại.

### Bước 5: Kiểm tra chain

```sh
keytool -list -v -alias app-server -keystore app-server.p12 -storetype PKCS12
```

Kiểm tra subject, issuer, thời hạn và certificate chain. Đảm bảo SAN có hostname/IP mà client thực sự sử dụng. Common Name một mình không thay thế SAN trong cấu hình TLS hiện đại.

## 10. Chuyển đổi JKS sang PKCS12

Khi nâng cấp ứng dụng Java cũ, có thể cần chuyển JKS sang PKCS12:

```sh
keytool -importkeystore -srckeystore legacy.jks -srcstoretype JKS -destkeystore modern.p12 -deststoretype PKCS12
```

Công cụ sẽ yêu cầu password của keystore nguồn và đích nếu chưa được cung cấp. Không cần ghi password trực tiếp vào lệnh tương tác.

Ý nghĩa:

- `-importkeystore`: sao chép entry từ một keystore sang keystore khác.
- `-srckeystore`: file nguồn.
- `-srcstoretype JKS`: định dạng nguồn.
- `-destkeystore`: file đích.
- `-deststoretype PKCS12`: định dạng đích.

Có thể chọn một alias cụ thể bằng `-srcalias` và đặt tên alias đích bằng `-destalias`. Nếu không chỉ định, `keytool` xử lý các entry theo quy tắc import của lệnh.

Sau khi chuyển đổi, kiểm tra cả hai file:

```sh
keytool -list -v -keystore legacy.jks -storetype JKS
keytool -list -v -keystore modern.p12 -storetype PKCS12
```

Đối chiếu số lượng alias và tên alias, loại entry, subject/issuer, thời hạn certificate, fingerprint, certificate chain và khả năng ứng dụng đọc private key.

Không xóa file nguồn ngay sau khi import. Giữ bản backup được bảo vệ cho đến khi ứng dụng đã được cấu hình và kiểm thử thành công với file mới.

## 11. Password của keystore và password của key

Các tùy chọn thường gặp:

- `-storepass`: password dùng để mở/bảo vệ keystore theo implementation.
- `-keypass`: password bảo vệ private key entry khi định dạng/provider hỗ trợ password riêng.
- `-srcstorepass`: password của keystore nguồn khi chuyển đổi.
- `-deststorepass`: password của keystore đích khi chuyển đổi.

Hành vi password phụ thuộc định dạng và provider. JKS có thể hỗ trợ password của keystore và private key riêng. Với implementation PKCS12 phổ biến của JDK, private key thường được bảo vệ bằng password của PKCS12 store; không nên giả định `-keypass` có thể khác `-storepass` như với JKS. Hãy kiểm tra tài liệu `keytool` của JDK/provider cụ thể.

Nguyên tắc bảo vệ:

- Dùng password dài, ngẫu nhiên và duy nhất.
- Không commit password vào source control.
- Không truyền secret trực tiếp trên command line nếu có thể tránh.
- Dùng secret manager hoặc cơ chế cấp phát secret được tổ chức phê duyệt.
- Hạn chế quyền đọc file keystore ở mức hệ điều hành.
- Không gửi private key hoặc file keystore chứa private key qua kênh không bảo mật.
- Có quy trình backup, rotation và thu hồi certificate.

Password của keystore không thay thế kiểm soát truy cập file. Người có quyền đọc file có thể sao chép container và thử tấn công offline; vì vậy phải bảo vệ cả file lẫn password.

## 12. Dùng KeyStore API trong Java

Java cung cấp API `java.security.KeyStore` để đọc và thao tác với keystore. Nên chỉ định type rõ ràng khi biết định dạng:

```java
KeyStore keyStore = KeyStore.getInstance("PKCS12");
```

Đọc file:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;

char[] password = obtainPasswordSecurely();

KeyStore keyStore = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(Path.of("app-server.p12"))) {
    keyStore.load(input, password);
}
```

`KeyStore.getInstance("PKCS12")` yêu cầu provider có hỗ trợ type PKCS12. `load` đọc container và xác thực password theo implementation. Nếu file không đúng định dạng, password sai hoặc dữ liệu bị hỏng, thao tác có thể ném exception.

Các method thường dùng:

| Method | Công dụng |
|---|---|
| `KeyStore.getInstance(type)` | Tạo đối tượng cho loại keystore |
| `load(input, password)` | Đọc keystore |
| `store(output, password)` | Ghi keystore |
| `aliases()` | Liệt kê alias |
| `containsAlias(alias)` | Kiểm tra alias |
| `getKey(alias, password)` | Lấy key nếu password và quyền phù hợp |
| `getCertificate(alias)` | Lấy certificate của entry |
| `getCertificateChain(alias)` | Lấy certificate chain |
| `isKeyEntry(alias)` | Kiểm tra entry chứa key |
| `isCertificateEntry(alias)` | Kiểm tra trusted certificate entry |
| `setCertificateEntry(alias, cert)` | Thêm trusted certificate |
| `deleteEntry(alias)` | Xóa entry |

Không log kết quả `getKey()` hoặc nội dung private key. Khi thao tác với password dạng `char[]`, xóa nội dung mảng sau khi sử dụng nếu vòng đời ứng dụng cho phép.

## 13. Chương trình Java 17+ liệt kê alias an toàn

Ví dụ sau đọc một keystore theo type do người dùng chỉ định. Password được nhập qua terminal bằng `Console.readPassword`, không truyền trong đối số dòng lệnh.

Tạo file `KeystoreInspector.java`:

```java
import java.io.Console;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.cert.Certificate;
import java.util.Arrays;
import java.util.Enumeration;

public class KeystoreInspector {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                "Usage: java KeystoreInspector <file> <type>");
            return;
        }

        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException(
                "Run this program from an interactive terminal.");
        }

        char[] password = console.readPassword("Keystore password: ");
        if (password == null) {
            throw new IllegalStateException("No password was entered.");
        }

        try {
            KeyStore keyStore = KeyStore.getInstance(args[1]);

            try (InputStream input =
                     Files.newInputStream(Path.of(args[0]))) {
                keyStore.load(input, password);
            }

            System.out.println("Type: " + keyStore.getType());

            Enumeration<String> aliases = keyStore.aliases();
            while (aliases.hasMoreElements()) {
                String alias = aliases.nextElement();

                String entryType = keyStore.isKeyEntry(alias)
                    ? "key entry"
                    : keyStore.isCertificateEntry(alias)
                        ? "trusted certificate entry"
                        : "other";

                System.out.println(alias + " (" + entryType + ")");

                Certificate certificate = keyStore.getCertificate(alias);
                if (certificate != null) {
                    System.out.println(
                        "  Certificate type: " + certificate.getType());
                }
            }
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

Biên dịch:

```sh
javac KeystoreInspector.java
```

Chạy với file PKCS12:

```sh
java KeystoreInspector app-server.p12 PKCS12
```

Chạy với file JKS:

```sh
java KeystoreInspector legacy.jks JKS
```

Kết quả liệt kê alias và loại entry có trong file. Nội dung cụ thể phụ thuộc keystore được đọc. Chương trình cần chạy trong terminal tương tác vì `System.console()` có thể trả về `null` khi chạy trong IDE hoặc khi stdin không phải console.

Ví dụ này chỉ hiển thị metadata entry và loại certificate; nó không xuất private key hoặc password ra stdout.

## 14. Chọn provider và kiểm tra khả năng hỗ trợ

`KeyStore.getInstance(type)` tìm provider đăng ký có hỗ trợ type được yêu cầu. Một type có thể tồn tại trong JDK chuẩn hoặc được cung cấp bởi provider bổ sung.

Có thể xem provider của một instance:

```java
import java.security.KeyStore;

KeyStore store = KeyStore.getInstance("PKCS12");
System.out.println(store.getProvider().getName());
```

Provider quyết định nhiều chi tiết triển khai như loại entry được hỗ trợ, thuật toán bảo vệ, xử lý password và tương thích với file được tạo bởi implementation khác.

Khi ứng dụng chạy trên nhiều JDK hoặc provider:

1. Xác nhận type có sẵn trong môi trường đích.
2. Kiểm tra provider thực sự được chọn.
3. Kiểm tra khả năng đọc file được tạo bởi hệ thống nguồn.
4. Thử load, liệt kê alias và lấy certificate.
5. Thử thao tác thực tế cần dùng, chẳng hạn lấy private key hoặc xác minh chain.
6. Kiểm tra lại sau khi nâng JDK/provider.

Không chỉ dựa vào việc `KeyStore.getInstance("PKCS12")` thành công để kết luận mọi tính năng của file sẽ tương thích.

## 15. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Keystore was tampered with, or password was incorrect` | Password sai, file hỏng hoặc integrity check thất bại | Kiểm tra password, bản backup và đúng store type |
| `Unrecognized keystore format` | Chọn sai `-storetype` hoặc file không phải keystore hợp lệ | Xác định format thực tế và chỉ định đúng type |
| `Alias does not exist` | Alias sai hoặc entry chưa được import | Dùng `keytool -list` để xem alias chính xác |
| `Cannot recover key` | Password key không đúng hoặc provider không hỗ trợ cách bảo vệ đó | Kiểm tra key password và đặc tính provider/format |
| Certificate reply không chứa public key tương ứng | Certificate reply không khớp key pair của alias | Tạo CSR từ đúng alias và yêu cầu CA cấp lại |
| Import thành công nhưng ứng dụng không tin certificate | Import nhầm leaf certificate/CA, thiếu chain hoặc ứng dụng dùng truststore khác | Kiểm tra trust chain và cấu hình truststore thực tế |
| Chuyển JKS sang PKCS12 nhưng thiếu entry | Loại entry hoặc provider không tương thích | Đối chiếu alias/entry type và chuyển bằng provider hỗ trợ |
| Ứng dụng cũ không đọc được PKCS12 | Runtime/provider cũ hoặc cấu hình chỉ chấp nhận JKS | Nâng runtime hoặc duy trì định dạng tương thích theo yêu cầu |
| Certificate đã hết hạn | Certificate hết thời hạn hoặc clock hệ thống sai | Kiểm tra ngày giờ, xin/gia hạn certificate |
| TLS báo hostname mismatch | SAN không chứa hostname/IP client sử dụng | Cấp lại certificate có SAN phù hợp |
| `NoSuchAlgorithmException` cho type | Provider không đăng ký type yêu cầu | Kiểm tra provider và security configuration |
| `System.console()` trả về `null` | Chương trình chạy không có interactive console | Chạy trong terminal hoặc thiết kế cơ chế nhập secret phù hợp |

Khi điều tra lỗi, kiểm tra lần lượt: file có tồn tại và đọc được không, type có đúng không, password có đúng không, alias có tồn tại không, provider có hỗ trợ entry type không và certificate chain có đáp ứng mục đích sử dụng không.

## 16. Lưu ý bảo mật khi vận hành keystore

- Không lưu private key trong repository hoặc thư mục chia sẻ công khai.
- Giới hạn quyền truy cập file theo tài khoản dịch vụ cần sử dụng.
- Lưu password trong secret manager hoặc hệ thống quản lý secret được phê duyệt.
- Xác minh fingerprint CA qua kênh độc lập trước khi import.
- Theo dõi ngày hết hạn và lập kế hoạch gia hạn certificate.
- Thu hồi và thay key khi nghi ngờ private key bị lộ.
- Backup keystore theo chính sách bảo mật, kiểm soát quyền đọc backup.
- Không dùng cùng một private key cho nhiều môi trường nếu chính sách yêu cầu tách biệt.
- Kiểm tra certificate chain và hostname khi cấu hình TLS.
- Thử quy trình restore backup để bảo đảm có thể khôi phục khi sự cố.

Một truststore sai có thể làm ứng dụng tin cậy CA không mong muốn; một keystore bị lộ có thể làm lộ danh tính private key của dịch vụ. Hãy coi cả hai là tài sản bảo mật quan trọng.

## 17. Quy trình chọn và chuyển keystore format

1. Xác định loại dữ liệu cần lưu: private key, certificate, trusted certificate hay secret key.
2. Xác định JDK/provider và các hệ thống khác cần đọc file.
3. Ưu tiên PKCS12 cho trường hợp mới nếu không có yêu cầu tương thích khác.
4. Giữ JKS nếu ứng dụng cũ hoặc phần mềm đích chỉ hỗ trợ JKS.
5. Dùng JCEKS khi có yêu cầu cụ thể về secret key và provider hỗ trợ.
6. Backup file nguồn trước khi chuyển đổi.
7. Chuyển bằng `keytool -importkeystore` với source/destination type tường minh.
8. Đối chiếu alias, entry type, certificate chain và fingerprint.
9. Cấu hình ứng dụng dùng file và type mới.
10. Chạy TLS/signing/integration test trên môi trường tương đương production.
11. Chỉ ngừng dùng file cũ sau khi xác nhận migration hoàn tất và backup đáp ứng chính sách.

Nếu cần tương tác với hệ thống không phải Java, kiểm tra định dạng và thuật toán bảo vệ mà hệ thống đó hỗ trợ. Một file PKCS12 tiêu chuẩn vẫn có thể gặp khác biệt implementation về cipher, MAC hoặc password encoding.

## 18. Checklist

- [ ] Đã xác định định dạng thực tế thay vì chỉ dựa vào phần mở rộng.
- [ ] Đã chọn `-storetype` rõ ràng trong script.
- [ ] Đã phân biệt keystore với truststore theo vai trò sử dụng.
- [ ] Đã kiểm tra alias và loại entry.
- [ ] Đã xác minh subject, issuer, SAN, thời hạn và fingerprint.
- [ ] Đã chọn format phù hợp với JDK/provider và hệ thống tích hợp.
- [ ] Đã kiểm tra khả năng hỗ trợ secret key nếu ứng dụng cần.
- [ ] Đã không đưa password/private key vào source control hoặc log.
- [ ] Đã xác minh CA fingerprint trước khi import certificate.
- [ ] Đã backup và đối chiếu entry sau khi chuyển đổi.
- [ ] Đã kiểm thử ứng dụng với keystore/truststore mới.
- [ ] Đã có quy trình gia hạn, rotation, thu hồi và khôi phục.

## 19. Tài liệu tham khảo

- Oracle JDK 21 Tool Reference — The `keytool` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html
- Java Security Standard Algorithm Names — KeyStore Types: https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html
- Java API — `java.security.KeyStore`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html
- RFC 7292 — PKCS #12: Personal Information Exchange Syntax v1.1: https://www.rfc-editor.org/rfc/rfc7292

Keystore format quyết định cách Java lưu trữ và bảo vệ key/certificate entry. Với phần lớn ứng dụng mới, PKCS12 là lựa chọn mặc định hợp lý; JKS và JCEKS vẫn có chỗ đứng khi cần tương thích hoặc hỗ trợ entry cụ thể. Luôn xác minh format, provider, alias, certificate chain và khả năng đọc thực tế trước khi triển khai hoặc chuyển đổi.