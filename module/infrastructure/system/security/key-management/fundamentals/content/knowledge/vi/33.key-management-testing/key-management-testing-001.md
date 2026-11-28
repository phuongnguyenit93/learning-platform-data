# Test key generation

**Test key generation** là quá trình kiểm tra chức năng sinh khóa của ứng dụng hoặc dịch vụ quản lý khóa có tạo ra khóa đúng thuật toán, đúng tham số, đúng mục đích và có thể được sử dụng an toàn trong kiến trúc dự kiến hay không. Việc kiểm thử bao gồm khóa đối xứng, cặp khóa bất đối xứng, provider mật mã, nơi lưu trữ và các metadata gắn với khóa.

Một phép kiểm thử thành công không chỉ chứng minh API trả về một đối tượng Key hoặc KeyPair. Khóa phải đáp ứng chính sách mật mã, hoạt động đúng với thao tác dự kiến, được lưu và truy xuất đúng cách, có quyền truy cập phù hợp và không làm lộ vật liệu khóa. Với KMS/HSM, cần xác minh cả hành vi của dịch vụ và ranh giới bảo vệ khóa.

Kiểm thử key generation cũng cần hiểu giới hạn của nó: unit test có thể xác minh thuật toán, kích thước, tính tương thích và thao tác mật mã, nhưng không thể chứng minh một bộ sinh số ngẫu nhiên có entropy tốt chỉ bằng cách sinh vài khóa rồi so sánh chúng. Chất lượng nguồn ngẫu nhiên cần dựa vào SecureRandom/provider đáng tin cậy, cấu hình nền tảng, đánh giá triển khai và kiểm định chuyên biệt.

## 1. Mục tiêu kiểm thử key generation

Một kế hoạch kiểm thử nên trả lời các câu hỏi:

- API có sinh được khóa bằng thuật toán được chính sách cho phép không?
- Kích thước khóa, đường cong hoặc tham số có đúng cấu hình không?
- Cặp public/private key có tương ứng và thực hiện được thao tác mật mã dự kiến không?
- Khóa đối xứng có hoạt động với Cipher hoặc Mac theo mục đích được cấp không?
- Provider được chọn có đúng provider được triển khai và có hỗ trợ thuật toán cần thiết không?
- Khóa có được lưu trong KeyStore, KMS hoặc HSM theo đúng chính sách không?
- Quyền sử dụng khóa, key ID, trạng thái và audit metadata có chính xác không?
- Các lỗi cấu hình hoặc thuật toán không được phép có bị từ chối không?
- Log, exception, test report và artifact có tránh chứa key material hoặc secret không?

Cần phân biệt kiểm thử chức năng với kiểm định mật mã. Unit test và integration test xác minh hành vi của ứng dụng; chúng không thay thế chứng nhận provider, kiểm định HSM, đánh giá thuật toán hoặc quy trình phê duyệt mật mã của tổ chức.

## 2. Phân loại phạm vi test

| Loại kiểm thử | Mục tiêu | Ví dụ |
|---|---|---|
| Unit test | Kiểm tra logic tạo khóa và cấu hình tham số | Sinh RSA 2048 bit, EC secp256r1 |
| Cryptographic behavior test | Xác minh khóa thực hiện đúng tác vụ | Ký rồi xác minh, mã hóa rồi giải mã |
| Provider integration test | Xác minh provider thực tế hỗ trợ thuật toán | JCA provider, PKCS#11 provider |
| KeyStore integration test | Kiểm tra lưu và tải lại entry | PrivateKeyEntry, SecretKeyEntry |
| KMS/HSM integration test | Kiểm tra thao tác với khóa không xuất được | Sign, Decrypt, GenerateDataKey |
| Policy/security test | Xác minh thuật toán và quyền bị giới hạn đúng | Từ chối RSA quá ngắn hoặc key usage sai |
| Operational test | Kiểm tra audit, rotation, backup và cleanup | Tạo key version, ghi event, hủy test key |

Unit test thường chạy nhanh và không phụ thuộc dịch vụ ngoài. Integration test cần môi trường được cô lập, credential thử nghiệm và quy trình cleanup. Không dùng khóa production hoặc dữ liệu production trong test.

## 3. Kiểm tra khóa đối xứng và cặp khóa bất đối xứng

