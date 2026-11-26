# Ghi nhận refresh thành công, thất bại và cấu hình đang dùng

## Mục tiêu và tình huống thực tế

Trong chương **Khả năng quan sát** của module **SPRING_CLOUD_KUBERNETES**, bài này tập trung vào một câu hỏi vận hành: sau khi ConfigMap hoặc Secret thay đổi, làm sao biết từng Pod đã nhận tín hiệu refresh, refresh có lỗi hay không và luồng nghiệp vụ đang sử dụng cấu hình nào?

Giả sử `order-service` có ba replica, dùng Configuration Watcher để nhận thông báo cập nhật. Bạn đổi giới hạn số sản phẩm trong một đơn từ 20 thành 50. Watcher có log gửi thông báo, `/actuator/refresh` trả HTTP 200, nhưng người dùng vẫn thỉnh thoảng gặp giới hạn cũ. Muốn giải thích được hiện tượng này, bạn cần quan sát cả quá trình phân phối tín hiệu, việc làm mới trong ứng dụng và trạng thái của bean thực sự tiêu thụ cấu hình.

Sau bài học, bạn có thể:

- Định nghĩa rõ refresh “thành công” ở cấp độ nào.
- Ghi log và metric cho mỗi lần gọi refresh, kể cả lần không làm thay đổi khóa nào.
- Quan sát một tập cấu hình không nhạy cảm tại bean mà nghiệp vụ sử dụng.
- Phân biệt lỗi ở Watcher, discovery, HTTP, đọc nguồn, bind/khởi tạo bean và xác minh hành vi.
- Đối chiếu kết quả theo từng Pod để phát hiện replica chưa hội tụ về cấu hình mong muốn.

Ví dụ Java dành cho ứng dụng JVM dùng Spring Boot 3.5, Spring Cloud Commons 4.3 và Spring Cloud Kubernetes 3.3, với BOM tương thích. Các tên metric và endpoint tự viết trong bài là thiết kế minh họa, không phải tính năng telemetry mặc định của Spring Cloud Kubernetes.

## 1. Định nghĩa thành công theo từng mốc

Một lần cập nhật cấu hình có nhiều mốc độc lập:

| Mốc | Bằng chứng cần có | Chưa chứng minh được |
| --- | --- | --- |
| Nguồn đã thay đổi | ConfigMap/Secret được cập nhật; có định danh thay đổi | Pod đã đọc được dữ liệu mới |
| Watcher phát hiện thay đổi | Log phát hiện resource trong đúng namespace | Đã tìm đủ instance cần thông báo |
| Thông báo đã gửi | Kết quả gửi tới từng instance hoặc publish Bus event | Ứng dụng đã xử lý xong refresh |
| Phương thức refresh hoàn tất | `ContextRefresher.refresh()` trả về bình thường | Mọi bean lazy đã tạo thành công |
| Bean đọc được cấu hình mới | Snapshot từ đúng bean phục vụ nghiệp vụ | Tất cả request đang chạy đều dùng bản mới |
| Hành vi được xác minh | Một phép kiểm tra nghiệp vụ an toàn cho kết quả mong đợi | Mọi replica đều đã hội tụ |

Trong Configuration Watcher, HTTP là một cách gửi thông báo đến endpoint refresh của các instance được discovery; một lựa chọn khác là Spring Cloud Bus. Cách chọn resource, ứng dụng đích và cổng quản trị phải khớp cấu hình thực tế. Xem [Configuration Watcher, dòng 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/spring-cloud-kubernetes-configuration-watcher.html).

Nên dùng các tên kết quả chính xác như:

~~~text
notification_sent
notification_failed
refresh_method_success
refresh_method_failure
config_verification_success
config_verification_failure
~~~

Đây là từ vựng đề xuất cho hệ thống log của bạn. Không gom tất cả về một trường `success=true` mà không nêu giai đoạn.

Ví dụ, caller bị timeout nên ghi `notification_outcome=unknown` hoặc một trạng thái tương đương khi chưa biết kết quả phía ứng dụng. Request có thể đã tới Pod và refresh vẫn tiếp tục sau khi caller ngừng chờ. Ngược lại, HTTP 401/403 trước khi vào endpoint là lỗi truy cập; bộ đo bên trong `ContextRefresher` sẽ không có một lần chạy tương ứng.

## 2. Hiểu vòng đời refresh để đặt điểm quan sát

### 2.1 Thứ tự của Spring Cloud Context

