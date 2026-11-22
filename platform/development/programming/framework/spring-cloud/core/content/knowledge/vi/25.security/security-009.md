# Ghi nhận lịch sử thao tác quản trị mà không lộ bí mật

Bài học thuộc chương **Bảo mật** của module **SPRING_CLOUD_CORE**. Trong hệ thống Spring Cloud, người vận hành có thể làm mới cấu hình, thay đổi trạng thái đăng ký service, cập nhật Environment, phát lệnh refresh qua Spring Cloud Bus hoặc điều chỉnh các endpoint quản trị của Actuator. Những thao tác này có thể ảnh hưởng đồng thời đến nhiều service instance, vì vậy hệ thống cần lưu lại ai đã thực hiện, hành động nào được yêu cầu, tài nguyên nào bị tác động và kết quả cuối cùng.

Audit trail phải cung cấp đủ bằng chứng để điều tra và truy vết, nhưng không được trở thành nơi lưu trữ bí mật thứ hai. Không ghi access token, mật khẩu, cookie, API key, private key, giá trị cấu hình bí mật, payload request nguyên bản hoặc thông báo exception có thể chứa dữ liệu nhạy cảm. Cách thiết kế an toàn là tạo event theo schema có kiểm soát, chỉ đưa các trường đã được cho phép vào dữ liệu audit, lưu trữ bền vững với quyền truy cập riêng và kiểm thử cả trường hợp dữ liệu nhạy cảm bị loại bỏ.

Spring Boot Actuator cung cấp nền tảng audit thông qua `AuditEventRepository` và `AuditApplicationEvent`. Spring Security có thể cung cấp các sự kiện xác thực và từ chối quyền. Các thao tác quản trị riêng của Spring Cloud vẫn cần được ứng dụng ghi nhận rõ ràng tại ranh giới thực thi. Bài học kết hợp các thành phần đó với ví dụ refresh cấu hình, thay đổi trạng thái service registry và quản trị endpoint.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích vì sao thao tác quản trị cần audit trail riêng.
2. Phân biệt audit event, application log, trace và metric.
3. Thiết kế schema event gồm actor, action, resource, outcome, timestamp và correlation ID.
4. Phân biệt thao tác được yêu cầu, được chấp thuận, được thực thi thành công và thất bại.
5. Sử dụng `AuditEventRepository` và `AuditApplicationEvent` để ghi event.
6. Hiểu những sự kiện bảo mật Spring Boot Actuator có thể tự ghi nhận.
7. Ghi nhận thao tác refresh, thay đổi service registry và cập nhật Environment.
8. Thiết kế allowlist cho dữ liệu audit và loại bỏ bí mật trước khi serialize.
9. Tránh ghi raw HTTP headers, request body, query string và exception message.
10. Chọn kho audit bền vững thay cho in-memory repository trong production.
11. Bảo vệ endpoint `/actuator/auditevents` và các endpoint quản trị.
12. Giữ tính toàn vẹn, khả năng truy vết và thời hạn lưu trữ của audit record.
13. Kiểm thử audit event cho thành công, thất bại, từ chối quyền và dữ liệu nhạy cảm.
14. Chẩn đoán lỗi khi thao tác đã chạy nhưng audit record không được lưu.

## 2. Vì sao thao tác quản trị phải được audit?

### 2.1. Một thao tác có thể tác động đến nhiều service

Trong môi trường phân tán, thao tác quản trị thường có phạm vi ảnh hưởng rộng:

| Thao tác | Tác động có thể xảy ra |
| --- | --- |
| `POST /actuator/refresh` | Làm mới các bean thuộc `@RefreshScope` trong một instance. |
| `POST /actuator/busrefresh` | Phát yêu cầu refresh tới các instance tham gia Spring Cloud Bus. |
| `POST /actuator/env` | Thay đổi một phần Environment và có thể rebind configuration properties. |
| `POST /actuator/busenv` | Cập nhật Environment trên nhiều instance qua Bus. |
| `POST /actuator/serviceregistry` | Thay đổi trạng thái registration hiện tại của instance. |
| Thay đổi security policy | Có thể cấp hoặc thu hồi quyền quản trị. |
| Xoay vòng credential | Có thể ảnh hưởng kết nối giữa nhiều service và hệ thống ngoài. |

Nếu một cấu hình sai khiến hệ thống ngừng phục vụ, log kỹ thuật có thể cho biết exception nhưng không trả lời đầy đủ ai đã khởi tạo thay đổi, yêu cầu đi qua kênh nào, thay đổi nhắm tới môi trường nào và thao tác được áp dụng trên bao nhiêu instance.

### 2.2. Audit trả lời câu hỏi khác application log

| Loại dữ liệu | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Audit event | Ai đã thực hiện hành động quản trị nào, với kết quả gì? | Người vận hành A yêu cầu refresh cấu hình của orders-service; kết quả thành công. |
| Application log | Ứng dụng đã xử lý nội bộ ra sao? | Config listener nhận event và khởi tạo lại bean. |
| Trace | Request đi qua những service/component nào và mất bao lâu? | Request quản trị đi qua gateway, management API và service instance. |
| Metric | Sự kiện hoặc hoạt động xảy ra bao nhiêu lần? | Số lần refresh thành công/thất bại trong một khoảng thời gian. |

Audit event có schema ổn định, phục vụ điều tra và đối soát. Application log có thể thay đổi theo phiên bản code và mức log; trace có sampling; metric thường tổng hợp và không lưu actor của từng thao tác. Không dùng một loại dữ liệu thay thế hoàn toàn cho loại còn lại.

### 2.3. Audit cả ý định và kết quả

Một thao tác quản trị nên có ít nhất hai mốc:

1. **Requested:** người dùng hoặc automation gửi yêu cầu.
2. **Completed/Failed:** hệ thống thực thi xong và ghi nhận kết quả.

Có thể thêm mốc **Authorized/Denied** nếu cần phân biệt yêu cầu bị chặn bởi policy với yêu cầu đã được cho phép. Với thao tác chạy bất đồng bộ hoặc qua Bus, nên có thêm trạng thái **Accepted/Dispatched** và **Applied** ở từng instance.

