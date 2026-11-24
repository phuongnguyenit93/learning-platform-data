# Support approval workflow — Luồng phê duyệt khôi phục tài khoản qua bộ phận hỗ trợ

## 1. Phê duyệt của hỗ trợ có ý nghĩa gì?

**Support approval workflow** là quy trình trong đó nhân viên có thẩm quyền xem xét một yêu cầu khôi phục, đưa ra quyết định dựa trên bằng chứng và chính sách, rồi để hệ thống cấp quyền thực hiện một tác vụ cụ thể trong giới hạn đã được xác định.

Trong dịch vụ khôi phục tài khoản, tác vụ có thể là đặt lại mật khẩu, thay MFA, cho phép đăng ký passkey mới hoặc lấy lại quyền truy cập sau khi mất thiết bị xác thực. Mỗi tác vụ có tác động khác nhau; không nên gộp thành một quyền chung mang tên “khôi phục mọi thứ”.

Một ticket được tạo không chứng minh người mở là chủ tài khoản. Một nhân viên đánh dấu “đã kiểm tra” cũng không tự là bằng chứng. Quy trình cần xác định điều gì đã được xác minh, ai được ra quyết định và hệ thống được phép làm gì sau quyết định đó.

Cần tách ba kết quả:

| Kết quả | Ý nghĩa |
| --- | --- |
| Review completed | Một người hoặc thành phần đã hoàn tất bước xem xét |
| Support approval recorded | Một quyết định phê duyệt hợp lệ được lưu cho phạm vi cụ thể |
| Recovery action completed | Tác vụ được bảo vệ đã thực sự hoàn tất |

Phê duyệt không tự đổi mật khẩu, xóa MFA hoặc cấp session đăng nhập đầy đủ. Nó là một điều kiện đầu vào của bước thực thi có kiểm soát.

