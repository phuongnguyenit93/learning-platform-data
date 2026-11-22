# Tính toàn vẹn của quyết định nghiệp vụ — Integrity of business decisions

## 1. Mục tiêu bảo vệ là quyết định có hiệu lực trong hệ thống

Một hệ thống bán hàng có thể lưu đúng dữ liệu, xác thực đúng người dùng và vẫn thực hiện một quyết định sai: duyệt hoàn tiền vượt thẩm quyền, chấp nhận mức giá do phía khách sửa, cho người đề nghị tự phê duyệt hoặc thực hiện lại một quyết định đã được sử dụng.

**Tính toàn vẹn của quyết định nghiệp vụ** là việc bảo đảm một quyết định được tạo ra và thực hiện từ dữ liệu đáng tin cậy, theo đúng chính sách, bởi đúng chủ thể có thẩm quyền, trên đúng đối tượng và đúng điều kiện có hiệu lực. Nội dung đã được quyết định không được bị thay thế, diễn giải khác hoặc áp dụng lại ngoài phạm vi cho phép.

Trong chương **Security Objectives** của học phần **Business Logic Security**, đây là một mục tiêu bảo vệ xuyên suốt. Business invariant xác định điều không được vi phạm; state machine biểu diễn các bước và điều kiện chuyển trạng thái; quyền theo đối tượng xác định ai được tác động lên hồ sơ nào; transaction và idempotency giúp giữ quyết định nhất quán khi có cạnh tranh hoặc gửi lại yêu cầu.

Sau bài này, bạn cần có khả năng:

- Phân biệt tính toàn vẹn của dữ liệu với tính toàn vẹn của quyết định và tác động thực tế.
- Xác định các dữ kiện, thẩm quyền và phiên bản chính sách làm cơ sở cho một quyết định.
- Ràng buộc phê duyệt với đúng nội dung hồ sơ, thay vì chỉ gắn một cờ “đã duyệt”.
- Thiết kế điều kiện thực thi để thay đổi dữ liệu, retry và xử lý đồng thời không làm sai ý nghĩa quyết định.
- Viết tình huống kiểm thử dựa trên kết quả nghiệp vụ bị cấm.

## 2. Quyết định nghiệp vụ gồm những gì?

Một quyết định nghiệp vụ trả lời câu hỏi có tác động đến quyền lợi, tài sản hoặc trách nhiệm. Ví dụ:

| Quyết định | Dữ kiện cần xem xét | Tác động cần được bảo vệ |
| --- | --- | --- |
| Chấp nhận giá thanh toán | Giá do máy chủ xác định, số lượng, ưu đãi, thuế, thời hạn báo giá | Khách bị thu đúng số tiền theo chính sách đã chốt |
| Duyệt hoàn tiền | Giao dịch gốc, phần được hoàn, trạng thái trả hàng, thẩm quyền người duyệt | Không hoàn sai người, sai khoản hoặc vượt quyền |
| Cho phép chuyển trạng thái hồ sơ | Trạng thái nguồn, điều kiện bắt buộc, người thực hiện | Không bỏ qua kiểm tra hoặc phê duyệt |
| Cấp quyền truy cập đối tượng | Danh tính, tenant, quan hệ sở hữu, phạm vi công việc | Không thao tác trên dữ liệu hoặc tài sản ngoài quyền |
| Phát hoặc thu hồi thưởng | Điều kiện chiến dịch, giao dịch đủ tư cách, lịch sử cấp thưởng | Không nhận lại quyền lợi hoặc giữ quyền lợi trái chính sách |

Một quyết định cần được mô tả đủ cụ thể. “Cho phép hoàn tiền” chưa nói rõ hoàn cho hồ sơ nào, theo khoản thanh toán nào, số tiền bao nhiêu, tiền tệ gì và quyết định có hiệu lực đến khi nào.

Có thể biểu diễn một quyết định phê duyệt dưới dạng:

~~~text
Quyết định:
  hành động: APPROVE_REFUND
  tenant: T1
  hồ sơ: RF-1042
  phiên bản nội dung: 7
  khoản thanh toán: P1
  số tiền: 1.200.000 VND
  người duyệt: U-SUPERVISOR-8
  chính sách: REFUND-POLICY phiên bản 12
  kết quả: APPROVED
  thời điểm quyết định: thời gian do máy chủ ghi nhận
  điều kiện thực thi: hồ sơ chưa đổi nội dung, còn hiệu lực,
                     đủ ngân sách hoàn, chưa có lệnh thực thi
~~~

Quyết định này không tự cho phép hoàn 2.800.000 đồng, chuyển sang khoản thanh toán khác hoặc dùng trong tenant khác.

### 2.1. Dữ liệu toàn vẹn chưa chứng minh quyết định đúng

Giả sử cơ sở dữ liệu lưu chính xác rằng một hồ sơ hiện có số tiền 2.800.000 đồng và trạng thái `APPROVED`. Hai trường đó không bị hỏng ở mức lưu trữ. Tuy nhiên, trạng thái phê duyệt có thể được tạo khi số tiền còn là 1.200.000 đồng.

Nếu chương trình chỉ đọc “trạng thái đã duyệt” rồi hoàn số tiền hiện tại, tính toàn vẹn của quyết định đã bị phá. Hệ thống không còn biết người duyệt thực sự đã đồng ý điều gì.

| Mục tiêu | Câu hỏi trọng tâm |
| --- | --- |
| Toàn vẹn dữ liệu | Giá trị có được thay đổi và lưu trữ theo cơ chế kiểm soát không? |
| Toàn vẹn quyết định | Với đúng dữ kiện và thẩm quyền, kết luận này có hợp lệ và có bị thay nghĩa không? |
| Toàn vẹn thực thi | Tác động có khớp nội dung đã được cho phép, với số lần và điều kiện cho phép không? |
| Bí mật | Ai được xem dữ kiện, quyết định và tài liệu liên quan? |
| Sẵn sàng | Quy trình có tiếp tục xử lý được trong giới hạn dịch vụ không? |

