# Test old key decryption

Trong chương **Kiểm thử key management** của module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, bài học này giải thích cách kiểm tra khả năng giải mã dữ liệu được mã hóa bằng khóa cũ sau khi hệ thống đã rotation. Một rotation thành công không có nghĩa ciphertext lịch sử tự động giải mã được. Ứng dụng, KMS/HSM, metadata, provider, backup và policy phải tiếp tục nhận diện đúng key version cũ trong suốt thời gian dữ liệu còn cần được đọc hoặc phục hồi.

## 1. Test old key decryption là gì?

**Test old key decryption** là hoạt động kiểm thử xác nhận ciphertext được tạo bằng key material hoặc key version trước đây vẫn có thể được giải mã đúng theo policy hiện tại.

Kiểm thử này đặc biệt quan trọng sau:

- Rotation KEK trong KMS/HSM.
- Thay key resource hoặc chuyển alias sang key mới.
- Rotation DEK và migration dữ liệu.
- Nâng cấp JDK, JCE provider, HSM firmware hoặc KMS client.
- Thay đổi serialization, ciphertext envelope hoặc metadata format.
- Di chuyển dữ liệu sang storage, region, account hoặc hệ thống mới.
- Thay đổi key policy, grant, IAM role hoặc encryption context.
- Restore backup được tạo trước lần rotation gần nhất.

Mục tiêu không chỉ là kiểm tra thuật toán giải mã. Test cần xác nhận ứng dụng chọn đúng key ID/version, dùng đúng algorithm và parameters, khôi phục đúng plaintext, kiểm tra integrity thành công và tuân thủ quyền truy cập dành cho key cũ.

## 2. Vì sao phải kiểm thử giải mã bằng key cũ?

Sau rotation, dữ liệu cũ có thể vẫn phụ thuộc key cũ. Nếu key cũ bị xóa, disable sai, mất mapping hoặc không còn được provider hỗ trợ, dữ liệu có thể không phục hồi được dù hệ thống mã hóa dữ liệu mới đang hoạt động bình thường.

Kiểm thử old key decryption giúp:

- Phát hiện key version cũ bị mất hoặc không thể truy cập.
- Xác nhận ciphertext metadata vẫn trỏ đúng key.
- Kiểm tra KMS/HSM còn hỗ trợ decrypt/unwrap bằng version cũ.
- Phát hiện policy vô tình chặn decrypt hoặc unwrap.
- Xác minh dữ liệu backup và archive vẫn có thể phục hồi.
- Kiểm tra provider/JDK mới tương thích với ciphertext format cũ.
- Chứng minh key cũ đã được chuyển sang decrypt-only đúng cách nếu policy yêu cầu.
- Tránh destruction trước khi hết dependency và retention.

Test này là một phần của key lifecycle validation và disaster recovery testing. Một phép thử thành công trên một file nhỏ không chứng minh mọi partition, tenant, backup hoặc archive đều còn đọc được.

## 3. Phân biệt key rotation với khả năng giải mã lịch sử

Rotation thường thay key version dùng cho operation mới. Khả năng giải mã dữ liệu cũ phụ thuộc vào việc key material cũ và metadata cần thiết vẫn được giữ lại.

| Thao tác | Ảnh hưởng với dữ liệu cũ |
|---|---|
| Tạo key version mới dưới cùng logical key | KMS có thể tự chọn version cũ phù hợp khi decrypt, tùy semantics |
| Chuyển alias sang key resource mới | Ciphertext cũ có thể vẫn cần key resource cũ |
| Rotate KEK | Wrapped DEK cũ có thể cần KEK version cũ hoặc phải được rewrap |
| Rotate DEK | Ciphertext dữ liệu cũ thường vẫn cần DEK cũ cho tới khi re-encrypt xong |
| Disable key cũ | Có thể chặn decrypt lịch sử dù key material chưa bị hủy |
| Destroy key cũ | Thường làm mất khả năng giải mã ciphertext phụ thuộc key đó |
| Chuyển key cũ sang decrypt-only | Cho phép đọc dữ liệu cũ nhưng ngăn tạo ciphertext mới nếu nền tảng hỗ trợ |

