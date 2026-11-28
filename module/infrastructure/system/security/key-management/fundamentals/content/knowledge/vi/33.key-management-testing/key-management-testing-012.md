# Test provider compatibility

Test provider compatibility là quá trình kiểm tra một ứng dụng Java có thể sử dụng đúng các dịch vụ mật mã trên những Java Security Provider và môi trường triển khai được hỗ trợ hay không. Kiểm thử cần xác minh thuật toán, transformation, tham số, key type, định dạng dữ liệu, hành vi lỗi và kết quả mật mã thực tế. Việc một provider liệt kê tên thuật toán chưa đủ chứng minh rằng ứng dụng có thể dùng thuật toán đó với mọi key size, mode, parameter spec hoặc loại khóa.

Trong module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, tương thích provider ảnh hưởng trực tiếp tới khả năng tạo, lưu, ký, mã hóa, giải mã và khôi phục khóa. Thay JDK, nâng cấp provider, đổi thứ tự provider hoặc thay HSM/PKCS#11 library đều có thể làm thay đổi hành vi. Vì vậy, cần kiểm thử theo đúng cấu hình runtime và lưu lại bằng chứng về provider thực sự đã thực hiện thao tác.

## 1. Vì sao cần kiểm thử provider compatibility?

Java Cryptography Architecture (JCA) và Java Cryptography Extension (JCE) cung cấp API chuẩn để ứng dụng gọi dịch vụ mật mã. Provider là thành phần cung cấp implementation cho các service như MessageDigest, Signature, Cipher, Mac, KeyAgreement, KeyPairGenerator, KeyGenerator, KeyFactory, SecretKeyFactory và KeyStore.

Một ứng dụng có thể chạy ổn định trên máy phát triển nhưng thất bại ở production vì:

- JDK hoặc vendor JDK khác nhau.
- Provider không được cài đặt, chưa đăng ký hoặc có thứ tự ưu tiên khác.
- Provider version mới bỏ alias cũ hoặc thay đổi cách xử lý tham số.
- Thuật toán có mặt nhưng transformation cụ thể không được hỗ trợ.
- Key size, curve, padding, digest hoặc tag length không được chấp nhận.
- Khóa được tạo bởi provider này nhưng provider khác không đọc được key format hoặc không hỗ trợ key object.
- PKCS#11 library, HSM firmware, token policy hoặc FIPS mode khác môi trường thử nghiệm.
- Chính sách mật mã của JDK giới hạn key size hoặc cấm thuật toán.

Kiểm thử compatibility giúp phát hiện sớm lỗi triển khai, tránh fallback ngoài ý muốn và bảo đảm các thao tác liên quan đến key material tiếp tục hoạt động sau khi nâng cấp hạ tầng.

## 2. Các chiều tương thích cần kiểm tra

Không nên ghi nhận compatibility chỉ bằng một giá trị như “AES được hỗ trợ”. Cần xác định chính xác tổ hợp môi trường và thao tác:

| Chiều kiểm tra | Ví dụ giá trị | Câu hỏi cần trả lời |
|---|---|---|
| JDK | Vendor, version, build, security properties | API và policy runtime có giống môi trường mục tiêu không? |
| Provider | Name, version, thứ tự đăng ký | Provider nào thực sự được chọn? |
| Service/algorithm | Cipher AES, Signature SHA256withRSA | Service và thuật toán có được triển khai không? |
| Transformation | AES/GCM/NoPadding | Mode và padding có hoạt động không? |
| Parameters | GCM tag length, OAEP digest/MGF, EC curve | Tham số cụ thể có được chấp nhận không? |
| Key | Key size, key class, key format, extractability | Provider có dùng được loại khóa thật không? |
| Storage | PKCS12, JKS, PKCS11 | Có load/store hoặc truy cập đúng entry không? |
| Platform | OS, architecture, container image | Native library và provider có tương thích không? |
| Hardware | HSM model, firmware, partition, PKCS#11 library | Thiết bị có hỗ trợ thao tác và policy cần thiết không? |
| Security policy | Approved mode, disabled algorithms, key-size limits | Cấu hình có cho phép thuật toán và tham số không? |
| Interoperability | Dữ liệu hoặc chữ ký giữa provider | Dữ liệu tạo ở môi trường này có được môi trường kia xử lý đúng không? |

