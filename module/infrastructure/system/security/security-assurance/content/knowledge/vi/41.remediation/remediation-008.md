# Xác minh đã sửa (Remediation Verification): chứng minh một phát hiện bảo mật đã được khắc phục

**Xác minh đã sửa (remediation verification)** là quá trình kiểm tra có phương pháp và bằng chứng để xác định một điểm yếu, sai lệch kiểm soát hoặc phát hiện kiểm toán đã được xử lý **đúng phạm vi, đúng nguyên nhân và đúng tiêu chí khắc phục**, trên hệ thống thực sự cần bảo vệ. Việc một pull request đã merge, một change ticket đã đóng hoặc một đội vận hành thông báo “đã sửa” chỉ chứng minh một phần tiến độ; chưa tự chứng minh lỗ hổng đã biến mất hay kiểm soát đang vận hành hiệu quả.

Trong chương **Remediation** của module **SECURITY_SECURITY_ASSURANCE**, chủ đề này là bước nối giữa phân tích rủi ro, security requirements và controls, kết quả kiểm thử/audit, hành động sửa lỗi và **kết luận bảo đảm có thể truy vết**. Trọng tâm là trả lời:

> **Phát hiện nào đã được sửa, trên những tài sản và phiên bản nào, kiểm tra bằng phương pháp gì, ai xác nhận, bằng chứng ở đâu, còn hạn chế gì, và liệu có đủ căn cứ để đóng finding hay chưa?**

Một kết luận tốt thường có dạng: “Finding AUTHZ-017 được xác minh không còn tái hiện trên bản phát hành R tại ba đường truy cập thuộc phạm vi đã đối chiếu; bộ test quyền hợp lệ và trái quyền đều đạt, cấu hình production trùng bản đã thử, log giám sát có đủ; người xác minh độc lập đã chấp thuận đóng vào ngày T. Phạm vi không bao gồm các API ngoài danh mục release R.” Đây là một **tuyên bố có điều kiện và bằng chứng**, không phải cam kết rằng hệ thống sẽ không bao giờ phát sinh lỗi tương tự.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **correction**, **remediation**, **corrective action**, **validation**, **verification**, **retest**, **regression testing** và **closure**.
2. Viết tiêu chí đóng (*closure criteria*) gắn với phát hiện gốc, security objective và rủi ro.
3. Lập kế hoạch kiểm chứng đúng tài sản, phạm vi, phiên bản đã triển khai, điều kiện sử dụng và thời kỳ.
4. Sử dụng các phép thử dương/âm, kiểm thử hồi quy và kiểm tra hiệu quả vận hành để đánh giá bản sửa.
5. Kiểm tra bằng chứng triển khai, tính đầy đủ của population, nguyên nhân gốc và rủi ro tái diễn.
6. Ghi nhận các trạng thái **VERIFIED FIXED**, **PARTIALLY REMEDIATED**, **RETEST FAILED**, **NOT DEMONSTRATED** và **RISK ACCEPTED** mà không đánh đồng ý nghĩa.
7. Thiết kế hồ sơ xác minh có khả năng phục vụ audit, assurance case, risk register và chương trình security assurance liên tục.

---

## 2. “Đã sửa” nghĩa là gì trong security assurance?

Có nhiều mốc hoàn thành khác nhau và mỗi mốc cần bằng chứng riêng:

| Thuật ngữ | Ý nghĩa | Ví dụ bằng chứng | Chưa đủ kết luận |
|---|---|---|---|
| **Correction** (sửa tình trạng cụ thể) | Loại bỏ một biểu hiện hoặc trường hợp sai lệch đã quan sát | Thu hồi quyền sai của một tài khoản | Quy trình cấp quyền sẽ không tái diễn lỗi |
| **Remediation** (khắc phục) | Triển khai biện pháp xử lý điểm yếu hoặc rủi ro đã nêu | Sửa authorization policy, cập nhật service | Bản sửa thực sự hoạt động trên đúng production |
| **Corrective action** (hành động khắc phục nguyên nhân) | Xử lý nguyên nhân gốc để ngăn tái diễn, khi phù hợp | Thêm policy gate và test trước khi cấp quyền | Toàn bộ đường cấp quyền đều đã được thử |
| **Implementation validation** | Xác nhận bản sửa được xây dựng/triển khai theo thiết kế đã duyệt | Change approval, build, deploy record, config diff | Kiểm soát hành vi có thực sự đạt mục tiêu |
| **Remediation verification / retest** | Thực hiện phép kiểm tra độc lập hoặc có kiểm soát để xem finding đã hết theo tiêu chí | Test trước/sau, kết quả mới, evidence gốc | Mọi tình huống bảo mật ngoài phạm vi cũng an toàn |
| **Regression testing** | Kiểm tra bản sửa không phá chức năng hoặc control liên quan | Bộ test nghiệp vụ và security regression | Hành vi vận hành nhiều tháng đã được chứng minh |
| **Operating effectiveness review** | Kiểm tra control đã hoạt động đúng trong giai đoạn/tần suất quy định | Log, access review, đối soát trong kỳ | Mọi kỳ tương lai chắc chắn đạt |
| **Verified closure** | Người có thẩm quyền xác nhận đủ điều kiện đóng finding theo quy trình | Biên bản retest, hồ sơ duyệt closure | Không còn bất kỳ rủi ro nào trên hệ thống |

**Xác minh sửa đúng lỗi** và **chứng minh không thể tái diễn trong tương lai** là hai mức tuyên bố khác nhau. Có thể chứng minh một endpoint đã chặn truy cập chéo tenant theo bộ test xác định, nhưng không thể từ đó kết luận không tồn tại bất kỳ đường bypass nào.

Đối với control định kỳ như rà soát quyền mỗi quý, test chạy hôm nay có thể xác nhận **thiết kế và triển khai**; cần thêm bằng chứng trong chu kỳ phù hợp để kết luận về **hiệu quả vận hành**. Phải ghi trạng thái trung gian đúng mức.

## 3. Chu trình từ finding đến verified closure

Một quy trình khép kín có thể diễn đạt như sau:

~~~mermaid
flowchart TD
    A["Finding được xác nhận và phân loại rủi ro"] --> B["Khóa phạm vi, nguyên nhân và tiêu chí đóng"]
    B --> C["Lập corrective action plan, owner, hạn"]
    C --> D["Containment và triển khai thay đổi"]
    D --> E["Xác minh đúng phiên bản/tài sản đã triển khai"]
    E --> F["Retest lỗi gốc + biến thể + regression"]
    F --> G["Kiểm tra control vận hành và evidence"]
    G --> H{"Mọi tiêu chí bắt buộc đã đạt?"}
    H -- "Chưa" --> I["FAIL / PARTIAL / NOT DEMONSTRATED"]
    I --> J["Bổ sung bằng chứng, sửa tiếp hoặc quyết định rủi ro"]
    J --> D
    H -- "Đạt" --> K["Reviewer xác minh, lưu dấu vết"]
    K --> L["VERIFIED CLOSED"]
    L --> M["Giám sát tái diễn, drift, thay đổi"]
    M --> A
