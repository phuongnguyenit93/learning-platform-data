# Chẩn đoán lỗi pod, node, DNS và kết nối trong AKS

Một API chạy trên **Azure Kubernetes Service (AKS)** trả HTTP 503 sau khi triển khai phiên bản mới. Nhóm phát triển nói image đã build thành công; nhóm mạng nói VNet vẫn hoạt động; còn bảng điều khiển Kubernetes hiển thị một số Pod ở trạng thái `Running`. Lỗi thực tế có thể nằm ở **readiness probe**, **Service không có endpoint sẵn sàng**, **CoreDNS**, **NetworkPolicy**, **node thiếu tài nguyên**, **Azure Load Balancer** hoặc một dependency ở ngoài cluster. Nếu chỉ khởi động lại toàn bộ Pod mà không xác định lớp lỗi, hệ thống có thể phục hồi tạm thời nhưng nguyên nhân vẫn tồn tại.

Bài học này cung cấp **quy trình chẩn đoán theo từng lớp, dựa trên bằng chứng**: từ Pod và container, node/node pool, dịch vụ phân giải DNS, mạng nội bộ Kubernetes đến mạng Azure và đường truy cập của client. Mỗi bước giải thích lệnh cần dùng, tín hiệu mong đợi, cách phân loại sự cố và những thay đổi cần tránh trong Production.

Bài thuộc chương **Vận hành AKS** của module `CLOUD_PROVIDERS_AZURE`. Module giới thiệu hệ sinh thái Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, tính toán, lưu trữ và dữ liệu; đồng thời hướng dẫn triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng. Việc điều tra sự cố AKS vì vậy không dừng ở lệnh `kubectl` mà còn liên quan tới **Azure RBAC, node pools, VNet, Azure CNI, NSG, routing, Storage, registry và giám sát**.

> Ví dụ trong bài dùng giá trị minh họa như namespace `shop`, Service `catalog-api`, AKS cluster `aks-prod-example` và VNet private. Các lệnh quan sát chủ yếu ở chế độ chỉ đọc. Lệnh tạo Pod debug, thay cấu hình, restart hoặc drain node được **đánh dấu riêng** vì có thể thay đổi cluster và phát sinh tác động. Những tính năng/đầu ra cụ thể phụ thuộc phiên bản AKS, Kubernetes, networking dataplane và add-ons đang triển khai.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt lỗi ở lớp **container, Pod, scheduler, node, DNS, Service, networking, ingress và dependency**.
2. Đọc `Pod phase`, `container state`, `Conditions`, Kubernetes Events và exit code mà không suy luận sai từ một trạng thái `Running`.
3. Chẩn đoán `Pending`, `ImagePullBackOff`, `CrashLoopBackOff`, `OOMKilled`, `Evicted` và `FailedMount`.
4. Phân tích node `NotReady`, `MemoryPressure`, `DiskPressure`, node taints, kubelet và cấu hình AKS node pool.
5. Kiểm tra **CoreDNS, kube-dns Service, search domains** và DNS ngoài cluster, bao gồm Azure Private DNS.
6. Lần theo đường truyền từ client đến **Ingress/LoadBalancer → Service → EndpointSlice → Pod**.
7. Phân biệt lỗi do **Kubernetes NetworkPolicy** và do **Azure NSG, UDR, firewall, private endpoint, outbound/SNAT**.
8. Sử dụng Azure CLI, `kubectl`, công cụ đo kết nối và Azure Monitor/Log Analytics một cách có kiểm soát.
9. Viết incident runbook có bước thu thập chứng cứ, xử lý, kiểm chứng và rollback.
10. Xác định những trường hợp cần escalations tới nhóm Platform, Networking, Identity hoặc ứng dụng.

## 2. Mô hình tư duy: chẩn đoán từ triệu chứng đến lớp nguyên nhân

Một request đi qua nhiều thành phần:

```text
Client / người dùng
        |
        v
DNS công khai / private DNS
        |
        v
Public hoặc internal Load Balancer / Ingress / Gateway
        |
        v
Kubernetes Service (ClusterIP / NodePort / LB)
        |
        v
EndpointSlice: các Pod IP sẵn sàng
        |
        v
Pod IP + container port
        |
        v
Application process
        |
        +--> CoreDNS --> Service nội bộ khác
        |
        +--> VNet / firewall / DNS --> DB, Storage, Key Vault
        |
       Node / kubelet / container runtime / CNI
```

Một lỗi “không truy cập được ứng dụng” có thể nằm ở bất kỳ mắt xích nào. Hãy đặt những câu hỏi theo thứ tự:

- **Ứng dụng có chạy?** Pod/container có khởi động, không bị crash và có readiness không?
- **Service có trỏ đúng Pod?** Selector, targetPort, EndpointSlices và trạng thái Ready có phù hợp không?
- **DNS phân giải đúng địa chỉ?** Tên nội bộ hay tên bên ngoài đang được hỏi từ đâu?
- **Mạng có cho phép packet đi qua?** Policy Kubernetes, route Azure, NSG/firewall, private endpoint?
- **Lớp công khai có đúng?** Ingress, TLS, load balancer health probe, hostname và backend routing?
- **Dependency có khỏe?** DB, registry, Key Vault, Storage, external API?
- **Sự cố xuất hiện sau thay đổi nào?** Deployment, image, node pool upgrade, DNS, route, policy hay secret rotation?

**Nguyên tắc:** cô lập lỗi bằng **kết quả quan sát được**, không gán nhãn “lỗi DNS” chỉ vì có dòng log chứa chữ `lookup`, cũng không kết luận “node khỏe” vì VM vẫn hiện trạng thái `Running` trong Azure.

## 3. Chuẩn bị điều tra: phạm vi, thời điểm và quyền

Trước khi chạy lệnh, ghi lại các thông tin:

| Trường | Ví dụ |
|---|---|
| Subscription / tenant | Subscription Production, tenant công ty |
| AKS cluster / resource group | `aks-prod-example` / `rg-platform-prod` |
| Namespace / workload | `shop` / Deployment `catalog-api` |
| Service / ingress | `catalog-api` / `shop.example.com` |
| Thời gian bắt đầu lỗi | 2026-11-20 08:10 UTC |
| Mức độ ảnh hưởng | Tất cả người dùng hay chỉ một zone/replica? |
| Hành vi kỳ vọng | HTTP 200 trong thời gian đáp ứng mục tiêu |
| Kết quả quan sát | HTTP 503, timeout, NXDOMAIN, `Pending`... |
| Thay đổi gần nhất | Rollout image, đổi DNS, upgrade node pool |
| Người phụ trách / incident ID | Đội ứng dụng, Platform, Networking |

### Bảo đảm dùng đúng cluster

```bash
az account show \
  --query "{Subscription:id,Tenant:tenantId,Name:name}" \
  --output table

kubectl config current-context
kubectl cluster-info
kubectl get namespaces
```

**Rủi ro phổ biến:** `kubectl` đang trỏ vào cluster khác với tài nguyên bạn xem trong Azure Portal. Đọc context trước khi chạy bất kỳ lệnh thay đổi tài nguyên.

Trong cluster đã được phê duyệt, nếu cần lấy credentials cho AKS, một quản trị viên có thể dùng quy trình `az aks get-credentials` phù hợp, nhưng lệnh đó **ghi vào kubeconfig cục bộ**. Không tự thay context của phiên vận hành Production khi chưa xác minh cluster đích, quyền và cơ chế đăng nhập được tổ chức chấp thuận.

### Chỉ dùng quyền cần thiết

Những lệnh `get`, `describe`, `logs` có thể yêu cầu các quyền RBAC khác nhau. Kiểm tra trước:

```bash
kubectl auth can-i get pods -n shop
kubectl auth can-i get pods/log -n shop
kubectl auth can-i get events -n shop
kubectl auth can-i create pods -n shop
```

Đừng xin `cluster-admin` chỉ vì thiếu quyền xem log. Một số lệnh `describe` có thể hiển thị environment variables hoặc cấu hình nhạy cảm nếu ứng dụng hard-code; hãy **ẩn thông tin bí mật** trước khi chia sẻ output.

## 4. Bộ lệnh chẩn đoán nhanh: mười phút đầu

Bắt đầu bằng dữ liệu chỉ đọc:

```bash
kubectl get nodes -o wide

kubectl get pods -A -o wide

kubectl -n shop get deploy,replicaset,pod,svc,ingress

kubectl -n shop get events \
  --sort-by=.metadata.creationTimestamp
```

Tiếp theo xác định Pod cụ thể:

```bash
kubectl -n shop describe pod <POD_NAME>

kubectl -n shop logs <POD_NAME> \
  --all-containers=true --since=30m --timestamps=true

kubectl -n shop logs <POD_NAME> \
  -c <CONTAINER_NAME> --previous --timestamps=true
```

Lệnh `--previous` chỉ có ý nghĩa khi tồn tại log của **instance container trước đó** và log chưa bị xoay vòng/mất. Nếu nó báo không có log trước, không có nghĩa Pod chưa từng restart trong toàn bộ vòng đời cluster.

Cuối cùng, kiểm tra Service và endpoints:

```bash
kubectl -n shop get svc catalog-api -o wide

kubectl -n shop describe svc catalog-api

kubectl -n shop get endpointslice \
  -l kubernetes.io/service-name=catalog-api \
  -o wide
```

Nếu Service có ClusterIP nhưng **không có EndpointSlice chứa endpoint sẵn sàng**, lỗi thường ở selector/Pod readiness hoặc cách backend được khai báo, **chưa phải bằng chứng DNS hỏng**.

### Cây quyết định sơ bộ