Các mục tiêu liên quan nhưng không thay thế nhau. Mã hóa một bản ghi không sửa được quy tắc tự duyệt sai. Tăng khả năng chịu tải không ngăn một lệnh hoàn tiền hợp lệ về cú pháp nhưng vượt thẩm quyền.

## 3. Từ dữ kiện đến tác động: một chuỗi cần được bảo vệ

Có thể nhìn quyết định như kết quả của một hàm:

~~~text
quyết định = evaluate(
    chủ thể và thẩm quyền,
    đối tượng cùng phiên bản nội dung,
    dữ kiện nghiệp vụ có thẩm quyền,
    chính sách cùng phiên bản,
    ngữ cảnh và thời điểm đánh giá
)
~~~

Đây là mô hình tư duy, không phải yêu cầu gom mọi dữ liệu vào một hàm khổng lồ. Nó buộc người thiết kế chỉ ra nguồn của từng đầu vào.

~~~mermaid
flowchart LR
    A[Danh tính và thẩm quyền] --> E[Đánh giá chính sách]
    B[Snapshot nội dung hồ sơ] --> E
    C[Dữ kiện nghiệp vụ đáng tin cậy] --> E
    D[Phiên bản chính sách và thời gian] --> E
    E --> F[Quyết định có nội dung ràng buộc]
    F --> G[Kiểm tra điều kiện thực thi]
    G --> H[Tác động và sổ ghi nhận]
~~~

Có hai điểm kiểm soát khác nhau:

1. **Tại lúc quyết định:** dữ kiện và quyền có đủ để đưa ra kết luận không?
2. **Tại lúc thực thi:** đối tượng còn phù hợp với quyết định và các điều kiện hiện hành bắt buộc không?

Một số dữ kiện nên được chốt thành snapshot, như giá đã thỏa thuận hoặc nội dung đã trình duyệt. Một số dữ kiện phải được kiểm tra lại khi thực thi, như ngân sách hoàn tiền còn lại, việc quyết định đã bị thu hồi hay chưa và điều kiện cấm giao dịch đang có hiệu lực. Cần quy định rõ loại nào được chốt, loại nào phải kiểm tra lại; không dùng một snapshot cũ để thay cho mọi điều kiện hiện tại.

### 3.1. Phân loại đầu vào theo mức độ tin cậy

| Đầu vào | Nguồn có thẩm quyền thường gặp | Điều không nên mặc nhiên tin |
| --- | --- | --- |
| Người gọi, tenant đang hoạt động | Ngữ cảnh xác thực và cơ chế chọn tenant có kiểm tra quyền | `userId`, `tenantId` tùy ý trong JSON |
| Giá và phần giảm giá | Dịch vụ giá hoặc snapshot giao dịch đã chốt | Giá hiển thị hoặc tổng tiền do trình duyệt gửi |
| Phạm vi thẩm quyền | Kho quyền, phân công và quy tắc nghiệp vụ phía máy chủ | Một cờ `isManager=true` do khách truyền |
| Số tiền còn được hoàn | Sổ thanh toán, khoản giữ và các lệnh hoàn liên quan | Tổng tiền của riêng hồ sơ hiện tại |
| Kết quả bên ngoài | Phản hồi đã xác minh, truy vấn đối soát, sự kiện có kiểm tra nguồn | URL quay về của trình duyệt có tham số `success=true` |
| Thời gian xét hạn | Đồng hồ máy chủ và chính sách thời gian đã xác định | Giờ trên thiết bị hoặc timestamp tự khai |

Một dữ kiện đến từ dịch vụ nội bộ vẫn cần đúng phạm vi, ngữ nghĩa và độ mới. “Nội bộ” không bảo đảm bản sao quyền đã cập nhật, giá thuộc đúng tiền tệ hoặc mã hồ sơ thuộc cùng tenant.

## 4. Tình huống xuyên suốt: sửa số tiền sau khi được duyệt

Xét một chính sách minh họa:

- Khoản thanh toán P1 của tenant T1 đã thực thu 3.000.000 đồng và còn đủ quyền hoàn.
- Hồ sơ RF-1042 đề nghị hoàn 1.200.000 đồng.
- Người giám sát được duyệt tối đa 2.000.000 đồng mỗi hồ sơ thuộc phạm vi mình phụ trách.
- Khoản lớn hơn cần luồng phê duyệt của bộ phận tài chính.
- Người đề nghị không được tự duyệt.
- Mỗi quyết định phê duyệt cuối cùng chỉ được tạo một lệnh hoàn tiền nghiệp vụ.

Tại phiên bản nội dung 7, người giám sát duyệt 1.200.000 đồng. Nếu tính năng sửa hồ sơ vẫn cho người đề nghị đổi số tiền thành 2.800.000 đồng mà giữ nguyên cờ đã duyệt, worker có thể hoàn theo giá trị mới.

Ở đây:

- Người giám sát có thể đã đăng nhập đúng và thao tác đúng quyền tại thời điểm duyệt.
- Người đề nghị có thể có quyền sửa hồ sơ trong một số trạng thái.
- Số tiền 2.800.000 đồng vẫn nhỏ hơn tiền đã thu, nên một kiểm tra “không hoàn quá tiền thanh toán” có thể vẫn cho qua.
- Quyết định thực thi vẫn sai vì không ai có thẩm quyền đã duyệt nội dung mới theo luồng bắt buộc.

### 4.1. Cách giữ nguyên ý nghĩa phê duyệt