~~~

**Bước 1 — Xác nhận finding:** Lấy ID, severity, security requirement/control, bằng chứng ban đầu, phạm vi, ngày phát hiện, cách tái hiện và tác động. Chỉ chọn kịch bản kiểm chứng được ủy quyền và an toàn.

**Bước 2 — Chốt closure criteria:** Xác định trạng thái mong đợi, các đường truy cập hoặc tài sản bắt buộc, phiên bản phải kiểm tra, tiêu chuẩn vận hành, người nghiệm thu và phương pháp thu thập bằng chứng. Tiêu chí phải được thống nhất **trước retest**, không được hạ chuẩn sau khi test thất bại chỉ để báo PASS.

**Bước 3 — Thực thi CAP:** Có owner cuối cùng, các action cụ thể, điều kiện phòng ngừa tái diễn, mốc hoàn thành, biện pháp tạm và đánh giá tác động tới control khác.

**Bước 4 — Xác minh deployment:** Đối chiếu commit/build, image digest hoặc cấu hình thực thi, change approval và danh mục tài sản được triển khai; một thay đổi merge vào main chưa chắc đã đến mọi vùng production.

**Bước 5 — Retest:** Chạy lại điều kiện đã làm lộ điểm yếu, đồng thời kiểm tra biến thể có rủi ro và kiểm thử hành vi hợp lệ. Dùng dữ liệu/đường kiểm tra được phép để không gây lộ dữ liệu hoặc gián đoạn dịch vụ.

**Bước 6 — Đánh giá evidence:** Kiểm tra các log, kết quả thực thi, cấu hình, timestamp, phạm vi và sự nhất quán. Nếu bằng chứng không đầy đủ, ghi **NOT DEMONSTRATED** thay vì tuyên bố hoàn tất.

**Bước 7 — Review và đóng:** Người đủ thẩm quyền độc lập phù hợp kiểm tra hồ sơ, ghi kết luận, hạn chế, rủi ro còn lại và quyết định đóng/mở lại.

**Bước 8 — Theo dõi sau sửa:** Giám sát regression, policy drift, release mới hoặc incident liên quan; mở lại finding hay tạo finding liên kết nếu điều kiện tái diễn theo quy trình của tổ chức.

## 4. Chuẩn bị đầu vào cho phép xác minh

Để phép thử lặp lại được, cần đủ dữ liệu trước khi bắt đầu.

### 4.1. Bằng chứng của vấn đề ban đầu

Một finding chất lượng nên ghi:

| Thuộc tính | Cần biết |
|---|---|
| Finding ID / source | Xuất phát từ audit, pentest, scan, incident hay monitoring? |
| Criteria / control objective | Yêu cầu đã bị vi phạm hoặc chưa thể chứng minh là gì? |
| Affected assets | Tên dịch vụ, environment, account, region, version, endpoint, dữ liệu |
| Original condition | Hành vi/cấu hình sai được quan sát chính xác thế nào? |
| Reproduction steps | Cách tái hiện có kiểm soát, được phép và đã ghi nhận |
| Original evidence | Kết quả test, log, cấu hình, ảnh, ticket, timestamp |
| Impact/risk | Nguy cơ và mức độ tác động lên đối tượng nào? |
| Scope uncertainty | Những hệ thống tương tự có thể bị ảnh hưởng nhưng chưa kiểm tra? |
| Planned fix | Thay đổi dự kiến, containment và root cause giả định hoặc đã xác minh |
| Owner / due / reviewer | Người xử lý, người ra quyết định và người kiểm chứng |

Nếu không lưu dấu vết ban đầu, dễ rơi vào tình huống **không tái hiện được vì test sai điều kiện**, rồi kết luận điểm yếu đã được sửa. Khi dữ liệu gốc không còn, cần ghi rõ giới hạn thay vì tự dựng kết quả.

### 4.2. Baseline thực thi

Bản sửa phải được so với tình trạng trước ở **cùng thuộc tính bảo mật**. Ví dụ:

- **Trước:** tài khoản tenant A có thể nhận bản ghi của tenant B qua một API export.
- **Sau mong đợi:** API từ chối/ẩn đối tượng ngoài quyền, không trả dữ liệu nhạy cảm, không tạo side effect trái quyền; luồng hợp lệ vẫn thành công.
- **Căn cứ:** chính sách phân quyền bản đã phê duyệt và kết quả kiểm thử trên artifact đã triển khai.

Không dùng “số dòng code đã đổi”, “PR đã review” hoặc “100% job CI xanh” thay cho phép đo của hành vi cần sửa.

## 5. Định nghĩa closure criteria trước khi retest

Closure criteria là **hợp đồng kiểm chứng** giữa control owner, đội sửa lỗi và bên đánh giá. Một bộ tiêu chí chặt chẽ thường bao gồm:

1. **Correct scope:** mọi asset, account, role, region, đường truy cập và phiên bản thuộc finding được nhận diện, không bỏ instance cũ.
2. **Fixed behavior:** hành vi vi phạm ban đầu không còn tái hiện trong điều kiện test phù hợp.
3. **Root cause addressed:** nguyên nhân hoặc đường lỗi tương tự được xử lý; không chỉ chặn một mẫu đầu vào cụ thể khi lớp lỗi rộng hơn.
4. **No security/function regression:** luồng hợp lệ, security controls liên quan, logging và tác vụ nghiệp vụ vẫn hoạt động.
5. **Deployment proof:** bản sửa thực sự có mặt ở môi trường và phiên bản cần bảo vệ.
6. **Operating evidence when applicable:** control được thực thi qua khoảng thời gian hoặc chu kỳ phù hợp với criteria.
7. **Evidence complete:** kết quả, phạm vi, timestamp, run ID, test inputs an toàn, reviewer và limitations được ghi.
8. **Approval:** người có thẩm quyền đánh giá và xác nhận closure; residual risk/ngoại lệ được xử lý riêng.

Ví dụ cho finding thiếu MFA ở quyền đặc biệt:

~~~text
Finding: IAM-017
Requirement: Tài khoản quản trị tương tác production phải bị cưỡng chế MFA.

