# Kiểm thử leader failover và tác vụ chạy trùng

## 1. Mục tiêu và tình huống thực hành

Một dịch vụ Spring Boot có ba replica cùng chạy trên Kubernetes. Dịch vụ quét các hóa đơn đến hạn; chỉ replica giữ vai trò `billing-scheduler` được phát động một lượt xử lý. Khi replica đó dừng, một replica khác phải tiếp quản. Tuy nhiên, tác vụ đang chạy trên leader cũ có thể chưa kết thúc, trong khi leader mới đã bắt đầu thử lại cùng hóa đơn.

Bài học thuộc chương **Kiểm thử tự động** của module **SPRING_CLOUD_KUBERNETES**. Mục tiêu là kiểm chứng cả khả năng tiếp quản lẫn kết quả nghiệp vụ, thay vì suy ra tính đúng đắn từ số replica hoặc một dòng log “became leader”.

Sau bài học, bạn có thể:

- Phân biệt trạng thái của bản ghi bầu leader, quyền thực thi trong từng tiến trình và tác dụng đã ghi ở hệ thống đích.
- Thiết kế kiểm thử cho khởi động đồng thời, bàn giao có kiểm soát, dừng đột ngột, mất kết nối API và tác vụ cũ tiếp tục chạy.
- Xây dựng phép đo để phát hiện cả xử lý trùng và bỏ sót công việc.
- Dùng idempotency và giao dịch để giữ đúng kết quả khi một công việc được thử nhiều lần.
- Tách kiểm thử logic ứng dụng khỏi kiểm thử RBAC, readiness và cạnh tranh trên Kubernetes thật.

Trong phạm vi module, DiscoveryClient và Spring Cloud LoadBalancer phục vụ tìm kiếm, chọn đích gọi; ConfigMap và Secret cung cấp cấu hình; Configuration Watcher hỗ trợ phản ứng với thay đổi cấu hình. Những thành phần này không tự quyết định replica nào được chạy một tác vụ nền. Chỉ bật thành phần cần dùng cho bài thử, để lỗi của discovery hay tải cấu hình không che khuất lỗi điều phối leader.

## 2. Chọn rõ cơ chế bầu leader trước khi viết test

### 2.1. Nhánh ví dụ dùng trong bài

Các đoạn cấu hình và Java bên dưới dùng **cơ chế Fabric8 với ConfigMap của Spring Cloud Kubernetes 3.3.x**, lấy 3.3.3 làm mốc đối chiếu API. Cơ chế này phát sự kiện Spring Integration `OnGrantedEvent` và `OnRevokedEvent`. Dependency tương ứng là `spring-cloud-kubernetes-fabric8-leader`. [Tài liệu leader election 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/leader-election.html)

Giả định đã có ứng dụng Spring Boot và Spring Cloud BOM tương thích với nhánh đã chọn. Không tự ghép số phiên bản riêng cho Fabric8, Spring Integration và Spring Cloud Kubernetes.

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-kubernetes-fabric8-leader</artifactId>
</dependency>
~~~

Các ví dụ dùng thêm Spring Boot Actuator, Spring JDBC, PostgreSQL, JUnit Jupiter và Awaitility ở những lớp tương ứng. Phần mã minh họa trình bày các thành phần cần ghép vào ứng dụng thử nghiệm; đây không phải một dự án đã đóng gói sẵn.

