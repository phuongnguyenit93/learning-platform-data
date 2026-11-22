# Khôi phục nhiều Pod và kiểm soát tải lên dịch vụ phụ thuộc

Khi triển khai Java với CRaC (Coordinated Restore at Checkpoint) trên Kubernetes, một checkpoint có thể giúp từng Pod khởi động và đạt trạng thái sẵn sàng nhanh hơn. Nhưng khi nhiều Pod cùng được khôi phục hoặc scale lên trong một khoảng thời gian ngắn, tất cả có thể đồng thời kết nối database, Redis, message broker, dịch vụ xác thực và các API bên ngoài.

Nếu mỗi Pod tự mở connection pool, refresh cache, đăng ký subscription và chạy warm-up ngay trong callback sau restore, tổng tải phát sinh có thể lớn hơn nhiều so với tải phục vụ bình thường. Database có thể hết connection, Redis bị connection storm, broker nhận quá nhiều consumer cùng lúc hoặc dịch vụ xác thực bị quá tải bởi các request lấy token.

Vì vậy, cần quản lý hai cấp độ riêng biệt:

- **Cấp Pod:** từng tiến trình khôi phục resource, kiểm tra dependency, warm-up có giới hạn và chỉ báo readiness khi có thể phục vụ.
- **Cấp fleet:** điều phối tốc độ khôi phục hoặc scale nhiều Pod, giới hạn tổng số kết nối và request đến dependency, phân tán retry và tránh mọi Pod cùng thực hiện một công việc nền.

Callback CRaC chỉ điều phối vòng đời của một tiến trình. Nó không tự điều phối toàn bộ replica trong Kubernetes. Muốn bảo vệ dịch vụ phụ thuộc, cần kết hợp lifecycle của ứng dụng với rollout strategy, autoscaling policy, rate limit, backpressure và quan sát ở cấp hệ thống.

## 1. Vì sao khôi phục nhiều Pod có thể tạo đột biến tải?

Giả sử một Deployment có 40 replica. Các Pod được khôi phục từ cùng một checkpoint hoặc được tạo gần như đồng thời. Mỗi Pod có thể thực hiện các thao tác sau:

- Mở 20 connection đến database pool.
- Kết nối Redis và refresh topology.
- Kết nối broker, tạo consumer và đăng ký subscription.
- Lấy access token từ identity provider.
- Nạp cache cấu hình và dữ liệu tham chiếu.
- Gọi health endpoint của các dịch vụ phụ thuộc.
- Chạy warm-up request để làm nóng code và cache.
- Khởi động scheduler hoặc background worker.

Chỉ riêng database pool đã có thể tạo 800 connection nếu 40 Pod cùng mở đủ 20 connection. Con số thực tế phụ thuộc pool configuration và thời điểm pool tạo connection, nhưng ví dụ cho thấy tổng tải fleet phải được tính bằng số Pod nhân với mức sử dụng trên mỗi Pod.

### 1.1. Connection storm và request storm

Có hai loại đột biến thường xuất hiện cùng nhau:

**Connection storm** xảy ra khi nhiều Pod đồng thời mở TCP/TLS connection, xác thực, thực hiện handshake và khởi tạo pool. Database hoặc Redis có thể chạm giới hạn connection trước khi ứng dụng nhận request nào.

**Request storm** xảy ra khi nhiều Pod cùng warm-up, refresh cache, gọi API cấu hình, tải metadata hoặc thực hiện health check. Dù số connection không quá lớn, số request trong một khoảng thời gian ngắn vẫn có thể vượt năng lực dependency.

Ví dụ:

| Hoạt động trên mỗi Pod | Số Pod | Tổng hoạt động khi cùng khôi phục |
|---|---:|---:|
| Mở tối đa 15 DB connection | 40 | 600 DB connections |
| Refresh 30 cache key | 40 | 1.200 cache reads |
| Lấy 2 token | 40 | 80 token requests |
| Tạo 4 broker consumer | 40 | 160 consumer |
| Gửi 5 warm-up request | 40 | 200 warm-up requests |

Đây là phép nhân minh họa. Pool có thể mở connection theo nhu cầu, cache có thể batch request và broker có thể giới hạn consumer. Tuy nhiên, nếu không thiết kế rõ, tất cả các hoạt động này có thể dồn vào cùng một cửa sổ thời gian.

### 1.2. Vì sao checkpoint không làm dependency dừng lại?

Checkpoint lưu trạng thái tiến trình Java. Database, Redis, broker và các API bên ngoài tiếp tục phục vụ những workload khác trong lúc Pod bị checkpoint.

Khi restore, mỗi Pod có thể khôi phục object client cũ nhưng vẫn phải xác nhận hoặc tạo lại kết nối. Nếu tất cả Pod cùng reconnect, dependency sẽ nhận một đợt tải mới trong khi vẫn xử lý traffic từ các ứng dụng khác.

~~~mermaid
sequenceDiagram
    participant K as Kubernetes / restore controller
    participant P1 as Pod 1
    participant P2 as Pod 2
    participant Pn as Pod N
    participant D as Database / Redis / Broker

    K->>P1: Restore
    K->>P2: Restore
    K->>Pn: Restore
    par Concurrent reconnect
        P1->>D: Connect, authenticate, warm-up
        P2->>D: Connect, authenticate, warm-up
        Pn->>D: Connect, authenticate, warm-up
    end
    D-->>P1: Slow response / connection limit
    D-->>P2: Timeout / queueing
    D-->>Pn: Retry
    P1->>D: Retry
    P2->>D: Retry
    Pn->>D: Retry
~~~

Nếu retry không có backoff và jitter, tải có thể tăng thêm đúng lúc dependency đang chậm. Một đợt khôi phục ban đầu ngắn có thể biến thành vòng lặp timeout và retry.

## 2. Hai cấp điều phối: Pod và fleet

Không thể giải quyết toàn bộ vấn đề bằng một callback `afterRestore()`. Cần phân chia trách nhiệm.

### 2.1. Cấp Pod

Mỗi Pod chịu trách nhiệm:

- Đánh dấu ứng dụng chưa sẵn sàng trong quá trình restore.
- Tạo lại resource thuộc quyền sở hữu của Pod.
- Dùng timeout cho kết nối và thao tác warm-up.
- Giới hạn concurrency nội bộ.
- Thực hiện retry có backoff và jitter.
- Chỉ mở admission khi dependency thiết yếu sẵn sàng.
- Không chạy lặp side effect nghiệp vụ chỉ vì tiến trình được restore.

### 2.2. Cấp fleet

Kubernetes controller, rollout controller hoặc một thành phần điều phối bên ngoài chịu trách nhiệm:

- Giới hạn số Pod được cập nhật hoặc khởi tạo trong một khoảng thời gian.
- Điều chỉnh tốc độ scale up.
- Phân nhóm hoặc chia đợt restore.
- Tránh tất cả replica cùng warm-up một dependency.
- Theo dõi tải dependency và tạm dừng đợt tiếp theo khi cần.
- Giữ đủ capacity phục vụ traffic hiện tại trong khi Pod mới đang khởi động.

Một callback CRaC không thể biết chắc tổng số Pod đang restore trên toàn cluster nếu không có một cơ chế điều phối riêng. Mỗi Pod chỉ nên tự quản lý phần việc của nó; giới hạn tổng tải cần được áp dụng ở cấp fleet hoặc tại chính dependency.

