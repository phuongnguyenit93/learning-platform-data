# Định dạng keystore và kiểm chứng khả năng đọc dữ liệu cũ

Khi nâng Java từ một JDK cũ sang JDK mới, ứng dụng có thể vẫn biên dịch và khởi động nhưng không thể thiết lập TLS, ký tài liệu, xác thực bằng certificate hoặc giải mã khóa đã lưu. Nguyên nhân thường không nằm ở mã gọi API mới mà ở **định dạng keystore, provider bảo mật, thuật toán mã hóa/bảo vệ bên trong file, mật khẩu và cách ứng dụng nạp dữ liệu tồn tại từ phiên bản trước**.

Một file keystore có thể đã được tạo từ nhiều năm trước bằng `keytool` của JDK 8, rồi được sao chép qua nhiều môi trường. Khi đội dự án chuyển sang JDK 17 hoặc JDK 21, có thể xảy ra hai tình huống trái chiều: (1) JDK mới không đọc hoặc không sử dụng được dữ liệu cũ do chính sách/thuật toán/provider đã thay đổi; (2) một file mới được tạo bởi JDK mới hoạt động ở môi trường mới nhưng JDK cũ dùng trong rollback không còn đọc được. Vì thế, kiểm tra tương thích keystore phải bao gồm cả **đọc dữ liệu cũ bằng runtime mới** lẫn **đọc dữ liệu mới bằng runtime cũ nếu rollback yêu cầu**.

Bài học này trình bày các định dạng Java keystore phổ biến, cách xác định đúng format thay vì suy đoán theo tên file, phương pháp kiểm kê và kiểm chứng trên nhiều phiên bản JDK, cách chuyển đổi có kiểm soát từ JKS sang PKCS#12 và các điểm cần lưu ý khi sử dụng keystore/truststore trong hệ thống production.

## 1. Keystore là gì và khác truststore thế nào?

Trong Java, `KeyStore` là API chuẩn để quản lý một tập entry có alias. Một implementation keystore có thể đọc dữ liệu từ file, thiết bị mật mã, provider hoặc một nguồn lưu trữ khác. Java SE không bắt buộc mọi loại keystore phải cùng một biểu diễn nhị phân hoặc cùng cách bảo vệ dữ liệu.

Các kiểu entry điển hình:

- **Private key entry:** chứa private key và chuỗi certificate đi kèm. Dùng cho định danh TLS server, mutual TLS client, ký số và các thao tác liên quan khóa bất đối xứng.
- **Trusted certificate entry:** chứa certificate được tin cậy theo cấu hình của ứng dụng; không chứa private key của chứng chỉ đó.
- **Secret key entry:** chứa khóa đối xứng; mức hỗ trợ phụ thuộc keystore type và provider.

**Keystore** và **truststore** chủ yếu là **vai trò sử dụng**, không nhất thiết là hai định dạng file khác nhau:

| Vai trò | Nội dung thường có | Cách dùng |
|---|---|---|
| Identity keystore | Private key + certificate chain | Xác thực bản thân ở TLS/mTLS; ký |
| Truststore | Trusted CA hoặc certificate tin cậy | Xác minh certificate của phía đối diện |
| Kho khóa ứng dụng | Private key, secret key hoặc nhiều entry | Ký, giải mã, bảo vệ dữ liệu tùy ứng dụng |
| Hardware-backed store | Entry được provider/token cung cấp | Sử dụng khóa trong HSM/smart card |

Một file `.p12` có thể dùng làm keystore hoặc truststore. Một file `.jks` cũng có thể chứa trusted certificates. Việc đổi tên file từ `server.jks` sang `truststore.p12` không chuyển đổi nội dung, không đổi type và không tự biến certificate chain thành trust anchors phù hợp.

### 1.1. Phân biệt khóa, certificate và chuỗi certificate

Một `PrivateKeyEntry` thường có private key và certificate chain liên kết với khóa. Certificate public không phải private key. Với TLS server, certificate chain có thể gồm leaf certificate và intermediate certificates; truststore của client thường chứa các CA hoặc certificate được phép tin cậy.

Các câu hỏi cần trả lời khi migration:

1. Có đúng private key cần dùng không?
2. Certificate chain có đầy đủ và đúng thứ tự/đúng khóa không?
3. Alias mà code hoặc JSSE chọn có còn tồn tại không?
4. Password bảo vệ file và password để lấy key có còn đúng không?
5. Provider/JDK mới có đọc được thuật toán bảo vệ entry không?
6. Certificate có còn hợp lệ theo hostname, thời hạn, trust chain và chính sách bảo mật hiện hành không?

Một file có thể **đọc được hoàn toàn** mà TLS vẫn thất bại do certificate hết hạn, certificate không có EKU phù hợp, thuật toán chữ ký bị hạn chế hoặc CA không được phía còn lại tin cậy. Đừng dùng thành công của `KeyStore.load` làm bằng chứng duy nhất cho thành công của TLS.

## 2. Các định dạng keystore thường gặp

### 2.1. JKS — Java KeyStore

`JKS` là định dạng keystore gắn với hệ sinh thái Java trong thời gian dài. Ở nhiều bản JDK cũ, JKS từng là loại mặc định của `keytool` và `KeyStore.getDefaultType()`.

Đặc điểm cần biết:

- Đây là định dạng truyền thống đặc thù của Java.
- Hỗ trợ các entry và cơ chế bảo vệ theo implementation.
- Có thể không hỗ trợ các loại entry/thuật toán theo cùng cách với PKCS#12 hoặc provider khác.
- Một hệ thống cũ có thể dùng `.jks` cho cả identity keystore và truststore.

JKS không nên được xem là lựa chọn tự động tốt nhất chỉ vì ứng dụng cũ dùng nó. Khi cần chuẩn hóa cho môi trường mới, nhóm có thể xem xét PKCS#12, nhưng phải kiểm tra khả năng tương thích thật của ứng dụng, thư viện và các runtime có quyền đọc file.

### 2.2. PKCS#12 — định dạng phổ biến để trao đổi khóa và certificate

`PKCS12` (thường biểu diễn trong file `.p12` hoặc `.pfx`) là định dạng theo chuẩn PKCS#12 và có khả năng tương tác rộng trong nhiều công cụ mật mã. Từ **JDK 9**, kiểu keystore mặc định theo Java đã chuyển sang `PKCS12` theo JEP 229; một số cập nhật JDK 8/vendor có thể mang các thay đổi tương thích hoặc backport, do đó phải kiểm tra runtime thực tế.

Điểm quan trọng:

- `PKCS12` là một **keystore type** trong Java, không chỉ là phần mở rộng file.
- File PKCS#12 có thể dùng các thuật toán khác nhau để bảo vệ khóa, certificate và kiểm tra tính toàn vẹn.
- Khả năng đọc thực tế còn phụ thuộc provider, JDK update và thuật toán bên trong file.
- Một file PKCS#12 mới được tạo bởi JDK mới không nhất thiết có thể được mở bởi mọi JDK cũ, dù đều ghi “PKCS12”.

Đây là loại được chọn phổ biến cho nhiều dự án mới. Tuy nhiên, yêu cầu quan trọng nhất khi migration là **tính tương thích với các phiên bản đang vận hành**, không phải chỉ đổi extension.

### 2.3. JCEKS — định dạng Java cũ cho một số kiểu khóa

`JCEKS` có thể được gặp trong ứng dụng cũ khi cần lưu private/secret keys theo cơ chế hỗ trợ của provider Java. Đừng coi JCEKS chỉ là một biến thể có thể đổi tên thành JKS. Nếu ứng dụng đang lưu `SecretKeyEntry`, việc chọn định dạng đích cần được kiểm tra với đúng loại entry và provider.

Một migration có thể yêu cầu xuất/nhập key bằng API hay công cụ thích hợp thay vì giả định lệnh chuyển đổi JKS→PKCS12 sẽ áp dụng nguyên trạng cho mọi trường hợp JCEKS.

### 2.4. BCFKS và các provider bên thứ ba

Một số dự án sử dụng `BCFKS` hoặc loại keystore khác do Bouncy Castle hay provider bên thứ ba cung cấp. Khả năng đọc phụ thuộc provider đã được cài đặt/đăng ký đúng và version của provider.

Nếu gặp lỗi `KeyStoreException: ... not found` hoặc thuật toán không có, cần kiểm tra:

- Keystore type được yêu cầu.
- Provider name và provider JAR/module.
- Provider đã được đăng ký chưa.
- JDK hiện tại có hỗ trợ và cho phép thuật toán cần dùng không.
- Có ràng buộc chính sách FIPS hay không.

Không nên đổi type sang `PKCS12` cho “dễ chạy” nếu dữ liệu thực tế thuộc định dạng khác. Việc làm đó thường chỉ tạo lỗi nạp file và che đi nguyên nhân ban đầu.

### 2.5. PKCS#11 — khóa trong token hoặc HSM

`PKCS11` trong Java thường đại diện cho một provider giao tiếp với token, smart card hoặc Hardware Security Module (HSM), **không phải một file keystore di động giống `.jks` hay `.p12`**.

Trong hệ thống có khóa không thể xuất khỏi HSM, mục tiêu migration là xác nhận cấu hình provider, thư viện PKCS#11 native, slot/token, PIN, thuật toán và phép ký trên JDK mới. Không nên cố “chuyển file PKCS11 thành p12” như thao tác sao chép thông thường.

### 2.6. PEM, DER và PKCS#12 không giống nhau

`PEM` là cách mã hóa văn bản (thường dùng Base64 với header/footer) để biểu diễn certificate, public key hoặc private key theo các cấu trúc khác nhau. `DER` là dạng mã hóa nhị phân của các cấu trúc ASN.1 tương ứng.

Ví dụ certificate PEM:

~~~text
-----BEGIN CERTIFICATE-----
... dữ liệu chứng chỉ được mã hóa Base64 ...
-----END CERTIFICATE-----
~~~

Một cặp file `cert.pem` và `key.pem` không đương nhiên là Java keystore. Để Java đọc bằng `KeyStore`, có thể cần import certificate/key vào loại keystore thích hợp hoặc sử dụng provider/parser được dự án hỗ trợ. Không nên đổi tên `.pem` thành `.p12`.

## 3. Thay đổi mặc định giữa các phiên bản JDK

### 3.1. JEP 229 và giá trị `keystore.type`

Trong các môi trường Java cũ, lời gọi:

~~~java
String type = KeyStore.getDefaultType();
~~~

có thể trả về `jks`. Trên nhiều JDK hiện đại, giá trị mặc định là `pkcs12`. Giá trị này có thể chịu ảnh hưởng cấu hình security property `keystore.type` và bản phân phối JDK.

Các hệ quả:

- `keytool -genkeypair -keystore mykeys` trên JDK mới có thể tạo keystore PKCS#12 mặc định.
- Ứng dụng `KeyStore.getInstance(KeyStore.getDefaultType())` có thể chọn type khác sau khi nâng JDK.
- Một file cũ có thể vẫn đọc được nhờ cơ chế nhận diện tương thích ở một số provider/JDK, nhưng không nên phụ thuộc âm thầm vào hành vi đó.
- Kết quả test trên JDK developer chưa chứng minh runtime production có cùng default keystore type.

**Quy tắc khi migration:** khai báo keystore type rõ ràng ở nơi cần ổn định định dạng và ghi thông tin này vào cấu hình. Dùng `PKCS12` hoặc `JKS` theo file thực tế thay vì suy đoán qua đuôi filename.

### 3.2. Tự nhận diện JKS/PKCS12 không phải hợp đồng thay cho kiểm thử

Một số implementation JDK hỗ trợ nhận diện tương thích giữa JKS và PKCS#12 (các behavior như JEP 229 mô tả). Tuy nhiên, việc một lệnh `keytool` hoặc `KeyStore.load` thành công dù type không khớp **không chứng minh** mọi JDK, mọi provider và mọi cơ chế triển khai sẽ xử lý như vậy.

Khi lên kế hoạch đa JDK:

1. Ghi **type thực tế** của artifact.
2. Ghi type được ứng dụng yêu cầu khi nạp.
3. Test với provider và JDK được triển khai.
4. Không dựa vào fallback không được ứng dụng cam kết.
5. Đưa cấu hình type vào release manifest hoặc tài liệu vận hành.

### 3.3. Thuật toán bên trong PKCS#12 có thể thay đổi

PKCS#12 là một container format. Các thành phần bên trong được bảo vệ bằng các cơ chế có thể thay đổi qua version JDK và provider, bao gồm thuật toán mã hóa và kiểm tra tính toàn vẹn (MAC). Khi JDK mới đổi các thuật toán mặc định theo hướng bảo mật mạnh hơn, runtime cũ có thể **không hiểu hoặc không hỗ trợ thuật toán** đó.

Điều này gây ra một dạng lỗi đáng chú ý:

- JDK mới **đọc được** file PKCS#12 cũ.
- JDK mới tạo **file PKCS#12 mới** dùng thuật toán mới.
- JDK cũ phục vụ rollback **không đọc được** file mới.

Không nên kết luận chỉ từ `.p12` rằng binary file có tính tương thích hai chiều. Cần test theo đúng cặp runtime, keystore entry và các thao tác thực tế.

Một số JDK cung cấp cơ chế cấu hình chính sách thuật toán PKCS#12 hoặc tùy chọn tương thích dạng legacy. Tên security property, behavior và khả năng hỗ trợ phụ thuộc phiên bản JDK. Chỉ dùng những cơ chế này sau khi đọc tài liệu của đúng version và đánh giá rủi ro bảo mật; tránh hạ thuật toán chỉ vì runtime cũ chưa được nâng.

## 4. Kiểm kê keystore và truststore trước khi chuyển đổi

Một migration có kiểm soát bắt đầu bằng việc biết file nào đang tồn tại và ai sử dụng chúng.

Tối thiểu cần ghi:

| Trường | Ý nghĩa |
|---|---|
| Vai trò | TLS server identity, mTLS client, truststore, ký số, khóa dữ liệu |
| Đường dẫn/nguồn | File trên disk, secret store, Kubernetes Secret, HSM, JAR resource |
| JDK/provider tạo | Version, vendor, công cụ đã tạo hoặc import |
| Keystore type | JKS, PKCS12, JCEKS, BCFKS, PKCS11 hoặc loại khác |
| Alias | Tên entry mà ứng dụng/JSSE chọn |
| Loại entry | PrivateKeyEntry, SecretKeyEntry, trustedCertEntry |
| Certificate chain | Leaf, intermediate, các định danh và thời hạn |
| Thuật toán | Key algorithm, certificate signature algorithm, key size, PBE/MAC nếu xác minh được |
| Mật khẩu | Nguồn secret và cơ chế truyền, **không ghi giá trị vào inventory** |
| Consumer | Service/instance/pipeline nào đọc artifact |
| Runtime | JDK/JVM, OS, provider thực tế đang đọc |
| Rollback | Runtime cũ có phải đọc file được ghi/chuyển đổi bởi bản mới không |
| Owner | Người chịu trách nhiệm bảo mật và vận hành |

Hãy phân biệt **bản gốc**, **bản sao đã được duyệt để kiểm tra** và **file đã chuyển đổi**. Không sửa trực tiếp file production trong bước khảo sát. Nếu chạy thử ở môi trường tách biệt, phải bảo vệ private key và passwords theo cùng chính sách kiểm soát truy cập như bản gốc.

### 4.1. Alias là hợp đồng ứng dụng

Một số ứng dụng chọn key theo alias cố định:

~~~java
KeyStore.PrivateKeyEntry entry = (KeyStore.PrivateKeyEntry)
        store.getEntry(
                "service-tls",
                new KeyStore.PasswordProtection(keyPassword));
~~~

Nếu alias được đổi từ `service-tls` thành `1` trong quá trình import, code có thể không tìm thấy key dù file vẫn có private key. Tương tự, việc nhập nhiều certificate khác nhau vào truststore có thể thay đổi tập trust anchors và làm chính sách xác thực rộng hơn hoặc hẹp hơn.

Khi chuyển đổi, so sánh danh sách alias trước/sau, nhưng đừng chỉ so số lượng entry. Cần kiểm tra **loại entry, certificate fingerprint, chain, private-key accessibility và hành vi thực tế**.

## 5. Dùng keytool kiểm tra file cũ trên đúng JDK

`keytool` là công cụ JDK để quản lý key/certificate và keystore. Để đánh giá compatibility, cần chạy **bản `keytool` của từng JDK mục tiêu**, không chỉ bản có sẵn trong `PATH`.

Trước khi kiểm tra:

~~~bash
java -version
keytool -help
~~~

Nếu có nhiều JDK, ưu tiên gọi đường dẫn tuyệt đối, ví dụ đường dẫn tới `$JAVA_HOME/bin/keytool` sau khi xác nhận `JAVA_HOME` đang trỏ đúng JDK. Trong Windows PowerShell, có thể dùng đường dẫn tới `keytool.exe` của JDK cụ thể.

### 5.1. Liệt kê metadata của JKS

~~~bash
keytool -list -v \
  -keystore /secure/input/legacy.jks \
  -storetype JKS
~~~

Lệnh thường yêu cầu password bằng prompt; tránh đưa password thật trực tiếp vào command line hoặc script được lưu trong log. Output có thể gồm alias, entry type, certificate chain, subject, issuer, fingerprint, thuật toán và thời hạn certificate.

### 5.2. Liệt kê metadata của PKCS#12

~~~bash
keytool -list -v \
  -keystore /secure/input/identity.p12 \
  -storetype PKCS12
~~~

Chạy với cùng artifact trên **JDK cũ và JDK mới**. Ghi rõ bản `keytool` và provider để khi khác kết quả có thể xác định khác biệt do JDK.

### 5.3. Không suy luận type chỉ bằng extension

Các tên sau không phải bằng chứng chắc chắn của format:

~~~text
truststore.jks
client.p12
server.keystore
cert-store
legacy.pfx
~~~

Tên file có thể bị đặt lại hoặc copy qua nhiều hệ thống. Nếu chưa biết type, hãy kiểm tra nguồn tạo file, metadata deployment và thử lệnh với type ứng viên trên bản sao được phép khảo sát. Không dùng thao tác tạo mới/ghi đè lên file gốc để “thử xem có mở được không”.

### 5.4. Trường hợp không có mật khẩu

Một số store có cấu hình password đặc thù hoặc chứa trusted certificates theo chính sách riêng. Không nên coi việc công cụ liệt kê được một phần thông tin mà không xác thực integrity đầy đủ là bằng chứng file đã được kiểm chứng toàn vẹn. Cần hiểu mode mà provider đang dùng và yêu cầu bảo mật của hệ thống.

Với store chứa private key, có thể tồn tại password bảo vệ store và password bảo vệ từng key. Hai giá trị đó có thể khác nhau hoặc chịu hạn chế từ định dạng/provider. Vì vậy việc `keytool -list` thành công không đồng nghĩa Java code có thể lấy private key để ký.

## 6. Kiểm tra bằng API java.security.KeyStore

`KeyStore` giúp ứng dụng mở dữ liệu theo type/provider tường minh. Ví dụ dưới đây minh họa việc đọc metadata của store mà **không in private key hoặc password**.

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;
import java.util.Enumeration;

