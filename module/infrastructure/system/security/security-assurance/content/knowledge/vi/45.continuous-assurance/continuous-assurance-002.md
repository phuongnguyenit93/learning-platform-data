# Kiểm soát liên tục (Continuous Controls): duy trì hiệu lực bảo mật bằng bằng chứng theo thời gian

**Kiểm soát liên tục (continuous controls)** là cách thiết kế, vận hành và đánh giá các **security controls** để những hành vi cần bảo vệ được duy trì trong suốt vòng đời của hệ thống, thay vì chỉ đạt ở một cuộc kiểm tra hoặc tại ngày phát hành. Tùy từng mục tiêu, điều này có thể bao gồm **kiểm soát ngăn chặn tự động, giám sát trạng thái và sự kiện, kiểm thử lặp lại, phát hiện sai lệch, xử lý có kiểm soát và lưu bằng chứng theo thời gian**.

Trong chương **Continuous assurance** của module **SECURITY_SECURITY_ASSURANCE**, trọng tâm không chỉ là làm hệ thống “có nhiều dashboard”, mà là **xây dựng cách đánh giá có bằng chứng rằng hệ thống liên tục đáp ứng các mục tiêu bảo mật đã chọn**: từ phân tích rủi ro và yêu cầu, triển khai security controls, kiểm thử, audit tới khắc phục phát hiện. Một kết luận assurance tốt cần biết **control nào đang được kiểm tra, áp dụng cho tập tài sản nào, trong khoảng thời gian nào, nguồn dữ liệu có đầy đủ không, ai xử lý ngoại lệ và điều gì vẫn chưa được chứng minh**.

Ví dụ, việc hệ thống cloud được audit là “không có bucket public” vào ngày đầu tháng là một trạng thái có ích. Nhưng nếu một người triển khai vô tình đổi bucket policy vào ngày thứ năm, tổ chức cần biết **cấu hình bị thay đổi khi nào, ngăn chặn hay phát hiện được không, mức độ phơi nhiễm kéo dài bao lâu, đã xử lý ra sao và có bằng chứng gì cho phần thời gian đó**. Đây là vấn đề cốt lõi của kiểm soát liên tục.

> **Câu hỏi xuyên suốt:** “Security control có còn hiệu lực trên toàn bộ phạm vi cần bảo vệ khi hệ thống, người dùng và mối đe dọa thay đổi không, và chúng ta chứng minh được điều đó bằng dữ liệu gì?”

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **continuous controls**, **continuous monitoring**, **continuous testing**, **continuous assurance** và **đánh giá tại một thời điểm**.
2. Xác định control objectives, tiêu chí đáp ứng, tập đối tượng chịu kiểm soát, thời gian đánh giá và mức rủi ro.
3. Thiết kế các kiểm soát **preventive**, **detective** và **corrective** phối hợp mà không tạo điểm mù.
4. Đề xuất cách kết hợp **policy/configuration as code**, nguồn trạng thái runtime, audit events, kiểm thử và evidence pipeline.
5. Đánh giá **coverage, freshness, completeness, reliability và integrity** của tín hiệu; không đồng nhất “không phát hiện vi phạm” với “đã chứng minh tuân thủ”.
6. Thiết kế xử lý **configuration drift**, phát hiện sai lệch, incident, exception, remediation và retest.
7. Xây dựng metrics, cảnh báo, ngưỡng, ownership và cơ chế xác minh hiệu quả vận hành.
8. Phân tích một ví dụ nhiều tài khoản cloud về MFA đặc quyền và bảo vệ storage để rút ra kết luận có giới hạn, có bằng chứng.

---

## 2. Kiểm soát liên tục là gì?

Một security control là biện pháp được thiết kế nhằm ngăn chặn, phát hiện, giảm thiểu hoặc khắc phục một rủi ro đối với mục tiêu bảo mật. Control có thể là chính sách, quy trình con người, kỹ thuật hoặc kết hợp.

**“Liên tục” không nhất thiết có nghĩa mọi kiểm soát đều chạy từng mili giây.** Nó có nghĩa tổ chức thiết kế cơ chế duy trì và đánh giá control **phù hợp với mức rủi ro và tốc độ thay đổi của đối tượng**.

Ví dụ:

- **Enforcement theo từng yêu cầu:** API thực thi kiểm tra authorization trước mỗi lần đọc một bản ghi.
- **Kiểm tra theo sự kiện:** khi role production thay đổi, hệ thống xác minh quyền không vượt baseline và tạo sự kiện cho Security Operations.
- **Kiểm tra định kỳ với thời gian hợp lý:** mỗi 15 phút so sánh cloud configuration với baseline, có phát hiện đột xuất qua change event.
- **Control theo chu kỳ nghiệp vụ:** rà soát quyền hàng quý được kiểm tra theo lịch bắt buộc, với bằng chứng các quyết định và hành động thu hồi.
- **Diễn tập phục hồi:** backup được tạo thường xuyên, nhưng hiệu lực restore được xác minh qua các lần thử theo mức quan trọng của dịch vụ.

Cần tránh gọi tất cả những cách trên là **real-time protection**. Kiểm tra định kỳ luôn có cửa sổ sai lệch giữa hai lần đo; kiểm tra theo sự kiện có thể mất sự kiện; còn một review định kỳ có thể chưa tới hạn ở ngày đang quan sát.

### 2.1. Phân biệt các khái niệm gần nhau

| Khái niệm | Trả lời câu hỏi | Ví dụ | Giới hạn |
|---|---|---|---|
| **Continuous control operation** | Biện pháp bảo vệ có được thực thi trong hoạt động thông thường? | API kiểm tra quyền mỗi request | Chưa tự chứng minh mọi đường truy cập đều đi qua control |
| **Continuous monitoring** | Hệ thống có phát hiện và đo được trạng thái/sự kiện quan trọng? | Theo dõi bucket policy và IAM changes | Có tín hiệu chưa đồng nghĩa có hành động |
| **Continuous control testing** | Có phép thử lặp lại về thiết kế/thực thi/hiệu lực control? | Test định kỳ đường cấp admin, test synthetic log | Test chỉ bao phủ kịch bản đã định |
| **Continuous assurance** | Có chuỗi lập luận và bằng chứng đủ hỗ trợ kết luận bảo mật theo thời gian? | Control mapping, evidence, exception, retest và review | Không tự bảo đảm mọi mối đe dọa ngoài phạm vi |
| **Continuous auditing** | Audit dùng dữ liệu/phép kiểm tra thường xuyên để đánh giá tiêu chí? | Đối chiếu các thay đổi privileged access | Không thay thế độc lập đánh giá và quyền kết luận |
| **Point-in-time assessment** | Tại mốc T control có đáp ứng tiêu chí không? | Snapshot cấu hình ngày T | Không bảo đảm trạng thái giữa hoặc sau các mốc |

Control liên tục có thể là một thành phần của assurance liên tục, nhưng **hai khái niệm không đồng nhất**. Một SIEM luôn nhận log vẫn chưa chứng minh rằng mọi nguồn bắt buộc đã gửi log đầy đủ, phân tích phát hiện được sự kiện cần thiết và đội trực có phản ứng hiệu quả.

## 3. Vì sao kiểm tra tại một thời điểm không đủ?

Hệ thống thay đổi liên tục: triển khai phiên bản, tài khoản mới, thay đổi quyền, feature flag, tài sản cloud tự tạo, khóa được luân chuyển, network policy thay đổi và dependency được cập nhật. Một kết quả PASS ở thời điểm T có thể không còn phản ánh môi trường tại T+1.

### 3.1. Các tình huống làm control suy giảm

1. **Configuration drift:** IaC định nghĩa storage private, nhưng một thao tác thủ công tạo policy public ngoài pipeline.
2. **Identity drift:** tài khoản có đặc quyền được cấp qua kênh khẩn cấp và không chịu chính sách MFA thông thường.
3. **Asset drift:** một cloud account mới chưa đưa vào inventory, do đó không được kiểm tra baseline.
4. **Evidence drift:** kiểm thử và báo cáo đã lỗi thời sau khi đổi IdP, policy hoặc release.
5. **Monitoring gap:** agent hoặc pipeline ngừng gửi log nhưng dashboard vẫn hiển thị dữ liệu cũ.
6. **Process drift:** review quyền có biên bản nhưng hành động thu hồi quyền bị trì hoãn.
7. **Threat drift:** một cách khai thác mới làm suy yếu hiệu quả của biện pháp trước đây.
8. **Dependency drift:** thay cấu hình KMS hoặc nhà cung cấp khiến backup có thể không khôi phục được.

