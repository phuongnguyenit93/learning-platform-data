# Ghi nhận nguồn, thời điểm và kết quả thay đổi cấu hình

Trong một ứng dụng Spring Cloud, cấu hình có thể đến từ nhiều nơi: file cấu hình, biến môi trường, Spring Cloud Config Server, Vault hoặc một `PropertySource` tùy chỉnh. Khi cấu hình thay đổi lúc ứng dụng đang chạy, nhóm vận hành cần trả lời được bốn câu hỏi: **thay đổi đến từ đâu, ai hoặc hệ thống nào yêu cầu, thay đổi xảy ra lúc nào, và từng instance đã áp dụng kết quả ra sao?**

Spring Cloud Context cung cấp các sự kiện như `EnvironmentChangeEvent` và `RefreshScopeRefreshedEvent`; Spring Boot Actuator cung cấp các endpoint quan sát `env`, `configprops`, `health` và `auditevents`. Các thành phần này tạo nền tảng để theo dõi thay đổi, nhưng không tự tạo thành một nhật ký kiểm toán đầy đủ. Ứng dụng cần bổ sung metadata nguồn, phiên bản cấu hình, người yêu cầu, correlation ID và kết quả xử lý.

Bài học thuộc chương **Quan sát** của module **SPRING_CLOUD_CORE**. Ta sẽ đi từ vòng đời thay đổi cấu hình, cách ghi nhận event, thiết kế audit record, ví dụ tích hợp `ContextRefresher` với `AuditEventRepository`, đến theo dõi qua Spring Cloud Bus, Actuator, metrics, log và kiểm thử.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt thay đổi tại kho cấu hình, thay đổi trong `Environment` và thay đổi được áp dụng vào bean.
- Giải thích dữ liệu mà `EnvironmentChangeEvent` và `RefreshScopeRefreshedEvent` cung cấp.
- Nhận biết metadata mà các event mặc định không cung cấp, như actor, source revision và correlation ID.
- Thiết kế audit record có nguồn, ứng dụng, profile, instance, thời điểm và kết quả.
- Ghi audit bằng `AuditEventRepository` và đọc qua Actuator `auditevents`.
- Dùng `ContextRefresher.refresh()` để lấy danh sách key thay đổi và điều phối việc refresh.
- Phân biệt rebind `@ConfigurationProperties` với việc invalidation bean trong `@RefreshScope`.
- Theo dõi việc phát tán thay đổi qua Spring Cloud Bus và webhook Config Monitor.
- Quan sát trạng thái cấu hình qua `env`, `configprops`, `health` và log.
- Bảo vệ dữ liệu nhạy cảm trong log, audit record và Actuator.
- Kiểm thử thành công, thất bại, thay đổi key và metadata bằng clock cố định cùng nguồn dữ liệu giả.

## 2. Ba lớp của một thay đổi cấu hình

Một thay đổi có thể tồn tại ở kho cấu hình mà chưa được tải vào ứng dụng. Tương tự, `Environment` có thể đã nhận giá trị mới nhưng bean đang sử dụng vẫn chưa được khởi tạo lại. Vì vậy, cần phân biệt ba lớp:

| Lớp | Điều đã xảy ra | Bằng chứng nên ghi nhận |
| --- | --- | --- |
| Nguồn cấu hình | Git commit, phiên bản Config Server, secret version hoặc file đã thay đổi | Source, revision/label, actor, thời điểm commit |
| Runtime Environment | Ứng dụng đã nạp property source và nhận diện các key thay đổi | Application, profile, instance, changed keys, event timestamp |
| Runtime component | `@ConfigurationProperties` đã rebind hoặc bean `@RefreshScope` được invalidated rồi tạo lại ở lần truy cập tiếp theo | Refresh outcome, bean health, lỗi khởi tạo, thời điểm xác minh |

~~~mermaid
flowchart TD
    A[Config source changes] --> B[Source audit: actor, revision, time]
    B --> C[Config Server / refresh request]
    C --> D[Each application instance loads configuration]
    D --> E[EnvironmentChangeEvent]
    E --> F[Rebind ConfigurationProperties]
    E --> G[Invalidate RefreshScope cache]
    G --> H[Next access creates scoped bean]
    F --> I[Verify effective configuration]
    H --> I
    I --> J[Audit outcome and health]
~~~

Một lần refresh có thể thành công ở lớp nguồn nhưng thất bại khi một instance tải cấu hình. Hoặc `Environment` đã đổi nhưng bean mới lỗi khi khởi tạo ở lần truy cập tiếp theo. Không nên gộp các trạng thái đó thành một nhãn “config updated” duy nhất.

## 3. Event của Spring Cloud ghi nhận điều gì?

### 3.1. EnvironmentChangeEvent

Spring Cloud Context phát `EnvironmentChangeEvent` khi Environment được cập nhật và có các key thay đổi. Event cung cấp tập hợp tên key qua `getKeys()`.

Khi event được xử lý, Spring Cloud thực hiện một số hành động mặc định:

- Rebind các bean `@ConfigurationProperties` trong context.
- Cập nhật log level cho các property thuộc `logging.level.*`.

Lưu ý: các bean `@ConfigurationProperties` dùng constructor binding, bao gồm Java record, không thể được refresh theo cơ chế rebind này. Nếu bean cần thay đổi theo refresh, hãy chọn kiểu binding và vòng đời bean phù hợp với yêu cầu.

Có thể thêm `ApplicationListener` hoặc `@EventListener` để ghi log, tăng metric hay gửi thông báo quan sát.

Ví dụ listener tối giản:

~~~java
import java.time.Instant;

import org.springframework.cloud.context.environment.EnvironmentChangeEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationChangeLogger {

    @EventListener
    public void onEnvironmentChange(EnvironmentChangeEvent event) {
        Instant occurredAt = Instant.ofEpochMilli(event.getTimestamp());

        System.out.printf(
                "event=environment-change time=%s changedKeys=%s%n",
                occurredAt,
                event.getKeys());
    }
}
~~~

Listener trên ghi thời điểm event được tạo và danh sách key. Nó chưa biết ai yêu cầu refresh, nguồn cấu hình là Git hay Vault, revision nào được tải, hoặc việc khởi tạo bean mới có thành công không.

