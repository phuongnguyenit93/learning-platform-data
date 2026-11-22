# Theo dõi tình trạng dịch vụ CI và runner

## 1. Vì sao phải quan sát dịch vụ CI và runner?

CI/CD là một dịch vụ nội bộ quan trọng đối với quá trình phát triển và phát hành phần mềm. Khi hệ thống CI chậm, runner không nhận job, queue tăng hoặc artifact không được publish, nhóm phát triển có thể không tích hợp được thay đổi, không phát hiện lỗi sớm và không phát hành đúng thời điểm. Một pipeline màu xanh không đủ để chứng minh toàn bộ nền tảng CI đang khỏe; ngược lại, một pipeline thất bại cũng chưa chắc do code của ứng dụng.

Quan sát (observability) dịch vụ CI và runner giúp trả lời các câu hỏi:

- Người dùng có thể tạo pipeline và nhận kết quả đúng thời gian mong đợi không?
- Job đang chờ vì thiếu runner, bị khóa bởi concurrency limit hay đang chờ dependency?
- Runner có đủ CPU, memory, disk và network để thực thi job không?
- Job thất bại do code, môi trường thực thi, nền tảng CI hay dịch vụ bên ngoài?
- Artifact, log và test evidence có được lưu đầy đủ sau khi job kết thúc không?
- Có runner nào mất heartbeat, bị kẹt, quá cũ hoặc không còn nhận job không?
- Một thay đổi cấu hình hoặc nâng cấp runner có làm tăng lỗi, thời gian chạy hoặc chi phí không?

Theo dõi tốt giúp phân biệt lỗi pipeline với lỗi nền tảng, phát hiện suy giảm trước khi người dùng báo, lập kế hoạch capacity và cung cấp bằng chứng để điều tra incident. Nó cũng giúp nhóm đánh giá chất lượng dịch vụ CI theo trải nghiệm thực tế thay vì chỉ nhìn số lượng job thành công.

## 2. Phạm vi cần quan sát trong một nền tảng CI

Một dịch vụ CI/CD thường có nhiều lớp. Chỉ quan sát máy runner sẽ bỏ sót lỗi ở control plane, queue hoặc artifact storage.

| Lớp | Thành phần | Câu hỏi cần trả lời |
|---|---|---|
| Control plane | API, scheduler, webhook, pipeline orchestrator, database metadata | Người dùng có tạo và điều khiển pipeline được không? |
| Queue/scheduler | Job queue, dispatcher, concurrency controller | Job chờ bao lâu và vì sao chưa được cấp runner? |
| Runner fleet | Runner manager, agent, worker VM/container, executor | Runner có online, đủ capacity và thực thi ổn định không? |
| Job execution | Checkout, build, test, scan, package, deploy | Stage nào chậm hoặc thất bại? |
| Dependency | Git server, package registry, container registry, database test, cloud API | Dependency nào gây timeout hoặc throttling? |
| Artifact/evidence | Artifact store, cache, test report, log, provenance | Kết quả có được lưu và truy xuất đầy đủ không? |
| Security boundary | Identity, secret provider, runner isolation, policy | Job có đúng quyền và runner có được bảo vệ không? |
| User experience | Pipeline UI/API, notification, status check | Developer nhận kết quả và feedback có kịp thời không? |

Một pipeline chỉ hoàn tất khi các lớp liên quan phối hợp được. Ví dụ, scheduler có thể tạo job thành công nhưng runner không nhận job; runner có thể chạy xong nhưng upload artifact thất bại; artifact có thể được lưu nhưng webhook báo trạng thái tới hệ thống quản lý mã nguồn bị lỗi.

## 3. Phân biệt metric, log, trace và event

Các loại telemetry bổ trợ nhau:

| Loại bằng chứng | Mô tả | Dùng để trả lời |
|---|---|---|
| Metric | Giá trị số được tổng hợp theo thời gian | Có bao nhiêu job đang chờ? Tỷ lệ lỗi tăng không? |
| Log | Sự kiện có nội dung và ngữ cảnh | Job nào lỗi? Runner báo lỗi gì? |
| Trace | Chuỗi span mô tả một request hoặc workflow qua nhiều thành phần | Thời gian bị tiêu tốn ở scheduler, queue hay runner? |
| Event | Sự kiện rời rạc có timestamp và actor | Runner được đăng ký, job được retry hay deployment bị hủy khi nào? |

