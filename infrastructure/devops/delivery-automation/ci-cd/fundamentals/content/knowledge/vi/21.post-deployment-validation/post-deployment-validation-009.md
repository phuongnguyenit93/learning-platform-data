# Lưu bằng chứng xác nhận kết quả triển khai

Một pipeline báo deploy thành công chỉ cho biết công cụ triển khai đã hoàn tất các bước mà nó được giao. Điều đó chưa chứng minh phiên bản mới đang phục vụ traffic đúng, các dependency hoạt động, dữ liệu không bị sai lệch hoặc người dùng có thể hoàn thành luồng nghiệp vụ quan trọng.

Sau khi triển khai, hệ thống cần thu thập bằng chứng để trả lời những câu hỏi cụ thể: artifact nào đã được đưa lên môi trường nào, ai hoặc workload nào thực hiện, rollout kết thúc ra sao, các kiểm tra sau deploy có đạt không, trong khoảng thời gian nào và dữ liệu nào hỗ trợ kết luận đó. Bằng chứng phải liên kết được với release và deployment cụ thể, có nguồn gốc rõ, được lưu đủ lâu và có thể kiểm tra lại khi xảy ra sự cố.

Trong CI/CD, bằng chứng sau triển khai là một phần của hồ sơ phát hành. Nó hỗ trợ quyết định tiếp tục rollout, dừng, rollback hoặc đánh dấu release hoàn tất; đồng thời giúp nhóm điều tra sự cố và chứng minh điều gì đã thực sự xảy ra.

## 1. Bằng chứng triển khai chứng minh điều gì?

Bằng chứng triển khai (deployment evidence) là dữ liệu được thu thập từ các hệ thống liên quan để xác nhận một deployment đã thực hiện điều gì và kết quả quan sát được sau đó.

Một hồ sơ có thể chứng minh:

- Artifact có định danh nào đã được triển khai.
- Artifact đó thuộc source revision và build run nào.
- Môi trường, cluster, namespace hoặc service nào nhận thay đổi.
- Deployment controller đã tạo revision hoặc rollout nào.
- Những instance nào đã chạy phiên bản mới.
- Health check, smoke test hoặc synthetic check nào đã chạy và kết quả.
- Các chỉ số quan trọng trước và sau deploy thay đổi ra sao.
- Migration hoặc data job có hoàn tất và đạt kiểm tra nhất quán không.
- Ai hoặc workload nào đã thực hiện hành động và thời điểm nào.
- Quyết định cuối cùng là success, failed, degraded, rolled back hay inconclusive.

Bằng chứng không nhất thiết chứng minh mọi khía cạnh của hệ thống đều đúng. Một smoke test thành công chỉ chứng minh những request và assertion mà test đã thực hiện trong khoảng thời gian đó. Một rollout hoàn tất chỉ chứng minh controller đạt trạng thái rollout theo cấu hình, không chứng minh mọi luồng nghiệp vụ đều hoạt động.

Vì vậy, mỗi evidence item cần ghi rõ phạm vi, nguồn và giới hạn của kết luận. Tránh ghi "production healthy" nếu thực tế chỉ có một endpoint trả HTTP 200.

## 2. Phân biệt log, kết quả kiểm tra và evidence record

Các dữ liệu này có liên quan nhưng không giống nhau.

| Loại dữ liệu | Mục đích | Ví dụ |
|---|---|---|
| Execution log | Ghi lại tiến trình và thông báo của công cụ | Output của deploy command, controller log |
| Test result | Ghi nhận một phép kiểm tra và assertion | Smoke test pass, contract test report |
| Telemetry | Quan sát trạng thái và hành vi hệ thống | Metric, log ứng dụng, distributed trace |
| Evidence record | Liên kết dữ liệu với một deployment và diễn giải điều dữ liệu chứng minh | Release ID, digest, target, check result, time window, source reference |

Log có thể rất dài và chứa thông tin không liên quan. Test report có thể không cho biết nó chạy trên artifact nào hoặc môi trường nào. Metric có thể phản ánh hệ thống nhưng thiếu liên kết với deployment vừa thực hiện.

Evidence record đóng vai trò chỉ mục có cấu trúc. Nó tham chiếu tới log, report, metric query, trace hoặc ảnh chụp trạng thái cần thiết, đồng thời ghi lại ngữ cảnh và kết quả. Không cần sao chép toàn bộ telemetry vào một file evidence; nên lưu bản tóm tắt và liên kết tới nguồn lưu trữ có vòng đời phù hợp.

Một dòng "deploy succeeded" trong CI log không đủ thay thế evidence record. Nó thường thiếu artifact digest, target identity, post-deploy observations và nguồn kiểm chứng độc lập.

## 3. Liên kết evidence với đúng release và artifact

Điều đầu tiên của một evidence bundle là xác định chính xác đối tượng đang được xác nhận.

Các trường nhận dạng thường cần:

- Service hoặc application name.
- Release ID và version.
- Artifact name và digest.
- Container image repository và digest nếu có.
- Source repository, commit SHA và tag.
- Build run ID và pipeline definition revision.
- SBOM hoặc provenance reference nếu có.
- Deployment request ID và deployment run ID.

