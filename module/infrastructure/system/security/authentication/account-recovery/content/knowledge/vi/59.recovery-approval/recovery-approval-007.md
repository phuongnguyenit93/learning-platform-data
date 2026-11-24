# Approval decision audit — Kiểm toán quyết định phê duyệt khôi phục

## 1. Một quyết định khôi phục cần để lại dấu vết gì?

Khi quản trị viên phê duyệt khôi phục tài khoản, hệ thống có thể cho phép người dùng đặt lại mật khẩu, đăng ký lại MFA hoặc thiết lập một passkey mới sau khi mất phương thức xác thực. Quyết định này tác động trực tiếp đến quyền truy cập tài khoản. Nếu sau đó xuất hiện khiếu nại hoặc dấu hiệu chiếm đoạt tài khoản, một dòng log “khôi phục thành công” không đủ để xác định điều gì đã xảy ra.

**Approval decision audit** là việc ghi nhận và bảo vệ dấu vết của quyết định phê duyệt để có thể giải thích ai đã quyết định, quyết định điều gì, dựa trên căn cứ nào, trong điều kiện nào và quyết định đó đã được sử dụng ra sao.

Đối với `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, dấu vết phải kết nối được các bước xác minh danh tính, đánh giá rủi ro, phê duyệt, cấp quyền khôi phục dùng một lần và kiểm soát phiên. Mục tiêu là dựng lại chuỗi quyết định bảo mật, đồng thời tránh biến nhật ký thành nơi lưu mật khẩu, token hoặc bản sao giấy tờ không cần thiết.

### Ví dụ mở đầu

Một người báo mất thiết bị MFA. Hai quản trị viên duyệt yêu cầu, hệ thống cấp quyền đăng ký lại MFA, nhưng người dùng thật phản ánh rằng họ chưa từng gửi yêu cầu đó. Người điều tra cần phân biệt:

- Ai đã mở yêu cầu và người đó đã được xác thực như thế nào?
- Hai quản trị viên đã duyệt cùng một phiên bản yêu cầu hay hai phiên bản khác nhau?
- Họ đã xem bộ bằng chứng nào và áp dụng chính sách nào?
- Quyền thực tế được cấp có đúng phạm vi được duyệt không?
- Quyền đã được dùng một lần vào thời điểm nào, và các phiên cũ đã được xử lý ra sao?

Nếu các bước chỉ chia sẻ một cờ `approved = true`, phần lớn câu hỏi trên không có câu trả lời đáng tin cậy.

## 2. Phân biệt quyết định, quyền được cấp và kết quả thực thi

Một luồng khôi phục có nhiều sự kiện bảo mật khác nhau:

| Đối tượng | Ý nghĩa | Không được suy ra trực tiếp |
|---|---|---|
| Kết quả xác minh bằng chứng | Một phương pháp đã xác minh được thuộc tính cụ thể | Toàn bộ yêu cầu đã được phê duyệt |
| Quyết định của người duyệt | Người có thẩm quyền chấp thuận hoặc từ chối một phạm vi | Quyền khôi phục đã được cấp thành công |
| Kết quả tổng hợp phê duyệt | Tập quyết định đáp ứng chính sách hiện tại | Người dùng đã hoàn tất khôi phục |
| Quyền khôi phục được cấp | Một quyền hạn chế tồn tại và có thời hạn | Quyền đã được sử dụng |
| Quyền khôi phục được tiêu thụ | Một thao tác đã dùng quyền đó | Mọi thao tác kiểm soát phiên đều đã hoàn tất |
| Kết quả xử lý phiên | Một hành động với phiên hoặc thông tin xác thực đã được thực hiện | Người yêu cầu ban đầu chắc chắn là chủ thể hợp pháp |

Nhật ký cần ghi đúng loại sự kiện. Không ghi `RECOVERY_COMPLETED` ngay khi quản trị viên nhấn duyệt, vì hành động đăng ký lại yếu tố xác thực có thể chưa diễn ra hoặc có thể thất bại.

Tương tự, một quyết định bị từ chối, một yêu cầu cần bổ sung bằng chứng và một lỗi kỹ thuật khi lưu quyết định là các kết quả khác nhau. Nếu gộp tất cả vào `FAILED`, người điều tra không biết hệ thống đã chủ động ngăn hành động hay đơn giản là chưa xử lý được.

## 3. Những câu hỏi mà một bản ghi quyết định phải trả lời

Một bản ghi hữu ích cần trả lời được các nhóm câu hỏi sau:

| Nhóm | Câu hỏi cần giải thích |
|---|---|
| Chủ thể | Người yêu cầu là ai? Tài khoản nào chịu tác động? Ai duyệt? Dịch vụ nào ghi nhận? |
| Phạm vi | Hành động nào được đề nghị? Hành động nào thực sự được cho phép? |
| Căn cứ | Bộ bằng chứng, kết quả xác minh và đánh giá rủi ro nào đã được sử dụng? |
| Chính sách | Phiên bản chính sách nào áp dụng? Những điều kiện bắt buộc nào đã đáp ứng? |
| Thời gian | Khi nào quyết định xảy ra? Hiệu lực đến khi nào? Khi nào sự kiện được lưu hoặc nhận? |
| Tính nhất quán | Quyết định gắn với phiên bản yêu cầu nào? Có thay đổi sau đó không? |
| Sử dụng | Quyết định đã cấp quyền nào? Quyền đó đã được dùng, hết hạn hay thu hồi? |
| Giới hạn | Dữ liệu nào không được lưu, đã hết thời gian lưu hoặc chưa thể xác minh? |

Không nhất thiết mọi câu trả lời nằm trong một bảng hoặc một sự kiện. Có thể dùng các bản ghi liên kết, miễn định danh ổn định, quyền truy cập rõ ràng và có thể dựng lại quan hệ khi cần.

## 4. Mô hình bản ghi quyết định

Một mô hình minh họa:

```text
decisionId
tenantId
accountId
recoveryRequestId
requestVersion
requestedAction
requestedActionDigest
decisionOutcome
approvedScope
reasonCodes
reviewerId
reviewerAuthorityReference
authenticationContextReference
evidenceSetId
evidenceSetVersion
riskAssessmentId
policyId
policyVersion
decidedAt
usableUntil
supersedesDecisionId
recordedByService
recordedAt
```

### Chủ thể yêu cầu khác người duyệt

`accountId` xác định tài khoản chịu tác động. Người gửi yêu cầu, người đại diện tổ chức, người duyệt và tài khoản dịch vụ ghi nhận sự kiện có thể là các chủ thể khác nhau. Không dùng một trường `userId` cho tất cả những vai trò này.

`recordedByService` cho biết thành phần nào lưu quyết định, không thay thế `reviewerId`. Nếu backend ghi “hành động bởi recovery-service” cho mọi phiếu duyệt, dấu vết không xác định được người thực sự ra quyết định.

### Ràng buộc nội dung quyết định

`requestVersion` và `requestedActionDigest` giúp phát hiện việc áp dụng phê duyệt cho yêu cầu đã thay đổi. Cần định nghĩa rõ dữ liệu chuẩn hóa dùng để tính digest, bao gồm các trường ảnh hưởng đến quyền như tài khoản, loại hành động và đích nhận kết quả nếu đích đó thuộc nội dung được duyệt.

Digest không thay thế hồ sơ hành động hoặc kiểm tra quyền truy cập. Nếu không giữ được cách chuẩn hóa và những dữ liệu cần thiết theo chính sách lưu trữ, một chuỗi băm đơn lẻ không giải thích được người duyệt đã chấp thuận điều gì.

### Tham chiếu thẩm quyền và ngữ cảnh xác thực

`reviewerAuthorityReference` có thể trỏ đến kết quả kiểm tra vai trò hoặc một bản chụp quyền phù hợp tại thời điểm quyết định. Chỉ nhìn vai trò hiện tại không đủ để biết người đó có thẩm quyền lúc duyệt hay không.

`authenticationContextReference` ghi nhận kết quả của luồng xác thực người duyệt, chẳng hạn việc hoàn thành xác thực tăng cường theo chính sách. Không ghi cookie, access token hoặc mã MFA để chứng minh điều đó.

## 5. Ví dụ sự kiện có cấu trúc

Ví dụ dưới đây dùng dữ liệu giả và chỉ mô tả việc một người duyệt chấp thuận một phạm vi. Nó chưa khẳng định yêu cầu đã đủ số phiếu hoặc quyền đã được cấp.

```json
{
  "schemaVersion": 1,
  "eventId": "evt-demo-501",
  "eventType": "RECOVERY_APPROVAL_DECISION_RECORDED",
  "tenantId": "tenant-demo-12",
  "aggregateId": "recovery-demo-742",
  "aggregateSequence": 8,
  "decisionId": "decision-demo-19",
  "requestVersion": 3,
  "subjectAccountId": "account-demo-742",
  "actor": {
    "type": "ADMINISTRATOR",
    "id": "admin-demo-27",
    "authorityReference": "authority-check-demo-91"
  },
  "action": "ALLOW_MFA_REENROLLMENT",
  "outcome": "APPROVED_FOR_SCOPE",
  "approvedScope": ["MFA_REENROLLMENT"],
  "reasonCodes": ["REQUIRED_EVIDENCE_ACCEPTED"],
  "evidenceSetReference": {
    "id": "evidence-set-demo-66",
    "version": 2
  },
  "riskAssessmentId": "risk-demo-54",
  "policyReference": {
    "id": "administrative-recovery",
    "version": "demo-v4"
  },
  "decidedAt": "2026-11-24T03:20:00Z",
  "usableUntil": "2026-11-24T03:35:00Z",
  "recordedAt": "2026-11-24T03:20:01Z",
  "recordedByService": "account-recovery",
  "correlationId": "correlation-demo-33"
}
```

Hệ thống thực tế cần xác định rõ ý nghĩa và quy tắc của từng trường, không sao chép các ID hoặc thời hạn minh họa làm cấu hình triển khai.

`schemaVersion` giúp hệ thống đọc sự kiện biết cách diễn giải cấu trúc. `eventId` dùng để nhận diện một sự kiện duy nhất; `decisionId` nhận diện quyết định; `correlationId` giúp liên kết hành trình xử lý. Ba giá trị này phục vụ mục đích khác nhau, không nên gộp làm một.

`aggregateSequence` biểu diễn thứ tự trong một yêu cầu khi hệ thống có cơ chế cấp thứ tự nhất quán cho yêu cầu đó. Nó không phải số thứ tự toàn cục của mọi quyết định trong hệ thống.

## 6. Ghi lý do đủ rõ nhưng không làm lộ bí mật

Một quyết định chỉ có `APPROVED` hoặc `REJECTED` thường không đủ để giải thích. Nên dùng mã nguyên nhân có ý nghĩa ổn định và mô tả nội bộ phù hợp.

Ví dụ mã nguyên nhân:

```text
REQUIRED_EVIDENCE_ACCEPTED
MANDATORY_EVIDENCE_MISSING
EVIDENCE_OUTDATED
MATERIAL_CONFLICT_UNRESOLVED
REVIEWER_NOT_AUTHORIZED
REQUEST_VERSION_CHANGED
ACTION_SCOPE_NOT_ALLOWED
SECURITY_REVIEW_REQUIRED
```

Đây là danh sách minh họa, không phải các mã bắt buộc cho mọi dịch vụ. Ý nghĩa của mã cần được quản lý theo phiên bản để một báo cáo cũ không bị diễn giải theo định nghĩa mới đã thay đổi.

Nếu một quyết định có nhiều lý do, lưu tập mã và xác định lý do chính theo quy tắc rõ ràng. Không bỏ mất cảnh báo an ninh chỉ vì một điều kiện khác được đánh giá trước.

Ghi chú tự do có thể bổ sung bối cảnh, nhưng không nên chứa dữ liệu giấy tờ, mã OTP, recovery code hoặc nội dung riêng tư không cần thiết. Không dùng ghi chú như nơi thay thế toàn bộ hồ sơ bằng chứng.

Thông báo ra ngoài và lý do kiểm toán nội bộ không nhất thiết giống nhau. Người dùng có thể nhận hướng dẫn bổ sung xác minh, trong khi nhật ký nội bộ ghi rõ điều kiện nào chưa đáp ứng. Việc tách này giúp hỗ trợ người dùng mà không tiết lộ chi tiết cơ chế phát hiện lạm dụng cho người chưa được xác minh.

## 7. Bảo đảm quyết định và dấu vết không lệch nhau

Một lỗi nguy hiểm là ghi trạng thái phê duyệt thành công rồi mới gửi một dòng log tới dịch vụ khác. Nếu ứng dụng dừng giữa hai bước, quyền đã được chấp thuận nhưng dấu vết bị thiếu.

Trong mô hình cùng cơ sở dữ liệu, có thể ghi trong một transaction:

1. Kiểm tra phiên bản yêu cầu, quyền người duyệt và điều kiện hiện tại.
2. Chèn bản ghi quyết định có định danh ổn định.
3. Cập nhật trạng thái liên quan bằng cơ chế kiểm soát đồng thời.
4. Ghi bản ghi outbox mô tả sự kiện quyết định.
5. Commit, sau đó mới phát sự kiện từ outbox sang kho kiểm toán tập trung.

```text
Nhận lệnh duyệt
    → kiểm tra quyền và ngữ cảnh
    → transaction: quyết định + thay đổi trạng thái + outbox
    → commit
    → bộ chuyển tiếp gửi sự kiện
    → kho kiểm toán tiếp nhận có chống trùng
