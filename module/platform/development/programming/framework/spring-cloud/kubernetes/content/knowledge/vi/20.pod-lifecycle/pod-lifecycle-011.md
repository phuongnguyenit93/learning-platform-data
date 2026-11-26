# Kiểm chứng hành vi ứng dụng trong suốt vòng đời triển khai

## 1. Kiểm chứng ứng dụng, không chỉ kiểm tra Pod đang chạy

Trong module **SPRING_CLOUD_KUBERNETES**, chúng ta tích hợp ứng dụng Spring với discovery, cấu hình Kubernetes, load balancing và theo dõi sức khỏe. Các tính năng đó chỉ có giá trị khi ứng dụng hoạt động đúng trong cả quá trình khởi động, nhận traffic, cập nhật và kết thúc.

Một Deployment báo thành công chưa chứng minh request không bị mất. Một Pod ở phase `Running` chưa chứng minh ứng dụng đã nạp cấu hình hoặc sẵn sàng xử lý nghiệp vụ. Ngược lại, một container restart chưa chắc tạo Pod mới.

Bài học xây dựng cách kiểm chứng xuyên suốt vòng đời triển khai bằng ba nguồn bằng chứng:

- **Kubernetes:** trạng thái Pod/container, probe, EndpointSlice, Deployment và sự kiện.
- **Ứng dụng Spring:** availability, request đang xử lý, phiên JVM và trạng thái công việc nền.
- **Người gọi và nghiệp vụ:** response, timeout, độ trễ, kết quả ghi bền vững và retry.

Mục tiêu không phải chứng minh “không có bất kỳ lỗi nào trong mọi điều kiện”, mà là xác định hợp đồng cụ thể, chủ động tạo tình huống và đối chiếu kết quả với hợp đồng đó.

## 2. Xác định bất biến trước khi triển khai

Với một dịch vụ xử lý đơn hàng chạy ba replica, có thể đặt các bất biến sau:

| Giai đoạn | Hành vi phải kiểm chứng |
| --- | --- |
| Khởi tạo | Không nhận traffic Service trước khi hoàn tất công việc khởi động bắt buộc |
| Sẵn sàng | Request tới đúng phiên bản, đúng cấu hình và hoàn tất trong SLO |
| Tạm thời không sẵn sàng | Pod rời tập đích phù hợp, không bị restart chỉ vì readiness lỗi |
| Rolling update | Replica đủ năng lực phục vụ; hai phiên bản cùng tồn tại an toàn |
| Drain và shutdown | Request đã nhận được hoàn tất hoặc thất bại theo hợp đồng; công việc mới ngừng đúng lúc |
| Crash hoặc cưỡng bức | Trạng thái bền vững phục hồi được, retry không nhân đôi tác dụng phụ |
| Rollback | Phiên bản cũ vẫn tương thích dữ liệu và cấu hình hiện tại |

Ví dụ SLO của **lab**:

- Ứng dụng sẵn sàng trong 90 giây với điều kiện tài nguyên đã xác định.
- Trong rollout có tải đại diện, tỷ lệ lỗi không vượt ngân sách đã thỏa thuận.
- Request lab dài 10 giây đã được nhận trước shutdown được hoàn tất trong ngân sách drain.
- Không có đơn hàng được tạo hai lần bởi cùng khóa nghiệp vụ.
- Không còn công việc đã nhận nhưng không thể truy vết là hoàn tất, hủy hoặc chờ retry.

Các con số này thuộc phép thử, không phải bảo đảm mặc định của Spring Cloud Kubernetes. Với WebSocket, streaming, batch dài hoặc giao dịch bên ngoài, phải định nghĩa hợp đồng riêng.

## 3. Các trạng thái cần phân biệt

### 3.1. Pod, container và JVM có vòng đời khác nhau

| Tín hiệu | Ý nghĩa | Không tự chứng minh |
| --- | --- | --- |
| Pod phase `Pending` | Pod chưa hoàn thành các bước cần để chạy container | JVM đang khởi động |
| Pod phase `Running` | Pod đã được gán node và container đã được tạo; có container đang chạy/khởi động lại | Ứng dụng Ready |
| Container `Waiting` | Đang chờ vì một nguyên nhân như pull image hoặc backoff | Cùng nguyên nhân với mọi Pod khác |
| Container `Terminated` | Một lần chạy container đã kết thúc | Pod chắc chắn đã bị xóa |
| Pod condition `Ready=True` | Các điều kiện readiness của Pod được đáp ứng | Mọi nghiệp vụ đều đúng hoặc đủ năng lực chịu tải |
| `deletionTimestamp` | Pod đã được yêu cầu xóa | Tiến trình đã dừng ngay lập tức |

`Terminating` và `CrashLoopBackOff` thường xuất hiện trong cột STATUS của công cụ, nhưng không phải các giá trị Pod phase mới. [Nguồn: Kubernetes — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/).

Dùng **Pod UID** để nhận diện Pod. Dùng thêm **boot ID** do ứng dụng tạo khi JVM khởi động để nhận diện phiên tiến trình. Container restart có thể giữ Pod UID nhưng đổi boot ID và tăng `restartCount`.

### 3.2. Ba probe trả lời ba câu hỏi

