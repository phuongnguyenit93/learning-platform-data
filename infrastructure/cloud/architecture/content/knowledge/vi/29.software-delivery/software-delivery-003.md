# Rolling update, blue–green và canary

Phát hành phiên bản mới là một thay đổi vận hành có thể ảnh hưởng trực tiếp tới availability, latency, tính đúng đắn của dữ liệu và trải nghiệm người dùng. Nếu dừng toàn bộ hệ thống để thay phiên bản, thời gian gián đoạn có thể không chấp nhận được. Nếu đưa phiên bản mới tới tất cả người dùng cùng lúc, một lỗi nhỏ có thể trở thành sự cố diện rộng trước khi đội ngũ kịp phát hiện.

Rolling update, blue–green và canary là ba chiến lược triển khai giúp thay đổi phiên bản theo những cách khác nhau. Rolling update thay dần các instance trong cùng một nhóm; blue–green duy trì hai môi trường riêng và chuyển traffic giữa chúng; canary đưa phiên bản mới tới một tỷ lệ nhỏ traffic hoặc một nhóm người dùng trước khi mở rộng.

Trong module **CLOUD_ARCHITECTURE**, bài học này đặt các chiến lược trên trong bối cảnh kiến trúc triển khai cloud: capacity, load balancing, health check, session, database migration, observability, rollback và automation. Mục tiêu là chọn cách phát hành phù hợp với SLO, trạng thái dữ liệu, khả năng tương thích, chi phí và mức rủi ro mà tổ chức có thể chấp nhận.

## 1. Vì sao cần deployment strategy?

Một deployment không chỉ thay binary hoặc container image. Nó có thể đồng thời thay:

- Application code và API behavior.
- Runtime, base image, library hoặc framework.
- Database schema, index và migration.
- Configuration, feature flag và secret.
- Message schema, event consumer và background worker.
- Network route, load balancer target và service discovery.
- Cache format, session state và static assets.

Một phiên bản có thể khởi động thành công nhưng vẫn không tương thích với dữ liệu cũ, message đang nằm trong queue hoặc các instance khác chưa được cập nhật. Vì vậy deployment strategy cần xem toàn bộ hệ thống và giai đoạn chuyển tiếp, không chỉ thời điểm process start.

### Mục tiêu triển khai an toàn

1. Giảm hoặc loại bỏ downtime có thể nhìn thấy.
2. Giới hạn blast radius khi phiên bản mới có lỗi.
3. Phát hiện lỗi qua health và business metrics trước khi rollout toàn bộ.
4. Có đường rollback hoặc forward-fix đã được chuẩn bị.
5. Giữ tương thích giữa phiên bản cũ/mới trong thời gian chuyển tiếp.
6. Không làm mất hoặc nhân đôi dữ liệu khi request/job đang chạy.
7. Có bằng chứng để biết phiên bản nào phục vụ traffic tại từng thời điểm.

## 2. Tổng quan ba chiến lược

| Chiến lược | Cách triển khai | Điểm mạnh | Đánh đổi chính |
| --- | --- | --- | --- |
| **Rolling update** | Thay instance từng phần trong cùng pool | Sử dụng lại capacity hiện có, không cần hai môi trường đầy đủ | Cũ và mới chạy đồng thời; cần compatibility và surge capacity |
| **Blue–green** | Duy trì hai môi trường, chuyển traffic từ blue sang green | Cutover nhanh, rollback traffic tương đối rõ | Chi phí/capacity kép; database và state phải tương thích |
| **Canary** | Gửi tỷ lệ nhỏ traffic tới phiên bản mới rồi tăng dần | Giới hạn blast radius, kiểm chứng bằng traffic thật | Cần routing/metrics đủ chi tiết và phân tích cohort |

Không có chiến lược nào tự động bảo đảm zero downtime hoặc rollback tức thì. Chất lượng kết quả phụ thuộc readiness, graceful shutdown, load balancer, session/state, data migration và các dependency.

~~~mermaid
flowchart TB
    subgraph R["Rolling update"]
      R1["Old instances"] --> R2["Replace a batch"]
      R2 --> R3["Mixed old + new"]
      R3 --> R4["All new"]
    end
    subgraph BG["Blue-green"]
      B1["Blue serves traffic"]
      B2["Green deployed and verified"]
      B1 --> B3["Switch traffic"]
      B2 --> B3
      B3 --> B4["Green serves traffic"]
    end
    subgraph C["Canary"]
      C1["Old version 100%"]
      C2["New version small slice"]
      C3["Increase exposure"]
      C4["New version full traffic"]
      C1 --> C2 --> C3 --> C4
    end
~~~

## 3. Deployment lifecycle và các trạng thái instance

Một instance mới cần trải qua nhiều bước trước khi nhận traffic:

1. Artifact được lấy từ registry và xác minh provenance/signature nếu có.
2. Runtime/container được khởi động với config và secret đúng.
3. Startup hoàn tất và dependency cần thiết sẵn sàng.
4. Readiness check pass.
5. Load balancer/service discovery đưa instance vào pool.
6. Instance xử lý traffic và được quan sát.
7. Khi thay thế, instance cũ ngừng nhận request mới.
8. Request đang chạy được drain trong giới hạn.
9. Instance cũ dừng sạch và giải phóng tài nguyên.

### Liveness, readiness và startup probe

- **Startup probe:** xác định ứng dụng đã hoàn tất giai đoạn khởi động chậm hay chưa.
- **Readiness probe:** xác định instance có thể nhận traffic hay không.
- **Liveness probe:** xác định process cần được restart vì không còn hoạt động bình thường.

Readiness và liveness không nên dùng cùng một phép kiểm tra một cách máy móc. Database tạm thời chậm có thể khiến readiness fail để ngừng nhận traffic, nhưng nếu liveness cũng fail đồng loạt thì hệ thống có thể restart toàn bộ instance và làm sự cố nặng hơn.

### Graceful shutdown

Khi instance bị loại khỏi pool:

- Ngừng nhận request mới.
- Chờ hoặc kết thúc request đang xử lý theo deadline.
- Dừng consumer/poller để không nhận thêm job.
- Commit/ack message chỉ khi xử lý thành công theo semantics.
- Đóng connection, flush metric/log và cleanup.
- Thoát trước shutdown grace period của platform.

Không đặt drain timeout ngắn hơn các request hợp lệ dài nhất nếu không có cơ chế chuyển tiếp. Ngược lại, drain vô hạn sẽ làm deployment treo.

## 4. Rolling update hoạt động thế nào?

Rolling update thay một phần instance cũ bằng instance mới qua nhiều batch. Trong thời gian triển khai, cả hai phiên bản có thể cùng phục vụ traffic.

~~~mermaid
flowchart LR
    LB["Load balancer"]
    OLD1["Old A"]
    OLD2["Old B"]
    NEW1["New A"]
    NEW2["New B"]
    LB --> OLD1
    LB --> OLD2
    LB --> NEW1
    LB --> NEW2
~~~

Sơ đồ thể hiện giai đoạn mixed-version; tỷ lệ instance thực tế thay đổi theo từng batch.

### Các tham số cần thiết kế

