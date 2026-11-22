# Mã hóa hoặc loại bỏ nội dung nhạy cảm sau khi gửi

Trong ứng dụng Spring Framework Mail, việc gửi email không chỉ là tạo `MimeMessage` rồi gọi `JavaMailSender.send(...)`. Một thông báo có thể chứa tên, số điện thoại, địa chỉ giao hàng, mã đặt lại mật khẩu, đường dẫn chứa token, hóa đơn, tài liệu nhân sự hoặc dữ liệu tài chính. Những dữ liệu này có thể bị giữ lại tại nhiều vị trí: bảng outbox, hàng đợi, object storage, file tạm, nhật ký, APM traces, exception, bản sao lưu và hạ tầng của email provider.

Một mẫu thiết kế production cần trả lời hai câu hỏi **khác nhau nhưng bổ trợ nhau**:

1. **Mã hóa nội dung nhạy cảm khi phải lưu giữ:** hạn chế thiệt hại nếu database, disk, object storage hoặc backup bị truy cập trái phép.
2. **Loại bỏ nội dung nhạy cảm khi đã hết mục đích:** không giữ plaintext, ciphertext, attachment hoặc token quá thời hạn thực sự cần thiết.

Không nên coi “đã gửi xong” là thời điểm có thể xóa mọi dữ liệu ngay lập tức, vì gửi qua SMTP có thể trả về lỗi tạm thời, kết quả không rõ ràng hoặc cần retry. Ngược lại, cũng không nên giữ nguyên body, HTML, attachment và toàn bộ email thô vô thời hạn chỉ để “dễ debug”.

**Giới hạn quan trọng:** sau khi email đã được chuyển tới nhà cung cấp hoặc máy chủ hộp thư người nhận, ứng dụng thông thường **không thể thu hồi hoặc xóa tất cả bản sao ở bên ngoài**. Xóa bản sao khỏi database của ứng dụng không xóa email trong Inbox, thư chuyển tiếp, bản sao lưu của provider hay thiết bị người nhận. Bài học này tập trung vào **những bản sao ứng dụng có quyền kiểm soát**, các biện pháp bảo vệ trong quá trình gửi, và cách diễn đạt ranh giới bảo vệ một cách chính xác.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Xác định những loại dữ liệu nên tránh đưa vào email ngay từ đầu.
2. Liệt kê những nơi dữ liệu nhạy cảm có thể được tạo, sao chép hoặc lưu lại trong một pipeline Spring Mail.
3. Phân biệt **TLS khi vận chuyển**, **encryption at rest**, **application-level encryption** và **end-to-end encryption**.
4. Thiết kế email outbox chỉ lưu tối thiểu dữ liệu phục vụ render, retry, audit và delivery tracking.
5. Sử dụng mã hóa xác thực như AES-GCM đúng cách khi cần lưu payload nhạy cảm trong ứng dụng.
6. Hiểu vai trò của KMS/HSM, data encryption key, key version và quy trình xoay khóa.
7. Quản lý vòng đời attachment, file tạm, HTML, signed URL và nội dung MIME đã serialize.
8. Đặt retention/TTL theo trạng thái `PENDING`, `PROCESSING`, `RETRY_WAIT`, `SUBMITTED`, `FAILED` và `UNKNOWN`.
9. Triển khai cleanup/purge có khả năng retry, kiểm chứng và không phá hỏng các notification đang hoạt động.
10. Thiết kế logs, metrics, traces, tests và runbooks mà không vô tình lưu dữ liệu nhạy cảm.

## 2. Bắt đầu bằng mô hình đe dọa, không bắt đầu bằng thuật toán

Trước khi thêm AES vào code, cần trả lời: **dữ liệu nào**, **ai có thể đọc**, **nơi nào đang giữ**, **giữ bao lâu**, và **mục đích** của bản sao.

Ví dụ một email đặt lại mật khẩu:

```text
User requests password reset
         |
         v
Create short-lived one-time reset token
         |
         v
Render reset email
         |
         v
Queue / Outbox
         |
         v
JavaMailSender / SMTP
         |
         v
Mail provider / Recipient mailbox
```

Các mối đe dọa có thể khác nhau:

- Nhân viên vận hành đọc nhầm raw payload từ database hoặc log.
- SQL injection hoặc lộ backup làm lộ nội dung outbox.
- Object storage bị cấu hình public cho attachment.
- SMTP debug log in cả người nhận và nội dung message.
- Worker crash khiến file tạm chứa hóa đơn tồn tại nhiều tháng.
- Một bản raw MIME được gửi lên hệ thống giám sát bên thứ ba.
- Một secret/token hết hạn nhưng vẫn còn dùng được vì hệ thống không thu hồi.
- Một user yêu cầu xóa dữ liệu nhưng vẫn còn bản sao trong archive và backup theo lịch.

### Phân loại dữ liệu trước

| Loại dữ liệu | Ví dụ | Chính sách gợi ý |
| --- | --- | --- |
| Bí mật xác thực | OTP, reset token, magic-link token | Tránh lưu plaintext; TTL rất ngắn; one-time |
| Thông tin nhận dạng | Email, họ tên, số điện thoại, địa chỉ | Giảm thiểu, giới hạn quyền và retention |
| Dữ liệu tài chính | Hóa đơn, số tài khoản, sao kê | Kiểm soát truy cập/mã hóa theo độ nhạy |
| Dữ liệu nhân sự/y tế | Nội dung tuyển dụng, kết quả khám | Đánh giá kênh email phù hợp; bảo vệ nghiêm ngặt |
| Metadata vận hành | Notification ID, route, trạng thái | Thường lưu lâu hơn payload nhưng vẫn bảo vệ |
| Dữ liệu không nhạy cảm | Mẫu thông báo chung | Có thể lưu template/version thay vì full render |

Không phải tất cả email đều cần cùng chính sách. Một báo cáo tài chính chứa attachment nhạy cảm khác với một email “Đơn hàng của bạn đã được tiếp nhận” không có thông tin riêng ngoài địa chỉ người nhận.

## 3. Tấn công ở từng lớp: lưu trữ, vận chuyển và đầu cuối

Một mô hình đơn giản:

```text
Application DB / disk / object storage
       |     encryption at rest
       v
Spring Mail worker (data visible to permitted process)
       |     SMTP over TLS when properly configured
       v
Sending mail provider
       |     inter-server transport policies vary
       v
Receiving mail provider
       |
       v
Recipient mail client / mailbox
```

**Mã hóa at rest** giúp khi một kho lưu trữ bị truy cập trái phép, nhưng ứng dụng đã được cấp quyền giải mã vẫn có thể thấy plaintext.

**STARTTLS/TLS** bảo vệ một kết nối giữa client và SMTP server trong phạm vi nó được thiết lập và kiểm chứng đúng; không đồng nghĩa mọi hop liên server và hộp thư đều được mã hóa đầu-cuối.

**S/MIME hoặc OpenPGP** có thể bảo vệ phần nội dung thư giữa các đầu cuối khi được triển khai đúng và người nhận có khóa phù hợp; nhưng việc quản trị chứng chỉ/khóa, header metadata và trải nghiệm người nhận phức tạp hơn nhiều.

**Xóa dữ liệu** làm giảm lượng bản sao cần bảo vệ, nhưng không thể bảo đảm xóa ngay mọi bản trong backup hoặc provider mà ứng dụng không kiểm soát.

## 4. Phân biệt ba trạng thái: gửi, chấp nhận và giao thư

`JavaMailSender.send(...)` trả về không ném lỗi thường chỉ cho biết **SMTP submission đã hoàn tất theo bằng chứng của transport**. Nó không chứng minh email đã đến Inbox.

```text
PENDING -> PROCESSING -> SUBMITTED
                 |
                 +-- known transient error -> RETRY_WAIT
                 +-- terminal error --------> FAILED
                 +-- ambiguous outcome -----> UNKNOWN

SUBMITTED -> provider may later report:
             DELIVERED_REMOTE / BOUNCED / DEFERRED
```

Không dùng sự kiện `SUBMITTED` duy nhất làm tín hiệu “được phép xóa mọi thứ” nếu ứng dụng cần giữ payload cho retry/reconciliation hoặc đáp ứng yêu cầu lưu trữ nghiệp vụ. Ngược lại, không cần giữ reset token/plaintext mãi chỉ vì chưa có `DELIVERED_REMOTE`, nếu token đã hết hạn hoặc có chính sách hủy.

**Retention phải phụ thuộc mục đích và trạng thái**, không phụ thuộc một boolean `sent`.

## 5. Data minimization: dữ liệu an toàn nhất là dữ liệu không được lưu

Trước khi mã hóa, hãy giảm những gì email pipeline thực sự cần.

Ví dụ **không nên** đưa cả đối tượng khách hàng vào queue:

```java
record MailJobUnsafe(
        CustomerEntity entireCustomer,
        OrderEntity entireOrder,
        byte[] pdfInvoice,
        String resetToken,
        String htmlBody
) {}
```

Những object này chứa nhiều trường dư thừa, có thể giữ các entity chưa tách khỏi transaction và đưa PII vào serialization/log.

Thay bằng một công việc nhỏ:

```java
record MailJobRef(
        UUID notificationId,
        UUID recipientId,
        String templateKey,
        String templateVersion,
        String encryptedPayloadRef,
        String attachmentObjectVersion
) {}
```

Lợi ích:

- Queue không ôm raw attachment hoặc HTML dài.
- Dễ giới hạn các trường nhạy cảm trong log.
- Payload có thể lưu ở kho mã hóa riêng với TTL.
- Có thể quản lý version/immutability cho retry.
- Dữ liệu nghiệp vụ không cần thiết không đi qua mail worker.

Tuy nhiên, **chỉ lưu reference** không có nghĩa tự động an toàn. Nếu reference là public URL hoặc đối tượng luôn thay đổi, worker có thể truy cập sai dữ liệu hoặc làm lộ bí mật. Reference phải có quyền truy cập, version, chính sách xóa và audit phù hợp.

## 6. Vòng đời một email có dữ liệu nhạy cảm

```text
Business event
      |
      v
Validate recipient + eligibility
      |
      v
Create encrypted payload reference / version
      |
      v
Outbox notification PENDING
      |
      v
Claim + PROCESSING
      |
      v
Decrypt only fields needed
      |
      v
Render + create MimeMessage
      |
      v
SMTP submission
      |
      +--> SUBMITTED
      +--> RETRY_WAIT
      +--> FAILED
      +--> UNKNOWN
      |
      v
Apply retention decision
      |
      +--> keep encrypted payload briefly
      +--> remove rendered/plaintext artifacts
      +--> delete encrypted payload at due time
      +--> keep minimal outcome/audit
```

Điều cần tránh là tạo thêm **bản sao thô không được theo dõi** tại mỗi bước. Mỗi data store phải có owner và retention policy.

## 7. Bảng dữ liệu nào cần giữ, dữ liệu nào nên xóa?

| Dữ liệu | Khi đang chờ gửi | Sau submission | Giải thích |
| --- | --- | --- | --- |
| Notification ID | Giữ | Có thể giữ theo audit policy | Không phải email content nhưng vẫn có thể liên kết cá nhân |
| Recipient ID | Giữ | Có thể giữ có giới hạn | Dùng correlation, suppression và audit |
| Recipient email plaintext | Chỉ khi thật sự cần; hạn quyền | Hạn chế hoặc thay bằng reference | Bảo vệ PII |
| Template key/version | Giữ | Có thể giữ | Hỗ trợ audit và tái dựng nội dung khi được phép |
| Template model nhạy cảm | Mã hóa nếu cần lưu | Xóa khi hết nhu cầu retry | Dữ liệu có thể tái dựng từ nguồn khác hay không? |
| Rendered HTML/plaintext | Ưu tiên tạo sát thời điểm gửi | Loại bỏ bản persistent khi không cần | Tránh giữ cùng một nội dung ở nhiều nơi |
| Raw MIME | Không lưu mặc định | Không lưu mặc định | Có thể chứa token, Bcc, attachment |
| Attachment temp file | Giữ đủ để worker đọc | Cleanup đúng lifecycle | Không xóa trước khi serialize |
| Encrypted attachment blob | Khi cần retry/audit | Xóa theo TTL/retention | Có thể có object versions/backups |
| SMTP provider ID | Giữ khi có | Giữ để reconcile trong hạn | Không bảo đảm provider hỗ trợ mã ID |
| Delivery/bounce events | Theo mục đích, giới hạn trường | Giữ tối thiểu | Có thể chứa diagnostic PII |
| One-time token | Không lưu plaintext | Thu hồi/hết hạn | Hash token hoặc kho chuyên biệt |

Chính sách retention chính xác phải được quyết định dựa trên nghiệp vụ, hợp đồng, quy định và yêu cầu điều tra, **không có một TTL chung đúng cho tất cả hệ thống**.

## 8. Xóa nội dung ngay sau send có thể làm hỏng retry

Một cách làm thiếu an toàn về độ tin cậy:

```java
try {
    mailSender.send(message);
} finally {
    payloadRepository.delete(notificationId);
}
```

Nếu `send(...)` thất bại tạm thời, mất kết nối hoặc có kết quả `UNKNOWN`, payload có thể đã bị xóa dù chính sách còn cần retry hoặc reconcile.

Mô hình đúng hơn:

1. Phân loại outcome của attempt.
2. Ghi kết quả bền vững.
3. Xác định liệu payload còn cần cho attempt tiếp theo.
4. Chỉ lên lịch purge khi đạt retention policy.
5. Cleanup **plaintext artifacts** ngay khi hết phạm vi xử lý.
6. Khi purge thất bại, có cơ chế retry/alert.

**Xóa plaintext sớm** và **xóa mọi bản encrypted source** là hai quyết định khác nhau. Có thể tránh lưu plaintext persistent ngay từ đầu mà vẫn giữ payload mã hóa để retry đúng.

## 9. Chỉ gửi những gì người nhận thực sự cần

Thay vì gửi một file Excel đầy đủ thông tin khách hàng:

```text
Subject: Báo cáo khách hàng quý IV
Attachment: customers-all-fields.xlsx
```

có thể thiết kế nội dung chỉ gồm những trường đã được phép:

```text
Subject: Báo cáo tổng hợp quý IV
Body: Có 235 đơn hàng đã hoàn tất
Attachment: Không cần thiết
Link: Portal có xác thực cho dữ liệu chi tiết
```

Nếu sản phẩm yêu cầu người dùng tải một tài liệu nhạy cảm, một portal có xác thực, phân quyền, audit, TTL và khả năng thu hồi có thể an toàn hơn attachment không thể thu hồi sau khi được forward. Tuy nhiên, link cũng có nguy cơ rò rỉ; không gửi public/bearer URL vô hạn thay cho attachment mà thiếu kiểm soát.

## 10. Spring Mail không tự mã hóa nội dung email trước khi gửi

Ví dụ:

```java
MimeMessage mime = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        mime, true, "UTF-8");

helper.setFrom("notice@example.org");
helper.setTo("recipient@example.net");
helper.setSubject("Thông báo");
helper.setText(
        "Nội dung thông báo",
        "<p>Nội dung thông báo</p>"
);

sender.send(mime);
```

