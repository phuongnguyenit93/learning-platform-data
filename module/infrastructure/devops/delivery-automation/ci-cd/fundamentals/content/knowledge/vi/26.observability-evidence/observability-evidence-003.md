# Liên kết commit, pipeline, artifact và môi trường trong cùng dấu vết

Khi một dịch vụ gặp lỗi sau triển khai, câu hỏi đầu tiên thường không chỉ là “pod nào đang lỗi?”. Nhóm cần biết phiên bản nào vừa được phát hành, phiên bản đó được build từ commit nào, pipeline nào tạo ra artifact, artifact có digest gì, môi trường nào đang chạy nó và request lỗi đã đi qua những thành phần nào.

Nếu commit, pipeline run, artifact, deployment và telemetry được lưu ở các hệ thống riêng nhưng không có khóa liên kết, việc điều tra sẽ phải dựa vào tên tag, thời gian gần đúng hoặc trí nhớ của người vận hành. Những cách dò tìm này dễ nhầm giữa các lần build, đặc biệt khi một commit được build nhiều lần hoặc cùng một artifact được triển khai ở nhiều môi trường.

**Dấu vết phát hành (release traceability)** là khả năng nối các bằng chứng đó thành một chuỗi có thể truy vấn: từ thay đổi mã nguồn đến pipeline, artifact bất biến, lần triển khai cụ thể và hành vi runtime sau triển khai. Mục tiêu là trả lời được artifact nào đang chạy ở đâu, được tạo từ đâu, ai hoặc hệ thống nào đã triển khai, cấu hình nào được áp dụng và bằng chứng vận hành nào liên quan.

Đây là năng lực thuộc **DEVOPS_CI_CD_FUNDAMENTALS**: xây dựng tư duy CI/CD từ sự kiện Git, pipeline dưới dạng mã, build và kiểm thử tự động đến quản lý artifact, môi trường, cổng chất lượng, phát hành có truy vết, bảo vệ bí mật, xác minh sau triển khai và khả năng quay lui.

## 1. Vì sao cần một dấu vết xuyên suốt?

Một release thường đi qua nhiều hệ thống:

- Git lưu repository, branch, commit, tag, pull request và review.
- CI platform lưu workflow, job, pipeline run, test result và approval.
- Build system tạo package, binary hoặc container image.
- Artifact registry lưu artifact và digest.
- Hệ thống provenance/SBOM lưu bằng chứng nguồn gốc và thành phần.
- Deployment platform ghi nhận môi trường, region, cluster, namespace và rollout.
- Hệ thống observability lưu log, metrics, traces, alert và sự kiện runtime.
- Incident/change management lưu quyết định, người chịu trách nhiệm và kết quả xử lý.

Mỗi hệ thống có ID riêng. Không cần ép tất cả dùng cùng một ID; cần lưu các quan hệ giữa chúng bằng những định danh ổn định.

Ví dụ, khi alert báo lỗi tăng ở production, người trực cần lần theo:

1. Service và environment đang bị ảnh hưởng.
2. Deployment nào vừa thay đổi service đó.
3. Deployment sử dụng artifact digest nào.
4. Artifact được tạo bởi pipeline run nào.
5. Pipeline run lấy source commit nào và dùng workflow revision nào.
6. Những dependency, cấu hình hoặc migration nào có liên quan.
7. Request trace, log và metrics nào cho thấy lỗi bắt đầu từ thời điểm nào.

Nếu những liên kết này có sẵn, nhóm có thể xác định phạm vi ảnh hưởng và chọn hành động như rollback, forward-fix hoặc tắt feature flag với bằng chứng rõ ràng.

## 2. Chuỗi định danh: commit → pipeline → artifact → deployment → runtime

Một mô hình liên kết điển hình:

~~~mermaid
flowchart LR
    A["Git repository<br/>commit SHA"] --> B["CI pipeline<br/>run ID"]
    B --> C["Build output<br/>artifact digest"]
    C --> D["Provenance / SBOM<br/>attestation"]
    C --> E["Deployment record<br/>deployment ID"]
    E --> F["Environment<br/>cluster / region"]
    F --> G["Runtime telemetry<br/>logs / metrics / traces"]
    G --> H["Incident / change record"]
    H --> E
~~~

Các định danh chính:

| Định danh | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Repository URL | Mã nguồn thuộc repository nào? | URL repository đã chuẩn hóa |
| Commit SHA | Nội dung source chính xác là gì? | Full Git commit SHA |
| Pipeline run ID | Lần chạy CI nào đã xử lý source? | Workflow run hoặc pipeline ID |
| Workflow revision | Định nghĩa pipeline nào đã chạy? | Commit SHA của workflow/template |
| Artifact digest | Nội dung binary/image chính xác là gì? | SHA-256 digest |
| Release ID | Nhóm đang nói về đợt phát hành logic nào? | rel-orders-2026-0042 |
| Deployment ID | Lần triển khai cụ thể nào? | deploy-prod-ap-southeast-184 |
| Environment identity | Artifact được chạy ở đâu? | production / cluster / namespace / region |
| Trace ID | Request phân tán cụ thể nào đang được theo dõi? | W3C trace ID |
| Incident/change ID | Quyết định vận hành hoặc sự cố nào liên quan? | INC-... hoặc CHG-... |

**Release ID** có thể liên kết nhiều deployment. Ví dụ cùng một release được triển khai lên staging rồi production, hoặc production ở hai region. **Deployment ID** xác định một lần áp dụng cụ thể cho một môi trường. **Artifact digest** xác định nội dung được triển khai. Ba khái niệm này không thay thế nhau.

## 3. Phân biệt release ID, deployment ID, correlation ID và trace ID

Các ID thường bị dùng lẫn nhau, dẫn đến log khó truy vấn hoặc dữ liệu metrics phình to.

| ID | Phạm vi | Vòng đời |
| --- | --- | --- |
| Release ID | Một đợt phát hành sản phẩm/service | Từ lúc tạo release đến khi kết thúc theo dõi |
| Deployment ID | Một lần triển khai artifact vào một môi trường/target | Một deployment hoặc rollout cụ thể |
| Correlation ID | Một nghiệp vụ hoặc yêu cầu cần nối qua nhiều hệ thống | Theo luồng nghiệp vụ hoặc request group |
| Trace ID | Một distributed trace gồm các span | Theo một lần thực thi được instrument |
| Span ID | Một operation bên trong trace | Một khoảng thực thi cụ thể |
| Commit SHA | Một trạng thái source trong Git | Bất biến theo object Git |
| Artifact digest | Nội dung artifact | Bất biến theo nội dung đã hash |

Release ID không phải trace ID. Một release có thể tạo ra hàng triệu request và mỗi request có trace ID riêng. Không tạo một trace ID chung cho toàn bộ release.

Correlation ID cũng không thay thế distributed tracing. Correlation ID có thể được tạo ở tầng nghiệp vụ để nối một đơn hàng hoặc một workflow qua nhiều request. Trace ID theo dõi một lần thực thi phân tán cụ thể. Một nghiệp vụ kéo dài nhiều phút có thể gồm nhiều trace nhưng vẫn dùng chung business correlation ID.

Định nghĩa rõ nơi tạo ID, định dạng, phạm vi duy nhất và cách truyền. Tránh dùng timestamp đơn lẻ làm ID vì hai event có thể cùng thời điểm và đồng hồ giữa các hệ thống có thể lệch.

## 4. Tạo release manifest làm điểm nối

Một release manifest là bản ghi có cấu trúc tổng hợp các định danh và tham chiếu bằng chứng của một release. Nó giúp người vận hành hoặc công cụ tra cứu từ một điểm bắt đầu.

Ví dụ:

~~~yaml
release:
  id: rel-orders-2026-0042
  service: orders-api
  source:
    repository: https://git.example.com/commerce/orders-api
    ref: refs/heads/main
    commit: 4f9a1c2d7b...
  pipeline:
    provider: ci-platform
    run_id: pipeline-1842
    workflow_revision: 9a71c4e...
    started_at: "2026-11-18T07:30:00Z"
    completed_at: "2026-11-18T07:38:20Z"
  artifact:
    uri: registry.example.com/commerce/orders-api
    version: 2.8.0
    digest: sha256:7b2d...e91a
    provenance: evidence/provenance/7b2d.json
    sbom: evidence/sbom/7b2d.cdx.json
  deployments:
    - id: deploy-staging-184
      environment: staging
      region: ap-southeast-1
      artifact_digest: sha256:7b2d...e91a
      config_revision: 81bc2f...
      status: verified
    - id: deploy-production-221
      environment: production
      region: ap-southeast-1
      artifact_digest: sha256:7b2d...e91a
      config_revision: a13d77...
      status: active
