# Requirement có thể kiểm thử: viết yêu cầu bảo mật đo được và chứng minh bằng bằng chứng

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích thế nào là **security requirement có thể kiểm thử** (*testable security requirement*) và phân biệt **security objective, requirement, security control, acceptance criterion, test case, evidence**.
2. Chuyển từ tài sản, mối đe dọa, kịch bản rủi ro và nghĩa vụ đã xác định thành yêu cầu có **đối tượng, hành vi, điều kiện, ranh giới, kết quả quan sát được và owner**.
3. Nhận diện yêu cầu mơ hồ như “bảo mật cao”, “nhanh chóng”, “mã hóa an toàn”, “chỉ người hợp lệ” và viết lại thành những phát biểu kiểm tra được mà **không tự bịa ngưỡng áp dụng chung**.
4. Tạo **acceptance criteria** cho đường thành công, truy cập bị cấm, dữ liệu biên, lỗi phụ thuộc, thu hồi quyền và trạng thái không xác định.
5. Thiết kế **verification method** phù hợp: review, static analysis, automated test, integration test, fault injection, configuration assessment, audit sampling và theo dõi vận hành.
6. Tổ chức **traceability** từ risk → requirement → control → test → evidence → finding → retest, kèm version/scope của kết luận assurance.
7. Đánh giá **tính đầy đủ, độ tin cậy và độ mới của bằng chứng**, phát hiện các yêu cầu chưa thể xác minh, thiếu test hoặc chưa thỏa điều kiện vận hành.
8. Dùng mẫu requirement có cấu trúc, Gherkin, ma trận kiểm thử, quality gates và checklist để làm việc cùng product, security, engineering, QA, operations và audit.

Trong module **SECURITY_SECURITY_ASSURANCE**, mục tiêu không chỉ là có danh sách yêu cầu bảo mật. Trong chương **Security requirements**, tổ chức phải **đánh giá có bằng chứng rằng hệ thống đáp ứng mục tiêu**: từ phân tích rủi ro, requirement và security control, qua kiểm thử, audit, xử lý phát hiện và tái đánh giá liên tục khi phần mềm thay đổi. Một requirement không thể kiểm thử sẽ tạo khoảng trống lớn: đội phát triển không biết thế nào là hoàn tất, kiểm thử không có oracle và auditor không đủ căn cứ để đưa ra kết luận.

> **Ý tưởng then chốt:** Một yêu cầu “nghe đúng” chưa chắc **có thể kiểm thử**. Yêu cầu có thể kiểm thử phải cho phép một người kiểm tra độc lập trả lời: **Kiểm tra cái gì, trong điều kiện nào, kỳ vọng gì, dựa vào dữ liệu nào và bằng chứng nào đủ để kết luận PASS, FAIL hoặc chưa thể kết luận?**

## 1. Requirement có thể kiểm thử là gì?

**Requirement có thể kiểm thử** là phát biểu mô tả một thuộc tính hoặc hành vi bắt buộc của hệ thống sao cho có thể **xác minh khách quan** bằng phương pháp được xác định trong phạm vi đã biết. Đối với bảo mật, thuộc tính đó có thể là việc chặn truy cập trái phép, bảo vệ dữ liệu, ghi dấu vết, giới hạn quyền, phát hiện bất thường, khôi phục an toàn hoặc duy trì kiểm soát khi thành phần bị lỗi.

Ví dụ:

- Mơ hồ: **“API phải có phân quyền chặt chẽ.”**
- Rõ hơn: **“API tra cứu hóa đơn phải xác minh người gọi có quyền `invoice.read` đối với hóa đơn được yêu cầu, dựa trên tenant sở hữu hóa đơn từ nguồn dữ liệu có thẩm quyền; request ngoài phạm vi phải bị từ chối và không trả nội dung hóa đơn.”**
- Có thể kiểm chứng hơn nữa: bổ sung **endpoint/version/môi trường**, cơ chế xác định identity, chính sách ngoại lệ, các tình huống đối tượng thật/giả mạo, expected response/data state và loại bằng chứng cần giữ.

Yêu cầu tốt không nhất thiết chứa toàn bộ mã kiểm thử trong một câu. Nhưng phải **đủ rõ để suy ra tiêu chí chấp nhận khách quan**, được liên kết tới test và evidence theo version.

### 1.1. Phân biệt các khái niệm

| Khái niệm | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| **Security objective** | Chúng ta muốn bảo vệ điều gì? | Dữ liệu hóa đơn không bị truy cập chéo tenant |
| **Risk/threat scenario** | Điều gì có thể xảy ra, bằng cách nào và gây hại gì? | Attacker đổi invoice ID để xem hóa đơn của tenant khác |
| **Security requirement** | Hệ thống **phải bảo đảm** thuộc tính/hành vi nào? | Mọi request invoice.read phải được kiểm tra object-level authorization |
| **Security control** | Biện pháp nào được triển khai để đạt yêu cầu? | Authorization middleware + ownership lookup + database guard |
| **Acceptance criterion** | Điều kiện nào chứng minh requirement thỏa? | User tenant B yêu cầu invoice tenant A thì không nhận được dữ liệu |
| **Test case** | Kiểm tra cụ thể được thực hiện ra sao? | Gọi API với hai tài khoản khác tenant, assert response và DB/output |
| **Evidence** | Bản ghi đáng tin nào chứng minh điều đã diễn ra? | Test result, request trace, config, policy version và dữ liệu trạng thái |
| **Finding** | Phát hiện chênh lệch nào chưa đạt? | Export worker bỏ qua kiểm tra ownership |
| **Assurance claim** | Có thể kết luận điều gì trong scope đã xác minh? | API v2 tại production chặn đọc chéo tenant theo test và sampling đã nêu |

Một requirement như “sử dụng WAF” thường chỉ mô tả **control hoặc giải pháp được chọn**. Nó chưa nói rõ mục tiêu cần đạt, điều kiện đánh giá và cách chứng minh control có hiệu quả. Trong một số bối cảnh **bắt buộc dùng công nghệ cụ thể** là yêu cầu hợp lệ (ví dụ yêu cầu kiến trúc/hợp đồng), nhưng vẫn cần tiêu chí **triển khai đúng, cấu hình đúng, phạm vi đủ và kiểm chứng thực tế**.

### 1.2. Testability khác các thuộc tính chất lượng khác

Requirement tốt cần nhiều đặc tính:

- **Correct:** phản ánh đúng mục tiêu, rủi ro và nghĩa vụ.
- **Necessary:** có lý do cần thiết, không tạo quy tắc thừa.
- **Unambiguous:** một cách hiểu được ưu tiên, không để người đọc tự đoán.
- **Atomic:** có thể đánh giá từng nghĩa vụ độc lập hoặc tách thành các yêu cầu con.
- **Feasible:** có thể triển khai và xác minh trong kiến trúc/nguồn lực thực tế.
- **Consistent:** không mâu thuẫn với requirement khác hoặc baseline.
- **Traceable:** liên kết được với nguồn, owner, control, test và evidence.
- **Testable/verifiable:** có phương pháp kiểm tra, expected outcome và phạm vi.
- **Maintainable:** được version hóa và cập nhật khi điều kiện thay đổi.

**Testability không bảo đảm requirement đúng:** Có thể kiểm thử hoàn hảo một quy tắc **cho phép truy cập trái phép** nếu chính quy tắc sai. Vì vậy phải đánh giá **nguồn gốc, độ phù hợp với rủi ro và tính đầy đủ** trước khi chỉ tập trung vào câu chữ.

## 2. Vì sao security requirement thường khó kiểm thử?

### 2.1. Khác biệt so với happy-path chức năng

Requirement chức năng thường nói “khi người dùng hợp lệ bấm nút, đơn hàng được tạo”. Security requirement còn đòi hỏi kiểm tra:

1. **Ai không được phép** làm việc đó?
2. Request bị **giả mạo, sửa tham số, phát lại hoặc vượt scope** thì sao?
3. Khi **IdP, policy engine, KMS hoặc audit pipeline lỗi**, hệ thống hành xử thế nào?
4. Có **bản sao dữ liệu** hoặc đường xử lý bất đồng bộ nào bỏ qua kiểm soát?
5. Khi quyền bị thu hồi giữa lúc check và use, kết quả có còn hợp lệ?
6. Khi kiểm thử chỉ quan sát HTTP 403, có chứng minh **không có side effect** phía sau không?

Vì vậy, chỉ có **positive test** cho user hợp lệ không đủ để bảo đảm authorization, integrity hoặc resilience.

### 2.2. Những từ khiến yêu cầu mơ hồ

| Cụm từ chưa đủ | Vì sao khó test? | Cách làm rõ |
|---|---|---|
| “An toàn”, “bảo mật cao” | Không nói thuộc tính hay threat nào | Chỉ rõ confidentiality/integrity/availability, scope và risk |
| “Nhanh nhất có thể” | Không có mức đo và hoàn cảnh | Chọn threshold và cách đo theo business/SLO được phê duyệt |
| “Chỉ người được phép” | Không có định nghĩa quyền | Xác định principal, action, resource, policy và owner |
| “Mã hóa mạnh” | Không có thuật toán/mode, phạm vi và key policy | Tham chiếu cryptographic baseline được duyệt, kiểm tra thực thi |
| “Mọi dữ liệu” | Có thể thiếu log, backup, export, vendor | Liệt kê population/inventory và trạng thái N/A/unknown |
| “Ghi log đầy đủ” | Không biết trường nào, ai nhận, độ trễ | Định nghĩa event schema, coverage, retention, integrity và test |
| “Không bao giờ lỗi” | Không thực tế, không có model lỗi | Mô tả fault conditions, safe behavior, RTO/RPO/SLO |
| “Theo tiêu chuẩn hiện hành” | Không rõ phiên bản, scope, kiểm soát | Chốt chuẩn/baseline/version đã áp dụng và owner |
| “Định kỳ” | Không biết tần suất | Chốt chu kỳ/trigger được phê duyệt, proof of execution |
| “Theo yêu cầu luật” | Luật/điều kiện/ngoại lệ chưa xác định | Privacy/legal xác nhận obligation matrix và phạm vi |

**Tránh tự điền số liệu vì muốn có vẻ đo được.** Thời gian khóa tài khoản, retention log, độ dài khóa, giới hạn latency, RTO/RPO hoặc ngưỡng risk phải dựa trên baseline, risk appetite, nghĩa vụ và kiến trúc được phê duyệt. Trong bài này, các con số trong ví dụ đều là **giả định để học cách xác minh**, không phải khuyến nghị bắt buộc cho mọi hệ thống.

### 2.3. Security requirement có thể là ràng buộc phủ định

Yêu cầu an ninh nhiều khi được mô tả dưới dạng **không cho phép**:

- Không trả dữ liệu người khác.
- Không ghi secret vào log.
- Không dùng khóa bị thu hồi để mã hóa dữ liệu mới.
- Không hoàn tất giao dịch hai lần khi retry.
- Không bỏ qua kiểm tra quyền khi policy engine timeout.

Không thể chứng minh một thuộc tính phủ định là **đúng với mọi tình huống vô hạn** chỉ bằng vài test. Assurance cần kết hợp **design reasoning, threat modeling, test coverage, code/config review, kiểm tra population và runtime monitoring**, rồi kết luận trong phạm vi chứng cứ thực sự hỗ trợ.

## 3. Nguồn hình thành requirement

Security requirement nên bắt nguồn từ mục tiêu được xác định, không phải sao chép một danh sách control mà không hiểu ứng dụng.

### 3.1. Tập hợp nguồn đầu vào

