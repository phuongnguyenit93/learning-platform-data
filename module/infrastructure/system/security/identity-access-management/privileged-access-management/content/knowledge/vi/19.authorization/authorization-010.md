# Policy simulation trong PAM

## Mục tiêu bài học

**Policy simulation** là việc đánh giá một chính sách cấp quyền trên các đầu vào xác định để dự đoán quyết định mà chính sách sẽ tạo ra, trước khi dùng nó để thực thi truy cập thật.

Trong Privileged Access Management (PAM), một thay đổi nhỏ về nhóm, cây tài nguyên, thời hạn hoặc quy tắc kết hợp có thể mở quyền tới nhiều tài khoản đặc quyền. Mô phỏng giúp phát hiện tác động đó, đồng thời kiểm tra rằng những công việc hợp lệ vẫn được thực hiện.

Sau bài học, bạn có thể:

- Xác định đầu vào cần thiết cho một lần mô phỏng có thể tái lập.
- So sánh policy hiện tại và policy đề xuất trên cùng dữ liệu.
- Thiết kế tình huống cho phép, từ chối, thiếu dữ liệu và xung đột.
- Kiểm tra cả hành động, resource, điều kiện và nghĩa vụ thực thi.
- Phân biệt replay, kiểm thử giả định và đánh giá song song.
- Đưa kết quả mô phỏng vào quy trình thay đổi, triển khai và đối soát quyền.

Tên policy, vai trò, dữ liệu và các đoạn mã trong bài là minh họa. Không có cấu hình nào được giả định tương thích nguyên trạng với một sản phẩm PAM cụ thể.

## 1. Mô phỏng để trả lời câu hỏi cụ thể

Giả sử một đội muốn đổi quyền từ:

> Nhóm vận hành có thể yêu cầu bảo trì trên mọi máy sản xuất.

thành:

> Nhóm vận hành thanh toán chỉ được yêu cầu bảo trì trên tài sản của dịch vụ thanh toán, với grant tối đa 30 phút và điều kiện được xác định.

Trước khi triển khai, cần biết:

- Người nào được thêm hoặc mất khả năng truy cập?
- Tài sản nào nằm trong phạm vi mới?
- Quyền kế thừa hoặc nhóm chồng lấn có làm rộng phạm vi không?
- Người bị khóa, grant hết hạn hoặc thiếu phê duyệt có bị chặn không?
- Phiên có cần ghi nhận, dùng tài khoản hạn chế hoặc cấm tiết lộ secret không?
- Điểm thực thi có thực hiện được các yêu cầu này không?

Mô phỏng có thể trả lời phần quyết định chính sách trên những dữ liệu đã cung cấp. Nó không tự chứng minh rằng mạng, vault, session broker và máy đích sẽ thực thi đúng.

Một kết quả “ALLOW” cần được hiểu là:

> Với policy, dữ liệu, thời điểm và quy tắc đánh giá này, bộ đánh giá tạo ra kết quả cho phép cùng các điều kiện đi kèm.

Không nên diễn giải thành “người dùng chắc chắn truy cập an toàn trong mọi hoàn cảnh”.

## 2. Ranh giới của policy simulation

| Hoạt động | Mục đích | Giới hạn |
|---|---|---|
| Kiểm tra cấu trúc hoặc cú pháp | Phát hiện policy không hợp lệ về biểu diễn | Không chứng minh quyền đúng |
| Phân tích quan hệ quyền | Tìm đường cấp quyền trực tiếp, nhóm hoặc kế thừa | Phụ thuộc mô hình và độ đầy đủ dữ liệu |
| Mô phỏng một yêu cầu | Dự đoán quyết định cho đầu vào cụ thể | Không bao phủ mọi tình huống |
| Replay dữ liệu lịch sử | Đánh giá lại những yêu cầu đã ghi nhận | Không tái tạo đầy đủ tương lai |
| Mô phỏng giả định | Thử thay thuộc tính, thời gian hoặc phạm vi | Phụ thuộc chất lượng giả định |
| Đánh giá song song | So sánh quyết định hiện tại và đề xuất trên yêu cầu quan sát được | Không được để quyết định thử nghiệm điều khiển truy cập thật |
| Kiểm thử tích hợp | Xác minh quyết định được thực thi qua thành phần liên quan | Cần môi trường và phạm vi được phép |

Một chức năng có tên “dry run” không mặc nhiên không có tác động. Phải biết nó có gọi API cấp quyền, đọc secret, gửi phê duyệt hoặc mở phiên thật không.

