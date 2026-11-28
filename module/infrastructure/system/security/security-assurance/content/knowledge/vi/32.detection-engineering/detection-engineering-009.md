# Detection blind spot: nhận diện, đo lường và giảm điểm mù trong phát hiện đe dọa

**Detection blind spot (điểm mù phát hiện)** là khoảng thiếu hụt khiến một hoạt động có ý nghĩa đối với an ninh không được hệ thống phát hiện hoặc không chuyển thành tín hiệu có thể xử lý đúng lúc. Điểm mù có thể xuất phát từ việc không có nguồn sự kiện, thiếu trường dữ liệu, lỗi truyền nhận, logic phát hiện không bao phủ kịch bản, cấu hình loại trừ quá rộng, cảnh báo bị triệt tiêu hoặc quy trình triage không đưa ra hành động. Một hệ thống có nhiều log và rất nhiều detection rule vẫn có thể có điểm mù nghiêm trọng.

Trong chương **Detection engineering** của module **SECURITY_SECURITY_ASSURANCE**, nhiệm vụ là đánh giá **có bằng chứng** rằng hệ thống đáp ứng mục tiêu bảo mật, từ phân tích rủi ro, yêu cầu và security controls đến kiểm thử, audit, xử lý phát hiện và cải tiến liên tục. Với detection blind spot, câu hỏi assurance cốt lõi là: **trong một kịch bản đe dọa cụ thể, hoạt động nào cần được quan sát, nguồn nào phải ghi nhận, phép phát hiện nào phải hoạt động, cảnh báo có đến đúng nơi và con người có thể hành động kịp thời hay không?**

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích điểm mù phát hiện và phân biệt nó với lỗ hổng phần mềm, sự cố logging, cảnh báo sai và độ trễ điều tra.
2. Phân loại điểm mù từ asset coverage, telemetry, data pipeline, detection logic, triển khai rule đến triage và phản ứng.
3. Sử dụng threat scenario và giả thuyết phát hiện để xác định yêu cầu telemetry và phép kiểm.
4. Xây dựng ma trận bao phủ phát hiện có mẫu số, phạm vi, độ tin cậy và chứng cứ kiểm thử rõ ràng.
5. Thực hiện thử nghiệm an toàn nhằm chứng minh một tín hiệu đi từ nguồn qua pipeline đến alert và người xử lý.
6. Ưu tiên khắc phục, quản lý ngoại lệ và tái kiểm tra liên tục khi hệ thống thay đổi.

## 2. Detection blind spot là gì?

### 2.1. Minh họa bằng một tình huống

Một tổ chức vận hành ứng dụng thanh toán trên cloud. Kẻ tấn công đánh cắp quyền của một workload và thay đổi chính sách truy cập vào kho dữ liệu. Ứng dụng vẫn chạy, dashboard SIEM vẫn có log, nhưng SOC không nhận được cảnh báo vì một trong các nguyên nhân:

- Cloud account mới chưa nằm trong phạm vi thu audit log tập trung.
- Audit log đã được gửi đi nhưng parser không giữ lại trường tên hành động hoặc định danh principal.
- Rule chỉ khớp một loại tên API cũ; biến thể hành động mới không được bao phủ.
- Rule được viết đúng nhưng chưa được triển khai trên môi trường production.
- Cảnh báo được tạo nhưng bị suppression bởi một ngoại lệ quá rộng.
- Cảnh báo xuất hiện ở hàng đợi không có người trực hoặc bị loại trong quy trình triage.

Các tình huống trên có **cùng hậu quả**: hành vi nguy hiểm không tạo ra phản ứng phù hợp. Tuy nhiên, nguyên nhân kỹ thuật và cách sửa rất khác nhau. Vì thế cần phân tích toàn bộ đường đi của tín hiệu.

### 2.2. Phân biệt các khái niệm

| Khái niệm | Câu hỏi cốt lõi | Ví dụ |
|---|---|---|
| **Visibility / observability** | Có tín hiệu mô tả hành vi cần quan sát không? | Có bản ghi API thay đổi IAM hay không? |
| **Telemetry coverage** | Tín hiệu có từ mọi asset, môi trường, nguồn và kỳ cần thiết không? | Account production mới có được thu log? |
| **Detection coverage** | Có phân tích nào nhận ra hành vi liên quan từ dữ liệu sẵn có? | Có rule cho việc cấp quyền quá mức? |
| **Detection efficacy** | Rule thực sự hoạt động tốt trên các biến thể và dữ liệu có nhiễu không? | Rule phát hiện được các tình huống kiểm thử đã chọn? |
| **Operational readiness** | Alert có được gửi đến đúng người và xử lý theo playbook không? | Analyst có nhận alert và biết bước triage? |
| **Blind spot** | Chặng nào khiến hành vi thuộc phạm vi không thể được phát hiện hoặc xử lý theo kỳ vọng? | Log có nhưng bị parser loại mất trường quan trọng |
| **False negative (FN)** | Một trường hợp đáng phát hiện trong tập đánh giá đã không được hệ thống phát hiện | Test được kỳ vọng tạo alert nhưng không có alert |
| **False positive (FP)** | Hệ thống gắn nhãn một hoạt động không thuộc điều kiện đe dọa là đáng ngờ | Job quản trị hợp lệ liên tục kích hoạt alert |

**Không có alert** không tự chứng minh **không có tấn công**. Ngược lại, một alert được kích hoạt trong một bài thử không chứng minh hệ thống bao phủ toàn bộ biến thể tấn công. Kết luận phải gắn với tập kịch bản, điều kiện kiểm thử và phạm vi triển khai.

### 2.3. Điểm mù thay đổi theo thời gian

Blind spot có thể xuất hiện khi:

- Tạo cloud account, project, namespace hoặc cluster mới mà pipeline không tự nhận diện.
- Di chuyển workload từ VM sang container/serverless.
- Đổi nhà cung cấp identity, log schema hoặc API phiên bản mới.
- Tắt một loại audit event để giảm chi phí.
- Thay phiên bản collector, parser, SIEM query hoặc rule.
- Bổ sung suppression/allowlist do một cảnh báo nhiễu.
- Không kiểm tra thời hạn ngoại lệ, quyền truy cập hoặc định tuyến alert.
- Nguồn vẫn phát heartbeat nhưng sự kiện quan trọng bị lọc bỏ.

Do đó, điểm mù là **trạng thái của hệ thống và giả định kiểm soát tại một thời điểm**, không phải một danh sách cố định làm một lần là xong.

## 3. Mô hình chuỗi phát hiện end-to-end

Một phát hiện đáng tin cậy cần ít nhất các mắt xích: tài sản nằm trong inventory, hoạt động phát sinh tín hiệu, nguồn ghi nhận, dữ liệu được chuyển và chuẩn hóa, logic đánh giá, kết quả được xuất thành alert, alert được định tuyến và đội vận hành xác nhận hành động.

~~~mermaid
flowchart LR
    A["Threat scenario / asset"] --> B["Hoạt động có thể quan sát"]
    B --> C["Sensor / audit source"]
    C --> D["Pipeline: gửi, parse, enrich"]
    D --> E["Detection logic"]
    E --> F["Rule enabled / evaluated"]
    F --> G["Alert + routing"]
    G --> H["Triage + response"]
    H --> I["Evidence + feedback"]
    I --> A
~~~

### 3.1. Các ranh giới tin cậy

- **Asset → sensor:** hoạt động có tạo sự kiện hay không; sensor có chạy đúng quyền và phạm vi hay không.
- **Sensor → pipeline:** sự kiện có bị drop, trễ, lặp, sai thời gian hoặc mất khi restart hay không.
- **Pipeline → analytic:** parser có giữ đúng field, normalization có làm đổi nghĩa, enrichment có gắn nhầm danh tính hay không.
- **Analytic → alert:** rule có bật, đúng phiên bản, chạy trên index/stream đúng và có ngoại lệ bất hợp lý hay không.
- **Alert → người xử lý:** severity, owner, kênh nhận, thời gian trực, ticket/playbook và giới hạn công cụ có đủ hay không.

