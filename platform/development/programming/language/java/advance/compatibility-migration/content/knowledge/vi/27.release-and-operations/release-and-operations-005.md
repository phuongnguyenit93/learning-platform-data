# Xác định điều kiện dừng triển khai và kích hoạt quay lui

Trong **Java Advance Compatibility Migration**, việc đưa một bản Java/JDK/framework mới vào production không được kết thúc ở trạng thái “build xanh, deploy thành công”. Một ứng dụng có thể khởi động tốt nhưng chỉ lỗi khi xử lý một event hiếm, gọi thư viện có `AbstractMethodError`, bắt tay TLS tới đối tác, chạy batch cuối ngày hoặc ghi dữ liệu bằng Hibernate version mới. Nếu không xác định trước **khi nào dừng rollout** và **cần kích hoạt quay lui theo cách nào**, sự cố nhỏ ở canary có thể lan thành incident toàn hệ thống.

Bài học trong chương **Phát hành và vận hành** trình bày cách thiết lập **go/no-go**, **hard stop**, **soft stop**, **rollback trigger**, đo lường SLO và bất biến nghiệp vụ, tổ chức canary/rolling/blue-green deployments và xây dựng runbook. Trọng tâm không chỉ là quay lại artifact cũ, mà còn là **bảo vệ dữ liệu, giới hạn ảnh hưởng và xác minh khả năng phục hồi**.

**Nguyên tắc:** mọi ngưỡng, điều kiện và quyền quyết định phải được thỏa thuận **trước** khi mở rộng traffic. Các con số trong ví dụ là minh họa phương pháp, không phải ngưỡng production có thể sao chép nguyên xi.

## 1. No-go, pause, containment, rollback và roll-forward

| Quyết định | Mục tiêu | Ví dụ |
|---|---|---|
| **No-go** | Không cho phép bắt đầu phát hành | Thiếu rollback image, JDK không đúng, test bắt buộc chưa pass |
| **Pause rollout** | Ngừng mở rộng ảnh hưởng để điều tra | Giữ canary ở 5%, không lên 25% |
| **Containment** | Dừng hoặc hạn chế hành vi đang gây hại | Tắt tính năng, cô lập write path, dừng consumer |
| **Rollback** | Trở về một trạng thái vận hành an toàn đã biết | Chuyển traffic về stable, chạy image/config cũ |
| **Roll-forward** | Sửa sự cố bằng một bản tiếp theo khi rollback không an toàn | Hotfix, compatibility adapter, data repair |

**Pause không đồng nghĩa rollback:** các pods/canary đã deploy có thể vẫn chạy và nhận traffic. **Rollback binary không đồng nghĩa rollback data:** những records, events, payments đã được xử lý không tự biến mất khi đổi image.

### 1.1. Ví dụ

Một ứng dụng nâng từ Java 11/Spring Boot 2 sang Java 17/Spring Boot 3:

1. Trước deploy, xác minh runtime, dependency versions và rollback plan: **go/no-go**.
2. Khi canary 5% có 5xx tăng: **pause**.
3. Nếu phát hiện payment bị tính trùng: **containment** ngay.
4. Khi dữ liệu còn tương thích stable: **rollback traffic/image**.
5. Khi stable không hiểu dữ liệu mới: không quay lui mù quáng, **contain và đánh giá roll-forward/repair**.

## 2. Tại sao phải đặt điều kiện dừng trước release?

Khi có sự cố, nhóm dễ tranh luận “chờ thêm để đủ mẫu”, “đây chỉ là warm-up” hoặc “tăng canary để quan sát thêm”. Nếu không có ranh giới, việc tăng traffic có thể làm mở rộng **blast radius**.

Điều kiện dừng chốt trước giúp:

- Giới hạn người dùng, giao dịch và dữ liệu bị ảnh hưởng.
- Tránh quyết định cảm tính vì muốn bảo vệ bản phát hành.
- Phân biệt regression do candidate với sự cố đang ảnh hưởng stable.
- Quy định ai được phép pause, rollback hoặc cô lập một flow.
- Ngăn CI/CD tự tiếp tục khi metrics thiếu.
- Tạo bằng chứng kiểm toán và post-incident review.
- Gắn recovery plan với RTO/RPO.
- Bảo đảm stable artifact và capacity đã được chuẩn bị.
- Giúp tất cả nhóm hiểu rõ những tín hiệu **không thể chấp nhận**.

Một chính sách “rollback khi ứng dụng không ổn” chưa đủ. Cần mô tả **metric, scope, observation window, threshold, sample, action, owner và evidence**.

## 3. Thuật ngữ quan trọng

| Khái niệm | Ý nghĩa |
|---|---|
| Stable/control | Phiên bản hiện đang phục vụ hoặc nhóm đối chứng |
| Candidate/canary | Phiên bản mới nhận một phần workload |
| Rollout step | Một lần tăng traffic, replicas, tenant hoặc region |
| Blast radius | Quy mô tác động tiềm năng |
| SLI | Chỉ số chất lượng đo được, ví dụ request success |
| SLO | Mục tiêu chất lượng dịch vụ trong cửa sổ đo |
| Error budget | Phần lỗi được phép theo SLO |
| Hard stop | Điều kiện buộc hành động giảm rủi ro ngay |
| Soft stop | Điều kiện pause và xác minh |
| Rollback trigger | Quy tắc chính thức kích hoạt quay lui |
| RTO | Thời gian mục tiêu khôi phục dịch vụ |
| RPO | Mức mất dữ liệu mục tiêu có thể chấp nhận |
| Inconclusive | Chưa đủ bằng chứng cho phép tiếp tục |
| Observability gap | Metrics/logs/traces thiếu hoặc không đáng tin |

RTO và RPO là hai mục tiêu khác nhau. Quay traffic về bản cũ trong 5 phút không chứng minh RPO được đáp ứng nếu bản lỗi đã ghi sai dữ liệu.

## 4. Go/no-go gate trước khi triển khai

Một preflight gate nên được kiểm tra **trước khi tác động production**:

| Gate | Cần xác minh | Không đạt |
|---|---|---|
| Artifact provenance | Commit, build ID, digest của image/JAR/WAR đúng bản duyệt | No-go |
| Java runtime | Compiler, test và container JVM phù hợp baseline | No-go |
| Dependencies | Framework, agents, library/bytecode tooling tương thích | No-go |
| Required tests | Unit/integration/contract/security checks đạt | No-go |
| Database | Schema và data tương thích rollback window | No-go |
| Messaging | Event formats và consumer/producer cùng chạy được | No-go |
| Observability | Metrics có labels version, logs/traces, alerts hoạt động | No-go |
| Stable capacity | Old version có thể nhận lại traffic | No-go |
| Rollback | Artifact/config/permissions/runbook sẵn | No-go |
| Ownership | Release owner, on-call và escalation contact rõ | No-go |
| Security | Không có blocker về auth, TLS, secrets, data access | No-go |
| Change window | Incident/maintenance và error-budget policy cho phép | No-go theo policy |

Không chỉ đánh dấu checkbox bằng cảm giác: mỗi mục cần gắn link hoặc log chứng minh. Nếu deployment đã có một migration destructive làm bản stable không hoạt động, phải giải quyết điều đó **trước** khi bắt đầu canary.

## 5. Hard stop: điều kiện không thể chờ thống kê

**Hard stop** bảo vệ những bất biến nghiệp vụ và an toàn cốt lõi:

- Ghi sai số tiền, balance hoặc duplicate charge.
- Có bằng chứng unauthorized access hoặc cross-tenant data exposure.
- Mất, ghi sai hoặc phá hỏng dữ liệu.
- Lộ secrets, token hay thông tin cá nhân.
- Đẩy message gây sai state ở downstream.
- Một artifact không đúng bản đã approved được deploy.
- Phiên bản mới làm shared infrastructure mất khả năng phục vụ.
- Critical transaction flow bị lỗi nghiêm trọng có bằng chứng.
- Một thay đổi khiến rollback path không còn an toàn khi release vẫn tiếp tục tăng rủi ro.

Khi có bằng chứng đủ xác nhận, phải **ngừng mở rộng ảnh hưởng và thực hiện containment theo runbook**; đồng thời đánh giá rollback và kích hoạt incident response. Không chờ đủ 500 requests hoặc 2 lần lấy mẫu nếu có một payment duplicate đã xác minh.

### 5.1. Không coi mọi alert là lỗi đã xác minh

Một detector có thể có false positive. Runbook phải mô tả bằng chứng xác minh và on-call triage nhanh; tuy vậy quy trình xác minh không được khiến sự cố data/security nghiêm trọng kéo dài vô hạn.

## 6. Soft stop: tạm dừng để điều tra

Một số tín hiệu đòi hỏi pause trước khi tăng traffic:

- 5xx ratio tăng nhưng chưa đủ data.
- p95/p99 latency vượt baseline.
- CPU/GC/heap tăng bền vững.
- Readiness hoặc startup không ổn định.
- Queue lag, retry rate hoặc DLQ tăng.
- Cả stable và candidate đang bị một dependency chung ảnh hưởng.
- Dashboard thiếu dữ liệu hoặc release labels bị lỗi.
- APM agent không report hoặc trace propagation đứt.

**Pause** có nghĩa giữ blast radius trong phạm vi đã chấp nhận. Sau đó nhóm xác định cause, tác động và quyết định **resume, rollback hoặc tiếp tục containment** theo timebox.

Một soft stop không có thời hạn điều tra dễ biến thành canary “treo” nhiều giờ mà không ai chịu trách nhiệm.

## 7. Thiết kế điều kiện đo được

Một điều kiện tốt cần:

~~~text
Signal:       HTTP 5xx error ratio
Scope:        orders-api candidate, checkout route
Window:       rolling 5 minutes
Min sample:   500 valid requests
Threshold:    > 1% AND > 3 times comparable stable ratio
Decision:     PAUSE increasing traffic
Owner:        release on-call
Investigation: logs, traces, dependency, business impact
Rollback:     if candidate-caused or regression persists
Evidence:     release-labeled dashboard + incident record
~~~

Các ngưỡng **500, 1%, 3 lần, 5 phút** chỉ là ví dụ.

### 7.1. Minimum sample là một phần của điều kiện

Một request lỗi trong mười requests là 10%, nhưng có ít bằng chứng thống kê. Với dịch vụ traffic thấp, cần longer windows hoặc synthetic tests. Nhưng sample size **không được vô hiệu hóa hard stop**.

### 7.2. Window phải phù hợp workload

Một batch job mỗi 60 phút không thể được xác nhận chỉ bằng 5 phút HTTP monitoring. Có thể đặt gate theo sự kiện: “job đầu tiên trên candidate chạy thành công”, “xử lý đủ các event type quan trọng” hoặc “reconciliation đúng”.

## 8. Tính error ratio minh họa

Giả sử trong 5 phút:

| Nhóm | Requests | 5xx | Tỷ lệ 5xx |
|---|---:|---:|---:|
| Stable | 20.000 | 40 | 0,2% |
| Candidate | 1.000 | 20 | 2,0% |

Công thức:

\[
\text{Error Ratio}=\frac{\text{Số request lỗi}}{\text{Tổng request hợp lệ}}
\]

Candidate có 2,0% lỗi, cao **10 lần stable**. Với policy đã chốt, đây là tín hiệu pause mạnh.

Tuy vậy, cần xác minh:

- Traffic mix về route/tenant/region có tương đồng không?
- Các error có cùng root cause không?
- Monitoring probes có làm sai denominator không?
- Lỗi ở application, ingress hay dependency?
- Có đủ sample và metric freshness không?
- 5xx có thực sự chỉ xuất hiện sau rollout không?

Nếu stable có 0 lỗi trong một cửa sổ nhỏ, phép tính “candidate cao gấp N lần” không đáng tin. Cần kết hợp ngưỡng tuyệt đối, khối lượng mẫu và đánh giá thực tế.

## 9. SLO, error budget và burn rate

Ví dụ SLO availability **99,9%** trên 30 ngày cho phép khoảng **0,1%** events không thành công theo cùng SLI.

Nếu candidate có 2% lỗi, tốc độ tiêu thụ error budget so mức cho phép xấp xỉ:

\[
\text{Burn Rate}=\frac{2\%}{0,1\%}=20
\]

Đây là cách diễn giải đơn giản; các hệ thống thật thường dùng **multi-window burn-rate alerts** để cân bằng tốc độ phát hiện và nhiễu.

