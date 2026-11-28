# Kiểm thử khả năng đọc, xác minh trên môi trường đích

Một cấu hình mật mã chỉ được xem là tương thích khi chính runtime đích có thể đọc dữ liệu, thực hiện thuật toán, xác minh chứng thư và hoàn tất giao thức theo chính sách đang bật. Việc thấy một tên thuật toán trong danh sách provider hoặc thấy một file keystore tồn tại chưa đủ để kết luận hệ thống dùng được.

Khi kiểm thử, cần dùng đúng JDK vendor, bản cập nhật, provider, security properties, truststore, hệ điều hành và cấu hình ứng dụng sẽ được triển khai. Một JDK mới có thể từ chối chứng thư, chữ ký hoặc thuật toán mà JDK cũ từng chấp nhận; ngược lại, một thuật toán có thể vẫn được provider cung cấp nhưng bị chính sách chặn tại lúc sử dụng.

JDK 26 có một thay đổi đáng chú ý: bổ sung security property **`jdk.crypto.disabledAlgorithms`** để chặn thuật toán ở tầng JCA/JCE. JDK 26 cũng bổ sung hỗ trợ PBMAC1 cho PKCS12, cảnh báo JKS/JCEKS và thay đổi một số yêu cầu thuật toán. JDK 27 tiếp tục có các thay đổi cần kiểm tra khi nâng cấp, gồm hybrid key exchange hậu lượng tử cho TLS 1.3, cách mã hóa private key ML-KEM/ML-DSA và công cụ đọc security properties đang hoạt động.

## 1. Xác định đúng runtime sẽ được kiểm thử

Trước khi kiểm tra chứng thư, khóa hoặc thuật toán, hãy ghi lại chính xác Java runtime và các công cụ đang được gọi. Trên Windows PowerShell:

    $env:JAVA_HOME
    Get-Command java, javac, keytool, jarsigner | Select-Object Name, Source
    java --version
    javac --version
    keytool -J-version
    jarsigner -J-version

Nếu ứng dụng chạy bằng service, container hoặc application server, kiểm tra executable và JAVA_HOME của chính service đó. Kết quả của terminal tương tác không chứng minh service đang dùng cùng JDK. Một máy có thể cài nhiều JDK và PATH có thể trỏ đến runtime khác với thư mục được IDE hoặc service sử dụng.

Ghi nhận ít nhất:

| Thông tin | Vì sao cần |
|---|---|
| Vendor và version đầy đủ | Oracle JDK, OpenJDK build và vendor khác có thể đóng gói provider, truststore hoặc policy khác nhau |
| Đường dẫn runtime thực tế | Xác nhận java, keytool và jarsigner thuộc cùng JDK |
| Bản cập nhật/build | Các CPU update có thể thay đổi root CA, disabled algorithms và chính sách bảo mật |
| Provider được nạp | Thuật toán có thể có ở SunJCE nhưng không có ở provider HSM hoặc provider bên thứ ba |
| Security properties | Xác định policy thực tế sau khi áp dụng file bổ sung và system property |
| Truststore/keystore | Xác định chứng thư tin cậy và khóa mà ứng dụng thật sự sử dụng |

Không dùng kết quả kiểm thử trên JDK 26 để thay cho JDK 27 hoặc ngược lại. Khi production có nhiều runtime, chạy cùng bộ kiểm thử trên từng runtime riêng.

## 2. Đọc security properties thực tế

Security properties mặc định nằm trong:

    %JAVA_HOME%\conf\security\java.security

Đây là master security properties file của JDK hiện tại. File có thể đặt provider, giới hạn thuật toán, trust manager mặc định, keystore type, chính sách độ mạnh mật mã và các thiết lập bảo mật khác.

Để xem tổng quan security settings mà runtime áp dụng:

    java -XshowSettings:security -version

Để ghi log các security properties được nạp và xử lý các chỉ thị include:

    java -Djava.security.debug=properties -version

Khi cần thử một security property trong file riêng, có thể truyền URL bằng `-Djava.security.properties=<URL>`. Cách dùng một dấu `=` sẽ nối file bổ sung vào master `java.security`; nếu dùng hai dấu `==`, file được chỉ định sẽ thay thế hoàn toàn master file. Trong bài kiểm thử thông thường, dùng cơ chế nối thêm để không vô tình làm mất cấu hình provider và security properties mặc định của JDK.

Có thể đọc một số giá trị trong chương trình:

    import java.security.Security;

    String[] names = {
        "jdk.certpath.disabledAlgorithms",
        "jdk.tls.disabledAlgorithms",
        "jdk.jar.disabledAlgorithms",
        "jdk.security.legacyAlgorithms",
        "jdk.tls.legacyAlgorithms",
        "jdk.crypto.disabledAlgorithms",
        "crypto.policy",
        "keystore.type",
        "keystore.pkcs12.macAlgorithm"
    };

    for (String name : names) {
        System.out.println(
                name + " = " + Security.getProperty(name)
        );
    }

Với `jdk.crypto.disabledAlgorithms`, JDK 26 cho phép system property cùng tên ghi đè security property. Vì vậy, nếu ứng dụng khởi chạy bằng `-Djdk.crypto.disabledAlgorithms=...`, hãy ghi nhận cả hai nguồn:

    System.out.println(
            "Security property: "
                    + Security.getProperty("jdk.crypto.disabledAlgorithms")
    );

    System.out.println(
            "System override: "
                    + System.getProperty("jdk.crypto.disabledAlgorithms")
    );

Không phải security property nào cũng được nạp lại khi ứng dụng đã chạy. Một số giá trị được đọc và cache lúc lớp bảo mật được khởi tạo. Gọi `Security.setProperty()` sau thời điểm đó có thể không thay đổi hành vi và cũng không nhất thiết ném exception. Khi kiểm thử policy, hãy cấu hình từ lúc JVM khởi động và tạo một process mới cho mỗi cấu hình.