~~~mermaid
flowchart TD
    A["Restore / scale request"] --> B["Fleet rollout controller"]
    B --> C["Giới hạn số Pod mỗi đợt"]
    C --> D["Pod được restore"]
    D --> E["CRaC afterRestore"]
    E --> F["Khởi tạo dependency có giới hạn"]
    F --> G["Warm-up và health check"]
    G --> H{"Pod sẵn sàng?"}
    H -->|Có| I["Readiness = READY"]
    H -->|Chưa| J["Retry có backoff / NOT READY"]
    I --> K["Cho phép đợt tiếp theo"]
    J --> L["Giữ tải trong giới hạn"]
    L --> H
~~~

## 3. Kiểm soát tốc độ khôi phục bằng Kubernetes Deployment

Với Deployment, rolling update cho phép giới hạn số Pod mới và số Pod cũ có thể unavailable trong quá trình thay đổi phiên bản.

Hai trường quan trọng là:

- `maxSurge`: số Pod vượt quá số replica mong muốn có thể được tạo trong lúc rollout.
- `maxUnavailable`: số Pod tối đa có thể unavailable trong quá trình rollout.

Ví dụ cấu hình rollout tuần tự hơn:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 12
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: app
          image: registry.example.com/orders-api:2026.11
          ports:
            - name: http
              containerPort: 8080
~~~

Với cấu hình này, trong một rolling update, Deployment có thể tạo thêm tối đa một Pod vượt số replica mong muốn và không chủ động giảm số Pod available theo `maxUnavailable: 0`. Pod mới cần đạt readiness trước khi controller tiếp tục tiến trình thay thế theo điều kiện rollout.

Các giá trị cụ thể phải phù hợp với capacity cluster và tải dependency. Nếu mỗi Pod mới tạo 100 connection trong giai đoạn khởi động, `maxSurge: 1` vẫn có thể tạo tải đáng kể. Cần tính cả những Pod đang được khởi tạo bởi các Deployment khác.

### 3.1. maxSurge không giới hạn mọi hình thức scale up

Cần hiểu phạm vi của rollout strategy:

- `maxSurge` và `maxUnavailable` điều khiển rolling update của Deployment.
- Khi tăng `spec.replicas` hoặc HPA scale up, số Pod có thể tăng theo quy tắc scaling riêng.
- Nhiều Deployment có thể rollout cùng lúc và mỗi Deployment có `maxSurge` riêng.
- Một restore controller tùy biến có thể có cơ chế tạo Pod riêng.

Vì vậy, không nên xem `maxSurge: 1` là giới hạn toàn cluster. Nếu có nhiều workload cùng khởi động, cần một ngân sách tải tổng hoặc một cơ chế điều phối cấp cao hơn.

### 3.2. HPA và tốc độ scale up

HorizontalPodAutoscaler có thể tạo thêm nhiều replica khi metric tăng. Nếu ứng dụng đang restore từ checkpoint, HPA có thể làm tăng số Pod nhanh hơn tốc độ dependency có thể tiếp nhận.

Có thể giới hạn tốc độ scale up bằng `behavior.scaleUp`:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: orders-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  minReplicas: 4
  maxReplicas: 30
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      selectPolicy: Min
      policies:
        - type: Pods
          value: 2
          periodSeconds: 60
        - type: Percent
          value: 25
          periodSeconds: 60
~~~

Ví dụ này giới hạn số Pod có thể tăng trong mỗi cửa sổ theo các policy đã khai báo. Đây là cấu hình minh họa; cần điều chỉnh theo phiên bản Kubernetes, metric và nhu cầu tải.

HPA không hiểu trực tiếp rằng Redis hoặc database đang quá tải nếu chỉ theo dõi CPU của Pod. Có thể cần custom metric hoặc external metric phản ánh queue depth, dependency latency, connection utilization hoặc khả năng tiếp nhận của backend.

### 3.3. Tránh autoscaling tạo thêm tải khi dependency đang nghẽn

Một hệ thống có thể rơi vào vòng lặp:

1. Database chậm làm request của Pod kéo dài.
2. CPU hoặc request queue tăng.
3. HPA tăng số Pod.
4. Pod mới cùng mở connection và warm-up.
5. Database nhận thêm tải và chậm hơn.

Nếu bottleneck nằm ở dependency, tăng replica ứng dụng có thể làm tình trạng xấu hơn. Hãy đặt giới hạn scale và xem xét metric dependency trước khi cho phép HPA tăng nhanh.

## 4. StatefulSet và khôi phục theo thứ tự

Với workload cần danh tính ổn định hoặc storage riêng, StatefulSet có thể phù hợp hơn Deployment. StatefulSet hỗ trợ thứ tự tạo, xóa và cập nhật Pod theo ordinal.

Mặc định, `podManagementPolicy: OrderedReady` yêu cầu các Pod được tạo theo thứ tự và Pod trước phải Ready trước khi tạo tiếp Pod sau. `Parallel` cho phép tạo hoặc xóa Pod song song hơn.

~~~yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: worker
spec:
  serviceName: worker
  replicas: 6
  podManagementPolicy: OrderedReady
  selector:
    matchLabels:
      app: worker
  template:
    metadata:
      labels:
        app: worker
    spec:
      containers:
        - name: app
          image: registry.example.com/worker:2026.11
~~~

Với `OrderedReady`, readiness của từng Pod trở thành một phần trong thứ tự tiến triển. Điều này có thể giúp giảm đột biến khi cần khởi động tuần tự.

### 4.1. Rolling update với partition

StatefulSet hỗ trợ `updateStrategy.rollingUpdate.partition` để kiểm soát ordinal nào được cập nhật. Đây là cách chia đợt update, hữu ích khi muốn thử restore trên một số Pod trước.

Ví dụ:

~~~yaml
spec:
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      partition: 5
~~~

Với StatefulSet có ordinal từ 0 đến 5, partition 5 khiến các Pod có ordinal nhỏ hơn 5 chưa được cập nhật trong khi Pod có ordinal từ 5 trở lên thuộc phạm vi update. Có thể giảm partition từng bước sau khi kiểm tra Pod đã cập nhật.

Cần kiểm tra đúng semantics và trạng thái rollout của StatefulSet trước khi dùng trong quy trình thực tế. Partition điều khiển update; nó không phải một bộ giới hạn request đến database.

### 4.2. Khi nào không nên ép thứ tự?

Khởi động tuần tự làm giảm burst nhưng kéo dài thời gian rollout. Nếu mỗi Pod cần 90 giây để reconnect và warm-up, 20 Pod tuần tự có thể cần rất lâu.

Có thể chọn batch size lớn hơn một, hoặc warm-up nhẹ trước rồi cho phép nhiều Pod đạt readiness theo từng đợt. Mức song song phải dựa trên capacity dependency và thời gian phục hồi mà hệ thống chấp nhận.

## 5. Readiness, startup probe và liveness probe

Kubernetes probes giúp phân biệt tiến trình đã khởi động, có thể phục vụ traffic và còn sống hay không. Chúng là công cụ quan trọng để ngăn Pod chưa sẵn sàng nhận request.

### 5.1. Startup probe

Startup probe dành cho ứng dụng cần thời gian khởi động dài. Khi startup probe chưa thành công, Kubernetes chưa chạy readiness và liveness probe theo cách thông thường.

Có thể dùng startup probe để cho ứng dụng đủ thời gian restore, khởi tạo JVM và hoàn tất giai đoạn startup cần thiết.

### 5.2. Readiness probe

Readiness probe xác định Pod có nên nhận traffic từ Service hay không. Khi readiness thất bại, Pod không được xem là endpoint sẵn sàng cho Service tương ứng.

Readiness nên kiểm tra các điều kiện cần để phục vụ request, ví dụ:

