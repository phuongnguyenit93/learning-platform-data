# Đánh giá chi phí vận hành tổng thể thay vì chỉ nhìn thời gian khởi động

## 1. Vì sao startup nhanh chưa đủ để chọn Native Image?

Spring Boot Native Image thường được nhắc đến với thời gian khởi động thấp và mức sử dụng bộ nhớ có thể nhỏ hơn trong một số workload. Tuy nhiên, một dịch vụ production không chỉ khởi động một lần. Nó còn được build, kiểm thử, lưu trong registry, pull về node, chạy qua nhiều replica, xử lý tải, phát sinh log/metric/trace và được đội vận hành hỗ trợ trong suốt vòng đời.

Một native executable có startup nhanh nhưng build mất nhiều phút, tiêu thụ nhiều RAM ở CI, tạo image khó cache hoặc cần nhiều công sức debug có thể không giảm tổng chi phí. Ngược lại, với workload scale-to-zero, job ngắn hoặc môi trường cần tạo replica liên tục, startup nhanh có thể tạo lợi ích đáng kể.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, quyết định JVM hay Native Image nên dựa trên **tổng chi phí vận hành (Total Cost of Ownership – TCO)** và yêu cầu dịch vụ. Bài này xây dựng khung đánh giá từ build pipeline đến production, bao gồm chi phí trực tiếp, chi phí kỹ thuật và chất lượng dịch vụ.

## 2. Xác định phạm vi TCO

TCO cần bao gồm cả chi phí một lần và chi phí lặp lại:

| Nhóm chi phí | Thành phần cần đo |
|---|---|
| Build/CI | Thời gian build, CPU, RAM, runner minutes, cache |
| Test/QA | JVM tests, AOT processing, native tests, container tests |
| Artifact/registry | Binary, image layers, storage, network transfer |
| Deployment | Pull time, rollout time, node capacity, startup/readiness |
| Runtime | CPU, memory, replicas, throughput, latency |
| Scaling | Scale-out, scale-in, cold start, idle capacity |
| Observability | Metrics, tracing, profiling, log storage |
| Operations | Debugging, incident response, upgrades, toolchain maintenance |
| Engineering | Migration, hints, compatibility fixes, training |
| Risk/availability | Failure modes, rollback, support window, vendor constraints |

Không nhất thiết mọi khoản phải quy đổi ngay thành tiền. Có thể bắt đầu bằng đơn vị vật lý như runner-minutes, GiB-hours, GB transferred, replica-hours và engineer-hours, sau đó áp đơn giá nội bộ để tính chi phí.

## 3. Phân biệt chi phí build một lần và chi phí runtime lặp lại

Native Image thường tăng chi phí build so với JAR JVM. Tuy nhiên, build xảy ra theo số lần phát hành/commit, còn runtime tiêu thụ tài nguyên liên tục theo số replica và thời gian chạy.

Một mô hình đơn giản trong một kỳ:

[
TCO = C_{build} + C_{artifact} + C_{deploy} + C_{runtime} + C_{observability} + C_{engineering}
]

Trong đó:

- (C_{build}): CI runner, thời gian build và test.
- (C_{artifact}): lưu trữ registry và truyền image.
- (C_{deploy}): tài nguyên rollout, pull và khởi động.
- (C_{runtime}): CPU/RAM/replica-hours.
- (C_{observability}): thu thập và lưu log/metric/trace/profile.
- (C_{engineering}): migration, duy trì metadata, xử lý lỗi và nâng cấp.

Công thức này là khung phân tích, không phải công thức billing cố định. Một tổ chức có thể gộp deployment vào runtime hoặc phân bổ chi phí platform theo cách khác; điều quan trọng là giữ cùng phương pháp khi so sánh hai phương án.

## 4. Chi phí build và CI

Native Image thường thực hiện Spring AOT, reachability analysis, code generation và linking. Các stage này có thể kéo dài hơn compile/package JVM và cần runner có RAM/CPU lớn hơn.

Cần đo:

- Wall-clock time theo từng stage.
- Peak RAM/cgroup memory.
- CPU time và số core được cấp.
- Số lần build trong kỳ.
- Tỷ lệ build fail/OOM/retry.
- Cache hit và chi phí lưu cache.
- Thời gian chạy native tests so với JVM tests.

