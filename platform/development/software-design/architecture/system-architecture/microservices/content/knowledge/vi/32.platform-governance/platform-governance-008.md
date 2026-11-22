# Ghi nhận quyết định kiến trúc và quản lý ngoại lệ trong microservices

## 1. Vì sao cần lưu quyết định, không chỉ lưu mã nguồn?

Trong một hệ thống microservices, nhiều lựa chọn quan trọng không thể hiểu đầy đủ chỉ bằng việc đọc code: tại sao Order Service sở hữu bảng đơn hàng, vì sao giao tiếp với Payment dùng sự kiện thay vì HTTP đồng bộ, vì sao phải dùng transactional outbox, tại sao API công khai yêu cầu mTLS hoặc vì sao một hệ cũ tạm được phép dùng phiên bản TLS chưa đạt chuẩn nội bộ.

Nếu những lý do đó chỉ nằm trong cuộc họp, tin nhắn riêng hoặc trí nhớ của một kiến trúc sư, tổ chức sẽ gặp rủi ro khi:
- Thành viên chuyển nhóm, nghỉ việc hoặc không có mặt trong incident.
- Một service được refactor và nhóm mới vô tình lặp lại lựa chọn đã bị bác bỏ.
- Có nhiều nhóm triển khai cùng một nhu cầu nhưng đưa ra những cách xử lý thiếu nhất quán.
- Các chuẩn bảo mật/khả năng phục hồi được nêu trên wiki nhưng không thể biết service nào tuân thủ.
- Một ngoại lệ được chấp nhận tạm thời biến thành thiết kế mặc định không có thời hạn.
- Hệ thống gặp outage nhưng không ai tìm được giả định ban đầu của quyết định routing, retry, cache hoặc data ownership.
- Audit/compliance yêu cầu chứng minh ai đã chấp nhận rủi ro, dựa trên bằng chứng gì và khi nào cần xem xét lại.

**Architecture Decision Record (ADR)** ghi lại một quyết định kiến trúc có ý nghĩa, bối cảnh, lựa chọn, lý do và hệ quả. **Exception/waiver** ghi lại một trường hợp không tuân thủ quy tắc hoặc chuẩn đang có hiệu lực, cùng đánh giá rủi ro, biện pháp bù trừ, người chịu trách nhiệm và thời hạn kết thúc.

Hai loại hồ sơ có liên quan nhưng **không thay thế nhau**. Một ADR có thể chọn một phương án hợp lý trong nhiều phương án đều được phép; một ngoại lệ là sự lệch khỏi một yêu cầu chuẩn cần được quản trị riêng.

### Mục tiêu học tập

Sau bài này, bạn có thể:
1. Phân biệt ADR, RFC, thiết kế chi tiết, tiêu chuẩn, chính sách và exception record.
2. Viết một ADR ngắn gọn nhưng có đủ bối cảnh, tradeoff và hệ quả.
3. Tổ chức vòng đời của quyết định: Proposed → Accepted → Superseded/Deprecated.
4. Thiết kế cơ chế xin ngoại lệ theo rủi ro, thời hạn, bằng chứng và trách nhiệm.
5. Tránh biến Architecture Review Board thành nút thắt cho mọi thay đổi.
6. Liên kết ADR/ngoại lệ với service catalog, code, pull request, pipeline và incident.
7. Dùng policy-as-code và kiểm tra tự động để thực thi chuẩn mà không cần phê duyệt thủ công mọi lần.
8. Phân biệt quyết định độc lập của service team với quyết định ảnh hưởng nhiều bounded contexts.
9. Đo chất lượng governance bằng rủi ro, độ rõ của ownership và khả năng thay đổi an toàn.
10. Áp dụng cách quản trị này trong tổ chức nhiều nhóm phát triển microservices.

## 2. Năm loại tài liệu thường bị nhầm lẫn

| Loại | Câu hỏi chính | Khi cần | Điều không nên làm |
| --- | --- | --- | --- |
| **ADR** | Vì sao chọn thiết kế này và chấp nhận tradeoff gì? | Quyết định có ảnh hưởng lâu dài, khó đảo ngược hoặc tác động nhiều bên | Viết như danh sách task đang triển khai |
| **RFC / design proposal** | Đề xuất, so sánh và lấy ý kiến trước khi quyết định thế nào? | Chưa thống nhất phương án, cần phản biện/thiết kế chi tiết | Coi bản nháp là chính sách đã phê duyệt |
| **Architecture standard** | Điều gì nên hoặc bắt buộc phải thực hiện nhất quán? | Quy tắc chung cho nhiều team/service | Làm mơ hồ giữa “MUST” và “RECOMMENDED” |
| **Exception / waiver** | Tại sao một đối tượng được phép tạm lệch chuẩn, với rủi ro và giới hạn nào? | Có yêu cầu hiện hành nhưng service chưa thể đáp ứng | Phê duyệt vĩnh viễn hoặc không có owner |
| **Runbook / operational procedure** | Khi vận hành hoặc gặp lỗi phải làm gì, theo thứ tự nào? | Deploy, rollback, incident, DR, migration | Thay thế lý do thiết kế bằng một chuỗi lệnh |

Những artifact khác có thể bổ sung:
- **Architecture diagram:** hình dung cấu trúc, luồng dữ liệu và boundaries.
- **API contract:** mô tả hành vi cụ thể giữa provider và consumer.
- **Threat model:** chỉ ra assets, trust boundaries, threat scenarios và controls.
- **Service catalog:** ánh xạ owner, repository, dependencies, SLO và tài liệu.
- **Risk register:** theo dõi rủi ro tổ chức và phương án xử lý ở cấp danh mục.
- **Change request:** triển khai một thay đổi cụ thể, có thời điểm và rollback.
- **Postmortem:** ghi nhận incident và bài học, có thể kích hoạt ADR mới.

Một ADR tốt có thể liên kết tới RFC, threat model và PR nhưng không chép lại toàn bộ những tài liệu đó. Exception record phải dẫn chiếu **chuẩn bị vi phạm** và bản ADR liên quan nếu có.

## 3. ADR là bản ghi một quyết định có ý nghĩa

Một ADR thông thường trả lời:

1. **Bối cảnh (Context):** vấn đề và các ràng buộc thực tế là gì?
2. **Động lực (Drivers):** mục tiêu, non-functional requirements và giả định nào quan trọng?
3. **Các lựa chọn (Options):** có những phương án khả thi nào?
4. **Quyết định (Decision):** chọn phương án nào, áp dụng trong phạm vi nào?
5. **Lý do (Rationale):** vì sao lựa chọn đó phù hợp hơn trong bối cảnh hiện tại?
6. **Hệ quả (Consequences):** lợi ích, chi phí, rủi ro, nợ kỹ thuật và yêu cầu vận hành?
7. **Trạng thái (Status):** đang đề xuất, đã chấp nhận hay đã bị thay thế?
8. **Ownership và evidence:** ai quyết, ai phải được tham vấn, những tài liệu/test nào hỗ trợ?
9. **Điều kiện xem lại (Review triggers):** giả định hoặc ngưỡng nào khiến quyết định không còn hợp lý?

ADR không cần dài. Một ADR dài 1–3 trang có lập luận rõ thường hữu ích hơn tài liệu 40 trang chỉ mô tả công nghệ. Với quyết định phức tạp, đặt thiết kế/thử nghiệm ở tài liệu liên kết để ADR vẫn dễ đọc.

### Điều gì đáng tạo ADR?

Ví dụ có khả năng đáng ghi:
- Chọn mô hình quyền sở hữu dữ liệu giữa Orders và Payments.
- Chọn asynchronous event thay cho synchronous call cho một workflow.
- Quy tắc partition key/order và tính tương thích của event schema.
- Quyết định dùng Saga thay vì distributed transaction.
- Cách xác thực workload identity và truyền user context.
- Chọn consistency model và SLO cho dữ liệu dẫn xuất.
- Chọn regional failover topology và RPO/RTO tradeoff.
- Quyết định tách một bounded context thành service riêng.
- Chuẩn versioning/deprecation của public API.

Không cần ADR cho mọi biến, refactor không thay đổi boundary, lựa chọn tên class hoặc mọi bản cập nhật package nhỏ nếu chúng không tạo quyết định kiến trúc đáng kể.

**Tiêu chí thực dụng:** nếu một người mới sau sáu tháng có khả năng hỏi “tại sao hệ thống làm cách này và bỏ qua phương án kia?”, đó có thể là một ADR phù hợp.

## 4. Quyết định đã chấp nhận không có nghĩa bất biến

Một quyết định thường là tốt nhất **trong bối cảnh nhất định**, không phải chân lý vĩnh viễn.

Ví dụ năm đầu, hệ thống dùng PostgreSQL làm read model cho tìm kiếm vì lưu lượng nhỏ, yêu cầu query đơn giản và team có kỹ năng SQL. Hai năm sau, lượng sản phẩm tăng, full-text ranking và fuzzy search trở thành yêu cầu chính, tổ chức có thể chuyển sang OpenSearch.

ADR cũ vẫn có giá trị:
- Cho thấy tại sao ban đầu không dùng search engine riêng.
- Ghi những giả định và chi phí vận hành được cân nhắc.
- Giúp hiểu thay đổi nào khiến quyết định cũ không còn phù hợp.
- Phục vụ incident/review lịch sử trong giai đoạn triển khai cũ.

Hướng xử lý đúng là tạo **ADR mới thay thế (supersede)**, liên kết hai chiều. Không sửa âm thầm nội dung ADR cũ để khiến lịch sử trông như chưa từng có quyết định khác.

### Vòng đời điển hình

```text
Draft / Proposed
      |
      | discussion, evidence, owners
      v
   Accepted
      |
      +------> Implemented / In force
      |
      +------> Superseded by new ADR
      |
      +------> Deprecated / Retired
      |
      +------> Rejected (chỉ với proposal chưa được chấp nhận)
```

Không có một bộ status bắt buộc cho mọi tổ chức; điều quan trọng là nghĩa của từng status và cách tìm **quyết định có hiệu lực hiện tại** phải rõ ràng.

## 5. Mẫu ADR bằng Markdown

Một mẫu ngắn gọn có thể được lưu cùng repository hoặc trong kho kiến trúc trung tâm:

```markdown
# ADR-0042 — Transactional outbox cho Order events

Status: Accepted
Date: 2026-11-12
Owners: Order Lifecycle Team
Decision makers: Order Tech Lead, Platform Reliability
Scope: Orders DB -> orders.events
Related: RFC-018, EVENT-CONTRACT-007, runbook/order-outbox
Supersedes: None
Review trigger: thay nguồn DB hoặc RPO/SLO event delivery

## Context

Order Service hiện ghi database và publish Kafka theo hai
bước riêng. Khi database commit thành công nhưng publish
thất bại, các consumer có thể không bao giờ nhận được event.

## Decision drivers

- Không để mất intent phát event sau business commit.
- Không yêu cầu distributed transaction giữa DB và broker.
- Consumer chấp nhận at-least-once và xử lý idempotent.
- Có thể quan sát backlog, replay và phục hồi sau DR.

## Options considered

1. Dual write DB rồi Kafka — đơn giản nhưng có cửa sổ mất event.
2. Transactional outbox + CDC/relay — thêm hạ tầng và backlog.
3. Distributed transaction — complexity/operability không phù hợp.

## Decision

Ghi business rows và outbox rows trong cùng DB transaction.
Relay phát outbox events tới Kafka; mỗi event có eventId và
aggregateVersion. Consumer phải idempotent.

## Consequences

Positive:
- Business commit và event intent không bị tách rời.
- Có thể retry/replay event một cách có kiểm soát.

Negative:
- Thêm outbox tables, relay, metrics và cleanup.
- Có thể publish trùng nếu relay crash giữa publish/checkpoint.

## Validation

- Test crash sau DB commit, trước publish.
- Test relay publish trùng và consumer idempotency.
- Metric: outbox oldest age, publish failures, DLQ.

## Review

Xem lại khi thay broker, đổi transaction boundary
hoặc outbox backlog vượt mục tiêu SLO.
```

Các ngày, ID, tên team và mã liên kết là **ví dụ minh họa**, không có nghĩa đã tồn tại trong một tổ chức cụ thể. Với ứng dụng thực, yêu cầu thêm owner thật, approval evidence và vị trí tài liệu có thể truy cập.

## 6. Ghi “vì sao không chọn” quan trọng không kém “đã chọn”

Một quyết định kỹ thuật hữu ích phải nêu **options considered** và tradeoff. Nếu chỉ ghi “dùng Kafka vì Kafka tốt”, người sau không biết các giới hạn hoặc phương án thay thế.

Ví dụ chọn cách đồng bộ giữa Orders và Payments:

| Phương án | Ưu điểm | Chi phí/rủi ro |
| --- | --- | --- |
| HTTP đồng bộ trong request checkout | Dễ nhận kết quả tức thời, flow đơn giản hơn | Tăng phụ thuộc availability/latency, timeout unknown |
| Event-driven với saga | Có thể giảm coupling thời gian và lưu pending state | Eventual consistency, dedup, reconciliation phức tạp |
| Shared database trực tiếp | Bớt API ở ngắn hạn | Phá data ownership, schema coupling, khó deploy độc lập |
| Distributed transaction | Có thể hứa atomicity trong phạm vi supported | Coordination, latency, failure handling và support có thể không phù hợp |

Bối cảnh mới quyết định phương án:
- Nếu người dùng phải biết authorization thành công ngay, synchronous call có thể hợp lý.
- Nếu tác vụ có thể chờ vài phút và bắt buộc chịu được provider outage, saga/event-driven có thể phù hợp.
- Nếu dữ liệu thuộc cùng transaction invariant, có thể cần xem lại microservice boundary thay vì dựng transaction xuyên nhiều service.

ADR nên nêu rõ điều kiện lựa chọn, không biến khẩu hiệu kiến trúc thành luật tuyệt đối.

## 7. Tách facts, assumptions và preferences

Nhiều ADR kém chất lượng vì trộn ba loại thông tin:

**Fact đã được đo:** “p99 latency qua payment gateway ở peak là 900 ms trong tuần thử nghiệm”.

**Assumption chưa được chứng minh:** “traffic có thể tăng ba lần trong hai năm”.

**Preference:** “team thích Spring Boot vì đã có kinh nghiệm”.

Ba loại đều có thể tham gia quyết định, nhưng phải được gắn nhãn rõ.

Một bảng drivers:

| Driver | Loại bằng chứng | Phương pháp xác minh |
| --- | --- | --- |
| RPO event intent không quá 1 phút | SLO/requirement | DR drill, outbox age |
| Peak traffic ~2.000 messages/giây | Historical observation | Broker metrics, load test |
| Tăng trưởng gấp ba sau 18 tháng | Assumption | Theo dõi product forecast hàng quý |
| Cần deploy Orders độc lập | Architectural requirement | Mixed-version contract tests |
| Không muốn vận hành thêm DB | Cost/preference | Platform capacity review |

**Review trigger** nên bám vào những assumption quan trọng. Nếu giả định tăng trưởng hoặc chi phí vận hành thay đổi, ADR cần được xem lại thay vì tiếp tục theo một lựa chọn không còn hợp bối cảnh.

## 8. Phạm vi ra quyết định và quyền tự chủ của team

Không phải ADR nào cũng cần một hội đồng kiến trúc công ty duyệt.

Có thể chia theo cấp:

| Cấp | Ví dụ | Owner quyết định | Người cần tham vấn |
| --- | --- | --- | --- |
| **Local/team** | Cấu trúc module nội bộ, cache trong service, retry nội bộ trong policy | Team sở hữu service | Reviewer nội bộ |
| **Domain/context** | API/event contract, database model, transaction invariant | Bounded-context owner | Consumer/producer liên quan |
| **Cross-team/platform** | Chuẩn telemetry, workload identity, API gateway, schema registry | Platform/domain architecture owners | Stream teams chịu tác động |
| **Organization-wide/high risk** | Data residency, encryption baseline, public trust boundary, regional DR strategy | Authorized architecture/security/risk decision makers | Security, compliance, SRE, business owners |

Đây là mô hình delegation tham khảo. Quyền cụ thể cần được tổ chức quy định rõ. Phân quyền nên dựa vào **blast radius, yêu cầu pháp lý và số team chịu ảnh hưởng**, không dựa vào cấp bậc danh xưng của tác giả.

Một thay đổi nội bộ không ảnh hưởng contract có thể được chấp nhận trong PR bình thường. Một thay đổi làm giảm mức bảo vệ dữ liệu khách hàng cần review của người có thẩm quyền cho rủi ro đó, dù code thay đổi chỉ một dòng.

## 9. Architecture governance không đồng nghĩa kiểm soát tập trung mọi quyết định

Có hai cực đoan cần tránh:

**Không quản trị:**
- Mỗi team tự chọn cơ chế authentication, event versioning và secret storage.
- Tương thích API không được kiểm soát.
- Không có người chịu trách nhiệm với shared failure domains.
- Khi audit chỉ có cuộc trò chuyện không thể truy xuất.

**Quản trị quá nặng:**
- Mọi PR đều phải qua một architecture board.
- Mất nhiều tuần phê duyệt một thay đổi nhỏ.
- Quy tắc không rõ nên người làm phải hỏi lại liên tục.
- Hội đồng trở thành owner mặc định của mọi incident dù không vận hành service.

Mô hình cân bằng:
1. Quy định một tập **principles/standards** có nghĩa rõ.
2. Delegation quyết định nội bộ cho team owner.
3. Đưa guardrail có thể tự động hóa vào CI/CD và service templates.
4. Chỉ yêu cầu review sâu với thay đổi cross-boundary/risk cao.
5. Ghi ADR với các quyết định có khả năng ảnh hưởng lâu dài.
6. Có exception workflow minh bạch và hết hạn.
7. Đo thời gian quyết định, số ngoại lệ quá hạn và chất lượng kiểm soát.
8. Xem lại chuẩn khi rủi ro hoặc nhu cầu tổ chức thay đổi.

Tổ chức nên hỏi **“làm sao kiểm soát rủi ro mà vẫn giúp team đưa giá trị ra production?”**, không chỉ hỏi “ai có quyền ký duyệt?”.

## 10. Phân biệt nguyên tắc, chuẩn, hướng dẫn và kiểm soát

Một taxonomy giúp giảm tranh cãi:

| Loại | Ví dụ | Tính bắt buộc |
| --- | --- | --- |
| **Principle** | Service sở hữu dữ liệu của mình | Định hướng thiết kế; vi phạm cần giải thích |
| **Standard** | API public phải có versioning và auth theo baseline | Có thể bắt buộc theo phạm vi/hiệu lực |
| **Guideline** | Ưu tiên async cho tác vụ không cần kết quả tức thời | Khuyến nghị; dùng phương án khác có lý do có thể hợp lệ |
| **Control** | CI chặn image có secret hardcoded hoặc quyền vượt baseline | Cơ chế thực thi/đo compliance |
| **Reference architecture** | Mẫu Spring Boot service có tracing, health, pipeline | Mẫu hỗ trợ, không mặc nhiên phù hợp mọi use case |
| **Exception** | Một service được tạm miễn control X tới ngày Y với biện pháp bù trừ | Giới hạn, được duyệt và phải theo dõi |

Trước khi xin ngoại lệ, phải biết đang lệch khỏi **điều gì**. Nếu tài liệu chỉ viết “ưu tiên event-driven” mà không có điều kiện bắt buộc, team chọn HTTP có thể cần ADR nhưng không nhất thiết cần exception.

**Không biến guideline thành policy bằng cách bất ngờ chặn CI.** Mỗi yêu cầu phải có version, phạm vi áp dụng, ngày hiệu lực, owner và cách giải thích.

## 11. Registry quyết định và tiêu chuẩn

Một kho có thể tổ chức:

```text
architecture/
  README.md
  principles/
    data-ownership.md
    failure-isolation.md
  standards/
    SEC-001-workload-identity.md
    API-004-versioning.md
    OBS-003-trace-context.md
    REL-006-timeouts-and-retries.md
  decisions/
    ADR-0001-database-per-context.md
    ADR-0042-order-transactional-outbox.md
    ADR-0043-payment-state-machine.md
  exceptions/
    EXC-0031-legacy-order-auth-migration.md
  templates/
    adr-template.md
    exception-template.md
  catalog/
    service-ownership.md
```