Các tình huống này không thể xử lý bằng một checklist PASS duy nhất. Cần cơ chế theo dõi biến động, xác nhận nguồn dữ liệu đang hoạt động và đánh giá lại khi điều kiện nền thay đổi.

### 3.2. Ví dụ về cửa sổ phơi nhiễm

Giả sử storage trở thành public lúc 10:01, công cụ quét trạng thái mỗi 60 phút và lần quét tiếp theo là 11:00. Nếu công cụ hoạt động đầy đủ, lỗi có thể tồn tại gần 59 phút trước khi được phát hiện. Nếu hàng đợi cảnh báo và quy trình xác minh thêm 20 phút, khoảng thời gian phơi nhiễm còn kéo dài.

Việc rút ngắn lịch quét có thể cải thiện, nhưng **không tự loại bỏ** nguy cơ thiếu nguồn, lỗi API, false negative hoặc chậm khắc phục. Với control có hậu quả lớn, có thể cần **ngăn chặn ngay tại nơi thực thi chính sách** và dùng monitoring làm lớp phát hiện bổ sung.

## 4. Kiểm soát ngăn chặn, phát hiện và khắc phục

Một kiến trúc hữu ích kết hợp ba nhóm control.

| Nhóm | Mục đích | Ví dụ | Evidence |
|---|---|---|---|
| **Preventive** | Không cho hành vi/trạng thái trái chính sách xuất hiện | Authorization tại API; IAM policy least privilege; policy gate trong triển khai | Test bị từ chối, policy evaluation, cấu hình thực tế |
| **Detective** | Phát hiện sai lệch hoặc dấu hiệu bất lợi đã xảy ra | Cloud configuration drift, SIEM rule, log thiếu nguồn | Sự kiện, trạng thái check, alert có timestamp |
| **Corrective** | Đưa hệ thống về trạng thái chấp nhận được, xử lý nguyên nhân | Rollback policy sai, rotate secret, thu hồi quyền, remediation workflow | Change record, retest, reviewer sign-off |

Các nhóm không thay thế nhau. **Cảnh báo** về bucket public không ngăn dữ liệu bị đọc trong khoảng phơi nhiễm; **chính sách chặn tạo bucket public** giảm khả năng lỗi, nhưng vẫn cần monitoring nếu có đường quản trị hoặc hệ thống ngoài pipeline.

### 4.1. Control tự động, bán tự động và thủ công

- **Tự động đầy đủ:** phù hợp với điều kiện có logic rõ, phạm vi đầy đủ và hành động an toàn, ví dụ từ chối một IaC configuration không đáp ứng encryption baseline.
- **Bán tự động:** hệ thống phát hiện rủi ro, tạo ticket và yêu cầu owner xác nhận trước khi sửa production.
- **Thủ công được kích hoạt theo điều kiện:** phê duyệt access exception, điều tra threat mới hoặc xác nhận dữ liệu cần khôi phục.

Tự động hóa không phải mục tiêu tự thân. Một bot thu hồi quyền quản trị quá rộng có thể chặn đường khắc phục sự cố hoặc làm thất bại DR. Cần đánh giá **rủi ro của hành động sửa** và có cơ chế giám sát phù hợp.

## 5. Kiến trúc kiểm soát liên tục trong Security Assurance

Một kiến trúc tham khảo có thể tổ chức như sau:

~~~mermaid
flowchart TD
    A["Security objectives, risk, policy và control criteria"] --> B["Control specification + asset population"]
    B --> C["Preventive enforcement / policy-as-code"]
    B --> D["Continuous state & event collection"]
    C --> E["Deployment / runtime systems"]
    E --> D
    D --> F["Coverage, freshness & data-quality checks"]
    F --> G["Control evaluator / tests"]
    G --> H{"Control evidence đủ và đạt?"}
    H -- "PASS" --> I["Evidence ledger + ongoing review"]
    H -- "FAIL" --> J["Finding / incident + containment"]
    H -- "UNKNOWN" --> K["Evidence gap + investigate"]
    J --> L["CAP / risk exception / remediation"]
    K --> L
    L --> M["Retest + independent verification"]
    M --> G
    I --> N["Assurance case / risk dashboard / audit"]
    N --> B
~~~

Các thành phần có trách nhiệm tách biệt:

1. **Control catalog:** ánh xạ mục tiêu bảo mật tới control, tiêu chí và owner.
2. **Population inventory:** biết chính xác những tài sản/danh tính/luồng nào phải chịu kiểm soát.
3. **Enforcement:** áp dụng policy ở nơi có quyền quyết định, ví dụ API backend, cloud policy, IAM engine, CI/CD admission.
4. **Telemetry/collection:** lấy trạng thái thực tế và các sự kiện thay đổi, bảo đảm nguồn hoạt động.
5. **Evaluator:** kiểm tra điều kiện và đưa ra kết quả theo phạm vi.
6. **Evidence ledger:** lưu nguồn, timestamp, phiên bản, truy vấn, kết quả, ngoại lệ, người kiểm tra.
7. **Response workflow:** cảnh báo, phân loại, containment, CAP, risk decision và retest.
8. **Review/governance:** xem tính đúng của logic, độ đủ dữ liệu, sự độc lập và độ tin cậy của kết luận.

**Chỉ có dòng dữ liệu từ cloud API hoặc dashboard là chưa đủ.** Nếu nguồn biến mất, hệ thống cần có khả năng ghi **UNKNOWN / NO EVIDENCE** thay vì mặc định PASS.

## 6. Bắt đầu từ mục tiêu bảo mật và control objective

Không nên triển khai công cụ monitoring rồi mới tìm lý do để dùng nó. Trình tự hợp lý:

**Risk → Security objective → Control objective → Acceptance criteria → Population → Enforcement/monitoring/test → Evidence → Decision.**

Ví dụ:

| Risk | Mục tiêu | Control objective | Kiểm tra liên tục |
|---|---|---|---|
| Chiếm quyền admin | Chỉ principal được phép và được xác thực mạnh có quyền đặc biệt | Đường login tương tác thuộc phạm vi bắt buộc MFA; quyền có phê duyệt | Policy checks, IAM events, synthetic tests, access review |
| Lộ dữ liệu qua storage | Storage nhạy cảm không truy cập công khai trái phép | Public access bị chặn với resource thuộc lớp dữ liệu đã định | Preventive policy, config inventory và event-driven drift checks |
| Mất log | Có audit trail cho hành động đặc quyền | Nguồn bắt buộc gửi đủ event trong kỳ và alert mất nguồn | Synthetic event, source-to-SIEM comparison, heartbeat |
| Secret bị lộ | Chỉ workload được phép dùng secret, rotate khi cần | Secret không public, không bị hardcode theo phạm vi phát hiện | Repo scanning, secret inventory, runtime access logs |
| Lỗ hổng kéo dài | Thời gian xử lý vulnerability tương xứng rủi ro | Finding được triage, vá hoặc có quyết định rủi ro đúng thẩm quyền | Scan coverage, asset mapping, SLA checks, retest |
| Không restore được | Backup phục hồi được theo mục tiêu đã duyệt | Backup/restore đạt kiểm tra integrity và khả năng khôi phục | Job monitoring, restore drills, RTO/RPO evidence |
| Thay đổi không được duyệt | Bảo vệ baseline production | Change có approval và policy gate theo loại thay đổi | Deployment events, PR/change mapping, drift detection |

Với từng control, cần biết **tiêu chí nào là bắt buộc** và **điểm nào chỉ là tín hiệu hỗ trợ**. Ví dụ “đã nhận 1 triệu log” có thể chỉ là chỉ số volume, không chứng minh sự kiện quản trị bắt buộc đã được ghi đúng.

## 7. Thiết kế một control specification có thể kiểm chứng

Một control muốn đánh giá liên tục phải được diễn đạt rõ:

| Thuộc tính | Cần xác định |
|---|---|
| **Control ID & version** | Mã, owner, nguồn policy/security requirement và phiên bản |
| **Objective** | Rủi ro hoặc thuộc tính bảo mật cần xử lý |
| **Population** | Toàn bộ asset/account/identity/flow bắt buộc phải kiểm tra |
| **Predicate/criteria** | Điều kiện đúng/sai và các trường hợp biên |
| **Frequency/trigger** | Per-request, event-driven, theo lịch, theo release hay theo chu kỳ nghiệp vụ |
| **Observation window** | Tình trạng tại mốc, trong giờ/ngày/quý, tần suất phải duy trì |
| **Evidence source** | API, runtime, log, hệ thống approval, test, scan |
| **Data quality gate** | Completeness, timeliness, integrity và khả năng đối chiếu |
| **Exceptions** | Ngoại lệ đã duyệt, phạm vi, hạn, compensating controls |
| **Decision rule** | PASS, FAIL, UNKNOWN, NOT APPLICABLE theo tiêu chí |
| **Response** | Owner, severity, SLA, incident, CAP, retest |
| **Reviewer/audit trail** | Ai phê duyệt logic, ai kiểm tra bằng chứng và quyết định |
| **Re-evaluation trigger** | Thay policy, thay tài sản, threat mới, finding, incident hoặc evidence lỗi thời |

Một tiêu chí như “MFA phải an toàn” chưa đủ. Cần xác định **loại principal**, **đường đăng nhập**, **hình thức xác thực chấp nhận**, **account/region**, **ngoại lệ** và phương pháp kiểm tra. Đừng giả định mọi service principal dùng cùng cơ chế MFA dành cho con người.

### 7.1. Viết ba trạng thái tối thiểu

Trong vận hành liên tục, ít nhất nên phân biệt:

- **PASS:** dữ liệu đủ, phép kiểm tra áp dụng đúng scope, điều kiện được chứng minh đạt.
- **FAIL:** có bằng chứng tin cậy cho thấy điều kiện bắt buộc bị vi phạm.
- **UNKNOWN / NOT DEMONSTRATED:** không đủ evidence để quyết định; ví dụ API collector lỗi hoặc inventory chưa đầy đủ.

Có thể bổ sung **EXCEPTED** cho sai khác nằm trong ngoại lệ hợp lệ, hoặc **NOT APPLICABLE** khi yêu cầu thực sự không áp dụng. Nhưng **EXCEPTED không tương đương PASS về kỹ thuật**; phần sai khác vẫn cần trình bày rõ trong assurance và risk register.

## 8. Chọn nhịp kiểm tra dựa trên rủi ro

Một câu “scan mỗi ngày” không đủ cho mọi control. Cần chọn lịch theo **tốc độ thay đổi, thời gian có thể gây thiệt hại và chi phí phát hiện/khắc phục**.

| Loại control | Cơ chế giám sát phù hợp | Điều cần lưu ý |
|---|---|---|
| API authorization | Enforcement per request + test định kỳ/có thay đổi | Kiểm thử phải bao phủ route và role trọng yếu |
| IAM privilege changes | Event-driven + reconciliation định kỳ | Event có thể mất; reconciliation giúp kiểm tra |
| Cloud public exposure | Preventive policy + config event + scan định kỳ | Scan không thay thế enforcement tại thời điểm thay đổi |
| Log pipeline health | Heartbeat, synthetic event, source-to-destination checks | Dashboard ít event có thể là bình thường hoặc mất nguồn |
| Vulnerability backlog | Scan theo thay đổi/image + lịch phù hợp rủi ro | Cần biết tài sản không được scan và phiên bản thực tế |
| Access recertification | Workflow theo kỳ + giám sát overdue/thu hồi | Không được kết luận đã review trước ngày đến hạn |
| Backup/restore | Backup monitor liên tục theo job + diễn tập khôi phục | Backup job xanh không chứng minh restore thành công |
| DR readiness | Theo dõi dependency và test theo kịch bản/chu kỳ | Không có kịch bản nào chứng minh mọi sự cố có thể xảy ra |

Ví dụ, **network exposure** có thể tạo tác động lớn ngay khi cấu hình thay đổi. Kiểm tra mỗi 24 giờ tạo cửa sổ sai lệch không phù hợp với nhiều hệ thống production. Trong khi đó, **đánh giá hiệu quả access review hàng quý** không thể hợp lý hóa bằng quét từng phút nếu hành động nghiệp vụ có tần suất theo kỳ.

Nên công bố các kỳ đo, mục tiêu phát hiện, điều kiện giám sát không hoạt động và mức rủi ro của thời gian mù. Không nên dùng chữ “real-time” nếu dữ liệu thực tế được làm mới sau nhiều giờ.

## 9. Preventive controls và policy-as-code

**Policy-as-code** biểu diễn một phần tiêu chí bảo mật thành điều kiện có thể kiểm tra bằng máy. Nó có thể được đặt ở:

- **Pre-commit/CI:** kiểm tra IaC, secret leakage, dependency, security test trước merge.
- **Build/release gate:** ngăn artifact hoặc configuration không đáp ứng security requirement.
- **Deployment/admission:** từ chối workload thiếu control được yêu cầu, như pod chạy đặc quyền trái policy.
- **Cloud/IAM control plane:** hạn chế tạo resource public hoặc thay IAM policy vượt phạm vi.
- **Application runtime:** thực thi authorization/validation cho từng thao tác.

Cần phân biệt **code đã được kiểm tra** với **trạng thái runtime**. Một policy gate PASS ở CI không ngăn thao tác thủ công về sau làm lệch cấu hình, nếu không có enforcement và monitoring bổ sung.

### 9.1. Ví dụ policy tạo storage

~~~text
Control objective:
  Dữ liệu nhạy cảm không được lưu trong object storage công khai.

Policy gate trước deploy:
  IF resource.data_classification == "sensitive"
     AND (resource.public_access_enabled
          OR resource.encryption_at_rest_disabled):
      DENY deployment

Post-deploy check:
  Inventory tất cả sensitive storage resources.
  So sánh policy thực tế với baseline.
  Đánh giá từng resource: PASS / FAIL / UNKNOWN.
  Kiểm tra sự kiện đổi policy và account mới.
~~~

Đây là **pseudocode** để minh họa logic, không phải một rule có thể sao chép chạy production. Hệ thống thực cần xem policy inheritance, network access, resource-level và account-level restrictions, object ACL, signed URL, alternate access path và ngoại lệ đã được duyệt.

### 9.2. Guardrails để tránh ngăn sai

- Thử chính sách với cả **trường hợp đúng** và **trường hợp sai** trước khi áp dụng.
- Kiểm tra route đặc quyền, khẩn cấp và đường DR được phép.
- Xác định control owner và quy trình cập nhật policy khi yêu cầu đổi.
- Ghi log mọi lần deny và lý do, nhưng không đưa secret/dữ liệu nhạy cảm vào log.
- Có cơ chế xử lý false positive và emergency exception trong phạm vi, thời hạn, thẩm quyền.
- Kiểm tra rằng chính pipeline/admission controller không thể bị bypass bởi một đường deploy khác.

## 10. Detective controls: phát hiện drift và sai lệch

**Drift** là việc trạng thái thực tế không còn khớp baseline hoặc điều kiện đã được phê duyệt. Drift có thể xảy ra do thao tác thủ công, tool tự động khác, update từ provider, điều chỉnh khẩn cấp hoặc thiếu đồng bộ.

### 10.1. Hai nguồn tín hiệu bổ trợ

**State-based check** hỏi: trạng thái hiện tại có đáp ứng tiêu chí không?

- Inventory cloud resources.
- Policy config export.
- Role assignment, KMS settings.
- Network ingress configuration.

**Event-based check** hỏi: đã có sự kiện nào thay đổi trạng thái hoặc gây hành vi cần theo dõi?

- Principal được cấp admin role.
- Bucket policy bị thay.
- Audit logging bị tắt.
- Secret được truy cập ngoài mẫu.
- Artifact được triển khai qua đường không được phê duyệt.

