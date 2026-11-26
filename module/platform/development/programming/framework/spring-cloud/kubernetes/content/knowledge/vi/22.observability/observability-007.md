# Theo dõi các lần thay đổi leader

## Mục tiêu và phạm vi

Trong chương **Khả năng quan sát** của module **SPRING_CLOUD_KUBERNETES**, bài học này hướng dẫn theo dõi việc một instance được trao hoặc bị thu hồi vai trò leader. Mục tiêu là biết **ai đang tự nhận là leader, khi nào vai trò thay đổi và việc chuyển giao có ảnh hưởng đến tác vụ hay không**.

Tình huống xuyên suốt là `orders-worker` có ba khả năng riêng: phục vụ HTTP, dùng cấu hình Kubernetes và chạy một tác vụ chỉ dành cho leader. DiscoveryClient hoặc Spring Cloud LoadBalancer không tự làm cho tác vụ nền chỉ chạy ở một replica; việc bầu leader là cơ chế phối hợp riêng.

Sau bài học, bạn có thể:

- Ghi log sự kiện nhận và mất leadership với đủ định danh instance, role và khóa bầu cử.
- Dùng counter, gauge và thời lượng quan sát để phát hiện thay đổi bất thường.
- Đối chiếu sự kiện ứng dụng với ConfigMap, trạng thái Pod và RBAC.
- Thực hành chuyển giao khi xóa có kiểm soát một Pod trong môi trường lab.
- Hiểu giới hạn của quan sát cục bộ, metric lấy mẫu và việc thiếu sự kiện khi tiến trình chết.

**Mốc triển khai của ví dụ:** Java 17 trở lên, Spring Boot 3.5.x và Spring Cloud Kubernetes **3.3.x với Fabric8 leader dùng ConfigMap**. Dependency được quản lý bằng bộ Spring Boot/Spring Cloud tương thích của dự án. Bài không mặc định dùng cơ chế Lease hoặc API sự kiện của nhánh khác.

## 1. Chốt cơ chế trước khi chọn sự kiện

Với triển khai ConfigMap trong Spring Cloud Kubernetes 3.3, các instance cạnh tranh leadership cho một role. Instance được trao vai trò nhận `OnGrantedEvent`; khi leadership bị thu hồi trong luồng xử lý có thể quan sát được, instance cũ nhận `OnRevokedEvent`. Các sự kiện mang `Context` và role của leadership. [Nguồn: Spring Cloud Kubernetes 3.3 — Leader election](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/leader-election.html).

Không trộn cấu hình của hai cơ chế sau:

| Nội dung | Ví dụ chính trong bài | Một cơ chế khác được tài liệu nhánh mới mô tả |
| --- | --- | --- |
| Họ thuộc tính | `spring.cloud.kubernetes.leader.*` | `spring.cloud.kubernetes.leader.election.*` |
| Khóa | ConfigMap | Có thể dùng Lease hoặc ConfigMap |
| Sự kiện | `OnGrantedEvent`, `OnRevokedEvent` | `StartLeadingEvent`, `StopLeadingEvent`, `NewLeaderEvent` |

