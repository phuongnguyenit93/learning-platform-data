# Ghi lại quyết định, giả thiết và phương án thay thế

## 1. Vì sao thiết kế hệ thống gửi email cần được ghi thành quyết định?

Một ứng dụng Spring Boot có thể bắt đầu bằng vài dòng `JavaMailSender.send(...)`. Tuy nhiên, khi bước vào production, email không còn là “một hàm gửi chuỗi văn bản”. Nó có thể là thông báo thanh toán, xác nhận đơn hàng, đường dẫn kích hoạt tài khoản, mã xác minh, hoá đơn có attachment, cảnh báo hệ thống hoặc bản tin marketing. Mỗi loại mang theo yêu cầu về độ tin cậy, thời gian xử lý, bảo mật và khả năng vận hành khác nhau.

Đội phát triển thường phải quyết định:

- Gửi đồng bộ trong request hay lưu **transactional outbox** và gửi bằng worker?
- Dùng `SimpleMailMessage`, `MimeMessageHelper` hay một mail model trung gian?
- Gửi qua SMTP bằng `JavaMailSender` hay gọi HTTP API của nhà cung cấp?
- Có nhiều provider không; được fallback trong trường hợp nào?
- Retry bao nhiêu lần, backoff ra sao và xử lý kết quả SMTP **không rõ** thế nào?
- Render template lúc tạo công việc hay lúc worker thực sự gửi?
- Ảnh inline, file attachment và dữ liệu cá nhân được lưu và xoá theo vòng đời nào?
- Khi nhà cung cấp SMTP chấp nhận email, trạng thái `SENT` có nghĩa gì?
- Ai được phép đổi tên miền gửi, cập nhật template, replay email lỗi hoặc thay SMTP credentials?
- Hệ thống cần lưu những bằng chứng gì để sau sự cố có thể giải thích **vì sao** đã chọn phương án này?

Nếu chỉ lưu code, một vài comment hoặc ghi nhớ trong cuộc họp, sau vài tháng người khác sẽ nhìn thấy **phương án đang triển khai** nhưng không biết:

1. **Bối cảnh** tại thời điểm quyết định.
2. **Ràng buộc** về nghiệp vụ, kỹ thuật, chi phí và tuân thủ.
3. Những **giả thiết** chưa có bằng chứng đầy đủ.
4. Các **phương án thay thế** đã xét.
5. **Tiêu chí chọn** và đánh đổi được chấp nhận.
6. **Rủi ro còn lại**, người sở hữu và điều kiện cần xem xét lại.

Đó là lý do nên ghi **Architecture Decision Record (ADR)** hoặc một định dạng decision log tương đương. Một ADR là bản ghi ngắn gọn nhưng đủ bằng chứng về một quyết định có tác động tới kiến trúc, không phải tài liệu mô tả tất cả các lớp Java.

> Mục tiêu của ADR không phải chứng minh lựa chọn hiện tại luôn đúng, mà giúp người khác biết **vì sao nó hợp lý trong bối cảnh đã biết**, điều gì có thể làm nó không còn đúng và khi nào cần thay đổi.

## 2. Phân biệt quyết định, giả thiết, ràng buộc, lựa chọn và bằng chứng

Năm loại thông tin rất dễ bị trộn lẫn khi thiết kế Spring Mail.

| Thành phần | Câu hỏi nó trả lời | Ví dụ trong hệ thống mail |
| --- | --- | --- |
| **Decision / Quyết định** | Chúng ta **chọn làm gì**? | Lưu notification vào PostgreSQL outbox rồi worker gửi bằng `JavaMailSender` |
| **Assumption / Giả thiết** | Điều gì đang được **tạm coi là đúng** nhưng chưa đủ bằng chứng? | SMTP relay có thể chịu 100 submissions/phút ở giờ cao điểm |
| **Constraint / Ràng buộc** | Điều gì **bắt buộc** phải tuân theo? | Không đưa token mật khẩu hoặc attachment nhạy cảm vào log |
| **Alternative / Phương án thay thế** | Có thể giải quyết bằng cách nào khác? | Gửi đồng bộ; message broker; email provider API |
| **Evidence / Bằng chứng** | Có dữ liệu nào ủng hộ hoặc bác bỏ? | Load test trên staging, incident, provider SLA, benchmark |

### 2.1. Quyết định phải đủ cụ thể để kiểm chứng

Không nên ghi:

> Chúng ta dùng giải pháp gửi mail tốt và đáng tin cậy.

Nên ghi:

> Đối với email giao dịch phát sinh từ thay đổi nghiệp vụ trong PostgreSQL, hệ thống ghi một delivery intent trong **cùng transaction** với thay đổi nghiệp vụ. Một worker riêng đọc outbox, xây MIME bằng Spring Mail và gửi qua SMTP; request nghiệp vụ không chờ SMTP. Retry và outcome được lưu theo delivery/attempt.

Quyết định thứ hai chỉ ra ranh giới transaction, cơ chế xử lý, trách nhiệm worker và các loại bằng chứng có thể kiểm tra.

### 2.2. Giả thiết không phải sự thật được bảo đảm

Ví dụ:

> Giả thiết A-02: Nhà cung cấp SMTP thường phản hồi trong dưới 2 giây.

Đây là một giả thiết có thể được đo. Không nên viết:

> SMTP luôn nhanh, vì vậy gửi đồng bộ không ảnh hưởng latency.

Nếu chưa thử tải thực tế và chưa đo p95/p99, đừng trình bày suy đoán là một đặc tính được provider bảo đảm.

### 2.3. Ràng buộc phải có nguồn và phạm vi

Ví dụ:

~~~text
Constraint C-01
Nguồn: Chính sách bảo vệ dữ liệu của tổ chức
Phạm vi: Email chứa dữ liệu cá nhân của nhóm khách hàng EU
Nội dung: Chỉ dùng provider/region đã được phê duyệt
Độ ưu tiên: Bắt buộc
Owner: Security/Compliance
~~~

Một SMTP provider có latency thấp hơn hoặc rẻ hơn vẫn không đủ điều kiện nếu trái ràng buộc. Nếu ràng buộc là chính sách nội bộ, phải biết chính sách nào và ai phê duyệt, không tự giả định từ tên miền người nhận.

### 2.4. Rủi ro khác giả thiết

Giả thiết:

> Retry SMTP sẽ hiếm khi gặp trạng thái không rõ kết quả.

Rủi ro tương ứng:

> Nếu kết nối đứt sau SMTP DATA mà relay đã accepted, việc retry hoặc fallback có thể tạo email trùng.

Mô tả rủi ro cần có **xác suất/độ không chắc chắn**, **tác động**, **biện pháp giảm thiểu** và **người chấp nhận**. Không chỉ ghi `Risk: low` mà không giải thích vì sao.

## 3. Khi nào nên tạo một ADR?

Không phải mọi thay đổi thuộc tính Java đều cần ADR. Nên tạo khi lựa chọn:

- Khó đảo ngược hoặc có chi phí chuyển đổi lớn.
- Ảnh hưởng tới nhiều nhóm/module.
- Mang rủi ro mất email, gửi trùng, rò rỉ dữ liệu, vi phạm SLA.
- Quyết định nền tảng về persistence, provider, contract và ranh giới transaction.
- Làm thay đổi mô hình vận hành, ownership, bảo mật hoặc chi phí.
- Dựa trên một giả thiết quan trọng chưa chắc chắn.

Ví dụ những quyết định **đáng ghi ADR**:

| Vấn đề | Vì sao quan trọng |
| --- | --- |
| Sync send hay outbox | Ảnh hưởng transaction, latency, retry và failure recovery |
| SMTP hay HTTP email API | Ảnh hưởng vendor lock-in, feedback, authentication và migration |
| One provider hay multi-provider | Ảnh hưởng deliverability, identity, cost và duplicate risk |
| Mô hình `ACCEPTED/UNKNOWN/FAILED` | Quyết định an toàn khi retry/fallback |
| Lưu MIME snapshot hay chỉ lưu template ID | Ảnh hưởng replay, audit, PII retention và khả năng thay đổi nội dung |
| Template render ở producer hay worker | Ảnh hưởng tính nhất quán và versioning |
| Cách lưu attachment | Ảnh hưởng disk/object storage, security và vòng đời |
| Chiến lược bounce/complaint | Ảnh hưởng suppression và chính sách liên lạc |
| Phân vùng tenant/region | Ảnh hưởng quyền, compliance và provider eligibility |

Những thay đổi nhỏ có thể chỉ cần pull request hoặc issue:

- Đổi tên biến `smtpTimeoutMillis`.
- Sửa một log typo.
- Điều chỉnh CSS của một template theo design system đã chấp thuận.
- Thêm một unit test cho một nhánh đã có.

Nếu một thay đổi “nhỏ” làm thay đổi hợp đồng quan trọng, ví dụ chuyển `timeout` thành blind resend, vẫn cần cập nhật ADR/risk rationale.

## 4. Một ADR tốt có những trường nào?

Một bản ghi hữu dụng thường có:

| Trường | Mục đích |
| --- | --- |
| ID/title | Tìm và tham chiếu ổn định |
| Status | Proposed, Accepted, Superseded... |
| Date | Ngày đưa ra hoặc chấp nhận quyết định |
| Owners/deciders | Ai chịu trách nhiệm chuyên môn và phê duyệt |
| Scope | Loại email, service, môi trường, tenant/region |
| Context/problem | Tình huống cần quyết định, điều gì đang không ổn |
| Decision drivers | NFR/SLO, chi phí, bảo mật, vận hành |
| Constraints | Điều bắt buộc, nguồn chính sách |
| Assumptions | Các giả thiết kèm độ tin cậy và kế hoạch kiểm chứng |
| Considered alternatives | Những cách giải quyết khả thi đã xét |
| Decision/rationale | Chọn phương án nào và vì sao |
| Tradeoffs/consequences | Được gì, mất gì, tác động mới |
| Risks/mitigations | Lỗ hổng còn lại và cách giảm thiểu |
| Verification | Điều kiện, thử nghiệm, metric xác nhận |
| Revisit triggers | Khi nào phải xem xét lại |
| References | Issue, PR, biểu đồ, benchmark, policy, incident |

Không nhất thiết mọi ADR đều dài hàng chục trang. Với quyết định nhỏ, một trang có thể đủ. Với quyết định quan trọng như outbox hay provider failover, cần ghi **giả thiết và thất bại tiềm ẩn** đủ sâu để sau này không vô tình lặp lại sai lầm.

### 4.1. ID ổn định và tên có ý nghĩa

Ví dụ:

~~~text
ADR-001: Gửi email giao dịch qua transactional outbox
ADR-002: Dùng JavaMailSender và MIME cho email có attachment
ADR-003: Chuẩn hóa outcome của SMTP thành ACCEPTED/REJECTED/UNKNOWN
ADR-004: Chỉ fallback khi đã chứng minh provider trước chưa accepted
ADR-005: Lưu template version và snapshot payload trước khi enqueue
~~~

Số ID dùng để tham chiếu và giữ lịch sử; không cần đổi số khi title chỉnh lại. Tên nên thể hiện **nội dung lựa chọn**, không phải chủ đề mơ hồ như “Email architecture”.

### 4.2. Trạng thái ADR

Một lifecycle thường gặp:

~~~text
PROPOSED
    |
    v
UNDER_REVIEW
    |
    +--> REJECTED
    |
    v
ACCEPTED
    |
    v
IMPLEMENTED
    |
    +--> REVISIT_REQUIRED
    |       |
    |       v
    |    New ADR
    |
    v
SUPERSEDED (by ADR-0xx)
~~~

Các status là **quy ước của nhóm**, không phải các enum chính thức của Spring Framework Mail. Có nhóm chỉ dùng `Proposed`, `Accepted`, `Deprecated`, `Superseded`. Quan trọng là định nghĩa rõ:

- `Accepted`: đã chọn, chưa chắc code đã triển khai.
- `Implemented`: code/config vận hành đã áp dụng theo phạm vi.
- `Superseded`: được thay bởi quyết định mới, nhưng bản cũ vẫn lưu.
- `Rejected`: đã xem xét nhưng không chọn; giữ lý do để tránh đề xuất lại mà thiếu bối cảnh.

Không âm thầm sửa ADR cũ thành một quyết định mới làm mất lịch sử. Nếu kiến trúc thay đổi đáng kể, tạo ADR kế tiếp và liên kết `supersedes` / `superseded-by`.

## 5. Mẫu ADR có thể dùng ngay

Mẫu sau có thể được lưu làm Markdown trong một repo kiến trúc:

~~~markdown
# ADR-XXX: [Tên quyết định theo dạng hành động]

- Status: PROPOSED
- Created: YYYY-MM-DD
- Decision owner: [Vai trò/nhóm]
- Deciders: [Nhóm có quyền chấp thuận]
- Scope: [Service, loại email, tenant/region, môi trường]
- Related: [Issue/PR/ADR trước]

## Context
[Hiện trạng, vấn đề, hậu quả nếu không quyết định]

## Goals / quality attributes
- [SLO/latency]
- [Reliability/recovery]
- [Security/privacy]
- [Observability/operations]
- [Cost/maintainability]

## Constraints
- C-01: [Ràng buộc, nguồn và phạm vi]

## Assumptions
| ID | Giả thiết | Độ tin cậy | Cách kiểm chứng | Owner |
| -- | -------- | ----------- | -------------- | ----- |
| A-01 | ... | Medium | ... | ... |

## Alternatives considered
### Option 1
- How it works:
- Benefits:
- Costs:
- Failure modes:

### Option 2
- How it works:
- Benefits:
- Costs:
- Failure modes:

## Decision
[Phương án được chọn, ranh giới, ngoại lệ]

## Rationale
[Tiêu chí nào quyết định; vì sao không chọn phương án khác]

## Consequences and tradeoffs
### Positive
### Negative
### Unknown / deferred

