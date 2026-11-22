# Provider mật mã và khả năng hỗ trợ thuật toán trong Java

**Ngữ cảnh:** Java 15 → Tương thích và build. Cơ chế JCA/JCE dưới đây vẫn dùng trong Java SE hiện hành. Danh sách provider và thuật toán phải được kiểm tra trên **JVM thực tế** của ứng dụng; không thể kết luận chỉ từ số phiên bản Java. Bài chỉ dùng kiến thức, API và khuyến nghị còn phù hợp với các hệ thống hiện nay.

## 1. Provider là gì? Vì sao ứng dụng có thể chạy khác nhau?

Java Cryptography Architecture (**JCA**) và Java Cryptography Extension (**JCE**, là thành phần của Java SE) cung cấp API thống nhất cho băm, MAC, mã hóa, chữ ký số, thỏa thuận khóa, keystore và sinh số ngẫu nhiên. Ứng dụng gọi một *engine class*; một **cryptographic service provider** cung cấp phần triển khai thuật toán ở phía sau.

Ví dụ:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
```

Hai lệnh yêu cầu **dịch vụ + thuật toán**, không chỉ định thư viện triển khai cụ thể. JCA/JCE tìm provider đã đăng ký có thể đáp ứng yêu cầu. Cùng mã nguồn có thể chọn implementation khác nhau khi chuyển giữa JDK vendor, hệ điều hành, container, runtime image hoặc môi trường có HSM (Hardware Security Module).

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Engine/service type** | Loại API để yêu cầu chức năng | `MessageDigest`, `Cipher`, `Mac`, `Signature`, `KeyAgreement`, `KeyStore`, `SSLContext` |
| **Algorithm name** | Tên thuật toán/kiểu dịch vụ gắn với engine | `SHA-256`, `HmacSHA256`, `RSASSA-PSS`, `PKCS12` |
| **Cipher transformation** | Thuật toán + mode + padding | `AES/GCM/NoPadding` |
| **Provider** | Thành phần công bố và triển khai các service | `SUN`, `SunJCE`, `SunEC`, provider HSM |
| **Provider.Service** | Bản ghi provider công bố về một cặp service/algorithm | `Cipher` + `AES` |
| **Runtime support** | Có thể khởi tạo và thực hiện với key, tham số và policy cụ thể | AES-GCM mã hóa rồi giải mã thành công |

Phân biệt bốn mức: **(1) Java có API**, **(2) provider có đăng ký tên thuật toán**, **(3) `getInstance` tạo được engine**, và **(4) phép toán với key/tham số thực tế chạy được**. Mức trước không tự bảo đảm mức sau.

## 2. Các provider phổ biến và phạm vi hỗ trợ

Đây là những ví dụ từ dòng OpenJDK/Oracle JDK. **Không mặc định tất cả đều có** trong mọi Java runtime; một số còn phụ thuộc module, hệ điều hành hoặc cấu hình.

| Provider | Vai trò điển hình | Điều cần hiểu |
| --- | --- | --- |
| `SUN` | `MessageDigest` SHA-2, `SecureRandom`, X.509, PKIX | Không đồng nghĩa cung cấp mọi loại `Cipher`. |
| `SunJCE` | `Cipher`, `Mac`, `KeyGenerator`; ví dụ AES-GCM và HMAC | Danh sách thực tế tùy JDK và policy. |
| `SunRsaSign` | Khóa và chữ ký RSA | Không suy ra mọi transformation mã hóa RSA đều do provider này cung cấp. |
| `SunEC` | EC/ECDSA, ECDH, các phép đường cong như X25519 ở JDK phù hợp | Có thể phụ thuộc module/thành phần runtime. |
| `SunJSSE` | TLS với `SSLContext` và các engine liên quan | Có `SSLContext("TLS")` chưa chắc bắt tay TLS được với một peer. |
| `SunPKCS11` | Cầu nối JCA/JCE đến thư viện native PKCS#11/HSM | Cần thư viện, token, cấu hình và mechanism tương thích; bản thân cầu nối không tự làm các phép mật mã. |
| Provider bổ sung | HSM, nhà cung cấp độc lập, tích hợp hệ điều hành | Chỉ hoạt động sau khi cài và đăng ký đúng cách. |

Các provider có thể được cấu hình tại `<java-home>/conf/security/java.security` hoặc bằng API đăng ký phù hợp. `Security.getProviders()` trả về danh sách provider đã đăng ký theo thứ tự ưu tiên chung; `Security.getProvider("Tên")` trả về provider theo tên hoặc `null`. Một JDK còn có thể ưu tiên provider riêng cho từng thuật toán (ví dụ `jdk.security.provider.preferred`). Vì vậy thứ tự danh sách không đủ để suy ra implementation cuối cùng cho mọi lời gọi.

**Ưu tiên không chỉ định provider** trong ứng dụng thông thường: `Cipher.getInstance("AES/GCM/NoPadding")`. Chỉ cố định provider khi có yêu cầu cụ thể như HSM, key không được phép xuất, policy hoặc chứng nhận tuân thủ; khi đó phải coi tên provider, loại key và cơ chế đăng ký là điều kiện triển khai cần kiểm thử.

## 3. “Có hỗ trợ thuật toán” nghĩa là gì?

**Mức 1 — Công bố dịch vụ:** `Security.getAlgorithms("MessageDigest")` liệt kê tên digest đã đăng ký. `Security.getProviders("Cipher.AES")` tìm các provider công bố `Cipher` + `AES`; kết quả có thể là `null`. Có thể duyệt `provider.getServices()` và đọc `Provider.Service.getType()` / `getAlgorithm()` để xem tên provider công bố.

**Mức 2 — Khởi tạo engine:** `Cipher.getInstance("AES/GCM/NoPadding")` thử **toàn bộ transformation**. `Security.getAlgorithms("Cipher")` thường chỉ liệt kê tên thuật toán cơ sở, **không phải** mọi tổ hợp mode/padding. `Cipher.AES` được công bố không tự chứng minh AES-GCM hoạt động.

**Mức 3 — Khởi tạo bằng key/tham số thật:** gọi `init` với key size, key type, IV/nonce, tag, curve, tham số RSA-PSS… mà ứng dụng thực sự dùng. Provider có thể quảng bá thuật toán nhưng không nhận key HSM hay bộ tham số được yêu cầu. Với `Cipher`, `Mac` và một số engine khác, JDK có thể **trì hoãn chọn provider đến lúc `init`** để chọn implementation phù hợp key. Do đó `getProvider()` trước `init` có thể chốt lựa chọn quá sớm; muốn ghi nhận provider của phép toán thực tế thì gọi sau `init`.

**Mức 4 — Thực hiện phép toán và kiểm tra kết quả:** thử `doFinal`, `sign`/`verify`, `generateSecret`, load keystore, hoặc TLS handshake với endpoint thực tế. Với mã hóa có xác thực (AEAD), cần xác nhận ciphertext/tag bị sửa bị từ chối.

**Mức 5 — Điều kiện triển khai:** chính sách TLS/certificate path, cấu hình FIPS, quyền HSM, bản native library, loại key và runtime image có thể hạn chế hành vi dù API/thuật toán được đăng ký.

| Mục tiêu | Engine và lựa chọn ví dụ còn phù hợp | Giới hạn kiểm tra |
| --- | --- | --- |
| Băm dữ liệu | `MessageDigest("SHA-256")` | Digest không xác thực người gửi; SHA-256 trực tiếp không phù hợp để lưu mật khẩu. |
| MAC có khóa | `Mac("HmacSHA256")` | Cần secret key và phép `init` thực sự thành công. |
| Mã hóa có xác thực | `Cipher("AES/GCM/NoPadding")` | Key AES, nonce riêng cho mỗi lần mã hóa với cùng key, tag xác thực. |
| Chữ ký số | `Signature("RSASSA-PSS")`, `Signature("SHA256withECDSA")` | Loại/độ dài key, tham số PSS, ký và xác minh thực tế. |
| Thỏa thuận khóa | `KeyAgreement("X25519")` hoặc `KeyAgreement("ECDH")` | Curve, định dạng key và bước dẫn xuất khóa chung. |
| Kho khóa/chứng chỉ | `KeyStore("PKCS12")` | Load/store, alias, mật khẩu và key type. |
| Kết nối bảo mật | `SSLContext("TLS")` | Policy giao thức/cipher suite, trust chain và handshake thật. |
| Nguồn ngẫu nhiên/khóa | `SecureRandom`, `KeyGenerator("AES")` | Chất lượng nguồn ngẫu nhiên, độ dài key và provider có thể sử dụng key. |

Tên trên là **ví dụ các khả năng cần kiểm chứng**, không cam kết hỗ trợ phổ quát. Hãy dùng tên chuẩn trong tài liệu *Java Security Standard Algorithm Names*; tra tài liệu đúng JDK/provider khi phụ thuộc một thuật toán hay mode cụ thể.

## 4. Chương trình kiểm kê provider: `CryptoProviderAudit.java`

Tạo đúng tệp **`CryptoProviderAudit.java`**:

```java
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.Provider;
import java.security.Security;
import java.security.Signature;
import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.net.ssl.SSLContext;

