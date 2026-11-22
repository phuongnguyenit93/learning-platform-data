# Kiểm tra cấu hình thuật toán hiện hành thay vì sao chép mặc định cũ (Java 9+)

## Mục tiêu

Trong ứng dụng Java sử dụng mật mã, việc một thuật toán **được JDK hoặc provider hỗ trợ** không chứng minh rằng thuật toán đó phù hợp với yêu cầu bảo mật hiện tại. Mặc định của JDK, các security provider, chính sách giới hạn thuật toán và giao thức TLS có thể thay đổi giữa các bản cập nhật, nhà phân phối JDK, hệ điều hành và môi trường chạy.

Sau bài học, bạn có thể:

- Phân biệt **thuật toán được cung cấp**, **thuật toán được phép trong một ngữ cảnh** và **thuật toán đã được ứng dụng lựa chọn**.
- Đọc cấu hình `java.security` và các thuộc tính hạn chế quan trọng mà không tùy tiện sửa các mặc định đang được bảo trì.
- Kiểm tra provider, transformation mã hóa, độ dài khóa được chính sách cho phép và thiết lập TLS đang hiệu lực.
- Viết một chương trình kiểm tra Java 17+ độc lập và tự kiểm chứng hành vi mật mã bằng một phép thử AES-GCM.
- Thiết lập quy trình đánh giá cấu hình sau khi cập nhật JDK, thay provider, thay truststore hoặc triển khai sang máy chủ khác.

**Phạm vi:** Đây là bài về **kiểm tra và lựa chọn cấu hình mật mã hiện hành** trong Java Standard Cryptography Architecture (JCA/JCE/JSSE), phù hợp cho người học Java 9 trở lên. Các ví dụ dùng API chuẩn còn được duy trì; không dùng mẫu cấu hình lỗi thời để khuyên triển khai mới.

## 1. Vì sao không sao chép nguyên cấu hình từ dự án cũ?

Một đoạn mã như sau không mô tả đầy đủ yêu cầu bảo mật:

```java
Cipher cipher = Cipher.getInstance("AES");
```

Tham số `"AES"` **chưa chỉ định mode và padding**. Provider được chọn có quyền sử dụng transformation mặc định, và mặc định đó có thể không phù hợp với bài toán. Khi mã hóa dữ liệu mới, hãy chủ động chọn transformation đầy đủ, chẳng hạn `"AES/GCM/NoPadding"`, cùng cách quản lý khóa, nonce và tag có xác thực.

Cũng không nên sao chép một danh sách cipher suite, một danh sách provider, khóa mẫu, hay giá trị `jdk.tls.disabledAlgorithms` lấy từ máy khác rồi cho rằng môi trường hiện tại giống hệt. Những quyết định đó phụ thuộc vào yêu cầu hệ thống và runtime thực tế.

Một cấu hình cần được xem theo **bốn lớp**:

| Lớp | Câu hỏi phải trả lời | Công cụ kiểm chứng |
| --- | --- | --- |
| **Runtime** | Đang chạy JDK nào, bản vá nào, trên môi trường nào? | `java -version`, `Runtime.version()`, `java.home` |
| **Provider** | Nhà cung cấp thực thi thuật toán nào? Thứ tự provider ra sao? | `Security.getProviders()`, `getInstance(...).getProvider()` |
| **Chính sách** | Thuật toán/độ dài khóa/giao thức nào bị hạn chế trong từng ngữ cảnh? | `Security.getProperty(...)`, `Cipher.getMaxAllowedKeyLength(...)`, cấu hình của provider |
| **Ứng dụng** | Code yêu cầu transformation, key size, TLS protocol và chứng thư thế nào? | Xem code/config, thử chức năng thật, kiểm tra kết quả handshake |

**Nguyên tắc:** `getInstance(...)` thành công mới chứng minh có implementation cho yêu cầu đó; **chưa** chứng minh thuật toán đáp ứng chính sách bảo mật nghiệp vụ, chưa chứng minh toàn bộ giao dịch TLS sẽ thành công, và chưa xác nhận cấu hình trên production.

