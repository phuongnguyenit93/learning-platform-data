# Quản lý phiên bản security standard

## 1. Quản lý phiên bản standard là gì?

**Quản lý phiên bản security standard** (*security standard version management*) là quy trình định danh, đánh giá thay đổi, phê duyệt, công bố, chuyển tiếp, giám sát áp dụng và lưu lịch sử những **bản phát hành khác nhau của một tiêu chuẩn bảo mật**. Mục tiêu không chỉ là biết tài liệu nào mới nhất, mà còn chứng minh được:

- **Yêu cầu cụ thể nào** có hiệu lực đối với từng hệ thống, đối tượng, môi trường và khoảng thời gian.
- **Ai có thẩm quyền** phê duyệt phiên bản và ngoại lệ.
- **Điều gì đã thay đổi** so với bản trước, vì sao thay đổi và rủi ro nào được giải quyết.
- **Những control, tiêu chuẩn phụ thuộc, cấu hình, kiểm thử và quy trình nào** phải điều chỉnh.
- **Hệ thống đã áp dụng phiên bản nào** và bằng chứng nào hỗ trợ kết luận.
- **Phiên bản cũ được xử lý ra sao**, kể cả hồ sơ phục vụ audit và điều tra trong quá khứ.

Một *security standard* thường cụ thể hóa yêu cầu của security policy thành các **quy tắc hoặc tiêu chí tối thiểu có tính bắt buộc trong phạm vi áp dụng**. Ví dụ, policy quy định mọi truy cập dữ liệu khách hàng phải được phân quyền; *API Authorization Standard* quy định phải kiểm tra quyền trên từng tài nguyên tại những đường đọc, sửa và xuất dữ liệu, kèm các tiêu chí kiểm chứng. Tiêu chuẩn có thể được sửa đổi theo rủi ro, mô hình kiến trúc hoặc khả năng triển khai mới.

Trong module **SECURITY_SECURITY_ASSURANCE**, phiên bản standard đóng vai trò **điểm neo yêu cầu** trong chuỗi:

**Risk/threat → Policy → Standard phiên bản cụ thể → Requirement → Control → Test/audit → Evidence → Kết luận assurance → Khắc phục, tái đánh giá.**

Nếu bỏ mất thông tin phiên bản, một kết quả test “PASS” có thể bị hiểu sai là đáp ứng yêu cầu hiện hành, trong khi nó chỉ kiểm chứng các tiêu chí của bản cũ.

> **Nguyên tắc cốt lõi:** “Mới nhất” không tự đồng nghĩa “đang có hiệu lực ở mọi nơi”, và “đã phát hành” không tự đồng nghĩa “đã triển khai”. Mọi kết luận tuân thủ hoặc security assurance phải ghi đúng **standard ID, phiên bản, phạm vi, thời điểm và bằng chứng áp dụng**.

## 2. Vì sao standard cần được quản lý theo phiên bản?

Trong phát triển và vận hành, tiêu chuẩn có thể thay đổi trước khi mọi ứng dụng kịp thích ứng. Nếu chỉ lưu một bản tài liệu và ghi đè nội dung, rất dễ xuất hiện các vấn đề:

1. **Không biết tiêu chí từng có hiệu lực:** audit hỏi một dịch vụ vào tháng trước phải đáp ứng quy tắc nào, nhưng bản cũ đã bị thay thế không còn hồ sơ.
2. **Đánh giá sai mức tuân thủ:** pipeline kiểm thử theo v1 trong khi đợt phát hành chịu yêu cầu v2.
3. **Thay đổi âm thầm:** người chỉnh sửa tài liệu làm chặt hơn quy tắc MFA hoặc quyền truy cập nhưng không có phê duyệt.
4. **Triển khai lệch pha:** đội A đã dùng v2, đội B vẫn dùng v1, đội C không biết có thời hạn chuyển tiếp.
5. **Bằng chứng không phù hợp:** log và kết quả kiểm thử ở staging được dùng để tuyên bố production đã đạt bản mới.
6. **Ngoại lệ thiếu kiểm soát:** một ứng dụng chưa đạt v2 và xin hoãn, nhưng không có risk owner hoặc thời hạn.
7. **Phụ thuộc chồng chéo:** phiên bản mới của tiêu chuẩn API mâu thuẫn với baseline xác thực hoặc quy trình kiểm thử cũ.

Quản lý phiên bản tốt tạo ra **truy vết lịch sử, thay đổi có kiểm soát và khả năng so sánh các kết luận assurance theo thời gian**.

| Câu hỏi cần trả lời | Nếu không quản lý phiên bản | Khi có hệ thống quản lý phù hợp |
| --- | --- | --- |
| Quy tắc nào áp dụng vào ngày phát hành? | Dễ suy từ bản mới nhất, có thể sai | Tra được phiên bản, hiệu lực, phạm vi |
| Vì sao yêu cầu thay đổi? | Thiếu lý do và người phê duyệt | Có change record liên kết rủi ro/phát hiện |
| Ai phải cập nhật control? | Trách nhiệm phân tán | Có impact assessment và action owner |
| Có thể dùng test cũ không? | Dễ tái sử dụng máy móc | Đối chiếu yêu cầu thay đổi và độ bao phủ test |
| Bản cũ đã được thay thế hoàn toàn? | Không nhìn thấy ứng dụng còn nợ | Có adoption register và ngoại lệ |
| Có thể kiểm toán một kỳ trước? | Thiếu artifact gốc và mốc thời gian | Giữ bản bất biến, biên bản và bằng chứng lịch sử |

## 3. Những khái niệm phải phân biệt

### 3.1. Policy, standard, baseline và phiên bản

| Đối tượng | Vai trò | Ví dụ về thay đổi |
| --- | --- | --- |
| **Security policy** | Quy định cấp quản trị: mục tiêu, nguyên tắc, thẩm quyền và nghĩa vụ | Yêu cầu kiểm tra quyền với dữ liệu khách hàng |
| **Security standard** | Tiêu chí bắt buộc cụ thể hóa policy, có phạm vi và điều kiện kiểm chứng | Quy định kiểm tra authorization theo đối tượng cho từng đường truy cập |
| **Security baseline** | Bộ cấu hình tối thiểu cho loại thành phần cụ thể | Profile cấu hình gateway, API, container hoặc database |
| **Procedure / runbook** | Trình tự, vai trò, bước thực hiện | Các bước cấp quyền, triển khai cấu hình, thu hồi token |
| **Control implementation** | Biện pháp được áp dụng trong hệ thống thực | Logic phân quyền trong Orders API |
| **Assurance evidence** | Bằng chứng hỗ trợ kết luận về thiết kế và hoạt động control | Test run, review, config snapshot, audit trail |

**Không phải mọi thay đổi kỹ thuật đều đòi hỏi đổi chính sách.** Cập nhật baseline của một framework có thể đáp ứng cùng standard đang hiệu lực. Ngược lại, nếu standard đổi tiêu chí bắt buộc, nhiều baseline và test phải thay đổi dù policy không sửa.