### 3.2. RefreshScopeRefreshedEvent

Khi `RefreshScope` hủy cache của một bean hoặc toàn bộ scope, Spring Cloud phát `RefreshScopeRefreshedEvent`. Với refresh một bean, event mang tên bean; với `refreshAll()`, event dùng tên mặc định.

~~~java
import java.time.Instant;

import org.springframework.cloud.context.scope.refresh.RefreshScopeRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class RefreshScopeChangeLogger {

    @EventListener
    public void onRefreshScopeRefreshed(
            RefreshScopeRefreshedEvent event) {
        System.out.printf(
                "event=refresh-scope-invalidated time=%s bean=%s%n",
                Instant.ofEpochMilli(event.getTimestamp()),
                event.getName());
    }
}
~~~

Tên event dễ khiến người đọc hiểu rằng bean mới đã được tạo xong. Thực tế, refresh-scope bean là lazy proxy: thao tác refresh xóa target đang cache và target mới được tạo ở lần gọi tiếp theo. Event chứng minh cache entry đã bị invalidated; nó không tự chứng minh lần khởi tạo tiếp theo thành công.

Spring Cloud có `RefreshScopeHealthIndicator` để phản ánh lỗi khi bean refresh hoặc rebind cấu hình thất bại. Hãy kết hợp event với health và log khởi tạo bean để xác minh kết quả.

### 3.3. Event mặc định không phải audit record đầy đủ

`EnvironmentChangeEvent` chủ yếu cung cấp changed keys. `RefreshScopeRefreshedEvent` cho biết bean/scope bị refresh. Hai event này không mang sẵn toàn bộ thông tin cần cho audit:

| Trường audit | Event mặc định có cung cấp không? | Cách bổ sung |
| --- | --- | --- |
| Danh sách key thay đổi | Có trong `EnvironmentChangeEvent` | Lấy từ `getKeys()` |
| Thời điểm event | Có timestamp của `ApplicationEvent` | Chuyển sang `Instant` UTC |
| Actor/người yêu cầu | Không | Lấy từ authenticated principal ở control plane |
| Nguồn cấu hình | Không đầy đủ | Gắn source ID, PropertySource name hoặc nguồn phát hành |
| Revision/commit/secret version | Không | Lấy từ Config Server, Git hoặc secret manager |
| Correlation ID | Không | Truyền từ request/webhook/Bus message |
| Kết quả từng instance | Không đầy đủ | Ghi trạng thái ở từng client và xác minh health |
| Giá trị cũ/mới | Không | Chụp snapshot có allowlist và redaction nếu thật sự cần |

Không suy ra actor từ hostname hoặc từ `event.getSource()`. Source của event thường là context phát event, không phải danh tính người đã thay đổi cấu hình.

## 4. Mô hình audit record

Một bản ghi thay đổi cấu hình nên có cấu trúc ổn định để truy vấn và đối chiếu giữa nhiều instance.

| Trường | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `eventType` | `CONFIG_REFRESH_SUCCEEDED` | Loại sự kiện |
| `occurredAt` | `2026-11-18T13:20:15Z` | Thời điểm ghi nhận theo UTC |
| `actor` | `deploy-bot` | Người hoặc hệ thống yêu cầu |
| `application` | `orders-service` | Ứng dụng đích |
| `instanceId` | `orders-7f9c` | Replica đã xử lý |
| `source` | `spring-cloud-config` | Nguồn cấu hình |
| `revision` | `a41c8d2` | Commit, label hoặc version |
| `profiles` | `staging` | Profile có hiệu lực |
| `changedKeys` | `limits.pool-size` | Các key được nhận diện thay đổi |
| `correlationId` | `cfg-req-8241` | Nối các log/event qua nhiều hệ thống |
| `outcome` | `SUCCEEDED`, `FAILED`, `PARTIAL` | Kết quả xử lý |
| `failureType` | `ConnectException` | Loại lỗi, nếu có |
| `durationMs` | `438` | Thời gian thực thi |

Nên dùng timestamp UTC (`Instant`) thay vì chuỗi giờ địa phương. Trong hệ thống phân tán, đồng hồ giữa các node có thể lệch; lưu thêm correlation ID và source revision để đối chiếu thứ tự sự kiện.

### 4.1. Nguồn và revision là hai khái niệm khác nhau

Tên `PropertySource` cho biết nguồn nào đang cung cấp property trong Environment, ví dụ một nguồn cấu hình từ Config Server. Nó không nhất thiết cho biết commit Git cụ thể hoặc version secret đã được phát hành.

Nếu cần truy nguyên tới commit, control plane phải truyền revision/label từ nguồn phát hành. Nếu cần truy nguyên tới một secret version, ghi version ID do secret manager trả về. Không tự tạo revision từ timestamp của client vì nó không đại diện cho phiên bản thực tế tại nguồn.

### 4.2. Một thay đổi có thể có nhiều kết quả theo instance

Giả sử Config Server phát hành revision `a41c8d2` tới ba replica. Replica thứ nhất tải và áp dụng thành công, replica thứ hai không kết nối được Config Server, replica thứ ba tải được nhưng bean refresh scope lỗi khi khởi tạo.

Audit cấp nguồn chỉ ghi một lần phát hành. Audit cấp client cần ba kết quả riêng:

| Instance | Revision | Kết quả |
| --- | --- | --- |
| `orders-1` | `a41c8d2` | `SUCCEEDED` |
| `orders-2` | `a41c8d2` | `FAILED_TO_LOAD` |
| `orders-3` | `a41c8d2` | `BEAN_REINITIALIZATION_FAILED` |

Không dùng một event “refresh thành công” ở Config Server để kết luận tất cả client đã áp dụng xong.

## 5. Quan sát property source và giá trị hiệu lực

Spring `Environment` giữ một danh sách `PropertySource`. Thứ tự nguồn ảnh hưởng đến giá trị cuối cùng khi nhiều nguồn cùng cung cấp một key. Vì thế, khi điều tra cấu hình, cần ghi nhận tên nguồn đang cung cấp key, giá trị nào đang có hiệu lực (chỉ với key được phép ghi nhận), profile và origin metadata nếu property source hỗ trợ.

