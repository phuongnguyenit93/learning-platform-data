# Thời hạn của challenge xác minh tăng cường (Step up challenge timeout)

## 1. Timeout quyết định khi nào một phản hồi còn được chấp nhận

Trong chương **Step Up Verification** của module khôi phục tài khoản, challenge là một yêu cầu xác minh cụ thể mà backend phát hành để người dùng chứng minh quyền kiểm soát một phương tiện hoặc cung cấp bằng chứng phù hợp. Challenge có thể yêu cầu nhập mã được gửi đến kênh đã đăng ký, thực hiện xác thực bằng passkey còn dùng được, hoặc hoàn tất một bước trong phương án recovery.

**Challenge timeout** là giới hạn thời gian backend cho phép hoàn tất challenge đó. Sau giới hạn này, phản hồi phải bị từ chối dù mã hoặc chữ ký vẫn đúng về mặt tính toán.

Ví dụ, Lan mất điện thoại TOTP nhưng còn khóa bảo mật dự phòng. Ứng dụng phát challenge cho khóa dự phòng lúc 09:00, hết hạn lúc 09:03. Lan mở hộp thoại rồi chuyển sang việc khác. Đến 09:08, trình duyệt mới gửi assertion về. Một chữ ký hợp lệ không đủ để biến challenge đã hết hạn thành challenge còn hiệu lực.

Thiết kế timeout nhằm hạn chế thời gian khai thác challenge bị lộ, giảm khả năng dùng lại phản hồi cũ và buộc việc cấp quyền dựa trên bằng chứng còn phù hợp. Timeout phải đi cùng kiểm tra đúng tài khoản, đúng giao dịch, đúng thao tác và sử dụng một lần; một thời hạn ngắn không tự thay thế các kiểm tra đó.

Sau bài này, người học có thể thiết kế thời hạn ở từng lớp, xử lý resend và phản hồi đến muộn, xác định thời điểm chấp nhận ở backend, và duy trì quyền giới hạn khi recovery chưa hoàn tất.

## 2. Tách các loại thời hạn

Không nên dùng một biến timeout chung cho mọi thứ trong luồng recovery.

| Loại thời hạn | Đối tượng được giới hạn | Khi hết hạn |
| --- | --- | --- |
| Thời hạn challenge | Một yêu cầu xác minh đã phát hành | Không nhận thêm phản hồi cho challenge đó |
| Cửa sổ hợp lệ của mã | Mã gửi ngoài băng, bước thời gian TOTP hoặc token cụ thể | Không nhận mã ngoài điều kiện của cơ chế đó |
| Độ mới của bằng chứng | Khoảng thời gian được phép sử dụng kết quả đã xác minh | Cần xác minh lại nếu thao tác yêu cầu bằng chứng mới hơn |
| Thời hạn grant step-up | Quyền ngắn hạn cho một thao tác sau xác minh | Không thực hiện thao tác bằng grant đó |
| Thời hạn phiên recovery | Quyền truy cập phiên giới hạn đang xử lý | Cần khôi phục phiên theo cơ chế được thiết kế |
| Thời hạn giao dịch recovery | Toàn bộ hồ sơ xử lý của một yêu cầu | Đóng yêu cầu hoặc chuyển sang quy trình tiếp tục được kiểm soát |
| Thời gian chờ gửi lại | Tần suất phát hoặc gửi challenge | Chỉ quyết định lúc nào được xin gửi lại |
| Thời gian chờ bảo vệ | Khoảng trì hoãn trước thay đổi nhạy cảm | Vẫn cần đáp ứng các điều kiện bằng chứng và quyền |

Phiên có thể hết hạn trước giao dịch; giao dịch còn tồn tại không cho phép bất kỳ trình duyệt nào tự nối lại. Việc tiếp tục cần một cơ chế chứng minh quyền truy cập giao dịch.

Một kết quả đã được backend chấp nhận đúng hạn có thể được sử dụng sau khi challenge gốc hết hạn nếu độ mới của bằng chứng và grant vẫn đáp ứng policy. Ngược lại, giữ trình duyệt mở không giúp một challenge chưa hoàn tất kéo dài thời gian hiệu lực.