## Risks and mitigations
| Risk | Impact | Mitigation | Owner | Residual risk |
| ---- | ------ | ---------- | ----- | ------------- |

## Validation
- [Test/metric/evidence cần đạt]
- [Người chấp nhận]

## Revisit triggers
- [Điều kiện phá vỡ giả thiết]
- [Thay đổi workload, provider, yêu cầu]

## References
- [Issue/PR/runbook/benchmark]
~~~

Các chỗ trong ngoặc vuông là placeholder. Khi áp dụng, hãy thay bằng số liệu và nguồn có thật; không để `A-01: provider ổn định` mà không nêu cách quan sát hay ngày đánh giá lại.

## 6. Ghi bối cảnh và động lực quyết định

Một ADR có thể đúng kỹ thuật nhưng vô dụng nếu viết không rõ **bài toán cần giải quyết**.

### 6.1. Context yếu

> Công ty có nhiều email, nên đổi hệ thống gửi email.

Câu này không phân biệt vấn đề latency, độ tin cậy, chi phí, deliverability, vận hành hay compliance.

### 6.2. Context có thể hành động

> Luồng xác nhận đơn hàng hiện gọi `JavaMailSender.send` trực tiếp trong HTTP request. Khi SMTP relay chậm hoặc unreachable, p95 latency của endpoint tăng và một số request thất bại dù transaction tạo đơn hàng đã commit. Sau restart, không có bản ghi durable cho những email chưa gửi. Nhóm cần một cơ chế bảo đảm giữ được ý định gửi, tách lỗi SMTP khỏi kết quả tạo đơn hàng và có thể retry sau crash.

Context này chỉ rõ:

- Vị trí ranh giới request và mail.
- Sự bất nhất giữa **business transaction** và **side effect**.
- Tác động tới user và vận hành.
- Nhu cầu durable, retry và khả năng đối soát.

### 6.3. Decision drivers nên ưu tiên rõ

Ví dụ cho email giao dịch:

| Tiêu chí | Mức ưu tiên | Vì sao |
| --- | --- | --- |
| Không mất ý định gửi sau khi đơn hàng commit | Must-have | Đơn hàng cần thông báo có thể phục hồi |
| Không chặn HTTP request bởi SMTP | Must-have | Trải nghiệm và resilience |
| Có audit per delivery/attempt | Must-have | Hỗ trợ điều tra |
| Bảo vệ PII/token | Must-have | Bảo mật |
| Latency từ tạo đơn đến submission | High | SLA thông báo |
| Chi phí vận hành | Medium | Có thể chấp nhận worker/DB maintenance |
| Đơn giản triển khai ở giai đoạn đầu | Medium | Không cần broker nếu DB đủ tải |

Một tiêu chí `Must-have` không nên dễ dàng được “bù” bằng điểm số ở tiêu chí `Low`. Nếu phương án không thỏa security/compliance, loại khỏi tập lựa chọn trước khi so điểm.

## 7. Phương án thay thế phải được ghi công bằng

Một ADR không tốt thường nêu một phương án được chọn rất chi tiết, còn các lựa chọn khác chỉ ghi “không phù hợp”. Người đọc cần biết tại sao chúng **đã từng là lựa chọn hợp lý**, điều kiện nào có thể khiến chúng trở thành phương án tốt hơn.

### 7.1. Đừng dựng đối thủ giả yếu

Ví dụ không công bằng:

~~~text
Option A: Gửi đồng bộ, dễ lỗi, không đáng dùng.
Option B: Outbox, tốt nhất trên mọi phương diện.
Chosen: B.
~~~

Trên thực tế, gửi đồng bộ có thể hoàn toàn hợp lý với ứng dụng nhỏ, lưu lượng thấp, mail không phải nghiệp vụ trọng yếu và khách hàng chấp nhận failure semantics tương ứng. Outbox tăng reliability nhưng cần:

- Database schema và cleanup.
- Worker/scheduler/queue ownership.
- Retry, backoff, timeout và dead letter.
- Kiểm soát duplicate, monitoring và runbook.
- Vòng đời template, attachments và secrets.

Một ADR nên ghi cả **chi phí và trường hợp áp dụng** cho phương án không chọn.

### 7.2. Bảng thay thế cho bài toán gửi mail

| Phương án | Ưu điểm | Hạn chế/rủi ro | Khi nào phù hợp |
| --- | --- | --- | --- |
| `JavaMailSender` đồng bộ trong request | Ít thành phần, dễ debug, biết kết quả submission trước khi trả lời | SMTP latency/outage ảnh hưởng request; transaction không bao phủ SMTP | App nhỏ, email không bắt buộc hoặc workflow chấp nhận timeout |
| `@Async`/executor trong memory | Request trả nhanh, triển khai đơn giản | Job có thể mất khi JVM restart; error handling/queue không mặc định durable | Notification best-effort, môi trường hạn chế |
| Transactional outbox bằng PostgreSQL | Ý định gửi bền vững khi commit cùng nghiệp vụ; retry/replay rõ | Worker, DB load, schema, idempotency và vận hành | Email giao dịch quan trọng, DB đã có và tải vừa phải |
| DB outbox + message broker | Có thể scale và tách consumers, retry/partitions linh hoạt | Phức tạp hơn; cần phối hợp DB/broker, ack và dedupe | Lưu lượng lớn, nhiều downstream |
| External notification service | Tập trung hóa gửi, template và provider routing | Phụ thuộc service, API contract, SLA và ownership | Nhiều product dùng chung notification |
| Gọi provider HTTP API trực tiếp | Có thể có message ID, templates/webhooks và idempotency theo hãng | Vendor lock-in, auth/API quota, semantics riêng | Khi provider có API và feedback đáp ứng nhu cầu |

Không nên thêm hàng “Mất email: không bao giờ” cho outbox hoặc broker. Một thiết kế outbox có thể phục hồi ý định gửi sau crash, nhưng **SMTP submission vẫn có cửa sổ kết quả không rõ**, và trạng thái delivered-to-inbox không thể được suy chỉ từ `send` thành công.

### 7.3. Mô tả lựa chọn bằng failure modes

Với mỗi phương án, nên nêu ít nhất:

1. Nếu **producer crash** trước/sau business commit thì sao?
2. Nếu **SMTP chậm/không kết nối** thì API/user chịu tác động gì?
3. Nếu **worker crash sau SMTP accepted** nhưng trước DB update thì sao?
4. Nếu **provider phản hồi UNKNOWN** sau DATA hoặc HTTP POST thì sao?
5. Nếu **template/attachment biến mất** lúc retry thì sao?
6. Nếu người vận hành cần **manual redrive**, bằng chứng ở đâu?
7. Nếu **tenant có hạn chế dữ liệu** thì phương án có tuân thủ được không?

Một phương án có điểm số tốt nhưng không giải quyết được failure mode nghiêm trọng không nên được chấp thuận vì “trung bình tổng điểm cao”.

## 8. Lập ma trận đánh đổi có số liệu nhưng không tạo độ chính xác giả

Ma trận decision matrix giúp thảo luận có cấu trúc, nhưng các trọng số và điểm thường là **đánh giá của nhóm**, không phải sự thật khoa học.

### 8.1. Bước 1: loại các phương án vi phạm ràng buộc

Ví dụ:

~~~text
Constraint:
  Mail intent must be durable after business commit.

Option: @Async using in-memory executor only.
Result: Not eligible for this workflow.
~~~

Không chấm `@Async` 10 điểm vì rẻ rồi dùng điểm đó để bù yêu cầu durability bắt buộc.

### 8.2. Bước 2: chấm các phương án còn hợp lệ

Ví dụ giả định cho một dịch vụ đơn hàng **đã có PostgreSQL**:

| Tiêu chí | Trọng số | Outbox DB | DB + broker | Notification service |
| --- | ---: | ---: | ---: | ---: |
| Khôi phục intent sau crash | 30% | 5 | 5 | 4 |
| Độ đơn giản vận hành ở giai đoạn hiện tại | 20% | 4 | 2 | 3 |
| Scale throughput khi tăng tải | 20% | 3 | 5 | 4 |
| Có đủ audit và khả năng đối soát | 20% | 4 | 4 | 4 |
| Chi phí triển khai ban đầu | 10% | 4 | 2 | 3 |
| **Điểm weighted minh họa** | **100%** | **4,1** | **3,8** | **3,7** |

Điểm số này chỉ phục vụ minh họa cách lập bảng. Khi áp dụng thực tế, cần:

- Thống nhất ý nghĩa thang điểm 1–5.
- Ghi nguồn evidence cho từng điểm.
- Đánh dấu độ tin cậy của estimate.
- Kiểm tra độ nhạy khi thay đổi trọng số.
- Ghi rõ quyết định cuối nếu nó khác kết quả chấm điểm.

**Lưu ý phép tính trong ví dụ:** lựa chọn được chấm trên thang 1–5 theo các trọng số đã nêu; không dùng bảng làm benchmark mặc định của Spring Mail.

### 8.3. Bước 3: sensitivity analysis

Nếu throughput tăng gấp nhiều lần, trọng số `Scale throughput` có thể từ 20% thành 40%, trong khi `Simplicity` giảm. Khi đó DB + broker có thể phù hợp hơn. Ghi lại điều kiện thay đổi:

> Revisit when sustained daily email volume exceeds the PostgreSQL outbox capacity established by load testing, or queue-age SLO is violated after ordinary scaling.

Như vậy lựa chọn hiện tại không trở thành “chân lý vĩnh viễn”, mà có **giới hạn áp dụng đã biết**.

### 8.4. Chi phí không chỉ là giá per-email

Với SMTP/API provider:

~~~text
Total cost
  = provider charges
  + infrastructure/storage
  + retries and additional traffic
  + engineering and on-call
  + deliverability/incident costs
  + compliance/security controls
~~~

Một provider rẻ hơn trên bảng giá có thể tốn hơn khi tính chi phí incident và feedback integration. Không nên ghi “B rẻ hơn” chỉ từ một giá niêm yết chưa xác minh workload, attachment, retention và hỗ trợ.

## 9. Quản lý giả thiết như một danh sách kiểm chứng được

Giả thiết quan trọng không nên chỉ nằm rải rác trong đoạn văn. Một **Assumption Register** giúp biết điều gì vẫn chưa chắc chắn và ai có trách nhiệm kiểm chứng.

### 9.1. Ví dụ cho Spring Mail

| ID | Giả thiết | Mức tin cậy | Nếu sai thì sao? | Cách kiểm chứng | Owner |
| --- | --- | --- | --- | --- | --- |
| A-01 | Outbox worker xử lý đủ tải giờ cao điểm | Medium | Queue age tăng, email chậm | Load test và p95 queue age | Backend |
| A-02 | Provider SMTP cho phép mức connection/quota dự kiến | Low | Throttle/temporary failure | Xác minh hợp đồng và staging test | Platform |
| A-03 | Ảnh logo trong classpath có trên mọi replica | High | MIME build lỗi | Test artifact/container | Build |
| A-04 | Attachment reference còn đọc được đến khi retry kết thúc | Medium | Retry mất payload | Retention/fault-injection test | Storage |
| A-05 | Phần lớn lỗi SMTP được phân loại đủ để retry an toàn | Low | Duplicate nếu retry UNKNOWN | Test protocol và reconcile | Mail owner |
| A-06 | Bounces được provider report với ID đủ để correlate | Medium | Suppression lệch | Webhook/DSN fixture test | Integration |
| A-07 | Marketing và security có thể cùng account mà không ảnh hưởng SLO | Low | OTP chậm khi campaign tăng | Capacity test, reserved quotas | Operations |
| A-08 | Data residency của backup/logs đáp ứng policy | Chưa xác nhận | Vi phạm quy định nội bộ | Contract/security review | Compliance |

Đây là **giả thiết ví dụ**, không phải kết luận về một nhà cung cấp cụ thể.

### 9.2. Mỗi giả thiết cần trạng thái

~~~text
PROPOSED
   |
   +--> VALIDATED
   |
   +--> INVALIDATED
   |
   +--> EXPIRED / NEEDS_RECHECK
~~~

Một giả thiết đã kiểm chứng bằng load test tháng trước có thể hết hiệu lực sau khi tăng traffic, chuyển region, nâng dependency hoặc thay provider quota. Trạng thái `VALIDATED` nên đi kèm ngày/phiên bản môi trường và phạm vi đo.

### 9.3. Độ tin cậy không thể thay bằng sự lạc quan

Ví dụ:

> A-05: “SMTP timeout sau DATA chắc chắn nghĩa là server chưa nhận”.

Giả thiết này **không an toàn**. Trong SMTP, kết quả có thể không rõ nếu client mất phản hồi sau khi truyền xong DATA. ADR phải ghi rủi ro duplicate và thiết kế `UNKNOWN`, không dùng confidence `High` để bỏ qua semantics giao thức.

### 9.4. Assumption → test → ADR decision

~~~text
Assumption A-01
    |
    v
Hypothesis:
  PostgreSQL outbox can keep queue age below SLO
    |
    v
Benchmark under representative workload
    |
    v
Evidence:
  throughput, DB IOPS, queue age, contention
    |
    v
Decision:
  accept DB outbox or revisit alternatives
~~~

Khi bằng chứng không hỗ trợ giả thiết, phải cập nhật quyết định hoặc risk acceptance. Không giữ giả thiết sai trong tài liệu chỉ vì code đã triển khai.

## 10. Phân biệt metric, SLO, SLA và giả thiết về delivery

Email có nhiều cột mốc khác nhau. Nếu không định nghĩa chúng, ADR dễ ghi lời hứa không thể kiểm chứng.

~~~text
Business transaction committed
         |
         v
Outbox intent persisted
         |
         v
Worker claims
         |
         v
SMTP/API submission
         |
         v
Provider accepts
         |
         v
