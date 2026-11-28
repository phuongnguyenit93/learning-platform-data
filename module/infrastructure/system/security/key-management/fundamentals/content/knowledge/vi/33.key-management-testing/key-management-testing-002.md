# Test key storage

Test key storage là quá trình kiểm thử cách hệ thống lưu trữ, bảo vệ, truy xuất, duy trì và khôi phục khóa mật mã trong suốt vòng đời của chúng. Phạm vi kiểm thử có thể gồm Java KeyStore trên filesystem, secret store của nền tảng, KMS hoặc HSM. Mục tiêu là chứng minh key material chỉ được truy cập bởi principal được phép, không bị lộ hoặc sửa trái phép, vẫn dùng được sau restart/restore và được xử lý đúng khi disable, rotate hoặc revoke.

Trong module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, kiểm thử key storage nối các khái niệm lưu trữ khóa, kiểm soát truy cập, backup/recovery, KMS/HSM và audit. Một file KeyStore mở được chưa đủ chứng minh hệ thống lưu trữ an toàn. Cần kiểm tra cả confidentiality, integrity, authorization, persistence, recovery và hành vi khi có lỗi.

## 1. Mục tiêu của kiểm thử key storage

Khóa mật mã thường là tài sản có giá trị cao. Nếu private key, secret key hoặc key-encryption key bị lộ, attacker có thể giải mã dữ liệu, giả mạo chữ ký hoặc mở rộng quyền truy cập. Nếu khóa bị mất hoặc không thể khôi phục, dữ liệu được mã hóa có thể trở nên không thể sử dụng.

Kiểm thử key storage cần trả lời:

- Khóa có được lưu đúng nơi và đúng định dạng đã phê duyệt không?
- Key material có được bảo vệ khi lưu trên đĩa, trong backup và khi truyền tới nơi lưu trữ không?
- Chỉ workload hoặc operator được ủy quyền mới có thể truy cập key không?
- Người không có quyền có bị từ chối khi đọc, export, thay đổi hoặc xóa key không?
- Dữ liệu lưu trữ có phát hiện được việc sửa đổi hoặc hỏng không?
- Khóa có còn truy cập được sau restart, failover và restore không?
- Rotation, disable, revoke và destroy có tạo ra trạng thái mong đợi không?
- Audit log có ghi lại thao tác mà không làm lộ key material không?

## 2. Phân biệt các mô hình lưu trữ khóa

Các mô hình lưu trữ có ranh giới bảo mật và cách kiểm thử khác nhau:

| Mô hình | Vật liệu được lưu | Điểm cần kiểm thử |
|---|---|---|
| Java KeyStore file | Private key, secret key hoặc trusted certificate tùy provider/format | Password protection, file permission, integrity, backup và khả năng load |
| OS keystore / platform keystore | Key object do hệ điều hành hoặc nền tảng quản lý | Quyền theo user/process, isolation, lifecycle và API export |
| KMS | Key material hoặc key operation được dịch vụ quản lý | IAM/key policy, API authorization, audit, versioning, availability và recovery |
| HSM | Key object trong thiết bị hoặc partition được bảo vệ | Non-extractability, object attributes, login, role separation, backup/restore và audit |
| Secret manager | Password, token hoặc secret; có thể dùng KMS để mã hóa khi lưu | Workload authorization, encryption at rest, versioning, rotation và access log |

Không nên dùng cùng một test suite cho mọi loại storage. Ví dụ, kiểm tra permission của file không chứng minh HSM không cho export private key; ngược lại, kiểm tra HSM object attribute không chứng minh backup file của ứng dụng được bảo vệ.

## 3. Các lớp cần kiểm thử

Một chiến lược kiểm thử toàn diện có thể chia thành các lớp:

1. **Confidentiality:** key material không xuất hiện trong file, log, dump hoặc backup ngoài dự kiến.
2. **Integrity:** dữ liệu KeyStore hoặc metadata key bị sửa phải được phát hiện.
3. **Authentication và authorization:** chỉ principal được phép mới có thể load, đọc, dùng hoặc quản trị key.
4. **Persistence:** key vẫn tồn tại và dùng được sau khi đóng ứng dụng, restart hoặc reconnect.
5. **Recovery:** backup có thể khôi phục theo đúng quy trình và quyền phê duyệt.
6. **Lifecycle:** rotation, disable, revoke và destroy tạo ra trạng thái đúng.
7. **Auditability:** thao tác nhạy cảm được ghi nhận với actor, resource, action và kết quả.
8. **Resilience:** hệ thống xử lý đúng khi storage, KMS hoặc HSM không khả dụng.

