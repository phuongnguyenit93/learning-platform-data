# Runbook, trực vận hành và phân công người chịu trách nhiệm

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Vận hành và SLO. Tài liệu giải thích cách xây dựng runbook có thể thực thi, tổ chức trực vận hành (on-call), định nghĩa quyền và trách nhiệm của từng nhóm, phân loại và xử lý sự cố, gắn cảnh báo với tác động đến người dùng/SLO, lập cơ chế escalation, bàn giao và học từ sự cố. Ví dụ tập trung vào hệ thống microservices có API Gateway, Order, Payment, Inventory, Kubernetes, cơ sở dữ liệu, message broker và các dependency bên ngoài.

## 1. Vì sao runbook và ownership là một phần của kiến trúc?

Một hệ thống có monitoring, tracing và dashboard tốt vẫn có thể gặp sự cố kéo dài nếu không ai biết **ai phải phản hồi**, **quyết định đầu tiên là gì**, **cách kiểm tra phạm vi ảnh hưởng** hoặc **làm sao đảo ngược một thay đổi an toàn**.

Trong microservices, một lỗi checkout có thể liên quan đến:

- Gateway và network policy do platform team quản lý.
- Order Service do product team quản lý.
- Payment Service và đối tác thanh toán.
- Database, connection pool, migration và schema.
- Kafka/RabbitMQ, các consumer, retry và dead-letter queue.
- Kubernetes rollout, resource quota, secret rotation và ingress.
- Frontend/mobile hiển thị sai trạng thái dù backend đã xử lý.
- Dịch vụ observability bị gián đoạn khiến dữ liệu điều tra thiếu.

Nếu một alert không có người nhận chịu trách nhiệm, nó chỉ là một thông báo. Nếu alert có người nhận nhưng thiếu runbook, người trực phải tự khám phá lại hệ thống trong lúc áp lực. Nếu runbook có lệnh sửa nhưng thiếu guardrail và owner phê duyệt, việc khắc phục có thể gây mất dữ liệu hoặc lan rộng sự cố.

**Ba thành phần phải được thiết kế cùng nhau:**

1. **SLO và alert:** định nghĩa điều gì đang tác động đến người dùng và khi nào cần hành động.
2. **On-call và ownership:** ai chịu trách nhiệm tiếp nhận, ai ra quyết định, ai thực thi, ai hỗ trợ.
3. **Runbook và incident workflow:** từng bước để xác minh, khoanh vùng, giảm tác động, phục hồi và kiểm chứng kết quả.

Mục tiêu không phải viết tài liệu dài nhất có thể. Mục tiêu là người trực không viết code của service vẫn có thể thực hiện các bước đầu tiên **đúng, nhanh, ít rủi ro**, biết khi nào dừng và mời chuyên gia.

## 2. Khái niệm và phạm vi

| Thuật ngữ | Định nghĩa | Ví dụ |
| --- | --- | --- |
| Runbook | Hướng dẫn thao tác vận hành có điều kiện, bước thực hiện, kiểm chứng và rollback | Khi Order API 5xx tăng, kiểm tra rollout, dependency, error budget rồi chọn giảm tác động |
| Playbook | Kịch bản phối hợp rộng cho một loại tình huống | Quy trình ứng phó sự cố nghiêm trọng liên quan nhiều đội |
| On-call rotation | Lịch cá nhân/nhóm chịu trách nhiệm phản hồi cảnh báo theo thời điểm | Primary trực từ thứ Hai đến thứ Hai, secondary dự phòng |
| Service owner | Nhóm sở hữu vận hành và vòng đời dịch vụ | Order Team sở hữu Order Service |
| Incident commander (IC) | Người điều phối sự cố, ưu tiên quyết định và phân chia công việc | Chỉ định một IC cho sự cố P1 nhiều service |
| Technical lead | Người dẫn dắt chẩn đoán, đề xuất biện pháp kỹ thuật | Payment SME kiểm tra timeout/provider |
| Communications lead | Người cập nhật thông tin cho khách hàng/stakeholder | Status page và bản cập nhật nội bộ |
| Escalation | Chuyển mức phản hồi khi không được nhận hoặc cần quyền/chuyên môn khác | Primary → Secondary → Platform/DBA → Incident manager |
| SLI/SLO | Tín hiệu chất lượng thực tế và mục tiêu mong muốn | Tỷ lệ checkout thành công trong 28 ngày |
| Error budget | Mức sai lệch SLO cho phép trong cửa sổ xác định | Phần request lỗi/chậm được phép theo policy |
| Mitigation | Giảm tác động nhanh dù chưa sửa gốc | Tắt feature mới, failover, rate limit |
| Resolution | Dịch vụ phục hồi và tiêu chí kết thúc đã đạt | Checkout success và latency về mức bình thường |
| Postmortem | Phân tích học từ sự cố và hành động phòng tái diễn | Phát hiện thiếu deadline, bổ sung alert và test |

Runbook không thay thế **điều tra kỹ thuật có tư duy**. Nó phải xác định các nhánh quyết định và giới hạn an toàn, không cố giả định mọi lỗi trong tương lai diễn ra giống nhau. Những hoạt động khẩn cấp ngoài tài liệu cần được ghi nhận, kiểm chứng và đưa lại vào tài liệu sau sự cố.

## 3. Từ mục tiêu sản phẩm đến trách nhiệm trực vận hành

Bắt đầu từ các hành trình quan trọng, không chỉ danh sách Pod hoặc container:

| Hành trình | Hậu quả nếu lỗi | Nhóm điều phối chính | Nhóm liên quan |
| --- | --- | --- | --- |
| Xem sản phẩm | Không xem được thông tin trước khi mua | Catalog/Frontend | Gateway, Cache, Search |
| Đặt hàng | Người dùng không tạo được đơn | Order Team | Inventory, Payment, Platform |
| Thanh toán | Có thể thất bại hoặc kết quả không rõ | Payment Team | Provider, Order, Fraud, Finance |
| Tra cứu trạng thái đơn | Hiển thị chậm hoặc trạng thái cũ | Order Team | Event pipeline, Frontend |
| Gửi thông báo | Email/push trễ, không nhất thiết chặn giao dịch | Notification Team | Broker, Email provider |

**Hệ thống được sở hữu theo dịch vụ nhưng sự cố được quản lý theo tác động.** Một lỗi checkout do Kafka backlog có thể thuộc quyền khắc phục của Messaging Team nhưng người điều phối cho hành trình checkout vẫn phải đảm bảo thông tin người dùng và xác nhận kết quả nghiệp vụ.

Với mỗi service cần ghi:

- Tên service, repository, deployment, namespace, cluster và dashboard.
- Product/business owner và technical owner.
- On-call primary rotation, secondary rotation, escalation contacts.
- SLI/SLO và các hành trình chịu ảnh hưởng.
- Dependency graph: upstream, downstream, DB, queue, provider.
- Runbook bắt đầu từ alert nào, kịch bản nào có thể làm sai dữ liệu.
- Chính sách rollback, feature flags, secret/config, backup và recovery.
- Link đến source of truth cho vận hành và ngày rà soát gần nhất.

Một bảng ownership chưa có người nhận ca trực tại thời điểm xảy ra lỗi là chưa đủ. **Service ownership phải ánh xạ được đến con người hoặc hệ thống trực có khả năng được gọi ngay bây giờ.**

## 4. Phân biệt service ownership, incident ownership và action ownership

Có ba kiểu trách nhiệm dễ bị nhầm:

1. **Service owner:** chịu trách nhiệm lâu dài về correctness, SLO, deploy, dữ liệu, runbook và cải tiến service.
2. **Incident owner/IC:** chịu trách nhiệm điều phối toàn sự cố, tổng hợp sự thật, ra quyết định ưu tiên và tuyên bố kết thúc; có thể không sở hữu service lỗi.
3. **Action owner:** người cụ thể nhận việc như rollback, kiểm tra DB, đối soát giao dịch hoặc phát thông báo; có thời hạn và trạng thái báo cáo.

Ví dụ sự cố P1 checkout lỗi:

~~~text
Incident Commander (Order on-call)
    |
    +-- Technical lead: Payment on-call
    |       +-- kiểm tra provider latency
    |       +-- đề xuất circuit breaker / failover
    |
    +-- Platform on-call
    |       +-- kiểm tra ingress, Kubernetes events, rollout
    |
    +-- Database SME
    |       +-- kiểm tra pool waits, locks, replication
    |
    +-- Communications lead
            +-- cập nhật nội bộ và status page
~~~

Một người có thể kiêm nhiều vai trò trong sự cố nhỏ, nhưng với sự cố nghiêm trọng nên tách **IC** khỏi người trực tiếp chạy từng lệnh. Người đang triage query không nên đồng thời phải viết thông báo, quản lý timeline và điều phối ba đội khác nếu có người hỗ trợ.