Ở Commons 4.3.0, `ContextRefresher.refresh()` thực hiện việc cập nhật Environment, phát `EnvironmentChangeEvent`, sau đó gọi `RefreshScope.refreshAll()` và trả lại tập khóa thay đổi. Xem [mã nguồn ContextRefresher](https://raw.githubusercontent.com/spring-cloud/spring-cloud-commons/v4.3.0/spring-cloud-context/src/main/java/org/springframework/cloud/context/refresh/ContextRefresher.java).

Sơ đồ khái quát:

~~~mermaid
sequenceDiagram
    participant W as Watcher hoặc caller
    participant A as RefreshEndpoint
    participant C as ContextRefresher
    participant R as RefreshScope
    participant B as Bean nghiệp vụ
    W->>A: POST /actuator/refresh
    A->>C: refresh()
    C->>C: Cập nhật Environment
    C->>C: Phát EnvironmentChangeEvent
    C->>R: refreshAll()
    R->>R: Xóa target cũ trong scope
    R-->>C: Hoàn tất bước scope
    C-->>A: Tập khóa thay đổi
    A-->>W: HTTP response
    Note over W,B: Lời gọi tiếp theo mới có thể kích hoạt tạo target mới
    B->>R: Truy cập bean qua proxy
    R-->>B: Tạo hoặc trả target hiện tại
~~~

`RefreshScope` dùng proxy và có cơ chế tạo lại target khi được truy cập sau khi cache bị xóa. Sự kiện `RefreshScopeRefreshedEvent` báo bước làm mới scope; nó không xác nhận mọi target mới đã được khởi tạo và sử dụng thành công. Xem [mã nguồn RefreshScope](https://raw.githubusercontent.com/spring-cloud/spring-cloud-commons/v4.3.0/spring-cloud-context/src/main/java/org/springframework/cloud/context/scope/refresh/RefreshScope.java).

### 2.2 Không dùng một event làm bằng chứng toàn bộ quá trình

| Điểm quan sát | Hữu ích cho | Giới hạn |
| --- | --- | --- |
| `EnvironmentChangeEvent` | Đếm khóa thay đổi, biết Environment đã đi tới bước phát event | Bước refresh scope hoặc tạo bean về sau vẫn có thể lỗi |
| `RefreshScopeRefreshedEvent` | Biết scope đã được làm mới ở mốc tương ứng | Bean lazy có thể lỗi ở lần truy cập kế tiếp |
| Biên vào/ra `ContextRefresher.refresh()` | Ghi thời gian, kết quả trả về hoặc exception của phương thức | Chưa bao phủ các lỗi nghiệp vụ phát sinh sau đó |
| Snapshot tại consumer | Biết cấu hình mà consumer vừa đọc | Là quan sát tại một thời điểm, một instance |
| Kiểm tra hành vi | Biết một luồng nghiệp vụ cụ thể hoạt động | Cần giới hạn side effect và phạm vi kiểm tra |

Không gán listener quan sát với các tác vụ chậm hoặc dễ ném exception: listener đồng bộ có thể làm chậm hay phá chính luồng refresh đang được quan sát. Nếu listener chạy bất đồng bộ, phải chủ động truyền ngữ cảnh tương quan; thread hiện tại không còn là bằng chứng đủ.

### 2.3 Danh sách khóa thay đổi rỗng không đồng nghĩa thất bại

Refresh endpoint trả tập tên khóa do `ContextRefresher` trả lại. Phản hồi `[]` có thể xuất hiện khi không có chênh lệch được phát hiện, kể cả trường hợp nhận thông báo lặp. Xem [mã nguồn RefreshEndpoint](https://raw.githubusercontent.com/spring-cloud/spring-cloud-commons/v4.3.0/spring-cloud-context/src/main/java/org/springframework/cloud/endpoint/RefreshEndpoint.java).

Khi dự kiến có thay đổi mà vẫn thấy `[]`, cần kiểm tra:

- Pod đã đọc được nguồn mới chưa?
- Giá trị có bị một property source ưu tiên hơn ghi đè không?
- Thay đổi vừa nhận có trùng với một lần refresh đã xử lý không?
- Bạn có gọi đúng Pod và đúng application context không?

`changed_key_count=0` là một kết quả cần diễn giải, không phải mã lỗi và cũng không đủ để xác nhận cấu hình mong muốn đã được áp dụng.

## 3. Thiết kế dữ liệu quan sát

### 3.1 Tách danh tính thay đổi, lần thử và replica

| Trường | Ví dụ | Mục đích |
| --- | --- | --- |
| `service` | `order-service` | Liên kết với ứng dụng |
| `namespace` | `refresh-lab` | Xác định phạm vi Kubernetes |
| `pod_name`, `pod_uid` | Tên Pod và UID thực tế | Phân biệt replica và vòng đời Pod |
| `process_start_time` hoặc instance ID | Thời điểm tiến trình bắt đầu | Nhận biết lần restart container |
| `attempt_id` | Một UUID cho mỗi lần gọi | Liên kết các bản ghi của một lần thử |
| `change_id` | `policy-018` | Liên kết nhiều replica với cùng một thay đổi |
| `stage`, `outcome` | `context_refresh`, `method_success` | Cho biết kết quả ở giai đoạn nào |
| `duration_ms` | `84` | Phát hiện refresh chậm |
| `changed_key_count` | `3` | Cho biết mức thay đổi được phát hiện |
| `error_type` | `IllegalArgumentException` | Phân loại lỗi mà không ghi giá trị lỗi |
| `bean_revision` | `policy-018` | Phiên bản quan sát được tại bean |

Pod UID không đổi khi chỉ container restart trong cùng một Pod. Vì vậy, nếu cần phân biệt vòng đời JVM, thêm thời điểm khởi động tiến trình hoặc một instance ID riêng.

`attempt_id` không thay cho `change_id`. Một thay đổi có thể gây nhiều lần thử; một lần refresh có thể gom các thay đổi từ nhiều nguồn. Configuration Watcher mặc định không có hợp đồng đảm bảo truyền toàn bộ metadata nguồn vào mỗi request refresh để ứng dụng tự biết resourceVersion tương ứng.

Nếu cần tương quan xuyên Watcher và ứng dụng, hãy thiết kế header/event metadata có kiểm soát hoặc đối chiếu log theo nguồn, Pod và cửa sổ thời gian. Không khẳng định hai UUID độc lập là cùng một thao tác.

### 3.2 Version nghiệp vụ khác resourceVersion

Nên đặt một marker không nhạy cảm trong dữ liệu cấu hình:

~~~yaml
demo:
  policy:
    revision: policy-018
    mode: standard
    max-items: 50
~~~

Marker này đi cùng các giá trị nó mô tả. Trong khi đó, `metadata.resourceVersion` là định danh phiên bản resource của Kubernetes, hữu ích để theo dõi nguồn; nó không tự được bind vào bean và không nên bị coi là bộ đếm số để so sánh lớn/nhỏ giữa các resource.

Một marker đơn lẻ chưa chứng minh cả tập cấu hình đồng bộ. Muốn xác nhận chính sách đang dùng, hãy đọc revision và các trường cho phép từ **cùng snapshot** tại consumer.

Khi có nhiều ConfigMap/Secret, có thể cần một tập định danh theo từng nguồn thay vì một version tổng giả tạo. Hash cũng chỉ có ý nghĩa khi bạn nêu rõ tập đầu vào, thứ tự chuẩn hóa và việc hash được tính trên dữ liệu mong muốn hay dữ liệu đã có hiệu lực.

### 3.3 Giới hạn dữ liệu nhạy cảm

Không ghi giá trị Secret, mật khẩu, token, connection string hoặc dump toàn bộ Environment. Tên khóa và thông báo exception cũng có thể chứa thông tin nhạy cảm.

Dùng allowlist cho các trường công khai như revision chính sách, mode hoặc giới hạn nghiệp vụ đã được duyệt. Một hash trực tiếp của Secret ít entropy vẫn có thể tạo điều kiện đoán giá trị; không mặc định xem hash là cách công bố Secret an toàn.

Đối với Secret, có thể quan sát version xoay credential từ hệ thống quản lý, trạng thái đọc nguồn và kết quả xác thực an toàn với dependency. Không xuất credential thực vào endpoint chẩn đoán.

## 4. Ví dụ đo thành công và thất bại của phương thức refresh

### 4.1 Chuẩn bị dependency

Giả định ứng dụng đã nạp được cấu hình Kubernetes bằng cơ chế đã chọn và có Spring Cloud Context. Thêm Actuator và Spring AOP vào dự án được BOM quản lý:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
~~~

Nếu chưa có Spring Cloud Context, dependency tương ứng là `org.springframework.cloud:spring-cloud-context`; dùng phiên bản từ BOM thay vì tự ghép các dòng không tương thích. Để xuất metric theo định dạng Prometheus, thêm `io.micrometer:micrometer-registry-prometheus`.

### 4.2 Đặt aspect quanh đúng biên thực thi

Ví dụ này đo lời gọi `refresh()` đi qua Spring proxy. Nó không thay endpoint chuẩn, không tự gọi refresh lần thứ hai và không nuốt exception từ refresh:

~~~java
package com.example.orders.observability;

import java.util.Collection;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class RefreshMethodTelemetry {

    private static final Logger log =
            LoggerFactory.getLogger(RefreshMethodTelemetry.class);

    private final Timer success;
    private final Timer failure;

    public RefreshMethodTelemetry(MeterRegistry registry) {
        this.success = Timer.builder("app.config.refresh")
                .tag("outcome", "method_success")
                .register(registry);
        this.failure = Timer.builder("app.config.refresh")
                .tag("outcome", "method_failure")
                .register(registry);
    }

    @Around("execution(public * "
            + "org.springframework.cloud.context.refresh."
            + "ContextRefresher+.refresh())")
    public Object observe(ProceedingJoinPoint invocation) throws Throwable {
        String attemptId = UUID.randomUUID().toString();
        long started = System.nanoTime();
        boolean completed = false;
        int changedKeyCount = -1;
        String errorType = "none";

        try {
            Object result = invocation.proceed();
            if (result instanceof Collection<?> keys) {
                changedKeyCount = keys.size();
            }
            completed = true;
            return result;
        }
        catch (Throwable ex) {
            errorType = ex.getClass().getSimpleName();
            throw ex;
        }
        finally {
            long elapsed = System.nanoTime() - started;
            report(attemptId, completed, changedKeyCount,
                    errorType, elapsed);
        }
    }

    private void report(String attemptId, boolean completed,
            int changedKeyCount, String errorType, long elapsedNanos) {
        try {
            (completed ? success : failure)
                    .record(elapsedNanos, TimeUnit.NANOSECONDS);
        }
        catch (RuntimeException ignored) {
            // Loi telemetry khong thay doi ket qua refresh.
        }

        try {
            String outcome = completed
                    ? "method_success" : "method_failure";
            String format = "event=config_refresh_finished "
                    + "stage=context_refresh attempt_id={} outcome={} "
                    + "duration_ms={} changed_key_count={} error_type={}";
            if (completed) {
                log.info(format, attemptId, outcome,
                        elapsedNanos / 1_000_000.0,
                        changedKeyCount, errorType);
            }
            else {
                log.warn(format, attemptId, outcome,
                        elapsedNanos / 1_000_000.0,
                        changedKeyCount, errorType);
            }
        }
        catch (RuntimeException ignored) {
            // Khong che exception goc bang loi ghi log.
        }
    }
}
~~~

Bộ đo chỉ xuất tên loại exception; nó chủ động không ghi `ex.getMessage()` hoặc toàn bộ đối tượng cấu hình. Trong hệ thống thực, cần thêm giám sát độc lập cho pipeline log/metric để biết khi telemetry bị mất. Các khối bảo vệ trên chỉ giúp telemetry không thay thế kết quả của thao tác được đo.

Timer đã cung cấp số lần ghi nhận và tổng thời gian; không cần tăng thêm một counter giống hệt chỉ để đếm cùng các lần hoàn tất. Xem [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

### 4.3 Giới hạn phải ghi rõ

- Aspect chỉ bắt các lời gọi qua proxy của bean Spring; một đối tượng tự tạo bằng `new` hoặc lời gọi bỏ qua proxy nằm ngoài phạm vi.
- Trong Spring AOP, self-invocation không tự đi qua proxy. Xem [Spring Framework: Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html).
- Bộ đo nhắm `ContextRefresher.refresh()`, không bao phủ mọi cách gọi trực tiếp `refreshEnvironment()` hay `RefreshScope.refreshAll()`.
- Request bị chặn ở security/network trước khi vào phương thức không tạo kết quả metric này.
- Timer ghi khi phương thức thoát. Một lần bị treo hoặc tiến trình bị kill giữa chừng có thể chưa có bản ghi kết thúc; cần log truy cập hoặc tín hiệu in-flight riêng nếu muốn phát hiện.
- Thời gian advice đo có thể bao gồm thời gian chờ khóa khi có các lần gọi đồng thời. Không gán nó hoàn toàn thành độ trễ API Kubernetes.
- Chiến lược restart/shutdown cần quan sát vòng đời Pod/JVM; không dùng số lần thành công của phương thức này để đại diện cho chúng.

Ngay cả khi `outcome=method_success`, vẫn cần bước xác minh bean và hành vi. Đó là phần quan trọng tiếp theo.

## 5. Quan sát cấu hình tại bean phục vụ nghiệp vụ

### 5.1 Dùng snapshot có hợp đồng rõ ràng

Đọc một key từ Environment chỉ cho biết kết quả phân giải property lúc đọc. Nó chưa cho biết một singleton đã copy giá trị vào field cũ, một HTTP client đã dựng xong hay một connection pool đang dùng tham số gì.

Spring Cloud hỗ trợ rebind `@ConfigurationProperties` và làm mới các bean refresh scope theo cơ chế riêng; không phải mọi đối tượng đã khởi tạo đều tự chuyển sang giá trị mới. Xem [Spring Cloud Context: Environment Changes và Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/4.3/spring-cloud-commons/application-context-services.html).

Ví dụ sau tạo một chính sách bất biến trong mỗi target của refresh scope. Đặt từng lớp public vào file Java tương ứng trong package được scan:

~~~java
package com.example.orders.policy;

import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class OrderPolicy {

    private final Snapshot current;

    public OrderPolicy(Environment environment) {
        String revision = environment.getRequiredProperty(
                "demo.policy.revision");
        String mode = environment.getRequiredProperty(
                "demo.policy.mode");
        int maxItems = environment.getRequiredProperty(
                "demo.policy.max-items", Integer.class);

        if (!revision.matches("[A-Za-z0-9._-]{1,40}")) {
            throw new IllegalArgumentException(
                    "Invalid policy revision format");
        }
        if (!mode.equals("standard") && !mode.equals("strict")) {
            throw new IllegalArgumentException("Invalid policy mode");
        }
        if (maxItems < 1 || maxItems > 500) {
            throw new IllegalArgumentException(
                    "Policy max-items outside allowed range");
        }

        this.current = new Snapshot(revision, mode, maxItems);
    }

    public Snapshot snapshot() {
        return current;
    }

    public record Snapshot(
            String revision, String mode, int maxItems) {
    }
}
~~~

Đây là một consumer cấu hình minh họa, không phải trình quản lý cấu hình dùng chung. Snapshot gắn revision với các giá trị trong một target. Nghiệp vụ phải dùng chính bean này và giữ snapshot trong biến local cho mỗi thao tác:

~~~java
OrderPolicy.Snapshot policy = orderPolicy.snapshot();
boolean accepted = itemCount <= policy.maxItems();
// Neu can audit, gan policy.revision() vao ket qua hoac log nghiep vu.
~~~

Đừng đọc `revision` ở một lần gọi proxy và `maxItems` ở lần gọi khác rồi coi chúng chắc chắn cùng phiên bản. Một refresh có thể xen giữa hai lần gọi.

Snapshot bất biến giúp giữ nhất quán khi sử dụng, nhưng bản thân việc đọc nhiều property trong constructor không tạo một giao dịch trên mọi property source. Lab nên dùng một nguồn chính sách và cập nhật tuần tự; hệ thống có yêu cầu nhất quán mạnh cần cơ chế xây, kiểm tra và hoán đổi snapshot nguyên khối.

### 5.2 Endpoint xác minh chỉ xuất trường được phép

Endpoint dưới đây đọc snapshot của `OrderPolicy`, đồng thời hiển thị revision do Environment phân giải để phát hiện chênh lệch:

~~~java
package com.example.orders.observability;

import java.time.Instant;
import java.util.Map;

import com.example.orders.policy.OrderPolicy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "effectiveconfig")
public class EffectiveConfigEndpoint {

    private static final Logger log =
            LoggerFactory.getLogger(EffectiveConfigEndpoint.class);

    private final OrderPolicy orderPolicy;
    private final Environment environment;

    public EffectiveConfigEndpoint(
            OrderPolicy orderPolicy, Environment environment) {
        this.orderPolicy = orderPolicy;
        this.environment = environment;
    }

    @ReadOperation
    public Map<String, Object> read() {
        String environmentRevision = safeRevision(
                environment.getProperty("demo.policy.revision"));
        String podName = environment.getProperty("POD_NAME", "unknown");
        String podUid = environment.getProperty("POD_UID", "unknown");

        try {
            OrderPolicy.Snapshot policy = orderPolicy.snapshot();
            return Map.of(
                    "state", "bean_readable",
                    "observedAt", Instant.now().toString(),
                    "podName", podName,
                    "podUid", podUid,
                    "environmentRevision", environmentRevision,
                    "beanRevision", policy.revision(),
                    "mode", policy.mode(),
                    "maxItems", policy.maxItems(),
                    "matchesEnvironment",
                    policy.revision().equals(environmentRevision));
        }
        catch (RuntimeException ex) {
            log.warn("event=config_verification_failed "
                    + "pod_name={} error_type={}",
                    podName, ex.getClass().getSimpleName());
            return Map.of(
                    "state", "verification_failed",
                    "observedAt", Instant.now().toString(),
                    "podName", podName,
                    "podUid", podUid,
                    "environmentRevision", environmentRevision,
                    "errorType", ex.getClass().getSimpleName());
        }
    }

    private String safeRevision(String revision) {
        return revision != null
                && revision.matches("[A-Za-z0-9._-]{1,40}")
                ? revision : "unavailable";
    }
}
~~~

Phản hồi thành công có thể là:

~~~json
{
  "state": "bean_readable",
  "observedAt": "2026-11-24T08:10:15Z",
  "podName": "order-service-example-a",
  "podUid": "example-pod-uid-a",
  "environmentRevision": "policy-018",
  "beanRevision": "policy-018",
  "mode": "standard",
  "maxItems": 50,
  "matchesEnvironment": true
}
~~~

Cần đọc đúng hợp đồng:

- `bean_readable` nghĩa là endpoint vừa đọc được snapshot của bean mẫu.
- `matchesEnvironment` chỉ so sánh revision của bean với revision phân giải tại thời điểm kiểm tra; nó không so với cấu hình mong muốn của hệ thống triển khai.
- Phải đối chiếu cả các giá trị `mode`, `maxItems` với chính sách mong muốn nếu revision chưa được quản lý chặt.
- Endpoint bắt lỗi và trả `state=verification_failed` dưới dạng dữ liệu chẩn đoán. HTTP 200 của endpoint này không có nghĩa xác minh thành công; caller phải đọc `state`.
- GET này có thể kích hoạt tạo target refresh scope. Đây là phép xác minh chủ động, không phải bản dump thụ động hoàn toàn không tác động.
- Một request nghiệp vụ đang chạy có thể vẫn giữ snapshot cũ. Quan sát mới không sửa lại dữ liệu mà request trước đã lấy.

Khi constructor của target mới lỗi, endpoint không trả lại một `beanRevision` cũ rồi gọi đó là cấu hình hiện tại. Kết quả đang dùng là **chưa xác minh được** đối với target được truy cập. Nếu hệ thống có cơ chế giữ bản tốt gần nhất, phải thiết kế nó riêng và công bố rõ đây là last-known-good, kèm thời điểm quan sát.

Mẫu này chỉ kiểm tra một chính sách. Nó không xác minh rằng DataSource, HTTP client, cache hoặc mọi bean khác đã nhận cấu hình tương ứng.

## 6. Cấu hình một lab có thể quan sát được

### 6.1 Nguồn cấu hình mẫu

Lab chọn ConfigMap mount thành file để thấy rõ khác biệt giữa thay đổi nguồn và dữ liệu trong Pod:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-service
  namespace: refresh-lab
  labels:
    spring.cloud.kubernetes.config: "true"
data:
  application.yml: |
    demo:
      policy:
        revision: policy-017
        mode: standard
        max-items: 20
~~~

Giả định namespace, Deployment, Service `order-service` và Configuration Watcher đã được triển khai đúng; Service phải chọn các Pod ứng dụng cần được thông báo. Bài này tập trung telemetry, không cung cấp toàn bộ manifest của hệ thống.

Trong `application.yml` đóng gói cùng ứng dụng:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "file:/etc/order-config/application.yml"

management:
  endpoints:
    web:
      exposure:
        include: health,refresh,metrics,effectiveconfig,prometheus
  endpoint:
    refresh:
      access: unrestricted
    env:
      show-values: never
    configprops:
      show-values: never
~~~

`prometheus` cần registry Prometheus đã nêu ở trên; nếu không dùng, bỏ ID đó khỏi exposure. Endpoint `env` và `configprops` không nằm trong danh sách được expose của ví dụ.

`access: unrestricted` là mức cho phép thao tác endpoint của Actuator, không phải cấu hình bỏ xác thực HTTP. Cần bảo vệ endpoint refresh và effectiveconfig bằng Spring Security/mạng phù hợp, đồng thời cho Watcher gọi đúng địa chỉ. Expose endpoint không đồng nghĩa đã cấp quyền gọi. Xem [Spring Boot: Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html).

Fragment của `spec.template.spec` trong Deployment:

~~~yaml
containers:
  - name: order-service
    image: example/order-service:refresh-lab
    ports:
      - name: http
        containerPort: 8080
    env:
      - name: POD_NAME
        valueFrom:
          fieldRef:
            fieldPath: metadata.name
      - name: POD_UID
        valueFrom:
          fieldRef:
            fieldPath: metadata.uid
    volumeMounts:
      - name: policy-config
        mountPath: /etc/order-config
        readOnly: true
volumes:
  - name: policy-config
    configMap:
      name: order-service
~~~

Ứng dụng đọc file mount không cần quyền API chỉ để đọc file đó; Watcher vẫn cần quyền quan sát nguồn và tìm các instance theo kiến trúc discovery đã chọn. Phân biệt lỗi RBAC tới API Kubernetes với lỗi security khi gọi HTTP Actuator.

### 6.2 Lưu ý cơ chế truyền dữ liệu

Kubernetes cập nhật dữ liệu ConfigMap trong volume theo cơ chế eventual; biến môi trường lấy từ ConfigMap không tự thay đổi trong container đang chạy, và mount dùng `subPath` không nhận cập nhật như volume thông thường. Xem [Kubernetes: ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/).

Watcher có tùy chọn trì hoãn trước khi gửi tín hiệu, ví dụ biến môi trường trong Deployment **của Watcher**:

~~~yaml
- name: SPRING_CLOUD_KUBERNETES_CONFIGURATION_WATCHER_REFRESHDELAY
  value: "10000"
~~~

Giá trị minh họa là 10.000 ms. Đo trên cluster thực để chọn thời gian phù hợp. Một độ trễ cố định không phải bằng chứng rằng mọi Pod chắc chắn đã nhận file mới; vì thế vẫn phải xác minh revision tại từng instance.

Trong lab, không đồng thời nạp cùng các key qua nhiều đường API, file mount và biến môi trường mà không biết thứ tự ưu tiên. Khi một giá trị khác mong đợi, kiểm tra property source thắng cuộc; Spring Boot có quy tắc ưu tiên cụ thể cho các nguồn cấu hình. Xem [Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html).

## 7. Đọc log và metric theo đúng ý nghĩa

### 7.1 Log hoàn tất ở cấp phương thức

Aspect mẫu tạo bản ghi dạng:

~~~text
event=config_refresh_finished stage=context_refresh attempt_id=example-1 outcome=method_success duration_ms=84.2 changed_key_count=3 error_type=none
~~~

Nếu luồng refresh ném exception:

~~~text
event=config_refresh_finished stage=context_refresh attempt_id=example-2 outcome=method_failure duration_ms=22.5 changed_key_count=-1 error_type=IllegalStateException
~~~

`-1` trong mẫu nghĩa là chưa nhận được tập khóa trả về, không phải số lượng khóa thay đổi âm. Nếu bean lazy lỗi sau refresh, bạn có thể thấy một cặp bằng chứng:

~~~text
event=config_refresh_finished stage=context_refresh attempt_id=example-3 outcome=method_success duration_ms=35.0 changed_key_count=2 error_type=none
event=config_verification_failed pod_name=order-service-example-a error_type=BeanCreationException
~~~

Hai dòng không mâu thuẫn: phương thức đã hoàn tất nhưng target mới không tạo được khi xác minh. Mã mẫu không tự liên kết hai dòng bằng cùng `attempt_id`; nếu cần quan hệ đó, phải lưu ngữ cảnh lần refresh gần nhất với quy tắc xử lý đồng thời rõ ràng.

Collector có thể bổ sung namespace, Pod name, UID và container metadata. Các trường đó không xuất hiện tự động chỉ vì code dùng SLF4J. Cũng không gán `trigger=http` hoặc `trigger=bus` từ suy đoán khi aspect chưa biết nguồn gọi.

Log framework hoặc stack trace khác vẫn có thể chứa tên khóa hay giá trị nhạy cảm dù bộ đo mẫu đã giới hạn dữ liệu. Kiểm tra cấu hình logger, redaction và quyền đọc log của toàn hệ thống.

### 7.2 Metric ít nhãn, định nghĩa rõ mẫu số

Với registry Prometheus, timer `app.config.refresh` thường được xuất thành các series như:

~~~text
app_config_refresh_seconds_count{outcome="method_success"} 12
app_config_refresh_seconds_sum{outcome="method_success"} 0.845
app_config_refresh_seconds_count{outcome="method_failure"} 1
app_config_refresh_seconds_sum{outcome="method_failure"} 0.122
~~~

Đối chiếu tên thực tế do phiên bản registry/backend xuất ra. Đây là metric ứng dụng tự đăng ký; không phải tên built-in của Configuration Watcher.

Truy vấn minh họa để phát hiện có lỗi trong 15 phút:

~~~promql
sum(
  increase(app_config_refresh_seconds_count{
    outcome="method_failure"
  }[15m])
) > 0
~~~

Thời gian trung bình của các lần hoàn tất trong 5 phút:

~~~promql
sum(rate(app_config_refresh_seconds_sum[5m]))
/
sum(rate(app_config_refresh_seconds_count[5m]))
~~~

Khi không có lần refresh, mẫu số bằng 0 và không có phép đo trung bình có ý nghĩa. Không biến trường hợp thiếu dữ liệu thành kết luận hệ thống đang tốt.

Chỉ dùng nhãn có tập giá trị hữu hạn như `outcome`. Không đưa attempt ID, revision, danh sách khóa, resourceVersion, exception message hoặc Secret vào nhãn metric. Danh tính Pod thường được gắn từ scrape target; vẫn phải theo dõi chi phí series do rollout và quy mô replica.

Nếu bổ sung metric xác minh, nêu rõ đang đếm **số lần kiểm tra** hay **số thay đổi đã áp dụng**. Poll endpoint 100 lần không có nghĩa cấu hình được áp dụng 100 lần. Các chỉ báo về version hiện tại nên nằm ở dữ liệu chẩn đoán/log hoặc một bộ thu thập hội tụ được thiết kế riêng.

### 7.3 Không chỉ cảnh báo khi có exception

Một hệ thống có thể không báo lỗi vì không có refresh nào tới được ứng dụng. Nên bổ sung:

- Cảnh báo nguồn đã đổi nhưng chưa đủ Pod xác nhận trong thời hạn.
- Cảnh báo không đọc được endpoint xác minh hoặc dữ liệu quan sát quá cũ.
- Cảnh báo tỉ lệ gửi thông báo thất bại, tách khỏi tỉ lệ phương thức refresh lỗi.
- Theo dõi số Pod cần xác minh và số Pod thực sự đã được kiểm tra.

Không dùng “lần refresh thành công cuối cùng cách đây lâu” làm cảnh báo độc lập nếu cấu hình vốn ít thay đổi. Chỉ có ý nghĩa khi gắn với thay đổi mong muốn hoặc một lịch xác minh cụ thể.

## 8. Xác minh trên từng Pod và đo thời gian hội tụ

### 8.1 Bảng đối chiếu tối thiểu

Với thay đổi `policy-018`, lập bảng từ các quan sát riêng:

| Pod | Revision mong muốn | Revision bean | Trạng thái xác minh | Kết luận |
| --- | --- | --- | --- | --- |
| Pod A | `policy-018` | `policy-018` | Đọc được snapshot, giá trị đúng | Đã xác nhận tại thời điểm quan sát |
| Pod B | `policy-018` | `policy-017` | Đọc được snapshot cũ | Chưa hội tụ |
| Pod C | `policy-018` | Chưa biết | Endpoint không truy cập được | Chưa có bằng chứng |

Đừng tính Pod C như đã thành công hoặc loại nó khỏi mẫu số để có 100%. Ghi riêng unavailable, stale và verified.

Chốt tập Pod cần quan sát ở thời điểm kiểm tra, kèm quy tắc cho Pod đang terminating và Pod mới xuất hiện do rollout. Hệ thống triển khai có thể thay đổi tập đích trong khi cấu hình đang được áp dụng.

### 8.2 Mốc thời gian

Định nghĩa:

~~~text
t_source: thời điểm thay đổi được hệ thống điều phối ghi nhận thành công
t_verified(pod): thời điểm xác minh Pod dùng snapshot mong muốn
convergence_time: max(t_verified của các Pod cần xét) - t_source
~~~

Đây là phép đo của quy trình quan sát, có sai số do chu kỳ polling và đồng bộ đồng hồ. Nó không đồng nghĩa với thời gian chạy phương thức refresh. Nếu kiểm tra mỗi 30 giây, không nên công bố độ chính xác hội tụ tới từng mili giây.

`observedAt` cho biết lúc endpoint tạo quan sát, không phải chính xác lúc cấu hình bắt đầu có hiệu lực. Để biết một request đã dùng version nào, gắn revision snapshot vào telemetry của request đó theo mức chi tiết phù hợp.

### 8.3 Service và LoadBalancer có thể che replica cũ

Gọi endpoint qua Service hoặc Spring Cloud LoadBalancer nhiều lần không bảo đảm đã chạm tới mọi Pod. Kết nối giữ lâu, cache danh sách instance và cách chọn instance có thể làm một replica xuất hiện nhiều lần.

Để xác minh rollout cấu hình, hãy gọi theo danh tính instance hoặc port-forward từng Pod. Dùng DiscoveryClient để tìm đích cũng cần đối chiếu với tập Pod kỳ vọng; replica không được discovery trả về không tự biến thành replica đã xác minh.

## 9. Quy trình thực hành có kiểm soát

Chạy các bước này trong namespace lab, với endpoint đã được bảo vệ phù hợp. Các placeholder `<pod-a>` phải được thay bằng tên Pod thật.

### Bước 1: Ghi trạng thái ban đầu

~~~powershell
kubectl -n refresh-lab get pods -l app=order-service -o wide
kubectl -n refresh-lab get configmap order-service -o jsonpath='{.metadata.resourceVersion}'
kubectl -n refresh-lab logs -l app=order-service --since=10m --prefix=true
~~~

Giữ port-forward tới một Pod trong một terminal:

~~~powershell
kubectl -n refresh-lab port-forward pod/<pod-a> 18081:8080
~~~

Ở terminal khác, dùng phương thức xác thực đã cấu hình cho lab khi cần:

~~~powershell
curl.exe -i http://127.0.0.1:18081/actuator/effectiveconfig
~~~

Ghi snapshot `policy-017`, `maxItems=20` và danh tính Pod. Lặp lại cho các replica bằng port-forward riêng. Port-forward không bỏ qua Spring Security.

### Bước 2: Đổi nguồn và để Watcher hoạt động

~~~powershell
kubectl -n refresh-lab edit configmap order-service
~~~

Trong một lần sửa, đổi revision thành `policy-018` và `max-items` thành `50` trong nội dung `application.yml`. Giữ định dạng YAML hợp lệ.

Theo dõi log Deployment của Watcher bằng tên thật trong cluster; ví dụ nếu Deployment tên `configuration-watcher`:

~~~powershell
kubectl -n refresh-lab logs deployment/configuration-watcher --since=10m
~~~

Đối chiếu thời điểm phát hiện, ứng dụng đích và kết quả gửi. Bật DEBUG có thời hạn nếu cần xác định namespace, label và danh sách instance. Không kết luận ứng dụng đã áp dụng chỉ từ log Watcher.

### Bước 3: Xác nhận kết quả trong từng Pod

~~~powershell
kubectl -n refresh-lab logs pod/<pod-a> --since=10m
curl.exe -i http://127.0.0.1:18081/actuator/effectiveconfig
~~~

Đọc `outcome` của refresh và snapshot riêng. Lặp lại cho toàn bộ tập Pod cần xét; lưu thời điểm xác minh để tính hội tụ.

Nếu cần tách lỗi gửi thông báo khỏi lỗi xử lý trong ứng dụng, có thể gọi thủ công **đúng một Pod**:

~~~powershell
curl.exe -i -X POST http://127.0.0.1:18081/actuator/refresh
~~~

Không cần body chứa dữ liệu cấu hình. Lệnh này là kích hoạt thêm một lần refresh, không phải thao tác đọc. Ghi nhận rằng lần gọi thủ công có thể làm thay đổi kết quả thí nghiệm Watcher và chỉ ảnh hưởng Pod đang được port-forward.

### Bước 4: Kiểm tra trường hợp không thay đổi

Sau khi xác minh bean đang ở `policy-018`, gọi refresh thêm một lần mà không đổi nguồn. Có thể nhận `[]`, log `method_success` và `changed_key_count=0`.

Điều cần học là “không phát hiện chênh lệch” khác với lỗi. Việc tạo lại bean vẫn có vòng đời của nó; đừng spam refresh như một cách polling vô hại.

### Bước 5: Tạo cấu hình không hợp lệ trong lab

Đổi revision thành `policy-019` và `max-items` thành `0`. Với consumer mẫu, kiểm tra range nằm trong constructor của target refresh scope.

Bạn có thể quan sát phương thức refresh hoàn tất, rồi `effectiveconfig` báo `verification_failed` khi tạo target mới. Tùy cơ chế bind, listener và bean thực tế, lỗi cũng có thể xuất hiện sớm hơn ngay trong refresh; không ép mọi ứng dụng phải tái hiện một thứ tự lỗi duy nhất.

Khôi phục nguồn hợp lệ bằng một revision mới, chẳng hạn `policy-020` với `max-items=50`. Đợi dữ liệu tới Pod, refresh lại và xác minh từng replica. Sửa file nguồn chưa đủ để kết luận cache lỗi hay target lỗi đã được thay thế.

Thao tác rollback cũng là một lần cập nhật cần được phân phối và xác minh. Refresh thất bại không có hợp đồng tự động hoàn tác mọi thay đổi Environment hoặc mọi bean về một trạng thái cũ nguyên vẹn.

## 10. Khoanh vùng lỗi từ bằng chứng

| Quan sát | Khả năng cần kiểm tra | Bằng chứng tiếp theo |
| --- | --- | --- |
| Nguồn đổi nhưng không có log Watcher phù hợp | Namespace, label, quyền đọc/watch, watcher không hoạt động | Log khởi tạo và lỗi RBAC của Watcher |
| Watcher phát hiện nhưng không thấy đủ đích | Service name, selector, discovery, instance chưa ready | Danh sách instance và tập Pod kỳ vọng |
| Gửi HTTP nhận 401/403 | Xác thực, phân quyền hoặc CSRF ở ứng dụng | Log truy cập/security; chưa quy thành lỗi bind |
| Caller timeout, không biết refresh có chạy không | Mạng chậm hoặc xử lý vẫn đang tiếp diễn | Log phía Pod, snapshot và thời gian phương thức |
| Refresh trả `[]`, bean vẫn cũ | Nguồn chưa tới, ưu tiên property, thông báo lặp | File mount, Environment, danh tính Pod |
| Method success nhưng snapshot lỗi | Tạo target lazy hoặc validation tại consumer lỗi | `errorType` và log được kiểm soát |
| Environment mới, singleton vẫn giữ giá trị cũ | Bean không được rebind/refresh hoặc consumer đã copy giá trị | Vòng đời bean và snapshot consumer thực |
| Một Pod mới, một Pod cũ | Thông báo thiếu, dữ liệu chưa đồng bộ, rollout hoặc override riêng | Bảng xác minh theo Pod UID và version tiến trình |
| Health `UP` nhưng cấu hình sai | Health hiện tại không kiểm tra hợp đồng cấu hình | Snapshot và phép kiểm tra nghiệp vụ |
| Không có metric refresh | Không có lần gọi, aspect không áp dụng, chưa scrape hoặc mất telemetry | Log request, proxy bean và pipeline metric |

Các giá trị từ `/actuator/env` hoặc `/actuator/configprops` có thể hỗ trợ chẩn đoán sâu khi được bảo vệ, nhưng không thay thế bằng chứng consumer thực sự dùng tham số nào. Chỉ expose chúng có chủ đích và giữ cơ chế che giá trị phù hợp.

Đừng đưa lỗi refresh của một dependency chung vào liveness theo phản xạ. Restart toàn bộ replica có thể làm gián đoạn rộng hơn mà không sửa được nguồn cấu hình sai. Nếu quyết định readiness phụ thuộc cấu hình hợp lệ, cần nêu rõ chính sách với last-known-good, target mới bị lỗi và các request đang chạy.

## 11. Kết quả cần có sau bài học

Một thiết kế quan sát đủ dùng cần trả lời được cho mỗi thay đổi:

1. Nguồn cấu hình nào đổi, trong namespace nào và marker mong muốn là gì?
2. Watcher hoặc Bus đã nhắm tới những instance nào; đích nào chưa có kết quả chắc chắn?
3. Mỗi Pod có lời gọi refresh hoàn tất hay lỗi; thời gian và giai đoạn lỗi là gì?
4. Bean nghiệp vụ vừa được xác minh đang dùng snapshot nào và quan sát còn mới không?
5. Còn Pod nào cũ, không truy cập được hoặc chưa được kiểm tra?
6. Nếu phải khôi phục, cấu hình phục hồi đã được xác minh trên toàn bộ tập đích chưa?

Chọn mức quan sát theo cơ chế triển khai thực sự cần: ứng dụng chỉ nạp cấu hình khi khởi động có thể theo dõi version và rollout; ứng dụng dùng refresh động cần thêm bằng chứng cho từng giai đoạn. Không thêm Configuration Watcher, DiscoveryClient hoặc Bus chỉ để tạo telemetry khi luồng cập nhật cấu hình không sử dụng chúng.
