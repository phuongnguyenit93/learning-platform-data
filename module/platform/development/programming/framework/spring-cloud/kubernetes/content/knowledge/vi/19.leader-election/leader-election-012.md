# Kiểm thử chuyển giao vai trò giữa nhiều Pod

## 1. Cần chứng minh điều gì khi leader thay đổi?

Trong module **SPRING_CLOUD_KUBERNETES**, bầu leader thường chọn một bản sao Spring chạy scheduler, quét công việc hoặc phát lệnh đồng bộ. Kiểm thử chuyển giao phải chứng minh công việc tiếp tục đúng khi Pod đang điều phối không còn làm việc.

Một dòng log “đã nhận leadership” chưa đủ. Leader mới có thể chưa khởi động scheduler, không tới được cơ sở dữ liệu hoặc đang chờ giao dịch cũ. Leader cũ cũng có thể tiếp tục gửi request dù bản ghi election đã đổi.

Ba nhóm thuộc tính cần kiểm tra:

| Thuộc tính | Câu hỏi |
| --- | --- |
| An toàn — safety | Có tác dụng phụ trùng hoặc lệnh cũ được chấp nhận trái quy tắc không? |
| Khả năng tiếp tục — liveness | Khi còn ứng viên đủ điều kiện, công việc có tiếp tục trong thời hạn chấp nhận được không? |
| Ổn định | Sau hội tụ, leadership và scheduler có ổn định thay vì liên tục đổi qua lại không? |

“Không quá một leader” và “luôn luôn có một leader” là hai yêu cầu khác nhau. Một khoảng chưa có leader có thể xuất hiện khi chuyển giao. Cần đặt giới hạn phục hồi cụ thể thay vì yêu cầu hệ thống không có bất kỳ gián đoạn nào.

Bài thực hành dùng ba Pod, tạo lỗi có kiểm soát và đối chiếu bằng chứng tại Kubernetes, ứng dụng và nơi chấp nhận tác dụng phụ. Kết quả có thể là **PASS**, **FAIL** hoặc **INCONCLUSIVE** khi thiếu bằng chứng.

## 2. Cố định implementation và cấu hình hiệu lực

### 2.1. Phạm vi ví dụ

Các cấu hình và listener trong bài nhắm tới **Spring Cloud Kubernetes 3.3, cơ chế Fabric8 leader dựa trên ConfigMap**. Cơ chế này tích hợp API leader election của Spring Integration và phát `OnGrantedEvent`, `OnRevokedEvent`. Dự án dùng nhánh khác cần đối chiếu tài liệu đúng dependency trước khi áp dụng. [Nguồn: Spring Cloud Kubernetes 3.3 — Leader Election](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/leader-election.html).

Không coi nhánh ví dụ là lựa chọn mặc định cho mọi dự án mới. Ghi phiên bản chính xác và dùng Spring Boot/Spring Cloud release train tương thích.

| Thành phần | Ví dụ Fabric8/ConfigMap | Khi đổi implementation |
| --- | --- | --- |
| Tài nguyên phối hợp | ConfigMap | Có thể là Lease hoặc ConfigMap |
| Sự kiện ứng dụng | `OnGrantedEvent`, `OnRevokedEvent` | Kiểm tra API đúng phiên bản |
| Phát hiện leader không hợp lệ | Liên quan Ready của Pod và cập nhật/watch | Có thể dựa vào renewal và thời hạn Lease |
| Tham số thời gian | `leader.update-period` | Có thể có retry period, renew deadline, lease duration |
| RBAC | ConfigMap và đọc/watch Pod | Có thể cần `coordination.k8s.io/leases` |

Không lấy kỳ vọng “Lease hết hạn sau 15 giây” để kiểm tra cơ chế ConfigMap ở đây.

Trong mã nguồn 3.3.0, controller kiểm tra Pod của leader được ghi trong ConfigMap có Ready không trước khi giữ hoặc thay leader. Nếu control plane vẫn thấy Pod Ready, chỉ chặn đường mạng từ ứng dụng tới API server chưa chắc tạo chuyển giao. [Nguồn: Fabric8LeadershipController 3.3.0](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.0/spring-cloud-kubernetes-fabric8-leader/src/main/java/org/springframework/cloud/kubernetes/fabric8/leader/Fabric8LeadershipController.java).

### 2.2. Hồ sơ cấu hình trước mỗi lần chạy

Ghi lại:

- Phiên bản Spring Boot, Spring Cloud Kubernetes, Kubernetes và CNI.
- Image digest hoặc tag bất biến.
- Namespace, tài nguyên election và role nghiệp vụ.
- Khoảng kiểm tra, client timeout, reconnect theo implementation.
- Replica, probe, thời gian shutdown và chiến lược rollout.
- Chính sách retry, checkpoint, idempotency và fencing của tác vụ.

Trong nhánh 3.3, `spring.cloud.kubernetes.leader.update-period` có mặc định 60 giây. Lab đặt 2 giây để dễ quan sát. Đó là chu kỳ kiểm tra trạng thái, không phải TTL được bảo đảm cho leadership. [Nguồn: Common application properties 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/appendix.html).

Không thay timeout giữa các lần chạy rồi so kết quả như thể điều kiện giống nhau.