Mỗi ranh giới nên có ít nhất một bằng chứng kỹ thuật và một kiểm tra thực tế. Ví dụ, ảnh chụp cấu hình "collector running" không chứng minh rằng một event thuộc nhóm bắt buộc đã tới SIEM với các trường cần cho rule.

### 3.2. Lỗi độc lập và lỗi lan truyền

Giả sử nguồn tạo event đúng nhưng parser làm mất **resource_id**. Rule dựa vào resource_id sẽ không khớp; đồng thời dashboard coverage có thể tính sai khi chỉ đếm tổng số event. Vì vậy, **data quality** là điều kiện tiền đề của detection quality. Kiểm chứng cần đi theo cùng một event hoặc một nhóm event có marker, từ nguồn đến kết quả.

Sơ đồ phân loại kết quả kiểm chứng:

~~~mermaid
flowchart TD
    T["Kịch bản kiểm thử hợp lệ"] --> S{"Nguồn phát sự kiện cần thiết?"}
    S -- "Không" --> BS1["Blind spot: sensor / logging"]
    S -- "Có" --> P{"Sự kiện đến nơi phân tích đủ field?"}
    P -- "Không" --> BS2["Blind spot: pipeline / parser"]
    P -- "Có" --> R{"Rule chạy và khớp điều kiện?"}
    R -- "Không" --> BS3["Blind spot: analytic / deployment"]
    R -- "Có" --> Q{"Alert đến người nhận đúng hạn?"}
    Q -- "Không" --> BS4["Blind spot: routing / operation"]
    Q -- "Có" --> V["Có bằng chứng end-to-end trong phạm vi test"]
~~~

Sơ đồ giúp xác định **điểm đứt đầu tiên**, nhưng khi điều tra nên kiểm tra cả các chặng sau vì có thể có nhiều lỗi đồng thời.

## 4. Phân loại detection blind spot theo nguyên nhân

| Nhóm | Ví dụ | Dấu hiệu nhận biết | Hướng xử lý |
|---|---|---|---|
| **Asset inventory** | Một cloud account hoặc máy chủ mới chưa được onboard | Tài sản có thật nhưng không có telemetry owner | Tự phát hiện asset, đối soát phạm vi và chủ sở hữu |
| **Sensor coverage** | EDR chưa chạy ở nhóm endpoint; audit bị tắt | Missing source, agent health fail | Triển khai sensor, bật đúng nguồn và kiểm thử |
| **Event coverage** | Chỉ thu management event, thiếu nhóm data event được yêu cầu | Không có loại sự kiện phù hợp dù nguồn hoạt động | Xác định sự kiện bắt buộc và cấu hình thu đúng |
| **Field fidelity** | Actor/resource/outcome mất khi parse | Event count vẫn tăng, field coverage giảm | Sửa parser/schema và test dữ liệu mẫu |
| **Pipeline reliability** | Queue đầy, mất batch, ingest lag lớn | Drop counter, gap, backlog | Buffer/ack/retry, dead-letter và cảnh báo |
| **Time/correlation** | Đồng hồ lệch; principal mapping sai | Chuỗi tương quan khó giải thích | Timestamp đa nguồn, correlation ID, kiểm thử enrichment |
| **Detection analytic** | Rule quá hẹp, sai ngưỡng hoặc chỉ khớp biến thể cũ | Log có nhưng rule không khớp test | Sửa hypothesis, analytic và regression test |
| **Rule deployment** | Rule chỉ có trong repo, chưa bật production | Không thấy rule ID/version tại engine | Gating triển khai, inventory rule và kiểm tra runtime |
| **Suppression/allowlist** | Loại trừ cả tenant hoặc role quá rộng | Log có hit nhưng không tạo alert | Thu hẹp ngoại lệ, có owner, ngày hết hạn |
| **Alert routing** | Alert gửi sai queue hoặc thiếu ca trực | Có alert trong SIEM nhưng không có case nhận | Test delivery, mapping owner và escalation |
| **Triage/response** | Alert đúng bị tự đóng như benign | Case đóng không đủ bằng chứng | Playbook, training, QA triage và review mẫu |
| **Governance** | Không có ai chịu trách nhiệm kịch bản rủi ro | Blind spot tồn tại lâu, không có quyết định | Sổ đăng ký gap, SLA, accepted-risk có hạn |

Một finding về detection blind spot cần chỉ ra **hành vi dự kiến, phạm vi tài sản, mắt xích lỗi và chứng cứ**, thay vì ghi chung "SOC chưa phát hiện được".

## 5. Lập bản đồ threat-led detection coverage

### 5.1. Bắt đầu từ kịch bản đe dọa

Không nên bắt đầu bằng việc đếm tất cả rule đã có và coi đó là mức bao phủ. Hãy xác định các tình huống ảnh hưởng mục tiêu bảo mật của hệ thống: chiếm quyền quản trị, lạm dụng danh tính workload, truy cập dữ liệu trái phép, thay đổi cấu hình audit, di chuyển ngang hoặc đánh cắp thông tin.

Một kịch bản được mô tả bằng:

1. **Tài sản và giá trị:** hệ thống, dữ liệu, quyền và mức độ trọng yếu.
2. **Tác nhân và giả định:** loại quyền ban đầu, vị trí truy cập, điều kiện hệ thống.
3. **Hành vi quan tâm:** thao tác hoặc chuỗi thao tác có thể quan sát trong thực tế.
4. **Tín hiệu dự kiến:** nguồn log, trường, giá trị, liên kết và thời gian.
5. **Phân tích phát hiện:** điều kiện rule, baseline hoặc tương quan đa nguồn.
6. **Hành động:** alert, owner, playbook, ngưỡng phản ứng.
7. **Phép kiểm:** cách tạo mẫu sự kiện hoặc mô phỏng an toàn để xác minh toàn chuỗi.

Có thể sử dụng **MITRE ATT&CK** làm ngôn ngữ chung để thảo luận chiến thuật, kỹ thuật và các hành vi. Tuy nhiên, việc gắn một rule với tên technique **không tự chứng minh rule phát hiện được technique đó**. Một kỹ thuật có nhiều biến thể, điều kiện và nguồn dữ liệu; detection coverage phải dựa trên test cụ thể.

### 5.2. Ma trận bao phủ tham khảo

| Scenario | Dữ liệu tối thiểu | Phát hiện kỳ vọng | Kiểm thử hiệu lực | Kết luận ví dụ |
|---|---|---|---|---|
| Tạo hoặc sửa vai trò đặc quyền trên cloud | Cloud audit event, actor, action, role/resource, environment | Cảnh báo thay quyền nhạy cảm ngoài quy trình | Thao tác cấu hình trong account test được phép | **PASS** với phạm vi account test |
| Truy cập bất thường vào kho dữ liệu | Access/audit log, identity, object, outcome, volume | Cảnh báo hành vi vượt baseline hoặc truy cập cấm | Synthetic events + kiểm tra rule và pipeline | **NOT_TESTED** với production |
| Tắt audit logging | Control-plane event và cấu hình hiện thời | Cảnh báo thay đổi log config, kiểm tra mất heartbeat | Mô phỏng đổi cấu hình trong môi trường thử | **FAIL** nếu không có alert |
| Container mở shell bất thường | Runtime process telemetry, pod/container identity | Cảnh báo hành vi trong workload nhạy cảm | Sự kiện test có đánh dấu, đã phê duyệt | **INCONCLUSIVE** nếu sensor không hỗ trợ node đó |
| Service account dùng quyền mới | Kubernetes audit/RBAC change và identity mapping | Cảnh báo role/binding thay đổi ngoài baseline | Tạo/bỏ RoleBinding an toàn ở namespace test | **PASS_WITH_SCOPE** |

Các trạng thái này là minh họa. Phải định nghĩa chung **PASS, FAIL, NOT_TESTED, INCONCLUSIVE, NOT_APPLICABLE** và accepted risk. Không gộp NOT_TESTED thành PASS, cũng không coi một test PASS là bằng chứng bao phủ tất cả asset hoặc biến thể hành vi.

