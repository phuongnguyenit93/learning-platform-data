# Chỉ cho phép thực hiện tác vụ khi đang giữ vai trò

Trong chương **Bầu leader** của **SPRING_CLOUD_KUBERNETES**, việc bầu được một Pod làm leader chỉ là bước đầu. Ứng dụng còn phải quyết định khi nào được bắt đầu công việc, khi nào phải dừng và cách xử lý phần việc đang dang dở khi quyền lãnh đạo thay đổi.

Giả sử dịch vụ đối soát sổ cái có ba replica. Cả ba đều phục vụ HTTP và đều có bộ lập lịch, nhưng chỉ replica đang giữ vai trò `ledger-reconciler` được chạy vòng đối soát. Hai replica còn lại vẫn hoạt động bình thường và chờ cơ hội tiếp quản. Bài học này xây dựng cổng kiểm tra quyền thực thi cho tình huống đó, sau đó chỉ ra giới hạn của cổng khi thao tác đến cơ sở dữ liệu hoặc dịch vụ bên ngoài.

## 1. Kết quả cần đạt và phạm vi API

Sau bài học, bạn có thể:

- Chuyển sự kiện được cấp hoặc thu hồi vai trò thành trạng thái thực thi an toàn giữa các luồng.
- Chặn tác vụ ở thời điểm nhận việc và tại các điểm kiểm tra trong quá trình xử lý.
- Phân biệt một lần giữ vai trò với lần được bầu lại sau đó.
- Bố trí quyền RBAC, readiness và cách quan sát để kiểm chứng hành vi trên nhiều Pod.
- Nhận ra khi nào cần idempotency hoặc fencing để bảo vệ kết quả nghiệp vụ.

Ví dụ Java sử dụng Java 17 trở lên và **cơ chế ConfigMap/Fabric8 của Spring Cloud Kubernetes 3.3.x**. Cơ chế này phát `OnGrantedEvent` và `OnRevokedEvent` của Spring Integration; tên ConfigMap được cấu hình bằng `spring.cloud.kubernetes.leader.config-map-name`. Đây là phạm vi phiên bản của ví dụ, không phải yêu cầu mọi dự án phải chọn dòng phiên bản này. [Tài liệu Leader Election 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/leader-election.html).