Recipient mail server accepts (if feedback known)
         |
         v
Mailbox/inbox placement (often not directly observable)
         |
         v
User sees/reads email (not reliably provable)
~~~

### 10.1. SLO đúng điều có thể đo

Thay vì:

> 99,9% email đến inbox trong dưới 5 giây.

Nếu không có bằng chứng inbox placement đáng tin, hãy chọn một SLO có thể quan sát:

> Với email giao dịch hợp lệ, 99% delivery intent được tạo và **được nộp thành công cho SMTP/API provider** trong vòng N giây từ business commit, loại trừ các trường hợp bị suppress hoặc vi phạm policy được định nghĩa rõ.

Con số N phải được quyết định từ yêu cầu và load test, không mặc định 5 giây cho mọi hệ thống.

### 10.2. Phân biệt delivered và accepted

`JavaMailSender.send(...)` trả thành công thường chứng minh transaction gửi qua SMTP đã hoàn tất theo client và relay accepted theo quan sát, **không bảo đảm thư đã tới inbox**. Delivery feedback từ provider có thể cho biết recipient server accepted, deferred, bounced hoặc complained; vẫn không chứng minh người dùng đã đọc nội dung.

### 10.3. Đặt SLO theo loại mail

| Loại email | Mục đích đo | Rủi ro nếu đến muộn |
| --- | --- | --- |
| OTP/security | Thời gian từ sự kiện đến submission | Token hết hạn, đăng nhập thất bại |
| Transactional | Thời gian từ commit đến submission | Người dùng thiếu xác nhận |
| Invoice | Hoàn tất trước deadline nghiệp vụ | Chậm hoá đơn, hỗ trợ tăng |
| Marketing | Throughput trong campaign window, complaint rate | Gửi sai giờ, reputation suy giảm |
| Alert nội bộ | Submission latency và alerting fallback | Bỏ sót phản ứng sự cố |

Không bắt buộc tất cả mail đi cùng một pool, timeout và retry policy. ADR phải ghi phạm vi để tránh dùng giả thiết của marketing cho OTP.

## 11. Ghi quyết định sao cho có thể truy ngược từ code và vận hành

Một ADR cần nối tới hệ thống thật, không nằm tách biệt như tài liệu đọc một lần.

### 11.1. Các liên kết cần thiết

~~~text
ADR-001: Transactional outbox
   |
   +--> Work item / issue
   +--> Pull request introducing outbox tables
   +--> Database migration
   +--> MailOutboxService / MailDispatchWorker
   +--> Dashboard for queue age / retry
   +--> Runbook for SMTP outage
   +--> Incident reports
   +--> ADR-003 for provider outcome model
~~~

Không cần biến ADR thành danh sách mọi file Java. Chỉ liên kết các thay đổi **thể hiện quyết định** và bằng chứng cần cho người bảo trì.

### 11.2. Lưu ở đâu?

Phương án thường gặp:

~~~text
docs/
  architecture/
    decisions/
      0001-transactional-outbox.md
      0002-mail-payload-snapshot.md
      0003-provider-outcome-model.md
      0004-fallback-guardrails.md
      index.md
~~~

Lưu ADR cùng repo giúp review trong pull request và đồng bộ với code. Với quyết định ảnh hưởng nhiều service, có thể dùng một registry kiến trúc trung tâm, miễn là các repo liên quan dễ tham chiếu.

### 11.3. Vì sao không chỉ ghi trong PR description?

PR hữu ích để thấy **implementation change**, nhưng sau thời gian dài:

- Thay đổi code có thể được refactor qua nhiều PR.
- Người mới không biết PR nào là quyết định ban đầu.
- Rationale bị chôn trong comment/thảo luận.
- Không có trạng thái `Superseded` rõ ràng.
- Không có `revisit trigger`, assumptions owner hay risk acceptance.

Nên có ADR làm **bản ghi quyết định ổn định**, rồi tham chiếu PR để đọc chi tiết triển khai.

### 11.4. Một decision log tổng hợp

| ADR | Chủ đề | Trạng thái | Owner | Bằng chứng gần nhất | Khi xem xét lại |
| --- | --- | --- | --- | --- | --- |
| ADR-001 | Mail outbox | Accepted | Messaging team | Load test L-01 | Queue age vượt SLO |
| ADR-002 | Template snapshot | Proposed | Product + Backend | Prototype P-02 | Trước khi áp dụng production |
| ADR-003 | SMTP outcome UNKNOWN | Accepted | Mail owner | Fault injection F-03 | Provider API thay đổi |
| ADR-004 | Provider fallback | Under review | Platform | Vendor contract review | Sau thử nghiệm secondary |

Đây là ví dụ cấu trúc. “Evidence L-01” không phải một báo cáo đã tồn tại trong dự án của người đọc; khi dùng thực tế phải thay bằng link kiểm chứng được.

## 12. Ví dụ ADR hoàn chỉnh: gửi email giao dịch qua transactional outbox

Đây là một **ví dụ giả định**, dùng để minh hoạ cách viết ADR có thể review và triển khai. Các thông số tải, SLA và yêu cầu cần được thay bằng dữ liệu thật của ứng dụng.

### ADR-001 — Quyết định

~~~text
ID: ADR-001
Title: Persist transactional mail intent in PostgreSQL outbox
Status: ACCEPTED (example)
Created: 2026-11-12 (example date)
Scope: Spring Boot Order Service; transactional confirmation emails
Owner: Backend Messaging
Deciders: Order Service owner + Platform owner
Supersedes: None
~~~

### 12.1. Context

Khi đơn hàng được tạo thành công, ứng dụng cần thông báo cho khách hàng. Cách triển khai hiện tại gọi SMTP trực tiếp từ HTTP handler:

~~~text
POST /orders
    |
    v
BEGIN DB transaction
    |
    v
INSERT order
    |
    v
COMMIT
    |
    v
JavaMailSender.send(email)
    |
    v
HTTP response
~~~

Nếu SMTP chậm, response chậm. Nếu SMTP lỗi sau business commit, HTTP request có thể trả lỗi dù đơn hàng đã được tạo; người dùng có thể gửi lại yêu cầu và tạo hành động trùng nếu business idempotency chưa tốt. Nếu process chết trước bước gửi mail, không có bản ghi chắc chắn để phục hồi notification.

### 12.2. Mục tiêu

- Không đánh mất **ý định gửi** khi transaction tạo đơn hàng đã commit.
- Không chặn response người dùng bởi latency SMTP.
- Theo dõi trạng thái/attempt của mỗi notification.
- Hỗ trợ retry, giới hạn số lượt, dead letter và manual redrive có audit.
- Không gửi nhầm người nhận hoặc lộ token/PII qua log.
- Có metric queue age và thời gian từ business commit tới provider submission.

### 12.3. Ràng buộc

- C-01: Orders và mail outbox có thể lưu trên cùng PostgreSQL transaction manager.
- C-02: Không được gửi email khi transaction tạo đơn rollback.
- C-03: Delivery phải được scope theo tenant/recipient và business event.
- C-04: SMTP không hỗ trợ distributed transaction với PostgreSQL.
- C-05: Không lưu SMTP password/token trong bảng outbox.

### 12.4. Giả thiết

| ID | Nội dung | Confidence | Cách xác minh |
| --- | --- | --- | --- |
| A-01 | PostgreSQL hiện có đủ capacity cho outbox workload | Medium | Load test đo insert/claim/index/cleanup |
| A-02 | Worker có thể xử lý hàng đợi trong latency SLO | Medium | Staging test theo peak workload |
| A-03 | SMTP provider có đủ quota và identity đã verify | Chưa xác nhận | Vendor contract + test |
| A-04 | Attachment/payload references còn hợp lệ qua retry | Medium | Retention/fault-injection test |
| A-05 | Đã có business key đủ ổn định để dedupe | Medium | Review các order events/retries |

### 12.5. Các phương án được xem xét

**Option A: tiếp tục gửi trực tiếp trong HTTP handler.**

- Ưu: triển khai đơn giản, ít thành phần.
- Nhược: request coupling, lỗi sau commit khó phục hồi, latency bị ảnh hưởng.
- Chấp nhận được nếu email chỉ best-effort và không cần durable intent.

**Option B: dùng `@Async` hoặc executor in-memory.**

- Ưu: request không chờ SMTP, ít thay đổi code.
- Nhược: task đã enqueue nhưng chưa xử lý có thể mất khi process restart, khó audit/retry bền vững.
- Không đáp ứng yêu cầu durable intent.

**Option C: PostgreSQL transactional outbox + worker.**

- Ưu: commit order và intent trong một transaction; có state/query/audit; vận hành trong hạ tầng DB hiện có.
- Nhược: cần job claim, lease, indexes, retry, retention; SMTP vẫn có outcome UNKNOWN.

**Option D: order transaction + publish trực tiếp lên broker.**

- Ưu: throughput tốt và có cơ chế consumer scalable.
- Nhược: không có transaction nguyên tử giữa PostgreSQL order và publish broker nếu không có transactional coordination phù hợp; producer crash có thể bỏ sót event.
- Có thể kết hợp broker **sau** outbox nếu nhu cầu scale tăng.

### 12.6. Decision

Chọn **Option C**. Producer ghi outbox row **trong cùng transaction** với order, worker xử lý sau commit. Không gửi SMTP trong transaction tạo order.

~~~text
POST /orders
    |
    v
BEGIN PostgreSQL transaction
    |
    +--> Insert order
    |
    +--> Insert mail_outbox(
    |      event_key, recipient, template,
    |      state=PENDING)
    |
    v
COMMIT
    |
    v
HTTP response (SMTP not awaited)

Separate worker:
    |
    v
Claim PENDING with lease
    |
    v
Build MIME and submit SMTP
    |
    v
Persist result ACCEPTED/RETRY/FAILED/UNKNOWN
~~~

### 12.7. Consequences

**Tích cực**

- Intent gửi gắn với business commit.
- Có khả năng phục hồi từ outbox sau restart.
- Có thể quan sát queue age và attempts.
- Worker có thể điều tiết throughput độc lập HTTP traffic.

**Tiêu cực**

- Email đến sau khi HTTP response, có eventual consistency.
- Phải vận hành job scheduler/worker và retry policy.
- Cần dọn dẹp outbox history, bảo vệ dữ liệu và tránh DB bloat.
- Cần reconciliation khi có kết quả SMTP không chắc chắn.

**Chưa chắc chắn**

- Throughput tối đa của claim/update trên DB.
- Phần trăm SMTP submissions rơi vào trạng thái UNKNOWN.
- Quota và deliverability thực tế của provider khi tăng tải.

### 12.8. Risks và mitigation

| Risk | Tác động | Mitigation | Residual |
| --- | --- | --- | --- |
| Worker crash trước send | Chậm thông báo | Lease expiry và claim lại | Delay |
| Worker crash sau SMTP accepted, trước DB commit | Gửi trùng nếu retry mù | Mark UNKNOWN/reconcile, trace attempt/provider | Không thể chứng minh exactly-once với SMTP thuần |
| DB outage | Producer không thể commit order/outbox | Xử lý theo failure policy, DB HA | Availability phụ thuộc DB |
| Mailbox quota bị throttle | Outbox backlog | Backoff, rate limiting, alert | Email chậm |
| Template/payload hết retention | Retry không build lại được | Immutable snapshot/reference và retention policy | Chi phí lưu trữ |
| Business event publish trùng | Gửi trùng | Unique business key theo recipient/operation | Cần định nghĩa key đúng |

### 12.9. Validation / acceptance

Không ghi “outbox chắc chắn không mất mail” mà không có test. Các điều kiện chấp nhận ví dụ:

1. Rollback tạo đơn → không có mail intent trong outbox.
2. Commit tạo đơn → outbox row tồn tại ngay cả khi SMTP offline.
3. Worker restart trước submission → intent vẫn còn và được claim lại.
4. Hai workers claim đồng thời → một row chỉ có một chủ sở hữu hợp lệ tại một thời điểm.
5. SMTP temporary failure → retry theo schedule, không hot loop.
6. SMTP timeout sau DATA → outcome không bị giả định chắc chắn FAILED.
7. Gửi thành công → lưu attempt/provider timestamp và correlation ID.
8. Queue age/throughput/failed/unknown hiện trên dashboard.
9. Content/template/attachment có thể được tái tạo đúng qua retry.
10. Security review xác nhận không log credential/PII ngoài phạm vi cho phép.

### 12.10. Revisit triggers

- Sustained queue age vượt business SLO dù đã điều chỉnh worker/DB hợp lý.
- Volume tăng làm outbox ảnh hưởng performance của transaction đơn hàng.
- Nhiều downstream services cần cùng notification event.
- Provider feedback/idempotency API cho phép mô hình submission khác tốt hơn.
- Thay đổi yêu cầu residency/retention khiến current storage không phù hợp.
- Số lượng UNKNOWN/duplicates vượt risk appetite đã chấp nhận.

Đây là một bản ADR có thể chuyển trực tiếp thành implementation tasks, tests và dashboards, thay vì một câu “dùng outbox vì best practice”.

## 13. Mã Spring minh họa quyết định ADR-001

ADR không thay code, nhưng ví dụ code giúp mô tả **ranh giới kiến trúc** được chọn.

### 13.1. Ghi business transaction và intent cùng nhau

~~~java
package com.example.orders;

import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final MailOutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orders,
            MailOutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public UUID createOrder(CreateOrderCommand command) {

        Order order = orders.create(command);

        outbox.insertOnce(new MailIntent(
                UUID.randomUUID(),
                command.tenantId(),
                "ORDER_CONFIRMED:" + order.id()
                    + ":" + command.recipientId(),
                command.recipientAddress(),
                "order-confirmation",
                order.id().toString()));

        return order.id();
    }
}
~~~