Quyết định cần ràng buộc với **phiên bản nội dung có ý nghĩa nghiệp vụ**, chẳng hạn `contentRevision=7`, cùng các trường được duyệt. Khi thay đổi số tiền, tiền tệ, khoản thanh toán, người thụ hưởng hoặc điều kiện ảnh hưởng phê duyệt:

1. Tăng phiên bản nội dung.
2. Chuyển hồ sơ về trạng thái cần đánh giá hoặc phê duyệt lại theo chính sách.
3. Vô hiệu hóa khả năng thực thi từ quyết định cũ.
4. Giữ lịch sử quyết định cũ để giải thích những gì đã xảy ra.

Không nên sửa ngược quyết định cũ thành nội dung mới. Một quyết định đã ghi nhận là bằng chứng về một lần đánh giá, không phải một ô trạng thái có thể tùy ý cập nhật.

Trong thiết kế này, `contentRevision` chỉ tăng khi dữ liệu có ảnh hưởng quyết định thay đổi. Nó khác với phiên bản kỹ thuật của aggregate dùng cho optimistic locking, vốn có thể tăng cả khi đổi trạng thái hoặc thêm thông tin khác. Nếu sử dụng một trường phiên bản duy nhất, phải quy định rõ cách ràng buộc trước và sau mỗi lần chuyển trạng thái để không tự làm quyết định vừa tạo trở nên vô hiệu.

### 4.2. Có được giữ duyệt khi thay đổi trường khác không?

Một sửa lỗi chính tả ở ghi chú nội bộ có thể không cần duyệt lại. Thay đổi lý do hoàn, chứng từ, số lượng hoặc người nhận tiền có thể ảnh hưởng trực tiếp.

Cần lập danh sách trường có ảnh hưởng và kiểm soát mọi đường ghi, gồm API, giao diện nhân viên, tác vụ nhập dữ liệu và job nền. Nếu một endpoint tăng phiên bản nhưng job khác sửa tiền mà không tăng, cơ chế ràng buộc vẫn bị phá.

Nếu doanh nghiệp cho phép phê duyệt theo hạn mức thay vì một số tiền cố định, phải biểu diễn rõ: ví dụ “cho phép hoàn tối đa 1.200.000 VND cho các dòng hàng này”. Không tự diễn giải một phê duyệt số tiền cụ thể thành hạn mức dùng cho mọi đối tượng.

## 5. Các thuộc tính cần có của một quyết định toàn vẹn

### 5.1. Đúng chủ thể và thẩm quyền

Xác thực chỉ trả lời người gọi là ai. Quyền chức năng như `APPROVE_REFUND` chưa đủ để quyết định người đó có được duyệt một hồ sơ cụ thể hay không.

Cần kiểm tra tenant, phạm vi phụ trách, hạn mức tiền, loại hồ sơ và quan hệ với người đề nghị. Quy tắc tách biệt nhiệm vụ phải so sánh đúng danh tính hoặc quan hệ mà chính sách quy định. Một người có cả vai trò đề nghị và phê duyệt không tự động được phép tự duyệt.

Nếu chính sách yêu cầu hai người duyệt độc lập, hai request từ cùng một chủ thể không được tính thành hai phê duyệt. Ràng buộc danh tính và tính duy nhất phải có tại nơi lưu quyết định.

### 5.2. Đúng đối tượng và quan hệ

Quyết định phải gắn với tenant, loại đối tượng và định danh cụ thể. Đồng thời kiểm tra quan hệ giữa hồ sơ, đơn hàng, dòng hàng, khoản thanh toán và người nhận.

Sở hữu một đơn không chứng minh được quyền dùng bất kỳ `paymentId` nào. Tương tự, một quyết định duyệt hợp lệ trong tenant T1 không được dùng cho hồ sơ có cùng mã hiển thị trong tenant T2.

### 5.3. Đúng dữ kiện và chính sách

Chính sách cần xác định đầu vào bắt buộc, cách tính và điều kiện từ chối. Thiếu dữ kiện quan trọng phải dẫn đến kết quả rõ ràng như chờ xác minh, lỗi đánh giá hoặc từ chối theo chính sách; không tự coi là được phép.

Ví dụ, dịch vụ quyền bị lỗi không được khiến chương trình bỏ kiểm tra hạn mức. Dịch vụ ưu đãi không phản hồi cũng không đồng nghĩa mọi mã giảm giá đều hợp lệ.

Chính sách có phiên bản giúp giải thích quyết định lịch sử và xử lý thay đổi. Tuy vậy, việc ghi một chuỗi `policyVersion` không tự chứng minh đã thực thi đúng phiên bản. Mã đánh giá phải thực sự nạp phiên bản bất biến tương ứng, và cần đủ bằng chứng để biết dữ kiện nào đã được sử dụng.

### 5.4. Đúng thời điểm và điều kiện hiệu lực

Một quyết định có thể hết hạn, bị thu hồi hoặc không còn phù hợp vì nội dung hồ sơ thay đổi. Cần phân biệt:

- Quyết định còn hiệu lực theo thời hạn đã chốt.
- Hồ sơ vẫn ở trạng thái được phép thực thi.
- Những điều kiện hiện hành bắt buộc vẫn còn đúng.
- Quy tắc xử lý khi quyền người duyệt hoặc chính sách thay đổi đã được xác định.

Không có một đáp án chung rằng mọi thay đổi quyền đều phải vô hiệu hóa mọi quyết định cũ. Có nghiệp vụ công nhận phê duyệt đã tạo hợp lệ; có nghiệp vụ bắt buộc người duyệt vẫn có thẩm quyền lúc thực thi. Hệ thống phải thực hiện đúng lựa chọn đã được quy định, thay vì để kết quả phụ thuộc vào cache hoặc thứ tự worker.

### 5.5. Tác động khớp nội dung và số lần được phép

