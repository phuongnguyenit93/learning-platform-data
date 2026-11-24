# Tiêu chí chấp nhận, chi phí bảo trì và trường hợp tiếp tục dùng JVM

## 1. Vì sao không phải ứng dụng Spring Boot nào cũng cần chuyển sang Native Image?

GraalVM Native Image có thể giúp Spring Boot khởi động nhanh hơn, giảm footprint trong một số workload và phù hợp với môi trường scale-to-zero hoặc tạo process ngắn hạn. Đổi lại, nhóm phải đầu tư vào native build toolchain, Spring AOT, reachability metadata, kiểm thử native, tương thích dependency, container runtime và quy trình chẩn đoán riêng.

Quyết định chuyển đổi vì vậy cần dựa trên tiêu chí chấp nhận có thể đo và chi phí duy trì trong suốt vòng đời. Nếu native không cải thiện mục tiêu kinh doanh hoặc SLO đủ để bù chi phí CI, migration và support, tiếp tục chạy JVM là lựa chọn hợp lý.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, bài học này giúp xác định điều kiện để chấp nhận một ứng dụng native, tính chi phí bảo trì định kỳ và nhận diện trường hợp nên giữ JVM. Mục tiêu không phải chuyển đổi bằng mọi giá mà chọn runtime phù hợp với workload, dependency, năng lực đội ngũ và yêu cầu vận hành.

## 2. Đặt mục tiêu trước khi bắt đầu migration

Trước khi tạo native executable, viết rõ vấn đề cần giải quyết. Mục tiêu có thể là:

- Giảm time-to-ready cho workload scale-to-zero.
- Giảm memory request để tăng mật độ replica trên node.
- Giảm thời gian scale-out khi traffic burst.
- Giảm chi phí runtime cho service có nhiều instance.
- Tạo executable nhỏ gọn cho job chạy ngắn.
- Đáp ứng yêu cầu nền tảng hoặc deployment environment cụ thể.

Mỗi mục tiêu cần gắn với baseline và ngưỡng chấp nhận. Ví dụ “startup nhanh hơn” phải xác định đo từ process launch tới readiness, trên cùng image pull/cache condition và resource limits.

Nếu không có pain point hoặc metric mục tiêu, native migration dễ trở thành công việc kỹ thuật tốn kém mà không tạo giá trị vận hành rõ ràng.

## 3. Bộ tiêu chí chấp nhận nên có nhiều nhóm

Một quyết định production-ready cần đánh giá tối thiểu các nhóm:

| Nhóm | Câu hỏi chấp nhận |
|---|---|
| Functional correctness | Native giữ đúng behavior và contract không? |
| Compatibility | Dependency, reflection, resource, proxy và JNI có hoạt động không? |
| Performance | Startup, latency, throughput và memory đạt mục tiêu không? |
| Reliability | Restart, shutdown, scale và failure recovery có ổn định không? |
| Security | SBOM, CVE scan, secret handling và provenance đạt policy không? |
| Observability | Log, metrics, tracing và crash diagnostics đủ dùng không? |
| Build/release | CI có tái lập, có đủ runner capacity và rollback không? |
| Economics | TCO có tốt hơn hoặc đáp ứng yêu cầu chiến lược không? |
| Ownership | Có đội ngũ chịu trách nhiệm nâng cấp và xử lý sự cố không? |

Một chỉ số tốt không bù cho hard blocker ở nhóm khác. Ví dụ startup nhanh không bù được lỗi serialization làm sai response hoặc thiếu quy trình điều tra crash.

## 4. Functional correctness là điều kiện bắt buộc

Native executable phải giữ đúng contract nghiệp vụ so với JVM baseline. Kiểm tra:

- API request/response schema.
- Validation và error mapping.
- Authentication/authorization.
- Transaction và persistence behavior.
- Serialization/deserialization, subtype và custom converter.
- Resource/template/message bundle.
- Scheduled job và message consumer.
- Retry, timeout và idempotency.
- Business side effects.

Chọn test theo capability và risk. Phần lớn unit tests có thể tiếp tục chạy trên JVM; native suite cần bao phủ các đường đi có khả năng khác biệt trong Native Image và các business flow quan trọng.

