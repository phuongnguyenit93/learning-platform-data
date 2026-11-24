# Backup code consumption — Tiêu thụ mã dự phòng đúng một lần

Trong chương **Backup Code Recovery** của module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, tiêu thụ mã dự phòng là bước chuyển một bí mật còn hiệu lực thành bằng chứng đã được sử dụng. Bước này nằm giữa xác minh yêu cầu và cấp quyền tiếp tục khôi phục khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực.

Mã khớp với dữ liệu lưu trong hệ thống chưa đủ để kết luận thành công. Hệ thống phải bảo đảm mã thuộc đúng tài khoản, đúng bộ mã đang hoạt động, yêu cầu hợp lệ và mã chưa từng được sử dụng thành công. Việc đánh dấu đã dùng cần gắn với kết quả khôi phục bền vững, kể cả khi nhiều máy chủ xử lý đồng thời hoặc kết nối mạng bị ngắt.

## 1. Mục tiêu và thuật ngữ

Sau bài này, bạn có thể:

- Phân biệt kiểm tra mã, tiêu thụ mã và cấp quyền khôi phục.
- Thiết kế thao tác dùng một lần, chống phát lại và xử lý yêu cầu đồng thời.
- Chọn cách lưu dấu kiểm chứng phù hợp với độ ngẫu nhiên của mã.
- Xác định ranh giới giao dịch giữa mã, yêu cầu khôi phục, quyền tạm thời và thông báo.
- Xử lý retry, lỗi commit, thay bộ mã và kiểm soát session sau khôi phục.

**Backup code** là bí mật dự phòng được cấp trước để người dùng lưu giữ và sử dụng khi phương tiện xác thực thông thường không còn khả dụng. Bài này dùng mô hình một bộ gồm nhiều mã độc lập; mỗi mã chỉ được sử dụng thành công một lần.

**Consumption**, hay tiêu thụ mã, là chuyển trạng thái có thẩm quyền từ khả dụng sang đã dùng. Việc người dùng bấm nút, giao diện ẩn mã hoặc máy chủ tính được digest khớp chưa phải là tiêu thụ thành công.

**Recovery attempt** là yêu cầu khôi phục có trạng thái phía máy chủ: tài khoản đích, mục đích, thời hạn, bằng chứng đã hoàn thành và liên kết với trình duyệt khởi tạo.

**Recovery grant** là quyền tạm thời cho phép thực hiện một bước khôi phục cụ thể. Grant có thể là bản ghi phía máy chủ đi kèm token ngẫu nhiên; nó không mặc nhiên là session đăng nhập đầy đủ.