Không suy luận rằng rotation đã hoàn tất thì old key có thể bị xóa. Chỉ retire hoặc destroy khi đã xác định toàn bộ dữ liệu, backup, replica, archive và chữ ký lịch sử không còn cần key đó, hoặc đã có migration được xác minh.

## 4. Các lớp cần được kiểm thử

Một bài test đầy đủ nên kiểm tra nhiều lớp:

1. **Key material:** key version cũ vẫn tồn tại và có thể được sử dụng theo policy.
2. **Key identity:** key ID/version trong metadata ánh xạ đúng tới key cũ.
3. **Cryptographic parameters:** algorithm, mode, padding, IV/nonce, tag và AAD đúng.
4. **Ciphertext format:** parser đọc đúng envelope hoặc serialization cũ.
5. **Authorization:** workload có quyền decrypt/unwrap cần thiết.
6. **Provider compatibility:** JDK/provider/HSM hỗ trợ operation và key type cũ.
7. **Data integrity:** authentication tag, checksum hoặc chữ ký được xác minh.
8. **Application behavior:** ứng dụng đọc dữ liệu cũ qua đúng code path.
9. **Backup/restore:** bản backup cũ có thể được phục hồi trong môi trường dự kiến.
10. **Audit:** operation sử dụng key cũ được ghi nhận đúng mà không lộ key material.

Một test chỉ gọi Cipher.doFinal() thành công có thể chưa kiểm tra key version resolution, tenant context, backup metadata hoặc quyền thực tế của production workload.

## 5. Xác định phạm vi dữ liệu phụ thuộc key cũ

Trước khi viết test, cần xác định key cũ đang bảo vệ loại dữ liệu nào:

- Database column, table, partition hoặc snapshot.
- Object storage, file archive hoặc document.
- Backup, replica, export và bản sao offline.
- DEK được bọc bởi KEK cũ.
- JWT, webhook signature hoặc tài liệu được ký bằng signing key cũ.
- TLS certificate/key và trust chain lịch sử.
- Secrets, credential hoặc configuration được mã hóa.
- Log archive và audit evidence.

Inventory cần liên kết data object hoặc data class với key ID, version, algorithm, thời điểm mã hóa và metadata cần để giải mã. Nếu hệ thống không lưu version tường minh, phải xác định cách KMS hoặc key resolver tìm đúng version.

Không chỉ lấy dữ liệu đang được truy cập gần đây làm test scope. Archive lâu năm, tenant ít hoạt động và backup chỉ dùng khi DR có thể là nơi duy nhất còn phụ thuộc key cũ.

## 6. Quản lý test fixture và golden ciphertext

**Test fixture** là dữ liệu mẫu được chuẩn bị để kiểm tra hành vi đã biết. Với old key decryption, fixture tốt nên được tạo bằng release cũ hoặc quy trình tương thích đã được ghi nhận, sau đó giữ nguyên ciphertext cùng metadata cần thiết.

Một fixture có thể bao gồm:

- Ciphertext nguyên bản.
- Key ID và key version.
- Algorithm, mode và padding.
- IV/nonce và authentication tag nếu được lưu tách.
- AAD hoặc encryption context.
- Format/schema version.
- Expected plaintext hoặc digest kiểm chứng.
- Phiên bản ứng dụng/provider đã tạo fixture.
- Thời điểm và mục đích tạo fixture.

Fixture cần được bảo vệ tương ứng với dữ liệu mà nó đại diện. Nếu fixture chứa ciphertext thật, vẫn cần classification, access control và retention. Expected plaintext có thể nhạy cảm; ưu tiên dữ liệu tổng hợp, vô hại hoặc digest khi chỉ cần xác nhận nội dung.

Không dùng raw production key trong source code hoặc test resource. Với test tích hợp KMS/HSM, dùng key test trong môi trường cô lập và quyền tối thiểu. Nếu cần kiểm thử khả năng đọc dữ liệu production, thực hiện qua quy trình được phê duyệt với dữ liệu được chọn lọc và audit đầy đủ.

## 7. Vì sao round-trip test chưa đủ?

