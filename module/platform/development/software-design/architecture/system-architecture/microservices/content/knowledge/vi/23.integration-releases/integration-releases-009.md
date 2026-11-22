# Tự động hóa phát hành và tiêu chí cho phép tiếp tục

Trong kiến trúc microservices, một thay đổi nhỏ có thể đi qua nhiều bước: build một service, kiểm tra hợp đồng API với các service khác, tạo container image, cập nhật cấu hình và hạ tầng, triển khai thử nghiệm, quan sát lưu lượng thực tế rồi mới mở rộng phát hành. Nếu mỗi bước chỉ dựa vào nhận định thủ công “có vẻ ổn”, hệ thống khó duy trì tốc độ thay đổi mà vẫn kiểm soát rủi ro.

**Tự động hóa phát hành** là việc biến quy trình đưa phiên bản mới tới môi trường sử dụng thành chuỗi hành động có thể lặp lại, có bằng chứng và có điều kiện dừng. **Tiêu chí cho phép tiếp tục** (promotion gate / go-no-go criteria) là bộ điều kiện quyết định một phiên bản có được chuyển sang giai đoạn tiếp theo hay phải tạm dừng, sửa lỗi hoặc quay lại phiên bản an toàn.

Điểm quan trọng: tự động hóa không đồng nghĩa với luôn triển khai bất chấp tín hiệu rủi ro. Một pipeline tốt có thể quyết định **tiếp tục, tạm giữ, từ chối hoặc rollback** theo dữ liệu và chính sách được định nghĩa trước.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt continuous integration, continuous delivery, continuous deployment, deployment và release.
2. Phân rã pipeline phát hành microservice thành các giai đoạn có đầu vào, đầu ra và điều kiện chuyển tiếp.
3. Thiết kế kiểm tra tự động cho mã nguồn, artifact, hợp đồng API, tương thích dữ liệu, cấu hình và vận hành.
4. Định nghĩa promotion gate gồm metric, ngưỡng, cửa sổ thời gian, cỡ mẫu, nguồn dữ liệu và hành động khi kết quả không xác định.
5. Áp dụng progressive delivery như canary, rolling update hoặc blue-green theo mức rủi ro.
6. Phân biệt rollback code, ngừng traffic, tắt feature flag và phục hồi dữ liệu.
7. Đề xuất cơ chế audit, phê duyệt có chọn lọc, quyền can thiệp và thử nghiệm quy trình.
8. Đọc telemetry để xác minh “phiên bản mới hoạt động tốt” trên lưu lượng thật, thay vì chỉ dựa vào việc container đã chạy.

## 2. Phân biệt build, deployment, release và promotion

Các thuật ngữ thường bị dùng thay thế cho nhau:

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Continuous Integration (CI)** | Tích hợp thay đổi liên tục, build và kiểm thử nhanh để phát hiện lỗi sớm. | Pull request chạy unit test, static check và contract test. |
| **Continuous Delivery** | Mọi thay đổi đạt tiêu chí đều ở trạng thái sẵn sàng phát hành; bước sản xuất có thể cần quyết định chủ động. | Artifact đã được kiểm chứng và có thể promote từ staging. |
| **Continuous Deployment** | Thay đổi vượt toàn bộ gates có thể tự động triển khai tới production. | Merge thành công kích hoạt rollout production mà không cần duyệt từng lần. |
| **Build** | Tạo artifact có thể triển khai. | Image của `order-service` với digest cụ thể. |
| **Deploy** | Đưa artifact vào một môi trường hoặc tập instance. | Chạy image mới trên 10% pod của production. |
| **Release** | Làm hành vi mới có thể sử dụng bởi người dùng/consumer. | Mở feature flag cho 5% người dùng. |
| **Promotion** | Cho phép cùng một phiên bản tiến sang môi trường hoặc mức traffic tiếp theo. | Canary 5% → 25% → 100%. |
| **Rollback / abort** | Ngăn phiên bản có vấn đề tiếp tục nhận traffic và trở về trạng thái phục vụ an toàn. | Đưa route về stable ReplicaSet hoặc chuyển traffic về blue. |

Có thể **deploy mà chưa release**: một service đã chạy image mới nhưng feature flag vẫn tắt. Cũng có thể **release mà không deploy mới**: mở một tính năng có sẵn trong image đang chạy. Phân biệt hai hành động giúp giảm phạm vi thay đổi tại từng bước.

Trong microservices, mỗi service thường có vòng đời triển khai độc lập; tuy nhiên, khả năng độc lập phải dựa trên **hợp đồng tương thích và dữ liệu chia sẻ phù hợp**, không chỉ dựa vào việc có pipeline CI riêng.

## 3. Mô hình đường đi phát hành

Một quy trình tiêu biểu:

~~~text
Developer commit / Merge
          |
          v
  [CI: lint, unit, static checks]
          |
          v
 [Build artifact + SBOM/provenance]
          |
          v
 [Verify artifact + security policy]
          |
          v
 [Integration & contract tests]
          |
          v
 [Deploy vào test/staging]
          |
          v
 [Smoke, e2e, migration checks]
          |
          v
 [Production canary 5%]
          |
          v
 [Gate: health + metrics + sample]
          |
          +------ Fail ------> Stop / Roll back / Investigate
          |                        ^
          +------ Unknown ----> Hold (không promote)
          |
          v
 [Production canary 25%]
          |
          v
 [Gate: health + metrics + dependencies]
          |
          v
 [Production rollout 100%]
          |
          v
 [Post-rollout observation + evidence]
~~~

Mỗi nút gate cần có **người sở hữu**, tiêu chí cụ thể và kết quả được ghi nhận. Dấu tích xanh ở job cuối cùng không đủ: ví dụ job “deploy successful” chỉ có thể xác nhận Kubernetes đã chấp nhận cấu hình hoặc pod đạt trạng thái Ready; nó chưa chứng minh tỷ lệ đặt hàng thành công không bị giảm.

### 3.1. Bốn câu hỏi của mọi gate

1. **Đang bảo vệ điều gì?** Ví dụ: không triển khai image có lỗ hổng nghiêm trọng chưa được chấp nhận; không phá hợp đồng API.
2. **Dùng bằng chứng nào?** Ví dụ: kết quả test có phiên bản, telemetry production cho canary và stable.
3. **Đạt nghĩa là gì?** Ngưỡng, cửa sổ quan sát, mẫu tối thiểu, tỷ lệ thất bại cho phép.
4. **Không đạt hoặc thiếu dữ liệu thì sao?** Fail, hold, rollback, tạo incident hoặc yêu cầu người có thẩm quyền xử lý.

Gates phải phản ánh rủi ro thực: gate nhanh, rẻ chạy sớm; gate đắt hoặc phụ thuộc production chạy sau nhưng trước khi tăng ảnh hưởng.

## 4. Những nguyên tắc thiết kế pipeline

**Xây một lần, triển khai nhiều lần.** Cùng một artifact đã kiểm chứng được đưa từ test sang staging rồi production. Tránh rebuild độc lập cho từng môi trường vì dependency hoặc compiler inputs có thể thay đổi.

