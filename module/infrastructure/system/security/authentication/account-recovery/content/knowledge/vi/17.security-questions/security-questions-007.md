# Removing knowledge questions — Loại bỏ câu hỏi kiến thức khỏi luồng khôi phục tài khoản

Trong chương **Security Questions** của module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, loại bỏ câu hỏi kiến thức là thay đổi cách hệ thống quyết định ai được quyền lấy lại tài khoản. Công việc này bao gồm phương thức khôi phục thay thế, API, quy trình hỗ trợ, token đã cấp và dữ liệu câu trả lời.

Mục tiêu là để một người biết tên thú cưng, trường học, ngày sinh hoặc thông tin lịch sử cá nhân không còn có thể dùng chúng để đặt lại mật khẩu, gỡ MFA, thay passkey hay đăng ký thiết bị xác thực mới. Đồng thời, người dùng hợp lệ cần có đường chuyển đổi rõ ràng và không bị đẩy sang một cơ chế yếu khác.

## 1. Hiểu đúng phạm vi loại bỏ

**Knowledge-based authentication — KBA** trong bài là việc xác thực bằng câu trả lời về thông tin cá nhân được cho là chỉ chủ tài khoản biết. Ví dụ: tên trường tiểu học, họ tên người thân, nơi sinh hoặc câu hỏi do người dùng tự đặt.

Thông tin riêng tư không đương nhiên là bí mật xác thực tốt. Câu trả lời có thể xuất hiện trên mạng xã hội, bị người quen biết, được suy ra từ dữ liệu rò rỉ hoặc tái sử dụng ở nhiều dịch vụ. Dù chưa bị lộ, không gian câu trả lời cũng có thể nhỏ và phân bố rất lệch.

Bài này không yêu cầu xóa mọi yếu tố “điều người dùng biết”. Mật khẩu được thiết kế và quản lý đúng là một loại bí mật xác thực khác với câu hỏi về tiểu sử. Một mã khôi phục ngẫu nhiên cũng không trở thành KBA chỉ vì người dùng phải gõ nó.