Code này tạo MIME email, không tự dùng end-to-end encryption. `MimeMessageHelper` hỗ trợ xây nội dung và MIME parts; nó không thay thế hệ thống quản lý khóa hay tự biến nội dung thành S/MIME/PGP.

Nếu ứng dụng lưu `MimeMessage`, serialize nó ra file, in nó bằng `writeTo(System.out)` hoặc ghi exception kèm payload, thông tin có thể xuất hiện ở dạng đọc được trong những nơi ấy.

## 11. STARTTLS giúp gì và không giúp gì?

Một cấu hình Spring Boot phổ biến:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 15000
      "[mail.smtp.writetimeout]": 15000
```

Đây là **cấu hình minh họa** cho một SMTP relay hỗ trợ STARTTLS và xác thực bằng username/password. Port, chế độ TLS và thuộc tính cần được đối chiếu với provider cụ thể. Với implicit TLS, cấu hình khác và thường dùng một port riêng.

`mail.smtp.starttls.required=true` yêu cầu nâng cấp STARTTLS thay vì âm thầm tiếp tục plaintext trên kết nối SMTP được cấu hình theo cách đó. Kiểm tra danh tính server bằng chính sách certificate/hostname phù hợp giúp giảm nguy cơ kết nối tới endpoint không đúng.

**Giới hạn của STARTTLS:** nó bảo vệ kết nối **từ ứng dụng đến SMTP relay này** khi thiết lập đúng. Nó không bảo đảm relay không đọc/lưu email, không bảo đảm mọi hop liên server có TLS, và không bảo đảm email được mã hóa trong mailbox của recipient.

## 12. Encryption at rest: bảo vệ bản sao mà ứng dụng lưu

Có nhiều mức bảo vệ:

| Lớp | Ví dụ | Ngăn được | Không ngăn được |
| --- | --- | --- | --- |
| Disk encryption | Mã hóa volume | Mất ổ đĩa/thiết bị | Process có quyền đọc filesystem |
| Database transparent encryption | TDE theo hệ DB | Một số trường hợp mất file backup/disk | User DB có quyền query plaintext |
| Object storage server-side encryption | KMS-managed bucket encryption | Truy cập trái phép vào storage media theo policy | App/service có quyền GetObject+Decrypt |
| Application-level field encryption | AES-GCM trước khi lưu row | Đọc DB dump không có key | App/KMS principal được cấp decrypt |
| Client-side E2E mail encryption | S/MIME/OpenPGP | Provider thường không đọc được protected content | Headers/metadata và endpoint compromise |

Các lớp có thể kết hợp. **Không có một lớp duy nhất loại bỏ mọi rủi ro**. Ví dụ application-level encryption giúp giảm tác động của một bản DB dump bị lộ, nhưng nếu attacker cũng lấy được KMS credentials, bảo vệ giảm đáng kể.

## 13. Chọn mã hóa xác thực: AES-GCM

Khi cần mã hóa một payload nhỏ trước khi lưu vào outbox, có thể dùng **AES-GCM**. Nó cung cấp:

- Tính bí mật của nội dung.
- Kiểm tra tính toàn vẹn/xác thực thông qua authentication tag.
- Khả năng dùng **Additional Authenticated Data (AAD)** để ràng buộc ciphertext vào context.

Các quy tắc:

1. Dùng một khóa AES có độ mạnh phù hợp (ví dụ 256 bit theo chính sách).
2. Dùng nonce/IV **không được tái sử dụng với cùng khóa**; 96 bit là kích thước thường dùng cho GCM.
3. Tạo IV mới bằng `SecureRandom` đủ chất lượng cho mỗi lần mã hóa.
4. Lưu version/algorithm, IV, ciphertext+tag và key reference.
5. Không tự viết AES hoặc sửa kết quả mã hóa bằng Base64 rồi gọi đó là “encryption”.
6. Không dùng ECB hoặc các chế độ không xác thực cho payload mới.
7. Khi giải mã thất bại do tag, **không trả về plaintext từng phần** hoặc lờ lỗi.
8. Giữ secret ngoài code/config public; quản lý bằng KMS/HSM/secret manager.

### AAD dùng làm gì?

Ví dụ AAD có thể bao gồm:

```text
tenantId | notificationId | payloadType | schemaVersion
```

Nhờ đó, một ciphertext bị copy sang notification khác với AAD khác sẽ không giải mã hợp lệ. AAD **không được mã hóa**, vì vậy không đặt thông tin nhạy cảm vào AAD chỉ để mong nó được che giấu.

## 14. Ví dụ Java: mã hóa và giải mã payload bằng AES-GCM

Đây là **một thành phần minh họa cho application-level encryption**, không phải API có sẵn của `JavaMailSender`. Trong production, khóa phải đến từ cơ chế KMS/secret management và payload metadata phải có version/schema rõ.

```java
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;

public final class PayloadAesGcm {

    private static final int IV_LENGTH = 12;      // 96-bit GCM nonce
    private static final int TAG_BITS = 128;
    private static final SecureRandom RANDOM = new SecureRandom();

    public record SealedPayload(
            int formatVersion,
            byte[] iv,
            byte[] ciphertextAndTag
    ) {
        public SealedPayload {
            iv = iv.clone();
            ciphertextAndTag = ciphertextAndTag.clone();
        }

        @Override
        public byte[] iv() {
            return iv.clone();
        }

        @Override
        public byte[] ciphertextAndTag() {
            return ciphertextAndTag.clone();
        }
    }

    public static SealedPayload encrypt(
            SecretKey key,
            byte[] plaintext,
            byte[] aad
    ) throws GeneralSecurityException {

        byte[] iv = new byte[IV_LENGTH];
        RANDOM.nextBytes(iv);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, iv)
        );
        cipher.updateAAD(aad);

        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        return new SealedPayload(
                1,
                iv,
                ciphertextAndTag
        );
    }

    public static byte[] decrypt(
            SecretKey key,
            SealedPayload sealed,
            byte[] aad
    ) throws GeneralSecurityException {

        if (sealed.formatVersion() != 1
                || sealed.iv().length != IV_LENGTH) {
            throw new GeneralSecurityException(
                    "Unsupported encrypted payload format"
            );
        }

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, sealed.iv())
        );
        cipher.updateAAD(aad);

        // Throws AEADBadTagException if ciphertext/AAD/key
        // was modified or does not match.
        return cipher.doFinal(sealed.ciphertextAndTag());
    }
}
```

Để dùng:

```java
byte[] aad = buildAad(
        tenantId, notificationId, "mail-template-data", 1
);

byte[] plaintext = serializeApprovedTemplateModel(model);
PayloadAesGcm.SealedPayload sealed =
        PayloadAesGcm.encrypt(dataKey, plaintext, aad);

// Lưu sealed.iv(), sealed.ciphertextAndTag(),
// formatVersion và reference của dataKey.
```

`buildAad(...)` và `serializeApprovedTemplateModel(...)` là hàm do ứng dụng cung cấp. **Phải tạo AAD có định dạng canonical, không mơ hồ**, ví dụ serialization có độ dài trường/kiểu dữ liệu rõ thay vì nối chuỗi với dấu phân cách có thể xuất hiện trong input.

### Điều gì còn thiếu trong ví dụ?

- Không có code cấp phát/lấy khóa từ KMS.
- Không có schema version cho dữ liệu nghiệp vụ.
- Chưa có authorization cho người gọi decrypt.
- Chưa có quản lý key rotation/revocation.
- Chưa có chính sách xử lý lỗi KMS, rate limit hoặc key unavailable.
- Chưa có cleanup/retention và quyền truy cập database.
- Chưa có logging/redaction policy cho exception.

Không copy ví dụ này vào production rồi đặt một khóa AES cố định trong source code.

## 15. Nonce reuse là rủi ro nghiêm trọng của GCM

Với cùng một khóa GCM, **tái sử dụng IV/nonce** cho hai thông điệp có thể làm mất bảo mật và tính toàn vẹn. Vì vậy:

```java
// Không làm:
byte[] iv = new byte[12]; // toàn số 0 cho mọi payload
```

Trong ví dụ Java, `SecureRandom` tạo IV ngẫu nhiên cho mỗi lần mã hóa. Với hệ thống khối lượng cực lớn hoặc nhiều instance dùng chung khóa trong thời gian dài, cần thiết kế giới hạn số lần mã hóa/key và nonce management theo tiêu chuẩn an toàn của hệ mật mã được chọn.

**Không tự tăng IV bằng một biến static trong JVM nếu nhiều nodes cùng dùng khóa**; các nodes có thể tạo trùng giá trị. Nếu dùng nonce theo counter, counter phải có thiết kế phân phối/khả năng khôi phục và đảm bảo uniqueness chặt chẽ.

Khi dùng một thư viện/provider crypto có API envelope encryption được bảo trì và kiểm toán, nên ưu tiên abstraction ấy hơn tự tạo format crypto riêng.

## 16. Mã hóa payload JSON hay mã hóa từng trường?

Có hai cách phổ biến:

**Mã hóa toàn payload object**:

```json
{
  "encryptedPayloadRef": "opaque-ref-123",
  "schemaVersion": 2
}
```

Payload lưu ở kho riêng dưới dạng ciphertext; template model giải mã chỉ khi render.

**Mã hóa từng trường**:

```text
notification_id         UUID (clear metadata)
template_key            string
recipient_email_enc     ciphertext
display_name_enc        ciphertext
invoice_data_ref        opaque reference
```

| Chiến lược | Ưu điểm | Nhược điểm |
| --- | --- | --- |
| Whole-object encryption | Ít nguy cơ bỏ sót trường, dễ giới hạn quyền decrypt | Khó query/filter theo một field |
| Field-level encryption | Có thể tách quyền cho từng trường | Quản trị schema/keys/rotation phức tạp |
| Storage encryption only | Đơn giản, thường ít thay đổi app code | App/DB principal có thể đọc plaintext |
| Data minimization + references | Giảm nội dung nằm trong mail DB | Cần quản lý data source và lifecycle nguồn |

Nếu cần query theo email address mà cột đã được mã hóa ngẫu nhiên bằng AES-GCM, không thể query equality trực tiếp trên ciphertext vì mỗi lần mã hóa có nonce mới. Có thể thiết kế **blind index/HMAC** trên giá trị được chuẩn hóa theo policy, nhưng nó tạo rủi ro phân tích tần suất và cũng cần key riêng/rotation.

Không dùng SHA-256 không khóa trên một tập giá trị nhỏ, dễ đoán như email/OTP rồi coi đó là ẩn danh chắc chắn.

## 17. KMS và envelope encryption

Một mẫu production thường dùng **envelope encryption**:

```text
Key Management Service (KMS)
           |
           | generate/wrap data key
           v
Encrypted Data Key (EDK) ----> store with ciphertext
           |
           | plaintext data key available briefly
           v
Application encrypts payload with AES-GCM
           |
           v
DB/Object Storage:
  - ciphertext
  - IV/nonce
  - auth tag
  - encrypted data key / key reference
  - algorithm + schema version
  - AAD context identifiers
```

Lúc giải mã:

1. Kiểm tra caller/tenant/notification được phép.
2. Lấy ciphertext, IV và wrapped data key.
3. Gọi KMS để unwrap data key theo quyền và context.
4. Dùng key giải mã AES-GCM với AAD chính xác.
5. Chỉ giữ plaintext đủ lâu để render/gửi.
6. Không log data key hoặc plaintext.

KMS có thể thực hiện encryption trực tiếp cho payload nhỏ, hoặc quản lý key bọc data keys. Lựa chọn phụ thuộc giới hạn API, kích thước payload, latency, chi phí, rotation và security requirements.

### KMS bảo vệ những gì?

KMS giúp quản lý key lifecycle, access control và audit; nó **không thể ngăn code ứng dụng đã được phép decrypt tự log plaintext**. Cần tách quyền và tuân thủ least privilege.

## 18. Thiết kế metadata cho encrypted payload

Một bản ghi có thể chứa:

```text
payload_id
notification_id
tenant_id
format_version
data_schema_version
algorithm_id = AES-256-GCM
kms_key_ref
encrypted_data_key
iv
ciphertext_and_tag
created_at
expires_at
encryption_context_version
```

Đặt `expires_at` **không đồng nghĩa dữ liệu sẽ tự biến mất**. Cần worker hoặc storage TTL/lifecycle có khả năng xóa thực và một cách chứng minh trạng thái cleanup.

### Không “đặt key ID” thay cho quản lý khóa

Một cột `kms_key_ref` chỉ giúp xác định khóa; cần thiết kế:

- Khóa thuộc tenant/region/loại dữ liệu nào?
- Principal nào được decrypt?
- Có tách quyền giữa mail worker, web API và admin không?
- Key rotation ảnh hưởng dữ liệu cũ thế nào?
- Khi key bị thu hồi, các notifications đang pending/retry ra sao?
- Logs/audit của KMS có chứa thông tin định danh nhạy cảm không?

Nếu email pipeline có nhiều tenants với isolation nghiêm, cân nhắc key scopes và IAM conditions phù hợp.

## 19. Rotation, re-encrypt và cryptographic erasure

**Key rotation** có thể có nhiều nghĩa:

- Tạo phiên bản master/wrapping key mới cho dữ liệu mới.
- Rewrap encrypted data keys cũ bằng phiên bản key mới.
- Re-encrypt payload bằng data key mới.
- Thu hồi key đã bị lộ.
- Xóa key khiến những ciphertext liên quan không còn giải mã được.

Không mặc định “bật auto-rotation trên KMS” sẽ tự mã hóa lại mọi ciphertext hoặc xóa khả năng giải mã bản cũ. Cách hoạt động phụ thuộc hệ thống key management và kiểu envelope encryption.

### Cryptographic erasure

Khi không còn cần nội dung, có thể xóa ciphertext và/hoặc hủy khóa cần thiết để giải mã. Hủy khóa có thể làm những bản encrypted còn trong backup không thể được giải mã, **nhưng chỉ khi không còn bản sao khóa/data key/plaintext ở vị trí khác**.

Ví dụ nếu 1.000 records dùng chung một data key mà còn cần giữ 999 records, không thể hủy key để xóa riêng record thứ 1 mà không làm mất 999 records còn lại. Cần thiết kế key granularity từ trước nếu có yêu cầu xóa có chọn lọc.

**Không tuyên bố xóa tuyệt đối bằng cách delete một KMS alias.** Alias là tên/định tuyến key, không nhất thiết là key material; cần tuân thủ đúng lifecycle của key và lưu ý tác động không thể đảo ngược.

## 20. Khả năng tìm kiếm và mối quan hệ với quyền riêng tư

Team vận hành thường muốn tìm notification theo email. Nếu bạn lưu raw email để search, việc mã hóa body chỉ bảo vệ một phần dữ liệu.

Các lựa chọn:

- Lưu `recipientId` nội bộ, tra email qua một service có quyền riêng.
- Dùng một chỉ mục HMAC theo canonicalization đã định nghĩa.
- Lưu prefix/domain hoặc bucket thống kê khi đủ cho analytics.
- Tách bảng PII với role/permission hạn chế.

Chỉ mục HMAC:

```text
index = HMAC(searchKey, canonicalRecipientEmail)
```

không thể giải ngược trực tiếp nếu thiếu key, nhưng vẫn có leakage về equality và phân bố giá trị. Với dữ liệu có entropy thấp, phải đánh giá nguy cơ suy đoán, compromise key, quyền tìm kiếm và rotation. HMAC search key không nên dùng chung với encryption key.

Không gắn blind index vào logs hoặc metrics public rồi coi đó là không còn dữ liệu cá nhân; nó vẫn có thể là định danh liên kết.

## 21. Payload bất biến để retry nhưng không lưu plaintext

Giả sử email hóa đơn phải được gửi lại nếu provider tạm không có kết nối. Một lựa chọn:

```text
Invoice issued
   |
   v