Closure requirements:
  [ ] Population tài khoản đặc quyền được đối chiếu đầy đủ.
  [ ] Mọi đường đăng nhập tương tác trong scope đều yêu cầu MFA.
  [ ] Luồng cấp quyền chuẩn và khẩn cấp không tạo account bypass.
  [ ] Ngoại lệ có đúng thẩm quyền, hạn và compensating control.
  [ ] Bản config đã triển khai tại các account/region cần bảo vệ.
  [ ] Có log test và kết quả kiểm tra lại từ reviewer.
  [ ] Không xuất hiện regression trong authentication hợp lệ.
  [ ] Hành động theo dõi drift được thiết lập.

Pass chỉ khi tất cả điều kiện bắt buộc đã được chứng minh.
~~~

Nếu kiểm tra chỉ một tài khoản sau sửa nhưng finding liên quan tất cả account production, không thể tự kết luận toàn bộ đã đáp ứng. Cần thu hẹp kết luận hoặc mở rộng việc kiểm chứng.

## 6. Xây dựng ma trận kiểm thử phù hợp với loại finding

Mỗi loại sai lệch cần phương pháp xác minh khác nhau. Không có một câu lệnh hay scan đủ để đóng mọi remediation.

| Finding | Bằng chứng triển khai | Retest trọng tâm | Regression / operating check |
|---|---|---|---|
| **BOLA/IDOR, broken authorization** | Code/config change ở service, endpoint inventory | Người dùng ngoài quyền không đọc/sửa được object; các role đặc biệt được thử | User hợp lệ vẫn thao tác được, logs không lộ dữ liệu |
| **MFA thiếu enforcement** | IdP/IAM policy, rollout trên account liên quan | Đường đăng nhập thuộc scope không bypass; test emergency provisioning | Đăng nhập hợp lệ, exception lifecycle và IAM audit |
| **Excessive permissions** | Role diff, approved access matrix | Quyền không cần thiết bị loại, không còn đường cấp lại | Service phụ thuộc chạy đúng, access review và drift alert |
| **Secret bị lộ** | Secret rotation/revocation, thay secret usage | Secret cũ bị vô hiệu, phiên/credential liên quan được đánh giá | Ứng dụng vẫn kết nối bằng secret mới; CI scanning và quản lý secret |
| **CVE/package yếu** | SBOM, version, image digest, deployment | Thành phần chịu ảnh hưởng được cập nhật; kiểm tra advisory và scanner theo phạm vi | Regression nghiệp vụ, asset inventory và rollback plan |
| **TLS/config yếu** | Config diff, runtime deployment | Đường kết nối chỉ hỗ trợ bộ chính sách được duyệt | Client hợp lệ kết nối được; giám sát config drift |
| **Audit logging thiếu** | Pipeline/config, nguồn event | Sự kiện mẫu đi từ nguồn đến đích, đúng định danh và thời gian | Độ bao phủ theo thời kỳ, alert khi mất log |
| **Backup không restore được** | Job, quyền, key/backup policy | Thử restore, integrity, giải mã, dữ liệu và chức năng | RTO/RPO, đường quản trị DR và security controls |
| **Rà soát quyền định kỳ thiếu** | Workflow, quy trình, reviewer assignments | Thử luồng review, hành động thu hồi và đối soát | Một hoặc nhiều kỳ hoạt động theo criteria |
| **Thay đổi thiếu phê duyệt** | Enforcement trong change pipeline | Không thể áp dụng thay đổi thuộc scope khi thiếu approval | Emergency change vẫn được kiểm soát và audit |
| **Lỗ hổng từ nhà cung cấp** | Thư xử lý, build/version, bằng chứng đối tác | Xác minh trên dịch vụ tích hợp thực tế, không chỉ giấy xác nhận | Contract responsibility, monitoring và rủi ro phụ thuộc |

Đối với lỗ hổng có nhiều kỹ thuật khai thác, bộ test cần bao gồm các **biến thể hợp lý của lớp lỗi** theo threat model và phạm vi. Tuy nhiên, retest phải được thực hiện với quyền cho phép, dữ liệu thử và cơ chế an toàn phù hợp; không phải tái tạo tấn công gây ảnh hưởng trên hệ thống thật.

## 7. Positive test, negative test và regression test

Một bản sửa tốt phải vừa **chặn điều không được phép**, vừa **giữ nguyên điều được phép**.

### 7.1. Negative test

Xác minh hệ thống từ chối hành vi vi phạm tiêu chí. Ví dụ với tenant isolation:

- User tenant A cố đọc object chỉ thuộc tenant B bằng đối tượng kiểm thử đã được cấp phép.
- Một request không có session hợp lệ không được trả hồ sơ.
- User thiếu quyền export không tạo job export hoặc lấy nội dung kết quả được.
- Một thao tác bị từ chối không tạo side effect trái quyền ở database, event bus hoặc object storage.

Mã HTTP có thể là 403 hoặc 404 tùy chính sách bảo vệ sự tồn tại của tài nguyên. Tiêu chí quyết định là **không tiết lộ dữ liệu/trạng thái trái quyền**, không mặc định mọi API phải dùng cùng status code.

### 7.2. Positive test

Đồng thời xác minh người có quyền đúng vẫn thực hiện được thao tác:

- User A đọc bản ghi của chính tenant A.
- Tenant-admin thao tác đúng đối tượng đã được cấp quyền.
- Service identity chạy batch trong phạm vi cho phép.
- Luồng audit logging/monitoring ghi nhận được kết quả theo yêu cầu.

Nếu bản sửa “thành công” bằng cách chặn toàn bộ người dùng, negative test có thể PASS nhưng hệ thống **không đạt mục tiêu nghiệp vụ**. Đây là regression rõ ràng, không phải hoàn tất khắc phục.

### 7.3. Regression test

Kiểm tra những chức năng và control có thể bị ảnh hưởng do sửa lỗi:

- Authentication, authorization, caching, pagination, export, async jobs.
- Schema, data integrity, idempotency và transaction semantics.
- Performance, service availability, retry/rollback.
- Logging, rate limit, KMS/secrets, network policy.
- Quy trình vận hành và support/admin/break-glass được phép.

Ví dụ pseudocode ở môi trường thử nghiệm được cấp quyền:

~~~text
Given:
  tenant_A_user = user hợp lệ thuộc tenant A
  tenant_B_record = bản ghi thử chỉ thuộc tenant B
  tenant_A_record = bản ghi thử thuộc tenant A

Negative:
  response = api.read_record(tenant_A_user, tenant_B_record)
  assert response không có dữ liệu của tenant B
  assert database không bị sửa sai bởi yêu cầu bị từ chối

Positive:
  response = api.read_record(tenant_A_user, tenant_A_record)
  assert response đúng dữ liệu đã cấp quyền

Regression:
  assert authn, authz, telemetry và các luồng hợp lệ còn hoạt động
  assert kiểm thử ở release/route/role đã công bố
~~~