## 3. Thiết kế nhóm Pod và nguồn bằng chứng

### 3.1. Topology

```text
Bộ điều khiển kiểm thử
  |-- hỏi từng Pod và quan sát Kubernetes API
  |-- tạo một fault tại một thời điểm
  |-- kiểm tra job và tác dụng phụ tại sink
  |
  +-- Namespace riêng
       |-- Pod A ----+
       |-- Pod B ----+--> cùng ConfigMap + cùng role
       |-- Pod C ----+
       |
       +-- leader --> sink nghiệp vụ --> kho dữ liệu bền vững
```

Ba Pod dùng cùng namespace election, cùng ConfigMap và cùng role, nhưng định danh ứng viên phải khác nhau. Với cấu hình mặc định dùng hostname làm candidate ID, không đặt cùng hostname cố định cho mọi Pod.

Mỗi chiến dịch có `run_id` riêng. Mỗi công việc có `job_key` ổn định qua retry và chuyển leader. Sink là dịch vụ kiểm thử hoặc downstream trong môi trường tích hợp, có khả năng ghi lại kết quả thực sự được chấp nhận.

Không dùng bộ nhớ riêng trong từng Pod làm nguồn sự thật duy nhất: khi Pod chết, bộ đếm và dữ liệu chưa đẩy ra ngoài cũng mất.

### 3.2. Quan sát ba lớp

| Lớp | Bằng chứng | Giới hạn |
| --- | --- | --- |
| Election | Nội dung ConfigMap hoặc Lease | Không chứng minh scheduler đã chạy |
| Ứng dụng | Listener, trạng thái từng Pod, phiên scheduler | Có thể chậm hoặc mất khi crash |
| Nghiệp vụ | Job hoàn tất, kết quả sink, lệnh bị từ chối | Phải gắn đúng run và job |

Pod không trả lời phải được ghi là **UNKNOWN/UNREACHABLE**. Không chuyển lỗi truy vấn thành `leader=false`; cách đó có thể che leader cũ vẫn đang gây tác dụng phụ.

Không gọi một Kubernetes Service nhiều lần rồi coi như đã hỏi đủ mọi Pod. Service DNS, DiscoveryClient hoặc Spring Cloud LoadBalancer có thể đưa nhiều request vào cùng một bản sao. Bộ quan sát phải hỏi từng Pod có định danh cụ thể.

### 3.3. Nhận diện đúng phiên tiến trình

Các trường cần thu gồm:

```text
run_id, namespace, pod_name, pod_uid, boot_id
role, local_generation, event_sequence
job_key, authority_epoch nếu có fencing
event_type, thời điểm quan sát
```

Pod UID phân biệt Pod cũ và Pod thay thế. `boot_id` phân biệt các lần JVM khởi động trong cùng Pod sau container restart. `local_generation` phân biệt các lần cùng JVM nhận leadership.

Generation cục bộ giúp quan sát và tránh task dùng nhầm phiên trong tiến trình; nó không phải fencing token có thứ tự toàn cục.

## 4. Thêm điểm quan sát vào ứng dụng Spring

### 4.1. Listener và endpoint lab

Ví dụ dùng Java 17 trở lên, Spring Web và các leader event của Spring Integration. Đặt lớp trong package được Spring Boot quét; import các kiểu từ Java và Spring tương ứng.

```java
@RestController
@Profile("leader-lab")
public class LabLeadershipProbe {
    private static final Logger log =
            LoggerFactory.getLogger(LabLeadershipProbe.class);

    public record Snapshot(
            String runId, String podName, String podUid,
            String bootId, String role,
            boolean leader, long generation,
            long eventSequence, Instant changedAt) {}

    private final String runId;
    private final String podName;
    private final String podUid;
    private final String role;
    private final String bootId = UUID.randomUUID().toString();
    private volatile Snapshot snapshot;

    public LabLeadershipProbe(
            @Value("${LAB_RUN_ID}") String runId,
            @Value("${POD_NAME}") String podName,
            @Value("${POD_UID}") String podUid,
            @Value("${spring.cloud.kubernetes.leader.role}") String role) {
        this.runId = runId;
        this.podName = podName;
        this.podUid = podUid;
        this.role = role;
        this.snapshot = state(false, 0, 0);
    }

    @EventListener
    public synchronized void onGranted(OnGrantedEvent event) {
        if (!role.equals(event.getRole())) {
            return;
        }
        Snapshot old = snapshot;
        long nextGeneration = old.leader()
                ? old.generation() : old.generation() + 1;
        snapshot = state(true, nextGeneration, old.eventSequence() + 1);
        log.info("event=LEADERSHIP_GRANTED snapshot={}", snapshot);
    }

    @EventListener
    public synchronized void onRevoked(OnRevokedEvent event) {
        if (!role.equals(event.getRole())) {
            return;
        }
        Snapshot old = snapshot;
        snapshot = state(false, old.generation(), old.eventSequence() + 1);
        log.info("event=LEADERSHIP_REVOKED snapshot={}", snapshot);
    }

    @GetMapping("/lab/leadership")
    public Snapshot current() {
        return snapshot;
    }

    private Snapshot state(boolean leader, long generation, long sequence) {
        return new Snapshot(
                runId, podName, podUid, bootId, role,
                leader, generation, sequence, Instant.now());
    }
}
```

