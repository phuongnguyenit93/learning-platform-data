# Link replay attempt — Phát lại liên kết khôi phục tài khoản

## 1. Link replay attempt là gì?

Một liên kết khôi phục thường chứa token cho phép người nhận thực hiện một hành động nhạy cảm, chẳng hạn đặt lại mật khẩu. Nếu máy chủ tiếp tục chấp nhận token sau khi hành động đã hoàn tất, người giữ bản sao liên kết có thể phát lại yêu cầu và thay đổi tài khoản thêm lần nữa.

**Link replay attempt** là lần thử sử dụng lại liên kết hoặc bằng chứng khôi phục đã được gửi trước đó. Đối tượng phát lại có thể là kẻ tấn công, nhưng cũng có thể là trình duyệt gửi lại biểu mẫu, người dùng bấm hai lần hoặc một thành phần tự động mở liên kết.

Trong module khôi phục tài khoản, cần quan tâm đến cả liên kết đặt lại mật khẩu, xác minh kênh khôi phục, tiếp tục hồ sơ recovery và cấp quyền gắn lại MFA hoặc passkey. Những liên kết này không nhất thiết có cùng quyền hạn; mỗi loại phải có mục đích và trạng thái riêng.

Ví dụ:

1. Hệ thống cấp liên kết L cho yêu cầu đặt lại mật khẩu.
2. Chủ tài khoản dùng L và đặt mật khẩu mới thành công.
3. Một bản sao của L tồn tại trong lịch sử trình duyệt hoặc nhật ký bị lộ.
4. Người khác gửi lại L cùng một mật khẩu do họ chọn.
5. Nếu máy chủ chỉ kiểm tra chữ ký và thời hạn, yêu cầu thứ hai vẫn có thể được chấp nhận.

Điều kiện cần bảo vệ là: **một quyền khôi phục chỉ được hoàn tất một lần theo phạm vi đã cấp, kể cả khi có nhiều yêu cầu đến đồng thời**.

## 2. Phân biệt phát lại, hết hạn và đánh cắp lần dùng đầu tiên

| Tình huống | Bản chất | Biện pháp trực tiếp |
| --- | --- | --- |
| Token được dùng sau khi đã hoàn tất | Phát lại quyền đã tiêu thụ | Trạng thái dùng một lần và kiểm tra nguyên tử |
| Token chưa dùng nhưng đã hết hạn | Sử dụng bằng chứng quá thời hạn | Kiểm tra thời gian phía máy chủ |
| Token đã bị thu hồi hoặc thay thế | Sử dụng quyền không còn được cho phép | Kiểm tra trạng thái và chính sách cấp lại |
| Hai yêu cầu dùng cùng token khi còn hợp lệ | Tranh chấp đồng thời | Chỉ một giao dịch được quyền hoàn tất |
| Kẻ xấu lấy token và dùng trước chủ tài khoản | Đánh cắp quyền dùng đầu tiên | Chống rò rỉ, xác minh phù hợp và kiểm soát rủi ro |
| Token đặt lại mật khẩu được gửi sang endpoint thay MFA | Sử dụng sai mục đích | Ràng buộc token với đúng hành động |

Thời hạn ngắn làm giảm khoảng thời gian token có thể bị lợi dụng, nhưng không bảo đảm dùng một lần. Nếu token có hiệu lực mười phút và bị dùng lại sau một phút, kiểm tra thời gian vẫn cho kết quả hợp lệ.

Ngược lại, dùng một lần không bảo đảm đúng người sử dụng. Nếu kẻ tấn công là người tiêu thụ token đầu tiên, hệ thống có thể đã thực thi đúng giới hạn một lần nhưng vẫn khôi phục tài khoản cho sai người.

Không diễn giải “đã chặn replay” thành “luồng khôi phục không thể bị chiếm đoạt”.

## 3. Liên kết cần đại diện cho một quyền hạn cụ thể

Có thể mô hình hóa liên kết bằng một challenge phía máy chủ:

| Trường minh họa | Vai trò |
| --- | --- |
| challenge_id | Định danh nội bộ để quản lý và ghi sự kiện |
| token_digest | Giá trị dùng để đối chiếu token, không phải token rõ |
| account_id | Tài khoản mà quyền khôi phục áp dụng |
| tenant_id | Phạm vi tổ chức nếu hệ thống có nhiều tenant |
| purpose | Mục đích như PASSWORD_RESET hoặc RECOVERY_CONTACT_VERIFY |
| issued_at, expires_at | Thời điểm cấp và hết hiệu lực |
| state | ISSUED, CONSUMED, REVOKED hoặc SUPERSEDED |
| consumed_at | Thời điểm quyền được tiêu thụ |
| issued_epoch | Phiên bản khôi phục tại thời điểm cấp, nếu dùng cơ chế phiên bản |

Token nên được sinh bằng nguồn ngẫu nhiên mật mã với độ khó đoán phù hợp, lưu an toàn, gắn với người dùng, có thời hạn và mất hiệu lực sau sử dụng. Đây là các thuộc tính OWASP nêu cho token khôi phục. [Nguồn: OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#general-security-practices).

Trong một phương án dùng token ngẫu nhiên có entropy cao, máy chủ có thể lưu digest để đối chiếu thay vì lưu token rõ. Không suy rộng cách lưu này sang mật khẩu hoặc mã ngắn: mã có không gian nhỏ còn cần biện pháp chống dò và bảo vệ lưu trữ phù hợp.

Token là bí mật dạng bearer: ai có token có thể thử dùng quyền mà nó đại diện. ID challenge, ID ticket hoặc email tài khoản không nên tự trở thành bí mật cấp quyền thay thế.

Các ràng buộc account, tenant và purpose phải được kiểm tra bằng dữ liệu đáng tin cậy. Không lấy account_id từ biểu mẫu rồi bỏ qua tài khoản gắn với token; không cho phía gọi tùy ý chọn purpose để vượt sang hành động mạnh hơn.

## 4. Vì sao kiểm tra rồi đánh dấu đã dùng vẫn bị vượt qua?

Một triển khai dễ gặp:

~~~text
challenge = findByToken(token)

if challenge.isUnused() and challenge.isUnexpired():
    changePassword(challenge.accountId, newPassword)
    challenge.markConsumed()
~~~

Từng yêu cầu riêng lẻ có vẻ đúng, nhưng hai yêu cầu có thể cùng đi qua điều kiện:

| Thứ tự | Yêu cầu A | Yêu cầu B |
| --- | --- | --- |
| 1 | Đọc state = ISSUED | |
| 2 | | Đọc state = ISSUED |
| 3 | Đổi sang mật khẩu A | |
| 4 | | Đổi sang mật khẩu B |
| 5 | Ghi CONSUMED | |
| 6 | | Ghi CONSUMED |

Sau cùng token chỉ có một trạng thái CONSUMED, nhưng tài khoản đã bị thay đổi hai lần. Cột consumed_at không tự bảo vệ được hành động xảy ra trước đó.

Vấn đề nằm ở khoảng cách giữa **kiểm tra điều kiện** và **thực thi thay đổi**. Yêu cầu bảo mật phải được cưỡng chế tại điểm ghi có thẩm quyền, không chỉ tại controller hoặc màn hình nhập mật khẩu.

Khóa trong một tiến trình Java cũng không đủ khi có nhiều instance. Hai instance có hai vùng nhớ và hai khóa riêng. Quyết định sử dụng một lần phải dựa vào trạng thái dùng chung có bảo đảm đồng thời thích hợp.

## 5. Thiết kế tiêu thụ token cùng giao dịch thay đổi tài khoản

### 5.1. Một phương án: tiêu thụ tại bước hoàn tất

Với luồng đặt lại mật khẩu đơn giản, có thể để liên kết chỉ mở trang nhập liệu, sau đó tiêu thụ token khi người dùng gửi biểu mẫu hợp lệ.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant W as Dịch vụ khôi phục
    participant D as Kho trạng thái có thẩm quyền
    U->>W: GET trang khôi phục
    W-->>U: Biểu mẫu, chưa hoàn tất thay đổi
    U->>W: POST token và mật khẩu mới
    W->>D: Bắt đầu giao dịch, khóa tài khoản liên quan
    W->>D: Chuyển ISSUED sang CONSUMED nếu còn hợp lệ
    alt Có đúng một challenge được tiêu thụ
        W->>D: Đổi mật khẩu và cập nhật trạng thái liên quan
        W->>D: Ghi sự kiện cần phát, commit
        W-->>U: Hoàn tất, hướng dẫn đăng nhập thông thường
    else Không tiêu thụ được
        W->>D: Rollback
        W-->>U: Liên kết không còn khả dụng
    end
~~~

Đây là một lựa chọn kiến trúc minh họa. Nếu hệ thống đổi link thành phiên khôi phục hạn chế ở bước trước, phải áp dụng cơ chế dùng một lần tại bước trao đổi đó và quản lý vòng đời phiên mới riêng, như mục 8.

### 5.2. SQL minh họa ranh giới nguyên tử

Đoạn sau mô tả ý tưởng giao dịch, không phải script chạy trực tiếp:

~~~sql
BEGIN;

-- :account_id lấy từ challenge đã đối chiếu token,
-- :tenant_id lấy từ ngữ cảnh tenant được xác thực.
SELECT id, recovery_epoch
FROM account
WHERE id = :account_id
  AND tenant_id = :tenant_id
FOR UPDATE;

-- Đọc :db_now từ nguồn thời gian có thẩm quyền sau khi có khóa.
UPDATE recovery_challenge
SET state = 'CONSUMED',
    consumed_at = :db_now
WHERE id = :challenge_id
  AND token_digest = :presented_digest
  AND account_id = :account_id
  AND tenant_id = :tenant_id
  AND purpose = 'PASSWORD_RESET'
  AND state = 'ISSUED'
  AND expires_at > :db_now
  AND issued_epoch = :current_recovery_epoch;

-- Chỉ tiếp tục nếu số hàng cập nhật đúng bằng 1.
-- Nếu là 0 hoặc có bất thường: ROLLBACK, không đổi mật khẩu.

UPDATE account
SET password_hash = :new_password_hash,
    recovery_epoch = recovery_epoch + 1,
    session_epoch = session_epoch + 1
WHERE id = :account_id
  AND tenant_id = :tenant_id;

-- Vô hiệu hóa những challenge khác thuộc phạm vi
-- mà chính sách quy định phải hết hiệu lực sau lần reset này.

INSERT INTO recovery_outbox (event_id, event_type, account_id)
VALUES (:event_id, 'PASSWORD_RECOVERY_COMPLETED', :account_id);

COMMIT;
~~~

Để mô hình này có ý nghĩa, triển khai còn cần bảo đảm:

- Tra cứu token không làm thay đổi chủ thể; kiểm tra lại các ràng buộc tại điểm ghi.
- Thứ tự lấy khóa thống nhất giữa các luồng cấp, thu hồi và hoàn tất để giảm deadlock.
- Số hàng cập nhật được kiểm tra thực sự; không bắt lỗi rồi vẫn trả về thành công.
- Các thay đổi tài khoản thuộc cùng giao dịch với việc tiêu thụ token.
- Nếu đổi mật khẩu thất bại, giao dịch rollback cả trạng thái CONSUMED.
- Bước kiểm tra thời hạn dùng thời gian phía máy chủ và quy tắc rõ tại thời điểm chấp nhận.
- Mật khẩu đầu vào và chính sách liên quan đã được kiểm tra trước khi thực thi thay đổi.

Phép tính hash mật khẩu tốn tài nguyên có thể được chuẩn bị trước để tránh giữ khóa lâu; việc đó không được bỏ qua các kiểm tra trạng thái cần thực hiện lại trong giao dịch.

Nếu cơ sở dữ liệu cung cấp thời gian cố định theo thời điểm bắt đầu giao dịch, không mặc định đó là thời điểm hiện tại sau một lần chờ khóa dài. Chọn cơ chế thời gian phù hợp và quy định rõ token hết hạn được đánh giá ở bước nào.

### 5.3. Phần việc ngoài giao dịch

Gửi email, đồng bộ phiên và gọi dịch vụ bên ngoài thường không nằm trong cùng giao dịch cơ sở dữ liệu. Outbox có thể giúp không mất công việc cần phát sau commit, nhưng không làm các hệ thống đó cập nhật đồng thời.

Ví dụ, tăng session_epoch chỉ có hiệu lực thu hồi khi đường kiểm tra phiên thực sự đối chiếu giá trị đó. Nếu resource server vẫn chấp nhận token cũ mà không kiểm tra, việc tăng cột dữ liệu chưa đủ ngăn truy cập.

Cần theo dõi kết quả, retry có kiểm soát và độ trễ áp dụng. Không dùng lý do “chờ gửi email” để cho phép token đã tiêu thụ thực hiện lại thay đổi mật khẩu.

## 6. Link được mở nhiều lần chưa chắc là tấn công

### 6.1. Trình quét thư, bản xem trước và trình duyệt

Một URL trong email có thể bị mở bởi bộ quét an toàn, thành phần tạo preview hoặc cơ chế tải trước. Người dùng cũng có thể mở nó trên hai tab.

Do đó, không thiết kế GET như một thao tác tự động đổi mật khẩu, gỡ MFA hay hoàn tất khôi phục. RFC 9110 giải thích rằng các phương thức an toàn cho phép việc truy xuất tự động và prefetch diễn ra mà không gây các thay đổi có hại. [Nguồn: RFC 9110, mục 9.2.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.1).

Một GET có thể được ghi nhận để vận hành, nhưng cần phân biệt:

- **Quan sát truy cập:** liên kết đã được yêu cầu.
- **Tiêu thụ quyền khôi phục:** hệ thống đã chấp nhận một hành động được cấp quyền.
- **Hoàn tất thay đổi:** giao dịch nghiệp vụ đã commit.

Không tăng thời hạn token mỗi lần trang được mở. Nếu làm vậy, việc truy cập lặp lại có thể kéo dài thời gian sống của liên kết vô hạn.

### 6.2. POST chưa tự giải quyết mọi vấn đề

Chuyển từ GET sang POST chỉ thay đổi ngữ nghĩa HTTP, không tạo trạng thái dùng một lần và không tự chống CSRF.

Nếu trình duyệt dùng cookie để duy trì ngữ cảnh khôi phục, áp dụng biện pháp CSRF phía máy chủ phù hợp, kiểm tra nguồn yêu cầu theo thiết kế và bảo vệ cookie. SameSite là một thành phần phòng vệ, không thay thế toàn bộ cơ chế. [Nguồn: OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

Một lần bấm nút “Tiếp tục” cũng không chứng minh người bấm là chủ tài khoản. Nó giúp tránh tiêu thụ ngoài ý muốn, còn mức xác minh danh tính phải do chính sách recovery quyết định.

## 7. Replay và retry hợp lệ cần được xử lý khác nhau

Giả sử yêu cầu A đã commit đổi mật khẩu, nhưng phản hồi bị mất trên mạng. Trình duyệt gửi lại cùng yêu cầu.

Máy chủ không được thực hiện thay đổi lần thứ hai chỉ để làm giao diện bớt khó hiểu. Có hai cách tổ chức phổ biến:

| Lựa chọn | Hành vi | Điểm cần giữ |
| --- | --- | --- |
| Từ chối dùng lại token | Lần gửi sau nhận thông báo liên kết không còn khả dụng | Hướng dẫn thử đăng nhập hoặc bắt đầu yêu cầu mới |
| Hỗ trợ idempotency có kiểm soát | Cùng thao tác đã hoàn tất có thể nhận lại xác nhận giới hạn | Không thực thi lại và không cấp thêm quyền |

Nếu hỗ trợ idempotency, không coi một chuỗi Idempotency-Key do người gọi chọn là bằng chứng sở hữu. Cần ràng buộc với đúng thao tác, ngữ cảnh khôi phục được phép và nội dung yêu cầu đã chuẩn hóa hoặc định danh an toàn.

Các điểm cần xác định:

- Hai lần gửi có thực sự là cùng thao tác hay đã đổi mật khẩu đầu vào?
- Ngữ cảnh gọi có còn quyền xem kết quả đó không?
- Thời hạn lưu kết quả và phạm vi tra cứu là gì?
- Có thể trả lại một xác nhận tối thiểu mà không lộ dữ liệu tài khoản không?

Không trả lại token đăng nhập, mật khẩu hoặc quyền recovery mới từ bộ nhớ đệm kết quả. Không lưu mật khẩu rõ để so sánh hai lần gửi; nếu cần ràng buộc nội dung nhạy cảm, dùng cơ chế fingerprint được thiết kế để không tạo thêm kho dữ liệu dễ dò.

**Idempotency** nghĩa là yêu cầu lặp không làm thay đổi nghiệp vụ thêm lần nữa. Nó không có nghĩa là liên kết được cấp quyền sử dụng nhiều lần.

## 8. Không chuyển replay từ liên kết sang phiên khôi phục

Một số thiết kế trao đổi token trong link lấy cookie hoặc phiên hạn chế để làm sạch URL trước các bước tiếp theo. Cách này cần phân tích cả hai loại quyền.

| Chặng | Quyền đang tồn tại | Điều kiện chống phát lại |
| --- | --- | --- |
| Trước trao đổi | Token trong liên kết | Chỉ một lần trao đổi được chấp nhận |
| Sau trao đổi | Phiên khôi phục hạn chế | Scope, TTL và trạng thái phiên phải được kiểm tra |
| Hoàn tất | Quyền thực hiện hành động cuối | Một thay đổi hợp lệ, rồi đóng hoặc vô hiệu hóa phiên |
| Sau thành công | Phiên đăng nhập thông thường nếu có quy trình riêng | Không tự suy ra từ việc mở lại liên kết |

Nếu token cũ có thể tạo không giới hạn phiên hạn chế, dù mỗi phiên chỉ hoàn tất một lần, kẻ tấn công vẫn có nhiều quyền để cạnh tranh. Điểm tiêu thụ token phải gắn nguyên tử với việc tạo phiên hợp lệ; lỗi tạo phiên không được để trạng thái nửa vời.

Phiên mới không nên có quyền truy cập toàn bộ ứng dụng. Nếu nó chỉ cho phép đặt lại mật khẩu thì không được dùng để đổi email, thêm passkey hoặc bỏ MFA. Sau khi hoàn tất, các bản sao của phiên hạn chế cũng phải hết quyền tương ứng.

Không trộn hai mô hình một cách vô tình: token đã trao đổi không được đồng thời tiếp tục dùng trực tiếp tại endpoint hoàn tất.

## 9. JWT có chữ ký vẫn có thể bị phát lại

Một JWT có chữ ký đúng chỉ chứng minh rằng dữ liệu chưa bị thay đổi theo cơ chế ký đã dùng và được bên có khóa phù hợp phát hành. Nó không tự ghi nhớ rằng người khác đã dùng token trước đó.

Các kiểm tra như issuer, audience, mục đích và thời gian vẫn cần thiết. Tuy nhiên:

~~~text
verifySignature(token)
verifyExpiry(token)
changePassword(token.subject, newPassword)
~~~

không bảo đảm dùng một lần.

RFC 7519 định nghĩa jti là định danh của JWT và nêu khả năng dùng nó để ngăn phát lại. Để đạt mục tiêu đó trong một luồng cụ thể, hệ thống vẫn cần cơ chế ghi nhận và cưỡng chế trạng thái sử dụng phù hợp. [Nguồn: RFC 7519, mục 4.1.7](https://www.rfc-editor.org/rfc/rfc7519.html#section-4.1.7).

Ví dụ, có thể duy trì bản ghi challenge theo jti và tiêu thụ bằng giao dịch. Chỉ thêm một jti ngẫu nhiên vào payload rồi kiểm tra chữ ký ở mọi lần gửi không làm token thành dùng một lần.

Không xoay khóa ký toàn hệ thống mỗi khi một người đặt lại mật khẩu. Cách đó ảnh hưởng phạm vi quá rộng và không thay thế việc quản lý vòng đời từng quyền recovery.

## 10. Cấp lại liên kết, nhiều thiết bị và trạng thái phân tán

### 10.1. Quy định rõ liên kết cũ còn dùng được không

Khi người dùng bấm “Gửi lại”, hệ thống có thể chọn hủy liên kết trước hoặc cho phép một tập challenge đang mở trong giới hạn. Cần nêu rõ chính sách thay vì để hành vi phụ thuộc ngẫu nhiên vào implementation.

Nếu chỉ liên kết mới nhất được chấp nhận, việc cấp mới và đánh dấu liên kết cũ SUPERSEDED cần được đồng bộ tại nguồn trạng thái có thẩm quyền. Gửi email mới thành công không tự hủy được email cũ.

Ngược lại, endpoint công khai cho phép gửi lại liên tục có thể bị lợi dụng làm các link của nạn nhân hết hiệu lực. Cần giới hạn tốc độ, kiểm soát lạm dụng và cân nhắc quy tắc cấp lại; không khóa tài khoản chỉ vì có nhiều yêu cầu chưa xác minh.

Sau một lần đổi mật khẩu thành công, những challenge hoặc phiên recovery khác thuộc phạm vi cần vô hiệu hóa phải được xử lý theo chính sách. Không để một link được cấp trước đó đổi mật khẩu thêm lần nữa chỉ vì nó có token khác.

### 10.2. Không lấy cache cũ làm quyết định cuối cùng

Trong hệ thống nhiều vùng hoặc nhiều instance, một bản sao đọc có thể vẫn thấy ISSUED sau khi vùng khác đã tiêu thụ token.

Có thể dùng cache để giảm tải một số phép đọc, nhưng quyết định chấp nhận hành động nhạy cảm cần đi qua cơ chế phối hợp có bảo đảm phù hợp. Kiểm tra ở replica rồi cập nhật độc lập tại mỗi vùng có thể tạo hai lần thành công.

Nếu không truy cập được nguồn trạng thái cần để quyết định dùng một lần, từ chối hoặc yêu cầu thử lại có kiểm soát. Không chuyển sang chế độ “chỉ kiểm chữ ký tạm thời”.

Một lệnh nguyên tử trong Redis và một giao dịch đổi mật khẩu ở cơ sở dữ liệu khác cũng không tự trở thành một giao dịch chung. Nếu chọn kiến trúc đó, phải giải quyết trạng thái dở dang, khôi phục sau lỗi và tranh chấp với các luồng thu hồi; không chỉ nêu tên lệnh nguyên tử rồi coi vấn đề đã xong.

## 11. Giảm cơ hội liên kết bị sao chép

Chống replay xử lý quyền đã được dùng hoặc hết hiệu lực. Giảm rò rỉ bảo vệ cả giai đoạn trước lần dùng đầu tiên.

Các vị trí cần xem xét gồm access log, tracing, lịch sử trình duyệt, analytics, ảnh chụp màn hình, ticket hỗ trợ, header Referer và tài nguyên bên thứ ba trên trang khôi phục.

Một cấu hình HTTP minh họa cho phản hồi nhạy cảm:

~~~http
Cache-Control: no-store
Referrer-Policy: no-referrer
~~~

Trang khôi phục nên tránh thành phần theo dõi hoặc tài nguyên không cần thiết có thể nhận thông tin URL. Che token tại tầng proxy, ứng dụng và hệ thống quan sát; chỉ che tại giao diện người dùng là chưa đủ.

Có thể chuyển hướng sang URL sạch hoặc dọn địa chỉ hiển thị theo thiết kế, nhưng việc đó không xóa token đã được ghi ở proxy, trình duyệt hoặc log trước đó. Các header trên cũng không thay thế trạng thái dùng một lần và không bảo vệ trước một thiết bị đã bị xâm nhập.

Không để nhân viên hỗ trợ yêu cầu khách hàng dán nguyên recovery URL còn hiệu lực vào chat. Khi cần điều tra, dùng ID challenge hoặc mã hồ sơ không tự cấp quyền thực hiện khôi phục.

## 12. Phát hiện và phản hồi một lần phát lại

### 12.1. Ghi nhận kết quả nội bộ, hạn chế chi tiết công khai

Một sự kiện nội bộ có thể có dạng:

~~~json
{
  "eventType": "RECOVERY_LINK_REJECTED",
  "challengeId": "challenge_example_42",
  "purpose": "PASSWORD_RESET",
  "reason": "ALREADY_CONSUMED",
  "observedAt": "2026-11-23T09:05:00Z",
  "requestId": "request_example_018",
  "accountMutationApplied": false
}
~~~

Đây là dữ liệu minh họa, không chứa token hoặc mật khẩu. Không ghi raw URL vào trường request metadata rồi vô tình đưa bí mật trở lại log.

Các reason nội bộ có thể phân biệt đã dùng, hết hạn, bị thu hồi, sai mục đích hoặc không tồn tại. Phản hồi cho người gọi có thể gộp những trường hợp phù hợp thành:

> Liên kết này không còn khả dụng. Nếu bạn đã hoàn tất khôi phục, hãy mở trang đăng nhập chính thức. Nếu vẫn cần hỗ trợ, hãy bắt đầu yêu cầu mới từ kênh chính thức.

Không mặc định phải trả một mã HTTP duy nhất cho mọi hệ thống; cần bảo đảm chính sách lỗi không tiết lộ thông tin tài khoản hoặc cho phép hành động tiếp tục.

### 12.2. Đánh giá tín hiệu thay vì tự kết luận

Một lần mở lại ngay sau thành công trên cùng trình duyệt có thể do người dùng bấm Back hoặc gửi lại. Nhiều lần thử từ nhiều nguồn sau khi token đã dùng có thể đáng điều tra hơn.

IP và User-Agent giúp điều tra, nhưng không phải bằng chứng xác định chủ tài khoản. Mạng di động, VPN hoặc trình duyệt có thể thay đổi hợp lệ; kẻ tấn công cũng có thể bắt chước một phần thông tin này.

Cần xem xét mối liên hệ với:

- Sự kiện khôi phục đã thành công trước đó.
- Thay đổi mật khẩu, MFA hoặc passkey không được nhận ra.
- Dấu hiệu token có mặt trong log hoặc kênh hỗ trợ.
- Số lượng challenge và tài khoản liên quan.
- Tình trạng phiên truy cập sau khôi phục.

Không tự khóa tài khoản chỉ vì một token đã dùng bị gửi lại. Nếu có dấu hiệu người không được phép đã tiêu thụ token đầu tiên, chuyển sang quy trình tài khoản nghi bị chiếm và xác minh độc lập; chặn lần dùng tiếp theo chưa xử lý được hậu quả của lần dùng đầu tiên.

## 13. Ví dụ xuyên suốt và các kết quả cần hiểu

Mai có một liên kết đặt lại mật khẩu đang hợp lệ. Hai yêu cầu A và B dùng cùng token đến hai instance khác nhau.

| Diễn biến | Kết quả đúng theo mô hình giao dịch |
| --- | --- |
| A có quyền hoàn tất trước | A tiêu thụ challenge và đổi mật khẩu trong cùng giao dịch |
| B đọc thấy token hợp lệ từ cache cũ | Cache không đủ để cho phép B thay đổi tài khoản |
| A commit, B đi đến điểm kiểm tra nguyên tử | B không cập nhật được challenge ISSUED, nên không đổi mật khẩu |
| Phản hồi A bị mất, Mai gửi lại | Không thực thi lần nữa; phản hồi theo chính sách retry/idempotency |
| A lỗi trước commit | Rollback cả đổi mật khẩu và tiêu thụ; một yêu cầu khác chỉ có thể tiếp tục nếu token vẫn còn hợp lệ |
| Token hết hạn trong khi chờ khóa | Kiểm tra thời gian ở điểm chấp nhận theo quy tắc đã định |
| Một link khác được cấp trước đó được gửi đến | Kiểm tra trạng thái, phiên bản và chính sách vô hiệu hóa sau khôi phục |

Trong một biến thể khác, kẻ tấn công lấy được link trước Mai và hoàn tất đầu tiên. Sau đó Mai nhận lỗi “liên kết không còn khả dụng”.

Trạng thái CONSUMED chứng minh đã có lần dùng thành công theo dữ liệu hệ thống, không chứng minh Mai là người dùng nó. Cần có thông báo phù hợp, đường báo cáo sự cố và khả năng điều tra quyền truy cập đã được cấp. Không hướng dẫn Mai tiếp tục gửi lại token đã dùng cho đến khi “may mắn thành công”.

## 14. Những lỗi thiết kế thường gặp

| Cách làm | Vì sao không đủ | Điều cần bổ sung |
| --- | --- | --- |
| Token chỉ có thời hạn ngắn | Có thể bị dùng nhiều lần trước khi hết hạn | Trạng thái dùng một lần tại điểm thực thi |
| Đánh dấu CONSUMED sau khi đổi mật khẩu ngoài giao dịch | Hai request cùng vượt qua kiểm tra | Ràng buộc nguyên tử giữa tiêu thụ và thay đổi |
| Khóa bằng synchronized trong một JVM | Instance khác không dùng cùng khóa | Cơ chế phối hợp tại nguồn trạng thái chung |
| Thêm jti nhưng không lưu trạng thái | Không biết jti đã dùng hay chưa | Cưỡng chế vòng đời theo định danh |
| GET tự hoàn tất khôi phục | Preview hoặc crawler có thể kích hoạt | Tách xem trang khỏi hành động có chủ đích |
| POST không có cơ chế CSRF khi dùng cookie | Có thể bị ép gửi yêu cầu từ ngữ cảnh khác | Kiểm tra CSRF phù hợp với luồng trình duyệt |
| Link tạo nhiều phiên hạn chế | Quyền bị nhân bản trước bước cuối | Trao đổi dùng một lần và quản lý phiên mới |
| Không kiểm tra purpose, tenant hoặc account | Token có thể được dùng sai phạm vi | Ràng buộc và kiểm tra phía máy chủ |
| Kho trạng thái lỗi thì bỏ qua kiểm tra replay | Mất bảo đảm ngay lúc không xác minh được | Từ chối có kiểm soát và phục hồi dịch vụ |
| Coi mọi lần gửi lại là tấn công | Khóa nhầm hoặc gây rối người dùng | Phân biệt kết quả kỹ thuật và đánh giá rủi ro |

Chống phát lại liên kết là một thuộc tính của toàn bộ vòng đời quyền khôi phục: cấp đúng phạm vi, giữ bí mật, chấp nhận nguyên tử, hoàn tất một lần và vô hiệu hóa những quyền liên quan theo chính sách. Nó cần được kết hợp với xác minh danh tính và kiểm soát session để giảm nguy cơ chiếm đoạt tài khoản.

## Tài liệu tham khảo

- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): đặc tính token và luồng đặt lại mật khẩu.
- [RFC 9110 — Safe Methods](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.1): ngữ nghĩa phương thức HTTP an toàn và truy xuất tự động.
- [RFC 7519 — JWT ID](https://www.rfc-editor.org/rfc/rfc7519.html#section-4.1.7): ý nghĩa định danh jti.
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): bảo vệ yêu cầu thay đổi trạng thái trong trình duyệt.