~~~mermaid
sequenceDiagram
    actor Admin as Administrator
    participant API as Management endpoint
    participant Audit as Audit service
    participant Op as Spring Cloud operation
    participant Store as Durable audit store

    Admin->>API: POST management action
    API->>Audit: Record REQUESTED
    Audit->>Store: Append request event
    API->>Op: Execute operation
    alt Operation succeeds
        Op-->>API: Success result
        API->>Audit: Record SUCCEEDED
        Audit->>Store: Append completion event
        API-->>Admin: 2xx response
    else Operation fails
        Op-->>API: Failure
        API->>Audit: Record FAILED
        Audit->>Store: Append failure event
        API-->>Admin: Error response
    end
~~~

Chỉ ghi một event sau khi trả HTTP 200 có thể bỏ sót yêu cầu đã được nhận nhưng process dừng trước khi hoàn tất. Chỉ ghi event trước khi thực thi lại không chứng minh thao tác thành công. Dùng event ID hoặc correlation ID chung để nối các mốc của cùng một yêu cầu.

## 3. Thiết kế audit event

### 3.1. Những trường nên có

Một event quản trị cần đủ thông tin để trả lời ai, làm gì, ở đâu, khi nào và kết quả thế nào.

| Trường | Mục đích | Ví dụ |
| --- | --- | --- |
| `eventId` | Định danh duy nhất của record. | UUID. |
| `timestamp` | Thời điểm event được ghi, dùng UTC. | `2026-11-18T12:30:15Z`. |
| `principal` | Danh tính đã xác thực thực hiện thao tác. | `user:alice` hoặc `service:release-bot`. |
| `actorType` | Phân biệt người dùng, service account hoặc automation. | `HUMAN`, `SERVICE_ACCOUNT`. |
| `type` | Loại event ổn định để lọc và báo cáo. | `ADMIN_CONFIG_REFRESH_SUCCEEDED`. |
| `action` | Tên thao tác ở cấp nghiệp vụ. | `CONFIG_REFRESH`. |
| `resource` | Tài nguyên bị tác động. | `application:orders-service`. |
| `environment` | Môi trường mục tiêu. | `production`. |
| `outcome` | Kết quả thao tác. | `REQUESTED`, `SUCCESS`, `FAILURE`, `DENIED`. |
| `requestId` | Nối event với request gốc. | Request ID từ gateway. |
| `traceId` | Liên kết với distributed trace nếu có. | Trace ID đã được tạo bởi tracing infrastructure. |
| `source` | Kênh khởi tạo. | `ACTUATOR_HTTP`, `AUTOMATION`, `BUS`. |
| `reasonCode` | Mã lý do đã chuẩn hóa. | `REGISTRY_UNAVAILABLE`. |
| `changeSummary` | Tóm tắt thay đổi đã được cho phép ghi. | Danh sách property key an toàn. |

`AuditEvent` của Spring Boot đã cung cấp các trường nền tảng như timestamp, principal, type và data. Các trường còn lại có thể đặt trong map data hoặc trong schema riêng của kho audit.

### 3.2. Dùng tên event ổn định

Nên chuẩn hóa event type và không đổi tên tùy tiện theo từng class Java:

| Event type | Ý nghĩa |
| --- | --- |
| `ADMIN_ACTION_REQUESTED` | Một thao tác quản trị được gửi đến hệ thống. |
| `ADMIN_ACTION_DENIED` | Yêu cầu bị từ chối bởi authorization policy. |
| `ADMIN_CONFIG_REFRESH_SUCCEEDED` | Refresh cấu hình đã hoàn tất. |
| `ADMIN_CONFIG_REFRESH_FAILED` | Refresh cấu hình thất bại. |
| `ADMIN_ENV_PROPERTY_UPDATED` | Một property được cập nhật qua kênh quản trị. |
| `ADMIN_SERVICE_STATUS_CHANGED` | Trạng thái registration đã được thay đổi. |
| `ADMIN_BUS_REFRESH_DISPATCHED` | Yêu cầu refresh đã được phát qua Bus. |
| `ADMIN_BUS_REFRESH_APPLIED` | Một instance đã áp dụng refresh. |
| `ADMIN_SECRET_ROTATION_REQUESTED` | Quy trình xoay vòng secret được yêu cầu. |
| `ADMIN_SECRET_ROTATION_COMPLETED` | Quy trình xoay vòng secret hoàn tất. |

Có thể thêm event type riêng theo domain. Mỗi type cần có định nghĩa về actor, resource, outcome và trường data được phép lưu.

### 3.3. Ví dụ record an toàn

Một record có thể trông như sau:

~~~json
{
  "eventId": "7c76c8b2-9a7f-4c83-9b8d-8df0f1d6d5e1",
  "timestamp": "2026-11-18T12:30:15Z",
  "principal": "user:alice",
  "type": "ADMIN_CONFIG_REFRESH_SUCCEEDED",
  "data": {
    "actorType": "HUMAN",
    "action": "CONFIG_REFRESH",
    "resource": "application:orders-service",
    "environment": "production",
    "outcome": "SUCCESS",
    "source": "ACTUATOR_HTTP",
    "requestId": "req-84c12",
    "configRevision": "git:8b7e4a1"
  }
}
~~~

Record chỉ chứa định danh và metadata cần thiết để điều tra. Nó không lưu nội dung cấu hình, token truy cập Config Server hoặc giá trị credential vừa được nạp.

### 3.4. Actor phải lấy từ danh tính đã xác thực

Lấy actor từ SecurityContext hoặc principal do authentication provider xác minh. Không tin một header tùy ý như `X-User` hoặc query parameter `?user=alice` để xác định người thực hiện.

Với người dùng, lưu subject ID ổn định do identity provider cấp. Với automation, lưu client ID hoặc service account đã xác thực. Không lưu toàn bộ JWT, access token, refresh token, session cookie hoặc object `Authentication` được serialize.

Nếu request không có người dùng trực tiếp, ghi actor theo danh tính hệ thống đã thực hiện thao tác, chẳng hạn `service:config-controller`. Không tự gán người vận hành cuối cùng nếu hệ thống không có bằng chứng.

## 4. Quy tắc quan trọng: chỉ ghi dữ liệu đã cho phép

### 4.1. Dùng allowlist thay vì blacklist

Blacklisting cố gắng nhận diện mọi tên trường nhạy cảm. Cách đó dễ bỏ sót một field mới như `clientSecretValue`, `privateKeyMaterial` hoặc một tên nội bộ không theo quy ước. Allowlist chỉ cho phép những field đã được xác định trước.

Ví dụ allowlist cho một thao tác refresh:

- `action`
- `resource`
- `environment`
- `outcome`
- `requestId`
- `configRevision`
- `changedKeys` nếu các key đã được duyệt