| Probe | Câu hỏi | Phản ứng khi lỗi đủ ngưỡng |
| --- | --- | --- |
| Startup | Tiến trình đã vượt qua điều kiện khởi động được kiểm tra chưa? | Container có thể bị kết thúc và restart theo chính sách |
| Readiness | Bản sao này có nên nhận traffic bình thường không? | Pod không Ready; không tự restart chỉ vì probe này |
| Liveness | Tiến trình có ở trạng thái cần restart để phục hồi không? | Container có thể bị kết thúc và restart |

Khi có startup probe, kubelet chưa chạy readiness và liveness probe cho container đó cho tới khi startup probe thành công. [Nguồn: Kubernetes — Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/).

Probe không tự bảo vệ mọi đường vào. Client gọi trực tiếp Pod IP hoặc giữ kết nối cũ có thể không tuân theo cùng quyết định định tuyến như một kết nối Service mới.

### 3.3. Availability của Spring và readiness của Pod

Ví dụ trong bài sử dụng các API/cấu hình được mô tả ở nhánh Spring Boot 3.5. Khi ghép với Spring Cloud Kubernetes, chọn release train tương thích; không suy ra tương thích chỉ vì hai dependency cùng có số major gần nhau.

Spring Boot phân biệt `LivenessState` và `ReadinessState`. Health group tương ứng có thể được đưa lên cổng ứng dụng qua `/livez`, `/readyz`. Điều này tránh chỉ kiểm tra một management server riêng vẫn khỏe trong khi cổng nghiệp vụ có vấn đề. [Nguồn: Spring Boot 3.5 — Kubernetes Probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html).

Không đưa lỗi DB hoặc dịch vụ ngoài vào liveness một cách máy móc: khi dependency chung lỗi, restart mọi replica có thể làm sự cố nặng hơn. Việc đưa dependency vào readiness cần dựa trên khả năng ứng dụng tiếp tục phục vụ, fallback và tác động khi tất cả Pod cùng bị loại.

## 4. Chuẩn bị ứng dụng có khả năng quan sát

### 4.1. Định danh và sự kiện cần thu

Mỗi response lab và log cần gắn tối thiểu:

```text
run_id, pod_name, pod_uid, boot_id
release, config_version, request_id
event_type, thời gian, thời lượng
```

Các mốc quan trọng gồm container start, context sẵn sàng, availability thay đổi, request được nhận, request hoàn tất, context đóng và trạng thái kết thúc container.

Không in Secret hoặc toàn bộ cấu hình vào log. Chỉ xuất phiên bản cấu hình không nhạy cảm, mã tham chiếu hoặc checksum của tập dữ liệu được phép công khai.

### 4.2. Controller và listener dành cho lab

Ví dụ Java 17 trở lên, ứng dụng servlet dùng Spring Web và Actuator. Đặt lớp trong package được Spring Boot quét và bật profile `lifecycle-lab`.

```java
@RestController
@Profile("lifecycle-lab")
public class LifecycleLabController {
    private static final Logger log =
            LoggerFactory.getLogger(LifecycleLabController.class);

    private final ApplicationContext context;
    private final ApplicationAvailability availability;
    private final String bootId = UUID.randomUUID().toString();
    private final String podUid;
    private final String release;
    private final String configVersion;

    public LifecycleLabController(
            ApplicationContext context,
            ApplicationAvailability availability,
            @Value("${POD_UID:local}") String podUid,
            @Value("${LAB_RELEASE:dev}") String release,
            @Value("${LAB_CONFIG_VERSION:unknown}") String configVersion) {
        this.context = context;
        this.availability = availability;
        this.podUid = podUid;
        this.release = release;
        this.configVersion = configVersion;
    }

    @GetMapping("/lab/work")
    public Map<String, Object> work(
            @RequestParam(defaultValue = "0") long delayMs,
            @RequestHeader(name = "X-Request-Id", required = false)
            String suppliedId) throws InterruptedException {
        if (delayMs < 0 || delayMs > 30000) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }
        String requestId = suppliedId == null
                ? UUID.randomUUID().toString() : suppliedId;
        long started = System.nanoTime();
        log.info("event=WORK_ACCEPTED requestId={} podUid={} bootId={}",
                requestId, podUid, bootId);
        Thread.sleep(delayMs);
        long elapsedMs = (System.nanoTime() - started) / 1_000_000;
        log.info("event=WORK_COMPLETED requestId={} elapsedMs={} bootId={}",
                requestId, elapsedMs, bootId);
        return Map.of(
                "requestId", requestId,
                "podUid", podUid,
                "bootId", bootId,
                "release", release,
                "configVersion", configVersion,
                "readiness", availability.getReadinessState().name(),
                "elapsedMs", elapsedMs);
    }

    @PostMapping("/lab/readiness/{accepting}")
    public void readiness(@PathVariable boolean accepting) {
        AvailabilityChangeEvent.publish(
                context,
                accepting ? ReadinessState.ACCEPTING_TRAFFIC
                          : ReadinessState.REFUSING_TRAFFIC);
    }

    @EventListener
    public void availabilityChanged(AvailabilityChangeEvent<?> event) {
        log.info("event=AVAILABILITY state={} bootId={}",
                event.getState(), bootId);
    }

    @EventListener
    public void closing(ContextClosedEvent event) {
        log.info("event=CONTEXT_CLOSING bootId={}", bootId);
    }
}
```