- Ứng dụng đã hoàn tất restore và khởi tạo.
- Client đến database hoặc Redis đã sẵn sàng nếu request yêu cầu chúng.
- Cache thiết yếu đã được warm-up hoặc có fallback an toàn.
- Consumer hoặc worker đã được khởi động nếu Pod có nhiệm vụ xử lý job.
- Admission gate đã mở.

**Readiness không giới hạn outbound request.** Pod chưa Ready vẫn có thể gọi database, Redis hoặc identity provider trong callback và background initialization. Vì vậy, vẫn cần giới hạn tải bên trong ứng dụng và ở cấp fleet.

### 5.3. Liveness probe

Liveness probe xác định container có cần được khởi động lại hay không. Không nên làm liveness phụ thuộc trực tiếp vào một database hoặc Redis có thể tạm thời chậm. Nếu dependency chậm khiến tất cả Pod fail liveness, Kubernetes có thể restart hàng loạt và làm tăng thêm tải reconnect.

Liveness nên tập trung vào việc process có còn hoạt động và có thể tiến triển hay không. Readiness phù hợp hơn để biểu thị dependency chưa sẵn sàng.

### 5.4. Ví dụ probe

~~~yaml
containers:
  - name: app
    image: registry.example.com/orders-api:2026.11
    ports:
      - name: http
        containerPort: 8080
    startupProbe:
      httpGet:
        path: /health/startup
        port: http
      periodSeconds: 5
      failureThreshold: 60
    readinessProbe:
      httpGet:
        path: /health/ready
        port: http
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 2
    livenessProbe:
      httpGet:
        path: /health/live
        port: http
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
~~~

Các path là endpoint do ứng dụng cung cấp. `failureThreshold` và `periodSeconds` cần phù hợp với thời gian restore và SLA. Không nên đặt timeout quá thấp khiến probe tự tạo thêm áp lực trong lúc JVM đang bận khởi tạo.

### 5.5. Pod readiness và readiness gate

Readiness gate có thể bổ sung điều kiện từ một controller bên ngoài thông qua Pod condition. Ví dụ, một restore coordinator có thể chỉ đánh dấu Pod đủ điều kiện nhận traffic sau khi đã kiểm tra dependency hoặc cấp một slot trong ngân sách restore.

Readiness gate chỉ có tác dụng khi có controller hoặc thành phần cập nhật condition tương ứng. Kubernetes không tự biết trạng thái CRaC callback nếu ứng dụng không cung cấp tín hiệu.

## 6. Readiness không phải cơ chế throttle dependency

Một lỗi thiết kế thường gặp là giữ Pod ở trạng thái NotReady nhưng vẫn cho callback sau restore tạo toàn bộ pool và warm-up ngay lập tức.

Service sẽ không gửi traffic inbound đến Pod chưa Ready, nhưng Pod vẫn có thể chủ động:

- Mở connection đến database.
- Tạo Redis connection pool.
- Tải dữ liệu từ API.
- Đăng ký hàng trăm consumer.
- Gửi health check đến dependency.
- Chạy warm-up request.

Do đó, readiness bảo vệ đường inbound, còn outbound load cần cơ chế riêng.

Một Pod có thể có trạng thái nội bộ theo từng giai đoạn:

| Trạng thái | Hành động | Readiness |
|---|---|---|
| RESTORING | Khôi phục process và JVM | NOT_READY |
| REINITIALIZING | Tạo lại resource cần thiết | NOT_READY |
| WAITING_FOR_BUDGET | Chờ slot hoặc token để warm-up | NOT_READY |
| WARMING | Chạy warm-up có giới hạn | NOT_READY |
| VERIFYING | Kiểm tra dependency và chức năng | NOT_READY |
| READY | Cho phép nhận traffic | READY |
| DEGRADED | Một dependency tùy chọn lỗi, fallback được phép | Theo capability/policy |

Ứng dụng nên cung cấp readiness state rõ ràng thay vì chỉ kiểm tra process có trả HTTP 200 hay không.

## 7. Giới hạn concurrency khi khởi tạo dependency

Ngay cả khi Kubernetes chỉ restore một vài Pod cùng lúc, mỗi Pod vẫn có thể tạo nhiều request nội bộ song song. Cần giới hạn concurrency ở cấp Pod.

Ví dụ, thay vì mở toàn bộ connection pool và warm-up 100 key đồng thời, có thể:

- Tạo ít connection ban đầu.
- Mở rộng pool theo nhu cầu thực tế.
- Nạp cache theo batch nhỏ.
- Giới hạn số request warm-up đồng thời.
- Tách warm-up critical và optional.
- Dùng semaphore hoặc bounded executor.
- Đặt timeout cho từng thao tác.

### 7.1. Semaphore giới hạn số thao tác đồng thời

Ví dụ abstraction trong Java:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class DependencyGate {

    private final Semaphore permits;

    public DependencyGate(int maxConcurrent) {
        this.permits = new Semaphore(maxConcurrent);
    }

    public <T> T execute(
            CheckedSupplier<T> operation,
            long timeout,
            TimeUnit unit) throws Exception {

        if (!permits.tryAcquire(timeout, unit)) {
            throw new IllegalStateException(
                "Dependency warm-up capacity is unavailable"
            );
        }

        try {
            return operation.get();
        } finally {
            permits.release();
        }
    }

    @FunctionalInterface
    public interface CheckedSupplier<T> {
        T get() throws Exception;
    }
}
~~~

Semaphore này giới hạn concurrency bên trong một Pod. Nếu mỗi Pod có 4 permit và có 50 Pod, fleet vẫn có thể tạo tối đa 200 thao tác đồng thời. Muốn giới hạn tổng tải cần thêm cơ chế fleet-wide hoặc giới hạn ở dependency.

### 7.2. Tách pool warm-up khỏi pool phục vụ request

Warm-up có thể tranh connection với traffic đang phục vụ. Có thể dùng pool hoặc quota riêng cho công việc khởi tạo, nhưng tổng connection vẫn phải nằm trong ngân sách dependency.

Ví dụ, nếu database chỉ cho phép ứng dụng dùng 500 connection:

- Dành phần lớn cho traffic đang phục vụ.
- Giới hạn số connection warm-up.
- Giữ một phần dự phòng cho failover và tác vụ vận hành.
- Không cho mỗi Pod tự chọn pool size tối đa mà không tính tổng replica.

Tách pool giúp phân loại và ưu tiên, nhưng không tạo thêm capacity ở database.

## 8. Giới hạn tải ở cấp fleet

Local semaphore không thể giới hạn tổng số Pod. Có một số chiến lược để điều phối tải trên toàn fleet.

### 8.1. Rollout theo batch

Tạo hoặc restore một số Pod nhỏ, đợi chúng đạt readiness và dependency load ổn định, sau đó mới tiến hành batch tiếp theo.

Ưu điểm:

- Dễ hiểu và dễ quan sát.
- Không cần một distributed limiter riêng nếu rollout controller đã đủ khả năng.
- Có thể dừng tiến trình khi backend có dấu hiệu quá tải.

Giới hạn:

- Thời gian rollout tăng.
- Nhiều Deployment hoặc cluster khác nhau có thể vẫn khởi động cùng lúc.
- Scale up ngoài rollout có thể không tuân theo cùng batch.

### 8.2. Restore budget hoặc admission token

Một thành phần điều phối cấp fleet có thể cấp một số lượng token giới hạn. Mỗi Pod chỉ bắt đầu bước kết nối/warm-up nặng khi có token.