| Nguồn | Ví dụ đầu vào | Đóng góp cho requirement |
|---|---|---|
| **Security objectives** | Không lộ dữ liệu, không sửa giao dịch trái phép | Tính chất cần bảo vệ |
| **Asset/data inventory** | Tập hóa đơn, PII, khóa, audit log | Resource và population |
| **Data classification** | Dữ liệu restricted, internal, public | Mức bảo vệ và điều kiện |
| **Threat model** | BOLA, credential stuffing, replay, injection | Misuse/negative scenarios |
| **Risk assessment** | Kịch bản, likelihood/impact, risk owner | Ưu tiên và mức nghiêm ngặt |
| **Policy/security standards** | Identity baseline, crypto baseline, logging policy | Điều kiện/constraint chung và phiên bản |
| **Legal/compliance obligations** | Nghĩa vụ được bộ phận có thẩm quyền xác nhận | Phạm vi, ngoại lệ, thời hạn, bằng chứng |
| **Business invariants** | Không tự phê duyệt khoản thanh toán do chính mình tạo | Điều kiện integrity |
| **Architecture/data flow** | API → queue → worker → DB → vendor | Các đường cần enforce và test |
| **Incident/assessment findings** | Export worker từng bỏ qua permission | Điều kiện phòng tái diễn và regression test |

### 3.2. Ví dụ risk scenario → requirement

**Kịch bản:** Người dùng tenant B biết hoặc đoán ID hóa đơn của tenant A. Gateway chỉ kiểm tra vai trò `invoice_reader`; API dùng ID này trực tiếp để truy vấn cơ sở dữ liệu. Hậu quả là lộ thông tin giao dịch của tenant A.

Từ đó:

- **Objective:** Bảo vệ dữ liệu hóa đơn giữa các tenant.
- **Risk:** Object-level authorization bị bỏ qua trên API hoặc worker.
- **Requirement:** Mỗi yêu cầu đọc/xuất hóa đơn phải kiểm tra quyền đối với **object được xác định từ nguồn có thẩm quyền**, không tin tenant do client khai.
- **Control candidates:** Policy engine, resource ownership lookup, guard trong service/data layer, token scope, audit.
- **Acceptance tests:** Tenant B không đọc/export invoice A; direct worker invocation không bypass; request từ tenant A có quyền thì đọc được theo scope.
- **Evidence:** Rule version, API/worker test, authz log và actual dữ liệu trong file/output.

### 3.3. Traceability ban đầu

~~~mermaid
flowchart TD
    A["Tài sản, business objective,<br/>data classification"] --> B["Threat scenario và risk"]
    B --> C["Security requirement<br/>ID + scope + expected behavior"]
    C --> D["Control design + owner"]
    D --> E["Implementation / configuration"]
    E --> F["Verification cases<br/>positive + negative + failure"]
    F --> G["Results + evidence<br/>release, environment, time"]
    G --> H{"Đủ căn cứ?"}
    H -- "No" --> I["Finding / exception<br/>remediation + retest"]
    I --> D
    H -- "Yes" --> J["Assurance claim<br/>with limitations"]
    J --> K["Change triggers +<br/>continuous monitoring"]
    K --> B
~~~

Đường mũi tên là **quan hệ cần duy trì**, không phải bằng chứng các bước đã hoàn thành. Một requirement chưa có test hoặc một test chưa có kết quả thực thi phải được biểu diễn là **gap**, không tự động ghi PASS.

## 4. Cấu trúc chuẩn của requirement có thể kiểm thử

### 4.1. Thành phần tối thiểu

Một mẫu câu hữu ích:

> **[Trong phạm vi/điều kiện X]**, **[hệ thống/thành phần S]** **phải [hành vi hoặc thuộc tính B]** đối với **[chủ thể, tài nguyên, hành động R]**, **[theo rule hoặc ngưỡng T được phê duyệt]**, và khi **[điều kiện lỗi/ngoại lệ F]** xảy ra thì **[safe behavior E]**. Kết quả được kiểm tra bằng **[phương pháp và bằng chứng V]**.

Không cần nhồi tất cả vào một câu dài. Tách thành **requirement statement** ngắn, **acceptance criteria** kiểm thử được và metadata tham chiếu.

| Thành phần | Câu hỏi | Minh họa |
|---|---|---|
| **ID/version** | Yêu cầu này có mã ổn định không? | `SEC-INVOICE-AUTHZ-01` / version 2 |
| **Subject/system** | Ai phải thực hiện nghĩa vụ? | Invoice API và Export Worker |
| **Scope** | Ở đâu, phiên bản và đối tượng nào? | Production, tenant-scoped invoices |
| **Trigger/condition** | Điều gì làm requirement được áp dụng? | Mỗi request `invoice.read` hoặc `invoice.export` |
| **Expected behavior** | Hệ thống phải làm gì? | Resolve owner và kiểm tra quyền trước khi trả dữ liệu |
| **Forbidden behavior** | Điều gì tuyệt đối không được xảy ra trong scope? | Không tiết lộ hóa đơn thuộc tenant khác |
| **Exceptions** | N/A hoặc ngoại lệ hợp lệ dựa trên đâu? | Shared invoice có delegation được phê duyệt |
| **Threshold/rule** | Khi nào đạt? | Policy version được duyệt; thời hạn lấy từ standard |
| **Verification method** | Test, review, inspection hay monitoring? | Cross-tenant integration + worker negative tests |
| **Evidence** | Điều gì cần ghi lại? | Test run, config, decision log, actual output |
| **Owner** | Ai chịu trách nhiệm requirement và control? | Invoice Data Owner và API Control Owner |
| **Lifecycle** | Khi nào test/retest? | Pull request, release, thay quyền/tenant mapping |

### 4.2. Điều kiện đạt phải quan sát được

Với yêu cầu `SEC-INVOICE-AUTHZ-01`, có thể định nghĩa:

- **Given:** Người dùng U đã được xác thực thuộc tenant A; invoice I thuộc tenant B.
- **When:** U đọc I bằng endpoint và qua export worker.
- **Then:** PEP từ chối theo chính sách, **không có hóa đơn I trong payload/export**, không có dữ liệu bị đọc/trả trái phép bởi đường thực thi đang kiểm tra; security audit ghi decision và request ID theo policy.

Nếu chỉ assert `HTTP 403` ở gateway mà worker vẫn tạo file chứa invoice B thì requirement **không đạt**. Kết quả cần kiểm chứng tại **điểm sử dụng dữ liệu thực**, không chỉ ở thông báo API.

### 4.3. Phạm vi và mẫu số

Cụm “mọi endpoint” chỉ kiểm tra được nếu có **population đáng tin**:

- OpenAPI routes, gateway routes và internal service routes.
- Queue consumers và asynchronous jobs.
- Admin/support endpoints.
- Data export/download paths.
- Scheduled tasks, batch và partner integrations.
- Legacy endpoints còn tồn tại.

Ví dụ: tìm thấy 80 routes cần authorization; mới có test PASS ở 60 routes. Không thể khẳng định “mọi endpoint đã được bảo vệ”. Mẫu số phải đối chiếu với **API/service inventory và runtime discovery** khi phù hợp.

### 4.4. Atomicity và decomposition

Requirement quá rộng:

> “Hệ thống phải xác thực người dùng, kiểm tra quyền, mã hóa dữ liệu, ghi audit và khôi phục sự cố.”

Nên tách thành:

- `SEC-AUTHN-01`: Xác thực danh tính và mức assurance cho hành động định trước.
- `SEC-AUTHZ-01`: Kiểm tra quyền subject–action–resource.
- `SEC-CRYPTO-01`: Bảo vệ dữ liệu nhạy cảm theo baseline mã hóa.
- `SEC-AUDIT-01`: Ghi những sự kiện bảo mật được định nghĩa và bảo vệ bằng chứng.
- `SEC-RECOVERY-01`: Khôi phục trong mục tiêu/điều kiện đã duyệt.

Tách giúp biết **yêu cầu nào PASS/FAIL**, ai sửa và một thay đổi ảnh hưởng test nào. Không tách vụn đến mức mất ý nghĩa nghiệp vụ: các yêu cầu phải vẫn liên kết được với risk scenario chung.

## 5. Chuyển câu mơ hồ thành yêu cầu xác minh được

### 5.1. Các ví dụ cải tiến

| Yêu cầu ban đầu | Vấn đề | Phiên bản có thể kiểm thử hơn |
|---|---|---|
| “Chỉ admin truy cập cấu hình” | Admin là ai, cấu hình nào? | Chỉ principal thuộc role được phê duyệt và đáp ứng điều kiện step-up mới có thể thay policy production; những principal khác bị chặn và có audit |
| “API an toàn” | Không có threat/scope | API `invoice.read` phải kiểm tra quyền sở hữu/ủy quyền đối với invoice từ nguồn có thẩm quyền trước khi trả dữ liệu |
| “Dữ liệu luôn được mã hóa” | Không rõ dữ liệu, trạng thái, key | Các dataset được phân loại restricted tại các storage đã kiểm kê phải có mã hóa-at-rest theo baseline phiên bản đã duyệt, với key ownership và kiểm thử cấu hình |
| “Log đầy đủ” | Không định nghĩa event/fields | Mỗi lần tạo/sửa policy truy cập production phải sinh audit event chứa actor, action, target, time, outcome và change ID; không chứa secret |
| “MFA cho hành động nhạy cảm” | Không rõ hành động, độ mới | Các hành động thuộc danh mục privileged operations phải kiểm tra mức assurance/freshness theo policy trước khi thực thi; thiếu điều kiện phải bị challenge/deny |
| “Xóa dữ liệu nhanh” | Mơ hồ và có retention exception | Khi yêu cầu xóa đã được phê duyệt theo decision matrix, những nguồn đủ điều kiện phải có disposition và evidence theo deadline được phê duyệt; nguồn còn mở phải được theo dõi |
| “Có thể khôi phục” | Không định nghĩa sự cố, mục tiêu | Trong drill mất primary region thuộc scope, workflow phải khôi phục dịch vụ/dữ liệu đạt RTO/RPO đã được business owner phê duyệt và giữ security invariants |
| “Không để lộ secrets” | Khó chứng minh tuyệt đối | Các pipeline/repository/image/logs thuộc scope phải qua secret-scanning controls và negative tests; phát hiện phải được xử lý theo incident workflow |

Các yêu cầu phiên bản tốt hơn vẫn phải đi kèm **mã, policy reference, acceptance criteria và bằng chứng thực tế**. Ví dụ “theo baseline” chỉ kiểm thử được nếu baseline có version, owner, cách áp dụng và tập đối tượng cụ thể.

### 5.2. “Có thể kiểm thử” không đồng nghĩa “chỉ cần một automation”

Không phải security requirement nào cũng được chứng minh bằng unit test:

- **Quản trị quyền cấp cao:** cần access review, approval và operating evidence.
- **Key ceremony/recovery:** cần quan sát quy trình, cấu hình và recovery drill.
- **Retention hoặc nghĩa vụ pháp lý:** cần decision matrix do người có thẩm quyền xác nhận và kiểm tra nguồn dữ liệu.
- **Third-party controls:** cần hợp đồng/trách nhiệm và bằng chứng trong scope nhà cung cấp.
- **Resilience/failover:** cần fault-injection và restore test, không chỉ đọc cấu hình HA.

Phương pháp thích hợp có thể là **test, analysis, inspection, demonstration, review hoặc monitoring**, nhưng phải nói rõ **kết quả quan sát nào chấp nhận được**.

## 6. Acceptance criteria: định nghĩa PASS, FAIL và UNKNOWN

