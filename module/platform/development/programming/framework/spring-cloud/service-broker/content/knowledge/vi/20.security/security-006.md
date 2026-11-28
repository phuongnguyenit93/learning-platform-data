# Phân quyền theo nền tảng, khách hàng, dịch vụ và tài nguyên

Một service broker có thể nhận request từ nhiều nền tảng, phục vụ nhiều khách hàng và quản lý nhiều loại service instance. Xác thực thành công một platform chỉ chứng minh request đến từ một caller được broker tin cậy; điều đó chưa đủ để cho phép caller thao tác trên mọi tenant, mọi service hoặc mọi tài nguyên. Broker cần kiểm tra quyền ở nhiều lớp: nền tảng nào đang gọi, tenant nào sở hữu scope, service/plan nào được phép sử dụng và instance hoặc binding cụ thể có nằm trong phạm vi của request hay không.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, phân quyền cần bao phủ toàn bộ vòng đời Open Service Broker API (OSB API): catalog, provision, update, bind, unbind, deprovision và truy vấn last operation. Mô hình phù hợp thường kết hợp role-based access control (RBAC), attribute-based access control (ABAC) và quan hệ ownership giữa các đối tượng. Spring Security bảo vệ HTTP boundary; domain authorization service quyết định quyền trên resource đã được phân giải; repository và database tiếp tục giới hạn dữ liệu theo platform cùng tenant.

## 1. Xác thực và phân quyền là hai quyết định khác nhau

**Authentication** trả lời caller là ai và thông tin xác thực có hợp lệ không. **Authorization** trả lời caller đó có được phép thực hiện hành động cụ thể trên đối tượng cụ thể trong ngữ cảnh hiện tại không.

Ví dụ, broker nhận request:

~~~http
DELETE /v2/service_instances/orders-db-prod?service_id=svc-postgresql&plan_id=plan-production
Authorization: Bearer <platform-token>
~~~

Token hợp lệ có thể xác định request đến từ Cloud Foundry foundation **cf-prod-a**. Tuy nhiên, broker vẫn cần xác định:

- Foundation này được đăng ký và đang active hay không.
- Request thuộc organization/space hoặc tenant nào.
- Instance **orders-db-prod** có được tạo dưới platform scope đó không.
- Service và plan trong query có khớp với instance đã lưu không.
- Platform có quyền deprovision instance ở trạng thái hiện tại không.
- Có policy nào cấm xóa do legal hold, retention hoặc trạng thái vận hành không.

Nếu chỉ kiểm tra token rồi cho phép mọi thao tác, một platform credential bị lộ có thể trở thành quyền truy cập toàn bộ dữ liệu broker.

Một nguyên tắc quan trọng: **xác thực caller trước, phân giải scope từ nguồn tin cậy, rồi mới quyết định quyền trên resource**. Không dùng instance ID, tenant ID hoặc field context do caller gửi làm bằng chứng ownership.

## 2. Bốn lớp phân quyền

Broker nên tách ít nhất bốn lớp quyền để tránh gom mọi quyết định vào một role chung.

| Lớp | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Platform | Platform registration nào được gọi broker và được dùng capability nào? | cf-prod-a được gọi provision và binding |
| Tenant/customer | Tenant nào được phép sử dụng broker và các service? | tenant-commerce có entitlement PostgreSQL |
| Service/plan | Tenant được dùng service, plan, region và capability nào? | Được dùng plan Standard, không được dùng plan Enterprise |
| Resource | Caller có được thao tác trên instance/binding/operation cụ thể không? | Chỉ deprovision instance thuộc tenant và platform scope đã xác minh |

Các lớp này có quan hệ bao hàm. Quyền ở lớp ngoài không tự động cấp mọi quyền ở lớp trong. Platform có thể được phép gọi endpoint bind nhưng một request cụ thể vẫn bị từ chối vì tenant không có entitlement hoặc instance không thuộc tenant đó.

Ví dụ: platform **cf-prod-a** được phép provision PostgreSQL cho tenant **tenant-commerce**; tenant đó chỉ được dùng plan **standard**; instance **orders-db-prod** thuộc tenant này; request bind của một application consumer chỉ được chấp nhận nếu consumer nằm trong scope được phép. Mỗi quyết định cần kiểm tra đúng lớp liên quan.

## 3. Mô hình principal và authorization context

Trong Spring Security, request sau khi xác thực thường có một Authentication đại diện cho caller. Broker nên chuyển principal đó thành một context nội bộ đã chuẩn hóa, thay vì để domain service đọc trực tiếp header hoặc JWT claim ở nhiều nơi.

Một mô hình minh họa:

~~~java
public record BrokerPrincipal(
    String subject,
    String clientId,
    String platformRegistrationId,
    Set<String> authorities
) {}