**Dùng artifact bất biến.** Pin container image theo digest (ví dụ `image@sha256:<digest>`), không chỉ dùng tag `latest`. Cần biết chính xác commit, cấu hình build và dependency tạo ra artifact.

**Đầu ra có thể truy vết.** Mỗi release có release ID, commit SHA, image digest, kiểm thử đã chạy, chính sách gate, người hoặc hệ thống phê duyệt, trạng thái triển khai và thời gian quan sát.

**Tách bí mật khỏi artifact.** Không nhúng credential vào image hoặc CI log. Lấy secrets qua cơ chế quản lý bí mật đúng môi trường và kiểm soát quyền truy cập.

**Hạn chế song song thay đổi trên một đích.** Hai rollout cùng đổi một service hoặc cùng thực thi database migration có thể làm mất ý nghĩa kết quả canary; dùng cơ chế khóa/concurrency phù hợp.

**Idempotent và có thể tiếp tục an toàn.** Chạy lại job sau failure không được tạo một phiên bản thứ hai với cùng tên nhưng bytes khác, đẩy trùng migration hoặc mất lịch sử quyết định.

**Tách build pipeline với release orchestration.** Build xác định “artifact có đủ điều kiện”, còn rollout xác định “phiên bản này có hoạt động an toàn trong môi trường đích”.

**Luôn có đường dừng.** Pipeline cần hỗ trợ pause, abort, rollback, khóa phát hành khi incident và quyền can thiệp rõ ràng.

## 5. Cổng kiểm tra trước khi tạo artifact

Những kiểm tra đầu tiên nên có phản hồi nhanh và lỗi rõ:

- **Source quality:** formatter hoặc lint theo quy ước, compile, static analysis thiết yếu.
- **Unit tests:** quy tắc nghiệp vụ, mapping DTO, xử lý lỗi và các điều kiện biên.
- **Build reproducibility:** khóa phiên bản dependency và plugin; kiểm tra artifact được build từ commit dự định.
- **Secret scanning:** ngăn commit credential/token và tập tin cấu hình chứa secret.
- **Dependency/security scanning:** đánh giá thành phần phụ thuộc, license và lỗ hổng theo mức chính sách.
- **Container configuration:** image chạy bằng quyền hạn cần thiết, expose cổng thích hợp, có liveness/readiness probes theo thiết kế.
- **Infrastructure validation:** lint/validate manifest, policy-as-code, schema của cấu hình và quyền truy cập.

Không phải cảnh báo của mọi công cụ đều phải chặn phát hành vô điều kiện. Chính sách cần xác định mức nghiêm trọng, khả năng khai thác, bối cảnh chạy và cơ chế **ngoại lệ có hạn sử dụng, người duyệt và bằng chứng**. Nhưng ngoại lệ không nên trở thành cách bỏ qua gate mặc định mỗi khi gấp.

### Artifact và nguồn gốc

Một release record tối thiểu:

~~~yaml
release:
  service: order-service
  sourceCommit: "8cf13b0"       # Ví dụ minh họa
  artifactDigest: "sha256:<verified-digest>"
  buildPipelineRun: "ci-1842"
  manifestRevision: "deploy-723"
  contractTestRun: "contract-912"
  policyVersion: "release-gates-v3"
  targetEnvironment: "production"
~~~

Giá trị trên là dữ liệu ví dụ. Trong hệ thống thực, digest phải là digest thật được registry xác nhận; không dùng chuỗi minh họa làm đầu vào deploy. Với supply-chain quan trọng, có thể ký artifact, sinh SBOM, xác thực provenance/attestation và chỉ cho deployment controller chạy artifact từ nguồn được tin tưởng.

## 6. Cổng kiểm tra tích hợp giữa microservices

Vấn đề khó của microservices là mỗi service có thể được triển khai ở phiên bản khác nhau. Test “service A chạy được” không đủ để biết A tương thích với B, C và các consumer chưa nâng cấp.

### 6.1. Contract tests

Ví dụ:

~~~text
Checkout v14 --HTTP--> Pricing v7
Checkout v14 --gRPC--> Inventory v9
Checkout v14 --events--> Analytics v4
~~~

Gate cần kiểm tra những hợp đồng quan trọng:

- URL, phương thức, status và response schema cho REST.
- Protobuf field numbers, kiểu dữ liệu và phương án versioning cho gRPC.
- Topic, event name, schema và semantics cho Kafka/RabbitMQ.
- Kiểu lỗi, timeout, idempotency và thay đổi bắt buộc/không bắt buộc.
- Consumer chưa nâng cấp có vẫn đọc được message/response mới không?

**Consumer-driven contract tests** có thể phát hiện một provider vừa thay đổi field mà consumer đang phụ thuộc, dù unit tests của provider vẫn xanh. Cần version hóa contract và liên hệ với artifact/commit thực được triển khai.

### 6.2. Tương thích ngược

Thay đổi an toàn thường theo hướng mở rộng trước:

~~~text
Bước 1: Provider thêm field tùy chọn hoặc endpoint mới.
Bước 2: Consumer cũ và mới cùng hoạt động với provider mới.
Bước 3: Consumer chuyển sang cách dùng mới.
Bước 4: Quan sát adoption và ngừng sử dụng đường cũ.
Bước 5: Loại bỏ đường cũ sau khi được chứng minh không còn consumer phụ thuộc.
~~~

Thay đổi xóa field, thay semantics, đổi kiểu hoặc tăng yêu cầu bắt buộc có thể phá các instance cũ đang chạy song song. Gate cần kiểm tra **các tổ hợp phiên bản có thể tồn tại trong rollout**, không chỉ tổ hợp “mới nhất với mới nhất”.

### 6.3. Integration tests trên môi trường gần thực tế

Một bộ test ngắn nhưng có giá trị:

1. API tạo đơn gọi sang Inventory bằng protocol và auth thật của môi trường test.
2. Event được publish và consumer nhận đúng schema; lỗi consumer không gây mất message.
3. Timeout, retry và duplicate request không tạo tác dụng phụ lặp khi không được phép.
4. Giao dịch qua database được commit/rollback đúng khi dependency lỗi.
5. Cơ chế health check có thể phát hiện service không sẵn sàng dù process còn chạy.

Kết quả phải gắn với đúng phiên bản artifact và hạ tầng. Nếu test môi trường bị lỗi do dependency test không sẵn sàng, hãy ghi “không xác định” và xử lý riêng; đừng tự động coi test xanh khi bị skip.

## 7. Database migration là gate riêng

Database thường được nhiều phiên bản ứng dụng sử dụng trong giai đoạn rolling update. Đổi schema trước hoặc sau khi đổi code có thể gây lỗi dù mỗi phiên bản riêng lẻ hoạt động.

Phương pháp **expand–migrate–contract**:

~~~text
Schema hiện tại
    |
    v
EXPAND: thêm bảng/cột/index tương thích
    |
    v
DEPLOY: phiên bản mới đọc được schema cũ/mới
    |
    v
MIGRATE: backfill dữ liệu có kiểm soát
    |
    v
SWITCH: chuyển logic đọc/ghi, quan sát kết quả
    |
    v
CONTRACT: chỉ bỏ cột/đường cũ sau khi không còn consumer
~~~

Gate liên quan:

- Migration được version hóa, đã test với dữ liệu và kích thước đại diện.
- Kết quả preflight cho thấy hệ thống có đủ quyền, dung lượng và thời gian triển khai.
- Migration dài được chia batch hoặc thực thi ngoài thời gian chặn response theo thiết kế.
- Có kế hoạch phục hồi dữ liệu và xác nhận backup khi rủi ro yêu cầu.
- Old/new app có thể cùng chạy trên schema trong giai đoạn quá độ.
- Step xóa dữ liệu hoặc cột cũ có điều kiện kiểm soát riêng, không tự động chạy trong cùng job canary khi chưa đủ bằng chứng.

**Rollback image không đảo ngược migration dữ liệu.** Nếu phiên bản mới đã ghi dữ liệu bằng định dạng khác, đưa pod về image cũ có thể tiếp tục gây lỗi. Release record phải xác định những bước nào đảo được, bước nào cần roll-forward, compensation hoặc kế hoạch khôi phục có kiểm soát.

## 8. Triển khai không đồng nghĩa với sẵn sàng phục vụ

Trước khi chuyển traffic, bộ điều phối phải xác minh:

- Pod/process mới đã chạy và không restart liên tục.
- **Readiness** chứng minh instance nhận traffic được; liveness chỉ nên chỉ ra khi nào cần khởi động lại.
- Startup probe hoặc timeout khởi động phù hợp với ứng dụng cần warm-up.
- Service discovery và route trỏ đúng workload mới.
- Dependencies thiết yếu như database, broker, cache hoặc config service đang trong trạng thái chấp nhận được.
- Có đủ replica healthy để giữ khả năng phục vụ khi chuyển traffic.
- Các bước khởi tạo dữ liệu, warm-up cache hoặc migration cần thiết đã hoàn tất.

Ví dụ Kubernetes manifest *minh họa* một phần readiness:

~~~yaml
containers:
  - name: order-service
    image: registry.example.invalid/order-service@sha256:<digest>
    ports:
      - containerPort: 8080
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: 8080
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 3
    startupProbe:
      httpGet:
        path: /actuator/health/liveness
        port: 8080
      periodSeconds: 5
      failureThreshold: 30
~~~

Đây là ví dụ khái niệm: cú pháp image digest phải được thay bằng giá trị thật, endpoint readiness/liveness cần được cấu hình và kiểm tra theo Spring Boot Actuator/ứng dụng cụ thể. Probe phải phản ánh sẵn sàng thật, nhưng không nên biến mọi sự cố downstream ngắn hạn thành vòng restart không cần thiết.

## 9. Các chiến lược progressive delivery

Không nhất thiết đưa 100% người dùng tới phiên bản mới ngay khi build xong.

| Chiến lược | Cách hoạt động | Đặc điểm cần chú ý |
|---|---|---|
| **Rolling update** | Thay dần instance cũ bằng instance mới. | Dễ tích hợp orchestrator; một phần traffic gặp phiên bản mới trong quá trình chuyển. |
| **Blue–green** | Chuẩn bị hai tập môi trường/instance, sau đó chuyển route. | Có khả năng chuyển traffic nhanh; cần chú ý session, state, DB schema và chi phí đôi môi trường. |
| **Canary** | Cho một phần traffic đi qua phiên bản mới, đo rồi tăng dần. | Quan sát rủi ro trên tập nhỏ; cần đủ số request và mẫu đại diện. |
| **Feature flag rollout** | Giữ cùng artifact nhưng chỉ bật hành vi cho nhóm người dùng nhất định. | Tách triển khai và mở tính năng; quản lý cờ tồn đọng, cohort và thứ tự side effect. |
| **Shadow traffic** | Gửi bản sao request để quan sát, thường không dùng kết quả từ shadow. | Không được tạo tác dụng phụ gây trùng, lộ dữ liệu hoặc tăng tải ngoài kiểm soát. |

Một ví dụ canary production:

~~~text
Stable v1: 100%, Canary v2: 0%
             |
             v
Stable 95%, Canary 5%   -- Quan sát cửa sổ 10 phút
             |
             v
Stable 75%, Canary 25%  -- Quan sát cửa sổ 15 phút
             |
             v
Stable 50%, Canary 50%  -- Quan sát cửa sổ 15 phút
             |
             v
Stable 0%, Canary 100%  -- Theo dõi sau rollout
~~~

Phần trăm và khoảng thời gian chỉ là **ví dụ chính sách**, phải chọn dựa trên traffic, mức độ rủi ro, thời gian phát hiện lỗi và năng lực rollback. Một service chỉ có vài request mỗi phút có thể cần cửa sổ dài hơn hoặc chiến lược khác.

## 10. Một promotion gate phải có cấu trúc xác định

Định nghĩa “canary ổn” là quá mơ hồ. Một chính sách tự động tối thiểu nên có:

| Thành phần | Nội dung cần ghi |
|---|---|
| **Target** | Service, phiên bản, môi trường, cohort, rollout step và phần traffic. |
| **Signal** | Availability/success rate, lỗi HTTP/gRPC, p95/p99 latency, saturation, business KPI, sức khỏe dependency. |
| **Baseline** | So sánh với stable, SLO hoặc lịch sử cùng loại request. |
| **Threshold** | Ngưỡng tuyệt đối và/hoặc chênh lệch chấp nhận được so với baseline. |
| **Observation window** | Khoảng thời gian liên tục cần thu thập, ví dụ 10–15 phút. |
| **Minimum sample** | Số request đủ cho quyết định; có thể theo endpoint/case quan trọng. |
| **Data freshness** | Dữ liệu telemetry phải mới; collector mất dữ liệu không được đánh dấu tốt. |
| **Failure action** | Hold, abort, rollback, tắt feature flag, mở incident. |
| **Unknown action** | Khi sample thiếu hoặc dữ liệu mơ hồ: giữ rollout, điều tra hoặc yêu cầu phê duyệt. |
| **Owner/evidence** | Chính sách có version, người chịu trách nhiệm, query/kết quả và mã deployment. |

**Tiêu chí kỹ thuật chỉ là một phần.** Đối với thanh toán, tạo đơn hoặc xác thực, business KPI như tỷ lệ giao dịch được ghi nhận/hoàn tất là tín hiệu quan trọng; container vẫn Ready và 5xx thấp không chứng minh nghiệp vụ đang đúng.

### 10.1. Tín hiệu vàng và tín hiệu nghiệp vụ

Các metric thường được dùng:

- **Latency:** p95 hoặc p99 theo route quan trọng, so sánh với stable và SLO.
- **Errors:** 5xx, gRPC failures, timeout, circuit breaker opens, retry exhaustion.
- **Traffic:** tổng số request, traffic share thực tế, phân phối nhóm request.
- **Saturation:** CPU, memory, pod restarts, thread/connection pool, queue lag, pending jobs.
- **Business correctness:** số đơn hoàn tất, giao dịch thanh toán thành công, events bị lỗi, sai lệch dữ liệu hoặc duplicate side effects.
- **User experience:** tỷ lệ client gặp lỗi, tăng thời gian chờ hay fallback bất thường.