Pseudocode minh họa ý nghĩa kiểm chứng, không phải bộ test đầy đủ. Khi triển khai thực tế, cần dùng fixture cách ly, dữ liệu giả lập, giới hạn thao tác, phiên bản đúng và ghi run ID để audit được.

## 8. Kiểm chứng đúng phiên bản đã triển khai

Một nguồn false positive phổ biến là **test bản đã sửa ở staging**, nhưng production đang chạy image cũ hoặc một region chưa nhận bản vá.

Cần chứng minh chuỗi:

~~~text
Finding ID
   ↓
Code/config change + review
   ↓
Commit / IaC version / package version
   ↓
Build artifact + integrity identifier
   ↓
Deployment approval & run record
   ↓
Actual runtime workload/version/region/account
   ↓
Retest result ở đúng đối tượng
   ↓
Reviewer confirmation
~~~

Các phương pháp có thể gồm đối chiếu:

- Git commit và mã change được phê duyệt.
- Container image digest, artifact checksum hoặc package version.
- Deployment manifest thực tế trên cluster/region, không chỉ file dự định áp dụng.
- Runtime API/build info được bảo vệ, scan version trên workload thật.
- Config state, policy version, rollout percentage và feature flags.
- Danh mục instance hoặc account đang phục vụ production.

Đối với canary rollout, một phần traffic có thể đến bản mới, một phần đến bản cũ. Retest một request may mắn đi vào bản mới không chứng minh **mọi instance liên quan** đã được sửa. Cần kiểm tra rollout completion và đường routing, hoặc ghi rõ phạm vi mới được xác minh.

Nếu bản sửa ở source nhưng binary đang chạy khác commit, kết luận chính xác là **fix implemented in source; production remediation not demonstrated**.

## 9. Kiểm tra nguyên nhân gốc và tính bền vững của bản sửa

Sửa triệu chứng là cần thiết khi có nguy cơ tức thời. Để giảm tái diễn, phải xem lỗi xuất hiện do cá biệt hay do **cơ chế hệ thống**.

### 9.1. Ví dụ: tài khoản nghỉ việc vẫn còn quyền

**Phát hiện:** 8 tài khoản đã nghỉ việc vẫn có quyền vào một hệ thống nội bộ.

- **Correction:** vô hiệu hóa 8 tài khoản được phát hiện.
- **Root-cause hypothesis:** sự kiện offboarding từ HR không được hệ thống IAM xử lý khi queue mất kết nối.
- **Corrective action:** xử lý retry, dead-letter queue, đối soát độc lập danh sách nhân sự và quyền, cảnh báo nếu chưa thu hồi trong hạn.
- **Verification:** tái hiện có kiểm soát trường hợp queue lỗi và phục hồi; xác minh quyền được thu hồi khi sự kiện được xử lý; kiểm tra population thực trong cửa sổ đã định; bảo đảm không mất log.

Nếu chỉ chứng minh 8 tài khoản không còn hoạt động, có thể ghi **8 trường hợp đã sửa**, nhưng chưa đủ khẳng định **quy trình offboarding đã được khắc phục**.

### 9.2. Tìm nguyên nhân bằng 5 Whys

~~~text
Vì sao tài khoản nghỉ việc còn quyền?
  -> Hệ thống không xử lý sự kiện offboarding.
Vì sao?
  -> Queue bị lỗi khi dịch vụ IAM gián đoạn.
Vì sao không phát hiện?
  -> Không có alert cho sự kiện chưa xử lý theo thời hạn.
Vì sao không có alert?
  -> Yêu cầu control mới chỉ kiểm tra luồng thành công.
Cải tiến cần kiểm chứng:
  -> Retry, monitoring backlog, đối soát HR/IAM,
     test failure-path và có người chịu trách nhiệm xử lý.
~~~

“5 Whys” chỉ là một công cụ, không chứng minh mặc định có một nguyên nhân duy nhất. Có thể có cả lỗi ownership, IAM policy, account inventory và vendor integration. Khi điều tra chưa hoàn tất, phải ghi **hypothesis** thay vì tuyên bố nguyên nhân gốc đã xác minh.

## 10. Scope completeness: đã sửa hết nơi có lỗi chưa?

Finding trên một asset có thể là đại diện cho lỗi chung của image, policy, thư viện, pipeline hoặc quy trình. Xác minh chỉ trên đúng một máy ban đầu có thể bỏ sót hàng trăm nơi cùng nguồn lỗi.

Các câu hỏi cần trả lời:

1. **Population là gì?** Tất cả workload/route/account thuộc phạm vi finding được định nghĩa ra sao?
2. **Nguồn inventory có đủ?** Có tài khoản cloud, cluster, region, instance hay luồng không được quản lý tập trung?
3. **Đường triển khai nào còn bản cũ?** Rollout, canary, autoscaling template, backup image, warm standby, disaster recovery site.
4. **Cùng root cause có ở nơi khác?** Service dùng chung middleware, module, Helm chart, IAM role, workflow.
5. **Các ngoại lệ nào tồn tại?** Ai duyệt, có bù trừ, giới hạn thời gian và mức tác động?
6. **Phép kiểm tra nào bao phủ được tập đó?** Full inventory scan, sampling có giải thích hoặc kiểm thử đại diện theo rủi ro.

Ví dụ 2/50 máy chủ đã được vá lỗi CVE nhưng việc kiểm tra chỉ nhắm hai máy gốc. Kết luận hợp lệ là **hai máy đã được kiểm tra**; không thể ghi “CVE remediated across production” nếu 48 máy còn lại chưa được đánh giá.

Với phương pháp lấy mẫu, cần ghi population, sampling unit, cách chọn, kích thước, ngoại lệ và giới hạn suy luận. Không chuyển tỷ lệ trong mẫu không xác suất thành tỷ lệ toàn bộ hệ thống.

## 11. Cân bằng xác minh trên staging và production

Kiểm thử ở production cho độ đại diện cao, nhưng có thể gây ảnh hưởng nếu thử khai thác, ghi dữ liệu hoặc kích hoạt failover. Vì vậy hãy kết hợp phương pháp theo rủi ro:

| Môi trường | Có thể chứng minh | Hạn chế |
|---|---|---|
| Unit/integration test | Logic sửa hoạt động với input và fixture được xác định | Có thể khác cấu hình và dependency production |
| Staging đại diện | Các service phối hợp, negative/positive và regression | Tải, IAM, network, dữ liệu hoặc identity có thể khác |
| Production-safe verification | Artifact/config thật, luồng synthetic an toàn, audit logs | Thường không thử được mọi kỹ thuật tấn công hay lỗi phá hoại |
| Diễn tập có kiểm soát | Đánh giá failover/restore và dependency thực | Cần kế hoạch, điều kiện dừng, đánh giá tác động |
| Quan sát vận hành | Control hoạt động trong thời kỳ xác định | Có thể không chứng minh trường hợp hiếm nếu telemetry thiếu |