### JDK 27: đọc property của process đang chạy

JDK 27 bổ sung lệnh chẩn đoán:

    jcmd <pid> VM.security_properties

Lệnh này in các security properties hiện tại của JVM có PID tương ứng, hữu ích khi kiểm tra ứng dụng đang chạy lâu trong production. Đây là tiện ích mới của JDK 27; không giả định lệnh tồn tại trên JDK 26. Với JDK 26, dùng `-XshowSettings:security`, `-Djava.security.debug=properties` hoặc ghi nhận Security.getProperty từ chính ứng dụng.

## 3. Phân biệt các nhóm chính sách mật mã

Không có một danh sách duy nhất quyết định mọi hoạt động mật mã của Java. Các property có phạm vi áp dụng khác nhau:

| Security property | Phạm vi chính | Điều cần kiểm tra |
|---|---|---|
| `jdk.certpath.disabledAlgorithms` | Xây dựng và xác minh đường dẫn chứng thư PKIX | Thuật toán ký chứng thư, kích thước khóa, điều kiện sử dụng và thời điểm bị từ chối |
| `jdk.tls.disabledAlgorithms` | Đàm phán TLS/DTLS trong SunJSSE | Protocol, cipher suite, key exchange, chữ ký handshake và kích thước khóa |
| `jdk.jar.disabledAlgorithms` | Xác minh chữ ký JAR | Digest, chữ ký và thuật toán/chứng thư dùng để ký JAR |
| `jdk.security.legacyAlgorithms` | Đánh dấu thuật toán yếu hoặc sắp bị hạn chế cho công cụ bảo mật | Cảnh báo từ keytool/jarsigner khi đọc, ký hoặc xác minh dữ liệu |
| `jdk.tls.legacyAlgorithms` | Đánh dấu thuật toán legacy trong TLS/DTLS | SunJSSE chỉ thương lượng nếu không còn ứng viên tốt hơn |
| `jdk.crypto.disabledAlgorithms` | Dịch vụ JCA/JCE ở tầng API | Cipher, KeyStore, MessageDigest và Signature |
| `crypto.policy` | Giới hạn độ mạnh mật mã theo jurisdiction policy | Kích thước khóa tối đa mà runtime cho phép |

Một thuật toán có thể được provider hỗ trợ nhưng bị chặn khi dùng cho một mục đích cụ thể. Ví dụ, SHA-1 có thể vẫn được cung cấp bởi MessageDigest cho một tác vụ tương thích, nhưng chứng thư ký SHA-1 có thể bị CertPath từ chối hoặc chữ ký JAR có thể bị đánh dấu là không an toàn.

Ngược lại, một thuật toán không nằm trong disabled list vẫn có thể không dùng được vì provider không triển khai, key type không phù hợp, giới hạn độ dài khóa hoặc định dạng dữ liệu không tương thích.

### Property mới của JDK 26: jdk.crypto.disabledAlgorithms

JDK 26 bổ sung `jdk.crypto.disabledAlgorithms` để giới hạn thuật toán theo tên service và tên thuật toán tại tầng JCA/JCE. Ở JDK 26, property này ban đầu không chặn thuật toán nào theo mặc định; chính sách có thể được cập nhật trong các bản JDK tương lai.

Trong JDK 26, các service được hỗ trợ ban đầu là:

- `Cipher`
- `KeyStore`
- `MessageDigest`
- `Signature`

Ví dụ cú pháp:

    jdk.crypto.disabledAlgorithms=Cipher.RSA/ECB/PKCS1Padding, MessageDigest.MD2

Giá trị trên là ví dụ minh họa phạm vi property, không phải cấu hình khuyến nghị cho mọi hệ thống. Tên service và thuật toán cần khớp tên chuẩn của Java Security Standard Algorithm Names.

Không nhầm property này với `jdk.tls.disabledAlgorithms`. Property mới chặn dịch vụ JCA/JCE cụ thể; property TLS điều khiển các thuật toán được phép thương lượng trong TLS/DTLS. Cũng không giả định property mới áp dụng cho mọi provider Java hoặc mọi service mật mã: tài liệu Oracle mô tả hành vi của JDK reference implementation và danh sách service được hỗ trợ.

### Disabled khác legacy

- **Disabled:** thuật toán bị từ chối trong phạm vi policy. Ứng dụng không thể bật lại chỉ bằng `setEnabledCipherSuites()` hoặc chỉ định tên thuật toán trong code.
- **Legacy:** thuật toán vẫn có thể được cung cấp nhưng bị đánh dấu yếu hoặc sắp bị loại bỏ. `jdk.tls.legacyAlgorithms` khiến SunJSSE chỉ thương lượng thuật toán legacy khi không còn ứng viên khác; `jdk.security.legacyAlgorithms` được keytool/jarsigner dùng để phát cảnh báo. Nếu một thuật toán legacy đồng thời bị disabled thì nó bị từ chối hoàn toàn trong phạm vi policy đó.
- **Available:** provider có implementation và policy không chặn cho thao tác đang kiểm tra. Trạng thái này vẫn không chứng minh toàn bộ giao thức hoặc chuỗi tin cậy hợp lệ.

Không xóa thuật toán khỏi disabled list chỉ để làm một kết nối cũ chạy lại. Trước hết cần xác định peer, chứng thư, provider hoặc dữ liệu nào còn phụ thuộc thuật toán đó, sau đó lập kế hoạch thay thế.

## 4. Kiểm tra provider và thực thi thuật toán thật