Quyết định duyệt không được trở thành giấy phép dùng vô hạn. Nếu nghiệp vụ quy định một lệnh hoàn cho mỗi quyết định, cần tính duy nhất theo `decisionId`, không chỉ theo khóa request do khách chọn.

Trong các nghiệp vụ khác, một quyết định có thể cho phép nhiều lần sử dụng đến một hạn mức. Khi đó cần theo dõi phần đã dùng và phần đang giữ một cách nguyên tử. Không áp dụng máy móc quy tắc “một lần” cho mọi quyết định.

## 6. Invariant và state machine cùng bảo vệ điều gì?

Một số invariant cho ví dụ hoàn tiền:

~~~text
Nội dung thực thi phải khớp nội dung được duyệt.
Người duyệt phải có thẩm quyền theo chính sách áp dụng.
Nếu cấm tự duyệt: người duyệt khác người đề nghị.
Một quyết định cuối cùng không tạo nhiều lệnh hoàn nghiệp vụ.
Tổng đã hoàn + đang giữ + khoản mới không vượt ngân sách liên quan.
Hồ sơ chỉ được thực thi từ trạng thái được cho phép.
~~~

Mỗi invariant cần có nơi thực thi cụ thể. Không để quy tắc quan trọng chỉ tồn tại trong tài liệu hoặc một màn hình.

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING_APPROVAL: Gửi đúng phiên bản nội dung
    PENDING_APPROVAL --> APPROVED: Đủ phê duyệt theo chính sách
    PENDING_APPROVAL --> REJECTED: Không được duyệt
    PENDING_APPROVAL --> DRAFT: Sửa nội dung cần đánh giá lại
    APPROVED --> DRAFT: Sửa nội dung và vô hiệu hiệu lực quyết định cũ
    APPROVED --> EXECUTION_PENDING: Kiểm tra binding và giữ ngân sách
    APPROVED --> REVOKED: Thu hồi theo thẩm quyền
    EXECUTION_PENDING --> COMPLETED: Xác nhận tác động thành công
    EXECUTION_PENDING --> EXECUTION_FAILED: Xác nhận thất bại cuối cùng
~~~

Đây là sơ đồ minh họa, không phải quy trình dùng chung cho mọi sản phẩm. Chính sách thử lại sau thất bại, tạo quyết định mới hoặc phục hồi hồ sơ cần được bổ sung theo nghiệp vụ.

Không cho sửa nội dung quyết định trong trạng thái đang thực thi chỉ bằng cách chuyển ngược về nháp. Khi lệnh bên ngoài có thể đã được gửi, cần xác định kết quả lệnh đó trước hoặc áp dụng quy trình hủy, điều chỉnh hay bù trừ rõ ràng.

Một enum trạng thái không tự bảo vệ quy trình. Tất cả đường thay đổi trạng thái phải kiểm tra trạng thái nguồn, quyền, phiên bản nội dung và điều kiện nghiệp vụ.

## 7. Giữ nhất quán giữa kiểm tra và ghi nhận

### 7.1. Rủi ro kiểm tra trước, dữ liệu đổi sau

Lỗi **time-of-check to time-of-use**, thường gọi là TOCTOU, xuất hiện khi điều kiện đúng lúc kiểm tra nhưng không còn đúng lúc sử dụng.

Ví dụ:

~~~text
T1: Worker đọc hồ sơ đã duyệt, phiên bản nội dung 7.
T2: Một thao tác sửa hồ sơ thành phiên bản 8.
T1: Worker thực thi số tiền từ bản ghi mới hoặc bỏ qua kiểm tra phiên bản.
~~~

Vấn đề không được giải quyết chỉ bằng cách gọi lại hàm kiểm tra trước thao tác ghi vài dòng mã. Cần cơ chế bảo đảm sự thay đổi cạnh tranh không chen giữa kiểm tra và việc giành quyền thực thi.

Có thể dùng khóa hàng trong transaction, optimistic locking hoặc cập nhật có điều kiện, tùy mô hình và hệ quản trị. Ví dụ SQL minh họa:

~~~sql
UPDATE refund_request
SET state = 'EXECUTION_PENDING',
    execution_id = :execution_id
WHERE tenant_id = :tenant_id
  AND id = :request_id
  AND state = 'APPROVED'
  AND content_revision = :approved_content_revision
  AND active_decision_id = :decision_id;
~~~

Ứng dụng chỉ tiếp tục khi số hàng cập nhật bằng 1. Các tham số quyết định phải được lấy từ bản ghi quyết định đáng tin cậy đã kiểm tra, không nhận nguyên trạng từ khách.

Đây chỉ là một phần của transaction. Cùng transaction còn phải xác minh quyết định chưa hết hạn hoặc bị thu hồi theo cơ chế nhất quán đã chọn, giữ ngân sách liên quan, tạo lệnh thực thi duy nhất và ghi outbox nếu cần gọi dịch vụ khác. Những thao tác sửa hồ sơ cũng phải tuân thủ quy tắc trạng thái để không đổi nội dung sau khi worker đã giành quyền thực thi.

### 7.2. Nhiều hồ sơ cùng dùng một ngân sách

Khóa RF-1042 không khóa một hồ sơ khác đang hoàn từ cùng P1. Do đó, ngân sách của khoản thanh toán và quyền hoàn theo dòng hàng cũng cần được bảo vệ tại bản ghi dùng chung.

Với cùng khoản thanh toán và tiền tệ:

~~~text
đã_hoàn + đang_giữ + khoản_mới <= ngân_sách_được_hoàn
~~~

Kiểm tra điều kiện rồi ghi từ hai transaction tách biệt có thể làm cả hai cùng thành công. Cơ chế giữ ngân sách cần nguyên tử, chẳng hạn cập nhật có điều kiện hoặc khóa bản ghi tương ứng. Mọi luồng hoàn tiền phải cùng tuân thủ cơ chế đó.