public class CryptoProviderAudit {
    @FunctionalInterface
    private interface Lookup {
        Provider find() throws GeneralSecurityException;
    }

    private static void check(String label, Lookup lookup) {
        try {
            Provider p = lookup.find();
            System.out.printf("%-22s : OK (%s)%n", label, p.getName());
        } catch (GeneralSecurityException e) {
            System.out.printf("%-22s : MISSING (%s)%n",
                    label, e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        for (Provider p : Security.getProviders()) {
            System.out.printf("Provider: %s (%s)%n",
                    p.getName(), p.getVersionStr());
        }
        Provider[] aes = Security.getProviders("Cipher.AES");
        System.out.println("Cipher.AES providers: " +
                (aes == null ? 0 : aes.length));

        check("SHA-256",
                () -> MessageDigest.getInstance("SHA-256").getProvider());
        check("HmacSHA256",
                () -> Mac.getInstance("HmacSHA256").getProvider());
        check("AES/GCM/NoPadding",
                () -> Cipher.getInstance("AES/GCM/NoPadding").getProvider());
        check("RSASSA-PSS",
                () -> Signature.getInstance("RSASSA-PSS").getProvider());
        check("KeyStore PKCS12",
                () -> KeyStore.getInstance("PKCS12").getProvider());
        check("SSLContext TLS",
                () -> SSLContext.getInstance("TLS").getProvider());
    }
}
```

Biên dịch/chạy trên JDK hỗ trợ mã nguồn (ví dụ Java 17+):

```bash
javac CryptoProviderAudit.java
java CryptoProviderAudit
```

Chương trình in danh sách provider, số provider công bố `Cipher.AES` và `OK (tên-provider)` hoặc `MISSING (loại-ngoại-lệ)` cho từng dịch vụ. **Không có stdout cố định** về tên/số provider vì phụ thuộc runtime. Đây là bước kiểm kê; `getProvider()` khi chưa `init` ở các engine có chọn provider trễ chỉ phản ánh lựa chọn tại thời điểm truy vấn, không bảo đảm đúng provider sẽ chạy với mọi key. Phép thử thật phải thực hiện thêm như phần tiếp theo.

Dùng `Security.getProviders("Cipher.AES")` để tìm các provider công bố engine + thuật toán, **không** dùng kết quả này như chứng cứ về mode GCM. Khi muốn kiểm kê toàn bộ service một provider, duyệt `Provider.getServices()` thay vì giả định mọi provider có cùng danh sách thuật toán.

## 5. Smoke test thực sự với AES-GCM: `AesGcmSmokeTest.java`

Tạo tệp **`AesGcmSmokeTest.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class AesGcmSmokeTest {
    public static void main(String[] args) throws Exception {
        KeyGenerator keyGenerator = KeyGenerator.getInstance("AES");
        keyGenerator.init(128);
        SecretKey key = keyGenerator.generateKey();

        byte[] iv = new byte[12];
        new SecureRandom().nextBytes(iv);
        byte[] input = "kiem tra provider".getBytes(StandardCharsets.UTF_8);

        Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
        encrypt.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv));
        byte[] ciphertext = encrypt.doFinal(input);

        Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
        decrypt.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, iv));
        byte[] restored = decrypt.doFinal(ciphertext);
        if (!Arrays.equals(input, restored)) {
            throw new AssertionError("AES-GCM round-trip failed");
        }
        System.out.println("AES-GCM round-trip: PASS");
    }
}
```

```bash
javac AesGcmSmokeTest.java
java AesGcmSmokeTest
```

Khi AES-GCM hoạt động và các provider chấp nhận key đã sinh, stdout chính xác:

```text
AES-GCM round-trip: PASS
```

**Vì sao test này có giá trị?** `KeyGenerator` sinh key AES 128 bit, `SecureRandom` tạo IV 12 byte, `GCMParameterSpec(128, iv)` chỉ định tag 128 bit. `encrypt.doFinal` mã hóa và tạo tag; `decrypt.doFinal` giải mã **đồng thời xác thực** tag. Vì vậy thử được các bước mà `Security.getAlgorithms` và `Cipher.getInstance` chưa chứng minh.

Đây là test với khóa tạm. Trong ứng dụng thật, **không được tái sử dụng cùng IV/nonce với cùng key AES-GCM** ở hai lần mã hóa; cần lưu/truyền IV cùng ciphertext/tag và giữ key bí mật. Nếu ciphertext, tag, key hoặc IV không khớp, giải mã có thể ném `AEADBadTagException`: phải coi đó là thất bại xác thực, không bỏ qua. Với HSM/FIPS, hãy test bằng **loại key thật** (có thể không xuất được) và provider/configuration thật; khóa do một provider sinh không mặc nhiên dùng được bởi provider khác.

## 6. Build, runtime và tính tương thích

### Chọn provider hợp lý

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
```