Trong thiết kế mô phỏng, nên tách đường đánh giá khỏi đường thực thi. Mô phỏng không cần lấy giá trị credential, thêm thành viên nhóm hoặc tạo grant sản xuất để biết một quy tắc sẽ quyết định gì.

## 3. Mô hình đầu vào của một lần mô phỏng

Một quyết định thường phụ thuộc nhiều hơn văn bản policy.

```text
Policy và phiên bản bộ đánh giá
          +
Chủ thể, nhóm và quan hệ quyền
          +
Resource, cây tài nguyên và thuộc tính
          +
Hành động cụ thể
          +
Xác thực, thiết bị và ngữ cảnh rủi ro
          +
Phê duyệt, grant, thời gian và trạng thái
          |
          v
Quyết định + lý do + nghĩa vụ thực thi
```

### 3.1. Chủ thể

Cần dữ liệu phù hợp về danh tính, tenant, nhóm, vai trò, trạng thái và những quan hệ như quản lý hoặc ủy quyền nếu policy sử dụng chúng.

Chỉ đưa nhóm trực tiếp vào mô phỏng có thể bỏ sót quyền qua nhóm lồng nhau. Ngược lại, nhập sẵn một tập nhóm rộng hơn thực tế có thể tạo kết quả cho phép giả.

### 3.2. Resource và hành động

Dùng định danh resource đủ miền, môi trường và hành động cụ thể.

“Có quyền access không?” thường quá mơ hồ. Nên hỏi:

> Chủ thể này có được mở phiên profile đọc log trên resource này tại thời điểm này không?

hoặc:

> Chủ thể này có được tiết lộ credential tham chiếu này không?

Mở phiên và nhận mật khẩu là những hành động khác nhau. Kết quả cho một hành động không được tái sử dụng như kết quả của mọi hành động trên cùng tài sản.

### 3.3. Thời gian và dữ liệu động

Đầu vào cần xác định thời điểm đánh giá, trạng thái phê duyệt và grant, độ mới xác thực, tình trạng thiết bị cùng các tín hiệu được sử dụng.

Nếu mô phỏng dùng đồng hồ hiện tại nhưng fixture chứa grant cũ, kết quả có thể thay đổi mỗi lần chạy. Cần truyền thời gian đánh giá rõ ràng khi bộ đánh giá hỗ trợ.

Một policy sử dụng trạng thái “thiết bị đạt yêu cầu” cần cả ngữ nghĩa và độ mới tương ứng, không chỉ một cờ được đặt thuận lợi trong mọi mẫu.

### 3.4. Policy, thuật toán hợp nhất và bộ đánh giá

Cùng một đầu vào nhưng khác quy tắc kết hợp giữa allow, deny, kế thừa và ngoại lệ có thể tạo quyết định khác.

Cần lưu:

- Phiên bản policy.
- Phiên bản hoặc cấu hình bộ đánh giá liên quan.
- Cách hợp nhất quy tắc.
- Giá trị mặc định khi không có quy tắc áp dụng.
- Cách xử lý lỗi, thuộc tính thiếu hoặc dữ liệu không xác định.
- Các phép ánh xạ vai trò, profile và hành động.

Không giả định mọi nền tảng đều có quy tắc “deny luôn thắng”. Điều đó phải được xác định trong mô hình thực tế và kiểm chứng.

## 4. Snapshot và khả năng tái lập

Một gói mô phỏng có thể được mô tả như sau:

```yaml
simulation_run:
  run_id: SIM-608
  baseline_policy: pam-maintenance-v12
  candidate_policy: pam-maintenance-v13
  evaluator_version: example-evaluator-4
  evaluation_time: "2026-12-07T20:10:00+07:00"
  input_snapshots:
    identities: identities-snapshot-22
    memberships: memberships-snapshot-19
    resources: resources-snapshot-31
    entitlement_graph: entitlements-snapshot-18
    approvals: approvals-snapshot-14
    grants: grants-snapshot-11
    authentication_contexts: authn-snapshot-09
  scenarios: maintenance-scenario-set-07
  execution_mode: decision_only
  side_effects_allowed: false
```

Đây là manifest minh họa. Các mã snapshot không chứng minh dữ liệu đầy đủ; cần mô tả nguồn và quy trình lấy dữ liệu.

### 4.1. So sánh trên cùng dữ liệu