| Tham số | Ý nghĩa |
| --- | --- |
| Batch size / max surge | Số instance mới tạo thêm trong một đợt |
| Max unavailable | Số instance có thể unavailable trong rollout |
| Min ready/healthy | Số hoặc tỷ lệ instance phải khỏe trước khi tiếp tục |
| Readiness delay | Thời gian chờ startup và warm-up |
| Progress deadline | Thời gian tối đa một rollout được phép tiến triển |
| Drain/grace period | Thời gian để instance cũ xử lý request đang chạy |
| Pause/resume | Khả năng dừng rollout khi health gate không đạt |

Tên tham số khác nhau theo orchestrator. Phải hiểu semantics cụ thể: một số nền tảng đếm desired replicas, một số tính max surge theo phần trăm hoặc số lượng.

### Ví dụ rolling update

Một service có 10 replicas, triển khai theo batch 2 instance:

1. Giữ đủ capacity hiện tại.
2. Tạo 2 instance mới.
3. Chờ readiness pass và quan sát health.
4. Drain 2 instance cũ.
5. Lặp lại tới khi toàn bộ 10 instance dùng phiên bản mới.

Nếu mỗi batch phải chờ 30 giây warm-up và 20 giây bake time, rollout có thể kéo dài vài phút. Điều đó thường an toàn hơn thay đồng loạt mà chưa biết lỗi.

### Max surge và capacity

Nếu 10 replicas cũ vẫn chạy trong lúc tạo 2 replicas mới, cluster cần đủ capacity tạm thời cho 12 replicas, cùng CPU/memory/network và quota tương ứng. Nếu không có headroom, scheduler có thể không đặt được pod mới hoặc autoscaler không kịp cấp node.

Nếu chọn max unavailable, cần đảm bảo các instance còn lại đủ phục vụ peak traffic và failure scenario. Deployment không nên đồng thời làm mất nhiều instance hơn capacity plan cho phép.

## 5. Ưu và nhược điểm của rolling update

### Ưu điểm

- Không cần duy trì hai stack đầy đủ trong toàn bộ thời gian.
- Tận dụng load balancer và orchestrator hiện tại.
- Rollout có thể tự động hóa theo batch.
- Phù hợp service stateless và backward-compatible.
- Chi phí tăng thêm thường chỉ là surge trong thời gian ngắn.

### Hạn chế

- Old và new cùng chạy nên API, schema, cache và event phải tương thích.
- Rollback binary không đảo ngược được database migration đã phá compatibility.
- Nếu lỗi phát hiện muộn, nhiều batch có thể đã thay thế.
- Request có thể đi qua hai phiên bản và tạo hành vi khác nhau.
- Capacity không đủ có thể làm rollout chậm hoặc làm production thiếu headroom.

### Khi phù hợp

- Service stateless hoặc state được externalize.
- Thay đổi nhỏ, backward-compatible.
- Có health/readiness và metric tin cậy.
- Deployment frequency cao và cần tối ưu resource.
- Có thể chấp nhận mixed-version trong giai đoạn rollout.

Không nên mặc định rolling update phù hợp với mọi database migration, protocol thay đổi không tương thích hoặc hệ thống stateful có quorum nhạy cảm.

## 6. Blue–green deployment hoạt động thế nào?

Blue–green duy trì hai môi trường có khả năng chạy cùng ứng dụng:

- **Blue:** phiên bản hiện đang phục vụ production.
- **Green:** môi trường mới được triển khai, kiểm tra và chuẩn bị nhận traffic.

Khi green đã sẵn sàng, load balancer, router hoặc DNS/service discovery chuyển traffic từ blue sang green. Blue được giữ lại trong một khoảng thời gian để có thể chuyển traffic trở lại nếu cần.

~~~mermaid
flowchart TB
    USER["Users"]
    ROUTER["Traffic router"]
    subgraph BLUE["Blue environment"]
      B["Version N"]
    end
    subgraph GREEN["Green environment"]
      G["Version N+1"]
    end
    USER --> ROUTER
    ROUTER -->|Before cutover| B
    ROUTER -.->|After cutover| G
~~~

### Các bước triển khai

1. Xác nhận blue đang khỏe và có baseline metric.
2. Tạo green với artifact/config mới.
3. Khởi tạo dependency, secret, network, schema-compatible access và capacity.
4. Chạy startup/readiness, smoke test và synthetic transaction.
5. Nếu phù hợp, gửi traffic kiểm thử có kiểm soát tới green.
6. Chuyển traffic production theo cách đã định nghĩa.
7. Theo dõi health, business metric, error rate và data correctness.
8. Giữ blue trong thời gian bake/rollback window.
9. Chỉ hủy blue sau khi hết điều kiện rollback và có phê duyệt.

### Cutover

Cutover có thể dùng load balancer target switch, service selector, ingress route, service mesh hoặc DNS. Mỗi cách có thời gian hội tụ và failure mode khác nhau. DNS switch có thể bị ảnh hưởng bởi TTL và resolver cache; load balancer switch có thể nhanh hơn nhưng connection đang tồn tại vẫn cần drain.

### Rollback

Nếu green có lỗi, chuyển traffic trở lại blue. Việc này nhanh khi:

- Blue vẫn còn chạy và nhận traffic được.
- Database/API contract tương thích cả hai phiên bản.
- Green không ghi dữ liệu theo schema/semantics mà blue không hiểu.
- Session/cache/event không ở trạng thái chỉ green mới hiểu.
- Router có thể chuyển lại và connection được xử lý an toàn.

Blue–green không tạo rollback an toàn nếu green đã thực hiện destructive migration hoặc ghi dữ liệu làm phiên bản cũ không thể xử lý.

## 7. Ưu và nhược điểm của blue–green

### Ưu điểm

- Có thể kiểm thử môi trường mới trước khi chuyển người dùng.
- Cutover traffic rõ ràng và có đường chuyển về môi trường cũ.
- Hạn chế thời gian chạy mixed-version trên cùng pool.
- Có thể giảm rủi ro deploy cho service lớn nếu hai environment độc lập.
- Hỗ trợ smoke test và synthetic test trên green trước production cutover.

### Hạn chế

- Có thể cần gần gấp đôi compute/network trong giai đoạn tồn tại hai môi trường.
- Data layer thường dùng chung, nên không hoàn toàn độc lập.
- Cần quản lý secret, certificate, DNS, session, cache và queue giữa hai environment.
- Cutover không làm mất các connection đang mở hoặc side effect đã phát sinh.
- Hai environment có thể drift về config hoặc dependency.

### Khi phù hợp

- Service cần cutover nhanh và có thể chạy hai environment.
- Release có rủi ro cần kiểm tra trước khi nhận traffic thật.
- Hạ tầng có thể provision song song.
- Có contract tương thích dữ liệu và quy trình rollback.
- Workload phù hợp để chuyển traffic ở lớp router.

Blue–green đặc biệt hữu ích với web/API stateless; cần kế hoạch bổ sung cho worker, scheduler và database migration.

## 8. Canary deployment hoạt động thế nào?

Canary đưa phiên bản mới tới một tập người dùng/traffic nhỏ, quan sát kết quả rồi tăng exposure theo từng bước. Canary có thể được định tuyến theo tỷ lệ request, tenant, region, user cohort hoặc header/feature flag.

~~~mermaid
flowchart LR
    CLIENT["Production traffic"]
    ROUTER["Traffic splitter"]
    OLD["Stable version"]
    NEW["Canary version"]
    METRIC["Compare SLI/business metrics"]
    CLIENT --> ROUTER
    ROUTER -->|95%| OLD
    ROUTER -->|5%| NEW
    OLD --> METRIC
    NEW --> METRIC
