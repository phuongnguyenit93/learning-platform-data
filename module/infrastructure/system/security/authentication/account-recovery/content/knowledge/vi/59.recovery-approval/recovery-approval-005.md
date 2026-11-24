# Approval expiration — Thời hạn hiệu lực của phê duyệt khôi phục tài khoản

## 1. Phê duyệt không phải giấy phép có hiệu lực vô hạn

Trong quy trình khôi phục tài khoản, một người có thẩm quyền có thể phê duyệt việc vô hiệu MFA bị mất, cho phép đăng ký lại passkey hoặc mở một bước đặt lại mật khẩu. Phê duyệt đó dựa trên bằng chứng, mức rủi ro, quyền của các bên và kế hoạch được trình tại một thời điểm cụ thể.

Những điều kiện này có thể thay đổi. Người yêu cầu có thể tìm lại thiết bị, tài khoản có thể được nâng quyền, một bằng chứng có thể hết giá trị hoặc hệ thống có thể phát hiện hành vi chiếm tài khoản. Nếu phê duyệt cũ vẫn được sử dụng nhiều ngày sau mà không có giới hạn, nó trở thành một khả năng truy cập đang chờ bị khai thác.

Approval expiration là thời điểm mà một phê duyệt không còn được dùng để cho phép một hành động mới. Trong `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, cơ chế này giúp giới hạn thời gian có thể sử dụng quyết định hỗ trợ người dùng sau khi mất mật khẩu, MFA, passkey hoặc thiết bị xác thực.

Hết hạn chỉ là một điều kiện. Một phê duyệt chưa hết hạn vẫn có thể không sử dụng được vì đã bị thu hồi, đã được dùng, sai tài khoản, sai kế hoạch hoặc không còn đáp ứng chính sách hiện tại.

## 2. Phân biệt các loại thời hạn trong cùng một hồ sơ

Một hồ sơ khôi phục thường chứa nhiều đối tượng có thời hạn. Chúng có mục đích khác nhau và không nên dùng chung một trường `expiresAt` mơ hồ.

| Loại thời hạn | Điều được giới hạn | Hậu quả khi hết hạn |
|---|---|---|
| Hạn nhận quyết định của yêu cầu phê duyệt | Khoảng thời gian người duyệt được phản hồi một yêu cầu đang chờ | Không nhận thêm quyết định cho vòng yêu cầu đó |
| Hạn sử dụng phê duyệt đã cấp | Khoảng thời gian quyết định được dùng để cho phép hành động đã duyệt | Không cho phép một lần thực thi mới dựa vào quyết định đó |
| Độ mới của bằng chứng | Khoảng thời gian kết quả xác minh còn đủ mới theo chính sách | Phải đánh giá hoặc thu thập lại bằng chứng khi cần |
| Thời hạn token hoặc grant khôi phục | Khoảng thời gian chủ thể được dùng khả năng khôi phục đã cấp | Không nhận bước tiêu thụ mới sau hạn tương ứng |
| Thời hạn phiên khôi phục | Khoảng thời gian phiên giới hạn còn hoạt động | Không tiếp tục các thao tác được bảo vệ bởi phiên đã hết hạn |
| Hạn xử lý của một lần thực thi | Khoảng thời gian xử lý hoặc tiếp tục một thao tác đã được cho phép | Dừng hoặc chuyển xử lý theo chính sách của thao tác |

Ví dụ, một phê duyệt hết hạn lúc 10:15 không tự trả lời token được cấp hợp lệ lúc 10:14 có được dùng lúc 10:16 hay không. Hệ thống phải quy định rõ phê duyệt chỉ cho phép phát hành token hay phải còn hiệu lực đến cả bước người dùng tiêu thụ token.

Nếu hai thời hạn phụ thuộc nhau, quan hệ đó phải nằm trong chính sách và cách tính cụ thể. Không nên để một nhóm phát triển mặc định “token có TTL riêng” còn nhóm khác mặc định “phê duyệt hết hạn thì token cũng chết”.

## 3. Mô hình một phê duyệt có thời hạn

Một bản ghi phê duyệt nên gắn quyết định với phạm vi đủ cụ thể:

```text
approvalId: approval-418
caseId: recovery-205
approvalRound: 3
planRevision: 8
targetIdentityId: identity-482
credentialAuthorityId: tenant-A
approvedActions:
  - INVALIDATE_FACTOR: factor-19
  - ISSUE_MFA_ENROLLMENT_GRANT