public final class KeystoreInspector {
    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: KeystoreInspector <type> <path> <password-env-name>");
        }

        String type = args[0];            // JKS hoặc PKCS12
        Path path = Path.of(args[1]);
        String envName = args[2];
        String supplied = System.getenv(envName);
        if (supplied == null) {
            throw new IllegalStateException(
                    "Thiếu secret environment variable");
        }

        char[] password = supplied.toCharArray();
        try {
            KeyStore store = KeyStore.getInstance(type);
            try (InputStream in = Files.newInputStream(path)) {
                store.load(in, password);
            }

            System.out.println("type=" + store.getType());
            System.out.println("provider=" +
                    store.getProvider().getName());
            System.out.println("size=" + store.size());

            Enumeration<String> aliases = store.aliases();
            while (aliases.hasMoreElements()) {
                String alias = aliases.nextElement();
                System.out.println("alias=" + alias);
                System.out.println("keyEntry=" +
                        store.isKeyEntry(alias));
                System.out.println("certificateEntry=" +
                        store.isCertificateEntry(alias));

                Certificate cert = store.getCertificate(alias);
                if (cert instanceof X509Certificate) {
                    X509Certificate x509 = (X509Certificate) cert;
                    System.out.println("subject=" +
                            x509.getSubjectX500Principal());
                    System.out.println("notAfter=" +
                            x509.getNotAfter());
                }

                Certificate[] chain =
                        store.getCertificateChain(alias);
                System.out.println("chainLength=" +
                        (chain == null ? 0 : chain.length));
            }
        } finally {
            java.util.Arrays.fill(password, '\0');
        }
    }
}
~~~

Đây là ví dụ phục vụ môi trường kiểm tra được cấp quyền. Nó nhận password từ environment variable để tránh đưa password vào arguments; tuy vậy environment variable cũng có thể bị quan sát bởi những thành phần có quyền tương ứng trong hệ điều hành. Trong production, ưu tiên secret manager, credential provider hoặc cơ chế truyền bí mật phù hợp chính sách; tránh in hoặc lưu secret vào log.

Đoạn mã sử dụng `Path.of` (Java 11 trở lên). Nếu cần chạy trên JDK cũ hơn, thay bằng API `Paths.get` tương ứng và biên dịch với source/release phù hợp.

### 6.1. Kiểm tra rằng private key thật sự lấy được

Việc `store.isKeyEntry(alias)` trả về `true` chỉ xác nhận entry là key entry. Để kiểm chứng runtime có thể sử dụng key, cần thử truy xuất bằng đúng password bảo vệ entry và đúng provider:

~~~java
java.security.Key key = store.getKey(
        "service-tls",
        keyPassword
);

if (!(key instanceof java.security.PrivateKey)) {
    throw new IllegalStateException(
            "Alias không trỏ tới private key mong đợi");
}
~~~

Với HSM/token, key object có thể là handle không cho phép xuất raw key bytes; điều này là bình thường và không có nghĩa key không dùng được. Tiếp theo nên thử **phép ký rồi xác minh chữ ký bằng public key/certificate** hoặc thiết lập TLS/mTLS trong môi trường kiểm tra, tùy chức năng cần chứng minh.

Không viết private key ra stdout, file tạm hoặc monitoring system. Nếu cần so sánh danh tính của identity key, ưu tiên so sánh public key/certificate fingerprint và thử phép ký xác minh có kiểm soát, không dump private key.

### 6.2. Kiểm chứng certificate có còn hợp lệ

Với `X509Certificate`:

~~~java
X509Certificate cert = (X509Certificate)
        store.getCertificate("service-tls");

if (cert == null) {
    throw new IllegalStateException("Không có certificate");
}

cert.checkValidity();  // kiểm tra thời hạn hiệu lực theo thời gian hiện tại
~~~

`checkValidity()` chỉ kiểm tra khoảng thời gian hiệu lực, **không** thay thế xác minh certificate path, trust anchors, revocation, hostname hay mục đích sử dụng. Với TLS, cần thử handshake bằng cấu hình JSSE mà hệ thống thật đang dùng.

## 7. Chuyển đổi từ JKS sang PKCS#12 có kiểm soát

Nếu mục tiêu của dự án là chuẩn hóa identity keystore hoặc truststore cũ sang PKCS#12, `keytool -importkeystore` là công cụ phổ biến.

Ví dụ minh họa:

~~~bash
keytool -importkeystore \
  -srckeystore /secure/input/identity-old.jks \
  -srcstoretype JKS \
  -destkeystore /secure/output/identity-new.p12 \
  -deststoretype PKCS12
~~~

Lệnh thường hỏi source/destination passwords theo prompt. Đường dẫn destination phải là **file mới**, không được ghi đè file source trong quá trình khảo sát/migration. Nếu source chứa nhiều entries, kiểm tra tất cả entries được chuyển và có xử lý password đúng.

Có thể chọn một alias cụ thể nếu chỉ muốn chuyển một identity:

~~~bash
keytool -importkeystore \
  -srckeystore /secure/input/identity-old.jks \
  -srcstoretype JKS \
  -srcalias service-tls \
  -destkeystore /secure/output/identity-new.p12 \
  -deststoretype PKCS12
~~~

Đối với production, nên vận hành theo quy trình được duyệt: backup bảo mật, ghi checksum file gốc, tạo file đích mới, test, rồi đổi cấu hình để trỏ sang file mới. Không dùng lệnh import như một tác vụ sửa trực tiếp file production đang phục vụ ứng dụng.

### 7.1. Kiểm tra sau chuyển đổi

So sánh trước và sau:

| Đối tượng | Điều phải so sánh |
|---|---|
| Alias | Tên entry, alias mà ứng dụng chọn |
| Entry type | Private key, trusted cert hoặc secret key |
| Certificate | Fingerprint, subject/issuer, serial, validity |
| Chain | Số lượng, danh tính và thứ tự chain phù hợp |
| Public key | Algorithm và public key khớp identity dự kiến |
| Private key | Có thể truy xuất/sử dụng bằng đúng password/provider |
| Secret key | Có thể truy xuất và thực hiện thao tác ứng dụng cần |
| Store integrity | Load thành công theo chính sách xác thực toàn vẹn |
| Runtime | JDK đích và mọi JDK rollback có quyền đọc |
| Permissions | File ownership, ACL, backup và secret delivery |

Không chỉ so sánh file size. JKS và PKCS#12 có cách mã hóa khác nhau, nên file sau convert có thể khác kích thước và checksum dù chứa cùng danh tính chứng chỉ/khóa.

