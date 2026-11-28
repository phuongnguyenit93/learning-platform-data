# Corrective Control (Kiểm soát khắc phục) trong Security Assurance

## 1. Vì sao phát hiện lỗi chưa phải là xử lý rủi ro?

Một công cụ kiểm thử phát hiện API có thể đọc hóa đơn của tenant khác. Hệ thống SIEM ghi lại hàng loạt lần đăng nhập bất thường. Bộ giám sát cấu hình cảnh báo một bucket chứa dữ liệu khách hàng vừa chuyển sang chế độ công khai. Đây đều là những phát hiện có giá trị, nhưng **phát hiện không đồng nghĩa với khắc phục**.

Nếu không có cơ chế sửa trạng thái sai, cô lập tác động, xử lý nguyên nhân, kiểm tra kết quả và ngăn vấn đề tái xuất hiện, tổ chức vẫn có thể chịu cùng một sự cố sau khi cảnh báo đã được đóng.

**Corrective control (kiểm soát khắc phục)** là biện pháp tổ chức, quy trình hoặc kỹ thuật được thiết kế nhằm **điều chỉnh một trạng thái, sai lệch hoặc hậu quả không mong muốn đã được phát hiện**, qua đó đưa hệ thống/hoạt động về trạng thái phù hợp và/hoặc giảm rủi ro tiếp diễn. Tùy kịch bản, corrective control có thể bao gồm tự động thu hồi quyền sai, sửa cấu hình không an toàn, vô hiệu hóa thông tin xác thực bị lộ, triển khai bản vá, khắc phục lỗi logic và xác minh rằng kết quả cần đạt đã xuất hiện.

Trong module **SECURITY_SECURITY_ASSURANCE**, người học cần biết **đánh giá có bằng chứng** rằng hệ thống đáp ứng mục tiêu bảo mật, đi từ rủi ro và requirements tới security controls, kiểm thử, audit, khắc phục phát hiện và assurance liên tục. Vì vậy, corrective control không chỉ là “nút sửa lỗi”, mà là một **chuỗi hành động có đầu vào, thẩm quyền, tiêu chí kết thúc và bằng chứng kiểm tra**.

> Một corrective control tốt không đòi hệ thống “không bao giờ gặp lỗi”. Nó đòi **khi sai lệch thuộc phạm vi kiểm soát xuất hiện**, tổ chức có khả năng phát hiện hoặc nhận tín hiệu phù hợp, xử lý bằng phương án được phép, kiểm tra kết quả và quản lý phần rủi ro còn lại.

### Ví dụ mở đầu

Một công cụ quản trị cloud liên tục kiểm tra bucket. Khi phát hiện chính sách cho phép truy cập công khai ngoài ý muốn, nó phát cảnh báo và tự động khôi phục cấu hình không công khai theo baseline đã được phê duyệt.

- **Detective control:** phát hiện chính sách bucket sai.
- **Corrective control:** áp lại chính sách quyền đúng, kiểm tra cấu hình đã có hiệu lực và ghi kết quả.
- **Hoạt động xử lý sự cố có thể cần thêm:** kiểm tra xem dữ liệu đã bị đọc trước lúc sửa chưa, bảo toàn log, đánh giá phạm vi ảnh hưởng và thực hiện thông báo theo nghĩa vụ nếu áp dụng.

Nếu chỉ “sửa bucket về private” rồi tuyên bố không có lộ dữ liệu, kết luận đó vượt quá bằng chứng hiện có.

## 2. Corrective control khác các nhóm security control như thế nào?

Việc phân loại giúp hiểu **vai trò trong chuỗi bảo vệ**, không nhất thiết gắn mỗi biện pháp vào duy nhất một nhãn.

| Nhóm control | Trọng tâm | Ví dụ | Điều chưa được chứng minh chỉ từ sự tồn tại của control |
| --- | --- | --- | --- |
| **Preventive** – Phòng ngừa | Ngăn hoặc giảm khả năng hành vi không mong muốn xảy ra. | Object-level authorization chặn đọc dữ liệu khác tenant; MFA cho quản trị. | Không bảo đảm mọi đường truy cập đều được bao phủ. |
| **Detective** – Phát hiện | Nhận ra hành vi, sự kiện hoặc trạng thái sai lệch. | SIEM alert, cấu hình drift detection, phát hiện malware. | Không chứng minh đã khắc phục, giới hạn hậu quả hay phục hồi. |
| **Corrective** – Khắc phục | Thực hiện hoặc điều phối sửa trạng thái/hành vi sau sai lệch, với điều kiện và xác minh rõ. | Thu hồi quyền cấp sai, khóa credential bị lộ, vá lỗi phân quyền, khôi phục cấu hình. | Không tự chứng minh nguyên nhân gốc đã được loại bỏ hoặc thiệt hại đã hết. |
| **Recovery** – Phục hồi | Khôi phục dịch vụ, dữ liệu hoặc năng lực hoạt động sau gián đoạn/tổn hại. | Khôi phục từ backup, failback, tái xây dựng hệ thống. | Phục hồi chức năng không đồng nghĩa lỗ hổng gây sự cố đã được xử lý. |
| **Compensating** – Bù đắp | Cung cấp một phương án khác để đạt mục tiêu kiểm soát khi biện pháp chuẩn chưa thể triển khai. | Giám sát và hạn chế quyền bổ sung trong lúc chờ sửa hệ thống cũ. | Biện pháp bù đắp phải được đánh giá hiệu quả, không tự là ngoại lệ được chấp nhận. |
| **Directive** – Chỉ đạo | Quy định, yêu cầu hoặc hướng dẫn hành vi cần thực hiện. | Quy trình phải thu hồi credential đã bị lộ. | Tài liệu có quy trình không chứng minh người vận hành đã làm đúng khi cần. |

**Một biện pháp có thể thực hiện nhiều chức năng.** Ví dụ hệ thống tự động cách ly máy trạm khi phát hiện hành vi độc hại: phần **phát hiện** là detective, phần **cách ly và loại bỏ nguy cơ lan truyền** là corrective/containment, còn khôi phục máy tới trạng thái sử dụng an toàn có thể được xem là recovery. Phân loại cần bám **mục đích được kiểm tra**.

### Correction, containment, remediation, corrective action và recovery

Trong thực tế, các từ này thường xuất hiện cùng nhau:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Containment – Khoanh vùng** | Làm gì ngay để hạn chế thiệt hại tiếp diễn? | Chặn export endpoint đang lộ, cô lập tài khoản bị chiếm. |
| **Correction – Sửa sai lệch cụ thể** | Trạng thái sai nào cần đưa về đúng ngay? | Đổi bucket về private, thu hồi một quyền không hợp lệ. |
| **Remediation – Khắc phục vấn đề** | Làm gì để loại bỏ hoặc giảm nguyên nhân tạo ra lỗ hổng/sai lệch? | Sửa logic authorization, sửa quy tắc IaC và deploy. |
| **Corrective action – Hành động khắc phục có hệ thống** | Làm gì với nguyên nhân gốc để giảm nguy cơ tái diễn? | Bổ sung security requirements, test hợp đồng phân quyền, policy-as-code và review. |
| **Recovery – Phục hồi** | Khôi phục dữ liệu, chức năng và tính nhất quán ra sao? | Restore dữ liệu, đối soát giao dịch và cho chạy lại dịch vụ. |

Các giai đoạn có thể **song song hoặc lặp lại** tùy mức nguy hiểm. Khoanh vùng không thay thế khắc phục nguyên nhân; khắc phục mã nguồn không thay thế xử lý dữ liệu đã bị xuất; phục hồi không bảo đảm môi trường đã sạch hoặc có thể vận hành an toàn.

## 3. Bắt đầu thiết kế từ risk scenario và kết quả mong muốn

Một corrective control chỉ có thể kiểm chứng khi biết rõ **sai lệch nào phải xử lý** và **trạng thái an toàn sau xử lý**.

Ví dụ chưa tốt:

> “Đội security phải sửa mọi lỗi nhanh chóng.”

Ví dụ rõ hơn:

> “Khi phát hiện một service account production có quyền truy cập ngoài phạm vi đã được phê duyệt, hệ thống phải ghi nhận phát hiện, xác định owner, thực hiện thu hồi quyền vượt phạm vi theo quy trình và xác minh quyền không còn tồn tại trên các đường truy cập liên quan; trường hợp thu hồi có thể làm gián đoạn dịch vụ phải có phương án xử lý rủi ro và phê duyệt thích hợp.”

Một bản mô tả control nên có:

1. **Risk scenario:** sai lệch có thể dẫn tới sự kiện/hậu quả nào?
2. **Control objective:** mục tiêu cụ thể sau khi corrective action thành công.
3. **Trigger:** phát hiện/cảnh báo, kết quả audit, incident, test fail hoặc thay đổi nào kích hoạt.
4. **Scope:** dịch vụ, tài sản dữ liệu, môi trường, tài khoản, tenant và phiên bản liên quan.
5. **Preconditions:** xác thực phát hiện, quyền thao tác, khả năng phục hồi và điều kiện an toàn trước khi chạy.
6. **Action:** sửa trạng thái bằng quy trình có kiểm soát; giới hạn hành động để tránh gây thiệt hại mới.
7. **Verification:** bằng chứng cụ thể cho trạng thái đúng, không chỉ báo lệnh chạy thành công.
8. **Failure handling:** cách xử lý nếu action lỗi, bị lặp, chạy một phần hoặc làm tăng tác động.
9. **Ownership:** control owner, operator, người duyệt, người đánh giá độc lập và người sở hữu rủi ro.
10. **Evidence/retention:** lưu kết quả, log, phiên bản và các giới hạn kiểm chứng theo chính sách.

### Liên kết với mục tiêu CIA

| Mục tiêu | Ví dụ sai lệch | Corrective control hướng tới |
| --- | --- | --- |
| **Confidentiality** | Bucket dữ liệu khách hàng có quyền public. | Thu hồi quyền public, chặn chia sẻ trái phép, xem lại bản sao và evidence. |
| **Integrity** | Người không có quyền sửa giá đơn hàng. | Dừng luồng sửa sai, sửa logic phân quyền, khôi phục/đối soát dữ liệu bị thay đổi. |
| **Availability** | Deployment làm API quan trọng không xử lý được đơn. | Rollback hoặc sửa cấu hình, kiểm tra giao dịch đầu cuối và khôi phục lưu lượng. |
| **Accountability** | Audit event thiếu actor sau khi đổi parser. | Sửa schema/pipeline, kiểm tra đường gửi và xử lý phần evidence bị thiếu. |

Mức ưu tiên khắc phục phải dựa trên **impact, likelihood, thời gian phơi lộ, yêu cầu bắt buộc và khả năng giảm hậu quả**; không suy ra duy nhất từ nhãn của một scanner.

## 4. Nguồn kích hoạt và chất lượng tín hiệu

Corrective control có thể được kích hoạt bởi **cảnh báo tự động**, **phát hiện pentest/audit**, **kiểm thử thất bại**, **sự cố thật**, **yêu cầu ứng cứu** hoặc **đánh giá rủi ro định kỳ**.

| Nguồn | Tín hiệu điển hình | Nguy cơ cần kiểm tra |
| --- | --- | --- |
| Vulnerability scan / SAST / DAST | Phát hiện lỗ hổng được báo cáo. | False positive, phiên bản không còn chạy, scope sai, severity kỹ thuật chưa phản ánh nghiệp vụ. |
| Cloud configuration monitoring | Bucket public, IAM policy rộng, audit log bị tắt. | Drift đã xảy ra trên production hay chỉ ở cấu hình tạm? Công cụ có quyền đọc đủ scope? |
| SIEM / EDR / IDS | Hoạt động bất thường hoặc máy trạm bị nghi ngờ xâm nhập. | Alert có đủ ngữ cảnh, có dấu hiệu đang diễn ra hay cần phân tích thêm? |
| CI/CD security tests | Negative authorization test thất bại, policy-as-code không đạt. | Test có mô phỏng đúng vai trò/dữ liệu, có được gate trước triển khai không? |
| Incident response | Dữ liệu bị lộ, credential bị chiếm, dịch vụ bị gián đoạn. | Phải bảo toàn bằng chứng, xác định phạm vi và phối hợp hành động nhiều nhóm. |
| Internal/external audit | Sai lệch với policy, thiếu evidence hoặc kiểm soát không hoạt động. | Khác biệt giữa “không có control” và “chưa cung cấp evidence”; cả hai cần xử lý phù hợp. |
| Data owner / business review | Quyền quá rộng, retention sai, dữ liệu test chứa bản sao production. | Quy tắc nghiệp vụ và nghĩa vụ liên quan phải được xác định trước khi sửa. |

**Detection quality quyết định chất lượng phản ứng.** Nếu detector báo sai, một corrective action tự động có thể vô hiệu hóa tài khoản hợp lệ hoặc xóa cấu hình thiết yếu. Vì vậy phải có cơ chế **xác minh tín hiệu, điều kiện an toàn, kiểm soát tác động và đường rollback** tương xứng với mức rủi ro.

### Corrective control tự động hay thủ công?

- **Tự động:** hợp khi điều kiện đầu vào rõ, hành động có phạm vi hẹp, dễ đảo ngược, được kiểm thử và có quyền thực thi tối thiểu.
- **Có con người phê duyệt:** hợp khi tác động lớn, có khả năng làm gián đoạn dịch vụ hoặc cần quyết định nghiệp vụ/pháp lý.
- **Hỗn hợp:** tự động khoanh vùng một phần, mở incident và yêu cầu operator phê duyệt sửa triệt để.

Ví dụ có thể tự động khóa **một policy truy cập công khai mới** đã được xác nhận vi phạm baseline, nhưng không nên tự động xóa toàn bộ bucket chứa dữ liệu khách hàng chỉ vì một alert không rõ ngữ cảnh.

## 5. Vòng đời corrective control: từ phát hiện đến kết luận

~~~mermaid
flowchart TD
    A["Security event / finding / audit gap"] --> B["Xác minh phạm vi và mức ưu tiên"]
    B --> C["Containment nếu cần thiết"]
    C --> D["Phân tích nguyên nhân và chọn phương án"]
    D --> E{"Phương án đủ thẩm quyền và an toàn?"}
    E -- "Chưa" --> F["Escalation / risk decision / biện pháp tạm"]
    F --> D
    E -- "Có" --> G["Corrective action / remediation"]
    G --> H["Verification + negative test + kiểm tra tác động phụ"]
    H --> I{"Đạt tiêu chí?"}
    I -- "Không" --> J["Mở lại / điều chỉnh / chạy lại có kiểm soát"]
    J --> D
    I -- "Có" --> K["Lưu evidence + đánh giá residual risk"]
    K --> L["Theo dõi tái diễn và thay đổi"]
    L --> B
~~~

### Bước 1 — Tiếp nhận và xác minh

Ghi nhận thời gian, nguồn phát hiện, tài sản, phiên bản, người báo cáo và bằng chứng gốc. Xác định **sự kiện đã xảy ra** hay **chỉ có điều kiện có thể dẫn tới sự kiện**; phân biệt dữ liệu đã bị truy cập trái phép với khả năng truy cập. Thêm severity và ưu tiên theo rubric của tổ chức.

### Bước 2 — Giới hạn phạm vi nguy hiểm

Khi đang có tác động hoặc nguy cơ nghiêm trọng, có thể cần vô hiệu hóa đường khai thác, thu hồi token, khóa tài khoản, giới hạn lưu lượng hoặc cô lập thành phần. Hoạt động phải theo **incident response/change process** phù hợp, xem xét giữ bằng chứng và khả năng gây gián đoạn nghiệp vụ.

### Bước 3 — Tìm nguyên nhân và chọn biện pháp

Đi từ biểu hiện tới **nguyên nhân kỹ thuật/quản trị**: lỗi code, quy tắc phân quyền sai, pipeline thiếu kiểm thử, drift cấu hình, secret quản lý yếu, thiếu owner hay quy trình review không hiệu quả. Không vội kết luận “do con người” nếu thiết kế hệ thống tạo điều kiện lỗi lặp lại.

