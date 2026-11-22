# AWS Audit Manager và thu thập bằng chứng kiểm soát

## Mục tiêu bài học

Trong hệ sinh thái CLOUD_PROVIDERS_AWS, AWS Audit Manager hỗ trợ hoạt động quản trị, rủi ro và tuân thủ (Governance, Risk, and Compliance – GRC). Dịch vụ kết nối yêu cầu kiểm soát với dữ liệu vận hành từ AWS như cấu hình tài nguyên, phát hiện bảo mật và hoạt động thay đổi. Nhờ đó, nhóm kỹ thuật và nhóm kiểm toán có thể theo dõi bằng chứng theo từng kiểm soát, xem xét chúng trong suốt vòng đời assessment và chuẩn bị hồ sơ cho cuộc đánh giá.

Sau bài học, người học có thể:

- Giải thích quan hệ giữa framework, assessment, control và evidence trong AWS Audit Manager.
- Chọn nguồn bằng chứng phù hợp giữa AWS Config, AWS Security Hub CSPM, AWS CloudTrail, AWS API calls và bằng chứng thủ công.
- Thiết kế quy trình thu thập, xem xét, bổ sung và xuất bằng chứng kiểm soát.
- Nhận biết giới hạn của kết quả tự động, đặc biệt là trạng thái Inconclusive.
- Đánh giá tác động của việc AWS Audit Manager chuyển sang maintenance mode từ ngày 30/04/2026.

> **Lưu ý về trạng thái dịch vụ tại ngày 20/11/2026:** AWS đã chuyển AWS Audit Manager sang maintenance mode. Tổ chức đã thiết lập dịch vụ trước ngày 30/04/2026 vẫn có thể tiếp tục sử dụng trong phạm vi tài khoản và Region đã thiết lập, bao gồm tạo assessment mới. Khách hàng dùng một tài khoản độc lập không thể thiết lập Audit Manager cho tài khoản hoặc Region mới. Với khách hàng đã thiết lập Audit Manager từ management account của AWS Organizations, các tài khoản thành viên thuộc chính tổ chức đó vẫn có thể được thêm vào assessment; không thể mở rộng sang Region mới hoặc tổ chức mới. Trong maintenance mode, AWS tiếp tục sửa lỗi và duy trì ánh xạ nguồn dữ liệu hiện có, nhưng không phát triển tính năng mới, framework mới, phiên bản framework mới hoặc hỗ trợ Region mới. Vì vậy, trước khi thiết kế hệ thống mới, cần xác minh tài khoản hiện tại có đủ điều kiện tiếp tục dùng Audit Manager hay không.

## 1. Vai trò của AWS Audit Manager

AWS Audit Manager tự động thu thập và sắp xếp bằng chứng liên quan đến các yêu cầu kiểm soát trong môi trường AWS. Dịch vụ giúp giảm công việc tìm kiếm ảnh chụp cấu hình, log hoạt động và kết quả kiểm tra bảo mật ở nhiều nơi. Nhóm kiểm toán có thể xem bằng chứng theo từng control, yêu cầu chuyên gia phụ trách kiểm tra và lựa chọn nội dung phù hợp để đưa vào assessment report.

Audit Manager không tự chứng nhận rằng tổ chức tuân thủ một tiêu chuẩn. Dịch vụ hỗ trợ thu thập và tổ chức dữ liệu liên quan; con người vẫn phải xác định yêu cầu áp dụng, kiểm tra bằng chứng, đánh giá các ngoại lệ và quyết định liệu kiểm soát có vận hành hiệu quả hay không. Bằng chứng AWS thu thập được cũng có thể chưa bao phủ toàn bộ chính sách, quy trình và hoạt động ngoài môi trường AWS mà một cuộc kiểm toán yêu cầu.

Các khái niệm chính:

| Thành phần | Ý nghĩa | Vai trò trong quy trình |
|---|---|---|
| Framework | Bộ kiểm soát được nhóm theo tiêu chuẩn, quy định hoặc yêu cầu nội bộ | Xác định cấu trúc và phạm vi kiểm toán |
| Control | Một yêu cầu hoặc biện pháp bảo vệ cần được chứng minh | Xác định điều gì cần kiểm tra |
| Assessment | Phiên đánh giá được tạo từ framework, có phạm vi tài khoản AWS cụ thể | Khởi động việc thu thập bằng chứng liên tục |
| Evidence source | Nguồn mà control dùng để thu thập dữ liệu | Xác định dữ liệu đến từ dịch vụ AWS hay người dùng |
| Evidence | Bản ghi, kết quả kiểm tra, ảnh chụp cấu hình hoặc tài liệu hỗ trợ một control | Cung cấp dữ liệu để người phụ trách xem xét |
| Assessment report | Báo cáo được tạo từ assessment và tập bằng chứng đã chọn | Chia sẻ kết quả cùng đường dẫn đến bằng chứng cho kiểm toán viên |

Framework có thể là framework tiêu chuẩn do AWS cung cấp hoặc framework tùy chỉnh do tổ chức xây dựng. Framework tiêu chuẩn phù hợp khi yêu cầu kiểm toán gắn với một tiêu chuẩn phổ biến. Framework tùy chỉnh hữu ích khi doanh nghiệp cần gom các control theo chính sách nội bộ hoặc yêu cầu của khách hàng.

Một control có thể dùng nhiều nguồn dữ liệu. Ví dụ, kiểm soát mã hóa dữ liệu có thể kết hợp kết quả AWS Config, kiểm tra bảo mật từ Security Hub CSPM, hoạt động thay đổi được ghi trong CloudTrail và tài liệu quy trình quản lý khóa được tải lên thủ công.

## 2. Luồng hoạt động từ framework đến báo cáo

Quy trình tổng quát gồm các bước sau:

~~~mermaid
flowchart TD
    A[Yêu cầu kiểm toán hoặc tiêu chuẩn] --> B[Chọn hoặc tạo framework]
    B --> C[Tạo assessment và xác định tài khoản]
    C --> D[Assessment kích hoạt các control]
    D --> E[Thu thập evidence từ nguồn AWS]
    D --> F[Bổ sung evidence thủ công]
    E --> G[Evidence được gắn với control]
    F --> G
    G --> H[Chủ sở hữu và delegate xem xét]
    H --> I[Chọn evidence cần đưa vào báo cáo]
    I --> J[Assessment report trong Amazon S3]
~~~

Khi assessment được tạo, Audit Manager bắt đầu thu thập bằng chứng liên tục cho các control đang hoạt động. Việc thu thập diễn ra theo tần suất của từng nguồn: có nguồn ghi nhận sự kiện gần như liên tục, có nguồn lấy kết quả theo lịch kiểm tra, và có nguồn chụp cấu hình hằng ngày, hằng tuần hoặc hằng tháng.

Bằng chứng được gắn với control tương ứng để người phụ trách không phải tự ghép từng log hoặc cấu hình với yêu cầu kiểm toán. Chủ sở hữu assessment có thể phân công control set cho delegate có chuyên môn, chẳng hạn nhóm IAM xem xét quyền truy cập, nhóm nền tảng xem xét cấu hình mạng hoặc nhóm vận hành xem xét sao lưu. Delegate chỉ nhận quyền trên các control set được giao và có thể xem bằng chứng, thêm nhận xét, tải tài liệu bổ sung và cập nhật trạng thái control theo quyền được cấp.

## 3. Các nguồn bằng chứng tự động

Audit Manager hỗ trợ bốn nhóm nguồn dữ liệu tự động chính. Mỗi nhóm trả lời một câu hỏi khác nhau, vì vậy cần chọn nguồn dựa trên nội dung control.