public record AuthorizationContext(
    BrokerPrincipal principal,
    UUID platformId,
    UUID tenantId,
    UUID platformScopeId,
    String correlationId
) {}
~~~

BrokerPrincipal biểu diễn danh tính đã xác thực. AuthorizationContext chứa platform, tenant và scope đã được resolver kiểm tra. Tenant ID và platform scope ID phải được lấy từ registration/mapping đáng tin cậy; không sao chép trực tiếp giá trị caller tự khai vào context.

Một request context có thể được tạo theo trình tự:

1. Spring Security xác thực token, client certificate hoặc credential platform.
2. Authentication converter tạo principal có platform registration reference.
3. Platform resolver kiểm tra registration active và xác định platform ID.
4. Context resolver đọc metadata platform được phép sử dụng.
5. Tenant resolver ánh xạ external organization/space/project/namespace sang tenant nội bộ.
6. Domain service nhận context bất biến để kiểm tra quyền và tra cứu resource.

Không nên đặt tenant context vào ThreadLocal thủ công trong reactive WebFlux rồi giả định nó tồn tại xuyên suốt mọi callback. Với reactive stack, dùng Reactor Context hoặc truyền AuthorizationContext rõ ràng qua command/service boundary. Với imperative stack, có thể dùng request-scoped context nếu lifecycle được kiểm soát và luôn được dọn đúng cách.

## 4. Nguồn tin cậy cho platform và tenant

OSB API có thể mang theo context, bind resource hoặc parameters, nhưng những field này không đồng nghĩa với một danh tính đã xác thực.

Ví dụ request context:

~~~json
{
  "context": {
    "platform": "cloudfoundry",
    "organization_guid": "org-123",
    "space_guid": "space-456"
  },
  "bind_resource": {
    "app_guid": "app-orders-api"
  }
}
~~~

Broker có thể dùng organization GUID, space GUID và app GUID để xác định scope hoặc consumer, nhưng phải kiểm tra chúng trong quan hệ với platform principal. Không cho caller tùy ý gửi tenant_id=tenant-admin rồi sử dụng giá trị đó làm ownership.

### Cloud Foundry

Platform registration xác định foundation. Broker ánh xạ organization/space GUID trong phạm vi foundation đó sang tenant nội bộ. Nếu cùng một organization GUID xuất hiện ở foundation khác, hai scope vẫn độc lập.

### Kubernetes

Cluster identity phải được xác định từ registration hoặc credential của adapter. Namespace name đơn lẻ không đủ để phân biệt nhiều cluster; namespace UID và cluster registration giúp tránh việc namespace mới cùng tên kế thừa quyền của namespace cũ.

### Tích hợp qua adapter

Nếu một controller hoặc gateway gọi broker thay mặt workload, broker cần xác định adapter có được quyền khẳng định consumer identity hay không. Nếu gateway chỉ chuyển tiếp một header không ký hoặc không xác thực, header đó không phải bằng chứng tin cậy. Có thể dùng workload identity, signed assertion, mTLS hoặc API riêng để xác minh consumer tùy kiến trúc.

## 5. RBAC: quyền theo vai trò

RBAC gán quyền cho role, sau đó gán role cho principal hoặc nhóm. Đây là cách thuận tiện để quản lý quyền vận hành và quản trị.

Ví dụ role nội bộ:

| Role | Quyền điển hình |
|---|---|
| PLATFORM_CLIENT | Gọi các endpoint OSB trong platform registration được cấp |
| TENANT_OPERATOR | Xem và quản lý tài nguyên thuộc tenant trong phạm vi được giao |
| SERVICE_OPERATOR | Vận hành service/plan cụ thể |
| BROKER_SUPPORT | Đọc trạng thái và chẩn đoán có kiểm soát |
| BROKER_ADMIN | Quản lý registration, entitlement và policy |
| SECURITY_AUDITOR | Đọc audit/security event theo quyền chỉ đọc |

Role không nên tự chứa mọi điều kiện về tenant hoặc resource. TENANT_OPERATOR không có nghĩa được thao tác trên tất cả tenant; role cần được gắn với một tenant scope cụ thể. Tương tự, SERVICE_OPERATOR có thể chỉ quản lý PostgreSQL chứ không có quyền trên Redis.

Có thể biểu diễn assignment:

| Principal | Role | Scope |
|---|---|---|
| client-cf-prod-a | PLATFORM_CLIENT | platform cf-prod-a |
| user-ops-17 | TENANT_OPERATOR | tenant tenant-commerce |
| team-database | SERVICE_OPERATOR | service svc-postgresql, tenant tenant-commerce |
| audit-user-4 | SECURITY_AUDITOR | toàn broker, read-only |

