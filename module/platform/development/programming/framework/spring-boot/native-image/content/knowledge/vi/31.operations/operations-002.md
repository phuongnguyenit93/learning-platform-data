# Timeout khởi động, readiness và cơ chế tự khởi động lại của nền tảng

## 1. Vì sao native startup nhanh vẫn cần cấu hình timeout và probe?

GraalVM Native Image thường rút ngắn thời gian khởi động Spring Boot so với JVM trong nhiều ứng dụng. Tuy nhiên, thời gian từ lúc container được tạo đến khi service thực sự nhận traffic còn gồm scheduling, image pull, process startup, Spring ApplicationContext initialization, kết nối dependency và readiness checks.

Một native process có thể chạy rất nhanh nhưng vẫn chưa sẵn sàng phục vụ vì database chưa reachable, migration chưa hoàn tất, cache chưa warm hoặc listener chưa đăng ký. Ngược lại, một liveness probe quá nhạy có thể restart process đang khởi động hợp lệ hoặc tạm thời chịu tải cao. Restart liên tục làm mất tiến trình khởi tạo, tăng tải lên dependency và khiến service không bao giờ đạt trạng thái healthy.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, cần cấu hình timeout và probe theo hành vi đo được của ứng dụng cùng nền tảng triển khai. Bài này phân biệt process startup, readiness và liveness; giải thích Kubernetes startup/readiness/liveness probes; trình bày restart/backoff, graceful shutdown và cách kiểm thử các tình huống chậm hoặc lỗi.

## 2. Phân biệt ba trạng thái: started, ready và live

Ba khái niệm trả lời ba câu hỏi khác nhau:

| Trạng thái | Câu hỏi | Ví dụ |
|---|---|---|
| Started | Process và ứng dụng đã hoàn thành giai đoạn khởi động cần thiết chưa? | Native executable chạy, Spring context refresh xong |
| Ready | Instance có thể nhận và xử lý traffic hiện tại không? | HTTP server nhận request, dependency bắt buộc sẵn sàng |
| Live | Process còn hoạt động và có khả năng tiến triển không? | Event loop/thread chính không bị deadlock, ứng dụng không ở trạng thái không thể phục hồi |

Một service có thể started nhưng chưa ready. Ví dụ context đã tạo xong nhưng database connection pool chưa kết nối thành công. Một service có thể ready nhưng một request cụ thể vẫn fail do lỗi nghiệp vụ hoặc dependency không bắt buộc.

Liveness không nên kiểm tra mọi dependency bên ngoài. Nếu database tạm ngắt và liveness fail, nền tảng có thể restart tất cả replica cùng lúc dù restart không thể sửa database. Readiness thường là nơi phù hợp hơn để ngừng gửi traffic tới instance không thể phục vụ.

## 3. Startup time khác time-to-ready

Đo startup bằng thời gian từ process launch đến log “Started …” có thể bỏ sót các bước sau đó. Đối với orchestrator, thời điểm quan trọng thường là khi readiness probe thành công và instance được đưa vào endpoints/service.

Có thể mô hình hóa:

[
T_{ready}=T_{schedule}+T_{imagePull}+T_{process}+T_{context}+T_{dependency}+T_{probe}
]

Không phải mọi nền tảng đều tính từng thành phần như nhau. Công thức giúp xác định phần nào tạo độ trễ. Native Image có thể giảm (T_{process}) và một phần (T_{context}), nhưng không tự giảm image pull, database migration hoặc thời gian chờ dependency.

Khi đo, ghi:
- Container creation và image pull duration.
- Process start timestamp.
- Spring application startup completion.
- Dependency initialization completion.
- Thời điểm readiness chuyển thành true.
- Thời điểm platform bắt đầu route traffic.

Dùng cùng định nghĩa ở JVM và native để so sánh công bằng.

## 4. Timeout cần có ý nghĩa cụ thể

Từ “timeout khởi động” có thể chỉ nhiều giới hạn khác nhau:

- **Container start timeout:** nền tảng chờ process/container bắt đầu.
- **Startup probe window:** thời gian tối đa cho phép ứng dụng khởi động trước khi bị coi là fail.
- **Readiness probe timeout:** thời gian một lần kiểm tra readiness được phép chạy.
- **Liveness probe timeout:** thời gian một lần kiểm tra liveness.
- **Application startup timeout:** giới hạn do script/deployment tool hoặc supervisor đặt.
- **Request timeout:** giới hạn thời gian xử lý request, không phải startup timeout.
- **Termination grace period:** thời gian process có để shutdown trước khi bị kill.

