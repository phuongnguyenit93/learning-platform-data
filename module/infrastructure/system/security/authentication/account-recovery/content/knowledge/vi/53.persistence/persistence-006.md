# Recovery record migration — Di trú bản ghi khôi phục tài khoản

## 1. Bản ghi recovery là một phần của cơ chế cấp quyền

Di trú bản ghi khôi phục tài khoản là chuyển dữ liệu đang lưu sang cấu trúc hoặc cách diễn giải mới, trong khi vẫn giữ đúng các điều kiện cho phép sử dụng luồng khôi phục. Một bản ghi có thể chứa định danh tài khoản, mục đích recovery, dấu vết xác minh, digest của token, hạn dùng, số lần thử, thời điểm thu hồi và trạng thái hoàn tất.

Trong hệ thống SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY, dữ liệu này phục vụ các tình huống mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Sai sót khi di trú có thể biến một liên kết đã dùng thành liên kết dùng được lần nữa, bỏ qua bước xác minh bổ sung hoặc cho phép token đặt lại mật khẩu được dùng để thay MFA.

Vì vậy, thành công không chỉ là mọi hàng đều đọc được theo schema mới. Điều kiện quan trọng là **quyền khôi phục không tự tăng lên do chuyển đổi dữ liệu**.

Ví dụ, hệ thống cũ lưu **used = true**, còn hệ thống mới lưu **state = CONSUMED**. Nếu cột state được điền mặc định READY, một token từng hoàn tất recovery có thể xuất hiện như chưa được sử dụng. Dữ liệu hợp lệ về kiểu vẫn có thể sai về quyền.