~~~

Tỷ lệ 95/5 chỉ là ví dụ. Với tenant hoặc cohort chọn lọc, tỷ lệ số request có thể không tương đương tỷ lệ số khách hàng, giá trị giao dịch hoặc mức rủi ro.

### Các bước canary

1. Thiết lập baseline của phiên bản stable.
2. Triển khai canary với capacity nhỏ.
3. Chọn cohort/traffic slice có thể đại diện và kiểm soát.
4. Chuyển tỷ lệ nhỏ traffic.
5. Quan sát health, SLI, business outcome và telemetry theo version.
6. Giữ đủ bake time để quan sát workload có chu kỳ.
7. Tăng tỷ lệ nếu guardrail đạt; pause/rollback nếu vi phạm.
8. Lặp lại cho tới khi canary nhận toàn bộ traffic.
9. Kết thúc rollout và dọn stable theo rollback policy.

### Ví dụ progressive delivery

| Giai đoạn | Traffic tới canary | Điều kiện tiếp tục |
| --- | ---: | --- |
| Initial | 1% | Readiness/synthetic pass, không có lỗi nghiêm trọng |
| Small cohort | 5% | Error/latency không xấu hơn baseline quá ngưỡng |
| Expansion | 20% | Business conversion và data correctness ổn định |
| Broad | 50% | Không vi phạm SLO, capacity đủ |
| Full | 100% | Bake time hoàn tất, owner xác nhận |

Ngưỡng số phải được thiết lập theo SLO, traffic volume và rủi ro. Ở 1% traffic, số lượng request có thể quá nhỏ để thống kê tin cậy; cần minimum sample size và thời gian quan sát.

## 9. Ưu và nhược điểm của canary

### Ưu điểm

- Giới hạn blast radius khi có lỗi.
- Đo tác động trên traffic thật và dependency thật.
- Có thể kết hợp business metrics với technical SLI.
- Hỗ trợ dừng/pause trước khi toàn bộ khách hàng bị ảnh hưởng.
- Có thể phát hiện khác biệt theo region, tenant tier hoặc client version.

### Hạn chế

- Cần traffic routing và telemetry theo phiên bản/cohort.
- Phân tích có thể bị sai lệch nếu cohort không đại diện.
- Lỗi hiếm hoặc chỉ xảy ra khi tải cao có thể không xuất hiện ở canary nhỏ.
- Cũ và mới chạy cùng lúc, vẫn cần backward compatibility.
- Có thể làm tăng complexity của feature flag, routing và data attribution.

### Khi phù hợp

- Workload có traffic đủ lớn để quan sát.
- Rủi ro thay đổi cần được kiểm chứng dần.
- Có thể định tuyến theo tỷ lệ hoặc cohort.
- Có SLI/business metric so sánh stable và canary.
- Có khả năng pause hoặc rollback tự động an toàn.

## 10. Canary theo traffic, tenant và cohort

Không phải mọi canary đều chia phần trăm request ngẫu nhiên.

| Phương pháp | Đặc điểm | Rủi ro cần xem |
| --- | --- | --- |
| Random traffic percentage | Chọn ngẫu nhiên một tỷ lệ request | Một user có thể đi qua cả hai version |
| Sticky user/session | Gắn user/session vào một version | Session affinity và phân bố tải |
| Tenant cohort | Chọn một số tenant | Tenant được chọn có thể không đại diện |
| Region/AZ cohort | Mở một region hoặc failure domain | Khác biệt network/data locality |
| Header/client cohort | Theo header, app version hoặc integration | Header phải được xác thực; client distribution lệch |
| Feature flag | Bật chức năng mới cho nhóm chọn lọc | Code path cũ/mới cùng tồn tại lâu |

### Chọn cohort

Một cohort tốt phải:

- Có dữ liệu đại diện cho workload quan trọng.
- Được chọn theo tiêu chí rõ, có thể tái lập.
- Không vô tình chỉ chứa nội bộ/traffic thử nghiệm nhẹ.
- Có giới hạn tác động tối đa.
- Có thể xác định trong log/metric mà không lộ PII.

### Tenant canary

Canary theo tenant hữu ích trong SaaS khi có tenant pilot hiểu rõ rủi ro hoặc tenant nội bộ. Tuy nhiên tenant pilot có thể có ít dữ liệu, ít integration hoặc usage pattern khác. Cần bổ sung test synthetic và tải đại diện; không suy luận toàn bộ fleet chỉ từ một tenant.

### Một request hay một user?

Nếu một user gửi nhiều request, random theo request có thể khiến cùng phiên làm việc chạy cả hai version, tạo khác biệt UI/API và khó debug. Sticky assignment theo user/tenant giúp nhất quán, nhưng có thể làm traffic không cân bằng. Chọn theo semantics của workload.

## 11. Backward compatibility trong giai đoạn mixed-version

Rolling update và canary tạo thời gian phiên bản cũ/mới cùng tồn tại. Blue–green cũng thường có hai version cùng truy cập database hoặc shared services. Trong khoảng chuyển tiếp, mỗi thành phần phải hiểu dữ liệu và protocol mà version kia tạo ra.

### Các lớp compatibility

- **API compatibility:** field, status code, validation, pagination và error semantics.
- **Database compatibility:** schema mới vẫn được version cũ đọc/ghi trong rollout.
- **Event compatibility:** producer/consumer chấp nhận message version cũ/mới.
- **Cache compatibility:** serialize format và key namespace không làm instance cũ lỗi.
- **Session compatibility:** session/token do version mới tạo vẫn đọc được bởi version cũ.
- **Configuration compatibility:** config mới không làm binary cũ fail khi rollback.
- **Static asset compatibility:** HTML, JS và API có thể lệch phiên bản trong cache/CDN.

### Quy tắc thay đổi an toàn

Thường nên ưu tiên các thay đổi additive:

- Thêm field optional thay vì đổi nghĩa field hiện tại.
- Consumer bỏ qua field chưa biết nếu contract cho phép.
- Producer chỉ phát field mới sau khi consumer đã sẵn sàng.
- Giữ endpoint/format cũ trong giai đoạn migration.
- Xóa field cũ ở release sau khi không còn consumer dùng.
- Có schema version và compatibility test.

Không đổi semantics của enum/status/units mà vẫn giữ cùng field name nếu consumer cũ không thể phân biệt.

## 12. Database migration: expand–migrate–contract

Database thường là điểm khiến rollback ứng dụng trở nên khó. Một migration destructive được chạy cùng lúc với deployment có thể làm phiên bản cũ không thể hoạt động.

Chiến lược expand–migrate–contract tách thay đổi schema thành nhiều giai đoạn:

~~~mermaid
flowchart LR
    E["Expand\nAdd compatible schema"]
    M["Migrate\nDual-read/write or backfill"]
    V["Verify\nCompare data and consumers"]
    C["Contract\nRemove obsolete schema later"]
    E --> M --> V --> C
~~~

### Ví dụ đổi cột customer_name thành display_name

**Release A — Expand**

- Thêm cột display_name nullable.
- Giữ customer_name.
- Code mới có thể đọc display_name nếu có, fallback customer_name.
- Write path có thể ghi cả hai trong giai đoạn chuyển tiếp.