### Bước 4 — Thực hiện khắc phục

Thực hiện theo runbook/change đã duyệt; bảo đảm người thực thi có quyền phù hợp, có kế hoạch sao lưu/rollback nếu cần, ghi phiên bản và thời điểm. Với thay đổi khẩn cấp, vẫn phải bảo đảm có **dấu vết phê duyệt/hậu kiểm** theo quy trình.

### Bước 5 — Kiểm chứng sau sửa

Chạy **positive test, negative test**, kiểm tra sản xuất và phụ thuộc trong phạm vi, xác nhận tác động phụ không gây sai lệch mới. Chỉ công bố trạng thái đạt khi có **tiêu chí chấp nhận và kết quả thực tế**. Nếu evidence thiếu, ghi “chưa xác minh”, không tự đánh dấu PASS.

### Bước 6 — Đóng phát hiện có điều kiện và theo dõi

Đóng finding khi tiêu chí hoàn tất đã đạt, evidence được lưu, các phần chưa xử lý được chuyển thành risk/finding riêng với owner và thời hạn. Theo dõi regression, config drift và sự kiện kích hoạt đánh giá lại.

## 6. Nguyên nhân gốc và CAPA: sửa để không tái diễn

Một corrective control ở mức kỹ thuật thường sửa trạng thái hiện tại; một chương trình **Corrective and Preventive Action (CAPA)** bổ sung cách điều tra nguyên nhân hệ thống, hành động và xác nhận hiệu quả lâu dài. Không phải mọi ticket đều cần một cuộc điều tra CAPA lớn, nhưng các phát hiện **lặp lại hoặc hậu quả cao** nên được xem theo chuỗi nguyên nhân.

### Ví dụ: bucket bị mở công khai nhiều lần

**Biểu hiện:** công cụ giám sát liên tục phát hiện bucket public.

**Sửa tạm:** đổi policy về private.

**Nguyên nhân gốc có thể là:** template IaC định nghĩa sai; quyền developer cho phép sửa trực tiếp; không có release gate; nhiều bucket chưa gắn nhãn nên detector thiếu scope.

**Hành động khắc phục bền vững:** sửa IaC, đưa security policy test vào CI, hạn chế thay đổi ngoài pipeline, phát hiện drift trên production và xác định owner của mọi bucket.

**Kiểm chứng hiệu quả:** dùng bài test mô phỏng IaC vi phạm ở môi trường an toàn, xác nhận pipeline chặn; thay đổi cấu hình không được phép trong phạm vi thử nghiệm phải bị phát hiện và xử lý; theo dõi phát hiện tái diễn trong khoảng thời gian được quy định.

### Kỹ thuật hỏi “Vì sao?” và tránh kết luận thiên lệch

Có thể dùng “5 Whys”, causal analysis hoặc timeline incident. Mục tiêu là xác định **chuỗi điều kiện có bằng chứng**, không mặc nhiên tìm một cá nhân để quy lỗi.

| Câu hỏi | Ví dụ dữ liệu cần xem |
| --- | --- |
| Vì sao trạng thái sai xuất hiện? | IaC diff, change log, phiên bản deploy, IAM action. |
| Vì sao không bị chặn trước triển khai? | CI rules, coverage, điểm bypass, trách nhiệm phê duyệt. |
| Vì sao phát hiện muộn? | Alert health, log forwarding, phân ca trực, false negative. |
| Vì sao sửa rồi vẫn tái diễn? | Cấu hình nguồn không được cập nhật, template khác, quyền sửa trực tiếp còn tồn tại. |
| Vì sao hậu quả vượt dự kiến? | Chia sẻ dữ liệu rộng, thiếu giới hạn tenant, không có phương án cô lập hoặc restore. |

Một hành động “đào tạo lại nhân viên” có thể là thành phần bổ sung nhưng hiếm khi thay thế đủ cho **kiểm soát quy trình và kỹ thuật** nếu sai lệch có thể dễ dàng tái diễn.

## 7. Phân công trách nhiệm: ai sửa, ai xác minh, ai nhận rủi ro?

### Các vai trò cần phân biệt

| Vai trò | Nhiệm vụ với corrective control |
| --- | --- |
| **Control owner** | Chịu trách nhiệm giải trình về thiết kế, phạm vi, vận hành và evidence của biện pháp khắc phục. |
| **Operator / engineering** | Thực thi runbook, sửa mã/cấu hình, kiểm thử kỹ thuật, triển khai và theo dõi trạng thái. |
| **System/service owner** | Quản lý tác động của thay đổi đối với dịch vụ, phụ thuộc, bảo đảm giao dịch hoạt động đúng. |
| **Data owner** | Xác định độ nhạy và phạm vi dữ liệu bị tác động, quy tắc xử lý dữ liệu và mức hậu quả nghiệp vụ. |
| **Incident commander / response team** | Điều phối khi có sự cố, khoanh vùng, bảo toàn bằng chứng và xử lý theo playbook. |
| **Security assurance / assessor** | Đánh giá bằng chứng thiết kế/vận hành, kiểm tra phát hiện đã được khắc phục trong phạm vi. |
| **Risk owner** | Quản lý và quyết định xử lý/chấp nhận residual risk trong thẩm quyền; không mặc nhiên là người tự sửa code. |
| **Legal/privacy/compliance** | Xác định hoặc tư vấn các nghĩa vụ xử lý/giữ dữ liệu, thông báo và điều kiện pháp lý khi áp dụng. |

### RACI ví dụ cho lỗi phân quyền dữ liệu

RACI: **R** = trực tiếp thực hiện; **A** = chịu trách nhiệm cuối cùng về hoạt động; **C** = được tham vấn; **I** = được thông báo. Ví dụ minh họa phải điều chỉnh theo tổ chức:

| Hoạt động | Service owner | Engineering | Security assurance | Data owner | Risk owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| Xác định phạm vi lỗi và mục tiêu sửa dịch vụ | **A** | **R** | C | C | I |
| Sửa authorization, triển khai và vận hành | **A** | **R** | C | I | I |
| Xác định hậu quả đối với dữ liệu nghiệp vụ | C | C | C | **A/R** | I |
| Kiểm tra độc lập evidence và retest khi cần | C | C | **A/R** | C | I |
| Quyết định residual risk theo thẩm quyền | C | I | C | C | **A/R** |

Nếu có incident đang diễn ra, người điều phối sự cố và đội ứng cứu phải được bổ sung vào RACI theo quy trình. **Một người sửa lỗi không tự động được phê duyệt việc chấp nhận rủi ro còn lại**, và người kiểm tra không tự động có quyền quyết định kinh doanh.

## 8. Case study A: sửa lỗi truy cập hóa đơn xuyên tenant

### Bối cảnh và threat scenario

Một ứng dụng SaaS phục vụ nhiều doanh nghiệp, mỗi hóa đơn thuộc một tenant. Một integration test phát hiện người dùng đã xác thực của tenant A có thể đọc hóa đơn tenant B nếu biết invoice ID.

**Security requirement:** mọi đường đọc, sửa và export hóa đơn phải kiểm tra quyền trên **đối tượng cụ thể**, dựa vào danh tính và tenant tin cậy, không chỉ kiểm tra token hợp lệ.

### Bước A1 — Khoanh vùng và xác minh phạm vi

Nhóm đánh giá API có thể bị ảnh hưởng, quyền và vai trò, số tenant, bản sao qua cache và export. Cần phân biệt **khả năng truy cập sai** với **bằng chứng truy cập thực tế**. Xem log hiện có trong thời hạn lưu, bảo toàn thông tin phục vụ điều tra và đánh giá biện pháp giới hạn tạm nếu rủi ro hiện hành cao.

### Bước A2 — Corrective action đối với logic phân quyền

Một nguyên nhân có thể là tầng controller chỉ kiểm tra authentication rồi gọi truy vấn theo invoice ID. Cách sửa là **ràng buộc truy vấn vào tenant/principal từ ngữ cảnh đã xác minh**, kiểm tra action được phép và mặc định từ chối khi không xác định được quyền.