~~~mermaid
flowchart TD
    A[Test key storage] --> B[Confidentiality]
    A --> C[Integrity]
    A --> D[Access control]
    A --> E[Persistence]
    A --> F[Backup and recovery]
    A --> G[Lifecycle]
    A --> H[Audit and resilience]
    B --> I[Evidence and test result]
    C --> I
    D --> I
    E --> I
    F --> I
    G --> I
    H --> I
~~~

## 4. Kiểm thử Java KeyStore trên filesystem

Java KeyStore API cung cấp lớp java.security.KeyStore để thao tác với kho khóa theo loại keystore và provider. Với ứng dụng mới, PKCS12 thường là lựa chọn phù hợp nhờ tính chuẩn hóa và khả năng tương tác. JKS là định dạng Java cũ; chỉ tiếp tục dùng khi có yêu cầu tương thích cụ thể.

Các test cơ bản cho file KeyStore:

- Tạo keystore mới và lưu xuống vị trí tạm trong test.
- Load lại bằng đúng store password.
- Xác nhận alias, entry type và certificate/key metadata mong đợi.
- Load bằng password sai và xác minh thao tác thất bại.
- Thử đọc key entry bằng entry password sai.
- Sửa một bản sao file và xác minh lỗi integrity/load được phát hiện.
- Kiểm tra quyền filesystem để user/process ngoài phạm vi không đọc hoặc ghi được file.

Không dùng keystore production trong unit test. Tạo key và store dùng riêng cho test, lưu trong thư mục tạm, rồi xóa sau khi test hoàn tất theo khả năng của hệ điều hành.

## 5. Ví dụ kiểm thử lưu và load secret key bằng PKCS12

Ví dụ dưới đây minh họa vòng đời lưu và đọc một AES key trong PKCS12. Khả năng lưu SecretKeyEntry phụ thuộc JDK và provider; nếu provider không hỗ trợ, test phải ghi nhận capability đó và dùng loại entry được hỗ trợ, chẳng hạn PrivateKeyEntry với certificate chain trong fixture kiểm thử.

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Key;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class KeyStoreStorageTestExample {
    public static void main(String[] args) throws Exception {
        char[] storePassword = loadTestPassword();
        char[] entryPassword = loadTestPassword();
        Path file = Files.createTempFile("keystore-test-", ".p12");

        try {
            KeyGenerator generator = KeyGenerator.getInstance("AES");
            generator.init(256);
            SecretKey originalKey = generator.generateKey();

            KeyStore store = KeyStore.getInstance("PKCS12");
            store.load(null, storePassword);
            store.setEntry(
                    "test-data-key",
                    new KeyStore.SecretKeyEntry(originalKey),
                    new KeyStore.PasswordProtection(entryPassword));

            try (var output = Files.newOutputStream(file)) {
                store.store(output, storePassword);
            }

            KeyStore loaded = KeyStore.getInstance("PKCS12");
            try (var input = Files.newInputStream(file)) {
                loaded.load(input, storePassword);
            }

            if (!loaded.isKeyEntry("test-data-key")) {
                throw new AssertionError("Key entry is missing");
            }

            Key recovered = loaded.getKey("test-data-key", entryPassword);
            if (!(recovered instanceof SecretKey recoveredKey)) {
                throw new AssertionError("Unexpected key entry type");
            }

            byte[] nonce = new byte[12];
            new SecureRandom().nextBytes(nonce);
            byte[] plaintext = "storage round-trip".getBytes(
                    java.nio.charset.StandardCharsets.UTF_8);

            Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
            encryptor.init(
                    Cipher.ENCRYPT_MODE,
                    recoveredKey,
                    new GCMParameterSpec(128, nonce));
            byte[] ciphertext = encryptor.doFinal(plaintext);

            Cipher decryptor = Cipher.getInstance("AES/GCM/NoPadding");
            decryptor.init(
                    Cipher.DECRYPT_MODE,
                    originalKey,
                    new GCMParameterSpec(128, nonce));
            byte[] recoveredPlaintext = decryptor.doFinal(ciphertext);

            if (!Arrays.equals(plaintext, recoveredPlaintext)) {
                throw new AssertionError("Key storage round-trip failed");
            }
        } finally {
            Arrays.fill(storePassword, '\0');
            Arrays.fill(entryPassword, '\0');
            Files.deleteIfExists(file);
        }
    }

    private static char[] loadTestPassword() {
        // Test fixture only. Production secrets must come from a protected source.
        return "test-only-password-change-me".toCharArray();
    }
}
~~~