```

Transaction cục bộ giúp ràng buộc dữ liệu trong phạm vi cơ sở dữ liệu đó. Nó không tự tạo ra một transaction xuyên tất cả dịch vụ bên ngoài. Nếu quyết định và quyền khôi phục được quản lý bởi những hệ thống độc lập, cần thiết kế giao thức và trạng thái trung gian để xử lý mất kết nối, thử lại và kết quả chưa xác định.

### Khi hệ thống ghi nhận gặp lỗi

Nếu không thể ghi bền vững bản ghi quyết định và dấu vết tối thiểu cần thiết, hệ thống không nên cấp một phê duyệt mới mà chính nó không thể giải thích lại. Cần trả lỗi kỹ thuật hoặc giữ yêu cầu chờ xử lý theo quy trình được định nghĩa.

Kho kiểm toán tập trung tạm thời không nhận dữ liệu là trường hợp khác với transaction cục bộ thất bại. Nếu sự kiện đã nằm bền vững trong outbox, bộ chuyển tiếp có thể gửi lại sau; cần theo dõi tồn đọng và giới hạn vận hành. Không tự đồng nhất “chưa xuất hiện trên dashboard” với “quyết định chưa được ghi”.

Nếu client mất kết nối sau khi transaction có thể đã commit, không khẳng định thao tác đã rollback chỉ vì không nhận được phản hồi. Tìm lại operation hoặc quyết định bằng idempotency key được ràng buộc với người gọi và nội dung yêu cầu trước khi thử tạo quyết định mới.

Các nỗ lực bị chặn trước khi có quyền truy cập yêu cầu cũng cần được ghi nhận ở luồng sự kiện an ninh thích hợp. Không tạo một bản ghi phê duyệt thành công để biểu diễn một lời gọi trái quyền.

## 8. Thử lại, giao trùng và thứ tự sự kiện

Một hệ thống phát sự kiện có thể giao cùng một sự kiện nhiều lần. Kho kiểm toán nên nhận diện trùng bằng `eventId` hoặc khóa sự kiện đã được thiết kế rõ, thay vì ghi thêm một “lần duyệt” mới mỗi khi bộ chuyển tiếp thử lại.

Phân biệt các trường hợp:

| Trường hợp | Cách hiểu |
|---|---|
| Cùng `eventId`, cùng nội dung | Lần giao lại của cùng sự kiện |
| Cùng `eventId`, khác nội dung | Bất nhất cần điều tra, không âm thầm ghi đè |
| Hai quyết định khác nhau trên cùng yêu cầu | Hai hành vi nghiệp vụ riêng, cần giữ cả hai |
| Retry cùng operation đã thành công | Trả trạng thái đã ghi, không tạo thêm quyết định |
| Cùng idempotency key nhưng khác hành động | Xung đột nội dung, cần từ chối theo contract |

Không dùng timestamp làm khóa chống trùng. Hai người có thể duyệt trong cùng một đơn vị thời gian, trong khi cùng một sự kiện có thể được giao lại ở những thời điểm khác nhau.

Sự kiện có thể đến kho tập trung không theo thứ tự xảy ra. Dùng định danh quan hệ, phiên bản và thứ tự theo yêu cầu nếu có để dựng lại trình tự. Không sắp xếp theo thời điểm nhận rồi kết luận rằng một quyền đã được dùng trước khi nó được cấp.

## 9. Thời gian và phiên bản chính sách

Một dấu vết thường cần phân biệt:

- `decidedAt`: thời điểm quyết định được xác lập theo ngữ nghĩa backend.
- `recordedAt`: thời điểm bản ghi được lưu ở nguồn.
- `receivedAt`: thời điểm kho tập trung nhận sự kiện.
- `usableUntil`: hạn có thể sử dụng quyết định, nếu áp dụng.
- Thời điểm thu hồi, cấp quyền và tiêu thụ quyền: các sự kiện riêng của vòng đời.

Các thời điểm nên được lưu dưới dạng thời điểm tuyệt đối và được hiển thị theo múi giờ của người vận hành. Đồng hồ trình duyệt không phải nguồn xác định thời gian quyết định. Cần thống nhất nguồn thời gian và ngữ nghĩa timestamp giữa các thành phần.

Một job có thể ghi nhận trạng thái hết hạn muộn hơn thời hạn thực tế. Trong trường hợp đó, bản ghi cần giữ hạn gốc và thời điểm job phát hiện; không viết lại lịch sử như thể quyền chỉ hết hạn lúc job chạy.

Để giải thích chính sách đã áp dụng, chỉ lưu một tên như `default-policy` thường không đủ. Cần phiên bản ổn định và khả năng tra cứu nội dung hoặc cấu hình có liên quan theo chính sách lưu trữ. Một digest của chính sách chỉ có ích cho việc đối chiếu nếu có dữ liệu tham chiếu phù hợp; nó không tự mô tả các điều kiện đã đánh giá.

Khi tái hiện quyết định, dùng bộ dữ liệu và phiên bản chính sách tại thời điểm đó để giải thích lịch sử. Việc chạy chính sách hiện tại trên dữ liệu hiện tại có thể là một phân tích bổ sung, nhưng không được trình bày như bằng chứng rằng quyết định cũ đã đánh giá những điều kiện mới.

Nếu dữ liệu đã được xóa theo chính sách lưu trữ, báo rõ giới hạn khả năng tái dựng. Không khẳng định đã tái hiện đầy đủ chỉ từ một mã kết quả và một số tham chiếu không còn truy cập được.

## 10. Nhiều người duyệt và tổng hợp điều kiện

Khi chính sách yêu cầu hai người duyệt, lưu từng quyết định riêng cùng định danh người duyệt, phiên bản hồ sơ và thời hạn của quyết định. Sau đó lưu kết quả tổng hợp tham chiếu chính xác những quyết định đã được dùng để đáp ứng chính sách.

Ví dụ:

```text
decision-A: admin-A, requestVersion=3, APPROVED_FOR_SCOPE
decision-B: admin-B, requestVersion=3, APPROVED_FOR_SCOPE
approval-set-C: uses [decision-A, decision-B], policy=demo-v4
grant-D: issued from approval-set-C, scope=MFA_REENROLLMENT
```

Kết quả tổng hợp cần cho biết các điều kiện phân tách nhiệm vụ đã được kiểm tra, thay vì chỉ lưu `approvalCount = 2`. Một người gửi lại hai lần không được trở thành hai người duyệt độc lập.

Nếu một phiếu đã hết hạn, bị thu hồi hoặc gắn với phiên bản yêu cầu khác, dấu vết cần thể hiện vì sao phiếu đó không được dùng trong tập phê duyệt hiện tại. Giữ lịch sử phiếu cũ không đồng nghĩa nó vẫn còn hiệu lực.

Việc đủ số người duyệt cũng không tự chứng minh bộ bằng chứng là đúng. Nhật ký cho thấy ai chịu trách nhiệm và căn cứ họ đã xem; tính phù hợp của bằng chứng vẫn phải được bảo đảm bởi quy trình thẩm định.

## 11. Thu hồi, sửa sai và tính toàn vẹn của lịch sử

Không nên sửa trực tiếp một bản ghi quyết định cũ từ `APPROVED` thành `REJECTED` rồi xóa mọi dấu vết trước đó. Cách đó làm mất khả năng biết quyền đã từng được cấp dựa trên quyết định nào.

Thay vào đó, ghi một sự kiện hoặc bản ghi mới thể hiện việc thu hồi, thay thế hoặc đính chính, tham chiếu quyết định cũ và nêu người thực hiện, lý do, thời điểm. Một quyết định mới không làm cho quyết định trước chưa từng tồn tại.

```text
decision-19: phê duyệt đăng ký lại MFA
revocation-20: thu hồi decision-19 do bằng chứng không còn được chấp nhận
grant-revocation-21: vô hiệu hóa quyền khôi phục đã cấp từ decision-19
```

Ba bản ghi mô tả ba sự kiện liên quan. Việc thu hồi quyết định không tự chứng minh quyền phát sinh đã bị vô hiệu hóa; cần ghi nhận kết quả của thao tác đó riêng.

Để giảm nguy cơ chỉnh sửa lịch sử, có thể kết hợp quyền ghi chỉ thêm, phân tách vai trò quản trị, bản sao ở vùng bảo vệ độc lập và cơ chế phát hiện thay đổi. Những biện pháp này cần được đánh giá theo mô hình đe dọa thực tế.

Chuỗi băm hoặc chữ ký có thể hỗ trợ phát hiện thay đổi khi được thiết kế và quản lý khóa phù hợp. Chúng không tự ngăn việc xóa cả phần cuối lịch sử hoặc viết lại toàn bộ chuỗi nếu kẻ tấn công kiểm soát được nguồn và mốc đối chiếu. Cần có mốc kiểm chứng hoặc bản sao độc lập nếu muốn phát hiện những tình huống đó.

Tính toàn vẹn cũng không chứng minh nội dung ban đầu là đúng. Một người duyệt có thể ghi một lý do sai vào một kho không cho sửa; vì vậy vẫn cần kiểm soát nguồn dữ liệu và trách nhiệm của người ra quyết định.

## 12. Dữ liệu tối thiểu và kiểm soát truy cập

Nhật ký khôi phục có thể tiết lộ tài khoản nào đang gặp khó khăn, yếu tố nào bị mất, ai có quyền duyệt và cách tổ chức xử lý sự cố. Ngay cả khi không chứa token, nó vẫn là dữ liệu cần được bảo vệ.

Các nguyên tắc thực hành:

- Ghi định danh và tham chiếu cần thiết, hạn chế lặp lại email, số điện thoại và dữ liệu giấy tờ.
- Không lưu mật khẩu, OTP, recovery code, khóa riêng passkey, cookie hoặc token khôi phục thô.
- Không mặc định băm một bí mật ngắn là đủ để lưu nó an toàn; nếu không cần bí mật trong nhật ký, hãy bỏ nó khỏi nhật ký.
- Tách quyền xem quyết định với quyền đọc bằng chứng gốc, vì không phải mọi người xem báo cáo đều cần xem tài liệu nhạy cảm.
- Ghi nhận truy cập và xuất dữ liệu kiểm toán theo mức độ nhạy cảm phù hợp.
- Quy định thời gian lưu riêng cho sự kiện, quyết định, kết quả xác minh và tài liệu gốc.

Nếu dùng định danh thay thế để giảm dữ liệu cá nhân trực tiếp, vẫn cần bảo vệ bảng ánh xạ và xem xét khả năng liên kết giữa các hệ thống. Định danh khó đọc không tự làm dữ liệu trở thành vô danh.

Chính sách chỉ thêm phục vụ bảo vệ lịch sử không có nghĩa giữ mọi dữ liệu vô thời hạn. Việc lưu trữ, xóa hoặc hạn chế truy cập khi đến hạn cần được thiết kế có kiểm soát, đồng thời không âm thầm diễn giải dữ liệu đã bị xóa thành “chưa từng có sự kiện”.

## 13. Dựng lại một chuỗi khôi phục từ nhật ký

Giả sử người dùng khiếu nại về việc MFA bị thay đổi. Một cuộc rà soát có thể đi theo chuỗi liên kết sau:

```text
recoveryRequestId
    → các phiên bản yêu cầu
    → bộ bằng chứng và kết quả xác minh được tham chiếu
    → từng decisionId
    → tập phê duyệt đã được chấp nhận
    → recoveryGrantId
    → operation tiêu thụ quyền
    → thay đổi yếu tố xác thực
    → kết quả xử lý phiên và thông báo bảo mật