State check có thể phát hiện trạng thái sai đang tồn tại nhưng **không cho biết chính xác khi nào sai lệch bắt đầu**. Event log có thể chỉ ra thời điểm và chủ thể thay đổi, nhưng **có thể mất sự kiện**. Vì vậy kết hợp cả hai thường cho bằng chứng tốt hơn nếu các nguồn được kiểm tra đầy đủ.

### 10.2. Không biến “không thấy lỗi” thành “không có lỗi”

Một lần quét trả về 0 tài sản vi phạm có thể vì:

1. Thực sự không có tài sản vi phạm trong scope.
2. Collector không có quyền đọc một cloud account.
3. Inventory chỉ nhìn thấy tài sản có tag chuẩn và bỏ sót shadow assets.
4. Rule đánh giá sai phiên bản API hoặc chưa nhận diện policy kế thừa.
5. Query bị giới hạn thời gian hoặc pagination và mất trang.
6. Job đã lỗi nhưng dashboard hiển thị kết quả cũ.

Vì vậy **PASS chỉ có giá trị khi data-quality gates cũng PASS**. Nếu một account mất quyền thu thập hoặc inventory thiếu, kết quả nên là UNKNOWN/PARTIAL cho phần bị ảnh hưởng, không cộng vào mẫu số “đạt”.

## 11. Data quality: nền tảng của mọi tuyên bố assurance

Độ tin cậy của monitoring phụ thuộc chất lượng dữ liệu. Một chương trình kiểm soát liên tục phải kiểm tra chính **đường thu thập bằng chứng**.

| Khía cạnh | Câu hỏi | Ví dụ kiểm tra |
|---|---|---|
| **Completeness** | Tất cả source/asset/identity bắt buộc có mặt? | So asset inventory, cloud account inventory, source heartbeat |
| **Freshness** | Dữ liệu có đủ mới so với mục tiêu phát hiện? | Thời gian lần scan cuối, event lag |
| **Integrity** | Dữ liệu có bị sửa/cắt mất sau thu thập? | Version, hash, storage append-only khi phù hợp |
| **Accuracy** | Rule/query và cách diễn giải có đúng không? | Sample raw records, test fixtures, peer review |
| **Reliability** | Collector có quyền và hoạt động nhất quán? | API failure, retry, rate-limit, pagination coverage |
| **Time coherence** | Timestamp/timezone và clock drift có đúng? | UTC normalization, source clock health |
| **Correlation** | Nguồn có chung điểm lỗi không? | Lineage of signals, independent cross-check |
| **Traceability** | Kết luận nối được tới source, query, version và người duyệt? | Evidence ID, run ID, rule version |

### 11.1. Heartbeat và synthetic evidence

Với log pipeline, một cách kiểm tra có ích là **phát một sự kiện thử được phép** ở nguồn, rồi xác nhận đích đã nhận đủ field và alert đúng trong thời gian chấp nhận. Cần tránh dùng sự kiện thử gây ảnh hưởng hoặc làm lộ thông tin.

Nếu không có event thực trong một giờ, điều đó có thể hợp lý. **Một sự kiện synthetic có ID và timestamp** giúp xác nhận đường truyền vẫn hoạt động. Tuy vậy một synthetic event thành công **không chứng minh mọi loại sự kiện thật đều đầy đủ**, nên vẫn cần đối chiếu event taxonomy và nguồn quan trọng.

### 11.2. Xử lý khoảng trống lịch sử

Giả sử nguồn log mất 12 giờ hôm qua, hôm nay pipeline đã hoạt động lại. Bằng chứng mới chỉ cho thấy **hiệu lực hiện tại**; nó không chứng minh có log đầy đủ của 12 giờ đã mất. Nếu không thể khôi phục dữ liệu từ nguồn khác, cần giữ **historical evidence gap** trong hồ sơ assurance/audit, đánh giá tác động và hành động khắc phục.

Đổi từ FAIL/UNKNOWN của kỳ cũ thành PASS chỉ vì dashboard hôm nay xanh là làm sai sự thật về thời gian.

## 12. Evaluator: cách ra kết quả control có điều kiện

Một evaluator phải trả lời **đúng criteria trên đúng population và cửa sổ thời gian**. Ví dụ một control IAM:

~~~text
Inputs:
  privileged_human_identities
  approved_authentication_policy
  login_entry_points
  valid_time_bounded_exceptions
  observed_enforcement_and_events

For each identity in the verified population:
  IF critical input missing:
      result = UNKNOWN
  ELSE IF policy/enforcement violates requirement:
      IF valid exception exists:
          result = EXCEPTED  # not PASS
      ELSE:
          result = FAIL
  ELSE:
      result = PASS

Overall:
  PASS only when all mandatory coverage and data-quality gates pass,
  all required identities meet criteria, and no material blocker exists.
~~~

Đây là mã giả, không mô tả đầy đủ cơ chế IAM thực tế. Cần phân biệt user tương tác, service identity, break-glass, auth method được chấp nhận và các đường đăng nhập. **Không nên yêu cầu MFA dạng người dùng cho một machine identity chỉ để làm rule dễ viết**; control objective cho loại identity đó có thể là workload authentication và giới hạn credential tương ứng.

### 12.1. Kiểm tra rule engine

Rule cần test như một thành phần phần mềm:

- Input hợp lệ/không hợp lệ; account mới, tài sản bị xóa, null fields.
- Policy kế thừa và nhiều quyền tích lũy.
- Pagination, retry, rate limits và duplicate events.
- Ngoại lệ hết hạn hoặc không đủ thẩm quyền.
- Log thiếu nguồn và kết quả stale.
- Thay đổi phiên bản API hoặc schema.
- Trường hợp đúng nhưng hiếm, để giảm false positive.
- Trường hợp vi phạm đã biết, để phát hiện false negative.

Một rule báo 100% PASS nhưng chưa từng được kiểm tra bằng một **vi phạm giả lập có kiểm soát** có thể không chứng minh được khả năng phát hiện.

## 13. Continuous correction: từ phát hiện đến hành động

Không phải mọi sai lệch nên được sửa tự động. Cần phân loại theo mức nguy hiểm của **cả tình trạng sai và hành động sửa**.

| Tình huống | Phản ứng thường phù hợp | Kiểm tra sau hành động |
|---|---|---|
| IaC định tạo storage public trái policy | Chặn ngay trước deploy | Kiểm tra resource không được tạo sai và ticket có lý do |
| Một tài khoản cũ còn quyền ngoài chính sách | Tạo incident/finding, thu hồi theo quyền hạn và rủi ro | IAM export và login verification; root-cause review |
| Role production bị mở rộng quyền | Alert khẩn, xem xét containment/rollback policy | Đối chiếu cả những service cần quyền hợp lệ |
| Logging collector mất dữ liệu | Khôi phục pipeline, bảo toàn evidence và đánh giá gap | Test source-to-SIEM, alert pipeline failure |
| Config drift của DNS/DR | Xác nhận owner, đánh giá tác động, change/rollback có kiểm soát | Kiểm tra availability, integrity và security controls |
| Backup restore thất bại | Tạo finding và CAP, thử lại theo kế hoạch | Restore data, application, IAM/KMS, RTO/RPO |

### 13.1. Tự động sửa có rủi ro

Bot tự thu hồi admin role có thể vô tình thu hồi quyền của emergency operator khi đang có sự cố. Bot tự đổi network policy có thể làm mất đường quản trị hoặc ngắt payment workflow.

Nếu dùng auto-remediation, nên có:
- **Định danh rõ** policy và tài sản bị ảnh hưởng.
- **Phân tích tác động trước khi thực hiện** với hành động có khả năng gián đoạn.
- **Dry-run/simulation** và approval cho nhóm rủi ro cao.
- **Idempotency** để không nhân đôi side effects.
- **Giới hạn blast radius** và tốc độ sửa.
- **Kill switch** và rollback/forward fix đã được kiểm tra.
- **Log/quyết định có thể audit**, cùng kịch bản lỗi.
- **Retest** để chứng minh đã sửa đúng tiêu chí.

**Một ticket chuyển Closed do automation không đồng nghĩa control đã được xác minh hiệu lực.** Phải có bằng chứng của trạng thái sau sửa và, khi cần, review độc lập.

## 14. Ngoại lệ, sai lệch chưa duyệt và risk acceptance