**Backfill**

- Copy dữ liệu từ customer_name sang display_name theo batch.
- Theo dõi tiến độ, lỗi và dữ liệu phát sinh đồng thời.
- Reconcile count/checksum hoặc business rule.

**Release B — Migrate**

- Consumer mới đọc display_name.
- Producer ghi display_name; có thể tiếp tục dual-write để giữ compatibility trong cửa sổ rollback.
- Kiểm tra không còn reader nào chỉ hiểu schema cũ.

**Release C — Contract**

- Sau khi hết rollback window và xác nhận không còn consumer cũ, bỏ customer_name.
- Thực hiện destructive cleanup như một thay đổi riêng có review.

### Backfill cần kiểm soát

- Batch size, rate limit và thời gian chạy.
- Lock duration và tác động tới production query.
- Retry/idempotency/checkpoint.
- Xử lý record mới/được sửa đồng thời.
- Reconciliation sau backfill.
- Khả năng pause/resume và rollback.

Không chạy một migration update toàn bảng lớn trong giờ cao điểm mà không đo lock, I/O, replication lag và ảnh hưởng workload.

### Rollback migration

Không phải migration nào cũng có thể đảo ngược. Với destructive change, thường cần forward-compatible code, backup/recovery plan và bước contract trì hoãn. “Rollback deployment” chỉ đổi binary; nó không tự phục hồi schema/data đã bị thay đổi.

## 13. Event schema, queue và consumer compatibility

Trong hệ thống event-driven, producer và consumer có thể được deploy vào thời điểm khác nhau. Consumer cũ có thể còn message trong queue; event mới có thể được replay từ retention.

Các nguyên tắc:

- Schema evolution có version và compatibility rule.
- Thêm field optional với default semantics rõ.
- Consumer chịu được field chưa biết khi phù hợp.
- Không đổi ý nghĩa field hiện có một cách âm thầm.
- Consumer có thể đọc event cũ trong toàn bộ retention/replay window.
- Dead-letter và replay path cũng phải hỗ trợ schema mới/cũ.

### Producer-first hay consumer-first?

Thứ tự phụ thuộc kiểu thay đổi:

- Khi thêm field mới, thường deploy consumer có thể hiểu field trước, sau đó producer bắt đầu phát.
- Khi bỏ field cũ, ngừng phát sau khi consumer không còn cần, rồi mới xóa logic đọc.
- Với event type mới, consumer có thể được deploy trước và ignore/no-op tới khi producer bật.

### Event schema registry

Schema registry có thể kiểm tra compatibility khi producer đăng ký schema. Nhưng registry chỉ bảo vệ contract đã khai báo; consumer vẫn cần kiểm thử business semantics, optional/null/default và replay. Một schema hợp lệ về cú pháp vẫn có thể làm thay đổi kết quả nghiệp vụ.

## 14. Cache, session và static asset khi rollout

### Cache format

Nếu phiên bản mới serialize object theo format không tương thích, instance cũ có thể không đọc được cache entry mới. Các lựa chọn:

- Version namespace/key, ví dụ cache:v2:...
- Chấp nhận cache miss và rebuild khi dữ liệu tái tạo được.
- Dual-read/dual-write trong thời gian ngắn.
- Dùng format có schema evolution.
- Giữ TTL cho key cũ tới khi hết thời gian rollback.

Không flush toàn cache khi rollout nếu cache warm-up có thể tạo tải lớn lên database.

### Session

Session có thể nằm trong shared store hoặc memory của instance. In-memory session làm routing sticky trở nên cần thiết nhưng giảm khả năng failover. Nếu dùng shared session, cần schema compatibility, encryption và TTL. Logout/revoke phải có hiệu lực trên cả hai version.

### Static assets và CDN

HTML cũ có thể tham chiếu JS bundle mới hoặc ngược lại. Dùng content-hashed asset names, giữ asset cũ trong cache window và triển khai theo thứ tự tương thích. Không xóa bundle cũ ngay khi cutover nếu browser đang giữ HTML cũ.

### Feature flag

Feature flag cho phép tách deploy code khỏi việc bật chức năng. Cần:

- Owner và purpose rõ.
- Default off cho capability chưa sẵn sàng.
- Targeting theo tenant/cohort đã xác thực.
- Kill switch có kiểm thử và quyền kiểm soát.
- Metric theo flag/version.
- Ngày hết hạn/cleanup để tránh flag tồn tại vĩnh viễn.

Feature flag không thay rollout strategy; nó điều khiển behavior bên trong phiên bản đang chạy.

## 15. Stateful workloads và deployment strategy

Stateful workload khó triển khai hơn stateless vì mỗi instance có thể sở hữu dữ liệu local, partition, leader role hoặc quorum membership.

### Database và clustered stateful service

- Kiểm tra quorum khi thay node.
- Thay follower/replica trước leader nếu protocol cho phép.
- Đợi replication catch-up và xác minh health.
- Không thay cùng lúc nhiều node vượt disruption budget.
- Có fencing để tránh hai leader cùng ghi.
- Kiểm tra backup và recovery trước destructive upgrade.
- Tuân thủ upgrade path theo phiên bản được hỗ trợ.

### Queue consumer

Rolling update cần xử lý consumer cũ và mới cùng tiêu thụ queue. Dừng consumer cũ sau khi không nhận message mới, chờ message đang xử lý hoàn tất hoặc đưa lại queue theo semantics. Dùng idempotency để tránh duplicate khi shutdown giữa chừng.

### Scheduled jobs và singleton task

Nếu hai version cùng chạy scheduler, có thể chạy duplicate job. Dùng distributed lock/lease, leader election hoặc scheduler external; job cần idempotency và version-aware state. Khi chuyển blue–green, chỉ một environment nên kích hoạt scheduler authoritative tại một thời điểm, trừ khi job được thiết kế chạy song song.

### Graceful drain

Drain phải tính tới long-lived connection, WebSocket, streaming request, consumer lease và in-flight transaction. Một timeout drain cố định không phù hợp mọi workload; cần quy định theo service class và deadline.

## 16. Health gate và metric để quyết định tiếp tục rollout

Không nên tăng tỷ lệ rollout chỉ vì instance mới ở trạng thái Ready. Cần kết hợp platform health, service SLI và business outcome.

### Technical signals

- Startup/readiness success và restart count.
- HTTP/gRPC error rate, timeout và retry rate.
- p50/p95/p99 latency.
- CPU, memory, GC pause, thread/connection pool.
- Queue depth, oldest message age và consumer lag.
- Database connections, lock wait và replication lag.
- Dependency latency và error rate.
- Crash loop, OOM, throttling và network errors.

### Business signals

- Booking/payment success rate.
- Tỷ lệ checkout abandonment hoặc transaction conflict.
- Số invoice/job bị tạo trùng.
- Inventory correctness và data reconciliation.
- Tỷ lệ đăng nhập/authorization failure.
- Customer support contact hoặc synthetic journey failure.

Một phiên bản mới có thể có HTTP 200 tốt nhưng tạo booking sai hoặc làm tăng payment duplicate. Business metric nên nằm trong deployment gate với mức độ phù hợp.

### So sánh canary với baseline