Một release gate có thể áp chính sách:

- Không phát hành thay đổi rủi ro cao khi error budget đã cạn.
- Ưu tiên sửa reliability hơn đưa thêm tính năng.
- Cho phép emergency fix theo quy trình phê duyệt riêng.
- Dừng rollout khi candidate tiêu thụ budget với tốc độ vượt giới hạn.

SLO trung bình không thay thế **critical business invariants**. Một API checkout lỗi cho nhóm nhỏ có thể nghiêm trọng dù toàn service còn đạt mục tiêu tổng.

## 10. Latency, GC và Java performance

Nâng JDK có thể đổi JIT, GC, class loading, TLS và thread scheduling. Một điều kiện minh họa:

~~~text
PAUSE nếu:
  p95 checkout latency > 500 ms
  AND p95 > 1.5x stable p95
  trong hai cửa sổ 5 phút liên tiếp
  với số request và traffic mix đủ đại diện.
~~~

Không áp nguyên xi 500 ms cho mọi service.

### 10.1. Warm-up không xóa hard stop

Canary mới có thể trải qua JIT warm-up, cache cold-start hoặc kết nối pool chưa đầy. Có thể cho warm-up window, nhưng không được dùng lý do này để bỏ qua lỗi mất dữ liệu, authorization bypass hoặc 5xx nghiêm trọng.

### 10.2. Percentile aggregation

Không tính p95 toàn service bằng cách lấy trung bình p95 của các pods. Dùng histogram/aggregation đúng theo công cụ đo.

### 10.3. Saturation metrics

Theo dõi CPU, throttling, heap, GC pauses, thread pools, HTTP/DB pools, native memory, file descriptors, OOM, queue age và timeout. Một canary nhỏ vẫn có thể gây lỗi toàn bộ dịch vụ nếu làm cạn connection pool dùng chung.

## 11. Các dấu hiệu đặc thù Java/JDK migration

| Loại lỗi | Ví dụ |
|---|---|
| Bytecode target | `UnsupportedClassVersionError` |
| ABI linkage | `NoSuchMethodError`, `AbstractMethodError`, `IncompatibleClassChangeError` |
| JPMS/reflection | `InaccessibleObjectException`, `IllegalAccessError` |
| Missing runtime API | `ClassNotFoundException`, `NoClassDefFoundError` |
| Javax/Jakarta mismatch | Servlet/Validation/JPA API không tương thích |
| Crypto/TLS | `SSLHandshakeException` |
| Serialization | JSON/XML/event deserialization lỗi |
| Bytecode agents | ASM/Byte Buddy không hỗ trợ class major |
| ORM/JDBC | Hibernate converter, SQL, transaction lỗi |
| JNI/native | `UnsatisfiedLinkError` |
| Runtime performance | GC pause, latency, heap/native memory regression |

Một lỗi có thể chỉ lộ khi request thực thi đúng method hoặc event path. Vì vậy, **startup green không có nghĩa runtime đã tương thích**.

Nếu canary mới lỗi ở một critical route, không cần đợi whole-service 5xx ratio vượt ngưỡng mới pause.

## 12. Business invariants: sức mạnh của tín hiệu đúng

Các bất biến nghiệp vụ nên tách khỏi HTTP metrics:

- Không charge hai lần cùng idempotency key.
- Không trừ stock hai lần.
- Không tạo invoice sai tổng tiền.
- Không để user đọc dữ liệu tenant khác.
- Không làm mất giao dịch đã xác nhận.
- Không ghi trạng thái mà consumer cũ không thể đọc ngoài rollout contract.
- Không làm sai số dư hoặc sổ cái.
- Không gửi dữ liệu người dùng tới sai destination.

Một lỗi Hibernate converter có thể vẫn trả HTTP 200 nhưng ghi order status sai. **Business reconciliation** mới phát hiện; do đó monitoring phải đo correctness, không chỉ availability.

### 12.1. Synthetic transactions

Có thể tạo các transaction thử nghiệm cô lập: login, tạo đơn giả, kiểm tra validation, outbound TLS, message serialization, query dữ liệu qua ORM. Không dùng thanh toán thật hoặc dữ liệu khách hàng nếu chưa có phương án isolation/cleanup được phê duyệt.

## 13. Observability là một release gate

Để quyết định rollout cần có:

1. Version/build/digest labels trong telemetry.
2. Release markers và timestamps.
3. Logs có trace/correlation IDs.
4. Error/latency/saturation theo candidate và stable.
5. Critical route và business metrics.
6. Queue/batch/job metrics nếu ứng dụng sử dụng.
7. Traces qua dependencies.
8. Alert channels đang hoạt động.
9. Metric ingestion latency được biết.
10. Owner của dashboard/queries.

### 13.1. Missing metrics không có nghĩa pass

Nếu metric bị mất, label đổi sau nâng Micrometer hoặc APM agent lỗi trên JDK mới, hệ thống ở trạng thái **inconclusive**. Thường nên pause cho tới khi khả năng quan sát phục hồi, không tự kết luận app khỏe.

### 13.2. Không dùng metric tổng để che lỗi canary

Nếu candidate chỉ nhận 5% requests, lỗi của nó có thể chìm trong service-level average. Phải so theo release label và traffic mix.

## 14. Canary và stable phải được so tương đồng

~~~text
                  Incoming traffic
                         |
                 +-------+-------+
                 |               |
                 v               v
            Stable N       Candidate N+1
             control          canary
                 |               |
                 +-------+-------+
                         |
                  Compare SLIs
                         |
             Continue / Pause / Rollback
~~~

Khi so, kiểm tra:

- Cùng time window.
- Request route/method và tenant profile.
- Region/device/client mix.
- Request sizes và workloads.
- Cache/JIT warm-up differences.
- External dependencies.
- Background jobs chưa được cover.
- Minimum sample và instrumentation quality.

**Canary 1% không đồng nghĩa rủi ro 1%:** một pod có thể chiếm shared DB connection pool hoặc tạo migration side effect ảnh hưởng mọi traffic.

## 15. Progressive rollout có các gate theo bước

Ví dụ sơ đồ:

~~~text
Preflight
   |
   v
1% traffic --> observe --> decision
   |
   v
5% traffic --> observe --> decision
   |
   v