### 3.2. Bản nháp, bản đã phê duyệt và bản có hiệu lực

Một bản standard thường đi qua các trạng thái:

| Trạng thái | Ý nghĩa | Có dùng để kết luận tuân thủ hiện hành không? |
| --- | --- | --- |
| **Draft** | Đang soạn hoặc lấy ý kiến, chưa được cấp có quyền phê duyệt | Không, trừ khi chỉ dùng để đánh giá thử có ghi rõ |
| **Approved** | Nội dung được chấp thuận theo quy chế; có thể chưa tới ngày hiệu lực | Chưa mặc định áp dụng cho mọi hệ thống |
| **Effective / Active** | Đã có hiệu lực cho phạm vi và thời điểm xác định | Có, trong phạm vi tương ứng |
| **Transition / Grace period** | Có quy tắc chuyển đổi giữa bản cũ và bản mới | Phải xem điều khoản chuyển tiếp riêng |
| **Superseded** | Đã bị bản mới thay thế theo quan hệ được ghi rõ | Dùng để tra lịch sử, không mặc định áp dụng cho triển khai mới |
| **Retired / Withdrawn** | Không còn hiệu lực theo quyết định của cấp có quyền | Cần giữ hồ sơ quá khứ và đánh giá các hệ thống phụ thuộc |

**Ngày phê duyệt**, **ngày công bố**, **ngày bắt đầu hiệu lực** và **hạn hoàn tất chuyển tiếp** là những mốc khác nhau. Một tài liệu được ký ngày 01/06 nhưng quy định áp dụng cho hệ thống mới từ 01/07, hệ thống cũ chuyển đổi trước 30/09. Không thể chỉ dựa vào ngày trên đầu tài liệu để kết luận mọi hệ thống phải đáp ứng cùng lúc.

### 3.3. Phiên bản tài liệu và trạng thái áp dụng của hệ thống

Hãy tách hai loại dữ liệu:

- **Standard version:** tập yêu cầu đã được phê duyệt ở thời điểm/phạm vi cụ thể, ví dụ STD-API-AUTHZ v2.0.
- **Adoption/compliance state:** service X đã áp dụng đến đâu, có bằng chứng nào và ngoại lệ nào, ví dụ Orders API đang kiểm chứng v2.0.

Không nên biến “v2.0 đã phát hành” thành “Orders API v2.0 compliant”. Bằng chứng của việc triển khai là một công việc độc lập, cần người thực hiện và kiểm tra.

## 4. Thiết kế quy tắc định danh và đánh số phiên bản

### 4.1. Định danh bền vững

Mỗi standard nên có một **ID ổn định** xuyên suốt các lần sửa, chẳng hạn:

- STD-API-AUTHZ: tiêu chuẩn phân quyền API.
- STD-SECRET-MGMT: tiêu chuẩn quản lý bí mật ứng dụng.
- STD-LOGGING: tiêu chuẩn nhật ký và truy vết bảo mật.

ID giúp phân biệt **danh tính tài liệu** với **phiên bản tài liệu**. Cách ghi tham chiếu đầy đủ nên gồm cả hai: **STD-API-AUTHZ, revision 2.0**.

Khi chuẩn được chia tách hoặc gộp, cần ghi quan hệ **supersedes/replaced-by**, các ID mới và những yêu cầu được chuyển sang tài liệu nào. Không nên âm thầm tái sử dụng một ID cho mục đích khác.

### 4.2. Chọn chiến lược versioning

| Cách đánh số | Ví dụ | Ưu điểm và lưu ý |
| --- | --- | --- |
| **Revision tuần tự** | Rev 1, Rev 2, Rev 3 | Đơn giản; cần change log để biết loại thay đổi |
| **Major.Minor** | 1.0, 1.1, 2.0 | Phân biệt thay đổi lớn và nhỏ nếu quy tắc được định nghĩa |
| **Major.Minor.Patch** | 2.0.0, 2.1.0, 2.1.1 | Phù hợp quy trình quản lý chặt; không tự suy theo SemVer của phần mềm |
| **Mã edition/năm** | Edition 2026, Edition 2027 | Dễ gắn chu kỳ ban hành; năm không thay thế ngày hiệu lực |
| **Phiên bản do bên ngoài quy định** | Mã tiêu chuẩn và năm/edition của nhà phát hành | Phải dùng đúng danh tính, phạm vi và tình trạng áp dụng |

Nếu áp dụng dạng **Major.Minor.Patch** cho tài liệu nội bộ, có thể định nghĩa:

- **Major:** thay đổi nghĩa vụ quan trọng, phạm vi hoặc tiêu chí bắt buộc có thể ảnh hưởng đáng kể tới control và test.
- **Minor:** bổ sung hoặc làm rõ yêu cầu trong phạm vi hiện có, có thể cần thay đổi hoạt động nhưng không đổi nguyên tắc lớn.
- **Patch:** sửa chính tả, liên kết, ví dụ hoặc diễn đạt **không làm thay đổi nghĩa vụ**.

Đây là **quy ước nội bộ minh họa**, không phải quy tắc bắt buộc của Semantic Versioning đối với security standards. Một thay đổi “minor” về đánh số vẫn có thể gây tác động lớn cho một hệ thống cụ thể. **Impact assessment** quyết định việc phải làm, không phải chỉ nhìn chữ số.

### 4.3. Khi nào bắt buộc tạo phiên bản mới?

Những thay đổi sau cần được kiểm soát theo quy trình đã định:

- Thêm, xóa, thay điều khoản bắt buộc hoặc thay đổi đối tượng/phạm vi áp dụng.
- Thay mức tối thiểu của control, thời hạn xử lý, ngưỡng chấp nhận hoặc tiêu chí đánh giá.
- Bổ sung chuẩn mới được viện dẫn có tác động đến nghĩa vụ.
- Thay điều kiện ngoại lệ, quyền phê duyệt hoặc trách nhiệm giữa các nhóm.
- Sửa ví dụ/baseline dẫn đến cách hiểu khác về yêu cầu.
- Sửa lỗi văn bản không ảnh hưởng nghĩa vụ nhưng cần lưu vết để đảm bảo tính toàn vẹn lịch sử.

Với bản đã ban hành, **không sửa nội dung âm thầm** dưới cùng một mã phiên bản nếu điều đó khiến không thể tái dựng điều khoản từng có hiệu lực. Ngay cả sửa nhỏ nên có change record hoặc một revision phù hợp.

## 5. Metadata tối thiểu của một standard version

Một hồ sơ phiên bản nên có:

| Trường | Mục đích |
| --- | --- |
| **standard_id, title, version** | Định danh tài liệu và revision |
| **document_status** | Draft, Approved, Effective, Superseded, Retired... |
| **policy_refs** | Chính sách cấp trên được cụ thể hóa |
| **standard_owner / approval_authority** | Người soạn/duy trì và cấp có quyền phê duyệt |
| **approved_at, published_at, effective_from** | Mốc phê duyệt, công bố và bắt đầu áp dụng |
| **transition_deadline** | Hạn chuyển đổi khi có quy tắc chuyển tiếp |
| **scope** | Đơn vị, tài sản, loại hệ thống, môi trường, thay đổi mới hay hệ thống hiện hữu |
| **supersedes / superseded_by** | Quan hệ với phiên bản trước/sau |
| **change_log / change_request** | Nội dung, lý do, phân loại và phê duyệt thay đổi |
| **requirement_ids** | Các điều khoản ổn định để ánh xạ control và test |
| **referenced_external_editions** | Định danh/edition chuẩn bên ngoài nếu có |
| **review_due / review_triggers** | Kỳ và sự kiện cần đánh giá lại |
| **canonical_location / integrity** | Nơi lưu bản chính thức và cách kiểm tra tính nguyên vẹn |

Không nhất thiết đưa mọi trường trực tiếp vào văn bản người đọc; chúng có thể nằm trong một **standard register** hoặc hệ thống quản lý tài liệu liên kết tới bản chính thức. Điều cần đảm bảo là thông tin chính xác, có quyền sửa/phê duyệt và có lịch sử kiểm toán.

### 5.1. Ví dụ hồ sơ YAML có phân biệt các mốc

Mẫu sau là **dữ liệu giả định để học**, không phải tiêu chuẩn có hiệu lực tại một tổ chức thực:

~~~yaml
standard_id: "STD-API-AUTHZ"
title: "API Authorization Standard"
version: "2.0.0"
document_status: "APPROVED_NOT_YET_EFFECTIVE"
owner: "Security Architecture"
approval_authority: "Security Governance Board"
approved_at: "2026-11-15"
published_at: "2026-11-18"
effective_from: "2026-12-01"
supersedes:
  standard_id: "STD-API-AUTHZ"
  version: "1.3.0"
scope:
  new_services: "2026-12-01"
  existing_services_transition_deadline: "2027-02-28"
  environments:
    - "production"
    - "pre-production security testing"
policy_refs:
  - "POL-ACCESS-CONTROL"
requirements:
  - id: "AUTHZ-REQ-01"
    summary: "Kiem tra quyen tren doi tuong tai moi duong truy cap"
  - id: "AUTHZ-REQ-02"
    summary: "Export va batch phai ap dung kiem tra quyen tuong duong"
  - id: "AUTHZ-REQ-03"
    summary: "Yeu cau khong duoc cap quyen khong tra du lieu nhay cam"
change_request: "STD-CHANGE-DEMO-029"
review_triggers:
  - "Thay doi co che identity hoac delegation"
  - "Phat hien loi object authorization"
evidence_plan:
  - "Trace requirements to controls and tests"
  - "Integration tests per role and object"
  - "Production deployment/configuration review"
~~~

Vì trạng thái mẫu là **APPROVED_NOT_YET_EFFECTIVE**, không được dùng hồ sơ này làm căn cứ tuyên bố toàn bộ dịch vụ đã phải hoặc đã đáp ứng v2.0.0 trước ngày hiệu lực. Đối với hệ thống hiện hữu, phạm vi **giai đoạn chuyển tiếp** cần được giải thích trong quy định chính thức; không suy rằng mọi bản cũ được chấp thuận vô điều kiện đến hết hạn.

## 6. Quy trình quản lý thay đổi phiên bản từ đầu đến cuối

### Bước 1. Khởi tạo yêu cầu thay đổi (*change request*)

Nguồn có thể là risk assessment, threat modeling, kết quả pentest, audit, sự cố, thay đổi công nghệ, nghĩa vụ mới hoặc phản hồi từ người vận hành. Hồ sơ yêu cầu nên trả lời:

- Điều khoản nào chưa rõ hoặc không còn phù hợp?
- Thực tế nào cho thấy cần thay đổi?
- Rủi ro nếu giữ nguyên là gì; rủi ro mới do thay đổi có thể tạo ra?
- Những tài sản và nhóm vận hành nào chịu ảnh hưởng?
- Có cần hành động khẩn cấp trước khi ban hành revision không?

**Không dùng câu “cần nâng cấp version” thay cho mục đích an ninh cụ thể.** Cần nêu điều thay đổi nhằm giảm rủi ro hoặc làm rõ cách kiểm chứng nào.

### Bước 2. So sánh bản cũ và bản đề xuất theo từng requirement

Thực hiện **diff theo nghĩa vụ**, không chỉ diff theo ký tự. Một đoạn văn trông giống nhau vẫn có thể thay đổi lớn nếu thêm từ “mọi”, đổi “khuyến nghị” thành “phải” hoặc mở rộng phạm vi áp dụng.

Ví dụ:

| Requirement | Standard v1.3 | Đề xuất v2.0 | Tác động |
| --- | --- | --- | --- |
| AUTHZ-REQ-01 | Kiểm tra quyền với truy cập đơn hàng qua API | Làm rõ kiểm tra quyền theo đối tượng ở **từng đường truy cập** | Review các endpoint, job và service nội bộ |
| AUTHZ-REQ-02 | Chưa mô tả rõ batch/export | Yêu cầu batch/export áp dụng cùng chính sách quyền trên tập dữ liệu | Bổ sung control cho export, test dữ liệu hỗn hợp |
| AUTHZ-REQ-03 | Từ chối truy cập không được phép | Làm rõ không trả dữ liệu nhạy cảm khi bị từ chối | Review response và logging |
| AUDIT-REQ-01 | Chưa thay đổi | Giữ nguyên ở standard có liên quan | Không chuyển nội dung trái phạm vi nếu không có lý do |

**Requirement ID** nên duy trì bền vững khi ý nghĩa không đổi. Khi thay đổi nghĩa vụ căn bản, cần đánh dấu phiên bản/ngữ nghĩa của điều khoản hoặc phát hành ID mới với quan hệ thay thế, để bằng chứng cũ không bị ghép sai.

### Bước 3. Đánh giá tác động và kế hoạch chuyển đổi

Đánh giá ít nhất:

1. **Risk/asset:** threat scenario, hậu quả và mức rủi ro mà yêu cầu mới hướng tới.
2. **Kiến trúc:** control dùng chung và control riêng ở từng ứng dụng, trust boundary, luồng dữ liệu.
3. **Độ bao phủ:** có bao nhiêu hệ thống hiện tại đang sử dụng bản cũ; tài sản nào trọng yếu?
4. **Triển khai:** code, cấu hình, IAM, pipeline, baseline, quy trình vận hành và năng lực nhà cung cấp.
5. **Kiểm thử:** test nào cần thêm, sửa hoặc chạy lại; các kịch bản bị từ chối có đủ?
6. **Bằng chứng:** kết quả test/audit cũ còn phù hợp phần nào, phần nào phải xác minh lại?
7. **Đào tạo và truyền thông:** ai cần hiểu yêu cầu mới, tài liệu nào cần cập nhật?
8. **Nguồn lực, mốc và rủi ro chuyển tiếp:** phải có người chịu trách nhiệm và phương án giảm thiểu.