Hai nhóm khóa có cách kiểm thử khác nhau.

**Khóa đối xứng** như AES hoặc HMAC chỉ có một vật liệu khóa bí mật. Test thường xác minh:

- Khóa được sinh với thuật toán và độ dài được yêu cầu.
- Khóa dùng được với Cipher hoặc Mac đúng mục đích.
- Dữ liệu mã hóa có thể giải mã bằng cùng khóa và tham số.
- Tag MAC tạo ra có thể xác minh, còn dữ liệu bị sửa phải bị từ chối.
- Khóa không bị xuất hoặc ghi log ngoài chính sách.

**Cặp khóa bất đối xứng** như RSA, EC hoặc Ed25519 có public key và private key liên kết. Test thường xác minh:

- Hai thành phần tồn tại và đúng thuật toán.
- Public key xác minh được chữ ký do private key tương ứng tạo ra.
- Chữ ký trên dữ liệu khác hoặc chữ ký bị sửa phải không hợp lệ.
- Với thuật toán thỏa thuận khóa như X25519, hai bên tính ra cùng shared secret.
- Private key được lưu và sử dụng theo chính sách; public key được phân phối có xác thực.

Không dùng cùng một bài test cho mọi loại khóa. Ví dụ, Ed25519 dùng cho chữ ký; X25519 dùng cho thỏa thuận khóa. Một test gọi Signature trên khóa X25519 là sai mục đích dù API có thể trả lỗi rõ ràng.

## 4. Kiểm tra thuật toán và tham số

Tên thuật toán chỉ là một phần của cấu hình. Test cần xác minh các tham số cụ thể:

| Thuật toán | Thuộc tính cần kiểm tra | Ví dụ |
|---|---|---|
| RSA | Modulus size, public exponent theo policy | 2048 hoặc 3072 bit tùy yêu cầu |
| EC | Named curve và kích thước trường | secp256r1 |
| Ed25519 | Thuật toán và khả năng hỗ trợ của provider | KeyPairGenerator Ed25519 |
| X25519 | Mục đích thỏa thuận khóa và provider | KeyPairGenerator X25519 |
| AES | Độ dài khóa được phép | 128 hoặc 256 bit theo policy |
| HMAC | Thuật toán MAC và độ dài khóa theo policy | HmacSHA256 |

Test không nên chỉ kiểm tra chuỗi **getAlgorithm()**. Với RSA, có thể kiểm tra **RSAPublicKey.getModulus().bitLength()**. Với EC, có thể kiểm tra tham số đường cong của **ECPublicKey**. Với khóa không xuất được trong HSM, dùng metadata hoặc thuộc tính do provider cung cấp; không yêu cầu **getEncoded()** phải trả về byte.

Cần tách chính sách môi trường khỏi test fixture. Ví dụ RSA 2048 bit có thể được dùng trong một test tương thích, nhưng production policy có thể yêu cầu 3072 bit. Test nên xác nhận cấu hình thực tế đúng với policy được truyền vào, thay vì rải một con số cố định ở nhiều nơi.

## 5. Kiểm tra cặp RSA bằng ký và xác minh

Một cách thực tế để kiểm tra hai khóa RSA có tương ứng là ký một thông điệp bằng private key rồi xác minh chữ ký bằng public key. Bài test không cần xuất hoặc in vật liệu khóa.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.Signature;
import org.junit.jupiter.api.Test;

class RsaKeyGenerationTest {
    @Test
    void generatedPairCanSignAndVerify() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048, new SecureRandom());

        KeyPair pair = generator.generateKeyPair();

        assertNotNull(pair.getPrivate());
        assertNotNull(pair.getPublic());
        assertEquals("RSA", pair.getPrivate().getAlgorithm());
        assertEquals("RSA", pair.getPublic().getAlgorithm());
        assertEquals(
            2048,
            ((java.security.interfaces.RSAPublicKey) pair.getPublic())
                .getModulus().bitLength()
        );

        byte[] message = "key-generation-test".getBytes(
            java.nio.charset.StandardCharsets.UTF_8
        );

        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signed = signer.sign();

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(pair.getPublic());
        verifier.update(message);

        assertTrue(verifier.verify(signed));

        Signature wrongMessageVerifier = Signature.getInstance("SHA256withRSA");
        wrongMessageVerifier.initVerify(pair.getPublic());
        wrongMessageVerifier.update("different-message".getBytes(
            java.nio.charset.StandardCharsets.UTF_8
        ));
        assertFalse(wrongMessageVerifier.verify(signed));
    }
}
~~~