Các import chính gồm Spring Web, `org.springframework.boot.availability.*`, `ApplicationContext`, `ContextClosedEvent`, `EventListener`, `Profile`, `Value`, SLF4J, `Map` và `UUID`. Với tham số path/query, dùng cấu hình biên dịch giữ tên tham số hoặc khai báo tên tường minh trong annotation.

`Thread.sleep` ở đây chỉ tạo request chậm có giới hạn để kiểm thử servlet drain, không phải mẫu xử lý nghiệp vụ production. Endpoint readiness chỉ thay availability; nó không tự chặn request gọi trực tiếp tới `/lab/work`.

`WORK_COMPLETED` phản ánh handler sắp trả response, chưa chứng minh client đã nhận đủ response. Bộ kiểm thử phải thu kết quả ở phía client.

Các endpoint thay đổi trạng thái chỉ dành cho lab được kiểm soát. Nếu có Spring Security, cấu hình quyền cho endpoint lab và truy cập probe rõ ràng.

### 4.3. Tạo khoảng warmup có thể đo

Có thể thêm bean sau vào cấu hình lab để trì hoãn hoàn tất startup:

```java
@Bean
@Profile("lifecycle-lab")
ApplicationRunner warmup(
        @Value("${LAB_STARTUP_DELAY_MS:0}") long delayMs) {
    return args -> {
        if (delayMs < 0 || delayMs > 60000) {
            throw new IllegalArgumentException("Invalid warmup delay");
        }
        Thread.sleep(delayMs);
    };
}
```

Spring Boot chỉ phát trạng thái sẵn sàng sau các startup runner. `ApplicationReadyEvent` diễn ra sau runner, và sự kiện chuyển sang nhận traffic theo sau đó; không dùng một dòng log “Started” làm mốc duy nhất. [Nguồn: Spring Boot 3.5 — SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html).

Nếu startup probe dùng liveness, nó có thể thành công trước khi warmup xong. Đây là điều cần phân biệt: startup probe đã pass không đồng nghĩa readiness đã pass.

## 5. Cấu hình triển khai nền

### 5.1. Cấu hình Spring

Ví dụ `application.yml`:

```yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
        add-additional-paths: true
```

`timeout-per-shutdown-phase` áp dụng cho từng phase shutdown, không phải giới hạn tổng duy nhất cho toàn JVM. Web server dừng nhận request mới theo cơ chế cụ thể của nó; kết nối persistent cũng ảnh hưởng hành vi quan sát. [Nguồn: Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html).

Baseline chỉ cần Spring Boot Web/Actuator. Probe Kubernetes không đòi hỏi ứng dụng cài Spring Cloud Kubernetes. Khi ghép vào dịch vụ thật, bật discovery, đọc cấu hình hoặc watcher theo nhu cầu và kiểm chứng bổ sung ở mục 9.

### 5.2. Manifest lab

Thay image bằng image lab đã build, có controller/runner trên và chạy JVM bằng entrypoint nhận được tín hiệu kết thúc. Ví dụ manifest không truy cập Kubernetes API từ trong ứng dụng, nên không cần mount ServiceAccount token.

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: lifecycle-lab
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: lifecycle-lab-settings
  namespace: lifecycle-lab
data:
  configVersion: cfg-v1
  warmupDelayMs: "0"
  application.yml: |
    server:
      port: 8080
      shutdown: graceful
    spring:
      lifecycle:
        timeout-per-shutdown-phase: 20s
    management:
      endpoints:
        web:
          exposure:
            include: health,info
      endpoint:
        health:
          show-details: never
          probes:
            enabled: true
            add-additional-paths: true
---
apiVersion: v1
kind: Service
metadata:
  name: lifecycle-lab
  namespace: lifecycle-lab
spec:
  selector:
    app: lifecycle-lab
  ports:
    - name: http
      port: 8080
      targetPort: http
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: lifecycle-lab
  namespace: lifecycle-lab
spec:
  replicas: 3
  minReadySeconds: 10
  progressDeadlineSeconds: 180
  revisionHistoryLimit: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: lifecycle-lab
  template:
    metadata:
      labels:
        app: lifecycle-lab
    spec:
      automountServiceAccountToken: false
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: registry.example.com/training/lifecycle-lab:v1
          args:
            - --spring.config.additional-location=file:/etc/lifecycle/
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: lifecycle-lab
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
            - name: LAB_RELEASE
              value: v1
            - name: LAB_CONFIG_VERSION
              valueFrom:
                configMapKeyRef:
                  name: lifecycle-lab-settings
                  key: configVersion
            - name: LAB_STARTUP_DELAY_MS
              valueFrom:
                configMapKeyRef:
                  name: lifecycle-lab-settings
                  key: warmupDelayMs
          volumeMounts:
            - name: settings
              mountPath: /etc/lifecycle
              readOnly: true
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 60
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 5
            timeoutSeconds: 1
            failureThreshold: 3
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 1Gi
      volumes:
        - name: settings
          configMap:
            name: lifecycle-lab-settings