Không thêm raw request body, map Environment, toàn bộ `@ConfigurationProperties` hoặc object cấu hình vào event.

### 4.2. Những dữ liệu không được ghi

| Dữ liệu | Cách xử lý |
| --- | --- |
| Password, passphrase | Không ghi giá trị. |
| Access token, refresh token, bearer token | Không ghi token hoặc header Authorization. |
| Cookie, session ID | Không ghi cookie/session secret. |
| API key, client secret | Không ghi giá trị hoặc bản mã hóa. |
| Private key, signing key | Không ghi nội dung khóa. |
| Giá trị property nhạy cảm | Không ghi trước/sau, kể cả giá trị đã mã hóa. |
| Raw request/response body | Không đưa vào audit record. |
| Query string đầy đủ | Chỉ ghi route/action đã chuẩn hóa, bỏ query values. |
| Exception message không kiểm soát | Ghi reason code và exception class đã cho phép. |
| Toàn bộ Authentication/JWT object | Chỉ ghi principal ID và metadata tối thiểu. |

Giá trị đã mã hóa vẫn có thể là dữ liệu nhạy cảm. Log một ciphertext không có nghĩa là đã loại bỏ rủi ro; ciphertext có thể bị giải mã ở nơi khác hoặc dùng làm dữ liệu tương quan để tấn công.

### 4.3. Property key cũng cần được xem xét

Tên property thường an toàn hơn giá trị, nhưng không phải lúc nào cũng vô hại. Key có thể tiết lộ tên dịch vụ nội bộ, topology, vendor hoặc chức năng bảo mật. Chỉ lưu các key thuộc allowlist, hoặc lưu nhóm thay đổi như `PAYMENT_PROVIDER_SETTINGS` thay cho tên property cụ thể.

Nếu thao tác xoay vòng credential, có thể ghi `credentialRotation=true` và loại credential ở mức khái quát. Không ghi secret reference nếu đường dẫn Vault/secret store cũng bị xem là thông tin nhạy cảm trong tổ chức.

### 4.4. Không dùng hash đơn giản để thay thế việc loại bỏ secret

Hash của password hoặc token có thể cho phép dò đoán nếu giá trị có entropy thấp hoặc có thể lấy từ không gian hữu hạn. Với audit trail, thông thường không cần lưu digest của secret. Nếu có yêu cầu đối soát integrity, dùng cơ chế chữ ký/HMAC với khóa được quản lý riêng và chỉ áp dụng cho record đã loại bỏ secret.

## 5. Spring Boot Actuator Audit framework

### 5.1. AuditEvent và AuditEventRepository

Spring Boot Actuator cung cấp `AuditEvent` để biểu diễn một sự kiện audit. Event gồm thời điểm, principal, type và data. `AuditEventRepository` là abstraction để ghi và truy vấn các event.

Các method cốt lõi:

~~~java
import java.time.Instant;
import java.util.List;

public interface AuditEventRepository {

    void add(AuditEvent event);

    List<AuditEvent> find(
            String principal,
            Instant after,
            String type
    );
}
~~~

- `add(event)` ghi một audit record.
- `find(principal, after, type)` tìm record theo principal, thời điểm bắt đầu và loại event.
- Các bộ lọc có thể để null khi muốn tìm rộng hơn.

Ứng dụng có thể inject repository để ghi event trực tiếp. Cách khác là publish `AuditApplicationEvent` thông qua Spring `ApplicationEventPublisher`; audit infrastructure sẽ nhận event và chuyển tới repository.

### 5.2. InMemoryAuditEventRepository chỉ phù hợp phát triển

Spring Boot cung cấp `InMemoryAuditEventRepository` để tiện thử nghiệm. Dữ liệu nằm trong bộ nhớ process nên có thể mất khi ứng dụng restart, không phù hợp cho audit trail production cần truy vết lâu dài.

Trong production, cung cấp implementation `AuditEventRepository` ghi vào kho bền vững như database audit riêng, log pipeline có bảo vệ hoặc hệ thống lưu trữ append-only. Thiết kế repository cần đáp ứng retention, truy vấn theo principal/type/time và phân quyền độc lập.

### 5.3. AuditApplicationEvent cho event tùy chỉnh

Ví dụ phát một event với principal, type và map data:

~~~java
import java.util.Map;

import org.springframework.boot.actuate.audit.listener.AuditApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class AdminAuditPublisher {

    private final ApplicationEventPublisher eventPublisher;

    public AdminAuditPublisher(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void record(
            String principal,
            String eventType,
            String action,
            String resource,
            String outcome,
            String requestId) {

        Map<String, Object> safeData = Map.of(
                "action", action,
                "resource", resource,
                "outcome", outcome,
                "requestId", requestId
        );

        eventPublisher.publishEvent(
                new AuditApplicationEvent(principal, eventType, safeData)
        );
    }
}
~~~

Ví dụ chỉ đưa các trường đã chọn vào map. Không truyền object request, Environment, credentials hoặc exception message vào `safeData`.

`AuditApplicationEvent` đóng gói một `AuditEvent` và phát qua Spring event mechanism. Repository phải được cấu hình để nhận và lưu event. Nếu ứng dụng tự inject repository và gọi `add()` trực tiếp, vẫn phải dùng cùng allowlist và cùng schema.

### 5.4. Ghi actor từ SecurityContext

Một helper có thể lấy tên principal từ Authentication:

~~~java
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public final class AuditPrincipal {

    private AuditPrincipal() {
    }

    public static String currentActor() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return "anonymous";
        }

        return authentication.getName();
    }
}
~~~

Chỉ lấy `getName()`. Không gọi `toString()` trên Authentication, không serialize credentials hoặc toàn bộ principal object. Với service-to-service call, bảo đảm Authentication đại diện đúng service account đã xác thực.

## 6. Những security event Spring Boot có thể tự ghi

### 6.1. Bật audit infrastructure

Khi Spring Security được dùng, Spring Boot Actuator có thể phát các audit event cho:
- Authentication thành công.
- Authentication thất bại.
- Authorization bị từ chối.

Để bật audit framework, cung cấp bean `AuditEventRepository`. Khi repository tồn tại, audit listeners có thể lưu security event vào đó.

Ví dụ cấu hình development:

~~~java
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.boot.actuate.audit.InMemoryAuditEventRepository;
import org.springframework.context.annotation.Bean;

@Bean
AuditEventRepository auditEventRepository() {
    return new InMemoryAuditEventRepository();
}
~~~