Để hiểu tác động của policy, baseline và candidate nên được đánh giá trên cùng đầu vào và thời điểm. Nếu đồng thời đổi membership hoặc dữ liệu resource, cần tách và ghi rõ những chiều thay đổi đó.

Nếu mục tiêu là đánh giá cả thay đổi policy lẫn thêm tài sản mới, có thể chạy nhiều cấu hình để phân biệt:

- Policy cũ với dữ liệu cũ.
- Policy mới với dữ liệu cũ.
- Policy mới với dữ liệu dự kiến.

Không gộp mọi chênh lệch vào một nhãn “do policy mới”.

### 4.2. Bảo vệ dữ liệu mô phỏng

Fixture có thể chứa danh tính, cấu trúc hạ tầng, quyết định phê duyệt hoặc thông tin về tài khoản đặc quyền. Cần phân quyền và giảm dữ liệu nhạy cảm phù hợp.

Không đưa mật khẩu, token, cookie hoặc khóa riêng vào snapshot. Nếu cần biết một bí mật thuộc tài sản nào, dùng tham chiếu và quan hệ thay vì giá trị bí mật.

Dữ liệu giả lập nên giữ được quan hệ quan trọng. Ẩn danh theo cách làm mất quan hệ nhóm hoặc trùng định danh có thể khiến kết quả mô phỏng không còn đại diện.

## 5. Thiết kế bộ tình huống có giá trị

Một bộ tình huống tốt không chỉ gồm những người dùng và tài sản chắc chắn được phép.

### 5.1. Các nhóm cần bao phủ

| Nhóm tình huống | Ví dụ |
|---|---|
| Hợp lệ | Đúng người, resource, hành động, phê duyệt và cửa sổ |
| Sai chủ thể | Người ngoài nhóm, tài khoản khóa hoặc tenant khác |
| Sai phạm vi | Tài sản cùng tên nhưng khác môi trường, dịch vụ khác |
| Sai hành động | Được mở phiên nhưng yêu cầu tiết lộ secret |
| Sai thời gian | Trước cửa sổ, đúng biên, sau hạn hoặc xác thực quá cũ |
| Thiếu dữ liệu | Không có nhóm, nhãn, phê duyệt hoặc trạng thái thiết bị cần thiết |
| Dữ liệu không đáng tin | Thuộc tính tự khai, issuer không được chấp nhận |
| Xung đột quyền | Một nguồn cho phép, nguồn khác từ chối hoặc giới hạn |
| Kế thừa và quyền hợp thành | Nhóm lồng nhau hoặc vai trò tổ tiên mở rộng quyền |
| Ngoại lệ | Truy cập khẩn cấp, ủy quyền và điều kiện bù đã được thiết kế |
| Vòng đời | Yêu cầu bị hủy, grant thu hồi, nhân sự chuyển nhóm |
| Nghĩa vụ không thực thi được | Yêu cầu ghi phiên nhưng gateway không sẵn sàng |

Không cần thử ngẫu nhiên mọi giá trị có thể có ngay từ đầu. Nên bắt đầu bằng những chiều làm thay đổi quyết định và những lỗi có tác động lớn.

### 5.2. Các bất biến cần bảo vệ

Một bất biến là điều được yêu cầu giữ đúng trong phạm vi chính sách đang xét. Ví dụ của luồng bảo trì thông thường:

- Tài khoản bị khóa không được tạo grant mới.
- Không được truy cập resource ngoài tenant và phạm vi được quản trị.
- Thiếu phê duyệt bắt buộc không được kích hoạt quyền.
- Quyền mở phiên không tự bao gồm tiết lộ secret.
- Grant không vượt thời hạn được cho phép.
- Nghĩa vụ bắt buộc không đáp ứng thì không thực hiện như một phiên hợp lệ.

Nếu có đường khẩn cấp với quy tắc khác, phải mô hình hóa riêng, có điều kiện và trách nhiệm rõ ràng. Không viết một bất biến tuyệt đối rồi dùng ngoại lệ ngầm để giải thích mọi sai lệch.

Kiểm thử nhiều đầu vào theo các bất biến giúp tìm lỗi, nhưng chỉ chứng minh kết quả trong phạm vi phương pháp và dữ liệu đã kiểm tra. Không mặc định đã chứng minh toàn bộ không gian trạng thái.

### 5.3. Kỳ vọng phải có căn cứ độc lập

Kết quả baseline không tự là đáp án đúng. Policy cũ có thể đang quá rộng hoặc chặn nhầm người hợp lệ.