`OrderRepository`, `MailOutboxRepository`, `CreateOrderCommand` và `MailIntent` là **interfaces/models do ứng dụng định nghĩa**, không phải class built-in của Spring Mail. Điều cần thể hiện là `orders.create(...)` và `outbox.insertOnce(...)` dùng **cùng transaction manager/datasource**, và `insertOnce` có unique constraint thực theo business key.

### 13.2. Database schema minh hoạ

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    business_key VARCHAR(250) NOT NULL,
    recipient_address VARCHAR(320) NOT NULL,
    template_key VARCHAR(120) NOT NULL,
    template_version VARCHAR(80),
    payload_ref VARCHAR(500),
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claim_token UUID,
    lease_until TIMESTAMPTZ,
    last_error_code VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(tenant_id, business_key)
);

CREATE INDEX ix_mail_outbox_ready
    ON mail_outbox(status, next_attempt_at);
~~~

Schema là một mẫu mô tả ADR, không phải migration toàn diện. Với production còn cần attachment manifest, provider attempts, retention, claim owner, audit và data protection. Không biến recipient email thành metric tag hoặc log toàn bộ row để debug.

### 13.3. Claim ngắn, không giữ transaction qua SMTP

~~~sql
WITH selected AS (
  SELECT id
  FROM mail_outbox
  WHERE status IN ('PENDING', 'RETRY')
    AND next_attempt_at <= now()
  ORDER BY next_attempt_at, created_at, id
  FOR UPDATE SKIP LOCKED
  LIMIT 1
)
UPDATE mail_outbox AS m
SET status='PROCESSING',
    attempt_count=attempt_count+1,
    claim_token=:claim_token,
    lease_until=now() + INTERVAL '2 minutes',
    updated_at=now()
FROM selected
WHERE m.id=selected.id
RETURNING m.id, m.attempt_count,
          m.recipient_address, m.template_key,
          m.payload_ref;
~~~

Claim và insert attempt history (nếu có) phải commit trong một transaction ngắn. Sau đó worker gọi SMTP **ngoài transaction**, rồi persist outcome trong transaction khác với điều kiện claim token vẫn thuộc attempt hiện tại.

### 13.4. Vì sao không dùng `@Transactional` bao cả gửi SMTP?

~~~java
@Transactional
public void createAndSend(CreateOrderCommand cmd) {
    orders.create(cmd);
    mailSender.send(prepareMimeMessage(cmd));
}
~~~

Một database transaction không bao phủ việc gửi email qua mạng SMTP:

- SMTP có thể accepted rồi DB transaction rollback → thư đã gửi nhưng đơn hàng không tồn tại.
- DB connection/locks được giữ trong lúc network IO chậm.
- Exception hoặc timeout không cho biết chắc submission đã được accepted hay chưa.

ADR nên ghi rõ **transaction boundary**, không chỉ yêu cầu “gửi mail trong một hàm @Transactional”.

### 13.5. Retry và UNKNOWN cần decision phụ

Không mô tả toàn bộ reliability chỉ bằng một nhánh:

~~~java
catch (Exception ex) {
    scheduleRetry();
}
~~~

Một retry policy phải phân loại ít nhất:

~~~text
DEFINITE_RETRYABLE_FAILURE
DEFINITE_PERMANENT_FAILURE
UNKNOWN_SUBMISSION_OUTCOME
~~~

Nếu client mất kết nối sau SMTP DATA, không thể chứng minh email chưa được relay accepted. Retry hoặc fallback mù có thể gửi trùng. Vì vậy, ADR-001 nên liên kết một ADR khác định nghĩa chính sách `UNKNOWN`, duplicate tolerance và reconciliation.

## 14. ADR thứ hai: SMTP provider adapter và fallback

ADR về outbox xử lý **lưu ý định và lập lịch gửi**. Một quyết định riêng cần xử lý **chọn provider nào** và khi nào được chuyển sang provider dự phòng.

### 14.1. Bối cảnh

Hệ thống dùng SMTP provider A cho email giao dịch. Khi A outage, outbox backlog tăng. Nhóm cân nhắc thêm provider B để duy trì SLO. Tuy nhiên:

- Cần verify From domain, DKIM/SPF/DMARC, account và sender identity trên B.
- B có thể dùng region/log storage khác.
- SMTP không có key idempotency tiêu chuẩn chung như một số HTTP APIs.
- Một attempt trên A có thể ở trạng thái UNKNOWN sau timeout.
- Bounce/complaint từ A có thể đến sau khi đã chọn B cho email mới.

### 14.2. Các lựa chọn

| Option | Ý tưởng | Ưu | Rủi ro |
| --- | --- | --- | --- |
| A | Một provider, retry/backoff | Dễ vận hành, nhất quán identity | Single-provider outage |
| B | Hai provider, fallback sau mọi exception | Bảo vệ một số lỗi outage | Có thể gửi trùng nghiêm trọng |
| C | Hai provider, chỉ fallback khi có bằng chứng chưa accepted và B eligible | Cân bằng resilience và kiểm soát duplicate | Cần classifier/policy/ops |
| D | Dùng HTTP API có idempotency và status lookup cho tất cả | Có thể đối soát submission tốt hơn tùy API | Vendor lock-in, chi phí chuyển đổi |

### 14.3. Decision

Chọn **Option C** theo phạm vi email đã phê duyệt. Provider B chỉ là candidate nếu đủ điều kiện:

~~~text
tenant/region/category policy
AND sender identity verified
AND attachment/size capability
AND provider contract/quota
AND TLS/security requirements
AND feedback/bounce handling available
~~~

Sau attempt A:

~~~text
ACCEPTED
   -> stop submitting; await feedback

DEFINITE_REJECTED (retryable, before submission)
   -> may try approved B within attempts/deadline

DEFINITE_REJECTED (permanent/policy)
   -> do not blindly fallback

UNKNOWN
   -> hold/reconcile; never equate timeout with no submission
~~~

### 14.4. Giả thiết và evidence

| Giả thiết | Cách xác minh | Nếu sai |
| --- | --- | --- |
| B có sender identity và DKIM đúng | Test mailbox, kiểm tra auth results | Reject/spam/DMARC fail |
| B đủ quota khi A outage | Capacity test, contract | Secondary overload |
| Policy cho phép B xử lý region này | Security/legal approval | Vi phạm xử lý dữ liệu |
| Adapter phân loại pre-submission errors đủ tốt | SMTP fault injection | Duplicate nếu đánh nhầm |
| Có provider logs/feedback để điều tra UNKNOWN | Test incident workflow | Nhiều case cần manual handling |

### 14.5. Consequences

**Ưu điểm**

- Có thể chuyển delivery mới hoặc attempt thất bại trước submission sang secondary hợp lệ.
- Không buộc provider B xử lý email ngoài vùng/identity được phép.
- Có thể audit quyết định route/fallback.

**Nhược điểm**

- Phải quản lý hai sets of credentials/quotas/DNS/webhooks.
- Ghi provider ID và route-policy version theo attempt.
- Không bảo đảm tiếp tục tự động với mọi lỗi; `UNKNOWN` cần reconciliation.
- Tăng chi phí test deliverability và on-call.

### 14.6. Revisit triggers

- Provider B trở nên không phù hợp region/compliance.
- Quota B không đáp ứng tình huống outage.
- API/idempotency contract thay đổi.
- Duplicate email rate vượt mức rủi ro đã chấp nhận.
- Có nhu cầu per-recipient feedback mà SMTP A không cung cấp.

**Bài học:** ADR phải ghi không chỉ “có provider dự phòng”, mà cả **những tình huống bắt buộc không fallback**.

## 15. ADR thứ ba: render template và lưu snapshot của nội dung email

Một quyết định dễ bị bỏ qua là **thời điểm render** email và **nơi lưu dữ liệu đầu vào**. Nó ảnh hưởng trực tiếp tới tính nhất quán và khả năng retry.

### 15.1. Ba phương án

**Option A — Chỉ lưu template key và domain entity ID.**

~~~text
Outbox:
  orderId=O123
  templateKey=order-confirmation

At send:
  load order O123
  render current template
~~~

Ưu: ít lưu dữ liệu lặp; template luôn được cập nhật. Nhược: nếu order/template đổi giữa lần enqueue và lần gửi, nội dung có thể không còn phản ánh sự kiện ban đầu. Nếu entity bị xóa hoặc di chuyển, retry không còn đủ dữ liệu.

**Option B — Lưu immutable mail model snapshot và template version.**

~~~text
Outbox:
  deliveryId=D1
  templateKey=order-confirmation
  templateVersion=v12
  modelSnapshotRef=object://.../snapshot-v1

At send:
  load frozen model and template version
  render
~~~

Ưu: nội dung có thể tái tạo khi retry, không lệ thuộc entity hiện tại. Nhược: phải quản lý version template, storage, retention và PII.

**Option C — Render toàn bộ HTML/text/MIME tại enqueue.**

~~~text
Outbox:
  deliveryId=D1
  renderedHtmlRef=...
  renderedTextRef=...
  attachmentsRef=...
~~~

Ưu: nội dung được cố định; dễ xem dữ liệu dự định gửi. Nhược: tăng kích thước lưu trữ, có thể giữ thông tin đã hết hiệu lực, cần quản lý tài nguyên MIME/attachment và data deletion.

### 15.2. Một quyết định có điều kiện

Ví dụ có thể chọn **Option B** cho email hoá đơn cần audit, nhưng **Option A** cho một bản tin best-effort không cần giữ nội dung lịch sử. ADR nên ghi rõ phạm vi, không áp quy tắc duy nhất cho mọi loại mail.

| Loại email | Ưu tiên | Gợi ý để đánh giá |
| --- | --- | --- |
| Xác nhận giao dịch | Tái hiện trạng thái tại thời điểm event | Snapshot model + template version |
| Hoá đơn | Nội dung/khoản tiền chính xác, audit | Frozen payload/document version |
| OTP/reset password | Thời hạn, không giữ token quá lâu | Không log token; expiry và policy riêng |
| Marketing | Phân phối template phiên bản campaign | Campaign version, consent và suppression |
| Báo cáo định kỳ | Có thể tạo nội dung tại thời điểm gửi | Render-time data theo requirement |

### 15.3. Giả thiết cần ghi

- Template version v12 còn được truy xuất trong toàn bộ retry window.
- Model snapshot chứa đủ biến để render mà không truy cập domain entity đã thay đổi.
- Object storage giữ được attachment version hợp lệ trong thời hạn gửi.
- Nội dung nhạy cảm trong snapshot được bảo vệ và xóa đúng retention.
- Encoding `UTF-8` và locale/timezone không làm thay nội dung khi render lại.

### 15.4. Failure mode

~~~text
Order changed from "pending" to "cancelled"
       |
       v
Outbox created before cancellation
       |
       v
Worker renders using CURRENT order
       |
       v
Email may not describe original event
~~~

Ngược lại, nếu email bị hoãn vài ngày, nội dung snapshot cũng có thể **đã lỗi thời** (ví dụ mã OTP hết hạn). Vì vậy, ngoài snapshot cần một **business expiry** và state policy xác định khi nào không được gửi nữa.

### 15.5. Kết luận mẫu ADR-005

> Với email giao dịch cần tái tạo chính xác, lưu template ID/version và immutable model snapshot trong kho được kiểm soát; worker render dựa trên snapshot đó, không query lại entity tùy ý. Với email có token ngắn hạn, không giữ token ngoài thời hạn và dừng gửi khi hết hạn. Attachment reference được pin theo immutable version và có retention ít nhất đủ cho các attempts được phép.

**Rủi ro còn lại:** lưu snapshot có thể tăng chi phí và PII footprint. Cần encryption, authorization, retention, redaction và kiểm thử deletion. Những tradeoff này phải nằm trong ADR, không chỉ trong tài liệu vận hành storage.

## 16. Ghi rõ quyết định về SimpleMailMessage và MimeMessageHelper

Ngay cả một lựa chọn API trong Spring Mail cũng có thể ảnh hưởng contract.

### 16.1. Khi SimpleMailMessage đủ dùng

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("no-reply@example.com");
mail.setTo("recipient@example.net");
mail.setSubject("Thông báo");
mail.setText("Nội dung văn bản thuần.");
mailSender.send(mail);
~~~

`SimpleMailMessage` phù hợp với email plain text không cần HTML, inline resources hoặc attachments. Trong ADR, đây có thể là lựa chọn hợp lý nếu sản phẩm chỉ yêu cầu thông báo ngắn, không có template phức tạp.

### 16.2. Khi cần MimeMessageHelper

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage mime = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        mime,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("recipient@example.net");
helper.setSubject("Xác nhận");

helper.setText(
        "Thông tin xác nhận bằng văn bản.",
        "<html><body>"
            + "<p>Thông tin xác nhận</p>"
            + "<img src=\"cid:companyLogo\" alt=\"Logo\">"
            + "</body></html>");

helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");

mailSender.send(mime);
~~~

Với MIME, ADR cần cân nhắc:

- Plain text alternative và HTML có cùng ý nghĩa hay không.
- Inline image dùng Content-ID; local filesystem path trong HTML không được recipient truy cập.
- `MimeMessageHelper` multipart mode và encoding phù hợp.
- Attachment source có thể mở stream lại, còn tồn tại đến khi transport đọc.
- File/tài liệu nhạy cảm có được phép gửi trực tiếp không.
- Template, MIME size và khả năng hiển thị giữa mail clients.

### 16.3. Quyết định có thể là kiến trúc ở tầng model

Thay vì cho mọi service tự biết `MimeMessageHelper`, có thể quyết định dùng mail model trung gian:

~~~java
public record MailComposition(
        String recipient,
        String senderIdentityId,
        String subject,
        String plainText,
        String htmlText,
        java.util.List<InlineAssetRef> inlineAssets,
        java.util.List<AttachmentRef> attachments) {
}
~~~

