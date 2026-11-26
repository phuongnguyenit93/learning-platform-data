# Dừng ứng dụng có kiểm soát và đóng tài nguyên SDK

## 1. Tại sao shutdown là một phần của tính đúng đắn dữ liệu?

Ứng dụng Spring Boot dùng **Spring Data Couchbase** đang có các yêu cầu đọc/ghi Order, truy vấn SQL++, tác vụ đồng bộ Inventory và các publisher reactive. Khi Kubernetes thực hiện rolling deployment hoặc một process nhận tín hiệu dừng, việc gọi `Cluster.disconnect()` ngay lập tức có thể cắt mất đường truyền của các thao tác vẫn đang chạy.

Một số tình huống thường gặp:

- `POST /orders` đã gửi mutation tới Couchbase, nhưng process ngắt kết nối trước khi nhận ACK. Client không biết đơn hàng đã tồn tại hay chưa.
- SQL++ `findByCustomerId` trả danh sách lâu do Index Service bận; web server đang dừng nhưng một worker vẫn cố gửi query mới qua SDK đã đóng.
- Transaction đang ghi Inventory và Order; shutdown không phối hợp khiến caller chưa nhận được trạng thái commit rõ ràng.
- WebFlux đã tạo `Mono` nhưng chưa subscribe; nếu tạo metric “đang chạy” ngay lúc tạo Publisher, drain sẽ đếm sai.
- Một `@Scheduled` task chạy mỗi vài giây vẫn tiếp tục phát sinh SDK requests trong khi HTTP đã ngừng tiếp nhận.
- Application tự tạo `ClusterEnvironment` riêng nhưng chỉ đóng `Cluster`, để lại resource do ứng dụng sở hữu.

Chương **Quan sát và vận hành** của module **SPRING_DATA_COUCHBASE** cần giải quyết trọn vẹn vòng đời tài nguyên. Module này học xây tầng truy cập bằng **document mapping, Repository, `CouchbaseTemplate`, SQL++**, thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive để bảo đảm hiệu năng, nhất quán, khả năng vận hành.

**Mục tiêu của bài học:**

1. Diễn giải quy trình dừng có kiểm soát ở HTTP, business workers, Repository/Template và Java SDK.
2. Phân biệt **graceful shutdown**, **forced termination**, crash và network partition.
3. Xác định ai sở hữu `Cluster`, `ClusterEnvironment`, `Bucket` và `Collection`; tránh đóng trùng hoặc rò rỉ.
4. Ngừng tiếp nhận tác vụ mới, theo dõi in-flight, chờ hữu hạn, xử lý quá hạn mà không giả báo thành công.
5. Thiết kế Spring Boot `SmartLifecycle`, Actuator readiness và cấu hình Kubernetes `SIGTERM`/grace period.
6. Xử lý đúng KV mutations, CAS, durability, SQL++/GSI, transactions, retry, WebFlux cancellation khi shutdown.
7. Ghi metrics/logs, kiểm thử và vận hành restart/rolling update an toàn.

> Nguyên tắc: **Không mở công việc mới trên client sắp đóng; không đóng tài nguyên còn được công việc cũ dùng; và không coi việc ngắt kết nối là bằng chứng write đã rollback.**

## 2. Phân biệt dừng bình thường, dừng cưỡng bức và sự cố kết nối

| Tình huống | Ứng dụng có cơ hội drain? | Điều đáng chú ý |
| --- | --- | --- |
| **Rolling deployment / SIGTERM** | Thường có, nếu process nhận signal và được cấp grace period | Dừng traffic, chờ in-flight, đóng SDK |
| **Operator chủ động stop** | Có thể có theo lifecycle của runtime | Cần thực hiện cleanup đúng thứ tự |
| **Kubernetes grace period hết rồi SIGKILL** | Không còn cơ hội hoàn tất mã cleanup | Các mutation đang chạy có thể ambiguous |
| **JVM crash, OOM kill, mất điện** | Không bảo đảm callback shutdown chạy | Phải có idempotency/recovery sau restart |
| **Mất mạng nhưng process sống** | App vẫn chạy nhưng Couchbase requests lỗi/chậm | Timeout/retry/circuit breaker, không phải quy trình đóng tài nguyên |
| **Couchbase failover/rebalance** | App thường không cần tự shutdown | SDK route/refresh topology, cần resilience |
| **Admin disable traffic / maintenance** | Có thể chủ động chuyển draining | Không tự restart mọi pod hoặc mất capacity |

**Graceful shutdown** là một kế hoạch *best effort có giới hạn thời gian*, không phải cam kết xử lý xong mọi tác vụ bất kể mất mạng, hết memory hoặc bị SIGKILL. Correctness phải đứng vững cả trong trường hợp shutdown không kịp chạy.

### 2.1. Một process có thể dừng sạch nhưng nghiệp vụ chưa hoàn tất

Nếu Controller đã kết thúc HTTP response 202 nhưng một job gửi email/payments vẫn chạy bên ngoài request lifecycle, HTTP graceful shutdown chưa chứng minh workflow đã hoàn tất. Cần quản lý riêng **background work, message acknowledgements, persistent job state** và recovery.

### 2.2. Một timeout không chứng minh mutation bị hủy

SDK có thể đã gửi `insert`/`replace` tới server, server áp dụng mutation rồi response bị mất khi ứng dụng đóng hoặc mạng gián đoạn. Idempotency key và readback/reconciliation vẫn cần thiết cho đường tạo đơn, bất kể shutdown được tổ chức tốt đến đâu.

## 3. Toàn cảnh trình tự dừng

~~~mermaid
sequenceDiagram
    participant K as Kubernetes / Orchestrator
    participant HTTP as Spring Web Server
    participant APP as Orders Service
    participant BG as Schedulers / Consumers
    participant SDK as Couchbase Java SDK
    participant CB as Couchbase Cluster

    K->>HTTP: Initiate termination
    HTTP->>HTTP: Stop accepting new HTTP work
    APP->>APP: Enter draining mode / refuse new DB work
    BG->>BG: Pause intake, stop new jobs
    Note over APP,BG: Track and wait for bounded in-flight operations
    APP->>SDK: Existing KV / Query / transaction operations
    SDK->>CB: Complete requests when possible
    CB-->>SDK: ACK / result / error
    SDK-->>APP: Observed outcome
    BG->>BG: Persist checkpoint / ack according to contract
    APP->>APP: Drain finishes or deadline expires
    APP->>SDK: Release owned SDK resources
    SDK->>SDK: Disconnect / shutdown environment as owned
    HTTP-->>K: Process exits
~~~

Đây là **thứ tự mục tiêu**. Cách các callback Spring thực thi phụ thuộc phiên bản Spring Boot, phases, bean dependencies và cách tạo client. Không tự kết luận shutdown callbacks luôn chạy cùng thứ tự với sơ đồ nếu chưa kiểm thử thực tế.

### 3.1. Ba lớp “ngừng nhận mới”

- **Ingress:** load balancer/Kubernetes không gửi request mới đến pod đang kết thúc.
- **Application gate:** business code từ chối công việc mới ngay cả khi còn request trên kết nối cũ.
- **Background producers:** scheduler, queue consumer, event listener, retry loop và async executor ngừng tạo DB calls.

Nếu chỉ thực hiện một lớp, SDK vẫn có thể bị gọi sau khi quá trình disconnect bắt đầu.

### 3.2. Hai lớp “chờ xong”

- **Web server drain:** các HTTP exchanges đang active có thời gian hoàn tất theo runtime.
- **Business operation drain:** các job/Publisher, transaction callbacks, message handlers và SDK calls do ứng dụng quản lý.

Hai con số này có thể khác nhau; không chỉ dùng HTTP active request count làm thước đo toàn bộ DB in-flight.

## 4. Sở hữu tài nguyên: ai có trách nhiệm đóng?

| Tài nguyên | Ai thường tạo | Nguyên tắc đóng |
| --- | --- | --- |
| **`Cluster` được Boot auto-configure** | Spring Boot/Spring Data context | Để lifecycle của Spring quản lý, xác minh destroy callback thực |
| **`Cluster` tự tạo bằng SDK** | Mã ứng dụng/bean factory riêng | Chủ sở hữu chịu trách nhiệm `disconnect()` khi không còn work |
| **`ClusterEnvironment` tự tạo** | Ứng dụng xây environment riêng | Chủ sở hữu shutdown environment theo SDK version, sau client |
| **Environment do SDK tạo/ngầm quản lý** | SDK/Cluster configuration | Không tự đóng hai lần qua tham chiếu mượn |
| **`Bucket`, `Scope`, `Collection` handles** | Lấy từ `Cluster` | Không coi chúng là client/socket pool độc lập phải đóng từng handle |
| **Spring Data Repository/Template** | Spring container | Không gọi `disconnect()` từ từng repository/service |
| **Task executors/schedulers riêng** | Application/Framework | Ngừng intake, drain, rồi shutdown theo ownership |
| **HTTP server/Actuator** | Spring Boot | Server graceful shutdown và lifecycle framework |
| **Message consumers** | Connector/messaging framework | Pause intake/ack/checkpoint theo contract, tránh mất/replay sai |

### 4.1. Một `Cluster` thường dùng cho nhiều collection

Không tạo `Cluster.connect` cho mỗi request, mỗi repository, mỗi health probe hoặc một customer ID. Kết nối mới mỗi request làm tăng bootstrap/TLS, giữ tài nguyên và gây reconnect storm trong rolling deploy. Dùng cluster bean chung với lifecycle được quản lý.

### 4.2. Không mượn bean rồi tự đóng

Một service tiêm `Cluster` từ Spring Boot không nghiễm nhiên là **chủ sở hữu**. Nếu service tự gọi `cluster.disconnect()` trong `@PreDestroy` của chính nó trong khi những bean khác còn sử dụng client, thứ tự destroy có thể làm hỏng các tác vụ cuối.

### 4.3. Shared environment cần đếm quyền sở hữu

Nếu nhiều SDK Cluster instances cùng dùng một `ClusterEnvironment` do application tạo, environment thường cần tồn tại cho tới khi **mọi cluster dùng nó đã ngừng**. Đừng đóng environment khi chỉ một client kết thúc. Ngược lại, nếu environment được SDK quản lý nội bộ, đừng shutdown nó lần nữa từ wrapper khác.

## 5. Ranh giới đóng `Cluster` và `ClusterEnvironment`

Với Java SDK 3.x, một client được ứng dụng sở hữu có thể được giải phóng khi hoàn tất tác vụ:

~~~java
// Minh họa: chỉ dùng nếu lớp hiện tại sở hữu cluster.
cluster.disconnect();
~~~

Khi app tự cấu hình environment cho SDK, thứ tự khái niệm là:

~~~text
Stop new requests / jobs
  -> bounded drain of in-flight work
  -> disconnect each application-owned Cluster
  -> shutdown application-owned ClusterEnvironment
  -> close remaining owned executors / exporters
~~~

**Lưu ý về API cụ thể:** SDK cung cấp cách tạo/đóng environment theo phiên bản. Cần xác minh method như `environment.shutdown()`, semantic shutdown completion và thread resources trên SDK version đang dùng trước khi copy code production. Không trộn hướng dẫn dành cho SDK 2.x với Java SDK 3.x.

### 5.1. Không tự đóng `Bucket` hoặc `Collection` như socket độc lập

Các đối tượng `Bucket`/`Scope`/`Collection` trong Java SDK 3.x là handles qua client/context, không phải nơi phải tự mở/đóng TCP connection cho từng operation. Khi cluster được đóng đúng, các tài nguyên transport gắn với cluster được release theo SDK lifecycle.

### 5.2. Kiểm tra Spring Boot auto-configuration

Nếu project sử dụng `spring-boot-starter-data-couchbase`, Spring context thường tạo các beans SDK/Spring Data. Cần xác minh bean ownership và destroy semantics của phiên bản Spring Boot/Spring Data thực: **không thêm một destroy callback thứ hai chỉ vì thấy code sample gọi `disconnect()`**.

### 5.3. Đóng SDK không phải “flush hết mọi pending mutation”

`disconnect()` kết thúc vòng đời client; không thể dùng nó làm bằng chứng rằng mọi request đã ACK, mọi transaction đã commit, hay mọi GSI đã bắt kịp. Muốn bảo đảm workflow, phải chờ operation-level results và lưu trạng thái domain trước khi đóng.

## 6. Spring Boot graceful shutdown: cấu hình đầu tiên cần có

Với những phiên bản Spring Boot hỗ trợ, cấu hình:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

**Ý nghĩa:**

- `server.shutdown=graceful` yêu cầu embedded web server xử lý shutdown theo cơ chế graceful được hỗ trợ, thay vì cắt ngay các exchanges đang hoạt động.
- `spring.lifecycle.timeout-per-shutdown-phase` đặt ngân sách chờ **mỗi phase** của Spring lifecycle; không phải lời hứa tổng thời gian JVM sẽ dừng trong đúng 30 giây.
- Việc server ngừng nhận kết nối mới và xử lý các request đang hoạt động có khác biệt theo Tomcat/Jetty/Reactor Netty/Undertow và phiên bản.
- Background consumers, `@Async` và những task được tự tạo ngoài request lifecycle **không tự động** được tính là toàn bộ HTTP in-flight.

### 6.1. Phải đối chiếu với Kubernetes grace period

Nếu một phase chờ 30 giây, worker drain cũng 30 giây, SDK close còn cần thời gian, thì `terminationGracePeriodSeconds=30` có thể quá ngắn. Thiết kế **ngân sách tổng** bao gồm preStop, ingress propagation, app drain, SDK cleanup và một biên an toàn.

### 6.2. Không chỉ thêm YAML rồi coi là xong

Một `@Scheduled` task vẫn phát sinh SQL++ query trong khi server ngừng HTTP, hoặc một class gọi SDK từ shutdown hook tự viết, có thể tạo request mới đúng lúc client đang đóng. Phải xem toàn bộ producers/consumers và ownership.

### 6.3. Không dùng `Thread.sleep` không giới hạn

Một lệnh sleep trong `@PreDestroy` không chứng minh mọi tác vụ đã hoàn tất, đồng thời ăn hết shutdown budget. Cần **đếm in-flight và chờ có timeout**, có logs rõ số requests chưa kết thúc.

## 7. Trình tự thực hiện ở mức nghiệp vụ

Một stop sequence đề xuất:

1. Công bố trạng thái **DRAINING** có timestamp, instance ID và reason (deployment, maintenance, operator).
2. Ngừng cấp phát request mới qua readiness/ingress theo thiết kế.
3. Chặn business DB operations mới tại app admission gate; trả lỗi an toàn nếu cần.
4. Pause queue/message consumers và tắt phát sinh công việc từ scheduler.
5. Hạn chế bắt đầu retry mới khi không còn đủ thời gian cho logical operation.
6. Theo dõi các KV reads, writes, SQL++ queries, transactions và reactive subscriptions đang active.
7. Chờ chúng hoàn thành trong ngân sách đã định; xử lý outcome thật.
8. Lưu checkpoint/offset/ack của consumer chỉ sau khi xử lý đạt contract.
9. Đánh dấu các write/transaction ambiguous cho reconciliation thay vì giả báo rollback.
10. Dừng background executors theo ownership.
11. Đóng `Cluster` và `ClusterEnvironment` thuộc quyền sở hữu của ứng dụng; để Spring đóng những beans do Spring quản lý.
12. Emit các metrics/log shutdown final nếu pipeline còn hoạt động, rồi đóng exporter/logging resources theo framework.
13. Process exit trước khi orchestrator cần dùng SIGKILL.

### 7.1. Cửa sổ nhận request mới không thể tuyệt đối bằng 0

Load balancer/kube-proxy/endpoints controller có propagation delay; keep-alive connections cũng có thể còn request in transit. Vì vậy bên cạnh readiness, **application gate** vẫn cần phản hồi có kiểm soát khi DRAINING thay vì tiếp tục tạo DB work tới cuối cùng.

### 7.2. Tránh tạo deadlock trong quá trình drain

Nếu task A chờ task B được enqueue vào cùng executor đã ngừng chấp nhận việc mới, “chờ mọi task hoàn tất” có thể bế tắc. Quy tắc ngừng producer trước nhưng vẫn cho phép **work continuation cần thiết để hoàn thành in-flight** cho tới khi drain kết thúc; phân biệt top-level new job và child task của job đang chạy.

## 8. Code: admission gate đồng bộ đếm in-flight an toàn

Ví dụ Java 17 dưới đây là một **gate của ứng dụng**, không phải SDK pending queue. Nó ngừng nhận operations mới khi `beginDrain()` được gọi, và cung cấp `awaitDrain` có timeout.