Metric phù hợp với dashboard và cảnh báo xu hướng. Log hỗ trợ điều tra chi tiết. Trace giúp nối thời gian xử lý giữa các dịch vụ. Event tạo timeline cho các thay đổi trạng thái như pipeline created, job queued, runner assigned, job started, artifact uploaded và pipeline completed.

Không nên chọn một loại telemetry thay cho tất cả. Ví dụ, metric job failure rate báo rằng tỷ lệ lỗi tăng, nhưng log và trace mới giúp xác định lỗi tập trung ở bước tải dependency hay ở test của ứng dụng.

## 4. Xác định SLI và SLO cho dịch vụ CI

Service Level Indicator (SLI) là chỉ số đo một khía cạnh của chất lượng dịch vụ. Service Level Objective (SLO) là mục tiêu chất lượng trong một cửa sổ thời gian. Với CI, cần chọn SLI phản ánh trải nghiệm developer và năng lực cung cấp kết quả.

Các SLI thường hữu ích:

- **Pipeline submission availability:** tỷ lệ yêu cầu tạo pipeline được chấp nhận thành công.
- **Queue wait time:** thời gian từ khi job sẵn sàng chạy đến khi runner bắt đầu thực thi.
- **Job start latency:** thời gian từ lúc job được tạo đến lúc bắt đầu.
- **Pipeline completion latency:** thời gian từ lúc pipeline được kích hoạt đến lúc có kết quả cuối.
- **Platform-attributable failure rate:** tỷ lệ job thất bại do nền tảng, runner hoặc dependency được quản lý.
- **Runner availability:** tỷ lệ thời gian runner pool có capacity sẵn sàng theo mục tiêu.
- **Artifact availability:** tỷ lệ artifact đã publish có thể tải lại trong thời gian yêu cầu.
- **Evidence completeness:** tỷ lệ job kết thúc có đủ log, report và metadata bắt buộc.

Ví dụ SLO minh họa:

| SLI | Mục tiêu ví dụ | Phạm vi |
|---|---|---|
| Pipeline submission | 99,9% request tạo pipeline được chấp nhận trong tháng | API/control plane |
| Queue wait | 95% job thuộc pool tiêu chuẩn bắt đầu trong 3 phút | Job đủ điều kiện, không tính job bị khóa có chủ đích |
| Platform failure | Dưới 1% job thất bại do nền tảng trong tháng | Phân loại nguyên nhân có bằng chứng |
| Artifact retrieval | 99,9% artifact còn trong retention tải lại thành công | Artifact repository |
| Evidence completeness | 99,5% job kết thúc có log và report bắt buộc | Job thuộc workflow có yêu cầu evidence |

Các con số chỉ là ví dụ để minh họa cách định nghĩa. SLO thực tế cần dựa trên nhu cầu của nhóm phát triển, dữ liệu lịch sử, loại workload và chi phí vận hành. Không nên đặt SLO chỉ vì một con số dễ nhớ.

## 5. Đo queue wait và thời gian thực thi riêng biệt

Tổng thời gian pipeline có thể gồm nhiều khoảng:

\[
T_{pipeline} = T_{queue} + T_{execution} + T_{post-processing}
\]

Trong đó:

- Queue time: thời gian job chờ scheduler hoặc runner.
- Execution time: thời gian runner thực hiện script, build, test hoặc deploy.
- Post-processing: upload artifact, tổng hợp report, cập nhật trạng thái và webhook.

Nếu chỉ đo tổng duration, nhóm không biết nên tối ưu runner, build script hay scheduler. Một pipeline tăng từ 8 lên 18 phút có thể do queue wait tăng 10 phút dù thời gian compile không đổi.

Nên lưu timestamp cho các mốc:

- Pipeline requested/created.
- Job queued.
- Job assigned to runner.
- Job started.
- Job finished.
- Artifact upload completed.
- Final status published.

Từ các mốc này có thể tính queue wait, runner startup, execution, upload và post-processing. Cần dùng cùng một định nghĩa cho các dashboard và báo cáo để tránh so sánh sai.

## 6. Theo dõi trạng thái runner fleet

Runner là tài nguyên thực thi job. Một runner có trạng thái online chưa chắc đã sẵn sàng nhận job; nó có thể hết disk, đang drain, không có executor phù hợp hoặc đã vượt giới hạn concurrent jobs.

Các trạng thái nên quan sát:

| Trạng thái | Ý nghĩa vận hành |
|---|---|
| Online/healthy | Agent kết nối control plane và đủ điều kiện nhận job |
| Busy | Đang thực thi một hoặc nhiều job |
| Idle | Có thể nhận job phù hợp |
| Draining | Không nhận job mới, chờ job hiện tại kết thúc |
| Provisioning | Đang tạo VM/container hoặc khởi động agent |
| Offline | Không gửi heartbeat hoặc không kết nối được |
| Unhealthy | Có lỗi tài nguyên, executor hoặc agent |
| Quarantined | Bị cách ly theo chính sách bảo mật/vận hành |
| Terminated | Đã kết thúc vòng đời |

Tổng số runner không bằng số runner có thể sử dụng. Nên theo dõi cả online, idle, busy, draining, provisioning và unhealthy theo pool, label, region và trust class.

## 7. Heartbeat và phát hiện runner mất kết nối

Runner manager thường gửi heartbeat hoặc cập nhật trạng thái định kỳ để control plane biết runner còn hoạt động. Nếu heartbeat ngừng, scheduler có thể coi runner offline và xử lý job đang chạy theo timeout hoặc retry policy.

Các thông tin hữu ích:

- Thời điểm heartbeat cuối cùng.
- Độ trễ heartbeat và số lần miss liên tiếp.
- Agent version và thời gian chạy từ lần khởi động.
- Executor/runner type và labels.
- Job đang chạy hoặc job gần nhất.
- Host/VM/container identity.
- Lý do offline hoặc termination nếu nền tảng cung cấp.

Không nên cảnh báo chỉ vì một heartbeat trễ ngắn nếu nền tảng có jitter hoặc network transient. Cần ngưỡng theo heartbeat interval, số lần miss và trạng thái của job đang chạy. Với runner ephemeral, cần phân biệt runner đã hoàn tất và được terminate theo thiết kế với runner mất kết nối bất thường.

## 8. Quan sát CPU, memory, disk và network của runner

Runner cần đủ tài nguyên để thực thi workload. Nên thu thập cả mức sử dụng và dấu hiệu bị giới hạn:

| Tài nguyên | Metric gợi ý | Dấu hiệu cần điều tra |
|---|---|---|
| CPU | utilization, load/run queue, throttled time | Job duration tăng khi concurrency tăng |
| Memory | working set, available memory, swap, OOM events | Build/test bị kill hoặc GC kéo dài |
| Disk | free bytes, inode, I/O latency, queue depth | Checkout/extract/upload chậm hoặc workspace đầy |
| Network | throughput, errors, retransmits, DNS latency | Download dependency timeout |
| Process | process count, open file descriptors, thread count | Không tạo được process hoặc socket |
| Container | CPU/memory limit, throttling, restart count | Job bị giới hạn bởi cgroup/container quota |

Theo dõi theo runner pool và loại workload giúp nhận diện vấn đề. Ví dụ, browser test có thể cần nhiều memory hơn unit test; image build có thể gây disk I/O cao; integration test có thể chờ database dù runner còn CPU.

## 9. Runner capacity và saturation

Capacity là năng lực tối đa có thể cung cấp; utilization là mức sử dụng; saturation thể hiện mức tài nguyên bị tranh chấp hoặc hàng đợi hình thành. Utilization cao chưa chắc là xấu nếu thời gian chờ vẫn thấp, nhưng saturation tăng thường báo hiệu người dùng bắt đầu chịu ảnh hưởng.

Các tín hiệu:

- Tỷ lệ runner busy so với runner online.
- Số job queued trên mỗi runner có thể nhận.
- Queue wait p50/p95/p99.
- Thời gian provision runner mới.
- CPU throttling và memory pressure.
- Tỷ lệ job bị OOM hoặc hết disk.
- Tỷ lệ runner offline hoặc bị quarantine.

Nếu runner pool thường xuyên 100% busy và queue wait tăng, có thể cần thêm capacity, điều chỉnh concurrency, phân loại workload hoặc giảm fan-out. Nếu runner idle nhưng job vẫn chờ, nguyên nhân có thể là labels không khớp, resource lock, quota dự án hoặc scheduler policy.

## 10. Theo dõi lifecycle của runner ephemeral

Runner ephemeral được tạo cho một job hoặc một nhóm job ngắn hạn rồi hủy. Mô hình này giảm tồn tại lâu dài của workspace và giúp cô lập workload, nhưng cần quan sát toàn bộ lifecycle:

1. Yêu cầu provision.
2. VM/container được tạo.
3. Agent khởi động và đăng ký.
4. Runner nhận job.
5. Job chạy và upload kết quả.
6. Agent deregister hoặc kết thúc.
7. VM/container và dữ liệu tạm được dọn.