`InlineAssetRef` và `AttachmentRef` là các kiểu ứng dụng tự định nghĩa, chứa resource IDs/versions đã được authorize; không nên giữ `InputStream` single-use hoặc file tạm theo HTTP request. Một mail composer/build layer sẽ chuyển model thành `MimeMessage`, còn provider adapter chịu trách nhiệm gửi.

Nếu sản phẩm có nhiều template và provider, lớp trung gian này giảm coupling nhưng tăng abstraction. ADR phải đánh giá liệu độ phức tạp ấy có cần thiết ở giai đoạn hiện tại hay không.

## 17. Quyết định về retry, dead letter và semantics của trạng thái

Một hệ thống mail thiếu định nghĩa trạng thái dễ phát sinh tranh luận vận hành:

> Email này ở `SENT`, vậy người nhận đã thấy chưa?

Không nhất thiết. Thường cần phân biệt:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +--> ACCEPTED (SMTP/API provider accepted submission)
   |
   +--> RETRY (definite failure, eligible for another attempt)
   |
   +--> FAILED (terminal; no automatic retry)
   |
   +--> UNKNOWN (provider may have accepted)
                 |
                 v
              RECONCILE
~~~

Email provider có thể phát thêm:

~~~text
ACCEPTED
   |
   +--> DEFERRED
   |
   +--> RECEIVER_ACCEPTED / DELIVERED (per provider definition)
   |
   +--> HARD_BOUNCE / COMPLAINT
~~~

### 17.1. Quyết định phải nói rõ “thành công” ở lớp nào

Một ADR có thể ghi:

> `ACCEPTED` là application-level observation rằng SMTP relay đã chấp nhận submission hoặc HTTP provider đã nhận request theo contract. Nó không bảo đảm inbox placement, đọc mail hay hoàn thành hành động của người dùng. Các sự kiện bounce/delivery feedback được lưu ở projection khác.

Không đồng nhất `MailException` với definite failure. Nếu lỗi xảy ra sau SMTP DATA hoặc HTTP POST đã tới provider, kết quả có thể `UNKNOWN`. Blind resend gây duplicate, nhất là khi switch provider.

### 17.2. Retry max attempts là một quyết định

Có thể lập bảng:

| Failure class | Xử lý | Lý do |
| --- | --- | --- |
| DNS/connect failure trước submission | Retry/backoff; fallback nếu eligible | Có thể chứng minh chưa accepted |
| Temporary rejection đã xác minh | Retry có giới hạn | Có cơ hội phục hồi |
| Permanent invalid recipient | FAILED/suppress theo policy | Đổi provider có thể không ích |
| Template validation | FAILED; sửa input/template | Retry liên tục không làm dữ liệu đúng |
| SMTP timeout sau DATA | UNKNOWN/reconcile | Có thể đã accepted |
| HTTP API idempotent POST timeout | Retry cùng key trong TTL hoặc lookup status | Theo hợp đồng provider cụ thể |
| Security content policy violation | Quarantine/FAILED | Không tự redrive |

### 17.3. Dead letter không phải một log

Nếu ADR ghi “email lỗi sẽ được đưa vào DLQ”, cần nêu **DLQ nằm ở đâu**, có durable hay không, có audit, retention và redrive process thế nào.

~~~text
Mail attempt fails permanently
        |
        v
BEGIN DB transaction
        |
        +--> mark delivery FAILED
        +--> insert dead_letter_event
        +--> update attempt outcome
        |
        v
COMMIT
        |
        v
Operator review/redrive (authorized)
~~~

Đặt tên một Spring Integration `DirectChannel` là `deadLetterChannel` không khiến message tự được lưu qua JVM restart. Nếu dùng RabbitMQ/Kafka, cần quyết định durability, ack/offset và retry/deduplication semantics.

### 17.4. Rủi ro lease và worker

Atomic claim/lease bảo vệ việc hai workers cùng sửa state, nhưng không tự ngăn duplicate side effect:

~~~text
Worker A starts SMTP
  |
  +-- lease expires while network is slow
             |
             v
Worker B reclaims and sends
             |
             v
A might also be accepted
~~~

ADR cần nêu timeout, heartbeat, fencing token, reclaim policy và cách xử lý attempts chưa rõ. Không ghi “exactly once” chỉ vì sử dụng `FOR UPDATE SKIP LOCKED`.

## 18. Quyết định về bảo mật và dữ liệu không thể “để sau”

Email có thể chứa địa chỉ liên lạc, thông tin đặt hàng, hoá đơn, tài liệu hoặc đường dẫn đổi mật khẩu. Quyết định kiến trúc có ảnh hưởng đến **data minimization, retention, access control, region và threat model**.

### 18.1. Các ràng buộc nên ghi

| Chủ đề | Ví dụ cần quyết định |
| --- | --- |
| Credential | Secret manager/runtime injection, rotation, no raw logs |
| Transport | SMTP STARTTLS/implicit TLS, hostname verification, timeout |
| Sender identity | Verified From, DKIM/SPF/DMARC, envelope MAIL FROM |
| Data residency | Approved provider/region, logs/backups/webhooks |
| PII | Data minimization, encrypted snapshot, retention/deletion |
| Attachments | Immutable reference, malware/size validation, tenant access |
| HTML | Contextual escaping, trusted template sources |
| Inbound webhook | Verify signature, replay protection, event dedupe |
| Operator actions | RBAC, redrive audit, suppression checks |
| Compliance | Policy source, owner, effective dates và exception approval |

### 18.2. ADR về dữ liệu phải phân biệt “must” và “nice to have”

Ví dụ:

~~~text
Must:
  EU-regulated payload is processed only through approved path.

Could:
  Prefer provider with lower average latency.
~~~

Không dùng score latency để vượt qua ràng buộc residency. Nếu provider dự phòng không đủ điều kiện, hệ thống phải giữ mail/HOLD và alert thay vì gửi trái chính sách.

### 18.3. Quyết định về raw logs

Thay vì:

~~~java
log.error("Failed to send message {}", mimeMessage, exception);
~~~

nên ưu tiên structured metadata:

~~~json
{
  "event": "mail.delivery.failure",
  "deliveryId": "opaque-delivery-id",
  "attemptId": "opaque-attempt-id",
  "providerGroup": "transactional-primary",
  "stage": "SMTP_DATA",
  "outcome": "UNKNOWN",
  "safeErrorCode": "SMTP_RESPONSE_TIMEOUT"
}
~~~

Không đưa raw subject, body, attachment bytes, access tokens hay recipient email vào metrics tags. Với log chi tiết phục vụ incident, phải có quyền truy cập, masking và retention được chấp thuận.

### 18.4. Một giả thiết về provider có thể là rủi ro tuân thủ

> A-08: “Nhà cung cấp B đặt SMTP endpoint trong EU nên toàn bộ dữ liệu được xử lý ở EU.”

Đây **không phải kết luận an toàn**: endpoint location có thể khác nơi logs, backups, support tools hoặc webhooks được xử lý. Phải xác minh hợp đồng và data flow thực tế, không suy từ tên miền `eu-...`.

### 18.5. Quản lý ngoại lệ chính sách

Nếu một team đề xuất gửi tài liệu có PII qua provider chưa được duyệt để giảm latency, đó không chỉ là tradeoff kỹ thuật. Cần:

~~~text
Policy requirement
     |
     v
Provider eligibility review
     |
     +--> Compliant -> candidate
     |
     +--> Not compliant -> reject
     |
     +--> Exception request -> authorized risk owner review
~~~

ADR có thể tham chiếu một **exception record được phê duyệt**, thời hạn và phạm vi. Nó không tự thay thế quyết định của người có thẩm quyền. Một comment “security agreed” không đủ khi không có bằng chứng hoặc phạm vi.

## 19. Kiểm chứng quyết định bằng experiment và fault injection

Một ADR dễ bị biến thành tranh luận ý kiến nếu không gắn với cách kiểm chứng. Với Spring Mail, các failure windows quan trọng thường **không xuất hiện trong happy-path demo**, nên nên đưa chúng thành kịch bản thử nghiệm.

### 19.1. Thí nghiệm cho synchronous vs outbox

| Thí nghiệm | Thiết lập | Dữ liệu cần lấy |
| --- | --- | --- |
| SMTP relay offline | Tắt fake SMTP trước khi tạo order | Order commit? Outbox tồn tại? HTTP behavior? |
| SMTP chậm | Delay response 15 giây | HTTP p95, worker latency, queue age |
| Producer crash | Kill sau DB commit | Mail intent có còn không? |
| Worker crash | Kill sau claim, trước send | Lease/reclaim, history, không mất intent |
| SMTP response lost | Cắt kết nối sau DATA | Outcome UNKNOWN, chính sách không blind retry |
| DB outcome update fail | Relay accepted, DB fail | Reconciliation/duplicate risk |
| Burst traffic | Mô phỏng giờ cao điểm | DB contention, throughput, SLO |

Test chỉ dùng Spring MockMvc không đủ để chứng minh SMTP protocol semantics. Có thể sử dụng SMTP test server có programmable responses, Postgres Testcontainers và fault injection ở các ranh giới phù hợp.

### 19.2. Thí nghiệm cho template và attachment

~~~text
Create mail intent with:
  templateVersion = v12
  attachmentVersion = object-v3

Then:
  deploy template v13
  update original document to object-v4
  restart worker
  retry delivery

Observe:
  Is MIME content still v12 + object-v3?
~~~

Nếu ADR quyết định snapshot nhưng test cho ra nội dung mới, implementation đã không thực hiện đúng quyết định.

### 19.3. Thí nghiệm cho multi-provider fallback

- A connect-refused trước submission; B đủ điều kiện → có thể chọn B.
- A timeout sau DATA; B đủ điều kiện → không auto fallback, chuyển UNKNOWN.
- A trả recipient permanent rejection → không retry B chỉ để lách lỗi.
- B chưa verify sending domain → không đưa B vào candidate set.
- B ngoài approved region → fail-closed dù A outage.
- A đã accepted, feedback chưa về → không submit B.
- B webhook đến trễ sau failback → vẫn correlate đúng attempt B.

### 19.4. Đặt tiêu chí pass/fail trước khi chạy experiment

Không nên benchmark rồi chọn ngưỡng sau khi nhìn kết quả để tuyên bố đã đạt. Với mỗi acceptance test:

~~~text
Experiment ID: EXP-MAIL-07
Hypothesis: Outbox survives a worker crash
Input: 100 test deliveries, 1 worker killed after claim
Expected: 100 durable intents remain accounted for;
          none silently disappear
Observed: [filled after test]
Status: PASS / FAIL / INCONCLUSIVE
Environment: [DB version, SMTP fake, build, date]
Evidence: [link to test/artifact]
~~~

Đây chỉ là ví dụ thông số test. Với production, định nghĩa metric “accounted for” rõ hơn, ví dụ trong `PENDING/RETRY/PROCESSING/ACCEPTED/FAILED/UNKNOWN`, và phân biệt số **business intents** với số **SMTP submissions**. Không hứa exactly-once delivery chỉ dựa vào số row outbox.

### 19.5. Độ tin cậy của bằng chứng

| Bằng chứng | Có thể khẳng định | Chưa thể khẳng định |
| --- | --- | --- |
| Unit test planner | Quy tắc chọn fallback theo input đã giả lập | SMTP provider thật sẽ phản hồi y như giả lập |
| Testcontainers PostgreSQL | Row locking/constraint/migration trong môi trường test | DB production dưới peak load giống test |
| Fake SMTP | MIME và một số failure modes khi gửi | Deliverability/inbox placement trên mọi provider |
| Vendor staging | Contract và giới hạn môi trường staging | Production account có quota/reputation y hệt |
| Production metrics | Hành vi thực trong khoảng đo | Nguyên nhân hay tính phổ quát của mọi incident |
| Vendor SLA/contract | Những điều provider cam kết | Không bao giờ xảy ra outage hoặc duplicate |

Khi ghi ADR, nên nói cụ thể “đã chứng minh trong điều kiện nào” thay vì “đã test rồi”.

## 20. Quy trình ra quyết định và phê duyệt

Một ADR là công cụ giúp nhóm thảo luận và giữ lịch sử; quy trình không cần nặng nhưng phải có owner rõ.

### 20.1. Vòng đời gợi ý

~~~text
Trigger: issue / incident / requirement
              |
              v
Architecture owner drafts ADR
              |
              v
List constraints, assumptions, options
              |
              v
Collect evidence / prototype
              |
              v
Review by affected teams
              |
        +-----+------+
        |            |
        v            v
     Accepted      Rework/reject
        |
        v
Link implementation PR/migrations
        |
        v
Deploy with telemetry/rollback
        |
        v
Record observed consequences
        |
        v
Revisit when trigger occurs
~~~

### 20.2. Ai cần tham gia?

| Loại quyết định | Nhóm tham gia thường cần |
| --- | --- |
| SMTP integration/API contract | Backend, integration, platform |
| Outbox/DB schema | Service owner, DBA/platform, SRE |
| OAuth/credentials/TLS | Security, platform |
| Provider/region/data retention | Legal/compliance, security, vendor owner |
| Marketing consent/suppression | Product, compliance, marketing operations |
| OTP/security latency | Identity/security, product, on-call |
| Attachment storage | Backend, storage, security |
| On-call/runbook | Operations/SRE, service owner |

Không cần mọi nhóm duyệt mọi thay đổi nhỏ. Nhưng nếu lựa chọn làm thay đổi nghĩa vụ tuân thủ, retry side effect hoặc vùng xử lý dữ liệu, hãy có đúng owner tham gia trước khi `Accepted`.

### 20.3. Phân biệt người đề xuất, người quyết định và người triển khai

~~~text
Proposer: đề xuất vấn đề và các phương án
Decider: chấp nhận lựa chọn theo quyền hạn
Implementer: thực hiện theo ADR
Reviewer: xác minh requirement/risk liên quan
Operator: vận hành và cung cấp phản hồi production
~~~