Không gán role quản trị toàn cục cho platform client chỉ để request OSB hoạt động. Platform client có thể được phép gọi một nhóm endpoint trong platform registration của nó mà không có quyền đọc dữ liệu quản trị hoặc thay đổi entitlement.

## 6. ABAC: quyền theo thuộc tính và policy

ABAC đánh giá các thuộc tính của principal, resource, action và environment. Nó phù hợp khi broker cần điều kiện chi tiết hơn role.

Một quyết định có thể xét:

- Principal: platform ID, client ID, authorities, authentication method.
- Resource: tenant ID, service ID, plan ID, instance state, sensitivity.
- Action: provision, update, bind, unbind, deprovision, retrieve.
- Environment: region, maintenance window, risk flag, request origin, policy version.

Ví dụ policy:

~~~text
ALLOW provision WHEN
  platform.status == ACTIVE
  AND tenant.status == ACTIVE
  AND tenant.entitlement CONTAINS requested.service_id
  AND requested.plan_id IN tenant.allowed_plans
  AND requested.region IN tenant.allowed_regions
  AND quota.available >= requested.capacity
~~~

Ví dụ policy cho deprovision:

~~~text
ALLOW deprovision WHEN
  principal.platform_id == instance.platform_id
  AND resolved.tenant_id == instance.tenant_id
  AND requested.service_id == instance.service_id
  AND requested.plan_id == instance.plan_id
  AND instance.lifecycle_state IN allowed_delete_states
  AND NOT instance.legal_hold
~~~

Các biểu thức trên là pseudocode mô tả logic, không phải ngôn ngữ policy có sẵn của Spring Security. Có thể triển khai bằng Java policy service, Spring AuthorizationManager hoặc một policy engine riêng nếu độ phức tạp và yêu cầu quản trị biện minh cho nó.

## 7. Relationship-based access: quyền dựa trên quan hệ ownership

Một số quyết định được diễn đạt tự nhiên hơn bằng quan hệ giữa các đối tượng:

- Platform registration owns platform scope.
- Platform scope maps to tenant.
- Tenant owns service instance.
- Service instance has service binding.
- Binding belongs to consumer.
- Operation targets instance hoặc binding.

Ví dụ:

~~~mermaid
flowchart TD
    P["Authenticated Platform"] -->|registered scope| S["Platform Scope"]
    S -->|mapped to| T["Tenant"]
    T -->|owns| I["Service Instance"]
    I -->|contains| B["Service Binding"]
    B -->|granted to| C["Consumer"]
    I --> O["Lifecycle Operation"]
~~~

Khi xử lý DELETE binding, broker phải xác minh binding thuộc đúng instance, instance thuộc tenant được resolve và tenant thuộc platform scope đang gọi. Không chỉ tìm binding theo binding_id rồi xóa.

Relationship check cũng giúp xử lý các trường hợp chia sẻ tài nguyên. Nếu tenant A cho tenant B dùng một instance, cần có một quan hệ share/grant được lưu rõ ràng, gồm phạm vi quyền, thời hạn và bên cấp quyền. Không tự suy ra quyền chia sẻ chỉ vì consumer ID tồn tại trong request.

## 8. Ma trận quyền theo endpoint OSB

Một ma trận giúp xác định quyền tối thiểu cần có cho từng thao tác:

| Endpoint/action | Platform permission | Tenant/service checks | Resource checks |
|---|---|---|---|
| GET /v2/catalog | Được phép đọc catalog của broker | Có thể lọc catalog theo entitlement nếu thiết kế hỗ trợ | Không đọc instance |
| PUT service_instances/{id} | PROVISION | Tenant active, service/plan được phép, quota/region hợp lệ | ID chưa được dùng trong scope hoặc retry cùng fingerprint |
| PATCH service_instances/{id} | UPDATE | Tenant còn entitlement cho thay đổi | Instance thuộc scope, state cho phép update |
| DELETE service_instances/{id} | DEPROVISION | Tenant và service policy cho phép thu hồi | Ownership, service/plan khớp, binding/operation policy |
| PUT service_bindings/{binding} | BIND | Service bindable, tenant có quyền | Instance active, consumer hợp lệ, binding thuộc instance |
| DELETE service_bindings/{binding} | UNBIND | Tenant vẫn có thể thu hồi binding | Binding đúng instance và ownership |
| GET last_operation | READ_OPERATION | Platform/tenant scope hợp lệ | Operation thuộc resource được truy vấn |

Tên permission trong bảng là quyền nội bộ minh họa. OSB API quy định endpoint và response contract, không bắt buộc dùng các tên role/permission này.

### Catalog có cần phân quyền không?