```text
Ứng dụng trả lỗi / timeout?
       |
       +-- Không có Pod Ready
       |      |
       |      +-- Pending → scheduler / requests / taint / PVC / quota
       |      +-- ImagePull... → registry / auth / DNS / network
       |      +-- CrashLoop... → process / config / secret / probes
       |      +-- Node NotReady → kubelet / CNI / pressure / hạ tầng
       |
       +-- Có Pod Ready
              |
              +-- Pod IP không kết nối được → app port / policy / CNI
              |
              +-- Pod IP được, Service không được
              |      → selector / EndpointSlice / port / dataplane
              |
              +-- Service được, tên DNS không được
              |      → DNS client / CoreDNS / search domain
              |
              +-- Nội bộ được, bên ngoài không được
                     → ingress / LB / DNS ngoài / NSG / TLS / route
```

Cây trên là điểm bắt đầu; ví dụ Pod Ready cũng có thể trả lỗi 500 do lỗi nghiệp vụ, và nhiều loại lỗi có thể xảy ra cùng lúc.

## 5. Đọc Pod phase, container state và Pod Conditions

Không đồng nhất mọi trạng thái hiển thị trong `kubectl get pods` với `Pod phase`.

| Tín hiệu | Ý nghĩa thực tế |
|---|---|
| **Pending** | Kubernetes đã chấp nhận Pod nhưng chưa thể sắp xếp hoặc chưa hoàn tất chuẩn bị container. |
| **Running** | Pod đã được gán node và có ít nhất một container đã tạo/đang khởi động/chạy theo ngữ nghĩa của Pod phase; **không đồng nghĩa ứng dụng Ready**. |
| **Succeeded** | Các container chính kết thúc thành công, thường gặp ở Job. |
| **Failed** | Pod đã kết thúc với lỗi theo ngữ nghĩa Kubernetes. |
| **Unknown** | Control plane không biết trạng thái Pod do vấn đề liên lạc hoặc tương tự. |
| **CrashLoopBackOff** | Container đang ở trạng thái chờ khởi động lại với backoff sau nhiều lần thất bại; là **waiting reason**, không phải Pod phase độc lập. |
| **ImagePullBackOff** | Container chờ thử lại việc kéo image sau các lỗi; không phải Pod phase. |

Các **Pod Conditions** như `PodScheduled`, `Initialized`, `ContainersReady` và `Ready` cung cấp thông tin cụ thể hơn.

Ví dụ:

```bash
kubectl -n shop get pod <POD_NAME> \
  -o jsonpath='{.status.phase}{"\n"}'

kubectl -n shop get pod <POD_NAME> \
  -o jsonpath='{range .status.conditions[*]}{.type}={.status}{" "}{.reason}{"\n"}{end}'
```

Nếu `phase=Running` nhưng `Ready=False`, Service thông thường **không đưa Pod đó vào tập endpoint phục vụ traffic hợp lệ**. Hãy kiểm tra readiness probe, startup, dependency và Pod Conditions trước khi đụng tới Azure Load Balancer.

## 6. Pod Pending: scheduler không tìm được nơi chạy

Các nguyên nhân thường gặp:

| Dấu hiệu trong Events | Lớp lỗi | Kiểm tra |
|---|---|---|
| `Insufficient cpu` / `Insufficient memory` | Requests vượt tài nguyên khả dụng của nodes. | Resource requests, node allocatable, autoscaler. |
| `untolerated taint` | Pod không có toleration phù hợp. | Node taints, Pod tolerations. |
| `node affinity/selector mismatch` | Không node nào thỏa yêu cầu. | `nodeSelector`, affinity, labels của node. |
| `Too many pods` | Đạt giới hạn số Pod trên node hoặc phân bổ IP liên quan. | Node maxPods, CNI/IP capacity. |
| `unbound immediate PersistentVolumeClaims` | PVC/PV hoặc storage class chưa sẵn sàng. | `kubectl get pvc,pv,storageclass`. |
| `TopologySpreadConstraints` hoặc vùng khả dụng | Ràng buộc trải Pod không khả thi. | Labels, topology, capacity từng zone. |
| Không cấp thêm node được | Cluster Autoscaler, quota, capacity hoặc giới hạn node pool. | AKS node pools, Azure quota, autoscaler events. |

Lệnh:

```bash
kubectl -n shop describe pod <PENDING_POD>

kubectl -n shop get pvc

kubectl get nodes \
  -o custom-columns=NAME:.metadata.name,TAINTS:.spec.taints,UNSCHEDULABLE:.spec.unschedulable

kubectl describe node <NODE_NAME>
```

### Requests khác limits

- **Requests** được scheduler dùng để quyết định Pod có thể được bố trí trên node theo tài nguyên khai báo.
- **Limits** giới hạn sử dụng tài nguyên của container theo cơ chế Kubernetes/runtime hỗ trợ.
- Pod với request quá cao có thể `Pending` dù CPU sử dụng thực tế trên node đang thấp.
- Pod với memory limit quá thấp có thể bị OOMKilled dù node còn nhiều RAM.

**Không hạ requests hoặc tăng limits mù quáng** để ép Pod chạy; cần kiểm tra workload thực tế và nguy cơ tranh chấp bộ nhớ khi scale.

## 7. ImagePullBackOff, ErrImagePull và lỗi tạo container

Lỗi kéo image thường có những nhóm nguyên nhân:

1. Sai tên registry, repository, tag hoặc image digest.
2. Registry không có image hoặc tag đã bị xóa.
3. Node thiếu quyền kéo image từ **Azure Container Registry (ACR)** hoặc registry khác.
4. Secret `imagePullSecrets` không tồn tại/sai/expired khi dùng credential-based pull.
5. DNS tới registry hoặc outbound network bị chặn.
6. Giới hạn network, rate limit hoặc lỗi tạm thời từ registry.
7. Image không tương thích kiến trúc CPU/OS khi container thực thi.

Lệnh quan sát:

```bash
kubectl -n shop describe pod <POD_NAME>

kubectl -n shop get deploy catalog-api \
  -o jsonpath='{.spec.template.spec.containers[*].image}{"\n"}'

az aks show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<AKS_CLUSTER>" \
  --query "{Name:name,Identity:identity,Network:networkProfile}" \
  --output json
```

Với AKS kết nối ACR, cần kiểm tra **danh tính thực hiện image pull của kubelet/node** và quyền registry thích hợp. Không đánh đồng identity của ứng dụng bên trong Pod với identity kéo image của kubelet. Tùy mô hình quyền ACR (RBAC truyền thống hay chế độ repository permission/ABAC được hỗ trợ), role/policy cần thiết khác nhau.

**Ví dụ phân loại log Event:**

- `manifest unknown`: có thể tag/digest không tồn tại.
- `unauthorized` / `denied`: kiểm tra identity, credential và registry permission.
- `no such host` / timeout: kiểm tra DNS/egress/registry endpoint.
- `exec format error` sau khi pull thành công: xem image platform/architecture và binary.

Không sửa lỗi pull bằng cách bật public access cho registry hoặc cấp quyền Owner rộng nếu vấn đề chỉ là repository tag sai.

## 8. CrashLoopBackOff: tiến trình liên tục thất bại

**CrashLoopBackOff** cho biết Kubernetes đang trì hoãn lần restart tiếp theo của container đã nhiều lần kết thúc. Nguyên nhân phải được tìm trong **exit reason, exit code, logs và Events**.

```bash
kubectl -n shop describe pod <POD_NAME>

kubectl -n shop logs <POD_NAME> \
  -c <CONTAINER_NAME> --previous --tail=200 --timestamps

kubectl -n shop get pod <POD_NAME> \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{" restarts="}{.restartCount}{" lastReason="}{.lastState.terminated.reason}{" lastExit="}{.lastState.terminated.exitCode}{"\n"}{end}'
```

| Hiện tượng | Nguyên nhân khả dĩ |
|---|---|
| Exit code khác 0 | App exception, cấu hình sai, dependency unavailable, lỗi startup. |
| `OOMKilled` / exit code thường 137 | Vượt memory limit hoặc bị kill theo bối cảnh runtime; cần kiểm tra reason thực tế. |
| `Error: missing environment variable` | ConfigMap/Secret không có hoặc env name sai. |
| `connection refused` tới DB | DB/Service chưa hoạt động, sai host/port, readiness dependency. |
| TLS handshake/permission error | Certificate/CA, identity, RBAC hoặc secret rotation. |
| Probe failures rồi restart | Liveness/startup probe quá chặt hoặc endpoint không đáp ứng. |

**Không kết luận exit code 137 luôn là Kubernetes memory-limit OOM.** Tín hiệu OOMKilled trong container status, node pressure và runtime logs mới giúp xác nhận nguyên nhân.

### Quy trình khắc phục

1. Xác nhận image và command/args hiện hành.
2. Đọc logs **của lần chạy trước**.
3. Xem container last termination reason và Pod Events.
4. Đối chiếu thời điểm rollout/đổi ConfigMap/Secret.
5. Xác minh dependency sẵn sàng và đường DNS/network.
6. Sửa root cause rồi rollout có kiểm soát; theo dõi restarts và readiness.
7. Có phương án rollback nếu version mới gây sự cố.

Khởi động lại Pod khi lỗi nằm trong biến cấu hình hoặc secret sai chỉ tạo **vòng lặp crash mới**.

## 9. Probes: readiness, liveness và startup

Kubernetes có ba loại probe phục vụ các mục tiêu khác nhau:

| Probe | Trả lời câu hỏi | Khi thất bại |
|---|---|---|
| **Readiness** | Container đã sẵn sàng nhận traffic? | Pod bị đánh dấu NotReady; thường bị loại khỏi tập Service endpoints hợp lệ. |
| **Liveness** | Container có đang kẹt/hỏng cần restart? | Kubelet có thể restart container sau khi vượt ngưỡng failure. |
| **Startup** | Ứng dụng đã khởi động xong chưa? | Trong giai đoạn startup, có thể trì hoãn liveness/readiness; khi vượt failure threshold, container có thể bị restart. |