Không nên yêu cầu mọi nhóm cam kết “đạt v2” trước khi xác định rõ **các khoảng trống và chi phí thực thi**.

### Bước 4. Review liên chức năng, giải quyết xung đột

Policy/standard owner điều phối ý kiến của security architect, engineering, SRE, risk owner, data owner, pháp chế/compliance và assurance/audit khi phù hợp.

Những câu hỏi cần trả lời:

- Standard mới có phù hợp policy cấp trên không?
- Có trái với standard/baseline khác hay nghĩa vụ bắt buộc đang áp dụng không?
- Yêu cầu có kiểm chứng được bằng test hoặc bằng chứng vận hành?
- Có rủi ro do lùi/sửa quy định hoặc do thời gian chuyển tiếp?
- Ai có quyền quyết định ngoại lệ và phê duyệt bản chính thức?

Review kỹ thuật không thay thế **quyền phê duyệt**. Nếu bất đồng về chấp nhận rủi ro, phải chuyển đúng cấp có thẩm quyền.

### Bước 5. Phê duyệt và cố định bản phát hành

Sau khi phê duyệt, cần lưu:

- Standard ID + revision; bản nội dung chính thức bất biến hoặc có cơ chế lưu lịch sử đáng tin.
- Người/cấp phê duyệt, ngày phê duyệt, biên bản/đường dẫn quyết định.
- Ngày công bố, hiệu lực, thời hạn chuyển tiếp và phạm vi áp dụng.
- Change log, bản diff và lý do.
- Tham chiếu tới yêu cầu, các tài liệu cấp trên và liên quan.

Một **draft trong repository** hoặc pull request được merge **chưa mặc định** là standard đã được phê duyệt nếu điều lệ yêu cầu phê duyệt riêng. Cần có một **nguồn chính thức duy nhất** cho trạng thái có hiệu lực.

### Bước 6. Công bố và phân phối có kiểm soát

Truyền đạt phiên bản mới đến đúng đối tượng: nhóm sản phẩm, security, SRE, risk owner, nhà cung cấp hoặc đơn vị audit liên quan. Thông tin công bố nên trả lời:

- Ai cần chuyển sang bản mới; bản nào đang có hiệu lực cho họ?
- Những điều khoản nào thay đổi và do vì sao?
- Hạn áp dụng và điều kiện chuyển tiếp?
- Những hành động kỹ thuật, test, bằng chứng và đào tạo nào phải hoàn tất?
- Hỏi ai khi yêu cầu khó hiểu và chuyển cấp thế nào?

Tránh chỉ gửi liên kết “document updated” mà không có change summary. Người thực hiện cần hiểu **nghĩa vụ mới**, không chỉ biết có một file mới.

### Bước 7. Triển khai theo hệ thống và theo dõi áp dụng

Một **adoption register** nên ghi từng service và trạng thái, thay vì báo một con số tổng không có ngữ cảnh:

| Trường | Câu hỏi |
| --- | --- |
| Service, owner, environment | Tài sản và người chịu trách nhiệm nào? |
| Target standard ID/version | Phải đạt phiên bản nào theo phạm vi/hiệu lực? |
| Current evaluated version | Hiện có bằng chứng đánh giá theo phiên bản nào? |
| Gap và action owner | Thiếu yêu cầu nào, ai thực hiện thay đổi? |
| Due date/transition rule | Mốc nào áp dụng và có ngoại lệ nào hợp lệ? |
| Evidence references | Test run, config, review và môi trường/phiên bản nào? |
| Verification status | Unassessed, In progress, Failed, Verified, Exception approved...? |
| Risk owner và decision | Ai chịu trách nhiệm residual risk và quyết định gì? |
| Last verified/next trigger | Kết quả còn hợp lệ khi hệ thống đổi không? |

Trạng thái **“đã áp dụng v2”** nên có bằng chứng đáp ứng các điều khoản v2 trong phạm vi, không chỉ vì đội đã nhận email hoặc đổi một trường cấu hình thành “2.0”.

### Bước 8. Xác minh và đánh giá rủi ro còn lại

Control owner cung cấp bằng chứng; security/assurance reviewer đánh giá tính phù hợp và mức tin cậy:

- **Design effectiveness:** thiết kế control có giải quyết threat/risk của yêu cầu standard mới?
- **Implementation:** biện pháp đã đến đúng hệ thống và bản phát hành?
- **Operating effectiveness:** control có thực thi như mong đợi theo test, monitoring hoặc audit?
- **Coverage:** có tất cả những luồng liên quan, role, endpoint, tenant, môi trường và trường hợp thất bại?
- **Freshness:** test/audit có phù hợp với phiên bản hiện hành và những thay đổi gần nhất?

**Không hạ residual risk chỉ vì standard mới được ban hành.** Bằng chứng cần cho thấy control mới hoạt động hoặc có biện pháp bù trừ đã được kiểm chứng trong phạm vi phù hợp.

### Bước 9. Lưu trữ, thay thế và rút bản cũ

Khi phiên bản mới có hiệu lực hoặc kết thúc chuyển tiếp:

- Cập nhật trạng thái bản cũ theo quyết định: superseded/retired, không xóa lịch sử.
- Đóng hoặc gia hạn hợp lệ các ngoại lệ đang chuyển đổi theo đúng thẩm quyền.
- Lưu bản cũ, hồ sơ phê duyệt và bằng chứng thời kỳ trước để phục vụ audit/điều tra.
- Ngăn các hệ thống mới vô tình tham chiếu bản cũ khi không còn được phép.
- Theo dõi tài liệu/baseline/test phụ thuộc và cập nhật link.
- Đặt lịch review phiên bản mới theo rủi ro và các trigger.

Nếu cần **rollback** standard do phát hiện lỗi trong bản mới, rollback phải được xem là **một quyết định thay đổi có phê duyệt và lịch sử**. Không âm thầm sửa ngày hiệu lực hoặc xóa phiên bản đã ban hành.

## 7. Sơ đồ vòng đời và mối liên kết với assurance

~~~mermaid
flowchart TD
    A["Phát hiện nhu cầu: risk, audit, incident, thay đổi"] --> B["Đề xuất revision và phân tích diff"]
    B --> C["Đánh giá tác động: control, test, hệ thống, nghĩa vụ"]
    C --> D{"Được phê duyệt theo đúng thẩm quyền?"}
    D -- "Chưa" --> E["Điều chỉnh draft hoặc chuyển cấp"]
    E --> B
    D -- "Có" --> F["Cố định bản chuẩn và mốc hiệu lực"]
    F --> G["Công bố, lập kế hoạch chuyển tiếp"]
    G --> H["Triển khai control, cập nhật baseline và test"]
    H --> I["Kiểm thử, audit và thu thập bằng chứng"]
    I --> J{"Đáp ứng yêu cầu revision trong phạm vi?"}
    J -- "Chưa có đủ bằng chứng" --> K["Bổ sung đánh giá, không tự xác nhận đạt"]
    K --> I
    J -- "Không đạt" --> L["Ghi gap, xử lý/ngoại lệ theo thẩm quyền, retest"]
    L --> H
    J -- "Đạt" --> M["Ghi kết luận assurance và trạng thái adoption"]
    M --> N["Giữ lịch sử, theo dõi thay đổi và review tiếp"]
    N --> A
