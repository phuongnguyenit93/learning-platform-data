# Ghi lại quyết định — Thiết kế chiến lược log cho Java

## 1. Ghi lại quyết định là gì?

Khi thiết kế logging cho một ứng dụng Java, nhóm phát triển phải lựa chọn **sự kiện nào cần ghi, dùng level nào, lưu định dạng gì, đưa đến đâu, ai được truy cập, giữ bao lâu và xử lý thế nào khi hệ thống log gặp lỗi**. Nếu chỉ thay code hoặc cấu hình mà không ghi lý do, vài tháng sau khó giải thích vì sao API log ERROR ở error handler thay vì ở service, vì sao một số DEBUG bị lấy mẫu, hoặc vì sao audit có kho lưu trữ riêng.

**Ghi lại quyết định** là tạo tài liệu có cấu trúc để bảo tồn **bối cảnh, lựa chọn đã cân nhắc, phương án được chấp thuận, lý do, hệ quả, người sở hữu và bằng chứng kiểm chứng**. Cách thực hành phổ biến trong thiết kế phần mềm là **Architecture Decision Record (ADR)**. Nhiều ADR được lập thành **decision register/decision log**, giúp thành viên mới và đội vận hành hiểu lịch sử lựa chọn.

Ví dụ:

~~~text
ID: LOG-001
Title: Chỉ ghi terminal ERROR tại HTTP exception boundary
Status: ACCEPTED
Owner: API Platform
Context: Cùng SQLException bị log ở repository, service và controller
Decision: Tầng trung gian bảo toàn cause, không log rồi rethrow
Rationale: Tránh báo ba lỗi cho một failed request
Consequences: Error boundary phải giữ requestId và root cause
Acceptance: Một request thất bại tạo một terminal ERROR event
Review trigger: Thay đổi error handling hoặc kiến trúc async
~~~

Đây là **quyết định thiết kế**, không phải một dòng log của request. Nó có thể được lưu bằng Markdown trong version control. Khi request chạy thật, ứng dụng có thể tạo một event ERROR mang eventCode, requestId và Throwable, nhưng không phải viết lại toàn bộ rationale của ADR vào log.

**Mục tiêu:** quyết định logging phải **giải thích được, review được, triển khai được, kiểm thử được và thay thế được** khi điều kiện kỹ thuật hoặc nghiệp vụ thay đổi.

## 2. Phân biệt decision record, runtime event, audit và change record

Bốn loại bản ghi có mục đích khác nhau:

| Loại | Trả lời câu hỏi | Ví dụ | Nơi lưu |
| --- | --- | --- | --- |
| **ADR** | Vì sao nhóm chọn chiến lược logging này? | LOG-001: ERROR một lần ở boundary | Repo tài liệu kỹ thuật |
| **Runtime decision log** | Request này được xử lý theo nhánh nào? | ruleId=RISK_CHECK, outcome=DENY | Log có cấu trúc |
| **Security/audit trail** | Ai thực hiện hoặc bị từ chối hành động cần chứng cứ? | Actor thay đổi role | Kênh audit có policy riêng |
| **Change/incident record** | Ai deploy, thay cấu hình, rollback và kết quả ra sao? | Chuyển parser v2, rollback do schema conflict | Change ticket/runbook |

Một ADR không thay audit theo quy định; một audit record không giải thích đầy đủ lý do chọn Logback, retention hoặc schema. Một runtime log cũng không đáng dùng làm kho ADR: log có thể bị rotate/xóa theo retention và thường chứa dữ liệu sự kiện với số lượng rất lớn.

Mối quan hệ đúng:

~~~text
Yêu cầu + SLO + rủi ro + bảo mật + ngân sách
                    |
                    v
              Đề xuất ADR
                    |
         review, so phương án, duyệt
                    |
                    v
          Code / config / runbook
                    |
                    v
          Log + metric + trace thực tế
                    |
                    v
          Tests, monitoring, evidence
                    |
           bối cảnh thay đổi?
                    |
                    v
            ADR mới supersede
~~~

Nhờ đó, người vận hành có thể từ một rule trong Logback đi ngược về ADR và hiểu vì sao nó được thiết kế, thay vì tự suy đoán.

## 3. Nếu không ghi lại quyết định thì chuyện gì xảy ra?

- **Level drift:** người mới chuyển mọi exception thành ERROR vì không biết trước đó nhóm đã thống nhất WARN cho fallback phục hồi thành công.
- **Duplicate logs:** repository log rồi throw, service log rồi throw, error handler lại log cùng lỗi; dashboard đếm một failure thành ba.
- **Schema drift:** Logback đổi PatternLayout, collector vẫn chạy Grok cũ nên mất requestId hoặc parser sai timestamp.
- **PII leakage:** ai đó thêm raw request body vào DEBUG vì không biết policy cấm token/Cookie.
- **Retention conflict:** giảm totalSizeCap để tiết kiệm storage và vô tình dọn log còn cần bảo vệ.
- **Khó đổi backend:** không ghi tại sao chọn Log4j 2 hoặc JSON encoder, nên đổi công cụ mà không biết tiêu chí tương thích.
- **Không rõ trách nhiệm:** ai chấp thuận fail-open, fail-closed, audit routing và quyền truy cập?
- **Thiếu kiểm chứng:** team có tài liệu “mọi request phải có traceId” nhưng không test async task hay error response.
- **Không biết khi nào phải xem lại:** volume production tăng gấp nhiều lần nhưng vẫn giữ sampling/retention theo giả định cũ.
- **Incident lặp:** bài học của lần xử lý sự cố trước không biến thành quyết định và regression test.

Ghi quyết định không làm logging tự đúng. Nó **làm rõ điều cần kiểm thử, điều được phép thay đổi và những rủi ro phải chấp nhận**.

## 4. Khi nào một lựa chọn logging cần ADR riêng?