Ví dụ manifest trích đoạn:

```yaml
containers:
  - name: catalog-api
    image: example.azurecr.io/catalog-api:1.2.0
    ports:
      - containerPort: 8080
    startupProbe:
      httpGet:
        path: /startup
        port: 8080
      periodSeconds: 5
      failureThreshold: 24
    readinessProbe:
      httpGet:
        path: /ready
        port: 8080
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
    livenessProbe:
      httpGet:
        path: /health/live
        port: 8080
      periodSeconds: 20
      timeoutSeconds: 2
      failureThreshold: 3
```

Đây chỉ là ví dụ minh họa. Đường dẫn phải thực sự được ứng dụng cung cấp, và các ngưỡng phải đo theo startup time, tải và yêu cầu service thực tế.

**Sai lầm phổ biến:** liveness phụ thuộc vào cơ sở dữ liệu bên ngoài. Khi DB tạm lỗi, kubelet restart liên tục hàng loạt Pod dù process vẫn khỏe, làm sự cố nặng hơn. Tách ý nghĩa **process sống** và **workload sẵn sàng nhận traffic**.

Nếu readiness thất bại nhưng liveness thành công, ứng dụng có thể chạy mà không nhận traffic qua Service. Điều đó giải thích vì sao thấy `Running` nhưng Ingress trả lỗi.

## 10. OOMKilled, CPU throttling và eviction

### Memory OOM

Khi container vượt giới hạn bộ nhớ, runtime có thể dừng container và ghi `OOMKilled`. Kiểm tra:

```bash
kubectl -n shop describe pod <POD_NAME>

kubectl -n shop get pod <POD_NAME> \
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{" "}{.lastState.terminated.reason}{"\n"}{end}'

kubectl -n shop top pod <POD_NAME> --containers
```

Lệnh `kubectl top` chỉ hoạt động nếu metrics API/metrics-server hoặc thành phần tương ứng đã sẵn sàng; thiếu metrics không chứng minh Pod không tiêu thụ memory.

Các bước tiếp theo:

- So sánh limit/request với bộ nhớ thực tế tại đỉnh tải.
- Kiểm tra memory leak, cache, buffer, batch size.
- Kiểm tra node `MemoryPressure` và lịch eviction.
- Điều chỉnh workload hoặc resources theo dữ liệu đo, sau đó benchmark.
- Với hệ thống có HPA, kiểm tra việc tăng replica có thực sự giảm tải mỗi instance hay không.

### Disk/ephemeral storage pressure

Một Pod có thể bị `Evicted` khi node thiếu tài nguyên, đặc biệt **ephemeral storage**, memory hoặc số điều kiện pressure khác. Log lớn, image layers, cache và ghi vào writable layer có thể làm đầy đĩa node.

```bash
kubectl describe node <NODE_NAME>

kubectl -n shop describe pod <POD_NAME>
```

Kiểm tra các conditions như `DiskPressure`, `MemoryPressure` và `PIDPressure`, cùng phần Events. Không xóa log hay dữ liệu hệ thống trên node thủ công khi chưa có runbook: làm như vậy có thể mất bằng chứng hoặc gây hỏng kubelet/runtime.

### CPU throttling

CPU limit thấp có thể làm ứng dụng bị throttling, tăng p95 latency hoặc khiến probe timeout, dù Pod vẫn Running. Để xác nhận, dùng **container CPU throttling metrics** từ hệ thống quan sát có hỗ trợ, không chỉ số CPU tổng trên VM.

## 11. Node NotReady: xác định lỗi ở kubelet hay hạ tầng

Khi một node chuyển sang `NotReady` hoặc `Unknown`, Pod trên node đó có thể mất khả năng phục vụ; scheduler/cluster controller sẽ phản ứng theo điều kiện và chính sách Kubernetes.

Bắt đầu:

```bash
kubectl get nodes -o wide

kubectl describe node <NODE_NAME>

kubectl get pods -A \
  --field-selector spec.nodeName=<NODE_NAME> -o wide
```

Trong `describe node`, chú ý:

- **Conditions:** Ready, MemoryPressure, DiskPressure, PIDPressure, NetworkUnavailable nếu có.
- **Capacity/Allocatable:** tài nguyên có thể cấp phát cho Pods.
- **Taints:** `node.kubernetes.io/not-ready`, `unreachable` hoặc taints do operator.
- **Events:** kubelet không đăng ký, network unavailable, container runtime/eviction.
- **Allocated resources:** requests/limits được khai báo trên node.

### Nguyên nhân thường gặp

| Hiện tượng | Khả năng nguyên nhân |
|---|---|
| Node heartbeat mất | Kubelet, VM/hạ tầng, networking đến control plane. |
| `NetworkUnavailable` hoặc CNI không sẵn sàng | Network plugin/dataplane, pod IP allocation, route. |
| `DiskPressure` | Ổ đĩa hệ thống/ephemeral thiếu dung lượng. |
| `MemoryPressure` | Memory contention, eviction, lỗi ứng dụng. |
| `PIDPressure` | Thiếu khả năng tạo tiến trình. |
| Node tạm unavailable khi upgrade | Node image upgrade, cordon/drain hoặc rolling change hợp lệ. |
| Node mới không join | Network/provisioning/bootstrap/identity/quota/capacity. |

**NotReady không đồng nghĩa VM đã bị tắt.** Một VM có thể vẫn tồn tại và hoạt động trong Azure nhưng kubelet hoặc đường tới API Server không khỏe.

## 12. AKS node pool: autoscaler, quota, image và availability

AKS quản lý các node pool dựa trên hạ tầng compute Azure. Một Pod `Pending` hoặc node `NotReady` có thể liên quan tới **VM family, quota, capacity, autoscaler và node upgrade**.

Các lệnh Azure CLI chỉ đọc:

```bash
az aks show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<AKS_CLUSTER>" \
  --query "{Name:name,Provisioning:provisioningState,Network:networkProfile}" \
  --output json

az aks nodepool list \
  --resource-group "<RESOURCE_GROUP>" \
  --cluster-name "<AKS_CLUSTER>" \
  --output table

az aks nodepool show \
  --resource-group "<RESOURCE_GROUP>" \
  --cluster-name "<AKS_CLUSTER>" \
  --name "<POOL_NAME>" \
  --output json
```

### Khi autoscaler không cấp được node

Kiểm tra:

1. Node pool có bật autoscaling và còn dưới `maxCount` không?
2. Subscription có đủ quota **regional vCPU** và **VM family** không?
3. Region/zone có đủ capacity cho kích thước VM không?
4. Có ràng buộc node labels, taints, affinity, topology spread quá chặt không?
5. VNet/subnet và mô hình CNI còn đủ địa chỉ IP/quota network không?
6. Có chính sách Azure hoặc quyền identity chặn tạo hạ tầng không?
7. Node pool upgrade/maintenance có đang làm giảm số node khả dụng không?

**Quota đủ không bảo đảm capacity Azure còn sẵn tại thời điểm tạo VM.** Nếu pool đã ở maxCount, autoscaler không thể giải quyết mọi Pod Pending; cần đánh giá chính sách scale và nguồn lực của workload.

### Cordon, drain, upgrade là thao tác thay đổi

Lệnh như `kubectl cordon`, `kubectl drain`, `az aks nodepool upgrade` hoặc thay node image **không phải lệnh điều tra read-only**. Chúng có thể gây dịch chuyển/gián đoạn Pod. Trong AKS Production, ưu tiên runbook upgrade/repair của AKS và kiểm tra PodDisruptionBudget, replica distribution, topology/zone trước khi làm.

## 13. PodDisruptionBudget, DaemonSet và sự cố node

Nếu muốn bảo trì node hoặc sửa một node xấu, cần phân biệt:

- **Deployment/ReplicaSet:** thường có thể tạo Pod thay thế nếu còn capacity và cấu hình cho phép.
- **StatefulSet:** có dữ liệu, ordinal và yêu cầu thứ tự/volume riêng.
- **DaemonSet:** thường chạy một Pod trên mỗi node phù hợp, ví dụ logging/network agents.
- **PodDisruptionBudget (PDB):** giới hạn số Pod được gián đoạn theo cơ chế **voluntary eviction**; không ngăn mọi crash/node failure.
- **Static/critical system Pods:** yêu cầu vận hành khác, không tùy tiện xóa.

Quan sát:

```bash
kubectl get pdb -A

kubectl -n shop get deploy,statefulset,daemonset

kubectl -n shop get pods \
  -o wide
```

Một PDB quá chặt hoặc thiếu replica có thể làm `drain` không hoàn thành. Nếu node pool chỉ có một node chạy workload quan trọng, drain có thể gây outage dù có PDB. Cần thiết kế **nhiều replicas, phân bố node/zone, readiness và capacity dự phòng** từ trước.

Không sửa PDB về mức 0 chỉ để lệnh drain qua nhanh nếu chưa chấp nhận tác động tới availability.

## 14. DNS trong AKS: truy vấn đi qua những đâu?

Trong Kubernetes, Pod thường phân giải tên Service qua DNS cluster, do **CoreDNS** cung cấp trong cấu hình AKS phổ biến. Pod có thể gọi:

- `catalog-api`: tên rút gọn khi cùng namespace và search domain hoạt động.
- `catalog-api.shop.svc.cluster.local`: FQDN theo cluster domain mặc định thường gặp.
- `api.partner.example`: tên ngoài cluster, CoreDNS có thể forward tới upstream resolver.

Luồng khái niệm:

```text
Pod: shop/frontend
      |
      | nslookup catalog-api.shop.svc.cluster.local
      v
/etc/resolv.conf
      |
      v
Cluster DNS Service (thường tên kube-dns)
      |
      v
CoreDNS replicas
      |
      +-- Kubernetes service record
      |      └── ClusterIP/records tương ứng
      |
      +-- External zone
             └── Forward upstream / Azure DNS / corporate DNS
```

