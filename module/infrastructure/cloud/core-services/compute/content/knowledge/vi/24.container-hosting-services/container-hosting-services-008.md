# Log, metric và xử lý lỗi khi container bị khởi động lại

Container có thể khởi động lại khi tiến trình chính thoát, bị runtime dừng, vượt giới hạn bộ nhớ, thất bại health check hoặc node gặp sự cố. Một lần restart có thể chỉ là hoạt động bình thường trong quá trình rollout; nhiều lần restart liên tiếp có thể làm gián đoạn request, mất dữ liệu tạm và khiến workload rơi vào vòng lặp không phục hồi.

Muốn xử lý đúng, cần giữ được bằng chứng của lần chạy trước, xác định lý do container kết thúc, đối chiếu log với metric và event của nền tảng, rồi mới quyết định sửa cấu hình, rollback, tăng tài nguyên hay thay đổi restart policy. Restart policy giúp runtime thử chạy lại container; nó không tự sửa lỗi ứng dụng hoặc bảo đảm dữ liệu được bảo toàn.

## 1. Phân biệt container, container process và Pod

Container là môi trường thực thi được tạo từ image. Trong đa số mô hình, container có một tiến trình chính; khi tiến trình này kết thúc, container chuyển sang trạng thái stopped. Runtime hoặc bộ điều phối có thể tạo lại tiến trình/container theo restart policy.

Trong Kubernetes, Pod là đơn vị triển khai nhỏ nhất và có thể chứa một hoặc nhiều container. Khi một container trong Pod thoát, kubelet có thể khởi động lại container đó bên trong cùng Pod. Khi Pod bị xóa và tạo lại, Pod mới có UID mới; tên có thể được tái sử dụng, chẳng hạn với StatefulSet. Restart count của Pod mới bắt đầu lại. Vì vậy, cần phân biệt:

- **Container restart:** container trong cùng Pod được chạy lại; Pod UID thường giữ nguyên và restart count tăng.
- **Pod replacement:** Pod cũ bị xóa, Deployment/StatefulSet/Job tạo Pod mới; Pod UID thay đổi.
- **Node replacement:** máy chạy Pod bị thay thế hoặc mất; workload được scheduler đặt lên node khác nếu controller và storage cho phép.
- **Application restart:** tiến trình con hoặc worker bên trong container tự khởi động lại, trong khi container chính vẫn sống; runtime có thể không tăng restart count.

Log, metric và event cần chứa đủ định danh để phân biệt các trường hợp này. Chỉ nhìn tên Pod hoặc container name là chưa đủ vì tên có thể được tái sử dụng; nên ghi thêm namespace, Pod UID, container ID, node và thời điểm.

## 2. Những nguyên nhân thường khiến container restart

Một container có thể kết thúc vì nhiều nguyên nhân:

| Nguyên nhân | Dấu hiệu thường gặp | Nơi cần kiểm tra |
|---|---|---|
| Ứng dụng tự thoát | Exit code khác 0, exception hoặc log fatal | Log ứng dụng, cấu hình, dependency và mã lỗi |
| Hoàn tất công việc bình thường | Exit code 0 | Loại workload, command/args và restart policy |
| OOM kill | `OOMKilled`, memory event, process bị SIGKILL | Memory limit, cgroup, node pressure và runtime metrics |
| Liveness probe thất bại | Event probe failed, container restart | Endpoint, timeout, startup time và ngưỡng probe |
| Bị dừng khi rollout/scale | SIGTERM, exit code thường gặp 143 | Deployment event, termination grace period và shutdown logic |
| Node hoặc runtime lỗi | Pod bị evict, node NotReady, runtime event | Kubelet, container runtime, node condition và cloud event |
| Cấu hình sai | Thiếu biến môi trường, secret, file hoặc quyền | Manifest, ConfigMap/Secret, volume mount và UID/GID |
| Image/command không chạy | `ImagePullBackOff`, `ErrImagePull`, `CreateContainerError` hoặc process không khởi động | Image reference, registry, entrypoint, permission và architecture |

Một container restart không nhất thiết là sự cố. Ví dụ, Job chạy xong rồi thoát là hành vi mong muốn. Ngược lại, một container luôn ở trạng thái Running cũng không chứng minh ứng dụng khỏe; tiến trình có thể bị treo hoặc không xử lý request.

## 3. Exit code và termination reason

Exit code là tín hiệu đầu tiên để định hướng điều tra, nhưng không phải bằng chứng đầy đủ về nguyên nhân.

- `0`: tiến trình kết thúc thành công theo quy ước của ứng dụng. Với service dài hạn, exit code 0 vẫn có thể gây restart nếu policy yêu cầu chạy liên tục.
- Giá trị khác `0`: ứng dụng hoặc runtime báo kết thúc bất thường; cần xem log và tài liệu của chương trình để hiểu ý nghĩa cụ thể.
- `137`: thường tương ứng với `128 + 9`, tức tiến trình nhận SIGKILL. OOM kill là một nguyên nhân phổ biến, nhưng quản trị viên hoặc runtime cũng có thể gửi SIGKILL.
- `143`: thường tương ứng với `128 + 15`, tức tiến trình nhận SIGTERM. Có thể xảy ra khi rollout hoặc dừng có kiểm soát; ứng dụng có thể chưa hoàn tất shutdown.