Một round-trip test thường làm:

~~~text
plaintext -> encrypt bằng key hiện tại -> decrypt bằng key hiện tại
~~~

Nó chứng minh cặp encrypt/decrypt hiện tại hoạt động, nhưng không chứng minh:

- Code mới đọc được ciphertext do release cũ tạo.
- Key resolver chọn đúng version cũ.
- Metadata cũ được parse đúng.
- KMS/HSM vẫn cho phép decrypt bằng old key.
- Backup cũ có đủ IV, tag, AAD và wrapped DEK.
- Provider mới tương thích với format hoặc parameter cũ.

Vì vậy cần **cross-version test**: tạo fixture bằng implementation/version trước đó rồi dùng implementation hiện tại giải mã. Khi có nhiều format lịch sử, cần fixture đại diện cho từng format còn được hỗ trợ.

## 8. Quy trình kiểm thử cơ bản

Một test plan có thể thực hiện theo thứ tự:

1. Chọn key cũ và xác định owner, purpose, version cùng trạng thái.
2. Chọn fixture ciphertext được tạo trước rotation.
3. Đọc metadata từ đúng nguồn mà ứng dụng production sử dụng.
4. Xác minh key resolver trả về đúng key ID/version cũ.
5. Kiểm tra principal test có quyền decrypt/unwrap phù hợp.
6. Thực hiện giải mã bằng đúng provider và parameters.
7. So sánh plaintext với expected result hoặc kiểm tra digest.
8. Xác minh authentication tag/AAD/integrity.
9. Ghi audit result và thời gian operation.
10. Thực hiện negative test với key/version/context sai.
11. Lặp lại trên các loại dữ liệu và backup quan trọng.
12. Ghi rõ key cũ cần tiếp tục giữ, có thể retire hay đã đủ điều kiện destruction.

Test phải chạy trong môi trường gần với môi trường thực tế về JDK, provider, policy, identity, network, KMS/HSM và storage. Mock có ích cho unit test nhưng không thay thế integration test.

## 9. Test key version resolution

Một lỗi thường gặp là ciphertext lưu key ID nhưng không lưu version, hoặc ứng dụng dùng alias đã chuyển sang key mới. Nếu resolver chọn sai key, decrypt có thể thất bại hoặc ứng dụng có thể thử nhiều key không kiểm soát.

Test cần xác minh:

- Metadata old ciphertext chứa đúng key identifier.
- Version tường minh được ưu tiên khi format yêu cầu.
- Alias resolution tuân theo semantics của KMS.
- Key resolver không tự thay old key bằng current key khi decrypt thất bại.
- Key ID thuộc đúng tenant, purpose và environment.
- Không thử một danh sách key tùy ý hoặc key thuộc tenant khác.
- Khi key version không tồn tại, ứng dụng trả lỗi rõ ràng và audit.

Nếu KMS quản lý nhiều material version dưới logical key, test cần xác minh dịch vụ chọn đúng material cũ theo ciphertext metadata. Nếu nền tảng không expose version, ghi nhận semantics và test bằng ciphertext thực tế được tạo trước rotation.

## 10. Test quyền decrypt-only cho old key

Trong nhiều hệ thống, key cũ cần tiếp tục decrypt dữ liệu lịch sử nhưng không được dùng để mã hóa dữ liệu mới. Đây là mô hình decrypt-only hoặc retired-use policy.

Test positive:

- Workload đọc dữ liệu cũ được phép decrypt.
- Backup recovery role được phép unwrap theo scope đã cấp.
- KMS/HSM chọn đúng key version cũ.

Test negative:

- Workload không được encrypt dữ liệu mới bằng key cũ.
- Workload không được sign message mới bằng signing key đã retire.
- Workload không được export key material.
- Principal ngoài scope không được decrypt.
- Tenant A không được dùng context của tenant B.
- Key đã disable hoặc bị revoke phải bị từ chối theo policy.

Tên action và trạng thái cụ thể phụ thuộc nền tảng. Một số KMS chỉ có trạng thái enabled/disabled ở cấp logical key, không hỗ trợ decrypt-only trực tiếp cho từng version. Khi đó phải thực thi giới hạn ở policy, grant, alias, key version hoặc application layer phù hợp.