### 5.1. Tìm nguồn đang cung cấp một key

Với `ConfigurableEnvironment`, có thể duyệt các property source để tìm nguồn đầu tiên chứa key:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public final class PropertySourceInspector {

    private PropertySourceInspector() {
    }

    public static Map<String, String> findEffectiveSources(
            ConfigurableEnvironment environment,
            Set<String> keys) {

        Map<String, String> result = new LinkedHashMap<>();

        for (String key : keys) {
            for (PropertySource<?> source : environment.getPropertySources()) {
                if (source.containsProperty(key)) {
                    result.put(key, source.getName());
                    break;
                }
            }
        }

        return result;
    }
}
~~~

Đây là cách kiểm tra nguồn hiệu lực ở mức tổng quát. Một số nguồn có thể bọc nguồn khác, chẳng hạn `CompositePropertySource` hoặc property source tổng hợp do Spring Boot tạo. Khi cần origin chi tiết như file, dòng hoặc nguồn Git, hãy dùng origin metadata do implementation hỗ trợ và metadata revision từ hệ thống phát hành.

### 5.2. Không ghi toàn bộ Environment vào log

`Environment` có thể chứa password, token, private key, URL nội bộ hoặc thông tin kết nối. Không dump toàn bộ property source hoặc Environment vào log để “dễ debug”.

Thay vào đó:

- Ghi danh sách key thay đổi.
- Ghi tên nguồn và revision.
- Chỉ chụp before/after cho allowlist key không nhạy cảm.
- Redact các key có tên chứa `password`, `secret`, `token`, `credential`, `private-key` hoặc các tên tương đương theo chính sách.
- Nếu cần so sánh secret, dùng HMAC với khóa audit được quản lý riêng; không dùng hash không khóa cho secret có entropy thấp.

## 6. EnvironmentChangeEvent và ContextRefresher trong vòng refresh

`ContextRefresher.refresh()` thực hiện các bước chính:

1. Chụp trạng thái property hiện tại.
2. Cập nhật Environment từ nguồn cấu hình theo implementation đang dùng.
3. So sánh trước và sau để tìm key thay đổi.
4. Phát `EnvironmentChangeEvent` với tập key thay đổi.
5. Gọi `RefreshScope.refreshAll()` để invalidation các target trong refresh scope.
6. Trả về tập key thay đổi cho caller.

Điều này giúp một service điều phối refresh có thể ghi nhận thời gian bắt đầu/kết thúc, source metadata và changed keys. Nếu refresh ném exception sau khi Environment đã được cập nhật, kết quả có thể là trạng thái một phần; audit nên phân biệt lỗi hoàn toàn với lỗi xảy ra sau bước cập nhật Environment.

~~~mermaid
sequenceDiagram
    participant Admin as Authenticated operator
    participant Audit as Audited refresh service
    participant Refresher as ContextRefresher
    participant Env as Environment
    participant Beans as Rebind / RefreshScope
    participant Repo as AuditEventRepository

    Admin->>Audit: refresh(source, revision, correlationId)
    Audit->>Audit: Capture actor and startedAt
    Audit->>Env: Snapshot allowlisted values
    Audit->>Refresher: refresh()
    Refresher->>Env: Reload property sources
    Refresher->>Env: Compare before and after
    Refresher->>Beans: Publish EnvironmentChangeEvent
    Refresher->>Beans: Invalidate RefreshScope
    Refresher-->>Audit: changed keys
    Audit->>Env: Snapshot effective values
    Audit->>Repo: Store success/failure and metadata
    Audit-->>Admin: Refresh result
~~~

Khi ứng dụng dùng Config Data hay bootstrap legacy, implementation cụ thể của `ContextRefresher` khác nhau. Hãy dùng bean được Spring Cloud auto-configure cho phiên bản đang chạy thay vì tự tạo một refresher không đúng với cơ chế nạp cấu hình của ứng dụng.

## 7. Ghi audit bằng AuditEventRepository

Spring Boot Actuator có abstraction `AuditEventRepository` để lưu và truy vấn `AuditEvent`. Một `AuditEvent` có thời điểm, principal, loại event và map dữ liệu bổ sung. Endpoint `/actuator/auditevents` chỉ hoạt động khi application context có bean `AuditEventRepository`.

Thêm Actuator starter nếu ứng dụng chưa có:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Starter cung cấp các API audit và endpoint Actuator. Ứng dụng vẫn phải có một implementation `AuditEventRepository` để lưu event; chọn implementation bền vững nếu cần giữ lịch sử qua restart và nhiều replica.

### 7.1. Thiết kế service điều phối refresh

Ví dụ dưới đây bao quanh lời gọi `ContextRefresher.refresh()` để ghi:

- Actor lấy từ danh tính đã xác thực.
- Source và revision do control plane truyền vào.
- Correlation ID để liên kết log ở Config Server và client.
- Thời điểm bắt đầu và kết thúc.
- Changed keys trả về từ Spring Cloud.
- Snapshot trước/sau chỉ cho một allowlist key không nhạy cảm.
- Kết quả pipeline hoặc lỗi có thể xảy ra sau khi Environment đã được cập nhật.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.cloud.context.refresh.ContextRefresher;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Service;

@Service
public class AuditedConfigurationRefresher {

    private static final Set<String> SAFE_KEYS = Set.of(
            "feature.checkout.enabled",
            "limits.pool-size");

    private final ContextRefresher contextRefresher;
    private final AuditEventRepository auditEvents;
    private final ConfigurableEnvironment environment;
    private final Clock clock;

    public AuditedConfigurationRefresher(
            ContextRefresher contextRefresher,
            AuditEventRepository auditEvents,
            ConfigurableEnvironment environment,
            Clock clock) {
        this.contextRefresher = contextRefresher;
        this.auditEvents = auditEvents;
        this.environment = environment;
        this.clock = clock;
    }