Catalog thường được platform đọc để biết service và plan mà broker công bố. Nếu catalog giống nhau cho mọi platform, có thể cấp quyền đọc catalog cho platform client đã xác thực. Nếu broker có entitlement khác nhau theo tenant hoặc platform, có thể lọc catalog hoặc plan theo policy, nhưng cần bảo đảm các thao tác provision vẫn kiểm tra lại quyền ở server.

Không dùng việc ẩn một plan khỏi catalog làm lớp bảo mật duy nhất. Caller có thể gửi trực tiếp service_id và plan_id; broker phải xác minh entitlement khi provision và update.

## 9. Kiểm tra service và plan entitlement

Entitlement xác định tenant được phép dùng service hoặc plan nào. Nó có thể dựa trên hợp đồng thương mại, license, subscription, quota hoặc policy vận hành.

Ví dụ model:

~~~java
public record ServiceEntitlement(
    UUID tenantId,
    String serviceId,
    Set<String> allowedPlanIds,
    Set<String> allowedRegions,
    int maximumInstances,
    boolean bindingAllowed,
    Instant validUntil
) {}
~~~

Trước khi provision:

1. Xác minh tenant active.
2. Tải entitlement cho service ID.
3. Kiểm tra plan ID nằm trong danh sách được phép.
4. Kiểm tra entitlement chưa hết hạn hoặc bị thu hồi.
5. Kiểm tra region/provider target.
6. Reserve quota nếu cần để tránh hai request đồng thời cùng vượt giới hạn.
7. Ghi entitlement/policy version dùng cho quyết định.

Entitlement cần được kiểm tra lại ở update nếu thao tác làm tăng năng lực hoặc thay plan. Khi deprovision, tenant có thể đã hết entitlement nhưng broker vẫn phải cho phép thu hồi tài nguyên và quyền truy cập. Không để việc subscription hết hạn khiến tài nguyên không thể được dọn dẹp.

## 10. Authorization theo lifecycle state

Quyền trên một resource có thể phụ thuộc trạng thái hiện tại. Một principal có quyền update instance không có nghĩa được update khi instance đang deprovisioning.

Ví dụ policy theo trạng thái:

| State | Retrieve | Bind | Update | Deprovision |
|---|---|---|---|---|
| PROVISIONING | Theo policy | Thường từ chối | Từ chối hoặc serialize | Theo chính sách hủy/cleanup |
| ACTIVE | Cho phép trong scope | Cho phép nếu bindable | Cho phép nếu entitlement | Cho phép nếu policy |
| UPDATING | Đọc trạng thái | Tùy policy | Không chạy operation xung đột | Serialize hoặc từ chối tạm thời |
| DEPROVISIONING | Đọc trạng thái cần thiết | Từ chối | Từ chối | Replay operation hiện tại |
| DEPROVISIONED | Theo retention/tombstone | Từ chối | Từ chối | Idempotent theo contract |
| FAILED | Đọc/diagnose | Theo trạng thái và policy | Chỉ khi recovery được phép | Có thể cho phép cleanup |

Bảng là policy tham khảo; broker cần xác định state transition cụ thể theo backend và OSB API version. Không dùng một boolean authorized=true đã tính từ đầu request rồi bỏ qua thay đổi state trong lúc operation chạy.

Với thao tác phá hủy, cần kiểm tra thêm legal hold, retention, approval hoặc policy bảo vệ dữ liệu nếu hệ thống có các ràng buộc đó. Các ngoại lệ này phải được lưu và audit.

## 11. Spring Security ở HTTP boundary

Spring Security bảo vệ endpoint OSB bằng authentication mechanism phù hợp với platform. Ví dụ cấu hình tổng quát cho WebFlux:

~~~java
@Configuration
@EnableWebFluxSecurity
public class BrokerSecurityConfiguration {

    @Bean
    SecurityWebFilterChain brokerSecurity(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/v2/catalog")
                    .hasAuthority("BROKER_CATALOG_READ")
                .pathMatchers("/v2/service_instances/**")
                    .hasAuthority("BROKER_OSB_CLIENT")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt())
            .build();
    }
}
~~~

Đây là cấu hình minh họa cho resource server dùng JWT. Cách xác thực thực tế có thể là OAuth2, mTLS hoặc cơ chế credential mà platform hỗ trợ. Các authority trong ví dụ là authority sau khi converter/authorization layer đã chuẩn hóa.

Một số lưu ý:

- Cấu hình phải áp dụng cho đúng WebFlux hoặc Servlet stack của ứng dụng.
- Không bật cả hai security stack chỉ để dùng chung một ví dụ.
- Không để endpoint OSB nhạy cảm rơi vào permitAll.
- Kiểm tra issuer, audience, expiry, signature và key rotation nếu dùng JWT.
- Với mTLS, ánh xạ certificate identity vào platform registration và kiểm tra trạng thái thu hồi.
- Không tin header X-Platform-Id nếu nó có thể bị client tự đặt.
- Catalog và các endpoint health/metrics cần policy riêng, không dùng chung quyền quản trị.