[OWASP Multifactor Authentication Cheat Sheet — Resetting MFA](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#resetting-mfa) nêu phương án liên hệ hỗ trợ với quy trình xác minh danh tính chặt chẽ. Việc có nhân viên tham gia không tự làm phương thức khôi phục an toàn; chính các kiểm soát của quy trình mới quyết định điều đó.

## 2. Phân vai và giới hạn quyền

Một mô hình minh họa có thể có các vai trò sau:

| Vai trò | Trách nhiệm | Giới hạn |
| --- | --- | --- |
| Intake agent | Tiếp nhận case, hướng dẫn bước hợp lệ, kiểm tra đủ hồ sơ | Không tự đánh dấu bằng chứng đã đạt chỉ vì người yêu cầu cung cấp |
| Evidence verifier | Đánh giá bằng chứng theo phương pháp được phê duyệt | Không tự mở rộng phạm vi tác vụ |
| Approver | Chấp thuận hoặc từ chối hồ sơ thuộc quyền xét duyệt | Không tự thực hiện mọi thay đổi bằng công cụ quản trị |
| Recovery executor | Thực thi quyền tác vụ còn hợp lệ | Không bỏ kiểm tra vì ticket mang nhãn APPROVED |
| Policy administrator | Quản lý chính sách và quyền của nhân viên | Không mặc nhiên có quyền khôi phục tài khoản tùy ý |
| Security reviewer | Xử lý dấu hiệu chiếm đoạt hoặc ngoại lệ thuộc thẩm quyền | Không dùng nhãn khẩn cấp để xóa điều kiện xác minh |

Một người có thể giữ nhiều vai trò nếu chính sách cho phép, nhưng hệ thống phải kiểm tra xung đột nhiệm vụ. Việc cùng một người đăng nhập bằng hai tài khoản không tạo ra hai người phê duyệt độc lập.

Quyền cần được kiểm tra theo loại tác vụ, tenant, nhóm tài khoản, mức rủi ro và trạng thái case. Có quyền mở ticket không đồng nghĩa có quyền xem toàn bộ hồ sơ hoặc phê duyệt thay MFA.

Các kiểm tra phải nằm ở server. Ẩn nút Approve trên giao diện không ngăn một lời gọi API trực tiếp. Role hoặc tenant do trình duyệt gửi không được coi là nguồn quyền đáng tin cậy.

## 3. Ràng buộc yêu cầu với phạm vi tác vụ rõ ràng

Trước khi xét duyệt, hệ thống cần biết chính xác đối tượng và tác động đang được đề nghị.

Một hồ sơ xem xét có thể chứa:

- Account và tenant do server xác định.
- Recovery request liên quan.
- Mục đích: chẳng hạn RESET_PASSWORD hoặc REBIND_MFA.
- Những thay đổi được phép và những thay đổi ngoài phạm vi.
- Kênh hoặc ngữ cảnh tiếp tục khôi phục đã được thiết lập phù hợp.
- Tập bằng chứng và kết quả kiểm tra.
- Phiên bản ngữ cảnh bảo mật của tài khoản.
- Policy áp dụng và thời hạn của hồ sơ.

Ví dụ, chấp thuận cho đăng ký lại MFA không tự cho phép đổi email bảo mật. Nếu người yêu cầu bổ sung yêu cầu đổi email trong khi chờ, đó là thay đổi đáng kể cần được xử lý như phạm vi mới hoặc phiên bản xét duyệt mới.

Một email mới khai báo để trao đổi cũng chưa mặc nhiên là đích nhận quyền khôi phục. Nếu quyền được gửi tới một địa chỉ do người yêu cầu tự chọn mà chưa có kiểm soát tương ứng, người yêu cầu có thể điều khiển nơi tiếp nhận dù hồ sơ ban đầu được xét đúng.

Phê duyệt cần gắn với một **snapshot xét duyệt** có phiên bản: tập dữ kiện mà người phê duyệt thực sự đã xem. Snapshot không nhất thiết chứa bản sao mọi giấy tờ; nó có thể giữ các tham chiếu được kiểm soát cùng kết quả xác minh.

Một digest của snapshot có thể giúp phát hiện thay đổi dữ liệu, nhưng không thay thế việc kiểm tra quyền hoặc chất lượng bằng chứng. Băm một hồ sơ không hợp lệ không làm hồ sơ đó hợp lệ.

## 4. Tiếp nhận và kiểm tra bằng chứng

Luồng hỗ trợ cần hướng người dùng tới các phương thức được sản phẩm hỗ trợ. Không yêu cầu họ gửi mật khẩu, mã dự phòng hoặc OTP cho nhân viên qua chat, email hay cuộc gọi. Nếu có bước nhập mã, người dùng nhập vào giao diện chính thức của cơ chế xác minh tương ứng.

Thông tin công khai, nội dung trong một email cũ hoặc ảnh chụp màn hình không tự chứng minh quyền sở hữu tài khoản. Một người tấn công có thể biết tên, nơi làm việc, số điện thoại hoặc lịch sử trao đổi.

Bằng chứng cần được đánh giá theo những câu hỏi cụ thể:

1. Phương pháp này có được policy cho phép cho loại tài khoản và tác vụ đó không?
2. Nguồn bằng chứng có đáng tin cậy và được kiểm tra đúng cách không?
3. Bằng chứng liên kết người yêu cầu với chính tài khoản đã tồn tại như thế nào?
4. Kết quả còn hiệu lực, đã bị thu hồi hoặc có dấu hiệu bị lạm dụng không?
5. Có điều kiện bổ sung nào chưa được đáp ứng?

[NIST SP 800-63B-4 — Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b/events/#recovery) phân biệt các phương thức khôi phục và việc lặp lại xác minh danh tính đối với tài khoản đã có liên kết danh tính phù hợp. Không nên coi việc xuất trình giấy tờ mới là đủ để chứng minh sở hữu một tài khoản vốn chưa được gắn với danh tính đó.

Kết quả kiểm tra nên có cấu trúc, chẳng hạn VERIFIED, REJECTED, INCONCLUSIVE hoặc EXPIRED theo hợp đồng. INCONCLUSIVE không phải VERIFIED. Nhân viên ghi chú “có vẻ đúng” không được tự chuyển kết quả máy hoặc quy trình thành đạt.

Hồ sơ nhạy cảm nên được giữ trong kho bằng chứng chuyên biệt với quyền và thời hạn riêng. Ticket và log vận hành chỉ cần các tham chiếu hoặc kết luận được phép xem, không sao chép toàn bộ tài liệu.

## 5. Trạng thái quy trình và các điều kiện chuyển

Một luồng minh họa:

~~~mermaid
flowchart TD
    A[RECEIVED] --> B[WAITING_EVIDENCE]
    B --> C[REVIEWABLE]
    C --> D[PENDING_APPROVAL]
    D --> E[APPROVED]
    E --> F[Kiểm tra điều kiện cấp quyền]
    F --> G[GRANT_ISSUED]
    G --> H[Kiểm tra quyền tại bước thực thi]
    H --> I[ACTION_COMPLETED]
    D --> J[REJECTED]
    D --> B
    E --> K[REVIEW_REQUIRED]
    K --> C
~~~

Sơ đồ trình bày nhánh chính. Các trạng thái hủy, hết hạn và sự cố cần được định nghĩa cho những bước thích hợp.

| Chuyển trạng thái | Điều kiện minh họa |
| --- | --- |
| WAITING_EVIDENCE → REVIEWABLE | Đủ đầu vào để xét theo hợp đồng, chưa khẳng định chắc chắn được chấp thuận |
| REVIEWABLE → PENDING_APPROVAL | Snapshot được chốt phiên bản và phân công người có quyền |
| PENDING_APPROVAL → APPROVED | Tập quyết định hợp lệ thỏa policy cho đúng snapshot |
| APPROVED → GRANT_ISSUED | Các điều kiện còn hiệu lực, thời gian chờ nếu có đã kết thúc |
| GRANT_ISSUED → ACTION_COMPLETED | Quyền được kiểm tra và tác vụ hoàn tất theo cơ chế thực thi |
| APPROVED → REVIEW_REQUIRED | Có thay đổi đáng kể hoặc điều kiện đã mất hiệu lực |

Không để client gửi trực tiếp state = APPROVED hoặc requiredApprovals = 0 để điều khiển luồng. Trạng thái và điều kiện chuyển là dữ liệu server quản lý.

Nếu người yêu cầu rút case, request hết hạn hoặc phát hiện dấu hiệu chiếm đoạt, các quyết định và quyền chưa dùng cần được xử lý theo policy. Không chỉ đổi nhãn ticket mà để một grant cũ tiếp tục dùng được.

Thời hạn đợi bổ sung hồ sơ, thời hạn quyết định và thời hạn quyền thực thi là những đại lượng khác nhau. Việc kéo dài một thời hạn không tự kéo dài những thời hạn còn lại.

## 6. Chính sách phê duyệt và tính độc lập

Số người cần phê duyệt phải dựa trên tác động, mô hình rủi ro và khả năng tổ chức, không có một con số phù hợp cho mọi hệ thống.

Ví dụ, một policy nội bộ có thể yêu cầu hai người độc lập cho nhánh hỗ trợ thay MFA của nhóm tài khoản có quyền cao. Đây là lựa chọn minh họa, không phải khẳng định mọi case đều phải có hai approver.

Một chính sách nhiều người cần quy định:

- Ai đủ điều kiện tham gia.
- Ai không được tự xét case mình tạo hoặc bằng chứng mình xác nhận.
- Những cặp nhiệm vụ nào bị coi là xung đột.
- Các quyết định phải thuộc cùng snapshot và cùng phạm vi.
- Có yêu cầu về nhóm quyền hoặc trách nhiệm khác nhau không.
- Cách xử lý khi xuất hiện quyết định từ chối.
- Quyền bị thu hồi sau phê duyệt được xử lý thế nào.
- Thời hạn áp dụng của từng quyết định.

Hai chữ ký không đủ nếu cả hai người chỉ xác nhận thông tin do một nguồn không đáng tin cung cấp. Kiểm soát nhiều người giúp giảm một số rủi ro sai sót và lạm quyền; nó không thay chất lượng bằng chứng.

Không tự chọn các phiếu thuận và bỏ qua phiếu từ chối để đạt đủ số. Policy phải xác định rõ một từ chối có chặn, buộc xem xét lại hay có quy trình giải quyết nào.

Nếu chuyển case sang nhóm khác, giữ lịch sử quyết định và lý do chuyển. Không tạo ticket mới để xóa dấu vết những lần từ chối trước đó. Những case liên quan cần được phát hiện ở phạm vi nội bộ có quyền truy cập phù hợp, không công khai thông tin tài khoản cho người yêu cầu.

## 7. Ghi quyết định như một dữ kiện có ràng buộc

Một quyết định phê duyệt cần thể hiện không chỉ “ai bấm nút” mà còn “đã chấp thuận điều gì”.

Ví dụ dữ liệu:

~~~json
{
  "decisionId": "56ca3cf3-946f-40c1-9eed-bdb0edf510fa",
  "reviewCaseId": "support-case-42",
  "recoveryRequestId": "recovery-request-91",
  "snapshotVersion": 7,
  "scope": "REBIND_MFA",
  "decision": "APPROVE",
  "approverRef": "operator-18",
  "policyVersion": "support-recovery-policy-v3",
  "accountSecurityContextVersion": 12,
  "evidenceAssessmentRef": "assessment-27",
  "reasonCode": "REQUIRED_EVIDENCE_SATISFIED",
  "decidedAt": "2026-11-24T11:00:00Z",
  "validUntil": "2026-11-24T12:00:00Z"
}
~~~

Mọi ID và thời điểm ở đây là dữ liệu minh họa. Khoảng hiệu lực một giờ không phải khuyến nghị chung.

approverRef, thời điểm server và quyền áp dụng phải được xác lập từ ngữ cảnh tin cậy. Trình duyệt không được tự chọn danh tính người phê duyệt.

Những dữ kiện quan trọng:

- snapshotVersion xác định bộ thông tin đã được xem.
- scope giới hạn tác vụ.
- accountSecurityContextVersion gắn quyết định với ngữ cảnh bảo mật liên quan.
- policyVersion giúp giải thích điều kiện dùng để xét.
- evidenceAssessmentRef trỏ tới kết quả đánh giá, không chứa nguyên tài liệu.
- validUntil giới hạn khả năng dùng lại một quyết định cũ.

Có thể dùng version riêng cho ngữ cảnh bảo mật thay vì version thay đổi theo mọi cập nhật không liên quan. Một lần ghi chú hỗ trợ không nhất thiết làm mất hiệu lực quyết định, nhưng đổi yếu tố xác thực hoặc đích nhận quyền có thể là thay đổi đáng kể.

Ghi chú tự do có thể bổ sung giải thích nhưng không thay thế các trường ràng buộc. Nó cũng không nên chứa bí mật hoặc toàn bộ hồ sơ xác minh.

## 8. Chống quyết định trùng và thay đổi đồng thời

Một approver có thể bấm hai lần, trình duyệt có thể gửi lại hoặc một request mạng có thể timeout sau khi server đã lưu quyết định.

API cần có cơ chế idempotency cho cùng một thao tác, đồng thời ràng buộc một người chỉ đóng góp số quyết định mà policy cho phép trên cùng snapshot. Hai request HTTP không được biến thành hai phiếu của hai người.

Khi hai approver xử lý cùng lúc:

1. Server kiểm tra cả hai đang xem cùng snapshot.
2. Mỗi quyết định được lưu với actor và phiên bản đúng.
3. Phép đánh giá tập quyết định được thực hiện dưới cơ chế đồng thời phù hợp.
4. Chuyển sang APPROVED chỉ xảy ra khi điều kiện thực sự thỏa.
5. Việc tạo quyền thực thi không bị lặp do hai luồng cùng thấy đủ số.

Nếu trong lúc xét, người yêu cầu đổi mục đích hoặc thêm đích liên hệ mới, quyết định cũ không tự áp dụng cho snapshot mới. Những phần thay đổi ảnh hưởng đến quyền phải được đưa vào xem xét lại theo policy.

Không dùng một cờ approved trên ticket để bỏ qua những vấn đề này. Cờ đó không thể hiện phạm vi, phiên bản, số phiếu hợp lệ hoặc thời hạn.

Nhân viên mất quyền hoặc rời nhóm trong lúc case chờ cũng là một thay đổi cần policy xử lý. Có thể phải đánh giá lại tính hợp lệ của tập quyết định trước khi cấp hoặc sử dụng quyền, thay vì chỉ kiểm tra quyền tại lần bấm đầu tiên.

## 9. Phê duyệt được chuyển thành quyền tác vụ có giới hạn

Sau APPROVED, hệ thống có thể tạo một recovery grant để cho phép bước tiếp theo. Grant cần được ràng buộc với:

- Account, tenant và request.
- Tác vụ cụ thể.
- Phiên bản hồ sơ hoặc quyết định có hiệu lực.
- Ngữ cảnh người yêu cầu hoặc kênh tiếp tục đã được thiết lập phù hợp.
- Thời hạn.
- Cơ chế dùng một lần hoặc giới hạn sử dụng theo hợp đồng.
- Điều kiện thu hồi và điều kiện kiểm tra lại.

Grant không nên là quyền quản trị chung. Quyền cho đăng ký một yếu tố mới không tự cho phép xem dữ liệu tài khoản, thay email bảo mật hoặc xóa mọi session.

Nếu grant được biểu diễn bằng token, việc sinh, lưu, chuyển giao và sử dụng token phải có cơ chế bảo vệ tương ứng. Nhân viên không cần đọc token rồi gửi thủ công qua một kênh tùy ý.

Không mặc định gửi grant tới địa chỉ mới mà người yêu cầu cung cấp. Việc chọn đích nhận quyền phải thuộc chính phạm vi đã được xác minh và phê duyệt.

Một phiên khôi phục hạn chế có thể cho phép nhập challenge hoặc hoàn thành đăng ký credential mới. Nó không phải session đăng nhập đầy đủ. Chỉ sau khi mọi điều kiện của luồng đã thỏa mới áp dụng chính sách đăng nhập tiếp theo.

Với passkey, người dùng cần hoàn tất quy trình đăng ký credential mới theo cơ chế của sản phẩm. Hỗ trợ không được yêu cầu người dùng gửi khóa riêng, và phê duyệt không có nghĩa hệ thống đã phục hồi một khóa riêng bị mất.

## 10. Kiểm tra cuối cùng tại điểm thực thi

Giữa lúc phê duyệt và lúc thực thi, tài khoản hoặc hồ sơ có thể thay đổi. Một grant chưa dùng có thể hết hạn, bị thu hồi hoặc không còn phù hợp vì chủ tài khoản đã tự khôi phục qua nhánh khác.

[OWASP Transaction Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html) đề cập kiểm soát ở server, ràng buộc dữ liệu giao dịch và bước kiểm tra cuối trước thực thi. Trong luồng hỗ trợ, các nguyên tắc đó được áp dụng cho đúng tác vụ khôi phục, không chỉ cho trạng thái ticket.

Một giao dịch minh họa khi tác vụ và dữ liệu kiểm soát nằm trong cùng cơ sở dữ liệu:

~~~text
BEGIN

  Khóa hoặc kiểm soát đồng thời phù hợp trên account, request và grant
  Nạp quyết định và policy áp dụng từ nguồn tin cậy
  Kiểm tra request chưa bị hủy, đóng hoặc hết hạn
  Kiểm tra grant còn hiệu lực, chưa dùng, chưa bị thu hồi
  Kiểm tra scope, người nhận quyền và phiên bản ngữ cảnh
  Kiểm tra tập quyết định vẫn đủ điều kiện theo policy
  Thực hiện đúng tác vụ được cho phép
  Tiêu thụ grant và cập nhật trạng thái
  Lưu audit bắt buộc
  Lưu công việc thông báo hoặc chuyển tiếp nếu cần

COMMIT
~~~

Không giữ khóa cơ sở dữ liệu trong một cuộc gọi mạng kéo dài rồi giả định toàn bộ các hệ thống cùng rollback được.

Nếu tác vụ đi qua nhiều kho hoặc nhà cung cấp, cần mô hình thực thi bền vững, idempotency và xử lý kết quả chưa biết phù hợp. Timeout không luôn đồng nghĩa tác vụ chưa xảy ra. Không tự phát lại grant hoặc cấp một grant khác chỉ để thử lại từ đầu.

Những tác động như vô hiệu hóa yếu tố cũ, thay credential và xử lý session phải được mô tả rõ trong phạm vi thực thi. Phê duyệt thay MFA không tự quyết định mọi chính sách session; nhưng hệ thống cũng không được quên xử lý session khi policy của tình huống bị chiếm đoạt yêu cầu.

Nếu policy thay đổi sau lúc phê duyệt, cần có quy tắc xác định quyết định cũ còn được phép dùng hay phải xét lại. Không để client chọn một phiên bản policy dễ hơn.

## 11. Trải nghiệm của approver phải giúp ra quyết định đúng

Giao diện xét duyệt nên trình bày những thông tin người có quyền cần biết:

- Tác vụ và tác động chính xác.
- Tài khoản, tenant và phạm vi công việc phù hợp.
- Kết quả bằng chứng cùng nguồn và thời hạn.
- Những dữ kiện chưa kết luận được.
- Những thay đổi so với snapshot đã xem trước đó.
- Quyết định khác và các xung đột liên quan.
- Policy áp dụng và lý do hệ thống yêu cầu thêm bước.

Không chỉ hiển thị nút Approve cạnh một ghi chú “khách hàng đang gấp”. Việc thúc ép về thời gian không chứng minh danh tính.

Đối với thao tác nhạy cảm, có thể yêu cầu xác thực lại hoặc mức xác thực phù hợp cho nhân viên theo policy. Một session bị đánh cắp của nhân viên không nên có khả năng duyệt vô hạn mà không có các kiểm soát khác.

API cần kiểm tra trạng thái, version và quyền kể cả khi giao diện đã kiểm tra. Các cơ chế bảo vệ request của phiên nhân viên, nguồn thao tác và việc hiển thị xác nhận phải được thiết kế phù hợp; không phụ thuộc vào một trường ẩn trong form.

Người phê duyệt không nhất thiết phải xem nguyên tài liệu nếu kết quả đánh giá tin cậy và tham chiếu đủ cho nhiệm vụ. Khi cần xem chi tiết, quyền mở hồ sơ cần được kiểm tra riêng và có dấu vết.

## 12. Ngoại lệ, khẩn cấp và thất bại phải có đường xử lý

Những câu như “tôi là giám đốc”, “đang ở sân bay” hoặc “quản lý của bạn đã đồng ý qua điện thoại” là dữ kiện cần xử lý theo quy trình, không phải quyền bỏ qua xác minh.

Một quy trình ngoại lệ được thiết kế trước có thể quy định:

- Ai có thẩm quyền xử lý.
- Những điều kiện nào vẫn không được bỏ.
- Bằng chứng hoặc kiểm soát thay thế được chấp nhận.
- Phạm vi quyền được cấp.
- Thời hạn và yêu cầu theo dõi.
- Cách ghi nhận lý do và các quyết định.

Nhãn khẩn cấp không được tự đặt requiredApprovals về không hoặc mở một endpoint quản trị bỏ kiểm tra. Người quản lý không được chuyển lời chấp thuận qua ghi chú rồi làm mất nguồn gốc quyết định.

Nếu thiếu bằng chứng, kết quả đúng có thể là cần bổ sung, không kết luận được hoặc từ chối. Không chuyển INCONCLUSIVE thành APPROVE chỉ để giảm thời gian xử lý.

Quy trình cũng cần có lối kết thúc rõ: case không đủ điều kiện không nên nằm vô thời hạn trong hàng chờ không ai chịu trách nhiệm. Người yêu cầu cần biết bước tiếp theo hoặc kết quả ở mức thông tin được phép cung cấp.

Việc thiếu nhân sự phê duyệt không tự tạo quyền cho một người tự duyệt. Nếu có cơ chế thay thế, nó phải thuộc policy; nếu không có, hệ thống giữ trạng thái chờ hoặc kết thúc theo hợp đồng thay vì lách điều kiện.

## 13. Thông báo, audit và số liệu vận hành

Thông báo cần gắn với đúng sự kiện:

- Case được tiếp nhận.
- Cần bổ sung đầu vào.
- Quyết định được lưu.
- Quyền tiếp tục được cấp nếu phù hợp.
- Tác vụ thực sự hoàn tất.
- Request bị hủy, hết hạn hoặc bị thu hồi quyền.

Không gửi thư “MFA đã thay thành công” chỉ vì approver vừa chấp thuận. Không gửi cảnh báo bảo mật duy nhất tới địa chỉ mới chưa được thiết lập phù hợp.

Thông báo về thay đổi nhạy cảm nên tới những kênh được policy chọn từ nguồn tin cậy. Người khởi xướng không được tự thay danh sách người nhận cảnh báo để che hoạt động.

Audit cần giữ được:

- Actor thực sự của bước tiếp nhận, đánh giá, phê duyệt và thực thi.
- Snapshot, scope, policy và ngữ cảnh liên quan.
- Những quyết định thuận, từ chối, yêu cầu bổ sung và thu hồi.
- Lý do xét lại sau thay đổi.
- Sự kiện grant được cấp, dùng, hết hạn hoặc thu hồi.
- Kết quả tác vụ đã được xác nhận.

Không sửa quyết định cũ để trông như người phê duyệt đã xem snapshot mới. Nếu cần đính chính, lưu bản bổ sung và liên kết phù hợp.

Metrics có thể đo thời gian chờ, số hồ sơ theo trạng thái và nhóm kết quả. Không gắn email, giấy tờ hoặc case ID làm label. Một tỷ lệ chấp thuận cao không tự chứng minh quy trình tốt; nó có thể phản ánh giảm điều kiện xét duyệt.

Mục tiêu vận hành cần cân bằng thời gian hỗ trợ với việc giữ đủ kiểm soát. Không thưởng cho nhân viên chỉ dựa trên tốc độ đóng hoặc số case được approve.

## 14. Tình huống vận dụng

Một người báo mất điện thoại có MFA và passkey. Họ mở case yêu cầu đăng ký lại MFA, đồng thời đưa một địa chỉ email mới để nhận kết quả.

Luồng minh họa xử lý như sau:

1. Intake tạo case và hướng dẫn phương thức xác minh được policy hỗ trợ; email mới chưa thành kênh nhận quyền.
2. Bằng chứng được đánh giá và liên kết với tài khoản theo phương pháp phù hợp. Hồ sơ chưa đủ không được đưa thành VERIFIED.
3. Snapshot phiên bản 7 được chốt cho phạm vi REBIND_MFA.
4. Policy của nhóm tài khoản này yêu cầu hai approver độc lập; các quyết định đều phải thuộc phiên bản 7.
5. Trong lúc chờ, người yêu cầu bổ sung đề nghị đổi email bảo mật. Hệ thống không tự mở rộng hai quyết định cũ sang thay đổi đó.
6. Sau khi phạm vi được xử lý đúng quy trình, hệ thống chỉ cấp quyền tác vụ tương ứng, với thời hạn và ngữ cảnh tiếp tục được ràng buộc.
7. Trước khi thực thi, hệ thống kiểm tra request, grant, phiên bản bảo mật và các điều kiện hiện tại.
8. Tác vụ hoàn tất mới tạo sự kiện hoàn tất, thông báo liên quan và xử lý session theo policy.
9. Nếu người dùng đã tự khôi phục qua nhánh khác hoặc request bị hủy trước bước 7, grant cũ không được tiếp tục thay yếu tố.

Trong toàn bộ quá trình, cần giữ rõ **ai có quyền quyết định, quyết định dựa trên dữ kiện nào, cho phép tác vụ nào và còn hiệu lực tới đâu**. Quy trình hỗ trợ chỉ hoàn thành vai trò bảo vệ khi những ràng buộc đó tiếp tục được kiểm tra tại thời điểm hành động.