### 6.1. Các hướng kiểm tra bắt buộc

| Hướng | Mục đích | Ví dụ invoice export |
|---|---|---|
| **Positive/happy path** | Không chặn sai người hợp lệ | Exporter tenant A xuất invoice được phép |
| **Negative authorization** | Chặn người không có quyền | Viewer không được export |
| **Cross-boundary** | Chặn vượt tenant/object/role | Tenant B không export invoice A |
| **Input/misuse** | Chặn giả mạo và dữ liệu không hợp lệ | Header tenant tự khai không làm đổi owner |
| **Boundary values** | Kiểm tra giới hạn được duyệt | Export trên/dưới limit, session vừa hết hạn |
| **Failure path** | Xử lý khi dependency lỗi | PDP timeout không tạo unverified permit |
| **Revocation/TOCTOU** | Quyền thay đổi khi job chờ/chạy | Export job bị recheck theo policy |
| **End-to-end effects** | Chứng minh không có side effect sai | File tải không chứa dữ liệu tenant khác |
| **Recovery/replay** | Không tái tạo hành động sai | Retry cùng job ID không tạo export trái policy |
| **Audit/evidence** | Có traceable result không tiết lộ bí mật | Decision ID, outcome, actual scope và version |

Không phải mọi yêu cầu đều cần mười loại test trên. Hãy **chọn theo risk scenario**, ghi rõ vì sao loại nào cần hoặc không áp dụng. Ví dụ quy tắc mã hóa-at-rest cần configuration inspection, data-flow review và key access tests hơn là UI test.

### 6.2. Test oracle phải độc lập và đúng lớp

**Test oracle** là căn cứ xác định kết quả mong đợi. Một lỗi thường gặp là kiểm thử so sánh hệ thống với chính output của policy engine rồi kết luận đúng:

- Engine trả **PERMIT**.
- Test kỳ vọng dựa vào **PERMIT do engine trả**.
- Test PASS dù policy cho phép sai người.

Oracle cần xuất phát từ **requirement/approved policy/business invariant**, độc lập với đường implement đang thử. Với cross-tenant test, dùng **tenant ownership được thiết lập trong fixture tin cậy** và kiểm tra thực tế rằng không có dữ liệu nào bị lộ.

### 6.3. Trạng thái xác minh

| Trạng thái | Nghĩa | Có được tính PASS? |
|---|---|---|
| **NOT_ASSESSED** | Chưa có test/review đủ | Không |
| **IN_PROGRESS** | Đang triển khai hoặc kiểm chứng | Không |
| **PASS** | Bằng chứng cho thấy tiêu chí đạt trong scope/version/kỳ xác định | Có, trong scope đó |
| **FAIL** | Có bằng chứng điều kiện không đạt | Không |
| **BLOCKED/UNKNOWN** | Thiếu môi trường, nguồn, permission, dữ liệu hoặc evidence đáng tin | Không |
| **EXCEPTION_ACTIVE** | Có quyết định ngoại lệ được phép và còn hiệu lực | Không đồng nghĩa control PASS |
| **NOT_APPLICABLE** | Có căn cứ chính thức loại khỏi phạm vi | Không tính là PASS; loại khỏi mẫu số phù hợp |
| **EXPIRED_EVIDENCE** | Test/config đã cũ so với scope hoặc release | Không tính PASS cho trạng thái hiện tại |

**Không gộp** `UNKNOWN`, `EXCEPTION_ACTIVE` và `NOT_APPLICABLE` thành “đã xử lý”. Một kết luận assurance đáng tin phải hiển thị **những nơi còn thiếu bằng chứng hoặc còn rủi ro**.

### 6.4. Tránh kiểm thử quá chặt vào chi tiết triển khai

Một requirement có thể quy định **người ngoài tenant không được truy cập** mà không bắt buộc HTTP status chính xác trong mọi trường hợp, trừ khi API contract/security policy đã chọn status để tránh enumeration. Acceptance criteria nên kiểm tra:

- Không có protected data được trả.
- Không có side effect trái phép.
- Trạng thái phản hồi và thông điệp không gây lộ thông tin theo contract.
- Audit và error handling phù hợp.

Nếu requirement chỉ test “HTTP 403” thì một ứng dụng có thể trả 403 nhưng **đã gửi dữ liệu nhạy cảm trong response body** hoặc đã tạo export file trước khi chặn. Kiểm tra kết quả **nghiệp vụ và bảo mật** quan trọng hơn so khớp một status code.

## 7. Các mẫu requirement theo nhóm security control

Những ví dụ dưới đây dùng ID và hệ thống **giả định**, được viết để minh họa kỹ thuật. Khi dùng thật cần thay bằng **baseline được phê duyệt, risk decision, owner, version và scope thực tế**.

### 7.1. Authentication và session assurance

**SEC-AUTHN-01 — Xác thực cho thao tác nhạy cảm**

> Trước khi cho phép người dùng thực hiện thao tác nằm trong danh mục `SENSITIVE_ACTIONS`, hệ thống phải xác minh session và mức assurance/freshness theo chính sách `AUTHN-BASELINE` đang có hiệu lực; nếu thiếu hoặc hết hiệu lực, thao tác phải bị chặn hoặc yêu cầu step-up theo quy trình đã định.

**Acceptance criteria:**

1. Session hợp lệ, assurance đáp ứng chính sách → thao tác tiếp tục **nếu authorization cũng cho phép**.
2. Session hết hạn hoặc signature không hợp lệ → không thực hiện thao tác.
3. Session hợp lệ nhưng chưa đạt fresh assurance → challenge/deny theo policy, không có side effect trước khi hoàn tất.
4. Khi IdP unavailable → không mặc định allow sensitive action.
5. Bằng chứng: policy version, step-up/session events, negative integration tests và actual data state.

**Không tự suy** MFA thành công thì user được làm mọi việc: AuthN và AuthZ là hai điều kiện riêng.

### 7.2. Authorization và tenant isolation

**SEC-AUTHZ-02 — Quyền trên object**

> Mỗi yêu cầu `invoice.read`, `invoice.update` và `invoice.export` qua các entry point đã kiểm kê phải xác minh quyền subject–action–resource với tenant/ownership từ nguồn authoritative; mọi yêu cầu thiếu quyền phải không truy cập hoặc thay đổi dữ liệu ngoài phạm vi được cấp.

**Acceptance criteria:**

1. Read-only user không thể update/export.
2. Tenant B không đọc, sửa hoặc export invoice tenant A.
3. Thay ID, header hoặc gọi worker trực tiếp không bypass.
4. Nếu resource ownership không tra được, không tự cấp quyền.
5. Audit outcome đủ liên kết request–decision–actual execution, không log raw PII không cần thiết.

### 7.3. Cryptography và key management

**SEC-CRYPTO-03 — Bảo vệ dataset nhạy cảm**

> Các dataset được phân loại restricted trong inventory version áp dụng phải được mã hóa khi lưu theo `APPROVED-CRYPTO-BASELINE`, với key management được phân quyền theo ứng dụng và môi trường; khi mã hóa/key service không khả dụng, hệ thống không được ghi plaintext như một đường fallback không được phê duyệt.

**Acceptance criteria:**

- Inventory có đầy đủ storage, bản sao/export/backup thuộc phạm vi hoặc trạng thái unknown được ghi.
- Kiểm tra cấu hình và test xác nhận đường ghi dùng crypto baseline.
- KMS policy chặn workload không có quyền decrypt/unwrap theo scope.
- Test KMS outage xác minh không ghi plaintext fallback.
- Evidence gồm dataset map, config, key/version, test results và change ID.

**Không đồng nhất** bật database encryption với bảo vệ mọi file xuất ra. Và **không đưa raw key vào evidence**.

### 7.4. Logging và audit integrity

**SEC-AUDIT-04 — Ghi sự kiện thay đổi chính sách**

> Mọi thay đổi effective access policy trong production thuộc phạm vi phải tạo một audit event có actor identity, thời điểm, target policy ID/version, action, outcome và change reference; event phải được chuyển tới audit store có giới hạn quyền sửa/xóa theo `AUDIT-RETENTION-POLICY`.

**Acceptance criteria:**

- Update thành công/thất bại ở đúng các đường thay policy đều tạo event phù hợp.
- Event không chứa secret, password, token hoặc dữ liệu không cần thiết.
- Người thay policy không có quyền tùy ý xóa bằng chứng.
- Audit pipeline outage kích hoạt buffer/controlled stop và alert theo policy.
- Kiểm tra event completeness với population thay đổi thực trong kỳ.

### 7.5. Secure deployment và supply-chain integrity

**SEC-DEPLOY-05 — Chỉ triển khai artifact được phê duyệt**

> Đường production deployment phải chỉ chấp nhận artifact có provenance, integrity verification và approval theo `RELEASE-SECURITY-POLICY`; artifact sai digest, không thuộc build được phép hoặc thiếu phê duyệt phải bị chặn trước khi chạy.

**Acceptance criteria:**

- Artifact hợp lệ theo chain đã kiểm tra được deploy.
- Artifact bị sửa một byte hoặc tag bị thay không được coi là hợp lệ chỉ vì tên version giống.
- Bypass qua manual deployment/internal runner bị chặn hoặc có quy trình riêng kiểm tra được.
- Log liên kết source revision, build ID, digest, policy version, approver và deployment outcome.

### 7.6. Recovery và resilience

**SEC-RECOVERY-06 — Phục hồi và bảo toàn kiểm soát**

> Khi xảy ra kịch bản mất primary region đã được xác định trong DR plan, hệ thống phải phục hồi theo RTO/RPO được business owner phê duyệt; sau failover phải tiếp tục enforce tenant authorization, bảo vệ khóa, audit và đối soát trạng thái nghiệp vụ.

**Acceptance criteria:**

- Recovery exercise có fault scenario, điều kiện kích hoạt và giới hạn được phê duyệt.
- Đo thực tế RTO và RPO so với mục tiêu đã xác nhận.
- Kiểm tra authorization/tenant isolation, key access, log pipeline và data integrity sau restore.
- Không chỉ PASS vì standby region đã khởi động; phải kiểm tra workload và dữ liệu.

### 7.7. Privacy và vòng đời dữ liệu

**SEC-PRIVACY-07 — Xử lý yêu cầu xóa trong scope**

> Với yêu cầu xóa dữ liệu đã được thẩm định theo policy/quy định thực sự áp dụng, các nguồn dữ liệu đủ điều kiện trong data inventory phải có quyết định, hành động và disposition có thể kiểm chứng; dữ liệu thuộc retention/legal hold phải được đánh giá và phản hồi phù hợp thay vì xóa hoặc từ chối tùy tiện.

**Acceptance criteria:**

- Xác minh đúng chủ thể và quyền đại diện.
- Có data inventory/lineage chỉ ra primary, exports, logs, vendor và backup cần xem xét.
- Mỗi source có status được xác minh hoặc gap/escalation rõ.
- Không đánh dấu full PASS nếu vendor connector lỗi hoặc bản sao chưa đánh giá.
- Case có decision, evidence, limitations và thông báo qua kênh phù hợp.

### 7.8. Secure configuration và drift

**SEC-CONFIG-08 — Cấu hình bảo mật không trôi khỏi baseline**

> Với những tài nguyên production thuộc inventory được phê duyệt, các security-sensitive settings phải được so sánh với baseline version hiện hành theo lịch/trigger đã duyệt; drift ngoài ngoại lệ hợp lệ phải tạo finding/alert và được theo dõi đến khi xử lý.

**Acceptance criteria:**