**Nguyên tắc:** Có thể nhiều người đóng góp, nhưng luôn có **một người điều phối cuối cùng** và **một người được giao cho từng action**. Tránh câu “Team A và B cùng chịu trách nhiệm” mà không ai cần ra quyết định.

## 5. RACI và ma trận quyền quyết định

RACI là một cách phân biệt:

- **R – Responsible:** người thực thi công việc.
- **A – Accountable:** người chịu trách nhiệm kết quả và quyền phê duyệt; nên có một A rõ cho mỗi quyết định.
- **C – Consulted:** người cần được tham khảo trước hoặc trong quá trình.
- **I – Informed:** người cần được cập nhật.

Một ví dụ, không phải cấu trúc bắt buộc:

| Hoạt động | IC | Service on-call | Platform | DBA | Product |
| --- | --- | --- | --- | --- | --- |
| Tuyên bố P1, lập cầu liên lạc | A/R | C | C | I | I |
| Khoanh vùng lỗi Order API | A | R | C | C | I |
| Rollback Order Deployment theo chính sách | A | R | C | I | I |
| Thay đổi DB schema/data khẩn cấp | A | C | C | R | C |
| Bật chế độ degraded checkout | A | R | C | I | C |
| Thông báo khách hàng | A | C | I | I | R |
| Xác nhận SLO đã phục hồi | A | R | R | C | C |
| Hành động khắc phục dài hạn | C | A/R | C | C | C |

Bảng chỉ minh họa: trong tổ chức thực, **IC không nhất thiết là người phê duyệt mọi thay đổi production**. Các thao tác đặc biệt rủi ro như xóa dữ liệu, failover database, thu hồi secret hoặc chuyển vùng có thể yêu cầu quyền riêng theo policy. Quy trình khẩn cấp phải nêu rõ cơ chế break-glass, audit và phê duyệt hậu kiểm nếu có.

Có thể dùng RACI ở cấp công việc, nhưng đối với vận hành phút-giây nên cung cấp **contact và quyền thực thi thực tế**. Bảng RACI không thay được việc xác định ai đang là primary on-call.

## 6. Định nghĩa SLO và cảnh báo theo tác động

Một SLO có ý nghĩa được mô tả bằng:

- Hành trình hoặc API: Checkout / POST /orders/confirm.
- Population: request hợp lệ từ người dùng thật, phân tách bot/synthetic nếu cần.
- Success: trạng thái nghiệp vụ đạt điều kiện, không chỉ HTTP 200.
- Cửa sổ: ví dụ 28 ngày.
- Target: ví dụ thành công >= 99,9%.
- Latency: ví dụ 95% giao dịch xác nhận dưới ngưỡng đã thống nhất.
- Error budget: phần vi phạm cho phép trong cùng window theo định nghĩa SLI.
- Owner và escalation khi burn rate cao.

Ví dụ: SLO request-based 99,9% với 1.000.000 request hợp lệ trong cửa sổ cho phép tối đa khoảng **1.000 request vi phạm** trước khi không còn đạt tỷ lệ mục tiêu. Với time-based availability 99,9% trên 30 ngày, budget lý thuyết khoảng 43,2 phút. **Không đánh tráo error budget request-based thành số phút downtime** nếu phân bố traffic không đồng đều.

### Từ metric đến page

Không phải mọi metric vượt ngưỡng đều nên đánh thức on-call. Cảnh báo cần phân cấp:

| Cấp tín hiệu | Ví dụ | Hành động |
| --- | --- | --- |
| Page ngay | Checkout success SLO burn nhanh, mất khả năng tạo đơn toàn vùng | Gọi primary; escalation theo chính sách |
| Page có điều kiện | Consumer lag tăng đến mức có nguy cơ vượt độ trễ nghiệp vụ | Gọi owner nếu vượt ngưỡng tác động và không tự phục hồi |
| Ticket | Tỷ lệ cache miss tăng nhẹ, capacity sắp cạn tuần tới | Đưa vào backlog owner |
| Dashboard | Pod restart một lần rồi Ready và không ảnh hưởng SLO | Theo dõi và điều tra nếu lặp lại |
| Security alert | Nghi credential leak hoặc hành vi truy cập đáng ngờ | Kênh security incident riêng, không chỉ quy trình availability |

**Một page tốt** chứa: tên hành trình/service, mức severity dự kiến, window, SLI hiện tại và baseline, phạm vi ảnh hưởng, đường dẫn dashboard, truy vấn log/trace, runbook, on-call routing và hướng dẫn escalation. Không gửi một thông báo mơ hồ “CPU > 80%” mà không có liên kết đến hành động.

### Burn-rate alert

Nếu mục tiêu success 99,9%, tỷ lệ lỗi cho phép là 0,1% trong cửa sổ SLO. Burn rate 10 nghĩa là trong khoảng quan sát, tỷ lệ vi phạm cao gấp 10 lần tốc độ ngân sách cho phép, theo cùng denominator và policy. Có thể sử dụng cảnh báo nhiều cửa sổ (ngắn + dài) để phát hiện sự cố nghiêm trọng mà giảm false positive. Ngưỡng cụ thể phải hiệu chỉnh theo traffic, khả năng chịu lỗi và chính sách tổ chức.

Không nên page từng Pod restart khi controller đã tự thay và journey SLO không bị ảnh hưởng, trừ khi đó là tín hiệu mất resilience nghiêm trọng. Đánh thức con người cần mang lại quyết định có thể thực hiện.

## 7. Chọn severity theo ảnh hưởng, không theo độ ồn của log

Một mô hình phân cấp **tham khảo**:

| Severity | Tiêu chí ví dụ | Phản hồi |
| --- | --- | --- |
| SEV1 / P0 | Ngừng giao dịch trọng yếu trên diện rộng, mất dữ liệu hoặc nghi vi phạm bảo mật nghiêm trọng | Incident command ngay, huy động nhóm cần thiết, truyền thông khẩn theo policy |
| SEV2 / P1 | Ảnh hưởng đáng kể tới một hành trình, tenant lớn hoặc một vùng; burn-rate cao | Page primary, IC khi sự cố vượt một nhóm, cập nhật đều đặn |
| SEV3 / P2 | Ảnh hưởng hạn chế, có workaround; chưa đe dọa SLO nghiêm trọng | Điều tra bởi service owner theo mục tiêu phản hồi |
| SEV4 / P3 | Rủi ro vận hành/chất lượng nhỏ, vấn đề kỹ thuật chưa tác động người dùng | Ticket, xử lý trong chu kỳ ưu tiên phù hợp |

Mức P0/P1/P2 ở đây là **quy ước minh họa**, không phải tiêu chuẩn chung của mọi doanh nghiệp. Phải định nghĩa bằng tác động cụ thể, không chỉ số lượng exception. Một request chậm nhưng thanh toán trùng có thể nghiêm trọng hơn vài nghìn 404 vô hại.

Severity có thể thay đổi khi có dữ liệu mới. Việc hạ cấp sự cố cần lý do và người quyết định, không phải chỉ vì alert đã tắt. Nếu nguy cơ mất tiền, rò dữ liệu hoặc vi phạm pháp lý, mở luồng Security/Legal/Finance tương ứng song song với kỹ thuật.

## 8. Thiết kế lịch trực vận hành

Một lịch on-call bền vững phải cung cấp coverage thực tế mà không mặc định một người luôn sẵn sàng 24/7.

Các thành phần:

1. **Primary:** người nhận page đầu tiên trong ca.
2. **Secondary:** backup khi primary không xác nhận đúng thời hạn hoặc cần hỗ trợ.
3. **Escalation chain:** senior engineer, domain SME, platform, DBA, incident manager theo điều kiện.
4. **Coverage window:** timezone, ngày lễ, cuối tuần, lịch chuyển ca và nhiệm vụ ngoài giờ được quy định.
5. **SLA/SLO nội bộ về phản hồi:** khoảng xác nhận page, tập hợp nhóm và cập nhật đối với từng severity.
6. **Hand-off procedure:** thông tin thay đổi hệ thống, alert còn mở, sự cố đang theo dõi và risk của ca tiếp theo.
7. **Access readiness:** VPN/SSO, MFA, quyền production có thể sử dụng khi trực, không chờ đến lúc lỗi mới xin.
8. **Compensation và giới hạn sức tải:** phù hợp chính sách lao động và sức khỏe của thành viên trực.
9. **Escalation khi không có người:** cơ chế tự động chuyển tới secondary và duty manager.
10. **Audit và freshness:** ai trực hiện tại được xác định từ lịch nguồn sự thật, không phải wiki cũ.

### Ví dụ sơ đồ tiếp nhận

~~~text
SLO / alert page
      |
      v