Các import chính: `org.springframework.integration.leader.event.OnGrantedEvent`, `OnRevokedEvent`, `org.springframework.context.event.EventListener`, `org.springframework.context.annotation.Profile`, `org.springframework.beans.factory.annotation.Value`, các annotation Spring Web, SLF4J, `java.time.Instant` và `java.util.UUID`.

Endpoint phản ánh sự kiện cục bộ đã nhận; nó không xác nhận quyền ghi tại sink. Quan sát thêm `SCHEDULER_STARTED`, `TASK_STARTED`, `TASK_COMMITTED`, `SCHEDULER_STOPPED` với cùng định danh phiên.

Giữ listener ngắn, không chạy job dài trong callback cấp leadership. Nếu có nhiều listener, không mặc định thứ tự cập nhật probe và khởi động scheduler giống nhau. Task đã khởi tạo cần giữ snapshot phiên bất biến, không đọc token mới từ biến toàn cục để tiếp tục công việc của phiên cũ.

### 4.2. Điểm tạo crash có thể tái lập

Image lab có thể cung cấp endpoint làm JVM dừng đột ngột:

```java
@RestController
@Profile("leader-lab")
public class LabCrashController {
    @PostMapping("/lab/faults/halt")
    public void halt() {
        Runtime.getRuntime().halt(137);
    }
}
```

`halt` không chạy shutdown hooks. Mã thoát 137 ở đây do ứng dụng chủ động chọn, không chứng minh hệ điều hành đã OOM-kill tiến trình.

Chỉ bật controller trong lab riêng, truy cập qua kênh quản trị tới đúng Pod. Nếu đã có công cụ process-kill được kiểm chứng, dùng nó thay endpoint. Endpoint lab cần nằm ngoài đường truy cập công khai.

## 5. Chuẩn bị ba Pod cùng tranh một role

### 5.1. Điều kiện của image

Image cần có Spring Web, Actuator, dependency leader Fabric8 tương thích và các điểm quan sát trên. Artifact leader của nhánh ví dụ là `spring-cloud-kubernetes-fabric8-leader`; ứng dụng cũng cần cấu hình Fabric8 client phù hợp.

Ứng dụng lab phải bổ sung scheduler và sink theo hợp đồng:

- Chỉ phiên hoạt động được nhận công việc mới.
- Thu hồi leadership yêu cầu dừng scheduler và task theo chính sách.
- Job chưa xong được lấy lại từ trạng thái bền vững.
- Retry giữ nguyên khóa nghiệp vụ.
- Sink thực thi idempotency và fencing nếu đó là yêu cầu cần chứng minh.

Các endpoint, `LAB_RUN_ID` và sink là thành phần của ứng dụng kiểm thử, không phải tính năng Spring Cloud Kubernetes tự sinh.

### 5.2. Manifest nền

Khi thực hành, lưu manifest vào tệp lab và thay image bằng image đã build, có thể pull từ cluster. Dùng namespace riêng cho chiến dịch.

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: sck-leader-lab
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: leader-lab
  namespace: sck-leader-lab
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: leader-lab-lock
  namespace: sck-leader-lab
