# Concurrent recovery attempts — Xử lý các lần khôi phục đồng thời

Hai lần bấm nút, hai tab, hai thiết bị hoặc hai người khác nhau có thể cùng thao tác trên một tài khoản. Trong khôi phục tài khoản, đây không chỉ là chuyện giao diện gửi trùng: hai request có thể cùng nhìn thấy token chưa dùng và cùng thay đổi mật khẩu, MFA hoặc passkey.

Bài này thuộc module SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY. Trọng tâm là cách persistence bảo vệ các bất biến khi nhiều luồng khôi phục cùng chạy. Các bảng và chính sách dưới đây là mô hình minh họa, không phải schema bắt buộc của module hoặc một quy định chung cho mọi sản phẩm.

## 1. Nhận diện các kiểu đồng thời

| Tình huống | Điểm tranh chấp |
| --- | --- |
| Một token được gửi hai lần | Quyền sử dụng một lần của token |
| Hai token khác nhau thuộc một request | Trạng thái hoàn tất của request |
| Hai request cùng khôi phục một tài khoản | Quyền thay đổi credential và trạng thái bảo mật tài khoản |
| Gửi lại mã trong lúc xác minh mã cũ | Phiên bản challenge và chính sách hiệu lực |
| Hủy trong lúc hoàn tất | Chuyển trạng thái cuối của request |
| Cùng đoán sai mã nhiều lần | Bộ đếm và giới hạn thử |
| Mất phản hồi sau commit | Phân biệt retry với một thao tác thay đổi mới |
| Hai instance ứng dụng cùng xử lý | Cơ chế đồng bộ phải vượt phạm vi một process |

Khóa một hàng token không giải quyết được mọi hàng trong bảng. Nếu hai request dùng hai token khác nhau, chúng có thể không tranh chấp ở token nhưng vẫn cùng cập nhật tài khoản.

Đầu tiên cần xác định **tài nguyên nào chỉ được có một người thắng tại một thời điểm**.

## 2. Viết bất biến trước khi chọn khóa

Trong thiết kế minh họa, hệ thống giữ các điều kiện sau:

1. Một bí mật dùng một lần chỉ tạo được một lần chuyển trạng thái hợp lệ.
2. Một request không thể vừa hoàn tất vừa bị hủy như hai kết quả cùng có hiệu lực.
3. Grant cho request này không được dùng cho request hoặc action khác.
4. Một lần hoàn tất thành công làm mất hiệu lực các recovery context cũ của cùng tài khoản.
5. Tiêu thụ quyền và thay đổi credential phải có ranh giới nguyên tử phù hợp.
6. Retry của thao tác cũ không được biến thành một lần đặt credential mới.
7. Thông báo thành công chỉ dựa trên kết quả đã được ghi nhận, không dựa trên số request đã gửi.

Điều 4 là lựa chọn của bài: nhiều request có thể đang chờ, nhưng chỉ một lần hoàn tất được phép dựa trên cùng một phiên bản bảo mật. Sản phẩm khác có thể chọn chính sách khác; nó vẫn phải mô tả rõ hành vi mong muốn.

