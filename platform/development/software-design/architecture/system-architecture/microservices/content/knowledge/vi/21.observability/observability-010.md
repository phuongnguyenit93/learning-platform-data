# Liên kết phiên bản triển khai với sự cố và thay đổi hành vi

## 1. Bài toán và mục tiêu

Một sự cố trong hệ thống Microservices có thể xảy ra ngay sau khi đội vận hành triển khai một phiên bản mới. Ví dụ, lúc 14:12 tỷ lệ thanh toán thất bại tăng, trong khi Payment Service bắt đầu deploy lúc 14:08. Hai thời điểm gần nhau là manh mối hữu ích nhưng **chưa chứng minh phiên bản mới gây sự cố**. Có thể cùng lúc xảy ra lỗi nhà cung cấp thanh toán, migration database, thay đổi feature flag, tăng tải hoặc hỏng cấu hình.

**Liên kết phiên bản triển khai với sự cố và thay đổi hành vi** là việc làm cho dữ liệu observability trả lời được ba câu hỏi: điều gì đã thay đổi, request hoặc người dùng nào thực sự nhận thay đổi, và kết quả có khác so với trước hay so với nhóm đối chứng không?

Sau bài này, người đọc có thể:

- Phân biệt release, artifact, Git SHA, deployment, config, schema và feature flag.
- Gắn phiên bản vào metrics, logs, traces và timeline thay đổi.
- Hiểu vì sao một dịch vụ có thể chạy nhiều phiên bản đồng thời.
- So sánh canary với stable theo error rate, latency, saturation và chỉ số nghiệp vụ.
- Phát hiện thay đổi hành vi dù HTTP vẫn trả 2xx.
- Phân tích tương quan và kiểm chứng nguyên nhân.
- Xử lý rollout, pause, rollback và xác minh phục hồi.
- Thiết kế dashboard, alert, runbook và bảng ghi sự cố có thể truy vết.

Bối cảnh ở đây là kiến trúc phân tán với các service được triển khai độc lập, có thể chạy trên Kubernetes hoặc nền tảng tương đương.

## 2. Vì sao chỉ nhìn thời điểm deploy là chưa đủ?

Giả sử checkout p95 tăng từ 450 ms lên 1.300 ms sau một lượt triển khai. Nếu dashboard chỉ có service.name=checkout, rất khó biết:

- Phiên bản mới đã thực sự nhận traffic chưa?
- Chỉ pod mới chậm hay tất cả pod đều chậm?
- Sự cố xuất hiện khi chuyển canary từ 5% lên 50%?
- Có một service phụ thuộc cũng triển khai cùng lúc?
- Feature flag chỉ bật cho một số tenant?
- Database migration đang khóa bảng?
- Runtime config mới thay timeout hoặc connection pool?
- Trace chậm thực sự đi qua phiên bản nào?

Mốc deployment là **change event**, không phải chứng cứ trực tiếp cho root cause. Muốn xác định tác động phải nhìn dữ liệu runtime và kết quả theo các nhóm chịu ảnh hưởng.

Ví dụ:

~~~text
14:00  Checkout v2.4.1 được build
14:08  Bắt đầu rollout production
14:12  Pod mới sẵn sàng
14:15  Canary nhận 5% traffic
14:22  Canary nhận 50% traffic
14:24  p95 checkout tăng
14:30  Rollback bắt đầu
14:35  Traffic trở về stable
14:38  p95 giảm
~~~

Nếu chỉ đánh dấu 14:08, người điều tra có thể bỏ qua thực tế triệu chứng bùng lên đúng lúc traffic shift tại 14:22.

## 3. Phân biệt các định danh của một thay đổi

| Thông tin | Ví dụ | Mục đích |
|---|---|---|
| service.name | checkout-service | Tên thành phần logic |
| service.version | 2.4.1 | Phiên bản chức năng |
| Git commit SHA | 8c91a1e | Mã nguồn cụ thể |
| Build ID | build-8421 | Một lần build CI |
| Image digest | sha256:abc... | Artifact bất biến |
| Deployment ID | deploy-prod-1422 | Một lần đưa artifact vào môi trường |
| Rollout revision | rollout-17 | Giai đoạn hoặc lần thay đổi workload |
| Config revision | checkout-config-v39 | Cấu hình runtime |
| Feature flag revision | flags-v12 | Quy tắc feature đang áp dụng |
| DB schema version | schema-148 | Trạng thái schema database |
| Experiment variant | checkout-v2 | Nhóm nhận hành vi mới |
| Environment/region | production / region-a | Phạm vi triển khai |

**service.version không đồng nghĩa deployment ID.** Một binary 2.4.1 có thể được đưa vào hai region vào thời điểm khác nhau hoặc deploy lại với cấu hình mới. Nếu chỉ ghi 2.4.1, sẽ khó phân biệt các lần triển khai đó.

**Git SHA không đồng nghĩa artifact.** Một commit có thể cho nhiều build, dependency hoặc base image khác nhau. Nên lưu image digest và thông tin build provenance bên cạnh commit.

