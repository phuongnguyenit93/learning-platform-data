# Thu hồi key bị compromise

## 1. Mục tiêu bài thực hành

Bài thực hành này mô phỏng một sự cố lộ khóa mã hóa trong dịch vụ lưu trữ tài liệu và yêu cầu người học thực hiện quy trình ứng phó từ phát hiện, khoanh vùng, containment, thay khóa, di trú dữ liệu đến xác minh và đóng sự cố. Người học sẽ thấy vì sao chỉ tạo một khóa mới hoặc đổi alias không đủ để xử lý một khóa đã bị lộ.

Sau bài thực hành, người học có thể:

- Phân biệt key material bị lộ với credential, workload identity hoặc quyền quản trị bị chiếm.
- Xác định dữ liệu, key version, tenant, ứng dụng và backup phụ thuộc vào khóa bị ảnh hưởng.
- Thu hồi quyền sử dụng khóa, session và grant của principal đáng ngờ.
- Chọn đúng hành động: disable, revoke grant, rotate, rewrap, re-encrypt hoặc destroy.
- Tạo khóa thay thế và chuyển workload sang khóa mới.
- Di trú dữ liệu đã mã hóa bằng khóa bị compromise.
- Xác minh dữ liệu mới bằng thao tác mật mã và negative test.
- Lưu audit evidence và đánh giá tác động còn lại của sự cố.

## 2. Phạm vi và quy tắc an toàn

Đây là bài lab trong môi trường local hoặc sandbox được phê duyệt. Chỉ dùng dữ liệu tổng hợp và khóa được tạo riêng cho bài thực hành. Không dùng private key, DEK, KEK, credential, certificate hoặc dữ liệu production. Không gửi key material lên chat, ticket, log hoặc kho mã nguồn.

Trong lab, người học cố ý tạo một bản sao của khóa cũ để mô phỏng tình huống key material đã bị lộ. Hành động này chỉ nhằm chứng minh tác động của compromise trong môi trường thử nghiệm. Trong production, tuyệt đối không export khóa chỉ để tái hiện sự cố.

Không thực hiện thao tác xóa khóa vĩnh viễn trong lab nếu chưa hoàn tất migration và kiểm tra. Với KMS/HSM thật, việc disable, schedule deletion, revoke grant và destroy có semantics khác nhau; chỉ thực hiện theo runbook và approval của tổ chức.

## 3. Tình huống sự cố

Một dịch vụ Java lưu tài liệu của nhiều tenant bằng envelope encryption. Mỗi tài liệu được mã hóa bằng một Data Encryption Key (DEK) riêng; DEK được wrap bằng Key Encryption Key (KEK) trong KMS. Ciphertext và wrapped DEK được lưu trong object storage.

Monitoring phát hiện một bản debug dump trong môi trường lab chứa bản sao DEK của tài liệu thử nghiệm. Điều tra xác nhận một principal của ứng dụng đã có thể đọc key material trong bộ nhớ và bản sao đó có khả năng được truy cập trái phép.

Thông tin tình huống:

| Thuộc tính | Giá trị lab |
|---|---|
| Tenant | tenant-lab-01 |
| Application | document-service |
| Object | doc-lab-1001 |
| Key ID | dek-lab-v1 |
| Key type | AES-256 DEK |
| Encryption mode | AES-256-GCM |
| KMS key | kek-lab-v1 |
| Detection | Bản sao DEK xuất hiện trong debug artifact |
| Suspected exposure | DEK dạng rõ |
| Data class | Dữ liệu tổng hợp, không nhạy cảm |

Người học được giao xử lý sự cố như thể DEK đã bị lộ hoàn toàn. Giả định kẻ tấn công có thể giữ một bản sao khóa và ciphertext mà họ đã lấy được. Việc thu hồi quyền trong ứng dụng không thể xóa bản sao đã nằm ngoài quyền kiểm soát của tổ chức.

## 4. Phân biệt các kiểu compromise

Trước khi thao tác, phân loại chính xác thứ bị lộ:

| Tình huống | Điều gì bị xâm phạm? | Hướng xử lý chính |
|---|---|---|
| DEK hoặc private key dạng rõ bị lộ | Key material có thể được dùng độc lập để giải mã hoặc ký. | Coi key version bị compromise; thay khóa và re-encrypt/re-sign dữ liệu liên quan. |
| Credential của workload bị lộ, KMS key không exportable | Kẻ tấn công có thể gọi API bằng principal bị chiếm quyền. | Thu hồi session/credential/grant, chặn principal, rà soát API use; đánh giá có cần rekey không. |
| KMS/HSM administrator bị chiếm | Có thể thay policy, grant, disable, export hoặc phá hủy tài nguyên tùy quyền. | Cô lập danh tính quản trị, khôi phục policy tin cậy, kiểm tra audit và quyền đã thay đổi. |
| KEK material bị lộ ngoài KMS | Kẻ tấn công có thể mở các wrapped DEK đã lấy được. | Thay KEK và đánh giá re-encrypt dữ liệu; rewrap đơn thuần không thu hồi bản sao DEK mà attacker đã mở. |
| Certificate private key bị lộ | Có thể giả mạo danh tính hoặc ký bằng private key. | Tạo key pair mới, cấp certificate mới, revoke certificate cũ và cập nhật trust. |
| HMAC key bị lộ | Có thể tạo MAC hợp lệ hoặc giả mạo thông điệp. | Thay HMAC key, giới hạn thời gian chấp nhận MAC cũ và xử lý token/message liên quan. |

Một KMS key không exportable thường không thể bị lấy raw key material qua API thông thường. Việc một IAM principal bị lộ không tự động chứng minh KMS key material đã bị lộ. Tuy nhiên, nếu attacker có quyền Decrypt, họ có thể yêu cầu KMS unwrap DEK và lấy plaintext DEK; khi đó cần đánh giá như sự cố lộ DEK ở phạm vi dữ liệu đã truy cập.

## 5. Chuẩn bị lab

### Công cụ

- JDK 17 trở lên.
- IDE hoặc terminal có thể biên dịch/chạy một lớp Java.
- Thư mục lab tạm thời, không đồng bộ lên cloud drive hoặc repository.
- Dữ liệu giả lập, ví dụ nội dung văn bản không nhạy cảm.

Lab Java bên dưới dùng JCA và khóa sinh trong bộ nhớ. Không cần KMS account. Phần thao tác KMS/HSM ở các mục sau được mô tả dưới dạng runbook để áp dụng trong sandbox có quyền phù hợp.

### Kết quả cần tạo

Người học cần có:

- Một ciphertext được tạo bằng DEK cũ.
- Một bản sao khóa cũ mô phỏng key exposure.
- Bằng chứng bản sao khóa cũ có thể giải mã ciphertext cũ.
- Một ciphertext mới được tạo bằng DEK thay thế.
- Bằng chứng khóa mới giải mã được ciphertext mới.
- Bằng chứng khóa cũ không giải mã được ciphertext mới.
- Biên bản containment, migration, validation và cleanup.

## 6. Bước 1 — Tạo dữ liệu và khóa thử nghiệm

Tạo một chương trình Java có các chức năng:

1. Sinh DEK AES-256 bằng KeyGenerator và SecureRandom.
2. Mã hóa một tài liệu thử bằng AES/GCM/NoPadding.
3. Lưu nonce và ciphertext kèm authentication tag.
4. Gắn AAD gồm tenant ID, object ID và format version.
5. Tạo bản sao DEK trong bộ nhớ để mô phỏng khóa bị lộ.

Đoạn mã nền tảng:

~~~java
import java.security.GeneralSecurityException;
import java.security.KeyGenerator;
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class CompromisedKeyLab {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    public record Envelope(
            byte[] nonce,
            byte[] ciphertextAndTag,
            String keyId) {
    }

    public static SecretKey newDek()
            throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RANDOM);
        return generator.generateKey();
    }

    public static Envelope encrypt(
            byte[] plaintext,
            SecretKey key,
            String keyId,
            byte[] aad) throws GeneralSecurityException {

        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);

        return new Envelope(
                nonce,
                cipher.doFinal(plaintext),
                keyId);
    }

    public static byte[] decrypt(
            Envelope envelope,
            SecretKey key,
            byte[] aad) throws GeneralSecurityException {

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, envelope.nonce()));
        cipher.updateAAD(aad);
        return cipher.doFinal(envelope.ciphertextAndTag());
    }

    public static byte[] copyKeyForLabOnly(SecretKey key) {
        return key.getEncoded().clone();
    }
}
~~~

