# Lập kế hoạch cutover, rollback và thu hồi hạ tầng cũ

Di chuyển một ứng dụng sang serverless không kết thúc khi function mới deploy thành công. Hệ thống cũ và mới có thể cùng tồn tại trong một khoảng thời gian; dữ liệu có thể được ghi ở hai nơi; event có thể đến trễ hoặc bị giao lại; DNS, queue, scheduler và client vẫn có thể gọi endpoint cũ. Nếu chuyển traffic mà chưa kiểm soát các yếu tố này, tổ chức có thể tạo ra đơn hàng trùng, mất event, sai trạng thái hoặc không thể quay lại phiên bản trước.

**Cutover** là thời điểm hoặc giai đoạn chuyển một phần/toàn bộ workload từ hệ thống cũ sang hệ thống serverless. **Rollback** là quy trình đưa traffic hoặc xử lý trở lại trạng thái an toàn trước đó khi tiêu chí vận hành/nghiệp vụ không đạt. **Decommission** là thu hồi có kiểm soát hạ tầng cũ sau khi đã xác nhận không còn phụ thuộc và đáp ứng yêu cầu retention, audit, recovery.

Bài này trình bày cách lập kế hoạch migration theo từng wave, chuẩn bị dữ liệu và event, chọn chiến lược traffic cutover, đặt rollback trigger, kiểm tra tính đúng đắn sau chuyển đổi và thu hồi hệ thống cũ. Ví dụ tập trung vào Java FaaS được kích hoạt bởi HTTP, queue, stream, scheduler hoặc event bus.

## 1. Mục tiêu và nguyên tắc migration

### 1.1. Migration thành công được đo bằng outcome

Một migration chỉ được xem là thành công khi workload mới đáp ứng yêu cầu nghiệp vụ và vận hành trong môi trường production. Các tiêu chí thường gồm:

- chức năng và API/event contract giữ đúng hành vi đã cam kết;
- dữ liệu đầy đủ, nhất quán và có thể đối soát;
- latency, availability, throughput và freshness đạt SLO;
- retry, duplicate delivery và partial failure được xử lý an toàn;
- IAM, network, encryption, retention và audit đáp ứng policy;
- cost per successful transaction nằm trong phạm vi chấp nhận;
- đội vận hành có dashboard, runbook, quyền và escalation path;
- có phương án rollback/forward recovery đã diễn tập;
- hạ tầng cũ chỉ bị thu hồi sau khi hết phụ thuộc và hết nhu cầu giữ lại.

Số function đã deploy hoặc tỷ lệ traffic đã chuyển không phải bằng chứng duy nhất cho thành công.

### 1.2. Không chuyển mọi thứ cùng lúc nếu không cần thiết

Chia migration thành các wave theo bounded context, API, tenant, loại event hoặc nhóm workload. Mỗi wave có owner, dependency, data boundary, success criteria và rollback plan riêng.

Wave nhỏ giúp giới hạn blast radius và học từ traffic thật. Tuy nhiên, chia quá nhỏ có thể kéo dài giai đoạn coexistence, dual operations và chi phí chạy song song. Cần cân bằng giữa rủi ro cutover và chi phí duy trì hai hệ thống.

### 1.3. Giữ một source of truth cho mỗi loại dữ liệu

Trong giai đoạn chuyển tiếp, có thể tồn tại bản sao dữ liệu ở cả legacy và serverless. Nhưng với mỗi aggregate/table/entity, phải biết hệ thống nào là writer có thẩm quyền tại từng thời điểm.

Hai hệ thống cùng nhận write độc lập mà không có conflict resolution rõ ràng dễ tạo split-brain. Nếu cần dual-write, dùng outbox/CDC và quy tắc ownership/version; không coi hai lần ghi riêng biệt là atomic.

### 1.4. Rollback phải được thiết kế trước cutover

Không thể chỉ ghi “nếu lỗi thì trỏ traffic về hệ thống cũ”. Rollback có thể không an toàn nếu hệ thống mới đã ghi dữ liệu theo schema mới, phát event mới hoặc thực hiện side effect không thể đảo ngược.

Trước cutover, cần trả lời:

- rollback trong bao lâu sau khi chuyển traffic?
- có thể đưa write mới về hệ thống cũ không?
- dữ liệu mới đã được reverse-sync chưa?
- schema cũ có đọc được dữ liệu mới không?
- event nào đã publish và ai đã consume?
- thao tác nào cần compensation/reconciliation?
- ai có quyền quyết định rollback và trong thời gian bao lâu?

## 2. Khảo sát workload và chọn chiến lược migration

### 2.1. Lập inventory

Trước khi thiết kế cutover, lập danh sách:

- service, API, batch job, cron/scheduler và consumer;
- inbound/outbound dependency;
- database, schema, object storage, cache và search index;
- queue/topic/stream, partition key, retention và consumer group;
- secret, certificate, IAM principal và network path;
- traffic volume, peak/burst, payload size và latency distribution;
- stateful session, local filesystem, connection pool và background thread;
- data classification, residency, retention và recovery requirement;
- service owner, on-call, SLO và cost center.

Với Java application, tìm các giả định không phù hợp với FaaS: process sống lâu, in-memory state, local file bền vững, singleton scheduler, thread nền, connection pool lớn, transaction dài hoặc session gắn với instance.

### 2.2. Baseline trước migration

Đo ít nhất một chu kỳ nghiệp vụ đại diện, gồm giờ cao điểm/thấp điểm nếu có:

- request/event rate và concurrency;
- p50/p95/p99 latency;
- success/error/timeout rate;
- queue lag và oldest message age;
- database CPU/IO/lock wait/connection count;
- retry, duplicate và DLQ rate;
- data volume và growth;
- cost per request và cost per successful transaction;
- operational toil và incident frequency.

Baseline là điểm so sánh sau cutover. Không chỉ so tổng bill vì traffic và business mix có thể thay đổi.

### 2.3. Chọn cách chuyển đổi

| Chiến lược | Cách làm | Khi phù hợp | Rủi ro chính |
| --- | --- | --- | --- |
| Rehost/replatform | Chuyển runtime/deployment với ít thay đổi logic | Ứng dụng tương đối stateless, dependency tương thích | Giữ nguyên coupling và chi phí cũ |
| Refactor theo function | Tách handler theo HTTP/event/workflow | Có bounded context và contract rõ | Thay đổi behavior, transaction boundary |
| Strangler | Chuyển từng capability qua gateway/router | Hệ thống lớn, cần coexistence | Routing và data ownership phức tạp |
| Big-bang | Chuyển toàn bộ trong một cửa sổ | Workload nhỏ, downtime chấp nhận được | Blast radius và rollback lớn |
| Blue-green | Hai stack hoàn chỉnh, chuyển traffic giữa chúng | Có thể giữ hai môi trường tương đương | Data compatibility và chi phí chạy đôi |
| Canary | Chuyển tỷ lệ nhỏ rồi tăng dần | Có traffic phân phối được và telemetry tốt | Phải kiểm soát state/data của cohort |
| Queue drain rồi switch | Dừng/điều tiết producer, xử lý backlog rồi đổi consumer | Workload có ordering hoặc không muốn hai consumer cùng xử lý | Có thể cần downtime và backlog tăng trong lúc drain |
| Read/write split | Chuyển read trước, sau đó chuyển write ownership | Có thể tách query khỏi transaction | Read/write semantics khác nhau và có nguy cơ stale data |