### 5.3. Thực thể cần phủ, không chỉ kỹ thuật

Đơn vị kiểm tra có thể là **scenario × asset group × environment × data-source variant × rule version**, tùy mục tiêu. Chẳng hạn:

- Một detection trên AWS không mặc nhiên áp dụng cho Azure hoặc Google Cloud.
- Một rule ghi nhận command trên VM không mặc nhiên hoạt động với serverless.
- Rule cùng logic nhưng parser của hai môi trường khác nhau có thể cho kết quả khác.
- Bài test trên staging với quyền hạn chế không tự xác nhận hành vi ở production.

Một phép đo coverage có giá trị phải công bố **mẫu số** của những đơn vị cần được kiểm chứng; loại trừ tài sản/nguồn không quan sát được một cách tùy tiện sẽ tạo bức tranh đẹp giả.

## 6. Định nghĩa detection hypothesis có thể kiểm thử

Một detection hypothesis là phát biểu cụ thể về tín hiệu và logic cần có khi hành vi rủi ro xảy ra. Nó nên tránh khẳng định chung như "phát hiện privilege escalation".

Ví dụ:

> Khi một principal có quyền phù hợp thay đổi binding của vai trò đặc quyền ngoài thay đổi đã phê duyệt trong môi trường production, hệ thống phải ghi event quản trị đủ actor, resource và outcome, áp rule theo scope, tạo alert mang đúng định danh tổ chức trong cửa sổ thời gian đã xác định.

Phát biểu trên có thể tách thành điều kiện kiểm tra nguồn, parser, rule và vận hành. Một mô hình metadata tham khảo:

~~~yaml
detection_id: "DET-PRIV-CHANGE-001"
scenario: "Privileged role binding changed"
risk_owner: "identity-security"
environments:
  - "production"
assets_in_scope: "cloud-accounts-managed"
required_data:
  source: "cloud-control-plane-audit"
  fields:
    - "event_time"
    - "actor_id"
    - "action"
    - "target_role"
    - "outcome"
  max_ingest_lag_seconds: 180
analytic:
  condition: "privileged_role_change AND outside_approved_change"
  rule_version: "v4"
alert:
  owner: "soc-identity"
  severity_policy: "risk-based"
  max_delivery_seconds: 300
validation:
  positive_case: "approved-test-role-binding-change"
  negative_case: "ordinary-nonprivileged-change"
  evidence_required:
    - "source_event"
    - "normalized_event"
    - "rule_evaluation"
    - "alert_delivery"
    - "triage_record"
~~~

Đây là **schema minh họa**, không phải cấu hình trực tiếp có thể chạy trên SIEM nào. Ngưỡng 180/300 giây cũng chỉ là ví dụ; cần quyết định theo mức rủi ro và năng lực hệ thống.

### 6.1. Điều kiện đạt và điều kiện không đạt

Đối với một test case:

- **PASS:** nguồn và pipeline cung cấp đủ dữ liệu, rule nhận diện đúng trường hợp, alert đi đến đúng người/queue theo thời hạn trong phạm vi phép thử, có bằng chứng triage nếu đó là phần của control.
- **FAIL:** một điều kiện bắt buộc bị vi phạm và có đủ chứng cứ xác định lỗi.
- **INCONCLUSIVE:** bài thử không chạy đến nơi, sensor không thu đủ dữ liệu để đánh giá, hoặc bằng chứng mất nên chưa xác định nguyên nhân.
- **NOT_TESTED:** chưa có kiểm thử thực tế trong phạm vi.
- **NOT_APPLICABLE:** được xác nhận bằng lý do và phạm vi, ví dụ loại công nghệ không tồn tại.
- **ACCEPTED_RISK:** điểm thiếu đã được cấp có thẩm quyền chấp thuận tạm thời cùng biện pháp bù trừ; không đồng nghĩa kỹ thuật đã đạt.

Một kết quả **PASS_WITH_SCOPE** có thể dùng như nhãn giao tiếp, nhưng luôn phải nêu rõ phạm vi và bản chất kiểm chứng trong dữ liệu đánh giá.

## 7. Các kiểu phát hiện thường bỏ sót

### 7.1. Chỉ có rule đơn sự kiện

Một hành vi có thể không đáng ngờ khi nhìn từng event nhưng đáng ngờ khi ghép thành chuỗi: tạo credential mới, dùng credential đó truy cập dịch vụ ít dùng, rồi thay đổi quyền. Rule đơn sự kiện thiếu correlation và ngữ cảnh có thể tạo điểm mù. Tuy nhiên, correlation nhiều bước phải xét việc mất event, lệch thời gian, retry và alias của danh tính.

### 7.2. Detection phụ thuộc địa chỉ hoặc tên cố định

Các rule quá phụ thuộc một địa chỉ IP, tiến trình, tên file hoặc tenant có thể thất bại khi hệ thống đổi cấu trúc. Nên bám hành vi/ngữ nghĩa của sự kiện, kết hợp context và baseline. Hạn chế phụ thuộc string dễ biến đổi; nếu dùng thì phải có lịch cập nhật và regression test.

### 7.3. Không bao phủ đường quản trị ngoài quy trình

Nếu tổ chức chỉ ghi thay đổi từ CI/CD mà bỏ qua thao tác qua console/API của nhà cung cấp, hành động ngoài pipeline có thể không xuất hiện trong detection. Cần kiểm tra cả hành động của người, workload identity, automation và quyền cấp tổ chức.

### 7.4. Không giám sát chính hệ thống giám sát

Tắt nguồn audit, hạ mức logging, đổi sink, thay index, dừng collector, xóa rule hoặc tạo suppressions là những hành vi ảnh hưởng năng lực phát hiện. **Detection-system health** và **control-plane audit** của chính pipeline là control quan trọng, vì attacker thường hưởng lợi khi khả năng quan sát suy giảm.

### 7.5. Nhìn thấy "agent healthy" nhưng không thấy event cần thiết

Heartbeat hoặc trạng thái agent running chứng minh một thành phần còn sống, không chứng minh mọi loại event đang được thu. Cần **synthetic canary** hoặc test event theo loại sự kiện trọng yếu để xác minh đủ trường và end-to-end delivery.

### 7.6. Source context bị biến đổi sau enrichment

Một collector có thể thay tên principal, bỏ region, chuẩn hóa sai resource ID hoặc gắn nhầm tenant. Rule sai mà không có lỗi cú pháp. Vì vậy, phải kiểm tra **field fidelity** trên dữ liệu thô và dữ liệu đã chuẩn hóa, nhất là các trường tham gia correlation/threshold.

## 8. Phát hiện blind spot bằng kiểm tra kỹ thuật

### 8.1. Kiểm kê asset và nguồn dữ liệu

Bắt đầu từ inventory độc lập với SIEM, chẳng hạn hệ thống quản lý cloud account, danh sách cluster, endpoint management và service catalog. Đối chiếu từng asset với nguồn log bắt buộc:

| Kiểm tra | Câu hỏi | Bằng chứng |
|---|---|---|
| Phạm vi asset | Có asset mới hoặc asset ngoài quản trị không? | Inventory từ API và service catalog có timestamp |
| Onboarding | Asset có owner, log profile và pipeline destination không? | Hồ sơ cấu hình và bản ghi phê duyệt |
| Source health | Agent/audit source đang hoạt động trên tài sản không? | Health, heartbeat, last-seen |
| Event coverage | Loại sự kiện bắt buộc có được phát sinh và thu không? | Test event, source sample, target sample |
| Field coverage | Trường cần cho rule có mặt và đúng kiểu không? | Parser schema, tỷ lệ missing/null, sample đối chiếu |
| Pipeline reliability | Có drop, retry, backlog, mất segment không? | Metrics queue, ingest delay, missing sequence |
| Rule coverage | Có rule triển khai cho scenario và scope không? | Rule inventory, version, enablement |
| Alert delivery | Alert đi đúng queue và có ack xử lý không? | Alert, ticket, on-call route, SLA |