Đối với vulnerability exploit hoặc thao tác phá hoại, cần thử ở **môi trường được phép và cách ly** rồi xác nhận production đã triển khai artifact/config tương đương bằng kỹ thuật không gây hại. Đừng mặc định việc chạy một payload từng gây lỗi trên production là bắt buộc để xác minh.

**Phép nối staging → production cần bằng chứng:** image digest, cấu hình ảnh hưởng control, feature flag, dependency và security policy phải tương thích. Chỉ nói “staging giống production” là chưa đủ.

## 12. Bằng chứng xác minh đạt yêu cầu phải gồm gì?

Một kết luận verified fixed cần nguồn gốc có thể kiểm tra:

| Nhóm bằng chứng | Ví dụ | Chứng minh điều gì |
|---|---|---|
| **Original finding** | ID, criteria, baseline test, asset/version, impact | Điều đã sai và tiêu chí cần sửa |
| **Root cause và CAP** | Phân tích, owner, kế hoạch, quyết định risk | Vì sao sửa và cách ngăn tái diễn |
| **Change implementation** | PR, code review, change approval, config diff | Hành động được xây dựng/phê duyệt |
| **Deployment** | Image digest, deploy log, inventory, runtime config | Đúng bản sửa đã đến đúng tài sản |
| **Retest** | Test case, expected/actual, run ID, data và môi trường | Điều kiện vi phạm đã bị chặn trong scope |
| **Regression** | Kết quả positive tests, security control tests, performance/smoke | Chức năng và control liên quan vẫn đạt |
| **Operating evidence** | Log, access review, SIEM event, drill result trong kỳ | Control thực thi theo thời gian/chu kỳ đã định |
| **Closure review** | Reviewer, ngày, kết luận, limitations, sign-off | Quyết định đóng có thẩm quyền và có thể truy vết |

Một hiện vật từ scanner cần kèm **phiên bản công cụ/rule**, cấu hình scan, độ bao phủ, thời điểm, kết quả có thể kiểm tra và thông tin asset. Câu “scan clean” có thể sai nếu scanner không còn xác thực được tới host hoặc plugin phát hiện bị tắt.

Một hash của tệp evidence giúp kiểm tra nội dung không đổi so với bản đã lưu, nhưng **không chứng minh dữ liệu nguồn đúng hoặc đủ ngay từ đầu**.

### 12.1. Bảo vệ kho bằng chứng

Evidence có thể chứa endpoint, account, cấu hình bảo mật, log nhạy cảm hoặc dữ liệu khách hàng. Cần phân quyền tối thiểu, ghi nhật ký truy cập, lưu version và thời hạn theo chính sách. Dùng **mã tham chiếu** trong ticket/report, hạn chế chép secret và dữ liệu thật vào bằng chứng chia sẻ rộng. Khi xử lý incident, yêu cầu bảo toàn chứng cứ có thể cần cách quản lý riêng.

## 13. Mẫu hồ sơ xác minh đã sửa

Mẫu YAML sau chỉ để minh họa cấu trúc, không phải tiêu chuẩn bắt buộc và **không phải bằng chứng thật**:

~~~yaml
verification_id: REM-VER-EXAMPLE-008
finding_id: AUTHZ-017
service: customer-records-api
control_id: AUTHZ-OBJECT-01
finding_source: security-assessment
risk_level_at_discovery: high

original_condition:
  affected_path: "GET /v2/records/{record_id}"
  issue: "cross-tenant object access was not rejected"
  baseline_evidence_ref: "restricted/findings/AUTHZ-017/baseline"
  original_release: "R-1"

closure_criteria:
  - "all relevant routes, roles and environments inventoried"
  - "cross-tenant object access rejected without data exposure"
  - "authorized access still works"
  - "control enforcement present in deployed runtime"
  - "security logging and regression tests pass"
  - "independent reviewer approves closure"

implementation:
  corrective_action_id: CAP-AUTHZ-017
  change_id: CHG-EXAMPLE-102
  artifact_digest_ref: "restricted/builds/release-R/digest"
  deployment_evidence_ref: "restricted/deployments/release-R"
  environment: production
  release: R

retest:
  run_id: AUTHZ-RETEST-2026-008
  tested_environment: "approved-representative-environment"
  build_equivalence_evidence_ref: "restricted/deployments/build-diff"
  negative_tests: PASS
  positive_tests: PASS
  regression_tests: PASS
  scope_coverage_review: PENDING
  evidence_refs:
    - "restricted/tests/negative-access"
    - "restricted/tests/positive-access"
    - "restricted/tests/security-regression"

assessment:
  remediation_status: NOT_DEMONSTRATED
  reason: "scope coverage review still pending"
  residual_risk_ref: "restricted/risks/AUTHZ-017"
  reviewer_role: INDEPENDENT_SECURITY_REVIEWER
  reviewer_decision: PENDING
  next_action: "complete route and identity population reconciliation"
~~~

Trong ví dụ, các test có thể PASS nhưng trạng thái tổng thể vẫn là **NOT DEMONSTRATED** vì chưa xác minh đầy đủ scope. Đây là cách ghi trung thực; không tự chuyển sang VERIFIED FIXED khi thiếu điều kiện chặn.

## 14. Quản lý trạng thái finding và quyết định đóng

Một workflow nên phân biệt rõ tình trạng công việc và kết luận của bên kiểm tra:

~~~text
OPEN
  ↓
TRIAGED
  ↓
ACTION_PLAN_APPROVED
  ↓
IMPLEMENTED
  ↓
RETESTING
  ├── RETEST_FAILED → REOPENED / REWORK
  ├── PARTIALLY_REMEDIATED → remaining actions
  ├── NOT_DEMONSTRATED → evidence/coverage gap
  └── VERIFIED_FIXED → VERIFIED_CLOSED

RISK_ACCEPTED:
  Luồng riêng với người duyệt, phạm vi, lý do,
  thời hạn, giám sát và risk register.
~~~

Một tổ chức có thể dùng tên trạng thái khác; điều quan trọng là **ý nghĩa và điều kiện chuyển trạng thái**.