25% traffic --> observe --> decision
   |
   v
100% traffic --> extended observation
~~~

Tỷ lệ chỉ minh họa. Với hệ thống traffic thấp có thể dùng cohort internal, region-first hoặc synthetic coverage.

Trước khi tăng bước:

- Metrics có đủ dữ liệu chưa?
- Critical workflow được gọi chưa?
- Error/latency/GC có ổn không?
- Data/security invariants có được bảo vệ?
- Rollback path còn an toàn không?
- Stable capacity còn đủ?
- Owner đã chấp thuận theo policy?

**Rollout đến 100% vẫn cần giám sát tiếp.** Batch cuối ngày hoặc luồng hiếm có thể chỉ chạy sau khi deploy complete.

## 16. Blue-green deployment và traffic switch

~~~text
                   Traffic router
                         |
                 +-------+-------+
                 |               |
                 v               v
           Blue stable      Green candidate
~~~

Mô hình blue-green có thể giúp chuyển traffic nhanh nhưng chỉ an toàn khi:

- Green ready và warmed up.
- Blue vẫn còn capacity.
- Database/event schemas tương thích.
- Session/cookie/redirect behavior đúng.
- Không có scheduler/consumer chạy trùng gây side effects.
- Traffic router có đường quay về blue.
- Monitoring xác nhận đúng pool và version.

Chuyển traffic từ green về blue **không xóa records đã được green ghi**. Nếu blue không hiểu records mới, rollback traffic có thể làm lỗi trầm trọng hơn.

## 17. Rolling deployment và nhiều phiên bản đồng thời

Trong rolling update, cùng lúc có thể có:

~~~text
Load balancer
  |            |
  v            v
Old pods     New pods
Version N    Version N+1
~~~

Cần kiểm tra:

- Old/new app đọc/ghi được cùng DB schema.
- Session serialization compatibility.
- API clients có thể trúng cả hai versions.
- Producers/consumers có hiểu messages của nhau.
- Cache values và key formats có tương thích.
- Feature flags có đồng bộ.
- Scheduler có được lock/leader election.
- Config/runtime không xung đột.

Một feature chỉ cần chạy 10 phút nhưng ghi state khiến old version không đọc được là đủ phá rollback window.

## 18. Feature flag và kill switch

Một feature flag có thể tách risky code path:

~~~text
Request
   |
   v
Feature flag
   |
   +--> Old implementation
   |
   +--> New implementation
~~~

Nếu được thiết kế đúng, tắt flag có thể giảm tác hại nhanh hơn rollback image. Nhưng cần chắc rằng:

- Old branch còn hoạt động.
- Flag propagate kịp thời.
- Data ghi bởi new branch tương thích old branch.
- Batch/consumer processes cũng kiểm tra flag nếu cần.
- Metrics phân biệt các trạng thái.
- Flag fallback được test.

**Tắt flag chỉ là containment nếu nguyên nhân còn trong artifact.** Sau đó vẫn phải khắc phục và quyết định có rollback toàn bộ không.

## 19. Các lớp rollback cần tách

| Lớp | Hành động | Không tự khôi phục |
|---|---|---|
| Traffic | Router chuyển về stable | DB và external side effects |
| Binary | Chạy known-good image/JAR/WAR | Config/data schemas |
| Config | Quay env vars/flags/feature settings | Writes đã commit |
| Queue | Dừng candidate consumer | Events đã ack/publish |
| DB | Restore/PITR/repair có kiểm soát | Giao dịch hợp lệ sau snapshot nếu không hòa giải |
| Roll-forward | Hotfix/compatibility adapter | Dữ liệu cũ đã bị sai |

Rollback toàn hệ thống thường cần phối hợp nhiều lớp. **Không tuyên bố phục hồi chỉ vì orchestrator báo revision trước đã Available.**

## 20. Chuẩn bị rollback Java runtime và framework

Một bản stable có thể bao gồm:

- JDK vendor/version và base OS image cũ.
- Spring Boot/Framework/Hibernate libraries khác.
- JVM flags khác.
- Java agent/APM khác.
- TLS provider/truststore khác.
- Serialization và data access mappings khác.
- Container config và secrets references riêng.

Nên lưu **stable image digest**, không chỉ tag có thể đổi. Cùng với artifact phải có cấu hình, dependency set và hướng xác nhận JDK runtime.

### 20.1. Không hạ từng JAR ngẫu nhiên

Không nên “rollback” bằng cách chỉ đổi một Spring Framework JAR hoặc Hibernate JAR trong candidate. Phải quay về một tổ hợp dependencies đã được kiểm chứng và có thể vận hành.

### 20.2. Stable cần đủ capacity

Nếu blue/stable đã scale xuống quá ít replicas, rollback traffic có thể gây overload. Chuẩn bị capacity hoặc time-to-scale-up theo RTO.

## 21. Database và quy trình expand-and-contract

Đây thường là rủi ro lớn nhất cho rollback.

Ví dụ:

~~~text
Version N hiểu trạng thái: NEW, PAID
Version N+1 thêm: PARTIALLY_REFUNDED
Rollback về N:
  old parser không hiểu giá trị mới
~~~

Ngay cả khi database schema không đổi, **data values** có thể làm old code không tương thích.

Một quy trình giảm rủi ro:

1. **Expand:** thêm field/table/index tương thích, không xóa cấu trúc cũ.
2. **Compatibility:** old/new versions có thể đồng thời đọc/ghi.
3. **Switch:** mở dần behavior mới theo rollout.
4. **Contract:** chỉ xóa phần cũ sau khi rollback window thực sự đóng.

Không mặc định dual-write luôn nên dùng; nó tạo rủi ro consistency riêng.

### 21.1. DDL rollback không phải data rollback

Một down migration có thể drop field chứa dữ liệu vừa ghi. Trước mọi thao tác destructive phải xem:

- Backup/PITR khả dụng.
- RPO và writes hợp lệ sau snapshot.
- Số records bị tác động.
- Consumers hoặc reports phụ thuộc schema.
- Người có quyền phê duyệt.
- Kế hoạch reconciliation.

### 21.2. Restore phải được diễn tập

Có backup chưa đủ. Cần biết restore mất bao lâu, dữ liệu nào mất, cách kiểm tra tính toàn vẹn và chủ sở hữu quyết định.