```

Image phải có entrypoint tương thích với `args` ở trên. Dùng exec form cho `java` hoặc cơ chế chuyển tiếp signal đúng; một shell không chuyển signal có thể làm shutdown thực tế khác bài kiểm thử.

Các giá trị CPU/memory là điểm bắt đầu của lab, cần điều chỉnh theo ứng dụng và tải. Cluster phải có tài nguyên/quota cho replica surge, nếu không rollout có thể đứng vì scheduling thay vì lỗi readiness.

Thời gian danh nghĩa của startup probe khoảng `60 × 2 = 120` giây, chưa bao gồm mọi độ trễ hệ thống. Không coi phép nhân này là SLA chính xác.

`minReadySeconds` yêu cầu Pod Ready liên tục trước khi được tính là available cho Deployment. Nó không trì hoãn việc Service bắt đầu dùng endpoint Ready. `progressDeadlineSeconds` phát hiện rollout không tiến triển; không tự bảo đảm rollback hay request thành công. [Nguồn: Kubernetes Deployment API](https://kubernetes.io/docs/reference/kubernetes-api/apps/deployment-v1/).

## 6. Thu bằng chứng trước khi tạo thay đổi

### 6.1. Khởi chạy baseline

Các lệnh quản trị sau dùng PowerShell:

```powershell
$labNamespace = 'lifecycle-lab'
$labSelector = 'app=lifecycle-lab'

kubectl config current-context
kubectl apply -f .\lifecycle-lab.yml
kubectl -n $labNamespace rollout status deployment/lifecycle-lab --timeout=240s
kubectl -n $labNamespace get pods -l $labSelector -o wide
kubectl -n $labNamespace get deployment lifecycle-lab -o yaml
kubectl -n $labNamespace get endpointslices -l kubernetes.io/service-name=lifecycle-lab -o yaml
```

Kiểm tra exit code các lệnh trong script tự động. Không coi một chuỗi JSON rỗng do lệnh thất bại là tập Pod không có lỗi.

Trong các terminal khác, theo dõi thay đổi:

```powershell
kubectl -n $labNamespace get pods -l $labSelector -w
```

```powershell
kubectl -n $labNamespace get endpointslices -l kubernetes.io/service-name=lifecycle-lab -w -o yaml
```

```powershell
kubectl -n $labNamespace logs -l $labSelector --prefix=true --timestamps=true --max-log-requests=10 --tail=-1 -f
```

Log theo selector đang follow không nên được coi là bộ thu tự động mọi Pod tạo về sau. Theo lại tập Pod động hoặc dùng log tập trung. Gắn metadata Pod UID và run ID tại bộ thu nếu log ứng dụng chưa chứa đầy đủ.

### 6.2. Phân biệt đường smoke và đường traffic thật

Port-forward tới một Pod hữu ích để xem health hoặc đổi readiness:

```powershell
$podListJson = kubectl -n $labNamespace get pods -l $labSelector -o json
if ($LASTEXITCODE -ne 0) { throw 'Không đọc được tập Pod' }
$podList = $podListJson | ConvertFrom-Json
$labPod = $podList.items |
    Where-Object {
        -not $_.metadata.deletionTimestamp -and
        ($_.status.conditions | Where-Object {
            $_.type -eq 'Ready' -and $_.status -eq 'True'
        })
    } |
    Select-Object -First 1
if ($null -eq $labPod) { throw 'Không có Pod Ready' }
$targetPod = $labPod.metadata.name
$targetUid = $labPod.metadata.uid
kubectl -n $labNamespace port-forward pod/$targetPod 18081:8080
```

Ở terminal khác:

```powershell
Invoke-RestMethod http://127.0.0.1:18081/livez
Invoke-RestMethod http://127.0.0.1:18081/readyz
Invoke-RestMethod http://127.0.0.1:18081/lab/work
```

Port-forward tới Service vẫn chọn một backend để tạo tunnel; nó không thay thế việc kiểm tra phân phối traffic qua Service. Đối với rollout và drain, tạo traffic từ một client trong cluster qua DNS Service hoặc qua đúng ingress/gateway mà hệ thống thật sử dụng.

Ví dụ vòng lấy mẫu tải nhẹ, chạy trong một môi trường client có Bash, curl và các tiện ích được dùng bên dưới:

```bash
for i in $(seq 1 300); do
  rid="lifecycle-$i"
  curl --silent --show-error --connect-timeout 1 --max-time 5 \
    -H "X-Request-Id: $rid" \
    --write-out '\nhttp=%{http_code} duration=%{time_total}\n' \
    http://lifecycle-lab.lifecycle-lab.svc:8080/lab/work
  curl_exit=$?
  printf '\nclient_exit=%s\n' "$curl_exit"
  sleep 0.2