| Dimension | Stable | Canary | Cách đọc |
| --- | --- | --- | --- |
| Error rate | 0,3% | 1,8% | Canary có khả năng regression |
| p99 latency | 420 ms | 900 ms | Tail latency xấu lên |
| CPU | 55% | 62% | Tăng nhẹ, chưa đủ kết luận |
| Booking success | 99,7% | 98,1% | Business outcome giảm |
| Payment duplicate | 0 | 3 | Guardrail nghiêm trọng, dừng và điều tra |

Các số liệu chỉ mang tính minh họa. Phải so trong cùng cohort, region, time window, traffic mix và request type; nếu không, so sánh có thể sai do khác tải.

### Guardrail và automatic analysis

Mỗi bước rollout có thể có điều kiện:

- **Continue:** tất cả critical guardrails pass và sample size đạt.
- **Pause:** dữ liệu chưa đủ hoặc metric không ổn định.
- **Abort/rollback:** vi phạm ngưỡng nghiêm trọng được xác định trước.
- **Manual review:** có signal mâu thuẫn hoặc business risk cần owner quyết định.

Không nên chỉ dùng một metric composite mờ khó giải thích. Ghi lại lý do tự động tiếp tục/dừng.

## 17. Bake time và sample size

Bake time là khoảng quan sát một phiên bản ở mức exposure hiện tại trước khi mở rộng. Thời gian cần đủ để thấy workload đại diện và lỗi có xác suất xuất hiện.

### Các yếu tố quyết định

- Traffic volume và số lượng request thực.
- Chu kỳ traffic ngày/đêm hoặc batch.
- Tác vụ theo lịch hàng giờ/ngày/tuần.
- Session dài hoặc user journey nhiều bước.
- Thời gian xử lý event/queue và eventual consistency.
- Tần suất giao dịch hiếm nhưng quan trọng.

Một canary 5% trong hai phút có thể không thấy lỗi chỉ xuất hiện khi nightly batch chạy. Ngược lại, bake time nhiều giờ với traffic rất thấp vẫn không cung cấp sample đủ mạnh.

### Minimum sample size

Phải định nghĩa số request/transaction tối thiểu trước khi đánh giá tỷ lệ lỗi. Nếu canary nhận quá ít traffic, không nên kết luận “không có lỗi” chỉ vì chưa quan sát thấy. Dùng synthetic test và targeted test để bổ sung coverage, nhưng không thay dữ liệu production hoàn toàn.

### Sequential rollout

Mỗi giai đoạn nên ghi:

- Tỷ lệ exposure.
- Thời điểm bắt đầu/kết thúc.
- Sample count.
- Guardrail result.
- Người/automation ra quyết định.
- Tình trạng dependency/capacity.

Nhờ đó có thể tái dựng vì sao rollout được tiếp tục hoặc dừng.

## 18. Rollback, roll-forward và feature disable

Rollback là đưa hệ thống về trạng thái/version trước đó. Roll-forward là phát hành bản sửa tiến lên. Feature disable tắt một capability mà không nhất thiết đổi binary.

| Cơ chế | Dùng khi | Điều kiện |
| --- | --- | --- |
| Traffic rollback | Phiên bản mới lỗi nhưng version cũ còn tương thích | Router chuyển lại được; data/schema không phá compatibility |
| Binary rollback | Artifact trước vẫn chạy với schema/config hiện tại | Old binary tương thích ngược |
| Roll-forward | Lỗi cần sửa nhanh hoặc migration không thể đảo ngược | Có patch/test và rollout an toàn |
| Feature kill switch | Một feature cụ thể gây lỗi | Flag có semantics an toàn và propagation nhanh |
| Restore | Dữ liệu bị hỏng/mất | Chọn đúng recovery point, kiểm tra RPO và integrity |

### Rollback readiness

Trước deployment cần xác định:

- Artifact/version trước đó ở đâu và có thể deploy lại không?
- Config/secret hiện tại có tương thích với version cũ không?
- Database migration có backward-compatible không?
- Event/cache/session format có đọc được không?
- Có side effect nào đã xảy ra không thể đảo ngược?
- Traffic routing và connection draining hoạt động ra sao?
- Ai quyết định rollback và có cần approval không?

### Rollback không phải nút hoàn tác mọi thứ

Một payment đã được xử lý không thể bị đảo ngược bằng cách rollback application. Một email đã gửi cũng không thể “thu hồi” bằng deployment. Hãy phân biệt state của phần mềm và side effect nghiệp vụ; cần reconciliation hoặc compensating action riêng.

### Roll-forward có thể an toàn hơn

Sau khi expand schema và đã có dữ liệu mới, rollback binary có thể khó hơn phát hành patch tương thích. Chọn theo trạng thái dữ liệu, không theo cảm tính “rollback luôn là tốt nhất”.

## 19. Traffic shifting và connection behavior

Traffic routing có thể dựa trên load balancer, ingress, service mesh, API gateway, DNS hoặc application router.

### Các kiểu traffic shift

- Weighted routing theo phần trăm.
- Header/cookie routing.
- User/tenant cohort.
- Region/AZ routing.
- Blue-green target switch.
- Feature-level routing trong ứng dụng.

### Long-lived connections

WebSocket, gRPC streaming, HTTP/2 và TCP connection có thể tồn tại sau khi traffic rule thay đổi. Router có thể chỉ áp dụng rule mới cho connection mới; connection hiện tại vẫn tới backend cũ. Cần quy định:

- Drain timeout.
- Maximum connection age.
- Graceful GOAWAY/close semantics nếu giao thức hỗ trợ.
- Sticky session behavior.
- Client reconnect và retry policy.
- Giới hạn reconnect storm khi cutover.

### DNS và cache

DNS TTL không bảo đảm mọi client đổi endpoint đúng thời điểm. Resolver/cache có thể giữ record lâu hơn hoặc kết nối cũ vẫn tồn tại. Với blue–green, không dùng DNS làm giả định cutover tức thời; đo propagation và có health check/rollback plan.

### Weighted routing không đảm bảo tỷ lệ chính xác theo user

Nếu một số khách hàng tạo nhiều traffic hơn, 5% request không đồng nghĩa 5% user/tenant. Khi chọn exposure, quyết định tỷ lệ theo mục tiêu: request volume, tenant count, revenue/transaction, data sensitivity hay risk cohort.

## 20. Security và supply chain trong deployment

Deployment là thời điểm artifact, config và identity mới được đưa vào môi trường production. Một rollout an toàn cần xác minh thứ được triển khai và quyền mà nó nhận.

### Artifact integrity

- Build từ pipeline/repository được kiểm soát.
- Scan dependency/container image theo policy.
- Pin version/digest thay vì tag mutable cho production.
- Ký artifact và xác minh signature/provenance nếu nền tảng hỗ trợ.
- Có SBOM hoặc dependency inventory theo yêu cầu.
- Hạn chế quyền push/pull registry và audit publish.

### Secrets và identity

- Dùng workload identity/secret manager thay vì hard-code secret.
- Cấp quyền tối thiểu cho phiên bản mới.
- Xác minh secret/certificate rotation tương thích với old/new versions.
- Tránh log secret trong startup/config dump.
- Có quy trình revoke nếu artifact hoặc credential bị compromise.

### IaC và configuration

Hạ tầng blue và green có thể drift. Quản lý infrastructure/config bằng source of truth, review policy và kiểm tra drift. Deployment nên gắn version artifact với config/manifest để biết chính xác tổ hợp đang phục vụ traffic.

