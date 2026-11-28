# Security configuration change

## 1. Vì sao thay đổi cấu hình bảo mật cần audit riêng?

**Security configuration change** là thay đổi cấu hình có thể tác động tới cách hệ thống xác thực, phân quyền, bảo vệ dữ liệu, kiểm soát kết nối, phát hiện hoặc ứng phó sự cố. Thay đổi có thể đến từ người quản trị, pipeline triển khai, chính sách tự động hoặc thao tác khẩn cấp.

Trong chương Logging và audit, bài học tập trung vào bằng chứng của thay đổi: ai yêu cầu, ai được phép, nội dung và phạm vi nào đã được chấp thuận, trạng thái nào đã được lưu, thành phần nào thực sự áp dụng và kết quả kiểm chứng ra sao.

Ví dụ, tổ chức bật yêu cầu MFA cho các hành động đặc quyền. Kho cấu hình đã lưu phiên bản mới, nhưng một số instance vẫn dùng cache cũ. Một dòng `configuration updated successfully` không đủ chứng minh mọi đường thực thi đã giữ chính sách mới.

[NIST SP 800-128](https://csrc.nist.gov/pubs/sp/800/128/upd1/final) đặt quản lý cấu hình có trọng tâm an toàn trong quá trình quản lý và giám sát rủi ro hệ thống. Với yêu cầu logging, điều đó có nghĩa phải nối quyết định thay đổi với trạng thái thực tế, thay vì chỉ đếm request quản trị thành công.

Mục tiêu của bài học là chuyển chuỗi này thành yêu cầu cụ thể, đo được và kiểm chứng được. Các tên field, generation, mục tiêu thời gian và cấu hình dưới đây thuộc hệ thống giả định, không phải giá trị bắt buộc áp dụng chung.

## 2. Xác định những cấu hình thuộc phạm vi bảo mật

### 2.1. Không chỉ là file có chữ security

| Nhóm | Ví dụ thay đổi | Điều có thể bị tác động |
|---|---|---|
| Xác thực | Yêu cầu MFA, session policy, trust với identity provider | Điều kiện xác minh danh tính và duy trì phiên |
| Phân quyền | Policy, rule, scope, điều kiện truy cập quản trị | Ai được làm gì trên tài nguyên nào |
| Kết nối | Xác minh TLS, trust store, mạng được phép, endpoint tích hợp | Đối tác được tin cậy và đường dữ liệu |
| Dữ liệu | Chính sách mã hóa, export, retention, nơi lưu/backup | Phạm vi bảo vệ và công bố dữ liệu |
| Lớp API | Rate limit, giới hạn upload, field trả về, chế độ debug | Khả năng lạm dụng và rò rỉ thông tin |
| Logging/detection | Event bắt buộc, audit sink, retention, rule cảnh báo | Khả năng tạo và sử dụng bằng chứng |
| Vận hành | Feature flag, cấu hình deployment, quyền công cụ hỗ trợ | Mở đường tắt hoặc thay đổi kiểm soát thực thi |

Một feature flag được đặt tên nghiệp vụ vẫn có thể bỏ bước kiểm quyền. Do đó, phân loại theo tác động, không chỉ theo tên file hoặc tiền tố khóa.

Không phải mọi giá trị đều được phép xuất nguyên vào audit. Một endpoint nội bộ, trust policy hoặc danh sách tài nguyên có thể là thông tin nhạy cảm về kiến trúc dù không phải password.

### 2.2. Bao phủ mọi đường thay đổi

Phạm vi phải gồm giao diện quản trị, API, CLI, Git/deployment pipeline, cloud console, thay trực tiếp ở hạ tầng, biến môi trường, cấu hình runtime và automation. Nếu một đường có thể thay hiệu lực kiểm soát thì cần owner và cách tạo/đối soát bằng chứng.

Commit trong repository có thể thể hiện nội dung dự kiến, nhưng chưa chứng minh nội dung đó đã được triển khai hoặc đang có hiệu lực. Chữ ký trên artifact hỗ trợ xác minh nguồn/toàn vẹn trong mô hình thích hợp, không tự chứng minh thay đổi đã được phép theo đúng rủi ro và phạm vi nghiệp vụ.

## 3. Mô hình đe dọa và câu hỏi điều tra

| Mã | Tình huống | Hậu quả cần hạn chế |
|---|---|---|
| R1 | Người hoặc workload sửa cấu hình ngoài nhiệm vụ/scope | Làm yếu hoặc mở rộng kiểm soát trái phép |
| R2 | Phê duyệt một nội dung nhưng áp nội dung khác | Vượt quy trình bằng thay payload sau duyệt |
| R3 | Lưu desired state được coi như mọi instance đã áp dụng | Kết luận sai về mức bảo vệ đang hoạt động |
| R4 | Diff, snapshot hoặc request log có secret/dữ liệu quá mức | Audit trở thành nguồn rò rỉ |
| R5 | Thay trực tiếp, override, cấu hình cũ hoặc rollback không được phát hiện | Drift và khôi phục điều kiện không còn an toàn |
| R6 | Thay cấu hình logging để che chính hành động thay đổi | Mất bằng chứng và tạo điểm mù |
| R7 | Retry, cạnh tranh hoặc sai thứ tự làm ghi đè/hội tụ sai | Cấu hình ngoài dự định hoặc lịch sử không khớp |
| R8 | Ngoại lệ khẩn cấp không hết hạn hoặc automation bị nhầm là actor con người | Đặc quyền tồn tại kéo dài và khó quy trách nhiệm |

Một cuộc điều tra cần trả lời được:

1. Ai khởi tạo, ai phê duyệt, workload nào thực thi và quyền nào được dùng?
2. Thay đổi nhắm tới môi trường, tenant, service và tập thành phần nào?
3. Phiên bản nào trước/sau, nội dung an toàn nào đã đổi và tài liệu kiểm chứng ở đâu?
4. Đây là đề xuất, source commit, bắt đầu rollout hay đã xác nhận hiệu lực?
5. Thành phần nào chưa áp dụng, lỗi, mất liên lạc hoặc bị override?
6. Có rollback, ngoại lệ, drift hoặc tác động tiếp theo nào cần xem xét không?

Audit phải công bố giới hạn của bằng chứng. Một actor ID gắn với phiên đã xác thực không tự chứng minh một con người cụ thể không bị chiếm phiên hay dùng chung credential.

## 4. Phân biệt trạng thái mong muốn, đã lưu và có hiệu lực

### 4.1. Ba loại trạng thái không thể gộp

| Trạng thái | Ý nghĩa | Bằng chứng minh họa |
|---|---|---|
| Proposed/approved state | Nội dung dự kiến và nội dung được phép | Change request, policy, approval gắn với artifact/scope |
| Committed desired state | Nguồn có thẩm quyền đã lưu generation mới | Revision/transaction tại kho cấu hình |
| Effective state | Thành phần thực thi đang dùng cấu hình tương ứng | Quan sát runtime, xác nhận applier và phép kiểm hành vi phù hợp |

Event HTTP thành công của control plane thường chỉ chứng minh mốc theo contract API đó. Không mặc định rằng cache, replica, job, gateway hoặc các instance đã chuyển cùng lúc.

Cũng cần phân biệt target đã nhận artifact, đã nạp thành công và đã thực thi đúng kiểm soát. Một acknowledgment “downloaded” chưa phải phép kiểm hành vi.

### 4.2. Event catalog theo vòng đời

| Sự kiện minh họa | Điều kiện và ý nghĩa |
|---|---|
| `SECURITY_CONFIG_CHANGE_REQUESTED` | Nhận đề xuất và scope được nhận diện |
| `SECURITY_CONFIG_CHANGE_REJECTED` | Từ chối vì quyền, điều kiện hoặc validation |
| `SECURITY_CONFIG_CHANGE_APPROVED` | Nội dung và phạm vi cụ thể được chấp thuận |
| `SECURITY_CONFIG_SOURCE_COMMITTED` | Generation mới đã được lưu ở nguồn có thẩm quyền |
| `SECURITY_CONFIG_ROLLOUT_STARTED` | Bắt đầu áp dụng tới target set |
| `SECURITY_CONFIG_TARGET_STATUS_CHANGED` | Một target có trạng thái mới, gồm lỗi/chưa xác định |
| `SECURITY_CONFIG_EFFECT_VERIFIED` | Có bằng chứng hiệu lực theo phạm vi đã khai báo |
| `SECURITY_CONFIG_DRIFT_DETECTED` | Quan sát khác trạng thái được phép/mong muốn |
| `SECURITY_CONFIG_ROLLBACK_REQUESTED` | Có quyết định đưa nội dung về baseline được chọn |
| `SECURITY_CONFIG_EXCEPTION_STATUS_CHANGED` | Ngoại lệ được cấp, hết hạn, thu hồi hoặc gia hạn |

Tên event là lựa chọn minh họa. Catalog thực tế có thể gộp bằng một state machine và nhiều event, miễn không làm mất ý nghĩa từng mốc.

### 4.3. Định nghĩa hoàn tất theo phạm vi

Một rollout cần target set, điều kiện thành công và cách xử lý thành phần chưa biết. Không ghi “hoàn tất toàn hệ thống” nếu mới kiểm một canary instance.

Nếu target set thay đổi do autoscaling hoặc phục hồi node, cần quy tắc cho thành phần mới trước khi nhận traffic. Không để một rollout đã đóng trở thành lý do bỏ kiểm generation của node được thêm sau đó.

## 5. Schema audit và diff an toàn

### 5.1. Metadata cần có

| Nhóm | Trường minh họa | Nguồn tin cậy |
|---|---|---|
| Nhận diện | Event ID, change ID, schema version | Cơ chế cấp ID và replay có kiểm soát |
| Chủ thể | Initiator, executor, approver, delegation reference | Context xác thực/phân quyền và approval thực tế |
| Phạm vi | Service, environment, tenant, target set reference | Nguồn inventory và scope được duyệt |
| Phiên bản | Previous generation, new generation, artifact reference | Trạng thái nguồn và vật phẩm thật được dùng |
| Thay đổi | Safe path, loại thay đổi, giá trị đã được phép | Projection theo allowlist, không dump nguyên cấu hình |
| Kết quả | Lifecycle stage, outcome, reason code | Bằng chứng tại mốc tương ứng |
| Policy | Rule/version, approval/exception reference | Policy thực sự có hiệu lực |
| Thời gian | Occurred, observed, thời hạn ngoại lệ nếu có | Nguồn đồng hồ/collector và quy tắc đã công bố |
| Liên kết | Request, workflow, deployment, verification reference | Context được tạo hoặc xác minh |

Thiếu trạng thái trước không được tự điền bằng một cache đã cũ rồi coi như đã biết. Event phải biểu diễn chưa có before-state đáng tin hoặc dẫn tới nguồn đối soát phù hợp.

### 5.2. Ví dụ source commit

```json
{
  "eventId": "event-demo-412",
  "eventType": "SECURITY_CONFIG_SOURCE_COMMITTED",
  "schemaVersion": 1,
  "changeId": "security-change-demo-83",
  "occurredAt": "2026-01-12T09:15:00.123Z",
  "observedAt": "2026-01-12T09:15:00.470Z",
  "serviceRef": "identity-service-demo",
  "environment": "production-demo",
  "targetSetRef": "admin-action-verifiers-demo",
  "initiatorRef": "operator-demo-4",
  "executorRef": "config-workload-demo",
  "approverRef": "reviewer-demo-8",
  "previousGeneration": 17,
  "newGeneration": 18,
  "safeChanges": [
    {
      "path": "privilegedActions.requireMfa",
      "before": false,
      "after": true
    }
  ],
  "artifactRef": "config-artifact-demo-18",
  "approvalRef": "approval-demo-41",
  "policyVersion": 12,
  "stage": "SOURCE_COMMITTED",
  "outcome": "SUCCESS",
  "requestId": "request-demo-901"
}
```

Đây là dữ liệu giả. `SUCCESS` chỉ nói source commit thành công, không có nghĩa mọi verifier đã yêu cầu MFA. `safeChanges` chỉ chứa field được phép công bố trong kho audit có mức bảo vệ phù hợp.

Một event hiệu lực có thể giữ generation, target scope, số target được xác minh, số chưa xác định và verification reference. Không cần chép toàn bộ cấu hình của từng instance vào event.

### 5.3. Không log secret qua diff hoặc digest

Không ghi password, API secret, private key, raw token, connection string có secret hoặc blob request/response cấu hình. Thay secret có thể được biểu diễn bằng tham chiếu/version phù hợp, còn vật liệu bí mật đi qua cơ chế quản lý secret riêng.

Một hash công khai của một cấu hình chứa giá trị bí mật dễ đoán có thể giúp thử ứng viên; không mặc định dùng hash toàn blob chứa secret như một dấu vết audit vô hại. Có thể dùng version/opaque reference hoặc digest của artifact không chứa secret theo thiết kế được duyệt.

Ví dụ, tài liệu [Kubernetes Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/) phân biệt mức metadata với mức có request/response body, và minh họa ghi metadata cho một số thay đổi secret/configmap. Đây là ví dụ về lựa chọn mức dữ liệu, không phải policy đủ cho mọi cluster hoặc hệ thống.

Phần cấu hình đầy đủ, nếu cần lưu để review/phục hồi, phải ở kho có quyền, mã hóa, retention và kiểm soát export tương ứng. Không coi một audit sink thông thường là kho secret.

## 6. Phê duyệt phải gắn với đúng nội dung và quyền

### 6.1. Xác minh người và workload theo vai trò

Initiator là người hoặc hệ thống yêu cầu; executor có thể là pipeline; approver là chủ thể quyết định cho phép theo profile. Không ghi mọi thứ dưới một actor chung là `admin` hoặc chỉ ghi service account làm mất dấu người khởi tạo.

Cần phân quyền theo nhóm cấu hình, môi trường, tenant và mức rủi ro. Có quyền deploy một service không tự đồng nghĩa có quyền tắt kiểm toán hoặc sửa trust của toàn tổ chức.

Policy có thể yêu cầu xác thực tăng cường, người duyệt độc lập hoặc giới hạn giờ/phạm vi cho thay đổi nhạy cảm. Các điều kiện này phải được hệ thống thực thi và ghi bằng chứng, không chỉ tồn tại trong một checkbox tự khai.

### 6.2. Ngăn thay đổi nội dung sau khi duyệt

Approval nên gắn với nội dung/artifact, target scope, expected generation, thời hạn và điều kiện liên quan. Nếu payload, scope hoặc precondition quan trọng đổi, phải đánh giá lại theo policy.

Một ticket đã được duyệt cho môi trường thử nghiệm không được tái sử dụng để đổi production. Một approval cho bật MFA không được dùng để tắt nó bằng cách sửa request sau đó.

Không log nguyên bearer approval token hoặc vật phẩm có thể được dùng lại để thực thi. Audit giữ approval reference và metadata đủ điều tra, còn bằng chứng nhạy cảm ở vùng được bảo vệ.

### 6.3. Validation không thay thế authorization

Cấu hình đúng schema vẫn có thể không được phép, ví dụ một giá trị hợp lệ về kiểu nhưng làm yếu kiểm soát ngoài policy. Cần kiểm cả nội dung, tác động và quyền của người thực hiện.

Nếu dùng chính sách tự động, cần ghi policy/rule version và nguồn context. Một verdict do client tự gửi không phải bằng chứng rằng thay đổi đã được kiểm.

## 7. Gắn source commit với bằng chứng bền vững

Ghi event trước commit có thể tạo lịch sử thành công giả. Ghi sau commit bằng thao tác riêng có thể mất event khi process chết. Khi trạng thái cấu hình và outbox cùng phạm vi transaction được hỗ trợ, có thể dùng mẫu:

```text
verify change authorization and approval binding
validate the non-secret configuration artifact and target scope

begin transaction
    load authoritative desired state with concurrency protection
    require expected generation and required conditions still hold
    persist the new desired generation and approved artifact reference
    append a non-secret SOURCE_COMMITTED event to the protected outbox
commit

publish the committed event with stable Event ID
start or continue rollout using the committed generation
record target outcomes and effect verification separately
```

Mã giả mô tả tính nhất quán ở nguồn, không bảo đảm một transaction xuyên mọi node và provider. Nếu nguồn là dịch vụ ngoài, cần cơ chế change journal, operation reference, sự kiện control plane hoặc đối soát theo contract của nguồn đó.

Khi mất xác nhận commit, giữ trạng thái chưa xác định và kiểm nguồn có thẩm quyền. Không thử lại mù quáng rồi tạo nhiều generation hoặc ghi đè một thay đổi mới của người khác.

Retry cùng event phải giữ Event ID và thời điểm nguồn. Thay đổi mới hoặc rollback có ý nghĩa mới cần change ID/generation tương ứng, không chỉ phát lại một event cũ rồi coi là đã hoàn tất tác động mới.

## 8. Kiểm chứng hiệu lực trên hệ thống phân tán

### 8.1. Theo dõi từng target và nguồn cấu hình hiệu lực

Một generation có thể được lưu nhưng chưa có hiệu lực vì cache, reload lỗi, cần restart, override bằng biến môi trường hoặc code đang dùng default khác. Audit cần liên kết với trạng thái cấu hình đã được phân giải tại điểm thực thi, không chỉ với file được gửi đi.

Mỗi target có thể có trạng thái:

```text
PENDING
RECEIVED
LOADED
VERIFIED
FAILED
UNKNOWN
```

Các trạng thái cần định nghĩa theo hệ thống. `LOADED` không tự là `VERIFIED`. Nếu target mất liên lạc, giữ `UNKNOWN`; không tự coi nó là thành công hoặc loại khỏi mẫu số để rollout đạt 100%.

Cần biết tập target được kỳ vọng và nguồn inventory. Một bản ghi “3 target thành công” chưa đủ nếu không biết còn bao nhiêu target hoặc entry point phục vụ cùng chức năng.

### 8.2. Dùng phép kiểm phù hợp với thay đổi

Với ví dụ bật MFA cho hành động đặc quyền, bằng chứng có thể gồm projection an toàn của cấu hình hiệu lực và phép kiểm được kiểm soát: hành động phù hợp bị từ chối khi thiếu bằng chứng MFA, được xử lý đúng khi đủ điều kiện.

Phép kiểm phải có scope, tài khoản thử nghiệm và hành động không gây tác động trái phép. Không bật/tắt kiểm soát production tùy ý chỉ để tạo một dashboard xanh.

Một target báo đã đọc generation mới có thể vẫn thực thi code cũ không dùng field đó. Vì vậy, tùy mức rủi ro, cần nối artifact, deployment version, runtime state và hành vi kiểm soát.

### 8.3. Ngân sách hội tụ và hành vi khi quá hạn

Ví dụ yêu cầu kỹ thuật:

> Sau source commit tại T0, mọi entry point trong target set phải thực thi yêu cầu MFA mới trong tối đa 2 phút. Target không đáp ứng phải bị xử lý theo policy, chẳng hạn chưa được phục vụ hành động đặc quyền liên quan, và rollout không được đánh dấu hoàn tất.

Hai phút là mục tiêu giả định. Nó chỉ khả thi nếu có cơ chế phân phối, kiểm trạng thái và hạn chế đường phục vụ chưa hội tụ. Một event `ROLLOUT_STARTED` không đáp ứng yêu cầu này.

Phải nêu cách xử lý request đang chạy và các phiên/caches liên quan. Một cấu hình được bật cho request mới không tự hủy mọi thao tác đã bắt đầu trước đó.

Khi có node mới hoặc node khôi phục, cần xác nhận generation/policy được phép trước khi nhận traffic thuộc scope. Không giới hạn bảo đảm vào những node đã tồn tại lúc rollout đầu tiên.

## 9. Drift, rollback và automation cũng là thay đổi cần audit

### 9.1. Drift là khác biệt so với trạng thái nào?

Drift cần một baseline/desired state được xác định rõ và một quan sát thực tế có thời điểm, nguồn và mức tin cậy. Cần phân biệt “khác bản file gần nhất” với “khác cấu hình hiệu lực được phép”.

Nguồn khác biệt có thể gồm thay trực tiếp trên console, override runtime, default sau nâng cấp, nội dung cũ sau restore hoặc rollout không hội tụ. Không mặc định mọi drift là tấn công; nó là tín hiệu cần đánh giá.

Event drift nên giữ target, expected generation, observed reference hoặc safe projection, thời điểm quan sát và reason nếu biết. Không sao chép toàn bộ môi trường hoặc secret để chứng minh có khác biệt.

Nếu không xác định được ai đã thay trực tiếp, phải ghi actor chưa biết và bằng chứng quan sát. Không tự gán người đang trực ca làm actor để hoàn thiện field.

### 9.2. Rollback là một thay đổi mới

Rollback cần change ID hoặc quan hệ `rollbackOf`, người quyết định, baseline được chọn, lý do và kết quả mới. Nội dung cũ có thể được dùng lại, nhưng generation vận hành nên thể hiện lần áp dụng mới theo contract của hệ thống.

Ví dụ: generation 18 gặp vấn đề; quyết định quay về nội dung baseline 17 được thực hiện bằng generation 19, có liên kết tới thay đổi gốc. Điều này giúp phân biệt một rollback được phép với một thông điệp cũ đang bị replay.

Không mặc định baseline trước luôn an toàn theo policy hiện tại. Nếu nó chứa điều kiện đã bị cấm hoặc đã được sửa vì lỗ hổng, phải đánh giá lại phương án phục hồi. “Khôi phục tính sẵn sàng” không tự cho phép làm yếu mọi kiểm soát.

Sau rollback vẫn cần kiểm chứng hiệu lực, xử lý target chưa hội tụ và ghi kết quả. Không chỉ ghi đã phát lệnh rollback rồi đóng sự cố.

### 9.3. Automation phải có dấu vết riêng

Một controller có thể tự sửa drift theo policy đã được duyệt. Audit nên ghi workload thực thi, rule/version, target và kết quả. Không gán một con người là actor chỉ vì họ từng tạo policy cho controller.

Khi automation và thao tác thủ công cạnh tranh, cần version/precondition phù hợp để tránh ghi đè ngoài dự định. Sự kiện đến sai thứ tự không được tự đưa target về trạng thái cũ trái desired generation.

Việc tự sửa thành công không xóa bằng chứng drift trước đó. Nếu không, lịch sử sẽ không giải thích được khoảng thời gian hệ thống từng khác baseline.

## 10. Khi thay đổi nhắm vào chính logging và detection

### 10.1. Ngăn thay kiểm soát để che mất dấu vết

Tắt event bắt buộc, đổi audit sink, hạ retention, thêm bộ lọc drop hoặc vô hiệu rule phát hiện đều có tác động an toàn. Chúng phải có catalog, quyền và nguồn bằng chứng phù hợp.

[OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#customizable-logging) đề cập quản lý thay đổi mức/phạm vi logging và khả năng kiểm tra cấu hình. Trong thiết kế cụ thể, cần giữ bằng chứng của chính thay đổi này bằng đường không bị thao tác đó tùy ý xóa bỏ.

Một event “audit disabled” được gửi duy nhất tới sink vừa bị tắt có thể không còn tồn tại để điều tra. Cần xem xét control-plane journal, nguồn quan sát độc lập hoặc cơ chế bảo vệ thích hợp, cùng giới hạn tin cậy của từng nguồn.

### 10.2. Không coi cấu hình khác là đủ để chứng minh audit còn hoạt động

Sau thay policy log, cần kiểm một synthetic event hoặc một hành động kiểm soát có thể truy vết qua các chặng phù hợp: tạo record, nhận, lưu, truy vấn và rule cần thiết. Việc file policy hợp lệ không chứng minh pipeline thực sự nhận được event.

Cần quan sát source health, backlog, schema rejection và nguồn im lặng. Đường cảnh báo mất audit không nên chỉ phụ thuộc vào chính phần đang bị vô hiệu.

Giữ quyền thay policy audit, xóa lịch sử và quản lý nơi lưu ở phạm vi phù hợp. Chỉ đổi tên role không tạo phân tách nếu cùng một chủ thể có thể tự cấp mọi quyền đó.

### 10.3. Toàn vẹn không đồng nghĩa đầy đủ

Hash/chữ ký hỗ trợ phát hiện thay đổi record trong mô hình thích hợp, không tự chứng minh mọi thao tác đã được tạo event. Nếu nguồn, khóa hoặc toàn bộ đường thu thập bị chiếm, cần nêu giới hạn của bằng chứng và dùng các nguồn đối soát phù hợp.

Không gắn nhãn “không thể chối bỏ” chỉ vì log có timestamp, username và một hash. Mức tin cậy phụ thuộc vào danh tính, khóa, quyền quản trị và ngữ nghĩa event đã được bảo vệ tới đâu.

## 11. Ngoại lệ khẩn cấp và hành vi khi phụ thuộc lỗi

### 11.1. Break glass cần phạm vi và thời hạn

Một ngoại lệ có thể cần initiator, người cấp quyền, cấu hình được phép thay, target, lý do, thời điểm bắt đầu/kết thúc và điều kiện hoàn nguyên. Ticket là một tham chiếu công việc, không tự là quyền thực hiện.

Không để người thao tác tự mở rộng field, môi trường hoặc thời hạn ngoài profile đã được cấp. Gia hạn là quyết định mới cần bằng chứng; không thay thời gian trong record cũ để che việc ngoại lệ đã hết hạn.

Hết hạn quyền break glass không chắc tự hoàn nguyên cấu hình đã áp dụng. Policy cần nói rõ có khôi phục không, ai thực hiện, baseline nào và cách kiểm chứng. Hai mốc “quyền thao tác đã hết hạn” và “kiểm soát đã được đưa về trạng thái yêu cầu” phải được theo dõi riêng.

### 11.2. Không áp một quy tắc lỗi cho mọi loại thay đổi

| Tình huống | Hành vi cần đặc tả |
|---|---|
| Thay đổi làm yếu kiểm soát nhưng thiếu quyền/approval hoặc record nguồn bắt buộc | Không thực hiện/không xác nhận hoàn tất ngoài policy |
| Collector tập trung lỗi nhưng journal nguồn còn bền vững | Có thể tiếp tục trong giới hạn được duyệt, giữ backlog và cảnh báo |
| Thắt chặt khẩn cấp để chặn truy cập đang nguy hiểm | Có đường được ủy quyền và bằng chứng dự phòng phù hợp, không bỏ audit tùy ý |
| Rollout một phần hoặc mất phản hồi target | Giữ trạng thái chưa hoàn tất; áp biện pháp bảo vệ scope và đối soát |
| Policy/rule không tải được hoặc context không đủ tin cậy | Không coi thiếu thông tin là một chấp thuận thay đổi |

Không nên vô tình ngăn mọi hành động chặn khẩn cấp chỉ vì một kho log tập trung đang ngừng hoạt động. Thiết kế cần chuẩn bị đường ghi nhận/đối soát và thẩm quyền phù hợp trước sự cố, không tạo bypass bất kỳ lúc nào có lỗi.

Nếu không thực hiện được thay đổi bảo vệ cần thiết, phải thể hiện trạng thái thật và chuyển owner xử lý. Một event thành công giả làm giảm khả năng ứng phó hơn là một trạng thái chưa xác định được công bố rõ.

### 11.3. Không dùng debug như phương án chữa lỗi audit

Không dump toàn bộ cấu hình, environment hoặc request quản trị vào response/log để xử lý nhanh sự cố. Fallback của audit cũng phải giữ allowlist và không tiết lộ lỗi thứ cấp của sink.

Các trường free-text như reason hoặc comment cần giới hạn, encode và xử lý dữ liệu nhạy cảm. Khi một field phụ không hợp lệ, phải có quy tắc bảo toàn event cốt lõi thay vì tự bỏ mọi bằng chứng.

## 12. Phát hiện, điều tra và bảo vệ lịch sử thay đổi

### 12.1. Use case cần dữ liệu nào?

| Use case | Bằng chứng cần nối |
|---|---|
| Một policy bị làm yếu bất thường | Actor, change flow, safe delta, approval và effective scope |
| Thay cấu hình không qua đường quản trị được duyệt | Drift, source identity, journal ngoài luồng và runtime observation |
| Tắt logging rồi xuất dữ liệu | Chuỗi change ID, event bị tác động, dữ liệu truy xuất và các mốc thời gian |
| Ngoại lệ tồn tại quá hạn | Exception record, quyền còn hiệu lực và observed effective state |
| Rollout hoặc rollback không hội tụ | Desired generation, inventory, target status và verification |

Rule cần xét mức rủi ro, quyền, mục đích và bối cảnh. Một lần đổi cấu hình ngoài giờ có thể là bảo trì hợp lệ; một thay đổi tăng bảo vệ cũng có thể gây gián đoạn cần theo dõi. Không coi mọi cấu hình thay đổi đều là tấn công.

### 12.2. Đo riêng các chặng

Cần tách thời gian từ yêu cầu tới quyết định, từ commit tới hiệu lực, từ event tới lưu/truy vấn, từ điều kiện phát hiện tới cảnh báo và phản ứng. Một mốc không thay thế các mốc còn lại.

Khi đo, phải xét đồng hồ nguồn, collector và event đến trễ. Timestamps cần có ý nghĩa rõ; request/trace ID hỗ trợ tương quan nhưng không tự tạo quyền xem log.

Số liệu quan trọng gồm rollout chưa xác minh, drift chưa xử lý, ngoại lệ quá hạn và commit thiếu event tương ứng. Không đưa raw diff hoặc comment quản trị vào metric label không giới hạn.

### 12.3. Quyền và retention của audit cấu hình

Audit có thể chứa topology, policy, danh tính quản trị và đường kiểm soát nhạy cảm. Cần quyền đọc theo nhiệm vụ/case, bảo vệ export, archive và các bản sao. Không chỉ che trên UI trong khi API trực tiếp trả nguyên dữ liệu.

Producer không mặc nhiên được sửa/xóa lịch sử. Thao tác quản trị kho, đổi retention, xem evidence và xuất lịch sử cần được kiểm soát phù hợp. Artifact đầy đủ, approval evidence và safe event có thể có mức dữ liệu và thời hạn khác nhau.

Retention cần theo mục tiêu, rủi ro và nghĩa vụ áp dụng. Không giữ mọi snapshot chứa secret vô hạn vì audit; cũng không xóa event nguồn trước khi đủ điều kiện sử dụng, lưu trữ hoặc bảo toàn theo case.

## 13. Bộ yêu cầu bảo mật mẫu có thể nghiệm thu

| ID | Yêu cầu | Rủi ro và bằng chứng |
|---|---|---|
| SCONFIG-01 | Inventory và catalog bao phủ cấu hình có tác động an toàn cùng mọi đường thay đổi được hỗ trợ | R1, R5, R8; sơ đồ source/override, UI/API/CLI/pipeline và control plane |
| SCONFIG-02 | Audit phân biệt initiator, executor, approver và scope từ nguồn tin cậy | R1, R8; kiểm giả metadata, delegation và quyền chéo môi trường/tenant |
| SCONFIG-03 | Approval gắn với nội dung, target, expected generation và thời hạn; thay điều kiện quan trọng được đánh giá lại | R2; sửa payload/scope sau duyệt và approval hết hạn |
| SCONFIG-04 | Source commit có record bền vững nhất quán, không nhầm request/decision với commit | R3, R7; crash/transaction và đối soát operation |
| SCONFIG-05 | Diff và event theo allowlist; secret, raw request/blob và evidence có khả năng sử dụng lại không xuất vào audit thông thường | R4; canary ở mọi telemetry và đường export |
| SCONFIG-06 | Rollout có target set, trạng thái từng target, ngân sách hội tụ và bằng chứng hiệu lực phù hợp | R3; partial rollout, cache/reload, node mới và behavior probe |
| SCONFIG-07 | Drift giữa trạng thái hiệu lực và baseline được phát hiện; không tự bịa actor hoặc before-state | R3, R5; override, default thay đổi, nguồn mất và runtime observation |
| SCONFIG-08 | Rollback là thay đổi có lineage và version; baseline được đánh giá theo policy hiện tại rồi kiểm chứng hiệu lực | R5, R7; rollback an toàn, replay generation cũ và target chưa hội tụ |
| SCONFIG-09 | Thay logging/detection có bằng chứng không bị chính thay đổi đó tùy ý xóa; pipeline được kiểm thực tế | R6; đổi sink/filter/rule và synthetic event qua nguồn độc lập |
| SCONFIG-10 | Break glass có scope, thẩm quyền, thời hạn và kết quả hoàn nguyên/đóng; lỗi phụ thuộc có hành vi theo rủi ro | R1, R8; ngoại lệ hết hạn, journal lỗi và chặn khẩn cấp |
| SCONFIG-11 | Quyền đọc/sửa/xóa/export và retention bảo vệ lịch sử, artifact và evidence theo mức dữ liệu | R4, R6; IAM, archive, API trực tiếp và thao tác quản trị kho |
| SCONFIG-12 | Use case phát hiện/điều tra có owner, rule/version và mục tiêu thời gian; thay schema/policy có regression | R3, R5, R8; diễn tập end-to-end, rollout và rollback phiên bản |

Ví dụ đặc tả chi tiết cho hiệu lực:

```yaml
id: SCONFIG-06
asset: privileged-action-authentication-policy
trigger: A new required-MFA generation is committed
requiredBehavior:
  - Track the approved target set and the effective generation per target
  - Distinguish RECEIVED, LOADED and VERIFIED
  - Keep UNKNOWN targets visible in rollout status
  - Verify the required behavior at the appropriate enforcement boundary
maximumConvergenceSeconds: 120
failureBehavior:
  - Do not claim full completion while required targets are unverified
  - Apply the approved protection for non-converged targets
measurement:
  fullCompletionClaimsWithUnverifiedRequiredTargets: 0
evidence:
  - Runtime projection and controlled behavior test
  - Partial-rollout, restart and new-instance test
owner: identity-platform
```

120 giây là tham số của ví dụ. Mẫu không tự chứng minh khả thi; cơ chế phân phối, kiểm chứng và xử lý quá hạn phải được thiết kế tương ứng. Một field `effectiveGeneration` không có nguồn tin cậy cũng không tạo ra bằng chứng.

## 14. Ma trận kiểm thử theo thuộc tính

Đây là tiêu chí thiết kế kiểm thử, chưa phải kết quả QA của một triển khai cụ thể. Dùng cấu hình, tài khoản và thao tác kiểm soát trong môi trường được phép.

| Tình huống | Kết quả mong đợi |
|---|---|
| Thay đổi hợp lệ qua đường chuẩn | Có lineage từ approval tới source commit và effect verification |
| Client giả actor, approver, tenant hoặc environment | Không tạo quyền hoặc bằng chứng tin cậy từ metadata tự khai |
| Payload/target thay sau khi được duyệt | Không thực thi ngoài approval binding |
| Approval hợp lệ về ID nhưng hết hạn hoặc sai expected generation | Được xử lý theo policy, không mở rộng quyền mặc định |
| Cấu hình đúng schema nhưng làm yếu kiểm soát trái policy | Bị chặn, có event phù hợp |
| Secret/canary nằm trong request, diff, artifact hoặc exception | Không xuất vào audit/response/telemetry ngoài policy |
| Reason/comment có CR/LF, markup hoặc quá dài | Không tạo event giả hoặc làm mất event cốt lõi ngoài contract |
| Commit lỗi hoặc process chết quanh commit | Không có thành công giả, không mất record bắt buộc cho commit đã xảy ra |
| Mất acknowledgment rồi retry cùng operation/event | Không tạo thay đổi thừa hoặc đếm nhiều lần cùng event |
| Hai thay đổi cùng expected generation cạnh tranh | Không ghi đè âm thầm ngoài quy tắc version |
| Target chỉ nhận/nạp artifact nhưng chưa thực thi đúng | Không gắn VERIFIED chỉ từ download acknowledgment |
| Một số target lỗi, stale cache hoặc mất liên lạc | Hiển thị partial/unknown, áp bảo vệ quá hạn và không đóng rollout sai |
| Node mới hoặc node từ backup tham gia sau rollout | Kiểm generation/policy trước khi phục vụ scope liên quan |
| Biến môi trường/default/deployment tạo override | Phát hiện khác biệt ở cấu hình hiệu lực phù hợp |
| Thay trực tiếp bằng console/script ngoài pipeline | Có bằng chứng tương ứng hoặc drift được phát hiện; không bịa actor |
| Rollback về baseline cũ không còn được phép | Không áp máy móc chỉ vì đó là bản trước |
| Rollback được phép và generation mới áp nội dung cũ | Có quan hệ rollback, version mới và kiểm chứng hiệu lực |
| Tắt/sửa audit sink, filter hoặc detection rule | Giữ bằng chứng theo thiết kế, kiểm được pipeline sau thay đổi |
| Collector lỗi nhưng journal nguồn còn hoặc cũng lỗi | Hành vi theo profile rủi ro, không fail-open hoặc lộ debug |
| Ngoại lệ hết hạn/gia hạn hoặc đóng mà cấu hình chưa hoàn nguyên | Các trạng thái được phân biệt và có owner xử lý |
| Reader khác scope thử đọc/export artifact/evidence | Bị chặn ở UI, API và archive tương ứng |
| Rollout/rollback schema audit hoặc logging config | Không âm thầm mất event/field bắt buộc hoặc mở raw payload |

Bằng chứng cần lấy ở nguồn trạng thái, journal, collector, target và điểm thực thi phù hợp. Một request HTTP 200 hoặc một dòng “updated” không chứng minh kiểm soát đã hoạt động trên toàn scope.

Canary không xuất hiện chỉ chứng minh ca thử đó. Cần phối hợp schema, nguồn giá trị, instrumentation và đường export. Với hiệu lực, test phải quan sát hành vi hoặc trạng thái có ý nghĩa tại boundary, không chỉ assert một event name.

## 15. Quản trị catalog và những lỗi đặc tả thường gặp

Catalog, classification của key, baseline, approval profile, rollout policy và detection rule cần owner cùng phiên bản. Khi thêm feature flag hoặc tích hợp mới, cần đánh giá tác động an toàn và đường audit tương ứng.

Một thay đổi tên field có thể phá query điều tra hoặc rule phát hiện dù event vẫn được ingest. Rollout/rollback phải xem cả tương thích parser, schema và dữ liệu cũ.

Khi điều tra, cần bảo toàn lịch sử và phân biệt điều đã biết với điều suy luận. Không sửa một event cũ từ UNKNOWN thành SUCCESS mà không có cơ chế lưu lịch sử/bằng chứng cập nhật phù hợp; có thể ghi một event đối soát mới liên kết với mốc trước.

Những lỗi thường gặp:

- **“Có Git history là đủ audit.”** Chưa chứng minh quyền phê duyệt, triển khai và cấu hình có hiệu lực.
- **“Control plane trả thành công là mọi node đã áp.”** Nhầm source commit với enforcement.
- **“Ghi nguyên before/after cho đầy đủ.”** Làm lộ secret, topology hoặc evidence nhạy cảm.
- **“Approval theo ticket ID là đủ.”** Không ràng buộc nội dung, scope và điều kiện thực thi.
- **“Rollback luôn quay về trạng thái an toàn.”** Bỏ qua policy hiện tại và lỗ hổng đã được khắc phục.
- **“Tắt audit thì ghi một event vào chính sink đó.”** Không có bằng chứng đủ tin cậy khi đường ghi bị vô hiệu.
- **“Hết hạn quyền break glass là đã hoàn nguyên.”** Nhầm thời hạn quyền thao tác với trạng thái cấu hình còn tồn tại.
- **“Automation không cần actor.”** Mất nguồn, rule và khả năng giải thích thay đổi tự động.

Yêu cầu audit cho security configuration change tốt nối được thẩm quyền, nội dung được duyệt, trạng thái đã lưu và kiểm soát thực sự đang chạy. Mỗi khẳng định hoàn tất cần scope và bằng chứng tương ứng; mỗi đường ngoại lệ, rollback và thay đổi logging phải giữ được khả năng truy vết mà không làm lộ cấu hình nhạy cảm.