**Code version không bao trùm mọi thay đổi.** Một feature flag, cấu hình retry, DNS, certificate, schema hoặc quy tắc phân quyền có thể đổi dù image không đổi.

**Rollback cũng là một deployment event mới.** Không được xóa hay ghi đè lịch sử rollout cũ; cần ghi thời điểm, target artifact và kết quả phục hồi.

## 4. Ba lớp dữ liệu cần liên kết

Một mô hình dễ hiểu gồm:

1. **Release artifact:** thứ được build từ mã nguồn, có version, SHA, image digest.
2. **Deployment record:** sự kiện đưa artifact vào môi trường, gồm thời gian, chiến lược, region, traffic allocation, config.
3. **Runtime observation:** metrics, logs và spans sinh ra từ instance/request đang chạy artifact và cấu hình thực tế.

~~~text
Source code -> CI build -> Immutable artifact
                                  |
                                  v
                          Deployment record
                    version / env / region / stage
                                  |
                +-----------------+----------------+
                |                 |                |
              Metrics            Traces           Logs
          rate/latency        request path       error/events
          by version          by version         by version
                |                 |                |
                +-----------------+----------------+
                                  |
                                  v
                     Incident timeline + diagnosis
~~~

Không cần sao chép mọi trường của deployment record vào từng metric. Chọn một số chiều có cardinality hợp lý, và để thông tin chi tiết trong registry/tracing/logging.

## 5. Một bản ghi deployment đủ dùng

Ví dụ sự kiện do hệ thống triển khai phát hành:

~~~json
{
  "deployment_id": "checkout-prod-20261112-1408",
  "service": "checkout-service",
  "environment": "production",
  "region": "region-a",
  "from_version": "2.4.0",
  "to_version": "2.4.1",
  "git_sha": "8c91a1e",
  "image_digest": "sha256:example-digest",
  "config_revision": "checkout-config-v39",
  "strategy": "canary",
  "started_at": "2026-11-12T07:08:00Z",
  "stage": "25-percent",
  "traffic_percent": 25,
  "status": "in_progress"
}
~~~

Dữ liệu trên chỉ để minh họa. Bản ghi thực nên có ID ổn định, timestamp, tác nhân hoặc pipeline chịu trách nhiệm, artifact trước/sau, environment, cluster/region, trạng thái và liên kết tới thay đổi liên quan.

Không ghi completed khi pipeline mới bắt đầu. Cần phân biệt pod đã sẵn sàng, lưu lượng đã được chuyển và quá trình drain phiên bản cũ đã xong.

Những event thường cần giữ:

- deployment.started
- deployment.pods_ready
- deployment.traffic_shifted
- deployment.paused
- deployment.resumed
- deployment.completed
- deployment.aborted
- deployment.rollback_started
- deployment.rollback_completed
- configuration.changed
- feature_flag.changed
- database_migration.started/completed

Các tên event có thể do tổ chức quy ước; nên thống nhất schema và nguồn phát sinh đáng tin.

## 6. Deployment markers trong dashboard

**Deployment marker** là annotation trên trục thời gian dashboard, đặt cạnh đường biểu diễn error rate, latency, throughput hoặc business success.

~~~text
Thời gian     14:00    14:08    14:15    14:22    14:35
                |--------|--------|--------|--------|
Checkout p95     450ms    470ms    520ms   1300ms   460ms
                           ^        ^        ^        ^
                       deploy    canary 5%  50%    rollback
                       started
~~~

Nếu deployment chạy nhiều giai đoạn, marker cần phản ánh từng đợt thay đổi traffic. Một lúc có thể có cả stable và canary phục vụ request. Ghi version đích và tỷ lệ thực tế giúp người xem không nhầm "bắt đầu deploy" với "đã nhận toàn bộ traffic".

Nếu annotation đến muộn, nên phân biệt event time và ingestion time. Sử dụng timestamp UTC hoặc có timezone rõ để kết nối sự kiện giữa hệ thống.

## 7. Gắn version vào traces

Trong distributed tracing, mỗi service sinh span có resource attributes. Ví dụ trong OpenTelemetry:

- service.name: checkout-service
- service.version: 2.4.1
- deployment.environment.name: production (theo conventions đang dùng)
- service.instance.id: instance/pod identity khi phù hợp

Ví dụ cấu hình dạng biến môi trường:

~~~text
OTEL_SERVICE_NAME=checkout-service
OTEL_RESOURCE_ATTRIBUTES=service.version=2.4.1,deployment.environment.name=production
~~~

Tên thuộc tính và đường cấu hình cụ thể tùy SDK/agent và semantic conventions. Cần kiểm tra chúng đã xuất hiện đúng trong tracing backend.

Ví dụ một trace:

~~~text
POST /checkout               Checkout v2.4.1     1700 ms
  cart.get                   Cart v1.8.3           70 ms
  inventory.reserve          Inventory v1.9.0     120 ms
  payment.authorize          Payment v3.2.5      1250 ms
    provider.request         External provider   1200 ms
  order.create               Order v2.1.0         140 ms
~~~

Một request qua nhiều service **không có cùng một version duy nhất**. Mỗi span cần ghi version của process tạo nó. Một trace chậm có thể được trigger từ Checkout v2.4.1 nhưng bottleneck thực tế nằm ở Payment v3.2.5 hoặc provider bên ngoài.

Khi xem trace, cần xác định:

1. Span SERVER nào thực sự nhận request.
2. Version của service đó lúc xử lý.
3. Đường đi quan trọng (critical path) của request.
4. Dependency nào chiếm thời gian hoặc gây lỗi.
5. Có retry, timeout, queue wait, connection pool wait không.
6. Những phiên bản upstream/downstream tham gia.

Không kết luận từ một trace đơn lẻ; phải xem nhiều trace nhanh/chậm trong các nhóm request tương đồng.

## 8. Gắn version vào structured logs

Log nên có cấu trúc ổn định để lọc:

~~~json
{
  "timestamp": "2026-11-12T07:23:12Z",
  "service": "payment-service",
  "serviceVersion": "3.2.5",
  "deploymentId": "payment-prod-20261112-1400",
  "region": "region-a",
  "traceId": "example-trace",
  "operation": "payment.authorize",
  "errorClass": "ProviderTimeout",
  "message": "Provider request timed out"
}
~~~

Tốt nhất metadata version/deployment được logger hoặc collector bổ sung nhất quán, thay vì từng lập trình viên ghép tay trong log message. Log giúp tìm thời điểm xuất hiện lớp lỗi mới, liên kết trace và phân tích theo instance.

Nhưng **đếm số log lỗi không luôn bằng tỷ lệ lỗi**. Version mới có thể tăng mức logging hoặc đổi format. Cần chia cho số request hoặc sử dụng metrics có định nghĩa ổn định.

Không log token, API key, thông tin thẻ, dữ liệu cá nhân nhạy cảm hoặc full request body chỉ để phục vụ correlation.

## 9. Gắn version vào metrics

Metrics là nguồn chính để đo quy mô và xu hướng sự cố. Các chiều có thể hữu ích:

- service, environment, region
- service_version hoặc rollout cohort
- route template và method
- status/outcome/error type được chuẩn hóa
- dependency name nếu có số lượng hữu hạn

Ví dụ time series:

~~~text
http_server_requests_seconds_count{
  service="checkout-service",
  service_version="2.4.1",
  uri="/checkout",
  status="500"
}
~~~

Không dùng raw URL có order ID hoặc user ID làm metric label. Cân nhắc trước khi thêm Git SHA, deployment ID, pod ID hoặc nhiều feature flags vào mọi time series: phép nhân số tổ hợp có thể làm tăng chi phí và hỏng hệ thống metrics.

Với thông tin chi tiết theo request, trace/log phù hợp hơn. Với so sánh version trong thời gian rollout, một chiều service_version có tập giá trị hữu hạn thường mang lại lợi ích lớn.

## 10. So sánh các chỉ số theo phiên bản

| Tín hiệu | Ý nghĩa | Điều kiện so sánh |
|---|---|---|
| HTTP 5xx/error rate | Lỗi kỹ thuật hiển thị | Cùng định nghĩa outcome |
| p50/p95/p99 latency | Độ trễ và tail latency | Cùng route/loại tải |
| Throughput/RPS | Version nhận bao nhiêu request | Hiển thị mẫu số |
| CPU/memory/saturation | Cạn tài nguyên | Cùng instance size/limit |
| Retry attempts | Lỗi bị che bằng retry | Xem tổng downstream traffic |
| Queue backlog/age | Chậm tác vụ bất đồng bộ | Đo completion latency |
| DB waits/queries | Thay đổi hành vi data access | Xem schema/query plan |
| Payment success rate | Thành công nghiệp vụ | Không chỉ dùng HTTP 200 |
| Order correctness | Dữ liệu được tạo đúng | Kiểm tra invariant |
| Feature exposure | Ai nhận logic mới | Tách cohort có kiểm soát |
| Cost/dependency calls | Bản mới phát sinh thêm tài nguyên | Xem fan-out/N+1 |

Một version có thể trả HTTP 200 nhưng tính sai giá, gửi thông báo trùng, không phát sự kiện, làm mất dữ liệu hoặc khiến người dùng bỏ checkout. Do đó **business metrics** và kiểm tra tính đúng đắn phải có chỗ đứng bên cạnh technical metrics.

## 11. Ví dụ PromQL cho canary/stable

Giả sử exporter đang có classic HTTP request metrics và nhãn service_version. Các tên metric/label bên dưới mang tính minh họa; phải dùng tên thực tế của hệ thống.

### 11.1. Request rate theo version

~~~promql
sum by (service_version) (
  rate(http_server_requests_seconds_count{job="checkout"}[5m])
)
~~~