Metric quan trọng gồm provisioning latency, startup failure, registration failure, job assignment delay, cleanup duration, orphan runner count và provisioning cost.

Runner tồn tại sau khi job kết thúc có thể là orphan; runner bị terminate trước khi upload log có thể làm mất bằng chứng. Cần đặt timeout, cleanup policy và cơ chế giữ evidence độc lập với filesystem tạm của runner.

## 11. Theo dõi pipeline và job state

Pipeline và job thường đi qua nhiều trạng thái: created, queued, running, waiting for approval, skipped, canceled, failed, succeeded hoặc timed out. Tên trạng thái cụ thể phụ thuộc nền tảng.

Nên đo:

- Số pipeline/job được tạo theo thời gian.
- Số đang queued/running/blocked.
- Tỷ lệ success/failure/cancel/timeout.
- Số lần retry và tỷ lệ retry thành công.
- Tỷ lệ job bị skipped do điều kiện workflow.
- Thời gian ở từng state.
- Số job bị treo hoặc vượt timeout.

Phân biệt failure do code với failure do nền tảng là việc quan trọng. Có thể dùng exit code, runner system error, dependency error, timeout reason, cancellation actor và stage name. Không nên gán mọi job failed thành lỗi CI platform; điều đó làm SLO mất ý nghĩa.

## 12. Phân loại nguyên nhân thất bại

Một taxonomy nhất quán giúp dashboard và incident review có thể so sánh:

| Nhóm | Ví dụ | Owner xử lý thường gặp |
|---|---|---|
| Source/test failure | Compile error, unit test assertion fail | Nhóm phát triển |
| Runner failure | Agent crash, disk full, OOM, executor lỗi | CI platform/runner team |
| Scheduler/queue | Job không được assign, queue stuck | CI platform |
| Dependency failure | Registry 429, database unavailable, cloud API timeout | Owner dependency hoặc platform |
| Configuration/policy | Runner label sai, permission denied, environment lock | Platform/security/release owner |
| Artifact/evidence | Upload thất bại, report thiếu, checksum mismatch | Platform/artifact owner |
| User cancellation | Developer hủy pipeline hoặc superseded commit | Người yêu cầu/workflow policy |
| Unknown | Chưa đủ bằng chứng để phân loại | Cần điều tra, không gán tùy tiện |

Giữ trạng thái unknown khi chưa có bằng chứng tốt hơn là ép vào nhóm code failure. Taxonomy nên có định nghĩa, ví dụ và quy tắc chuyển trạng thái sau khi điều tra.

## 13. Theo dõi dependency từ góc nhìn CI

CI thường phụ thuộc vào dịch vụ mà team platform không trực tiếp vận hành. Cần theo dõi latency, error rate, throttling và timeout khi gọi dependency:

- Git hosting và webhook delivery.
- Package repository và dependency proxy.
- Container registry.
- Secret manager và identity provider.
- Cloud provisioning API.
- Kubernetes API server và admission webhook.
- Database, message broker và test environment.
- Artifact store, object storage và cache.

Metric ở phía CI nên gắn tên dependency, operation và kết quả. Không ghi token, URL có credential hoặc payload nhạy cảm vào label/log.

Nếu registry chậm, nhiều job có thể cùng retry và làm tình trạng nặng hơn. Kết hợp dependency metrics với queue và retry metrics giúp xác định lỗi gốc thay vì chỉ thấy job duration tăng.

## 14. Cache và artifact store cũng cần được quan sát

Cache giúp giảm thời gian tải/build nhưng cache hit rate không phải mục tiêu duy nhất. Cache cũ hoặc sai key có thể gây kết quả không nhất quán; cache miss hàng loạt có thể tạo tải lớn lên registry.

Nên theo dõi:

- Cache hit/miss rate theo loại cache.
- Cache download/upload latency.
- Cache size, eviction và failed restore.
- Artifact upload/download success rate.
- Artifact transfer duration và throughput.
- Storage capacity, retention deletion và replication lag.
- Checksum/digest verification failures.
- Số job kết thúc nhưng thiếu report hoặc artifact bắt buộc.

Cache có thể được tạo lại; artifact phát hành và bằng chứng thường cần retention, integrity và khả năng truy xuất mạnh hơn. Không gộp hai loại dữ liệu này thành một SLO duy nhất nếu yêu cầu vòng đời khác nhau.

## 15. Log có cấu trúc cho pipeline và runner

Log nên có trường nhất quán để tìm kiếm và liên kết các thành phần:

~~~json
{
  "timestamp": "2026-11-18T08:30:00Z",
  "level": "ERROR",
  "service": "ci-runner",
  "runner_id": "runner-42",
  "runner_pool": "linux-medium",
  "pipeline_id": "pipe-1042",
  "job_id": "job-3",
  "stage": "integration-test",
  "event": "dependency_timeout",
  "dependency": "integration-db",
  "duration_ms": 30000,
  "correlation_id": "corr-7f..."
}
~~~

Các trường hữu ích:

- Timestamp chuẩn hóa và timezone.
- Severity/level.
- Service/component và version.
- Runner ID, pool, executor và host identity.
- Pipeline ID, job ID, stage và attempt.
- Event name, error category và exit code.
- Dependency/operation.
- Duration và retry count.
- Trace ID/correlation ID nếu có.

Không nên đưa toàn bộ environment variable, command line có token, secret, nội dung source code riêng tư hoặc dữ liệu người dùng vào log. Cần masking, access control, retention và quy trình xử lý log có chứa secret ngoài ý muốn.

## 16. Trace một pipeline qua nhiều thành phần

Distributed tracing giúp nối request từ lúc nhận webhook đến khi pipeline hoàn tất. Một trace có thể gồm các span:

~~~text
webhook_received
  └── pipeline_created
       └── job_queued
            └── runner_provisioned
                 └── runner_registered
                      └── job_started
                           ├── checkout
                           ├── dependency_restore
                           ├── build
                           ├── test
                           └── artifact_upload
       └── status_callback
~~~

Trace giúp tìm phần chậm trong một lần chạy cụ thể. Nếu không thể instrument trực tiếp mọi công cụ build, có thể tạo span ở wrapper/orchestrator quanh các bước lớn và gắn trace context vào log.

Trace không nên chứa secret hoặc payload nhạy cảm. Với pipeline có nhiều job độc lập, có thể dùng trace link hoặc correlation ID chung thay vì ép mọi job thành một trace dài vượt giới hạn thời gian. Cần kiểm tra sampling để không mất toàn bộ trace của các lỗi hiếm.

## 17. Metric naming, labels và cardinality

Metric nên có tên mô tả đơn vị và ý nghĩa, ví dụ:

- **ci_jobs_queued**
- **ci_job_queue_wait_seconds**
- **ci_job_duration_seconds**
- **ci_job_failures_total**
- **ci_runner_online**
- **ci_runner_cpu_utilization_ratio**
- **ci_runner_memory_working_set_bytes**
- **ci_runner_disk_free_bytes**
- **ci_artifact_upload_duration_seconds**

Labels có thể gồm pool, executor, job type, stage, result class và region. Tránh label có cardinality cao như pipeline ID, job ID, commit SHA, branch tùy ý hoặc username trên metric time series. Các định danh này phù hợp hơn với log, trace hoặc event.

Cardinality quá cao làm tăng chi phí lưu trữ và query, đồng thời có thể gây mất dữ liệu metric. Nếu cần drill down từ dashboard, dùng link tới log/trace hoặc event store theo pipeline ID thay vì tạo một time series cho từng pipeline.

## 18. Ví dụ metric Prometheus và truy vấn

Một exporter hoặc instrumentation nội bộ có thể cung cấp metric theo dạng:

~~~text
ci_jobs_queued{pool="linux-medium",priority="normal"} 14
ci_runner_online{pool="linux-medium"} 12
ci_runner_busy{pool="linux-medium"} 10
ci_job_failures_total{stage="integration-test",cause="dependency"} 23
ci_job_queue_wait_seconds_bucket{pool="linux-medium",le="60"} 120
ci_job_queue_wait_seconds_bucket{pool="linux-medium",le="180"} 185
~~~

Các truy vấn PromQL minh họa:

~~~promql
# Tỷ lệ runner busy trên số runner online
sum(ci_runner_busy) / clamp_min(sum(ci_runner_online), 1)

# Tốc độ job failure theo stage và nguyên nhân
sum by (stage, cause) (rate(ci_job_failures_total[15m]))

# Queue wait p95 từ histogram
histogram_quantile(
  0.95,
  sum by (le, pool) (rate(ci_job_queue_wait_seconds_bucket[15m]))
)
~~~

Tên metric và label phải khớp với exporter thực tế. Ví dụ trên chỉ minh họa cách biểu diễn và truy vấn; nếu metric runner busy/online là gauge không đồng bộ hoặc histogram thiếu bucket phù hợp, cần điều chỉnh instrumentation trước khi dùng trong cảnh báo.