Có thể đặt ADR ngay trong repository service để gần code, hoặc registry trung tâm để dễ tìm toàn công ty. Nếu chọn mô hình phân tán, nên có **index tìm kiếm** với ID, status, owner, link tới chuẩn và service. Nếu chọn mô hình trung tâm, đừng tạo rào cản cho team đóng góp.

Yêu cầu tối thiểu cho một registry:
- ID ổn định, không tái sử dụng.
- Title, status, owner, scope và ngày.
- Link tới documents/PR/service catalog liên quan.
- Tìm theo service, domain, team, standard ID và decision type.
- Có lịch sử thay đổi/version control.
- Phân quyền đọc phù hợp với thông tin nhạy cảm.
- Dễ nhận biết “đang áp dụng” và “đã được thay thế”.
- Có review triggers và exception expiry tracking.

Không nên xóa ADR bị supersede để “dọn sạch”; lịch sử ra quyết định thường cần thiết cho audit, rollback và học từ sự cố.

## 12. ADR nên nằm ở đâu trong Git workflow?

Một cách áp dụng là **Docs-as-Code**:
- Tạo file Markdown trong repository của team hoặc shared architecture registry.
- Dùng pull request để lấy phản hồi từ stakeholder cần thiết.
- Review tập trung vào logic và tradeoff, không chỉ chính tả.
- Merge khi có decision authority phù hợp và mọi điều kiện chấp nhận được ghi rõ.
- Gắn link ADR trong PR triển khai và service catalog.
- Dùng version control làm lịch sử quyết định, không sửa âm thầm ADR accepted.

Một PR có thể chứa:
- `docs/adr/0042-transactional-outbox.md`.
- Đo benchmark hoặc threat model liên quan.
- Link RFC và danh sách consumer bị ảnh hưởng.
- CI check metadata ADR (ID, status, owner, link).
- Link issue follow-up và deployment plan.

**ADR merge không tự chứng minh quyết định đã triển khai.** Nên có trạng thái “accepted” tách với adoption/implementation status và liên kết các PR hiện thực, tests và dashboard.

Trong các lĩnh vực cần phê duyệt chính thức, review Git có thể là một phần bằng chứng nhưng không mặc nhiên thay thế quy trình phê duyệt có chữ ký/ủy quyền riêng.

## 13. Ví dụ ADR đầy đủ: chuẩn giao tiếp giữa Checkout và Payment

Một bài toán thực tế:
- Checkout cần xác nhận thanh toán nhưng Payment provider có lúc timeout.
- Synchronous call có latency tốt cho happy path.
- Dữ liệu payment phải tránh double capture.
- Trạng thái không xác định có thể cần reconciliation.
- Team muốn deploy mỗi service độc lập.

Ba lựa chọn:
1. Synchronous HTTP với idempotency và trạng thái pending khi timeout.
2. Asynchronous orchestration với queue và workflow state.
3. Shared DB transaction giữa Checkout và Payments.

Giả sử nhóm chọn phương án 1 cho authorization theo request path, đồng thời đưa kết quả không chắc chắn vào state machine và reconciliation bất đồng bộ.

Ví dụ ADR:

```markdown
# ADR-0073 — Payment authorization từ Checkout

Status: Accepted
Date: 2026-11-12
Scope: Checkout -> Payment Authorization API
Owners: Checkout Team, Payments Team
Approvers: Domain owners cho mỗi bên
Review trigger: p99 authorization > 2s hoặc provider outage tăng

## Context
Checkout cần trả kết quả nhanh khi authorization thành công,
nhưng network timeout không cho biết provider đã xử lý hay chưa.

## Drivers
- Không charge trùng khi retry.
- Có kết quả hợp đồng rõ: AUTHORIZED/DECLINED/PENDING.
- Thời gian người dùng chờ có deadline.
- Các service được deploy độc lập.

## Options
1. Sync HTTP + stable operationId + reconciliation.
2. Event-driven async authorization.
3. Shared DB transaction.

## Decision
Dùng HTTP trong thời hạn request budget; gửi operationId
bất biến. Nếu timeout/unknown, Checkout ghi PENDING và
reconcile theo provider operation identity; không tự charge lại.

## Consequences
- Happy path phản hồi nhanh.
- Cần idempotency, pending UX và reconciliation worker.
- Availability của authorization chịu ảnh hưởng provider.
- Không được retry vô hạn hoặc sinh operationId mới.

## Evidence
Contract tests cho AUTHORIZED/DECLINED/PENDING;
fault-injection test timeout-after-provider-success;
runbook đối soát và traceId.

## Rollout
Provider contract first; consumer handles new state;
canary; observe unknown-operation count; remove legacy path.

## Review
Đánh giá lại nếu p99, traffic hay requirement thay đổi.
```

ADR này ghi **sự lựa chọn và điều kiện**, không cố biến thành full API specification hoặc runbook chi tiết. Các bước triển khai và schema/event examples nên được liên kết tới tài liệu có owner riêng.

## 14. Khi nào phải tạo exception thay vì ADR?

Giả sử chuẩn công ty quy định:
> Mọi public API phải dùng mTLS hoặc workload identity tương đương theo SEC-001 từ ngày hiệu lực.

Một hệ thống legacy do đối tác quản lý chỉ hỗ trợ TLS server authentication, chưa thể bật client cert trong 60 ngày. Team có thể có lý do kỹ thuật hợp lệ nhưng vẫn **không đáp ứng chuẩn**.

Trong trường hợp này:
- ADR có thể ghi kiến trúc tích hợp với đối tác và phương án lâu dài.
- Exception record ghi phạm vi chưa đạt SEC-001, đánh giá rủi ro, controls bù trừ, thời hạn và người chấp nhận.
- Release pipeline/service catalog biết ngoại lệ được duyệt cho endpoint nào, tới bao giờ.
- Có kế hoạch chuyển đổi, evidence và cảnh báo trước ngày hết hạn.

**Không tạo ADR “chúng ta quyết định không dùng mTLS” để né exception workflow**. Khi có quy tắc bắt buộc, lựa chọn lệch chuẩn phải được chấp thuận bởi đúng risk owner.

Ngược lại, việc chọn HTTP hay gRPC khi chuẩn không cấm một trong hai có thể chỉ cần ADR; tạo exception cho mọi khác biệt sẽ biến governance thành bureaucracy.

## 15. Định nghĩa exception chính xác

Một exception nên được hiểu là:

> Sự chấp thuận **có giới hạn** cho một đối tượng và hành vi cụ thể không đáp ứng một yêu cầu hiện hành, dựa trên đánh giá rủi ro được ghi nhận, biện pháp kiểm soát bù trừ và kế hoạch kết thúc/xem xét lại.

Các thành phần bắt buộc theo mô hình khuyến nghị:
- **Exception ID:** ví dụ EXC-0031.
- **Standard/control ID và version:** lệch khỏi yêu cầu nào.
- **Object scope:** service, repository, environment, endpoint, region, tenant, dữ liệu.
- **Current noncompliance:** hành vi hiện tại và lý do.
- **Business justification:** tại sao chưa thể tuân thủ ngay.
- **Risk analysis:** xác suất/tác động, assets bị ảnh hưởng, threat scenarios.
- **Compensating controls:** biện pháp giảm rủi ro có thể xác minh.
- **Owner/accountable person:** người chịu trách nhiệm xử lý.
- **Risk approver:** người có thẩm quyền chấp nhận residual risk.
- **Start date, expiry date, review date:** có hiệu lực trong bao lâu.
- **Remediation plan:** milestones, owner, tickets, bằng chứng đạt chuẩn.
- **Monitoring/kill switch:** cách phát hiện thay đổi rủi ro, điều kiện rút phép.
- **Evidence links:** test, scan, diagram, threat model, approval record.
- **Status:** Requested/Approved/Expired/Closed/Revoked hoặc bộ trạng thái tương đương.

Một ngoại lệ “Service A được miễn security checks” là **quá rộng**. Ngoại lệ phải định danh control cụ thể và phạm vi nhỏ nhất có thể.

## 16. Mẫu exception record

```yaml
exception_id: EXC-0031
title: "Legacy partner endpoint chưa hỗ trợ mTLS"
status: approved
standard:
  id: SEC-001
  version: "2.3"
  requirement: "Mutual workload authentication"
scope:
  service: shipping-adapter
  environment: production
  endpoint: "partner-shipping.example/internal/callback"
  data_classification: restricted
  region: "ap-southeast-example"
requested_by: shipping-platform-owner
accountable_owner: shipping-team-lead
risk_approver: delegated-security-risk-owner
start_date: "2026-11-12"
review_date: "2026-12-01"
expires_at: "2027-01-12"
justification: >
  Partner cần lộ trình nâng endpoint và cấp client certificates;
  đổi ngay sẽ làm gián đoạn luồng xác nhận giao hàng.
risk:
  scenarios:
    - "Endpoint impersonation under compromised network path"
  inherent_level: high
  residual_level: medium
compensating_controls:
  - "IP allowlist + private egress route theo điều kiện hạ tầng"
  - "OAuth audience-bound credentials with short lifetime"
  - "Strict request signing and replay protection"
  - "Dedicated audit and anomaly alerting"
remediation:
  target: "Chuyển sang mTLS per SEC-001"
  milestones:
    - "Sandbox certificate onboarding"
    - "Staging integration test"
    - "Canary production switch"
    - "Remove exception policy"
  tracking_issue: "SEC-MIGRATION-EXAMPLE"
evidence:
  threat_model: "link-to-approved-model"
  control_test: "link-to-control-verification"
  approval: "link-to-approval-record"
```

Đây là **dữ liệu minh họa**, không phải yêu cầu schema phổ quát. Các hostname, dates, IDs và approvals trong ví dụ không đại diện cho đối tượng thật. Những compensating controls phải được Security đánh giá dựa trên threat model; IP allowlist hoặc request signing **không tự bảo đảm** mức an toàn tương đương mTLS trong mọi threat scenario.

