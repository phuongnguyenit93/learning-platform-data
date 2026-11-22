# Alias trong keytool

Trong **keytool**, một **alias** là tên dùng để nhận diện một entry bên trong keystore. Mỗi entry chứa khóa, chứng chỉ hoặc thông tin xác thực khác; các lệnh keytool dùng alias để biết entry nào cần tạo, liệt kê, xuất, nhập, đổi tên hoặc xóa.

Ví dụ, keystore có thể chứa entry tên \`app-signing\` cho khóa riêng dùng ký ứng dụng, \`internal-root-ca\` cho chứng chỉ CA nội bộ và \`database-client\` cho chứng chỉ client TLS. Alias giúp con người và công cụ chọn đúng entry mà không phải tìm bằng nội dung chứng chỉ mỗi lần.

Alias là nhãn định danh trong phạm vi một keystore. Nó không phải mật khẩu, không phải khóa mật mã và cũng không tự xác định danh tính trong chứng chỉ X.509. Danh tính trong chứng chỉ được thể hiện bằng các trường như Subject, Subject Alternative Name và public key; alias chỉ giúp tìm entry lưu trong keystore.

## 1. Alias, keystore và entry

Ba khái niệm này có quan hệ trực tiếp:

- **Keystore:** vùng lưu trữ các entry mật mã, thường chứa khóa và chứng chỉ. Keystore có định dạng như PKCS12 hoặc JKS.
- **Entry:** một mục được lưu trong keystore. Entry có thể chứa private key, secret key hoặc trusted certificate.
- **Alias:** tên dùng để truy cập một entry cụ thể.

Có thể hình dung:

~~~text
app-signing.p12
├── app-signing       -> PrivateKeyEntry
├── internal-root-ca  -> TrustedCertificateEntry
└── session-aes       -> SecretKeyEntry
~~~

Mỗi alias xác định một entry trong keystore đó. Hai keystore khác nhau có thể dùng cùng một alias mà không xung đột, vì alias không phải tên toàn cục.

### Alias không phải Subject của chứng chỉ

Ví dụ entry có alias \`app-signing\`, nhưng chứng chỉ bên trong có Subject:

~~~text
CN=Example Application, OU=Engineering, O=Example, C=VN
~~~

Đổi alias thành \`release-key-2026\` không sửa Subject, SAN, serial number, public key hay chữ ký của chứng chỉ. Thao tác đổi alias chỉ đổi tên entry trong keystore.

Điều này quan trọng khi tích hợp với ứng dụng: cấu hình TLS hoặc công cụ ký có thể tham chiếu alias, trong khi việc xác thực chứng chỉ vẫn dựa trên nội dung chứng chỉ và chuỗi tin cậy.

## 2. Những loại entry có thể được nhận diện bằng alias

KeyStore hỗ trợ nhiều loại entry. Ba loại thường gặp nhất là:

| Loại entry | Nội dung | Trường hợp sử dụng |
|---|---|---|
| \`PrivateKeyEntry\` | Private key và certificate chain tương ứng | TLS server/client, ký JAR, ký code |
| \`TrustedCertificateEntry\` | Một public certificate được tin cậy | Trust anchor, CA certificate, chứng chỉ đối tác |
| \`SecretKeyEntry\` | Symmetric secret key | Mã hóa/giải mã dữ liệu |

Các lệnh keytool tạo hoặc nhập entry với alias:

- \`-genkeypair\` tạo cặp public/private key và lưu trong key entry, kèm chứng chỉ tự ký ban đầu nếu không chỉ định signer.
- \`-genseckey\` tạo secret key và lưu trong SecretKeyEntry.
- \`-importcert\` có thể tạo trusted certificate entry hoặc nhập certificate reply cho một key entry đã tồn tại.
- \`-importpass\` nhập passphrase vào một SecretKeyEntry.

Một alias có thể trỏ đến entry chứa private key hoặc secret key; vì vậy không nên giả định mọi alias đều đại diện cho một chứng chỉ tin cậy.

### Phân biệt key entry và trusted certificate entry

**Key entry** chứa vật liệu khóa bí mật. Với PrivateKeyEntry, entry còn có certificate chain để người khác xác minh public key tương ứng. Với SecretKeyEntry, entry chứa khóa đối xứng.

**Trusted certificate entry** chỉ chứa chứng chỉ public được chủ keystore chấp nhận là tin cậy. Nó không chứa private key của chủ thể chứng chỉ.

Sự phân biệt này ảnh hưởng trực tiếp đến \`-importcert\`: nếu alias chưa tồn tại, keytool có thể tạo trusted certificate entry; nếu alias đã trỏ đến key entry, keytool hiểu dữ liệu nhập vào là certificate reply cho public key của entry đó.

## 3. Quy tắc đặt và tính duy nhất của alias

Oracle mô tả các entry trong keystore được truy cập bằng các alias duy nhất. Vì vậy, hãy chọn một alias riêng cho mỗi entry trong cùng một keystore.

### Alias chỉ duy nhất trong keystore

Ví dụ:

- \`app-signing\` trong \`release.p12\`
- \`app-signing\` trong \`test.p12\`

Hai alias này không xung đột vì chúng thuộc hai keystore khác nhau.

Trong cùng một keystore, không nên dùng một alias cho hai entry khác nhau. Nếu tên alias đã tồn tại, lệnh tạo hoặc nhập có thể từ chối, yêu cầu xác nhận ghi đè hoặc xử lý theo quy tắc riêng của command.

### Alias có phân biệt chữ hoa/chữ thường không?

Theo API \`java.security.KeyStore\`, việc alias có phân biệt chữ hoa/chữ thường hay không phụ thuộc implementation/provider. Vì vậy, không nên tạo hai alias chỉ khác chữ hoa/chữ thường, chẳng hạn \`AppSigning\` và \`appsigning\`. Hành vi có thể không nhất quán khi chuyển keystore giữa các định dạng hoặc provider.

Nên chọn quy ước chữ thường và dùng nhất quán trong mọi lệnh, cấu hình và pipeline.

### Quy ước đặt tên dễ quản lý

Alias nên ngắn, ổn định, có ý nghĩa và mô tả vai trò của entry. Ví dụ:

| Alias | Ý nghĩa |
|---|---|
| \`app-signing\` | Khóa dùng ký ứng dụng |
| \`api-server-tls\` | Khóa/chứng chỉ TLS của API server |
| \`database-client\` | Chứng chỉ xác thực client với database |
| \`internal-root-ca\` | Chứng chỉ CA gốc nội bộ |
| \`partner-a-ca\` | Chứng chỉ CA của đối tác A |
| \`session-aes\` | Khóa AES dùng cho phiên làm việc |

Một số nguyên tắc:

1. Dùng tên mô tả mục đích hoặc hệ thống sở hữu entry.
2. Dùng chữ thường, số và dấu gạch ngang để dễ dùng trong shell và cấu hình.
3. Không chỉ khác nhau bằng chữ hoa/chữ thường.
4. Không đưa password, private key hoặc secret vào alias.
5. Tránh tên quá chung như \`key1\`, \`cert\`, \`test\` trong keystore production.
6. Nếu cần phân biệt môi trường hoặc vòng đời, thêm hậu tố có quy ước như \`-staging\`, \`-prod\` hoặc \`-2026\`.
7. Ghi alias vào tài liệu vận hành và cấu hình ứng dụng; không dựa vào thứ tự entry trong keystore.

## 4. Chỉ định alias trong keytool

Hầu hết lệnh thao tác với một entry đều nhận tùy chọn:

~~~bash
-alias <alias-name>
~~~

Ví dụ:

~~~bash
keytool -list -alias app-signing -keystore app-signing.p12
~~~

Lệnh này yêu cầu keytool hiển thị entry có alias \`app-signing\` trong keystore \`app-signing.p12\`.

Nếu bỏ \`-alias\` trong lệnh \`-list\`, keytool liệt kê toàn bộ entry trong keystore. Với lệnh tạo entry, nên luôn chỉ định alias tường minh để tránh dựa vào alias mặc định.

### Một số lệnh sử dụng alias

| Lệnh | Vai trò của alias |
|---|---|
| \`-genkeypair\` | Tên entry lưu public/private key |
| \`-genseckey\` | Tên entry lưu secret key |
| \`-importcert\` | Entry nhận chứng chỉ hoặc certificate reply |
| \`-certreq\` | Entry private key dùng tạo CSR |
| \`-list\` | Entry cần xem; bỏ alias để liệt kê tất cả |
| \`-exportcert\` | Entry có chứng chỉ cần xuất |
| \`-changealias\` | Alias cũ và tên alias mới |
| \`-delete\` | Entry cần xóa |
| \`-keypasswd\` | Entry có private/secret key cần đổi password |
| \`-importkeystore\` | Alias nguồn và alias đích khi nhập một entry |

Các lệnh keytool có thể nhận thêm \`-keystore\` và \`-storetype\` để xác định đúng kho lưu trữ. Nếu bỏ \`-keystore\`, một số lệnh dùng keystore mặc định trong thư mục home, thường là \`.keystore\`. Trong script và tài liệu vận hành, nên chỉ rõ đường dẫn để tránh vô tình thao tác nhầm kho.

## 5. Ví dụ: tạo entry có alias cụ thể

JDK 9 trở lên mặc định dùng PKCS12 nếu không thay đổi cấu hình bảo mật. Ví dụ dưới đây chỉ rõ định dạng PKCS12 để lệnh có thể tái lập giữa các máy.

Tạo một cặp khóa RSA và chứng chỉ tự ký:

~~~bash
keytool -genkeypair \
  -alias app-signing \
  -keyalg RSA \
  -keysize 3072 \
  -validity 365 \
  -dname "CN=Example Application, OU=Engineering, O=Example, C=VN" \
  -keystore app-signing.p12 \
  -storetype PKCS12
~~~

Keytool sẽ yêu cầu nhập password cho keystore và password bảo vệ private key nếu cần. Khi dùng PKCS12, nhiều công cụ yêu cầu password của private key trùng với password keystore; hãy làm theo prompt và quy tắc tương thích của công cụ tiêu thụ.

Sau khi chạy, entry được lưu dưới alias \`app-signing\`. Nếu bỏ tùy chọn \`-alias\`, keytool có thể dùng alias mặc định \`mykey\`; không nên dựa vào giá trị mặc định trong quy trình production.

### Liệt kê tất cả alias

~~~bash
keytool -list -keystore app-signing.p12 -storetype PKCS12
~~~

### Xem chi tiết một alias

~~~bash
keytool -list -v \
  -alias app-signing \
  -keystore app-signing.p12 \
  -storetype PKCS12
~~~

Với key entry, output verbose thường có các trường như:

~~~text
Alias name: app-signing
Entry type: PrivateKeyEntry
Certificate chain length: 1
Owner: CN=Example Application, OU=Engineering, O=Example, C=VN
Issuer: CN=Example Application, OU=Engineering, O=Example, C=VN
~~~

Đây là output minh họa; ngày tạo, serial number, fingerprint, thời hạn và các trường chứng chỉ phụ thuộc dữ liệu thực tế.

Alias cho biết entry nào đang được xem. \`Entry type\` cho biết entry chứa loại dữ liệu nào. Nếu entry là PrivateKeyEntry, \`Certificate chain length\` cho biết số chứng chỉ trong chuỗi đang gắn với private key.

## 6. Dùng alias khi tạo và nhập chứng chỉ

### Tạo một trusted certificate entry

Giả sử đã nhận được chứng chỉ CA gốc trong tệp \`internal-root-ca.pem\`. Có thể nhập chứng chỉ đó vào truststore:

~~~bash
keytool -importcert \
  -alias internal-root-ca \
  -file internal-root-ca.pem \
  -keystore truststore.p12 \
  -storetype PKCS12
~~~

Nếu alias chưa tồn tại, keytool tạo một TrustedCertificateEntry với tên \`internal-root-ca\`.

Trước khi xác nhận tin cậy chứng chỉ, hãy kiểm tra fingerprint SHA-256 bằng nguồn độc lập hoặc kênh xác thực đã tin cậy:

~~~bash
keytool -printcert -file internal-root-ca.pem
~~~

Đối chiếu fingerprint nhận được với fingerprint do CA hoặc quản trị viên cung cấp qua kênh an toàn. Không nên dùng \`-noprompt\` để bỏ qua bước xác minh trong một quy trình nhập chứng chỉ chưa được kiểm soát.

### Tạo CSR từ alias private key

Nếu entry \`app-signing\` chứa private key, có thể tạo Certificate Signing Request (CSR):

~~~bash
keytool -certreq \
  -alias app-signing \
  -file app-signing.csr \
  -keystore app-signing.p12 \
  -storetype PKCS12
~~~

CSR được tạo bằng private key tương ứng với alias. Gửi CSR đến CA theo quy trình cấp chứng chỉ của tổ chức.

### Nhập certificate reply vào đúng alias

Sau khi CA trả certificate hoặc certificate chain, nhập lại vào alias đang chứa key pair:

~~~bash
keytool -importcert \
  -trustcacerts \
  -alias app-signing \
  -file app-signing-reply.pem \
  -keystore app-signing.p12 \
  -storetype PKCS12
~~~

Ở đây, \`app-signing\` đã là key entry. Keytool hiểu chứng chỉ được nhập là certificate reply, kiểm tra public key trong reply khớp với key entry và cập nhật certificate chain cho entry đó. Alias vẫn là \`app-signing\`; private key không được thay thế bằng certificate reply.

Phân biệt hai tình huống:

- Alias chưa tồn tại: nhập chứng chỉ CA/đối tác để tạo trusted certificate entry.
- Alias đã trỏ đến key entry: nhập certificate reply để gắn chứng chỉ/chain với private key tương ứng.

Nếu alias đã tồn tại dưới dạng trusted certificate entry, keytool không thể coi nó như key entry để nhập certificate reply. Hãy xác định đúng loại entry trước khi thực hiện.

## 7. Xuất chứng chỉ theo alias

Dùng \`-exportcert\` để xuất chứng chỉ gắn với alias:

~~~bash
keytool -exportcert -rfc \
  -alias app-signing \
  -file app-signing.crt \
  -keystore app-signing.p12 \
  -storetype PKCS12
~~~

Tùy chọn \`-rfc\` xuất chứng chỉ ở dạng Base64 PEM với các dòng BEGIN/END. Nếu không dùng \`-rfc\`, dữ liệu mặc định ở dạng binary.

Nếu alias là trusted certificate entry, lệnh xuất chứng chỉ của entry đó. Nếu alias là key entry có certificate chain, lệnh xuất chứng chỉ đầu tiên trong chain, thường là chứng chỉ của chủ thể sở hữu private key.

**-exportcert chỉ xuất chứng chỉ public, không xuất private key.** Đây không phải bản backup đầy đủ của key entry. Nếu cần backup private key, hãy dùng quy trình sao lưu keystore được mã hóa và bảo vệ chặt chẽ.

## 8. Đổi alias bằng -changealias

Khi cần chuẩn hóa tên entry hoặc đổi quy ước naming, dùng:

~~~bash
keytool -changealias \
  -alias old-app-key \
  -destalias app-signing \
  -keystore app-signing.p12 \
  -storetype PKCS12
~~~

- \`-alias\` là tên hiện tại.
- \`-destalias\` là tên mới.

Thao tác đổi alias giữ nguyên entry và nội dung khóa/chứng chỉ; nó không cấp chứng chỉ mới và không đổi Subject của chứng chỉ.

Sau khi đổi tên, hãy kiểm tra lại:

~~~bash
keytool -list -alias app-signing -keystore app-signing.p12 -storetype PKCS12
~~~

Đồng thời cập nhật cấu hình ứng dụng, TLS connector, lệnh jarsigner, pipeline ký và tài liệu vận hành đang tham chiếu alias cũ. Nếu còn cấu hình dùng tên cũ, ứng dụng có thể không tìm thấy entry sau migration.

Tên alias đích phải chưa được dùng bởi entry khác. Nếu alias đích đã tồn tại, hãy giải quyết xung đột có chủ đích trước khi đổi tên.

## 9. Xóa entry bằng -delete

Dùng \`-delete\` để xóa entry được nhận diện bằng alias:

~~~bash
keytool -delete \
  -alias old-test-key \
  -keystore app-signing.p12 \
  -storetype PKCS12
~~~

Lệnh xóa toàn bộ entry tại alias đó, không chỉ xóa nhãn alias. Nếu entry là PrivateKeyEntry, private key và certificate chain gắn với nó sẽ bị xóa khỏi keystore. Nếu entry là TrustedCertificateEntry, chứng chỉ tin cậy tương ứng sẽ bị xóa.

Trước khi xóa:

1. Kiểm tra alias bằng \`keytool -list -v\`.
2. Xác nhận đúng keystore và đúng loại entry.
3. Kiểm tra ứng dụng hoặc dịch vụ có còn tham chiếu alias không.
4. Backup keystore theo quy trình an toàn nếu entry còn giá trị.
5. Chỉ xóa sau khi đã xác nhận tác động.

Không nhầm \`-delete\` với \`-changealias\`: một lệnh xóa entry, lệnh còn lại đổi tên entry.

## 10. Chuyển entry sang keystore khác và đổi alias

\`-importkeystore\` có thể nhập một entry hoặc toàn bộ entry từ keystore nguồn sang keystore đích.

Ví dụ nhập một entry và đổi alias trong keystore mới:

~~~bash
keytool -importkeystore \
  -srckeystore source.p12 \
  -srcstoretype PKCS12 \
  -srcalias old-app-key \
  -destkeystore destination.p12 \
  -deststoretype PKCS12 \
  -destalias app-signing
~~~

Keytool sẽ yêu cầu password cần thiết để đọc keystore nguồn và ghi keystore đích. Nếu không chỉ định \`-destalias\`, alias nguồn thường được dùng làm alias đích khi nhập một entry.

Nếu không chỉ định \`-srcalias\`, lệnh có thể nhập tất cả entry từ keystore nguồn. Khi alias đích đã tồn tại, keytool có thể yêu cầu xác nhận ghi đè hoặc chọn tên khác; hành vi với \`-noprompt\` cần được xem xét kỹ vì entry hiện có có thể bị ghi đè.

Sau khi chuyển đổi, kiểm tra cả hai kho:

~~~bash
keytool -list -keystore source.p12 -storetype PKCS12
keytool -list -keystore destination.p12 -storetype PKCS12
~~~

Đừng xóa keystore nguồn cho đến khi đã xác minh entry đích, certificate chain, khả năng phục hồi private key và ứng dụng sử dụng được alias mới.

## 11. Alias trong jarsigner và ứng dụng Java

### Dùng alias để ký JAR

\`jarsigner\` dùng alias để chọn private key entry thực hiện chữ ký:

~~~bash
jarsigner \
  -keystore app-signing.p12 \
  -storetype PKCS12 \
  app.jar \
  app-signing
~~~

Alias phải trỏ đến key entry có private key phù hợp. TrustedCertificateEntry chỉ chứa chứng chỉ public nên không thể dùng để ký JAR.

Trong pipeline release, alias thường được cấu hình rõ ràng cùng keystore path, loại keystore và cơ chế cấp password an toàn.

### Truy cập alias bằng Java KeyStore API

Java có thể liệt kê alias và kiểm tra loại entry qua lớp \`java.security.KeyStore\`.

Tạo tệp \`AliasInventory.java\`:

~~~java
import java.io.Console;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.util.Arrays;
import java.util.Enumeration;

public class AliasInventory {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java AliasInventory <keystore-file>");
            System.exit(2);
        }

        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException(
                    "Run this program from an interactive terminal."
            );
        }

        char[] password = console.readPassword("Keystore password: ");
        if (password == null) {
            throw new IllegalStateException("No password was provided.");
        }

        try {
            KeyStore keyStore = KeyStore.getInstance("PKCS12");

            try (InputStream input =
                         Files.newInputStream(Path.of(args[0]))) {
                keyStore.load(input, password);
            }

            Enumeration<String> aliases = keyStore.aliases();
            while (aliases.hasMoreElements()) {
                String alias = aliases.nextElement();

                String entryType;
                if (keyStore.isKeyEntry(alias)) {
                    entryType = "key entry";
                } else if (keyStore.isCertificateEntry(alias)) {
                    entryType = "trusted certificate entry";
                } else {
                    entryType = "other entry";
                }

                System.out.printf("%s: %s%n", alias, entryType);
            }
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 AliasInventory.java
~~~

Chạy với keystore PKCS12 đã có:

~~~bash
java AliasInventory app-signing.p12
~~~

Output minh họa nếu keystore có hai entry:

~~~text
app-signing: key entry
internal-root-ca: trusted certificate entry
~~~

Kết quả thật phụ thuộc vào nội dung keystore. Chương trình không in private key hoặc password; nó chỉ liệt kê alias và phân loại entry.

Các API thường dùng:

| API | Công dụng |
|---|---|
| \`aliases()\` | Liệt kê tất cả alias |
| \`containsAlias(alias)\` | Kiểm tra alias có tồn tại |
| \`getCertificate(alias)\` | Lấy chứng chỉ của entry |
| \`getCertificateChain(alias)\` | Lấy certificate chain của key entry |
| \`getKey(alias, password)\` | Lấy key nếu password hợp lệ |
| \`isKeyEntry(alias)\` | Kiểm tra entry có chứa key |
| \`isCertificateEntry(alias)\` | Kiểm tra entry có phải trusted certificate |
| \`deleteEntry(alias)\` | Xóa entry theo alias |
| \`getCreationDate(alias)\` | Lấy ngày tạo entry |

Độ nhạy chữ hoa/chữ thường của alias phụ thuộc implementation của keystore provider. Nếu ứng dụng chuyển giữa JKS, PKCS12 hoặc provider phần cứng, hãy dùng tên alias nhất quán và kiểm tra hành vi trên đích triển khai.

## 12. Bảo mật và vận hành alias

Alias không phải bí mật. Nó có thể xuất hiện trong lệnh build, log, cấu hình hoặc output \`keytool -list\`. Không đặt password, token hoặc dữ liệu nhạy cảm vào tên alias.

Các nguyên tắc quan trọng:

- Không ghi password keystore hoặc private key trực tiếp vào command line, script hoặc repository.
- Khi có thể, để keytool hỏi password tương tác hoặc dùng cơ chế bảo vệ bí mật phù hợp của hệ thống build.
- Bảo vệ file keystore và backup bằng quyền truy cập tối thiểu.
- Không gửi private key cho bên cần xác minh chứng chỉ; chỉ chia sẻ public certificate khi phù hợp.
- Kiểm tra fingerprint qua kênh độc lập trước khi nhập trusted certificate.
- Tránh \`-noprompt\` trong thao tác tin cậy chứng chỉ nếu chưa có bước xác minh fingerprint tự động đáng tin cậy.
- Ghi rõ alias trong cấu hình dịch vụ và tài liệu vận hành.
- Trước khi đổi tên hoặc xóa alias, tìm mọi tham chiếu trong ứng dụng, pipeline, secret manager và cấu hình hạ tầng.
- Backup keystore trước khi thay đổi entry quan trọng và kiểm thử khả năng khôi phục.
- Dùng alias ổn định theo vai trò; không dùng alias làm cơ chế phân quyền hoặc xác thực.

Một alias dễ đoán không làm lộ private key, nhưng người vận hành có thể chọn nhầm entry nếu tên quá chung. Tên rõ ràng giúp giảm lỗi cấu hình và thao tác.

## 13. Lỗi thường gặp liên quan đến alias

### Alias đã tồn tại

Lệnh tạo key hoặc nhập trusted certificate có thể báo alias đã tồn tại. Kiểm tra entry trước khi quyết định dùng tên khác, đổi tên hoặc ghi đè. Không ghi đè entry đang dùng trong production khi chưa có backup và kế hoạch chuyển đổi.

### Không tìm thấy alias

Nguyên nhân thường gặp:

- Gõ sai tên alias.
- Chọn nhầm file keystore.
- Dùng sai \`-storetype\`.
- Alias đã bị đổi tên hoặc xóa.
- Keystore được tạo bởi provider khác có quy tắc alias khác.

Dùng \`keytool -list\` trên đúng keystore để xem các alias hiện có.

### Alias đúng nhưng entry type không đúng

Ví dụ, lệnh ký JAR chọn alias của TrustedCertificateEntry. Entry này không có private key nên không thể tạo chữ ký. Kiểm tra \`Entry type\` bằng \`keytool -list -v\` và chọn PrivateKeyEntry phù hợp.

### Import certificate vào nhầm alias

Nếu alias trỏ đến key entry, \`-importcert\` được hiểu là nhập certificate reply. Nếu alias chưa tồn tại, keytool tạo trusted certificate entry. Xác nhận mục tiêu trước khi chạy lệnh và dùng alias riêng cho CA certificate.

### Alias chỉ khác chữ hoa/chữ thường

Một số provider có thể coi các tên này là cùng alias. Chuẩn hóa quy ước tên và tránh tên chỉ khác chữ hoa/chữ thường.

### Đổi alias xong ứng dụng không tìm thấy key

Cấu hình TLS, jarsigner hoặc ứng dụng Java có thể vẫn tham chiếu alias cũ. Tìm và cập nhật tất cả cấu hình tiêu thụ entry; kiểm tra lại bằng lệnh list và test trên môi trường triển khai.

### Không truy xuất được private key

Alias có thể tồn tại nhưng password bảo vệ key sai, hoặc entry không phải key entry. Kiểm tra loại entry, password và keystore provider. Không xóa entry chỉ vì một lần truy xuất thất bại.

### Nhầm export certificate với backup private key

\`-exportcert\` chỉ xuất public certificate. Muốn backup private key cần sao lưu keystore hoặc chuyển entry bằng quy trình bảo vệ khóa phù hợp.

## 14. Quy trình quản lý alias đề xuất

1. Chọn keystore và loại keystore rõ ràng, ưu tiên định dạng tương thích như PKCS12 nếu phù hợp.
2. Đặt alias mô tả mục đích, hệ thống và môi trường.
3. Tạo key entry hoặc trusted certificate entry theo đúng vai trò.
4. Liệt kê alias sau khi tạo và xác nhận entry type.
5. Ghi alias vào cấu hình tiêu thụ, ví dụ TLS hoặc jarsigner.
6. Kiểm tra certificate Subject, SAN, fingerprint và thời hạn; không dựa vào alias để xác minh danh tính.
7. Khi cấp certificate mới, dùng lại alias key entry nếu đang nhập certificate reply cho key đó.
8. Khi đổi alias, cập nhật mọi tham chiếu trước khi triển khai.
9. Khi xóa entry, xác minh không còn caller sử dụng và đã backup nếu cần.
10. Quét hoặc kiểm tra keystore định kỳ để loại bỏ entry hết hạn, không dùng hoặc không rõ owner.

## 15. Checklist khi thao tác alias

- Xác định đúng file keystore và \`-storetype\`.
- Xác định alias chính xác trước khi chạy lệnh.
- Kiểm tra entry type: PrivateKeyEntry, SecretKeyEntry hay TrustedCertificateEntry.
- Dùng alias duy nhất trong cùng keystore.
- Tránh alias chỉ khác nhau bằng chữ hoa/chữ thường.
- Dùng tên mô tả vai trò, không chứa secret.
- Không dựa vào alias để xác minh Subject hoặc fingerprint chứng chỉ.
- Khi nhập CA certificate, xác minh fingerprint trước khi tin cậy.
- Khi nhập certificate reply, dùng alias đang chứa key pair tương ứng.
- Khi đổi alias, cập nhật cấu hình TLS, jarsigner và ứng dụng.
- Khi xóa alias, hiểu rằng toàn bộ entry sẽ bị xóa.
- Không xem file chứng chỉ export là backup của private key.
- Không đặt password trực tiếp trong command line hoặc script.
- Backup và kiểm tra khả năng khôi phục trước thay đổi quan trọng.
- Liệt kê lại keystore sau thao tác và kiểm thử ứng dụng tiêu thụ entry.

## 16. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Alias | Tên nhận diện một entry trong keystore |
| Keystore | Kho lưu khóa, chứng chỉ và thông tin xác thực |
| Entry | Một mục dữ liệu bên trong keystore |
| PrivateKeyEntry | Entry chứa private key và certificate chain |
| SecretKeyEntry | Entry chứa symmetric secret key |
| TrustedCertificateEntry | Entry chứa một chứng chỉ public được tin cậy |
| PKCS12 | Định dạng keystore đa nền tảng, mặc định trong JDK hiện đại |
| JKS | Định dạng keystore Java truyền thống |
| Certificate chain | Chuỗi chứng chỉ liên kết chứng chỉ thực thể với CA |
| CSR | Certificate Signing Request gửi đến CA |
| Fingerprint | Giá trị băm dùng đối chiếu nhận dạng chứng chỉ |
| Subject | Thông tin chủ thể trong chứng chỉ X.509 |
| SAN | Subject Alternative Name, tên miền/IP hoặc định danh bổ sung |
| \`-changealias\` | Đổi tên alias của entry |
| \`-delete\` | Xóa entry theo alias |
| \`-importkeystore\` | Chuyển một hoặc nhiều entry giữa các keystore |

Alias là cách gọi một entry cụ thể trong keystore. Quản lý alias nhất quán giúp keytool, jarsigner và ứng dụng Java chọn đúng khóa hoặc chứng chỉ; hãy luôn xác nhận loại entry, keystore, fingerprint và các cấu hình đang tham chiếu trước khi thay đổi.

## Tài liệu tham khảo

- Oracle JDK 24 — [The keytool Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/keytool.html)
- Oracle Java SE 24 API — [KeyStore](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/security/KeyStore.html)
- Oracle JDK 24 — [Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/24/security/java-cryptography-architecture-jca-reference-guide.html)
- Oracle JDK 24 — [Security Developer's Guide](https://docs.oracle.com/en/java/javase/24/security/security-developer-guide.pdf)