### 7.3. Quyết định bên ngoài transaction

Nếu đánh giá có gọi dịch vụ ngoài, không nên giả định transaction cục bộ giữ được dữ kiện bên kia không đổi. Cần một hợp đồng như snapshot có phiên bản, báo giá có thời hạn, giữ quyền lợi có token hoặc tái xác nhận tại thời điểm tiêu thụ.

Khi một dữ kiện không thể được chốt hoặc giữ nguyên tử, thiết kế phải chỉ ra cách phát hiện hết hiệu lực và xử lý thất bại. Kéo dài transaction trong lúc chờ mạng không tự tạo ra tính nguyên tử xuyên dịch vụ.

## 8. Minh họa mã Java: phê duyệt có ràng buộc nội dung

Đoạn mã sau là **mã khung kiến trúc**, không phải chương trình chạy độc lập. Nó minh họa một thao tác tạo phê duyệt cuối cùng khi người gọi và hồ sơ đã đáp ứng đủ chính sách. Luồng cần bổ sung phê duyệt tài chính phải được xử lý riêng, không được biến thành phê duyệt cuối chỉ vì hàm này được gọi.

~~~java
record ApproveRefundCommand(
        String requestId,
        long expectedContentRevision) {}

record ApprovalReceipt(
        String decisionId,
        String requestId,
        long approvedContentRevision) {}

public ApprovalReceipt approveRefund(
        ActorContext actor,
        ApproveRefundCommand command) {

    validateCommand(command);

    return transactions.required(() -> {
        var request = refundRequests.lockByTenantAndId(
                actor.tenantId(), command.requestId());

        permissions.requireCanReviewRefund(actor, request);
        request.requirePendingApproval();
        request.requireContentRevision(command.expectedContentRevision());

        // The snapshot contains server-owned business fields.
        var snapshot = request.approvalSnapshot();
        var facts = authoritativeFacts.forApproval(actor, snapshot);
        var policy = policies.immutableVersion(request.policyVersion());

        var evaluation = policy.evaluateFinalApproval(
                actor, snapshot, facts);

        // Rejects self-approval, insufficient authority and missing approvals.
        evaluation.requireFinalApprovalPermitted();

        var now = serverClock.instant();
        var grant = ApprovalGrant.issue(
                snapshot.binding(),
                policy.version(),
                actor.subjectId(),
                now,
                policy.expiryFrom(now));

        decisions.insertImmutable(grant);
        refundRequests.attachApprovalAndMarkApproved(
                request, grant.id(), snapshot.contentRevision());
        auditOutbox.appendApprovalCreated(grant.auditRecord());

        return new ApprovalReceipt(
                grant.id(), request.id(), snapshot.contentRevision());
    });
}
~~~

Các hợp đồng bắt buộc của mã khung:

1. `ActorContext` đến từ ngữ cảnh xác thực đáng tin cậy. Quyền truy cập tenant và đối tượng vẫn được kiểm tra tại máy chủ.
2. `lockByTenantAndId` bảo vệ cùng hồ sơ khỏi sửa cạnh tranh trong transaction. Những đường ghi khác phải sử dụng cơ chế tương thích.
3. `approvalSnapshot` chứa đúng nội dung cần duyệt: đối tượng liên quan, số tiền, tiền tệ, phiên bản nội dung và dữ kiện có ảnh hưởng. Không chứa số tiền tự khai chưa được kiểm chứng.
4. `authoritativeFacts` có nguồn, độ mới và cách giữ hiệu lực rõ ràng. Các giới hạn dùng chung có thể cần được kiểm tra lại khi thực thi; snapshot lúc duyệt không tự giữ ngân sách.
5. `evaluateFinalApproval` áp dụng đúng phiên bản chính sách, kiểm tra thẩm quyền theo giá trị, tách biệt nhiệm vụ và các phê duyệt bắt buộc. Vai trò chung không thay thế đánh giá này.
6. `insertImmutable`, gắn quyết định với hồ sơ và ghi sự kiện kiểm toán cùng thành công hoặc rollback trong transaction cục bộ.
7. Các ràng buộc duy nhất ngăn ghi hai phê duyệt cuối không tương thích hoặc tính một người thành nhiều người duyệt. Khóa Java trong một tiến trình không đủ khi có nhiều instance.
8. Retry sau khi mất phản hồi phải tìm được quyết định đã tạo theo hợp đồng API và ràng buộc nghiệp vụ, thay vì tự tạo một quyết định mới.

Ở thời điểm thực thi, không chỉ đọc `request.state == APPROVED`. Thành phần thực thi phải tải quyết định, so khớp binding, kiểm tra hiệu lực, giành quyền thực thi và bảo vệ ngân sách. Ví dụ này chưa hiện thực các bước đó.

Đối với tiền trong Java, dùng số nguyên theo đơn vị tiền nhỏ nhất với kiểm tra tràn số, hoặc `BigDecimal` với scale và cách làm tròn rõ ràng. Không dùng `double` để quyết định hạn mức. Tiền tệ là một phần của dữ kiện; không cộng hoặc so sánh trực tiếp các khoản khác tiền tệ nếu chưa có chính sách chuyển đổi.

## 9. Quyết định cần lưu bằng chứng gì?

Một bản ghi quyết định có ích cho thực thi và kiểm toán thường gồm:

| Nhóm dữ liệu | Nội dung minh họa |
| --- | --- |
| Định danh | `decisionId`, loại hành động, tenant, đối tượng |
| Binding nội dung | Phiên bản nội dung và các trường đã duyệt, hoặc tham chiếu snapshot bất biến |
| Thẩm quyền | Người duyệt, danh tính người đề nghị, phạm vi hoặc bằng chứng quyền cần thiết |
| Chính sách | Mã và phiên bản thực sự được dùng khi đánh giá |
| Kết quả | Cho phép, từ chối, cần phê duyệt bổ sung hoặc chưa đủ dữ kiện |
| Lý do | Mã lý do có ý nghĩa nghiệp vụ, các điều kiện đã thỏa hoặc chưa thỏa |
| Hiệu lực | Thời điểm quyết định, thời hạn và trạng thái thu hồi nếu có |
| Thực thi | Tham chiếu lệnh đã tạo, phần quyền lợi đã dùng hoặc đang giữ |

Không cần sao chép mọi dữ liệu nhạy cảm vào log. Có thể lưu tham chiếu tới snapshot được bảo vệ, dữ kiện tối thiểu hoặc dấu vết phù hợp với nhu cầu truy nguyên và thời gian lưu trữ. Người dùng xem lịch sử cũng phải có quyền theo đối tượng.

Lưu dữ liệu đầu vào và phiên bản chính sách giúp giải thích hoặc tái đánh giá, nhưng không phải lúc nào cũng tái tạo chính xác mọi quyết định. Nếu một dịch vụ ngoài trả kết quả rủi ro mà không lưu dữ kiện hoặc phiên bản mô hình cần thiết, việc chạy lại sau này có thể cho kết quả khác. Hệ thống cần nói rõ giới hạn bằng chứng của mình.

### 9.1. Hash không tạo ra thẩm quyền

Hash của nội dung có thể hỗ trợ phát hiện không khớp với một giá trị tham chiếu đáng tin cậy. Nếu người dùng được thay cả nội dung lẫn hash thì hash không chứng minh đã được phê duyệt.

Khi dùng hash để ràng buộc nội dung, cần xác định schema và cách chuẩn hóa: trường bắt buộc, thứ tự biểu diễn, đơn vị tiền, số thập phân và giá trị rỗng. Hash của chuỗi JSON tùy ý có thể khác nhau vì biểu diễn dù cùng ý nghĩa, hoặc bỏ sót trường nghiệp vụ nếu chọn sai đầu vào.

Trong cùng một hệ thống, một bản ghi quyết định được bảo vệ bằng quyền ghi và transaction có thể đã đủ; không phải mọi phê duyệt đều cần chữ ký số.

Nếu truyền một chứng thư quyết định giữa dịch vụ, chữ ký hoặc MAC chỉ bảo vệ nội dung trong phạm vi mô hình khóa tương ứng. Bên nhận vẫn phải kiểm tra đúng bên phát hành, bên nhận dự kiến, tenant, đối tượng, hành động, hiệu lực, khả năng thu hồi và việc sử dụng lại. Một token hợp lệ về mật mã không tự chứng minh ngân sách hiện tại còn đủ.

## 10. Retry và tác động bên ngoài phải giữ cùng ý nghĩa

Có ba thứ dễ bị nhầm:

- **Khóa idempotency của request:** nhận diện việc gửi lại cùng ý định ở một phạm vi API.
- **Mã quyết định:** nhận diện kết quả đánh giá nghiệp vụ cụ thể.
- **Mã lệnh thực thi:** nhận diện tác động được tạo từ quyết định đó.

Nếu người dùng gửi khóa idempotency mới, mã quyết định cũ không được trở thành nguồn tạo thêm lệnh tài chính ngoài chính sách. Cần ràng buộc duy nhất từ quyết định sang lệnh, hoặc cơ chế trừ hạn mức nếu quyết định được dùng nhiều lần.

Luồng minh họa cho quyết định hoàn tiền một lần:

1. Transaction cục bộ kiểm tra quyết định, giữ ngân sách, tạo một lệnh thực thi và ghi outbox.
2. Worker gửi lệnh bằng mã ổn định, sử dụng khả năng idempotency của nhà cung cấp theo đúng hợp đồng hỗ trợ.
3. Nếu worker dừng hoặc mất phản hồi, lần xử lý lại dùng cùng lệnh và cùng khóa bên ngoài.
4. Khi có kết quả chắc chắn, hệ thống cập nhật trạng thái và sổ tài chính theo cơ chế chống áp dụng trùng.
5. Khi kết quả chưa rõ, tiếp tục đối soát; không tự tạo một lệnh nghiệp vụ mới hoặc giải phóng khoản giữ vì timeout.

Outbox giúp bảo toàn ý định đã commit trước khi gọi dịch vụ ngoài. Nó không tự làm tác động bên ngoài xảy ra đúng một lần. Cần kết hợp tính duy nhất nghiệp vụ, khả năng của nhà cung cấp và đối soát.

Một sự kiện hoàn tiền thành công cũng không phải lệnh phê duyệt mới. Webhook hoặc message đến trùng, muộn hay sai thứ tự chỉ được cập nhật trạng thái trong phạm vi hợp lệ; không được làm thay đổi nội dung đã duyệt.

## 11. Thay đổi chính sách và thu hồi quyết định

Khi hạn mức người giám sát giảm từ 2.000.000 xuống 1.000.000 đồng, một hồ sơ đã duyệt 1.200.000 đồng cần được xử lý thế nào? Phải trả lời bằng chính sách, không bằng cách triển khai tình cờ.

Có thể có các lựa chọn:

| Cách áp dụng | Ý nghĩa | Cơ chế cần có |
| --- | --- | --- |
| Công nhận quyết định cũ còn hiệu lực | Duyệt hợp lệ theo phiên bản cũ vẫn được thực thi trong phạm vi đã chốt | Lưu phiên bản, hạn hiệu lực và các điều kiện hiện hành vẫn phải kiểm tra |
| Bắt buộc đánh giá lại trước thực thi | Quyết định cũ chưa đủ để tạo tác động sau thời điểm đổi chính sách | Đánh dấu cần đánh giá lại, thông báo lý do, ngăn worker dùng quyết định cũ |
| Thu hồi nhóm quyết định cụ thể | Áp dụng khi có sự cố hoặc rủi ro xác định | Quyền thu hồi, phạm vi rõ ràng, lịch sử và đồng bộ với worker |