## 11. Test AES-GCM ciphertext cũ trong Java

Với AES-GCM, decrypt cần đúng key, nonce, authentication tag và AAD. Java JCA thường nhận ciphertext nối với authentication tag qua doFinal; nonce được truyền bằng GCMParameterSpec, AAD được truyền qua updateAAD.

Ví dụ phương thức decrypt:

~~~java
import java.security.GeneralSecurityException;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class LegacyAesGcmDecryptor {
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    public static byte[] decrypt(
            SecretKey oldKey,
            byte[] nonce,
            byte[] ciphertextAndTag,
            byte[] aad) throws GeneralSecurityException {

        if (oldKey == null || nonce == null
                || nonce.length != NONCE_BYTES
                || ciphertextAndTag == null
                || ciphertextAndTag.length < TAG_BITS / 8) {
            throw new IllegalArgumentException("Invalid encrypted payload");
        }

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE,
                oldKey,
                new GCMParameterSpec(TAG_BITS, nonce));

        if (aad != null && aad.length > 0) {
            cipher.updateAAD(aad);
        }

        // doFinal verifies the authentication tag before returning plaintext.
        return cipher.doFinal(ciphertextAndTag);
    }
}
~~~

Đoạn code minh họa giả định format fixture lưu nonce riêng và ciphertext nối với tag. Nếu format cũ lưu nonce/tag theo cấu trúc khác, adapter phải parse đúng format trước khi gọi decrypt. Không tự suy đoán nonce hoặc AAD từ ciphertext.

Với GCM, nếu tag không hợp lệ hoặc AAD sai, doFinal thường ném AEADBadTagException. Không trả plaintext một phần, không bỏ qua lỗi tag và không tự thử một key khác mà không có metadata đáng tin cậy.

## 12. Ví dụ JUnit cho fixture được tạo bởi release cũ

Test nên lấy key version từ một resolver test được cấu hình rõ ràng. Không hard-code raw key bytes trong test:

~~~java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import org.junit.jupiter.api.Test;
import javax.crypto.SecretKey;

class LegacyAesGcmDecryptorTest {
    private final TestKeyResolver keyResolver =
            TestKeyResolver.fromTestKeyStore();

    @Test
    void decryptsFixtureCreatedBeforeRotation() throws Exception {
        LegacyFixture fixture =
                LegacyFixture.load("fixtures/aes-gcm-v1.bin");

        SecretKey oldKey = keyResolver.resolve(
                fixture.keyId(),
                fixture.keyVersion());

        byte[] actual = LegacyAesGcmDecryptor.decrypt(
                oldKey,
                fixture.nonce(),
                fixture.ciphertextAndTag(),
                fixture.aad());

        assertArrayEquals(fixture.expectedPlaintext(), actual);
    }
}
~~~

TestKeyResolver và LegacyFixture là abstraction minh họa, không phải API có sẵn trong JUnit hoặc JCA. Trong dự án thực tế, resolver có thể gọi KMS/HSM integration test service hoặc đọc key test từ một keystore được bảo vệ.

Test này có giá trị khi fixture được tạo bởi release cũ và được giữ nguyên. Nếu test tự tạo fixture ngay trước khi decrypt bằng cùng implementation mới, nó chỉ là round-trip test.

## 13. Test negative cases và tampering

Old key decryption test cần chứng minh hệ thống từ chối dữ liệu không hợp lệ:

- Sai key version hoặc key ID.
- Sai key material.
- Sai nonce/IV.
- Ciphertext bị thay đổi.
- Authentication tag bị thay đổi hoặc cắt cụt.
- AAD/encryption context không khớp.
- Ciphertext format version không được hỗ trợ.
- Key đã disable, revoke hoặc không còn quyền sử dụng.
- Principal thuộc tenant khác.
- Algorithm hoặc parameters bị thay đổi ngoài metadata được phép.

