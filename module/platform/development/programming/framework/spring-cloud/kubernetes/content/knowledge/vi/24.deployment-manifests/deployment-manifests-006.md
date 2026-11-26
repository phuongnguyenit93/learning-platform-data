# Requests, limits và giới hạn mức đồng thời của ứng dụng

## Mục tiêu và bối cảnh

Trong chương **Manifest triển khai** của module **SPRING_CLOUD_KUBERNETES**, cấu hình tài nguyên phải đi cùng cách ứng dụng tiếp nhận công việc. Một Pod có CPU và bộ nhớ giới hạn vẫn có thể nhận quá nhiều request, tạo quá nhiều tác vụ hoặc làm cạn connection pool của dịch vụ phụ thuộc.

Bài học hướng dẫn phối hợp ba lớp: **ngân sách tài nguyên của container**, **ngân sách bộ nhớ và luồng của JVM**, và **số công việc ứng dụng cho phép xử lý đồng thời**. Các ví dụ liên hệ với DiscoveryClient, Spring Cloud LoadBalancer và Configuration Watcher để làm rõ tính năng nào cần được tính vào ngân sách triển khai.

Sau bài học, bạn có thể:

- Đặt requests/limits đúng đơn vị và giải thích được tác dụng của chúng.
- Phân biệt CPU throttling, container OOM, Java heap OOM và quá tải hàng đợi.
- Đặt giới hạn in-flight, thread pool, task queue và connection pool theo đúng phạm vi.
- Tính lại ngân sách toàn hệ thống khi scale hoặc rolling update.
- Kiểm chứng bằng dữ liệu tải, trạng thái Pod và các giá trị ứng dụng quan sát được.

Ví dụ sử dụng Linux container, Java 21, Spring Boot tương thích với Spring MVC/Tomcat và Actuator. Phần cấu hình virtual threads dành cho phiên bản Spring Boot có hỗ trợ, chẳng hạn từ dòng 3.2. Các con số là điểm khởi đầu của lab, cần đo trước khi dùng cho sản phẩm.

## 1. Requests và limits kiểm soát điều gì?

| Trường | Vai trò chính | Không tự thực hiện |
| --- | --- | --- |
| `requests.cpu` | Đầu vào xếp lịch và trọng số CPU khi tranh chấp | Giới hạn số request HTTP |
| `limits.cpu` | Hạn chế mức sử dụng CPU, thường qua throttling | Tự động từ chối request dư |
| `requests.memory` | Khai báo nhu cầu bộ nhớ phục vụ xếp lịch | Cấp sẵn Java heap tương ứng |
| `limits.memory` | Giới hạn bộ nhớ container; có thể dẫn tới OOM kill | Chỉ giới hạn riêng Java heap |

Container có thể sử dụng vượt request khi tài nguyên cho phép. CPU và bộ nhớ có cơ chế cưỡng chế khác nhau: CPU có thể bị throttling; vượt khả năng bộ nhớ có thể làm tiến trình bị kernel kết thúc. Requests không phải mức trần sử dụng. Xem [Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/).

Ví dụ:

~~~yaml
resources:
  requests:
    cpu: 500m
    memory: 512Mi
  limits:
    cpu: "1"
    memory: 768Mi
~~~

`500m` CPU là `0,5` đơn vị CPU, không phải 500 mili giây. `"1"` là một đơn vị CPU. `Mi` và `Gi` là đơn vị nhị phân cho bộ nhớ; không viết `500m` với ý nghĩa 500 MiB bộ nhớ.

Với khai báo trên, scheduler xét nhu cầu CPU `500m` và bộ nhớ `512Mi` của container này. Khi tính khả năng đặt Pod lên node, còn phải xét các container khác, init container và overhead phù hợp. Nếu không đủ tài nguyên theo request, Pod có thể Pending dù một số container hiện sử dụng ít.

LimitRange hoặc ResourceQuota của namespace có thể bổ sung mặc định, ràng buộc hoặc từ chối khai báo. Hãy đọc Pod thực tế sau admission, không chỉ dựa vào tệp YAML ban đầu.

### 1.1. CPU throttling khác với lỗi ứng dụng

Giới hạn CPU không tạo thêm năng lực xử lý. Khi nhiều luồng cần CPU vượt ngân sách, thời gian xử lý có thể tăng dù node vẫn còn CPU nhàn rỗi. Tăng thread pool trong tình huống đó có thể làm tăng tranh chấp, hàng đợi và thời gian GC.

Không coi mọi độ trễ cao là throttling. Cần đối chiếu CPU sử dụng, dữ liệu throttling nếu runtime xuất ra, thời gian chờ I/O và tình trạng pool.

### 1.2. QoS không thay thế kiểm soát quá tải

Với cách khai báo từng container trong ví dụ, request và limit không bằng nhau nên Pod thuộc lớp Burstable nếu không có cấu hình khác làm thay đổi điều kiện phân loại.