~~~

Sơ đồ thể hiện tiến trình quản trị, **không** có nghĩa mọi sự cố phải đợi chu kỳ phát hành standard. Trong tình huống đang có nguy cơ cấp bách, đội ứng cứu và control owner phải hành động theo quy trình ứng cứu/giảm thiểu được ủy quyền, đồng thời đưa thay đổi dài hạn vào quản trị standard.

## 8. Quản lý phụ thuộc và tiêu chuẩn bên ngoài

### 8.1. Standard nội bộ tham chiếu edition bên ngoài

Tổ chức có thể tham khảo chuẩn của **ISO/IEC**, **NIST**, **OWASP** hoặc một tiêu chí ngành trong security standard nội bộ. Khi viện dẫn cần ghi rõ:

- **Tên và định danh chính xác**, edition/năm hoặc revision được dùng.
- **Phạm vi:** điều khoản nào là yêu cầu nội bộ, điều khoản nào chỉ là tài liệu tham khảo.
- **Loại tham chiếu:** cố định phiên bản (*pinned*) hay theo phiên bản được cập nhật (*floating*).
- **Người theo dõi thay đổi:** ai đánh giá edition mới và mức ảnh hưởng.
- **Quyền sử dụng tài liệu** và hình thức lưu trữ/tham chiếu hợp lệ.

Không nên viết đơn giản “tuân thủ NIST/ISO phiên bản mới nhất” rồi mặc định tự động thay đổi nghĩa vụ đối với các nhóm. Standard mới của bên ngoài có thể đổi cấu trúc, thuật ngữ hoặc tiêu chí; tổ chức phải đánh giá tác động, cập nhật ánh xạ và phê duyệt áp dụng theo quy chế.

**Ví dụ:** nội bộ quản lý STD-LOGGING v3.0, có bảng ánh xạ tới một edition của chuẩn bên ngoài. Khi edition ngoài đổi, bản nội bộ **không tự trở thành v4.0**. Policy owner hoặc standard owner cần xem những yêu cầu nào đổi, có cần cập nhật control và bằng chứng, rồi đề xuất revision phù hợp.

### 8.2. Mối liên hệ giữa nhiều tài liệu nội bộ

Một standard có thể viện dẫn baseline cấu hình, tiêu chuẩn quản lý log và quy trình quản lý thay đổi. Nên duy trì **dependency matrix**:

| Tài liệu phụ thuộc | Loại liên kết | Khi STD-API-AUTHZ đổi cần làm gì? |
| --- | --- | --- |
| Access Control Policy | Yêu cầu cấp trên | Kiểm tra standard vẫn phù hợp chính sách |
| API Security Baseline | Cấu hình triển khai | Cập nhật hướng dẫn gateway, token, framework phù hợp |
| Secure Coding Standard | Quy tắc triển khai | Kiểm tra không mâu thuẫn về authorization |
| Security Test Standard | Tiêu chí kiểm thử | Bổ sung test xuất dữ liệu và truy cập chéo |
| Exception Procedure | Quy trình ngoại lệ | Xác định quyền phê duyệt và giai đoạn chuyển tiếp |
| Evidence Retention Rule | Quản lý bằng chứng | Bảo đảm test run, approval, diff có thể tra cứu |

Tránh vòng tham chiếu mâu thuẫn như Standard A bắt buộc B v2, nhưng B v2 chỉ hoạt động với A v1. Kiểm tra tham chiếu theo **ID + phiên bản hoặc dải tương thích được phê duyệt**, không dựa vào tên file gần giống.

### 8.3. Phiên bản kỹ thuật không đồng nghĩa phiên bản standard

Ứng dụng Spring Boot 3.x, thư viện bảo mật mới hoặc phiên bản container **không tự động** chứng minh đáp ứng một standard bảo mật. Một thay đổi library có thể ảnh hưởng cơ chế token/authorization, nhưng **yêu cầu chuẩn** là điều cần được kiểm tra riêng bằng thiết kế, cấu hình và hành vi.

Ngược lại, standard có thể được cập nhật để làm rõ test bắt buộc **mà không yêu cầu nâng framework** nếu triển khai hiện hành đã đáp ứng.

## 9. Tình huống thực hành: nâng phiên bản API Authorization Standard cho Java/Spring Boot

### 9.1. Bối cảnh

Một tổ chức đang sử dụng **STD-API-AUTHZ v1.3**. Standard yêu cầu xác thực và phân quyền khi truy cập tài nguyên khách hàng. Trong quá trình rà soát threat model, nhóm phát hiện các endpoint **đọc từng bản ghi** đã có test phân quyền, nhưng một số endpoint **xuất dữ liệu hàng loạt** chưa có tiêu chí test rõ ràng.

Tổ chức đề xuất **v2.0** để làm rõ:

1. Mọi đường đọc/sửa/xuất dữ liệu phải kiểm tra quyền của chủ thể trên đối tượng hoặc tập kết quả tương ứng.
2. Các trường hợp **truy cập chéo tài khoản** phải có test âm.
3. Bằng chứng được liên kết với build và môi trường đánh giá.
4. Phát hiện phải được kiểm thử lại sau khắc phục; không coi thay đổi mã là kết quả assurance.

Đây là tình huống **giả định**, không phải một tiêu chuẩn đang áp dụng trong thực tế.

### 9.2. Bảng tác động theo phiên bản

| Nhóm | Theo v1.3 | Thay đổi ở v2.0 | Hành động |
| --- | --- | --- | --- |
| Requirements | Quy định chung phân quyền tài nguyên | Làm rõ cả export/batch và quyền theo từng bản ghi | Cập nhật test plan và control mapping |
| Orders API | Có kiểm tra đơn hàng theo ID | Xem các đường list, export và batch | Review code và test âm A/B |
| Test | Chủ yếu test endpoint đọc một đơn | Thêm dữ liệu hỗn hợp và các role | Integration tests mới, chạy trên build mục tiêu |
| Evidence | Báo cáo build trước | Yêu cầu liên kết standard revision với test run | Cập nhật bằng chứng và reviewer |
| Risk | Tồn tại nguy cơ lộ dữ liệu nếu export không lọc quyền | Đánh giá lại phơi nhiễm và residual risk | Risk owner nhận kết luận có căn cứ |
| Transition | Các service đang dùng v1.3 | Cần lộ trình và hạn chuyển đổi | Giao action owner, mốc và ngoại lệ nếu cần |

Không kết luận “v1.3 yếu hơn” trong mọi hệ thống: một service đã bảo vệ export đúng có thể chỉ cần **bổ sung kiểm thử/bằng chứng**, trong khi service khác cần **sửa control**. Đây là lý do phải phân loại gap trên từng hệ thống.

### 9.3. Control minh họa ở Orders API