Không kết luận OOM chỉ từ exit code 137. Hãy đối chiếu termination reason, kernel/cgroup event, memory usage và thời điểm kết thúc. Tương tự, exit code 143 không tự chứng minh shutdown đã hoàn tất an toàn; cần xem log ứng dụng và thời gian graceful termination.

Trong Kubernetes, trạng thái container thường cung cấp `state`, `lastState`, `reason`, `exitCode`, `startedAt` và `finishedAt`. Trường `lastState.terminated` rất hữu ích vì mô tả lần kết thúc gần nhất của container hiện tại.

## 4. Restart policy trong Docker

Docker có các restart policy phổ biến:

| Policy | Hành vi khái quát |
|---|---|
| `no` | Không tự động restart khi container thoát; đây là mặc định nếu không chỉ định policy |
| `on-failure` | Restart khi process thoát với exit code khác 0; có thể giới hạn số lần thử |
| `always` | Docker cố gắng restart container khi nó dừng; container cũng có thể được khởi động lại khi Docker daemon khởi động lại theo điều kiện policy |
| `unless-stopped` | Tương tự `always`, nhưng giữ trạng thái dừng thủ công qua lần daemon restart theo semantics của Docker |

Ví dụ:

```bash
docker run -d \
  --name orders-api \
  --restart unless-stopped \
  -p 8080:8080 \
  registry.example.com/commerce/orders-api:1.4.0
```

Giới hạn số lần thử với `on-failure`:

```bash
docker run -d \
  --name batch-worker \
  --restart on-failure:5 \
  registry.example.com/commerce/batch-worker:1.4.0
```

Restart policy chỉ áp dụng cho vòng đời container do Docker quản lý. Nó không thay thế health check, giám sát, xử lý dữ liệu hoặc cơ chế retry của ứng dụng. Nếu container liên tục thoát vì cấu hình sai, `always` có thể tạo vòng lặp restart và làm log tăng nhanh.

Có thể xem policy và trạng thái:

```bash
docker inspect orders-api --format '{{json .HostConfig.RestartPolicy}}'
docker inspect orders-api --format '{{json .State}}'
```

## 5. Restart policy trong Kubernetes

Kubernetes đặt `restartPolicy` ở cấp Pod. Các giá trị hợp lệ là `Always`, `OnFailure` và `Never`.

| Policy | Hành vi khái quát | Workload thường gặp |
|---|---|---|
| `Always` | Kubelet khởi động lại container khi container kết thúc, bất kể exit code | Deployment, StatefulSet và workload service dài hạn |
| `OnFailure` | Khởi động lại container khi exit code khác 0 | Job cần retry container trong Pod |
| `Never` | Không khởi động lại container đã kết thúc trong Pod đó | Job cần controller tạo Pod khác hoặc xử lý lỗi theo chính sách riêng |

Deployment và StatefulSet thông thường dùng `restartPolicy: Always`; Pod template của Job thường dùng `OnFailure` hoặc `Never`. Controller như Job hoặc Deployment có trách nhiệm quản lý Pod theo mục tiêu của workload. Không thể đặt `restartPolicy: OnFailure` cho Pod template của Deployment.

Ví dụ Pod chạy service:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders-api
spec:
  restartPolicy: Always
  containers:
    - name: api
      image: registry.example.com/commerce/orders-api:1.4.0
      ports:
        - name: http
          containerPort: 8080
```

`CrashLoopBackOff` là trạng thái backoff của Kubernetes khi container liên tục kết thúc và kubelet trì hoãn lần restart tiếp theo. Đây không phải một restart policy riêng và cũng không phải nguyên nhân gốc. Cần tìm termination reason và log của lần chạy trước.

## 6. Lấy log của container hiện tại và lần chạy trước

Khi container restart, log của lần chạy cũ có thể không còn trong luồng log hiện tại. Phải thu thập log trước khi Pod bị thay thế hoặc node dọn file log.

Với Docker:

```bash
docker logs --timestamps --since 30m orders-api
docker logs --timestamps --tail 200 orders-api
```

Với Kubernetes:

```bash
kubectl logs pod/orders-api -n production -c api
kubectl logs pod/orders-api -n production -c api --previous
```

`--previous` yêu cầu log của container instance trước còn được runtime giữ và có thể truy xuất. Lệnh này không phải kho lưu trữ lịch sử dài hạn; nếu Pod đã bị thay thế hoặc node đã dọn log, dữ liệu có thể không còn. Với Pod nhiều container, chỉ rõ `-c` để tránh lấy nhầm container.

Để lấy log theo label:

```bash
kubectl logs -n production -l app=orders-api \
  --all-containers=true --prefix --since=20m