Test này kiểm tra cặp khóa hoạt động cùng nhau với SHA256withRSA. Trong hệ thống mới, chính sách chữ ký có thể yêu cầu RSA-PSS thay vì PKCS#1 v1.5; khi đó test phải dùng đúng thuật toán và tham số mà giao thức quy định.

Nên bổ sung negative test: xác minh chữ ký với thông điệp khác phải thất bại; xác minh bằng public key của một cặp khác cũng phải thất bại. Không cần in signature hoặc key encoding ra console khi test fail.

## 6. Kiểm tra EC và Ed25519

Với EC, test cần chỉ định named curve để không phụ thuộc mặc định provider.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import org.junit.jupiter.api.Test;

class EcKeyGenerationTest {
    @Test
    void generatedEcPairUsesExpectedCurveAndVerifies() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(
            new ECGenParameterSpec("secp256r1"),
            new SecureRandom()
        );

        KeyPair pair = generator.generateKeyPair();

        assertNotNull(pair.getPrivate());
        assertNotNull(pair.getPublic());
        assertEquals(
            256,
            ((java.security.interfaces.ECPublicKey) pair.getPublic())
                .getParams().getCurve().getField().getFieldSize()
        );

        byte[] message = "ec-key-test".getBytes(
            java.nio.charset.StandardCharsets.UTF_8
        );

        Signature signer = Signature.getInstance("SHA256withECDSA");
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signed = signer.sign();

        Signature verifier = Signature.getInstance("SHA256withECDSA");
        verifier.initVerify(pair.getPublic());
        verifier.update(message);

        assertTrue(verifier.verify(signed));
    }
}
~~~

Đối với Ed25519, test có thể dùng **KeyPairGenerator.getInstance("Ed25519")** và **Signature.getInstance("Ed25519")**. Thuật toán này có tham số cố định, vì vậy không cần khởi tạo bằng kích thước RSA hoặc EC curve. Cần kiểm tra JDK và provider đích có hỗ trợ Ed25519.

Với X25519, dùng **KeyAgreement** để kiểm tra hai cặp khóa độc lập tạo ra cùng shared secret. Không dùng Signature cho X25519. Sau khi kiểm thử thỏa thuận khóa, ứng dụng thực tế cần đưa shared secret qua KDF phù hợp trước khi sử dụng làm khóa phiên.

## 7. Kiểm tra khóa AES và HMAC

Với khóa AES, một test round-trip có thể xác minh khóa mới dùng được với AES-GCM. Nonce phải được tạo mới cho mỗi lần mã hóa bằng cùng khóa; không tái sử dụng nonce trong test chạy lặp lại hoặc fixture dùng chung.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.AEADBadTagException;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import org.junit.jupiter.api.Test;

class AesKeyGenerationTest {
    @Test
    void generatedAesKeyEncryptsAndDecrypts() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128, new SecureRandom());
        SecretKey key = generator.generateKey();

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);

        byte[] plaintext = "aes-key-test".getBytes(
            java.nio.charset.StandardCharsets.UTF_8
        );

        Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
        encryptor.init(
            Cipher.ENCRYPT_MODE,
            key,
            new GCMParameterSpec(128, nonce)
        );
        byte[] ciphertext = encryptor.doFinal(plaintext);

        Cipher decryptor = Cipher.getInstance("AES/GCM/NoPadding");
        decryptor.init(
            Cipher.DECRYPT_MODE,
            key,
            new GCMParameterSpec(128, nonce)
        );
        byte[] recovered = decryptor.doFinal(ciphertext);

        assertArrayEquals(plaintext, recovered);

        byte[] tampered = ciphertext.clone();
        tampered[0] ^= 1;

        Cipher tamperDecryptor = Cipher.getInstance("AES/GCM/NoPadding");
        tamperDecryptor.init(
            Cipher.DECRYPT_MODE,
            key,
            new GCMParameterSpec(128, nonce)
        );
        assertThrows(
            AEADBadTagException.class,
            () -> tamperDecryptor.doFinal(tampered)
        );
    }
}
~~~