evidenceRevision: 4
policyVersion: recovery-policy-12
approverIdentityId: reviewer-27
approvedAt: 2026-11-24T03:00:00Z
expiresAt: 2026-11-24T03:15:00Z
state: APPROVED
```

Các thời điểm và khoảng 15 phút trong ví dụ chỉ dùng minh họa. Chúng không phải cấu hình mặc định cho mọi hệ thống.

Một quyết định chỉ có thể được dùng khi đồng thời thỏa mãn các điều kiện như:

- Đúng hồ sơ, tài khoản đích và miền có thẩm quyền quản lý credential.
- Đúng vòng phê duyệt, phiên bản kế hoạch và tập hành động.
- Đủ số người duyệt hợp lệ theo quy tắc phân tách trách nhiệm.
- Chưa hết hạn, chưa bị thu hồi và chưa bị tiêu thụ theo mô hình đã chọn.
- Bằng chứng, rủi ro và quyền hiện tại còn đáp ứng điều kiện thực thi.

Không nên chỉ kiểm tra `state == APPROVED`. Giá trị lưu trong cơ sở dữ liệu có thể vẫn là `APPROVED` dù thời điểm hết hạn đã qua và tác vụ dọn trạng thái chưa chạy.

## 4. Xác định mốc bắt đầu và mốc hết hạn

### 4.1. Không lấy đồng hồ trình duyệt làm căn cứ cho phép

Thời điểm có thẩm quyền phải đến từ hạ tầng máy chủ được thiết kế cho quyết định này, chẳng hạn đồng hồ của cơ sở dữ liệu hoặc một nguồn thời gian máy chủ thống nhất trong đường thực thi.

Trình duyệt có thể hiển thị đếm ngược để giúp người vận hành, nhưng không có quyền quyết định phê duyệt còn hạn. Thay đồng hồ máy cá nhân, sửa dữ liệu yêu cầu hoặc gửi lại một ảnh chụp màn hình không được làm phê duyệt sống lại.

Lưu các thời điểm dưới dạng thời điểm tuyệt đối và dùng múi giờ địa phương cho hiển thị. Một chuỗi như “10:15” thiếu ngày và múi giờ dễ gây hiểu sai khi người duyệt và người thực hiện ở các khu vực khác nhau.

### 4.2. Khoảng hiệu lực cần có ranh giới rõ ràng

Một quy ước đơn giản là dùng khoảng nửa mở:

```text
approvedAt <= thời điểm cho phép thực thi < expiresAt
```

Tại đúng `expiresAt`, quyết định đã hết hạn. Khi dùng quy ước này, mọi dịch vụ cần áp dụng cùng một phép so sánh. Nếu nơi dùng `<` còn nơi dùng `<=`, hành vi tại biên sẽ không nhất quán.

### 4.3. Hạn hiệu lực có thể bị giới hạn bởi nhiều nguồn

Chính sách có thể tính thời điểm hết hạn bằng hạn sớm nhất trong những giới hạn thực sự áp dụng:

```text
expiresAt = min(
    approvedAt + thời lượng phê duyệt theo chính sách,
    hạn cuối của hồ sơ nếu có,
    hạn hiệu lực của bằng chứng cần thiết,
    hạn ủy quyền có liên quan
)
```

Cần xác định giới hạn nào được áp dụng cho hành động nào. Không tự đưa vào một hạn không tồn tại rồi biến nó thành vô hạn một cách thiếu kiểm soát.

Nếu hạn tính được không lớn hơn thời điểm phê duyệt, hệ thống không nên cấp một phê duyệt trông có vẻ sử dụng được. Nó cần yêu cầu làm mới điều kiện liên quan hoặc báo rõ rằng không còn cửa sổ thực thi hợp lệ.

### 4.4. Thời gian chờ và thời gian hết hạn là hai trục khác nhau

Một quy trình có thể yêu cầu chờ trước khi thực thi để cho chủ tài khoản có cơ hội phản hồi. Khi đó, cần có cả `notBefore` và `expiresAt` nếu thiết kế sử dụng hai mốc này.

```text
notBefore <= thời điểm cho phép thực thi < expiresAt
```

Nếu thời gian chờ kéo dài quá hạn phê duyệt, hồ sơ không có cửa sổ thực thi. Cần điều chỉnh chính sách hoặc xin phê duyệt mới; không bỏ qua một trong hai kiểm soát để làm yêu cầu chạy được.

## 5. Chọn thời lượng theo rủi ro và khả năng vận hành

Thời hạn ngắn giảm thời gian một quyết định bị đánh cắp hoặc bị bỏ quên có thể được sử dụng. Tuy nhiên, nếu ngắn hơn thời gian xử lý bình thường, người vận hành có thể liên tục xin duyệt lại hoặc tìm đường tắt. Chính sách cần cân bằng mức tác động với quy trình thực tế.

Các đầu vào đáng cân nhắc gồm:

| Đầu vào | Ảnh hưởng tới cách thiết kế thời hạn |
|---|---|
| Mức đặc quyền của tài khoản đích | Tác động lớn thường cần cửa sổ kiểm soát chặt và kiểm tra lại điều kiện |
| Loại hành động | Thay kênh khôi phục khác với chỉ mở một bước đăng ký lại có giới hạn |
| Độ mới và độ tin cậy của bằng chứng | Bằng chứng nhạy với thời gian có thể giới hạn hạn sử dụng quyết định |
| Dấu hiệu xâm nhập hoặc lạm dụng | Có thể cần dừng, thu hồi hoặc chuyển điều tra thay vì chỉ rút ngắn TTL |
| Độ trễ hàng đợi và phụ thuộc bên ngoài | Phải đủ quan sát để phát hiện hồ sơ thường xuyên hết hạn trước khi được xử lý |
| Cơ chế thông báo và thời gian chờ | Cần thiết kế một cửa sổ khả thi sau khi đã hoàn thành các bước bắt buộc |

Không coi TTL ngắn là biện pháp thay thế cho xác minh danh tính hoặc kiểm tra quyền. Một phê duyệt cấp sai người nhưng chỉ sống trong vài phút vẫn có thể đủ để chiếm tài khoản.

Người gọi API không nên tự chọn thời hạn tùy ý. Nếu sản phẩm cho phép yêu cầu một thời hạn, máy chủ vẫn phải giới hạn bằng chính sách và lưu lại giá trị thực tế đã áp dụng.

## 6. Hết hạn, thu hồi và mất hiệu lực do thay đổi kế hoạch

Ba lý do này cần được phân biệt để người vận hành hiểu cách xử lý.

| Trạng thái hoặc lý do | Nguyên nhân | Có thể tiếp tục bằng quyết định cũ không? |
|---|---|---|
| Hết hạn | Đã đến hoặc qua thời điểm cuối được sử dụng | Không |
| Bị thu hồi | Có quyết định chủ động hủy hiệu lực, chẳng hạn xuất hiện dấu hiệu chiếm tài khoản | Không |
| Bị thay thế | Có vòng phê duyệt hoặc kế hoạch mới làm quyết định cũ không còn áp dụng | Không |
| Không khớp phạm vi | Sai tài khoản, yếu tố, hành động hoặc miền quản lý | Không |
| Đã tiêu thụ | Quyết định đã được gắn với một lần thực thi theo mô hình dùng một lần | Không cho phép tạo lần thực thi mới bằng quyết định đó |

Hạn hết hiệu lực là giới hạn tối đa, không phải lời hứa rằng phê duyệt sẽ dùng được đến thời điểm đó. Nếu rủi ro thay đổi, hệ thống có thể phải thu hồi sớm theo chính sách.

Các thay đổi quan trọng như thay tài khoản đích, thêm hành động đổi email, đổi yếu tố bị vô hiệu hoặc tăng đặc quyền của tài khoản cần được đánh giá lại. Không chỉ giữ nguyên `approvalId` rồi cập nhật nội dung kế hoạch ở dưới nó.

Với thay đổi vai trò của người duyệt, chính sách cần quy định điều gì phải được kiểm tra lại lúc thực thi. Không mặc định mọi phê duyệt cũ tự hợp lệ hoặc tự vô hiệu trong mọi tình huống. Dịch vụ thực thi phải áp dụng đúng quy tắc hiện hành và ghi được lý do quyết định.

## 7. Kiểm tra tại thời điểm cho phép thực thi

Một lỗi phổ biến là chỉ kiểm tra hạn ở lúc mở màn hình hoặc lúc bấm nút gửi yêu cầu. Yêu cầu có thể nằm trong hàng đợi rồi mới được xử lý sau khi phê duyệt đã hết hạn.

Đường thực thi phải có một thời điểm rõ ràng mà tại đó quyết định được sử dụng để cho phép thao tác. Có thể gọi đây là điểm cam kết cấp quyền thực thi. Phép kiểm tra thời hạn phải gắn với điểm này, cùng kiểm tra kế hoạch, trạng thái và khả năng dùng một lần.

Một chuỗi xử lý minh họa:

```text
Bắt đầu giao dịch hoặc cơ chế cập nhật có kiểm soát phiên bản
  Đọc và bảo vệ trạng thái hồ sơ, kế hoạch, phê duyệt
  Lấy thời điểm có thẩm quyền sau khi đã giành quyền cập nhật
  Kiểm tra phê duyệt còn hạn và đúng phiên bản
  Kiểm tra bằng chứng, phạm vi, rủi ro và phê duyệt độc lập
  Kiểm tra đã có lần thực thi cho yêu cầu này chưa
  Gắn phê duyệt với đúng lần thực thi và tập hành động bất biến
  Ghi lệnh thực thi bền vững cùng sự kiện cần thiết