OWASP yêu cầu thực thi thời hạn phiên ở phía server; bộ đếm phía client không thể quyết định hiệu lực bảo mật. Xem [OWASP: Session Expiration](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#session-expiration).

## 3. Định nghĩa mốc thời gian trước khi chọn con số

Một policy timeout cần trả lời ít nhất bốn câu hỏi:

1. Đồng hồ bắt đầu chạy khi nào?
2. Điều kiện nào tạo deadline hiệu lực?
3. Thời điểm nào được xem là đã chấp nhận phản hồi?
4. Sau khi chấp nhận, bằng chứng được dùng đến lúc nào và cho việc gì?

### 3.1. Điểm bắt đầu

Trong mô hình của bài, challenge bắt đầu có hiệu lực khi backend lưu thành công bản ghi phát hành. Không lấy thời điểm người dùng nhìn thấy giao diện, thời điểm SMS được mở hoặc một timestamp do client khai báo làm điểm bắt đầu.

Nếu challenge được đưa vào hàng đợi gửi SMS, thời gian nằm trong hàng đợi vẫn tiêu tốn thời hạn đã cấp. Một delivery receipt không tự làm dịch chuyển expiresAt. Nếu thời hạn còn quá ít, hệ thống có thể không gửi mã cũ và đề nghị người dùng tạo challenge mới theo giới hạn hiện có.

Một hệ thống có thể chọn tạo challenge muộn hơn, gần lúc gửi thực tế, nhưng phải xác định rõ trạng thái trước phát hành và tính thời hạn từ mốc backend có thể kiểm soát. Không được vô tình tạo một mã có hiệu lực vô hạn chỉ vì chưa nhận được thông báo giao hàng.

### 3.2. Deadline hiệu lực

Với challenge chưa hoàn tất, deadline hiệu lực có thể được tính như sau:

~~~text
effectiveDeadline = min(
    challenge.expiresAt,
    recoveryTransaction.expiresAt,
    deadlineBắtBuộcCủaPhươngThức
)

còn_hạn = decisionTime < effectiveDeadline
hết_hạn = decisionTime >= effectiveDeadline
~~~

Nếu phương thức không có một deadline riêng, bỏ thành phần đó. Việc phiên recovery còn được phép hoạt động được kiểm tra đồng thời, bao gồm cả idle timeout nếu có.

Độ chính xác cần nhất quán: nếu backend so sánh tới mili giây, các lớp lưu trữ và API không nên âm thầm làm tròn theo cách gia hạn thêm. Trường hợp đúng bằng deadline phải có kết quả xác định; bài này chọn từ chối tại mốc bằng.

### 3.3. Thời điểm chấp nhận

Mô hình của bài chọn **thời điểm cập nhật nguyên tử challenge từ ISSUED sang CONSUMED sau khi đã kiểm chứng phản hồi** làm thời điểm chấp nhận. Tại điểm đó, backend kiểm tra lại thời hạn và các ràng buộc đang có hiệu lực.

Các mốc sau không đủ để thay thế:

- Người dùng bấm nút trước deadline.
- Trình duyệt ghi một timestamp trước deadline.
- API gateway nhận request trước deadline.
- Một worker bắt đầu kiểm tra chữ ký trước deadline.
- Một request đã đọc trạng thái ISSUED trước khi chờ khóa dữ liệu.

Ví dụ, API nhận request lúc 09:02:59 nhưng tới 09:03:02 mới hoàn tất kiểm chứng và có thể tiêu thụ challenge hết hạn lúc 09:03:00. Theo policy này, kết quả là hết hạn.

Đây là lựa chọn policy minh họa nhằm có ranh giới rõ ràng. Nếu sản phẩm dùng một quy tắc khác về thời điểm tiếp nhận, quy tắc đó cần được đặc tả và giới hạn việc xử lý tiếp theo; không thể chỉ tin timestamp từ client.

### 3.4. Thời điểm chấp nhận và thời điểm commit

Một transaction có thể tiêu thụ challenge ngay trước deadline rồi commit ngay sau đó. Theo định nghĩa trên, điều kiện thời gian được xét tại phép chuyển trạng thái nguyên tử, và chỉ có hiệu lực nếu transaction commit thành công.

Không nên mô tả quy tắc đó thành “mọi commit đều xảy ra trước deadline”. Nếu cần ràng buộc thao tác nhạy cảm ở bước sau, phải kiểm tra grant và các điều kiện của thao tác tại bước sau. Các transaction cũng cần ngắn và có giới hạn thời gian xử lý để tránh giữ quyết định ở trạng thái chưa commit quá lâu.

## 4. Chọn thời hạn theo cơ chế xác minh

Các con số trong bảng sau là **cấu hình giả định để minh họa**, không phải giá trị mặc định hay khuyến nghị chung cho mọi sản phẩm.

| Thành phần trong ứng dụng giả định | Giá trị minh họa | Cách hiểu |
| --- | --- | --- |
| Challenge passkey | 3 phút | Backend không chấp nhận assertion sau deadline |
| Challenge mã ngoài băng | 5 phút | Phải đáp ứng cả giới hạn của phương thức và policy áp dụng |
| Grant thay một authenticator | 2 phút | Chỉ dùng cho thao tác đã được duyệt |
| Độ mới của bằng chứng dùng cho grant | 5 phút | Tính từ thời điểm xác minh thực tế |
| Giao dịch recovery tự phục vụ | 30 phút | Resend không tự khởi động lại khoảng này |
| Khoảng chờ gửi lại | 30 giây | Không làm mã hiện tại sống lâu hơn |

Cần lựa chọn dựa trên tác động của thao tác, đặc điểm kênh gửi, thời gian thao tác thực tế, nhu cầu tiếp cận và quy định kỹ thuật áp dụng. Không chọn thời hạn dài chỉ để che độ trễ bất thường của nhà cung cấp.

### 4.1. Mã xác thực ngoài băng

Đối với xác thực ngoài băng thuộc phạm vi NIST SP 800-63B-4, việc xác thực phải hoàn tất trong mười phút; một secret chỉ được chấp nhận một lần. Phát sinh secret mới không được đặt lại bộ đếm xác thực thất bại. Xem [NIST: Out-of-Band Devices](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#ooba).

Mười phút ở đây là giới hạn của cơ chế được nêu, không phải lý do để mọi challenge đều sống mười phút. Policy có thể chọn thời hạn ngắn hơn và vẫn cần giới hạn thử mã.

### 4.2. TOTP

TOTP có cửa sổ kiểm tra dựa vào bước thời gian của authenticator. Thời hạn của giao dịch step-up là một lớp khác. Trong mô hình của bài, backend chỉ chấp nhận khi **cả cửa sổ mã lẫn challenge step-up đều hợp lệ**.

Không tăng cửa sổ TOTP thành vài phút chỉ vì luồng recovery cho người dùng vài phút thao tác. Nếu người dùng không kịp nhập mã đang hiện, họ dùng mã phù hợp ở thời điểm tiếp theo trong challenge còn hạn; backend vẫn áp dụng quy tắc chống dùng lại của phương thức.

### 4.3. Passkey và WebAuthn

Thuộc tính timeout của WebAuthn là gợi ý thời gian chờ cho client và có thể bị client điều chỉnh. Nó không thay thế deadline backend. Relying Party phải kiểm tra challenge trong phản hồi khớp challenge đã phát hành. Xem [W3C WebAuthn Level 3: Request Options](https://www.w3.org/TR/webauthn-3/#dictionary-assertion-options) và [Cryptographic Challenges](https://www.w3.org/TR/webauthn-3/#sctn-cryptographic-challenges).

Vì vậy, một hộp thoại xác thực còn mở không có nghĩa challenge ở backend còn sống. Một lỗi hủy hoặc lỗi chờ của hộp thoại cũng không tự chứng minh backend đã chuyển challenge sang EXPIRED; client cần lấy trạng thái hoặc tạo lại theo luồng được phép.

### 4.4. Recovery code và link email

Không gộp mọi mã được gửi qua email hoặc SMS vào cùng một nhóm “OTP step-up”. NIST quy định riêng issued recovery code: tối đa mười phút nếu gửi bằng tin nhắn hoặc thoại và tối đa hai mươi bốn giờ nếu gửi đến email, trong phạm vi mục tương ứng. Xem [NIST: Issued Recovery Codes](https://pages.nist.gov/800-63-4/sp800-63b/events/#issued-recovery-codes).

Đó là giới hạn tối đa cho loại mã được mô tả, không phải thời hạn mà mọi link email phải sử dụng. Mã recovery đã lưu từ trước cũng không tự có thời hạn vài phút như một challenge vừa phát hành. Khi người dùng trình mã đó trong giao dịch step-up, giao dịch và quyền được cấp vẫn có thời hạn riêng.

OWASP yêu cầu token đặt lại mật khẩu có thời hạn phù hợp và chỉ dùng một lần. Xem [OWASP: Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Một link còn hạn không đồng nghĩa người dùng được thay mọi yếu tố bảo mật: policy recovery vẫn phải quyết định bằng chứng đó có đủ cho thao tác đang yêu cầu hay không.

## 5. Vòng đời challenge: hết hạn không phụ thuộc tác vụ dọn rác

Một mô hình trạng thái đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> ISSUED: Backend phát hành
    ISSUED --> ISSUED: Phản hồi sai, còn ngân sách thử
    ISSUED --> CONSUMED: Phản hồi đúng và được chấp nhận đúng hạn
    ISSUED --> EXPIRED: Đã tới deadline
    ISSUED --> SUPERSEDED: Challenge mới thay thế
    ISSUED --> CANCELLED: Người dùng hoặc policy hủy
    ISSUED --> ATTEMPT_LIMIT_REACHED: Hết ngân sách thử
    CONSUMED --> [*]
    EXPIRED --> [*]
    SUPERSEDED --> [*]
    CANCELLED --> [*]
    ATTEMPT_LIMIT_REACHED --> [*]
~~~

Các trạng thái kết thúc không được chuyển về ISSUED. Nếu cần thử lại, tạo challenge mới theo policy.

Backend phải suy ra việc hết hạn từ deadline ngay trong đường kiểm tra. Một bản ghi vẫn ghi ISSUED trong cơ sở dữ liệu sau deadline là bản ghi **đã hết hiệu lực**, dù tác vụ nền chưa kịp cập nhật nhãn EXPIRED.

Tương tự, TTL của cache hoặc lịch xóa bản ghi chỉ phục vụ lưu trữ. Không để sự chậm trễ của tác vụ xóa trở thành khoảng thời gian được chấp nhận thêm.

### 5.1. Dữ liệu tối thiểu

Ví dụ bản ghi backend:

~~~json
{
  "challengeId": "ch-204",
  "tenantId": "tenant-a",
  "accountId": "account-42",
  "recoveryTransactionId": "rec-18",
  "recoverySessionBinding": "binding-7",
  "purpose": "AUTHORIZE_MFA_REPLACEMENT",
  "method": "EXISTING_PASSKEY",
  "generation": 2,
  "state": "ISSUED",
  "issuedAt": "2026-11-23T02:00:00Z",
  "expiresAt": "2026-11-23T02:03:00Z",
  "consumedAt": null,
  "policyVersion": "timeout-v1",
  "accountSecurityVersion": 12
}
~~~

Bản ghi cần thêm dữ liệu riêng theo phương thức, như nonce WebAuthn hoặc bộ kiểm chứng secret. Không lưu OTP ngắn bằng một hash nhanh rồi cho rằng đã tránh được đoán ngoại tuyến; lựa chọn cách lưu phải xét entropy thấp và mô hình lộ dữ liệu. Không ghi secret hay phản hồi xác thực nguyên văn vào log.

generation giúp nhận biết challenge nào đang được dùng trong một luồng gửi lại. Khi tạo challenge mới với nonce mới, kết quả kiểm chứng dựa trên thế hệ cũ không thể tự chuyển sang thế hệ mới.

accountSecurityVersion là một cách biểu diễn trạng thái bảo mật liên quan. Nếu có thay đổi khiến challenge không còn đáng tin, policy có thể vô hiệu hóa nó dù chưa tới deadline.

### 5.2. Thời hạn tuyệt đối và giới hạn thử

Trong mô hình này, expiresAt được cố định lúc phát hành. Nhập sai, tải lại trang và gọi API xem trạng thái không đẩy deadline về sau.

Giới hạn thử là một điều kiện độc lập:

~~~text
có_thể_chấp_nhận =
    state == ISSUED
    AND đúng_phạm_vi
    AND đúng_thế_hệ
    AND phản_hồi_được_kiểm_chứng
    AND còn_ngân_sách_thử
    AND decisionTime < effectiveDeadline
    AND trạng_thái_tài_khoản_và_recovery_còn_cho_phép
~~~

Đặt timeout ngắn nhưng không giới hạn thử vẫn cho phép thử hàng loạt trong cửa sổ ngắn. Đặt giới hạn thử theo từng challenge nhưng cho tạo challenge vô hạn lại chuyển cuộc tấn công sang bước phát hành.

## 6. Resend và tạo challenge mới phải có quy tắc rõ ràng

“Gửi lại” có thể mang hai nghĩa khác nhau.

| Cách xử lý | Điều gì xảy ra? | Quy tắc thời hạn |
| --- | --- | --- |
| Gửi lại cùng challenge, cùng secret | Chỉ có lần giao thông điệp mới | Giữ nguyên deadline và ngân sách thử |
| Phát hành challenge mới | Tạo nonce hoặc secret mới, có generation mới | Deadline mới bị giới hạn bởi giao dịch và policy phát hành |
| Đổi phương thức xác minh | Tạo challenge cho phương thức khác được policy chấp nhận | Không tự hạ yêu cầu bằng chứng; vẫn giữ các giới hạn chung |

Bài này chọn policy **mỗi phạm vi xác minh chỉ có một challenge hiện hành**. Khi phát hành challenge thay thế, challenge trước được đánh dấu SUPERSEDED trong cùng transaction với việc tạo challenge mới.

Phạm vi ở đây gồm tài khoản, giao dịch recovery và mục đích. Nếu ứng dụng cố ý cho nhiều challenge song song, cần một mô hình chấp nhận riêng và vẫn bảo đảm không cấp quyền lặp lại ngoài ý muốn.

### 6.1. Không khởi động lại mọi đồng hồ

Giả sử giao dịch hết hạn lúc 09:30. Người dùng xin challenge mới lúc 09:29 và thời hạn thông thường là năm phút. Deadline hiệu lực của challenge mới không vượt 09:30.

Nếu khoảng còn lại không đủ để thao tác hợp lý, hệ thống có thể hướng dẫn bắt đầu lại hoặc tiếp tục giao dịch qua cơ chế được thiết kế. Không tự cộng thêm ba mươi phút chỉ vì vừa gửi một mã.

Bộ đếm thử sai theo tài khoản hoặc authenticator, giới hạn phát hành, khoảng chờ gửi lại và ngân sách của giao dịch phải được quản lý ngoài vòng đời của một challenge đơn lẻ. Tạo challenge mới không có nghĩa người dùng nhận lại một ngân sách thử không giới hạn.

### 6.2. SMS hoặc email đến sai thứ tự

Challenge A được phát trước, challenge B được phát sau, nhưng thông điệp A đến muộn hơn. Backend vẫn dựa vào trạng thái và generation, không dựa vào thứ tự hiển thị trong hộp thư.

Giao diện nên giải thích rằng việc xin mã mới có thể làm mã trước mất hiệu lực. Thông điệp có thể có thời điểm phát hành hoặc nhãn yêu cầu không chứa bí mật để người dùng dễ phân biệt.

Với mã ngắn, chỉ đánh dấu A là SUPERSEDED chưa bảo đảm mã cũ không tình cờ trùng mã B. Thiết kế có thể tránh tái sử dụng giá trị trong tập challenge gần đây còn liên quan và chỉ kiểm tra mã với challenge hiện hành. Không thử một mã nhập vào trên mọi challenge cũ để “tìm mã nào còn đúng”.

### 6.3. Gửi lại không được trở thành cách chiếm quyền giao dịch

Quyền xin resend cần gắn với phiên recovery hoặc một cơ chế tiếp tục được xác minh. Người ngoài chỉ biết accountId không được thay challenge của một giao dịch đã có chủ thể đang xác minh.

Ở bước tiếp nhận recovery công khai, có thể phản hồi chung và áp dụng hạn mức gửi để tránh lộ tài khoản. Không dùng yêu cầu công khai đó để tự hủy các challenge đang hoạt động của người dùng hợp lệ.

## 7. Backend phải kiểm tra hạn sau khi có thể quyết định thật sự

Đoạn mã sau là mã giả theo phong cách Java để minh họa hợp đồng xử lý. Nó chưa phải một ứng dụng hoàn chỉnh và không thay thế verifier của từng phương thức.

~~~java
public VerificationResult verify(
        RecoveryPrincipal principal,
        VerifyChallengeCommand command) {

    // Kho chung quản lý ngân sách; không chỉ dùng bộ đếm trong JVM.
    attemptBudget.requireAndReserve(principal, command.challengeId());

    var snapshot = challenges.requireBoundSnapshot(
            principal, command.challengeId());

    // Kiểm chứng mật mã ngoài transaction giữ khóa.
    var checkedProof = verifier.verify(snapshot, command.response());

    return transaction.required(() -> {
        // Quy tắc khóa nhất quán cho verify, resend và hủy.
        var flow = recoveries.lock(principal.recoveryTransactionId());
        var challenge = challenges.lock(snapshot.id());

        requirePrincipalStillActive(principal);
        requireSameAccountTenantSessionAndPurpose(principal, flow, challenge);
        requireFlowOpen(flow);
        requireUnchangedChallengeIdentity(snapshot, challenge);
        requireState(challenge, State.ISSUED);

        requireAttemptBudgetStillUsable(principal, challenge);
        requireSecurityAndPolicyStillApplicable(flow, challenge);

        var deadline = earliest(
                challenge.expiresAt(),
                flow.expiresAt(),
                methodDeadline(challenge, checkedProof));

        // Đây là thời gian hiện tại của nguồn đồng hồ quyết định,
        // được đọc sát phép chuyển trạng thái, sau khi đã chờ khóa.
        var decisionTime = decisionClock.instant();

        if (!decisionTime.isBefore(deadline)) {
            challenge.markExpired();
            return VerificationResult.expired();
        }

        if (!checkedProof.validFor(challenge, decisionTime)) {
            attemptBudget.recordFailure(principal, challenge);
            return VerificationResult.invalid();
        }

        challenge.consume(decisionTime);

        var evidence = evidenceStore.appendAccepted(
                principal, challenge, checkedProof, decisionTime);

        // Chưa phải quyền thay authenticator hoặc phiên đăng nhập đầy đủ.
        return VerificationResult.accepted(evidence.id());
    });
}
~~~

Các hợp đồng quan trọng trong ví dụ:

- requireUnchangedChallengeIdentity đối chiếu cả nonce hoặc generation và dữ liệu bất biến mà verifier đã dùng; không chỉ so sánh challengeId.
- checkedProof do verifier tin cậy tạo, không phải boolean do client gửi. Kết quả phải khớp challenge hiện tại và các yêu cầu giao thức. Với TOTP, methodDeadline hoặc validFor phải xét cửa sổ mã tại decisionTime, không chỉ lúc bắt đầu kiểm chứng. earliest bỏ qua thành phần không áp dụng cho phương thức.
- decisionClock đại diện nguồn thời gian dùng cho quyết định được tuần tự hóa. Nếu dùng thời gian của cơ sở dữ liệu, cần hiểu hàm thời gian đang trả về thời gian hiện tại hay một mốc cố định từ đầu transaction.
- Khoảng từ decisionTime đến consume phải ngắn, không có gọi mạng hoặc công việc chậm. Với cập nhật có điều kiện, có thể đánh giá trạng thái và deadline ngay trong phép cập nhật nguyên tử.
- MarkExpired rồi trả kết quả bình thường cho phép transaction lưu trạng thái hết hạn. Nếu ném exception làm rollback, nhãn EXPIRED có thể không được lưu; tuy vậy kiểm tra deadline vẫn phải bảo đảm từ chối lần sau.
- Nhánh sai mã cập nhật ngân sách có hiệu lực sau commit. Cần tránh vô tình rollback bộ đếm thử sai khi chuyển kết quả thành lỗi HTTP.
- Chỉ trả kết quả ACCEPTED sau commit thành công. Rollback không được để lại evidence có hiệu lực ở một kho khác.

requirePrincipalStillActive bao gồm kiểm tra hiệu lực phiên recovery và các giới hạn phù hợp. Nếu idle timeout được gia hạn bằng polling, cần xác định polling có thật sự là hoạt động của người dùng hay không; không nên để một tab nền giữ phiên nhạy cảm sống mãi.

Mã giả tạo một evidence, chưa trực tiếp cấp mọi quyền. Một policy riêng phải đánh giá tổ hợp bằng chứng để cấp grant cho đúng thao tác. Bằng chứng đúng hạn nhưng không đủ yêu cầu recovery vẫn không được dùng để thay MFA hoặc thêm passkey mới.

## 8. Xử lý đồng thời, hàng đợi và sai lệch đồng hồ

### 8.1. Hai phản hồi đúng cùng đến

Hai request có thể cùng vượt qua kiểm tra mật mã. Chỉ một request được chuyển challenge từ ISSUED sang CONSUMED. Request còn lại không được tạo thêm evidence độc lập hoặc một grant mới.

Một mutex trong một JVM không bảo vệ các instance khác. Có thể dùng transaction khóa bản ghi hoặc compare-and-set tại kho dữ liệu chung, với điều kiện cập nhật bao gồm trạng thái và thời hạn.

Nếu retry do mất phản hồi mạng, hệ thống có thể trả lại tham chiếu kết quả đã commit cho đúng chủ thể và cùng request idempotent. Đây là đọc lại kết quả, không phải chấp nhận lại challenge và không làm mới verifiedAt.

### 8.2. Resend cạnh tranh với verify

Verify và resend phải dùng cùng quy tắc tuần tự hóa:

- Verify được chấp nhận trước: challenge đã tiêu thụ; resend xử lý theo trạng thái đã hoàn thành.
- Resend thay thế trước: phản hồi của generation cũ bị từ chối.
- Giao dịch bị hủy trước: cả verify lẫn resend không được cấp quyền mới.

Không cho một request đọc challenge A, kiểm chứng xong rồi tiêu thụ challenge B chỉ vì B có cùng mục đích.

### 8.3. Thời gian giữa các node

Nếu node phát hành nhanh hơn đồng hồ quyết định hoặc node kiểm tra chậm hơn, thời hạn thực tế có thể lệch. Thiết kế cần chọn nguồn thời gian rõ ràng, đồng bộ các hệ thống liên quan và giám sát độ lệch.

Trong mô hình tập trung, kho quyết định dùng một nguồn thời gian chung cho phát hành và tiêu thụ. Nếu phát hành ở nhiều node, phải quản lý sai lệch có giới hạn thay vì âm thầm cộng thêm thời gian “dự phòng” ở mọi lớp.

Đồng hồ monotonic phù hợp để đo độ trễ trong một tiến trình; giá trị đó không thể mang nguyên sang tiến trình khác làm deadline tuyệt đối. Các deadline lưu trữ cần biểu diễn thống nhất, chẳng hạn UTC, và không phụ thuộc múi giờ hiển thị.

Nếu phát hiện sai lệch nghiêm trọng, hệ thống cần có cách dừng hoặc hạn chế việc cấp quyền mới theo policy sự cố. Không tiếp tục chấp nhận challenge cũ chỉ vì dịch vụ đồng bộ thời gian đang lỗi.

### 8.4. Worker chậm không được giữ quyền chấp nhận trước

Nếu request phải xếp hàng trước khi kiểm chứng, thời gian trong hàng đợi vẫn được tính. Một timestamp “đã nhận” của queue không bảo đảm phản hồi đã được kiểm chứng khi còn hạn.

Khi backlog tăng, có thể từ chối sớm các request chắc chắn không còn thời gian xử lý, giảm tải hoặc cải thiện năng lực xử lý. Không tự thay đổi expiresAt của các challenge đã phát hành để giải quyết backlog.

## 9. Giao diện đếm ngược hỗ trợ người dùng, backend quyết định hiệu lực

Một API phát hành challenge có thể trả về:

~~~json
{
  "challengeId": "ch-204",
  "generation": 2,
  "serverTime": "2026-11-23T02:00:05Z",
  "expiresAt": "2026-11-23T02:03:00Z",
  "resendAvailableAt": "2026-11-23T02:00:30Z",
  "state": "ISSUED"
}
~~~

Client dùng thông tin đó để hiển thị khoảng còn lại và thời điểm có thể xin gửi lại. Nếu thiết bị lệch giờ, có thể ước lượng chênh lệch bằng serverTime rồi dùng bộ đếm elapsed trong lúc trang hoạt động. Kết quả này chỉ hỗ trợ hiển thị; backend vẫn kiểm tra bằng thời gian của mình.

Khi tab được mở lại sau sleep, mất mạng hoặc chạy nền lâu, nên lấy trạng thái mới. Không tiếp tục tin một setInterval đã bị trình duyệt tạm dừng.

Một cách thể hiện rõ ràng:

> Yêu cầu xác minh còn khoảng 2 phút. Nếu hết hạn, bạn có thể tạo yêu cầu mới. Việc tạo yêu cầu mới có thể làm mã trước mất hiệu lực.

Không cần đọc từng giây bằng trình đọc màn hình. Có thể thông báo ở các mốc có ý nghĩa, cho phép nhập và dán mã thuận tiện, giữ hướng dẫn rõ ràng, và hỗ trợ phương thức khác khi policy cho phép.

Nhu cầu tiếp cận nên được cân nhắc khi thiết kế thời hạn và cách bắt đầu lại. Khi cần thêm thời gian, một lựa chọn là phát hành challenge mới với nonce mới, trong phạm vi các giới hạn hiện có. Không cho client tự gia hạn nonce cũ bằng một nút “thêm thời gian” không được backend kiểm soát.

### 9.1. Mã lỗi nghiệp vụ

Với một phiên recovery đã được xác minh quyền truy cập, backend có thể phân biệt:

| Kết quả | Ý nghĩa | Hành động giao diện |
| --- | --- | --- |
| CHALLENGE_EXPIRED | Đã tới deadline | Hướng dẫn tạo challenge mới nếu còn được phép |
| CHALLENGE_SUPERSEDED | Có challenge thay thế | Đồng bộ về yêu cầu hiện hành |
| CHALLENGE_ALREADY_CONSUMED | Đã hoàn tất | Lấy kết quả đã lưu nếu đúng chủ thể |
| INVALID_RESPONSE | Phản hồi không đúng | Cho thử lại nếu ngân sách còn |
| ATTEMPT_LIMIT_REACHED | Không còn được thử theo policy | Hiển thị hướng dẫn tiếp theo phù hợp |
| RECOVERY_SESSION_EXPIRED | Phiên giới hạn hết hiệu lực | Thực hiện cơ chế tiếp tục hoặc bắt đầu lại |
| RECOVERY_TRANSACTION_EXPIRED | Hồ sơ yêu cầu đã đóng do thời hạn | Bắt đầu giao dịch mới hoặc theo nhánh hỗ trợ được thiết kế |

Ở endpoint công khai chưa chứng minh quyền truy cập, không nên tiết lộ tài khoản nào đang có challenge hoặc đang bị hạn chế. Mức chi tiết của lỗi phụ thuộc vào ngữ cảnh được phép biết, không phải ai gửi challengeId cũng được xem trạng thái nội bộ.

Nếu client đếm về 0 nhưng server vừa chấp nhận phản hồi, giao diện cần hiển thị kết quả đã được server xác nhận. Nếu server từ chối dù màn hình còn một giây, hướng dẫn người dùng tạo lại thay vì báo rằng họ đã nhập sai mật khẩu hay bị chiếm tài khoản.

## 10. Timeout phải giữ recovery ở trạng thái an toàn

Hết hạn challenge chỉ có nghĩa không được nhận thêm phản hồi cho challenge đó. Nó không tự chứng minh gian lận và không tự cho phép các thay đổi khác.

Trong luồng khôi phục tài khoản:

- Không xóa MFA cũ chỉ vì người dùng mở form thay MFA rồi để timeout.
- Không liên kết passkey mới nếu quyền cấp cho thao tác đã hết hạn trước khi được sử dụng.
- Không cấp phiên đăng nhập đầy đủ từ phiên recovery khi còn thiếu quyết định cấp quyền.
- Không đổi email hoặc số recovery như một cách “giúp người dùng vượt timeout”.
- Không khóa vĩnh viễn toàn bộ tài khoản chỉ vì một challenge đã hết hạn.
- Không tự hồi sinh grant cũ khi tạo challenge mới.

Nếu đang chuẩn bị authenticator thay thế, dữ liệu tạm như secret TOTP cần có vòng đời và quyền truy cập riêng. Khi giao dịch bị hủy hoặc đóng, dữ liệu chưa được liên kết phải bị vô hiệu hóa và dọn theo chính sách lưu trữ. Tác vụ dọn chậm không được làm dữ liệu tạm trở thành authenticator hoạt động.

Khi hệ thống mất kết nối đến kho quyết định, không dựa vào cache trạng thái cũ để cấp quyền mới. Giao diện có thể báo chưa thể xác minh và cho thử lại; việc retry vẫn phải tuân theo deadline và không tiêu thụ thêm quyền ngoài ý muốn.

Nếu phản hồi đã được chấp nhận và commit nhưng HTTP response bị mất, lấy lại trạng thái giao dịch qua phiên hợp lệ. Không yêu cầu backend chấp nhận challenge lần thứ hai để sửa lỗi trải nghiệm.

## 11. Bằng chứng và grant sau khi challenge đã hoàn tất

Giả sử challenge passkey hết hạn lúc 09:03:00 và backend đã chấp nhận phản hồi lúc 09:02:50. Policy giả định cho phép dùng bằng chứng trong năm phút và grant thay MFA trong hai phút.

Thời hạn grant có thể được tính:

~~~text
evidenceFreshUntil = verifiedAt + evidenceFreshness

grantExpiresAt = min(
    grantIssuedAt + grantLifetime,
    evidenceFreshUntil,
    recoveryTransaction.expiresAt,
    các_deadline_bắt_buộc_khác
)
~~~

Nếu grant được phát hành lúc 09:02:55 và không có giới hạn khác ngắn hơn, grant hết hạn lúc 09:04:55. Challenge hết hạn lúc 09:03:00 không làm mất hiệu lực một kết quả đã được chấp nhận trước đó; grant chịu các điều kiện và deadline riêng.

Ngược lại, nếu người dùng chỉ có một assertion chưa được backend chấp nhận lúc 09:03:00, không thể dùng việc grant có thời hạn hai phút để biện minh cho việc nhận assertion muộn.

| Thời điểm | Sự kiện | Kết quả theo policy giả định |
| --- | --- | --- |
| 09:00:00 | Phát challenge, hạn 09:03:00 | Chưa có bằng chứng được chấp nhận |
| 09:02:50 | Backend kiểm chứng và tiêu thụ challenge | Ghi evidence với verifiedAt thực tế |
| 09:02:55 | Policy cấp grant, hạn 09:04:55 | Chỉ cấp đúng thao tác được duyệt |
| 09:03:10 | Gửi lại assertion của challenge đã tiêu thụ | Không tạo evidence mới |
| 09:04:54 | Sử dụng grant, các điều kiện khác vẫn đạt | Có thể chấp nhận thao tác theo ranh giới đã định |
| 09:04:55 | Bắt đầu dùng grant ở đúng deadline | Từ chối vì đã hết hạn |

Việc grant còn hạn chưa đủ nếu tài khoản vừa bị đánh dấu compromise, authenticator nguồn đã bị thu hồi hoặc trạng thái recovery đã đổi. Deadline là một điều kiện cần trong một quyết định cấp quyền đầy đủ.

Không dùng refresh access token để thay verifiedAt. Không dùng polling để tạo grant mới lặp lại từ một bằng chứng đã quá cũ. Nếu challenge mới được tạo nhưng chưa hoàn tất, nó cũng không làm mới bằng chứng trước đó.

Với mã recovery đã lưu, phải phân biệt trạng thái “mã đã tiêu thụ” với evidence mà backend đã tạo từ việc tiêu thụ đó. Tạo lại challenge không làm mã đã dùng trở về chưa dùng. Nếu evidence được phép dùng tiếp trong cùng giao dịch, quyền đó cần phạm vi và thời hạn rõ ràng.

## 12. Quan sát vận hành để điều chỉnh đúng vấn đề

Không thể chọn timeout tốt chỉ bằng một con số áp dụng cho mọi người dùng. Cần quan sát thời gian ở từng giai đoạn, có phân biệt phương thức xác minh và loại luồng recovery.

| Chỉ số | Vấn đề có thể nhận ra |
| --- | --- |
| Thời gian từ phát hành tới gửi ra nhà cung cấp | Backlog hoặc worker gửi chậm |
| Thời gian từ phát hành tới phản hồi của người dùng | Cửa sổ thao tác có phù hợp không |
| Thời gian kiểm chứng và thời gian chờ khóa | Backend làm phản hồi đúng trở thành hết hạn |
| Tỷ lệ EXPIRED theo phương thức | Kênh cụ thể bị chậm hoặc UX khó hoàn tất |
| Tỷ lệ SUPERSEDED và resend | Mã đến sai thứ tự hoặc người dùng khó phân biệt |
| Số lần thử và số challenge trên một giao dịch | Dấu hiệu đoán mã hoặc reset ngân sách |
| Sai lệch đồng hồ giữa các thành phần | Deadline có thể không được áp dụng nhất quán |
| ACCEPTED nhưng client không thấy kết quả | Mất response hoặc retry chưa được xử lý tốt |

Có thể lưu các mốc issuedAt, expiresAt, decisionTime và mã lý do để giải thích một quyết định. Log dùng tham chiếu nội bộ phù hợp để tương quan sự kiện, không chứa OTP, token tiếp tục phiên, mã recovery, raw assertion hoặc secret TOTP.

Nếu phần lớn timeout đến từ hàng đợi gửi thông điệp, cải thiện hàng đợi và nhà cung cấp có thể phù hợp hơn việc tăng tuổi thọ mã. Nếu người dùng gặp khó vì thao tác qua nhiều thiết bị, cải thiện chỉ dẫn và khả năng bắt đầu lại có thể giảm lỗi.

Khi thay đổi policy thời hạn, nên lưu policyVersion và deadline đã phát hành vào bản ghi. Không tự kéo dài tất cả challenge đang tồn tại bằng cách đổi một biến cấu hình toàn cục. Nếu cần vô hiệu hóa sớm do sự cố, dùng một quyết định hủy hoặc thu hồi rõ ràng và có thể truy vết.

## 13. Những ranh giới cần hiểu đúng

| Tình huống | Cách xử lý trong mô hình bài học |
| --- | --- |
| Phản hồi được kiểm chứng đúng tại deadline | Từ chối theo quy tắc decisionTime < deadline |
| Request vào gateway trước hạn nhưng chờ xử lý đến sau hạn | Không chấp nhận chỉ dựa vào thời điểm gateway nhận |
| Kho dữ liệu chưa xóa bản ghi quá hạn | Vẫn từ chối nhờ kiểm tra deadline |
| Trình duyệt bị chỉnh giờ | Không thay đổi quyết định ở backend |
| Challenge còn hạn nhưng giao dịch recovery đã hết hạn | Từ chối vì deadline hiệu lực đã tới |
| Challenge mới được tạo sau nhiều lần thử sai | Giữ ngân sách và hạn mức chung theo policy |
| Hai request đúng cùng lúc | Một lần tiêu thụ; không tạo hai lần cấp quyền |
| Challenge cũ bị thay trong lúc đang kiểm chứng | Kết quả cũ không được dùng cho generation mới |
| Challenge đã hoàn tất rồi mới tới deadline | Evidence và grant tiếp tục theo điều kiện riêng |
| Response của lần thành công bị mất | Đọc lại kết quả đã commit trong đúng phạm vi |
| Thiết bị hoặc kênh được báo mất trước khi dùng grant | Kiểm tra trạng thái mới, không chỉ nhìn thời hạn |
| Người dùng không hoàn tất được challenge còn lại | Chọn nhánh recovery đủ điều kiện, không tự bỏ yếu tố |

Timeout hiệu quả khi hệ thống có thể chỉ ra rõ **challenge nào**, **thuộc giao dịch nào**, **được chấp nhận lúc nào**, và **quyền nào còn hiệu lực sau đó**. Trong khôi phục tài khoản, sự rõ ràng này giúp người dùng bắt đầu lại an toàn mà không biến phản hồi đến muộn, resend hoặc lỗi session thành một đường chiếm đoạt tài khoản.
