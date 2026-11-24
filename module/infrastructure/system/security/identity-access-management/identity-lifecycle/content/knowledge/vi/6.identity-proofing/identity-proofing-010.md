# Rà soát proofing trong vòng đời danh tính IAM

> **Chương: Identity proofing.** Rà soát proofing là hoạt động xem xét lại **độ tin cậy của việc xác minh danh tính** và sự liên kết giữa danh tính đã xác minh với người đang sở hữu hoặc sử dụng tài khoản. Mục đích là phát hiện bằng chứng không còn phù hợp, liên kết sai người, gian lận, dữ liệu mâu thuẫn hay những thay đổi làm mức bảo đảm danh tính không còn đáp ứng yêu cầu. Trong IAM theo **Joiner–Mover–Leaver (JML)**, việc rà soát cần dựa trên rủi ro, sự kiện vòng đời và bằng chứng kiểm toán.

## Mục tiêu học tập

Sau khi học xong, bạn có thể:

1. Giải thích **identity proofing review** và phân biệt nó với xác thực đăng nhập, rà soát quyền truy cập, kiểm tra nhân sự và tái xác minh danh tính (re-proofing).
2. Nhận biết **khi nào** cần rà soát: theo lịch, sự kiện JML, sự cố bảo mật, tranh chấp danh tính, khôi phục tài khoản hoặc yêu cầu quyền nhạy cảm.
3. Xây dựng quy trình rà soát bằng chứng, tính nhất quán hồ sơ, chất lượng liên kết tài khoản và mức bảo đảm cần thiết.
4. Quyết định khi nào chỉ cần đối chiếu nguồn, khi nào cần làm rõ, khi nào phải thực hiện re-proofing với biện pháp chống giả mạo và giám sát con người.
5. Thiết kế trạng thái, nhật ký, giới hạn quyền, bảo vệ dữ liệu cá nhân và xử lý ngoại lệ trong một workflow IAM có IdP, SSO, SCIM, RBAC/ABAC.

## 1. Rà soát proofing là gì?

**Identity proofing** là quá trình thu thập và kiểm tra những bằng chứng cần thiết để thiết lập rằng một danh tính khai báo thực sự gắn với một con người cụ thể trong bối cảnh được tổ chức chấp nhận. Tùy chính sách, quy trình có thể gồm kiểm tra thuộc tính từ nguồn đáng tin cậy, xác minh tính hợp lệ của bằng chứng và **binding** — ràng buộc người tham gia quy trình với danh tính đã xác minh.

**Rà soát proofing (proofing review)** là hoạt động đánh giá lại kết quả hoặc cơ sở tin cậy của quy trình đó, chẳng hạn:

- Hồ sơ có được xác minh bằng đúng quy trình và mức bảo đảm theo chính sách tại thời điểm cấp tài khoản không?
- Bằng chứng hoặc xác nhận nguồn còn phù hợp với mục đích hiện tại không?
- Mã nhân sự, danh tính IAM, User tại IdP và tài khoản ứng dụng có đang liên kết với đúng **một người được phép** không?
- Có sự kiện mới làm giảm độ tin cậy, ví dụ hồ sơ trùng, cảnh báo gian lận, thay đổi giấy tờ/thuộc tính định danh quan trọng hoặc phục hồi tài khoản bất thường không?
- Có cần kiểm tra lại một phần, re-proofing toàn bộ, chặn một quyền nhạy cảm hay chuyển điều tra thủ công không?

Rà soát có thể kết thúc bằng kết quả **giữ nguyên mức tin cậy**, **cập nhật bằng chứng và thuộc tính**, **đề nghị tái xác minh**, **áp dụng hạn chế truy cập có tỷ lệ phù hợp** hoặc **chuyển xử lý rủi ro**. Không nên mặc định mọi lần rà soát đều yêu cầu người dùng nộp lại giấy tờ.

### Phân biệt với các công việc IAM khác

| Hoạt động | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Identity proofing ban đầu** | Người xin danh tính có đúng là người được khai báo không? | Kiểm tra và đối chiếu hồ sơ người mới gia nhập. |
| **Proofing review** | Cơ sở tin cậy của danh tính đã cấp có còn đầy đủ và phù hợp không? | Đối chiếu lại liên kết HR–IAM sau khi thấy tài khoản trùng. |
| **Re-proofing** | Có cần thực hiện lại bước xác minh danh tính để thiết lập độ tin cậy không? | Bắt đầu quy trình xác minh lại khi nghi ngờ người đang giữ tài khoản không phải chủ sở hữu hợp lệ. |
| **Authentication** | Người thực hiện phiên đăng nhập có chứng minh được quyền sở hữu authenticator không? | Đăng nhập qua IdP bằng passkey/MFA. |
| **Access review / recertification** | Người này có còn cần vai trò và quyền đã cấp không? | Quản lý xác nhận lại quyền vào ứng dụng kế toán. |
| **Employment / eligibility verification** | Người này còn quan hệ công việc hoặc hợp đồng hợp lệ không? | HR xác nhận hợp đồng vẫn có hiệu lực. |
| **Account recovery** | Làm sao khôi phục quyền kiểm soát tài khoản cho chủ sở hữu hợp lệ? | Khôi phục MFA bị mất và xác minh lại khi rủi ro cao. |