Primary on-call
      |
      +-- acknowledge in policy window --> triage
      |
      +-- no acknowledgement / cannot act
                            |
                            v
                       Secondary
                            |
                      still blocked?
                       /       \
                      no       yes
                      |         |
                   triage   Incident manager /
                            domain SME escalation
~~~

Không đặt response window cứng như “5 phút” cho mọi tổ chức khi chưa có policy. Thời hạn cần phản ánh severity, coverage và độ khẩn. Lịch trực phải có **người dự phòng thực**, không phải chỉ tên một nhóm chat nhận thông báo.

### Chất lượng on-call không đo bằng số lần thức đêm

Một hệ thống có nhiều page ban đêm chưa chắc đang được vận hành tốt. Đo số page actionable, false page rate, số lần escalation vì thiếu ownership, thời gian acknowledgment và mức gián đoạn người trực. Chủ động loại alert nhiễu, tự động hóa bước an toàn và sửa hệ thống để người trực có thể ngủ.

## 9. Bàn giao ca: trạng thái hệ thống quan trọng hơn lịch cá nhân

Một handoff ngắn nên có:

- Ngày giờ, timezone và primary/secondary mới.
- Incident đang mở, severity, IC, cầu liên lạc, thời điểm cập nhật tiếp.
- Alert đang suppressed/acknowledged và thời điểm suppression kết thúc.
- Deployment, migration, secret rotation hoặc feature flag thay đổi gần đây.
- Dependency đang degraded, backlog còn tồn, nguy cơ capacity.
- Workaround đang bật và điều kiện tháo bỏ.
- Action tiếp theo, owner, deadline, ai có quyền thực hiện.
- Những quyền truy cập hoặc dashboard đang có sự cố.
- Xác nhận người nhận ca đã có mặt và hiểu các điểm rủi ro.

Ví dụ:

~~~text
Handoff UTC+07 / Ca 18:00–06:00
Primary: người theo lịch trực hiện hành
Secondary: người theo lịch dự phòng hiện hành

Open incident:
  - Payment provider p99 elevated; checkout SLO đang theo dõi
  - Current mitigation: đã giảm optional provider retries
  - Risk: backlog reconciliation chưa xử lý xong
  - Next action: kiểm tra reconciliation dashboard sau 30 phút
  - Escalation: Payment technical lead nếu failed transactions tăng

Recent changes:
  - Order deployment release-2026-11-12
  - Feature flag checkout_v2 đang ở mức rollout có kiểm soát
```

Các dữ liệu trên chỉ là ví dụ, không phải trạng thái production thực. Thông tin nhạy cảm như token, password, thông tin tài chính của khách hàng không nên đưa vào bản handoff.

Khi chuyển ca giữa các timezone, cần ghi **timestamp có timezone rõ**. Đừng ghi “đến 6 giờ sáng” nếu người nhận ở múi giờ khác.

## 10. Mẫu runbook có thể thực thi

Một runbook nên bắt đầu từ vấn đề người trực thấy trên page. Mẫu khuyến nghị:

~~~markdown
# Runbook: Checkout API 5xx tăng

Owner: Order Team
Secondary: Platform Team
Severity mặc định: theo ảnh hưởng thực và policy
Last reviewed: YYYY-MM-DD
Triggers: Checkout success burn-rate alert; sustained HTTP 5xx
Dashboards: <dashboard-link>
Logs/Traces: <query-link>
Related services: Order, Inventory, Payment, Gateway, DB, Broker
Required permissions: read-only observability; privileged changes need approval

## Nhận diện
- Alert nào kích hoạt?
- Người dùng/region/tenant nào ảnh hưởng?
- SLO và error budget đang bị tiêu hao thế nào?

## Kiểm tra an toàn (read-only)
1. Xem SLI + traffic + error code distributions.
2. Xem deployment/config changes gần thời điểm lỗi.
3. Mở traces để tìm service/dependency trên critical path.
4. Xem Kubernetes events, pod readiness/restarts.
5. Xem DB pool, broker lag, provider status nếu liên quan.

## Cây quyết định
- Có rollback candidate tương thích? -> đánh giá rollback.
- Provider external đang lỗi? -> circuit breaker/degrade theo contract.
- DB saturated? -> giảm tải, kiểm tra pool/slow queries, mời DBA.
- Mất dữ liệu/transaction không rõ? -> mở reconciliation; không retry mù.

## Mitigation được phép
- Tác vụ tự động có guardrail / thủ tục cần approval.
- Commands với target environment và expected output.
- Điều kiện dừng nếu rủi ro tăng.

## Xác minh
- Success/latency phục hồi theo target trong observation window.
- Không tăng duplicate orders, backlog, error secondary.
- Ghi timestamp, người thực hiện, version trước/sau.

## Rollback/đảo ngược mitigation
- Điều kiện, người quyết định, và dấu hiệu thất bại.
- Recovery state hoặc backup nếu hành động thay đổi dữ liệu.

## Escalation và truyền thông
- Người cần gọi và khi nào.
- Bản cập nhật tiếp theo và kênh liên lạc.

## Hậu sự cố
- Timeline, root cause, action items, owner.
```

Mẫu dùng placeholder, không ghi nhầm URL/tên cụm thật. Nội dung phải được tùy chỉnh cho topology thực và quyền của đội trực.

Một runbook tốt có **ngày kiểm tra gần nhất**, owner và đường dẫn mở được. Runbook không có timestamp hoặc chỉ dẫn “hỏi anh X” thường thất bại khi người đó nghỉ phép.

## 11. Runbook ưu tiên bước đọc an toàn trước bước thay đổi

Trong lúc sự cố, người trực dễ chạy một lệnh quen thuộc nhưng sai namespace hoặc sai cluster. Thiết kế hướng dẫn theo mức độ rủi ro:

| Mức | Thao tác | Nguyên tắc |
| --- | --- | --- |
| Read-only | Xem SLO, logs, traces, events, configs đã che secret | Cho phép người trực thực hiện theo quyền |
| Low-risk mitigation | Giảm traffic optional, tắt feature flag có kill switch rõ | Có điều kiện trước/sau, audit |
| Medium-risk | Rollback deployment, điều chỉnh replica hoặc concurrency | Xác minh compatibility và capacity |
| High-risk | DB failover, migration rollback, broker reset offsets, thay secrets hàng loạt | Cần SME/phê duyệt, backup và kế hoạch phục hồi |
| Destructive | Xóa dữ liệu, drop table, purge DLQ, xóa topic, force detach volume | Không tự động theo page; cần phê duyệt và quy trình riêng |

**Mọi lệnh thay đổi phải nêu target, preconditions, expected outcome, rollback và giới hạn blast radius.** Không hướng dẫn “delete all pods” như phản xạ chung khi thấy 5xx.

### Checklist trước khi thực hiện thay đổi

1. Đã xác định đúng cluster, region, namespace, service và version?
2. Lệnh là read-only hay thay đổi trạng thái?
3. Có thẩm quyền cho thay đổi và approval theo policy?
4. Có dữ liệu đang xử lý hoặc side effect có thể bị nhân đôi?
5. Biện pháp có thể khiến dependency chung quá tải hoặc khiến toàn cụm giảm capacity không?
6. Có thể đảo ngược không, trong bao lâu và cần backup nào?
7. Quan sát metric nào để biết biện pháp giúp hay gây hại?
8. Ai ghi timeline và thông báo kết quả?
9. Khi nào phải dừng, gọi SME hoặc chuyển sang phương án khác?

Không có thay đổi an toàn tuyệt đối; các guardrail giúp người trực nhận ra rủi ro trước khi sửa.

## 12. Ví dụ runbook kỹ thuật: Order API 5xx tăng

**Trigger:** checkout success rate giảm, burn rate tăng và request 5xx chủ yếu ở POST /orders.

**Mục tiêu:** giảm tác động mà không gây double order hoặc mất trạng thái nghiệp vụ.

### Bước 1: Xác nhận phạm vi

- Kiểm tra error rate và total request rate, không chỉ số 5xx tuyệt đối.
- Phân tách region, ingress, route, version, user segment nếu có dữ liệu.
- Xem lúc bắt đầu lỗi có trùng deploy, migration, feature flag hoặc network policy không.
- Xác nhận ID của vài request lỗi qua trace, xem bottleneck và HTTP status từ downstream.
- Kiểm tra loại lỗi: validation 4xx, provider 502/503, DB timeout, saturation.

Một truy vấn PromQL minh họa:

~~~promql
sum(rate(http_server_requests_seconds_count{
  service="order-service",
  status=~"5.."
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    service="order-service"
  }[5m])),
  1
)
~~~

