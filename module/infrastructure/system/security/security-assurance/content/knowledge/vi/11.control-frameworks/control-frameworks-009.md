# Control gap: Nhận diện và xử lý khoảng trống kiểm soát trong Control Framework

## 1. Control gap là gì?

**Control gap** (khoảng trống kiểm soát bảo mật) là **sự chênh lệch có ý nghĩa** giữa trạng thái kiểm soát bảo mật **cần đạt** và trạng thái **đang có hoặc đã được chứng minh** của một hệ thống, quy trình hoặc tổ chức. Trạng thái mục tiêu thường xuất phát từ rủi ro, chính sách, tiêu chuẩn nội bộ, nghĩa vụ áp dụng và các yêu cầu từ **control framework** được tổ chức lựa chọn.

Một control gap có thể biểu hiện dưới nhiều hình thức:

- **Không có control cần thiết:** chẳng hạn chưa có quy trình thu hồi quyền cho nhân viên nghỉ việc.
- **Control thiết kế chưa đủ:** chỉ kiểm tra người dùng đã đăng nhập, nhưng không kiểm tra quyền trên từng tài nguyên.
- **Control triển khai chưa đủ phạm vi:** endpoint đọc từng bản ghi được bảo vệ, nhưng endpoint xuất dữ liệu không áp dụng cùng nguyên tắc.
- **Control hoạt động không đạt:** hệ thống cảnh báo có rule nhưng không nhận log từ một phần môi trường production.
- **Thiếu bằng chứng:** control có thể hoạt động, nhưng chưa có test, báo cáo, log hoặc xác minh đủ tin cậy để kết luận.
- **Thiếu quản trị và trách nhiệm:** control chưa có owner, lịch đánh giá hoặc đường xử lý phát hiện.

Vì vậy, **control gap không đồng nghĩa với một lỗ hổng phần mềm cụ thể**. Nó cũng không đồng nghĩa rằng hệ thống đã bị tấn công hoặc rằng mọi mục chưa có bằng chứng đều đang thất bại. Control gap là thông tin để tổ chức **xác minh, ưu tiên và xử lý** một khoảng cách so với yêu cầu mục tiêu.

Trong module **SECURITY_SECURITY_ASSURANCE**, việc nhận diện control gap tạo cầu nối giữa **khung kiểm soát** và **bằng chứng assurance**: từ phân tích rủi ro, chọn yêu cầu, thiết kế control, thực hiện test/audit, ghi phát hiện, khắc phục cho đến tái đánh giá trong quá trình phát triển và vận hành.

> **Nguyên tắc:** chỉ gọi một yêu cầu là “đạt” khi có căn cứ phù hợp trong phạm vi đánh giá. Trạng thái **“chưa đủ bằng chứng”** cần được giữ riêng với **“không đạt”**, vì chúng mô tả hai loại vấn đề khác nhau và đòi hỏi hành động khác nhau.

## 2. Control gap nằm ở đâu trong một control framework?

Một **control framework** là cấu trúc giúp tổ chức tổ chức các mục tiêu, nhóm và hoạt động kiểm soát an ninh thông tin. Có thể tham khảo các khung như **ISO/IEC 27001/27002**, **NIST SP 800-53**, **NIST Cybersecurity Framework** hoặc **CIS Controls**, tùy mục tiêu và phạm vi.

Chúng không hoàn toàn cùng loại:

- **ISO/IEC 27001** đặt ra yêu cầu cho hệ thống quản lý an ninh thông tin; các control trong Phụ lục A và hướng dẫn liên quan hỗ trợ lựa chọn và xử lý rủi ro theo phạm vi áp dụng.
- **NIST SP 800-53** cung cấp danh mục control an ninh và quyền riêng tư có cấu trúc, có thể được điều chỉnh cho hệ thống và tổ chức.
- **NIST CSF** tổ chức các kết quả an ninh mong muốn theo chức năng; khi đánh giá cần diễn giải các outcome thành những yêu cầu và bằng chứng cụ thể.
- **CIS Controls** cung cấp tập biện pháp được ưu tiên và các hoạt động triển khai; phạm vi áp dụng phụ thuộc môi trường và mục tiêu của tổ chức.

Nhóm phải ghi **tên, phiên bản/edition và phạm vi** của framework đang sử dụng. Không được tự cho rằng một mục trong danh mục là yêu cầu bắt buộc với mọi tổ chức và mọi hệ thống. Cách chọn/bỏ control cần tuân thủ phương pháp đánh giá rủi ro và nghĩa vụ thực tế.

### 2.1. Phân biệt framework, requirement, control và evidence

| Thành phần | Vai trò | Ví dụ minh họa |
| --- | --- | --- |
| **Framework** | Cấu trúc tham chiếu để tổ chức các mục tiêu và control | Danh mục các lĩnh vực kiểm soát truy cập, giám sát, ứng cứu |
| **Requirement** | Điều kiện cụ thể bắt buộc với một đối tượng theo scope và tiêu chí áp dụng | Mọi đường đọc dữ liệu khách hàng phải kiểm tra quyền tài nguyên |
| **Control design** | Cơ chế đề xuất nhằm đáp ứng yêu cầu | Phân quyền theo tenant ở tầng service/data |
| **Control implementation** | Cơ chế thật đã triển khai trên hệ thống | Truy vấn dữ liệu ràng buộc tenant ID từ identity tin cậy |
| **Control operation** | Hoạt động của control qua các request và trong kỳ vận hành | Yêu cầu ngoài quyền luôn bị từ chối theo policy |
| **Evidence** | Thông tin kiểm chứng thiết kế, triển khai và vận hành | Test âm/dương, code review, log, báo cáo kiểm thử |
| **Control gap** | Khoảng cách còn tồn tại hoặc chưa được chứng minh | Endpoint export không lọc tenant, hoặc chưa được test |
| **Risk decision** | Quyết định xử lý/chấp nhận rủi ro còn lại theo thẩm quyền | Sửa khẩn cấp, tạm dừng tính năng, ngoại lệ có thời hạn |

Một control thực tế có thể **đáp ứng nhiều framework requirement**; một requirement có thể cần **nhiều control**. Vì vậy, không nên tạo một control mới chỉ để làm đẹp bảng cho từng dòng framework.

### 2.2. Gap analysis không phải là đếm ô checklist

Hãy phân biệt:

- **Framework coverage:** các yêu cầu áp dụng đã được ánh xạ đến control nào.
- **Design adequacy:** thiết kế control có đủ để giải quyết rủi ro không.
- **Implementation coverage:** control đã triển khai tại những hệ thống, endpoint, tài khoản và môi trường nào.
- **Operating effectiveness:** control có hoạt động nhất quán theo mục tiêu không.
- **Assurance evidence coverage:** những kết luận trên có bằng chứng tương ứng không.

Một tổ chức có thể ánh xạ **100% mục framework** nhưng vẫn còn control gap nghiêm trọng khi một cơ chế không vận hành. Tương tự, một control đang hoạt động có thể vẫn bị đánh dấu **evidence gap** nếu việc chứng minh chưa đủ.

## 3. Những loại control gap quan trọng