Các hoạt động này có thể kích hoạt lẫn nhau, nhưng **mục đích và bằng chứng khác nhau**. Ví dụ, một người được xác minh danh tính rất chắc chắn vẫn có thể đang giữ quyền quản trị không cần thiết; proofing tốt không thay thế access review. Ngược lại, cấp lại mật khẩu thành công không tự chứng minh quá trình proofing ban đầu đạt mức tin cậy cần thiết.

## 2. Rà soát những gì trong một hồ sơ proofing?

Đối tượng rà soát nên là **bằng chứng và kết quả kiểm soát** liên quan đến việc thiết lập và duy trì danh tính, thay vì chỉ nhìn tên, email hoặc cờ `verified=true`.

| Nhóm cần xem | Câu hỏi kiểm tra | Ví dụ phát hiện |
| --- | --- | --- |
| **Nguồn và định danh** | Nguồn nào có thẩm quyền đối với người này? Mã định danh có ổn định, đúng namespace và tenant? | Hai hồ sơ IAM cùng liên kết một mã nhân sự do lỗi đồng bộ. |
| **Bằng chứng proofing** | Có hồ sơ về phương thức, kết quả, thời điểm và người/hệ thống thực hiện không? | Tài khoản đặc quyền không có bằng chứng từng hoàn tất quy trình xác minh yêu cầu. |
| **Tính hợp lệ** | Bằng chứng có đủ độ tin cậy và còn phù hợp với loại danh tính/tác vụ đang xin? | Hồ sơ đối tác được xác nhận bởi sponsor đã hết hợp đồng. |
| **Binding** | Người tham gia xác minh có được liên kết đúng với danh tính nguồn và tài khoản hay không? | Liên kết thủ công một User ở IdP vào nhầm hồ sơ HR. |
| **Tính nhất quán** | Dữ liệu giữa HR, IAM, IdP và ứng dụng có mâu thuẫn quan trọng không? | Mã nhân viên trùng, ngày bắt đầu không khớp, email bị tái sử dụng. |
| **Mức bảo đảm** | Kết quả proofing có đáp ứng mức tin cậy theo rủi ro của tác vụ? | Tài khoản được tạo qua lời mời email nhưng xin quyền xử lý dữ liệu rất nhạy cảm. |
| **Sự kiện rủi ro** | Có cảnh báo giả mạo, khiếu nại danh tính, gian lận hoặc khôi phục tài khoản đáng ngờ không? | Người dùng báo không hề yêu cầu tạo tài khoản mang tên mình. |
| **Bằng chứng kiểm toán** | Có thể truy vết ai xét duyệt, kết luận gì, ngoại lệ nào, hành động nào đã thực thi? | Hồ sơ đánh dấu đã kiểm tra nhưng không có dấu thời gian hoặc người chịu trách nhiệm. |

Trong một số khung đánh giá, **Identity Assurance Level (IAL)** được dùng để chỉ mức bảo đảm danh tính dựa trên quy trình proofing. Không nên tự gán IAL cao chỉ vì người dùng bật MFA hoặc vì tài khoản nằm trong IdP: **mức bảo đảm proofing** và **mức bảo đảm xác thực** là hai khía cạnh khác nhau. Khi dùng một mức IAL hoặc khung bảo đảm cụ thể, cần xác định yêu cầu và bằng chứng theo đúng chính sách, tiêu chuẩn và quy trình mà tổ chức áp dụng.

### Ba lớp độ tin cậy cần nối với nhau

~~~mermaid
flowchart LR
    S["Nguồn định danh có thẩm quyền<br/>HR / đối tác / quy trình đăng ký"] --> P["Kết quả identity proofing<br/>Bằng chứng, độ tin cậy, thời điểm"]
    P --> I["Identity trong IAM<br/>ID ổn định và trạng thái"]
    I --> A["Tài khoản tại IdP / ứng dụng"]
    A --> R["Phiên, nhóm, vai trò và quyền"]
    P --> V["Rà soát proofing theo rủi ro"]
    I --> V
    A --> V
    V --> C["Kết luận và hành động có kiểm soát"]
~~~

Một chuỗi liên kết sai ở bất kỳ bước nào có thể khiến quyền gắn vào **nhầm người**. Việc User đăng nhập được chỉ cho thấy cơ chế xác thực chấp nhận người đang kiểm soát authenticator; chưa đủ chứng minh hồ sơ HR và bằng chứng danh tính ban đầu đã được nối đúng.

## 3. Khi nào phải kích hoạt proofing review?

Nên kết hợp **rà soát định kỳ theo rủi ro** với **rà soát do sự kiện**. Tần suất, ngưỡng kích hoạt và mức kiểm tra phải do chính sách của tổ chức quy định; không có một chu kỳ cố định phù hợp cho mọi danh tính.

