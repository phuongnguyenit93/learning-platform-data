# Access Transparency và Access Approval

Trong môi trường Google Cloud, dữ liệu của tổ chức được vận hành trên hạ tầng do Google quản lý. Có những tình huống nhân viên Google cần truy cập nội dung khách hàng để xử lý yêu cầu hỗ trợ, điều tra sự cố hoặc duy trì dịch vụ. Với hệ thống chứa dữ liệu nhạy cảm, tổ chức cần biết khi nào hoạt động truy cập như vậy diễn ra và, trong những trường hợp được hỗ trợ, có quyền xem xét trước khi truy cập được thực hiện.

Google Cloud cung cấp hai cơ chế bổ sung cho nhau: **Access Transparency** ghi lại hoạt động truy cập nội dung khách hàng của nhân viên Google; **Access Approval** cho phép tổ chức phê duyệt hoặc từ chối một số yêu cầu truy cập trước khi nhân viên Google thực hiện. Khi kết hợp hai cơ chế với IAM, Cloud Logging và quy trình ứng phó sự cố, đội bảo mật có thể tăng khả năng giám sát và chứng minh việc kiểm soát dữ liệu.

## 1. Access Transparency và Access Approval giải quyết hai câu hỏi khác nhau

| Cơ chế | Câu hỏi cần trả lời | Cách hoạt động |
| --- | --- | --- |
| Access Transparency | Nhân viên Google đã truy cập nội dung khách hàng khi nào, vì lý do gì và liên quan đến tài nguyên nào? | Tạo log về các hoạt động truy cập thuộc phạm vi được hỗ trợ; tổ chức tra cứu và lưu giữ log trong Cloud Logging |
| Access Approval | Tổ chức có đồng ý cho nhân viên Google thực hiện yêu cầu truy cập này không? | Gửi yêu cầu để người có thẩm quyền xem xét, phê duyệt hoặc từ chối trước khi truy cập thuộc phạm vi kiểm soát được thực hiện |

Access Transparency tập trung vào khả năng quan sát và kiểm toán. Access Approval tập trung vào quyết định cho phép truy cập. Access Approval không thay thế log kiểm toán; Access Transparency cũng không tự ngăn một hoạt động truy cập. Triển khai cả hai giúp tổ chức vừa xem được hoạt động đã xảy ra, vừa kiểm soát trước các yêu cầu thuộc phạm vi Access Approval.

Hai cơ chế này nói về việc nhân viên Google truy cập **nội dung khách hàng** trong quá trình vận hành dịch vụ. Chúng không thay thế IAM của tổ chức, không quản lý quyền truy cập của nhân viên nội bộ vào project, và không cấp quyền cho ứng dụng đọc dữ liệu. Những luồng truy cập đó vẫn phải được kiểm soát bằng IAM, Cloud Audit Logs và chính sách bảo mật tương ứng.

## 2. Access Transparency ghi nhận hoạt động truy cập

Access Transparency cung cấp các log mô tả hoạt động truy cập nội dung khách hàng do nhân viên Google thực hiện trong các dịch vụ Google Cloud được hỗ trợ. Log được đưa vào Cloud Logging dưới loại log Access Transparency, giúp đội vận hành có thể tra cứu, tạo bộ lọc, thiết lập cảnh báo và chuyển tiếp dữ liệu kiểm toán đến hệ thống lưu trữ hoặc SIEM.

Một bản ghi có thể cung cấp các thông tin như:

- **Danh tính thực hiện:** thông tin nhận diện nhân viên hoặc danh tính phía Google được ghi trong sự kiện.
- **Thời điểm:** thời gian hoạt động được ghi nhận.
- **Tài nguyên liên quan:** project, dịch vụ hoặc tài nguyên có nội dung được truy cập.
- **Thao tác:** phương thức hoặc hoạt động truy cập được mô tả trong log.
- **Lý do truy cập:** ngữ cảnh giải thích vì sao hoạt động được thực hiện, chẳng hạn xử lý yêu cầu hỗ trợ hoặc vận hành dịch vụ.
- **Thông tin bổ sung:** mã hoạt động, thông tin yêu cầu hoặc trường metadata khác tùy dịch vụ và loại sự kiện.