Một migration có thể kết hợp strangler ở cấp capability với canary ở cấp traffic.

### 2.4. Xác định điều kiện không phù hợp

FaaS không tự động phù hợp với mọi workload. Cần đánh giá lại nếu ứng dụng phụ thuộc vào:

- process liên tục chạy hoặc daemon nền;
- kết nối dài hạn không được nền tảng hỗ trợ;
- filesystem cục bộ cần giữ state;
- latency rất chặt nhưng cold start không thể kiểm soát;
- tải liên tục cao khiến container/service luôn chạy kinh tế hơn;
- transaction dài hoặc stateful session xuyên nhiều request;
- library/native runtime không tương thích với môi trường function.

Có thể giữ một số workload trên container/VM và chỉ chuyển phần phù hợp sang FaaS. Mục tiêu là ranh giới vận hành hợp lý, không phải chuyển tất cả bằng mọi giá.

## 3. Thiết kế migration wave và dependency graph

### 3.1. Chia theo business capability

Ví dụ hệ thống thương mại điện tử có thể chia:

1. Notification và email event handler.
2. Catalog read API.
3. Order intake HTTP API.
4. Inventory reservation consumer.
5. Payment workflow.
6. Reporting/export batch.

Không nhất thiết theo thứ tự này. Ưu tiên capability có boundary rõ, ít shared write và khả năng đo kết quả độc lập. Payment/inventory thường cần kiểm soát correctness cao hơn nên cần rehearsal kỹ.

### 3.2. Lập dependency graph

Vẽ các node service, data store, event source, identity và external API; thể hiện hướng đọc/ghi. Mỗi cạnh nên có:

- protocol và contract;
- owner của producer/consumer;
- timeout/retry semantics;
- authentication/authorization;
- schema/version;
- data classification;
- behavior khi dependency lỗi.

Dependency graph giúp phát hiện một function mới vẫn phụ thuộc vào database cũ, scheduler cũ hoặc service khác chưa chuyển.

### 3.3. Wave plan

Mỗi wave nên có record:

| Thuộc tính | Nội dung |
| --- | --- |
| Scope | API/event/tenant/workload được chuyển |
| Owner | Accountable team và technical lead |
| Dependencies | Data, queue, API, IAM, network |
| Migration method | Canary, blue-green, strangler, batch |
| Data plan | Snapshot, CDC, freeze, reconciliation |
| Cutover window | Thời điểm, duration và traffic profile |
| Success criteria | SLO, business correctness, cost |
| Rollback triggers | Ngưỡng cụ thể và cửa sổ đánh giá |
| Rollback steps | Ai làm gì, trong thứ tự nào |
| Hypercare | Người trực, thời gian và dashboard |
| Decommission gate | Điều kiện thu hồi legacy resources |

### 3.4. Thứ tự dependency

Chuyển capability theo dependency graph. Ví dụ nếu consumer mới cần event schema v2 thì producer cũ phải phát schema tương thích hoặc consumer phải đọc được cả v1/v2 trước. Không cutover producer trước khi mọi consumer cần thiết hiểu contract mới.

## 4. Chuẩn bị kiến trúc Java serverless

### 4.1. Tách business logic khỏi adapter

Giữ business logic trong service/domain layer và đặt HTTP, queue, stream hoặc scheduler handler ở adapter. Cách này cho phép chạy cùng logic qua legacy entry point và FaaS adapter trong thời gian coexistence.

```text
HTTP API / Legacy Controller ----+
                                 |
Queue / Stream Function ----------+--> Application Service --> Ports
                                 |                         |
Scheduler Function --------------+                         +--> Repository
                                                           +--> Event Publisher
                                                           +--> External Client
```

Adapter chịu trách nhiệm parse payload, auth context, retry/ack semantics và mapping response. Domain service không nên phụ thuộc trực tiếp vào object event riêng của một cloud provider.

### 4.2. Contract compatibility

Giữ API/event contract tương thích trong giai đoạn chuyển tiếp:

- hỗ trợ field optional mới;
- không đổi ý nghĩa field hiện có;
- version event rõ ràng;
- consumer đọc được schema cũ và mới trong migration window;
- không phát event v2 trước khi consumer cần thiết đã sẵn sàng;
- giữ error semantics và idempotency behavior.

### 4.3. Configuration bên ngoài artifact

Endpoint, table/queue name, feature flag, timeout và concurrency limit nên được cấu hình theo environment. Artifact Java nên bất biến qua dev/staging/production; config revision được ghi trong release record.

Secret được tham chiếu từ secret manager, không nhúng trong JAR/container hoặc file cấu hình version control. Khi cutover, xác nhận runtime identity mới đọc đúng secret và network route.

### 4.4. Stateless handler và state bền vững

Không chuyển state từ singleton/static field sang function rồi giả định warm environment giữ nó. Session, idempotency record, workflow state và checkpoint cần lưu ở dịch vụ bền vững. Local cache chỉ là tối ưu có thể mất.

### 4.5. Java example: route theo migration cohort

Ví dụ application-level router chọn legacy hoặc serverless theo tenant cohort. Quyết định phải ổn định cho một tenant trong một wave và được ghi lại để điều tra:

```java
public enum ProcessingTarget {
    LEGACY,
    SERVERLESS
}

public interface MigrationCohortPolicy {
    ProcessingTarget targetFor(String tenantId);
}

public final class OrderFacade {
    private final MigrationCohortPolicy policy;
    private final OrderProcessor legacy;
    private final OrderProcessor serverless;

    public OrderFacade(
            MigrationCohortPolicy policy,
            OrderProcessor legacy,
            OrderProcessor serverless) {
        this.policy = policy;
        this.legacy = legacy;
        this.serverless = serverless;
    }

    public OrderResult submit(String tenantId, OrderCommand command) {
        return switch (policy.targetFor(tenantId)) {
            case LEGACY -> legacy.submit(tenantId, command);
            case SERVERLESS -> serverless.submit(tenantId, command);
        };
    }
}
```

Đây là router minh họa. Policy nên lấy từ feature/config service có audit, có fallback an toàn và không thay đổi ngẫu nhiên giữa retry. Nếu một business transaction bắt đầu ở legacy, mọi bước tiếp theo phải biết owner/route của transaction đó để tránh một phần chạy legacy, phần khác chạy serverless ngoài ý muốn.