**Mẫu số phải dựa trên phạm vi cần quan sát**, không chỉ các asset vốn đã gửi log. Nếu 10 máy mới không có trong bảng nguồn SIEM, đo coverage từ bảng đó sẽ không thể phát hiện phần thiếu.

### 8.2. Theo dõi data freshness và silent failure

Một rule có thể hoạt động bình thường nhưng source đã im lặng. Theo dõi:

- **last_event_at** theo source, loại sự kiện và môi trường.
- **expected heartbeat** so với heartbeat nhận được.
- **ingest lag** giữa event time và ingest time (kèm kiểm soát clock drift).
- **drop/error rate** của agent, parser, broker và detection engine.
- **field null rate** của trường bắt buộc.
- **số lượng event tương đối với mức nền** và deployment/traffic changes.
- **last rule evaluation** và phiên bản rule đang chạy.
- **số alert không được route hoặc không nhận ack**.

Không nên đặt một ngưỡng "nguồn im lặng 5 phút" cho mọi source. Với nguồn event hiếm, cần heartbeat hoặc synthetic event độc lập. Với nguồn traffic cao, giảm bất thường dù chưa về zero đã có thể là dấu hiệu quan trọng.

### 8.3. Synthetic telemetry và canary

Synthetic telemetry là sự kiện thử **được phê duyệt và có nhãn rõ ràng**, tạo theo chu kỳ nhằm đo luồng từ nguồn tới nơi phân tích. Nó có thể là một lần đăng nhập test, yêu cầu API giả lập hoặc thay đổi cấu hình vô hại trong sandbox.

Canary tốt phải có:

1. ID/marker duy nhất cho từng lần thử.
2. Source và scope chính xác, không làm lộ secret.
3. Event class, các trường bắt buộc và kỳ vọng rõ ràng.
4. Thời hạn đến pipeline và tạo alert.
5. Kết quả so khớp từ nguồn đến SIEM/case.
6. Kết quả FAIL/INCONCLUSIVE có người xử lý.
7. Giới hạn: canary chỉ chứng minh con đường và hành vi được kiểm, không phải toàn bộ các trường hợp.

Nên kiểm tra cả **positive test** (đáng phát hiện) và **negative test** (hành vi hợp lệ không nên tạo alert) để không tối ưu theo một chiều chỉ đẩy số alert lên.

## 9. Quản lý detection-as-code và kiểm thử hồi quy

Detection-as-code biểu diễn điều kiện phát hiện, metadata, nguồn dữ liệu cần thiết, ngoại lệ, test case và owner trong hệ thống có version control. Việc này hỗ trợ review, kiểm thử, triển khai và rollback, nhưng chỉ có file trong repository chưa đủ: cần xác minh rule đã được nạp và chạy trong hệ thống thật.

### 9.1. Vòng đời rule

~~~mermaid
flowchart LR
    T["Threat hypothesis"] --> D["Rule + telemetry contract"]
    D --> UT["Unit test với dữ liệu mẫu"]
    UT --> IT["Integration test pipeline"]
    IT --> RV["Review + risk approval"]
    RV --> DEP["Deploy + runtime inventory"]
    DEP --> MON["Monitor quality + drift"]
    MON --> REG["Regression test"]
    REG --> D
~~~

**Unit test** kiểm tra logic với bộ sự kiện được kiểm soát. **Integration test** kiểm tra parsing, storage, scheduler, query, routing và tình trạng thật của pipeline. **End-to-end exercise** kiểm tra tín hiệu từ asset/sensor đến quy trình xử lý. Các lớp kiểm thử này bổ sung cho nhau.

### 9.2. Bộ dữ liệu test có tính đại diện

Một bộ test nên có:

- Trường hợp đúng điều kiện phát hiện và có đầy đủ field.
- Biến thể hợp lệ của event name, principal, resource, region hoặc hệ điều hành.
- Trường hợp âm: thay đổi được phê duyệt hoặc hành vi giống bề ngoài nhưng không mang rủi ro.
- Dữ liệu nhiễu, thiếu trường, sai kiểu, thứ tự đảo, timestamp trễ, duplicate, replay.
- Dữ liệu nhiều tenant/môi trường để phát hiện correlation xuyên ranh giới sai.
- Lịch sử phát hiện lỗi trước đây để ngăn lỗi tái phát sau chỉnh sửa rule.

Sử dụng dữ liệu đã khử nhạy cảm hoặc tổng hợp; tránh đẩy credential, PII hoặc sự kiện thật không cần thiết vào test repository.

### 9.3. Kiểm soát suppression và exception

Suppression có thể cần để hạn chế cảnh báo nhiễu, nhưng là nguồn blind spot phổ biến khi đặt quá rộng. Mỗi ngoại lệ nên có:

| Trường | Ý nghĩa |
|---|---|
| exception_id, rule_id | Xác định chính xác rule bị ảnh hưởng |
| scope | Định danh host, service, account, principal hoặc resource |
| reason | Vì sao hành vi được phép hoặc được chấp nhận tạm thời |
| owner, approver | Người đề xuất, chịu trách nhiệm, phê duyệt |
| created_at, expires_at | Thời điểm hiệu lực và kết thúc |
| expected_signal | Dữ liệu vẫn cần thu để đánh giá hành vi trong scope |
| compensating_control | Kiểm soát bổ sung trong kỳ ngoại lệ |
| review_evidence | Kết quả xem lại và kiểm tra ảnh hưởng tới coverage |

Ngoại lệ hết hạn cần được phát hiện tự động; một exception không có owner hoặc không biết còn áp dụng cho asset nào là finding quản trị, kể cả khi rule vẫn hoạt động tốt ngoài phạm vi đó.

## 10. Baseline control cho Detection blind spot assurance

Một chương trình assurance cần tách **control** (yêu cầu kiểm soát) khỏi **test** (phép xác minh) và **evidence** (bằng chứng). Baseline dưới đây là khung tham khảo; tổ chức phải quyết định phạm vi, tiêu chí đạt và mức rủi ro theo hệ thống đang bảo vệ.

| ID | Control | Điều kiện kỳ vọng | Phép kiểm và bằng chứng |
|---|---|---|---|
| **DBS-01** | Asset và source inventory | Mọi asset quan trọng có owner, log profile và nguồn phát hiện bắt buộc | Đối soát inventory cloud/host/cluster với coverage registry và SIEM sources |
| **DBS-02** | Telemetry onboarding | Asset mới được kết nối nguồn log và kiểm tra trước khi đưa vào hoạt động | Quy trình tạo asset, kết quả test event, thời gian onboarding |
| **DBS-03** | Event/data coverage | Những event class quan trọng có mặt và đủ trường trong pipeline | Source sample, normalized sample, field completeness và test synthetic |
| **DBS-04** | Pipeline reliability | Có đo ingest lag, retry, drop, parsing failure và phát cảnh báo khi sai ngưỡng | Metrics, controlled fault test, alert/ticket |
| **DBS-05** | Sensor tamper/health | Mất sensor, tắt audit, đổi sink hoặc tắt collector được nhận biết | Health/heartbeat, audit thay cấu hình, controlled test |
| **DBS-06** | Threat-based mapping | Kịch bản trọng yếu có hypothesis, tín hiệu, analytic, owner và mức rủi ro | Scenario registry, detection mapping có phạm vi |
| **DBS-07** | Rule deployment | Rule được review, version và chứng minh đã bật đúng môi trường | Repository revision, SIEM runtime rule ID/version/status |
| **DBS-08** | Analytic validation | Rule có positive/negative test và kết quả với dữ liệu đại diện | Fixture, kết quả unit/integration test, change record |
| **DBS-09** | End-to-end exercise | Tín hiệu từ source đi đến alert/case trong cửa sổ quy định | Source event, ingest ID, rule hit, alert ID, route và acknowledgment |
| **DBS-10** | Exception governance | Suppression/allowlist có scope, owner, phê duyệt và hạn sử dụng | Exception inventory, expiry checks, test coverage ngoài scope |
| **DBS-11** | Detection system monitoring | Engine, parser, index, scheduler và alert router được giám sát | Heartbeat, last-run, lag, parser errors, routing test |
| **DBS-12** | Analyst response readiness | Alert trọng yếu có owner, playbook và được triage trong thời hạn | Alert/case sample, on-call route, tabletop result |
| **DBS-13** | Coverage measurement | KPI dùng mẫu số từ phạm vi rủi ro và phân biệt trạng thái chưa thử | Ma trận coverage, cách tính, nguồn dữ liệu và snapshot |
| **DBS-14** | Blind spot remediation | Gap có severity, owner, kế hoạch, hạn và retest | Finding/ticket, bằng chứng sửa và đánh giá lại |
| **DBS-15** | Continual change assurance | Asset/schema/rule/policy thay đổi kéo theo kiểm tra liên quan | Trigger CI/CD, deploy event, regression/recertification result |