Không âm thầm dùng chính sách mới để diễn giải lại bản ghi lịch sử như thể đó là quy tắc tại thời điểm duyệt.

Thu hồi trước thực thi khác với đảo ngược tác động đã hoàn tất. Nếu tiền đã được hoàn, thay trạng thái quyết định thành “thu hồi” không lấy lại được tiền. Cần một nghiệp vụ điều chỉnh hoặc bù trừ riêng, có thẩm quyền và dấu vết riêng.

Cache quyền hoặc chính sách cần có chiến lược hết hạn, phiên bản hoặc vô hiệu hóa phù hợp. Nếu điều kiện yêu cầu hiệu lực ngay, cache có thể trả dữ liệu cũ không được xem là đủ bằng chứng.

## 12. Kiểm thử tính toàn vẹn của quyết định

Bắt đầu bằng việc viết kết quả nào bị cấm, rồi thử thay đổi đầu vào, quan hệ, thời gian hoặc thứ tự để đạt kết quả đó. Thực hiện trên môi trường và dữ liệu kiểm thử được cho phép.

| Tình huống | Thao tác kiểm thử | Điều cần chứng minh |
| --- | --- | --- |
| Sửa số tiền sau duyệt | Duyệt phiên bản 7 với 1.200.000 đồng, sửa thành phiên bản 8 với 2.800.000 đồng | Quyết định cũ không thể thực thi nội dung mới |
| Sửa trường liên quan | Đổi payment, tiền tệ hoặc người nhận sau duyệt | Binding không còn phù hợp; phải xử lý lại theo chính sách |
| Giữ nguyên ID, đổi tenant | Dùng quyết định T1 cho đối tượng T2 | Không tạo tác động hoặc tiết lộ dữ liệu trái quyền |
| Ghép sai quan hệ | Dùng hồ sơ hợp lệ với khoản thanh toán không thuộc giao dịch | Bị chặn tại kiểm tra quan hệ phía máy chủ |
| Vượt thẩm quyền | Người giám sát duyệt khoản vượt 2.000.000 đồng trong chính sách ví dụ | Không tạo phê duyệt cuối; đi đúng luồng tài chính |
| Tự duyệt hoặc tính trùng người duyệt | Người đề nghị tự duyệt; một người gửi hai lần trong luồng hai người | Không thỏa điều kiện độc lập |
| Thiếu dữ kiện | Dịch vụ quyền hoặc nguồn dữ kiện bắt buộc lỗi | Không có kết quả cho phép ngầm định |
| Cạnh tranh sửa và thực thi | Đồng bộ hai luồng cùng chạm hồ sơ | Hoặc sửa thắng và yêu cầu duyệt lại, hoặc thực thi thắng và chặn sửa; không dùng nội dung chưa duyệt |
| Cạnh tranh ngân sách | Hai quyết định dùng chung khoản thanh toán | Tổng đã hoàn và đang giữ không vượt giới hạn |
| Retry | Gửi lại cùng request; sau đó đổi khóa nhưng dùng cùng quyết định | Không tạo thêm quyết định hoặc tác động ngoài hợp đồng |
| Hết hạn hoặc thu hồi | Cho worker xử lý sau thời hạn hoặc sau thu hồi đã có hiệu lực | Không sử dụng quyết định mất hiệu lực |
| Đổi chính sách | Chuyển phiên bản giữa lúc duyệt và lúc thực thi | Kết quả khớp quy tắc chuyển tiếp đã công bố |
| Mất phản hồi nhà cung cấp | Tác động đã xảy ra nhưng worker nhận timeout | Không tạo lệnh mới, không giải phóng ngân sách sai |
| Sự kiện trùng hoặc lệch thứ tự | Phát lại message và webhook cũ | Không cộng tác động hai lần hoặc quay lùi trạng thái cuối |

Đối với kiểm thử cạnh tranh, cần đồng bộ các luồng tại điểm có thể tranh chấp và chạy với cơ sở dữ liệu có ngữ nghĩa transaction thực tế. Hai request chạy tuần tự hoặc mock luôn thành công không chứng minh được tính nguyên tử.

Không chỉ kiểm tra mã HTTP. Cần xem số quyết định, nội dung binding, trạng thái hồ sơ, khoản giữ, lệnh outbox, sổ tài chính và số tác động tại nhà cung cấp mô phỏng.

Có thể bổ sung kiểm thử sinh chuỗi thao tác: tạo, sửa, gửi duyệt, duyệt, thu hồi, retry, thực thi và nhận sự kiện. Sau mỗi bước commit, các invariant vẫn phải đúng. Cách này hữu ích khi lỗi chỉ xuất hiện trong tổ hợp trạng thái.

## 13. Dấu vết kiểm toán và giám sát

Cần đủ dữ kiện để trả lời: **Ai đã quyết định điều gì, dựa trên nội dung và chính sách nào, rồi hệ thống đã thực hiện ra sao?**

Một chuỗi tương quan hữu ích:

~~~text
requestId
  -> contentRevision
  -> decisionId
  -> executionId
  -> externalTransactionId
~~~

Kèm theo đó là tenant, chủ thể, thời gian máy chủ, phiên bản chính sách, mã lý do và các chuyển trạng thái. Không ghi bí mật xác thực, token đầy đủ hoặc dữ liệu thanh toán nhạy cảm không cần thiết.