Create versioned immutable invoice PDF
   |
   v
Encrypt object or store with controlled KMS encryption
   |
   v
Outbox:
  notificationId
  recipientId
  templateVersion
  invoiceObjectVersion
  encryptedModelRef
   |
   v
Worker loads/decrypts and sends
```

Không cần giữ một bản raw `MimeMessage` đã serialize trong database nếu có thể dựng lại từ snapshot bất biến. Tuy nhiên, nếu nghiệp vụ hoặc pháp lý yêu cầu **lưu đúng byte đã phát hành**, nên có một archive chính thức với retention và encryption riêng, thay vì tận dụng logs hay temp folder như nơi lưu trữ.

### Vì sao cần versioned object?

Nếu object key trỏ đến một file thay đổi theo thời gian, lần retry sau có thể gửi một hóa đơn khác với lần đầu. Data minimization không được đánh đổi tính đúng đắn của nội dung. Dùng object version hoặc immutable content address nếu phù hợp và không lộ thông tin.

## 22. Email body và template model: lưu ở đâu?

Một email HTML có thể tạo từ:

```text
templateKey = payment-receipt
templateVersion = 4
model = {
  customerDisplayName,
  orderCode,
  totalAmount,
  receiptLink
}
```

Có thể áp dụng các chiến lược:

| Chiến lược | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| Render sát lúc gửi từ dữ liệu nghiệp vụ | Nội dung phải phản ánh trạng thái mới nhất | Dữ liệu có thể thay đổi; cần policy rõ |
| Snapshot model đã mã hóa | Cần nội dung nhất quán qua retry | Quản lý key, schema, TTL |
| Lưu rendered MIME đã mã hóa | Có yêu cầu byte-for-byte archive | Tốn storage, nguy cơ nhiều bản sao |
| Chỉ lưu ID và link portal | Không cần đính kèm nội dung nhạy cảm | Quyền truy cập và token expiry |

Không có chiến lược đúng duy nhất. Với một email “Trạng thái đơn hàng hiện tại”, render dữ liệu mới nhất có thể phù hợp; với hóa đơn đã phát hành, snapshot immutable thường cần thiết để tránh nội dung thay đổi khi retry.

## 23. Không đưa reset token plaintext vào outbox

Một lỗi phổ biến:

```java
record ResetPasswordMail(
        String email,
        String resetToken,
        String html
) {}

// Đẩy record chứa raw token vào queue/log/database.
```

Nếu token được lưu plaintext, ai đọc queue/outbox có thể dùng nó để chiếm quyền account khi token còn hiệu lực.

Một thiết kế thay thế tùy kiến trúc:

1. Tạo token entropy cao bằng CSPRNG.
2. Chỉ lưu **token verifier/digest** thích hợp ở hệ reset-password (được bảo vệ), cùng TTL và single-use state.
3. Trong đoạn gửi email, tạo token sát thời điểm gửi hoặc giữ bản token cần gửi trong kho **mã hóa với retention cực ngắn**, không để raw token đi vào logs.
4. Hạn chế quyền decrypt của mail worker.
5. Thu hồi token khi dùng, khi hết hạn hoặc sau reset thành công.
6. Nếu email cần retry sau khi token hết hạn, **không gửi lại link đã hết hiệu lực**; cần policy tạo yêu cầu mới.

Lưu hash token một chiều giúp xác minh token về sau nhưng **không thể tái dựng token để gửi email**. Vì thế, bài toán “tạo token rồi gửi bất đồng bộ” cần chọn một trong các chiến lược phù hợp: mã hóa bản token tạm thời, tạo token trong worker, hoặc quy trình token issuance riêng. Không mô tả việc lưu hash như thể từ hash có thể lấy lại token gốc.

### Cân nhắc lưu token trong URL

Magic link/reset link có thể xuất hiện trong browser history, proxy log, email security scanners hoặc link preview. Cần TTL, one-time use, domain chính thức, HTTPS và một cơ chế không để token vô tình bị xác nhận bởi prefetch. Việc thay một OTP thô bằng một URL có bearer token **không tự loại bỏ rủi ro lộ bí mật**.

## 24. Encryption at rest không thay thế TLS và recipient validation

Một record outbox mã hóa rất tốt vẫn có thể gửi nhầm đến người nhận nếu:

```java
helper.setTo(untrustedRecipient);
sender.send(message);
```

Giá trị To có thể được lấy từ input chưa validate hoặc dữ liệu sai nghiệp vụ. Khi đó, bí mật được giải mã đúng nhưng gửi tới sai người.

Trước submission:

- Kiểm tra recipient được phép nhận loại thông báo này.
- Kiểm tra consent/suppression theo quy định và nghiệp vụ.
- Kiểm tra tenant ownership.
- Bcc và reply-to không được lấy tùy tiện từ untrusted headers.
- Xác nhận template và attachment thuộc đúng notification.
- Không tự render raw HTML từ user data mà không escape.

**Mã hóa dữ liệu là một biện pháp phòng thủ, không thay thế quyền truy cập và tính đúng đắn của recipient.**

## 25. Dữ liệu trong Java heap: giới hạn của việc “xóa”

Khi decrypt payload, ứng dụng có thể tạo:

```java
byte[] plaintext = decrypt(...);
String html = renderer.render(...);
MimeMessage message = sender.createMimeMessage();
```

Một `byte[]` có thể được ghi đè sau khi sử dụng:

```java
try {
    processPlaintext(plaintext);
} finally {
    Arrays.fill(plaintext, (byte) 0);
}
```

Nhưng điều đó **không bảo đảm mọi bản sao plaintext đã biến mất khỏi heap**:

- `String` immutable không có cơ chế wipe đáng tin cậy.
- Renderer/template engine có thể tạo các chuỗi và buffer trung gian.
- Jakarta Mail có thể giữ dữ liệu trong MIME parts.
- Java/JIT/GC có thể tạo hoặc di chuyển object trong memory.
- Crash dump/core dump/heap dump có thể chứa nội dung đã được render.

Do đó mục tiêu thực tế là **giảm thời gian tồn tại và số bản sao**, kiểm soát heap dump và swap/disk, tránh object retention dài, không hứa zeroization tuyệt đối trên JVM managed runtime.

## 26. File tạm là một bản sao dữ liệu, dù không nằm trong database

Khi ứng dụng tạo PDF/CSV attachment:

```java
Path file = Files.createTempFile(
        "mail-invoice-", ".pdf");
invoiceRenderer.writeTo(file, invoiceData);
```

File này có thể nằm trên:

- Local disk của container/VM.
- Shared filesystem được mount.
- Volume dùng chung với các process khác.
- Disk có snapshot hoặc backup.
- Storage ephemeral vẫn tồn tại trong vòng đời node.

**Không mặc định thư mục “temp” có nghĩa là file tự bị xóa sau khi mail được gửi**. Cũng không nên đặt dữ liệu nhạy cảm vào thư mục có quyền đọc rộng.

### Quy tắc cho temp file

1. Tạo trong thư mục chuyên dụng với quyền truy cập hạn chế.
2. Không đặt tên chứa email address, họ tên hoặc thông tin bí mật.
3. Dùng tên ngẫu nhiên/opaque để tránh collision.
4. Chỉ giữ đủ lâu cho quá trình MIME serialization và retry policy đã định.
5. Xóa sau khi không còn cần; ghi nhận failure nếu không xóa được.
6. Có sweeper định kỳ cho file còn lại sau crash.
7. Có quota disk và cảnh báo dung lượng.
8. Xem xét encryption ở volume hoặc mã hóa riêng khi nội dung rất nhạy cảm.
9. Không cho worker tải file từ path người dùng cung cấp khi chưa validate quyền và path.
10. Đừng bật backup/snapshot thư mục temp theo thói quen nếu không phù hợp retention.

## 27. FileSystemResource có thể được đọc lúc send, không phải lúc addAttachment

Ví dụ:

```java
Path invoicePath = createTemporaryInvoice();

MimeMessage mime = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        mime, true, "UTF-8");
helper.setTo("recipient@example.net");
helper.setFrom("billing@example.org");
helper.setSubject("Hóa đơn");
helper.setText("Xem hóa đơn đính kèm.");
helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(invoicePath)
);

Files.delete(invoicePath);  // Có thể xóa quá sớm!
sender.send(mime);
```

`addAttachment(...)` gắn một nguồn nội dung vào MIME part; file có thể chỉ được đọc khi Jakarta Mail serialize message hoặc transport gửi DATA. Nếu xóa file trước `send(...)`, việc gửi có thể thất bại hoặc attachment không còn đọc được.

Một ví dụ đúng hơn về vòng đời **gửi đồng bộ**:

```java
Path invoicePath = createTemporaryInvoice();

try {
    MimeMessage mime = composeWithAttachment(invoicePath);
    sender.send(mime);
} finally {
    Files.deleteIfExists(invoicePath);
}
```

**Điều kiện:** ví dụ này chỉ phù hợp nếu file có thể bị xóa ngay sau attempt và ứng dụng còn nguồn bền vững để retry hoặc đã có chính sách rõ về failure. Với send bất đồng bộ, xóa trong caller `finally` ngay sau enqueue là **quá sớm**. Với retry sau crash, một file temp ephemeral có thể không đủ.

## 28. Không dùng InputStreamResource single-use một cách tùy tiện

Một `InputStreamResource` thường dựa trên stream đã mở, có thể chỉ đọc được một lần. Jakarta Mail có thể yêu cầu dữ liệu từ MIME part ở nhiều giai đoạn.

```java
InputStream stream = storage.openStream(key);
InputStreamSource risky = new InputStreamResource(stream);
helper.addAttachment(
        "document.pdf",
        risky,
        "application/pdf"
);
```

Để hỗ trợ đọc lại theo contract, có thể dùng:

```java
InputStreamSource source = () ->
        storage.openStream(versionedObjectKey);
```

Mỗi lần `getInputStream()` tạo một stream mới. Nhưng cần bảo đảm:

- Object/version còn tồn tại cho tới khi attempt hoàn thành.
- Truy cập storage có authentication/authorization và timeout.
- Không lưu signed URL còn hiệu lực lâu trong log hoặc database không bảo vệ.
- Không ghi tạm plaintext xuống disk không kiểm soát.
- Stream được thư viện đóng đúng vòng đời theo contract.
- Không tự giả định streaming nghĩa là hoàn toàn không có plaintext trong heap.

Đối với encrypted object từ object storage, việc mở stream giải mã cần giới hạn kích thước và xác thực nội dung; nếu dùng mã hóa xác thực, **không được cung cấp dữ liệu chưa xác thực làm attachment hợp lệ**. Chọn thư viện/format streaming authenticated encryption có contract rõ khi file lớn, thay vì tự chia một GCM ciphertext tùy tiện rồi gửi từng phần chưa verify.

## 29. Attachment trong object storage: lifecycle và versioning

Một kiến trúc:

```text
Encrypted object:
  tenant/invoice/opaque-id/version
             |
             v
Outbox holds:
  notificationId + objectVersionId
             |
             v
Worker decrypts/streams content
             |
             v
JavaMailSender SMTP submission
             |
             v
Retention worker deletes object/version
```

Khi object storage có versioning:

- Xóa key hiện tại có thể chỉ tạo delete marker.
- Các phiên bản cũ vẫn tồn tại.
- Replication có thể tạo thêm bản sao sang region khác.
- Lifecycle expiration có thể xử lý từng version theo chính sách riêng.
- Multipart upload chưa hoàn thành có thể cần quy trình dọn.
- Backups hoặc object lock/retention policy có thể ngăn xóa ngay.

**Không báo “payload đã xóa hoàn toàn” chỉ vì một lệnh delete object trả thành công** nếu storage đang giữ các versions/replicas được quản lý riêng.

### Một cleanup job nên biết gì?

```text
payloadReference
objectVersion
encryptionKeyReference
expiryPolicy
retentionHold
deletionRequestedAt
deletionConfirmedAt
lastErrorCategory
```

Đối tượng cần xóa phải được lấy từ metadata nội bộ đã xác minh, không tự ghép path theo chuỗi email của người dùng.

## 30. Retention khác nhau theo trạng thái

Một chính sách minh họa, **không phải khuyến nghị thời gian cố định**:

| Trạng thái | Nội dung cần giữ? | Quy tắc ra quyết định |
| --- | --- | --- |
| `PENDING` | Có thể giữ encrypted payload/reference | Còn chưa tới lượt gửi |
| `PROCESSING` | Giữ đến khi attempt kết thúc hoặc lease được reconcile | Worker đang dùng nguồn |
| `RETRY_WAIT` | Giữ source đủ cho attempt tiếp theo | Cần kiểm tra TTL và tính hợp lệ |
| `SUBMITTED` | Có thể xóa source theo policy | Có cần lưu cho audit/recipient resend không? |
| `FAILED` | Có thể xóa sớm sau khi hết cửa sổ điều tra | Không cần giữ full body vô hạn |
| `UNKNOWN` | Cân nhắc giữ encrypted source ngắn hạn | Chưa biết gửi rồi hay chưa |
| `CANCELED` | Loại bỏ payload khi không còn mục đích khác | Không đụng các bản đã submit bên ngoài |
| `EXPIRED` | Xóa token/attachment theo policy | Nội dung không còn giá trị |

Một vài hệ thống giữ encrypted payload sau `SUBMITTED` trong một khoảng ngắn để hỗ trợ **manual resend**. Nếu có nhu cầu đó, cần quyền gửi lại, audit và quản lý nguy cơ duplicate; không lấy “có thể resend” làm lý do lưu dữ liệu vô hạn.

### Chỉ xóa payload, giữ metadata tối thiểu

Sau purge, có thể giữ:

```text
notificationId
messageClass
templateVersion
createdAt
submittedAt
status
payloadPurgedAt
providerRoute
errorCategory (not raw body)
```

Ngay cả metadata có thể là dữ liệu cá nhân khi liên kết tới recipient/tenant. Retention của metadata cũng phải được thẩm định; “không chứa body” không có nghĩa được giữ mãi.

## 31. Tạo chính sách retention dựa trên mục đích

Không dùng một con số như “30 ngày” cho mọi thông báo mà không giải thích:

- **Mục đích gửi:** OTP vài phút, hóa đơn nhiều năm, campaign theo chiến dịch.
- **Cơ sở lưu trữ:** có yêu cầu hồ sơ/audit hợp lệ không?
- **Retry window:** tối đa bao lâu còn được phép submit?
- **Provider feedback window:** có cần đối chiếu bounce/delivery?
- **Attachment source:** đã lưu chính thức ở hệ nghiệp vụ khác chưa?
- **Dữ liệu bị thu hồi:** hủy yêu cầu, đổi consent, user xóa account?
- **Vị trí lưu:** primary DB, object versions, cache, backup, third-party logs.
- **Legal hold:** có yêu cầu giữ một record cụ thể không?

Một policy có thể được thể hiện thành:

```text
DataClass: MAIL_TEMPLATE_MODEL
Purpose: render and retry transactional notification
Storage: application encrypted payload store
EligibleForPurge: terminal or retry expired
RetentionAfterTerminal: configured duration
LegalHoldSupport: yes
DeletionMethod: delete payload ref + wrapped DEK
Audit: status and timestamp only
```

Thời hạn cụ thể phải do nhóm nghiệp vụ, bảo mật và pháp lý quyết định theo quy định áp dụng. Không giả định một vùng pháp lý có thời hạn xóa chung cho mọi loại email.

## 32. Đừng gắn purge trực tiếp vào callback SMTP

Một anti-pattern:

```java
sender.send(message);
payloadStorage.delete(payloadId);
```

Nếu process crash sau khi SMTP accepted và trước khi xóa, payload còn tồn tại. Nếu delete thất bại, code cần cơ chế retry cleanup. Nếu phương thức được thực hiện trong một transaction DB dài, SMTP I/O giữ lock không cần thiết.

Thiết kế tốt hơn:

```text
Mail worker
   |
   +-- submit SMTP
   +-- record outcome
   +-- schedule payload retention deadline
   |
   v