| Tác nhân kích hoạt | Điều cần đánh giá | Hành động có thể phù hợp |
| --- | --- | --- |
| **Đến kỳ rà soát** | Hồ sơ còn đủ bằng chứng, đúng người và đáp ứng yêu cầu hiện tại? | Đối chiếu hồ sơ, kiểm tra rủi ro; tái xác minh nếu thiếu hoặc giảm độ tin cậy. |
| **Joiner / tái tuyển dụng** | Đã xác minh đúng người chưa; hồ sơ cũ có liên kết hợp lệ với người quay lại không? | Đối sánh nguồn, làm proofing theo chính sách; không tự hồi sinh toàn bộ quyền cũ. |
| **Mover** | Thay đổi vai trò/nguồn có làm phát sinh yêu cầu tin cậy danh tính cao hơn hoặc mâu thuẫn định danh không? | Đánh giá mức bảo đảm; re-proofing khi cần, đồng thời access review riêng. |
| **Leaver** | Có tài khoản, liên kết danh tính hoặc bằng chứng cần lưu để kiểm toán và chống tái sử dụng nhầm? | Thu hồi truy cập; giữ hồ sơ đúng hạn lưu giữ, không trì hoãn việc khóa quyền. |
| **Yêu cầu quyền nhạy cảm** | Proofing hiện tại có đủ tin cậy cho thao tác/dữ liệu dự kiến? | Kiểm tra trước khi cấp quyền; yêu cầu xác minh bổ sung khi chính sách đòi hỏi. |
| **Khôi phục tài khoản / MFA** | Có dấu hiệu kẻ khác đang tìm cách chiếm danh tính? | Tăng kiểm soát recovery; xác minh lại người sở hữu khi rủi ro cao. |
| **Cảnh báo gian lận hoặc hồ sơ trùng** | Danh tính bị giả mạo, liên kết nhầm, nguồn bị xâm phạm hoặc dữ liệu sai? | Mở case điều tra, hạn chế hoạt động rủi ro, đối chiếu bằng chứng và xử lý thủ công. |
| **Thay đổi nguồn dữ liệu** | HR chuyển hệ thống, di trú IdP hoặc thay đổi mapping có làm mất tính toàn vẹn danh tính? | Đối soát định danh và tập tài khoản theo manifest migration. |
| **Khiếu nại danh tính / quyền riêng tư** | Người liên quan phủ nhận hoặc yêu cầu sửa thông tin định danh? | Xác minh yêu cầu, điều tra có kiểm soát và sửa nguồn dữ liệu hợp lệ. |

### Không đồng nhất Mover với re-proofing bắt buộc

Một nhân viên chuyển từ hỗ trợ sang kế toán cần **rà soát và thay đổi quyền** theo RBAC/ABAC, nhưng nếu định danh vẫn chắc chắn và loại truy cập mới không đòi mức tin cậy cao hơn, có thể **không cần** xác minh lại giấy tờ. Ngược lại, khi một tài khoản được đề nghị trở thành quản trị viên hệ thống nhạy cảm mà hồ sơ chỉ có bước xác minh tối thiểu, quy trình có thể phải kiểm tra lại mức bảo đảm danh tính trước khi cấp quyền.

Sự kiện Mover là một **điểm đánh giá rủi ro**, không phải lệnh tự động thu thập lại toàn bộ dữ liệu cá nhân.

## 4. Quy trình rà soát proofing theo rủi ro

Quy trình tham khảo gồm bảy bước có thể thực hiện bằng workflow IAM/IGA và đội bảo mật:

1. **Khởi tạo review case.** Ghi nhận danh tính, sự kiện kích hoạt, phạm vi, hệ thống liên quan, độ nhạy tác vụ và mức ưu tiên. Dùng ID bất biến; không mở case chỉ dựa vào tên hiển thị.
2. **Xác minh nguồn và quyền truy cập dữ liệu.** Xác định HR, hệ thống nhà thầu hoặc nguồn đăng ký được ủy quyền; kiểm tra reviewer có quyền hợp lệ để xem bằng chứng hay không.
3. **Thu thập dữ liệu tối thiểu.** Truy vấn metadata proofing trước: loại phương thức, thời điểm, kết luận, nguồn, mức bảo đảm được ghi nhận, phiên bản chính sách, liên kết tài khoản. Chỉ mở bằng chứng nhạy cảm khi thật sự cần.
4. **Đối chiếu và đánh giá rủi ro.** Kiểm tra tính toàn vẹn định danh, sự trùng lặp, sự kiện mới, nguồn bất thường, tuổi của hồ sơ, dấu hiệu gian lận và yêu cầu bảo đảm hiện tại.
5. **Chọn biện pháp.** Có thể chấp nhận nguyên trạng, yêu cầu xác minh thuộc tính đơn lẻ, yêu cầu re-proofing, chuyển đánh giá thủ công, tạm chặn cấp quyền mới hoặc hạn chế đường truy cập có nguy cơ theo chính sách.
6. **Thực thi và xác minh.** Cập nhật trạng thái tin cậy, chứng cứ và các luồng liên quan; nếu cần hạn chế truy cập thì áp dụng ở IdP/ứng dụng, thu hồi phiên khi phù hợp và đọc lại kết quả.
7. **Đóng case và đặt lịch xem xét lại.** Lưu quyết định, lý do, người xử lý, kết quả từng hệ thống, hạn ngoại lệ và thời điểm tái đánh giá; xử lý dữ liệu bằng chứng theo lịch lưu giữ.

~~~mermaid
flowchart TD
    T["Sự kiện hoặc kỳ rà soát"] --> K["Tạo review case<br/>Xác định scope, rủi ro và owner"]
    K --> E["Đối chiếu nguồn, metadata proofing<br/>và liên kết tài khoản"]
    E --> D{"Bằng chứng và mức tin cậy<br/>còn đáp ứng chính sách?"}
    D -->|Có| P["Xác nhận kết quả<br/>ghi bằng chứng kiểm toán"]
    D -->|Không chắc| M["Yêu cầu làm rõ / human review"]
    D -->|Không| R["Re-proofing hoặc xử lý gian lận<br/>theo mức rủi ro"]
    M --> Q{"Đã giải quyết?"}
    Q -->|Có| P
    Q -->|Chưa| R
    R --> C["Kiểm soát quyền/phiên khi cần<br/>và xác minh hệ thống đích"]
    C --> H["Lưu kết luận, ngoại lệ có hạn,<br/>kế hoạch theo dõi"]
    P --> H