### 3.1. Requirement hoặc applicability gap

Khoảng trống xuất hiện khi chưa xác định rõ **yêu cầu nào áp dụng** cho tài sản, dữ liệu, loại hệ thống hoặc nghĩa vụ thực tế.

Ví dụ: framework được chọn có nội dung về quản lý định danh, nhưng tổ chức chưa chuyển thành yêu cầu cho **service account** và **API token**. Một số control không được đánh giá vì chưa có trong phạm vi.

**Cách xử lý:** xác nhận applicability, cập nhật requirement và lý do chọn/bỏ; tham vấn risk owner, policy owner hoặc bộ phận phụ trách nghĩa vụ.

### 3.2. Design gap

Control được mô tả nhưng **cơ chế không xử lý đầy đủ** kịch bản rủi ro cần bảo vệ.

Ví dụ: “Có JWT authentication” không đủ để ngăn người dùng A đọc dữ liệu B nếu không có **object-level authorization**.

**Bằng chứng phân tích:** threat model, security claim, sơ đồ luồng dữ liệu, design review và các tình huống có thể vượt qua cơ chế.

### 3.3. Implementation gap

Thiết kế phù hợp nhưng control **chưa được triển khai đúng hoặc đầy đủ**.

Ví dụ: API đọc đơn hàng kiểm tra quyền, nhưng batch export truy vấn trực tiếp cơ sở dữ liệu mà không lọc theo người có quyền.

**Bằng chứng:** code review, cấu hình, endpoint inventory, kiểm thử tích hợp, bản build và mô tả đường dữ liệu.

### 3.4. Operating effectiveness gap

Control được cài đặt nhưng **không hoạt động đúng trong thực tế hoặc không ổn định trong kỳ đánh giá**.

Ví dụ: công cụ quét cấu hình chỉ chạy trong tuần đầu, sau đó job bị tắt; hoặc rule cảnh báo không hoạt động vì nguồn log đổi cấu trúc.

**Bằng chứng:** lịch chạy, telemetry, log, báo cáo kiểm tra, sự cố, cảnh báo và diễn tập.

### 3.5. Evidence gap

Chưa thể khẳng định control đạt vì **bằng chứng không có, không phù hợp, quá cũ hoặc sai phạm vi**.

Ví dụ: nhóm có tài liệu nói “backup đang hoạt động”, nhưng chưa có bằng chứng restore thành công; hoặc chỉ test phân quyền trên staging khi production đã thay cấu hình.

**Hướng xử lý:** thu thập evidence, kiểm tra đúng build/phạm vi, chạy test hoặc thực hiện đánh giá bổ sung. **Chưa đủ bằng chứng không tự chứng minh control thất bại.**

### 3.6. Ownership, governance hoặc process gap

Không có người chịu trách nhiệm cuối cùng, quy trình ngoại lệ, lịch kiểm thử hoặc cơ chế khắc phục; đây là khoảng trống quản trị có thể làm suy yếu các control kỹ thuật.

Ví dụ: quản lý secret tồn tại ở nền tảng tập trung, nhưng không rõ đội nào thu hồi secret của dịch vụ khi nhân viên đổi vai trò.

**Hướng xử lý:** cập nhật owner, RACI, quy trình bàn giao, thời hạn, tiêu chí kiểm chứng và cấp chuyển tiếp.

### 3.7. Scope và integration gap

Một control dùng chung có thể bảo vệ một phần kiến trúc nhưng không bao phủ **đường kết nối và môi trường mới**.

Ví dụ: API gateway xác thực request bên ngoài, song service nội bộ có đường gọi bỏ qua gateway, hoặc hệ thống dùng nhiều tenant nhưng kiểm tra quyền chỉ ở cấp chức năng.

**Hướng xử lý:** xác định ownership giữa nền tảng và sản phẩm, kiểm tra từng trust boundary và mọi đường truy cập trong scope.

| Loại gap | Câu hỏi nhận diện | Hành động ưu tiên |
| --- | --- | --- |
| Requirement/applicability | Có biết chính xác điều gì bắt buộc cho đối tượng này chưa? | Xác định scope và yêu cầu |
| Design | Cơ chế có giảm đúng threat không? | Thiết kế/sửa control |
| Implementation | Đã áp dụng cơ chế tại mọi điểm cần bảo vệ chưa? | Cập nhật code/cấu hình/tích hợp |
| Operation | Có chạy đúng và đủ ổn định trong kỳ không? | Sửa vận hành, giám sát và phản ứng |
| Evidence | Có đủ căn cứ để kết luận đạt/không đạt không? | Test, review, audit, lưu evidence |
| Ownership/process | Ai duy trì, phát hiện sai lệch và khắc phục? | Phân vai, quy trình, cơ chế chuyển cấp |
| Scope/integration | Các đường mới, vùng mới, hệ thống dùng chung đã được bao phủ? | Mở rộng inventory, coverage và test |

Một phát hiện có thể thuộc **nhiều loại**. Khi điều tra nên ghi nhiều nhãn và chia thành các hành động cụ thể, thay vì ép mọi việc về một trạng thái duy nhất.

## 4. Xác định trạng thái mục tiêu trước khi đo gap

### 4.1. Applicability: mục framework nào thực sự cần đánh giá?

Trước khi đánh giá thiếu/đủ, phải biết:

1. Framework nào được sử dụng, phiên bản/edition và phạm vi được phê duyệt?
2. Tài sản, nghiệp vụ, dữ liệu, môi trường và bên thứ ba nào thuộc scope?
3. Rủi ro và mục tiêu bảo mật nào cần được xử lý?
4. Nghĩa vụ nội bộ hoặc bên ngoài nào **thực sự áp dụng**?
5. Control nào được chọn, control nào không áp dụng và lý do, thẩm quyền xác nhận?
6. Có yêu cầu về **thiết kế**, **triển khai** và **bằng chứng vận hành** khác nhau không?

Trong hệ thống quản lý theo ISO/IEC 27001, việc xem xét tính áp dụng của các control và **lý do lựa chọn hoặc loại trừ** thường được ghi vào **Statement of Applicability (SoA)** theo các yêu cầu của tiêu chuẩn và phiên bản áp dụng. SoA không phải công cụ cho phép loại bỏ tùy ý những nghĩa vụ bắt buộc; bản ghi phải phản ánh kết quả xử lý rủi ro và cách quản trị chính thức.

Trong những framework khác, có thể dùng **applicability matrix**, control register hoặc profile. Hình thức khác nhau, nhưng nguyên tắc vẫn là: **không đánh giá một mục là gap chỉ vì nó có trong danh mục tham khảo; cũng không bỏ qua một rủi ro quan trọng chỉ vì mục danh mục không nhắc chính xác tên kịch bản đó**.

### 4.2. Định nghĩa target state đo được

Câu “cần kiểm soát truy cập tốt” quá mơ hồ. Một target state nên nêu:

> “Mọi đường truy cập hóa đơn khách hàng trong Billing API phải kiểm tra quyền trên đúng đối tượng và tenant. Yêu cầu ngoài quyền không được trả thông tin hóa đơn. Các đường đọc chi tiết, danh sách và export phải có bằng chứng kiểm thử trên bản phát hành mục tiêu.”