Không cần ADR cho mỗi lời gọi log.info(...). Nên ghi lại khi quyết định:

1. Ảnh hưởng nhiều service/đội hoặc thay đổi contract với collector, alert, dashboard và support.
2. Có nhiều phương án hợp lý và đánh đổi quan trọng.
3. Liên quan security, PII, audit, retention, legal hold hoặc quyền xóa dữ liệu.
4. Gây chi phí vận hành đáng kể hoặc khó rollback dữ liệu đã ingest.
5. Thay đổi semantics của eventCode, severity, traceId, sampling hoặc log loss.
6. Đưa vào technology/backend mới hoặc phụ thuộc provider khó thay thế.
7. Có thể khiến người khác hỏi “vì sao lại chọn như vậy?” sau nhiều tháng.

Ví dụ **cần xem xét ADR**: chọn JSON Lines thay text, chọn kênh audit tách biệt, chính sách mất log khi queue đầy, thay retention trên toàn bộ cluster. Ví dụ **có thể chỉ cần code review/config comment**: sửa typo trong message, thêm DEBUG tạm theo policy đã có, đổi tên biến local.

**Trường hợp đặc biệt:** các quyết định pháp lý/bảo mật có thể phải có phê duyệt riêng dù thay đổi code nhỏ. Không tự lấy tiêu chí “ít dòng code” làm căn cứ bỏ review.

Nên giữ ADR **ngắn, tập trung một quyết định đủ lớn**. Nếu một file vừa chọn backend, vừa đặt retention, vừa quyết định PII, vừa xử lý queue đầy, việc review và supersede từng phần rất khó.

## 5. Quyết định quan trọng trong chiến lược log

| Chủ đề | Câu hỏi phải được chốt | Cách kiểm chứng |
| --- | --- | --- |
| **Event taxonomy** | Ghi những sự kiện nào, vì mục đích gì? | Event catalog, fixtures |
| **Severity** | Khi nào INFO/WARN/ERROR? | Unit/integration tests |
| **Exception ownership** | Tầng nào log lỗi cuối? | Đếm LogEvent, kiểm tra cause |
| **Structured logging** | JSON hay text? Schema và kiểu trường? | Parser/golden tests |
| **Correlation** | requestId/traceId sinh ở đâu, propagate thế nào? | HTTP + async tests |
| **Routing** | Console, file, search, audit sink nào? | Appender and collector tests |
| **Sampling/filtering** | Sự kiện nào được lấy mẫu hoặc bỏ? | Volume, consistency tests |
| **Reliability** | Queue đầy hoặc sink down thì drop/retry/block? | Failure injection |
| **Retention** | Giữ bao lâu ở từng kho? Xóa theo điều kiện nào? | Lifecycle readback |
| **Privacy/security** | Field nào không được log, ai có quyền đọc? | PII scanning, IAM |
| **Index/alerts** | Backend mapping và alert threshold nào? | Query/dashboard tests |
| **Ownership/operations** | Ai duyệt, monitor và rollback? | Change record/runbook |
| **Cost/capacity** | Bytes/day, throughput, CPU, index replication? | Benchmarks, budgets |

Các quyết định về sampling DEBUG và security audit thường **không nên bị gộp vào cùng một rule**, vì yêu cầu giữ và tính đầy đủ khác nhau.

## 6. Những trường tối thiểu của một ADR logging

Một decision record tốt cần:

- **ID và tên kết luận:** ví dụ LOG-007 — Dùng JSON Lines cho application logs; tránh tên “Nghiên cứu logging”.
- **Status:** PROPOSED, ACCEPTED, SUPERSEDED hoặc trạng thái được team thống nhất.
- **Owner, reviewers, thời điểm:** ai đề xuất, ai duyệt và ngày ra quyết định.
- **Scope:** service, môi trường, log class, sink, đối tượng chịu ảnh hưởng và phần không áp dụng.
- **Context:** vấn đề, dữ liệu hiện trạng, incident/budget/requirements.
- **Drivers/constraints:** performance, security, cost, legal, compatibility, recovery.
- **Alternatives:** các phương án thực sự có thể chọn, ưu/nhược từng phương án.
- **Decision:** câu nêu hành động rõ ràng có thể triển khai.
- **Rationale:** tại sao phương án được chọn phù hợp bối cảnh hơn những phương án khác.
- **Consequences:** điều tốt, bất lợi, chi phí và rủi ro chưa giải quyết.
- **Implementation references:** PR/config/schema/test/dashboard/runbook.
- **Acceptance criteria:** điều kiện đo được để khẳng định đã triển khai đúng.
- **Rollout/rollback:** canary, migration, cách quay lại nếu không đạt.
- **Review triggers:** incident, luật, cost, schema hoặc topology thay đổi.
- **Supersedes/superseded-by:** liên kết nếu quyết định thay thế quyết định trước.

Theo thực hành ADR của AWS, GOV.UK và nhiều nhóm kiến trúc, **context, decision và consequences** là phần tối thiểu. Những trường bổ sung làm quyết định logging dễ đi vào vận hành vì có nhiều thành phần ngoài code Java.

**Đừng để ADR thành danh sách khẩu hiệu.** “Logging phải an toàn” không cho biết điều gì bị cấm, ở đâu phải redact và kiểm chứng thế nào.

## 7. Mẫu ADR Markdown đầy đủ

Ví dụ minh họa dùng dữ liệu giả định. Có thể đặt trong docs/adr/LOG-007-json-lines.md của dự án; đường dẫn thực cần do team xác định.

~~~markdown
# LOG-007 — Dùng JSON Lines cho application logs

- Status: ACCEPTED
- Date: 2026-11-10
- Owner: Platform Observability
- Reviewers: API team, Security
- Scope: Java HTTP services; không áp dụng audit sink
- Supersedes: None