Không dùng một giá trị timeout chung cho tất cả. Mỗi giới hạn cần phản ánh failure mode và hành vi mong muốn của nền tảng.

## 5. Spring Boot Actuator cung cấp health indicators

Spring Boot Actuator có thể expose health endpoint và Kubernetes-oriented health groups khi được cấu hình phù hợp. Ví dụ:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health
```

Trong môi trường Kubernetes, Spring Boot có thể cung cấp các nhóm health như:
- `/actuator/health/liveness`
- `/actuator/health/readiness`

Cần thêm dependency Actuator và xác nhận endpoint path/port thực tế. Không giả định endpoint tồn tại chỉ vì đã thêm YAML. Nếu management server dùng port riêng, probe phải trỏ đúng port.

Health indicator tùy chỉnh cần chạy nhanh, có timeout và không tạo side effect. Tránh thực hiện query nặng, migration hoặc gọi nhiều downstream trong mỗi probe.

## 6. Liveness probe: chỉ phát hiện trạng thái không thể phục hồi

Liveness trả lời liệu process có còn khả năng hoạt động hay cần restart. Những tình huống có thể xem xét fail liveness:

- Application thread bị deadlock nghiêm trọng và không thể phục hồi.
- Internal subsystem thiết yếu bị kẹt vĩnh viễn.
- Process rơi vào trạng thái lỗi mà restart là cơ chế phục hồi đã được thiết kế.
- Watchdog nội bộ phát hiện tiến trình không tiến triển.

Không nên fail liveness chỉ vì:
- Database tạm unavailable.
- Payment provider chậm.
- Một request lỗi.
- Queue đang backlog nhưng process vẫn hoạt động.
- CPU tăng tạm thời trong lúc xử lý burst.

Restart không thể khắc phục dependency outage và có thể tạo restart storm. Nếu service không thể phục vụ vì dependency bắt buộc, readiness thường nên fail để ngừng nhận traffic trong khi process vẫn sống và có thể phục hồi.

## 7. Readiness probe: quyết định có nhận traffic không

Readiness xác định instance có thể nhận request mới hay chưa. Có thể fail readiness khi:

- ApplicationContext chưa hoàn tất.
- Listener chưa bind hoặc subsystem phục vụ chưa khởi tạo.
- Dependency thực sự bắt buộc cho mọi request chưa sẵn sàng.
- Instance đang drain/shutdown.
- Instance quá tải theo chính sách admission control.

Không đưa tất cả dependency vào readiness một cách máy móc. Ví dụ email provider có thể không cần cho API đọc đơn hàng; nếu email service tạm lỗi, không nhất thiết phải loại toàn bộ API khỏi traffic. Thiết kế readiness theo khả năng phục vụ của endpoint/workload.

Readiness thường được nền tảng dùng để thêm/bỏ instance khỏi service endpoints. Nó không tự restart container khi fail.

## 8. Startup probe bảo vệ giai đoạn khởi động

Kubernetes startup probe cho phép ứng dụng có thời gian khởi động dài hơn mà không bị liveness/readiness kiểm tra quá sớm. Khi startup probe chưa thành công, Kubernetes chưa chạy liveness/readiness probe cho container đó.

Ví dụ:

```yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 2
  timeoutSeconds: 1
  failureThreshold: 30