Một người có thể giữ nhiều vai trò trong team nhỏ. Nhưng cần ít nhất biết ai chịu trách nhiệm **cập nhật ADR khi giả thiết bị phá vỡ** và ai có quyền chấp nhận residual risk.

### 20.4. Decision time-boxing

Một nhóm có thể trì hoãn mãi vì thiếu thông tin. ADR nên cho phép:

> Chọn phương án C trong 90 ngày với giới hạn 2 worker và chỉ một provider, sau đó đo queue age và throughput. Nếu không đạt SLO hoặc provider đưa ra API idempotency tốt hơn, mở lại quyết định.

Đây là **quyết định có thời hạn và phạm vi**, không phải “chốt vĩnh viễn”.

### 20.5. Record những gì bị hoãn

Ví dụ:

~~~text
Decided now:
  PostgreSQL outbox + one SMTP provider.

Deferred:
  Multi-region active-active mail dispatch.
  Provider B automatic failover.
  Tenant-specific branding portal.

Revisit:
  After peak load test or confirmed SLA requirement.
~~~

Hoãn một lựa chọn không phải bỏ qua nó; ghi **lý do chưa thực hiện và trigger** để ngăn thiết kế overengineering hoặc thiếu kế hoạch.

## 21. Quản lý thay đổi và supersede ADR

Một quyết định đúng năm trước có thể không còn phù hợp sau khi:

- Tăng số lượng email/tenant.
- Chuyển provider, region hoặc SMTP account.
- Bổ sung email dạng MIME, attachments, inbound mail.
- Thay đổi yêu cầu bảo mật/retention.
- Xảy ra incident không được dự báo.
- Spring Boot/Spring Mail/Jakarta Mail dependency thay đổi hành vi hỗ trợ.

### 21.1. Không sửa lịch sử để làm như chưa từng quyết định

Tránh:

~~~text
ADR-001 in 2025:
  "Use synchronous send"

In 2026, edit same ADR to:
  "Use outbox"
~~~

Người đọc sẽ không biết hệ thống từng dùng sync send và vì sao nó bị thay. Thay vào đó:

~~~text
ADR-001 (SUPERSEDED)
  Use synchronous mail send.
  Superseded by ADR-014.

ADR-014 (ACCEPTED)
  Use transactional outbox for transactional email.
  Supersedes ADR-001.
  Rationale: failures/latency requirements changed.
~~~

Có thể thêm một ghi chú hậu kiểm vào ADR-001, nhưng giữ nguyên context và rationale gốc.

### 21.2. Decision drift: code và ADR không còn khớp

Ví dụ ADR nói:

> Mọi attempt UNKNOWN phải được giữ lại để reconciliation.

Nhưng một PR thêm:

~~~java
catch (MailSendException ex) {
    retryImmediately();
}
~~~

Đây là **decision drift**. Code hiện tại có thể vi phạm policy chống duplicate của ADR. Review nên:

- Chỉ ra ADR bị ảnh hưởng.
- Kiểm tra thay đổi có phải bug fix hay một quyết định mới.
- Nếu quyết định thay đổi, cập nhật/supersede ADR có approval.
- Nếu code sai, sửa implementation theo quyết định đã được chấp thuận.

Không yêu cầu ADR phải mô tả mọi dòng code; chỉ cần các bất biến quan trọng, contract và failure semantics còn đúng.

### 21.3. Liên kết incident với reevaluation

Ví dụ:

~~~text
Incident INC-42:
  SMTP relay accepted message
  DB markSent failed
  worker retried and duplicated confirmation
            |
            v
ADR-003 assumption invalidated:
  "send failure always means not accepted"
            |
            v
New ADR-016:
  introduce UNKNOWN + reconciliation
~~~

Một postmortem nên làm rõ **giả thiết nào sai hoặc chưa được ghi** và quyết định nào cần thay đổi, thay vì chỉ gán nguyên nhân cho một dòng code.

### 21.4. Thời gian đánh giá lại

Có thể thêm:

~~~text
NextReviewDate: 2027-02-01
ReviewOwner: Messaging Platform
RevisitTrigger:
  - p99 queue age exceeds business SLO
  - SMTP provider increases rejection rate
  - regional data policy changes
  - new provider API offers status reconciliation
~~~

Ngày review là lịch quản trị nội bộ, không phải yêu cầu của Spring. Revisit trigger dựa trên **metric/condition** thường hữu ích hơn việc chờ một ngày cố định.

## 22. Kết nối quyết định kiến trúc với bản đồ phụ thuộc

Một quyết định mail có thể ảnh hưởng nhiều service và tài nguyên ngoài code. Nếu chỉ ghi component Spring mà không ghi **data flow và ownership**, migration dễ bỏ sót một ranh giới quan trọng.

### 22.1. Ví dụ bản đồ phụ thuộc

~~~text
Order Service
    |
    | transaction: create order + mail intent
    v
PostgreSQL Outbox
    |
    v
Mail Dispatch Worker
    |
    +--> Template Repository
    |       +--> template version
    |
    +--> Asset Storage
    |       +--> inline images
    |       +--> attachments
    |
    +--> Credential Provider
    |       +--> SMTP secret / API token
    |
    +--> JavaMailSender / Provider Adapter
            |
            v
       SMTP / HTTP provider
            |
            +--> Bounce mailbox
            +--> Feedback webhook
                      |
                      v
               Delivery event store
                      |
                      v
              Central suppression
~~~

Một ADR về provider fallback có thể yêu cầu thay đổi cả DNS, credential, SPF/DKIM, webhook authentication và suppression, không chỉ đổi host trong `spring.mail.host`.

### 22.2. Thứ cần ghi vào impact analysis

| Bề mặt | Câu hỏi |
| --- | --- |
| Business semantics | Ai tạo intent? Cùng sự kiện có thể tạo bao nhiêu email hợp lệ? |
| Storage | Bảng nào, unique constraints, retention, backup và migration? |
| API | HTTP/gateway trả kết quả gì khi SMTP không khả dụng? |
| Background processing | Scheduler/worker, lease, concurrency, retry ownership? |
| Provider | Account, quota, credentials, APIs, feedback? |
| Sender identity | From, Reply-To, envelope sender, DNS authentication? |
| Template | Versioning, encoding, HTML/text, inline images? |
| Attachment | Immutable bytes, access control, size, cleanup? |
| Security/compliance | Region, logs, data deletion, audit, access? |
| Observability | Dashboards, metrics, alerts, runbooks? |
| Testing | Protocol faults, crash windows, duplicate prevention? |
| Rollout/rollback | Canary scope, feature flags, data compatibility? |

### 22.3. Decision boundary cũng là ownership boundary

Ví dụ:

~~~text
Order service:
  responsible for creating correct intent once

Mail worker:
  responsible for scheduling and submitting intent

Provider adapter:
  responsible for transport-specific conversion/outcome

Feedback handler:
  responsible for validating and normalizing provider events

Operations:
  responsible for triage/redrive under policy
~~~

Nếu không biết ai sở hữu `UNKNOWN` khi provider timeout, dễ xảy ra tình huống service A nghĩ service B sẽ retry, còn B nghĩ email đã được xử lý. ADR nên có **một owner cho mỗi trạng thái cần hành động**, không chỉ một owner cho toàn bộ codebase.

## 23. Đưa ADR vào pull request và quy trình phát hành

Một thay đổi kiến trúc tốt nên để lại dấu vết từ quyết định tới code.

### 23.1. Ví dụ PR description

~~~markdown
## What changed
- Added mail_outbox schema and indexes.
- Introduced worker claim and attempt state.
- Replaced synchronous send in order request.

## Architecture decisions
- Implements ADR-001.
- Relies on ADR-003 for UNKNOWN handling.

## Assumptions
- A-01: Existing PostgreSQL can support peak mail workload.
- A-04: Attachment snapshot retained for retry window.

## Evidence
- Test: business rollback does not create outbox intent.
- Test: worker restart resumes durable pending rows.
- Test: SMTP after-DATA timeout is UNKNOWN.

## Rollout
- Feature flag enabled for internal canary.
- Monitor queue age, error rate, duplicate incidents.
- Rollback procedure documented.
~~~

Đây là nội dung mẫu. Khi áp dụng, những mục `Test` phải được thay bằng link test/evidence thật; không ghi PASS nếu chưa chạy.

### 23.2. Implementation checklist khác acceptance evidence

`Checklist`:

- Có migration cho bảng outbox.
- Có worker đọc row pending.
- Có timeouts và structured logs.

`Bằng chứng`:

- Migration áp dụng thành công trên môi trường kiểm thử.
- Worker chịu được fault injection đã định.
- Queue age dưới ngưỡng được phê duyệt khi load test.

“Đã viết code” không đồng nghĩa “giả thiết đã được kiểm chứng”. Nên ghi cả hai một cách riêng biệt.

### 23.3. Feature flag và shadow mode

Khi chuyển từ đồng bộ sang outbox, có thể dùng feature flag để triển khai theo nhóm nhỏ. Cẩn trọng với **shadow mode**:

~~~text
Old path: synchronous SMTP sends
New path: outbox worker also sends
             |
             v
      Duplicate emails!
~~~

Shadow mode an toàn có thể chỉ ghi intent và kiểm tra dữ liệu/latency **mà không submit SMTP**, hoặc gửi tới một test sink cô lập. Không để cả hai đường cùng thực hiện side effect cho recipient thật.

### 23.4. Rollback phải dựa trên trạng thái

Nếu rollout outbox đã tạo hàng nghìn intent `PENDING`, việc tắt worker rồi bật lại gửi đồng bộ có thể để lại backlog. Nếu worker sau đó được bật lại, cùng sự kiện có thể gửi trùng.

Một rollback plan cần nêu:

1. Feature flag áp dụng cho **delivery mới** ra sao.
2. Những intent đã tạo theo đường mới tiếp tục được xử lý hay cần migrate.
3. Cách chống một business event đi cả hai đường.
4. Có thể rollback schema mà không xóa mail intents chưa xử lý hay không.
5. Ai quyết định redrive những delivery trạng thái UNKNOWN.

### 23.5. Migrate mà không làm mất audit

Nếu thay provider A bằng B, cần giữ:

- Provider ID của mỗi attempt.
- Provider message ID/feedback reference nếu có.
- Route policy version và selection reason.
- Webhook/bounce ingestion của A cho các message đã accepted.
- Suppression records cần áp dụng xuyên provider.

ADR về migration phải nói rõ retention của các luồng cũ, không chỉ “đổi cấu hình sang B”.

## 24. Những quyết định nên tách ra thay vì ghi trong một ADR khổng lồ

Một ADR quá lớn rất khó supersede từng phần. Có thể tách theo **trách nhiệm và chu kỳ thay đổi**.

| ADR | Câu hỏi cần quyết | Có thể thay đổi độc lập? |
| --- | --- | --- |
| ADR-001: Outbox | Khi nào intent được ghi bền vững? | Có |
| ADR-002: MIME composition | API nào tạo HTML/inline/attachment? | Có |
| ADR-003: Outcome semantics | Khi nào ACCEPTED/UNKNOWN/FAILED? | Có |
| ADR-004: Retry and dead letter | Ai lên lịch retry và redrive? | Có |
| ADR-005: Template snapshot | Nội dung nào được freeze ở thời điểm nào? | Có |
| ADR-006: Provider abstraction | Interface nào che SMTP/HTTP API? | Có |
| ADR-007: Fallback policy | Khi nào chuyển nhà cung cấp là an toàn? | Có |
| ADR-008: Feedback processing | Correlate bounce/complaint bằng gì? | Có |
| ADR-009: Security/data residency | Provider/asset nào đủ điều kiện? | Có |

Không cần tách thành chín ADR nếu ứng dụng cực nhỏ. Nguyên tắc là: **một ADR nên có một lựa chọn trung tâm**, có thể đổi mà không làm mất toàn bộ bối cảnh các lựa chọn khác.

### 24.1. Phụ thuộc giữa các quyết định

Ví dụ:

~~~text
ADR-001 (Outbox)
    |
    +--> ADR-003 (Outcome semantics)
    |       |
    |       +--> ADR-004 (Retry policy)
    |       +--> ADR-007 (Fallback policy)
    |
    +--> ADR-005 (Template snapshot)
    |
    +--> ADR-008 (Feedback processing)
~~~

Một PR thay đổi `UNKNOWN` cần xem cả retry/fallback behavior. Một ADR phụ thuộc không có nghĩa mọi quyết định phải chấp thuận cùng ngày; có thể ghi dependency và những hạn chế tạm thời.

### 24.2. Trường hợp nhiều ADR mâu thuẫn

Ví dụ:

~~~text
ADR-003: UNKNOWN must not be automatically resent.
ADR-007: Any SMTP error triggers fallback to provider B.
~~~

Hai quyết định này mâu thuẫn. Cần sửa/supersede một trong hai, xác định scope và ưu tiên. Không để developer tự chọn ADR nào “có vẻ mới hơn” dựa vào tên file. Một index có status, superseded links và reviewer owner giúp giảm mâu thuẫn.

## 25. Review một ADR qua những câu hỏi cụ thể

Thay vì chỉ hỏi “ai có ý kiến gì?”, có thể review bằng các câu hỏi gắn với **tính đúng đắn và vận hành**.

### 25.1. Về mục tiêu và phạm vi

- Quyết định giải quyết vấn đề thật hay chỉ thêm abstraction?
- Những loại mail nào thuộc phạm vi và loại nào không?
- Có business SLO/retention/deadline cụ thể không?
- Có nêu điều gì **không được bảo đảm**, ví dụ inbox placement hoặc exactly-once?

### 25.2. Về phương án thay thế