Đây chỉ là cấu hình phục vụ development/test. Trong production, thay bằng repository bền vững.

### 6.2. Tùy chỉnh authentication và authorization audit listener

Spring Boot cung cấp `AbstractAuthenticationAuditListener` và `AbstractAuthorizationAuditListener` để tùy chỉnh cách security event được chuyển thành audit record. Có thể mở rộng listener khi cần thay đổi event type hoặc metadata, nhưng vẫn phải áp dụng allowlist.

Không ghi thông tin credential trong event failure. Ví dụ, một `BadCredentialsException` không phải lý do để lưu mật khẩu người dùng đã nhập hoặc request body đăng nhập.

### 6.3. Spring Security authentication events

Spring Security có `AuthenticationSuccessEvent` và các `AuthenticationFailureEvent`. Nếu muốn tự xử lý trực tiếp, cấu hình `AuthenticationEventPublisher` phù hợp rồi lắng nghe bằng `@EventListener`.

~~~java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher applicationEventPublisher) {

    return new DefaultAuthenticationEventPublisher(applicationEventPublisher);
}
~~~

Listener có thể chuyển các event thành audit event với principal, loại xác thực và kết quả. Tránh lưu token, password, credentials hoặc toàn bộ Authentication.

### 6.4. Authorization denied event

Spring Security có `AuthorizationDeniedEvent` cho trường hợp quyết định authorization bị từ chối. Cần có `AuthorizationEventPublisher` để phát các event tương ứng.

Authorization granted events có thể tạo lượng dữ liệu rất lớn và không mặc định được phát trong một số cấu hình Spring Security hiện hành. Chỉ bật khi có nhu cầu rõ ràng, ví dụ chỉ ghi các quyền quản trị nhạy cảm, thay vì ghi mọi quyết định authorization thông thường.

### 6.5. Security event không thay thế audit thao tác quản trị

Authentication success chỉ chứng minh người dùng đã xác thực. Authorization denied chỉ chứng minh một yêu cầu bị từ chối. Chúng không chứng minh một lệnh refresh hoặc thay đổi registry đã được thực thi thành công.

Ví dụ một admin đăng nhập thành công rồi gửi POST `/actuator/refresh`. Audit trail cần ít nhất:
- Event xác thực thành công.
- Event yêu cầu refresh.
- Event kết quả refresh.
- Có thể có event access denied nếu quyền không cho phép.

Các event phải được nối bằng request ID hoặc trace ID khi có thể.

## 7. Ghi nhận thao tác quản trị Spring Cloud

### 7.1. Refresh cấu hình

Spring Cloud Context cung cấp endpoint `/actuator/refresh` để làm mới context/configuration và invalidate các bean thuộc `@RefreshScope`. Nếu một thao tác refresh có thể thay đổi hành vi của ứng dụng, hãy ghi actor, application/service ID, environment, config revision và kết quả.

Không ghi toàn bộ Environment hoặc giá trị các property được refresh. Nếu cần biết thay đổi nào được áp dụng, chỉ lưu property key đã được allowlist hoặc một change-set ID có thể đối soát ở kho cấu hình an toàn.

Một service/facade có thể ghi event trước và sau thao tác:

~~~java
import org.springframework.cloud.context.scope.refresh.RefreshScope;
import org.springframework.stereotype.Service;

@Service
public class ConfigurationRefreshService {

    private final RefreshScope refreshScope;
    private final AdminAuditPublisher audit;

    public ConfigurationRefreshService(
            RefreshScope refreshScope,
            AdminAuditPublisher audit) {
        this.refreshScope = refreshScope;
        this.audit = audit;
    }

    public void refresh(
            String actor,
            String application,
            String requestId) {

        audit.record(
                actor,
                "ADMIN_CONFIG_REFRESH_REQUESTED",
                "CONFIG_REFRESH",
                "application:" + application,
                "REQUESTED",
                requestId
        );

        try {
            refreshScope.refreshAll();

            audit.record(
                    actor,
                    "ADMIN_CONFIG_REFRESH_SUCCEEDED",
                    "CONFIG_REFRESH",
                    "application:" + application,
                    "SUCCESS",
                    requestId
            );
        }
        catch (RuntimeException exception) {
            audit.record(
                    actor,
                    "ADMIN_CONFIG_REFRESH_FAILED",
                    "CONFIG_REFRESH",
                    "application:" + application,
                    "FAILURE",
                    requestId
            );
            throw exception;
        }
    }
}
~~~

Đây là ví dụ minh họa cho một operation service do ứng dụng quản lý. Nếu dùng trực tiếp built-in Actuator endpoint, cần bổ sung instrumentation ở ranh giới HTTP hoặc cơ chế mở rộng tương ứng để ghi nhận request và kết quả. Không giả định endpoint tự phát custom audit event cho mọi lần refresh.

### 7.2. Thay đổi trạng thái ServiceRegistry

Spring Cloud Commons cung cấp endpoint `/actuator/serviceregistry`. GET đọc trạng thái registration hiện tại; POST gửi JSON có field `status` để yêu cầu provider đổi trạng thái. Các giá trị hợp lệ phụ thuộc provider; Eureka thường có `UP`, `DOWN`, `OUT_OF_SERVICE` và `UNKNOWN`.

Audit event nên ghi:
- Actor và nguồn yêu cầu.
- Service ID/instance ID mục tiêu.
- Trạng thái cũ nếu đọc được.
- Trạng thái mới được yêu cầu.
- Kết quả provider trả về.
- Request ID.

Trạng thái service không phải bí mật nên có thể ghi giá trị status. Tuy nhiên, không ghi toàn bộ Registration object vì metadata có thể chứa địa chỉ, thông tin môi trường hoặc dữ liệu nội bộ không cần thiết.

### 7.3. Cập nhật Environment qua /actuator/env

Spring Cloud Context cho phép POST `/actuator/env` để cập nhật Environment và rebind configuration properties. Endpoint này cần được bật tường minh bằng `management.endpoint.env.post.enabled=true`; có thể giới hạn các property key được phép cập nhật bằng `management.endpoint.env.post.valid-keys-regex`.

Ví dụ cấu hình giới hạn:

~~~yaml
management:
  endpoint:
    env:
      post:
        enabled: true
        valid-keys-regex: "^(app\\.feature\\.[a-zA-Z0-9.-]+\\.enabled)$"
~~~