- **IMPLEMENTED:** đã triển khai hành động; chưa được độc lập xác minh hiệu quả.
- **RETEST_FAILED:** còn tái hiện vấn đề hoặc tiêu chí bắt buộc chưa đạt.
- **PARTIALLY_REMEDIATED:** đã xử lý một phần tài sản/luồng nhưng còn phần tồn đọng.
- **NOT DEMONSTRATED:** chưa có đủ evidence để khẳng định đã đạt; có thể chưa biết lỗi còn hay đã hết.
- **VERIFIED FIXED:** kiểm chứng đạt theo closure criteria trong phạm vi.
- **VERIFIED CLOSED:** hồ sơ và thẩm quyền kiểm tra/duyệt closure đã hoàn thành.
- **RISK ACCEPTED:** quyết định xử lý rủi ro còn lại có điều kiện; không có nghĩa control đã đạt.

Không nên chuyển trạng thái chỉ vì PR merge, owner nhắn “fixed”, deadline đến hạn hoặc scanner tự chuyển một finding sang “resolved”. Công cụ tự động có thể cung cấp dữ liệu, nhưng **phải kiểm tra nguyên nhân của trạng thái và độ đầy đủ của phép thử**.

## 15. Trường hợp khó: không tái hiện được lỗi

**Not reproducible** có thể do:

- Lỗi đã được sửa thật.
- Endpoint hoặc tài sản đã bị tắt, đổi đường dẫn hoặc không còn reachable.
- Tài khoản test không đủ quyền để kích hoạt điều kiện trước đây.
- Data fixture khác khiến nhánh lỗi không được đi qua.
- Công cụ, rule, payload hoặc config đã thay đổi.
- Scanner không có credential, timeout hoặc bị network policy chặn.
- Lỗi chỉ xuất hiện trong race condition, tải cao hoặc trạng thái dữ liệu đặc biệt.

Do đó **không tái hiện được ≠ đã sửa**, trừ khi bối cảnh và điều kiện đã được xác minh đầy đủ. Cách xử lý:

1. Đối chiếu finding gốc và preconditions.
2. Kiểm tra log, asset, version, route, credential, dữ liệu và test method.
3. Tìm evidence của thay đổi thực tế giải quyết nguyên nhân.
4. Dùng kiểm tra tương đương được cho phép, kết hợp code review và runtime/config evidence.
5. Nếu vẫn chưa đủ, ghi **NOT DEMONSTRATED** kèm lý do và bước tiếp theo.

Nếu asset được decommission, có thể đóng finding theo chính sách **khi chứng minh asset không còn hiện diện hoặc không còn đường gây rủi ro**, không đơn giản vì scanner không thấy nó.

## 16. Partial fixes, compensating controls và risk acceptance

Không phải mọi lỗi có thể sửa triệt để ngay. Có thể cần containment, chính sách ngoại lệ, thay thế kiến trúc hoặc hợp tác nhà cung cấp. Hồ sơ xác minh cần phân biệt:

| Trường hợp | Đánh giá phù hợp |
|---|---|
| Một trong ba region được vá; hai region còn lỗi | **Partially remediated**; phải ghi region và rủi ro còn lại |
| Feature đã tắt làm đường lỗi không reachable | Có thể giảm phơi nhiễm; cần chứng minh flag, route và khả năng bật lại có kiểm soát |
| WAF rule chặn pattern đã biết nhưng code còn lỗi | Có compensating control; chưa tự là root-cause remediation |
| Vendor đã xác nhận đang sửa nhưng chưa có release | Action in progress; kiểm tra mitigation và phụ thuộc |
| Có ngoại lệ được duyệt để giữ một tài khoản không tuân thủ | Risk accepted trong phạm vi; không được ghi control compliant nếu tiêu chí không cho phép |
| Bản sửa đã chạy, nhưng chưa qua một kỳ access review | Implementation validated; operating effectiveness pending |

Đối với ngoại lệ, cần owner, người có thẩm quyền phê duyệt, lý do, scope, thời hạn, biện pháp bù trừ, cách giám sát và trigger xem lại. **Ngoại lệ nội bộ không thể tự xóa nghĩa vụ pháp luật hoặc hợp đồng** nếu tổ chức không có quyền quyết định như vậy.

Nếu một finding liên quan đến nhiều control, có thể đóng action đã xác minh riêng và giữ finding tổng còn mở cho tới khi tất cả closure criteria bắt buộc đạt.

## 17. Ví dụ hoàn chỉnh: sửa lỗi phân quyền API hồ sơ

**Bối cảnh giả định:** Một nền tảng SaaS đa tenant có 36 endpoint liên quan hồ sơ. Đợt security assessment phát hiện tại **GET /v2/reports/export** người dùng tenant A có thể nhận nội dung của một báo cáo tenant B qua đường export bất đồng bộ. Phát hiện mang mã **AUTHZ-017**, yêu cầu liên quan **AUTHZ-OBJECT-01**.

### 17.1. Baseline trước sửa

| Mục | Tình trạng |
|---|---|
| Claim | Mọi đường API trong inventory phải kiểm tra tenant/object authorization |
| Điều quan sát | Export job kiểm tra role khi tạo job, nhưng bước tải kết quả chưa kiểm tra tenant ownership |
| Evidence | Test có dữ liệu giả lập ở môi trường được phép, log của request, ảnh hưởng dữ liệu đã kiểm soát |
| Risk | Người dùng có thể xem nội dung thuộc tenant khác |
| Root cause | Authorization chỉ nằm ở bước tạo job, không thực thi lại ở bước lấy kết quả |
| Scope uncertainty | Các đường export/download khác có thể dùng chung handler |

Không chia sẻ dữ liệu thật của khách hàng trong bằng chứng; sử dụng fixture thử nghiệm và tài khoản được phép.

### 17.2. CAP và closure criteria

**Correction tạm thời:** giới hạn tính năng export có rủi ro hoặc kiểm soát đường tải xuống, giám sát truy cập và xác minh không làm gián đoạn không cần thiết.

**Corrective action dài hạn:** thực thi kiểm tra tenant/object ownership cả lúc tạo job và khi đọc kết quả; dùng cơ chế authorization chung, thêm test cho mọi route export/download và yêu cầu policy gate trong CI.

| Action | Owner ví dụ | Tiêu chí kiểm chứng |
|---|---|---|
| A1: sửa authorization tại downloader | App security team | Mọi request trái tenant được từ chối không lộ dữ liệu |
| A2: đối chiếu route dùng chung handler | API platform | Inventory bao gồm toàn bộ route/async flow |
| A3: regression cho role/tenant và luồng hợp lệ | QA/Security engineering | Negative và positive tests được lưu với run ID |
| A4: xác minh rollout | SRE/Platform | Toàn bộ runtime thuộc scope chạy đúng build/policy |
| A5: review độc lập | Security assurance | Cổng closure đầy đủ và limitations có ghi nhận |

### 17.3. Kết quả kiểm chứng vòng thứ nhất

Giả sử:

- PR được merge và pipeline PASS.
- Bản mới chạy ở một region production; region còn lại chưa triển khai.
- Test đã kiểm tra handler chính, nhưng chưa kiểm tra đường legacy download.
- Người dùng hợp lệ vẫn export được theo test.
- Chưa có bản đối chiếu toàn bộ inventory.

**Kết luận đúng:** Có bằng chứng triển khai và test đạt **một phần**. Finding tổng **PARTIALLY REMEDIATED**, chưa đủ điều kiện verified fixed cho toàn production. Không báo “đã đóng AUTHZ-017”.

### 17.4. Kết quả kiểm chứng vòng thứ hai

Giả sử sau đó:

1. Cả hai region có image digest đúng và feature flag tương ứng đã được xác minh.
2. Đối chiếu router, gateway và worker cho thấy ba đường export/download liên quan đã được nhận diện.
3. Negative tests từ tenant sai, token thiếu và role không đủ quyền đều không trả dữ liệu.
4. Positive tests cho user hợp lệ và support role được cấp quyền đúng đều đạt.
5. Download link hết hạn/thu hồi đúng tiêu chí, kết quả cũ không vượt qua kiểm tra quyền.
6. Audit logging ghi sự kiện bị từ chối và truy cập hợp lệ theo quy tắc; không lộ nội dung nhạy cảm trong log.
7. Reviewer độc lập kiểm tra test run, sample data, phạm vi và deployment evidence.

Nếu tất cả điều kiện bắt buộc đã được chứng minh, có cơ sở ghi **VERIFIED FIXED** và theo quy trình chuyển **VERIFIED CLOSED** trong phạm vi release và kịch bản đã nêu. Cần giữ hành động theo dõi thay đổi route mới để ngăn tái diễn.

### 17.5. Phần kết luận có bằng chứng

> Finding AUTHZ-017 đã được kiểm chứng khắc phục trên hai region production của release R: cả ba đường export/download liên quan đã được đối chiếu với inventory và kiểm thử negative/positive theo vai trò, tenant và tình trạng token. Hành vi trái quyền không còn tái hiện ở các trường hợp đã thử; luồng hợp lệ, log và deployment equivalence được xác nhận. Hồ sơ evidence tham chiếu test run V-017, rollout record D-017 và review R-017; không suy rộng ra endpoint mới sau release R.

Tuyên bố này rõ phạm vi và không khẳng định “không có bất kỳ lỗ hổng authorization nào”.

## 18. Ví dụ khác: từ “đã bật logging” tới bằng chứng vận hành

**Finding:** Một API quan trọng không gửi audit event tới SIEM trong 12 ngày; chính sách yêu cầu log các hoạt động đặc quyền.

**Implementation:** Sửa agent/forwarder, cải thiện retry, phát cảnh báo khi không có event hoặc queue tồn đọng.

**Verification kỹ thuật:** Tạo sự kiện kiểm thử hợp lệ, kiểm tra từ source tới destination có đủ user, action, timestamp và asset; xác minh không bỏ event hoặc lộ dữ liệu nhạy cảm.

**Verification vận hành:** Quan sát cửa sổ đủ đại diện, đối chiếu event count, kiểm tra alert khi giả lập đường truyền lỗi theo quy trình an toàn.

**Giới hạn:** Log được khôi phục trong tháng sau **không làm bằng chứng cho 12 ngày đã mất**. Nếu finding gốc có yêu cầu phải bảo toàn log quá khứ, cần báo phần không thể khôi phục và nghĩa vụ retention tương ứng.

Có thể đóng **action sửa pipeline** sau khi thử thành công, nhưng giữ **evidence gap của kỳ cũ** trong audit report/risk register nếu không có nguồn độc lập phục hồi dữ liệu lịch sử.

Đây là ví dụ cho thấy **đã sửa hiện trạng** và **đã chứng minh tuân thủ trong quá khứ** là hai kết luận khác nhau.

## 19. Báo cáo remediation verification cho audit và assurance case

Một bộ hồ sơ đủ kiểm toán phải hỗ trợ chuỗi truy vết:

~~~text
Security objective / Risk
          ↓
Requirement / Control
          ↓
Finding + Original evidence
          ↓
Root cause + CAP + Owner
          ↓
Change / Deployment evidence
          ↓
Retest + Regression + Operating evidence
          ↓
Verification decision + Reviewer
          ↓
Closure / Residual risk / Follow-up
~~~

**Trong audit:** management response có thể báo action đã triển khai; auditor hoặc reviewer theo cơ chế được duyệt kiểm tra **điều kiện đóng** và sự phù hợp với tiêu chí audit. Không tự thay đổi phát hiện lịch sử khi một action đã sửa lỗi ở kỳ sau.

**Trong assurance case:** finding mở là một *counterevidence/defeater* của claim liên quan. Khi có retest được xác minh, cập nhật claim và evidence reference đúng phiên bản; không dùng một sửa lỗi cục bộ để tự động nâng top-level claim nếu các nhánh khác chưa đạt.

**Trong risk management:** risk register phản ánh mức rủi ro còn lại, ngoại lệ và thời hạn. Rủi ro có thể giảm sau fix nhưng vẫn tồn tại dưới dạng rủi ro khác; closure finding không đồng nghĩa chấp nhận mọi rủi ro.

## 20. Đo hiệu quả remediation verification

Các chỉ số có thể giúp phát hiện vấn đề hệ thống:

| Chỉ số | Cách dùng | Hạn chế |
|---|---|---|
| **Verified closure rate** | Tỷ lệ finding đóng sau retest đủ evidence | Cần xét severity và chất lượng review |
| **Retest failure rate** | Tỷ lệ action đã thực hiện nhưng test không đạt | Có thể do giải pháp yếu hoặc tiêu chí test chưa đúng |
| **Reopen / recurrence rate** | Theo dõi lỗi lặp lại sau closure | Cần phân biệt lỗi cùng root cause với lỗi mới |
| **Time to verified remediation** | Thời gian từ phát hiện đến verified fixed | Khác với thời gian merge PR hoặc deploy |
| **Coverage of affected assets** | Tỷ lệ asset/route/account trong population đã xác minh | Phải có inventory đầy đủ |
| **Evidence completeness** | Tỷ lệ hồ sơ có nguồn, test, version, reviewer | Đếm trường không đủ đánh giá chất lượng evidence |
| **Overdue high-risk findings** | Ưu tiên những vấn đề có tác động lớn còn mở | Cần xem biện pháp tạm và risk acceptance |
| **Control drift after remediation** | Đo khả năng cấu hình/quy trình quay về sai lệch | Chỉ số phụ thuộc telemetry và phạm vi |

Một dashboard 100% ticket closed có thể che các finding chưa được kiểm chứng. Tách **implemented**, **verified**, **risk accepted** và **not demonstrated** giúp lãnh đạo hiểu đúng tiến độ và mức bảo đảm.