Từ đó nhóm có thể đánh giá cụ thể: những endpoint nào đã có control, test nào chạy, rủi ro nào còn thiếu và khi nào có thể đóng gap.

### 4.3. Không lấy trạng thái công cụ làm mục tiêu cuối cùng

“Đã bật WAF”, “đã mua SIEM”, “đã chạy vulnerability scanner” là mô tả giải pháp, chưa phải tiêu chí hiệu quả.

Thay vào đó cần hỏi:

- WAF có giảm được kịch bản tấn công được nêu và có những đường bypass nào?
- SIEM có nhận đúng log trọng yếu, tạo cảnh báo và đưa người xử lý đến hành động không?
- Quét lỗ hổng có đủ phạm vi, xử lý phát hiện và kiểm thử lại không?
- Kiểm tra phân quyền có ngăn truy cập sai tài nguyên trên mọi đường vào cần bảo vệ không?

## 5. Quy trình control gap analysis từng bước

### Bước 1. Khởi tạo assessment và chốt scope

Định danh cuộc đánh giá:

- Assessment ID, mục tiêu, ngày và khoảng thời gian.
- Framework ID + phiên bản/edition; policy và standard phiên bản có liên quan.
- Tài sản, service, môi trường, nhà cung cấp và các loại dữ liệu.
- Người chịu trách nhiệm đánh giá, control owner, risk owner.
- Tiêu chí đánh giá, thời gian, công cụ và giới hạn phạm vi.

Nếu chỉ đánh giá 5/20 dịch vụ, hãy ghi **mẫu nào được kiểm tra**; không đưa ra kết luận cho cả 20 dịch vụ.

### Bước 2. Lập applicability và control mapping

Xây dựng bảng từ **mục tiêu/framework requirement** đến **control thực tế** và **security claim**.

| Framework domain / mục tiêu | Requirement nội bộ minh họa | Control hiện tại | Tài sản/scope |
| --- | --- | --- | --- |
| Quản lý truy cập | Mọi đường đọc dữ liệu phải xác minh quyền trên tài nguyên | Object authorization | Billing API |
| Bảo vệ bí mật | Secret không được đặt trong mã nguồn và phải có kiểm soát truy cập | Secrets manager + scanner | CI/CD và runtime |
| Logging/monitoring | Sự kiện quản trị trọng yếu phải được truy vết và xem xét | Audit log + alert | Admin services |
| Khả năng phục hồi | Dữ liệu quan trọng phải khôi phục theo mục tiêu đã duyệt | Backup + restore exercise | Database |
| Quản lý thay đổi | Chỉ artifact được phê duyệt mới đến production | Branch protection, CI/CD approval | Build/deploy pipeline |

Các domain ở đây mang tính **minh họa**, không phải trích dẫn mã điều khoản chính thức của một framework. Nếu báo cáo tuân thủ một chuẩn cụ thể, phải dùng **mã kiểm soát và văn bản đúng edition** trong hồ sơ quản trị của tổ chức.

### Bước 3. Thu thập hiện trạng và bằng chứng

Đối chiếu từng control với:

- Kiến trúc, threat model, data flow, trust boundary.
- Mã nguồn, IaC, cấu hình IdP/gateway/database.
- Nhật ký triển khai, asset inventory, quyền người dùng/service account.
- Kết quả unit, integration, security test, pentest và scan.
- Kết quả đánh giá vận hành theo kỳ, giám sát và diễn tập.
- Findings, exceptions, action tracking, sự cố và near-miss.
- Biên bản phê duyệt rủi ro cùng các giả định còn hiệu lực.

Mỗi bằng chứng nên có **nguồn, thời gian, hệ thống, môi trường, phiên bản, người tạo và người review**. Chỉ nhìn một bản screenshot không rõ thời điểm có thể dẫn đến kết luận sai.

### Bước 4. Đánh giá design, implementation và operation

Lần lượt xác minh:

1. **Design adequacy:** control có xử lý mục tiêu và failure modes đáng quan tâm?
2. **Implementation coverage:** control đã tới mọi đối tượng/đường truy cập áp dụng?
3. **Operating effectiveness:** control hoạt động đúng trong phạm vi và kỳ đánh giá?
4. **Evidence sufficiency:** tài liệu/test/log có đủ để đưa ra kết luận?
5. **Ownership:** có người duy trì, kiểm tra và xử lý gap?

Chỉ được kết luận về những gì đã kiểm tra. Nếu test âm cho GET /api/invoices/{id} thành công nhưng không có test export, nên ghi **partial/evidence gap**, không mặc định “mọi API đã an toàn”.

### Bước 5. Phân loại gap và trạng thái

Một bộ trạng thái tham khảo:

| Trạng thái | Diễn giải | Hành động |
| --- | --- | --- |
| **Implemented and verified** | Control đáp ứng tiêu chí trong phạm vi đã kiểm tra, bằng chứng phù hợp | Theo dõi thay đổi và tái đánh giá theo kỳ |
| **Partial** | Mới đáp ứng một phần yêu cầu/phạm vi hoặc có lỗi giới hạn | Ghi gap cụ thể, làm rõ coverage |
| **Failed / ineffective** | Có bằng chứng không đạt tiêu chí | Khắc phục và đánh giá rủi ro |
| **Not implemented** | Chưa có control cần thiết | Thiết kế và triển khai |
| **Insufficient evidence** | Chưa đủ cơ sở để xác định đạt hay không | Bổ sung test/review/audit |
| **Exception approved** | Không đáp ứng nhưng có quyết định ngoại lệ hợp lệ, có điều kiện | Theo dõi rủi ro và hết hạn; không tính là đạt |
| **Not applicable** | Có căn cứ chính thức rằng requirement không áp dụng | Lưu lý do và xem lại khi scope đổi |

**Lưu ý:** “Exception approved” là một trạng thái quản trị, không phải một phép biến đổi control từ **failed** thành **effective**.

### Bước 6. Đánh giá và ưu tiên theo rủi ro

Không nên ưu tiên chỉ bằng **số lượng gap** hoặc nhãn severity từ công cụ. Cần xét:

- **Tài sản và hậu quả:** dữ liệu nào, số người ảnh hưởng, tác động bí mật/toàn vẹn/sẵn sàng?
- **Threat và mức phơi nhiễm:** có đường tấn công thực tế, đã được kiểm thử, yêu cầu đặc quyền gì?
- **Bản chất gap:** control hoàn toàn thiếu, hoạt động sai hay mới thiếu bằng chứng?
- **Biện pháp hiện có:** có control khác giảm tác động và đã được kiểm chứng không?
- **Phạm vi:** số hệ thống, tenant, tài khoản, vùng triển khai.
- **Độ tin cậy của kết luận:** bằng chứng trực tiếp hay suy luận từ mẫu nhỏ?
- **Nghĩa vụ:** có tiêu chí bắt buộc hoặc thời hạn không thể trì hoãn bằng chấp nhận nội bộ?