Nên dùng digest hoặc định danh bất biến để liên kết artifact. Tag có thể thay đổi, nên chỉ ghi image tag như latest hoặc stable không đủ để chứng minh nội dung đã chạy. Với JAR hoặc ZIP, lưu checksum theo thuật toán đã thống nhất. Với image đa kiến trúc, ghi digest của manifest index và thông tin platform image khi cần.

Nếu cùng một version được publish lại với nội dung khác, evidence của lần deploy trước có thể bị hiểu nhầm. Vì vậy, release chính thức nên bất biến; một nội dung mới cần version hoặc digest mới.

## 4. Xác định target và trạng thái deployment

Evidence phải xác định môi trường mà deployment thực sự thay đổi, không chỉ môi trường mà người vận hành định triển khai.

Tùy nền tảng, target identity có thể gồm:

- Environment name: development, staging hoặc production.
- Cloud account, subscription hoặc project ID.
- Region hoặc zone.
- Cluster endpoint hoặc cluster identity.
- Namespace, tenant hoặc resource group.
- Service, workload, deployment name.
- Deployment controller revision, rollout ID hoặc release history entry.
- Resource UID hoặc generation nếu nền tảng cung cấp.

Tên context hoặc namespace có thể được đặt tùy ý. Khi yêu cầu truy vết cao, cần ghi identifier đáng tin cậy từ API hoặc cloud account thay vì chỉ ghi nhãn thân thiện.

Nên lưu cả trạng thái trước và sau deploy. Ví dụ: image digest cũ, deployment generation cũ, số replica trước; sau đó là digest mới, generation mới, số replica ready và thời điểm rollout hoàn tất. Điều này giúp phân biệt một deployment thực sự thay đổi phiên bản với một lần chạy lại pipeline không tạo thay đổi.

## 5. Xác định danh tính thực hiện và thời gian

Một hồ sơ phát hành cần cho biết ai hoặc workload nào đã thực hiện hành động. Với CI/CD, nên lưu principal hoặc workload identity, role/service account, workflow, job và run ID.

Các trường hữu ích:

- Actor type: human hoặc workload.
- Principal identifier hoặc service account.
- Repository và workflow/pipeline.
- Trigger event, branch hoặc tag.
- Approval reference và người phê duyệt nếu có.
- Deployment job ID.
- Thời điểm bắt đầu, kết thúc và các mốc quan trọng.

Dùng timestamp theo UTC và định dạng nhất quán, chẳng hạn RFC 3339. Hệ thống runner, cluster và telemetry backend cần đồng bộ đồng hồ để so sánh sự kiện. Nếu clock skew lớn, thứ tự log có thể bị hiểu sai.

Không lưu access token, private key hoặc secret value vào evidence. Chỉ lưu định danh principal, role, credential issuer hoặc secret reference cần thiết. Nếu cần điều tra quyền, tham chiếu audit event của nhà cung cấp.

## 6. Thiết kế evidence bundle

Một deployment evidence bundle là tập hợp các record và nguồn dữ liệu gắn với cùng một deployment request. Có thể tổ chức thành các nhóm:

| Nhóm | Nội dung |
|---|---|
| Identity | Service, release, artifact, source revision, build run |
| Target | Environment, account, cluster, namespace, workload |
| Execution | Deployment run, controller revision, start/end time, actor |
| Pre-deploy snapshot | Trạng thái trước deploy, version hiện tại, health baseline |
| Rollout evidence | Replica/instance readiness, rollout status, events |
| Post-deploy checks | Smoke, synthetic, API, contract hoặc business checks |
| Observability | Metric window, log query, trace reference, alert state |
| Data evidence | Schema version, migration result, backfill/reconciliation |
| Decision | Pass, fail, degraded, rollback, waiver hoặc inconclusive |
| Integrity | Digest, signature, evidence schema version, storage reference |

Không phải deployment nào cũng cần đủ mọi nhóm. Một service không dùng database thì không có data migration evidence. Một deployment tài liệu tĩnh có thể chỉ cần artifact identity, CDN verification và smoke test. Chọn evidence theo rủi ro, nhưng các trường nhận dạng và kết luận cần nhất quán.

Một bundle tốt có thể được đọc bởi con người và xử lý bởi công cụ tự động. Tên file có thể thân thiện, nhưng bên trong cần có schema và identifier ổn định.

## 7. Thu thập trạng thái trước và sau deploy

So sánh trước/sau giúp xác định deployment tạo ra thay đổi nào và có dấu hiệu bất thường nào xuất hiện sau đó.

Trước deploy, có thể ghi:

- Artifact digest và version đang chạy.
- Số instance/replica healthy.
- Error rate, latency và throughput baseline.
- Trạng thái alert và incident.
- Schema version và migration state.
- Resource capacity hoặc saturation.
- Các deployment đang chạy hoặc thay đổi gần đây.

Sau deploy, thu thập cùng loại thông tin trong một cửa sổ quan sát phù hợp:

- Digest/revision thực tế của workload.
- Replica mới ready và instance cũ đã được thay thế.
- Error rate, latency, throughput và saturation.
- Health check và smoke test result.
- Alert mới phát sinh.
- Database/schema state và migration result.
- Consumer lag hoặc queue backlog nếu có.

Baseline cần có cửa sổ thời gian rõ ràng. Ví dụ, so sánh 15 phút trước deploy với 15 phút sau khi rollout ổn định. Nếu lưu chỉ một giá trị trung bình mà không có time range, nhóm khó biết dữ liệu có đại diện cho giai đoạn deployment hay không.