Một exception chỉ được xem là **đang có hiệu lực** khi status, ngày hiệu lực, scope và approval đáp ứng đúng chính sách. Không coi file YAML tồn tại là đủ để CI cho qua tất cả controls.

## 17. Exception khác risk acceptance vĩnh viễn

Một số rủi ro có thể được doanh nghiệp chấp nhận lâu dài; nhưng điều đó không có nghĩa nên gọi mọi quyết định chấp nhận rủi ro là “ngoại lệ tạm thời”.

Phân biệt:
- **Temporary exception:** chưa đạt chuẩn có hiệu lực, có remediation và expiry.
- **Risk acceptance:** cơ quan có thẩm quyền chấp nhận residual risk theo quy trình doanh nghiệp; có thể có chu kỳ review.
- **Policy change:** tổ chức thay chuẩn vì yêu cầu cũ không còn hợp lý, với assessment và version mới.
- **Waiver for legacy end-of-life:** phạm vi bị giới hạn cho hệ sắp bỏ, có lộ trình đóng thực tế.
- **Emergency exception:** phê duyệt thời hạn ngắn trong incident hoặc security patch, với hậu kiểm.
- **False positive suppression:** một công cụ báo sai; cần evidence chứng minh không vi phạm, không nhất thiết là exception thực.

Nếu một số lượng lớn service liên tục xin cùng ngoại lệ, có hai khả năng:
1. Nhiều team đang gặp cùng một rào cản kỹ thuật và cần platform hỗ trợ.
2. Chuẩn hiện tại không còn phù hợp hoặc không có phương án thực thi khả thi.

Trong cả hai trường hợp, nên **xem lại cách thiết kế policy**, không chỉ gia hạn hàng loạt exception vô thời hạn.

## 18. Luồng xin và phê duyệt ngoại lệ

Một vòng đời minh họa:

```text
Identify deviation
        |
        v
Create scoped exception request
        |
        v
Security/architecture risk assessment
        |
        +----> Missing evidence -> Request changes
        |
        v
Choose compensating controls + remediation
        |
        v
Authorized risk decision
        |
        +----> Rejected -> comply or change design
        |
        v
Approved with scope and expiration
        |
        v
Implement and verify compensating controls
        |
        v
Continuous monitoring and milestone reviews
        |
        +----> Remediated -> Close
        +----> Conditions violated -> Revoke/escalate
        +----> Expiration approaching -> Reassess
        +----> Expired -> No automatic continuation
```

Đầu vào phải đủ để người duyệt hiểu **rủi ro cụ thể**. Không nên duyệt chỉ dựa vào “deadline business gấp” nếu thiếu blast radius, data classification và controls. Tuy nhiên, workflow cũng không nên kéo dài hàng tuần cho một ngoại lệ nhỏ có rủi ro thấp và mô hình xử lý đã rõ.

### Risk-based routing

| Mức độ | Ví dụ | Dạng review hợp lý |
| --- | --- | --- |
| Thấp | Lệch khuyến nghị không liên quan dữ liệu nhạy cảm | Team owner hoặc automation |
| Trung bình | Tạm không đạt standard observability trên service nội bộ | Platform/architecture owner, có deadline |
| Cao | Thay mô hình auth, encryption, tenant isolation hoặc DR cho dữ liệu nhạy cảm | Security/risk authority và affected business owner |
| Rất cao/không chấp nhận | Thiếu control pháp lý bắt buộc, khả năng lộ dữ liệu nghiêm trọng | Có thể không được phép cấp exception |

Bảng minh họa logic điều phối; tiêu chí phê duyệt thực tế phụ thuộc pháp luật, chính sách và delegation của tổ chức. Một số yêu cầu **không được miễn trừ** ngay cả khi có người chịu trách nhiệm.

## 19. Quyền phê duyệt và separation of duties

Người đề xuất ngoại lệ thường muốn release nhanh. Người đánh giá rủi ro phải đủ độc lập để xem xét tác động, đặc biệt với bảo mật và compliance.

Một ma trận RACI tham khảo:

| Hoạt động | Service team | Platform/Architect | Security/Risk | Product owner | Audit/Compliance |
| --- | --- | --- | --- | --- | --- |
| Viết ADR local | R/A | C | C nếu liên quan | I/C | I khi cần |
| Quyết định cross-service standard | C | R/A | C/A theo control | C | C |
| Xin exception | R | C | C | C | I |
| Phân tích residual risk | R cung cấp bằng chứng | C | R/A theo policy | C | C |
| Chấp nhận exception high-risk | C | C | A theo delegation | C/A nếu yêu cầu | C |
| Thực hiện remediation | R/A | C | V kiểm soát | I | I |
| Theo dõi expiry/evidence | R | R hỗ trợ automation | A cho risk review | I | I/C |

R = Responsible, A = Accountable, C = Consulted, I = Informed. Đây không phải RACI bắt buộc. Trong bảng, một số hoạt động có nhiều bên phê duyệt theo loại rủi ro; tổ chức nên xác định **người accountable cuối cùng** rõ trong từng luồng để tránh mơ hồ.

Một service owner **không nên tự tạo, tự đánh giá và tự chấp nhận ngoại lệ an ninh nghiêm trọng** không có review độc lập khi policy yêu cầu separation of duties.

## 20. Thời hạn và lifecycle của exception

Exception không được để “vô hạn” vì hệ thống có thể dần quên lý do tồn tại.

Cơ chế tối thiểu:
- `requested_at`, `approved_at`, `starts_at`, `expires_at`.
- `review_at` trước expiry đủ lâu để xử lý.
- `last_verified_at` và chứng cứ controls còn hiệu lực.
- `remediation_owner` và milestones.
- Cảnh báo khi gần hết hạn, bị quá hạn hoặc conditions thay đổi.
- Có logic revoke khi rủi ro tăng, không chờ expiry.
- Đóng exception chỉ sau khi kiểm tra compliance, không chỉ sau khi PR merge.
- Gia hạn bằng **assessment mới có dấu vết**, không sửa trực tiếp ngày hết hạn cũ rồi làm mất lịch sử.

Một rule minh họa:
- Cảnh báo trước 30 ngày.
- Escalate trước 7 ngày nếu chưa có remediation evidence.
- Tới ngày hết hạn, gate ngăn release rủi ro trong phạm vi áp dụng theo policy; có cơ chế emergency override đúng thẩm quyền.
- Nếu production đang chạy, expiry không nhất thiết đồng nghĩa tự động tắt service vì có thể tạo outage lớn; cần incident/escalation plan được định nghĩa trước.

Một ngoại lệ đã hết hạn có thể là **noncompliance đang tồn tại** cần quản lý; không nên đánh đồng việc “chưa deploy phiên bản mới” với việc “đã khắc phục rủi ro”.

## 21. Scope ngoại lệ phải đủ hẹp

Một ngoại lệ cần hạn chế bốn chiều:

1. **Đối tượng:** service cụ thể, endpoint, repository hoặc workload identity.
2. **Môi trường:** production/staging/region/cluster.
3. **Hành vi/kiểm soát:** rule nào, trường hợp nào được cho phép.
4. **Thời gian:** từ khi nào, tới khi nào, điều kiện revoke.

Ví dụ tốt:

```text
EXC-0031:
  service = shipping-adapter
  endpoint = /partner/callback
  environment = production
  policy = SEC-001.require-client-mtls
  expires = 2027-01-12
```

Ví dụ xấu:

```text
All shipping projects may bypass transport security
until migration is complete.
```

Mẫu xấu không có ngày cụ thể, phạm vi và cơ chế xác minh. Khi policy-as-code triển khai, scope quá rộng có thể cho phép các endpoint không liên quan vô tình né kiểm soát.

## 22. Policy-as-code và automated guardrails

Những quy tắc rõ ràng có thể được chuyển thành kiểm tra tự động:

- Không deploy image chứa high-risk secret scanning findings.
- Pod cần resource requests/limits theo policy.
- Workload identity phải dùng service account riêng.
- Artifact phải có provenance/signature theo chuẩn áp dụng.
- Public API phải khai báo schema/owner/SLO.
- Database migrations phải qua compatibility tests.
- Không tạo wildcard network access nếu không có phê duyệt phù hợp.
- Deployment cần health probes, log/tracing conventions hoặc policy tương đương.

Pipeline minh họa:

```text
Pull Request
    |
    +--> Lint + unit tests
    +--> Contract verification
    +--> Security scans
    +--> Architecture policy checks
                    |
                    v
          Any policy violation?
                /         \
              No           Yes
              |             |
              v             v
          Continue     Valid scoped exception?
                            /     \
                          Yes      No
                          |         |
                          v         v
                  Verify controls   Block and guide remediation
                  + expiry + risk
                          |
                          v
                   Continue with evidence
```

Không nên chỉ kiểm tra “exception ID có tồn tại”. Gate cần xác minh ID gắn đúng service/control/version/scope, status được duyệt, chưa hết hạn và compensating controls có evidence phù hợp.

Trong Kubernetes có thể dùng admission policies, OPA/Gatekeeper hoặc Kyverno theo năng lực đang triển khai; trong Git có linters/custom checks; trong artifact pipeline có security scanners. Chọn công cụ phù hợp với hệ thực tế, không biến một tên tool thành bảo đảm compliance.

## 23. Một ví dụ policy evaluation minh họa

Pseudocode, không phụ thuộc một engine policy cụ thể:

```text
function allowDeployment(service, target, control):
    if meetsStandard(service, target, control):
        return ALLOW

    exception = approvedExceptions.find(
        serviceId = service.id
        and environment = target.environment
        and controlId = control.id
        and controlVersion = control.version
    )

    if exception is absent:
        return DENY("Missing control and no scoped exception")

    if exception.status != APPROVED:
        return DENY("Exception not approved")

    if now < exception.validFrom or now >= exception.expiresAt:
        return DENY("Exception outside validity window")

    if not exception.scope.matches(target):
        return DENY("Exception does not cover this deployment")

    if not verifyCompensatingControls(exception):
        return DENY("Compensating controls not verified")

    emitAudit(service, control, exception.id, decision = ALLOW)
    return ALLOW
```