Không phải mọi thao tác của nhân viên Google trên mọi sản phẩm đều xuất hiện trong Access Transparency. Phạm vi ghi nhận phụ thuộc dịch vụ, loại nội dung và điều kiện áp dụng của sản phẩm. Vì vậy, trước khi dùng log làm bằng chứng tuân thủ, cần xác nhận dịch vụ đang sử dụng nằm trong danh sách hỗ trợ và tổ chức đã đáp ứng điều kiện kích hoạt tương ứng.

### Tra cứu log trong Cloud Logging

Trong Logs Explorer, có thể lọc loại log Access Transparency bằng biểu thức:

~~~text
log_id("cloudaudit.googleapis.com/access_transparency")
~~~

Để tập trung vào một project cụ thể, chọn đúng project trong phạm vi truy vấn hoặc bổ sung điều kiện tài nguyên phù hợp. Khi điều tra một sự kiện, đọc toàn bộ bản ghi thay vì chỉ dựa vào một trường riêng lẻ. Đối chiếu thời điểm, tài nguyên, lý do truy cập và mã yêu cầu với ticket hỗ trợ hoặc hồ sơ sự cố nội bộ.

Ví dụ, đội vận hành nhận được yêu cầu hỗ trợ về lỗi truy vấn BigQuery. Sau khi sự cố được xử lý, đội bảo mật tìm log Access Transparency trong khoảng thời gian tương ứng, xác định tài nguyên liên quan và kiểm tra lý do truy cập có khớp với ticket hỗ trợ đã mở hay không. Nếu log không khớp với phạm vi công việc dự kiến, đội bảo mật có thể mở quy trình điều tra và yêu cầu Google hoặc nhóm hỗ trợ làm rõ.

### Lưu giữ và giám sát log

Log có giá trị khi được bảo vệ và lưu giữ theo yêu cầu kiểm toán. Tổ chức nên:

1. Cấp quyền xem log cho nhóm bảo mật và kiểm toán theo nguyên tắc tối thiểu.
2. Thiết lập log sink để chuyển log đến nơi lưu trữ hoặc hệ thống phân tích tập trung khi cần thời hạn lưu giữ dài hơn.
3. Kiểm soát quyền sửa cấu hình sink, quyền xóa log và quyền truy cập kho lưu trữ.
4. Tạo bộ lọc hoặc cảnh báo cho sự kiện có tài nguyên nhạy cảm, lý do truy cập không mong đợi hoặc hoạt động ngoài khung vận hành thông thường.
5. Định kỳ kiểm tra khả năng truy vấn, tính đầy đủ của phạm vi log và quy trình xử lý cảnh báo.

Access Transparency giúp tăng khả năng truy vết nhưng không thay thế quy trình quản lý sự cố. Đội bảo mật vẫn cần xác định người chịu trách nhiệm xem xét log, thời gian phản hồi và cách lưu bằng chứng.

## 3. Access Approval kiểm soát yêu cầu trước khi truy cập

Access Approval cho phép tổ chức yêu cầu phê duyệt trước đối với những hoạt động truy cập nội dung khách hàng của nhân viên Google thuộc phạm vi dịch vụ được hỗ trợ. Khi phát sinh yêu cầu, người phê duyệt nhận thông tin để xem xét rồi quyết định chấp thuận hoặc từ chối.

Một yêu cầu có thể cung cấp ngữ cảnh như:

- Lý do nhân viên Google cần truy cập.
- Tài nguyên hoặc phạm vi dữ liệu liên quan.
- Dịch vụ và thao tác dự kiến.
- Thời hạn hoặc khoảng thời gian yêu cầu có hiệu lực.
- Thông tin hỗ trợ hoặc mã tham chiếu liên quan, nếu có.

Người phê duyệt cần đánh giá yêu cầu dựa trên ngữ cảnh vận hành và chính sách của tổ chức. Việc phê duyệt phải có chủ đích, có người chịu trách nhiệm và có thể kiểm tra lại. Nếu yêu cầu không rõ mục đích, không khớp ticket hoặc vượt quá phạm vi hỗ trợ đã thống nhất, người phê duyệt nên từ chối hoặc yêu cầu làm rõ theo quy trình.