~~~

Đây là schema minh họa, không phải định dạng bắt buộc của một CI platform. Trong hệ thống thật, dùng full commit SHA và digest đầy đủ, URI có quyền truy cập phù hợp, timestamp UTC và ID deployment do hệ thống tạo. Không lưu secret, token hoặc giá trị cấu hình nhạy cảm trong manifest.

Manifest có thể được lưu cùng release metadata hoặc trong kho bằng chứng. Nếu cần cập nhật trạng thái deployment, nên tạo event hoặc revision mới có audit trail thay vì âm thầm ghi đè thông tin lịch sử.

## 5. Ghi lại bằng chứng ở từng chặng

Mỗi bước nên phát ra một event hoặc record đủ thông tin để nối với bước trước và bước sau.

### 5.1. Source event

Khi code được merge hoặc tag release được tạo, ghi:

- Repository URL.
- Commit SHA đầy đủ.
- Ref/branch/tag.
- Pull request hoặc change request liên quan.
- Người hoặc danh tính đã tạo/merge thay đổi theo chính sách.
- Thời điểm event và hệ thống phát event.

Commit SHA là khóa quan trọng hơn branch name. Branch có thể tiến lên commit mới; nếu chỉ ghi main thì sau này không biết chính xác source nào đã được build.

### 5.2. Pipeline event

Ghi:

- Pipeline run ID và job ID.
- Workflow/pipeline definition revision.
- Trigger type: push, pull request, tag, schedule hoặc manual.
- Source commit được checkout thực tế.
- Runner/builder identity và toolchain version.
- Kết quả test, quality gate, approval và thời gian thực thi.
- Liên kết log/report theo quyền truy cập.

Pipeline definition cũng là một đầu vào. Cùng source commit nhưng chạy hai revision workflow khác nhau có thể tạo kết quả khác nhau. Vì vậy, ghi cả revision của workflow hoặc reusable template khi có thể.

### 5.3. Artifact event

Ghi:

- Artifact URI và loại artifact.
- Version/tag dễ đọc.
- Digest bất biến.
- Build run ID tạo ra artifact.
- Provenance, SBOM, signature và scan report.
- Registry/repository và thời điểm publish.

Không dùng tag có thể thay đổi làm khóa duy nhất. Nếu tag 2.8.0 bị ghi đè, deployment record phải vẫn chỉ ra digest thực tế.

### 5.4. Deployment event

Ghi:

- Deployment ID và release ID.
- Artifact digest được áp dụng.
- Environment, cluster, namespace, region và target.
- Config/manifest revision và infrastructure revision.
- Người hoặc workload identity khởi chạy deployment.
- Approval/change request liên quan.
- Thời điểm bắt đầu, hoàn tất, trạng thái và kết quả verify.
- Rollout strategy, tỷ lệ traffic hoặc feature flag stage nếu có.

Nên ghi cả trạng thái mong muốn và trạng thái thực tế. Pipeline có thể yêu cầu triển khai digest A nhưng cluster vẫn chạy digest B do rollout chưa hoàn tất hoặc một instance cũ chưa bị thay thế.

### 5.5. Runtime evidence

Ghi và liên kết:

- Service name và service version.
- Environment và deployment identity.
- Log có timestamp, severity, request/correlation ID.
- Trace có trace ID và span ID.
- Metrics về error rate, latency, saturation và business outcomes.
- Alert, incident và thao tác rollback/mitigation.

Runtime evidence phải chỉ ra nó quan sát service nào, phiên bản nào và ở môi trường nào. Nếu telemetry không có version hoặc deployment context, việc so sánh trước/sau release sẽ khó chính xác.

## 6. Liên kết với logs, metrics và traces

Ba tín hiệu observability có vai trò khác nhau:

| Tín hiệu | Dùng để trả lời | Trường liên kết hữu ích |
| --- | --- | --- |
| Logs | Điều gì đã xảy ra tại một thời điểm? | timestamp, service, environment, release/deployment ID, trace ID |
| Metrics | Mức độ và xu hướng của vấn đề ra sao? | service, environment, version, region, rollout stage |
| Traces | Một request đi qua các service/span nào? | trace ID, span ID, service version, deployment context |

### 6.1. Structured logs