Đây là logic khái niệm. Một hệ thực cần xử lý timezones, clock skew, signed approval evidence, cache invalidation, service identity, exception registry availability và fail-safe behavior. “Cho qua khi registry không truy cập được” có thể tạo lỗ hổng; “chặn tất cả khi registry hỏng” có thể tạo outage pipeline. Phải chọn hành vi dựa trên risk model và khả năng vận hành.

**Không để nội dung PR tự khai báo `approved=true` rồi được phép bypass control.** Bằng chứng phê duyệt phải đến từ nguồn có quyền độc lập.

## 24. Quản lý ngoại lệ liên quan bảo mật: không biến waiver thành lỗ hổng

Một số tình huống có thể xuất hiện:
- Legacy service chưa hỗ trợ mTLS.
- Third-party library có vulnerability nhưng chưa có bản vá hoặc việc nâng cấp phá compatibility.
- Service cần egress rộng hơn chuẩn trong giai đoạn migration.
- Cơ chế mã hóa/backup chưa đạt baseline mới.
- Workload không thể xoay secret tự động do provider legacy.

Cần đánh giá:
1. Threat scenario nào đang mở?
2. Dữ liệu hoặc quyền nào có thể bị lộ/lạm dụng?
3. Hệ thống bị ảnh hưởng nằm trong trust boundary nào?
4. Có compensating controls đã được kiểm thử không?
5. Monitoring có phát hiện exploit/violation không?
6. Thời hạn exposure và phương án emergency revoke?
7. Compliance/legal requirement có cho phép exception không?
8. Nếu không thể đáp ứng, có cách đổi kiến trúc hoặc ngừng chức năng không?

Không coi exception như giấy phép bỏ logging, bỏ authentication hoặc dùng credential chung lâu dài. Với controls quan trọng, một số rủi ro **không thể được chấp nhận ở cấp team**.

## 25. Ngoại lệ về reliability và SLO

Không phải exception nào cũng thuộc bảo mật.

Ví dụ chuẩn vận hành yêu cầu:
- Critical service có readiness/liveness health probes.
- SLO và burn-rate alerts.
- Graceful shutdown, retry budget và circuit breaker cho downstream bắt buộc.
- RPO/RTO và DR drill cho dữ liệu quan trọng.
- Immutable artifact và rollback path.

Một service legacy chưa thể có DR test tự động trong vòng một quý có thể xin ngoại lệ nếu:
- Định rõ những business operations và dữ liệu chịu rủi ro.
- Có manual restore runbook đã được thử nghiệm trong sandbox.
- Có thêm backup verification và alert về replication lag.
- Có owner chịu trách nhiệm, milestone tự động hóa và expiry.
- Risk approver chấp nhận residual RPO/RTO impact.

Nếu hệ thống đã tiêu hết error budget, exception về việc bỏ deploy gate cần được đánh giá theo user impact và release policy; không tự cho phép với lý do “đang gấp”.

Một **reliability exception** cũng cần scope, evidence và thời hạn giống security exception. Chỉ có mức review/owner khác tùy chính sách.

## 26. Ngoại lệ về dữ liệu và API contract

Các trường hợp thường gặp:
- Consumer cũ chưa thể nâng schema, provider phải giữ deprecated endpoint lâu hơn chuẩn.
- Legacy integration dùng shared database read-only trong thời gian phân tách.
- Một event topic chưa có schema registry compatibility check.
- Data warehouse cần tiếp tục đọc schema cũ dù đã có model mới.
- Công việc batch dùng manual export vì connector chưa hỗ trợ.

Risk:
- API breaking change, lỗi triển khai lockstep.
- Vi phạm data ownership.
- Quyền dữ liệu rộng hơn cần thiết.
- Event replay không đọc được schema cũ.
- Dữ liệu nhạy cảm bị nhân bản vượt chính sách.
- Drift giữa nguồn và read projection.

Một ngoại lệ nên có migration path như:
```text
Temporary shared DB read
   → add read API/CDC contract
   → migrate consumer
   → verify parity and access
   → revoke direct database grants
   → close exception
```

Không đóng ngoại lệ khi chỉ có code mới, trong khi DB grant cũ vẫn tồn tại. **Evidence thực tế của removal** là điều kiện đóng.

## 27. Quyết định kiến trúc trong incident và emergency change

Trong sự cố nghiêm trọng, đội vận hành có thể phải quyết định nhanh:
- Disable một feature gây lỗi.
- Tạm chuyển traffic sang vùng khác.
- Thay retry limit, circuit breaker hoặc load shedding.
- Tạm cho phép fallback không đầy đủ để giảm user impact.
- Chặn một integration độc hại hoặc không ổn định.

Không hợp lý nếu yêu cầu hội đồng họp 3 ngày trước khi giảm thiểu một incident đang diễn ra. Nhưng cũng không nên để quyết định rủi ro cao biến mất khỏi lịch sử.

Mô hình:
1. Incident commander và người có thẩm quyền ra quyết định khẩn cấp.
2. Ghi action/time/owner/impact trong incident log.
3. Thực hiện mitigation có rollback/expiry khi có thể.
4. Sau incident, tạo ADR hoặc exception record hậu kiểm nếu thay đổi tạo trạng thái kiến trúc/rủi ro kéo dài.
5. Đánh giá residual risk, controls và remediation.
6. Đóng tạm thời hoặc chính thức hóa thiết kế đúng quy trình.

**Emergency exception cần thời hạn ngắn và review sau sự kiện.** Không coi incident kết thúc là lý do giữ một bypass vô thời hạn.

## 28. Liên kết ADR và exception với Service Catalog

Service catalog có thể là nơi tìm nhanh:
- Service owner và on-call.
- Repository, runtime, cluster/region.
- Public API/events và data classification.
- Dependencies và downstream consumers.
- SLO, dashboards và runbooks.
- Active ADRs ảnh hưởng đến service.
- Active exceptions và ngày hết hạn.
- Standards/control coverage và evidence.
- Các PR/migrations đang thay đổi boundary.

Ví dụ record:

```yaml
service: orders
owner: order-lifecycle-team
tier: critical
data_classification: restricted
repository: "git.example/org/orders"
adrs:
  - ADR-0042
  - ADR-0073
exceptions:
  - id: EXC-0031
    note: "chỉ ví dụ; xác minh scope trước khi gắn"
standards:
  - API-004@2.1
  - OBS-003@1.4
  - SEC-001@2.3
links:
  dashboard: "service-observability-link"
  runbook: "service-incident-runbook-link"
```

Các trường và đường dẫn minh họa, không phải dữ liệu doanh nghiệp thật. Quan trọng là developer không cần biết tên một kiến trúc sư để tìm quyết định. Metadata nên được cập nhật bằng CI/catalog automation khi có thể; không dựa vào sửa tay ở nhiều wiki không đồng bộ.

## 29. Traceability: nối requirement, ADR, code, control và evidence

Một chuỗi truy vết:

```text
Business requirement / Risk
             |
             v
         RFC / ADR
             |
             +--> Standard/control IDs
             +--> Alternatives and tradeoffs
             +--> Threat model / capacity evidence
             |
             v
       Implementation PRs
             |
             +--> Tests / CI policy evidence
             +--> API/event contract versions
             |
             v
      Deployment / Release record
             |
             +--> Image digest + config version
             +--> Canary/SLO results
             |
             v
       Operational feedback
             |
             +--> Incident / postmortem
             +--> Review trigger / new ADR
```

Với ngoại lệ, thêm:
```text
Failed control
     |
     v
Exception request → Risk decision → Compensating control
     |
     v
CI/deployment policy records exception ID
     |
     v
Remediation PRs → Verification → Exception closure
```

Không phải mọi thay đổi cần toàn bộ tài liệu. Mức traceability nên theo **rủi ro và tác động**. Một service dùng thử nội bộ không xử lý dữ liệu nhạy cảm có thể cần hồ sơ nhẹ hơn một payment service chịu compliance và kiểm soát pháp lý.

## 30. Quản lý ID, version và supersession

Một số quy tắc thực dụng:
- Mỗi ADR có ID duy nhất và ổn định, ví dụ `ADR-0042`.
- Mỗi exception có ID riêng, ví dụ `EXC-0031`.
- Không tái sử dụng ID ngay cả khi document bị rejected/retired.
- Tiêu đề có thể đổi nhưng ID giữ nguyên.
- Khi thay quyết định, tạo ADR mới và chỉ ra `Supersedes: ADR-0042`.
- ADR cũ cập nhật metadata `Superseded by: ADR-0079` nếu workflow cho phép, không sửa lý do lịch sử.
- Chuẩn phải có version và ngày hiệu lực; exceptions tham chiếu version kiểm soát.
- Khi chuẩn nâng major version, phải đánh giá các exception cũ còn phù hợp hay cần reapproval.
- Quyết định trong repo cũ khi service được tách/merge cần được giữ index hoặc redirect.
- Với ADR chứa thông tin nhạy cảm, đặt quyền đọc và summary công khai theo policy thay vì phát tán secrets.

Một nguyên tắc hữu ích: **ghi nguyên nhân và trạng thái hiện tại tách biệt**. Current standard có thể thay, nhưng lý do decision ở thời điểm cũ phải còn đọc được.

## 31. Tối ưu kích thước ADR: ngắn mà đủ bằng chứng

Một cấu trúc ADR hiệu quả:
- 1 đoạn mô tả context, có con số/ràng buộc.
- 3–5 decision drivers.
- 2–4 lựa chọn thực tế có tradeoff.
- 1 quyết định rõ, có scope.
- Positive/negative consequences.
- Chủ thể review và validation.
- Link chi tiết.

Những câu nên tránh:
- “Chúng tôi chọn X vì best practice.”
- “Chọn Kafka vì scalable.”
- “Sẽ làm nhanh hơn.”
- “Security đã duyệt.”
- “Tương thích với mọi hệ thống.”

Thay bằng:
- “Chọn event-driven vì hành vi không cần response ngay, có thể chấp nhận kết quả chậm tối đa 2 phút và đã có idempotent consumer.”
- “Thử nghiệm dưới peak 4.000 events/giây cho thấy consumer xử lý ổn định trong quota hiện có; nếu vượt ngưỡng cần đo lại.”
- “Security approver được xác định trong approval record; residual risk và expiry nằm ở EXC-...”
- “Chỉ áp dụng cho Orders read projection; Payment Capture tiếp tục dùng synchronous API.”