## Context
Pattern text hiện tại khác nhau giữa các service.
Parser ở collector thường bỏ sót requestId và exception.
Một số message chứa dấu xuống dòng và dấu phân cách.

## Decision drivers
- Có timestamp, service, severity, eventCode.
- Giữ requestId/traceId nếu context tồn tại.
- Không xuất password, token, Cookie hoặc raw request body.
- Rollout từng service và có rollback.

## Alternatives
A. Giữ text + Grok ở collector.
B. Xuất JSON Lines với schema versioned tại nguồn.
C. Gửi event binary qua agent chuyên dụng.

## Decision
Chọn B cho application logs.
Mỗi logical event thành một JSON object trên một dòng.
Dùng JSON serializer để escape message và exception.
Giữ schema contract có version, không áp dụng lên audit sink.

## Rationale
Giảm lệ thuộc vào vị trí text và regex,
dễ query theo typed field và phát hiện schema drift.

## Consequences
+ Dễ truy vấn requestId, traceId, eventCode.
+ Giảm lỗi multiline khi exception được escape.
- Thêm chi phí encoder/schema governance.
- Collector và dashboards cần migration.
- Cần kiểm soát PII và dynamic fields.

## Acceptance
- Golden fixtures parse đúng, một event mỗi dòng.
- Không thấy secret trong output thử nghiệm.
- Query bằng requestId tìm được event tại backend.
- Volume, latency và parser errors trong ngưỡng phê duyệt.

## Rollout and rollback
Canary trên một service, so với baseline.
Rollback encoder/pipeline nếu không đạt.
Không xóa dữ liệu cũ trước khi nghiệm thu.

## Review triggers
Đổi backend, incident parser, chính sách privacy
hoặc chi phí ingest vượt giới hạn.
~~~

**Quan trọng:** Mẫu chỉ là **quyết định giả định**, không tuyên bố project đã chọn JSON. Acceptance là mục tiêu kiểm thử, **không phải kết quả đã đo**. Người làm bài phải phân biệt trạng thái quyết định và tình trạng triển khai.

Một ADR tốt có thể nằm trong một file Markdown ngắn; dữ liệu chi tiết và phép đo có thể liên kết sang tài liệu khác, không nhất thiết nhồi tất cả output log vào ADR.

## 8. Lifecycle: đề xuất, chấp thuận, thay thế

~~~text
Nhu cầu mới / incident / change request
               |
               v
       DRAFT hoặc PROPOSED
               |
        review & alternatives
               |
               v
            ACCEPTED
               |
     code/config/test, rollout
               |
            VERIFIED
               |
   điều kiện đổi / có bằng chứng mới
               |
               v
       ADR mới supersede ADR cũ
               |
        record cũ: SUPERSEDED
~~~

Tùy quy ước, **VERIFIED** có thể là trạng thái triển khai riêng chứ không thuộc status ADR. Nên tách:

- **Decision status:** PROPOSED, ACCEPTED, SUPERSEDED.
- **Implementation status:** NOT_STARTED, IN_PROGRESS, ROLLED_OUT, VERIFIED, ROLLED_BACK.

Không gộp ACCEPTED với VERIFIED. Một ADR được duyệt nhưng chưa rollout **không phải** chính sách đang thực thi trong production.

**Bảo tồn lịch sử:** Khi thay một lựa chọn có ý nghĩa, nên lập ADR mới rồi liên kết thay thế, thay vì âm thầm viết lại rationale của ADR đã chấp thuận. Chỉnh typo/URL có thể được phép theo quy ước tài liệu, nhưng thay đổi quan điểm phải để lại lịch sử.

Với một lựa chọn không được duyệt, giữ trạng thái PROPOSED hoặc REJECTED theo quy trình; không dùng mã đang proposed làm quy tắc sản xuất chỉ vì pull request đã tồn tại.

## 9. Quyền quyết định và trách nhiệm

| Vai trò | Điểm cần xem |
| --- | --- |
| Application owner | Cần log gì để debug và hỗ trợ nghiệp vụ? |
| Platform/Observability | Schema, ingestion, index, query, quota, cost |
| SRE/Operations | Queue, backpressure, failure policy, incident runbook |
| Security | Secret/PII, audit, tamper resistance, access control |
| Compliance/Legal | Retention, legal hold, quyền xóa dữ liệu theo luật áp dụng |
| Support | Có cách lấy requestId và tìm sự kiện mà không lộ dữ liệu? |
| Data/Analytics | Field type, consistency và reliability của metrics |

Một ADR nên có **owner chịu trách nhiệm cuối**, người tham gia review theo tác động và cơ chế giải quyết bất đồng. Không cần tất cả các nhóm duyệt mọi thay đổi nhỏ, nhưng **thay audit retention hoặc quyền đọc log** cần đúng vai trò có thẩm quyền.

Không dùng approval kiểu “đã thảo luận trong chat” không có kết luận để thay quyết định có trạng thái. Nếu cần phê duyệt chính thức, lưu tham chiếu tới change/security review trong hệ thống phù hợp.

## 10. Ví dụ quyết định: log lỗi một lần tại boundary

Một anti-pattern phổ biến:

~~~text
Repository: log.error(SQLException), throw
Service:    log.error(OrderCreationException), throw
Controller: log.error("request failed"), throw
Handler:    log.error("HTTP 500", exception)
~~~

Một logical failure bị log nhiều lần. Decision LOG-001 có thể chọn:

~~~text
Scope: Java HTTP services
Choice:
  - Repository/service chuyển exception và giữ root cause.
  - Chỉ terminal boundary log ERROR khi operation thật sự fail.
  - Validation 400 dự kiến không mặc định full ERROR stack trace.
  - Fallback thành công dùng metric/WARN nếu sự suy giảm quan trọng.
Acceptance:
  - Một failed request có đúng một terminal ERROR event.
  - Có requestId/eventCode và Throwable cause.
  - Hai requests độc lập vẫn được đếm thành hai failures.