Xem mẫu số trước khi tin một phần trăm lỗi, đặc biệt ở canary 1% với ít request.

### 11.2. Tỷ lệ lỗi 5xx

~~~promql
sum by (service_version) (
  rate(http_server_requests_seconds_count{
    job="checkout",status=~"5.."
  }[5m])
)
/
sum by (service_version) (
  rate(http_server_requests_seconds_count{job="checkout"}[5m])
)
~~~

Khi một version không có request, mẫu số bằng 0 hoặc series không xuất hiện; không diễn giải điều đó là version có tỷ lệ lỗi 0%. Cần hiển thị request count bên cạnh.

### 11.3. p95 latency với classic histogram

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service_version) (
    rate(http_server_requests_seconds_bucket{
      job="checkout"
    }[5m])
  )
)
~~~

Cách tính trên dành cho classic histogram có bucket với nhãn le. Nếu exporter dùng native histogram hoặc tên metric khác, truy vấn cần điều chỉnh. Histogram là ước lượng và phụ thuộc cấu hình bucket.

### 11.4. So cùng route

~~~promql
sum by (service_version, uri) (
  rate(http_server_requests_seconds_count{
    job="checkout",uri="/checkout"
  }[5m])
)
~~~

Tên nhãn route có thể là uri, route hoặc http_route. Sử dụng route template chuẩn để tránh label cardinality quá lớn.

## 12. So sánh trước/sau: những biến gây nhiễu

Giả sử p95 tăng sau deploy. Một so sánh đơn giản có thể sai vì:

- Traffic cao điểm sau 14:00 khác trước 14:00.
- Tỷ lệ request nặng, payload lớn hoặc cache miss tăng.
- Autoscaling chưa kịp đáp ứng.
- Canary được route tới vùng hoặc nhóm người dùng khác stable.
- Service phụ thuộc bị lỗi cùng lúc.
- Database backup/migration gây I/O hoặc lock.
- Connection pool cold sau restart.
- Feature flag và cấu hình thay đổi độc lập.
- Tracing sampling chỉ giữ request chậm/lỗi.

Phương pháp tốt hơn:

1. Chọn khoảng thời gian trước/sau đủ đại diện.
2. Phân nhóm theo route, region, loại traffic, payload/cohort và load.
3. So stable và canary đang chạy cùng thời điểm nếu có.
4. Hiển thị lượng request, phân bố và độ bất định.
5. Xem dependency metrics và change events khác.
6. Kết luận với mức độ tin cậy phù hợp.

Không dùng tập trace tail-sampled để suy ra trực tiếp error rate hay p95 toàn hệ thống. Metrics có độ bao phủ đúng là nguồn chủ đạo cho SLI; trace giúp giải thích những request cụ thể.

## 13. Canary và kiểm chứng rollout

Canary đưa một phần traffic tới bản mới:

~~~text
Stage 0: stable 100%
Stage 1: canary 1%
Stage 2: canary 5%
Stage 3: canary 25%
Stage 4: canary 50%
Stage 5: canary 100%
~~~

Ở mỗi stage, cần so canary với stable cùng thời điểm:

- Request rate và traffic mix.
- Technical error rate, timeout, latency.
- Tỷ lệ thành công nghiệp vụ.
- Saturation, retry, DB/queue effects.
- Tình trạng dependency và số lượng mẫu.
- Các guardrails phù hợp với rủi ro.

Ví dụ canary có 20 request và 1 lỗi thì error rate là 5%. Stable có 50.000 request và 0,3% lỗi. Chênh lệch đáng quan sát, nhưng dữ liệu canary rất ít nên chưa thể ước lượng chính xác mức regression. Có thể tăng thời gian quan sát trong giới hạn an toàn. Với lỗi tài chính hoặc an toàn dữ liệu nghiêm trọng, cần ưu tiên ngăn ảnh hưởng thay vì chờ thêm mẫu.

Canary không tự bảo đảm nhóm đối chứng công bằng. Nếu bản mới chỉ ở region A còn stable ở region B, sự khác biệt có thể do network/region. Route allocation, user cohort và feature exposure cần được ghi rõ.

## 14. Rolling update và blue-green

**Rolling update:** các pod cũ và mới cùng tồn tại trong thời gian rollout. Một service dashboard tổng hợp dễ che lỗi chỉ xảy ra ở pod mới. Cần group theo version và theo dõi pod readiness/drain, session affinity, connection còn mở.

**Blue-green:** hai nhóm môi trường chạy song song, sau đó chuyển traffic. Trước khi đối chiếu metrics phải xác nhận chúng dùng dependency và cấu hình tương đồng, và môi trường mới thực sự nhận request. Một cutover 100% khiến so sánh đồng thời khó hơn canary; cần baseline và khả năng rollback nhanh.

Trong cả hai mô hình, trạng thái pipeline "Success" có thể xuất hiện trước khi mọi request cũ kết thúc. Deployment registry cần phản ánh traffic thực tế.