Test negative cần thay đổi ciphertext hoặc AAD và xác minh giải mã bị từ chối, thường qua AEADBadTagException. Không được sử dụng plaintext trả về một phần trước khi xác thực tag thành công.

Với HMAC, sinh khóa bằng **KeyGenerator.getInstance("HmacSHA256")**, tạo tag bằng Mac, rồi xác minh bằng một Mac đã khởi tạo với cùng khóa. Test nên xác minh tag hợp lệ được chấp nhận và tag của thông điệp bị sửa bị từ chối. Dùng **MessageDigest.isEqual** để so sánh tag trong logic xác minh của ứng dụng.

## 8. Kiểm tra SecureRandom và tính duy nhất của khóa

KeyPairGenerator và KeyGenerator cần nguồn ngẫu nhiên mật mã. Test nên xác minh ứng dụng dùng SecureRandom hoặc nguồn do provider/KMS/HSM tin cậy cung cấp, đồng thời cấu hình provider đúng với môi trường.

Không dùng java.util.Random, timestamp, bộ đếm hoặc chuỗi cố định làm nguồn sinh khóa. Không tự seed SecureRandom bằng giá trị cố định trong production.

Một số test có thể sinh nhiều khóa và kiểm tra chúng không trùng nhau như một smoke test. Tuy nhiên:

- Không trùng nhau không chứng minh entropy đủ tốt.
- Một số lượng mẫu nhỏ không thể chứng minh bộ sinh ngẫu nhiên an toàn.
- Kiểm tra tần suất byte hoặc kiểm định thống kê đơn giản không thay thế đánh giá nguồn entropy.
- Test không nên yêu cầu khóa giống hệt giữa các lần chạy.

Nếu cần test thuật toán với vector xác định, hãy tách test vector khỏi test sinh khóa production. Dữ liệu ngẫu nhiên giả lập chỉ được dùng trong fixture cô lập để kiểm tra logic; không được dùng nó để đánh giá hoặc triển khai sinh khóa thực tế.

## 9. Kiểm tra provider và môi trường triển khai

JCA cho phép nhiều provider triển khai cùng một thuật toán. Kết quả test trên provider phần mềm không bảo đảm provider PKCS#11 hoặc HSM có cùng hành vi.

Cần kiểm tra:

- Thuật toán có được đăng ký trong provider thực tế không?
- Provider được chọn có đúng tên và phiên bản đã phê duyệt không?
- Provider hỗ trợ đúng tham số, curve, padding và key size không?
- KeyPairGenerator hoặc KeyGenerator có thực hiện sinh khóa trong HSM khi được yêu cầu không?
- Đối tượng khóa trả về có phải handle/opaque key không?
- Các thao tác Sign, Decrypt hoặc MAC có được thực hiện trong ranh giới thiết bị không?
- Khi HSM mất kết nối hoặc partition không sẵn sàng, ứng dụng xử lý lỗi đúng không?

Có thể ghi nhận **getProvider().getName()** và tên thuật toán trong test report. Không ghi encoded private key hoặc secret key. Với HSM, **getEncoded()** có thể trả về null vì khóa không thể xuất; đó có thể là hành vi đúng theo thiết kế.

## 10. Kiểm tra lưu trữ trong KeyStore

Sinh khóa thành công chưa chứng minh khóa đã được lưu an toàn. Integration test cần kiểm tra:

- Đúng loại entry được tạo: PrivateKeyEntry hoặc SecretKeyEntry.
- Alias đúng và không ghi đè entry khác ngoài chủ đích.
- Entry protection được áp dụng theo chính sách.
- Có thể tải lại entry bằng credential được cấp.
- Certificate chain gắn với private key đúng nếu dùng PrivateKeyEntry.
- Quyền truy cập file hoặc backend KeyStore được giới hạn.
- Test cleanup loại bỏ keystore tạm và test key sau khi hoàn tất.

Không nên dùng cùng mật khẩu keystore hoặc entry password trong mọi môi trường. Test fixture có thể tạo keystore tạm trong thư mục riêng của test runner, nhưng phải bảo đảm không đưa vào artifact hoặc commit.