Trong code ứng dụng chung, dạng này để JCA tự tìm implementation phù hợp. Khi bắt buộc dùng provider cụ thể, xác nhận provider đã đăng ký, chọn overload `getInstance(transformation, provider)` và có integration test cho provider, key, tham số và token ấy. Tránh mặc định ép `SunJCE` chỉ vì máy phát triển có nó.

**Ba lớp cần phân biệt:**

1. **Build/API:** `javac --release 15` (nếu toolchain đang dùng còn hỗ trợ đích Java 15) giúp kiểm tra API/class file cho đích đó; **không mô phỏng** tập provider, chính sách bảo mật hay thiết bị của JRE đích. Với hệ thống mới, sử dụng JDK còn được hỗ trợ bảo mật.
2. **Runtime image:** bản JDK ở CI, container và production có thể khác vendor/version, cấu hình `java.security`, module `jlink`, provider hoặc native PKCS#11. Kiểm tra `java -version` và chạy audit trên **chính runtime cuối cùng**.
3. **Policy và tài nguyên khóa:** key size, key type, FIPS policy, `jdk.tls.disabledAlgorithms`, `jdk.certpath.disabledAlgorithms`, thư viện native, quyền HSM/token hoặc keystore có thể làm thất bại thao tác dù tên thuật toán được đăng ký.