## 5. Data migration: snapshot, CDC và đồng bộ cuối

### 5.1. Chọn chiến lược dữ liệu

| Cách | Mô tả | Phù hợp | Lưu ý |
| --- | --- | --- | --- |
| Offline copy | Dừng write, export/import rồi mở hệ thống mới | Dataset nhỏ, downtime chấp nhận được | Đơn giản nhưng cần cửa sổ dừng rõ |
| Snapshot + CDC | Copy snapshot, sau đó phát các thay đổi mới qua CDC | Dataset lớn, downtime ngắn | Cần xử lý ordering, lag và checkpoint |
| Replication liên tục | Đồng bộ dữ liệu trong giai đoạn coexistence | Cần cutover linh hoạt | Xác định một chiều/owner; tránh multi-master ngoài kế hoạch |
| Logical export/import | Chuyển qua file/format trung gian | Khác database engine/schema | Cần validate encoding, type và constraint |
| Event replay | Rebuild read model từ event log | Event history đầy đủ và replay an toàn | Phụ thuộc retention, ordering và idempotency |

### 5.2. Snapshot + CDC

Một quy trình phổ biến:

1. Chụp snapshot nhất quán tại thời điểm T0.
2. Import snapshot vào target database.
3. Bắt đầu/tiếp tục CDC từ vị trí tương ứng với T0.
4. Apply change theo thứ tự cần thiết và giữ checkpoint.
5. Theo dõi replication lag và lỗi apply.
6. Khi cutover, chặn write mới ở source hoặc chuyển write owner theo kế hoạch.
7. Drain transaction đang chạy và đợi CDC đến watermark cuối.
8. Chạy checksum/count/reconciliation.
9. Mở write path trên target.

Phải hiểu semantics của công cụ CDC: snapshot boundary, transaction ordering, delete/tombstone, schema change và retry. Không tự suy ra “lag bằng 0” đồng nghĩa mọi dữ liệu nghiệp vụ đã đúng.

### 5.3. Tránh dual-write tùy tiện

Mẫu Java ghi legacy DB rồi target DB bằng hai câu lệnh độc lập có failure mode:

- legacy commit, target fail;
- target commit, legacy fail;
- response timeout khiến caller retry và ghi hai lần;
- một DB nhận update mới hơn trước, thứ tự thay đổi khác nhau.

Nếu cần dual-write, dùng CDC/outbox hoặc một cơ chế replication có semantics rõ. Nếu buộc phải ghi hai nơi, lưu operation ID, version và trạng thái đồng bộ; có reconciliation và repair process. Không giả định hai database commit atomic.

### 5.4. Một writer có thẩm quyền

Trong từng giai đoạn, xác định hệ thống nào nhận write chính:

| Giai đoạn | Source | Target | Quy tắc |
| --- | --- | --- | --- |
| Initial copy | Writer chính | Read/replica | Snapshot + CDC source → target |
| Canary read | Writer chính | Read-only/candidate | So sánh kết quả, không cho target phát side effect |
| Canary write | Theo cohort | Writer cho cohort được chuyển | Một owner cho mỗi aggregate/tenant |
| Full cutover | Read-only/retired writer | Writer chính | Chặn write source và xác minh target |
| Rollback window | Theo rollback design | Theo rollback design | Reverse sync hoặc forward recovery đã được chuẩn bị |

Nếu cần split ownership theo tenant, routing và data partition phải bảo đảm một tenant không bị hai hệ thống cùng làm writer.

### 5.5. Schema expand-migrate-contract

Khi thay đổi schema:

1. **Expand:** thêm field/table/index tương thích ngược.
2. **Migrate:** deploy reader/writer tương thích và backfill dữ liệu.
3. **Validate:** kiểm tra dữ liệu cũ/mới và consumer compatibility.
4. **Contract:** chỉ xóa field/format cũ sau khi mọi reader/writer cũ đã dừng và rollback window kết thúc.

Không xóa cột hoặc đổi meaning ngay trước cutover nếu rollback cần binary cũ đọc dữ liệu target. Giữ compatibility đủ lâu cho cả release rollback và delayed event.

### 5.6. Kiểm tra dữ liệu

Kiểm tra theo nhiều lớp:

- row/document count theo partition/tenant/time window;
- checksum/hash trên dữ liệu đã chuẩn hóa;
- aggregate totals như balance, inventory và order count;
- null/missing field và enum value;
- foreign key/reference consistency;
- duplicate business key;
- timestamp/timezone và precision;
- sequence/version gap;
- event/outbox/inbox reconciliation.

Count khớp không bảo đảm nội dung khớp. Checksum toàn bảng có thể đắt; có thể kiểm tra theo partition, sample và các invariant nghiệp vụ quan trọng.

## 6. Event migration và consumer cutover

### 6.1. Tránh hai consumer cùng tạo side effect

Nếu legacy consumer và function mới cùng đọc một queue/topic, mỗi message có thể được xử lý hai lần. Điều này chỉ an toàn nếu consumer có idempotency chung và semantics cho phép. Thông thường cần một trong các cách:

- consumer group/queue ownership riêng và chuyển subscription;
- pause legacy consumer trước khi bật consumer mới;
- route theo partition/key hoặc tenant cohort;
- mirror event vào môi trường shadow nhưng không thực hiện side effect;
- dedup bằng event ID/business operation ID dùng chung.

### 6.2. Queue cutover

Trước cutover:

- xác định message đang in-flight và visibility/lease timeout;
- dừng producer hoặc route message mới sang target;
- đợi legacy consumer hoàn tất hoặc lưu trạng thái checkpoint;
- xác nhận queue depth/oldest message age;
- bật consumer mới theo concurrency cap;
- theo dõi duplicate, DLQ và business completion.

Nếu queue cũ còn backlog, quyết định xử lý hết ở legacy, drain sang queue mới hay chuyển nguyên queue phụ thuộc ordering và schema. Không copy message tùy tiện khi consumer cũ vẫn đang xử lý.

### 6.3. Stream cutover

Với Kafka/Kinesis hoặc stream tương tự, xác định:

- partition/shard assignment;
- committed offset/checkpoint;
- consumer group identity;
- retention window;
- ordering scope;
- replay behavior;
- schema compatibility.

Consumer mới có thể bắt đầu từ offset cũ, offset mới hoặc timestamp. Chọn sai điểm bắt đầu gây mất hoặc xử lý lặp record. Lưu checkpoint và event ID; idempotency bảo vệ duplicate nhưng không thay thế việc chọn đúng offset.

### 6.4. Scheduled job migration

Một cron job cũ và scheduler mới có thể cùng chạy trong cùng phút. Dùng một scheduler owner tại một thời điểm, lock/lease có fencing hoặc job idempotency key theo logical schedule window. Xác nhận timezone, daylight saving behavior, missed invocation và catch-up policy.