    public Set<String> refresh(
            String actor,
            String source,
            String revision,
            String correlationId) {

        Instant requestedAt = clock.instant();
        Map<String, String> before = snapshotSafeValues();

        Set<String> changedKeys;
        Map<String, String> after;
        try {
            changedKeys = contextRefresher.refresh();
            after = snapshotSafeValues();
        }
        catch (RuntimeException exception) {
            Instant failedAt = clock.instant();
            Map<String, String> afterFailure = snapshotSafeValues();

            Map<String, Object> data = commonData(
                    source, revision, correlationId, requestedAt);
            data.put("completedAt", failedAt.toString());
            data.put("durationMs",
                    Duration.between(requestedAt, failedAt).toMillis());
            data.put("before", before);
            data.put("after", afterFailure);
            data.put("observedChangedKeys",
                    changedSafeKeys(before, afterFailure));
            data.put("outcome", "FAILED_OR_PARTIAL");
            data.put("failureType", exception.getClass().getName());

            auditEvents.add(new AuditEvent(
                    failedAt,
                    actor,
                    "CONFIG_REFRESH_PIPELINE_FAILED",
                    data));

            throw exception;
        }

        Instant completedAt = clock.instant();
        Map<String, Object> data = commonData(
                source, revision, correlationId, requestedAt);
        data.put("completedAt", completedAt.toString());
        data.put("durationMs",
                Duration.between(requestedAt, completedAt).toMillis());
        data.put("changedKeys", new TreeSet<>(changedKeys));
        data.put("before", before);
        data.put("after", after);
        data.put("effectivePropertySources",
                PropertySourceInspector.findEffectiveSources(
                        environment, changedKeys));
        data.put("outcome",
                changedKeys.isEmpty() ? "NO_CHANGE" : "PIPELINE_COMPLETED");

        auditEvents.add(new AuditEvent(
                completedAt,
                actor,
                "CONFIG_REFRESH_PIPELINE_COMPLETED",
                data));

        return changedKeys;
    }

    private Map<String, Object> commonData(
            String source,
            String revision,
            String correlationId,
            Instant requestedAt) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("source", source);
        data.put("revision", revision);
        data.put("correlationId", correlationId);
        data.put("requestedAt", requestedAt.toString());
        data.put("application",
                environment.getProperty("spring.application.name", "application"));
        data.put("instanceId",
                environment.getProperty("app.instance-id", "unknown"));
        data.put("profiles", environment.getActiveProfiles());
        return data;
    }

    private Map<String, String> snapshotSafeValues() {
        Map<String, String> values = new LinkedHashMap<>();
        for (String key : SAFE_KEYS) {
            String value = environment.getProperty(key);
            if (value != null) {
                values.put(key, value);
            }
        }
        return values;
    }

    private Set<String> changedSafeKeys(
            Map<String, String> before,
            Map<String, String> after) {
        Set<String> keys = new TreeSet<>(before.keySet());
        keys.addAll(after.keySet());
        keys.removeIf(key ->
                java.util.Objects.equals(before.get(key), after.get(key)));
        return keys;
    }
}
~~~

`PropertySourceInspector` là utility ở phần 5.1. Trong ví dụ, `SAFE_KEYS` chỉ chứa property được phép lưu before/after. Không mở rộng allowlist thành toàn bộ Environment nếu chưa có chính sách phân loại và redaction.

### 7.2. Cung cấp Clock

Dùng `Clock` giúp test thời gian xác định và giúp ứng dụng thống nhất UTC:

~~~java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AuditClockConfiguration {

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }
}
~~~

### 7.3. Nguồn metadata phải đáng tin cậy

Trong ví dụ, `actor` nên được lấy từ principal đã xác thực, còn `source` và `revision` nên được lấy từ nguồn phát hành hoặc Config Server. Không nhận các trường này như chuỗi tự do từ request body mà không xác minh. Nếu người gọi có thể tự khai báo actor hoặc revision, audit log có thể bị làm sai.

`ContextRefresher.refresh()` trả về tập key đã thay đổi, nhưng không trả về commit Git hoặc danh tính người dùng. Phần metadata đó phải được truyền từ control plane hoặc được tra cứu qua API của nguồn cấu hình.

### 7.4. Hiểu đúng kết quả pipeline

`PIPELINE_COMPLETED` có nghĩa là phương thức refresh đã hoàn tất và trả về danh sách changed keys. Nó không khẳng định mọi bean lazy trong refresh scope đã được tạo lại thành công, vì target mới chỉ được tạo khi bean được truy cập lần tiếp theo.

Nếu cần xác nhận sau cùng, hãy kết hợp:

- Health của `RefreshScopeHealthIndicator`.
- Log khởi tạo bean sau lần truy cập đầu tiên.
- Một health check nghiệp vụ kiểm tra cấu hình mới có hoạt động không.
- Audit event riêng cho trạng thái xác minh cuối cùng.

Nếu exception xảy ra sau khi Environment đã đổi, ghi `FAILED_OR_PARTIAL` để phản ánh rằng runtime có thể đã nhận một phần thay đổi. Đừng ghi đơn giản `FAILED` rồi giả định Environment vẫn giữ nguyên.

### 7.5. Audit repository trong production

`AuditEventRepository` là abstraction lưu trữ. Một implementation trong bộ nhớ phù hợp demo/test, nhưng sẽ mất dữ liệu khi process restart và không chia sẻ giữa replicas. Production nên dùng repository bền vững, ví dụ database audit riêng hoặc event store.

Nếu audit là yêu cầu kiểm soát bắt buộc, quyết định rõ hành vi khi ghi audit thất bại: chặn thao tác refresh, đưa sự kiện vào outbox để retry, hay cho phép refresh nhưng phát cảnh báo nghiêm trọng. Không để lỗi ghi audit bị bỏ qua âm thầm.

## 8. Kết hợp event listener với audit

Service ở phần trước ghi nhận request refresh có metadata đầy đủ. Listener bổ sung thông tin về những event runtime đã thực sự được phát.

~~~java
import java.time.Instant;

import org.springframework.cloud.context.environment.EnvironmentChangeEvent;
import org.springframework.cloud.context.scope.refresh.RefreshScopeRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationRuntimeEventListener {

    @EventListener
    public void onEnvironmentChange(EnvironmentChangeEvent event) {
        Instant eventTime = Instant.ofEpochMilli(event.getTimestamp());

        System.out.printf(
                "event=environment-change eventTime=%s changedKeys=%s%n",
                eventTime,
                event.getKeys());
    }

    @EventListener
    public void onRefreshScopeInvalidated(
            RefreshScopeRefreshedEvent event) {
        Instant eventTime = Instant.ofEpochMilli(event.getTimestamp());

        System.out.printf(
                "event=refresh-scope-invalidated eventTime=%s bean=%s%n",
                eventTime,
                event.getName());
    }
}
~~~