OWASP khuyến nghị token khôi phục dùng một lần, có hạn sử dụng và được lưu an toàn. Tính dùng một lần phải tồn tại cả khi hai request đến đồng thời. [OWASP: Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

Không dùng “người dùng bình thường sẽ không bấm hai lần” làm giả định bảo mật. Attacker có thể chủ động tạo request song song để khai thác khoảng giữa kiểm tra và ghi.

## 3. Vì sao đọc rồi ghi riêng rẽ không đủ?

Một triển khai dễ sai:

```text
A: đọc token → chưa dùng
B: đọc token → chưa dùng
A: đổi mật khẩu thành P1
B: đổi mật khẩu thành P2
A: đánh dấu token đã dùng
B: đánh dấu token đã dùng
```

Kết quả cuối có thể là P2, trong khi cả A và B đều nhận thông báo thành công. Có một token nhưng đã có hai lần thay đổi.

Các kiểu code có cùng vấn đề:

```java
// Minh họa cách làm không đủ an toàn khi chạy đồng thời.
Token token = tokenRepository.findById(tokenId);

if (!token.isUsed()) {
    passwordRepository.changePassword(accountId, newPasswordHash);
    tokenRepository.markUsed(tokenId);
}
```

Đặt các câu lệnh trong transaction cũng chưa tự giải quyết mọi tranh chấp. Cần biết mức cô lập, khóa và điều kiện cập nhật đang bảo vệ điều gì.

Ở PostgreSQL Read Committed, một SELECT thông thường nhìn dữ liệu đã commit tại thời điểm câu lệnh bắt đầu; không mặc nhiên khóa hàng để bảo vệ quyết định ở câu lệnh tiếp theo. [PostgreSQL: Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html)

Đừng thay bằng một cờ `processing` trong bộ nhớ Java. Cờ đó không bảo vệ được trước instance khác, restart hoặc một đường code không sử dụng cùng cờ.

## 4. Tách cấp token, request và tài khoản

Mô hình dữ liệu rút gọn:

| Thành phần | Dữ liệu liên quan đến đồng thời |
| --- | --- |
| `account_security` | `account_id`, `recovery_epoch`, `session_epoch`, credential của ví dụ |
| `recovery_request` | `id`, `account_id`, `action`, `state`, `expected_recovery_epoch`, `expires_at` |
| `recovery_challenge` | Bằng chứng cần xác minh, phiên bản, số lần thử, trạng thái |
| `recovery_grant` | Quyền thực thi đã được cấp, request, purpose, verifier, trạng thái, hạn dùng |
| Biên nhận thao tác | Định danh thao tác đã hoàn tất và kết quả được phép đọc |
| Outbox | Sự kiện cần gửi sau khi thay đổi được commit |

Ở đây, challenge chứng minh một điều kiện; grant cho phép thực hiện một thay đổi cụ thể sau khi policy đã chấp nhận.

Nếu xác minh OTP chỉ là bước để cấp grant, cần tiêu thụ OTP và ghi kết quả tương ứng trong một ranh giới phù hợp. Không coi “OTP từng đúng” là một quyền không giới hạn cho mọi lần hoàn tất sau đó.

### Recovery epoch

`recovery_epoch` là số phiên bản bảo mật do máy chủ quản lý.

Ví dụ:

```text
Tài khoản: recovery_epoch = 12
Request R1: expected_recovery_epoch = 12
Request R2: expected_recovery_epoch = 12

R1 hoàn tất:
    cập nhật credential
    recovery_epoch = 13

R2 tiếp tục:
    12 != 13
    → context cũ không còn được phép hoàn tất
```

Không tăng epoch chỉ vì một người lạ nhập email vào form. Làm vậy có thể cho phép kẻ khác liên tục vô hiệu hóa yêu cầu hợp lệ của chủ tài khoản.

Epoch cũng không tự thu hồi quyền nếu các endpoint không kiểm tra nó. Mọi đường sử dụng recovery context phải thực thi cùng quy ước.

## 5. Chọn ranh giới tranh chấp dùng chung

Với mô hình một cơ sở dữ liệu, có thể dùng hàng `account_security` làm điểm đồng bộ cho các thay đổi recovery trên cùng tài khoản.

Thứ tự khóa minh họa:

```text
account_security
    → recovery_request
        → recovery_challenge hoặc recovery_grant
```

Các luồng phát hành, hoàn tất, hủy và thay đổi trạng thái bảo mật cần tuân thủ giao thức phù hợp với phần dữ liệu mà chúng sửa.

`SELECT ... FOR UPDATE` trong PostgreSQL khóa những hàng đã chọn và ngăn các writer hoặc locker xung đột đến khi transaction kết thúc. Nó không chặn mọi SELECT thông thường. [PostgreSQL: Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)

Các giới hạn cần hiểu:

- Khóa request R1 không khóa R2.
- SELECT không tìm thấy hàng không tạo ra một khóa hàng cho đối tượng chưa tồn tại.
- Một lock cục bộ trong Java không thay thế khóa hoặc điều kiện tại nơi ghi dữ liệu.
- Redis lock có thể hỗ trợ điều phối nhưng không tự làm các ghi database trở nên nguyên tử.
- Một tiến trình khác bỏ qua giao thức khóa vẫn có thể phá giả định của thiết kế.

Khóa tài khoản giúp giải thích tính đúng của ví dụ, nhưng có thể tạo điểm nóng. Không đặt cuộc gọi gửi email, chờ nhân viên hoặc tính toán chậm trong khi đang giữ khóa đó.

## 6. Ví dụ hoàn tất đặt lại mật khẩu bằng transaction ngắn

Ví dụ này dành cho `RESET_PASSWORD` và một grant đã được policy cấp với purpose `RESET_PASSWORD_COMMIT`. Nó không giả định rằng biết email hoặc nhập đúng một loại mã bất kỳ là đã đủ điều kiện.

Các bảng dưới đây là bảng giả định, chưa phải migration hoàn chỉnh. Các tham số được bind; giá trị credential và bí mật không được ghép vào SQL hoặc ghi log.

Trước transaction có thể:

- Kiểm tra hình thức dữ liệu và giới hạn yêu cầu.
- Tìm các định danh sơ bộ từ grant để xác định account cần khóa.
- Tính hash mật khẩu mới bằng cơ chế phù hợp sau các kiểm tra ban đầu cần thiết.

Những bước đó không thay thế xác thực lại grant và trạng thái bên trong transaction. Không tin `account_id` do client tự khai.

### 6.1. Khóa và đọc lại trạng thái

```sql
BEGIN;

SELECT account_id, recovery_epoch, session_epoch
FROM account_security
WHERE account_id = :accountId
FOR UPDATE;

SELECT id, account_id, action, state,
       expected_recovery_epoch, expires_at
FROM recovery_request
WHERE id = :requestId
  AND account_id = :accountId
FOR UPDATE;

SELECT id, request_id, purpose, secret_verifier,
       state, expires_at
FROM recovery_grant
WHERE id = :grantId
  AND request_id = :requestId
FOR UPDATE;

SELECT clock_timestamp() AS checked_at;
```

Sau khi có khóa, service kiểm tra:

1. Các quan hệ account, request và grant đúng như dự kiến.
2. Người gọi có ngữ cảnh và bí mật hợp lệ.
3. Action và purpose phù hợp.
4. Request đang ở trạng thái cho phép hoàn tất.
5. Grant chưa dùng hoặc bị thu hồi.
6. Epoch của request khớp epoch hiện tại.
7. Request, grant và các điều kiện policy vẫn còn hiệu lực.

Trong ví dụ, `checked_at` được lấy sau khi đã chờ các khóa và được bind lại thành `:checkedAt` cho phần ghi tiếp theo.

### 6.2. Tiêu thụ grant và ghi credential

```sql
UPDATE recovery_grant
SET state = 'CONSUMED',
    consumed_at = :checkedAt
WHERE id = :grantId
  AND request_id = :requestId
  AND purpose = 'RESET_PASSWORD_COMMIT'
  AND state = 'ACTIVE'
  AND expires_at > :checkedAt;
```

Service yêu cầu số hàng cập nhật bằng 1. Nếu bằng 0, dừng và rollback; không tiếp tục đổi mật khẩu.

```sql
UPDATE account_security
SET password_hash = :newPasswordHash,
    recovery_epoch = recovery_epoch + 1,
    session_epoch = session_epoch + 1
WHERE account_id = :accountId
  AND recovery_epoch = :expectedRecoveryEpoch;
```

Tiếp tục yêu cầu đúng 1 hàng. Trong ví dụ này, tăng `session_epoch` biểu diễn chính sách làm mất hiệu lực session cũ. Nó chỉ có tác dụng nếu cơ chế kiểm tra session thật sự đối chiếu epoch; không tự khiến mọi session đang tồn tại biến mất.

```sql
UPDATE recovery_request
SET state = 'COMPLETED',
    completed_at = :checkedAt
WHERE id = :requestId
  AND account_id = :accountId
  AND action = 'RESET_PASSWORD'
  AND state = 'AUTHORIZED'
  AND expected_recovery_epoch = :expectedRecoveryEpoch
  AND expires_at > :checkedAt;
```

Service lại yêu cầu đúng 1 hàng. Sau đó ghi biên nhận và sự kiện cần thiết trong cùng transaction rồi commit.

```text
INSERT biên nhận thao tác hoàn tất
INSERT sự kiện outbox không chứa bí mật
COMMIT
```

Các câu kiểm tra row count là một phần bắt buộc của ví dụ, không phải chú thích có thể bỏ khi triển khai.

### 6.3. Ý nghĩa nguyên tử

Nếu ghi credential hoặc request thất bại, rollback phục hồi cả việc tiêu thụ grant trong cùng transaction. Người dùng không bị mất grant chỉ vì một cập nhật phía sau chưa thành công.

Nếu commit thành công, grant đã dùng, request đã hoàn tất và epoch đã tăng cùng nhau. Không có khoảng đã commit mà credential mới có hiệu lực nhưng grant vẫn được coi là chưa dùng.

Ví dụ định nghĩa hạn sử dụng tại thời điểm kiểm tra tiêu thụ sau khi có khóa. Nếu chính sách yêu cầu một ranh giới thời gian khác, cần thực thi rõ ràng; không suy từ thời điểm trình duyệt gửi request.

## 7. Hai request khác nhau: vì sao cần epoch?

Giả sử R1 và R2 đều có grant riêng, cùng được tạo ở epoch 12.

| Trình tự | Transaction T1 của R1 | Transaction T2 của R2 |
| --- | --- | --- |
| 1 | Khóa account ở epoch 12 | Chờ khóa account |
| 2 | Kiểm tra R1 và grant G1 | Chưa được quyết định từ trạng thái cũ |
| 3 | Đổi credential, tăng epoch thành 13, commit | Tiếp tục sau khi có khóa |
| 4 | Hoàn tất | Đọc epoch 13 |
| 5 | — | Từ chối context R2 vốn dựa trên epoch 12 |

Hai token có thể đều chưa dùng về mặt riêng lẻ, nhưng chỉ một recovery context cũ được phép thay đổi tài khoản.

Các request cũ có thể vẫn còn state lưu trữ là `AUTHORIZED` nếu hệ thống không cập nhật hàng loạt. Khi đó hiệu lực phải được tính từ cả state, hạn dùng và epoch. Tác vụ dọn dẹp có thể cập nhật trạng thái hiển thị sau; nó không được là cơ chế duy nhất ngăn sử dụng.

Không cần khóa rồi cập nhật mọi request cũ trong transaction nếu chính sách epoch đã được thực thi nhất quán. Việc cập nhật hàng loạt có thể tăng thời gian giữ khóa và gây thêm tranh chấp.

Nếu các action được phép độc lập, sản phẩm có thể cần phiên bản theo phạm vi thay vì một epoch chung. Đó là thay đổi chính sách, không chỉ là tối ưu kỹ thuật; phải xét quan hệ giữa đổi mật khẩu, rebind MFA và thay đổi kênh recovery.

## 8. Một request, nhiều challenge và gửi lại mã

Nút “Gửi lại” có thể được bấm khi mã trước vẫn đang được xác minh.

Có nhiều chính sách hợp lệ, nhưng persistence phải biết chính sách nào đang áp dụng:

| Chính sách | Điều cần kiểm soát |
| --- | --- |
| Chỉ mã mới nhất dùng được | Phiên bản challenge hiện hành và việc thay thế nguyên tử |
| Nhiều mã cùng còn hiệu lực | Giới hạn phát hành, số lần thử và chỉ một lần hoàn tất |
| Gửi lại cùng hướng dẫn trong giới hạn | Chống tạo nhiều bí mật hoặc side effect ngoài dự kiến |

Nếu dùng “mã mới nhất”, xác minh mã cũ phải đối chiếu phiên bản sau khi đồng bộ với thao tác phát hành mã mới. Không để một thread xác minh bằng dữ liệu cache rồi cấp grant sau khi challenge đã bị thay thế.

Cũng cần đánh giá nguy cơ từ chối dịch vụ: nếu bất kỳ ai biết email đều có thể phát hành mã mới và lập tức vô hiệu hóa mã cũ, attacker có thể cản trở người dùng. Không chọn chính sách này chỉ vì nó dễ viết SQL.

### Mã dự phòng dùng chung cho tài khoản

Một saved recovery code có thể được gửi qua R1 và R2 cùng lúc. Chỉ khóa từng request không đủ; cả hai đang sử dụng cùng bí mật.

Sau khi kiểm tra bí mật theo cơ chế phù hợp, có thể dùng một chuyển trạng thái có điều kiện:

```sql
UPDATE saved_recovery_code
SET consumed_at = :checkedAt
WHERE id = :codeId
  AND account_id = :accountId
  AND consumed_at IS NULL
RETURNING id;
```

Chỉ đường nhận được một hàng mới được ghi nhận bằng chứng sử dụng code. Việc tiêu thụ code và ghi kết quả xác minh cần cùng ranh giới transaction phù hợp.

Câu SQL không tự xác minh giá trị code hoặc quyền account. Không nhận `codeId` từ client rồi coi đó là đủ để tiêu thụ và cấp bằng chứng.

## 9. Tạo request đồng thời và ràng buộc duy nhất

Một lỗi thường gặp ở bước tạo:

```text
T1: đếm request đang hoạt động → 0
T2: đếm request đang hoạt động → 0
T1: insert R1
T2: insert R2
```

Nếu chính sách chỉ cho một request mở theo account và action, kết quả đã vi phạm chính sách.

Có thể dùng một điểm đồng bộ chung hoặc ràng buộc duy nhất thích hợp. Ví dụ tùy chọn:

```sql
CREATE UNIQUE INDEX uq_one_open_recovery_request
ON recovery_request (account_id, action)
WHERE state IN ('REQUESTED', 'VERIFYING', 'AUTHORIZED');
```

PostgreSQL hỗ trợ unique partial index để bảo đảm duy nhất cho những hàng thỏa predicate. [PostgreSQL: Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html)

Index này **chỉ phù hợp chính sách một request mở**, không phải mô hình nhiều request cùng chờ của ví dụ epoch ở trên. Không áp dụng cả hai mà không xem lại hành vi sản phẩm.

Các giới hạn:

- State lưu trữ chưa đổi sẽ tiếp tục chiếm vị trí dù deadline đã qua.
- Không dùng một predicate phụ thuộc đồng hồ như `expires_at > now()` để mong index tự thay đổi khi thời gian trôi.
- Cần chuyển trạng thái hết hạn hoặc thay thế theo transaction thích hợp trước khi tạo mới.
- Unique violation phải được ánh xạ thành hành vi phù hợp, không phải luôn trả lỗi kỹ thuật.
- Không lấy thông báo xung đột làm kênh tiết lộ account tồn tại.

Nếu cho nhiều request mở, cần giới hạn số lượng và chống lạm dụng. Không dùng “không có unique index” làm lý do cho phép phát hành vô hạn.

## 10. Bộ đếm thử sai cũng là dữ liệu tranh chấp

Một bộ đếm kiểu đọc 4 rồi ghi 5 có thể mất cập nhật khi hai request cùng chạy. Khi đó hệ thống cho nhiều lần thử hơn chính sách.

Cần đồng bộ việc:

1. Đọc trạng thái challenge và số lần còn được thử.
2. Quyết định có cho kiểm tra tiếp.
3. Ghi nhận kết quả sai và tăng bộ đếm.
4. Khóa hoặc chấm dứt challenge khi đạt giới hạn.
5. Cấp bằng chứng hoặc grant nếu kết quả đúng và các điều kiện còn hợp lệ.

Các nhánh đúng và sai phải tuân thủ cơ chế nhất quán. Không cho request đúng đi qua một đường không kiểm tra trạng thái khóa mà request sai vừa ghi nhận.

Một điểm dễ bỏ sót: tăng counter rồi ném exception khiến toàn transaction rollback có thể xóa luôn dấu vết thử sai. Kết quả nghiệp vụ “mã không được chấp nhận” không luôn có nghĩa mọi ghi trạng thái bảo vệ đều phải rollback.

Có thể commit nhánh ghi nhận thất bại rồi trả phản hồi phù hợp, hoặc dùng cơ chế ghi nhận riêng được thiết kế nguyên tử với giới hạn. Không tách tùy tiện đến mức việc kiểm tra và tăng counter lại tạo một race mới.

Giới hạn per-challenge cũng chưa đủ nếu attacker tạo nhiều challenge để có tổng số lần đoán lớn. Cần xét giới hạn theo account, nguồn và bối cảnh mà không biến endpoint thành công cụ khóa tài khoản của người khác.

## 11. Hủy, thay đổi policy và tác vụ đến muộn

Hủy và hoàn tất cần cùng thống nhất điểm đồng bộ.

Trong mô hình account → request → grant:

- Nếu hủy có hiệu lực trước, hoàn tất phải thấy request không còn cho phép.
- Nếu hoàn tất đã commit trước, hủy không được báo rằng credential đã được giữ nguyên.
- Kết quả xác minh đến sau hủy không được chuyển request trở lại trạng thái được cấp quyền.
- Approval dựa trên context hoặc policy đã bị vô hiệu hóa phải được kiểm tra lại khi thực thi.

Không cần tăng epoch toàn tài khoản chỉ để hủy một request nếu chính sách chỉ chấm dứt request đó. State request và quyền liên quan cần đủ để ngăn nó tiếp tục.

Nếu policy khẩn cấp yêu cầu vô hiệu hóa nhiều context, phải có cơ chế phiên bản hoặc trạng thái được tất cả đường thực thi đối chiếu. Xóa một cache không tự chứng minh mọi instance đã ngừng dùng kết quả cũ.

Không đánh dấu request hoàn tất ở một cơ sở dữ liệu trong khi thay đổi credential ở dịch vụ khác rồi coi chúng là một transaction. Ranh giới nhiều dịch vụ cần giao thức điều phối và trạng thái lỗi riêng.

## 12. Thời gian, lock wait và deadlock

Một request có thể bắt đầu trước khi token hết hạn nhưng phải chờ khóa đến sau deadline.

Trong PostgreSQL, `CURRENT_TIMESTAMP` và `now()` gắn với lúc transaction bắt đầu; `clock_timestamp()` trả thời gian tại lúc được gọi. Đây là lý do ví dụ lấy lại thời gian sau khi đã có khóa. [PostgreSQL: Current Date/Time](https://www.postgresql.org/docs/current/functions-datetime.html#FUNCTIONS-DATETIME-CURRENT)

Không tái sử dụng một mốc thời gian đã lấy trước thời gian chờ dài để quyết định token còn hạn. Nguồn đồng hồ và chính sách lệch giờ cũng phải được xác định.

Để giảm deadlock và thời gian chờ:

- Giữ thứ tự khóa ổn định giữa các đường code.
- Với nhiều đối tượng cùng loại, có thứ tự định danh rõ.
- Chuẩn bị tính toán tốn thời gian ngoài đoạn giữ khóa khi có thể, rồi kiểm tra lại điều kiện cần thiết bên trong.
- Không chờ email, mạng bên ngoài hoặc thao tác người dùng trong transaction.
- Giới hạn thời gian chờ theo thiết kế vận hành.
- Không mở một vòng retry vô hạn.

Nếu dùng optimistic locking, version phải được so sánh ở chính câu ghi:

```sql
UPDATE recovery_request
SET state = 'CANCELLED',
    row_version = row_version + 1
WHERE id = :requestId
  AND state = 'AUTHORIZED'
  AND row_version = :expectedVersion;
```

Không có hàng cập nhật nghĩa là cần xử lý xung đột; không có nghĩa đã hủy. Một version trên R1 cũng không tự bảo vệ tranh chấp giữa R1 và R2 ở cấp account.

Serializable có thể phát hiện một số bất thường mà mức cô lập yếu hơn cho phép, nhưng ứng dụng vẫn phải xử lý transaction bị hủy và retry đúng cách. Nó không thực hiện hộ chính sách scope, idempotency hoặc kiểm tra bí mật.

## 13. Retry, idempotency và kết quả commit chưa rõ

Cần phân biệt ba trường hợp:

| Tình huống | Điều đã biết | Hướng xử lý |
| --- | --- | --- |
| Database xác nhận transaction bị abort | Các ghi trong transaction đó không commit | Có thể retry toàn transaction theo điều kiện phù hợp |
| API nhận cùng thao tác đã commit | Có kết quả cũ được định danh | Trả biên nhận phù hợp, không ghi credential lần nữa |
| Mất kết nối quanh COMMIT | Chưa biết commit có xảy ra hay không | Tra kết quả bằng ngữ cảnh và định danh thao tác được phép |

Không bắt mọi exception rồi chạy lại thao tác đổi mật khẩu. Nếu commit đầu đã thành công, một retry không được chấp nhận mật khẩu mới khác với ý định ban đầu chỉ vì cùng token hoặc request.

Một thiết kế biên nhận cần ràng buộc:

- Đúng request và action.
- Đúng chủ thể hoặc ngữ cảnh được phép đọc.
- Đúng thao tác nghiệp vụ.
- Nội dung lệnh tương ứng nếu cho retry bằng cùng key.
- Kết quả đã commit và phạm vi dữ liệu được trả.

Nếu dùng fingerprint để đối chiếu nội dung có mật khẩu, không lưu mật khẩu hoặc một hash nhanh không khóa như một bản sao dễ dò. Cần một thiết kế bảo vệ phù hợp, hoặc ràng buộc lệnh bất biến ở phía server trước khi thực thi. Chỉ có request ID và idempotency key chưa đủ chứng minh hai payload có cùng ý nghĩa.

Việc tra biên nhận không được biến ID thành bearer token. Khi không đủ ngữ cảnh để biết kết quả, trả thông báo trung thực và đường trợ giúp phù hợp; không bịa “đã thành công”.

Idempotency không làm grant hết hạn hoặc đã thu hồi trở nên có thể cấp quyền mới. Trả lại kết quả cũ khác với chấp thuận lại một giao dịch.

## 14. Outbox, cache và replica

Nếu gửi email trước commit, người dùng có thể nhận thông báo thành công cho một transaction sau đó rollback. Nếu chỉ gửi sau commit mà không có cơ chế phục hồi, process có thể chết trước khi gửi.

Outbox là một phương án:

```text
Cùng transaction:
    tiêu thụ grant
    cập nhật credential và epoch
    hoàn tất request
    ghi biên nhận
    ghi sự kiện outbox

Sau commit:
    worker đọc outbox
    gửi thông báo theo cơ chế có kiểm soát
```

Outbox không bảo đảm một email vật lý chỉ được gửi đúng một lần. Worker hoặc nhà cung cấp có thể gặp kết quả không rõ; cần thiết kế gửi lại và chống trùng phù hợp.

Payload sự kiện chỉ chứa dữ liệu cần thiết. Không đưa mật khẩu mới, raw grant hoặc mã recovery vào thông báo kỹ thuật.

Cache và replica cũng cần ranh giới rõ:

- Kiểm tra tiêu thụ cuối cần nguồn dữ liệu có độ nhất quán phù hợp.
- Replica chậm có thể vẫn thấy grant đang active sau khi writer đã tiêu thụ.
- Cache `used=false` không được cấp quyền sau khi transaction đã đổi trạng thái.
- Tăng epoch chỉ có hiệu lực tức thời ở nơi kiểm tra thấy phiên bản mới; nếu cache có độ trễ, phải nói rõ giới hạn và cơ chế bù.
- Cập nhật credential, grant và session nằm ở nhiều kho không tự trở nên nguyên tử chỉ vì cùng một API gọi chúng.

Một response “thành công” cần phản ánh đúng ranh giới mà hệ thống thực sự bảo đảm.

## 15. Những tình huống làm rõ thiết kế persistence

| Tình huống | Kết quả cần bảo đảm |
| --- | --- |
| Hai request dùng cùng grant | Chỉ một lần tiêu thụ tạo được thay đổi |
| Hai grant của cùng request | Request không hoàn tất hai lần |
| R1 và R2 cùng dựa trên một epoch | Chỉ một lần hoàn tất theo chính sách ví dụ |
| R2 được tạo sau khi epoch đã tăng | Dựa trên context mới và phải đáp ứng lại điều kiện |
| Cùng mã dự phòng được gửi qua hai request | Chỉ một lần sử dụng bí mật được ghi nhận |
| Gửi lại và xác minh đụng nhau | Hành vi theo đúng chính sách phiên bản challenge |
| Nhiều lần đoán sai đến cùng lúc | Không mất cập nhật bộ đếm |
| Hủy cạnh tranh với hoàn tất | Có một thứ tự hiệu lực rõ |
| Token hết hạn trong lúc chờ khóa | Được đánh giá theo thời gian kiểm tra đã xác định |
| Transaction bị abort | Không để trạng thái tiêu thụ nửa chừng |
| Mất phản hồi sau commit | Không tự đặt lại credential lần nữa |
| Email hoặc sự kiện được xử lý muộn | Không hồi sinh context đã mất hiệu lực |

Tính đúng khi khôi phục đồng thời đến từ sự phối hợp giữa bất biến, phạm vi khóa, điều kiện ghi, phiên bản bảo mật và ranh giới transaction. Một token dùng một lần chỉ có ý nghĩa khi mọi đường có thể sử dụng nó cùng tuân thủ những điều kiện đó.