Ma trận tương thích cần giới hạn vào các tổ hợp thực sự được triển khai. Không cần kiểm thử mọi JDK/provider trên thị trường, nhưng phải bao phủ các tổ hợp production, disaster recovery và môi trường nâng cấp dự kiến.

## 3. Phân biệt service, algorithm và transformation

JCA chọn implementation theo service type và thuật toán. Với Cipher, tên transformation còn xác định mode và padding. Đây là điểm dễ gây nhầm khi khám phá provider:

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| Service type | Cipher | Loại dịch vụ JCA |
| Algorithm | AES | Thuật toán cơ sở mà provider đăng ký |
| Transformation | AES/GCM/NoPadding | Thuật toán kết hợp mode và padding |
| Parameter spec | GCMParameterSpec | Tham số cụ thể khi khởi tạo engine |
| Key type | SecretKey/AES | Loại khóa đưa vào thao tác |

Provider thường đăng ký service Cipher theo thuật toán cơ sở như AES. Việc thấy Cipher.AES trong danh sách provider không chứng minh rằng AES/GCM/NoPadding, AES/CCM/NoPadding hoặc mọi transformation khác đều hoạt động. Phải gọi Cipher.getInstance với transformation đầy đủ rồi thực hiện thao tác bằng key và parameter spec thực tế.

Tương tự, provider có thể hỗ trợ Signature với RSA nhưng không hỗ trợ mọi biến thể như RSASSA-PSS với digest/MGF cụ thể. Tên thuật toán cần được kiểm tra cùng tham số và key type.

## 4. Xác định provider thực sự được sử dụng

Nếu gọi getInstance mà không chỉ định provider, JCA tìm implementation theo danh sách provider đã đăng ký và thứ tự ưu tiên trong runtime. Cấu hình JDK, ứng dụng hoặc thư viện có thể làm thay đổi thứ tự này.

Có thể kiểm tra provider đã đăng ký:

~~~java
import java.security.Provider;
import java.security.Security;

public class ProviderInventory {
    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            System.out.println(
                    provider.getName() + " / " + provider.getVersionStr());
        }
    }
}
~~~

Provider.getVersionStr() có từ Java 9. Nếu ứng dụng phải chạy trên Java 8, dùng API phiên bản provider tương ứng của runtime đó và chuẩn hóa cách ghi version trong báo cáo.

Để biết provider đã thực hiện một thao tác cụ thể, kiểm tra provider trên engine sau khi tạo:

~~~java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
System.out.println("Selected provider: " + cipher.getProvider().getName());
~~~

Trong production, nếu yêu cầu bảo mật phụ thuộc vào một provider cụ thể, nên chỉ định provider rõ ràng hoặc kiểm tra provider được chọn khi khởi động. Ví dụ:

~~~java
Provider required = Security.getProvider("RequiredProvider");
if (required == null) {
    throw new IllegalStateException("Required provider is unavailable");
}

Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding", required);
~~~

Tên provider trong ví dụ là placeholder. Ứng dụng cần cấu hình đúng tên provider đã được phê duyệt và kiểm tra version. Không tự thêm provider không xác thực hoặc tự đổi thứ tự provider chỉ để làm một test thất bại trở thành thành công.

## 5. Kiểm tra danh sách service và algorithm

Có thể liệt kê các service mà provider công bố:

~~~java
import java.security.Provider;
import java.security.Security;

public class ProviderServices {
    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            System.out.println("Provider: " + provider.getName());
            for (Provider.Service service : provider.getServices()) {
                System.out.println(
                        service.getType() + "." + service.getAlgorithm());
            }
        }

        System.out.println(
                "MessageDigest algorithms: "
                        + Security.getAlgorithms("MessageDigest"));
    }
}
~~~

Danh sách này hữu ích cho inventory và chẩn đoán, nhưng chỉ là metadata được provider công bố. Alias, cách viết hoa/thường và tên canonical có thể khác nhau. Không nên xây dựng logic production bằng cách so khớp chuỗi danh sách một cách cứng nhắc rồi kết luận thuật toán hoạt động.