~~~java
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public final class OrderDbGate {
    private final AtomicBoolean accepting = new AtomicBoolean(true);
    private final AtomicInteger inFlight = new AtomicInteger();
    private final CompletableFuture<Void> drained =
            new CompletableFuture<>();

    public <T> T execute(Supplier<T> dbOperation) {
        if (!accepting.get()) {
            throw new DrainingException();
        }

        inFlight.incrementAndGet();

        // Kiểm tra lại để khép race với beginDrain().
        if (!accepting.get()) {
            release();
            throw new DrainingException();
        }

        try {
            return dbOperation.get();
        } finally {
            release();
        }
    }

    public void beginDrain() {
        accepting.set(false);
        if (inFlight.get() == 0) {
            drained.complete(null);
        }
    }

    public boolean awaitDrain(Duration budget)
            throws InterruptedException {
        try {
            drained.get(budget.toMillis(), TimeUnit.MILLISECONDS);
            return true;
        } catch (TimeoutException exceeded) {
            return false;
        } catch (ExecutionException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    public int inFlight() {
        return inFlight.get();
    }

    public boolean accepting() {
        return accepting.get();
    }

    private void release() {
        int remaining = inFlight.decrementAndGet();
        if (remaining == 0 && !accepting.get()) {
            drained.complete(null);
        }
    }

    public static final class DrainingException
            extends RuntimeException {
        public DrainingException() {
            super("Application is draining");
        }
    }
}
~~~

**Phạm vi và giới hạn:**

- Chỉ đếm operations thực sự chạy **qua gate này**; mọi đường bỏ qua gate vẫn có thể dùng SDK khi shutdown.
- Double-check sau increment ngăn một task đã đọc `accepting=true` nhưng chưa được tính in-flight truy cập SDK sau khi drain báo rỗng.
- Nếu drain bắt đầu trước increment, request bị từ chối sau second check và không gọi DB.
- Một operation đang chạy lúc bắt đầu drain vẫn được phép kết thúc; shutdown chờ nó.
- `awaitDrain` trả `false` khi timeout; **không tự cancel operation** hay chứng minh server đã rollback.
- Không bật lại `accepting=true` sau drain trên cùng instance nếu không thiết kế lại lifecycle và future state.
- Gate này đồng bộ; không dùng `execute(Supplier<Mono<T>>)` để đo reactive I/O, vì nó chỉ đếm lúc tạo Publisher.

### 8.1. Không biến gate thành nơi retry vô hạn

Nếu `execute` bọc một Repository method có retry 10 phút, gate vẫn thấy nó in-flight nhưng shutdown timeout. Dùng deadline/attempt budget ở tầng thấp và tắt nguồn new retries khi DRAINING theo domain policy.

### 8.2. Map lỗi DrainingException thành response có ý nghĩa

Với request mới vừa tới trong cửa sổ drain, có thể trả 503/`Retry-After` theo API contract; riêng mutation timeout/unknown-outcome phải trả thông tin tránh retry mù. Đừng catch `DrainingException` rồi trả HTTP 200 hoặc danh sách rỗng.

## 9. Kết nối gate với Repository/Service

Giả sử Spring Data Repository trả `Optional<OrderDocument>` theo key:

~~~java
import java.util.NoSuchElementException;
import org.springframework.stereotype.Service;

@Service
public final class OrderReadService {
    private final OrderRepository repository;
    private final OrderDbGate gate;

    public OrderReadService(
            OrderRepository repository,
            OrderDbGate gate) {
        this.repository = repository;
        this.gate = gate;
    }

    public OrderDocument get(String id) {
        return gate.execute(() ->
                repository.findById(id)
                        .orElseThrow(NoSuchElementException::new));
    }
}
~~~

Bean `OrderDbGate` phải được đăng ký đúng trong Spring context (ví dụ qua `@Bean` hoặc `@Component`). `OrderRepository` là interface cụ thể do Spring Data tạo với entity phù hợp.

### 9.1. Domain operation lớn hơn một DB call

Nếu tạo Order gồm validate → KV insert → publish event, đặt gate chỉ quanh `insert` chưa chắc drain đã tính thời gian publish/checkpoint; đặt **logical-work gate** quanh toàn bộ operation khi nghiệp vụ cần. Có thể có metric `logicalInFlight` và `dbInFlight` riêng, không dùng chung một số với hai nghĩa khác nhau.

### 9.2. Lỗi business không được đếm là shutdown failure

Một Order không tồn tại và `findById` trả empty có thể là HTTP 404 bình thường. Gate vẫn giảm in-flight qua `finally`, nhưng metric/error classifier nên phân biệt not-found với timeout/SDK unavailable.

## 10. `SmartLifecycle` để ngừng work trước khi Spring hủy beans

Spring cung cấp `SmartLifecycle` để các components quản lý start/stop và **phase**. Khi context đóng, `stop(Runnable callback)` cho phép một component thực hiện shutdown bất đồng bộ, rồi báo callback khi xong; framework có thể chờ trong budget cấu hình.

Ví dụ tối giản dùng `OrderDbGate` ở mục 8:

~~~java
import java.time.Duration;

import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public final class OrdersDrainLifecycle implements SmartLifecycle {
    private final OrderDbGate gate;
    private volatile boolean running;

    public OrdersDrainLifecycle(OrderDbGate gate) {
        this.gate = gate;
    }

    @Override
    public void start() {
        running = true;
    }

    @Override
    public void stop(Runnable callback) {
        gate.beginDrain();

        Thread drainThread = new Thread(() -> {
            try {
                boolean clean =
                        gate.awaitDrain(Duration.ofSeconds(20));
                // Ghi metric/log clean, gate.inFlight()
                // và shutdown duration trước khi trả callback.
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            } finally {
                running = false;
                callback.run();
            }
        }, "orders-drain");

        drainThread.start();
    }

    @Override
    public void stop() {
        gate.beginDrain();
        try {
            gate.awaitDrain(Duration.ofSeconds(20));
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        } finally {
            running = false;
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
~~~

**Các giới hạn triển khai:**

- `start` ở đây không mở kết nối: Spring đã tạo/tiêm client theo cấu hình context.
- `stop(Runnable)` báo callback **sau khi chờ hoặc hết ngân sách**, không block thread lifecycle caller vô hạn.
- Khi timeout, callback vẫn cần báo để framework không bị treo; **các operation chưa xong vẫn có outcome chưa rõ** và phải có domain recovery.
- `getPhase=0` chỉ minh họa; SmartLifecycle dừng phase cao trước phase thấp. Cần kiểm thử phase của web server, consumers và SDK-owning beans trên Spring Boot version thật.
- Đừng tạo nhiều bean cùng cố điều khiển cùng gate mà không thống nhất owner.
- Đừng dùng giải pháp này làm workaround nếu framework/consumer đã có graceful shutdown management; cần tích hợp để không cạnh tranh/đóng trùng.

### 10.1. Phase không thay thế dependency ordering

Dù `SmartLifecycle` cho phép dừng sớm một số producers, Java bean destruction và `@PreDestroy` của custom Cluster wrapper vẫn có thứ tự dựa trên dependency/context. Luôn kiểm tra bằng integration test xem **không có DB call nào phát sinh sau khi SDK đóng**.

### 10.2. Không xây một thread riêng mỗi request

Thread ở ví dụ chỉ được tạo **một lần lúc shutdown**. Không tạo thread cho từng request để “đợi SDK”; việc làm đó tăng resource và làm drain khó kiểm soát. Trong hệ thống lớn, có thể dùng một lifecycle executor được quản lý, với shutdown policy rõ.

## 11. `@PreDestroy` dùng đúng khi nào?

`@PreDestroy` (Jakarta trên Spring Boot 3+) chạy trong quá trình hủy bean, phù hợp giải phóng tài nguyên **do chính bean sở hữu**.

~~~java
import jakarta.annotation.PreDestroy;

public final class OwnedResourceCleanup {
    private final SomeApplicationOwnedResource resource;

    public OwnedResourceCleanup(SomeApplicationOwnedResource resource) {
        this.resource = resource;
    }

    @PreDestroy
    public void closeOwnedResource() {
        resource.close();
    }
}

// SomeApplicationOwnedResource minh họa một tài nguyên
// do ứng dụng sở hữu, không phải bean Cluster mượn từ Boot.
~~~

Ở ví dụ này, `SomeApplicationOwnedResource` là interface/class do ứng dụng cung cấp, không phải API Couchbase. Mục tiêu là minh họa ownership boundary, **không** bảo rằng mọi `@PreDestroy` nên gọi SDK disconnect.

### 11.1. Khi nào không nên gọi `cluster.disconnect()` trong `@PreDestroy` của service?

Nếu `Cluster` được Spring Boot tạo và shared bởi Repository, Template, health indicator và các workers, một service không nên chủ động đóng cluster khi bean của nó bị destroy. Để bean owner/framework xử lý, với lifecycle drain đã hoàn tất trước đó.

### 11.2. Callback không được giả định chạy lúc crash/SIGKILL

`@PreDestroy` hoặc JVM shutdown hook không bảo đảm chạy khi kernel kill, host mất điện, OOM kill hoặc process bị force terminate. Do đó một Order operation phải an toàn với **at-least-once delivery**, duplicate retry hoặc unknown write outcome ngay cả khi không có cleanup.

### 11.3. Tránh đăng ký cùng cleanup ở nhiều cơ chế

Một resource có cả `@PreDestroy`, `DisposableBean.destroy`, `@Bean(destroyMethod=...)` và JVM shutdown hook có thể bị close lặp hoặc sai phase. Chọn **một owner** và một contract đóng; nếu API close idempotent thì vẫn không nên dựa vào đó để che lỗi ownership.

## 12. Dừng nguồn công việc: scheduler, queue consumer và async worker

HTTP ngừng nhận traffic chỉ ngăn một đường input. Hệ thống thực tế còn:

- `@Scheduled` task quét Orders hết hạn hoặc tổng hợp báo cáo.
- `@Async`/`ThreadPoolTaskExecutor` chạy tác vụ nền.
- Kafka/RabbitMQ/queue listener hoặc custom poller xử lý event.
- Reactor stream liên tục, retry loops, interval timers.
- Transaction cleanup/reconciliation jobs.
- Application startup/shutdown listeners kích hoạt workload phụ.

**Trình tự phù hợp:**

1. Mark draining, không nhận **top-level jobs** mới.
2. Pause/stop polling/consumption theo APIs của framework.
3. Cho phép những subtasks cần thiết của in-flight work kết thúc.
4. Chờ có timeout; ghi outstanding work, retry/cancel status.
5. Acknowledge/checkpoint những message đã xử lý đúng contract.
6. Giữ message chưa xử lý để có thể redeliver, dùng idempotency để chống duplicate.
7. Shutdown executor/publisher/consumer do app sở hữu, rồi mới đóng SDK.

### 12.1. Không ack message trước khi write được xác minh

Nếu consumer nhận Order event, ack Kafka message trước khi KV write có ACK/durability phù hợp, process có thể chết và mất cơ hội retry. Nếu write đã ACK rồi process chết trước ack, message có thể được xử lý lại; vì vậy **idempotent writes** là thiết kế mặc định đáng tin cậy.

### 12.2. Không chờ mọi `CompletableFuture` mà quên child tasks

Có thể có future không được quản lý, fire-and-forget `subscribe()` hoặc job chạy trong executor khác. Trước khi cam kết “drain complete”, inventary các luồng tạo công việc và áp dụng structured ownership/ack tracking.

### 12.3. Stop retries khi đang drain

Không phát thêm application retries sau khi shutdown deadline đã gần hết; nếu outcome một write chưa rõ, lưu logical command state để recovery thay vì giữ pod sống vô hạn.

## 13. Executor shutdown và các nguy cơ deadlock

Với Spring `ThreadPoolTaskExecutor` hoặc `TaskScheduler`, configuration về chờ tasks kết thúc có thể phụ thuộc Spring Boot và Spring Framework version. Ví dụ định hướng, cần xác nhận properties/version thực:

~~~yaml
spring:
  task:
    execution:
      shutdown:
        await-termination: true
        await-termination-period: 20s
    scheduling:
      shutdown:
        await-termination: true
        await-termination-period: 20s
~~~

**Đừng hiểu** những property này là đảm bảo mọi custom thread/executor do ứng dụng tự `new` đều được Spring quản lý. Khi app tạo `ExecutorService` riêng, app là owner và phải quản lý `shutdown`/`awaitTermination`/`shutdownNow` theo contract.

### 13.1. `shutdownNow()` chỉ yêu cầu hủy, không cam kết hủy remote write

Interrupt/cancel một thread đang chờ SDK không bảo đảm server chưa áp dụng mutation. Không dùng nó như một rollback primitive. Với transaction, dùng recovery/SDK transaction semantics thực, không tự assert commit đã rollback.

### 13.2. Phải tránh deadlock khi ngừng executor quá sớm

Một request đang xử lý chờ callback được schedule lên executor đã shutdown sẽ không bao giờ hoàn tất. Ngừng nguồn **top-level new work** trước, nhưng giữ tài nguyên phục vụ tasks đang hoạt động đủ lâu để drain xong.

### 13.3. Không để drain vượt quá grace period tổng

Chờ 20 giây ở HTTP, tiếp 20 giây ở scheduler, rồi 20 giây ở SDK close có thể vượt Kubernetes grace 30 giây. Mỗi phase có budget riêng nhưng phải tính được **upper bound tổng** và có margin.

## 14. SQL++ query đang chạy và result materialization lúc shutdown

Một `CouchbaseRepository.findByCustomerId` hoặc `CouchbaseTemplate.findByQuery` có thể thực thi SQL++ và mapping ra entity. Cần xác định **khi nào DB operation được coi là hoàn thành**:

| Mốc | Đã hoàn tất toàn logical request? |
| --- | --- |
| Gửi query tới SDK | Chưa |
| Query Service bắt đầu chạy | Chưa |
| SDK nhận một phần rows | Chưa chắc |
| API trả `QueryResult` nhưng rows chưa materialize theo caller | Phụ thuộc API/cách dùng |
| Repository đã trả danh sách entities đầy đủ | Có thể hoàn tất DB call, chưa chắc HTTP serialization |
| HTTP response gửi xong | Hoàn tất request theo web server instrumentation |

### 14.1. Đừng đóng SDK khi row stream còn active

Với streaming query/results reactive, một HTTP exchange có thể tiếp tục đọc rows sau khi handler trả Publisher. Gate phải bám **subscription lifecycle**, không chỉ lúc controller method trả về.

### 14.2. Consistency wait không được xem là “connection leak”

SQL++ `REQUEST_PLUS` có thể chờ GSI cập nhật, đặc biệt sau đợt writes lớn hoặc failover/rebalance. Khi drain timeout, hãy ghi query consistency mode, Index backlog/Query wait nếu có, không gán mọi chậm trễ là SDK không đóng socket.

### 14.3. Không chạy DDL hoặc heavy scan trong shutdown hook

Tạo, xóa hay rebuild index khi ứng dụng dừng có thể tốn tải và làm stop chậm. Schema migration thuộc workflow triển khai có kiểm soát, không là nhiệm vụ của `@PreDestroy`.

## 15. Timeout, deadline và ngân sách shutdown

Tại thời điểm nhận `SIGTERM`, ứng dụng có thể đang xử lý một request với HTTP deadline dài hơn thời gian orchestrator cho phép. Cần xác định nguyên tắc **ngân sách tổng**.

~~~text
Kubernetes termination grace window    ví dụ 70s
  Optional preStop/drain signal          một phần
  Ingress/endpoints propagation         một phần
  HTTP graceful stop                    tới giới hạn framework
  Worker/DB in-flight drain             ví dụ tối đa 25s
  SDK close / environment shutdown      cần biên dự phòng
  Final logs/exit                       phần còn lại
~~~

Các con số chỉ để minh họa, không phải timeout mặc định chuẩn. Ngân sách có thể **chồng lấn** giữa phases, nhưng không được lấy các cấu hình độc lập rồi giả sử tổng tự vừa termination grace.

### 15.1. Quy tắc deadline cho công việc đang chạy

- Work mới phải bị từ chối khi draining.
- Work cũ chỉ tiếp tục nếu còn khả năng hoàn thành trong deadline hợp lý.
- Retry/backoff phải xét **remaining total budget**, không làm lại full timeout mỗi attempt.
- Nếu không thể xác minh kết quả write trước deadline, lưu trạng thái uncertain theo workflow đã thiết kế.
- Khi hết budget, log outstanding count/operation category; không chặn JVM vô hạn.

### 15.2. SIGKILL có thể đến sớm hơn dự tính

Node crash, eviction conditions, operator force-delete hoặc runtime issues có thể cắt thời gian; không có shutdown code nào bảo đảm xử lý mọi trường hợp. Business correctness cần chống duplicate/replay từ đầu.

## 16. Reactive WebFlux: phải drain theo subscription, không theo method call

Với `ReactiveCouchbaseRepository`/`ReactiveCouchbaseTemplate` hoặc SDK reactive, việc tạo `Mono`/`Flux` chưa chắc thực hiện I/O. Code sau **không đếm đúng**:

~~~java
// Sai: chỉ đếm lúc tạo Mono, không đếm I/O thực tế.
inFlight.incrementAndGet();
Mono<OrderDocument> publisher = repository.findById(id);
inFlight.decrementAndGet();
return publisher;
~~~

Một subscription có thể xuất hiện sau khi Controller đã trả Publisher, và HTTP client có thể cancel trước khi Server operation hoàn tất. Drain phải bao trùm **thời gian subscription hoạt động**.

### 16.1. Reactive gate tối giản

Dùng lại cách kiểm soát tương tự `OrderDbGate` nhưng đặt việc nhận/giảm in-flight vào `Mono.defer` và `doFinally`.

~~~java
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Mono;

public final class ReactiveDbGate {
    private final AtomicBoolean accepting = new AtomicBoolean(true);
    private final AtomicInteger active = new AtomicInteger();
    private final CompletableFuture<Void> drained =
            new CompletableFuture<>();

    public <T> Mono<T> guard(Mono<T> source) {
        return Mono.defer(() -> {
            if (!accepting.get()) {
                return Mono.error(
                        new OrderDbGate.DrainingException());
            }

            active.incrementAndGet();

            if (!accepting.get()) {
                release();
                return Mono.error(
                        new OrderDbGate.DrainingException());
            }

            return source.doFinally(signal -> release());
        });
    }

    public void beginDrain() {
        accepting.set(false);
        if (active.get() == 0) {
            drained.complete(null);
        }
    }

    public boolean awaitDrain(Duration budget) throws Exception {
        try {
            drained.get(
                    budget.toMillis(), TimeUnit.MILLISECONDS);
            return true;
        } catch (java.util.concurrent.TimeoutException timeout) {
            return false;
        }
    }

    public int active() {
        return active.get();
    }

    private void release() {
        if (active.decrementAndGet() == 0 && !accepting.get()) {
            drained.complete(null);
        }
    }
}
~~~

**Giải thích ranh giới:**

- `Mono.defer` kiểm tra gate **mỗi lần subscribe**, không phải khi tạo Publisher.
- Nếu drain bắt đầu trước subscription, subscriber mới nhận lỗi, không gọi SDK.
- Một subscription đang active khi drain bắt đầu được cho cơ hội hoàn tất.
- `doFinally` chạy ở complete, error hoặc cancel để giảm count.
- Khi downstream cancel, `active` có thể về 0 nhưng không bảo đảm remote write đã rollback hoặc server dừng xử lý ngay.
- `awaitDrain` dùng blocking wait **chỉ trong thread quản lý shutdown**, không bao giờ gọi trên Reactor Netty event loop.
- Ví dụ này bao bọc **Mono**. Với `Flux` dùng `Flux.defer` và terminal/cancellation tracking tương tự.

### 16.2. Reactive retry làm thay đổi nghĩa của “active”

Nếu `guard` nằm trong `retryWhen`, mỗi subscription attempt có thể được tính riêng; nếu `guard` nằm ngoài, nó có thể đo cả logical operation và các đợt retry. Phải quyết định drain cần đợi **logical business workflow** hay chỉ một SDK attempt; với write, an toàn nghiệp vụ quan trọng hơn việc gauge về 0 nhanh.

### 16.3. Không `block()` để “bảo đảm đã xong”

~~~java
// Phản ví dụ trong WebFlux event loop:
OrderDocument order = reactiveRepository.findById(id).block();
~~~

Lệnh block không làm transaction/SDK an toàn hơn; nó có thể gây thread starvation, kéo dài shutdown và biến p99 HTTP thành lỗi thứ cấp.

## 17. Cancellation: khác biệt giữa hủy phía client và outcome phía Couchbase

Một HTTP client đóng kết nối trong khi `Mono<MutationResult>` chưa phát result. Reactor có thể phát cancel signal; JVM có thể thôi chờ. Tuy nhiên:

1. Request có thể đã được gửi tới Data Service.
2. Server có thể đã áp dụng mutation.
3. ACK có thể đang trên đường hoặc đã thất lạc.
4. SDK/framework có thể có cancellation semantics riêng theo operation.
5. Application có thể không nhận mutation token/CAS result.
6. Transaction commit outcome cũng có thể không rõ với caller.

**Không diễn giải `doOnCancel` là “mutation không xảy ra”.** Với Order/Inventory/Payment, lưu logical command ID và thực hiện readback/reconciliation khi có thể, kể cả khi request HTTP đã bị hủy.

### 17.1. Streaming SQL++/Query

Nếu endpoint stream một `Flux<Row>`, cần theo dõi:

- time-to-first-row,
- total stream duration,
- rows emitted/consumed,
- cancel/error/complete,
- SDK Query result/cursor lifecycle theo API thực,
- downstream HTTP write completion.

Một stream bị client cancel sau 5 rows không có nghĩa Query Service không thực hiện phần còn lại; khi drain, xử lý cancellation theo contract của SDK/version.

### 17.2. Fire-and-forget tạo “công việc vô chủ”

Code không nên dùng:

~~~java
reactiveRepository.save(order).subscribe();
return Mono.just("saved");
~~~

HTTP trả thành công **trước** khi server xác nhận write; drain khó biết Publisher này còn chạy. Trả Publisher đúng lên framework hoặc đưa job vào hệ thống background có ownership/persistent state, không tự `subscribe()` rồi bỏ kết quả.

## 18. Retry và circuit breaker trong lúc draining

Shutdown không phải thời điểm tốt để khởi động một chuỗi retry kéo dài:

| Tình huống | Chính sách nên xem xét |
| --- | --- |
| KV read transient failure, còn deadline | Retry hữu hạn nếu budget và operation semantics cho phép |
| New HTTP request khi draining | Reject ngay, không tạo DB operation mới |
| In-flight read đã retry nhiều lần | Giới hạn attempts theo remaining shutdown/HTTP deadline |
| KV insert timeout, outcome ambiguous | Không tạo document ID mới; verify/reconcile |
| SQL++ `REQUEST_PLUS` chờ GSI | Có thể hết drain budget; không hạ consistency lén lút |
| Transaction commit unknown | Cần domain-state reconciliation |
| Breaker mở vì Query outage | Không half-open bằng hàng loạt heavy queries trên pod đang đóng |
| Queue consumer nhận message cuối | Giữ ack/checkpoint đúng contract, tránh mất việc |

### 18.1. Không trộn lỗi draining với outage của database

Một `DrainingException` xuất phát từ app gate có nghĩa ứng dụng **cố ý không nhận công việc mới**. Nó nên có metric riêng như `reason=draining`, không đưa vào thống kê `couchbase_timeout` hay alert “Data node DOWN”.

### 18.2. Không hủy idempotency state khi shutdown

Nếu app lưu idempotency record dạng in-memory map, restart sẽ làm mất dấu lệnh đang chờ ACK. Với workflows quan trọng, cần persistent record/document và TTL phù hợp retention nghiệp vụ, có bảo vệ concurrent update. Dùng IDs ổn định qua cả retries và restarts.

### 18.3. Circuit breaker không thay gate

Breaker đóng/mở theo health/error history. Gate DRAINING là quyết định vòng đời pod. Không sử dụng breaker như nguồn chân lý duy nhất cho shutdown, vì breaker có thể half-open trong khi instance đang kết thúc.

## 19. KV write, CAS, durability khi kết thúc process

Couchbase KV mutation có các lớp bảo đảm khác nhau:

| Cơ chế | Giúp điều gì | Không tự bảo đảm điều gì |
| --- | --- | --- |
| **ACK từ SDK call** | Biết kết quả theo API/mức durability đã chọn | Mọi side effect ngoài database đã hoàn tất |
| **CAS/`@Version`** | Phát hiện ghi đè cạnh tranh | Không biến network timeout thành rollback |
| **Durability level** | Ràng buộc acknowledgment/persistence/replication theo cluster/version | Exactly-once business operation |
| **Idempotency key** | Nhận diện cùng logical command giữa retries | Không thay thế transaction cho nhiều tài nguyên |
| **Transaction** | Điều phối atomicity/consistency theo phạm vi hỗ trợ | Không tự bao phủ hệ thống payment/email bên ngoài |
| **GSI consistency** | Điều khiển độ mới khi SQL++ đọc sau mutation | Không làm ứng dụng tiếp tục chạy sau SIGKILL |

### 19.1. Case “ACK mất đúng khi process đóng”

~~~mermaid
sequenceDiagram
    participant APP as Orders API
    participant SDK as Java SDK
    participant KV as Couchbase Data Service
    APP->>SDK: insert stable Order key
    SDK->>KV: mutation
    KV->>KV: apply mutation
    KV--xSDK: ACK không đến client
    APP->>APP: termination deadline reached
    Note over APP,KV: Operation outcome chưa được xác minh
~~~

Khi process khởi động lại, một client gửi lại **cùng idempotency key**, ứng dụng nên đọc/xác minh document hoặc retry insert cùng key với chính sách đã thiết kế, không tạo UUID hoàn toàn mới.

### 19.2. CAS conflict sau retry có thể là tín hiệu write trước đã chạy

Một `replace` lần đầu đã thành công nhưng response mất. Retry với CAS cũ có thể báo conflict; đó có thể do lần ghi trước của chính operation hoặc một writer khác. Phải readback state/command fingerprint và phân biệt nghiệp vụ, không tự đổi CAS rồi ghi đè.

### 19.3. Durability không làm `Cluster.disconnect()` trở thành commit

Đóng client không thay một durability acknowledgment chưa nhận. Các transaction hoặc mutations đã hoàn tất cần được xử lý theo results/contract ở **operation boundary** trước khi đóng tài nguyên.

## 20. Transaction đang chạy: callback replay và trạng thái chưa rõ

Với Couchbase Transactions, SDK có thể tự retry transaction attempt hoặc callback trong những tình huống phù hợp theo API/version. Trong shutdown:

1. Không tạo transaction mới khi gate DRAINING.
2. Cho transaction đang active cơ hội hoàn tất trong bounded budget.
3. Theo dõi transaction duration, outcome, retry count theo API thực.
4. Không đặt email, payment charge hoặc external webhook không-idempotent trong callback có thể chạy lại.
5. Không tự coi exception lúc commit là chắc chắn rollback.
6. Nếu outcome chưa rõ, giữ persistent command/state để reconcile.
7. Đừng tắt/đóng SDK khi vẫn còn callback đang chạy nếu còn drain budget.
8. Nếu deadline hết, ghi rõ unknown outcome chứ không giả tạo kết quả thành công.

### 20.1. Logical operation khác một transaction attempt

Một transaction có thể thực hiện nhiều KV reads/writes và nhiều attempts. Dashboard phải tách logical-order completion, transaction completion, SDK attempts và domain-state confirmation. Đừng báo “đã xử lý 5 Orders” chỉ vì có 5 attempts.

### 20.2. Outbox và consumer shutdown

Nếu Order commit thành công rồi cần publish event, mô hình outbox hoặc state machine có thể để event được gửi lại sau restart. Khi consumer shutdown, chỉ ack sau bước xác nhận phù hợp; consumer bị dừng giữa chừng có thể nhận lại message, phải deduplicate.

### 20.3. Không chạy cleanup transaction thủ công vô hạn

Transaction SDK và server có cơ chế cleanup/metadata riêng. Một `@PreDestroy` tự chạy hàng nghìn queries quét và sửa “transaction pending” có thể gây quá tải và vượt grace period. Dùng workflow recovery được thiết kế có giới hạn sau startup/ngoài request teardown.

## 21. TTL, cache và read-after-write quanh thời điểm restart

Một câu trả lời “Order không có” sau restart không nhất thiết do SDK đóng không sạch:

- Document có thể đã hết TTL thật.
- Query SQL++ `NOT_BOUNDED` có thể tạm chưa thấy mutation trong GSI.
- Cache Caffeine/Redis/HTTP/frontend có thể trả dữ liệu cũ.
- Một session có thể đang đọc từ replica với freshness semantics khác.
- Order ID có thể bị sinh lại sai do retry, dẫn tới tìm nhầm key.
- RBAC/collection mapping có thể khác giữa hai versions của app trong rolling update.

### 21.1. Không đổi `REQUEST_PLUS` thành `NOT_BOUNDED` chỉ để drain nhanh

Một workflow phải thấy Order vừa ghi trong list không nên hạ consistency vô điều kiện. Nếu query không thể đạt freshness SLO trước deadline, cần trả lỗi/uncertain state đúng contract, không tráo tính đúng đắn lấy response nhanh.

### 21.2. Cache invalidation có thể sống qua restart

Nếu shutdown xảy ra giữa mutation và publish event xóa cache, hệ thống sau restart có thể phục vụ cache cũ. Cần transactional/outbox/invalidation replay hoặc TTL/consistency policy rõ, không chỉ đóng SDK đúng.

## 22. Kubernetes Deployment: grace period, probes và rolling update

Ví dụ một đoạn cấu hình PodSpec có tính minh họa:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      terminationGracePeriodSeconds: 75
      containers:
        - name: orders-api
          image: registry.example.invalid/orders-api:TAG
          ports:
            - containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 2
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            failureThreshold: 3
~~~

**Các con số chỉ là ví dụ**, không phải cấu hình tốt nhất cho mọi pod. Cần kiểm chứng timeoutSeconds, expected startup, HTTP drain, SDK cleanup và traffic conditions.

### 22.1. Điều gì xảy ra khi pod bị terminate?

Về nguyên tắc, orchestration bắt đầu quá trình termination của pod. Kubernetes có cơ chế lifecycle hooks, SIGTERM cho process và grace period trước khi cưỡng bức kill. Endpoint routing/Ingress/service mesh có thể cập nhật không ngay lập tức; vẫn có các request đã vào hoặc keep-alive connections.

### 22.2. `preStop` là tùy chọn, không phải phép màu

Một `preStop` hook có thể báo app bắt đầu draining qua một endpoint **nội bộ được bảo vệ**, nhưng bản thân hook cũng tiêu tốn termination grace period; không nên chỉ `sleep 30` theo thói quen rồi ngầm giả định load balancer đã xóa endpoint.

Nếu dùng hook, phải xác minh:

- Endpoint có thể được gọi khi process còn sống và đúng địa chỉ/port.
- Chỉ kubelet/operator có thể kích hoạt, có audit/authorization khi cần.
- Nó chuyển app gate/readiness sang trạng thái phù hợp **trước** khi task drain.
- Nó có timeout và trả kết quả nhanh, không chặn SIGTERM vô hạn.
- Lifecycle/termination semantics tương thích với service mesh và cluster setup.

### 22.3. Readiness REFUSING_TRAFFIC và gate là hai thứ khác nhau

Spring Boot có `ApplicationAvailability`/readiness states. Ứng dụng có thể phát sự kiện tương ứng khi bắt đầu draining, chẳng hạn dùng API `AvailabilityChangeEvent` theo Spring Boot version. Nhưng **readiness false không tức khắc ngăn mọi in-flight HTTP calls**, do đó vẫn cần gate và deadline.

### 22.4. Rolling update phải giữ đủ capacity

Nếu `maxUnavailable` quá cao hoặc các pod mới bootstrap chậm, hệ thống có thể không đủ capacity dù shutdown cũ rất sạch. Cân nhắc rolling strategy, `maxSurge`, resource headroom, dependency startup và readiness của pods mới. Không để tất cả phiên bản cũ dừng trước khi phiên bản mới có thể truy cập Couchbase.

## 23. Phân biệt shutdown của process với lỗi node Couchbase

Trong môi trường nhiều pods:

| Quan sát | Có thể là | Hành động đầu tiên |
| --- | --- | --- |
| Một pod DRAINING và 503 tăng ngắn khi rollout | Shutdown điều phối | Kiểm tra endpoints/rolling config |
| Nhiều pods timeout KV dù không rollout | Data/network outage | SDK diagnostics, vBucket/topology, routes |
| KV khỏe, SQL++ timeout | Query/Index issue | Query Service/Index state/plan |
| DB calls còn phát sinh sau shutdown bắt đầu | Scheduler/consumer chưa dừng | Tìm nguồn work bị bỏ sót |
| HTTP requests đã về 0 nhưng in-flight DB > 0 | Background job/transaction | Kiểm tra ownership và deadline |
| SDK disconnected trước khi workers xong | Sai thứ tự lifecycle | Fix bean phases/ownership |
| SIGKILL trước cleanup complete | Grace period quá ngắn hoặc work treo | Đo durations/reconcile |
| Pod NotReady nhưng liveness liên tục restart | Health policy sai | Tách process health khỏi dependency |
| Outbound network restored, app vẫn lỗi | Endpoint discovery/secret/trust | So pod diagnostics, config |
| Restart xong thấy Order trùng | Idempotency/retry sai | Kiểm tra logical IDs, DB state |

Không tự giải thích mọi timeout trong thời gian deploy là lỗi Couchbase Server. Time window chứa rollout, traffic switch, JVM GC và dependency health cần được xem cùng nhau.

## 24. Resource ownership với `ClusterEnvironment` tự tạo

Một ứng dụng chỉ nên chọn **một mô hình rõ ràng**:

**Mô hình A: Spring Boot/Spring Data auto-configure.** Spring container tạo và quản lý SDK client/beans. Không tạo một client phụ trong mỗi service và không gọi `disconnect` từ consumer mượn `Cluster`.

**Mô hình B: ứng dụng tự quản lý SDK cluster/environment.** Chủ sở hữu phải đóng sau khi producer/drain xong.

Ví dụ khái niệm với Java SDK 3.x:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.ClusterOptions;
import com.couchbase.client.java.env.ClusterEnvironment;

ClusterEnvironment environment =
        ClusterEnvironment.builder().build();

Cluster cluster = Cluster.connect(
        "couchbases://couchbase.internal.example",
        ClusterOptions.clusterOptions(
                "YOUR_COUCHBASE_USERNAME",
                "YOUR_COUCHBASE_PASSWORD")
            .environment(environment));

try {
    // Chạy application-owned SDK operations.
} finally {
    try {
        cluster.disconnect();
    } finally {
        environment.shutdown();
    }
}
~~~

**Giới hạn ví dụ:**

- Đừng đặt password literal trong code production; dùng secret manager.
- Kiểm tra API tạo/đóng environment trên Java SDK version thực đang dùng; các tên phương thức và lifecycle semantics có thể đổi giữa releases.
- Mã chỉ minh họa **ownership và thứ tự**; một web server cần lifetime dài và graceful drain trước `finally`, không phải tạo client trong một HTTP request.
- Nếu môi trường được chia sẻ bởi nhiều `Cluster`, chỉ shutdown environment khi **toàn bộ borrowers đã ngừng**.
- Nếu SDK/Boot tự tạo environment, đừng đóng nó hai lần.
- Cần xử lý trường hợp connect/bootstrap fail một phần và phát sinh cleanup tương ứng.

### 24.1. Một Cluster bean có thể do Spring quản lý qua `@Bean` destroy method

Khi tự cấu hình `@Bean`, có thể khai báo destroy method tương ứng cho SDK client, nhưng phải tránh vừa khai báo destroy method vừa viết `@PreDestroy` trùng. Hãy xác minh behavior của Spring context và connection ownership thay vì nhân đôi callback.

### 24.2. Không nhầm `Cluster.disconnect()` với ngừng cluster server

Lời gọi disconnect đóng **SDK client phía ứng dụng**, không tắt Couchbase cluster server, không xóa dữ liệu và không tự làm rebalance/failover. Một SDK client đóng trong pod A không ảnh hưởng trực tiếp đến client connections ở pod B, ngoài việc thay đổi tải chung.

## 25. Logging, metrics và tracing cho quá trình shutdown

Nên có các mốc hữu ích:

~~~text
event=shutdown.begin reason=rolling_deploy
event=traffic.drain_started
event=consumer.pause_requested
event=drain.inflight service=kv count=8
event=drain.inflight service=query count=3
event=drain.timeout remaining=2
event=sdk.disconnect.begin
event=sdk.disconnect.complete
event=shutdown.end clean=false
~~~

Đây là **format ứng dụng tự thiết kế**, không phải mặc định SDK. Không log customerId, order body, secrets hoặc raw SDK diagnostics trên kênh công khai.

### 25.1. Các chỉ số nên instrument

| Metric ứng dụng gợi ý | Loại | Ý nghĩa |
| --- | --- | --- |
| `app.shutdown.started` | Counter | Số lần bước drain được bắt đầu |
| `app.shutdown.duration` | Timer | Từ bắt đầu tới hoàn tất cleanup/exit phase |
| `app.shutdown.clean` | Counter/tag boolean hữu hạn | Clean vs exceeded deadline |
| `app.db.inflight` | Gauge | Số DB operations đang trong wrapper |
| `app.workers.active` | Gauge | Jobs/consumers đang xử lý |
| `app.workers.rejected` | Counter | Công việc bị từ chối khi draining |
| `app.write.ambiguous` | Counter | Mutations có outcome chưa rõ |
| `app.reconciliation.pending` | Gauge | Số logical commands chờ xác minh |
| `app.sdk.disconnect.duration` | Timer | Thời gian client cleanup từ góc app |

**Không tự bịa metric name của SDK/Server.** Những tên trên là **đề xuất ứng dụng** và phải đăng ký bằng Micrometer hoặc stack quan sát thực tế.

### 25.2. Không đo sai duration khi process bị SIGKILL

Nếu process bị kill trước khi callback cuối chạy, metric `shutdown.duration` có thể không được emit. Cần cả **orchestrator events/termination reason**, pod status, startup reconciliation và metrics shutdown incomplete, không suy “không có log lỗi” là dừng sạch.

### 25.3. Tracing và correlation

Một HTTP request có trace ID riêng. Các KV/SQL++ calls có spans hoặc client context IDs nếu instrumentation hỗ trợ. Khi drain, gắn lifecycle state ở log/scope, nhưng không dùng trace ID hoặc Order ID làm Prometheus label vì cardinality/PII.

## 26. Bảo vệ log/credentials trong thời điểm shutdown

Ở lúc ứng dụng có lỗi và dừng, developer có thể muốn bật DEBUG toàn SDK hoặc dump `cluster.diagnostics()`. Điều này cần kiểm soát:

1. Không log raw connection string có password/TLS secrets.
2. Không trả nguyên error context, hostnames/private IPs hoặc `QueryResult` body tới public HTTP.
3. Không ghi full SQL++ parameters hay document JSON.
4. Không đưa idempotency key/command fingerprint vào labels.
5. Chỉ operator có quyền xem deep diagnostics và thay log level.
6. Bật DEBUG/TRACE có thời hạn, trên pod/category nhỏ với sampling.
7. Ghi trace/request ID trong hệ thống có RBAC và retention rõ.
8. Đánh giá observability exporter khi shutdown: không block JVM vô hạn để flush logs.
9. Không để secret trong Docker image/ConfigMap mà không có quản lý quyền.
10. Không dùng một endpoint `/internal/drain` không bảo vệ để người ngoài làm pod từ chối traffic.

### 26.1. Log cần phản ánh kết quả thật

Ghi `outcome=shutdown_timeout` nếu deadline hết, không `outcome=success` chỉ vì `finally` có chạy. Việc `Cluster.disconnect()` trả về không chứng minh tất cả mutations/transactions đã hoàn tất.

## 27. Unit test: admission gate thực sự chờ work đang chạy

Một gate chỉ có ý nghĩa nếu test được các race quan trọng: không nhận mới sau drain, không báo drained khi vẫn còn work, và luôn giảm in-flight dù có exception.

Ví dụ JUnit 5 kiểm thử `OrderDbGate` ở mục 8, không cần Couchbase Server:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

class OrderDbGateTest {

    @Test
    void rejectsNewWorkAndWaitsForExistingWork()
            throws Exception {

        OrderDbGate gate = new OrderDbGate();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        try {
            Future<String> oldWork = executor.submit(() ->
                    gate.execute(() -> {
                        entered.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                            throw new RuntimeException(e);
                        }
                        return "OK";
                    }));

            assertTrue(entered.await(2, TimeUnit.SECONDS));
            assertEquals(1, gate.inFlight());

            gate.beginDrain();

            assertFalse(gate.accepting());
            assertFalse(gate.awaitDrain(
                    Duration.ofMillis(20)));

            assertThrows(
                    OrderDbGate.DrainingException.class,
                    () -> gate.execute(() -> "NEW"));

            release.countDown();

            assertEquals(
                    "OK", oldWork.get(2, TimeUnit.SECONDS));
            assertTrue(gate.awaitDrain(
                    Duration.ofSeconds(1)));
            assertEquals(0, gate.inFlight());
        } finally {
            release.countDown();
            executor.shutdownNow();
        }
    }
}
~~~

**Các assertions đáng bổ sung vào test suite:**

1. `beginDrain()` khi không có work báo drained ngay.
2. Một operation throw RuntimeException vẫn giảm in-flight trong `finally`.
3. Nhiều concurrent tasks hoàn thành không làm count âm.
4. Task bắt đầu sát thời điểm chuyển DRAINING không đi vào SDK nếu nó chưa vượt qua gate.
5. `awaitDrain` trả false đúng budget, không tự coi tasks đã rollback.
6. Gọi `beginDrain()` lặp không mở lại gate.
7. Test không tạo SDK Cluster hoặc network request không cần thiết.

### 27.1. Tránh flaky race tests

Một test dùng `Thread.sleep(500)` rồi giả định worker chắc đã vào gate dễ flaky theo CPU/CI. Dùng `CountDownLatch`, futures và bounded waits để đồng bộ các trạng thái cần assert.

### 27.2. DRAINING là trạng thái một chiều

Một instance đang kết thúc không nên tự mở `accepting=true` khi nhận callback muộn. Nếu muốn một admin pause/resume capability độc lập, thiết kế state machine riêng thay vì tái sử dụng future `drained` đã hoàn tất.

## 28. Unit test reactive: subscribe, cancel và terminal cleanup

Với `ReactiveDbGate` ở mục 16, cần kiểm tra các tình huống:

| Test | Outcome mong đợi |
| --- | --- |
| Tạo `Mono`, không subscribe | `active=0` |
| Subscribe vào `Mono.never()` | `active=1` cho tới cancel |
| Gọi `beginDrain()` khi subscription đang active | Không chấp nhận subscription mới |
| Cancel subscription | `doFinally` giảm active về 0 |
| Upstream `Mono.error(...)` | Error propagate, active về 0 |
| Upstream success | Result giữ nguyên, active về 0 |
| Deadline hết khi subscription chưa hoàn tất | Shutdown ghi drain timeout, không giả success |
| `retryWhen` resubscribe | Số attempt/logical operation được định nghĩa rõ |
| Nested service calls | Không nhân đôi logical in-flight tùy tiện |

Ví dụ với `StepVerifier` (Reactor Test dependency), nếu chỉ dùng publisher giả:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveDbGateTest {

    @Test
    void subscriptionAfterDrainIsRejected() {
        ReactiveDbGate gate = new ReactiveDbGate();

        Mono<String> publisher =
                gate.guard(Mono.just("OK"));

        assertEquals(0, gate.active());

        gate.beginDrain();

        StepVerifier.create(publisher)
                .expectError(
                        OrderDbGate.DrainingException.class)
                .verify();

        assertEquals(0, gate.active());
    }
}
~~~

**Lưu ý:** Đây là test subscription, không kiểm tra SDK remote cancellation. Muốn chứng minh in-flight writes sau client cancel được reconcile, cần integration/fault tests với stable idempotency key.

### 28.1. Reactive gate chỉ bảo vệ Publisher được bọc đúng

Nếu một background service gọi `reactiveRepository.save(order).subscribe()` trực tiếp và không qua gate, metric active có thể báo 0 trong khi SDK operation đang chạy. Không nên dựa vào metric này để cho phép SDK disconnect; cần kiểm kê các luồng tạo I/O.

## 29. Integration test: thứ tự shutdown và SDK close

Trên Spring Boot **test application** với fake SDK adapter hoặc Testcontainers/test Couchbase cluster có quyền phù hợp, kiểm tra toàn bộ đường shutdown:

1. Gửi một HTTP request đang chờ có kiểm soát bên trong service.
2. Xác nhận request đã qua admission gate.
3. Yêu cầu Spring context đóng/graceful stop.
4. Xác nhận app từ chối **new top-level work**.
5. Xác nhận request cũ được hoàn thành khi release latch/fake DB call.
6. Xác nhận SDK owner `disconnect` **chỉ sau** request cũ hoàn thành.
7. Xác nhận các schedulers/consumers không phát sinh work mới khi draining.
8. Xác nhận không có double-close `Cluster`/`ClusterEnvironment`.
9. Xác nhận shutdown không treo khi một fake operation không bao giờ hoàn thành.
10. Xác nhận termination reason và clean/timeout metrics theo contract.

### 29.1. Ghi nhận thứ tự bằng fake resource

Một fake owned resource có thể ghi các event vào list thread-safe:

~~~text
shutdown.begin
admission.closed
workers.paused
existing.order.done
sdk.disconnect.begin
sdk.disconnect.complete
shutdown.end
~~~

Assert **thứ tự trước–sau** thay vì cố đòi timestamps chính xác tới mili giây. Nếu có callbacks bất đồng bộ, dùng futures/latches và bounded timeout.

### 29.2. Phân biệt Spring context close và Kubernetes SIGTERM

Test gọi `context.close()` kiểm tra lifecycle Spring, nhưng chưa tái hiện đủ kubelet routing, ingress propagation, preStop và SIGKILL. Cần một test end-to-end trong cluster lab để xác minh cấu hình PodSpec/Service thực.

### 29.3. Tránh assert một thời gian tuyệt đối không có kiểm soát

Một test “pod phải dừng trong 500 ms” có thể flaky theo CI load/GC. Đặt upper bound dựa trên budget được định nghĩa, ghi shutdown duration và lý do fail nếu vượt ngưỡng; không biến benchmark performance thành unit test.

## 30. Thử nghiệm rolling update và termination trong lab

Trên môi trường **không phải production** có workload Order test và Couchbase cluster phù hợp:

| Pha | Hành động có kiểm soát | Chỉ số/tiêu chí |
| --- | --- | --- |
| Baseline | Chạy GET/POST/SQL++ với test data | p95/p99, 5xx, inflight, error baseline |
| Normal drain | Rollout một pod | Pod không nhận new work sau drain |
| Long KV request | Giữ một KV read/SDK fake call | Drain chờ bounded, không close sớm |
| Slow SQL++ | Cho một Query test kéo dài | HTTP/server budget, no new queries |
| Background consumer | Có một message đang xử lý | Pause intake, ack sau đúng state |
| Reactive cancellation | Client ngắt stream | Không báo write rolled back |
| Timeout write | Mô phỏng mất ACK | Retry cùng idempotency key, không duplicate |
| Force kill | Hết grace ở lab | Startup reconciliation xử lý pending |
| Recovery | Pod mới Ready, traffic ổn định | SLO trở lại, zero unintended duplicates |

### 30.1. Failure injection phải đúng phạm vi

Không kill Couchbase Server, cắt mạng production, chạy synthetic write/delete lớn hoặc gây partition trong môi trường thật để “test shutdown”. Chỉ thử trong cluster lab được phép, có rollback và cleanup fixtures.

### 30.2. Test không bảo đảm exactly-once chỉ bằng đếm HTTP 2xx

Một create command có thể được server ghi hai lần bằng hai keys mà Controller trả một response duy nhất. Kiểm tra **domain state sau recovery**, idempotency records, duplicate detection, inventory/payment side effects, không chỉ HTTP status.

### 30.3. Test readiness + ingress propagation

Sau khi readiness chuyển false, vẫn có thể tồn tại requests đã in-flight hoặc load balancer giữ connection. Xác minh gate xử lý chúng đúng. Không đặt kỳ vọng rằng một probe fail sẽ ngay lập tức chặn tất cả TCP packets.

## 31. Incident A: rolling deploy đóng SDK trước khi scheduler dừng

**Timeline giả định:**

~~~text
14:00:00  Pod nhận SIGTERM
14:00:01  HTTP server bắt đầu graceful stop
14:00:02  Bean owning Cluster gọi disconnect()
14:00:03  @Scheduled task còn chạy gọi Repository.findById
14:00:04  SDK operation fail vì client đã đóng
14:00:05  Scheduler retry liên tục, làm log noise
14:00:20  Pod bị SIGKILL khi vẫn còn executor thread
~~~

**Tại sao xảy ra?**

- Không có thứ tự lifecycle rõ giữa schedulers/workers và SDK owner.
- Spring web-server drain không bao trùm `@Scheduled` task.
- Task không kiểm tra gate DRAINING.
- Có thể có cleanup callback/destroyMethod trùng hoặc quá sớm.
- Retry loop không biết shutdown deadline.

**Hướng sửa:**

1. Đăng ký gate được mọi DB workloads quan trọng sử dụng.
2. Khi bắt đầu shutdown, ngừng intake của scheduler/consumer.
3. Giữ SDK sống cho tới khi in-flight work drain trong budget.
4. Chỉ owner/framework đóng `Cluster` và environment, một lần.
5. Test lifecycle ordering với fake client logs và latches.
6. Đo outstanding tasks, SDK disconnect duration và shutdown timeout.
7. Nếu một worker không thể hoàn tất, lưu/checkpoint state cho restart thay vì chờ vô hạn.

**Điều kiện phục hồi:** Không còn SDK call mới sau disconnect, không có message bị ack trước xử lý, pod shutdown trong grace và các jobs unfinished được xử lý sau restart theo idempotency contract.

## 32. Incident B: SIGKILL giữa thao tác tạo Order

**Timeline giả định:**

~~~text
15:10:00  POST /orders với idempotencyKey=K17
15:10:01  KV insert gửi tới Couchbase
15:10:02  Server có thể đã lưu Order
15:10:03  Termination grace hết, process bị kill
15:10:04  HTTP client không nhận success/ACK
15:10:10  Client retry cùng command
~~~

**Điểm mấu chốt:** Không thể biết từ riêng phía client lúc 15:10:04 rằng Order đã được server tạo hay chưa.

Quy trình an toàn:

1. Dùng `idempotencyKey` ổn định từ logical request.
2. Resolve document key tương ứng, xác minh state/command fingerprint sau khi app phục hồi.
3. Nếu document đúng command đã tồn tại, trả thông tin đã xác minh theo API contract.
4. Nếu chưa có, cân nhắc retry insert với **cùng key** trong policy cho phép.
5. Nếu có payment/Inventory ngoài Order document, đối chiếu side effects/outbox/transaction.
6. Nếu trạng thái chưa xác minh được, giữ trạng thái pending/unknown và một cơ chế reconciliation có khả năng lặp.
7. Theo dõi số pending có tuổi lớn hơn SLO; alert khi không thể xác minh.

**Không làm:** “Không thấy HTTP 201 nên chắc chắn Order chưa tạo; sinh một UUID mới và gọi charge một lần nữa.”

### 32.1. Vì sao drain có ích nhưng không đủ?

Graceful shutdown làm giảm xác suất một write bị cắt giữa chừng khi rolling deploy, nhưng không ngăn OOM/crash/node kill. Idempotency và domain-state verification bảo vệ cả các trường hợp không có `@PreDestroy`.

## 33. Incident C: SQL++ stream chưa hoàn tất nhưng HTTP đã dừng nhận mới

**Triệu chứng giả định:**

~~~text
16:00:00  GET /orders/export bắt đầu Flux<Row>
16:00:01  Pod chuyển DRAINING
16:00:02  HTTP server từ chối request mới
16:00:03  Query stream vẫn còn rows chưa đọc
16:00:04  Cluster.disconnect() được gọi quá sớm
16:00:05  HTTP response bị cắt, exporter nhận file thiếu
~~~

**Nguyên nhân có thể:**

- Logic chỉ đếm thời gian controller tạo `Flux`, không đếm subscription.
- Lifecycle gọi SDK disconnect trước khi reactive stream terminal.
- Không có giới hạn kích thước/trang/cancellation/error semantics cho export.
- HTTP graceful shutdown timeout ngắn hơn cần thiết cho export lớn.
- App không có resumable export/cursor checkpoint, buộc download lại từ đầu.

**Hướng cải thiện:**

1. Đo time-to-first-row, total stream duration và cancellation.
2. Đặt reactive gate từ subscription đến complete/error/cancel.
3. Thiết kế export lớn dưới dạng background job có trạng thái bền vững và file artifact được lưu thay vì giữ HTTP stream rất lâu, khi phù hợp.
4. Giữ SDK cho tới drain hoặc deadline; không cố bảo đảm mọi export khổng lồ phải xong trước SIGKILL.
5. Nếu stream bị cắt, response phải được coi thất bại hoặc resumable theo contract, không ghi “export success”.
6. Test client cancellation và rolling deploy song song với Query/Index load.

## 34. Runbook vận hành khi dừng ứng dụng không sạch

~~~mermaid
flowchart TD
    A["Pod shutdown có lỗi hoặc bị SIGKILL"] --> B{"Có app draining event?"}
    B -->|Không| C["Crash/OOM/force kill; kiểm tra pod reason"]
    B -->|Có| D["Xem intake pause và in-flight counters"]
    D --> E{"Có DB operations chưa hoàn tất?"}
    E -->|Có| F["Phân loại KV write, Query, transaction"]
    E -->|Không| G["Kiểm tra SDK ownership / disconnect"]
    F --> H["Ambiguous outcome? Verify / reconcile"]
    G --> I["Phase order, executor, environment cleanup"]
    C --> H
    H --> J["Khôi phục và kiểm tra dữ liệu/SLO"]
    I --> J
~~~

**Trình tự cho on-call:**

1. Xác định pod, rollout revision, lúc bắt đầu terminate và termination reason (`SIGTERM`/`SIGKILL`/OOM/crash).
2. Đối chiếu `terminationGracePeriodSeconds`, preStop, startup/liveness/readiness và Spring graceful settings.
3. Tra lifecycle logs: drain begin, HTTP stop, consumer pause, in-flight, SDK disconnect, end.
4. Kiểm tra có DB requests tạo mới sau drain không; tìm schedulers, message listeners, fire-and-forget Publishers.
5. Kiểm tra ownership: `Cluster`/`ClusterEnvironment` do Spring quản lý hay custom, có close sớm/đúp?
6. Phân biệt unfinished **KV read**, **KV write ambiguous**, **Query stream**, **transaction unknown commit**.
7. Với write, giữ logical command ID, đối chiếu idempotency fingerprint/state; không retry với ID mới.
8. Với Query, xem Index/Query health, consistency wait và những Publisher chưa terminal.
9. Kiểm tra shutdown executor/deadlock, quá nhiều retries hoặc task không thể cancel.
10. So Kubernetes traffic drain và readiness propagation, các HTTP requests đến muộn.
11. Nếu pod bị force kill, kiểm tra startup reconciliation/outbox và message redelivery.
12. Điều chỉnh budgets/order/gate theo bằng chứng và thử lại trong lab.
13. Sau rollout, kiểm tra HTTP SLO, error rate, pending commands, duplicate Orders và data freshness.
14. Lưu postmortem đã redacted và đo lại các trường hợp tương tự để tránh hồi quy.

### 34.1. Hành động tạm thời và giải pháp dài hạn

Tăng grace period có thể giảm forced kill nhưng không sửa worker không bao giờ kết thúc, SDK close trùng hoặc retry vô hạn. Một giải pháp tốt cần giới hạn công việc, thứ tự lifecycle và domain reconciliation đúng.

### 34.2. Không restart mọi pods để chữa lỗi ở một pod

Một rollout có quá nhiều unavailable pods cần xem deployment strategy/capacity. Nếu shared Couchbase outage đang diễn ra, restart toàn bộ ứng dụng có thể tạo bootstrap storm; phân biệt app shutdown bug với dependency outage.

## 35. Những sai lầm dễ gặp

1. Đóng `Cluster` ngay khi nhận `SIGTERM` mà chưa drain in-flight DB operations.
2. Chỉ bật `server.shutdown=graceful` rồi coi background jobs đã dừng.
3. Đặt `@PreDestroy` gọi `cluster.disconnect()` trong từng Repository service mượn chung client.
4. Tự đóng `ClusterEnvironment` mà client khác vẫn dùng.
5. Không shutdown environment do app tự sở hữu, gây rò rỉ resource.
6. Tạo mới `Cluster.connect` mỗi request/health probe.
7. Coi `Bucket`/`Collection` handles là từng socket cần đóng.
8. Quên ngừng scheduler/consumer nên chúng gửi SQL++ sau khi SDK đóng.
9. Dùng `Thread.sleep` cố định thay thay in-flight tracking.
10. Để shutdown đợi vô hạn và bị SIGKILL bất ngờ.
11. Lấy `HTTP active=0` làm bằng chứng không có background DB operation.
12. Tạo `Mono` rồi đo “đã hoàn thành” trước subscription.
13. Gọi `subscribe()` fire-and-forget trong service.
14. Coi `doOnCancel` là đảm bảo KV write chưa commit.
15. Coi ambiguous timeout là “server chắc chưa ghi”.
16. Retry `POST /orders` với UUID mới.
17. Coi CAS conflict sau retry là chắc chắn một writer khác.
18. Đưa payment/email vào transaction callback có thể replay.
19. Ack queue message trước khi kết quả ghi được xác nhận.
20. Shutdown executor trước khi child tasks cần nó đã hoàn thành.
21. Gắn `REQUEST_PLUS` query nặng vào readiness.
22. Đưa Couchbase health vào liveness khiến shared outage tạo restart storm.
23. Coi readiness false lập tức chặn mọi requests trên keep-alive connections.
24. Dùng `preStop sleep` dài mà không tính vào Kubernetes grace period.
25. Đặt grace period ngắn hơn tổng khả năng drain/cleanup.
26. Đóng SDK từ hai cơ chế `@PreDestroy` và destroyMethod khác nhau.
27. Không log shutdown stages/outstanding counts.
28. Ghi raw SDK diagnostics, credentials, customer IDs ra public logs.
29. Không kiểm tra index freshness/caches sau rolling deploy.
30. Coi process exit code 0 là bằng chứng không có duplicate hoặc pending Order.

## 36. Bài tập thực hành

### A. `Cluster.disconnect()` gọi trước `@Scheduled` task kết thúc

**Yêu cầu:** Thiết kế lại lifecycle.

**Hướng giải:** Đưa scheduler/DB operations qua gate, pause new triggers, drain task có giới hạn, rồi owner/framework mới close Cluster; test phase ordering.

### B. Reactive `Mono` tạo lúc 10:00 nhưng subscribe lúc 10:01

Pod bắt đầu drain lúc 10:00:30. Có nên thực hiện I/O khi subscribe?

**Hướng giải:** Nếu gate ở subscription kiểm tra DRAINING, request mới bị từ chối. Đếm in-flight khi subscribe, không khi tạo Mono.

### C. HTTP đã hết requests nhưng `inFlightDb=5`

**Yêu cầu:** Tìm 5 operation đang chạy.

**Hướng giải:** Có thể là scheduler, queue consumer, transaction, detached async/Flux. Cần tracking ngoài HTTP, không close SDK chỉ vì web server báo rỗng.

### D. SIGKILL khi insert Order chưa nhận ACK

**Hướng giải:** Không biết server đã ghi chưa; retry cùng idempotency key, readback/fingerprint, reconcile transaction/payment side effects. Không sinh UUID mới.

### E. Hai beans cùng gọi `disconnect()`

**Hướng giải:** Xác định một owner; giữ một destroy method/`@PreDestroy` duy nhất theo Spring context. Test close count.

### F. Kubernetes readiness đã DOWN nhưng vẫn có request mới

**Hướng giải:** Ingress propagation/keep-alive; application gate cần từ chối DB top-level work mới và có HTTP error contract.

### G. `preStop sleep 60s`, grace period 30s

**Hướng giải:** Hook tiêu hết budget, process có thể bị kill trước cleanup. Thiết kế total budget, dùng drain signal có kiểm soát thay vì chờ mù.

### H. Transaction callback gửi email hai lần sau retry

**Hướng giải:** Bỏ external side effect khỏi callback, dùng outbox/job có idempotency và trạng thái commit được xác minh.

### I. Query SQL++ REQUEST_PLUS chờ GSI lâu khi pod shutdown

**Hướng giải:** Xem Index backlog/freshness SLO, bounded drain và response errors đúng contract; không đổi consistency lén lút.

### J. Test context.close() pass nhưng rollout thật lỗi

**Hướng giải:** Integration test trong Kubernetes lab gồm kubelet SIGTERM/preStop/Service endpoint propagation, grace period, ingress, message consumers và SDK ownership.

## 37. Checklist production: dừng sạch và đóng tài nguyên SDK

- [ ] Có sơ đồ lifecycle từ ingress → business/workers → SDK → observability/exporters?
- [ ] Phân biệt graceful shutdown, SIGKILL, crash và network partition?
- [ ] `server.shutdown=graceful` và phase budget được cấu hình cho Spring Boot version?
- [ ] Kubernetes termination grace đủ cho total drain/cleanup có margin?
- [ ] Readiness/ingress routing và application gate phối hợp, không chỉ một probe?
- [ ] Gate có từ chối new DB operations khi DRAINING?
- [ ] In-flight work có đếm đúng sync và reactive subscription/Flux terminal?
- [ ] `@Scheduled`, `@Async`, queue consumers và retry loops ngừng new top-level work?
- [ ] Child tasks của in-flight work có cơ hội kết thúc trước executor shutdown?
- [ ] Không có `subscribe()` fire-and-forget trên đường write nghiệp vụ?
- [ ] Background message ack/checkpoint tuân theo write outcome đã xác minh?
- [ ] Pending/retry budgets bị giới hạn và xét remaining shutdown deadline?
- [ ] `Cluster` được Spring Boot quản lý hay custom-owned đã xác định rõ?
- [ ] Không có hai destroy callbacks đóng cùng một client?
- [ ] `ClusterEnvironment` tự tạo chỉ shutdown sau mọi borrowers đã disconnect?
- [ ] Không gọi đóng `Bucket`/`Collection` handle như socket riêng?
- [ ] Không khởi tạo SDK connection mới cho từng request/shutdown probe?
- [ ] SDK close chỉ bắt đầu khi drain hoàn tất hoặc deadline đã đạt?
- [ ] Cleanup không tự tuyên bố mọi writes/transactions đã commit?
- [ ] KV write ambiguous có stable idempotency key và reconciliation?
- [ ] CAS/`@Version` xung đột được phân biệt với timeout?
- [ ] Durability policy được ghi rõ theo business contract/topology?
- [ ] Transaction callback không chứa external side effect không-idempotent?
- [ ] Query/Index `REQUEST_PLUS`/freshness không bị hạ khi shutdown?
- [ ] HTTP deadline, worker drain, SDK cleanup và Kubernetes grace được cân đối?
- [ ] Client cancellation không được hiểu là rollback mutation?
- [ ] Kubernetes `preStop` nếu dùng có bảo mật, timeout và tính vào grace period?
- [ ] Graceful stop làm việc trên serving port, không chỉ management port?
- [ ] Rolling strategy giữ đủ Ready replicas để tránh mất capacity?
- [ ] Có log/metrics drain start, in-flight, timed-out work, disconnect duration?
- [ ] Không log PII, credentials, raw Query parameters hoặc private topology?
- [ ] Tests có latches để kiểm tra không close trước in-flight completion?
- [ ] Tests có cancellation, ambiguous write, retry và double-close scenarios?
- [ ] Lab rollout kiểm tra end-to-end SIGTERM/SIGKILL/traffic drain?
- [ ] Sau restart có consumer redelivery/idempotent replay/reconciliation?
- [ ] Runbook xác minh SLO, data freshness và duplicate prevention sau rollout?

## 38. Kết luận

**Dừng ứng dụng có kiểm soát không chỉ là gọi `Cluster.disconnect()` khi JVM kết thúc.** Đó là trình tự phối hợp giữa HTTP server, readiness/ingress, service admission, scheduler/consumer, các tác vụ đang chạy, transaction/SQL++/KV operations, SDK client và environment do đúng chủ sở hữu quản lý. Mục tiêu là không nhận work mới trên client sắp đóng và cho phép work cũ kết thúc trong một **ngân sách hữu hạn**.

Với **Spring Data Couchbase**, hãy sử dụng **Spring Boot graceful shutdown** cùng **admission gate/SmartLifecycle**, quản lý reactive operations theo **subscription–terminal signal**, phân biệt Spring-owned với application-owned `Cluster`/`ClusterEnvironment` và tránh double-close. Với ghi dữ liệu, luôn giữ **stable idempotency key, CAS/`@Version`, durability và transaction/outbox semantics**: cancellation, timeout hoặc SIGKILL không chứng minh server chưa áp dụng mutation.

Một hệ thống sẵn sàng vận hành phải vừa **dừng đúng thứ tự**, vừa **phục hồi đúng dữ liệu và nghiệp vụ khi thứ tự ấy bị phá vỡ bởi sự cố không báo trước**. Chỉ coi một đợt rollout thành công khi khả năng phục vụ, p95/p99, backlog, pending/ambiguous commands và tính đúng đắn của các Order sau restart đều đã được kiểm chứng.