- Reconcile inventory production với population scanner.
- Config drift có resource ID, baseline, actual config, owner và thời điểm.
- Unknown/unscanned không tính compliant.
- Test cấu hình sai có phép gây detection và action theo policy.

### 7.9. Third-party dependencies

**SEC-VENDOR-09 — Kiểm chứng kiểm soát thuê ngoài**

> Những controls giao cho processor/provider trong scope phải có responsibility mapping và bằng chứng từ nguồn phù hợp về cách thực hiện, hiệu lực và giới hạn; phần khách hàng chịu trách nhiệm vẫn phải được kiểm tra ở cấu hình và workload thực tế.

**Acceptance criteria:**

- Có vendor/control inventory, contract boundary và owner.
- Báo cáo provider có scope, thời gian, hệ thống và limitation.
- Evidence customer-side cho policy, encryption key choice, IAM và log integrations.
- Không kết luận toàn hệ thống compliant chỉ vì provider có chứng nhận.

### 7.10. Security monitoring và response

**SEC-DETECT-10 — Phát hiện bất thường có thể hành động**

> Những tín hiệu nguy cơ đã định nghĩa trong detection catalog phải được giám sát theo nguồn và độ trễ đã phê duyệt; khi điều kiện kích hoạt đạt, hệ thống phải tạo alert chứa thông tin đủ triage và route tới owner/on-call phù hợp, kể cả ghi nhận khi nguồn telemetry bị mất.

**Acceptance criteria:**

- Synthetic event có phép gây alert trong giới hạn được phê duyệt.
- Alert có subject/resource/time/rule version và không lộ secret.
- Missing telemetry có trạng thái degraded và thông báo phù hợp.
- False positives/false negatives được review qua sampling và tuning.

Các ví dụ cho thấy **đường test và evidence phải tương ứng với mục tiêu**: requirement authorization cần test object-level; requirement backup cần restore drill; requirement audit cần population reconciliation; requirement key management cần policy và operation tests.

## 8. Biểu diễn requirement bằng YAML có cấu trúc

### 8.1. Vì sao cần metadata?

Một dòng requirement trong tài liệu Word có thể dễ hiểu nhưng khó quản lý khi hệ thống có hàng trăm requirements, nhiều releases, tenants và environments. Một bản ghi có cấu trúc giúp:

- Tra theo **ID ổn định**.
- Liên kết risk, asset, control, implementation và test.
- Ghi rõ **accepted criteria** và phương pháp xác minh.
- Phát hiện requirement không có owner/test hoặc evidence hết hiệu lực.
- Đánh giá tác động khi policy, schema, API hoặc dependency thay đổi.
- Tạo báo cáo coverage có **mẫu số giải thích được**.

### 8.2. YAML minh họa hoàn chỉnh

Đây là **mẫu học tập** cho yêu cầu `SEC-INVOICE-AUTHZ-01`, không phải schema chính thức của công cụ ALM/test management:

~~~yaml
securityRequirement:
  id: SEC-INVOICE-AUTHZ-01
  version: "2.1"
  title: "Object-level authorization for invoice access"
  category: authorization
  lifecycleStatus: approved
  language: vi

  source:
    securityObjectiveId: OBJ-TENANT-CONFIDENTIALITY
    riskScenarioIds:
      - RISK-INVOICE-BOLA-01
      - RISK-EXPORT-CONFUSED-DEPUTY
    policyReference: APP-ACCESS-CONTROL-BASELINE
    threatModelVersion: TM-INVOICE-3

  scope:
    system: Partner-Invoice-Platform
    environments:
      - production
      - staging
    affectedComponents:
      - invoice-api
      - invoice-export-worker
      - invoice-download-gateway
    protectedResourceType: invoice
    coveredActions:
      - invoice.read
      - invoice.export
    excludedWithRationale: []

  statement: >-
    Mỗi yêu cầu đọc hoặc xuất hóa đơn phải được kiểm tra quyền
    của chủ thể đối với hành động và hóa đơn cụ thể, dựa trên
    tenant/ownership lấy từ nguồn dữ liệu có thẩm quyền.
    Yêu cầu ngoài phạm vi phải bị chặn trước khi dữ liệu được tiết lộ.

  inputs:
    identitySource: VERIFIED-IDP
    resourceOwnershipSource: INVOICE-DATA-AUTHORITY
    policyVersionReference: APPROVED-AUTHZ-POLICY

  acceptanceCriteria:
    - id: AC-01
      type: positive
      expected: authorized-in-scope-read-succeeds
    - id: AC-02
      type: negative
      expected: cross-tenant-read-is-denied-without-data-disclosure
    - id: AC-03
      type: negative
      expected: viewer-role-cannot-export
    - id: AC-04
      type: bypass
      expected: direct-worker-invocation-does-not-bypass-authorization
    - id: AC-05
      type: failure
      expected: unknown-resource-owner-does-not-grant-access
    - id: AC-06
      type: revocation
      expected: delayed-export-rechecks-authority-before-execution

  owners:
    businessOwnerRole: Invoice Data Owner
    requirementOwnerRole: Security Requirements Owner
    implementationOwnerRole: Invoice Platform Team
    verificationOwnerRole: Security QA
    riskOwnerRole: Invoice Risk Owner

  controls:
    - CTRL-INVOICE-OBJECT-AUTHZ
    - CTRL-EXPORT-WORKER-AUTHZ

  verification:
    methods:
      - integration-test
      - end-to-end-negative-test
      - config-review
      - production-sample-audit
    testIds:
      - TEST-INVOICE-CROSS-TENANT
      - TEST-INVOICE-WORKER-BYPASS
      - TEST-EXPORT-ROLE-REVOCATION
    evidenceRequired:
      - policy-and-code-version
      - run-environment-and-time
      - expected-and-actual-data-state
      - decision-and-enforcement-correlation
      - reviewer-and-findings

  changeTriggers:
    - New invoice API route
    - Tenant ownership schema change
    - Export worker or policy engine change
    - Access-control incident or finding

  assessment:
    status: NOT_ASSESSED
    resultReference: null
    exceptionReference: null
    lastVerifiedRelease: null
    openFindingIds: []
~~~

**Lưu ý học thuật:**

- Giá trị `assessment.status: NOT_ASSESSED` là có chủ ý: requirement mới được **định nghĩa**, chưa thể tự đánh dấu PASS.
- `evidenceRequired` ghi **loại bằng chứng cần có**, không phải bằng chứng đã thu được.
- Các IDs phải tham chiếu tài liệu/test thực và có owner khi triển khai.
- `excludedWithRationale` chỉ là danh sách rỗng minh họa; nếu một đường legacy không được kiểm tra, phải ghi exclusion/gap có lý do và risk owner.
- Không chép danh tính khách hàng, token hoặc nội dung hóa đơn thật vào requirement metadata.

### 8.3. Lưu statement và test riêng

Không nên nhúng vài trăm dòng Gherkin hay tất cả test scripts vào một field statement. Duy trì:

1. **Requirement statement** mô tả điều hệ thống phải bảo đảm.
2. **Acceptance criteria** mô tả hành vi quan sát được.
3. **Test specification** mô tả fixtures, dữ liệu, preconditions và steps.
4. **Evidence records** mô tả run, release, environment, output và kết luận.

Tách các lớp này giúp refactor test mà không làm biến đổi mục tiêu an ninh; hoặc đổi implementation từ middleware sang service authorization mà vẫn giữ cùng điều kiện bảo vệ.

### 8.4. Versioning và stable IDs

Một ID ổn định không nên bị tái sử dụng cho mục tiêu khác:

- **Minor editorial change:** Làm rõ câu chữ, test logic có thể không thay nếu ngữ nghĩa giữ nguyên.
- **Material requirement change:** Đổi scope, security invariant, threshold hoặc exception → version mới, impact review và test cập nhật.
- **Deprecated requirement:** Giữ history, lý do thay thế, mapping tới requirement mới.
- **Split requirement:** Giữ link nguồn và migration của evidence/test IDs.
- **Deleted requirement:** Không xóa dấu vết để che gap; cần quyết định scope và lý do.

Evidence cần gắn với **version requirement và effective policy/release**, tránh nhầm test PASS cho yêu cầu cũ là bằng chứng cho yêu cầu mới.

## 9. Gherkin: biến acceptance criteria thành hành vi kiểm thử

Gherkin (*Given–When–Then*) giúp chuyển điều kiện thành ví dụ kiểm chứng rõ ràng. Nó hữu ích khi security, product và QA cùng review, nhưng **viết Gherkin không tự sinh bằng chứng**; cần thực thi với fixtures và assertions đáng tin.

### 9.1. Kịch bản cho object-level authorization

~~~gherkin
Feature: Testable security requirement for invoice authorization

  Background:
    Given tenant T1 and tenant T2 have separate invoice data
    And invoices have authoritative tenant owners

  Scenario: An authorized member reads their own tenant's invoice
    Given user U1 is authenticated and authorized for invoice.read in T1
    And invoice I1 belongs to tenant T1
    When U1 requests invoice I1
    Then the service must return only the permitted invoice information
    And the policy decision and enforcement outcome must be traceable

  Scenario: A foreign tenant invoice remains inaccessible
    Given user U2 is authenticated and authorized only for T2
    And invoice I1 belongs to tenant T1
    When U2 requests invoice I1 using its real identifier
    Then access must be denied without disclosing invoice I1 data
    And no asynchronous export job for invoice I1 may be started

  Scenario: Changing client-supplied tenant headers does not grant access
    Given user U2 has no membership in tenant T1
    When U2 sends a read request with a forged T1 tenant header
    Then the system must resolve ownership from a trusted server source
    And it must not disclose T1 invoice data

  Scenario: A viewer role cannot perform an export action
    Given user U3 can read but cannot export T1 invoices
    When U3 requests a bulk invoice export
    Then the export operation must be denied
    And no output artifact may contain the protected records

  Scenario: An unavailable ownership source cannot grant an unchecked permit
    Given ownership metadata is required to authorize invoice.read
    And the authoritative metadata service is unavailable
    When a user requests an invoice
    Then the operation must follow the approved safe-failure behavior
    And no unverified authorization may disclose protected data

  Scenario: A queued export rechecks authorization
    Given user U4 submitted a permitted export job
    And the job has not started
    And U4's export privilege has been revoked
    When the export worker begins the job
    Then the required authorization check must block unauthorized processing
    And the job's actual outcome must be auditable

  Scenario: A direct worker call cannot bypass the control
    Given worker W1 can access the invoice data store
    And caller C1 lacks valid authority for tenant T1
    When C1 invokes the export worker outside the API gateway
    Then the worker must refuse the unauthorized request
    And no T1 invoice must be exported
~~~

**Dữ liệu kiểm thử cần được kiểm soát**: tạo tenant T1/T2, invoices và principals giả định trong môi trường được phép, không lợi dụng dữ liệu khách hàng thật. Những test có tính phá hủy phải có approval và rollback.

### 9.2. Kịch bản cho audit và mã hóa

~~~gherkin
Feature: Testable security requirements for audit and cryptography

  Scenario: A policy change creates a protected audit event
    Given an authorized administrator has an approved change reference
    When the administrator updates the effective production access policy
    Then an audit record must link the actor, target, operation, time and outcome
    And the record must not contain passwords, tokens or key material
    And the record must be protected against unauthorized modification

  Scenario: Loss of audit telemetry is not silent
    Given the system must audit privileged operations
    And the audit delivery pipeline is unavailable
    When a privileged operation is attempted
    Then the system must follow the approved audit-failure policy
    And the degraded state must be detectable and recorded

  Scenario: Sensitive data is never written as an unapproved plaintext fallback
    Given a restricted dataset requires encryption at rest
    And the cryptographic service cannot complete the approved operation
    When the application attempts to store new restricted data
    Then the application must not store unapproved plaintext
    And the failure must be handled according to the documented policy
