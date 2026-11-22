# Phát hành thử với một phần lưu lượng trước khi triển khai rộng

Một ứng dụng Java có thể biên dịch thành công trên JDK mới, vượt qua unit test và integration test, thậm chí chạy tốt trong môi trường staging, nhưng vẫn phát sinh lỗi khi gặp dữ liệu, nhịp tải, thời gian sống và sự đa dạng request thực tế ở production. Một trong những cách giảm rủi ro là **phát hành thử (canary release) cho một phần lưu lượng có kiểm soát**, quan sát kết quả, rồi chỉ mở rộng phạm vi khi có đủ bằng chứng.

Trong **Java Advance Compatibility Migration**, canary đặc biệt hữu ích bởi lỗi nâng JDK có thể biểu hiện dưới nhiều hình thức:

- Một endpoint ít dùng mới nạp thư viện không còn tương thích class-file version hoặc API.
- Framework dùng reflection vào JDK internals và chỉ thất bại ở một workflow.
- JDK mới thay đổi mặc định về charset, TLS, locale hoặc timezone khiến payload khác trước.
- Java agent, JNI library hoặc bytecode instrumentation phát sinh lỗi trên runtime mới.
- JIT cần thời gian làm nóng, khiến pod mới có độ trễ cao lúc bắt đầu nhận traffic.
- Cấu hình GC, heap, CPU quota hay container image làm thay đổi p99 latency và chi phí vận hành.
- Ứng dụng vẫn chạy nhưng ghi dữ liệu theo định dạng mà phiên bản cũ không đọc được, làm rollback nguy hiểm.

Canary không thay thế các bước kiểm thử trước phát hành. Nó là **cổng kiểm chứng sau khi đã có một release đủ điều kiện đưa vào production**, với phạm vi ảnh hưởng được giới hạn và khả năng ngừng hoặc quay lại phiên bản ổn định.

Bài học này hướng dẫn thiết kế canary cho migration JDK, từ baseline, lựa chọn cohort/traffic, tính tương thích dữ liệu, cấu hình định tuyến, metrics và guardrails đến phân tích kết quả, rollout, rollback và bàn giao vận hành. Các ví dụ YAML, lệnh và chỉ số chỉ là mẫu minh họa để điều chỉnh theo hệ thống thật; không tự áp dụng lên production.

## 1. Canary release là gì?

### 1.1. Khái niệm

**Canary release** là cách triển khai một bản ứng dụng mới tới một phần nhỏ môi trường hoặc người dùng thật trước khi chuyển toàn bộ lưu lượng. Trong thời gian thử, phiên bản ổn định và phiên bản mới cùng tồn tại.

Ví dụ tổng quát:

```text
                      Production traffic
                              |
                              v
                       Ingress / Gateway
                              |
                  +-----------+------------+
                  |                        |
               Stable                   Canary
            JDK hiện tại              JDK đích
            App release A             App release A/B
                  |                        |
                  +-----------+------------+
                              |
                    Shared dependencies
                     DB / queue / cache
```

Mục đích không chỉ là “có một pod chạy JDK mới”, mà là **một tập request thực sự được xử lý bởi bản mới, với khả năng đo và đảo ngược lưu lượng**.

### 1.2. Phải định nghĩa “một phần lưu lượng” thật rõ

Có ít nhất ba cách diễn giải rất khác nhau:

1. **Phần trăm request:** gateway định tuyến một tỷ lệ request tới canary.
2. **Phần trăm người dùng/tenant/session:** một cohort cố định được gán vào canary.
3. **Phần trăm instance/pod:** một số replica chạy phiên bản mới.

Chúng **không tương đương**.

Nếu có 1 pod mới trong 10 pod, không thể mặc định canary nhận đúng 10% request. Load balancer, connection reuse, sticky session, pod readiness và autoscaling đều có thể làm phân bố lệch. Cần đo tỷ lệ request thực tế theo version.

### 1.3. Câu hỏi mà canary phải trả lời

Với migration Java, mục tiêu có thể là:

> “Bản ứng dụng đang chạy trên JDK 21 có duy trì các hợp đồng nghiệp vụ, SLO về lỗi/độ trễ và chi phí tài nguyên trong production traffic khi so với bản JDK 17 hay không?”

Câu trả lời phải gắn với:

- Artifact và runtime versions cụ thể.
- Phạm vi traffic/cohort được thử.
- Thời gian quan sát.
- Những code paths đã được kích hoạt.
- Tiêu chí pass/fail định nghĩa trước.
- Các rủi ro chưa được bao phủ.

Canary pass không phải bằng chứng rằng mọi workflow hoặc mọi thời điểm trong tương lai đều an toàn.

## 2. Phân biệt canary, rolling, blue-green, feature flag và shadow traffic

| Kỹ thuật | Cách hoạt động | Điểm mạnh | Giới hạn |
|---|---|---|---|
| **Canary** | Phân phối một phần traffic tới bản mới | Quan sát production behavior với blast radius nhỏ | Cần routing, telemetry và rollback tốt |
| **Rolling update** | Thay instance cũ bằng instance mới dần dần | Dễ dùng với orchestrator | Số pod mới không nhất thiết là tỷ lệ traffic có thể kiểm soát |
| **Blue-green** | Hai môi trường hoàn chỉnh; chuyển traffic từ blue sang green | Chuyển đổi/rollback traffic nhanh nếu state tương thích | Thường cần tài nguyên gấp đôi và thao tác cutover lớn |
| **Feature flag** | Bật/tắt một chức năng cho một cohort | Tách business feature khỏi deploy | Không thay được JVM của process đang chạy |
| **Shadow/mirroring** | Sao chép một phần request sang bản mới, không dùng response shadow | Có thể quan sát trước khi phục vụ user | Side effects, dữ liệu cá nhân và I/O rất nguy hiểm nếu không cách ly |
| **A/B experiment** | Phân nhóm để đo hiệu quả sản phẩm | So sánh business outcomes | Không thay thế compatibility/safety gate |

Một đợt phát hành có thể kết hợp các kỹ thuật. Ví dụ:

- Canary 5% các phiên session để đánh giá JDK mới.
- Feature flag giữ tắt tính năng nghiệp vụ mới để cô lập runtime change.
- Rolling update bên trong nhóm canary pods.
- Blue-green cho chuyển đổi hạ tầng lớn.

Đừng gọi một lần rolling update mặc định là “canary có phân tích” nếu không có traffic controls, observability và decision gates.

## 3. Vì sao canary đặc biệt quan trọng khi nâng JDK?

### 3.1. Correctness và startup pass chưa đủ

Một binary có thể tải được class và báo health thành công, nhưng chỉ gặp lỗi khi:

- Tạo TLS connection đến đối tác dùng thuật toán/certificate cũ.
- Serialize XML bằng JAXB, JAX-WS provider chỉ được nạp động.
- Gọi JDBC driver hoặc native compression library hiếm khi dùng.
- Xử lý file từ khách hàng có charset khác UTF-8.
- Một plugin có class major cao hơn JVM runtime.
- Java agent instrument một class chỉ load trong transaction đặc biệt.

Canary giúp nhận những lỗi phụ thuộc traffic thật mà staging chưa mô phỏng đủ, nhưng phải **cố ý chọn phạm vi kích hoạt**. Nếu chỉ 1% request chủ yếu gọi health endpoint, kết quả sẽ ít giá trị.

### 3.2. Hiệu năng phụ thuộc runtime và traffic mix

Một lần nâng JDK có thể ảnh hưởng:

- HotSpot JIT, tiered compilation, deoptimization và code cache.
- GC implementation/defaults và heap ergonomics.
- Thread scheduling, CPU quota và container awareness.
- Reflection/proxy/code generation.
- Memory allocation và native memory.
- HTTP/TLS/charset/timezone behavior.
- Java agents, profiler và monitoring instrumentation.

Tại 1% traffic, canary có thể **không đủ tải để làm nóng cùng hot paths** như stable, nên latency có thể cao hơn mà không đại diện cho steady-state của bản mới ở 100%. Ngược lại, một canary quá ít tải có thể không bộc lộ contention hoặc memory leak khi traffic tăng.

### 3.3. Canary là công cụ quản lý blast radius

Khi có lỗi chỉ ở bản mới, tắt routing tới canary có thể giảm số request tiếp tục bị ảnh hưởng. Tuy nhiên, không phải mọi side effect có thể rollback ngay:

- Database writes đã commit.
- Queue messages đã publish.
- Emails/payments đã gửi.
- Caches bị ghi theo schema mới.
- Long-lived sessions và WebSocket connections.
- Scheduled jobs chạy trên canary.
- Data migrations không đảo ngược.

Vì vậy, **rollback traffic là một phần của rollback, không phải toàn bộ rollback**.

## 4. Các điều kiện phải hoàn thành trước canary

Không nên đưa bản chưa vượt kiểm thử cơ bản vào production chỉ để “nhờ canary bắt lỗi”.

### 4.1. Preflight bắt buộc

Trước khi mở một request thật:

1. Build artifact có provenance rõ ràng, checksum/image digest.
2. Xác minh JDK vendor, major/update/build và runtime process thật.
3. Kiểm tra compatibility matrix của framework, dependency, application server, agents và JNI.
4. Compile/run unit, integration, contract, migration tests trên JDK đích.
5. Smoke test artifact cuối, không chỉ classes của source set.
6. Kiểm tra startup flags, JPMS, reflective access và class loading.
7. Kiểm tra TLS/certificates, data encoding, file I/O, serialization.
8. Kiểm tra readiness/liveness/startup probes.
9. Có observability phân tách stable/canary.
10. Có owner, trực vận hành, stop/rollback procedure có thể thực thi.
11. Có baseline và ngưỡng quyết định được thống nhất.
12. Database/shared-state compatibility đã được kiểm chứng khi hai phiên bản cùng tồn tại.