### 6.5. Event schema và delayed delivery

Event phát trước cutover có thể đến sau cutover. Consumer mới phải đọc schema cũ trong retention/replay window hoặc có translator. Không xóa schema cũ ngay sau khi producer mới deploy.

## 7. Shadow traffic và validation trước cutover

### 7.1. Shadow mode

Shadow traffic gửi bản sao request/event đến hệ thống mới để so sánh kết quả nhưng không cho phép hệ thống mới thực hiện side effect production. Ví dụ function mới chạy validation và tính response; kết quả được log/compare, không charge payment hoặc gửi email.

Shadow giúp phát hiện khác biệt behavior, latency và lỗi tương thích. Tuy nhiên, dữ liệu shadow cần được bảo vệ và không tạo tải vượt capacity target.

### 7.2. So sánh kết quả

So sánh các thuộc tính có ý nghĩa:

- status/decision code;
- normalized response fields;
- business invariants;
- generated event type/payload;
- calculated totals/rounding;
- validation errors;
- latency và dependency usage.

Loại bỏ timestamp, random ID hoặc field không deterministic trước khi so sánh. Không chỉ so byte-for-byte nếu thứ tự field hoặc metadata khác nhau nhưng semantics giống nhau.

### 7.3. Không để shadow gây side effect

Tạo identity/resource riêng cho shadow và deny quyền write/send/charge nếu có thể. Nếu không thể bảo đảm read-only, dùng mock/sandbox cho dependency side effect. Gắn `shadow=true` vào telemetry nhưng đừng chỉ dựa vào một header caller có thể giả mạo để bảo vệ production data.

### 7.4. Exit criteria cho shadow

- không có khác biệt correctness nghiêm trọng chưa giải thích;
- schema và auth context tương thích;
- p95/p99 và concurrency nằm trong budget;
- không có write/email/payment side effect ngoài ý muốn;
- dependency quota và cost có headroom;
- các error class đã có owner và remediation.

## 8. Chiến lược traffic cutover

### 8.1. Big-bang cutover

Chuyển toàn bộ traffic trong một cửa sổ bảo trì. Trình tự thường gồm freeze change, drain in-flight work, final data sync, switch routing, smoke test và theo dõi.

Ưu điểm là ranh giới ownership rõ sau chuyển đổi. Nhược điểm là blast radius lớn và cần rollback nhanh. Chỉ dùng khi workload, downtime và recovery plan cho phép.

### 8.2. Blue-green

Blue (legacy) và green (serverless) cùng được chuẩn bị. Router chuyển traffic sang green; blue được giữ sẵn trong rollback window.

Blue-green dễ chuyển traffic nhưng không tự giải quyết database compatibility. Nếu green ghi schema mà blue không đọc được, rollback routing có thể làm hỏng dữ liệu. Cần expand-migrate-contract và write ownership.

### 8.3. Canary theo tỷ lệ

Chuyển một phần traffic: 1%, 5%, 10%, 25%, 50%, rồi 100% là một ví dụ. Tỷ lệ thực tế phụ thuộc volume và risk. Ở mỗi bước, giữ thời gian quan sát đủ dài để có sample đại diện cho business cycle.

Canary có thể theo:

- weighted routing ở gateway/load balancer;
- function alias/version routing;
- tenant cohort;
- account/customer segment;
- API route hoặc operation type;
- event partition/group.

Không phân cohort ngẫu nhiên cho từng retry nếu cùng một business transaction có thể chạy trên cả hai hệ thống. Dùng routing ổn định theo transaction/tenant và lưu quyết định route.

### 8.4. Strangler routing

Gateway/router gửi capability đã chuyển sang function mới và phần còn lại đến legacy. Dần dần legacy chỉ còn các capability chưa migration.

Router cần xử lý auth, timeout, header, correlation ID, rate limit và error mapping nhất quán. Tránh tạo vòng gọi legacy → gateway → function → legacy ngoài ý muốn.

### 8.5. DNS cutover

DNS có cache ở client, resolver và proxy. Giảm TTL trước migration có thể giúp rút ngắn propagation, nhưng không bảo đảm mọi client đổi ngay. Với HTTP API, gateway/edge routing thường dễ kiểm soát hơn DNS đơn thuần.

Nếu dùng DNS:

- kiểm tra TTL thực tế và client behavior;
- giữ endpoint cũ hoạt động trong rollback window;
- không thu hồi certificate/network route cũ ngay;
- theo dõi traffic thực tế đến endpoint cũ;
- chuẩn bị cách xử lý client pinning hoặc cache lâu.

### 8.6. Feature flag và kill switch

Feature flag cho phép chuyển capability hoặc tenant theo cấu hình. Cần có:

- owner và approval;
- audit log thay đổi;
- default/fallback behavior;
- cache/propagation behavior;
- kill switch có kiểm thử;
- expiry date để xóa flag sau migration.

Flag không nên là cấu hình vô thời hạn. Flag cũ làm routing khó hiểu và tăng nguy cơ split traffic.

## 9. Quy trình cutover chi tiết

### 9.1. Trước ngày cutover

**T-14 đến T-7 ngày** (ví dụ, điều chỉnh theo dự án):

- hoàn tất dependency inventory và ownership;
- chạy load, soak, chaos/failure test trong phạm vi an toàn;
- hoàn tất snapshot/CDC và schema compatibility;
- kiểm thử rollback trên môi trường tương đương;
- xác nhận IAM, network, secret và quota production;
- kiểm tra dashboard, alert và runbook;
- chốt SLO, business validation và rollback threshold;
- thông báo stakeholder/support và provider nếu cần.

**T-1 ngày:**

- freeze thay đổi không liên quan;
- xác nhận artifact digest/config revision;
- xác nhận backup/snapshot và restore point;
- kiểm tra replication lag, queue backlog và scheduler ownership;
- xác nhận người trực, decision maker và escalation channel;
- kiểm tra thời gian đồng bộ giữa hệ thống và timestamp.

### 9.2. Trong cutover window

1. Mở incident/change bridge và xác nhận người ra quyết định.
2. Kiểm tra health của legacy và target trước thay đổi.
3. Tạm dừng hoặc giới hạn write/producer theo kế hoạch.
4. Drain in-flight request/message và ghi checkpoint.
5. Đợi CDC/replication đến watermark đã định.
6. Chạy final reconciliation/consistency check.
7. Chuyển routing hoặc consumer ownership.
8. Mở traffic theo cohort/tỷ lệ đã chọn.
9. Chạy smoke test kỹ thuật và business transaction test.
10. Quan sát error, latency, queue age, data correctness và cost.
11. Tăng traffic theo gate; dừng ngay khi vượt rollback trigger.
12. Ghi timestamp và quyết định từng bước vào change record.