Không gate trên một metric duy nhất. Nếu response rất nhanh nhưng trả lỗi cho phần lớn người dùng, latency tốt vẫn là kết quả tệ. Nếu canary có error rate thấp nhưng số request quá ít, chưa có đủ bằng chứng.

## 11. Ví dụ chính sách promotion 5% → 25%

Giả sử `order-service` có hai phiên bản:

- Stable `v1` phục vụ 95% request.
- Canary `v2` phục vụ 5% request.
- Tổng traffic trong cửa sổ 10 phút: khoảng 20.000 request.
- Traffic canary dự kiến khoảng 1.000 request; traffic thực tế cần đo, không lấy 5% danh nghĩa làm mẫu.

Ví dụ một bộ tiêu chí giả định:

| Điều kiện | Gate tiếp tục | Khi không đạt |
|---|---|---|
| **Sẵn sàng** | Tất cả canary replicas được route đều Ready, không CrashLoop hoặc restart bất thường. | HOLD/ABORT tùy lỗi. |
| **Số mẫu** | Ít nhất 800 requests canary trong cửa sổ. | HOLD, quan sát thêm. |
| **Dữ liệu metric** | Dữ liệu không trễ quá mức cho phép, đủ labels phân biệt canary/stable. | HOLD, sửa telemetry. |
| **Lỗi 5xx** | Canary 5xx ≤ 1% **và** không vượt stable quá 0,5 điểm phần trăm. | ABORT nếu độ tin cậy/khối lượng mẫu phù hợp. |
| **p95 latency** | Canary p95 ≤ 400 ms **và** không cao hơn stable quá 25%. | HOLD hoặc ABORT theo mức lệch và chính sách. |
| **Nghiệp vụ** | Không tăng đáng kể tỷ lệ checkout thất bại; không xuất hiện lỗi tính tiền hoặc sai dữ liệu. | ABORT ngay với lỗi correctness nghiêm trọng. |
| **Rủi ro hạ tầng** | Không có OOM, số connection/queue lag vượt giới hạn hay sự cố cluster liên quan. | HOLD/ABORT. |
| **Sự cố đang mở** | Không có incident cùng phạm vi làm sai lệch phép đo. | HOLD. |

Đây là **giá trị minh họa**, không phải tiêu chuẩn chung cho mọi service. Việc kết luận “tăng đáng kể” cần quy tắc thống kê hoặc chỉ tiêu kinh doanh cụ thể. Khi traffic thấp, phép so sánh tỷ lệ lỗi có thể nhiễu: chỉ vài request lỗi đã làm tỷ lệ biến động mạnh. Kết hợp ngưỡng tuyệt đối, baseline và mức mẫu tối thiểu giúp tránh quyết định thiếu căn cứ, nhưng không loại bỏ mọi sai lầm thống kê.

### Tính đơn giản để hiểu ngưỡng

Giả sử:

~~~text
Stable:  19.000 requests, 57 lỗi 5xx   -> 0,30%
Canary:  1.000 requests, 12 lỗi 5xx    -> 1,20%

Ngưỡng canary tuyệt đối:              1,00%
Ngưỡng chênh lệch so với stable:      +0,50 điểm phần trăm
Thực tế chênh lệch:                    +0,90 điểm phần trăm
~~~

Canary **không đạt** cả hai ngưỡng minh họa. Gate có thể abort nếu dữ liệu hợp lệ, traffic tương đương và chính sách coi sự sai lệch này đủ tin cậy. Ngược lại, nếu canary chỉ nhận 20 requests và không lỗi, không nên kết luận “100% thành công, promote được”: thiếu cỡ mẫu.

**Phân biệt điểm phần trăm với tỷ lệ phần trăm:** từ 0,30% lên 1,20% là tăng **0,90 điểm phần trăm**, tương đương tăng 300% tương đối so với 0,30%. Viết rõ đơn vị trong policy và dashboard để tránh lập trình nhầm ngưỡng.

### Không đánh đồng traffic stable và canary

Canary cần nhận các loại request đại diện. Nếu phiên bản mới chỉ được route tới một vùng ít traffic hoặc nhóm tài khoản không dùng tính năng mới, số liệu tốt chưa chứng minh nó sẽ hoạt động khi mở rộng. Kiểm tra:

- Tỷ lệ các endpoint chủ chốt giữa stable và canary.
- Khu vực, thiết bị, loại khách hàng, thời điểm và quy mô request.
- Có phân bổ traffic theo sticky session gây lệch mẫu không?
- Những đường code quan trọng có được kích hoạt trong cửa sổ không?
- Lỗi từ phụ thuộc chung có ảnh hưởng cả hai cohort hay không?

## 12. Ba trạng thái quyết định: PASS, FAIL, UNKNOWN

Một gate tự động chỉ có hai trạng thái “pass/fail” thường xử lý sai khi telemetry không đầy đủ. Cách biểu diễn tốt hơn:

~~~text
                        +-----------------------------+
                        | Kiểm tra prerequisites       |
                        | build, test, config, health  |
                        +--------------+--------------+
                                       |
                            Không đạt? +----> FAIL -> ABORT
                                       |
                                       v
                        +-----------------------------+
                        | Thu metric trong time window |
                        +--------------+--------------+
                                       |
                            Không đủ dữ liệu?
                                       +----> UNKNOWN -> HOLD
                                       |
                                       v
                        +-----------------------------+
                        | Áp ngưỡng và chính sách      |
                        +--------------+--------------+
                                       |
                        +--------------+--------------+
                        |                             |
                       PASS                          FAIL
                        |                             |
                        v                             v
                    PROMOTE                    ABORT/ROLLBACK
~~~

Ý nghĩa:

- **PASS:** tất cả điều kiện bắt buộc được xác nhận và có đủ bằng chứng; có thể tiến.
- **FAIL:** một hoặc nhiều điều kiện không đạt; dừng, giảm traffic hoặc rollback theo mức độ.
- **UNKNOWN:** telemetry không đến, chưa đủ traffic, query timeout, service chỉ mới khởi động hoặc có incident làm sai lệch phép đo; **không tự động promote**.

Ngoài ba trạng thái của gate, bộ điều phối cần trạng thái rollout như `PENDING`, `RUNNING`, `PAUSED`, `ROLLING_BACK`, `COMPLETED` để tránh kích hoạt lại những hành động không phù hợp.

### Timeout của chính gate

Gate cũng không được đợi mãi. Ví dụ chỉ quan sát tối đa 45 phút để đạt 800 request. Nếu hết 45 phút mà vẫn thiếu mẫu, kết quả là UNKNOWN với lý do `INSUFFICIENT_TRAFFIC` và người sở hữu phải chọn tăng thời gian quan sát, chạy kiểm thử bổ sung hoặc hủy rollout. Không được chuyển thành PASS chỉ vì vượt hạn chờ.

## 13. Chính sách dưới dạng dữ liệu, không dựa vào trí nhớ

Một manifest minh họa (pseudo-YAML, **không phải cú pháp trực tiếp của một công cụ**):

~~~yaml
apiVersion: delivery.example/v1
kind: PromotionPolicy
service: order-service
environment: production