Tránh kết luận nguyên nhân chỉ từ việc một metric tăng sau deploy. Traffic, lịch batch, sự cố dependency hoặc thay đổi hạ tầng khác cũng có thể ảnh hưởng. Evidence nên ghi quan sát và mốc thời gian; việc quy kết nguyên nhân cần thêm phân tích.

## 8. Evidence về rollout và instance thực tế

Deployment controller có thể báo rollout complete nhưng evidence nên lưu các chi tiết đủ để xác minh phiên bản thực tế.

Với Kubernetes, có thể thu thập:

- Deployment name, namespace và UID.
- Generation và observedGeneration.
- Replica desired, updated, ready và available.
- Pod owner references và imageID thực tế.
- Revision hoặc ReplicaSet mới.
- Events liên quan tới rollout.
- Thời điểm rollout bắt đầu và hoàn tất.

Ví dụ các lệnh chỉ đọc:

```bash
kubectl rollout status deployment/orders-api -n production
kubectl get deployment orders-api -n production -o wide
kubectl get pods -n production -l app=orders-api -o wide
```

Các lệnh này là ví dụ; label selector và tên tài nguyên phải phù hợp với ứng dụng. Nếu cần chứng minh image digest đang chạy, cần truy xuất imageID từ Pod status hoặc API tương ứng, vì trường image trong Pod spec có thể chứa tag.

Không lưu toàn bộ object dump nếu nó chứa environment variables hoặc thông tin nhạy cảm. Hãy lọc các trường cần thiết, che dữ liệu nhạy cảm và giữ lại resource UID/revision để có thể tra cứu chi tiết khi được phép.

## 9. Kiểm tra sau deploy và lưu kết quả

Evidence có thể đến từ nhiều loại kiểm tra. Mỗi check cần có tên, mục tiêu, nguồn chạy, target, thời điểm, kết quả và phạm vi assertion.

**Readiness/liveness:** xác nhận instance mới đã sẵn sàng theo health contract của ứng dụng. Readiness cho biết instance có thể nhận traffic; liveness hỗ trợ phát hiện process bị kẹt. Không dùng liveness thay cho kiểm tra nghiệp vụ.

**Smoke test:** thực hiện một tập request nhỏ để xác nhận luồng cốt lõi hoạt động, ví dụ health endpoint, đăng nhập test hoặc đọc một resource.

**Synthetic check:** mô phỏng hành động của người dùng từ một điểm quan sát bên ngoài, có thể chạy từ nhiều vùng hoặc network path khác nhau.

**Contract/API check:** xác minh endpoint, status, schema và hành vi tích hợp sau deploy.

**Business check:** kiểm tra một kết quả nghiệp vụ có ý nghĩa, ví dụ tạo một đơn test và xác minh trạng thái cuối cùng trong hệ thống kiểm thử.

Mỗi kết quả cần chỉ rõ test có chạy trên phiên bản mới hay không. Một probe được gửi tới load balancer có thể vô tình đi tới instance cũ trong rolling deployment. Nếu cần xác nhận từng instance hoặc từng revision, phải kiểm tra theo workload identity hoặc deployment label phù hợp.

## 10. Evidence về metrics và SLO

Metrics cho biết hệ thống vận hành ra sao trong một khoảng thời gian. Sau deploy, nên lưu query và cửa sổ quan sát để có thể tái tạo kết quả.

Các chỉ số thường dùng:

- Request rate hoặc throughput.
- Error rate theo status class hoặc loại lỗi.
- Latency percentile, ví dụ p50, p95 và p99.
- CPU, memory, disk và network saturation.
- Queue depth, consumer lag và retry rate.
- Database connection, query latency, lock wait và replication lag.
- Cache hit ratio hoặc eviction rate.
- Số instance ready và restart count.

Một evidence item có thể ghi query reference, metric name, label filters, start/end time, aggregation và threshold. Không chỉ lưu ảnh chụp dashboard vì hình ảnh khó xử lý tự động và có thể không cho biết truy vấn nào đã tạo ra nó.

Nếu deployment có SLO hoặc error budget policy, lưu kết quả đánh giá liên quan. Ví dụ, error rate trong cửa sổ 10 phút không vượt ngưỡng đã định và p95 latency không tăng quá mức cho phép so với baseline.

Ngưỡng cần được định nghĩa trước release hoặc trong policy version được quản lý. Không thay ngưỡng sau khi thấy kết quả xấu chỉ để biến deployment thành pass. Nếu metric backend không truy cập được, kết quả nên là inconclusive thay vì pass.

## 11. Evidence từ logs và distributed traces

Log và trace hỗ trợ điều tra lỗi mà metric tổng hợp không giải thích được.

Evidence record có thể lưu:

- Log query hoặc saved search identifier.
- Khoảng thời gian truy vấn.
- Service, environment và version filter.
- Correlation ID hoặc trace ID của các smoke test.
- Số lỗi theo nhóm hoặc một số mẫu đã được làm sạch.
- Link tới trace đại diện cho request thất bại hoặc chậm.
- Parser/query version dùng để tổng hợp kết quả.

Không nhúng hàng triệu dòng log vào bundle. Lưu summary và tham chiếu tới hệ thống log có quyền truy cập, retention và audit phù hợp. Nếu log có PII, token hoặc payload nhạy cảm, phải áp dụng masking và access control.