```

`--prefix` giúp phân biệt nguồn log. Khi điều tra restart, nên lưu log, mô tả Pod và event trước khi xóa Pod hoặc rollout lại, vì thao tác đó có thể làm mất bằng chứng cần thiết.

## 7. Thu thập trạng thái và event trong Kubernetes

Các lệnh cơ bản:

```bash
kubectl get pods -n production -o wide
kubectl describe pod orders-api -n production
kubectl get events -n production --sort-by=.lastTimestamp
kubectl get pod orders-api -n production -o yaml
```

Tập trung vào các trường:

- `status.containerStatuses[].restartCount`: số lần container restart trong Pod hiện tại.
- `state.waiting.reason`: lý do container chưa chạy, ví dụ `CrashLoopBackOff` hoặc `ImagePullBackOff`.
- `lastState.terminated.reason`: lý do lần kết thúc trước, ví dụ `OOMKilled` hoặc `Error`.
- `lastState.terminated.exitCode`: exit code của lần kết thúc.
- `startedAt` và `finishedAt`: thời điểm bắt đầu/kết thúc.
- `ready`: container có đang được đánh dấu sẵn sàng hay không.
- Events: probe failure, image pull error, eviction, scheduling hoặc mount error.

Ví dụ xem restart count và termination reason bằng JSONPath:

```bash
kubectl get pod orders-api -n production \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{" restarts="}{.restartCount}{" reason="}{.lastState.terminated.reason}{" exit="}{.lastState.terminated.exitCode}{"\n"}{end}'
```

Nếu Pod do Deployment quản lý, xem cả ReplicaSet và rollout:

```bash
kubectl get deployment,replicaset -n production
kubectl rollout status deployment/orders-api -n production
kubectl rollout history deployment/orders-api -n production
```

Tên tài nguyên trong ví dụ cần thay theo môi trường. `kubectl describe` thường là điểm bắt đầu tốt vì kết hợp trạng thái, cấu hình probe và event liên quan.

## 8. Docker diagnostics: state, events và tài nguyên

Docker cung cấp trạng thái container và event để xác định lúc nào container start, die, restart hoặc bị kill:

```bash
docker inspect orders-api --format '{{json .State}}'
docker inspect orders-api --format '{{.RestartCount}}'
docker events --since 30m --filter container=orders-api
docker stats --no-stream orders-api
```

Các thông tin cần lưu:

- `Status`, `Running`, `Restarting`, `OOMKilled` và `ExitCode` trong state.
- `StartedAt` và `FinishedAt` để đối chiếu timeline.
- `RestartCount` để biết container đã restart bao nhiêu lần trong vòng đời hiện tại.
- `OOMKilled` và memory limit để kiểm tra khả năng bị kill do memory.
- Event `die`, `start`, `restart`, `kill` hoặc `oom` nếu runtime phát ra.
- CPU, memory, network và block I/O trước/sau khi sự cố xảy ra.

`docker stats` là ảnh chụp hiện tại, không thay thế time-series metrics. Khi lỗi xảy ra nhanh, cần hệ thống giám sát lưu metric liên tục để có thể xem lại lịch sử.

## 9. Thiết kế log để điều tra restart

Ứng dụng container nên ghi log vận hành ra `stdout` và `stderr` để runtime hoặc nền tảng thu thập. Nếu chỉ ghi log vào file trong writable layer, log có thể mất khi container bị xóa hoặc thay thế. Nếu cần ghi file, hãy dùng volume hoặc agent thu thập file có cấu hình vòng đời rõ ràng.

Log có cấu trúc nên chứa các trường hữu ích:

| Trường | Mục đích |
|---|---|
| `timestamp` | Xếp sự kiện theo thời gian; ưu tiên UTC hoặc chuẩn thời gian thống nhất |
| `severity` | Phân biệt DEBUG, INFO, WARN, ERROR, FATAL |
| `service.name` | Xác định workload |
| `environment` | Phân biệt production, staging và development |
| `container.id` | Nhận diện container instance |
| `pod.name`, `pod.uid`, `namespace` | Định vị workload trong Kubernetes |
| `node.name` hoặc `host.id` | Xác định máy chạy container |
| `restart.sequence` hoặc startup ID | Phân biệt các lần chạy nếu ứng dụng tự phát sinh được |
| `trace_id`, `span_id`, `request_id` | Liên kết log với request và trace khi có context |
| `event` / `error.type` | Phân loại sự kiện và loại lỗi |
| `message` | Diễn giải ngắn gọn, có ngữ cảnh |

Ví dụ log JSON:

```json
{
  "timestamp": "2026-11-22T08:15:31.442Z",
  "severity": "ERROR",
  "service.name": "orders-api",
  "environment": "production",
  "namespace": "production",
  "pod.name": "orders-api-7b9c8f6d4d-k2m8p",
  "container.name": "api",
  "container.id": "containerd://a12b34c56d",
  "event": "database_connection_failed",
  "error.type": "ConnectionTimeout",
  "message": "Could not obtain a database connection before timeout"
}
```

Đây là schema minh họa; tên trường cần thống nhất với logging pipeline. Không ghi password, access token, cookie, private key, request body nhạy cảm hoặc dữ liệu cá nhân không cần thiết. Log lỗi nên có stack trace khi hữu ích, nhưng cần giới hạn dữ liệu và tránh lặp stack trace hàng nghìn lần trong vòng restart.

## 10. Log startup và shutdown có chủ đích

Một container khó điều tra nếu log không thể hiện rõ vòng đời. Ứng dụng nên ghi các sự kiện:

- Bắt đầu process và phiên bản build/image.
- Nạp cấu hình và xác thực các dependency bắt buộc.
- Bắt đầu lắng nghe port hoặc mở consumer.
- Readiness chuyển sang trạng thái phục vụ.
- Nhận tín hiệu shutdown và bắt đầu drain.
- Ngừng nhận request/message mới.
- Hoàn tất hoặc timeout khi đóng connection, flush dữ liệu và dừng worker.
- Lý do ứng dụng chủ động thoát nếu có thể xác định.

Không ghi secret hoặc toàn bộ cấu hình có chứa credential khi startup. Chỉ ghi tên cấu hình, trạng thái và giá trị không nhạy cảm cần cho điều tra.

Với ứng dụng nhiều worker, log nên cho biết số worker, concurrency và queue state tại thời điểm khởi động. Khi shutdown, cần ghi nhận số request đang xử lý và kết quả drain để phân biệt restart do crash với restart do rollout.

## 11. Metric cần theo dõi khi container restart

Log cho biết chi tiết sự kiện; metric cho thấy xu hướng và mức ảnh hưởng. Các metric quan trọng gồm:

| Metric | Ý nghĩa | Cách dùng |
|---|---|---|
| Container restart count/rate | Số lần restart hoặc tốc độ restart | Phát hiện vòng lặp restart và so sánh theo service/node |
| Last termination reason/exit code | Nguyên nhân và mã kết thúc gần nhất | Phân nhóm lỗi OOM, app exit hoặc bị dừng |
| Container memory working set | Bộ nhớ đang dùng | Đối chiếu memory limit và OOM event |
| Memory limit utilization | Mức dùng so với limit | Phát hiện tiến trình tiến sát giới hạn |
| CPU usage/throttling | CPU sử dụng và thời gian bị throttling | Tìm startup chậm, timeout hoặc CPU limit quá thấp |
| Probe failure count | Số lần liveness/readiness/startup probe thất bại | Phát hiện endpoint sai hoặc cấu hình probe không phù hợp |
| Request rate/error/latency | Tác động tới người dùng | Biết restart có gây 5xx hoặc latency tăng không |
| Queue depth/consumer lag | Công việc đang chờ | Phát hiện worker restart làm backlog tăng |
| Node condition/pressure | Trạng thái máy chạy workload | Phân biệt lỗi container với node memory/disk/PID pressure |
| Image pull/startup duration | Thời gian thay thế container | Đánh giá thời gian phục hồi và rollout |

Nên quan sát restart count cùng thời điểm, termination reason, memory, CPU, probe event và service SLI. Một restart lẻ có thể không đáng báo động; restart liên tục trên nhiều replica hoặc đi kèm error rate tăng cần được ưu tiên.

## 12. Giới hạn và thu thập log của Docker

Docker dùng logging driver để chuyển stdout/stderr tới nơi lưu log. Driver mặc định phụ thuộc cấu hình daemon. Có thể kiểm tra:

```bash
docker info --format '{{.LoggingDriver}}'
docker inspect orders-api --format '{{.HostConfig.LogConfig.Type}}'
```

Với `json-file`, có thể cấu hình rotation khi tạo container:

```bash
docker run -d \
  --name orders-api \
  --log-driver json-file \
  --log-opt max-size=10m \
  --log-opt max-file=5 \
  registry.example.com/commerce/orders-api:1.4.0