Có thể kiểm tra một service cụ thể bằng Provider.getService(type, algorithm). Tuy nhiên, service lookup cũng không xác minh được transformation đầy đủ, key size, parameter spec hoặc thao tác thực tế. Phải kết hợp discovery với functional test.

## 6. Kiểm tra key size và parameter constraints

Provider compatibility phụ thuộc key size và tham số:

- AES có thể hỗ trợ key 128 bit nhưng bị giới hạn hoặc không hỗ trợ 192/256 bit trong một cấu hình.
- RSA có thể hỗ trợ ký nhưng giới hạn kích thước modulus hoặc padding.
- EC có thể hỗ trợ một số named curve nhưng không hỗ trợ curve khác.
- AES-GCM có thể chấp nhận một số IV length và authentication tag length.
- RSA-OAEP cần thống nhất digest, MGF algorithm, MGF digest và label.
- RSA-PSS cần thống nhất digest, MGF, salt length và trailer field.

Cipher.getMaxAllowedKeyLength(transformation) cho biết giới hạn key size tối đa theo chính sách mật mã của runtime đối với transformation được hỏi. Giá trị này không chứng minh provider hoặc HSM cụ thể hỗ trợ key size đó. Cần thử với key đúng loại và kiểm tra tài liệu provider.

Đối với thuật toán có parameter spec, test nên khởi tạo engine với đúng cấu hình production. Không chỉ kiểm tra getInstance thành công rồi kết luận tương thích.

## 7. Functional test và known-answer test

Functional test kiểm tra một thao tác có chạy được và kết quả có đúng. Known-answer test (KAT) so sánh kết quả với một vector đã biết, giúp phát hiện implementation trả kết quả sai dù thao tác không ném exception.

Ví dụ SHA-256 với chuỗi abc có digest chuẩn:

~~~text
ba7816bf8f01cfea414140de5dae2223
b00361a396177a9cb410ff61f20015ad
~~~

Ví dụ Java kiểm tra digest trên từng provider:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.Provider;
import java.util.HexFormat;

public static void testSha256(Provider provider) throws Exception {
    byte[] actual = MessageDigest.getInstance("SHA-256", provider)
            .digest("abc".getBytes(StandardCharsets.US_ASCII));

    String expected =
            "ba7816bf8f01cfea414140de5dae2223"
            + "b00361a396177a9cb410ff61f20015ad";

    if (!HexFormat.of().formatHex(actual).equals(expected)) {
        throw new AssertionError("SHA-256 known-answer test failed");
    }
}
~~~

HexFormat có từ Java 17. Với Java version cũ hơn, dùng hàm chuyển byte array sang hexadecimal của test utility. Nếu provider không hỗ trợ SHA-256, test phải ghi nhận là unsupported thay vì bỏ qua âm thầm.

Với Cipher, cần dùng vector chuẩn phù hợp với transformation và tham số. Ví dụ AES-128-GCM với key 16 byte toàn số 0, IV 12 byte toàn số 0 và plaintext rỗng tạo ra ciphertext rỗng cùng authentication tag:

~~~text
58e2fccefa7e3061367f1d57a4e7455a
~~~

Vector này có thể dùng để kiểm tra implementation AES-GCM trong test độc lập. Khi xây dựng test, cần phân biệt ciphertext và tag theo API của provider; nhiều Java Cipher implementation trả ciphertext nối tiếp tag từ doFinal. Không sử dụng vector test làm key hoặc nonce trong dữ liệu production.

KAT không thay thế test với dữ liệu thực tế, tham số production, key object từ KMS/HSM và kiểm thử interoperability.

## 8. Kiểm thử Cipher transformation và AEAD

Với mỗi transformation quan trọng, cần kiểm tra:

1. Engine được tạo bởi đúng provider.
2. Key size và key class phù hợp.
3. Parameter spec được chấp nhận.
4. Encrypt và decrypt tạo ra plaintext ban đầu.
5. Thay đổi ciphertext, nonce hoặc AAD làm xác minh tag thất bại.
6. Nonce được tạo và quản lý theo quy tắc của mode.
7. Provider không tự chuyển sang transformation khác khi cấu hình yêu cầu không được hỗ trợ.

Ví dụ test round-trip AES-GCM:

~~~java
import java.security.SecureRandom;
import java.security.Provider;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public static void testAesGcm(
        Provider provider, SecretKey key) throws Exception {
    byte[] nonce = new byte[12];
    new SecureRandom().nextBytes(nonce);
    byte[] plaintext = "provider compatibility".getBytes(
            java.nio.charset.StandardCharsets.UTF_8);

    Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding", provider);
    encryptor.init(
            Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, nonce));
    byte[] ciphertext = encryptor.doFinal(plaintext);

    Cipher decryptor = Cipher.getInstance("AES/GCM/NoPadding", provider);
    decryptor.init(
            Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, nonce));
    byte[] recovered = decryptor.doFinal(ciphertext);

    if (!Arrays.equals(plaintext, recovered)) {
        throw new AssertionError("AES-GCM round-trip failed");
    }
}
~~~

Đây là test Cipher trong môi trường cô lập; key cần được tạo bằng fixture phù hợp với provider hoặc bằng KeyGenerator nếu provider đó có hỗ trợ service này. Có thể kiểm tra KeyGenerator riêng:

~~~java
KeyGenerator generator = KeyGenerator.getInstance("AES", provider);
generator.init(128);
SecretKey testKey = generator.generateKey();
~~~

Tách hai phép thử giúp xác định lỗi nằm ở service KeyGenerator hay Cipher. Với HSM, phải dùng key object được tạo trên đúng token/partition nếu muốn kiểm tra đường thực thi phần cứng. Không tái sử dụng nonce dưới cùng một key trong ứng dụng thực tế. Nên bổ sung negative test: thay một byte ciphertext hoặc AAD rồi xác minh doFinal thất bại với lỗi xác thực phù hợp.

## 9. Kiểm thử Signature và khả năng tương tác giữa provider

Một provider có thể tạo chữ ký nhưng provider khác không xác minh được do khác thuật toán, encoding, parameter hoặc format. Kiểm thử interoperability nên tạo key pair và chữ ký bằng provider A, sau đó xác minh bằng provider B.

Với RSA/ECDSA:

- Thống nhất thuật toán chữ ký và digest.
- Kiểm tra key size hoặc EC named curve.
- Xác nhận public key format có thể chuyển giữa hai provider nếu được phép export.
- Kiểm tra chữ ký tạo bởi A xác minh thành công ở B.
- Thay đổi message hoặc signature và xác minh phải thất bại.

Với ECDSA, Java Signature thường sử dụng biểu diễn chữ ký ASN.1 DER. Một số giao thức hoặc thiết bị yêu cầu biểu diễn fixed-width r||s; test interoperability phải kiểm tra định dạng và thực hiện chuyển đổi theo chuẩn giao thức nếu cần.

Với RSA-PSS, không dựa vào default parameter của provider. Cần đặt rõ digest, MGF algorithm, MGF digest, salt length và trailer field bằng parameter spec thống nhất. Hai provider có thể cùng hỗ trợ RSASSA-PSS nhưng không tương thích nếu tham số mặc định khác nhau.

Với HSM private key không export được, không cần chuyển private key sang provider B. Có thể ký trong HSM rồi đưa chữ ký và public key/certificate tới provider B để xác minh. Đây là cách kiểm thử ranh giới phần cứng thực tế hơn.

## 10. Kiểm thử KeyStore và key format interoperability

KeyStore compatibility không chỉ là định dạng file. Cần kiểm tra:

- Loại keystore như PKCS12, JKS hoặc PKCS11.
- Provider tạo và provider đọc.
- PrivateKeyEntry, SecretKeyEntry và TrustedCertificateEntry.
- Key format như PKCS#8, X.509 SubjectPublicKeyInfo và RAW nếu được hỗ trợ.
- Certificate chain và thuật toán/chữ ký của certificate.
- Password protection và cách provider xử lý entry protection.
- Alias, metadata và thuộc tính key sau khi load.

Test interoperability nên tạo một keystore bằng tổ hợp JDK/provider thứ nhất, sau đó load bằng tổ hợp thứ hai trong môi trường test. Kiểm tra cả certificate chain, alias và thao tác sử dụng key. Không giả định mọi provider PKCS12 hỗ trợ giống nhau đối với secret key entry hoặc thuật toán bảo vệ entry.