Các bước nên đưa vào kiểm thử phát hành:

1. Ghi nhận **JDK vendor/version, base image và file cấu hình security** của các môi trường chạy.
2. Liệt kê chính xác nhu cầu của ứng dụng: engine, algorithm/transformation, key size/curve, tham số, kho khóa và chứng chỉ, thay cho yêu cầu mơ hồ “cần RSA và AES”.
3. Chạy `CryptoProviderAudit` trên mỗi runtime mục tiêu; lưu provider thực tế và kết quả những thuật toán bắt buộc.
4. Chạy phép toán thực tế với **key thật hoặc key cùng loại**: AES-GCM round-trip; chữ ký thì sign/verify, keystore thì load/read key; TLS thì handshake với endpoint thử nghiệm.
5. Nếu dùng HSM/PKCS#11, kiểm tra module `jdk.crypto.cryptoki` khi cần, thư viện native, cấu hình token, cơ chế cryptographic mechanism và quyền truy cập. Có tên `SunPKCS11` không có nghĩa phần cứng sẵn sàng.
6. Test lại sau khi đổi JDK, nhà cung cấp, container image, chính sách bảo mật hoặc cách sinh/lưu key. Không chỉ kiểm thử trên laptop rồi suy ra production giống hệt.

**Đặc biệt với TLS:** có `SSLContext("TLS")` chỉ chứng minh engine được cung cấp. Phiên TLS thực tế còn phụ thuộc protocol/cipher suite được policy cho phép, trust store, certificate chain và bên đối tác. Bài kiểm kê JCA không thay thế handshake test.

## 7. Lỗi thường gặp và cách xử lý

| Lỗi/triệu chứng | Nguyên nhân khả dĩ | Kiểm tra hoặc khắc phục |
| --- | --- | --- |
| `NoSuchAlgorithmException` | Không có service/algorithm phù hợp, tên sai, runtime thiếu provider | Xem engine, tên chuẩn, provider đã đăng ký và JDK thực tế. |
| `NoSuchPaddingException` | Padding/mode của transformation không được hỗ trợ | Kiểm tra đủ `algorithm/mode/padding`, đừng chỉ xét `Cipher.AES`. |
| `NoSuchProviderException` | Tên provider ép chọn chưa được đăng ký | So sánh `Security.getProviders()` với cấu hình runtime. |
| `InvalidKeyException` | Key sai thuật toán/kích thước, hoặc key HSM không dùng qua provider này | Thử đúng loại key, provider thực thi và quyền token. |
| `InvalidAlgorithmParameterException` | IV, tag, curve hoặc PSS parameters không hợp lệ | Đối chiếu bộ tham số cụ thể của provider. |
| `AEADBadTagException` | Xác thực AEAD thất bại: ciphertext/tag/key/IV không khớp | Kiểm tra đường truyền và quản lý IV/key; **không bỏ qua lỗi**. |
| `KeyStoreException` hoặc lỗi load | Loại kho khóa, mật khẩu, alias, provider hoặc dữ liệu không phù hợp | Kiểm tra `PKCS12`, dữ liệu và key thật. |
| `SSLHandshakeException` | Chứng chỉ/trust, TLS version, cipher suite hoặc policy không tương thích | Chẩn đoán handshake và policy TLS riêng. |