### 4.2. Tách thay đổi để suy luận nguyên nhân

Một cách hữu ích:

```text
Stable:
  App binary: A
  JDK: 17
  Framework: F
  Config: C

Canary runtime-first:
  App binary: A
  JDK: 21
  Framework: F
  Config: C
```

Cần giữ tất cả biến khác giống nhau khi khả thi. Nếu image base thay đổi hoặc runtime Java 21 buộc nâng framework, ghi đây là **JDK + environment/framework migration**.

Nếu canary dùng app release B, dependency mới và feature flags mới đồng thời, khi p99 tăng sẽ khó phân biệt nguyên nhân. Điều đó không làm thử nghiệm vô giá trị, nhưng không thể kết luận riêng “JDK 21 gây chậm” từ phép thử như vậy.

### 4.3. Khi không thể thực hiện canary an toàn

Có những migration phải được xử lý trước bằng staging/isolated deployment hoặc kiến trúc mở rộng:

- Database schema migration không tương thích với phiên bản cũ.
- Shared cache/session format không backward/forward compatible.
- Không có cách định tuyến traffic hay cô lập side effects.
- Tác vụ batch/queue chỉ có một active leader và không có cơ chế chuyển owner.
- Native library hoặc server upgrade có tác dụng toàn cluster, không chạy song song được.
- Sản phẩm không có metrics/rollback đủ để phát hiện và giới hạn lỗi.
- Chính sách pháp lý không cho phép dùng một nhóm khách hàng làm thử nghiệm không có kiểm soát.

Canary là một phương pháp, không phải lý do bỏ các biện pháp bảo vệ dữ liệu hoặc vận hành.

## 5. Chụp baseline của phiên bản ổn định

### 5.1. Baseline có hai phần

**Artifact/environment baseline:**

- Git revision và application release.
- JAR/WAR/EAR checksum hoặc container image digest.
- JDK vendor/version/build.
- Framework/server versions.
- Runtime dependency graph và agent/native library versions.
- JVM flags, GC, heap, env và system properties.
- OS, architecture, CPU/memory limits, container runtime.
- External service versions và database schema.

**Operational baseline:**

- Traffic volume theo route, tenant và request type.
- Error rate, timeout và retry counts.
- p50/p95/p99 latency, queueing và throughput.
- CPU per request, throttling, allocation, GC, RSS.
- Startup/readiness, warm-up và autoscaling.
- Business success metrics và data correctness indicators.
- Lỗi đã tồn tại trước migration.

Một biểu đồ canary màu xanh không đủ nếu baseline thật cũng có lỗi, traffic composition khác hoặc metrics bị gắn nhãn sai.

### 5.2. Đo cùng thời điểm khi có thể

So sánh canary với stable **cùng thời gian** giúp giảm ảnh hưởng của traffic seasonality, backend incidents và thay đổi tải. Nhưng vẫn cần cân nhắc khác biệt cohort:

- Canary có nhiều người dùng mới hay nhiều khách hàng lớn hơn?
- Canary có request sizes hoặc endpoints giống stable không?
- Canary có nhận traffic từ một khu vực mạng chậm hơn không?
- Một zone/node chứa canary có CPU throttling hơn stable không?

Một so sánh tốt nên cố gắng cân bằng cohort hoặc chuẩn hóa theo traffic mix, thay vì nhìn một aggregate latency duy nhất.

## 6. Thiết kế traffic splitting đúng mục tiêu

### 6.1. Weighted request routing

Gateway/service mesh có thể định tuyến theo trọng số:

```text
Stable 95%
Canary  5%
```

Đây là **trọng số phân phối mong muốn**, không phải bảo đảm đúng 5% request trong mọi khoảng thời gian nhỏ. Kết quả phụ thuộc routing implementation, connection reuse, retries, readiness và phân phối traffic thực.

Cần đo:

```text
actual_canary_share =
  requests_handled_by_canary /
  requests_handled_by_all_versions
```

Với request streams, WebSockets hoặc long-lived connections, “% request” và “% connection/user” có thể khác rất xa.

### 6.2. Cohort routing theo user/tenant

Khi session hoặc business workflow kéo dài qua nhiều request, định tuyến ổn định theo hash user/tenant có thể có lợi:

```text
hash(tenant_id) -> cohort
  cohort stable  -> JDK cũ
  cohort canary  -> JDK mới
```

Ưu điểm:

- Một user không bị chuyển phiên bản ở mọi request.
- Dễ so sánh business outcome ở mức cohort.
- Có thể định tuyến một workflow nhất quán.
- Có thể exclude nhóm khách hàng rất nhạy cảm ban đầu.

Nhược điểm:

- Cohort nhỏ có thể không đại diện.
- Tenant lớn có thể chiếm phần lớn tải dù ít tenant.
- User được gán cố định không giúp test mọi quốc gia/chức năng.
- Sticky routing làm rollback phức tạp hơn nếu session/state của bản mới không tương thích.

Cần công bố đúng đơn vị phân chia: request, session, user, tenant hay connection.

### 6.3. Route hoặc endpoint targeting

Một số đội ngũ chỉ bật canary cho những route ít rủi ro ban đầu. Ví dụ:

```text
GET /catalog/*       canary eligible
GET /orders/*        canary eligible
POST /payments       stable-only initially
POST /refunds        stable-only initially
```

Đây là chiến lược giảm rủi ro nhưng coverage còn thiếu. Phải lên kế hoạch kiểm tra những đường quan trọng trước khi full rollout, trong môi trường sandbox hoặc với cohort được phép.

Không được kết luận hệ thống thanh toán an toàn chỉ vì canary xử lý tốt một endpoint đọc dữ liệu.

### 6.4. Định tuyến theo region hoặc zone

Deploy canary ở một vùng địa lý/availability zone có thể giảm blast radius, nhưng tạo biến số:

- Regional traffic khác nhau.
- Database replica/latency khác.
- TLS/certificate/network policies khác.
- CPU/OS nodes hoặc hardware generation khác.
- Phân bố tenant và dữ liệu không đồng nhất.

Nếu mục tiêu đo riêng tác động JDK, cần có stable baseline trong **cùng region/zone hoặc hạ tầng tương đương**.

### 6.5. Retry có thể làm sai tỷ lệ thực

Một gateway có thể retry request thất bại qua version khác. Nếu một request bị canary xử lý thất bại rồi stable xử lý thành công, metric cuối cùng ở client có thể che lỗi ban đầu.

Cần theo dõi:

- Routing decision ban đầu.
- Backend attempts theo version.
- Retry count và nguyên nhân.
- Response cuối cùng client nhận.
- Duplicate side effects.

Không đánh giá canary chỉ bằng overall success rate khi retry policy che lỗi ở bản mới.

## 7. Không nhầm số pod với phần trăm traffic

### 7.1. Kubernetes Deployment rolling update

Một Kubernetes Deployment có thể dùng:

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0
```

Cấu hình này mô tả **thay thế pod theo đợt**, không tạo một traffic split canary 5% có thể quan sát và giữ cố định trong một thời gian.

Nếu dùng một Service chung trỏ cả pod cũ và mới, traffic distribution bị ảnh hưởng bởi endpoint set, connection pooling và routing implementation. Đặc biệt với long-lived connections, số request được xử lý có thể lệch hẳn tỷ lệ replicas.

### 7.2. Canary thường cần hai workload và routing control

Một mô hình minh họa:

```text
Deployment: order-stable   image: order:jdk17
Service:    order-stable

Deployment: order-canary   image: order:jdk21
Service:    order-canary

Gateway / service mesh:
  backend order-stable -> weight 95
  backend order-canary -> weight 5
```

Tách workload giúp giữ đồng thời hai version, điều chỉnh weight và scale canary độc lập. Nhưng thiết kế cuối cùng phụ thuộc platform/rollout controller, không nên sao chép kiến trúc này nếu môi trường đã có cơ chế canary được hỗ trợ khác.

### 7.3. Readiness ảnh hưởng effective traffic

Canary pod có thể được tạo nhưng chưa ready vì:

- JDK startup flags lỗi.
- Framework class initialization fail.
- Config/secrets chưa có.
- Java agent fail.
- Native library load fail.
- Health probe timeout quá ngắn.

Nếu pod không ready, request không tới canary; một hệ thống chỉ nhìn overall 200 responses có thể “pass” dù **không hề có request canary**. Phải có gate xác minh số pod ready và số request thực tế đi qua canary.

## 8. Ví dụ định tuyến theo trọng số bằng Kubernetes Gateway API

Một nền tảng hỗ trợ **Gateway API HTTPRoute weighted backends** có thể khai báo minh họa:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: order-routing
spec:
  parentRefs:
    - name: order-gateway
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /orders
      backendRefs:
        - name: order-stable
          port: 8080
          weight: 95
        - name: order-canary
          port: 8080
          weight: 5
```

**Điều kiện tiên quyết:**

- Namespace, gateway, listeners, Services và backend ports phải tồn tại.
- Gateway implementation phải hỗ trợ tính năng weighted backends.
- Route phải được controller chấp nhận và attached đúng listener/hostname.
- Authentication, TLS và policy attachment phải nhất quán.
- Các route khác không được vô tình bypass canary split.
- Có metrics/labels phân biệt stable và canary sau routing.

Ví dụ này là cấu hình tham khảo, **không phải file áp dụng trực tiếp cho production**. Sau khi apply trong môi trường được phép, phải xác nhận route status và phân bố request thực tế.