## 2. Cấu hình bảo mật Java được lấy từ đâu?

Java dùng lớp `java.security.Security` để quản lý các **security properties** và danh sách security provider. Một vị trí cấu hình thông dụng trên JDK hiện đại là:

```text
<JAVA_HOME>/conf/security/java.security
```

Đây là vị trí điển hình của JDK, không phải tên đường dẫn tuyệt đối áp dụng cho mọi nhà phân phối. Các chính sách có thể bị ảnh hưởng bởi file thuộc tính bổ sung, môi trường, profile và các thiết lập mà ứng dụng khởi tạo từ sớm.

Một số thuộc tính hữu ích khi rà soát:

| Security property | Mục đích kiểm tra |
| --- | --- |
| `security.provider.n` | Thứ tự ưu tiên các provider khi code không chỉ định provider cụ thể. |
| `jdk.tls.disabledAlgorithms` | Hạn chế các thuật toán, giao thức, key exchange hoặc cipher suite trong JSSE/TLS. |
| `jdk.certpath.disabledAlgorithms` | Hạn chế các thuật toán và độ dài khóa khi kiểm tra đường dẫn chứng thư. |
| `jdk.jar.disabledAlgorithms` | Hạn chế thuật toán dùng để kiểm tra chữ ký JAR. |
| `crypto.policy` | Chính sách mật mã mà runtime hỗ trợ, nếu bản JDK có cấu hình thuộc tính này. |

Các giá trị trên là **ví dụ tên thuộc tính để kiểm tra**, không phải các giá trị mặc định cố định phải chép vào file. Đọc giá trị **thực tế** bằng:

```java
String disabledTls = Security.getProperty("jdk.tls.disabledAlgorithms");
String disabledCertPath =
        Security.getProperty("jdk.certpath.disabledAlgorithms");
```

`Security.getProperty(...)` là API đọc security property. `System.getProperty(...)` chỉ đọc **system property**, là một không gian tên khác; không thay chúng cho nhau khi cần kiểm tra chính sách bảo mật.

Không nên lấy nội dung `java.security` trên một máy rồi ghi đè toàn bộ ở máy khác. Việc đó dễ làm mất thay đổi bảo mật mới hoặc thay đổi thứ tự provider. Nếu tổ chức cần chính sách tùy chỉnh, dùng cơ chế cấu hình được JDK đang chạy hỗ trợ, đặt trước khi các thành phần bảo mật được khởi tạo, quản lý file bằng kiểm soát phiên bản và kiểm thử sau mỗi cập nhật.

## 3. Kiểm tra thuật toán và provider đang hoạt động

JCA/JCE cung cấp nhiều kiểu dịch vụ:

| Dịch vụ | API | Mục đích |
| --- | --- | --- |
| Tạo dữ liệu ngẫu nhiên bảo mật | `SecureRandom` | Nonce, salt, vật liệu ngẫu nhiên cần CSPRNG. |
| Băm mật mã | `MessageDigest` | Ví dụ SHA-256 cho hash nội dung, checksum bảo mật khi ngữ cảnh phù hợp. |
| Mã xác thực thông điệp | `Mac` | Ví dụ `HmacSHA256` với khóa bí mật. |
| Mã hóa/giải mã | `Cipher` | Ví dụ `AES/GCM/NoPadding` cho mã hóa có xác thực. |
| Chữ ký số | `Signature` | Ví dụ `Ed25519` khi provider/hệ thống tương thích. |
| Sinh khóa | `KeyGenerator`, `KeyPairGenerator` | Tạo khóa theo loại, độ dài và chính sách đã chọn. |
| TLS | `SSLContext`, `SSLParameters` | Cấu hình protocol, cipher suite và thành phần tin cậy cho TLS. |

