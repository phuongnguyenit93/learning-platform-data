# Thay đổi vận hành có kiểm soát và diễn tập sự cố

Một hệ thống microservices hiếm khi ngừng thay đổi sau khi phát hành. Nhóm kỹ thuật phải điều chỉnh cấu hình, đổi phiên bản ứng dụng, nâng thư viện, xoay bí mật, thay chính sách mạng, mở rộng tài nguyên, di chuyển dữ liệu và bảo trì hạ tầng. Mỗi thay đổi có thể cải thiện hiệu năng hoặc an toàn, nhưng đồng thời tạo ra một đường phát sinh sự cố: cấu hình sai, hợp đồng API không tương thích, tăng tải lên dependency, quá hạn timeout, mất quyền truy cập hoặc thay đổi trạng thái dữ liệu không thể đảo ngược.

**Thay đổi vận hành có kiểm soát** là cách đưa một thay đổi vào hệ thống bằng quy trình có mục tiêu, phạm vi, điều kiện cho phép, quan sát và phương án dừng/khôi phục xác định trước. **Diễn tập sự cố** là việc chủ động thực hành phát hiện, phối hợp, giảm tác động và phục hồi trong một tình huống được thiết kế an toàn, thay vì đợi một sự cố thật mới kiểm tra năng lực của tổ chức.

Hai hoạt động bổ sung cho nhau: thay đổi được kiểm soát giúp giảm xác suất hoặc phạm vi sự cố; diễn tập giúp phát hiện khoảng trống trong runbook, quyền truy cập, giám sát và đường khôi phục trước khi sự cố thật xảy ra.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt thay đổi theo kế hoạch, thay đổi khẩn cấp, thao tác vận hành định kỳ và diễn tập lỗi.
2. Liên hệ quyết định thay đổi với **SLI**, **SLO**, **error budget**, rủi ro của dịch vụ và các dependency liên quan.
3. Thiết kế một change record có mục tiêu, phạm vi, chủ sở hữu, bằng chứng kiểm thử, kế hoạch triển khai, rollback và tiêu chí thành công.
4. Dùng progressive delivery, feature flag, maintenance window và promotion gate khi phù hợp để giới hạn blast radius.
5. Tổ chức game day và chaos experiment với giả thuyết, steady state, inject fault, guardrails và điều kiện dừng.
6. Thực hành các vai trò trong incident response: incident commander, technical lead, communications lead và scribe.
7. Đánh giá khả năng khôi phục qua các số đo như MTTD, MTTA, MTTR, RTO, RPO và business impact.
8. Viết post-incident review và chuyển bài học từ diễn tập thành các cải tiến cụ thể có người chịu trách nhiệm.
9. Phân biệt một diễn tập thành công với một hệ thống thực sự đã đủ năng lực chống chịu mọi lỗi.

## 2. Vì sao microservices làm thay đổi vận hành khó hơn?

Một ứng dụng đơn khối thường có một đường triển khai chính; microservices có nhiều thành phần với vòng đời độc lập:

~~~text
Client
  |
  v
API Gateway
  |
  +--> Order Service --------> Order DB
  |       |
  |       +--> Inventory Service ----> Inventory DB
  |       |
  |       +--> Payment Service ------> Payment Provider
  |       |
  |       +--> Publish Event --------> Message Broker
  |                                      |
  |                                      v
  |                                 Notification Worker
  |
  +--> Catalog Service -------> Cache / Catalog DB
~~~

Thay đổi `payment.timeout` ở Order Service có thể làm tăng lỗi cho người dùng, tăng retry tới Payment Service, tăng các giao dịch có trạng thái chưa xác định và gián tiếp làm backlog của message broker lớn hơn. Một thay đổi Kubernetes NetworkPolicy có thể cắt kết nối tới DNS hoặc external payment provider dù tất cả Pod vẫn đang Running.

Vì vậy, một thay đổi vận hành cần hiểu:

- **Đường đi của request:** service nào gọi service nào; sync/async boundaries; deadline và retries.
- **Tài nguyên chia sẻ:** database, cache, broker, gateway, cluster node, service mesh, cloud quota.
- **Hợp đồng dữ liệu:** event schema, database schema, API contract, idempotency và version compatibility.
- **Phạm vi người dùng:** region, tenant, user cohort, endpoint quan trọng và luồng nghiệp vụ.
- **Quan sát được hay không:** có đủ SLI, telemetry, log/trace và alert để phân biệt phiên bản mới với phiên bản ổn định?
- **Phục hồi được hay không:** rollback code có đủ không, hay còn migration, stateful side effects và dữ liệu đã ghi?

Một thao tác đơn giản ở một service có thể là thay đổi rủi ro cao nếu chạm đến dependency có nhiều consumer hoặc dữ liệu không thể phục hồi.

## 3. Thay đổi vận hành khác sự cố như thế nào?

| Khái niệm | Mục tiêu | Đặc điểm |
|---|---|---|
| **Planned change** | Chủ động nâng chất lượng, bảo trì hoặc phát hành | Có kế hoạch, đánh giá rủi ro và cửa sổ triển khai |
| **Standard change** | Thực thi một thao tác lặp lại, rủi ro thấp, đã được phê duyệt theo quy trình | Có runbook tự động và điều kiện tiền đề rõ |
| **Emergency change** | Khôi phục dịch vụ hoặc giảm rủi ro đang xảy ra | Cần nhanh nhưng vẫn có owner, audit và kiểm tra tối thiểu |
| **Incident** | Ứng phó với suy giảm khả năng phục vụ hoặc tác động khách hàng | Ưu tiên giới hạn thiệt hại và khôi phục an toàn |
| **Game day** | Luyện tập ứng phó và kiểm tra quy trình trong tình huống giả lập | Có kịch bản, vai trò, quan sát và điều kiện dừng |
| **Chaos experiment** | Kiểm tra một giả thuyết về tính chịu lỗi bằng cách tạo nhiễu có kiểm soát | Có steady state, fault injection, giới hạn blast radius và đánh giá |
| **Disaster recovery exercise** | Xác minh năng lực phục hồi sau mất dữ liệu, vùng triển khai hoặc hạ tầng | Đo RTO/RPO, integrity và khả năng vận hành sau restore |

Không đồng nhất chaos engineering với việc “ngẫu nhiên tắt máy”. Một thí nghiệm chỉ có giá trị khi đã biết **muốn chứng minh giả thuyết gì**, có đường quan sát, giới hạn thiệt hại và phương án dừng.

## 4. SLI, SLO và error budget trong quyết định thay đổi

**SLI (Service Level Indicator)** là chỉ số mô tả chất lượng dịch vụ như tỷ lệ request thành công, latency hoặc tỷ lệ job hoàn tất đúng hạn.

**SLO (Service Level Objective)** là mục tiêu cho SLI trong một cửa sổ xác định, ví dụ:

- 99,9% request `POST /orders` hợp lệ hoàn tất thành công trong 30 ngày.
- 99% request đọc catalog có latency không quá 200 ms trong cửa sổ 28 ngày.
- 99,5% event `OrderCreated` được xử lý trong 5 phút.

**Error budget** là phần không đạt mục tiêu mà SLO cho phép trong cửa sổ đó. Với SLO thành công 99,9% theo request, ngân sách lỗi là 0,1% số request hợp lệ trong cùng cửa sổ. Cách tính phải nhất quán với định nghĩa SLI, mẫu số và các request được loại trừ; không được lấy thời gian downtime thay cho tỷ lệ lỗi request khi SLI không đo theo thời gian.

Ví dụ ước lượng minh họa:

~~~text
SLO success: 99,9%
Cửa sổ: 30 ngày
Số request hợp lệ: 1.000.000
Lỗi tối đa theo budget: 1.000 request

Một sự cố có 700 lỗi được tính vào SLI
  -> đã tiêu thụ khoảng 70% budget của ví dụ.
~~~