### 8.1. Tăng weight không có nghĩa tăng capacity tương ứng

Nếu canary có một replica và stable có nhiều replicas, chuyển từ 5% lên 25% traffic có thể làm canary quá tải trước khi người dùng được hưởng benefit của bản mới. Cần xem:

- Request rate/CPU theo pod.
- Concurrency limit.
- HPA behavior.
- Queue length.
- Memory/heap và GC.
- Network/DB connection pool size.
- Pod readiness và warm-up.
- Traffic hotspots/tenant skew.

Traffic weight và số replicas phải được thiết kế cùng nhau nhưng không đánh đồng.

### 8.2. Nếu không có weighted-routing controller

Có thể dùng:

- Service mesh có traffic split.
- API gateway/ingress controller hỗ trợ canary.
- Application load balancer có weighted target groups.
- Cohort routing tại reverse proxy.
- Blue-green với chuyển tenant/dịch vụ từng nhóm.

Không tạo một script tự thay endpoint labels thủ công trên production chỉ để mô phỏng canary khi thiếu cơ chế rollback an toàn.

## 9. Chọn kế hoạch tăng lưu lượng theo giai đoạn

### 9.1. Lộ trình mẫu

Một chuỗi minh họa:

```text
0% (deploy, no traffic)
      |
      v
1%  -> 5% -> 10% -> 25% -> 50% -> 100%
       |      |      |      |
    Gate A  Gate B Gate C Gate D
```

Không có tỷ lệ hay thời gian cố định phù hợp mọi hệ thống. Với service có traffic thấp, 1% có thể quá ít mẫu; với service có hàng triệu request, 1% có thể đã là blast radius lớn.

Có thể bắt đầu bằng một cohort nội bộ hoặc khu vực giới hạn thay vì tỷ lệ request cố định. Lộ trình nên dựa trên **risk budget, traffic volume và mức độ confidence**, không dựa vào “quy tắc 5%” chung chung.

### 9.2. Mỗi giai đoạn cần ba điều kiện

1. **Minimum exposure:** đủ request/transactions có ý nghĩa đã được bản canary xử lý.
2. **Minimum observation:** đủ thời gian để quan sát startup, warm-up, GC, scheduled jobs hoặc lỗi chậm.
3. **Guardrails đạt:** error, latency, resource và business metrics trong ngưỡng đã định, không có incident trọng yếu.

Nếu không đủ mẫu hoặc có telemetry gap, kết luận là **INCONCLUSIVE**, không phải PASS.

### 9.3. Giai đoạn đầu có thể cần lâu hơn tưởng tượng

Một canary 1% trong hệ thống ít traffic có thể không nhận được workflow hiếm trong nhiều ngày. Trường hợp này cần:

- Trình tự smoke/contract synthetic test bổ sung.
- Cohort được chọn để có workflow cần kiểm chứng.
- Thời gian quan sát dài hơn.
- Tăng traffic đến mức có mẫu đủ, với guardrails rõ.
- Hoặc kiểm chứng trong môi trường isolated trước khi mở rộng.

Không tăng traffic chỉ để đạt cỡ mẫu khi chưa có khả năng rollback hoặc monitoring phù hợp.

### 9.4. Tránh tiến lên khi metrics chưa được tổng hợp đầy đủ

Hệ thống metrics có thể có scrape interval và delay, log ingestion bị trễ hoặc tracing sampling khác nhau. Nếu vừa đổi weight 5% lên 25%, không nên ngay lập tức tăng lên 50% trước khi window của 25% có dữ liệu đủ.

Ghi rõ timestamps cho từng stage, phân biệt khoảng startup/ramp và stable window.

## 10. SLO, SLI và guardrails cho canary Java

### 10.1. Chọn metrics có ý nghĩa với người dùng

Một số SLI quan trọng:

| Nhóm | SLI | Câu hỏi |
|---|---|---|
| Availability | Tỷ lệ request/transaction thành công | User có hoàn thành công việc không? |
| Latency | p50/p95/p99 hoặc tỷ lệ request dưới threshold | Bản mới có làm tail latency xấu đi? |
| Correctness | Dữ liệu/response contract mismatch | Có trả kết quả đúng không? |
| Error quality | 5xx, timeouts, exceptions, retries | Có lỗi mới bị retry che không? |
| Resource | CPU/req, RSS, GC, native memory | Chi phí vận hành có tăng không? |
| Startup | Time to readiness, cold p99 | Pod mới có nhận tải an toàn không? |
| Business | Payment success, completed orders | Business outcome có thay đổi không? |
| Async | Queue lag, consumer errors, DLQ | Background processing có bị ảnh hưởng không? |
| Security | TLS/auth failures, policy violations | JDK security defaults có làm integration fail không? |

Không chọn chỉ CPU hoặc chỉ request error rate. Một bản có CPU thấp hơn nhưng ghi dữ liệu sai vẫn phải **fail**.

### 10.2. Baseline-relative và absolute guardrails

Hai dạng điều kiện nên kết hợp:

- **Absolute threshold:** canary phải nằm trong SLO sản phẩm.
- **Relative threshold:** canary không xấu hơn stable quá ngưỡng được thống nhất khi so cùng loại traffic.

Ví dụ minh họa:

```text
Absolute:
  availability >= SLO target
  p99 latency <= business limit

Relative:
  canary 5xx rate not materially worse than stable
  canary p95/p99 within agreed regression budget
  CPU/transaction and memory within capacity budget

Critical:
  no data corruption, irreversible writes,
  unauthorized access, or severe crash
```

Không đặt một threshold giả định làm tiêu chuẩn chung. Nên chọn số liệu cụ thể từ baseline, risk appetite và SLO hiện có.

### 10.3. Định nghĩa denominator đúng

Ví dụ metric availability:

```text
success_ratio =
  successful_business_transactions /
  eligible_business_transactions
```

Tùy sản phẩm, HTTP 2xx chưa chắc là thành công (ví dụ HTTP 200 nhưng giao dịch bị từ chối do backend error). Ngược lại, 4xx từ invalid client requests không nhất thiết là lỗi của ứng dụng; nhưng tăng bất thường ở canary có thể phản ánh validation behavior khác.

Phải xác định request nào được tính trong error budget trước khi đo.

## 11. Can​​ary comparison không chỉ là so hai đường biểu đồ

### 11.1. Số liệu phải có cùng đơn vị phân tích

Nếu stable nhận nhiều traffic bulk/report requests còn canary nhận nhiều GET nhẹ, average latency của canary thấp hơn không chứng minh runtime mới nhanh hơn.

Có thể nhóm theo:

- Endpoint/route.
- HTTP method.
- Tenant size hoặc cohort class.
- Request payload size buckets.
- Region/zone.
- HTTP status/error category.
- Cold/warm pod state.
- JVM/agent version.

Nhưng phân nhóm quá chi tiết có thể tạo metric cardinality bùng nổ. Không gắn raw user ID, email hoặc request ID lên labels có cardinality cao hoặc dữ liệu nhạy cảm.

### 11.2. Cỡ mẫu và độ tin cậy

p99 là chỉ số nhạy khi số request nhỏ. Nếu canary chỉ nhận vài chục request trong một window, percentile có thể dao động mạnh hoặc không có ý nghĩa.

Khi so sánh:

1. Ghi sample count từng version.
2. Xác định confidence/statistical method phù hợp.
3. Tránh gọi “PASS” khi số liệu chưa đủ.
4. Không lựa chọn tùy tiện đoạn thời gian đẹp nhất.
5. Phân biệt p99 sample-based với histogram-based estimation.
6. Tính đến delayed metrics và high-cardinality sampling.

Có thể dùng sequential testing hoặc cơ chế canary analysis chuyên biệt, nhưng cần quản lý false positives/false negatives. Không có một ngưỡng p-value hay thời gian quan sát duy nhất phù hợp mọi request rate.

### 11.3. So sánh theo concurrent stable baseline

Một ứng dụng có traffic biến động theo giờ: so canary lúc 02:00 với stable hôm trước 14:00 thường không công bằng.

Nếu hai version nhận traffic cùng thời điểm, so sánh sẽ có giá trị hơn, nhưng vẫn phải kiểm soát cohort skew và resource placement.

### 11.4. Không che lỗi với retries

Nếu canary ném 500 rồi gateway retry sang stable và trả 200, end-user metric có thể trông bình thường trong khi canary đang lỗi. Theo dõi cả:

- First-attempt error rate.
- Retry attempts theo backend version.
- Final client-visible outcome.
- Duplicate writes/idempotency.
- Extra latency do retry.

Một bản canary yêu cầu quá nhiều retries không nên được mở rộng chỉ vì final success rate đạt.

## 12. Gắn nhãn version và JDK trong telemetry

### 12.1. Mỗi request cần biết đã chạy ở version nào

Một cách thiết kế:

```text
service=order-api
release_track=stable | canary
app_version=4.8.1
image_digest=sha256:...
java_runtime=17 | 21
region=...
route=/orders/{id}
```

Thông tin version nên đi vào metrics, traces và logs theo dạng chuẩn của hệ observability. Không sử dụng giá trị raw path chứa ID người dùng làm metric label.

### 12.2. Tránh nhãn gây cardinality quá cao

Những labels thường có thể kiểm soát:

- `service`, `deployment_track`.
- `jdk_major`.
- `region`, `cluster`, `route_template`.
- `response_code_class`.
- `build_revision` nếu số lượng version hoạt động được giới hạn.

Không dùng raw user/tenant IDs ở toàn bộ request counters. Nếu cần phân tích một tenant cụ thể, dùng traces/logs với policy dữ liệu phù hợp thay vì Prometheus label vô hạn.