Tài liệu ở các nhánh mới có thể mô tả thêm chế độ election với Lease và nhóm sự kiện khác. Khi chuyển chế độ, phải thay cả cấu hình, listener, RBAC, cách đọc bản ghi và phép đo timeout. Không đưa tham số `leaseDuration` hoặc `renewDeadline` vào ví dụ ConfigMap này rồi kỳ vọng chúng điều khiển failover. [Tài liệu các cơ chế leader election](https://docs.spring.io/spring-cloud-kubernetes/reference/leader-election.html)

### 2.2. Điều gì cần được quan sát?

Có ba lớp thông tin riêng biệt:

| Lớp | Ví dụ bằng chứng | Điều chưa thể kết luận |
| --- | --- | --- |
| Bản ghi điều phối | ConfigMap ghi Pod A cho role đang thử | Tiến trình B đã ngừng mọi tác vụ cũ |
| Trạng thái cục bộ | A nhận granted, B nhận revoked | Một lệnh ghi của B đã gửi đi có bị hủy hay chưa |
| Hệ thống đích | Hóa đơn X có đúng một kết quả đã commit | Chỉ có một lần thử xử lý X |

Với cùng role, các replica phải dùng chung namespace và tên ConfigMap. Nếu mỗi replica trỏ tới một ConfigMap khác nhau, chúng đang tham gia các cuộc bầu chọn khác nhau và đều có thể trở thành leader.

Trong implementation được chọn, việc kiểm tra Pod Ready tham gia vào quyết định giữ hoặc giành vai trò leader. Trạng thái readiness và quyền đọc/watch Pod vì vậy nằm trong phạm vi kiểm thử. Đây là hành vi cụ thể của implementation, không phải quy tắc chung rằng mọi cơ chế leader election đều dựa vào readiness. [Mã Fabric8LeadershipController 3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-fabric8-leader/src/main/java/org/springframework/cloud/kubernetes/fabric8/leader/Fabric8LeadershipController.java)

### 2.3. Leader election không phải bảo đảm exactly-once

Một cửa sổ lỗi điển hình:

~~~mermaid
sequenceDiagram
    participant A as Pod A - leader cũ
    participant K as Kubernetes API
    participant B as Pod B
    participant D as Cơ sở dữ liệu
    A->>D: Chuẩn bị xử lý hóa đơn X
    Note over A: Tạm dừng lâu hoặc mất liên lạc
    B->>K: Được công nhận là leader mới
    B->>D: Thử ghi kết quả cho X
    Note over A: Tác vụ cũ tiếp tục chạy
    A->>D: Cũng thử ghi kết quả cho X
    Note over D: Phải nhận diện cùng khóa nghiệp vụ
~~~

Sơ đồ mô tả một tình huống cần kiểm thử, không khẳng định cứ mất mạng là implementation ConfigMap lập tức bầu được leader mới.

Một bộ bầu chọn không tự chặn mọi yêu cầu từ tiến trình từng là leader tại nơi lưu dữ liệu. Tài liệu thư viện leader election của Kubernetes cũng nêu rõ giới hạn về fencing. Với ứng dụng Java trong bài, đây là lý do cần kiểm thử trực tiếp nơi phát sinh tác dụng, chứ không phải bằng chứng rằng ứng dụng đang dùng thư viện Go đó. [Giới hạn fencing trong client-go](https://pkg.go.dev/k8s.io/client-go/tools/leaderelection)

## 3. Xác định tiêu chí đạt trước khi gây lỗi

### 3.1. Safety, liveness và tính đầy đủ

Gọi `k` là một khóa công việc hợp lệ, chẳng hạn `invoice:INV-042:2026-11`.

- **Safety:** số tác dụng đã commit cho `k` không vượt quá một.
- **Liveness:** khi còn ứng viên khỏe, đủ quyền và liên lạc với API được, hệ thống tiếp tục xử lý trong thời hạn đã đặt.
- **Tính đầy đủ:** khi kết thúc bài thử, mọi khóa đầu vào đều có đúng một kết quả mong đợi.

Có thể viết:

~~~text
Trong khi chạy:    committed_effects(k) <= 1
Khi hoàn tất:      committed_effects(k) == 1, với mọi k trong tập đầu vào
Sau khi gây lỗi:   có bằng chứng tiến triển trước deadline của bài thử
~~~

`attempts(k) > 1` có thể là kết quả đúng của một phép thử retry. Phải báo riêng số lần thử, số lần bị từ chối do trùng và số tác dụng thành công.

### 3.2. Đo hai mốc failover

Dùng đồng hồ đơn điệu của test runner để đo:

~~~text
T_election = thời điểm quan sát granted ở ứng viên mới - thời điểm gây lỗi
T_progress = thời điểm kết quả mới xuất hiện ở đích - thời điểm gây lỗi
~~~

Hai con số trả lời hai câu hỏi khác nhau: đã có leader mới chưa, và nghiệp vụ đã chạy tiếp chưa. Nếu leader mới không truy cập được cơ sở dữ liệu, `T_election` có thể tốt trong khi `T_progress` không đạt.

Với ConfigMap trong bài, ngân sách thời gian cần tính đến phát hiện Pod lỗi/không Ready, watch hoặc lần kiểm tra kế tiếp, độ trễ API và lịch chạy tác vụ. Với cơ chế Lease khác, còn phải tính quy tắc hết hạn và gia hạn của chính cơ chế đó. Không dùng một timeout ngắn cho mọi loại lỗi.

Ví dụ nhóm tự đặt mục tiêu phòng lab là hội tụ leader trong 60 giây và hoàn thành 20 khóa công việc trong 90 giây trên cluster đã khởi động sẵn. Đây là ngưỡng kiểm thử do nhóm chọn, không phải cam kết của Spring Cloud Kubernetes.

## 4. Dựng môi trường để lỗi có thể tái hiện

### 4.1. Cấu hình ứng dụng thử nghiệm

Các giá trị sau dành cho môi trường test:

~~~yaml
spring:
  application:
    name: billing-worker
  cloud:
    kubernetes:
      config:
        enabled: false
      secrets:
        enabled: false
      discovery:
        enabled: false
      leader:
        enabled: true
        role: billing-scheduler
        namespace: ${POD_NAMESPACE}
        config-map-name: billing-leader
        create-config-map: false
        update-period: 2s

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
~~~

`update-period: 2s` giúp rút ngắn vòng kiểm tra trong phòng lab; cần đo tải API và độ ổn định trước khi áp dụng ở môi trường triển khai. Thuộc tính này là chu kỳ kiểm tra trạng thái trong nhánh ConfigMap, không phải thời hạn một Lease. [LeaderProperties 3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/leader/LeaderProperties.java)

Các cờ tắt phía trên dành cho bộ nạp cấu hình qua Kubernetes API. Nếu cấu hình JDBC được đưa vào Pod bằng biến môi trường từ Secret, Kubernetes vẫn có thể thực hiện việc đó. Ứng dụng không cần tự gọi API đọc Secret cho cách cấp cấu hình này.

Không thêm starter DiscoveryClient, LoadBalancer hoặc triển khai Configuration Watcher vào fixture chỉ để có bầu leader. Nếu ứng dụng thật có các tính năng ấy, thêm lại theo từng bài thử riêng sau khi phép thử leader cơ bản hoạt động.

### 4.2. Namespace, ServiceAccount và quyền ứng dụng

Mỗi lần chạy integration test tạo một namespace riêng, ví dụ `leader-it-<run-id>`. Manifest dưới đây dùng tên cụ thể `leader-it-demo` để dễ đọc; harness phải thay **mọi** chỗ mang namespace này khi chạy đồng thời.

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: leader-it-demo
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: billing-worker
  namespace: leader-it-demo
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: billing-leader
  namespace: leader-it-demo
data: {}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: billing-leader
  namespace: leader-it-demo
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["billing-leader"]
    verbs: ["get", "update"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: billing-leader
  namespace: leader-it-demo
subjects:
  - kind: ServiceAccount
    name: billing-worker
    namespace: leader-it-demo
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: billing-leader
~~~

Test runner tạo ConfigMap trước khi chạy ứng dụng; vì vậy ứng dụng dùng `create-config-map: false` và không có quyền tạo ConfigMap. Không thể dùng `resourceNames` để giới hạn một yêu cầu tạo tài nguyên cấp cao nhất theo tên. Cấp quyền đọc/watch Pod trong namespace thử nghiệm phục vụ kiểm tra trạng thái ứng viên. [Quy tắc resourceNames của Kubernetes RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)

Danh tính chạy test runner và ServiceAccount của ứng dụng phải tách biệt. Runner có quyền dựng fixture, đọc bằng chứng, gây lỗi và thu dọn namespace; ứng dụng chỉ có quyền hoạt động đã nêu. Test chạy dưới kubeconfig quản trị có thể che mất lỗi RBAC nếu chính ứng dụng cũng vô tình dùng danh tính đó.

ConfigMap khóa bầu chọn không dùng chung với ConfigMap chứa cấu hình nghiệp vụ. Không gắn nhãn theo dõi cấu hình cho khóa nếu Configuration Watcher của hệ thống có thể phản ứng với các cập nhật trên nó.

### 4.3. Ba replica và danh tính phục vụ đối chiếu

Phần Pod template cần có:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: billing-worker
  namespace: leader-it-demo
spec:
  replicas: 3
  selector:
    matchLabels:
      app: billing-worker
  template:
    metadata:
      labels:
        app: billing-worker
    spec:
      serviceAccountName: billing-worker
      terminationGracePeriodSeconds: 20
      containers:
        - name: app
          image: YOUR_REGISTRY/billing-worker:leader-it
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
            - name: SPRING_DATASOURCE_URL
              valueFrom:
                secretKeyRef:
                  name: billing-db
                  key: url
            - name: SPRING_DATASOURCE_USERNAME
              valueFrom:
                secretKeyRef:
                  name: billing-db
                  key: username
            - name: SPRING_DATASOURCE_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: billing-db
                  key: password
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 2
            failureThreshold: 60
~~~

Thay image bằng bản đã build từ ứng dụng thử nghiệm. Trước khi apply Deployment, fixture phải cung cấp PostgreSQL, schema và Secret `billing-db` với ba khóa tương ứng; database phải truy cập được từ cả ba Pod. Các đoạn manifest không tự tạo database hay image.

Readiness ở đây phản ánh khả năng phục vụ của tiến trình, độc lập với việc đang là follower hay leader. Nếu bắt follower báo NotReady chỉ vì chưa là leader, implementation cần Pod Ready để tranh cử có thể không có ứng viên hợp lệ. Liveness cũng không được thất bại chỉ vì replica không giữ vai trò leader.

Ghi Pod name, UID và một `process_id` sinh lúc ứng dụng khởi động. UID phân biệt Pod thay thế; `process_id` phân biệt hai lần JVM khởi động lại trong cùng Pod. Một container restart có thể giữ nguyên Pod UID. [Vòng đời và danh tính Pod](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)

## 5. Cửa kiểm soát tác vụ trong ứng dụng

### 5.1. Cấp quyền theo một thế hệ cục bộ

Boolean `isLeader` có một lỗi dễ bỏ sót: tác vụ lấy giá trị `true`, replica mất quyền rồi lại giành quyền; tác vụ cũ thấy `true` lần nữa và chạy tiếp. Dùng thế hệ cục bộ để phân biệt hai nhiệm kỳ:

~~~java
import java.util.Optional;

public final class LeadershipGate {

    public record Permit(long generation) {}

    private long generation;
    private boolean leading;

    public synchronized void grant() {
        if (!leading) {
            generation++;
            leading = true;
        }
    }

    public synchronized void revoke() {
        leading = false;
        generation++;
    }

    public synchronized Optional<Permit> acquire() {
        return leading
                ? Optional.of(new Permit(generation))
                : Optional.empty();
    }

    public synchronized boolean accepts(Permit permit) {
        return permit != null
                && leading
                && permit.generation() == generation;
    }
}
~~~

`generation` chỉ có ý nghĩa trong một tiến trình. Nó không phải fencing token toàn cluster, không lưu thứ tự các leader giữa các Pod và không được dùng làm khóa chống trùng nghiệp vụ.

### 5.2. Nối sự kiện Spring vào gate

Đăng ký `LeadershipGate` thành một bean singleton. Listener dưới đây dùng đúng nhóm sự kiện của nhánh đã chọn:

~~~java
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.integration.leader.event.OnGrantedEvent;
import org.springframework.integration.leader.event.OnRevokedEvent;
import org.springframework.stereotype.Component;

@Component
public class BillingLeadershipEvents {

    private static final String ROLE = "billing-scheduler";
    private final LeadershipGate gate;

    public BillingLeadershipEvents(LeadershipGate gate) {
        this.gate = gate;
    }

    @EventListener
    public void onGranted(OnGrantedEvent event) {
        if (ROLE.equals(event.getRole())) {
            gate.grant();
        }
    }

    @EventListener
    public void onRevoked(OnRevokedEvent event) {
        if (ROLE.equals(event.getRole())) {
            gate.revoke();
        }
    }

    @EventListener
    public void onClosed(ContextClosedEvent event) {
        gate.revoke();
    }
}
~~~

Listener chỉ cập nhật trạng thái ngắn gọn. Không chạy vòng batch dài trong callback, không thêm `@Async` khiến thứ tự xử lý granted/revoked bị thay đổi. Nếu ứng dụng đã tùy biến bộ phát sự kiện bất đồng bộ, phải kiểm thử và thiết kế lại việc tuần tự hóa các chuyển trạng thái.

Trước khi nhận việc mới và trước mỗi ranh giới ghi, tác vụ kiểm tra permit đã lấy. Sau khi mất quyền, dừng lấy thêm việc, yêu cầu hủy tác vụ đang chờ và đặt timeout hữu hạn cho I/O. Hủy `Future` hoặc ngắt thread không bảo đảm một lệnh ghi đã đến đích sẽ bị thu hồi.

Ngay cả đoạn `if (gate.accepts(permit)) { write(); }` vẫn có khoảng đua giữa kiểm tra và ghi. Gate giảm công việc không cần thiết; lớp bảo vệ tại hệ thống đích mới xử lý các yêu cầu trùng còn lọt qua.

## 6. Bảo vệ kết quả bằng khóa nghiệp vụ và giao dịch

### 6.1. Fixture dữ liệu

Dùng cùng một PostgreSQL thật cho mọi replica trong integration test. Mỗi lần chạy có `run_id` riêng để cô lập dữ liệu thử:

~~~sql
CREATE TABLE expected_task (
    run_id UUID NOT NULL,
    task_key TEXT NOT NULL,
    PRIMARY KEY (run_id, task_key)
);

CREATE TABLE execution_ledger (
    run_id UUID NOT NULL,
    task_key TEXT NOT NULL,
    pod_uid TEXT NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (run_id, task_key)
);

CREATE TABLE billing_effect (
    effect_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id UUID NOT NULL,
    task_key TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
~~~

Harness tạo trước tập `expected_task`, ví dụ 20 hóa đơn, rồi mới mở cho scheduler xử lý. Worker quét lại các khóa chưa hoàn tất; nếu JVM chết giữa chừng, công việc vẫn còn trong database. Không chỉ để danh sách công việc trong RAM của leader.

Trong fixture này, `billing_effect` cố ý không có unique constraint theo `task_key`, để phép thử có thể phát hiện lỗi nếu code bỏ qua ledger. Đây là mô hình tác dụng để kiểm thử; hệ thống thật nên áp dụng thêm ràng buộc nghiệp vụ phù hợp ở bảng đích.

`run_id` phục vụ cô lập phép thử. Trong hệ thống thật, idempotency key phải tồn tại qua các lần triển khai và retry, thường là tổ hợp mã hóa đơn, kỳ tính tiền và loại thao tác. Không sinh khóa mới theo Pod, lần granted hoặc lần gọi HTTP.

### 6.2. Giành quyền ghi và tạo tác dụng trong cùng transaction

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BillingWriter {

    private final JdbcTemplate jdbc;

    public BillingWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean applyOnce(UUID runId, String taskKey,
                             String podUid, BigDecimal amount) {
        int inserted = jdbc.update("""
                INSERT INTO execution_ledger(run_id, task_key, pod_uid)
                VALUES (?, ?, ?)
                ON CONFLICT (run_id, task_key) DO NOTHING
                """, runId, taskKey, podUid);

        if (inserted == 0) {
            return false;
        }

        jdbc.update("""
                INSERT INTO billing_effect(run_id, task_key, amount)
                VALUES (?, ?, ?)
                """, runId, taskKey, amount);

        return true;
    }
}
~~~

Caller gọi `BillingWriter` qua Spring bean được quản lý; không tự `new` và không dựa vào self-invocation để có transaction. Cả hai câu lệnh dùng cùng datasource, transaction manager và transaction.

Với unique key của ledger, hai transaction cạnh tranh cùng khóa không cùng được quyền tạo tác dụng. Nếu lệnh ghi tác dụng thất bại, exception phải thoát ra để transaction rollback cả ledger. `ON CONFLICT DO NOTHING` là cơ chế PostgreSQL dùng để xử lý xung đột ở câu lệnh insert này. [PostgreSQL INSERT](https://www.postgresql.org/docs/current/sql-insert.html)

Không bắt exception rồi trả về thành công. Không commit ledger trước, sau đó mới ghi kết quả trong transaction khác: tiến trình có thể chết ở giữa, làm retry tưởng công việc đã hoàn tất dù chưa có tác dụng.

Mẫu trên chỉ bảo vệ tác dụng nằm trong **cùng database transaction**. Nếu tác dụng là gửi email, gọi cổng thanh toán hoặc publish sang hệ thống khác, cần idempotency ở bên nhận hoặc thiết kế outbox cùng cơ chế khử trùng phù hợp. Việc ghi một dòng ledger không làm một HTTP request ngoài transaction trở thành exactly-once.

## 7. Kiểm thử nhanh trước khi lên cluster

### 7.1. Kiểm thử gate mà không cần Kubernetes

Các test sau dùng JUnit Jupiter và kiểm tra hợp đồng mà scheduler cần dựa vào:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class LeadershipGateTest {

    @Test
    void followerCannotAcquireWork() {
        var gate = new LeadershipGate();

        assertTrue(gate.acquire().isEmpty());
    }

    @Test
    void revocationInvalidatesAnExistingPermit() {
        var gate = new LeadershipGate();
        gate.grant();
        var permit = gate.acquire().orElseThrow();

        gate.revoke();

        assertFalse(gate.accepts(permit));
        assertTrue(gate.acquire().isEmpty());
    }

    @Test
    void aNewTermDoesNotReviveAnOldTask() {
        var gate = new LeadershipGate();
        gate.grant();
        var oldPermit = gate.acquire().orElseThrow();

        gate.revoke();
        gate.grant();
        var newPermit = gate.acquire().orElseThrow();

        assertFalse(gate.accepts(oldPermit));
        assertTrue(gate.accepts(newPermit));
    }
}
~~~

Bổ sung test cho adapter sự kiện: granted đúng role mở gate, revoked đúng role đóng gate, sự kiện của role khác không đổi trạng thái. Các test này phát hiện lỗi nối logic ứng dụng nhưng chưa chứng minh có bầu chọn thật, đủ RBAC hoặc có failover.

Để thử tác vụ đang chạy, đặt một barrier sau khi lấy permit, phát revoked rồi mới cho tác vụ tiếp tục. Xác nhận nó không lấy thêm việc và không đi vào ranh giới ghi nếu đang kiểm tra lại permit. Đây là cách tạo thứ tự thực thi xác định, thay vì hy vọng một `sleep` ngẫu nhiên sẽ trúng khoảng đua.

### 7.2. Cho hai caller cạnh tranh ghi cùng công việc

Đặt đoạn test sau trong lớp integration test đã inject `BillingWriter writer` và `JdbcTemplate jdbc`, khởi tạo schema trên PostgreSQL thật. Có thể dùng PostgreSQL do fixture CI cung cấp hoặc một container riêng cho lớp test.

Không đặt toàn bộ phương thức test trong `@Transactional`: hai thread cần thấy dữ liệu đã commit, và mỗi lần gọi service cần transaction riêng. Connection pool phải đủ cho hai lời gọi đồng thời.

~~~java
@Test
void twoAttemptsCommitOnlyOneEffect() throws Exception {
    UUID runId = UUID.randomUUID();
    String key = "invoice:INV-042:2026-11";

    jdbc.update("""
            INSERT INTO expected_task(run_id, task_key) VALUES (?, ?)
            """, runId, key);

    var ready = new java.util.concurrent.CountDownLatch(2);
    var start = new java.util.concurrent.CountDownLatch(1);
    var pool = java.util.concurrent.Executors.newFixedThreadPool(2);

    try {
        java.util.concurrent.Callable<Boolean> attempt = () -> {
            ready.countDown();
            if (!start.await(10, java.util.concurrent.TimeUnit.SECONDS)) {
                throw new IllegalStateException("Không nhận được tín hiệu bắt đầu");
            }
            return writer.applyOnce(
                    runId, key, "pod-test",
                    new java.math.BigDecimal("100.00"));
        };

        var first = pool.submit(attempt);
        var second = pool.submit(attempt);

        assertTrue(ready.await(10, java.util.concurrent.TimeUnit.SECONDS));
        start.countDown();

        var outcomes = java.util.List.of(
                first.get(20, java.util.concurrent.TimeUnit.SECONDS),
                second.get(20, java.util.concurrent.TimeUnit.SECONDS));

        assertEquals(1L, outcomes.stream().filter(Boolean::booleanValue).count());
        assertEquals(Integer.valueOf(1), jdbc.queryForObject("""
                SELECT count(*)::integer FROM billing_effect
                WHERE run_id = ? AND task_key = ?
                """, Integer.class, runId, key));
    }
    finally {
        start.countDown();
        pool.shutdownNow();
        assertTrue(pool.awaitTermination(
                10, java.util.concurrent.TimeUnit.SECONDS));
    }
}
~~~

Thêm test cho trường hợp transaction thất bại sau khi insert ledger: dùng hook chỉ có trong test để ném exception trước khi ghi effect; sau đó xác nhận cả ledger lẫn effect đều chưa commit. Bỏ hook rồi retry cùng khóa phải tạo được đúng một effect.

Test cạnh tranh database cố ý gọi writer từ hai phía, không qua gate. Nó kiểm chứng lớp bảo vệ cuối khi giả định “chỉ leader gọi writer” bị phá vỡ.

## 8. Xây dựng harness kiểm thử trên Kubernetes thật

### 8.1. Hợp đồng quan sát

Harness có thể dùng Kubernetes client hoặc lệnh `kubectl` và gọi trực tiếp từng Pod bằng port-forward. Không đọc trạng thái leader bằng một request duy nhất qua Service, DiscoveryClient hay LoadBalancer: kết quả đó chỉ phản ánh replica được chọn cho request ấy.

Mỗi Pod cần cung cấp bằng chứng chẩn đoán từ profile thử nghiệm hoặc một kênh quan sát tương đương:

| Trường | Mục đích |
| --- | --- |
| namespace, pod_name, pod_uid, process_id | Xác định đúng tiến trình |
| role, leading, local_generation | Đối chiếu quyền thực thi cục bộ |
| granted_count, revoked_count | Nhận diện chuỗi chuyển vai trò |
| run_id, task_key, attempt_id | Nối lần thử với công việc |
| outcome | Phân biệt committed, duplicate_rejected, failed, cancelled |

Có thể dùng Actuator info của nhánh thư viện để hỗ trợ đối chiếu, nhưng dữ liệu gate và kết quả nghiệp vụ vẫn phải được quan sát riêng. Những trường ở bảng trên là hợp đồng do ứng dụng thử nghiệm xây dựng, không phải toàn bộ đều có sẵn trong endpoint của Spring Cloud Kubernetes.

Nếu tạo endpoint điều khiển barrier hoặc gây lỗi, chỉ bật trong profile kiểm thử và giới hạn quyền truy cập. Không đưa các endpoint ấy vào image triển khai thông thường.

Runner giữ một dòng thời gian gồm lúc gây lỗi, trạng thái từng Pod, sự kiện ứng dụng và kết quả đã commit. Dùng thứ tự/barrier và đồng hồ đơn điệu ở runner cho phép đo; không suy ra thứ tự tuyệt đối giữa các máy chỉ từ timestamp trong log.

### 8.2. Quy trình một lần chạy

1. Sinh `run_id`, namespace và tập khóa nghiệp vụ cố định.
2. Tạo database fixture hoặc vùng dữ liệu riêng, schema và cấu hình kết nối.
3. Tạo ServiceAccount, Role, RoleBinding và ConfigMap khóa.
4. Khởi động ba replica; chờ chúng Ready và quan sát được từ runner.
5. Chờ hội tụ một leader; đối chiếu ConfigMap với danh tính Pod thực tế.
6. Mở tập công việc và đặt barrier tại điểm cần gây lỗi.
7. Gây đúng một loại lỗi, xác nhận lỗi đã có hiệu lực, rồi quan sát phục hồi.
8. Đợi hoàn tất đầu vào, kiểm tra các truy vấn dữ liệu và theo dõi thêm một khoảng ổn định.
9. Thu bằng chứng trước khi thu dọn tài nguyên của lần chạy.

Không chạy các ca sửa RBAC, thay readiness và xóa Pod song song trong cùng namespace. Chúng có thể thay đổi điều kiện mà ca khác đang đo.

### 8.3. Chờ theo điều kiện và theo khoảng quan sát

Ví dụ Awaitility cho các điều kiện cuối cùng:

~~~java
await().atMost(java.time.Duration.ofSeconds(60))
       .pollInterval(java.time.Duration.ofMillis(250))
       .untilAsserted(() -> {
           var states = fixture.readAllPodStates();
           assertEquals(3, states.size());
           assertEquals(1L,
                   states.stream().filter(PodState::leading).count());
       });

await().atMost(java.time.Duration.ofSeconds(90))
       .pollInterval(java.time.Duration.ofMillis(500))
       .untilAsserted(() -> {
           assertEquals(0, fixture.countMissingOrDuplicateEffects(runId));
       });
~~~

Đây là **mã điều phối minh họa**: `fixture`, `PodState` và các hàm đọc là adapter của bộ test cần được triển khai, không phải API sẵn có của Spring Cloud Kubernetes. Khi đọc Pod, adapter phải kiểm tra danh sách Pod mong đợi và báo lỗi nếu không truy cập được một Pod đang tồn tại; không âm thầm bỏ qua replica không trả lời.

Một lần đọc thấy “một leader” chưa chứng minh trạng thái ổn định. Sau khi hội tụ, tiếp tục lấy mẫu trong một cửa sổ, chẳng hạn 10 giây của phòng lab, đồng thời quan sát các lần thử và tác dụng. Việc lấy mẫu ba Pod không diễn ra nguyên tử và vẫn có thể bỏ lỡ khoảng chồng lấn ngắn. Vì vậy dữ liệu ở đích là phép kiểm bắt buộc.

Không dùng `Thread.sleep(5000)` rồi assert một lần. Cách đó vừa làm test chậm khi hệ thống đã sẵn sàng, vừa thất bại giả khi CI chậm. Polling cần deadline, thông báo lỗi có ngữ cảnh và không được nuốt lỗi xác thực thành trạng thái “chưa có leader”.

## 9. Các kịch bản phải kiểm thử

| Kịch bản | Cách tạo tình huống | Bằng chứng chính |
| --- | --- | --- |
| Ba replica khởi động đồng thời | Cùng namespace, role, khóa điều phối | Hội tụ; đầu vào hoàn tất; effect không trùng |
| Bàn giao có kiểm soát | Dừng leader qua luồng shutdown bình thường | Dừng nhận việc mới; ứng viên khác tiếp quản |
| Dừng đột ngột | Dừng JVM mà không chạy callback shutdown | Còn tiến triển; retry không bỏ sót hoặc ghi trùng |
| Leader tạm không Ready | Làm probe kiểm thử thất bại | Hành vi bầu chọn và gate đúng với thiết kế |
| Mất kết nối Kubernetes API | Cắt đúng đường từ Pod tới API | Chứng minh lỗi mạng; quan sát hành vi thực tế |
| Leader cũ tiếp tục tác vụ | Barrier, chuyển quyền, rồi thả tác vụ cũ | Hai lần thử cùng khóa nhưng tối đa một effect |
| Thiếu quyền RBAC | Bỏ đúng quyền update khóa | Lỗi được thấy; ứng dụng không tự nhận quyền |
| Rolling update | Có Pod cũ và mới cùng tồn tại | Cùng miền bầu chọn; dữ liệu vẫn đúng |

### 9.1. Khởi động đồng thời

Cho ba replica tranh cùng role trước khi mở tập dữ liệu. Kiểm tra:

- Không dùng ba tên khóa hoặc ba namespace khác nhau do nội suy cấu hình sai.
- Leader được quan sát tồn tại trong tập Pod hiện tại.
- Follower không chủ động mở thêm vòng scheduler vì một cờ mặc định sai.
- Sau khi xử lý, mỗi khóa đầu vào có một effect và giá trị nghiệp vụ đúng.

Thử lại với tên ConfigMap khác trên một replica là **negative control**: bộ test phải chỉ ra cấu hình tạo hai miền bầu chọn hoặc thấy nhiều nơi tự nhận quyền. Không dựa riêng vào effect trùng để phát hiện, vì writer có idempotency vẫn có thể giữ effect đúng dù bầu chọn cấu hình sai.

### 9.2. Bàn giao có kiểm soát

Xác định leader bằng quan sát từng Pod, ghi lại Pod name, UID và process_id, rồi yêu cầu xóa Pod theo grace period bình thường:

~~~powershell
$testNamespace = 'leader-it-demo'
$leaderPodName = '<ten-pod-leader-da-xac-minh>'
kubectl delete pod $leaderPodName -n $testNamespace --wait=false
~~~

Chuỗi kiểm chứng cần có:

1. Leader cũ bắt đầu shutdown và ngừng nhận công việc mới.
2. Tác vụ đang chạy kết thúc hoặc bị hủy theo chính sách ứng dụng.
3. Một tiến trình khác nhận quyền và hoàn thành công việc còn lại.
4. Những khóa đã hoàn thành trước bàn giao không phát sinh effect thứ hai.

Không bắt buộc phải thấy `OnRevokedEvent` trong mọi luồng kết thúc tiến trình. Ứng dụng còn có thể đóng gate theo sự kiện đóng context; hành vi chính cần xác minh là ngừng nhận việc và tính đúng của kết quả.

Nếu chỉ thử yield mà tiến trình cũ vẫn là ứng viên khỏe, nó có thể giành lại quyền. Ca bắt buộc “Pod khác tiếp quản” nên loại ứng viên cũ khỏi cuộc bầu chọn, thay vì coi việc cùng Pod được bầu lại là lỗi thư viện.

### 9.3. Dừng đột ngột

Đặt barrier sau khi leader đã nhận một khóa nhưng trước commit. Dừng JVM theo cơ chế fault injection của cluster test; xác minh tiến trình thực sự đã dừng. Sau đó chờ ứng viên sống tiếp quản và retry khóa ấy.

Không coi `kubectl delete pod --force --grace-period=0` là bằng chứng đủ rằng tiến trình trên node đã chết. Việc xóa cưỡng bức đối tượng API và xác nhận dừng tiến trình là hai việc cần phân biệt, nhất là khi node mất liên lạc. Khi dùng thao tác này trong lab, harness vẫn phải xác minh trạng thái runtime. [Quá trình kết thúc Pod](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)

Phân biệt hai kiểu phục hồi:

- Container restart trong cùng Pod có thể giữ UID và danh tính ứng viên theo Pod name.
- Deployment thay Pod tạo một UID mới.

Nếu yêu cầu bài thử là một Pod khác tiếp quản, cần fixture bảo đảm tiến trình cũ không quay lại tranh cử trước khi quan sát người tiếp quản. Nếu chỉ thử container restart, tiêu chí hợp lệ có thể là tiến trình mới tiếp tục công việc; không ép nó phải có Pod UID khác.

Tại đây, mất callback revoked là tình huống bình thường. Nếu tính an toàn chỉ tồn tại khi callback luôn chạy, thiết kế chưa chịu được crash.

### 9.4. Mất kết nối Kubernetes API

Cắt đường từ **Pod được chọn** tới Kubernetes API, đồng thời giữ kết nối từ Pod đó tới PostgreSQL và kênh quan sát cần thiết. Dùng công cụ fault injection, proxy hoặc cơ chế mạng mà môi trường kiểm thử đã kiểm chứng.

NetworkPolicy chỉ có hiệu lực nếu CNI hỗ trợ và cho phép mô phỏng đúng đường cần cắt. Nếu fixture không thể tạo lỗi mạng như mô tả, báo ca này bị chặn; không đánh dấu pass chỉ vì đã apply một manifest policy.

Trước khi đánh giá ứng dụng, chứng minh:

- Request API từ đúng Pod thất bại hoặc timeout.
- Request từ các ứng viên còn lại vẫn hoạt động.
- Pod bị cô lập vẫn chạy và vẫn có thể kết nối hệ thống đích nếu đó là giả định của ca.
- Runner không vô tình cắt chính đường quan sát của mình.

Với ConfigMap 3.3.x trong bài, **không có TTL Lease để dựa vào**. Một Pod mất kết nối API nhưng vẫn Ready trong góc nhìn các ứng viên khác có thể chưa bị thay thế. Không đặt assert “sau 15 giây chắc chắn có leader mới”. Cần ghi rõ hợp đồng vận hành mà nhóm muốn đạt và quan sát implementation có đáp ứng không.

Nếu yêu cầu triển khai là ngừng ghi khi không thể xác nhận quyền, cần một thiết kế fail-closed đã được triển khai và kiểm thử, hoặc chọn cơ chế điều phối phù hợp hơn. Ví dụ gate ở mục 5 chỉ phản ứng với sự kiện cục bộ; bản thân nó không có bộ phát hiện mất liên lạc API.

Một ca tiếp theo có thể đưa leader cũ sang NotReady bằng probe thử nghiệm, để các ứng viên khỏe có cơ sở chuyển quyền theo implementation đã chọn. Hãy ghi rõ đây là **hai sự kiện lỗi**, không trình bày kết quả như chỉ mất mạng đã đủ gây failover.

### 9.5. Cho tác vụ của leader cũ chạy tiếp sau chuyển quyền

Đây là ca quan trọng để phân biệt kiểm thử bầu chọn với kiểm thử an toàn nghiệp vụ:

1. Pod A đang là leader lấy khóa `k`.
2. Test hook giữ tác vụ A tại barrier ngay trước lời gọi writer, sau lần kiểm tra permit cuối cùng.
3. Làm A không còn là ứng viên hợp lệ theo kịch bản đã chọn; chờ B được công nhận làm leader.
4. B thử xử lý `k`. Giữ tập đầu vào cố định để cả hai phía có thể nhắm cùng khóa.
5. Thả barrier của A trong khi A vẫn còn sống.
6. Đợi cả hai lời gọi kết thúc, rồi kiểm tra đúng một effect cho `k`.

Đặt barrier sau kiểm tra permit là có chủ ý: ca này mô phỏng khoảng đua mà gate không thể tự loại bỏ. Có thể A ghi trước hoặc B ghi trước; không buộc một Pod cụ thể phải thắng. Phải thấy ít nhất hai lần thử cùng khóa và chỉ một tác dụng đã commit.

Nếu tạo race bằng cách gọi trực tiếp writer từ hai Pod, hãy ghi nhãn đó là phép thử chống trùng ở biên ghi. Nó không thay thế ca chuyển quyền đầy đủ.

Nếu lỗi mới chỉ dừng A rồi B xử lý, bạn đã thử recovery sau crash; bạn chưa thử được tác vụ cũ và mới cùng có cơ hội ghi.

### 9.6. RBAC và khóa không tồn tại

Với cấu hình `create-config-map: false`, chạy một ca không tạo ConfigMap trước. Kỳ vọng không có granted hợp lệ và không có effect; bằng chứng phải giải thích rõ thiếu khóa điều phối.

Một ca khác giữ quyền đọc nhưng bỏ `update` trên `billing-leader`. Ứng viên không được tự mở gate chỉ vì đọc được ConfigMap hoặc vì Pod đã Ready. Cần thu được dấu hiệu request bị từ chối và xác nhận không có kết quả nghiệp vụ.

Kiểm tra trước quyền bằng danh tính ứng dụng:

~~~powershell
$testNamespace = 'leader-it-demo'
$subjectName = "system:serviceaccount:${testNamespace}:billing-worker"

kubectl auth can-i get configmap/billing-leader -n $testNamespace --as=$subjectName
kubectl auth can-i update configmap/billing-leader -n $testNamespace --as=$subjectName
kubectl auth can-i watch pods -n $testNamespace --as=$subjectName
kubectl auth can-i list secrets -n $testNamespace --as=$subjectName
~~~

Trong fixture này, ba kiểm tra đầu phải được cho phép và kiểm tra list Secret phải bị từ chối. Runner cần quyền impersonate để dùng `--as`; nếu không có, xác minh bằng một request thực tế chạy với ServiceAccount trong Pod. Không coi lỗi impersonation của runner là lỗi RBAC của ứng dụng.

Khi sửa lại quyền, cần kiểm chứng ứng dụng có thể phục hồi theo cơ chế retry/reconnect đã chọn, hoặc ghi nhận phải restart. Không mặc định quá trình phục hồi giống nhau ở mọi client và mọi loại lỗi.

### 9.7. Rolling update và cập nhật cấu hình

Cho rollout tạo thời điểm Pod mới và cũ cùng tồn tại. Tất cả phải giữ cùng namespace, role và tên khóa, đồng thời dùng cùng quy tắc idempotency.

Nếu một thay đổi ConfigMap/Secret hoặc Configuration Watcher làm ứng dụng restart, chạy thêm ca trong đó restart xảy ra giữa lượt xử lý. Nếu chỉ thay đổi tham số nghiệp vụ, xác định rõ công việc đang chạy dùng bản cấu hình cũ hay mới; ghi phiên bản cấu hình trong kết quả chẩn đoán.

Không đổi tên khóa bầu chọn giữa rollout rồi kỳ vọng hai nhóm vẫn phối hợp. Không tái tạo idempotency key từ phiên bản cấu hình hoặc lần khởi động, trừ khi nghiệp vụ thực sự xác định đó là công việc khác.

Việc refresh thuộc tính thông thường cũng không tự bảo đảm leader initiator được dựng lại với tên khóa mới. Những thay đổi hạ tầng điều phối cần đường triển khai và kiểm thử riêng.

## 10. Truy vấn phát hiện trùng, thiếu và kết quả ngoài đầu vào

Sau khi mọi lời gọi đã kết thúc hoặc hết deadline, kiểm tra các khóa thiếu hoặc có nhiều effect. Ví dụ dùng `:run_id` làm tham số bind của công cụ SQL hoặc test harness:

~~~sql
SELECT e.task_key, count(b.effect_id) AS effect_count
FROM expected_task e
LEFT JOIN billing_effect b
    ON b.run_id = e.run_id
   AND b.task_key = e.task_key
WHERE e.run_id = :run_id
GROUP BY e.task_key
HAVING count(b.effect_id) <> 1;
~~~

Kết quả phải rỗng. `LEFT JOIN` từ tập đầu vào giúp thấy cả khóa chưa có effect; chỉ group bảng kết quả sẽ không thấy công việc bị bỏ sót.

Kiểm tra effect không thuộc đầu vào:

~~~sql
SELECT b.task_key, count(*) AS effect_count
FROM billing_effect b
LEFT JOIN expected_task e
    ON e.run_id = b.run_id
   AND e.task_key = b.task_key
WHERE b.run_id = :run_id
  AND e.task_key IS NULL
GROUP BY b.task_key;
~~~

Kiểm tra tính nhất quán giữa ledger và effect:

~~~sql
SELECT l.task_key
FROM execution_ledger l
LEFT JOIN billing_effect b
    ON b.run_id = l.run_id
   AND b.task_key = l.task_key
WHERE l.run_id = :run_id
  AND b.effect_id IS NULL;
~~~

Ba truy vấn này vẫn chưa kiểm tra nội dung nghiệp vụ. Hãy so sánh thêm số tiền, mã hóa đơn, kỳ xử lý và giá trị tổng dự kiến; một effect duy nhất nhưng sai số tiền vẫn là lỗi.

Với tác dụng ngoài database, thay phép đếm bảng bằng bằng chứng ở hệ thống đích hoặc một test double lưu bền mọi request cùng idempotency key và kết quả xử lý. Đếm outbox row chỉ chứng minh có một ý định phát thông điệp; nó chưa chứng minh phía nhận chỉ áp dụng một lần.

## 11. Fencing và công việc dài

Idempotency giải quyết các lần thử của **cùng một khóa nghiệp vụ**. Nó chưa ngăn leader cũ ghi một công việc khác chưa từng được xử lý, hoặc ghi đè trạng thái bằng dữ liệu lỗi thời.

Nếu cần chặn mọi lần ghi của nhiệm kỳ cũ, có thể thiết kế fencing tại tài nguyên đích:

~~~text
Tài nguyên đích lưu current_epoch = 42
Leader mới ghi với epoch = 42
Tác vụ cũ ghi với epoch = 41 -> bị từ chối
~~~

Điều kiện để cơ chế này có ý nghĩa:

- Epoch được cấp bởi một cơ chế dùng chung có thứ tự đáng tin cậy.
- Việc cập nhật epoch hiện hành và kiểm tra quyền ghi có tính nguyên tử cần thiết tại đích.
- Tác vụ cũ không thể tự lấy epoch mới rồi tiếp tục như thuộc nhiệm kỳ mới.
- Mọi đường ghi cần bảo vệ đều bị kiểm tra, kể cả tác vụ nền và các lần retry.

Bộ đếm `local_generation` của từng JVM không đáp ứng các điều kiện đó. `metadata.resourceVersion` là phiên bản đối tượng trong giao thức Kubernetes API. Ngay cả khi phiên bản cluster hỗ trợ so sánh thứ tự các giá trị này, chúng không tự tạo hợp đồng fencing tại database. Muốn sử dụng trong một thiết kế cụ thể, vẫn phải chứng minh cách cấp quyền và từ chối ghi nguyên tử ở đích. [Ngữ nghĩa resourceVersion](https://kubernetes.io/docs/reference/using-api/api-concepts/#resource-versions)

Để kiểm thử một cơ chế fencing đã triển khai, giữ tác vụ cũ sau khi nhận token, cấp token mới và commit một thay đổi từ leader mới, rồi cho tác vụ cũ ghi. Test phải thấy lần ghi cũ bị từ chối ngay tại đích và trạng thái mới không bị ghi đè. Ca này bổ sung cho idempotency, vì hai cơ chế bảo vệ các thuộc tính khác nhau.

## 12. Giảm flakiness và chẩn đoán đúng lớp lỗi

| Hiện tượng | Khả năng cần kiểm tra | Bằng chứng cần lấy |
| --- | --- | --- |
| Không có leader | Sai namespace, thiếu ConfigMap, thiếu quyền, Pod chưa Ready | Cấu hình hiệu lực, response API, conditions của Pod |
| Nhiều nơi báo leading kéo dài | Khóa/role khác nhau, trạng thái cũ, lỗi adapter sự kiện | Trạng thái từng tiến trình, bản ghi khóa, chuỗi sự kiện |
| Leader đổi nhưng công việc không tiến triển | Executor đã dừng, database lỗi, không quét lại việc | Hàng đợi, vòng scheduler, lỗi JDBC |
| Có hai effect cho một khóa | Khóa thay đổi khi retry, ghi ngoài transaction, bỏ qua ledger | Input key, transaction, dữ liệu đích |
| Có ledger nhưng thiếu effect | Commit tách rời, bắt exception sai hoặc tác dụng ở ngoài DB | Transaction boundary, log lỗi, bản ghi tương ứng |
| Chỉ CI chậm mới fail | Deadline sai, thiếu tài nguyên, image chưa sẵn sàng | Thời điểm startup, API latency, tài nguyên node |
| Test luôn pass quá nhanh | Không tạo được lỗi hoặc chưa có công việc thực sự chạy | Xác nhận fault và số lần thử trước/sau lỗi |

Mỗi test cần lưu tối thiểu:

- Phiên bản Spring Boot, Spring Cloud BOM, Spring Cloud Kubernetes, client Kubernetes, image digest và phiên bản cluster.
- Namespace, role, tên khóa, cấu hình hiệu lực đã che dữ liệu nhạy cảm.
- Pod name/UID/process_id, trạng thái Ready, restart count và kết quả rollout.
- ConfigMap khóa trước và sau lỗi, sự kiện granted/revoked và log các Pod liên quan.
- Mốc gây lỗi, bằng chứng fault đã có hiệu lực và số đo tiếp quản/tiến triển.
- Tập đầu vào, số lần thử, duplicate rejection, effect thành công và truy vấn bất thường.

Với test thất bại, thu bằng chứng trước khi xóa namespace. Khôi phục lỗi mạng trong `finally`; nếu không khôi phục được hoặc không thu được dữ liệu cần thiết, báo rõ phần đó thay vì làm mất nguyên nhân bằng một exception thu dọn mới.

Bộ test nên có một kiểm chứng độ nhạy trong fixture riêng: vô hiệu hóa lớp chống trùng và ép hai lần ghi cùng khóa. Phép đếm effect phải bắt được lỗi. Không đưa biến thể này vào image thông thường. Mục tiêu là chứng minh test thật sự quan sát thuộc tính cần bảo vệ.

## 13. Bài thực hành và tiêu chí hoàn thành

Thực hiện trên cluster thử nghiệm với ba replica và 20 khóa đầu vào cố định:

1. Chạy ca khởi động đồng thời, ghi lại leader và chứng minh đủ 20 kết quả.
2. Dừng leader có kiểm soát giữa lượt xử lý; đo riêng thời gian có leader và thời gian có tiến triển.
3. Dừng đột ngột trước commit; chứng minh việc chưa hoàn tất được thử lại.
4. Dùng barrier để tác vụ cũ và tác vụ mới cùng thử ghi một khóa; chứng minh hai attempt nhưng một effect.
5. Bỏ quyền update khóa; chứng minh test phân biệt lỗi điều phối với lỗi nghiệp vụ.
6. Nếu môi trường hỗ trợ, cô lập API của một Pod, xác nhận fault và ghi nhận hành vi thực tế.
7. Thu bằng chứng, đối chiếu cả trùng, thiếu và nội dung kết quả, rồi thu dọn tài nguyên của lần chạy.

Một lần chạy đạt yêu cầu khi có bằng chứng fault đã xảy ra, hệ thống phục hồi đúng hợp đồng của ca, mọi khóa hợp lệ có một kết quả đúng và không còn tác vụ chưa quan sát sau khi kết thúc. Ca không tạo được lỗi hoặc không có khả năng quan sát phải được báo riêng.

Khi chọn giải pháp triển khai, chỉ dùng leader election nếu thực sự cần một tiến trình điều phối trong nhóm replica. Với tác vụ theo lịch, cân nhắc [Kubernetes CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/); với công việc phân chia độc lập, cân nhắc hàng đợi và cơ chế claim tại database. CronJob vẫn yêu cầu tác vụ chịu được việc chạy lặp. Dù chọn cách nào, vẫn phải xác định retry, khóa nghiệp vụ và cách kiểm chứng tác dụng tại đích.

Điểm cần giữ xuyên suốt là: **có leader mới chưa đủ; phải chứng minh công việc tiếp tục với kết quả đúng trong lúc các lần thử cũ và mới có thể giao nhau**.

## Tài liệu đối chiếu

- [Spring Cloud Kubernetes 3.3 — Leader Election](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/leader-election.html): API sự kiện và dependency của nhánh ví dụ.
- [Spring Cloud Kubernetes — các chế độ Leader Election](https://docs.spring.io/spring-cloud-kubernetes/reference/leader-election.html): nhận diện khác biệt khi chọn chế độ khác.
- [Spring Integration — Leadership Event Handling](https://docs.spring.io/spring-integration/reference/leadership-event-handling.html): vai trò của sự kiện granted/revoked và Context.
- [Kubernetes RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/): quyền theo resource, namespace và giới hạn resourceNames.
- [Kubernetes Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): readiness, restart và danh tính Pod.
- [PostgreSQL INSERT](https://www.postgresql.org/docs/current/sql-insert.html): cú pháp xử lý xung đột trong ví dụ chống trùng.