Ví dụ, nếu ngân sách là 3 Pod đang warm-up đồng thời, chỉ 3 Pod được phép thực hiện bước đó. Khi một Pod hoàn thành hoặc timeout, token được trả lại.

Có thể triển khai bằng:

- Controller/operator quản lý Pod condition.
- Queue hoặc coordinator bên ngoài.
- Lease có TTL trong một control-plane store.
- Một dịch vụ cấp token.
- Hệ thống rollout có pause/resume và analysis step.

Nếu dùng Redis hoặc database làm nơi cấp token, phải tính tải của chính coordinator. Tránh dùng dependency đang cần bảo vệ làm điểm nghẽn duy nhất cho restore budget. Cần có TTL/lease để token không bị giữ vĩnh viễn khi Pod crash.

### 8.3. Token bucket ở gateway hoặc dependency

Rate limiter tại API gateway hoặc dependency có thể giới hạn tổng request theo thời gian. Token bucket cho phép một burst nhỏ nhưng giới hạn tốc độ trung bình.

Ví dụ, dependency cho phép 100 request/giây và burst 20. Những request vượt giới hạn có thể bị trì hoãn hoặc từ chối có kiểm soát.

Rate limit ở dependency bảo vệ backend ngay cả khi nhiều ứng dụng cùng khởi động. Tuy nhiên, ứng dụng cần xử lý response 429 hoặc lỗi quota với backoff, không retry ngay lập tức.

### 8.4. Chia đợt theo node pool hoặc zone

Nếu nhiều Pod cùng restore có thể tạo áp lực lên network, storage hoặc dependency, chia đợt theo availability zone hoặc node pool giúp phân tán tải hạ tầng.

Tuy nhiên, phân tán theo zone không tự giới hạn số request đến một database dùng chung. Vẫn cần rate limit hoặc concurrency budget cho dependency.

## 9. Retry có backoff và jitter

Sau restore, dependency có thể chưa sẵn sàng. Retry là cần thiết, nhưng retry đồng thời từ nhiều Pod sẽ khuếch đại tải.

### 9.1. Exponential backoff

Khoảng chờ tăng theo số lần thất bại:

| Lần thử | Khoảng chờ minh họa |
|---|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.6 s |
| 5 | 3.2 s |

Nên đặt giới hạn tối đa, deadline tổng và số lần thử phù hợp. Không retry vô hạn các lỗi cấu hình hoặc xác thực.

### 9.2. Jitter

Nếu mọi Pod đều dùng cùng một lịch backoff cố định, chúng có thể retry đồng thời sau 200 ms, 400 ms, 800 ms. Jitter thêm độ ngẫu nhiên để phân tán request.

Ví dụ full jitter:

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class RetryDelay {

    public static Duration fullJitter(
            int attempt,
            Duration base,
            Duration maximum) {

        long multiplier = 1L << Math.min(attempt, 20);
        long cap;

        try {
            cap = Math.min(
                maximum.toMillis(),
                Math.multiplyExact(base.toMillis(), multiplier)
            );
        } catch (ArithmeticException e) {
            cap = maximum.toMillis();
        }

        long delay = ThreadLocalRandom.current()
                .nextLong(Math.max(1, cap + 1));

        return Duration.ofMillis(delay);
    }
}
~~~

Đây là ví dụ minh họa. Trong production, cần xử lý attempt âm, overflow và deadline tổng. Có thể dùng thư viện retry đã được kiểm chứng nếu nó hỗ trợ jitter và retry budget.

### 9.3. Retry budget

Giới hạn tổng số retry hoặc tổng thời gian retry giúp tránh một fleet liên tục tạo tải khi dependency đã hỏng.

Khi hết budget:

- Giữ Pod NotReady nếu dependency là bắt buộc.
- Chuyển sang degraded mode nếu fallback an toàn.
- Phát metric và log.
- Để controller quyết định tiếp tục, pause hoặc rollback rollout.

Không nên để liveness probe restart Pod chỉ vì dependency chưa phục hồi; restart sẽ lặp lại quá trình reconnect và có thể tạo storm lớn hơn.

## 10. Connection pool và ngân sách connection toàn hệ thống

Pool size cần được tính ở cấp fleet, không chỉ ở một Pod.

Giả sử database có giới hạn connection dành cho ứng dụng là 600. Hệ thống có:

- 30 Pod đang phục vụ.
- 10 Pod mới đang restore.
- Một số connection dành cho migration, monitoring và vận hành.

Nếu mỗi Pod có maximum pool size 20, tổng số connection tiềm năng của 40 Pod là 800, chưa tính thành phần khác. Pool cấu hình hợp lý ở một Pod vẫn có thể vượt giới hạn khi nhân với replica.

### 10.1. Công thức ngân sách đơn giản

Có thể ước lượng:

\[
C_{\text{total}} =
N_{\text{ready}} \times C_{\text{ready}}
+
N_{\text{restoring}} \times C_{\text{restore}}
+
C_{\text{other}}
\]

Trong đó:

- \(N_{\text{ready}}\): số Pod đang phục vụ.
- \(C_{\text{ready}}\): số connection trung bình hoặc giới hạn cho mỗi Pod đang phục vụ.
- \(N_{\text{restoring}}\): số Pod đang khởi tạo.
- \(C_{\text{restore}}\): số connection mỗi Pod tạo trong giai đoạn restore.
- \(C_{\text{other}}\): connection từ job, migration, admin và ứng dụng khác.

Tổng này cần thấp hơn ngân sách connection được cấp cho ứng dụng, có dự phòng cho failover và biến động tải.

### 10.2. Khởi tạo pool lười

Một pool có thể được cấu hình để không mở toàn bộ connection ngay khi tạo. Khởi tạo lazy hoặc giới hạn minimum idle giúp giảm burst.

Cần kiểm tra semantics của thư viện pool đang dùng. Một số pool tạo connection theo nhu cầu, một số có thể prefill hoặc chạy validation khi khởi động.

### 10.3. Tách giới hạn theo workload

Có thể phân bổ ngân sách riêng cho:

- Request đồng bộ.
- Background worker.
- Cache warm-up.
- Scheduled task.
- Health check.

Nếu warm-up dùng hết connection, request thật có thể bị chặn ngay khi Pod Ready. Nếu request pool quá lớn, worker nền có thể chiếm hết connection khi hệ thống đang phục hồi.

## 11. Cache warm-up và tránh thundering herd

Nhiều Pod cùng khôi phục local cache có thể tạo hàng loạt truy vấn đến Redis hoặc database.

### 11.1. Chỉ warm-up dữ liệu thiết yếu

Chia cache thành nhóm:

| Nhóm | Ví dụ | Chiến lược |
|---|---|---|
| Critical | Cấu hình và metadata cần cho mọi request | Nạp trước, có timeout |
| High-use | Key phổ biến | Warm-up theo batch |
| Optional | Dữ liệu ít dùng | Lazy load |
| Sensitive | Permission, token, session | Refresh hoặc kiểm tra nguồn |
| Versioned | Dữ liệu gắn generation | Giữ nếu version còn khớp |

Không nên xóa và nạp lại toàn bộ cache ở tất cả Pod nếu chỉ một phần dữ liệu cần refresh.

### 11.2. Batch và concurrency limit

Thay vì đọc 10.000 key đồng thời, chia thành batch nhỏ, giới hạn số batch chạy song song và đặt timeout cho mỗi batch.

Có thể dùng multi-get hoặc pipeline nếu Redis/database client hỗ trợ và semantics phù hợp. Batch giúp giảm round trip nhưng payload quá lớn có thể gây spike memory và latency.

### 11.3. Single-flight theo key