| Nguồn | Loại dữ liệu | Cách thu thập | Ví dụ câu hỏi được hỗ trợ |
|---|---|---|---|
| AWS Config | Kết quả đánh giá cấu hình và tuân thủ tài nguyên | Lấy kết quả từ Config rule theo trigger của rule | Bucket có bật mã hóa hay không? |
| AWS Security Hub CSPM | Kết quả kiểm tra bảo mật | Lấy kết quả từ Security Hub control theo lịch kiểm tra | Tài nguyên có vi phạm kiểm tra bảo mật đang bật không? |
| AWS CloudTrail | Hoạt động của người dùng hoặc dịch vụ | Theo dõi các sự kiện CloudTrail được hỗ trợ; evidence hoạt động được thu thập liên tục | Ai đã thay đổi cấu hình hoặc gọi API nào? |
| AWS API calls | Ảnh chụp cấu hình tài nguyên | Gọi API AWS được hỗ trợ theo lịch hằng ngày, hằng tuần hoặc hằng tháng | Cấu hình hiện tại của tài nguyên là gì? |

### 3.1. AWS Config

AWS Config ghi nhận cấu hình tài nguyên và đánh giá tài nguyên bằng Config rules. Audit Manager có thể lấy kết quả đánh giá của rule và gắn kết quả đó vào control liên quan dưới dạng compliance check evidence.

Ví dụ, một control yêu cầu bucket Amazon S3 phải bật mã hóa phía máy chủ. AWS Config rule kiểm tra thuộc tính mã hóa của bucket. Audit Manager lấy kết quả đánh giá để người xem xét biết tài nguyên nào đáp ứng hoặc chưa đáp ứng điều kiện.

Để nguồn này hoạt động, tài khoản và Region cần có AWS Config được cấu hình phù hợp, có recorder theo dõi loại tài nguyên cần đánh giá và có rule tương ứng. Cần kiểm tra danh sách rule được Audit Manager hỗ trợ; việc một rule tồn tại trong AWS Config không tự động bảo đảm rule đó được ánh xạ vào mọi control của Audit Manager.

### 3.2. AWS Security Hub CSPM

Security Hub CSPM tổng hợp kết quả từ các security check được hỗ trợ. Audit Manager sử dụng control ID của Security Hub CSPM làm ánh xạ nguồn và nhập kết quả kiểm tra vào assessment.

Nguồn này phù hợp khi control tập trung vào tư thế bảo mật của tài nguyên, chẳng hạn cấu hình mã hóa, quyền truy cập hoặc các thực hành bảo mật nền tảng. Kết quả được thu thập theo lịch của security check. Vì vậy, thời điểm xuất hiện evidence phụ thuộc vào lịch chạy kiểm tra và trạng thái tích hợp.

### 3.3. AWS CloudTrail

CloudTrail ghi nhận hoạt động API trong tài khoản AWS. Audit Manager có thể theo dõi các event name được hỗ trợ và thu thập hoạt động liên quan thành user activity evidence.

Ví dụ, khi một principal gọi API thay đổi cấu hình mã hóa của bucket, CloudTrail có thể ghi lại thời điểm, danh tính gọi API và sự kiện tương ứng. Bằng chứng này hữu ích để xác định ai đã thực hiện thay đổi và khi nào thay đổi xảy ra.

CloudTrail evidence cho biết hoạt động đã được ghi nhận; nó không tự chứng minh rằng hoạt động đó được phê duyệt đúng quy trình hoặc rằng cấu hình sau thay đổi an toàn. Người xem xét cần đối chiếu với change request, chính sách phê duyệt hoặc tài liệu vận hành khi control yêu cầu.

### 3.4. AWS API calls

Với nguồn API calls, Audit Manager gọi một API AWS được hỗ trợ để lấy ảnh chụp cấu hình tài nguyên. Người tạo custom control chọn API và tần suất thu thập: hằng ngày, hằng tuần hoặc hằng tháng.