~~~

### Tại sao cần tách người đánh giá và người được đánh giá?

Nếu người dùng tự xác nhận danh tính, tự phê duyệt bằng chứng và tự cấp đặc quyền cho chính mình, hệ thống mất khả năng kiểm soát gian lận. Với trường hợp nhạy cảm, nên có **separation of duties (SoD)** giữa người yêu cầu, người xác minh, người phê duyệt ngoại lệ và người cấp quyền. Hành động của nhân viên xử lý review cũng phải được ghi log, gồm mọi lần mở hoặc xuất dữ liệu chứng minh danh tính.

## 5. Khi nào cần re-proofing và xác minh lại bằng cách nào?

**Re-proofing** là thực hiện lại một phần hoặc toàn bộ hoạt động xác minh danh tính theo chính sách hiện hành để nâng hoặc khôi phục độ tin cậy. Nó có thể cần thiết khi:

- Hồ sơ ban đầu thiếu bước xác minh mà quyền/tác vụ mới yêu cầu.
- Bằng chứng xuất hiện dấu hiệu giả mạo, không khớp với nguồn có thẩm quyền hoặc bị khiếu nại.
- Có dấu hiệu chiếm đoạt tài khoản và recovery thông thường không đủ thiết lập người sở hữu.
- Một phép gộp/trùng tài khoản hoặc di trú hệ thống làm mất độ tin cậy của ánh xạ người–tài khoản.
- Kết quả proofing trước đây không thể chứng minh hoặc không còn phù hợp với chính sách đang áp dụng cho tác vụ rủi ro cao.

Tùy rủi ro, có thể:

| Mức xử lý | Khi nào phù hợp | Ví dụ |
| --- | --- | --- |
| **Đối chiếu dữ liệu** | Có thay đổi hành chính nhưng danh tính cơ bản vẫn đáng tin cậy. | So sánh mã HR và trạng thái hợp đồng sau Mover. |
| **Xác minh lại một thuộc tính** | Một dữ liệu có ảnh hưởng đến quyền bị sai hoặc chưa rõ. | Xác nhận lại sponsor và ngày kết thúc hợp đồng. |
| **Rà soát thủ công** | Bằng chứng mâu thuẫn, nghi ngờ giả mạo hoặc nguồn cấp không đáng tin. | Hai hồ sơ cùng nhận một tài khoản đích. |
| **Re-proofing đầy đủ** | Không còn cơ sở tin cậy để liên kết danh tính với người dùng hoặc cần mức bảo đảm cao hơn. | Quy trình onboarding cũ không xác định được ai thực sự hoàn tất xác minh. |
| **Điều tra gian lận / xử lý sự cố** | Có dấu hiệu chủ đích đánh cắp, mua bán hoặc giả mạo danh tính. | Có người phủ nhận từng đăng ký tài khoản được cấp dưới tên mình. |

**Không có một bộ giấy tờ hay phương thức kiểm tra phù hợp với mọi người.** Việc thu thập bằng chứng phải tương xứng rủi ro, yêu cầu pháp luật và chính sách dữ liệu. Với xác minh từ xa, hệ thống cần xét nguy cơ giả mạo tài liệu, danh tính tổng hợp, video giả và hành vi thao túng quy trình; biện pháp đối phó có thể gồm đối chiếu nguồn đáng tin cậy, kiểm tra bằng chứng và sự tham gia của người xử lý được đào tạo. Không nên hứa rằng một dấu hiệu sinh trắc học hoặc phép so khớp tự động sẽ loại bỏ hoàn toàn gian lận.

### Người dùng không thể hoàn tất bước xác minh tiêu chuẩn

Cần cung cấp đường xử lý thay thế có kiểm soát cho người không thể dùng phương thức tự động, không có đủ loại giấy tờ theo mặc định hoặc gặp rào cản thiết bị, ngôn ngữ hay khả năng tiếp cận. Luồng thay thế vẫn phải đạt yêu cầu bảo đảm phù hợp, có người xử lý, bằng chứng và giới hạn ngoại lệ; không nên mặc định xem khác biệt dữ liệu cá nhân là dấu hiệu gian lận.

## 6. Trạng thái review và quy tắc quyết định

Một hệ thống IAM có thể dùng state machine nội bộ như sau (tên trạng thái chỉ mang tính minh họa):