~~~

### 9.3. Giới hạn của Gherkin

Gherkin thường **không đủ một mình** để chứng minh:

- Đúng thuật toán/parameter trong cryptographic module.
- Phạm vi PEP trên **mọi entry point**.
- Retention và audit integrity trong thời gian dài.
- Khả năng khôi phục hệ thống sau mất region.
- Tuân thủ nghĩa vụ áp dụng và ngoại lệ.

Đối với những thuộc tính này, bổ sung **inspection, configuration validation, recovery drills, runtime sampling, architecture review và operational evidence**.

## 10. Chọn verification method đúng cho từng requirement

### 10.1. Ma trận phương pháp

| Phương pháp | Phù hợp với | Không nên kết luận quá mức |
|---|---|---|
| **Document/design review** | Policy, risk linkage, owner, architecture | Không chứng minh control đã triển khai |
| **Static analysis** | Patterns mã nguồn, insecure API, hard-coded secrets | Không chứng minh runtime không có bypass |
| **Unit/property-based test** | Hàm quyết định, validation, edge conditions | Không thay integration và mapping dữ liệu thật |
| **Integration test** | API–PDP–DB, KMS, queue, policy enforcement | Không đại diện mọi môi trường/release |
| **End-to-end test** | Workflow và business effect nhiều service | Có thể bỏ sót failure conditions và legacy paths |
| **Fuzzing/negative test** | Malformed input, authz boundary, unexpected values | Không chứng minh mọi đầu vào vô hạn |
| **Configuration inspection** | IAM, TLS, crypto, logging, network controls | Cấu hình đúng không bảo đảm operation đúng |
| **Fault injection** | Timeout, stale policy, queue failure, failover | Môi trường test có thể khác production |
| **Performance/load test** | Rate limit, saturation, SLO theo điều kiện tải | Không tự chứng minh confidentiality/integrity |
| **Recovery drill** | RTO/RPO, restore/key recovery, failover integrity | Một drill không bao quát mọi sự cố |
| **Production evidence sampling** | Operating effectiveness trong kỳ | Phụ thuộc population, sample và log completeness |
| **Independent audit/assessment** | Kiểm tra độc lập governance, evidence, scope | Kết luận chỉ trong scope và kỳ được đánh giá |

Một requirement có thể cần **nhiều phương pháp**. Ví dụ least privilege KMS:

1. Review quyền thiết kế và threat scenario.
2. Inspection effective IAM/KMS policies.
3. Negative test cho identity không được phép.
4. Sampling operation logs và access review.
5. Test impact khi role/key bị thu hồi.

### 10.2. Verification plan tối thiểu

| Trường | Nội dung phải ghi |
|---|---|
| Requirement ID/version | Yêu cầu nào đang được chứng minh |
| Verification owner | Ai chạy, ai review độc lập nếu cần |
| Method | Test, inspection, analysis, drill, sampling |
| Test environment | Staging/prod có phép, topology, release |
| Preconditions | Accounts, data fixtures, policy, key, network |
| Steps/input | Tác nhân, request, thời điểm, fault injection |
| Expected | Hành vi/metric theo acceptance criteria |
| Actual | Trạng thái, output, side effects và telemetry |
| Population/sample | Mẫu số endpoint/tenant/key/record/case; sample selection |
| Result | PASS/FAIL/UNKNOWN/exception với lý do |
| Evidence reference | Artifact, log, config, hash, retention |
| Limitations | Scope chưa kiểm tra hoặc kết quả không đại diện |
| Retest trigger | Khi policy/release/architecture thay đổi |

### 10.3. Negative test là yêu cầu cơ bản, không phải phụ lục tùy hứng

Với authorization, positive test chỉ chứng minh một user hợp lệ **có thể truy cập**. Để chứng minh kiểm soát ngăn truy cập trái phép cần các negative test:

- Unauthenticated user.
- Authenticated user không có role.
- User đúng role nhưng **sai tenant/object**.
- Session/token bị hết hạn hoặc sửa.
- Resource ownership không rõ.
- Direct internal API/worker.
- Permission bị revoke sau khi submit.
- Mandatory condition bị thiếu/không thể xác minh.

Tương tự, với audit requirement cần negative tests cho pipeline outage, missing event và unauthorized log deletion. Với key management cần tests cho quyền decrypt ngoài scope, export raw key không được phép và destruction khi còn dependency.

### 10.4. Kiểm tra tính đầy đủ của test population

Giả sử hệ thống có 50 endpoints, trong đó 40 qua gateway và 10 nội bộ:

- Test 40 gateway endpoints PASS.
- 10 internal endpoints chưa được đánh giá.

Kết quả là **40/50 đường đã biết có evidence PASS (80%)**, không phải 100%. Nếu còn batch jobs hoặc storage downloads chưa có trong inventory, **mẫu số 50 chưa đầy đủ**. Đây là hai vấn đề khác nhau:

1. **Coverage of known population**: Có bao nhiêu đối tượng đã biết được xác minh?
2. **Completeness of population**: Có phát hiện đủ những đối tượng trong scope hay chưa?

Một báo cáo assurance cần ghi cả hai.

## 11. Requirement traceability và ma trận bằng chứng

### 11.1. Chuỗi liên kết

~~~mermaid
flowchart LR
    R["Risk scenario<br/>RISK-INV-BOLA-01"] --> Q["Requirement<br/>SEC-AUTHZ-02"]
    Q --> C["Control<br/>object authz"]
    C --> I["Implementation<br/>API + worker + data"]
    Q --> AC["Acceptance criteria<br/>AC-01..AC-05"]
    AC --> T["Test cases<br/>positive/negative/failure"]
    I --> T
    T --> E["Execution evidence<br/>release/time/scope"]
    E --> V["Review decision<br/>PASS/FAIL/UNKNOWN"]
    V --> F["Finding / remediation<br/>retest when needed"]
    F --> I
~~~

**Traceability hai chiều** giúp:

- Từ risk tìm requirements/controls nào đang bảo vệ nó.
- Từ requirement tìm tests và evidence.
- Từ test failure tìm requirement/risk owner.
- Từ implementation change tìm requirements cần retest.
- Từ audit claim tìm đúng bằng chứng và limitations.

### 11.2. Ma trận minh họa

| Risk / objective | Requirement | Control | Test / phương pháp | Evidence | Trạng thái |
|---|---|---|---|---|---|
| Cross-tenant disclosure | `SEC-AUTHZ-02` | Object authz + worker guard | API/worker negative E2E | Policy, test, actual export | PASS nếu đủ scope |
| Privileged operation without fresh assurance | `SEC-AUTHN-01` | Reauth/step-up policy | Expired session, step-up test | AuthN events và side-effect | UNKNOWN nếu IdP evidence thiếu |
| Plaintext fallback | `SEC-CRYPTO-03` | KMS encrypt + safe failure | KMS fault injection | KMS result + storage check | PASS/FAIL theo thực tế |
| Audit loss | `SEC-AUDIT-04` | Protected pipeline + buffer | Missing telemetry simulation | Expected/received events | FAIL nếu silent drop |
| Release tampering | `SEC-DEPLOY-05` | Provenance validation | Wrong digest negative test | CI/CD gate logs | PASS nếu đúng đường |
| DR with insecure failover | `SEC-RECOVERY-06` | Recovery + security recheck | Failover drill | RTO/RPO và policy retest | UNKNOWN nếu chưa diễn tập |

Đây là **ví dụ cách trình bày**, không phải kết quả thực thi. Cột trạng thái phải được lấy từ verification runs thực tế và quyết định reviewer, không được tô PASS vì test case đã được viết.

### 11.3. Orphan requirements và orphan tests

- **Orphan requirement:** Có requirement nhưng không có control owner, test hoặc evidence.
- **Orphan test:** Có test nhưng không liên kết requirement/risk; có thể là regression test hữu ích nhưng mục tiêu không rõ.
- **Orphan control:** Đã cài một biện pháp mà không có mục tiêu/rủi ro hoặc phạm vi đánh giá.
- **Uncovered risk:** Risk được xác định nhưng không có requirement/control hợp lý hoặc quyết định risk treatment.
- **Stale evidence:** Có evidence nhưng không khớp release/policy hiện tại.

Các loại orphan cần được review để xác định **thiếu liên kết thực** hay tài liệu chỉ chưa cập nhật; không xóa test hoặc risk record chỉ để làm số liệu đẹp.

### 11.4. Tách verified, implemented và specified

Một lộ trình:

~~~text
DEFINED       Requirement đã được xác định và review
APPROVED      Có owner và acceptance criteria được chấp thuận
IMPLEMENTED   Control đã được triển khai theo scope
TESTED        Đã có test/review run
VERIFIED      Evidence đủ để kết luận requirement đạt trong scope
MONITORED     Có cơ chế theo dõi drift/failure sau release
~~~

Không phải trạng thái sau **tự suy** từ trạng thái trước. `IMPLEMENTED` không đồng nghĩa `VERIFIED`; `TESTED` không đồng nghĩa `PASS`; `VERIFIED` không đồng nghĩa **mãi mãi tuân thủ** khi release hoặc ngữ cảnh thay đổi.

## 12. Quality gates cho requirements trong vòng đời phát triển

### 12.1. Definition of Ready (DoR)

Trước khi triển khai một security requirement, yêu cầu nên có:

- Risk/objective và nguồn nghĩa vụ rõ.
- Statement không mơ hồ, có scope/action/resource.
- Acceptance criteria cho đường hợp lệ và ít nhất những failure/abuse paths cần thiết.
- Threshold/baseline reference có **owner và version**.
- Control owner, verification owner và risk owner.
- Phương pháp test/evidence và dữ liệu/môi trường cần chuẩn bị.
- Dependency, ngoại lệ/assumptions và điều kiện ngoài scope.

Nếu thiếu, yêu cầu có thể được đánh dấu **NEEDS_CLARIFICATION**, không nên để engineering đoán rồi kiểm thử theo chính giả định của mình.

### 12.2. Definition of Done (DoD)

Một requirement chỉ có thể coi là hoàn thành trong phạm vi được thỏa thuận khi:

1. Implementation đã được review và chạy ở release/environment mục tiêu.
2. Acceptance tests **đủ coverage theo risk** và không còn lỗi nghiêm trọng chưa được xử lý.
3. Config/effective policy được xác minh, không chỉ đọc template.
4. Results cho **positive/negative/failure** có expected/actual rõ.
5. Audit/evidence được lưu đúng nơi và có owner/reviewer.
6. Những exception/risk decisions được ghi đúng thẩm quyền, không gộp vào PASS.
7. Có runtime monitoring và revalidation triggers nếu requirement cần operating assurance.

Không tự động dùng cùng DoD cho mọi yêu cầu. Key recovery có thể cần drill theo chu kỳ; system design có thể yêu cầu review trước coding; data retention có thể cần sampling sau vận hành.

### 12.3. Quy trình triển khai theo release

~~~mermaid
flowchart TD
    A["Risk / obligation review"] --> B["Requirement drafting<br/>+ IDs + acceptance criteria"]
    B --> C{"Quality gate:<br/>testable và approved?"}
    C -- "No" --> D["Clarify scope/rule/owner<br/>and revise requirement"]
    D --> B
    C -- "Yes" --> E["Control implementation<br/>and code/config review"]
    E --> F["Static + unit + integration<br/>+ negative tests"]
    F --> G{"Test/evidence đạt?"}
    G -- "No" --> H["Finding + remediation<br/>or authorized exception"]
    H --> E
    G -- "Yes" --> I["Release gate / deployment"]
    I --> J["Runtime sampling + metrics<br/>and operational evidence"]
    J --> K["Assurance review +<br/>limited claim"]
    K --> L["Change/incident-driven retest"]
    L --> B