OWASP yêu cầu token đặt lại mật khẩu được lưu an toàn, chỉ sử dụng một lần và hết hạn sau khoảng thời gian phù hợp. Di trú phải bảo toàn những đặc tính đó. Phần áp dụng cho MFA hoặc passkey trong bài là thiết kế minh họa; các luồng này cần chính sách xác minh riêng theo rủi ro. [Nguồn: OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

## 2. Xác định chính xác dữ liệu đang được di trú

Cần phân biệt thay đổi cấu trúc bảng, thay đổi ý nghĩa dữ liệu và thay đổi chính sách chấp nhận recovery.

| Loại thay đổi | Ví dụ | Câu hỏi phải trả lời |
| --- | --- | --- |
| Cấu trúc lưu trữ | Tách cột JSON thành các cột có kiểu | Giá trị thiếu hoặc không hợp lệ được xử lý thế nào? |
| Mô hình trạng thái | Chuyển used/revoked sang state | Những trạng thái nào đã kết thúc và không được mở lại? |
| Liên kết định danh | Bổ sung tenant_id hoặc purpose | Có nguồn đáng tin cậy để xác định giá trị lịch sử không? |
| Cách kiểm tra token | Thêm token_format và key_id | Trình xác minh có đọc được token đang lưu hành không? |
| Chính sách recovery | Tăng yêu cầu bằng chứng cho thay MFA | Bản ghi cũ có thật sự đạt điều kiện mới không? |
| Vận hành dữ liệu | Chuyển bảng, shard hoặc cơ sở dữ liệu | Nguồn nào quyết định token còn dùng được tại mỗi thời điểm? |

Đổi nơi lưu không có nghĩa là khôi phục bí mật của người dùng. Không được tạo lại private key passkey, seed MFA hay mật khẩu từ recovery record. Nếu chính sách cho phép đăng ký yếu tố mới sau recovery, đó là một hành động nghiệp vụ riêng, có xác minh và kiểm soát session tương ứng.

Trong bài, một recovery record đại diện cho **một yêu cầu và mục đích cụ thể**. Nếu hệ thống thực tế tách request, challenge, evidence và grant thành nhiều bảng, cần giữ cả quan hệ giữa chúng. Việc một challenge đã được xác minh không tự có nghĩa là toàn bộ yêu cầu đã đủ điều kiện hoàn tất.

## 3. Các bất biến bảo mật phải được giữ

Một kế hoạch chuyển đổi nên viết rõ các bất biến trước khi chọn công cụ backfill.

| Bất biến | Cách áp dụng khi di trú |
| --- | --- |
| Đúng tài khoản và tenant | Giữ nguyên liên kết định danh; không dùng tenant mặc định cho hàng thiếu dữ liệu |
| Đúng mục đích | PASSWORD_RESET không tự trở thành MFA_REPLACEMENT hoặc PASSKEY_REPLACEMENT |
| Dùng một lần | Trạng thái consumed và dấu vết sử dụng tiếp tục chặn mọi lần sử dụng tiếp theo |
| Thu hồi có hiệu lực | Bản ghi revoked không được trở lại pending hoặc ready |
| Không gia hạn ngầm | Giữ hoặc rút ngắn hạn dùng đã có |
| Không nâng mức xác minh | Bằng chứng cũ không được tự đổi thành bằng chứng mạnh hơn |
| Không xóa chống lạm dụng | Số lần thử, khóa tạm và thời gian chờ không bị đặt lại vì đổi schema |
| Tôn trọng thay đổi tài khoản | Kiểm tra phiên bản bảo mật hiện tại khi dùng token |
| Không phát sinh tác dụng phụ nghiệp vụ | Backfill không đổi mật khẩu, gắn MFA, tạo session hay gửi lại token |
| Không rò bí mật | Log, bảng tạm và dữ liệu lỗi không chứa raw token hoặc bằng chứng định danh đầy đủ |

Hai loại chuyển đổi đặc biệt nguy hiểm là **mất thông tin từ chối** và **sáng tạo thông tin chấp nhận**. Ví dụ thứ nhất là bỏ revoked_at; ví dụ thứ hai là điền verified_at bằng thời điểm chạy migration cho hàng chưa từng được xác minh.

Với dữ liệu không đủ chứng cứ, có thể cách ly bản ghi, thu hồi quyền sử dụng và yêu cầu người dùng bắt đầu một luồng mới. Bản ghi mới phải qua quy trình phát hành và kiểm soát lạm dụng bình thường; migration không tự tạo quyền thay thế.

## 4. Tách các loại version

Một trường version duy nhất thường không đủ để diễn tả mọi thay đổi.

| Trường minh họa | Ý nghĩa |
| --- | --- |
| schema_version | Cấu trúc hoặc cách tuần tự hóa dữ liệu |
| migration_version | Phiên bản chuyển đổi đã áp dụng cho hàng |
| token_format | Quy tắc diễn giải và kiểm tra token |
| key_id | Khóa dùng để kiểm tra digest hoặc giải mã dữ liệu |
| policy_version | Chính sách áp dụng khi phát hành hoặc đánh giá yêu cầu |
| security_epoch | Phiên bản bảo mật của tài khoản mà yêu cầu gắn với |
| row_version | Phiên bản cập nhật để phát hiện ghi đè đồng thời |

Ví dụ, tăng migration_version từ 1 lên 2 không được tăng security_epoch hay biến policy_version cũ thành chính sách mới đã được đáp ứng. row_version tăng vì bản ghi được ghi lại cũng không chứng minh người dùng vừa xác minh danh tính.

security_epoch hữu ích khi thay đổi mật khẩu, yếu tố xác thực hoặc sự kiện rủi ro phải làm mất hiệu lực các recovery request trước đó. Nếu token mang epoch cũ, bộ xử lý phải từ chối dù state trong hàng vẫn là READY.

Một epoch lịch sử bị thiếu không được điền bằng epoch hiện tại chỉ để làm phép so sánh thành công. Cách đó có thể hợp thức hóa yêu cầu đã bị vô hiệu hóa. Cần có chứng cứ lịch sử đáng tin cậy hoặc chặn yêu cầu đó.

## 5. Ánh xạ trạng thái theo ý nghĩa

Giả sử mô hình đích có các trạng thái sau:

- **PENDING**: còn thiếu bước xác minh hoặc điều kiện bắt buộc.
- **READY**: đã đạt các điều kiện của quy trình được định nghĩa, nhưng vẫn phải kiểm tra token, hạn dùng và trạng thái tài khoản khi hoàn tất.
- **CONSUMED**: quyền đã được sử dụng.
- **REVOKED**: quyền đã bị thu hồi.
- **EXPIRED**: hết hạn.
- **QUARANTINED**: dữ liệu không đủ tin cậy để tiếp tục sử dụng.

Các tên này là mô hình minh họa, không phải yêu cầu về tên enum.

| Dữ liệu lịch sử | Kết quả an toàn |
| --- | --- |
| Có dấu vết đã sử dụng | CONSUMED; giữ thời điểm và dấu vết gốc |
| Có dấu vết bị thu hồi | REVOKED; giữ lý do và thời điểm nếu có |
| Có cả dấu vết sử dụng và thu hồi | Giữ cả hai dữ kiện, chọn trạng thái kết thúc theo quy tắc đã công bố; không cho sử dụng |
| Hạn dùng đã qua | EXPIRED, kể cả tác vụ dọn dữ liệu chưa chạy |
| Thiếu tài khoản, tenant hoặc mục đích đáng tin cậy | QUARANTINED |
| VERIFIED trong hệ thống chỉ có nghĩa đã xác minh email | PENDING nếu luồng đích còn yêu cầu bằng chứng khác |
| Trạng thái cũ không nhận diện được | QUARANTINED và ghi mã nguyên nhân nội bộ |
| READY có đủ ngữ nghĩa và dữ liệu tương thích | Có thể giữ READY; quyết định cuối vẫn kiểm tra điều kiện hiện thời |

Không nên dùng nhánh mặc định READY cho một enum chưa biết. Nếu thay thế bằng chứng hoặc workflow, cần ánh xạ từng loại bằng chứng và phạm vi của nó; không chỉ đổi tên enum cho giống mô hình mới.

Trạng thái EXPIRED trong cơ sở dữ liệu có thể được cập nhật chậm. Vì vậy, mọi đường chấp nhận token phải tự kiểm tra expires_at. Một hàng chưa được gắn nhãn EXPIRED không có nghĩa là token còn hạn.

## 6. Bảo toàn thời gian và giới hạn lạm dụng

### Hạn dùng là thời điểm tuyệt đối

Giả sử token được phát hành lúc 10:00 và hết hạn lúc 10:15. Migration chạy lúc 10:10 phải giữ mốc 10:15 hoặc rút ngắn theo quyết định chính sách. Nếu đặt expires_at bằng thời điểm migration cộng 15 phút, token sẽ được gia hạn đến 10:25.

Khi áp dụng một giới hạn mới ngắn hơn, có thể thiết kế:

~~~text
effective_expires_at =
    min(original_expires_at, issued_at + new_max_lifetime)
~~~

Công thức chỉ áp dụng khi cả hạn cũ và thời điểm phát hành đều được xác định tin cậy. Không thay giá trị thiếu bằng thời điểm hiện tại. Các thời điểm cần được chuyển đổi theo quy ước múi giờ đã xác định; một timestamp không kèm múi giờ phải có cách diễn giải lịch sử rõ ràng.

Thời điểm consumed_at, revoked_at và verified_at là dấu vết nghiệp vụ. migrated_at là dấu vết kỹ thuật. Không ghi đè nhóm thứ nhất bằng nhóm thứ hai.

### Số lần thử và thời gian chờ không được bắt đầu lại

Nếu một yêu cầu đã dùng 4 trên 5 lần thử, việc chuyển bảng không được đưa attempt_count về 0. Nếu chính sách đích giảm giới hạn xuống 3, yêu cầu đó phải bị chặn theo chính sách áp dụng, thay vì được cấp thêm lượt.

Tương tự, not_before hoặc cooldown_until cần giữ nguyên hoặc tăng mức hạn chế theo quyết định được phê duyệt. Không bỏ thời gian chờ vì schema mới chưa có cột tương ứng.

Nếu bộ đếm trước đây được lưu ở kho khác, cần có kế hoạch duy trì hoặc chuyển quyền quyết định giữa các kho. Không giả định việc copy recovery_record đã chuyển cả dữ liệu chống lạm dụng.

## 7. Triển khai theo expand — migrate — contract

Một cách triển khai minh họa dùng cùng hàng dữ liệu làm nguồn quyết định trong giai đoạn chuyển tiếp.

~~~mermaid
flowchart TD
    A[Thêm cấu trúc đích tương thích] --> B[Triển khai ứng dụng chuyển tiếp]
    B --> C[Loại mọi writer không tương thích]
    C --> D[Backfill theo lô nhỏ]
    D --> E[Chuyển reader sang mô hình đích]
    E --> F[Đối soát trạng thái và quan hệ]
    F --> G[Ngừng hỗ trợ dữ liệu cũ]
    G --> H[Gỡ cấu trúc dư theo kế hoạch]
~~~

### Expand: thêm cấu trúc mà chưa thay nghĩa dữ liệu

Thêm cột đích hoặc bảng đích trước; ứng dụng hiện tại phải tiếp tục hoạt động trong phạm vi tương thích đã thiết kế. Không đổi tên hoặc xóa cột mà một phiên bản đang chạy còn dùng.

Cột trạng thái đích ban đầu có thể để trống và đi kèm migration_version. Reader phải phân biệt rõ hàng chưa được chuyển với hàng bị lỗi. Không dùng COALESCE(state_v2, 'READY').

Trên PostgreSQL 17, CHECK hoặc khóa ngoại có thể thêm bằng NOT VALID rồi xác thực sau bằng VALIDATE CONSTRAINT. NOT VALID vẫn áp dụng với các insert/update tiếp theo; nó không có nghĩa là tạm bỏ kiểm tra cho mọi thao tác. Vẫn cần dự trù khóa DDL và thời gian thực thi. [Nguồn: PostgreSQL 17 ALTER TABLE](https://www.postgresql.org/docs/17/sql-altertable.html).

### Ứng dụng chuyển tiếp: thống nhất mọi đường ghi

Phiên bản chuyển tiếp phải đọc được cả dữ liệu cũ và mới, đồng thời bảo toàn các trường mà reader cũ còn dựa vào. Nếu cần duy trì hai cách biểu diễn trong cùng cơ sở dữ liệu, cập nhật chúng trong cùng transaction.

Phải tính đến API, consumer hàng đợi, công cụ quản trị, tác vụ dọn dữ liệu và handler chạy nền. Một consumer cũ còn sống vẫn có thể ghi trạng thái lạc hậu sau khi backfill đã hoàn tất.

Trong thiết kế của bài, chỉ bắt đầu backfill sau khi mọi writer không tương thích đã dừng. Có thể dùng cơ chế khác như trigger hoặc change data capture, nhưng cơ chế đó cần được thiết kế đầy đủ; việc chỉ sao chép dữ liệu định kỳ không tự giải quyết được ghi đồng thời.

### Migrate: chuyển từng lô có thể tiếp tục

Mỗi lô nên có transaction ngắn, số hàng giới hạn và điều kiện chọn chỉ các hàng chưa chuyển. Ghi marker hoàn thành cùng transaction với dữ liệu đích. Nếu transaction rollback, lô đó vẫn có thể được chọn lại.

Điểm tiếp tục của tiến trình giúp tránh quét lại quá nhiều dữ liệu, nhưng không phải bằng chứng rằng mọi hàng trước cursor đã xong. Các hàng từng bị khóa hoặc lỗi cần được quét lại theo migration_version.

### Contract: ngừng chấp nhận mô hình cũ

Chỉ loại bỏ cột, parser hoặc khóa cũ sau khi không còn ứng dụng cần chúng và không còn token hợp lệ phụ thuộc vào chúng, trừ trường hợp đã chủ động thu hồi.

Một cửa sổ hỗ trợ định dạng cũ phải có thời hạn và quy tắc từ chối rõ ràng. Nếu dữ liệu lịch sử có hạn dùng không xác định, không nên lấy “chờ thêm một khoảng thời gian” làm bằng chứng rằng mọi quyền cũ đã hết hiệu lực.

## 8. Ví dụ backfill có khóa và giữ nguyên dữ liệu quyết định quyền

Ví dụ dưới đây dành cho PostgreSQL 17, trên một bảng đã tồn tại. Đây là SQL minh họa để hiểu thiết kế, không phải một script hoàn chỉnh cho mọi hệ thống.

Giả sử bảng recovery_record đã có:

- id, tenant_id, account_id, purpose.
- legacy_status, issued_at, expires_at, consumed_at, revoked_at.
- token_digest, token_format, key_id, security_epoch.
- attempt_count, attempt_limit.

Các timestamp dùng kiểu timestamp with time zone. legacy_status = READY đã được xác định rõ là hoàn tất các bước xác minh của **luồng đặt lại mật khẩu cũ**. Các writer chuyển tiếp đã được triển khai trước khi chạy backfill.

### Thêm các trường chuyển đổi

~~~sql
ALTER TABLE recovery_record
    ADD COLUMN state_v2 text,
    ADD COLUMN migration_version smallint NOT NULL DEFAULT 1,
    ADD COLUMN row_version bigint NOT NULL DEFAULT 0;
~~~

Ứng dụng chuyển tiếp phải ghi migration_version = 2 cùng state_v2 hợp lệ cho hàng mới. Default 1 chỉ giúp phân loại dữ liệu chưa chuyển; nó không là giá trị phát hành mặc định của ứng dụng mới.

### Chuyển một lô trong một transaction

~~~sql
BEGIN;

WITH batch AS (
    SELECT id
    FROM recovery_record
    WHERE migration_version = 1
    ORDER BY id
    LIMIT 200
    FOR UPDATE SKIP LOCKED
)
UPDATE recovery_record AS r
SET state_v2 = CASE
        WHEN r.consumed_at IS NOT NULL
             OR r.legacy_status = 'CONSUMED'
            THEN 'CONSUMED'
        WHEN r.revoked_at IS NOT NULL
             OR r.legacy_status = 'REVOKED'
            THEN 'REVOKED'
        WHEN r.issued_at IS NULL
             OR r.expires_at IS NULL
             OR r.expires_at <= r.issued_at
            THEN 'QUARANTINED'
        WHEN r.expires_at <= statement_timestamp()
            THEN 'EXPIRED'
        WHEN r.legacy_status = 'PENDING'
            THEN 'PENDING'
        WHEN r.legacy_status = 'READY'
             AND r.tenant_id IS NOT NULL
             AND r.account_id IS NOT NULL
             AND r.purpose = 'PASSWORD_RESET'
             AND r.token_digest IS NOT NULL
             AND octet_length(r.token_digest) = 32
             AND r.token_format = 'HMAC_SHA256_V1'
             AND r.key_id IS NOT NULL
             AND r.security_epoch IS NOT NULL
             AND r.attempt_count >= 0
             AND r.attempt_limit > 0
             AND r.attempt_count < r.attempt_limit
            THEN 'READY'
        ELSE 'QUARANTINED'
    END,
    migration_version = 2,
    row_version = r.row_version + 1
FROM batch
WHERE r.id = batch.id
  AND r.migration_version = 1
RETURNING r.id, r.state_v2, r.migration_version;

COMMIT;
~~~

Lô này chỉ chuyển cách biểu diễn trạng thái và marker kỹ thuật. Nó không sửa expires_at, tenant_id, account_id, purpose, digest, epoch, số lần thử hoặc các dấu vết kết thúc.

Nhánh READY cố ý chỉ áp dụng cho hợp đồng đặt lại mật khẩu đã nêu. Với recovery thay MFA hoặc passkey, cần một ánh xạ có đầy đủ điều kiện riêng; không mở rộng danh sách purpose rồi mặc định xem đó là đủ xác minh.

Kiểm tra độ dài digest và tên định dạng chỉ kiểm tra cấu trúc, chưa xác minh token, tính sẵn có của khóa hay trạng thái tài khoản. READY vẫn phải qua bộ xử lý nghiệp vụ hiện tại trước khi được dùng.

Theo tài liệu PostgreSQL, SKIP LOCKED bỏ qua các hàng không khóa được ngay và không cung cấp góc nhìn nhất quán cho truy vấn tổng quát. Ở đây nó chỉ phục vụ chia lô công việc. Một lô trả về 0 hàng không chứng minh toàn bộ migration đã hoàn tất vì có thể vẫn còn hàng đang bị khóa. [Nguồn: PostgreSQL 17 SELECT — Locking Clause](https://www.postgresql.org/docs/17/sql-select.html).

Nếu một transaction sử dụng token đang giữ khóa hàng, lô migration sẽ bỏ qua hàng đó. Nếu migration giữ khóa trước, handler sử dụng token phải chờ rồi đánh giá lại dữ liệu hiện thời. Hiệu quả này chỉ có khi mọi writer cùng tuân thủ hợp đồng cập nhật; nó không sửa được một writer cũ ghi đè dữ liệu sau đó.

### Ràng buộc trạng thái và marker

Sau khi ứng dụng đã tương thích, có thể bổ sung ràng buộc minh họa:

~~~sql
ALTER TABLE recovery_record
ADD CONSTRAINT recovery_record_state_v2_check
CHECK (
    migration_version IN (1, 2)
    AND (
        (migration_version = 1 AND state_v2 IS NULL)
        OR
        (
            migration_version = 2
            AND state_v2 IS NOT NULL
            AND state_v2 IN (
                'PENDING', 'READY', 'CONSUMED',
                'REVOKED', 'EXPIRED', 'QUARANTINED'
            )
        )
    )
) NOT VALID;

ALTER TABLE recovery_record
VALIDATE CONSTRAINT recovery_record_state_v2_check;
~~~

Điều kiện state_v2 IS NOT NULL được viết tường minh. Không dựa riêng vào biểu thức IN để loại NULL trong CHECK. Ràng buộc này chỉ bảo vệ hình dạng trạng thái; cần thêm ràng buộc và kiểm tra nghiệp vụ phù hợp cho định danh, bằng chứng và việc chuyển trạng thái.

Nếu nguồn có dữ liệu mâu thuẫn, việc cách ly phải giữ được mã nguyên nhân và bằng chứng lịch sử cần thiết theo chính sách lưu trữ. Không ghi raw token vào bảng lỗi để tiện điều tra.

## 9. Tính dùng một lần trong lúc migration đang chạy

Backfill an toàn không thay thế tính nguyên tử của thao tác hoàn tất recovery. Bộ xử lý vẫn cần một transaction quyết định quyền và thay đổi tài khoản.

Một trình tự minh họa là:

1. Xác định tài khoản từ liên kết đáng tin cậy; khóa hàng tài khoản theo thứ tự thống nhất.
2. Khóa recovery record và đọc dữ liệu mới nhất.
3. Chọn đúng bộ diễn giải theo migration_version và token_format.
4. Kiểm tra tenant, account, purpose, token, hạn dùng, bằng chứng, giới hạn thử, thời gian chờ và security_epoch hiện tại.
5. Nếu đủ điều kiện, thay đổi credential được phép và đánh dấu quyền đã dùng trong cùng transaction.
6. Áp dụng chính sách tăng epoch, vô hiệu hóa quyền cũ hoặc ghi yêu cầu thu hồi session; nếu cần dịch vụ ngoài, dùng cơ chế giao việc bền vững phù hợp.
7. Commit trước khi phát sinh tác dụng phụ bên ngoài như thông báo.

Mọi thao tác làm thay đổi epoch cũng phải dùng quy tắc đồng bộ tương thích. Chỉ đọc epoch rồi bỏ khóa trước khi dùng token vẫn có thể để lọt thay đổi đồng thời.

Nếu cập nhật có điều kiện bằng row_version, kết quả 0 hàng nghĩa là phải đọc lại và đánh giá lại hoặc từ chối theo hợp đồng. Không tiếp tục đổi credential dựa trên dữ liệu đã đọc trước đó.

Với session ở dịch vụ ngoài, việc commit một outbox event chưa đồng nghĩa mọi session đã bị thu hồi. Cần quy định cách chặn truy cập trong khoảng chờ, chẳng hạn kiểm tra epoch khi dùng session. Migration không được đánh dấu tác dụng phụ đó là đã xong.

Backfill không gọi lại handler “hoàn tất recovery”. Nếu gọi handler để tiện tái sử dụng code, nó có thể vô tình đổi mật khẩu, phát session, gửi email hoặc tăng epoch cho hàng loạt tài khoản.

## 10. Khi nguồn và đích là hai bảng hoặc hai hệ thống

Hai bản sao độc lập không được cùng có quyền cho phép sử dụng token. Nếu một reader chấp nhận khi **nguồn cũ hoặc nguồn mới** còn READY, một bản sao chậm cập nhật có thể làm sống lại quyền đã dùng.

Cần xác định quyền quyết định theo từng giai đoạn:

| Giai đoạn | Nguồn quyết định | Yêu cầu |
| --- | --- | --- |
| Đang sao chép | Nguồn cũ | Đích chỉ là bản sao, không tự cấp quyền |
| Bắt kịp thay đổi | Nguồn cũ | Áp dụng cả consume, revoke, expire và sự kiện xóa |
| Chuyển quyền | Được xác định bằng cơ chế chuyển giao | Chặn writer cũ, đồng bộ đến mốc chuyển giao và loại đường chấp nhận cũ |
| Sau chuyển quyền | Nguồn mới | Retry, consumer chậm và reader cũ không thể cấp quyền từ nguồn cũ |

Cơ chế chuyển giao có thể dùng một khoảng dừng ghi có kiểm soát hoặc một giao thức quản lý quyền ghi rõ ràng. Nếu liên quan nhiều dịch vụ, cần xử lý cả request đang bay, cache và consumer giữ dữ liệu cũ.

Dual-write sang hai hệ thống theo hai lệnh độc lập có khoảng lỗi: nguồn cập nhật CONSUMED thành công nhưng đích vẫn READY. Outbox hoặc CDC hỗ trợ truyền thay đổi bền vững, song không tự tạo ra tính dùng một lần xuyên hai nơi nếu cả hai nơi vẫn được phép quyết định.

Ngoài hàng đang tồn tại, phải chuyển được ý nghĩa của việc xóa hoặc thu hồi. Nếu nguồn xóa bản ghi còn đích không nhận tombstone, bản sao đích có thể tồn tại như một quyền cũ chưa bị chặn.

## 11. Token format, khóa và dữ liệu nhạy cảm

### Không thể tùy ý đổi digest khi không có token gốc

Nếu cơ sở dữ liệu chỉ giữ HMAC của token, không thể tính HMAC mới với khóa mới chỉ từ HMAC cũ. Tương tự, hash thêm một digest cũ không tự tương đương với cách verifier mới xử lý raw token.

Một thiết kế chuyển tiếp có thể lưu token_format và key_id, tiếp tục kiểm tra định dạng cũ trong thời hạn đã giới hạn, đồng thời phát hành yêu cầu mới bằng định dạng mới.

Giữ khả năng đọc định dạng cũ chỉ phù hợp khi thiết kế và khóa cũ còn được xem là an toàn. Nếu khóa bị lộ hoặc định dạng cũ không đáp ứng yêu cầu, phải thu hồi các quyền liên quan và yêu cầu bắt đầu lại, thay vì duy trì tương thích bằng mọi giá.

Không bỏ qua kiểm tra digest khi gặp định dạng chưa biết. Không thử mọi khóa sẵn có mà không có hợp đồng chọn khóa và giới hạn rõ ràng.

### Mã hóa lại cần bảo toàn liên kết

Với evidence được mã hóa, quá trình đổi khóa phải được thiết kế như một thao tác mật mã riêng: quyền truy cập tối thiểu, plaintext chỉ tồn tại trong phạm vi cần thiết và không đưa vào log.

Nếu dùng mã hóa có xác thực với dữ liệu liên kết như tenant_id, account_id, purpose hoặc record_id, phải giữ hoặc chuyển dữ liệu liên kết theo giao thức tương thích. Chỉ copy ciphertext sang một định danh mới có thể khiến không giải mã được hoặc làm sai liên kết bảo mật.

Không coi key_id mới là bằng chứng dữ liệu đã được mã hóa lại. Chỉ đổi marker sau khi có dữ liệu đích và xác nhận kỹ thuật tương ứng.

## 12. Retry, idempotency và sự cố giữa chừng

Một batch cần cho phép chạy lại mà không tự tạo thêm quyền. Trong ví dụ, điều kiện migration_version = 1 ngăn áp dụng lại cùng phép chuyển trên hàng đã hoàn tất.

Các tình huống cần được thiết kế rõ:

| Sự cố | Hành vi cần có |
| --- | --- |
| Tiến trình chết trước commit | Transaction rollback; hàng vẫn có thể được chọn lại |
| Commit xong nhưng tiến trình chưa ghi nhận kết quả | Lần chạy sau bỏ qua hàng đã có marker đích |
| Hàng bị handler recovery khóa | Batch bỏ qua hoặc chờ theo chính sách; quay lại xử lý sau |
| Phát hiện dữ liệu không đủ tin cậy | Cách ly, giữ nguyên dấu vết và không phát hành quyền thay thế |
| Consumer cũ chạy lại sau chuyển quyền | Bị ngăn ghi hoặc ngăn cấp quyền theo cơ chế chuyển giao |
| Log hoặc báo cáo lỗi không gửi được | Không lặp lại tác dụng phụ nghiệp vụ; trạng thái nguồn vẫn quyết định |

Idempotency của migration khác với idempotency của API hoàn tất recovery. Migration chạy lại không được tạo thêm email, reset credential hay phát thêm session, kể cả khi API nghiệp vụ hỗ trợ khóa idempotency.

Nếu marker bị ghi trước dữ liệu đích trong hai transaction khác nhau, tiến trình có thể bỏ sót một hàng chưa chuyển xong. Marker và dữ liệu tương ứng phải commit cùng nhau hoặc có giao thức phục hồi được định nghĩa rõ.

## 13. Rollback không được đảo ngược sự kiện bảo mật

Rollback phần mềm và khôi phục dữ liệu là hai việc khác nhau.

Có thể quay lại phiên bản chuyển tiếp đã biết cách đọc dữ liệu đích. Không nên quay về một bản ứng dụng không hiểu trạng thái mới nhưng vẫn có quyền ghi hoặc chấp nhận token.

Một token đã bị tiêu thụ trong thời gian triển khai phải tiếp tục bị chặn sau rollback. Tương tự, việc thu hồi, thay epoch, tăng số lần thử và thay credential không được bị đảo ngược chỉ vì muốn quay lại schema cũ.

Khôi phục snapshot cơ sở dữ liệu có thể làm mất những sự kiện xảy ra sau snapshot. Với recovery, điều đó có thể làm token cũ sống lại. Kế hoạch phục hồi cần đối soát các sự kiện bảo mật hoặc vô hiệu hóa những quyền bị ảnh hưởng trước khi mở lại đường sử dụng.

Không rollback bằng cách đổi hàng loạt CONSUMED thành READY, xóa revoked_at hoặc đặt lại bộ đếm. Nếu không thể diễn giải an toàn một tập dữ liệu sau phục hồi, chặn tập đó và hướng người dùng qua quy trình recovery mới.

## 14. Ví dụ diễn biến thời gian

Một yêu cầu đặt lại mật khẩu có các dữ kiện:

~~~text
record_id          = R-42
purpose            = PASSWORD_RESET
issued_at          = 10:00
expires_at         = 10:15
security_epoch     = 7
attempt_count      = 2
attempt_limit      = 5
legacy_status      = READY
~~~

Lúc 10:10, backfill chuyển hàng sang mô hình mới. Kết quả vẫn có expires_at = 10:15, epoch = 7 và attempt_count = 2. migration_version thay đổi nhưng bằng chứng xác minh không được tạo thêm.

Lúc 10:11, một request sử dụng token thành công. Trong transaction nghiệp vụ, hệ thống thay mật khẩu, đánh dấu CONSUMED và cập nhật trạng thái bảo mật tài khoản theo chính sách.

Lúc 10:12, tiến trình migration chạy lại sau sự cố. Nó không xử lý lại hàng đã chuyển và không sửa dấu vết consumed. Một reader tương thích cũng phải từ chối token này.

Nếu lúc 10:09 tài khoản đã đổi epoch từ 7 sang 8 vì một sự kiện bảo mật, bản ghi dù còn hạn vẫn phải bị từ chối khi sử dụng. Migration không được điền epoch = 8 vào hàng chỉ để khớp tài khoản hiện tại.

Nếu đến 10:16 chưa có ai sử dụng token, đường hoàn tất recovery phải từ chối vì hết hạn, kể cả khi trạng thái lưu trong hàng vẫn chưa đổi từ READY sang EXPIRED.

## 15. Quan sát kết quả chuyển đổi

Trong vận hành, số lượng hàng đã chuyển cần đi kèm các chỉ dấu về ý nghĩa dữ liệu:

- Số hàng còn migration_version cũ, bao gồm hàng từng bị khóa.
- Số hàng bị cách ly theo mã nguyên nhân.
- Số hàng có trạng thái kết thúc ở nguồn nhưng có khả năng được chấp nhận tại đích.
- Số hàng có hạn dùng đích dài hơn hạn gốc.
- Số hàng thiếu hoặc sai liên kết tenant, account, purpose.
- Số lỗi chọn token_format, key_id hoặc đọc evidence.
- Writer cũ, độ trễ truyền thay đổi, lỗi khóa và tải cơ sở dữ liệu.

Không đưa token, mã OTP, đường dẫn reset đầy đủ hoặc tài liệu định danh vào metric label. Các định danh nội bộ trong báo cáo cũng cần giới hạn quyền truy cập và thời hạn lưu.

Hoàn thành chuyển đổi cần có bằng chứng rằng các hàng đã được xử lý, mọi đường ghi và đọc đều theo hợp đồng đích, các trạng thái kết thúc vẫn bị chặn, và quyền quyết định đã chuyển rõ ràng. Tổng số hàng bằng nhau chỉ chứng minh một phần của việc sao chép dữ liệu.

Nguyên tắc xuyên suốt là: **thay cách lưu trữ không tự thay đổi điều người dùng đã chứng minh, thời gian quyền còn hiệu lực hoặc việc quyền đó đã được sử dụng**.