Điều quan trọng hơn số phép tính là **chính sách sử dụng budget**. Nếu ngân sách lỗi đang cạn hoặc burn rate tăng nhanh, nhóm có thể hạn chế thay đổi rủi ro cao, ưu tiên sửa reliability và yêu cầu kiểm soát chặt hơn với các release còn lại. Đây là ví dụ về một chính sách có thể áp dụng, không có nghĩa mọi tổ chức phải tự động đóng băng mọi thay đổi khi budget về 0.

### 4.1. Error budget không phải “quota để làm hỏng”

Budget giúp cân bằng tốc độ thay đổi với độ tin cậy đã cam kết. Nó không cho phép bỏ qua rủi ro bảo mật, sai lệch thanh toán, mất dữ liệu hoặc vi phạm pháp lý. Các failure mode có tác động không thể đảo ngược phải có guardrail riêng, dù SLO latency/availability vẫn đang tốt.

Một thay đổi có thể không gây 5xx nhưng làm sai giá bán, tạo trùng giao dịch hoặc gửi sai email. Vì vậy, ngoài SLI kỹ thuật cần quan sát **business correctness** và các invariant quan trọng.

## 5. Mô hình quyết định trước thay đổi: người dùng, dịch vụ và dữ liệu

Trước một thay đổi, đội vận hành cần trả lời:

1. **Tại sao thay đổi?** Khắc phục lỗi, tăng capacity, nâng an toàn, giảm chi phí hay thay đổi chức năng?
2. **Tác động ở đâu?** Service, namespace, cluster, region, tenant, endpoint và dependency.
3. **Đâu là rủi ro chính?** Downtime, data loss, permission failure, latency regression, backlog hoặc thông điệp xử lý trùng?
4. **Có được triển khai từng phần không?** Canary theo traffic, theo Pod, theo region, theo tenant hoặc feature flag?
5. **Nhận biết tốt/xấu bằng cách nào?** SLI, health, cảnh báo, business KPIs và logs/traces đã gắn version.
6. **Rollback hoặc roll-forward ra sao?** Điều kiện bắt đầu, thời gian dự kiến, tác động đến dữ liệu và ai có quyền thực hiện.
7. **Khi thiếu dữ liệu thì sao?** HOLD, không tự suy đoán hệ thống khỏe chỉ vì dashboard rỗng.
8. **Ai chịu trách nhiệm?** Change owner, người quan sát, on-call của dependency, người có quyền phê duyệt emergency action.

### Phân loại độ rủi ro

| Ví dụ | Rủi ro điển hình | Kiểm soát phù hợp |
|---|---|---|
| Sửa dashboard title | Thấp | Review và audit đơn giản |
| Tăng số replicas trong ngưỡng đã thử | Thấp đến vừa | Capacity check, auto scale guardrail, quan sát |
| Đổi timeout/retry ở gateway | Vừa đến cao | Load test, canary, theo dõi timeout và retries |
| Bật policy mạng mới | Cao nếu chạm critical path | Dry run/kiểm tra rule, staged rollout, backout |
| Di chuyển database primary | Cao | Rehearsal, bảo vệ dữ liệu, kiểm tra replication, failback |
| Xoay secret thanh toán | Cao | Overlap/rotation plan, kiểm tra mọi Pod và job |
| Xóa schema cũ | Rất cao nếu còn consumer | Contract matrix, compatibility gate, kế hoạch phục hồi |
| Tắt feature flag không còn dùng | Tùy ảnh hưởng | Kiểm tra cohort và behavior đã tương đương |

Mức rủi ro không chỉ phụ thuộc loại thay đổi; còn phụ thuộc lượng traffic, thời điểm, maturity của runbook và khả năng khôi phục.

## 6. Change record: mô tả đủ để một người khác kiểm tra

Một thay đổi nên có một bản ghi ngắn gọn, đọc được, có phiên bản và bằng chứng.

~~~yaml
change:
  id: CHG-EXAMPLE-204
  service: order-service
  environment: production
  owner: team-orders
  purpose: "Adjust outbound payment timeout"
  artifactRevision: "git:8cf13b0"
  configRevision: "orders-config-v18"

scope:
  region: "region-a"
  initialTrafficPercent: 5
  dependencies:
    - payment-service
    - order-db

risk:
  primary: "Potential increased timeout/retry rate"
  dataMigration: false

preconditions:
  - "SLO indicators available and fresh"
  - "No conflicting production rollout"
  - "Rollback config revision validated"
  - "Payment on-call reachable"

success:
  - "Payment timeout rate within approved threshold"
  - "Checkout completion rate not regressing"
  - "No error-budget burn-rate alert"

onFailure: "Stop promotion and revert config rollout"
onUnknown: "Hold and investigate telemetry"
~~~

Đây là YAML **minh họa nội dung change record**, không phải schema của một công cụ triển khai cụ thể. Bản ghi thật có thể được lưu trong ticket, GitOps PR, release orchestration hoặc hệ thống quản lý thay đổi.

Tối thiểu cần có: nguyên nhân, phạm vi, owner, bằng chứng trước thay đổi, cách triển khai, điều kiện dừng, cách phục hồi và xác nhận sau thay đổi. Không cần điền biểu mẫu dài khi thao tác đã được tự động hóa và đủ bằng chứng; tránh biến change management thành thủ tục phê duyệt hình thức.

### 6.1. Liên kết thay đổi với phiên bản thực sự

Không ghi “deploy phiên bản mới nhất” mà thiếu định danh. Với ứng dụng nên dùng commit SHA, image digest và manifest revision. Với cấu hình nên dùng config revision/feature flag version. Với database cần migration ID. Khi điều tra sự cố, các mốc này giúp biết điều gì đã thay đổi **trước khi** SLI bắt đầu suy giảm.

## 7. Change calendar, freeze và cửa sổ triển khai

Không phải thời điểm nào cũng có cùng rủi ro. Một thay đổi trên Payment Service trong giờ cao điểm có thể gây tác động lớn hơn vào giờ thấp điểm; nhưng triển khai ban đêm khi không có người trực cũng có rủi ro nếu phát hiện chậm.

Cân nhắc:

- Dự báo traffic và phân phối theo khu vực.
- Lịch chiến dịch, batch reconciliation, payroll, flash sale hoặc peak season.
- Khả năng có mặt của người phụ trách dịch vụ và dependency.
- Những thay đổi khác trên cùng cluster/DB/broker.
- Sự cố chưa được khôi phục hoặc error budget đang burn nhanh.
- Thời gian cần để quan sát đủ mẫu và thời gian phục hồi.

**Change freeze** có thể có ý nghĩa khi dịch vụ đang rất bất ổn hoặc sự kiện kinh doanh có rủi ro cao. Nhưng freeze phải có phạm vi, ngoại lệ và điều kiện kết thúc; không dùng nó như giải pháp thay cho cải thiện rollout và năng lực khôi phục.

## 8. Tự động hóa preflight

Một preflight có thể kiểm tra tự động:

1. Artifact và config revision khớp với kế hoạch đã phê duyệt.
2. Pipeline compile, unit, integration, security và contract checks đã đạt ngưỡng.
3. Không có deployment khác đang chiếm cùng target.
4. Thay đổi tương thích với Pod/consumer cũ đang chạy.
5. Backups, replication và restore path được xác minh nếu thay đổi có rủi ro dữ liệu.
6. Dashboards/alerts/trace correlation đủ phân biệt canary và stable.
7. Có capacity để chạy canary, blue-green hoặc rollback về stable.
8. Có quyền thực hiện pause, abort và traffic shift khi cần.
9. Bản ghi change có owner, thời điểm, phiên bản và điều kiện dừng.
10. Cảnh báo SLO hoặc incident có mức độ chặn phát hành được xử lý theo policy.