steps:
  - trafficPercent: 5
    observation:
      window: 10m
      maximumWait: 45m
      minCanaryRequests: 800
      maxMetricAge: 2m
    prerequisites:
      minReadyReplicas: 2
      requireContractTests: true
      requireMigrationCompatibility: true
    checks:
      - name: http-5xx
        absoluteMaxPercent: 1.0
        maxDeltaPercentagePointsVsStable: 0.5
      - name: request-p95
        absoluteMaxMillis: 400
        maxRatioVsStable: 1.25
      - name: checkout-correctness
        requirement: NO_CRITICAL_REGRESSION
    onPass: PROMOTE_TO_25_PERCENT
    onFail: ABORT_AND_ROUTE_TO_STABLE
    onUnknown: HOLD_AND_NOTIFY_OWNER

  - trafficPercent: 25
    observation:
      window: 15m
      maximumWait: 60m
      minCanaryRequests: 2500
    onPass: PROMOTE_TO_100_PERCENT
    onFail: ABORT_AND_ROUTE_TO_STABLE
    onUnknown: HOLD_AND_NOTIFY_OWNER
~~~

Trong pipeline thật, chính sách cần ràng buộc với release ID, deployment target, endpoint metric, ngôn ngữ query, thời điểm bắt đầu window và policy version. Bộ điều phối chịu trách nhiệm diễn giải các giá trị trên, không dựa vào tên YAML hư cấu. Có thể triển khai bằng GitHub Actions/GitLab CI/Jenkins phối hợp với Kubernetes controller hoặc hệ thống progressive delivery; bộ công cụ cụ thể cần được chọn theo kiến trúc đang dùng.

### 13.1. Hàm ra quyết định độc lập với orchestrator

Pseudocode:

~~~text
evaluate(rollout, policy, metrics):
    if !rollout.versionMatchesExpected:
        return FAIL("VERSION_MISMATCH")

    if rollout.readinessFailed:
        return FAIL("NOT_READY")

    if metrics.queryUnavailable or metrics.tooOld:
        return UNKNOWN("METRICS_UNAVAILABLE")

    if metrics.canaryRequests < policy.minCanaryRequests:
        return UNKNOWN("INSUFFICIENT_TRAFFIC")

    if metrics.criticalBusinessRegression:
        return FAIL("BUSINESS_CORRECTNESS")

    if metrics.errorRate > policy.errorAbsoluteMax:
        return FAIL("ERROR_RATE")

    if metrics.errorRate - metrics.stableErrorRate >
            policy.maxErrorDelta:
        return FAIL("ERROR_REGRESSION")

    if metrics.latencyP95 > policy.latencyAbsoluteMax:
        return FAIL("LATENCY_SLO")

    if metrics.latencyP95 >
            metrics.stableLatencyP95 * policy.maxLatencyRatio:
        return FAIL("LATENCY_REGRESSION")

    if !metrics.requiredDependenciesHealthy:
        return FAIL("DEPENDENCY_HEALTH")

    return PASS("PROMOTION_ELIGIBLE")
~~~

Hàm trên minh họa logic chứ không thay thế việc xét thống kê, sampling và nhiều nhóm request. Chính sách thật nên so sánh giá trị theo đơn vị rõ ràng, tránh lỗi chia cho 0, kiểm tra canary/stable chạy cùng điều kiện, và ghi toàn bộ bằng chứng của quyết định.

## 14. Đọc metric đúng cách khi gate tự động

Một số lỗi thường xuất hiện khi nối monitoring vào hệ thống ra quyết định.

### 14.1. Không có dữ liệu không đồng nghĩa với giá trị bằng 0

Một query trả về empty series có thể do service chưa có traffic, tên label sai, scrape lỗi hoặc collector ngừng hoạt động. Nếu evaluator ép empty thành `0 errors`, canary trông khỏe mạnh dù hoàn toàn không có tín hiệu. Phải phân biệt:

- Có 0 lỗi trong **N request đã ghi nhận**.
- Không có request nào.
- Có request nhưng hệ thống đo không thu được dữ liệu.
- Dữ liệu chưa cập nhật đủ mới.

### 14.2. Tính tỷ lệ trên đúng mẫu số

Tỷ lệ lỗi HTTP 5xx nên phản ánh:

~~~text
error_rate =
    số request 5xx của canary trong window
    --------------------------------------
    tổng request canary trong cùng window
~~~

Cần thống nhất loại request nào được tính: có loại trừ health probes, scrape endpoints, synthetic traffic, request client-cancel hay không. Không so sánh canary có tính health check với stable không tính.

### 14.3. Theo dõi tail latency thay vì trung bình đơn thuần

Latencies thường có phân phối lệch. Một số request rất chậm có thể ảnh hưởng khách hàng dù p50 không đổi. p95/p99 quan trọng nhưng cần lượng traffic đủ lớn. Với histogram metric, cần cấu hình buckets phù hợp mục tiêu latency; tránh tính phân vị từ histogram quá thô rồi dùng để quyết định sát ngưỡng.

### 14.4. Độ mới và độ toàn vẹn dữ liệu

Gate nên xác nhận:

- Có đúng labels phân biệt version/canary/stable.
- Mốc dữ liệu nằm **sau khi** phiên bản mới sẵn sàng nhận traffic.
- Query không vô tình lấy kết quả cache cũ trước rollout.
- Thu thập còn hoạt động ở cả stable lẫn canary.
- Tỷ lệ telemetry bị drop không tăng bất thường.
- Số request trong metrics phù hợp traffic thực đo của gateway/mesh.

Telemetry là bằng chứng vận hành, nhưng có thể bị sai. Việc kiểm tra “dữ liệu đo đáng tin” phải đứng trước việc diễn giải KPI.

## 15. Health gate, readiness và cảnh báo

Readiness/liveness probes cần có mục đích riêng:

- **Startup probe:** cho phép thời gian khởi động/warm-up mà không restart quá sớm.
- **Readiness probe:** loại instance khỏi luồng traffic nếu chưa thể phục vụ.
- **Liveness probe:** phát hiện tiến trình bị kẹt trong tình huống thực sự cần restart.
- **Application smoke test:** kiểm tra một hành trình đơn giản qua các thành phần thiết yếu sau deploy.
- **Synthetic probe:** chủ động tạo yêu cầu test an toàn để phát hiện lỗi ngay cả khi traffic thật thấp.

Không biến liveness thành kiểm tra phụ thuộc tạm thời rồi tạo restart storm. Readiness thành công không chứng minh hành trình tạo đơn hoặc thanh toán đúng. Gate nên kết hợp health kỹ thuật với success rate, business metrics và monitoring của dependency.

### Dừng rollout khi có incident

Nếu một incident đang ảnh hưởng cùng cluster hoặc dependency, dữ liệu canary có thể bị nhiễu; tuy vậy mở rộng traffic trong lúc đó cũng tăng rủi ro. Chính sách có thể HOLD rollout trong khi incident hoạt động, trừ thay đổi khẩn cấp được phê duyệt theo đường riêng với kiểm soát cụ thể.

## 16. Giữ an toàn khi tự động rollback

Rollback là hành động vận hành thực sự, cần xác định điều gì có thể quay lại và điều gì đã thay đổi không thể đảo ngược.

### 16.1. Rollback có thể làm gì?

