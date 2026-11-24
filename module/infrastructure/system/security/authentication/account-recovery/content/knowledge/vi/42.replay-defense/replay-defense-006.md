# Replay detection state

## 1. Vì sao chống replay cần nhớ điều đã xảy ra?

**Replay detection state** là trạng thái mà bên xác minh dùng để phân biệt một bằng chứng còn quyền sử dụng với bằng chứng đã được chấp nhận, thu hồi hoặc hết hiệu lực. Trong khôi phục tài khoản, trạng thái này ngăn một đường dẫn đặt lại mật khẩu, mã recovery hoặc phê duyệt bị dùng để tạo nhiều lần thay đổi quyền truy cập.

Một token có chữ ký hợp lệ và chưa hết hạn chưa chắc còn được sử dụng. Ví dụ:

1. Token T được phát hành lúc 09:00 và hết hạn lúc 09:10.
2. Chủ tài khoản dùng T để đổi mật khẩu lúc 09:02.
3. Một bản sao T được gửi lại lúc 09:03.
4. Nếu máy chủ chỉ kiểm chữ ký và thời hạn, T vẫn vượt qua cả hai điều kiện.

Thời hạn giới hạn **khoảng thời gian** có thể sử dụng. Trạng thái đã dùng giới hạn **số lần** bằng chứng có thể được chấp nhận. Hai cơ chế giải quyết hai vấn đề khác nhau.