Preflight khác điều kiện chứng minh thay đổi thành công. Việc API Kubernetes chấp nhận Deployment mới chỉ xác nhận một phần cấu hình được áp dụng; cần nhìn vào request, business KPI và tình trạng dependency sau khi chuyển traffic.

## 9. Triển khai từng phần để giới hạn blast radius

Thay đổi nhỏ có thể gây hậu quả lớn nếu đồng thời áp trên 100% replicas. Một lộ trình staged rollout:

~~~text
Stable: 100%, New: 0%
          |
          v
Canary 5% -> observe -> gate
          |
       PASS?
    /    |      \
  YES   NO     UNKNOWN
   |     |        |
   v     v        v
 25%   ABORT     HOLD
   |
   v
50% -> observe -> gate
   |
   v
100% -> post-change monitoring
~~~

Đối với cấu hình, có thể tạo một deployment revision riêng và rollout một nhóm Pods. Đối với feature flags, có thể mở theo cohort. Đối với cluster/network changes, có thể triển khai ở một namespace hoặc region không trọng yếu trước khi mở rộng.

### 9.1. Chọn canary theo tác động, không chỉ theo phần trăm

Một canary 5% không hữu ích nếu:

- Traffic đi vào không kích hoạt code path vừa sửa.
- Tất cả request là health checks, không có business transactions.
- Cohort không đại diện cho khách hàng sẽ chịu thay đổi.
- Backend shared dependency bị ảnh hưởng bởi cả stable và canary, làm so sánh khó hiểu.
- Đường thay đổi là schema/database migration tác động tất cả users trước khi chuyển traffic.
- Khối lượng request quá thấp khiến không đủ mẫu để ra quyết định.

Cần chọn cơ chế giới hạn phạm vi phù hợp nhất. Với migration dữ liệu, giới hạn theo batch/partition và kiểm tra checkpoint có thể hữu ích hơn canary HTTP đơn thuần.

## 10. Promotion gate: PASS, FAIL và UNKNOWN

Một gate tốt phải phân biệt ba kết quả:

- **PASS:** các điều kiện bắt buộc có đủ dữ liệu và đạt ngưỡng; có thể tăng phạm vi.
- **FAIL:** có vi phạm ngưỡng hoặc invariant cần chặn; dừng hoặc rollback theo playbook.
- **UNKNOWN:** thiếu mẫu, mất telemetry, query trễ, baseline không hợp lệ hoặc dependency có incident; giữ rollout để điều tra.

| Signal | Ví dụ điều kiện | Khi không đáp ứng |
|---|---|---|
| Ready replicas | Số replica sẵn sàng không dưới mức tối thiểu | HOLD hoặc FAIL tùy loại lỗi |
| 5xx rate | Không vượt ngưỡng SLO/change policy | FAIL nếu có đủ dữ liệu |
| p95/p99 latency | Không tăng vượt mức cho phép so với stable | FAIL/HOLD |
| Payment success | Không giảm dưới ngưỡng nghiệp vụ | FAIL ngay với regression nghiêm trọng |
| Queue lag | Không tăng bất thường sau thay đổi | HOLD/FAIL |
| Dependency health | Không có lỗi lan sang downstream | HOLD/FAIL |
| Metric freshness | Mẫu mới, nhãn version đúng, đủ request | UNKNOWN nếu thiếu |
| Error-budget burn | Không có mức burn báo động | FAIL/HOLD theo policy |
| Security/data invariant | Không có truy cập sai, giao dịch trùng hoặc mất dữ liệu | FAIL và kích hoạt xử lý sự cố |

Các ngưỡng phải được chọn từ SLO, baseline và độ nhạy nghiệp vụ thực tế. Con số minh họa không phải mặc định áp cho mọi tổ chức. Đặc biệt, **không có metric** không được giải thích thành “0 lỗi”.

## 11. SLO burn-rate và cửa sổ quan sát

SLO có thể chỉ báo cáo giá trị tổng hợp 30 ngày, trong khi một release xấu gây lỗi trong vài phút. **Burn rate** so sánh tốc độ tiêu thụ error budget hiện tại với tốc độ tương ứng nếu phân bổ đều qua cửa sổ SLO.

Ví dụ với mục tiêu 99,9%, error fraction cho phép là 0,1%. Nếu tỷ lệ request lỗi là 1% trong một cửa sổ có đủ mẫu, burn rate so với budget đó khoảng 10 lần. Đây là ví dụ theo request-based SLI với sample đủ lớn, không phải phép đo tác động của một incident cụ thể nếu định nghĩa SLI khác.

Một chính sách có thể dùng multi-window alerts để tránh vừa chậm phát hiện vừa nhiễu. Nhưng change gate còn cần:

- Minimum number of requests hoặc jobs có ý nghĩa.
- Window bắt đầu **sau khi** canary thật sự nhận traffic.
- Dữ liệu telemetry mới và có nhãn version/cohort.
- So sánh stable/canary trên các loại request tương đương.
- Một tín hiệu business correctness độc lập với SLO kỹ thuật.
- Tình trạng dependency chung có thể làm sai lệch kết luận.

Không phải lúc nào “không thấy burn-rate alert” cũng là bằng chứng đủ để promote. Alert có thể chưa kích hoạt vì quy tắc suppress, mất data hoặc chưa đủ thời gian.

## 12. Kế hoạch rollback trước khi triển khai

Một kế hoạch “nếu lỗi thì rollback” chưa đủ. Cần trả lời rõ:

1. **Rollback cái gì?** Traffic, image digest, config, feature flag, network policy, database schema hay credential?
2. **Ai thực hiện?** Người/on-call hoặc controller có quyền trên đúng môi trường.
3. **Điều kiện kích hoạt?** 5xx vượt ngưỡng, invariant sai, không đủ readiness, latency cao, error-budget burn.
4. **Mất bao lâu?** Thời gian đo thực tế của traffic switch, Pod readiness, cache warm-up hoặc failover.
5. **State có đảo ngược được không?** Message đã phát, payment đã thực hiện, DB migration đã chạy.
6. **Xác nhận phục hồi ra sao?** Không chỉ lệnh thành công mà còn traffic/SLI/business KPI trở lại trạng thái chấp nhận.
7. **Khi rollback không an toàn?** Roll-forward fix, tắt feature flag, compatibility layer hoặc restore đã diễn tập.

### 12.1. Rollback code không hoàn tác dữ liệu

~~~text
App v1 -> DB schema v1
   |
   | EXPAND schema
   v
App v1 + v2 chạy song song -> DB schema mở rộng
   |
   | v2 bắt đầu ghi định dạng mới
   v
Rollback image v2 -> v1
   |
   +--> v1 có còn hiểu được dữ liệu đã ghi hay không?
~~~

Không được mặc định v1 đọc được schema/data do v2 ghi. Dùng expand–migrate–contract, compatibility tests, versioned events và kế hoạch compensation/reconciliation. Với giao dịch tài chính, side effect đã hoàn tất cần được xử lý bằng nghiệp vụ phù hợp, không phải “xóa log” hay chỉ chuyển image cũ lên.

## 13. Runbook và playbook: làm được khi đang áp lực

**Runbook** là hướng dẫn thao tác lặp lại, ví dụ xác minh readiness, rollback Deployment, xử lý queue lag. **Incident playbook** mô tả cách phản ứng trước một loại sự cố có triệu chứng đặc trưng như Payment timeout tăng cao hoặc database failover.

Một runbook hữu ích phải có:

- Mục tiêu, service/namespace/cluster cụ thể.
- Điều kiện kích hoạt và dấu hiệu không được phép thực hiện.
- Quyền và tài khoản cần dùng.
- Lệnh hoặc thao tác từng bước, kèm ý nghĩa.
- Bằng chứng phải quan sát sau mỗi bước.
- Điều kiện dừng/khôi phục nếu kết quả không như mong đợi.
- Cách liên hệ on-call và eskalate.
- Ngày/phiên bản cập nhật, người sở hữu và kết quả lần diễn tập gần nhất.