Với trace, cần gắn deployment version hoặc service version vào resource attributes để lọc request đi qua phiên bản mới. Nếu không có thuộc tính này, trace sau deploy có thể trộn lẫn traffic của nhiều revision và khó diễn giải.

## 12. Evidence về migration và dữ liệu

Nếu deployment đi kèm thay đổi schema hoặc data backfill, evidence cần ghi riêng trạng thái của phần dữ liệu.

Các trường hữu ích:

- Database identity hoặc logical target đã được làm mờ theo policy.
- Schema version trước và sau migration.
- Migration tool và migration run ID.
- Danh sách migration được áp dụng.
- Thời điểm bắt đầu/kết thúc.
- Lock wait, duration và lỗi.
- Số bản ghi đã đọc, cập nhật, bỏ qua hoặc lỗi.
- Checkpoint cuối và trạng thái resumable job.
- Reconciliation result giữa cấu trúc cũ và mới.
- Replication lag hoặc các ngưỡng vận hành liên quan.

Không ghi connection string hoặc database password. Có thể ghi database alias và schema identifier thay vì endpoint nhạy cảm.

Migration status "success" chỉ chứng minh tool báo hoàn tất. Nếu thay đổi dữ liệu, cần thêm kiểm tra số lượng, constraint, checksum hoặc business invariant phù hợp. Ví dụ, sau backfill có thể xác minh không còn bản ghi hợp lệ nào thiếu giá trị đích và tổng số record không thay đổi ngoài dự kiến.

Nếu migration chưa hoàn tất nhưng ứng dụng đã deploy, evidence cần ghi trạng thái partial/in progress và điều kiện tiếp tục. Không đánh dấu release hoàn tất chỉ vì ứng dụng đã khởi động.

## 13. Xác định cửa sổ quan sát và tiêu chí kết luận

Một deployment không thể được xác nhận chỉ bằng một request ngay sau khi rollout. Có thể cần một cửa sổ quan sát để phát hiện lỗi xuất hiện khi traffic tăng, cache lạnh, background worker chạy hoặc batch bắt đầu.

Cửa sổ có thể gồm:

1. **Ngay sau rollout:** kiểm tra controller, readiness và smoke test.
2. **Sau khi nhận traffic:** quan sát error rate, latency và dependency.
3. **Sau một chu kỳ nghiệp vụ:** xác minh worker, schedule hoặc batch job quan trọng.
4. **Sau khoảng ổn định đã định:** quyết định rollout tiếp tục, dừng hay rollback.

Thời lượng phụ thuộc hệ thống. Service có traffic liên tục có thể cần một cửa sổ vài phút; job chạy theo lịch hàng giờ hoặc hàng ngày có thể cần theo dõi tới chu kỳ tiếp theo. Không chọn thời lượng tùy tiện chỉ để pipeline kết thúc nhanh.

Tiêu chí kết luận nên được xác định trước:

- Success: tất cả check bắt buộc đạt và không có ngưỡng vận hành bị vi phạm.
- Degraded: chức năng chính hoạt động nhưng một số chỉ số hoặc check không đạt ngưỡng cảnh báo.
- Failed: có lỗi chức năng hoặc vi phạm ngưỡng dừng.
- Rolled back: phiên bản trước đã được khôi phục và kiểm tra sau rollback đạt.
- Inconclusive: thiếu dữ liệu hoặc nguồn quan sát không đủ để kết luận.

Nếu cửa sổ quan sát chưa kết thúc, trạng thái nên là monitoring/in progress. Không gán success quá sớm rồi mới phát hiện lỗi sau đó mà không cập nhật release record.

## 14. Evidence cho progressive delivery và canary

Với canary hoặc progressive rollout, evidence cần gắn kết quả với từng phase và cohort traffic.

Ví dụ:

- 5% traffic tới revision mới.
- Quan sát error rate, latency và business metric.
- Nếu đạt ngưỡng, tăng lên 25%, 50%, rồi 100%.
- Nếu vi phạm ngưỡng, dừng rollout và thực hiện rollback hoặc giữ traffic ở mức hiện tại theo policy.

Mỗi phase nên lưu:

- Revision và digest đang thử nghiệm.
- Tỷ lệ traffic hoặc số instance.
- Start/end time.
- Metric window và baseline/control cohort.
- Check result và threshold.
- Quyết định promote, pause hoặc rollback.
- Actor hoặc automation policy đưa ra quyết định.

Nếu có thể, so sánh canary với control group cùng thời điểm để giảm ảnh hưởng của thay đổi traffic chung. Ghi rõ cách chia cohort và cách tính metric. Nếu sample quá nhỏ, kết quả không đủ tin cậy để kết luận.

Một canary thành công ở 5% traffic không tự chứng minh release an toàn ở 100%. Evidence cần lưu từng phase và trạng thái cuối cùng.

## 15. Tổ chức evidence record có cấu trúc

Evidence record nên có schema version để consumer có thể đọc và nâng cấp theo thời gian. Ví dụ JSON minh họa:

```json
{
  "schemaVersion": "1.0",
  "deployment": {
    "id": "deploy-2026-00421",
    "service": "orders-api",
    "environment": "production",
    "target": {
      "account": "prod-account",
      "cluster": "prod-cluster-a",
      "namespace": "orders"
    },
    "actor": {
      "type": "workload",
      "principal": "ci/orders-release"
    },
    "startedAt": "2026-11-18T08:00:00Z",
    "completedAt": "2026-11-18T08:07:30Z"
  },
  "release": {
    "version": "3.8.1",
    "sourceCommit": "a1b2c3d4",
    "buildRun": "build-1842",
    "artifact": {
      "uri": "registry.example.com/orders-api",
      "digest": "sha256:..."
    }
  },
  "rollout": {
    "revision": "42",
    "desiredReplicas": 6,
    "readyReplicas": 6,
    "result": "complete"
  },
  "checks": [
    {
      "name": "smoke-api",
      "result": "pass",
      "startedAt": "2026-11-18T08:08:00Z",
      "completedAt": "2026-11-18T08:08:12Z",
      "evidenceRef": "ci://reports/deploy-2026-00421/smoke"
    }
  ],
  "decision": {
    "status": "success",
    "evaluatedAt": "2026-11-18T08:25:00Z",
    "policyVersion": "production-post-deploy-v3"
  }
}
```

Các giá trị là minh họa. Schema thực tế cần quy định field bắt buộc, kiểu dữ liệu, enum trạng thái, timezone, URI scheme và cách biểu diễn giá trị không có. Không dùng chuỗi rỗng để thay thế mọi trạng thái thiếu dữ liệu; phân biệt not_applicable, not_collected, unavailable và failed.

Evidence record nên tham chiếu tới report hoặc telemetry gốc bằng URI ổn định. Nếu nguồn có thời hạn lưu ngắn hơn evidence record, liên kết có thể hỏng; cần policy retention đồng bộ hoặc snapshot dữ liệu tối thiểu cần thiết.

## 16. Lưu evidence theo bundle và cấu trúc thư mục

Với hệ thống lưu file, có thể tổ chức bundle theo deployment ID:

```text
evidence/
└── production/
    └── deploy-2026-00421/
        ├── manifest.json
        ├── rollout-summary.json
        ├── checks/
        │   ├── smoke-api.json
        │   └── synthetic-check.json
        ├── telemetry/
        │   ├── metrics-summary.json
        │   └── alert-state.json
        ├── data/
        │   └── migration-summary.json
        ├── references.json
        └── signatures/
            └── manifest.sig
```

Đây là cách tổ chức logic, không bắt buộc dùng đúng cấu trúc này. Một số hệ thống lưu record trong database và report trong object storage; một số dùng release management hoặc deployment platform làm index.

Manifest nên là entry point duy nhất để tìm các evidence item. Tên file cần ổn định, có deployment ID và schema version. Không dựa vào tên run hiển thị có thể thay đổi.

Nếu bundle gồm nhiều file, manifest cần ghi digest của từng file hoặc dùng một manifest được ký để phát hiện file bị thay thế. Khi bổ sung evidence sau đó, cần tạo revision mới hoặc append-only event; không âm thầm sửa file đã được ký mà không ghi lại lịch sử.

## 17. Bảo vệ tính toàn vẹn và nguồn gốc evidence

Evidence có giá trị khi người đọc tin rằng nó đến từ nguồn được xác định và chưa bị sửa trái phép.

Các biện pháp:

**Digest/checksum:** tính hash cho manifest và các file evidence để phát hiện thay đổi nội dung.

**Signature:** ký manifest hoặc attestation bằng danh tính workload được quản lý. Consumer xác minh chữ ký và danh tính signer.

**Immutable storage:** dùng object lock, retention lock hoặc append-only storage nếu yêu cầu kiểm toán cần chống sửa/xóa trong một khoảng thời gian.

**Audit log:** ghi ai đã tạo, đọc, sửa metadata, tải hoặc xóa evidence.

**Source references:** liên kết report với hệ thống đã tạo nó, bao gồm run ID, query ID hoặc event ID.

Một hash được lưu cạnh file trong cùng một vùng có quyền ghi không đủ chống lại người có thể thay cả file và hash. Với yêu cầu cao, chữ ký cần được bảo vệ bằng key hoặc workload identity tách khỏi quyền chỉnh sửa bundle; storage cần audit và retention phù hợp.

Chữ ký chứng minh dữ liệu được ký bởi một identity và nội dung không đổi kể từ khi ký. Nó không tự chứng minh phép kiểm tra là đúng hoặc nguồn telemetry không bị thao túng. Cần tin cậy cả quy trình tạo evidence và hệ thống cung cấp dữ liệu.

## 18. Chống sửa đổi và lịch sử bổ sung evidence

Một deployment record có thể cần cập nhật khi cửa sổ quan sát kết thúc hoặc khi có kết quả bổ sung. Cần phân biệt cập nhật trạng thái với viết lại lịch sử.

Có thể dùng mô hình append-only:

- Tạo record ban đầu với trạng thái monitoring.
- Thêm event rollout-completed.
- Thêm event smoke-check-passed.
- Thêm metric-window-evaluated.
- Thêm decision-success hoặc decision-rollback.
- Mỗi event có timestamp, actor, source reference và digest.

Manifest hiện tại có thể tổng hợp trạng thái mới nhất, nhưng event history vẫn được giữ để biết trạng thái đã thay đổi như thế nào. Nếu phải sửa sai một event, thêm correction event có liên kết tới event cũ và lý do; không xóa lịch sử mà không để dấu vết.