### 12.3. Logs và trace correlation

Khi có lỗi trong canary, cần trả lời:

- Request đã được route tới phiên bản nào?
- JVM process đang chạy JDK nào?
- Exception xuất hiện tại bước nào?
- Một retry có chuyển qua stable không?
- Downstream nào làm lỗi?
- Có side effect nào đã commit?
- Error có tương quan với class loading/GC/TLS hay agent không?

Trace/log IDs giúp liên kết các nguồn, nhưng không phải tất cả thông tin đều nên được ghi công khai.

## 13. Ví dụ truy vấn metrics (PromQL minh họa)

Giả sử ứng dụng có counter:

```text
http_server_requests_total{
  service="order-api",
  release_track="stable|canary",
  status_code="200|500|..."
}
```

Tên metric và labels là **giả định**, phải thay theo instrumentation thật.

### 13.1. Request rate theo version

```promql
sum by (release_track) (
  rate(http_server_requests_total{service="order-api"}[5m])
)
```

### 13.2. 5xx rate theo version

```promql
sum by (release_track) (
  rate(
    http_server_requests_total{
      service="order-api",
      status_code=~"5.."
    }[5m]
  )
)
/
clamp_min(
  sum by (release_track) (
    rate(http_server_requests_total{service="order-api"}[5m])
  ),
  0.000001
)
```

Đây là tỷ lệ 5xx, không tự động bao gồm timeout ở gateway, application-level failures hoặc retries. Cần thêm metric riêng cho các trường hợp đó.

### 13.3. p95/p99 nếu có histogram

Giả sử exporter cung cấp `http_server_request_duration_seconds_bucket`:

```promql
histogram_quantile(
  0.99,
  sum by (le, release_track) (
    rate(
      http_server_request_duration_seconds_bucket{
        service="order-api"
      }[5m]
    )
  )
)
```

Histogram quantile là **ước lượng** theo bucket boundaries và metric conventions; không giống tính p99 trực tiếp từ raw request samples. Nếu service dùng native histograms hoặc metric schema khác, truy vấn phải thay tương ứng.

### 13.4. Đừng để “no traffic” thành pass

Nếu canary không có traffic, request error rate có thể không hiện ra hoặc có mẫu số gần zero. Không nên gán mặc định 0% error và kết luận pass. Gate cần minimum traffic/exposure và xác minh phân bố theo version.

## 14. JVM-specific metrics cho JDK canary

### 14.1. Startup và readiness

- Process start timestamp.
- JVM initialization/ready time.
- Application readiness transition.
- Startup errors và restart count.
- Pod scheduling/image pull time nếu phân tích end-to-end.
- Time from ready to SLO-compliant throughput.

Readiness không có nghĩa JIT đã warm up; một pod có thể ready trước khi hot methods được compile hoặc connection pools được khởi tạo đầy đủ.

### 14.2. JIT và code cache

Có thể quan sát:

- CPU tiêu thụ bởi compiler threads trong chẩn đoán.
- Compilation activity hoặc queue qua JFR/jcmd khi phù hợp.
- Code cache usage/warnings.
- Warm-up latency và throughput trend.
- Deoptimization/recompilation nếu có hypothesis.

Không cần bật verbose compilation logs cho mọi canary pod trên production. Ưu tiên telemetry với overhead chấp nhận được; khi có vấn đề mới bật diagnostics có giới hạn.

### 14.3. GC và allocation

Cần theo dõi:

- GC pause time và frequency.
- Heap occupancy before/after GC.
- Allocation rate.
- Old-generation/full collections nếu collector có khái niệm tương ứng.
- Native memory/RSS.
- CPU usage và throttling.

Khi nâng JDK, default GC hoặc ergonomics có thể khác giữa release/configuration. So sánh phải ghi rõ flags và heap/CPU limits. Một p99 spike trùng GC chưa đủ chứng minh JIT regress.

### 14.4. Classloading và reflection

Canary cần metrics/logs cho:

- `ClassNotFoundException` và `NoClassDefFoundError`.
- `UnsupportedClassVersionError`.
- `InaccessibleObjectException`.
- `NoSuchMethodError`/`IllegalAccessError`.
- ServiceLoader/provider lookup failures.
- Agent/instrumentation errors.

Một số lỗi chỉ xảy ra khi route hoặc plugin hiếm được kích hoạt; cần chạy phù hợp trong canary coverage.

### 14.5. JDK security và I/O

Theo dõi bất thường của:

- TLS handshake và certificate verification.
- HTTP client connection failures.
- DNS resolution.
- Filesystem encoding/locale.
- Cryptographic provider.
- Native library loading.
- Database driver validation.

Đừng chỉ nhìn 5xx server nếu outbound client lỗi được ứng dụng nuốt và biến thành empty data hoặc retry vô hạn.

## 15. Warm-up và cold pod: một thách thức riêng

### 15.1. Canary nhỏ có thể luôn ở trạng thái “không đủ nóng”

Một canary nhận rất ít request có thể ít cơ hội làm nóng các hot paths so với stable. Điều này có thể dẫn đến:

- Nhiều interpreted/C1 execution trong khoảng đo.
- Cold caches và class initialization.
- Delayed connection pool growth.
- Lower steady throughput vì không đủ load.
- Per-request latency cao hơn baseline dù khi full traffic có thể khác.

Nếu muốn so steady-state performance, cần đo sau khi canary đủ warm-up **theo metrics và workload**, không chỉ sau một số phút cố định.

### 15.2. Warm-up không phải gửi một GET /health

Health endpoint thường không kích hoạt:

- Business serializer/validator.
- JPA/SQL queries.
- TLS client handshakes.
- Native compression/calls.
- Complex DTO mapping.
- Error paths.
- Large payload handling.

Nếu sử dụng warm-up traffic tổng hợp, cần mô phỏng critical paths và bảo đảm không gây side effects production. Synthetic traffic phải có label để không làm sai số liệu user SLO.

### 15.3. Đo cold và warm riêng

Có thể chia phase:

```text
Deploy canary pods
       |
       v
Readiness / startup metrics
       |
       v
Initial routed traffic
       |
       v
Warm-up observation
       |
       v
Steady observation
       |
       v
Traffic increase / phase shift
```

Nếu chỉ loại bỏ cold window khỏi báo cáo, nhóm sẽ bỏ lỡ rủi ro autoscaling. Nếu chỉ đo cold window, nhóm có thể đánh giá không công bằng long-running throughput.

### 15.4. Autoscaling canary có thể tạo cold pods liên tục

Khi tăng weight, HPA có thể tạo thêm pods. Mỗi pod mới có JIT/caches riêng, dẫn tới một đợt warm-up khác. Vì vậy gate sau traffic increase phải tính tới:

- New pod count.
- Pod age.
- Warm vs cold pod share.
- JDK startup behavior.
- CPU/memory headroom.
- HPA stabilization và target utilization.

Không chỉ xét global average của deployment.

## 16. Cơ sở dữ liệu và shared-state compatibility khi hai bản cùng chạy

### 16.1. Canary thường cùng dùng state với stable

Hai bản có thể đồng thời đọc/ghi:

- Cùng relational database.
- Redis/cache keys.
- Kafka topics/consumer groups.
- Shared object storage.
- Session store.
- Message payloads và schema registry.
- Feature flags và configuration service.

Nếu canary ghi định dạng mới mà stable không hiểu, **ngừng routing tới canary không khôi phục dữ liệu đã ghi**.

### 16.2. Expand-contract migration

Với schema thay đổi, một chiến lược phổ biến:

1. **Expand:** bổ sung schema/fields theo cách bản cũ vẫn hoạt động.
2. **Dual-compatible:** cả stable/canary hiểu dữ liệu cần thiết.
3. **Migrate:** backfill/transform theo kế hoạch có kiểm chứng.
4. **Switch:** tăng traffic sau khi contract đạt.
5. **Contract:** chỉ xóa cấu trúc cũ khi không còn consumer cũ và rollback policy cho phép.

Ví dụ thêm cột nullable có thể ít rủi ro hơn đổi kiểu/xóa cột ngay, nhưng chi tiết phụ thuộc database, ORM và contract.

### 16.3. Serialization thay đổi dù business code ít đổi

Nâng JDK hoặc framework có thể ảnh hưởng:

- Default charset và encoding khi không chỉ định.
- Java serialization nếu class/metadata thay đổi.
- Jackson/JSON date format khi dependency đổi.
- XML/JAXB binding và namespace.
- Locale/timezone data.
- Cache value type hoặc binary format.
- JDK provider selection trong cryptography.

Cần test **forward/backward compatibility** khi hai version cùng tiêu thụ dữ liệu. Nếu rollback yêu cầu bản cũ đọc được dữ liệu do bản mới ghi, phải đưa đó thành release gate.

### 16.4. ID generation, sequence và ordering

Khi hai bản cùng ghi database, cần đảm bảo không tạo trùng ID hoặc mâu thuẫn ordering. Nếu thay đổi service logic, ORM hoặc transaction strategy cùng JDK, rủi ro cao hơn nhiều.

Canary chỉ là cách phân phối traffic; nó không tự giải quyết concurrency, schema migration hay idempotency.

## 17. Queue consumers và background jobs không đi qua HTTP gateway

### 17.1. Một điểm dễ bỏ sót

Canary HTTP routing 5% **không** đồng nghĩa queue consumers hoặc scheduled tasks của canary chỉ xử lý 5% công việc. Nếu cả stable và canary đều tham gia cùng consumer group, phân phối messages phụ thuộc broker partition assignment và concurrency, không phải HTTPRoute weights.