Ví dụ, API đọc cấu hình mã hóa của S3 có thể cung cấp ảnh chụp trạng thái tại thời điểm thu thập. Ảnh chụp này hữu ích để chứng minh cấu hình được quan sát tại một thời điểm, nhưng không thay thế log lịch sử về ai đã thay đổi cấu hình.

### 3.5. AWS managed sources và customer managed sources

Khi tạo custom control, người dùng có thể chọn AWS managed source hoặc customer managed source.

- **AWS managed source** là nhóm nguồn do AWS duy trì và ánh xạ tới common control hoặc core control. Khi AWS cập nhật định nghĩa nguồn, các custom control sử dụng nguồn đó được áp dụng cập nhật tương ứng. Đây thường là lựa chọn nên ưu tiên khi nguồn có sẵn và phù hợp với yêu cầu.
- **Customer managed source** là nguồn do tổ chức tự định nghĩa, ví dụ một AWS Config rule riêng hoặc một API call cụ thể. Tổ chức chịu trách nhiệm duy trì mapping, kiểm tra tính đúng đắn và cập nhật nguồn khi yêu cầu thay đổi.

Một control có thể kết hợp nhiều nguồn. Không nên thêm nguồn chỉ để tăng số lượng evidence; mỗi nguồn cần có mục đích rõ ràng và phải cung cấp dữ liệu có liên quan đến yêu cầu kiểm soát.

## 4. Bằng chứng thủ công

Không phải yêu cầu kiểm soát nào cũng có thể được chứng minh bằng trạng thái cấu hình AWS. Một số yêu cầu liên quan đến hoạt động của con người, tài liệu quản trị hoặc môi trường ngoài AWS. Audit Manager hỗ trợ bổ sung các loại bằng chứng này theo ba cách:

1. **Import từ Amazon S3:** dùng khi tài liệu, báo cáo hoặc artifact đã được lưu trong bucket.
2. **Upload từ trình duyệt:** dùng khi tài liệu đang ở máy tính hoặc mạng nội bộ, chẳng hạn bản scan biên bản hoặc chữ ký.
3. **Nhập câu trả lời dạng văn bản:** dùng khi control là câu hỏi đánh giá và bằng chứng phù hợp là lời giải thích hoặc thông tin dạng text.

Ví dụ, một control yêu cầu tổ chức có quy trình phê duyệt cấp quyền. AWS có thể cung cấp bằng chứng về cấu hình IAM và hoạt động tạo hoặc thay đổi policy. Tuy nhiên, quy trình phê duyệt, danh sách người có thẩm quyền, biên bản rà soát quyền và hồ sơ đào tạo nhân viên có thể cần được cung cấp thủ công.

Bằng chứng thủ công cũng có thể đến từ hệ thống on-premises, nền tảng SaaS hoặc môi trường cloud khác. Khi thêm tài liệu, cần gắn tài liệu vào đúng assessment control và mô tả rõ tài liệu chứng minh yêu cầu nào, thuộc khoảng thời gian nào và do bộ phận nào chịu trách nhiệm.

Không nên tải thông tin nhạy cảm hoặc dữ liệu nhận dạng cá nhân (PII) lên làm manual evidence. Trước khi upload, hãy loại bỏ dữ liệu không cần thiết, kiểm tra quyền truy cập và xác nhận rằng tài liệu có thể được chia sẻ với đúng nhóm kiểm toán.

## 5. Thiết kế một control có bằng chứng đầy đủ

Một control tốt bắt đầu từ yêu cầu có thể kiểm tra được. Hãy chuyển yêu cầu chung thành các câu hỏi cụ thể:

- Đối tượng nào nằm trong phạm vi?
- Trạng thái hoặc hành vi nào cần được chứng minh?
- Bằng chứng cần thể hiện trạng thái tại một thời điểm hay lịch sử thay đổi?
- Yêu cầu có bao gồm chính sách, phê duyệt hoặc hoạt động của con người không?
- Ai sẽ xem xét bằng chứng và tần suất xem xét là bao lâu?