Để biết **provider thực sự được chọn**, dùng đối tượng nhận được từ `getInstance`:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
String chosenProvider = cipher.getProvider().getName();
```

Lưu ý:

- `Security.getProviders()` trả danh sách provider theo thứ tự ưu tiên. Thứ tự này ảnh hưởng đến lựa chọn implementation nếu không chỉ rõ provider.
- `Security.getAlgorithms("Cipher")` có thể dùng để xem các tên thuật toán được đăng ký, nhưng danh sách đó **không nhất thiết liệt kê mọi transformation hoàn chỉnh**. Thử đúng `Cipher.getInstance("AES/GCM/NoPadding")` là cách phù hợp để xác định yêu cầu cụ thể có implementation hay không.
- Một tên thuật toán xuất hiện trong provider có thể vẫn không được phép trong **TLS**, **xác thực chứng thư** hoặc **chữ ký JAR** do các chính sách riêng của những thành phần đó.
- Đừng mặc định ép dùng `SunJCE` hoặc provider của một hãng nếu ứng dụng không có yêu cầu được xác minh; việc cố định provider có thể gây lỗi khi chuyển runtime, FIPS provider hoặc HSM.

## 4. Chương trình kiểm tra thực tế, chạy độc lập bằng Java 17+

Ví dụ này chỉ **đọc trạng thái runtime**, không sửa security properties và không kết nối mạng. Nó kiểm tra chính xác các dịch vụ mà một ứng dụng có thể cần, in provider đã được chọn và phân biệt các protocol TLS **mặc định được bật** với những protocol **được implementation hỗ trợ**.

Lưu thành file `CryptoConfigAudit.java`:

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.Provider;
import java.security.SecureRandom;
import java.security.Security;
import java.security.Signature;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.net.ssl.SSLContext;

public final class CryptoConfigAudit {

    @FunctionalInterface
    interface Probe {
        Provider provider() throws GeneralSecurityException;
    }

    private static void show(String label, Probe probe) {
        try {
            System.out.println(label + "=" + probe.provider().getName());
        } catch (GeneralSecurityException e) {
            System.out.println(label + "=UNAVAILABLE("
                    + e.getClass().getSimpleName() + ")");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("jdk=" + Runtime.version().feature());

        String providerOrder = String.join(",",
                Arrays.stream(Security.getProviders())
                        .map(Provider::getName)
                        .toList());
        System.out.println("providers=" + providerOrder);

        for (String key : List.of(
                "jdk.tls.disabledAlgorithms",
                "jdk.certpath.disabledAlgorithms",
                "jdk.jar.disabledAlgorithms")) {
            System.out.println(key + "="
                    + Objects.toString(Security.getProperty(key), "(not set)"));
        }

        show("AES/GCM/NoPadding",
                () -> Cipher.getInstance("AES/GCM/NoPadding")
                        .getProvider());
        show("SHA-256",
                () -> MessageDigest.getInstance("SHA-256").getProvider());
        show("HmacSHA256",
                () -> Mac.getInstance("HmacSHA256").getProvider());
        show("Ed25519",
                () -> Signature.getInstance("Ed25519").getProvider());
        show("DRBG",
                () -> SecureRandom.getInstance("DRBG").getProvider());

        System.out.println("AES policy max key length="
                + Cipher.getMaxAllowedKeyLength("AES"));

        SSLContext tls = SSLContext.getInstance("TLS");
        tls.init(null, null, null);

        System.out.println("TLS default protocols="
                + Arrays.toString(
                        tls.getDefaultSSLParameters().getProtocols()));
        System.out.println("TLS supported protocols="
                + Arrays.toString(
                        tls.getSupportedSSLParameters().getProtocols()));
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```sh
javac --release 17 -encoding UTF-8 CryptoConfigAudit.java
java CryptoConfigAudit
```

**Đầu ra phụ thuộc môi trường**: số phiên bản JDK, provider, giá trị các thuộc tính và danh sách giao thức có thể khác trên máy của bạn. Ví dụ, đoạn sau là **trích một phần đầu ra đã quan sát khi thử trên OpenJDK 24**, không phải mặc định phải áp dụng:

```text
jdk=24
AES/GCM/NoPadding=SunJCE
SHA-256=SUN
HmacSHA256=SunJCE
Ed25519=SunEC
DRBG=SUN
AES policy max key length=2147483647
TLS default protocols=[TLSv1.3, TLSv1.2]
```

Chương trình thực còn in thứ tự provider, các thuộc tính hạn chế và danh sách giao thức được hỗ trợ. `UNAVAILABLE(...)` cho biết không lấy được một implementation bằng API đang thử; cần kiểm tra runtime/provider rồi đối chiếu với yêu cầu dự án.

**Cách diễn giải, tránh kết luận sai:**

1. `Cipher.getInstance("AES/GCM/NoPadding")` thành công: transformation tồn tại. Chưa chứng minh key, IV/nonce và tag của ứng dụng được sử dụng đúng.
2. `Cipher.getMaxAllowedKeyLength("AES")` trả `2147483647` trên một số JDK với chính sách không giới hạn: đây là **giới hạn cấp chính sách** (trong trường hợp này được biểu diễn bằng `Integer.MAX_VALUE`), **không có nghĩa** AES nhận khóa dài hàng tỷ bit. Khóa thực vẫn phải có độ dài hợp lệ và được provider hỗ trợ.
3. `SSLContext.getDefaultSSLParameters().getProtocols()` mô tả giao thức mặc định của context; `getSupportedSSLParameters().getProtocols()` có thể gồm giao thức không được bật hoặc bị hạn chế. **Không coi “supported” = “allowed for production”.**
4. `SSLContext.getInstance("TLS")` và `init(...)` trong ví dụ **không tạo TLS handshake**. Chưa có bằng chứng kiểm tra chứng thư, hostname, phiên bản negotiated hay cipher suite được chọn của kết nối thật.
5. `Security.getProperty(key) == null` có thể có nghĩa thuộc tính không hiện diện theo implementation/cấu hình hiện tại; **không được suy ra** rằng thuật toán tương ứng được phép hoặc môi trường an toàn.
6. `SecureRandom.getInstance("DRBG")` chỉ là phép dò provider hỗ trợ DRBG, không khẳng định mọi ứng dụng phải chọn chuỗi `"DRBG"`. `new SecureRandom()` cũng là API CSPRNG hợp lệ khi được provider phù hợp cung cấp; chọn theo chính sách và yêu cầu vận hành.

## 5. Chọn cấu hình mã hóa hiện hành và kiểm chứng hoạt động

Đối với **mã hóa dữ liệu thông thường** cần bảo mật và kiểm tra tính toàn vẹn, AEAD như **AES-GCM** là một lựa chọn được duy trì trong JCA/JCE. Một phép thử tối thiểu cần xác nhận:

- Chọn transformation đầy đủ `AES/GCM/NoPadding`.
- Tạo khóa AES bằng `KeyGenerator` và nguồn ngẫu nhiên bảo mật cho nonce.
- Sử dụng `GCMParameterSpec` chỉ rõ độ dài authentication tag.
- Giải mã trả đúng dữ liệu ban đầu; ciphertext/tag bị sửa phải bị từ chối.

Ví dụ sau **chạy độc lập**, tạo khóa tạm và nonce ngẫu nhiên cho **một** phép mã hóa; không lưu trữ hay in khóa.

Lưu thành `CryptoSelfTest.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class CryptoSelfTest {
    public static void main(String[] args) throws Exception {
        KeyGenerator keys = KeyGenerator.getInstance("AES");
        keys.init(128);
        SecretKey key = keys.generateKey();

        byte[] iv = new byte[12];
        new SecureRandom().nextBytes(iv);
        GCMParameterSpec parameters = new GCMParameterSpec(128, iv);

        byte[] input = "kiem tra".getBytes(StandardCharsets.UTF_8);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(Cipher.ENCRYPT_MODE, key, parameters);
        byte[] ciphertext = encrypt.doFinal(input);

        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(Cipher.DECRYPT_MODE, key, parameters);
        if (!Arrays.equals(input, decrypt.doFinal(ciphertext))) {
            throw new AssertionError("Round trip failed");
        }
        System.out.println("AES-GCM round-trip: PASS");

        ciphertext[ciphertext.length - 1] ^= 1;

        Cipher verify = Cipher.getInstance("AES/GCM/NoPadding");
        verify.init(Cipher.DECRYPT_MODE, key, parameters);
        try {
            verify.doFinal(ciphertext);
            throw new AssertionError("Tamper undetected");
        } catch (AEADBadTagException expected) {
            System.out.println("AES-GCM tamper detection: PASS");
        }
    }
}
```

Chạy:

```sh
javac --release 17 -encoding UTF-8 CryptoSelfTest.java
java CryptoSelfTest
```

**Đầu ra chính xác trên JDK/provider hỗ trợ AES-GCM:**

```text
AES-GCM round-trip: PASS
AES-GCM tamper detection: PASS
```

Ví dụ đã được kiểm tra với OpenJDK 24. Nó cho thấy quá trình mã hóa/giải mã và phát hiện sửa đổi hoạt động; **không phải một định dạng lưu trữ ciphertext hoàn chỉnh**.

Khi đưa AES-GCM vào ứng dụng thực:

- **Tuyệt đối không tái sử dụng cặp (key, IV/nonce) để mã hóa.** IV ngẫu nhiên dài 12 byte trong ví dụ chỉ dùng một lần; ứng dụng có lưu lượng lớn cần chính sách phân bổ nonce và giới hạn số lần mã hóa trên mỗi khóa rõ ràng.
- Lưu IV cùng ciphertext/tag để giải mã; bảo vệ và quản lý khóa ở vị trí thích hợp (KMS/HSM hoặc kho khóa được kiểm soát), **không** lưu khóa bí mật công khai cùng payload.
- Nếu có AAD (additional authenticated data), truyền **cùng dữ liệu AAD** và đúng thứ tự trước `doFinal` ở cả hai phía.
- Không bỏ qua `AEADBadTagException`; lỗi có thể do ciphertext, tag, khóa, IV hoặc AAD sai. Không dùng dữ liệu plaintext chưa qua kiểm tra tag.
- Dùng độ dài khóa do chính sách bảo mật phê duyệt và provider thực sự hỗ trợ. AES-128 và AES-256 là hai lựa chọn được sử dụng hiện nay tùy mô hình đe dọa; đừng chọn kích thước bằng cách chép một ví dụ cũ.

## 6. Kiểm tra TLS: “hỗ trợ”, “bật”, “được phép” và “đã thương lượng”

TLS là ví dụ điển hình cho việc không thể đoán chính sách từ tên thuật toán.

```text
Provider JSSE có khả năng hỗ trợ protocol/cipher suite
                    |
                    v