NIST mô tả look-up secret là bí mật dùng một lần và chỉ rõ loại này không chống phishing. Vì vậy, chặn phát lại sau khi dùng chưa ngăn được kẻ tấn công chuyển tiếp một mã chưa sử dụng trong thời gian thực. [NIST SP 800-63B-4, mục 3.1.2](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#look-up-secrets).

## 2. Xác định mã được phép thay thế bằng chứng nào

Cùng một mã nhập vào có thể dẫn tới những quyền rất khác nhau. Chính sách phải xác định quyền đó trước khi triển khai endpoint.

| Tình huống | Bằng chứng và ngữ cảnh cần kiểm tra | Kết quả trong thiết kế minh họa |
|---|---|---|
| Còn mật khẩu, mất ứng dụng TOTP | Mật khẩu đã được xác minh gần đây trong đúng attempt; mã hợp lệ | Quyền tiếp tục thay yếu tố bị mất theo chính sách |
| Mất passkey, còn phương thức độc lập đã đăng ký | Phương thức còn lại và mã nếu chính sách yêu cầu tổ hợp này | Luồng đăng ký phương tiện thay thế có kiểm soát |
| Quên mật khẩu, còn phương tiện xác thực khác | Hoàn thành bằng chứng theo chính sách đặt lại mật khẩu | Quyền đổi mật khẩu có thời hạn |
| Mất toàn bộ phương tiện xác thực | Đánh giá riêng các phương án khôi phục và mức bảo đảm cần đạt | Có thể cần bằng chứng bổ sung hoặc xác minh danh tính |
| Nghi bộ mã bị lộ | Xử lý sự cố, đánh giá rủi ro và thu hồi | Không tiếp tục tin tưởng các mã còn lại chỉ vì chúng chưa dùng |

Email nhập vào chỉ là thông tin định tuyến; IP quen thuộc và User-Agent giống trước đây chỉ là tín hiệu rủi ro. Chúng không tự chứng minh quyền sở hữu tài khoản.

Hai mã trong cùng bộ cũng không tự tạo ra hai phương thức khôi phục độc lập: chúng có thể cùng bị đánh cắp từ một tệp. Khi áp dụng NIST cho tài khoản có mức xác thực tối đa AAL2, phải đối chiếu các tổ hợp khôi phục được quy định, thay vì gán mức bảo đảm từ số lượng mã đã nhập. [NIST SP 800-63B-4, mục 4.2.2](https://pages.nist.gov/800-63-4/sp800-63b/events/#recovery-requirements-by-ialaal).

## 3. Những bất biến cần giữ

1. **Đúng phạm vi:** chỉ tra cứu mã trong tài khoản và bộ mã mà máy chủ xác định từ attempt hợp lệ.
2. **Tối đa một lần thành công:** một mã chỉ gắn với tối đa một kết quả tiêu thụ đã commit.
3. **Không mất mã khi yêu cầu bị từ chối:** sai mã, sai binding hoặc thiếu bằng chứng không được làm mất một mã hợp lệ.
4. **Không cấp quyền trước commit:** chỉ trả token hoặc nâng quyền sau khi giao dịch tiêu thụ thành công.
5. **Có kết quả bền vững:** mã đã dùng liên kết tới attempt và grant tương ứng, không chỉ tới một dòng log.
6. **Không hồi sinh:** retry, lỗi gửi email hoặc hỗ trợ thủ công không được đặt lại `used_at` về `NULL`.
7. **Thu hồi có hiệu lực:** nơi sử dụng grant phải kiểm tra trạng thái hiện tại, không chỉ tin vào lần xác minh trước.

Có thể diễn đạt bất biến trung tâm như sau:

~~~text
Với mỗi backup_code_id:
  số recovery grant khởi tạo từ các lần tiêu thụ đã commit <= 1
~~~

Một grant có thể cho phép nhiều thao tác trong phạm vi khôi phục, chẳng hạn tạo challenge và xác minh authenticator mới. Điều đó không có nghĩa là tiêu thụ mã nhiều lần. Riêng thao tác hoàn tất thay đổi credential vẫn cần chuyển trạng thái nguyên tử để tránh thực hiện hai lần.

## 4. Mô hình trạng thái

### 4.1. Trạng thái mã

~~~mermaid
stateDiagram-v2
    [*] --> AVAILABLE: Cấp mã và kích hoạt bộ mã
    AVAILABLE --> CONSUMED: Tiêu thụ và commit thành công
    AVAILABLE --> REVOKED: Thu hồi hoặc thay bộ mã
    AVAILABLE --> EXPIRED: Quá hạn nếu có chính sách hết hạn
    CONSUMED --> [*]
    REVOKED --> [*]
    EXPIRED --> [*]
~~~

Nhập sai không làm đổi trạng thái mã; nó tăng bộ đếm thất bại của attempt hoặc tài khoản. Một giao dịch đã cập nhật `used_at` nhưng rollback chưa tạo ra trạng thái `CONSUMED` bền vững.

Không có chuyển trạng thái `CONSUMED → AVAILABLE`. Khi cần mã mới, hệ thống cấp bí mật ngẫu nhiên mới theo luồng được phép.

### 4.2. Trạng thái attempt và grant

~~~text
Attempt:
  PENDING -> CONSUMED
  PENDING -> EXPIRED hoặc CANCELLED

Grant:
  ACTIVE -> COMPLETED
  ACTIVE -> EXPIRED hoặc REVOKED
~~~

`Attempt.CONSUMED` ở đây nghĩa là attempt đã nhận một grant và không được đổi tiếp mã khác. Nó không khẳng định tài khoản đã hoàn tất khôi phục.

Attempt và grant có thời hạn riêng. Ví dụ attempt sống 10 phút, grant sống 5 phút là lựa chọn minh họa của sản phẩm, không phải thời hạn bắt buộc chung. Mã lưu ngoại tuyến có thể có vòng đời dài hơn; không sao chép thời hạn của token đặt lại mật khẩu sang mã dự phòng mà không phân tích nhu cầu.

## 5. Từ đầu vào tới dấu kiểm chứng

### 5.1. Chuẩn hóa có giới hạn

Giả sử mỗi mã được sinh từ **16 byte ngẫu nhiên mật mã**, biểu diễn thành 32 ký tự hex và hiển thị theo nhóm bốn ký tự. Đây là lựa chọn thiết kế 128 bit entropy của ví dụ, không phải yêu cầu định dạng cho mọi hệ thống.

~~~text
Ví dụ hình thức, không phải mã để sử dụng:
A71C-2D90-4F86-B3E1-C802-9A6D-51F0-7B24

Dạng chuẩn:
A71C2D904F86B3E1C8029A6D51F07B24
~~~

Quy tắc ở bước cấp và bước dùng phải giống nhau:

- Giới hạn đầu vào trước xử lý, ví dụ tối đa 64 ký tự.
- Chỉ bỏ dấu gạch ngang ASCII và dấu cách ASCII nếu giao diện công bố hỗ trợ.
- Chuyển `a..f` thành `A..F`; giữ nguyên `0..9`.
- Từ chối ký tự khác, kể cả chữ toàn chiều rộng, dấu gạch Unicode và ký tự vô hình.
- Sau chuẩn hóa phải có đúng 32 ký tự hex.

Không dùng quy tắc “xóa mọi ký tự không phải chữ hoặc số”, vì nó có thể biến nhiều đầu vào sai thành cùng một bí mật.

Đoạn Java dưới đây chỉ áp dụng cho định dạng hex đã chọn:

~~~java
static String canonicalizeBackupCode(String input) {
    if (input == null || input.length() > 64) {
        throw new IllegalArgumentException("Invalid backup code format");
    }

    StringBuilder canonical = new StringBuilder(32);
    for (int i = 0; i < input.length(); i++) {
        char c = input.charAt(i);
        if (c == '-' || c == ' ') {
            continue;
        }
        if (c >= 'a' && c <= 'f') {
            c = (char) (c - ('a' - 'A'));
        }
        if (!((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F'))) {
            throw new IllegalArgumentException("Invalid backup code format");
        }
        canonical.append(c);
    }

    if (canonical.length() != 32) {
        throw new IllegalArgumentException("Invalid backup code format");
    }
    return canonical.toString();
}
~~~

Không phản ánh lại mã trong thông báo lỗi. Java `String` không cho bảo đảm xóa sạch bí mật khỏi bộ nhớ; cần giảm thời gian lưu giữ và tránh sao chép không cần thiết. Không đưa đầu vào vào exception, log hoặc tracing.

### 5.2. Lưu verifier thay vì mã rõ

Với mã ngẫu nhiên 128 bit của ví dụ, có thể thiết kế dấu kiểm chứng:

~~~text
digest = HMAC-SHA-256(
  server_key[key_id],
  encode_with_lengths("backup-code/v1", user_id, set_id, canonical_code)
)
~~~

`encode_with_lengths` là mã hóa các trường với độ dài hoặc cấu trúc xác định; không nối chuỗi tùy ý bằng dấu phân cách có thể xuất hiện trong dữ liệu. `user_id` và `set_id` lấy từ trạng thái máy chủ. Khóa HMAC được bảo vệ riêng với database, chẳng hạn qua kho khóa có kiểm soát truy cập.

Đây là phương án minh họa cho mã entropy cao. Độ dài chuỗi không chứng minh entropy: 32 ký tự suy ra từ ngày sinh vẫn yếu. Với look-up secret ít entropy, không thay hàm băm mật khẩu có salt bằng SHA-256 hoặc HMAC nhanh rồi cho rằng đã đáp ứng yêu cầu chống đoán ngoại tuyến. NIST có yêu cầu lưu trữ bổ sung đối với look-up secret dưới mức độ mạnh nêu trong tài liệu. [NIST SP 800-63B-4, mục 3.1.2.2](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#look-up-secret-verifiers).

Nếu dùng hàm băm mật khẩu có salt cho một bộ mã ngắn, có thể kiểm chứng tập ứng viên nhỏ trong đúng tài khoản. Sau khi tìm được ứng viên, vẫn phải tiêu thụ bằng cập nhật có điều kiện trên bản ghi đó. Không tạo chỉ mục băm nhanh không khóa cho mã ít entropy nếu chỉ mục này lại cho phép dò toàn bộ không gian mã khi database bị lộ.

`key_id` là phiên bản khóa phía máy chủ. Vì không giữ mã rõ, thường không thể tính lại HMAC của toàn bộ mã chưa dùng khi thay khóa. Cần giữ khóa cũ trong giai đoạn chuyển tiếp được kiểm soát hoặc thu hồi và cấp bộ mới. Nếu không lấy được khóa cần thiết, xử lý như lỗi tạm thời; không bỏ qua kiểm chứng.

## 6. Mô hình dữ liệu

Các bảng sau là mô hình logic, không phải migration hoàn chỉnh để chép vào production.

| Thực thể | Trường chính | Vai trò |
|---|---|---|
| `account_security` | `user_id`, `enabled`, `current_backup_set_id`, `credential_epoch` | Trạng thái bảo mật và điểm khóa chung |
| `backup_code` | `id`, `user_id`, `set_id`, `key_id`, `code_digest`, `used_at`, `revoked_at`, `expires_at`, `consumed_attempt_id` | Dấu kiểm chứng và vòng đời mã |
| `recovery_attempt` | `id`, `user_id`, `purpose`, `state`, `browser_binding_digest`, `expires_at`, `primary_verified_at`, `grant_id` | Ngữ cảnh và bằng chứng của yêu cầu |
| `recovery_grant` | `id`, `user_id`, `attempt_id`, `backup_code_id`, `token_digest`, `purpose`, `credential_epoch`, `expires_at`, `state` | Quyền khôi phục tạm thời |
| `security_outbox` | `event_id`, `event_type`, `aggregate_id`, `payload`, `created_at` | Sự kiện bền vững phục vụ thông báo |

Ví dụ ràng buộc duy nhất:

~~~sql
-- Các đoạn SQL trong bài dùng PostgreSQL.
CREATE UNIQUE INDEX uq_backup_code_verifier
    ON backup_code (user_id, set_id, key_id, code_digest);

CREATE UNIQUE INDEX uq_grant_per_attempt
    ON recovery_grant (attempt_id);

CREATE UNIQUE INDEX uq_grant_per_backup_code
    ON recovery_grant (backup_code_id);
~~~

Cần bổ sung khóa chính, khóa ngoại và cột bắt buộc phù hợp. Mã, attempt và grant phải cùng tài khoản; có thể dùng khóa ngoại ghép hoặc ràng buộc tương đương qua một đường ghi được kiểm soát. Các chỉ mục trên không tự xác thực người đang gửi request.

`used_at` khác `revoked_at`: một mã đã dùng hợp lệ khác một mã bị thu hồi. Giữ trạng thái riêng giúp điều tra mà không lưu mã rõ.

`credential_epoch` là phiên bản trạng thái xác thực do ứng dụng quản lý. Grant ghi phiên bản lúc cấp; endpoint sử dụng grant so sánh với phiên bản hiện tại để từ chối quyền cũ sau các thay đổi bảo mật mà chính sách quy định phải làm mất hiệu lực grant.

## 7. Vì sao đọc rồi ghi có thể dùng mã hai lần

Mã giả sau có lỗ hổng nếu không có cơ chế cạnh tranh phù hợp:

~~~java
BackupCode code = repository.findMatching(userId, digest);
if (code != null && code.usedAt() == null) {
    grantAccess();
    repository.markUsed(code.id());
}
~~~

Hai instance có thể cùng quan sát mã chưa dùng:

| Thời điểm | Request A | Request B |
|---|---|---|
| 1 | Đọc `used_at = NULL` | |
| 2 | | Đọc `used_at = NULL` |
| 3 | Cấp quyền | |
| 4 | | Cấp quyền |
| 5 | Ghi đã dùng | Ghi đã dùng |

Database cuối cùng chỉ có một giá trị `used_at`, nhưng hệ thống đã cấp quyền hai lần. Chỉ kiểm tra trạng thái cuối cùng sẽ bỏ sót lỗi này.

`synchronized` trong một JVM chỉ bảo vệ thread trong instance đó. Khóa nút trên trình duyệt hoặc đánh dấu trong cache cũng không tạo ra bảo đảm dùng một lần trên toàn hệ thống.

Quyết định phải dựa trên cập nhật có điều kiện tại kho dữ liệu có thẩm quyền:

~~~sql
UPDATE backup_code
SET used_at = clock_timestamp(),
    consumed_attempt_id = :attempt_id
WHERE user_id = :server_user_id
  AND set_id = :current_set_id
  AND key_id = :key_id
  AND code_digest = :digest
  AND used_at IS NULL
  AND revoked_at IS NULL
  AND (expires_at IS NULL OR expires_at > clock_timestamp())
RETURNING id;
~~~

Phải nhận **đúng một dòng** để đi tiếp. Không có dòng nghĩa là không cấp grant; nhiều dòng là vi phạm bất biến và phải rollback.

Ở PostgreSQL `READ COMMITTED`, cập nhật cạnh tranh trên cùng hàng có thể phải chờ; khi giao dịch trước commit, điều kiện `WHERE` được đánh giá lại trên phiên bản mới. Nhờ đó, `used_at IS NULL` chặn lần dùng sau. Với hệ quản trị hoặc mức cô lập khác, phải đối chiếu lại ngữ nghĩa khóa và lỗi cần retry. [PostgreSQL 18: Read Committed](https://www.postgresql.org/docs/18/transaction-iso.html#XACT-READ-COMMITTED).

Câu lệnh này giải quyết cạnh tranh của một hàng mã. Nó chưa tự xử lý cuộc đua với thao tác đổi bộ mã hoặc khóa tài khoản nằm ở hàng khác.

## 8. Gắn tiêu thụ mã với quyền khôi phục trong một giao dịch

### 8.1. Chuẩn bị request

1. Nhận request qua HTTPS, kiểm tra kích thước và định dạng.
2. Tìm attempt từ ngữ cảnh máy chủ; không tin `user_id`, `purpose` hoặc `set_id` do client tự khai.
3. Xác minh browser binding, chống CSRF khi dùng cookie và các bằng chứng chính sách yêu cầu.
4. Áp dụng giới hạn thử trước công việc tốn tài nguyên.
5. Sinh token grant độc lập bằng CSPRNG, ví dụ 32 byte ngẫu nhiên. Chuẩn bị digest để lưu; chỉ trả token rõ sau commit.

Backup code và token grant là hai bí mật khác nhau. Không dùng chính backup code làm cookie của luồng khôi phục.

Kiểm tra sơ bộ giúp giảm tải, nhưng trạng thái có thể đổi trong lúc chờ khóa. Các điều kiện bảo mật có thể thay đổi phải được xác minh lại trong giao dịch.

### 8.2. Thứ tự khóa

Ví dụ chọn thứ tự chung:

~~~text
account_security -> recovery_attempt -> backup_code -> recovery_grant
~~~

Mọi đường đổi bộ mã, khóa tài khoản, hủy attempt và thu hồi quyền liên quan phải tuân theo quy ước tương thích. Chỉ endpoint tiêu thụ khóa tài khoản trong khi endpoint đổi bộ mã bỏ qua khóa thì vẫn còn cuộc đua.

Khóa theo tài khoản làm các thao tác khôi phục của cùng tài khoản chạy tuần tự. Đây là đánh đổi dễ giải thích cho luồng ít xảy ra; cần giới hạn thời gian chờ khóa và tránh gọi email, HTTP hay dịch vụ chậm khi đang giữ khóa.

### 8.3. Khung giao dịch PostgreSQL

Các tham số `:server_*` và `:locked_*` lấy từ ngữ cảnh tin cậy hoặc hàng đã khóa. Các dòng `ASSERT` trong chú thích là điều kiện ứng dụng **phải kiểm tra và rollback nếu sai**, không phải cú pháp PostgreSQL chạy trực tiếp.

~~~sql
BEGIN;

SELECT user_id, enabled, current_backup_set_id, credential_epoch
FROM account_security
WHERE user_id = :server_user_id
FOR UPDATE;

-- ASSERT: đúng một tài khoản, enabled = true,
-- có bộ mã hiện tại đang hoạt động.

SELECT id, user_id, purpose, state, expires_at,
       browser_binding_digest, primary_verified_at
FROM recovery_attempt
WHERE id = :attempt_id
  AND user_id = :server_user_id
FOR UPDATE;

-- ASSERT sau khi lấy khóa:
-- state = 'PENDING'; binding đúng; purpose được phép;
-- bằng chứng còn đủ mới; attempt chưa hủy hoặc hết hạn.

-- Tính code_digest theo bộ mã vừa đọc và đúng phiên bản khóa.
-- Có thể chuẩn bị khóa trước transaction, nhưng phải xác nhận
-- lại bộ mã và phiên bản khóa sau khi lấy khóa hàng.

UPDATE backup_code
SET used_at = clock_timestamp(),
    consumed_attempt_id = :attempt_id
WHERE user_id = :server_user_id
  AND set_id = :locked_set_id
  AND key_id = :locked_key_id
  AND code_digest = :code_digest
  AND used_at IS NULL
  AND revoked_at IS NULL
  AND (expires_at IS NULL OR expires_at > clock_timestamp())
RETURNING id;

-- ASSERT: đúng một dòng; lấy id làm :consumed_code_id.
-- Kiểm tra lại deadline của attempt ngay trước bước quyết định
-- nếu việc chờ hoặc xử lý có thể đã vượt deadline.

INSERT INTO recovery_grant (
    id, user_id, attempt_id, backup_code_id, token_digest,
    purpose, credential_epoch, expires_at, state
) VALUES (
    :grant_id, :server_user_id, :attempt_id, :consumed_code_id,
    :grant_token_digest, :server_allowed_purpose,
    :locked_credential_epoch,
    clock_timestamp() + interval '5 minutes', 'ACTIVE'
);

UPDATE recovery_attempt
SET state = 'CONSUMED', grant_id = :grant_id
WHERE id = :attempt_id
  AND user_id = :server_user_id
  AND state = 'PENDING';

-- ASSERT: đúng một dòng được cập nhật.

INSERT INTO security_outbox (
    event_id, event_type, aggregate_id, payload, created_at
) VALUES (
    :event_id, 'BACKUP_CODE_CONSUMED', :server_user_id,
    :metadata_without_secrets, clock_timestamp()
);

COMMIT;
~~~

Thời hạn của mã được kiểm tra ở bước tiêu thụ. Deadline của attempt phải được kiểm tra bằng thời gian hiện tại phía database sau khi lấy khóa và sát bước quyết định; không dùng một timestamp cũ lấy từ đầu request. Nếu chính sách yêu cầu deadline chung đến lúc hoàn tất giao dịch, cần thiết kế rõ điều kiện đó.

Sau khi `COMMIT` được xác nhận thành công, API mới trả token grant hoặc đặt cookie. Nếu bất kỳ bước nào rollback, mã và grant đều không được ghi thành công. Endpoint sử dụng token còn phải đối chiếu bản ghi grant đã commit.

Bộ mã và epoch được đọc từ hàng đã khóa, không lấy dữ liệu cũ từ read replica làm quyết định. Với ORM, cần xác nhận SQL thật có điều kiện, kiểm tra số dòng và thực sự nằm trong cùng transaction; annotation giao dịch không tự sửa thuật toán đọc-rồi-ghi sai.

### 8.4. Diễn tiến thành công

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant A as Recovery API
    participant D as Database có thẩm quyền
    participant W as Outbox worker
    U->>A: Gửi mã trong attempt đã ràng buộc
    A->>A: Kiểm tra đầu vào, bằng chứng và giới hạn thử
    A->>D: BEGIN, khóa tài khoản và attempt
    A->>D: UPDATE mã còn khả dụng
    D-->>A: Một code_id
    A->>D: INSERT grant, đóng attempt, INSERT outbox
    A->>D: COMMIT
    D-->>A: Commit thành công
    A-->>U: Quyền khôi phục có giới hạn
    W->>D: Đọc sự kiện đã commit
    W-->>U: Thông báo qua kênh đã đăng ký
~~~

Cập nhật nguyên tử bảo đảm một mã không bị tiêu thụ hai lần. Transaction giữ kết quả mã và grant nhất quán. Outbox giúp giao việc sau commit một cách bền vững. Ba cơ chế giải quyết ba vấn đề khác nhau.

## 9. Retry và kết quả commit chưa xác định

| Sự cố | Trạng thái có thể có | Hành vi phù hợp |
|---|---|---|
| API dừng trước commit | Transaction rollback | Có thể thử lại sau khi kiểm tra trạng thái |
| Tạo grant lỗi sau cập nhật mã | Toàn bộ transaction rollback | Không để riêng `used_at` đã commit |
| Commit thành công nhưng mất response | Mã đã dùng, grant đã có; client có thể chưa nhận token | Kiểm tra kết quả qua attempt đáng tin cậy |
| Gửi lại mã trong attempt khác | Mã đã dùng | Không tạo grant thứ hai |
| Gửi thông báo lỗi | Mã và grant vẫn đã commit | Retry outbox, không mở lại mã |
| Đứt kết nối khi commit | API chưa biết commit hay rollback | Đối chiếu database có thẩm quyền |

### 9.1. Phương án đơn giản: không phát lại token cũ

Ví dụ giao dịch ở trên không lưu response để phát lại. Nếu response chứa token bị mất, digest đã lưu không cho phép tái tạo token rõ. Sản phẩm cần chấp nhận hạn chế này hoặc cung cấp cách tiếp tục đã được thiết kế, chẳng hạn resume có ràng buộc mạnh; một phương án khác là dùng mã còn lại và attempt mới theo chính sách.

Không giải quyết bằng cách trả grant cho bất cứ ai biết mã đã dùng, và không đặt lại `used_at`.

### 9.2. Nếu cần idempotency

Một cơ chế trả lại kết quả cho cùng request phải có hợp đồng cụ thể:

- Khóa idempotency ràng buộc với attempt và browser secret đã xác minh; bản thân khóa không cấp quyền.
- Fingerprint payload không được tạo thêm công cụ dò mã. Cùng khóa nhưng khác payload bị từ chối.
- Kết quả tham chiếu cùng grant, không tạo grant mới và không tiêu thụ mã khác.
- Nếu cần trả lại token rõ, phải thiết kế nơi giữ response được mã hóa, TTL ngắn, hoặc một giao thức resume riêng. Chỉ lưu digest thì không khôi phục được token.
- Response cache không làm sống lại grant hết hạn hoặc bị thu hồi; phải kiểm tra trạng thái hiện tại.

Khi commit chưa rõ kết quả, tra theo `attempt_id` và grant trên nguồn có thẩm quyền. Không tự động chạy một thao tác “bù” đặt lại mã. Độ bền của transaction và cơ chế failover cũng phải đủ để không mất lịch sử tiêu thụ đã xác nhận.

## 10. Cạnh tranh với thay bộ mã và thay đổi bảo mật

### 10.1. Tiêu thụ đồng thời với tạo bộ mã mới

Giả sử request dùng bộ `S1` trong lúc thiết bị khác tạo `S2`:

- Nếu transaction thay bộ mã giữ khóa và commit trước, request tiêu thụ phải thấy `S2`; mã `S1` bị từ chối.
- Nếu transaction tiêu thụ commit trước, mã `S1` có thể đã được chấp nhận hợp lệ trước thời điểm thay bộ.
- Nếu thay bộ vì nghi lộ bí mật, cần thu hồi cả grant đang chờ có nguồn gốc từ bộ cũ, hoặc dùng epoch mà mọi endpoint grant đều kiểm tra.

Chỉ đổi `current_backup_set_id` mà bỏ qua grant đã cấp chưa vô hiệu hóa toàn bộ hệ quả của việc lộ bộ mã.

### 10.2. Hai mã khác nhau trong cùng attempt

Dù cả hai mã đều chưa dùng, cùng một attempt không nên tạo hai grant. Khóa attempt, chuyển nó khỏi `PENDING` và ràng buộc duy nhất trên `recovery_grant(attempt_id)` cùng bảo vệ điều này. Request thua phải rollback để không làm mất thêm mã.

### 10.3. Khóa tài khoản và đổi credential

Đường khóa tài khoản phải phối hợp cùng điểm khóa và cơ chế thu hồi. Khi sử dụng grant, luôn kiểm tra `enabled`, trạng thái grant, thời hạn và epoch hiện tại.

Khi hoàn tất cập nhật credential và tăng epoch, quy định rõ việc chuyển grant sang `COMPLETED` trong cùng giao dịch. Không để grant cũ vẫn có thể thực hiện lại thao tác.

## 11. Kiểm soát grant và session sau tiêu thụ

Trong thiết kế của bài, tiêu thụ mã tạo quyền có giới hạn, chẳng hạn tiếp tục thay authenticator bị mất. Backend xác định thao tác được phép từ `purpose` và chính sách, không nhận danh sách scope do client tự chọn.

Mỗi endpoint sử dụng grant cần kiểm tra:

- Token khớp verifier và liên kết đúng tài khoản, attempt, browser context nếu dùng binding.
- Grant đang `ACTIVE`, chưa hết hạn và chưa bị thu hồi.
- Tài khoản vẫn được phép khôi phục; epoch còn đúng.
- Thao tác nằm trong mục đích được cấp.
- Đã hoàn thành bằng chứng bổ sung cần thiết cho hành động nhạy cảm.

Một backup code không tự cấp quyền đổi email nhận thông báo, thay số điện thoại, tải dữ liệu hoặc tạo API key. Nếu grant cho phép đăng ký authenticator mới, luồng vẫn phải kiểm chứng phương tiện mới theo giao thức tương ứng; tiêu thụ mã chưa hoàn tất bước đăng ký.

Tách session trước xác thực và sau xác thực. Khi thiết lập session mới hoặc tăng quyền, thay session identifier theo framework và làm mất hiệu lực trạng thái cũ phù hợp. OWASP yêu cầu tái sinh session ID khi mức quyền thay đổi và xem khôi phục tài khoản là sự kiện cần cân nhắc xác thực lại. [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#renew-the-session-id-after-any-privilege-level-change).

Cookie mang token cần `Secure`, `HttpOnly`, `SameSite` và phạm vi phù hợp. Chống CSRF vẫn cần thiết theo kiến trúc; `SameSite` không thay thế mọi biện pháp khác. Không đặt backup code hoặc token grant trong URL vì dễ lọt vào lịch sử, log và công cụ phân tích.

Nếu khôi phục do mất thiết bị hoặc nghi bị chiếm quyền, xử lý session, refresh token và authenticator bị ảnh hưởng theo chính sách. Xóa cookie hiện tại không thu hồi token trên thiết bị khác. Với access token tự chứa, epoch chỉ giúp thu hồi sớm khi dịch vụ nhận token thực sự kiểm tra nó hoặc áp dụng cơ chế thu hồi tương đương.

## 12. Chống đoán mã, dò tài khoản và phá hoại

### 12.1. Giới hạn nhiều chiều

Giới hạn theo tài khoản hoặc định danh đích đã chuẩn hóa, attempt và nguồn truy cập. Chỉ giới hạn IP dễ bị né bằng nhiều nguồn; chỉ giới hạn attempt dễ bị né bằng cách tạo attempt mới.

Ví dụ sản phẩm có thể cho phép tối đa 5 lần sai trong một attempt và áp dụng backoff theo tài khoản. Đây là số minh họa; ngưỡng thực tế phụ thuộc entropy, rủi ro, lưu lượng và khả năng hỗ trợ.

Bộ đếm thất bại phải tồn tại dù transaction tiêu thụ rollback. Nếu tăng bộ đếm rồi rollback cùng giao dịch bị từ chối, kẻ tấn công có thể không bao giờ chạm ngưỡng. Có thể dùng limiter dùng chung hoặc cập nhật trạng thái thất bại trong transaction riêng được thiết kế rõ.

Không khóa vĩnh viễn tài khoản chỉ vì người lạ nhập sai nhiều lần. Backoff, giới hạn nguồn và đường hỗ trợ có kiểm soát giúp giảm nguy cơ từ chối dịch vụ. CAPTCHA là biện pháp bổ sung, không thay thế trạng thái dùng một lần hoặc giới hạn phía máy chủ.

### 12.2. Thông báo công khai

Ví dụ:

> Không thể sử dụng mã này cho yêu cầu hiện tại. Hãy kiểm tra mã hoặc dùng phương thức khôi phục khác.

Tránh endpoint công khai trả “tài khoản còn 7 mã”, “mã đã dùng lúc 09:12” hoặc “mã đúng nhưng tài khoản bị khóa”. Chi tiết chỉ nên xuất hiện trong ngữ cảnh đã xác thực và được phép.

Lỗi tạm thời hoặc rate limit có thể có phản hồi riêng nhất quán, miễn không lộ tình trạng của tài khoản. Với verifier tốn tài nguyên, cân bằng giảm khác biệt thời gian phản hồi với chống làm cạn CPU; không chạy băm đắt tiền không giới hạn chỉ để làm đều latency.

### 12.3. Bảo vệ bí mật khỏi công cụ vận hành

Ẩn trường mã ở reverse proxy, log ứng dụng, APM, trace, session replay và báo cáo lỗi. Bỏ log trong controller chưa đủ nếu gateway vẫn ghi toàn bộ body.

Không đưa mã rõ hoặc digest vào metric label. IP, định danh thiết bị và metadata cá nhân cũng cần giới hạn truy cập và thời gian lưu.

Nhân viên hỗ trợ không nên yêu cầu người dùng đọc nguyên backup code qua điện thoại hoặc chat để kiểm tra thủ công. Hỗ trợ phải dùng quy trình xác minh đã thiết kế, không đi vòng qua nơi tiêu thụ mã có thẩm quyền.

## 13. Mã còn lại, cấp bù và thu hồi

Có thể hiển thị số mã còn lại sau commit trong ngữ cảnh đã được phép. Con số này phục vụ trải nghiệm và có thể thay đổi do thao tác ở thiết bị khác; nó không phải nguồn quyết định mã tiếp theo còn hiệu lực.

Không trả lại mã rõ cũ: hệ thống chỉ giữ verifier nên không nên có khả năng đọc lại danh sách bí mật. Khi nghi lộ bộ mã, tạo bộ mới và thu hồi bộ cũ theo transaction hoặc quy trình kích hoạt có trạng thái rõ. Cần xử lý cả trường hợp người dùng đóng trang trước khi lưu mã mới; không âm thầm kích hoạt hai bộ do retry.

Phân biệt các mô hình:

| Mô hình | Hành vi sau khi dùng mã | Điểm phải quy định |
|---|---|---|
| Bộ nhiều mã dự phòng dùng trong luồng MFA của sản phẩm | Các mã chưa dùng có thể còn hiệu lực nếu chính sách cho phép và không có sự cố | Khi nào cảnh báo còn ít, cấp bù hoặc thay bộ |
| Saved recovery code theo NIST | Vô hiệu hóa mã đã dùng và cấp mã thay thế | Không tuyên bố đáp ứng mô hình chỉ bằng cách giảm số mã trong bộ |

NIST quy định saved recovery code có ít nhất 64 bit ngẫu nhiên, lưu dạng băm, có giới hạn thử, và sau sử dụng phải vô hiệu hóa cùng việc cấp mã thay thế. Khi áp dụng mô hình đó, quy trình phải xử lý cả bước thay thế. [NIST SP 800-63B-4, mục 4.2.1.1](https://pages.nist.gov/800-63-4/sp800-63b/events/#saved-recovery-codes).

Cấp bù phải nằm trong ngữ cảnh đã đáp ứng chính sách, qua kênh bảo vệ và có trạng thái giao nhận phù hợp. Grant còn thiếu bằng chứng không được tạo vô hạn mã mới. Không hồi sinh mã đã tiêu thụ để khắc phục lỗi giao nhận.

OWASP xem thay yếu tố MFA là thao tác rủi ro cao cần xác thực phù hợp và thông báo độc lập. Chính sách cấp hoặc thay bộ mã nên được đánh giá cùng nhóm thao tác này. [OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors).

## 14. Audit, thông báo và độ bền

Sự kiện nội bộ có thể có dạng sau; các giá trị chỉ để minh họa:

~~~json
{
  "eventId": "evt-illustration-01",
  "eventType": "BACKUP_CODE_CONSUMED",
  "accountRef": "account-internal-42",
  "attemptRef": "attempt-internal-17",
  "codeRef": "code-internal-08",
  "grantRef": "grant-internal-23",
  "purpose": "REPLACE_LOST_AUTHENTICATOR",
  "outcome": "COMMITTED"
}
~~~

Bổ sung thời gian đáng tin cậy và metadata rủi ro tối thiểu cần thiết. `codeRef` là định danh bản ghi nội bộ, không phải mã hoặc digest. Không ghi thành công trước commit; nếu cần log giai đoạn trung gian, phải thể hiện rõ trạng thái chưa commit.

Outbox worker gửi thông báo qua kênh đã đăng ký đáng tin cậy, nêu thời gian và cách báo cáo bất thường. Không gửi mã đã dùng hoặc token grant. Luồng “không phải tôi” cũng cần chống lạm dụng để không trở thành cách khóa tài khoản tùy ý.

Worker phải chịu được việc xử lý lại sự kiện. Dùng `event_id` để khử trùng lặp ở nơi nhận khi có thể; thiết kế nội dung chịu được khả năng gửi trùng. Transaction cộng broker hoặc email không tự tạo bảo đảm gửi đúng một lần xuyên suốt.

Các chỉ số hữu ích: số lần tiêu thụ thành công, từ chối, chạm rate limit, thời gian chờ khóa và tuổi sự kiện outbox chưa xử lý. Phân biệt lý do nội bộ để điều tra nhưng không dùng mã hoặc tài khoản thô làm nhãn metric có cardinality cao.

**Phục hồi snapshot cũ** có thể làm mã đã dùng xuất hiện như chưa dùng. Kế hoạch khôi phục dữ liệu phải tái lập lịch sử tiêu thụ/thu hồi đáng tin cậy hoặc vô hiệu hóa các bộ mã và grant bị ảnh hưởng. Failover làm mất transaction đã xác nhận cũng có thể phá bất biến. Bảo đảm ứng dụng luôn chịu giới hạn độ bền thực tế của kho dữ liệu.

## 15. Tình huống: mất điện thoại và gửi mã hai lần

Linh còn mật khẩu nhưng mất điện thoại chứa TOTP. Chính sách sản phẩm cho phép mật khẩu mới xác minh kết hợp một backup code để bắt đầu thay authenticator; rủi ro cao có thể yêu cầu kiểm tra bổ sung.

1. Máy chủ tạo attempt `PENDING` có TTL ngắn và browser binding sau bước mật khẩu. Linh chưa có session đầy đủ.
2. Linh gửi mã từ bộ đã lưu. Giao diện khóa nút tạm thời để giảm bấm nhầm.
3. Mạng chậm khiến trình duyệt gửi hai request đến hai instance.
4. A khóa tài khoản và attempt, tiêu thụ mã, tạo grant, đóng attempt rồi commit.
5. B chờ khóa, sau đó thấy attempt không còn `PENDING`; không tạo grant thứ hai và không làm mất mã khác.
6. Khi nhận token của A, Linh tiếp tục đăng ký và xác minh authenticator mới trong phạm vi grant.
7. Nếu mất response của A, hệ thống xử lý theo hợp đồng retry/resume ở mục 9, không mở lại mã.
8. Hoàn tất khôi phục làm grant chuyển `COMPLETED`; hệ thống xử lý authenticator bị mất, session liên quan và bộ mã theo chính sách, rồi gửi thông báo bảo mật.

Nếu kẻ tấn công lấy mã chưa dùng và hoàn thành đủ bằng chứng trước Linh, cập nhật nguyên tử vẫn có thể cho kẻ tấn công thắng. Dùng một lần chỉ giới hạn số lần thành công; bảo vệ nơi lưu mã, chất lượng bằng chứng và đánh giá rủi ro quyết định ai có thể thực hiện lần đó.

## 16. Các tình huống cần chứng minh khi triển khai

Bảng này là tình huống để đối chiếu thiết kế, không phải kết quả kiểm thử của một hệ thống đã chạy.

| Tình huống | Kết quả cần có |
|---|---|
| Mã và attempt hợp lệ | Một mã được tiêu thụ, một grant được commit |
| Nhiều instance dùng cùng mã | Tối đa một grant khởi tạo từ mã đó |
| Hai mã khác nhau trong cùng attempt | Chỉ một grant; mã của transaction bị từ chối không bị mất |
| Mã tài khoản khác | Từ chối, không chấp nhận xuyên tài khoản |
| Mã đã dùng, hết hạn hoặc bị thu hồi | Không có grant mới |
| Đổi bộ mã trong lúc request chờ | Tôn trọng thứ tự transaction và trạng thái bộ mã mới |
| Attempt hết hạn khi chờ khóa | Kiểm tra lại deadline và từ chối phù hợp |
| Tạo grant hoặc ghi outbox lỗi | Rollback toàn bộ |
| Commit xong nhưng mất response | Không tiêu thụ lần hai; theo hợp đồng retry/resume |
| Rollback do sai mã | Bộ đếm thất bại vẫn tồn tại theo chính sách |
| Cùng idempotency key, payload khác | Từ chối; không trả token request trước |
| Khóa tài khoản hoặc thu hồi grant | Endpoint sử dụng grant từ chối |
| Token còn trên thiết bị khác | Cơ chế thu hồi phía máy chủ có hiệu lực theo chính sách |
| Thiếu khóa HMAC hoặc database lỗi | Lỗi tạm thời, không bỏ qua kiểm chứng |
| Restore từ trước lần dùng mã | Không cho mã đã dùng xác thực lại ngoài chính sách phục hồi |

Kiểm tra cạnh tranh cần nhiều kết nối hoặc tiến trình độc lập và quan sát **số grant đã commit**, không chỉ số HTTP 200 hay giá trị `used_at` cuối cùng. Giao diện có thể giảm gửi trùng; backend và kho dữ liệu phải thực thi bảo đảm cuối cùng.

## 17. Tài liệu đối chiếu và phạm vi ví dụ

- [NIST SP 800-63B-4 — Authenticator and Verifier Requirements](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/): tính dùng một lần và lưu trữ look-up secret.
- [NIST SP 800-63B-4 — Authenticator Event Management](https://pages.nist.gov/800-63-4/sp800-63b/events/): saved recovery code và các tổ hợp khôi phục.
- [OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html): khôi phục và bảo vệ việc thay yếu tố.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): vòng đời session và cookie.
- [PostgreSQL 18 — Transaction Isolation](https://www.postgresql.org/docs/18/transaction-iso.html): cập nhật cạnh tranh và mức cô lập.

Định dạng 128 bit, TTL minh họa, HMAC, thứ tự khóa theo tài khoản và mô hình grant là những lựa chọn để giải thích một thiết kế cụ thể. Ví dụ SQL cần được đưa vào chính sách xác thực, khôi phục và độ bền dữ liệu của hệ thống; nó không thay thế một triển khai đầy đủ hoặc chứng nhận tuân thủ tiêu chuẩn.