| Trạng thái | Ý nghĩa | Hành động tiếp theo |
| --- | --- | --- |
| `NOT_DUE` | Chưa đến kỳ và không có trigger đang mở. | Tiếp tục theo dõi sự kiện rủi ro. |
| `REVIEW_REQUIRED` | Có trigger hoặc kỳ hạn cần đánh giá. | Gán người phụ trách, khóa phạm vi case. |
| `UNDER_REVIEW` | Đang đối chiếu bằng chứng và nguồn. | Thu thập tối thiểu, ghi log thao tác. |
| `NEEDS_CLARIFICATION` | Có dữ liệu chưa rõ hoặc nguồn mâu thuẫn. | Yêu cầu giải trình, chặn tự động kết luận đạt. |
| `REPROOFING_REQUIRED` | Cần xác minh danh tính lại theo chính sách. | Mở quy trình re-proofing phù hợp. |
| `VERIFIED` | Kết quả review đạt yêu cầu tại thời điểm đánh giá. | Lưu bằng chứng, đặt kỳ/sự kiện tái đánh giá. |
| `REJECTED` | Không đạt sau các bước kiểm tra cần thiết. | Áp dụng kiểm soát rủi ro, thông báo và cơ chế xử lý theo chính sách. |
| `EXCEPTION_APPROVED` | Có ngoại lệ được cấp bởi người có thẩm quyền. | Giới hạn phạm vi, thời hạn, người chịu trách nhiệm và giám sát. |

Trạng thái proofing review **không phải** trạng thái đăng nhập của IdP hay trạng thái employment ở HR. Một User có thể đang `UNDER_REVIEW` nhưng vẫn cần một phần quyền công việc để xử lý case; ngược lại, tài khoản đã `VERIFIED` vẫn phải bị thu hồi khi HR phát Leaver hợp lệ.

### Chính sách quyết định minh họa

Pseudocode sau chỉ thể hiện cách liên kết chính sách. Nó không phải chính sách sẵn dùng của IdP/SCIM:

~~~text
KHI có yêu cầu cấp đặc quyền:
    KIỂM TRA identity.active và employmentEligibility
    KIỂM TRA trạng thái proofing và mức bảo đảm yêu cầu

    NẾU proofing đang có nghi vấn nghiêm trọng:
        TỪ CHỐI tự động cấp đặc quyền mới
        MỞ review case và thông báo người có thẩm quyền
    NGƯỢC LẠI NẾU mức bảo đảm chưa đáp ứng:
        YÊU CẦU re-proofing phù hợp trước khi xét cấp
    NGƯỢC LẠI:
        TIẾP TỤC kiểm tra RBAC/ABAC, phê duyệt, SoD, thời hạn
        CẤP theo nguyên tắc quyền tối thiểu và đối soát đích

KHI có Leaver hợp lệ:
    THU HỒI quyền theo sự kiện Leaver, không chờ review proofing
~~~

Trường hợp nghi ngờ chiếm đoạt tài khoản đang hoạt động đòi hỏi đánh giá ứng phó sự cố riêng, có thể cần vô hiệu hóa hoặc rút ngắn phiên ngay. Mức kiểm soát phải phù hợp rủi ro và có chủ sở hữu, tránh cả việc bỏ mặc đường truy cập nguy hiểm lẫn khóa tùy tiện mọi người vì sai khác dữ liệu nhỏ.

## 7. Liên hệ với IdP, SSO, SCIM, RBAC/ABAC và tài khoản dịch vụ

| Thành phần | Vai trò trong quản lý proofing review | Giới hạn cần nhận biết |
| --- | --- | --- |
| **HR/nguồn định danh** | Cung cấp thông tin về quan hệ lao động, mã nguồn, thuộc tính và sự kiện JML. | Hồ sơ việc làm hợp lệ không tự chứng minh tất cả bằng chứng identity proofing. |
| **IAM / IGA** | Tổ chức case review, phê duyệt, bằng chứng, trạng thái và chính sách. | Cờ xác nhận nội bộ phải có nguồn chứng cứ, người chịu trách nhiệm và thời điểm. |
| **IdP** | Gắn danh tính với phương thức xác thực, chính sách đăng nhập và nhóm. | MFA tốt không tự nâng kết quả proofing ban đầu. |
| **SSO (OIDC/SAML)** | Chuyển thông tin xác thực đã được tin cậy tới ứng dụng liên kết. | Ứng dụng không nên tự coi claim tùy ý là chứng minh proofing nếu không có hợp đồng/đảm bảo về nguồn. |
| **SCIM / provisioning** | Tạo, cập nhật, vô hiệu hóa User và nhóm tại đích theo yêu cầu. | SCIM không phải giao thức kiểm tra giấy tờ hoặc đảm bảo người đăng nhập đúng chủ hồ sơ. |
| **RBAC/ABAC** | Giới hạn quyền theo vai trò, thuộc tính, rủi ro và điều kiện. | Trạng thái proofing là một đầu vào chính sách nếu được bảo vệ; không thay kiểm tra tài nguyên, tenant hay thời hạn. |
| **PAM** | Quản lý truy cập đặc quyền có hạn và phê duyệt tăng cường. | Proofing đạt không đồng nghĩa tài khoản đủ điều kiện giữ quyền admin thường trực. |
| **Audit/monitoring** | Phát hiện bất thường, liên kết sự kiện, xác nhận xử lý và lưu vết. | Log không được chứa bản sao giấy tờ, token hay dữ liệu nhạy cảm không cần thiết. |

Một thiết kế hợp lý có thể giữ kết quả review trong hệ thống IAM/IGA, rồi xuất **tín hiệu đáng tin cậy đã được quy ước** cho IdP hoặc policy engine nếu ứng dụng thật sự cần. Tín hiệu phải có tính toàn vẹn, thời hạn hiệu lực và ngữ cảnh sử dụng. Không truyền tự do ảnh giấy tờ hoặc toàn bộ chi tiết xác minh cho mọi ứng dụng chỉ để kiểm tra một điều kiện truy cập.