Với kho object storage không hỗ trợ append, có thể tạo phiên bản bundle mới với revision number và giữ phiên bản trước theo retention. Cần ghi rõ revision nào là bản hiện hành và ai tạo revision đó.

## 19. Quyền truy cập và phân loại dữ liệu

Evidence có thể chứa topology nội bộ, tên cluster, endpoint, thông tin người phê duyệt, log trích đoạn hoặc dữ liệu người dùng. Không nên coi mọi evidence đều công khai cho tất cả developer.

Nên phân quyền theo nhu cầu:

- CI publisher có quyền tạo evidence cho deployment của mình.
- Release manager có quyền đọc bundle và kết quả gate.
- On-call có quyền đọc evidence cần cho incident.
- Auditor có quyền đọc lịch sử và audit theo phạm vi.
- Cleanup service có quyền xóa khi policy cho phép, nhưng không sửa nội dung release record.

Áp dụng phân loại dữ liệu và masking:

- Không lưu token, password, private key hoặc raw secret.
- Loại bỏ hoặc làm mờ PII trong log và test report.
- Không lưu request/response body đầy đủ nếu không cần.
- Hạn chế endpoint nội bộ và topology chi tiết theo vai trò.
- Dùng secret reference hoặc principal ID thay vì credential.
- Ghi lại truy cập và tải dữ liệu nhạy cảm.

Nếu cần giữ payload để điều tra, phải có lý do, phạm vi truy cập, thời hạn và cơ chế xóa phù hợp. Evidence cần đủ để xác minh nhưng không trở thành nơi tập trung dữ liệu nhạy cảm.

## 20. Retention và vòng đời evidence

Thời hạn giữ evidence nên dựa trên yêu cầu vận hành, thời gian hỗ trợ release, điều tra incident và kiểm toán.

Có thể phân loại:

| Loại evidence | Mục đích | Chính sách lưu giữ |
|---|---|---|
| Deployment manifest và decision | Truy vết release | Theo vòng đời hỗ trợ và audit policy |
| Smoke/synthetic report | Xác minh chức năng | Theo thời gian cần điều tra và so sánh |
| Metric summary | So sánh trước/sau | Giữ summary lâu hơn raw metric nếu cần |
| Raw logs/traces | Điều tra chi tiết | Theo retention của observability platform |
| Migration/backfill report | Chứng minh trạng thái dữ liệu | Theo yêu cầu dữ liệu và kiểm toán |
| Approval/audit events | Truy vết quyết định | Theo policy quản trị |
| Temporary debug output | Chẩn đoán ngắn hạn | Xóa sớm sau khi hết nhu cầu |

Không nên giữ mọi raw log vô thời hạn. Cũng không nên xóa evidence của release còn được triển khai hoặc nằm trong thời gian hỗ trợ. Có thể giữ summary và digest lâu hơn dữ liệu chi tiết, miễn là liên kết và chính sách được mô tả rõ.

Cleanup cần kiểm tra deployment và release reference trước khi xóa. Với hold phục vụ incident hoặc audit, cần cơ chế legal/audit hold có owner và thời hạn rà soát.

## 21. Khi nguồn evidence không khả dụng

Một số lần triển khai có thể thành công nhưng metric backend, log service hoặc test endpoint tạm thời không truy cập được. Pipeline cần phân biệt trạng thái hệ thống với khả năng thu thập bằng chứng.

Ví dụ:

- Rollout controller báo hoàn tất, nhưng metric backend timeout.
- Smoke test không chạy vì test runner không khởi động.
- Synthetic provider không có dữ liệu trong cửa sổ quan sát.
- Audit API trả lỗi nên không xác minh được actor.
- Migration job thành công nhưng report upload thất bại.

Không tự động coi mọi trường hợp này là deployment failure, nhưng cũng không thể kết luận success nếu evidence bắt buộc bị thiếu. Dùng trạng thái inconclusive hoặc evidence-pending, rồi retry việc thu thập theo thời hạn policy.

Nếu evidence bắt buộc là điều kiện promote traffic hoặc đánh dấu release hoàn tất, gate nên giữ trạng thái chờ hoặc dừng. Nếu evidence chỉ mang tính thông tin, có thể tiếp tục theo policy nhưng cần ghi rõ item unavailable và lý do.

Không giả mạo kết quả, tái sử dụng report của deployment trước hoặc đánh dấu check pass khi nó chưa chạy.

## 22. Evidence và quyết định tiếp tục, dừng hoặc rollback

Evidence chỉ hữu ích khi được kết nối với một quyết định có quy tắc.

Ví dụ policy:

- Nếu rollout không đạt số replica ready trong timeout, dừng rollout.
- Nếu smoke test quan trọng thất bại, không tăng traffic.
- Nếu error rate hoặc latency vượt ngưỡng trong cửa sổ quan sát, pause hoặc rollback theo policy.
- Nếu migration reconciliation không đạt, không bật read path mới.
- Nếu evidence bắt buộc không thu thập được, giữ trạng thái inconclusive.
- Nếu mọi check bắt buộc đạt trong cửa sổ đã định, cho phép promote hoặc đánh dấu release complete.

Decision record cần ghi policy version, ngưỡng, cửa sổ quan sát, evidence item đã dùng và kết quả. Nếu con người override quyết định tự động, lưu actor, lý do, phạm vi và thời hạn waiver.