Nếu dự án bật cơ chế mới, phải viết adapter quan sát theo đúng API của cơ chế ấy. Không mong listener `OnGrantedEvent` tự nhận mọi kiểu sự kiện mới chỉ vì cùng có tên chức năng leader election. [Nguồn đối chiếu: Leader election ở nhánh tài liệu mới](https://docs.spring.io/spring-cloud-kubernetes/reference/leader-election.html).

Kubernetes Lease là một loại tài nguyên điều phối riêng. Vì ví dụ này dùng ConfigMap, không tìm `spec.leaseTransitions` trên ConfigMap và không áp dụng các thông số TTL của Lease vào `update-period` của ví dụ. [Nguồn: Kubernetes — Leases](https://kubernetes.io/docs/concepts/architecture/leases/).

## 2. Định nghĩa “một lần thay đổi” trước khi đếm

Một lần chuyển giao logic từ A sang B có thể tạo ra:

1. A quan sát việc mất vai trò.
2. B quan sát việc nhận vai trò.
3. Khóa lưu định danh leader mới.
4. Hệ thống giám sát thu thập các bằng chứng vào những thời điểm khác nhau.

Hai callback ở A và B không phải hai lần chuyển giao độc lập. Hơn nữa, nếu A chết trước khi ghi log, có thể chỉ còn sự kiện nhận vai trò của B.

| Bằng chứng | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- |
| `OnGrantedEvent` tại A | A được thông báo nhận leadership | Tác vụ của A đã sẵn sàng hoặc hoàn thành |
| `OnRevokedEvent` tại A | A được thông báo mất leadership | Mọi công việc đang chạy ở A đã dừng xong |
| Gauge cục bộ bằng 1 | Listener tại instance đang giữ trạng thái đã nhận vai trò | Đây là ảnh chụp tức thời, tuyệt đối của toàn cluster |
| Khóa hiện ghi B | API đang trả bản ghi leader B | Có lịch sử đầy đủ mọi lần thay đổi trước đó |
| Không thấy log revoke | Chưa có bằng chứng revoke trong nguồn log đang xem | A chưa từng mất leadership |

Trong triển khai 3.3, controller chỉ phát sự kiện granted/revoked khi thay đổi liên quan đến **candidate cục bộ**. Một follower thấy leader khác đổi từ A sang B không đồng nghĩa follower ấy nhận `OnGrantedEvent`. Vì vậy phải thu thập từ tất cả instance tham gia. Đây là kết luận từ mã triển khai của phiên bản ví dụ. [Nguồn: LeadershipController v3.3.3](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/leader/LeadershipController.java).

Để nhận diện đúng một phạm vi bầu cử, luôn xét cùng **cluster, namespace, tên khóa và role**. Hai role hoặc hai khóa độc lập có thể đều có leader mà không phải lỗi.

## 3. Chuẩn bị ứng dụng và cấu hình quan sát

### 3.1. Dependency

Với dependency management tương thích đã có trong dự án, khai báo:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-kubernetes-fabric8-leader</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
```

Không gán phiên bản riêng tùy ý cho từng thư viện. Artifact leader 3.3.3 phụ thuộc Fabric8 autoconfiguration và Spring Integration core; Actuator là phụ thuộc optional của artifact đó, nên ví dụ khai báo tường minh để dùng metric và endpoint quản trị. [Nguồn: POM của Fabric8 leader v3.3.3](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.3/spring-cloud-kubernetes-fabric8-leader/pom.xml).

### 3.2. Cấu hình dành cho lab

```yaml
spring:
  application:
    name: orders-worker
  main:
    banner-mode: "off"
  cloud:
    kubernetes:
      client:
        namespace: "${POD_NAMESPACE:leader-lab}"
      leader:
        enabled: true
        namespace: "${POD_NAMESPACE:leader-lab}"
        role: orders-scheduler
        config-map-name: orders-leaders
        create-config-map: false
        update-period: 5s

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      probes:
        enabled: true
  info:
    leader:
      enabled: true
  metrics:
    tags:
      application: "${spring.application.name}"
      cluster: "${CLUSTER_NAME:training}"
      namespace: "${POD_NAMESPACE:leader-lab}"

logging:
  structured:
    format:
      console: logstash
    json:
      add:
        application: "${spring.application.name}"
        cluster: "${CLUSTER_NAME:training}"
        pod_namespace: "${POD_NAMESPACE:leader-lab}"
        pod_name: "${POD_NAME:local}"
        pod_uid: "${POD_UID:local}"
```

Trong bài, ConfigMap khóa được tạo trước, nên ứng dụng không cần tự tạo nó. Role được đặt rõ ràng để mọi candidate tham gia cùng một phạm vi. `update-period: 5s` là lựa chọn cho lab, có thể làm tăng số lần gọi API; mặc định nhánh 3.3 là 60 giây. Nó không cam kết failover hoàn tất trong đúng 5 giây. [Nguồn: Thuộc tính Spring Cloud Kubernetes 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/appendix.html).

Spring Boot cung cấp JSON console và khả năng thêm field cố định; SLF4J fluent key/value được đưa vào log có cấu trúc. Tên field trong bài là schema tự định nghĩa, không phải toàn bộ field do thư viện leader tự sinh. [Nguồn: Spring Boot 3.5 — Structured logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html#features.logging.structured).

Các endpoint `info`, `metrics` và `prometheus` được expose cho việc thực hành có kiểm soát. Triển khai thật phải áp dụng chính sách xác thực và mạng của hệ thống. Không thêm endpoint ghi dữ liệu hoặc endpoint refresh chỉ để theo dõi leadership.

## 4. Listener ghi log và metric có ý nghĩa rõ ràng

### 4.1. Các tín hiệu sẽ tạo

Những meter sau là **metric do bài học tự xây dựng**:

| Tên Micrometer | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `app.leadership.events` | Counter, tag `event=granted/revoked` | Số callback cục bộ đã xử lý theo từng loại |
| `app.leadership.is.leader` | Gauge 0/1 | Trạng thái cục bộ được listener ghi nhận |
| `app.leadership.tenure` | Timer | Thời gian từ grant đến revoke đã quan sát đủ tại cùng tiến trình |

Counter đếm sự kiện đã nhận, không phải số lần đổi leader duy nhất toàn cluster. Khi JVM khởi động lại, counter trong bộ nhớ bắt đầu lại; nên xem mức tăng hoặc tốc độ theo cửa sổ thời gian thay vì chỉ so sánh giá trị tuyệt đối. [Nguồn: Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html).

Gauge chỉ cho thấy giá trị tại lần lấy mẫu. Nếu leadership đổi nhiều lần giữa hai lần scrape, gauge không giữ lại các trạng thái trung gian. Đối tượng giữ giá trị gauge trong ví dụ được giữ tham chiếu mạnh bằng field của bean. [Nguồn: Micrometer — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html).

Timer ghi nhận một khoảng thời gian khi `Timer.Sample` được dừng. Nếu tiến trình chết trước revoke, nhiệm kỳ đó không có mẫu hoàn chỉnh trong timer; không mặc định coi đây là số liệu bao phủ mọi nhiệm kỳ. [Nguồn: Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

### 4.2. Mã listener

Đặt lớp sau trong package được component scan của ứng dụng lab:

```java
package com.example.orders;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.event.EventListener;
import org.springframework.integration.leader.Candidate;
import org.springframework.integration.leader.event.OnGrantedEvent;
import org.springframework.integration.leader.event.OnRevokedEvent;
import org.springframework.stereotype.Component;

@Component
public class LeadershipTelemetry {

    private static final Logger log =
            LoggerFactory.getLogger(LeadershipTelemetry.class);

    private final Candidate candidate;
    private final MeterRegistry registry;
    private final String role;
    private final String lockName;
    private final String observerInstance = UUID.randomUUID().toString();
    private final AtomicInteger localLeader = new AtomicInteger(0);
    private final Counter grants;
    private final Counter revokes;
    private final Timer completedTenure;

    private Timer.Sample activeTenure;
    private long sequence;
    private long localTerm;

    public LeadershipTelemetry(
            Candidate candidate,
            MeterRegistry registry,
            @Value("${spring.cloud.kubernetes.leader.role}") String role,
            @Value("${spring.cloud.kubernetes.leader.config-map-name}")
            String lockName) {
        this.candidate = candidate;
        this.registry = registry;
        this.role = role;
        this.lockName = lockName;

        this.grants = Counter.builder("app.leadership.events")
                .tags("role", role, "lock", lockName, "event", "granted")
                .register(registry);
        this.revokes = Counter.builder("app.leadership.events")
                .tags("role", role, "lock", lockName, "event", "revoked")
                .register(registry);
        this.completedTenure = Timer.builder("app.leadership.tenure")
                .tags("role", role, "lock", lockName)
                .register(registry);

        Gauge.builder("app.leadership.is.leader",
                        localLeader, AtomicInteger::get)
                .tags("role", role, "lock", lockName)
                .register(registry);
    }

    @EventListener
    public synchronized void onGranted(OnGrantedEvent event) {
        if (!role.equals(event.getRole())) {
            return;
        }
        grants.increment();
        boolean changed = localLeader.getAndSet(1) == 0;
        if (changed) {
            localTerm++;
            activeTenure = Timer.start(registry);
        }
        writeLog("granted", changed, event.getTimestamp());
    }

    @EventListener
    public synchronized void onRevoked(OnRevokedEvent event) {
        if (!role.equals(event.getRole())) {
            return;
        }
        revokes.increment();
        boolean changed = localLeader.getAndSet(0) == 1;
        if (changed && activeTenure != null) {
            activeTenure.stop(completedTenure);
            activeTenure = null;
        }
        writeLog("revoked", changed, event.getTimestamp());
    }

    private void writeLog(
            String event, boolean changed, long eventTimestamp) {
        log.atInfo()
                .addKeyValue("leadership_event", event)
                .addKeyValue("role", role)
                .addKeyValue("lock_name", lockName)
                .addKeyValue("candidate_id", candidate.getId())
                .addKeyValue("observer_instance", observerInstance)
                .addKeyValue("sequence", ++sequence)
                .addKeyValue("local_term", localTerm)
                .addKeyValue("state_changed", changed)
                .addKeyValue("is_leader", localLeader.get() == 1)
                .addKeyValue("event_timestamp_ms", eventTimestamp)
                .log("leadership-transition");
    }
}
```

Spring Integration cho phép nhận leadership event bằng listener và truy cập role/context. Ví dụ chỉ quan sát sự kiện, không đưa một tác vụ dài vào callback. Không gắn `@Async` vào listener này rồi mặc định thứ tự xử lý vẫn như trước. [Nguồn: Spring Integration 6.5 — Leadership event handling](https://docs.spring.io/spring-integration/reference/6.5/leadership-event-handling.html).

Candidate được inject từ cơ chế bầu cử để ghi đúng ID mà triển khai sử dụng. Với autoconfiguration Fabric8 3.3.3 mặc định, ID được tạo từ hostname và role lấy từ cấu hình. Trong lab không tùy biến Pod hostname; khi triển khai khác, không mặc định candidate ID luôn bằng Pod UID. [Nguồn: Fabric8LeaderAutoConfiguration v3.3.3](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.3/spring-cloud-kubernetes-fabric8-leader/src/main/java/org/springframework/cloud/kubernetes/fabric8/leader/Fabric8LeaderAutoConfiguration.java).

### 4.3. Đọc đúng các field và giới hạn

- `observer_instance` thay đổi khi bean/tiến trình mới được tạo, giúp phân biệt hai chuỗi đếm sau restart.
- `sequence` chỉ sắp thứ tự callback trong listener này.
- `local_term` tăng khi trạng thái cục bộ chuyển từ 0 sang 1. Nó không phải election term toàn cục và không phải fencing token.
- `state_changed=false` giúp nhận ra callback cùng loại không làm thay đổi trạng thái đã giữ; counter vẫn ghi nhận callback ấy.
- `event_timestamp_ms` là thời điểm tạo event trong ứng dụng, không phải thời điểm commit khóa đã được xác minh toàn cục.

Giá trị gauge ban đầu là 0, nghĩa là listener chưa ghi nhận một grant đang có hiệu lực. Nó không chứng minh ứng dụng đã đồng bộ thành công trạng thái cluster. Nếu không thấy event, phải kiểm tra bầu cử có thật sự chạy, listener có được tạo và kết nối API có hoạt động không.

Ví dụ này phục vụ một candidate, một role và một bộ điều phối leadership trong application context. Nếu ứng dụng có nhiều initiator cùng role, phải mở rộng khóa nhận diện và lọc event theo nguồn tương ứng; chỉ lọc role là chưa đủ.

## 5. Chuẩn bị RBAC và Pod cho lab

Các manifest dưới đây dành cho namespace lab riêng `leader-lab`. Người học áp dụng chúng bằng tài khoản có quyền chuẩn bị môi trường. Chúng không phải yêu cầu cấp quyền quản trị cluster cho ứng dụng.

### 5.1. Tạo trước khóa và cấp quyền trong namespace

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: leader-lab
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-leader
  namespace: leader-lab
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-leaders
  namespace: leader-lab
data: {}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: orders-leader
  namespace: leader-lab
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["orders-leaders"]
    verbs: ["get", "watch", "update"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: orders-leader
  namespace: leader-lab
subjects:
  - kind: ServiceAccount
    name: orders-leader
    namespace: leader-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: orders-leader
```

Role giới hạn thay đổi vào ConfigMap khóa đã đặt tên, không cấp quyền đọc Secret. Vì `create-config-map=false` và khóa đã có sẵn, ứng dụng không cần quyền create ConfigMap.

Khi dùng `resourceNames` cho list/watch, client phải gửi bộ lọc tên phù hợp với yêu cầu RBAC. Nếu một phiên bản client cần thao tác khác, xem API request và lỗi `403` trước khi sửa quyền; không thay ngay bằng wildcard hoặc ClusterRole rộng. [Nguồn: Kubernetes — RBAC authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Trong triển khai Fabric8 3.3.3, watcher khóa theo dõi ConfigMap đã đặt tên; watcher readiness theo dõi Pod. Đây là lý do lab cần quyền watch tương ứng. [Fabric8LeaderRecordWatcher](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.3/spring-cloud-kubernetes-fabric8-leader/src/main/java/org/springframework/cloud/kubernetes/fabric8/leader/Fabric8LeaderRecordWatcher.java), [Fabric8PodReadinessWatcher](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.3/spring-cloud-kubernetes-fabric8-leader/src/main/java/org/springframework/cloud/kubernetes/fabric8/leader/Fabric8PodReadinessWatcher.java).

### 5.2. Chạy ba candidate

Đóng gói ứng dụng có cấu hình và listener ở trên, rồi thay image placeholder bằng image mà cluster pull được:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-worker
  namespace: leader-lab
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-worker
  template:
    metadata:
      labels:
        app: orders-worker
    spec:
      serviceAccountName: orders-leader
      terminationGracePeriodSeconds: 30
      containers:
        - name: orders-worker
          image: your-registry.example/orders-worker:leader-observation
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
            - name: POD_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
            - name: POD_UID
              valueFrom:
                fieldRef:
                  fieldPath: metadata.uid
            - name: CLUSTER_NAME
              value: training
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
```

Đây là lab quan sát, chưa có tác vụ nghiệp vụ gây tác động bên ngoài. Không thêm một scheduler gửi tiền, phát email hoặc ghi dữ liệu thật để thử bầu leader.

**Không biến “không phải leader” thành readiness lỗi.** Với cơ chế của ví dụ, controller chỉ nhận candidate ready và kiểm tra readiness của leader hiện tại. Nếu Pod chỉ ready sau khi được bầu, trong khi nó phải ready mới được bầu, bạn tạo vòng chờ. Follower vẫn có thể ready và phục vụ HTTP; tác vụ chỉ dành cho leader phải được điều khiển riêng. [Nguồn: Fabric8LeadershipController v3.3.3](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.3/spring-cloud-kubernetes-fabric8-leader/src/main/java/org/springframework/cloud/kubernetes/fabric8/leader/Fabric8LeadershipController.java).

Không dùng ConfigMap khóa như nguồn cấu hình nghiệp vụ. Trong các luồng ConfigMap/Secret hoặc Configuration Watcher khác của hệ thống, giữ phạm vi và bộ lọc tách khỏi tài nguyên khóa, để việc bầu cử không bị hiểu nhầm là một thay đổi cấu hình cần refresh ứng dụng.

## 6. Thực hành quan sát chuyển giao leader

### 6.1. Thu mốc ban đầu

Sau khi áp dụng các manifest lab, dùng PowerShell:

```powershell
kubectl -n leader-lab rollout status deployment/orders-worker
kubectl -n leader-lab get pods -l app=orders-worker -o wide
kubectl -n leader-lab get configmap orders-leaders -o yaml

$beforeLog = kubectl -n leader-lab logs -l app=orders-worker -c orders-worker --since=10m --tail=-1
```

Đọc leader từ dữ liệu khóa của triển khai ví dụ:

```powershell
$lockSnapshot = kubectl -n leader-lab get configmap orders-leaders -o json | ConvertFrom-Json
$oldLeader = $lockSnapshot.data.'leader.id.orders-scheduler'

if ([string]::IsNullOrWhiteSpace($oldLeader)) {
    throw 'Chưa có leader được ghi nhận; cần chẩn đoán trước khi thử chuyển giao.'
}

kubectl -n leader-lab get pod $oldLeader -o custom-columns='NAME:.metadata.name,UID:.metadata.uid,READY:.status.conditions[?(@.type=="Ready")].status'
```

Khóa `leader.id.orders-scheduler` được tạo bằng prefix `leader.id.` cộng role trong cơ chế này. Nếu dùng schema khóa khác, phải đọc theo schema thực tế; không hard-code đường dẫn của ví dụ vào mọi triển khai.

Trong terminal riêng, quan sát khóa và Pod:

```powershell
kubectl -n leader-lab get configmap orders-leaders -w
```

```powershell
kubectl -n leader-lab get pods -l app=orders-worker -w
```

Lệnh watch hữu ích để thấy thay đổi từ thời điểm bắt đầu quan sát, không thay thế kho lịch sử lâu dài. Dùng Ctrl+C để dừng khi đã đủ bằng chứng.

### 6.2. Kiểm tra metric tại đúng Pod

Trong một terminal khác, thay tên Pod vào lệnh hoặc gán lại biến `$oldLeader`; biến PowerShell không tự được chia sẻ giữa các terminal:

```powershell
kubectl -n leader-lab port-forward pod/$oldLeader 18080:8080
```

Giữ port-forward chạy và gọi từ terminal còn lại:

```powershell
curl.exe -sS http://127.0.0.1:18080/actuator/info
curl.exe -sS http://127.0.0.1:18080/actuator/metrics/app.leadership.is.leader
curl.exe -sS http://127.0.0.1:18080/actuator/prometheus
```

Trong phiên bản ví dụ có InfoContributor leader, `info` cung cấp một snapshot về leader ID, role và việc instance hiện tại có phải leader hay không. Nó là dữ liệu chẩn đoán bổ sung, không phải chuỗi lịch sử chuyển giao.

Ở Pod đã nhận grant, gauge mẫu phải bằng 1. Khi kiểm tra follower, mở port-forward trực tiếp tới follower ở cổng local khác; không gọi một Service cân bằng tải rồi mặc định mọi phản hồi đều đến từ cùng instance.

Spring Boot tự cấu hình registry từ implementation có trên classpath; endpoint Prometheus cần registry tương ứng và phải được expose. Tên meter Micrometer được chuyển theo quy ước của backend. [Nguồn: Spring Boot — Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html).

### 6.3. Gây một lần chuyển giao có kiểm soát

Chỉ thực hiện với Pod thuộc Deployment lab ở trên, sau khi đã lưu mốc leader và log vào biến:

```powershell
kubectl -n leader-lab delete pod $oldLeader
kubectl -n leader-lab get pods -l app=orders-worker -w
```

Đây là yêu cầu xóa Pod bình thường, không dùng force delete. Deployment sẽ cố duy trì số replica. Candidate thắng tiếp theo có thể là follower còn sống hoặc Pod thay thế đã sẵn sàng; không yêu cầu một Pod cụ thể phải thắng.

Kỳ vọng quan sát:

- Khóa cập nhật sang leader khác khi quá trình bầu cử và readiness hội tụ.
- Candidate mới ghi `leadership_event=granted`.
- Candidate cũ có thể ghi `revoked` nếu tiến trình còn đủ điều kiện xử lý và chuyển log ra ngoài.
- Gauge ở candidate mới chuyển sang 1; dữ liệu của Pod đã mất có thể còn xuất hiện tạm thời trong hệ thống lấy mẫu.

Không coi thiếu log revoke ở Pod đang bị xóa là bằng chứng cơ chế bầu cử thất bại. Quá trình kết thúc có thời hạn; khi tiến trình chết đột ngột hoặc không đẩy kịp log, callback cuối có thể không còn quan sát được. [Nguồn: Kubernetes — Pod termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination).

Port-forward tới Pod cũ sẽ ngắt. Sau khi có leader mới, tạo lại port-forward tới đúng Pod đó để xác minh.

### 6.4. Đọc các callback đã thu được

Dừng watch khi ổn định, rồi lấy log của các Pod còn tồn tại:

```powershell
$afterLog = kubectl -n leader-lab logs -l app=orders-worker -c orders-worker --since=10m --tail=-1

$events = (@($beforeLog) + @($afterLog)) |
    Where-Object { $_.TrimStart().StartsWith('{') } |
    ForEach-Object { $_ | ConvertFrom-Json } |
    Where-Object { $_.message -eq 'leadership-transition' }

$events |
    Sort-Object observer_instance,sequence -Unique |
    Select-Object '@timestamp',pod_name,pod_uid,candidate_id,leadership_event,role,lock_name,observer_instance,sequence,local_term,state_changed
```

Hai cửa sổ log có thể chồng lấn. Cặp `observer_instance + sequence` giúp loại bản ghi trùng do thu lại cùng log trong lab, không phải thuật toán hợp nhất mọi sự kiện phân tán.

Không thêm `--prefix=true` hoặc timestamp tiền tố vào lệnh dùng để parse JSON. Dòng không phải JSON được lọc trong ví dụ cho tiện quan sát; pipeline thật cần ghi nhận lỗi parse thay vì bỏ log âm thầm.

Ví dụ một log grant rút gọn:

```json
{
  "message": "leadership-transition",
  "application": "orders-worker",
  "cluster": "training",
  "pod_namespace": "leader-lab",
  "pod_name": "orders-worker-example-b",
  "pod_uid": "example-pod-uid-b",
  "leadership_event": "granted",
  "role": "orders-scheduler",
  "lock_name": "orders-leaders",
  "candidate_id": "orders-worker-example-b",
  "observer_instance": "example-observer-id",
  "sequence": 1,
  "local_term": 1,
  "state_changed": true,
  "is_leader": true
}
```

Nếu cần thấy revoke trong khoảng đang xóa Pod, phải stream log trước khi xóa hoặc dùng hệ thống thu log tập trung. Snapshot `beforeLog` không chứa tương lai, còn `afterLog` không truy xuất được log của Pod đã bị xóa chỉ nhờ selector.

Khi ghép timeline qua nhiều Pod, timestamp có thể lệch do đồng hồ và độ trễ thu thập. Giữ nguồn event, thứ tự cục bộ và thời điểm quan sát khóa; không ép các đồng hồ thành một thứ tự nhân quả tuyệt đối.

## 7. Dashboard và cảnh báo từ nhiều nguồn

### 7.1. Thu metric từ mọi candidate

Giả định nền tảng đã có Prometheus hoặc hệ thống tương đương. Cấu hình discovery/scrape để **mỗi Pod là một target riêng**, với nhãn instance/Pod phân biệt được. Các annotation trên Pod không tự bảo đảm Prometheus sẽ scrape nếu cấu hình discovery không sử dụng chúng.

Không chỉ scrape một URL Service cân bằng tải. Nếu mỗi lần scrape đi vào Pod khác nhau dưới cùng một target, bạn có thể trộn các bộ đếm, bỏ sót follower và hiểu sai gauge. Prometheus hỗ trợ Kubernetes service discovery, nhưng việc lọc target và relabel phải được cấu hình phù hợp với hệ thống. [Nguồn: Prometheus — Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/).

Dashboard nên đặt cạnh nhau:

| Khung quan sát | Nội dung |
| --- | --- |
| Leadership | Gauge từng Pod, tổng gauge theo phạm vi bầu cử |
| Thay đổi | Grant/revoke trong cửa sổ thời gian, timeline log |
| Hạ tầng | Pod restart, Ready, rollout, CPU và độ trễ GC |
| API | Lỗi RBAC, timeout, watch reconnect nếu có telemetry tương ứng |
| Tác vụ | Heartbeat tiến độ, tuổi của lần thành công gần nhất, lỗi và hàng đợi |

### 7.2. Truy vấn tham khảo

Giả định đã xác minh tên xuất Prometheus từ endpoint và đã có các tag `cluster`, `namespace`, `application`, `role`, `lock` theo cấu hình/meter của bài.

Số instance đang công bố trạng thái leader:

```promql
sum by (cluster, namespace, application, role, lock) (
  app_leadership_is_leader{
    application="orders-worker",
    role="orders-scheduler",
    lock="orders-leaders"
  }
)
```

Trong giai đoạn ổn định và đủ dữ liệu, kỳ vọng tổng bằng 1. Tuy nhiên:

- Tổng bằng 0 cần đối chiếu coverage của scrape và trạng thái khởi động.
- Tổng lớn hơn 1 là dấu hiệu cần điều tra, không tự nó chứng minh hai tiến trình cùng thực thi tác vụ tại đúng một thời điểm.
- Không có series là tình huống khác với một series có giá trị 0.
- Trong chuyển giao, mẫu của leader cũ và mới có thể đến từ thời điểm khác nhau.

Số callback grant ước lượng trong 15 phút:

```promql
sum by (cluster, namespace, application, role, lock) (
  increase(app_leadership_events_total{
    application="orders-worker",
    event="granted"
  }[15m])
)
```

`increase` xử lý reset counter và nội suy theo cửa sổ lấy mẫu; kết quả có thể không là số nguyên. Nó không phục hồi được các event xảy ra hoàn toàn ngoài khoảng có mẫu, chẳng hạn một tiến trình khởi động, nhận grant rồi chết trước lần scrape đầu tiên. [Nguồn: Prometheus — Query functions](https://prometheus.io/docs/prometheus/latest/querying/functions/).

Đừng cộng granted và revoked rồi gọi kết quả là “số lần đổi leader”. Một chuyển giao bình thường có thể tạo cả hai; một sự cố chết đột ngột lại có thể thiếu revoke.

Để phát hiện mất toàn bộ tín hiệu cho một phạm vi đã biết:

```promql
absent_over_time(
  app_leadership_is_leader{
    cluster="training",
    namespace="leader-lab",
    application="orders-worker",
    role="orders-scheduler",
    lock="orders-leaders"
  }[5m]
)
```

Năm phút là cửa sổ minh họa. Cần kết hợp `up`, số target mong đợi và inventory workload để phát hiện thiếu một phần candidate, vì vẫn còn một series không đồng nghĩa đã thu đủ ba Pod.

### 7.3. Chọn cảnh báo theo tác động

| Tình huống | Điều kiện điều tra | Bằng chứng bổ sung |
| --- | --- | --- |
| Không có leader kéo dài | Tổng gauge bằng 0 qua nhiều lần scrape, coverage đủ | Khóa, RBAC, Ready và việc leader election có bật không |
| Nhiều instance cùng tự nhận leader | Tổng gauge lớn hơn 1 kéo dài | ID candidate, khóa/role thực tế, độ mới của mẫu, log tác vụ |
| Đổi leader liên tục | Grant tăng nhanh hơn mức bình thường của workload | Rollout, readiness flapping, restart, lỗi API |
| Có leader nhưng không có tiến độ | Gauge ổn định nhưng heartbeat/success age xấu | Deadlock, downstream, backlog và kết quả tác vụ |
| Mất tín hiệu | Target hoặc metric thiếu | Discovery/scrape, kết nối mạng và Pod đã bị thay thế |

Không chọn ngưỡng “quá nhiều lần” giống nhau cho mọi dịch vụ. Một rollout có kế hoạch và một tác vụ thanh toán ít được phép gián đoạn cần mức nhạy khác nhau.

## 8. Điều tra nguyên nhân thay đổi leader

Bắt đầu từ cùng cluster/namespace/lock/role, sau đó đối chiếu các mốc quanh lần chuyển giao:

1. Event cấp/mất vai trò ở ứng dụng.
2. Thay đổi khóa và Pod Ready.
3. Rollout, eviction, restart hoặc thay thế Pod.
4. Lỗi API, RBAC hoặc kết nối watch.
5. Tác vụ leader có ngừng/khởi động và đạt tiến độ hay không.

Ví dụ kiểm tra quyền bằng tài khoản người học có quyền impersonate:

```powershell
kubectl auth can-i get configmap/orders-leaders -n leader-lab --as=system:serviceaccount:leader-lab:orders-leader
kubectl auth can-i update configmap/orders-leaders -n leader-lab --as=system:serviceaccount:leader-lab:orders-leader
kubectl auth can-i watch pods -n leader-lab --as=system:serviceaccount:leader-lab:orders-leader

kubectl -n leader-lab describe deployment orders-worker
kubectl -n leader-lab get events --sort-by=.metadata.creationTimestamp
```

Nếu tài khoản người học không được impersonate, lệnh kiểm tra có thể bị từ chối dù service account ứng dụng có quyền đúng. Khi đó xem lỗi request thực tế hoặc nhờ người quản lý namespace xác minh.

`OnFailedToAcquireMutexEvent` có thể hữu ích khi bật xuất sự kiện lỗi theo cơ chế tương ứng, nhưng “mất tranh chấp” không đồng nghĩa “leader đã đổi”. Thống kê lỗi giành khóa nên tách khỏi granted/revoked để tránh đếm sai. Spring Integration mô tả nhóm sự kiện này cùng API leadership. [Nguồn: AbstractLeaderEvent](https://docs.spring.io/spring-integration/api/org/springframework/integration/leader/event/AbstractLeaderEvent.html).

Nếu follower không được bầu, đừng tự hạ readiness hoặc tăng restart liên tục để “ép” thắng. Trước hết kiểm tra role/khóa có thống nhất, leader hiện tại còn ready, callback có bị chặn và client có gọi đúng namespace không.

## 9. Quan sát leadership không thay thế an toàn tác vụ

Log grant chỉ cho biết listener đã nhận tín hiệu. Cần phân biệt thêm các mốc nghiệp vụ:

- `leader-work-starting`: bắt đầu chuẩn bị công việc.
- `leader-work-ready`: công việc đã đủ điều kiện thực thi.
- `leader-work-stop-requested`: đã yêu cầu dừng sau revoke.
- `leader-work-stopped`: đã xác nhận dừng hoặc ghi nhận công việc còn dang dở.
- Heartbeat tiến độ và kết quả thành công cuối cùng.

Khi revoke, một request gửi xuống hệ thống ngoài có thể vẫn đang chạy. Việc kiểm tra một cờ `isLeader` trước khi gọi không loại bỏ khoảng đua giữa kiểm tra và hành động. Nếu tác vụ không được phép thực hiện trùng, cần thiết kế idempotency, ràng buộc dữ liệu hoặc fencing được hệ thống nhận ghi kiểm tra.

`local_term`, resourceVersion của ConfigMap và số thứ tự log trong bài không tự trở thành fencing token hợp lệ. Không đưa chúng vào quyết định từ chối/cho phép ghi ở hệ thống ngoài nếu chưa có giao thức tương ứng.

Tương tự, DiscoveryClient, Spring Cloud LoadBalancer và Configuration Watcher giải quyết các nhu cầu khác. Không thêm leader election chỉ vì ứng dụng đang dùng các tính năng ấy; chỉ sử dụng khi công việc thực sự cần một vai trò phối hợp và đã xác định cách dừng, phục hồi, quan sát tác vụ.

## 10. Tiêu chí hoàn thành

Bạn hoàn thành bài thực hành khi có thể chỉ ra:

1. Phiên bản/cơ chế leader election, loại khóa, role và API sự kiện đang sử dụng.
2. Một grant ban đầu khớp candidate ID và Pod identity.
3. Một lần chuyển giao có bằng chứng từ khóa, log ứng dụng và trạng thái Pod.
4. Lý do có thể thiếu revoke khi Pod bị chấm dứt.
5. Ý nghĩa chính xác của counter callback, gauge cục bộ và timer nhiệm kỳ hoàn chỉnh.
6. Cách phân biệt không có leader với không thu được metric.
7. Readiness độc lập với vai trò follower/leader trong lab.
8. Giới hạn của thứ tự log cục bộ và lý do quan sát leadership chưa bảo đảm tác vụ chỉ thực hiện một lần.

Một hệ thống theo dõi hữu ích không chỉ thông báo “leader đã đổi”. Nó giúp xác định phạm vi bầu cử, instance liên quan, độ tin cậy của bằng chứng và tác động thực tế lên công việc.