Không chấp nhận migration nếu test bị skip mà không có lý do và bằng chứng thay thế. Một native smoke test chỉ chứng minh process khởi động, không chứng minh nghiệp vụ đúng.

## 5. Compatibility gate cho dependency

Lập inventory dependency và phân loại:

- Framework/starter có native support chính thức.
- Thư viện có reachability metadata được duy trì.
- Thư viện dùng reflection/resource/proxy.
- Thư viện sinh bytecode hoặc nạp class động.
- Native library/JNI/JNA.
- Thư viện chỉ xuất hiện trong test scope.
- Dependency chưa có support rõ ràng.

Với từng dependency rủi ro, ghi version, feature đang dùng, native test và owner. Nếu dependency không tương thích, cần có phương án: nâng version, bật AOT mode, thay thế, tách module hoặc giữ JVM.

Không dùng nhãn “dependency compatible” chung cho toàn bộ thư viện nếu chỉ một feature được kiểm tra. Compatibility phải gắn với version và cách sử dụng cụ thể.

## 6. Performance gate phải dựa trên workload tương đương

So sánh JVM và native trên cùng:
- Source revision và dependency.
- Request mix, dataset và concurrency.
- CPU/memory limits.
- Base image/runtime environment.
- Warm-up policy và thời gian đo.
- Observability overhead.
- External dependencies và network conditions.

Đo ít nhất:

| Metric | Cách dùng trong quyết định |
|---|---|
| Time-to-ready p50/p95/p99 | Đánh giá startup và scale-out |
| RSS/cgroup peak | Đánh giá memory budget |
| CPU/request | Đánh giá chi phí xử lý |
| Throughput | Đánh giá năng lực tổng |
| p95/p99 latency | Đánh giá tail latency |
| Error/restart/OOM rate | Đánh giá độ ổn định |
| Build duration/peak RAM | Đánh giá chi phí CI |
| Image size/pull time | Đánh giá artifact/deployment |

Đặt ngưỡng theo SLO và baseline thực tế. Không dùng một con số startup benchmark đơn lẻ để quyết định.

## 7. Ví dụ acceptance criteria có thể kiểm tra

Một nhóm có thể viết tiêu chí dạng:

| Tiêu chí | Ví dụ điều kiện pass |
|---|---|
| Functional tests | Tất cả contract và critical business tests pass |
| Native-specific tests | Tất cả scenario rủi ro cao pass |
| Startup | p95 time-to-ready thấp hơn mục tiêu đã thống nhất |
| Memory | Peak cgroup memory nằm trong budget với headroom |
| Latency | p95/p99 không regression vượt ngưỡng SLO |
| Throughput | Đạt capacity mục tiêu ở resource limit dự kiến |
| Stability | Không có OOM/restart bất thường trong soak test |
| Security | Không có finding vượt policy chưa được xử lý |
| Observability | On-call có đủ log/metric/trace và crash evidence |
| Deployment | Final image pass probes, non-root và graceful shutdown |
| Rollback | Có thể chuyển về JVM artifact đã biết tốt |
| Maintenance | Có owner và ngân sách duy trì toolchain/metadata |

Các ngưỡng số cụ thể phải do service owner/SRE/product xác định theo hệ thống. Không áp dụng một mức memory reduction hoặc startup improvement cố định cho mọi Spring Boot application.

## 8. Hard gate và trade-off có thể chấp nhận

Nên phân biệt:

**Hard gates** là điều kiện bắt buộc:
- Functional behavior đúng.
- Security/authorization không regression.
- Critical native paths đã được test.
- SLO và resource limits được đáp ứng.
- Không có CVE/blocker chưa được chấp nhận theo policy.
- Có observability, rollback và owner.

**Trade-offs** có thể đánh giá theo TCO:
- CI build lâu hơn.
- Native runner cần nhiều RAM hơn.
- Binary/image lớn hơn hoặc nhỏ hơn tùy cấu hình.
- Cần thêm metadata/test maintenance.
- Một số diagnostics khác JVM.
- Upgrade toolchain cần thêm regression work.

Không nên biến trade-off thành hard gate nếu không có lý do sản phẩm. Ngược lại, không hạ hard gate chỉ vì native benchmark có kết quả hấp dẫn.

## 9. Chi phí migration ban đầu