### 10.1. Kiểm soát phòng ngừa, phát hiện và khắc phục

- **Phòng ngừa:** pipeline cấp phát asset đòi hỏi bật audit, onboarding source và xác minh test event; chính sách quản trị hạn chế tắt log.
- **Phát hiện:** thông báo khi nguồn im lặng, mất field, pipeline drop, rule không chạy hoặc cảnh báo không đến queue.
- **Khắc phục:** sửa collector, parser, analytic, routing hoặc quyền; backfill dữ liệu nếu còn và có căn cứ; lưu lại kết quả retest.
- **Bù trừ:** giám sát từ nguồn độc lập, tăng review thủ công, kiểm soát quyền mạnh hơn hoặc hạn chế chức năng trong kỳ chưa có detection.

Chỉ có control phòng ngừa không đủ để khẳng định detection efficacy: cần phép kiểm thực tế xem sự kiện rủi ro có được nhận diện và xử lý.

### 10.2. Bằng chứng mạnh hơn ảnh chụp dashboard

Bộ bằng chứng nên cho phép người khác tái kiểm tra đường đi của cùng một event:

1. **Nguồn:** action, source ID, asset ID, timestamp và marker của sự kiện thử.
2. **Thu nhận:** event ID hoặc trace ở collector, receiver, index/stream.
3. **Parser:** các trường gốc và normalized field quan trọng.
4. **Rule:** rule ID/version, execution context, match/result, thời gian chạy.
5. **Alert:** alert ID, severity, destination, thời gian gửi và thời gian nhận.
6. **Triage:** case/ticket, người hoặc automation xử lý, kết luận và mốc thời gian.
7. **Kiểm chứng:** tool/version, test run, trạng thái, phạm vi, giới hạn và người đánh giá.

Một dashboard toàn màu xanh có thể giấu những nguồn không có trong mẫu số hoặc những rule chỉ chạy trên tập dữ liệu sai. Bằng chứng phải chỉ ra được **nguồn và dữ liệu dự kiến**, không chỉ trạng thái thành phần.

## 11. Thực hành: phát hiện thiếu telemetry trên một nhóm asset

Giả sử hệ thống có danh sách cloud account production được quản lý, còn SIEM nhận sự kiện từ các account đó. Nhiệm vụ assurance là tìm account chưa ghi nhận **bất kỳ audit heartbeat hoặc sự kiện xác nhận nào** trong khoảng kiểm tra. Cách tiếp cận này hỗ trợ tìm nguồn im lặng; nó chưa đủ để kết luận mọi hành vi quản trị đều đã được ghi.

### 11.1. Thiết lập điều kiện

Ví dụ yêu cầu:

- Phạm vi gồm mọi cloud account production đang hoạt động.
- Có ít nhất một loại nguồn audit được yêu cầu cho mỗi account.
- Nếu nguồn không phát dữ liệu trong thời hạn cho phép, phải có heartbeat độc lập hoặc synthetic event.
- Mọi gap phải được điều tra theo owner và ghi rõ khoảng thời gian.

Một bản ghi inventory có thể dùng:

~~~yaml
asset_id: "cloud-account-111122223333"
environment: "production"
business_service: "payments"
asset_owner: "payments-platform"
expected_telemetry:
  - "cloud-admin-audit"
  - "identity-access-audit"
pipeline_destination: "siem-production"
detection_owner: "soc-cloud"
onboarded_at: "2026-11-27T03:00:00Z"
last_validation: "2026-11-28T07:00:00Z"
~~~

Các ID và thời gian ở đây là minh họa.

### 11.2. Tìm asset không xuất hiện trong telemetry

Sau đây là **SQL giả lập theo mô hình dữ liệu ví dụ**. Nó cần được điều chỉnh theo engine, schema và khung thời gian thực tế; không phải câu lệnh sẵn chạy cho mọi SIEM.

~~~sql
WITH required_sources AS (
  SELECT asset_id, telemetry_type
  FROM asset_telemetry_requirements
  WHERE environment = 'production'
    AND lifecycle_status = 'active'
),
recent_telemetry AS (
  SELECT asset_id, telemetry_type, MAX(ingest_time) AS last_seen
  FROM siem_events
  WHERE ingest_time >= :window_start
    AND ingest_time < :window_end
  GROUP BY asset_id, telemetry_type
)
SELECT r.asset_id, r.telemetry_type, t.last_seen
FROM required_sources AS r
LEFT JOIN recent_telemetry AS t
  ON r.asset_id = t.asset_id
 AND r.telemetry_type = t.telemetry_type
WHERE t.last_seen IS NULL;
~~~

**Điểm quan trọng:** điều kiện chọn được account không có event trong cửa sổ, nhưng một nguồn có tần suất phát sự kiện rất thấp có thể im lặng bình thường. Cần có heartbeat/canary riêng hoặc điều kiện thống kê phù hợp trước khi kết luận source lỗi. Cũng cần đối chiếu clock và ingest lag để tránh nhầm event đến muộn.

### 11.3. Phân biệt nguồn thiếu với parser lỗi

Giả sử hệ thống báo không thấy event thay đổi IAM:

- Nếu **nguồn không có event** trong log gốc dù đã thực hiện thao tác test, có thể là cấu hình audit, phân quyền, loại sự kiện hoặc giả định về event.
- Nếu **collector có event** nhưng SIEM không nhận, kiểm tra queue, filter, network, dead-letter, event drop và quyền ingestion.
- Nếu **SIEM có bản raw** nhưng rule không khớp, so sánh parser output và field yêu cầu của analytic.
- Nếu **rule hit** nhưng không tạo case, xem suppression, threshold, scheduling và alert routing.
- Nếu **case được tạo** nhưng không có phản hồi, xem ownership, on-call, playbook và case workflow.

Với mỗi nhánh, phải lưu được event/counter/log/case để chứng minh nguyên nhân, không chỉ suy đoán.

## 12. Bài thực hành end-to-end: thay đổi một quyền thử nghiệm

Một bài thử an toàn có thể dùng **tài nguyên sandbox đã phê duyệt** để kiểm tra detection cảnh báo thay đổi vai trò. Không cần thực hiện tấn công hoặc thao tác nguy hiểm trên dữ liệu thật. Ví dụ, đội hạ tầng tạo một vai trò thử nghiệm có tên được gắn nhãn rõ và thay đổi binding theo quy trình kiểm thử.

### 12.1. Kịch bản và kỳ vọng

**Mục tiêu:** chứng minh một thay đổi quyền thuộc loại được giám sát sẽ phát event đến hệ thống phát hiện và tạo alert được định tuyến đúng trong cửa sổ đánh giá.

Các mốc ví dụ:

| Mốc | Sự kiện mong đợi | Dấu vết |
|---|---|---|
| T0 | Bài thử bắt đầu, test ID duy nhất được đăng ký | Test run và approval |
| T1 | Thao tác thay quyền thử nghiệm thực hiện thành công | Cloud audit event với actor/resource/action |
| T2 | Collector/stream nhận sự kiện | Ingest ID, receive/ingest time |
| T3 | Parser chuẩn hóa đầy đủ trường | Raw/normalized sample và parser version |
| T4 | Rule chạy và khớp điều kiện test | Rule ID/version, evaluation result |
| T5 | Alert tới đúng queue | Alert ID và delivery timestamp |
| T6 | Người trực nhận/triage theo playbook | Case ID, acknowledgment, hành động |

Nếu event T1 không có trong nguồn gốc, việc chỉ nhìn không thấy T5 không cho biết lỗi nằm ở đâu. Cần truy vết từng mốc theo marker.

### 12.2. Tiêu chí kiểm thử

- **Positive case:** thao tác thử thỏa điều kiện rule phải được nhận dạng và tạo alert.
- **Negative case:** thao tác thông thường không thỏa điều kiện không nên tạo alert cùng loại.
- **Coverage test:** chạy ở các biến thể môi trường/sensor/parser được coi là tương đương; phải ghi rõ biến thể chưa thử.
- **Timing test:** đo trễ của T1 → T2, T2 → T4, T4 → T5 và T5 → T6 theo SLA.
- **Operational test:** đúng owner nhận được case và có thể truy xuất các field cần triage.
- **Failure injection có kiểm soát:** trong test environment, làm mất một chặng dữ liệu hoặc tạm dừng bản sao collector để kiểm tra health alert và khôi phục.

Bài thử trên sandbox cung cấp bằng chứng hữu ích về chuỗi phát hiện, nhưng chưa chứng minh mọi account production sẽ behave tương tự. Muốn mở rộng kết luận phải kiểm tra tính tương đồng của cấu hình, policy, nguồn log và vận hành.

### 12.3. Ví dụ hồ sơ kết quả

~~~yaml
test_id: "DE-BS-2026-11-28-014"
scenario_id: "PRIVILEGE-CHANGE"
environment: "staging"
asset_id: "cloud-account-111122223333"
test_marker: "assurance-test-014"
run_started_at: "2026-11-28T07:20:00Z"
required_detection_id: "DET-PRIV-CHANGE-001"
rule_version: "v4"
expected:
  source_event: true
  required_fields: ["actor_id", "action", "target_role", "outcome"]
  alert_destination: "soc-identity"
  max_delivery_seconds: 300
observed:
  source_event_reference: "evidence/run014/source.json"
  normalized_reference: "evidence/run014/normalized.json"
  rule_evaluation_reference: "evidence/run014/rule-evaluation.json"
  alert_id: "alert-example-427"
  case_id: "case-example-588"
  alert_delivered_seconds: 87
result: "PASS_WITH_SCOPE"
limitations:
  - "Chỉ xác minh kịch bản và môi trường staging đã nêu"
  - "Không suy rộng sang mọi biến thể privilege escalation"
assessor: "detection-assurance-team"
~~~

Đây là hồ sơ minh họa. Các đường dẫn/ID và số đo chỉ có giá trị ví dụ, chưa phải kết quả đánh giá thực tế.

## 13. Hai tình huống có điểm mù khác nhau

### 13.1. Tình huống A — Cloud account bị bỏ khỏi danh sách thu log

Một tổ chức quản lý 24 cloud account. Bộ phận phát triển tạo thêm một account production để tách workload nhạy cảm. Account được triển khai ứng dụng nhưng không thuộc quy trình onboarding logging tập trung. SOC thấy dashboard của 24 account cũ vẫn bình thường.

**Điều tra:** inventory cấp tổ chức ghi 25 account, nhưng SIEM source inventory chỉ có 24. Một event thay đổi IAM tại account mới tồn tại ở nguồn theo cấu hình kiểm tra tại thời điểm đánh giá, nhưng không có trong hệ thống nhận log tập trung.

**Điểm mù:** asset onboarding và telemetry coverage, không nhất thiết nằm ở logic detection.

**Khắc phục:**

1. Ghi finding cho account mới, kịch bản ảnh hưởng và cửa sổ không có khả năng quan sát.
2. Đưa account vào hệ thống thu audit đúng phạm vi.
3. Tạo event thử hợp lệ; theo dõi đủ source → collector → parser → rule → alert → case.
4. Thêm kiểm tra đối soát tự động giữa organization asset list và inventory nguồn log.
5. Đánh giá khả năng backfill những event đã tồn tại tại nguồn, công bố phần lịch sử không thể khôi phục.
6. Retest sau sửa và ghi độ bao phủ vào KPI.

**Bài học:** dashboard SIEM chỉ đo những gì nó biết. Assurance cần **mẫu số asset độc lập**.

### 13.2. Tình huống B — Rule có dữ liệu nhưng bị exception che khuất

Một nhóm vận hành tạo allowlist cho một principal dịch vụ vì hệ thống triển khai tự động sinh nhiều cảnh báo. Về sau principal này có quyền quản trị rộng hơn, nhưng exception cũ vẫn loại toàn bộ sự kiện của principal đó. Một thay đổi quyền nguy hiểm được ghi và parse đầy đủ, rule cũng khớp nếu không có exception.

**Điều tra:** raw event, normalized event và rule dry-run đều có dấu vết; trạng thái production không sinh alert do exception vẫn được áp.

**Điểm mù:** suppression governance và thiếu đánh giá lại sau thay đổi quyền.

**Khắc phục:**

1. Ghi chính xác principal, điều kiện suppression và rule bị ảnh hưởng.
2. Thay ngoại lệ rộng bằng điều kiện hẹp theo hành động/tài nguyên/quy trình đã phê duyệt.
3. Bổ sung thời hạn, owner, review sau khi quyền hoặc vai trò thay đổi.
4. Chạy test dương trên hành vi rủi ro và test âm với hoạt động tự động hợp lệ.
5. Đưa việc thêm/sửa exception vào review và audit định kỳ.
6. Kiểm tra lại trường hợp phát hiện trước đây bị suppress để đánh giá tác động, trong giới hạn dữ liệu lưu còn có.

**Bài học:** một rule đúng và một nguồn log đầy đủ vẫn có thể không tạo cảnh báo nếu tầng chính sách vận hành che mất tín hiệu.

## 14. Ưu tiên xử lý blind spot theo rủi ro

Điểm mù phát hiện phải được đánh giá tương quan với mức quan trọng của tài sản, khả năng xảy ra hành vi đe dọa và thời gian tổ chức không thể nhận biết/ứng phó.

Một cách ưu tiên mang tính định tính:

| Yếu tố | Câu hỏi |
|---|---|
| Criticality | Tài sản hoặc dữ liệu bị ảnh hưởng quan trọng đến đâu? |
| Exposure | Đường tấn công có thể tiếp cận từ Internet, đối tác, nội bộ hay workload đã bị xâm phạm không? |
| Threat relevance | Kịch bản có gắn với rủi ro, sự cố hoặc threat intelligence đáng quan tâm không? |
| Breadth | Có bao nhiêu account, workload, đội nghiệp vụ hoặc môi trường chịu ảnh hưởng? |
| Duration | Điểm mù tồn tại bao lâu và có còn hoạt động không? |
| Other controls | Có kiểm soát phòng ngừa hoặc nguồn giám sát độc lập giảm tác động không? |
| Recoverability | Có thể backfill log hoặc điều tra từ nguồn khác không? |
| Response requirement | Tổ chức có nghĩa vụ phát hiện trong một thời gian nhất định không? |

Ví dụ, thiếu audit đối với thao tác quản trị của một account chứa dữ liệu nhạy cảm đang kết nối Internet thường đáng ưu tiên hơn thiếu một sự kiện debug ít tác động ở sandbox. Tuy nhiên, severity vẫn cần căn cứ vào phân tích rủi ro và bối cảnh thật; không nên áp nhãn critical cho tất cả missing logs.

### 14.1. Hồ sơ finding tham khảo

~~~yaml
finding_id: "DBS-FIND-2026-041"
control_id: "DBS-03"
title: "Missing privileged-change events for a production cloud account"
affected_assets:
  - "cloud-account-111122223333"