Đừng viết runbook chỉ gồm “restart service” nếu không giải thích vì sao restart an toàn, có đủ replicas không và chuyện gì xảy ra với request hoặc message đang xử lý.

## 14. Ví dụ runbook: rollback một Deployment Kubernetes

Đoạn sau là ví dụ cho Deployment stateless, với điều kiện image/config revision cũ còn tương thích và release controller không đồng thời tự động ghi đè trạng thái.

~~~bash
# Xác định revision và trạng thái hiện tại.
kubectl -n orders rollout history deployment/orders-api

# Kiểm tra rollout và Pods trước khi thao tác.
kubectl -n orders rollout status deployment/orders-api
kubectl -n orders get pods -l app=orders-api

# Nếu đã xác định cần rollback một revision theo playbook:
kubectl -n orders rollout undo deployment/orders-api

# Theo dõi rollback, không chỉ nhìn lệnh đã gửi thành công.
kubectl -n orders rollout status deployment/orders-api

# Tiếp tục xác minh ở gateway/tracing/metrics:
# traffic thực đã quay về stable revision,
# error rate, latency, business completion rate đã phục hồi.
~~~

Lệnh chỉ là **ví dụ trên môi trường đã được cấp quyền**. Trong hệ thống GitOps, controller có thể đồng bộ lại desired state và ghi đè undo; phải xử lý nguồn khai báo GitOps hoặc dùng chức năng rollback của release controller theo quy trình, tránh hai công cụ kéo trạng thái theo hai hướng.

Một bản rollback chỉ hoàn tất khi kết quả thực tế được xác minh:

- Đúng replica set/digest nhận traffic.
- Capacity đủ cho toàn bộ traffic.
- Errors, latency, saturation và business KPIs ổn định.
- Background jobs và consumer không còn tiếp tục side effect lỗi.
- Không có DB/event schema incompatibility do thay đổi đã thực hiện.

## 15. Incident response: mục tiêu đầu tiên là giảm tác động

Một sự cố vận hành cần được xử lý theo thứ tự ưu tiên:

~~~text
Detect
   |
   v
Triage: tác động, phạm vi, mức nghiêm trọng
   |
   v
Assign roles / establish communication
   |
   v
Mitigate / contain blast radius
   |
   v
Restore critical user flows
   |
   v
Verify recovery and observe
   |
   v
Document timeline, root causes and follow-ups
~~~

Trong giai đoạn đầu, không nhất thiết xác định chính xác root cause trước khi giảm tác động. Nếu vừa đổi timeout và tỷ lệ thanh toán thất bại tăng mạnh, **dừng rollout hoặc revert an toàn** có thể là biện pháp cần làm ngay trong khi nhóm tiếp tục điều tra.

### 15.1. Severity dựa trên ảnh hưởng thực

Một mô hình minh họa:

| Mức độ | Dấu hiệu | Phản ứng |
|---|---|---|
| SEV-1 | Luồng thanh toán/đặt hàng ngưng diện rộng, mất dữ liệu hoặc nguy cơ an toàn nghiêm trọng | Kích hoạt chỉ huy sự cố, giảm tác động ngay, thông tin định kỳ |
| SEV-2 | Một vùng hoặc nhóm người dùng lớn bị lỗi; SLO burn nhanh | Phối hợp nhiều service, điều tra và khôi phục theo ưu tiên |
| SEV-3 | Suy giảm giới hạn, workaround tồn tại, ít ảnh hưởng người dùng | Triage theo on-call, theo dõi và lập kế hoạch sửa |
| SEV-4 | Lỗi không ảnh hưởng dịch vụ hoặc vấn đề nội bộ | Đưa vào backlog với owner và ưu tiên |

Đây là ví dụ; tổ chức cần định nghĩa severity theo business impact, security, tài chính, data integrity và nghĩa vụ thông báo, không chỉ dựa vào số lượng 5xx.

## 16. Các vai trò trong một cuộc ứng phó

Một người có thể giữ nhiều vai trò trong sự cố nhỏ, nhưng sự cố lớn nên tránh để một người vừa điều tra, vừa điều phối, vừa gửi thông báo.

| Vai trò | Trách nhiệm |
|---|---|
| **Incident Commander (IC)** | Xác định ưu tiên, quyết định hành động tổng thể, điều phối và thay đổi mức độ sự cố |
| **Technical Lead / Ops Lead** | Điều tra, đề xuất và thực hiện giảm tác động, bảo đảm lệnh có người kiểm tra |
| **Communications Lead** | Cập nhật người dùng/đơn vị liên quan theo nhịp và thông tin đã xác minh |
| **Scribe / Timeline Owner** | Ghi sự kiện, timestamp, quyết định, telemetry và người thực hiện |
| **Service Owner / SME** | Cung cấp kiến thức hệ thống và đánh giá rủi ro kỹ thuật của các bước |
| **Security/Data Lead** | Tham gia khi có secret, data loss, phân quyền hoặc nghĩa vụ bảo mật |

Nên có một **incident channel** và một tài liệu diễn biến được thống nhất. Quyết định quan trọng như failover DB hoặc tắt tích hợp thanh toán phải có người chịu trách nhiệm và người xác minh kết quả. Ghi các mốc thời gian chính xác giúp phân biệt thứ tự nhân quả, nhưng không sao chép token hoặc dữ liệu khách hàng vào timeline.

## 17. Tạo một giả thuyết trước diễn tập

Diễn tập có giá trị nhất khi kiểm tra một giả thuyết có thể quan sát:

> “Nếu một instance Redis không truy cập được trong 3 phút, Catalog Service vẫn giữ tỷ lệ lỗi dưới ngưỡng đã đặt nhờ local cache và fallback được giới hạn, đồng thời không gây quá tải database.”

Giả thuyết tốt xác định:

- **Steady state:** điều kiện bình thường trước thử nghiệm, ví dụ tỷ lệ request thành công, latency, queue lag.
- **Fault:** lỗi định tạo, ví dụ chặn kết nối từ một canary Pod tới Redis.
- **Blast radius:** một Pod, một namespace test, một region hoặc một phần traffic.
- **Expected behavior:** timeout, circuit breaker, graceful degradation, retry budget và recovery.
- **Measurements:** SLI, error budget impact, rate of origin fallback, p95 latency, DB CPU.
- **Guardrails/stop:** giới hạn 5xx, DB saturation, ảnh hưởng khách hàng và thời gian tối đa.
- **Recovery action:** bỏ fault injection, restore route, scale capacity, kiểm tra dữ liệu.
- **Owner/approval:** người biết cách can thiệp và có quyền kết thúc thí nghiệm.

**“Tắt Redis xem sao”** thiếu giả thuyết, phạm vi và điều kiện dừng. Nếu không thể đo hành vi cần kiểm chứng, nên cải thiện observability trước khi chạy lỗi thật.

## 18. Các loại diễn tập từ ít rủi ro đến có fault injection

Không cần bắt đầu bằng cách ngắt network production.

### 18.1. Tabletop exercise

Các thành viên giả định tình huống và diễn giải cách phản ứng trên giấy hoặc qua cuộc họp có kịch bản:

~~~text
10:00 Alert: checkout 5xx vượt ngưỡng
10:03 Dashboard: payment timeout tăng ở region-a
10:06 Phát hiện vừa thay config timeout
10:08 Chủ sở hữu config đang không trực
10:10 Câu hỏi: ai có quyền abort release?
10:12 Câu hỏi: khi rollback, DB có tương thích không?
~~~

Đo khả năng tìm đúng runbook, gọi đúng người, xác định scope và quyết định an toàn. Không có thay đổi hệ thống thật nên rủi ro thấp; tuy vậy không chứng minh các lệnh thực sự chạy được.

### 18.2. Game day trên staging

Tạo lỗi ở môi trường đại diện gần production, ví dụ:

- Kill một Pod đang xử lý request.
- Chặn DNS hoặc một dependency giả lập.
- Giới hạn CPU/memory để kiểm tra autoscaling và readiness.
- Tăng latency hoặc timeout của một endpoint downstream.
- Dừng một consumer để xem backlog/lag và phục hồi.
- Phát sự kiện trùng để kiểm tra idempotency.
- Mô phỏng lỗi quyền truy cập của ServiceAccount.

Phải dùng dữ liệu thử nghiệm, giới hạn tài nguyên và không kết nối nhầm vào hệ thống production.

### 18.3. Chaos experiment trong phạm vi hẹp

Sau khi có bằng chứng staging, tổ chức có thể chạy một thí nghiệm rất giới hạn trên production nếu đã có approvals, observability, kiểm soát blast radius và cơ chế rollback tự động phù hợp. Ví dụ chỉ ảnh hưởng một Pod canary nhận traffic nhỏ, kết thúc nhanh và có ngưỡng dừng.

Không mặc định rằng production chaos là yêu cầu bắt buộc. Nếu dịch vụ có dữ liệu/khách hàng nhạy cảm, rủi ro không thể đảo ngược hoặc chưa chứng minh được restore, hãy dùng staging, shadow hoặc tabletop cho đến khi đủ điều kiện.

### 18.4. Disaster recovery exercise

Một số giả định cần thử:

- Mất một availability zone.
- Mất một node pool, broker partition hoặc database replica.
- Không thể truy cập region chính.
- Có backup nhưng restore chậm hoặc backup không hợp lệ.
- Secret manager hoặc identity provider không sẵn sàng.
- Khả năng phát hành hotfix khi CI/CD hoặc GitOps controller đang lỗi.

Diễn tập DR phải kiểm tra tính toàn vẹn dữ liệu và kết quả nghiệp vụ sau khôi phục, không chỉ việc máy chủ khởi động được.

## 19. Phạm vi an toàn và điều kiện dừng diễn tập

Mỗi bài tập fault injection phải có bộ rào chắn rõ ràng:

1. Kịch bản có chủ sở hữu và được chấp thuận theo môi trường.
2. Không dùng dữ liệu khách hàng thật ở hệ thống test nếu thiếu chính sách bảo vệ.
3. Có một người quan sát có quyền dừng fault, không phụ thuộc hoàn toàn vào controller đang được kiểm thử.
4. Giới hạn vùng, service, replica, traffic cohort và thời gian.
5. Thu thập baseline và xác nhận dashboard/alert hoạt động trước khi inject.
6. Có **stop condition** theo error rate, latency, DB saturation, impact khách hàng hoặc dấu hiệu data corruption.
7. Có rollback/restore đã chuẩn bị và kiểm thử trên phạm vi nhỏ.
8. Không triển khai thay đổi khác cùng lúc trên đối tượng thí nghiệm.
9. Có kênh liên hệ on-call và thông báo nếu bài tập ảnh hưởng người ngoài phạm vi.
10. Sau khi dừng phải xác nhận đã thu hồi fault injection, không để cấu hình lỗi tồn tại.

**Stop condition không chỉ là thời gian hết hạn.** Nếu xuất hiện lỗi dữ liệu hoặc ảnh hưởng ngoài phạm vi, phải dừng ngay theo quyền đã phân công dù chưa đến thời hạn.

## 20. Ví dụ game day: Payment Provider tăng latency

### 20.1. Bối cảnh

Order Service gọi Payment Service, rồi Payment Service gọi provider bên ngoài. Luồng thanh toán có timeout budget và cơ chế idempotency. Nhóm muốn kiểm tra xem latency tăng có làm tồn đọng request, retry storm hoặc duplicate payment hay không.

~~~text
Client -> Gateway -> Order -> Payment -> Provider
                          |            |
                          |            +-- latency injection
                          |
                          +-> Order DB / event broker
~~~

### 20.2. Giả thuyết

“Nếu provider tăng latency thêm một lượng đã xác định trong môi trường test, Payment Service trả kết quả có kiểm soát trong request deadline, circuit breaker/timeout bảo vệ thread pool, retry không vượt budget và không tạo giao dịch trùng.”

### 20.3. Chuẩn bị

- Chạy trên staging hoặc sandbox provider có dữ liệu giả lập.
- Định nghĩa baseline 10–15 phút phù hợp traffic test.
- Ghi p95/p99, timeout rate, retry count, pool utilization, queue depth và transaction status.
- Đảm bảo mỗi lệnh thanh toán dùng idempotency key đúng ngữ nghĩa.
- Chuẩn bị chức năng tắt fault injection và quay về cấu hình cũ.
- Cấm dùng credential/payment account production trong bài tập.

### 20.4. Thực hiện theo giai đoạn

~~~text
T0:  Xác nhận hệ thống steady state
T1:  Bật latency injection cho tập traffic test đã giới hạn
T2:  Quan sát timeout, retry, error categories và queueing
T3:  Phát hiện alert; người trực thực hiện triage
T4:  Thử mitigation theo runbook (giảm retry, circuit breaker...)
T5:  Thu hồi fault injection
T6:  Xác nhận thời gian phục hồi, dữ liệu và trạng thái jobs
~~~

Không phải mọi bước phải thực hiện trong một khoảng thời gian cứng. Nếu stop condition vượt ngưỡng, dừng và phục hồi sớm.

### 20.5. Kết quả cần ghi

- Alert có đến đúng người không?
- Nhóm có nhận ra đường Payment → Provider là nguyên nhân không?
- Có tạo nhiều retries vượt budget không?
- Có request nào bị treo lâu hơn deadline đã hứa với client không?
- Pool/thread/DB có suy giảm không?
- Có giao dịch trùng hoặc trạng thái “unknown” không được reconciliation không?
- Sau khi bỏ fault, service có tự phục hồi hay cần restart?
- Runbook có thể áp dụng trong phạm vi an toàn hay không?

Đây là một bài diễn tập nhằm tìm khoảng trống; kết quả có vấn đề là thông tin hữu ích để sửa hệ thống, không phải lý do bỏ hoặc che giấu dữ liệu quan sát.

## 21. Ví dụ game day: message broker backlog

Giả sử Notification Worker tiêu thụ event từ broker và gửi email. Nhóm muốn biết điều gì xảy ra khi consumer tạm dừng 10 phút.

~~~text
Order Service -> Broker Topic -> Consumer Group -> Notification Worker
                     |
                     v
               Queue lag tăng
~~~

Giả thuyết: khi một consumer mất, broker giữ message theo durability policy; lag tăng trong phạm vi dự kiến; khi consumer phục hồi, backlog giảm và không gửi email trùng ngoài idempotency contract.

Kiểm tra:

- Producer vẫn thành công hay bị backpressure?
- Broker retention và storage có đủ để giữ messages trong thời gian test?
- Consumer group rebalance diễn ra như thế nào?
- Có message bị duplicate delivery sau restart không?
- Worker có idempotency key và deduplication đúng không?
- Khi xử lý backlog, worker có rate limit để không làm email provider quá tải không?
- Alert queue lag có phát ra không?
- Có cơ chế dead-letter và cách phân biệt malformed message với lỗi tạm thời không?
- MTTD và recovery time có đáp ứng SLO xử lý event không?

Cảnh báo: **broker lag trở về 0 không tự chứng minh không mất hoặc không gửi trùng message**. Cần đối chiếu message count, outcome và business invariants trong test.

## 22. Ví dụ diễn tập database failover

Một DB primary failover là bài thử khác với rollback Deployment vì có state và replication:

~~~text
Service Pods -> DB Primary A ---- replication ----> Replica B
                        |
                        | simulated controlled failover
                        v
                     New Primary B
~~~

Trước diễn tập:

- Xác nhận backup/restore point và phạm vi quyền.
- Đánh giá độ trễ replication, failover policy và khả năng dữ liệu chưa replicate.
- Dùng dữ liệu test hoặc môi trường phù hợp với rủi ro.
- Kiểm tra DNS/service discovery, connection pools và transaction retries.
- Bảo đảm các thao tác ghi có idempotency/transaction handling đúng.
- Xác định RPO chấp nhận và cách đối chiếu dữ liệu sau failover.

Trong diễn tập, ghi thời điểm write bị gián đoạn, khi new primary sẵn sàng, khi service bắt đầu thành công lại và độ trễ phục hồi client connections. Không khởi động failover production chỉ để “xem thử” nếu chưa có approvals và bảo đảm an toàn dữ liệu.

## 23. RTO, RPO, MTTD, MTTA và MTTR

Các số đo giúp so sánh năng lực phục hồi, nhưng cần định nghĩa rõ mốc đo.

| Chỉ số | Ý nghĩa thực dụng | Điểm chú ý |
|---|---|---|
| **MTTD** – Mean Time To Detect | Thời gian trung bình từ lúc lỗi bắt đầu đến lúc hệ thống/người trực nhận biết | “Bắt đầu lỗi” phải được mô phỏng hoặc xác định bằng timeline đáng tin |
| **MTTA** – Mean Time To Acknowledge | Thời gian trung bình để người trực xác nhận cảnh báo | Không đồng nghĩa với mitigation |
| **MTTR** – Mean Time To Restore/Recover | Thời gian trung bình để khôi phục dịch vụ, tùy định nghĩa tổ chức | Cần định nghĩa “restored”: users phục vụ được, không chỉ Pod Ready |
| **RTO** – Recovery Time Objective | Mục tiêu thời gian tối đa để khôi phục dịch vụ sau gián đoạn | Mục tiêu, không phải số đo tự động |
| **RPO** – Recovery Point Objective | Mức mất dữ liệu theo thời gian tối đa có thể chấp nhận | Phù hợp bài toán stateful restore/DR |
| **Error-budget burn** | Tốc độ tiêu thụ phần không đạt SLO trong cửa sổ | Phụ thuộc SLI và mẫu số |

Một buổi diễn tập có thể đo thực tế 9 phút từ lúc bắt đầu fault tới khi dịch vụ trở lại ổn định. Con số này không tự động là MTTR của toàn tổ chức; nó là **một quan sát** trong một kịch bản. Cần thu thập nhiều sự cố/diễn tập có phân loại trước khi kết luận xu hướng.

### Ví dụ đặt mục tiêu theo critical flow

- Checkout: mục tiêu phục hồi trong một khoảng do business quyết định; không được duplicate charge.
- Search: có thể cho phép degraded mode trong khi index được phục hồi.
- Notification: có thể chấp nhận xử lý chậm ngắn hạn nếu broker retention và user commitments cho phép.
- Reporting batch: RTO tính theo giờ có thể phù hợp, nhưng RPO/data completeness cần bảo đảm.

Không lấy cùng RTO/RPO cho mọi service; phải dựa trên nhu cầu nghiệp vụ và khả năng kiến trúc.

## 24. Post-incident review không nhằm tìm người có lỗi

Sau sự cố hoặc game day, nhóm cần làm rõ **điều gì xảy ra, vì sao hệ thống cho phép nó xảy ra, đã phản ứng như thế nào và thay đổi gì để lần sau tốt hơn**.

Một cấu trúc review:

1. **Summary:** tác động người dùng và hệ thống, phạm vi và thời gian.
2. **Timeline:** các mốc thay đổi, metric, alert, phát hiện, hành động và phục hồi.
3. **What worked:** biện pháp có hiệu quả, ví dụ canary giới hạn 5% traffic.
4. **What did not work:** cảnh báo muộn, thiếu quyền rollback, dashboard không phân biệt version.
5. **Contributing factors:** kiến trúc, chính sách, tests, dependency, giao tiếp và runbook.
6. **Detection gap:** SLI/cảnh báo nào chưa thể hiện đúng business impact.
7. **Recovery gap:** bước nào quá lâu, thao tác nào chưa có đường thực hiện an toàn.
8. **Action items:** cải tiến cụ thể, ưu tiên, owner, hạn hoàn tất và phép kiểm tra lại.
9. **Follow-up:** kế hoạch xác minh fix và diễn tập lại phần đã thất bại.

Tinh thần **blameless** không có nghĩa bỏ qua trách nhiệm chuyên môn; nó giúp tìm các điều kiện hệ thống, incentives và kỹ thuật làm lỗi dễ xảy ra, thay vì dừng ở kết luận “người vận hành gõ sai lệnh”. Mọi hành động sửa chữa vẫn cần chủ sở hữu và deadline rõ.

## 25. Hành động cải tiến phải kiểm chứng được

Các hạng mục “cần giám sát tốt hơn” hoặc “hãy cẩn thận” khó xác định đã hoàn thành. Thay bằng việc cụ thể:

| Phát hiện | Hành động có thể kiểm chứng |
|---|---|
| Alert chỉ gửi tới người nghỉ phép | Cấu hình on-call escalation và kiểm thử tới backup |
| Không biết Pod nào chạy config mới | Gắn config revision trong deployment metadata và dashboard |
| Rollback GitOps bị controller ghi đè | Tạo runbook rollback tại nguồn desired state và diễn tập |
| Cache outage làm database quá tải | Giới hạn concurrent fallback, thêm circuit breaker và load test |
| 5xx thấp nhưng checkout sai | Thêm business completion SLI và invariant checks |
| Không tìm thấy secret rotation owner | Đăng ký ownership, expiry alert và rotation drill |
| Broker redelivery gửi email trùng | Thêm idempotency store và integration test duplicate messages |
| Không biết trạng thái migration sau revert | Bổ sung expand–contract checklist và compatibility test |

Mỗi action item nên có:

- Owner chịu trách nhiệm.
- Mức ưu tiên theo tác động.
- Tiêu chí hoàn tất đo được.
- Evidence từ test hoặc production rollout.
- Ngày dự định kiểm tra lại.
- Cách chứng minh đã giảm failure mode được phát hiện.

## 26. Automating incident drills without automating harm

Một framework diễn tập có thể kích hoạt tình huống trên test environment từ script hoặc chaos controller. Tuy nhiên, bộ tự động phải có giới hạn:

~~~text
Controller starts experiment
   |
   v
Verify preflight:
  target allowlisted?
  environment correct?
  incident already active?
  observers available?
  abort path tested?
  monitoring healthy?
   |
   +-- No --> REFUSE TO RUN
   |
   v
Apply bounded fault (time/namespace/traffic)
   |
   v
Observe and compare with stop thresholds
   |
   +-- Stop threshold crossed --> REMOVE FAULT + RESTORE
   |
   v
End experiment
   |
   v
Remove fault + verify recovered steady state
   |
   v
Export evidence and open action items
~~~

**Cấu hình “tắt fault injection sau X phút” không đủ nếu automation chết giữa chừng.** Cần thiết kế TTL/lease, external cleanup hoặc cơ chế watchdog tách khỏi thành phần đang được kiểm thử. Có thể đặt fault có thời hạn cứng cùng một controller độc lập giám sát; kiểm chứng quá trình dọn dẹp trong môi trường test trước.

Nếu môi trường dùng network policies, chaos mesh hoặc fault injection trong service mesh, chỉ cho phép các target đã đăng ký; không nhận raw namespace/Pod selector bất kỳ từ người dùng thiếu thẩm quyền.

## 27. Kế hoạch một game day mẫu

**Chủ đề:** “Mất một Pod của Order Service và retry tăng khi Payment Service chậm.”

**Mục tiêu:** kiểm tra readiness, retry budget, error rate, alerting, runbook và khả năng phối hợp nhiều nhóm.

### 27.1. Trước buổi tập