Ví dụ, nếu mỗi commit build native mất thêm 8 phút và pipeline có 100 lần chạy trong tuần, chi phí phát sinh là 800 runner-minutes/tuần trước khi tính native test và cache. Số liệu cần lấy từ CI thực tế, không suy ra từ một lần build local.

Tối ưu build cache và chỉ chạy native pipeline theo risk-based policy có thể giảm chi phí, nhưng phải giữ native validation bắt buộc ở các mốc phù hợp như pull request quan trọng hoặc release.

## 5. Chi phí kiểm thử và bảo đảm chất lượng

Không nên tính riêng thời gian compiler rồi bỏ qua test. Native workflow có thể cần:

- Application AOT.
- TestContext AOT.
- Native test compilation.
- Native executable integration tests.
- Container runtime tests.
- Compatibility checks sau khi nâng GraalVM/Spring Boot/dependency.

Giữ phần lớn unit tests nhanh trên JVM, chọn native scenarios cho reflection, resource, proxy, serialization, JNI và luồng nghiệp vụ rủi ro cao. Cách này có thể giảm số lượng native test nhưng vẫn phải duy trì bằng chứng cho các capability quan trọng.

Nếu native test làm CI kéo dài, đo chi phí theo tầng và xác định test nào tạo thêm bằng chứng. Không loại test quan trọng chỉ để pipeline xanh nhanh hơn.

## 6. Artifact storage và network transfer

Native executable size không đồng nghĩa container image size. Container image còn base OS, shared libraries, certificates, timezone data, external config và các runtime files khác.

Chi phí artifact gồm:

- Registry storage theo số version được giữ.
- Số lần push/pull và dung lượng layer transfer.
- Thời gian tải image lên node khi deploy/scale.
- Cache hit giữa các node.
- Retention của debug symbols và build reports.
- Storage của SBOM, provenance và test artifacts.

Image nhỏ hơn có thể giảm pull time và registry transfer, nhưng chỉ khi so sánh cùng semantics (compressed/unpacked, layer sharing). Nếu native image yêu cầu nhiều layer hoặc library hỗ trợ, cần tính chúng vào payload triển khai.

## 7. Runtime cost: CPU, RAM và replica-hours

Runtime cost phụ thuộc workload, không chỉ runtime technology. Đo trên cùng request mix, concurrency, data set, resource limit và thời gian quan sát.

Các chỉ số chính:

| Chỉ số | Ý nghĩa |
|---|---|
| CPU-seconds/request | Lượng CPU trung bình cho một request |
| RSS/working set | Bộ nhớ process/container đang dùng |
| Peak memory | Đỉnh RAM trong workload |
| Throughput | Request/job xử lý mỗi giây |
| p50/p95/p99 latency | Phân phối thời gian phản hồi |
| Replica-hours | Số replica nhân thời gian chạy |
| CPU throttling | Thời gian bị giới hạn CPU |
| OOM/restart | Sự cố bộ nhớ hoặc process |

Nếu native dùng ít RAM hơn, có thể chạy nhiều replica hơn trên cùng node hoặc giảm memory request/limit. Nhưng chỉ giảm limit sau khi đo peak under load và headroom; mức idle RSS thấp không chứng minh đủ bộ nhớ khi traffic tăng.

## 8. Startup nhanh có giá trị kinh tế khi nào?

Startup nhanh có thể giảm thời gian chờ trong các tình huống:

- Workload scale-to-zero và scale-out thường xuyên.
- Serverless/function hoặc job runner chạy ngắn.
- Rolling deployment cần thay replica nhanh.
- Autoscaling phải đáp ứng burst traffic.
- Nhiều process ngắn hạn được tạo theo từng task.

Với một service chạy liên tục nhiều ngày và hiếm khi restart, startup nhanh có thể ít ảnh hưởng tới chi phí hơn CPU/RAM/throughput. Trong trường hợp đó, cần định lượng startup benefit theo số lần cold start và thời gian mỗi lần tiết kiệm.

Không so thời gian main method với thời gian JVM warm-up rồi kết luận startup. Đo từ lúc process được tạo đến khi readiness thực sự phục vụ được request.

## 9. Chi phí scale-out và cold start

Khi autoscaler cần thêm replica, thời gian từ lúc quyết định scale đến khi replica sẵn sàng gồm:

[
T_{ready} = T_{schedule} + T_{image pull} + T_{process start} + T_{app init} + T_{readiness}
]

Native Image có thể giảm một phần (T_{process start}) và (T_{app init}), nhưng image pull, scheduling, network và readiness checks vẫn tồn tại.

Đo riêng từng thành phần nếu nền tảng cung cấp metrics. Nếu pull image chiếm phần lớn thời gian, giảm startup của executable có thể không cải thiện đáng kể time-to-capacity.

Đối với scale-to-zero, tính số cold starts mỗi kỳ và thời gian request/job bị ảnh hưởng. Đối với service luôn có minimum replicas, lợi ích startup có thể chủ yếu nằm ở rollout và node failure recovery.

## 10. Ước lượng chi phí runtime từ workload thực

Một mô hình minh họa:

[
C_{runtime} =
H 	imes N_{avg} 	imes (P_{cpu} cdot CPU_{req} + P_{mem} cdot Mem_{req})
]

Trong đó:

- (H): số giờ trong kỳ.
- (N_{avg}): số replica trung bình.
- (CPU_{req}): CPU request mỗi replica.
- (Mem_{req}): memory request mỗi replica.
- (P_{cpu}), (P_{mem}): đơn giá theo CPU-hour và GiB-hour.

Đây là mô hình phân bổ theo resource request. Một cloud provider có thể tính theo node, vCPU-second, memory GiB-second hoặc instance-hour. Hãy thay bằng pricing model thực tế.

Nếu native giảm memory request từ 1 GiB xuống 600 MiB nhưng cần tăng CPU hoặc thêm replica do throughput thấp hơn, tổng chi phí có thể không giảm. Tính bằng tổng workload và đơn giá, không chỉ so RSS.

## 11. Chi phí observability và troubleshooting

Native Image có thể cần cấu hình riêng cho debug symbols, stack traces, JFR, heap dump hoặc JMX tùy GraalVM version. Spring Actuator, Micrometer và tracing exporter lại là các dependency/runtime configuration riêng.

TCO nên tính:

- CPU/memory overhead của metrics/tracing.
- Dung lượng log, trace và profile lưu trữ.
- Chi phí backend observability.
- Thời gian đội kỹ thuật điều tra crash/native stack.
- Thời gian tái tạo lỗi với đúng toolchain.
- Chi phí giữ debug symbols và build reports.
- Đào tạo và quy trình nâng cấp GraalVM.

Nếu thiếu debug symbols hoặc diagnostic capability cần thiết, incident có thể kéo dài dù runtime rẻ hơn. Observability phải là một phần của phương án native ngay từ đầu, không phải hạng mục bổ sung sau khi xảy ra sự cố.

## 12. Chi phí migration và duy trì metadata

Chuyển ứng dụng sang Native Image có thể cần:

- Sửa code phụ thuộc reflection/classloader.
- Bổ sung RuntimeHints hoặc reachability metadata.
- Thay thư viện không tương thích.
- Viết native integration tests.
- Điều chỉnh class initialization.
- Thay đổi Dockerfile/buildpack.
- Pin GraalVM/JDK/plugin versions.
- Cập nhật pipeline và developer workflow.

Các chi phí này thường tập trung trong giai đoạn migration nhưng một phần tiếp tục phát sinh khi dependency hoặc framework nâng version. Metadata thủ công có thể cần review lại; native compatibility test phải chạy sau thay đổi có rủi ro.

Đo engineer-hours theo task hoặc sprint. Không coi migration là chi phí bằng 0 chỉ vì executable cuối cùng có ít RAM hơn.

## 13. Ví dụ so sánh TCO cho hai phương án

Bảng sau chỉ minh họa cách tính, không phải benchmark thực tế:

| Hạng mục/tháng | JVM | Native |
|---|---:|---:|
| CI build/test | 120 runner-hours | 210 runner-hours |
| Registry transfer/storage | 500 GB-month | 320 GB-month |
| Runtime memory | 180 GiB-hours | 110 GiB-hours |
| Runtime CPU | 900 vCPU-hours | 820 vCPU-hours |
| Cold-start impact | 240 phút chờ cộng dồn | 35 phút |
| Engineering maintenance | 20 giờ | 34 giờ |

Không cộng trực tiếp GB-month, GiB-hours, phút và engineer-hours thành một con số. Cần áp đơn giá nội bộ hoặc dùng bảng scorecard đa tiêu chí.