### 9.3. Sau cutover

- giữ legacy ở read-only hoặc standby theo rollback design;
- theo dõi traffic còn đến legacy;
- đối soát data và event theo cohort;
- kiểm tra retry/DLQ và duplicate side effect;
- theo dõi SLO và cost per successful transaction;
- cập nhật service catalog và on-call ownership;
- duy trì hypercare trong khoảng thời gian đã thống nhất.

## 10. Readiness gate và tiêu chí thành công

### 10.1. Technical readiness

- artifact đã ký/scan và digest được ghi;
- Java runtime/dependency tương thích;
- IAM least privilege và network path đã kiểm thử;
- timeout, memory, concurrency, retry và DLQ cấu hình đúng;
- API/event contract tương thích;
- dashboard, log, trace và alert hoạt động;
- quota/capacity đủ cho peak và retry;
- backup/restore và rollback được diễn tập.

### 10.2. Data readiness

- snapshot/CDC checkpoint rõ;
- replication lag trong ngưỡng;
- schema tương thích hai chiều trong rollback window;
- row count/checksum/invariant đã xác minh;
- writer ownership không mơ hồ;
- event ID, version và idempotency được giữ;
- dữ liệu nhạy cảm được bảo vệ đúng policy.

### 10.3. Operational readiness

- service owner, on-call và escalation đã xác nhận;
- runbook có người thực hiện thử;
- decision maker và rollback authority sẵn sàng;
- change record/approval đầy đủ;
- provider support path đã biết;
- hypercare schedule có coverage.

### 10.4. Business readiness

- business owner xác nhận acceptance criteria;
- đối soát số lượng/giá trị nghiệp vụ;
- customer communication/support script sẵn sàng;
- downtime/degraded mode được chấp thuận;
- compliance/data residency sign-off hoàn tất nếu cần.

### 10.5. Success criteria phải định lượng

Ví dụ cho một API order:

| Metric | Gate minh họa |
| --- | --- |
| HTTP success rate | Không thấp hơn baseline quá 0,2 điểm phần trăm trong 30 phút |
| p95 latency | Không vượt SLO đã công bố |
| Duplicate order | 0 duplicate business order trong reconciliation window |
| Payment/inventory invariant | Không có discrepancy chưa giải thích |
| Queue age | Trong freshness SLO |
| DLQ rate | Không tăng vượt threshold đã phê duyệt |
| Cost per completed order | Không vượt guardrail đã thống nhất sau khi normalize traffic |

Các ngưỡng trên chỉ là ví dụ. Đặt threshold theo baseline, SLO và risk appetite của service. Chọn cửa sổ quan sát đủ dài để tránh quyết định từ một spike ngắn.

## 11. Rollback: quyết định, điều kiện và trình tự

### 11.1. Rollback trigger

Trigger nên gồm cả technical và business signal:

- error/timeout rate vượt threshold liên tục;
- p95/p99 latency vi phạm SLO;
- consumer lag/oldest message age tăng không kiểm soát;
- database throttling/connection saturation;
- data checksum, balance, inventory hoặc order reconciliation sai;
- duplicate/missing event vượt ngưỡng;
- security/IAM/data exposure incident;
- cost spike do retry/event loop;
- target không thể xử lý trong capacity/quota.

Một trigger nghiêm trọng như dữ liệu sai hoặc lộ dữ liệu có thể yêu cầu dừng ngay, không chờ hết cửa sổ quan sát.

### 11.2. Rollback decision record

Ghi:

- trigger và metric/evidence;
- thời điểm bắt đầu ảnh hưởng;
- scope/cohort/region;
- decision maker;
- lựa chọn rollback hay forward-fix;
- data write/event đã xảy ra;
- thứ tự hành động và owner;
- điều kiện xác nhận phục hồi.

### 11.3. Rollback routing không đồng nghĩa rollback data

Đổi traffic về legacy chỉ thay đổi đường đi request. Nếu target đã ghi dữ liệu mới, legacy có thể không nhìn thấy hoặc không hiểu dữ liệu đó. Trước rollback, xác định:

- target có phát sinh write không;
- CDC/reverse replication có đưa write về legacy không;
- có thể đưa source về writer hay phải giữ target làm source of truth;
- schema có tương thích không;
- event đã publish có thể bị consumer legacy xử lý không;
- side effect ngoài database đã xảy ra chưa.

Nếu không có reverse sync an toàn, có thể cần giữ target làm writer và forward-fix, hoặc tạm dừng write rồi reconcile trước khi chuyển. Không flip-flop writer tùy tiện.

### 11.4. Quy trình rollback có kiểm soát

1. Kích hoạt incident/change procedure và xác định decision maker.
2. Dừng tăng canary/traffic; nếu cần, chặn write mới.
3. Ghi lại target checkpoint, CDC position, queue offsets và transaction IDs.
4. Xác định hệ thống đang có authoritative data.
5. Chọn reverse sync, restore, compensation hoặc forward-fix.
6. Chuyển traffic/consumer về target an toàn theo routing plan.
7. Xác nhận legacy đọc được state và event/schema hiện tại.
8. Chạy reconciliation và duplicate/missing event checks.
9. Mở traffic theo giới hạn và theo dõi SLO.
10. Giữ target/legacy ở trạng thái phục vụ điều tra cho đến khi sign-off.

### 11.5. Rollback, roll-forward và compensation

| Cách | Mô tả | Khi phù hợp |
| --- | --- | --- |
| Rollback code/routing | Trở về artifact/route trước | Dữ liệu và contract vẫn tương thích |
| Roll-forward fix | Sửa lỗi trên target rồi tiếp tục | Data đã đổi, rollback không an toàn hoặc fix nhanh hơn |
| Compensation | Tạo thao tác nghiệp vụ bù | Side effect đã commit và có nghiệp vụ đảo/bù |
| Restore/replay | Khôi phục snapshot hoặc replay event | Mất/sai dữ liệu, có recovery point và replay plan |
| Stop-the-write | Tạm dừng write để bảo toàn consistency | Có nguy cơ split-brain hoặc data corruption |

Rollback không luôn là lựa chọn tốt nhất. Quyết định phụ thuộc data state, compatibility, business impact và thời gian phục hồi.

### 11.6. Thao tác rollback theo nền tảng

| Nền tảng | Cách đưa workload về trạng thái ổn định | Điều cần xác minh |
|---|---|---|
| AWS Lambda | Đưa alias về version trước hoặc để CodeDeploy rollback deployment | Alias target, event source mapping, resource permission và Provisioned Concurrency |
| API Gateway | Khôi phục integration/route hoặc stage deployment trước | Stage đang active, authorizer, cache và integration timeout |
| Azure Functions | Swap slot lại hoặc deploy artifact ổn định | Slot-specific settings, hostname, trigger listener và app settings |
| Azure API Management | Khôi phục backend/policy/revision đã ổn định | Backend target, policy, subscription và health |
| Queue consumer | Dừng consumer mới, bật consumer cũ theo runbook | In-flight message, checkpoint, duplicate và DLQ |
| DNS | Khôi phục record trước nếu dùng DNS cutover | Resolver/client cache, TTL và connection reuse |