## 22. Messaging, idempotency và rollback consumers

Trong hệ event-driven:

~~~text
New producer --> Broker --> Old consumer
    new schema              incompatible parser
~~~

Rollback producer không xóa events đã publish. Rollback consumer không tự đảo payment, email hay side effects.

Stop conditions cần theo dõi:

- Consumer lag và oldest message age.
- Deserialize failures.
- DLQ growth.
- Retry storms.
- Duplicate processing.
- Offset commit state.
- Schema compatibility.
- Cross-version producer/consumer tests.

**Không tự reset offsets/replay mọi messages** nếu idempotency chưa được xác minh. Khi dữ liệu đã sai, phải có reconciliation plan.

## 23. Security hard stop

Những tín hiệu cần escalation ngay:

- Bypass authorization.
- Cross-tenant data access.
- TLS validation bị tắt.
- Tokens/secrets xuất hiện trong logs.
- Management endpoint bị mở công khai.
- Wrong audience/issuer acceptance trong JWT.
- Dữ liệu nhạy cảm truyền sai destination.

Dừng tăng exposure, contain và chuyển security incident process. Không chờ p95 hay 5xx. Không dùng workaround trust-all TLS để deployment có vẻ hoạt động.

## 24. Tự động pause, tự động rollback hay phê duyệt thủ công?

| Phương án | Ưu điểm | Rủi ro |
|---|---|---|
| Auto-pause | Giới hạn blast radius nhanh | Canary hiện tại vẫn có thể chạy |
| Auto-rollback | Phản ứng nhanh khi traffic-based rollback an toàn | False positives, metric outage, data mismatch |
| Human-approved | Có ngữ cảnh nghiệp vụ/dữ liệu | Chậm nếu ownership mơ hồ |
| Hybrid | Pause tự động, rollback theo policy/approval | Cần escalation và audit rõ |

Auto-rollback nên chỉ áp dụng khi:

1. Telemetry đáng tin và label theo version.
2. Có sample/window và fail/inconclusive semantics rõ.
3. Stable artifact/capacity sẵn.
4. DB/schema/event formats backward-compatible.
5. Action đã được diễn tập, idempotent.
6. Có audit logs và owner.
7. Không kích hoạt destructive data recovery không được duyệt.

Với data corruption, team thường cần containment tức thì và DB/incident owner tham gia quyết định phục hồi.

## 25. Cây quyết định rollout

~~~text
Preflight passed?
    |
    +-- NO --> NO-GO
    |
    +-- YES --> Candidate receives traffic
                      |
                      v
              Hard stop verified?
                |           |
               YES          NO
                |            |
         CONTAIN+INCIDENT    v
                       Telemetry valid?
                         |         |
                        NO        YES
                         |         |
                       PAUSE       v
                            SLIs & invariants OK?
                              |         |
                             YES        NO
                              |          |
                           Advance      PAUSE
                             step         |
                                          v
                                 Rollback safe?
                                  |       |
                                 YES      NO
                                  |       |
                               ROLLBACK  CONTAIN +
                                         ESCALATE/
                                         ROLL-FORWARD
~~~

Đây là sơ đồ suy luận, không phải workflow máy chạy trực tiếp. Một hard stop có thể được xác minh ở bất kỳ giai đoạn nào và cần ưu tiên xử lý ngay.

## 26. Bảng guardrails minh họa

| Signal | Ngưỡng ví dụ | Quyết định |
|---|---|---|
| Duplicate payment đã xác minh | Một trường hợp | Hard stop + reconciliation |
| Authorization bypass | Một trường hợp xác minh | Hard stop + security incident |
| 5xx ratio | >1%/5 phút, ≥500 requests, >3× stable | Pause, rollback nếu release-caused |
| p95 checkout | >500 ms và >1,5× stable qua hai windows | Pause |
| Canary crashloop | Repeated NotReady và retries | Pause/rollback |
| LinkageError critical path | Được xác minh ở candidate | Pause/rollback |
| Consumer DLQ growth | Cao hơn baseline liên tục | Pause/contain |
| Data inconsistency | Vi phạm invariant đã xác minh | Hard stop |
| Monitoring unavailable | Không có SLI bắt buộc | Pause |
| Stable capacity missing | Không nhận lại được traffic | No-go |
| Unsafe rollback | Old version không tương thích state | No-go hoặc containment |

Các số liệu **chỉ mang tính ví dụ**. Với dịch vụ traffic thấp hoặc yêu cầu cao về correctness, cần chính sách riêng.

## 27. Policy-as-code minh họa

~~~yaml
# Pseudocode, KHÔNG phải cấu hình Kubernetes/Argo/Flagger thực tế.
releaseGuardrails:
  service: orders-api
  stable: known-good
  candidate: java17-boot3
  preflight:
    approvedArtifact: true
    stableCapacityRequired: true
    rollbackImageRequired: true
    observabilityRequired: true
    databaseCompatibilityRequired: true
  rollout:
    stepsPercent: [1, 5, 25, 100]
    insufficientData: PAUSE
  metrics:
    - name: canary5xx
      windowMinutes: 5
      minRequests: 500
      pauseIfRatioAbove: 0.01
      pauseIfTimesStableAbove: 3
    - name: checkoutP95
      windowMinutes: 5
      minRequests: 300
      pauseIfLatencyMsAbove: 500
      pauseIfTimesStableAbove: 1.5
  hardStop:
    - verifiedDataCorruption
    - verifiedAuthorizationBypass
    - verifiedDuplicateTransaction
  decisions:
    pauseOwner: release-oncall
    rollbackRequires: safeAndVerifiedPlan
    dataRestoreRequires: databaseOwnerApproval
~~~

Keys chỉ biểu diễn một **mô hình chính sách**; muốn chạy phải chuyển sang schema/tool version thực tế và kiểm thử behavior của controller.

Policy changes cần review. Không âm thầm nới ngưỡng để dashboard “xanh” trong lúc có release pressure.

## 28. Kubernetes Deployment: pause và undo

Ví dụ lệnh dành cho một runbook đã có authorization:

~~~bash
kubectl rollout status deployment/orders-api -n production
kubectl describe deployment orders-api -n production
~~~

Tạm dừng cập nhật:

~~~bash
kubectl rollout pause deployment/orders-api -n production
~~~

Xem revision và quay lui khi thích hợp:

~~~bash
kubectl rollout history deployment/orders-api -n production
kubectl rollout undo deployment/orders-api -n production
kubectl rollout status deployment/orders-api -n production
~~~

Resume khi đã được đánh giá lại:

~~~bash
kubectl rollout resume deployment/orders-api -n production
~~~

**Giới hạn:**

- `rollout pause` ngừng progression của Deployment, không tự chuyển traffic về stable.
- `rollout undo` phụ thuộc revision history còn khả dụng, image cũ pull được và cấu hình thích hợp.
- Nếu Deployment đang paused, cần thực hiện trình tự pause/resume/undo phù hợp với hệ thống đã kiểm thử.
- Lệnh undo không hoàn tác database, queue messages, side effects hoặc external config.
- `rollout status` báo trạng thái Deployment, không chứng minh customer-facing SLO/correctness.

Canary weighted traffic có thể cần ingress, service mesh hoặc progressive delivery controller; không mặc định Deployment cung cấp chính sách routing đó.

## 29. Health probes không thay business guardrails

- **Startup probe** kiểm tra trạng thái khởi động.
- **Readiness probe** cho biết pod sẵn sàng nhận traffic theo routing semantics tương ứng.
- **Liveness probe** giúp phát hiện container cần restart.

Những probes không chứng minh:

- Không có duplicate payments.
- Hibernate mapping đúng.
- JWT authorization không bị bypass.
- Message serialization còn tương thích.
- p99 đáp ứng SLO.
- External API integrations hoạt động.

Liveness cấu hình quá gắt có thể khiến JDK mới restart liên tục trong GC pause/JIT warm-up. Dùng probe phù hợp lifecycle, đồng thời chạy user-facing metrics và invariants.

## 30. Query metrics minh họa

Một PromQL-like query cho candidate 5xx ratio, giả định có các metrics/labels tương ứng:

~~~promql
sum(rate(http_server_requests_seconds_count{
  service="orders-api",
  version="candidate",
  status=~"5.."
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  service="orders-api",
  version="candidate"
}[5m]))
~~~

Đây chỉ là **ví dụ**. Spring/Micrometer/OTel metric names và labels có thể khác. Cần:

- Kiểm tra denominator.
- Loại noise từ health probes nếu phù hợp.
- Phân biệt candidate/control.
- Xử lý zero requests.
- Kiểm tra sample và metric freshness.
- Có business checks độc lập.

Không nên tin một query đơn lẻ nếu những thay đổi serialization/data correctness không xuất hiện dưới dạng 5xx.

## 31. Runbook rollback có thể thực thi

Một runbook thực tế nên chứa:

~~~text
Release:
  service, candidate digest, stable digest,
  cluster, namespace, owners, change window.

Trigger:
  exact metric/invariant, scope, window,
  threshold and incident severity.

Pre-checks:
  stable available and enough capacity;
  database/event backward compatibility;
  config/secrets and JVM runtime compatible.

Contain:
  pause increasing traffic;
  disable risky feature/consumer if authorized;
  open incident if required.

Rollback:
  change routing or deploy stable artifact;
  restore compatible configuration;
  confirm no unintended candidate traffic.

Validate:
  deployed digest, 5xx, latency, GC,
  critical business transaction, security,
  DB reads/writes, queues and observability.

Close:
  incident timeline, RTO/RPO, impact,
  ownership, prevention and re-release gate.
~~~

Những dòng này phải được chuyển thành **commands, dashboard URLs và contact points** của ứng dụng thật. Không đợi incident mới đi tìm stable image hay người có quyền rollback.

## 32. Vai trò và quyền quyết định

| Vai trò | Trách nhiệm |
|---|---|
| Release owner | Điều phối các rollout steps và quyết định theo policy |
| On-call/SRE | Theo dõi alerts, pause, routing/rollback theo quyền |
| Application owner | Chẩn đoán JVM/framework/API và nghiệp vụ |
| Database owner | Đánh giá state/schema, backup, repair/reconciliation |
| Security owner | Xử lý auth/TLS/privacy incidents |
| Incident commander | Điều phối khi sự cố nặng hoặc nhiều hệ thống |
| Communications owner | Thông báo trạng thái và ảnh hưởng |
| Approver | Phê duyệt thao tác nguy hiểm theo policy |

Một người có thể đảm nhiệm nhiều vai trò, nhưng không được bỏ trống ownership.

Quy định rõ hành động nào on-call được thực hiện ngay để **chặn thiệt hại**, và hành động nào như destructive DB restore cần phê duyệt. Không tạo quy trình khiến người vận hành phải chờ vô thời hạn trước một dữ liệu đang bị phá.

## 33. Timebox và quyết định resume

Một plan minh họa:

~~~text
T0: candidate receives canary traffic
T+5m: check telemetry freshness and sample
T+10m: pause if soft-stop guardrail breached
T+15m: assign cause and severity
T+20m: decide safe rollback or controlled continuation
~~~

Các mốc không phải mặc định production. Hard stop cần xử lý ngay; batch job hàng giờ phải có observation theo sự kiện.

Resume chỉ được thực hiện khi:

1. Cảnh báo đã được giải thích, không chỉ biến mất.
2. Metrics còn mới và có đủ data.
3. Candidate đã pass critical tests.
4. Data/security invariants vẫn đúng.
5. Stable/rollback options còn sẵn.
6. Owner chấp thuận theo release policy.

Nếu chưa đủ bằng chứng sau timebox, **không mở rộng blast radius**.

## 34. Khi rollback không an toàn

Một vài trường hợp:

- DB đã xóa field mà stable còn dùng.
- New data values old binary không parse.
- Broker còn new-schema events mà old consumer không hiểu.
- Side effect đã thực hiện (charge/email).
- Stable image có lỗ hổng bảo mật nghiêm trọng.
- Backup không thể restore trong RPO.
- External API contract đã thay một chiều.

Khi đó:

1. Dừng rollout.
2. Contain flow gây hại.
3. Giữ logs/transactions và xác định phạm vi.
4. Đánh giá DB/data/security ownership.
5. So rollback với roll-forward/compatibility adapter.
6. Thực hiện repair/reconciliation có kiểm soát.
7. Xác minh correctness trước khi mở traffic.
8. Ghi quyết định và bằng chứng.