Migration cost thường gồm:
- Inventory dependency và dynamic behavior.
- Nâng cấp Spring Boot/dependency.
- Sửa code không tương thích.
- Viết RuntimeHints hoặc cấu hình metadata.
- Điều chỉnh class initialization.
- Tạo native integration tests.
- Xây toolchain và CI runner.
- Chuyển Dockerfile/buildpacks.
- Thiết lập observability/incident workflow.
- Đào tạo developer và on-call.

Ghi effort theo engineer-hours hoặc sprint, phân loại theo capability. Điều này giúp dự báo chi phí khi mở rộng sang service tương tự.

Đừng tính migration bằng số giờ chạy compiler. Phần lớn công việc có thể nằm ở điều tra dependency, sửa integration và thiết kế test.

## 10. Chi phí bảo trì định kỳ sau migration

Sau khi native release, chi phí vẫn tiếp tục phát sinh:

| Hoạt động | Công việc bảo trì |
|---|---|
| Spring Boot upgrade | Chạy lại AOT/native compatibility và regression |
| GraalVM upgrade | Kiểm tra option, toolchain, compiler behavior |
| Dependency update | Kiểm tra metadata và native integration |
| RuntimeHints | Review, xóa hint lỗi thời, bổ sung hint mới |
| Native tests | Duy trì test cho capability rủi ro |
| CI/build | Pin runner, cache, capacity, plugin |
| Container | Cập nhật base image/libc/native libraries |
| Security | SBOM, rescan, CVE remediation |
| Observability | Kiểm tra symbols, JFR/heap dump support và runbook |
| Incident response | Điều tra native crash, OOM và compatibility issue |

Mỗi release framework hoặc dependency có thể thay đổi metadata và behavior. Không giả định một lần build pass có nghĩa mọi lần nâng cấp sau đều an toàn.

## 11. RuntimeHints cũng cần ownership

RuntimeHints có thể được duy trì trong source hoặc dependency metadata. Khi dependency thay đổi, hints thủ công có thể:
- Không còn cần thiết.
- Đăng ký sai member/type.
- Thiếu metadata cho feature mới.
- Giữ reachability rộng hơn cần thiết.
- Trùng với metadata do thư viện đã cung cấp.

Đặt owner cho hints theo module/dependency, ghi lý do và test. Review thay đổi như code production. Khi nâng dependency, kiểm tra lại native test và xóa metadata lỗi thời nếu có bằng chứng.

Không để một file hints khổng lồ không có người hiểu hoặc không biết feature nào cần nó. Metadata càng khó truy vết, chi phí nâng cấp càng cao.

## 12. Chi phí toolchain và CI capacity

Native build có thể cần CPU/RAM cao và thời gian dài hơn JVM packaging. Đội ngũ cần duy trì:
- GraalVM distribution/version.
- JDK và Native Build Tools.
- C compiler/linker/SDK.
- Builder image.
- Cache và artifact store.
- Runner capacity và timeout.
- Build logs/provenance.
- Native test execution environment.

Pin version để tái lập, nhưng cũng phải có lịch nâng cấp bảo mật. Pin mãi một GraalVM version cũ có thể tạo technical debt và không còn nhận patch.

Tính CI cost theo số lần build, runner minutes, peak memory, native test time và cache storage. Nếu chỉ chạy native build ở release mà không kiểm tra thay đổi thường xuyên, lỗi compatibility có thể tích tụ và khó sửa khi cần phát hành gấp.

## 13. Chi phí container và platform compatibility

Native executable gắn với OS/architecture và ABI cụ thể. Khi triển khai nhiều nền tảng, có thể phải tạo binary/image riêng cho:
- Linux amd64.
- Linux arm64.
- glibc hoặc musl environment.
- Các base image khác nhau.
- Native libraries của vendor.

Mỗi target có thể cần build/test riêng. Đội ngũ phải duy trì matrix, artifact digest, image scan và runtime test. Nếu nền tảng triển khai thay đổi node architecture hoặc base image, native artifact cần được xác minh lại.

Nếu ứng dụng cần portability rộng và workload không hưởng lợi đáng kể từ native, JAR JVM có thể đơn giản hơn vì chạy trên nhiều môi trường có JRE tương thích.

## 14. Chi phí observability và incident response