### 7.2. Không chuyển đổi một cách mù quáng

Một số lý do cần dừng trước khi convert:

- Source là `JCEKS` chứa secret keys với behavior phụ thuộc provider.
- Source là PKCS11/HSM, private key không được phép export.
- Password bảo vệ key khác password store và công cụ đích có hạn chế.
- Consumer legacy chỉ được kiểm thử với JKS và chưa hỗ trợ PKCS#12.
- Rollback cần JDK cũ đọc file mới, nhưng thuật toán PKCS#12 hiện tại chưa tương thích.
- File nguồn có entry bị hỏng, certificate chain không nhất quán hoặc private key không còn sử dụng được.

Trong những tình huống này, kế hoạch có thể là giữ store cũ, thay API/provider, thay phiên bản JDK rollback hoặc chuyển khóa bằng cơ chế riêng được phép, chứ không nhất thiết ép mọi dữ liệu vào cùng một định dạng.

## 8. Kiểm chứng khả năng đọc dữ liệu cũ trên JDK đích

Cần tách ba lớp kiểm chứng:

**Lớp A — File/parser:** JDK có mở được store bằng `KeyStore.load` hoặc `keytool -list` không?

**Lớp B — Entry/key operation:** Có lấy được đúng alias, certificate chain, private/secret key và thực hiện phép toán thực tế không?

**Lớp C — Hệ thống:** TLS/mTLS, ký số hoặc giải mã dữ liệu ứng dụng có hoạt động với chính keystore đó trong runtime mới không?

Một kết quả pass ở lớp A không suy ra pass ở B hoặc C.

### 8.1. Ma trận kiểm tra một chiều và hai chiều

Giả sử hệ thống có JDK cũ A và JDK mới B:

| File đầu vào | Runtime kiểm tra | Mục tiêu |
|---|---|---|
| Keystore cũ do A tạo | JDK A | Baseline: chứng minh artifact gốc hợp lệ |
| Keystore cũ do A tạo | JDK B | Đọc dữ liệu cũ sau nâng JDK |
| Keystore mới do B tạo/chuyển | JDK B | Xác nhận cấu hình target |
| Keystore mới do B tạo/chuyển | JDK A | Xác minh rollback nếu A cần đọc file mới |
| Truststore cũ | JDK B | Kiểm tra trust anchors, policy và handshake |
| Keystore HSM/token | JDK B + provider/driver mới | Xác minh ký/giải mã mà không export key |

Nếu file sau migration là **bản sao riêng**, còn rollback dùng bản gốc cũ không bị đổi, có thể không cần JDK cũ đọc file mới. Nhưng phải chứng minh rollback sẽ dùng đúng artifact/config cũ. Nếu hệ thống ghi đè store dùng chung giữa các version, khả năng đọc hai chiều quan trọng hơn.

### 8.2. Khi có nhiều update release hoặc vendor

Không chỉ ghi “Java 8” hay “Java 17”. Ghi feature release, update/build và vendor cụ thể. Thuật toán hỗ trợ, security provider và chính sách có thể thay đổi giữa các update trong cùng một dòng JDK. Các bản vá bảo mật có thể thay default hoặc chặn các thuật toán yếu.

Ví dụ một test record:

~~~text
Artifact: client-identity-legacy.p12
Source creation environment: JDK A / provider X
Target environment: JDK B / provider Y
Type: PKCS12
Aliases: service-client, backup-client
Load: PASS
Private key retrieval: PASS
Certificate chain: PASS
mTLS handshake with test server: PASS
Legacy rollback reader: NOT YET VERIFIED
Owner: platform-security
Evidence: CI run / test report / log đã loại bỏ secret
~~~

Khi ghi nhận trạng thái, dùng “chưa xác minh” thay vì coi thiếu lỗi log là bằng chứng mọi thuật toán được hỗ trợ.

## 9. JSSE: KeyManager, TrustManager và cấu hình TLS

Trong Java Secure Socket Extension (JSSE), identity keystore thường được dùng để khởi tạo `KeyManagerFactory`, còn truststore dùng với `TrustManagerFactory`. Hai vai trò khác nhau dù cùng sử dụng `KeyStore`.

Ví dụ về cấu trúc Java:

~~~java
KeyStore identity = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(identityPath)) {
    identity.load(in, storePassword);
}

KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(identity, keyPassword);

KeyStore trust = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(trustPath)) {
    trust.load(in, trustPassword);
}

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trust);

SSLContext context = SSLContext.getInstance("TLS");
context.init(kmf.getKeyManagers(), tmf.getTrustManagers(),
             new SecureRandom());
~~~

Ví dụ giả định đã có import phù hợp (`java.io`, `java.nio.file`, `java.security`, `javax.net.ssl`) và các biến path/password được cung cấp qua secret management. Nó không chỉ định TLS version/cipher suite cụ thể; trong ứng dụng thật phải kiểm tra policy hiện hành và cấu hình client/server tương ứng.

### 9.1. Các system properties phổ biến

Một số ứng dụng cấu hình JSSE qua:

~~~text
javax.net.ssl.keyStore
javax.net.ssl.keyStoreType
javax.net.ssl.keyStorePassword
javax.net.ssl.trustStore
javax.net.ssl.trustStoreType
javax.net.ssl.trustStorePassword
~~~

Không nên bỏ qua các thuộc tính `*Type` khi chuyển từ JKS sang PKCS#12. Đồng thời, không đưa mật khẩu thật vào lệnh khởi chạy có thể bị hiển thị qua process list, diagnostic dump, script hoặc log mà chưa có cơ chế bảo vệ.

Nếu ứng dụng tự tạo `SSLContext` hoặc framework sử dụng trust manager riêng, thay đổi JSSE system properties có thể không tác động tới kết nối đó. Hãy tìm đường cấu hình thực tế thay vì dựa vào tên property “quen thuộc”.

### 9.2. Default truststore của JDK không phải truststore tùy chỉnh

JDK thường đi kèm tập CA đáng tin cậy theo cách phân phối của vendor, thường ở dạng `cacerts` trong thư mục cấu hình bảo mật của runtime. Đường dẫn, nội dung và policy có thể thay đổi theo vendor và update.

Một custom truststore không đồng nghĩa với default `cacerts`. Nếu ứng dụng cấu hình riêng `javax.net.ssl.trustStore`, nó có thể thay thế tập trust anchors được chọn bởi cơ chế mặc định của JSSE trong bối cảnh đó. Vì vậy hãy phân biệt:

- Có sử dụng default trust anchors của runtime không?
- Có truststore riêng chỉ chứa CA nội bộ không?
- Có merge trust anchors theo code hoặc provider custom không?
- Có hostname verification và trust checks đúng không?

Không nên copy nguyên `cacerts` cũ sang JDK mới chỉ để “giữ tương thích”. Cách đó có thể giữ lại CA hoặc certificate đã không còn phù hợp chính sách bảo mật. Nếu cần CA nội bộ, hãy quản lý và phân phối có kiểm soát các trust anchors được phê duyệt.

## 10. Thuật toán bảo mật: đọc được file nhưng dùng được key hay không?

Một keystore có thể chứa key và certificate sử dụng thuật toán đã bị hạn chế theo chính sách JDK mới. Các nhóm cần đánh giá:

- Algorithm và kích thước public/private key, ví dụ RSA, EC và độ dài tương ứng.
- Signature algorithm của certificate chain.
- Thuật toán PBE/MAC để bảo vệ PKCS#12 entry/file.
- TLS protocol versions và cipher suites được phép.
- Constraint trong `java.security` và chính sách của provider.
- Chính sách doanh nghiệp, FIPS hoặc ràng buộc HSM.
- Certificate chain, basic constraints, key usage và extended key usage.

Hai tình huống khác nhau:

1. **Không mở được file:** có thể do format, password, provider hoặc thuật toán bảo vệ nội dung keystore.
2. **Mở được nhưng TLS thất bại:** có thể do certificate chain, hostname, trust, key usage, disabled algorithms hoặc giao thức hai đầu không thương lượng được.

Không xử lý bằng cách tắt certificate validation hoặc mở lại hàng loạt thuật toán yếu. Phải xác minh nguyên nhân bằng thông báo lỗi, JDK security release notes, policy của tổ chức và kiểm thử liên kết thật.

### 10.1. Mật khẩu sai và thuật toán không hỗ trợ có thể biểu hiện giống nhau

Một số exception có thông điệp tổng quát hoặc có nested cause. Khi `KeyStore.load` báo lỗi “keystore password was incorrect”, không được lập tức kết luận password sai nếu file được đọc trên JDK/provider khác mà trước đó vẫn hợp lệ. Cần xem **cause chain** và thử trên baseline runtime:

- Baseline JDK mở được nhưng JDK mới không: nghi ngờ provider, format, thuật toán hoặc thay đổi chính sách.
- Cả hai JDK không mở được: kiểm tra file corruption, secret, type và nguồn artifact.
- `-list` thành công nhưng `getKey` thất bại: kiểm tra key entry password, thuật toán và provider.
- Key lấy được nhưng phép ký/TLS thất bại: kiểm tra quyền sử dụng, algorithm policy, certificate và HSM/provider.

Không thử liên tục các password đoán mò trên file hoặc token production. Token/HSM có thể có chính sách khóa tài khoản, rate limit hoặc log bảo mật.

## 11. Phân loại lỗi thường gặp

| Triệu chứng | Khả năng nguyên nhân | Bước xác minh |
|---|---|---|
| `Invalid keystore format` hoặc lỗi parse | Sai storetype, file hỏng, không phải keystore mong đợi | Xác minh metadata artifact, thử bản sao bằng JDK gốc |
| `IOException` trong `KeyStore.load` | Password, integrity/MAC, định dạng hoặc algorithm | Xem cause chain, type/provider, JDK update |
| `UnrecoverableKeyException` | Password key entry sai hoặc không thể phục hồi key | Kiểm tra alias và key password qua môi trường được cấp quyền |
| `NoSuchAlgorithmException` | Provider không có thuật toán bảo vệ/khóa | Kiểm tra provider/version/security policy |
| `KeyStoreException` về type/provider | Type không tồn tại hoặc provider chưa đăng ký | Xem `Security.getProviders()`, keystore type |
| `NoSuchProviderException` | Tên provider không được cài | Kiểm tra provider JAR/module/config |
| `CertificateException` | Lỗi parse hoặc xử lý certificate | Kiểm tra certificate chain và format |
| `KeyStore.getKey(alias) == null` | Alias không tồn tại hoặc entry không phải key entry | Liệt kê alias/entry types |
| `SSLHandshakeException` | Trust, certificate, TLS policy hoặc nhiều nguyên nhân | Test handshake với server/client đúng môi trường |
| `PKIX path building failed` | Không xây được chain tin cậy | Kiểm tra trust anchors, intermediates, chain |
| `ValidatorException` hoặc algorithm constraints | Chain/algorithm không đáp ứng chính sách | Xem policy JDK và certificate metadata |
| HSM/provider không tìm thấy key | Token, slot, PIN, provider hoặc ACL | Kiểm tra cấu hình PKCS#11/HSM và quyền |

Các thông báo cụ thể có thể thay đổi giữa JDK, provider và lớp thư viện. Bảng chỉ hỗ trợ định hướng điều tra; luôn đọc stack trace đầy đủ và xác định thao tác nào đang thất bại.

## 12. Đánh giá tương thích với phần mềm ngoài Java

Keystore đôi khi được chia sẻ với hệ thống khác: load balancer, reverse proxy, hệ thống ký số, trình duyệt, ứng dụng .NET, OpenSSL hoặc thiết bị phần cứng. PKCS#12 có tính tương tác rộng, nhưng không bảo đảm mọi phần mềm đọc được mọi thuật toán bảo vệ PKCS#12.

Nếu công cụ ngoài Java cần dùng file, hãy kiểm tra bằng đúng phiên bản và policy của công cụ đó. Ví dụ có thể dùng công cụ `openssl pkcs12` để kiểm tra metadata của file mà không xuất private key ra file:

~~~bash
openssl pkcs12 -info -in identity.p12 -noout
~~~

Công cụ có thể yêu cầu password; tùy phiên bản OpenSSL, tùy chọn xử lý các thuật toán cũ khác nhau. Với OpenSSL 3, một số file cũ cần chế độ legacy/provider phù hợp; điều đó không đồng nghĩa có thể dùng lại thuật toán yếu trong production mà không đánh giá bảo mật.

Không chạy lệnh xuất private key dạng rõ như `-nodes` vào terminal/log trong quy trình khảo sát. Nếu cần chuyển đổi khóa sang một công cụ khác, phải tuân thủ chính sách xuất khóa và bảo vệ bản xuất ở mức tương đương private key gốc.

## 13. Keystore trong container, Kubernetes và CI/CD

Khi chuyển từ ứng dụng chạy trực tiếp trên máy chủ sang container hoặc Kubernetes, rủi ro keystore không chỉ ở format.