```

Với ví dụ này, cửa sổ tối đa theo phép tính đơn giản xấp xỉ (30 	imes 2 = 60) giây, nhưng thời điểm thực tế còn phụ thuộc initial delay, probe execution và kubelet scheduling. Không coi phép nhân là deadline chính xác tuyệt đối.

Native startup có thể nhanh, nhưng vẫn cần tính đến image pull (không nằm trong startup probe window), context initialization, secret/config mount và dependency setup. Đặt cửa sổ dựa trên phân phối thời gian startup quan sát được, không dựa trên một lần chạy nhanh nhất.

## 9. Ví dụ đầy đủ startup, readiness và liveness trên Kubernetes

```yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 2
  timeoutSeconds: 1
  failureThreshold: 30

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
  successThreshold: 1

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
```

Đây là cấu hình mẫu, không phải giá trị mặc định nên áp dụng cho mọi dịch vụ. Cần điều chỉnh theo startup distribution, probe endpoint latency, platform load và recovery objectives.

Liveness nên có ngưỡng đủ rộng để tránh restart vì một lần timeout ngẫu nhiên. Readiness có thể phản ứng nhanh hơn với trạng thái không thể nhận traffic. Startup probe bảo vệ giai đoạn đầu để liveness không can thiệp quá sớm.

## 10. Probe timeout và failure threshold ảnh hưởng thế nào?

Các tham số chính của Kubernetes probe:

| Tham số | Ý nghĩa |
|---|---|
| `initialDelaySeconds` | Chờ trước lần probe đầu tiên (nếu dùng) |
| `periodSeconds` | Khoảng cách giữa các lần probe |
| `timeoutSeconds` | Timeout cho một lần probe |
| `failureThreshold` | Số lần fail liên tiếp trước khi hành động tương ứng |
| `successThreshold` | Số lần pass liên tiếp để chuyển sang success; liveness/startup thường yêu cầu 1 |
| `terminationGracePeriodSeconds` | Thời gian cho shutdown sau khi container cần kết thúc |

Với liveness/startup, khi đạt failure threshold, kubelet có thể restart container theo restart policy. Với readiness, endpoint không ready khiến pod bị loại khỏi service endpoints; container không bị restart chỉ vì readiness fail.

Probe endpoint phải nhanh hơn timeout trong điều kiện tải dự kiến. Nếu probe tự query database chậm, timeout có thể phản ánh latency database thay vì trạng thái process.

## 11. Dependency readiness và health group

Spring Boot health groups cho phép tách liveness/readiness. Dependency ngoài chỉ nên nằm trong readiness khi service không thể xử lý các request cần thiết nếu dependency đó unavailable.

Ví dụ, nếu toàn bộ request ghi đơn hàng cần database, readiness có thể bao gồm datasource health indicator. Nhưng nếu ứng dụng vẫn có thể phục vụ endpoint đọc cache hoặc metadata khi database mất kết nối, một readiness tổng thể quá nghiêm ngặt có thể loại instance không cần thiết.

Một thiết kế tốt:
- Liveness chỉ kiểm tra trạng thái nội bộ.
- Readiness phản ánh khả năng phục vụ workload chính.
- Health indicator bên ngoài có timeout ngắn và không retry kéo dài.
- Dependency optional được quan sát bằng metrics/alert riêng.
- Trạng thái degraded có thể được biểu diễn mà không luôn làm readiness fail.

Tránh health check tạo tải đáng kể lên database khi hàng trăm replica cùng probe định kỳ.

## 12. Restart policy và vai trò của orchestrator

Restart policy xác định nền tảng làm gì khi process kết thúc hoặc container fail. Với Kubernetes, hành vi phụ thuộc workload controller và `restartPolicy` của Pod; Deployment thông thường dùng `Always`. Khi container exit, kubelet có thể khởi động lại container trong cùng Pod.

Cần phân biệt:
- Probe liveness/startup thất bại có thể dẫn tới container restart.
- Readiness fail chỉ ảnh hưởng trạng thái nhận traffic.
- Process tự exit có thể kích hoạt restart theo policy.
- Pod bị xóa hoặc node mất sẽ do controller/scheduler tạo lại hoặc đặt lại workload.

Không thiết kế ứng dụng tự restart chính nó bằng vòng lặp shell nếu orchestrator đã quản lý lifecycle. Một supervisor bổ sung có thể che mất exit code và làm tín hiệu shutdown sai.

## 13. CrashLoopBackOff và restart backoff

Nếu container liên tục exit hoặc bị restart do probe failure, Kubernetes áp dụng backoff trước các lần restart tiếp theo và có thể hiển thị trạng thái `CrashLoopBackOff`. Backoff giúp tránh restart liên tục quá nhanh nhưng không sửa nguyên nhân gốc.

Điều tra:

```bash
kubectl describe pod <pod-name>
kubectl logs <pod-name> --previous
kubectl get events --sort-by=.lastTimestamp
```

Kiểm tra:
- Exit code và termination reason.
- OOMKilled.
- Startup/liveness probe failures.
- Config/secret mount.
- Port bind và permission.
- Native library/loader error.
- Dependency timeout.
- Graceful shutdown có vượt grace period không.

Không tăng restart backoff hoặc probe threshold để che một crash deterministic. Tìm stack trace/log đầu tiên và tái hiện bằng cùng image digest.

## 14. OOM và restart khác với probe failure

Container có thể bị OOMKilled khi memory vượt limit. Đây không phải liveness failure. Native Image có thể dùng ít heap hơn một số JVM workload, nhưng RSS vẫn bao gồm code, thread stacks, native memory, mapped files và libraries.

Khi container restart:
- Xem termination reason.
- Kiểm tra cgroup memory peak.
- Đối chiếu heap limit với container limit.
- Xem allocation burst và live set.
- Xem CPU throttling có làm probe timeout không.
- Xem native memory/third-party library usage.

Không giải quyết OOM bằng cách tăng liveness timeout. Cũng không đặt heap max bằng toàn bộ container memory mà không chừa headroom.

## 15. Graceful shutdown và termination grace period

Khi Deployment rollout hoặc Pod bị dừng, Kubernetes gửi SIGTERM cho process trong container, sau đó chờ termination grace period trước khi có thể gửi SIGKILL.

Spring Boot có graceful shutdown support. Cấu hình có thể gồm:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
```