Cam kết thay đổi
```

Không nên kiểm tra thời gian trước khi chờ một khóa lâu, rồi dùng nguyên giá trị cũ sau khi giành được khóa. Tương tự, cơ chế giao dịch có thể cung cấp thời điểm theo những ngữ nghĩa khác nhau; cần chọn nguồn thời gian tương ứng với thời điểm mà hệ thống cam kết cấp quyền, thay vì mặc định mọi hàm thời gian đều phản ánh lúc hiện tại.

Nếu hệ thống có hai worker cùng xử lý một phê duyệt, cả hai có thể nhìn thấy nó còn hạn. Kiểm tra thời gian không ngăn sử dụng hai lần. Cần ràng buộc trạng thái hoặc tính duy nhất để chỉ một lần thực thi mới được tạo theo mô hình đã chọn.

## 8. Thực thi bất đồng bộ và hành động vượt qua mốc hết hạn

Phải xác định rõ điều gì đã được cho phép trước hạn và điều gì chỉ mới được xếp hàng. Hai thiết kế dưới đây có ngữ nghĩa khác nhau.

### 8.1. Phê duyệt phải còn hạn khi worker bắt đầu cấp quyền

Ở thiết kế này, yêu cầu được gửi vào hàng đợi không tiêu thụ phê duyệt. Worker phải đánh giá lại trước khi tạo hoặc cho phép hành động thực tế.

Nếu đến lượt xử lý sau hạn, worker dừng và báo cần phê duyệt mới. Thời điểm người dùng bấm nút không được dùng để kéo dài hiệu lực của quyết định.

### 8.2. Phê duyệt được tiêu thụ để tạo một lần thực thi bất biến trước hạn

Ở thiết kế khác, hệ thống có thể kiểm tra đầy đủ và cam kết tạo một lần thực thi trước hạn. Lệnh đã cam kết mang đúng tài khoản, hành động, phiên bản kế hoạch và định danh thực thi. Worker sau đó chỉ hoàn tất lệnh đó, không được tự thêm hành động hoặc đổi đối tượng.

Thiết kế này cần quy định thêm hạn xử lý của lệnh, điều kiện hủy và cách xử lý khi rủi ro thay đổi trước lúc tác động ra ngoài. Không được biến một lệnh chưa chạy thành quyền giữ chỗ vô thời hạn để bỏ qua hạn phê duyệt.

Nếu hành động ở nhà cung cấp danh tính đã bắt đầu trước hạn và chỉ nhận được phản hồi sau hạn, hết hạn phê duyệt không tự đảo ngược thay đổi đã xảy ra. Hệ thống cần đối chiếu kết quả theo định danh thực thi. Không tự gọi lại như một hành động mới chỉ vì lần chờ phản hồi đầu tiên đã hết thời gian.

Một giao dịch cục bộ cũng không làm cho lời gọi sang dịch vụ bên ngoài trở thành nguyên tử với cơ sở dữ liệu. Cần cơ chế xử lý lặp, đối chiếu kết quả và chính sách hủy rõ ràng tại ranh giới này.

## 9. Minh họa kiểm tra thời hạn bằng Java

Ví dụ dưới đây chỉ minh họa phép đánh giá cửa sổ thời gian và trạng thái của một phê duyệt. Nó chưa bao gồm kiểm tra bằng chứng, tenant, quyền, số người duyệt hoặc giao dịch tiêu thụ.

```java
import java.time.Clock;
import java.time.Instant;