Đoạn Java/Spring minh họa dưới đây là một ý tưởng thiết kế, không phải thành phần chạy độc lập hoặc thay thế review toàn hệ thống:

~~~java
// Ví dụ: tenantId lấy từ principal đã được xác thực và chuẩn hóa.
@Transactional(readOnly = true)
public InvoiceView findInvoiceForTenant(
        UUID invoiceId,
        VerifiedPrincipal principal) {

    String tenantId = principal.tenantId();
    if (tenantId == null || !principal.canReadInvoices()) {
        throw new AccessDeniedException("Not authorized");
    }

    Invoice invoice = invoiceRepository
        .findByIdAndTenantId(invoiceId, tenantId)
        .orElseThrow(() -> new ResponseStatusException(
            HttpStatus.NOT_FOUND));

    return invoiceMapper.toAuthorizedView(invoice, principal);
}
~~~

Ở đây **VerifiedPrincipal** là interface/kiểu minh họa được ứng dụng định nghĩa; phải bảo đảm tenantId và quyền không đến từ header do client tự kiểm soát. Repository phải thực sự giới hạn truy vấn theo tenant; mapper chỉ trả những trường được phép. Phải kiểm tra thêm các đường sửa/xóa/batch/export, dữ liệu cache và tài khoản dịch vụ, không chỉ một phương thức.

### Bước A3 — Thiết kế kiểm thử sau sửa

| ID | Ca kiểm thử | Kỳ vọng |
| --- | --- | --- |
| **AUTHZ-01** | Người dùng tenant A đọc hóa đơn A trong quyền. | Trả đúng dữ liệu được phép. |
| **AUTHZ-02** | Người dùng tenant A đọc hóa đơn B. | Từ chối theo chính sách; không tiết lộ nội dung B. |
| **AUTHZ-03** | Người dùng chỉ đọc cố sửa/xóa hóa đơn A. | Bị từ chối; trạng thái dữ liệu không thay đổi. |
| **AUTHZ-04** | Người dùng A truyền tenant B qua header/body. | Không mở rộng quyền; server dùng tenant từ ngữ cảnh tin cậy. |
| **AUTHZ-05** | Job export hoặc API batch yêu cầu dữ liệu tenant B. | Không bypass cùng quy tắc quyền. |
| **AUTHZ-06** | Token hết hạn hoặc principal thiếu quyền. | Không truy cập được; có audit event phù hợp. |
| **AUTHZ-07** | Cache/CDN trả dữ liệu đã được tạo cho tenant khác. | Không lộ; cache key và authorization đáp ứng yêu cầu. |

**Evidence:** danh sách API và đường dữ liệu, code review, test report gắn với commit/release, kết quả deploy, cấu hình production và bản ghi phát hiện/khắc phục. Với lỗi nhạy cảm cần kiểm tra **trạng thái dữ liệu và log** tại đích, không chỉ status code HTTP.

### Bước A4 — Đóng finding và tính residual risk

Nếu mọi ca liên quan đã đạt trong phạm vi, nhóm có thể kết luận control phân quyền đã được sửa ở phiên bản đó. Nhưng **impact nếu vẫn xảy ra rò rỉ dữ liệu** có thể chưa đổi; việc loại bỏ đường tấn công chủ yếu làm giảm khả năng khai thác kịch bản đã xét. Rủi ro còn lại về endpoint khác, quyền admin, dữ liệu đã xuất trước khi sửa hoặc nhà cung cấp cần được xem riêng.

## 9. Case study B: bucket bị public do cấu hình drift

### Điều kiện và hành động tức thời

Một bucket chứa file export dữ liệu khách hàng bị cấu hình quyền đọc public trái với security baseline. Công cụ phát hiện drift gửi event tới hệ thống phản ứng.

**Corrective control đề xuất:** khi điều kiện vi phạm được xác nhận, cơ chế có quyền tối thiểu áp lại chính sách không công khai đã duyệt, ghi nhận phiên bản cấu hình, xác minh public access không còn và tạo finding để điều tra nguyên nhân. Nếu có khả năng ảnh hưởng lớn, cần con người xác nhận hoặc cơ chế hạn chế tác động đã được kiểm thử.

### Luồng điều khiển an toàn

~~~mermaid
flowchart TD
    A["Config drift: bucket public"] --> B["Xác nhận asset, owner, classification"]
    B --> C{"Cấu hình public được phê duyệt hợp lệ?"}
    C -- "Có" --> D["Đối chiếu exception, scope, expiry; giám sát"]
    C -- "Không" --> E["Containment / áp lại baseline"]
    E --> F["Đọc lại policy và thử quyền truy cập"]
    F --> G{"Private trong phạm vi?"}
    G -- "Không" --> H["Escalate + manual response"]
    G -- "Có" --> I["Điều tra exfiltration, root cause và bản sao"]
    I --> J["Sửa IaC / quyền / tests; retest"]
    J --> K["Evidence + residual risk + closure"]
~~~

### Tiêu chí cần tránh nhầm lẫn

- Có **bucket private hiện tại** không chứng minh **không ai đã tải dữ liệu trước đó**.
- Có **audit log truy cập** không chứng minh mọi request trong thời gian lộ đều được ghi nếu logging bị tắt hoặc retention không đủ.
- Có **IaC đúng trong Git** không chứng minh cấu hình production giống Git nếu ai đó có thể sửa trực tiếp.
- Có **policy-as-code chặn deploy sai** không loại trừ credential quản trị bị lộ hoặc các bucket ngoài inventory.
- **Tự động xóa bucket** để “loại bỏ rủi ro” có thể phá hủy chứng cứ và dữ liệu; hành động phải được giới hạn vào mục tiêu, cân nhắc backup và phục hồi.

### Bằng chứng để đánh giá

Nguồn cảnh báo và timestamp; data classification; cấu hình trước/sau (bảo vệ dữ liệu nhạy cảm); bản ghi ai/cái gì đổi policy; kết quả thử truy cập không có quyền; phạm vi bucket/đường cấp quyền khác; IaC change và CI test; log truy cập trong khoảng liên quan và nhận định về giới hạn của chúng; lịch sử retest.

Với nghi ngờ tiết lộ dữ liệu, phối hợp incident response và privacy/legal theo nghĩa vụ áp dụng, **không tự tuyên bố đã xử lý xong sự cố** chỉ vì permission đã được sửa.

## 10. Case study C: credential bị lộ và quyền truy cập bị lạm dụng

Nhóm phát triển vô tình đưa một API key của đối tác vào kho mã. Công cụ secret scanning phát hiện key trong một commit.

### Hành động nào là corrective?

1. **Khoanh vùng:** xác định phạm vi quyền của key và khả năng nó đã được sử dụng; hạn chế luồng nguy hiểm nếu cần.
2. **Thu hồi/xoay vòng:** vô hiệu hóa credential cũ tại nơi cấp và thay mới qua secret manager hoặc cơ chế tương đương.
3. **Cập nhật nơi sử dụng:** thay reference của ứng dụng, job, pipeline và integration; triển khai với phương án rollback an toàn.
4. **Kiểm tra hoạt động:** xác nhận credential cũ thực sự không còn quyền trên các API trong phạm vi, credential mới hoạt động đúng.
5. **Điều tra và ngăn tái diễn:** xem log sử dụng, đánh giá mức lộ, sửa quy trình commit, secret scan và quyền key.

**Xóa secret khỏi một commit mới không tự loại bỏ key khỏi Git history hoặc khỏi bản sao đã bị bên khác giữ**. Biện pháp ưu tiên là **thu hồi khả năng sử dụng** và xử lý lịch sử/bản sao theo điều kiện thực tế; không nên coi lịch sử đã “sạch” là bằng chứng credential chưa từng bị lộ.

### Những kiểm tra quan trọng

| Claim | Evidence phù hợp |
| --- | --- |
| Key cũ không còn hiệu lực. | Trạng thái revoke ở hệ thống cấp, negative test với key cũ trong môi trường cho phép, audit việc revoke. |
| Ứng dụng đã chuyển sang key mới hợp lệ. | Cấu hình secret reference, deploy ID, test chức năng phụ thuộc. |
| Quyền credential mới được giới hạn. | Ma trận quyền, scope/token policy, test thao tác không được phép. |
| Không có sử dụng bất thường chưa được điều tra trong phạm vi quan sát. | Log/telemetry, khoảng retention, kết quả điều tra và giới hạn nguồn dữ liệu. |
| Lỗi được giảm khả năng tái diễn. | Secret scanning trong CI, test đẩy mẫu secret giả có kiểm soát, hướng dẫn và review. |