affected_scenarios:
  - "PRIVILEGE-CHANGE"
first_observed_at: "2026-11-27T09:15:00Z"
observed_at: "2026-11-28T07:30:00Z"
risk_level: "high"
risk_rationale: "Privileged changes cannot be monitored through the central pipeline"
evidence:
  - "evidence/find041/asset-inventory.json"
  - "evidence/find041/source-config.json"
  - "evidence/find041/missing-siem-source.json"
owner: "platform-team"
target_fix_date: "2026-12-03"
proposed_fix: "Onboard audit feed and add provisioning gate"
compensating_controls:
  - "Temporary daily independent review of control-plane audit"
status: "OPEN"
retest_required: true
~~~

Các trường và thời gian là ví dụ. Đối với finding thực tế, nên ghi **sai lệch là gì, thiếu bao phủ từ khi nào, chứng cứ nào hỗ trợ, ai chịu trách nhiệm và khi nào retest**. Nếu không biết chính xác ngày bắt đầu điểm mù, ghi "earliest known" hoặc giới hạn khoảng thời gian; không giả định first_observed đồng nghĩa first_existed.

### 14.2. Phương án giảm rủi ro trong thời gian sửa

Nếu chưa khắc phục được ngay, có thể tăng audit từ nguồn khác, hạn chế đặc quyền, yêu cầu phê duyệt bổ sung cho thao tác nhạy cảm, tăng xác minh thủ công hoặc tạm giới hạn hành động có rủi ro. Biện pháp bù trừ phải có owner, phạm vi, bằng chứng vận hành và ngày hết hạn. Nó không làm detection chưa hoạt động tự động trở thành PASS.

## 15. Đo coverage và chất lượng detection

### 15.1. Định nghĩa mẫu số

Một định nghĩa tham khảo:

\[
\text{Verified scenario coverage}
=\frac{\text{Số đơn vị kiểm thử thuộc phạm vi đạt tất cả tiêu chí bắt buộc}}
{\text{Tổng số đơn vị kiểm thử bắt buộc thuộc phạm vi}}
\times100\%
\]

Một **đơn vị kiểm thử** phải được định nghĩa nhất quán, chẳng hạn scenario × environment × asset class × telemetry variant. Đơn vị chưa thử vẫn nằm trong mẫu số nếu nó là yêu cầu bắt buộc. Các đơn vị NOT_APPLICABLE chỉ được loại sau khi có phê duyệt phạm vi và lý do.

Ví dụ: có 20 đơn vị kiểm chứng cần thiết, 12 PASS, 3 FAIL, 4 NOT_TESTED, 1 INCONCLUSIVE. Coverage đã **chứng minh đạt** là 12/20 = **60%**. Nếu chỉ lấy 12/15 trong số test đã có kết quả thì ra 80%, nhưng con số đó bỏ qua 5 đơn vị chưa chứng minh; phải gọi là một metric khác và ghi giới hạn.

### 15.2. Một số KPI hữu ích

| Chỉ số | Cách tính/diễn giải | Điều dễ gây hiểu sai |
|---|---|---|
| **Verified scenario coverage** | Đơn vị bắt buộc đã test PASS / tổng đơn vị bắt buộc | Rule có mapping nhưng chưa test không phải PASS |
| **Telemetry source coverage** | Asset/source cần thu log đã được xác minh / tất cả asset/source cần thu log | SIEM chỉ đếm source hiện hữu sẽ bỏ sót asset mới |
| **Field completeness** | Event thuộc loại yêu cầu có đủ trường / tổng event được kiểm | Event bị drop trước parser không nằm trong mẫu số này |
| **Pipeline freshness** | Độ trễ ingest theo percentile và nhóm source | Mean có thể che tail latency hoặc source im lặng |
| **Sensor/collector health** | Nguồn có heartbeat/health đúng kỳ / tổng nguồn yêu cầu | Healthy không chứng minh event type đủ |
| **Detection test pass rate** | Test case PASS / test case thực hiện có kết quả hợp lệ | Không thay thế coverage toàn bộ trường hợp cần test |
| **False negative rate trong test** | Ca đáng phát hiện nhưng không được phát hiện / ca đáng phát hiện trong tập test | Chỉ có ý nghĩa với tập test và ground truth đã khai báo |
| **Alert delivery success** | Alert cần route đến đúng nơi và được xác nhận / alert kiểm tra | Có alert trong engine chưa chứng minh người trực nhận |
| **Time to detect** | Từ thời điểm hành vi kiểm soát đến alert usable, theo phân phối | Event time/ingest time có thể lệch; cần đo đúng mốc |
| **Time to remediate blind spots** | Từ phát hiện gap đến retest chứng minh đã sửa | Ticket Done chưa đủ |
| **Overdue exceptions** | Ngoại lệ quá hạn chưa xử lý / tổng ngoại lệ có hạn đã qua | Ngoại lệ không có hạn cần được xử lý như vấn đề quản trị |

KPI tổng có thể che nhóm rủi ro cao. Nên phân tách theo production/non-production, loại asset, nhóm kịch bản, mức criticality, nền tảng cloud và dữ liệu nhạy cảm.

### 15.3. False negative và bài toán ground truth

Trong production hiếm khi có nhãn chắc chắn cho mọi hoạt động nguy hiểm đã diễn ra. Vì vậy, **false negative rate từ một tập test** không được diễn giải thành tỷ lệ bỏ sót thật của mọi cuộc tấn công. Có thể kết hợp:

- Synthetic test và replay dataset được gắn nhãn.
- Purple-team exercise trong phạm vi được phê duyệt.
- Review sự cố thật đã có kết luận.
- Threat-hunting hypothesis và đối soát nguồn độc lập.
- Rule shadow evaluation với dữ liệu phù hợp.

Mỗi nguồn có giới hạn, thiên lệch mẫu và điều kiện khác nhau. Báo cáo assurance nên nêu mức độ tin cậy của kết luận, thay vì tạo một phần trăm chính xác giả.

## 16. Continuous assurance: phát hiện drift và ngăn tái xuất hiện

Một thiết kế thực tiễn có thể đưa kiểm tra detection vào những mốc:

1. **Khi tạo asset:** inventory phát hiện nguồn mới; onboarding pipeline và xác minh test event là điều kiện bàn giao.
2. **Khi đổi schema hoặc collector:** chạy parser contract test và so sánh field fidelity.
3. **Khi sửa rule:** thực hiện unit, integration, positive/negative regression test rồi xác nhận rule version ở production.
4. **Khi thêm suppression:** review phạm vi, approval, test ngoài exception và đặt expiry.
5. **Khi đổi identity/permission:** đánh giá lại khả năng phát hiện hành vi đặc quyền và mapping principal.
6. **Khi xảy ra sự cố:** so sánh chuỗi hành động thực tế với detection timeline để phát hiện hành vi bị bỏ sót.
7. **Theo kỳ:** diễn tập end-to-end cho các scenario ưu tiên, xem alert routing và khả năng xử lý của người trực.

**Drift** có thể là telemetry mất, một field đổi tên, rule bị tắt hoặc case routing thay đổi. Khi phát hiện, ghi rõ thời điểm lần cuối control được xác minh và thời điểm đầu tiên biết có sai lệch; khoảng giữa là **cửa sổ rủi ro cần xem xét**, không được tự khẳng định toàn bộ khoảng đó chắc chắn mất detection.

### 16.1. Vòng phản hồi từ incident và threat hunting

Nếu một sự cố cho thấy hoạt động đã xảy ra mà detection không nhận biết, cần đưa vào quy trình cải tiến:

~~~mermaid
flowchart TD
    INC["Incident / hunting evidence"] --> MAP["Timeline hành vi"]
    MAP --> GAP{"Tín hiệu nào bị mất?"}
    GAP --> SRC["Nguồn, pipeline và analytic"]
    SRC --> FIX["Sửa control + cập nhật test"]
    FIX --> RETEST["Retest end-to-end"]
    RETEST --> EVID["Evidence và coverage register"]
    EVID --> REV["Review theo chu kỳ"]
    REV --> MAP