Ưu tiên log có cấu trúc thay vì chỉ ghi một câu tự do:

~~~json
{
  "timestamp": "2026-11-18T08:15:22.481Z",
  "severity": "ERROR",
  "service.name": "orders-api",
  "service.version": "2.8.0",
  "deployment.environment.name": "production",
  "release.id": "rel-orders-2026-0042",
  "deployment.id": "deploy-production-221",
  "artifact.digest": "sha256:7b2d...e91a",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "message": "Order persistence failed",
  "error.type": "DatabaseTimeout"
}
~~~

Các tên thuộc tính trong ví dụ là cách đặt tên minh họa; nếu tổ chức dùng OpenTelemetry hoặc schema log chuẩn, hãy tuân theo convention và mapping thống nhất. Không ghi access token, password, dữ liệu thẻ, nội dung cá nhân hoặc payload nhạy cảm vào log.

### 6.2. Metrics và cardinality

Metrics giúp so sánh error rate, latency và saturation trước/sau release. Có thể phân tách theo các chiều có tập giá trị được kiểm soát như service, environment, region, version hoặc rollout stage.

Không đưa trace ID, user ID, request ID, commit SHA hay deployment ID có số lượng giá trị gần như vô hạn vào label của mọi time series. Việc đó tạo high cardinality, tăng chi phí lưu trữ và có thể làm hệ thống metrics quá tải.

Giữ các định danh chi tiết trong log, trace hoặc event store. Metrics chỉ cần chiều đủ thấp để so sánh và cảnh báo; khi phát hiện bất thường, dùng timestamp, version và environment để đi từ metric đến log/trace tương ứng.

### 6.3. Distributed trace context

Khi request đi qua nhiều service, truyền trace context theo chuẩn thống nhất, thường là W3C Trace Context với header `traceparent`. Các service tạo span con và giữ quan hệ parent/child để có thể xem đường đi của request.

Release ID hoặc deployment ID có thể được gắn làm resource/span attribute để hỗ trợ lọc trace theo phiên bản. Không dùng chúng thay cho trace ID. Cần kiểm soát kích thước attribute và tránh đưa dữ liệu cá nhân vào baggage hoặc header được truyền xuyên hệ thống nếu không cần thiết.

Một trace cho thấy request đã đi qua service nào và mất thời gian ở đâu. Release manifest cho biết code và artifact nào đang chạy. Kết hợp hai nguồn mới giúp xác định lỗi có liên quan đến một deployment cụ thể hay không.

## 7. Dùng OpenTelemetry và semantic attributes nhất quán

OpenTelemetry cung cấp API, SDK và giao thức để instrument ứng dụng, thu thập traces, metrics và logs. Khi dùng OpenTelemetry, hãy thống nhất resource attributes để các tín hiệu có thể được nhóm theo service và môi trường.

Một số thuộc tính thường hữu ích:

- `service.name`: tên service ổn định.
- `service.version`: phiên bản ứng dụng đang chạy.
- `deployment.environment.name`: tên môi trường như staging hoặc production.
- `service.instance.id`: định danh instance nếu cần phân biệt replica.

Các thuộc tính release ID, deployment ID, artifact digest và commit revision có thể được bổ sung theo schema nội bộ. Chọn tên thống nhất giữa ứng dụng, collector, dashboard và log pipeline.

Không để mỗi service tự đặt các tên khác nhau như release, releaseId, build, build_number hoặc deploy_version cho cùng một khái niệm. Tạo một mapping/schema chung và kiểm tra trong code review hoặc telemetry validation.

## 8. Promote cùng một artifact qua các môi trường

Một quy tắc quan trọng của khả năng truy vết là **build một lần, promote cùng artifact**:

1. Build artifact từ commit đã xác định.
2. Tính digest và lưu provenance/SBOM.
3. Triển khai artifact digest đó lên dev hoặc test.
4. Sau khi kiểm tra đạt, promote chính digest đó lên staging.
5. Sau approval, promote cùng digest lên production.
6. Mỗi môi trường tạo deployment record riêng, cùng tham chiếu release và artifact digest.

Không build lại từ source ở mỗi môi trường rồi chỉ giữ cùng version string. Build lại có thể thay đổi dependency, timestamp, base image hoặc tham số. Khi digest khác, đó là artifact khác và cần provenance, SBOM, scan cùng các kiểm tra tương ứng.

Ví dụ:

| Môi trường | Release ID | Artifact digest | Deployment ID |
| --- | --- | --- | --- |
| Test | rel-orders-2026-0042 | sha256:7b2d...e91a | deploy-test-184 |
| Staging | rel-orders-2026-0042 | sha256:7b2d...e91a | deploy-staging-184 |
| Production | rel-orders-2026-0042 | sha256:7b2d...e91a | deploy-production-221 |

Nếu production đang chạy digest khác staging, cần biết đó là chủ ý (hotfix, platform-specific image hoặc release khác) hay drift ngoài ý muốn. Không so sánh version string đơn thuần.

## 9. Liên kết cấu hình và hạ tầng với release

Artifact giống nhau vẫn có thể hoạt động khác nhau giữa môi trường vì cấu hình, secret reference, feature flag, network policy hoặc hạ tầng khác nhau.

Deployment record nên ghi các revision có thể kiểm tra:

- Config repository commit hoặc config bundle version.
- Kubernetes manifest/Helm chart revision.
- Infrastructure-as-code revision.
- Feature flag configuration version hoặc snapshot ID.
- Secret version reference nếu hệ thống hỗ trợ, không phải secret value.
- Cluster, namespace, region và deployment strategy.

Không đưa giá trị secret vào manifest hoặc telemetry. Chỉ ghi secret reference/version ID nếu policy cho phép, để có thể biết deployment đã dùng phiên bản credential nào mà không tiết lộ nội dung.

### 9.1. Desired state và actual state

Desired state là trạng thái pipeline hoặc hệ thống quản lý cấu hình yêu cầu. Actual state là những gì đang chạy thật.

Ví dụ pipeline yêu cầu:

- Image digest A.
- Ba replica.
- Config revision C.
- Feature flag ở mức 10%.

Nhưng cluster thực tế có một pod digest cũ, một pod mới chưa Ready và config revision khác. Nếu chỉ lưu lệnh deploy thành công, release record sẽ không phản ánh tình trạng thật.

Sau deployment, cần truy vấn platform để xác minh:

- Tất cả replica mong đợi đã chạy digest đúng chưa?
- Rollout đã hoàn tất chưa?
- Config/manifest revision thực tế là gì?
- Có instance cũ còn nhận traffic không?
- Feature flag hoặc routing đang ở tỷ lệ nào?
- Có drift so với desired state không?

Ghi lại kết quả xác minh và thời điểm. Khi hệ thống tự thay đổi state sau đó, có thể tạo drift event mới thay vì sửa lịch sử deployment ban đầu.

## 10. Event schema để nối các hệ thống

Một event nên có envelope chung để các hệ thống có thể lưu và truy vấn:

~~~json
{
  "event_id": "evt-01JCV...",
  "event_type": "deployment.verified",
  "occurred_at": "2026-11-18T08:20:00Z",
  "producer": "deployment-controller",
  "service": "orders-api",
  "release_id": "rel-orders-2026-0042",
  "deployment_id": "deploy-production-221",
  "environment": "production",
  "artifact": {
    "uri": "registry.example.com/commerce/orders-api",
    "digest": "sha256:7b2d...e91a"
  },
  "source": {
    "repository": "https://git.example.com/commerce/orders-api",
    "commit": "4f9a1c2d7b..."
  },
  "result": {
    "status": "verified",
    "checks_passed": 12,
    "checks_failed": 0
  }
}
~~~

Event này minh họa một deployment đã được xác minh. Trong hệ thống thực tế, schema cần định nghĩa trường bắt buộc, kiểu dữ liệu, phiên bản schema, timezone, quy tắc unique event ID và cách xử lý event đến trễ hoặc trùng lặp.

Event producer nên phát event sau khi hành động thực sự xảy ra. Ví dụ deployment controller phát deployment.verified sau khi đã truy vấn trạng thái và xác nhận rollout; pipeline không nên phát event “verified” chỉ vì lệnh deploy trả exit code 0.

### 10.1. Event ordering và idempotency

Event có thể đến hệ thống lưu trữ không theo đúng thứ tự vì queue, retry hoặc đồng hồ lệch. Hãy lưu:

- occurred_at: thời điểm sự kiện thực sự xảy ra theo producer.
- received_at: thời điểm hệ thống nhận event.
- event_id: định danh duy nhất.
- sequence hoặc revision nếu producer có thứ tự nội bộ.
- entity ID như release ID hoặc deployment ID.