Trong ứng dụng thực tế, thay `System.out` bằng logger có structured fields hoặc publisher gửi tới hệ thống quan sát. Listener có thể ghi event timestamp, application name, instance ID và correlation ID nếu context propagation đã được thiết kế.

Không giả định correlation ID tự động đi qua mọi `ApplicationEvent`. Nếu refresh được kích hoạt từ HTTP request, webhook hoặc Bus message, hãy đưa correlation ID vào metadata điều phối và truyền tiếp một cách tường minh.

### 8.1. Nối các event thành một timeline

Một timeline dễ điều tra có thể gồm:

| Mốc | Event | Nơi ghi |
| --- | --- | --- |
| T0 | Config source commit/publish | Git hoặc Config Server audit |
| T1 | Refresh request accepted | API gateway/control plane |
| T2 | Client bắt đầu refresh | Client audit service |
| T3 | `EnvironmentChangeEvent` | Client event listener |
| T4 | `RefreshScopeRefreshedEvent` | Client event listener |
| T5 | Bean được khởi tạo lại/health được xác minh | Client health/log/audit |

Tất cả bản ghi nên chia sẻ cùng correlation ID và source revision. Khi đó có thể tìm ra instance nào chưa nhận revision hoặc instance nào đã nhận nhưng không thể khởi tạo bean.

## 9. Theo dõi thay đổi qua Spring Cloud Config và Bus

Spring Cloud Config Client không mặc định polling Config Server để tìm thay đổi. Với hệ thống nhiều replica, có thể dùng Spring Cloud Bus để phát tín hiệu refresh tới các instance liên quan.

### 9.1. Config Monitor và webhook

Khi Config Server có dependency `spring-cloud-config-monitor` và Spring Cloud Bus được kích hoạt, endpoint `/monitor` có thể nhận webhook từ GitHub, GitLab, Gitea hoặc nhà cung cấp repository khác. Config Server phân tích đường dẫn thay đổi, xác định ứng dụng bị ảnh hưởng và gửi `RefreshRemoteApplicationEvent`.

~~~mermaid
sequenceDiagram
    participant Git as Git provider
    participant Monitor as Config Server /monitor
    participant Bus as Spring Cloud Bus
    participant A as orders-service instance A
    participant B as orders-service instance B

    Git->>Monitor: Signed webhook
    Monitor->>Monitor: Validate signature and changed paths
    Monitor->>Bus: RefreshRemoteApplicationEvent
    Bus-->>A: Deliver refresh event
    Bus-->>B: Deliver refresh event
    A->>A: Reload Environment and audit result
    B->>B: Reload Environment and audit result
~~~

`RefreshRemoteApplicationEvent` chỉ được truyền khi Spring Cloud Bus hoạt động ở cả Config Server và client application. Webhook nên được xác thực bằng chữ ký hoặc token mà provider hỗ trợ. Config Server có thể từ chối request không có secret hợp lệ bằng HTTP 403.

### 9.2. Metadata nào cần truyền qua Bus?

Refresh event giúp phát tán tín hiệu; nó không thay thế audit record. Hãy bảo đảm metadata có thể được liên kết:

- Repository provider và repository name.
- Commit SHA hoặc revision đã phát hành.
- Các file/path cấu hình thay đổi.
- Application/label/profile đích.
- Webhook delivery ID hoặc correlation ID.
- Thời điểm Config Server nhận webhook.

Nếu event mặc định không mang đủ metadata cần thiết cho chính sách audit, hãy lưu bản ghi ở Config Server trước khi broadcast và cung cấp một correlation ID để client ghi kết quả tương ứng.

### 9.3. Phân biệt phát tán và áp dụng

Bus xác nhận thông điệp được gửi theo cơ chế messaging, nhưng không phải bằng chứng mọi replica đã nạp và áp dụng revision. Mỗi client cần ghi kết quả riêng và gửi trạng thái về hệ thống quan sát trung tâm. Có thể theo dõi:

- `RECEIVED`: instance nhận được refresh signal.
- `LOADING`: instance đang tải cấu hình.
- `PIPELINE_COMPLETED`: `ContextRefresher` hoàn tất.
- `VERIFIED`: health check xác nhận cấu hình mới hoạt động.
- `FAILED`: tải hoặc áp dụng thất bại.

Các trạng thái này là quy ước audit của ứng dụng, không phải tên trạng thái bắt buộc của Spring Cloud Bus.

## 10. Quan sát bằng Spring Boot Actuator

Actuator cung cấp các endpoint hữu ích để kiểm tra cấu hình hiện tại và audit events.

| Endpoint | Dữ liệu | Cách dùng |
| --- | --- | --- |
| `/actuator/env` | Property trong Spring Environment | Kiểm tra nguồn property và giá trị hiệu lực |
| `/actuator/configprops` | Các bean `@ConfigurationProperties` | Xác minh giá trị đã bind |
| `/actuator/health` | Trạng thái ứng dụng và health contributor | Kiểm tra refresh scope hoặc health check nghiệp vụ |
| `/actuator/auditevents` | Audit events | Truy vấn actor, event type và metadata đã ghi |
| `/actuator/refresh` | Kích hoạt refresh | Dùng cho refresh legacy/runtime nếu được expose |

### 10.1. Expose có chọn lọc

Ví dụ cấu hình:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - env
          - configprops
          - auditevents
          - refresh
  endpoint:
    env:
      show-values: never
~~~

Chỉ expose các endpoint cần dùng. Trong môi trường production, đặt chúng trên management port/network riêng và dùng Spring Security để yêu cầu quyền phù hợp. Endpoint `refresh` có thể thay đổi trạng thái runtime; endpoint `env` có thể đọc hoặc (nếu bật POST) thay đổi property.

### 10.2. env và configprops không phải audit log