Guaranteed đòi hỏi thỏa điều kiện tài nguyên tương ứng của Pod, không chỉ đặt một trường request bằng một trường limit. Tên lớp QoS không có nghĩa ứng dụng được miễn OOM, được cấp CPU riêng hoặc không cần giới hạn tải. Xem [Pod Quality of Service Classes](https://kubernetes.io/docs/concepts/workloads/pods/pod-qos/).

## 2. Mức đồng thời khác số luồng, số kết nối và tốc độ

**In-flight** là số công việc đã được nhận nhưng chưa hoàn tất trong một phạm vi cụ thể.

| Đại lượng | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Tốc độ request | 30 request/giây | Số request trong một đơn vị thời gian |
| Request in-flight | 16 request | Số request đang chiếm chỗ xử lý |
| Worker threads | 32 luồng Tomcat | Số luồng xử lý của một executor |
| Kết nối HTTP | 128 kết nối | Có thể bao gồm kết nối keep-alive không xử lý request |
| Kết nối JDBC | 8 kết nối | Số kết nối mở trong một pool dữ liệu |
| Hàng đợi tác vụ | 16 phần tử | Công việc chờ executor thực hiện |

Các đại lượng này không bằng nhau. Với HTTP/2, một kết nối có thể mang nhiều stream; với I/O bất đồng bộ, một luồng có thể tham gia nhiều request. Rate limit cũng không tự tạo giới hạn in-flight khi thời gian xử lý tăng.

Một luồng tiếp nhận đơn giản:

~~~text
Client
  → kết nối và hàng chờ của HTTP server
  → worker xử lý request
  → cổng giới hạn công việc nghiệp vụ
  → pool kết nối / bulkhead của dịch vụ phụ thuộc
  → hoàn tất hoặc từ chối trong thời gian có giới hạn
~~~

Giới hạn ở lớp ứng dụng không xóa hàng đợi phía trước nó. Proxy, connector, executor và client vẫn cần timeout cùng ngân sách chờ phù hợp.

### 2.1. Dùng quan hệ giữa tải và thời gian xử lý để ước lượng

Trong điều kiện ổn định và cùng một ranh giới đo, định luật Little cho biết:

~~~text
Số công việc trung bình trong hệ thống
    = tốc độ hoàn tất trung bình × thời gian trung bình trong hệ thống

L = λ × W
~~~

Ví dụ một Pod hoàn tất trung bình `30 request/s`, mỗi request ở trong phạm vi đang đo trung bình `0,2 s`:

~~~text
L = 30 × 0,2 = 6 request
~~~

Đây là giá trị trung bình, không phải mức cap chắc chắn đáp ứng mọi đợt tăng tải. Có thể bắt đầu thử cap `16` rồi đo độ trễ, tỷ lệ từ chối, CPU và bộ nhớ. Không thay `W` trung bình bằng p95 và coi đó vẫn là đẳng thức trên.

Nếu downstream chậm lên, số in-flight có thể tăng ngay cả khi tốc độ đến không tăng. Hàng đợi không giới hạn chỉ giữ thêm công việc trong RAM; nó không làm downstream nhanh hơn.

## 3. Tách ngân sách bộ nhớ container và Java heap

Một ngân sách minh họa cho limit `768Mi`:

| Thành phần dự kiến | Ngân sách |
| --- | --- |
| Java heap tối đa | `384Mi` |
| Metaspace, code cache, thread stack, direct/native buffer và phần khác | Dự trù `192Mi` |
| Biên an toàn cho biến động | Dự trù `192Mi` |
| Tổng ngân sách thiết kế | `768Mi` |

Hai khoản dự trù phải được thay bằng số đo. Việc dành ra một khoản không tự cưỡng chế từng thành phần native chỉ dùng đúng khoản đó.

Có thể bắt đầu với:

~~~text
-Xms128m -Xmx384m -XX:+ExitOnOutOfMemoryError
~~~

`-Xmx` chỉ giới hạn heap. `MaxRAMPercentage` là một lựa chọn khác để tính heap theo bộ nhớ JVM nhận diện; không coi nó là giới hạn toàn bộ tiến trình. Kiểm tra tùy chọn hiệu lực của đúng JVM/image, nhất là khi launcher hoặc buildpack đã tính sẵn ngân sách. Không chồng nhiều cơ chế tính heap mà không biết cơ chế nào có hiệu lực. Tham khảo [lệnh java của JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).

Cần phân biệt:

- **Java heap OOM:** JVM không cấp phát được trong heap; có thể có `OutOfMemoryError` và log của JVM.
- **Container OOM kill:** kernel kết thúc tiến trình do giới hạn hoặc tình trạng bộ nhớ; JVM có thể chưa kịp ghi heap dump.
- **Node pressure/eviction:** vòng đời Pod bị ảnh hưởng bởi áp lực tài nguyên ở node, cần đọc sự kiện và lý do cụ thể.

Mã thoát `137` chỉ là một tín hiệu liên quan việc bị kết thúc bằng SIGKILL; không đủ để tự kết luận nguyên nhân là OOM. Kiểm tra `lastState`, reason, sự kiện và dữ liệu bộ nhớ.

Tăng số platform thread còn có thể tăng nhu cầu stack/native memory. File trong `emptyDir` dùng RAM khi chọn `medium: Memory` cũng cần được tính vào ngân sách liên quan; nó không phải vùng lưu trữ miễn phí ngoài bộ nhớ container.

## 4. Tính giới hạn theo toàn bộ số bản sao đang đóng góp tải

Giới hạn cục bộ thường áp dụng **mỗi JVM hoặc mỗi Pod**, không tự trở thành giới hạn toàn cluster.

Giả sử database cho nhóm ứng dụng này ngân sách `80` kết nối. Kế hoạch triển khai có:

- Từ `2` đến `6` replica.
- Rolling update dùng `maxSurge: 1`.
- Một khoản dự phòng cho các Pod đang termination nhưng còn giữ kết nối.
- Ngân sách thiết kế ban đầu là tối đa `9` tiến trình còn đóng góp kết nối trong các tình huống đã xét.

Nếu mỗi tiến trình có một pool tối đa `8` kết nối:

~~~text
9 × 8 = 72 kết nối
72 ≤ 80
~~~

Số `9` là giả định năng lực phải được kiểm chứng và kiểm soát bằng quy trình triển khai, không phải hard cap mà Deployment tự đảm bảo. Pod đang termination có thể khiến tổng số Pod thực tế vượt `replicas + maxSurge`. Nhiều đợt rollout chồng nhau hoặc đóng kết nối chậm có thể làm giả định không còn đúng. Xem [Deployments của Kubernetes](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/).

Cách tính tổng quát:

~~~text
Tổng kết nối tiềm năng
  = tổng của mọi pool trong mọi tiến trình còn giữ kết nối

Ngân sách một pool mỗi Pod
  ≤ phần ngân sách dành cho workload / số Pod đóng góp tải đã dự kiến
~~~

Nếu ứng dụng có nhiều datasource, job nền, nhiều pool tới cùng database hoặc workload khác dùng chung ngân sách, phải cộng tất cả.

Tương tự, với ngân sách `60` lời gọi downstream đồng thời và `9` tiến trình, một bulkhead tối đa `6` lời gọi/tiến trình tạo mức tiềm năng `54`. Đây là tính toán cho bulkhead outbound, không phải lý do đặt mọi loại concurrency trong ứng dụng bằng `6`.

Autoscaling có thể giảm tải cho từng Pod nhưng làm tăng tổng kết nối, tổng tác vụ và tổng lời gọi tới hệ thống đích. DiscoveryClient và LoadBalancer giúp tìm/chọn instance; chúng không tự bảo vệ ngân sách toàn hệ thống của downstream.

## 5. Phối hợp các giới hạn trong Spring

### 5.1. Lớp HTTP

Bài lab dùng Tomcat với platform threads:

~~~yaml
server:
  tomcat:
    threads:
      max: 32
      min-spare: 4
    max-connections: 128
    accept-count: 32
spring:
  threads:
    virtual:
      enabled: false
app:
  concurrency:
    max-in-flight: 16
~~~

`app.concurrency.max-in-flight` là property tự định nghĩa, chỉ có tác dụng vì mã ứng dụng ở mục 6 đọc nó. Spring Boot không tự hiểu một property tùy ý và biến nó thành giới hạn request.

`threads.max` kiểm soát worker threads; `max-connections` kiểm soát kết nối; `accept-count` liên quan backlog kết nối khi connector bão hòa. Không cộng chúng thành một số request tối đa và không coi `accept-count` là tổng mọi hàng đợi bên trong Tomcat. Đối chiếu [Common Application Properties của Spring Boot](https://docs.spring.io/spring-boot/appendix/application-properties/) theo phiên bản đang sử dụng.

Khi bật virtual threads, các thuộc tính pool Tomcat tương ứng có thể không còn hiệu lực. Virtual threads cũng không làm database, HTTP client hoặc downstream có năng lực vô hạn. Với WebFlux, cần giới hạn theo luồng reactive và tài nguyên thực tế; không lấy số event-loop thread làm cap request.

### 5.2. Tác vụ nền và hàng đợi

Nếu sử dụng executor do Spring Boot tự cấu hình, một điểm khởi đầu có thể là:

~~~yaml
spring:
  task:
    execution:
      pool:
        core-size: 4
        max-size: 8
        queue-capacity: 16
~~~

Với ThreadPoolTaskExecutor thông thường, sau khi đạt core size, công việc thường vào queue trước khi pool tăng tới max size. Hàng đợi hữu hạn giúp giới hạn công việc đang chờ, nhưng vẫn cần xử lý tình huống submit bị từ chối.

Cấu hình này không tự giới hạn mọi `CompletableFuture`, executor tự tạo, scheduler hoặc message listener. Xác định executor nào đang chạy tác vụ. Khi bật virtual threads, cơ chế executor có thể khác; xem [Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html).

Không dùng hàng đợi trong RAM làm nơi nhận vô hạn công việc đã cam kết bền vững với client. Nếu cần tiếp nhận để xử lý sau, thiết kế hàng đợi bền vững, giới hạn consumer và xử lý backpressure thích hợp.

### 5.3. Pool database và client outbound

Khi ứng dụng thực sự dùng datasource HikariCP, có thể cấu hình riêng:

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 8
      minimum-idle: 0
      connection-timeout: 500
~~~

`connection-timeout` trong ví dụ là thời gian chờ mượn kết nối theo mili giây, không phải timeout thực thi câu SQL. `minimum-idle: 0` là lựa chọn lab để giảm số kết nối duy trì khi nhàn rỗi, không phải giá trị tối ưu mặc định cho mọi hệ thống. Xem [tài liệu HikariCP](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby).

Pool database không giới hạn request không dùng database. Một request cũng có thể giữ kết nối quá lâu nếu bao cả lời gọi HTTP chậm trong transaction. Hãy giảm thời gian giữ tài nguyên, thay vì chỉ tăng pool.

Đối với HTTP client:

- Đặt giới hạn kết nối, thời gian chờ mượn kết nối, connect timeout và response timeout ở đúng client đang dùng.
- Nếu cần giới hạn số lời gọi đồng thời, dùng bulkhead/semaphore ở phạm vi outbound phù hợp.
- Với HTTP/2 hoặc cơ chế multiplexing, giới hạn kết nối không đồng nghĩa giới hạn lời gọi.
- Không giả định cấu hình của một RestClient/WebClient tự áp dụng cho mọi client khác.

## 6. Ví dụ cổng giới hạn cho công việc đồng bộ

Ví dụ sau dành cho **Spring MVC xử lý đồng bộ**. Ứng dụng đã có lớp khởi động Spring Boot và Actuator. Đặt controller trong package được component scan.

~~~java
package example.resourcebudget;

import java.util.Map;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WorkController {
    private final int limit;
    private final Semaphore slots;
    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger maxObserved = new AtomicInteger();
    private final AtomicLong rejected = new AtomicLong();
    private final String pod =
            System.getenv().getOrDefault("POD_NAME", "local");

    public WorkController(
            @Value("${app.concurrency.max-in-flight:16}") int limit) {
        if (limit <= 0) {
            throw new IllegalArgumentException("Concurrency limit must be positive");
        }
        this.limit = limit;
        this.slots = new Semaphore(limit);
    }

    @GetMapping("/api/work")
    public ResponseEntity<Map<String, Object>> work(
            @RequestParam(name = "delayMs", defaultValue = "200") int delayMs) {
        if (delayMs < 0 || delayMs > 1000) {
            return ResponseEntity.badRequest()
                    .body(Map.of("status", "invalid-delay"));
        }

        if (!slots.tryAcquire()) {
            rejected.incrementAndGet();
            return ResponseEntity.status(503)
                    .header("Retry-After", "1")
                    .body(Map.of("status", "busy", "pod", pod));
        }

        int admitted = active.incrementAndGet();
        maxObserved.accumulateAndGet(admitted, Math::max);
        try {
            // Chỉ mô phỏng công việc chờ I/O trong lab.
            Thread.sleep(delayMs);
            return ResponseEntity.ok(Map.of(
                    "status", "ok",
                    "pod", pod,
                    "limit", limit,
                    "inFlightAtAdmission", admitted));
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return ResponseEntity.status(503)
                    .body(Map.of("status", "interrupted", "pod", pod));
        } finally {
            active.decrementAndGet();
            slots.release();
        }
    }

    @GetMapping("/internal/concurrency")
    public Map<String, Object> concurrency() {
        return Map.of(
                "pod", pod,
                "limit", limit,
                "active", active.get(),
                "maxObserved", maxObserved.get(),
                "rejected", rejected.get());
    }
}
~~~

`tryAcquire()` từ chối ngay khi hết permit; `finally` trả permit khi công việc đồng bộ kết thúc, kể cả khi có lỗi. Tham khảo [Semaphore của Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html).

Phạm vi cần hiểu rõ:

- Controller là singleton mặc định, nên các request tới phương thức này trong cùng JVM dùng chung một semaphore.
- Mỗi Pod có semaphore riêng; `16` không phải cap toàn cluster.
- Chỉ `/api/work` được giới hạn. Những endpoint hoặc tác vụ khác không tự dùng chung cap.
- `Thread.sleep` mô phỏng thời gian chờ, không mô phỏng tải CPU.
- Endpoint chẩn đoán chỉ dành cho lab hoặc kênh nội bộ được bảo vệ.

Không áp dụng nguyên vòng đời permit này cho `Mono`, `CompletableFuture`, Servlet async hoặc streaming. Khi phương thức trả về trước lúc công việc kết thúc, phải giữ permit đến tín hiệu hoàn tất/hủy thực sự, đồng thời xử lý timeout và cancellation.

Mã `503` ở đây biểu thị dịch vụ tạm thiếu năng lực. `429` thường dùng cho chính sách hạn mức của client; hãy chọn mã và hợp đồng retry nhất quán với API. Không yêu cầu mọi client retry ngay chỉ vì đã trả `Retry-After`.

## 7. Manifest ghép tài nguyên với cấu hình ứng dụng

Chuẩn bị image `resource-demo:lab` chứa controller ở mục 6, web server và Actuator. Image phải tương thích Java 21, chạy được bằng UID/GID `10001` và không cần ghi ngoài volume tạm đã cấp.

Manifest dùng ConfigMap qua volume để Spring Boot nạp cấu hình. Ứng dụng không cần tự gọi Kubernetes API, nên token tự động được tắt. Nếu workload thực tế dùng DiscoveryClient hoặc đọc cấu hình qua API, cần cấu hình ServiceAccount/RBAC riêng theo tính năng đó.

Lưu nội dung thành `resource-demo.yaml` trong môi trường thực hành:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: resource-lab
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: resource-demo
  namespace: resource-lab
automountServiceAccountToken: false
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: resource-demo-config
  namespace: resource-lab
data:
  application.yaml: |
    spring:
      application:
        name: resource-demo
      threads:
        virtual:
          enabled: false
      task:
        execution:
          pool:
            core-size: 4
            max-size: 8
            queue-capacity: 16
      lifecycle:
        timeout-per-shutdown-phase: 20s
      cloud:
        loadbalancer:
          retry:
            enabled: false
    server:
      port: 8080
      shutdown: graceful
      tomcat:
        threads:
          max: 32
          min-spare: 4
        max-connections: 128
        accept-count: 32
    management:
      endpoints:
        web:
          exposure:
            include: health,metrics
      endpoint:
        health:
          probes:
            enabled: true
          show-details: never
    app:
      concurrency:
        max-in-flight: 16
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: resource-demo
  namespace: resource-lab
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: resource-demo
  template:
    metadata:
      labels:
        app: resource-demo
    spec:
      serviceAccountName: resource-demo
      automountServiceAccountToken: false
      terminationGracePeriodSeconds: 30
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: app
          image: resource-demo:lab
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_CONFIG_ADDITIONAL_LOCATION
              value: file:/etc/app-config/
            - name: JAVA_TOOL_OPTIONS
              value: "-Xms128m -Xmx384m -XX:+ExitOnOutOfMemoryError -Djava.io.tmpdir=/tmp"
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
          resources:
            requests:
              cpu: 500m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 768Mi
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
          volumeMounts:
            - name: config
              mountPath: /etc/app-config
              readOnly: true
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: config
          configMap:
            name: resource-demo-config
            defaultMode: 0444
        - name: tmp
          emptyDir:
            sizeLimit: 128Mi
---
apiVersion: v1
kind: Service
metadata:
  name: resource-demo
  namespace: resource-lab
spec:
  selector:
    app: resource-demo
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

Nạp image vào node của cluster cục bộ hoặc thay `image` bằng địa chỉ registry/digest của artifact đã chuẩn bị. Không dùng việc build trên host làm bằng chứng node đã có image.

Các cấu hình executor chỉ có tác dụng khi công việc được submit vào đúng executor. Lab không tạo job nền hoặc datasource, nên chưa kiểm chứng các pool đó. Cấu hình HikariCP ở mục 5 chỉ thêm vào ứng dụng có datasource thật và ngân sách kết nối đã thống nhất.

Một số điểm cần đối chiếu:

- Limit bộ nhớ `768Mi` và heap `384m` là hai ngân sách khác nhau.
- Cổng nghiệp vụ có cap `16`, trong khi worker Tomcat có mức tối đa `32`.
- Actuator không đi qua semaphore của `/api/work` nhưng vẫn dùng tài nguyên của ứng dụng.
- Shutdown của Spring có ngân sách `20s`, nằm trong thời gian kết thúc Pod `30s`; cần tính thêm các bước shutdown khác nếu có.
- Chỉ ConfigMap được mount; không cấp RBAC rộng khi ứng dụng chỉ đọc tệp.

Tách probe khỏi cap nghiệp vụ không đảm bảo tuyệt đối probe luôn được phục vụ khi CPU, connector hoặc RAM đã bão hòa. Không đưa trạng thái “đang hết permit” hay lỗi downstream nhất thời trực tiếp vào liveness để khởi động lại Pod liên tục.

## 8. Kiểm tra manifest và giới hạn trên một Pod

### 8.1. Triển khai và đọc cấu hình thực tế

Các lệnh sau dành cho cluster thực hành:

~~~powershell
kubectl apply -f resource-demo.yaml
kubectl rollout status deployment/resource-demo -n resource-lab --timeout=180s
kubectl get pods -n resource-lab -l app=resource-demo
kubectl get deployment resource-demo -n resource-lab -o yaml
kubectl top pods -n resource-lab --containers
~~~

`kubectl top` cần Metrics API phù hợp trong cluster. Không có dữ liệu từ lệnh này không đồng nghĩa ứng dụng không dùng CPU hoặc bộ nhớ.

Nếu Pod Pending, đọc sự kiện bằng `kubectl describe pod` cho đúng tên Pod. Nếu tiến trình khởi động rồi thoát, đọc log và trạng thái container; không tăng request hoặc heap chỉ từ một thông báo lỗi chung.

Chọn một Pod để kiểm tra cap cục bộ:

~~~powershell
$PodSnapshot = kubectl get pods -n resource-lab -l app=resource-demo -o json | ConvertFrom-Json
$ProbePod = $PodSnapshot.items[0].metadata.name
kubectl port-forward -n resource-lab "pod/$ProbePod" 18080:8080
~~~

Trong terminal khác:

~~~powershell
Invoke-RestMethod http://127.0.0.1:18080/internal/concurrency
Invoke-RestMethod http://127.0.0.1:18080/actuator/health/readiness
Invoke-RestMethod "http://127.0.0.1:18080/api/work?delayMs=200"
~~~

Giá trị `limit` phải là `16`. Nếu nhận giá trị khác, kiểm tra ConfigMap, đường dẫn, biến môi trường và nguồn ghi đè trước khi đánh giá hiệu năng.

Port-forward tới một Pod phục vụ kiểm tra chính Pod đó. Port-forward tới Service hoặc Deployment cũng không thay thế phép đo phân phối tải thực tế qua nhiều backend.

### 8.2. Tạo một đợt request chồng lấn có giới hạn

Ví dụ yêu cầu **PowerShell 7**, dùng `ForEach-Object -Parallel` và `-SkipHttpErrorCheck` để ghi nhận cả phản hồi `503`:

~~~powershell
$Results = 1..120 | ForEach-Object -Parallel {
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:18080/api/work?delayMs=1000" -SkipHttpErrorCheck -TimeoutSec 10
        [pscustomobject]@{
            Status = [string][int]$response.StatusCode
            Milliseconds = $watch.ElapsedMilliseconds
        }
    } catch {
        [pscustomobject]@{
            Status = "transport-error"
            Milliseconds = $watch.ElapsedMilliseconds
        }
    } finally {
        $watch.Stop()
    }
} -ThrottleLimit 48

$Results | Group-Object Status | Select-Object Name, Count
$Results | Where-Object Status -eq "200" |
    Measure-Object -Property Milliseconds -Average -Maximum
Invoke-RestMethod http://127.0.0.1:18080/internal/concurrency
~~~

Đây là batch với tối đa `48` tác vụ client cùng lúc, không phải bộ tạo tải có tốc độ đến cố định. Máy client, port-forward và thời gian khởi tạo runspace ảnh hưởng kết quả.

Các quan sát mong đợi khi có đủ request chồng lấn:

- Có request hoàn tất bình thường và có request bị từ chối vì hết permit.
- `maxObserved` không vượt `16` trong Pod được đo.
- Sau khi tải kết thúc, `active` trở về `0`.
- Request mới vẫn được phục vụ, Pod không liên tục restart.
- Có thể phân biệt phản hồi `503` từ cổng giới hạn với lỗi kết nối từ hạ tầng.

Nếu tất cả request đều thành công, chưa chắc cap bị sai; có thể tải chưa tạo đủ chồng lấn. Đối chiếu `maxObserved` và mức đồng thời thực tế trước khi kết luận.

Không gộp độ trễ của phản hồi `503` nhanh vào rồi kết luận p95 của công việc thành công đã tốt hơn. Phân tích riêng request thành công, request bị từ chối và lỗi transport.

`Thread.sleep` làm phép thử này chủ yếu kiểm tra giới hạn in-flight khi chờ. Muốn đánh giá CPU limit, GC hoặc database pool, phải dùng workload đại diện cho CPU, kích thước dữ liệu và hệ thống phụ thuộc thật hoặc stub phù hợp.

### 8.3. Những dữ liệu cần có ngoài lệnh top

| Nhóm tín hiệu | Câu hỏi cần trả lời |
| --- | --- |
| Request rate, p95/p99, số `503/429` | Thời gian chờ và tỷ lệ từ chối có trong hợp đồng không? |
| CPU sử dụng và throttling | CPU đang bận thật hay bị giới hạn theo quota? |
| Bộ nhớ container và heap | Tổng bộ nhớ có đủ biên an toàn không? |
| GC, số luồng, thời gian pause | JVM có đang trả giá vì lượng công việc giữ trong RAM không? |
| Active/queued/rejected của executor | Hàng đợi có tăng kéo dài hay có từ chối đúng dự kiến? |
| JDBC active/pending và thời gian mượn | Database hoặc pool có phải điểm nghẽn không? |
| Outbound in-flight, timeout và retry | Downstream có bị khuếch đại tải không? |
| Restart, OOMKilled và eviction | Cấu hình tài nguyên có làm mất ổn định vòng đời Pod không? |

Actuator/Micrometer cung cấp các nhóm metrics JVM, HTTP, executor hoặc datasource khi thành phần tương ứng được tích hợp; tên và mức chi tiết phụ thuộc phiên bản và thư viện. Xem [Spring Boot Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).

`jvm.memory.used` không phải tổng bộ nhớ container. Ngược lại, số bộ nhớ từ `kubectl top` không đủ để giải thích thành phần heap/native hoặc đỉnh sử dụng rất ngắn. Cần ghép các góc nhìn.

## 9. Requests tác động tới cách HPA đọc tải

Nếu cluster có Metrics API, có thể thử HPA sau khi đã hiểu giới hạn cục bộ:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: resource-demo
  namespace: resource-lab
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: resource-demo
  minReplicas: 2
  maxReplicas: 6
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
~~~

Với một container ứng dụng có CPU request `500m`, mức dùng `350m` tương ứng `70%` của request, không phải `70%` của limit `1` CPU. Đổi CPU request có thể đổi hành vi HPA dù lưu lượng không đổi.

HPA cần request và dữ liệu metric phù hợp để tính utilization. Khi thêm sidecar, phải xem lại phạm vi metric và tài nguyên của các container. Xem [Horizontal Pod Autoscaling](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/).

Các hệ quả vận hành:

- HPA phản ứng theo vòng lấy mẫu và điều kiện điều khiển; nó không thay cổng từ chối tải tức thời.
- Workload chờ I/O có thể đầy permit nhưng CPU còn thấp, nên CPU-only HPA có thể không phản ánh hết nhu cầu.
- Thêm Pod có thể làm vượt ngân sách database hoặc downstream nếu không tính tổng pool.
- HPA không tự bổ sung node; replica mới vẫn có thể Pending.
- Khi HPA quản lý replica, tránh thao tác liên tục ép lại `spec.replicas` bằng quy trình deploy không phù hợp.

Đo tải qua Service/Ingress hoặc bộ tạo tải trong cluster để đánh giá nhiều Pod. Kiểm tra phân phối thực tế, vì keep-alive, HTTP/2 và thuật toán load balancing có thể khiến tải lệch giữa các Pod.

## 10. Retry, discovery và cập nhật cấu hình trong Spring Cloud Kubernetes

### 10.1. Retry có thể khuếch đại tải đã bị từ chối

Một request nghiệp vụ có thể tạo nhiều lần thử tới downstream. Với nhiều lớp retry ở gateway, client và service, lượng công việc thực tế có thể lớn hơn đáng kể lưu lượng ban đầu.

Spring Cloud LoadBalancer chọn instance và có tùy chọn retry theo tích hợp/cấu hình; nó không tự trở thành bulkhead. Cấu hình lab tắt `spring.cloud.loadbalancer.retry.enabled` để quan sát giới hạn mà không thêm retry của lớp này. Điều đó không tắt retry ở mọi HTTP client hoặc proxy. Xem [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html).

Nếu sản phẩm cần retry:

- Giới hạn số lần thử và tổng deadline.
- Xét tính idempotent của thao tác.
- Dùng backoff/jitter theo thiết kế client.
- Không retry hàng loạt phản hồi quá tải ngay lập tức.
- Đặt budget cho cả số attempt và số lời gọi đang chạy.

### 10.2. Tính cả các thành phần nền thực sự được bật

DiscoveryClient, watcher, HTTP client Kubernetes, cache và executor nền đều có thể dùng kết nối, luồng hoặc bộ nhớ. Chỉ đưa vào image và bật các tính năng cần cho triển khai, rồi đo tác động của chúng.

Nếu ứng dụng chỉ cần Kubernetes Service DNS và ConfigMap qua volume, bài lab không cần quyền đọc API để chứng minh resources/concurrency hoạt động.

Nếu có Configuration Watcher, cần kiểm tra workload watcher riêng và kiểm tra cả luồng cập nhật ứng dụng. Năng lực của watcher không tự trở thành giới hạn request của workload nhận refresh.

### 10.3. Thay cấu hình không đồng nghĩa thay bộ giới hạn đang chạy

Semaphore trong controller được tạo ở constructor. Thay ConfigMap hoặc gọi refresh không tự thay số permit đúng cách.

Với lab, cập nhật ConfigMap rồi rollout Deployment để khởi tạo phiên bản giới hạn mới. Trong thời gian rollout, bản cũ và bản mới cùng tồn tại, nên vẫn phải tính tổng tải theo cả hai cấu hình.

Không đặt semaphore vào một bean được tạo lại rồi mặc định việc refresh là an toàn: request cũ có thể còn giữ permit của limiter cũ trong khi request mới dùng limiter mới. Nếu cần thay cap tại chỗ, dùng cơ chế cập nhật hỗ trợ rõ vòng đời công việc và kiểm chứng dưới tải.

Các tham số JVM và `resources` cũng có vòng đời cập nhật riêng. Trong workflow Deployment của bài, thay Pod template dẫn tới rollout; sửa mỗi ConfigMap không tự tạo cùng hiệu ứng đó.

## 11. Chẩn đoán theo triệu chứng

| Triệu chứng | Điều cần kiểm tra trước | Thay đổi có căn cứ |
| --- | --- | --- |
| Pod Pending với thiếu CPU/RAM | Requests, khả năng node, quota và các container khác | Điều chỉnh kế hoạch cấp tài nguyên hoặc nhu cầu đã đo |
| CPU sát limit, độ trễ tăng | Throttling, CPU của công việc, GC và contention | Giảm cạnh tranh, tối ưu công việc hoặc tăng CPU theo dữ liệu |
| Heap thấp nhưng container gần limit | Native/direct memory, stack, cache, file dùng RAM | Đo phần ngoài heap và sửa ngân sách tổng |
| `OOMKilled` | Bộ nhớ container và trạng thái lần chạy trước | Giảm giữ dữ liệu/in-flight hoặc cấp đủ ngân sách |
| Java báo heap OOM | Heap, dữ liệu giữ lại, queue và dấu hiệu rò rỉ | Phân tích nguyên nhân trước khi chỉ tăng `-Xmx` |
| Nhiều request chờ JDBC | Pool pending, truy vấn, transaction và tổng kết nối | Rút ngắn thời gian giữ kết nối hoặc giảm tải |
| Nhiều `503` do gate, CPU thấp | Downstream chậm, cap, phân phối tải | Kiểm tra nút nghẽn và ngân sách đích trước khi scale |
| Queue tăng nhưng throughput không tăng | Hàng đợi che giấu điểm nghẽn | Giới hạn queue, deadline và tốc độ tiếp nhận |
| Pod restart khi tải tăng | Liveness, thiếu tài nguyên, lỗi ứng dụng | Phân biệt quá tải với trạng thái không thể tự phục hồi |
| Scale lên làm database kém hơn | Tổng pool/attempt trên mọi Pod | Giảm ngân sách mỗi Pod hoặc đổi giới hạn scale |

Giảm request không làm ứng dụng tự dùng ít CPU/RAM hơn. Tăng limit không tự làm pool hợp lý hơn. Tăng cap không tự làm tăng throughput nếu điểm nghẽn nằm ở CPU hoặc downstream.

Khi đổi cấu hình, ghi rõ giả thuyết, giữ workload so sánh được và thay từng nhóm tham số có liên quan. So sánh độ trễ, tỷ lệ từ chối, throughput thành công và sự ổn định, không chỉ nhìn CPU trung bình.

## 12. Bài thực hành và điều kiện hoàn thành

1. Giải thích vì sao `500m` CPU request, `1` CPU limit và `16` request in-flight là ba con số độc lập.
2. Triển khai manifest và xác nhận resources thực tế, trạng thái Ready và cap ứng dụng.
3. Tạo tải trên một Pod, ghi lại `maxObserved`, số phản hồi từ chối và khả năng phục vụ lại sau tải.
4. Thử cap `8` rồi `16` trên cùng workload; so sánh throughput thành công và độ trễ, không mặc định cap lớn hơn sẽ tốt hơn.
5. Đánh giá thêm workload CPU hoặc downstream phù hợp để thấy sự khác biệt với phép thử `Thread.sleep`.
6. Tính lại tổng database pool và outbound concurrency khi có autoscaling, surge và Pod đang termination.
7. Nêu cơ chế cập nhật cap, cách giới hạn retry và những thành phần Spring Cloud Kubernetes thực sự cần bật.

Hoàn thành khi bạn đưa ra được một bộ manifest và cấu hình ứng dụng có ngân sách nhất quán, kèm bằng chứng giới hạn hoạt động trong phạm vi đã chọn. Quyết định tài nguyên và mức đồng thời phải bảo vệ cả Pod lẫn hệ thống phụ thuộc trong điều kiện tải, scale và rollout thực tế.