Không để một dashboard màu xanh là điều kiện duy nhất. Cần lưu kết quả có thể tái tạo: metric query, thời gian, threshold và giá trị đánh giá.

## 23. Ví dụ: thu thập trạng thái Kubernetes

Một bước thu thập có thể lấy trạng thái rollout, Deployment và Pod rồi chọn các trường cần thiết để tạo JSON summary.

Các lệnh chỉ đọc minh họa:

```bash
kubectl rollout status deployment/orders-api -n production
kubectl get deployment orders-api -n production -o json
kubectl get pods -n production -l app=orders-api -o json
```

Pipeline có thể parse JSON output và tạo summary gồm:

- Deployment UID, generation và observedGeneration.
- Desired, updated, ready và available replicas.
- Pod name, phase và trạng thái Ready của từng container.
- ImageID thực tế của từng container.
- Owner reference và ReplicaSet revision.
- Timestamp thu thập và cluster identity.

Cần kiểm tra exit code của từng lệnh, xử lý trường hợp field không tồn tại và tính trạng thái Ready chính xác theo tất cả container cần thiết. Không nên xem summary là kết luận cuối cùng nếu chưa so sánh imageID với digest mong muốn và chưa chạy post-deploy checks.

Nếu API trả về lỗi, không tạo summary giả với giá trị mặc định như zero hoặc success. Ghi rõ evidence item là unavailable hoặc failed và nguyên nhân.

## 24. Ví dụ pipeline thu thập và lưu evidence

Một pipeline khái niệm có thể chia thành các giai đoạn:

```yaml
jobs:
  deploy:
    steps:
      - deploy artifact by immutable digest
      - capture deployment revision and target identity

  verify:
    needs: [deploy]
    steps:
      - wait for rollout completion
      - run smoke and synthetic checks
      - collect metric window and alert state
      - collect migration and data verification result

  assemble-evidence:
    needs: [verify]
    steps:
      - create deployment evidence manifest
      - calculate digest for each evidence file
      - sign manifest with workload identity
      - upload bundle to controlled evidence storage

  decide:
    needs: [assemble-evidence]
    steps:
      - evaluate required evidence against release policy
      - record success, degraded, failed or inconclusive
      - promote, pause or rollback according to policy
```

Tên bước là mô tả khái niệm, cần thay bằng action của nền tảng CI và hệ thống observability thực tế. Nếu deploy job và verify job chạy trên runner khác nhau, cần truyền deployment ID và artifact digest qua output có kiểm soát hoặc release record. Không truyền secret hoặc access token trong output.

Upload evidence nên là bước có kiểm tra. Nếu lưu trữ thất bại, quyết định cuối cùng phải theo policy: giữ release ở trạng thái pending, retry upload hoặc đánh dấu inconclusive. Không báo release hoàn tất nếu bằng chứng bắt buộc chưa được lưu.

## 25. Kiểm tra chất lượng evidence

Evidence cần được kiểm tra như một artifact khác. Trước khi đánh dấu bundle hoàn chỉnh, xác minh:

- Schema version được hỗ trợ.
- Deployment ID và release ID có giá trị.
- Artifact digest đúng định dạng.
- Target identity khớp deployment request.
- Timestamp có timezone và thứ tự hợp lý.
- Check result dùng enum được quy định.
- Evidence reference truy cập được bởi consumer được phép.
- Digest file khớp nội dung thực tế.
- Signature hợp lệ nếu policy yêu cầu.
- Không có secret hoặc dữ liệu nhạy cảm ngoài phạm vi.
- Các check bắt buộc không bị thiếu hoặc có trạng thái unavailable chưa được giải quyết.

Có thể validate manifest bằng JSON Schema hoặc schema validator tương đương. Schema nên có version và quy trình tương thích khi thêm field. Consumer cũ cần bỏ qua field mở rộng an toàn hoặc nâng cấp có kiểm soát.

Không cho phép một bundle thiếu artifact digest hoặc target identity được đánh dấu complete chỉ vì JSON hợp lệ. Validation cú pháp và validation nghiệp vụ là hai lớp riêng.

## 26. Những anti-pattern thường gặp

| Cách làm chưa tốt | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ lưu dòng "deploy succeeded" | Không biết artifact, target và kết quả thực tế | Evidence manifest gắn release và digest |
| Chỉ lưu log thô | Khó truy vấn, thiếu kết luận và có thể chứa secret | Lưu summary có cấu trúc và tham chiếu log |
| Chỉ kiểm tra một health endpoint | Không chứng minh luồng nghiệp vụ | Kết hợp smoke, synthetic và business checks |
| Dùng tag thay đổi để nhận dạng image | Không xác định nội dung đã chạy | Ghi digest thực tế từ runtime |
| Không lưu target identity | Có thể nhầm môi trường hoặc cluster | Ghi account, cluster, namespace và resource UID |
| Ghi timestamp không có timezone | Khó sắp xếp sự kiện giữa hệ thống | Dùng UTC/RFC 3339 và đồng bộ clock |
| Chụp dashboard nhưng không lưu query | Không thể tái tạo phép đánh giá | Lưu query, filter, window và threshold |
| Thiếu dữ liệu nhưng vẫn ghi success | Quyết định không có căn cứ | Dùng inconclusive/evidence-pending |
| Sửa bundle đã ký mà không có revision | Mất lịch sử và tính toàn vẹn | Append-only event hoặc bundle revision |
| Lưu raw log chứa secret/PII | Tạo kho rò rỉ dữ liệu | Masking, access control và retention |
| Giữ raw telemetry vô thời hạn | Chi phí và rủi ro dữ liệu tăng | Retention theo loại, giữ summary/digest phù hợp |
| Không liên kết migration evidence | Không biết dữ liệu đã chuyển tới đâu | Ghi schema version, run ID và reconciliation |