Ví dụ: **Kiểm soát mã hóa dữ liệu trong Amazon S3**.

| Phần cần chứng minh | Nguồn phù hợp | Bằng chứng thu được | Điểm cần người xem xét xác nhận |
|---|---|---|---|
| Bucket thuộc phạm vi có bật mã hóa | AWS Config hoặc Security Hub CSPM | Kết quả kiểm tra cấu hình | Rule/control có bao phủ đúng bucket và Region không? |
| Cấu hình mã hóa tại thời điểm kiểm tra | AWS API calls | Ảnh chụp cấu hình mã hóa | Snapshot có đủ thuộc tính cần kiểm tra không? |
| Hoạt động thay đổi cấu hình | AWS CloudTrail | Sự kiện thay đổi, danh tính và thời điểm | Thay đổi có ticket và phê duyệt phù hợp không? |
| Quy trình quản lý khóa và ngoại lệ | Manual evidence | Chính sách, quy trình, biên bản rà soát | Tài liệu còn hiệu lực và áp dụng cho đúng hệ thống không? |

Ví dụ này cho thấy một nguồn dữ liệu thường chỉ chứng minh được một phần của control. Config hoặc Security Hub có thể cho biết trạng thái kỹ thuật; CloudTrail giúp theo dõi hoạt động; tài liệu thủ công chứng minh quy trình quản trị. Người phụ trách cần xem xét các phần này cùng nhau trước khi kết luận control hoạt động hiệu quả.

Khi tạo custom control, nên mô tả rõ mục tiêu, cách kiểm tra, nguồn evidence, tần suất cần thiết và loại tài liệu thủ công có thể bổ sung. Nếu dùng customer managed source, cần ghi nhận người chịu trách nhiệm duy trì mapping và kiểm tra nguồn khi AWS thay đổi API hoặc rule.

## 6. Xem xét bằng chứng và hiểu trạng thái kết quả

Sau khi evidence được thu thập, người phụ trách cần xem xét nội dung thay vì chỉ dựa vào trạng thái tổng hợp. Với từng evidence, hãy kiểm tra:

- **Phạm vi:** đúng tài khoản, Region, dịch vụ, tài nguyên và control cần đánh giá.
- **Thời gian:** evidence nằm trong kỳ kiểm toán và phản ánh thời điểm phù hợp.
- **Nguồn:** xác định dữ liệu đến từ Config, Security Hub CSPM, CloudTrail, API call hay upload thủ công.
- **Độ đầy đủ:** dữ liệu có các thuộc tính cần thiết để kiểm tra yêu cầu hay không.
- **Tính liên quan:** bằng chứng có chứng minh đúng yêu cầu của control hay chỉ cung cấp thông tin gần giống.
- **Ngoại lệ:** tài nguyên không áp dụng, thay đổi được phê duyệt hoặc thiếu dữ liệu cần được giải thích và lưu hồ sơ.

Đối với compliance check evidence từ AWS Config hoặc Security Hub CSPM, kết quả có thể thể hiện tài nguyên tuân thủ hoặc không tuân thủ. Với CloudTrail, API calls và manual evidence, Audit Manager thường không có cơ chế đánh giá tuân thủ tự động nên có thể hiển thị trạng thái **Inconclusive**.

**Inconclusive không có nghĩa là thất bại.** Trạng thái này cho biết Audit Manager chưa thể tự đánh giá evidence theo logic compliance check. Người có chuyên môn phải mở chi tiết evidence, đối chiếu với yêu cầu và ghi nhận kết luận. Nếu AWS Config hoặc Security Hub CSPM chưa được bật hoặc chưa có dữ liệu đánh giá, evidence liên quan cũng có thể ở trạng thái Inconclusive.

Một quy trình xem xét có thể phân công như sau:

| Vai trò | Trách nhiệm |
|---|---|
| Audit owner | Quản lý assessment, phạm vi, control set, phân công và báo cáo |
| Delegate | Xem xét control set được giao, nhận xét và bổ sung evidence theo quyền |
| Chủ sở hữu hệ thống | Giải thích kiến trúc, cấu hình, thay đổi và ngoại lệ |
| Nhóm GRC hoặc kiểm toán nội bộ | Đối chiếu evidence với tiêu chuẩn, chính sách và kỳ kiểm toán |

Nên ghi nhận lý do chấp nhận ngoại lệ, bằng chứng thay thế, người phê duyệt và thời hạn khắc phục. Một trạng thái compliant của cấu hình không tự chứng minh rằng mọi quy trình liên quan cũng được tuân thủ.

## 7. Chọn bằng chứng và tạo assessment report

Evidence mới được thu thập không tự động xuất hiện trong assessment report. Audit owner phải chọn evidence cần đưa vào báo cáo. Có thể thêm cả evidence folder hoặc chọn từng evidence item trong folder.

Quy trình chuẩn bị báo cáo:

1. Mở assessment và kiểm tra control set cần báo cáo.
2. Xem các evidence folder theo control và khoảng thời gian.
3. Mở evidence chi tiết, xác minh nguồn, thời gian, tài nguyên và nội dung.
4. Bổ sung manual evidence hoặc nhận xét cho các control cần giải thích thêm.
5. Chọn evidence folder hoặc evidence item phù hợp để thêm vào assessment report.
6. Kiểm tra danh sách evidence đã chọn trước khi tạo báo cáo.
7. Tạo assessment report và lưu tại Amazon S3 bucket đã cấu hình làm report destination.
8. Tải báo cáo từ Audit Manager nếu cần và kiểm tra quyền truy cập tới báo cáo cùng các evidence liên quan.

Báo cáo tóm tắt assessment và cung cấp liên kết đến các thư mục bằng chứng được tổ chức theo control. Việc lựa chọn evidence là một bước kiểm soát quan trọng: báo cáo cần bao gồm đúng tài liệu liên quan, đúng kỳ đánh giá và đủ thông tin để người nhận hiểu kết quả.

Bucket lưu báo cáo cần được quản trị như một kho dữ liệu kiểm toán. Hãy áp dụng quyền truy cập tối thiểu, mã hóa dữ liệu, giám sát truy cập và chính sách lưu giữ phù hợp với yêu cầu nội bộ. Chỉ chia sẻ báo cáo cho người có thẩm quyền và kiểm tra quyền truy cập đến các đối tượng S3 được tham chiếu trong báo cáo.

## 8. Vận hành an toàn và xử lý sự cố thường gặp

### 8.1. Không có evidence được thu thập

Kiểm tra lần lượt:

- Assessment và control có đang ở trạng thái hoạt động hay đã bị chuyển sang inactive không.
- Tài khoản và Region có nằm trong phạm vi assessment không.
- AWS Config hoặc Security Hub CSPM đã được bật và có dữ liệu hay chưa.
- Config recorder, rule hoặc Security Hub control có hoạt động và thuộc danh sách được Audit Manager hỗ trợ không.
- CloudTrail có ghi nhận event cần theo dõi và event đó có nằm trong danh sách được hỗ trợ không.
- API call đã chọn có được hỗ trợ, có quyền truy cập cần thiết và có lịch thu thập phù hợp không.
- Quyền IAM và service-linked role có còn hợp lệ không.

### 8.2. Evidence ở trạng thái Inconclusive

Xác định nguồn tạo evidence trước. Nếu nguồn là CloudTrail, API call hoặc manual upload, Inconclusive có thể là trạng thái bình thường vì Audit Manager không tự đánh giá nội dung đó. Nếu nguồn là Config hoặc Security Hub CSPM, kiểm tra việc bật dịch vụ, rule/control, trạng thái đánh giá và dữ liệu trả về. Sau đó, người phụ trách cần đánh giá thủ công theo tiêu chí của control.