- Chuyển traffic từ canary về stable.
- Thu hồi hoặc giảm bản canary mới để tránh tiếp tục nhận request.
- Tắt feature flag để ngừng kích hoạt hành vi lỗi.
- Khôi phục manifest/config version trước nếu đã được quản lý và có thể quay lại an toàn.

### 16.2. Rollback có thể không làm gì?

- Không hoàn tác database schema/data migration một cách tự nhiên.
- Không thu hồi một message đã gửi hoặc email đã gửi.
- Không xóa side effect đã ghi sang payment provider.
- Không khôi phục cache hoặc dữ liệu đã thay đổi nếu thiếu kế hoạch.
- Không đảm bảo client cũ sẽ đọc được dữ liệu do phiên bản mới ghi.

Vì vậy “rollback ready” là gate tiền triển khai: phiên bản cũ phải tương thích với schema hiện tại; schema migration cần expand–contract; mọi side effect quan trọng cần idempotency/compensation. Khi không thể rollback, thiết kế chiến lược roll-forward có điều kiện và cần mức phê duyệt phù hợp.

### 16.3. Xác nhận rollback thành công

Không chỉ chờ job rollback trả exit code 0. Kiểm tra:

1. Routing đã trở lại phiên bản stable như dự kiến.
2. Stable replicas Ready và có đủ capacity cho 100% traffic.
3. Error rate và latency đã trở về trạng thái chấp nhận.
4. Không còn request mới được chuyển tới phiên bản lỗi.
5. Các request đang chạy, message đang xử lý hoặc giao dịch chưa xác định được quản lý theo chính sách.
6. Release record ghi nguyên nhân, timestamp và bằng chứng phục hồi.

## 17. Feature flags và việc mở tính năng

Feature flag giúp tách “đã có mã” khỏi “người dùng đang thấy hành vi mới”. Một rollout có thể:

~~~text
Deploy image v2 cho 100% pods
        |
        v
Flag OFF: hành vi cũ vẫn phục vụ
        |
        v
Flag ON cho nhân viên nội bộ
        |
        v
Flag ON cho 1% -> 10% -> 50% -> 100%
        |
        v
Dọn cờ khi ổn định
~~~

Gate mở flag nên đánh giá **hành vi mới** theo cohort, không chỉ so sánh phiên bản image. Nếu version v2 đã chạy 100% nhưng chỉ 1% request có flag ON, metric theo image version sẽ trộn nhóm dùng tính năng với nhóm không dùng.

Những điều cần cân nhắc:

- Có theo dõi cohort và segment an toàn, không tạo metric labels cardinality cao hay lộ dữ liệu cá nhân.
- Flag quyết định trước side effect nhạy cảm; tắt flag có ngừng được hoạt động lỗi chưa?
- Định nghĩa default nếu dịch vụ feature flag không khả dụng.
- Không dùng flag đơn giản để bỏ qua migration bắt buộc hoặc bảo đảm dữ liệu không tương thích.
- Cờ phải có owner, expiry hoặc lịch dọn sau khi rollout hoàn tất.

## 18. Quản lý thay đổi liên service

Tự động hóa phát hành một microservice có thể độc lập, nhưng những thay đổi tương tác cần điều phối.

Ví dụ một cải tiến ở Order v5 cần Pricing v8:

~~~text
Pricing v7 -> Pricing v8 (thêm field tùy chọn)
                   |
                   v
Contract test: cả Order v4 và v5 đều tương thích
                   |
                   v
Deploy Pricing v8
                   |
                   v
Deploy Order v5
                   |
                   v
Kiểm tra không còn consumers phụ thuộc cũ
~~~

Cần mô hình hóa dependencies theo **khả năng tương thích**, không nhất thiết theo một danh sách “deploy tất cả cùng lúc”. Một service có thể đã sẵn sàng code nhưng chưa được phép promote vì provider chưa đạt phiên bản tương thích, hoặc feature flag của dependency chưa bật.

Các bằng chứng nên gồm:

- Provider/consumer contract matrix cho các phiên bản có thể cùng tồn tại.
- Thứ tự database schema và event schema changes.
- Các backward-compatible adapters đang hoạt động.
- Theo dõi message schema compatibility và retries khi consumer phiên bản cũ vẫn chạy.
- Kế hoạch phục hồi khi chỉ một phần rollout đa service thành công.

Nếu mọi microservice cần phát hành đồng bộ, hệ thống đã tạo coupling về delivery; cân nhắc thay đổi hợp đồng và kiến trúc để cho phép triển khai độc lập hơn.

## 19. Môi trường và cấu hình: promote artifact, kiểm tra config

Cùng image có thể chạy trên staging và production với config khác nhau. Một pipeline phải quản lý:

- Version của deployment manifests hoặc GitOps repository.
- Environment-specific settings: endpoint, resource limits, replica count, timeout, rate limit, feature flags.
- Secrets được cấp qua cơ chế có phân quyền, không đưa vào build logs.
- Network policy, service accounts, quyền database/topic.
- Cấu hình monitoring/alert và scrape/trace exporter trước khi mở traffic.
- Hạn chế các cấu hình mâu thuẫn như timeout thấp hơn response duration kỳ vọng hoặc connection pool quá nhỏ.

Một thay đổi config cũng là thay đổi production và có thể cần gate tương đương đổi code. GitOps có thể dùng trạng thái được khai báo làm nguồn quản lý rollout, nhưng controller “synced” chỉ xác nhận sự khớp cấu hình, không thay thế đo sức khỏe người dùng và business correctness.

## 20. Tự động hóa trong GitHub Actions/GitLab/Jenkins và rollout controller

Thông thường CI system giỏi build/test/artifact, còn deployment controller hoặc progressive delivery tool giỏi quản lý phần trăm traffic và chiến lược rollback.

~~~text
CI System
  ├─ Build and test
  ├─ Produce immutable image + provenance
  ├─ Publish artifacts
  └─ Open deployment change / trigger release
                         |
                         v
                Deployment Controller
                  ├─ Deploy canary
                  ├─ Query monitoring
                  ├─ Evaluate promotion gates
                  ├─ Shift traffic
                  └─ Abort / Rollback / Finish
                         |
                         v
                   Audit/Release Log
~~~

Một workflow dạng pseudocode:

~~~yaml
# Đây là sơ đồ YAML minh họa, không dùng trực tiếp
# làm file workflow cho GitHub Actions hoặc Kubernetes.
pipeline:
  on: merge-to-main

  stages:
    - name: ci
      run:
        - compile
        - unit-test
        - secret-scan
        - dependency-policy

    - name: package
      requires: [ci]
      run:
        - build-immutable-image
        - create-sbom-and-provenance
        - sign-and-publish-artifact

    - name: integration
      requires: [package]
      run:
        - provider-consumer-contract-tests
        - database-migration-compatibility
        - integration-tests

    - name: staging
      requires: [integration]
      run:
        - deploy-same-artifact
        - smoke-tests
        - verify-observability

    - name: production
      requires: [staging]
      run:
        - rollout-canary
        - evaluate-promotion-policy
        - promote-or-abort
        - post-rollout-observation
~~~