Các thao tác cụ thể phụ thuộc deployment mechanism và cấu hình môi trường. Hãy diễn tập trong staging để xác nhận operator có quyền và biết đúng alias, slot, route hoặc consumer cần đổi.

#### AWS Lambda: alias và CodeDeploy

Lambda version là snapshot bất biến của code và một số cấu hình. Alias như `live` tạo ARN ổn định cho caller trong khi version phía sau có thể thay đổi. CodeDeploy hỗ trợ traffic shifting theo canary/linear và có thể dừng hoặc rollback khi alarm/hook thất bại.

Ví dụ AWS SAM rút gọn:

```yaml
Resources:
  CatalogFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: com.example.catalog.CatalogHandler::handleRequest
      CodeUri: target/catalog-function.zip
      AutoPublishAlias: live
      DeploymentPreference:
        Type: Canary10Percent5Minutes
        Alarms:
          - !Ref CatalogFunctionErrorsAlarm
```

Đây là phần cấu hình minh họa; stack cần định nghĩa alarm, IAM, API integration và các thuộc tính còn lại. Caller nên invoke alias thay vì pin trực tiếp version nếu cần chuyển đổi nhanh. Kiểm tra event source mapping có trỏ đến function/alias nào và resource-based permission vẫn cho phép trigger gọi đúng đích. Rollback alias không đảo ngược database write, message hoặc side effect đã xảy ra.

#### Azure Functions: deployment slot và swap

Trên hosting plan hỗ trợ deployment slots, deploy candidate vào staging slot, warm-up và chạy smoke test trước khi swap với production. Nếu lỗi sau swap, có thể swap lại hoặc deploy artifact ổn định theo runbook.

1. Deploy artifact vào staging slot.
2. Gắn cấu hình staging riêng và đánh dấu setting cần giữ theo slot (slot-specific/sticky setting).
3. Warm up runtime và kiểm tra hostname staging.
4. Xác nhận trigger listener không xử lý nhầm queue production.
5. Chạy smoke test và kiểm tra Application Insights.
6. Swap staging với production, sau đó xác minh hostname, auth và function execution.
7. Nếu không đạt, swap lại hoặc redeploy artifact ổn định.

Với Queue, Service Bus hoặc Timer trigger, staging slot có thể khởi chạy listener. Nếu cả staging và production cùng kết nối queue thật, hai listener có thể cạnh tranh message hoặc xử lý song song. Dùng queue test, cấu hình listener phù hợp hoặc quy trình chuyển consumer rõ ràng. Kiểm tra hosting plan/OS hỗ trợ slots trước khi dựa vào swap làm cơ chế rollback.

## 12. Data reconciliation sau cutover hoặc rollback

### 12.1. Đối soát theo business invariant

Đừng chỉ so row count. Với order/payment/inventory, đối chiếu:

- số order theo status/tenant/time window;
- tổng amount/currency theo ledger;
- reserved/available inventory;
- payment captured/refunded/unknown;
- event produced/consumed/failed;
- outbox/inbox pending và duplicate;
- aggregate version và sequence gap.

### 12.2. Xử lý unknown outcome

Nếu request timeout nhưng payment provider có thể đã capture, không gửi charge mới ngay. Query provider theo idempotency key/operation ID, reconcile ledger và chỉ thực hiện hành động tiếp theo sau khi trạng thái rõ.

### 12.3. Reconciliation report

Một report nên có:

| Trường | Ý nghĩa |
| --- | --- |
| Scope | Cohort, tenant, partition và time range |
| Source/target watermark | Điểm dữ liệu đã đồng bộ |
| Count delta | Chênh lệch số record |
| Amount/aggregate delta | Chênh lệch tổng nghiệp vụ |
| Missing/duplicate IDs | Event hoặc transaction bị thiếu/trùng |
| Version/sequence gaps | Khoảng trống thứ tự |
| Exceptions | Các sai lệch cần điều tra |
| Decision | Accept, repair, replay hoặc stop |
| Owner/evidence | Người xác nhận và tài liệu kèm theo |

### 12.4. Repair phải idempotent và có audit

Repair script/job nên có dry-run, giới hạn scope, operation ID, audit log và khả năng resume. Không chạy update hàng loạt không có checkpoint. Với dữ liệu tài chính hoặc nhạy cảm, cần approval theo policy và đối soát độc lập sau repair.

## 13. Hypercare và theo dõi sau chuyển đổi

### 13.1. Hypercare

Hypercare là giai đoạn hỗ trợ tăng cường ngay sau cutover. Xác định:

- thời gian bắt đầu/kết thúc;
- primary/secondary on-call;
- business owner và platform contact;
- dashboard/war-room;
- cadence cập nhật stakeholder;
- điều kiện kết thúc hypercare;
- owner cho issue tồn đọng.

### 13.2. Dashboard cutover

Theo dõi song song legacy và target:

- traffic split theo route/cohort;
- success/error/timeout rate;
- latency p50/p95/p99;
- invocation/concurrency/throttle/cold start;
- queue lag, oldest message age và DLQ;
- database CPU/IO/connection/lock/replication lag;
- data discrepancy và business completion;
- retry amplification và duplicate rate;
- cost per successful transaction.

Phân tách shadow traffic khỏi production traffic để tránh đọc nhầm success rate/cost.

### 13.3. Tiêu chí kết thúc hypercare

- SLO ổn định qua một chu kỳ nghiệp vụ đại diện;
- không có discrepancy nghiêm trọng chưa xử lý;
- backlog/DLQ ở mức bình thường;
- alert noise và runbook đã được hiệu chỉnh;
- support/on-call team đã tiếp nhận ownership;
- rollback window đã đóng hoặc được gia hạn có owner;
- decommission gate được review.

## 14. Thu hồi hạ tầng cũ (decommission)

### 14.1. Không xóa legacy ngay khi traffic mới đạt 100%

Legacy có thể còn được dùng bởi:

- client cũ hoặc DNS cache;
- scheduled job/cron chưa chuyển;
- webhook subscription;
- queue consumer hoặc DLQ replay;
- report/export job;
- admin script và support tool;
- backup/restore hoặc audit;
- hệ thống downstream gọi private endpoint cũ.

Phải xác minh không còn traffic và dependency thực tế, không chỉ dựa vào danh sách kiến trúc.

#### Quarantine trước khi xóa

Trước khi xóa resource, có thể tạm ngừng hoặc cô lập legacy trong một khoảng quan sát:

1. Disable listener, scheduler hoặc job cũ theo kế hoạch.
2. Chặn ingress mới đến endpoint legacy nhưng giữ access log/metric để phát hiện caller còn sót.
3. Theo dõi qua ít nhất một chu kỳ hoạt động của batch/scheduled client quan trọng.
4. Nếu xuất hiện caller hợp lệ, khôi phục đường truy cập hoặc chuyển caller trước khi tiếp tục.

Chọn thời gian quarantine theo traffic pattern. Một job chạy hàng tháng không thể được xác nhận là không còn dùng chỉ bằng vài ngày không có request.

### 14.2. Decommission gate

Chỉ bắt đầu thu hồi khi:

- traffic đến legacy bằng 0 hoặc chỉ còn traffic đã được giải thích;
- mọi writer/consumer/scheduler đã chuyển;
- target đạt SLO và business acceptance trong hypercare;
- data reconciliation hoàn tất;
- rollback window kết thúc và có sign-off;
- backup/export/retention/legal hold được xử lý;
- owner đã duyệt xóa resource và dữ liệu;
- có inventory đầy đủ resource, dependency và credential liên quan.

### 14.3. Trình tự thu hồi

1. Đánh dấu legacy read-only hoặc disable entry point theo kế hoạch.
2. Theo dõi access log/metrics để phát hiện client còn gọi.
3. Disable scheduler, event subscription, webhook và consumer cũ.
4. Drain queue hoặc lưu archive theo retention policy.
5. Export/backup dữ liệu cần giữ và thử khả năng đọc lại.
6. Thu hồi IAM role, access key, secret, certificate và cross-account trust không còn dùng.
7. Gỡ DNS record, route, load balancer, NAT rule, firewall và network path cũ sau khi xác minh.
8. Xóa compute/database/storage resource theo approval và deletion protection policy.
9. Xác nhận log/audit/billing evidence được lưu đúng retention.
10. Cập nhật service catalog, CMDB, diagrams, cost allocation và runbook.
11. Theo dõi hóa đơn và alert để phát hiện resource còn sót.

Không xóa backup hoặc dữ liệu chỉ vì compute resource đã dừng. Retention, legal hold, data residency và audit policy có thể yêu cầu giữ dữ liệu lâu hơn.

### 14.4. Thu hồi theo lớp

| Lớp | Hành động | Kiểm tra trước khi xóa |
| --- | --- | --- |
| Compute | Stop/scale to zero/delete VM/container/service | Không còn traffic, process hoặc scheduled task |
| Network | Gỡ route, security group, NAT, endpoint, load balancer | Không còn consumer/client phụ thuộc |
| Identity | Revoke role/key/trust/policy | Không còn workload dùng principal |
| Data | Archive/delete database, file, cache | Retention, legal hold, backup và reconciliation |
| Messaging | Disable subscription/consumer, archive queue/topic | Offset, backlog, DLQ và replay đã xử lý |
| DNS/certificate | Gỡ record/cert/binding | TTL/client cache và endpoint cũ không còn cần |
| Observability | Ngừng agent/metric/log pipeline cũ | Audit/retention evidence đã lưu |
| Billing | Xóa capacity/license/commitment không cần | Không làm ảnh hưởng workload khác dùng chung |

### 14.5. Decommission evidence

Lưu bằng chứng:

- approval và change record;
- danh sách resource đã xóa/giữ;
- traffic/access check;
- backup/retention reference;
- IAM revocation result;
- data deletion confirmation nếu áp dụng;
- cost before/after;
- owner sign-off và ngày hoàn tất.

### 14.6. IaC và bảo vệ khỏi xóa nhầm

Khi resource được quản lý bằng IaC, xóa block resource khỏi code có thể khiến lần `apply` tiếp theo phá hủy resource. Trước khi thay đổi:

- xác nhận workspace/state đúng môi trường và đúng account/subscription;
- kiểm tra dependency và resource dùng chung;
- đọc plan để biết chính xác resource nào bị destroy/replace;
- dùng deletion protection hoặc `prevent_destroy` cho resource dữ liệu quan trọng trong thời gian migration;
- dùng retain policy hoặc snapshot trước khi xóa nếu cần giữ dữ liệu;
- không dùng `terraform destroy` cho toàn bộ workspace chỉ để retire một endpoint.

Ví dụ Terraform lifecycle guard cho database:

```hcl
resource "aws_db_instance" "legacy" {
  identifier        = "legacy-orders"
  allocated_storage = 100
  engine            = "postgres"
  instance_class    = "db.t4g.medium"

  deletion_protection = true

  lifecycle {
    prevent_destroy = true
  }
}
```

Đây là ví dụ minh họa, không phải cấu hình database production hoàn chỉnh. `prevent_destroy` khiến Terraform từ chối plan destroy khi resource block và lifecycle guard vẫn còn trong configuration; deletion protection là lớp bảo vệ phía dịch vụ. Khi đã đủ điều kiện retire, thay đổi gỡ guard phải được review, tạo snapshot/retention cần thiết và kiểm tra plan trước khi apply. Không bỏ guard chỉ để làm cho pipeline xanh.

## 15. Java migration example: idempotency và route stability

### 15.1. Giữ operation ID xuyên qua hai hệ thống

Khi caller gửi order, tạo/nhận business operation ID ổn định. Cả legacy và serverless adapter phải hiểu cùng key và cùng semantics. Không tạo key mới mỗi lần router đổi target.

```java
public record OrderCommand(
        String operationId,
        String orderId,
        String tenantId,
        long amountMinor) {
}

public interface OrderProcessor {
    OrderResult submit(String tenantId, OrderCommand command);
}

public interface IdempotencyStore {
    // Atomically claims an operation key or returns its prior result.
    IdempotencyDecision begin(String scope, String operationId);
}
```

`IdempotencyStore` phải được chia sẻ bởi hai đường xử lý hoặc có cơ chế deduplication thống nhất. Nếu legacy và serverless dùng hai kho idempotency riêng, cùng operation có thể được xử lý một lần ở mỗi hệ thống.

### 15.2. Route decision phải ổn định

Nếu tenant A được chuyển sang serverless, retry của transaction A vẫn phải đi đến target phù hợp hoặc target phải nhận biết operation đã bắt đầu ở legacy. Không chọn target bằng random mỗi request. Lưu cohort assignment và transaction owner trong cấu hình/state bền vững.

### 15.3. Không dual-write business side effect khi shadow

Shadow invocation chỉ tính/so sánh kết quả. Nó không được charge, reserve inventory, gửi email hoặc publish event production. Tách permission và endpoint sandbox để giới hạn side effect.

## 16. Cutover runbook mẫu

### Trước cutover