Ví dụ có thể dùng thang **Cao / Trung bình / Thấp** theo tiêu chí của tổ chức. Một **evidence gap** với tác động tiềm tàng rất lớn có thể đòi hỏi xác minh khẩn cấp, dù chưa có bằng chứng control thất bại.

### Bước 7. Chọn phương án và giao hành động

| Loại khoảng trống | Hành động điển hình | Điều kiện đóng |
| --- | --- | --- |
| Requirement/scope chưa rõ | Xác nhận applicability, làm rõ requirement | Có phạm vi và quyết định theo thẩm quyền |
| Design thiếu | Sửa security design, bổ sung control | Design review và tiêu chí chấp nhận rõ |
| Code/cấu hình thiếu | Triển khai sửa, bổ sung test | Test lại trên bản mục tiêu và đúng scope |
| Operating failure | Sửa giám sát/job/runbook, xử lý phụ thuộc | Có bằng chứng hoạt động trong kỳ phù hợp |
| Evidence thiếu | Chạy test/review/audit bổ sung | Bằng chứng đủ cho security claim |
| Ownership thiếu | Bổ nhiệm control owner và RACI | Trách nhiệm và đường chuyển cấp rõ |
| Ngoại lệ | Đánh giá residual risk và phê duyệt có hạn theo quyền | Ngoại lệ còn hiệu lực hoặc control đã được sửa và retest |

Mỗi finding nên có **gap ID, risk ID, action owner, mức ưu tiên, hạn, kế hoạch, bằng chứng yêu cầu và người xác minh**. Khi rủi ro hiện diện nghiêm trọng có thể cần tắt tính năng hoặc giảm thiểu tạm thời, không đợi hoàn tất biểu mẫu.

### Bước 8. Xác minh sửa lỗi và cập nhật risk/evidence

Một control gap **chưa nên đóng** chỉ vì pull request đã merge, tài liệu được cập nhật hoặc ticket được chuyển sang Done. Quy trình xác minh nên gồm:

1. Kiểm tra phiên bản triển khai và phạm vi ảnh hưởng.
2. Chạy lại kịch bản từng thất bại cùng các regression tests liên quan.
3. Kiểm tra phần còn lại của hệ thống không xuất hiện bypass tương tự.
4. Cập nhật bằng chứng đúng build, cấu hình, thời điểm và reviewer.
5. Đánh giá lại effectiveness và residual risk, nêu rõ giới hạn.
6. Đóng finding theo tiêu chí đã thống nhất và phê duyệt phù hợp.

Nếu kết quả retest cho thấy sửa một endpoint nhưng export vẫn rò dữ liệu, **gap chưa được giải quyết trong scope mục tiêu**.

### Bước 9. Theo dõi liên tục và cập nhật framework mapping

Gap analysis không chỉ thực hiện trước audit. Khi có API mới, thay IdP, đổi nhà cung cấp, nâng dependency, chuyển dữ liệu hoặc cập nhật standard/framework, phải rà soát:

- Applicability và control mapping có thay đổi?
- Những control nào chịu ảnh hưởng và cần test lại?
- Bằng chứng đã hết hạn hoặc sai bản chạy?
- Ngoại lệ có còn đủ điều kiện, risk owner có cần xem lại?
- Có lỗ hổng/incident cho thấy control design chưa đáp ứng?
- Framework phiên bản mới có được phê duyệt áp dụng chưa?

Mục tiêu là **assurance liên tục**, không phải dọn bảng gap một lần vào cuối quý.

## 6. Sơ đồ đánh giá và xử lý control gap

~~~mermaid
flowchart TD
    A["Chọn framework, phiên bản, phạm vi và applicability"] --> B["Ánh xạ objective/requirement tới control và owner"]
    B --> C["Thu thập thiết kế, cấu hình, test và evidence vận hành"]
    C --> D{"Đã có đủ căn cứ đánh giá?"}
    D -- "Chưa" --> E["Ghi evidence gap, xác minh bổ sung"]
    E --> C
    D -- "Có" --> F{"Control đáp ứng claim và scope?"}
    F -- "Có" --> G["Ghi verified và giới hạn kết luận"]
    F -- "Không" --> H["Phân loại design/implementation/operation/scope gap"]
    H --> I["Đánh giá likelihood, impact và rủi ro còn lại"]
    I --> J["Chọn treatment, giao owner, hạn và tiêu chí đóng"]
    J --> K["Thực hiện khắc phục hoặc ngoại lệ đúng thẩm quyền"]
    K --> L["Retest, review evidence và cập nhật risk"]
    L --> F
    G --> M["Theo dõi thay đổi và kỳ đánh giá mới"]
    M --> A
~~~

Sơ đồ mô tả quy trình thông thường. Nếu xuất hiện một **lỗi có nguy cơ hiện hữu nghiêm trọng**, nhóm cần đồng thời áp dụng biện pháp giảm thiểu hoặc ứng cứu phù hợp; không phải chờ tới khi việc mapping và bằng chứng hoàn tất.

## 7. Ví dụ xuyên suốt: Framework gap ở API xuất hóa đơn Java/Spring Boot

### 7.1. Hệ thống và target requirement

Giả sử một nền tảng SaaS chạy **Billing API** viết bằng Java/Spring Boot. Dữ liệu hóa đơn được tách theo tenant, trong đó tenant A **không được xem hóa đơn tenant B** nếu không có quyền ủy quyền cụ thể.

Tổ chức lựa chọn một nhóm objective kiểm soát truy cập trong control framework và chuyển thành yêu cầu nội bộ minh họa:

> **AUTHZ-OBJ-01:** Mọi đường đọc, tìm kiếm và xuất dữ liệu hóa đơn phải kiểm tra quyền của danh tính hiện tại trên từng đối tượng hoặc phạm vi kết quả; không được trả dữ liệu ngoài quyền.

**Security claim:** “Một người dùng tenant A không thể truy cập nội dung hóa đơn của tenant B qua GET chi tiết, danh sách hoặc endpoint export, trừ khi được ủy quyền hợp lệ theo policy.”

Đây là yêu cầu nội bộ **minh họa**, không phải nguyên văn điều khoản hay mã control của ISO/NIST/CIS.

### 7.2. Luồng dữ liệu và trust boundary

~~~mermaid
flowchart LR
    U["Client tenant A (untrusted)"] -->|"JWT, invoiceId, filter"| G["API Gateway"]
    G --> A["Billing API (Spring Boot)"]
    A --> DB[("Invoices DB")]
    A --> Q["Export Queue"]
    Q --> W["Export Worker"]
    W --> OBJ[("Object Storage")]
    A -->|"Export job/status"| U
    W -. "Tạo file xuất theo danh tính/quyền đã kiểm chứng" .-> OBJ
~~~

Giả định nguy hiểm là **“client đã đăng nhập nên có thể export tất cả hóa đơn”**. Xác thực không thay thế phân quyền trên từng tài nguyên, và kiểm tra quyền ở GET chi tiết không tự áp dụng cho worker tạo file.

Cần xác minh:

- Gateway và Billing API xử lý identity/tenant context thế nào.
- Controller/list/export có cùng policy phân quyền không.
- Worker nhận danh tính hoặc phạm vi đã được kiểm chứng hay chỉ nhận tenant ID do client cung cấp.
- Object storage có cấp quyền tải file theo đúng user/tenant và hạn hiệu lực không.
- Có khả năng thay đổi request, job ID hoặc đường dẫn tải để xem dữ liệu của người khác không.

### 7.3. Đánh giá hiện trạng và phát hiện giả định

| Luồng | Evidence giả định | Nhận định |
| --- | --- | --- |
| GET /api/invoices/{id} | Test A đọc A được, A đọc B bị từ chối | **Verified** với endpoint/build đã kiểm tra |
| GET /api/invoices | Có code lọc tenant, nhưng chưa có test dữ liệu hỗn hợp | **Insufficient evidence** đối với tập kết quả |
| POST /api/invoices/export | Test giả định cho thấy file của A chứa hóa đơn B | **Implementation/operating gap đã xác nhận** trong kịch bản thử |
| GET /api/exports/{jobId}/download | Chưa có test phân quyền tải file | **Evidence gap**, chưa kết luận đạt/thất bại |
| Export worker → object storage | Chưa rõ principal và cơ chế cấp quyền file | **Design/ownership question** cần làm rõ |

Tất cả kết quả trong bảng là **kịch bản giả định phục vụ học tập**, không phải phát hiện trên hệ thống thật.

Cách ghi chính xác hơn “Billing API không an toàn” là:

> “Có bằng chứng rằng đường export không thực thi yêu cầu AUTHZ-OBJ-01 trong tình huống A xuất được dữ liệu B. Các đường list và download chưa đủ bằng chứng. Endpoint GET chi tiết đạt những test đã chạy; phải khắc phục export, đánh giá đường tải file và retest trên phiên bản triển khai.”

### 7.4. Thiết kế control ở tầng Java

Đối với đọc một hóa đơn, có thể truy vấn theo **invoiceId và tenantId lấy từ security context tin cậy**:

~~~java
@Service
public class InvoiceQueryService {
    private final InvoiceRepository invoices;
    private final CurrentTenant currentTenant;

    public InvoiceQueryService(InvoiceRepository invoices,
                               CurrentTenant currentTenant) {
        this.invoices = invoices;
        this.currentTenant = currentTenant;
    }