### 8.3. Có evidence nhưng báo cáo thiếu dữ liệu

Kiểm tra tab lựa chọn assessment report. Evidence mới thu thập không được tự động thêm vào báo cáo; audit owner phải chọn folder hoặc item cần đưa vào. Đồng thời, xác minh bộ lọc thời gian khi tìm folder, vì giao diện có thể mặc định hiển thị khoảng thời gian gần đây.

### 8.4. Phân quyền và bảo vệ dữ liệu

Dùng IAM policy theo vai trò, tách quyền quản lý assessment khỏi quyền chỉ xem hoặc xem xét control set. Delegate chỉ nên được giao những control thuộc chuyên môn của họ. Hạn chế quyền truy cập vào bucket lưu report và evidence, bật các biện pháp bảo vệ dữ liệu phù hợp, và giữ lịch sử phê duyệt cho các thay đổi quan trọng.

Không dùng manual evidence để lưu secret, credential, token hoặc PII không cần thiết. Với tài liệu cần cung cấp cho kiểm toán viên, hãy chuẩn bị bản đã loại bỏ thông tin ngoài phạm vi và xác định rõ người được phép xem.

## 9. Định hướng sau khi Audit Manager chuyển sang maintenance mode

Vì ngày hiện tại là 20/11/2026, việc lựa chọn Audit Manager phải bắt đầu bằng kiểm tra trạng thái triển khai hiện có:

- **Tổ chức đã dùng Audit Manager trước 30/04/2026:** có thể tiếp tục dùng trong phạm vi tài khoản và Region đã thiết lập; nếu đã cấu hình ở management account của AWS Organizations, có thể đưa thêm tài khoản thành viên thuộc cùng tổ chức vào assessment theo giới hạn AWS công bố.
- **Tổ chức hoặc tài khoản mới chưa thiết lập Audit Manager:** không thể bắt đầu triển khai dịch vụ theo cách thông thường sau mốc 30/04/2026.
- **Nhu cầu kiểm tra tư thế tuân thủ tài nguyên AWS:** xem xét AWS Config Conformance Packs. Chúng triển khai các detective controls dưới dạng Config rules, có thể quản lý ở cấp tài khoản hoặc AWS Organizations và cung cấp dashboard cùng trạng thái theo tài nguyên.
- **Nhu cầu quản lý đầy đủ hồ sơ kiểm toán:** đánh giá khoảng trống trước khi chuyển đổi. Conformance Packs không phải bản thay thế tương đương Audit Manager Frameworks. AWS Config tập trung vào kết quả Config rules và Configuration Items; nó không thu thập CloudTrail logs, Security Hub controls hoặc gọi API dịch vụ như Audit Manager. Nó cũng không cung cấp cùng quy trình gom, xem xét và chia sẻ toàn bộ bằng chứng phi kỹ thuật như chính sách, phỏng vấn hoặc hồ sơ phê duyệt. Một số framework của Audit Manager, bao gồm SOC 2 và GDPR trong tài liệu AWS tại thời điểm viết, chưa có Conformance Pack tương ứng.

Khi chuyển đổi, hãy lập bảng đối chiếu từng control với Config rule hoặc Conformance Pack tương ứng, ghi rõ phần nào có thể tự động kiểm tra và phần nào vẫn cần tài liệu hoặc quy trình riêng. Có thể dùng AWS Config Advanced Query để xuất các Configuration Items hiện tại dưới dạng CSV hoặc JSON; nếu cần lịch sử cấu hình, xem xét API GetResourceConfigHistory. Với yêu cầu quản lý bằng chứng và workflow kiểm toán rộng hơn, cần đánh giá thêm giải pháp GRC phù hợp thay vì giả định Conformance Packs bao phủ toàn bộ tiêu chuẩn.

## 10. Thực hành đề xuất