Exceptions:
  - Security/audit event có mục đích khác vẫn phải lưu theo policy.
~~~

Phương án thay thế là log ở nhiều tầng để dễ tìm call-site. **Đánh đổi:** chọn terminal boundary tránh nhiễu nhưng đòi hỏi truyền exception context tốt; nếu lớp giữa nuốt cause thì mất thông tin. Vì vậy ADR phải đi kèm test bảo toàn cause chain và correlation context.

Không coi **một stack trace nhiều dòng** là nhiều logging events. Không chặn ERROR bằng regex theo message giống nhau, vì hai request khác nhau có thể có cùng nguyên nhân thật.

## 11. Ví dụ quyết định: schema và correlation

Một logging schema minh họa:

~~~json
{
  "timestamp": "2026-11-10T03:30:05Z",
  "level": "ERROR",
  "service": "order-service",
  "eventCode": "ORDER_FAILED",
  "requestId": "req-42",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "outcome": "FAILED",
  "errorCode": "DEPENDENCY_UNAVAILABLE"
}
~~~

ADR về schema phải quyết định:

1. Timestamp có offset/UTC hay không; event time khác observed time thế nào?
2. Có giữ severityText gốc (JUL SEVERE, Logback ERROR) và map severityNumber chuẩn không?
3. Tên field và kiểu có nhất quán giữa service không?
4. requestId sinh ở gateway/app, có chấp nhận header do client gửi không?
5. traceId/spanId được truyền bằng tracing instrumentation và W3C context thế nào?
6. eventCode có registry hay chỉ ghi message tùy ý?
7. Exception/stacktrace được encode và bảo vệ ra sao?
8. Có schemaVersion và migration/compatibility policy không?
9. Những trường nào phải redact hoặc không được ingest?
10. Ai sở hữu golden fixtures cho collector và dashboard?

**OpenTelemetry Logs Data Model** có Timestamp, ObservedTimestamp, SeverityText, SeverityNumber, Body, Resource, Attributes và TraceId/SpanId. Có thể dùng như tài liệu thiết kế semantic mapping, nhưng không tự coi một JSON tự định nghĩa có tên field tương tự là toàn bộ OpenTelemetry LogRecord chuẩn.

Khi ADR nói “mọi request phải tìm được theo requestId”, cần kiểm tra end-to-end: HTTP response → Java MDC → Logback/Log4j 2 output → shipper/collector → backend query. Chỉ thấy MDC trong controller chưa đủ.

## 12. Ví dụ quyết định: privacy, retention và audit

Security/logging decisions thường có hai nhóm ràng buộc khó cân bằng:

- **Cần đủ bằng chứng:** điều tra, phát hiện tấn công, auditing, debugging, SLA.
- **Không giữ quá mức:** dữ liệu cá nhân, token, quyền truy cập, mục đích xử lý, thời hạn, chi phí.

Một ADR/retention policy nên nêu:

- Log classes: debug, application, access, security, audit.
- Dữ liệu cần loại ngay tại nguồn: password, access token, Cookie, raw payment data, secret key.
- Trường được phép ghi có điều kiện: actorRef, IP, requestId, route template; phải có mục đích và phân quyền.
- Kênh audit riêng hay chung? Nếu riêng, vì sao và làm sao kiểm tra routing?
- Thời hạn giữ theo loại dữ liệu và cơ sở áp dụng; khi nào bắt đầu tính tuổi.
- Đích thực tế: local file, stdout/container, collector queue, search index, object archive, snapshot, backup, export.
- Có **legal hold** hợp lệ hay không; ai đặt/gỡ và có thời điểm review không.
- Xóa/khử nhận dạng dữ liệu có tác động tới bản sao và restore thế nào.
- Quy tắc khi dung lượng đầy: chuyển tier/alert, không âm thầm xóa evidence bắt buộc.
- Cách chứng minh đã thực thi, không chỉ lưu một file YAML policy.

**Không ghi trong ADR “giữ 90 ngày vì đây là chuẩn” nếu chưa có căn cứ**. Retention là quyết định theo luật, hợp đồng và nhu cầu tổ chức; số ngày minh họa không có giá trị pháp lý. Việc một nhóm gọi mọi sự kiện là “audit” cũng không làm toàn bộ PII được miễn mọi nghĩa vụ xóa.

Nếu có security/PII risk, cần review bởi đúng nhóm có thẩm quyền và test có thể kiểm chứng: synthetic secret không xuất trong log, audit đi đúng sink, lifecycle chạy đủ nơi, backup restore không làm dữ liệu bị xóa hợp lệ xuất hiện lại.

## 13. Ví dụ quyết định: sampling, chi phí và độ bền

Một quyết định “lấy mẫu 10% DEBUG” quá ngắn, bởi nó chưa nói:

- Đó là **10% event**, **10% request** hay sampling ở cấp trace?
- Random per line có làm thiếu bối cảnh của một request không?
- Khi DEBUG có exception quan trọng thì có cần bỏ không?
- Sampling có áp dụng cho security/audit không, theo căn cứ gì?
- Chi phí ingest trước/sau ước tính bằng bytes/day hay chỉ bằng số dòng?
- Khi incident cần tăng diagnostic, làm thế nào, trong bao lâu, ai duyệt?
- Có ảnh hưởng dashboard hoặc alert được suy từ log không?

Tương tự, quyết định dùng AsyncAppender hoặc queue:

| Câu hỏi | Ví dụ điều cần chốt |
| --- | --- |
| Khi queue đầy | Drop DEBUG, block producer hay spill-to-disk? |
| Khi collector down | Retry trong bao lâu, bounded buffer ở đâu? |
| Khi JVM crash | Log nào có thể mất trong memory queue? |
| Khi shutdown | Flush timeout và dữ liệu chưa ACK được xử lý thế nào? |
| Khi audit sink lỗi | Fail-open hay fail-closed theo chính sách? |
| Khi backpressure | Latency của request và giới hạn tài nguyên? |