## 15. Version matrix và tương thích giữa microservices

Vì mỗi service triển khai độc lập, một request có thể chạy qua tổ hợp version:

| Service | Stable | Canary |
|---|---|---|
| Checkout | 2.4.0 | 2.4.1 |
| Inventory | 1.9.0 | 1.9.1 |
| Payment | 3.2.4 | 3.2.5 |
| Order | 2.1.0 | Không |
| Pricing | 1.6.2 | Không |

Nếu chỉ Checkout 2.4.1 kết hợp Payment 3.2.5 gây lỗi, metric phân theo riêng Checkout version có thể chỉ thấy tín hiệu yếu. Trace cho phép xem **tổ hợp thực tế** của các service trong request.

Các lỗi tương thích thường gặp:

- Producer đổi trường sự kiện, consumer cũ không hiểu.
- Client mới gửi field API mà server cũ không chấp nhận.
- Retry/timeout policy thay đổi và khuếch đại tải.
- Cache key hoặc serialization format không tương thích.
- Version mới cần schema chưa triển khai đủ.
- Data do bản mới ghi không đọc được bởi bản cũ khi rollback.
- Một feature flag bật logic mới trước khi các service phụ thuộc sẵn sàng.

Contract testing, versioning schema, expand-and-contract migration và compatibility matrix giảm rủi ro. Để điều tra, cần metadata về phiên bản thực trong trace/log chứ không chỉ một bảng "version mới nhất".

## 16. Feature flags và cấu hình có thể đổi hành vi

Ví dụ Checkout 2.4.1 triển khai lúc 10:00, nhưng flag new-payment-flow chỉ bật lúc 15:30. Tỷ lệ lỗi tăng lúc 15:31. Nếu timeline chỉ có marker deploy 10:00, điều tra rất dễ bỏ qua thay đổi gần sự cố hơn.

Nên lưu:

- Tên flag, rule revision, variant được áp.
- Thời điểm thay đổi và thời điểm rule có hiệu lực.
- Nhóm cohort/tenant/region được tác động, theo quy định dữ liệu.
- Người hoặc pipeline thực hiện thay đổi.
- Trạng thái trước/sau và cách tắt/rollback.
- Kiểm tra cache TTL của flag SDK và sự khác biệt giữa instance.

Không đưa toàn bộ tập user attributes hoặc mọi flag vào metric labels. Với flag quan trọng, có thể dùng span event/attribute được chuẩn hóa và metric cohort có kiểm soát.

**Configuration changes** như endpoint, pool size, feature parameters, TLS và retry policy cũng cần version/hash và change marker. Không gửi secret hoặc full config vào observability.

## 17. Database migration và hành vi dữ liệu

Một ví dụ dễ gây nhầm:

~~~text
14:00  Schema migration bắt đầu
14:05  Database lock wait tăng
14:08  Checkout v2.4.1 bắt đầu rollout
14:10  Latency tăng mạnh
14:15  Migration hoàn tất
14:18  Latency giảm dù v2.4.1 vẫn chạy
~~~

Nếu không ghi migration event, có thể đổ lỗi sai cho Checkout. Nên liên kết DB migration version, start/end/status với lock metrics, query latency, CPU/I/O và connection saturation.

Các hệ thống production thường cần migration kiểu expand-and-contract:

1. Thêm schema tương thích với version cũ/mới.
2. Deploy ứng dụng biết đọc/ghi theo chế độ chuyển tiếp.
3. Backfill dữ liệu theo đợt có kiểm soát.
4. Bật tính năng mới và tăng traffic.
5. Loại bỏ schema cũ chỉ sau khi không còn consumer phụ thuộc.

Rollback code không luôn khôi phục dữ liệu/schema. Runbook cần xác định khả năng rollback, giới hạn và hành động đối soát dữ liệu.

## 18. Phân biệt tương quan và nguyên nhân

**Correlation:** lỗi tăng gần mốc triển khai. **Causation:** thay đổi đó thực sự dẫn tới lỗi thông qua cơ chế có thể kiểm chứng.

Bằng chứng hỗ trợ một giả thuyết mạnh:

- Canary lỗi rõ rệt hơn stable cùng thời điểm, cùng traffic mix.
- Lỗi tăng theo tỷ lệ traffic chuyển vào bản mới.
- Trace/log chỉ ra code path hoặc dependency mới khác biệt.
- Thực nghiệm có kiểm soát tái hiện regression.
- Tắt flag hoặc rollback làm triệu chứng giảm khi các yếu tố khác ổn định.
- Phiên bản có lỗi chứa một thay đổi logic tương ứng với triệu chứng.

Bằng chứng phản chứng:

- Lỗi xuất hiện trước khi version mới nhận request.
- Stable và canary cùng lỗi như nhau.
- Dependency chung bị outage toàn khu vực.
- Traffic mix, cache cold hoặc hạ tầng giải thích sự khác biệt.
- Sai lệch sampling hoặc instrumentation khiến dữ liệu không đại diện.