Trong cùng một Pod, nếu nhiều request cùng gặp cache miss, chỉ một request nên tải dữ liệu; những request khác chờ cùng kết quả hoặc dùng stale value nếu được phép.

Single-flight ở local chỉ ngăn trùng trong một Pod. Nhiều Pod vẫn có thể cùng refresh một key. Nếu cần phối hợp toàn fleet, có thể dùng distributed lock hoặc cache refresh coordinator, nhưng phải tính thêm độ phức tạp và tải của cơ chế đó.

### 11.4. TTL jitter

Tránh đặt cùng TTL cho hàng loạt entry hoặc Pod nếu việc hết hạn có thể đồng loạt. Thêm jitter vào expiry hoặc phân tán thời điểm warm-up giúp giảm đợt truy vấn đồng thời.

Với token, permission hoặc dữ liệu nhạy cảm, không được cộng jitter khiến dữ liệu được dùng vượt quá thời hạn hợp lệ.

## 12. Kiểm soát broker consumer và background worker

Khôi phục nhiều Pod có thể làm broker nhận một đợt lớn consumer mới. Việc tạo consumer đồng loạt có thể gây rebalance, tăng số heartbeat và làm thay đổi phân phối partition.

Cần cân nhắc:

- Giới hạn số consumer trên mỗi Pod.
- Khởi động consumer sau khi dependency và worker pool sẵn sàng.
- Chia đợt start consumer.
- Giới hạn số message đang xử lý đồng thời.
- Dùng backpressure khi worker queue đầy.
- Xử lý message pending hoặc được giao lại.
- Dùng idempotency để chịu được duplicate delivery.
- Chỉ ACK/commit sau khi xử lý nghiệp vụ đã được ghi nhận.

Nếu một Pod có 8 consumer và 30 Pod cùng restore, broker có thể phải xử lý 240 consumer mới trong thời gian ngắn. Cần so sánh với partition count và capacity của broker.

### 12.1. Phân biệt khởi động Pod và bắt đầu consume

Pod có thể đạt trạng thái process-ready trước khi bắt đầu consume. Một trình tự an toàn:

1. Restore JVM.
2. Khởi tạo connection và worker pool.
3. Kiểm tra broker.
4. Đăng ký consumer theo batch hoặc budget.
5. Xác nhận subscription và partition assignment.
6. Bắt đầu nhận message.
7. Đưa Pod vào trạng thái Ready cho vai trò worker.

Với worker không nhận HTTP traffic, readiness có thể được biểu diễn qua custom health state hoặc cơ chế controller riêng. Không nên dùng probe HTTP đơn giản chỉ để báo process đang sống nếu worker chưa thể nhận việc.

## 13. Kiểm soát warm-up request và health check

Warm-up request thường được thiết kế để làm nóng JIT, serializer hoặc cache. Nhưng nếu mọi Pod gọi cùng endpoint cùng lúc, hệ thống có thể tạo tải không khác gì traffic thật.

Nên:

- Chọn một tập nhỏ endpoint đại diện.
- Dùng read-only hoặc sandbox data.
- Giới hạn request đồng thời.
- Thêm jitter giữa các Pod.
- Dùng endpoint nội bộ hoặc warm-up mode có kiểm soát.
- Không warm-up mọi nhánh hiếm.
- Tránh warm-up đi qua hệ thống thanh toán hoặc side effect thật.

Health check cũng cần nhẹ. Nếu readiness mỗi 2 giây thực hiện một truy vấn nặng đến database từ 100 Pod, probe có thể tự tạo tải đáng kể.

Tốt hơn là ứng dụng cập nhật readiness state từ các kiểm tra đã được giới hạn tần suất, thay vì mỗi lần probe đều gọi tất cả dependency.

## 14. Circuit breaker, bulkhead và backpressure

Ba mẫu thiết kế này giúp ngăn một dependency chậm làm ảnh hưởng toàn bộ ứng dụng.

### 14.1. Circuit breaker

Circuit breaker theo dõi lỗi và latency. Khi lỗi vượt ngưỡng, nó tạm ngừng gửi request đến dependency để tránh tiếp tục tạo tải.

Các trạng thái phổ biến:

- Closed: cho phép request.
- Open: từ chối hoặc fallback trong một khoảng thời gian.
- Half-open: cho một số request thử để kiểm tra dependency đã phục hồi chưa.

Sau restore, không nên để mọi Pod cùng chuyển half-open và gửi probe ngay lập tức. Cần jitter hoặc giới hạn số probe trên mỗi khoảng thời gian.

### 14.2. Bulkhead

Bulkhead tách tài nguyên cho từng dependency hoặc workload. Ví dụ, pool Redis không dùng chung semaphore với database; warm-up không chiếm hết executor dành cho request.

Điều này giới hạn phạm vi ảnh hưởng khi một backend chậm.

### 14.3. Backpressure

Backpressure làm chậm hoặc từ chối công việc mới khi hệ thống không đủ capacity.

Ví dụ:

- Giới hạn queue size.
- Giới hạn concurrent request.
- Trả 429 hoặc 503 khi quá tải.
- Tạm dừng consumer khi worker queue đầy.
- Không mở thêm connection khi pool đã đạt giới hạn.

Không nên để queue không giới hạn. Queue lớn chỉ che giấu tình trạng quá tải và làm tăng latency, memory usage.

## 15. Tránh duplicate background work khi restore nhiều bản sao

Nếu nhiều Pod được tạo từ cùng một checkpoint, chúng có thể khôi phục cùng trạng thái heap. Điều này đặc biệt quan trọng với:

- Scheduler đã lên lịch một job.
- Counter hoặc sequence chỉ lưu trong memory.
- Singleton task.
- Leader election state.
- In-memory lock.
- Random generator hoặc ID generator có state.
- Consumer state.
- Job đang chạy tại thời điểm checkpoint.

Nếu mỗi Pod tiếp tục cùng một task, side effect có thể bị lặp nhiều lần.

### 15.1. Không dựa vào singleton trong heap để đảm bảo singleton toàn cluster

Một biến static hoặc singleton trong Spring context chỉ là singleton trong một process. Khi restore 20 Pod, có 20 bản sao của singleton đó.

Nếu một scheduled task phải chạy đúng một lần trên toàn hệ thống, cần cơ chế phân tán:

- Leader election.
- Distributed lease.
- Database job claim.
- Queue consumer group.
- Unique constraint hoặc idempotency key.

Sau restore, Pod phải xác nhận quyền sở hữu lease hiện tại trước khi tiếp tục công việc. Không dùng một lock object được khôi phục trong heap làm bằng chứng rằng Pod vẫn là leader.

### 15.2. Job cần nguồn trạng thái bền vững

Task nghiệp vụ nên được biểu diễn bằng job ID hoặc command descriptor lưu bền vững. Sau restore, Pod kiểm tra trạng thái job và claim theo cơ chế có tính nguyên tử.

Nếu nhiều Pod cùng nhìn thấy một job pending, chỉ một Pod được claim thành công. Các Pod còn lại tiếp tục lấy công việc khác.

### 15.3. Fencing và lease

Một lease có thể hết hạn trong lúc Pod bị checkpoint. Pod cũ restore sau đó có thể tưởng rằng nó vẫn giữ quyền sở hữu.

Fencing token hoặc generation tăng dần giúp hệ thống đích từ chối thao tác từ owner cũ. Với critical section quan trọng, chỉ kiểm tra một boolean trong heap là không đủ.

## 16. Ví dụ Java: readiness và giới hạn khởi tạo dependency