## 27. Lộ trình xây dựng evidence trong CI/CD

Có thể triển khai theo từng bước:

1. **Chuẩn hóa deployment identity:** tạo deployment ID, release ID và artifact digest dùng xuyên suốt pipeline.
2. **Định nghĩa evidence schema:** xác định field bắt buộc, trạng thái và URI reference.
3. **Chọn nguồn dữ liệu:** deployment controller, test runner, metrics, logs, traces, migration tool và audit API.
4. **Thu thập baseline:** ghi trạng thái trước deploy và thời điểm bắt đầu.
5. **Thu thập rollout evidence:** lưu revision, instance readiness, image digest và events.
6. **Chạy post-deploy checks:** smoke, synthetic, API và business checks phù hợp rủi ro.
7. **Thu thập telemetry:** lưu query, window, threshold và summary.
8. **Tổng hợp data evidence:** schema, backfill, reconciliation nếu có.
9. **Tạo và ký manifest:** tính digest, xác minh nguồn và lưu bundle.
10. **Đánh giá policy:** quyết định success, degraded, failed hoặc inconclusive.
11. **Thiết lập retention và access:** bảo vệ dữ liệu, audit và cleanup.
12. **Diễn tập điều tra:** chọn một deployment cũ, truy xuất bundle và tái tạo kết luận.

Bắt đầu với một service có deployment thường xuyên. Chọn một tập evidence nhỏ nhưng đủ nhận dạng artifact, target, rollout và smoke result. Sau khi quy trình ổn định, mở rộng sang metrics, traces, migration và signature.

## 28. Đo chất lượng hệ thống evidence

Có thể theo dõi:

- Tỷ lệ deployment có evidence bundle đầy đủ.
- Tỷ lệ bundle có artifact digest và target identity.
- Tỷ lệ check bắt buộc có kết quả và nguồn tham chiếu.
- Thời gian từ rollout completion tới evidence decision.
- Tỷ lệ evidence upload/signature/validation thất bại.
- Tỷ lệ deployment ở trạng thái inconclusive do thiếu nguồn dữ liệu.
- Thời gian truy xuất evidence của một release cũ.
- Tỷ lệ liên kết report/telemetry còn truy cập được trong retention window.
- Số lần incident cần evidence nhưng bundle không đủ dữ liệu.
- Số lần phát hiện sai lệch integrity hoặc truy cập không phù hợp.

Đừng chỉ tối ưu tỷ lệ bundle complete bằng cách giảm số check bắt buộc. Mục tiêu là evidence phản ánh đúng rủi ro và giúp quyết định phát hành có căn cứ.

## 29. Checklist lưu bằng chứng sau triển khai

- [ ] Có deployment ID và release ID duy nhất.
- [ ] Artifact version và digest được ghi lại.
- [ ] Source commit và build run được liên kết.
- [ ] Target identity phản ánh môi trường thực tế.
- [ ] Actor/workload identity và deployment run được ghi lại.
- [ ] Có trạng thái trước và sau deploy.
- [ ] Rollout revision và instance readiness có bằng chứng.
- [ ] Smoke/synthetic/API/business checks có result và timestamp.
- [ ] Metric evidence có query, filter, threshold và time window.
- [ ] Log/trace reference có correlation ID và masking phù hợp.
- [ ] Migration/backfill evidence được liên kết nếu có.
- [ ] Cửa sổ quan sát và tiêu chí success/fail được xác định.
- [ ] Thiếu dữ liệu được biểu diễn là unavailable/inconclusive.
- [ ] Manifest có schema version và được validate.
- [ ] Digest/signature bảo vệ tính toàn vẹn theo policy.
- [ ] Evidence storage có access control, audit và retention.
- [ ] Không lưu secret hoặc PII ngoài nhu cầu.
- [ ] Có thể truy xuất bundle và tái tạo kết luận cho một release cũ.

## Kết luận

Lưu bằng chứng xác nhận kết quả triển khai giúp biến một lần deploy thành một sự kiện có thể truy vết và kiểm tra lại. Evidence cần liên kết release, artifact digest, source revision, target identity, actor, rollout state và kết quả kiểm chứng sau deploy. Nó nên kết hợp summary có cấu trúc với tham chiếu tới test report, telemetry, migration result và audit event.

Một hồ sơ tốt nêu rõ dữ liệu nào được quan sát, trong cửa sổ nào, bằng nguồn nào và giới hạn của kết luận. Khi manifest được validate, nội dung được bảo vệ bằng digest hoặc chữ ký, quyền truy cập và retention được kiểm soát, nhóm có thể quyết định promote, pause hoặc rollback dựa trên bằng chứng và điều tra sự cố mà không phải dựa vào trí nhớ hay một dòng log thành công.