hasAuthority("BROKER_OSB_CLIENT") chỉ là bước bảo vệ endpoint. Nó không thay thế kiểm tra tenant, service, plan và resource trong domain service.

## 12. Domain authorization service

Một policy service tập trung giúp các handler provision, bind, unbind, update và deprovision áp dụng cùng quy tắc.

Ví dụ:

~~~java
public interface BrokerAuthorizationService {
    Mono<Void> assertCanProvision(
        AuthorizationContext context,
        String serviceId,
        String planId,
        String region
    );

    Mono<Void> assertCanAccessInstance(
        AuthorizationContext context,
        ServiceInstance instance,
        BrokerAction action
    );

    Mono<Void> assertCanAccessBinding(
        AuthorizationContext context,
        ServiceInstance instance,
        ServiceBinding binding,
        BrokerAction action
    );
}
~~~

Một implementation có thể kết hợp role, tenant mapping và ownership:

~~~java
public Mono<Void> assertCanAccessInstance(
        AuthorizationContext context,
        ServiceInstance instance,
        BrokerAction action) {

    if (!instance.platformId().equals(context.platformId())) {
        return Mono.error(new ResourceNotFoundException());
    }

    if (!instance.tenantId().equals(context.tenantId())) {
        return Mono.error(new ResourceNotFoundException());
    }

    if (!actionPolicy.isAllowed(
            context.principal().authorities(),
            action,
            instance.serviceId(),
            instance.lifecycleState())) {
        return Mono.error(new AccessDeniedException(
            "Action is not permitted"
        ));
    }

    return Mono.empty();
}
~~~

Đây là pseudocode kiến trúc; exception mapping và repository model cần điều chỉnh theo ứng dụng. Trong một số trường hợp, trả cùng một lỗi not-found cho resource ngoài scope giúp tránh tiết lộ sự tồn tại của tài nguyên tenant khác. Với resource đã xác định thuộc caller nhưng hành động bị cấm, có thể dùng lỗi access-denied phù hợp contract. Hãy thống nhất cách ánh xạ trong broker và không tiết lộ dữ liệu nhạy cảm qua thông báo lỗi.

### Không chỉ kiểm tra ở controller

Nếu authorization chỉ nằm trong controller hoặc event flow HTTP, worker nền và tác vụ nội bộ có thể bỏ qua nó. Domain service nên yêu cầu context hoặc một authorization decision đã được tạo từ nguồn tin cậy. Với worker, dùng service identity và quyền hẹp được lưu/ủy quyền cho operation cụ thể.

## 13. Repository lookup phải có scope

Authorization sau khi tải resource vẫn cần được kết hợp với truy vấn có scope. Không tìm theo ID toàn cục rồi trả entity cho mọi caller.

Ví dụ Spring Data:

~~~java
public interface ServiceInstanceRepository
        extends ReactiveCrudRepository<ServiceInstance, UUID> {

    Mono<ServiceInstance>
    findByPlatformIdAndTenantIdAndExternalInstanceId(
        UUID platformId,
        UUID tenantId,
        String externalInstanceId
    );
}
~~~

Nếu contract đảm bảo instance ID duy nhất trong platform, có thể dùng platform ID và instance ID làm composite lookup rồi xác minh tenant với record đã lưu. Repository method phải phản ánh đúng unique key đã thiết kế.

Khi truy vấn binding, nên giới hạn cả parent instance:

~~~java
Mono<ServiceBinding> findByInternalInstanceIdAndExternalBindingId(
    UUID internalInstanceId,
    String externalBindingId
);
~~~

Tránh các method như findById(externalInstanceId) nếu external ID không phải primary key và không có phạm vi rõ ràng. Unique constraint trong database là lớp bảo vệ cuối cùng trước request đồng thời; kiểm tra bằng Java trước insert không đủ.

## 14. Bảo vệ thao tác binding và consumer identity

Binding tạo credential hoặc quyền truy cập cho consumer. Đây là thao tác cần kiểm tra cả instance ownership và consumer authorization.

Trước khi bind:

- Service definition có bindable=true.
- Instance thuộc platform/tenant scope đã xác minh.
- Instance ở trạng thái cho phép bind.
- Service ID và plan ID khớp metadata instance.
- Consumer identity được xác minh theo platform adapter.
- Tenant còn entitlement và quota binding.
- Parameters nằm trong allowlist và không thể nâng quyền ngoài policy.
- Binding ID chưa tồn tại với request mâu thuẫn.

Không dùng app_guid, workload name hoặc namespace từ request làm chứng cứ duy nhất rằng consumer thuộc tenant. Adapter phải xác minh consumer qua platform API, signed context hoặc mapping đã đăng ký.