Native executable cần quy trình chẩn đoán phù hợp:
- Structured logs và correlation.
- Actuator/Micrometer metrics.
- Distributed tracing.
- Exit code, signal và OOM events.
- Debug symbols gắn với binary digest.
- Core dump/heap dump nếu được hỗ trợ.
- JFR/JMX theo GraalVM version.
- Tooling/debug container cho distroless.

Đội ngũ on-call cần diễn tập thu evidence và đọc native stack. Nếu incident workflow chỉ quen HotSpot heap dump/JMX và chưa có phương án native, MTTR có thể tăng.

Đưa chi phí này vào acceptance criteria trước production. Không đợi đến lần crash đầu tiên mới xác định cách lấy symbol hoặc core dump.

## 15. Khi nào nên tiếp tục dùng JVM?

JVM thường là lựa chọn phù hợp khi một hoặc nhiều điều kiện sau đúng:

- Service chạy liên tục, ít cold start và startup không phải bottleneck.
- Workload CPU-bound, native không cải thiện throughput/latency.
- Ứng dụng cần plugin JAR hoặc class loading tùy ý sau deploy.
- Dependency cốt lõi sinh bytecode động mà chưa có native-compatible mode.
- Script engine cần compiler/classloader runtime không được hỗ trợ.
- Nhiều thư viện JNI/native không tương thích với target.
- Build runner không đủ RAM/CPU hoặc chi phí CI vượt lợi ích runtime.
- Team chưa có khả năng duy trì metadata, toolchain và native diagnostics.
- Deployment cần chạy trên nhiều OS/architecture chưa có native build matrix.
- SLO đã đạt tốt bằng JVM với chi phí thấp hơn.

Đây không phải dấu hiệu kiến trúc kém. JVM là runtime trưởng thành, có hệ sinh thái rộng và phù hợp với nhiều workload production.

## 16. Khi nào Native Image đáng đầu tư?

Native Image có thể đáng đầu tư nếu:
- Cold start/time-to-ready là vấn đề kinh doanh được đo rõ.
- Service scale-to-zero hoặc tạo nhiều process ngắn hạn.
- Memory footprint là giới hạn capacity đáng kể.
- Giảm memory request giúp tăng mật độ replica và giảm chi phí.
- Dependency/framework có native support ổn định.
- Native-specific tests bao phủ được capability quan trọng.
- Build pipeline có runner và cache phù hợp.
- Đội ngũ có owner, observability và upgrade process.

Lợi ích phải xuất hiện trong production-like workload và TCO. Một benchmark micro hoặc chạy local không đủ đại diện cho chi phí triển khai.

## 17. Trường hợp nên dùng mô hình hybrid

Không nhất thiết toàn bộ hệ thống phải chạy cùng runtime. Có thể:
- Giữ JVM cho plugin host hoặc scripting engine.
- Chạy native cho API stateless có startup/memory pressure cao.
- Tách worker/job ngắn hạn thành native executable.
- Giữ JVM cho module có JNI hoặc dependency chưa hỗ trợ.
- Tách phần dynamic extension thành service riêng.
- Dùng cùng contract/API để hai runtime giao tiếp.

Hybrid có thể tối ưu từng workload nhưng tăng số artifact, deployment và operational model. Chỉ chọn khi lợi ích lớn hơn chi phí duy trì hai pipeline/runtime.

Không tách service chỉ để tránh một hint nhỏ. Tách khi có ranh giới domain/deployment/ownership hợp lý và khả năng vận hành độc lập.

## 18. Cách quyết định bằng TCO

Tính chi phí theo cùng kỳ, ví dụ mỗi tháng:

`TCO = CI + artifact + deployment + runtime + observability + engineering + risk`

Các thành phần cần quy đổi:
- CI runner-hours và memory capacity.
- Registry storage và image transfer.
- CPU/GiB-hours production.
- Replica-hours và scale-out overhead.
- Observability storage/processing.
- Engineer-hours migration/maintenance.
- Incident cost và availability impact.

So sánh JVM/native theo low, expected và high workload. Đưa release frequency, replica count, cold starts, resource price và maintenance effort vào sensitivity analysis.

Nếu native chỉ có lợi trong một kịch bản traffic hiếm hoặc khi bỏ qua engineering cost, quyết định cần được xem lại. Nếu native giảm compute đáng kể ở workload thực tế và đáp ứng hard gates, chi phí build cao hơn có thể chấp nhận.

