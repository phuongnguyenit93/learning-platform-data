# Identity proofing levels — Các mức bảo đảm xác minh danh tính

## 1. Mục tiêu và phạm vi

Trong chương **Identity Proofing** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, xác minh danh tính giúp đánh giá người yêu cầu có thực sự gắn với danh tính được khai báo hay không. Bài toán trở nên quan trọng khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực và không còn hoàn tất được đường xác thực thông thường.

Một ảnh giấy tờ, một cuộc gọi hỗ trợ hay một kết quả so khớp khuôn mặt không tự đại diện cho cả quy trình. Cần biết hệ thống đã kiểm tra điều gì, bằng cách nào, dựa trên nguồn nào và kết quả được phép dùng để cấp quyền gì.

**Identity proofing levels** là các mức bảo đảm về kết quả xác minh danh tính. Bài sử dụng thuật ngữ **Identity Assurance Level — IAL** theo **NIST SP 800-63A-4** làm khung tham chiếu, rồi áp dụng vào thiết kế account recovery.

Mục tiêu sau bài học:

- Phân biệt IAL với mức xác thực và quyền nghiệp vụ.
- Hiểu ý nghĩa của IAL1, IAL2, IAL3 trong đúng phiên bản tiêu chuẩn.
- Nhận diện các bước phải có trước khi gắn nhãn một mức bảo đảm.
- Đánh giá mối liên hệ giữa người đã proofing và tài khoản đang cần khôi phục.
- Cấp quyền recovery có phạm vi và bảo vệ dữ liệu thu thập.

Các mô hình dữ liệu và tình huống trong bài là thiết kế minh họa. Chúng không tự chứng nhận một sản phẩm đạt IAL hay thay thế việc đối chiếu đầy đủ yêu cầu tiêu chuẩn.

## 2. Ba câu hỏi độc lập: danh tính, xác thực và quyền

### 2.1. IAL trả lời câu hỏi nào?

Identity proofing xem xét mối liên hệ giữa người yêu cầu và danh tính được khai báo. Chẳng hạn, người trình bằng chứng có thực sự gắn với danh tính mà bằng chứng mô tả không?

Nó khác với việc kiểm tra người đó có đang điều khiển một authenticator hợp lệ hay không. Nó cũng khác với việc quyết định người đó được đổi email recovery hoặc quản trị một tổ chức hay không.

| Khía cạnh | Câu hỏi chính | Ví dụ kết quả |
| --- | --- | --- |
| Identity proofing, IAL | Người yêu cầu gắn với danh tính được khai báo ở mức bảo đảm nào? | Một hồ sơ proofing đạt mức theo profile đã áp dụng |
| Authentication, AAL | Người đang tương tác chứng minh quyền kiểm soát authenticator như thế nào? | Một sự kiện xác thực được verifier chấp nhận |
| Federation, FAL | Thông tin xác thực liên kết được bảo vệ và chuyển tới bên nhận ra sao? | Assertion đáp ứng profile federation phù hợp |
| Authorization | Chủ thể được thực hiện hành động gì với tài nguyên nào? | Quyền đăng ký lại MFA cho đúng tài khoản |
| Risk assessment | Bối cảnh có dấu hiệu làm tăng hoặc giảm rủi ro nào? | Thiết bị mới cần kiểm tra bổ sung |