## 19. Dashboard cho developer và platform operator

Không nên dồn mọi thông tin vào một dashboard. Người phát triển cần biết pipeline của họ đang ở đâu; platform operator cần thấy sức khỏe toàn fleet và dependency.

Dashboard developer có thể hiển thị:

- Pipeline status và stage hiện tại.
- Queue wait so với execution time.
- Lịch sử success/failure gần đây.
- Job failure reason và liên kết log.
- Artifact/report có sẵn hay thiếu.
- Runner pool đang được sử dụng.

Dashboard platform có thể hiển thị:

- Pipeline submission rate và control plane availability.
- Queue depth, oldest job age và queue wait p50/p95.
- Runner online/idle/busy/unhealthy theo pool.
- CPU, memory, disk, network và provisioning latency.
- Job failure/cancel/timeout theo nguyên nhân.
- Dependency latency, 429, 5xx và retry rate.
- Artifact/cache upload/download và storage capacity.
- SLO/error budget và cảnh báo đang mở.

Dashboard nên có liên kết drill-down từ tổng quan tới pipeline, job, runner và trace/log. Không đưa thông tin nhạy cảm lên dashboard công khai cho toàn tổ chức.

## 20. Thiết kế alert có hành động

Alert tốt cần cho biết vấn đề, tác động, mức độ khẩn cấp và bước đầu tiên để điều tra. Tránh cảnh báo chỉ vì một metric vượt ngưỡng trong một mẫu ngắn.

Ví dụ nhóm alert:

| Alert | Điều kiện gợi ý | Hành động |
|---|---|---|
| Queue wait elevated | p95 queue wait vượt SLO trong một cửa sổ đủ dài | Kiểm tra runner capacity, labels, locks và scheduler |
| Runner pool unavailable | Số runner healthy dưới mức tối thiểu | Kiểm tra provisioning, agent, network và quota |
| Runner disk pressure | Disk free thấp hoặc inode gần cạn | Xác định pool/job gây đầy, cleanup theo policy |
| CI platform failure spike | Platform-attributable failure rate tăng | Kiểm tra control plane, runner rollout và dependency |
| Artifact upload failure | Upload failure vượt ngưỡng | Kiểm tra object store, credentials, network và quota |
| Dependency throttling | 429/timeout tăng | Giảm concurrency, backoff và kiểm tra quota |
| Evidence missing | Job kết thúc nhưng thiếu report bắt buộc | Kiểm tra upload/finalization và retention path |

Alert nên có owner, runbook, dashboard link và điều kiện resolve. Dùng grouping, inhibition và deduplication để tránh gửi hàng trăm alert cho cùng một sự cố gốc.

## 21. Error budget và ưu tiên cải thiện dịch vụ CI

Nếu một SLO đặt availability hoặc queue wait objective, error budget biểu thị mức suy giảm còn được phép trong cửa sổ đánh giá. Khi error budget tiêu thụ nhanh, nhóm có thể ưu tiên độ ổn định nền tảng hơn việc triển khai thay đổi rủi ro.

Ví dụ, nếu mục tiêu 99,9% cho một chỉ số availability trong tháng, phần thời gian không đạt mục tiêu là error budget tương ứng. Cách tính cụ thể cần dùng đúng SLI và loại trừ các trạng thái được định nghĩa trước, chẳng hạn job bị hủy chủ động hoặc pipeline bị chặn do approval.

Không nên tính mọi job failed vào error budget của CI platform. Test assertion fail do code thường thuộc trách nhiệm chất lượng phần mềm; runner crash hoặc scheduler không cấp job mới có thể thuộc SLO nền tảng. Cần phân loại rõ và công khai định nghĩa.

## 22. Bảo vệ dữ liệu telemetry và evidence

Log, trace và report CI có thể chứa source path, tên branch, tên người dùng, endpoint nội bộ, dữ liệu test hoặc vô tình có secret. Observability cần được thiết kế cùng bảo mật:

- Phân quyền đọc log và artifact theo project, environment và vai trò.
- Mask secret trước khi lưu và kiểm tra log redaction.
- Không ghi toàn bộ environment hoặc command line có credential.
- Giới hạn retention theo mục đích và yêu cầu kiểm toán.
- Mã hóa dữ liệu khi truyền và khi lưu theo chính sách.
- Ghi audit log cho truy cập/xóa evidence quan trọng.
- Giữ evidence độc lập với runner ephemeral.
- Xác minh tính toàn vẹn của report/artifact bằng checksum hoặc chữ ký khi cần.
- Có quy trình xử lý khi phát hiện secret hoặc dữ liệu nhạy cảm trong log.