    @Transactional(readOnly = true)
    public InvoiceView read(UUID invoiceId) {
        UUID tenantId = currentTenant.requireVerifiedTenantId();

        return invoices.findByIdAndTenantId(invoiceId, tenantId)
            .map(InvoiceView::from)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
~~~

Đây là **đoạn mã minh họa**, chưa thể chạy độc lập; InvoiceRepository, CurrentTenant và InvoiceView phải được triển khai trong dự án. CurrentTenant phải xác định tenant theo danh tính đã xác thực và **xác minh principal được phép hành động trong tenant đó**, không chỉ đọc một claim không được kiểm chứng hoặc tham số client tự khai. Chính sách riêng cho vai trò quản trị hoặc ủy quyền hợp lệ phải được kiểm tra riêng.

Trả **403** hoặc **404** khi không đủ quyền tùy theo policy API; trong mọi trường hợp không được tiết lộ dữ liệu hóa đơn ngoài quyền.

**Quan trọng:** control ở phương thức read() không bảo đảm endpoint **export** an toàn. Đường xuất phải giới hạn **toàn bộ tập hóa đơn**, truyền phạm vi quyền an toàn đến worker và kiểm soát quyền trên file tải về. Không sử dụng một tenantId tùy ý trong job payload rồi mặc định nó đáng tin.

### 7.5. Kế hoạch kiểm thử làm rõ gap và chứng minh sửa lỗi

| Test | Dữ liệu và hành vi | Kết quả kỳ vọng |
| --- | --- | --- |
| A đọc hóa đơn của A | A có quyền, hóa đơn thuộc A | Trả đúng dữ liệu |
| A đọc hóa đơn B | B khác tenant, A không có quyền | Từ chối và không tiết lộ nội dung |
| A liệt kê với dữ liệu lẫn A/B | Database có hóa đơn của cả hai tenant | Chỉ có hóa đơn A được phép xem |
| A export với tập dữ liệu lẫn A/B | Job tạo file với dữ liệu hỗn hợp | File không chứa hóa đơn B |
| A sửa filter, ID hoặc job ID | Thay tham số nhằm vượt qua lọc quyền | Không cấp thêm quyền ngoài policy |
| B tải export job của A | B không được phép xem job/file của A | Từ chối |
| Role được ủy quyền hợp lệ | Policy cấp quyền theo phạm vi có điều kiện | Chỉ truy cập đúng phạm vi |
| Token thiếu, sai hoặc hết hạn | Không có danh tính hợp lệ | Từ chối theo chính sách xác thực |
| Phiên bản đã sửa | Build và cấu hình mục tiêu | Retest đạt, kèm regression các đường khác |

Một ca test âm với Spring Security Test có thể được diễn đạt như sau:

~~~java
@Test
void userFromTenantACannotReadTenantBInvoice() throws Exception {
    mockMvc.perform(
        get("/api/invoices/{id}", invoiceOwnedByB)
            .with(jwt().jwt(jwt ->
                jwt.claim("tenant_id", tenantAId.toString())))
    )
    .andExpect(status().isNotFound());
}
~~~

Mã chỉ thể hiện **ý tưởng kiểm thử**; cần cấu hình MockMvc, security mapping, fixture, Principal và các biến invoiceOwnedByB, tenantAId phù hợp. JWT dựng trong test **không thay thế** việc kiểm tra chữ ký, issuer, audience và ánh xạ quyền ở môi trường tích hợp thực. Không chỉ kiểm tra status: cần xác nhận response **không chứa dữ liệu ngoài quyền**.

Khi export đã sửa, test cần đọc **nội dung file được tạo** và kiểm tra trường hợp dữ liệu A/B hỗn hợp; chỉ thấy API trả HTTP 200 không đủ chứng minh quyền xuất dữ liệu đúng.

### 7.6. Gap register cho tình huống

Mẫu YAML dưới đây là **hồ sơ giả định**, chưa mang bằng chứng audit thực:

~~~yaml
gap_id: "GAP-AUTHZ-DEMO-009"
framework:
  name: "Control framework noi bo tham chieu"
  edition: "demo-revision"
requirement:
  id: "AUTHZ-OBJ-01"
  claim: "Moi duong doc va export chi tra du lieu trong quyen"
scope:
  service: "billing-api"
  environment: "integration"
  build: "demo-build-before-fix"
  functions:
    - "GET /api/invoices/{id}"
    - "GET /api/invoices"
    - "POST /api/invoices/export"
    - "GET /api/exports/{jobId}/download"
asset: "Du lieu hoa don theo tenant"
gap:
  types:
    - "IMPLEMENTATION"
    - "OPERATING"
  confirmed_scenario: "A export duoc hoa don tenant B trong test gia dinh"
  evidence_gaps:
    - "Chua test list voi du lieu hon hop"
    - "Chua test phan quyen tai file download"
risk:
  likelihood: "CAN_DANH_GIA"
  impact: "CAO_NEU_LO_DU_LIEU_NHAY_CAM"
  confidence: "CAO_VOI_TEST_GIA_DINH_DA_XAC_NHAN"
  risk_owner: "Billing Product Owner"
control_owner: "Billing API Tech Lead"
action_owner: "Billing Engineering Team"
treatment:
  strategy: "MITIGATE"
  actions:
    - "Loc du lieu export theo quyen duoc xac minh"
    - "Kiem tra quyen tai export job va download"
    - "Them integration/e2e tests va review worker"
  closure_criteria:
    - "Retest A/B, list, export va download tren build muc tieu"
    - "Review khong con duong bypass trong scope"
  verification_status: "PENDING"
evidence:
  - ref: "TEST-DEMO-BILLING-EXPORT"
    actual_run_link: null
exception:
  approved: false
  approval_ref: null
~~~

Trong hồ sơ thực, cần thêm ngày giờ, người đánh giá, đường dẫn bằng chứng thật, risk rating theo phương pháp tổ chức, hạn và lịch sử quyết định. Không nên để giá trị giả định trong một báo cáo tuân thủ chính thức.

## 8. Từ gap đến remediation có thể kiểm chứng

### 8.1. Phân tích nguyên nhân gốc

Ví dụ, nguyên nhân “export chưa phân quyền” có thể bắt nguồn từ:

- Requirement chỉ nêu “GET endpoint” mà không đề cập batch/export.
- Thiết kế tin rằng API gateway đã xử lý mọi authorization.
- Worker sử dụng tài khoản database có quyền đọc rộng và không mang principal context.
- Code review không có checklist kiểm tra phân quyền cho endpoint mới.
- Bộ test chỉ kiểm tra response thành công, không có negative cases.
- Không có owner chịu trách nhiệm cho object storage download.

Đây là **nhiều lớp nguyên nhân**. Chỉ sửa một dòng code có thể không giải quyết những khoảng trống về requirement và test khiến lỗi tái diễn.

### 8.2. Remediation plan phải trả lời được điều gì?

| Trường | Mục đích |
| --- | --- |
| Gap ID / risk ID | Gắn phát hiện với đánh giá rủi ro |
| Requirement / control ID | Biết cần đáp ứng tiêu chí nào |
| Root cause | Xác định vì sao control không đạt |
| Action owner | Người chịu trách nhiệm triển khai |
| Due date / milestone | Mốc và điều kiện chuyển cấp |
| Temporary mitigation | Giảm phơi nhiễm trong thời gian chưa sửa |
| Fix design | Thay đổi nào được đề xuất, phạm vi tác động |
| Verification method | Chạy test, review, audit hay diễn tập nào |
| Closure criteria | Điều kiện đóng rõ, không chỉ ghi “đã sửa” |
| Reviewer / risk approver | Ai xác minh, ai quyết định residual risk |
| Next reassessment trigger | Khi nào kết luận phải được xem lại |

Bằng chứng retest cần liên kết với **đúng build, môi trường và phạm vi**, tránh trường hợp test bản sửa ở staging rồi production vẫn chạy bản cũ.

### 8.3. Temporary control và compensating control

Khi không thể xử lý ngay, nhóm có thể sử dụng biện pháp bù trừ như **tạm tắt export**, giới hạn quyền hoặc yêu cầu phê duyệt bổ sung, nếu phù hợp với threat và được cho phép.

Tuy nhiên:

- Một WAF không tự sửa lỗi object authorization.
- Đưa endpoint sau VPN không chắc loại bỏ rủi ro từ tài khoản nội bộ bị lạm dụng.
- Chỉ giám sát hành vi lạ thường không ngăn dữ liệu đã bị tiết lộ.
- Một control bù trừ phải có **mục tiêu, phạm vi, bằng chứng và thời hạn**.

Chấp nhận **residual risk** hoặc ngoại lệ thuộc người có quyền theo quy chế. Không dùng trạng thái “Exception approved” để biến control không đạt thành “Implemented and verified”.

## 9. Chất lượng bằng chứng và kết luận assurance

### 9.1. Các thuộc tính cần đánh giá

| Thuộc tính | Câu hỏi |
| --- | --- |
| **Relevance** | Evidence có kiểm chứng đúng claim/requirement? |
| **Scope** | Có đúng hệ thống, tenant, endpoint, môi trường, khoảng thời gian? |
| **Freshness** | Có phù hợp với build/cấu hình hiện hành, đã thay đổi gì? |
| **Coverage** | Đã kiểm tra các trường hợp âm, dương, biên và luồng thay thế? |
| **Integrity** | Có nguồn gốc, người/công cụ tạo, khả năng xác minh và bảo vệ chống sửa đổi? |
| **Repeatability** | Có thể tái chạy hoặc tái dựng phương pháp đánh giá nếu cần? |
| **Independence** | Reviewer có đủ độc lập theo mức rủi ro và yêu cầu kiểm toán? |
| **Retention** | Hồ sơ được lưu an toàn và đủ thời hạn theo chính sách áp dụng? |

**Một báo cáo test PASS không thay thế ma trận coverage.** Nếu 10 test đều PASS nhưng không thử export, không thể dùng kết quả đó để đóng gap về export.

### 9.2. Lấy mẫu và giới hạn suy luận

Khi kiểm tra nhiều ứng dụng hoặc control instance, có thể cần **sampling**:

- Xác định tổng thể: số service, endpoint, tài khoản hoặc bản ghi.
- Xác định cách chọn mẫu: rủi ro, sự biến động, loại control, ngẫu nhiên có thiết kế...
- Ghi số lượng mẫu, thời điểm, đặc điểm các đối tượng bị loại trừ.
- Nêu rõ phát hiện trên mẫu có được mở rộng điều tra phần còn lại không.
- Không tự tuyên bố mức bảo đảm thống kê nếu phương pháp chọn mẫu không hỗ trợ.

Ví dụ, kiểm tra 8/40 service và tất cả đều PASS **không chứng minh** 32 service khác cũng đạt. Thông tin đó chỉ hỗ trợ kết luận đối với mẫu và các giả định hợp lý được nêu.

### 9.3. Trạng thái kết luận nên mang ý nghĩa gì?

- **Verified in scope:** đạt các tiêu chí được kiểm tra; ghi phạm vi và giới hạn.
- **Failed:** có bằng chứng không đạt yêu cầu.
- **Partially verified:** một phần có bằng chứng, phần còn lại chưa được kiểm tra.
- **Insufficient evidence:** không đủ căn cứ để kết luận đạt hoặc không đạt.
- **Exception with residual risk:** chưa đáp ứng nhưng có quyết định quản trị có điều kiện; không được ghi “đạt”.
- **Not applicable with rationale:** có cơ sở được phê duyệt rằng yêu cầu không áp dụng.

Một báo cáo đáng tin thường có câu:

> “Control kiểm tra quyền cấp hóa đơn đạt các trường hợp GET chi tiết trên build X được đánh giá. Đường export đã xác nhận không đạt; đường download chưa đủ bằng chứng. Chưa thể kết luận toàn bộ nhóm control đạt yêu cầu framework; cần khắc phục và retest trước khi xem xét residual risk.”

Câu này hữu ích hơn “Control access = 80% compliant” nếu thiếu định nghĩa mẫu số và bản chất của phần không đạt.

## 10. Đo lường control gap bằng KPI/KRI

Các chỉ số hữu ích nên giúp **phát hiện khoảng trống thực sự và theo dõi khắc phục**, không chỉ đếm số dòng đã gắn nhãn.

| Chỉ số | Cách dùng | Cảnh báo |
| --- | --- | --- |
| **Applicable requirements mapped** | Số requirement áp dụng có mapping tới control / tổng requirement áp dụng | Mapping không chứng minh control hiệu quả |
| **Verified control coverage** | Số control/scope đã có bằng chứng đạt / tổng control/scope áp dụng | Không xem mọi control có trọng số rủi ro như nhau |
| **Critical gap age** | Thời gian các gap trọng yếu còn mở | Phải phân biệt gap thật và thiếu bằng chứng |
| **Verified remediation rate** | Số gap đóng sau retest / số gap đến hạn đánh giá | “Ticket Done” chưa đủ |
| **Repeat gap rate** | Tần suất lỗi tái diễn sau khắc phục | Cần xét khác biệt threat và phạm vi |
| **Evidence currency** | Tỷ lệ bằng chứng còn hiệu lực đúng version và kỳ đánh giá | Bằng chứng “có file” nhưng sai scope không tính |
| **Exception overdue** | Số ngoại lệ quá hạn, mức rủi ro và thời gian phơi nhiễm | Ngoại lệ có phê duyệt vẫn có residual risk |
| **Time to assign owner** | Thời gian từ ghi nhận gap đến khi có action owner | Owner trên giấy chưa đủ quyền giải quyết |
| **Control drift frequency** | Mức độ control lệch baseline và thời gian tồn tại | Cần xét tác động từng sai lệch |
| **High-risk scope unassessed** | Tài sản quan trọng chưa có đánh giá đủ | Không làm mất dấu “unknown” trong trung bình |

**Ví dụ minh họa:** 30 control yêu cầu được xác định áp dụng trong một scope. Có 18 control đạt với bằng chứng, 4 không đạt, 5 chưa đủ bằng chứng, 2 có ngoại lệ và 1 đang đánh giá. Khi đó **verified coverage = 18/30 = 60%**, không phải 24/30 vì “4 cái đang sửa và 2 cái có ngoại lệ”.

Con số 60% **không có nghĩa hệ thống an toàn 60%**. Một control liên quan khóa ký hoặc phân quyền tenant có thể quan trọng hơn nhiều control hành chính có mức rủi ro thấp.

### 10.1. Chỉ số chất lượng chứ không chỉ số lượng

Nếu chỉ đặt mục tiêu “giảm số gap”, nhóm có thể chuyển **Failed** thành **Unknown**, hoặc xóa mục không thuận lợi. Cách đo đúng cần xem:

- Xu hướng risk exposure và **critical gaps còn mở**.
- Tỷ lệ có **evidence hợp lệ** và retest đạt.
- Những gap tái diễn do root cause chưa được xử lý.
- Ngoại lệ quá hạn, scope thay đổi và phần chưa được đánh giá.
- Khả năng phát hiện sớm gap khi thay đổi hệ thống.

## 11. Các vai trò và trách nhiệm

| Vai trò | Nhiệm vụ | Không được tự suy |
| --- | --- | --- |
| **Framework / GRC owner** | Duy trì framework mapping, phiên bản, applicability và báo cáo gap | Không tự tuyên bố control đã vận hành tốt |
| **Risk owner** | Đánh giá tác động và quyết định xử lý/chấp nhận residual risk theo quyền | Không mặc định là người triển khai kỹ thuật |
| **Control owner** | Thiết kế, bảo đảm triển khai/vận hành và bằng chứng; điều phối sửa gap | Không có quyền chấp nhận mọi rủi ro |
| **Engineering / SRE / operator** | Triển khai, kiểm thử, giám sát, cung cấp evidence và retest | PR hoàn thành không tự đóng finding |
| **Security architect/analyst** | Đánh giá threat scenario, thiết kế control và cách kiểm chứng | Không thay thế người chịu trách nhiệm nghiệp vụ |
| **Assurance reviewer / auditor** | Đánh giá bằng chứng độc lập khi cần, báo cáo giới hạn và findings | Không thực hiện thay remediation trong vai trò audit |
| **Policy / standard owner** | Định nghĩa yêu cầu bắt buộc, phiên bản và phạm vi áp dụng | Danh mục framework không tự tạo nghĩa vụ không có căn cứ |

Với control dùng chung, cần phân định **ai chịu trách nhiệm control nền tảng, ai cấu hình tích hợp từng service và ai tổng hợp kết luận**. Ví dụ, IdP cung cấp cơ chế xác thực; mỗi ứng dụng vẫn phải kiểm tra authorization theo chức năng và tài nguyên.

### 11.1. RACI minh họa

*R = trực tiếp thực hiện; A = chịu trách nhiệm cuối cùng; C = tham vấn; I = được thông báo.*

| Hoạt động | Framework/GRC owner | Control owner | Kỹ thuật/vận hành | Risk owner | Assurance/audit |
| --- | --- | --- | --- | --- | --- |
| Chọn framework, áp dụng và mapping | **A/R** | C | C | C | C |
| Cung cấp evidence và đánh giá hiện trạng control | C | **A** | R | I | C |
| Đánh giá độc lập bằng chứng (khi được yêu cầu) | C | C | C | I | **A/R** |
| Đánh giá tác động kinh doanh và xử lý rủi ro | C | C | C | **A/R** | I |
| Khắc phục gap về control | I | **A** | R | C | C |
| Retest, cập nhật mapping và trạng thái gap | **R** | **A** | R | I | C |
| Chấp nhận residual risk theo thẩm quyền | I | C | C | **A/R** | I |

RACI chỉ là ví dụ; quyền quyết định thực tế theo cơ cấu tổ chức. Không vì một người vừa viết code vừa chạy test mà mặc định kết luận đó đủ tính độc lập cho mọi control rủi ro cao.

## 12. Các sai lầm thường gặp

### 12.1. So framework theo tên control mà không xét applicability

**Sai:** thấy “backup control” xuất hiện trong danh mục là kết luận mọi thành phần đều phải có cùng cơ chế backup.

**Đúng:** xác định tài sản, rủi ro, phạm vi và tiêu chí bắt buộc; ghi lý do áp dụng và không áp dụng có căn cứ.

### 12.2. Coi một policy đã được ký là bằng chứng control đạt

Policy có thể yêu cầu MFA nhưng cấu hình một số tài khoản service hoặc admin vẫn không có bảo vệ thích hợp. **Phải đánh giá implementation và operating effectiveness**, không chỉ existence.

### 12.3. Đánh đồng “thiếu evidence” với “control thất bại”

Thiếu test khôi phục chưa chứng minh backup chắc chắn hỏng, nhưng cũng **không đủ để xác nhận khả năng phục hồi**. Giữ trạng thái riêng và giao hành động đánh giá.

### 12.4. Cho một control dùng chung bao phủ mọi service

Có gateway xác thực không có nghĩa các endpoint nội bộ hoặc worker đã được phân quyền theo tài nguyên. **Phải xác minh shared responsibility và từng đường tích hợp.**

### 12.5. Lấy điểm severity của vulnerability làm mức risk cuối cùng

Điểm kỹ thuật không phản ánh đầy đủ tài sản, tác động kinh doanh, exposure hoặc hiệu lực control. **Đánh giá risk scenario và bằng chứng riêng.**

### 12.6. Chấm điểm coverage rồi tuyên bố hệ thống an toàn theo tỷ lệ

Nếu 95% control được đánh dấu đạt nhưng 5% còn lại gồm kiểm soát khóa bí mật hoặc truy cập dữ liệu nhạy cảm, kết luận “an toàn 95%” là sai. **Báo cả mức trọng yếu, loại gap và phần chưa xác minh.**

### 12.7. Đóng finding khi đã tạo ticket hoặc merge PR

**Hành động triển khai không phải bằng chứng thành công.** Cần retest trên build/môi trường mục tiêu, bảo đảm các đường tương tự không còn lỗi.

### 12.8. Giảm gap bằng cách cấp ngoại lệ vô hạn

Ngoại lệ không làm control hiệu quả hơn. **Đòi hỏi thẩm quyền, rủi ro, biện pháp bù trừ, thời hạn và lịch đánh giá lại**; không miễn trừ được nghĩa vụ bắt buộc bằng quyết định nội bộ.

### 12.9. Không cập nhật mapping theo phiên bản framework

Một phiên bản framework hoặc internal standard mới có thể thay đổi scope/tiêu chí. **Ghi ID, edition, lịch sử mapping và đánh giá tác động**; không tái sử dụng bằng chứng cũ cho yêu cầu mới nếu không xác minh độ phù hợp.

### 12.10. Không xét lỗ hổng nghiệp vụ

Quét dependency có thể PASS, nhưng lỗi **người dùng A xuất dữ liệu B** là khoảng trống authorization không nhất thiết xuất hiện trong danh sách CVE. **Kết hợp threat modeling, review logic, negative tests và kiểm thử nghiệp vụ.**

## 13. Checklist control gap assessment

- [ ] Framework/standard có tên, phiên bản, phạm vi và tiêu chí áp dụng được phê duyệt.
- [ ] Tài sản, dữ liệu, môi trường và hệ thống trong scope được xác định rõ.
- [ ] Các requirement bắt buộc đã có ID, mô tả kiểm chứng được và owner.
- [ ] Các mục không áp dụng có lý do, bằng chứng và cấp xác nhận phù hợp.
- [ ] Requirement được ánh xạ tới control thực tế, không chỉ tới tên công cụ.
- [ ] Đã đánh giá hiệu quả thiết kế, phạm vi triển khai và vận hành theo kỳ.
- [ ] Evidence có build, thời điểm, môi trường, nguồn, kết quả và reviewer.
- [ ] Đã xem các luồng mới, worker, batch, export và ranh giới tin cậy.
- [ ] Gap được phân loại: requirement, design, implementation, operation, evidence hoặc ownership.
- [ ] Phân biệt **Failed**, **Partial**, **Insufficient evidence**, **Not applicable** và **Exception approved**.
- [ ] Mức ưu tiên dựa trên risk scenario, impact và exposure chứ không chỉ điểm checklist.
- [ ] Mỗi gap có control owner, risk owner, action owner, hạn và điều kiện đóng.
- [ ] Ngoại lệ có đánh giá rủi ro, phê duyệt, control bù trừ và ngày hết hạn.
- [ ] Bản sửa được triển khai và **retest trên môi trường/build có liên quan**.
- [ ] Đã cập nhật framework mapping, control register, risk register và evidence.
- [ ] Có trigger đánh giá lại khi thay đổi kiến trúc, framework, tiêu chuẩn hoặc có sự cố.
- [ ] Kết luận chỉ tuyên bố đạt trong **phạm vi bằng chứng đã hỗ trợ**.

Checklist là công cụ điều phối; **việc đánh dấu đủ ô không thay thế kết quả assurance hoặc audit**.

## 14. Câu hỏi tự kiểm tra

1. Control gap khác vulnerability và incident ở điểm nào?
2. Tại sao một mục có trong framework không mặc định bắt buộc áp dụng cho mọi hệ thống?
3. Nếu control đã có code và cấu hình nhưng chưa được test, nên dùng trạng thái gì? Vì sao không tự kết luận đạt/không đạt?
4. Hãy phân biệt design gap, implementation gap, operating gap và evidence gap qua API xuất dữ liệu nhiều tenant.
5. Vì sao kiểm tra phân quyền endpoint GET chi tiết không chứng minh endpoint export và download file cũng an toàn?
6. Một control tập trung ở IdP có thể được xem là “đã thừa kế” hoàn toàn cho mọi ứng dụng không? Những trách nhiệm còn lại ở service là gì?
7. Khi cùng một gap ảnh hưởng nhiều framework requirement, có nên tạo nhiều bản sửa kỹ thuật giống nhau không? Nên mapping thế nào?
8. Khi nào có thể đánh dấu một requirement là Not applicable và ai xác nhận?
9. Nếu 18/30 control đã được xác minh đạt, 2 có ngoại lệ, 5 chưa có evidence và 5 chưa đạt, nên báo tỷ lệ verified thế nào? Có thể nói hệ thống an toàn 60% không?
10. Nếu code đã sửa nhưng chưa được triển khai production, gap đã đủ điều kiện đóng chưa?
11. Một finding về export trả dữ liệu trái quyền nên có những trường nào trong remediation record?
12. Risk owner và control owner có trách nhiệm khác nhau thế nào khi cần chấp nhận một residual risk?
13. Khi framework đổi edition hoặc thêm service mới, nhóm cần đánh giá lại những mapping và evidence nào?
14. Vì sao lấy mẫu nhỏ không tự chứng minh toàn bộ danh mục control đã được triển khai đúng?

## 15. Tổng kết

**Control gap** là **khoảng cách giữa yêu cầu kiểm soát cần đạt và thực trạng được triển khai, vận hành hoặc có thể chứng minh**. Trong một **control framework**, phải bắt đầu bằng phạm vi và **applicability**, ánh xạ yêu cầu tới control và bằng chứng, phân biệt rõ **thiếu thiết kế, thiếu triển khai, lỗi vận hành, thiếu evidence và thiếu ownership**, rồi ưu tiên theo **rủi ro thực tế**. Mọi khoảng trống được xử lý cần có người chịu trách nhiệm, tiêu chí đóng và **kiểm thử/xác minh lại**; ngoại lệ có phê duyệt không tự trở thành trạng thái đạt. Giá trị của control gap analysis đối với **SECURITY_SECURITY_ASSURANCE** là tạo một vòng assurance liên tục, có thể truy vết từ **risk → framework requirement → control → evidence → finding → remediation → retest → residual risk decision**, giúp tổ chức đưa ra kết luận bảo mật có căn cứ thay vì chỉ sở hữu một bảng checklist.