Consumer cần xử lý event trùng lặp theo event ID hoặc idempotency key. Không giả định event đến sau luôn là trạng thái mới hơn nếu không có sequence/revision đáng tin cậy.

## 11. Truy vấn dấu vết trong điều tra sự cố

Một hệ thống truy vết hữu ích phải hỗ trợ đi từ nhiều điểm bắt đầu:

**Từ commit đến production**

1. Tìm pipeline run đã build commit.
2. Lấy artifact digest và provenance.
3. Tìm các deployment record tham chiếu digest.
4. Xem environment, region, rollout và trạng thái hiện tại.
5. Mở dashboard/log/trace trong khoảng thời gian deployment.

**Từ alert đến commit**

1. Xác định service, environment và thời điểm alert.
2. Tìm release/deployment gần nhất có ảnh hưởng.
3. Đối chiếu version/digest đang chạy.
4. Tìm commit và pipeline run đã tạo artifact.
5. So sánh thay đổi source, dependency, config và feature flag.

**Từ artifact đến mọi nơi đang chạy**

1. Tìm artifact digest trong registry hoặc release inventory.
2. Truy vấn deployment record theo digest.
3. Liệt kê environment, region, cluster và deployment ID.
4. Xác định nơi cần rollback, patch hoặc xác minh lại.

Các truy vấn này rất quan trọng khi phát hiện một dependency có lỗ hổng hoặc một artifact bị nghi ngờ. Nhóm có thể tìm chính xác phiên bản đang chạy thay vì chỉ tìm theo tên service.

## 12. Ví dụ điều tra một lỗi sau release

Giả sử sau khi phát hành orders-api 2.8.0, alert cho thấy tỷ lệ timeout khi tạo đơn tăng ở production.

Một quy trình điều tra:

1. Từ alert, xác định service orders-api, production, region và thời điểm bắt đầu.
2. Dashboard cho thấy timeout chỉ tăng trên service.version 2.8.0.
3. Log có release.id rel-orders-2026-0042 và deployment.id deploy-production-221.
4. Deployment record cho biết artifact digest sha256:7b2d...e91a, config revision a13d77... và cluster đích.
5. Release manifest liên kết digest với pipeline-1842 và commit 4f9a1c2d7b....
6. Trace cho thấy thời gian chờ tăng ở span gọi inventory-service; database của orders-api vẫn ổn định.
7. Nhóm kiểm tra thay đổi commit và cấu hình timeout, xác định một giá trị retry mới làm tăng thời gian chờ.
8. Nhóm dừng rollout hoặc rollback cấu hình/phiên bản theo phạm vi đã xác định.
9. Sau xử lý, metrics và smoke test xác minh tỷ lệ timeout trở về mức bình thường.
10. Incident record lưu release ID, digest, deployment ID, commit, trace mẫu và hành động đã thực hiện.

Không có một ID duy nhất nào trả lời toàn bộ câu hỏi. Giá trị đến từ việc mỗi hệ thống giữ đúng quan hệ và có thể truy vấn sang hệ thống kế tiếp.

## 13. Bảo vệ tính toàn vẹn và quyền riêng tư của bằng chứng

Dấu vết phát hành có giá trị cho kiểm toán và điều tra nên cần được bảo vệ:

- Lưu event và manifest trong kho có kiểm soát truy cập.
- Giữ lịch sử append-only hoặc audit trail khi trạng thái thay đổi.
- Ký hoặc xác minh provenance/attestation theo policy.
- Bảo vệ log khỏi sửa/xóa ngoài quyền được cấp.
- Đồng bộ thời gian hệ thống và dùng timestamp UTC.
- Quy định retention theo yêu cầu vận hành, bảo mật và tuân thủ.
- Phân quyền đọc log, trace, release metadata và incident record.
- Ghi nhận người hoặc workload identity đã tạo/duyệt/thay đổi deployment.

Không ghi secret, token, password, private key hoặc payload nhạy cảm vào manifest. Tránh đưa PII vào metric label, trace attribute hoặc correlation key. Nếu cần liên kết người dùng để điều tra, dùng định danh giả danh và giới hạn quyền truy cập.

Một digest chứng minh nội dung khớp với giá trị hash, nhưng không chứng minh ai đã tạo artifact. Chữ ký/attestation xác minh nguồn phát hành theo trust policy. Cả hai cần được dùng cùng provenance và quyền kiểm soát kho lưu trữ.