Ví dụ nếu native giảm memory cost nhưng tăng CI và maintenance cost, kết quả TCO phụ thuộc số replica, thời gian chạy, số lần phát hành và đơn giá runner. Với một workload scale-to-zero, cold-start impact có thể có giá trị kinh doanh lớn hơn chi phí CI tăng thêm.

## 14. Phân tích độ nhạy và điểm hòa vốn

Kết quả TCO phụ thuộc giả định. Hãy thay đổi các biến quan trọng để tìm điều kiện Native Image có lợi:

- Số lần build/phát hành mỗi tháng.
- Số replica trung bình và peak.
- Thời gian chạy mỗi replica.
- Memory request và CPU request.
- Số cold starts.
- Image transfer volume.
- Đơn giá CI runner và production resources.
- Engineer-hours duy trì metadata.

Có thể tính điểm hòa vốn theo kỳ:

[
Savings_{period} =
Savings_{runtime} + Savings_{scale}
- Extra_{build} - Extra_{artifact} - Extra_{engineering}
]

Nếu kết quả dương ổn định trong các kịch bản thực tế, Native Image có thể có lợi về chi phí. Nếu chỉ dương khi giả định traffic hoặc memory reduction quá lạc quan, cần thêm benchmark production-like.

Không chỉ chọn kịch bản trung bình. Tính cả low/expected/high workload và xem kết quả có đổi dấu hay không.

## 15. Chi phí availability và failure modes

TCO không chỉ là tiền hạ tầng. Cần tính khả năng đáp ứng SLA/SLO và chi phí sự cố:

- Native startup nhanh có thể giúp phục hồi replica nhanh hơn.
- Native build phức tạp có thể tăng thời gian phát hành hoặc rollback.
- Dependency không tương thích có thể gây lỗi chỉ ở một code path hiếm.
- Binary phụ thuộc libc/architecture có thể giới hạn node placement.
- Thiếu diagnostic capability có thể kéo dài MTTR.
- Native toolchain upgrade có thể tạo regression cần xử lý.

Đo error rate, restart rate, deployment failure, rollback frequency và mean time to recovery. Một phương án có compute cost thấp hơn nhưng tăng outage risk có thể đắt hơn về tổng thể.

## 16. Chiến lược rollout để đo trong thực tế

Có thể triển khai JVM và native song song cho cùng workload hoặc một nhóm traffic được kiểm soát:

1. Chọn service có metric và workload ổn định.
2. Build hai artifact từ cùng source revision.
3. Chạy cùng contract/integration tests.
4. Deploy canary native với traffic hoặc replica giới hạn.
5. Thu metrics CPU/RAM/latency/startup/pull/scale.
6. So sánh cùng time window và traffic profile.
7. Theo dõi lỗi native-specific và chi phí CI/registry.
8. Mở rộng traffic khi đạt SLO và có lợi ích rõ.
9. Giữ rollback path về JVM trong thời gian đánh giá.

Không route cùng một request có side effect tới cả hai hệ thống nếu không có cơ chế idempotency/duplicate control. Có thể dùng shadow traffic cho request chỉ đọc hoặc test data được cô lập.

## 17. Scorecard ra quyết định

Một scorecard có thể dùng các tiêu chí sau:

| Tiêu chí | Câu hỏi | Trọng số gợi ý |
|---|---|---:|
| Runtime resource | CPU/RAM giảm bao nhiêu với cùng workload? | 25% |
| Startup/scale | Time-to-ready và cold-start cải thiện thế nào? | 15% |
| Build/CI | Runner time và peak RAM tăng bao nhiêu? | 15% |
| Artifact/deploy | Registry size, pull và rollout thay đổi ra sao? | 10% |
| Compatibility | Bao nhiêu dependency cần workaround? | 15% |
| Observability | Có đủ dữ liệu debug và monitoring không? | 10% |
| Maintenance | Engineer-hours và upgrade effort ra sao? | 10% |

Trọng số chỉ là ví dụ. Điều chỉnh theo mục tiêu dịch vụ: serverless có thể tăng trọng số startup; service chạy liên tục có thể tăng trọng số runtime resource và throughput.

Scorecard không thay thế hard constraints. Nếu native không đáp ứng chức năng, SLO, platform architecture hoặc support policy, điểm tổng cao cũng không làm nó trở thành lựa chọn hợp lệ.