Kỳ vọng nên dựa trên yêu cầu nghiệp vụ, chính sách được chấp thuận và phân tích resource/hành động. Nếu chỉ sao chép mọi kết quả cũ làm kỳ vọng, bộ kiểm thử sẽ bảo vệ cả lỗi cũ.

Mỗi tình huống nên có mục đích và tiêu chí rõ, ví dụ:

```yaml
scenario:
  id: CASE-NO-SECRET-DISCLOSURE
  purpose: Quyền mở phiên không được chuyển thành quyền nhận mật khẩu
  input:
    subject_id: person-041
    tenant_id: organization-01
    resource_id: asset-2041
    action: reveal_secret
    eligible_profile: service-restart-limited
    approval_status: approved
    grant_status: active
  expected:
    decision: DENY
    reason_category: action_not_entitled
```

Mẫu này đã giản lược. Trong một lần chạy thực, các giá trị cần có nguồn và ngữ nghĩa phù hợp; không nhận `approval_status: approved` tự khai như bằng chứng hợp lệ.

## 6. So sánh quyết định: nhiều hơn ALLOW và DENY

### 6.1. Ma trận chênh lệch

| Baseline | Candidate | Hướng điều tra |
|---|---|---|
| DENY | ALLOW | Quyền mới được mở; xác minh đây có phải thay đổi chủ đích không |
| ALLOW | DENY | Quyền bị thu hẹp; kiểm tra tác động đến công việc hợp lệ |
| ALLOW | ALLOW | So sánh thêm phạm vi, thời hạn và nghĩa vụ |
| DENY | DENY | Kiểm tra lý do và chắc rằng không cùng sai |
| ERROR/UNKNOWN | Bất kỳ | Điều tra dữ liệu, bộ đánh giá hoặc quy tắc xử lý |
| Bất kỳ | ERROR/UNKNOWN | Không coi như một kết quả từ chối sạch để bỏ qua lỗi |

Một số bộ đánh giá có trạng thái như không có quy tắc áp dụng hoặc không thể xác định. Giữ lại ngữ nghĩa gốc và mô tả cách điểm thực thi xử lý; không tự gom mọi trạng thái thành allow hoặc deny để báo cáo đẹp hơn.

Nếu chính sách quy định lỗi đánh giá phải chặn hành động, đó vẫn là một lỗi cần xử lý, không phải bằng chứng quy tắc cấp quyền đã đúng.

### 6.2. Nghĩa vụ và điều kiện thực thi

Hai kết quả đều cho phép nhưng có thể khác tác động:

```yaml
baseline_result:
  decision: ALLOW
  resource_id: asset-2041
  action: open_session
  effective_profile: full_administrator
  duration_minutes: 120
  obligations: []

candidate_result:
  decision: ALLOW
  resource_id: asset-2041
  action: open_session
  effective_profile: service-restart-limited
  duration_minutes: 30
  obligations:
    - record_session
    - use_controlled_gateway
    - do_not_disclose_credential
```

Candidate trong ví dụ có phạm vi kỹ thuật khác đáng kể. Tuy nhiên, cần kiểm chứng profile hạn chế thực sự được ánh xạ đúng và điểm thực thi hỗ trợ các nghĩa vụ.

Không báo cáo “không thay đổi quyền” chỉ vì hai trường `decision` giống nhau.

### 6.3. Chuẩn hóa kết quả có kiểm soát

Có thể chuẩn hóa thứ tự của một tập không có thứ tự để so sánh. Nhưng không được tự sắp xếp lại các quy tắc có ưu tiên hoặc xóa điều kiện có ý nghĩa.

Một bản ghi chênh lệch nên gồm:

- Mã tình huống và đầu vào tham chiếu.
- Hai phiên bản policy.
- Kết quả đầy đủ và lý do liên quan.
- Resource, hành động, profile, thời hạn và nghĩa vụ khác nhau.
- Kỳ vọng độc lập.
- Phân loại: chủ đích, hồi quy, lỗi dữ liệu hoặc chưa giải thích.
- Người xác nhận và bằng chứng khi xử lý.

### 6.4. Định lượng phạm vi ảnh hưởng

Có thể đếm số tình huống đổi quyết định, số principal, resource hoặc loại hành động bị ảnh hưởng trong tập đã mô phỏng.

Phải ghi rõ mẫu số. “Không có mở quyền ngoài ý định trong 500 tình huống” không đồng nghĩa “không có mở quyền ngoài ý định trên toàn hệ thống”.