Việc thu hồi key có thể gây gián đoạn cho dịch vụ đang dùng nó; corrective control phải định nghĩa thứ tự thao tác phù hợp với **mức độ khẩn cấp và rủi ro vận hành**. Không có một trình tự duy nhất áp dụng mọi credential.

## 11. Corrective control với tính sẵn sàng và toàn vẹn dữ liệu

Trong security assurance, corrective control không chỉ xử lý truy cập trái phép. Nó còn liên quan **availability**, **integrity** và tính đúng đắn của vận hành.

### 11.1. Rollback bản phát hành lỗi

Một release làm dịch vụ Order API liên tục trả lỗi. Điều kiện kiểm soát có thể là SLO bị vi phạm trong thời gian được định nghĩa và telemetry đủ tin cậy.

**Corrective action:** đưa hệ thống về cấu hình/bản phát hành ổn định theo change/rollback runbook.

**Verification:** thử giao dịch tạo đơn, thanh toán và xem đơn; kiểm tra tương thích schema, message queue và dữ liệu đã ghi; đo SLI sau rollback; đối soát giao dịch trong khoảng lỗi.

**Giới hạn:** rollback binary không nhất thiết rollback được **schema migration**, dữ liệu đã thay đổi hoặc sự kiện đã gửi cho đối tác. Nếu tự động rollback mà không kiểm tra khả năng tương thích, control có thể làm hậu quả nặng hơn.

### 11.2. Phát hiện bản ghi nghiệp vụ bị sửa trái phép

Giả sử một batch sai cập nhật giá trị đơn hàng. Một corrective control có thể đóng băng luồng cập nhật, xác định tập bản ghi bị ảnh hưởng và áp dụng phương án sửa/khôi phục theo hồ sơ nguồn đúng.

Không nên chỉ restore toàn bộ database ngay nếu có giao dịch hợp lệ được ghi sau thời điểm lỗi. Cần kiểm tra **điểm khôi phục, tính nhất quán, quyền duyệt sửa dữ liệu, audit trail và tác động tới hệ thống đồng bộ**. Data owner xác nhận quy tắc nghiệp vụ của dữ liệu, platform/operator thực thi và assessor kiểm tra.

### 11.3. Corrective vs recovery

Một hệ thống có backup và runbook restore là **năng lực phục hồi**. Khi phát hiện ransomware, quyết định cách ly máy, loại bỏ credential xâm nhập, phục hồi hệ thống từ bản an toàn và đối soát dữ liệu có thể là một **kế hoạch khắc phục tổng thể**. Tuy vậy, phải kiểm tra **nguyên nhân xâm nhập**: nếu endpoint hoặc credential vẫn yếu, restore chỉ đưa dịch vụ trở lại trạng thái có thể bị tấn công lần nữa.

## 12. Thiết kế corrective automation an toàn và có thể chứng minh

Tự động hóa đem lại tốc độ nhưng có thể gây tác động hàng loạt khi rule hoặc quyền sai. Một **automated corrective control** nên đáp ứng các nguyên tắc sau:

| Tiêu chí | Mục đích | Cách kiểm chứng |
| --- | --- | --- |
| **Điều kiện kích hoạt có chứng cứ** | Tránh hành động từ alert giả hoặc dữ liệu thiếu. | Test positive/negative trigger, dữ liệu đầu vào mâu thuẫn, nguồn không xác thực. |
| **Phạm vi tối thiểu** | Tránh sửa/xóa tài sản không liên quan. | Test tài sản ngoài scope, multi-tenant, dry-run nếu có. |
| **Quyền thực thi tối thiểu** | Không biến automation thành danh tính đặc quyền toàn hệ thống. | IAM review, negative permission tests, access logs. |
| **Idempotency / concurrency safety** | Lặp alert hoặc chạy song song không tạo thay đổi sai. | Trigger lặp, race condition, compare-and-set/version checks. |
| **Bảo vệ trạng thái và bằng chứng** | Giữ dữ liệu để điều tra và tránh mất integrity. | Pre-action capture, audit trail, xử lý dữ liệu nhạy cảm. |
| **Rollback / recovery khi lỗi** | Kiểm soát tác động của hành động sửa. | Diễn tập action thất bại giữa chừng, đường rollback/human takeover. |
| **Hậu kiểm độc lập** | Xác minh trạng thái đích đúng, không chỉ job completed. | Read-after-write, negative access test, telemetry và business checks. |
| **Escalation** | Có người xử lý nếu không đạt hoặc vượt ngưỡng. | Diễn tập cảnh báo, ticket, quy tắc phân ca và thời gian đáp ứng. |
| **Chống tái diễn** | Không chỉ chữa triệu chứng nhiều lần. | Sửa template/CI, theo dõi drift, phân tích nguyên nhân lặp. |

### Pseudocode cho tự sửa cấu hình

Đây là ví dụ logic **an toàn theo nguyên tắc**, không phải code cloud cụ thể:

~~~text
on verified_policy_violation(event):
    asset = inventory.find(event.asset_id)
    if asset is unknown:
        escalate("Unknown asset; no automatic modification")
        return

    if not event.is_current or not event.matches_asset_version:
        record("Stale or conflicting finding; verify again")
        return

    if authorized_exception_covers(asset, event):
        record("Exception applies; check expiry and conditions")
        return

    if action_impact_exceeds_approved_limit(asset):
        request_human_approval("Potential availability impact")
        return

    capture_minimum_pre_action_evidence(asset)
    apply_approved_baseline_with_narrow_permissions(asset)
    verified = read_back_effective_policy(asset)
    if not verified:
        escalate("Correction incomplete")
    else:
        open_root_cause_follow_up(asset)
        record_result_and_reassessment(asset)
~~~

Các kiểm tra như **asset version, exception scope, quyền thực thi và đọc lại effective policy** phải được hiện thực bằng API/cơ chế thực tế, có xử lý sự kiện bị trễ, duplicate và race. Đừng copy pseudocode rồi tuyên bố đã có control hiệu quả.

## 13. Cần bằng chứng gì để kết luận corrective control hiệu quả?

Một control có thể **được thiết kế hợp lý** nhưng **không hoạt động đúng** do thiếu quyền, cấu hình drift, worker mất kết nối hoặc người vận hành không được gọi.

### Design effectiveness và operating effectiveness

**Design effectiveness** hỏi: nếu mọi bước diễn ra đúng như mô tả, control có thể xử lý rủi ro, trong phạm vi và thời gian yêu cầu không? Cần xem điều kiện đầu vào, quyền, tiêu chí hoàn tất, khả năng fail-safe, dependency, giới hạn và quy trình hậu kiểm.

**Operating effectiveness** hỏi: control có thực sự được kích hoạt và xử lý đúng khi có điều kiện tương ứng trong **thời gian và môi trường được đánh giá** không? Cần các bằng chứng như record phát hiện, action, cấu hình thực tế, thời gian phản hồi, hậu kiểm, trường hợp thất bại và xử lý sau đó.

### Claim – Argument – Evidence (CAE)

**Claim:** “Các bucket thuộc nhóm dữ liệu Confidential trong production được tự động khôi phục cấu hình không công khai khi phát hiện public access trái baseline; kết quả được kiểm tra và thất bại được chuyển cho người trực trong phạm vi thời gian đã phê duyệt.”

**Argument:** “Inventory xác định bucket thuộc phạm vi; detector đọc effective policy; automation được cấp quyền hẹp; rule áp baseline; hậu kiểm độc lập đọc lại quyền; alert/ticket theo dõi action không đạt.”

**Evidence:** inventory, mã rule/phiên bản, cấu hình production, test case public→private ở môi trường cho phép, audit action, kết quả đọc lại quyền, ticket escalation, lịch sử drift, các trường hợp ngoại lệ và đo thời gian xử lý.