NIST SP 800-63-4 không coi KBA dựa vào câu hỏi kiến thức cá nhân là bí mật chấp nhận được cho xác thực số. OWASP cũng nói rõ phần hướng dẫn chọn câu hỏi bảo mật của họ phục vụ bối cảnh legacy, không phải khuyến nghị thêm cơ chế này vào thiết kế an toàn mới. [NIST SP 800-63-4, Authenticators](https://pages.nist.gov/800-63-4/sp800-63.html#authenticators), [OWASP Choosing and Using Security Questions](https://cheatsheetseries.owasp.org/cheatsheets/Choosing_and_Using_Security_Questions_Cheat_Sheet.html#introduction).

Cần phân biệt ba công việc:

| Công việc | Ý nghĩa | Ví dụ |
|---|---|---|
| Định tuyến hoặc tìm hồ sơ | Xác định hồ sơ nào cần xử lý | Nhập email để bắt đầu yêu cầu |
| Xác thực quyền kiểm soát tài khoản | Chứng minh đang kiểm soát phương tiện đã gắn với tài khoản | Hoàn thành challenge của authenticator đã đăng ký |
| Xác minh danh tính | Liên kết người đang làm thủ tục với danh tính đã được kiểm chứng | Quy trình identity proofing có bằng chứng và xác minh phù hợp |

Việc nhân viên biết ngày sinh khớp hồ sơ có thể giúp tìm đúng hồ sơ, nhưng không tự chứng minh người gọi là chủ tài khoản. NIST SP 800-63A-4 không cho dùng KBV/KBA để thực hiện identity verification. Không được đổi nhãn “câu hỏi bảo mật” thành “xác minh danh tính” rồi giữ nguyên cách so khớp thông tin cá nhân. [NIST SP 800-63A-4, Identity Verification](https://pages.nist.gov/800-63-4/sp800-63a.html#identity-verification).

## 2. Vì sao chỉ ẩn giao diện chưa hoàn thành

Một hệ thống có thể bỏ ô nhập câu trả lời trên website nhưng vẫn chấp nhận chúng qua ứng dụng cũ, API đối tác hoặc tổng đài. Kẻ tấn công sẽ dùng đường còn hoạt động.

Các thay đổi sau không đủ để tuyên bố loại bỏ KBA:

- Đổi từ ba câu hỏi sang một câu hỏi “khó hơn”.
- Băm câu trả lời nhưng tiếp tục dùng chúng để cấp quyền.
- Tắt trang quản lý câu hỏi nhưng vẫn giữ endpoint xác minh.
- Bỏ KBA ở đăng nhập và giữ ở quên mật khẩu hoặc mất MFA.
- Cho tài khoản đã có passkey chọn “không dùng được” rồi quay về câu hỏi.
- Chuyển câu hỏi sang hỗ trợ thủ công hoặc chatbot.
- Giữ một cờ cấu hình có thể mở lại KBA khi hệ thống mới gặp lỗi.

Băm giúp giảm một phần hậu quả khi lộ dữ liệu lưu trữ; nó không làm câu trả lời khó đoán hơn từ phía người gọi API.

Một định nghĩa hoàn thành có thể kiểm chứng là:

~~~text
Sau thời điểm ngừng KBA:
  không đường cấp quyền nào chấp nhận câu trả lời kiến thức cá nhân;
  không phát sinh token/grant mới nhờ KBA;
  quyền còn hiệu lực từ KBA được thu hồi hoặc xử lý theo chính sách;
  người dùng có phương án thay thế phù hợp;
  dữ liệu legacy được ngừng thu thập và có vòng đời xóa rõ ràng.
~~~

Không cần đợi xóa xong mọi bản sao lưu mới chặn KBA. **Ngừng tin cậy cơ chế** và **hoàn tất xử lý dữ liệu** là hai mốc riêng, đều phải được theo dõi.

## 3. Kiểm kê đường sử dụng và nơi lưu dữ liệu

Trước khi chuyển đổi, lập bản đồ theo **quyền có thể được cấp**, không chỉ theo màn hình có chữ “security question”.

### 3.1. Các luồng phải rà soát

| Khu vực | Điều cần tìm | Rủi ro nếu bỏ sót |
|---|---|---|
| Đăng ký và onboarding | Trường bắt buộc, wizard, bước hoàn thiện hồ sơ | Tiếp tục thu thập dữ liệu dù không còn sử dụng |
| Quên mật khẩu | Cấp reset token sau khi đúng câu trả lời | Đường đặt lại mật khẩu vẫn mở |
| Mất MFA hoặc thiết bị | Tắt TOTP, gỡ khóa bảo mật, xóa passkey | Kẻ tấn công vượt yếu tố mạnh |
| Thay thông tin liên hệ | Đổi email, số điện thoại, địa chỉ khôi phục | Chuyển kênh khôi phục sang người khác |
| Quản lý authenticator | Đăng ký passkey, cấp backup code | Biến KBA thành phương tiện truy cập lâu dài |
| Hỗ trợ và quản trị | Script tổng đài, ghi chú CRM, nút override | Cơ chế cũ tồn tại qua con người |
| Tích hợp | Mobile cũ, API nội bộ, đối tác, tenant riêng | Tắt một nơi nhưng còn nơi khác |
| Federation | IdP dùng KBA và RP chấp nhận kết quả | Ứng dụng không tự hỏi nhưng vẫn tin nguồn KBA |

Với mỗi đường, ghi nhận chủ sở hữu, endpoint hoặc chức năng, bằng chứng được chấp nhận, artifact được cấp và nơi thực thi chính sách. Không sao chép câu trả lời thật vào bảng kiểm kê.

### 3.2. Các bản sao dữ liệu cần quản lý

Câu hỏi và câu trả lời có thể nằm trong bảng chính, JSON hồ sơ, cache, search index, kho phân tích, CDC, message queue, log, trace, ticket và bản sao lưu. Câu hỏi tự viết hoặc hint cũng có thể chứa dữ liệu cá nhân hoặc gợi ý mật khẩu.

Không cần xuất toàn bộ dữ liệu để biết quy mô. Ưu tiên số lượng bản ghi, loại kho lưu trữ, tuổi dữ liệu, quyền truy cập và các luồng đọc/ghi.

Kết quả kiểm kê cần trả lời được:

1. Ai còn phụ thuộc vào KBA?
2. Họ có phương tiện thay thế nào thực sự dùng được?
3. Hệ thống nào còn có thể cấp quyền nhờ KBA?
4. Có token, session hoặc credential nào đã được tạo từ KBA?
5. Dữ liệu được xóa ở đâu, khi nào và bằng cách nào?

## 4. Chọn phương án thay thế theo bằng chứng và mức rủi ro

Bỏ một cơ chế yếu không có nghĩa là chọn một cơ chế thay thế duy nhất cho mọi tài khoản.

| Tình trạng tài khoản | Đường chuyển đổi có thể phù hợp | Điều kiện cần giữ |
|---|---|---|
| Còn authenticator đủ mức bảo đảm | Xác thực lại rồi đăng ký phương tiện dự phòng | Kiểm tra độ mới và loại bằng chứng phía máy chủ |
| Còn mật khẩu và yếu tố MFA | Hoàn thành tổ hợp theo chính sách trước khi thay cấu hình | Không coi session cũ là đủ để thay mọi yếu tố |
| Mất một yếu tố nhưng còn mã dự phòng | Luồng recovery dùng mã và bằng chứng bổ sung nếu cần | Mã ngẫu nhiên, dùng một lần, giới hạn thử, đúng tài khoản |
| Có địa chỉ khôi phục đã thiết lập | Cấp recovery code theo chính sách rủi ro | Không mặc nhiên coi quyền truy cập email là đủ để gỡ mọi MFA |
| Không còn phương tiện nhưng đã được proofing | Quy trình xác minh lại có kiểm soát nếu phù hợp | Có liên hệ với danh tính đã thiết lập, không chỉ nhận ảnh giấy tờ |
| Tài khoản ẩn danh, không còn phương tiện | Phương án đã thiết kế riêng, nếu có đủ bằng chứng | Không hứa có thể khôi phục chỉ nhờ một tên thật mới khai |

Một passkey thay thế phải được đăng ký và kiểm chứng đúng giao thức; có tên nó trong database chưa chứng minh người dùng đã dùng được. Với kênh email hoặc số điện thoại, phân biệt địa chỉ đã xác minh từ trước với địa chỉ vừa được nhập trong yêu cầu khôi phục.

NIST phân biệt các phương thức như saved recovery code, issued recovery code, recovery contact và repeated identity proofing, đồng thời quy định tổ hợp theo mức bảo đảm. Không suy ra hai mã trong cùng một bộ là hai phương thức độc lập. [NIST SP 800-63B-4, Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b/events/#account-recovery).

Nếu không có bằng chứng đủ mạnh, trạng thái đúng là **chưa đủ điều kiện khôi phục**, kèm cách khiếu nại hoặc hỗ trợ được thiết kế. Việc hỗ trợ nhanh hơn không được biến thành quyền bỏ qua xác minh.

## 5. Ngăn việc dùng KBA để đăng ký phương thức mới

Một lỗi chuyển đổi nguy hiểm là:

~~~text
Trả lời đúng câu hỏi cũ
  -> được thêm passkey mới
  -> được đánh dấu đã chuyển đổi an toàn
~~~

Kẻ tấn công chỉ cần thắng KBA một lần để có phương tiện truy cập lâu dài. Sau đó xóa câu hỏi sẽ không xóa passkey của họ.

Luồng đăng ký thay thế cần chứng minh quyền kiểm soát bằng bằng chứng **độc lập với KBA** và đủ cho thao tác:

1. Xác thực lại bằng phương tiện đã đăng ký hoặc hoàn tất recovery được phê duyệt.
2. Kiểm tra nguồn gốc, thời gian và tài khoản của bằng chứng ở backend.
3. Tạo challenge đăng ký mới, ràng buộc với tài khoản và giao dịch.
4. Kiểm chứng kết quả đăng ký theo giao thức.
5. Xác nhận phương tiện mới có thể hoàn thành một thao tác chứng minh quyền kiểm soát thích hợp.
6. Thông báo qua kênh đã đăng ký và ghi audit không chứa bí mật.

Một session còn cookie không đồng nghĩa với bằng chứng đủ mạnh. Session có thể bị đánh cắp, quá cũ hoặc vừa được tạo qua KBA. OWASP khuyến nghị xác thực lại khi thay yếu tố và không chỉ dựa vào session đang hoạt động. [OWASP Multifactor Authentication, Changing MFA Factors](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors).

Trong mô hình chuyển đổi, nên lưu metadata như `verified_method`, `verified_at`, `credential_id`, `purpose` và nguồn gốc của grant. Metadata được ghi bởi thành phần xác minh tin cậy, không lấy từ trường `method=PASSKEY` do client gửi.

Không đánh dấu người dùng “sẵn sàng” chỉ vì đã gửi email mời đăng ký, đã mở trang hoặc đã tải tệp backup code. Mốc sẵn sàng phải gắn với bằng chứng phương tiện đã được thiết lập hợp lệ và đường dùng của nó đã được xác nhận theo chính sách.

## 6. Lộ trình chuyển đổi có mốc đóng rõ ràng

### 6.1. Tách trạng thái chuyển đổi khỏi mức sẵn sàng

Có thể dùng hai trục thay vì một cờ `migrated`:

~~~text
Trạng thái cơ chế:
  LEGACY_PRESENT -> PREPARED -> KBA_DISABLED -> DATA_PURGED

Trạng thái người dùng:
  UNASSESSED
  ALTERNATIVE_READY
  NEEDS_ASSISTED_RECOVERY
~~~

`PREPARED` nghĩa là hạ tầng thay thế đã sẵn sàng, không có nghĩa mọi người dùng đã có phương tiện. `KBA_DISABLED` nghĩa là không còn chấp nhận KBA; dữ liệu có thể vẫn đang chờ xử lý theo vòng đời lưu trữ. `DATA_PURGED` cần có định nghĩa phạm vi và trạng thái bản sao lưu, không được dùng để che các bản sao còn tồn tại.

### 6.2. Các giai đoạn triển khai

| Giai đoạn | Việc thực hiện | Điều kiện đi tiếp |
|---|---|---|
| 1. Dừng phát sinh mới | Ngừng yêu cầu tạo/cập nhật câu hỏi; bỏ trường bắt buộc ở tài khoản mới | Không còn đường ghi mới ngoài hoạt động xử lý dữ liệu được kiểm soát |
| 2. Chuẩn bị thay thế | Cung cấp phương thức dự phòng và quy trình hỗ trợ | Luồng đăng ký, sử dụng, thu hồi và thông báo hoạt động được |
| 3. Chuyển đổi theo nhóm | Mời người dùng thiết lập phương tiện; ngừng KBA cho nhóm đạt điều kiện | Bằng chứng sẵn sàng được ghi nhận và backend chặn đường cũ |
| 4. Đóng hoàn toàn | Ngừng KBA trên mọi kênh, xử lý artifact còn mở | Không có nơi cấp hoặc nhận quyền dựa vào KBA |
| 5. Xử lý dữ liệu và mã legacy | Xóa dữ liệu theo kế hoạch, bỏ dependency và code cũ | Có bằng chứng xóa, kiểm soát restore và không còn khả năng tự mở lại |

Trong giai đoạn chuyển tiếp, nhóm chưa chuyển đổi có thể vẫn còn rủi ro legacy. Nếu một tổ chức chấp nhận duy trì tạm thời, cần xác định phạm vi, thời hạn và người chịu trách nhiệm; không gọi hệ thống là đã loại bỏ KBA trong thời gian đó. Với đường có nguy cơ cao hoặc đang bị khai thác, có thể phải đóng sớm và chuyển người dùng sang recovery phù hợp.

Không để một cohort ngoại lệ tồn tại vô thời hạn chỉ vì sợ ảnh hưởng chỉ số đăng nhập. Người dùng lâu không hoạt động cũng cần chính sách quay lại; không thể chờ họ đăng nhập hết rồi mới đóng cơ chế cũ.

## 7. Thực thi ở backend và tương thích client

### 7.1. Quyết định quyền phải dựa trên chính sách hiện tại

Sau cutover, backend không được chấp nhận kết quả KBA dù client cũ vẫn hiển thị form. Nơi quyết định tạo reset token, recovery grant, session hoặc đăng ký authenticator đều phải thực thi quy tắc này.

Ví dụ Java dưới đây là **mã giả về ranh giới quyết định**; các lớp và hàm phụ trợ cần được triển khai theo kiến trúc thực tế:

~~~java
void authorizeRecovery(
        VerifiedAttempt attempt,
        AccountSecurity account,
        RecoveryPolicy currentPolicy,
        Instant now) {

    require(account.enabled());
    require(attempt.accountId().equals(account.accountId()));
    require(attempt.isOpen());
    require(attempt.expiresAt().isAfter(now));
    require(attempt.isBoundToCurrentContext());
    require(attempt.policyVersion() == currentPolicy.version());
    require(attempt.recoveryEpoch() == account.recoveryEpoch());

    // provenance gồm cả nguồn gốc kế thừa từ grant/session trước.
    require(!attempt.provenance().contains(ProofKind.LEGACY_KBA));

    for (VerifiedProof proof : attempt.proofs()) {
        require(currentPolicy.accepts(proof.kind()));
    }

    // Kiểm tra đủ tổ hợp và đủ mới cho đúng thao tác.
    // "Không có KBA" chưa có nghĩa là đã đủ bằng chứng.
    currentPolicy.requireEvidenceFor(
            attempt.purpose(), attempt.proofs(), account, now);
}
~~~

`VerifiedAttempt` phải được tạo từ kết quả xác minh phía máy chủ. Không deserialize payload người dùng vào kiểu này rồi tin các trường `verified` hoặc `provenance`.

Nguồn gốc cần bao gồm chuỗi quyền kế thừa. Nếu một session được tạo từ KBA rồi đổi lấy grant mang nhãn “session”, chỉ kiểm tra proof cuối cùng sẽ bỏ sót KBA phía trước. Với artifact thiếu provenance, áp dụng chính sách bảo thủ như thu hồi hoặc yêu cầu xác thực lại; không mặc định coi là bằng chứng mạnh.

### 7.2. Endpoint đã ngừng

Một endpoint chỉ phục vụ câu hỏi cũ có thể trả phản hồi công khai cố định, ví dụ:

~~~http
HTTP/1.1 410 Gone
Content-Type: application/json
Cache-Control: no-store

{
  "code": "RECOVERY_METHOD_RETIRED",
  "message": "Phương thức này đã ngừng hỗ trợ. Hãy dùng luồng khôi phục hiện tại."
}
~~~

Đây là lựa chọn API minh họa. Phản hồi không thay đổi theo tài khoản có tồn tại, câu trả lời có đúng hoặc người đó đã chuyển đổi hay chưa.

Không nhận request cũ rồi bỏ qua trường câu trả lời và tiếp tục reset mật khẩu. Nếu endpoint mới có hợp đồng khác, client phải đi qua đầy đủ bằng chứng của hợp đồng mới. Việc “bỏ kiểm tra câu hỏi” trong một chuỗi `if` có thể vô tình biến cơ chế cũ thành không cần bằng chứng.

### 7.3. Client cũ, cache và hệ thống bên ngoài

Backend là điểm kiểm soát cuối cùng. Gỡ form, bản dịch, bộ nhớ đệm và nội dung CDN giúp giảm nhầm lẫn nhưng không thay thế chặn server.

Trong rollout nhiều phiên bản, một node cũ còn logic cấp quyền là đủ để giữ lỗ hổng. Cần có hàng rào chính sách tương thích với các node đang chạy, dừng node không đáp ứng hoặc chặn route liên quan cho đến khi toàn bộ đường cấp quyền đạt yêu cầu.

Với IdP hoặc đối tác, cần xác nhận cách họ xác thực và assurance được truyền tới ứng dụng. Không tự cho rằng bật MFA ở ứng dụng là đủ nếu đối tác vẫn có thể reset yếu tố bằng KBA rồi phát assertion được ứng dụng tin cậy.

## 8. Cutover, yêu cầu đang chạy và trạng thái đã cấp

### 8.1. Không chỉ chặn yêu cầu mới

Trước thời điểm đóng, hệ thống có thể đã cấp:

- Challenge câu hỏi đang chờ trả lời.
- Reset token sau khi trả lời đúng.
- Recovery grant để gỡ MFA hoặc thay passkey.
- Session hoặc refresh token có nguồn gốc KBA.
- Credential mới được đăng ký nhờ một trong các quyền trên.

Ngừng endpoint phát hành không làm các artifact đó tự mất hiệu lực. Mỗi loại cần quyết định thu hồi, hạn chế hoặc yêu cầu xác thực lại.

### 8.2. Ranh giới nguyên tử

Một mô hình triển khai dùng hàng trạng thái bảo mật của tài khoản làm điểm phối hợp. Mọi đường cấp hoặc sử dụng quyền recovery phải kiểm tra phiên bản chính sách và epoch tương ứng.

~~~text
BEGIN
  khóa trạng thái bảo mật của tài khoản
  bật kba_disabled
  tăng recovery_policy_version và recovery_epoch
  hủy challenge KBA và attempt không còn hợp lệ
  thu hồi grant/token recovery bị ảnh hưởng
  ghi audit và outbox
COMMIT
~~~

Đây là khung thuật toán, không phải lệnh SQL chạy trực tiếp. Quyết định chính sách có thể chọn hủy toàn bộ recovery attempt/grant đang mở của tài khoản để đơn giản hóa trường hợp thiếu nguồn gốc; đây là đánh đổi trải nghiệm cần thông báo rõ.

Cả đường phát hành và đường hoàn tất recovery phải phối hợp với cùng trạng thái. Khi có hai request cạnh tranh:

- Nếu cutover commit trước, request cũ đọc thấy chính sách mới và bị từ chối.
- Nếu cấp grant commit trước, cutover phải làm grant đó mất hiệu lực theo chính sách.
- Khi grant được sử dụng, backend kiểm tra lại epoch và trạng thái thay vì chỉ tin chữ ký token.

Nếu chỉ nơi phát hành kiểm tra chính sách, grant cũ vẫn có thể vượt cutover tại nơi hoàn tất. Nếu chỉ gateway chặn route công khai, dịch vụ nội bộ hoặc job đang chạy vẫn có thể cấp quyền.

### 8.3. Hệ phân tán và token tự chứa

Tăng `recovery_epoch` chỉ có tác dụng khi nơi nhận token thực sự đối chiếu epoch. Một JWT vẫn có chữ ký hợp lệ có thể tiếp tục được chấp nhận nếu dịch vụ chỉ kiểm tra chữ ký và `exp`.

Chọn cơ chế thu hồi phù hợp: tra trạng thái tập trung, phiên bản được kiểm tra đáng tin cậy, denylist hoặc một thiết kế token khác. TTL ngắn chỉ giới hạn cửa sổ tồn tại; nó không tương đương với thu hồi tức thời.

Nếu chính sách được phân phối qua cache hoặc cấu hình, phải xác định thời gian lan truyền và cách xử lý node có dữ liệu cũ. Không được tuyên bố “đã đóng hoàn toàn” trong khi có nơi vẫn dùng snapshot cho phép KBA. Khi không đọc được chính sách bắt buộc, dừng cấp quyền hoặc chuyển sang xử lý có kiểm soát; không tự quay về câu hỏi.

## 9. Xử lý credential đã được đăng ký nhờ KBA

Cần phân biệt **ngừng một cơ chế yếu** với **xử lý một vụ chiếm đoạt đã xảy ra**. Có nguồn gốc KBA không chứng minh người dùng là kẻ tấn công, nhưng cũng không đủ để coi phương tiện được tạo ra từ đó có độ tin cậy mới cao hơn.

Ví dụ:

~~~text
KBA thành công ở ngày trước cutover
  -> reset mật khẩu
  -> tạo session
  -> đăng ký passkey mới
  -> dùng passkey sau cutover
~~~

Nếu chỉ chặn KBA trực tiếp, passkey ở cuối chuỗi vẫn hoạt động. Cần đánh giá chuỗi cấp quyền theo lịch sử có được, thời điểm phát sinh và dấu hiệu rủi ro.

Các hướng xử lý có thể gồm:

- Yêu cầu xác thực lại bằng phương tiện đã tồn tại độc lập trước sự kiện KBA.
- Cô lập credential mới khỏi thao tác nhạy cảm cho đến khi đủ bằng chứng.
- Thu hồi credential hoặc session bị nghi chiếm đoạt theo quy trình sự cố.
- Chuyển sang recovery có kiểm soát nếu không còn bằng chứng độc lập.

Không chỉ đổi nhãn `origin=PASSKEY` để xóa lịch sử nguồn gốc. Cũng không tự động xóa mọi credential không có metadata mà không phân tích hậu quả khóa nhầm người dùng. Thiếu lịch sử là một rủi ro cần chính sách xử lý và phạm vi hành động cụ thể.

Nếu phát hiện thông tin liên hệ đã bị đổi trong chuỗi đó, gửi mã tới địa chỉ hiện tại có thể chỉ trao thêm quyền cho người đang chiếm tài khoản. Quy trình hỗ trợ cần xem xét lịch sử thay đổi và kênh liên hệ đáng tin cậy theo chính sách sự cố, không lấy một trường vừa bị sửa làm gốc tin cậy mới.

## 10. Loại bỏ dữ liệu câu hỏi và câu trả lời

### 10.1. Ngừng sử dụng trước, dọn dữ liệu có kiểm soát sau

Trình tự thực tế thường là:

1. Ngừng thu thập và thay đổi câu hỏi/câu trả lời.
2. Ngừng đọc chúng để đưa ra quyết định bảo mật.
3. Chặn quyền đọc không còn cần thiết của dịch vụ và nhân viên.
4. Xóa dữ liệu tại các kho hoạt động theo kế hoạch.
5. Xử lý bản sao, backup, restore và chứng cứ hoàn tất.

Không nên xóa bảng đang được phiên bản cũ yêu cầu bắt buộc rồi vô tình làm hỏng đăng nhập hoặc tạo lỗi fallback. Chuẩn bị tương thích schema và triển khai hành vi ngừng sử dụng trước khi bỏ trường.

Ngược lại, giữ dữ liệu trong database chỉ để “rollback khi cần” sẽ kéo dài rủi ro. Nếu còn yêu cầu lưu theo chính sách retention đã xác định, cần ghi rõ phạm vi, mục đích, người được truy cập và thời điểm xử lý tiếp; dữ liệu được giữ không được quay lại phục vụ xác thực.

### 10.2. Những loại dữ liệu cần xử lý

| Loại dữ liệu | Cách nhìn khi loại bỏ |
|---|---|
| Câu trả lời rõ | Bí mật legacy và có thể là dữ liệu cá nhân |
| Hash/verifier, salt, metadata đối sánh | Vẫn là dữ liệu liên quan tới câu trả lời; không mặc nhiên vô hại |
| Câu hỏi tùy chỉnh và hint | Có thể chứa tên thật, số điện thoại hoặc gợi ý mật khẩu |
| Log, trace, replay, ticket | Có thể đã sao chép câu trả lời hoặc request body |
| Cache, index, kho phân tích | Bản sao cần có owner và cơ chế xóa |
| Backup, snapshot, môi trường thử nghiệm | Cần retention, kiểm soát truy cập và kế hoạch restore |

Không giải mã hoặc dò hash để “xem câu trả lời nào cần xóa”. Cũng không chuyển chúng thành câu hỏi cho chatbot, tín hiệu xác thực hỗ trợ hoặc tập dữ liệu thử nghiệm mới.

Tránh điền câu trả lời giả, chuỗi rỗng hoặc giá trị mặc định để thỏa `NOT NULL`. Một nhánh legacy có thể coi các giá trị đó là câu trả lời hợp lệ. Hãy thay đổi schema và bỏ dependency theo kế hoạch.

### 10.3. Xóa theo lô và chứng cứ

Với dữ liệu lớn, thực hiện job có khả năng tiếp tục, checkpoint theo khóa ổn định và giới hạn tải. Đảm bảo đường ghi cũ đã bị chặn để dữ liệu không xuất hiện lại sau khi job đi qua.

Chứng cứ hoàn tất có thể gồm số bản ghi xử lý, phạm vi kho dữ liệu, mốc thời gian, phiên bản job và kết quả kiểm tra không còn đường đọc/ghi nghiệp vụ. Không lưu nguyên câu hỏi hoặc hash vào audit chỉ để chứng minh đã xóa chúng.

Không đồng nhất `UPDATE ... SET answer = NULL` với việc xóa mọi bản sao vật lý ngay lập tức: log giao dịch, replica, snapshot và hệ thống lưu trữ còn có vòng đời riêng. Mức cam kết phải phản ánh đúng những nơi đã xử lý và những nơi đang chờ hết hạn.

### 10.4. Backup và phục hồi hệ thống

Một backup cũ có thể chứa đồng thời câu trả lời, cờ `kba_enabled=true` và token chưa bị thu hồi. Khôi phục nó nguyên trạng có thể làm cơ chế cũ sống lại.

Kế hoạch restore cần có hàng rào trước khi phục vụ người dùng:

~~~text
Khôi phục vào vùng cách ly
  -> áp dụng chính sách ngừng KBA và phiên bản hiện hành
  -> xử lý lại dữ liệu/credential bị ảnh hưởng
  -> vô hiệu hóa artifact cũ theo chính sách
  -> xác minh backend không còn cấp quyền nhờ KBA
  -> mới mở phục vụ
~~~

Không giả định có thể sửa trực tiếp mọi bản sao lưu bất biến. Theo dõi chúng bằng vòng đời retention và kiểm soát truy cập phù hợp; mọi lần restore phải qua bước xử lý. Nếu dùng hủy khóa mã hóa như một phần giải pháp, phải chứng minh dữ liệu thực sự được mã hóa bằng khóa riêng và mọi bản sao khóa liên quan đã được xử lý. Một khóa dùng chung với dữ liệu còn cần sử dụng không thể tùy ý bị hủy.

## 11. Thay quy trình hỗ trợ và quản trị

Nếu tổng đài vẫn hỏi “tên trường học đầu tiên” rồi bấm gỡ MFA, hệ thống chưa loại bỏ KBA.

Quy trình mới cần có:

- Danh sách bằng chứng được chấp nhận cho từng tình huống.
- Cách kiểm chứng bằng chứng và mối liên hệ với tài khoản cần khôi phục.
- Phạm vi thao tác nhân viên được thực hiện.
- Cơ chế phê duyệt bổ sung với trường hợp rủi ro cao.
- Thời hạn, audit, thông báo và cách hủy yêu cầu.
- Kênh xử lý khi không đủ bằng chứng hoặc người dùng khiếu nại.

Nhân viên có thể hỏi thông tin để tìm hồ sơ hoặc hiểu sự cố, nhưng câu trả lời khớp hồ sơ không được trở thành bằng chứng duy nhất để cấp quyền.

Ảnh chụp giấy tờ, hóa đơn hoặc email chuyển tiếp cũng không tự tạo một quy trình xác minh danh tính đáng tin cậy. Cần xác minh tính hợp lệ của bằng chứng và quan hệ của người đang yêu cầu với bằng chứng, đồng thời xét xem tài khoản ban đầu có được gắn với danh tính đó hay không. Với tài khoản chưa từng được proofing, một giấy tờ mới có thể không chứng minh quyền sở hữu tài khoản cũ.

Công cụ hỗ trợ nên gọi cùng dịch vụ cấp grant có chính sách và audit. Nếu cần ngoại lệ quản trị, ngoại lệ phải có phạm vi, điều kiện và kiểm soát rõ; không dùng một nút “đã xác minh” bỏ qua toàn bộ bằng chứng. Việc nhân viên đăng nhập thành công chỉ chứng minh danh tính nhân viên, không chứng minh danh tính người gọi.

Chatbot và trợ lý tự động cũng phải tuân theo quy tắc này. Không để một mô hình ngôn ngữ kết luận “câu chuyện có vẻ hợp lý” rồi cấp quyền hoặc suy đoán câu trả lời từ hồ sơ.

Đào tạo đội hỗ trợ trước thời điểm đóng: cách giải thích thay đổi, tiếp nhận người chưa chuyển đổi, xử lý dấu hiệu lừa đảo và chuyển tuyến. Gỡ tài liệu, macro trả lời và màn hình CRM còn khuyến khích thu thập câu trả lời.

## 12. Trải nghiệm chuyển đổi và thông báo

### 12.1. Mời đăng ký khi người dùng còn quyền truy cập

Thời điểm thuận lợi là sau khi người dùng vừa hoàn thành xác thực phù hợp, trước khi họ bị mất phương tiện.

Nội dung thông báo có thể là:

> Chúng tôi sẽ ngừng sử dụng câu hỏi bảo mật từ [ngày áp dụng]. Hãy mở phần Bảo mật trong tài khoản để thiết lập phương thức khôi phục phù hợp. Chúng tôi không yêu cầu bạn gửi câu trả lời bảo mật qua email hoặc chat.

`[ngày áp dụng]` là chỗ điền theo kế hoạch thực tế, không phải một lịch đã được thiết lập trong bài học.

Giao diện nên cho người dùng biết phương thức nào đã thiết lập thành công, phương thức nào còn cần xác minh và cách lưu mã dự phòng an toàn. Không bắt nhập lại câu trả lời cũ để xóa câu hỏi hoặc rời khỏi cơ chế đó.

Khuyến khích phương án dự phòng tách khỏi điểm hỏng chính. Hai bản sao cùng chỉ có trên một điện thoại bị mất không đem lại mức dự phòng giống hai nơi lưu độc lập. Chính sách cần xét cả khả năng người dùng không có điện thoại thông minh hoặc không dùng được một loại authenticator.

### 12.2. Sau khi ngừng cơ chế

Phản hồi ở luồng công khai có thể là:

> Câu hỏi bảo mật đã ngừng hỗ trợ. Bạn có thể tiếp tục bằng phương thức khôi phục hiện có hoặc xem quy trình hỗ trợ.

Không hiển thị danh sách phương tiện, địa chỉ liên hệ đầy đủ hoặc tình trạng chuyển đổi của một tài khoản trước khi đủ ngữ cảnh được phép. OWASP khuyến nghị phản hồi nhất quán cho yêu cầu quên mật khẩu để giảm khả năng dò tài khoản. [OWASP Forgot Password, Forgot Password Request](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#forgot-password-request).

Không gửi lại câu trả lời để “nhắc người dùng trước khi xóa”. Không thông báo “mọi dữ liệu đã được xóa” nếu backup và các kho khác vẫn đang được xử lý theo kế hoạch.

### 12.3. Người dùng chưa chuyển đổi hoặc mất toàn bộ phương tiện

Cần có đường tiếp nhận dễ tìm, giải thích bằng chứng cần thiết và trạng thái xử lý. Tránh buộc họ lặp lại đăng ký phương tiện mới khi chính việc đăng ký đòi hỏi quyền họ chưa có.

Cơ chế hỗ trợ không nên hứa chắc chắn lấy lại tài khoản. Với bằng chứng không đủ, có thể cần trì hoãn hoặc từ chối theo chính sách. Trải nghiệm tốt là giúp người dùng hiểu bước tiếp theo và có kênh khiếu nại, đồng thời giữ yêu cầu xác minh.

## 13. Chống lạm dụng trong thời gian chuyển đổi

Một đợt thay đổi lớn có thể làm tăng yêu cầu recovery hợp lệ và cả nỗ lực lợi dụng hỗ trợ.

Các kiểm soát cần được giữ ở cả luồng mới lẫn endpoint đã ngừng:

- Giới hạn thử và tạo yêu cầu theo tài khoản/định danh đích, attempt và nguồn truy cập.
- Giới hạn gửi email hoặc thông báo để tránh quấy rối người dùng.
- Không khóa vĩnh viễn tài khoản chỉ vì người lạ gửi nhiều yêu cầu sai.
- Ràng buộc token với tài khoản, mục đích, attempt, thời hạn và trạng thái sử dụng.
- Cấp quyền tối thiểu cho bước recovery, không tự tạo session đầy đủ.
- Thông báo các thay đổi nhạy cảm qua kênh đã thiết lập.
- Theo dõi thay đổi địa chỉ liên hệ ngay trước hoặc trong recovery.

Mã hoặc token dùng một lần phải được tiêu thụ nguyên tử. Xóa KBA nhưng thêm luồng email có token dùng lại được sẽ đưa vào rủi ro mới. Các token khôi phục cần ngẫu nhiên, đủ dài, được lưu an toàn và vô hiệu hóa sau sử dụng. [OWASP Forgot Password, General Security Practices](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#general-security-practices).

Giới hạn thử không chỉ nằm trong cache cục bộ của một node nếu hệ thống có nhiều instance. Việc tạo attempt mới cũng không được làm mất toàn bộ lịch sử backoff của tài khoản.

Log cần phân biệt lỗi tích hợp client cũ với yêu cầu recovery thất bại và tín hiệu tấn công, nhưng không ghi câu trả lời. Với endpoint KBA đã ngừng, thường chỉ cần metadata tối thiểu như phiên bản client, route và mã kết quả; không còn lý do nghiệp vụ để lưu body chứa bí mật.

## 14. Đo lường và phương án khi rollout có lỗi

### 14.1. Đo cả sự sẵn sàng và việc chặn cơ chế

Các chỉ số trả lời những câu hỏi khác nhau:

| Chỉ số | Câu hỏi cần trả lời |
|---|---|
| Tỷ lệ tài khoản có phương thức thay thế đã xác nhận | Người dùng có sẵn sàng chuyển đổi không? |
| Số tài khoản còn cần assisted recovery | Năng lực hỗ trợ cần chuẩn bị là bao nhiêu? |
| Số quyền mới được cấp từ KBA | Backend đã thực sự đóng cơ chế chưa? |
| Số artifact nguồn KBA còn hiệu lực | Có còn quyền tồn tại qua cutover không? |
| Số lượt gọi endpoint cũ theo client/tenant | Còn tích hợp nào chưa nâng cấp? |
| Tỷ lệ hoàn tất recovery và thời gian hỗ trợ | Người dùng hợp lệ bị ảnh hưởng thế nào? |
| Số đường ghi dữ liệu legacy và lượng dữ liệu còn lại | Việc ngừng thu thập/xử lý dữ liệu tiến triển ra sao? |
| Mốc hoàn tất của các kho sao chép và backup | Cam kết xử lý dữ liệu có phản ánh đủ phạm vi không? |

Tỷ lệ gọi endpoint cũ bằng 0 không chứng minh endpoint đã bị chặn: có thể chưa ai gọi trong cửa sổ đo. Ngược lại, nhiều response `410` sau cutover không đồng nghĩa với KBA còn được chấp nhận.

Không coi “không có cảnh báo chiếm đoạt” là bằng chứng hệ thống an toàn. Kết hợp dữ liệu vận hành với kiểm chứng đường cấp quyền và kết quả kiểm thử.

### 14.2. Không mở lại KBA để xử lý outage

Khi phương thức mới gặp lỗi, phương án ứng phó có thể là:

- Dừng chuyển thêm nhóm người dùng trong giai đoạn chưa cutover.
- Khôi phục phiên bản ứng dụng tương thích với chính sách KBA đã bị vô hiệu hóa.
- Sửa hoặc chuyển sang một phương thức thay thế đã được phê duyệt.
- Tạm dừng thao tác nhạy cảm và chuyển hỗ trợ theo chính sách.

Sau khi một nhóm đã ngừng KBA, việc quay lại chấp nhận câu trả lời là một thay đổi mức tin cậy và mở lại đường tấn công. Không để rollback code hoặc restore database tự làm điều đó.

Cần tách rollback ứng dụng khỏi rollback quyết định bảo mật. Trước khi hạ phiên bản, xác nhận bản cũ hiểu cờ ngừng KBA, phiên bản chính sách và schema hiện hành. Nếu không, không cho phiên bản đó phục vụ đường cấp quyền liên quan.

Cờ cấu hình có quyền mở lại cơ chế cũ cũng là một đường truy cập cần kiểm soát. Sau khi hoàn tất, bỏ khả năng mở lại bằng cấu hình thông thường và xóa code legacy theo kế hoạch.

## 15. Tình huống chuyển đổi minh họa

Một nền tảng học tập giả định có các nhóm:

| Nhóm | Số tài khoản minh họa | Tình trạng |
|---|---:|---|
| A | 6.000 | Có phương tiện độc lập đủ điều kiện và dùng được |
| B | 3.000 | Còn đăng nhập được nhưng chưa có phương án dự phòng phù hợp |
| C | 1.000 | Chỉ còn đường KBA hoặc chưa xác định được khả năng khôi phục |

Các con số chỉ phục vụ bài học, không phải dữ liệu của một hệ thống thật.

Nhóm A có thể được chuyển sớm sau khi backend và artifact liên quan đã xử lý. Nhóm B được mời đăng ký phương án phù hợp sau xác thực lại. Nhóm C cần phân loại sâu hơn và chuẩn bị assisted recovery; không tự đánh dấu họ đã sẵn sàng vì đã gửi email thông báo.

Một chuỗi triển khai có thể là:

1. Ngừng tạo câu hỏi mới, kiểm kê và thống nhất chính sách.
2. Chuẩn bị phương thức thay thế, hỗ trợ và audit.
3. Xác nhận phương tiện độc lập của nhóm A, rồi đóng KBA theo nhóm.
4. Chuyển nhóm B qua đăng ký và kiểm chứng phương án dự phòng.
5. Phân luồng nhóm C; công bố mốc đóng và cách xử lý trường hợp chưa đủ bằng chứng.
6. Cutover toàn hệ thống, thu hồi artifact liên quan và kiểm tra mọi điểm cấp quyền.
7. Xử lý dữ liệu và loại bỏ code/cấu hình legacy.

Giả sử một người đã trả lời câu hỏi thành công trước cutover và có reset token còn hạn. Sau cutover, endpoint đổi mật khẩu phải từ chối token theo epoch hoặc cơ chế thu hồi, dù chữ ký và thời hạn vẫn hợp lệ. Nếu chỉ kiểm tra lúc cấp token, đường recovery cũ vẫn tồn tại.

Giả sử người khác đã dùng KBA để thêm passkey từ trước. Không được lấy chính passkey này làm bằng chứng độc lập duy nhất để đánh dấu quá trình chuyển đổi an toàn mà bỏ qua nguồn gốc. Cần xử lý theo chính sách lịch sử credential và dấu hiệu rủi ro ở mục 9.

## 16. Các tình huống cần kiểm chứng khi triển khai

Đây là danh sách tình huống học tập, không phải kết quả kiểm thử đã chạy trên một ứng dụng.

| Tình huống | Kết quả cần chứng minh |
|---|---|
| Tài khoản mới đăng ký | Không bị buộc tạo câu hỏi; không có dữ liệu KBA mới |
| Client cũ gửi câu trả lời đúng | Không được cấp reset token, grant hoặc session nhờ câu trả lời |
| Cùng endpoint với tài khoản không tồn tại | Phản hồi không tiết lộ trạng thái hồ sơ |
| Tài khoản đã có passkey chọn fallback | Không quay lại KBA |
| Session được tạo từ KBA yêu cầu thêm credential | Không được coi là bằng chứng độc lập đủ mạnh |
| Proof mang nhãn mạnh nhưng có nguồn gốc KBA | Chính sách xử lý cả chuỗi provenance |
| Payload tự khai `verified=true` hoặc `method=PASSKEY` | Backend không tin dữ liệu này như kết quả xác minh |
| Token KBA cấp trước cutover được dùng sau cutover | Bị thu hồi hoặc từ chối theo chính sách hiện tại |
| Grant được cấp đồng thời với cutover | Không vượt quyết định vô hiệu hóa tại bước sử dụng |
| Một node hoặc tenant chưa cập nhật | Không còn khả năng cấp quyền qua cơ chế cũ |
| Chính sách hoặc dịch vụ xác minh không khả dụng | Không fallback sang KBA |
| Nhân viên hỗ trợ có câu trả lời khớp hồ sơ | Không thể cấp quyền chỉ từ câu trả lời |
| Người dùng chưa có phương tiện thay thế | Có đường xử lý rõ, không tự hạ yêu cầu bằng chứng |
| Job xóa chạy lại hoặc dừng giữa chừng | Có thể tiếp tục, không tái tạo dữ liệu và không ghi bí mật vào audit |
| Restore backup từ trước cutover | Hàng rào ngừng KBA được áp dụng trước khi phục vụ |
| Rollback sang phiên bản cũ | Không tự mở lại KBA hoặc bỏ kiểm tra epoch |
| Phương thức thay thế dùng token | Token vẫn được ràng buộc và tiêu thụ dùng một lần |
| Dashboard không ghi nhận gọi KBA | Vẫn có kiểm chứng trực tiếp việc đường cũ bị từ chối |

Kiểm thử phải quan sát **quyền thật sự được cấp hoặc được sử dụng**, không chỉ giao diện hoặc mã HTTP. Một response báo thất bại nhưng đã phát reset token qua email vẫn là lỗi.

Các tài khoản và câu trả lời trong kiểm thử cần là dữ liệu tổng hợp. Không sao chép câu trả lời thật từ production vào fixture để chứng minh migration.

## 17. Tiêu chí hoàn tất và tài liệu đối chiếu

Một đợt loại bỏ hoàn tất về mặt kiểm soát truy cập khi:

- Không còn cơ chế đăng ký, xác minh hoặc hỗ trợ dùng KBA để cấp quyền.
- Mọi nơi cấp và sử dụng artifact tuân theo chính sách sau cutover.
- Token, session và credential có nguồn gốc liên quan đã được xử lý theo phạm vi xác định.
- Người dùng có đường chuyển đổi hoặc hỗ trợ được công bố và đủ năng lực vận hành.
- Rollback, restore, client cũ và đối tác không tự mở lại đường cũ.

Hoàn tất xử lý dữ liệu là mốc bổ sung: ngừng ghi mới, xử lý các kho hoạt động, theo dõi bản sao lưu và có chứng cứ phản ánh đúng phạm vi còn tồn tại. Báo cáo hai mốc riêng để không nhầm “không còn dùng để xác thực” với “đã xóa hết mọi bản sao”.

Các nguồn đối chiếu chính:

- [NIST SP 800-63-4 — Digital Identity Guidelines](https://pages.nist.gov/800-63-4/sp800-63.html#authenticators): phạm vi KBA trong xác thực số.
- [NIST SP 800-63A-4 — Identity Verification](https://pages.nist.gov/800-63-4/sp800-63a.html#identity-verification): phân biệt thông tin định tuyến với bằng chứng xác minh danh tính.
- [NIST SP 800-63B-4 — Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b/events/#account-recovery): phương thức và yêu cầu khôi phục.
- [OWASP Choosing and Using Security Questions](https://cheatsheetseries.owasp.org/cheatsheets/Choosing_and_Using_Security_Questions_Cheat_Sheet.html#introduction): lưu ý về phạm vi legacy.
- [OWASP Multifactor Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors): kiểm soát thay yếu tố.
- [OWASP Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): phản hồi công khai và vòng đời token.

Các trạng thái migration, epoch, mẫu API, mã Java và lộ trình trong bài là thiết kế minh họa. Áp dụng tiêu chuẩn cần đối chiếu đúng phạm vi và yêu cầu của tổ chức; bài học không tự xác nhận một hệ thống đã tuân thủ hoặc đã thực hiện chuyển đổi.