NIST mô tả replay resistance là khả năng chống việc ghi lại rồi phát lại thông điệp xác thực; bảo vệ đường truyền không tự giải quyết mọi trường hợp bằng chứng bị lấy trước khi vào kênh bảo vệ. Xem [NIST — Replay Resistance](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#replay).

Đối với đặt lại mật khẩu, OWASP yêu cầu token hoặc mã có thời hạn phù hợp và chỉ dùng một lần. Bài này triển khai ý tưởng đó thành một mô hình trạng thái phía máy chủ; các bảng và luồng bên dưới là thiết kế minh họa, không phải schema bắt buộc của OWASP. Xem [OWASP — Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

## 2. Xác định chính xác thứ gì chỉ được dùng một lần

Trước khi chọn nơi lưu, cần xác định đơn vị mà hệ thống sẽ tiêu thụ:

- Một token đặt lại mật khẩu.
- Một mã recovery trong bộ mã dự phòng.
- Một challenge xác nhận trên thiết bị tin cậy.
- Một quyền đăng ký lại MFA.
- Một quyền tạm để hoàn tất đăng ký passkey mới.

Đừng dùng một cờ chung như account.recoveryUsed. Chủ tài khoản có thể thực hiện nhiều lần recovery hợp lệ trong vòng đời tài khoản; điều cần chặn là sử dụng lại **cùng quyền** cho một hoặc nhiều thao tác.

Một định danh tiêu thụ cần nằm trong không gian rõ ràng:

~~~text
tenant / issuer / purpose / tokenId
~~~

Nếu nhiều tenant hoặc dịch vụ dùng chung kho trạng thái, tokenId trùng nhau không được làm các quyền khác nhau ghi đè hoặc vô hiệu hóa lẫn nhau. Nếu đã bảo đảm tokenId duy nhất toàn hệ thống, vẫn cần kiểm tra đúng issuer, tài khoản và purpose trước khi sử dụng.

Các ràng buộc thuộc máy chủ phải xác định:

| Ràng buộc | Câu hỏi được giải quyết |
| --- | --- |
| accountId | Token áp dụng cho tài khoản nào? |
| purpose | Được đặt mật khẩu hay được thay MFA? |
| recoveryRequestId | Thuộc giao dịch recovery nào? |
| changeSetDigest nếu cần | Tập thay đổi nào đã được phê duyệt? |
| recoveryEpoch | Còn thuộc thế hệ recovery hiện hành không? |
| expiresAt | Có còn trong thời gian chấp nhận không? |

Không cho client đổi accountId hoặc purpose sau khi kiểm tra token. Các trường client gửi chỉ là dữ liệu cần đối chiếu; bản ghi hoặc nội dung đã được xác minh mới là nguồn quyền.

### Định danh công khai không phải bí mật

Biết tokenId không đồng nghĩa sở hữu token. Nếu token gồm phần định danh và phần bí mật, máy chủ phải kiểm tra phần bí mật trước khi tiêu thụ.

Nếu chỉ cần gửi tokenId để đánh dấu CONSUMED, người ngoài có thể đốt quyền recovery của chủ tài khoản mà không biết bí mật. Ngược lại, việc kiểm tra bí mật đúng rồi mới cập nhật trạng thái vẫn phải chống hai yêu cầu hợp lệ chạy đồng thời.

Đối với token ngẫu nhiên có entropy cao, có thể lưu digest của token thay cho giá trị gốc. Mã ngắn như OTP cần thêm biện pháp chống dò và bảo vệ dữ liệu lưu; chỉ băm một mã sáu chữ số không làm không gian đoán trở nên lớn.

## 3. Hai mô hình lưu trạng thái và ý nghĩa của việc không tìm thấy

### Mô hình danh sách quyền đã phát hành

Máy chủ lưu mọi token được phát hành. Chỉ token có bản ghi ISSUED, đúng ràng buộc và còn hạn mới được chấp nhận.

~~~text
Không có bản ghi -> từ chối
Có bản ghi ISSUED hợp lệ -> thử tiêu thụ nguyên tử
Có bản ghi CONSUMED hoặc REVOKED -> từ chối
~~~

Ưu điểm là có thể thu hồi từng token và kiểm soát trạng thái tập trung. Khi bản ghi bị xóa, token không tự trở thành hợp lệ.

### Mô hình danh sách bằng chứng đã dùng

Token có thể tự mang thông tin được ký. Máy chủ kiểm tính hợp lệ của token và tra danh sách token đã tiêu thụ.

~~~text
Token hợp lệ về mật mã và thời gian
    + chưa xuất hiện trong danh sách đã dùng
    + ghi nhận đã dùng thành công theo thao tác nguyên tử
    -> mới được tiếp tục
~~~

Trong mô hình này, “không thấy bản ghi” có thể có nghĩa là chưa dùng, nhưng cũng có thể là dữ liệu đã bị xóa, bị mất hoặc chưa đồng bộ. Vì vậy độ bền và thời gian lưu danh sách đã dùng là một phần của điều kiện bảo mật.

Một trường jti trong JWT chỉ là định danh. Nó không tự lưu lịch sử sử dụng, không tự chống hai lần đổi mật khẩu và không tự phát hiện replay.

| Tình huống | Danh sách quyền đã phát hành | Danh sách bằng chứng đã dùng |
| --- | --- | --- |
| Không tìm thấy token | Từ chối | Chỉ có thể xem là chưa dùng sau khi xác minh token và tin cậy kho trạng thái |
| Xóa bản ghi đã tiêu thụ | Có thể mất khả năng phân loại replay, nhưng không tạo quyền mới nếu thiếu là từ chối | Có thể mở lại token vẫn còn trong cửa sổ chấp nhận |
| Kho trạng thái không truy cập được | Không đủ cơ sở cấp quyền | Không đủ cơ sở kết luận token chưa dùng |
| Token chưa từng do hệ thống phát hành | Không có quyền tương ứng | Phải bị loại ở bước xác minh, trước khi tạo trạng thái |

Bài này dùng mô hình danh sách quyền đã phát hành làm ví dụ chính.

## 4. Trạng thái phải chuyển một chiều

Một vòng đời tối thiểu:

~~~mermaid
stateDiagram-v2
    [*] --> ISSUED
    ISSUED --> CONSUMED: Bằng chứng đúng và thao tác được commit
    ISSUED --> REVOKED: Hủy yêu cầu hoặc thay đổi chính sách
    ISSUED --> EXPIRED: Hết thời gian chấp nhận
    CONSUMED --> [*]
    REVOKED --> [*]
    EXPIRED --> [*]
~~~

Không chuyển CONSUMED trở lại ISSUED để xử lý việc người dùng mất kết nối. Nếu cần thử lại về mặt trải nghiệm, dùng kết quả của thao tác đã commit hoặc phát hành một quyền mới theo chính sách.

EXPIRED có thể là trạng thái được ghi xuống dữ liệu, hoặc được suy ra từ expiresAt. Dù tiến trình dọn dẹp chưa chạy, điều kiện expiresAt vẫn phải được kiểm tra khi tiêu thụ. Không được coi bản ghi còn mang chữ ISSUED là còn hạn.

Một bản ghi minh họa:

~~~text
tokenId
tokenDigest
accountId
purpose
recoveryRequestId
recoveryEpoch
state
issuedAt
expiresAt
consumedAt
operationId
version
~~~

operationId xác định thao tác nghiệp vụ đã dùng token. Nó hỗ trợ điều tra và xử lý retry, nhưng biết operationId không được tự cấp quyền xem dữ liệu hoặc nhận session mới.

Nếu cần một giai đoạn PROCESSING cho tác vụ bất đồng bộ, phải định nghĩa chủ sở hữu, kết quả bền vững và cách tiếp tục. Không tự trả token về ISSUED chỉ vì hết lease: tác vụ cũ có thể đã tạo hiệu ứng ở dịch vụ khác.

## 5. Tiêu thụ nguyên tử thay cho “đọc rồi ghi”

Cách xử lý sau có race condition:

~~~text
Nếu token chưa dùng:
    đổi mật khẩu
    đánh dấu token đã dùng
~~~

Hai worker có thể cùng đọc trạng thái chưa dùng trước khi một worker ghi lại. Cả hai đều nghĩ mình được phép đổi mật khẩu.

Ngay cả cách đảo thứ tự sau cũng chưa đủ:

~~~text
đánh dấu token đã dùng
gọi dịch vụ thay MFA
~~~

Nếu bước đầu thành công nhưng bước sau thất bại, người dùng mất token mà thao tác chưa hoàn tất. Nếu thay MFA xong nhưng ghi trạng thái thất bại, token có thể được dùng lại.

Trong một cơ sở dữ liệu có giao dịch, có thể đặt **tiêu thụ token và thay đổi nghiệp vụ cùng phạm vi commit**. Sau commit, cả quyền đã dùng và thay đổi tài khoản đều tồn tại; rollback thì cả hai không được xem là đã hoàn tất.

### Ví dụ cập nhật có điều kiện

SQL dưới đây minh họa PostgreSQL. Các tham số phải được bind; accountId, purpose và epoch không được tin từ request chưa xác minh.

~~~sql
BEGIN;

-- Khóa trạng thái tài khoản trước; các luồng cấp/hủy/tiêu thụ
-- cần tuân theo cùng quy ước khóa.
SELECT recovery_epoch
FROM recovery_account_state
WHERE account_id = :server_account_id
FOR UPDATE;

-- :locked_epoch là giá trị server vừa đọc dưới khóa.
UPDATE recovery_token
SET state = 'CONSUMED',
    consumed_at = clock_timestamp(),
    operation_id = :server_operation_id,
    version = version + 1
WHERE token_id = :token_id
  AND token_digest = :verified_digest
  AND account_id = :server_account_id
  AND purpose = :expected_purpose
  AND recovery_epoch = :locked_epoch
  AND state = 'ISSUED'
  AND expires_at > clock_timestamp()
RETURNING account_id, recovery_request_id, operation_id;

-- Chỉ tiếp tục nếu đúng một hàng được cập nhật.
-- Áp dụng thay đổi tài khoản đã được kiểm tra trong cùng transaction.
-- Có thể ghi sự kiện outbox ở đây.

COMMIT;
~~~

tokenId hoặc tokenDigest cần ràng buộc duy nhất phù hợp để câu lệnh không thể tiêu thụ nhiều quyền ngoài ý muốn. Nếu không cập nhật được đúng một hàng, không chạy thao tác bảo vệ rồi mới phân loại lỗi sau.

Trong PostgreSQL, RETURNING cung cấp dữ liệu của những hàng thực sự được cập nhật. Ở mức Read Committed, cập nhật cạnh tranh trên cùng hàng phải chờ và điều kiện WHERE được kiểm tra lại trên phiên bản hàng sau cập nhật của giao dịch trước. Những đặc tính này hỗ trợ mẫu cập nhật có điều kiện; chúng không tự giải quyết các điều kiện nghiệp vụ nằm ở hàng khác. Xem [PostgreSQL — UPDATE](https://www.postgresql.org/docs/current/sql-update.html) và [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).

Khóa trạng thái tài khoản trong ví dụ giúp điều phối việc tăng epoch với tiêu thụ token. Biện pháp chỉ có tác dụng nếu mọi đường cập nhật liên quan đều tuân thủ cùng giao thức. Đọc epoch từ cache rồi cập nhật token trong database không tạo ra cùng bảo đảm.

Thời gian phải được kiểm tra ở điểm quyết định có thẩm quyền. Với yêu cầu bị chờ khóa lâu, không chỉ dùng thời gian đã lấy từ lúc bắt đầu HTTP request để kết luận token còn hạn.

## 6. Ranh giới giao dịch trong service

Mã Java giả định dưới đây mô tả trách nhiệm của service, không phải đoạn triển khai đầy đủ:

~~~java
RecoveryResult completeRecovery(
    PresentedToken presented,
    RecoveryCommand command
) {
    TokenLookup lookup = tokens.lookupByDigest(
        tokenDigester.digest(presented)
    );

    if (lookup == null) {
        throw new InvalidRecoveryProof();
    }

    return transactions.required(() -> {
        RecoveryAccount account =
            accounts.lockForRecovery(lookup.accountId());

        // Lookup trước transaction không phải quyết định cấp quyền.
        RecoveryToken token =
            tokens.lockCurrentVersion(lookup.tokenId());

        policy.requireValidAndAllowed(account, token, command);
        bindings.requireSamePurposeAndRequest(token, command);
        proofs.requireValidSecret(token, presented);

        String operationId = operationIds.newId();

        tokens.consumeOnceOrThrow(
            token, account.recoveryEpoch(), operationId
        );

        // Chỉ chứa thay đổi có thể commit cùng kho dữ liệu này.
        RecoveryResult result =
            accountChanges.apply(account, token, command);

        outbox.recordRecoveryCompleted(operationId, account.id());
        return result;
    });
}
~~~

Phương thức consumeOnceOrThrow vẫn phải kiểm tra trạng thái và thời hạn ở thao tác ghi có thẩm quyền. Không chỉ dựa vào đối tượng token đã được nạp vào bộ nhớ.

Lớp transaction trong ví dụ phải rollback khi một bước kiểm tra hoặc thay đổi thất bại. Lời gọi một service từ xa không tự trở thành một phần của transaction chỉ vì nó nằm bên trong callback.

Nếu việc thu hồi session hoặc thay MFA diễn ra ở dịch vụ khác, cần mô hình operation bền vững:

1. Ghi nhận việc tiêu thụ và operation cần thực hiện trong cùng commit.
2. Gửi công việc qua cơ chế có khả năng tiếp tục sau sự cố.
3. Dịch vụ nhận lưu operationId cùng hiệu ứng nghiệp vụ theo cách nguyên tử hoặc tương đương.
4. Gửi lại cùng operationId không tạo thêm lần thay đổi.
5. Chỉ công bố hoàn tất khi những điều kiện bảo mật bắt buộc đã đạt.

Đây là sự phối hợp giữa trạng thái replay và idempotency ở phía nhận. Outbox giúp không mất ý định gửi sau commit, nhưng không tự làm hiệu ứng từ xa xảy ra đúng một lần.

## 7. Nhiều máy chủ phải có cùng quyết định

Giả sử instance A và B cùng xử lý token T:

~~~text
A đọc: ISSUED
B đọc: ISSUED
A tiêu thụ và commit
B cố tiêu thụ: điều kiện ISSUED không còn đúng
B từ chối tạo thao tác mới
~~~

Điểm quan trọng là A và B phải tranh chấp trên cùng trạng thái có thẩm quyền. Hai bản sao bộ nhớ riêng không tạo ra điểm quyết định chung.

| Nơi lưu hoặc cách đọc | Có thể dùng cho điều gì? | Giới hạn |
| --- | --- | --- |
| Bộ nhớ trong một JVM | Tối ưu cục bộ, gom yêu cầu trùng | Restart hoặc instance khác không biết lịch sử |
| Cache dùng chung | Giảm truy vấn, phân phối một số quyết định phụ | Không được mất dữ liệu quyết định rồi xem token là chưa dùng |
| Database có ghi có điều kiện | Quyết định tiêu thụ và thay đổi cùng transaction | Cần độ bền, topology và xử lý failover phù hợp |
| Read replica có thể trễ | Báo cáo và quan sát khi chấp nhận dữ liệu trễ | Không dùng trạng thái ISSUED cũ để cấp quyền |
| Nhật ký audit | Điều tra và thống kê | Ghi log sau sự kiện không thay thế chặn tiêu thụ trùng |

Một cập nhật nguyên tử chỉ giải quyết tranh chấp trong phạm vi mà nó thực sự bảo vệ. Nó không tự bảo đảm dữ liệu đã được ghi bền vững trên mọi bản sao, cũng không bảo đảm failover không mất lần tiêu thụ vừa xác nhận.

Trong triển khai nhiều vùng, chọn một điểm ghi có thẩm quyền cho mỗi token hoặc dùng kho dữ liệu có mức nhất quán đủ mạnh cho quyết định đó. Nếu hai vùng độc lập đều được phép kết luận “chưa dùng” khi mất liên lạc, một token có thể được chấp nhận ở cả hai.

Khi kho trạng thái không truy cập được, không chuyển sang chỉ kiểm chữ ký hoặc chỉ kiểm expiry để cho recovery tiếp tục. Trả lỗi tạm thời phù hợp và giữ nguyên quyền chưa được tiêu thụ nếu chưa có commit. Nếu kết quả commit chưa biết, phải tra operation có thẩm quyền trước khi quyết định thử lại.

### Vì sao mutex cục bộ không đủ?

synchronized hoặc khóa trong một process có thể tuần tự hóa các thread của process đó. Khi có hai instance, mỗi instance vẫn có khóa riêng.

Khóa phân tán cũng không thay thế trạng thái tiêu thụ. Nếu khóa hết lease trong khi thao tác cũ còn chạy, một worker mới có thể tiếp tục. Quyền áp dụng thay đổi cuối cùng vẫn cần được bảo vệ bằng điều kiện nguyên tử, version hoặc cơ chế từ chối chủ sở hữu đã mất quyền.

## 8. Thời gian lưu khác với thời gian còn hiệu lực

Có ba mốc thời gian riêng:

- **Hạn chấp nhận:** sau mốc này token không được dùng.
- **Hạn giữ dữ liệu chống replay:** cần giữ đủ lâu để không mở lại quyền.
- **Hạn giữ dữ liệu điều tra:** phụ thuộc nhu cầu vận hành và chính sách dữ liệu.

Trong mô hình danh sách bằng chứng đã dùng, có thể diễn đạt điều kiện dọn như sau:

~~~text
thời điểm xóa dấu đã dùng
    > thời điểm muộn nhất mọi verifier còn có thể chấp nhận token
      + biên an toàn vận hành đã xác định
~~~

Mốc chấp nhận phải bao gồm dung sai đồng hồ và mọi cửa sổ được hỗ trợ. Biên an toàn cần gắn với mô hình vận hành cụ thể; không dùng nó để che giấu việc verifier có thể kéo dài hiệu lực vô hạn.

Ví dụ minh họa:

- Token có expiresAt = 09:10:00.
- Một verifier được phép dung sai thêm 30 giây.
- Dấu đã dùng bị xóa lúc 09:10:00.
- Lúc 09:10:10, bản sao token vẫn có thể qua kiểm thời gian nhưng không còn dấu đã dùng để chặn.

Sai sót nằm ở việc dùng một mốc dọn ngắn hơn cửa sổ chấp nhận thực tế. TTL của dấu đã dùng không được mặc định bằng một khoảng ngắn tính từ thời điểm tiêu thụ nếu token còn có thể được chấp nhận lâu hơn.

Trong mô hình danh sách quyền đã phát hành, thiếu bản ghi luôn bị từ chối nên xóa bản ghi đã dùng không tự làm token sống lại. Tuy nhiên hệ thống có thể mất khả năng phân biệt replay với token không xác định, và mất dữ liệu hỗ trợ retry. Cần cân nhắc riêng các nhu cầu đó.

Không tạo lại bản ghi ISSUED từ cache cũ hoặc lịch sử phát hành chỉ vì bản ghi hiện tại không còn tồn tại. Việc tái dựng như vậy có thể đảo ngược ý nghĩa của thao tác xóa hoặc thu hồi.

### Tránh TTL trượt cho quyền recovery

Một yêu cầu xem trang, polling hoặc resend không được tự kéo dài thời hạn tiêu thụ. Nếu chính sách cho phát hành quyền mới, quyền mới phải có định danh riêng và quan hệ rõ với quyền cũ.

Với mã ngắn có thể trùng giá trị ở các lần phát hành, trạng thái phải gắn với lần phát hành hoặc challenge tương ứng. Không dùng chuỗi ký tự của mã làm định danh toàn cục vĩnh viễn.

## 9. Retry hợp lệ và replay có thể trông giống nhau

Một người dùng có thể gửi lại request vì không thấy phản hồi:

~~~text
Client gửi yêu cầu
Server tiêu thụ token, thay mật khẩu, commit
Kết nối mất trước khi client nhận kết quả
Client gửi lại cùng yêu cầu
~~~

Lần gửi thứ hai không được tạo lần đổi mật khẩu mới. Tuy nhiên không nhất thiết phải kết luận rằng người dùng có ý đồ xấu.

Có thể xử lý theo một trong hai cách đã được thiết kế rõ:

- Từ chối sử dụng token lần nữa và hướng dẫn người dùng đăng nhập bằng thông tin mới hoặc bắt đầu quy trình phù hợp.
- Trả lại kết quả tối thiểu của operation đã hoàn tất nếu ngữ cảnh yêu cầu có quyền xem kết quả đó.

Idempotency key cần ràng buộc với tài khoản, thao tác và nội dung command. Dùng lại một key với mật khẩu đích hoặc tập thay đổi khác không được tự kế thừa kết quả cũ.

Không trả session mới, recovery grant mới hoặc bí mật cũ cho bất kỳ ai chỉ biết một idempotency key hay token đã tiêu thụ. Một phản hồi “thao tác đã được xử lý” khác hoàn toàn với việc cấp lại quyền truy cập.

Đừng giải quyết sự cố bằng cách xóa CONSUMED rồi thử lại. Nếu commit thành công nhưng phản hồi mất, cách đó biến lỗi truyền thông thành khả năng thực hiện lại thao tác bảo mật.

Cũng không dùng GET mở link làm thời điểm hoàn tất thay đổi nhạy cảm. Trình quét email, trình xem trước và prefetch có thể mở URL trước người dùng. Nếu luồng đổi token lấy một ngữ cảnh recovery tạm, bước trao đổi đó cũng cần tiêu thụ nguyên tử và quản lý quyền của ngữ cảnh mới; không chỉ bỏ kiểm tra one-time ở bước sau.

## 10. Thu hồi, phát hành lại và recovery epoch

Chỉ chặn sử dụng lại token T chưa xử lý hết những quyền khác đã phát hành cho cùng tài khoản.

Ví dụ, người dùng có T1 từ hôm trước và T2 vừa nhận. Sau khi hoàn tất bằng T2, hệ thống cần chính sách rõ về T1:

- Giữ T1 hợp lệ đến hạn.
- Thu hồi mọi token cùng purpose.
- Thu hồi toàn bộ quyền recovery đang chờ của tài khoản.

Trong các thao tác có nguy cơ chiếm đoạt, việc để lại những quyền cũ có thể tạo đường quay lại cho kẻ tấn công. Lựa chọn phải gắn với mô hình rủi ro, không chỉ thuận tiện cho database.

**Recovery epoch** là một cách biểu diễn việc vô hiệu hóa theo thế hệ. Token lưu thế hệ khi được phát hành; máy chủ so sánh với thế hệ hiện hành khi tiêu thụ. Khi chính sách yêu cầu hủy toàn bộ quyền cũ, thế hệ được thay đổi.

Điểm cần giữ:

1. Phát hành, tăng epoch và tiêu thụ phải được điều phối trên trạng thái có thẩm quyền.
2. Không lấy epoch do client tự gửi làm giá trị hiện hành.
3. Tăng epoch không thay thế kiểm tra trạng thái one-time của từng token.
4. Mọi endpoint dùng quyền recovery đều phải kiểm tra thế hệ, kể cả endpoint nội bộ và đường tiếp tục đăng ký MFA.
5. Việc thu hồi authenticator hoặc session là quyết định riêng, không tự xảy ra chỉ vì token đã CONSUMED.

Nếu một yêu cầu mới làm vô hiệu mọi yêu cầu cũ ngay lập tức, kẻ ngoài có thể liên tục bấm “quên mật khẩu” để làm link của chủ tài khoản mất hiệu lực. Cần giới hạn lạm dụng và chọn thời điểm vô hiệu hóa có chủ đích; không mặc định mọi lần khởi tạo chưa xác minh đều được hủy quyền của người dùng.

### Khôi phục database có thể khôi phục cả quyền đã dùng

Backup có thể chứa T ở trạng thái ISSUED trong khi trước sự cố T đã được tiêu thụ. Restore backup làm lịch sử database lùi lại; một token cũ vẫn còn trong tay người dùng hoặc kẻ tấn công có thể trông như chưa dùng.

Kế hoạch phục hồi cần vô hiệu hóa quyền recovery bị ảnh hưởng trước khi mở lại khả năng tiêu thụ. Với mô hình danh sách đã phát hành, có thể thu hồi những quyền còn hoạt động trong dữ liệu được phục hồi. Với token tự chứa, có thể cần đổi khóa hoặc thế hệ phát hành được quản lý đúng phạm vi.

Không chỉ tăng một bộ đếm từ snapshot cũ rồi giả định nó chưa từng được dùng trước sự cố. Một thế hệ đã tồn tại trong phần lịch sử bị mất có thể vô tình được tái sử dụng. Cơ chế vô hiệu hóa sau restore phải tránh trùng thế hệ cũ và được kiểm tra ở mọi bên xác minh liên quan.

## 11. Quan sát replay mà không làm lộ bằng chứng

Phản hồi công khai thường không cần tiết lộ token đã dùng, bị thu hồi hay thuộc tài khoản nào. Thông điệp chung như “Yêu cầu không còn hợp lệ” có thể giảm khả năng dò trạng thái; thời gian phản hồi và khả năng truy vấn cũng cần được cân nhắc.

Nội bộ có thể phân biệt:

| Kết quả nội bộ | Ý nghĩa vận hành |
| --- | --- |
| CONSUMED_SUCCESS | Lần tiêu thụ và operation đã commit |
| ALREADY_CONSUMED | Có trạng thái đã dùng; không thực hiện thao tác mới |
| EXPIRED | Ngoài cửa sổ chấp nhận |
| REVOKED | Quyền đã bị thu hồi |
| BINDING_MISMATCH | Không đúng purpose, giao dịch hoặc thế hệ |
| INVALID_PROOF | Không có bằng chứng hợp lệ |
| STATE_UNAVAILABLE | Chưa thể đưa ra quyết định có thẩm quyền |
| OUTCOME_UNKNOWN | Chưa biết chắc giao dịch trước đã commit hay chưa |

Không suy luận ALREADY_CONSUMED chỉ từ một tokenId công khai nếu người gửi chưa chứng minh sở hữu bằng chứng. Chi tiết chẩn đoán không được biến thành API tra lịch sử token cho người ngoài.

Log nên dùng định danh nội bộ, mã kết quả, thời gian và operationId cần thiết. Không ghi raw token, OTP, URL chứa bí mật hoặc toàn bộ request body. Digest của mã ngắn cũng có thể hỗ trợ dò offline nếu bị lộ, nên không coi mọi giá trị đã băm là dữ liệu an toàn để xuất ra log.

Một lần trùng có thể là retry hợp lệ. Nhiều lần trùng từ nhiều ngữ cảnh hoặc sau một thay đổi nhạy cảm đáng được theo dõi, nhưng không tự động khóa tài khoản chỉ dựa vào các request mà kẻ ngoài có thể tạo.

Ngân sách ghi log và tạo trạng thái lỗi cần có giới hạn. Không để người ngoài đưa vô hạn tokenId giả vào kho replay và làm đầy bộ nhớ hoặc dung lượng lưu.

## 12. Áp dụng cho các kiểu khôi phục tài khoản

**Đặt lại mật khẩu:** token chỉ được tạo một operation đổi mật khẩu. Trạng thái tiêu thụ phải đi cùng thay đổi có thẩm quyền; việc cấp session sau đó cần chính sách riêng.

**Thay MFA sau mất thiết bị:** ngoài trạng thái của token, cần ràng buộc với giao dịch đã được xác minh. Một quyền đặt lại mật khẩu không tự trở thành quyền xóa mọi phương thức MFA.

**Đăng ký passkey thay thế:** phê duyệt recovery và hoàn tất đăng ký khóa mới có thể là hai bước. Mỗi quyền một lần ở từng bước cần được quản lý, và khóa đích phải khớp với dữ liệu đã được cho phép. Không tái sử dụng một phê duyệt để đăng ký thêm nhiều khóa.

**Dùng mã recovery dự phòng:** tiêu thụ đúng mã hoặc đúng bản ghi trong bộ mã. Không đánh dấu cả bộ đã dùng nếu chính sách cho phép từng mã độc lập, và không để một mã được dùng đồng thời ở hai instance.

Quy tắc thiết kế xuyên suốt là: **mỗi quyền recovery có danh tính rõ ràng, được tiêu thụ tại một điểm quyết định chung, và không tạo lại hiệu ứng sau khi đã commit**. Hết hạn, thu hồi, retry, failover và restore đều phải giữ được ý nghĩa đó.