Có thể liệt kê provider và service đã đăng ký:

    import java.security.Provider;
    import java.security.Security;

    for (Provider provider : Security.getProviders()) {
        System.out.println(
                provider.getName() + " " + provider.getVersionStr()
        );

        for (Provider.Service service : provider.getServices()) {
            if (service.getType().equalsIgnoreCase("Cipher")
                    || service.getType().equalsIgnoreCase("Signature")
                    || service.getType().equalsIgnoreCase("MessageDigest")
                    || service.getType().equalsIgnoreCase("KeyStore")) {
                System.out.println(
                        "  " + service.getType()
                                + "." + service.getAlgorithm()
                );
            }
        }
    }

Danh sách này chỉ là bước kiểm kê. Nó không chứng minh thuật toán hoạt động với khóa, tham số, policy hoặc dữ liệu thật. Cần gọi API và thực hiện một thao tác hoàn chỉnh.

Ví dụ smoke test cho các dịch vụ thường gặp:

    import java.nio.charset.StandardCharsets;
    import java.security.KeyPair;
    import java.security.KeyPairGenerator;
    import java.security.MessageDigest;
    import java.security.SecureRandom;
    import java.security.Signature;
    import java.util.Arrays;
    import javax.crypto.Cipher;
    import javax.crypto.KeyGenerator;
    import javax.crypto.SecretKey;
    import javax.crypto.spec.GCMParameterSpec;

    public class CryptoSmokeTest {

        public static void main(String[] args) throws Exception {
            byte[] message =
                    "crypto-policy-probe".getBytes(StandardCharsets.UTF_8);

            // MessageDigest: tạo digest thực tế.
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(message);
            System.out.println("SHA-256 bytes: " + digest.length);

            // Cipher: kiểm tra AES-256-GCM bằng round trip.
            KeyGenerator keyGenerator = KeyGenerator.getInstance("AES");
            keyGenerator.init(256);
            SecretKey aesKey = keyGenerator.generateKey();

            byte[] nonce = new byte[12];
            new SecureRandom().nextBytes(nonce);

            Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
            encrypt.init(
                    Cipher.ENCRYPT_MODE,
                    aesKey,
                    new GCMParameterSpec(128, nonce)
            );
            byte[] ciphertext = encrypt.doFinal(message);

            Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
            decrypt.init(
                    Cipher.DECRYPT_MODE,
                    aesKey,
                    new GCMParameterSpec(128, nonce)
            );
            byte[] recovered = decrypt.doFinal(ciphertext);

            if (!Arrays.equals(message, recovered)) {
                throw new IllegalStateException("AES-GCM round trip failed");
            }

            // Signature: tạo và xác minh chữ ký bằng một cặp khóa tạm.
            KeyPairGenerator rsa = KeyPairGenerator.getInstance("RSA");
            rsa.initialize(3072);
            KeyPair pair = rsa.generateKeyPair();

            Signature signer = Signature.getInstance("SHA256withRSA");
            signer.initSign(pair.getPrivate());
            signer.update(message);
            byte[] signature = signer.sign();

            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(pair.getPublic());
            verifier.update(message);

            if (!verifier.verify(signature)) {
                throw new IllegalStateException("Signature verification failed");
            }

            System.out.println("AES-GCM: PASS");
            System.out.println("SHA256withRSA: PASS");
            System.out.println(
                    "Maximum AES key length: "
                            + Cipher.getMaxAllowedKeyLength("AES")
            );
        }
    }

Biên dịch và chạy trên đúng JDK đích:

    javac --release 26 -encoding UTF-8 -d out src/CryptoSmokeTest.java
    java -cp out CryptoSmokeTest

Nếu dùng JDK 27, đổi `--release 26` thành `--release 27` khi muốn biên dịch với API release 27. Chương trình chỉ dùng API ổn định; không cần preview flag.

Smoke test này kiểm tra provider, khả năng tạo khóa, khởi tạo Cipher, mã hóa/giải mã, ký/xác minh và giới hạn độ dài khóa AES. Nó không thay thế kiểm thử certificate path, TLS handshake, PKCS12 hoặc chữ ký JAR. Cũng không dùng các khóa tạm trong ví dụ làm khóa production.

### Kiểm tra chính sách chặn một thuật toán

Có thể kiểm chứng property mới trong một process thử nghiệm riêng. Ví dụ chặn SHA-256 cho service MessageDigest:

    java -Djdk.crypto.disabledAlgorithms=MessageDigest.SHA-256 -cp out CryptoSmokeTest

Kết quả mong đợi là lời gọi `MessageDigest.getInstance("SHA-256")` bị từ chối trong JDK reference implementation áp dụng property này. Ví dụ chỉ dùng để kiểm tra cơ chế policy trong môi trường lab; không chạy cấu hình đó trên production vì nhiều thư viện, giao thức và thao tác xác minh có thể phụ thuộc SHA-256.

Khi kiểm tra property này, nhớ rằng nó hỗ trợ ban đầu các service Cipher, KeyStore, MessageDigest và Signature. Đừng dùng ví dụ này để suy ra KeyPairGenerator, Mac hoặc mọi API khác cũng chịu cùng policy.

## 5. Kiểm tra độ mạnh khóa và crypto.policy

JDK 26/27 mặc định sử dụng jurisdiction policy **unlimited**. Bộ policy limited vẫn được phân phối trong JDK cho các môi trường phải giới hạn độ mạnh theo yêu cầu nhập khẩu/xuất khẩu mật mã.

Có thể kiểm tra giới hạn AES mà runtime cho phép:

    System.out.println(
            Cipher.getMaxAllowedKeyLength("AES")
    );

Trong policy unlimited, giá trị thường là giới hạn số nguyên tối đa của API. Với policy limited, giá trị có thể thấp hơn, ví dụ 128 bit cho AES.

Hai khái niệm cần phân biệt:

- `crypto.policy` giới hạn độ mạnh mật mã tối đa theo jurisdiction policy.
- `jdk.crypto.disabledAlgorithms` chặn một thuật toán cụ thể theo service và tên thuật toán.

Không chuyển sang limited chỉ để làm ứng dụng “an toàn hơn”. Chọn policy theo yêu cầu pháp lý áp dụng cho tổ chức và môi trường triển khai; hãy hỏi bộ phận phụ trách tuân thủ mật mã khi có nghĩa vụ về giới hạn xuất/nhập khẩu.

## 6. Kiểm tra KeyStore và PKCS12

PKCS12 là loại keystore mặc định và được khuyến nghị trong JDK. Nó có thể lưu private key, certificate chain và các secret entry phù hợp. Khi kiểm thử, dùng rõ `-storetype PKCS12` để tránh phụ thuộc default type của một JDK khác.

Liệt kê và đọc keystore trên runtime đích:

    keytool -list -v -keystore application.p12 -storetype PKCS12

Keytool sẽ yêu cầu mật khẩu tương tác. Khi đọc thành công, kiểm tra alias, entry type, certificate chain, ngày hết hạn, Subject/Issuer và fingerprint. Việc nạp PKCS12 bằng mật khẩu cũng kiểm tra phần integrity MAC của file. Mật khẩu sai hoặc file bị thay đổi thường làm thao tác load thất bại.

Trong ứng dụng, có thể kiểm tra bằng API:

    KeyStore keyStore = KeyStore.getInstance("PKCS12");

    try (InputStream input =
            Files.newInputStream(Path.of("application.p12"))) {
        keyStore.load(input, storePassword);
    }

    if (!keyStore.containsAlias("service-key")) {
        throw new IllegalStateException("Missing service-key alias");
    }

Sau khi load, kiểm tra entry type, certificate và key theo alias. Nếu cần dùng private key, gọi `getKey(alias, keyPassword)` rồi thực hiện một thao tác ký/xác minh bằng certificate tương ứng. Chỉ load thành công chưa chứng minh private key có thể được provider sử dụng trong tác vụ thực tế.

Không ghi mật khẩu store hoặc private-key password trong command line, script, log hay source code. Ưu tiên prompt bảo mật, secret manager hoặc cơ chế credential của môi trường triển khai.

### Kiểm thử PBMAC1 trên JDK 26+

JDK 26 bổ sung hỗ trợ PBMAC1 cho integrity protection của PKCS12. Để tạo một file kiểm thử dùng PBMAC1, đặt security property:

    keystore.pkcs12.macAlgorithm=PBEWithHmacSHA256

Có thể đặt trong file cấu hình thử nghiệm riêng, sau đó truyền file đó vào JVM chạy keytool bằng tùy chọn `-J`:

    keytool -J-Djava.security.properties=file:/C:/crypto-lab/pbmac1.security -genkeypair -alias probe -keyalg RSA -keysize 3072 -dname "CN=crypto-lab" -validity 30 -keystore probe-pbmac1.p12 -storetype PKCS12

Lệnh tạo một cặp khóa và keystore kiểm thử. Keytool hỏi mật khẩu. Đọc lại bằng đúng runtime và cấu hình:

    keytool -J-Djava.security.properties=file:/C:/crypto-lab/pbmac1.security -list -v -keystore probe-pbmac1.p12 -storetype PKCS12

Thực hiện thêm một lượt đọc bằng đúng JDK/vendor của ứng dụng đích. Nếu file cần được chia sẻ với runtime cũ hoặc một công cụ khác, kiểm tra khả năng đọc của từng bên trước khi triển khai.

Điểm cần nhớ:

- JDK 26 có hỗ trợ PBMAC1, nhưng không có nghĩa mọi PKCS12 được tạo trước đó đều tự động chuyển sang PBMAC1.
- File PKCS12 cũ tiếp tục dùng thuật toán integrity mà file đó đã được tạo với.
- Property trên điều khiển thuật toán MAC cho file PKCS12 mới được tạo trong process đó.
- Oracle ghi nhận default của `keystore.pkcs12.macAlgorithm` sẽ chuyển sang PBMAC1 trong một JDK tương lai; không giả định default đã đổi nếu chưa kiểm tra runtime đích.
- PBMAC1 không thay thế việc bảo vệ file, quản lý mật khẩu, phân quyền truy cập hoặc bảo vệ private key.

Nếu dùng OpenSSL hay công cụ ngoài Java để trao đổi PKCS12, kiểm thử đúng phiên bản công cụ. Khả năng đọc PBMAC1 phụ thuộc implementation và phiên bản, không chỉ JDK.

### Chuyển keystore JKS/JCEKS cũ sang PKCS12

JDK 26 cảnh báo khi keytool, jarsigner và KeyStore API sử dụng JKS/JCEKS. Các định dạng này dùng thuật toán cũ và được thông báo sẽ bị loại bỏ trong một bản JDK tương lai. Không dùng chúng làm định dạng mới cho hệ thống.

Nếu còn keystore cũ, chuyển một bản sao sang PKCS12:

    keytool -importkeystore -srckeystore legacy.jks -srcstoretype JKS -destkeystore migrated.p12 -deststoretype PKCS12

Sau khi chuyển:

1. Đọc file PKCS12 mới bằng đúng JDK đích.
2. So sánh alias và entry type.
3. Kiểm tra private key và certificate chain.
4. Thực hiện ký/xác minh hoặc TLS handshake với khóa đã chuyển.
5. Cập nhật cấu hình ứng dụng sang file PKCS12.
6. Chỉ lưu trữ hoặc loại bỏ file cũ theo quy trình quản lý khóa của tổ chức.

Không xóa keystore nguồn trước khi xác nhận ứng dụng và hệ thống khôi phục có thể sử dụng file mới.

## 7. Kiểm tra chứng thư và đường dẫn tin cậy