## 14. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ ghi branch name | Không xác định được source chính xác | Ghi full commit SHA |
| Dùng tag artifact làm định danh duy nhất | Tag có thể bị ghi đè | Ghi digest bất biến |
| Không ghi pipeline run ID | Không truy ngược được log, test và approval | Liên kết artifact với run ID |
| Bỏ qua workflow revision | Cùng commit nhưng build process khác nhau | Ghi revision của pipeline/template |
| Dùng cùng ID cho release và deployment | Không phân biệt một release với nhiều lần triển khai | Dùng release ID và deployment ID riêng |
| Chỉ ghi lệnh deploy thành công | Không biết trạng thái thực tế trong cluster | Xác minh desired/actual state sau deploy |
| Build lại ở từng môi trường | Artifact giữa staging và production có thể khác | Promote cùng digest |
| Không gắn version vào telemetry | Không phân biệt lỗi theo release | Gắn service version và deployment context |
| Đưa trace ID vào metric label | Cardinality tăng rất nhanh | Giữ trace ID trong log/trace |
| Event không có ID duy nhất | Retry tạo bản ghi trùng hoặc sai thứ tự | event_id, idempotency và revision |
| Ghi secret trong manifest/log | Lộ credential qua bằng chứng | Chỉ lưu secret reference an toàn |
| Không lưu lịch sử rollback | Khó biết ai đổi gì và khi nào | Ghi rollback event và incident link |

## 15. Checklist xây dựng dấu vết phát hành

**Source và pipeline**

- [ ] Ghi repository URL, ref và full commit SHA.
- [ ] Ghi pull request/change record liên quan theo policy.
- [ ] Ghi pipeline run ID, job ID và workflow revision.
- [ ] Ghi builder identity, toolchain và kết quả quality gate.

**Artifact và bằng chứng chuỗi cung ứng**

- [ ] Artifact có URI, version và digest bất biến.
- [ ] Artifact liên kết với pipeline run đã tạo nó.
- [ ] Provenance, SBOM, signature và scan report có tham chiếu truy cập được.
- [ ] Digest được xác minh trước khi promote/deploy.

**Deployment và môi trường**

- [ ] Mỗi lần triển khai có deployment ID riêng.
- [ ] Deployment tham chiếu release ID và artifact digest.
- [ ] Ghi environment, region, cluster, namespace và config revision.
- [ ] Xác minh desired state khớp actual state.
- [ ] Ghi approval, rollout stage, kết quả smoke test và rollback nếu có.

**Runtime observability**

- [ ] Logs có timestamp, service, environment và release/deployment context.
- [ ] Traces có trace/span ID và context được truyền xuyên service.
- [ ] Metrics phân tách theo service/environment/version với cardinality được kiểm soát.
- [ ] Có correlation ID cho luồng nghiệp vụ cần truy vết.
- [ ] Alert và incident liên kết được với release/deployment liên quan.

**Bảo vệ bằng chứng**

- [ ] Timestamp dùng UTC và hệ thống đồng bộ thời gian.
- [ ] Event có ID duy nhất và consumer xử lý duplicate.
- [ ] Manifest/event có schema và version.
- [ ] Kho bằng chứng có access control, retention và audit trail.
- [ ] Không lưu secret hoặc PII không cần thiết trong telemetry.

## Kết luận

Liên kết commit, pipeline, artifact và môi trường tạo ra một dấu vết xuyên suốt từ thay đổi source đến hành vi runtime. Release ID, deployment ID, commit SHA và artifact digest giúp xác định các đối tượng; event, manifest, provenance và telemetry lưu quan hệ giữa chúng. Logs, metrics và traces bổ sung bằng chứng về điều gì đã xảy ra sau khi artifact được triển khai.

Một hệ thống truy vết tốt phải hỗ trợ đi từ commit đến mọi môi trường đang chạy artifact, hoặc từ alert đến deployment và source change liên quan. Hãy promote cùng artifact digest, ghi nhận cả desired state lẫn actual state, dùng schema nhất quán, kiểm soát cardinality và bảo vệ dữ liệu telemetry. Khi đó, nhóm có thể điều tra sự cố, đánh giá tác động của lỗ hổng, xác minh release và rollback dựa trên bằng chứng thay vì suy đoán.