~~~

### 12.4. CI/CD automation và manual assurance

Có thể tự động:

- Kiểm tra requirement YAML bắt buộc có ID/owner/acceptance criteria.
- Phát hiện duplicate IDs, reference bị hỏng và tests thiếu mapping.
- Chạy SAST/SCA/secret scanning, unit/property tests, integration tests.
- Áp policy-as-code checks và negative authorization scenarios.
- Lưu release/config hash, test reports và artifacts.
- Gate deploy theo severity/scope được tổ chức phê duyệt.

Không nên tự động hóa một kết luận quá mức như **“mọi security requirement đều PASS vì CI pipeline xanh”**. CI thường không kiểm tra đủ vendor, production policy drift, recovery, human approval và audit completeness. Các yêu cầu cần **manual review hoặc operational sampling** phải còn trạng thái riêng.

### 12.5. Trạng thái exception không xóa nghĩa vụ

Nếu một requirement chưa đạt nhưng hệ thống vẫn cần release:

- Ghi finding, affected scope, impact và risk.
- Đưa ra compensating controls nếu phù hợp.
- Đưa ra **expiry, owner, điều kiện giám sát và remediation timeline**.
- Có người có thẩm quyền quyết định risk acceptance/exception.
- Giữ status kỹ thuật **FAIL/EXCEPTION_ACTIVE** theo mô hình đã duyệt, không đổi thành PASS.
- Retest khi hoàn tất remediation hoặc exception hết hiệu lực.

Ngoại lệ không thể hợp pháp hóa một hành vi trái nghĩa vụ bắt buộc nếu người phê duyệt không có thẩm quyền hoặc điều kiện pháp lý không cho phép.

## 13. Chỉ số coverage và cách diễn giải không sai

### 13.1. Ví dụ phân bổ 30 requirements

Giả sử trong một phạm vi đánh giá có **30 yêu cầu** được nhận diện:

- **19 PASS:** bằng chứng đủ theo tiêu chí.
- **4 FAIL:** đã phát hiện không đạt.
- **3 NOT_ASSESSED:** chưa có kết quả.
- **2 EXCEPTION_ACTIVE:** có ngoại lệ còn hiệu lực, không đồng nghĩa control đạt.
- **2 NOT_APPLICABLE:** có căn cứ loại khỏi phạm vi áp dụng.

Tổng là 19 + 4 + 3 + 2 + 2 = 30. Với mẫu số **các yêu cầu áp dụng = 30 − 2 = 28**:

~~~text
Applicable requirement count = 30 - 2 = 28
Verified PASS rate among applicable = 19 / 28 ≈ 67.86%
Known FAIL count = 4
Not assessed count = 3
Exception active count = 2
Not applicable with approved rationale = 2
~~~

**Không báo 21/28 PASS bằng cách cộng ngoại lệ**, cũng không loại bỏ 4 FAIL để làm tăng tỷ lệ. Quan trọng hơn, các con số này còn phụ thuộc **requirement inventory** có đầy đủ không và bằng chứng PASS còn phù hợp release/environment đang đánh giá hay không.

### 13.2. Các metric cần theo dõi

| Metric | Cách hiểu | Cảnh báo |
|---|---|---|
| **Requirement testability coverage** | Bao nhiêu yêu cầu có statement, acceptance criteria, method và owner? | Có trường metadata chưa chứng minh nội dung rõ |
| **Test mapping coverage** | Bao nhiêu requirements có test/evidence plan? | Test tồn tại chưa chắc đã chạy |
| **Verification coverage** | Bao nhiêu yêu cầu có kết quả đủ scope? | Đừng gộp UNKNOWN/exception |
| **Population completeness** | Inventory resources/endpoints/keys/flows đầy đủ tới đâu? | Mẫu số thường bị thiếu |
| **Negative-path coverage** | Những risk/misuse cases quan trọng được test? | Đếm test case không thay risk coverage |
| **Evidence freshness** | Test/config còn khớp release/policy? | PASS cũ có thể expired |
| **Open findings** | Yêu cầu FAIL/unknown và remediation | Ticket closed chưa chắc retest PASS |
| **Exception exposure** | Ngoại lệ theo rủi ro/expiry/owner | Ngoại lệ không phải compliance |
| **Change-triggered retest** | Release/policy change có kích hoạt tests? | Test vào ngày khác có thể không đại diện |
| **Traceability completeness** | Risk↔requirement↔control↔test↔evidence? | Liên kết không hợp lệ hoặc stale |

### 13.3. Không so sánh số PASS thô giữa các đội

Một đội có 5 requirement đơn giản và một đội có 5 requirement critical khác nhau có thể cùng 80% PASS nhưng **rủi ro còn lại rất khác**.

Để diễn giải cần:

- Phân loại requirement theo criticality/risk.
- Có mẫu số và scope tương đương.
- Tách **chất lượng evidence** và trạng thái kỹ thuật.
- Nêu các gaps trên controls trọng yếu thay vì chỉ báo tổng.
- Tránh dùng metric làm mục tiêu khiến đội **viết requirements dễ PASS** hoặc bỏ qua risk scenarios phức tạp.

## 14. Bằng chứng assurance: từ một test PASS tới kết luận có căn cứ

### 14.1. Một kết quả PASS có thể đáng tin đến đâu?

So sánh ba tình huống:

**Tình huống A — Test tồn tại:** Repository có test `testTenantAccess()` nhưng chưa xác nhận test chạy ở release nào.

**Tình huống B — Test chạy và PASS:** Pipeline cho thấy test chạy thành công trên commit X tại staging; chưa biết staging có cùng authorization policy với production không.

**Tình huống C — Bằng chứng đầy đủ hơn:** Có test run và fixture rõ, effective policy, mapping resource ownership, triển khai cùng release, kết quả actual từ API/worker, đối chiếu runtime cấu hình production, evidence review và giới hạn được ghi.

Chỉ tình huống C hỗ trợ mạnh hơn cho một claim trong scope tương ứng. Vẫn không thể khẳng định **không bao giờ có lỗi** vì chưa kiểm tra mọi thời điểm, đường truy cập hoặc biến thể tấn công.

### 14.2. Thuộc tính của bằng chứng tốt

| Thuộc tính | Câu hỏi đánh giá |
|---|---|
| **Relevant** | Có chứng minh đúng requirement và acceptance criterion không? |
| **Authentic** | Có nguồn gốc đáng tin, liên kết run/config/owner không? |
| **Complete enough** | Có đủ population, paths, trạng thái lỗi/unknown không? |
| **Timely/fresh** | Có khớp release, policy, môi trường và thời điểm đánh giá không? |
| **Accurate** | Expected/actual và method có được ghi đúng không? |
| **Reproducible** | Người kiểm tra độc lập có thể lặp lại trong điều kiện phù hợp? |
| **Protected** | Evidence có chống sửa/xóa trái phép và hạn chế dữ liệu nhạy cảm? |
| **Traceable** | Liên kết được risk, requirement, test, finding và conclusion? |
| **Scoped** | Rõ môi trường, component, tenant/sample, time window và limitations? |

Ảnh chụp screenshot UI thường **không đủ** nếu thiếu policy/config thật, actual data state, test methodology và version. Ngược lại, rất nhiều log không chọn lọc cũng không tự tạo evidence có chất lượng nếu không biết log nào chứng minh tiêu chí nào.

### 14.3. Mẫu verification record

~~~yaml
verificationRecord:
  id: VERIFY-SEC-INVOICE-AUTHZ-01-042
  requirementId: SEC-INVOICE-AUTHZ-01
  requirementVersion: "2.1"
  release: invoice-platform-2.8.1
  environment: staging-mirrors-production-authz
  executionTimeReference: RUN-2026-11-28-042
  testIds:
    - TEST-INVOICE-CROSS-TENANT
    - TEST-INVOICE-WORKER-BYPASS
  populationReference: INVENTORY-INVOICE-ENTRY-POINTS-05
  effectivePolicyReference: POLICY-INVOICE-AUTHZ-9
  testDataReference: SYNTHETIC-TENANT-FIXTURES-2
  expectedResultsReference: AC-INVOICE-AUTHZ-01-06
  actualResultsReference: TEST-RESULT-BUNDLE-042
  evidenceIntegrityReference: ARTIFACT-DIGEST-042
  findings:
    - FIND-EXPORT-WORKER-LEGACY-ACCESS
  review:
    verificationOwnerRole: Security QA
    reviewerRole: Independent Security Assurance
    status: FAIL
    reason: "Worker bypass test failed; API tests alone insufficient."
    limitations:
      - Production runtime sampling not yet performed
  retestReference: null
~~~

**Điểm đáng chú ý:** Một verification record có evidence rõ vẫn có thể có kết luận **FAIL**. Mục đích của assurance là phản ánh đúng sự thật để khắc phục, không phải tạo tỷ lệ PASS đẹp.

### 14.4. Claim–Argument–Evidence–Limitations

Mô hình lập luận:

- **Claim:** Điều muốn khẳng định, có scope rõ.
- **Argument:** Lý do kiến trúc, control và test liên quan chứng minh claim.
- **Evidence:** Bản ghi cụ thể có thể kiểm tra lại.
- **Limitations:** Những thành phần, dữ liệu, trường hợp lỗi và khoảng thời gian chưa được kiểm chứng.

Ví dụ:

> **Claim:** Trong phạm vi Partner Invoice API v2 và Export Worker bản 2.8.1 ở môi trường kiểm thử đã đối chiếu cấu hình, các request đọc/xuất hóa đơn sai tenant bị từ chối theo chính sách object-level authorization đã phê duyệt.
>
> **Argument:** Chính sách so sánh subject tenant với owner của invoice từ nguồn authoritative; PEP ở API và worker enforce quyền trước khi trả dữ liệu hoặc tạo file.
>
> **Evidence:** Approved requirement/policy versions, test fixture tenant A/B, API và worker negative test results, decision logs và kiểm tra actual output files.
>
> **Limitations:** Chưa có production sampling đầy đủ và một đường support export legacy chưa được xác minh; kết luận không bao trùm những đường này.

Một claim như “hệ thống đã tuân thủ tất cả yêu cầu bảo mật” phải có **coverage và evidence đủ rộng**, điều hiếm khi được hỗ trợ chỉ bằng một bộ test CI.

## 15. Review chất lượng requirement trước khi lập test

### 15.1. Bộ câu hỏi review

Một reviewer độc lập có thể hỏi:

1. **Vì sao tồn tại requirement?** Có liên kết mục tiêu/rủi ro/nghĩa vụ?
2. **Nghĩa vụ thuộc về thành phần nào?** Không dùng “hệ thống” chung chung nếu nhiều team cùng tham gia.
3. **Đối tượng nào thuộc phạm vi?** API, data flow, cloud account, source, tenant, key hoặc job?
4. **Khi nào áp dụng?** Trigger/event, precondition, release, environment?
5. **Hành vi có quan sát được không?** Có output, denied operation, record state, log hay metric?
6. **Mức chấp nhận lấy từ đâu?** Threshold/baseline version và người phê duyệt?
7. **Trường hợp bị cấm và dependency lỗi thế nào?** Negative/failure paths?
8. **Có trường hợp ngoại lệ không?** Ai quyết định, căn cứ, thời hạn và ảnh hưởng?
9. **Verification method đủ chưa?** Chỉ unit test hay cần end-to-end/drill/sampling?
10. **Có ai sở hữu?** Requirement owner, control owner, tester, risk owner?
11. **Có thể truy vết bằng chứng không?** Test ID, policy/config version, evidence retention?
12. **Khi hệ thống thay đổi, khi nào cần retest?** Policy, architecture, data source, vendor, incident?