### Progressive delivery và security gate

Canary có thể giới hạn blast radius nếu phiên bản mới có vulnerability hoặc quyền sai, nhưng không thay security review. Không chờ canary phát hiện secret leak hoặc privilege escalation; phải có static/dynamic scanning, policy gate và approval trước production.

## 21. Tự động hóa deployment bằng pipeline và progressive delivery

CI/CD pipeline biến quy trình phát hành thành các bước có thể lặp lại và kiểm tra. Progressive delivery bổ sung khả năng điều khiển exposure theo health/metric thay vì chỉ deploy xong là chuyển 100% traffic.

~~~mermaid
flowchart TD
    SRC["Source commit"]
    BUILD["Build + unit/integration tests"]
    SEC["Scan + sign artifact"]
    STAGE["Deploy staging"]
    TEST["Smoke + contract + load checks"]
    PROD["Deploy production candidate"]
    CANARY["Canary / blue-green / rolling"]
    GATE{"Health and business gates pass?"}
    EXPAND["Expand traffic / finish rollout"]
    PAUSE["Pause / abort / rollback"]
    SRC --> BUILD --> SEC --> STAGE --> TEST --> PROD --> CANARY --> GATE
    GATE -->|Yes| EXPAND
    GATE -->|No| PAUSE
~~~

### Pipeline stages

1. **Build:** tạo artifact bất biến từ source commit.
2. **Verify:** unit, integration, contract và security tests.
3. **Package:** image/artifact kèm digest, version và metadata.
4. **Deploy candidate:** staging hoặc production pool không nhận traffic lớn.
5. **Validate:** startup/readiness, smoke, synthetic và dependency checks.
6. **Progressive exposure:** rolling batch, blue-green cutover hoặc canary percentage.
7. **Analyze:** đánh giá SLI/business guardrail và sample size.
8. **Promote or abort:** tiếp tục, pause, rollback hoặc roll-forward theo policy.
9. **Finalize:** ghi deployment record và dọn tài nguyên theo rollback window.

### Deployment metadata

Gắn mỗi release với source commit/build ID, artifact digest/signature, config/IaC version, database migration version, feature flag version, deployment strategy, batch/exposure history, start/end time, approval và health gate decision. Metadata giúp liên kết incident với chính xác phiên bản/config, thay vì chỉ biết “vừa deploy”.

### Automation không nên che giấu quyết định

Nếu auto-promotion xảy ra, lưu metric và rule đã thỏa. Nếu auto-rollback, ghi nguyên nhân, threshold, thời gian và target version. Cần có pause/manual override có audit để tránh hệ thống tự động tiếp tục qua một anomaly chưa được model.

## 22. Canary analysis và so sánh thống kê

Canary analysis so sánh phiên bản mới với stable trong các điều kiện tương đương. Không chỉ nhìn giá trị tuyệt đối; cần xem baseline, variance và sample size.

### So sánh cùng điều kiện

- Cùng region hoặc điều chỉnh khác biệt region.
- Cùng endpoint/request class.
- Cùng tenant tier/client version nếu ảnh hưởng traffic.
- Cùng time window và peak/off-peak profile.
- Loại trừ traffic test nội bộ nếu không đại diện.
- Theo dõi cả dependency và downstream side effect.

### Absolute threshold và relative threshold

Absolute threshold có thể yêu cầu error rate dưới 1%; relative threshold có thể yêu cầu canary không xấu hơn stable quá 0,2 điểm phần trăm. Cả hai có thể cần thiết: stable vốn đang xấu thì “không tệ hơn stable” chưa đủ để rollout tiếp.

### Guardrail quan trọng hơn trung bình

Một lỗi hiếm nhưng có tác động lớn, như double charge hoặc cross-tenant data leak, có thể không làm error rate tổng tăng đáng kể. Dùng invariant/security guardrail riêng và dừng ngay khi có bằng chứng vi phạm.

### Correlation không chứng minh nguyên nhân

Canary error rate tăng có thể do traffic mix khác chứ không phải version. Kiểm tra cohort, request type, region và dependency trước khi kết luận. Tuy nhiên, khi rủi ro nghiêm trọng, pause exposure trước rồi điều tra; không cần đợi root cause mới giảm blast radius.

## 23. Deployment cho multi-region và multi-tenant

Ở hệ thống nhiều region hoặc tenant, rollout có thể được chia thành các failure domain/cohort để hạn chế tác động.

### Region-first rollout

1. Chọn một region pilot có traffic đại diện và capacity dự phòng.
2. Deploy phiên bản mới vào region pilot.
3. Chạy synthetic/business transaction và kiểm tra replication/dependency.
4. Tăng traffic/canary trong region.
5. Rollout các region còn lại theo wave.
6. Theo dõi global control plane và data consistency.

Region đầu tiên nên được chọn theo mức rủi ro và khả năng khôi phục, không mặc định chọn region ít traffic nhất nếu nó không đại diện.

### Tenant cohort rollout

Chia tenant theo tier, region, integration hoặc usage profile. Tenant pilot cần có owner, communication và opt-out/rollback plan phù hợp. Cần kiểm soát feature flags và route assignment từ trusted tenant identity.

### Shared control plane

Nếu deployment controller/flag service dùng chung toàn cầu, rollout controller lỗi có thể ảnh hưởng tất cả region. Có thể cần staged rollout cho chính control plane và chế độ fail-safe để data plane không bị khóa khi control plane tạm mất kết nối.

### Data residency và deployment

Canary/blue-green không được vô tình copy dữ liệu production sang region khác chỉ để test. Dùng synthetic data hoặc dataset đã được phê duyệt; bảo đảm backup, log và telemetry tuân thủ residency policy.

## 24. Rollout cho frontend, API và mobile client

Các lớp client cập nhật không đồng bộ. Backend có thể đã triển khai phiên bản mới trong khi browser/mobile app cũ tiếp tục hoạt động trong nhiều tuần.

### API evolution

- Thay đổi additive và giữ endpoint cũ trong compatibility window.
- Version API rõ ràng khi semantics thay đổi lớn.
- Quan sát client version và endpoint usage trước khi retire.
- Không yêu cầu mọi client cập nhật cùng lúc.

### Frontend/CDN

- Dùng hashed asset filename và immutable cache cho asset versioned.
- HTML/app shell cập nhật theo release metadata.
- Giữ asset cũ đủ lâu cho browser cache và session đang mở.
- Kiểm tra service worker update/rollback; service worker cũ có thể tiếp tục serve bundle cũ.

### Mobile

- Store approval và user adoption khiến client update chậm.
- Backend cần support N và N-1 (hoặc cửa sổ đã định nghĩa).
- Có thể dùng minimum supported version nhưng cần communication và fallback.
- Feature flag remote có thể tắt capability lỗi mà không cần chờ client release mới.

### Contract testing

Test provider với nhiều consumer version và giữ fixture của API/event cũ. Contract test giúp phát hiện breaking change trước release; nó không thay integration/e2e test cho business workflow.

## 25. Chọn chiến lược theo tình huống