Regex chỉ cho phép một nhóm property flag đã xác định. Hãy điều chỉnh theo key thực tế của ứng dụng và kiểm thử các key bị từ chối.

Khi audit, ghi key đã được cho phép và outcome. Không ghi field `value` của request, vì cùng endpoint có thể cập nhật password, token, endpoint credential hoặc secret reference. Không log raw JSON body.

### 7.4. Spring Cloud Bus refresh và bus environment

`/actuator/busrefresh` phát refresh tới các instance qua Spring Cloud Bus. `/actuator/busenv` có thể cập nhật key/value trên nhiều instance. Với thao tác phân tán:
- Ghi event ở nơi khởi tạo lệnh.
- Ghi event dispatch khi message được phát thành công.
- Nếu cần xác minh rollout, ghi event applied/failure tại từng instance.
- Dùng correlation ID hoặc command ID chung để nối các kết quả.
- Không ghi giá trị gửi qua busenv; chỉ ghi key an toàn hoặc change-set ID.

Một event "dispatch thành công" chỉ chứng minh message đã được gửi tới Bus theo contract hiện tại. Nó không chứng minh tất cả instance đã áp dụng thay đổi. Tách trạng thái dispatched và applied trong audit schema.

## 8. Bắt event tại ranh giới thực thi

### 8.1. Ưu tiên audit trong service thực hiện hành động

Khi ứng dụng có một service/facade riêng để thực hiện quản trị, ghi audit tại chính service đó. Cách này có thể ghi được:
- Ý định trước khi thao tác.
- Kết quả thật sau khi thao tác.
- Resource ID đã được chuẩn hóa.
- Reason code khi thất bại.
- Change-set ID hoặc version đã áp dụng.

Đây là vị trí tốt để phân biệt operation thành công về mặt nghiệp vụ với HTTP request chỉ trả về một response.

### 8.2. Khi dùng built-in Actuator endpoint

Nếu không thể thay built-in endpoint bằng facade riêng, có thể ghi metadata HTTP ở một lớp filter/interceptor tại management boundary:
- Chỉ theo dõi các method thay đổi trạng thái như POST.
- So khớp route với allowlist endpoint quản trị.
- Lấy actor từ SecurityContext.
- Ghi request ID, route đã chuẩn hóa và thời gian.
- Sau khi request kết thúc, ghi HTTP outcome.
- Không đọc/serialize body và không ghi headers/query values.

Với Servlet stack có thể dùng filter; với WebFlux dùng WebFilter tương ứng. Filter chỉ quan sát request/response. Nếu operation chạy bất đồng bộ hoặc trả accepted trước khi hoàn tất, cần event từ operation handler hoặc consumer để xác nhận kết quả cuối.

### 8.3. Phân biệt HTTP status và outcome nghiệp vụ

HTTP 2xx có thể có nghĩa lệnh đã được nhận hoặc dispatch, chưa chắc tất cả tác động đã hoàn tất. HTTP 4xx có thể phản ánh validation hoặc authorization; HTTP 5xx có thể xảy ra sau khi một phần operation đã chạy.

Ghi cả outcome nghiệp vụ và HTTP status đã chuẩn hóa nếu cần. Không suy luận rằng status code là bằng chứng đầy đủ về trạng thái toàn hệ thống.

## 9. Không để log và trace làm rò rỉ bí mật

### 9.1. Các nguồn rò rỉ phổ biến

| Nguồn | Rủi ro |
| --- | --- |
| HTTP access log | Ghi URL query có token hoặc body POST. |
| Request/response logging filter | Ghi Authorization, Cookie hoặc payload cấu hình. |
| Exception logging | Exception message chứa URI có credential hoặc giá trị property. |
| Debug log của configuration client | In property source hoặc dữ liệu cấu hình. |
| Trace baggage | Truyền secret vào tag/baggage qua nhiều service. |
| Audit data map | Developer thêm nguyên object request hoặc configuration vào map. |
| Service metadata | Registration metadata chứa thông tin nội bộ không cần thiết. |

Bảo vệ audit stream nhưng để access log hoặc tracing system ghi cùng bí mật vẫn là rò rỉ. Chính sách redaction phải áp dụng ở mọi lớp có thể thu thập dữ liệu.

### 9.2. Không log các header nhạy cảm

Không đưa các header sau vào audit data hoặc log chung:
- `Authorization`.
- `Cookie` và `Set-Cookie`.
- Header API key.
- Header chứa session hoặc credential tùy chỉnh.
- Header có dữ liệu người dùng nhạy cảm nếu không cần cho điều tra.

Nếu cần lưu client identity, lấy client ID đã xác thực từ security context thay vì sao chép token từ header.

### 9.3. Không log query string hoặc raw body

Một URL như `/actuator/env?token=...` có thể làm lộ secret qua access log. Ghi route template `/actuator/env` và HTTP method là đủ cho audit event.

Request body của `/actuator/env` hoặc `/actuator/busenv` có thể chứa giá trị cấu hình. Không dùng body caching filter để serialize toàn bộ request vào audit. Nếu cần tóm tắt thay đổi, parse ở lớp operation và chỉ lấy key thuộc allowlist.

### 9.4. Sanitization phải diễn ra trước serialization

Đừng dựa vào việc che dữ liệu trong dashboard sau khi đã ghi raw event vào database. Hãy lọc dữ liệu trước khi tạo `AuditEvent` hoặc trước khi repository ghi record.

Một chính sách allowlist nên:
1. Xác định event type.
2. Chọn các field hợp lệ cho event type đó.
3. Kiểm tra kiểu và độ dài dữ liệu.
4. Chuẩn hóa chuỗi, loại control characters và giới hạn kích thước.
5. Loại field không nằm trong schema.
6. Chỉ sau đó mới serialize và persist.

Không truyền object tùy ý vào audit map. Dùng DTO/schema riêng cho từng loại thao tác nếu dữ liệu có cấu trúc phức tạp.

## 10. Lưu trữ audit bền vững

### 10.1. Repository production

`AuditEventRepository` chỉ định nghĩa hợp đồng add/find; cách lưu bền vững do ứng dụng cung cấp. Một repository production có thể chuyển event thành record immutable rồi ghi vào audit store:

~~~java
public final class PersistentAuditEventRepository
        implements AuditEventRepository {

    private final AuditRecordStore store;

    public PersistentAuditEventRepository(AuditRecordStore store) {
        this.store = store;
    }

    @Override
    public void add(AuditEvent event) {
        AuditRecord record = AuditRecord.fromAllowlistedEvent(event);
        store.append(record);
    }

    @Override
    public List<AuditEvent> find(
            String principal,
            Instant after,
            String type) {

        return store.find(principal, after, type)
                .stream()
                .map(AuditRecord::toAuditEvent)
                .toList();
    }
}
~~~