Với AEAD như AES-GCM, thay đổi ciphertext, nonce hoặc AAD phải làm xác minh tag thất bại. Với chế độ mã hóa không xác thực như CBC, cần có integrity protection riêng và test phải kiểm tra MAC/chữ ký trước khi tin plaintext; padding hợp lệ không chứng minh ciphertext không bị sửa.

Negative test không được biến thành cơ chế thử mọi key cho đến khi một key giải mã thành công. Chọn key dựa trên authenticated metadata và policy, không dựa vào việc plaintext “trông có vẻ đúng”.

## 14. Test envelope encryption và old KEK

Trong envelope encryption, dữ liệu được mã hóa bằng DEK; DEK được bọc bằng KEK. Sau KEK rotation, ciphertext dữ liệu có thể vẫn giữ nguyên nhưng wrapped DEK vẫn phụ thuộc KEK version cũ.

Test nên xác minh:

1. Fixture chứa ciphertext, wrapped DEK, KEK ID/version và encryption context.
2. Resolver chọn đúng KEK cũ hoặc logical key có version semantics phù hợp.
3. KMS/HSM unwrap được DEK cũ.
4. DEK được sử dụng để decrypt ciphertext.
5. AEAD tag/AAD hoặc integrity metadata được xác minh.
6. Plaintext khớp expected result.
7. Principal chỉ có quyền unwrap trong scope cần thiết.
8. Key cũ không được dùng để wrap DEK mới nếu policy đã chuyển sang version mới.

Nếu workflow đã rewrap DEK bằng KEK mới, cần giữ fixture của trạng thái trước rewrap để test đường phục hồi lịch sử. Đồng thời kiểm tra metadata mới vẫn liên kết đúng wrapped DEK với KEK version mới.

Không log DEK plaintext, KEK bytes hoặc wrapped key bytes. Test report chỉ nên chứa fixture ID, key ID/version, operation, result và correlation reference.

## 15. Test backup và restore bằng old key

Backup có thể được tạo trước nhiều lần rotation và chỉ được restore sau nhiều tháng. Vì vậy, test restore cần mô phỏng đầy đủ metadata lịch sử:

- Backup manifest và format version.
- Ciphertext hoặc snapshot.
- Wrapped DEK và KEK ID/version.
- IV/nonce, tag, AAD/encryption context.
- Provider/JDK compatibility.
- Key policy và identity của recovery workload.
- Mapping tenant, region và storage location.

Quy trình test:

1. Chọn backup cũ đại diện cho từng thời kỳ/format.
2. Restore vào môi trường cô lập.
3. Dùng identity recovery có quyền tối thiểu.
4. Giải mã/unwrap bằng old key path.
5. Kiểm tra integrity, checksum và dữ liệu nghiệp vụ.
6. Ghi thời gian phục hồi so với RTO/RPO.
7. Xác minh audit log và key version đã được dùng.
8. Xóa dữ liệu test theo retention và sanitization policy.

Không chỉ kiểm tra rằng backup file tồn tại hoặc KMS báo key enabled. Chỉ một restore thực tế mới xác nhận cả chuỗi dependency hoạt động.

## 16. Test sau nâng cấp JDK hoặc provider

Một bản nâng cấp JDK/provider có thể thay đổi thuật toán được phép, transformation support, key format, parameter handling hoặc security constraints.

Regression suite cần:

- Giải mã golden fixture từ từng format cũ còn được hỗ trợ.
- Kiểm tra transformation và parameter spec chính xác.
- Xác minh provider được chọn đúng theo policy.
- Kiểm tra key type, size và encoding.
- Kiểm tra certificate path hoặc signature verification nếu có.
- Xác minh crypto policy không chặn thuật toán lịch sử cần đọc.
- Kiểm tra lỗi được báo rõ khi thuật toán đã bị cấm theo policy.

Không nới lỏng algorithm constraints chỉ để test cũ chạy qua. Nếu dữ liệu dùng thuật toán không còn được chấp thuận, cần đánh giá migration/re-encryption trong môi trường được kiểm soát, ghi nhận ngoại lệ và deadline.

## 17. Test old signing key verification

Với asymmetric signing key, dữ liệu lịch sử thường cần public key cũ để verify chữ ký. Test cần:

- Giữ public key/certificate cũ hoặc trust metadata tương ứng.
- Xác minh chữ ký được tạo trước rollover.
- Kiểm tra issuer, certificate chain, validity và timestamp theo policy lịch sử.
- Xác minh key ID/kid ánh xạ đúng public key.
- Từ chối chữ ký sai, payload bị sửa hoặc key không đáng tin.
- Đảm bảo private key cũ không còn quyền sign dữ liệu mới nếu đã retire.

Với HMAC, verifier cần shared secret cũ và do đó cũng có khả năng tạo MAC. Không thể tách quyền verify khỏi quyền sign chỉ bằng cách đặt tên operation khác nếu cùng secret được dùng. Policy cần giới hạn consumer và cân nhắc chuyển sang chữ ký bất đối xứng nếu nhiều bên chỉ cần verify.

## 18. Test policy, authorization và key state

Khả năng giải mã về mặt mật mã chưa đủ nếu authorization sai. Cần test cả:

| Tình huống | Kết quả mong đợi |
|---|---|
| Recovery workload đúng scope, old key còn decrypt permission | Allow |
| Application không có quyền đọc dữ liệu lịch sử | Deny |
| Principal thuộc tenant khác | Deny |
| Key cũ ở trạng thái decrypt-only theo policy | Decrypt allow, encrypt deny |
| Key bị disable hoặc revoked | Deny theo key state/policy |
| Key version không tồn tại | Lỗi rõ ràng, không fallback tùy tiện |
| Encryption context sai | Deny hoặc authentication failure |
| Export old key material | Deny nếu policy cấm export |
| Audit sink unavailable | Xử lý theo policy vận hành, không âm thầm bỏ audit |

Test phải chạy với workload identity tương tự production. Dùng administrator credential trong test có thể che giấu lỗi vì admin thường có quyền rộng hơn ứng dụng thật.

## 19. Test key retention và destruction guard

Một trong những mục đích của old key decryption test là ngăn key bị destroy trước khi hết dependency.

Có thể tự động hóa guard:

1. Inventory liệt kê ciphertext, backup và archive còn phụ thuộc key version.
2. Test suite giải mã các fixture đại diện bằng key version đó.
3. Recovery owner xác nhận backup/restore đã đạt.
4. Consumer telemetry không còn operation ngoài policy.
5. Retention/legal hold đã được kiểm tra.
6. Chỉ sau khi tất cả điều kiện đạt mới cho phép retire/destroy theo approval.

Test pass không tự động chứng minh không còn dữ liệu phụ thuộc. Fixture chỉ đại diện cho tập dữ liệu đã chọn. Cần kết hợp inventory scan, dependency mapping, backup records và owner attestation.

Không tự động destroy key cũ chỉ vì test suite thành công. Destruction là quyết định vòng đời riêng, cần policy và bằng chứng đầy đủ.

## 20. Quản lý test data và key test an toàn

Test cần dùng dữ liệu và key phù hợp:

- Ưu tiên synthetic plaintext và key test được tạo riêng.
- Không copy production key vào unit test hoặc CI environment.
- Không lưu password, raw key, DEK hoặc private key trong repository.
- Bảo vệ fixture ciphertext nếu nó chứa dữ liệu thật hoặc metadata nhạy cảm.
- Hạn chế quyền truy cập test KMS/HSM và tách môi trường.
- Xóa test plaintext và temporary files theo policy.
- Không ghi plaintext vào test failure output hoặc CI artifact.
- Dùng secret manager hoặc HSM test partition nếu cần integration test.
- Không dùng cùng key test giữa nhiều pipeline không liên quan nếu điều đó làm tăng blast radius.

Nếu test cần xác nhận dữ liệu production có thể giải mã, dùng quy trình được phê duyệt, giới hạn record, tránh xuất plaintext và ghi audit. Không biến test runner thành nơi tập trung bản sao key material.

## 21. Các chỉ số và bằng chứng cần lưu

Một test report nên lưu:

- Test suite/build ID và code version.
- Fixture ID và ciphertext format version.
- Key ID/version được yêu cầu và key version thực tế đã dùng nếu nguồn cung cấp.
- Algorithm, provider và JDK version.
- Environment, region và workload identity.
- KMS/HSM request/correlation ID.
- Kết quả decrypt, integrity verification và plaintext comparison.
- Thời gian thực hiện và mã lỗi.
- Kết quả positive/negative/restore test.
- Người review và thời điểm.

Không lưu raw key material, password, plaintext hoặc wrapped DEK trong report. Nếu cần chứng minh plaintext đúng, có thể so sánh trong bộ nhớ và chỉ lưu kết quả boolean hoặc digest phù hợp với threat model.

## 22. Ví dụ ma trận kiểm thử

| Test case | Input | Kết quả mong đợi |
|---|---|---|
| Legacy fixture decrypt | Ciphertext tạo bởi release cũ, key version cũ | Plaintext đúng |
| Current implementation compatibility | Fixture cũ đọc bằng JDK/provider hiện tại | Thành công theo format được hỗ trợ |
| Wrong key version | Metadata trỏ version không đúng | Từ chối hoặc lỗi rõ ràng |
| Wrong AAD | Ciphertext đúng nhưng context sai | Authentication failure |
| Tampered ciphertext | Một byte ciphertext bị thay đổi | Authentication failure |
| Tampered tag | Tag bị thay đổi | Authentication failure |
| Old key decrypt-only | Decrypt dữ liệu cũ | Allow |
| Old key encrypt | Tạo ciphertext mới bằng key đã retire | Deny |
| Tenant isolation | Context thuộc tenant khác | Deny/failure |
| KMS permission revoked | Workload mất quyền decrypt | Deny và audit |
| Backup restore | Backup trước rotation | Restore và integrity check đạt |
| Old signing key verify | Signature lịch sử | Verify theo policy |
| Destroy guard | Còn dependency trong inventory | Không cho destruction |
| Missing key metadata | Ciphertext thiếu key ID/version bắt buộc | Fail closed, không thử key tùy ý |

Ma trận cần được điều chỉnh theo loại key, thuật toán, format và yêu cầu lưu trữ. Không phải test case nào cũng áp dụng cho mọi hệ thống; ghi rõ lý do loại trừ để tránh khoảng trống kiểm thử.

## 23. Troubleshooting khi old key decryption thất bại

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Key not found | Version/resource đã bị retire hoặc metadata sai | Kiểm tra key inventory, ID/version mapping và retention |
| Access denied | Principal, grant hoặc key policy không cho decrypt | Kiểm tra workload identity, action, context và audit decision |
| InvalidKeyException | Key type/size/format không tương thích | Kiểm tra provider, key encoding và key metadata |
| NoSuchAlgorithm/NoSuchPadding | JDK/provider không còn hỗ trợ transformation | Kiểm tra provider và crypto policy; lập kế hoạch migration nếu thuật toán yếu |
| AEADBadTagException | Sai key, nonce, tag, AAD hoặc ciphertext bị sửa | Xác minh fixture metadata và integrity; không bỏ qua tag |
| Padding error | Sai key, ciphertext hỏng hoặc parameters không khớp | Kiểm tra format, IV, padding và nguồn ciphertext |
| Decrypt được nhưng dữ liệu sai | Metadata/encoding hoặc application parsing lỗi | So sánh fixture version, encoding và checksum |
| Backup restore thất bại | Thiếu wrapped DEK, old KEK hoặc context | Kiểm tra manifest, backup metadata và key retention |
| Chỉ một region thất bại | Replica, policy hoặc provider khác nhau | So sánh key version, IAM, KMS endpoint và configuration |

Khi lỗi xảy ra, giữ nguyên ciphertext gốc và metadata để điều tra. Không overwrite dữ liệu bằng một lần mã hóa thử hoặc tự chọn key khác cho tới khi plaintext trông hợp lý.

## 24. Quy trình điều tra theo thứ tự