## 19. Quy trình review và phê duyệt migration

Một quyết định có thể được review theo trình tự:

1. Ghi pain point và baseline JVM.
2. Chọn vertical slice đại diện.
3. Xác định dependency/native risk.
4. Xây acceptance criteria và SLO gates.
5. Thực hiện AOT/native build và native tests.
6. Kiểm tra final container/observability/security.
7. Chạy canary hoặc production-like workload.
8. Tính TCO và maintenance effort.
9. Xác định owner và upgrade calendar.
10. Phê duyệt mở rộng, hybrid hoặc giữ JVM.

Quyết định cần lưu bằng chứng và giả định. Nếu workload, dependency hoặc platform thay đổi đáng kể, review lại lựa chọn runtime.

## 20. Ví dụ decision matrix cho ba loại service

| Loại service | Đặc điểm | Hướng lựa chọn ban đầu |
|---|---|---|
| API scale-to-zero | Nhiều cold start, traffic burst, dependency native-compatible | Ưu tiên pilot Native Image |
| Backend chạy liên tục | Ít restart, throughput ổn định, JVM đã đạt SLO | Giữ JVM trừ khi memory/TCO cho thấy lợi ích native |
| Plugin/script platform | Nạp code mới sau deploy, runtime bytecode generation | Ưu tiên JVM hoặc tách dynamic engine |

Đây là hướng đánh giá, không phải kết luận cho mọi hệ thống cùng loại. Ví dụ backend chạy liên tục vẫn có thể phù hợp native nếu memory density là chi phí lớn; API scale-to-zero vẫn có thể không phù hợp nếu dependency không tương thích.

## 21. Bài thực hành: lập acceptance và maintenance plan cho Order API

**Bối cảnh:** Order API hiện chạy JVM, có nhiều dependency Spring Data, JSON serialization, HTTP clients và một số integration tùy chọn. Nhóm đang cân nhắc native cho production.

**Bước 1 — Viết mục tiêu.** Chọn một pain point đo được như time-to-ready hoặc memory per replica.

**Bước 2 — Lấy JVM baseline.** Thu startup/readiness, RSS, CPU, throughput, latency, CI time, image size và error rate.

**Bước 3 — Lập dependency inventory.** Ghi version, native support, reflection/proxy/resource/JNI behavior và owner.

**Bước 4 — Chọn slice.** Chạy một vertical flow qua AOT/native và final image.

**Bước 5 — Viết hard gates.** Xác định functional, compatibility, security, SLO, observability và rollback criteria.

**Bước 6 — Tính maintenance.** Ước lượng engineer-hours cho hints, native tests, toolchain upgrades, CVE rebuild và incident support.

**Bước 7 — Benchmark.** So sánh JVM/native cùng workload, resource limits và môi trường.

**Bước 8 — Tính TCO.** Quy đổi CI, registry, runtime, observability và engineering cost theo tháng/quý.

**Bước 9 — Review lựa chọn.** Chọn native, JVM hoặc hybrid; ghi giả định, risk, owner và ngày review lại.

Tiêu chí hoàn thành: acceptance criteria có thể kiểm chứng; baseline và native evidence cùng điều kiện; maintenance owner được chỉ định; TCO có cả chi phí kỹ thuật; quyết định runtime và rollback được ghi nhận.

## 22. Kết luận

Chỉ chấp nhận Spring Boot Native Image khi functional behavior đúng, dependency tương thích, native tests và final image tests đạt, SLO được đáp ứng, security/observability đầy đủ và có người chịu trách nhiệm duy trì. Startup nhanh là một lợi ích, không phải tiêu chí duy nhất.

Native Image có chi phí bảo trì liên tục ở GraalVM/toolchain, AOT, RuntimeHints, dependency upgrades, native tests, container ABI, SBOM và incident diagnostics. Nếu service ít cold start, JVM đã đạt SLO, hoặc ứng dụng cần dynamic class loading/bytecode generation không được hỗ trợ, tiếp tục dùng JVM thường là quyết định tốt hơn. Chọn runtime theo TCO và yêu cầu thực tế; có thể dùng hybrid khi các workload có đặc tính khác nhau và ranh giới vận hành đủ rõ.