Đọc được chứng thư X.509 không đồng nghĩa chứng thư được tin cậy. Cần phân biệt:

1. **Đọc/parse:** file có cấu trúc chứng thư mà CertificateFactory hiểu được.
2. **Chữ ký và thời hạn:** chữ ký chứng thư hợp lệ, chứng thư nằm trong thời gian hiệu lực.
3. **PKIX path validation:** chuỗi nối đến trust anchor được tin cậy và đáp ứng các algorithm constraints.
4. **TLS endpoint verification:** hostname/SAN khớp endpoint và handshake hoàn tất.
5. **Revocation:** kiểm tra trạng thái thu hồi qua CRL/OCSP nếu policy yêu cầu.

Liệt kê trust anchors của JDK đang dùng:

    keytool -list -cacerts -v

Xem chứng thư server từ một endpoint:

    keytool -printcert -sslserver api.example.com:443 -v

Lệnh thứ hai hữu ích để kiểm tra certificate chain mà server trình bày. Việc đọc và hiển thị chain không thay thế một TLS handshake thành công với trust manager và hostname verification của ứng dụng.

### Kiểm tra TLS bằng chính Java client

Có thể dùng HttpClient với SSLContext mặc định để kiểm tra handshake, xác minh chain và hostname theo cấu hình JSSE của runtime:

    import java.net.URI;
    import java.net.http.HttpClient;
    import java.net.http.HttpRequest;
    import java.net.http.HttpResponse;
    import java.time.Duration;

    public class TlsTargetProbe {
        public static void main(String[] args) throws Exception {
            URI endpoint = URI.create(args[0]);

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(10))
                    .build();

            HttpRequest request = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofSeconds(20))
                    .GET()
                    .build();

            HttpResponse<Void> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.discarding()
            );

            System.out.println("HTTP status: " + response.statusCode());
            System.out.println("TLS handshake and request completed");
        }
    }

Chạy với endpoint staging hoặc endpoint thật mà ứng dụng cần gọi:

    java -cp out TlsTargetProbe https://api.example.com/health

Nếu ứng dụng sử dụng truststore riêng, SSLContext riêng, proxy, client certificate hoặc provider khác, hãy chạy probe với cùng cấu hình đó. Không dùng trust-all TrustManager hoặc tắt hostname verification để làm phép thử “pass”; những cách đó loại bỏ chính điều cần kiểm chứng.

Để xem handshake và certificate trust manager xử lý như thế nào:

    java -Djavax.net.debug=ssl:handshake,trustmanager -cp out TlsTargetProbe https://api.example.com/health

Để xem chi tiết CertPath validation:

    java -Djava.security.debug=certpath -cp out TlsTargetProbe https://api.example.com/health

Các log có thể chứa hostname, certificate metadata và thông tin môi trường. Chỉ bật trong môi trường kiểm thử hoặc phiên chẩn đoán được kiểm soát; không thu thập rồi công khai log bảo mật.

### Kiểm tra thay đổi truststore của JDK 26

JDK 26 đã loại bỏ bốn root certificate AffirmTrust không còn hoạt động khỏi `cacerts`. Ngoài ra, SunJSSE từ chối TLS server certificate được phát hành sau ngày 17-03-2026 nếu chuỗi của nó neo vào Chunghwa root CA thuộc policy bị distrust.

Vì vậy, khi một TLS handshake từng chạy được trên JDK cũ nhưng thất bại trên JDK 26/27, kiểm tra:

- Certificate chain server đang gửi.
- Root CA mà chain kết thúc.
- Ngày phát hành và ngày hết hạn của certificate.
- SAN/hostname.
- Các thuật toán chữ ký và kích thước khóa.
- Giá trị `jdk.certpath.disabledAlgorithms` và `jdk.security.caDistrustPolicies`.
- Truststore riêng có được dùng thay cho cacerts mặc định hay không.

Không khắc phục bằng cách thêm lại một root đã bị distrust hoặc nới lỏng policy mà không có quyết định của người phụ trách PKI. Cần cập nhật chứng thư/chuỗi tin cậy theo CA và chính sách đang áp dụng.

## 8. Kiểm tra chữ ký JAR và thuật toán legacy

Dùng jarsigner của JDK đích để kiểm tra JAR đã ký:

    jarsigner -verify -strict -verbose -certs application.jar

Kết quả cần xem:

- Các entry đã ký có digest khớp nội dung hiện tại hay không.
- Chữ ký có xác minh được bằng certificate trong signature block hay không.
- Certificate chain có đáng tin cậy trong môi trường đích hay không.
- Có cảnh báo thuật toán legacy, disabled algorithm hoặc certificate hết hạn hay không.
- Lệnh có báo severe warning khiến chế độ `-strict` trả lỗi hay không.

JDK sử dụng `jdk.jar.disabledAlgorithms` để quyết định thuật toán nào khiến JAR được xem như unsigned. `jdk.security.legacyAlgorithms` có thể khiến keytool/jarsigner cảnh báo về thuật toán yếu nhưng chưa bị vô hiệu hóa. Đọc toàn bộ warning, không chỉ dựa vào dòng cuối “jar verified”.

Nếu policy tổ chức yêu cầu kiểm tra thu hồi certificate khi xác minh JAR, có thể dùng:

    jarsigner -verify -strict -verbose -certs -revCheck application.jar

Tùy chọn `-revCheck` có thể tạo kết nối mạng để lấy OCSP response hoặc CRL. Vì vậy, phép thử phải chạy trong môi trường có mạng và quyền truy cập phù hợp. Không mặc định rằng jarsigner đã kiểm tra thu hồi khi chưa bật tùy chọn này.