## 18. Khi nào JVM vẫn là lựa chọn kinh tế hơn?

JVM có thể phù hợp hơn khi:

- Service chạy lâu, ít cold start.
- Workload chủ yếu CPU-bound và native không cải thiện throughput.
- Hệ thống dùng nhiều dynamic class loading, plugin hoặc script compilation.
- Build runner bị giới hạn RAM/CPU và native build quá tốn kém.
- Dependency native support chưa ổn định.
- Đội ngũ chưa có khả năng duy trì toolchain/metadata.
- Observability hoặc incident workflow trên native chưa đáp ứng yêu cầu.

JVM không phải lựa chọn kém hơn. Nếu nó đáp ứng latency, throughput, availability và chi phí mục tiêu với quy trình vận hành đơn giản hơn, giữ JVM là quyết định hợp lý.

## 19. Khi nào Native Image có thể đáng đầu tư?

Native Image có thể phù hợp khi:

- Cold start ảnh hưởng trực tiếp tới trải nghiệm hoặc SLA.
- Workload ngắn hạn/scale-to-zero tạo nhiều process.
- Memory footprint là ràng buộc chính trên node.
- Có nhiều replica và giảm memory request tạo tiết kiệm đáng kể.
- Dependency và framework đã có Native Image support tốt.
- Build pipeline đủ tài nguyên và cache được tối ưu.
- Đội ngũ có native tests, observability và quy trình nâng cấp rõ.

Lợi ích phải được xác nhận bằng benchmark cùng workload. Một con số startup nhanh trong môi trường local không đủ để quyết định production.

## 20. Bài thực hành: lập TCO cho Order API

**Bối cảnh:** Order API hiện chạy JVM, có thể chuyển sang native. Dịch vụ có traffic liên tục trong giờ làm việc, burst theo chiến dịch, nhiều replica và pipeline phát hành hằng ngày.

**Bước 1 — Chọn kỳ đo.** Dùng ít nhất một giai đoạn có traffic đại diện, ghi cả peak/burst và giờ thấp tải.

**Bước 2 — Lấy baseline JVM.** Thu CI runner time, image size, pull time, replica-hours, CPU/RAM, p95/p99 latency và restart/startup metrics.

**Bước 3 — Build native từ cùng revision.** Ghi AOT/native build time, peak memory, binary/image size, test time và số lần workaround.

**Bước 4 — Chạy workload tương đương.** Giữ request mix, concurrency, data, resource limit và SLO; đo CPU/RAM/throughput/latency.

**Bước 5 — Đo scale behavior.** Thử rollout, scale-out và cold start; phân rã scheduling, pull, process startup và readiness.

**Bước 6 — Tính chi phí.** Áp đơn giá CI, registry, CPU, memory, network và engineer-hours theo cùng kỳ.

**Bước 7 — Phân tích độ nhạy.** Thử low/expected/high replica count, release frequency và traffic profile.

**Bước 8 — Đưa ra quyết định.** Ghi lợi ích, chi phí tăng thêm, giới hạn compatibility, rủi ro vận hành và điều kiện rollback.

Tiêu chí hoàn thành: TCO có dữ liệu đo thay vì chỉ giả định; build/runtime/deployment/engineering costs được tính riêng; kết quả được so sánh theo cùng workload và kỳ; quyết định có điều kiện rõ ràng và có phương án rollback.

## 21. Kết luận

Thời gian khởi động chỉ là một phần trong chi phí của Spring Boot Native Image. Quyết định cần tính cả CI/build, peak RAM, test, registry, image pull, CPU/RAM runtime, replica-hours, scaling, observability, migration và engineering maintenance. Những chi phí này lặp lại ở các tần suất khác nhau nên phải được quy về cùng kỳ và cùng mô hình tính.

Hãy đo bằng workload production-like, phân biệt startup với time-to-ready, binary size với container transfer, process RSS với cgroup memory và chi phí hạ tầng với công sức kỹ thuật. Native Image đáng đầu tư khi lợi ích tổng thể đáp ứng mục tiêu kinh doanh/SLO sau khi tính cả chi phí tăng thêm; JVM vẫn là lựa chọn đúng nếu nó mang lại kết quả tốt hơn với rủi ro và công sức thấp hơn.