Ở hiện thực thực tế, cần đặt điều kiện ràng buộc phiên bản: mỗi stage chỉ xử lý cùng một artifact digest; chuyển đổi trạng thái rollout phải được lưu bền vững; concurrent runs không thay đổi cùng target; quyền publish/prod deploy được tách khỏi quyền sửa mã hoặc xem secrets.

## 21. Phê duyệt thủ công có chọn lọc

Không phải mọi phát hành đều cần một cuộc họp; cũng không nên để mọi thay đổi có rủi ro cao tự động chạy như thường lệ.

Có thể phân cấp:

| Loại thay đổi | Ví dụ | Cách ra quyết định |
|---|---|---|
| Rủi ro thấp | Sửa log category, refactor nội bộ, thêm feature flag mặc định OFF | Tự động theo CI, contracts, rollout gates. |
| Rủi ro trung bình | Đổi timeout, caching, nâng dependency có ảnh hưởng client | Gates chặt hơn, canary dài hơn, người phụ trách trực sẵn. |
| Rủi ro cao | Thay đổi giao thức lớn, thanh toán, auth, migration phá tương thích | Cần phê duyệt có trách nhiệm, rehearsal và rollback/roll-forward plan rõ. |
| Thay đổi khẩn | Hotfix khôi phục sự cố production | Đường riêng với quyền hạn và audit; vẫn giữ các kiểm tra tối thiểu liên quan. |

Phê duyệt phải gắn với **phiên bản cụ thể**, bằng chứng test cụ thể và khoảng thời gian hiệu lực; không phê duyệt một tag mutable rồi sau đó artifact thay đổi. Quyền override gate cần giới hạn, ghi lý do và chịu trách nhiệm; không nên làm nút “force pass” tùy ý.

## 22. Ghi nhận bằng chứng và khả năng audit

Mỗi lần release nên trả lời được:

1. **Cái gì được phát hành?** Commit, artifact digest, manifest/config versions, feature flags.
2. **Ai hoặc hệ thống nào khởi tạo?** Trigger, pipeline run, approval, người chủ sở hữu.
3. **Được triển khai ở đâu?** Environment, region/zone, cluster, namespace, service, cohort.
4. **Qua những cổng nào?** CI runs, contract tests, migration readiness, security policy, smoke tests.
5. **Tại sao promote?** Các metric và baseline thực tế, thời gian quan sát, cỡ mẫu, policy version.
6. **Kết quả là gì?** Đã phục vụ bao nhiêu traffic, lỗi, độ trễ, business KPI, rollback/hold hay hoàn tất.
7. **Có thay đổi nào được override?** Lý do, thời hạn, người duyệt, kiểm soát thay thế.

Ví dụ một phần audit record:

~~~json
{
  "service": "order-service",
  "releaseId": "rel-2026-11-12-004",
  "artifactDigest": "sha256:<verified-digest>",
  "environment": "production",
  "step": "5-percent-to-25-percent",
  "policyVersion": "release-gates-v3",
  "observationWindow": "10m",
  "canaryRequestCount": 1000,
  "stableErrorPercent": 0.30,
  "canaryErrorPercent": 1.20,
  "decision": "FAIL",
  "action": "ABORT_AND_ROUTE_TO_STABLE",
  "reason": "ERROR_RATE_REGRESSION"
}
~~~

Trên production, record cần dùng digest thật, timestamp đúng, số liệu truy được tới metric query và trạng thái điều khiển rollout. Tránh đưa token, payload khách hàng hoặc dữ liệu nhạy cảm vào audit log. Lịch sử audit là chứng cứ kỹ thuật và vận hành, không phải bản sao toàn bộ request.

## 23. Kiểm thử chính pipeline và đường phục hồi

Một pipeline xanh chưa chắc là pipeline an toàn. Cần thử tình huống gate/rollout gặp sự cố:

| Tình huống | Hành vi mong đợi |
|---|---|
| Unit hoặc contract test thất bại | Artifact không được promote. |
| Image digest của staging và production không khớp | Dừng, yêu cầu xác nhận lại artifact. |
| Canary pods không Ready | Không nhận traffic hoặc abort theo chính sách. |
| Có 0 request canary | UNKNOWN/HOLD, không coi error rate bằng 0 là PASS. |
| Monitoring query timeout/mất dữ liệu | UNKNOWN/HOLD, không promote. |
| 5xx hoặc p95 vượt ngưỡng | FAIL, giảm traffic/rollback theo policy. |
| Business KPI sai dù 5xx bình thường | FAIL nếu correctness gate phát hiện. |
| Controller bị restart giữa rollout | Khôi phục trạng thái từ release record, không shift traffic lặp. |
| Hai pipeline chạy cho cùng service | Serialize hoặc cô lập, không trộn số liệu hai rollout. |
| Rollback khi database đã expand | Stable vẫn tương thích; xác minh phục vụ phục hồi. |
| DB migration phá schema | Không auto rollback mù; chuyển sang kế hoạch phục hồi chuyên biệt. |
| Feature flag service mất kết nối | Ứng xử theo default đã thiết kế; không tự bật rộng hơn. |
| Collector gửi dữ liệu trễ | Chỉ đánh giá khi window đủ và độ mới đạt chuẩn. |
| Dependency dùng chung gặp incident | HOLD hoặc abort theo chính sách; không tự đánh giá sai canary. |

**Diễn tập rollback** nên được làm trước thay đổi có rủi ro lớn. Biết chạy lệnh chuyển traffic không đủ; phải đo thời gian khôi phục (RTO), chất lượng dữ liệu còn lại, tình trạng request đang chạy và business side effects.

### Kiểm thử gate theo fixture

Với một evaluator có input metrics:

~~~text
Case A: sample đủ, mọi ngưỡng đạt => PASS
Case B: sample ít, 0 lỗi          => UNKNOWN
Case C: metric stale              => UNKNOWN
Case D: 5xx cao và sample đủ      => FAIL
Case E: rollout version lệch      => FAIL
Case F: business correctness lỗi  => FAIL
~~~

Các test này kiểm tra chính sách quyết định, không chỉ kiểm tra tool chạy thành công. Sau unit tests, cần integration test với telemetry và rollout controller thực tế hoặc môi trường mô phỏng tương đương để xác nhận truy vấn và hành động theo ngữ cảnh thật.

## 24. Những sai lầm thường gặp