Một yêu cầu có rất nhiều từ kỹ thuật vẫn có thể thiếu câu trả lời cho các điểm trên.

### 15.2. Ví dụ review sai lệch giữa hai yêu cầu

Giả sử có:

> **REQ-A:** Khi IdP không phản hồi, tất cả user đang đăng nhập phải tiếp tục truy cập mọi thao tác để duy trì availability.
>
> **REQ-B:** Mọi thay đổi người nhận thanh toán phải có authorization và step-up còn hiệu lực ở thời điểm thực hiện.

Hai yêu cầu có thể **mâu thuẫn** khi IdP lỗi. Đừng giải bằng cách ngẫu nhiên chọn một rule. Cần:

- Phân loại các hành động theo criticality.
- Xác định **degraded-mode policy** được business/security/risk owner phê duyệt.
- Định nghĩa phạm vi action có thể dùng session đã xác thực trước đó và tuổi cache tối đa.
- Với thao tác thay người nhận, **không bỏ qua điều kiện cần** khi không thể xác minh.
- Test scenario IdP outage và xác nhận không có side effect trái phép.

Như vậy có thể tách REQ-A thành các yêu cầu **read-only ít rủi ro**, **privileged state-change** và **emergency access** khác nhau. Điều này làm hệ thống có thể kiểm thử và tránh xung đột mục tiêu.

### 15.3. Ví dụ một threshold chưa có cơ sở

> “Hệ thống phải thu hồi mọi quyền truy cập trong 5 giây.”

Câu có vẻ đo được, nhưng cần hỏi:

- Tất cả quyền nào? User session, privileged roles, API tokens, database grants hay vendor access?
- Mốc bắt đầu là khi người dùng bấm revoke, khi IdP commit hay khi PEP nhận event?
- Mốc kết thúc là PEP từ chối request tiếp theo hay mọi kết nối đã đóng?
- Trường hợp offline clients, network partition và long-running jobs?
- Tại sao **5 giây** là mức chấp nhận? Theo risk, SLO, hợp đồng hay tiêu chuẩn?
- Có đủ telemetry để đo từ trigger tới actual deny không?

Viết lại:

> Đối với những actions thuộc danh mục `PRIVILEGED_ACTIONS`, sau khi revocation được xác nhận tại identity authority, các PEP thuộc scope phải từ chối những request mới sử dụng quyền đã thu hồi trong **giới hạn thời gian được phê duyệt trong `PRIVILEGE-REVOCATION-BASELINE`**; phép đo dùng timestamps đã đồng bộ và test gồm cả cache/network degradation.

Mẫu này **chưa nêu số cụ thể** cho tới khi baseline thực tế đã được thông qua. Khi có số, test plan phải khóa cách đo và error tolerance phù hợp.

## 16. Case study: từ “API bảo mật” tới tập requirement kiểm chứng được

### 16.1. Bối cảnh

Một nền tảng **Partner Invoice Platform** có:

- **Invoice API:** người dùng xem và sửa hóa đơn.
- **Export Worker:** tạo file CSV/PDF bất đồng bộ.
- **Object Storage:** lưu file xuất và cung cấp download link.
- **Identity Provider:** xác thực người dùng và tổ chức.
- **Payment Service:** truy vấn giao dịch liên quan.
- **Audit Pipeline:** ghi những thao tác xem/xuất/sửa.
- **Backup/DR:** lưu dữ liệu qua nhiều phiên bản.

Đội sản phẩm yêu cầu:

> “API phải bảo mật, chỉ người có quyền mới xem được hóa đơn, dữ liệu phải được mã hóa, log đầy đủ và hệ thống phải ổn định.”

Đây là **security objective/ý định ở mức cao**, không đủ để QA xác nhận hoàn tất.

### 16.2. Xây risk scenarios

| Risk ID | Tình huống | Tác động |
|---|---|---|
| **R-01** | User tenant B đổi invoice ID để đọc tenant A | Lộ dữ liệu |
| **R-02** | Export worker đọc mọi tenant bằng service account | Confused deputy, dữ liệu bị xuất sai |
| **R-03** | Role bị thu hồi nhưng job trong queue vẫn chạy | Stale authorization |
| **R-04** | Object storage link không kiểm tra recipient | Disclosure sau khi export |
| **R-05** | KMS lỗi khiến worker ghi file plaintext | Lộ dữ liệu khi degraded |
| **R-06** | Audit pipeline down và request vẫn xử lý không có evidence | Mất accountability |
| **R-07** | Retry export/payment tạo duplicated side effects | Sai integrity nghiệp vụ |
| **R-08** | Backup restore làm sống lại trạng thái không còn hợp lệ | Mất consistency/privacy |

### 16.3. Chuyển thành các yêu cầu có mã

| Requirement ID | Phát biểu kiểm chứng được | Verification focus |
|---|---|---|
| **INV-REQ-01** | API read/update phải kiểm tra object ownership và action permission từ nguồn tin cậy | Cross-tenant + role negative tests |
| **INV-REQ-02** | Worker chỉ được xử lý những invoice thuộc scope của request được duyệt | Direct worker call, subject/tenant binding |
| **INV-REQ-03** | Job export phải kiểm tra quyền theo policy tại điểm thực thi được xác định | Revocation + queued job test |
| **INV-REQ-04** | File export phải chỉ chứa trường và record được phép; download cần kiểm tra quyền/kênh | Output inspection, expiry và wrong recipient |
| **INV-REQ-05** | Dữ liệu restricted trên storage thuộc inventory phải được mã hóa theo baseline; không plaintext fallback | Config/key tests + KMS outage |
| **INV-REQ-06** | Các thao tác nhạy cảm cần audit đúng schema và safe failure khi pipeline lỗi | Event population + fault injection |
| **INV-REQ-07** | Retry một job/transaction theo cùng idempotency identity không tạo side effect trùng | Timeout/retry + actual DB/provider reconciliation |
| **INV-REQ-08** | Restore/failover phải giữ quyền, tính toàn vẹn và dữ liệu được phép trong RTO/RPO phê duyệt | Recovery drill + post-restore checks |

**Lưu ý:** Tên gọi “theo policy” chỉ có thể kiểm thử khi policy **được phê duyệt, có version, có nguồn dữ liệu đáng tin và có quy tắc hành xử khi lỗi**.

### 16.4. Chi tiết cho INV-REQ-02

**Statement:**

> Export Worker phải xác minh một job được tạo từ request đã được ủy quyền cho đúng chủ thể, tenant, action và resource set. Trước khi đọc dữ liệu hoặc tạo output, worker phải enforce scope của job theo chính sách đang áp dụng; yêu cầu không có quyền, sai tenant hoặc context không xác minh được phải không tạo ra file chứa dữ liệu được bảo vệ.

**Acceptance criteria:**

1. Job hợp lệ tenant A đọc đúng tập hóa đơn A theo điều kiện.
2. Caller có service token nhưng thiếu **business authorization context** không tạo được export A.
3. Job tenant B có invoice ID của A bị từ chối ở điểm worker, dù gateway đã bị bypass.
4. Quyền user bị revoke trước thời điểm execution thì worker áp hành vi theo revocation policy.
5. Nếu authorization dependency unavailable, worker không mặc định cho phép.
6. Kết quả xác minh gồm decision ID, input job scope, output file content/scope, worker version và policy version.

**Verification methods:** Integration tests cho API → queue → worker → object storage; negative direct-worker test; kiểm tra effective service-account privilege; runtime sampling có phép.

**Boundaries:** Những connector ngoại bộ hoặc legacy worker chưa nằm trong test scope phải được ghi là **gap**, không tự suy đã được bảo vệ.

### 16.5. Phát hiện thực tế trong một lần test giả định

Trong môi trường kiểm thử có dữ liệu tổng hợp:

- 10 negative API cases PASS.
- 3 worker authorization tests: 2 PASS, 1 FAIL vì worker chấp nhận job có tenant do caller tự khai.
- KMS outage test PASS: không lưu plaintext.
- Audit event schema test PASS, nhưng **audit pipeline outage** chưa được kiểm thử.
- Download link test phát hiện token không bị thu hồi sau khi quyền user bị revoke.

**Không báo toàn bộ security requirements PASS.** Cần ít nhất:

| ID | Tình trạng | Xử lý |
|---|---|---|
| INV-REQ-01 | PASS trong API scope đã test | Lưu kết quả và theo dõi các route mới |
| INV-REQ-02 | FAIL | Sửa trusted tenant context, worker authz, negative retest |
| INV-REQ-05 | PASS trong phạm vi KMS/storage thử | Đánh giá môi trường production và export khác |
| INV-REQ-06 | UNKNOWN cho outage behavior | Bổ sung fault-injection và đánh giá audit completeness |
| INV-REQ-04 | FAIL phần revocation/download | Sửa delivery authorization, thu hồi link và retest |

**Risk owner và engineering owner** cần phân tích tác động và ưu tiên remediation; không gộp các trạng thái này thành một tỷ lệ “95% secure” vô căn cứ.

### 16.6. Kết luận assurance hợp lệ

> **Claim:** Trong bản thử nghiệm Partner Invoice Platform v2 ở môi trường được chỉ định, Invoice API đã chặn các tình huống đọc chéo tenant được kiểm tra; KMS outage test đã ngăn plaintext fallback tại đường lưu dữ liệu nằm trong scope.
>
> **Argument:** Object authorization và key failure handling được triển khai và quan sát qua negative/integration tests, đối chiếu actual output.
>
> **Evidence:** Requirement versions, approved policy/config, synthetic fixtures, API negative tests, KMS fault-injection logs và storage checks.
>
> **Limitations:** Export Worker có lỗ hổng trusted tenant scope; download link revocation không đạt; audit outage chưa được xác minh; chưa đủ bằng chứng kết luận toàn hệ thống.
>
> **Follow-up:** Gán findings, owner, risk impact và retest; chỉ mở rộng claim sau khi các đường worker/download/audit được kiểm chứng.

Đây là cách sử dụng **requirement có thể kiểm thử** để biến một phát biểu chung thành **đánh giá có bằng chứng** thay vì kết luận cảm tính.