- Có ít nhất một lựa chọn đơn giản hơn không?
- Có lựa chọn sử dụng hạ tầng hiện tại không?
- Có xét provider/SDK/API vs SMTP phù hợp?
- Có viết những trường hợp lựa chọn không được chọn sẽ tốt hơn?
- Có nói chi phí migration/rollback không?

### 25.3. Về giả thiết

- Giả thiết nào nếu sai có thể làm thay đổi quyết định?
- Ai chịu trách nhiệm kiểm chứng chúng?
- Đã có benchmark/test/contract hay chỉ là suy đoán?
- Điều gì làm bằng chứng cũ hết hiệu lực?
- Có điều kiện hủy bỏ quyết định nếu giả thiết quan trọng bị bác bỏ không?

### 25.4. Về tính đúng đắn của mail flow

- Đã phân biệt business intent với SMTP submission chưa?
- Có thể gửi trùng sau crash/timeout không?
- Khi SMTP accepted nhưng state commit thất bại sẽ làm gì?
- Email bị suppress, token hết hạn hoặc attachment mất thì xử lý thế nào?
- Mail client hiển thị HTML/inline image khác nhau có thuộc phạm vi không?
- Có cách đối soát bounce/complaint và feedback không?

### 25.5. Về bảo mật

- Secrets đến từ đâu và được rotate thế nào?
- Sender identity có được verify trên mọi eligible provider?
- Nội dung mail và attachment có rời khỏi region cho phép không?
- Log/DLQ/outbox có lưu PII quá mức không?
- Manual redrive cần quyền gì và có audit không?

### 25.6. Về vận hành

- Ai nhận alert queue backlog?
- Metrics nào chứng minh quyết định đáp ứng SLO?
- Có runbook cho provider outage và UNKNOWN không?
- Có thể rollback mà không mất mail intent không?
- Khi nào phải viết ADR mới thay vì sửa code âm thầm?

## 26. Runbook: giả thiết kiến trúc bị phá vỡ trong production

ADR không phải tài liệu để đọc một lần rồi bỏ. Khi hệ thống gặp incident, nó có thể trở thành điểm nối giữa **triệu chứng**, **giả thiết ban đầu** và **quyết định cần thay**.

### 26.1. Ví dụ: queue age tăng đột ngột

Triệu chứng:

~~~text
PENDING mail intents: increasing
Oldest due age: 40 minutes
Worker process: running
SMTP response time: elevated
HTTP order requests: mostly healthy
~~~

Quyết định hiện tại: PostgreSQL outbox + SMTP worker.

Giả thiết bị nghi ngờ:

> A-01: Worker/DB/SMTP capacity đủ để xử lý peak traffic trong SLO.

Các bước:

1. Kiểm tra mail category, số lượng intents và `next_attempt_at`.
2. Tách backlog do DB contention, worker ít, SMTP throttle, network hay template build.
3. Xem metrics `inflight`, provider 4xx/5xx, queue age và worker crash.
4. Kiểm tra retry storm/backoff và những attempt UNKNOWN cần hold.
5. Đo trước khi tăng số worker; tăng concurrency có thể làm quota SMTP tệ hơn.
6. Nếu giả thiết capacity sai, cập nhật evidence và mở lại ADR về worker/broker/provider.
7. Trước khi đổi phương án, ghi rollout/rollback và rủi ro mất/duplicate mail.

Không kết luận “PostgreSQL outbox không scale” chỉ vì backlog tăng khi SMTP provider đang rate limit.

### 26.2. Ví dụ: gửi trùng email sau restart

Triệu chứng:

~~~text
Mail D1:
  attempt #1 -> provider accepted?
  worker crashed before state update
  attempt #2 -> SMTP accepted
  recipient reports two copies
~~~

Giả thiết sai:

> Mọi exception hoặc missing state đồng nghĩa provider chưa accepted.

Các bước:

1. Xác định delivery ID, attempt IDs, SMTP/provider logs, timestamps.
2. Kiểm tra kết quả có phải `UNKNOWN` và tại sao bị schedule retry.
3. Xem lease expiry/reclaim và thời gian SMTP timeout.
4. Tách lỗi claim concurrency khỏi lỗi side-effect idempotency.
5. Ghi residual risk: SMTP thuần có thể không có dedupe guarantee.
6. Cập nhật ADR outcome semantics và fallback/reconciliation.
7. Thêm fault-injection test cho crash sau DATA/accepted.

Không viết lại lịch sử thành “đã có exactly-once”; đó là cam kết không được bảo đảm chỉ bởi transaction/unique constraint trong database.

### 26.3. Ví dụ: migration provider B làm bounce tăng

Triệu chứng:

~~~text
Provider B acceptance: high
Hard bounce / complaint: rising
Delivery feedback: incomplete
~~~

Giả thiết bị kiểm tra:

- Sender identity/DKIM/DMARC của B đủ tốt.
- B webhook luôn map được về delivery.
- Central suppression có hiệu lực trên cả A/B.

Các bước:

1. Xác minh DNS/authentication và sender identity.
2. Phân biệt provider accepted với recipient-server delivered.
3. Kiểm tra event signature, correlation và event lag.
4. Xem suppression, consent và category routing.
5. Giảm canary/rollback **cho delivery mới**.
6. Giữ feedback ingestion của B cho những email đã accepted.
7. Đánh giá lại ADR provider fallback/migration với evidence mới.

### 26.4. Lưu bản ghi reevaluation

~~~markdown
## Review record — 2026-11-12 (example)

ADR: ADR-001
Trigger: Oldest due queue age exceeded defined SLO
Observed evidence: [dashboard link / test IDs]
Assumption affected: A-01 (capacity)
Finding: [validated / invalidated / still inconclusive]
Decision: [keep / amend scope / open new ADR]
Owner: Messaging team
Follow-up issue: [link]
~~~

Không cần sửa decision text gốc nếu lựa chọn chưa thay đổi. Thêm review note có liên kết và tạo ADR mới khi quyết định thay thế một phần đáng kể.

## 27. Những lỗi phổ biến khi ghi quyết định kiến trúc

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ ghi lựa chọn cuối | Không biết vì sao đã chọn | Ghi context, drivers, alternatives, rationale |
| Không ghi giả thiết | Sai sau khi workload/provider đổi | Assumption register + revisit triggers |
| Coi giả thiết là sự thật | Overpromise về SMTP latency/delivery | Gắn confidence và evidence |
| Không nêu phạm vi | Áp policy marketing cho OTP | Scope theo mail type, tenant/region |
| Không ghi phương án đơn giản hơn | Overengineering | So sync, async, DB outbox, broker công bằng |
| Nói “outbox bảo đảm exactly once” | Hiểu sai rủi ro duplicate | Phân biệt durable intent và SMTP acceptance |
| Coi `SENT` là inbox delivered | KPI/delivery report sai | Định nghĩa submission/feedback stages |
| Gửi B sau mọi exception ở A | Gửi trùng sau unknown | Fallback chỉ khi điều kiện cho phép |
| Không ghi security constraints | Chọn sai provider/region | Đặt non-negotiables trước scoring |
| Chấm điểm nhưng không có nguồn | Điểm chủ quan giả chính xác | Evidence và sensitivity analysis |
| Bỏ qua negative consequences | Nhóm sau không biết nợ vận hành | Ghi tradeoffs/cost/owner |
| Không có acceptance criteria | Quyết định không thể kiểm tra | Test/metric rõ từ trước |
| “Đã test” mà không có môi trường | Không tái lập kết luận | Ghi workload/build/provider/test scope |
| Chỉ lưu trong chat/meeting | Rationale dễ thất lạc | ADR version-controlled, linked PR |
| Một ADR chứa 10 quyết định độc lập | Khó thay/supersede từng phần | Chia theo decision boundary |
| Edit ADR cũ thành lựa chọn mới | Mất lịch sử | New ADR supersedes old |
| Không ghi owner | Không ai cập nhật giả thiết | Decision/review owner rõ |
| Không liên kết incident | Lặp lại lỗi đã biết | Trace incident → assumption → ADR |
| Rollback chỉ xét code | Còn mail intents/backlog/provider feedback | Rollback plan bao gồm data/state |
| Chỉ benchmark happy path | Bỏ qua crash/unknown/duplicate | Fault-injection acceptance tests |
| Dùng tên `errorChannel` là đã có DLQ | Mất lỗi khi JVM restart | Ghi cơ chế durable disposition |
| Quên attachment lifecycle | Retry không còn file | Immutable reference/retention |
| Không xem xét template versioning | Email retry ra nội dung khác | Snapshot/version decision |
| Quyết định dựa vào giá per-email | Tốn chi phí ops/deliverability | Total cost/risk model |
| Chỉ ghi ngày review, không có trigger | Bỏ lỡ thay đổi lớn giữa chu kỳ | Trigger theo SLO/quota/provider/incident |
| PR thay semantics mà không xem ADR | Decision drift | ADR link trong review |

### 27.1. Viết ADR không có nghĩa code phải phức tạp

Một ADR có thể kết luận:

> Trong 6 tháng đầu, giữ một provider SMTP và `JavaMailSender` đơn giản; không thêm adapter registry vì chưa có provider thứ hai. Ghi rủi ro vendor outage, theo dõi delivery SLO, và revisit khi hợp đồng yêu cầu failover hoặc observed downtime vượt ngưỡng.

Đây có thể là một quyết định có trách nhiệm nếu phù hợp workload và risk appetite. “Không thêm abstraction” vẫn là một quyết định đáng lưu khi có lý do.

### 27.2. Ghi “chưa quyết định” khác với im lặng

Ví dụ:

~~~text
Decision:
  Use DB outbox for transactional emails.

Not decided yet:
  Whether marketing mail needs separate provider.

Assumption:
  Campaign volume below current account quota.

Trigger:
  First marketing peak load test or confirmed volume forecast.
~~~

Nội dung này giúp người khác hiểu **ranh giới quyết định**, tránh tự suy rằng mọi email đều phải dùng cùng provider.

## 28. Câu hỏi thường gặp

**“ADR có phải tài liệu thiết kế chi tiết không?”**  
Không. ADR lưu **lý do lựa chọn và hệ quả**. Design document có thể mô tả mọi API, schema và sequence diagram. Hai loại tài liệu liên kết với nhau; ADR không cần copy toàn bộ code.

**“Spring Framework Mail có cung cấp ADR format chuẩn không?”**  
Không. ADR là phương pháp ghi quyết định kiến trúc do nhóm áp dụng. Spring Mail cung cấp API như `JavaMailSender`, `MimeMessageHelper`, còn nhóm chọn format phù hợp để ghi rationale.

**“Có bắt buộc mỗi feature tạo ADR?”**  
Không. Ưu tiên những lựa chọn khó đảo ngược, ảnh hưởng cross-team, reliability, security/compliance hoặc cost. Một bug fix nhỏ có thể chỉ cần PR.

**“Điều gì khác giữa decision và assumption?”**  
Decision là **lựa chọn của nhóm**; assumption là **điều tạm coi là đúng**. Chọn outbox là decision; PostgreSQL còn đủ capacity cho peak traffic là assumption cần chứng minh.

**“Nếu giả thiết đã được validate thì còn phải lưu không?”**  
Có ích, vì evidence có phạm vi: phiên bản code, môi trường, workload, thời điểm. Khi điều kiện thay đổi, evidence có thể hết hiệu lực.

**“Có cần ghi phương án không chọn không?”**  
Có. Chúng giải thích tradeoff và giúp tránh đề xuất lại cùng lựa chọn mà không có bối cảnh. Trình bày công bằng, không biến phương án không chọn thành caricature.

**“Nếu một phương án không đạt ràng buộc bảo mật thì có đưa vào bảng điểm?”**  
Có thể liệt kê như lựa chọn bị loại, nhưng không nên cho điểm cao ở các tiêu chí khác để bù một ràng buộc bắt buộc. Filter eligibility trước khi weighted scoring.

**“Ma trận điểm có bắt buộc không?”**  
Không. Với quyết định rõ ràng, một rationale định tính đủ tốt có thể hữu ích hơn một bảng số điểm chủ quan. Nếu dùng ma trận, ghi nguồn, trọng số, confidence và sensitivity.

**“Có nên đặt ADR ở wiki hay repository?”**  
Cả hai có thể phù hợp. Repo có lợi cho version control và PR review; wiki tiện cross-team. Quan trọng là ID/link ổn định, dễ tìm, có owner/status/superseded record.

**“Một ADR đã Accepted có nghĩa code đã deploy?”**  
Không nhất thiết. `Accepted` nghĩa lựa chọn đã được chấp thuận; triển khai và deployment có thể diễn ra sau. Có thể dùng status `Implemented` hoặc liên kết PR/release.

**“Khi thay quyết định nên sửa ADR cũ hay tạo mới?”**  
Nếu lựa chọn chính thay đổi, tạo ADR mới và link supersedes. Nếu chỉ cập nhật evidence/clarification mà quyết định giữ nguyên, có thể thêm review note theo quy ước.

**“Có nên ghi nguyên danh sách class Spring trong ADR không?”**  
Chỉ những API/ràng buộc quan trọng với lựa chọn. Ví dụ dùng `JavaMailSender` là một contract; mọi method/constructor chi tiết nên nằm trong design/code.

**“Dùng @Async có được xem là durable retry không?”**  
Không mặc định. Nếu chỉ dùng executor trong memory, task có thể mất khi process restart. Nếu bài toán yêu cầu bền vững, cần message store/broker/outbox phù hợp.

**“Transactional outbox có nghĩa email chắc chắn chỉ gửi một lần?”**  
Không. Nó giúp giữ ý định gửi cùng business transaction; SMTP không có transaction với DB nên vẫn có crash window sau accepted trước khi cập nhật state.

**“Có thể ghi `SENT` nghĩa inbox delivered không?”**  
Không nên khi chỉ dựa vào `JavaMailSender.send`. Nên định nghĩa submitted/accepted riêng với provider/recipient feedback; inbox placement và read/open còn là những điều khác.