Các điểm cần xác minh:

- File được mount vào path mà ứng dụng thực sự đọc.
- Ownership và permission cho phép đúng user/container đọc.
- Secret được cập nhật/rotate theo cơ chế đã thiết kế.
- File được tạo bằng JDK/toolchain nào; container runtime dùng JDK nào.
- Có nhiều instance đồng thời đọc file không, và chúng có cùng version?
- Có nơi nào ghi trở lại keystore khi ứng dụng khởi động hoặc tự cập nhật certificate không?
- Hot reload certificate có được hỗ trợ hay cần restart?
- File có bị copy vào container image, log artifact hoặc build cache trái chính sách không?

Không khuyến nghị bake private key production trực tiếp vào container image. Ưu tiên secret store hoặc cơ chế mount/identity provider phù hợp. Với GitOps, chỉ lưu manifest/reference, không đưa keystore kèm password vào repository.

### 13.1. Không nhầm việc mount đúng với đọc đúng

Một pod có thể thấy file ở `/run/secrets/client.p12`, nhưng `KeyStore.load` vẫn thất bại do type, password, provider hoặc thuật toán. Ngược lại, một store hợp lệ có thể được nạp nhưng SSLContext đang dùng truststore mặc định thay vì file được mount.

Cần log trạng thái đủ để chẩn đoán mà không lộ bí mật:

~~~text
keystore.type=PKCS12
keystore.source=configured-secret
keystore.alias.required=service-client
keystore.load=SUCCESS
certificate.expiry.days=...
tls.handshake=SUCCESS
~~~

Không log nội dung private key, mật khẩu, raw token PIN hoặc toàn bộ cấu hình secret. Certificate metadata công khai cũng cần xem xét rủi ro thông tin nội bộ trước khi đưa vào log tập trung.

## 14. Thực hiện migration theo các giai đoạn an toàn

### Giai đoạn 1 — Chốt baseline

- Xác định file gốc, path, checksum và nơi lưu trữ.
- Ghi JDK/vendor/update/provider đang đọc file.
- Ghi type, alias, entry types, certificate chain và cách ứng dụng lấy password.
- Chạy kiểm thử hiện tại trên bản sao trong môi trường được cấp phép.
- Lưu lại TLS/mTLS, ký số hoặc thao tác ứng dụng được coi là baseline pass.

### Giai đoạn 2 — Đọc file cũ bằng JDK mới, chưa chuyển format

Trước tiên dùng **chính file cũ** trên JDK đích. Chạy:

1. `keytool -list -v` với type được xác nhận.
2. Java `KeyStore.load` với provider mục tiêu.
3. Kiểm tra alias, entry type và chain.
4. Thử lấy private/secret key bằng đúng password và thực hiện thao tác an toàn.
5. Test TLS/mTLS hoặc ký số trên môi trường tương đương production.

Nếu bước này thành công, có thể lựa chọn **giữ nguyên file JKS cũ** trong một giai đoạn và chỉ nâng JDK, thay vì chuyển format cùng lúc. Điều đó tách rủi ro JDK khỏi rủi ro chuyển đổi dữ liệu.

### Giai đoạn 3 — Chuyển format nếu có nhu cầu