```

Giới hạn trên là ví dụ. `max-size` và `max-file` cần sizing theo tốc độ log và thời gian cần lưu tại node. Rotation giúp tránh log lấp đầy disk, nhưng log cũ sẽ bị loại khỏi node; cần ship log tới hệ thống tập trung nếu yêu cầu điều tra dài hạn.

Nếu dùng logging driver gửi thẳng tới backend, kiểm tra buffering, retry, network outage và hành vi khi backend không nhận log. Một cấu hình log không phù hợp có thể làm ứng dụng block hoặc mất log khi collector ngừng hoạt động.

## 13. Thu thập log trên Kubernetes

Kubernetes thường thu thập stdout/stderr của container thông qua container runtime và kubelet. Log file trên node có thể được rotate theo cấu hình kubelet/runtime; khả năng truy xuất qua `kubectl logs` phụ thuộc log file còn tồn tại.

Các lựa chọn tập trung log thường gồm:

- Agent dạng DaemonSet chạy trên từng node và đọc log container.
- Managed logging agent hoặc dịch vụ observability của nền tảng.
- Sidecar collector cho một số trường hợp cần xử lý log riêng, nhưng sidecar làm tăng tài nguyên và độ phức tạp.
- Ứng dụng gửi log trực tiếp qua giao thức được hỗ trợ, nếu có buffering và bảo vệ phù hợp.

Với agent node-level, cần lọc namespace, container, label và mức độ log; tránh thu thập trùng giữa agent và sidecar. Với sidecar, cần tính memory/CPU, volume chia sẻ và hành vi khi sidecar lỗi.

Đặt retention phù hợp với tốc độ ingest và yêu cầu điều tra. Log startup, shutdown, lỗi và audit có thể cần chính sách khác log debug thông thường.

## 14. Log của kubelet và container runtime

Nếu nhiều container trên cùng node cùng restart hoặc Pod không thể tạo container, lỗi có thể nằm ở node hoặc runtime thay vì ứng dụng. Khi có quyền truy cập node, kiểm tra trạng thái và log của kubelet/container runtime theo hệ điều hành và bản phân phối.

Ví dụ trên Linux dùng systemd:

```bash
sudo journalctl -u kubelet --since "30 minutes ago" --no-pager
sudo journalctl -u containerd --since "30 minutes ago" --no-pager
```

Tên service và cách truy cập log có thể khác theo managed Kubernetes, runtime hoặc distribution. Một số nền tảng không cho phép truy cập trực tiếp node; khi đó dùng node problem detector, control plane events hoặc log service do nhà cung cấp cung cấp.

Nếu có lỗi disk pressure, inode exhaustion, PID exhaustion hoặc container runtime mất kết nối, nhiều Pod có thể bị ảnh hưởng đồng thời. Không nên chỉ restart từng container trong khi node vẫn đang gặp sự cố nền.

## 15. Health check: liveness, readiness và startup probe

Probe xác định ứng dụng có khởi động, tiếp tục sống và sẵn sàng nhận traffic hay không. Dùng sai probe là nguyên nhân phổ biến khiến container restart không cần thiết.

| Probe | Câu hỏi | Khi thất bại |
|---|---|---|
| Startup probe | Ứng dụng đã khởi động xong chưa? | Kubelet tiếp tục thử tới ngưỡng; sau khi vượt ngưỡng, container bị restart |
| Liveness probe | Tiến trình còn có khả năng tiếp tục hoạt động không? | Kubelet restart container sau số lần thất bại liên tiếp theo cấu hình |
| Readiness probe | Ứng dụng có thể nhận traffic ngay lúc này không? | Container bị đánh dấu not ready và không được đưa vào endpoint phục vụ tương ứng |

Startup probe hữu ích cho ứng dụng khởi động lâu. Khi có startup probe, liveness và readiness probe chưa được thực hiện cho tới khi startup probe thành công. Điều này tránh liveness probe giết ứng dụng trong giai đoạn warm-up hợp lệ.

Readiness failure không tự restart container. Nó chỉ báo rằng container chưa sẵn sàng nhận traffic. Liveness failure có thể dẫn tới restart. Phân biệt hai hành vi này giúp tránh dùng liveness để xử lý mọi dependency tạm thời.

### Ví dụ cấu hình probe

```yaml
containers:
  - name: api
    image: registry.example.com/commerce/orders-api:1.4.0
    ports:
      - name: http
        containerPort: 8080
    startupProbe:
      httpGet:
        path: /health/startup
        port: http
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 30
    livenessProbe:
      httpGet:
        path: /health/live
        port: http
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /health/ready
        port: http
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 2
```

Đây là ví dụ minh họa; endpoint và ngưỡng phải phù hợp với thời gian startup, latency và đặc tính ứng dụng. `failureThreshold` cần đủ để chịu jitter ngắn nhưng vẫn phát hiện lỗi thật trong thời gian đáp ứng SLO.

Liveness endpoint nên kiểm tra trạng thái nội bộ có ý nghĩa, chẳng hạn event loop còn phản hồi. Không nên để liveness thất bại chỉ vì database hoặc API bên ngoài tạm thời mất kết nối; nếu tất cả replica cùng restart khi dependency lỗi, hệ thống có thể tạo restart storm và làm phục hồi chậm hơn. Readiness có thể phản ánh dependency bắt buộc nếu ứng dụng thực sự không thể phục vụ request khi dependency đó lỗi.

## 16. Graceful shutdown và termination grace period

Khi container bị dừng do rollout, scale-in hoặc xóa Pod, runtime thường gửi SIGTERM tới tiến trình chính rồi chờ trong khoảng grace period. Nếu tiến trình chưa kết thúc khi hết thời gian, runtime có thể gửi SIGKILL.

Ứng dụng nên:

1. Nhận SIGTERM hoặc tín hiệu shutdown tương ứng.
2. Ngừng nhận request/message mới.
3. Đánh dấu readiness false để ngừng nhận traffic mới.
4. Hoàn tất hoặc hủy có kiểm soát request đang chạy.
5. Commit/flush trạng thái bền vững và đóng connection pool.
6. Dừng worker và thoát trước deadline.

Trong Kubernetes, `terminationGracePeriodSeconds` xác định thời gian chờ kết thúc Pod theo cấu hình. Hook `preStop`, nếu có, chạy trong khoảng grace period đó và có thể tiêu thụ một phần thời gian dành cho shutdown. Đặt grace period quá ngắn có thể khiến ứng dụng bị SIGKILL; đặt quá dài có thể làm rollout và scale-in chậm.

Ứng dụng nên log rõ thời điểm nhận SIGTERM, bắt đầu drain và kết thúc shutdown. Nếu container thường kết thúc bằng exit code 137 trong rollout, kiểm tra grace period, thời gian xử lý request và signal handling trước khi kết luận OOM.

## 17. Điều tra OOM và memory limit

Container có thể bị OOM kill khi vượt memory limit của cgroup, dù node còn RAM. Cần xem cả mức dùng bộ nhớ của container, limit và trạng thái kernel/runtime.

Trong Kubernetes:

```bash
kubectl describe pod orders-api -n production
kubectl get pod orders-api -n production \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{" reason="}{.lastState.terminated.reason}{" exit="}{.lastState.terminated.exitCode}{"\n"}{end}'
kubectl top pod orders-api -n production --containers
```

`kubectl top` cần Metrics Server hoặc nguồn metrics tương thích; nó thường hiển thị mức dùng hiện tại, không phải lịch sử tại thời điểm OOM. Dùng Prometheus/managed monitoring hoặc metrics backend để xem xu hướng trước sự cố.

Kiểm tra:

- Memory working set và memory limit trước lúc restart.
- Heap, native memory, thread stack, cache và buffer của runtime.
- `requests.memory` và `limits.memory` trong Pod spec.
- Event `OOMKilled`, node memory pressure và eviction.
- Thay đổi tải, release, batch job hoặc cache warm-up gần thời điểm lỗi.

Đừng chỉ tăng limit nếu memory tăng liên tục do leak. Hãy xác định working set hợp lệ, sửa leak hoặc giới hạn cache/concurrency, sau đó sizing lại có headroom.

## 18. Phân biệt container restart với Pod eviction

Container restart xảy ra khi container trong Pod được chạy lại. Pod eviction là khi kubelet hoặc control plane loại Pod khỏi node, thường do node pressure hoặc chính sách disruption. Pod replacement có thể tạo Pod mới ở node khác.

Các tín hiệu khác nhau:

- `restartCount` tăng nhưng Pod UID giữ nguyên: có thể là container restart.
- Pod có reason `Evicted`: xem message và node condition để biết memory, disk hoặc PID pressure.
- Pod cũ ở trạng thái `Failed` và Pod mới được tạo: controller có thể đang thay Pod.
- Node `NotReady` hoặc `MemoryPressure`/`DiskPressure`: xem node-level event và workload khác cùng node.
- Deployment rollout tạo ReplicaSet/Pod mới: đối chiếu rollout history và image digest.

Nếu nhiều Pod trên cùng node đồng loạt lỗi, ưu tiên điều tra node, runtime, disk và network. Nếu chỉ một container có restart count tăng, tập trung vào ứng dụng, probe, limit và dependency của workload đó.

## 19. Giữ dữ liệu và bằng chứng qua lần restart

Container writable layer thường có vòng đời gắn với container instance. Khi container bị xóa hoặc Pod bị thay thế, dữ liệu trong layer đó có thể mất. Không lưu trạng thái nghiệp vụ, queue checkpoint hoặc log duy nhất trong writable layer.

Phân loại dữ liệu:

| Dữ liệu | Nơi lưu phù hợp |
|---|---|
| Log ứng dụng | stdout/stderr và hệ thống log tập trung; file log cần volume/agent rõ ràng |
| Cache có thể tạo lại | Memory hoặc ephemeral storage với chính sách warm-up |
| Dữ liệu nghiệp vụ | Database, object storage hoặc persistent volume theo semantics ứng dụng |
| Checkpoint batch | Kho bền vững hoặc volume có vòng đời phù hợp |
| File tạm | Writable layer, `emptyDir` hoặc tmpfs nếu có thể mất khi restart |
| Crash dump/core dump | Volume riêng có giới hạn, quyền truy cập và retention |
| Cấu hình/secret | ConfigMap/Secret hoặc secret manager; không ghi ngược vào image |

Trong Kubernetes, `emptyDir` tồn tại trong vòng đời Pod và có thể sống qua container restart trong cùng Pod, nhưng bị xóa khi Pod bị loại khỏi node. PersistentVolume có vòng đời độc lập hơn tùy reclaim policy và storage provider; vẫn cần backup và kiểm tra attach/failover semantics.

Khi điều tra crash, lưu log trước, termination state, Pod YAML, event, image digest và metric timeline. Nếu cần core dump, cấu hình trước dung lượng, quyền và nơi lưu; không đợi đến lúc container restart mới hy vọng dữ liệu dump tồn tại.

## 20. Xử lý CrashLoopBackOff theo trình tự

Khi Pod ở `CrashLoopBackOff`, nên điều tra theo thứ tự:

1. Xác định đúng Pod, namespace, container và node.
2. Lấy `kubectl logs --previous` cho container đã kết thúc.
3. Dùng `kubectl describe pod` để đọc termination reason và event.
4. Xem `lastState.terminated`, exit code, started/finished time và restart count.
5. Kiểm tra command/args, environment, ConfigMap, Secret, volume mount và permission.
6. Đối chiếu memory/CPU limit, OOM event, probe failure và node pressure.
7. Kiểm tra dependency, DNS, certificate, network policy và service endpoint.
8. So sánh image digest/config với phiên bản trước và rollout gần nhất.
9. Sửa nguyên nhân trong manifest hoặc ứng dụng; deploy có kiểm soát.
10. Theo dõi restart count, readiness, error rate và log sau khi sửa.

Không xóa Pod ngay khi thấy CrashLoopBackOff nếu chưa lấy bằng chứng. Nếu cần dừng restart storm để bảo vệ dependency, dùng biện pháp điều phối phù hợp với controller và runbook; thay đổi replica hoặc rollout có thể làm mất Pod cũ và log local.

## 21. Ví dụ: container restart do cấu hình sai

Một API được triển khai trên Kubernetes. Sau rollout, Pod mới liên tục restart. `kubectl get pods` hiển thị `CrashLoopBackOff` và restart count tăng.

Quy trình:

```bash
kubectl logs pod/orders-api-xxxxx -n production -c api --previous
kubectl describe pod orders-api-xxxxx -n production
kubectl get pod orders-api-xxxxx -n production -o yaml
```

Log trước cho thấy ứng dụng không tìm thấy biến `DB_HOST`. `describe` cho biết container kết thúc với exit code khác 0, không có `OOMKilled`, và event không ghi nhận liveness probe failure. Kiểm tra Pod spec cho thấy ConfigMap mới được đổi key nhưng Deployment vẫn tham chiếu key cũ.

Khắc phục:

1. Xác nhận tên key đúng trong ConfigMap và Deployment.
2. Cập nhật manifest qua pipeline đã phê duyệt.
3. Kiểm tra diff và rollout status.
4. Xác nhận Pod mới nhận biến môi trường cần thiết mà không in secret ra log.
5. Kiểm tra readiness, request thành công và restart count không tăng tiếp.

Trong trường hợp này, tăng memory limit hoặc đổi restart policy không giải quyết được lỗi. Bằng chứng từ previous log và Pod event giúp khoanh vùng nhanh vào cấu hình.

## 22. Ví dụ: OOM restart sau khi tăng tải

Một worker xử lý message tăng số consumer từ 4 lên 20. Sau khi triển khai, container bị `OOMKilled` trong giờ cao điểm. Metric cho thấy memory working set tăng dần tới sát limit, trong khi queue lag giảm lúc đầu rồi tăng trở lại khi worker restart.

Điều tra:

- Đối chiếu restart timestamp với memory working set và limit.
- Kiểm tra heap/native memory, số message đang xử lý và kích thước batch.
- Xem log trước restart để biết worker đang xử lý loại message nào.
- Kiểm tra consumer concurrency và prefetch/buffer.
- Xác định có message lớn hoặc cache không giới hạn hay không.

Biện pháp có thể là giảm concurrency, giới hạn batch/prefetch, stream payload thay vì nạp toàn bộ vào RAM, đặt giới hạn cache hoặc tăng memory limit nếu node có đủ capacity. Sau thay đổi, chạy soak test ở tải peak và theo dõi memory, queue lag, processing rate, error và restart count.

## 23. Alerting và dashboard cho restart

Dashboard nên hiển thị theo service, namespace, workload, Pod, container và node:

- Restart count và restart rate theo khoảng thời gian.
- Termination reason và exit code gần nhất.
- Pod readiness, desired/available replicas và rollout status.
- OOMKilled, memory working set/limit và node memory pressure.
- Liveness/readiness/startup probe failures.
- CPU usage/throttling, disk pressure và PID pressure.
- Request rate, 5xx, latency p95/p99 và queue lag.
- Image version/digest và thời điểm rollout.
- Log startup, shutdown, exception và previous container logs.

Alert nên dựa trên mức độ ảnh hưởng:

- Một container restart đơn lẻ nhưng replica khác healthy có thể chỉ cần ghi nhận.
- Restart lặp lại trong một cửa sổ thời gian cần cảnh báo theo workload.
- Tất cả replica restart hoặc readiness giảm cần cảnh báo mức nghiêm trọng.
- OOMKilled lặp lại, CrashLoopBackOff kéo dài hoặc desired replicas không đạt cần điều tra ngay.
- Restart đồng loạt trên một node cần cảnh báo node/runtime.

Không dùng restart count tích lũy từ lúc Pod tạo làm cảnh báo duy nhất; một Pod sống lâu có thể có một lần restart lịch sử nhưng hiện tại khỏe. Dùng rate/increase trong cửa sổ thời gian và kết hợp readiness/error rate.

## 24. Runbook khi container restart bất thường

Runbook nên chuẩn hóa thông tin cần thu thập và hành động theo mức độ:

**Bước 1 — Bảo toàn bằng chứng**

- Ghi namespace, Pod UID, container ID, node, image digest và thời điểm.
- Thu previous logs, current logs, `describe`, Pod YAML và events.
- Lưu metric timeline cho memory, CPU, probe, request và queue.
- Không xóa Pod hoặc restart thủ công trước khi thu thập bằng chứng, trừ khi cần giảm tác động khẩn cấp.

**Bước 2 — Phân loại**

- Application exit/exception.
- OOM hoặc resource limit.
- Probe failure.
- Node/runtime/eviction.
- Config/image/secret/volume/network.
- Restart có chủ đích do rollout hoặc scale.

**Bước 3 — Khôi phục an toàn**

- Rollback image/config nếu release mới gây lỗi và rollback dữ liệu an toàn.
- Điều chỉnh probe nếu cấu hình không phù hợp với startup/health semantics.
- Sửa memory/CPU limit, concurrency hoặc leak theo số liệu.
- Cách ly node nếu có bằng chứng node/runtime lỗi.
- Bảo vệ database/queue khỏi retry storm và duplicate processing.

**Bước 4 — Xác minh**

- Container không còn restart ngoài dự kiến.
- Pod đạt Ready và số replica khả dụng đạt mục tiêu.
- Request/error/latency và queue lag trở về baseline.
- Dữ liệu/checkpoint không bị mất hoặc xử lý trùng.
- Log, metric và alert đã ghi nhận nguyên nhân và kết quả.

## 25. Những sai lầm thường gặp

- **Chỉ đọc log hiện tại:** bỏ lỡ lỗi của container instance trước. Dùng `kubectl logs --previous` hoặc log backend tập trung.
- **Coi CrashLoopBackOff là nguyên nhân:** đây là trạng thái backoff. Đọc termination reason, exit code và previous log.
- **Kết luận OOM từ exit code 137:** SIGKILL có thể đến từ nguyên nhân khác. Đối chiếu OOM event và memory metrics.
- **Dùng liveness để kiểm tra mọi dependency:** dependency tạm lỗi khiến tất cả container restart. Tách liveness khỏi readiness.
- **Probe quá gắt:** ứng dụng bị restart trong warm-up hoặc lúc CPU bị throttling. Dùng startup probe và timeout phù hợp.
- **Restart policy `Always` cho mọi loại Job:** công việc hoàn tất với exit code 0 vẫn có thể chạy lại ngoài ý muốn. Chọn policy và controller đúng.
- **Lưu log duy nhất trong container filesystem:** log mất khi container/Pod bị thay thế. Ship stdout/stderr tới hệ thống tập trung.
- **Không cấu hình log rotation:** log lấp đầy disk node và gây lỗi cho workload khác. Đặt retention/rotation theo tốc độ ingest.
- **Tăng memory limit mà không kiểm tra leak:** chỉ trì hoãn lần OOM tiếp theo. Profile và giới hạn cache/concurrency.
- **Restart thủ công trước khi thu bằng chứng:** làm mất trạng thái và log cần điều tra. Thu thập trước khi can thiệp khi điều kiện cho phép.
- **Không xử lý graceful shutdown:** request đang chạy bị cắt khi rollout. Nhận SIGTERM, drain và đặt grace period phù hợp.

## 26. Checklist vận hành

- [ ] Log ứng dụng được ghi ra stdout/stderr hoặc pipeline file có persistence rõ ràng.
- [ ] Log có timestamp, service, namespace, Pod UID, container ID và severity.
- [ ] Có log startup, shutdown, exception và lý do ứng dụng chủ động thoát.
- [ ] Có log tập trung và retention đủ để điều tra sau khi Pod/node bị thay thế.
- [ ] Log rotation giới hạn dung lượng node nhưng không làm mất dữ liệu cần giữ.
- [ ] Theo dõi restart count/rate, termination reason, exit code và image digest.
- [ ] Theo dõi memory/CPU, limit, OOM event, probe failure và node pressure.
- [ ] Có startup, liveness và readiness probe với semantics tách biệt.
- [ ] Ứng dụng xử lý SIGTERM, drain request và shutdown trong grace period.
- [ ] Dữ liệu nghiệp vụ/checkpoint nằm trên storage có vòng đời phù hợp.
- [ ] Runbook lưu previous logs, Pod events, YAML và metric timeline trước khi xóa/recreate.
- [ ] Alert phân biệt restart đơn lẻ, CrashLoopBackOff, OOM lặp lại và node-wide failure.
- [ ] Sau khắc phục đã xác minh readiness, SLI, queue và restart rate trở lại bình thường.

Khi container restart, log của lần chạy trước, termination state, metric và event cần được xem như một bộ bằng chứng thống nhất. Restart policy và probe chỉ điều khiển cách nền tảng phản ứng; việc phục hồi bền vững đòi hỏi xác định đúng nguyên nhân, bảo toàn dữ liệu, kiểm soát shutdown và xác minh workload đã trở lại trạng thái phục vụ ổn định.