Với PKCS11, dữ liệu key có thể nằm trong token/HSM thay vì file. Khi đó, cần kiểm thử cấu hình provider, token login, slot/partition, object attributes và quyền truy cập. Không áp dụng kỳ vọng của file-backed KeyStore cho token-backed KeyStore.

## 11. Kiểm thử PKCS#11 và HSM compatibility

Provider PKCS#11 tạo cầu nối giữa Java và token/HSM. Compatibility phụ thuộc đồng thời vào:

- JDK và phiên bản provider Java.
- PKCS#11 library và phiên bản native library.
- HSM model, firmware, partition và token configuration.
- Algorithm mechanism mà thiết bị công bố.
- Key object attributes và quyền của client.
- Cấu hình login, PIN, session và slot.
- Hệ điều hành, kiến trúc CPU và cách nạp native library.

Test cần thực hiện trên đúng thiết bị hoặc partition kiểm thử:

1. Khởi tạo provider và xác nhận token/slot mong đợi.
2. Login bằng danh tính test có quyền giới hạn.
3. Tạo hoặc truy cập key object theo policy.
4. Thực hiện Sign/Verify, Encrypt/Decrypt hoặc KeyAgreement cần thiết.
5. Xác nhận thao tác nhạy cảm chạy trên HSM theo audit/device evidence.
6. Kiểm tra key không export được nếu policy yêu cầu non-extractability.
7. Logout, reconnect và kiểm tra session/key handle.
8. Thử token unavailable, sai PIN, session exhausted và lỗi native library.

Không kết luận HSM compatibility chỉ vì Cipher hoặc Signature getInstance thành công. Engine có thể được tạo nhưng thiết bị từ chối mechanism hoặc key object khi init/doFinal/sign.

## 12. Provider selection, fallback và fail-safe

Fallback có thể giúp ứng dụng tương thích nhiều môi trường, nhưng cũng có thể làm thay đổi ranh giới bảo mật. Ví dụ, nếu ứng dụng yêu cầu thao tác Sign trong HSM mà HSM provider lỗi, chuyển sang provider phần mềm có thể khiến private key được xử lý ngoài thiết bị.

Quy tắc triển khai:

- Định nghĩa danh sách provider được phép cho từng service/algorithm.
- Ghi nhận provider name/version thực tế trong startup diagnostics.
- Không tự động fallback sang thuật toán yếu hơn hoặc provider không được phê duyệt.
- Nếu provider bắt buộc không khả dụng, fail closed đối với thao tác nhạy cảm.
- Nếu có fallback được phê duyệt, kiểm tra rõ điều kiện, key source và audit.
- Không thay đổi provider order giữa các request.
- Kiểm thử hành vi khi provider bị gỡ, native library mất hoặc HSM offline.

Lỗi tương thích phải được báo với thông tin đủ chẩn đoán nhưng không chứa password, token hoặc key material.

## 13. Kiểm thử FIPS và security policy

Một số môi trường yêu cầu provider hoặc module mật mã hoạt động trong chế độ được đánh giá/chứng nhận, chẳng hạn FIPS 140. Compatibility test cần xác minh đúng phiên bản module, cấu hình approved mode và thuật toán nằm trong phạm vi được phép.

Không kết luận môi trường tuân thủ chỉ vì provider có tên chứa FIPS hoặc một API gọi thành công. Cần kiểm tra:

- Phiên bản module/provider và phạm vi chứng nhận áp dụng.
- Cấu hình approved mode theo tài liệu nhà cung cấp.
- Thuật toán, key size, mode và tham số được phép.
- Nguồn tạo và nơi thực thi key operation.
- Không có fallback ngoài module được đánh giá.
- Security properties và disabledAlgorithms của JDK.

Một thuật toán có thể vẫn được provider công bố để tương thích nhưng bị policy cấm trong môi trường cụ thể. Test cần phân biệt unsupported, disabled by policy và provider failure để báo cáo chính xác.

## 14. Ma trận tương thích và báo cáo kiểm thử

Nên lưu kết quả theo từng tổ hợp môi trường:

| JDK | Provider/version | Platform/HSM | Transformation/service | Key/parameters | Kết quả |
|---|---|---|---|---|---|
| JDK build A | Provider X version 1 | Linux x86_64 | AES/GCM/NoPadding | AES-128, tag 128, IV 12 bytes | PASS/FAIL |
| JDK build A | Provider Y version 3 | HSM partition test | SHA256withRSA | RSA-3072, non-extractable private key | PASS/FAIL |
| JDK build B | Provider X version 2 | Windows x64 | PKCS12 KeyStore | PrivateKeyEntry + chain | PASS/FAIL |

Báo cáo cần ghi:

- JDK vendor/version/build và OS/architecture.
- Provider name/version và thứ tự đăng ký.
- Service, algorithm, transformation và parameter spec.
- Key class, key size, key format hoặc nguồn key object.
- HSM model/firmware/PKCS#11 library nếu có.
- Kết quả KAT, round-trip, negative test và interoperability.
- Exception type, provider error code và request ID đã loại bỏ dữ liệu nhạy cảm.
- Policy/FIPS mode và security property liên quan.

Không ghi key bytes, password, PIN, token hoặc private key trong report. Có thể ghi key ID/alias nếu chính sách phân loại dữ liệu cho phép.

## 15. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| NoSuchAlgorithmException | Service/algorithm/transformation không có trong provider khả dụng | Kiểm tra tên, provider, JDK và alias |
| NoSuchProviderException | Provider chưa cài hoặc tên provider sai | Kiểm tra Security.getProvider và cấu hình khởi động |
| InvalidKeyException | Key class, key size, key usage hoặc token policy không phù hợp | Kiểm tra nguồn key, attributes và hỗ trợ key type |
| InvalidAlgorithmParameterException | Parameter spec, curve, IV, tag hoặc padding không được hỗ trợ | Kiểm tra tham số chính xác và tài liệu provider |
| SignatureException hoặc BadPaddingException | Sai key, sai tham số, dữ liệu hỏng hoặc không tương thích | Kiểm tra key version, format, digest, MGF và dữ liệu đầu vào |
| ProviderException | Lỗi implementation, native library, token hoặc HSM | Kiểm tra provider/HSM log, firmware, session và kết nối |
| Chạy được ở dev nhưng lỗi production | JDK, provider order, policy hoặc phần cứng khác nhau | So sánh compatibility matrix |
| Engine tạo được nhưng thao tác thất bại | Metadata có nhưng capability thực tế thiếu | Thử init và operation với key/parameters thật |
| Ký được nhưng provider khác không verify | Signature encoding hoặc parameters khác nhau | Kiểm tra DER/raw, digest, curve, PSS/MGF |

Không bắt mọi exception rồi tiếp tục bằng provider mặc định. Hãy phân loại lỗi và dừng thao tác nhạy cảm khi không đáp ứng yêu cầu bảo mật.

## 16. Checklist triển khai

- [ ] Liệt kê JDK vendor/version/build và hệ điều hành được hỗ trợ.
- [ ] Ghi provider name/version và thứ tự provider trong runtime.
- [ ] Xác định service, algorithm và transformation chính xác.
- [ ] Kiểm thử key size, parameter spec, curve, mode, padding và tag length.
- [ ] Kiểm thử với đúng key class, key format và nguồn key production dự kiến.
- [ ] Chạy known-answer test cho các thuật toán cốt lõi.
- [ ] Chạy round-trip và negative test cho Cipher/AEAD.
- [ ] Kiểm thử ký-xác minh giữa provider hoặc giữa provider và hệ thống ngoài.
- [ ] Kiểm thử KeyStore format và PKCS#11/HSM trên môi trường tương ứng.
- [ ] Xác minh provider thực sự thực hiện thao tác và không fallback ngoài policy.
- [ ] Kiểm tra FIPS/approved mode và disabled algorithm policy nếu áp dụng.
- [ ] Kiểm thử sau khi nâng cấp JDK, provider, SDK, native library hoặc firmware.
- [ ] Lưu compatibility matrix và report không chứa bí mật.

Test provider compatibility phải chứng minh ứng dụng thực hiện đúng thao tác mật mã với provider, key và tham số thực tế trong từng môi trường được hỗ trợ. Kết hợp discovery, known-answer test, round-trip, negative test và interoperability giúp phát hiện khác biệt trước khi triển khai, đồng thời bảo đảm việc chọn provider không làm suy yếu ranh giới bảo vệ khóa.