Chỉ khi có mục tiêu rõ ràng (chuẩn hóa PKCS#12, interoperable toolchain, vendor support, chính sách bảo mật), tạo bản mới:

~~~text
identity-old.jks  ->  identity-new.p12
        |                    |
        v                    v
  Giữ nguyên bản gốc     Test trên JDK đích
                             |
                             v
                       Test rollback reader
                             |
                             v
                       Chuyển cấu hình
~~~

Không xóa source ngay sau import. Giữ backup theo retention và kiểm soát khóa đã được phê duyệt. Đồng thời, ghi rõ trường hợp certificate/private key không được phép sao chép giữa môi trường.

### Giai đoạn 4 — Cập nhật cấu hình ứng dụng

Thay đổi có kiểm soát:

- Store path.
- `keyStoreType` / `trustStoreType` hoặc type ở Java API.
- Alias được chọn.
- Secret reference và cách cấp quyền đọc.
- KeyManager/TrustManager hoặc framework SSL config.
- Runtime image/container mount và permission.
- Certificate rotation/renewal pipeline.

Nếu đang dùng mTLS, hãy test cả client certificate selection và server-side trust policy, không chỉ kết nối HTTPS một chiều.

### Giai đoạn 5 — Triển khai từng phần và rollback

Rollout nên có:

- Canary hoặc môi trường staging dùng đúng artifact.
- Theo dõi lỗi TLS handshake, authentication, signing và certificate expiry.
- Bằng chứng ứng dụng dùng file mới đúng path/type.
- Điều kiện dừng hoặc rollback khi lỗi vượt ngưỡng.
- Cấu hình rollback cùng store cũ hoặc xác minh JDK cũ đọc được store mới.
- Quy trình xử lý nếu đã rotate khóa/certificate và không thể đơn giản quay lại identity cũ.

Rollback còn phụ thuộc phía đối tác. Nếu certificate mới đã được đối tác chấp nhận nhưng certificate cũ bị thu hồi, quay về artifact cũ có thể khiến mTLS thất bại. Cần phối hợp hệ thống ngoài trước khi quyết định.

## 15. Ví dụ tình huống: JKS cũ, JDK mới và rollback

Giả sử ứng dụng thanh toán dùng identity store `payment-client.jks` được tạo nhiều năm trước, có alias `client-mtls`. Nhóm dự định nâng runtime từ JDK 8 lên JDK 17 và chuyển keystore thành PKCS#12.

**Cách làm dễ sai:** đổi tên file thành `payment-client.p12`, đặt `javax.net.ssl.keyStoreType=PKCS12` và nâng JDK cùng lúc; sau đó chỉ kiểm tra service đã khởi động.

**Cách làm có bằng chứng:**

1. Trên JDK 8 gốc, xác nhận file `payment-client.jks` còn đọc được và alias `client-mtls` có đúng private key/certificate chain.
2. Trên JDK 17, thử mở file gốc với `JKS` type tường minh; thử mTLS bằng bản sao an toàn. Nếu hoạt động, có thể nâng JDK trước, chưa đổi format.
3. Dùng JDK được chọn để tạo file PKCS#12 **mới**; không ghi đè JKS gốc.
4. Đọc file mới trên JDK 17, kiểm tra alias, chain, fingerprint và key operation.
5. Nếu rollback về JDK 8 cần đọc chính file mới, kiểm tra bằng bản JDK 8 thực tế. Nếu không đọc được do thuật toán, phải điều chỉnh chiến lược rollback hoặc lựa chọn phương án được hỗ trợ thay vì âm thầm giảm bảo mật.
6. Cập nhật secret path/type, chạy end-to-end mTLS với đối tác test và xác nhận server nhận đúng client certificate.
7. Triển khai có kiểm soát; lưu artifact gốc trong kho bí mật theo retention đã được phê duyệt.

Kết quả cần ghi độc lập:

| Bài kiểm tra | Kết quả |
|---|---|
| JDK 8 đọc JKS cũ | Pass/fail với bằng chứng |
| JDK 17 đọc JKS cũ | Pass/fail với bằng chứng |
| JDK 17 đọc PKCS#12 mới | Pass/fail với bằng chứng |
| JDK 8 đọc PKCS#12 mới (nếu cần) | Pass/fail hoặc không thuộc phạm vi |
| Alias/chain/key phù hợp | Pass/fail |
| mTLS handshake | Pass/fail |
| Rollback artifact/config | Pass/fail |

Không được tự điền “PASS” chỉ vì các bước là hợp lý. Kết quả chỉ có ý nghĩa khi chạy trên đúng artifact và runtime.

## 16. Những sai lầm thường gặp

**“File đuôi .jks chắc chắn dùng JKS, đuôi .p12 chắc chắn dùng PKCS12.”** Không đúng; tên file không quyết định format thực tế.

**“Java mới vẫn đọc JKS nên không cần kiểm tra gì.”** Không đủ; việc đọc phụ thuộc JDK, provider, storetype, entry/password và thuật toán. TLS hoặc key operation vẫn có thể thất bại.

**“Đổi JKS sang PKCS#12 chỉ là đổi extension.”** Sai; cần chuyển đổi dữ liệu bằng công cụ/provider thích hợp và xác minh toàn bộ entry.

**“PKCS#12 là tiêu chuẩn nên mọi JDK đều đọc được mọi file PKCS#12.”** Không chính xác; các thuật toán bảo vệ bên trong có thể không tương thích với runtime cũ.

**“Liệt kê alias thành công tức có thể ký hoặc chạy mTLS.”** Không đủ; phải lấy được key, kiểm tra certificate chain và chạy thao tác thực tế.

**“Cứ đặt truststore mới vào JSSE thì mọi kết nối HTTPS sẽ dùng nó.”** Không chắc; framework hoặc ứng dụng có thể tạo SSLContext/TrustManager riêng.

**“Có thể copy cacerts cũ sang JDK mới để tránh lỗi CA.”** Có rủi ro giữ trust anchors hoặc chính sách cũ; cần quản lý CA được phê duyệt và kiểm tra policy của JDK đích.

**“Giảm thuật toán bảo vệ store là giải pháp tương thích mặc định.”** Không nên; phải đánh giá rủi ro bảo mật, chính sách và phương án nâng JDK cũ.

**“Không cần kiểm tra rollback vì dịch vụ đã chạy trên JDK mới.”** Chưa đủ nếu rollback cần đọc dữ liệu được ghi bằng định dạng/thuật toán mới.

**“HSM cũng là một file keystore.”** Không đúng trong nhiều trường hợp; provider/token quản lý khóa, và private key có thể không xuất được.

**“Password xuất hiện ở dòng lệnh keytool là cách kiểm tra tiện nhất.”** Không nên; secrets có thể lọt vào lịch sử shell, process list, CI logs hoặc hệ thống giám sát.

## 17. Checklist kiểm chứng dữ liệu keystore cũ

- [ ] Đã xác định tất cả keystore/truststore phục vụ runtime và build/signing.
- [ ] Đã phân biệt identity store, truststore và kho secret keys.
- [ ] Đã lưu bản gốc có kiểm soát, checksum, owner và nguồn secret.
- [ ] Đã xác định type thực tế thay vì chỉ dựa vào extension.
- [ ] Đã ghi JDK/vendor/update và security provider của baseline/target.
- [ ] Đã ghi alias, entry type, certificate chain và yêu cầu key password.
- [ ] Đã xác nhận JDK đích có thể mở file cũ bằng type/provider tường minh.
- [ ] Đã xác nhận đọc entry, private/secret key và thực hiện thao tác ứng dụng cần.
- [ ] Đã xem xét thuật toán bảo vệ file, key algorithm, certificate signature và security constraints.
- [ ] Đã kiểm tra trust anchors và không sao chép mù quáng `cacerts` cũ.
- [ ] Đã chạy TLS/mTLS hoặc ký số end-to-end khi ứng dụng có dùng.
- [ ] Nếu chuyển JKS→PKCS12, đã tạo file mới và giữ nguyên file gốc.
- [ ] Đã so sánh alias, certificate fingerprint, chain và thao tác khóa trước/sau convert.
- [ ] Đã kiểm tra PKCS#12 mới trên JDK cũ nếu rollback cần đọc nó.
- [ ] Đã cập nhật type/path/alias/secret reference trong cấu hình triển khai.
- [ ] Đã kiểm tra file permission, secret rotation, native provider và container mounts.
- [ ] Đã có kế hoạch rollback gồm cả dữ liệu khóa và tình trạng certificate ở hệ thống đối tác.
- [ ] Đã lưu báo cáo kiểm thử có kết quả rõ ràng, không tiết lộ bí mật.

## 18. Kết luận

Định dạng keystore là một phần của hợp đồng tương thích giữa **dữ liệu đã lưu**, **security provider**, **phiên bản JDK** và **ứng dụng sử dụng khóa**. Thay đổi mặc định từ JKS sang PKCS#12 ở các thế hệ JDK mới là một điểm cần chú ý, nhưng mức rủi ro không chỉ nằm ở tên định dạng. Thuật toán bảo vệ bên trong PKCS#12, entry password, alias, certificate chain, JSSE policy và cơ chế triển khai đều có thể ảnh hưởng đến khả năng đọc và sử dụng dữ liệu cũ.

Lộ trình an toàn là **kiểm kê và giữ nguyên bản gốc**, thử đọc store cũ trên runtime mới, thử key/certificate operation thật, rồi mới chuyển đổi format khi cần. Nếu có khả năng rollback, phải kiểm tra cả chiều **runtime cũ đọc dữ liệu mới** hoặc chuẩn bị một artifact/cấu hình rollback độc lập. Khi mọi kết luận đều có bằng chứng trên đúng JDK/provider và không làm lộ secrets, đội dự án có thể nâng cấp Java mà vẫn duy trì tính sẵn sàng và bảo mật của hệ thống.