- Chọn môi trường staging hoặc phạm vi production đã được duyệt.
- Viết giả thuyết và điều kiện dừng.
- Xác nhận traffic synthetic, data test, không có payment thật.
- Ghi baseline SLI và thông số hạ tầng.
- Chỉ định IC, technical lead, communications lead và scribe.
- Kiểm thử quyền dừng fault và đường rollback.
- Thông báo cho các nhóm có thể nhìn thấy alert test để tránh hiểu nhầm sự cố thật.

### 27.2. Trong buổi tập

1. Inject một fault đã giới hạn, ví dụ tăng latency của Payment mock.
2. Scribe ghi timestamp inject và metric đầu tiên thay đổi.
3. Quan sát hệ thống phát alert và on-call xác nhận.
4. IC phân loại mức độ tác động, gắn người điều tra.
5. Technical lead xác định dependency chậm và chọn mitigation.
6. Nếu vượt guardrail, chủ động abort thay vì tiếp tục để “đủ bài”.
7. Thu hồi fault và xác minh request thành công lại.
8. Kiểm tra các giao dịch hoặc events chưa có trạng thái cuối.

### 27.3. Sau buổi tập

- Chốt timeline phát hiện và phục hồi.
- Đối chiếu với SLO/error budget và giới hạn blast radius.
- Nêu khoảng trống của runbook, quyền, dashboard và cách phối hợp.
- Tạo action items có owner và test lại.
- Lưu kết quả theo môi trường và release/config revisions để có thể so sánh các lần sau.

## 28. Mẫu báo cáo game day

~~~markdown
# Game Day: Payment latency

## Scope
- Environment: staging
- Services: order-service, payment-service
- Fault target: payment mock, synthetic traffic only

## Hypothesis
- Order Service maintains bounded timeout/retry behavior.
- No duplicate payments or inconsistent order state.

## Preconditions
- Observability/alerting verified
- Rollback path tested
- IC and technical observer assigned

## Steady state
- Success rate: [measurement]
- p95 latency: [measurement]
- Queue lag: [measurement]

## Timeline
- T0: baseline confirmed
- T1: fault injected
- T2: first SLI regression
- T3: alert acknowledged
- T4: mitigation performed
- T5: fault removed
- T6: service restored

## Findings
- Detection:
- Diagnosis:
- Recovery:
- Data integrity:
- Communication:

## Follow-ups
- Action:
- Owner:
- Verification:
~~~

Các trường `[measurement]` là placeholder của biểu mẫu thực hành, không phải thông số đã đo. Một báo cáo thật phải có timestamp, link dashboard/traces và bản ghi thay đổi phù hợp, nhưng tránh đính kèm secret hoặc dữ liệu khách hàng.

## 29. Kiểm soát dữ liệu và bảo mật trong diễn tập

Một game day cũng có thể gây sự cố bảo mật nếu tự ý dùng tài khoản production, xem secret, ngắt xác thực hoặc gửi synthetic payload sang đối tác thật.

Nguyên tắc:

- Dùng test/sandbox credentials và data tổng hợp cho staging.
- Không copy PII, token hay nội dung giao dịch thật vào ticket/recording.
- Nếu thí nghiệm tác động third-party provider, phải dùng sandbox hoặc có thỏa thuận và giới hạn rõ.
- Thao tác có quyền cao cần được quản lý qua role tạm thời, audit và thời hạn.
- Không vô hiệu hóa security controls “cho dễ chạy game day” trên môi trường thật.
- Không truyền fault injection payload qua đường thực thi không xác thực.
- Nếu ghi replay messages, phải phân biệt synthetic traffic với business events production.
- Sau diễn tập, kiểm tra tài nguyên test, quyền tạm, debug logs và config fault đã được thu hồi.

Bảo mật là một phần của sự thành công: một bài tập chứng minh hệ thống chịu latency tốt nhưng để lộ secret trong logs vẫn cho thấy lỗ hổng cần xử lý.

## 30. Khi nào phải dừng một thay đổi?

Những tình huống sau thường đáng cân nhắc HOLD hoặc ABORT tùy chính sách:

- SLI của luồng trọng yếu giảm và có evidence gắn với thay đổi.
- Canary xuất hiện lỗi correctness hoặc tác dụng phụ không thể đảo ngược.
- Readiness không ổn định, Pod restart liên tục hoặc capacity dự phòng không đủ.
- Metrics không còn phân biệt version/stable/canary hoặc bị trễ nhiều.
- Database replication lag vượt mức an toàn.
- Queue lag và retries tăng theo hướng làm kiệt dependency.
- Có incident đang mở ảnh hưởng cùng nhóm tài nguyên khiến kết quả không đáng tin.
- Không còn người có quyền rollback hoặc đường rollback chưa hoạt động.
- Kết quả preflight không khớp artifact/config revision đã được phê duyệt.
- Cảnh báo bảo mật, mất dữ liệu hoặc truy cập trái quyền.

Tuy nhiên, trong một sự cố cần hotfix khẩn cấp, tổ chức có thể có đường ngoại lệ với phê duyệt và kiểm soát riêng. Điều quan trọng là ghi nhận lý do, quyền thực hiện và bằng chứng hậu kiểm, không cho phép bypass vô danh.

## 31. Liên hệ thay đổi với observability

Nếu chỉ có dashboard CPU và Pod Ready, nhóm khó biết thay đổi làm người dùng thất bại ở đâu. Một bộ observability tối thiểu để vận hành theo SLO có thể gồm:

- **Metrics:** request success/latency, dependency errors, retry rate, queue lag, saturation và business outcomes.
- **Traces:** đường đi request qua HTTP/RPC/broker; span có release/config revision nếu policy cho phép.
- **Logs:** structured event theo severity, mã lỗi và trace correlation; không ghi raw token/PII.
- **Release annotations:** đánh dấu thời điểm deployment/config switch trên dashboard.
- **Alerts:** multi-window SLO burn rate, critical invariant và dependency outage.
- **Synthetic checks:** hành trình test an toàn giúp có signal khi traffic thật quá ít.
- **Audit:** ai thay đổi config/feature flag/network policy, lúc nào và kết quả.

Với trace mất một phần do sampling, không thể kết luận hệ thống an toàn chỉ từ một trace. Ngược lại, một trace lỗi cá biệt không tự chứng minh toàn bộ canary đang suy giảm; cần kết hợp metric và business impact.

## 32. Thực hành phối hợp với các service owners

Một thay đổi Gateway có thể ảnh hưởng Order, Catalog và Auth. Nhóm Gateway không thể tự kết luận thay đổi an toàn chỉ vì gateway Pods Ready.

Phối hợp có thể gồm:

1. Liệt kê downstream cùng loại request chịu ảnh hưởng.
2. Xác định on-call và thông tin liên hệ theo dependency.
3. Thống nhất invariant nghiệp vụ: không double charge, không mất đơn, không lộ dữ liệu.
4. Xác định dashboard nào cần cùng xem và owner của từng SLI.
5. Ghi quyền can thiệp: ai có thể rollback gateway, tắt feature flag, stop consumer hay chuyển traffic.
6. Thử một đường E2E có thật bằng synthetic data.
7. Sau thay đổi, quan sát cả luồng user và dependency, không chỉ thành phần vừa đổi.

Nếu team có nhiều timezone, tạo runbook đủ rõ để on-call của ca sau tiếp nhận từ change record mà không cần hỏi người làm ban đầu.

## 33. Bài tập tình huống: một thay đổi cấu hình gây sự cố

Hệ thống đặt hàng có đường đi:

~~~text
Mobile Client
    |
    v
API Gateway
    |
    v
Order Service
    |----> Inventory Service -> Inventory DB
    |----> Payment Service -> External Provider
    |
    +----> Kafka: OrderCreated
                |
                v
         Notification Worker
~~~