Đây là fixture đơn giản cho lab. Trong production, không gọi getEncoded() để lấy DEK từ KMS/HSM nếu khóa được thiết kế không exportable. Mảng byte trả về từ SecretKey và record trên cũng cần defensive copy trong ứng dụng thật.

### Thực hiện

- Sinh khóa với ID dek-lab-v1.
- Tạo AAD cố định cho tài liệu thử: tenant-lab-01, doc-lab-1001, format version 1.
- Mã hóa nội dung tổng hợp, ví dụ “Lab document for tenant-lab-01”.
- Giữ envelope trong bộ nhớ hoặc thư mục lab tạm.
- Tạo một bản sao DEK bằng hàm copyKeyForLabOnly để mô phỏng artifact bị lộ.

**Kết quả mong đợi:** chương trình tạo được envelope gồm nonce, ciphertext/tag và key ID. Không có plaintext key được ghi vào console.

## 7. Bước 2 — Xác nhận tác động của key exposure

Trong một test method, khởi tạo fixture và tạo SecretKeySpec từ bản sao DEK bị lộ rồi thử giải mã envelope cũ bằng đúng AAD:

~~~java
import java.nio.charset.StandardCharsets;
import javax.crypto.spec.SecretKeySpec;
import javax.crypto.SecretKey;
import java.util.Arrays;

SecretKey oldDek = CompromisedKeyLab.newDek();
byte[] originalPlaintext =
        "Lab document for tenant-lab-01".getBytes(StandardCharsets.UTF_8);
byte[] aad =
        "tenant-lab-01|doc-lab-1001|format-v1"
                .getBytes(StandardCharsets.UTF_8);
CompromisedKeyLab.Envelope oldEnvelope =
        CompromisedKeyLab.encrypt(
                originalPlaintext, oldDek, "dek-lab-v1", aad);

byte[] leakedKeyBytes = CompromisedKeyLab.copyKeyForLabOnly(oldDek);
SecretKey leakedDek =
        new SecretKeySpec(leakedKeyBytes, "AES");

byte[] attackerPlaintext =
        CompromisedKeyLab.decrypt(oldEnvelope, leakedDek, aad);

boolean exposureConfirmed =
        Arrays.equals(originalPlaintext, attackerPlaintext);

System.out.println("Old ciphertext readable with leaked key: "
        + exposureConfirmed);
Arrays.fill(attackerPlaintext, (byte) 0);
~~~

**Kết quả mong đợi:** phép so sánh trả về true. Điều này chứng minh rằng khi attacker đã có cả ciphertext và bản sao DEK, việc xóa DEK khỏi ứng dụng hoặc thu hồi quyền KMS không thể làm bản sao đó mất khả năng giải mã.

Các biến oldDek, originalPlaintext, aad và oldEnvelope sẽ được dùng tiếp ở bước migration. Đây là đoạn test chạy trong cùng tiến trình lab; không lưu leakedKeyBytes hoặc leakedDek ra file.

SecretKeySpec giữ bản sao key bytes nội bộ nên việc xóa leakedKeyBytes không xóa bản sao trong leakedDek. Đây là chủ ý để mô phỏng attacker giữ khóa. Kết thúc lab bằng cách dừng tiến trình thử nghiệm và xóa thư mục tạm; không xem thao tác fill một mảng byte là bằng chứng zeroization tuyệt đối của JVM.

Ghi nhận finding:

- Key ID dek-lab-v1 bị đánh dấu COMPROMISED.
- Object doc-lab-1001 có ciphertext được bảo vệ bởi key này.
- Bản sao khóa đã ra khỏi ranh giới tin cậy trong giả định sự cố.
- Các ciphertext khác dùng cùng DEK phải được tìm kiếm trong inventory.

Không ghi giá trị leakedKeyBytes hoặc attackerPlaintext vào báo cáo.

## 8. Bước 3 — Triage và xác định blast radius

Trước khi thu hồi, lập danh sách phạm vi:

| Câu hỏi | Việc cần làm |
|---|---|
| Key ID/version nào bị ảnh hưởng? | Đối chiếu key registry, alias và metadata ciphertext. |
| Khóa được dùng cho tenant nào? | Truy vấn mapping server-side theo key ID. |
| Có bao nhiêu object/ciphertext phụ thuộc? | Quét database, object metadata, backup và archive. |
| Khóa có từng được dùng cho nhiều mục đích? | Kiểm tra purpose, operation và key usage policy. |
| Có bản sao ở đâu? | Kiểm tra debug artifact, heap dump, crash report, CI artifact và backup. |
| Principal nào đã truy cập? | Rà soát IAM/KMS/HSM audit, application log và session history. |
| Thời điểm exposure đầu tiên là khi nào? | Xác định timeline từ log và metadata. |
| Có dữ liệu đã bị exfiltrate không? | Phối hợp incident response và data access monitoring. |

Tìm cả bản sao ciphertext đã lưu trước khi phát hiện. Nếu attacker đã lấy ciphertext và DEK trong cùng một thời điểm, re-encrypt bản lưu hiện tại không thể thu hồi bản ciphertext cũ mà attacker đang giữ.

**Checkpoint:** chỉ chuyển sang containment khi đã ghi nhận key ID/version, owner, principal liên quan, dữ liệu phụ thuộc và evidence cần bảo toàn. Trong sự cố thực tế, containment khẩn cấp có thể bắt đầu song song với việc thu thập phạm vi.

## 9. Bước 4 — Containment và thu hồi quyền

Chọn hành động theo loại compromise:

### Nếu credential hoặc workload identity bị lộ

1. Disable hoặc rotate credential bị lộ theo IAM process.
2. Thu hồi session/token đang hoạt động nếu nền tảng hỗ trợ.
3. Revoke grant và quyền KMS của principal bị ảnh hưởng.
4. Kiểm tra role assumption, trust policy và workload identity binding.
5. Tìm principal thay thế hoặc credential mới đã được phê duyệt.
6. Rà soát API event trong khoảng thời gian nghi ngờ.

Nếu KMS key vẫn non-exportable và không có bằng chứng DEK/key material đã bị trả về hoặc sử dụng trái phép, có thể giữ key material và tiếp tục hoạt động qua principal mới sau khi kiểm tra. Quyết định này phải dựa trên audit evidence và threat assessment.

### Nếu DEK hoặc private key dạng rõ bị lộ

1. Đánh dấu key version COMPROMISED trong inventory.
2. Ngăn ứng dụng dùng khóa đó để tạo ciphertext, chữ ký hoặc MAC mới.
3. Thu hồi grant runtime thông thường.
4. Cô lập nơi chứa bản sao bị lộ và bảo toàn forensic evidence.
5. Nếu cần migration dữ liệu cũ, cấp quyền decrypt tạm thời cho migration identity riêng, chỉ trong môi trường cô lập và có approval.
6. Chặn mọi principal khác khỏi decrypt/unwrap bằng key cũ.
7. Tạo khóa mới và chuyển dữ liệu sang khóa mới.

Không disable key trong KMS một cách máy móc nếu thao tác đó sẽ chặn cả migration decrypt cần thiết. Một phương án là giữ key enabled nhưng giới hạn policy chỉ cho incident migration principal dùng decrypt trong thời gian ngắn, đồng thời revoke mọi grant runtime khác. Nếu đang có hoạt động lạm dụng trực tiếp và cần dừng ngay, có thể phải disable key và chấp nhận dịch vụ tạm thời không đọc được cho đến khi có phương án phục hồi.

Nếu key material đã được export, disable KMS key chỉ chặn thao tác qua KMS; nó không vô hiệu hóa bản sao key bytes mà attacker đang giữ.

### Nếu KMS/HSM administrator bị chiếm

- Cô lập admin identity, session và credential.
- Khôi phục key policy từ nguồn được kiểm soát nếu policy đã bị sửa.
- Kiểm tra grant, alias, key state, deletion schedule, export/import và audit configuration.
- Xác định liệu attacker chỉ có quyền quản trị hay đã có quyền decrypt/sign thực tế.
- Yêu cầu phê duyệt độc lập trước khi cấp lại quyền quản trị.

**Kết quả mong đợi:** principal hoặc đường truy cập bị xâm phạm không còn thực hiện được operation ngoài phạm vi containment. Audit ghi nhận actor, thời điểm, key ID, quyền bị thu hồi và approval.