Security properties chặn lựa chọn không phù hợp
                    |
                    v
SSLContext / SSLParameters xác định lựa chọn bật ban đầu
                    |
                    v
Application server/client cấu hình hoặc ghi đè các lựa chọn
                    |
                    v
TLS handshake + peer + chứng thư quyết định kết quả thực
```

Các API hữu ích:

```java
SSLContext context = SSLContext.getInstance("TLS");
context.init(null, null, null);

String[] enabled =
        context.getDefaultSSLParameters().getProtocols();
String[] supported =
        context.getSupportedSSLParameters().getProtocols();
```

Lưu ý trong một số JSSE implementation, “disabled algorithms” vẫn nằm trong danh sách được báo cáo là **supported**, nhưng không thể dùng để thương lượng handshake theo chính sách. Vì vậy **không dùng một danh sách `supported` để tự bật toàn bộ giao thức**. Với ứng dụng mới, TLS 1.3 là lựa chọn ưu tiên khi cả hai đầu hỗ trợ; TLS 1.2 chỉ dùng khi đáp ứng yêu cầu tương thích và chính sách cipher suite hiện hành.

Để xác định hoạt động thật, cần kiểm tra ở **nơi tạo kết nối**:

1. Client/server đang dùng `SSLContext`, trust manager, key manager nào?
2. Trên socket/engine thực, `getEnabledProtocols()` và `getEnabledCipherSuites()` là gì?
3. Khi handshake thành công, `SSLSession.getProtocol()` và `getCipherSuite()` báo giá trị nào?
4. Chuỗi chứng thư có được kiểm tra hợp lệ không? Client có bật xác minh hostname (HTTPS endpoint identification) không?
5. Chính sách `jdk.tls.disabledAlgorithms` và `jdk.certpath.disabledAlgorithms` có ngăn lựa chọn không được phép hay không?

**Không bỏ kiểm tra hostname hoặc trust chain để làm cho kiểm thử “PASS”.** `SSLContext.getInstance("TLS")` không tự chứng minh ứng dụng thực tế kiểm tra danh tính máy chủ đúng cách; thư viện HTTP/connector và cấu hình endpoint phải được đánh giá trong từng luồng.

Không gửi dữ liệu nhạy cảm hay khóa riêng ra log khi làm kiểm toán TLS. Những thông tin như protocol, cipher suite, issuer fingerprint và lý do handshake thất bại thường đủ hữu ích để phân tích.

## 7. Mỗi mục đích có tiêu chí lựa chọn thuật toán riêng

“Thuật toán mạnh” không phải một tùy chọn dùng được cho mọi mục đích. Lựa chọn điển hình được kiểm chứng theo nhu cầu:

| Nhu cầu | Ví dụ hướng tiếp cận hiện hành | Phải xác minh |
| --- | --- | --- |
| Bảo mật dữ liệu khi lưu/truyền ở cấp ứng dụng | AES-GCM có xác thực | Mode, kích thước khóa, nonce duy nhất theo khóa, tag, quản lý khóa |
| Bảo mật dữ liệu khi truyền qua mạng | TLS 1.3 hoặc TLS 1.2 với bộ mã được phê duyệt | Phiên bản thương lượng thật, cipher suite, chứng thư/hostname |
| Kiểm tra tính toàn vẹn có khóa | HMAC với SHA-256 hoặc họ SHA-2 phù hợp | Khóa bí mật, cách tạo/xoay khóa, xác minh MAC đúng cách |
| Hash dữ liệu không bí mật | SHA-256 hoặc SHA-3 theo yêu cầu | Không nhầm hash với mã xác thực hoặc hash mật khẩu |
| Chữ ký số | Ed25519 hoặc thuật toán chữ ký hiện hành đã được chính sách chấp thuận | Loại khóa, provider hỗ trợ, xác thực public key, hệ sinh thái tương thích |
| Sinh số ngẫu nhiên cho mật mã | `SecureRandom` / DRBG đã được kiểm chứng | Provider, entropy, yêu cầu tính dự đoán, lỗi khởi tạo |
| Dẫn xuất khóa từ mật khẩu | KDF chuyên dụng được tổ chức phê duyệt | Salt, work factor có hiệu chỉnh, quản lý bí mật và thư viện phù hợp |

Đặc biệt, **không băm mật khẩu trực tiếp bằng `MessageDigest.getInstance("SHA-256")` rồi lưu hash**. Hash nhanh phù hợp nhiều mục đích khác, nhưng lưu mật khẩu cần một password hashing/KDF thích hợp, salt riêng và tham số công việc được hiệu chỉnh. JDK có các API PBE/PBKDF2; chọn cấu hình theo tiêu chuẩn bảo mật và hệ thống xác thực đang dùng, thay vì chép một iteration count không có cơ sở.

Việc provider hỗ trợ một thuật toán **không đồng nghĩa** tổ chức đã phê duyệt thuật toán đó. Nếu có yêu cầu FIPS, KMS, HSM hoặc chứng nhận chuyên ngành, phải đánh giá module và cấu hình thực tế, không suy ra từ tên provider.

## 8. Lập hồ sơ quyết định mật mã thay vì lưu “mặc định đẹp”

Với từng chức năng dùng mật mã, nên lưu **quyết định cụ thể, có thể kiểm tra**, chẳng hạn:

| Trường thông tin | Ví dụ nội dung cần ghi |
| --- | --- |
| Tác vụ | Mã hóa trường dữ liệu cá nhân trong database |
| Transformation | `AES/GCM/NoPadding` |
| Key length | 128 hoặc 256 bit, theo tiêu chuẩn được phê duyệt |
| Quản lý khóa | KMS/HSM hoặc kho khóa được quản trị |
| Nonce/tag | Quy tắc sinh nonce không lặp theo key; tag 128 bit |
| Provider thực thi | Lấy từ runtime được triển khai, không giả định tên |
| Chứng cứ | Chạy self-test, tamper test và kiểm tra giải mã trên artifact thật |
| Phiên bản môi trường | JDK distribution, build, runtime image/container |
| Người duyệt và thời điểm rà soát | Gắn với release, nâng cấp JDK hoặc thay đổi yêu cầu bảo mật |

Trong hồ sơ, có thể ghi **yêu cầu bắt buộc** (ví dụ “phải có AES/GCM/NoPadding”) và **kết quả quan sát** (ví dụ “đang dùng provider A trên runtime B”) ở hai trường khác nhau. Khi nâng cấp hệ thống, giá trị quan sát được có thể đổi, còn yêu cầu phải được đánh giá lại một cách có chủ đích.

## 9. Quy trình kiểm tra trong dự án thật

### Bước 1 — Xác định runtime đang triển khai

Trên máy/container chạy đúng artifact:

```sh
java -version
```

Kiểm tra thêm `JAVA_HOME`, đường dẫn executable thực, tên JDK distribution và JDK build trong pipeline. Đừng kiểm thử bản JDK của IDE rồi suy ra container production đang dùng phiên bản tương tự.

### Bước 2 — Lấy snapshot các thuộc tính và provider

Chạy `CryptoConfigAudit` của mục 4 trong môi trường tương đương production. Ghi lại hash/tên phiên bản của runtime, thứ tự provider, các giới hạn có liên quan và implementation thực thi. Snapshot này là **chứng cứ quan sát**, không phải template để ghi đè mặc định của mọi máy.

### Bước 3 — Đối chiếu với yêu cầu nghiệp vụ

Với từng chỗ dùng `Cipher`, `Mac`, `Signature`, `MessageDigest`, `SecureRandom`, TLS hoặc `KeyStore`, liệt kê thuật toán yêu cầu, tham số, key size, provider được chọn và cách quản lý khóa. Phân biệt mục đích hash dữ liệu, hash mật khẩu, chữ ký số và xác thực thông điệp.

### Bước 4 — Kiểm thử khả năng thực thi

Dùng `getInstance` cho các thuật toán/transformation bắt buộc và tạo một thử nghiệm hành vi. Ví dụ `CryptoSelfTest` giúp chứng minh AES-GCM mã hóa/giải mã và phát hiện sửa dữ liệu trong runtime hiện tại.

Riêng TLS phải có kiểm thử tích hợp đến **endpoint được kiểm soát** và đọc protocol/cipher suite đã thương lượng; chỉ nhìn thông tin `SSLContext` là chưa đủ.

### Bước 5 — Đánh giá ngoại lệ và các trường hợp lỗi

Kế hoạch kiểm thử nên có:

- Provider hoặc transformation bắt buộc không tồn tại: ứng dụng báo lỗi khởi động/cấu hình rõ ràng, không âm thầm chọn một thuật toán khác.
- Độ dài khóa không được chấp nhận: dừng có thông báo phù hợp, không tự giảm độ dài khóa.
- Payload mã hóa bị thay đổi, sai tag hoặc sai khóa: giải mã thất bại; không sử dụng dữ liệu chưa được xác thực.
- Server dùng protocol/cipher suite bị cấm hoặc chứng thư không hợp lệ: TLS handshake thất bại đúng chính sách.
- Sau cập nhật JDK, có thay đổi security properties hoặc provider: thực hiện kiểm thử hồi quy, phân tích các thay đổi trước khi phát hành.

### Bước 6 — Quản lý và cập nhật có kiểm soát

So sánh snapshot giữa các runtime và bản phát hành; tham khảo security release notes của JDK đang dùng. Nếu một kết nối hỏng sau cập nhật, cần tìm nguyên nhân thực (chứng thư, thuật toán, khóa, TLS phiên bản, truststore, handshake), không vội nới lỏng `jdk.*.disabledAlgorithms` để làm ứng dụng chạy trở lại.

Các thay đổi bảo mật phải được review, chạy kiểm thử tương thích có giới hạn và có kế hoạch loại bỏ các phụ thuộc không đáp ứng chính sách. Tránh việc “sửa tạm” bằng tắt xác thực chứng thư/hostname hoặc thay thuật toán mà không đánh giá hệ quả.

## 10. Lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Điều đúng cần nhớ |
| --- | --- |
| “Code gọi `Cipher.getInstance("AES")` chạy được nên cấu hình an toàn.” | Chưa rõ mode/padding; phải chỉ định đầy đủ transformation và tham số thích hợp. |
| “`Security.getAlgorithms(...)` liệt kê thuật toán, vậy mọi thuật toán đều được phê duyệt.” | Danh sách thể hiện provider đăng ký service; chính sách cho từng mục đích có thể chặn hoặc không cho dùng. |
| “`getSupportedSSLParameters()` là các protocol được phép triển khai.” | `supported` khác `enabled`, khác `được phép theo chính sách` và khác `đã thương lượng`. |
| “`Cipher.getMaxAllowedKeyLength("AES")` lớn thì AES nhận khóa dài tùy ý.” | Đó là giới hạn chính sách; provider/thuật toán vẫn yêu cầu key length hợp lệ. |
| “Dùng SHA-256 cho mọi trường hợp có chữ ‘hash’.” | Hash thông thường, MAC, chữ ký và lưu mật khẩu có yêu cầu khác nhau. |
| “Cấu hình JDK ở máy phát triển là mặc định production.” | Cần đo trên đúng runtime image, JDK build, provider và app config đã triển khai. |
| “Nới `jdk.tls.disabledAlgorithms` là cách sửa TLS nhanh.” | Có thể tái cho phép điều không phù hợp; phải sửa tương thích và kiểm tra nguyên nhân. |
| “Chỉ cần một test AES-GCM là đủ cho an toàn toàn hệ thống.” | Cần quản lý khóa/nonce, kiểm thử lỗi, TLS, chứng thư và vận hành thực tế. |

## 11. Checklist trước khi phát hành

- [ ] Ghi nhận JDK vendor, version/build và artifact/runtime image thực.
- [ ] Xác minh thứ tự provider, các thuật toán bắt buộc và transformation đầy đủ.
- [ ] Đọc `jdk.tls.disabledAlgorithms`, `jdk.certpath.disabledAlgorithms`, `jdk.jar.disabledAlgorithms` từ runtime.
- [ ] Kiểm tra key size theo chính sách **và** khả năng thực thi của provider.
- [ ] Chạy thử mã hóa có xác thực, giải mã và từ chối dữ liệu bị sửa.
- [ ] Kiểm tra TLS enabled và handshake negotiated, trust chain và hostname trên endpoint kiểm thử.
- [ ] Ghi quyết định mật mã, yêu cầu bảo mật, snapshot triển khai và chủ sở hữu.
- [ ] Tự động kiểm tra lại sau khi nâng cấp JDK, thay provider hoặc thay cấu hình bảo mật.

## Nguồn chính thức để tự đối chiếu với JDK đang dùng

- [Java SE Security Developer's Guide — JCA Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-cryptography-architecture-jca-reference-guide.html)
- [Java SE 25 — The Security Properties File](https://docs.oracle.com/en/java/javase/25/security/security-properties-file.html)
- [Java SE 25 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html)
- [Java SE 25 — `java.security.Security` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Security.html)
- [Java SE 25 — `javax.crypto.Cipher` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/Cipher.html)

Khi sử dụng bản JDK khác, xem **tài liệu và release notes đúng phiên bản runtime** để xác nhận các giá trị/giới hạn hiện hành. Không coi một danh sách mặc định lấy từ tài liệu của bản phát hành khác là cấu hình bắt buộc.