Giả sử một tổ chức đang chuẩn bị kiểm toán kiểm soát bảo vệ dữ liệu cho ứng dụng chạy trên AWS. Nhóm cần chứng minh rằng bucket S3 được mã hóa, thay đổi cấu hình được theo dõi và quy trình quản lý khóa có người phê duyệt.

Một cách triển khai hợp lý là:

1. Chọn framework phù hợp với yêu cầu kiểm toán và xác định các AWS account nằm trong phạm vi.
2. Tạo assessment nếu tài khoản và Region hiện tại đủ điều kiện sử dụng Audit Manager.
3. Xác định control liên quan đến mã hóa dữ liệu và chọn AWS managed source nếu mapping có sẵn, phù hợp.
4. Bổ sung nguồn Config hoặc Security Hub CSPM để kiểm tra cấu hình, CloudTrail để theo dõi thay đổi và API call để chụp cấu hình khi cần.
5. Thu thập tài liệu thủ công về quy trình quản lý khóa, phê duyệt thay đổi và xử lý ngoại lệ.
6. Giao control set cho nhóm nền tảng và nhóm bảo mật xem xét; audit owner theo dõi các evidence còn thiếu hoặc Inconclusive.
7. Đối chiếu kết quả với kỳ kiểm toán, giải thích ngoại lệ và chỉ chọn các evidence đã được xác minh để đưa vào báo cáo.
8. Lưu báo cáo và bằng chứng trong S3 với quyền truy cập, mã hóa và thời hạn lưu giữ phù hợp.

Nếu tổ chức chưa thể thiết lập Audit Manager, hãy chuyển bài toán thành danh sách yêu cầu kiểm tra kỹ thuật có thể triển khai bằng AWS Config Conformance Packs, đồng thời xác định riêng các yêu cầu về CloudTrail, Security Hub, tài liệu quy trình và phê duyệt. Cách làm này giúp duy trì khả năng quan sát tư thế tuân thủ của tài nguyên mà vẫn chỉ ra rõ những phần cần một quy trình hoặc công cụ GRC khác hỗ trợ.

## Kết luận

AWS Audit Manager liên kết framework, assessment, control và evidence để hỗ trợ chuẩn bị kiểm toán trên AWS. Chất lượng của kết quả phụ thuộc vào việc chọn đúng control, cấu hình đúng nguồn dữ liệu, bổ sung bằng chứng thủ công khi cần và để người có chuyên môn xem xét từng evidence. Trạng thái Inconclusive cần được đánh giá theo nội dung và nguồn dữ liệu, không nên tự động xem là lỗi hoặc thất bại.

Từ 30/04/2026, Audit Manager ở maintenance mode và giới hạn việc thiết lập cho tài khoản, Region hoặc tổ chức mới. Do đó, người thiết kế giải pháp cần kiểm tra điều kiện sử dụng hiện tại và đánh giá AWS Config Conformance Packs cùng các công cụ GRC khác theo phạm vi kiểm soát thực tế.

## Tài liệu tham khảo

- [What is AWS Audit Manager?](https://docs.aws.amazon.com/audit-manager/latest/userguide/what-is.html)
- [Understanding AWS Audit Manager concepts and terminology](https://docs.aws.amazon.com/audit-manager/latest/userguide/concepts.html)
- [Supported data source types for automated evidence](https://docs.aws.amazon.com/audit-manager/latest/userguide/control-data-sources.html)
- [Managing assessments in AWS Audit Manager](https://docs.aws.amazon.com/audit-manager/latest/userguide/assessments.html)
- [Adding manual evidence in AWS Audit Manager](https://docs.aws.amazon.com/audit-manager/latest/userguide/upload-evidence.html)
- [Preparing an assessment report in AWS Audit Manager](https://docs.aws.amazon.com/audit-manager/latest/userguide/generate-assessment-report.html)
- [AWS Audit Manager availability change](https://docs.aws.amazon.com/audit-manager/latest/userguide/audit-manager-availability-change.html)