`AuditRecordStore` và `AuditRecord` trong ví dụ là abstraction do ứng dụng định nghĩa, không phải class có sẵn của Spring Boot. Điểm quan trọng là chuyển đổi bằng allowlist trước khi ghi vào kho.

### 10.2. Tính append-only và quyền truy cập

Audit record nên được append, không cho ứng dụng nghiệp vụ sửa hoặc xóa record đã ghi. Cân nhắc:
- Tách kho audit khỏi database nghiệp vụ.
- Dùng identity chỉ có quyền append cho service ghi audit.
- Cấp quyền read riêng cho nhóm điều tra/audit.
- Hạn chế quyền delete/update ở tầng storage.
- Bật encryption at rest và backup có kiểm soát.
- Dùng immutable/WORM storage hoặc cơ chế tamper-evident nếu yêu cầu tuân thủ cần.
- Ghi lại thao tác truy cập/export audit data nếu dữ liệu nhạy cảm.
- Không đặt signing key hoặc HMAC key cạnh chính record mà nó bảo vệ.

Hash chain hoặc chữ ký số có thể giúp phát hiện sửa đổi, nhưng không tự bảo vệ nếu attacker có quyền thay cả dữ liệu lẫn khóa. Phân tách quyền và quản lý khóa là điều kiện cần.

### 10.3. Retention và privacy

Không giữ audit data vô thời hạn nếu chính sách không yêu cầu. Xác định:
- Thời hạn lưu theo loại event.
- Quy trình archive và purge có kiểm soát.
- Quyền truy cập theo vai trò.
- Cách xử lý định danh cá nhân theo chính sách privacy.
- Cách giữ khả năng điều tra khi user account bị xóa hoặc đổi tên.

Ưu tiên subject ID ổn định và chỉ lưu thông tin cá nhân tối thiểu cần thiết. Không ghi email, số điện thoại hoặc địa chỉ IP nếu không có mục đích và chính sách rõ ràng.

### 10.4. Đồng bộ thời gian và correlation

Dùng timestamp UTC và đồng bộ clock giữa các service/host. Lưu request ID hoặc command ID để ghép event trên nhiều instance. Nếu dùng trace ID, bảo đảm tracing context không chứa secret và ID không bị thay đổi giữa các hop.

## 11. Đảm bảo audit không bị mất

### 11.1. Ghi trước và sau thao tác

Với thao tác quan trọng, ghi event yêu cầu trước khi thực thi và event kết quả sau khi hoàn tất. Nếu hệ thống audit store không sẵn sàng, cần có policy rõ:
- Với hành động đặc quyền có rủi ro cao, có thể từ chối thực thi nếu không thể ghi durable intent.
- Với thao tác ít rủi ro hơn, có thể cho phép chạy nhưng phải tạo alert và retry ghi audit.
- Không âm thầm bỏ event khi repository lỗi.

Quyết định fail-closed hay fail-open phải dựa trên impact và yêu cầu vận hành, không dùng một lựa chọn cho mọi thao tác.

### 11.2. Outbox hoặc message queue

Nếu operation cập nhật database nội bộ và cần audit nguyên tử với thay đổi, cân nhắc transactional outbox: ghi business change và audit/outbox row trong cùng transaction, sau đó relay tới audit store.

Nếu thao tác gọi registry từ xa hoặc phát message tới Bus, không có transaction phân tán tự động bao phủ mọi hệ thống. Ghi command/request event trước, rồi ghi kết quả hoặc reconciliation event sau. Có thể dùng idempotency key để tránh ghi trùng khi retry.

### 11.3. Idempotency và duplicate event

Message retry hoặc request retry có thể tạo nhiều event. Mỗi thao tác nên có request/command ID; mỗi event có event ID riêng. Repository hoặc consumer có thể dùng event ID để chống insert trùng, đồng thời vẫn giữ các mốc requested, dispatched và applied khác nhau.

Không loại bỏ hai event chỉ vì principal, action và timestamp gần nhau; chúng có thể là hai thao tác hợp lệ khác nhau.

## 12. Bảo vệ endpoint quản trị và audit endpoint

### 12.1. Exposure không đồng nghĩa authorization

Spring Boot Actuator chỉ expose HTTP health endpoint theo mặc định trong cấu hình thông thường. Các endpoint khác cần được expose rõ ràng. Việc thêm endpoint vào exposure list không tự cấp quyền cho admin phù hợp; cần Spring Security, management network và access policy.

Ví dụ chỉ expose health và audit events:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,auditevents"
~~~

Đường dẫn mặc định của audit endpoint là `/actuator/auditevents`. Endpoint yêu cầu `AuditEventRepository` bean.

### 12.2. Chỉ nhóm audit reader được đọc audit events

`auditevents` có thể trả principal, loại thao tác, timestamp và data. Đây là dữ liệu nhạy cảm vì nó cho biết ai đã làm gì trong hệ thống. Chỉ cấp GET cho vai trò audit reader/incident responder phù hợp; không mở endpoint cho user thông thường hoặc Internet công cộng.

Các endpoint thay đổi trạng thái như `refresh`, `env`, `serviceregistry` và `busrefresh` cần quyền write riêng. Không gộp quyền đọc audit với quyền thay đổi cấu hình nếu không có lý do.

### 12.3. Ví dụ SecurityFilterChain cho Actuator

Ví dụ khái quát với Spring Security:

~~~java
import org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ManagementSecurityConfiguration {

    @Bean
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint());

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .requestMatchers(EndpointRequest.to("auditevents"))
                    .hasRole("AUDIT_READER")
                .requestMatchers(EndpointRequest.to(
                        "refresh", "env", "serviceregistry", "busrefresh", "busenv"))
                    .hasRole("PLATFORM_ADMIN")
                .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Helper lấy actor ở phần trước minh họa Servlet stack, nơi SecurityContext thường gắn với thread xử lý request. Với WebFlux, lấy Authentication từ reactive security context trong Reactor chain; không dựa vào SecurityContextHolder dạng ThreadLocal khi code chạy reactive.