**Rollback không an toàn không có nghĩa tiếp tục phát hành.** Có thể phải chuyển chức năng sang read-only hoặc tạm dừng consumer.

## 35. Tình huống: linkage error chỉ xuất hiện trong canary

Một candidate nâng Java 17 và framework. Khi gọi checkout:

~~~text
java.lang.AbstractMethodError:
Receiver class com.vendor.LegacyCheckoutAdapter ...
~~~

Quy trình:

1. Candidate metrics ghi 5xx ở checkout; stable cùng window không lỗi.
2. Pause canary ngay.
3. Kiểm tra critical business impact.
4. Nếu state tương thích và guardrail yêu cầu, rollback traffic.
5. Kiểm tra các payments đã thực hiện để tránh retry/duplicate.
6. Xác minh checkout ổn lại trên stable.
7. Điều tra SPI version, adapter binary, classpath, class loader.
8. Nâng adapter/test failing path trước khi rollout lại.

Không cần chờ whole-service error ratio tăng cao nếu critical path đã có lỗi đã xác minh.

## 36. Tình huống: ORM ghi dữ liệu sai với HTTP 200

Candidate nâng Hibernate cùng JDK. Một custom enum converter đổi mapping. Controller trả HTTP 200 nhưng reconcile phát hiện giá trị order sai.

Hành động:

- Hard stop theo correctness invariant.
- Tạm ngừng writes gây ảnh hưởng.
- Xác định những records bị sai.
- Đánh giá old binary có đọc được state mới không.
- Chỉ rollback code/traffic khi an toàn.
- Sửa/reconcile dữ liệu dưới trách nhiệm DB/business owner.
- Test correctness trước khi mở lại.
- Ghi user impact và incident report.

Đây là lý do monitoring phải bao gồm business invariants, không chỉ availability.

## 37. Tình huống: TLS handshake lỗi sau nâng JDK

Candidate không gọi được đối tác thanh toán:

~~~text
javax.net.ssl.SSLHandshakeException
~~~

Có thể do truststore, certificate chain, TLS protocol/provider hoặc mTLS config.

Quy trình:

1. Pause.
2. Xem outbound error metrics/traces.
3. Không tắt TLS validation hoặc dùng trust-all.
4. Rollback runtime/traffic nếu ảnh hưởng và state tương thích.
5. Sửa certificate/truststore theo chính sách.
6. Test outbound TLS trong staging tương đồng.
7. Canary lại có guardrails.

## 38. Tình huống: cả stable và candidate tăng 502/504

Giả sử ngay sau canary cả hai pools đều tăng lỗi. Không tự kết luận candidate gây ra hoặc hoàn toàn không liên quan.

Kiểm tra:

- Database/shared connection pool saturation.
- Ingress/proxy/network outage.
- Candidate có query/connections bất thường không.
- Traffic spike và load balancer behavior.
- Error distribution theo version và route.
- Dependency logs và deployment events.

Giữ rollout paused cho tới khi incident chung được xử lý, root cause đủ rõ và guardrails có thể đánh giá lại.

## 39. Diễn tập rollback trước khi cần rollback

Một rehearsal có thể:

1. Deploy candidate vào staging/environment phù hợp.
2. Chạy synthetic workflows.
3. Pause và chuyển traffic về stable.
4. Xác minh old runtime/image/config.
5. Kiểm tra DB schema/data compatibility.
6. Kiểm tra queue, cache, session và scheduled jobs.
7. Đo thời gian thao tác và phục hồi.
8. Kiểm tra RBAC và escalation.
9. Xác nhận metrics/traces/alerts phản ánh việc chuyển version.
10. Lưu runbook update và những bước còn thủ công.

Không dùng dữ liệu khách hàng hoặc giao dịch thật một cách tùy tiện cho rehearsal. Diễn tập phải đánh giá **state compatibility**, không chỉ việc một lệnh trả 0.

## 40. RTO/RPO và incident timeline

Ví dụ minh họa:

~~~text
14:00 candidate incident detected
14:02 rollout paused
14:06 traffic returned to stable
14:09 HTTP SLIs restored
14:25 data reconciliation completed
~~~

Dịch vụ có thể phục hồi HTTP trước khi toàn bộ dữ liệu được xác nhận đúng. Không tuyên bố incident kết thúc ở 14:09 nếu business correctness chưa được khôi phục.

Nên đo:

- Time to detect.
- Time to decide.
- Time to contain.
- Time to restore traffic.
- Time to reconcile state.
- Total customer impact.
- RTO/RPO thực tế so mục tiêu.

## 41. Mẫu báo cáo quyết định

~~~yaml
# Template minh họa; không phải một incident đã xảy ra.
releaseDecision:
  service: orders-api
  candidate: jdk17-boot3-build
  stable: known-good
  rolloutStepPercent: 5

  trigger:
    type: error-regression
    windowMinutes: 5
    minimumRequests: 500
    observedCandidateRatio: "record-value"
    observedStableRatio: "record-value"

  decision:
    action: PAUSE
    timestamp: "record-time"
    owner: release-oncall
    approvedBy: incident-policy

  safety:
    stableArtifactAvailable: false
    stableCapacityValidated: false
    databaseBackwardCompatible: false
    eventSchemaCompatible: false
    rollbackRehearsed: false

  evidence:
    dashboard: "record-link"
    logs: "record-link"
    traces: "record-link"
    incident: "record-link"

  outcome:
    stableTrafficRestored: false
    criticalFlowsVerified: false
    dataIntegrityVerified: false
    followUpOwner: application-team
~~~

Các giá trị `false` và `record-value` là placeholders, không phải bằng chứng PASS. Quyết định thực tế cần đi kèm version/digest, người phê duyệt, metrics/traces và thời điểm cụ thể.

## 42. Checklist go/no-go