done
```

Đây là phép quan sát tuần tự, không phải benchmark đủ tải. Mỗi tiến trình curl tạo kết nối mới; cần bổ sung client giữ kết nối nếu ứng dụng dùng connection pool, HTTP/2 hoặc streaming. Đổi prefix request ID theo run để tránh trộn dữ liệu.

Thu đủ status, lỗi kết nối, timeout, response body, Pod UID, boot ID và release. HTTP 200 từ sai phiên bản hoặc cấu hình sai vẫn có thể là FAIL.

## 7. Kiểm chứng từng giai đoạn triển khai

### 7.1. Khởi động chậm nhưng hợp lệ

Trong bản cấu hình của một run riêng, đặt `warmupDelayMs: "20000"`, sau đó tạo lại các Pod bằng rollout có kiểm soát. Chỉ sửa ConfigMap không tự thay biến môi trường của container đang chạy.

Quan sát:

1. JVM và web server có thể tồn tại trước khi startup runner kết thúc.
2. `/livez` có thể thành công trong khi `/readyz` chưa thành công.
3. Pod mới chưa được dùng như endpoint Ready cho traffic thông thường.
4. Sau warmup, availability và Pod Ready đổi, rồi client bắt đầu thấy boot ID mới.
5. Không có restart do liveness trong thời gian startup hợp lệ.

Đừng chỉ chờ “ba Pod Running”. Đo thời gian tới request nghiệp vụ đầu tiên thành công qua đường định tuyến cần kiểm tra.

Nếu ứng dụng có warmup bất đồng bộ sau startup runner, readiness mặc định có thể chưa phản ánh điều kiện nghiệp vụ đó. Cần thêm health indicator hoặc điều phối availability phù hợp và kiểm thử chính điều kiện ấy.

### 7.2. Startup sai cấu hình

Tạo run dùng một cấu hình không hợp lệ hoặc image lab cố ý thất bại khi khởi tạo.

Kỳ vọng:

- Pod không trở thành endpoint sẵn sàng phục vụ nghiệp vụ.
- Rollout không âm thầm coi phiên bản đó là available.
- Lỗi được phân loại rõ: image pull, mount cấu hình, binding/validation, kết nối bắt buộc hoặc readiness.
- Với `maxUnavailable: 0`, các replica cũ còn khỏe được giữ theo chiến lược rollout; vẫn phải đo năng lực thực tế và điều kiện tài nguyên.

Không chỉnh probe để ứng dụng lỗi được báo Ready. Nếu deadline hết, giữ log và trạng thái trước khi rollback.

### 7.3. Readiness mất và phục hồi

Sau baseline, dùng port-forward tới đúng Pod đã chọn:

```powershell
Invoke-WebRequest -Method Post -Uri http://127.0.0.1:18081/lab/readiness/false
```

Xác minh đồng thời:

- `/readyz` chuyển sang không sẵn sàng.
- Liveness vẫn tốt.
- Pod Ready đổi sau chu kỳ/ngưỡng probe.
- EndpointSlice phản ánh trạng thái phù hợp.
- Sau thời gian hội tụ định tuyến đã đo, kết nối mới từ client thông thường không tiếp tục được đưa tới Pod đó.
- Pod UID, boot ID và restart count không đổi chỉ vì readiness lỗi.

Khôi phục:

```powershell
Invoke-WebRequest -Method Post -Uri http://127.0.0.1:18081/lab/readiness/true
```

Chờ readiness, endpoint và traffic phục hồi bằng polling có deadline. Không bắt buộc Pod quay lại ngay sau đúng một phép nhân `periodSeconds × failureThreshold`, vì còn thời gian request, lập lịch và lan truyền.

Request trực tiếp qua port-forward có thể vẫn tới `/lab/work` khi readiness false. Đó là đường đi bỏ qua quyết định chọn endpoint của Service, không tự chứng minh readiness thất bại.

### 7.4. Rolling update với traffic liên tục

Chuẩn bị manifest v2, đổi image sang phiên bản bất biến và `LAB_RELEASE` sang `v2` trong cùng lần cập nhật Pod template.

```powershell
kubectl -n $labNamespace rollout history deployment/lifecycle-lab
kubectl apply -f .\lifecycle-lab-v2.yml
kubectl -n $labNamespace rollout status deployment/lifecycle-lab --timeout=240s
```

Chạy client trước, trong và sau rollout. Kiểm tra:

- Response có thể đến từ v1 lẫn v2 trong giai đoạn hai phiên bản cùng tồn tại.
- Không thấy v2 nhận traffic trước khi điều kiện readiness thực sự thỏa.
- Không có khoảng thiếu năng lực vượt SLO dù số replica nhìn có vẻ đủ.
- Request đang xử lý ở v1 được drain theo hợp đồng.
- Sau hội tụ và hết cửa sổ quan sát đã xác định, kết nối mới tới release mong đợi.
- Không có task nền cũ sống vô hạn hoặc chạy trùng sau thay đổi phiên bản.

`maxSurge` và các Pod terminating làm số tiến trình quan sát được có thể lớn hơn số replica mong muốn. Không hard-code bộ thu chỉ theo ba tên Pod ban đầu. [Nguồn: Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/).

Tải cần bao gồm loại request chậm, tải CPU và truy cập DB đại diện. Một vòng curl tuần tự chỉ kiểm tra được một phần hành vi.

## 8. Kiểm chứng drain và kết thúc

### 8.1. Mô hình thời gian thực tế

Luồng cần quan sát không phải một chuỗi đồng bộ tuyệt đối:

```text
Yêu cầu xóa Pod
    |-- kubelet bắt đầu tiến trình kết thúc, chạy preStop nếu có
    |-- control plane cập nhật endpoint cho Pod terminating
    |
    +-- tín hiệu kết thúc tới tiến trình
         -> Spring chuyển vào shutdown
         -> web server ngừng nhận request mới theo cơ chế của nó
         -> xử lý request đang chạy và dừng thành phần nền
         -> tiến trình kết thúc