**Đừng nhầm:**

- **Azure DNS / Azure Private DNS** quản lý tên và private zone theo cấu hình Azure.
- **CoreDNS** phục vụ name resolution trong Kubernetes.
- **Kubelet/node DNS configuration** ảnh hưởng đường đi tới upstream resolvers và có thể ảnh hưởng Pod.
- **Service và EndpointSlices** quyết định backend network sau khi tên đã được phân giải.

Với headless Service hoặc các mô hình DNS đặc biệt, DNS có thể trả Pod IP thay vì ClusterIP. Không áp dụng cùng diễn giải record cho mọi loại Service.

## 15. Kiểm tra CoreDNS và DNS Service

Những lệnh đầu tiên là read-only:

```bash
kubectl -n kube-system get svc kube-dns -o wide

kubectl -n kube-system get deployments

kubectl -n kube-system get pods -o wide

kubectl -n kube-system get events \
  --sort-by=.metadata.creationTimestamp
```

Trong AKS phổ biến có deployment CoreDNS và Service tên `kube-dns`, nhưng **tên resource, labels và node-local DNS option có thể khác** theo phiên bản/cấu hình. Hãy quan sát kết quả thật thay vì mặc định một selector cố định.

Kiểm tra config DNS của Pod:

```bash
kubectl -n shop get pod <POD_NAME> \
  -o jsonpath='{.spec.dnsPolicy}{"\n"}'

kubectl -n shop exec <POD_NAME> -- cat /etc/resolv.conf
```

Lệnh `exec` yêu cầu container đang chạy và có binary `cat`; với image distroless, lệnh có thể không chạy dù DNS/ứng dụng vẫn khỏe. Tránh dùng `kubectl exec` nếu Pod không có quyền hoặc chính sách cấm thao tác này.

### Điều gì trong resolv.conf quan trọng?

Ví dụ:

```text
nameserver 10.0.0.10
search shop.svc.cluster.local svc.cluster.local cluster.local
options ndots:5
```

Địa chỉ 10.0.0.10 là **ví dụ**, không phải IP DNS cố định của AKS. Quan sát:

- `nameserver`: IP của DNS Service hoặc node-local DNS cache nếu cấu hình hỗ trợ.
- `search`: giúp phân giải tên ngắn theo namespace và domain cluster.
- `ndots`: ảnh hưởng thứ tự thử tên với search domains, có thể làm tăng số DNS queries nếu dùng nhiều hostname ngoài cluster.
- `dnsPolicy` / `dnsConfig`: có thể thay đổi resolver mặc định trên Pod.

Sửa CoreDNS ConfigMap hoặc DNS policy hàng loạt **không phải bước đầu tiên**. Cần biết lỗi do một Pod hay toàn cluster.

## 16. Thử DNS nội bộ và bên ngoài từ đúng nguồn

Một kiểm tra từ laptop không chứng minh DNS trong Pod hoạt động. Cần chạy phép thử từ **Pod gặp lỗi hoặc Pod debug trong cùng namespace/node/policy tương đương**.

Nếu container có sẵn `nslookup`:

```bash
kubectl -n shop exec <POD_NAME> -- \
  nslookup kubernetes.default.svc.cluster.local

kubectl -n shop exec <POD_NAME> -- \
  nslookup catalog-api.shop.svc.cluster.local

kubectl -n shop exec <POD_NAME> -- \
  nslookup example.com
```

Diễn giải:

| Test | Kết quả | Khoanh vùng |
|---|---|---|
| `kubernetes.default.svc.cluster.local` thất bại | Không phân giải Service cơ bản. | DNS của Pod, kube-dns/CoreDNS, đường mạng tới DNS. |
| Kubernetes Service cơ bản được, `catalog-api` thất bại | Lỗi tên, namespace, Service thiếu hoặc CoreDNS cache/config. | Kiểm tra Service và FQDN. |
| Internal FQDN được, external domain lỗi | Forwarding/upstream DNS, network egress hoặc DNS policy. | CoreDNS upstream và Azure/corporate DNS. |
| DNS trả đúng IP nhưng TCP timeout | DNS có thể ổn; xét route/policy/backend port. | Chuyển sang Service/network testing. |
| Tên private endpoint trả IP public hoặc NXDOMAIN | Private DNS/zone link/forwarder sai. | Azure Private DNS, custom resolver và link VNet. |

**NXDOMAIN** thường gợi ý tên không tồn tại tại resolver đang hỏi; **SERVFAIL** thường liên quan resolver/upstream không xử lý được; **timeout** có thể do traffic DNS bị chặn, resolver quá tải hoặc không phản hồi. Đây là tín hiệu chẩn đoán chứ không phải bằng chứng duy nhất.

### Khi container không có công cụ DNS

Một debug Pod riêng có thể hữu ích, nhưng **tạo Pod là thao tác thay đổi cluster**. Chỉ thực hiện nếu được phép:

```bash
kubectl -n shop run dns-check \
  --image=busybox:1.36 \
  --restart=Never \
  --command -- sleep 1800
```

Sau khi Pod ở trạng thái Running:

```bash
kubectl -n shop exec dns-check -- \
  nslookup catalog-api.shop.svc.cluster.local

kubectl -n shop exec dns-check -- \
  nslookup example.com
```

Khi hoàn tất, xóa Pod lab theo runbook đã phê duyệt; không tạo hàng loạt debug Pods trên Production. Image debug phải xuất phát từ registry được tổ chức tin cậy và có thể pull trong môi trường. Debug Pod **khác labels/service account/node** có thể chịu NetworkPolicy khác Pod gốc, vì vậy kết quả chỉ là một phép thử tương đối.

## 17. CoreDNS khỏe nhưng tên riêng vẫn lỗi

Có những nguyên nhân không thuộc deployment CoreDNS:

1. Service chưa được tạo hoặc tên/namespace sai.
2. Pod dùng `dnsPolicy: Default` thay vì policy phù hợp cho truy vấn Service.
3. Tên FQDN có cluster domain khác mặc định `cluster.local`.
4. CoreDNS đang forward zone tùy chỉnh tới DNS server không biết zone đó.
5. DNS cache của ứng dụng hoặc thư viện client giữ record cũ.
6. CoreDNS replica quá ít, CPU throttling hoặc bị lỗi khi load cao.
7. NetworkPolicy egress chặn UDP/TCP port 53 từ Pod tới DNS.
8. NodeLocal DNSCache hoặc plugin DNS tùy chọn gặp sự cố.
9. Custom DNS của VNet không forward đúng các zone cần thiết.
10. IP DNS Service hoặc service CIDR được cấu hình không phù hợp với thiết kế mạng.

Kiểm tra logs CoreDNS nếu có quyền:

```bash
kubectl -n kube-system logs deployment/coredns \
  --since=30m --all-containers=true
```

Nếu AKS cluster không dùng deployment tên `coredns` hoặc command không hỗ trợ theo cách triển khai, hãy tìm tên Pod/deployment thực tế từ `kubectl -n kube-system get deployments,pods` trước.

**Không bật CoreDNS query logging trên Production một cách tùy tiện**: có thể làm log rất lớn, tăng latency/chi phí và lộ hostname nội bộ. Cần có thời hạn, phê duyệt và biện pháp bảo vệ log.

## 18. Azure Private DNS, VNet DNS và private endpoints

Một ứng dụng AKS truy cập Azure SQL, Storage, Key Vault hoặc registry thông qua private endpoint cần cả **mạng riêng** và **DNS đúng**.

Ví dụ:

```text
AKS Pod
  |
  v
CoreDNS
  |
  v
Upstream DNS được cấu hình
  |
  v
Private DNS zone / resolver phù hợp
  |
  v
db-prod.database.windows.net
  --> Private Endpoint IP trong VNet
  |
  v
TCP tới private IP, route, firewall, authentication
```

Tên miền/zone cụ thể phụ thuộc dịch vụ Azure, private link configuration và hệ thống DNS. **Không tự tạo A record tùy ý** cho mọi service vì có thể làm hỏng cơ chế resolution khi endpoint đổi.

### Checklist

- Private endpoint đã ở trạng thái approved/connected?
- VNet dùng bởi AKS có **DNS resolution path** tới private zone liên quan?
- Private DNS zone có VNet link hoặc custom forwarder phù hợp?
- Nếu dùng on-prem DNS, có conditional forwarder đến Azure DNS Private Resolver hoặc hạ tầng resolver tương thích?
- Pod phân giải endpoint thành IP private mong muốn?
- NSG/UDR/Azure Firewall cho phép kết nối đến private IP và port đích?
- Identity/credential của ứng dụng vẫn hợp lệ?

**Private DNS resolve đúng không đồng nghĩa TCP/HTTPS đã thông.** Ngược lại, kết nối TCP tới IP trực tiếp thành công không chứng minh ứng dụng TLS với hostname/certificate đúng.

## 19. Service, selector, EndpointSlice và targetPort

Khi Pod đã Ready nhưng API không truy cập được qua Service, kiểm tra đường mapping.

Giả sử Deployment Pod có:

```yaml
metadata:
  labels:
    app: catalog-api
spec:
  containers:
    - name: catalog-api
      image: example.azurecr.io/catalog-api:1.2.0
      ports:
        - containerPort: 8080
```

Service:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: catalog-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
      protocol: TCP
```

Các bước đọc:

1. Service có `selector.app=catalog-api`.
2. Pod trong cùng namespace phải có label phù hợp.
3. Pod phải **Ready** để trở thành endpoint phục vụ traffic bình thường.
4. Client gọi Service port **80**.
5. Dataplane chuyển tới Pod IP trên **targetPort 8080**.
6. Ứng dụng phải **listen** trên port 8080 ở interface có thể được truy cập qua Pod IP (không chỉ `127.0.0.1`).

### Lệnh kiểm tra

```bash
kubectl -n shop get svc catalog-api -o yaml