Giả sử endpoint:

~~~http
GET /api/orders/841
Authorization: Bearer <token-cua-khach-A>
~~~

Nếu đơn hàng 841 thuộc khách B, một yêu cầu đọc từ khách A phải bị từ chối theo chính sách phân quyền. Một triển khai minh họa có thể truy vấn theo orderId **và** customerId được ánh xạ từ **identity đã xác thực**:

~~~java
@Service
public class OrderReadService {
    private final OrderRepository orderRepository;
    private final CurrentCustomer currentCustomer;

    public OrderReadService(OrderRepository orderRepository,
                            CurrentCustomer currentCustomer) {
        this.orderRepository = orderRepository;
        this.currentCustomer = currentCustomer;
    }

    @Transactional(readOnly = true)
    public OrderView getOrder(long orderId) {
        long customerId = currentCustomer.customerId();

        return orderRepository.findByIdAndCustomerId(orderId, customerId)
                .map(OrderView::from)
                .orElseThrow(() ->
                    new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
~~~

Đây là mã **minh họa**, không phải ứng dụng biên dịch/chạy độc lập. Các kiểu **OrderRepository, CurrentCustomer, OrderView** cần được triển khai thực tế; CurrentCustomer phải lấy danh tính từ context đã được xác thực, không tin customerId do client tự khai. Trường hợp admin hoặc quyền được ủy quyền cần chính sách và test riêng; mã **403/404** khi thiếu quyền phải phù hợp yêu cầu API và không tiết lộ dữ liệu nhạy cảm.

**Điểm quan trọng:** bảo vệ endpoint GET đọc một đơn **không tự bảo vệ** endpoint export. v2.0 cần có control kiểm tra quyền trên **toàn bộ tập bản ghi trả về**, kể cả lọc, phân trang, export nền và worker liên quan.

### 9.4. Ma trận test phiên bản v2.0

| Kịch bản | Kết quả cần chứng minh | Evidence |
| --- | --- | --- |
| A đọc đơn của A | Trả đúng dữ liệu theo quyền | Test dương |
| A đọc đơn của B | Không trả thông tin B | Test âm |
| A export dữ liệu có cả A và B | Chỉ có những bản ghi A được phép xem | Test tập dữ liệu hỗn hợp, kiểm tra nội dung xuất |
| A thay ID/điều kiện lọc | Không vòng qua authorization | Test âm theo biến thể đầu vào |
| Vai trò được ủy quyền hợp lệ | Quyền chỉ trong phạm vi cho phép | Test role và chính sách đặc biệt |
| Token không hợp lệ hoặc đã bị thu hồi theo cơ chế | Yêu cầu bị từ chối phù hợp chính sách | Test xác thực |
| Bản build được triển khai | Test gắn đúng commit, cấu hình, môi trường | Build ID, test run ID, thời gian, reviewer |
| Đã có lỗi và đã sửa | Lỗi không còn trên bản sửa; có hồi quy liên quan | Ticket, thay đổi mã, retest đạt |

Không dùng “CI xanh” làm kết luận compliance nếu suite không có test tương ứng các nghĩa vụ v2.0 hoặc chạy trên build không phải bản triển khai.

### 9.5. Ví dụ adoption record

Hồ sơ giả định sau cho thấy **chưa được xác minh**, dù standard v2 đã được phê duyệt:

~~~yaml
service: "orders-api"
owner: "Orders API Team"
environment: "production"
standard:
  id: "STD-API-AUTHZ"
  required_version: "2.0.0"
  applicability_basis: "Chuyen tiep theo quy dinh ban hanh"
current_evaluated_version: "1.3.0"
adoption_status: "IN_PROGRESS"
controls:
  - id: "CTRL-OBJECT-AUTHZ"
    action: "Rao soat authorization tren batch va export"
  - id: "CTRL-AUTHZ-TEST"
    action: "Them integration test du lieu hon hop"
evidence:
  - requirement: "AUTHZ-REQ-02"
    test_run_ref: null
    state: "NOT_VERIFIED"
risk_owner: "Orders Product Owner"
control_owner: "Orders API Tech Lead"
action_owner: "Orders API Team"
exception:
  approved: false
  approval_ref: null
closure_criteria:
  - "Test am A/B va export dat tren build muc tieu"
  - "Review cac duong truy cap tuong tu"
  - "Reviewer xac nhan evidence dung pham vi"
~~~

Dữ liệu này chỉ minh họa mối quan hệ giữa **revision được yêu cầu, revision đã được đánh giá và trạng thái áp dụng**. Trước khi dùng trong audit thật, phải có mốc thời gian, cơ sở áp dụng, ngày chuyển tiếp, phê duyệt, liên kết test run thực và người đánh giá cụ thể.

## 10. Ngoại lệ, giai đoạn chuyển tiếp và trường hợp khẩn cấp

### 10.1. Chuyển tiếp có điều kiện

Khi tiêu chuẩn mới có phạm vi lớn, có thể cần giai đoạn chuyển tiếp. Điều khoản chuyển tiếp nên xác định:

- Đối tượng nào phải đáp ứng **ngay** (ví dụ hệ thống mới sau ngày hiệu lực).
- Đối tượng nào có **hạn chuyển đổi**; phần nào của bản cũ còn được công nhận đến mốc nào.
- Những trường hợp rủi ro cao phải khắc phục sớm hoặc áp dụng control tạm thời.
- Cách đo tiến độ, yêu cầu bằng chứng và thời điểm chuyển cấp.
- Quy trình khi không kịp hạn hoặc một yêu cầu không thể đáp ứng.

Không nên sử dụng “grace period” như sự cho phép bỏ qua mọi kiểm soát. Trong thời gian chuyển tiếp vẫn phải quản lý rủi ro và tuân thủ các nghĩa vụ hiện hành.

### 10.2. Ngoại lệ khi chưa đáp ứng bản mới

Một ngoại lệ hợp lệ cần:

1. Standard ID, phiên bản, điều khoản cụ thể và phạm vi dịch vụ.
2. Lý do không đáp ứng và risk scenario liên quan.
3. Bằng chứng trạng thái control hiện có, khoảng trống và hạn chế.
4. Control bù trừ và kết quả kiểm tra tính hiệu quả nếu có.
5. Risk owner và **người có quyền phê duyệt ngoại lệ**.
6. Thời hạn hết hiệu lực, mốc khắc phục và hành động chuyển cấp.
7. Điều kiện thu hồi ngoại lệ hoặc đánh giá lại khi có thay đổi.

Một ticket “đã nhận rủi ro” không phải phê duyệt hợp lệ nếu thiếu đúng quyền. **Ngoại lệ nội bộ không thể tự miễn trừ nghĩa vụ pháp lý bắt buộc.**

### 10.3. Bản sửa khẩn cấp của standard

Khi có threat hoặc phát hiện nghiêm trọng, tổ chức có thể cần phát hành bổ sung/đính chính khẩn cấp:

- Xác định phạm vi rủi ro và biện pháp giảm thiểu tức thời.
- Sử dụng cơ chế phê duyệt khẩn cấp đã được quy định, không tự bỏ qua quyền hạn.
- Phát hành một revision/erratum có truy vết, mốc hiệu lực và đối tượng áp dụng.
- Thông báo rõ điều kiện chuyển tiếp hoặc yêu cầu xử lý ngay.
- Sau khi ổn định, rà soát hậu kiểm nguyên nhân và cập nhật standard chính thức.

Việc dùng một hotfix kỹ thuật để bảo vệ hệ thống **có thể diễn ra trước** khi văn bản standard được cập nhật, theo quy trình ứng cứu/thay đổi khẩn cấp có thẩm quyền; không chờ tài liệu hoàn chỉnh mới xử lý nguy cơ đang tồn tại.

## 11. Quản trị trách nhiệm bằng RACI

Các vai trò cần phân biệt:

- **Standard owner:** soạn, duy trì, đề xuất sửa, quản lý phiên bản và chất lượng tài liệu.
- **Approval authority:** quyết định phê duyệt revision, hiệu lực và những ngoại lệ thuộc quyền.
- **Risk owner:** chịu trách nhiệm quyết định xử lý/chấp nhận residual risk của tài sản/nghiệp vụ trong quyền được giao.
- **Control owner:** bảo đảm control đáp ứng yêu cầu, có bằng chứng và xử lý sai lệch.
- **Developer/SRE:** triển khai, vận hành, viết/chạy test, cung cấp thông tin thực tế.
- **Assurance/audit reviewer:** đánh giá bằng chứng và nêu kết luận trong phạm vi, bảo vệ tính độc lập khi cần.

Ma trận **RACI** minh họa (R = thực hiện, A = chịu trách nhiệm cuối cùng, C = tham vấn, I = thông báo):

| Hoạt động | Standard owner | Cấp phê duyệt | Control owner/kỹ thuật | Risk owner | Assurance/audit |
| --- | --- | --- | --- | --- | --- |
| Đề xuất/soạn revision | **A/R** | I | C | C | C |
| Đánh giá tác động triển khai | **A** | I | **R** | C | C |
| Phê duyệt standard version mới | R | **A** | C | C | I |
| Cập nhật control/test ở từng service | C | I | **A/R** | C | C |
| Đánh giá độc lập bằng chứng (nếu thực hiện) | I | I | C | I | **A/R** |
| Chấp nhận residual risk theo quyền risk owner | C | I | C | **A/R** | I |
| Theo dõi lịch review và bản bị thay thế | **A/R** | I | C | I | I |

Ma trận chỉ là **gợi ý** và phải điều chỉnh theo điều lệ thật. Một hoạt động cần xác định chủ thể chịu trách nhiệm cuối cùng; các vai trò R có thể là nhiều người. Nếu một người vừa triển khai vừa đánh giá control rủi ro cao, nên có cơ chế rà soát chéo phù hợp.

## 12. Đo hiệu quả quản lý phiên bản

Đừng chỉ đếm số standard đã nâng version. Các chỉ số nên đánh giá **mức độ truy vết, chất lượng chuyển đổi và hiệu quả bảo mật**:

| Chỉ số | Cách hiểu | Cảnh báo |
| --- | --- | --- |
| Tỷ lệ standard đang hiệu lực có đủ owner, approval, effective date | Mức đầy đủ quản trị phiên bản | Có metadata không tự chứng minh control hiệu quả |
| Tỷ lệ thay đổi quy phạm có diff, impact assessment và phê duyệt | Mức kiểm soát thay đổi | Không chỉ tính số PR đã merge |
| Tỷ lệ service đã **xác minh** đạt phiên bản bắt buộc | Tiến độ adoption thực, có bằng chứng | Không coi email nhận thông báo hoặc chỉnh nhãn là compliant |
| Tỷ lệ yêu cầu trọng yếu có mapping tới control/test | Khả năng truy vết | Mapping có thể chưa phản ánh test đủ độ bao phủ |
| Tỷ lệ bằng chứng đúng revision, build và môi trường | Chất lượng assurance | Bằng chứng lỗi thời không hỗ trợ kết luận bản mới |
| Số ngoại lệ chuyển tiếp quá hạn | Kỷ luật quản lý rủi ro còn lại | Xem mức phơi nhiễm và điều kiện của từng ngoại lệ |
| Tuổi của gap trọng yếu chưa xác minh khắc phục | Rủi ro tồn đọng sau thay đổi standard | Không tính chỉ dựa ngày ticket đóng |
| Thời gian từ approval đến adoption đạt | Hiệu quả phối hợp thực thi | Cần phân nhóm độ phức tạp và mức rủi ro |

**Ví dụ giả định:** một standard v2 áp dụng cho 20 dịch vụ. Có 11 dịch vụ có bằng chứng hợp lệ đạt v2, 5 dịch vụ đang chuyển đổi, 2 có ngoại lệ còn hiệu lực và 2 chưa được đánh giá. Tỷ lệ **đã xác minh đạt** là **11/20 = 55%**, không phải 90% vì “đã gửi thông báo cho 18 dịch vụ”. Hai ngoại lệ **không tự được tính là đáp ứng**, và cần báo riêng trạng thái rủi ro của chúng.

Mức 55% cũng **không có nghĩa hệ thống an toàn 55%**. Một dịch vụ chưa đánh giá có thể xử lý dữ liệu quan trọng hơn nhiều dịch vụ đã được kiểm chứng.

### 12.1. Chất lượng kết luận assurance theo version

Khi báo cáo kết quả, nên trình bày ít nhất:

- Standard ID và revision áp dụng, nguồn phê duyệt.
- Hệ thống, build/version, môi trường và khoảng thời gian đánh giá.
- Requirement IDs và phạm vi các trường hợp kiểm tra.
- Bằng chứng, người review, trạng thái và giới hạn.
- Phát hiện hoặc ngoại lệ còn mở, risk owner và kế hoạch xử lý.
- Kết luận chính xác: **Đạt trong phạm vi**, **Không đạt**, **Chưa đủ bằng chứng** hoặc **Ngoại lệ có điều kiện**.

Không sử dụng một trường boolean **compliant=true** đơn lẻ làm thay thế cho toàn bộ thông tin cần truy vết.

## 13. Những sai lầm thường gặp

### 13.1. Ghi đè bản cũ rồi mất lịch sử

Người đánh giá không thể biết yêu cầu nào áp dụng tại một mốc thời gian. **Khắc phục:** lưu revision bất biến, change log, thời điểm hiệu lực và quan hệ thay thế.

### 13.2. Nhầm bản đã phê duyệt với bản đang có hiệu lực

Một revision đã ký nhưng chưa tới ngày áp dụng không đồng nghĩa mọi hệ thống đã phải đạt. **Khắc phục:** tách approved/published/effective, đối tượng áp dụng và lịch chuyển tiếp.

### 13.3. Dựa vào số phiên bản để quyết định tác động

Một bản 2.1 có thể thêm yêu cầu kiểm thử quan trọng; một bản 3.0 có thể thay chủ yếu cấu trúc. **Khắc phục:** phân tích diff theo requirement và impact cho từng hệ thống.

### 13.4. Viện dẫn “phiên bản mới nhất” của chuẩn bên ngoài

Không rõ edition thực tế, có thể làm nghĩa vụ thay đổi tự động và không qua phê duyệt. **Khắc phục:** ghi edition chính xác, cơ chế theo dõi cập nhật và quyết định áp dụng.

### 13.5. Chỉ cập nhật tài liệu, bỏ qua test và control

Standard mới đã ban hành nhưng pipeline vẫn dùng các ca test cũ, triển khai chưa thay đổi. **Khắc phục:** ánh xạ requirement phiên bản mới tới backlog, kiểm thử và bằng chứng trên build mục tiêu.

### 13.6. Cho rằng test của bản trước chứng minh bản mới

Một test cũ có thể vẫn hợp lệ **cho những điều khoản không đổi**, nhưng không chứng minh yêu cầu mới. **Khắc phục:** rà lại phạm vi, bổ sung test và ghi kết luận riêng theo requirement.

### 13.7. Kéo dài chuyển tiếp hoặc ngoại lệ không có quyết định

Tổ chức tồn tại hai phiên bản với thời hạn không rõ, không có người chịu trách nhiệm. **Khắc phục:** xác định đối tượng, hạn, risk owner, phê duyệt và cảnh báo quá hạn.

### 13.8. Thu hồi phiên bản cũ quá sớm

Dữ liệu kiểm toán và điều tra cần tái dựng tiêu chuẩn áp dụng tại thời điểm trước. **Khắc phục:** lưu trữ bản đã thay, metadata, biên bản và bản ghi bằng chứng theo thời hạn phù hợp.

### 13.9. Trộn các lớp tài liệu

Tăng version policy, standard, baseline, test artifact và ứng dụng đồng thời mà không rõ thay đổi nào là bắt buộc. **Khắc phục:** mỗi loại có định danh, owner và lifecycle riêng, liên kết bằng dependency matrix.

## 14. Checklist quản lý phiên bản standard

- [ ] Mỗi standard có **ID bền vững**, tiêu đề, owner và nguồn chính thức.
- [ ] Quy ước đánh số revision và quy tắc thay đổi đã được phê duyệt.
- [ ] Phiên bản đang hiệu lực có người phê duyệt, ngày phê duyệt, công bố và hiệu lực rõ.
- [ ] Quy tắc áp dụng cho hệ thống mới/cũ và thời hạn chuyển tiếp được công bố.
- [ ] Bản đã phát hành được giữ nguyên hoặc có lịch sử sửa đổi tin cậy.
- [ ] Bản mới có change request, diff theo requirement và lý do thay đổi.
- [ ] Có đánh giá tác động lên rủi ro, tài sản, kiến trúc, control, baseline và test.
- [ ] Đã kiểm tra tham chiếu đến chính sách và edition chuẩn bên ngoài.
- [ ] Các yêu cầu mới có **ID ổn định**, tiêu chí kiểm chứng và owner.
- [ ] Có kế hoạch triển khai từng hệ thống với action owner và mốc kiểm tra.
- [ ] Có bằng chứng về thiết kế, triển khai và vận hành control đúng **revision**.
- [ ] Test run liên kết build, cấu hình, môi trường, phạm vi và người review.
- [ ] Ngoại lệ có đánh giá rủi ro, thẩm quyền, điều kiện và hạn.
- [ ] Bản cũ có trạng thái superseded/retired và có khả năng truy xuất lịch sử.
- [ ] Có trigger cập nhật khi threat, sự cố, kiến trúc hoặc chuẩn bên ngoài thay đổi.
- [ ] Báo cáo adoption phân biệt **Verified / In progress / Exception / Unassessed / Failed**.
- [ ] Không suy luận đã an toàn chỉ từ việc standard được ban hành hoặc hệ thống đổi nhãn version.

Checklist này hỗ trợ quy trình quản trị; **không thay thế kiểm chứng control hoặc audit chuyên môn**.

## 15. Câu hỏi tự kiểm tra

1. Vì sao cần lưu cả **standard version** lẫn **adoption state** cho từng hệ thống?
2. Một standard được phê duyệt ngày 01/06, hiệu lực 01/07 và các service cũ có hạn 30/09. Vào ngày 15/06 hoặc 15/08, có thể kết luận tất cả service phải hoặc đã tuân thủ phiên bản mới không? Cần kiểm tra gì?
3. Khi tiêu chuẩn bên ngoài xuất bản edition mới, standard nội bộ có tự đổi phiên bản và nghĩa vụ không?
4. Khác nhau giữa sửa chính tả trong standard và sửa quy tắc bắt buộc “phải kiểm tra quyền cho mọi endpoint” là gì? Cần hồ sơ nào?
5. Nếu test của v1.3 đã PASS nhưng v2.0 thêm yêu cầu cho API export, nhóm cần tạo những bằng chứng nào?
6. Vì sao việc nâng Spring Boot hoặc cập nhật thư viện bảo mật không tự chứng minh service đạt security standard mới?
7. Với 20 dịch vụ, 11 đạt có bằng chứng, 5 đang làm, 2 có ngoại lệ và 2 chưa đánh giá, tỷ lệ đạt được xác minh là bao nhiêu? Có nên cộng hai ngoại lệ vào tỷ lệ đạt không?
8. Một nhóm muốn “rollback” standard để đơn giản hóa triển khai. Cần những quyết định, đánh giá tác động và lưu vết nào?
9. Ai có quyền chấp nhận residual risk của một ứng dụng không kịp chuyển v2? Vai trò control owner và reviewer là gì?
10. Vì sao một kết luận “compliant=true” không có revision, build, môi trường và bằng chứng là yếu?
11. Bản standard cũ đã bị thay thế nên xóa khỏi hệ thống tài liệu hay giữ để kiểm tra quá khứ? Vì sao?
12. Những sự kiện nào nên kích hoạt rà soát phiên bản trước kỳ hạn định kỳ?

## 16. Tổng kết

**Quản lý phiên bản security standard** là quản lý **sự thay đổi của các yêu cầu bảo mật có tính bắt buộc** theo một quy trình có định danh, phân quyền, ngày hiệu lực, thời hạn chuyển tiếp và lịch sử quyết định rõ ràng. Để phiên bản mới tạo ra giá trị, tổ chức phải nối từng thay đổi với **rủi ro và policy**, xác định **control và test bị ảnh hưởng**, theo dõi **trạng thái áp dụng theo hệ thống** và thu thập **bằng chứng assurance đúng revision, build, môi trường và phạm vi**. Khi phát hiện chưa đạt, phải quản lý khắc phục, ngoại lệ và residual risk theo đúng thẩm quyền. Mục tiêu không phải nâng số phiên bản nhanh, mà là duy trì **một hệ thống tiêu chuẩn có thể truy vết, thực thi và kiểm chứng liên tục trong phát triển và vận hành**.