Có thể xảy ra:

- Canary nhận một partition có traffic cực lớn.
- Canary xử lý nhiều messages nhạy cảm hơn stable.
- Một cron job chạy trên cả hai version và gửi duplicate notifications.
- Leader-election lock bị cấu hình sai, tạo hai active schedulers.
- Một message schema mới làm stable consumer fail.

### 17.2. Thiết kế canary cho asynchronous work riêng

Các lựa chọn, tùy hệ thống:

- Chọn một tập partitions/queues rõ ràng.
- Dùng cohort routing ở producer theo key với contract tương thích.
- Chạy canary consumer trong group/test topic riêng khi cần cách ly.
- Giữ scheduler disabled trên canary ban đầu.
- Dùng leader election an toàn và test failover.
- Giảm concurrency có kiểm soát và quan sát lag/DLQ.
- Chạy synthetic events có thể tái tạo/rollback.

Không tự thêm consumer group cho production topic nếu việc đó khiến mọi message bị xử lý lần hai; cần hiểu semantics của broker.

### 17.3. Metrics cần cho async canary

- Processed/successful events theo version.
- Failed/retried events.
- Consumer lag và rebalance count.
- Dead-letter count.
- Processing latency theo event type.
- Duplicate side effects/idempotency violations.
- Checkpoint/offset correctness.
- Graceful shutdown và in-flight message handling.

Không chốt rollout 100% chỉ dựa trên HTTP metrics khi ứng dụng còn xử lý queue hoặc cron.

## 18. Sticky sessions, WebSockets và long-lived connections

### 18.1. Request-level split có thể phá session behavior

Nếu user request đầu vào canary, request tiếp theo vào stable trong khi session format khác nhau, có thể gặp:

- Authentication/session invalidation.
- Cache state không tương thích.
- CSRF token hoặc cookie behavior khác.
- Inconsistent feature state.
- Duplicate workflow hoặc lost updates.

Routing theo session/user có thể phù hợp hơn request split đối với stateful workloads, nhưng làm cohort và rollback phức tạp hơn.

### 18.2. WebSocket/gRPC streaming

Một connection sống nhiều giờ có thể giữ ở một backend dù traffic weight đã đổi. Đặt canary weight về 0 không tự ngắt các connections đang tồn tại; khi rollback cần chính sách:

- Drain.
- Graceful shutdown.
- Connection lifetime cap.
- Reconnection behavior.
- Streaming state checkpoint.
- Đảm bảo không mất message khi chuyển phiên bản.

Một canary có ít connections nhưng mỗi connection mang nhiều messages không được đánh giá chỉ bằng connection count.

### 18.3. Session compatibility là yêu cầu release

Nếu hai JDK versions vẫn chạy cùng app artifact, session compatibility có thể ít thay đổi hơn khi đồng thời nâng framework. Nhưng vẫn cần test vì serialization, security provider, container server/session store có thể khác.

Không giả định rollback canary an toàn nếu user đã nhận state mới không đọc được bởi stable.

## 19. Canary phân tích lỗi dữ liệu mà HTTP status không phát hiện

### 19.1. “200 OK” không phải lúc nào cũng đúng nghiệp vụ

Một bản mới có thể trả HTTP 200 nhưng:

- Số tiền bị làm tròn sai.
- Date/time format bị lệch timezone.
- Tiếng Việt bị sai encoding.
- JSON property biến mất.
- XML namespace sai.
- Record được ghi hai lần.
- Authorization cho phép một hành động không hợp lệ.
- Cache key bị thay khiến dữ liệu sai tenant.

Canary cần domain-specific correctness checks, không chỉ exceptions.

### 19.2. So sánh output theo contract

Nếu hệ thống có đường đọc hoặc tính toán thuần, có thể so response stable/canary với test fixtures. Cần xác định những trường được phép khác nhau: timestamp, random IDs, order of unordered collections, headers hoặc tracing info.

Một cách an toàn hơn với tác vụ có side effects là kiểm thử qua staging/test accounts hoặc workflow có rollback domain rõ ràng, không gửi cùng giao dịch thanh toán hai lần để “so kết quả”.

### 19.3. Shadow traffic chỉ dùng khi có cách ly

Nếu sao chép request để đánh giá bản mới:

- Request shadow không được ghi production DB một lần nữa.
- Không gửi email/SMS/payment/notification thật.
- Không lộ dữ liệu cá nhân ngoài phạm vi được phép.
- Downstream calls cần sandbox/mocks hoặc read-only policy.
- Không đưa shadow responses đến người dùng.
- Không làm sai audit, rate limits hoặc chống gian lận.

Nếu không đảm bảo được điều kiện này, **không dùng mirroring cho những nghiệp vụ có side effects**.

## 20. Health checks và rollback readiness

### 20.1. Startup, readiness và liveness có ý nghĩa khác nhau

- **Startup probe:** cho ứng dụng có thời gian khởi động mà không bị liveness giết quá sớm, khi môi trường hỗ trợ.
- **Readiness probe:** báo backend có thể tiếp nhận traffic theo contract.
- **Liveness probe:** phát hiện tình trạng tiến trình cần được restart theo chính sách.

Nếu liveness quá nghiêm trong lúc JIT/class initialization hoặc GC startup, canary có thể restart liên tục. Nếu readiness quá dễ dãi, request thật đến trước khi service sẵn sàng xử lý.

### 20.2. Không biến readiness thành benchmark JIT toàn diện

Readiness không nên chờ mọi method được biên dịch C2 hoặc chạy mọi business transaction. Điều đó có thể làm rollout không ổn định hoặc gây side effects.

Thay vào đó:

- Readiness đảm bảo thành phần tối thiểu để nhận traffic.
- Traffic ramp kiểm soát tải ban đầu.
- Warm-up observation đánh giá cold performance.
- SLO guardrails giám sát trải nghiệm thực.

### 20.3. Một canary pod unhealthy không thể pass

Gate phải kiểm tra pod readiness/restarts và request count, chứ không chỉ stable aggregate. Nếu canary đã crash và traffic tự động quay về stable, overall success rate vẫn có thể đẹp; đó là **canary fail**.

## 21. Sự khác nhau giữa rollback traffic và rollback deployment

### 21.1. Rollback traffic

Đưa canary weight về 0 hoặc loại cohort khỏi routing:

```text
Before:
  stable 90%
  canary 10%

After abort:
  stable 100%
  canary 0%
```

Đây là bước quan trọng để hạn chế request mới, nhưng một số connections/streams/in-flight requests có thể tiếp tục. Gateway/controller có propagation delay, nên cần xác minh **actual request rate tới canary đã giảm**.

### 21.2. Rollback deployment

Sau khi routing ổn định:

- Drain canary connections.
- Stop background consumers/schedulers.
- Đảm bảo in-flight transactions hoàn tất hoặc được retry an toàn.
- Scale down hoặc revert workload.
- Giữ logs/JFR/crash dumps trước khi xóa pod nếu policy cho phép.
- Xác minh stable còn đủ capacity.
- Ghi incident và đóng hoặc giữ release ở trạng thái blocked.

Không xóa vội toàn bộ logs của canary sau khi rollback; điều đó làm mất bằng chứng root cause.

### 21.3. Rollback dữ liệu

Nếu canary ghi dữ liệu không tương thích, rollback có thể cần:

- Ngừng writers.
- Chạy compensating transaction được thiết kế trước.
- Restore từ backup nếu được chấp thuận và phù hợp RPO.
- Data repair/migration plan.
- Requeue/replay events an toàn.
- Isolate affected tenant/cohort.

Đây là công việc có thể rủi ro cao. Vì thế cần kiểm tra data compatibility trước canary và thiết kế các thay đổi **expand-contract** khi có thể.

### 21.4. Rollback phải được diễn tập

Một runbook chưa được thử không đủ. Trước khi mở rộng traffic, nên kiểm tra trong staging hoặc môi trường kiểm soát:

- Command/API rollback thực tế.
- Auth/permissions.
- Thời gian propagation/detection.
- Cách drain workload.
- Database/session compatibility.
- Thông báo on-call.
- Cách trở lại stable success metrics.

Tránh dựa vào thao tác thủ công phức tạp chỉ một người biết.

## 22. Quy tắc dừng khẩn cấp (abort) trước khi bắt đầu

### 22.1. Các trigger có thể cần dừng ngay

Ví dụ mang tính định hướng:

- Bất kỳ bằng chứng corruption hoặc data leakage.
- Security/authz bypass.
- Critical payment/billing side effect sai.
- Canary crash loop hoặc thiếu ready endpoints.
- Tăng lỗi nghiêm trọng so với stable.
- p99 vượt SLO theo ngưỡng đã được thống nhất.
- Queue lag/DLQ tăng nguy hiểm.
- Native JVM crash/agent incompatibility.
- Resource usage đe dọa shared downstream.
- Không còn quan sát được canary hoặc rollback control bị lỗi.

Điều kiện critical có thể yêu cầu abort ngay không chờ sample lớn.

### 22.2. Phân biệt STOP, HOLD và PROMOTE

| Quyết định | Tình huống | Hành động |
|---|---|---|
| **STOP / ABORT** | Vi phạm guardrail quan trọng | Dừng traffic tăng, rollback routing và xử lý side effects |
| **HOLD** | Dữ liệu ít, metrics delay hoặc uncertainty | Giữ mức thấp, bổ sung quan sát nếu an toàn |
| **PROMOTE** | Đủ exposure, tests và guardrails đạt | Nâng traffic theo stage đã duyệt |
| **PAUSE FOR INVESTIGATION** | Một metric lệch nhưng chưa rõ nguồn | Không tăng tải, cô lập bằng logs/traces |
| **COMPLETE** | Đạt full rollout và post-deploy verification | Chốt release evidence và đóng canary |