Ba trục IAL, AAL và FAL được phân biệt trong bộ hướng dẫn danh tính số của NIST; chúng không phải một thang điểm chung. [NIST SP 800-63-4 — Digital Identity Risk Management](https://pages.nist.gov/800-63-4/sp800-63/dirm/)

### 2.2. Không có phép suy tự động giữa các kết quả

Những suy luận sau không đủ căn cứ:

- “Đã dùng MFA nên danh tính đời thực đã được proofing.”
- “Đã đạt IAL2 nên session hiện tại chắc chắn là của người đó.”
- “Giấy tờ hợp lệ nên được đổi email của bất kỳ tài khoản cùng tên.”
- “Passkey mới đăng ký thành công nên quyền đăng ký nó đã được chứng minh.”
- “Điểm rủi ro thấp nên có thể bỏ một bước proofing bắt buộc.”

Trong recovery, cần kết hợp các quyết định đúng vai trò: proofing, liên kết với tài khoản, cấp quyền enrollment, xác thực tiếp theo và kiểm soát session.

## 3. Luôn ghi rõ phiên bản khi nói đến IAL

### 3.1. Điểm dễ nhầm giữa Revision 3 và Revision 4

Ở NIST SP 800-63A thuộc bộ Revision 3, IAL1 không yêu cầu liên kết với một danh tính đời thực cụ thể. Sang **SP 800-63A-4**, “không thực hiện identity proofing” được mô tả riêng; IAL1 đã có yêu cầu xác minh. [NIST SP 800-63A, Revision 3 — Identity Assurance Levels](https://pages.nist.gov/800-63-3/sp800-63a.html#sec2), [NIST SP 800-63A-4 — Identity Assurance Levels](https://pages.nist.gov/800-63-4/sp800-63a.html)

Vì vậy, câu “IAL1 chỉ là người dùng tự khai” không được dùng như mô tả cho IAL1 của Revision 4.

### 3.2. Hệ quả với hệ thống và dữ liệu cũ

Nếu database chỉ lưu:

~~~text
identity_level = IAL1
~~~

đội vận hành chưa biết nhãn đó có nghĩa gì. Nó có thể là nhãn từ phiên bản cũ, cách phân loại nội bộ hoặc một kết luận đúng theo profile mới.

Một kết quả cần có căn cứ diễn giải:

~~~text
framework = NIST_SP_800_63A
framework_revision = 4
achieved_level = IAL1
proofing_profile = profile_reference
completed_at = timestamp
result_reference = assessment_reference
~~~

Không nâng tất cả record IAL1 cũ thành IAL1 mới bằng một migration đổi chuỗi. Nếu chưa đủ bằng chứng về quy trình đã thực hiện, trạng thái cần thể hiện thiếu thông tin hoặc cần đánh giá theo chính sách.

Tương tự, nhãn “basic”, “advanced” hoặc “KYC tier 2” của một nhà cung cấp không tự tương đương IAL2.

## 4. Tổng quan các mức trong SP 800-63A-4

| Mức hoặc trạng thái | Ý nghĩa khái quát | Điều không nên suy ra |
| --- | --- | --- |
| Không thực hiện identity proofing | Chưa có kết luận proofing theo một IAL | Không có nghĩa tài khoản không thể có MFA |
| IAL1 | Có căn cứ về sự tồn tại của danh tính và một mức tin cậy về liên hệ với người yêu cầu | Không còn đồng nghĩa hoàn toàn tự khai |
| IAL2 | Bổ sung yêu cầu về bằng chứng, validation và verification để tăng khả năng chống mạo danh | Không bắt buộc mọi triển khai đều dùng selfie |
| IAL3 | Tăng yêu cầu, gồm proofing tại chỗ có nhân sự được đào tạo và thu thập sinh trắc học | Không phải chỉ thêm video call vào IAL2 |

Theo SP 800-63A-4, IAL1 có kiểm tra thuộc tính cốt lõi; IAL2 có nhiều đường verification, gồm đường không dùng sinh trắc học; IAL3 yêu cầu on-site attended proofing. Đây chỉ là tóm tắt định hướng. Để tuyên bố đạt mức, cần kiểm tra toàn bộ quy trình và các yêu cầu chung tương ứng. [NIST SP 800-63A-4 — Identity Assurance Level Requirements](https://pages.nist.gov/800-63-4/sp800-63a/ial/)

Bài không chuyển bảng này thành một checklist kiểu “một giấy tờ là IAL1, hai giấy tờ là IAL2”. Số tệp tải lên không tự thể hiện chất lượng bằng chứng hoặc việc người trình thật sự sở hữu danh tính.

### 4.1. IAL1: một kết luận proofing có điều kiện

Ở mức này, hệ thống vẫn cần thực hiện các bước của profile đã chọn. Chỉ gửi OTP tới email mới hoặc lưu họ tên do người dùng nhập chưa đủ để tự gắn nhãn IAL1 của Revision 4.

Khi dùng trong recovery, câu hỏi tiếp theo vẫn là: danh tính đã được proofing có liên hệ đáng tin với tài khoản nào? Proofing người yêu cầu thành công không tự trả lời câu hỏi đó.

### 4.2. IAL2: cần đánh giá đường thực hiện cụ thể

Không nên hard-code “IAL2 = giấy tờ cộng selfie”. Một nhà cung cấp có thể hỗ trợ các đường khác nhau, nhưng hệ thống tích hợp phải biết profile nào đã được áp dụng và kết quả nào thực sự đạt.

Nếu dịch vụ chỉ trả “document passed” mà chưa có kết quả verification hoặc các bước bắt buộc khác, ứng dụng không được tự tổng hợp thành IAL2 bằng suy đoán.

### 4.3. IAL3: không thể thay bằng một nhãn giao diện

Một nút “xác minh nâng cao” hoặc một nhân viên gọi video chưa đủ để kết luận đạt IAL3.

Đội thiết kế cần kiểm soát quy trình, nhân sự, môi trường, dữ liệu và việc chuyển kết quả sang bước cấp quyền. Chi phí cao hơn hay nhiều thao tác hơn không tự tạo mức bảo đảm cao hơn.

## 5. Những bước tạo thành kết quả proofing

### 5.1. Resolution, validation và verification

| Bước | Mục tiêu | Ví dụ câu hỏi |
| --- | --- | --- |
| Identity resolution | Phân biệt danh tính trong phạm vi phục vụ | Có đủ thuộc tính để phân biệt những người cùng tên không? |
| Evidence validation | Đánh giá bằng chứng có xác thực và hợp lệ theo quy trình không | Dữ liệu có bị sửa hoặc nguồn phát hành có được tin cậy không? |
| Attribute validation | Kiểm tra tính chính xác của thuộc tính | Thuộc tính có khớp nguồn có thẩm quyền hoặc đáng tin không? |
| Identity verification | Liên kết người đang tham gia với danh tính trong bằng chứng | Bằng chứng đã kiểm tra có thực sự thuộc người đang trình không? |
| Enrollment và binding | Thiết lập hồ sơ và liên kết phương tiện theo quyền đã có | Kết quả đang được gắn vào đúng hồ sơ và đúng context không? |

NIST phân biệt việc kiểm tra bằng chứng và thuộc tính với việc xác minh mối liên hệ giữa người trình và danh tính. Chất lượng bằng chứng được phân loại theo các đặc tính quy định, không theo đuôi tệp hay tên giấy tờ do client gửi. [NIST SP 800-63A-4 — Identity Proofing Overview](https://pages.nist.gov/800-63-4/sp800-63a/proofing/)

### 5.2. Vì sao một ảnh giấy tờ chưa đủ?

Một ảnh có thể:

- Chụp từ giấy tờ thật nhưng thuộc người khác.
- Là ảnh bị lấy từ một vụ lộ dữ liệu.
- Bị chỉnh sửa hoặc ghép.
- Có thuộc tính đúng nhưng không đủ phân biệt hai hồ sơ.
- Được gửi trong một case của tài khoản không có liên hệ với danh tính đó.

OCR đọc đúng chữ chỉ giải quyết việc trích xuất dữ liệu. Nó chưa chứng minh giấy tờ thật, người trình đúng hoặc quyền recovery đã đủ.

### 5.3. Phân loại bằng chứng không phải nhãn do người dùng chọn

Các thuật ngữ FAIR, STRONG và SUPERIOR trong tiêu chuẩn là những nhóm yêu cầu về bằng chứng. Không cho client chọn “SUPERIOR” rồi xem đó là thuộc tính đã xác minh.

Cũng không đếm hai ảnh mặt trước và mặt sau của cùng một giấy tờ thành hai bằng chứng độc lập chỉ vì chúng là hai upload.

Hệ thống phải lưu kết quả đánh giá của quy trình có thẩm quyền, cùng thông tin đủ để giải thích quyết định trong phạm vi được phép.

## 6. Phương thức thực hiện không đồng nhất với mức bảo đảm

### 6.1. Các chiều cần phân biệt

Một quy trình có thể được mô tả theo:

- Từ xa hay tại chỗ.
- Có hay không có nhân sự tham dự.
- Dùng bằng chứng vật lý hay số.
- Có hay không có đối sánh sinh trắc học.
- Cách kiểm tra nguồn phát hành và thuộc tính.
- Cách bảo vệ việc chụp, truyền và xử lý dữ liệu.

Những chiều này mô tả cách thực hiện. Chỉ khi toàn bộ điều kiện tương ứng được đáp ứng mới có căn cứ kết luận mức bảo đảm.

### 6.2. Có người xem không tự loại bỏ rủi ro

Nhân viên có thể bị đánh lừa bằng bằng chứng giả, dữ liệu đánh cắp, câu chuyện khẩn cấp hoặc sai sót đối chiếu. Quy trình có người tham gia vẫn cần hướng dẫn, quyền hạn, dữ liệu và kiểm soát phù hợp.

Ngược lại, một quy trình tự động không tự là mức thấp chỉ vì không có người gọi video. Cần xét profile và kết quả thực tế.

### 6.3. Sinh trắc học là một thành phần, không phải kết luận tổng quát

So khớp khuôn mặt giải quyết một câu hỏi cụ thể trong quy trình. Nó chưa tự chứng minh nguồn ảnh đáng tin, dữ liệu đầu vào không bị thay hoặc tài khoản cần recovery thuộc danh tính đó.

Khi sử dụng chụp từ xa, cần xét tấn công chèn nội dung, trình ảnh hoặc video giả, việc chuyển dữ liệu giữa các thành phần và cách xử lý các kết quả không chắc chắn.

Các yêu cầu chung của NIST có nội dung bảo vệ quy trình proofing, bao gồm các rủi ro đối với thu thập và xử lý dữ liệu từ xa. [NIST SP 800-63A-4 — General Requirements](https://pages.nist.gov/800-63-4/sp800-63a/ial-general/)

Không ép mọi người dùng qua một phương thức không phù hợp chỉ để giữ một nhãn “cao nhất”. Cần có đường được hỗ trợ cho những trường hợp không hoàn tất được.

## 7. Chọn mức theo hậu quả của quyết định recovery

### 7.1. Xác định điều đang cần tin cậy

Trong account recovery, cần tách ít nhất bốn câu hỏi:

~~~text
1. Danh tính người yêu cầu đã được proofing ở mức nào?
2. Danh tính đó có liên hệ được chấp nhận với tài khoản đang xét không?
3. Bằng chứng recovery nào khác còn được sử dụng?
4. Quyền cụ thể nào có thể cấp sau quyết định?
~~~

Chọn mức chỉ vì hệ thống “có sẵn API selfie” là bắt đầu từ công nghệ thay vì mục tiêu bảo vệ.

### 7.2. Ma trận sản phẩm minh họa

| Bối cảnh | Vấn đề cần giải quyết | Hướng chính sách minh họa |
| --- | --- | --- |
| Người dùng còn khóa dự phòng hợp lệ | Có thể xác thực bằng đường đã thiết lập | Không tự yêu cầu giấy tờ nếu quy trình phù hợp đã đủ |
| Mất toàn bộ MFA nhưng có bằng chứng recovery | Đánh giá đường recovery đã định nghĩa | Không mặc định proofing đời thực là bước bắt buộc |
| Tài khoản đã gắn danh tính theo profile rõ ràng | Có dữ liệu để đối chiếu lại | Xác định mức và các bước cần lặp theo chính sách |
| Tài khoản bí danh chưa có liên kết danh tính | Chưa có căn cứ nối giấy tờ với tài khoản | Không cấp quyền chỉ từ tên trên giấy tờ |
| Tài khoản quản trị có hậu quả lớn | Cần kiểm soát quyền quản trị và rủi ro tổ chức | Kết hợp recovery, phân quyền và phê duyệt phù hợp |
| Tài khoản bị thay thông tin trái phép | Hồ sơ hiện tại có thể đã bị sửa | Xét nguồn liên kết và lịch sử được tin cậy |

Các hàng này không gán IAL bắt buộc cho một loại tài khoản. Tổ chức phải lựa chọn theo yêu cầu áp dụng và phân tích rủi ro, rồi triển khai đầy đủ profile tương ứng.

### 7.3. Mức yêu cầu và mức đã đạt phải là hai trường khác nhau

Ví dụ:

~~~text
required_identity_level = IAL2
proofing_status = IN_PROGRESS
achieved_identity_level = null
~~~

Không điền mức đã đạt bằng mức được yêu cầu ngay khi tạo case. Tương tự, “nhà cung cấp hỗ trợ IAL2” khác với “case cụ thể này đã hoàn tất quy trình IAL2 được chấp nhận”.

Nếu bằng chứng thiếu, verifier lỗi hoặc hồ sơ đang chờ review, trạng thái phải thể hiện điều đó.

## 8. Liên kết người đã proofing với tài khoản cũ

### 8.1. Đây là một quyết định bảo mật riêng

Giả sử người yêu cầu đã chứng minh mình là Nguyễn Văn A. Điều đó chưa cho biết họ có quyền với tài khoản username “nguyenvana” hay không.

Một hệ thống có thể có nhiều người cùng tên. Tên hiển thị, email liên lạc hoặc trường địa chỉ trong tài khoản cũng có thể tự khai hoặc đã bị kẻ tấn công thay.

Mối liên hệ cần đến từ dữ kiện được thiết lập hợp lệ, có nguồn gốc và đủ độ phân biệt cho bối cảnh.

### 8.2. Dữ liệu nối kết có thể đã thay đổi

Cần xác định:

- Thuộc tính nào được proofing từ trước và theo profile nào.
- Thuộc tính nào chỉ là dữ liệu tự khai.
- Những thay đổi nào diễn ra trong giai đoạn nghi bị chiếm.
- Kết quả proofing mới có đang được áp dụng cho đúng hồ sơ không.
- Có xung đột, nhiều hồ sơ hoặc thiếu căn cứ đối chiếu không.

Không chọn tự động tài khoản đầu tiên có tên hoặc ngày sinh trùng. Cũng không công khai toàn bộ dữ liệu cũ để người yêu cầu học cách trả lời đúng.

### 8.3. Tài khoản chưa được proofing không tự có đường recovery bằng giấy tờ

Một diễn đàn có thể chỉ yêu cầu username và email khi đăng ký. Nhiều năm sau, người yêu cầu trình giấy tờ thật và nói mình là chủ tài khoản.

Ngay cả khi proofing xác nhận danh tính đời thực, vẫn thiếu mối liên hệ đã được thiết lập với tài khoản bí danh. Sản phẩm cần căn cứ recovery khác hoặc quy trình được thiết kế cho tình huống đó.

Đây là giới hạn của dữ liệu và chính sách, không phải lỗi mà việc tăng IAL của người yêu cầu luôn sửa được.

## 9. Dùng kết quả proofing trong luồng recovery

### 9.1. Kết quả proofing là đầu vào, chưa phải lệnh thay đổi tài khoản

NIST mô tả việc lặp lại các phần của proofing như một trong những cách recovery, cùng các phương pháp khác và điều kiện tương ứng. Không phải mọi quy trình recovery đều cần thu thập giấy tờ mới. [NIST SP 800-63B-4 — Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b/events/#account-recovery)

Một luồng minh họa:

~~~mermaid
flowchart TD
    A[Yêu cầu recovery] --> B[Chọn policy và mức cần thiết]
    B --> C[Thu thập và kiểm tra theo profile]
    C --> D{Đạt điều kiện proofing?}
    D -->|Chưa| E[Bổ sung, review hoặc kết thúc]
    D -->|Đạt| F[Kiểm tra liên kết với tài khoản]
    F --> G{Đủ căn cứ recovery?}
    G -->|Chưa| E
    G -->|Đủ| H[Cấp quyền hạn hẹp theo mục đích]
    H --> I[Liên kết phương tiện thay thế]
    I --> J[Kiểm soát session và hoàn tất]
~~~

Không có cạnh đi trực tiếp từ “ảnh giấy tờ hợp lệ” đến “đổi toàn bộ thông tin tài khoản”.

### 9.2. Giới hạn quyền sau quyết định

Một quyết định có thể chỉ cho phép:

~~~text
purpose = REENROLL_MFA
account = A
recovery_case = R1
allowed_context = C1
expires_at = thời hạn theo policy
single_use_for_enrollment = true
~~~

Quyền đó chưa cho đổi recovery email, xuất dữ liệu, tạo API token hoặc chuyển quyền sở hữu tổ chức.

Nếu cần những quyền khác, phải có quyết định và bằng chứng phù hợp. Không dùng một cờ global “identity_verified” để bỏ mọi step-up về sau.

### 9.3. Proofing xong vẫn cần xử lý authenticator và session

Liên kết phương tiện mới cần đúng quyền đã cấp và đúng context. Phương tiện mới không được tự hợp thức hóa quyền đăng ký của chính nó.

Sau recovery, phải xác định phạm vi thu hồi session, refresh token, credential trái phép và link recovery còn mở. Một hồ sơ proofing đạt mức cao không tự khiến token của kẻ tấn công hết hiệu lực.

Khi người dùng quay lại hành động ban đầu, server vẫn phải kiểm tra quyền nghiệp vụ, target, chính sách hiện hành và trạng thái session.

## 10. Lưu kết quả đủ để giải thích mức bảo đảm

### 10.1. Mô hình dữ liệu khái niệm

~~~text
ProofingAssessment
    assessment_id
    recovery_case_id
    applicant_reference
    intended_account_reference
    framework
    framework_revision
    required_level
    achieved_level
    profile_id
    proofing_type
    status
    validation_result_references
    verification_result_reference
    account_linkage_decision_reference
    provider_reference
    policy_version
    completed_at
    invalidated_at
~~~

Tham chiếu là để truy vết kết quả có kiểm soát, không phải yêu cầu sao chép toàn bộ giấy tờ hay mẫu sinh trắc học vào record ứng dụng.

Cần phân biệt thời điểm proofing với thời điểm người dùng đăng nhập gần nhất. Một bằng chứng về danh tính trong quá khứ không tự chứng minh ai đang giữ session hôm nay.

### 10.2. Không để client tự khai mức đã đạt

Request như sau chỉ là dữ liệu chưa được tin cậy:

~~~json
{
  "case_id": "R1",
  "achieved_level": "IAL3",
  "document_checked": true
}
~~~

Backend phải nhận kết quả từ thành phần có thẩm quyền, kiểm tra tính xác thực, liên kết với case, người yêu cầu và profile. Callback của nhà cung cấp cũng cần chống gửi lại, kết quả trễ và việc tráo case.

Một ID giao dịch khó đoán không thay thế kiểm tra chữ ký hoặc cơ chế xác thực callback của tích hợp.

### 10.3. Không đồng nhất thiếu kết quả với không đạt

Các trạng thái nên phân biệt được:

~~~text
IN_PROGRESS
PASSED
NOT_MET
REVIEW_REQUIRED
DEPENDENCY_UNAVAILABLE
EXPIRED
INVALIDATED
~~~

Verifier timeout chưa chứng minh người yêu cầu gian lận. Tuy nhiên, khi chưa có kết quả bắt buộc, quyền recovery vẫn chưa được cấp.

Không biến outage thành lý do tự hạ mức yêu cầu hoặc bỏ phần verification.

## 11. Mã giả ra quyết định

~~~text
evaluateRecoveryProofing(caller, caseId, assessmentReference):
    case = loadAuthorizedRecoveryCase(caller, caseId)
    requireCaseCurrentAndUsable(case)

    policy = resolveCurrentRecoveryPolicy(case)
    assessment = loadTrustedAssessment(assessmentReference)

    requireAssessmentBoundToCaseAndApplicant(assessment, case)
    requireAcceptedFrameworkRevisionAndProfile(assessment, policy)
    requireAssessmentCompletedSuccessfully(assessment)
    requireRequiredLevelMetUnderAcceptedProfile(assessment, policy)

    linkage = evaluateAccountLinkage(
        assessment, trustedAccountHistory(case.account)
    )
    requireLinkageAccepted(linkage)

    requireOtherRecoveryConditionsMet(case, policy)
    recheckSecurityStateAndCaseGeneration(case)

    atomicallyRecordDecisionAndIssueScopedRecoveryGrant(
        account = case.account,
        case = case,
        purpose = policy.allowedRecoveryPurpose,
        policyVersion = policy.version
    )
~~~

Đây là mã giả về trách nhiệm, không phải hàm production đầy đủ.

Không so sánh mức bằng thứ tự chữ cái của chuỗi “IAL1”, “IAL2”, “IAL3” mà bỏ qua framework, revision và profile. Quan hệ chấp nhận giữa các kết quả cần do chính sách xác định trong cùng khung yêu cầu được hiểu rõ.

Nếu policy, account linkage hoặc trạng thái bảo mật thay đổi trong lúc chờ nhà cung cấp, phải đánh giá lại trước khi cấp quyền có tác dụng. Một callback cũ không được làm sống lại case đã hủy.

## 12. Bảo vệ dữ liệu và khả năng tiếp cận

### 12.1. Mức cao hơn không phải lý do thu thập mọi thứ

Dữ liệu proofing có thể nhạy cảm và khó thay thế nếu bị lộ. Cần xác định rõ:

- Dữ liệu nào thực sự cần cho profile và mục đích.
- Thành phần nào được phép nhận hoặc xem.
- Dữ liệu thô, kết quả và audit được lưu trong bao lâu.
- Cách xóa, hạn chế truy cập và xử lý sự cố.
- Những gì cần thông báo cho người tham gia.

Không mặc định đưa ảnh giấy tờ hoặc sinh trắc học vào log, ticket hỗ trợ hay dữ liệu phân tích hành vi.

Đối với triển khai có yêu cầu lưu một loại dữ liệu theo profile áp dụng, cần thực hiện đúng yêu cầu đó cùng cơ chế bảo vệ; “tối thiểu hóa” không có nghĩa tự bỏ bước bắt buộc rồi vẫn tuyên bố đạt mức.

### 12.2. Cần đường xử lý người dùng không hoàn tất được

Người dùng có thể không có loại giấy tờ được hỗ trợ, camera phù hợp, kết nối ổn định hoặc khả năng dùng một phương thức nhất định.

Sản phẩm cần cung cấp hướng dẫn và các đường thay thế được chính sách cho phép. Một đường hỗ trợ cần có căn cứ và thẩm quyền, thay vì trở thành nút hạ yêu cầu tùy ý.

Lỗi đối sánh hoặc thiếu dữ liệu chưa đủ để gắn nhãn người dùng gian lận. Cần lưu đúng kết luận mà quy trình thực sự hỗ trợ.

### 12.3. Cân bằng khả năng bảo vệ và gánh nặng thu thập

Buộc mọi lần reset password đều proofing ở mức cao có thể làm tăng chi phí, dữ liệu nhạy cảm và tỷ lệ người dùng không thể hoàn tất mà không tương ứng với rủi ro cần giải quyết.

Ngược lại, dùng một hình thức kiểm tra sơ sài cho mọi quyết định chiếm quyền tài khoản có thể để lại đường mạo danh.

Mức cần dùng phải đến từ yêu cầu và phân tích rủi ro. Trải nghiệm và khả năng tiếp cận được cải thiện trong tập các phương án vẫn đáp ứng yêu cầu.

## 13. Các ví dụ áp dụng

### 13.1. Tài khoản bí danh và giấy tờ thật

An mất email và TOTP của tài khoản “blue-river”. An gửi giấy tờ thật có tên pháp lý.

Quy trình proofing có thể xác nhận danh tính An, nhưng nếu tài khoản chưa từng liên kết với danh tính này, hệ thống chưa đủ căn cứ cấp quyền tài khoản chỉ vì giấy tờ đạt một mức nhất định.

Cần xét bằng chứng recovery được hỗ trợ và mối liên hệ đáng tin khác. Tăng chất lượng ảnh hoặc thêm selfie không tự tạo lịch sử liên kết còn thiếu.

### 13.2. Hồ sơ đã được proofing, nhưng session bị chiếm

Bình từng hoàn tất một profile proofing được chấp nhận. Hiện kẻ tấn công giữ session và muốn thêm passkey.

Trường “identity level” của tài khoản mô tả một kết quả danh tính trước đó, không xác minh người đang gửi request hiện tại. Hành động thêm passkey vẫn cần quyền và bằng chứng hiện hành.

### 13.3. Nhà cung cấp trả một bước thành công

Nhà cung cấp báo ảnh giấy tờ của Chi vượt kiểm tra chất lượng và OCR. Backend không được gán IAL2 nếu đó chỉ là kết quả tiền xử lý.

Ứng dụng cần hợp đồng kết quả rõ: trạng thái toàn bộ assessment, profile, liên kết case và những điều kiện còn thiếu. Tên một API chứa chữ “verify” không quyết định mức bảo đảm.

### 13.4. Đã đạt yêu cầu proofing nhưng chưa đủ recovery

Dũng đạt yêu cầu proofing của case, nhưng liên kết với tài khoản có xung đột và hồ sơ còn một điều kiện review.

Hệ thống giữ case ở trạng thái phù hợp, không cấp grant enrollment sớm. “Proofing passed” và “recovery approved” là hai quyết định có ý nghĩa khác nhau.

## 14. Tình huống cần kiểm chứng khi triển khai

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Record chỉ có IAL1 mà không có revision | Không tự diễn giải thành kết quả theo Revision 4 |
| Client gửi achieved_level | Không tin làm kết quả proofing |
| Nhà cung cấp chỉ xác nhận OCR | Không tự gắn IAL |
| Tài khoản có MFA nhưng chưa proofing | Không suy ra mức danh tính |
| Tài khoản đã proofing nhưng session bị nghi chiếm | Vẫn kiểm tra bằng chứng và quyền hiện hành |
| Hai ảnh của cùng giấy tờ | Không tự đếm thành hai bằng chứng độc lập |
| Người cùng tên yêu cầu recovery | Không chọn account chỉ bằng tên |
| Giấy tờ thật nhưng chưa có liên kết với tài khoản bí danh | Không tự cấp quyền tài khoản |
| Quy trình chỉ có video call | Không tự gọi IAL3 |
| Verification hoặc validation còn thiếu | Chưa kết luận hoàn tất mức yêu cầu |
| Callback thuộc case khác | Bị từ chối theo liên kết context |
| Callback đến sau khi case hết hạn | Không làm case sống lại |
| Nhà cung cấp không khả dụng | Không mặc định đạt hoặc tự hạ mức |
| Grant chỉ cho đăng ký lại MFA | Không dùng để xuất dữ liệu hay đổi email tùy ý |
| Chính sách thay đổi trong lúc proofing | Kiểm tra lại trước quyết định có tác dụng |
| Session và token cũ vẫn còn hiệu lực | Không tuyên bố recovery đã loại toàn bộ quyền truy cập của kẻ tấn công |
| Kiểm tra log và ticket | Không có dữ liệu proofing nhạy cảm ngoài phạm vi được phép |

Bảng là tiêu chí thiết kế cho đội triển khai, không phải xác nhận một hệ thống cụ thể đã vượt kiểm thử.

## 15. Những điểm cần ghi nhớ

- Ghi rõ framework và revision khi sử dụng IAL.
- IAL1 của SP 800-63A-4 đã có yêu cầu proofing; không đồng nhất với mô tả cũ của Revision 3.
- IAL, AAL, FAL và phân quyền giải quyết những câu hỏi khác nhau.
- Mức bảo đảm thuộc toàn bộ quy trình được chấp nhận, không thuộc một ảnh giấy tờ hoặc một điểm so khớp.
- Kết quả proofing phải được nối với đúng tài khoản bằng căn cứ phù hợp.
- Quyền recovery cần đúng mục đích, có thời hạn và kiểm tra tại server.
- Thu thập dữ liệu và hỗ trợ người dùng phải đi cùng mục tiêu bảo vệ và yêu cầu áp dụng.