## 10. Bước 5 — Tạo khóa thay thế

Với lab DEK:

1. Sinh DEK mới có ID dek-lab-v2 bằng KeyGenerator.
2. Dùng DEK mới cho dữ liệu ghi mới.
3. Trong hệ thống KMS thật, tạo data key bằng KEK mới hoặc key version được phê duyệt.
4. Lưu wrapped DEK mới và metadata version.
5. Cấp quyền chỉ cho workload và migration identity cần thiết.
6. Kiểm tra encrypt/decrypt bằng key mới trước khi chuyển traffic.

Không đổi alias để trỏ sang khóa mới rồi giả định ciphertext cũ sẽ tự giải mã. Ciphertext cũ phải giữ mapping tới đúng key version đã tạo nó.

Với signing key, tạo key pair mới trong HSM/KMS, kiểm tra sign/verify, phát hành certificate mới nếu cần và cập nhật client/trust configuration. Với HMAC, tạo secret mới và triển khai versioning để hệ thống có thể xác minh dữ liệu trong thời gian chuyển tiếp.

## 11. Bước 6 — Re-encrypt dữ liệu đã bị ảnh hưởng

Khi DEK bị lộ, rewrap DEK cũ bằng KEK mới không khắc phục được sự cố: attacker đã có DEK cũ. Cần tạo DEK mới và mã hóa lại plaintext bằng khóa mới.

Luồng migration:

~~~text
Old ciphertext + old DEK
          |
          v
 Controlled migration worker
          |
          v
   Decrypt old ciphertext
          |
          v
   Validate old AEAD tag
          |
          v
   Plaintext in memory
          |
          v
 Encrypt with new DEK
          |
          v
New ciphertext + new wrapped DEK
          |
          v
 Verify + atomic metadata switch
~~~

Các bước:

1. Migration worker chạy với identity riêng và quyền decrypt giới hạn trên key cũ.
2. Đọc ciphertext và metadata theo key ID/version.
3. Dựng lại AAD và context đúng; xác minh tenant/object mapping.
4. Decrypt và xác minh AEAD tag. Nếu tag sai, dừng record và ghi nhận integrity failure.
5. Sinh DEK mới cho object hoặc phạm vi được thiết kế.
6. Encrypt plaintext bằng AES-GCM với nonce mới và AAD theo schema hiện hành.
7. Wrap DEK mới bằng KEK mới qua KMS.
8. Ghi ciphertext và metadata mới vào vùng staging.
9. Đọc thử bản staging bằng đường decrypt bình thường và so sánh hash/expected result.
10. Commit metadata pointer theo thao tác atomic hoặc optimistic locking.
11. Đánh dấu object đã migration và lưu old/new key reference trong audit.
12. Xóa buffer plaintext/DEK theo khả năng runtime; không log dữ liệu.

Migration phải idempotent. Dùng object ID, source version và migration ID để tránh xử lý lặp. Nếu worker crash sau khi ghi staging nhưng trước khi commit, lần chạy sau cần nhận diện staging record và tiếp tục hoặc dọn theo policy.

### Ví dụ Java: mã hóa lại bằng DEK mới

~~~java
import java.security.GeneralSecurityException;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.SecretKey;

public static CompromisedKeyLab.Envelope reencrypt(
        CompromisedKeyLab.Envelope oldEnvelope,
        SecretKey oldDek,
        SecretKey newDek,
        byte[] aad,
        String newKeyId) throws GeneralSecurityException {

    byte[] plaintext =
            CompromisedKeyLab.decrypt(oldEnvelope, oldDek, aad);
    try {
        return CompromisedKeyLab.encrypt(
                plaintext, newDek, newKeyId, aad);
    } finally {
        Arrays.fill(plaintext, (byte) 0);
    }
}

public static boolean oldKeyRejected(
        CompromisedKeyLab.Envelope newEnvelope,
        SecretKey oldDek,
        byte[] aad) throws GeneralSecurityException {

    try {
        byte[] unexpected =
                CompromisedKeyLab.decrypt(newEnvelope, oldDek, aad);
        Arrays.fill(unexpected, (byte) 0);
        return false;
    } catch (AEADBadTagException expected) {
        return true;
    }
}
~~~