Không coi “không phát hiện lỗi” tương đương “đã chứng minh pass” khi telemetry hoặc coverage thiếu.

### 22.3. Guardrail không cần đợi release manager online mới hoạt động

Một số tổ chức dùng automation để dừng tiến trình rollout khi metrics vượt threshold. Nhưng cần:

- Quy tắc đã được review.
- Dữ liệu metrics đáng tin cậy.
- Quyền rollback hạn chế và audit.
- Không tự động thực hiện data rollback nguy hiểm.
- Có manual override và escalation policy.
- Không che lỗi bằng tự động retry rollout vô hạn.

Automation là lớp hỗ trợ, không thay trách nhiệm vận hành.

## 23. Ví dụ kế hoạch rollout có gate rõ ràng

Một runbook minh họa:

| Giai đoạn | Traffic | Yêu cầu trước khi lên bước tiếp |
|---|---|---|
| **P0 — Deploy** | 0% external | Image/JDK/health/observability và rollback sẵn sàng |
| **P1 — Internal** | Cohort nội bộ | Synthetic critical paths, no critical exceptions |
| **P2 — Small** | 1–5% | Minimum exposure, error/latency guardrails, warm-up |
| **P3 — Medium** | 10–25% | Business flows, GC/CPU/memory, async jobs đủ dữ liệu |
| **P4 — Large** | 50% | Soak, capacity, state compatibility, incident-free window |
| **P5 — Full** | 100% | SLO và correctness tiếp tục đạt |
| **P6 — Observe** | 100% + monitoring | Xác minh tail effects, giữ rollback window theo policy |

Các tỷ lệ là ví dụ để thảo luận, không phải mặc định an toàn. Với low-volume jobs, một cohort rõ ràng có thể có giá trị hơn một tỷ lệ %. Với một hệ thống chịu trách nhiệm tài chính hoặc y tế, guardrails và validation cần nghiêm ngặt hơn.

### 23.1. Thời gian của mỗi gate

Không có “mỗi stage 5 phút là đủ” chung. Phải phụ thuộc:

- Traffic volume.
- Latency SLO/window.
- Thời điểm scheduled jobs chạy.
- JIT/cold startup.
- Database/queue behavior.
- Các luồng hiếm nhưng quan trọng.
- Khoảng thời gian cần để leak/resource regressions xuất hiện.

Nếu service có batch chạy mỗi đêm, một canary chỉ hoạt động buổi trưa chưa kiểm chứng batch path đó.

### 23.2. Mở rộng theo vùng hoặc tenant

Nếu triển khai nhiều khu vực, có thể chọn:

```text
Region A -> small cohort -> larger cohort -> full
Region B -> small cohort -> larger cohort -> full
Region C -> small cohort -> larger cohort -> full
```

Cần ghi rõ rằng hoàn thành Region A không tự chứng minh Region B có tương đồng về CA trust, native libs, locale, availability zone hay networking.

## 24. Release artifact và JDK provenance

### 24.1. Những thứ phải version hóa

Canary và stable cần có metadata:

```yaml
release:
  application_version: "4.8.1"
  commit: "<git-sha>"
  artifact_sha256: "<artifact-checksum>"
  container_image_digest: "<image-digest>"
  java:
    vendor: "<vendor>"
    version: "<major-update-build>"
  framework_version: "<version>"
  runtime_dependencies_manifest: "<reference>"
  gc: "<collector>"
  jvm_flags_reference: "<config-reference>"
  deployment_track: "canary"
```

Không lưu secret trong release manifest. Các trường chứa placeholder cần được điền từ pipeline thật.

### 24.2. Container image tag không đủ

Một tag như `app:jdk21` có thể bị overwrite. Nếu muốn kết luận canary chạy đúng binary, phải lưu immutable digest hoặc provenance tương đương.

Nếu dùng cùng application JAR trong hai images có JDK khác nhau, có thể xác minh application JAR SHA-256 giống nhau, đồng thời ghi khác biệt runtime layer.

### 24.3. Java runtime thật phải được quan sát

Một số container có nhiều JVM installations hoặc launcher scripts thay `JAVA_HOME`. Chỉ thấy CI build dùng Java 21 không chứng minh production canary pod dùng Java 21.

Hãy lấy runtime metadata từ process/startup logs hoặc ứng dụng telemetry được xác thực; tránh expose sensitive system properties vào public endpoint.

## 25. CI/CD pipeline cho canary migration

Một pipeline tổng quát:

```text
Commit / approved release
            |
            v
Build + unit/integration tests
            |
            v
JDK compatibility + artifact verification
            |
            v
Image signing / provenance / security policy
            |
            v
Staging contract + performance smoke
            |
            v
Deploy canary workloads (0% external)
            |
            v
Preflight health + telemetry + rollback test
            |
            v
Controlled traffic stage
            |
            v
Automated + human review (if policy)
            |
         +--+--+
         |     |
       FAIL   PASS
         |     |
         v     v
       ABORT  PROMOTE
         |     |
         v     v
     Incident   Next stage / full rollout
```

Pipeline cần đóng băng artifact giữa các bước. Nếu job “deploy canary” tự rebuild source với dependency versions mới, evidence từ staging có thể không còn áp dụng.

### 25.1. Không cho pipeline bypass security/quality gates

Canary là **bước sau** kiểm thử và kiểm soát artifact, không phải lý do bỏ:

- Unit/integration tests.
- Dependency vulnerability checks.
- Artifact provenance.
- Secret scanning.
- API schema compatibility.
- Database migration review.
- Required approvals.

### 25.2. Các biến số cần đồng bộ

- JDK build/runtime vendor.
- Container image/OS.
- JVM flags.
- Framework/server dependencies.
- Feature flags.
- Schema version.
- Traffic routing policies.
- Monitoring labels.
- Synthetic traffic exclusions.

Nếu canary và stable dùng các backend cấu hình khác nhau, báo cáo phải nói rõ.

## 26. Vấn đề JVM nổi bật trong quá trình canary

### 26.1. JEP 403 và reflection

Khi nâng lên các JDK có strong encapsulation nghiêm ngặt hơn, framework hoặc agent cũ có thể gặp `InaccessibleObjectException` ở code path hiếm. Canary cần log exception types và kích hoạt đủ các workflow có reflection.

`--add-opens` có thể là workaround có phạm vi nếu được phê duyệt, nhưng không nên bật hàng loạt chỉ để giữ canary xanh. Phải ghi owner và kế hoạch nâng thư viện.

### 26.2. JEP 320 và Java EE APIs đã loại bỏ

Nâng từ JDK 8 sang JDK 11+ có thể làm mất các module JAXB/JAX-WS/Activation từng có trong JDK. Một REST endpoint có thể pass trong khi export XML fail vì `javax.xml.bind.JAXBContext` chỉ được nạp động.

Trước canary, nên test các workflow XML/SOAP, hoặc cung cấp runtime dependencies phù hợp trong artifact đã được kiểm chứng. Nếu canary pass do không có XML requests, kết quả vẫn chưa bao phủ rủi ro này.

### 26.3. JEP 400 và charset mặc định

Khi chuyển đến JDK 18+, default charset UTF-8 có thể làm behavior khác với môi trường cũ cho các API phụ thuộc default charset. Một canary xử lý file legacy cần test byte-level data và kiểm tra ký tự có dấu, đặc biệt các luồng import/export.

Không chỉ so HTTP status khi output file bị lỗi encoding.

### 26.4. Bytecode level và runtime graph

Nếu một dependency class được compile Java 21 nhưng canary runtime vẫn là Java 17, có thể gặp `UnsupportedClassVersionError` tại đường code tải class đó. Nếu mục tiêu là nâng runtime lên Java 21, xác nhận image thật đã có Java 21 và classpath không trộn JAR không phù hợp.

Một ứng dụng compile target 17 vẫn có thể sử dụng JDK 21 runtime; không cần bắt buộc nâng bytecode target lên 21 cùng đợt.

### 26.5. Java agents và native code

Một Java agent hoặc JNI library chạy tốt trên baseline JDK không bảo đảm hỗ trợ target JDK. Canary cần kiểm tra agent startup, bytecode instrumentation, native library version, architecture và resource cleanup.

Trường hợp native crash có thể khiến cả JVM thoát; route rollback sẽ không cứu những transactions đã bị side effect trước crash.

### 26.6. Virtual threads và concurrency

Nếu migration JDK 17 → 21 đồng thời chuyển executor sang virtual threads, đó là một thay đổi concurrency architecture riêng. Có thể làm tăng requests đồng thời và tạo downstream saturation, dù JDK runtime cải thiện throughput.

Nên thử JDK upgrade không đổi thread model trước khi đánh giá tác động của virtual threads, nếu sản phẩm cho phép. Nếu buộc gộp, phải ghi rõ canary đang đo **full-stack change**, không chỉ JDK delta.

## 27. Cô lập kết quả khi stable/canary dùng chung downstream

### 27.1. Database có thể là điểm nghẽn chung

Nếu canary chiếm thêm connection pool capacity hoặc gửi queries khác, nó có thể ảnh hưởng stable. Khi đó stable không còn là nhóm control hoàn toàn độc lập.

Cần theo dõi:

- DB active/idle connections.
- Query latency và lock waits.
- Transaction aborts/deadlocks.
- Slow queries.
- Saturation của shared connection pool/DB.
- Cache hit rate và eviction.
- Rate limits bên đối tác.