Tài liệu nên đủ cụ thể để có thể kiểm chứng, không quá dài tới mức mọi người ngại đọc.

## 32. Review triggers: khi nào cần xem lại quyết định?

Không phải cứ đến mỗi quý là phải họp review mọi ADR, nhưng những giả định quan trọng cần cơ chế kiểm tra.

Ví dụ triggers:
- Traffic tăng hơn năng lực đã dùng trong benchmark.
- p99 latency vượt SLO trong nhiều cửa sổ.
- Team ownership hoặc ranh giới domain thay đổi.
- Chính sách bảo mật/compliance đổi.
- Vendor ngừng hỗ trợ một API hoặc phiên bản.
- Một incident cho thấy failure mode chưa được xem xét.
- Shared database coupling ngăn independent deployment.
- RPO/RTO mới khắt khe hơn khi business criticality tăng.
- Data residency thay đổi do mở thị trường.
- Chi phí vận hành vượt ngưỡng chấp nhận.
- Consumer count và schema compatibility có thay đổi lớn.

Mỗi trigger nên có:
1. Điều kiện đo hoặc sự kiện kích hoạt.
2. Owner nhận thông báo.
3. Thời hạn ra quyết định.
4. Cách đánh giá lại options.
5. Ghi ADR mới hoặc xác nhận ADR còn phù hợp.
6. Liên kết tới PR/incident/risk review.

**Review trigger không tự làm quyết định sai**, chỉ yêu cầu kiểm tra lại assumptions dựa trên bằng chứng mới.

## 33. Decision log và meeting minutes khác ADR

Meeting minutes có thể rất dài: ai nói gì, ai phản đối, còn ai follow-up. ADR nên tóm tắt **quyết định cuối cùng và lập luận kiểm chứng được**.

Ví dụ:
- Meeting minutes: 12 ý kiến, thời gian thảo luận, người tham gia.
- RFC: thiết kế và alternatives trước khi quyết định.
- ADR: chọn outbox thay dual write, vì rủi ro mất event không thể chấp nhận, với consequences.
- Implementation plan: thay code như thế nào, deploy theo thứ tự nào.
- Runbook: kiểm tra backlog/retry/rollback khi production gặp sự cố.
- Postmortem: hệ thống đã sai ra sao và cần thay đổi điều gì.

Có thể link meeting notes từ ADR nhưng không biến ADR thành bản ghi chat. Khi các bên bất đồng, ghi **dissent và rủi ro chưa giải quyết** trong bối cảnh thích hợp, không xóa quan điểm quan trọng chỉ để tạo cảm giác mọi người nhất trí.

## 34. Anti-pattern: Architecture Review Board thành “cửa duyệt” mọi thay đổi

Một số dấu hiệu:
- Mọi team đều cần slot họp hàng tuần cho cả refactor nhỏ.
- Người duyệt không biết code/domain nhưng có quyền veto rộng.
- Hội đồng chỉ đánh giá slide chứ không có evidence từ test/production.
- Những tiêu chuẩn bất thành văn khiến PR bị yêu cầu sửa nhiều vòng.
- Quyết định được chấp nhận nhưng không rõ ai vận hành.
- Các ngoại lệ phải được xem xét theo cách thủ công lặp lại mà không có automation.

Cách cải thiện:
1. Công bố decision rights theo risk tiers.
2. Local ADR được review trong team; cross-context mới cần consultation rộng.
3. Standards rõ thành checklist/test trong CI.
4. “Office hours” hoặc architecture coaching cho vấn đề chưa rõ.
5. Thu thập feedback để sửa guardrails quá cứng.
6. Đặt SLA nội bộ cho review cần thiết, có backup approver.
7. Không bắt team tái thuyết trình một ADR đã accepted nếu scope và assumptions chưa thay.
8. Xem xét ngoại lệ theo risk chứ không theo mức độ nổi tiếng của team.

Một governance tốt làm **thời gian ra quyết định ngắn hơn** nhờ giảm mơ hồ, không phải chỉ tạo nhiều biên bản hơn.

## 35. Quyết định về microservice boundary: một ví dụ governance

Giả sử Checkout Team muốn tách Pricing ra khỏi Orders:
- Pricing có domain rules riêng và tần suất thay đổi nhanh.
- Orders hiện dùng bảng giá chung, transaction cùng DB.
- Một số consumer lấy giá trực tiếp từ Orders API.
- Việc tách có thể ảnh hưởng latency checkout và data consistency.

Quy trình:
1. Team tạo RFC với data ownership, bounded contexts và decision drivers.
2. Domain experts, Orders và Checkout review ngữ nghĩa giá và invariants.
3. Benchmark latency, threat/PII impact và migration plan.
4. ADR ghi quyết định boundary, quyền sở hữu, contract và hệ quả.
5. Chỉ tạo exception nếu giai đoạn migration buộc lệch một chuẩn bắt buộc, ví dụ tạm shared DB read.
6. Phân bổ owner và expiry cho exception nếu có.
7. Triển khai expand–migrate–contract, deploy mixed versions và đo journey SLO.
8. Khi migration xong, revoke direct table access, đóng exception với evidence.
9. Nếu assumptions thay đổi, tạo ADR supersede thay vì ghi đè lịch sử.

Ở đây, governance giúp giữ **tính chính xác của ranh giới domain và khả năng triển khai độc lập**, không đơn thuần phê duyệt chọn công nghệ.

## 36. Tương thích API và event: tiêu chuẩn + ADR + ngoại lệ

Một tổ chức có thể có chuẩn:
- API được version và deprecate có cửa sổ thông báo.
- Event schemas phải kiểm tra backward compatibility theo chính sách.
- Consumer xử lý unknown fields và duplicate events.
- Producer không phát enum mới trước khi consumer versions liên quan sẵn sàng.
- Public contracts có owner, changelog và test evidence.

Một team muốn thay `OrderStatus` từ string sang object ngay trong cùng version cần:
- Đánh giá phương án non-breaking trong RFC.
- ADR nếu sự thay đổi mang tính kiến trúc/cross-team.
- Exception nếu buộc vi phạm tiêu chuẩn compatibility, **và chuẩn đó cho phép được miễn**.
- Consumer inventory và rollout plan.
- Thử nghiệm old/new mixed versions.
- SLO/canary gates và rollback tương thích data.
- Approval đúng risk authority.

Không nên dùng exception để hợp thức hóa việc phá consumer mà không có mitigation. Nếu risk không thể chấp nhận, phương án phải đổi.

## 37. Quản trị data ownership và bảo mật đa tenant

Một standard có thể quy định:
- Mỗi bounded context sở hữu dữ liệu của mình.
- Truy cập trực tiếp database của service khác bị cấm trừ integration migration đã được kiểm soát.
- Tenant isolation được thực thi trong API và data store.
- Dữ liệu nhạy cảm phải được mã hóa và audit theo policy.
- Cross-border data transfer phải được xem xét.
- Secret/credential có vòng đời rotation.

ADR cho một service mới có thể ghi:
- Vì sao dùng database riêng hay shared physical cluster với schema isolation.
- Quy tắc transaction/cross-service consistency.
- Data classification, retention và backup.
- Tenant scoping và authorization model.
- Lộ trình migrate dữ liệu từ hệ legacy.
- Chi phí và trách nhiệm vận hành.

Ngoại lệ có thể xuất hiện trong migration, nhưng các yêu cầu pháp lý không cho miễn phải được xử lý bằng **phương án tuân thủ** chứ không bằng chấp nhận rủi ro thiếu thẩm quyền.

Đừng ghi chi tiết credential, token, customer records hoặc secret material vào ADR/exception. Tài liệu phục vụ audit vẫn phải đáp ứng data minimization và access control.

## 38. Chuẩn về observability và SLO

Giả sử Platform có standard yêu cầu critical services:
- Trace propagation xuyên HTTP/message.
- Structured logs có correlation ID, không chứa secrets.
- Golden signals theo operation: traffic, errors, latency, saturation.
- Owner và service catalog entry.
- SLO/alerts dựa trên user-facing SLI.
- Runbook và escalation path.

ADR có thể nêu lý do chọn OpenTelemetry + vendor backend cụ thể và tradeoff về storage/cost. Team không cần ADR riêng cho mỗi lần thêm span nhỏ.

Một service chưa thể propagate trace qua một partner SDK có thể có exception nếu chuẩn cho phép và đã có:
- Manual correlation mapping.
- Error metrics, request IDs được bảo vệ.
- Alternative log evidence.
- Owner/milestone nâng SDK.
- Expiry và verification.

Khi platform cung cấp instrumentation mặc định trong template hoặc SDK, số lượng exception có thể giảm tự nhiên. Đây là một cách governance tạo **năng lực thực thi**, thay vì chỉ chặn.

## 39. Quản trị ngoại lệ trên quy mô hàng trăm service

Nếu mỗi team lưu waiver ở một file tùy ý không có index:
- Một exception có thể đã hết hạn mà không ai biết.
- Risk owner không thấy tổng exposure.
- CI không thể xác minh đúng control/scope.
- Khi standard version thay đổi, không biết cần review record nào.
- Service chuyển owner nhưng waiver vẫn trỏ người cũ.

Cần exception registry có:
- ID, owner, service ID, standard/control version.
- State và dates có timezone.
- Risk level và residual risk, data classification.
- Compensating controls được xác thực.
- Approval evidence được bảo vệ.
- Remediation issue, milestone, lần review gần nhất.
- Service/region/environment scope.
- Link tới current ADR và PRs liên quan.
- API/query để dashboard/CI dùng như nguồn dữ liệu có thẩm quyền.

Dashboard quan trọng:
- Active exceptions theo risk level, standard, owner.
- Expired và expiring trong 7/30 ngày.
- Exceptions lặp lại nhiều lần theo cùng root cause.
- Thời gian từ requested tới approved/rejected.
- % remediation milestones quá hạn.
- Số policy bypass thực sự xảy ra trong deployments.
- Changes trong residual risk hoặc data classification.

**Không cố làm đẹp chỉ số bằng việc từ chối ghi nhận những ngoại lệ đang có.** Governance cần thấy risk để giảm risk, không phải xóa dấu vết.