Tập replay cũng có thiên lệch: những hành động trước đây bị chặn hoặc chưa bao giờ được yêu cầu có thể ít xuất hiện. Cần bổ sung tình huống âm và giả định có chủ đích.

## 7. Quy trình mô phỏng đề xuất

### Bước 1: xác định thay đổi và tiêu chí

Mô tả vấn đề hiện tại, hành vi mong muốn, phạm vi tài sản và những bất biến phải giữ. Chia thay đổi lớn thành phần có thể giải thích khi phù hợp.

### Bước 2: chuẩn bị gói đầu vào

Lấy policy baseline, candidate và snapshot cần thiết. Kiểm tra độ bao phủ, nguồn, dữ liệu thiếu và thời điểm.

Không cho mô phỏng gọi dịch vụ cấp quyền hoặc lấy secret thật chỉ vì bộ đánh giá có sẵn tích hợp đó. Dùng dữ liệu chỉ đọc hoặc thay thế phù hợp với ý nghĩa cần đánh giá.

### Bước 3: chạy cùng tập tình huống

Mã giả khái niệm:

```text
cho mỗi tình huống:
    xác định đầu vào và thời điểm cố định
    kết quả cũ = đánh giá(policy cũ, đầu vào, snapshot)
    kết quả mới = đánh giá(policy mới, đầu vào, snapshot)

    giữ nguyên trạng thái lỗi hoặc không xác định
    so sánh quyết định, phạm vi và nghĩa vụ
    đối chiếu từng kết quả với kỳ vọng độc lập
    ghi bằng chứng và chênh lệch
```

Đây không phải mã để triển khai một bộ máy cấp quyền. Quy tắc đánh giá phải tương đương với cơ chế sẽ được dùng thật; một mô hình giản lược cần được ghi giới hạn.

### Bước 4: điều tra chênh lệch

Theo đường giải thích: chủ thể nhận quyền từ đâu, resource thuộc phạm vi nào, quy tắc nào áp dụng và điều kiện nào quyết định kết quả.

Không chỉ sửa fixture cho đến khi báo cáo hết lỗi. Nếu dữ liệu thử sai, sửa có lý do; nếu policy sai, sửa policy; nếu yêu cầu chưa rõ, làm rõ tiêu chí trước khi chấp nhận kết quả.

### Bước 5: kiểm chứng điểm thực thi

Chọn những đường quan trọng để thử tích hợp trong môi trường được phép: API, vault, broker, JIT và đích.

Xác nhận các giới hạn được thực thi và lỗi từng phần được phản ánh. Một policy yêu cầu ghi phiên sẽ không đạt mục tiêu nếu gateway không ghi nhưng vẫn cho truy cập.

### Bước 6: quyết định thay đổi và theo dõi

Lưu kết quả, chênh lệch đã giải thích, giới hạn và kế hoạch triển khai. Mô phỏng là đầu vào cho phê duyệt thay đổi, không tự thay phê duyệt.

Sau triển khai cần so sánh trạng thái thực tế và có cách xử lý nếu xuất hiện tác động ngoài dự kiến.

## 8. Tình huống thực hành: thu hẹp quyền bảo trì sản xuất

### 8.1. Mục tiêu thay đổi

Policy hiện tại cho nhóm vận hành yêu cầu bảo trì trên một tập máy sản xuất quá rộng. Policy đề xuất cần:

- Chỉ cho đội thanh toán yêu cầu trên tài sản dịch vụ thanh toán.
- Giữ phê duyệt bắt buộc và grant có thời hạn.
- Sử dụng profile hạn chế thay cho quản trị toàn máy trong công việc này.
- Không cấp quyền tiết lộ secret.
- Giữ các điều kiện xác thực, thiết bị và đường phiên.
- Chặn yêu cầu khi thiếu thuộc tính bắt buộc.

Để giải thích tác động, có thể kiểm tra riêng thay đổi phạm vi resource và thay đổi profile, sau đó kiểm tra bản kết hợp.

### 8.2. Tập tình huống mẫu