Khi unbind, quyền cần thu hồi là quyền của binding được chỉ định. Không thu hồi credential dùng chung nếu binding khác vẫn phụ thuộc. Khi deprovision instance, broker phải áp dụng policy đối với toàn bộ binding còn tồn tại và không bỏ sót credential đang hiệu lực.

## 15. Quyền của worker và service-to-service identity

Provision hoặc deprovision bất đồng bộ có thể tiếp tục sau khi HTTP request kết thúc. Worker không có user session của request và không nên chạy bằng quyền admin toàn cục.

Khi tạo operation, broker lưu các thông tin cần thiết:

- Internal instance/binding ID.
- Platform ID và tenant ID đã xác minh.
- Operation type và operation ID.
- Resource specification hoặc fingerprint cần cho tác vụ.
- Policy/entitlement version dùng cho quyết định.
- Service identity hoặc execution scope được phép chạy operation.

Worker lấy operation từ state store, xác minh state hiện tại và chỉ thực thi đúng target đã lưu. Không nhận tenant ID, backend resource ID hoặc quyền mới từ message payload mà không đối chiếu database.

Có thể dùng service account riêng cho provider adapter. Ví dụ worker provision chỉ có quyền tạo và đọc loại resource cần thiết; worker deprovision có quyền xóa trong account/region được chỉ định. Credential của provider nên được cấp theo workload identity hoặc secret manager, có rotation và audit.

Nếu policy yêu cầu kiểm tra entitlement lại khi worker bắt đầu, phải định nghĩa rõ thời điểm quyết định: quyền được đánh giá tại lúc nhận request, lúc worker chạy hay cả hai. Không để một entitlement thay đổi giữa chừng làm worker tự mở rộng phạm vi thao tác. Với deprovision, thường cần duy trì quyền cleanup để tránh tài nguyên bị bỏ lại, kể cả khi subscription đã hết hạn.

## 16. Deny by default và phân biệt lỗi

Một quyết định authorization không rõ ràng phải mặc định từ chối. Không coi thiếu policy, lỗi đọc entitlement hoặc timeout policy engine là cho phép.

| Tình huống | Quyết định |
|---|---|
| Principal chưa xác thực | Từ chối tại security filter |
| Platform registration bị suspend | Từ chối request |
| Không phân giải được tenant scope | Từ chối; không tự tạo mapping |
| Tenant không có entitlement | Từ chối service/plan operation |
| Service/plan không thuộc catalog hoặc không khớp instance | Từ chối request |
| Resource ngoài platform/tenant scope | Từ chối và tránh tiết lộ sự tồn tại |
| Action không có trong permission set | Từ chối |
| Policy service không khả dụng | Fail closed với lỗi vận hành phù hợp |
| Worker operation không còn hợp lệ | Dừng và ghi trạng thái cần reconciliation |
| Admin break-glass | Chỉ cho phép qua luồng riêng, thời hạn ngắn và audit đầy đủ |

HTTP status và error body phải được ánh xạ theo OSB API version cùng exception handler của broker. Không trả stack trace, token, tenant mapping nội bộ hoặc backend credential cho platform.

Phân biệt lỗi xác thực, lỗi phân quyền, lỗi request và resource không tồn tại giúp vận hành dễ chẩn đoán. Tuy nhiên, với resource ngoài scope, có thể chủ động dùng phản hồi không tiết lộ tồn tại để hạn chế ID enumeration. Quyết định này cần nhất quán trên các endpoint.

## 17. Cache policy và thu hồi quyền

Authorization decision có thể được cache để giảm tải, nhưng cache stale có thể giữ quyền sau khi tenant bị suspend hoặc entitlement bị thu hồi.

Nếu cache, key cần chứa đầy đủ scope:

~~~text
authz:{principal_id}:{platform_id}:{tenant_id}:{resource_id}:{action}:{policy_version}
~~~

Cần xác định:

- TTL ngắn phù hợp với mức rủi ro.
- Invalidation khi platform/tenant/entitlement bị suspend.
- Policy version để loại bỏ decision cũ.
- Không cache allow lâu hơn thời gian hiệu lực của token hoặc entitlement.
- Không dùng cache chung thiếu tenant/platform scope.
- Fail closed khi không thể xác minh một quyết định quan trọng.

Đối với thao tác phá hủy hoặc cấp credential, có thể cần kiểm tra quyền trực tiếp hoặc dùng cache rất ngắn. Nếu operation đã được chấp nhận và chạy nền, lưu policy version cùng operation để có thể giải thích quyết định ban đầu.

## 18. Audit và giám sát quyết định authorization