Đây là ví dụ minh họa, không phải mẫu quản lý password production. Test nên dùng password fixture ngẫu nhiên hoặc secret test được cấp từ môi trường kiểm thử, không hardcode password thật. Đoạn mã so sánh hành vi bằng phép mã hóa/giải mã; nó không in key bytes. Trong test thực tế, cần đóng/xóa file tạm ngay cả khi assertion thất bại và xác minh provider đang dùng đúng loại PKCS12 mong muốn.

Nếu test chạy trên Java version không hỗ trợ cú pháp pattern matching cho instanceof, thay bằng kiểm tra kiểu và cast theo cú pháp Java tương ứng. var trong ví dụ yêu cầu Java 10 trở lên.

## 6. Kiểm thử password, integrity và tampering

Với file-backed keystore, nên có test âm:

| Test case | Thao tác | Kết quả mong đợi |
|---|---|---|
| Đúng store password | Load file bằng password đúng | Load thành công |
| Sai store password | Load file bằng password sai | Load thất bại |
| Sai entry password | Lấy private/secret key bằng password sai | Không lấy được key |
| File bị cắt cụt | Xóa bớt byte trong bản sao file | Load thất bại hoặc báo định dạng không hợp lệ |
| File bị sửa | Thay đổi byte trong bản sao | Integrity check/load phát hiện lỗi nếu format/provider bảo vệ nội dung đó |
| Alias không tồn tại | Truy xuất alias không có | Trả kết quả không tồn tại hoặc lỗi theo API |
| Entry type sai | Đọc certificate entry như key entry | Ứng dụng xử lý đúng loại entry, không dùng nhầm |

Không nên assert chính xác nội dung exception message vì message có thể khác giữa JDK/provider. Hãy kiểm tra loại lỗi hoặc kết quả thất bại theo hợp đồng API. Chỉ thao tác trên bản sao file test; không sửa trực tiếp kho khóa đang được dịch vụ sử dụng.

Password của keystore có thể được dùng để bảo vệ nội dung và/hoặc kiểm tra integrity tùy format/provider. Không suy ra mức bảo vệ chỉ từ việc file load được khi nhập password. Cần biết thuật toán PBE/MAC và tham số mà provider thực tế sử dụng, cũng như giới hạn password.

## 7. Kiểm thử quyền filesystem và bảo mật file

File keystore cần được bảo vệ như key material. Kiểm thử cần xác minh:

- File thuộc user/service account đúng.
- Chỉ owner hoặc nhóm được phê duyệt có quyền đọc.
- Chỉ tiến trình quản trị hoặc quy trình rotation được phép ghi/xóa.
- Thư mục cha không cho user khác thay thế file bằng symlink hoặc file giả.
- File tạm, bản copy, backup và crash dump không làm lộ keystore.
- Quyền không bị mở rộng sau khi deploy, restore hoặc copy sang host khác.

Trên Linux, quyền như 0600 cho file và 0700 cho thư mục riêng có thể là điểm khởi đầu, nhưng cần xét owner/group, ACL, SELinux/AppArmor, container volume và hệ thống file. Trên Windows, cần kiểm tra NTFS ACL, inherited permissions, service identity và quyền truy cập của backup agent.

Không chỉ kiểm tra permission ngay sau khi tạo file. Cần kiểm tra cả sau khi triển khai, rotation, restore và thay đổi owner. File permission tốt không bảo vệ được key nếu password nằm trong cùng thư mục hoặc log.

## 8. Kiểm thử KMS storage và API access

Với KMS, key material thường được dịch vụ quản lý; ứng dụng thao tác qua API thay vì đọc file key. Kiểm thử nên tập trung vào policy và hành vi API:

- Principal hợp lệ có thể thực hiện đúng action trên đúng key.
- Principal không hợp lệ bị từ chối.
- Quyền Decrypt không tự động kéo theo quyền quản trị hoặc export key.
- Key policy, IAM policy, grant và condition được áp dụng như mong đợi.
- Key version/rotation metadata được trả về hoặc liên kết đúng với ciphertext.
- Disable/revoke key làm thao tác mới bị từ chối theo semantics của dịch vụ.
- Audit log ghi principal, action, key ID, request ID và kết quả.
- Throttling, timeout và lỗi dịch vụ không khiến ứng dụng chuyển sang key hoặc provider yếu hơn.

Test KMS nên dùng account/project và key riêng cho môi trường kiểm thử. Dùng key production để thử deny, disable, schedule deletion hoặc thay policy có thể gây gián đoạn không mong muốn.

### Kiểm thử envelope encryption

Nếu ứng dụng dùng envelope encryption, kiểm tra cả DEK và KEK:

1. Yêu cầu KMS tạo data key.
2. Xác minh ứng dụng nhận plaintext DEK và encrypted DEK theo hợp đồng API.
3. Mã hóa dữ liệu bằng plaintext DEK.
4. Lưu ciphertext và encrypted DEK; không lưu plaintext DEK.
5. Xóa bản plaintext DEK khỏi vùng nhớ ứng dụng theo khả năng runtime.
6. Đọc lại encrypted DEK và yêu cầu KMS giải mã bằng principal được phép.
7. Xác minh principal không có quyền Decrypt bị từ chối.

Không ghi plaintext DEK vào log, file test output hoặc assertion message. Nếu test phải quan sát DEK, chỉ kiểm tra trong bộ nhớ và tránh đưa bytes ra báo cáo.

## 9. Kiểm thử HSM và non-extractability

Với HSM, một yêu cầu quan trọng là key object nhạy cảm không thể bị export khỏi ranh giới phần cứng. Kiểm thử cần xác nhận:

- Key được tạo hoặc import vào đúng device/partition/token.
- Thuộc tính key object như CKA_SENSITIVE và CKA_EXTRACTABLE được đặt theo policy.
- Principal/client không thể export key bằng API được hỗ trợ.
- Các thao tác Sign, Decrypt, Derive hoặc Wrap chỉ hoạt động với quyền đã cấp.
- Logout, restart client hoặc reconnect không làm key object biến mất ngoài dự kiến.
- Backup/restore tuân theo quy trình HSM và cơ chế quorum/phê duyệt.
- Audit log ghi nhận login, truy cập object, thao tác và thay đổi thuộc tính.

Với Java PKCS#11 provider, KeyStore type PKCS11 có thể được dùng để truy cập object trên token tùy provider và cấu hình. Cách load, login và tham số PIN phụ thuộc implementation. Không giả định mọi HSM/provider hỗ trợ cùng API hoặc cùng loại key object.

PrivateKey.getEncoded() trả null là một dấu hiệu có thể gặp với private key không export được, nhưng riêng điều đó chưa chứng minh non-extractability. Cần kiểm tra thuộc tính object trên HSM và thử thao tác export theo cách được nhà cung cấp hỗ trợ trong môi trường test. Không thử export key production để chứng minh policy.

## 10. Kiểm thử backup và restore

Backup key storage cần được kiểm thử như một quy trình khôi phục hoàn chỉnh, không chỉ xác nhận file backup tồn tại:

- Backup được mã hóa và quyền đọc bị giới hạn.
- Backup có integrity check và metadata cần để khôi phục.
- Bản backup được lưu ở vị trí/region phù hợp với chính sách.
- Có phân tách quyền giữa người tạo backup, người phê duyệt và người restore.
- Quy trình restore yêu cầu credential/quorum phù hợp.
- Khôi phục vào môi trường cô lập và xác minh key hoạt động đúng.
- Kiểm tra khả năng giải mã dữ liệu mẫu đã mã hóa trước backup.
- Ghi lại actor, thời điểm, nguồn backup, key version và kết quả restore.