enum ApprovalState {
    APPROVED,
    CONSUMED,
    REVOKED,
    SUPERSEDED
}

enum ApprovalWindowDecision {
    WITHIN_WINDOW,
    NOT_ACTIVE,
    NOT_YET_VALID,
    EXPIRED,
    INVALID_WINDOW
}

record ApprovalWindow(
        ApprovalState state,
        Instant notBefore,
        Instant expiresAt) {
}

final class ApprovalExpirationPolicy {
    private final Clock clock;

    ApprovalExpirationPolicy(Clock clock) {
        this.clock = clock;
    }

    ApprovalWindowDecision evaluate(ApprovalWindow approval) {
        if (!approval.notBefore().isBefore(approval.expiresAt())) {
            return ApprovalWindowDecision.INVALID_WINDOW;
        }
        if (approval.state() != ApprovalState.APPROVED) {
            return ApprovalWindowDecision.NOT_ACTIVE;
        }

        Instant now = clock.instant();
        if (now.isBefore(approval.notBefore())) {
            return ApprovalWindowDecision.NOT_YET_VALID;
        }
        if (!now.isBefore(approval.expiresAt())) {
            return ApprovalWindowDecision.EXPIRED;
        }
        return ApprovalWindowDecision.WITHIN_WINDOW;
    }
}
```

Các giá trị trong `ApprovalWindow` phải được tải từ dữ liệu có thẩm quyền, đã được kiểm tra tính hợp lệ, không lấy trạng thái và hạn do trình duyệt tự khai báo. `Clock` là phụ thuộc của máy chủ để việc lấy thời gian rõ ràng; nó không tự bảo đảm đồng bộ giữa mọi máy chủ.

Giá trị `WITHIN_WINDOW` chỉ có nghĩa cửa sổ thời gian đang phù hợp tại lúc đánh giá. Nó không phải quyết định cuối cùng cho phép khôi phục và không được lưu vào cache để dùng vô hạn. Nếu có cạnh tranh giữa các worker, phép đánh giá phải được phối hợp với cập nhật trạng thái theo cơ chế đã nêu ở phần trước.

Không cần một tác vụ nền đổi `APPROVED` thành `EXPIRED` đúng từng mili giây để phép kiểm tra có hiệu lực. Dịch vụ cho phép thực thi phải tự so sánh thời điểm, còn tác vụ nền có thể phục vụ hiển thị, thông báo và dọn dữ liệu theo chính sách.

## 10. Nhiều người duyệt và vòng phê duyệt

Nếu chính sách yêu cầu nhiều người duyệt, việc đã từng thu được đủ chữ ký không chứng minh hiện tại vẫn đủ các quyết định hợp lệ.

Ví dụ hồ sơ cần hai người duyệt độc lập:

| Người duyệt | Thời điểm cấp | Hết hạn | Trạng thái lúc 10:16 |
|---|---|---|---|
| A | 10:00 | 10:15 | Hết hạn |
| B | 10:10 | 10:25 | Còn trong hạn |

Tại 10:16, không thể thực thi dựa trên lập luận rằng “đã có hai phê duyệt”. Chỉ một quyết định còn trong cửa sổ thời gian, trừ khi hệ thống đã cam kết một lần thực thi hợp lệ trước đó theo ngữ nghĩa được quy định riêng.

Với chính sách tất cả người duyệt đều bắt buộc, thời hạn sử dụng chung không thể vượt quá quyết định hết hạn sớm nhất trong tập bắt buộc. Với chính sách chọn đủ số lượng từ một tập lớn hơn, cần xác định tập quyết định còn hợp lệ, độc lập và đúng phạm vi tại thời điểm cấp quyền; không chỉ lấy hạn nhỏ nhất của toàn bộ lịch sử quyết định.

Khi một quyết định hết hạn, không tự động lấy chữ ký của vòng cũ ghép với chữ ký vòng mới nếu chính sách yêu cầu duyệt cùng một vòng. `approvalRound`, phiên bản kế hoạch và phiên bản bằng chứng giúp ngăn việc ghép các quyết định không cùng nội dung.

Nếu hồ sơ có quyết định từ chối, cách xử lý phải theo chính sách của vòng duyệt. Không âm thầm bỏ quyết định từ chối khỏi phép đếm để đạt đủ số lượng đồng ý.

## 11. Xin phê duyệt lại và xử lý yêu cầu lặp

Khi phê duyệt hết hạn, quy trình phù hợp là đánh giá lại điều kiện hiện tại rồi tạo quyết định mới hoặc vòng mới theo chính sách. Không đơn giản cập nhật `expiresAt` của quyết định cũ vì như vậy làm thay đổi ý nghĩa của lịch sử.

Những nội dung cần xem lại có thể gồm tình trạng mất thiết bị, bằng chứng còn đủ mới không, tài khoản có bị nâng quyền không, kênh liên hệ có thay đổi không và có dấu hiệu lạm dụng mới không.

Quyết định mới nên liên kết với quyết định hoặc vòng đã hết hạn để giải thích vì sao cần duyệt lại. Lịch sử cũ vẫn được giữ theo chính sách lưu trữ và quyền truy cập thích hợp.

Phát hành lại email nhắc, tải lại trang hoặc gọi lại API do lỗi mạng không nên tự đặt lại đồng hồ hiệu lực. Một lần thử lại cùng định danh yêu cầu cần trả về kết quả hoặc đối tượng đã được tạo, thay vì âm thầm tạo một phê duyệt mới có hạn dài hơn.

Nếu người dùng liên tục xin phê duyệt lại, cần kiểm soát lạm dụng và tránh gây áp lực khiến người duyệt bấm đồng ý theo thói quen. Hạn chế tần suất và chuyển xử lý phải gắn với bối cảnh, không dùng một quy tắc tùy tiện để khóa mọi người dùng gặp sự cố thật.

## 12. Quan hệ với token khôi phục và phiên

Thiết kế cần chọn một trong các ngữ nghĩa phù hợp với hành động và ghi rõ nó.

### 12.1. Phê duyệt chỉ cho phép phát hành grant

Phê duyệt được kiểm tra và tiêu thụ khi cấp một grant khôi phục có giới hạn. Grant có thời hạn, mục đích và điều kiện thu hồi riêng. Nó không được trở thành phiên đăng nhập toàn quyền.

Nếu grant có thể còn sống sau khi phê duyệt hết hạn, điều đó phải là chủ đích của chính sách. Cần giới hạn thời gian và tác động của grant để không tạo một đường kéo dài quyền vô hạn. Hệ thống vẫn cần có khả năng thu hồi grant khi có rủi ro hoặc khi hồ sơ bị hủy.

### 12.2. Phê duyệt phải còn hiệu lực khi dùng grant

Nếu chính sách yêu cầu phê duyệt còn hạn tới thời điểm sử dụng, hạn của grant có thể được giới hạn bởi hạn phê duyệt, đồng thời bước tiêu thụ kiểm tra trạng thái có thẩm quyền.

Chỉ đặt `expiresAt` của token bằng hạn phê duyệt không giải quyết mọi trường hợp. Phê duyệt có thể bị thu hồi sớm hoặc kế hoạch bị thay thế, nên có thể cần kiểm tra trạng thái hiện hành ngoài phép so sánh thời gian.

### 12.3. Không đánh đồng hết hạn phê duyệt với thu hồi phiên

Khi khôi phục đã hoàn tất hợp lệ và người dùng có một phiên đăng nhập thông thường, việc phê duyệt cũ đến hạn không tự có nghĩa phải thu hồi phiên đó. Phiên chịu chính sách xác thực và kiểm soát rủi ro tương ứng.

Ngược lại, nếu phát hiện phê duyệt đã bị lạm dụng, cần xử lý các grant, yếu tố mới và phiên phát sinh theo quy trình ứng phó. Hết hạn tự nhiên của một bản ghi không xóa tác động của một hành động đã xảy ra.

## 13. Minh họa dòng thời gian

Giả sử chính sách của một hồ sơ cho phép dùng phê duyệt trong khoảng từ 10:00 đến trước 10:15. Các mốc dưới đây chỉ minh họa cách xác định điểm cấp quyền.

```text
10:00           10:14:50       10:15:00       10:15:20
  |                 |              |               |