Các dấu hiệu đáng kiểm tra gồm:

- Thực thi không có quyết định đang hiệu lực hoặc không khớp phiên bản nội dung.
- Một quyết định một lần gắn với nhiều lệnh thực thi.
- Nhiều lần sửa trường tài chính ngay sau phê duyệt.
- Luồng phê duyệt tập trung bất thường vào một cặp người đề nghị và người duyệt.
- Lệnh chờ kết quả bên ngoài quá lâu, không được đối soát.
- Thay đổi dữ liệu qua đường quản trị không phát sinh lịch sử tương ứng.

Dấu hiệu bất thường là cơ sở điều tra, không tự chứng minh gian lận. Giám sát cũng không thay thế việc chặn sai phạm tại nơi quyết định hoặc tạo tác động.

Quyền sửa quyết định và quyền sửa dấu vết kiểm toán cần được kiểm soát. Nếu một tài khoản nghiệp vụ có thể đồng thời thay số tiền, sửa người duyệt và xóa lịch sử, việc ghi log thông thường không bảo đảm được bằng chứng đáng tin cậy.

## 14. Những cách triển khai dễ làm sai mục tiêu

| Cách triển khai | Vì sao chưa đủ | Cách sửa theo mục tiêu |
| --- | --- | --- |
| Chỉ có cờ `approved=true` | Không biết ai duyệt nội dung nào | Lưu quyết định, binding và điều kiện hiệu lực |
| Chỉ kiểm tra vai trò “manager” | Bỏ qua hạn mức, đối tượng và tự duyệt | Đánh giá thẩm quyền theo ngữ cảnh nghiệp vụ |
| Tin số tiền hoặc tenant do client gửi | Client có thể chọn dữ kiện có lợi | Xác định lại từ nguồn máy chủ và quan hệ hợp lệ |
| Duyệt đúng nhưng worker dùng dữ liệu hiện tại | Nội dung có thể đã thay đổi | So khớp quyết định với snapshot hoặc phiên bản nội dung |
| Có transaction nhưng không kiểm soát tranh chấp | Nhiều luồng vẫn cùng tiêu thụ một quyền lợi | Dùng khóa, phiên bản hoặc cập nhật có điều kiện phù hợp |
| Chỉ dựa vào khóa idempotency | Khóa mới có thể tạo thêm tác động | Ràng buộc tính duy nhất hoặc ngân sách theo quyết định |
| Hash JSON rồi tin là đã duyệt | Hash không xác minh người duyệt và có thể thiếu trường | Bảo vệ bản ghi gốc, chuẩn hóa nội dung và kiểm tra thẩm quyền |
| Đổi policy rồi chạy worker tùy cache | Kết quả không nhất quán theo thời điểm | Định nghĩa phiên bản và quy tắc chuyển tiếp |
| Xóa quyết định sai để làm sạch dữ liệu | Mất bằng chứng và có thể tái dùng quyền lợi | Thu hồi hoặc điều chỉnh bằng thao tác có lịch sử |

## 15. Bài tập tự kiểm tra

### Bài 1: dữ liệu không bị sửa trái phép, vì sao quyết định vẫn sai?

Một nhân viên có quyền sửa hồ sơ và đã sửa số tiền sau phê duyệt qua API chính thức. Tất cả thay đổi đều có log. Worker đọc cờ đã duyệt và hoàn theo số tiền mới.

**Gợi ý trả lời:** quyền sửa dữ liệu không bao gồm quyền mở rộng nội dung người khác đã phê duyệt. Log giúp truy nguyên nhưng không ngăn tác động sai. Cần ràng buộc quyết định với nội dung, vô hiệu hiệu lực khi trường liên quan thay đổi và kiểm tra nguyên tử trước thực thi.

### Bài 2: cùng quyết định, hai khóa request

API dùng idempotency key và mỗi khóa chỉ tạo một lệnh. Khách gửi hai khóa khác nhau cùng tham chiếu một quyết định hoàn tiền một lần.

**Gợi ý trả lời:** idempotency theo khóa request chưa biểu diễn tính duy nhất của quyền lợi. Cần ràng buộc duy nhất theo quyết định ở nơi tạo lệnh, cùng transaction với việc tiêu thụ quyền và giữ ngân sách. Hai khóa khác nhau không mở rộng thẩm quyền của quyết định.

### Bài 3: người duyệt nghỉ việc sau khi phê duyệt

Hồ sơ được duyệt đúng quyền hôm qua. Hôm nay người duyệt bị thu hồi tài khoản, còn worker chưa thực thi.

**Gợi ý trả lời:** không suy ra đáp án chỉ từ việc tài khoản hiện đã khóa. Cần chính sách về hiệu lực quyết định lịch sử, thu hồi và điều kiện phải kiểm tra lại. Dù chọn tiếp tục công nhận hay yêu cầu duyệt lại, phải thực thi nhất quán và lưu được căn cứ.

## 16. Các điểm cần ghi nhớ

Tính toàn vẹn của quyết định đòi hỏi nhiều hơn việc bảo vệ một trường dữ liệu. Hệ thống phải giữ được mối liên hệ giữa người có thẩm quyền, dữ kiện đã đánh giá, chính sách đã áp dụng, nội dung được cho phép và tác động được tạo ra.

Một thiết kế có thể kiểm chứng cần chỉ ra nguồn dữ kiện đáng tin cậy, binding của quyết định, điều kiện hết hiệu lực và ranh giới thực thi nguyên tử. State machine, quyền theo đối tượng, transaction, idempotency và đối soát cùng phục vụ mục tiêu đó.

Câu hỏi kiểm tra cốt lõi là: **Hệ thống có thể chứng minh rằng tác động này chính là điều đã được cho phép, trên đúng đối tượng, với đúng điều kiện và số lần hay không?**