Audit cần cho biết ai đã làm gì, trên đối tượng nào, theo policy nào và kết quả ra sao. Một record có thể gồm:

| Field | Mục đích |
|---|---|
| event_id | Định danh audit event |
| timestamp | Thời điểm quyết định |
| principal_id | Caller hoặc service identity |
| platform_id | Platform registration |
| tenant_id | Tenant scope đã resolve |
| action | PROVISION, BIND, UPDATE, UNBIND, DEPROVISION |
| resource_type/resource_id | Instance, binding hoặc operation |
| decision | ALLOW hoặc DENY |
| reason_code | Mã lý do đã chuẩn hóa |
| policy_version | Phiên bản policy |
| correlation_id | Liên kết với request/operation |
| source | HTTP, worker hoặc admin workflow |

Không ghi token, password, private key, connection URI có credential hoặc raw request body. Audit event cần được bảo vệ khỏi sửa/xóa trái phép và có retention policy.

Metrics có thể theo dõi số lần deny theo action/reason, số tenant bị suspend, số lỗi resolve scope và số operation bị worker dừng do authorization. Tránh dùng tenant ID hoặc resource ID làm label metric có cardinality cao; dùng reason/action hoặc nhóm đã chuẩn hóa.

## 19. Quyền quản trị và break-glass

Quản trị viên broker cần quyền cao hơn platform client, nhưng quyền đó cũng phải được kiểm soát. Tách các capability:

- Quản lý platform registration.
- Tạo/suspend tenant mapping.
- Quản lý service entitlement và plan availability.
- Xem audit/security event.
- Chạy reconciliation.
- Force cleanup hoặc xử lý tài nguyên bị kẹt.

Break-glass là quyền khẩn cấp để xử lý sự cố khi quy trình bình thường không đáp ứng. Nó nên có:

1. Danh tính quản trị được xác thực mạnh.
2. Lý do và ticket/incident reference.
3. Phạm vi resource/action cụ thể.
4. Thời hạn ngắn và tự hết hiệu lực.
5. Audit trước/sau thao tác.
6. Thông báo hoặc review độc lập sau sự kiện.

Không dùng một cờ isAdmin để bỏ qua mọi kiểm tra ownership và lifecycle. Ngay cả thao tác quản trị cũng cần ghi rõ target và lý do, đặc biệt khi xóa tài nguyên hoặc đọc dữ liệu nhạy cảm.

## 20. Ví dụ policy cho provision và deprovision

Một policy service có thể tách quyết định khỏi handler:

~~~java
public Mono<Void> authorizeProvision(
        AuthorizationContext context,
        String serviceId,
        String planId,
        String region) {

    return platformPolicy.assertActive(context.platformId())
        .then(tenantPolicy.assertActive(context.tenantId()))
        .then(entitlementPolicy.assertPlanAllowed(
            context.tenantId(), serviceId, planId))
        .then(regionPolicy.assertAllowed(
            context.tenantId(), region))
        .then(quotaPolicy.assertCapacityAvailable(
            context.tenantId(), serviceId));
}
~~~

Với deprovision:

~~~java
public Mono<Void> authorizeDeprovision(
        AuthorizationContext context,
        ServiceInstance instance) {

    return ownershipPolicy.assertOwnedBy(
            context.platformId(),
            context.tenantId(),
            instance
        )
        .then(servicePolicy.assertServiceMatches(
            instance.serviceId()))
        .then(lifecyclePolicy.assertCanDeprovision(
            instance.lifecycleState()))
        .then(retentionPolicy.assertDeletionAllowed(instance));
}
~~~

Các method policy là abstraction nội bộ minh họa. Trong triển khai thực tế, quota cần được reserve nguyên tử nếu có thể xảy ra request đồng thời; kiểm tra available trước rồi tạo resource sau có thể để hai request cùng vượt quota. Deprovision cần giữ đường cleanup ngay cả khi entitlement không còn hiệu lực, nhưng vẫn tuân thủ legal hold hoặc retention.

## 21. Kiểm thử phân quyền nhiều lớp

Kiểm thử phải xác nhận cả quyết định allow và deny. Đặc biệt, cần chứng minh ID trùng giữa tenant/platform không tạo truy cập chéo.