## 17. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm? | Cách khắc phục |
|---|---|---|
| Viết “secure”, “strong”, “fast” không có định nghĩa | Reviewer hiểu khác nhau, không có oracle | Xác định thuộc tính, scope, baseline, threshold |
| Sao chép control mà không có risk/objective | Kiểm tra công nghệ thay vì hiệu quả bảo vệ | Liên kết requirement tới risk/asset |
| Gộp nhiều nghĩa vụ vào một requirement | Khó quy trách nhiệm và xác định FAIL | Tách atomic requirements liên kết nhau |
| Chỉ test happy path | Không phát hiện misuse hoặc bypass | Negative, boundary, failure-path tests |
| Chỉ assert HTTP code | Có thể đã lộ dữ liệu/tạo side effect | Kiểm tra actual resource/output state |
| Test oracle dựa vào chính output implement | Policy sai vẫn PASS | Oracle từ approved requirement/business invariant |
| “Mọi endpoint” nhưng inventory không đủ | Mẫu số coverage đẹp giả | Endpoint/worker/storage discovery và reconciliation |
| Mã hóa-at-rest được hiểu là bảo vệ mọi bản sao | Export/log/cache có thể plaintext | Data inventory và scope từng copy |
| Baseline không có version hoặc owner | “Đáp ứng tiêu chuẩn” không xác minh được | Policy reference, approval, version |
| Số lượng ngưỡng được bịa để có vẻ SMART | Test đo được nhưng không phù hợp risk | Risk-based threshold approval |
| Tập trung implementation detail thay mục tiêu | Khó đổi thiết kế, quên security property | Behavioral outcome + constraint khi bắt buộc |
| Không mô tả behavior khi dependency lỗi | Fail-open, mất audit hoặc plaintext fallback | Failure criteria và safe behavior |
| Không có requirement owner | Gap không ai chịu trách nhiệm | Gán business/control/verification/risk owner |
| Đánh dấu PASS ngay khi code merge | Chưa có runtime evidence | Test/effective config và review |
| Cộng exception vào PASS | Che rủi ro còn tồn tại | Separate statuses, expiry và risk acceptance |
| Không lưu evidence version/environment | PASS cũ không áp cho release mới | Release/policy/requirement version binding |
| Log thật chứa PII hoặc secrets | Evidence trở thành rò rỉ | Data minimization, access control và references |
| Coi provider certification là đủ | Không chứng minh customer-side configuration | Shared-responsibility assessment |
| Đổi requirement nhưng giữ test cũ | Test không còn đúng expected behavior | Impact analysis, update oracle và retest |
| Chỉ đo percent PASS | Che severity và critical gaps | Risk-weighted analysis kèm findings |
| Đóng finding mà không retest | Sửa trên giấy không chứng minh hiệu quả | Actual retest và evidence |

## 18. Bài tập thực hành

### Bài tập 1 — Sửa các câu mơ hồ

Bạn nhận được năm câu:

- “Ứng dụng phải bảo mật dữ liệu.”
- “Admin phải dùng xác thực mạnh.”
- “Các API phải có phân quyền đầy đủ.”
- “Hệ thống phải phục hồi nhanh.”
- “Ghi log mọi thứ quan trọng.”

**Yêu cầu:** Viết lại mỗi câu thành một hoặc nhiều security requirements có **scope, trigger, subject/resource/action, expected outcome, baseline/threshold reference và owner**. Đề xuất ít nhất một positive test, một negative/failure test khi phù hợp và loại evidence cần có. Những ngưỡng chưa được phê duyệt phải ghi là **cần quyết định**, không tự sáng tác.

### Bài tập 2 — Từ threat model tới requirements

Một hệ thống bán vé có Account API, Payment API, Reservation DB, Redis, webhook và bên gửi email. Threat model phát hiện **IDOR, replay payment webhook, stale role và log thiếu**.

**Yêu cầu:** Lập bảng **risk scenario → security objective → atomic requirement → control owner → test → evidence** cho bốn nguy cơ trên. Chỉ ra ít nhất hai trust boundaries, một failure path và một trường hợp phải đối soát trạng thái nghiệp vụ.

### Bài tập 3 — Phân biệt requirement và implementation

Đội phát triển viết:

> “Phải dùng một library X để kiểm tra JWT trước gateway, dùng WAF Y, bật cloud KMS Z và lưu log 90 ngày.”

**Yêu cầu:** Phân loại từng câu là **technology constraint, control decision hay security property**. Chuyển thành những yêu cầu có thể kiểm thử về token validation, object authorization, mã hóa/key access và audit retention. Nêu điều kiện khi việc quy định chính xác công nghệ là bắt buộc hợp lệ.

### Bài tập 4 — Viết Gherkin với oracle độc lập

Một user có quyền đọc invoice tenant A nhưng không có quyền export. API trả 403 cho export, song worker vẫn tạo một file CSV.

**Yêu cầu:** Viết ba scenario Gherkin cho **positive read, negative export và direct worker bypass**. Từng scenario phải xác minh không chỉ response code mà còn **file/output/data state**. Mô tả fixtures để oracle không phụ thuộc vào policy engine trả về gì.

### Bài tập 5 — Lập verification plan cho key management

Một dataset restricted dùng envelope encryption, KEK trong cloud KMS, DEKs ở object metadata và backup. Nhóm chỉ cung cấp screenshot “Encryption enabled”.

**Yêu cầu:** Viết requirement có thể test cho **encryption coverage, KMS least privilege, key rotation dependency và no-plaintext fallback**, cùng phương pháp config inspection, negative KMS test, dependency scan và recovery drill. Viết giới hạn của screenshot.

### Bài tập 6 — Tính coverage không gian dối

Trong kỳ có 30 requirements: 19 PASS, 4 FAIL, 3 NOT_ASSESSED, 2 EXCEPTION_ACTIVE và 2 NOT_APPLICABLE có căn cứ. Một legacy service chưa vào inventory.

**Yêu cầu:** Tính tỷ lệ PASS trên số requirement áp dụng, nêu các nhóm chưa đạt và giải thích tại sao kết quả **không đại diện đầy đủ** khi service legacy chưa được kiểm kê. Đề xuất cách báo cáo theo risk criticality và evidence freshness.

### Bài tập 7 — Phân tích mâu thuẫn và degraded behavior

Requirement A yêu cầu “mọi request tiếp tục hoạt động khi IdP không khả dụng”; requirement B yêu cầu “thao tác thay người nhận thanh toán phải được xác thực và ủy quyền còn hiệu lực”.

**Yêu cầu:** Chỉ ra mâu thuẫn, xây ma trận **public read, authenticated read, sensitive state change, emergency admin access** với hành vi fail-open/closed được đánh giá theo risk. Định nghĩa test khi IdP timeout, token hết hạn và quyền đã bị thu hồi.

### Bài tập 8 — Review và kết luận assurance

Một nhóm đã có 12 requirements, 12 test script, dashboard “100% tests exist”. Tuy nhiên chỉ 7 test đã chạy trên staging, 2 test FAIL, 3 chưa chạy và một API mới xuất hiện sau lần scan.

**Yêu cầu:** Viết **Claim–Argument–Evidence–Limitations** đúng với dữ liệu hiện có, không suy “100% compliant”. Xác định những thông tin còn cần về **test results, population, release/policy version, expected/actual, PEP paths và owners**. Lập danh sách findings và retest triggers.

### Bài tập 9 — Thiết kế requirement review gate

Team product thường chuyển câu “tăng bảo mật login” thẳng cho developer, không có security reviewer hay definition of ready.

**Yêu cầu:** Thiết kế một checklist review/approval trước implementation, một pipeline kiểm tra requirement metadata/test mapping và tiêu chí khi nào có thể release. Phân biệt phần có thể tự động với **quyết định risk/requirement validity** cần người có thẩm quyền.

### Bài tập 10 — Chuyển đổi một requirement đã thay đổi

Phiên bản 1 của yêu cầu chỉ bảo vệ `invoice.read`; phiên bản 2 bổ sung `invoice.export`, async worker và download gateway. Test cũ cho `invoice.read` vẫn PASS.

**Yêu cầu:** Thiết kế version/impact analysis, liệt kê tests/evidence mới, cách đánh dấu **expired hoặc partial evidence** và cách không để kết quả PASS của version 1 được hiểu thành PASS version 2.

## 19. Checklist đánh giá “Requirement có thể kiểm thử”

### 19.1. Review trước khi triển khai

- **Nguồn gốc:** Requirement có link tới security objective, risk scenario hoặc nghĩa vụ đã xác định?
- **Mục tiêu:** Có rõ đang bảo vệ confidentiality, integrity, availability, accountability hay thuộc tính nào?
- **Scope:** Hệ thống, môi trường, tenant, resource, action, dữ liệu và luồng liên quan đã được định danh?
- **Chủ thể:** Principal/workload/service cần làm gì, được phép hoặc bị cấm?
- **Trigger:** Điều kiện nào làm requirement áp dụng; có boundary cases?
- **Quan sát được:** Có kết quả về response, state, event, time hoặc metric mà tester có thể kiểm tra?
- **Mức chấp nhận:** Threshold/cryptographic baseline/deadline lấy từ nguồn có phê duyệt và version?
- **Ngôn ngữ:** Có loại bỏ “mạnh”, “tốt”, “nhanh”, “đầy đủ” không định nghĩa?
- **Atomicity:** Có tách các nghĩa vụ độc lập mà vẫn giữ liên kết mục tiêu?
- **Tính đúng:** Có xung đột với requirement khác, business invariant hoặc nghĩa vụ bắt buộc không?
- **Ownership:** Có requirement owner, control owner, verification owner và risk owner?
- **Exceptions:** Có điều kiện N/A, ngoại lệ và authority rõ, không tự suy?

### 19.2. Review verification plan và evidence

- **Acceptance criteria:** Có positive, negative, misuse và failure-path criteria phù hợp risk?
- **Oracle:** Expected behavior từ approved requirement, độc lập với implementation?
- **Method:** Chọn unit/integration/E2E/static/config/drill/sampling đúng loại thuộc tính?
- **Population:** Biết đầy đủ API, worker, object store, tenant, key, vendor hoặc case thuộc scope?
- **Test fixtures:** Dữ liệu kiểm thử có hợp pháp/an toàn, tách tenant và đủ edge cases?
- **Execution:** Có actual test result, environment, release và policy version?
- **Side effects:** Đã kiểm tra dữ liệu thực, job/file/DB state và log, không chỉ HTTP code?
- **Enforcement:** Có kiểm tra đường bypass và các control ở data plane?
- **Failure behavior:** Khi nguồn phụ thuộc lỗi, có không tạo allow/plaintext/duplicate/silent audit gap?
- **Evidence quality:** Log/config/run có provenance, integrity, freshness và được bảo vệ?
- **Negative outcomes:** FAIL, UNKNOWN, N/A và EXCEPTION được phân biệt với PASS?
- **Traceability:** Risk → requirement → control → test → evidence → finding/retest được liên kết?
- **Reviewer:** Có người xem xét độc lập theo mức rủi ro và lưu kết luận có giới hạn?

### 19.3. Review trong vận hành và khi thay đổi

- **Drift:** Có so effective policy/config/runtime với baseline đang áp dụng?
- **Triggers:** Thêm endpoint, đổi data flow, IdP, KMS, vendor, policy hoặc incident có kích hoạt reassessment?
- **Retest:** Sau remediation hoặc release mới, kết quả có được cập nhật?
- **Metrics:** Có mẫu số yêu cầu và resource population đủ, báo coverage trung thực?
- **Findings:** Những yêu cầu chưa đạt có owner, risk, hạn xử lý và evidence đóng?
- **Exceptions:** Ngoại lệ có thẩm quyền, phạm vi, expiry và monitoring; không tính là PASS?
- **Claims:** Kết luận assurance có scope, time window, assumptions và limitations?
- **Continuous assurance:** Có chương trình theo dõi lâu dài thay vì chỉ có checklist trước go-live?

**Điều cần ghi nhớ:** Một **requirement có thể kiểm thử** không phải câu có nhiều từ kỹ thuật hoặc một con số bất kỳ. Nó là cam kết bảo mật **đúng mục tiêu và có căn cứ**, mô tả rõ **ai, làm gì, trên tài nguyên nào, khi nào, theo điều kiện nào và kết quả nào chấp nhận được**; được liên kết với **control, phương pháp kiểm tra, bằng chứng, owner và hành động khi FAIL/UNKNOWN**. Trong **security assurance**, điều quan trọng không phải làm sao cho tất cả các ô chuyển sang PASS mà là **biết chắc điều gì được chứng minh, phần nào chưa thể kết luận, rủi ro còn lại do ai xử lý và khi nào phải kiểm tra lại**.