JDK 26 hỗ trợ tạo và xác minh JAR ký bằng ML-DSA. Nếu pipeline ký JAR dùng thuật toán hậu lượng tử này, chạy cả bước sign lẫn verify bằng đúng JDK/provider đích và kiểm tra khả năng xác minh của công cụ phân phối downstream.

## 9. Kiểm tra TLS hậu lượng tử khi target là JDK 27

JDK 27 bổ sung post-quantum hybrid key exchange cho TLS 1.3. Các nhóm mới gồm:

- `X25519MLKEM768`
- `SecP256r1MLKEM768`
- `SecP384r1MLKEM1024`

`X25519MLKEM768` được bật mặc định và ưu tiên cao nhất. Việc có hỗ trợ trong client không có nghĩa handshake đã dùng nhóm này: server cũng phải hỗ trợ và hai bên phải thương lượng thành công.

Để kiểm tra nhóm thực sự được chọn, bật JSSE handshake debug:

    java -Djavax.net.debug=ssl:handshake -cp out TlsTargetProbe https://api.example.com/health

Trong log handshake TLS 1.3, tìm extension `key_share` trong ServerHello và kiểm tra named group. Ví dụ kết quả mong đợi nếu hybrid group được thương lượng:

    key_share (51):
      server_share:
        named group: x25519mlkem768

Nếu chỉ thấy X25519 hoặc nhóm cổ điển khác, kết nối có thể vẫn được mã hóa an toàn theo cấu hình hiện tại, nhưng chưa chứng minh hybrid post-quantum key exchange đã được sử dụng. Kiểm tra cả khả năng của server, proxy, load balancer, TLS inspection appliance và provider đang được dùng.

JDK 26 chưa có thay đổi JDK 27 này. Không đánh giá JDK 26 là lỗi chỉ vì nó không thương lượng `X25519MLKEM768`; hãy đối chiếu với mục tiêu runtime và policy của hệ thống.

## 10. Kiểm tra tương thích khóa ML-KEM/ML-DSA giữa JDK 26 và JDK 27

JDK 27 thay đổi định dạng PKCS #8 mặc định khi tạo private key ML-KEM và ML-DSA. JDK 27 dùng định dạng `seed`, trong khi JDK trước đó dùng dạng tương đương `expandedKey`.

JDK 27 có thể đọc các định dạng đã nêu, nhưng private key mới ở định dạng seed không được JDK cũ chấp nhận theo mặc định. Nếu cần tạo key bằng JDK 27 nhưng chuyển cho ứng dụng chạy JDK 26, phải kiểm thử tương thích định dạng.

Có thể yêu cầu JDK 27 tạo private key ở định dạng cũ bằng các property:

    -Djdk.mlkem.pkcs8.encoding=expandedKey
    -Djdk.mldsa.pkcs8.encoding=expandedKey

Các property này cần được đặt ở process thực hiện tạo hoặc translate key, trước khi thao tác KeyPairGenerator/KeyFactory. Ví dụ cấu hình khi chạy chương trình tạo key:

    java -Djdk.mlkem.pkcs8.encoding=expandedKey -Djdk.mldsa.pkcs8.encoding=expandedKey -cp out KeyGenerationProbe

Chỉ đặt property liên quan đến thuật toán mà hệ thống thực sự dùng. Sau khi tạo key, kiểm tra:

1. JDK 27 đọc lại private key vừa tạo.
2. JDK 26 đọc private key đó bằng KeyFactory tương ứng.
3. Public/private key pair thực hiện được thao tác encapsulate/decapsulate hoặc sign/verify phù hợp.
4. File PKCS #8 được trao đổi không bị thay đổi trong quá trình lưu trữ, mã hóa hoặc chuyển tải.
5. Provider của hai runtime hỗ trợ đúng algorithm parameter set.

Đừng chỉ so sánh byte encoding rồi kết luận hai khóa khác nhau về mặt mật mã. Hãy kiểm tra thao tác mật mã thực tế và định dạng được từng runtime hỗ trợ.

## 11. Kiểm tra provider bên thứ ba

Nếu ứng dụng dùng provider như HSM, PKCS#11, provider thương mại hoặc provider nội bộ, kiểm thử cả việc nạp provider lẫn thao tác thực tế.

Trong Oracle JDK 26, provider JCE bên thứ ba ký bằng certificate từ Sun JCE CA cũ đã hết hạn có thể bị từ chối với lỗi:

    java.lang.SecurityException:
    JCE cannot authenticate the provider MyProvider

Kiểm tra chữ ký JAR provider:

    jarsigner -verify -verbose -certs MyProvider.jar

Nếu certificate ký provider có tổ chức phát hành cũ là `Sun Microsystems Inc`, cần liên hệ nhà cung cấp để phát hành lại provider bằng chứng thư code-signing JCE hiện hành. Đừng tắt xác minh chữ ký provider để ép runtime nạp một JAR không còn được tin cậy.

Cũng cần kiểm tra khác biệt giữa Oracle JDK và OpenJDK/vendor build. Oracle JDK yêu cầu third-party cryptographic provider có JCE Code Signing Certificate; OpenJDK tiếp tục cho phép nạp provider bên thứ ba chưa ký. Vì vậy, một provider chạy được trong OpenJDK không tự động chứng minh sẽ nạp được trong Oracle JDK.

## 12. Các thay đổi thuật toán cần chú ý khi nâng cấp

JDK 26 loại bỏ một số thuật toán khỏi danh sách implementation requirements vì chúng không còn được khuyến nghị cho triển khai mới:

| Thuật toán/biến thể | Điều cần làm |
|---|---|
| DESede (Triple DES) | Không chọn cho dữ liệu mới; thay bằng AES-GCM hoặc thuật toán AEAD phù hợp |
| DESede/CBC và DESede/ECB | Không phụ thuộc implementation availability trong JDK tương lai |
| RSA/ECB/PKCS1Padding dùng mã hóa | Không dùng cho thiết kế mã hóa mới; ưu tiên RSA-OAEP hoặc cơ chế hiện đại phù hợp |
| SHA-1 cho chữ ký/chứng thư | Kiểm tra policy và thay bằng SHA-256 trở lên theo mục đích |
| JKS/JCEKS | Chuyển sang PKCS12 |
| Thuật toán legacy được cảnh báo | Lập kế hoạch thay thế trước khi chuyển sang trạng thái disabled |

JDK 26 đồng thời bổ sung các yêu cầu PBES2 hiện đại như `PBEWithHmacSHA256AndAES_128`, `PBEWithHmacSHA256AndAES_256` và `PBKDF2WithHmacSHA256`. Việc một thuật toán không còn là yêu cầu bắt buộc không nhất thiết có nghĩa mọi provider lập tức xóa implementation; điều đó có nghĩa ứng dụng không nên dựa vào sự hiện diện của nó để bảo đảm tính tương thích lâu dài.

Không tự sửa policy để giữ lại thuật toán cũ trước khi xác định lý do nghiệp vụ, mức rủi ro và lộ trình thay thế. Nếu phải duy trì khả năng đọc dữ liệu cũ, hãy tách đường tương thích đọc khỏi đường tạo dữ liệu mới.

## 13. Ma trận kiểm thử trên môi trường đích

Nên tạo một bộ test lặp lại được cho từng JDK/vendor trong hệ thống:

| Hạng mục | Phép thử | Bằng chứng cần lưu |
|---|---|---|
| Runtime | java --version, java.home, vendor | Version/build và đường dẫn JDK |
| Security properties | -XshowSettings:security, java.security.debug=properties | Giá trị policy và file include |
| JDK 27 runtime policy | jcmd VM.security_properties | Property của process đang chạy |
| Provider | Liệt kê provider và thực thi smoke test | Provider, thuật toán, lỗi thực tế |
| Key strength | Cipher.getMaxAllowedKeyLength và AES-256-GCM round trip | Key size tối đa và kết quả mã hóa |
| PKCS12 | keytool -list, KeyStore.load | Load integrity, alias, entry và certificate |
| PBMAC1 | Tạo PKCS12 với PBEWithHmacSHA256 rồi đọc lại | Khả năng đọc trên mọi runtime/công cụ |
| Certificate | PKIX validation và TLS handshake | Trust anchor, chain, SAN, validity, algorithm constraints |
| JAR | jarsigner -verify -strict | Chữ ký, digest, warning và trust |
| Provider JCE | Xác minh chữ ký JAR và nạp provider | Certificate code signing và provider service |
| TLS 1.3 PQ | JSSE handshake debug trên JDK 27 | Named group thực sự được thương lượng |
| ML-KEM/ML-DSA | Tạo, lưu, đọc và dùng key trên JDK 26/27 | Encoding và kết quả thao tác mật mã |

Lưu thêm log và cấu hình nhưng phải loại bỏ password, private key, PSK, token và dữ liệu nhạy cảm. Có thể ghi fingerprint SHA-256 của certificate/public key để đối chiếu giữa các môi trường mà không phải log toàn bộ bí mật.

## 14. Phân loại lỗi và hướng điều tra

| Lỗi | Nguyên nhân thường gặp | Kiểm tra tiếp |
|---|---|---|
| NoSuchAlgorithmException | Provider không có thuật toán hoặc policy chặn service/algorithm | Provider list, jdk.crypto.disabledAlgorithms, tên chuẩn và key type |
| NoSuchPaddingException | Provider không hỗ trợ padding trong transformation | Tách transformation và kiểm tra provider hỗ trợ |
| InvalidKeyException | Sai key type, key size, tham số hoặc key không hợp lệ | KeyFactory, KeyPairGenerator, provider và algorithm parameters |
| InvalidAlgorithmParameterException | Tham số không tương thích hoặc thuật toán bị giới hạn | Policy, parameter spec và provider |
| AEADBadTagException | Ciphertext/AAD/key/nonce không khớp hoặc dữ liệu bị sửa | Kiểm tra byte đầu vào, không sử dụng plaintext lỗi |
| IOException khi KeyStore.load | Password sai, integrity MAC không hợp lệ, file hỏng hoặc định dạng không được hỗ trợ | Password prompt, loại keystore, PBMAC1 và runtime |
| CertPathValidatorException | Chuỗi chứng thư không hợp lệ, policy chặn thuật toán hoặc trust anchor không phù hợp | certpath debug, root CA, validity, key size và disabled list |
| SSLHandshakeException | Không có protocol/cipher/group chung, certificate không tin cậy hoặc provider lỗi | JSSE handshake debug, named groups, signature schemes và trust manager |
| SecurityException: JCE cannot authenticate provider | JAR provider không có chữ ký được Oracle JDK tin cậy | jarsigner -verify -verbose -certs và certificate code-signing |
| JAR được xem như unsigned | Chữ ký/digest dùng thuật toán đã disabled hoặc chữ ký không hợp lệ | jarsigner -verify -strict và java.security policy |

Không gộp mọi lỗi bảo mật thành “JDK không hỗ trợ thuật toán”. Một lỗi có thể xuất phát từ provider, policy, certificate chain, định dạng, password, tham số hoặc cấu hình handshake. Hãy giữ nguyên exception cause và bật đúng loại debug cho từng lớp.

## 15. Quy trình kiểm thử trước khi phát hành