Tên metric và labels khác nhau theo instrumentation; ví dụ không phải cú pháp dùng được nguyên vẹn ở mọi môi trường. Đây là tỷ lệ trên số HTTP server requests theo selector minh họa, **chưa chắc đồng nghĩa với user-journey success SLI** nếu việc xác nhận order là async.

### Bước 2: Kiểm tra tình trạng Pod

Lệnh đọc dữ liệu minh họa, thay placeholder bằng namespace/deployment đã xác minh:

~~~bash
kubectl --context <verified-context> -n <namespace> \
  get deploy,pods -l app=order-service

kubectl --context <verified-context> -n <namespace> \
  describe deploy order-service

kubectl --context <verified-context> -n <namespace> \
  get events --sort-by=.metadata.creationTimestamp
~~~

Kiểm tra image version, rollout, Ready/Not Ready, OOMKilled, CrashLoopBackOff, liveness/readiness failures và resource throttling. Không giả định “Pod Running = API khỏe”.

### Bước 3: Xác định nhánh xử lý

- **Sau deploy mới:** so sánh error rate theo version, xem schema compatibility và config revision; cân nhắc rollback nếu version cũ còn tương thích với DB và secret hiện tại.
- **DB pool pending cao:** xem connection acquisition latency, slow queries, locks, session limits; mời DBA trước thay đổi pool quá lớn.
- **Payment provider 503:** có thể giảm retry, bật circuit breaker và đưa order vào PENDING nếu contract cho phép; không retry charge bằng idempotency key khác.
- **Inventory timeout:** xem queue, network, dependency SLO; giảm tải hoặc degrade nếu nghiệp vụ cho phép.
- **Broker backlog:** xác minh outbox vẫn durable và consumers còn xử lý; không xóa queue để làm biểu đồ lag về 0.

### Bước 4: Xác minh mitigation

- SLO success và latency trở về trong observation window phù hợp.
- Error/timeout giảm ở tất cả region/tenant bị ảnh hưởng, không chỉ một Pod.
- Số order duplicate, pending reconciliation và message backlog không tăng bất thường.
- Không có lỗi mới ở Payment/Inventory/DB do chuyển tải.
- Ghi action timestamp, người thực hiện, artifact/config revision và quyết định tiếp theo.

Nếu symptom giảm nhưng dữ liệu payment chưa rõ, incident có thể tiếp tục mở ở trạng thái business reconciliation. **Khôi phục HTTP 200 không đủ để tuyên bố thanh toán đúng.**

## 13. Ví dụ runbook: Kubernetes Pod Not Ready hoặc restart

**Trigger:** available replicas giảm, pod readiness fail hoặc restart count tăng cùng tác động user journey.

1. Xác định Pod đang ở trạng thái Pending, ContainerCreating, Running Not Ready hay CrashLoopBackOff.
2. Dùng events và container status tìm image pull, scheduling/resource, secret mount, startup/liveness probe hoặc OOMKilled.
3. Kiểm tra đường dẫn/port readiness, app config, startup latency và dependency cần thiết.
4. Xem CPU throttling, memory, JVM GC pause và thread pool; probe quá nhạy có thể làm restart storm.
5. Nếu chỉ xảy ra ở phiên bản mới, so sánh runtime, image digest, config/secret và schema migration với phiên bản cũ.
6. Nếu tất cả Pod cùng Not Ready khi DB outage, không tự restart mọi replica; xem lại readiness dependency policy.
7. Đánh giá rollout rollback có an toàn với database migration và secret rotation không.
8. Xác nhận Pod mới Ready ổn định và traffic thật qua ingress/Service thành công.

Ví dụ lệnh đọc:

~~~bash
kubectl --context <verified-context> -n <namespace> \
  describe pod <pod-name>

kubectl --context <verified-context> -n <namespace> \
  logs <pod-name> -c <container-name> --previous --tail=200
~~~

Tùy phiên bản công cụ và trạng thái container, `--previous` chỉ trả log của container instance trước đó nếu tồn tại. Không in giá trị secret hoặc dump environment vào kênh công khai.

Không nhầm sự cố scheduler thiếu quota với lỗi app. Tăng liveness failureThreshold có thể chỉ che app deadlock; thay đổi ngưỡng probe cần có bằng chứng và test sau khắc phục.

## 14. Ví dụ runbook: database connection pool bị nghẽn

**Triệu chứng:** Order API p99 tăng, nhiều request timeout khi lấy connection; CPU app không nhất thiết cao.

### Chẩn đoán

- Tách **pool acquisition wait**, SQL execution và commit latency.
- Kiểm tra active/idle/pending connections, giới hạn DB và số replicas.
- Xem long-running transactions, locks, deadlocks và slow queries.
- So sánh traffic và pool config ngay trước khi sự cố bắt đầu.
- Tìm connection leak: active tăng, không giảm dù traffic đã xuống.
- Xác minh một migration/index maintenance có đang giữ lock kéo dài không.

### Mitigation có kiểm soát

- Hạn chế concurrency hoặc rate limit upstream để DB phục hồi.
- Rollback code/config mới nếu thấy truy vấn N+1 hoặc leak mới.
- Kết thúc truy vấn/transaction chỉ theo quy trình DBA và kiểm soát side effects.
- Tăng connection pool **chỉ sau khi tính tổng toàn cluster** và khả năng DB.
- Không restart tất cả Pod đồng loạt vì tạo connection storm.

Ví dụ 12 replica × pool max 40 có thể tạo tối đa khoảng **480 application DB connections** trước các workload phụ. Nếu DB limit thấp hơn hoặc còn nhiều consumer khác, việc tăng pool lên 60 sẽ làm rủi ro tăng, không tự sửa nguyên nhân.

**Verification:** giảm pool pending và DB lock wait, p95/p99 request phục hồi, error rate giảm, không có transaction bị mất hoặc duplicate retry.

## 15. Ví dụ runbook: consumer lag hoặc dead-letter queue tăng

**Trigger:** độ tuổi message cũ nhất vượt ngưỡng nghiệp vụ, event processing latency và consumer lag tăng, backlog đe dọa SLO thông báo hoặc order state.

**Kiểm tra read-only:**

- Consumer group/vhost/queue cụ thể nào bị ảnh hưởng, partition nào bị lag?
- Producer rate so với consumer processing rate?
- Consumer rebalances, authentication errors, poison messages, schema errors?
- Thread pool/DB dependency của consumer có bị saturation?
- Có release mới làm message processing chậm, payload lớn hoặc schema không tương thích?
- DLQ tăng do cùng error code hay nhiều loại khác nhau?

**Mitigation:**

- Sửa dependency/consumer lỗi hoặc rollback phiên bản không tương thích.
- Giảm producer load nếu có thể và theo policy, tránh đẩy broker đầy.
- Tăng consumer concurrency/replicas khi partitioning, DB capacity và idempotency cho phép.
- Đưa poison message vào DLQ theo quy tắc thay vì retry vô hạn.
- Nếu phải replay, xác minh dữ liệu đã xử lý và idempotency/ordering trước, phân chia batch có giới hạn và quan sát side effects.

**Cấm mặc định:** reset consumer offsets về latest hoặc purge queue để metric lag trở về 0. Hành động đó có thể **bỏ qua nghiệp vụ chưa xử lý**, không phải phục hồi. Cần approval, snapshot và kế hoạch replay nếu buộc thao tác destructive.

**Verification:** oldest message age giảm, throughput xử lý phục hồi, DLQ không tăng bất thường, dữ liệu Order/Notification nhất quán, không double delivery gây side effect không mong muốn.

## 16. Ví dụ runbook: Payment Provider chậm hoặc trả lỗi

Đối tác thanh toán là dependency nhiều rủi ro vì timeout có thể xảy ra sau khi giao dịch đã được chấp nhận.

**Triệu chứng:** authorization p99 tăng, 502/503/504 hoặc network errors; khách hàng báo bị trừ tiền nhưng màn hình chưa xác nhận.

Quy trình:

1. Kiểm tra provider status chính thức và metrics theo provider/region/method.
2. Phân biệt request **chưa gửi**, **đã gửi nhưng timeout** và **đã nhận response lỗi xác định**.
3. Xác nhận transaction IDs và idempotency keys có trong kho dữ liệu bảo vệ; không công khai thông tin thẻ.
4. Không retry charge với key mới khi outcome chưa rõ; dùng reconciliation/status API theo hợp đồng.
5. Cân nhắc circuit breaker/fallback provider nếu policy cho phép và đủ điều kiện chống double charge.
6. Đặt trạng thái PENDING_RECONCILIATION khi cần thay vì trả “thanh toán thành công” giả.
7. Liên hệ provider support theo incident escalation và lưu ticket/correlation ID an toàn.
8. Truyền thông rõ rằng kết quả đang xử lý nếu chưa có bằng chứng hoàn tất.
9. Sau khi provider phục hồi, chạy reconciliation được kiểm soát và kiểm tra sổ giao dịch.