Kiểm soát liên tục thường phát hiện những tài sản chưa thể đáp ứng baseline trong một khoảng thời gian. Cần phân biệt:

- **UNAPPROVED DEVIATION:** sai lệch chưa có quyết định hợp lệ; không được coi tuân thủ.
- **APPROVED EXCEPTION:** quyết định cho sai khác **trong một phạm vi, thời hạn và điều kiện** được phê duyệt.
- **RISK ACCEPTED:** người có thẩm quyền chấp nhận rủi ro còn lại, không đồng nghĩa control kỹ thuật đạt.
- **FALSE POSITIVE:** rule đã được chứng minh đánh giá nhầm; cần sửa logic/evidence.
- **NOT APPLICABLE:** yêu cầu thực sự không áp dụng theo tiêu chí; cần căn cứ.
- **REMEDIATED:** đã sửa điều kiện sai và có retest phù hợp.

Một exception record thường gồm **control, asset/identity, environment, allowed deviation, effective/expires, risk owner, approver, compensating controls, CAP, monitoring và re-review trigger**.

Nếu exception duyệt cho hai host nhưng autoscaling tạo host thứ ba, host mới **không tự được hưởng ngoại lệ**. Evaluator cần kết hợp kiểm tra asset scope, validity, điều kiện và thẩm quyền; không chỉ kiểm tra một ID trong allowlist rồi bỏ qua mọi vi phạm.

**Ngoại lệ nội bộ không thể tự xóa yêu cầu pháp luật, hợp đồng hoặc tiêu chuẩn bên ngoài không cho phép miễn trừ.** Trong chương trình assurance cần ghi rõ nghĩa vụ nào vẫn chưa đáp ứng dù đã có quyết định nội bộ.

## 15. Ownership: ai chịu trách nhiệm ở từng mắt xích?

Không nên để việc “tool báo FAIL” thành câu chuyện không ai sở hữu. Một mô hình trách nhiệm:

| Vai trò | Trách nhiệm |
|---|---|
| **Business/service owner** | Mục tiêu nghiệp vụ, mức tác động và quyết định residual risk trong thẩm quyền |
| **Control owner** | Định nghĩa control objective, criteria, scope, exception và cách xử lý |
| **Security engineering / platform** | Triển khai preventive controls, evaluators, inventory/telemetry |
| **SOC/detection engineering** | Rule phát hiện, cảnh báo, triage, threat coverage và phản ứng |
| **SRE/operations** | Availability, change, incident, phục hồi, vận hành pipeline và rollback |
| **GRC/risk** | Mapping policy, exception register, overdue, audit trail, thẩm quyền phê duyệt |
| **Independent reviewer / auditor** | Phản biện logic, kiểm tra bằng chứng, đánh giá hiệu quả và closure theo phạm vi |
| **Data/privacy owner** | Phân loại dữ liệu, quyền riêng tư, sử dụng và bảo vệ evidence nhạy cảm |

Tối thiểu cần một **accountable owner** cho từng control và một owner cho việc sửa từng finding. Người tự tạo rule có thể kiểm thử nội bộ, nhưng một kết luận assurance quan trọng nên có review phù hợp mức độc lập yêu cầu. Không nên giao mọi quyền định nghĩa, thực thi, sửa, phê duyệt exception và xác nhận đóng cho cùng một vai trò mà không có giám sát.

## 16. Bằng chứng liên tục: ghi gì để kiểm toán được?

Một bản ghi evidence không chỉ có nhãn PASS/FAIL. Nên ghi:

| Trường | Ý nghĩa |
|---|---|
| Control/requirement ID | Tiêu chí đang được kiểm tra và phiên bản |
| Run ID / event ID | Nhận diện lần kiểm tra hoặc sự kiện |
| Timestamp, window | Khi nào, cho khoảng thời gian nào |
| Population & denominator | Tập asset/identity đã được kiểm tra |
| Data quality status | Coverage/freshness/completeness/collector health |
| Result | PASS, FAIL, UNKNOWN, EXCEPTED theo quy tắc |
| Source & method | API, query, config snapshot, test script, rule version |
| Evidence references | Liên kết tới raw data, manifest, test report |
| Exceptions/findings | Ngoại lệ có điều kiện, CAP, incident, remediation ID |
| Owner/reviewer | Người chịu trách nhiệm và người thẩm tra |
| Retention/integrity | Quyền truy cập, version, kiểm tra thay đổi, thời hạn lưu |

### 16.1. Ví dụ một evidence record

~~~yaml
evidence_record:
  id: EV-MFA-EXAMPLE-2026-11-28-001
  control_id: IAM-PRIV-MFA-01
  control_version: "1.4"
  evaluated_at_utc: "2026-11-28T08:00:00Z"
  observation_window:
    from_utc: "2026-11-28T07:00:00Z"
    to_utc: "2026-11-28T08:00:00Z"
  population:
    source_ref: "restricted/inventory/production-privileged-identities"
    expected_accounts: 4
    accounts_collected: 4
    expected_identities: 120
    identities_evaluated: 120
    completeness_review: PASS
  collector:
    id: iam-policy-collector
    api_status: HEALTHY
    max_source_lag_minutes: 5
    rule_version: "mfa-check-v1.4"
  results:
    pass: 116
    fail: 2
    excepted: 2
    unknown: 0
  exception_refs:
    - EX-EXAMPLE-09
    - EX-EXAMPLE-10
  finding_refs:
    - IAM-FINDING-EXAMPLE-021
  result_for_entire_control: FAIL
  evidence_refs:
    - "restricted/evidence/iam-snapshot"
    - "restricted/evidence/privileged-login-check"
    - "restricted/evidence/collector-health"
  reviewer_role: SECURITY_ASSURANCE_REVIEWER
  review_status: PENDING
~~~

**Toàn bộ mã, con số, thời gian, ID và đường dẫn là dữ liệu giả định.** Việc có một file YAML ghi “completeness_review: PASS” không tự chứng minh nguồn đủ. Người đánh giá phải kiểm tra inventory, phép truy vấn, log nguồn và các hiện vật tham chiếu. Trong ví dụ, hai trường hợp ngoại lệ **không được cộng thành compliant**; hai trường hợp FAIL vẫn khiến control chưa đạt trong phạm vi yêu cầu.

### 16.2. Privacy và bảo mật evidence

Evidence của IAM, log hoặc vulnerability có thể tiết lộ tài khoản, host, đường mạng, secrets, thông tin người dùng và điểm yếu bảo mật. Cần phân quyền theo mục đích, giảm dữ liệu không cần thiết, giữ audit trail, kiểm soát retention và truy xuất qua reference ID.

Hash hoặc chữ ký có thể giúp phát hiện tệp bị thay đổi sau khi lưu; **không chứng minh nguồn dữ liệu vốn đúng và đầy đủ**. Những báo cáo chia sẻ rộng nên hiển thị summary được phép, không nhúng credential hay danh sách tài sản dễ bị khai thác.

## 17. Metrics cho kiểm soát liên tục

Metrics cần hỗ trợ ra quyết định và có định nghĩa mẫu số/chỉ tiêu rõ ràng.

| Chỉ số | Cách hiểu | Giới hạn |
|---|---|---|
| **Verified control coverage** | Tỷ lệ tài sản/luồng trong population đã được đánh giá với evidence đủ | Population thiếu làm tỷ lệ đẹp giả |
| **Current control failure count** | Số đối tượng đang không đạt control | Cần xét mức rủi ro và mức nghiêm trọng của từng đối tượng |
| **Detection latency** | Thời gian từ lúc sai lệch bắt đầu tới lúc hệ thống ghi nhận phát hiện | Thời điểm bắt đầu có thể không biết nếu mất log |
| **Time to containment/remediation** | Thời gian tới khi giảm phơi nhiễm hoặc sửa và xác minh | Containment không bằng verified closure |
| **Evidence freshness** | Độ trễ nguồn, lần đánh giá cuối và kỳ còn hiệu lực | Data mới nhưng nguồn không đầy đủ vẫn yếu |
| **Unknown / no-evidence count** | Số đối tượng không thể kết luận | Không nên loại khỏi mẫu số để “tăng compliance” |
| **Exception age / overdue** | Ngoại lệ kéo dài và số lần gia hạn | Exception đã duyệt vẫn là rủi ro tồn đọng |
| **Repeat finding rate** | Sai lệch tái diễn sau closure | Có thể do root cause chưa xử lý hoặc drift |
| **Control test reliability** | Tỷ lệ job/test chạy thành công và phát hiện fixture vi phạm | Test pass rate không bằng xác suất an toàn |
| **False positive / false negative review** | Chất lượng rule và chi phí triage | False negative khó thấy nếu không chủ động test |
| **Source-health coverage** | Tỷ lệ nguồn quan trọng có heartbeat/reconciliation | Cần biết danh mục nguồn kỳ vọng đầy đủ |