```

Cập nhật EndpointSlice và shutdown diễn ra qua các thành phần khác nhau. Endpoint terminating có thể vẫn tồn tại trong slice; cần xem các condition như `ready`, `serving`, `terminating`, không chỉ đếm địa chỉ IP. [Nguồn: Kubernetes — Termination of Pods](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/).

Các proxy có thể có quy tắc riêng cho endpoint terminating/serving và kết nối đã có. Kiểm chứng đường traffic thật thay vì giả định cập nhật API ngay lập tức ngăn mọi byte tới Pod. [Nguồn: Kubernetes — EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/).

### 8.2. Request dài được nhận trước shutdown

Trong client ở cluster, gửi request có ID riêng:

```bash
curl --silent --show-error --max-time 35 \
  -H "X-Request-Id: drain-001" \
  "http://lifecycle-lab.lifecycle-lab.svc:8080/lab/work?delayMs=10000"
```

Quan sát log `WORK_ACCEPTED requestId=drain-001` và xác định **đúng Pod** đã nhận request. Sau khi xác nhận đó, xóa Pod này trong terminal quản trị:

```powershell
# Gán từ bằng chứng của request drain-001, không chọn Pod ngẫu nhiên.
$drainTargetPod = 'ten-pod-da-xac-nhan'
kubectl -n $labNamespace delete pod $drainTargetPod --wait=false
```

Với request 10 giây và ngân sách cấu hình phù hợp, kỳ vọng client nhận đủ response hợp lệ. Thu cả `WORK_COMPLETED`, kết quả client và trạng thái kết thúc container.

Không dùng tunnel port-forward của Pod làm đường kiểm thử duy nhất ở đây: tunnel có thể đứt theo lifecycle quản trị của Pod, làm nhiễu kết luận về Service hoặc ingress.

Lặp lại với request vượt timeout drain trong một run riêng. Kết quả chấp nhận được phải được định nghĩa trước: client lỗi có thể được dự kiến, nhưng công việc ghi phải có trạng thái xác định hoặc khả năng đối soát/retry.

### 8.3. Ngân sách shutdown

Nếu dùng `preStop`, thời gian hook nằm trong grace period của Pod và hook được chạy trước tín hiệu TERM theo luồng thông thường. [Nguồn: Kubernetes — Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/).

Một bất đẳng thức thiết kế:

```text
terminationGracePeriodSeconds
  >= thời gian preStop
   + tổng thời gian shutdown ứng dụng đã đo
   + phần dự phòng