**Verification:** success rate, p95/p99, pending payments, duplicate authorizations, chargeback risk và audit logs; đóng incident khi cả availability **và tính đúng giao dịch** đã được xác nhận theo policy.

Tránh dùng runbook availability thông thường cho sự cố nghi rò rỉ thông tin thanh toán; mở security incident và xử lý dữ liệu theo quy trình liên quan.

## 17. Incident workflow: từ page đến phục hồi

Một vòng đời minh họa:

~~~text
Monitoring / user report
          |
          v
Alert fired -> On-call paged
          |
          v
Acknowledge + initial triage
          |
          v
Assess impact + severity
          |
          +-- minor/local -> service owner xử lý
          |
          +-- major -> declare incident, assign IC
                          |
                          v
                   Establish channel
                          |
                          v
                 Mitigate user impact
                          |
                   parallel diagnose
                          |
                          v
                  Verify recovery
                          |
                          v
                    Resolve incident
                          |
                          v
               Postmortem + action items
                          |
                          v
                 Update runbooks/SLOs
~~~

### 17.1. Acknowledge không đồng nghĩa resolve

Khi một người nhấn acknowledge, hệ thống chỉ biết đã có người nhận trách nhiệm phản hồi. Phải ghi rõ người đang triage và khi nào escalation nếu không có tiến triển. Không để alert bị acknowledge vô hạn làm mất thông tin.

### 17.2. Declare sớm khi có dấu hiệu nghiêm trọng

Nếu khách hàng không checkout được trên diện rộng hoặc có rủi ro duplicate payment, nên công bố incident và huy động vai trò cần thiết sớm theo policy. Không cần chứng minh root cause mới được lập incident. Severity có thể được điều chỉnh khi hiểu rõ hơn.

### 17.3. Phục hồi trước, tìm gốc song song

Trong nhiều sự cố, rollback code mới hoặc tắt feature flag rủi ro là cách khôi phục nhanh hơn phân tích từng stack trace. Tuy nhiên **không rollback mù** nếu database migration, credential rotation hoặc schema consumer đã đổi và phiên bản cũ không còn tương thích.

### 17.4. Xác minh trước khi đóng

Mỗi mitigation cần observation window và success criteria. Đừng đóng sự cố chỉ vì một alert chấm dứt trong một phút khi backlog, dữ liệu không nhất quán hoặc traffic thấp che vấn đề.

## 18. Incident command trong sự cố đa nhóm

Một IC tốt tập trung vào thông tin và quyết định, không tự làm mọi phần việc.

Checklist IC:

- Tuyên bố sự cố với ID, severity ban đầu và mô tả impact.
- Chỉ định technical lead, communications lead và scribe khi cần.
- Thiết lập kênh hoặc bridge chính, xác định nguồn sự thật của timeline.
- Chia công việc thành các giả thuyết, mỗi action có owner và thời hạn cập nhật.
- Thống nhất quy tắc phát biểu: điều đã xác minh, giả thuyết, việc đang thử, bước tiếp theo.
- Ưu tiên mitigation có blast radius nhỏ; cân nhắc rollback/feature flag/rate limit.
- Thông báo định kỳ theo severity và audience; không đợi có thông tin hoàn hảo mới cập nhật.
- Bảo đảm không có hai nhóm đồng thời thay đổi cùng hệ thống theo hướng xung đột.
- Theo dõi việc phục hồi của primary SLO và downstream side effects.
- Tuyên bố resolution khi đạt điều kiện, rồi bàn giao follow-up cho owner.

### Mẫu thông báo cập nhật

~~~text
Incident ID: INC-XXXX
Severity: P1 (theo quy ước nội bộ)
Status: INVESTIGATING / MITIGATING / MONITORING / RESOLVED
Started: timestamp + timezone
Impact: Tỷ lệ tạo đơn thành công giảm tại region ...
Known facts: ... (đã kiểm chứng)
Current hypothesis: ... (chưa xác minh)
Mitigation: ... (người phụ trách + thời điểm)
Customer guidance: ...
Next update: timestamp + timezone
Incident commander: vai trò/người được phân công
~~~

Không ghi tên khách hàng, token, thông tin tài chính hoặc dữ liệu nhạy cảm vào status page. Dùng ngôn ngữ mô tả tác động thay vì kết luận nguyên nhân khi chưa có bằng chứng.

## 19. Ghi timeline và quản lý giả thuyết

Trong incident, trí nhớ cá nhân không đáng tin. Dùng một timeline có thời gian rõ:

| Thời điểm minh họa | Sự kiện | Bằng chứng/owner |
| --- | --- | --- |
| 10:02 +07 | Checkout burn-rate alert bắt đầu | Monitoring |
| 10:04 +07 | Primary acknowledge | On-call |
| 10:08 +07 | Xác nhận chỉ region A ảnh hưởng | Traces/RUM |
| 10:11 +07 | Phát hiện rollout Payment v2 trùng thời điểm | Deployment log |
| 10:14 +07 | IC chấp thuận rollback tương thích | Decision record |
| 10:19 +07 | Rollback hoàn tất, error rate giảm | Dashboard |
| 10:29 +07 | Bắt đầu monitoring recovery | IC |
| 10:49 +07 | SLO và giao dịch đối soát đạt điều kiện | Technical lead |

Bảng này chỉ minh họa, không diễn tả một sự cố thật. Nên ghi **ai làm gì, khi nào, ở môi trường nào, kết quả**; không chỉ liệt kê tin nhắn chat.

Phân biệt:

- **Fact:** đo được qua metric, trace, event, user report đã xác minh.
- **Hypothesis:** có khả năng nhưng chưa đủ bằng chứng.
- **Decision:** chọn hành động A vì trade-off cụ thể.
- **Action:** người thực hiện và kết quả.
- **Risk:** điều vẫn chưa biết hoặc có thể gây lỗi tiếp.

Nếu một giả thuyết bị bác bỏ, cập nhật rõ thay vì xóa khỏi lịch sử; đó là dữ liệu giúp postmortem học từ quá trình điều tra.

## 20. Escalation theo thời gian, rủi ro và chuyên môn

Không chờ primary mất kết nối mới escalation. Một số tình huống cần gọi người khác ngay:

| Điều kiện | Escalation |
| --- | --- |
| Primary không acknowledge đúng thời hạn | Secondary/incident manager |
| Không xác định service owner | Platform/service catalog owner |
| Cần thay đổi DB dữ liệu hoặc failover | DBA, technical approver |
| Khả năng rò secret hoặc truy cập trái phép | Security incident commander |
| Nghi charge trùng hoặc mất giao dịch | Payment/Finance/Operations |
| Outage ảnh hưởng nhiều team | Chỉ định IC và nhóm chuyên gia |
| Không có quyền production trong ca | Privileged operator/break-glass policy |
| Mitigation thất bại hoặc tác động lan rộng | Nâng severity và mở rộng incident bridge |
| SLO đang phục hồi nhưng backlog dữ liệu lớn | Data/business reconciliation owner |

Runbook nên có câu **“Dừng ở đây và gọi chuyên gia nếu…”** trước thao tác nguy hiểm. Những gì người trực không biết là tín hiệu cần escalation, không phải lý do để thử destructive command.

Escalation không phải quy trách nhiệm cá nhân. Mục đích là đưa đúng chuyên môn và quyền vào thời điểm quyết định mà vẫn giữ một incident owner duy nhất.

## 21. Change management và emergency rollback

Rất nhiều sự cố bắt đầu gần một lần deploy/config change. Do đó runbook cần cho người trực truy vết:

- Image digest và artifact version.
- Deployment time/region/namespace.
- Config revision và feature flag changes.
- DB migration/schema version.
- Secret rotation/credential version.
- Infrastructure/IAM/network policy changes.
- Consumer/provider compatibility matrix.

### Rollback an toàn gồm những bước nào?

1. Xác minh chỉ số nào suy giảm và nó trùng thay đổi nào.
2. Đánh giá app version trước có còn tương thích DB schema, event version, API và secret mới không.
3. Xác nhận mục tiêu rollback và manifest/config revision.
4. Kiểm tra capacity trong lúc rolling update, connection draining và in-flight requests.
5. Thực hiện theo policy quyền/approval, ghi đầy đủ hành động.
6. Theo dõi canary/rollout theo SLO và error rate; dừng nếu hậu quả tăng.
7. Xác minh trạng thái nghiệp vụ, queue, payment reconciliation và customer impact.
8. Mở follow-up để xử lý nguyên nhân và tái triển khai khi an toàn.