`/actuator/env` phản ánh property trong Environment tại thời điểm truy vấn. `/actuator/configprops` hiển thị dữ liệu đã bind vào `@ConfigurationProperties`. Chúng hữu ích để kiểm tra trạng thái hiện tại, nhưng không lưu lịch sử trước/sau hoặc actor đã gây ra thay đổi.

Các giá trị nhạy cảm của `env` và `configprops` được sanitization mặc định. Giữ chính sách này trong production; không bật hiển thị giá trị thô cho tất cả người dùng chỉ để debug.

### 10.3. auditevents cần AuditEventRepository

Endpoint `/actuator/auditevents` yêu cầu một bean `AuditEventRepository`. Endpoint trả về những audit event mà repository lưu trữ. Nếu dùng repository trong bộ nhớ, lịch sử sẽ mất khi process restart và không được hợp nhất giữa nhiều replica.

Để truy vấn lịch sử đầy đủ, dùng kho audit bền vững và lưu `application`, `instanceId`, `source`, `revision`, `correlationId` trong event data. Actuator endpoint là giao diện quan sát; nó không tự phát hiện mọi thay đổi cấu hình.

### 10.4. POST /actuator/env

Spring Cloud Context hỗ trợ POST vào `/actuator/env` để cập nhật Environment, rebind `@ConfigurationProperties` và log levels. Endpoint này chỉ được bật khi cấu hình `management.endpoint.env.post.enabled=true`, đồng thời nên giới hạn key hợp lệ bằng `management.endpoint.env.post.valid-keys-regex`.

Nếu bật endpoint này, cần kiểm soát quyền ghi, giới hạn key và tạo audit cho request. Nếu chỉ ghi audit trong service wrapper gọi `ContextRefresher`, các thay đổi trực tiếp qua endpoint `env` có thể đi ngoài wrapper đó. Hãy chọn một đường cập nhật có thể quan sát đầy đủ hoặc bổ sung listener/audit cho mọi đường ghi.

## 11. Bảo vệ audit và dữ liệu cấu hình

Audit log thường được giữ lâu hơn log ứng dụng thông thường. Nếu ghi giá trị cấu hình thô, audit store có thể trở thành nơi rò rỉ credential.

### 11.1. Chỉ ghi những gì cần thiết

Ưu tiên ghi:

- Tên key thay đổi.
- Tên nguồn hoặc nguồn phát hành.
- Revision/label/version.
- Actor, application, profile, instance và correlation ID.
- Outcome, failure type và duration.

Chỉ ghi before/after cho key không nhạy cảm đã được duyệt. Với secret, ghi secret version ID hoặc trạng thái rotation; không ghi secret value.

### 11.2. Phân quyền và bảo vệ endpoint

- Chỉ operator hoặc deployment identity có quyền mới được yêu cầu refresh.
- Xác thực chữ ký webhook trước khi Config Server phát tín hiệu refresh.
- Bảo vệ `refresh`, `env`, `configprops` và `auditevents` bằng role phù hợp.
- Không expose toàn bộ Actuator endpoint công khai nếu không có nhu cầu.
- Dùng TLS giữa control plane, Config Server và client.
- Giới hạn retention và quyền truy cập audit store.

### 11.3. Tính toàn vẹn của audit

Nếu audit phục vụ kiểm soát thay đổi, cần chống sửa hoặc xóa trái phép. Có thể dùng append-only storage, database permission riêng, event store hoặc chuyển log sang hệ thống tập trung có retention policy. Ghi thêm actor đã xác thực và correlation ID để điều tra chuỗi thao tác.

Một bản ghi audit không chứng minh giá trị được áp dụng thành công. Nó chỉ chứng minh hệ thống đã ghi nhận một trạng thái cụ thể. Hãy đối chiếu audit event với health và trạng thái runtime của từng instance.

## 12. Log, metrics và tracing

Audit event lưu lịch sử nghiệp vụ. Log cung cấp ngữ cảnh kỹ thuật, metrics cho thấy xu hướng, còn tracing liên kết request hoặc refresh operation qua các dịch vụ.

### 12.1. Structured log

Một log record nên có các field ổn định:

~~~json
{
  "event": "config.refresh.completed",
  "timestamp": "2026-11-18T13:20:15Z",
  "application": "orders-service",
  "instanceId": "orders-7f9c",
  "source": "spring-cloud-config",
  "revision": "a41c8d2",
  "correlationId": "cfg-req-8241",
  "changedKeyCount": 2,
  "outcome": "PIPELINE_COMPLETED",
  "durationMs": 438
}
~~~

Đây là ví dụ cấu trúc log. Không đưa giá trị secret hoặc toàn bộ map property vào record.

### 12.2. Metrics có cardinality thấp

Có thể theo dõi các metric:

| Metric | Ý nghĩa |
| --- | --- |
| `config.refresh.requests` | Số yêu cầu refresh |
| `config.refresh.completed` | Số pipeline hoàn tất |
| `config.refresh.failed` | Số pipeline thất bại |
| `config.refresh.duration` | Thời gian xử lý refresh |
| `config.refresh.changed.keys` | Số lượng key thay đổi mỗi lần |
| `config.refresh.verification.failed` | Số lần health/verification thất bại |

Tag metric chỉ nên dùng các giá trị có tập hợp nhỏ và ổn định như application, environment hoặc outcome. Không dùng actor ID, commit SHA, correlation ID hoặc từng property name làm tag metric vì sẽ tạo cardinality rất lớn. Các giá trị chi tiết này thuộc audit/log/tracing.

### 12.3. Correlation ID qua các thành phần

Một correlation ID nên được tạo ở nơi nhận yêu cầu thay đổi hoặc lấy từ webhook delivery ID đã xác thực. Truyền nó qua:

1. API gateway/control plane.
2. Config Server và webhook monitor.
3. Spring Cloud Bus message hoặc refresh request.
4. Client audit service và event listener.
5. Log/trace và kết quả health verification.

Nếu một instance không nhận được correlation ID, vẫn có thể liên kết bằng revision, application và khoảng thời gian, nhưng việc điều tra sẽ kém chính xác hơn.

## 13. Kiểm thử việc ghi nhận thay đổi cấu hình

Audit service nên được kiểm thử bằng nguồn cấu hình giả, clock cố định và repository mock. Không cần chạy Config Server hoặc message broker để xác minh logic tạo audit record.