| Mã | Đầu vào chính | Baseline quan sát | Kỳ vọng với candidate |
|---|---|---|---|
| C1 | Đúng đội, đúng tài sản thanh toán, đủ điều kiện | ALLOW | ALLOW với profile hạn chế |
| C2 | Đúng đội, tài sản dịch vụ báo cáo | ALLOW | DENY do ngoài phạm vi |
| C3 | Người không thuộc nhóm được phép | DENY | DENY |
| C4 | Đúng phạm vi nhưng thiếu phê duyệt | DENY | DENY |
| C5 | Grant hết hạn trước thời điểm đánh giá | DENY | DENY |
| C6 | Yêu cầu reveal secret thay vì mở phiên | DENY | DENY |
| C7 | Tài sản thiếu nhãn dịch vụ bắt buộc | Cần xác định hành vi thực tế | Không tự cho phép bằng mặc định rộng |
| C8 | Cùng tên máy nhưng tenant khác | DENY | DENY |
| C9 | Nhóm kế thừa khác vẫn cho quyền quản trị toàn cục | ALLOW từ nguồn khác | Phải được phát hiện và xử lý theo mục tiêu thay đổi |
| C10 | Điều kiện ghi phiên bắt buộc không thực thi được | Cần kiểm tra tích hợp | Không thực hiện như một phiên tuân thủ đầy đủ |

C2 là thay đổi thu hẹp có chủ đích. C1 không chỉ là ALLOW giữ nguyên: profile và giới hạn thực thi phải thay đổi như mong muốn.

C9 cho thấy sửa một policy chưa chắc đã loại bỏ quyền rộng nếu nguồn khác vẫn cấp quyền. Mô phỏng cần đủ đồ thị quyền để nhận biết đường đó.

### 8.3. Phát hiện lỗi do điều kiện thiếu dữ liệu

Giả sử candidate có ý định kiểm tra:

> Chỉ tài sản mang service ID thanh toán mới được phép.

Nhưng cấu hình thực tế dùng quy tắc mặc định:

> Nếu không có service ID thì coi là dùng chung và cho nhóm vận hành truy cập.

C7 sẽ phát hiện kết quả không phù hợp. Cần sửa cách xử lý dữ liệu thiếu hoặc quy trình phân loại tài sản, rồi chạy lại các tình huống bị ảnh hưởng và những bất biến liên quan.

Không sửa dữ liệu thử bằng cách luôn gắn nhãn thuận lợi để bỏ qua nhánh này.

### 8.4. Phát hiện mở quyền khi thêm tài sản

Một tài sản mới được gắn nhãn dịch vụ thanh toán. Với phạm vi động, candidate có thể cho đội truy cập ngay khi đủ điều kiện khác.

Cần mô phỏng thay đổi đó để xác nhận:

- Ai được sửa nhãn.
- Phạm vi phê duyệt là danh sách tĩnh hay tập động.
- Grant cũ có tự mở sang tài sản mới không.
- Tài khoản và profile thực thi có phù hợp tài sản mới không.

Không kết luận “policy không đổi nên không có thay đổi quyền”. Dữ liệu nguồn có thể làm quyền đổi mà policy giữ nguyên.

### 8.5. Kết luận của tình huống

Một kết quả chấp nhận được cần giải thích được mọi chênh lệch trong phạm vi đánh giá, xử lý nguồn quyền rộng còn lại và ghi các giới hạn.

Nếu C9 còn cho phép quản trị toàn cục ngoài mục tiêu, báo cáo không nên tuyên bố đã thu hẹp toàn bộ quyền. Có thể candidate đúng trong phần policy được sửa, nhưng mục tiêu quyền hiệu lực vẫn chưa đạt.

## 9. Replay, giả định và đánh giá song song

### 9.1. Replay lịch sử

Replay hữu ích để biết policy mới sẽ xử lý những yêu cầu đã quan sát như thế nào.

Cần quyết định câu hỏi đang hỏi là:

- Policy mới sẽ quyết định thế nào với trạng thái lúc sự kiện cũ xảy ra?
- Hay policy mới sẽ quyết định thế nào với những yêu cầu đó nhưng dùng trạng thái hiện tại?

Hai câu hỏi khác nhau. Nếu dùng membership hiện tại cho một sự kiện cũ, không nên gọi kết quả là tái dựng chính xác quá khứ.

### 9.2. Kiểm thử giả định

Có thể thay một chiều mỗi lần: grant hết hạn, đổi tenant, bỏ một phê duyệt, làm cũ xác thực hoặc thêm một nguồn quyền kế thừa.

Đây là cách kiểm tra biên và những trường hợp ít xuất hiện trong log. Cần giữ các đầu vào khác hợp lý để không tạo một tình huống không thể diễn giải.