### 17.1. Ví dụ cách diễn giải có trách nhiệm

Giả sử có **120 identity** trong population đã xác minh:
- 116 đáp ứng control.
- 2 vi phạm không có ngoại lệ.
- 2 có ngoại lệ đúng thẩm quyền, còn hiệu lực và có điều kiện bù trừ.

Có thể báo **116/120 đáp ứng trực tiếp tiêu chí**, **2/120 vi phạm**, **2/120 có ngoại lệ**, kèm trạng thái giám sát. Không nên công bố “118/120 compliant” chỉ bằng cách cộng ngoại lệ vào PASS nếu control requirement vẫn chưa được đáp ứng.

Nếu còn **10 identity không được thu thập** từ một cloud account ngoài danh mục, mẫu số 120 chưa phải toàn population; mọi tỷ lệ phải bị đánh dấu **incomplete/unknown**, không dùng làm tuyên bố assurance toàn production.

### 17.2. Metrics không thay thế đánh giá rủi ro

Một sai lệch IAM trên principal có quyền toàn account có thể quan trọng hơn hàng trăm sai lệch tag của tài sản thử nghiệm. Báo cáo nên phân nhóm theo **severity, asset criticality, data classification, control objective và thời gian phơi nhiễm**. Không dùng tỷ lệ trung bình để che blocker trọng yếu.

## 18. Vận hành khi detector sai hoặc pipeline hỏng

Continuous assurance cần khả năng tự phát hiện **hỏng cơ chế đo**.

### 18.1. Khi có false positive

Ví dụ rule cảnh báo mọi account thiếu MFA, kể cả service principal chỉ dùng workload identity không có interactive login. Đây có thể là **lỗi định nghĩa population**, không phải security finding thực.

Cách xử lý:
1. Kiểm tra control criteria và type của identity.
2. Xác nhận nguồn dữ liệu và hành vi thực.
3. Ghi quyết định false positive có evidence và người kiểm tra.
4. Sửa rule, thêm positive/negative fixtures.
5. Chạy lại toàn population, kiểm tra các finding liên quan.
6. Không xóa lịch sử kết quả cũ mà không có trace.

### 18.2. Khi có false negative

Detector không báo một bucket đã public vì query bỏ qua resource thuộc region mới. Đây là khoảng trống nghiêm trọng hơn dashboard cho thấy; cần:
- Mở finding về coverage của tool và đánh giá các control có liên quan.
- Xác định thời kỳ mất bảo đảm và tài sản bị ảnh hưởng.
- Sửa inventory/query, thêm fixtures cho region mới.
- Thu thập lại bằng chứng nếu có thể, xử lý các vi phạm thực.
- Rà soát những kết luận PASS trước đó có phụ thuộc nguồn lỗi này.

### 18.3. Khi nguồn dữ liệu không hoạt động

Nếu collector mất quyền IAM read hoặc một account API timeout, **không suy ra không còn vi phạm**. Đánh dấu nguồn/đối tượng UNKNOWN, phát cảnh báo riêng về monitoring health, áp dụng biện pháp kiểm soát tạm theo mức rủi ro và khôi phục pipeline.

Một chương trình control liên tục đáng tin phải có **monitoring of the monitor**; nhưng vòng kiểm tra đó cũng cần đánh giá tính đầy đủ, không tạo chuỗi niềm tin vô hạn.

## 19. Continuous controls trong SDLC và release

Một hệ thống cần kiểm soát từ lúc thiết kế đến production.

### 19.1. Design và threat modeling

- Security objectives và yêu cầu được chuyển thành control criteria.
- Threat model xác định nơi enforcement cần xuất hiện và đường bypass có thể có.
- Kiến trúc có owner, tài sản trọng yếu và data flow được kiểm kê.
- Định nghĩa bằng chứng cần có ngay từ đầu, thay vì chờ audit mới tìm log.

### 19.2. Build và CI/CD

- Kiểm tra dependency, secrets, IaC policy, unit/integration security tests.
- Ánh xạ từng phép thử tới requirement/control, phiên bản source và artifact.
- Test negative paths và policy failure cases.
- Nếu gate bị bypass do emergency, phải có dấu vết, quyền hạn và review hậu thay đổi.

### 19.3. Release

- Chốt release candidate và artifact digests.
- Rà soát interaction risks giữa các thay đổi, không chỉ PR riêng lẻ.
- Xác minh mandatory security gates và ngoại lệ có điều kiện.
- Có staged rollout, kill switch, rollback/forward fix và monitoring plan.

### 19.4. Production

- Enforcement đúng trust boundary.
- State/event collection và kiểm tra source health.
- Phát hiện drift, triage, incident response, CAP và retest.
- Đánh giá lại khi account/region/route mới xuất hiện.

### 19.5. Audit và cải tiến

- Trình bày chuỗi criteria → control → coverage → evidence → conclusion.
- Đánh giá cả **design effectiveness** lẫn **operating effectiveness** trong phạm vi phù hợp.
- Ghi finding/exception, root cause, owner, deadline và verification.
- Dùng trend tái diễn và evidence gaps để cải tiến policy, tool và vận hành.

## 20. Case study: MFA đặc quyền và bảo vệ storage trên nhiều cloud account

**Toàn bộ dữ liệu và thời gian sau đây là giả định học tập.**

### 20.1. Bối cảnh

Một nền tảng SaaS dùng **4 cloud account production** thuộc hai region. Có **120 human identities** được phân loại là có quyền đặc biệt theo policy; hệ thống có object storage lưu báo cáo khách hàng. Nhóm bảo mật muốn hỗ trợ hai mục tiêu:

- **C1 — Privileged authentication:** mọi tài khoản đặc quyền tương tác trong population phải dùng phương pháp xác thực mạnh theo security policy khi login; ngoại lệ chỉ có hiệu lực với phạm vi và thời hạn đã duyệt.
- **C2 — Sensitive storage exposure:** mọi bucket/object store có dữ liệu nhạy cảm trong inventory phải không cho phép truy cập công khai trái policy và có logging thay đổi trạng thái quan trọng.

Ban đầu, tổ chức kiểm tra thủ công hàng tháng. Một lần audit cho thấy 2 identity đi qua luồng cấp quyền khẩn cấp không chịu policy MFA, một bucket được mở public trong 45 phút và một account mới không có trong danh sách scan.

### 20.2. Thiết kế control loop

| Thành phần | C1: Privileged IAM | C2: Sensitive storage |
|---|---|---|
| Preventive | Enforce MFA/authn tại IdP và IAM admission phù hợp identity type | Policy chặn public exposure ở nơi hỗ trợ |
| Population | Privileged identities từ account inventory + IdP/IAM | Storage inventory từ mọi account/region và data classification |
| Event signals | Role grant, policy change, emergency provisioning | Bucket policy/ACL, public exposure/config events |
| State check | Định kỳ đối chiếu role và authn enforcement | Định kỳ đánh giá config thực tế |
| Synthetic tests | Test an toàn đường login và cấp quyền đặc biệt | Test cấu hình đã chọn bằng policy evaluation phù hợp |
| Data quality | 4/4 account được thu thập, loại identity rõ, timestamp đủ | Coverage từng account/region, pagination, tag/classification |
| Response | Finding IAM, containment, CAP sửa workflow | Hạn chế public exposure an toàn, incident triage nếu có truy cập |
| Verification | Retest luồng thường/khẩn cấp và hoạt động IAM | Policy recheck, log changes, đánh giá dữ liệu có thể bị lộ |
| Reporting | PASS/FAIL/EXCEPTED/UNKNOWN theo identity | PASS/FAIL/UNKNOWN theo storage resource |