### Evidence matrix

| Claim thành phần | Evidence | Điều không thể suy ra |
| --- | --- | --- |
| Detector bao phủ tài sản mục tiêu. | Inventory đối chiếu cloud resources, scope scan và nguồn event. | Không có tài sản ngoài inventory. |
| Automation được kích hoạt khi phát hiện sai. | Event ID nối với workflow execution, timestamp và actor. | Tất cả sự kiện tương tự trong mọi thời kỳ đều kích hoạt. |
| Action thực sự sửa trạng thái. | Config before/after, read-back effective policy, negative access test. | Không ai đã khai thác trước khi sửa. |
| Kết quả thất bại được xử lý. | Test lỗi API/thiếu quyền, alert/ticket và kết quả escalation. | Con người chắc chắn sẽ xử lý đúng mọi lần nếu chưa diễn tập. |
| Nguyên nhân gốc được xử lý. | IaC diff, test CI, change approval, theo dõi drift tái diễn. | Không còn đường tạo sai lệch nào khác. |
| Residual risk được đánh giá lại. | Risk register cập nhật, finding, evidence, quyết định của risk owner. | Risk bằng 0 hoặc tự được chấp nhận. |

**Bằng chứng có giới hạn:** một screenshot “workflow succeeded” không đủ nếu không có **trạng thái hệ thống sau sửa**, tên tài sản, môi trường, ngày giờ và phương pháp kiểm tra. Một test trên staging không tự chứng minh automation production vận hành đúng.

## 14. Kế hoạch kiểm thử corrective control

Để tránh đánh giá chỉ dựa vào tình huống thành công đơn giản, cần bao phủ cả **sự kiện gây lỗi, tình huống méo và đường khôi phục khi action thất bại**. Ví dụ cho control tự sửa IAM/cloud policy:

| Test ID | Tình huống | Tiêu chí đạt |
| --- | --- | --- |
| **COR-01** | Phát sinh một vi phạm baseline đã biết trong môi trường test được phép. | Detector nhận ra và action đúng tài sản/mức quyền. |
| **COR-02** | Tài sản đang tuân thủ policy. | Không có thay đổi không cần thiết hoặc tác động bất lợi. |
| **COR-03** | Event bị gửi trùng hoặc tới muộn. | Xử lý idempotent; không làm sai cấu hình hiện tại. |
| **COR-04** | Event trỏ asset đã xóa, đổi phiên bản hoặc ngoài inventory. | Không tự sửa nhầm; ghi nhận/escalate thích hợp. |
| **COR-05** | Automation thiếu quyền hoặc API provider trả lỗi. | Thất bại được ghi, alert/ticket đúng người; không báo “closed”. |
| **COR-06** | Action hoàn tất một phần. | Hậu kiểm phát hiện sai lệch; có phương án sửa tiếp hoặc rollback an toàn. |
| **COR-07** | Có ngoại lệ hợp lệ còn hiệu lực. | Kiểm tra đúng scope, hạn và điều kiện; không tắt toàn bộ monitoring. |
| **COR-08** | Ngoại lệ hết hạn hoặc bị thu hồi. | Sai lệch lại được xử lý theo quy trình, không bị bỏ qua vô thời hạn. |
| **COR-09** | Thao tác sửa có thể làm gián đoạn nghiệp vụ. | Gating/approval/khả năng khôi phục theo policy; không tự xóa hoặc vô hiệu hóa bừa bãi. |
| **COR-10** | Đường giám sát lỗi trong khi action thành công/thất bại. | Có kiểm tra độc lập/heartbeat, nhận diện khoảng thiếu evidence. |
| **COR-11** | Sau sửa, mẫu cấu hình hoặc pipeline tiếp tục tạo drift. | Root-cause action/CI test và theo dõi tái diễn hoạt động. |
| **COR-12** | Nhiều tài sản cùng vi phạm trong một đợt. | Giới hạn tốc độ/quy mô hành động, theo dõi tác động và escalation khi vượt ngưỡng. |

**Không cố tình tạo lỗi trên production ngoài quy trình cho phép.** Diễn tập trong sandbox hoặc test environment có ranh giới rõ, dùng tài sản/canary giả, kế hoạch hoàn nguyên và đánh giá rủi ro cho phép. Với các control quan trọng, có thể kiểm tra thêm bằng **simulation, tabletop exercise, replay dữ liệu đã được làm sạch** hoặc kiểm tra cấu hình/telemetry production mà không gây sự cố.

### Tiêu chí đóng một phát hiện cần bao gồm

- Đã xác minh điều kiện ban đầu và phạm vi.
- Hành động đã triển khai ở **môi trường, phiên bản và asset** cần sửa.
- Positive/negative tests đạt theo requirement, không gây regression quan trọng.
- Dữ liệu/đối tượng đã bị ảnh hưởng được xử lý hoặc ghi finding/risk riêng.
- Root cause, ngoại lệ, kế hoạch ngăn tái diễn và người theo dõi rõ.
- Evidence gốc được bảo vệ; risk owner nhận báo cáo khi cần.

## 15. Đo hiệu quả corrective control

Một control không nên được coi tốt chỉ vì đóng nhiều ticket. Cần đo cả **tốc độ, chất lượng, hậu quả và sự tái diễn**, với định nghĩa nhất quán.

| Chỉ số | Ý nghĩa | Cảnh báo khi diễn giải |
| --- | --- | --- |
| **Time to containment** | Thời gian từ mốc được định nghĩa tới lúc giới hạn tác động ban đầu. | Bắt đầu tính từ phát hiện hay từ sự kiện? Cần ghi rõ. |
| **Time to correction / remediation** | Thời gian từ mốc tới trạng thái sửa được xác minh theo tiêu chí. | Đóng ticket trước khi retest sẽ tạo kết quả sai. |
| **Mean Time to Repair/Restore/Recover (MTTR)** | Thời gian bình quân để đạt trạng thái mục tiêu, tùy định nghĩa cụ thể. | MTTR là thuật ngữ đa nghĩa; phải xác định mốc bắt đầu/kết thúc. |
| **SLA/SLO khắc phục theo mức rủi ro** | Tỷ lệ findings được xử lý đúng hạn đã phê duyệt. | Một lỗi Critical kéo dài có thể bị che bởi hàng trăm lỗi nhỏ đúng hạn. |
| **Verification pass rate** | Tỷ lệ corrective actions đạt retest, ở đúng scope. | Chỉ tính các ca đã test sẽ che các mục “NOT TESTED”. |
| **Reopen/recurrence rate** | Tỷ lệ lỗi tái diễn sau khi thông báo đã xử lý. | Cần định nghĩa cùng root cause hay chỉ cùng loại triệu chứng. |
| **Automation success & rollback rate** | Tính ổn định và tác động phụ của tự động sửa. | Có thể “success” từ workflow nhưng trạng thái hệ thống chưa đúng. |
| **Residual risk beyond tolerance** | Phần rủi ro vẫn vượt ngưỡng sau corrective action. | Risk chấp nhận có điều kiện không đồng nghĩa đã loại bỏ rủi ro. |

### Ví dụ minh họa cách tính thời gian

Một phát hiện được ghi lúc 09:00, khoanh vùng lúc 09:18, triển khai bản sửa lúc 11:10 và retest xác nhận đúng lúc 11:35.

- Nếu chọn **mốc phát hiện**, time to containment = **18 phút**.
- Time to remediation **đã xác minh** từ phát hiện = **2 giờ 35 phút**.
- Thời gian “từ merge PR tới deploy” hoặc “từ phát hiện tới merge” là các chỉ số khác và không thay thế việc kiểm tra hệ thống.

Đây là ví dụ số giả định. Phải phân biệt thời gian **sự kiện thực sự bắt đầu** và **thời gian được phát hiện** nếu đã có telemetry để ước lượng.

## 16. Hồ sơ corrective control và bằng chứng mẫu

Để kiểm toán, cần kết nối corrective action với **finding ID, control requirement, risk scenario, owner và các hiện vật**. Ví dụ YAML mang tính học tập; không phải cấu hình bắt buộc của công cụ nào:

~~~yaml
control_id: CTRL-COR-OBJECT-POLICY-01
name: "Correct unauthorized public object storage policy"
control_type:
  - corrective
  - automated_with_escalation
control_objective: >
  Restore the approved private-access baseline for
  in-scope sensitive data objects after verified drift.
scope:
  environment: production
  asset_classification: [Confidential, Restricted]
  inventory_source: "approved-data-assets"
trigger:
  source: "cloud-policy-drift-detector"
  condition: "Unauthorized public read access verified"
owner_role: "Cloud Security Control Owner"
operator_role: "Cloud Platform Automation"
escalation_role: "Security On-call"
risk_owner_role: "Data Protection Risk Owner"
action:
  - "Verify asset identity and policy version"
  - "Check authorized time-bound exceptions"
  - "Preserve minimal pre-action evidence"
  - "Apply approved private-access baseline"
  - "Read back effective policy and test denial"
  - "Escalate if action or verification fails"
verification:
  - "Public read not effective after correction"
  - "Legitimate approved access still works"
  - "Audit trail links event, action and result"
evidence:
  - "inventory/scope-release-example"
  - "tests/public-policy-remediation"
  - "logs/remediation-execution-example"
known_limits:
  - "Past unauthorized reads require separate investigation"
  - "Assets absent from inventory may not be covered"
related_findings:
  - "FIND-POLICY-017"
review_triggers:
  - "New cloud storage type or policy mechanism"
  - "Change in classification or public access approval"
  - "Failed automation or repeated drift"
~~~

Các ID và đường dẫn trên **chỉ minh họa**. Khi triển khai phải thay bằng evidence thật có timestamp, version, người tạo, phạm vi và kết quả. Nếu hồ sơ chứa đường tấn công hoặc dữ liệu nhạy cảm, phải quản lý quyền truy cập theo chính sách.

### Phân biệt hiện vật kế hoạch với evidence kết quả

| Hiện vật | Chứng minh được | Không tự chứng minh |
| --- | --- | --- |
| Runbook khắc phục được duyệt | Có thiết kế quy trình và thẩm quyền. | Runbook đã được thực thi đúng trong sự kiện thực. |
| PR sửa lỗ hổng | Có thay đổi mã được đề xuất/merge. | Bản sửa đã có trên production và không còn bypass. |
| CI test PASS | Các test đã chạy đạt ở môi trường/phiên bản CI. | Tất cả đường sản xuất hoặc dữ liệu đã bị ảnh hưởng đều an toàn. |
| Deployment report | Thay đổi đã triển khai theo báo cáo. | Logic nghiệp vụ đã được kiểm chứng sau deploy. |
| Config diff / read-back | Trạng thái trước/sau trong phạm vi kiểm tra. | Không có hành vi khai thác trước thời điểm sửa. |
| Incident report | Kết quả điều tra và timeline trong giới hạn nguồn dữ liệu. | Các phần chưa quan sát được không tồn tại. |
| Risk acceptance | Người có thẩm quyền quyết định với phạm vi/điều kiện. | Rủi ro đã biến mất hoặc nghĩa vụ bắt buộc được miễn. |

## 17. Ngoại lệ, thời hạn và rủi ro còn lại

Có thể có corrective actions không thể hoàn thành ngay: dependency từ nhà cung cấp, hệ thống legacy khó sửa, yêu cầu khôi phục liên quan dữ liệu lớn hoặc phải chờ thay đổi kiến trúc.

Một hồ sơ ngoại lệ hoặc xử lý rủi ro nên bao gồm:

1. **Finding, control và risk ID**, mô tả sai lệch, impact/likelihood và phạm vi phiên bản/dữ liệu.
2. **Current residual risk** với controls đang hoạt động và evidence hiện có; không tính biện pháp chỉ mới lên kế hoạch là đã có hiệu quả.
3. **Biện pháp tạm/compensating control** cùng giả định và cách kiểm chứng, nếu phù hợp.
4. **Owner, deadline, kế hoạch khắc phục, tiêu chí kiểm thử và ngày hết hiệu lực**.
5. **Người có thẩm quyền xử lý/chấp nhận**, quyết định có chữ ký/dấu vết và điều kiện giám sát.
6. **Trigger đánh giá lại** khi rủi ro tăng, phát hiện mới, biện pháp tạm lỗi hoặc phạm vi thay đổi.

**Corrective control owner không mặc nhiên là risk owner.** Không phải yêu cầu pháp lý, hợp đồng hoặc an toàn bắt buộc nào cũng có thể được bỏ qua bằng một ngoại lệ nội bộ. Khi có nghi ngờ phải tham vấn chức năng chuyên trách.

### Current vs target residual risk

Ví dụ hiện tại API export thiếu object-level authorization, nhưng bản sửa sẽ phát hành sau bảy ngày. **Current residual risk** phải phản ánh lỗ hổng đang tồn tại và các biện pháp tạm đã thật sự có hiệu lực. **Target residual risk** là dự kiến sau khi triển khai và retest. Không được giảm mức hiện tại chỉ vì đã có ticket, lịch deploy hoặc bản thiết kế.

## 18. Corrective control trong assurance liên tục

Ở quy mô lớn, các phát hiện sinh ra từ CI/CD, vulnerability management, cloud configuration, SOC và audit. Một chương trình có thể tổ chức **đường đi chung từ phát hiện đến bằng chứng**:

~~~mermaid
flowchart LR
    A["Threat / Security requirement"] --> B["Control + owner"]
    B --> C["Test / Monitoring / Audit"]
    C --> D["Finding + triage"]
    D --> E["Correction / remediation"]
    E --> F["Independent verification"]
    F --> G["Residual risk + decision"]
    G --> H["Continuous monitoring"]
    H --> C
~~~

### Tích hợp vào SDLC

| Thời điểm | Corrective control liên quan | Evidence |
| --- | --- | --- |
| **Thiết kế** | Xác định trạng thái sai có thể xảy ra, trigger, hạn và cách khôi phục. | Threat model, security requirement, runbook design, RACI. |
| **Coding/review** | Sửa nguyên nhân và thêm regression tests. | Pull request, review, test report gắn commit. |
| **CI/CD** | Chặn thay đổi không đạt và kích hoạt workflow sửa khi phù hợp. | Policy test, build/deploy record, cơ chế approval. |
| **Production** | Theo dõi drift, hành vi, lỗi; chạy corrective action trong quyền hạn. | Monitoring, action logs, config read-back, on-call ticket. |
| **Incident response** | Khoanh vùng, khắc phục, phục hồi, hậu kiểm và điều tra. | Timeline, evidence bảo toàn, kết quả phục hồi, post-incident review. |
| **Audit/assurance** | Xem thiết kế/vận hành, kiểm tra phát hiện đã đóng và residual risk. | CAE, audit report, retest, risk decision. |

### Tự động sửa có thể tạo vòng lặp sai

Nếu hệ thống cấu hình mong muốn trong IaC mâu thuẫn với automation tự sửa production, cả hai có thể liên tục **ghi đè qua lại**. Vì vậy cần một nguồn **desired state được quản trị**, giải quyết ngoại lệ, versioning, thay đổi có phê duyệt và giám sát số lần tự sửa lặp. Hành động khắc phục càng nhanh nhưng liên tục bị đảo ngược càng cho thấy nguyên nhân chưa được xử lý.

### Đánh giá lại khi có thay đổi

Triggers điển hình:

- Thêm service, API, loại dữ liệu hoặc tenant/đối tác.
- Thay IAM, cloud policy, network segmentation, recovery architecture hoặc hệ thống log.
- Automation chạy lỗi, bỏ sót, gây outage hoặc phải rollback.
- Phát hiện tái diễn; nguyên nhân chung xuất hiện ở nhiều sản phẩm.
- Sự cố thực tế chứng minh giả định về trigger/response không đúng.
- Evidence hết hạn, exception hết hạn hoặc phạm vi bảo vệ thay đổi.

Mục tiêu không phải chạy lại mọi bài test sau mỗi commit, mà là **kiểm tra đúng các claim và controls bị ảnh hưởng**.