Đây là ví dụ chính sách cho Servlet management endpoints. Import của `EndpointRequest` thay đổi package giữa các thế hệ Spring Boot; hãy dùng package phù hợp với BOM của ứng dụng. Nếu dùng WebFlux, cấu hình bằng reactive security chain tương ứng.

Với browser session, xem xét CSRF protection cho thao tác POST. Với machine-to-machine management API, dùng credential ngắn hạn/được quản lý, TLS và network restriction; không tắt CSRF một cách rộng rãi chỉ để làm endpoint POST hoạt động.

### 12.4. Tách management network

Nếu kiến trúc cho phép:
- Dùng management port riêng.
- Chỉ cho phép mạng quản trị hoặc control plane truy cập.
- Không route actuator write endpoint qua public ingress.
- Dùng firewall/network policy để giới hạn nguồn.
- Bảo vệ cả JMX nếu endpoint được expose qua JMX.
- Kiểm tra reverse proxy không vô tình chuyển tiếp endpoint nội bộ.

## 13. Truy vấn audit events

### 13.1. Query endpoint

Khi có repository bean và endpoint đã được expose, có thể truy vấn:

~~~bash
curl --request GET \
  "http://localhost:8080/actuator/auditevents?principal=user%3Aalice&type=ADMIN_CONFIG_REFRESH_SUCCEEDED"
~~~

Endpoint hỗ trợ các bộ lọc principal, after và type. Ví dụ truy vấn event sau một thời điểm UTC:

~~~text
GET /actuator/auditevents?after=2026-11-18T12:00:00Z&type=ADMIN_SERVICE_STATUS_CHANGED
~~~

Response có danh sách event với timestamp, principal, type và data. Hình dạng chi tiết phụ thuộc Spring Boot version và schema event đã ghi.

### 13.2. Query qua repository

Nếu service điều tra được phép dùng repository trực tiếp:

~~~java
List<AuditEvent> events = auditEventRepository.find(
        "user:alice",
        Instant.parse("2026-11-18T12:00:00Z"),
        "ADMIN_CONFIG_REFRESH_SUCCEEDED"
);
~~~

Hạn chế số lượng kết quả và phân trang ở lớp storage nếu kho có nhiều record. Không tải toàn bộ audit history vào bộ nhớ cho mỗi truy vấn.

### 13.3. Kiểm soát việc đọc và export

Đọc audit data cũng là một hành động nhạy cảm. Cân nhắc audit:
- Ai đã truy vấn audit events.
- Ai đã export một khoảng thời gian.
- Ai đã tải dữ liệu ra ngoài hệ thống.
- Lý do hoặc ticket incident liên quan nếu quy trình yêu cầu.

Không tạo vòng lặp vô hạn bằng cách audit mỗi lần đọc event vào chính cùng một query stream; tách audit access log hoặc dùng pipeline phù hợp.

## 14. Kiểm thử audit trail

### 14.1. Kiểm thử event thành công

Khi thao tác refresh thành công, xác minh:
- Event REQUESTED được ghi.
- Event SUCCEEDED được ghi.
- Principal đúng với Authentication.
- Resource/application đúng.
- Request ID nối được hai event.
- Không có config value hoặc credential trong data.

### 14.2. Kiểm thử thất bại

Mô phỏng refresh/registry provider ném exception. Xác minh event FAILED có reason code đã chuẩn hóa. Không assert hoặc persist raw exception message nếu message có thể chứa URL, token hoặc property value.

### 14.3. Kiểm thử denied action

Gửi request với principal không có quyền quản trị. Xác minh:
- Security trả 401/403 theo authentication state.
- Có audit event từ chối quyền nếu listener/repository đã được cấu hình.
- Không có event SUCCEEDED.
- Không có operation side effect.

### 14.4. Kiểm thử secret không xuất hiện

Dùng một sentinel value giả lập secret trong test:

~~~java
@Test
void auditEventDoesNotContainSecretValue() {
    String secretSentinel = "TEST-ONLY-SECRET-DO-NOT-STORE";

    adminService.updateConfiguration(
            "user:alice",
            "orders-service",
            secretSentinel
    );

    AuditEvent event = recordingRepository.lastEvent();

    assertThat(event.getData())
            .doesNotContainKey("password")
            .doesNotContainKey("token")
            .doesNotContainKey("secret")
            .doesNotContainValue(secretSentinel);
}
~~~

Nếu có nhiều event, kiểm tra toàn bộ record đã ghi và serialized output. Cũng tìm sentinel trong application logs, HTTP access logs và trace attributes của test run.

### 14.5. Kiểm thử repository và endpoint

| Test | Điều cần xác minh |
| --- | --- |
| Repository add/find | Ghi và truy vấn được theo principal, after, type. |
| Repository restart | Record vẫn tồn tại sau khi process khởi động lại. |
| Endpoint exposure | `/actuator/auditevents` chỉ truy cập khi được expose. |
| Endpoint authorization | Audit reader đọc được; user thường bị từ chối. |
| Admin write authorization | Chỉ role quản trị phù hợp mới gọi POST. |
| Refresh success/failure | Có request và outcome event. |
| Registry status change | Ghi trạng thái mới và instance mục tiêu, không serialize Registration. |
| Bus refresh | Ghi dispatch và kết quả applied theo command ID. |
| Secret redaction | Sentinel không xuất hiện trong audit, log, trace hoặc response ngoài ý muốn. |
| Audit store unavailable | Hành vi fail-closed/fail-open đúng policy. |

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `/actuator/auditevents` trả 404. | Thiếu AuditEventRepository hoặc endpoint chưa expose. | Tạo repository bean và thêm `auditevents` vào exposure list. |
| Có endpoint nhưng không có event. | Security audit listener chưa được kích hoạt hoặc custom event chưa được publish. | Kiểm tra Spring Security publisher, repository và event publisher. |
| Chỉ có authentication event, không có admin action. | Ứng dụng chưa phát event cho refresh/env/registry operation. | Instrument operation service hoặc management boundary. |
| Audit record mất sau restart. | Dùng InMemoryAuditEventRepository. | Chuyển sang repository bền vững trong production. |
| Principal là anonymous. | Request không có Authentication hợp lệ hoặc lấy actor từ sai context. | Kiểm tra authentication chain và service account identity. |
| Event có raw token hoặc password. | Developer truyền raw request/authentication/config object vào data map. | Dùng allowlist schema, loại bỏ field và kiểm thử sentinel. |
| Event FAILED không rõ nguyên nhân. | Chỉ ghi outcome nhưng không có reason code an toàn. | Ánh xạ exception sang mã lỗi đã chuẩn hóa. |
| Exception message làm lộ secret. | Lưu raw message/stack trace trong audit data. | Chỉ ghi exception class đã cho phép và reason code. |
| Refresh thành công nhưng audit chỉ có REQUESTED. | Process dừng trước khi ghi completion hoặc lỗi repository. | Dùng durable event/outbox, retry và reconciliation. |
| Bus refresh dispatch thành công nhưng instance chưa cập nhật. | Nhầm accepted/dispatched với applied. | Ghi event theo từng phase và correlation ID. |
| Không truy vấn được event cũ. | Repository chỉ lưu bộ nhớ, retention quá ngắn hoặc query không đúng UTC/type. | Kiểm tra storage, retention và bộ lọc. |
| Audit endpoint lộ dữ liệu cho user thường. | Thiếu authorization hoặc management port public. | Giới hạn role, network và exposure. |
| Audit event bị trùng. | Retry tạo nhiều request/event mà không có idempotency key. | Dùng event ID và command ID để phân biệt/deduplicate đúng. |
| Không biết ai đã thực hiện automation. | Ghi actor chung là system. | Dùng client ID/service account riêng cho từng automation. |
| Audit record có IP giả mạo. | Tin trực tiếp X-Forwarded-For từ client. | Chỉ dùng forwarded header từ trusted proxy đã cấu hình. |
| Log/trace vẫn chứa secret dù audit đã sạch. | Redaction chỉ áp dụng cho audit publisher. | Áp dụng chính sách redaction cho access log, tracing và exception logging. |