1. **Xem CI xanh là đủ để lên production:** bỏ qua traffic và dependency thực tế. Cần gate runtime theo KPI.
2. **Dùng tag mutable `latest`:** cùng tên image nhưng nội dung khác nhau. Pin digest và ghi provenance.
3. **Test chỉ với các phiên bản mới nhất:** không phát hiện contract break khi old/new coexist. Kiểm tra version matrix.
4. **Canary quá ít traffic:** kết luận “0 lỗi” dù gần như không có request. Đặt minimum sample và maximum wait.
5. **Metric không có dữ liệu được hiểu là 0:** promote sai khi monitoring hỏng. Trạng thái UNKNOWN phải HOLD.
6. **Dựa duy nhất vào CPU hoặc readiness:** thiếu bằng chứng chức năng người dùng. Thêm application SLI và business correctness.
7. **Thiếu đường rollback trước release:** khi lỗi mới phát hiện chuyện schema/data không còn tương thích. Thiết kế expand–contract và diễn tập.
8. **Rollback image coi như rollback transaction:** tác dụng phụ payment/event không biến mất. Dùng idempotency, reconciliation/compensation.
9. **Mở 100% ngay sau canary 5% một phút:** thiếu thời gian quan sát, dễ lọt lỗi chậm. Chọn window theo hệ thống.
10. **Một gate không có owner hoặc policy version:** khó trả lời vì sao release được đi tiếp. Lưu quyết định và evidence.
11. **Cho tất cả thay đổi cần duyệt tay:** làm tắc delivery và tạo thói quen duyệt hình thức. Dùng cơ chế dựa trên rủi ro.
12. **Phê duyệt thủ công bỏ qua mọi kiểm tra:** rủi ro không có bằng chứng. Override phải hiếm, có lý do, thời hạn và audit.
13. **Triển khai hai bản cùng lúc khiến số liệu lẫn nhau:** không xác định phiên bản gây lỗi. Cô lập và điều phối concurrency.
14. **Coi hoàn tất 100% traffic là hết trách nhiệm:** lỗi có thể xuất hiện khi cache hết hạn, batch chạy hoặc traffic tăng. Cần theo dõi hậu triển khai.

## 25. Quy trình xây dựng từ một service đang triển khai thủ công

**Bước 1 — Đặt mục tiêu:** viết rõ SLO/SLI và rủi ro không chấp nhận được của service. Ví dụ: đơn hàng hoàn tất, tỷ lệ lỗi/độ trễ, mất message, trùng payment.

**Bước 2 — Xác định hành trình phát hành hiện tại:** từ merge tới production, ai thực hiện, điểm dừng nào, lỗi nào hay xảy ra, nguồn sự thật của image và config.

**Bước 3 — Chuẩn hóa artifact:** mỗi commit tạo image bất biến, gắn digest/provenance, không rebuild khi promote. Quản lý secrets riêng.

**Bước 4 — Tự động kiểm tra đầu nguồn:** compile, unit, contract, integration, security, schema migration và manifests. Phân loại gate bắt buộc so với advisory có điều kiện.

**Bước 5 — Chuẩn hóa readiness/staging:** kiểm tra app sẵn sàng, smoke test đường chính, khả năng đo canary và stable theo version/cohort.

**Bước 6 — Định nghĩa policy như dữ liệu:** version các ngưỡng, cửa sổ, mẫu tối thiểu, độ mới, hành động PASS/FAIL/UNKNOWN và chủ sở hữu.

**Bước 7 — Tạo canary nhỏ:** chuyển một phần traffic, lưu thời điểm bắt đầu và theo dõi cả lỗi kỹ thuật lẫn business correctness.

**Bước 8 — Tự động quyết định:** chỉ promote nếu đủ bằng chứng; hold khi thiếu dữ liệu; abort/rollback khi phát hiện bất thường được định nghĩa.

**Bước 9 — Xác nhận phục hồi và audit:** diễn tập rollback, ghi release record và kiểm chứng stable sau rollback; xử lý DB/message side effects riêng.

**Bước 10 — Tăng phạm vi thận trọng:** sau khi hệ thống đo đã đáng tin, mở rộng sang các service và môi trường khác; hiệu chỉnh policy bằng dữ liệu incident thật và thay đổi traffic.

Một rollout đã tự động thành công phải chứng minh được **phiên bản nào**, **đang nhận traffic bao nhiêu**, **metric nào cho phép tiếp tục**, và **cách quay lại** nếu điều kiện ngừng được kích hoạt.

## 26. Bài tập tình huống

Bạn quản lý `checkout-service`. Quy trình hiện tại: merge vào `main` → unit tests → build Docker image → deploy 100% production. Nhóm muốn chuyển sang tự động canary 5% → 25% → 100%.

Hệ thống có:

- Checkout HTTP gọi Inventory và Payment.
- Checkout phát event `OrderCreated` cho Notification Worker.
- Database chứa bảng `orders` được cả v1 và v2 sử dụng.
- Traffic bình quân 30.000 requests mỗi 15 phút, nhưng một số giờ thấp hơn nhiều.
- Các metric đã có: request count, 5xx, p95 latency, timeout, queue lag và checkout completion rate.
- Phiên bản v2 thêm một cột mới và thay đổi format của event `OrderCreated`.

**Câu hỏi:**

1. Điều kiện build/test nào nên chặn trước khi triển khai staging?
2. Cần kiểm tra tương thích giữa v1/v2 ở database và event như thế nào?
3. Định nghĩa một gate 5% với cửa sổ thời gian, mẫu tối thiểu, baseline và ba hành động PASS/FAIL/UNKNOWN.
4. Nếu canary không có request do routing sai, evaluator nên trả gì?
5. Nếu 5xx không tăng nhưng tỷ lệ checkout completed giảm mạnh, có được promote không?
6. Nếu v2 được rollback nhưng đã ghi event theo format mới mà Notification Worker cũ không đọc được, bạn cần phương án nào?
7. Nếu Payment Provider gặp sự cố đồng thời cả stable và canary, phải diễn giải số liệu ra sao?

### Hướng triển khai

- Trước staging: kiểm tra compile, unit, contract gRPC/HTTP/event, schema compatibility, integration qua Payment mock hoặc sandbox, provenance và chính sách security.
- Với DB: thêm cột theo expand–contract; cả v1 và v2 phải chạy được khi cùng tồn tại. Với event: version hoặc schema evolution giữ consumer compatibility, rồi mới đổi producer.
- Gate 5% có thể dùng cửa sổ 10–15 phút và min sample được hiệu chỉnh theo traffic. Bắt buộc có request đủ, metric mới, error rate/latency so sánh stable và checkout completion rate.
- Routing sai hoặc telemetry rỗng trả UNKNOWN/HOLD; không thể suy ra phiên bản lành mạnh.
- Correctness regression là lý do FAIL dù availability tốt.
- Rollback code không xử lý message format đã phát; cần compatible consumer, event versioning, hoặc chiến lược replay/repair rõ.
- Sự cố dependency chung có thể khiến cả hai nhóm xấu đi; cần tách common-cause incident với regression do v2 và thường HOLD rollout cho đến khi đo được dữ liệu đủ đáng tin.

## 27. Ghi nhớ

Tự động hóa phát hành microservices chỉ thật sự an toàn khi **mỗi bước tiến đều có bằng chứng và điều kiện dừng cụ thể**. Build một lần với artifact bất biến; kiểm tra hợp đồng và migration trước sản xuất; triển khai tăng dần bằng canary/feature flag; quan sát đầy đủ từ readiness tới latency, error rate và business correctness.

Một promotion gate có **PASS, FAIL và UNKNOWN**: chỉ PASS khi bằng chứng đủ và đáng tin; FAIL khi rủi ro vượt ngưỡng; UNKNOWN khi chưa thể kết luận thì HOLD. Kết hợp chính sách version hóa, audit và rollback/roll-forward có diễn tập giúp nhóm triển khai thường xuyên mà vẫn kiểm soát được sự cố liên service, dữ liệu và trải nghiệm người dùng.