| Ca kiểm thử | Điều kiện | Kết quả mong đợi |
|---|---|---|
| Token hợp lệ, platform active | Caller đã xác thực | Qua authentication |
| Token hợp lệ, platform suspended | Registration bị khóa | Từ chối |
| Context giả tenant | Principal thuộc tenant A nhưng body khai tenant B | Không dùng tenant B |
| Tenant thiếu entitlement | Service/plan không được cấp | Từ chối trước provider call |
| Plan bị ẩn trong catalog | Caller gửi trực tiếp plan ID | Server vẫn kiểm tra entitlement |
| Instance tenant A, caller tenant B | External ID biết trước | Không đọc hoặc sửa resource |
| Instance trùng ID ở hai platform | Platform A/B có scope riêng | Không truy cập chéo |
| Binding của instance khác | Binding ID giống nhau | Parent instance scope quyết định |
| Service không bindable | Request bind | Từ chối, không tạo credential |
| Instance đang deprovisioning | Request bind/update | Từ chối theo lifecycle policy |
| Last operation sai scope | Operation thuộc tenant khác | Không tiết lộ trạng thái |
| Worker redelivery | Cùng operation được gửi lại | Chỉ thực thi target đã lưu, idempotent |
| Entitlement bị thu hồi | Request provision mới | Từ chối |
| Entitlement hết hạn sau 202 | Worker tiếp tục operation đã accepted | Theo policy version và execution rule đã định nghĩa |
| Policy engine timeout | Không có quyết định | Fail closed |
| Cache sau suspend | Decision allow cũ còn cache | Invalidation/TTL ngăn quyền tồn tại quá lâu |
| Break-glass | Admin thao tác có scope và lý do | Audit đầy đủ, quyền hết hạn |
| Secret trong audit | Request chứa credentials | Không log dữ liệu nhạy cảm |

Nên có unit test cho từng policy, integration test qua Spring Security filter chain, repository test với database thật và test worker chạy lại operation. Với reactive stack, dùng StepVerifier/WebTestClient để xác minh context không bị mất giữa các operator.

## 22. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Xem authentication là authorization | Platform credential có quyền quá rộng | Kiểm tra quyền theo scope và action |
| Tin tenant ID từ request body | Caller có thể giả mạo ownership | Resolve tenant từ platform registration |
| Chỉ dùng RBAC toàn cục | Role không phân biệt tenant/resource | Gắn role với scope và bổ sung ABAC/ownership |
| Chỉ lọc catalog | Caller gọi trực tiếp plan ID vẫn có thể vượt quyền | Kiểm tra entitlement server-side |
| Tìm resource theo ID toàn cục | Nguy cơ IDOR/cross-tenant access | Scoped repository lookup |
| Kiểm tra quyền chỉ ở controller | Worker hoặc internal service bỏ qua policy | Domain authorization tại service boundary |
| Dùng chung quyền admin cho platform client | Lộ dữ liệu và thao tác vượt phạm vi | Tách platform authority và admin role |
| Worker dùng credential toàn năng | Một job bị chiếm quyền có thể ảnh hưởng toàn broker | Service identity và least privilege |
| Cache allow không có scope/version | Quyền stale hoặc rò giữa tenant | Cache key đầy đủ và invalidation |
| Fail open khi policy service lỗi | Mất kiểm soát truy cập | Deny by default |
| Error response tiết lộ resource khác | Dò ID và tenant | Error mapping không tiết lộ tồn tại |
| Không audit quyết định deny | Khó phát hiện tấn công và lỗi cấu hình | Audit reason code, action, scope |
| Cho break-glass bỏ qua mọi policy | Quyền khẩn cấp trở thành quyền thường trực | Scope hẹp, thời hạn ngắn, review |

## 23. Nguyên tắc cần ghi nhớ

Phân quyền trong service broker phải được đánh giá theo caller, platform, tenant, service/plan và resource. Spring Security xác thực và bảo vệ HTTP boundary; authorization context chuẩn hóa identity và scope; domain policy quyết định quyền theo action, entitlement, ownership và lifecycle; repository/database giới hạn dữ liệu; worker sử dụng execution identity có phạm vi hẹp.

Khi triển khai **SPRING_CLOUD_SERVICE_BROKER**, hãy giữ các nguyên tắc:

- Tách authentication khỏi authorization.
- Lấy platform identity từ principal đã xác thực.
- Resolve tenant và external scope từ mapping đáng tin cậy.
- Kết hợp RBAC với ABAC và quan hệ ownership khi cần.
- Kiểm tra entitlement service/plan ở server cho cả provision và update.
- Kiểm tra ownership và lifecycle ở mọi thao tác instance/binding/operation.
- Giới hạn repository lookup theo platform/tenant/parent resource.
- Không để worker nền dùng quyền admin toàn cục hoặc tin payload queue.
- Mặc định từ chối khi không có quyết định policy đáng tin cậy.
- Audit allow/deny mà không ghi secret.
- Thiết kế cache, quota và break-glass có scope, version và thời hạn rõ ràng.

Khi các lớp quyền được phân tách và kiểm tra nhất quán, broker có thể phục vụ nhiều platform và khách hàng trên cùng hạ tầng mà vẫn giữ quyền truy cập đúng phạm vi, bảo vệ tài nguyên và hỗ trợ vận hành an toàn.