Đoạn mã minh họa migration cho một object trong bộ nhớ. Production cần stream an toàn cho file lớn, transaction/staging, retry, versioned metadata, authorization, audit và quản lý bộ nhớ. Không dùng đoạn mã này để migrate dữ liệu production trực tiếp.

Sau khi đặt hai helper reencrypt và oldKeyRejected vào test harness, chạy phần kiểm tra:

~~~java
SecretKey newDek = CompromisedKeyLab.newDek();
CompromisedKeyLab.Envelope newEnvelope =
        reencrypt(oldEnvelope, oldDek, newDek, aad, "dek-lab-v2");

byte[] recovered = CompromisedKeyLab.decrypt(newEnvelope, newDek, aad);
if (!Arrays.equals(originalPlaintext, recovered)) {
    throw new AssertionError("Khóa mới không khôi phục đúng plaintext");
}

if (!oldKeyRejected(newEnvelope, oldDek, aad)) {
    throw new AssertionError("Khóa cũ vẫn mở được ciphertext mới");
}

System.out.println("New key decrypts migrated data: true");
System.out.println("Old key rejected for new ciphertext: true");
Arrays.fill(recovered, (byte) 0);
~~~

Kết quả mong đợi: DEK v2 giải mã được envelope mới và DEK v1 bị GCM authentication tag từ chối. Phép thử này chỉ chứng minh ciphertext mới được bảo vệ bằng khóa mới; nó không chứng minh bản ciphertext cũ mà attacker đã sao chép trở nên an toàn.

## 12. Bước 7 — Kiểm chứng sau rotation

Kiểm tra cả trường hợp được phép và bị từ chối:

| Kiểm tra | Kết quả mong đợi |
|---|---|
| Decrypt ciphertext mới bằng DEK v2 | Thành công, plaintext khớp fixture gốc. |
| Decrypt ciphertext mới bằng DEK v1 | Thất bại xác thực AEAD. |
| Decrypt ciphertext cũ trong migration scope | Thành công trong cửa sổ migration đã phê duyệt. |
| Runtime principal dùng DEK v1 | Bị từ chối theo policy. |
| Runtime principal dùng DEK v2 | Thành công đúng tenant và operation. |
| Tenant khác dùng context của tenant-lab-01 | Bị authorization/KMS policy từ chối. |
| Sửa nonce, ciphertext, tag hoặc AAD | Decrypt thất bại, không trả plaintext. |
| Principal không có quyền | KMS deny và audit event được tạo. |
| Key v1 dùng để encrypt dữ liệu mới | Bị chặn sau cutover. |

Kiểm tra thêm:

- Số object trong inventory bằng số object migration thành công, thất bại và đang chờ.
- Không còn bản ghi production nào ghi mới bằng key version bị compromise.
- Backup, archive, replica và snapshot đã được đánh giá.
- Dashboard hiển thị key v2 là current encryption version.
- Alert phát hiện nếu key v1 tiếp tục được sử dụng ngoài migration scope.

Lưu ý: nếu attacker đã lấy ciphertext cũ và DEK cũ trước khi migration, họ vẫn có thể giải mã bản sao đã exfiltrate. Re-encrypt bảo vệ bản dữ liệu được tổ chức kiểm soát sau thời điểm chuyển đổi; nó không thể thu hồi bản plaintext/ciphertext mà attacker đã có.

## 13. Bước 8 — Xử lý khóa cũ và đóng quyền migration

Chỉ retire/destroy key cũ sau khi:

- Tất cả dữ liệu online cần tiếp tục sử dụng đã migration hoặc có quyết định xử lý riêng.
- Backup/archive đã được re-encrypt, rewrap phù hợp hoặc có retention/exception được phê duyệt.
- Không còn workload hợp lệ cần key version cũ.
- Quyền decrypt tạm thời của migration identity đã được thu hồi.
- Inventory, metadata và audit phản ánh trạng thái COMPROMISED/RETIRED/DESTROYED đúng semantics.
- Owner và security approver xác nhận phạm vi hoàn tất.

Với KMS, disable ngăn các thao tác mật mã qua key theo semantics của dịch vụ; schedule deletion thường có recovery window; destroy/deletion có thể không đảo ngược. Không coi disable là zeroization. Nếu key material đã bị lộ ngoài KMS, deletion không xóa bản sao của attacker.