Một nhóm dự kiến giảm `payment-client-timeout` từ 800 ms xuống 250 ms để cải thiện latency. Service xử lý 40.000 request hợp lệ trong 1 giờ; Payment Provider đôi khi trả kết quả sau 300–500 ms. Một rollout canary 10% được lên lịch, nhưng dashboard chỉ đang hiển thị tổng tỷ lệ 5xx của Order Service.

### Câu hỏi

1. Thay đổi này có thể tác động đến những dependency và hành vi nghiệp vụ nào?
2. Preflight cần bổ sung điều gì trước khi mở 10% traffic?
3. Vì sao 5xx tổng của Order Service có thể không đủ để quyết định promote?
4. Cần định nghĩa các tiêu chí PASS, FAIL và UNKNOWN như thế nào?
5. Nếu Payment Service nhận request timeout, có được retry thanh toán vô điều kiện không?
6. Khi lỗi tăng, phương án rollback có cần xem xét transaction hoặc messages đã phát không?
7. Hãy thiết kế một game day staging để kiểm tra latency tăng của provider mà không gọi giao dịch thật.
8. Sau diễn tập, hành động nào cần có owner và phép kiểm tra lại?

### Hướng phân tích

- Timeout thấp có thể gây tăng client cancel, retry, pending payment và trạng thái chưa xác định; phải dùng idempotency/reconciliation, tránh double charge.
- Preflight cần đo distribution latency provider, retry budget, deadlines, khả năng phân biệt canary/stable, business success rate và rollback config.
- Tổng 5xx có thể che mất sự cố chỉ ở 10% cohort; cần metric theo release version, route và dependency.
- PASS khi đủ sample, metric mới, timeout/latency/success đạt ngưỡng. FAIL khi lỗi hoặc correctness vượt giới hạn. UNKNOWN khi thiếu dữ liệu/cohort sai hoặc dependency incident gây nhiễu.
- Retry phải theo hợp đồng idempotency và trạng thái chắc chắn của provider, không giả định timeout nghĩa là chưa thanh toán.
- Rollback timeout config không hoàn tác thanh toán hoặc event đã gửi; cần theo dõi các trạng thái đang chờ và điều hòa dữ liệu.
- Game day dùng provider mock có latency injection, synthetic orders, guardrails và stop switch.
- Action items có thể gồm dashboard phân version, retry budget test, timeout SLO review, playbook rollback và bài test không tạo giao dịch trùng.

## 34. Những sai lầm phổ biến

1. **Triển khai 100% rồi mới kiểm tra:** không giới hạn blast radius dù có thể canary.
2. **Chỉ dựa vào health Pod:** không nhìn business success và downstream.
3. **Không có owner/đường rollback:** khi incident xảy ra không ai biết ai có quyền dừng.
4. **Đổi cấu hình không có revision:** khó biết Pod nào dùng giá trị nào.
5. **Thấy dashboard rỗng và coi là 0 lỗi:** dữ liệu có thể thiếu, phải HOLD.
6. **Coi error budget là quyền gây lỗi:** bỏ qua data corruption và security risk.
7. **Diễn tập bằng cách tắt ngẫu nhiên service production:** không có giả thuyết, guardrail hoặc approval.
8. **Không đo steady state trước inject:** không thể biết lỗi được tạo tác động thế nào.
9. **Chỉ dọn fault bằng tay mà không có timeout/lease:** controller lỗi có thể để hệ thống ở trạng thái hỏng lâu.
10. **Chỉ đo Pod trở lại Ready:** chưa chứng minh người dùng khôi phục.
11. **Không xét queue và side effects:** worker có thể gửi lại message, tạo giao dịch trùng.
12. **Rollback image mà quên database migration:** code cũ có thể không hiểu dữ liệu mới.
13. **Ghi raw secret/PII vào biên bản diễn tập:** tạo rò rỉ ngoài production logs.
14. **Postmortem tập trung đổ lỗi cá nhân:** bỏ qua lỗ hổng công cụ, quy trình và thiết kế.
15. **Action item chỉ là khẩu hiệu:** không có owner hoặc phép thử xác nhận hoàn tất.
16. **Không diễn tập lại sau sửa:** không biết thay đổi có thật sự loại failure mode.
17. **Tạo nhiều thay đổi chồng nhau:** khó tìm quan hệ nhân quả và rollback đúng phiên bản.
18. **Đóng incident khi alert tắt:** chưa kiểm tra data integrity và job còn tồn đọng.

## 35. Checklist thay đổi vận hành có kiểm soát

- [ ] Xác định mục tiêu, phiên bản artifact/config và service owner.
- [ ] Liệt kê dependencies, phạm vi người dùng và dữ liệu bị ảnh hưởng.
- [ ] Phân loại rủi ro, cân nhắc SLO/error budget và incident hiện tại.
- [ ] Có kiểm tra tương thích API, message và database schema nếu liên quan.
- [ ] Có preflight và bằng chứng metric/trace đủ phân biệt rollout.
- [ ] Có staged rollout, canary/flag hoặc giới hạn blast radius phù hợp.
- [ ] Định nghĩa chính xác PASS, FAIL, UNKNOWN và hành động sau mỗi kết quả.
- [ ] Có sample tối thiểu, observation window và điều kiện dữ liệu đủ mới.
- [ ] Có đường rollback/roll-forward thực tế, đã kiểm chứng quyền thao tác.
- [ ] Không có thay đổi khác đồng thời gây nhiễu trên cùng đích.
- [ ] Có người quan sát và liên hệ on-call trong thời gian rollout.
- [ ] Sau thay đổi, xác nhận SLI, business outcomes và dữ liệu không sai.
- [ ] Lưu change record, quyết định và bằng chứng mà không chứa bí mật.
- [ ] Có quy trình follow-up nếu xuất hiện sai lệch hoặc sự cố.

## 36. Checklist diễn tập sự cố

- [ ] Viết giả thuyết về một failure mode cụ thể.
- [ ] Đo steady state trước thí nghiệm.
- [ ] Chọn môi trường và scope nhỏ nhất có ý nghĩa.
- [ ] Có dữ liệu synthetic và loại bỏ side effects thật nếu có thể.
- [ ] Xác định fault, thời gian, blast radius và stop conditions.
- [ ] Chỉ định IC/technical observer và người có quyền abort.
- [ ] Kiểm tra dashboard, alert, runbook và permissions trước inject.
- [ ] Có rollback/cleanup hoạt động độc lập với thành phần bị kiểm thử.
- [ ] Thực hành triage, mitigation, communication và recovery.
- [ ] Đo MTTD/MTTA/recovery, backlog và business invariants.
- [ ] Xác nhận fault đã được thu hồi và hệ thống quay về steady state.
- [ ] Viết báo cáo timeline, phát hiện và action items có owner.
- [ ] Xác minh fix bằng bài diễn tập lại hoặc integration tests thích hợp.

## 37. Kết luận

Thay đổi vận hành có kiểm soát là việc **đưa rủi ro ra ánh sáng trước khi mở rộng tác động**: biết chính xác điều gì sẽ đổi, ai chịu trách nhiệm, chỉ số nào chứng minh an toàn, khi nào phải HOLD hoặc ABORT và cách phục hồi khi cần. SLO và error budget cung cấp ngôn ngữ chung để cân bằng tốc độ thay đổi với chất lượng phục vụ, nhưng không thay thế các điều kiện bảo vệ dữ liệu, bảo mật và tính đúng đắn nghiệp vụ.

Diễn tập sự cố biến runbook thành năng lực thực tế. Một game day tốt có giả thuyết, steady state, fault được giới hạn, quan sát đầy đủ, điều kiện dừng và kiểm chứng phục hồi; kết quả của nó là bằng chứng để cải thiện hệ thống và khả năng phối hợp, không phải một cuộc thử độ liều lĩnh. Khi ghép **progressive delivery + SLO-based decisions + practiced recovery**, microservices có thể thay đổi thường xuyên hơn mà vẫn kiểm soát được phạm vi và thời gian của sự cố.