Thời gian cụ thể cần đồng bộ với `terminationGracePeriodSeconds` của Pod và thời gian drain của load balancer. Đừng đặt Spring shutdown timeout dài hơn toàn bộ grace period vì process có thể bị kill trước khi hoàn tất.

Trong quá trình shutdown:
- Ngừng nhận request mới.
- Đánh dấu readiness false/drain traffic.
- Hoàn tất request đang xử lý trong giới hạn.
- Đóng connection pool, broker consumer và scheduler.
- Flush log/telemetry nếu có thể.
- Thoát với exit code phù hợp.

Kiểm thử khi có request đang chạy, không chỉ dừng một process idle.

## 16. Timeout ở Docker và nền tảng khác

Docker không có bộ startup/readiness/liveness probes tương đương Kubernetes theo cùng semantics. Docker HEALTHCHECK đánh giá trạng thái health của container; restart policy như `--restart=unless-stopped` điều khiển restart khi process/container exit, không tự động có cùng hành vi với Kubernetes probes.

Ví dụ:

```bash
docker run -d   --name orders-service   --restart unless-stopped   -p 8080:8080   orders-service:1.0
```

Nếu dùng Docker HEALTHCHECK, lệnh check phải tồn tại trong image. Distroless/scratch có thể không có shell hoặc curl; dùng exec-form healthcheck binary nếu có, hoặc để hệ thống bên ngoài kiểm tra HTTP.

Các nền tảng như ECS, Nomad hoặc systemd có mô hình health/restart riêng. Ánh xạ khái niệm startup/readiness/liveness sang cấu hình nền tảng tương ứng; không copy nguyên YAML Kubernetes sang nền tảng khác.

## 17. Đặt timeout dựa trên số liệu startup

Đo thời gian từ container creation đến readiness trong nhiều lần chạy và các điều kiện:
- Cold image pull và image đã cache.
- Cold node và node đang có tải.
- Dependency nhanh và dependency chậm.
- Startup bình thường và startup có migration/cache initialization.
- CPU/memory limit production.
- Các architecture được phát hành.

Dùng percentile như p95/p99 thay vì chỉ average. Startup probe window nên bao phủ các trường hợp hợp lệ nhưng không kéo dài vô hạn khi ứng dụng bị treo.

Ví dụ nếu p99 time-to-ready là 18 giây trong điều kiện production-like, có thể đặt startup window lớn hơn để có headroom. Giá trị cụ thể cần cộng thêm biến động môi trường và mục tiêu recovery. Không dùng ví dụ 60 giây trong tài liệu như một con số mặc định cho mọi ứng dụng.

## 18. Kiểm thử probe và restart behavior

Cần kiểm tra không chỉ trường hợp khỏe mạnh mà cả các trạng thái lỗi:

| Tình huống | Kết quả mong muốn |
|---|---|
| Startup bình thường | Startup probe pass, sau đó readiness pass |
| Startup chậm hợp lệ | Startup window đủ để process hoàn tất |
| Context init fail | Process/log thể hiện lỗi; restart theo policy hoặc rollout fail |
| Database tạm unavailable | Readiness phản ánh khả năng phục vụ; liveness không restart vô ích |
| Process deadlock nội bộ | Liveness phát hiện theo cơ chế đã thiết kế |
| CPU throttling | Probe timeout không gây restart storm do cấu hình quá nhạy |
| Shutdown có request đang xử lý | Traffic drain và process kết thúc trong grace period |
| OOM | Event/metrics cho thấy OOM, sizing được điều chỉnh |

Có thể dùng test environment để chặn network tới dependency, tạo tải CPU hoặc gửi SIGTERM. Không thực hiện fault injection trên production nếu chưa có kế hoạch kiểm soát.

## 19. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Pod restart trước khi app ready | Thiếu startup probe hoặc startup window quá ngắn | Đo time-to-ready và cấu hình startup probe |
| Readiness fail nhưng container vẫn chạy | Dependency/service chưa sẵn sàng | Xem readiness indicator và dependency |
| Liveness restart liên tục | Probe kiểm tra dependency ngoài hoặc timeout quá ngắn | Giảm phạm vi liveness, tăng tolerance dựa trên đo |
| CrashLoopBackOff | Process crash, OOM hoặc probe failure | Describe pod, previous logs, events |
| Native process startup nhanh nhưng traffic đến muộn | Image pull, scheduling, dependency hoặc readiness | Phân rã time-to-ready |
| Shutdown bị SIGKILL | Grace period ngắn hoặc lifecycle phase treo | Đồng bộ shutdown timeout và grace period |
| Health endpoint timeout | Probe endpoint quá nặng hoặc port/path sai | Tạo health check nhẹ, kiểm tra config |
| Container không restart dù readiness fail | Readiness chỉ loại khỏi traffic | Dùng liveness cho trạng thái không thể phục hồi |

## 20. Bài thực hành: cấu hình lifecycle cho Order API native

**Bối cảnh:** Order API chạy trên Kubernetes, native executable có startup nhanh nhưng cần kết nối database và message broker trước khi nhận request ghi đơn hàng.

**Bước 1 — Đo baseline.** Ghi process start, Spring context ready, dependency ready và thời điểm endpoint nhận traffic trong nhiều lần chạy.

**Bước 2 — Bật Actuator probes.** Thêm Actuator dependency, cấu hình health groups và xác nhận endpoint liveness/readiness trên port thực tế.

**Bước 3 — Thiết kế liveness.** Chỉ kiểm tra trạng thái nội bộ; không để database/payment provider outage gây restart tất cả replica.

**Bước 4 — Thiết kế readiness.** Bao gồm các dependency bắt buộc cho workload cần phục vụ; timeout indicator ngắn và có kiểm soát.

**Bước 5 — Cấu hình startup probe.** Chọn failure threshold/period dựa trên p99 time-to-ready cộng headroom.

**Bước 6 — Đồng bộ shutdown.** Bật graceful shutdown, cấu hình phase timeout và Pod termination grace period.

**Bước 7 — Fault injection.** Thử database unavailable, startup chậm, CPU throttling, process crash và SIGTERM khi có request.

**Bước 8 — Quan sát restart.** Ghi restart count, CrashLoopBackOff events, OOMKilled, probe failures và time-to-recovery.

Tiêu chí hoàn thành: startup window không cắt ngang khởi động hợp lệ; readiness chỉ nhận traffic khi service có thể phục vụ; liveness không gây restart storm; shutdown hoàn tất trong grace period; các failure modes có log/metrics và cách xử lý rõ.

## 21. Kết luận

Native Image có thể rút ngắn process startup, nhưng vận hành ổn định còn phụ thuộc readiness, dependency, image pull, probe và shutdown. Hãy phân biệt started, ready và live; dùng startup probe bảo vệ giai đoạn khởi động, readiness để điều khiển traffic và liveness để phát hiện trạng thái process không thể phục hồi.

Đặt timeout theo p95/p99 time-to-ready và probe latency đo trong điều kiện production-like. Tránh để liveness phụ thuộc vào dịch vụ bên ngoài, đồng bộ graceful shutdown với termination grace period và điều tra CrashLoopBackOff/OOM bằng event cùng log trước đó. Một cấu hình tốt giúp native service khởi động nhanh mà không tạo restart loop hoặc nhận traffic trước khi sẵn sàng.