Không phải mọi log cần giữ vô thời hạn. Hãy xác định retention cho log vận hành, debug log, test report, artifact release và audit evidence theo giá trị sử dụng và nghĩa vụ tổ chức.

## 23. Phân biệt telemetry của nền tảng với telemetry của ứng dụng

CI platform metrics cho biết job có được chạy và runner có hoạt động không. Application telemetry cho biết phần mềm được build/deploy có hoạt động đúng không. Hai loại này cần được liên kết nhưng không trộn định nghĩa.

Ví dụ:

- CI job success rate: pipeline có hoàn tất không.
- Deployment success: workload có được áp dụng không.
- Post-deployment verification: phiên bản có đúng và health có đạt không.
- Application SLO: người dùng có nhận được dịch vụ theo mục tiêu không.

Một pipeline có thể thành công nhưng application sau deploy bị lỗi. Ngược lại, application có thể khỏe trong khi một job CI thất bại do test không liên quan hoặc runner tạm thời offline. Dashboard nên cho phép đi từ release ID tới deployment record và application telemetry để tìm mối liên hệ.

## 24. Quy trình điều tra khi CI hoặc runner suy giảm

Khi có cảnh báo, điều tra theo thứ tự giúp khoanh vùng nhanh:

1. Xác định phạm vi: toàn nền tảng, một project, một pool hay một loại job.
2. Kiểm tra control plane/API và webhook delivery.
3. Kiểm tra queue depth, oldest job age và scheduler assignment.
4. Kiểm tra runner online/idle/busy, heartbeat và provisioning.
5. Kiểm tra CPU, memory, disk, network và executor error.
6. Kiểm tra dependency latency, quota, 429/5xx và retry.
7. Đối chiếu pipeline/job log, trace và event timeline.
8. Xác định thay đổi gần đây: runner image, agent version, concurrency, secret policy hoặc registry.
9. Giảm tải hoặc cô lập pool bị ảnh hưởng theo runbook.
10. Xác minh service phục hồi bằng queue wait, job start và job completion thực tế.

Không nên restart toàn bộ runner fleet ngay khi queue tăng. Nếu nguyên nhân là registry đang throttling, restart runner có thể làm tăng pull burst và kéo dài sự cố. Hành động giảm tải cần dựa trên bằng chứng về bottleneck.

## 25. Ví dụ: phân tích queue tăng nhưng runner vẫn idle

Giả sử dashboard cho thấy 40 job đang queued nhưng 8 runner vẫn idle. Đây không nhất thiết là thiếu capacity.

Các giả thuyết cần kiểm tra:

- Job yêu cầu label linux-large nhưng runner idle chỉ có label linux-small.
- Job bị chặn bởi resource group hoặc environment lock.
- Project đã đạt concurrency quota.
- Runner đang online nhưng không được phép nhận job từ trust class của pipeline.
- Scheduler có lỗi hoặc queue partition bị kẹt.
- Job yêu cầu architecture, region hoặc executor không có trong pool.

Quy trình:

1. Lấy một job queued đại diện và đọc requested labels/constraints.
2. Đối chiếu với labels, capacity và trust class của runner idle.
3. Kiểm tra concurrency/resource lock và quota project.
4. Xem scheduler event và lý do assignment thất bại.
5. Kiểm tra một job tương tự có được assign vào pool khác không.
6. Sửa mismatch hoặc quota nếu được phép; sau đó quan sát queue age và assignment latency.

Ví dụ này cho thấy metric tổng số runner không đủ. Cần theo dõi capacity theo pool/label và lý do job chưa được cấp runner.

## 26. Đo hiệu quả vận hành runner fleet

Một số chỉ số giúp đánh giá hiệu quả:

- Runner utilization theo pool và thời gian.
- Queue wait p50/p95/p99.
- Job throughput trên mỗi runner-hour.
- Provisioning success rate và startup latency.
- Runner failure/replacement rate.
- Cost per successful job hoặc pipeline.
- Tỷ lệ job retry do runner/platform.
- Orphan runner và cleanup failure.
- Tỷ lệ job thiếu log/report/artifact.

Utilization quá thấp có thể gợi ý capacity dư thừa; utilization quá cao kèm queue wait tăng có thể báo thiếu capacity hoặc điều phối chưa phù hợp. Không tối ưu utilization đơn độc: mục tiêu là đáp ứng SLO với chi phí và rủi ro hợp lý.