Không xóa bằng chứng incident, audit record, backup cần điều tra hoặc dữ liệu đang chịu legal hold. Việc hủy key phải tuân thủ retention và approval. Với key compromise, giữ key cũ trong kho cách ly chỉ khi cần điều tra hoặc migration và có kiểm soát truy cập chặt.

## 14. Nhánh xử lý cho certificate private key bị compromise

Nếu sự cố liên quan đến private key dùng cho TLS hoặc chữ ký:

1. Xác định certificate serial, fingerprint, SAN, issuer và endpoint/client sử dụng.
2. Tạo key pair mới trong HSM/KMS hoặc nơi bảo vệ được phê duyệt.
3. Tạo CSR mới và yêu cầu CA cấp certificate mới.
4. Triển khai certificate mới trên toàn bộ node, ingress, region và client liên quan.
5. Revoke certificate cũ qua CA; kiểm tra CRL/OCSP hoặc cơ chế status được client sử dụng.
6. Xác minh endpoint trả certificate mới và client xác thực chain/hostname thành công.
7. Kiểm tra log ký, TLS handshake và truy cập private key trong thời gian nghi ngờ compromise.
8. Thu hồi quyền và hủy private key cũ theo policy sau khi xử lý dependency.

Revoke certificate không tự động làm mọi client ngừng tin ngay lập tức. Cần kiểm tra hành vi cache, CRL/OCSP và trust policy của client. Cấp certificate mới nhưng giữ private key cũ không giải quyết compromise của key material.

## 15. Nhánh xử lý cho HMAC key bị compromise

Nếu HMAC key dùng để ký token hoặc message bị lộ:

- Tạo HMAC key version mới và lưu trong secret manager/KMS/HSM theo policy.
- Chuyển issuer sang tạo MAC bằng version mới.
- Verifier chỉ chấp nhận version cũ trong cửa sổ chuyển tiếp ngắn đã xác định.
- Token có thể thu hồi hoặc phát hành lại nếu attacker có thể tạo token giả bằng key cũ.
- Theo dõi key ID/version trong token header hoặc metadata; không tiết lộ secret.
- Kết thúc cửa sổ chuyển tiếp, từ chối MAC cũ và hủy key cũ theo retention.

Không giữ xác minh bằng key cũ vô thời hạn chỉ để tương thích ngược. Đặt deadline, kiểm soát replay và có phương án thu hồi token đã phát hành.

## 16. Audit và evidence

Biên bản incident cần có:

- Incident ID, thời điểm phát hiện và thời điểm exposure ước tính.
- Key ID/version, loại khóa, owner, purpose và tenant.
- Dữ liệu, ciphertext, backup, replica và ứng dụng phụ thuộc.
- Principal, credential, session hoặc thiết bị liên quan.
- Bằng chứng key material đã bị lộ hay chỉ credential/quyền bị chiếm.
- Containment action: revoke grant, disable principal, deny operation hoặc disable key.
- New key ID/version và thời điểm cutover.
- Số object migration thành công/thất bại/chưa xử lý.
- Kết quả positive/negative test.
- RTO, thời gian exposure và tác động còn lại.
- Quyết định retire/destroy, approver và evidence reference.

Audit log không được chứa key bytes, plaintext DEK/KEK, private key, token hoặc nội dung tài liệu. Dùng fingerprint, key ID, request ID, principal ID và reference tới bằng chứng được bảo vệ.

## 17. Bài tập mở rộng

Sau khi hoàn thành tình huống DEK bị lộ, thực hiện thêm các tình huống sau trong sandbox:

### Tình huống A — Workload credential bị lộ

KMS key không exportable, nhưng access token của document-service bị đưa vào log thử nghiệm.

Yêu cầu:

- Thu hồi token/session và cấp credential mới.
- Revoke grant hoặc role binding cũ.
- Rà soát KMS Decrypt event trong thời gian nghi ngờ.
- Xác định có DEK nào đã được trả về ngoài workload hợp lệ không.
- Quyết định có cần re-encrypt dữ liệu hay không và giải thích bằng evidence.

### Tình huống B — KEK bị lộ

Giả định attacker có KEK material và một tập wrapped DEK.

Yêu cầu:

- Xác định DEK và ciphertext phụ thuộc KEK.
- Giải thích vì sao chỉ rewrap DEK bằng KEK mới không thu hồi bản DEK attacker đã mở.
- Tạo DEK mới và re-encrypt dữ liệu có nguy cơ.
- Kiểm tra backup và archive.
- Đề xuất thứ tự retire KEK cũ.

### Tình huống C — Private signing key bị lộ

Giả định private key ký artifact đã bị copy khỏi môi trường build.

Yêu cầu:

- Tạo key pair và certificate mới.
- Revoke certificate cũ.
- Xác định artifact cần ký lại hoặc xác minh tăng cường.
- Cập nhật trust policy và signer identity.
- Lưu evidence về chữ ký mới và trạng thái revoke.

## 18. Tiêu chí chấm bài

| Tiêu chí | Điểm |
|---|---:|
| Phân loại đúng key material compromise và principal compromise | 15 |
| Khoanh vùng key ID/version, tenant và dependency | 10 |
| Containment và revoke quyền đúng thứ tự | 15 |
| Tạo khóa mới và phân biệt rewrap với re-encrypt | 15 |
| Migration an toàn, idempotent và có thể phục hồi | 15 |
| Positive/negative cryptographic validation | 10 |
| Audit evidence và báo cáo tác động | 10 |
| Cleanup, thu hồi quyền tạm thời và đóng sự cố | 10 |
| **Tổng** | **100** |

Điều kiện đạt:

- Tổng điểm từ 80/100.
- Không ghi key material vào log hoặc báo cáo.
- Không dùng khóa bị compromise để mã hóa dữ liệu mới.
- Không đánh dấu migration hoàn tất khi còn object phụ thuộc chưa được xử lý.
- Có bằng chứng key mới giải mã được dữ liệu mới và key cũ bị chặn khỏi luồng runtime.

## 19. Checklist đóng sự cố

- [ ] Đã phân loại chính xác loại compromise.
- [ ] Đã xác định key ID/version, owner, principal và blast radius.
- [ ] Đã bảo toàn audit evidence và artifact liên quan.
- [ ] Đã revoke credential, session, grant hoặc quyền bị xâm phạm.
- [ ] Đã ngừng dùng key version cũ cho thao tác bảo vệ mới.
- [ ] Đã tạo key version/key pair mới theo policy.
- [ ] Đã re-encrypt dữ liệu nếu key material bị lộ.
- [ ] Đã xác minh ciphertext mới và negative case.
- [ ] Đã rà soát backup, archive, replica và snapshot.
- [ ] Đã thu hồi quyền migration tạm thời.
- [ ] Đã cập nhật inventory, alert, owner và audit.
- [ ] Đã có approval trước khi disable/destroy key cũ.
- [ ] Đã ghi nhận dữ liệu attacker có thể đã lấy trước khi containment.
- [ ] Đã lên kế hoạch khắc phục nguyên nhân gốc và ngăn tái diễn.

## 20. Kết quả cần nộp

Người học nộp một báo cáo ngắn gồm:

1. Incident summary và loại compromise.
2. Danh sách key ID/version, tenant và object bị ảnh hưởng.
3. Containment plan và các quyền đã thu hồi.
4. Sơ đồ hoặc mô tả luồng migration sang key mới.
5. Kết quả Java lab: attacker đọc được ciphertext cũ, key mới đọc được ciphertext mới, key cũ không đọc được ciphertext mới.
6. Bảng positive/negative test và bằng chứng.
7. Kế hoạch xử lý backup, archive, certificate/HMAC nếu liên quan.
8. Audit evidence, cleanup và quyết định retire/destroy.
9. Tác động còn lại, đặc biệt dữ liệu ciphertext attacker có thể đã exfiltrate trước khi rotation.

Thu hồi key bị compromise là một quy trình ứng phó sự cố có kiểm soát. Thu hồi quyền ngăn principal tiếp tục sử dụng dịch vụ; thay khóa ngăn dữ liệu mới phụ thuộc vào key cũ; re-encrypt bảo vệ bản dữ liệu tổ chức còn kiểm soát; audit và xác minh chứng minh quá trình đã hoàn tất. Không thao tác nào có thể làm attacker quên key material hoặc plaintext mà họ đã lấy trước thời điểm containment, vì vậy phát hiện sớm và giới hạn blast radius vẫn là yếu tố quyết định.