**Tránh “rollback code = rollback mọi thứ”.** Schema migration có thể không đảo ngược được, event đã phát không thể thu hồi, payment đã charge không thể giải quyết bằng deploy bản cũ. Trong các tình huống đó, feature flag, forward fix hoặc traffic rerouting an toàn có thể phù hợp hơn.

## 22. Tự động hóa runbook mà vẫn giữ guardrail

Có thể tự động hóa bước đọc và thao tác ít rủi ro:

- Tạo incident với ID, severity, channel và các đường dẫn dashboard.
- Tổng hợp error-rate, traffic, version, release diff và Pod readiness.
- Gắn trace/log exemplars liên quan vào timeline.
- Kiểm tra on-call schedule và gửi page/escalation.
- Kiểm tra những điều kiện trước khi bật feature flag hoặc rollback có policy.
- Đề xuất hành động có kèm risk/rollback instructions.
- Theo dõi mitigation để xác nhận success criteria.

**Không tự động hóa vô điều kiện** việc xóa message, reset consumer offsets, failover DB, thay đổi security policy hoặc chạy migration destructive khi một alert phát ra. Tự động hóa nên có:

1. Input đã được xác minh (cluster, namespace, service, region).
2. Idempotency cho tác vụ lặp.
3. Dry-run hoặc read-only preview khi hỗ trợ.
4. Thẩm quyền/phê duyệt tương ứng mức rủi ro.
5. Giới hạn blast radius và tốc độ thay đổi.
6. Audit log, correlation/incident ID và người chịu trách nhiệm.
7. Khả năng dừng hoặc đảo ngược.
8. Tín hiệu kiểm chứng hậu hành động.

Một automation chỉ hữu ích khi **nó không nhân sự cố lên nhiều lần** do alert flapping hoặc retry job không idempotent.

## 23. Runbook và quản lý bí mật, dữ liệu nhạy cảm

Một runbook thường có quyền truy cập production nên cần thiết kế bảo mật:

- Không đưa password, API key, private key, recovery code, token hoặc DSN có credential vào Markdown.
- Không bảo người trực chụp màn hình chứa PII hoặc paste full payment payload vào incident channel.
- Thay secret bằng link đến secret manager/identity workflow được cấp quyền.
- Lệnh truy vấn phải lọc hoặc redact các cột nhạy cảm; không xuất bảng khách hàng ra public chat.
- Chỉ người được phân quyền thực thi lệnh thay đổi; audit và phê duyệt theo risk.
- Break-glass có TTL, MFA, giám sát và hậu kiểm theo policy.
- Status page và cập nhật khách hàng chỉ mô tả tác động đã được xác minh.
- Nghi security incident phải chuyển sang quy trình bảo toàn bằng chứng, hạn chế thay đổi hệ thống làm mất dấu vết.
- Log/trace/incident attachments có retention và access control; incident ID không tự cấp quyền xem dữ liệu.
- Không nhúng URL có token hoặc signed link dài hạn vào runbook.

Sự cố bảo mật có thể xung đột với mục tiêu khôi phục nhanh: restart hoặc cleanup có thể xóa forensic evidence. Ưu tiên phối hợp với security incident commander theo policy, không áp dụng runbook availability một cách máy móc.

## 24. Runbook cho thay đổi có thể gây mất dữ liệu

Các hành động như manual DB fix, consumer offset reset, queue purge, DLQ replay và failover có rủi ro lớn. Trước khi đề xuất:

1. Xác định **source of truth** và dữ liệu nào có thể bị mất hoặc phát lại.
2. Xác định recovery point/time objectives (RPO/RTO) theo policy.
3. Có snapshot/backup hoặc change log tương thích để phục hồi.
4. Kiểm tra transactional boundaries và idempotency.
5. Ghi số record/message và phạm vi trước hành động.
6. Lập dry-run để ước lượng tác động nếu hỗ trợ.
7. Có phê duyệt của data owner/SME/IC theo policy.
8. Chọn batch nhỏ, kiểm tra kết quả và dừng khi có dấu hiệu bất thường.
9. Tạo báo cáo reconciliation sau thay đổi.

Không dùng một lệnh “xóa topic rồi tạo lại” như biện pháp chữa lag. Có thể làm lag bằng 0 vì không còn dữ liệu, nhưng thực chất mất công việc chưa xử lý. Tương tự, `TRUNCATE` một bảng lỗi tạm thời có thể xóa thông tin duy nhất giúp đối soát giao dịch.

## 25. SLO, runbook và incident ưu tiên theo business impact

Một kỹ thuật hữu ích là lập bản đồ:

~~~text
User journey SLO
      |
      +-- API Gateway
      |      +-- ingress / auth / rate limits
      |
      +-- Order Service
      |      +-- DB + outbox
      |
      +-- Inventory Service
      |      +-- reservation semantics
      |
      +-- Payment Service
             +-- external provider
             +-- reconciliation