### Tài khoản dịch vụ và workload

**Identity proofing theo nghĩa xác minh con người không được áp dụng máy móc cho service account.** Với danh tính máy, bài toán tương ứng là xác minh **dịch vụ có thật, ai chịu trách nhiệm, workload chạy ở đâu và nguồn nào có quyền tạo danh tính đó**. Hoạt động rà soát tập trung vào:

- Owner nghiệp vụ và owner kỹ thuật có còn làm việc, được phân công và đủ thẩm quyền không?
- Tài khoản máy có liên kết đúng ứng dụng, môi trường và workload đang tồn tại không?
- Credential, trust policy, mối liên kết federation, chứng chỉ hoặc khóa có còn đúng scope và hạn dùng không?
- Có credential/tài khoản mồ côi do dự án bị dừng hoặc do owner rời tổ chức không?
- Khi thay đổi owner hoặc decommission, đã thu hồi quyền, khóa và phiên cần thiết chưa?

Ví dụ, khi người phát triển một job CI/CD nghỉ việc, không cần buộc “job” nộp giấy tờ tùy thân. Cần xác minh lại **chủ sở hữu dịch vụ**, nguồn cấp danh tính máy, phạm vi quyền và trạng thái credential, rồi thu hồi những quan hệ tin cậy không còn hợp lệ.

## 8. Bảo vệ dữ liệu và chất lượng bằng chứng

Hồ sơ proofing có thể chứa thông tin nhận dạng cá nhân nhạy cảm. Vì vậy, rà soát hiệu quả phải đồng thời bảo đảm **tính toàn vẹn, tính bảo mật và khả năng kiểm toán**.

### Thu thập và lưu giữ tối thiểu

- Ưu tiên lưu **metadata kết quả** (phương thức, thời điểm, đơn vị xác minh, mã case, trạng thái) thay vì bản chụp bằng chứng khi không cần giữ nội dung gốc.
- Chỉ thu thập thông tin cần thiết cho mức bảo đảm theo chính sách; áp dụng giới hạn mục đích sử dụng và lịch lưu giữ.
- Mã hóa dữ liệu khi lưu và truyền, giới hạn người xem, ghi nhận mọi lần truy cập hoặc xuất bằng chứng.
- Khi phải dùng ảnh giấy tờ hoặc sinh trắc học, cần căn cứ và biện pháp xử lý dữ liệu chuyên biệt; không để chúng rò rỉ qua log, ticket, email thông thường hay báo cáo toàn hệ thống.
- Hỗ trợ chỉnh sửa thông tin sai tại nguồn có thẩm quyền và đồng bộ lại, giữ lịch sử thay đổi phù hợp yêu cầu kiểm toán.

### Bằng chứng kỹ thuật và bằng chứng nghiệp vụ

Một case review có thể cần cả:

1. **Bằng chứng kỹ thuật:** kết quả kiểm tra ở dịch vụ proofing, mã tham chiếu, phiên bản quy trình, tính toàn vẹn liên kết tài khoản, kết quả đối soát.
2. **Bằng chứng nghiệp vụ:** nguồn HR, sponsor nhà thầu, phê duyệt ngoại lệ, căn cứ yêu cầu loại quyền, ngày hiệu lực.

Nên ghi **reference đến bằng chứng trong kho được kiểm soát**, không nhúng nội dung gốc vào mọi event. Nếu nguồn gặp sự cố hoặc dữ liệu trùng, lưu lại dấu vết kiểm tra và người xử lý đủ để điều tra nhưng tránh nhân bản dữ liệu cá nhân không cần thiết.

### Ví dụ một record review nội bộ

JSON này là mô hình minh họa phục vụ thiết kế, không phải payload SCIM/OIDC hay schema tiêu chuẩn:

~~~json
{
  "reviewId": "prv-00842",
  "identityId": "iam-user-239",
  "sourcePersonRef": "HR:EMP-2039",
  "trigger": "REHIRE_IDENTITY_LINK_CHECK",
  "riskTier": "ELEVATED",
  "reviewState": "NEEDS_CLARIFICATION",
  "proofingEvidenceRef": "vault://proofing/case-441",
  "lastProofingMethod": "SUPERVISED_VERIFICATION",
  "policyVersion": "id-proofing-v3",
  "reviewOwnerRole": "IDENTITY_REVIEWER",
  "requestedAt": "2026-11-23T09:00:00+07:00",
  "accessDecision": "PRIVILEGE_GRANT_PENDING",
  "correlationId": "corr-445"
}
~~~

Không nên lưu bất kỳ `proofingEvidenceRef` nào dưới dạng URL công khai cho phép xem trực tiếp tài liệu. Giá trị `riskTier` và trạng thái trong ví dụ là quy ước nội bộ, cần có định nghĩa và quy trình xử lý cụ thể nếu triển khai thật.

## 9. Các tình huống điển hình và cách xử lý

### Tình huống A — Nhân viên được tuyển lại sau thời gian dài

**Hoàn cảnh:** Minh từng làm việc tại công ty, nghỉ việc rồi quay lại. HR tạo hồ sơ hợp đồng mới, còn IdP có tài khoản cũ đang bị vô hiệu hóa. Email của Minh trùng với email đã dùng trước đó.