Rollback thành công vẫn chưa luôn chứng minh nguyên nhân: rollback có thể đồng thời reset connection pool, giảm concurrency hoặc kích hoạt fallback. Phân loại kết luận là confirmed, likely hoặc unresolved tùy chứng cứ, và ghi điều gì còn chưa biết.

## 19. Thay đổi hành vi khi HTTP vẫn 200

Các thay đổi có thể không làm tăng 5xx:

- Checkout trả giá sai nhưng response 200.
- Payment được chấp nhận hai lần do retry thiếu idempotency.
- Order được tạo nhưng event tiếp theo bị mất.
- Notification gửi trùng.
- Cấu hình timeout khiến nhiều request fallback và kết quả kém chính xác.
- Authorization policy mới chặn người dùng hợp lệ.
- Cache stale làm hiển thị trạng thái cũ.
- Queue lag kéo dài dù HTTP enqueue trả 202.
- Tỷ lệ conversion giảm do giao diện thay đổi.

Nên đo **business success/correctness** bằng các event rõ nghĩa:

~~~text
checkout_started
payment_authorized
order_created
checkout_completed
checkout_abandoned
~~~

Khi tính conversion cần deduplicate event, xử lý late arrivals và có mẫu số nhất quán. Metadata cohort/version được dùng để so nhóm chịu ảnh hưởng. Với thao tác tài chính, phải ưu tiên bất biến nghiệp vụ và đối soát dữ liệu, không chỉ dựa vào dashboard thành công kỹ thuật.

## 20. Quy trình điều tra sự cố có thay đổi gần đó

### Bước 1 — Đặt ranh giới sự cố

Xác nhận metric hoặc nghiệp vụ bị ảnh hưởng, thời điểm, môi trường, region, service, route, mức độ. Dùng UTC hoặc timezone rõ ràng.

### Bước 2 — Tập hợp change timeline

Lấy deployment, rollout stage, config/flag, schema migration, infrastructure và dependency events trong cửa sổ liên quan. Đặt cạnh đường biểu diễn error rate, latency, throughput, saturation và business metrics.

### Bước 3 — Xác minh runtime exposure

Kiểm tra version nào thực sự phục vụ request, ở region/pod nào, canary đang chiếm bao nhiêu traffic. Đối chiếu readiness, routing và sticky session. Một deployment chỉ bắt đầu chưa có nghĩa traffic đã đi vào binary mới.

### Bước 4 — So sánh nhóm

So stable với canary cùng thời điểm và route, chọn cohort phù hợp. Xem request count, distribution, error rate, latency, business outcome. Loại trừ khác biệt tải, dependency và feature flags.

### Bước 5 — Đào sâu trace/log

Chọn trace chậm/lỗi của version nghi vấn, tìm critical path, retry, timeout, error source và version từng service. Đọc log theo trace ID và các error class.

### Bước 6 — Kiểm tra nguyên nhân thay thế

Xem DB, broker, provider API, mạng, CPU, memory, queue, migration, certificate/config hoặc platform event. Tránh mặc định "deploy gần nhất" là nguyên nhân.

### Bước 7 — Giảm tác động

Dừng tăng canary, tắt flag, giảm traffic hoặc rollback nếu guardrail bị vi phạm. Cân nhắc mức rủi ro và khả năng đảo ngược dữ liệu. Với lỗi nghiêm trọng, giảm tác động sớm là hợp lý ngay cả khi root cause chưa xác định đầy đủ.

### Bước 8 — Xác minh phục hồi

Sau thay đổi, kiểm tra traffic đã quay về version mong muốn, các instance cũ đã drain, error rate/latency và business success hồi phục; nhìn cả queue/backlog và dữ liệu giao dịch chưa đối soát.

### Bước 9 — Ghi kết luận

Lưu timeline, những giả thuyết đã kiểm tra, bằng chứng, trạng thái xác định nguyên nhân, hành động khắc phục và guardrail cần thêm.

## 21. Ví dụ điều tra: Checkout success giảm

Giả sử sau rollout:

| Nhóm | Requests / 10 phút | HTTP 5xx | Checkout hoàn tất |
|---|---:|---:|---:|
| Stable 2.4.0 | 20.000 | 40 | 19.200 |
| Canary 2.4.1 | 2.000 | 6 | 1.760 |

Tính toán:

- 5xx stable: 40 / 20.000 = 0,20%.
- 5xx canary: 6 / 2.000 = 0,30%.
- Checkout success stable: 19.200 / 20.000 = 96%.
- Checkout success canary: 1.760 / 2.000 = 88%.

Sự khác biệt business success 8 điểm phần trăm lớn hơn sự khác biệt 5xx. Đây là tín hiệu quan trọng: có thể nhiều request trả 200 nhưng không hoàn tất đơn. Điều tra event order_created, payment_authorized và quy trình fallback để tìm nơi rơi mất bước nghiệp vụ.