**Không tuyên bố exactly-once/no loss** nếu hệ thống chỉ dùng memory queue bất đồng bộ. Các mục tiêu độ bền cần định nghĩa ranh giới ACK và failure semantics thực tế; luật/audit có thể yêu cầu con đường khác với application debug logs.

ADR nên ghi **phép đo baseline** và giới hạn đã duyệt; không bịa con số target. Nếu còn thiếu đo đạc, để PROPOSED kèm kế hoạch thử nghiệm thay vì chấp thuận chỉ bằng cảm giác.

## 14. Từ ADR tới thực thi và kiểm chứng

Một ADR không tự thay đổi code. Nên có đường truy vết:

~~~text
ADR LOG-001: terminal ERROR một lần
       |
       +--> Service: giữ cause, không catch-log-rethrow
       +--> HTTP error handler: một ERROR với requestId/eventCode
       +--> Logback encoder: có throwable và MDC
       +--> Integration test: logCount=1, root cause preserved
       +--> Metrics/alert: đếm logical failure, không đếm stack lines
       +--> Runbook: query theo requestId và eventCode
~~~

Ví dụ decision register:

| ID | Tóm tắt | Decision status | Implementation status | Bằng chứng |
| --- | --- | --- | --- | --- |
| LOG-001 | Chỉ ERROR ở boundary | ACCEPTED | VERIFIED | Test one-error |
| LOG-002 | Không ghi secret/PII thừa | ACCEPTED | VERIFIED | Redaction test |
| LOG-003 | Sampling DEBUG | PROPOSED | NOT_STARTED | Design draft |
| LOG-007 | JSON Lines application logs | ACCEPTED | ROLLOUT | PR, fixtures |
| LOG-009 | Audit pipeline riêng | ACCEPTED | VERIFIED | Routing/ACL test |

Các trạng thái và ID là **dữ liệu giả lập**, không khẳng định repo nào đã triển khai. Link tới PR, config, tests và dashboard phải là link thật khi dùng production.

Không cần ép mọi runtime LogEvent chứa ADR ID: decisionId có thể được liên kết từ release notes/schemaVersion/config và decision register. Gắn ADR ID vào event chỉ khi có ích cho truy vết và không làm tăng chi phí vô lý.

## 15. Java 17+ chạy độc lập: Decision catalog và logger

Ví dụ sau minh họa hai nhiệm vụ liên hệ nhưng khác nhau:

1. Một catalog nhỏ chứa ba quyết định với ID, status, owner, choice, rationale và test.
2. Runtime chỉ áp dụng decision **ACCEPTED** khi phát một sự kiện ERROR ở boundary. Decision còn PROPOSED bị từ chối.

Đoạn code dùng **JDK 17 java.util.logging**, không cần thư viện ngoài. Handler trong bộ nhớ đếm LogRecord để không nhầm số dòng stack trace với số event. Đây **không phải hệ thống duyệt ADR production**; tài liệu thật nên nằm ngoài code trong kho review/version control.