Background cleanup worker
   |
   +-- selects eligible payloads
   +-- checks active leases/legal holds
   +-- deletes exact storage version
   +-- records minimal tombstone/result
   +-- retries cleanup failures safely
```

Việc cleanup nên là **một workflow có state** thay vì một câu lệnh không quan sát được. Nhờ đó failure của object storage hoặc KMS không khiến dữ liệu bị giữ vô thời hạn mà không ai biết.

## 33. Mô hình dữ liệu: tách outbox khỏi encrypted payload

Ví dụ PostgreSQL mang tính giảng dạy:

```sql
CREATE TABLE mail_notification (
    notification_id UUID PRIMARY KEY,
    recipient_id UUID NOT NULL,
    status VARCHAR(32) NOT NULL,
    template_key VARCHAR(100) NOT NULL,
    template_version VARCHAR(40) NOT NULL,
    encrypted_payload_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE mail_encrypted_payload (
    payload_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    format_version INTEGER NOT NULL,
    kms_key_ref VARCHAR(250) NOT NULL,
    encrypted_data_key BYTEA NOT NULL,
    iv BYTEA NOT NULL,
    ciphertext_and_tag BYTEA NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    state VARCHAR(32) NOT NULL DEFAULT 'AVAILABLE',
    deletion_requested_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX ix_mail_payload_expiry
    ON mail_encrypted_payload(expires_at, payload_id)
    WHERE state = 'AVAILABLE';

CREATE TABLE mail_submission_attempt (
    attempt_id UUID PRIMARY KEY,
    notification_id UUID NOT NULL
        REFERENCES mail_notification(notification_id),
    status VARCHAR(32) NOT NULL,
    provider_key VARCHAR(80),
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ
);
```

Trong production, thường còn có recipient policy, tenant isolation, foreign key constraints, storage object versions, indexes và concurrency controls. Không coi ví dụ schema là migration dùng ngay.

### Vì sao không đặt payload bytea trực tiếp trên notification row?

Tách bảng giúp:

- Giới hạn quyền `SELECT` cho những thành phần cần decrypt.
- Đặt retention/index và lifecycle riêng.
- Xóa body/attachment source mà vẫn giữ audit metadata.
- Giảm số lượng người/worker phải đọc dữ liệu nhạy cảm.

Nhưng tách bảng không tự chống rò rỉ nếu mọi service vẫn dùng cùng database credentials có quyền đọc cả hai.

## 34. Purge phải tránh race với worker đang gửi

Tình huống:

```text
10:00 Worker A claims mail, bắt đầu đọc encrypted payload
10:01 Cleanup worker thấy expires_at đã qua
10:01 Cleanup deletes payload
10:02 Worker A cần đọc attachment lần thứ hai
10:02 SMTP submission fails vì source không còn
```

Một cách giải quyết:

- Mail worker có claim/lease đủ dài và được gia hạn nếu xử lý lâu.
- Cleanup chỉ xóa khi notification không active và payload không còn được tham chiếu bởi attempt đang hợp lệ.
- Nếu có shared payload dùng bởi nhiều notifications, cần reference counting hoặc policy theo tất cả consumers.
- TTL không được đồng nhất với thời điểm file chắc chắn không còn được dùng.
- Khi quá hạn bắt buộc phải xóa vì security policy, worker phải ngừng/cancel và ghi trạng thái phù hợp thay vì tiếp tục gửi từ dữ liệu hết hạn.

Quy tắc “chờ worker xong” và quy tắc “xóa dữ liệu quá hạn” cần một ưu tiên có quyết định trước, không chỉ so sánh một timestamp.

## 35. Ví dụ trạng thái cleanup

```text
AVAILABLE
   |
   v
ELIGIBLE_FOR_PURGE
   |
   v
DELETE_IN_PROGRESS
   |
   +-- storage temporarily fails --> DELETE_RETRY
   |                                      |
   |                                      v
   |                              DELETE_IN_PROGRESS
   |
   +-- deletion confirmed -------> PURGED
   |
   +-- legal hold ---------------> HELD
```

**`PURGED` cần được định nghĩa cụ thể:** xóa khỏi primary database? xóa bản object version? xóa wrapped key? hay đã hết khả năng truy cập qua ứng dụng? Tránh đặt tên trạng thái chung mà không biết scope của bảo đảm.

Nếu phải tuân thủ một yêu cầu xóa toàn hệ thống, cần có danh mục storage targets và một bản ghi kết quả từng nơi thay vì chỉ một boolean.

## 36. Purge bằng SQL có điều kiện

Một bước xác định những payload đủ hạn:

```sql
SELECT p.payload_id
FROM mail_encrypted_payload p
WHERE p.state = 'AVAILABLE'
  AND p.expires_at <= now()
  AND NOT EXISTS (
      SELECT 1
      FROM mail_notification n
      JOIN mail_submission_attempt a
        ON a.notification_id = n.notification_id
      WHERE n.encrypted_payload_id = p.payload_id
        AND a.status IN (
            'PROCESSING', 'RETRY_WAIT', 'UNKNOWN'
        )
  )
ORDER BY p.expires_at, p.payload_id
FOR UPDATE OF p SKIP LOCKED
LIMIT 100;
```

Đây là **truy vấn minh họa**, chưa thể là toàn bộ chính sách purge. Trong thực tế cần:

- Kiểm tra legal hold, retention exception, shared references và active leases.
- Claim payload/mark `DELETE_IN_PROGRESS` trong transaction ngắn.
- Commit trước khi gọi object storage/KMS nếu thao tác ngoài database.
- Xử lý retry khi delete một trong nhiều storage targets thất bại.
- Xóa bytes nhạy cảm với một bước bền vững sau khi đã kiểm tra điều kiện.
- Không sử dụng cùng một database transaction để bao cả network calls và cleanup phức tạp.

**Không chỉ chạy một `DELETE FROM mail_encrypted_payload WHERE expires_at < now()` trong production** nếu dữ liệu có thể vẫn được worker sử dụng hoặc đang bị legal hold.

## 37. Delete idempotency và tombstone

Một cleanup worker có thể crash sau khi đã xóa object nhưng trước khi cập nhật database. Khi chạy lại, câu lệnh delete object có thể báo “not found”.

Nếu object version đã được xác minh là mục tiêu cần xóa, `not found` có thể được coi là cleanup hoàn tất trong phạm vi cụ thể. Nhưng **không nhầm “không tìm thấy” vì thiếu quyền hoặc sai key với đã xóa thành công**.

Một tombstone metadata:

```text
payloadId
deletionRequestId
targetClass
deletionPolicyVersion
requestedAt
completedAt
resultCategory
```

Không giữ raw recipient hoặc nội dung để chứng minh việc đã xóa nội dung. Chỉ lưu metadata vừa đủ theo audit policy; tombstone cũng có retention riêng.

## 38. Backup và snapshot: xóa ở primary không xóa ngay mọi bản

Khi database có backup:

```text
Primary DB: payload deleted at T1
Daily backup created at T0 (< T1)
Backup retained until T2 (> T1)
```

Backup có thể vẫn chứa bản encrypted payload cũ. Cần trả lời:

- Backup được mã hóa và ai có quyền restore?
- Thời hạn backup retention là gì?
- Có thể xóa một record riêng khỏi immutable backup không?
- Nếu restore backup, những yêu cầu xóa gần đây có được áp dụng lại không?
- Key đã bị destroy/revoked thì backup còn giải mã được không?
- Legal hold có yêu cầu giữ một số records không?

**Xóa theo lịch backup expiration** có thể là cách xử lý hợp lệ trong một số chính sách, nhưng phải được diễn đạt rõ về thời gian và giới hạn. Không hứa “xóa ngay khỏi mọi backup” nếu hạ tầng không hỗ trợ.

## 39. Restore backup có thể làm dữ liệu đã xóa xuất hiện trở lại

Một kịch bản:

```text
Day 1: user requests deletion
Day 2: primary payload purged
Day 3: incident -> restore backup from Day 0
Day 3: deleted payload appears again in restored DB
```

Để tránh:

1. Giữ deletion requests/tombstones hoặc event log ở nguồn có khả năng tồn tại qua restore.
2. Khi restore, **replay deletion decisions** trước khi đưa dữ liệu vào hoạt động.
3. Kiểm tra restored backup không đưa payload expired vào mail worker gửi lại.
4. Phân biệt backup phục hồi kỹ thuật với khôi phục quyền sử dụng dữ liệu.
5. Có runbook/kiểm thử restore kết hợp retention.

Nếu sử dụng cryptographic erasure bằng key destruction, cần chắc chắn key material không được restore từ một backup khác rồi làm dữ liệu đọc lại được. Một bản backup encrypted không mặc định tuân thủ deletion policy nếu key quản lý sai.

## 40. Logs có thể là nơi rò rỉ lớn nhất

Một dòng log:

```java
log.error("Failed to send mail: {}", mimeMessage, exception);
```

hoặc:

```java
mimeMessage.writeTo(System.out);
```

có thể lưu body, headers, To/Cc/Bcc, token, filename và attachment ở dạng không phù hợp với chính sách. Log có thể được chuyển đến nhiều hệ thống APM/SIEM, có thời gian giữ lâu hơn database outbox.

### Nguyên tắc logging

- Không log raw `MimeMessage`, `SimpleMailMessage` hay toàn bộ Integration Message.
- Không log payload template model hoặc `Map.toString()` chứa PII.
- Không log `JavaMailSenderImpl` debug session của production nếu không có quy trình kiểm soát đặc biệt.
- Không đưa raw exception message chưa sanitize vào metric labels.
- Không log body lỗi HTTP/webhook nếu body có thể chứa recipient/content.
- Không gửi attachment qua tracing hoặc crash reports.
- Dùng opaque IDs và error categories đã chuẩn hóa.

Ví dụ metadata log:

```text
event=mail_submission_failed
notificationId=6b7f-opaque
attemptId=23e1-opaque
providerRoute=transactional-primary
failureCategory=SMTP_TEMPORARY
smtpReplyClass=4xx
containsAttachment=true
payloadRetentionState=ENCRYPTED
```

Ngay cả IDs cũng cần giới hạn quyền truy cập nếu có thể liên kết ngược tới một user.

## 41. JavaMail debug và SMTP protocol logging

Jakarta Mail có khả năng bật debug session để xem quá trình kết nối/trao đổi SMTP. Điều đó hữu ích trong môi trường test nhưng có rủi ro ở production.

```java
JavaMailSenderImpl sender = new JavaMailSenderImpl();
Properties props = sender.getJavaMailProperties();

// Không bật production nếu chưa có quy trình kiểm soát:
props.put("mail.debug", "true");
```

Tùy implementation và mức debug, log có thể chứa các lệnh SMTP, địa chỉ người nhận, thông tin xác thực được che hoặc không che như mong đợi, và metadata khác. Không tin rằng mọi phiên bản library đều tự redact đầy đủ credential và PII.

**Cách tiếp cận an toàn hơn**:

1. Bật debug chỉ với SMTP test server và dữ liệu giả.
2. Khi điều tra production, ưu tiên thống kê reply codes, timing và correlation IDs.
3. Nếu cần protocol trace, giới hạn người truy cập, thời hạn, môi trường và phương thức thu thập.
4. Thu hồi/debug off sau điều tra; kiểm tra hệ thống log tập trung có giữ bản copy không.
5. Không bật debug bằng cấu hình global cho toàn bộ production traffic nhiều ngày.

## 42. Exceptions và stack traces cũng có thể mang PII

`MailSendException` hoặc nested `MessagingException` có thể chứa:

- Recipient address bị lỗi.
- SMTP reply message từ server.
- Host, route hoặc account metadata.
- Exception mô tả payload/attachment nếu code custom nhúng vào.

Một interceptor ghi toàn bộ exception theo mặc định có thể chuyển PII sang SIEM.

### Thay đổi cách phân loại lỗi

```java
public enum MailFailureCategory {
    PREPARATION,
    AUTHENTICATION,
    CONNECTION,
    RECIPIENT_REJECTED,
    MESSAGE_REJECTED,
    TIMEOUT_UNKNOWN,
    PROVIDER_RATE_LIMIT,
    STORAGE_UNAVAILABLE,
    UNCLASSIFIED
}
```

Lưu enum, giai đoạn giao thức và correlation ID; với diagnostic chi tiết, dùng một kênh bảo mật có TTL riêng. Không cần giữ nguyên `ex.getMessage()` trong bản ghi notification để hỗ trợ dashboard.

### Tránh lưu exception object vào queue

Không serialize `Throwable`, `MimeMessage` hoặc `ErrorMessage` đầy đủ vào dead-letter queue nếu nó có thể chứa payload nhạy cảm. Một DLQ record nên mang ID, loại lỗi và tham chiếu đến trạng thái được quản lý, với ACL và retention tương ứng.

## 43. Tracing và APM: không gắn dữ liệu nhạy cảm vào span

Ví dụ không nên:

```java
span.setAttribute("mail.recipient", customerEmail);
span.setAttribute("mail.body", html);
span.setAttribute("mail.reset_token", token);
```

Tốt hơn:

```java
span.setAttribute("mail.type", "transactional");
span.setAttribute("mail.provider_route", approvedRoute);
span.setAttribute("mail.has_attachment", true);
span.setAttribute("mail.outcome", "SUBMITTED");
```

Các giá trị như `approvedRoute` cần được kiểm soát từ allowlist, không lấy tùy ý từ user input.

Đừng dùng subject, filename, recipient email hoặc hash email không đánh giá rủi ro làm span name/metric label. Dữ liệu tracing thường được xuất sang hệ thống khác và có chính sách retention khác với database nghiệp vụ.

## 44. Metrics nên đếm trạng thái, không giữ nội dung

Ví dụ các metric vận hành:

| Metric | Mục đích |
| --- | --- |
| `mail.payload.encrypted_total` | Số payload được mã hóa lưu |
| `mail.payload.decrypt_failures_total` | Lỗi decrypt/KMS/tag mismatch |
| `mail.payload.purge_eligible` | Số payload đủ hạn cleanup |
| `mail.payload.purge_attempt_total` | Số lần cleanup thử |
| `mail.payload.purge_failure_total` | Lỗi cleanup theo loại |
| `mail.payload.oldest_expired_age_seconds` | Tuổi của payload hết hạn nhưng còn giữ |
| `mail.temp_files_bytes` | Dung lượng file tạm chưa xóa |
| `mail.outbox.pending` | Số công việc cần dữ liệu để gửi |
| `mail.smtp.unknown_total` | Số attempts outcome mơ hồ |
| `mail.raw_mime_logging_incidents_total` | Sự cố kiểm soát thông tin nếu theo dõi |

Tên metric là ví dụ do ứng dụng định nghĩa. Không đưa raw payload ID, email, token, attachment filename hoặc ciphertext vào metric label. Để điều tra một notification cụ thể, dùng log có quyền tương ứng thay vì time-series có cardinality cao.

## 45. Audit log không phải archive toàn bộ body

Một audit record đủ hữu ích:

```text
notificationId
createdAt
messageClass
templateVersion
recipientRef
submissionAttemptId
status
providerRoute
payloadPurgedAt
deletionPolicyVersion
```

Không cần mặc định lưu:

```text
htmlBody
plainText
rawMime
attachmentBytes
resetToken
smtpPassword
```

Nếu pháp lý/nghiệp vụ yêu cầu lưu chính xác email đã gửi, hãy có **compliant archive** riêng: mã hóa, audit truy cập, retention, legal hold, backup và deletion policy. Đừng dựa vào application log để làm evidence archive.

### Audit truy cập giải mã

Một số hệ thống cần audit:

- Ai/service nào đã gọi decrypt?
- Mục đích nghiệp vụ/notification ID?
- Khi nào và ở môi trường nào?
- KMS key scope nào?
- Kết quả thành công/thất bại?

Audit không nên ghi plaintext hoặc data key. Việc audit truy cập có thể giúp phát hiện một service đọc hàng loạt encrypted payload bất thường.

## 46. SMTP provider là một data processor độc lập

Khi gửi:

```text
Spring app -> SMTP relay -> recipient provider
```

relay/provider có thể giữ message, routing metadata, bounce logs hoặc bản sao theo chính sách riêng. Kể cả khi ứng dụng xóa outbox ngay sau `SUBMITTED`, provider vẫn có thể giữ dữ liệu.

Cần tìm hiểu từ hợp đồng và tài liệu provider:

- Provider có lưu full body/attachment không?
- Logs có chứa recipient/content không?
- Retention mặc định và tùy chọn là gì?
- Có sandbox/test mode giữ dữ liệu khác production không?
- Data residency và subprocessors như thế nào?
- Provider có chức năng xóa message log hoặc request data không?
- Provider có thể khôi phục từ backup trong bao lâu?
- Ai có thể truy cập message event/history?

**Không tuyên bố rằng ứng dụng có thể xóa email khỏi provider sau khi submit nếu provider không có contract/API hỗ trợ.**

### Provider message ID vẫn có thể là dữ liệu cần bảo vệ

Một `providerMessageId` thường không chứa plaintext email, nhưng có thể liên kết với recipient/transaction qua provider dashboard. Hãy bảo vệ quyền tra cứu ID và không đưa nó vào public URL không cần thiết.

## 47. Delivery webhook không cần raw email

Provider feedback thường có:

```text
provider
providerMessageId
eventType = delivered / bounced / deferred
eventTime
recipient metadata
diagnostic text (có thể nhạy cảm)
```

Ứng dụng nên normalize thành:

```text
notificationId
attemptId
recipientId
canonicalEventType
occurredAt
failureCategory
eventDedupeKey
```

Nếu cần giữ raw webhook body để điều tra chữ ký hoặc mapping, phải có retention và quyền riêng. Raw diagnostic có thể chứa địa chỉ recipient, phản hồi mailbox và thông tin khác; không tự lưu vô hạn.

### Không dùng thiếu feedback làm lý do giữ body

Nếu SMTP đã submit và provider không gửi delivered event, việc giữ raw email body thêm một năm **không tạo ra feedback bị thiếu**. Có thể giữ provider correlation ID và làm reconciliation theo API/provider logs trong cửa sổ hỗ trợ; sau đó đánh dấu `UNOBSERVED` thay vì kéo dài retention toàn body.

## 48. End-to-end encryption: S/MIME và OpenPGP

Nếu ứng dụng thực sự cần bảo vệ nội dung email khỏi mail providers ở giữa, có thể cân nhắc các chuẩn như:

- **S/MIME:** mã hóa/ký email bằng chứng chỉ và khóa công khai/riêng.
- **OpenPGP (PGP/MIME):** mã hóa/ký payload theo khóa của người nhận.

Mô hình khái niệm:

```text
Spring app
   |
   +-- Build MIME content
   +-- Encrypt for recipient public key
   |
   v
Encrypted MIME body
   |
   v
SMTP providers cannot ordinarily read protected body
   |
   v
Recipient client decrypts with private key
```

**Đây là E2E content encryption**, không giống mã hóa outbox trong database hoặc STARTTLS. Nhưng nó có nhiều hạn chế:

- Cần có public key/certificate tin cậy của recipient.
- Phải quản lý key rotation, revoke và khả năng mở thư cũ.
- Một số mail clients hỗ trợ không đầy đủ hoặc UX phức tạp.
- Email headers như To, From, Subject có thể vẫn lộ hoặc cần cơ chế bảo vệ riêng; chuẩn và implementation quyết định.
- Sender/recipient endpoints vẫn có thể thấy plaintext.
- Nếu private key bị mất, người nhận có thể không giải mã được.
- Malware, phishing hoặc việc forward nội dung đã decrypt không được E2E ngăn hoàn toàn.

Không tự mã hóa HTML thành một chuỗi Base64 rồi ghi “encrypted”. Nếu triển khai S/MIME/PGP, dùng thư viện đã được kiểm toán/bảo trì, quản lý khóa riêng và test tương thích client.

## 49. Mã hóa outbox không có nghĩa provider không thấy nội dung

Giả sử:

```text
Encrypted outbox
      |
      v
Worker decrypts
      |
      v
MimeMessageHelper.setText(plaintext)
      |
      v
SMTP provider receives ordinary email
```

Lúc gửi, provider có thể thấy nội dung nếu email không được mã hóa end-to-end. Mã hóa outbox nhằm giảm rủi ro **trước và sau submission trong hệ thống của ứng dụng**, không làm cho một email MIME thông thường trở thành E2E encrypted.

Đây là ranh giới bảo mật cần giải thích rõ khi đánh giá tuân thủ hoặc thông báo quyền riêng tư cho người dùng.

## 50. Một link tải tài liệu có thể dễ thu hồi hơn attachment

Một email nhạy cảm có thể chỉ chứa:

```text
Bạn có tài liệu mới.
Đăng nhập tại https://portal.example.org/documents
để xem tài liệu.
```

Lợi ích:

- Email không chứa toàn bộ tài liệu.
- Có thể thu hồi quyền truy cập tại portal.
- Có thể yêu cầu MFA/re-authentication.
- Có audit ai đã tải tài liệu.
- Có TTL, quota và chính sách DLP.

Nhược điểm:

- Người nhận phải đăng nhập và có mạng.
- Link/portal có thể bị phishing spoofing.
- Metadata trong email vẫn có thể nhạy cảm.
- Tài liệu đã tải xuống máy người nhận vẫn không thể thu hồi hoàn toàn.

Một **signed URL** là bearer capability; ai có URL còn hiệu lực có thể sử dụng nó nếu không có lớp xác thực khác. Không gửi signed URL sống nhiều tháng qua email rồi kỳ vọng nó an toàn như portal có session/MFA.

## 51. Không dùng attachment “mã hóa ZIP bằng password gửi cùng email”

Một kiểu xử lý thường gặp:

```text
Email body: "Mật khẩu ZIP là ABC123"
Attachment: secret.zip
```

Nếu password và attachment nằm cùng một email, người đọc được email thường có cả hai. Cách này không tăng bảo vệ đáng kể trước việc truy cập trái phép mailbox.

Ngay cả khi password được gửi qua kênh khác, cần kiểm tra:

- Thuật toán encryption của ZIP và công cụ hỗ trợ.
- Entropy và policy của password.
- Kênh phân phối password độc lập.
- Khả năng password bị lưu/log.
- Thời hạn lưu ciphertext và key.
- UX của người nhận.

Với dữ liệu có yêu cầu bảo vệ cao, thường nên chọn portal có auth/authorization hoặc chuẩn E2E được hỗ trợ thay vì tự xây phương thức mã hóa attachment ad hoc.

## 52. Không gửi secret mà ứng dụng không cần tiết lộ

Các trường nên bị loại khỏi template model nếu không cần:

```text
password hash
API key
JWT refresh token
database credential
complete payment card data
internal session cookie
long-lived signed URL
unredacted identity document
```

Trong email reset password, chỉ gửi một **one-time link** có policy an toàn, không gửi mật khẩu hiện tại và không đính kèm session secrets.

Đối với số thẻ thanh toán hoặc dữ liệu nhận dạng rất nhạy, cần xem xét kênh email có phù hợp với mục đích và quy định hay không trước khi hỏi “mã hóa ở đâu”.

## 53. Header email cũng có thể tiết lộ dữ liệu

Ngay cả khi body đã mã hóa hoặc không lưu, một message vẫn có:

```text
From
To / Cc
Subject
Reply-To
Message-ID
Date
Received
Content-Type
```

Đặc biệt:

- Subject có thể hiện trong notifications trên màn hình khóa.
- To/Cc công khai danh sách recipient theo semantics email.
- Bcc cần được xử lý đúng ở envelope/header.
- Custom headers có thể vô tình chứa IDs nhạy cảm.
- Message-ID và Received headers cung cấp metadata tracing.

Không đặt số định danh nhạy cảm, OTP hoặc thông tin khám bệnh trực tiếp vào Subject. Nếu cần correlation nội bộ, dùng opaque IDs có TTL/permissions hợp lý, không dùng những giá trị giúp người ngoài truy cập dữ liệu.

## 54. Gửi sai người không thể được khắc phục chỉ bằng purge

Một email chứa tài liệu nhạy cảm gửi nhầm recipient là một **sự cố phân quyền và tiết lộ thông tin**, không phải chỉ là vấn đề cleanup database.

Các biện pháp phòng ngừa:

1. Validate recipient eligibility tại thời điểm gửi, không chỉ lúc schedule.
2. Ràng buộc tenant, notification và attachment owner.
3. Kiểm tra template/model data thuộc đúng recipient.
4. Tránh reuse mutable `MimeMessage` giữa nhiều users.
5. Với Bcc, test SMTP envelope và MIME headers.
6. Sử dụng provider test/sandbox thay vì địa chỉ thật khi QA.
7. Cân nhắc portal access thay attachment nếu dữ liệu cực nhạy.
8. Có quy trình incident response nếu xảy ra misdelivery.

Sau khi email đã tới mailbox người khác, ứng dụng thường không thể buộc người ấy xóa tất cả bản sao. Điều này khiến **pre-send authorization** còn quan trọng hơn việc xóa bản ghi sau gửi.

## 55. Sự khác nhau giữa encryption, redaction, pseudonymization và deletion

| Biện pháp | Ví dụ | Có thể khôi phục nội dung? | Mục đích |
| --- | --- | --- | --- |
| Encryption | AES-GCM ciphertext + KMS key | Có, với key và quyền | Bảo vệ tính bí mật khi lưu/truyền theo lớp |
| Redaction | Đổi email thành `j***@example.net` trong log | Không từ bản đã redact, nhưng còn bản nguồn | Giảm lộ thông tin trong observability |
| Pseudonymization | Thay email bằng recipient ID | Có thể liên kết qua mapping | Giảm sự hiện diện của direct identifier |
| Irreversible deletion | Xóa plaintext và ciphertext cùng khả năng decrypt | Không, nếu mọi bản/key đã xử lý | Giảm/loại bỏ dữ liệu lưu |
| Retention expiry | Đánh dấu đã đến hạn cleanup | Dữ liệu vẫn có thể còn | Tín hiệu để kích hoạt xóa |

**Pseudonymization không giống anonymization** nếu hệ thống vẫn có mapping hoặc đủ dữ liệu để xác định người dùng. Redaction log cũng không xóa nguồn gốc nhạy cảm khỏi database/backup.

## 56. Quyền truy cập: chỉ mail worker nên được decrypt khi cần

Một ứng dụng có các thành phần:

```text
Web/API service
Outbox dispatcher
Mail renderer + sender
Reporting dashboard
Cleanup worker
Security audit service
```

Không phải component nào cũng cần quyền decrypt full email model. Một thiết kế:

| Thành phần | Quyền cần thiết |
| --- | --- |
| API tạo notification | Ghi encrypted payload reference, tạo request |
| Outbox dispatcher | Đọc status/IDs, claim và enqueue |
| Mail renderer/sender | Decrypt đúng payload của notification được claim |
| Reporting dashboard | Đọc aggregate metrics/status, không đọc body |
| Cleanup worker | Xóa payload/object/key theo scope, không nhất thiết decrypt |
| Audit service | Đọc event metadata, không đọc raw content |

Phân quyền cần được thực thi bằng IAM/KMS/DB grants/network access, không chỉ dựa trên code convention.

### Tách worker khỏi dashboard

Nếu dashboard API dùng cùng một database credential/KMS permission như mail sender, một lỗ hổng ở dashboard có thể cho phép đọc toàn bộ payload. Tách service identity và quyền decrypt giúp giảm phạm vi rủi ro.

Khi nhiều tenants cùng dùng chung worker, authorization còn phải ràng buộc `tenantId` với notification/outbox và KMS encryption context. Không dùng ID từ untrusted HTTP request để tùy ý decrypt payload của tenant khác.

## 57. Tách encryption context theo tenant và notification

Một key context có thể gồm:

```text
tenant_id
notification_id
payload_type
format_version
```

Nếu KMS hỗ trợ encryption context trong envelope flow, có thể ràng buộc context đó với dữ liệu đang wrap/unwrap. Đồng thời AES-GCM AAD có thể ràng buộc ciphertext với logical record.

**Đừng dùng encryption context như authentication duy nhất.** Ứng dụng vẫn cần kiểm tra quyền đọc record, tenant ownership và business role trước khi gọi KMS.

Nếu context thay đổi do migrate tenant/sửa notification ID, dữ liệu có thể không decrypt được nếu không có quy trình re-encrypt/rewrap. Lưu context version và metadata chính xác giúp tránh “mất khóa” logic trong migration.

## 58. Một service gửi email với vùng plaintext tồn tại ngắn

Ví dụ khung code:

```java
import java.util.Arrays;
import java.util.UUID;

public final class ProtectedMailWorker {

    private final EncryptedPayloadReader payloadReader;
    private final MailTemplateRenderer renderer;
    private final MailSubmitter submitter;

    public ProtectedMailWorker(
            EncryptedPayloadReader payloadReader,
            MailTemplateRenderer renderer,
            MailSubmitter submitter
    ) {
        this.payloadReader = payloadReader;
        this.renderer = renderer;
        this.submitter = submitter;
    }

    public void process(UUID notificationId) throws Exception {
        byte[] plaintextModel =
                payloadReader.decryptForClaimedNotification(
                        notificationId);

        try {
            RenderedMail mail =
                    renderer.render(plaintextModel);

            // submitter owns a distinct attempt record and
            // classifies SMTP result: SUBMITTED/FAILED/UNKNOWN.
            submitter.submit(notificationId, mail);
        } finally {
            Arrays.fill(plaintextModel, (byte) 0);
        }
    }
}
```

`EncryptedPayloadReader`, `MailTemplateRenderer`, `MailSubmitter` và `RenderedMail` là những abstractions do ứng dụng thiết kế. Đoạn code cho thấy cách giới hạn scope của byte[] đã decrypt; nó **không bảo đảm zeroization toàn heap**, vì renderer có thể tạo `String`/MIME copies. Cần tránh giữ `RenderedMail` trong cache hoặc logging interceptor.

Trên hệ thống thực, cần lưu một submission attempt bền vững trước SMTP I/O và ghi kết quả sau đó trong transaction riêng. Chỉ code trên không đảm bảo retry hoặc exactly-once.

## 59. Không giữ một DB transaction trong lúc decrypt, render và send

Anti-pattern:

```java
@Transactional
public void send(UUID id) {
    Notification n = repository.lockById(id);
    byte[] model = crypto.decrypt(n.payload());
    MimeMessage message = compose(model);
    sender.send(message);  // SMTP I/O trong transaction DB.
    n.markSubmitted();
}
```

Đây là vấn đề vì:

- SMTP send có thể mất nhiều giây hoặc timeout.
- Transaction/locks/connection bị giữ lâu.
- Database rollback không thể “thu hồi” email đã được provider chấp nhận.
- Crash sau SMTP accepted nhưng trước DB commit có thể làm notification bị gửi lại.
- Plaintext có thể tồn tại trong memory lâu hơn vì toàn method chờ I/O.

Nên tách:

```text
Transaction 1: claim notification + create attempt
              |
              v
Outside DB transaction:
  authorize decrypt -> render -> SMTP submit
              |
              v
Transaction 2: record attempt outcome
              |
              v
Cleanup worker: evaluate retention separately
```

Khi gửi nhiều recipients trong một `MimeMessage`, cũng cần đánh giá partial SMTP success trước khi retry, tránh vô tình gửi lại cho người đã được submit.

## 60. Đừng dùng email attachment để chuyển toàn bộ dữ liệu cá nhân

Một báo cáo có thể chỉ cần:

```text
Tổng doanh thu kỳ này: ...
Số đơn hàng: ...
Link đến portal quản trị đã xác thực
```

thay vì:

```text
Danh sách từng khách hàng + số điện thoại +
địa chỉ + lịch sử thanh toán dưới dạng PDF/CSV
```

Điều này giảm:

- Mức nhạy cảm của email đã phát ra ngoài.
- Dung lượng mã hóa/lưu/backup.
- Số attachment copies trong SMTP/mailboxes.
- Chi phí và độ phức tạp của retention/deletion.

Nếu người nhận thực sự cần dữ liệu chi tiết, có thể cấp quyền tải qua portal hoặc API với audit. **Không tự xóa những trường cần thiết cho nhiệm vụ hợp pháp**, mà nên quyết định fields tối thiểu cùng product/security stakeholders.

## 61. DLP và kiểm tra nội dung trước khi gửi

Một lớp kiểm tra trước SMTP có thể đánh giá:

- Có secret/credential bị đưa nhầm vào body không?
- Attachment có chứa thông tin vượt quyền người nhận không?
- Template có in dữ liệu customer của tenant khác không?
- File có đúng MIME type và kích thước theo policy?
- Recipient domain có được phép cho loại thông tin này không?
- Có thông tin được phân loại “portal only” nhưng đang gửi raw email không?

Một luồng:

```text
Render candidate message
      |
      v
Policy/DLP check
      |
      +-- Allowed --> SMTP send
      |
      +-- Blocked --> FAIL_CLOSED + safe audit
```

**Không log raw content bị DLP chặn** chỉ vì đó là nội dung “cần điều tra”. Có thể lưu reason code/category, fingerprint bảo mật với retention riêng hoặc một sample ở hệ kiểm soát được cấp quyền nếu quy trình thật sự yêu cầu.

Một DLP scanner có thể bỏ sót dữ liệu hoặc false-positive. Nó là một lớp hỗ trợ, không thay thế việc giới hạn dữ liệu ở business/template model.

## 62. Một yêu cầu xóa dữ liệu phải có phạm vi rõ ràng

Giả sử người dùng yêu cầu xóa dữ liệu liên quan email. Cần xác định:

1. Các notification nào thuộc người ấy?
2. Còn job scheduled/outbox pending nào có thể tạo lại nội dung?
3. Có encrypted payload và attachment/object versions nào?
4. Có event/webhook/projection chứa PII nào?
5. Có raw MIME/log/trace hoặc support ticket chứa copy không?
6. Backup/replication có quy trình retention nào?
7. Có legal hold hoặc nghĩa vụ lưu giữ hợp lệ không?
8. Có provider ngoài hệ thống đang giữ email/log không?

Không tuyên bố “đã xóa dữ liệu người dùng” chỉ vì một record `mail_notification` đã bị xóa nếu vẫn còn attachment và bản sao trong storage.

### Tạo data inventory từ đầu

Một bảng inventory nội bộ có thể gồm:

| Store | Data class | Owner | Retention | Deletion mechanism |
| --- | --- | --- | --- | --- |
| Outbox DB | Encrypted template model | Mail platform | Theo policy | Purge worker |
| Object storage | Encrypted attachment version | Document service | Theo policy | Lifecycle + explicit delete |
| Redis/cache | Render/temp metadata | Mail worker | Ngắn hạn | TTL + eviction |
| Logs | Status/diagnostic metadata | Platform ops | Theo policy | Log retention |
| APM traces | Technical spans | Observability | Theo policy | Export retention |
| Backup | Encrypted DB/object snapshots | Infrastructure | Theo backup policy | Expire/restore re-delete |
| External provider | Recipient/message feedback | Vendor account | Theo hợp đồng | Vendor controls/request |

Inventory là điều kiện để đánh giá xóa thực sự, không nhất thiết phải đưa danh sách này vào notification record.

## 63. Legal hold và yêu cầu lưu trữ bắt buộc

Một số loại tài liệu hoặc thông báo phải được giữ vì nghĩa vụ kế toán, hợp đồng, điều tra nội bộ hoặc yêu cầu pháp lý cụ thể. Điều này có thể xung đột với yêu cầu xóa ngay.

Một retention engine nên xử lý:

```text
Is content eligible for purge?
          |
          +-- No: still needed for processing/retry
          |
          +-- No: authorized legal hold / required retention
          |
          +-- Yes: schedule controlled deletion
```

**Không dùng legal hold như một cờ tùy tiện để giữ dữ liệu vô hạn.** Cần owner, căn cứ, phạm vi, thời hạn/review và quyền quản lý. Khi hold kết thúc, hệ thống phải đánh giá lại retention và xóa nếu không còn cơ sở giữ.

Quy định cụ thể khác nhau theo khu vực và loại dữ liệu; cần phối hợp với người phụ trách pháp lý/compliance, không suy ra một TTL thống nhất từ Spring Mail.

## 64. Xóa dữ liệu trước khi gửi: hủy notification pending

Nếu người dùng rút yêu cầu hoặc hết hạn OTP khi notification còn `PENDING`:

1. Cập nhật `status=CANCELED/EXPIRED` theo transaction.
2. Ngăn worker mới claim notification.
3. Xác định worker đang xử lý có cần dừng theo policy không.
4. Xóa hoặc làm vô hiệu hóa token đã tạo.
5. Purge encrypted payload sau khi không còn active lease/retention hold.
6. Ghi audit metadata tối thiểu.

Nếu job đã được claim và bắt đầu SMTP I/O, không thể coi database cancellation là bảo đảm email chưa đi ra ngoài. Phải có business state check ngay trước send và quy tắc xử lý in-flight attempts.

## 65. Xóa sau khi gửi: tránh hứa hẹn vượt quyền kiểm soát

Một API `deleteNotificationContent(notificationId)` có thể:

```text
Delete encrypted outbox payload
Delete local temp files
Delete object versions under app control
Prune archived MIME if retention allows
Scrub/cache eviction as supported
Schedule backup expiration/replay deletion
Keep minimal audit tombstone
```

Nó **không thể tự động**:

```text
Delete message from recipient mailbox
Delete forwarded copies
Delete screenshots/downloads
Delete a provider's backups without its cooperation
Guarantee zero RAM remanence on every JVM component
```

Khi trả kết quả cho API/user, nên phân biệt:

- `PURGED_FROM_APP_PRIMARY_STORES`.
- `ADDITIONAL_STORES_PENDING_RETENTION`.
- `EXTERNAL_EMAIL_ALREADY_SUBMITTED`.
- `BLOCKED_BY_AUTHORIZED_HOLD`.

Những tên là ví dụ, không phải status của Spring Mail. Mục tiêu là **trung thực về phạm vi và tiến độ**.

## 66. Mã hóa và xóa tại nhiều môi trường

Development, staging và production có thể khác nhau:

| Môi trường | Khuyến nghị |
| --- | --- |
| Local development | Synthetic recipients/payload, SMTP capture server |
| CI | Không có production secrets, fake KMS/test keys |
| Staging | KMS/test resources riêng, không copy raw production PII |
| Production | Least privilege, encryption, retention, audit và monitoring |
| Disaster recovery | Restore test với key management + deletion replay |

Một lỗi phổ biến là copy database production sang staging “để test gửi mail”, rồi staging tự submit các notification cũ tới người thật hoặc giữ raw payload ở môi trường ít bảo vệ hơn.

Nếu cần dữ liệu representative để benchmark, dùng synthetic/đã được xử lý theo chuẩn phù hợp, đồng thời vô hiệu hóa đường gửi email thật. Khi restore database, nên mặc định **khóa mail submission** cho tới khi các flags và deletion records được reconcile.

## 67. Test 1: encrypted storage không chứa plaintext

Một test cơ bản:

1. Tạo payload synthetic có một marker rõ, ví dụ `"TEST-SECRET-436"`.
2. Mã hóa và lưu qua repository test.
3. Đọc raw row/object bytes từ store.
4. Xác nhận plaintext marker không xuất hiện dưới dạng trực tiếp.
5. Giải mã bằng key được cấp quyền và AAD đúng.
6. Xác nhận dữ liệu trùng fixture ban đầu.

Ví dụ JUnit dùng AES-GCM:

```java
import org.junit.jupiter.api.Test;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import static org.junit.jupiter.api.Assertions.*;

@Test
void encryptThenDecryptWithCorrectContext() throws Exception {
    KeyGenerator generator = KeyGenerator.getInstance("AES");
    generator.init(256);
    SecretKey key = generator.generateKey();

    byte[] plaintext =
            "TEST-SECRET-436".getBytes(StandardCharsets.UTF_8);
    byte[] aad =
            "tenant-1/notification-1/model-v1"
                    .getBytes(StandardCharsets.UTF_8);

    var sealed = PayloadAesGcm.encrypt(
            key, plaintext, aad
    );

    assertFalse(
            java.util.Arrays.equals(
                    plaintext,
                    sealed.ciphertextAndTag()
            )
    );

    byte[] restored = PayloadAesGcm.decrypt(
            key, sealed, aad
    );

    assertArrayEquals(plaintext, restored);
}
```

Test `ciphertext != plaintext` chỉ là một assertion cơ bản, **không đủ để chứng minh storage mã hóa an toàn**. Cần dùng thuật toán được thẩm định, secret handling, key management và kiểm thử security controls ở tầng liên quan.

## 68. Test 2: đổi ciphertext hoặc AAD phải bị từ chối

GCM authentication tag phải phát hiện dữ liệu bị sửa:

```java
@Test
void rejectsTamperedCiphertext() throws Exception {
    SecretKey key = newAesKeyForTest();
    byte[] aad = "notification-1".getBytes(UTF_8);

    var sealed = PayloadAesGcm.encrypt(
            key, "synthetic".getBytes(UTF_8), aad
    );

    byte[] corrupted = sealed.ciphertextAndTag();
    corrupted[0] ^= 0x01;

    var tampered = new PayloadAesGcm.SealedPayload(
            sealed.formatVersion(),
            sealed.iv(),
            corrupted
    );

    assertThrows(
            javax.crypto.AEADBadTagException.class,
            () -> PayloadAesGcm.decrypt(key, tampered, aad)
    );
}
```

`newAesKeyForTest()` và `UTF_8` là helper/import trong test class; ví dụ nhấn mạnh hành vi chứ không tạo một test class standalone đầy đủ.

Một test tương tự thay đổi `aad` (ví dụ notification ID khác) cũng phải fail. Ứng dụng **không được fallback trả ciphertext dưới dạng plaintext** hoặc bỏ qua tag validation.

## 69. Test 3: quyền KMS và tenant isolation

Trong integration test với KMS sandbox hoặc mock kiểm soát policy:

1. Mail worker thuộc tenant A được phép decrypt payload A.
2. Worker hoặc API không thuộc tenant A **không được** decrypt payload A.
3. Dashboard principal chỉ có quyền đọc status, không có quyền KMS decrypt.
4. Cleanup principal có quyền xóa đúng object/version nhưng không cần quyền decrypt toàn bộ body.
5. Một encryption context bị sửa phải bị từ chối theo contract.
6. Khi key rotated, payload cũ vẫn đọc được nếu policy yêu cầu.
7. Khi key bị thu hồi, worker xử lý lỗi theo status, không tự gửi email thiếu nội dung.

Không kết luận security đã hoàn chỉnh chỉ vì unit test dùng mock trả `AccessDenied`. Cần kiểm tra IAM/KMS policies thực tế ở staging hoặc môi trường được phép, nhất là khi dùng nhiều service accounts và cross-account.

## 70. Test 4: xóa không làm mất notification còn cần retry

Kịch bản:

```text
N1: PENDING      -> encrypted payload present
N2: RETRY_WAIT   -> encrypted payload present
N3: SUBMITTED    -> retention deadline expired
N4: UNKNOWN      -> reconciliation policy active
N5: FAILED       -> retention deadline expired
```

Chạy cleanup worker với một `Clock` cố định:

- N1 không bị purge vì còn pending.
- N2 được giữ đến khi hết retry policy.
- N3 được purge nếu không có legal hold, active reference hoặc yêu cầu archive.
- N4 được giữ/đánh dấu xử lý theo policy cho `UNKNOWN`, không xóa tự động chỉ vì SMTP method ném exception.
- N5 được purge nếu không còn purpose hoặc hold.

**Retention tests phải assert vào storage target**, không chỉ một cờ `deleted=true` trên entity. Nếu file/object vẫn đọc được thì cleanup chưa đạt mục tiêu.

## 71. Test 5: cleanup idempotency sau crash

Một cleanup flow có thể crash ở các thời điểm:

```text
A: claim deletion
B: delete object version
C: delete encrypted data key/reference
D: delete database ciphertext
E: mark completion/audit
```

Test giả lập crash sau B rồi chạy lại:

1. Cleanup biết target version đã được yêu cầu xóa.
2. “Object not found” được phân loại chính xác theo API/cause.
3. Các bước C/D/E tiếp tục hoặc reconcile an toàn.
4. Không xóa nhầm object/version mới.
5. Không ghi rằng đã hoàn tất các bước chưa được xác nhận.
6. Có metric/alert nếu cleanup bị kẹt quá hạn.

Đây là **mẫu workflow idempotent**, không phải một transaction ACID trên cả database, object storage và KMS.

## 72. Test 6: cleanup và SMTP đang xử lý đồng thời

Một test concurrency:

```text
Mail worker A: starts reading attachment
Cleanup worker B: sees expires_at reached
Mail worker A: needs resource for MIME serialization
```

Kiểm tra:

- Nếu policy cho phép attempt tiếp tục, cleanup phải tôn trọng active lease/reference và không xóa nguồn sớm.
- Nếu policy yêu cầu hủy ngay khi hết hạn, worker phải nhận tín hiệu cancel và không gửi nội dung đã hết hiệu lực, trong phạm vi có thể kiểm soát.
- Nếu email đã qua SMTP acceptance, cancellation chỉ áp dụng các bản chưa submit/retention còn kiểm soát.
- Sau khi work kết thúc, cleanup có thể được kích hoạt lại.

Dùng `CountDownLatch`, transaction barriers hoặc test helper kiểm soát timing thay vì `Thread.sleep(...)` tùy tiện. Điều quan trọng là kiểm tra **thứ tự state** và storage availability dưới race.

## 73. Test 7: không log plaintext trong happy path và failure path

Fixture nên chứa một marker synthetic:

```text
TEST-ONLY-SECRET-DO-NOT-LOG-436
```

Test luồng:

1. Mã hóa và lưu payload synthetic.
2. Render và submit tới SMTP test server.
3. Buộc sender ném lỗi kết nối/auth/RCPT theo scenario.
4. Capture logs/traces được tạo bởi application components trong môi trường test.
5. Đảm bảo marker không xuất hiện trong application logs/exception serialization.
6. Kiểm tra structured event chỉ có ID/category được phép.

Không dùng marker này để khẳng định **toàn bộ** production logging an toàn. Cần thêm review cấu hình thư viện, APM agent, SMTP debug, framework exception handler và log routing.

**Không capture raw MIME của người dùng thật** trong test; SMTP test server phải chỉ nhận dữ liệu fixture giả.

## 74. Test 8: backup restore và replay deletion

Một integration/disaster-recovery exercise:

```text
T0 Backup DB contains encrypted payload P
T1 Delete request for P recorded
T2 Primary DB purges P
T3 Restore backup from T0 into isolated DR test
T4 Replay authoritative deletion ledger
T5 Confirm P inaccessible before mail workers enabled
```

Điều cần xác minh:

- Deletion ledger không bị mất cùng bản backup phục hồi.
- Tất cả storage targets được cập nhật đúng.
- Mail submission bị **tắt** trong DR restore cho tới khi reconciliation hoàn tất.
- Nếu ciphertext còn trong snapshot, có encryption/ACL và key policies phù hợp.
- Audit không tiết lộ body/token.

Không thử nghiệm restore backup production chứa PII vào một môi trường không được cấp quyền hoặc kém bảo vệ hơn.

## 75. Test 9: provider không tự xóa sau khi app purge

Trong integration test dùng SMTP sandbox:

1. Application submit một email synthetic có marker.
2. Application purge encrypted payload và temp files.
3. SMTP sandbox vẫn có thể giữ bản message đã nhận.
4. Test xác nhận giới hạn đó được ghi trong tài liệu/policy.

Test này giúp đội ngũ không lầm rằng “đã xóa ở ứng dụng” nghĩa là email không còn tồn tại ngoài hệ thống.

Nếu provider có API xóa logs/suppress message, nên có test theo contract cụ thể và phân biệt **xóa log provider** với **thu hồi email đã giao tới recipient mailbox**.

## 76. Test 10: retention theo loại email

Một test policy table-driven:

| Loại nội dung | Trạng thái | Kết quả kỳ vọng |
| --- | --- | --- |
| OTP đã hết hạn | `PENDING` | Không gửi, thu hồi token, purge theo policy |
| Hóa đơn cần retry | `RETRY_WAIT` | Giữ encrypted source tới retry expiry |
| Marketing email bị opt-out trước send | `PENDING` | Cancel, không gửi, purge source phù hợp |
| Email đã submitted | `SUBMITTED` | Xóa render/temp, giữ tối thiểu audit |
| Attempt chưa rõ | `UNKNOWN` | Reconcile hoặc giữ source ngắn theo policy |
| Record dưới legal hold | Terminal | Không purge trái hold; review expiry |

Không hard-code thời hạn ngay trong test mà không có policy version/config. Có thể dùng `Clock.fixed(...)` và fixture expiry times để test deterministic.

## 77. Test 11: payload bị copy sang notification khác

Tạo ciphertext cho notification A với AAD:

```text
tenant-A | notification-A | templateModel | v1
```

Sau đó thử decrypt cùng bytes bằng context notification B. Với AES-GCM AAD đúng, authentication phải thất bại.

Test này giúp phát hiện lỗi correlation/swap ciphertext giữa records. Nhưng nó **không thay thế authorization checks**; application vẫn phải kiểm tra người gọi được phép truy cập A hay B trước khi cố decrypt.

## 78. Test 12: không gửi nhầm email khi payload hết hạn

Kịch bản:

```text
Reset token expires at 10:05
Mail worker delayed until 10:08
```

Kỳ vọng:

- Worker kiểm tra token/notification vẫn eligible.
- Nếu link hết hạn, không submit email chứa token vô dụng.
- Notification được đánh dấu `EXPIRED/CANCELED` theo policy.
- Dữ liệu token còn lưu tạm được purge.
- Một yêu cầu reset mới cần tạo token mới với state mới.

Không “gia hạn token” tự động bằng cách thay `expiresAt` trong database mà không đánh giá security protocol; token issuance và reset verification cần một mô hình bảo mật thống nhất.

## 79. Test 13: attachment không còn sau cleanup

Một test với file/object synthetic:

1. Worker dùng immutable attachment object để gửi.
2. SMTP test server xác nhận đã đọc đúng attachment bytes.
3. Đánh dấu notification đạt retention deadline.
4. Cleanup xóa đúng object version và metadata key.
5. Kiểm tra API storage không còn trả attachment theo permission tương ứng.
6. Kiểm tra phiên bản mới của object cùng tên (nếu có) không bị xóa nhầm.

Không dùng `Files.exists(path)==false` làm bằng chứng rằng mọi bản backup/snapshot và storage replica cũng không còn. Kiểm chứng chỉ áp dụng **phạm vi storage target đang test**.

## 80. Một test matrix bảo mật và độ tin cậy

| ID | Scenario | Lớp bảo vệ | Kết quả cần quan sát |
| --- | --- | --- | --- |
| S01 | Encrypted payload store | At rest | Không có plaintext trực tiếp ở row/blob |
| S02 | Ciphertext tamper | Integrity | Decrypt fail closed |
| S03 | AAD swapped notification | Context binding | Authentication tag failure |
| S04 | Unauthorized KMS principal | Access control | Denied decrypt |
| S05 | Retryable SMTP failure | Lifecycle | Encrypted source còn đủ để retry |
| S06 | SMTP outcome UNKNOWN | Reliability | Không purge/retry mù |
| S07 | Submitted + TTL expired | Retention | Cleanup được kích hoạt đúng |
| S08 | Cleanup crash midway | Idempotency | Resume không xóa nhầm |
| S09 | Active worker vs cleanup | Concurrency | Không xóa source ngoài policy |
| S10 | Application logs | Observability | Synthetic secret không xuất hiện |
| S11 | Backup restore | Recovery | Deletion replay trước khi mở workers |
| S12 | Provider SMTP acceptance | External boundary | App purge không bị gọi là mailbox deletion |
| S13 | Object versions | Storage semantics | Không còn version thuộc phạm vi xóa |
| S14 | Legal hold | Retention exception | Không xóa khi hold hợp lệ |
| S15 | Expired reset token | Security | Không gửi token hết hạn |
| S16 | Bcc recipient | Privacy | Envelope đúng, không log/lộ header |

Một suite có unit, integration và DR tests; không cần mọi test chạy ở mỗi commit. Nhưng những thay đổi về crypto format, retention worker và mail routing cần có test phù hợp trước deploy.

## 81. Runbook: phát hiện raw email trong log

Giả sử team phát hiện một dòng log chứa reset link có token:

```text
ERROR mail send failed:
  subject=Reset password
  body=https://example.org/reset?token=...
```

Cách xử lý:

**Bước 1 — Ngăn phát sinh thêm bản sao.**

- Xác định logger/interceptor/debug property.
- Dừng việc in raw MIME hoặc exception chứa payload.
- Không tạo thêm các dòng log chứa cùng token khi điều tra.

**Bước 2 — Phân loại phạm vi.**

- Những service/instance nào đã ghi?
- Log nằm ở local disk, stdout, APM, SIEM hay support ticket?
- Có ai đã được cấp quyền xem?
- Thời gian tồn tại và số bản sao là bao nhiêu?

**Bước 3 — Giảm tác động của bí mật còn hiệu lực.**

- Thu hồi/reset tokens hoặc credentials bị lộ nếu được phép và phù hợp giao thức.
- Không làm vô hiệu hóa account không cần thiết mà thiếu quy trình incident.
- Với dữ liệu không thể thu hồi, áp dụng incident response/compliance.

**Bước 4 — Cleanup theo khả năng từng hệ thống.**

- Dùng cơ chế xóa/redact log của nền tảng nếu được hỗ trợ.
- Kiểm tra retention/backup và bản sao đã export.
- Ghi audit kết quả; không hứa xóa mọi bản ngay lập tức.

**Bước 5 — Prevent recurrence.**

- Structured safe logging.
- Unit/integration tests dùng synthetic markers.
- Review code review checklist và default log configuration.

Không gửi nguyên log có token sang kênh chat/email khác khi yêu cầu hỗ trợ.

## 82. Runbook: payload đã quá hạn nhưng chưa xóa

Nếu metric `mail.payload.oldest_expired_age_seconds` tăng:

1. Xác định cleanup worker còn chạy không.
2. Kiểm tra storage/KMS API errors, permission và rate limit.
3. Kiểm tra active lease hoặc notification state đang chặn purge.
4. Kiểm tra có legal hold hợp lệ không.
5. Kiểm tra object version/delete marker/replication behavior.
6. Xem deletion retry state và số target còn pending.
7. Cân nhắc tăng batch size/concurrency có kiểm soát.
8. Ưu tiên records có mức độ nhạy cảm và thời gian quá hạn cao.
9. Ghi result categories và audit từng batch.
10. Không xóa cưỡng bức các payload đang thuộc attempt hợp lệ nếu chưa quyết định chính sách hủy.

Nếu nguyên nhân là cleanup job đã tắt trong nhiều tuần, cần làm backlog purge theo batches có giới hạn thay vì xóa toàn bộ trong một transaction lớn.

## 83. Runbook: nghi ngờ lộ khóa mã hóa

Một sự cố liên quan key/KMS principal phải được coi là vấn đề có phạm vi riêng:

- Xác định key version, alias, quyền decrypt và những payload bị ảnh hưởng.
- Thu hồi credentials/role bị lộ theo quy trình.
- Kiểm tra KMS audit logs và thời gian truy cập.
- Tạo key/version mới cho dữ liệu mới.
- Quyết định rewrap/re-encrypt dữ liệu còn cần giữ.
- Không xóa một key đang cần để decrypt những notifications hợp lệ nếu chưa có kế hoạch phục hồi.
- Đánh giá dữ liệu trong backup hoặc cache còn được truy cập không.
- Kiểm tra có plaintext bị export ra ngoài không.
- Theo dõi lỗi decrypt/queue backlog sau rotation.

**Rotation không tự thu hồi dữ liệu đã bị attacker đọc trước đó**. Tác động cần được đánh giá dựa trên bằng chứng truy cập và phạm vi dữ liệu.

## 84. Runbook: restore làm dữ liệu đã xóa xuất hiện lại

Khi DR restore:

1. Đưa hệ thống vào chế độ **không tự gửi email**.
2. Khôi phục database/storage theo kế hoạch đã phê duyệt.
3. Lấy deletion ledger/authoritative state từ nguồn phù hợp.
4. Replay những deletions/cancellations đã commit sau backup snapshot.
5. Kiểm tra record expired/held và các references còn sống.
6. Kiểm tra KMS key references và quyền decrypt.
7. Đối chiếu notification statuses; không resend old outbox bừa.
8. Chạy integrity/cleanup checks trước khi mở mail workers.
9. Ghi nhận phạm vi dữ liệu đã được khôi phục và xử lý lại.

Nếu deletion ledger cũng nằm trong cùng snapshot cũ và không có nguồn khác, khả năng replay có thể bị mất. Vì vậy, thiết kế DR phải tính dữ liệu xóa ngay từ đầu.

## 85. Runbook: mail gửi nhầm người với tài liệu nhạy cảm

Một incident không được giải quyết bằng `payloadStorage.delete(...)` đơn lẻ.

Các bước cần đánh giá:

- Xác định notification, recipient, attachment và thời điểm gửi.
- Kiểm tra sự cố là do dữ liệu upstream, header mapping, reuse mutable message hay tenant authorization.
- Ngăn những sends tương tự ngay lập tức nếu cần.
- Xác định mail provider đã chấp nhận và có delivery feedback không.
- Kích hoạt quy trình an ninh/pháp lý/tuân thủ thích hợp theo mức nhạy cảm.
- Nếu provider hỗ trợ các control liên quan, chỉ sử dụng theo contract; không hứa có thể thu hồi từ mailbox.
- Hạn chế thêm bản sao trong logs/tickets.
- Sửa validation, ownership check, tests và monitoring.

Không gửi email “xin lỗi” chứa lại toàn bộ dữ liệu nhạy cảm như một phần xử lý incident.

## 86. Checklist: trước khi đưa payload vào outbox

- [ ] Đã xác định các trường nhạy cảm và mục đích gửi.
- [ ] Đã bỏ các trường không cần thiết khỏi template model.
- [ ] Recipient/tenant ownership và eligibility được kiểm tra.
- [ ] Token có TTL, one-time use và quy tắc thu hồi.
- [ ] Template/key/version được ghi rõ khi cần tái dựng.
- [ ] Payload cần lưu được mã hóa ở lớp phù hợp.
- [ ] Data key không nằm trong source code/DB ở dạng plaintext.
- [ ] AAD/context binding được thiết kế đúng.
- [ ] Chỉ có một số services được phép decrypt.
- [ ] Không đẩy `MimeMessage`, raw HTML hoặc `byte[]` lớn vào queue không kiểm soát.
- [ ] Attachment reference trỏ tới object/version an toàn, không public.
- [ ] Có `expires_at` và retention policy version.

## 87. Checklist: khi worker dựng và gửi mail

- [ ] Chỉ decrypt sau khi claim/ủy quyền đã được xác nhận.
- [ ] Không giữ plaintext trong long-lived cache hoặc debug logs.
- [ ] Render HTML an toàn và không nhầm dữ liệu giữa tenants/recipients.
- [ ] MIME subject/headers không chứa bí mật không cần thiết.
- [ ] Bcc được xử lý theo privacy policy.
- [ ] SMTP TLS/certificate policy phù hợp provider.
- [ ] Không log SMTP raw DATA.
- [ ] File/stream attachment sống đủ lâu cho serialization.
- [ ] SMTP attempts được ghi bền vững và phân loại outcome.
- [ ] Không tự retry `UNKNOWN` mà không có policy.
- [ ] Không giữ DB transaction dài qua SMTP.
- [ ] Sau attempt, cleanup plaintext artifacts và lên lịch retention cho encrypted source.

## 88. Checklist: cleanup và deletion

- [ ] Có data inventory cho DB, object storage, cache, logs, backups và providers.
- [ ] Retention được định nghĩa theo loại dữ liệu/mục đích.
- [ ] Policy xử lý `PENDING/RETRY_WAIT/SUBMITTED/UNKNOWN` rõ ràng.
- [ ] Cleanup kiểm tra lease, active references và legal holds.
- [ ] Có unique/idempotent deletion request ID hoặc trạng thái tương đương.
- [ ] Storage deletes áp dụng cho đúng object version.
- [ ] Có xử lý versioning/replication/backup TTL.
- [ ] Có retry và alert cho cleanup failures.
- [ ] Có minimal tombstone/audit không chứa body.
- [ ] Restore runbook có replay deletion.
- [ ] Định nghĩa chính xác trạng thái “purged” theo phạm vi.
- [ ] Không hứa thu hồi email đã tới mailbox chỉ vì app xóa dữ liệu.

## 89. Checklist: quản lý khóa và môi trường

- [ ] Sử dụng thuật toán/mode hiện đại có kiểm chứng tính toàn vẹn.
- [ ] GCM nonce unique trong phạm vi key; không static/fixed IV.
- [ ] Có algorithm/key/schema version.
- [ ] KMS/HSM/secret manager được cấu hình và bảo vệ.
- [ ] IAM least privilege cho mail worker và cleanup worker.
- [ ] Có chính sách rotation/rewrap/re-encrypt/revocation.
- [ ] Có monitoring decrypt failures và KMS access anomalies.
- [ ] Secrets không in vào logs/config dumps.
- [ ] CI/staging dùng keys và synthetic payload riêng.
- [ ] Backup và DR bao gồm key availability/deletion considerations.
- [ ] Có incident runbook cho key compromise.

## 90. Checklist: kiểm thử và quan sát

- [ ] AES-GCM roundtrip và tag tampering fail-closed.
- [ ] AAD mismatch/cross-tenant access bị từ chối.
- [ ] Encrypted storage không chứa synthetic plaintext trực tiếp.
- [ ] Retention policy được test bằng `Clock.fixed(...)`.
- [ ] Cleanup idempotency sau crash được kiểm thử.
- [ ] Race giữa purge và active SMTP worker có test.
- [ ] Không rò synthetic secrets qua logs/traces trong failure path.
- [ ] Không gửi token/link hết hạn.
- [ ] Backup restore có reapply deletion state.
- [ ] Có metrics về expired backlog, purge failures và key errors.
- [ ] Không dùng recipient address/token làm metric labels.
- [ ] SMTP sandbox và test keys không truy cập production data.

## 91. Các sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm? | Cách thay thế |
| --- | --- | --- |
| “Đã bật TLS nên DB không cần bảo vệ” | TLS không bảo vệ DB dump | Encryption at rest + access control |
| “Đã mã hóa DB nên provider không đọc được” | Worker giải mã trước khi SMTP submit | E2E content encryption nếu thực sự cần |
| Lưu key cùng ciphertext trong một bảng không được bảo vệ | Lộ DB có thể lộ cả data và key | KMS/envelope encryption/least privilege |
| IV GCM cố định cho mọi message | Có thể phá bảo mật | Unique random nonce/key policy |
| Chỉ dùng Base64 để “encrypt” | Base64 đảo ngược công khai | Mã hóa chuẩn và quản lý key |
| Lưu nguyên template model không cần thiết | Tăng diện lộ PII | Data minimization |
| Lưu raw `MimeMessage` để dễ debug | Body/Bcc/token/attachment nằm trong logs | Structured safe diagnostic |
| Xóa payload trong `finally` dù send lỗi | Mất dữ liệu cần retry/reconcile | Lifecycle policy theo outcome |
| Chờ `DELIVERED` mới xóa body mãi mãi | Provider có thể không có event | Separate feedback coverage and retention |
| Xóa file sau `addAttachment` | Resource có thể chưa được đọc | Giữ tới serialization/attempt hoàn tất |
| Temp file không có sweeper | File tồn tại qua crash | Cleanup jobs + quota |
| Delete object key mà bỏ qua versions | Older versions còn tồn tại | Version-aware delete/lifecycle |
| Xóa primary DB rồi khẳng định mọi backup đã xóa | Snapshots còn bản cũ | Backup policy + restore replay |
| Lưu hash OTP rồi cố lấy hash gửi mail | Hash không đảo ngược được | Token issuance và encrypted transient delivery |
| Gửi ZIP password cùng email | Người lộ email có cả password | Separate channel/E2E/portal |
| Xóa message ở app rồi hứa thu hồi Inbox | Provider/mailbox ngoài quyền kiểm soát | Diễn đạt phạm vi chính xác |
| Dùng cùng KMS quyền cho dashboard và mail worker | Mở rộng blast radius | Separate service identities |
| Lưu email address dưới dạng metric label | PII + cardinality cao | Opaque ID/log có quyền |
| Không xét legal hold | Xóa dữ liệu bắt buộc giữ | Hold workflow có audit/expiry |
| Không replay deletion sau backup restore | Dữ liệu đã xóa xuất hiện lại | Restore runbook có deletion ledger |

## 92. Tình huống tự luyện 1 — Mail đặt lại mật khẩu

Một service tạo reset token, lưu token trong outbox payload plaintext rồi đặt lịch gửi sau 30 phút. Token hết hạn sau 15 phút.

**Câu hỏi:** Có những lỗi gì?

**Gợi ý:** raw token bị lưu lâu, email gửi khi token đã hết hạn, queue có thể leak, retry có thể gửi link không dùng được. Nên thiết kế token issuance/TTL phù hợp, không giữ plaintext persistent không mã hóa, kiểm tra eligibility trước send và xóa/thu hồi sau hạn.

## 93. Tình huống tự luyện 2 — Hóa đơn bị giữ vô thời hạn

SMTP đã submit nhưng attachment PDF và rendered MIME vẫn ở object storage sáu tháng vì “đề phòng resend”.

**Gợi ý:** cần xác định mục đích/retention chính thức. Nếu hóa đơn phải được lưu, lưu ở document/archive system được mã hóa và phân quyền; không dùng bản sao tạm của mail worker làm archive vô hạn. Có manual resend policy và audit riêng.

## 94. Tình huống tự luyện 3 — SMTP timeout sau DATA

Worker đã gửi hết MIME bytes rồi timeout, status `UNKNOWN`. Cleanup worker thấy `send(...)` ném exception và xóa payload.

**Gợi ý:** status không rõ cần reconciliation/policy, không coi exception đồng nghĩa chắc chắn chưa submit; cleanup không được phá khả năng xử lý đang còn hợp lệ theo retention đã định.

## 95. Tình huống tự luyện 4 — AES key lưu ngay trong config

Ứng dụng encrypt outbox rất tốt nhưng có:

```yaml
app:
  mail:
    encryption-key: "hardcoded-key-example"
```

**Gợi ý:** secret có thể lộ qua repository, CI, deployment logs và nhiều người có quyền đọc config. Dùng KMS/secret manager, quyền giải mã tối thiểu, rotation và audit; không đặt key vào source.

## 96. Tình huống tự luyện 5 — Xóa nhưng versioning giữ bản cũ

Cleanup gọi DeleteObject thành công, dashboard báo `PURGED`. Object bucket bật versioning và có ba versions cũ.

**Gợi ý:** cần kiểm tra semantics của delete marker, xóa đúng versions hoặc áp lifecycle phù hợp, báo trạng thái theo phạm vi thật; không coi một thao tác API là xóa hoàn toàn mọi bản.

## 97. Tình huống tự luyện 6 — Sự cố log chứa token

SMTP authentication thất bại. Error handler in toàn bộ `MimeMessage` để debug; reset token xuất hiện trong SIEM.

**Gợi ý:** tắt raw logging, phân loại phạm vi, thu hồi token còn hiệu lực theo incident process, cleanup nơi lưu có thể kiểm soát và thay bằng structured error codes.

## 98. Tình huống tự luyện 7 — Worker và cleanup chạy đua

Worker dùng `FileSystemResource` đọc PDF khi send. Cleanup xóa file ngay khi TTL đến hạn, dù SMTP đang truyền.

**Gợi ý:** active lease/reference và retention precedence; đồng bộ việc xóa với lifecycle. Nếu deadline là bắt buộc phải hủy, ngăn submit theo policy thay vì im lặng phá tệp giữa lúc serialize.

## 99. Tình huống tự luyện 8 — Tài liệu nhạy cảm gửi qua email thường

Team đề xuất encryption at rest cho outbox rồi cho rằng mail providers không thể xem nội dung.

**Gợi ý:** worker giải mã trước SMTP. Cần xác định có yêu cầu E2E không; nếu có cân nhắc S/MIME/OpenPGP hoặc portal có auth, cùng chính sách khóa và hỗ trợ client.

## 100. Tình huống tự luyện 9 — Restore backup

User yêu cầu xóa dữ liệu ngày thứ Hai; thứ Tư hệ thống restore backup từ Chủ nhật và email cũ xuất hiện lại trong queue.

**Gợi ý:** đóng đường gửi trong DR, replay deletion/cancellation ledger, kiểm tra outbox state, key policies và chỉ mở worker khi reconciliation xong.

## 101. Tình huống tự luyện 10 — Dashboard cần tìm theo email

Team muốn lưu recipient email plaintext trong mọi `mail_notification` row vì dễ filter.

**Gợi ý:** cân nhắc recipient ID, lookup service được cấp quyền, field encryption/blind index có threat model; đừng biến sự tiện lợi của dashboard thành lý do mọi worker có thể đọc PII.

## 102. Những nguyên tắc cần nhớ

1. **Không lưu là biện pháp bảo vệ mạnh nhất khi dữ liệu không cần thiết.**
2. **Mã hóa at rest, TLS SMTP và E2E encryption bảo vệ những ranh giới khác nhau.**
3. **JavaMailSender không tự mã hóa đầu cuối nội dung email.**
4. **Outbox nên giữ metadata/reference và encrypted model khi cần**, tránh raw MIME mặc định.
5. **AES-GCM cần nonce unique, tag validation, AAD/context và quản lý key**.
6. **KMS không tự ngăn ứng dụng đã được cấp quyền log plaintext**.
7. **Retention phải xét trạng thái SMTP và business purpose**, đặc biệt retry/UNKNOWN.
8. **Cleanup là một workflow bền vững**, có retry, idempotency và giám sát.
9. **File tạm, object versions, logs, APM, backups và providers là những bản sao cần inventory**.
10. **Bản đã gửi tới provider/recipient thường không thể thu hồi hoàn toàn từ ứng dụng.**
11. **Data key destruction cần đánh giá granularity và các bản sao khác**, không chỉ xóa alias.
12. **Restore có thể hồi sinh dữ liệu đã xóa**, cần deletion replay.
13. **Token hết hạn/one-time phải có vòng đời riêng**, không phụ thuộc duy nhất vào send status.
14. **Quyền decrypt phải tối thiểu và tách khỏi quyền xem dashboard**.
15. **Pre-send authorization và recipient correctness quan trọng không kém mã hóa**.

## 103. Tài liệu tham khảo

Để triển khai theo phiên bản đang dùng, nên đối chiếu:

- Spring Framework — Email Integration: https://docs.spring.io/spring-framework/reference/integration/email.html
- Spring Boot — Sending Email: https://docs.spring.io/spring-boot/reference/io/email.html
- Java Cryptography Architecture / Cipher (JDK documentation): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html
- OWASP — Cryptographic Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- NIST SP 800-38D — Galois/Counter Mode (GCM): https://csrc.nist.gov/pubs/sp/800/38/d/final

Các tài liệu trên là điểm tham chiếu về API và nguyên tắc bảo mật; các tính năng KMS, object versioning, backup và deletion phải được đối chiếu tài liệu, hợp đồng và chính sách của nền tảng cụ thể. Những ví dụ repository/KMS/service trong bài là abstractions do ứng dụng thiết kế, không phải API tự động có sau khi thêm `spring-boot-starter-mail`.

## 104. Kết luận

**Mã hóa hoặc loại bỏ nội dung nhạy cảm sau khi gửi** là một mẫu thiết kế production bao phủ **toàn vòng đời dữ liệu**, không chỉ là việc gọi `JavaMailSender.send(...)` thành công rồi chạy `DELETE`. Ứng dụng cần giảm số trường nhạy cảm từ đầu, giữ model/attachment ở kho được mã hóa khi còn cần cho retry, giới hạn quyền decrypt, không log raw MIME, quản lý file tạm và object versions, và đặt retention rõ theo loại email, trạng thái notification và yêu cầu nghiệp vụ.

Khi mã hóa, hãy phân biệt encryption at rest với SMTP TLS và S/MIME/PGP. Với payload ứng dụng lưu, nên dùng thuật toán mã hóa xác thực được hỗ trợ và quản lý khóa qua cơ chế phù hợp; AES-GCM đòi hỏi nonce unique, authentication tag và context binding đúng. Khi xóa, cleanup phải có state/idempotency, xử lý race với worker, tuân thủ retention/legal hold và tính tới backups/restore. **Không được hứa rằng xóa payload ở ứng dụng sẽ xóa bản email đã được nhà cung cấp hoặc người nhận lưu.**

Mục tiêu của kiến trúc là **lưu ít nhất có thể, bảo vệ chặt những gì buộc phải lưu, xóa có kiểm chứng khi hết mục đích và báo cáo trung thực về giới hạn kiểm soát**. Kết hợp encrypted outbox, secure mail worker, retention service, deletion ledger và kiểm thử bằng dữ liệu giả giúp hệ thống Spring Framework Mail giảm đáng kể nguy cơ rò rỉ mà vẫn giữ được khả năng retry, audit và vận hành đáng tin cậy.