Với khóa HSM-backed, KeyStore có thể chỉ chứa tham chiếu tới khóa. Test cần xác minh handle vẫn có thể thực hiện thao tác được phép sau khi tải lại provider/session, thay vì mong đợi private key được serialize thành byte.

## 11. Kiểm tra KMS/HSM và non-exportable key

Integration test với KMS/HSM cần chạy trong tài khoản, project, partition hoặc tenant thử nghiệm được cô lập. Không dùng key production để test việc tạo, xóa hoặc đổi policy.

Các tình huống nên kiểm tra:

- Tạo key với thuật toán, key size và usage đã định.
- Key ID/version và metadata được trả về đúng.
- Principal được phép thực hiện đúng operation.
- Principal không được phép bị từ chối.
- Khóa không thể export nếu policy yêu cầu non-exportable.
- Thao tác ký hoặc giải mã thành công mà không cần lấy key material về ứng dụng.
- Audit log ghi nhận actor, key ID, operation và kết quả.
- Disable, rotation và cleanup có hành vi đúng.
- Hết quota, timeout hoặc mất kết nối không khiến ứng dụng fallback sang key không được phê duyệt.

Không kiểm tra non-exportable bằng cách cố đọc nội dung khóa rồi ghi lỗi ra report. Hãy xác minh thuộc tính của key và hành vi API theo tài liệu provider; nếu gọi getEncoded() theo API được hỗ trợ, chỉ kiểm tra kết quả không xuất được mà không log đối tượng hoặc byte.

## 12. Negative test và kiểm tra policy

Negative test xác minh hệ thống từ chối cấu hình hoặc hành động không được phép.

| Tình huống | Kết quả mong đợi |
|---|---|
| Yêu cầu thuật toán không được hỗ trợ | Lỗi rõ ràng, không fallback âm thầm |
| RSA key size thấp hơn policy | Từ chối trước khi lưu hoặc kích hoạt key |
| EC curve không được phê duyệt | Từ chối tham số |
| Key usage không phù hợp với operation | Từ chối ký, giải mã hoặc thỏa thuận khóa sai mục đích |
| Principal không có quyền tạo key | Access denied và audit event |
| Alias đã tồn tại ngoài chính sách overwrite | Không ghi đè entry hiện tại |
| KeyStore password hoặc entry password sai | Không tải được entry |
| KMS/HSM unavailable | Báo lỗi vận hành, không dùng key dự phòng ngoài policy |
| HSM key export bị cấm | Không trả key material cho caller |
| Tạo key vượt quota | Trả lỗi có kiểm soát và ghi nhận sự kiện |

Negative test không nên chỉ xác minh rằng có exception. Cần kiểm tra hệ thống không tạo ra tài nguyên một phần, không ghi metadata sai, không cấp quyền rộng hơn và có thể cleanup những tài nguyên được tạo trước khi lỗi xảy ra.

## 13. Kiểm tra metadata, audit và vòng đời

Mỗi key được tạo cần có metadata đủ để quản lý trong suốt vòng đời:

- Key ID hoặc alias ổn định.
- Thuật toán và tham số.
- Key usage hoặc mục đích sử dụng.
- Owner, service, environment và classification.
- Thời điểm tạo, trạng thái và version.
- Provider, KMS key reference hoặc HSM partition.
- Policy và principal được phép sử dụng.
- Thời điểm rotation dự kiến và dependency.

Test nên xác minh event tạo khóa được ghi nhận mà không chứa key material. Các sự kiện sau đó như activate, use, rotate, disable, revoke và destroy cũng cần liên kết được với cùng key identity và version.

Một test vòng đời có thể tạo key trong môi trường tạm, xác minh operation, rotate sang version mới, kiểm tra dữ liệu cũ vẫn đọc được theo policy rồi cleanup key thử nghiệm. Không xóa key production hoặc key có dữ liệu thật phụ thuộc trong test.

## 14. Test isolation, fixture và cleanup

Test key generation thường tạo ra tài nguyên nhạy cảm. Cần quản lý chúng như tài nguyên có vòng đời:

- Mỗi test hoặc test suite có key/alias riêng, dễ nhận diện và không xung đột.
- Dùng tài khoản, namespace, HSM partition hoặc KMS project thử nghiệm riêng.
- Không dùng secret, certificate hay private key production.
- Không commit fixture chứa key material thật.
- Cleanup trong finally, @AfterEach hoặc teardown phù hợp.
- Nếu cleanup thất bại, ghi resource ID và cảnh báo; không ghi key bytes.
- Test chạy song song cần tránh dùng chung alias hoặc thay đổi policy chung.
- Đặt quota và giới hạn chi phí để test không tạo vô hạn key hoặc request KMS.

Với test HSM, không tự động xóa key nếu fixture không xác nhận quyền sở hữu và môi trường thử nghiệm. Có thể gắn tag hoặc metadata test run để cleanup chỉ chọn tài nguyên do test tạo.

## 15. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hệ quả | Cách phòng tránh |
|---|---|---|
| Chỉ kiểm tra API trả về KeyPair | Không phát hiện cặp khóa không hoạt động hoặc sai tham số | Ký/xác minh hoặc thực hiện operation tương ứng |
| Chỉ kiểm tra getAlgorithm() | Không xác minh key size, curve hay usage | Kiểm tra thuộc tính thuật toán và policy |
| Dùng provider khác production | Test pass nhưng triển khai thật thất bại | Có integration test với provider thực tế |
| Yêu cầu getEncoded() luôn có dữ liệu | Test sai với khóa HSM non-exportable | Kiểm tra metadata và thao tác qua provider |
| Dùng Random hoặc seed cố định | Tạo khóa có thể dự đoán | Dùng SecureRandom hoặc nguồn tin cậy |
| Xem khóa khác nhau là bằng chứng entropy | Đánh giá sai chất lượng RNG | Phân biệt smoke test với kiểm định entropy |
| Chỉ test happy path | Bỏ sót policy denial và cấu hình sai | Bổ sung negative test và failure injection |
| Dùng key production trong test | Có thể làm lộ hoặc phá hủy dữ liệu thật | Dùng môi trường và key thử nghiệm cô lập |
| Không cleanup test key | Tăng bề mặt tấn công và chi phí | Teardown, tag tài nguyên và theo dõi orphan |
| Log key bytes để debug | Làm lộ vật liệu khóa trong CI/log | Chỉ ghi metadata và mã lỗi an toàn |

## 16. Nguyên tắc triển khai an toàn

- Kiểm thử đúng thuật toán, key size, curve, key usage và provider theo policy.
- Dùng SecureRandom hoặc nguồn sinh khóa được KMS/HSM cung cấp; không tự xây dựng RNG.
- Xác minh cặp khóa bằng thao tác thực tế như ký/xác minh hoặc thỏa thuận khóa.
- Kiểm tra khóa đối xứng bằng encrypt/decrypt hoặc MAC/verify với tham số an toàn.
- Bổ sung negative test cho thuật toán, tham số, policy và quyền không hợp lệ.
- Có integration test với provider và KMS/HSM thực tế trong môi trường cô lập.
- Chấp nhận rằng khóa HSM có thể không xuất được; kiểm tra khả năng thao tác thay vì byte encoding.
- Không coi test sinh khóa lặp lại hoặc kiểm tra thống kê đơn giản là chứng minh entropy.
- Không ghi key material, secret hoặc plaintext vào test output, log và artifact.
- Gắn key thử nghiệm với owner và test run, cleanup có kiểm soát.
- Kiểm tra audit và metadata để truy vết key từ lúc tạo đến khi hủy.
- Tách kiểm thử chức năng khỏi chứng nhận provider, kiểm định HSM và Content QA chuyên môn.

Test key generation cần xác minh cả kết quả sinh khóa lẫn khả năng sử dụng, lưu trữ và quản lý khóa trong môi trường thực tế. Khi kết hợp unit test, cryptographic behavior test, provider/KMS/HSM integration test và negative test, đội ngũ có thể phát hiện sớm sai thuật toán, tham số, policy hoặc ranh giới bảo vệ. Những kiểm tra này hỗ trợ quy trình quản lý khóa an toàn, nhưng không thay thế đánh giá chuyên biệt về chất lượng nguồn ngẫu nhiên và mức bảo đảm của thiết bị mật mã.