Phê duyệt       Gửi yêu cầu     Hết hạn        Worker nhận việc
được cấp        vào hàng đợi
```

Nếu đưa vào hàng đợi chỉ là tiếp nhận yêu cầu, worker ở 10:15:20 phải từ chối dùng quyết định cũ và yêu cầu duyệt lại. Việc bấm nút lúc 10:14:50 không giữ chỗ quyền thực thi.

Nếu hệ thống đã đánh giá đầy đủ và cam kết một lần thực thi bất biến lúc 10:14:50, worker cần xử lý theo hạn riêng của lần thực thi và chính sách hủy tương ứng. Người vận hành phải nhìn thấy trạng thái “đã cam kết thực thi” khác với “đang chờ kiểm tra phê duyệt”.

Tại đúng 10:15:00, một lần cấp quyền mới bị chặn theo quy ước khoảng nửa mở. Nếu giao diện vẫn còn hiển thị một giây vì chậm cập nhật, máy chủ vẫn dùng thời gian và trạng thái có thẩm quyền.

## 14. Thông báo, dấu vết và dọn dữ liệu

Giao diện nên hiển thị thời điểm hết hạn rõ ràng, trạng thái hiện tại và cách xin duyệt lại. Khi hết hạn, thông báo cần giải thích rằng quyết định không còn được dùng để cho phép hành động mới, thay vì báo chung chung “lỗi hệ thống”.

Thông báo nhắc hạn không nên chứa token khôi phục hoặc dữ liệu bằng chứng nhạy cảm. Đường dẫn trong thông báo đưa người có thẩm quyền về một chức năng được bảo vệ; nó không thay thế xác thực, phân quyền và kiểm tra thời hạn trên máy chủ.

Nhật ký nên giúp phân biệt:

- Phê duyệt được cấp với hạn nào, dựa trên phiên bản chính sách và kế hoạch nào.
- Có yêu cầu dùng phê duyệt vào thời điểm nào và kết quả quyết định là gì.
- Phê duyệt được tiêu thụ cho lần thực thi nào nếu áp dụng mô hình dùng một lần.
- Quyết định bị thu hồi, bị thay thế hay hết hạn tự nhiên.
- Có lần xin duyệt lại nào và nó liên kết với lịch sử cũ ra sao.

Không cần ghi một sự kiện hết hạn cho mỗi lần mở trang. Có thể ghi chuyển trạng thái nghiệp vụ hoặc quyết định sử dụng theo thiết kế, đồng thời tránh tạo nhiều bản ghi gây hiểu nhầm rằng phê duyệt được cấp lại.

Dọn dữ liệu hết hạn là công việc lưu trữ, không phải cơ chế duy nhất để chặn sử dụng. Không xóa ngay mọi quyết định hết hạn nếu hồ sơ còn cần phục vụ rà soát hoặc điều tra. Thời hạn giữ dữ liệu cần được xác định riêng với thời hạn sử dụng phê duyệt.

## 15. Các lỗi thiết kế cần tránh

| Lỗi | Hậu quả |
|---|---|
| Chỉ ẩn nút khi bộ đếm trình duyệt về không | API vẫn có thể nhận và thực thi phê duyệt đã hết hạn |
| Chỉ dựa vào tác vụ nền đổi trạng thái | Quyết định quá hạn vẫn dùng được khi tác vụ chạy trễ |
| Gia hạn khi tải lại trang hoặc gửi lại email | Quyền có thể được kéo dài mà không có quyết định mới |
| Chỉ kiểm tra trước khi vào hàng đợi | Yêu cầu được thực thi nhiều thời gian sau khi điều kiện đã thay đổi |
| Kiểm tra thời gian nhưng không gắn với cập nhật trạng thái | Nhiều worker có thể tạo nhiều lần thực thi |
| Dùng phê duyệt cũ cho kế hoạch mới | Người duyệt chưa từng đồng ý với hành động thực tế |
| Gom phê duyệt hết hạn với phê duyệt mới để đủ số lượng | Mất ý nghĩa của cửa sổ thời gian và vòng duyệt |
| Coi hết hạn là hoàn tác hành động đã xảy ra | Credential hoặc phiên không được xử lý đúng với trạng thái thực tế |

Một cơ chế hết hạn tốt phải xác định được đối tượng nào hết hiệu lực, thời điểm nào có thẩm quyền và bước nào đang tiêu thụ quyết định. Khi kết hợp với kiểm tra phạm vi, bằng chứng, rủi ro, quyền dùng một lần và kiểm soát phiên, thời hạn phê duyệt mới thực sự giới hạn được cửa sổ can thiệp vào tài khoản.