Với khoảng thời gian, thử trước, tại và sau biên theo ngữ nghĩa đã xác định. Không dùng một giá trị “giờ hiện tại” thay đổi liên tục rồi khó giải thích kết quả.

### 9.3. Đánh giá song song

Một policy mới có thể được đánh giá bên cạnh policy đang thực thi trên yêu cầu quan sát được. Chỉ kết quả đã được chọn theo cấu hình vận hành mới được điều khiển quyền thật.

Đường đánh giá thử cần tránh tác động phụ: không tự gửi phê duyệt, cấp grant, đọc secret hoặc mở phiên. Cũng cần kiểm soát tải để mô phỏng không làm suy giảm hệ thống đang phục vụ.

Đánh giá song song giúp bổ sung dữ liệu thực tế, nhưng vẫn bỏ sót hành động không xuất hiện trong lưu lượng và không thay kiểm thử điểm thực thi.

## 10. Từ kết quả mô phỏng đến triển khai

Một hồ sơ thay đổi nên liên kết policy candidate, snapshot, bộ tình huống, kết quả, người rà soát và quyết định triển khai.

Tiêu chí chấp nhận có thể gồm:

- Những trường hợp bắt buộc cho phép hoạt động như yêu cầu.
- Không có mở quyền chưa được giải thích trong tập kiểm tra.
- Các bất biến quan trọng được giữ.
- Trạng thái lỗi hoặc thiếu dữ liệu đã được xử lý rõ.
- Nghĩa vụ quan trọng đã được kiểm chứng tại điểm thực thi.
- Kế hoạch theo dõi, đối soát và xử lý sự cố đã sẵn sàng.

Các tiêu chí và ngưỡng phải phù hợp thay đổi cụ thể; không có một tỷ lệ chênh lệch chung bảo đảm an toàn.

### 10.1. Triển khai có phạm vi được xác định

Có thể triển khai theo nhóm tài sản hoặc chủ thể đã được chấp thuận, quan sát kết quả rồi mở rộng. Phạm vi triển khai phải rõ để biết policy nào thực sự áp dụng cho một yêu cầu.

Không để một fallback không được kiểm soát tự dùng policy rộng hơn khi candidate từ chối. Nếu có đường khẩn cấp, nó phải được nhận diện và có quy tắc riêng.

### 10.2. Rollback và quyền đã cấp

Quay lại policy cũ chỉ thay một phần logic quyết định. Các grant, token, tài khoản tạm hoặc phiên đã tạo theo candidate có thể vẫn tồn tại.

Kế hoạch rollback cần xác định:

- Những grant nào được cấp trong khoảng áp dụng candidate.
- Có cần thu hồi, rút ngắn hoặc đánh giá lại không.
- Những phiên nào đang hoạt động.
- Credential đã tiết lộ hoặc thay đổi cần xử lý thế nào.
- Tác vụ cấp hoặc thu hồi đang chờ có thể chạy muộn không.

Tương tự, triển khai policy thu hẹp không tự bảo đảm quyền trực tiếp tại đích đã được gỡ. Cần đối soát và thực thi thu hồi riêng.

### 10.3. Theo dõi sau thay đổi

Đối chiếu quyết định thực tế với phạm vi đã mô phỏng, nhất là lỗi mới, chênh lệch nhóm, tài sản mới và điều kiện không có trong fixture.

Nếu xuất hiện hành vi ngoài dự kiến, cần giữ bằng chứng, xử lý quyền đang gây rủi ro và điều tra nguyên nhân. Không chỉ cập nhật bộ tình huống để kết quả trông phù hợp sau sự kiện.

## 11. Bằng chứng của một lần mô phỏng

Một báo cáo có thể gồm:

| Thành phần | Nội dung cần giải thích |
|---|---|
| Mục tiêu | Vấn đề và hành vi mong muốn |
| Phạm vi | Người dùng, tài sản, hành động và thời gian được kiểm tra |
| Policy | Baseline, candidate, phiên bản và nội dung tham chiếu |
| Bộ đánh giá | Phiên bản, thuật toán hợp nhất và cấu hình |
| Dữ liệu | Nguồn, snapshot, độ mới và khoảng trống |
| Tình huống | Cách chọn và kỳ vọng độc lập |
| Kết quả | Quyết định, profile, thời hạn, nghĩa vụ và lỗi |
| Chênh lệch | Phân loại chủ đích, hồi quy hoặc chưa giải thích |
| Kiểm thử thực thi | Những đường đã được xác minh và giới hạn |
| Quyết định thay đổi | Người chịu trách nhiệm và điều kiện triển khai |
| Theo dõi | Đối soát sau triển khai và trạng thái khắc phục |