## 21. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Merge PR = fixed | Production có thể chưa nhận bản sửa | Chứng minh artifact/runtime/deployment |
| Scanner không thấy CVE = đã sửa | Scanner có thể thiếu credential, host hoặc plugin | Kiểm tra coverage, version và lý do kết quả |
| Chỉ test payload ban đầu | Có thể còn bypass cùng lớp lỗi | Thử biến thể theo root cause và threat model |
| Chỉ chạy negative test | Có thể chặn luôn nghiệp vụ hợp lệ | Positive và regression test |
| Chỉ thử staging khác production | Không chứng minh control thực tế | Deployment/config equivalence và production-safe check |
| Bỏ qua region/account/worker cũ | Vẫn còn phiên bản dễ bị khai thác | Xác minh toàn population và rollout |
| “Không tái hiện” thành PASS | Có thể do test setup sai | Xác minh precondition, root cause và evidence |
| Đóng khi có ticket Done | Không đánh giá hiệu quả | Retest, log, closure criteria và reviewer |
| Sửa một tài khoản, bỏ workflow gây lỗi | Lỗi tái diễn | Corrective action xử lý root cause |
| Đổi tiêu chí sau khi test FAIL | Kết luận thiếu trung thực | Quản lý phiên bản, phê duyệt thay đổi scope |
| Chấp nhận rủi ro được ghi compliant | Sai ý nghĩa status | Tách remediation khỏi risk decision |
| Bằng chứng log không có thời điểm | Khó chứng minh giai đoạn | UTC timestamp, source, run ID và audit trail |
| Retest phá hỏng dữ liệu production | Gây thiệt hại không cần thiết | Dữ liệu giả, sandbox, kiểm thử có kiểm soát |
| Không xác minh độc lập | Thiên lệch và rủi ro bỏ sót | Reviewer có thẩm quyền phù hợp |
| Không theo dõi sau closure | Policy drift hoặc release mới làm lỗi quay lại | Regression gate và continuous monitoring |

## 22. Bài tập thực hành

### Tình huống A — Quyền quản trị bị cấp quá rộng

Một audit finding nói: “Một workflow cấp quyền production cho phép engineer tự cấp admin role mà không có phê duyệt.” Đội IAM đã xóa role admin của ba account được chỉ ra và cung cấp screenshot sau sửa.

**Yêu cầu:**

1. Phân biệt correction và corrective action trong tình huống.
2. Viết ít nhất năm closure criteria đo được để xác minh toàn bộ vấn đề.
3. Đề xuất nguồn chứng minh inventory account/role đầy đủ.
4. Thiết kế negative và positive tests cho cấp quyền thường/khẩn cấp có quyền cho phép.
5. Cho biết khi nào screenshot đủ để nói “đã sửa ba account”, khi nào chưa thể nói “workflow đã được sửa”.
6. Chọn evidence vận hành để kiểm tra quyền không được cấp lại qua đường cũ.

### Tình huống B — Lỗ hổng ở thư viện dịch vụ

Một scanner báo một phiên bản dependency có CVE trên sáu service production. Team cập nhật dependency ở repo chính và CI PASS, nhưng dashboard triển khai mới chỉ hiển thị ba service dùng image mới.

**Yêu cầu:**

1. Nêu trạng thái đúng của finding và vì sao chưa VERIFIED FIXED.
2. Đề xuất cách kiểm chứng sáu runtime artifact/version bằng bằng chứng không gây hại.
3. Liệt kê regression tests cho một thay đổi thư viện quan trọng.
4. Giải thích vì sao “scan không còn alert” chưa đủ nếu scanner chỉ quét ba service.
5. Thiết kế hồ sơ retest và một điều kiện mở lại finding sau release.

### Tình huống C — Logging và bằng chứng lịch sử

Một hệ thống ngừng chuyển log quản trị trong 14 ngày quý III. Tháng 10, nhóm vận hành sửa pipeline và cho thấy 30 ngày log đủ nguồn.

**Yêu cầu:**

1. Cần những phép kiểm tra nào để chứng minh forwarder hiện hoạt động?
2. Có thể kết luận toàn bộ log quý III đã được thu thập đầy đủ không?
3. Phân biệt closure cho action kỹ thuật, compliance finding lịch sử và residual risk.
4. Viết kết luận verification có scope, thời điểm, bằng chứng và giới hạn.
5. Nêu cách phát hiện logging drift trong tương lai.

### Tình huống D — Bản sửa chỉ chặn sai lệch trên một đường

Một API đa tenant có 20 route và một export job. Sau khi sửa lỗ hổng đọc trái quyền ở route GET, test negative cho GET PASS, nhưng đường export chưa được kiểm tra và user hợp lệ không thể tải bản ghi của chính mình.

**Yêu cầu:**

1. Nêu ít nhất hai lý do không thể đóng finding.
2. Thiết kế coverage matrix cho các đường API và các vai trò.
3. Phân biệt negative test với positive/regression test.
4. Xây dựng CAP kiểm tra root cause, deployment, export và luồng hợp lệ.
5. Viết status báo cáo cho management và nội dung cần security assurance retest.

**Gợi ý:** Khi bằng chứng chưa đủ để kết luận, hãy dùng **NOT DEMONSTRATED**; khi biết có tiêu chí bắt buộc không đạt, dùng **RETEST FAILED** hoặc trạng thái tương đương. Không làm đẹp số lượng closed findings bằng cách đổi nghĩa trạng thái.

## 23. Ghi nhớ

**Xác minh đã sửa** là bước chuyển từ **“chúng tôi đã thực hiện thay đổi”** sang **“chúng tôi có bằng chứng rằng điểm yếu đã được xử lý đúng mục tiêu và đúng phạm vi”**. Muốn kết luận đáng tin, người đánh giá phải biết **finding gốc, tiêu chí khắc phục, nguyên nhân, tập tài sản, bản đã triển khai, kết quả negative/positive/regression tests, evidence vận hành và người phê duyệt closure**.

Trong **SECURITY_SECURITY_ASSURANCE**, chuỗi assurance đầy đủ là:

**Risk / Security requirement → Finding có bằng chứng → Root cause / CAP → Fix + deployment proof → Retest + regression + operating evidence → Independent verification → Verified closure hoặc residual-risk decision → Monitoring và đánh giá lại.**

Không có bằng chứng đủ thì chưa thể khẳng định đã sửa; có phản chứng thì phải ghi nhận; đã chấp nhận rủi ro cũng không biến control chưa đạt thành compliant. Một chương trình remediation hiệu quả luôn có thể trả lời **sửa điều gì, trên đâu, kiểm chứng ra sao, còn rủi ro gì và khi nào phải thử lại**.