```

Với mỗi liên kết, kiểm tra định danh tài khoản và tenant có nhất quán không, phiên bản có phù hợp không và hành động thực tế có nằm trong phạm vi cho phép không. Không suy luận hai bản ghi liên quan chỉ vì chúng có timestamp gần nhau.

Ví dụ trình tự minh họa:

| Thời điểm | Sự kiện | Câu hỏi cần đối chiếu |
|---|---|---|
| 10:00 | Tạo yêu cầu phiên bản 1 | Ai gửi và hành động đề nghị là gì? |
| 10:08 | Bổ sung bằng chứng, tạo phiên bản 2 | Kết quả xác minh gắn với phiên bản nào? |
| 10:12 | Người duyệt A chấp thuận | Có thẩm quyền và đúng phạm vi không? |
| 10:16 | Người duyệt B chấp thuận | Cùng phiên bản và đủ độc lập không? |
| 10:17 | Cấp quyền đăng ký lại MFA | Tham chiếu đúng tập quyết định còn hiệu lực không? |
| 10:19 | Quyền được dùng | Có đúng một operation và đúng hành động không? |
| 10:20 | Xử lý phiên cũ | Kết quả nào đã thành công, kết quả nào còn chờ? |

Nếu thiếu một sự kiện ở kho tập trung, cần đối chiếu nguồn quyết định, operation và trạng thái outbox trong phạm vi được phép trước khi kết luận rằng thao tác chưa xảy ra. Sự vắng mặt trên một hệ thống đang đồng bộ trễ không phải bằng chứng đầy đủ về sự vắng mặt của hành động.

Hoạt động phân tích lịch sử phải là đọc dữ liệu hoặc mô phỏng không gây tác dụng phụ. Không gọi lại endpoint cấp quyền, đăng ký MFA hoặc thu hồi phiên chỉ để “tái hiện” một quyết định cũ.

## 14. Theo dõi chất lượng dấu vết và phát hiện bất thường

Một số chỉ số vận hành hữu ích:

- Quyết định thiếu tham chiếu chính sách, bằng chứng hoặc danh tính người duyệt.
- Quyền khôi phục không tìm được tập quyết định nguồn phù hợp.
- Quyết định được sử dụng ngoài phạm vi, sau khi thu hồi hoặc trên phiên bản yêu cầu khác.
- Số lần retry và sự kiện trùng, đặc biệt các trường hợp cùng ID nhưng khác nội dung.
- Độ trễ phát sự kiện, số lượng outbox tồn đọng và lỗi ghi nhận.
- Mẫu phê duyệt tập trung bất thường theo người duyệt, tenant hoặc loại hành động.

Một tỷ lệ chấp thuận cao hoặc thời gian duyệt ngắn không tự chứng minh hành vi sai. Các chỉ số là tín hiệu để điều tra theo bối cảnh, không phải kết luận tự động về người dùng hay nhân viên.

Không tối ưu quy trình chỉ theo tốc độ duyệt hoặc tỷ lệ chấp thuận. Nếu mục tiêu vận hành khiến người duyệt bỏ qua lý do, phiên bản bằng chứng hoặc bước xác minh bắt buộc, dấu vết đầy đủ về mặt số lượng vẫn có thể phản ánh một quy trình không an toàn.

## 15. Những tình huống thiết kế cần được làm rõ

Bảng sau mô tả hành vi mong muốn để hiểu cơ chế, không phải báo cáo đã chạy kiểm thử hệ thống:

| Tình huống | Hành vi cần có |
|---|---|
| Transaction lưu quyết định thất bại | Không công bố phê duyệt thành công hoặc cấp quyền dựa trên quyết định chưa được lưu |
| Commit thành công nhưng phản hồi bị mất | Tra cứu operation theo định danh retry, không tạo thêm phiếu |
| Bộ chuyển tiếp sự kiện giao lại | Kho đích nhận diện cùng sự kiện và không nhân đôi hành vi nghiệp vụ |
| Cùng `eventId` nhưng payload khác | Ghi nhận bất nhất và xử lý điều tra, không tự ghi đè |
| Hai người duyệt ở hai phiên bản yêu cầu | Không coi đó là tập duyệt hợp lệ cho phiên bản hiện tại |
| Quản trị viên đổi vai trò sau khi duyệt | Có dữ liệu giải thích thẩm quyền lúc duyệt và kiểm tra hiệu lực theo chính sách khi sử dụng |
| Quyết định bị thu hồi sau khi đã cấp quyền | Giữ lịch sử, theo dõi riêng kết quả thu hồi quyền phát sinh |
| Sự kiện đến không đúng thứ tự | Dựng lại bằng quan hệ và phiên bản, không chỉ theo thời điểm nhận |
| Tài liệu gốc đã hết thời gian lưu | Nêu rõ dữ liệu còn lại và giới hạn giải thích |
| Token hoặc OTP xuất hiện trong log | Xử lý sự cố dữ liệu nhạy cảm và sửa đường ghi nhận theo quy trình phù hợp |

Những lỗi cốt lõi cần tránh là chỉ lưu kết quả cuối, nhầm tài khoản chịu tác động với người duyệt, dùng trạng thái hiện tại để suy đoán lịch sử, và coi tính toàn vẹn của log là bằng chứng rằng quyết định ban đầu chắc chắn đúng.

Một dấu vết phê duyệt tốt nối được căn cứ, thẩm quyền, chính sách, phạm vi và kết quả sử dụng quyền. Nó giúp giải thích các hành động khôi phục mật khẩu, MFA hoặc passkey mà không biến nhật ký thành kho bí mật, đồng thời cho phép phát hiện nơi quy trình đã bị thay đổi, bỏ qua hoặc thực thi sai.