Ví dụ dưới đây minh họa một lifecycle coordinator ở cấp Pod. Các interface là abstraction của ứng dụng, không phải API có sẵn của CRaC hoặc Kubernetes.

~~~java
import java.util.concurrent.atomic.AtomicReference;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class PodRestoreResource implements Resource {

    public enum State {
        RESTORING,
        WAITING_FOR_CAPACITY,
        INITIALIZING,
        WARMING,
        READY,
        UNAVAILABLE
    }

    private final DependencyFactory dependencyFactory;
    private final WarmupService warmupService;
    private final ReadinessPublisher readiness;
    private final int maxConcurrentWarmups;

    private final AtomicReference<State> state =
            new AtomicReference<>(State.RESTORING);

    private volatile DependencyRuntime runtime;

    public PodRestoreResource(
            DependencyFactory dependencyFactory,
            WarmupService warmupService,
            ReadinessPublisher readiness,
            int maxConcurrentWarmups) {

        this.dependencyFactory = dependencyFactory;
        this.warmupService = warmupService;
        this.readiness = readiness;
        if (maxConcurrentWarmups <= 0) {
            throw new IllegalArgumentException(
                "maxConcurrentWarmups must be positive"
            );
        }
        this.maxConcurrentWarmups = maxConcurrentWarmups;

        readiness.notReady();
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        state.set(State.RESTORING);
        readiness.notReady();

        warmupService.stopAccepting();
        warmupService.drain();

        DependencyRuntime old = runtime;
        runtime = null;

        if (old != null) {
            old.close();
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {

        readiness.notReady();
        state.set(State.WAITING_FOR_CAPACITY);

        DependencyRuntime restored = null;

        try {
            state.set(State.INITIALIZING);

            restored = dependencyFactory.createAndConnect();

            restored.verifyRequiredDependencies();

            state.set(State.WARMING);
            warmupService.warmCriticalData(
                restored,
                maxConcurrentWarmups
            );

            warmupService.attach(restored);
            runtime = restored;
            warmupService.resumeAccepting();

            state.set(State.READY);
            readiness.ready();

        } catch (Exception e) {
            state.set(State.UNAVAILABLE);
            readiness.notReady();

            if (restored != null) {
                runtime = null;
                restored.close();
            }

            throw e;
        }
    }

    public State state() {
        return state.get();
    }
}
~~~

Ví dụ cho thấy một số nguyên tắc:

- Readiness được đặt về NOT_READY trong quá trình chuẩn bị.
- Warm-up nhận giới hạn concurrency cho từng Pod; `WarmupService` phải thực thi giới hạn đó bằng bounded executor hoặc semaphore.
- Dependency được tạo và kiểm tra trước khi mở admission.
- Nếu khởi tạo thất bại, Pod vẫn ở trạng thái unavailable.
- Runtime cũ được đóng trước checkpoint.

Giới hạn `maxConcurrentWarmups` trong ví dụ chỉ áp dụng bên trong một Pod. Nó không giới hạn tổng số Pod đang warm-up. Muốn có fleet-wide limit, cần một coordinator bên ngoài hoặc giới hạn rollout/scale. `WarmupService` cũng cần bảo đảm mọi task đã kết thúc hoặc được xử lý trước khi callback trả về.

Trong production, cần bổ sung timeout riêng cho connect, health check và warm-up; quản lý trạng thái lỗi khi `beforeCheckpoint()` thất bại; chỉ gán runtime mới sau khi kiểm tra và khởi tạo thành công; và xác định lifecycle của từng client theo đúng thư viện.

## 17. Ví dụ Kubernetes: Pod chỉ Ready sau khi dependency sẵn sàng

Một ứng dụng có thể cung cấp ba endpoint:

- `/health/startup`: JVM và quá trình restore đã hoàn tất giai đoạn khởi tạo cơ bản.
- `/health/ready`: dependency thiết yếu và warm-up critical đã sẵn sàng.
- `/health/live`: process vẫn có thể tiến triển, không bị deadlock hoặc hỏng nội bộ nghiêm trọng.

Ví dụ Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 8
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: registry.example.com/orders-api:2026.11
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /health/startup
              port: http
            periodSeconds: 5
            failureThreshold: 60
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

Cấu hình này minh họa một rollout có giới hạn surge và Pod chỉ nhận traffic khi readiness thành công. Nó không tự giới hạn số connection outbound mà callback tạo ra. Phần đó vẫn cần pool sizing, semaphore, retry budget và fleet-wide pacing.

### 17.1. PodDisruptionBudget không phải rate limiter

PodDisruptionBudget (PDB) giúp giới hạn số Pod có thể bị gián đoạn bởi các voluntary disruption thông qua eviction API, chẳng hạn một số thao tác drain node.

PDB không:

- Giới hạn số request mỗi Pod gửi đến database.
- Điều tiết reconnect đến Redis.
- Giới hạn HPA scale up.
- Thay thế Deployment rolling update strategy.
- Điều phối warm-up workload trên toàn fleet.

PDB hữu ích để giữ đủ capacity phục vụ trong một số tình huống bảo trì node, nhưng cần dùng đúng mục tiêu.

## 18. Tính toán batch size theo capacity dependency

Giả sử database có ngân sách 240 connection dành cho ứng dụng này. Các Pod đang phục vụ dùng tối đa 160 connection. Cần giữ 40 connection cho biến động traffic và tác vụ vận hành. Như vậy chỉ còn khoảng 40 connection dành cho giai đoạn restore.

Nếu mỗi Pod mới tạo tối đa 8 connection khi warm-up, số Pod có thể khởi tạo đồng thời theo ngân sách này là:

\[
N_{\text{batch}} \leq
\left\lfloor \frac{40}{8} \right\rfloor = 5
\]

Đây chỉ là ước lượng đơn giản. Cần cộng connection của ứng dụng khác, pool đang tăng theo tải, connection đang idle và các thao tác failover. Nên dùng số đo thực tế và giữ headroom.

### 18.1. Tính cả request rate

Connection count không phản ánh toàn bộ tải. Một connection có thể gửi hàng trăm request mỗi giây; nhiều connection khác có thể chỉ idle.

Nên tính cả:

- Request per second.
- Concurrent request.
- Query duration.
- Connection acquisition wait.
- CPU và I/O của dependency.
- Cache hit/miss.
- Authentication rate.
- Consumer count và rebalance rate.

Batch size nên dựa trên chỉ số giới hạn thực tế của dependency.

### 18.2. Bắt đầu nhỏ rồi tăng có điều kiện

Một quy trình rollout có thể:

1. Khôi phục một Pod.
2. Đợi Pod Ready và quan sát dependency trong một khoảng thời gian.
3. Kiểm tra connection count, latency và error rate.
4. Khôi phục thêm một batch nhỏ.
5. Tạm dừng nếu dependency vượt ngưỡng.
6. Tiếp tục khi hệ thống ổn định.

Cách này làm rollout chậm hơn nhưng cho phép điều chỉnh theo tải thực tế thay vì giả định capacity.

## 19. Thứ tự khởi tạo dependency

Một Pod có thể phụ thuộc vào nhiều dịch vụ. Không nên tạo tất cả connection và warm-up song song mà không xét dependency.

Ví dụ thứ tự:

1. Đọc configuration và secret hiện tại.
2. Thiết lập DNS/service discovery.
3. Kết nối đến dependency nền tảng cần thiết.
4. Xác thực và kiểm tra quyền.
5. Khởi tạo cache hoặc metadata cần thiết.
6. Khởi động worker pool.
7. Khôi phục consumer và subscription.
8. Chạy warm-up request.
9. Mở admission và readiness.

Thứ tự cụ thể phụ thuộc kiến trúc. Ví dụ, nếu Redis dùng để cấp restore token, Redis phải sẵn sàng trước bước lấy token. Nhưng nếu Redis đang là dependency bị bảo vệ, không nên tạo thêm một lượng lớn request coordinator vào chính Redis.

### 19.1. Khởi tạo tuần tự và song song có giới hạn

Một số dependency độc lập có thể khởi tạo song song, nhưng cần giới hạn concurrency. Dependency có quan hệ phụ thuộc phải khởi tạo theo thứ tự.

Có thể dùng một startup coordinator chia thành nhóm:

- Nhóm bắt buộc: database hoặc configuration service.
- Nhóm cache: Redis, local cache, metadata.
- Nhóm message: broker và consumer.
- Nhóm optional: telemetry exporter hoặc integration phụ.

Nếu dependency optional không sẵn sàng, ứng dụng có thể tiếp tục ở degraded mode nếu nghiệp vụ cho phép. Không nên để một exporter telemetry lỗi chặn toàn bộ Pod nếu nó không phải dependency phục vụ request.

## 20. Restore nhiều Pod và các tình huống đặc biệt

### 20.1. Nhiều Deployment cùng restore

Mỗi Deployment có thể cấu hình `maxSurge: 1`, nhưng nếu 10 Deployment cùng rollout thì có thể có 10 Pod mới cùng khởi tạo.

Cần phối hợp ở cấp release hoặc cluster:

- Đặt thứ tự rollout giữa các service.
- Dùng pipeline có approval/analysis step khi cần.
- Dùng restore coordinator dùng chung.
- Giới hạn tổng số warm-up đang chạy.
- Theo dõi dependency dùng chung.

### 20.2. Scale từ 0 lên nhiều replica

Scale từ 0 lên 50 replica không phải lúc nào cũng chịu cùng giới hạn như rolling update. Hãy giới hạn HPA scale-up, dùng batch hoặc controller riêng nếu cần khôi phục có kiểm soát.

### 20.3. Node restart hoặc zone recovery

Khi một node hoặc zone phục hồi, nhiều Pod có thể được schedule lại cùng lúc. PodDisruptionBudget không bảo vệ khỏi mọi loại sự cố ngoài dự kiến và không giới hạn reconnect storm sau node failure.

Cần có capacity planning, topology spread, giới hạn autoscaling và backoff ở ứng dụng.

### 20.4. Dependency cũng đang restore

Nếu database, Redis hoặc broker cũng đang phục hồi, ứng dụng không nên retry nhanh theo cùng nhịp. Dùng retry budget, jitter, circuit breaker và readiness. Có thể cần dependency startup order do platform orchestrator quản lý.

### 20.5. Checkpoint chứa scheduled task hoặc leader state

Nếu nhiều Pod được khôi phục từ cùng trạng thái, mỗi Pod có thể mang theo scheduled task giống nhau. Hãy xác định task nào chỉ được chạy một lần toàn hệ thống và chuyển ownership sang lease/leader election có fencing. Không dựa vào singleton trong heap.

## 21. Quan sát tải và điều kiện dừng rollout

Để điều phối fleet, cần theo dõi cả Pod lẫn dependency.

### 21.1. Metric cấp Pod

- Restore duration.
- Time to startup probe success.
- Time to readiness.
- Số lần reconnect.
- Số lần retry.
- Warm-up duration.
- Queue depth.
- Số connection active/idle.
- Số request warm-up.
- Readiness state và degraded state.

### 21.2. Metric cấp dependency

| Dependency | Metric nên theo dõi |
|---|---|
| Database | Active connections, connection wait, query latency, CPU, lock wait |
| Redis | Connected clients, command latency, rejected connections, memory |
| Message broker | Consumer count, rebalance, pending messages, lag |
| Identity provider | Token request rate, latency, 429/5xx, auth failure |
| HTTP service | Request rate, concurrent request, p95/p99, error rate |
| DNS/service discovery | Lookup latency, error rate, query volume |

### 21.3. Điều kiện pause

Có thể tạm dừng batch tiếp theo khi:

- Dependency latency vượt ngưỡng.
- Connection utilization gần giới hạn.
- Error rate tăng.
- Queue hoặc consumer lag tăng nhanh.
- Authentication provider trả 429.
- Số retry vượt retry budget.
- Pod mới không đạt readiness trong thời gian dự kiến.

Một rollout controller hoặc pipeline có thể dùng các điều kiện này để pause và tiếp tục sau khi hệ thống ổn định.

### 21.4. Log theo correlation

Nên gắn các log với Pod UID, application version, checkpoint ID và restore attempt. Không dùng một ID giống nhau cho mọi replica nếu cần phân biệt từng Pod.

Các sự kiện hữu ích:

- Restore started/completed.
- Dependency initialization started/completed.
- Restore budget acquired/released.
- Warm-up started/completed.
- Readiness changed.
- Consumer assignment completed.
- Retry exhausted.
- Rollout paused/resumed.

Không ghi credential hoặc payload nhạy cảm vào log.

## 22. Kiểm thử kịch bản khôi phục nhiều Pod

Kiểm thử một Pod đơn lẻ không đủ để phát hiện connection storm hoặc thundering herd. Cần kiểm thử cả fleet và dependency.

Các kịch bản nên có:

1. Một Pod restore trong điều kiện dependency khỏe.
2. Nhiều Pod restore đồng thời.
3. Restore theo batch nhỏ và theo batch lớn để so sánh.
4. HPA scale up trong khi database gần giới hạn connection.
5. Redis restart trong lúc nhiều Pod reconnect.
6. Identity provider trả 429 khi tất cả Pod refresh token.
7. Broker rebalance khi nhiều consumer cùng tham gia.
8. DNS chậm hoặc thay đổi endpoint.
9. Cache miss đồng loạt trên nhiều Pod.
10. Một Pod warm-up thất bại và giữ NotReady.
11. Dependency phục hồi sau một khoảng outage.
12. Pod bị kill khi đang giữ restore token hoặc lease.
13. Node restart khiến nhiều Pod được schedule lại.
14. Nhiều Deployment cùng rollout và dùng chung database.

Đo:

- Thời gian toàn fleet đạt desired ready replicas.
- Peak connection count.
- Peak request rate đến từng dependency.
- Dependency p95/p99 latency.
- Tỷ lệ 429, timeout và 5xx.
- Số retry và thời gian retry.
- Queue depth và message lag.
- Thời gian từ restore đến khi hệ thống ổn định.

Mục tiêu không chỉ là mọi Pod cuối cùng đều Ready. Cần chứng minh dependency không bị quá tải trong quá trình đạt trạng thái đó.

## 23. Quy trình triển khai thực tế

### Trước checkpoint

1. Xác định các dependency mà mỗi Pod sử dụng.
2. Tính ngân sách connection và request theo số replica tối đa.
3. Dừng công việc mới, drain task và listener.
4. Đóng hoặc chuẩn bị lại resource theo CRaC lifecycle.
5. Xác định background task nào không được nhân bản khi restore nhiều Pod.
6. Tạo checkpoint và gắn manifest/runtime profile phù hợp.

### Khi bắt đầu restore hoặc rollout

1. Giới hạn số Pod được tạo trong một batch.
2. Áp dụng HPA scale-up policy phù hợp.
3. Đặt Pod ở NOT_READY trong quá trình khởi tạo.
4. Cấp restore budget nếu cần giới hạn tổng warm-up.
5. Tạo connection và khởi tạo dependency theo concurrency limit.
6. Dùng retry với exponential backoff, jitter và retry budget.
7. Warm-up cache theo batch và chỉ cho dữ liệu thiết yếu.
8. Khôi phục consumer/subscription theo thứ tự.
9. Chỉ mở readiness sau khi chức năng cần thiết đã sẵn sàng.
10. Theo dõi dependency và pause batch kế tiếp nếu vượt ngưỡng.

### Sau khi fleet ổn định

1. Xác nhận số replica Ready đạt mục tiêu.
2. Kiểm tra connection count và request rate trở về mức bình thường.
3. Xác nhận không có job hoặc scheduled task bị chạy lặp.
4. Kiểm tra cache consistency và consumer lag.
5. Ghi lại thời gian restore và các metric để điều chỉnh batch size lần sau.

## 24. Checklist khôi phục nhiều Pod

### Điều phối fleet

- [ ] Có giới hạn số Pod được rollout hoặc restore đồng thời.
- [ ] HPA scale-up có policy và maxReplicas phù hợp.
- [ ] Nhiều Deployment dùng chung dependency được điều phối theo đợt.
- [ ] Có restore budget hoặc coordinator khi cần giới hạn tổng warm-up.
- [ ] Có điều kiện pause rollout khi dependency quá tải.

### Lifecycle ở mỗi Pod

- [ ] `afterRestore()` đặt ứng dụng ở trạng thái NOT_READY.
- [ ] Resource được tạo lại theo đúng ownership.
- [ ] Warm-up có concurrency limit và timeout.
- [ ] Retry có exponential backoff, jitter và retry budget.
- [ ] Consumer và scheduler chỉ hoạt động sau khi dependency sẵn sàng.
- [ ] Không tiếp tục leader lease hoặc lock cũ chỉ dựa trên heap state.

### Kubernetes health

- [ ] Startup probe có đủ thời gian cho restore.
- [ ] Readiness phản ánh khả năng phục vụ thật.
- [ ] Liveness không restart Pod chỉ vì dependency tạm thời chậm.
- [ ] PDB được dùng đúng mục đích voluntary disruption.
- [ ] Deployment strategy hoặc StatefulSet policy phù hợp với batch size.

### Dependency protection

- [ ] Pool size được tính theo tổng replica.
- [ ] Warm-up request được giới hạn.
- [ ] Có rate limit hoặc concurrency budget.
- [ ] Có circuit breaker, bulkhead và backpressure.
- [ ] Có fallback an toàn và không gây database stampede.
- [ ] Có metric về connection, latency, retry và queue.

### Kiểm thử

- [ ] Đã thử nhiều Pod restore đồng thời.
- [ ] Đã thử dependency chậm hoặc unavailable.
- [ ] Đã thử HPA scale up và node recovery.
- [ ] Đã thử consumer rebalance và cache invalidation.
- [ ] Đã thử Pod chết khi đang giữ restore token.
- [ ] Đã đo peak load và thời gian toàn fleet đạt Ready.

## 25. Câu hỏi thường gặp

### Kubernetes có tự điều phối callback CRaC giữa các Pod không?

Không. Callback CRaC chạy trong vòng đời của từng tiến trình Java. Kubernetes quản lý Pod và workload theo controller, nhưng không tự hiểu toàn bộ logic warm-up hoặc dependency của callback. Ứng dụng và cơ chế triển khai cần kết nối readiness, rollout và restore coordination.

### Nếu Pod chưa Ready thì nó có còn tạo tải lên database không?

Có. Readiness chủ yếu điều khiển việc Pod có nhận traffic từ Service hay không. Callback và background initialization vẫn có thể mở connection hoặc gửi request outbound. Cần giới hạn tải ở cấp ứng dụng và fleet.

### maxSurge: 1 có bảo đảm chỉ một Pod khởi động trong toàn cluster không?

Không. Nó áp dụng cho rolling update của một Deployment. HPA scale up, scale từ 0, Deployment khác hoặc controller riêng có thể tạo Pod cùng lúc. Cần thêm giới hạn ở các cơ chế đó.

### PodDisruptionBudget có ngăn connection storm không?

Không. PDB bảo vệ số Pod trước một số voluntary disruption qua eviction API. Nó không giới hạn outbound connection hoặc request đến dependency.

### Có nên dùng startup probe để chờ Redis và database không?

Startup probe có thể cho ứng dụng thời gian hoàn tất startup, nhưng không phải rate limiter. Readiness nên phản ánh dependency thiết yếu đã sẵn sàng; liveness không nên fail chỉ vì Redis hoặc database tạm thời chậm.

### Có nên warm-up toàn bộ cache trên mỗi Pod không?

Thường không. Chỉ warm-up dữ liệu cần thiết để phục vụ request ban đầu. Dữ liệu ít dùng có thể lazy load. Nếu nhiều Pod cùng warm-up, hãy dùng batch, jitter và giới hạn concurrency.

### Làm sao giới hạn tổng số Pod đang warm-up?

Có thể giới hạn rollout/scale, dùng controller cấp restore token hoặc rate limiter tập trung. Local semaphore chỉ giới hạn trong một Pod nên không đủ nếu cần ngân sách toàn fleet.

### Nếu database quá tải trong lúc restore thì sao?

Giữ Pod mới ở NotReady, giảm hoặc tạm dừng batch tiếp theo, giới hạn retry và connection creation, đồng thời dùng circuit breaker/backoff. Không để liveness restart hàng loạt Pod và tạo thêm reconnect storm.

### Có thể restore nhiều Pod từ cùng một checkpoint không?

Việc đó phụ thuộc nền tảng và cách đóng gói checkpoint. Nếu triển khai theo cách này, phải xem xét trạng thái heap bị nhân bản: scheduler, counter, random state, leader lease và job đang chạy. Mỗi Pod cần tạo identity phù hợp và xác minh quyền sở hữu công việc phân tán sau restore.

### Làm sao tránh scheduled job chạy lặp trên mọi Pod?

Dùng leader election, lease, durable job queue, atomic claim hoặc cơ chế idempotency. Singleton trong heap chỉ là singleton của một process, không phải singleton toàn cluster.

### Có cần đợi mọi Pod Ready mới bắt đầu nhận traffic không?

Không nhất thiết. Service có thể gửi traffic đến các Pod đã Ready trong khi những Pod khác đang restore, miễn là số Pod sẵn sàng đủ capacity và rollout policy cho phép. Cần giữ headroom và bảo đảm traffic không vượt capacity của nhóm Pod hiện có.

## Kết luận

Khôi phục nhiều Pod từ checkpoint có thể làm tải lên database, Redis, broker, identity provider và API bên ngoài tăng đột biến. Readiness probe giúp ngăn Pod chưa sẵn sàng nhận traffic inbound, nhưng không giới hạn các kết nối và request outbound do callback hoặc warm-up tạo ra. `maxSurge`, HPA policy, StatefulSet ordering và PDB cũng có phạm vi khác nhau; không công cụ nào một mình giải quyết toàn bộ dependency storm.

Một thiết kế bền vững kết hợp điều phối batch ở cấp fleet với concurrency limit ở từng Pod, connection budget theo tổng replica, retry có backoff và jitter, rate limit, circuit breaker, backpressure và readiness đúng nghĩa. Đồng thời, cần bảo vệ trạng thái nghiệp vụ khỏi bị nhân bản: scheduler, lock và job phải dùng lease, leader election hoặc nguồn trạng thái bền vững. Đo peak connection, request rate, dependency latency và thời gian toàn fleet đạt Ready trong thử nghiệm nhiều Pod sẽ giúp chọn batch size và warm-up policy phù hợp.