- [ ] Change record và stakeholder communication được duyệt.
- [ ] Primary/secondary on-call và decision maker đã xác nhận.
- [ ] Target health, quota, IAM, network và secret đã kiểm tra.
- [ ] Snapshot/CDC checkpoint và replication lag đạt ngưỡng.
- [ ] Queue/stream/scheduler ownership đã rõ.
- [ ] Legacy/target schema compatibility đã xác minh.
- [ ] Dashboard/alert và business reconciliation sẵn sàng.
- [ ] Rollback/forward recovery đã diễn tập.
- [ ] Backup/restore point và data retention đã xác nhận.

### Thực hiện

- [ ] Freeze thay đổi không liên quan.
- [ ] Pause hoặc route producer theo kế hoạch.
- [ ] Drain in-flight work và lưu checkpoint.
- [ ] Đợi final data sync/watermark.
- [ ] Chạy count/checksum/business invariant checks.
- [ ] Chuyển traffic theo cohort/tỷ lệ đã phê duyệt.
- [ ] Chạy smoke test và business test.
- [ ] Theo dõi SLO, duplicate, DLQ, lag và cost.
- [ ] Tăng traffic chỉ khi gate trước đạt.
- [ ] Ghi decision/timestamp/evidence.

### Rollback nếu trigger xảy ra

- [ ] Dừng tăng traffic và xác định blast radius.
- [ ] Ghi target/source watermark, event offset và write history.
- [ ] Xác định authoritative data store.
- [ ] Chọn reverse sync, compensation, forward-fix hoặc stop-the-write.
- [ ] Chuyển route/consumer theo kế hoạch tương thích dữ liệu.
- [ ] Chạy reconciliation và xác minh business correctness.
- [ ] Thông báo stakeholder và cập nhật incident record.

### Sau cutover

- [ ] Hypercare hoàn tất và owner tiếp nhận.
- [ ] Legacy traffic/dependency đã được xác minh.
- [ ] Rollback window đóng có sign-off.
- [ ] Retention/backup/legal hold được xử lý.
- [ ] Decommission approval và resource inventory đầy đủ.
- [ ] IAM/network/DNS/compute/data cleanup hoàn tất.
- [ ] Billing và service catalog được cập nhật.

## 17. Các anti-pattern trong migration

### 17.1. Chuyển traffic trước khi hiểu data ownership

Traffic có thể chuyển nhanh, nhưng nếu hai hệ thống cùng ghi một aggregate, rollback sẽ rất khó. Chốt writer ownership và reconciliation trước.

### 17.2. Dual-write không có outbox/CDC

Hai lệnh ghi độc lập không tạo transaction phân tán. Một bên có thể thành công và bên kia thất bại. Dùng replication/outbox hoặc repair process có version và operation ID.

### 17.3. Shadow traffic có quyền production write

Shadow có thể gửi email, charge payment hoặc tạo event thật. Dùng identity/resource riêng, deny write hoặc sandbox side effects.

### 17.4. Canary ngẫu nhiên theo từng request

Một transaction có thể bắt đầu ở legacy nhưng retry sang serverless. Dùng cohort/operation routing ổn định và giữ transaction ownership.

### 17.5. Rollback chỉ đổi DNS/alias

Data và event có thể đã thay đổi. Kiểm tra reverse sync, schema compatibility và side effect trước khi route về legacy.

### 17.6. Tắt legacy ngay sau cutover

Client cũ, scheduler, delayed event và backup có thể còn phụ thuộc. Giữ rollback window, read-only period và kiểm tra access thực tế.

### 17.7. Xóa backup cùng lúc với compute

Backup/retention/audit có lifecycle riêng. Xác minh retention và legal hold trước khi xóa dữ liệu.

### 17.8. Không có owner cho rollback

Nếu mọi người đều có thể đề xuất nhưng không ai có quyền quyết định, incident bridge sẽ chậm. Xác định decision maker, threshold và authority trước cutover.

## 18. Checklist production migration

- [ ] Workload inventory, dependency graph và owner hoàn chỉnh.
- [ ] Baseline traffic, latency, error, data và cost được ghi.
- [ ] Wave scope và migration strategy có business owner.
- [ ] Java business logic tách khỏi cloud-specific adapter ở mức phù hợp.
- [ ] API/event contract và schema version tương thích.
- [ ] Configuration/secret/IAM/network cho target đã kiểm tra.
- [ ] Data snapshot/CDC/checkpoint và final sync đã rehearsal.
- [ ] Một writer có thẩm quyền cho mỗi aggregate/tenant ở từng giai đoạn.
- [ ] Dual-write có outbox/CDC/reconciliation, không dựa vào hai thao tác độc lập.
- [ ] Idempotency key và event ID được giữ qua legacy/target/retry.
- [ ] Queue/stream offset, scheduler ownership và delayed event được xử lý.
- [ ] Shadow mode không có production side effect.
- [ ] Canary/cohort routing ổn định qua retry.
- [ ] Cutover gates đo cả technical SLO và business correctness.
- [ ] Rollback trigger, decision maker và timebox được phê duyệt.
- [ ] Rollback plan bao gồm data, event, schema và side effect.
- [ ] Forward-fix/compensation/replay path được định nghĩa.
- [ ] Hypercare owner và dashboard đã sẵn sàng.
- [ ] Decommission gate xác nhận traffic/dependency bằng evidence.
- [ ] Backup, retention, legal hold và audit được giữ đúng policy.
- [ ] IAM, secret, DNS, certificate, network và resource cũ được thu hồi có kiểm soát.
- [ ] IaC plan chỉ tác động đúng resource legacy đã duyệt; deletion protection/retain policy được review.
- [ ] Cost before/after và cost per successful transaction được đối chiếu.
- [ ] Service catalog, runbook, RACI và support boundary được cập nhật.

## Kết luận

Cutover là thay đổi routing và ownership của workload; rollback là phục hồi một trạng thái vận hành và dữ liệu an toàn; decommission là thu hồi resource sau khi xác minh không còn phụ thuộc. Ba hoạt động này phải được thiết kế cùng nhau từ đầu migration.

Với Java serverless, hãy chuyển theo wave, tách business logic khỏi adapter, giữ API/event compatibility, chọn một writer có thẩm quyền và dùng snapshot/CDC/outbox để kiểm soát dữ liệu. Shadow/canary giúp giảm blast radius nhưng phải bảo vệ side effect và giữ route ổn định qua retry. Success gate cần đo cả SLO, business invariant, queue freshness và cost per successful transaction.

Rollback không chỉ là trỏ traffic về endpoint cũ. Cần biết dữ liệu nào đã ghi, event nào đã phát, schema nào đã đổi và side effect nào không thể đảo ngược. Khi rollback không an toàn, forward-fix, compensation hoặc stop-the-write có thể là lựa chọn phù hợp hơn. Chỉ thu hồi legacy sau hypercare, reconciliation, rollback window, retention review và decommission sign-off. Mọi bước phải có owner, checkpoint, evidence và runbook để migration có thể kiểm soát được trong production.