Nếu sử dụng mã băm cho hiện vật, nó giúp đối chiếu đúng phiên bản dữ liệu. Nó không tự chứng minh snapshot đầy đủ hoặc nguồn dữ liệu đáng tin cậy.

Báo cáo và dữ liệu quyền có thể nhạy cảm dù không chứa credential. Cần phân quyền, bảo vệ toàn vẹn và giữ theo vòng đời phù hợp.

## 12. Những sai lầm thường gặp

**Chỉ thử trường hợp được phép.** Không thể biết policy quá rộng nếu không có trường hợp cần bị chặn.

**Dùng baseline làm đáp án đúng cho mọi tình huống.** Policy cũ có thể chứa lỗi; kỳ vọng cần căn cứ độc lập.

**Đổi policy và dữ liệu cùng lúc mà không phân tích.** Khó xác định nguyên nhân chênh lệch.

**Chỉ so sánh ALLOW/DENY.** Có thể bỏ sót profile rộng hơn, thời hạn dài hơn hoặc nghĩa vụ bị mất.

**Bỏ qua lỗi và dữ liệu thiếu.** Một lỗi bị che có thể trở thành đường cấp quyền khi tích hợp khác xử lý mặc định không giống nhau.

**Mô phỏng một role nhưng bỏ đồ thị quyền khác.** Người dùng vẫn có thể được cấp cùng quyền từ nhóm hoặc nguồn khác.

**Coi replay là bao phủ toàn bộ tương lai.** Lưu lượng quá khứ không chứa mọi tài sản mới, hành vi mới hoặc nhánh bị từ chối.

**Coi kết quả mô phỏng thay kiểm thử tích hợp.** Một quyết định đúng chưa chứng minh vault và đích thực thi đúng giới hạn.

**Rollback policy mà quên grant đang hoạt động.** Quyền đã được cấp cần vòng đời và thu hồi riêng.

## 13. Tự kiểm tra

1. Vì sao policy hợp lệ cú pháp chưa đủ để triển khai?
2. Cần cố định những dữ liệu nào để so sánh baseline và candidate?
3. Vì sao ALLOW ở cả hai bản vẫn có thể là một thay đổi quyền lớn?
4. Một grant không có trong replay có thể cho thấy điều gì về độ bao phủ?
5. Tại sao kỳ vọng kiểm thử không nên chỉ sao chép kết quả cũ?
6. Cần làm gì khi thiếu nhãn resource bắt buộc?
7. Mô phỏng có chứng minh một profile hạn chế thực sự chặn lệnh ngoài phạm vi không?
8. Rollback có tự kết thúc grant và phiên đã tạo không?

### Gợi ý trả lời

1. Cú pháp không chứng minh quyết định đúng, dữ liệu đủ hoặc điểm thực thi hoạt động.
2. Policy, bộ đánh giá, thời điểm và các snapshot chủ thể, resource, quyền cùng ngữ cảnh liên quan.
3. Profile, resource, thời hạn và nghĩa vụ có thể thay đổi dù nhãn quyết định giống nhau.
4. Replay không bao phủ tình huống đó; cần bổ sung giả định hoặc nguồn dữ liệu phù hợp.
5. Vì policy cũ có thể chứa lỗi hoặc khác mục tiêu mới.
6. Giữ trạng thái thiếu và xử lý theo chính sách; không mặc định mở rộng quyền.
7. Không. Cần kiểm thử tích hợp và kiểm tra quyền thực tế trong phạm vi được phép.
8. Không. Phải đánh giá và xử lý những trạng thái đã tồn tại riêng.

## Kết luận

Policy simulation giúp thay đổi quyền trong PAM trở nên có thể phân tích và kiểm chứng trước khi thực thi. Một lần mô phỏng có giá trị cần đầu vào có nguồn gốc, thời điểm rõ ràng, kỳ vọng độc lập và so sánh đầy đủ cả quyết định lẫn giới hạn đi kèm.

Kết quả đó cần được nối với phê duyệt thay đổi, kiểm thử điểm thực thi, theo dõi sau triển khai và đối soát grant. Khi giữ rõ các ranh giới này, mô phỏng hỗ trợ phát hiện mở quyền ngoài ý định mà vẫn phản ánh trung thực điều đã kiểm tra và điều còn chưa biết.