## 16. Nguyên tắc vận hành

1. **Ghi actor có thể xác minh.** Dùng principal hoặc service account đã xác thực.
2. **Tách request và outcome.** Không coi yêu cầu được nhận là thao tác đã hoàn tất.
3. **Dùng schema ổn định.** Chuẩn hóa event type, action, resource và outcome.
4. **Chỉ lưu allowlist.** Không serialize request, Authentication, Environment hoặc Registration object.
5. **Không lưu secret ở dạng mã hóa.** Ciphertext vẫn là dữ liệu nhạy cảm.
6. **Ghi reason code an toàn.** Tránh exception message và raw stack trace trong audit record.
7. **Dùng repository bền vững.** In-memory chỉ dùng cho development/test.
8. **Append-only và phân quyền riêng.** Ứng dụng nghiệp vụ không được sửa/xóa lịch sử audit.
9. **Nối event đa instance.** Dùng request ID, command ID hoặc trace ID.
10. **Phân biệt dispatch và applied.** Đặc biệt với Spring Cloud Bus.
11. **Bảo vệ audit endpoint.** Chỉ cấp quyền đọc cho vai trò cần thiết.
12. **Bảo vệ management write endpoint.** Dùng RBAC, TLS, management network và policy phù hợp.
13. **Kiểm thử redaction.** Dùng sentinel secret và tìm trong mọi kênh ghi log.
14. **Đặt retention có chủ đích.** Giữ đủ lâu để điều tra nhưng tuân thủ privacy.
15. **Định nghĩa behavior khi audit store lỗi.** Chọn fail-closed hoặc fail-open theo mức độ rủi ro.
16. **Đối chiếu version.** API package và cấu hình Actuator/Security có thể thay đổi theo Spring Boot/Spring Security release.

## 17. Checklist hoàn thành

- [ ] Giải thích được audit trail khác application log, trace và metric.
- [ ] Xác định được thao tác quản trị cần audit trong Spring Cloud.
- [ ] Thiết kế schema event có event ID, timestamp, principal, type, resource, outcome và request ID.
- [ ] Ghi riêng requested, denied, succeeded và failed.
- [ ] Dùng AuditEventRepository và AuditApplicationEvent.
- [ ] Hiểu InMemoryAuditEventRepository chỉ phù hợp development/test.
- [ ] Có repository production lưu trữ bền vững.
- [ ] Ghi security event xác thực và từ chối quyền.
- [ ] Tạo custom event cho refresh, env, service registry và bus operations.
- [ ] Chỉ ghi property key hoặc change-set đã được allowlist.
- [ ] Không ghi token, password, cookie, private key hoặc raw configuration value.
- [ ] Không ghi raw request body, Authorization header, query string hoặc exception message.
- [ ] Bảo vệ /actuator/auditevents bằng role riêng.
- [ ] Bảo vệ management write endpoints bằng least privilege và network restriction.
- [ ] Có chính sách retention, append-only, backup và integrity.
- [ ] Có correlation ID cho thao tác phân tán.
- [ ] Kiểm thử success, failure, denied, persistence và secret redaction.
- [ ] Xác định hành vi khi audit store unavailable.

**Tài liệu chính thức cần đối chiếu theo phiên bản dự án:**

- [Spring Boot – Auditing](https://docs.spring.io/spring-boot/reference/actuator/auditing.html): AuditEventRepository, InMemoryAuditEventRepository, security audit listeners và custom AuditApplicationEvent.
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint auditevents, exposure, access control và bảo vệ management endpoints.
- [Spring Boot – AuditEvent API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/audit/AuditEvent.html): principal, timestamp, type và data.
- [Spring Boot – AuditEventRepository API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/audit/AuditEventRepository.html): hợp đồng add/find.
- [Spring Boot – AuditApplicationEvent API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/audit/listener/AuditApplicationEvent.html): publish audit event qua ApplicationEventPublisher.
- [Spring Security – Authentication Events](https://docs.spring.io/spring-security/reference/servlet/authentication/events.html): AuthenticationSuccessEvent, AuthenticationFailureEvent và AuthenticationEventPublisher.
- [Spring Security – Authorization Events](https://docs.spring.io/spring-security/reference/servlet/authorization/events.html): AuthorizationDeniedEvent và cách phát authorization events.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): ServiceRegistry, auto-registration và serviceregistry Actuator endpoint.
- [Spring Cloud Context – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): refresh, env, restart và các management endpoint.
- [Spring Cloud Bus – Bus Endpoints](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/bus-endpoints.html): busrefresh và busenv.

Audit trail chỉ đáng tin khi event phản ánh đúng thao tác, dữ liệu đã được lọc trước khi lưu và kho audit được bảo vệ độc lập. Hãy thử các thao tác quản trị trong môi trường kiểm thử, xác minh cả request lẫn kết quả trên nhiều instance và chứng minh bằng test rằng secret sentinel không xuất hiện trong bất kỳ audit record nào.