### 20.3. Kết quả giả định ở vòng đầu

Lần đánh giá đầu cho thấy:
- 116/120 identity PASS.
- 2/120 vi phạm yêu cầu MFA ở đường login tương tác.
- 2/120 có ngoại lệ khẩn cấp được phê duyệt đúng nhưng sắp hết hạn.
- 3/4 cloud account gửi trạng thái storage đầy đủ; cloud account thứ tư bị collector từ chối quyền đọc.
- Từ nguồn event, một bucket thuộc account thứ tư đã được đổi policy nhưng không có snapshot để biết trạng thái hiện tại.

**Đánh giá đúng:**
- C1 chưa đạt trên ít nhất 2 identity, dù phần lớn population PASS.
- C2 **NOT DEMONSTRATED** ở cấp toàn production, vì nguồn thứ tư thiếu coverage; không được báo “0 bucket public” trên toàn hệ thống.
- Ngoại lệ của 2 identity cần theo dõi hạn và điều kiện, không gộp vào PASS.
- Data-quality failure của cloud account thứ tư cần ticket/escalation riêng, vì nó làm suy yếu kết luận assurance.

### 20.4. Phân tích nguyên nhân và CAP

Đội IAM xác định workflow cấp quyền khẩn cấp tạo principal trước khi enforcement policy được gắn, và khi đồng bộ lỗi thì không có bước kiểm tra hậu cấp. Đội cloud xác định role của collector chưa cập nhật quyền đọc khi account mới được onboard.

CAP mẫu:

| Action | Owner giả định | Tiêu chí kiểm chứng |
|---|---|---|
| A1: hạn chế hai đường login chưa bảo vệ | IAM Ops | Trạng thái quyền và login test có evidence |
| A2: sửa workflow khẩn cấp, fail closed khi policy chưa áp | IAM Engineering | Test luồng lỗi/success, không có bypass |
| A3: kiểm tra lại toàn bộ privileged population | IAM Governance | 4/4 account + IdP mapping đủ nguồn và role |
| A4: sửa onboarding/permissions của collector | Cloud Platform | 4/4 account được đọc, pagination đầy đủ |
| A5: đánh giá bucket có sự kiện đổi policy | Security Operations | Config history, event timing, data exposure assessment |
| A6: kiểm tra mất nguồn định kỳ | Detection Engineering | Synthetic/source-health test và alert khi account vắng |
| A7: retest và review độc lập | Security Assurance | Evidence đúng phiên bản, scope và closure criteria |

Không nên kết luận tài sản thứ tư an toàn chỉ vì sửa quyền collector xong; cần **thu thập lại trạng thái thực và rà soát lịch sử event** nếu có.

### 20.5. Giả sử có bản sửa, nhưng còn giới hạn lịch sử

Sau khi sửa:
- Đủ 4/4 account trong inventory và collector.
- Hai identity được áp policy mới, thử các đường login theo tiêu chí đạt.
- Policy gate đã ngăn tạo principal khẩn cấp không có enforcement.
- Storage snapshot không còn resource public trái policy trong phạm vi.
- Có evidence alert về account mới, drift và thay đổi policy.

Nhưng nếu **khoảng 45 phút bucket public trước đây không có log truy cập đầy đủ**, không thể kết luận “không ai đã truy cập dữ liệu” từ trạng thái hiện tại. Cần ghi **historical uncertainty**, đánh giá khả năng ảnh hưởng dữ liệu và nghĩa vụ xử lý tương ứng.

Kết luận assurance có trách nhiệm:

> Trong cửa sổ kiểm chứng mới, hai control C1 và C2 được đánh giá trên inventory đã đối chiếu của bốn cloud account. Những đường IAM và cấu hình storage thuộc phạm vi đã thử đáp ứng tiêu chí hiện tại; enforcement, collector health và cảnh báo drift có bằng chứng. Hai ngoại lệ khẩn cấp được quản lý riêng đến khi hết hạn. Khoảng thời gian trước đây khi storage có khả năng public và thiếu log truy cập vẫn là giới hạn bằng chứng, không được coi đã chứng minh không có truy cập trái phép.

### 20.6. Điều gì làm kết luận mất hiệu lực?

- Thêm account, region, tenant hoặc đường login.
- Đổi IdP, role mapping hoặc emergency provisioning.
- Chuyển storage sang nhà cung cấp/dịch vụ khác.
- Thay security policy, data classification hoặc control objective.
- Detector mất quyền, đổi API, bị rate-limited hoặc thiếu lịch sử.
- Có incident, finding, test fail hay threat mới ảnh hưởng assumption.

Những sự kiện này phải kích hoạt **impact assessment, cập nhật control spec và kiểm thử/evidence mới**, không chờ đến audit cuối năm.

## 21. Lộ trình triển khai theo mức trưởng thành

Không cần tự động hóa toàn bộ control từ ngày đầu. Một lộ trình thực dụng:

### Giai đoạn 1 — Biết mình cần bảo vệ gì

- Chọn một số **critical controls** từ risk assessment, không bắt đầu bằng danh mục tool.
- Chốt control objective, criteria, owner, asset population và nguồn bằng chứng.
- Đánh giá khả năng đọc hiện trạng của inventory, log và change history.
- Đặt baseline và thước đo chất lượng dữ liệu.

**Deliverable:** control register và evidence plan có người chịu trách nhiệm.

### Giai đoạn 2 — Phát hiện đáng tin

- Tự động thu thập trạng thái/sự kiện cho control đã chọn.
- Kiểm tra account/region/source coverage, heartbeat và data freshness.
- Chạy evaluator có PASS/FAIL/UNKNOWN và bảo toàn raw evidence.
- Phân loại alert, triage false positives và kiểm tra khả năng phát hiện vi phạm mẫu.

**Deliverable:** detection loop có evidence, không bỏ sót nguồn một cách im lặng.

### Giai đoạn 3 — Kết nối phản ứng và xác minh

- Ánh xạ findings tới owner, risk, CAP và exception.
- Tự động hóa hành động an toàn; hành động rủi ro cao có approval/guardrails.
- Xây retest/closure criteria trước khi sửa.
- Theo dõi thời gian phơi nhiễm và nguyên nhân tái diễn.

**Deliverable:** chuỗi finding → remediation → verification có thể audit.

### Giai đoạn 4 — Assurance có thể dùng để ra quyết định

- Đánh giá thiết kế, vận hành và độ tin cậy bằng chứng của các control trọng yếu.
- Liên kết tới assurance case, release gates và các quyết định risk acceptance.
- Review độc lập định kỳ, theo dõi changes khiến evidence lỗi thời.
- Cải tiến dựa trên recurrence, false negative, source gaps và lessons learned.

**Deliverable:** kết luận an ninh có phạm vi, evidence, limitations và chủ thể quyết định rõ.

## 22. Các sai lầm thường gặp