Với HSM, backup có thể là backup thiết bị hoặc key wrapping theo cơ chế nhà cung cấp; không phải lúc nào cũng là file có thể sao chép. Với KMS managed key, khả năng export/backup key material có thể bị giới hạn hoặc do nhà cung cấp quản lý. Hãy kiểm thử cơ chế recovery được hỗ trợ, không tự tìm cách xuất key material ngoài thiết kế.

Đặt RPO/RTO cho key storage và thử khôi phục trong điều kiện mất region, mất token, mất file hoặc mất credential quản trị. Nếu dữ liệu đã mã hóa phụ thuộc key không có bản sao khôi phục, backup ciphertext đơn lẻ không bảo đảm khả năng khôi phục.

## 11. Kiểm thử rotation, disable, revoke và destroy

Key storage phải được kiểm thử qua các trạng thái vòng đời:

| Thao tác | Kiểm tra |
|---|---|
| Create/import | Key có đúng algorithm, size, usage, owner và storage location không |
| Activate/enable | Principal được phép có thể dùng key |
| Rotate | Phiên bản mới được tạo, metadata cập nhật và reader xử lý được dữ liệu cũ |
| Disable | Thao tác mới bị từ chối theo policy, dữ liệu/metadata cũ vẫn được giữ |
| Revoke grant/permission | Principal cũ mất quyền sau thời gian propagation/session phù hợp |
| Schedule deletion | Thời gian chờ, thông báo và quyền hủy lịch xóa hoạt động đúng |
| Destroy | Key không còn dùng được sau khi destroy; thao tác có approval/audit |

Không dùng destroy trong test chung trên key cần thiết cho các bài test khác. Tạo key riêng cho test lifecycle và xác nhận không có dữ liệu/backup phụ thuộc trước khi thực hiện thao tác không thể đảo ngược.

## 12. Kiểm thử tính nguyên tử và khả năng chịu lỗi

Khi lưu file KeyStore, ứng dụng có thể bị dừng giữa lúc ghi. Nếu ghi trực tiếp lên file đang dùng, file có thể bị cắt cụt hoặc hỏng. Một pattern thường dùng là ghi vào file tạm trong cùng filesystem, flush dữ liệu, sau đó thay thế file đích bằng thao tác atomic move nếu nền tảng hỗ trợ.

Kiểm thử cần mô phỏng:

- Process dừng trước khi ghi xong.
- Process dừng sau khi ghi file tạm nhưng trước khi rename.
- Lỗi disk full hoặc permission denied.
- File bị lock hoặc có tiến trình khác đang cập nhật.
- KMS/HSM timeout, throttling hoặc mất kết nối.
- Provider không khả dụng hoặc token chưa login.

Sau mỗi lỗi, hệ thống phải giữ được bản keystore cũ hợp lệ hoặc báo lỗi rõ ràng; không để một file rỗng/không hoàn chỉnh được xem là kho khóa hợp lệ. Với nhiều writer, cần cơ chế lock hoặc đồng bộ ở tầng ứng dụng; không giả định KeyStore object hay file storage tự an toàn khi truy cập đồng thời.

## 13. Ma trận test case đề xuất

| Nhóm | Test case | Kết quả mong đợi |
|---|---|---|
| Load/store | Tạo, lưu, đóng và load lại | Entry và metadata còn nguyên |
| Password | Sai store/entry password | Thất bại, không fallback |
| Integrity | File bị sửa hoặc cắt cụt | Phát hiện lỗi, không dùng key |
| Authorization | Principal hợp lệ/không hợp lệ | Allow đúng phạm vi, deny ngoài phạm vi |
| Non-extractability | Thử export key HSM | Không lấy được key material |
| Persistence | Restart app hoặc reconnect token | Key vẫn có thể truy cập theo policy |
| Backup | Restore từ bản backup | Khôi phục và dùng được với dữ liệu test |
| Rotation | Tạo version mới và đọc dữ liệu cũ | Dữ liệu cũ/mới được xử lý đúng |
| Revocation | Thu hồi grant hoặc disable key | Thao tác mới bị từ chối theo policy |
| Audit | Thực hiện thao tác nhạy cảm | Event có actor, action, resource, result |
| Resilience | Timeout, disk full, provider unavailable | Fail safe, không làm hỏng bản lưu hợp lệ |
| Leakage | Quét log, artifact và test output | Không có key bytes, password hoặc token |

## 14. Tổ chức test trong CI/CD