### 13.1. Kiểm thử refresh thành công

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.cloud.context.refresh.ContextRefresher;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import org.mockito.ArgumentCaptor;

class AuditedConfigurationRefresherTests {

    @Test
    void recordsSourceRevisionChangedKeysAndBeforeAfterValues() {
        ContextRefresher refresher = mock(ContextRefresher.class);
        AuditEventRepository auditEvents = mock(AuditEventRepository.class);
        MockEnvironment environment = new MockEnvironment();
        environment.setProperty("spring.application.name", "orders-service");
        environment.setActiveProfiles("staging");
        environment.setProperty("feature.checkout.enabled", "false");
        environment.setProperty("limits.pool-size", "8");

        when(refresher.refresh()).thenAnswer(invocation -> {
            environment.setProperty("feature.checkout.enabled", "true");
            environment.setProperty("limits.pool-size", "12");
            return Set.of(
                    "feature.checkout.enabled",
                    "limits.pool-size");
        });

        Instant fixedTime = Instant.parse("2026-11-18T13:20:15Z");
        Clock clock = Clock.fixed(fixedTime, ZoneOffset.UTC);

        AuditedConfigurationRefresher service =
                new AuditedConfigurationRefresher(
                        refresher, auditEvents, environment, clock);

        Set<String> changedKeys = service.refresh(
                "deploy-bot",
                "spring-cloud-config",
                "a41c8d2",
                "cfg-req-8241");

        assertThat(changedKeys)
                .containsExactlyInAnyOrder(
                        "feature.checkout.enabled",
                        "limits.pool-size");

        ArgumentCaptor<AuditEvent> captor =
                ArgumentCaptor.forClass(AuditEvent.class);
        verify(auditEvents).add(captor.capture());

        AuditEvent event = captor.getValue();
        assertThat(event.getType())
                .isEqualTo("CONFIG_REFRESH_PIPELINE_COMPLETED");
        assertThat(event.getPrincipal()).isEqualTo("deploy-bot");
        assertThat(event.getTimestamp()).isEqualTo(fixedTime);
        assertThat(event.getData())
                .containsEntry("source", "spring-cloud-config")
                .containsEntry("revision", "a41c8d2")
                .containsEntry("correlationId", "cfg-req-8241")
                .containsEntry("outcome", "PIPELINE_COMPLETED");
        assertThat((java.util.Map<?, ?>) event.getData().get("before"))
                .containsEntry("feature.checkout.enabled", "false");
        assertThat((java.util.Map<?, ?>) event.getData().get("after"))
                .containsEntry("feature.checkout.enabled", "true");
    }
}
~~~

Test này kiểm tra actor, source, revision, correlation ID, timestamp, changed keys và snapshot trước/sau. Clock cố định giúp assertion không phụ thuộc thời điểm test thực sự chạy.

### 13.2. Kiểm thử refresh thất bại hoặc một phần

Thêm test vào cùng class:

~~~java
@Test
void recordsFailureWhenRefreshThrows() {
    ContextRefresher refresher = mock(ContextRefresher.class);
    AuditEventRepository auditEvents = mock(AuditEventRepository.class);
    MockEnvironment environment = new MockEnvironment();
    environment.setProperty("spring.application.name", "orders-service");

    when(refresher.refresh())
            .thenThrow(new IllegalStateException("controlled refresh failure"));

    Clock clock = Clock.fixed(
            Instant.parse("2026-11-18T13:20:15Z"),
            ZoneOffset.UTC);

    AuditedConfigurationRefresher service =
            new AuditedConfigurationRefresher(
                    refresher, auditEvents, environment, clock);

    org.assertj.core.api.Assertions.assertThatThrownBy(
            () -> service.refresh(
                    "deploy-bot",
                    "spring-cloud-config",
                    "a41c8d2",
                    "cfg-req-8242"))
            .isInstanceOf(IllegalStateException.class);

    ArgumentCaptor<AuditEvent> captor =
            ArgumentCaptor.forClass(AuditEvent.class);
    verify(auditEvents).add(captor.capture());

    assertThat(captor.getValue().getType())
            .isEqualTo("CONFIG_REFRESH_PIPELINE_FAILED");
    assertThat(captor.getValue().getData())
            .containsEntry("outcome", "FAILED_OR_PARTIAL")
            .containsEntry(
                    "failureType",
                    IllegalStateException.class.getName());
}
~~~

Test failure xác nhận service ghi audit rồi ném lại exception cho caller. Trong test tích hợp sâu hơn, hãy thay đổi Environment trước khi ném exception để kiểm tra trạng thái `FAILED_OR_PARTIAL` và danh sách key được quan sát thay đổi.

### 13.3. Kiểm thử event và health

Ngoài service wrapper, test listener với `EnvironmentChangeEvent` và `RefreshScopeRefreshedEvent` để xác minh key và bean name được ghi nhận. Dùng context test có một bean `@RefreshScope`, thay đổi property, gọi refresh, rồi truy cập bean để xác nhận target mới thực sự được khởi tạo.

Nếu ứng dụng có health indicator, kiểm thử cả:

- Refresh scope khỏe sau khi bean tạo lại thành công.
- Refresh scope chuyển `DOWN` khi bean mới không thể khởi tạo hoặc rebind.
- Audit pipeline có thể hoàn tất nhưng bước health verification sau đó thất bại.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Có `EnvironmentChangeEvent` nhưng không có actor | Event mặc định không mang principal | Ghi actor tại control plane và truyền correlation ID |
| Changed keys rỗng | Revision không đổi, nguồn không được reload hoặc giá trị hiệu lực không đổi | Kiểm tra source revision và property source ordering |
| Property source name không chỉ ra Git commit | Tên source chỉ định danh nguồn, không chứa revision | Ghi commit SHA/label riêng từ Config Server |
| Environment đã đổi nhưng bean không đổi | Bean không được rebind hoặc không thuộc refresh scope | Kiểm tra `@ConfigurationProperties`, `@RefreshScope` và giới hạn constructor binding |
| Có `RefreshScopeRefreshedEvent` nhưng bean mới lỗi | Event chỉ báo cache bị invalidated | Kiểm tra lần truy cập tiếp theo, bean initialization log và refresh health |
| `/auditevents` không có dữ liệu | Chưa có `AuditEventRepository` hoặc repository không lưu event | Kiểm tra bean, implementation và cấu hình exposure |
| Audit mất sau restart | Đang dùng repository trong bộ nhớ | Dùng kho audit bền vững |
| Một số replica không refresh | Bus không hoạt động ở server/client, hoặc message không tới instance | Kiểm tra broker, Bus health, destination và correlation ID |
| Webhook không kích hoạt refresh | Secret/signature sai hoặc Config Monitor chưa bật | Kiểm tra webhook validation và dependency `spring-cloud-config-monitor` |
| `/env` hoặc `/configprops` chỉ hiện `******` | Sanitization đang hoạt động | Đây là mặc định bảo vệ dữ liệu; không bật raw values cho mọi người |
| Có refresh nhưng audit service không ghi | Có đường cập nhật khác đi ngoài wrapper | Kiểm soát endpoint `/refresh`, POST `/env` và các trigger khác |
| Audit event bị lặp | Nhiều trigger hoặc refresh được gửi lại | Dùng event ID/correlation ID và xử lý idempotent ở kho audit |

### 14.1. Quy trình điều tra một lần thay đổi

1. Tìm source revision và actor ở Git/configuration control plane.
2. Tìm webhook hoặc refresh request theo correlation ID.
3. Xác định application, profile và instance đích.
4. Kiểm tra client có nhận được tín hiệu refresh không.
5. Kiểm tra `EnvironmentChangeEvent` và changed keys.
6. Kiểm tra property source nào đang cung cấp key.
7. Kiểm tra `@ConfigurationProperties` đã rebind và refresh scope đã invalidated chưa.
8. Kiểm tra lần khởi tạo bean mới và refresh health.
9. Đối chiếu audit event, log, metrics và kết quả verification.

## 15. Bài tập thực hành

### Bài 1 — Ghi event thay đổi Environment

Viết listener cho `EnvironmentChangeEvent`. Ghi timestamp UTC và changed keys, không ghi giá trị property.

### Bài 2 — Phân biệt invalidation và recreation

Tạo bean `@RefreshScope`, phát refresh và quan sát `RefreshScopeRefreshedEvent`. Xác minh bean mới chỉ được tạo khi proxy được gọi tiếp theo.

### Bài 3 — Audit một lần refresh

Tạo `AuditedConfigurationRefresher` dùng `ContextRefresher`, `AuditEventRepository` và `Clock.fixed`. Ghi actor, source, revision, correlation ID và changed keys.

### Bài 4 — Ghi nhận kết quả một phần

Mô phỏng Environment đã đổi nhưng một bean refresh scope lỗi khi khởi tạo. Phân biệt pipeline completion với health verification và ghi audit trạng thái phù hợp.

### Bài 5 — Phát tán tới nhiều replica

Thiết lập Config Monitor và Spring Cloud Bus trong môi trường test. Phát webhook giả lập, xác minh các client nhận event và ghi kết quả theo instance.

### Bài 6 — Bảo vệ dữ liệu

Thêm một property secret vào nguồn cấu hình. Xác minh log/audit chỉ ghi key và source metadata, không ghi giá trị secret.

**Tiêu chí hoàn thành:** bạn có thể truy nguyên một thay đổi từ nguồn cấu hình đến từng instance, biết key nào thay đổi, lúc nào event được xử lý, refresh pipeline có hoàn tất không và bean/health đã được xác minh chưa.

## 16. Tổng kết

Spring Cloud Context phát `EnvironmentChangeEvent` với danh sách key thay đổi và `RefreshScopeRefreshedEvent` khi cache của refresh scope bị invalidated. Các event này là tín hiệu runtime hữu ích, nhưng không mang đầy đủ actor, source revision, correlation ID hoặc kết quả xác minh bean.

Để ghi nhận đầy đủ, hãy kết hợp audit ở nguồn phát hành với audit ở từng client. Một service điều phối có thể bọc `ContextRefresher.refresh()`, chụp snapshot an toàn trước/sau, ghi `AuditEvent` qua `AuditEventRepository` và phân biệt pipeline completion với health verification. Spring Cloud Bus giúp phát tán refresh signal; Config Monitor nhận webhook và cần xác thực chữ ký. Actuator `env`, `configprops`, `health` và `auditevents` hỗ trợ kiểm tra trạng thái hiện tại và lịch sử đã lưu.

Audit chỉ nên ghi metadata và các giá trị được allowlist. Không dump Environment hoặc secret vào log. Trong hệ thống nhiều replica, hãy lưu kết quả riêng theo application/instance và liên kết mọi bản ghi bằng source revision cùng correlation ID.

## Tài liệu tham khảo

- [Spring Cloud Commons 5.0.4 — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): `EnvironmentChangeEvent`, rebind, refresh scope, health indicator và các endpoint refresh.
- [Spring Cloud Config 5.0.6 — Push Notifications and Spring Cloud Bus](https://docs.spring.io/spring-cloud-config/reference/server/push-notifications-and-bus.html): Config Monitor, webhook, `RefreshRemoteApplicationEvent` và webhook signature validation.
- [Spring Boot 4.1.2 — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): `env`, `configprops`, `auditevents`, endpoint security và sanitization.
- [AuditEventRepository API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/audit/AuditEventRepository.html): hợp đồng lưu và truy vấn audit event.
- [AuditEvent API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/audit/AuditEvent.html): timestamp, principal, event type và event data.
- [ContextRefresher source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/refresh/ContextRefresher.java): cách refresh Environment, tính changed keys, phát `EnvironmentChangeEvent` và refresh scope.
- [EnvironmentChangeEvent source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/environment/EnvironmentChangeEvent.java): dữ liệu key set được event cung cấp.
- [RefreshScope source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/scope/refresh/RefreshScope.java): thời điểm phát `RefreshScopeRefreshedEvent` khi invalidation cache.

Đối chiếu hành vi với release train Spring Cloud và phiên bản Spring Boot thực tế. Config Data, bootstrap legacy, Bus và Actuator có thể có khác biệt giữa các thế hệ phiên bản.