## 40. Debt, risk và thời hạn: phân biệt cái cần làm ngay

Một ADR có thể chấp nhận technical debt có chủ đích: tạm dùng một library hiện hành, chưa tách service, hoặc chọn một data store dễ vận hành dù có giới hạn về scale. Điều này **không nhất thiết là exception**, nếu vẫn tuân thủ policy.

Nên phân loại:
- **Technical debt có chủ đích:** tradeoff giữa thời gian và chi phí bảo trì; ghi trigger hoặc kế hoạch.
- **Architecture risk:** khả năng ảnh hưởng đến tính đúng đắn/reliability/security.
- **Compliance gap:** không đáp ứng một yêu cầu chuẩn/pháp lý.
- **Operational toil:** thao tác thủ công gây lãng phí hoặc tăng sai sót.
- **Capability gap:** thiếu tooling/skills để đạt chuẩn.

Tùy loại mà dùng:
- ADR + backlog item cho debt chấp nhận được.
- Risk register cho rủi ro cần được theo dõi ở mức tổ chức.
- Exception cho vi phạm chuẩn bắt buộc có thể xin miễn.
- Incident action item cho failure mode đã xuất hiện.
- Platform roadmap cho tooling nhiều team cùng thiếu.

Nếu một service không có owner hoặc exception không có remediation capacity, điều đó là vấn đề tổ chức cần giải quyết; không nên kéo dài ngày hết hạn rồi coi là hoàn tất.

## 41. Metrics để biết governance có hiệu quả không

Đo theo **khả năng ra quyết định an toàn và nhanh**, không chỉ số lượng hồ sơ.

| Metric | Câu hỏi |
| --- | --- |
| Decision lead time | Từ khi đề xuất đến khi có quyết định rõ mất bao lâu? |
| ADR discoverability | Người mới có tìm được quyết định đang áp dụng không? |
| Decision reversal due to missing context | Có thường phải làm lại vì quên tradeoff không? |
| Contract-related incidents | Quyết định interface/boundary có giảm lỗi không? |
| Exception age và time-to-remediation | Việc lệch chuẩn được xử lý thật hay chỉ gia hạn? |
| Expired exceptions count | Có risk không còn được phê duyệt nhưng vẫn chạy? |
| Repeated exception pattern | Chuẩn/platform có bottleneck hệ thống không? |
| Policy false-positive rate | Gate có chặn nhầm và mất niềm tin không? |
| Emergency override count | Thay đổi khẩn cấp có kiểm soát hay đang thành đường tắt? |
| Service ownership coverage | Mỗi service/control có owner rõ không? |
| Deployment lead time | Guardrails có giảm hay tăng chờ bất hợp lý? |
| Change failure/incident recurrence | Governance có góp phần giảm rủi ro thực tế không? |

Một số ADR nhiều không đồng nghĩa kiến trúc tốt. Một số exception ít cũng không chứng minh compliance cao nếu chưa có kiểm soát phát hiện. Nên đánh giá cùng những chỉ số vận hành và bằng chứng thực tế.

Không nên dùng số lần “phải xin ngoại lệ” để trừng phạt team; team có thể đang chủ động khai báo rủi ro mà trước đó bị che giấu.

## 42. Governance review hàng quý hoặc theo chu kỳ phù hợp

Một phiên review nên tập trung vào các quyết định/rủi ro thực sự cần xử lý:

1. Những ADR có review trigger đã bị kích hoạt.
2. Các standards sẽ thay version hoặc có effective date mới.
3. Exception hết hạn trong kỳ tới, residual risk cao.
4. Nhóm exception xuất hiện lặp lại vì một platform limitation.
5. Những incident cho thấy assumption sai.
6. Ownership đã thay, service bị xóa/merge/tách.
7. Các control automation bị false positives hoặc bypass quá rộng.
8. Việc remediation trễ cần escalations hoặc thay approach.

Đầu ra rõ:
- ADR mới hoặc supersede decision cũ.
- Standard change proposal/version mới.
- Exception closed, reapproved với evidence hoặc escalated.
- Platform engineering tasks giúp nhiều team tuân thủ dễ hơn.
- Owner/milestones cho rủi ro không thể giải quyết ngay.
- Thay đổi trong dashboard/registry/CI.

Không cần họp lớn cho mọi ADR. Có thể review bất đồng bộ với owner rõ; chỉ escalations mang rủi ro cao hoặc có tradeoff liên phòng ban mới cần thảo luận trực tiếp.

## 43. Quy trình triển khai governance từ con số 0

### Pha A — Minimum viable governance

- Định nghĩa một ADR template tối giản và ID convention.
- Chọn kho lưu trữ có version control và tìm kiếm.
- Tạo taxonomy principle/standard/guideline/control.
- Xác định người có thẩm quyền cho local/cross-team/high-risk decisions.
- Ghi 5–10 quyết định ảnh hưởng lớn đang tồn tại, không cố tài liệu hóa mọi dòng code.
- Xây exception template có expiry/owner/approval.
- Công bố link trong service catalog.

### Pha B — Tích hợp vào developer workflow

- Tạo PR template hỏi “thay đổi boundary hoặc policy không?”.
- Nếu có, yêu cầu link ADR/RFC/exception phù hợp.
- Tạo CODEOWNERS cho docs/standards.
- Thêm lint metadata và link checks.
- Tự động hóa một số controls dễ đo (secrets, image provenance, health/SLO metadata).
- Cung cấp guideline về khi nào không cần ADR để tránh burocracy.

### Pha C — Risk-based exception management

- Tạo registry và approval workflow theo risk levels.
- Triển khai expiry reminders/alerts.
- Link exception ID từ CI control failures.
- Kiểm tra scope/approval/compensating controls ở gate phù hợp.
- Theo dõi remediation và evidence.
- Tạo emergency exception path có hậu kiểm.

### Pha D — Học từ dữ liệu

- Đo review lead time, false positives và expired exceptions.
- Xem những standards tạo quá nhiều exception vì khó áp dụng.
- Platform hóa các controls lặp lại thành self-service.
- Xem lại những ADR assumptions đã sai sau incident.
- Cải thiện docs discoverability và training cho team mới.

Mục tiêu không phải tạo một bộ thủ tục đồ sộ ngay đầu; **bắt đầu từ quyết định quan trọng và rủi ro thật**, rồi tăng kiểm soát khi cần.

## 44. Một quy trình ví dụ cho thay đổi kiến trúc nhiều service

Tình huống: team muốn đổi cách truyền user identity qua Gateway → Orders → Payments. Hiện service trung gian forward toàn bộ bearer token, khiến nguy cơ confused deputy và quyền vượt scope.

Quy trình:
1. Threat model đánh giá identity propagation và boundaries.
2. RFC đề xuất token exchange, audience-bound tokens hoặc workload/user context phù hợp.
3. Security, Gateway, Orders và Payments tham vấn.
4. ADR ghi lựa chọn, trust model, token claims, backward compatibility.
5. Các services triển khai verify audience/scope và authorization ở resource owner.
6. Contract tests và security integration tests kiểm chứng.
7. Nếu legacy Payments adapter chưa hỗ trợ, tạo scoped exception với compensating controls và expiry (nếu policy cho phép).
8. Rollout theo lớp, không cho token cũ trở thành đường bypass vô hạn.
9. Theo dõi access-denied anomalies và user journey SLO.
10. Gỡ đường cũ, revoke legacy credentials, đóng exception với evidence.

ADR ghi **lý do chọn cách truyền identity**; exception ghi **phần chưa thể đạt standard trong thời gian giới hạn**; runbook ghi **cách xử lý lỗi/rollback**. Ba tài liệu bổ trợ nhau.

## 45. Bài toán lớn: chọn ADR cho một Platform Golden Path

Một platform team xây golden path tạo service Java/Spring Boot gồm:
- Docker image build và signing.
- OpenTelemetry tracing và logs.
- SLO/health endpoints.
- Workload identity và secret injection.
- Pipeline canary/rollback.
- API contracts, dependency scanning và schema migration checks.

Nên có:
- ADR cho lựa chọn công nghệ nền có tác động lâu dài (ví dụ cách sinh identity/telemetry).
- Standards cho security, contracts và release controls.
- Reference template được version và có migration notes.
- Exception workflow nếu service legacy chưa adopt được.
- Service catalog để theo dõi adoption và ownership.
- Runbook cho lỗi nền tảng và incident.
- Cơ chế cập nhật templates mà không buộc tất cả service deploy lockstep.

Nếu Platform ép tất cả team dùng template mà không hỗ trợ migration, registry sẽ đầy exception. Cần nhìn exception trend như **feedback sản phẩm nội bộ**, không chỉ lỗi tuân thủ của team sử dụng.

## 46. Checklist trước khi chấp nhận một ADR

- [ ] Quyết định có tầm ảnh hưởng đủ để cần ghi lại?
- [ ] Context và scope rõ service/domain/environment?
- [ ] Có constraints, facts, assumptions và decision drivers?
- [ ] Ít nhất các phương án khả thi đã được xem xét?
- [ ] Lý do chọn và lý do bỏ phương án khác có thể hiểu?
- [ ] Positive/negative consequences được ghi trung thực?
- [ ] Data ownership, security, reliability, cost và operation được xét khi liên quan?
- [ ] Có owner và đúng thẩm quyền ra quyết định?
- [ ] Affected teams/consumers đã được tham vấn nếu thay contract?
- [ ] Có evidence và cách kiểm chứng trong CI/production?
- [ ] Có migration/deprecation/rollback implications khi cần?
- [ ] Có review triggers và link tới tài liệu liên quan?
- [ ] Status, ngày, ID, supersedes/superseded-by hợp lệ?
- [ ] Có người sở hữu sau khi implement, không chỉ tác giả tài liệu?

## 47. Checklist trước khi phê duyệt ngoại lệ