1. Chọn đúng JDK build và executable mà production sẽ chạy.
2. Thu thập security properties, provider order, truststore và crypto strength policy.
3. Chạy smoke test cho MessageDigest, Cipher, Signature và key size thực tế.
4. Kiểm tra PKCS12 bằng keytool và KeyStore API; xác minh private key/certificate nếu ứng dụng cần dùng chúng.
5. Kiểm tra certificate path và TLS handshake bằng cùng SSLContext/truststore của ứng dụng.
6. Chạy jarsigner verification với strict mode cho artifact đã ký.
7. Nếu có custom provider, xác minh chữ ký JAR và nạp provider trong đúng JDK distribution.
8. Kiểm tra PBMAC1 nếu tạo PKCS12 mới hoặc trao đổi file giữa nhiều runtime.
9. Nếu dùng ML-KEM/ML-DSA, kiểm tra định dạng PKCS #8 khi trao đổi giữa JDK 26 và 27.
10. Nếu dùng TLS trên JDK 27, xác nhận named group hybrid đã thực sự được thương lượng khi peer hỗ trợ.
11. Chạy integration test trong container/VM/service giống production, không chỉ trong terminal của developer.
12. Lưu kết quả, lỗi, policy và fingerprint; chỉ phát hành khi các phép thử bắt buộc đã pass hoặc ngoại lệ có phê duyệt rõ ràng.

Không thay đổi master `java.security` của JDK dùng chung chỉ để làm một bài test pass. Dùng một runtime hoặc security properties file riêng trong môi trường lab, sau đó khởi chạy process mới. Khi triển khai policy mới, kiểm tra ảnh hưởng đến mọi ứng dụng dùng chung runtime đó.

## 16. Checklist cuối cùng

- [ ] Đúng vendor, JDK build, JAVA_HOME và toolchain.
- [ ] Đã đọc security properties thực tế và kiểm tra system overrides.
- [ ] Đã phân biệt disabled, legacy, unavailable và unsupported.
- [ ] Đã test thao tác mật mã thật thay vì chỉ liệt kê tên provider.
- [ ] Đã kiểm tra AES key length và crypto.policy.
- [ ] Keystore mới dùng PKCS12; file cũ đã có kế hoạch chuyển đổi.
- [ ] Đã test PBMAC1 và đọc file trên mọi runtime đích cần hỗ trợ.
- [ ] Certificate chain, trust anchor, SAN và thời hạn đều hợp lệ.
- [ ] TLS handshake chạy với trust manager thật, không trust-all.
- [ ] JAR signature được kiểm tra bằng jarsigner strict.
- [ ] Third-party provider được xác thực và nạp thành công.
- [ ] ML-KEM/ML-DSA private key encoding tương thích giữa các JDK.
- [ ] JDK 27 TLS hybrid group được xác nhận qua handshake khi yêu cầu.
- [ ] Không đưa password, private key hoặc secret vào log.
- [ ] Không nới lỏng disabled algorithms để che lỗi tương thích.

## Tài liệu chính thức

- [Oracle — Security Properties File, Java SE 26](https://docs.oracle.com/en/java/javase/26/security/security-properties-file.html): file cấu hình, include, system override, `-XshowSettings:security` và debug properties.
- [Oracle — Disabled and Restricted Cryptographic Algorithms, Java SE 26](https://docs.oracle.com/en/java/javase/26/security/java-secure-socket-extension-jsse-reference-guide.html): phạm vi `jdk.certpath.disabledAlgorithms`, `jdk.tls.disabledAlgorithms` và `jdk.crypto.disabledAlgorithms`.
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): property JCE mới, PBMAC1, JKS/JCEKS warning, truststore changes, thuật toán không còn là implementation requirement và provider code signing.
- [Java Security Standard Algorithm Names, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html): tên chuẩn của Cipher, Signature, MessageDigest, PBES2, PKCS12 và các dịch vụ mật mã.
- [Oracle — JDK 26 Providers Documentation](https://docs.oracle.com/en/java/javase/26/security/oracle-providers.html): provider, thuật toán, jurisdiction policy và giới hạn khóa.
- [Oracle — Java Cryptography Architecture Reference Guide, Java SE 27](https://docs.oracle.com/en/java/javase/27/security/java-cryptography-architecture-jca-reference-guide.html): provider, KeyStore, PKCS12 và cryptographic strength settings.
- [Java SE 26 API — KeyStore](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyStore.html): load, store, kiểm tra integrity và truy cập entry.
- [Oracle — keytool Command, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html): đọc, kiểm tra, tạo và chuyển keystore.
- [Oracle — jarsigner Command, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html): xác minh chữ ký, warning, strict mode và revocation checking.
- [Oracle — Security Updates in JDK 26](https://docs.oracle.com/en/java/javase/26/migrate/security-updates.html): tổng quan thay đổi bảo mật JDK 26.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): ML-KEM/ML-DSA PKCS #8 encoding, `jcmd VM.security_properties`, TLS certificate compression và các thay đổi TLS.
- [JDK 27 Release Notes — TLS Hybrid Key Exchange](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): các named group hybrid và cách xác nhận nhóm thực tế trong ServerHello.
- [RFC 9180 — Hybrid Public Key Encryption](https://www.rfc-editor.org/rfc/rfc9180.html): tiêu chuẩn HPKE; tham khảo khi kiểm thử dịch vụ HPKE dùng trong ứng dụng.
- [Oracle — Java Cryptographic Roadmap](https://www.java.com/en/configure_crypto.html): trạng thái cập nhật thuật toán và chính sách mật mã trên các JDK release.

Chính sách mật mã cần được kiểm tra trên đúng runtime và provider sẽ triển khai. Với JDK 26, điểm mới cần kiểm tra riêng là `jdk.crypto.disabledAlgorithms` và PBMAC1 cho PKCS12. Khi target là JDK 27, bổ sung kiểm thử hybrid TLS và encoding ML-KEM/ML-DSA. Chỉ kết luận tương thích sau khi dữ liệu thực tế được đọc, thao tác mật mã hoàn tất và certificate/JAR/TLS được xác minh bằng chính cấu hình production.