Quyết định phê duyệt chỉ áp dụng trong phạm vi yêu cầu và điều kiện được nêu. Không xem một lần phê duyệt là sự cho phép chung cho mọi lần truy cập trong tương lai. Những ngoại lệ được quy định cho trường hợp khẩn cấp, yêu cầu pháp lý hoặc hoạt động vận hành đặc biệt có thể được xử lý theo cơ chế riêng của Google; cần đọc điều kiện của từng dịch vụ và không giả định rằng mọi trường hợp đều có thể bị chặn bằng Access Approval.

## 4. Luồng phối hợp giữa hai cơ chế

Sơ đồ sau thể hiện luồng điển hình khi một yêu cầu truy cập cần được phê duyệt:

~~~mermaid
flowchart TD
  A["Nhân viên Google cần truy cập nội dung khách hàng"] --> B["Access Approval tạo yêu cầu"]
  B --> C["Thông báo đến nhóm phê duyệt của tổ chức"]
  C --> D{"Người phê duyệt xem xét"}
  D -->|"Từ chối"| E["Yêu cầu bị từ chối"]
  D -->|"Chấp thuận"| F["Truy cập được phép theo phạm vi yêu cầu"]
  F --> G["Access Transparency ghi nhận hoạt động thuộc phạm vi hỗ trợ"]
  G --> H["Cloud Logging, cảnh báo và kiểm toán"]
  E --> I["Lưu quyết định và hồ sơ xử lý"]
  H --> I
~~~

Luồng thực tế phụ thuộc dịch vụ và loại yêu cầu. Access Approval xử lý quyết định trước khi truy cập được thực hiện theo cơ chế được hỗ trợ; Access Transparency cung cấp bằng chứng về hoạt động truy cập đã diễn ra. Nhóm bảo mật nên liên kết yêu cầu phê duyệt, quyết định và log tương ứng bằng mã yêu cầu, thời gian và tài nguyên để tạo thành hồ sơ kiểm toán đầy đủ.

## 5. Ví dụ: bảo vệ dữ liệu khách hàng trong BigQuery

Giả sử công ty thương mại điện tử lưu dữ liệu đơn hàng và thông tin khách hàng trong BigQuery. Khi có lỗi dịch vụ, nhóm hỗ trợ Google đề nghị kiểm tra một tập dữ liệu cụ thể.

Tổ chức có thể xử lý như sau:

1. Nhóm hỗ trợ cung cấp yêu cầu truy cập và lý do cần kiểm tra dữ liệu.
2. Access Approval gửi yêu cầu đến nhóm được phân công phê duyệt.
3. Người phê duyệt đối chiếu project, dataset, mục đích và ticket sự cố. Nếu phạm vi phù hợp, họ chấp thuận; nếu yêu cầu quá rộng hoặc thiếu căn cứ, họ từ chối hoặc yêu cầu làm rõ.
4. Sau khi hoạt động hỗ trợ diễn ra, đội bảo mật tìm log Access Transparency trong Cloud Logging.
5. Đội bảo mật so sánh log với yêu cầu đã được phê duyệt, ghi nhận sai lệch nếu có và lưu hồ sơ theo chính sách kiểm toán.

Trong ví dụ này, Access Approval kiểm soát yêu cầu truy cập của nhân viên Google; IAM và chính sách BigQuery vẫn kiểm soát người dùng nội bộ và service account của ứng dụng. Access Transparency cung cấp dấu vết để đội bảo mật xác minh hoạt động đã xảy ra.

## 6. Triển khai theo phạm vi tổ chức

Trước khi cấu hình, cần xác định dịch vụ và loại dữ liệu cần bảo vệ. Access Transparency và Access Approval không có phạm vi hỗ trợ giống nhau trên mọi sản phẩm Google Cloud. Khả năng sử dụng còn phụ thuộc điều kiện dịch vụ, cấu hình tổ chức và các yêu cầu về gói hỗ trợ hoặc chương trình tuân thủ áp dụng. Hãy kiểm tra tài liệu hiện hành của từng dịch vụ trước khi đưa tính năng vào cam kết kiểm soát.