1. Xác nhận fixture/object ID và nguồn ciphertext.
2. Đọc format version, key ID/version và algorithm metadata.
3. Kiểm tra key cũ còn tồn tại, enabled và có decrypt permission không.
4. Xác nhận workload identity và authorization context.
5. Xác nhận provider, JDK, transformation, nonce/IV, tag, AAD và encoding.
6. Đối chiếu với golden fixture hoặc test vector của release tạo dữ liệu.
7. Kiểm tra KMS/HSM audit để biết key version thực tế được gọi.
8. Kiểm tra backup/replica và khả năng phục hồi nếu key/resource bị mất.
9. Ghi lại kết quả và mở incident nếu có dấu hiệu integrity failure hoặc key loss.

Không ghi plaintext hoặc key bytes vào log khi điều tra. Nếu cần xem nội dung, dùng môi trường kiểm soát, dữ liệu tổng hợp hoặc phương pháp so sánh trong bộ nhớ.

## 25. Những sai lầm thường gặp

- **Chỉ test round-trip bằng key mới:** không kiểm tra khả năng đọc ciphertext lịch sử.
- **Tạo fixture bằng code hiện tại:** không chứng minh tương thích ngược với format cũ.
- **Không lưu key version trong metadata:** resolver có thể chọn sai key sau rotation.
- **Dùng alias mới để giải mã mọi ciphertext:** alias có thể không trỏ tới key resource cũ.
- **Xóa old key ngay sau rotation:** backup và archive có thể không còn phục hồi được.
- **Chỉ mock KMS/HSM:** bỏ qua policy, identity, provider và network thực tế.
- **Dùng admin credential trong test:** che giấu thiếu quyền của application workload.
- **Bỏ qua AAD hoặc encryption context:** ciphertext có thể không xác thực đúng tenant/purpose.
- **Bỏ qua AEAD tag failure:** có thể chấp nhận dữ liệu bị sửa.
- **Thử nhiều key cho đến khi decrypt được:** che giấu metadata sai và mở rộng phạm vi truy cập.
- **Dùng production key trong CI:** tăng nguy cơ lộ key material.
- **Chỉ test dữ liệu đang hoạt động:** bỏ sót backup, archive và tenant ít truy cập.
- **Cho rằng test pass đủ để destroy key:** fixture không chứng minh hết dependency.
- **Không test sau JDK/provider upgrade:** có thể làm hỏng khả năng đọc dữ liệu cũ.

## 26. Checklist test old key decryption

- [ ] Đã lập inventory dữ liệu còn phụ thuộc key version cũ.
- [ ] Fixture được tạo bởi release/format cũ và có nguồn gốc rõ ràng.
- [ ] Fixture giữ key ID/version, algorithm, nonce/IV, tag, AAD và format metadata.
- [ ] Test dùng implementation, JDK và provider dự kiến triển khai.
- [ ] Resolver chọn đúng old key/version; không fallback tùy tiện.
- [ ] Positive test xác nhận plaintext hoặc digest đúng.
- [ ] Negative test bao gồm wrong key, wrong AAD, tampering và authorization denial.
- [ ] Old key decrypt-only được kiểm tra cả allow và deny operation.
- [ ] Envelope encryption test xác minh unwrap DEK bằng KEK cũ.
- [ ] Backup/restore test thực hiện trên bản backup trước rotation.
- [ ] Signing/certificate history được verify nếu có dependency.
- [ ] Test chạy với workload identity gần production.
- [ ] Không có raw key, secret hoặc plaintext trong source, log và CI artifact.
- [ ] Audit ghi key ID/version, provider, request ID và kết quả.
- [ ] Có kiểm tra dependency trước khi retire/destroy old key.
- [ ] Kết quả test được review và liên kết với change/rotation record.

Test old key decryption chứng minh hệ thống vẫn đọc được dữ liệu được tạo trước rotation trong phạm vi fixture và dependency đã kiểm tra. Một test có giá trị phải dùng ciphertext lịch sử, metadata đầy đủ, đúng key version, đúng provider và workload identity thực tế; đồng thời xác minh integrity, backup/restore và các trường hợp bị từ chối. Giữ key cũ tới khi dữ liệu, archive và backup không còn phụ thuộc hoặc đã được migration có kiểm chứng. Không dùng một lần round-trip thành công làm bằng chứng rằng có thể hủy key cũ.