data: {}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: leader-lab
  namespace: sck-leader-lab
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["leader-lab-lock"]
    verbs: ["get", "watch", "update", "patch"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: leader-lab
  namespace: sck-leader-lab
subjects:
  - kind: ServiceAccount
    name: leader-lab
    namespace: sck-leader-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: leader-lab
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: leader-lab
  namespace: sck-leader-lab
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: leader-lab
  template:
    metadata:
      labels:
        app: leader-lab
    spec:
      serviceAccountName: leader-lab
      terminationGracePeriodSeconds: 30
      containers:
        - name: app
          image: registry.example.com/training/leader-lab:replace-me
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: leader-lab
            - name: LAB_RUN_ID
              value: handover-001
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
            - name: POD_UID
              valueFrom:
                fieldRef:
                  fieldPath: metadata.uid
            - name: POD_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
            - name: SPRING_CLOUD_KUBERNETES_CLIENT_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
            - name: SPRING_CLOUD_KUBERNETES_LEADER_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
            - name: SPRING_CLOUD_KUBERNETES_LEADER_ENABLED
              value: "true"
            - name: SPRING_CLOUD_KUBERNETES_LEADER_ROLE
              value: invoice-scheduler
            - name: SPRING_CLOUD_KUBERNETES_LEADER_CONFIGMAPNAME
              value: leader-lab-lock
            - name: SPRING_CLOUD_KUBERNETES_LEADER_CREATECONFIGMAP
              value: "false"
            - name: SPRING_CLOUD_KUBERNETES_LEADER_UPDATEPERIOD
              value: 2s
            - name: SPRING_CLOUD_KUBERNETES_DISCOVERY_ENABLED
              value: "false"
            - name: SPRING_CLOUD_KUBERNETES_CONFIG_ENABLED
              value: "false"
            - name: SPRING_CLOUD_KUBERNETES_SECRETS_ENABLED
              value: "false"
            - name: SPRING_CLOUD_KUBERNETES_RELOAD_ENABLED
              value: "false"
            - name: MANAGEMENT_ENDPOINT_HEALTH_PROBES_ENABLED
              value: "true"
            - name: MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE
              value: health,info
            - name: SERVER_SHUTDOWN
              value: graceful
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 2
            failureThreshold: 60
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 3
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 1Gi
```

Manifest tạo sẵn ConfigMap và đặt `create-config-map=false`, nên ServiceAccount không cần quyền tạo ConfigMap. Watch theo tên phải tương thích request của client; nếu gặp 403, kiểm tra request và audit log trước khi mở rộng quyền.

Bổ sung cấu hình sink theo ứng dụng lab, giữ giống nhau giữa ba Pod. Dùng Secret cho thông tin xác thực và không đưa giá trị Secret vào báo cáo.

Follower vẫn phải có thể Ready khi ứng dụng đã sẵn sàng. Nếu readiness phụ thuộc “tôi là leader”, mọi ứng viên có thể không đủ điều kiện nhận leadership trong implementation này.

## 6. Dựng đường cơ sở trước khi gây lỗi

Các lệnh dưới đây dùng PowerShell. Bộ quan sát cần kubeconfig có quyền đọc tài nguyên; quyền port-forward hoặc Pod proxy được cấp riêng cho người chạy.

```powershell
$labNamespace = 'sck-leader-lab'
$labSelector = 'app=leader-lab'

kubectl config current-context
kubectl apply -f .\leader-lab.yml
kubectl -n $labNamespace rollout status deployment/leader-lab --timeout=180s
kubectl -n $labNamespace get pods -l $labSelector -o wide

kubectl auth can-i get configmap/leader-lab-lock -n $labNamespace --as=system:serviceaccount:sck-leader-lab:leader-lab
kubectl auth can-i update configmap/leader-lab-lock -n $labNamespace --as=system:serviceaccount:sck-leader-lab:leader-lab
```

Người chạy cần quyền impersonation để dùng `--as`. Nếu thiếu quyền đó, lỗi của lệnh không chứng minh ServiceAccount ứng dụng thiếu quyền. Kiểm tra thêm get/watch Pod và watch ConfigMap khi điều tra đường bầu chọn.

Mở cửa sổ quan sát tài nguyên election:

```powershell
kubectl -n $labNamespace get configmap leader-lab-lock -w -o yaml
```

Mở cửa sổ thu log:

```powershell
kubectl -n $labNamespace logs -l $labSelector --all-containers=true --prefix=true --timestamps=true --max-log-requests=10 --tail=-1 -f
```

Không coi một phiên `kubectl logs -f -l ...` là bộ thu tự động đầy đủ của mọi Pod tạo về sau. Sau khi tập Pod thay đổi, gắn lại luồng log hoặc dùng hệ thống log tập trung. Với container restart, lấy thêm log lần trước bằng `kubectl logs --previous` nếu còn tồn tại.

Đọc ứng viên đang được ghi nhận:

```powershell
$lockJson = kubectl -n $labNamespace get configmap leader-lab-lock -o json
if ($LASTEXITCODE -ne 0) { throw 'Không đọc được tài nguyên election' }
$lock = $lockJson | ConvertFrom-Json
$leaderPod = $lock.data.'leader.id.invoice-scheduler'
if ([string]::IsNullOrWhiteSpace($leaderPod)) {
    throw 'Chưa có leader trong bản ghi election'
}
kubectl -n $labNamespace get pod $leaderPod -o wide
```

Khóa data trên dùng prefix mặc định và role của ví dụ; nó không phải schema chung cho mọi implementation.

Để hỏi đúng Pod, port-forward trong một terminal:

```powershell
kubectl -n $labNamespace port-forward pod/$leaderPod 18081:8080
```

Ở terminal khác:

```powershell
Invoke-RestMethod http://127.0.0.1:18081/lab/leadership
```

Bộ thu tự động cũng có thể dùng Kubernetes Pod proxy khi được cấp quyền `get pods/proxy`:

```powershell
$podListJson = kubectl -n $labNamespace get pods -l $labSelector -o json
if ($LASTEXITCODE -ne 0) { throw 'Không lấy được tập Pod' }
$labPods = $podListJson | ConvertFrom-Json

foreach ($labPod in $labPods.items) {
    $podName = $labPod.metadata.name
    $proxyPath = "/api/v1/namespaces/$labNamespace/pods/${podName}:8080/proxy/lab/leadership"
    $sampleJson = kubectl --request-timeout=3s get --raw $proxyPath
    if ($LASTEXITCODE -eq 0) {
        $sampleJson | ConvertFrom-Json
    } else {
        [pscustomobject]@{ podName = $podName; state = 'UNKNOWN' }
    }
}
```

Đây là một lượt lấy mẫu, chưa phải bộ kiểm thử hoàn chỉnh. Lặp lại với timeout và cửa sổ ổn định ở mục 7. Không cấp quyền Pod proxy cho tài khoản ứng dụng chỉ để tiện quan sát. Nếu có Spring Security, bổ sung xác thực cho endpoint lab và cho phép probe truy cập theo cấu hình triển khai.

Baseline đạt khi ba Pod sẵn sàng, cùng role/tài nguyên election, có đúng một leader cục bộ ổn định trong cửa sổ quan sát và sink cho thấy job thực sự tiến triển. Nếu baseline đã flapping hoặc không có tiến triển, chưa gây thêm lỗi.

## 7. Mốc thời gian và tiêu chí PASS

### 7.1. Đo riêng election và phục hồi nghiệp vụ

```text
T_request : bộ điều khiển gửi yêu cầu gây lỗi
T_fault   : lỗi thực sự có hiệu lực
T_grant   : phiên mới nhận leadership
T_start   : scheduler của phiên mới bắt đầu
T_commit  : tác dụng phụ hợp lệ đầu tiên của phiên mới được sink chấp nhận
T_stable  : đạt cửa sổ ổn định đã định trước
```

Có thể định nghĩa:

```text
recovery_time = T_commit - T_fault
```

Nếu không đo được `T_fault` chính xác, dùng `T_request` làm mốc end-to-end và ghi rõ giới hạn đó. Không đổi cách tính giữa các kịch bản.

Ví dụ tiêu chí của **lab**, phải điều chỉnh theo môi trường:

- Có tiến triển nghiệp vụ từ một phiên hợp lệ trong 60 giây sau fault.
- Sau hội tụ, cùng một phiên hoạt động ổn định ít nhất 10 giây.
- Không có tác dụng phụ trùng cho cùng job.
- Không có lệnh phiên cũ được chấp nhận sau điểm cắt fencing đã xác định.

Đây là SLO của phép thử, không phải bảo đảm mặc định của Spring Cloud Kubernetes.

### 7.2. Polling có giới hạn

Không dùng một lần sleep dài rồi chỉ hỏi trạng thái cuối:

```text
deadline = đồng hồ đơn điệu hiện tại + timeout
lặp tới deadline:
    thu mẫu từng Pod, tài nguyên election và tiến triển tại sink
    lưu lỗi quan sát, không đổi lỗi thành follower
    nếu hội tụ và tiến triển đạt điều kiện:
        bắt đầu hoặc tiếp tục cửa sổ ổn định
        nếu cửa sổ đủ dài: PASS
    nếu điều kiện bị phá vỡ:
        đặt lại cửa sổ ổn định
    chờ một khoảng lấy mẫu ngắn có giới hạn
hết deadline: FAIL hoặc INCONCLUSIVE theo bằng chứng
```

Dùng đồng hồ đơn điệu của bộ điều khiển để tính timeout. Từng request quan sát cũng cần timeout, nếu không một Pod treo có thể khóa cả phép thử.

Khoảng lấy mẫu quyết định độ phân giải quan sát. Không thấy hai leader trong các mẫu cách nhau một giây không chứng minh không có overlap ngắn hơn một giây. Kết hợp event, task journal và hàng rào tại sink.

Timestamp giữa các JVM có thể lệch. Ưu tiên thứ tự chấp nhận tại hệ thống đích và giao thức fencing thay vì chỉ so đồng hồ các Pod.

## 8. Các kịch bản chuyển giao

### 8.1. Dừng có kiểm soát leader hiện tại

1. Đọc lại leader ngay trước fault, không dùng tên đã lưu từ một lần chạy trước.
2. Ghi Pod UID, boot ID, phiên scheduler và tiến độ sink.
3. Thu bằng chứng và gửi yêu cầu xóa đúng Pod leader.
4. Quan sát shutdown, cập nhật election, grant mới và commit mới.
5. Chờ cửa sổ ổn định, đối chiếu job cũ và job mới.

```powershell
# $leaderPod được đọc lại từ baseline ngay trước kịch bản.
kubectl -n $labNamespace get pod $leaderPod -o json
kubectl -n $labNamespace delete pod $leaderPod --wait=false
```

Đây là yêu cầu kết thúc có grace period. `--wait=false` chỉ làm client không chờ xong; nó không biến thao tác thành crash. Kubernetes cố gắng thực hiện luồng dừng trước khi cưỡng bức khi cần. [Nguồn: Kubernetes — Termination of Pods](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/).

Kiểm tra leader cũ ngừng nhận job mới, task đang chạy tuân thủ chính sách hoàn tất/hủy, leader mới tiếp tục tiến độ và không tạo kết quả trùng.

Deployment có thể tạo Pod thay thế. Không ép B thắng thay vì C hoặc Pod mới; chỉ kiểm tra ứng viên thắng hợp lệ.

Trong đường dừng có kiểm soát, log revoke là bằng chứng hữu ích. Nếu log thiếu, đối chiếu nguồn khác trước khi kết luận; không lấy riêng sự có mặt hoặc vắng mặt một dòng log làm kết quả cuối.

### 8.2. Làm JVM dừng đột ngột

1. Đọc lại leader, port-forward tới đúng Pod.
2. Ghi `restartCount`, Pod UID và boot ID.
3. Gọi endpoint halt ở terminal thứ hai:

```powershell
Invoke-WebRequest -Method Post -Uri http://127.0.0.1:18081/lab/faults/halt
```

Client có thể nhận lỗi kết nối vì JVM dừng trước khi trả response. Xác minh trạng thái container và boot ID, không coi lỗi HTTP là bằng chứng duy nhất.

```powershell
kubectl -n $labNamespace get pod $leaderPod -o json
kubectl -n $labNamespace logs $leaderPod -c app --previous --timestamps
```

Kubelet có thể khởi động lại container trong cùng Pod. JVM mới có thể nhận lại leadership trước follower khác. Đây vẫn là phục hồi nếu tiêu chí cho phép. Nếu mục tiêu bắt buộc chuyển sang **Pod khác**, giữ Pod bị lỗi không đủ điều kiện bằng cơ chế fault đã xác minh trong suốt cửa sổ, rồi đối chiếu Pod UID của bên tiếp quản.

Không đòi hỏi revoke từ tiến trình đã chết. Bằng chứng cần là tiến trình cũ đã dừng và một phiên hợp lệ tiếp tục công việc.

Không dùng `kubectl delete --force --grace-period=0` để khẳng định tiến trình đã bị kill. Xóa cưỡng bức có thể loại đối tượng khỏi API trước khi xác nhận tiến trình trên node đã kết thúc. [Nguồn: kubectl delete](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_delete/).

### 8.3. Dừng một follower

Xác nhận một Pod không phải leader ngay trước lúc xóa nó. Kỳ vọng công việc của leader tiếp tục, không có tác dụng phụ trùng và nhóm trở lại số replica mong muốn.

Nếu leadership đổi bất ngờ, giữ bằng chứng để phân biệt lỗi ổn định, readiness thay đổi và race trong chọn mục tiêu: một follower được chọn có thể đã trở thành leader trước khi lệnh xóa có hiệu lực.

Kịch bản này kiểm tra ảnh hưởng của thay đổi thành viên; nó không tự chứng minh failover của leader.

### 8.4. Rolling restart hoặc nâng image

```powershell
kubectl -n $labNamespace rollout restart deployment/leader-lab
kubectl -n $labNamespace rollout status deployment/leader-lab --timeout=180s
```

Quan sát cả quá trình. Với `maxSurge: 1`, có thể xuất hiện ứng viên ngoài ba replica mong muốn; Pod đang terminating cũng có thể còn chạy trong grace period. Bộ thu cần theo tập Pod động. [Nguồn: Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/).

Kỳ vọng: không rơi mất checkpoint, không để scheduler cũ chạy mãi sau thu hồi và kết quả job đúng chính sách. Khi nâng image, kiểm tra cả khả năng hai phiên bản cùng tồn tại và tương thích payload/schema.

### 8.5. Scale và khởi động cạnh tranh

```powershell
kubectl -n $labNamespace scale deployment/leader-lab --replicas=5
kubectl -n $labNamespace rollout status deployment/leader-lab --timeout=180s
```

Giảm về ba replica rồi quan sát tiếp. Scale-down không cam kết loại đúng leader; ghi Pod thực tế bị kết thúc.

Khởi động đồng thời từ không có ứng viên là một kịch bản riêng: tạo trước workload tại sink, khởi động nhóm và kiểm tra chỉ một phiên điều phối sau hội tụ.

Nếu ứng dụng tự tạo ConfigMap, cần kiểm tra cạnh tranh tạo tài nguyên. Manifest của bài dùng ConfigMap đã tạo sẵn nên không bao phủ đường đó.

### 8.6. Chặn API server nhưng vẫn giữ đường tới sink

Fault cần đáp ứng:

- Chỉ Pod mục tiêu mất đường tới Kubernetes API.
- Pod đó vẫn tới được sink, DB và DNS cần thiết.
- Follower và bộ quan sát vẫn tới được API.
- Có thể tháo fault và xác nhận khôi phục.

NetworkPolicy cần CNI thực thi. Các policy cộng gộp quyền cho phép; policy mới không phủ nhận policy khác đang cho egress. Cách xử lý Service IP và kết nối đã thiết lập cần được kiểm chứng trong cluster thực tế. [Nguồn: Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/).

Không chặn toàn bộ egress rồi kết luận stale writer đã bị bảo vệ: có thể sink cũng bị chặn. Trước khi đo, chứng minh client thực sự mất đường API/watch, trong khi request kiểm tra tới sink vẫn thành công.

Với Fabric8/ConfigMap trong bài, control plane có thể tiếp tục thấy leader cũ Ready. Khi đó follower có thể tiếp tục giữ leader cũ thay vì chuyển giao theo một lease timeout. Cần:

1. Đo xem ứng dụng có dừng phát việc khi không còn xác nhận được quyền không.
2. Ghi kết quả đối với yêu cầu liveness thực tế, không tự tuyên bố chắc chắn có leader mới.
3. Nếu cần kiểm tra đường NotReady, tạo fault readiness riêng và xác nhận Ready đổi.
4. Khi tháo partition, kiểm tra scheduler không nhân đôi và task cũ không mượn phiên mới.

Nếu nghiệp vụ yêu cầu failover trong dạng partition này mà implementation không đáp ứng, đó là giới hạn thiết kế cần được báo rõ; không sửa kết luận bằng cách đổi fault sau khi thấy test thất bại.

### 8.7. Tạm dừng lâu và request đến muộn

Giữ một task ở điểm chặn ngay trước khi gửi tác dụng phụ. Cho hệ thống chuyển sang phiên mới bằng fault đã xác định, rồi thả task cũ.

Dùng latch, proxy trì hoãn hoặc công cụ pause của lab. Không sleep lâu trong listener election vì có thể chặn chính đường xử lý sự kiện cần kiểm tra.

Kỳ vọng: sau điểm cắt fencing tại sink, lệnh phiên cũ bị từ chối. Retry từ phiên mới giữ khóa nghiệp vụ của cùng ý định.

Nếu hợp đồng cho phép ý định đã commit trước handover tiếp tục được dispatcher gửi, kiểm tra theo hợp đồng đó; không tự coi mọi công việc xuất phát từ phiên cũ đều phải bị hủy.

## 9. Bộ kiểm chứng công việc và tác dụng phụ

### 9.1. Nguồn dữ liệu mong đợi và thực tế

Một schema quan sát tối giản:

```sql
CREATE TABLE lab_expected_job (
    run_id  text NOT NULL,
    job_key text NOT NULL,
    PRIMARY KEY (run_id, job_key)
);

CREATE TABLE lab_effect_journal (
    effect_sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id           text NOT NULL,
    job_key          text NOT NULL,
    pod_uid          text NOT NULL,
    boot_id          text NOT NULL,
    local_generation bigint NOT NULL,
    authority_epoch  bigint,
    recorded_at      timestamptz NOT NULL DEFAULT clock_timestamp()
);
```

Nạp trước danh sách job mong đợi. Sink ghi journal khi một hiệu ứng **thực sự được chấp nhận**, không phải ngay lúc request bắt đầu.

Journal cố ý không có unique constraint trên `(run_id, job_key)`, để không tự che lỗi mà phép thử muốn phát hiện. Dữ liệu nghiệp vụ vẫn có thể cần unique key hoặc inbox để bảo đảm idempotency; journal phải phản ánh hiệu ứng sau lớp bảo vệ đó.

Nếu hiệu ứng là ghi DB, ghi journal cùng giao dịch nghiệp vụ. Nếu hiệu ứng ở nhà cung cấp ngoài, đối chiếu mã giao dịch/biên nhận tại nhà cung cấp; journal nội bộ không tự chứng minh được hiệu ứng ngoài hệ thống.

Kiểm tra trùng:

```sql
SELECT job_key, count(*) AS effect_count
FROM lab_effect_journal
WHERE run_id = 'handover-001'
GROUP BY job_key
HAVING count(*) > 1;
```

Kiểm tra job còn thiếu sau thời hạn hoàn tất:

```sql
SELECT e.job_key
FROM lab_expected_job e
LEFT JOIN lab_effect_journal j
    ON j.run_id = e.run_id AND j.job_key = e.job_key
WHERE e.run_id = 'handover-001'
  AND j.effect_sequence IS NULL;
```

Kiểm tra công việc ngoài danh sách dự kiến:

```sql
SELECT j.job_key
FROM lab_effect_journal j
LEFT JOIN lab_expected_job e
    ON e.run_id = j.run_id AND e.job_key = j.job_key
WHERE j.run_id = 'handover-001'
  AND e.job_key IS NULL;
```

Các truy vấn giả định một job hợp lệ tạo đúng một hiệu ứng. Nếu một job có nhiều hiệu ứng, dùng `effect_key` hoặc số lượng mong đợi tương ứng.

### 9.2. Phân biệt idempotency và không có chạy đồng thời

Hai Pod cùng thử một job nhưng unique key chặn một bên có thể vẫn tạo đúng một kết quả. Nếu yêu cầu là kết quả lũy đẳng, đó có thể là PASS. Nếu yêu cầu là không chạy hai tác vụ tốn kém cùng lúc, cần thêm attempt journal, khoảng chạy task và số scheduler hoạt động.

Thu cả attempt bị chặn và effect được chấp nhận. Khi giao dịch nghiệp vụ rollback, bằng chứng về lần từ chối cần được ghi theo cách không mất theo cùng rollback.

### 9.3. Kiểm tra fencing theo điểm cắt có thẩm quyền

Sau khi authority kích hoạt và xác nhận commit epoch mới, gửi request mang epoch cũ cho một **job mới**. Nó phải bị từ chối dù khóa idempotency chưa tồn tại.

Không lấy thứ tự cấp số identity trong journal làm bằng chứng tổng quát cho thứ tự commit. Một số có thể được cấp trước khi giao dịch hoàn tất. Hãy dùng phép thử request cũ gửi sau activation đã commit hoặc bằng chứng từ giao thức serialize tại sink.

Hai event GRANTED gần nhau không đủ để kết luận lỗi dữ liệu. Một hàng kết quả duy nhất cũng không đủ để kết luận không có stale writer.

## 10. Giảm kiểm thử chập chờn và phân loại lỗi

| Hiện tượng | Hướng điều tra |
| --- | --- |
| Không có leader từ đầu | Namespace, role, candidate ID, readiness, RBAC, ConfigMap |
| Bản ghi election đổi nhưng không có job | Listener, scheduler, phiên quyền ghi, sink và checkpoint |
| Leadership đổi liên tục | Probe flapping, CPU throttling, timeout và reconnect |
| Hai JVM tự báo leader | Độ trễ sự kiện, partition, boot/generation; đối chiếu quyền ghi tại sink |
| Không thấy revoke khi crash | Tiến trình đã chết và độ đầy đủ của log |
| Chỉ tiếp tục khi Pod cũ quay lại | Thiếu ứng viên đủ điều kiện hoặc giới hạn election |
| Test treo dù có timeout chung | Request con, thao tác fault hoặc cleanup chưa có timeout |
| Thiếu instrumentation nhưng vẫn PASS | Bộ kiểm chứng đang coi thiếu dữ liệu là không có lỗi |

Test tốt bắt đầu khi nền ổn định, tạo một fault có xác nhận và kết thúc theo điều kiện có giới hạn. Không thêm sleep dài để che giả định sai về election.

Không retry toàn bộ test rồi chỉ báo lần cuối thành công. Giữ kết quả từng lần, vì tác dụng phụ trùng đã xảy ra không biến mất sau khi chạy lại.

Chạy nhiều vòng dưới tải đại diện để đánh giá phân bố recovery time. Muốn báo p95/p99 cần số mẫu phù hợp và cùng cách đo; vài lần thủ công không đủ để suy ra tail latency.

Trong lab với hiệu ứng mô phỏng, dùng negative control: cố ý để mọi Pod cùng nhận job hoặc bỏ một lớp chống trùng. Bộ kiểm chứng phải phát hiện sai lệch. Nếu vẫn PASS, oracle chưa đáng tin.

## 11. Tự động hóa và dọn môi trường

Phân lớp kiểm thử:

- Unit test kiểm tra chuyển trạng thái scheduler, snapshot phiên và callback lặp; không chứng minh election thật.
- Integration test trong cluster kiểm tra RBAC, watch, nhiều replica và Pod lifecycle.
- Fault test mạng, pause và node failure cần môi trường có công cụ phù hợp; cluster một node không chứng minh khả năng tiếp tục khi node đó mất.

Trong CI song song, cấp namespace hoặc tài nguyên election riêng cho mỗi run. Không để hai chiến dịch dùng cùng lock và role trong cùng namespace. Bên trong một run, các Pod cần giữ cùng định danh election để thực sự cạnh tranh.

Cleanup cần chạy cả sau thành công, lỗi hoặc timeout:

1. Tháo network fault, pause, proxy delay và readiness override.
2. Dừng port-forward và bộ thu thuộc run.
3. Lưu bằng chứng trước khi xóa tài nguyên.
4. Khôi phục replica hoặc xóa đúng namespace lab đã tạo.
5. Không thả worker bị pause về môi trường có quyền ghi thật.

Baseline tắt tải ConfigMap/Secret và reload để dễ quy nguyên nhân. Sau khi kiểm thử election ổn định, thêm kịch bản Configuration Watcher cập nhật cấu hình lúc handover nếu ứng dụng thực sự dùng tính năng đó. Không reset khóa job hoặc trạng thái tiến độ bền vững khi refresh.

Health cần tách khỏi leadership. Readiness thất bại làm Pod không sẵn sàng nhận traffic theo probe; liveness thất bại có thể khiến kubelet restart container. Không dùng liveness để trừng phạt follower bình thường. [Nguồn: Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

Chỉ bật DiscoveryClient, Spring Cloud LoadBalancer và Configuration Watcher khi có hành vi cụ thể cần đánh giá. Ví dụ, nếu kiểm thử retry downstream khi Endpoint đổi cùng lúc leadership chuyển giao, cần tách kết quả lỗi định tuyến khỏi lỗi election.

## 12. Báo cáo một lần kiểm thử

Báo cáo cần đủ bằng chứng để tái lập và hiểu giới hạn kết luận:

```text
run_id:
implementation và dependency version:
cluster / CNI / image digest:
namespace / role / election resource:
replica và probe:
fault loại gì, đặt ở Pod UID / boot ID nào:
thời điểm gửi fault và xác nhận có hiệu lực:
leader / phiên trước và sau:
thời gian tới grant / scheduler start / first valid commit:
cửa sổ ổn định:
job dự kiến / hoàn tất / thiếu / trùng / ngoài dự kiến:
stale request bị từ chối hoặc được chấp nhận:
lỗi quan sát và dữ liệu bị thiếu:
kết quả PASS / FAIL / INCONCLUSIVE:
cleanup:
```

Ví dụ diễn giải có bằng chứng: “Sau halt JVM của A, B có commit hợp lệ đầu tiên sau 8,4 giây; 100 job hoàn tất, không có hiệu ứng trùng; request dùng epoch cũ gửi sau activation bị từ chối; hệ thống ổn định thêm 10 giây.”

Kết luận “đã xóa leader và thấy Pod khác báo leader nên failover thành công” còn thiếu tiến triển nghiệp vụ, bảo vệ tác dụng phụ và độ đầy đủ của quan sát.

Chuyển giao vai trò hoàn tất về mặt nghiệp vụ khi một phiên hợp lệ tiếp tục công việc, kết quả cũ được xử lý đúng hợp đồng và các tác dụng phụ quan trọng vẫn được bảo vệ.