- [ ] Xác định candidate commit, digest và JDK/runtime version.
- [ ] Compiler/test/production JVM đáp ứng baseline.
- [ ] Framework, dependencies, agents và bytecode tooling được kiểm tra.
- [ ] Required unit/integration/contract/security tests pass.
- [ ] Stable artifact và capacity sẵn.
- [ ] Database/schema backward compatibility đã xét.
- [ ] Producer/consumer event schema compatibility đã xét.
- [ ] Auth/TLS/privacy hard stops đã định nghĩa.
- [ ] Critical business transactions có giám sát.
- [ ] Canary/control telemetry có labels đáng tin.
- [ ] Ngưỡng/window/min sample và inconclusive policy rõ.
- [ ] Runbook, owner, permissions và escalation sẵn.
- [ ] Rollback rehearsal hoặc bằng chứng tương đương đã có.
- [ ] Change window và error budget policy cho phép.

## 43. Checklist trong rollout

- [ ] Đã ghi marker cho mỗi traffic increase.
- [ ] Xác nhận candidate nhận traffic đúng như dự kiến.
- [ ] Xem startup/readiness và JVM/linkage errors.
- [ ] Xem error ratio, p95/p99, GC, saturation.
- [ ] So cùng cửa sổ với stable/control.
- [ ] Kiểm tra critical route và business invariants.
- [ ] Kiểm tra queue lag, DLQ và scheduled jobs.
- [ ] Kiểm tra telemetry freshness.
- [ ] Không tiếp tục khi data inconclusive.
- [ ] Pause hoặc contain khi guardrail kích hoạt.
- [ ] Ghi rõ người ra quyết định và bằng chứng.
- [ ] Resume chỉ khi đạt lại các điều kiện đã chốt.

## 44. Checklist sau rollback

- [ ] Candidate không còn nhận unintended traffic.
- [ ] Stable artifact và JVM/runtime đã xác minh.
- [ ] Cấu hình và secrets references tương thích.
- [ ] Error ratio, latency, saturation chấp nhận được.
- [ ] Critical business transactions hoạt động.
- [ ] Data integrity và reconciliation hoàn tất hoặc có plan rõ.
- [ ] Queue offsets, retry, DLQ và external side effects được kiểm soát.
- [ ] Login, session, cache và security hoạt động.
- [ ] Traces, metrics, alerts đã phục hồi.
- [ ] RTO/RPO và customer impact được ghi.
- [ ] Incident có owner và action items.
- [ ] Candidate lỗi bị chặn tự động redeploy.
- [ ] Re-release chỉ sau root-cause fix/regression tests.

**Rollback hoàn tất khi dịch vụ và dữ liệu ở trạng thái được xác minh**, không chỉ khi tool báo Deployment Available.

## 45. Những sai lầm thường gặp

### 45.1. Ngưỡng mơ hồ

“CPU cao thì rollback” không có baseline, scope, window và user impact. Cần điều kiện đo được.

### 45.2. Chỉ nhìn 5xx

HTTP 200 vẫn có thể che data corruption, duplicate payments hoặc authorization bypass.

### 45.3. Chờ sample cho hard stop

Không bắt một sai lệch dữ liệu nghiêm trọng đã được xác minh phải chờ 500 requests.

### 45.4. Metrics mất thì coi pass

Thiếu telemetry thường là trạng thái inconclusive, phải pause hoặc xử lý theo policy.

### 45.5. Pause bị nhầm với rollback

Canary pods đã deploy vẫn có thể chạy; cần traffic và lifecycle controls thực tế.

### 45.6. Rollback chỉ là image

Schema, dữ liệu, queues và external side effects không tự hoàn tác.

### 45.7. Rollback tự động cho mọi alert

False positives hoặc data incompatibility có thể làm tình hình xấu đi. Chỉ auto khi rollback an toàn và đã thử.

### 45.8. Không có owner

Alert đúng nhưng không ai có quyền thao tác là release process chưa sẵn sàng.

### 45.9. Không diễn tập

Runbook chưa thử có thể thiếu RBAC, image, stable capacity hoặc đúng JVM flags.

### 45.10. Resume vì alert biến mất

Alert có thể hết vì canary traffic giảm hoặc metric pipeline đứt. Phải xác minh nguyên nhân.

### 45.11. Ép roll-forward chỉ để tránh rollback

Quyết định nên dựa vào state compatibility, risk và recovery, không dựa vào cảm xúc.

### 45.12. Không đo hậu rollback

Một lệnh undo thành công không bảo đảm checkout, events và data correctness đã phục hồi.

## 46. Nguyên tắc kết luận

- **No-go, pause, containment, rollback và roll-forward** là năm loại quyết định khác nhau.
- **Guardrails phải được chốt trước deploy** và gồm metric, scope, window, sample, threshold, action, owner.
- **Hard stops ưu tiên data/security/business invariants**, không phụ thuộc thống kê đầy đủ khi đã xác minh vi phạm.
- **Soft stops** dùng metrics so canary/control, observation windows và minimum volume để hạn chế nhiễu.
- **Thiếu telemetry không phải thành công**, và metrics tổng có thể che regression của candidate.
- **SLO/error budget giúp đánh giá reliability**, nhưng không thay các checks về correctness.
- **Java migration có failure modes đặc thù** như linkage, reflection, TLS, Jakarta, bytecode agents, GC và ORM behavior.
- **Canary/blue-green/rolling deployment** đều cần kiểm tra traffic, state và shared resources thực tế.
- **Rollback artifact không tự phục hồi database, messages hoặc side effects**.
- **Expand-and-contract và backward compatibility** giúp stable version còn hoạt động trong rollback window.
- **Automated rollback chỉ phù hợp khi hành động an toàn, telemetry đáng tin và được diễn tập**.
- **Runbook phải có owner, artifact digest, RBAC, commands, dashboards và tests sau phục hồi**.
- **Nếu rollback không an toàn, phải contain và escalate**, không mặc định tiếp tục rollout.
- **Đánh giá phục hồi qua SLI, business invariants và data integrity**, không chỉ status của orchestrator.

Trong **Java Advance Compatibility Migration**, điều kiện dừng và kích hoạt quay lui không phải một phần phụ của deployment checklist. Chúng là hàng rào an toàn giúp đội phát hành biết **khi nào không nên bắt đầu, khi nào phải giới hạn rủi ro, khi nào có thể quay về stable và khi nào phải xử lý state theo một kế hoạch riêng**. Khi các quyết định đó dựa trên tín hiệu, bằng chứng và ownership rõ ràng, việc nâng Java/JDK/framework có thể tiến hành theo từng bước có kiểm soát và khả năng phục hồi đáng tin.