**“Tại sao SMTP timeout không tự động retry?”**  
Vì timeout sau DATA có thể xảy ra khi provider đã chấp nhận message nhưng response cuối bị mất. Retry ngay có nguy cơ duplicate; ADR cần mô tả `UNKNOWN` và reconciliation.

**“Fallback có phải lựa chọn kỹ thuật thuần túy?”**  
Không. Nó phụ thuộc region, tenant, sender identity, quota, compliance, attachment capability và business tolerance với duplicate.

**“Giả thiết nào cần ưu tiên kiểm chứng trước?”**  
Những giả thiết có **tác động lớn nếu sai** và độ tin cậy thấp: duplicate semantics, data residency, security, critical SLO, khả năng retry/recovery hoặc provider quota.

**“Nếu một ADR chứa giả thiết không thể test ngay thì sao?”**  
Ghi rõ `unvalidated`, lý do, owner, risk mitigation và thời điểm/trigger kiểm chứng. Không bỏ trống rồi biến assumption thành promise.

**“SLO submission và SLO inbox delivery khác nhau thế nào?”**  
Submission đo khi app/provider tiếp nhận email; inbox delivery phụ thuộc nhiều tầng người nhận và không luôn quan sát được. Chọn metric đúng điều hệ thống có thể đo.

**“Có nên quyết định template render khi worker chạy?”**  
Tuỳ nhu cầu. Nếu muốn nội dung lúc event được giữ chính xác, cần snapshot/version hoặc lưu rendered content. Nếu muốn dữ liệu luôn mới, có thể render về sau nhưng cần xác định tính đúng đắn nghiệp vụ.

**“Lưu MIME snapshot có vấn đề bảo mật không?”**  
Có thể. Nó có thể chứa PII, token, attachment. ADR cần retention, encryption, tenant access và deletion, không chỉ lợi ích replay.

**“Gửi email HTML có ảnh cần ghi riêng ADR không?”**  
Nếu là một template nhỏ thì có thể chỉ cần design convention. Nếu quyết định về storage asset, inline CID vs HTTPS, khả năng replay và PII ảnh hưởng toàn bộ hệ thống, có thể cần ADR.

**“Có thể tin SMTP provider SLA để bỏ load test không?”**  
SLA/contract là một nguồn evidence, nhưng không thay thế test về workload, connection pool, credentials, network và cách client retry của chính ứng dụng.

**“Nếu load test đạt một lần thì giả thiết được xem là đúng mãi?”**  
Không. Bằng chứng bị giới hạn bởi phiên bản và quy mô test. Khi workload/provider/dependency đổi, cần xem xét lại.

**“Ai nên approve ADR về data residency?”**  
Những người có quyền phê duyệt theo chính sách tổ chức, thường gồm security/compliance và owner kiến trúc. Không coi một developer comment là approval về nghĩa vụ pháp lý.

**“Có nên ghi failover trong cùng ADR với provider adapter?”**  
Có thể nếu scope nhỏ, nhưng adapter contract và fallback policy thường thay đổi độc lập. Tách ADR giúp thay lựa chọn mà không mất các rationale còn đúng.

**“Một incident có bắt buộc tạo ADR mới?”**  
Không phải luôn. Nếu incident chỉ sửa bug không làm thay lựa chọn, cập nhật evidence/runbook. Nếu nó phá giả thiết cốt lõi hoặc dẫn tới policy mới, nên tạo/supersede ADR.

**“ADR có thay thế incident postmortem không?”**  
Không. Postmortem ghi sự kiện, timeline, tác động, nguyên nhân; ADR ghi lựa chọn sau khi xét bối cảnh và alternatives. Chúng nên liên kết.

**“Có thể xóa ADR bị Superseded không?”**  
Không nên, trừ khi chính sách retention bắt buộc. Giữ lịch sử giúp hiểu vì sao thiết kế từng thay đổi và tránh lặp lại sai lầm.

**“Tại sao phải ghi owner?”**  
Vì giả thiết cần người xác minh, risk cần người chấp nhận và decision drift cần người phản hồi. Không có owner, tài liệu dễ trở thành nhật ký không ai bảo trì.

**“Có cần ghi phương án rollback?”**  
Với lựa chọn ảnh hưởng live delivery, có. Rollback không chỉ trả code về trước mà còn phải xử lý backlog, in-flight attempts, schema và delayed feedback.

**“Làm sao để ADR không trở thành thủ tục hành chính?”**  
Giữ một decision trung tâm mỗi ADR, viết ngắn nhưng đủ bối cảnh, link evidence và owner. Gắn việc cập nhật với PR/incident/revisit trigger thay vì tạo biểu mẫu dài cho mọi chỉnh sửa nhỏ.

## 29. Checklist áp dụng vào dự án Spring Framework Mail

### Trước khi chốt quyết định

1. Xác định **câu hỏi kiến trúc trung tâm** mà ADR cần trả lời.
2. Ghi service, loại email, tenant, region và môi trường thuộc phạm vi.
3. Ghi lý do hiện trạng không đáp ứng yêu cầu hoặc cơ hội cần tận dụng.
4. Xác định tiêu chí reliability, latency, security, observability và chi phí.
5. Phân biệt yêu cầu **bắt buộc** và điều có thể đánh đổi.
6. Ghi những giả thiết chưa được kiểm chứng, độ tin cậy và owner.
7. Liệt kê ít nhất một phương án đơn giản hoặc dùng hạ tầng hiện tại.
8. Mô tả công bằng lợi ích, hạn chế và failure modes của từng phương án.
9. Nếu chấm điểm, ghi trọng số, dữ liệu nguồn và độ nhạy của quyết định.
10. Không cho phương án vi phạm bảo mật/compliance thắng chỉ nhờ điểm chi phí.

### Khi thiết kế mail flow

11. Định nghĩa business intent được tạo khi nào và bởi transaction nào.
12. Phân biệt gửi đồng bộ, `@Async` in-memory, outbox và broker.
13. Định nghĩa ranh giới `JavaMailSender`, mail model và provider adapter.
14. Chọn `SimpleMailMessage` hay `MimeMessageHelper` dựa trên MIME requirements.
15. Định nghĩa cách render template và pin template version.
16. Bảo đảm attachment/inline resources còn tồn tại và đọc lại được khi retry.
17. Định nghĩa SMTP/API submission outcome và nghĩa của `ACCEPTED`.
18. Ghi rõ cách xử lý `UNKNOWN`, không giả định timeout nghĩa chưa gửi.
19. Định nghĩa retry, backoff, max attempts, dead letter và manual redrive.
20. Ghi business idempotency key và duplicate risk còn lại.
21. Xác định khi nào được fallback, provider nào eligible và policy region/identity.
22. Định nghĩa feedback/bounce/complaint correlation và suppression.
23. Ghi rõ secret management, TLS, PII retention và audit.

### Khi kiểm chứng

24. Có unit tests cho decision logic/mapping.
25. Có integration tests với PostgreSQL thật hoặc Testcontainers nếu dùng row locking.
26. Có SMTP fake/test server cho MIME và protocol failures.
27. Có fault injection tại điểm trước/sau SMTP accepted.
28. Có test crash khi producer/worker restart.
29. Có test attachment/template versioning qua retry.
30. Có test multi-tenant/region restrictions và credential handling.
31. Có benchmark dưới workload đại diện và metric đúng ngữ nghĩa.
32. Ghi môi trường, phiên bản, ngày đo và link evidence.
33. Không đánh dấu giả thiết VALIDATED nếu test chưa bao phủ nó.

### Khi triển khai và vận hành

34. ADR có owner, status, link issue và PR.
35. Có rollout/canary rõ, không gửi email thật qua hai đường “shadow”.
36. Có rollback plan cho backlog, in-flight và feedback muộn.
37. Có dashboard queue age, attempts, failures, UNKNOWN, bounce/complaint.
38. Có alert theo business SLO và runbook theo failure class.
39. Có quy trình redrive kiểm tra quyền, suppression, expiry và duplicate risk.
40. Có data retention/cleanup mà không mất work item chưa xử lý.
41. Có revisit triggers và người theo dõi assumptions.
42. Khi code thay đổi semantics, cập nhật ADR hoặc tạo bản superseding.
43. Khi incident xảy ra, liên kết postmortem tới giả thiết/quyết định bị tác động.
44. Giữ ADR cũ để có lịch sử và giải thích lý do đổi phương án.

## 30. Mẫu Decision Log rút gọn cho cuộc họp

Không phải lúc nào cũng có đủ thông tin để viết ADR ngay trong một cuộc họp. Có thể bắt đầu bằng một bảng nhỏ:

| Field | Nội dung ví dụ |
| --- | --- |
| Decision ID | ADR-012 |
| Question | Nên dùng một SMTP relay hay có secondary provider? |
| Why now | Provider A outage gây tăng backlog, SLO bị ảnh hưởng |
| Mandatory constraints | Tenant/region, sender identity, suppression |
| Options | A-only retry, A+B blind fallback, A+B guarded fallback |
| Provisional choice | Guarded fallback sau definite pre-submission failure |
| Key assumption | Provider B đủ quota và đã verify domain |
| Highest risk | UNKNOWN trên A có thể tạo email trùng nếu resend B |
| Evidence needed | SMTP fault injection, quota verification, DKIM/DMARC test |
| Owner | Messaging/Platform |
| Status | Proposed pending evidence |
| Follow-up | Viết ADR hoàn chỉnh, review security, chạy test |

Sau cuộc họp, ADR author sẽ mở rộng decision log thành tài liệu có alternatives và rationale. Không ghi `Accepted` khi còn thiếu phê duyệt cho mandatory constraints.

### 30.1. Một mẫu một trang cho quyết định nhỏ

~~~markdown
# ADR-XXX: [Decision title]

**Status:** Proposed
**Scope:** [Which messages/services]
**Owner:** [Role]

## Problem
[What breaks or needs to improve?]

## Constraints
- [...]

## Options
1. [Option A: benefit / downside]
2. [Option B: benefit / downside]

## Assumptions
- A-01: [Claim; confidence; validation owner]

## Decision
[Chosen option and boundaries]

## Why
[Most important rationale and tradeoff]

## Validate
- [Test / SLO / evidence link]

## Revisit when
- [Trigger]
~~~

Nếu quyết định có rủi ro đáng kể, hãy thêm phần risk/mitigation và rollout/rollback. Mẫu ngắn không phải lý do để bỏ qua điều kiện an toàn.

## 31. Sơ đồ toàn bộ vòng đời quyết định

~~~text
              New requirement / incident
                         |
                         v
              Define the architecture question
                         |
                         v
                  Describe context
                         |
         +---------------+----------------+
         |               |                |
         v               v                v
     Constraints     Assumptions       Goals/SLO
         |               |                |
         +---------------+----------------+
                         |
                         v
                List viable alternatives
                         |
                         v
            Filter mandatory constraints
                         |
                         v
            Compare risks, tradeoffs, cost
                         |
                         v
            Gather evidence / run experiments
                         |
                   +-----+-----+
                   |           |
                   v           v
                Inconclusive  Sufficient
                   |           |
                   v           v
             Time-box/     Decide + record
             mitigate          |
                               v
                       Review / approval
                               |
                               v
                      Implement via PR
                               |
                               v
                       Deploy with metrics
                               |
                               v
                     Observe actual outcomes
                               |
                     +---------+---------+
                     |                   |
                     v                   v
               Assumptions hold     Assumption invalid /
                     |              trigger breached
                     v                   |
               Keep decision            v
                     |               Re-evaluate
                     |                   |
                     |                   v
                     |               New ADR if
                     |               decision changes
                     |                   |
                     +-------------------+
                               |
                               v
                   Keep immutable decision history
~~~

### 31.1. Ba câu hỏi luôn cần trả lời

Khi đọc bất kỳ ADR nào cho Spring Framework Mail, người bảo trì nên trả lời được:

1. **Vì sao chúng ta chọn phương án này thay vì các cách khác trong bối cảnh ban đầu?**
2. **Những giả thiết/rủi ro nào khiến phương án có thể không còn phù hợp?**
3. **Bằng chứng và điều kiện nào sẽ kích hoạt việc giữ, sửa hoặc thay quyết định?**

Nếu tài liệu không trả lời được các câu hỏi ấy, nó có thể chỉ là mô tả hiện trạng chứ chưa phải một **bản ghi quyết định kiến trúc** đủ dùng.

## 32. Kết luận

**Ghi lại quyết định, giả thiết và phương án thay thế** giúp kiến trúc Spring Framework Mail có thể được giải thích, kiểm chứng và thay đổi có kiểm soát. Một hệ thống email không chỉ phải “gửi được”, mà còn cần xử lý transaction boundaries, retry/unknown outcomes, provider restrictions, MIME/template/attachment lifecycle, bảo mật dữ liệu, feedback và vận hành trong các tình huống lỗi.

ADR tốt ghi rõ **bài toán, lựa chọn, tiêu chí, ràng buộc, giả thiết và nguồn bằng chứng**, sau đó nối chúng với test, dashboard, incident và code thực tế. Phương án không được chọn cũng cần mô tả công bằng, bởi chính những tradeoff ấy sẽ giúp nhóm hiểu khi nào phải thay đổi kiến trúc. Với Spring Mail, đặc biệt nên tránh tuyên bố chưa được chứng minh như “SMTP accepted đồng nghĩa inbox delivered”, “outbox bảo đảm exactly-once” hoặc “mọi exception đều có thể fallback an toàn”.

Giá trị lớn nhất của ADR không nằm ở việc có thêm tài liệu, mà ở khả năng **giữ lại lý do của quyết định hôm nay để người vận hành và phát triển ngày mai có thể đánh giá lại nó bằng dữ liệu, thay vì đoán hoặc lặp lại các sự cố đã từng xảy ra**.