**Rủi ro:** Hệ thống có thể nối nhầm nhân viên mới với tài khoản cũ vì chỉ so email, hoặc bật lại các quyền đặc quyền trước khi kiểm tra tính liên tục danh tính.

**Cách xử lý:** Đối chiếu định danh nguồn theo chính sách tái tuyển dụng, xác minh người quay lại liên quan hợp lệ với hồ sơ trước, xem lại kết quả proofing và thực hiện re-proofing nếu cần. Sau đó cấp lại **quyền theo công việc hiện tại**, không khôi phục nguyên trạng mọi vai trò cũ; xác minh các tài khoản đích và ghi audit.

### Tình huống B — Hai tài khoản dùng cùng một mã nhân sự

**Hoàn cảnh:** Đợt di trú IdP khiến hai User cùng trỏ tới một `employeeId`; một tài khoản có đặc quyền.

**Rủi ro:** Hành vi truy cập có thể bị ghi cho sai người; quy trình Mover hoặc Leaver có thể thu hồi nhầm hoặc bỏ sót quyền.

**Cách xử lý:** Tạm ngừng việc **tự động cấp thêm quyền nhạy cảm** cho các liên kết chưa rõ; mở case, đối chiếu danh tính từ nguồn đáng tin cậy, kiểm tra mapping, lịch sử proofing, những tài khoản có quyền và chủ sở hữu. Khi xử lý, phải đối soát lại toàn bộ tài khoản liên quan và đánh giá quyền còn hiệu lực. Không gộp hồ sơ chỉ dựa vào tên/email.

### Tình huống C — Người dùng mất MFA và yêu cầu recovery

**Hoàn cảnh:** Một nhân viên yêu cầu đặt lại yếu tố MFA qua email. Cùng thời điểm, hệ thống phát hiện đăng nhập từ bối cảnh bất thường.

**Rủi ro:** Người tấn công có thể kiểm soát kênh email và tìm cách chiếm tài khoản qua khôi phục.

**Cách xử lý:** Áp dụng quy trình recovery tương xứng rủi ro, tăng xác minh người sở hữu, giám sát và phê duyệt thủ công khi cần. Kiểm tra nguồn, bằng chứng và kết quả; nếu có chỉ dấu xâm nhập, xử lý sự cố phiên/credential. Sau recovery, không tự gán quyền cao hơn trước.

### Tình huống D — Mover sang vị trí nhạy cảm

**Hoàn cảnh:** Thảo chuyển sang nhóm vận hành tài chính và yêu cầu quyền duyệt thanh toán. Hồ sơ proofing ban đầu chỉ gồm bước xác minh tối thiểu trong onboarding.

**Rủi ro:** Mức tin cậy danh tính có thể thấp hơn yêu cầu của tác vụ nhạy cảm.

**Cách xử lý:** Kiểm tra yêu cầu mức bảo đảm cho quyền mới; nếu chưa đạt, yêu cầu proofing bổ sung trước khi cấp đặc quyền. Đồng thời kiểm tra SoD, RBAC/ABAC, phê duyệt của resource owner và thu hồi quyền vai trò cũ không còn cần thiết.

### Tình huống E — Nhân sự nghỉ việc đang có case proofing chưa đóng

**Hoàn cảnh:** Hồ sơ của An đang chờ rà soát do dữ liệu trùng; HR phát sự kiện Leaver có hiệu lực hôm nay.

**Rủi ro:** Nếu hệ thống chờ case proofing hoàn tất rồi mới khóa tài khoản, An có thể tiếp tục truy cập sau thời điểm rời tổ chức.

**Cách xử lý:** **Thực thi Leaver và thu hồi quyền đúng hiệu lực**, đồng thời giữ case bằng chứng để giải quyết trùng hồ sơ, tài khoản liên kết và lưu trữ theo chính sách. Đánh giá riêng liệu còn User/tài khoản nào cũng phải chịu tác động do ánh xạ sai.

## 10. Kiểm toán và chỉ số vận hành

Một hệ thống review có khả năng kiểm toán cần trả lời:

- **Ai** đã kích hoạt rà soát, dựa trên sự kiện hoặc kỳ hạn nào?
- **Danh tính và tài khoản nào** thuộc phạm vi, nguồn dữ liệu có thẩm quyền là gì?
- **Bằng chứng nào** được xem, loại/phương thức nào, kết luận của ai và phiên bản chính sách nào?
- **Rủi ro nào** khiến case cần làm rõ, re-proofing, hạn chế quyền hoặc điều tra?
- **Ai** chấp thuận ngoại lệ, phạm vi và thời hạn bao lâu, ai chịu trách nhiệm theo dõi?
- **Hệ thống nào** đã được cập nhật, thực sự áp dụng thay đổi ra sao và còn sai lệch nào chưa giải quyết?

Các chỉ số nên được phân tích theo mức rủi ro và loại danh tính:

| Chỉ số | Phát hiện vấn đề gì? | Lưu ý khi đọc |
| --- | --- | --- |
| Tỷ lệ hồ sơ thiếu bằng chứng phù hợp | Lỗ hổng quy trình proofing cũ hoặc migration. | Phân nhóm theo nhiệm vụ và mức bảo đảm cần thiết. |
| Số hồ sơ trùng/liên kết không chắc chắn | Nguy cơ gán tài khoản cho nhầm người. | Ưu tiên hồ sơ có đặc quyền hoặc tài nguyên nhạy cảm. |
| Thời gian giải quyết review case | Tốc độ xử lý rủi ro danh tính. | So sánh theo mức độ nghiêm trọng, không ép case khó đóng sớm. |
| Số case re-proofing đang chờ quá hạn | Rủi ro truy cập chưa được xử lý hoặc chặn nhu cầu hợp lệ. | Cần theo dõi ảnh hưởng người dùng và biện pháp tạm thời. |
| Tỷ lệ ngoại lệ còn hiệu lực sau hạn | Điểm yếu trong thu hồi kiểm soát tạm thời. | Đối soát thực tế và kiểm tra quyền phát sinh. |
| Số tài khoản đích sai ánh xạ sau xử lý | Đánh giá hiệu quả cập nhật IdP, SCIM và connector. | Ghi theo từng hệ thống, tránh chỉ đếm lệnh gửi thành công. |
| Tỷ lệ khiếu nại/kháng nghị thành công | Dấu hiệu quyết định review thiếu chính xác. | Có thể gợi ý cần cải thiện quy trình và khả năng tiếp cận. |

Nên có cơ chế **phản hồi, khiếu nại và sửa sai** khi người dùng bị chặn do thông tin nhầm lẫn. Với kết quả tự động có ảnh hưởng đáng kể, tổ chức cần xem xét kiểm tra con người, giải thích được lý do, lưu dấu quyết định và cách xử lý theo chính sách dữ liệu hiện hành.

## 11. Bài tập tự kiểm tra

**Câu 1.** Một nhân viên vừa đổi phòng ban nhưng hồ sơ định danh không thay đổi, không có dấu hiệu gian lận và vai trò mới không đòi mức bảo đảm cao hơn. Có phải re-proofing toàn bộ không?

*Gợi ý:* Không mặc định. Thực hiện Mover và access review để tính lại quyền; chỉ yêu cầu proofing lại nếu có trigger hoặc yêu cầu bảo đảm cụ thể.

**Câu 2.** Tài khoản đã đăng nhập qua SSO bằng MFA. Có thể suy ra hồ sơ proofing ban đầu đủ tin cậy cho quyền quản trị nhạy cảm không?

*Gợi ý:* Không. Xác thực và proofing giải quyết hai câu hỏi khác nhau; phải xem kết quả/bằng chứng proofing và chính sách cho quyền đó.

**Câu 3.** Một hệ thống phát hiện hai User cùng trỏ đến một mã HR và một User đang giữ quyền cao. Nên hành động ra sao?

*Gợi ý:* Mở case kiểm tra mapping, hạn chế tự động cấp thêm quyền nhạy cảm, đối chiếu nguồn có thẩm quyền, đánh giá phiên và quyền hiện tại, khắc phục liên kết sai và readback ở hệ thống đích.

**Câu 4.** Vì sao không nên gửi ảnh giấy tờ định danh tới tất cả ứng dụng qua provisioning?

*Gợi ý:* Không cần thiết cho phần lớn quyết định truy cập, làm tăng diện lộ dữ liệu nhạy cảm. Nên giữ bằng chứng trong hệ thống kiểm soát và chia sẻ tín hiệu/trạng thái tối thiểu có hợp đồng tin cậy.

**Câu 5.** Trong lúc đang rà soát proofing, HR phát Leaver hợp lệ. Quy trình nào phải được ưu tiên?

*Gợi ý:* Thu hồi truy cập theo Leaver đúng thời điểm hiệu lực; tiếp tục xử lý hồ sơ proofing để bảo đảm tất cả tài khoản liên kết được xác định, điều tra và lưu giữ bằng chứng cần thiết.

**Câu 6.** Với service account dùng cho job sao lưu, có nên thực hiện xác minh giấy tờ của chính tài khoản không?

*Gợi ý:* Không. Cần rà soát danh tính workload, owner, quyền, credential và vòng đời dịch vụ; proofing con người áp dụng khi cần xác minh chủ sở hữu hoặc người đại diện có thẩm quyền.

## Ghi nhớ

- **Rà soát proofing** kiểm tra lại độ tin cậy của danh tính và chất lượng liên kết người–tài khoản; **authentication** kiểm tra phiên đăng nhập, còn **access review** kiểm tra quyền cần thiết.
- Kết hợp **lịch rà soát theo rủi ro** và **trigger theo sự kiện**; không mặc định Mover luôn cần nộp lại giấy tờ hay MFA có thể thay proofing.
- Rà soát cần nguồn có thẩm quyền, metadata/bằng chứng đủ kiểm tra, đánh giá mức bảo đảm, khả năng re-proofing, phê duyệt độc lập, ngoại lệ có hạn và đối soát kết quả.
- **IdP/SSO, SCIM, RBAC/ABAC** hỗ trợ đăng nhập, cấp phát và thực thi quyền; chúng chỉ sử dụng kết quả proofing đúng cách khi có liên kết, nguồn tin cậy và chính sách rõ ràng.
- Trong **Joiner–Mover–Leaver**, phải giữ quyền truy cập phù hợp với trạng thái thật, thu hồi khi hết nhu cầu và kiểm tra quyền tồn dư tại mọi tài khoản đích.
- Bảo vệ dữ liệu cá nhân bằng **thu thập tối thiểu, kiểm soát xem bằng chứng, thời hạn lưu giữ và audit**, kèm phương án xử lý thủ công khi người dùng có căn cứ khiếu nại.