```

Với mỗi node, xác định người sở hữu, runbook và loại alert. Một sự cố “Payment provider mất kết nối” nên mở từ checkout impact, không chỉ từ message “TCP connect failed” trên một Pod. Nếu checkout vẫn hoạt động nhờ provider dự phòng, có thể theo dõi/ticket tùy mức độ rủi ro; nếu 70% thanh toán không hoàn tất, cần incident bất kể CPU có bình thường hay không.

Các câu hỏi ưu tiên:

- Bao nhiêu người dùng/tenant/region thực sự ảnh hưởng?
- Hành trình nào không thể hoàn tất, có workaround không?
- Có nguy cơ dữ liệu sai/mất/nhân đôi?
- Error budget đang burn nhanh mức nào?
- Có thể giảm tác động mà không gây thêm hại không?
- Hệ thống có giảm capacity an toàn nếu chuyển traffic không?
- Ai có quyền thực hiện phương án giảm tác động?
- Ai xác nhận khôi phục đúng nghĩa nghiệp vụ?

Không nhầm **độ ồn alert** với **tác động sản phẩm**. Một trăm error logs của một background task ít quan trọng có thể kém khẩn hơn một triệu giao dịch mất khả năng xác nhận thanh toán với rất ít exception.

## 26. Postmortem không đổ lỗi và action items thực chất

Sau sự cố, nên viết postmortem theo cách tìm lỗ hổng hệ thống và quy trình, không quy trách nhiệm dựa trên kết quả mà người xử lý không thể biết lúc đó.

Cấu trúc:

1. **Summary:** điều xảy ra, khoảng ảnh hưởng, severity.
2. **User impact:** hành trình, tỷ lệ request lỗi/chậm, tenant/region và dữ liệu nghiệp vụ.
3. **Timeline:** theo timestamp và bằng chứng, từ detection đến resolution.
4. **Detection gap:** alert báo chậm, sai owner hay tín hiệu bị mất?
5. **Contributing factors:** code, config, dependency, deployment, capacity, quy trình.
6. **What went well:** bước giúp giảm tác động, dashboard/runbook hiệu quả.
7. **What was difficult:** quyền truy cập, log thiếu, ownership mơ hồ, lệnh rủi ro.
8. **Root cause / causal analysis:** nguyên nhân đã xác minh và các giới hạn của bằng chứng.
9. **Prevent recurrence:** test, safeguard, architecture fixes, rollout gate.
10. **Reduce time to recover:** alert, runbook, ownership, automation, đào tạo.
11. **Actions:** owner, ưu tiên, deadline, điều kiện hoàn tất có thể kiểm tra.

Ví dụ action không đủ tốt: “Team phải cẩn thận hơn”. Action tốt hơn: “Thêm integration test chứng minh consumer cũ đọc được event schema mới; owner Messaging Team; kiểm tra qua CI compatibility gate”. Một action khác: “Bổ sung runbook phân biệt timeout sau provider accepted vs provider rejected để tránh double charge”.

**Không cần biến mọi sự cố nhỏ thành báo cáo dài**, nhưng sự cố nghiêm trọng hoặc có tác động lặp lại cần có review, action items và theo dõi đến khi đóng thật.

## 27. Đo chất lượng vận hành và mức trưởng thành của runbook

Những chỉ số có thể theo dõi:

| Chỉ số | Ý nghĩa | Cảnh báo khi diễn giải |
| --- | --- | --- |
| MTTA – Mean Time to Acknowledge | Thời gian từ alert đến khi có người nhận | Acknowledge nhanh không có nghĩa giảm tác động nhanh |
| TTD/MTTD – Time to Detect | Bao lâu mới phát hiện dấu hiệu ảnh hưởng | Định nghĩa mốc bắt đầu rõ |
| TTM – Time to Mitigate | Bao lâu để giảm tác động người dùng | Phân biệt giảm tác động với sửa gốc |
| MTTR – Mean Time to Recover/Restore | Thời gian phục hồi theo định nghĩa cụ thể | “R” có thể được hiểu khác nhau; cần ghi rõ |
| Page actionability rate | Tỷ lệ page cần và có hành động | Page vô ích gây mệt mỏi, bỏ sót page nguy hiểm |
| Escalation due to missing ownership | Số lần không tìm được người phụ trách | Cho thấy service catalog/on-call mapping yếu |
| Runbook coverage | Tỷ lệ cảnh báo actionable có runbook đang dùng được | Có link không đồng nghĩa runbook đúng |
| Runbook freshness | Ngày kiểm tra gần nhất và tỉ lệ tài liệu lỗi thời | Tài liệu cần test theo thay đổi hệ thống |
| Recurring incidents | Lỗi tái diễn cùng nguyên nhân | Cho thấy action chưa hoàn tất |
| Error budget burn | Tác động trực tiếp tới mục tiêu SLO | Cần denominator và cửa sổ nhất quán |
| Change failure rate | Tỷ lệ thay đổi gây suy giảm dịch vụ | Phải định nghĩa phạm vi/thời gian |
| Reconciliation backlog | Tác động nghiệp vụ còn sau phục hồi | HTTP khỏe không đủ để đóng |

Không nên tối ưu một metric độc lập bằng cách đóng sự cố sớm hoặc giảm page vô điều kiện. Một hệ thống với MTTR thấp nhưng mất giao dịch không được coi thành công. Dùng kết hợp **SLO, tác động dữ liệu, trải nghiệm người dùng và mức công việc trực**.

### Đo runbook thực sự hữu ích

Một runbook tốt không chỉ có mặt:

- Người mới trực có thể mở trong vài thao tác, không phải hỏi link.
- Hướng dẫn còn đúng với namespace, dashboard và quyền hiện tại.
- Bước đầu tiên chỉ đọc, rõ ràng và ít rủi ro.
- Có cây quyết định và điều kiện gọi SME.
- Có thao tác phục hồi/rollback phù hợp với phiên bản đang chạy.
- Có cách xác minh tác động giảm và theo dõi side effect.
- Có owner, lịch kiểm tra và cơ chế cập nhật sau incident.
- Có lịch diễn tập không phá production khi cần.

## 28. Diễn tập incident và game day

Runbook chỉ được kiểm chứng khi người dùng thử thực hiện. Có thể tổ chức game day trên môi trường staging tạm hoặc môi trường thử được kiểm soát:

1. Mô phỏng Payment API trả 503 hoặc latency tăng.
2. Gửi page tới nhóm diễn tập theo quy trình và ghi thời gian acknowledgment.
3. Cho người trực mở runbook mà không tiết lộ trước root cause.
4. Kiểm tra dashboard, trace links, quyền truy cập và bước xác định impact.
5. Đề xuất mitigation trong giới hạn an toàn, xác minh bằng SLO synthetic.
6. Test escalation khi primary không thể xử lý.
7. Đo thời gian tìm owner, thời gian ra quyết định và điểm mơ hồ trong tài liệu.
8. Ghi nhận thiếu sót, cập nhật runbook rồi kiểm tra lại.

Các kịch bản hay:

- Một Pod version mới CrashLoopBackOff vì config thiếu.
- All Pod Not Ready do readiness gọi DB đang lỗi.
- Kafka consumer lag sau schema incompatibility.
- DB pool saturation do traffic burst.
- Secret rotation làm client mất auth.
- Payment callback bị duplicate hoặc timeout.
- Region failover cần thay định tuyến và đối soát.
- Observability backend bị lỗi đúng lúc incident.

**Không tạo chaos vào production tùy tiện**. Diễn tập cần phạm vi được phê duyệt, rollback và quy tắc dừng rõ; đối với thao tác rủi ro, dùng sandbox với synthetic data.

## 29. Runbook theo mô hình "5 phút đầu"

Trong năm phút đầu của một sự cố nghiêm trọng, mục tiêu thường không phải chứng minh root cause hoàn toàn mà là tạo quyết định có ích:

- Xác nhận đã nhận page, tránh trôi alert.
- Ghi incident ID, giờ bắt đầu và primary owner.
- Xác minh người dùng có bị ảnh hưởng không và ước lượng phạm vi.
- Xác minh SLO/burn-rate/traffic, xem các deploy gần thời điểm lỗi.
- Chọn kênh liên lạc và chỉ định IC nếu vượt một nhóm.
- Bảo vệ dữ liệu, đặc biệt payment/order/authorization khi outcome chưa rõ.
- Kiểm tra có mitigation ít rủi ro như feature kill switch/circuit breaker không.
- Gọi secondary/SME sớm nếu cần quyền hoặc có dấu hiệu mất dữ liệu.
- Chốt lần cập nhật tiếp theo, kể cả khi nguyên nhân chưa rõ.

Người trực không cần thuộc lòng tất cả command. Runbook cần dẫn họ tới đúng decision tree, quyền và dashboard. Một bước “nhấn vào dashboard này và kiểm tra hai chỉ số này” tốt hơn một đoạn giải thích dài không đưa ra hành động.

## 30. Tình huống nhiều nhóm cùng có một thay đổi gần thời điểm lỗi

Giả sử Payment Team vừa triển khai retry policy, Platform Team thay ingress và Order Team bật feature flag checkout mới. Nếu tất cả xảy ra cùng giờ, giả thuyết “last deploy caused it” chưa đủ.

IC nên:

1. Lập **timeline thay đổi theo thời gian** và phạm vi, không chọn một thủ phạm ngay.
2. So sánh lỗi theo version/region/tenant/route để biết lỗi chỉ ở phiên bản nào.
3. Chỉ định một nhóm đọc traffic/ingress, một nhóm đọc trace/Payment, một nhóm kiểm tra feature flag.
4. Tránh ba nhóm cùng rollback độc lập khiến không còn bằng chứng biết thay đổi nào hữu ích.
5. Ưu tiên action có blast radius nhỏ và quan sát được; ghi rõ thời gian trước/sau.
6. Nếu có phục hồi, tiếp tục kiểm tra dữ liệu thanh toán/đơn hàng, không kết luận vội từ 5xx.
7. Sau incident, đánh giá thay đổi nào thiếu canary, deployment coordination hay rollback guide.

Runbook nên hỗ trợ **thay đổi có phối hợp** chứ không tự động giả định service của mình luôn là nguyên nhân.

## 31. Tài liệu as code và kiểm tra freshness

Một cách giữ runbook không lỗi thời là lưu Markdown cùng repository hoặc knowledge base có pull request/review. Khi deployment hoặc topology thay đổi, yêu cầu kiểm tra liên kết:

- Runbook link từ alert còn truy cập được.
- Tên deployment/namespace và route đúng theo source of truth.
- Query dashboard/log phù hợp phiên bản instrumentation.
- Contact và rotation dùng link động tới lịch trực, không hard-code người.
- Break-glass/permission workflow đã cập nhật.
- Recovery/rollback process phản ánh migration và secret rotation mới.
- Checklist kiểm thử được cập nhật sau incident hoặc game day.

Có thể chạy linter cho link, schema các trường bắt buộc và code block mang tính read-only. Với command có quyền thay đổi, nên đặt trong automation được kiểm soát hoặc tài liệu có preconditions rõ, không cho phép người đọc copy vào cluster bất kỳ.

**Owner phải chịu trách nhiệm làm mới runbook** khi thay đổi quan trọng. Một quy trình tốt là mỗi change request liên quan alert, dependency hoặc kiến trúc phải xem xét liệu runbook và on-call routing cần cập nhật không.

## 32. Service catalog là nơi tìm ownership

Khi đội trực nhận alert “HTTP 503 qua gateway”, không nên phải dò Git để biết team nào sở hữu endpoint. Service catalog tối thiểu cần:

~~~yaml
service: order-service
domain: checkout
lifecycle: production
owner_team: order-team
oncall_primary: "<rotation-link>"
oncall_secondary: "<secondary-rotation-link>"
slo_dashboard: "<slo-dashboard-link>"
runbook_index: "<runbook-link>"
repository: "<repo-link>"
deployments:
  - "<deployment-link>"
dependencies:
  - inventory-service
  - payment-service
  - order-database
data_classification: "sensitive-business-data"
```

Đây chỉ là schema minh họa, không phải định dạng bắt buộc của Backstage hay hệ catalog cụ thể. Tránh lưu tên cá nhân cố định trong repo mà không cập nhật khi đổi ca; dùng liên kết tới hệ lịch trực đang hoạt động.

Dịch vụ không có owner cần được gắn **temporary accountable owner** và kế hoạch hoàn thiện. Không để một production service tiếp tục vận hành không có người có trách nhiệm bảo trì, permission và SLO.

## 33. Quyền và trách nhiệm theo vòng đời phát hành

Một service owner không chỉ là “người sửa bug khi production lỗi”. Trách nhiệm gồm:

| Giai đoạn | Owner chịu trách nhiệm |
| --- | --- |
| Thiết kế | Xác định SLO, dependency, degradation mode, dữ liệu và failure modes |
| Phát triển | Test timeout/retry, idempotency, observability, security |
| Trước deploy | Runbook, dashboard, on-call routing, rollback compatibility |
| Khi deploy | Theo dõi rollout, canary, acceptance gates, capacity |
| Khi có incident | Nhận page, triage, giảm tác động, escalation |
| Sau incident | Postmortem, sửa nguyên nhân, cập nhật runbook/alerts |
| Khi ngừng service | Gỡ alerts/rotation, chuyển ownership dữ liệu và phụ thuộc |

**You build it, you run it** có thể là một phương pháp, nhưng không phải doanh nghiệp nào cũng tổ chức cùng một kiểu. Dù mô hình là DevOps, SRE-centralized hay shared operations, một dịch vụ production vẫn cần primary accountable owner, quyền ra quyết định và lộ trình escalation rõ.

Đội platform có thể hỗ trợ Kubernetes, gateway, observability và shared database, nhưng không tự nhiên sở hữu semantics của thanh toán hay reservation. Ngược lại, product team không nên bị yêu cầu tự thực hiện failover storage nếu không có quyền và chuyên môn.

## 34. Kế hoạch vận hành cho thay đổi quy mô lớn

Một migration API/event, database hoặc region cần chuẩn bị trước runbook và lịch trực:

1. Chốt owner/phân quyền và cửa sổ triển khai.
2. Thống nhất SLI/SLO và rollback gates.
3. Xác nhận backward/forward compatibility giữa version cũ/mới.
4. Chuẩn bị dashboard/traces, error code và alert routing.
5. Chuẩn bị người trực từ các nhóm phụ thuộc và người phê duyệt thao tác rủi ro.
6. Ghi data reconciliation plan nếu migration gây duplicate/missing events.
7. Xác định stop conditions nếu burn rate tăng hoặc dữ liệu không nhất quán.
8. Chuẩn bị runbook rollback/forward-fix và chiến lược phục hồi phụ thuộc.
9. Thực hiện canary/rolling theo policy, theo dõi đến khi ổn định.
10. Bàn giao hệ thống cho ca sau nếu rollout kéo qua cửa sổ trực.

Một release chưa có runbook cho failure mode nghiêm trọng hoặc chưa có owner đang trực trong cửa sổ rủi ro có thể cần hoãn theo change policy. Không mặc định mọi thay đổi đều phải có “war room” lớn, nhưng thay đổi nguy hiểm phải có quyền và kế hoạch được xác nhận.

## 35. Checklist runbook sẵn sàng đưa vào production

- [ ] Mọi hành trình trọng yếu có SLI/SLO, owner và đường dẫn dashboard.
- [ ] Mọi alert cần page có **rotation và runbook rõ**, không chỉ kênh chung.
- [ ] Primary/secondary và escalation chain có coverage thực theo timezone.
- [ ] Service catalog ghi owner team, dependency, deployment, repository và runbook.
- [ ] Có severity policy dựa trên tác động người dùng và dữ liệu.
- [ ] Vai trò IC, technical lead, communications và action owner được định nghĩa.
- [ ] Runbook có trigger, symptom, impact, checks, decision tree, mitigation, verification và rollback.
- [ ] Các bước đầu an toàn/read-only; bước ghi production có scope/approval/guardrail.
- [ ] Mọi command chỉ rõ cluster/namespace/service, không sử dụng wildcard destructive.
- [ ] Có tiêu chí chuyển cấp khi không nhận page, cần quyền hoặc rủi ro mất dữ liệu.
- [ ] Có kế hoạch đối soát order/payment/event khi HTTP phục hồi nhưng kết quả nghiệp vụ chưa rõ.
- [ ] Monitoring bổ sung đủ traffic, latency, error rate, traces, deployment diff và backlog.
- [ ] Alert noise được đo; page không actionable được đưa vào cải tiến.
- [ ] Tài liệu không chứa credentials, PII hoặc thông tin bí mật.
- [ ] Các biến động như rollout/config/secret rotation có thể truy vết.
- [ ] Có quy trình handoff ca trực và lưu incident timeline.
- [ ] Postmortem có action owner, deadline và verification condition.
- [ ] Game day diễn tập cả ứng phó và escalation, không chỉ test kỹ thuật.
- [ ] Runbook được version/review và kiểm tra link/commands sau các thay đổi.
- [ ] Có cách đóng incident theo SLO và business correctness, không chỉ alert hết đỏ.

## 36. Câu hỏi thường gặp

**Runbook có cần ghi tất cả command sửa lỗi không?**

Không. Runbook phải có đủ bước phát hiện, kiểm tra an toàn, cây quyết định, guardrail và escalation. Các thao tác nguy hiểm có thể trỏ đến quy trình riêng được kiểm soát. Một danh sách command không có phạm vi và rollback dễ gây hại hơn thiếu command.

**Một dịch vụ có hai team cùng sở hữu được không?**

Có thể cùng phát triển hoặc hỗ trợ, nhưng trách nhiệm production và lịch on-call cần một accountable owner rõ. Đối với sự cố nhiều service, IC chịu trách nhiệm điều phối toàn sự cố; action owners là những người thực hiện ở từng nhóm.

**Khi alert đã chuyển xanh, có thể đóng incident ngay không?**

Chỉ khi tiêu chí phục hồi đã đạt. Nếu còn queue backlog, payment outcome chưa rõ, dữ liệu sai hoặc có traffic thấp che lỗi, cần tiếp tục monitoring và reconciliation. Đặt observation window theo policy.

**Có nên page khi CPU > 80%?**

Không mặc định. CPU cao có thể bình thường theo thiết kế, còn p99 và success SLO mới phản ánh tác động. CPU/capacity signal có ích để triage hoặc cảnh báo dự báo, nhưng cần phân biệt ticket và urgent page.

**MTTR thấp có đồng nghĩa chất lượng vận hành tốt?**

Không nếu một incident bị đóng sớm khi dữ liệu chưa đối soát hoặc cứ tái diễn. Cần xem SLO, user impact, thời gian giảm tác động, recurring incidents, action completion và page fatigue.

**Team phát triển có phải trực 24/7 không?**

Phụ thuộc tổ chức, thỏa thuận lao động, giờ cung cấp dịch vụ và mức độ rủi ro. Dù dùng SRE tập trung, product on-call hay outsourced operations, phải có coverage và escalation thực, người có đủ quyền và runbook mới.

**Cần làm gì khi không biết root cause?**

Vẫn có thể tuyên bố incident và giảm tác động bằng biện pháp an toàn. Ghi fact/hypothesis, kiểm tra release diff, chia nhánh điều tra, escalation sớm, chọn action có thể xác minh và rollback. Không giả định phải biết nguyên nhân hoàn toàn mới được bảo vệ người dùng.

**Nếu rollout mới trùng lúc outage, cứ rollback ngay là tốt nhất?**

Không phải lúc nào cũng an toàn. App cũ có thể không tương thích DB migration/event schema/secret mới; cần xác minh rollback candidate và blast radius. Đôi khi feature flag hoặc forward fix an toàn hơn.

**Runbook có cần kiểm thử?**

Có. Có thể review định kỳ, game day, test link/permission và diễn tập một số failure mode. Runbook chỉ tồn tại dưới dạng Markdown mà không ai thực hiện thường lỗi thời đúng lúc cần nhất.

**Cảnh báo Payment chậm nên gửi Order on-call hay Payment on-call?**

Tín hiệu service kỹ thuật gửi tới Payment owner; user-journey checkout SLO cần incident coordinator/owner của checkout biết và chủ động phối hợp. Quy ước routing nên được khai báo rõ để không có alert bị thất lạc giữa các team.

**Postmortem cần tập trung vào cá nhân nào đã thao tác sai?**

Nên tập trung vào điều kiện hệ thống/quy trình khiến hành động đó xảy ra hoặc không được bảo vệ: quyền, giao diện, runbook, monitoring, kiểm thử và safeguard. Mục tiêu là giảm xác suất/tác động sự cố lặp lại, chứ không dựa vào kết quả để phán xét người xử lý trong hoàn cảnh thiếu thông tin.

---

**Nguyên lý ghi nhớ:** *Một dịch vụ production chỉ thực sự vận hành được khi có SLO đáng tin cậy, cảnh báo dẫn tới hành động, người trực và người chịu trách nhiệm xác định, runbook an toàn có thể làm theo, escalation rõ ràng, cách kiểm chứng phục hồi và cơ chế học từ sự cố. Monitoring cho thấy điều bất thường; ownership và runbook biến tín hiệu đó thành hành động bảo vệ người dùng.*