**Những nhầm lẫn cần tránh:**

- Coi danh sách từ `Security.getAlgorithms(...)` là bằng chứng mọi phép toán với mọi key đều chạy được.
- Gọi `Cipher.getInstance("AES")` mà không chỉ rõ mode/padding: default tùy provider và có thể không phù hợp an toàn. Với mã hóa mới, ưu tiên transformation có xác thực như `AES/GCM/NoPadding`.
- Lấy MD5, SHA-1 làm hash cho chữ ký mới, hoặc DES/3DES/RC4, ECB làm lựa chọn mặc định chỉ vì provider vẫn đăng ký chúng. **Còn tồn tại cho tương thích không đồng nghĩa còn phù hợp để thiết kế mới.**
- Dùng `java.util.Random` để sinh khóa/IV, dùng IV cố định với GCM, hay bỏ qua kết quả xác thực.
- Nhầm hỗ trợ của JCA với việc thuật toán/cipher suite được phép trong TLS hoặc quy trình xác minh chứng chỉ PKIX.
- Khóa cứng tên provider, thứ tự provider hoặc stdout audit của một máy vào logic nghiệp vụ.
- Đổi JDK hoặc `--release` nhưng bỏ qua test native HSM, permission token, keystore và security policy trên môi trường deploy.

## 8. Tình huống và bài tập áp dụng

**Tình huống A — Đổi JDK vendor:** `Security.getProviders()` cho danh sách khác trước, nhưng smoke test AES-GCM vẫn `PASS`. Kết luận hợp lý: tên/thứ tự provider có thay đổi, còn **năng lực cần thiết của ứng dụng** đang hoạt động; vẫn cần test các chức năng khác mà ứng dụng dùng.

**Tình huống B — “Có AES” nhưng AES-GCM lỗi:** `Security.getProviders("Cipher.AES")` không rỗng, còn `Cipher.getInstance("AES/GCM/NoPadding")` hoặc `init` thất bại. Cần kiểm tra mode/padding, key và policy: đăng ký `Cipher.AES` chỉ là điều kiện ban đầu.

**Tình huống C — Chuyển private key vào HSM:** code sign/verify chạy với khóa phần mềm nhưng thất bại với khóa token. Kiểm tra provider được chọn **sau khi `initSign`**, khả năng key không xuất được, mechanism và policy HSM; không tìm cách xuất private key nếu policy không cho phép.

Bài tập:

1. Chạy `CryptoProviderAudit` trên laptop và container đích. Ghi lại provider thực tế của `SHA-256`, `AES/GCM/NoPadding` và giải thích khác biệt.
2. So sánh `Security.getProviders("Cipher.AES")` với `Cipher.getInstance("AES/GCM/NoPadding")`. Nêu rõ mỗi phép thử xác nhận mức hỗ trợ nào.
3. Thay một byte ciphertext hoặc IV trong `AesGcmSmokeTest` trước khi giải mã. Xác nhận phép giải mã từ chối dữ liệu bị sửa.
4. Đề xuất smoke test riêng cho ứng dụng dùng `RSASSA-PSS` hoặc `KeyStore("PKCS12")`: phải có bước nào vượt quá `getInstance`?

**Tự đánh giá hoàn thành:** có thể xác định provider đã đăng ký, đặt đúng tên engine/algorithm/transformation, xác minh cả `init` và phép toán, và xây dựng kiểm thử tương thích cho runtime/build đang triển khai.

## Tài liệu tham khảo chính thức

- [JCA Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-cryptography-architecture-jca-reference-guide.html) — kiến trúc provider và chọn implementation.
- [JDK Providers Documentation](https://docs.oracle.com/en/java/javase/25/security/oracle-providers.html) — ví dụ provider và thuật toán trên bản JDK đã được tài liệu hóa.
- [Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html) — tên chuẩn service, thuật toán và transformation.
- [Security API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Security.html) và [Cipher API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/Cipher.html) — `getProviders`, `getAlgorithms`, `getInstance`, `init`, `doFinal`.
- [PKCS#11 Reference Guide](https://docs.oracle.com/en/java/javase/25/security/pkcs11-reference-guide1.html) — cấu hình PKCS#11 và điều kiện sử dụng HSM.

Tài liệu trên mô tả cơ chế API và hành vi đang áp dụng; khi đưa ứng dụng vào hoạt động, phải kết hợp tài liệu của **JDK/provider đang chạy** với phép thử thực tế.