kubectl -n shop get pods -l app=catalog-api -o wide

kubectl -n shop get endpointslice \
  -l kubernetes.io/service-name=catalog-api \
  -o yaml
```

Output YAML có thể dài; khi chia sẻ, che dữ liệu/annotations nhạy cảm.

Nếu Service có **0 endpoints**, kiểm tra:

- Selector đúng nhưng Pod không tồn tại?
- Pod có Ready=False?
- Service được khai báo **không có selector**, với EndpointSlice quản lý bên ngoài? (trường hợp đặc biệt)
- Pod thuộc namespace khác? Service selector chỉ chọn Pods trong namespace của Service.
- EndpointSlice controller hoặc trạng thái control plane có bất thường?

Nếu có endpoints nhưng kết nối lỗi, chuyển sang kiểm tra **đúng port, ứng dụng có listen, network policy và dataplane**. Không đổi DNS trước khi kiểm tra selector và readiness.

## 20. Phân biệt Pod IP, ClusterIP và Service DNS

Mỗi lớp có ý nghĩa khác nhau:

| Đích thử | Kiểm tra điều gì? | Hạn chế |
|---|---|---|
| **Pod IP:port** | Đường mạng trực tiếp đến Pod và ứng dụng. | Pod IP thay đổi khi recreate; có thể không reachable từ mọi mạng bên ngoài cluster. |
| **Service ClusterIP:port** | Routing/load balancing của Service qua Kubernetes dataplane. | Không kiểm tra DNS nếu gọi thẳng IP. |
| **Service FQDN:port** | Thêm lớp DNS bên cạnh Service routing. | Có thể bị DNS cache hoặc policy của Pod ảnh hưởng. |
| **Ingress/LB hostname** | Toàn chuỗi public/private entrypoint, TLS và backend. | Có thêm nhiều lớp gây lỗi; chẩn đoán cuối cùng sau khi kiểm tra nội bộ. |

Trình tự thử hợp lý từ một Pod debug được phép:

```text
1. http://<POD_IP>:8080/health
2. http://<SERVICE_CLUSTER_IP>:80/health
3. http://catalog-api.shop.svc.cluster.local/health
4. https://shop.example.com/health
```

Kết quả:

- **1 lỗi:** xem app listener, Pod, network policy, CNI.
- **1 được, 2 lỗi:** Service mapping/dataplane/policy.
- **2 được, 3 lỗi:** DNS name/path từ client.
- **3 được, 4 lỗi:** ingress/LB/external DNS/TLS/route.
- **Cả 4 được nhưng người dùng lỗi:** có thể do request path/header/auth, client network, DNS cache hoặc tải không đều.

Trình tự trên giả định bạn có **đường network hợp lệ** từ điểm thử đến từng IP. Cách thử `Pod IP` hoặc `ClusterIP` từ laptop bên ngoài cluster có thể thất bại hoàn toàn bình thường, tùy networking model.

## 21. CNI và địa chỉ IP: cơ chế mạng Pod trong AKS

AKS có nhiều mô hình mạng, chẳng hạn **Azure CNI Overlay** và **Azure CNI Pod Subnet** trên những phiên bản/cấu hình hỗ trợ; một số cluster cũ có thể dùng mô hình khác. Không nên suy ra mô hình CNI chỉ từ địa chỉ IP của Pod.

Các yếu tố cần hiểu:

- **Node IP:** địa chỉ của VM trong Azure VNet.
- **Pod IP:** do mô hình networking của cluster cấp phát; phạm vi/routing phụ thuộc network plugin.
- **Service CIDR:** vùng địa chỉ ảo cho Kubernetes Services, không phải một subnet Azure VM thông thường.
- **DNS Service IP:** nằm trong phạm vi service CIDR theo cấu hình cluster.
- **VNet/subnet CIDR:** vùng địa chỉ các VM, private endpoints hoặc Pod Subnet theo thiết kế.
- **Kube-proxy hoặc dataplane thay thế:** xử lý Kubernetes Service routing theo chế độ cluster; AKS có thể dùng các dataplane khác nhau.

Quan sát network profile:

```bash
az aks show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<AKS_CLUSTER>" \
  --query "networkProfile" \
  --output json
```

Cần kiểm tra `networkPlugin`, `networkPluginMode`, `networkDataplane`, `serviceCidr`, `dnsServiceIP` và những field được API trả về. Không giả định tất cả luôn hiện diện với cùng tên trong mọi version.

### IP exhaustion và overlapping CIDR

Một node pool có thể không mở rộng hoặc Pod không lấy được IP do:

- Subnet thiếu địa chỉ còn khả dụng theo mô hình cấp phát.
- Giới hạn `maxPods`/node và quy hoạch số node chưa đủ.
- Pod CIDR, service CIDR hoặc VNet/on-prem ranges chồng lấn trong topology liên quan.
- CNI/IPAM/agent gặp lỗi khi cấp phát IP.
- Hệ thống route hoặc NAT không hỗ trợ đường đi theo thiết kế.

**Chữa lỗi thiếu IP bằng cách tăng số node** chưa chắc giúp, đặc biệt khi subnet cấp IP cho node/Pod đã cạn. Cần đối chiếu thiết kế địa chỉ AKS đang dùng và subnet thực tế.

## 22. NetworkPolicy, NSG, route và firewall: bốn lớp khác nhau

| Lớp | Phạm vi | Kiểm tra |
|---|---|---|
| **Kubernetes NetworkPolicy** | Lọc ingress/egress của Pods được policy chọn theo network policy engine. | Namespace, labels, policy selectors, port/protocol, egress DNS. |
| **Azure NSG** | Lọc ở subnet/NIC hạ tầng Azure theo cơ chế network plugin và traffic path. | Source/destination CIDR, service tags, port, effective rules. |
| **User-defined routes (UDR)** | Chọn next hop của traffic trong VNet/subnet. | Route tới Azure Firewall/NVA, đường return path. |
| **Azure Firewall/NVA** | Kiểm soát egress/ingress theo network/security rules. | Application/network rules, FQDN, SNAT, logs. |

**Chặn ở bất kỳ lớp nào** có thể làm kết nối thất bại. Ngược lại, mở NSG chưa chắc vượt được Kubernetes NetworkPolicy. Với Azure CNI/Cilium hoặc dataplane khác, đường thực thi policy thay đổi; không nên mặc định mọi cluster dùng iptables/kube-proxy theo cùng mô hình.

### Kiểm tra NetworkPolicy

```bash
kubectl get networkpolicy -A

kubectl -n shop describe networkpolicy <POLICY_NAME>

kubectl -n shop get pod <POD_NAME> \
  --show-labels
```

Khi một policy chọn Pod và chặn egress mặc định, Pod có thể không gọi được CoreDNS nếu chưa có rule cho DNS theo cách thiết kế. Cần kiểm tra **UDP và TCP 53** khi loại truy vấn/response sử dụng tương ứng, và nguồn/đích DNS thực tế có thể là Service IP hoặc node-local cache tùy cấu hình.

### Phân biệt vấn đề DNS và policy

- `nslookup` timeout và Pod bị áp NetworkPolicy: kiểm tra egress DNS.
- `nslookup` trả đúng IP nhưng `curl` timeout: kiểm tra egress traffic tới port đích, NSG/route/firewall.
- Một namespace lỗi, namespace khác được: so NetworkPolicy, Pod labels, service account, DNS policy và node placement.
- Chỉ một node lỗi: kiểm tra node-level CNI/dataplane, route và network agents.

**Không “sửa” bằng cách xóa toàn bộ NetworkPolicy**. Mọi thay đổi policy phải có phê duyệt, thử trong lab và kiểm tra cả hướng ingress/egress.

## 23. Egress và SNAT: lỗi kết nối gián đoạn

Một dạng sự cố AKS phổ biến là **request ra ngoài cluster bị timeout ngẫu nhiên** khi số lượng kết nối đồng thời tăng. Ngoài DNS và endpoint availability, cần xem **SNAT port allocation/exhaustion** trong đường outbound.

Luồng có thể gồm:

```text
Pod → Node/CNI → AKS egress configuration
                 |
                 +-- Load Balancer outbound rules / NAT Gateway
                 +-- Azure Firewall / NVA
                 +-- UserDefinedRouting / egress gateway
                 |
                 v
           External API / database
```

Không phải mọi AKS cluster đi qua cùng một phương án outbound; hãy đọc `networkProfile.outboundType` và routing thực tế.

### Tín hiệu gợi ý SNAT/resource exhaustion

- Kết nối mới thường timeout nhưng kết nối tồn tại vẫn hoạt động.
- Lỗi tăng khi lượng outbound connection tăng đột biến.
- Một đích external service bị lỗi khi có nhiều replica cùng mở kết nối ngắn.
- Azure Monitor/Load Balancer/NAT Gateway/Firewall metrics cho thấy dấu hiệu giới hạn port/connections theo nguồn hỗ trợ.
- Tần suất lỗi giảm khi connection reuse/keep-alive được cải thiện.

Không kết luận SNAT exhaustion chỉ từ một log `ETIMEDOUT`. Kiểm tra thêm latency phía external API, firewall rules, DNS cache, connection pool và khả năng quota/network service.

### Hướng giảm thiểu

1. Reuse HTTP/TCP connections bằng keep-alive/connection pooling.
2. Kiểm tra DNS caching/TTL và request retry/backoff.
3. Thiết kế egress capacity/NAT Gateway/Firewall theo tải và tính năng hỗ trợ.
4. Giảm kết nối đồng thời vô hạn, có giới hạn mỗi client.
5. Dùng private endpoint hoặc service-to-service networking khi khả thi.
6. Theo dõi metrics outbound và kiểm thử tải có kiểm soát.

## 24. Ingress, Azure Load Balancer và lỗi client bên ngoài

Nếu nội bộ Service hoạt động nhưng người dùng bên ngoài gặp lỗi, hãy kiểm tra:

1. Client đang truy vấn **đúng DNS record** trỏ đến public/internal entrypoint chưa?
2. Ingress Controller/Application Gateway/gateway đã nhận đúng host/path chưa?
3. TLS certificate, SNI, hostname và HTTP/HTTPS redirect có đúng không?
4. Kubernetes Service có đúng loại và backend không?
5. External Load Balancer có frontend IP/rule/health probe phù hợp không?
6. NSG, firewall, route và private/public access policy có cho phép nguồn client?
7. Có endpoint Ready trong namespace và port đích?
8. Lỗi có chỉ xảy ra trên một ingress replica hoặc một zone không?

Lệnh quan sát:

```bash
kubectl get ingress -A