Nếu cả stable và canary cùng xấu đi, không tự kết luận canary vô tội; nó có thể gây shared-backend overload.

### 27.2. So sánh resource cost công bằng

Một canary nhận ít tải hơn có thể có CPU/request cao do startup, fixed overhead hoặc chưa warm JIT; khi nhận tải lớn hơn, bottleneck khác lại xuất hiện.

Khi so sánh:

- Dùng cùng hardware/container budget nếu có thể.
- Xem per-pod CPU và request rate.
- Tách cold/warm pods.
- So p95/p99 theo request mix.
- Kiểm tra autoscaling và downstream capacity.

Không thay đổi CPU limits chỉ cho canary nếu mục tiêu là cô lập runtime JDK, trừ khi được ghi nhận là thay đổi cấu hình phải kiểm chứng.

### 27.3. Kiểm tra cascade failure

Một canary lỗi nhiều có thể tăng retries, từ đó làm database/queue hoặc stable version quá tải. Cần giới hạn retry budgets, concurrency và circuit-breaker behavior để blast radius thực sự được khống chế.

Canary không an toàn nếu 1% user traffic có thể tạo 100% downstream saturation qua retry storm.

## 28. Hướng xử lý khi metrics xấu nhưng root cause chưa rõ

### 28.1. Không vội sửa bằng tăng heap

Nếu p99 canary cao:

1. Kiểm tra sample count, traffic mix và version labels.
2. Kiểm tra cold/warm pod age.
3. Kiểm tra CPU quota/throttling.
4. Kiểm tra GC pauses, allocation và RSS.
5. Kiểm tra JIT/warm-up khi có dấu hiệu.
6. Kiểm tra downstream latency/retries.
7. Kiểm tra Java agents/observability overhead.
8. Xem application logs/traces của các request chậm.
9. Đối chiếu stable cùng thời điểm.
10. Quyết định HOLD, ABORT hoặc thử cấu hình trong staging.

Tăng heap hoặc đổi GC đồng thời khi đang đánh giá JDK có thể làm mất khả năng xác định nguyên nhân. Nếu cần thử một mitigation, lưu thành một phiên bản/config canary mới với baseline rõ.

### 28.2. Can​​ary error spike ngay khi chuyển traffic

Một số khả năng:

- Readiness không đảm bảo application thực sự sẵn sàng.
- TLS/DB pool chưa khởi tạo.
- Classloading/lazy initialization.
- JDK flags hoặc agent lỗi.
- Memory/CPU resources không đủ.
- Routing/gateway misconfiguration.
- Dữ liệu canary cohort có đặc điểm khác stable.

Trước khi gọi đó là “JDK regression”, xác minh metrics và logs. Tuy nhiên, khi vi phạm guardrail quan trọng, cần **dừng/rollback trước rồi điều tra**, không giữ traffic thật chỉ để lấy thêm log.

### 28.3. Lỗi chỉ sau nhiều giờ

Có thể liên quan:

- Native memory leaks.
- File descriptors/connections leaks.
- GC/memory pressure.
- Background job.
- TLS certificate rotation.
- Stale classloader/plugin behavior.
- Queue replay.
- Cache eviction/TTL.
- Scheduled job code path.

Vì vậy mỗi stage cần thời gian quan sát theo loại workload, không chỉ vài lần smoke requests.

## 29. Quy trình xử lý sự cố canary

### Bước 1 — Kích hoạt abort theo guardrail

Ngừng tăng traffic, đưa routing về stable theo runbook nếu vượt ngưỡng critical.

### Bước 2 — Xác minh hiệu lực

Kiểm tra backend request rate: canary có còn nhận request mới không? Long-lived sessions/streams có cần drain không?

### Bước 3 — Bảo vệ downstream và dữ liệu

Ngừng/bảo vệ queue consumers, schedulers, writes hoặc external side effects nếu cần, theo kế hoạch đã duyệt.

### Bước 4 — Giữ bằng chứng

Lưu image digest, JDK version, logs, traces, metrics windows, crash reports và pod events theo policy. Tránh để GC/rollout xóa hết evidence.

### Bước 5 — Phân loại lỗi

- JDK API removal.
- Reflection/JPMS.
- Bytecode/dependency mismatch.
- Native/agent.
- TLS/charset/timezone.
- JIT/GC/resource/performance.
- Routing/readiness.
- Data/session/queue compatibility.
- External backend/shared resource.

### Bước 6 — Quyết định rollback tiếp, fix-forward hay tạm dừng

Nếu chỉ là routing config và fix đã được xác minh, có thể lập canary mới. Nếu data corruption hoặc security impact, cần incident process đầy đủ, không tự retry release.

### Bước 7 — Chốt incident và guardrail mới

Ghi nguyên nhân, mức traffic/time affected, request/tenant scope, blast radius, data repair và regression test cần bổ sung.

## 30. Ví dụ xuyên suốt: canary JDK 17 → JDK 21 cho REST service

Giả sử một dịch vụ:

```text
Service: order-api
Current runtime: JDK 17
Target runtime: JDK 21
App JAR: same release revision, same SHA-256
Framework: version verified to support JDK 21
Deployment: Kubernetes, two workloads
Traffic: REST requests + queue consumers
Shared backend: PostgreSQL + Redis
SLO: agreed p99 / error budget
```

### 30.1. Trước rollout

Nhóm:

1. Chạy artifact trên JDK 21 ở staging.
2. Test business flows, TLS, JDBC, serialization, security.
3. Xác nhận container JDK 21 process/version.
4. Chốt stable/canary routing và telemetry labels.
5. Kiểm tra database compatibility hai chiều.
6. Quyết định queue consumers chưa bật ở canary ban đầu.
7. Diễn tập rollback từ small cohort.
8. Xác định error/latency/business guardrails.

### 30.2. Giai đoạn P0/P1

Triển khai canary 0% external, đo startup, probe, image/JDK provenance. Chạy test cohort nội bộ để kích hoạt critical business paths và xác minh logs/traces đúng nhãn.

Nếu có `InaccessibleObjectException` trong serializer khi tạo DTO cụ thể, dừng ngay và xử lý thư viện; chưa có lý do mở 5% user traffic.

### 30.3. Giai đoạn small traffic

Chuyển một cohort nhỏ, kiểm tra request distribution thực và đo cold/warm riêng.

Giả sử canary có p99 cao trong những phút đầu nhưng sau warm-up nằm trong ngưỡng, trong khi stable luôn ít biến động. Nhóm chưa nên tuyên bố pass chỉ dựa vào steady numbers; phải kiểm tra autoscaling/cold-pod SLO. Có thể giữ mức traffic, điều chỉnh ramp hoặc bổ sung capacity theo quy trình sau khi xác định nguyên nhân.

### 30.4. Giai đoạn medium

Tăng traffic khi đủ sample và guardrails đạt. Kiểm tra:

- Per-route errors/latency.
- CPU/request, GC, JIT warm-up.
- DB pool/Redis impact.
- Restart/ready pods.
- Session affinity.
- Security/TLS and charset.
- Business outcome metrics.

Nếu mở queue consumer canary, phải có kế hoạch routing/partitioning riêng, không dùng HTTP traffic weight làm proxy.

### 30.5. Giai đoạn full và quan sát

Khi traffic đạt 100%:

- Không xóa stable rollback capacity ngay nếu chính sách yêu cầu cửa sổ quan sát.
- Đo lại SLO ở full-load behavior, vì 50% có thể chưa bộc lộ capacity bottleneck.
- Theo dõi ít nhất một chu kỳ vận hành đủ để quan sát những scheduled jobs liên quan.
- Xác nhận dữ liệu ghi mới có thể được đọc bởi rollback version nếu policy cần.
- Chốt evidence và owner cho workarounds còn tồn tại.

Kết luận hợp lệ là: **bản phát hành cụ thể trên JDK 21 đã đạt guardrails với traffic và môi trường quan sát được**, không phải mọi ứng dụng Java 17 đều an toàn trên Java 21.

## 31. Ví dụ thứ hai: JDK 8 → JDK 21 và code path hiếm

Một ứng dụng cũ dùng JAXB từ JDK 8, nhưng chức năng export XML chỉ chiếm một lượng nhỏ yêu cầu. Dự án chạy app trên JDK 21, health và các endpoint JSON đều pass. Canary 1% chỉ nhận JSON traffic nên không phát hiện thiếu JAXB API/runtime.

Sau khi full rollout, người dùng đầu tiên gọi export XML và gặp:

```text
java.lang.NoClassDefFoundError:
  javax/xml/bind/JAXBContext
```

Bài học ở đây:

1. Không dùng traffic share nhỏ làm bằng chứng coverage toàn bộ.
2. Tính năng hiếm nhưng quan trọng phải có synthetic/contract tests trước canary.
3. Trước khi nâng JDK 8 lên 11+, kiểm tra modules JAXB/JAX-WS/Activation đã rời JDK.
4. Bổ sung API/provider runtime đúng thế hệ khi cần, với artifact mới được kiểm chứng.
5. Ghi rõ rằng sửa runtime dependency tạo ra deployment bundle khác; không tiếp tục gọi là binary unchanged.
6. Tạo regression test thực thi export XML trên JDK đích.

Canary chỉ phát hiện lỗi khi test hoặc traffic thực sự kích hoạt đường lỗi.

## 32. Khi nào không nên mở rộng traffic?

Một tập tiêu chí **NO-GO** mẫu:

- Không biết chính xác binary/JDK đang chạy trong canary.
- Không đo được request rate hoặc error rate riêng của canary.
- Stable/canary không cùng data contract, rollback có thể làm hỏng state.
- Canary pod không ready, restart loop hoặc không nhận traffic thật.
- Chưa có phương án dừng queue consumers/scheduler.
- Có lỗi critical ở security, data integrity hoặc payment.
- Framework/vendor target JDK không được hỗ trợ theo policy bắt buộc.
- Guardrails chưa đạt hoặc có metrics không đáng tin.
- Không đủ mẫu/không đủ code path coverage cho bước tăng tải.
- Không có owner trực rollback trong rollout window.
- Downstream services đã gần saturation và canary có thể tạo retry storm.
- Artifact đã đổi ngoài kế hoạch nên kết quả baseline không còn so sánh được.

Khi thiếu bằng chứng, **HOLD** để kiểm tra bổ sung là kết quả hợp lệ. Khi có critical violation, **ABORT** theo runbook là hành động an toàn hơn việc “chờ đủ sample”.

## 33. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
|---|---|
| “Một pod mới trong 20 pod nghĩa 5% traffic” | Replica ratio không bảo đảm request share |
| “RollingUpdate tự động là canary an toàn” | Cần giữ stage, routing và analysis riêng |
| “Không lỗi trong 5 phút nghĩa pass” | Có thể không đủ sample hoặc chưa chạm tới code path |
| “Health 200 nghĩa JDK compatibility đã đủ” | Health không kiểm chứng TLS/JAXB/JPA/native/rare flows |
| “Canary p99 thấp hơn stable nghĩa JDK mới nhanh hơn” | Cần cân bằng traffic mix, cold state và hardware |
| “Đóng canary weight về 0 sẽ hoàn tác mọi thứ” | DB/queue/session side effects vẫn tồn tại |
| “5% HTTP traffic nghĩa 5% queue work” | Queue assignment và schedulers độc lập |
| “JDK mới cùng JAR nên dữ liệu không thay đổi” | Charset/timezone/security/defaults có thể khác |
| “Canary nhỏ không thể gây outage lớn” | Retry storm hoặc shared DB saturation vẫn có thể lan rộng |
| “p99 từ rất ít requests là bằng chứng mạnh” | Percentile thiếu mẫu dễ biến động |
| “Gateway trả 200 nên canary không có lỗi” | Retry sang stable có thể che backend failure |
| “Shadow POST an toàn vì response bị bỏ qua” | Side effects vẫn có thể xảy ra nếu không cách ly |
| “Readiness=true tức JIT đã warm” | Readiness và steady performance khác nhau |
| “Một region pass tức mọi region pass” | Native/CA/CPU/traffic có thể khác |
| “Rollback chỉ cần giữ app image cũ” | Còn dữ liệu, config, schema, agent, runtime và sessions |
| “Cứ tăng heap để sửa p99 khi JDK đổi” | Cần cô lập JIT/GC/CPU/downstream trước |
| “SLO pass là được, không cần business correctness” | Ghi sai dữ liệu không thể được chấp nhận |
| “Canary thay thế integration tests” | Các đường hiếm có thể không được traffic kích hoạt |
| “Một release có thể promote khi không có dữ liệu canary” | Không có exposure không phải PASS |

## 34. Checklist trước, trong và sau canary

### Trước khi mở traffic

- [ ] Đã xác nhận runtime upgrade goal, phạm vi và cách tách biến số.
- [ ] Đã chốt application artifact checksum/image digest.
- [ ] Đã xác minh JDK vendor/version/build trong process thật.
- [ ] Đã kiểm tra framework, dependency, native library và agent support matrix.
- [ ] Đã chạy unit/integration/contract tests trên JDK đích.
- [ ] Đã kiểm tra class-file, JPMS/reflection, TLS, charset và serialization.
- [ ] Đã xác minh health/startup/readiness/liveness probes phù hợp.
- [ ] Đã thiết lập stable/canary workloads và routing.
- [ ] Đã kiểm tra quyền rollback và diễn tập trong môi trường cho phép.
- [ ] Đã định nghĩa SLI/SLO, stop/hold/promote criteria và minimum exposure.
- [ ] Đã xác nhận database/cache/session/queue compatibility.
- [ ] Đã xử lý side effects, scheduled jobs và consumer-group semantics.
- [ ] Đã có version labels và observability dashboards.
- [ ] Đã có người chịu trách nhiệm rollout, on-call và escalation.
- [ ] Đã kiểm tra secret, logging/privacy và security policy.

### Khi đang thử traffic

- [ ] Đã xác minh actual canary request share, không chỉ routing weight.
- [ ] Đã xác nhận canary ready pods có traffic và capacity.
- [ ] Đã quan sát request mix/cohort, retry và backend attempts.
- [ ] Đã phân biệt cold/warm canary metrics.
- [ ] Đã theo dõi errors, p95/p99, throughput và business outcome.
- [ ] Đã quan sát CPU, GC, memory, container throttling và restarts.
- [ ] Đã kiểm tra TLS, native, agent, class loading và reflection exceptions.
- [ ] Đã theo dõi queue lag/DLQ/schedulers nếu có.
- [ ] Đã xem shared backend load và retry amplification.
- [ ] Đã đợi đủ sample, observation window và metrics ingestion.
- [ ] Đã ghi từng thay đổi weight/cohort với timestamp.
- [ ] Đã dừng tăng traffic khi có guardrail uncertainty.
- [ ] Đã abort đúng lúc nếu có critical incident.

### Sau promote hoặc abort

- [ ] Đã xác minh full deployment thực sự nhận traffic như mong đợi.
- [ ] Đã quan sát post-promotion SLO và batch/soak behavior.
- [ ] Đã xác nhận old/new state compatibility trong rollback window.
- [ ] Đã giữ rollback artifact/runtime/image và runbook theo policy.
- [ ] Nếu abort, đã ngừng traffic, drain connections và xử lý async jobs.
- [ ] Đã đánh giá data repair/side effects nếu xảy ra lỗi.
- [ ] Đã lưu logs, traces, metrics và crash evidence phù hợp.
- [ ] Đã ghi incident/root cause và follow-up regression tests.
- [ ] Đã xử lý workarounds, owner và technical debt còn tồn tại.
- [ ] Đã cập nhật support matrix và release documentation.

## 35. Hồ sơ bàn giao cho đội phát hành/vận hành

Một đợt canary nên tạo được bộ hồ sơ như sau:

1. **Change scope:** JDK-only, JDK + container, hay JDK + framework/dependency.
2. **Artifact provenance:** SHA-256 hoặc immutable image digest, git revision và BOM/lockfile.
3. **Runtime matrix:** JDK vendor/build, JVM flags, GC, agents, OS/architecture.
4. **Traffic plan:** routing/cohort strategy, tỷ lệ từng stage, endpoint eligibility.
5. **Coverage:** business flows/feature flags/async paths đã được thử.
6. **Shared-state plan:** schema/session/queue compatibility và side-effect ownership.
7. **Baseline:** SLO, traffic mix và resource metrics của stable.
8. **Canary telemetry:** version-labeled dashboards, logs/traces, real traffic share.
9. **Decision gates:** thresholds, minimum exposure, observation windows, owners.
10. **Stage evidence:** thời gian, sample count, metrics, approval/decision.
11. **Operational incidents:** crash, retries, data anomalies và phương án giải quyết.
12. **Rollback proof:** route switch, connection drain, async pause và data recovery.
13. **Post-rollout verification:** full-load SLO, autoscaling, cold starts và scheduled jobs.
14. **Residual risks:** những code paths chưa bao phủ, framework support gaps và workarounds.
15. **Next steps:** dọn stable resources theo policy, nâng toolchain/source/dependencies nếu cần.

### Mẫu decision log ngắn

```yaml
canary:
  service: "order-api"
  release_id: "<release>"
  stable:
    app_artifact: "<sha256>"
    jdk: "<vendor-17-build>"
  candidate:
    app_artifact: "<sha256>"
    jdk: "<vendor-21-build>"
  routing:
    method: "weighted-gateway"
    desired_weight_percent: 5
    measured_share_percent: "<observed>"
  analysis:
    window: "<start-end>"
    request_samples: "<count>"
    required_exposure_met: false
    functional_contracts: "PASS"
    error_guardrail: "PASS"
    latency_guardrail: "INCONCLUSIVE"
    data_compatibility: "PASS"
    async_workload_coverage: "PENDING"
  decision:
    status: "HOLD"
    reason: "Insufficient observation for async workflow"
    owner: "<release-owner>"
  rollback:
    route_procedure: "<runbook-reference>"
    artifact_reference: "<immutable-image-digest>"
```

Các trường mẫu không phải số liệu production. Nếu `required_exposure_met=false` hoặc guardrails quan trọng còn `INCONCLUSIVE/PENDING`, không được tự đổi `status` thành `PROMOTE` chỉ vì phần kiểm tra còn lại có chữ PASS.

**Kết luận:** Canary release giúp giảm rủi ro khi nâng Java/JDK bằng cách giới hạn một phần lưu lượng thật đến bản mới, đo riêng stable/canary và mở rộng theo các cổng quyết định có bằng chứng. Một canary tốt không chỉ là vài pod JDK mới: nó đòi hỏi **artifact provenance, định tuyến kiểm soát được, đủ code path coverage, quan sát cold/warm JVM, SLO và correctness guardrails, tương thích dữ liệu khi hai bản cùng chạy, quản lý async workloads và rollback thực sự đã được chuẩn bị**. Chỉ tăng lên 100% khi các tiêu chí đó đạt, và tiếp tục giám sát sau full rollout vì tải hoàn chỉnh có thể bộc lộ những vấn đề mà một canary nhỏ không thể thấy.