Vẫn phải kiểm tra routing, payment method, region, các segment khách hàng, traffic mix và metric semantics. Không thể suy ra canary là nguyên nhân cuối cùng chỉ từ bảng số liệu.

Nếu tắt flag new-payment-flow làm business success phục hồi, cần lưu flag-off event và xem trace/logic của nhánh mới; không kết luận quá sớm rằng bản binary 2.4.1 hoàn toàn lỗi.

## 22. Ví dụ Java/Spring Boot: version cho metrics

Một cách đơn giản để ghi version ứng dụng dưới dạng common tags trong Micrometer:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MetricsVersionConfiguration {
    @Bean
    MeterRegistryCustomizer<MeterRegistry> versionTags(
            @Value("#{systemEnvironment['APP_VERSION'] ?: 'unknown'}")
                    String version,
            @Value("#{systemEnvironment['APP_ENVIRONMENT'] ?: 'unknown'}")
                    String environment) {
        return registry -> registry.config().commonTags(
                "service_version", version,
                "environment", environment
        );
    }
}
~~~

Đây là ví dụ ứng dụng Spring Boot có Actuator/Micrometer; tùy version framework, cần cấu hình exporter tương ứng. Pipeline deployment đặt APP_VERSION bằng định danh artifact và APP_ENVIRONMENT bằng môi trường đã được xác định. Các tag common nên được cấu hình trước khi meter được tạo.

Không thay các nhãn này bằng giá trị sinh mới cho mỗi request. Với version mới mỗi commit, hãy đánh giá cardinality và retention.

Traces có thể ghi OpenTelemetry resource service.version qua agent hoặc SDK; logs có thể lấy cùng APP_VERSION từ cấu hình logger/collector. Dùng một nguồn build/deployment metadata để tránh metrics ghi 2.4.1 còn log ghi 2.4.0 do cấu hình lệch.

### Ví dụ event từ pipeline

~~~json
{
  "type": "deployment.traffic_shifted",
  "deployment_id": "checkout-prod-20261112-1408",
  "service": "checkout-service",
  "environment": "production",
  "region": "region-a",
  "from_version": "2.4.0",
  "to_version": "2.4.1",
  "traffic_percent": 25,
  "timestamp": "2026-11-12T07:15:00Z",
  "status": "applied"
}
~~~

Event phải phản ánh trạng thái traffic thật, không chỉ việc chạy thành công một lệnh CI. Nếu có rollout controller hoặc service mesh, tận dụng dữ liệu xác nhận traffic split/readiness thực tế.

## 23. Alert và runbook có bối cảnh phiên bản

Một alert hữu ích cần có:

- Tín hiệu vượt ngưỡng, giá trị hiện tại, baseline và cửa sổ quan sát.
- Service, environment, region, route và mức độ ảnh hưởng.
- Recent deployment/config/flag/schema changes liên quan.
- Version/cohort nghi vấn, chỉ khi dữ liệu hỗ trợ.
- Link dashboard, trace search, log query, runbook.
- Quy trình tạm dừng rollout, rollback hoặc tắt flag.

Ví dụ:

~~~text
Checkout completion rate giảm từ 96% còn 88% trong nhóm canary
trong 10 phút; canary v2.4.1 hiện nhận 10% traffic tại region-a.
Recent change: traffic shift lúc 14:15.
Kiểm tra cohort, payment method và dependency trước khi xác định root cause.
~~~

Không tự động đưa lời kết luận "Deployment X gây lỗi" vào alert nếu chỉ có tương quan thời gian. Có thể xếp hạng recent changes theo mức liên quan và hiển thị bằng chứng kèm theo.

## 24. Rollback và kiểm chứng sau rollback

Rollback cần được xem là một thay đổi có lịch sử riêng:

1. Ghi deployment ID, version đích và lý do rollback.
2. Kiểm tra binary cũ có tương thích schema/data hiện tại không.
3. Thực hiện chuyển traffic hoặc tái triển khai artifact cũ.
4. Theo dõi pod readiness và tỷ lệ traffic thực ở stable/canary.
5. Xem p95/p99, lỗi, throughput và business correctness sau rollback.
6. Theo dõi queue backlog, transaction đang xử lý và event đến muộn.
7. Kiểm tra những side effects đã xảy ra: giao dịch trùng, đơn bị mất, dữ liệu cần đối soát.
8. Ghi rollback completed chỉ khi runtime và các chỉ số quan trọng đã ổn định.

Nếu nguyên nhân nằm ở feature flag, tắt flag có thể nhanh và an toàn hơn rollback cả service. Nếu migration dữ liệu không thể đảo ngược, rollback binary có thể gây thêm lỗi. Runbook phải giải thích lựa chọn và giới hạn cụ thể.

## 25. Những sai lầm phổ biến