Nên tách test theo mức độ phụ thuộc hạ tầng:

- **Unit test:** kiểm tra logic chọn alias/version, xử lý metadata, validation và error handling bằng test keystore.
- **Integration test:** kiểm tra KeyStore provider, file permission, KMS sandbox hoặc HSM test partition.
- **Security test:** kiểm tra negative authorization, non-extractability, tampering, secret leakage và audit.
- **Recovery test:** khôi phục từ backup trong môi trường cô lập và xác minh dữ liệu mẫu.
- **Operational test:** rotation, disable, revoke, failover và xử lý timeout theo quy trình vận hành.

Không nên chạy thao tác phá hủy hoặc thay đổi policy production trong pipeline thông thường. Dùng key/test account riêng, tự động dọn tài nguyên có thể dọn và giữ bằng chứng không chứa bí mật. CI log chỉ nên ghi alias, key ID đã được phép công khai, provider name/version và kết quả kiểm thử.

Các test phụ thuộc HSM hoặc KMS có thể chạy trong một stage được kiểm soát thay vì mọi commit. Tuy vậy, cần chạy định kỳ và sau khi nâng cấp JDK, provider, HSM firmware, SDK hoặc policy.

## 15. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra keystore load được | Bỏ sót quyền filesystem, backup, export và audit | Dùng test matrix theo confidentiality/integrity/access/recovery |
| Dùng production key trong test | Có thể lộ key hoặc phá hủy dữ liệu | Dùng key riêng cho môi trường kiểm thử |
| Cho rằng PKCS12 password bảo vệ mọi bản sao | Backup, file tạm hoặc password có thể bị lộ | Kiểm tra toàn bộ đường lưu trữ và quản lý password riêng |
| Cho rằng getEncoded() == null chứng minh HSM non-extractable | Bỏ sót đường export khác hoặc sai cấu hình object | Kiểm tra object attribute và export policy trên HSM |
| Không thử sai password/tampering | Không biết hệ thống xử lý file hỏng ra sao | Thêm negative test trên bản sao test |
| Ghi đè trực tiếp keystore đang dùng | Process crash có thể làm hỏng kho khóa | Dùng file tạm, atomic replacement và backup |
| Không thử restore | Backup có thể tồn tại nhưng không dùng được | Thực hiện recovery drill và test giải mã dữ liệu mẫu |
| Xóa key cũ trước khi kiểm tra archive | Mất khả năng khôi phục dữ liệu lịch sử | Kiểm tra retention và dependency trước destroy |
| Log exception chứa secret | Credential/key material bị lộ qua log | Redact và kiểm tra test output |
| Không kiểm thử quyền deny | Principal ngoài phạm vi có thể truy cập key | Có negative authorization test cho từng role |

## 16. Checklist hoàn tất kiểm thử

- [ ] Xác định loại storage, provider, key type và ranh giới bảo mật.
- [ ] Dùng key, account, token hoặc partition riêng cho test.
- [ ] Kiểm tra load/store và khả năng dùng key sau khi reload.
- [ ] Kiểm tra password sai, entry sai, file tampered và file bị cắt cụt.
- [ ] Xác minh filesystem ACL/permission và các bản sao/backup.
- [ ] Kiểm thử authorization allow/deny theo principal, action và resource.
- [ ] Với HSM, kiểm tra object attributes và non-extractability trên thiết bị test.
- [ ] Kiểm thử KMS API, key policy, grant và audit event.
- [ ] Kiểm thử backup/restore bằng thao tác giải mã dữ liệu mẫu.
- [ ] Kiểm thử rotation, disable, revoke và destroy trên key test riêng.
- [ ] Mô phỏng crash, disk full, timeout, throttling và provider unavailable.
- [ ] Quét log, artifact, dump và test report để phát hiện secret/key leakage.
- [ ] Lưu kết quả, provider/version, test environment và bằng chứng không chứa bí mật.

Test key storage phải chứng minh được cả việc khóa được bảo vệ lẫn việc khóa có thể được sử dụng và khôi phục đúng lúc. Bộ kiểm thử tốt bao phủ file KeyStore, KMS/HSM, quyền truy cập, tính toàn vẹn, backup/restore, lifecycle và xử lý lỗi; đồng thời tránh để chính test trở thành nguồn rò rỉ key material.