## 19. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Có alert nghĩa là đã có corrective control.” | Alert là phát hiện; phải có hành động, hậu kiểm và trách nhiệm khắc phục. |
| “Đóng ticket sửa lỗi đồng nghĩa rủi ro bằng 0.” | Phải kiểm chứng thay đổi thực tế và đánh giá residual risk, kể cả phần ngoài phạm vi. |
| “Một lần rollback là đã giải quyết nguyên nhân gốc.” | Rollback có thể đưa dịch vụ về trạng thái hoạt động nhưng nguyên nhân và dữ liệu bị sai cần xử lý riêng. |
| “Backup thành công nghĩa là đã corrective/recovery được dữ liệu.” | Cần restore drill, tính toàn vẹn và xác nhận nghiệp vụ. |
| “Sửa cấu hình bucket về private chứng minh chưa từng lộ dữ liệu.” | Chỉ chứng minh trạng thái quyền hiện tại trong phạm vi kiểm tra; phải điều tra khoảng phơi lộ trước đó. |
| “Xóa secret khỏi Git là thu hồi credential.” | Credential phải được revoke/rotate ở nguồn cấp; phải kiểm tra bản sao và log sử dụng. |
| “Automation có quyền admin sẽ sửa nhanh nhất và tốt nhất.” | Quyền quá rộng tăng blast radius; cần scope tối thiểu và cơ chế phê duyệt. |
| “Workflow báo success nghĩa là sửa đúng.” | Phải đọc lại trạng thái hệ thống và kiểm thử hậu quả mong muốn. |
| “Plan khắc phục được duyệt nghĩa là current residual risk giảm.” | Chỉ tính biện pháp đã hoạt động và có bằng chứng; plan là target. |
| “Chỉ cần sửa lỗi đang xuất hiện, không cần tìm nguyên nhân.” | Với lỗi tái diễn hoặc nghiêm trọng phải xem cơ chế khiến sai lệch trở lại. |
| “Corrective control phải luôn tự động.” | Có những hành động cần đánh giá nghiệp vụ, pháp lý hoặc kiểm soát tác động trước khi thực thi. |
| “Không có sự cố mới nghĩa là control chắc chắn tốt.” | Có thể thiếu telemetry, trigger chưa xảy ra hoặc test coverage yếu. |

## 20. Checklist triển khai và đánh giá corrective control

1. **Scenario:** sự kiện hoặc sai lệch nào cần khắc phục; dữ liệu, khách hàng và dịch vụ nào chịu tác động?
2. **Objective:** trạng thái an toàn sau xử lý được định nghĩa đo được chưa?
3. **Trigger:** nguồn phát hiện, mức tin cậy, điều kiện chống false positive và trường hợp im lặng có rõ không?
4. **Ownership:** có control owner, operator, người phê duyệt, risk owner và đầu mối escalation?
5. **Authority:** quyền sửa đủ nhưng không quá rộng; có giới hạn phạm vi, approval và audit?
6. **Action:** runbook/automation có xét tính lặp, concurrency, rollback, bảo toàn evidence và tác động nghiệp vụ?
7. **Verification:** có kiểm tra **effective state**, negative test và hậu quả phụ trên môi trường/phiên bản thực tế?
8. **Root cause:** nếu lỗi lặp hoặc nghiêm trọng, có phân tích điều kiện tạo sai lệch và biện pháp chống tái diễn?
9. **Evidence:** có thể nối finding → action → result → retest → risk decision không?
10. **Residual risk:** phần chưa sửa, dữ liệu đã bị ảnh hưởng, exception và thời hạn có rõ không?
11. **Monitoring:** có theo dõi lỗi automation, tỷ lệ tái diễn, evidence cũ, thay đổi và trigger đánh giá lại?

## 21. Bài tập tự kiểm tra

### Tình huống A — Alert có nhưng không có người xử lý

SIEM phát cảnh báo một tài khoản quản trị đăng nhập từ ngữ cảnh bất thường. Cảnh báo nằm trong dashboard ba ngày mà không có ticket hoặc người trực. Có thể coi chương trình đã có corrective control hiệu quả không?

**Gợi ý:** Chưa. Detector hỗ trợ chức năng **phát hiện**, nhưng thiếu luồng triage, quyền thực thi, escalation và hậu kiểm. Cần xác định response playbook, thời gian xử lý, bằng chứng giao cảnh báo tới đúng người và kết quả action; thử nghiệm đường xử lý đầu cuối.

### Tình huống B — PR đã merge nhưng lỗi còn ở production

Lỗi BOLA được sửa trong nhánh chính, integration tests trên CI đạt. Production vẫn chạy bản phát hành cũ và endpoint export chưa có test.

**Gợi ý:** Không thể đóng finding trên toàn production. Cần xác minh deployment/version, retest luồng đọc/sửa/export theo phạm vi, kiểm tra dữ liệu cũ nếu có và đánh giá current residual risk. PR/CI chỉ chứng minh bước phát triển, không thay thế kết quả thực tế.

### Tình huống C — Tự động thu hồi quyền gây mất dịch vụ

Một automation phát hiện service account có quyền quá rộng rồi xóa toàn bộ role, khiến job thanh toán dừng. Thiết kế corrective control sai ở đâu?

**Gợi ý:** Hành động không giới hạn vào **quyền dư thừa** và không kiểm tra tác động phụ. Cần quyền thực thi tối thiểu, thiết kế desired state, xác nhận dependency, gating khi hậu quả lớn, chế độ thử/rollback và test chức năng nghiệp vụ sau sửa.

### Tình huống D — Bucket private nhưng file đã bị tải

Một bucket nhạy cảm mở public trong hai giờ; công cụ tự đổi về private và báo SUCCESS. Security review chưa có dữ liệu truy cập đầy đủ.

**Gợi ý:** Control có thể đã sửa trạng thái quyền, nhưng chưa xử lý hết sự cố. Cần bảo toàn và đánh giá log trong giới hạn, xác định loại dữ liệu và phạm vi, điều tra khả năng exfiltration, sửa nguyên nhân tạo public policy và quyết định rủi ro/phản ứng theo thẩm quyền.

### Tình huống E — Thời gian khắc phục bị tính sai

Phát hiện được báo lúc 08:00, code được merge lúc 09:30, triển khai production lúc 10:20 nhưng retest lúc 11:00 mới phát hiện endpoint phụ vẫn lỗi. Dashboard hiển thị remediation time = 90 phút.

**Gợi ý:** Dashboard đang dùng mốc merge PR, không phải **trạng thái đã được xác minh**. Cần định nghĩa mốc kết thúc và theo dõi reopen/failed verification. Theo ca này chưa có thời gian khắc phục cuối cùng vì tiêu chí chưa đạt.

### Tình huống F — Backup và ransomware

Tổ chức khôi phục một máy từ backup thành công, nhưng tài khoản quản trị bị chiếm vẫn còn hoạt động và mã độc quay lại.

**Gợi ý:** Recovery đã phục hồi một phần năng lực, nhưng corrective action chưa xử lý credential/đường xâm nhập. Cần xác định root cause, thu hồi quyền/khóa liên quan, khôi phục môi trường sạch, kiểm tra lại quyền và giám sát trước khi kết luận.

## Kết luận

**Corrective control** là mắt xích chuyển **phát hiện và sai lệch bảo mật** thành **hành động có trách nhiệm, trạng thái được sửa và kết quả có thể kiểm chứng**. Nó khác với preventive/detective controls, thường phối hợp containment, remediation và recovery nhưng không nên bị đánh đồng với việc “đã đóng ticket”. Trong chương trình **SECURITY_SECURITY_ASSURANCE**, một corrective control đáng tin phải gắn với risk scenario và security requirement, có trigger đúng, phạm vi và quyền hợp lý, action an toàn, bằng chứng trước/sau, kiểm thử độc lập khi phù hợp, xử lý nguyên nhân tái diễn và quyết định residual risk rõ ràng. Chỉ khi các bước đó được chứng minh trên hệ thống trong phạm vi đánh giá, tổ chức mới có cơ sở kết luận **rủi ro đã được giảm bằng hành động thực tế**, thay vì bằng lời hứa hoặc kế hoạch.