1. **Không gắn version vào telemetry:** không tách được pod cũ/mới trong rolling update.
2. **Chỉ ghi một mốc deploy:** bỏ qua các giai đoạn traffic shift.
3. **Cho rằng Git SHA đủ:** bỏ qua image digest, config và schema.
4. **So trước/sau mà không xét traffic mix:** dễ kết luận sai.
5. **Không có sample count:** kết luận từ một vài request canary.
6. **Chỉ đo HTTP status:** bỏ sót kết quả nghiệp vụ sai.
7. **Không ghi feature flag changes:** gán nhầm lỗi cho binary gần nhất.
8. **Gắn ID động vào metric labels:** cardinality tăng rất nhanh.
9. **Không xét phiên bản service phụ thuộc:** bỏ qua lỗi tương thích.
10. **Không ghi data migration:** không thấy lock/backfill làm chậm hệ thống.
11. **Dùng trace sampled để tính tỷ lệ lỗi toàn cục:** dữ liệu có thiên lệch.
12. **Rollback không kiểm tra dữ liệu:** hậu quả vẫn tồn tại.
13. **Khẳng định nguyên nhân chỉ từ tương quan:** thiếu phản chứng và kiểm chứng.
14. **Thiếu timeline sau incident:** khó học lại hoặc tái hiện sự cố.

## 26. Bài tập áp dụng

Một dịch vụ Search được deploy v3.1.0 lúc 16:00, nhưng latency tăng lúc 16:20. Biết rằng:

- 16:00: deployment.started.
- 16:08: pod mới ready nhưng chưa có traffic.
- 16:15: canary nhận 5%.
- 16:20: canary nhận 50%; p95 search tăng.
- 16:22: Database ghi nhận pool wait tăng.
- 16:28: tắt feature flag semantic-ranking, p95 giảm dù v3.1.0 vẫn chạy.
- 16:35: rollout tạm dừng để điều tra.

Hãy trả lời:

1. Mốc nào liên quan trực tiếp hơn đến việc p95 tăng: 16:00 hay 16:20? Vì sao?
2. Có thể kết luận v3.1.0 gây lỗi từ dữ liệu trên chưa?
3. Tại sao feature flag là ứng viên mạnh?
4. Cần so sánh metrics nào của canary và stable?
5. Cần dùng trace để tìm điều gì trong đường đi Search → Database?
6. Thông tin nào phải có trong deployment/flag event để đối chiếu?
7. Nếu flag off phục hồi latency nhưng query correctness giảm, có được coi là hồi phục hoàn toàn không?

Gợi ý: cần kiểm tra thời điểm và phần trăm traffic thực, sự khác biệt query mix, database pool wait, các spans truy vấn mới, variant được đánh giá và cả business correctness của kết quả tìm kiếm. Một hệ thống "nhanh hơn" nhưng trả kết quả sai chưa chắc đáp ứng SLO.

## 27. Checklist trước khi đưa vào vận hành

- [ ] Có version, build ID, Git SHA và artifact digest cho mỗi release.
- [ ] Có deployment ID, environment, region, rollout stage và start/end time.
- [ ] Thời điểm pod ready và traffic shift được ghi riêng.
- [ ] Metrics phân nhóm được theo phiên bản/cohort có số lượng giá trị hợp lý.
- [ ] Logs có version, timestamp, region và trace ID khi phù hợp.
- [ ] Traces hiển thị version của từng service tham gia.
- [ ] Dashboard có deployment annotations và recent change timeline.
- [ ] Feature flag/config/schema/infrastructure changes cũng được ghi.
- [ ] Guardrails có error, latency, saturation và business correctness.
- [ ] So sánh canary/stable có kiểm soát route, region, traffic mix và lượng mẫu.
- [ ] Alerts cung cấp bối cảnh thay đổi nhưng không tự khẳng định root cause.
- [ ] Runbook có pause/abort/rollback và kiểm tra tính tương thích dữ liệu.
- [ ] Có bước xác minh phục hồi và điều tra side effects sau rollback.
- [ ] Lịch sử incident có thể truy ngược tới artifact và các quyết định triển khai.

## 28. Ghi nhớ

**Phiên bản**, **lần triển khai** và **một request đang chạy trên instance cụ thể** là ba lớp thông tin khác nhau. Muốn hiểu một sự cố, phải kết nối cả ba với kết quả quan sát được.

Một deployment gần mốc lỗi là manh mối chứ chưa phải nguyên nhân. Cần kết hợp change timeline, metrics phân theo version, trace cho các request đại diện, logs, dependency metrics và chỉ số đúng đắn nghiệp vụ. So sánh canary/stable cùng thời điểm giúp kiểm chứng nhưng phải xét traffic mix, sample size và các thay đổi độc lập.

Thay đổi hành vi có thể đến từ code, feature flag, cấu hình, schema, dữ liệu hoặc dependency. Rollback code không luôn đảo ngược các thay đổi đó.

**Thực hành quan trọng nhất: ghi rõ điều gì đã thay đổi, ai thực sự nhận thay đổi, kết quả khác ra sao và bằng chứng nào cho phép kết luận nguyên nhân.**