```

Không thay “tổng thời gian shutdown” bằng duy nhất timeout của web server nếu ứng dụng còn nhiều phase, consumer, scheduler hoặc flush telemetry.

Ví dụ grace period 60 giây, preStop 5 giây và tổng shutdown đo được 25 giây có dư địa 30 giây. Đây là tính ngân sách, không phải chứng minh mọi lần chạy đều hoàn tất đúng hạn.

Chỉ thêm preStop chờ lan truyền định tuyến khi có bằng chứng cần thiết. Một sleep tùy ý không chứng minh traffic đã drain; image không có shell cũng không chạy được hook exec dựa vào `/bin/sh`. Nếu dùng HTTP hook, bảo đảm endpoint có thể gọi được và bản thân hook có thời hạn.

### 8.4. Công việc nền có hợp đồng riêng

HTTP graceful shutdown không tự hoàn tất mọi scheduler hoặc consumer:

- Ngừng claim công việc mới trước khi tháo hạ tài nguyên cần cho công việc đang chạy.
- Hoàn tất, checkpoint hoặc trả lại công việc theo chính sách.
- Chỉ ack message sau điểm commit đúng hợp đồng.
- Giữ khóa idempotency qua retry.
- Nếu có leader election, thu hồi phiên và dùng fencing tại nơi ghi cho tác dụng phụ quan trọng.
- Giới hạn thời gian chờ để một task treo không chặn shutdown vô hạn.

Một shutdown hook chỉ ghi log “bye” không phải bằng chứng job được bàn giao. Dùng kho dữ liệu nghiệp vụ hoặc biên nhận downstream để đối chiếu.

## 9. Ghép các tính năng Spring Cloud Kubernetes vào vòng kiểm chứng

### 9.1. DiscoveryClient và LoadBalancer

Baseline dùng Service DNS nên không cần DiscoveryClient cho đường gọi này. Nếu ứng dụng thật dùng discovery và Spring Cloud LoadBalancer, kiểm tra thêm:

- Instance không Ready hoặc đang terminating còn xuất hiện trong danh sách client bao lâu.
- Cấu hình có chủ ý bao gồm địa chỉ chưa Ready hay không.
- Cache danh sách instance, connection pool và retry ảnh hưởng chọn đích thế nào.
- Retry có chuyển sang instance khác và có giữ khóa nghiệp vụ không.
- Client chỉ đọc Endpoints hay EndpointSlice theo đúng phiên bản/cấu hình.

Không kết luận chỉ từ `kubectl get endpointslices` rằng mọi cache phía client đã cập nhật. Cần đối chiếu instance được chọn và response thực tế.

### 9.2. ConfigMap, Secret và thời điểm có hiệu lực

| Cách nhận cấu hình | Điều cần kiểm tra |
| --- | --- |
| Biến môi trường từ ConfigMap/Secret | Container đang chạy giữ giá trị đã nhận; phiên mới phải đọc giá trị mong đợi |
| Volume cấu hình | File có thể cập nhật sau một độ trễ; ứng dụng chưa chắc đã đọc lại |
| Spring đọc cấu hình khi startup | Giá trị hiệu lực trong bean có thể giữ nguyên đến khi tái tạo phù hợp |
| Watcher và refresh | Event được gửi, đúng instance được thông báo và bean thực sự dùng giá trị mới |
| Shutdown để nạp lại | Cần kiểm chứng toàn bộ hành vi kết thúc/khởi động và tiến độ công việc |

ConfigMap dùng qua biến môi trường không tự cập nhật trong container đang chạy. Volume projection có tính lan truyền và mount bằng `subPath` có giới hạn cập nhật riêng. [Nguồn: Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/).

Trong controller lab, `LAB_CONFIG_VERSION` là giá trị chụp từ env lúc khởi tạo. Sửa ConfigMap sẽ **không** làm trường này đổi trực tiếp. Dùng nó để xác nhận phiên container mới nhận đúng cấu hình.

Nếu cần chứng minh live refresh, bổ sung property được quản lý theo cơ chế refresh của dự án và kiểm tra hành vi dùng property đó. Không lấy nhãn phiên bản từ file rồi mặc định mọi bean đã cập nhật nhất quán.

### 9.3. Configuration Watcher

Khi dùng Configuration Watcher, kiểm tra cả chuỗi: thay đổi nguồn, lựa chọn ứng dụng đích, gửi sự kiện hoặc HTTP refresh, ứng dụng xử lý và giá trị có hiệu lực. Mounted file đổi không đồng nghĩa Spring tự nạp lại cấu hình; nhánh 3.3 mô tả cơ chế thông báo qua HTTP hoặc Spring Cloud Bus. [Nguồn: Spring Cloud Kubernetes 3.3 — Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/spring-cloud-kubernetes-configuration-watcher.html).

Tạo phép thử refresh trong lúc có request và một phép thử refresh đồng thời rollout. Xác định rõ request đang chạy dùng snapshot cấu hình cũ hay được phép dùng cấu hình mới. Không để một thao tác nửa dùng endpoint cũ, nửa dùng thông tin xác thực mới mà không có quy tắc chuyển đổi.

Chọn RBAC theo tính năng thực sự chạy: ứng dụng chỉ dùng volume và probe không cần quyền list/watch Secret. Watcher, discovery hoặc đọc API cần ServiceAccount và quyền tương ứng. Bật lại token và cấp quyền đúng phạm vi khi chuyển từ baseline sang các kịch bản này.

## 10. Sự cố, phục hồi và rollback

### 10.1. Phân loại failure mode

| Tình huống | Bằng chứng cần lấy | Không suy diễn |
| --- | --- | --- |
| Crash JVM | Boot ID, exit code, last state, restart count | Chắc chắn tạo Pod mới |
| OOM | Termination reason, memory, sự kiện và limit | Exit 137 luôn là OOM |
| Liveness lỗi | Kubelet event, probe failure và container restart | Readiness là nguyên nhân restart |
| Node mất liên lạc | Node condition, eviction/rescheduling, kết nối client | Ứng dụng chắc chắn đã nhận TERM |
| Xóa cưỡng bức | Đối tượng API và tiến trình thực tế | API không còn Pod nghĩa là tiến trình đã chết |
| Rollout đứng | ReplicaSet, scheduling, probe và điều kiện Deployment | Chắc chắn lỗi mã Java |
| 403 khi tích hợp | Request bị từ chối, ServiceAccount, RBAC | Mọi probe cần quyền API |

Không kỳ vọng log shutdown khi JVM bị dừng tức thời, node mất hoặc OOM-kill. Đó là lý do trạng thái quan trọng phải ở kho bền vững, không dựa riêng vào cleanup khi kết thúc.

Với request ghi bị timeout, tra cứu theo khóa nghiệp vụ hoặc dùng idempotency theo hợp đồng. Timeout không chứng minh tác dụng phụ chưa xảy ra.

### 10.2. Rollout lỗi và rollback

Tạo image lab có readiness luôn không đạt, rồi quan sát deadline và khả năng các replica cũ tiếp tục phục vụ. Trong Kubernetes, báo `ProgressDeadlineExceeded` không tự triển khai chính sách rollback thay cho hệ thống phát hành.

Lưu bằng chứng và thực hiện rollback có chủ ý:

```powershell
kubectl -n $labNamespace rollout history deployment/lifecycle-lab
kubectl -n $labNamespace rollout undo deployment/lifecycle-lab
kubectl -n $labNamespace rollout status deployment/lifecycle-lab --timeout=240s
```

Kiểm tra lại traffic, image ID thực tế, config version và nghiệp vụ. Rollback Deployment phục hồi Pod template của revision trước; nó không tự hoàn tác dữ liệu DB hoặc nội dung ConfigMap đang dùng.

Nếu ConfigMap đã thay đổi, image cũ có thể nạp cấu hình mới. Muốn tái lập release, lưu phiên bản cấu hình hoặc tham chiếu nguồn bất biến và kiểm thử khả năng rollback của cả bộ release.

Schema dữ liệu nên cho phép giai đoạn phiên bản cũ/mới cùng tồn tại theo kế hoạch migration. Không kết luận rollback an toàn chỉ vì container cũ đã lên Ready.

### 10.3. PDB không thay thế kiểm chứng rollout

Nếu thêm PodDisruptionBudget, kiểm thử đường Eviction API phù hợp. Xóa Pod trực tiếp không phải bằng chứng PDB đã bảo vệ việc gián đoạn.

PDB không hạn chế cách Deployment thực hiện rolling update; chiến lược update thuộc workload controller. PDB cũng không ngăn mọi sự cố không tự nguyện như node hỏng. [Nguồn: Kubernetes — Disruptions](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/).

Cluster một node không chứng minh được tính sẵn sàng khi node đó mất. Đặt phạm vi kết luận đúng với topology đã chạy.

## 11. Xây bộ kiểm chứng không báo thành công giả

### 11.1. Đo phía client và phía nghiệp vụ

Một bản ghi client nên chứa:

```text
run_id, request_id, operation_key
send_time, elapsed_time
http_status hoặc transport_error
pod_uid, boot_id, release, config_version
kết quả nghiệp vụ nếu có
```

Tách `request_id` của một lần thử và `operation_key` của cùng ý định nghiệp vụ. Retry có thể dùng request ID mới nhưng phải giữ operation key nếu muốn chống trùng.

Đối chiếu danh sách thao tác mong đợi với kết quả bền vững để tìm:

- Thao tác thiếu, trùng hoặc ngoài kế hoạch.
- Response thành công nhưng dữ liệu không đúng.
- Timeout nhưng tác dụng phụ đã commit.
- Job đã nhận rồi biến mất khỏi mọi trạng thái có thể phục hồi.

Không đặt unique constraint chỉ trên bảng quan sát rồi dùng “không có hàng trùng” để chứng minh hệ thống không tạo trùng bên ngoài. Journal phải phản ánh tác dụng phụ thực sự.

### 11.2. Polling, thời gian và độ đầy đủ

Dùng đồng hồ đơn điệu của bộ kiểm thử cho timeout. Mỗi request và lệnh con đều có thời hạn. Xác nhận một điều kiện ổn định trong cửa sổ đủ dài thay vì chỉ lấy một mẫu cuối.

Khi không hỏi được Pod, ghi UNKNOWN. Nếu không có đủ bằng chứng để chứng minh bất biến, báo INCONCLUSIVE thay vì PASS. Nếu có bằng chứng vi phạm, báo FAIL dù lần chạy lại thành công.

Độ phân giải lấy mẫu có giới hạn. Không thấy traffic sai trong vài mẫu không chứng minh không có cửa sổ lỗi ngắn; dùng thêm log request, trạng thái endpoint và dữ liệu client.

Cần có negative control trong lab: readiness cố ý khai báo sai, image không graceful hoặc shutdown budget quá ngắn với hiệu ứng mô phỏng. Bộ kiểm chứng phải phát hiện hành vi sai đã tạo ra.

### 11.3. Các phép thử tối thiểu trước phát hành

| Phép thử | Điều kiện đạt |
| --- | --- |
| Cold start và warmup | Không phục vụ sớm, đạt readiness trong SLO |
| Readiness mất/phục hồi | Định tuyến hội tụ đúng, không restart ngoài ý muốn |
| Rolling update có tải | Lỗi/độ trễ trong ngân sách, hai phiên bản cùng tồn tại an toàn |
| Request đang chạy khi xóa Pod | Kết quả client và nghiệp vụ khớp hợp đồng drain |
| Crash hoặc restart | Phục hồi được công việc, không trùng tác dụng phụ |
| Cập nhật cấu hình | Giá trị thực dùng thay đổi theo đúng cơ chế đã chọn |
| Rollout xấu và rollback | Phát hiện được lỗi, khôi phục release có kiểm chứng |

## 12. Báo cáo và kết thúc một run

Một báo cáo hữu ích cần ghi:

```text
Run ID, mục tiêu và bất biến:
Phiên bản Java / Spring Boot / Spring Cloud Kubernetes:
Kubernetes / CNI / ingress / web server:
Image digest và phiên bản cấu hình:
Replica, probe, rollout strategy, shutdown budget:
Đường traffic và loại client:
Tình huống, thời điểm tạo và xác nhận hiệu lực:
Mốc availability / Pod Ready / EndpointSlice / request:
Tỷ lệ lỗi, timeout, độ trễ và kết quả nghiệp vụ:
Container restart, last termination reason:
Kết quả PASS / FAIL / INCONCLUSIVE:
Bằng chứng, giới hạn quan sát và cleanup:
```

Phân lớp tự động hóa: unit test cho logic availability và lifecycle component; integration test cho Kubernetes thật; fault test cho mạng, node và cưỡng bức. Mock Kubernetes API không kiểm chứng được kubelet, proxy hay tín hiệu container.

CI song song cần namespace/run riêng. Cleanup phải chạy sau cả lỗi và timeout: khôi phục readiness, tháo fault, dừng client/port-forward, lưu bằng chứng rồi chỉ xóa tài nguyên thuộc run. Không ghi nội dung Secret vào artifact.

Kết luận triển khai phải dựa trên hành vi được quan sát: ứng dụng chỉ nhận việc khi đủ điều kiện, phục vụ đúng trong giai đoạn chuyển đổi, dừng theo ngân sách và phục hồi được khi không thể dừng có kiểm soát.