~~~

Khi xây lại detection, kiểm thử trên mẫu sự cố đã khử nhạy cảm hoặc mẫu mô phỏng tương đương có thể giúp ngăn lỗi tái diễn. Đồng thời kiểm tra rule mới không gây false positive quá mức dẫn đến việc lại bị suppress.

### 16.2. Audit quyền thay đổi hệ thống detection

Quyền đổi log source, parser, query, index, alert route hoặc allowlist là quyền ảnh hưởng trực tiếp đến assurance. Cần có kiểm soát quản trị và audit:

- Ai được tạo/sửa/xóa detection rule?
- Ai được tắt collector hoặc thay filter trước khi dữ liệu được kiểm chứng?
- Ai có quyền tạo ngoại lệ áp dụng toàn bộ account/tenant?
- Ai được sửa severity và alert destination?
- Ai có thể xóa historical alert/test evidence?
- Khi quyền cấp cao được dùng, có cảnh báo và đánh giá độc lập không?

Một hệ thống detection có nhiều control tốt nhưng không kiểm soát được chính các quyền này có thể xuất hiện điểm mù do thao tác quản trị.

## 17. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| "Có SIEM nghĩa là đã phát hiện mọi hành vi nguy hiểm." | SIEM phụ thuộc nguồn, parsing, rule, routing và vận hành. |
| "Có log nghĩa là có detection." | Log là đầu vào; cần analytic, rule được bật và kết quả alert hoạt động. |
| "Có rule gắn MITRE ATT&CK nghĩa là đã bao phủ technique." | Mapping là metadata; cần test các biến thể trong phạm vi đã định. |
| "Không có alert nghĩa là không có incident." | Hệ thống có thể có blind spot hoặc hành vi nằm ngoài hypothesis. |
| "Agent healthy nghĩa là đầy đủ telemetry." | Heartbeat không kiểm chứng mọi loại event/trường. |
| "Test trên staging PASS nghĩa là production PASS." | Cần xác minh tương đồng cấu hình và các khác biệt về nguồn/asset. |
| "100 rule tốt hơn 10 rule." | Số rule không nói về mức rủi ro được bao phủ và khả năng xử lý. |
| "False positive thấp chứng minh detection hiệu quả." | Có thể do rule quá hẹp, tắt rule hoặc suppression quá rộng. |
| "Rule có trong Git nghĩa là đã hoạt động." | Cần kiểm chứng phiên bản được triển khai, scheduler và runtime state. |
| "Đã xử lý ticket nên gap hết." | Cần retest đúng scenario, scope và end-to-end chain. |
| "Một synthetic event thành công chứng minh mọi đường quan sát." | Nó chỉ chứng minh đường/event class đã thử tại thời điểm test. |
| "Blind spot chỉ là thiếu log." | Có thể do parser, analytic, exception, routing, triage hoặc governance. |

## 18. Bài tập tự kiểm tra

**Câu 1.** Hệ thống có 50 cloud account production; SIEM hiện nhận log từ 45 account. Dashboard hiển thị 100% nguồn log healthy. KPI đó có chứng minh telemetry coverage toàn tổ chức đạt không?

**Gợi ý:** Không. Mẫu số của dashboard chỉ gồm 45 nguồn đang có. Cần đối soát với 50 account trong asset inventory, kiểm tra 5 nguồn thiếu và xác định khoảng trống giám sát.

**Câu 2.** Một rule chạy đúng trên dữ liệu mẫu nhưng production không tạo cảnh báo. Bạn sẽ phân biệt những nguyên nhân nào?

**Gợi ý:** Kiểm tra event ở nguồn, đường ingest, parser/field fidelity, rule runtime/deployment, schedule, suppression, alert routing và case handling. Theo dõi cùng test marker qua từng chặng.

**Câu 3.** Một rule được map với technique trong ATT&CK. Có thể đánh dấu đã phát hiện toàn bộ technique không?

**Gợi ý:** Không. Rule chỉ chứng minh những biến thể hành vi và điều kiện được kiểm thử; phải công bố asset, môi trường, nguồn, phiên bản và dữ liệu kiểm chứng.

**Câu 4.** Có 20 đơn vị kiểm thử bắt buộc: 12 PASS, 3 FAIL, 4 NOT_TESTED, 1 INCONCLUSIVE. Tỷ lệ đơn vị đã được chứng minh đạt là bao nhiêu?

**Gợi ý:** 12/20 = 60%. Không loại các đơn vị chưa test khỏi mẫu số khi đo coverage đã chứng minh.

**Câu 5.** Mọi event có đầy đủ dữ liệu trong SIEM, nhưng principal production đã nằm trong allowlist không thời hạn. Rủi ro nào còn tồn tại?

**Gợi ý:** Suppression tạo điểm mù ở analytic/alert path. Cần review quyền và lý do exception, giới hạn theo hành vi, đặt expiry, test dương và test âm.

**Câu 6.** Vì sao một synthetic event được SIEM nhận thành công chưa đủ chứng minh SOC có thể phát hiện và xử lý tình huống thật?

**Gợi ý:** Phải xét logic rule, alert routing, người trực, triage, thời gian và sự tương đồng của event test với biến thể thật. Synthetic event có giới hạn phạm vi.

## 19. Checklist triển khai detection blind spot assurance

- [ ] Có danh mục asset, nguồn telemetry bắt buộc, owner và loại môi trường.
- [ ] Có các threat scenario ưu tiên theo rủi ro, gắn với detection hypothesis và dữ liệu tối thiểu.
- [ ] Coverage register định nghĩa rõ đơn vị kiểm chứng, mẫu số và trạng thái chưa thử.
- [ ] Có test kiểm tra sensor, event class, field completeness, ingest lag và dropped events.
- [ ] Có heartbeat/canary và cảnh báo khi nguồn hoặc pipeline im lặng bất thường.
- [ ] Rule được version, review, test với positive/negative cases và chứng minh đã bật đúng scope.
- [ ] Có end-to-end exercise từ sự kiện thử đến alert, case, triage và retest evidence.
- [ ] Có rà soát suppression, allowlist và exclusion với owner, scope, expiry và biện pháp bù trừ.
- [ ] Có giám sát thay đổi đối với audit logging, parser, rule, routing và tài khoản đặc quyền.
- [ ] Blind spot có finding ID, severity theo rủi ro, owner, hạn sửa và kết quả retest.
- [ ] Dashboard phân tách PASS, FAIL, NOT_TESTED, INCONCLUSIVE, NOT_APPLICABLE và ACCEPTED_RISK.
- [ ] Bằng chứng có source/event ID, rule version, timestamps, scope, phương pháp và giới hạn.
- [ ] Sau incident hoặc threat hunting, có phân tích hành vi không được phát hiện và bổ sung regression test.
- [ ] Có lịch rà soát độ bao phủ theo thay đổi hệ thống, không chỉ theo số rule hiện có.

## Kết luận

**Detection blind spot** xuất hiện khi một hành vi đáng quan tâm không thể được quan sát, nhận diện hoặc đưa đến phản ứng thích hợp trong phạm vi bảo vệ đã cam kết. Điểm mù có thể nằm ở asset inventory, nguồn log, pipeline, dữ liệu đã parse, logic rule, ngoại lệ hoặc quy trình xử lý cảnh báo. Tìm được điểm đứt và chứng minh nguyên nhân bằng event, metrics, rule state và alert/case là điều kiện để sửa đúng.

Đối với **SECURITY_SECURITY_ASSURANCE**, kết luận về detection coverage cần dựa trên **threat scenario có ưu tiên, phạm vi asset rõ ràng, giả thuyết có thể thử nghiệm, bằng chứng end-to-end, phép kiểm định kỳ và quy trình khắc phục/retest**. Khi mẫu số, giới hạn và độ tin cậy được trình bày trung thực, các chỉ số phát hiện mới phục vụ quyết định rủi ro và cải tiến chương trình security assurance liên tục.