kubectl get svc -A -o wide

kubectl -n shop describe ingress <INGRESS_NAME>

kubectl -n shop describe svc <EXTERNAL_SERVICE_NAME>
```

**Một Ingress resource không tự bảo đảm có Ingress Controller**. AKS có thể dùng NGINX/AGIC/Application Gateway for Containers hoặc giải pháp khác tùy triển khai. Logs, health probes và layer mapping phụ thuộc controller cụ thể; không áp dụng một runbook NGINX cho mọi topology.

### 502, 503, 504 có luôn cùng ý nghĩa?

Không. Những status codes do ingress/gateway/proxy khác nhau trả về có semantics khác nhau. Quy ước thường gặp:

- **502:** gateway không có response hợp lệ từ upstream.
- **503:** upstream không sẵn sàng hoặc không có backend phục vụ.
- **504:** gateway timeout chờ upstream.

Nhưng một ứng dụng cũng có thể **tự trả các mã này**. Cần xem response headers, ingress logs, request ID và logs ứng dụng để xác định thành phần nào phát sinh lỗi.

## 25. Phân biệt lỗi TCP, HTTP và TLS

Một kết nối gồm nhiều giai đoạn:

```text
DNS lookup → TCP connect → TLS handshake → HTTP request
                                     |
                                     v
                               HTTP response
```

| Lỗi | Ý nghĩa có thể | Kiểm tra |
|---|---|---|
| `no such host` / `NXDOMAIN` | Tên DNS không được phân giải. | Resolver, hostname, zone/forwarder. |
| TCP timeout | Không có phản hồi kết nối theo thời gian chờ. | Route, policy, firewall, server down, SNAT. |
| `connection refused` | Đích phản hồi không có listener hoặc policy từ chối ở lớp tương ứng. | Port, app process, Service mapping. |
| TLS certificate verify failed | CA/hostname/expiry hoặc chain không hợp lệ. | Certificate, SAN, SNI, trust store. |
| HTTP 401/403 | Xác thực/ủy quyền trong app/proxy/dịch vụ đích. | Token, role, access policy; network có thể đã thông. |
| HTTP 404 | Route/path/host không khớp hoặc object không tồn tại. | Ingress rule, app path, version. |
| HTTP 5xx | Lỗi ứng dụng hoặc upstream/gateway. | Logs theo request ID, dependencies, probes. |

Ví dụ thử từ một điểm mạng được phép có công cụ `curl`:

```bash
curl -sv --connect-timeout 5 \
  http://catalog-api.shop.svc.cluster.local/health

curl -sv --connect-timeout 5 \
  https://shop.example.com/health
```

`curl -v` có thể in request/response headers chứa token hoặc cookies nếu người vận hành thêm chúng; **không đính kèm credential** khi chia sẻ log. Không dùng `curl -k` để bỏ kiểm tra TLS như một giải pháp Production; nếu dùng tạm để khoanh vùng thì phải ghi rõ kết quả không xác thực được server.

## 26. Khi nào cần debug Pod hoặc ephemeral container?

Nhiều application images tối giản (distroless) không có shell, `curl` hoặc `nslookup`. Bạn có ba lựa chọn:

1. Dùng tools/logging đã có trong container, nếu chính sách cho phép.
2. Tạo một **debug Pod** trong namespace tương tự để thử DNS/network.
3. Dùng **ephemeral debug container** cho Pod hiện có nếu Kubernetes feature, RBAC và policy hỗ trợ.

### Rủi ro khi dùng debug Pod

- Tạo Pod là thao tác thay đổi cluster và cần quyền.
- Debug image có thể không được phê duyệt hoặc chứa công cụ nhạy cảm.
- Pod debug có labels/node/service account khác với Pod gốc, làm NetworkPolicy/identity khác.
- Ephemeral container có thể yêu cầu quyền cao và tương tác runtime của Pod; phải được phê duyệt.
- Pod debug để quên gây tiêu hao tài nguyên hoặc giữ dữ liệu nhạy cảm.

**Nguyên tắc:** dùng image đã được tổ chức duyệt, thời hạn ngắn, không mount secrets của Production nếu không thực sự cần. Khi cần debug CNI/node, phối hợp nhóm Platform thay vì tùy tiện chạy privileged containers hoặc dùng host networking để bypass policy.

## 27. Azure Monitor, Container insights và logs hệ thống

AKS có các nguồn quan sát:

| Nguồn | Quan sát được |
|---|---|
| `kubectl get/describe/events` | Trạng thái Kubernetes gần thời điểm hiện tại, scheduling, probes và node conditions. |
| `kubectl logs` | Stdout/stderr của container theo cơ chế runtime và retention thực tế. |
| **Azure Monitor Container insights** | Pod/node inventory, performance và container logs khi đã cấu hình và có agent phù hợp. |
| **Azure Monitor managed Prometheus** | Metrics Kubernetes/Prometheus theo cấu hình scrape và môi trường hỗ trợ. |
| **Log Analytics** | Truy vấn logs lịch sử theo workspace, bảng và retention đã cấu hình. |
| **Azure Activity Log** | Những thao tác control-plane Azure như thay AKS resource, node pool, network resources. |
| **Network Watcher / flow logs/diagnostics** | Tín hiệu network tại lớp Azure khi tính năng và cấu hình hỗ trợ. |
| **Application Insights / OpenTelemetry** | Request traces, dependencies, exceptions khi ứng dụng được instrument. |

**Không tự động có mọi nguồn này** chỉ vì tạo AKS cluster. Cần kiểm tra add-ons, Data Collection Rules, workspaces, agent/extension, retention, RBAC và chi phí telemetry.

### Logs phục vụ chẩn đoán phải có correlation

Một log ứng dụng tốt có:

- UTC timestamp, service/version, namespace, Pod/replica identifier.
- Trace ID hoặc request ID.
- HTTP route/status/latency.
- Tên dependency bị lỗi và mã lỗi đã được làm sạch.
- Event khởi động/khởi tạo/secret refresh.

Không ghi password, token, storage account key, Kubernetes service account token hay dữ liệu cá nhân không cần thiết vào logs.

## 28. Log Analytics và KQL: tìm lỗi theo Pod hoặc thời gian

Khi AKS gửi container logs tới Log Analytics, **ContainerLogV2** là một bảng thường gặp trong cấu hình hiện đại. Bảng/cột có thể thay đổi theo phiên bản agent, DCR và workload logging schema.

Ví dụ tìm error logs của namespace `shop` trong hai giờ gần đây:

```kusto
ContainerLogV2
| where TimeGenerated > ago(2h)
| where PodNamespace == "shop"
| where tostring(LogMessage) has_any ("error", "exception", "failed")
| project TimeGenerated, PodNamespace, PodName,
          ContainerName, LogMessage
| order by TimeGenerated desc
```

Có thể tham khảo inventory của Pod nếu workspace thu thập:

```kusto
KubePodInventory
| where TimeGenerated > ago(2h)
| where Namespace == "shop"
| summarize LastSeen=max(TimeGenerated) by Name, PodStatus
| order by LastSeen desc
```

**Đây là ví dụ theo schema tham khảo**, không bảo đảm mọi workspace có hai bảng trên hoặc cùng tên cột. Mở **Tables** trong Log Analytics để xác minh schema trước khi kết luận “không có lỗi”.

### Kết hợp logs và metrics

Ví dụ HTTP 503 tăng lúc 08:15 UTC:

1. Xác định phiên bản Deployment được rollout lúc nào.
2. Xem `Ready replicas` và số endpoints vào thời điểm đó.
3. Truy vấn container errors từ 08:10–08:20.
4. Đối chiếu Node `NotReady`, CoreDNS, autoscaler events.
5. Nếu app call DB, mở traces theo request ID và kiểm tra dependency latency.
6. Kiểm tra Azure LB/NSG/Firewall nếu nội bộ Service khỏe nhưng client bên ngoài lỗi.

Không suy diễn rằng mọi log `timeout` là lỗi mạng Azure; timeout có thể do ứng dụng chờ lock, connection pool đầy hoặc database chạy chậm.

## 29. Chi phí quan sát và giữ bằng chứng sự cố

Log và monitoring có chi phí:

- Log Analytics ingestion/retention.
- Managed Prometheus metrics và lưu trữ tương ứng.
- Container insights agents và thu thập performance.
- Trace sampling, Application Insights ingestion.
- Network flow logs, Storage, export và retention.
- Nhân sự điều tra và chi phí thiết lập lab tái hiện.

Đừng tắt hoàn toàn error logs để giảm chi phí. Thay vào đó:

1. Giảm debug logs không cần thiết trong Production.
2. Sử dụng structured logging và mức log theo incident window.
3. Điều chỉnh retention theo mức rủi ro và quy định tổ chức.
4. Đặt sampling phù hợp cho traces/metrics mà vẫn giữ lỗi quan trọng.
5. Dùng budget/alerts, tags và ownership rõ ràng cho workspace.
6. Tránh ghi toàn bộ HTTP body, credential hoặc dữ liệu nhạy cảm.
7. Xây dashboard và runbook để giảm thời gian khôi phục (MTTR).

## 30. Quy tắc sửa lỗi an toàn: không xóa bằng chứng

Một thao tác thay đổi quá sớm có thể làm mất nguồn thông tin quan trọng. Trước restart/rollout/network edit:

- Lưu các Events, Pod status và logs có thể được phép lưu theo policy.
- Ghi tên image/digest, Deployment revision và thời điểm rollout.
- Kiểm tra ConfigMap/Secret *reference*, không chép secret value.
- Đối chiếu Service selector và EndpointSlices.
- Chọn phạm vi nhỏ nhất để thử.
- Kiểm tra rollback path và PodDisruptionBudget.
- Có phê duyệt cho thay đổi Production.
- Xác định metric/alert để chứng minh sự cố được giải quyết.

Các lệnh sau **thay đổi cluster**, chỉ thực hiện nếu được phép và theo runbook:

```bash
# Ví dụ thao tác tác động tới ứng dụng, KHÔNG chạy như bước điều tra mặc định:
kubectl -n shop rollout restart deployment/catalog-api