- [ ] Control/standard ID và version được chỉ rõ, là yêu cầu có hiệu lực.
- [ ] Phạm vi service/endpoint/env/region/time được giới hạn tối thiểu.
- [ ] Có business justification và giải thích không thể comply ngay.
- [ ] Risk scenarios và data classification được đánh giá.
- [ ] Đã xác định điều kiện policy không được miễn trừ.
- [ ] Residual risk và compensating controls có evidence.
- [ ] Risk approver có thẩm quyền độc lập theo policy.
- [ ] Có start/review/expiry dates và trạng thái rõ.
- [ ] Remediation plan có owner, milestone, tracking issue.
- [ ] Có monitoring, escalation và điều kiện revoke sớm.
- [ ] Pipeline có thể áp exception đúng scope mà không bypass rộng.
- [ ] Có cơ chế cảnh báo gần expiry.
- [ ] Có điều kiện đóng được kiểm chứng, không chỉ “đã merge PR”.
- [ ] Có audit trail của approvals, gia hạn và thay đổi risk.
- [ ] Không tiết lộ secrets/dữ liệu nhạy cảm trong record.

## 48. Những sai lầm phổ biến

**“Viết ADR sau khi triển khai để hợp thức hóa lựa chọn.”** Có thể ghi lại quyết định lịch sử khi cần, nhưng phải nói rõ đây là retrospective record và không giả vờ đã được review trước.

**“Accepted nghĩa là không được đổi.”** Quyết định nên có review triggers và supersession để thích nghi khi giả định thay đổi.

**“Một ADR dài là bằng chứng kiến trúc tốt.”** Thông tin quan trọng là context, tradeoff, consequences và ownership, không phải số trang.

**“Mọi PR đều phải có ADR.”** Gây quá tải, giảm giá trị tài liệu. Dùng tiêu chí tầm ảnh hưởng và rủi ro.

**“ADR có thể thay thế risk approval.”** Không đúng khi quyết định vi phạm standard bắt buộc cần risk owner chấp thuận.

**“Exception không cần thời hạn vì chưa biết khi nào sửa.”** Không có hạn sẽ trở thành bypass vĩnh viễn; nếu chưa có phương án, phải escalate rủi ro và cân nhắc phạm vi hoạt động.

**“Đã có exception thì không cần compensating controls.”** Exception thường tồn tại chính vì rủi ro còn; biện pháp giảm rủi ro phải được duy trì.

**“Team tự cấp exception cho mình.”** Có thể vi phạm separation-of-duties, nhất là security/compliance.

**“CI chỉ tìm exception ID trong YAML là đủ.”** Phải kiểm tra authority, scope, expiry, control, environment và evidence.

**“Gia hạn bằng cách sửa ngày cũ.”** Mất lịch sử đánh giá; gia hạn cần record và review minh bạch.

**“Ngoại lệ nhiều nghĩa là team yếu.”** Có thể chuẩn quá khó, tooling thiếu hoặc migration chưa được platform hỗ trợ; cần xem root cause.

**“Board approval bảo đảm production an toàn.”** Approval không thay tests, canary, monitoring, rollback và incident response.

**“Không có incidents nghĩa là controls đang hiệu quả.”** Có thể telemetry hoặc detection gaps; cần kiểm chứng định kỳ.

**“Đóng exception khi có PR.”** Phải xác minh behavior/rights/config ở environment thực, không chỉ code trên branch.

**“Xóa ADR cũ vì đã obsolete.”** Có thể mất logic lịch sử quan trọng cho incident/audit; nên đánh dấu superseded.

**“Tổ chức governance càng tập trung càng nhất quán.”** Centralized review không thay standards rõ và guardrails tự động.

## 49. Bài tập thực hành

### Bài 1 — Phân biệt ADR và exception

Một team quyết định dùng gRPC thay HTTP giữa hai service; hiện không có chuẩn bắt buộc về protocol. Một team khác phải bỏ mTLS cho partner trong 45 ngày do giới hạn kỹ thuật. Xác định trường hợp nào cần ADR, trường hợp nào cần exception và lý do.

### Bài 2 — Viết ADR cho messaging pattern

Orders cần phát `OrderCreated` sau khi DB commit. So sánh dual write, outbox và distributed transaction; viết một ADR đầy đủ context, drivers, decision, consequences, owner và validation.

### Bài 3 — Risk-based approval

Service xử lý dữ liệu nhạy cảm muốn dùng shared credential tạm trong production. Xác định threat scenario, scope, residual risk, biện pháp bù trừ và loại authority cần phê duyệt. Thảo luận trường hợp không nên cấp exception.

### Bài 4 — Expiry và gia hạn

Một exception cho legacy TLS sẽ hết hạn sau 12 ngày nhưng vendor chưa nâng cấp. Thiết kế quy trình: thu thập evidence mới, risk reassessment, review authority, monitoring, extension và lựa chọn ngừng tính năng nếu rủi ro không thể chấp nhận.

### Bài 5 — Policy-as-code

Thiết kế pseudocode kiểm tra một deployment thiếu workload identity nhưng khai có `EXC-0031`. Hãy xác minh status, standard version, scope, dates, approval và compensating controls; giải thích vì sao tự điền `approved=true` trong repo là không an toàn.

### Bài 6 — ADR supersession

Có ADR cũ chọn PostgreSQL search projection, nay traffic và full-text ranking khiến OpenSearch phù hợp hơn. Viết ADR mới, link supersession, nêu giả định đã thay đổi và lộ trình rebuild/cutover.

### Bài 7 — Governance bottleneck

Một architecture board duyệt tất cả PR, mất trung bình năm ngày mỗi quyết định. Đề xuất decision rights và standards automation để giảm lead time mà vẫn bảo vệ cross-service security/data boundaries.

### Bài 8 — Incident liên quan exception

Legacy adapter không có tracing vì ngoại lệ đã được chấp thuận, nhưng incident không tìm được downstream cause. Lập plan: thêm compensating logs/correlation, owner, expiry và platform enablement; phân biệt giải quyết incident với đóng exception.

### Bài 9 — Migration database

Hai service đang đọc chung một bảng trái data ownership standard. Hãy tạo exception phạm vi hẹp, ADR migration, API/CDC contract, milestones, cutover, verify revocation và điều kiện close.

### Bài 10 — Đo governance

Registry có 120 exceptions, 30 quá hạn, 50 liên quan cùng một CI template không hỗ trợ legacy app. Đề xuất dashboard, root-cause grouping, platform changes và risk-based remediation; tránh chỉ yêu cầu “đóng thật nhiều exceptions”.

### Bài 11 — Audit trail

Mô tả dữ liệu cần lưu để một auditor có thể truy vết từ policy control → exception approval → pipeline decision → deployment → remediation evidence. Những thông tin nào không nên công bố rộng hoặc đặt trong Git public?

### Bài 12 — Team API và quyền ra quyết định

Một stream-aligned team muốn thêm cache cho API, một platform team phản đối vì chi phí. Xác định decision level, evidence cần đo và cách giải quyết tradeoff mà không buộc board quyết định mọi tuning nội bộ.

## 50. Ghi nhớ

- **ADR lưu bối cảnh và lý do của một quyết định kiến trúc quan trọng**, không chỉ mô tả code hoặc quyết định đang triển khai.
- **Một quyết định có thể bị thay thế khi giả định thay đổi**; nên dùng supersession chứ không xóa lịch sử.
- **RFC đề xuất, ADR ghi quyết định, standard quy định yêu cầu, exception ghi sự lệch chuẩn có kiểm soát và runbook chỉ dẫn vận hành.**
- **Không phải lựa chọn khác chuẩn khuyến nghị đều là ngoại lệ**; phải biết quy tắc nào thật sự bắt buộc.
- **Exception phải có scope hẹp, owner, risk analysis, compensating controls, approver và expiry**; không tự động cho phép bypass vĩnh viễn.
- **Risk-based delegation** giúp team tự chủ trong local decisions trong khi các quyết định high-impact vẫn được review đủ.
- **Policy-as-code có thể tăng tốc và tính nhất quán**, nhưng việc áp exception phải xác thực nguồn phê duyệt, control, phạm vi và thời hạn.
- **Governance có giá trị khi tạo khả năng tìm kiếm, truy vết, bảo vệ rủi ro và giảm chờ**, không phải khi tạo nhiều biểu mẫu.
- **ADR, exception và service catalog cần liên kết với PR, deployment, SLO và incident**, giúp kết quả kiểm chứng được.
- **Những ngoại lệ lặp lại là tín hiệu cải tiến platform hoặc chuẩn**, không nhất thiết chỉ là lỗi của các team.
- **Sau incident cần học và sửa giả định**, dùng ADR mới, standard update hoặc remediation thay vì che giấu tradeoff cũ.

Một kiến trúc microservices có khả năng phát triển lâu dài cần cả **quyền tự chủ trong ranh giới đã rõ** và **khả năng giải thích, kiểm chứng và chịu trách nhiệm cho các lựa chọn ảnh hưởng hệ thống**. ADR giữ ký ức của tổ chức; cơ chế exception giữ những lệch chuẩn trong tầm kiểm soát để tính linh hoạt không biến thành rủi ro không có chủ.

### Tài liệu tham khảo và hướng học thêm

- Michael Nygard — Documenting Architecture Decisions: https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions
- ADR GitHub Organization: https://adr.github.io/
- Martin Fowler — Architecture Decision Record: https://martinfowler.com/articles/architecture-decision-records.html
- Team Topologies — Key Concepts: https://teamtopologies.com/key-concepts
- Open Policy Agent (OPA): https://www.openpolicyagent.org/docs/
- Kyverno Policies: https://kyverno.io/docs/
- Kubernetes — Admission Controllers: https://kubernetes.io/docs/reference/access-authn-authz/admission-controllers/
- Google SRE Workbook — Implementing SLOs: https://sre.google/workbook/implementing-slos/
- NIST Risk Management Framework: https://csrc.nist.gov/projects/risk-management/about-rmf
- OWASP — Threat Modeling: https://owasp.org/www-community/Threat_Modeling
- CNCF — Cloud Native Security Whitepaper: https://github.com/cncf/tag-security

Các ID, ngày, policy names, hostnames, risk levels và approval records trong bài đều là ví dụ minh họa. Khi áp dụng cần dựa trên quyền quyết định, chuẩn đang có hiệu lực, dữ liệu nhạy cảm, pháp lý và môi trường vận hành của tổ chức. Bài học này không thay thế việc phê duyệt của security/compliance/risk authorities trong những trường hợp bắt buộc.