| Tình huống | Chiến lược thường phù hợp | Điều kiện bổ sung |
| --- | --- | --- |
| Stateless API, additive code/schema | Rolling update | Readiness, drain, compatibility |
| Cần cutover nhanh và rollback traffic | Blue–green | Hai environment, shared-data safety |
| Business logic có rủi ro cao, traffic lớn | Canary | Metrics/cohort/bake time |
| Database engine/stateful cluster | Rolling theo protocol vendor | Quorum, replication, upgrade path |
| Frontend asset/API thay đổi | Rolling/blue–green kết hợp versioned assets | Client compatibility window |
| Tenant SaaS có pilot group | Tenant canary | Identity-based routing, tenant owner |
| Release hiếm, traffic nhỏ | Blue–green hoặc staged rollout | Synthetic test và manual review |
| Thay đổi destructive schema | Expand–migrate–contract, tách release | Backfill, validation, delayed contract |

### Decision flow

1. Có thể chạy old và new đồng thời an toàn không? Nếu không, cần migration/protocol thay đổi trước.
2. Có đủ capacity cho hai environment không? Nếu có và cần cutover rõ, cân nhắc blue–green.
3. Có traffic và metrics đủ để đánh giá từng cohort không? Nếu có, cân nhắc canary.
4. Service stateless, thay đổi nhỏ, cần tối ưu capacity? Rolling update thường phù hợp.
5. Stateful/quorum/database? Theo upgrade procedure riêng và kiểm tra consistency.
6. Có destructive data change? Thiết kế expand–migrate–contract trước khi chọn traffic strategy.

## 26. Case study: triển khai Booking API với rolling update

Một Booking API chạy 12 replicas ở ba AZ. Release mới thêm trường optional vào response, tối ưu query và thay đổi log format. API giữ backward compatibility; database không có migration destructive.

### Thiết kế rollout

- Max surge 2 replicas.
- Max unavailable 1 replica.
- Mỗi batch tối đa 2 instance.
- Readiness chỉ pass sau khi config/connection pool sẵn sàng.
- Drain request cũ trước khi terminate.
- Bake time 5 phút giữa các batch (giả định traffic đủ).

### Health gates

- Error rate không tăng vượt threshold so với baseline.
- p99 latency không vi phạm SLO.
- DB connection/CPU/replication lag trong giới hạn.
- Booking create success rate và duplicate count ổn định.
- Restart/OOM không tăng.

### Rollback

Nếu query mới gây latency tăng, pause rollout và rollback binary về version trước. Vì schema thay đổi additive và không destructive, version cũ vẫn hoạt động. Nếu đã tạo index mới, index được giữ lại tới khi xác nhận không có dependency; không xóa ngay trong incident.

### Điều cần lưu

Deployment record ghi batch, instance ID, version, readiness time, metric gate và quyết định. Nhờ đó on-call biết chính xác phần fleet nào đã cập nhật.

## 27. Case study: blue–green cho API thanh toán

Payment API cần thay runtime và cấu trúc nội bộ nhưng muốn cutover nhanh. Tổ chức có thể provision green độc lập, chạy contract/synthetic test với sandbox provider, rồi chuyển traffic theo từng tỷ lệ.

### Data contract

Blue và green cùng sử dụng payment ledger/database. Migration chỉ additive; green không ghi field mà blue không hiểu trong rollback window. Provider idempotency key được giữ ổn định theo payment operation.

### Cutover

1. Provision green với capacity và secret riêng.
2. Kiểm tra readiness, network egress, certificate, KMS và provider connectivity.
3. Chạy synthetic authorize/capture/void trong sandbox; production probe chỉ dùng transaction đã được phê duyệt và có đối soát.
4. Chuyển một phần traffic theo router nếu business/consistency cho phép.
5. Quan sát payment success, decline, timeout, duplicate và reconciliation.
6. Chuyển phần còn lại khi guardrails pass.
7. Giữ blue tới khi hoàn tất rollback window.

### Rollback safety

Nếu green có lỗi, chuyển traffic về blue. Payment operation đã commit ở provider không được chạy lại với key mới; cần query state bằng provider reference. Cả hai version phải hiểu trạng thái pending/unknown và ledger format.

Blue–green giảm rủi ro cutover code nhưng không tách transaction với external payment provider; idempotency và reconciliation vẫn bắt buộc.

## 28. Case study: canary theo tenant cho SaaS multi-tenant

Một SaaS thêm luồng export hóa đơn mới. Tenant có quy mô và tích hợp khác nhau; lỗi có thể xuất hiện với tenant có hàng triệu invoice hoặc custom policy.

### Chọn cohort

- Nhóm nội bộ dùng synthetic dataset.
- Một tenant pilot có volume trung bình và owner đồng ý.
- Một tenant có volume lớn sau khi batch/limit được kiểm thử.
- Mở rộng theo tier/region, không chỉ theo số tenant.

### Routing và guardrails

Feature flag được đánh giá từ canonical tenant identity đã xác thực, không dựa header tùy ý. Metric phân nhóm theo version/tenant tier nhưng tránh label cardinality vô hạn. Guardrail gồm export success, time-to-complete, file correctness, storage cost và cross-tenant access test.

### Pause/rollback

Nếu file sai hoặc chứa record tenant khác, tắt flag ngay, dừng worker mới, cách ly output đã tạo, bảo toàn evidence và kích hoạt security/privacy review theo quy trình. Không chỉ route về code cũ rồi bỏ qua file đã phát hành; cần xử lý access đối với output theo semantics storage.

## 29. Những sai lầm thường gặp

1. **Coi Ready là đủ để promote:** instance có thể khỏe ở platform nhưng business transaction sai.
2. **Rolling quá nhiều instance cùng lúc:** capacity còn lại không đủ hoặc quorum bị ảnh hưởng.
3. **Không tính max surge:** cluster thiếu CPU/memory/quota khi tạo instance mới.
4. **Drain không đúng:** request dài, WebSocket hoặc message đang xử lý bị cắt.
5. **Old và new không backward-compatible:** deployment thành công nhưng request đi qua version khác nhau cho kết quả khác.
6. **Destructive DB migration cùng release:** binary rollback không thể khôi phục schema/data.
7. **Blue–green chỉ đổi router:** scheduler/worker ở hai môi trường cùng chạy job và tạo side effect trùng.
8. **Blue bị hủy quá sớm:** mất khả năng rollback traffic khi lỗi xuất hiện sau bake time.
9. **Cho rằng DNS cutover tức thì:** resolver và connection cũ vẫn route tới endpoint trước.
10. **Canary cohort không đại diện:** chỉ thử internal/light traffic rồi bỏ sót tenant hoặc peak workload.
11. **Canary sample quá nhỏ:** không đủ dữ liệu để kết luận error rate.
12. **Chỉ đo metric trung bình:** bỏ sót p99, duplicate transaction hoặc data correctness.
13. **Không tách traffic theo version:** không biết lỗi đến từ stable hay canary.
14. **Không có minimum bake time:** lỗi theo chu kỳ xuất hiện sau khi đã promote hết.
15. **Feature flag không cleanup:** code path cũ và mới cùng tồn tại, tăng complexity.
16. **Rollback không tính side effect:** payment, email hoặc event đã commit không tự đảo ngược.
17. **Không giữ static asset cũ:** browser cache/service worker dùng HTML và JS không tương thích.
18. **Không test client N-1:** mobile và integration cũ tiếp tục hoạt động sau release.
19. **Tăng rollout khi dependency đang degraded:** lỗi downstream bị nhầm là lỗi version hoặc bị che bởi retry.
20. **Không ghi deployment metadata:** incident không thể truy ngược artifact/config chính xác.