# Ví dụ rollback; cần xác minh revision đích và thay đổi dữ liệu liên quan:
kubectl -n shop rollout undo deployment/catalog-api
```

Rollback Deployment **không tự rollback** schema database, file trên persistent volume, dữ liệu ghi ra Storage hoặc thay đổi Azure network. Có thể cần quy trình migration/compensation riêng.

### Quy trình xác nhận sau sửa lỗi

1. Pod mới tạo được, scheduled và Ready.
2. Service có endpoints Ready đúng.
3. Request Pod IP → Service IP → Service DNS → Ingress thành công từ nguồn test hợp lệ.
4. Lỗi 5xx, timeout, restart và OOM giảm về mức bình thường.
5. Không xuất hiện lỗi mới ở node/CNI/CoreDNS.
6. Tỷ lệ thành công và latency đáp ứng SLO.
7. Những rule tạm, debug Pods và quyền tạm được thu hồi.
8. Ghi bài học và thay đổi bảo vệ trong IaC/GitOps.

## 31. Runbook xử lý sự cố theo 5 pha

### Pha 1 – Tiếp nhận và khoanh vùng

1. Ghi incident ID, UTC time và mức độ ảnh hưởng.
2. Xác định **chỉ một app**, **một namespace**, **một node**, **một zone** hay **toàn cluster**.
3. Xem các thay đổi gần nhất: rollout, secret rotation, DNS, VNet/NSG, AKS upgrade, autoscaling.
4. Không xóa Pod/node hoặc thay DNS khi chưa có bằng chứng.

### Pha 2 – Kiểm tra Pod và Service

1. `kubectl get pods -o wide`, `describe pod` và events.
2. Xem exit reason, readiness/liveness/startup probes.
3. Xem logs current/previous.
4. Kiểm tra Service selector, port/targetPort và EndpointSlices.
5. Nếu Pod chưa Ready, tập trung vào ứng dụng/scheduling trước.

### Pha 3 – Kiểm tra node và cluster

1. `kubectl get nodes`, `describe node`.
2. Node pool state, autoscaler, quota, capacity, IP allocation.
3. System Pods, network agents, CoreDNS và Kubernetes control plane reachability.
4. Nếu lỗi chỉ ở một node, so sánh node đó với node khỏe cùng pool.

### Pha 4 – Kiểm tra DNS/network/dependency

1. Từ đúng Pod/source, thử DNS internal/external.
2. Thử Pod IP, Service IP, Service FQDN theo phạm vi reachable.
3. Kiểm tra NetworkPolicy, CNI, NSG, UDR, Firewall.
4. Nếu chỉ ingress lỗi, kiểm tra controller, LB, TLS, DNS bên ngoài.
5. Nếu external API timeout gián đoạn, xét SNAT/connection pool/capacity.

### Pha 5 – Xử lý, chứng minh và học hỏi

1. Chọn sửa đổi nhỏ, có thể quay lui.
2. Đo endpoints Ready, success rate, p95 latency và các chỉ số lỗi.
3. Xác nhận ứng dụng hoạt động với request nghiệp vụ thật.
4. Dọn debug resources/temporary access, lưu bằng chứng.
5. Cập nhật runbook, cảnh báo và quy trình review thay đổi.

## 32. Tình huống A: Pod Running nhưng Ingress trả 503

**Bối cảnh:** triển khai `catalog-api:v2` thành công; Ingress trả 503. `kubectl get pods` cho thấy 3 Pod ở trạng thái Running, nhưng cột READY là `0/1`.

**Điều tra:**

1. `kubectl -n shop describe pod`: readiness probe `/ready` trả 404.
2. `kubectl -n shop get svc catalog-api`: port 80, targetPort 8080.
3. `kubectl -n shop get endpointslice -l kubernetes.io/service-name=catalog-api`: không có backend Ready.
4. Logs app cho thấy v2 đổi endpoint health từ `/ready` sang `/health/ready`, nhưng Deployment chưa cập nhật probe.

**Nguyên nhân:** readiness probe không khớp application route, khiến Pod không được chọn làm backend bình thường. Sự cố không nằm ở DNS hoặc public LB.

**Khắc phục:** sửa probe trong Deployment/IaC theo route thật, deploy an toàn, kiểm tra Pod Ready và EndpointSlice, sau đó xác minh qua Ingress.

**Bài học:** `Running` không đủ để xác định sẵn sàng nhận traffic. Dùng **Pod Conditions + EndpointSlices + request result**.

## 33. Tình huống B: Pod Pending sau khi tăng số replicas

**Bối cảnh:** Deployment tăng từ 6 lên 18 replicas. Sáu Pod mới `Pending`, Cluster Autoscaler không thêm node.

**Điều tra:**

1. Events có `Insufficient cpu` và `Too many pods`.
2. Node pool đã gần `maxCount`.
3. Một số node có pod IP/slot giới hạn theo networking model.
4. Azure quota và node pool policy được kiểm tra để xem còn khả năng mở rộng không.

**Hướng giải quyết:**

- Xác nhận capacity thực tế và Pod requests/limits.
- Điều chỉnh autoscaler/node pool theo phê duyệt nếu đủ quota/capacity/IP.
- Xem thiết kế subnet/pod address và maxPods.
- Tối ưu requests theo tải đo được, không giảm tùy ý.
- Kiểm tra cluster distribution và chi phí trước khi scale.

**Bài học:** không phải mọi Pod Pending đều do scheduler lỗi; giới hạn **CPU, pods/node, subnet IP, quota và node pool max** có thể kết hợp.

## 34. Tình huống C: DNS nội bộ được, Key Vault private endpoint lỗi

**Bối cảnh:** Pod giải được `kubernetes.default.svc.cluster.local` và Service nội bộ, nhưng không lấy được secret từ Key Vault private endpoint.

**Điều tra:**

1. Từ nguồn được phép, phân giải hostname Key Vault bằng resolver trong Pod.
2. Trả về IP không đúng theo thiết kế private endpoint.
3. CoreDNS nội bộ khỏe; upstream DNS/Private DNS zone link của VNet mới bị thay.
4. Sau khi xác định resolution path, nhóm Platform kiểm tra DNS forwarder, zone VNet link và record đúng.
5. Sau sửa, kiểm tra tiếp port 443, vault firewall, identity và Key Vault RBAC.

**Bài học:** CoreDNS vẫn chạy không chứng minh **external/private DNS zones** hoạt động; giải đúng IP cũng chưa chứng minh **HTTPS và authorization** thông suốt.

## 35. Tình huống D: chỉ một số Pod timeout tới external API

**Bối cảnh:** ứng dụng trên AKS gọi API thanh toán. Ban ngày request thành công; giờ cao điểm xuất hiện timeout kết nối mới.

**Điều tra:**

1. DNS external API phân giải đúng, thời điểm lỗi không trùng với thay đổi image.
2. Timeout tăng cùng số Pod và số outbound connections.
3. Đo retry rate, connection pool, external API latency và network egress metrics.
4. Kiểm tra outbound type, NAT/LB/Firewall metrics và dấu hiệu SNAT port pressure.
5. So sánh nguồn/đích và số kết nối để loại trừ rate limiting phía API.

**Hướng xử lý:** dùng keep-alive, giới hạn kết nối, backoff có jitter, đánh giá egress NAT capacity theo mô hình được hỗ trợ; không tăng retries vô hạn vì có thể làm vấn đề nặng hơn.

**Bài học:** lỗi gián đoạn theo tải không nhất thiết là “CoreDNS chập chờn”; phải đo **network connections, SNAT, dependency và application concurrency**.

## 36. Bài thực hành: khoanh vùng sự cố AKS theo từng lớp

**Môi trường giả định:** cluster AKS `aks-lab`, namespace `shop`, một Deployment `catalog-api`, Service `catalog-api` và Ingress `shop.example.com`. Đội thực hành chỉ có quyền đọc trong cluster, trừ khi được cho phép tạo debug Pod ở namespace lab.

### Kịch bản được giao

- Deployment có 3 replicas, hai Pod Ready, một Pod RestartCount tăng.
- Service `catalog-api` expose port 80 → targetPort 8080.
- Một số người dùng gặp HTTP 502/503 trong thời điểm rollout.
- Một service phụ thuộc cần truy cập hostname riêng trong Azure Private DNS.
- Logs báo cả lỗi startup lẫn vài timeout DNS.

### Nhiệm vụ

1. Ghi lại tenant, subscription, cluster context và UTC incident window.
2. Lấy trạng thái Pod với `kubectl get pods -o wide`.
3. Chọn Pod restart nhiều nhất, đọc `describe` và `logs --previous`.
4. Kiểm tra readiness/liveness/startup probes trong Deployment.
5. Đọc Service selector/targetPort, so với labels và Pod listening port.
6. Liệt kê EndpointSlices và số endpoint Ready thực tế.
7. Xem node chứa Pod lỗi có `NotReady` hoặc pressure không.
8. Kiểm tra cluster DNS Service và CoreDNS health.
9. Thử internal DNS, sau đó private hostname của dependency từ Pod/debug Pod phù hợp.
10. Nếu DNS trả IP đúng nhưng TCP vẫn timeout, nêu ba lớp mạng phải kiểm tra tiếp.
11. Phân biệt tình huống lỗi 502 đến từ ingress hay lỗi 500 do app trả về.
12. Đề xuất thay đổi nhỏ nhất, cơ chế xác nhận và phương án rollback.
13. Lập bảng nguồn bằng chứng để chuyển cho nhóm Platform/Networking.
14. Viết hai cảnh báo: một cho Pod restart/OOM; một cho HTTP 5xx/readiness.
15. Mô tả cách dọn debug Pod và thu hồi quyền tạm sau incident.

### Kết quả mong đợi

| Tầng | Lệnh hoặc dữ liệu | Câu hỏi cần trả lời |
|---|---|---|
| Cluster | `az account show`, `kubectl config current-context` | Có đúng cluster cần điều tra không? |
| Pod | `get pods`, `describe pod`, `logs --previous` | Container có crash, OOM hoặc probe lỗi không? |
| Node | `describe node`, node pool state | Node có pressure, NotReady hoặc scheduling bottleneck không? |
| Service | `get svc`, `get endpointslice` | Service có backend Ready và port đúng không? |
| DNS | `nslookup` internal/private | Query nào sai, resolver trả IP nào? |
| Network | NetworkPolicy, CNI, NSG, UDR, Firewall | Lớp nào có khả năng chặn traffic? |
| Ingress | Controller logs, LB health, request ID | Mã lỗi do lớp nào phát sinh? |
| Observability | Container logs, metrics, traces | Có bằng chứng theo UTC/time window không? |

### Lời giải tham khảo

1. **Pod có restart:** kiểm tra previous logs và last termination reason trước. Nếu liveness probe restart process do timeout startup, cần điều chỉnh probe theo hành vi ứng dụng đã đo.
2. **EndpointSlices thiếu một Pod:** nếu Pod thứ ba NotReady, Service bình thường chỉ chuyển traffic tới các Pod Ready. Đó chưa phải lỗi CoreDNS.
3. **Hai Pod Ready vẫn trả lỗi 5xx:** kiểm tra proxy/gateway upstream state, app logs và dependencies.
4. **Tên private DNS lỗi:** nếu internal Service DNS hoạt động, tập trung upstream/private zone resolution và network access thay vì khởi động lại CoreDNS ngay.
5. **Node pressure:** nếu Pod trên một node liên tục OOM/Evicted, chuyển tới kiểm tra requests/limits và node conditions, không chỉ nâng replica count.
6. **Kết thúc:** rollout điều chỉnh có phê duyệt, xác minh Ready endpoints, HTTP success, latency, restart rate và external dependency. Ghi lại sự cố để bổ sung cảnh báo và IaC.

### Tiêu chí nghiệm thu

- Có bằng chứng phân biệt **symptom, root cause và yếu tố góp phần**.
- Không dùng xóa/restart hàng loạt làm biện pháp điều tra mặc định.
- Đã xác minh **Pod → Service → DNS → Ingress** theo nguồn kết nối phù hợp.
- Nêu rõ ranh giới **Kubernetes vs Azure networking**.
- Đề xuất cách sửa nhỏ nhất có rollback.
- Có kết quả theo dõi sau sửa và kế hoạch ngăn tái diễn.

## 37. Tự kiểm tra kiến thức

**Câu 1.** Một Pod hiển thị `Running` nhưng `Ready=False`. Có thể kết luận nó đã nhận traffic bình thường từ Service không?

**Đáp án:** Không. `Running` không bảo đảm ứng dụng sẵn sàng; readiness quyết định trạng thái endpoint phục vụ traffic theo cơ chế Service bình thường.

**Câu 2.** `CrashLoopBackOff` là Pod phase hay tín hiệu container đang chờ restart?

**Đáp án:** Là waiting reason/thời gian backoff của container sau các lần chạy lỗi, không phải một Pod phase độc lập.

**Câu 3.** Pod `Pending` với event `Insufficient cpu` có được giải quyết chắc chắn bằng cách tăng memory limit không?

**Đáp án:** Không. Scheduler xem CPU requests và tài nguyên allocatable. Phải kiểm tra requests/node capacity/autoscaler thay vì sửa memory limit không liên quan.

**Câu 4.** ImagePullBackOff có nhất thiết do Azure Container Registry bị lỗi không?

**Đáp án:** Không. Có thể do sai image/tag, quyền image pull, expired credential, DNS, egress hoặc registry unavailable.

**Câu 5.** Vì sao `kubectl logs --previous` hữu ích với CrashLoopBackOff?

**Đáp án:** Container hiện tại có thể chưa khởi động hoặc không còn log lỗi; logs của instance trước giúp thấy exception hay quá trình exit.

**Câu 6.** Readiness probe thất bại có tự làm kubelet restart container không?

**Đáp án:** Không. Nó thường làm Pod NotReady; liveness/startup probe mới có hành vi restart khi vượt ngưỡng thất bại.

**Câu 7.** Node `NotReady` nhưng VM trong Azure vẫn `Running`. Có mâu thuẫn không?

**Đáp án:** Không. VM có thể hoạt động nhưng kubelet, CNI, container runtime hoặc đường mạng tới control plane bị lỗi.

**Câu 8.** Một Service có ClusterIP nhưng không có endpoint Ready. Có phải DNS chắc chắn sai không?

**Đáp án:** Không. Hãy kiểm tra selector, Pod labels, readiness, EndpointSlice và port trước.

**Câu 9.** Pod truy vấn `kubernetes.default.svc.cluster.local` được nhưng `example.com` không được. Lớp nào nên điều tra?

**Đáp án:** CoreDNS forwarding/upstream DNS, DNS policies, node DNS và egress tới resolver; không mặc định toàn bộ cluster DNS hỏng.

**Câu 10.** Phân giải Key Vault private endpoint thành đúng private IP có chứng minh App có quyền đọc secret không?

**Đáp án:** Không. Còn cần đường TCP/TLS, vault firewall và Key Vault/Entra permissions.

**Câu 11.** NetworkPolicy Allow có bỏ qua Azure NSG Deny không?

**Đáp án:** Không. Kubernetes policy, NSG, UDR và firewall là các lớp riêng; traffic phải đi qua những lớp áp dụng theo đường đi.

**Câu 12.** Một Pod chạy trên node khác lại không kết nối được Service. Có thể do đâu?

**Đáp án:** CNI/dataplane trên node, NetworkPolicy, route, node-level agent, Pod IP allocation hoặc backend Pod health; so sánh với node khỏe.

**Câu 13.** `kubectl top` không trả về metrics. Có thể kết luận Pod không dùng CPU/RAM không?

**Đáp án:** Không. Có thể metrics API/agent chưa có hoặc không hoạt động; dùng nguồn quan sát khác.

**Câu 14.** Vì sao request từ laptop tới ClusterIP có thể timeout dù Service bên trong AKS khỏe?

**Đáp án:** ClusterIP là địa chỉ Service nội bộ Kubernetes; từ bên ngoài cluster không mặc nhiên có route hoặc dataplane hỗ trợ tới đó.

**Câu 15.** HPA hoặc Cluster Autoscaler có luôn giải quyết tình trạng quá tải không?

**Đáp án:** Không. Node pool maxCount, quota/capacity, IP exhaustion, PDB, constraints, metrics và bottleneck ứng dụng có thể hạn chế scale.

**Câu 16.** Khi external request timeout tăng theo tải, ngoài DNS cần kiểm tra điều gì?

**Đáp án:** Connection pool, egress outboundType, NAT/LB SNAT, firewall, retry và tình trạng external API.

**Câu 17.** Khi ingress trả 503, có thể chắc chắn Ingress Controller hỏng không?

**Đáp án:** Không. Có thể Service không có endpoints Ready, upstream app lỗi hoặc một proxy khác trả mã này. Cần correlation logs và backend health.

**Câu 18.** Vì sao không nên tắt NetworkPolicy hoặc mở NSG mọi nguồn để thử ngay trên Production?

**Đáp án:** Có thể tạo rủi ro lộ dịch vụ, mất kiểm soát an ninh và khó xác định root cause. Cần thử hẹp, có phê duyệt, thời hạn và rollback.

**Câu 19.** Nếu một Pod vừa OOMKilled, thao tác restart có phải sửa triệt để?

**Đáp án:** Không. Nếu memory leak/limit/request hoặc tải không được giải quyết, Pod có thể OOM lại; cần đo memory và tìm nguyên nhân.

**Câu 20.** Để chứng minh incident đã kết thúc, chỉ cần Pod Ready trở lại chưa?

**Đáp án:** Chưa. Cần kiểm tra Service endpoints, DNS/network path, request thành công, latency/SLO, dependencies, alerts và việc thu hồi quyền/debug resources tạm.

**Tóm lại:** Chẩn đoán AKS hiệu quả là đi từ **bằng chứng ở Pod và node**, kiểm tra **Service/EndpointSlice**, xác minh **CoreDNS và DNS upstream**, sau đó mới mở rộng sang **CNI, NetworkPolicy, VNet, NSG, UDR, firewall, Load Balancer và dependency**. Không lấy `Running` làm bằng chứng hệ thống khỏe; không coi `kubectl restart` là phương pháp tìm nguyên nhân. Một quy trình đáng tin cậy luôn có **phạm vi sự cố rõ ràng, phép thử tại đúng nguồn, thay đổi nhỏ có thể rollback và số liệu chứng minh dịch vụ đã phục hồi**.