Một quy trình triển khai có thể gồm các bước:

1. **Xác định phạm vi:** liệt kê project, dịch vụ và loại dữ liệu cần kiểm soát; xác nhận dịch vụ hỗ trợ Access Transparency và Access Approval.
2. **Xác nhận điều kiện:** kiểm tra điều kiện về tổ chức, dịch vụ, khu vực, gói hỗ trợ hoặc chương trình tuân thủ theo tài liệu Google Cloud hiện hành.
3. **Bật và cấu hình tính năng:** cấu hình Access Transparency theo phạm vi tổ chức được hỗ trợ; bật Access Approval API và thiết lập phạm vi áp dụng, thông báo theo hướng dẫn của sản phẩm.
4. **Phân công người phê duyệt:** xác định nhóm bảo mật, chủ sở hữu dữ liệu hoặc nhóm tuân thủ chịu trách nhiệm. Chuẩn bị người thay thế để yêu cầu không bị bỏ sót khi người chính vắng mặt.
5. **Thiết lập giám sát:** bảo đảm log có thể được truy vấn, thiết lập log sink và cảnh báo, đồng thời kiểm soát quyền truy cập dữ liệu kiểm toán.
6. **Kiểm thử quy trình:** dùng môi trường hoặc tình huống thử nghiệm phù hợp để xác minh thông báo, quyền phê duyệt, quyết định từ chối và khả năng tra cứu log.
7. **Đưa vào vận hành:** công bố hướng dẫn cho người phê duyệt, thời hạn xử lý, quy trình leo thang và cách lưu bằng chứng.

Có thể bật Access Approval API trong project bằng Google Cloud CLI:

~~~bash
gcloud services enable accessapproval.googleapis.com \
  --project=PROJECT_ID
~~~

Thay PROJECT_ID bằng project dùng để cấu hình API. Việc bật API chỉ là một bước chuẩn bị; tổ chức vẫn cần cấu hình Access Approval ở phạm vi tài nguyên thích hợp, thiết lập thông báo, phân quyền người phê duyệt và kiểm tra dịch vụ mục tiêu có được hỗ trợ hay không.

## 7. Phân quyền người cấu hình và người phê duyệt

Quyền cấu hình Access Approval và quyền quyết định một yêu cầu nên được phân công rõ ràng. Google Cloud cung cấp các predefined IAM role dành cho Access Approval:

| IAM role | Mục đích | Nhóm thường đảm nhiệm |
| --- | --- | --- |
| **roles/accessapproval.configEditor** | Quản lý cấu hình Access Approval | Nhóm nền tảng hoặc quản trị bảo mật |
| **roles/accessapproval.approver** | Xem xét và quyết định yêu cầu thuộc phạm vi được cấp | Nhóm bảo mật, chủ sở hữu dữ liệu hoặc người được ủy quyền |
| **roles/accessapproval.viewer** | Xem cấu hình và thông tin yêu cầu mà không thực hiện quyền quản trị hoặc phê duyệt | Nhóm kiểm toán hoặc giám sát |

Hãy cấp role ở phạm vi nhỏ nhất đáp ứng nhiệm vụ và kiểm tra quyền kế thừa từ organization, folder hoặc project. Người cấu hình nên được tách khỏi nhóm phê duyệt khi quy trình tuân thủ yêu cầu kiểm soát chéo. Không cấp quyền approver cho mọi quản trị viên project chỉ để tiện xử lý thông báo.

Đối với Access Transparency, cấp quyền đọc log cho nhóm cần giám sát và kiểm toán. Tách quyền xem log khỏi quyền thay đổi cấu hình log sink hoặc xóa dữ liệu lưu trữ để giảm nguy cơ một người có thể vừa thay đổi dấu vết vừa tự kiểm tra thay đổi đó.

## 8. Tiêu chí đánh giá một yêu cầu Access Approval

Trước khi chấp thuận, người phê duyệt nên kiểm tra:

- Yêu cầu có mã tham chiếu hoặc ticket hỗ trợ hợp lệ không?
- Lý do truy cập có liên quan trực tiếp đến sự cố hoặc nhiệm vụ đang xử lý không?
- Project, dịch vụ và tài nguyên được nêu có đúng phạm vi cần thiết không?
- Thao tác dự kiến và khoảng thời gian truy cập có hợp lý không?
- Yêu cầu có tuân thủ chính sách dữ liệu, hợp đồng và quy định nội bộ không?
- Có cần hỏi chủ sở hữu dữ liệu hoặc cán bộ tuân thủ trước khi quyết định không?
- Sau khi quyết định, ai sẽ đối chiếu log Access Transparency và lưu bằng chứng?

Nếu từ chối, ghi lại lý do theo quy trình nội bộ và thông báo cho đầu mối hỗ trợ khi cần. Nếu chấp thuận, chỉ chấp thuận yêu cầu cụ thể sau khi đã xác minh đầy đủ ngữ cảnh. Không dùng phê duyệt để thay thế việc giới hạn quyền truy cập của ứng dụng hoặc nhân viên nội bộ.

## 9. Những giới hạn và sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Xem Access Transparency là cơ chế ngăn truy cập | Tổ chức có log nhưng không kiểm soát trước yêu cầu | Kết hợp Access Transparency với Access Approval và quy trình phản ứng |
| Xem Access Approval là log kiểm toán đầy đủ | Thiếu bằng chứng đối chiếu hoạt động thực tế sau khi phê duyệt | Thu thập và lưu log Access Transparency cùng hồ sơ yêu cầu |
| Cho rằng mọi dịch vụ đều hỗ trợ hai tính năng | Phạm vi kiểm soát thực tế nhỏ hơn cam kết tuân thủ | Kiểm tra danh sách dịch vụ và điều kiện áp dụng hiện hành |
| Phê duyệt yêu cầu chỉ dựa vào tên người gửi | Có thể chấp thuận yêu cầu quá rộng hoặc không có căn cứ | Kiểm tra lý do, ticket, tài nguyên và thời hạn |
| Cấp quyền approver cho quá nhiều người | Khó duy trì trách nhiệm và kiểm soát chéo | Giới hạn nhóm phê duyệt và rà soát thành viên định kỳ |
| Không cấu hình lưu giữ hoặc chuyển tiếp log | Bằng chứng có thể không còn sẵn sàng khi kiểm toán | Thiết lập log sink, chính sách lưu trữ và kiểm tra khả năng truy xuất |
| Bỏ qua trường hợp ngoại lệ hoặc khẩn cấp | Quy trình nội bộ có thể hiểu sai giới hạn bảo vệ | Xây dựng quy trình xem xét ngoại lệ và đối chiếu log sau sự kiện |

## 10. Checklist vận hành và kiểm toán

Định kỳ, nhóm bảo mật và tuân thủ nên xác nhận:

- Các dịch vụ chứa dữ liệu nhạy cảm đã được kiểm tra về khả năng hỗ trợ Access Transparency và Access Approval chưa?
- Cấu hình Access Approval có đúng phạm vi organization, folder hoặc project cần kiểm soát không?
- Nhóm approver có đủ người trực, có người thay thế và được rà soát quyền định kỳ không?
- Thông báo yêu cầu có đến đúng người và được xử lý trong thời hạn nội bộ không?
- Log Access Transparency có thể truy vấn, lưu giữ và chuyển đến hệ thống giám sát tập trung không?
- Quyết định phê duyệt hoặc từ chối có thể liên kết với log truy cập tương ứng không?
- Các trường hợp ngoại lệ, khẩn cấp và yêu cầu pháp lý có quy trình xử lý, ghi nhận và hậu kiểm rõ ràng không?
- Bằng chứng kiểm toán có được bảo vệ khỏi sửa đổi hoặc xóa trái phép không?

Access Transparency và Access Approval giúp tổ chức tăng tính minh bạch và quyền kiểm soát đối với hoạt động truy cập nội dung khách hàng của nhân viên Google. Khi được triển khai cùng IAM, Cloud Logging, quy trình phê duyệt và cơ chế lưu giữ bằng chứng, hai tính năng này hỗ trợ tổ chức quản lý rủi ro vận hành, đáp ứng yêu cầu kiểm toán và xây dựng niềm tin trong quá trình sử dụng Google Cloud.