## 30. Checklist review deployment strategy

- Chiến lược có phù hợp stateful/stateless và risk của thay đổi không?
- Có xác định old/new version coexistence và compatibility window không?
- Readiness, liveness, startup probe và graceful drain có phân biệt đúng không?
- Max surge/max unavailable có được tính theo capacity/quota và failure domain?
- Load balancer/traffic router có health gate và rollback route không?
- DNS, long-lived connection, sticky session và reconnect behavior đã xem xét?
- Database migration dùng expand–migrate–contract khi cần không?
- Event producer/consumer và queue replay có tương thích schema không?
- Cache/session/static assets có versioning và migration plan không?
- Worker/scheduler tránh chạy duplicate qua hai environment thế nào?
- Canary cohort và sample size có đại diện không?
- Bake time đủ cho traffic/cron/queue cycle không?
- Technical và business guardrail có so sánh stable/canary theo cùng điều kiện?
- Có auto-pause/abort, manual override và decision evidence?
- Rollback/roll-forward/feature disable có owner và stop condition?
- Side effect nghiệp vụ có idempotency/reconciliation?
- Artifact provenance, signature, scan, secret và least privilege đã kiểm tra?
- Multi-region/tenant rollout có giới hạn blast radius và data residency?
- Deployment record gắn commit, artifact, config, migration, flag và approval?
- Runbook incident/rollback và post-deploy monitoring có sẵn?

## 31. Các chỉ số theo dõi sau deployment

| Nhóm | Chỉ số |
| --- | --- |
| Deployment progress | Instances updated, rollout duration, batch status, pause/failure count |
| Availability | Success rate, readiness failure, restart/crash loop |
| Latency | p50/p95/p99 theo version/cohort |
| Correctness | Business success, duplicate, invariant violation, reconciliation |
| Capacity | CPU, memory, network, connection/pool, autoscaler activity |
| Dependency | DB latency/replication, cache, queue lag, external API |
| Traffic | Request count, cohort exposure, region/tenant distribution |
| Recovery | Rollback count/time, time to mitigate, late completion |
| Cost | Surge capacity, dual environment hours, data transfer, idle resources |
| Security | Artifact signature/provenance, policy violations, access anomalies |

### Deployment frequency và change failure rate

Deployment frequency cho biết tốc độ phát hành; change failure rate thể hiện tỷ lệ deployment gây incident/rollback/hotfix theo định nghĩa tổ chức; lead time for changes và time to restore bổ sung góc nhìn luồng delivery và reliability. Không tối ưu một metric riêng lẻ: tăng tần suất phát hành mà tăng lỗi nghiêm trọng có thể làm giảm kết quả tổng thể.

### So sánh trước/sau

Giữ baseline trước deployment, phân đoạn theo version và thời gian. Khi có thay đổi traffic mix, region hoặc dependency, ghi nhận để tránh kết luận sai. Sau mỗi rollout, lưu kết quả vào deployment record và review các ngưỡng nếu cảnh báo quá nhạy hoặc bỏ sót lỗi.

## 32. Bài tập thực hành và đáp án định hướng

Một service đặt chỗ có 8 replicas, chạy ở hai AZ. Release mới thay đổi API response, thêm một cột database và thay cách xử lý message. Đội phát triển đề xuất canary 10% trong 2 phút rồi triển khai toàn bộ. Hệ thống có mobile client cũ, queue giữ message 24 giờ và worker chạy tác vụ theo lịch.

### Câu 1 — Canaries 10% trong 2 phút có đủ không?

**Đáp án định hướng:** Chưa thể kết luận. Cần traffic volume, minimum sample size, peak profile, batch/queue cycle và lỗi hiếm. Hai phút có thể không thấy scheduled job hoặc replay event; bake time phải theo workload.

### Câu 2 — Có thể thay API response và deploy ngay không?

**Đáp án:** Kiểm tra mobile N-1 và integration consumer. Ưu tiên additive field/giữ semantics cũ; nếu breaking change, dùng API version hoặc compatibility window. Contract test phải chạy với consumer cũ.

### Câu 3 — Migration thêm cột có thể chạy trước không?

**Đáp án:** Nếu additive và backward-compatible, có thể expand trước app release. Backfill theo batch và verify; contract/remove cột cũ chỉ sau rollback window và không còn consumer.

### Câu 4 — Queue message 24 giờ ảnh hưởng gì?

**Đáp án:** Consumer mới phải đọc event cũ trong retention/replay window. Giữ schema compatibility hoặc upcaster/adapter; test DLQ replay và out-of-order event.

### Câu 5 — Scheduler có thể chạy ở cả old và new không?

**Đáp án:** Chỉ khi job idempotent và có coordination/lease tránh chạy trùng. Nếu không, chỉ một environment/leader được quyền scheduler trong thời điểm cutover.

### Câu 6 — Rolling update cần tính capacity nào?

**Đáp án:** Với 8 replicas, max surge và max unavailable xác định số instance đồng thời. Tính CPU/memory, connection DB và quota node trong lúc old/new coexist; giữ đủ capacity nếu mất thêm một AZ.

### Câu 7 — Dấu hiệu nào phải abort canary ngay?

**Đáp án:** Vi phạm security/data isolation, double booking/duplicate payment, data corruption hoặc business invariant nghiêm trọng. Error rate/p99 vượt guardrail cũng có thể abort theo policy; không đợi đủ sample nếu có lỗi critical đã xác minh.

### Câu 8 — Khi rollback, có cần rollback database không?

**Đáp án:** Không mặc định. Nếu schema additive, giữ schema và rollback binary tương thích thường an toàn hơn. Chỉ rollback data/schema khi có migration rollback được kiểm chứng; destructive migration thường cần forward fix hoặc restore/repair plan.

## 33. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Độ tin cậy** | Release có giới hạn blast radius, rollback và khôi phục được không? | Health gates, canary, drain, rollback/DR tests |
| **Bảo mật** | Artifact, config, secret và traffic mới có được xác minh và cấp quyền tối thiểu không? | Signature/provenance, scanning, IAM, secret manager |
| **Hiệu năng** | Rollout có giữ capacity, tail latency và dependency health không? | Surge sizing, p95/p99, pool/queue metrics |
| **Tối ưu chi phí** | Có lựa chọn mức surge/dual environment/bake time hợp lý không? | Cost per release, environment hours, right-sizing |
| **Vận hành xuất sắc** | Deployment có tự động hóa, record, runbook và decision gate không? | CI/CD, deployment metadata, pause/abort, incident runbook |
| **Tính bền vững** | Tài nguyên tạm và môi trường cũ có được dọn đúng thời điểm không? | Cleanup policy, retention, capacity utilization |

Rolling update, blue–green và canary là các cách phân phối rủi ro của một thay đổi. **Rolling update thay dần instance; blue–green chuyển traffic giữa hai môi trường; canary kiểm chứng phiên bản mới trên một phần workload trước khi mở rộng.** Chọn chiến lược dựa trên khả năng coexistence, trạng thái dữ liệu, capacity, chất lượng telemetry và khả năng khôi phục. Một deployment an toàn kết thúc khi phiên bản mới được xác minh trên hành trình nghiệp vụ thực, các side effect được đối soát và đường rollback/cleanup được xử lý theo kế hoạch.