| Sai lầm | Tác hại | Cách khắc phục |
|---|---|---|
| Có dashboard nên coi là continuous assurance | Không biết control có thực thi/đạt không | Mapping criteria → evidence → conclusion |
| 0 alert nghĩa là 0 rủi ro | Có thể detector mất nguồn | Heartbeat, coverage, synthetic checks |
| 100% compliance trên inventory thiếu | Bỏ tài sản ngoài danh mục | Xác minh population từ nhiều nguồn |
| Quét liên tục nhưng không xử lý findings | Rủi ro tồn đọng dù detector tốt | Owner, severity, CAP, retest |
| Auto-remediate mọi vi phạm | Có thể gây sự cố hoặc mất đường quản trị | Guardrails, risk review, safe rollback |
| Dùng một rule cho mọi identity | Sai với service accounts/break-glass | Định nghĩa population và control theo loại |
| Một screenshot hôm nay chứng minh cả quý | Không có bằng chứng lịch sử | Lưu event/state history và thời kỳ |
| Thêm exception vào PASS | Làm sai trạng thái control | EXCEPTED riêng, theo dõi risk |
| Gia hạn ngoại lệ tự động | Sai khác trở thành mặc định | Review rủi ro, quyền duyệt, hạn, CAP |
| Chỉ kiểm tra state, bỏ thay đổi sự kiện | Không biết khoảng phơi nhiễm | Kết hợp state và event signals |
| Chỉ có event, không đối chiếu state | Mất event tạo false negative | Reconciliation snapshot định kỳ |
| SAST/CI xanh là proof production | Code/config runtime có thể khác | Runtime/deployment evidence |
| Control chạy nhưng không kiểm tra rule | Rule có thể luôn PASS do lỗi | Positive/negative fixtures, reviewer |
| Logging nhiều nhưng không kiểm tra đủ nguồn | Mất sự kiện trọng yếu | Source inventory, schema, end-to-end tests |
| Xóa FAIL cũ sau khi đã sửa | Che thời kỳ không đáp ứng | Immutable/versioned history, hậu kiểm |
| Đếm số policy làm KPI an toàn | Không phản ánh hiệu quả | Coverage, evidence quality, time-to-verified-remediation |
| Một người tự viết rule và tự duyệt kết quả | Tăng thiên lệch | Segregation of duties, independent review |
| Công cụ phát hiện cloud account mới nhưng không tự mở scope | Có blind spot nghiêm trọng | Onboarding và review theo thay đổi |
| Không kiểm tra privacy của evidence | Rò rỉ dữ liệu qua SIEM/report | Least privilege, minimization, retention |
| Không kiểm tra tác động tới DR | Sửa bảo mật nhưng phá phục hồi | Test recovery dependencies và regression |

## 23. Bài tập thực hành

### Bài tập A — Từ câu “có kiểm soát liên tục” thành control spec

Một nhóm tuyên bố: “Mọi tài khoản admin đều an toàn vì SIEM theo dõi đăng nhập.”

1. Vì sao tuyên bố chưa đủ để kết luận MFA/privileged access đạt?
2. Viết lại control objective và phân biệt human interactive account với machine identity.
3. Đề xuất population inventory, event/state evidence, frequency và cửa sổ quan sát.
4. Nêu tối thiểu năm data-quality gates cần có.
5. Thiết kế PASS/FAIL/UNKNOWN/EXCEPTED và biện pháp xử lý tương ứng.
6. Mô tả một phép thử synthetic hoặc negative test được phép để kiểm tra khả năng phát hiện.

### Bài tập B — Drift và mất nguồn

Hệ thống quét cloud config mỗi 30 phút, phát hiện một object store public lúc 10:30. Log cho thấy policy thay đổi lúc 10:04. Một region mới lại không có trong inventory.

1. Khoảng thời gian có bằng chứng về phơi nhiễm được xác định thế nào?
2. Vì sao không thể khẳng định mọi storage ngoài region đó đều an toàn?
3. Cần containment, đánh giá tác động dữ liệu và remediation nào?
4. Viết cách hiển thị kết quả: phạm vi được kiểm tra, UNKNOWN region, finding và risk status.
5. Đề xuất preventive policy và monitoring bổ sung để giảm khả năng tái diễn.

### Bài tập C — Logging sau khi pipeline được sửa

Audit phát hiện 12 giờ log quản trị không đến SIEM. Sau khi sửa, pipeline hoạt động và synthetic test PASS trong 7 ngày.

1. Những claim nào có thể hỗ trợ cho trạng thái hiện tại?
2. Claim nào về 12 giờ quá khứ còn NOT DEMONSTRATED?
3. Làm sao kiểm tra collector/source completeness, event taxonomy và alert rules?
4. Nêu evidence cần lưu cho CAP, retest và auditor.
5. Đề xuất trigger để phát hiện pipeline mất nguồn sớm.

### Bài tập D — Ngoại lệ không đúng phạm vi

Ngoại lệ cho phép trì hoãn patch của hai workload production tới ngày D, với điều kiện network isolation và monitoring. Một workload thứ ba được autoscale từ cùng image; monitoring cho một workload không còn dữ liệu.

1. Tài sản mới có tự nằm trong ngoại lệ không?
2. Control status của ba workload được phân loại thế nào?
3. Mất monitoring làm ảnh hưởng hiệu lực ngoại lệ ra sao?
4. Ai phải quyết định việc tiếp tục, containment và risk escalation?
5. Viết closure criteria và evidence cần có để kết thúc ngoại lệ.

### Bài tập E — Đánh giá độ tin cậy dashboard

Dashboard hiển thị 99,5% resource compliant, nhưng:
- 3/20 cloud accounts chưa được scan.
- Các “EXCEPTED” được cộng vào PASS.
- 2 scanner jobs gần nhất lỗi timeout.
- Một finding critical bị đóng khi PR merge, chưa có retest.

Hãy viết một **assurance assessment ngắn** nêu điều đã biết, điều không thể kết luận, các hành động ưu tiên, mức nghiêm trọng của evidence gap và điều kiện mới có thể dùng dashboard cho quyết định.

**Gợi ý:** Không sửa số liệu cho đẹp bằng cách bỏ các nguồn UNKNOWN. Một lời giải tốt phải ưu tiên **tính đầy đủ của population, hiệu lực thật của control và bằng chứng sau khắc phục**.

## 24. Checklist vận hành kiểm soát liên tục

Trước khi tuyên bố một control vận hành và được đánh giá liên tục, xác nhận:

- [ ] Control objective gắn với risk/security requirement và có owner.
- [ ] Criteria đủ cụ thể để kiểm tra và được version hóa.
- [ ] Population của asset/identity/flow được định nghĩa và đối chiếu đầy đủ.
- [ ] Nhịp kiểm tra phù hợp tốc độ thay đổi và tác động rủi ro.
- [ ] Có preventive controls ở nơi cần thiết, không chỉ detector.
- [ ] State và event signals được dùng phù hợp; nguồn có monitoring health.
- [ ] Logic kiểm tra có test cho trường hợp đúng, vi phạm và thiếu dữ liệu.
- [ ] PASS/FAIL/UNKNOWN/EXCEPTED được phân biệt và xử lý rõ.
- [ ] Evidence có source, timestamp, window, run ID, rule version và link.
- [ ] Cảnh báo có owner, ngưỡng, triage và escalation theo rủi ro.
- [ ] Auto-remediation có guardrails, rollback và kiểm thử sau sửa.
- [ ] Exception có đúng scope, risk owner, approval, hạn và điều kiện.
- [ ] Control định kỳ có evidence về vận hành trong chu kỳ thích hợp.
- [ ] Dữ liệu nhạy cảm trong evidence được bảo vệ và lưu giữ đúng yêu cầu.
- [ ] Reviewer độc lập có thể lần theo criteria → raw evidence → conclusion.
- [ ] Change/release/incident kích hoạt review và retest cho control liên quan.
- [ ] Các khoảng trống lịch sử không bị xóa khi trạng thái hiện tại đã xanh.

Checklist là công cụ thực hành, không phải tiêu chuẩn chứng nhận độc lập hoặc bằng chứng rằng tất cả control đã đạt.

## 25. Ghi nhớ

**Kiểm soát liên tục** không chỉ là quét nhiều lần hay bật một công cụ giám sát. Đó là một **vòng kiểm soát có thể chứng minh được**: từ định nghĩa mục tiêu và phạm vi, thực thi ngăn chặn, thu thập trạng thái và sự kiện, kiểm tra chất lượng dữ liệu, đánh giá control, xử lý sai lệch, xác minh khắc phục đến cập nhật kết luận assurance.

Trong **SECURITY_SECURITY_ASSURANCE**, chuỗi truy vết cần giữ là:

**Risk / Security objective → Control requirement & scope → Enforcement + monitoring → Data-quality verification → Evidence-backed evaluation → Finding / exception / remediation → Retest & reviewer → Assurance decision → Re-evaluation on change.**

Kết luận có trách nhiệm phải nêu rõ **control nào được đánh giá, áp dụng cho tài sản và thời kỳ nào, bằng chứng nào đủ tin cậy, điều gì đang FAIL hoặc UNKNOWN, ai chịu trách nhiệm và điều gì sẽ khiến kết luận phải được xem xét lại**. Một hệ thống kiểm soát liên tục tốt không giả vờ rằng mọi thứ luôn an toàn; nó giúp tổ chức **phát hiện sớm sai lệch, kiểm chứng được việc sửa và ra quyết định bảo mật dựa trên sự thật**.