## 27. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ theo dõi CPU runner | Bỏ sót queue, scheduler và dependency | Quan sát toàn bộ control plane đến artifact |
| Chỉ xem tổng số runner online | Không biết runner có đúng label/capacity không | Phân đoạn theo pool, executor, region và trust class |
| Gộp queue time vào job duration | Không xác định được bottleneck | Ghi timestamp riêng cho từng state |
| Coi mọi job failure là lỗi platform | SLO và dashboard sai lệch | Taxonomy nguyên nhân có định nghĩa |
| Dùng pipeline ID làm metric label | Cardinality tăng mạnh | Đưa ID vào log/trace/event |
| Alert theo một mẫu metric | Nhiễu và cảnh báo giả | Dùng cửa sổ, baseline và điều kiện mẫu tối thiểu |
| Restart runner hàng loạt khi queue tăng | Có thể làm provisioning/pull burst nặng hơn | Xác định bottleneck trước khi hành động |
| Giữ log vô hạn hoặc không phân quyền | Chi phí và rủi ro lộ dữ liệu | Retention, masking và access control |
| Dựa vào cache hit rate duy nhất | Có thể che lỗi artifact hoặc cache stale | Theo dõi integrity, upload/download và build result |
| Không giữ evidence ngoài runner | Mất log khi runner ephemeral bị hủy | Upload và xác minh evidence trước cleanup |

## 28. Checklist thiết kế observability cho CI và runner

Trước khi đưa nền tảng vào vận hành hoặc mở rộng runner fleet, hãy xác minh:

- [ ] Có sơ đồ thành phần control plane, queue, runner, dependency và artifact store.
- [ ] SLI/SLO phản ánh submission, queue wait, job start, platform failure và evidence availability.
- [ ] Timestamp được ghi cho pipeline/job lifecycle để tách queue và execution time.
- [ ] Runner có heartbeat, trạng thái lifecycle và thông tin pool/label/executor.
- [ ] CPU, memory, disk, network, process và container throttling được theo dõi.
- [ ] Có metric capacity, saturation, provisioning và orphan runner.
- [ ] Job state, retry, cancellation, timeout và failure cause được phân loại.
- [ ] Dependency latency, quota, 429/5xx và retry được quan sát.
- [ ] Artifact/cache upload-download, integrity và retention được theo dõi.
- [ ] Log có cấu trúc, trace/correlation ID và event timeline.
- [ ] Metric labels được kiểm soát cardinality.
- [ ] Dashboard tách góc nhìn developer và platform operator.
- [ ] Alert có owner, runbook, mức độ và điều kiện resolve.
- [ ] Evidence được masking, phân quyền, retention và lưu ngoài runner ephemeral.
- [ ] Có quy trình điều tra queue tăng, runner mất heartbeat và dependency throttling.
- [ ] Sau khi khắc phục, xác minh bằng số liệu thực tế và ghi nhận timeline.

## 29. Nguyên tắc thực hành cốt lõi

1. Quan sát toàn bộ dịch vụ CI từ control plane, queue, runner, dependency đến artifact/evidence.
2. Đo queue wait, execution và post-processing riêng để xác định đúng bottleneck.
3. Theo dõi runner theo pool, label, executor và lifecycle; online không đồng nghĩa có thể nhận mọi job.
4. Kết hợp metric, log, trace và event để nhìn xu hướng và điều tra từng lần chạy.
5. Đặt SLI/SLO theo trải nghiệm developer và phân loại rõ lỗi platform với lỗi source/test.
6. Quan sát tài nguyên runner và dependency; không tối ưu concurrency chỉ theo CPU.
7. Theo dõi artifact, cache và evidence về khả năng truy xuất, tính toàn vẹn và retention.
8. Dùng dashboard/alert có ngữ cảnh, owner và runbook để hành động nhanh.
9. Bảo vệ telemetry khỏi lộ secret và dữ liệu nhạy cảm; giữ evidence độc lập với runner tạm thời.
10. Xác minh phục hồi bằng queue, job start, completion và trải nghiệm người dùng thực tế.

Theo dõi tình trạng dịch vụ CI và runner biến một nền tảng vốn chỉ được chú ý khi pipeline lỗi thành một dịch vụ có thể đo lường và vận hành chủ động. Khi có SLI/SLO rõ, telemetry liên kết được pipeline với runner và dependency, cùng alert có hành động, nhóm có thể phát hiện suy giảm sớm, tìm đúng nguyên nhân và cải thiện độ tin cậy của toàn bộ quy trình phát hành.