Một số dòng mới có cơ chế native được bật bằng `spring.cloud.kubernetes.leader.election.enabled`, với các sự kiện `StartLeadingEvent` và `StopLeadingEvent`. Khi dùng cơ chế đó, cần thay lớp tiếp nhận sự kiện theo đúng API; không ghép thuộc tính và tên sự kiện của hai cơ chế vào cùng một ví dụ. Phần thiết kế cổng và giới hạn nghiệp vụ dưới đây vẫn áp dụng. [Tài liệu Leader Election cho các cơ chế được hỗ trợ](https://docs.spring.io/spring-cloud-kubernetes/reference/leader-election.html).

## 2. Ba điều kiện khác nhau trước khi làm việc

Một tác vụ đối soát chỉ nên bắt đầu khi đồng thời thỏa mãn ba điều kiện:

| Điều kiện | Câu hỏi cần trả lời | Cơ chế trong bài |
| --- | --- | --- |
| Được phép theo vai trò | Pod này đã được cấp đúng vai trò chưa? | Cổng nhận sự kiện leader |
| Không có lượt chạy chồng trong JVM | Một lời gọi khác có đang thực hiện cùng tác vụ không? | `AtomicBoolean` cho lượt chạy |
| Lượt công việc còn thuộc nhiệm kỳ hiện tại | Công việc có được tạo trước một lần mất quyền không? | Mã thế hệ của giấy phép |

Leader election không tự thay đổi cách `@Scheduled` hoạt động. Nếu mọi replica có cùng phương thức được lập lịch, mọi replica vẫn đi vào phương thức đó. Cổng thực thi phải chủ động cho follower thoát ra trước khi chạm đến nghiệp vụ.

Tương tự, `synchronized` hoặc `AtomicBoolean` chỉ điều phối các luồng trong một JVM. Chúng không ngăn một Pod khác cùng xử lý công việc.

Ở đây, **role** là tên vai trò nghiệp vụ như `ledger-reconciler`. Nó khác tài nguyên Kubernetes **Role** trong RBAC. Role nghiệp vụ dùng để xác định nhóm tranh quyền; RBAC quyết định ServiceAccount được gọi những Kubernetes API nào.

### Nhận việc và tiếp tục làm việc là hai lần kiểm tra

Một lần kiểm tra ở đầu tác vụ không đủ cho tác vụ dài:

~~~text
t0: Pod A nhận quyền, bắt đầu xử lý 10.000 bản ghi.
t1: Pod A mất quyền.
t2: Pod B nhận quyền và bắt đầu xử lý.
t3: Pod A vẫn tiếp tục vòng lặp vì chỉ kiểm tra một lần ở t0.
~~~

Do đó, cổng cần được kiểm tra trước khi nhận batch và trước từng đơn vị công việc đủ nhỏ. Mỗi đơn vị cũng phải có thời gian xử lý hữu hạn để việc dừng có độ trễ kiểm soát được.

## 3. Cấu hình ứng dụng chỉ với tính năng cần dùng

Dự án cần Spring Boot, Spring Scheduling và dependency leader tương thích với Spring Cloud BOM đang dùng. Với dòng 3.3.x, module leader phụ thuộc vào Fabric8 autoconfiguration và Spring Integration core. Không cần thêm DiscoveryClient hay LoadBalancer chỉ để bầu leader. [Dependency của module leader 3.3.3](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.3/spring-cloud-kubernetes-fabric8-leader/pom.xml).

Đoạn `pom.xml` dưới đây là phần dependency bổ sung cho dự án đã quản lý phiên bản Spring Boot/Spring Cloud tương thích qua parent và BOM:

~~~xml
<dependencies>
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
</dependencies>
~~~

Web và Actuator phục vụ HTTP cùng các probe của bài thực hành. Chúng không phải điều kiện để thuật toán bầu leader có thể tồn tại.

Đặt cấu hình sau trong `application.yml` của ứng dụng mẫu:

~~~yaml
spring:
  application:
    name: ledger-reconciler
  cloud:
    kubernetes:
      leader:
        enabled: true
        auto-startup: true
        role: ledger-reconciler
        namespace: ${POD_NAMESPACE:leader-lab}
        config-map-name: ledger-leaders
        create-config-map: false
        update-period: 2s

tasks:
  reconcile:
    delay-ms: 5000

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
~~~

Các thuộc tính `role`, `namespace`, `create-config-map` và `update-period` ở đây thuộc nhóm `spring.cloud.kubernetes.leader` của cơ chế đã chọn. Giá trị `2s` là chu kỳ kiểm tra của ví dụ; không được diễn giải thành thời hạn bảo đảm chuyển quyền sau đúng hai giây. [LeaderProperties 3.3.3](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/leader/LeaderProperties.java).

ConfigMap `ledger-leaders` được tạo trước bởi người triển khai. Đây là đối tượng điều phối, khác với ConfigMap chứa cấu hình nghiệp vụ được nạp vào Spring Environment. Việc dùng leader election không yêu cầu đọc Secret, bật Configuration Watcher hoặc tự động refresh cấu hình.

Tất cả replica tham gia cùng nhóm phải thống nhất namespace, tên ConfigMap và role. Không thay role bằng cấu hình động khi còn công việc đang chạy; một thay đổi như vậy cần quy trình dừng, chuyển nhóm và khởi động lại rõ ràng.

## 4. Cổng thực thi với giấy phép theo từng nhiệm kỳ

Một cờ boolean cho biết trạng thái hiện tại nhưng không xác định nguồn gốc của công việc. Xét trình tự sau:

~~~text
Công việc X được tạo ở thế hệ 1.
Pod mất quyền: leader = false.
Pod được bầu lại: leader = true.
Công việc X tỉnh dậy và thấy leader = true.
~~~

Nếu chỉ dùng boolean, công việc X có thể tiếp tục dưới lần giữ quyền mới. Để tránh điều đó, mỗi lần thay đổi quyền phải làm giấy phép cũ mất hiệu lực.

Mô hình dưới đây dùng bộ đếm `generation` cục bộ:

~~~mermaid
stateDiagram-v2
    [*] --> Waiting
    Waiting --> Leading: Được cấp đúng role, tăng generation
    Leading --> Waiting: Bị thu hồi, tăng generation
    Leading --> Closed: Ứng dụng đóng
    Waiting --> Closed: Ứng dụng đóng
    Closed --> [*]
~~~

Một giấy phép hợp lệ khi cổng đang mở, Pod đang được xem là leader và số thế hệ của giấy phép trùng số thế hệ hiện tại.

### Lớp LeaderGate

Đặt từng lớp Java trong tệp riêng cùng package `example.leader`. Các tên tệp trong bài là hướng dẫn tạo ứng dụng thực hành.

~~~java
package example.leader;

import java.util.Optional;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.integration.leader.event.OnGrantedEvent;
import org.springframework.integration.leader.event.OnRevokedEvent;
import org.springframework.stereotype.Component;

@Component
public class LeaderGate {

    private static final Logger log = LoggerFactory.getLogger(LeaderGate.class);

    public record Permit(long generation) {
    }

    private final String role;
    private final String podName;

    // Mọi truy cập các trường dưới đây đều giữ cùng monitor.
    private boolean leader;
    private boolean closed;
    private long generation;

    public LeaderGate(
            @Value("${spring.cloud.kubernetes.leader.role}") String role,
            @Value("${POD_NAME:local}") String podName) {
        this.role = role;
        this.podName = podName;
    }

    @EventListener
    public synchronized void onGranted(OnGrantedEvent event) {
        if (closed || !role.equals(event.getRole())) {
            return;
        }

        generation++;
        leader = true;
        log.info("LEADER_GRANTED pod={} role={} generation={}",
                podName, role, generation);
    }

    @EventListener
    public synchronized void onRevoked(OnRevokedEvent event) {
        if (closed || !role.equals(event.getRole())) {
            return;
        }

        leader = false;
        generation++;
        log.info("LEADER_REVOKED pod={} role={} generation={}",
                podName, role, generation);
    }

    public synchronized Optional<Permit> acquirePermit() {
        if (closed || !leader) {
            return Optional.empty();
        }
        return Optional.of(new Permit(generation));
    }

    public synchronized boolean isValid(Permit permit) {
        return permit != null
                && !closed
                && leader
                && generation == permit.generation();
    }

    @EventListener
    public synchronized void onApplicationClosing(ContextClosedEvent event) {
        if (!closed) {
            closed = true;
            leader = false;
            generation++;
            log.info("LEADER_GATE_CLOSED pod={} role={}", podName, role);
        }
    }
}
~~~

`getRole()` và `getContext()` là API của lớp sự kiện cha trong Spring Integration. Cổng lọc theo role để sự kiện cho một vai trò khác không vô tình cấp quyền thực thi. [API AbstractLeaderEvent](https://docs.spring.io/spring-integration/api/org/springframework/integration/leader/event/AbstractLeaderEvent.html).

Các lựa chọn quan trọng trong thiết kế:

- **Khởi đầu đóng:** chưa nhận được sự kiện cấp quyền thì không phát giấy phép.
- **Đồng bộ hóa nhất quán:** cả listener và luồng chạy tác vụ đều truy cập trạng thái qua cùng monitor; không đọc trực tiếp các trường.
- **Thu hồi làm vô hiệu giấy phép:** không chỉ đổi boolean mà còn tăng thế hệ.
- **Đóng ứng dụng là trạng thái cuối:** một sự kiện grant đến sau khi cổng đóng cũng không mở lại cổng.
- **Không giữ monitor trong lúc làm nghiệp vụ:** thao tác đối soát dài không ngăn listener cập nhật trạng thái.

Giữ listener cập nhật cổng ngắn và đồng bộ theo luồng phát sự kiện thông thường. Không thêm `@Async` vào hai listener này hoặc chuyển bộ phát sự kiện sang executor mà không thiết kế lại thứ tự xử lý. Sự kiện bị trì hoãn hoặc đảo thứ tự có thể khiến trạng thái cục bộ sai.

`generation` là **mã của nhiệm kỳ trong một tiến trình**, không phải thông tin xác thực và không phải fencing token dùng chung toàn cụm. Sau khi Pod khởi động lại, bộ đếm bắt đầu lại. Điều đó phù hợp với giấy phép chỉ sống trong bộ nhớ của chính tiến trình.

## 5. Gắn cổng vào tác vụ được lập lịch

Bật Scheduling trong ứng dụng:

~~~java
package example.leader;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@EnableScheduling
@SpringBootApplication
public class LeaderTaskApplication {

    public static void main(String[] args) {
        SpringApplication.run(LeaderTaskApplication.class, args);
    }
}
~~~

Tác vụ minh họa dưới đây xử lý mười đơn vị trong mỗi lượt. `Thread.sleep(200)` chỉ mô phỏng thời gian chuẩn bị dữ liệu; `DEMO_PROCESS` chỉ ghi log, chưa gọi cơ sở dữ liệu hay API nghiệp vụ.

~~~java
package example.leader;

import java.util.concurrent.atomic.AtomicBoolean;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ReconcileTask {

    private static final Logger log =
            LoggerFactory.getLogger(ReconcileTask.class);

    private final LeaderGate gate;
    private final String podName;
    private final AtomicBoolean running = new AtomicBoolean(false);

    public ReconcileTask(
            LeaderGate gate,
            @Value("${POD_NAME:local}") String podName) {
        this.gate = gate;
        this.podName = podName;
    }

    @Scheduled(fixedDelayString = "${tasks.reconcile.delay-ms:5000}")
    public void tick() {
        LeaderGate.Permit permit = gate.acquirePermit().orElse(null);
        if (permit == null) {
            log.debug("SKIP_NOT_LEADER pod={}", podName);
            return;
        }

        if (!running.compareAndSet(false, true)) {
            log.debug("SKIP_ALREADY_RUNNING pod={}", podName);
            return;
        }

        try {
            for (int item = 0; item < 10; item++) {
                if (!mayContinue(permit)) {
                    log.info("STOP_STALE_WORK pod={} generation={}",
                            podName, permit.generation());
                    return;
                }

                // Mô phỏng chuẩn bị dữ liệu, không tạo tác dụng phụ.
                Thread.sleep(200);

                if (!mayContinue(permit)) {
                    log.info("STOP_BEFORE_EFFECT pod={} generation={}",
                            podName, permit.generation());
                    return;
                }

                log.info("DEMO_PROCESS pod={} generation={} item={}",
                        podName, permit.generation(), item);
            }
        }
        catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            log.info("STOP_INTERRUPTED pod={}", podName);
        }
        catch (RuntimeException failure) {
            log.error("BATCH_FAILED pod={}", podName, failure);
        }
        finally {
            running.set(false);
        }
    }

    private boolean mayContinue(LeaderGate.Permit permit) {
        return !Thread.currentThread().isInterrupted()
                && gate.isValid(permit);
    }
}
~~~

`fixedDelay` của phương thức đồng bộ giúp một lịch đơn không tự chồng lượt. Chốt `running` thể hiện thêm điều kiện loại trừ trong JVM nếu cùng đối tượng tác vụ có đường kích hoạt khác về sau. Nó vẫn không thay thế việc bầu leader giữa các Pod.

Khi quyền bị thu hồi trong lúc `sleep`, lần kiểm tra tiếp theo sẽ dừng batch. Khi Pod mất quyền rồi được bầu lại rất nhanh, batch cũ vẫn dừng vì giấy phép mang thế hệ cũ. Lượt lịch sau có thể lấy giấy phép mới và bắt đầu một batch mới.

Khoảng giữa lần kiểm tra cuối và dòng `DEMO_PROCESS` vẫn tồn tại. Listener có thể thu hồi quyền ngay trong khoảng này. Vì vậy, mẫu này là **hủy hợp tác theo hiểu biết cục bộ**, không phải bảo đảm nguyên tử giữa quyền lãnh đạo và tác dụng phụ.

### Nếu công việc được đưa vào executor hoặc hàng đợi

Giấy phép phải đi cùng phần việc ngay từ lúc phần việc được tạo:

~~~text
Nhận batch -> lấy Permit P -> đưa Work(batchId, P) vào executor.
Executor lấy Work -> kiểm tra P -> xử lý từng phần với P.
Có revoke/grant mới -> P cũ mất hiệu lực -> Work cũ dừng.
~~~

Không lấy một giấy phép mới ở giữa batch để làm công việc cũ hợp lệ trở lại. Nếu muốn tiếp tục batch sau chuyển quyền, đó phải là một lượt phục hồi mới có checkpoint và chính sách chống trùng rõ ràng.

Khi thu hồi quyền, có thể gọi `Future.cancel(true)` để yêu cầu dừng sớm. Tuy nhiên, interrupt không buộc mọi thư viện I/O dừng ngay và không hoàn tác HTTP request đã gửi. Phần việc phải tự kiểm tra trạng thái, tôn trọng interrupt và đặt timeout cho thao tác chặn.

## 6. RBAC và readiness cho môi trường thực hành

Ví dụ triển khai sử dụng namespace riêng `leader-lab`, hai replica và ServiceAccount `ledger-worker`. Tạo ConfigMap điều phối trước, sau đó không cấp quyền tạo ConfigMap cho ứng dụng.

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: leader-lab
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ledger-worker
  namespace: leader-lab
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: ledger-leaders
  namespace: leader-lab
data: {}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: ledger-leader-access
  namespace: leader-lab
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["ledger-leaders"]
    verbs: ["get", "list", "watch", "update"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: ledger-leader-access
  namespace: leader-lab
subjects:
  - kind: ServiceAccount
    name: ledger-worker
    namespace: leader-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: ledger-leader-access
~~~

Quyền ConfigMap được giới hạn theo tên. Với quyền `list/watch` có `resourceNames`, client phải gửi bộ lọc tên tương ứng để yêu cầu được chấp nhận. Không thể dùng cùng kỹ thuật để giới hạn yêu cầu `create` tài nguyên cấp cao nhất theo tên; vì vậy bài thực hành chọn tạo sẵn ConfigMap. [Quy tắc resourceNames trong Kubernetes RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#referring-to-resources).

Trong triển khai Fabric8 đã chọn, watcher ConfigMap được tạo bằng thao tác `withName(...).watch(...)`; bộ điều khiển đọc và cập nhật bản ghi bằng resource version. Nếu thay phiên bản client, cần kiểm tra yêu cầu API thực tế trước khi điều chỉnh quyền đọc thay vì cấp quyền toàn cụm. [Fabric8LeaderRecordWatcher 3.3.3](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.3/spring-cloud-kubernetes-fabric8-leader/src/main/java/org/springframework/cloud/kubernetes/fabric8/leader/Fabric8LeaderRecordWatcher.java), [Fabric8LeadershipController 3.3.3](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.3/spring-cloud-kubernetes-fabric8-leader/src/main/java/org/springframework/cloud/kubernetes/fabric8/leader/Fabric8LeadershipController.java).

Quyền đọc/watch Pod phục vụ theo dõi readiness. Cơ chế này dùng trạng thái Ready của Pod khi quyết định nhận hoặc thay leader; vì vậy follower cần có khả năng Ready trước khi được bầu. [Fabric8PodReadinessWatcher 3.3.3](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.3/spring-cloud-kubernetes-fabric8-leader/src/main/java/org/springframework/cloud/kubernetes/fabric8/leader/Fabric8PodReadinessWatcher.java).

Đừng định nghĩa readiness là `isLeader == true` cho ứng dụng này. Cách đó tạo vòng phụ thuộc: Pod chờ làm leader mới Ready, trong khi quá trình tranh quyền lại chờ Pod Ready. Follower khỏe mạnh vẫn nên Ready để tiếp quản và phục vụ các chức năng không yêu cầu leader.

Deployment minh họa:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ledger-reconciler
  namespace: leader-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: ledger-reconciler
  template:
    metadata:
      labels:
        app: ledger-reconciler
    spec:
      serviceAccountName: ledger-worker
      terminationGracePeriodSeconds: 30
      containers:
        - name: app
          image: example/ledger-reconciler:leader-lab
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
            - name: KUBERNETES_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            initialDelaySeconds: 5
            periodSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            initialDelaySeconds: 20
            periodSeconds: 10
~~~

Thay image mẫu bằng image chứa ba lớp Java và cấu hình ở trên. Biến `POD_NAME` phục vụ log; ví dụ giữ hostname mặc định của Pod để không làm sai định danh candidate. `KUBERNETES_NAMESPACE` cấu hình namespace cho Fabric8 client, còn `POD_NAMESPACE` được dùng trong thuộc tính leader. Hai giá trị cần trùng nhau trong bài thực hành này.

Không cần quyền Secret, quyền sửa Deployment hoặc ClusterRoleBinding cho tác vụ trên. Nếu sau này ứng dụng cần DiscoveryClient, đọc ConfigMap nghiệp vụ hay Secret, hãy đánh giá và bổ sung từng nhóm quyền theo chức năng được bật.

## 7. Kiểm chứng hành vi trên hai replica

Các lệnh dưới đây dành cho ứng dụng thực hành đã được build và triển khai bằng các manifest trên. Chúng là hướng dẫn kiểm chứng, không phải kết quả một lần chạy sẵn.

### Quan sát trạng thái ổn định

~~~powershell
kubectl get pods -n leader-lab -l app=ledger-reconciler
kubectl get configmap ledger-leaders -n leader-lab -o yaml
kubectl logs -n leader-lab -l app=ledger-reconciler --prefix=true --tail=100 -f
~~~

Kỳ vọng sau khi hai Pod Ready và quá trình điều phối ổn định:

- Một Pod có `LEADER_GRANTED`, sau đó có các dòng `DEMO_PROCESS`.
- Pod còn lại không tạo log `DEMO_PROCESS` khi chưa được cấp quyền.
- ConfigMap có thông tin của role đang tranh quyền; quan sát đối tượng này mà không chỉnh tay dữ liệu để ép đổi leader.
- Nếu bật DEBUG cho package `example.leader`, follower có log `SKIP_NOT_LEADER`.

Mỗi dòng log phải có Pod và generation để phân biệt các tiến trình và các lượt giữ quyền. Giá trị generation bằng nhau ở hai Pod không có nghĩa chúng cùng một nhiệm kỳ.

### Quan sát đổi leader

Lấy tên Pod leader từ log, rồi trong namespace thực hành xóa đúng Pod đó:

~~~powershell
$leaderPod = 'ten-pod-leader-lay-tu-log'
kubectl delete pod $leaderPod -n leader-lab
kubectl get pods -n leader-lab -l app=ledger-reconciler -w
~~~

Giữ cửa sổ log mở ở terminal khác. Kiểm tra Pod còn lại có thể nhận quyền và tiếp tục chạy; Pod thay thế do Deployment tạo ra không tự ý chạy nghiệp vụ trước grant.

Khi đóng ứng dụng có trật tự, có thể thấy `LEADER_GATE_CLOSED`. Khi tiến trình chết đột ngột, không thể kỳ vọng nó ghi log revoke hoặc chạy callback đóng. Việc follower tiếp quản phụ thuộc vào cơ chế phát hiện và cập nhật trạng thái của cụm, không chỉ thuộc tính `update-period`.

### Quan sát việc dừng một batch còn sống

Xóa Pod chủ yếu kiểm tra chuyển quyền giữa các tiến trình. Để thấy rõ `STOP_STALE_WORK` mà tiến trình cũ vẫn còn sống, dùng một kịch bản trong môi trường thử nghiệm khiến Pod mất vai trò nhưng JVM vẫn chạy, hoặc kiểm thử lớp cổng với chuỗi sự kiện có kiểm soát.

Chuỗi cần quan sát là:

~~~text
grant đúng role -> lấy P1 -> isValid(P1) = true
revoke đúng role -> isValid(P1) = false
grant lại đúng role -> lấy P2 -> isValid(P2) = true
kiểm tra P1 lần nữa -> vẫn false
~~~

Kịch bản này xác minh điều mà thử nghiệm xóa Pod không tự chứng minh: công việc cũ không được hồi sinh khi chính Pod đó được bầu lại.

### Xem thông tin qua Actuator

Cơ chế leader của dòng được chọn có InfoContributor cung cấp thông tin tại `/actuator/info`. Có thể port-forward đến từng Pod rồi xem endpoint này. Đây là dữ liệu quan sát; không dùng HTTP GET tới Actuator làm bước khóa trước mỗi thao tác nghiệp vụ. [Leader Election Info Contributor](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/leader-election.html#leader-election-info-contributor).

## 8. Xử lý công việc đang chạy khi quyền thay đổi

Thu hồi vai trò không tương đương rollback tất cả công việc. Cần xác định điểm dừng cho từng dạng tác vụ:

| Dạng công việc | Điểm kiểm tra phù hợp | Cách xử lý khi mất quyền |
| --- | --- | --- |
| Quét bảng theo trang | Trước truy vấn trang, sau chuẩn bị và trước ghi | Dừng nhận trang mới; lưu checkpoint theo giao dịch |
| Xử lý nhiều bản ghi | Trước từng bản ghi hoặc nhóm nhỏ | Bỏ phần chưa bắt đầu; phục hồi bằng khóa nghiệp vụ |
| HTTP đến hệ thống ngoài | Trước gửi, trước retry và khi xử lý kết quả | Giới hạn timeout; đối soát kết quả bằng idempotency key |
| Phần việc chờ executor | Khi nhận khỏi hàng đợi và trước tác dụng phụ | Loại phần việc mang giấy phép cũ |
| Giao dịch cơ sở dữ liệu dài | Trước mở giao dịch và trước thao tác quan trọng | Chia nhỏ giao dịch; dùng kiểm tra quyền tại nơi ghi nếu cần |

Độ trễ dừng thực tế gồm:

~~~text
Thời gian phát hiện mất quyền
+ thời gian đưa sự kiện đến cổng
+ thời gian đến điểm kiểm tra tiếp theo
+ phần I/O không thể ngắt ngay.
~~~

Không thể đặt chu kỳ kiểm tra nhỏ rồi suy ra mọi tác vụ sẽ dừng ngay. Một batch có truy vấn không timeout vẫn có thể bị kẹt rất lâu.

Khi ứng dụng đóng bình thường, ưu tiên đóng cổng nhận việc, dừng producer hoặc scheduler riêng nếu có, yêu cầu hủy phần việc nền và chờ có giới hạn. Với mẫu đồng bộ trong bài, cổng đóng khiến vòng lặp thoát ở checkpoint tiếp theo; quá trình tắt scheduler do Spring quản lý. Nếu tự tạo executor, phải bổ sung quản lý vòng đời cho executor đó.

## 9. Giới hạn: cổng cục bộ không bảo đảm chỉ một bên ghi

Tình huống khó xuất hiện khi leader cũ không còn liên lạc với Kubernetes API nhưng vẫn liên lạc được cơ sở dữ liệu:

~~~text
A giữ quyền -> A bị mất kết nối điều phối hoặc bị pause.
B được cụm xác định là leader mới.
A chưa nhận được revoke hoặc tỉnh dậy với trạng thái cũ.
A và B đều có thể đi tới nơi ghi dữ liệu.
~~~

Tài liệu thư viện leader election của Kubernetes cũng nêu rằng bầu leader không tự cung cấp fencing. Đây là giới hạn thiết kế của mô hình điều phối cần được xét khi xây dựng nghiệp vụ; không phải khẳng định ứng dụng Java đang sử dụng thư viện Go. [Kubernetes client-go leader election](https://pkg.go.dev/k8s.io/client-go/tools/leaderelection).

Cổng trong bài chỉ đóng khi nhận tín hiệu mà nó được lập trình xử lý. Nó **không tự phát hiện mọi lần mất kết nối API**. Trước grant, trạng thái chưa biết bị từ chối; sau grant, nếu tín hiệu revoke không đến, trạng thái có thể bị cũ.

Ngay cả `event.getContext().isLeader()` trong triển khai 3.3.3 cũng kiểm tra thông tin leader do bộ điều khiển cục bộ giữ. Nó không phải một lần xác nhận quyền mới, nguyên tử với cơ sở dữ liệu, từ Kubernetes API. [LeaderContext 3.3.3](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/leader/LeaderContext.java).

Nếu nghiệp vụ yêu cầu dừng nhận việc khi độ tin cậy điều phối không còn đủ, cần thiết kế thêm tín hiệu tình trạng điều phối và chính sách đóng cổng, chẳng hạn từ một bộ giám sát có giới hạn thời gian rõ ràng. Không suy ra tín hiệu này từ việc Pod vẫn Running hoặc health HTTP vẫn trả 200. Chính sách đó vẫn cần kết hợp bảo vệ tại nơi tạo tác dụng phụ.

### Idempotency: lặp yêu cầu mà không lặp hiệu ứng

Với nghiệp vụ đối soát, có thể xác định khóa `job_key` từ ngày đối soát, tài khoản và loại thao tác. Khi phục hồi sau chuyển leader, công việc dùng lại cùng khóa.

Ví dụ ràng buộc dữ liệu:

~~~sql
CREATE TABLE reconciliation_effect (
    job_key VARCHAR(200) PRIMARY KEY,
    result_payload TEXT NOT NULL,
    completed_at TIMESTAMP NOT NULL
);
~~~

Trong một giao dịch, kiểm tra hoặc ghi khóa và cập nhật dữ liệu nghiệp vụ tương ứng. Nếu khóa đã được hoàn tất, trả lại kết quả trước đó theo quy ước. Không ghi dấu hoàn tất ở một giao dịch rồi tạo hiệu ứng ở giao dịch khác mà thiếu cơ chế phục hồi.

Với HTTP, gửi cùng idempotency key cho mọi lần thử của cùng thao tác, nếu hệ thống nhận hỗ trợ. Khi timeout khiến kết quả chưa rõ, truy vấn hoặc thử lại theo cùng khóa; không tạo khóa ngẫu nhiên mới cho mỗi lần retry. Nếu hệ thống đích không có khả năng chống trùng, phía gửi không thể chỉ dựa vào cổng leader để biến việc gửi thành exactly-once.

### Fencing: nơi ghi từ chối nhiệm kỳ cũ

Khi cần ngăn leader cũ ghi sau khi leader mới đã tiếp quản, nơi nhận thao tác phải kiểm tra một token nhiệm kỳ do cơ chế có thẩm quyền cấp. Token phải có thứ tự và phạm vi đúng với tài nguyên được bảo vệ.

Phác thảo cho cơ sở dữ liệu:

~~~text
Cơ chế cấp quyền có thẩm quyền đăng ký token hiện hành cho resource.
Mỗi phần việc mang token được cấp cho nhiệm kỳ của nó.

Trong cùng một giao dịch ghi:
  khóa dòng guard của resource;
  so sánh token của yêu cầu với token hiện hành;
  không khớp -> từ chối;
  khớp -> áp dụng thay đổi cùng khóa idempotency;
  commit rồi giải phóng khóa.
~~~

Việc thay token hiện hành cũng phải phối hợp qua cùng guard để không có khoảng đua giữa bước so sánh và bước ghi. Đây là phác thảo thiết kế, chưa phải một triển khai fencing hoàn chỉnh trong các lớp Java của bài.

Không dùng `generation` cục bộ làm token đó. Không coi `metadata.resourceVersion` của Kubernetes là số thứ tự nghiệp vụ để so sánh lớn/nhỏ. Cũng không cho một worker cũ tự xin token lớn hơn mỗi lần retry; việc cấp token phải gắn với quyền thực sự được xác lập bởi cơ chế có thẩm quyền.

Idempotency xử lý lặp cùng một thao tác; fencing xử lý yêu cầu từ nhiệm kỳ cũ. Hai cơ chế giải quyết hai câu hỏi khác nhau và có thể cần đi cùng nhau.

## 10. Theo dõi và xử lý sự cố

Nên tách ba nhóm tín hiệu:

- **Điều phối:** grant/revoke, lỗi gọi API, watch bị ngắt, thời gian chưa có leader.
- **Thực thi:** số batch đang chạy, số lần bỏ qua vì follower, số phần việc dừng do giấy phép cũ.
- **Nghiệp vụ:** checkpoint, thao tác bị loại do trùng khóa và yêu cầu bị từ chối vì token cũ.

Có thể theo dõi gauge leader cho từng Pod và role để nhận biết trạng thái ổn định. Số liệu metric được thu theo từng thời điểm khác nhau nên tổng gauge bằng một không phải bằng chứng toán học rằng không hề có thao tác ghi đồng thời.

| Hiện tượng | Khả năng cần kiểm tra | Hướng kiểm tra đầu tiên |
| --- | --- | --- |
| Không Pod nào chạy | Chưa Ready, sai role, thiếu ConfigMap hoặc thiếu quyền | Readiness, cấu hình thực tế, lỗi 403/404 |
| Cả hai Pod đều ghi log xử lý lâu dài | Mỗi Pod dùng khác nhóm điều phối hoặc tác vụ đi vòng qua cổng | Namespace, ConfigMap, role và mọi điểm vào nghiệp vụ |
| Có grant nhưng batch cũ tiếp tục sau revoke | Chỉ kiểm tra ở đầu batch hoặc không mang giấy phép | Các checkpoint và generation của phần việc |
| Được bầu lại làm công việc cũ chạy tiếp | Dùng boolean hoặc cấp giấy phép mới cho phần việc cũ | Giữ nguyên permit của batch |
| Chuyển quyền chậm | Readiness, watch, tải API hoặc tác vụ không dừng | Log theo thời gian và timeout I/O |
| API điều phối lỗi nhưng vẫn có log nghiệp vụ | Trạng thái leader cục bộ chưa bị thu hồi | Chính sách đóng cổng và bảo vệ tại nơi ghi |
| Mỗi lần retry tạo hiệu ứng mới | Khóa chống trùng không ổn định hoặc không được thực thi tại đích | Cách tạo job key và ranh giới giao dịch |

Trước khi đưa mẫu vào nghiệp vụ thật, cần xác định được bốn điều: mọi đường kích hoạt đều qua cổng; phần việc cũ giữ nguyên giấy phép; các đoạn chặn có timeout; và nơi tạo tác dụng phụ có chiến lược chống trùng hoặc chống ghi từ nhiệm kỳ cũ phù hợp.

Bài thực hành hoàn thành khi follower không nhận việc trước grant, giấy phép cũ mất hiệu lực sau revoke kể cả khi cùng Pod được bầu lại, và người triển khai giải thích được vì sao kết quả quan sát đó vẫn cần được bổ sung bằng bảo vệ dữ liệu cho thao tác không được phép lặp.