Tạo file **LoggingDecisionDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingDecisionDemo {
    record Decision(String id, String status, String owner,
                    String choice, String rationale, String test) {}

    static final List<Decision> CATALOG = List.of(
        new Decision("LOG-001", "ACCEPTED", "platform",
            "BOUNDARY_ERROR_ONCE", "Avoid duplicate errors", "log-once-test"),
        new Decision("LOG-002", "ACCEPTED", "security",
            "REDACT_SECRET", "Minimize sensitive data", "pii-test"),
        new Decision("LOG-003", "PROPOSED", "observability",
            "SAMPLE_DEBUG", "Limit log volume", "sampling-test")
    );

    static final Logger LOG = Logger.getLogger("demo.strategy");
    static final List<LogRecord> RECORDS = new ArrayList<>();

    static Decision accepted(String id) {
        return CATALOG.stream()
            .filter(d -> d.id().equals(id)
                      && d.status().equals("ACCEPTED"))
            .findFirst()
            .orElseThrow(() ->
                new IllegalStateException("Decision not accepted"));
    }

    static void logTerminalFailure(String requestId, String eventCode) {
        Decision decision = accepted("LOG-001");

        LOG.log(Level.SEVERE, "strategyId=" + decision.id()
            + " requestId=" + requestId
            + " eventCode=" + eventCode + " outcome=FAILED",
            new IllegalStateException("dependency unavailable"));
    }

    public static void main(String[] args) {
        Set<String> ids = new HashSet<>();

        for (Decision d : CATALOG) {
            if (!ids.add(d.id()) || d.owner().isBlank()
                    || d.rationale().isBlank() || d.test().isBlank()) {
                throw new IllegalStateException("Invalid decision record");
            }

            System.out.println("decision " + d.id() + " status="
                + d.status() + " owner=" + d.owner()
                + " choice=" + d.choice());
        }

        System.out.println("accepted=" + CATALOG.stream()
            .filter(d -> d.status().equals("ACCEPTED")).count()
            + " proposed=" + CATALOG.stream()
            .filter(d -> d.status().equals("PROPOSED")).count());

        boolean proposedBlocked = false;
        try {
            accepted("LOG-003");
        } catch (IllegalStateException expected) {
            proposedBlocked = true;
        }
        System.out.println("proposedBlocked=" + proposedBlocked);

        Handler memory = new Handler() {
            { setLevel(Level.ALL); }

            @Override
            public void publish(LogRecord event) {
                if (isLoggable(event)) RECORDS.add(event);
            }

            @Override public void flush() {}
            @Override public void close() {}
        };

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);
        LOG.addHandler(memory);

        try {
            String sensitive = "secret-demo-value";
            logTerminalFailure("req-42", "ORDER_FAILED");

            LogRecord event = RECORDS.get(0);
            System.out.println("loggedEvents=" + RECORDS.size());
            System.out.println("level=" + event.getLevel());
            System.out.println("message=" + event.getMessage());
            System.out.println("hasThrowable="
                    + (event.getThrown() != null));
            System.out.println("containsSecret="
                    + event.getMessage().contains(sensitive));
        } finally {
            LOG.removeHandler(memory);
            memory.close();
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac LoggingDecisionDemo.java
java LoggingDecisionDemo
~~~

**Stdout đã được kiểm chứng:**

~~~text
decision LOG-001 status=ACCEPTED owner=platform choice=BOUNDARY_ERROR_ONCE
decision LOG-002 status=ACCEPTED owner=security choice=REDACT_SECRET
decision LOG-003 status=PROPOSED owner=observability choice=SAMPLE_DEBUG
accepted=2 proposed=1
proposedBlocked=true
loggedEvents=1
level=SEVERE
message=strategyId=LOG-001 requestId=req-42 eventCode=ORDER_FAILED outcome=FAILED
hasThrowable=true
containsSecret=false
~~~

### Cách đọc kết quả

- CATALOG chứa hai ACCEPTED và một PROPOSED; accepted("LOG-003") không trả về quyết định hợp lệ nên proposedBlocked=true.
- HashSet kiểm tra ID không trùng, cùng các trường owner/rationale/test không được rỗng. Điều này không thay thế phê duyệt thật.
- logTerminalFailure chỉ dùng LOG-001 và phát một JUL LogRecord với strategyId, requestId, eventCode và outcome.
- getThrown()!=null chứng minh event có Throwable; nó **không chứng minh Throwable có getCause() lồng nhau**.
- containsSecret=false chỉ kiểm tra **message trong ví dụ** không chứa chuỗi giả định; không chứng minh mọi exception, appender và sink đều đã được redact an toàn.
- setUseParentHandlers(false) ngăn event đi tiếp đến parent logger trong test; output thực của appender production có thể khác.

**Giới hạn:** List/ArrayList không phải kho ADR bền vững hoặc thread-safe cho nhiều request. Sử dụng các class logging và collector thực tế, kiểm tra cả async, recovery, security và output sink. Việc một code path gọi accepted() không tự ngăn mọi module khác dùng config chưa được duyệt; cần review/deployment gates và tests xuyên hệ thống.

## 16. Khi dùng SLF4J, Logback và Log4j 2

Trong ứng dụng Spring Boot có SLF4J 2.x, terminal error có thể dùng fluent API:

~~~java
// Fragment trong class có logger SLF4J và biến đã được xác định.
log.atError()
   .addKeyValue("eventCode", "ORDER_FAILED")
   .addKeyValue("requestId", requestId)
   .addKeyValue("outcome", "FAILED")
   .setCause(exception)
   .log("Create order failed");
~~~

Đây **không phải chương trình độc lập**: nó cần dependency SLF4J, backend, biến requestId và exception. addKeyValue tạo metadata của logging event; backend/encoder phải được cấu hình thích hợp để xuất nó như structured field. Không tự khẳng định Logback/Log4j 2 đang lưu JSON chỉ vì fluent API dùng key-value.

Ví dụ **Logback text PatternLayout** có MDC:

~~~xml
<configuration>
  <appender name="CONSOLE"
      class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{ISO8601} %-5level requestId=%X{requestId:-} %logger - %msg%n%ex{full}</pattern>
    </encoder>
  </appender>
  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

Đây là pattern text **không phải JSON Lines**. Nếu ADR chọn JSON, phải cấu hình encoder/layout JSON tương thích và test collector. Log4j 2 dùng ThreadContext và PatternLayout/JSON Template Layout theo dependency/version riêng; không copy class XML của Logback sang Log4j 2.

**MDC cũng cần lifecycle:** set context sớm, clear đúng lúc, propagate qua async/thread pool/Reactor theo framework. Không thể sửa lỗi mất requestId ở async bằng cách viết ADR mà không sửa code/tests.

## 17. Ghi lại các quyết định về runtime business rules

Đôi khi “ghi lại quyết định” còn có nghĩa hệ thống phải ghi **quyết định xử lý nghiệp vụ**: rule engine cho phép/từ chối, feature flag chọn nhánh, fallback chuyển provider, quyền truy cập được chấp nhận/bác bỏ. Đây là **runtime decision event**, liên hệ nhưng khác ADR thiết kế logging.

Ví dụ event có cấu trúc:

~~~json
{
  "timestamp": "2026-11-10T03:30:05Z",
  "eventCode": "RISK_RULE_EVALUATED",
  "requestId": "req-42",
  "ruleId": "RISK_CHECK",
  "policyVersion": "v3",
  "outcome": "DENY",
  "reasonCode": "RULE_THRESHOLD_EXCEEDED"
}
~~~

ADR quyết định **vì sao** runtime event phải có ruleId, policyVersion, outcome và reasonCode; còn event chứng minh **request cụ thể đã đi qua nhánh gì**.

Các lưu ý:

- Ghi reasonCode ổn định thay vì nguyên input thô chứa PII.
- Không tiết lộ secret threshold, password hoặc chi tiết policy bảo mật cho người không có quyền.
- Audit/security events có thể cần bảo toàn dù application logging bị sampling.
- Khi retry hoặc nhiều rule chạy, phân biệt per-rule evaluation với kết quả nghiệp vụ cuối.
- Ghi policyVersion đang thực sự áp dụng, không chỉ version mới nhất trong tài liệu.
- Một runtime event cần requestId/traceId đúng context nếu có; không dùng mã này thay xác thực.
- Không đưa toàn bộ ADR rationale vào mỗi dòng log, gây phình storage và lộ thông tin nội bộ.

Để trả lời “**vì sao kiến trúc chọn ghi trường này?**” xem ADR. Để trả lời “**vì sao request này bị từ chối?**” tra runtime event/audit với quyền phù hợp.

## 18. Gắn ADR với kiểm thử và monitoring

| Decision | Kiểm thử/monitoring cần thiết | Điều dễ sai |
| --- | --- | --- |
| LOG-001 ERROR một lần | Một request fail tạo một terminal ERROR với cause | Đếm stacktrace lines thành events |
| JSON schema v2 | Golden fixtures, type/escaping, readback index | JSON hợp lệ nhưng field sai tên |
| Response correlation | Header requestId khớp log, async không lẫn | MDC rò thread context |
| Secret redaction | Synthetic secret không thấy ở output sinks | Exception message vẫn lộ token |
| DEBUG sampling | Distribution/volume theo rule, không mất audit | Sampling per-line cắt rời trace |
| Security audit routing | Sự kiện tới đúng sink và quyền đọc phù hợp | Appender additivity làm audit lan sang debug |
| Retention | Giữ đủ kỳ và xóa đúng kỳ theo policy | Chỉ xóa file local, bỏ index/backup |
| Full queue policy | Failure-injection khi collector chậm/offline | Drop âm thầm, không có metric |
| Parser migration | Old/new fixtures, data contract, backend query | Regex cũ parse sai log mới |
| Runtime decision event | ruleId/version/outcome đúng, không ghi raw PII | Log nhầm actor/user input |

**Test ở đúng tầng:** unit test kiểm logic event, integration test kiểm Logback/Log4j 2, pipeline test kiểm collector/index, operational test kiểm retention/restore và runbook.

Acceptance “một ERROR mỗi failed request” không có nghĩa **không được ghi security audit**. Tín hiệu khác mục đích có thể cùng tồn tại; test phải phân biệt loại event.

Ngoài test, nên có **monitoring drift**: log volume/day, parser error rate, missing requestId, audit routing errors, retained bytes/age, full queue/drop count và thời gian tra cứu sự cố. Nếu ADR giả định 1 GB/day mà production lên 30 GB/day, cần kích hoạt review thay vì im lặng đổi số trong tài liệu.

## 19. Rollout, rollback và bằng chứng quyết định đã áp dụng

Một quy trình thực tế:

1. Thu thập incident hoặc yêu cầu; đo baseline về log volume, lỗi parser, time-to-diagnose và chi phí.
2. Viết ADR với alternatives và rủi ro đã biết.
3. Review bởi application, platform, SRE, security/compliance theo tác động.
4. ACCEPTED khi đã có người duyệt và acceptance criteria, không đồng nghĩa đã deploy.
5. Mở PR thay code/config, liên kết tới ADR.
6. Test event schema, failure paths, PII, correlation, async và routing.
7. Canary theo service/environ­ment, theo dõi metrics và so với baseline.
8. Kiểm chứng ở **đích cuối** (index/backend), không chỉ dòng console.
9. Nếu không đạt, rollback encoder/config/routing theo plan; xử lý dữ liệu đã ingest nếu schema xung đột.
10. Ghi evidence và implementation status, update runbook/dashboard.
11. Khi rủi ro hoặc điều kiện khác đi, lập ADR mới để thay thế.

**Các đường dẫn PR/test/cấu hình phải là đường dẫn có thật** trong dự án. Không tạo “bằng chứng” bằng cách viết câu DONE vào ADR khi chưa kiểm thử.

Một số quyết định khó rollback: đổi retention có thể đã xóa dữ liệu; thay schema đã tạo documents; sửa audit routing có thể gây gap. Với chúng, cần migration và backup/legal review riêng, không giả định rollback code tự phục hồi dữ liệu đã mất.

## 20. Trường hợp phải đánh giá lại quyết định

- Incident không tìm được log theo requestId hoặc traceId.
- Thay framework/backend major version: JUL, SLF4J, Logback, Log4j 2, Spring Boot.
- Thay shipper, collector, index template, data stream hoặc schema.
- Traffic tăng làm queue full, collector mất sự kiện, cost vượt budget.
- Phát hiện secret/PII trong log hoặc quyền đọc sai.
- Quy định/contract retention, audit hoặc quyền xóa dữ liệu thay đổi.
- Bổ sung Kafka, async jobs, microservices, tenants hoặc vùng triển khai.
- Một lựa chọn sampling làm mất dữ liệu cần điều tra.
- Team đổi trách nhiệm sở hữu, hoặc hiện trạng implementation khác ADR.
- Metrics đạt ngưỡng review đã chốt (parser errors, missing fields, drop counts).

**Không sửa lý do lịch sử của ADR cũ cho “đúng với hiện tại”.** Viết ADR mới với context mới, chỉ rõ supersedes record cũ, hậu quả migration và cách chứng minh sau thay đổi.

Review có chất lượng phải trả lời “các giả định ban đầu còn đúng không?” chứ không chỉ thêm dòng “Reviewed on date ...”.

## 21. Những anti-pattern khi ghi quyết định

**Chỉ ghi lựa chọn, không ghi lý do.** “Dùng Logback” không trả lời vì sao, có thử Log4j 2/JUL hay không, chi phí và khả năng thay đổi.

**Không có owner hoặc status.** Một file Markdown không nói ai duyệt và đang PROPOSED hay ACCEPTED dễ tạo chính sách ngầm.

**ACCEPTED nhưng chưa deploy.** Decision status và implementation status phải tách; có test/evidence thực tế.

**Viết lại ADR cũ khi đổi phương án.** Làm mất lịch sử; nên supersede và liên kết.

**Ghi quá nhiều ADR lặt vặt.** Decision log trở thành danh sách typo config không ai đọc. Chọn quyết định có tác động.

**Tạo một ADR khổng lồ.** Rất khó review riêng privacy, retention, routing, sampling; nên chia theo tradeoff.

**Không có acceptance.** “Log đủ chi tiết” hay “không mất log” không thể kiểm tra. Định nghĩa cụ thể event fields, scope, drop semantics và tests.

**Ghi PII/secret thật vào tài liệu.** History trong Git vẫn tồn tại dù xóa dòng sau này; dùng dữ liệu giả và kiểm soát quyền.

**Cho rằng đọc ADR đủ thay code review.** Phải giữ config, code, collector và policy thực tế đồng bộ.

**Tắt audit để giảm duplicate hoặc volume.** Audit/security là loại event khác với diagnostic stacktrace, không được tắt không qua đánh giá.

**Chỉ sửa code, quên pipeline.** App đã xuất JSON nhưng backend vẫn parse text cũ; contract test phải tới đích.

**Tối ưu cost mà không xét retention/forensics.** Giảm log không phải lý do để xóa chứng cứ bắt buộc hoặc giữ PII quá lâu.

**Không có điều kiện review.** Một quyết định hợp lý khi traffic nhỏ có thể sai khi quy mô thay đổi.

## 22. Bài tập: xây một decision register cho Java API

Một Java service có các triệu chứng:

~~~text
- Log text khác pattern giữa các service.
- Cùng exception bị ghi ERROR ở service và controller.
- Support không tra cứu được requestId từ HTTP response.
- DEBUG chiếm phần lớn dung lượng.
- Không rõ audit được lưu ở đâu và bao lâu.
- Collector đôi lúc quá tải, không có policy drop/retry.
~~~

Cách thực hiện:

1. Tách vấn đề thành các quyết định có phạm vi: error ownership, event schema/correlation, diagnostic volume, audit/retention và reliability.
2. Với mỗi quyết định, đo baseline nếu có; không tự điền số giả vào ADR như số liệu production.
3. Liệt kê ít nhất hai phương án khả thi, gồm lợi/hại, chi phí và risk.
4. Xác định owner/reviewers: API, Observability, Security/Compliance.
5. Viết context, decision, rationale, consequences, tests, rollout, rollback, review triggers.
6. Giữ PROPOSED cho phần còn chờ phê duyệt; không cho triển khai chỉ vì code đã viết.
7. Khi ACCEPTED, liên kết ADR tới PR, config và test tương ứng.
8. Canary với synthetic requests, đo ERROR count, parser correctness, log volume, missing requestId và audit routing.
9. Ghi implementation status trung thực theo evidence.
10. Nếu quyết định không còn phù hợp, tạo ADR mới supersede thay vì xóa lịch sử.

Một người mới gia nhập nhóm phải có thể đọc register và trả lời: **khi nào chúng ta log ERROR, vì sao dùng định dạng này, ai duyệt retention và làm sao kiểm tra hệ thống đang thực thi đúng**.

## 23. Checklist trước khi đóng ADR logging

- [ ] Có ID, tiêu đề rõ, scope và owner.
- [ ] Ghi bối cảnh, yêu cầu, số liệu hoặc giả định.
- [ ] Có alternatives thật và tradeoffs cả tốt lẫn xấu.
- [ ] Kết luận cụ thể, có thể triển khai và kiểm chứng.
- [ ] Phê duyệt đúng vai trò với security/privacy/retention khi liên quan.
- [ ] PROPOSED/ACCEPTED/SUPERSEDED được định nghĩa rõ.
- [ ] Tách decision status khỏi rollout/verification status.
- [ ] Có link tới code/config/schema/tests/dashboard/runbook thực.
- [ ] Có acceptance criteria đo được, không chỉ khẩu hiệu.
- [ ] Có migration, canary, rollback nếu thay đổi nhiều hệ thống.
- [ ] Không có PII/secret trong decision record.
- [ ] Đã đánh giá audit, retention, legal hold, queue failure, sampling.
- [ ] Có review triggers và quy trình supersede giữ lịch sử.
- [ ] Decision register được bảo trì và phù hợp hệ thống đang chạy.

**Kết luận:** Trong **Thiết kế chiến lược log**, “Ghi lại quyết định” là lưu **vì sao** những lựa chọn logging được đưa ra và **làm sao xác minh chúng**. ADR giúp giải thích context, alternatives, decision, rationale, consequences và người chịu trách nhiệm; decision register nối chúng với cấu hình Java, collector, tests và vận hành. Runtime log vẫn là nguồn chứng cứ của sự kiện xảy ra, không phải nơi thay thế tài liệu quyết định kiến trúc.

## 24. Tài liệu tham khảo

- [AWS Prescriptive Guidance — ADR process](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html): context, decision, consequences, status và decision log.
- [AWS Prescriptive Guidance — ADR FAQ](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/faq.html): owner, review và các nội dung tối thiểu.
- [GOV.UK — Documenting Architecture Decisions](https://gds-way.digital.cabinet-office.gov.uk/standards/architecture-decisions.html): version control và lý do ghi nhận quyết định.
- [Martin Fowler — Architecture Decision Record](https://martinfowler.com/bliki/ArchitectureDecisionRecord.html): record ngắn, lifecycle, supersession.
- [Google Cloud — Architecture Decision Records](https://docs.cloud.google.com/architecture/architecture-decision-records): context, options, reasons, implementation consequences.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): event attributes, dữ liệu cần loại, bảo vệ và retention.
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): Timestamp, ObservedTimestamp, SeverityText/Number, Body, Resource và Attributes.
- [SLF4J Manual](https://www.slf4j.org/manual.html): fluent API, key-value fields và Throwable.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html): hierarchy, additivity và backend layout.
- [Logback Manual — Layouts](https://logback.qos.ch/manual/layouts.html): MDC/pattern.
- [Apache Log4j 2 — Architecture](https://logging.apache.org/log4j/2.x/manual/architecture.html): LoggerConfig, routing và Appenders.
- [Oracle Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): LogRecord và Throwable trong ví dụ runnable.
