# Giới thiệu tính năng tùy chọn theo năng lực thực tế của nền tảng

## Mục tiêu và bối cảnh

Một service broker có thể triển khai nhiều tính năng: provision bất đồng bộ, update plan, binding, truy xuất thông tin instance, truy xuất binding, dashboard, context update hoặc các kiểu binding đặc thù như route forwarding và volume mount. Tuy nhiên, không phải platform nào cũng hỗ trợ tất cả các khả năng đó, và không phải backend provider nào cũng thực thi được chúng.

Trong Spring Cloud Service Broker, việc bật một tính năng phải dựa trên khả năng thực tế của cả chuỗi tích hợp: platform, giao thức OSB API, broker implementation, provider backend và quy trình vận hành. Nếu broker quảng bá một tính năng trong catalog nhưng không thực hiện được request tương ứng, platform có thể hiển thị lựa chọn sai hoặc tạo ra instance không thể quản lý. Nếu broker tắt một tính năng mà backend đã hỗ trợ, người dùng có thể không tận dụng được năng lực sẵn có.

Bài học này trình bày cách giới thiệu tính năng tùy chọn theo năng lực thực tế của nền tảng. Trọng tâm là xây dựng capability matrix, công bố khả năng qua OSB catalog, quản lý feature flags, kiểm tra tương thích, rollout đồng nhất giữa các broker replica và bảo vệ tài nguyên đã tồn tại khi thay đổi cấu hình.

Sau bài học, bạn có thể:

- Phân biệt năng lực của platform, broker và provider.
- Xác định tính năng nào là khả năng chuẩn hóa trong OSB API và tính năng nào là mở rộng riêng.
- Công bố bindable, plan_updateable, requires và các metadata/schema phù hợp.
- Bật/tắt tính năng theo platform profile, service hoặc plan.
- Tránh quảng bá tính năng khi thiếu worker, persistence, security hoặc backend support.
- Triển khai feature flags an toàn và nhất quán giữa nhiều replica.
- Giữ tương thích với instance và operation đang hoạt động khi thay đổi capability.
- Kiểm thử catalog, request thực tế và hành vi khi platform không hỗ trợ tính năng.

## 1. Tính năng tùy chọn là gì?

Tính năng tùy chọn là hành vi mà broker có thể cung cấp nhưng không phải mọi deployment hoặc mọi platform đều sử dụng được. Một số khả năng được OSB API mô tả trực tiếp; một số khác phụ thuộc vào tích hợp platform hoặc provider.

Ví dụ:

- Broker có thể xử lý provision đồng bộ hoặc bất đồng bộ.
- Một service có thể cho phép binding hoặc chỉ provision độc lập.
- Một plan có thể cho phép update sang plan khác.
- Platform có thể hỗ trợ route service hoặc volume mount binding.
- Broker có thể cho phép truy xuất lại thông tin instance hoặc binding.
- Provider có thể hỗ trợ maintenance version hoặc dashboard.
- Một deployment có thể bật context update, trong khi deployment khác chưa có policy an toàn.

Không nên coi danh sách feature flags nội bộ là bằng chứng platform có hỗ trợ. Một flag chỉ điều khiển code của broker; nó không tự thêm khả năng vào Cloud Foundry, Kubernetes, OSB client hoặc provider.

### 1.1. Năng lực phải tồn tại ở toàn bộ chuỗi

Một tính năng chỉ nên được quảng bá khi tất cả thành phần liên quan đều đáp ứng:

1. Platform có thể gửi và xử lý request hoặc metadata tương ứng.
2. Phiên bản OSB API đang dùng định nghĩa được hành vi đó.
3. Broker có handler và state management đúng.
4. Provider backend có API hoặc cơ chế thực thi.
5. Security, retry, audit và vận hành đã được chuẩn bị.
6. Test xác nhận luồng thành công, lỗi và phục hồi.

~~~mermaid
flowchart TD
    P[Platform capability] --> G{Protocol compatible?}
    G -->|No| X[Do not advertise]
    G -->|Yes| B[Broker implementation]
    B --> H{Handler and state ready?}
    H -->|No| X
    H -->|Yes| R[Provider capability]
    R --> S{Backend operation supported?}
    S -->|No| X
    S -->|Yes| O{Security and operations ready?}
    O -->|No| X
    O -->|Yes| T[Contract and integration tests]
    T -->|Pass| E[Enable and advertise feature]
    T -->|Fail| X
~~~

Ví dụ broker có thể tạo database bằng API provider nhưng provider không hỗ trợ revoke credential riêng cho từng binding. Khi đó broker có thể hỗ trợ provision nhưng không nên khai báo service bindable cho tới khi có cách cấp và thu hồi binding an toàn.

### 1.2. Phân biệt khả năng, cấu hình và quyền sử dụng

Ba khái niệm cần được tách riêng:

| Khái niệm | Câu hỏi |
|---|---|
| Capability | Hệ thống có khả năng thực hiện hành vi này không? |
| Configuration/feature flag | Deployment hoặc service có bật hành vi này không? |
| Authorization/access | Caller hoặc tenant có được phép sử dụng hành vi đã bật không? |

Một platform có thể hỗ trợ binding, broker cũng có implementation, nhưng administrator có thể tắt binding cho một plan. Ngược lại, một tenant không có quyền dùng plan không có nghĩa broker mất capability binding.

## 2. Xây dựng capability matrix

Trước khi công bố tính năng, lập bảng năng lực theo platform, broker và provider. Bảng này là tài liệu quyết định cấu hình, không chỉ là checklist triển khai.

Ví dụ:

| Tính năng | Platform | Broker | Provider | Điều kiện bật |
|---|---|---|---|---|
| Catalog và plan | Đọc OSB catalog | Có endpoint catalog | Không phụ thuộc trực tiếp | OSB version tương thích |
| Provision | Gửi provision request | Có handler và persistence | Có API tạo resource | Đã test create và recovery |
| Async operation | Hỗ trợ accepts_incomplete và polling | Có operation store, worker, last_operation | Có thể xử lý lâu hoặc async | Có retry/idempotency bền vững |
| Binding | Có luồng bind | Có bind/unbind handler | Cấp/revoke credential | Credential lifecycle hoàn chỉnh |
| Plan update | Hỗ trợ update OSB | Có validation/state transition | Có API thay đổi cấu hình | Có migration/compensation |
| Route forwarding | Platform có route service integration | Có binding semantics tương ứng | Có route registration backend | Test route lifecycle |
| Volume mount | Platform hỗ trợ kiểu binding cần thiết | Có metadata và handler tương ứng | Có volume/export capability | Kiểm tra bảo mật và mount lifecycle |
| Binding retrieval | Platform có dùng retrieval endpoint | Lưu binding data an toàn | Có thể tái tạo hoặc truy xuất dữ liệu | Persistence và authorization phù hợp |
| Dashboard | Platform có thể dùng dashboard URL | Công bố URL và auth flow | Có dashboard hoạt động | SSO/session bảo mật |

Capability matrix cần được quản lý theo từng deployment profile hoặc từng service/plan nếu khả năng khác nhau. Không gộp mọi platform thành một giá trị supportsAllFeatures=true.

### 2.1. Capability của platform

Platform capability có thể khác theo sản phẩm, phiên bản, cấu hình và controller tích hợp.

Ví dụ:

- Cloud Foundry có thể gọi OSB API và điều phối các lifecycle request theo phiên bản Cloud Controller đang chạy.
- Kubernetes có thể dùng controller hoặc adapter khác nhau để gọi broker và đưa binding data vào workload.
- Một tích hợp Kubernetes cũ có thể hỗ trợ một tập con tính năng hoặc không tương thích với Kubernetes version hiện tại.
- Một platform có thể hỗ trợ OSB provision/bind nhưng không hỗ trợ một kiểu binding đặc thù.

Không suy luận capability chỉ từ header User-Agent, tên platform hoặc một giá trị context do caller gửi. Hãy dùng platform registration đã xác thực, phiên bản đã kiểm chứng và integration test với đúng controller đang triển khai.

### 2.2. Capability của broker

Broker capability phải được chứng minh bởi implementation thực tế:

- Endpoint và handler tồn tại.
- State machine cho phép transition tương ứng.
- Persistence lưu đủ dữ liệu để retry và phục hồi.
- Idempotency ngăn side effect lặp.
- Authorization kiểm tra đúng owner.
- Error mapping phù hợp OSB API.
- Worker hoặc scheduler có giới hạn và giám sát.
- Test cover cả success, failure và restart.

Chỉ thêm một boolean vào catalog không làm cho broker có khả năng đó.

### 2.3. Capability của provider

Provider có thể hỗ trợ một thao tác nhưng không hỗ trợ thao tác ngược lại. Ví dụ provider có thể tạo user nhưng không cho rotate password theo cách không gián đoạn; có thể tạo database nhưng không resize online; có thể cấp credential nhưng không có API thu hồi riêng cho từng binding.

Cần mô tả rõ:

- API provider nào thực hiện feature.
- Có hỗ trợ idempotency key hay không.
- Có lookup resource theo request key không.
- Có hỗ trợ rollback hoặc compensation không.
- Thời gian thực thi và quota.
- Hành vi khi timeout sau side effect.
- Cách thu hồi quyền và dọn resource.

## 3. Công bố khả năng qua OSB catalog

OSB catalog là hợp đồng để platform biết service và plan nào có thể được sử dụng. Broker cần khai báo capability đúng với service hoặc plan thay vì chỉ mô tả bằng văn bản.

Một số trường tiêu biểu:

| Trường catalog | Ý nghĩa |
|---|---|
| bindable | Service có hỗ trợ tạo binding hay không |
| plan_updateable | Service có hỗ trợ thay đổi plan cho instance hay không |
| requires | Các capability platform cần có để hỗ trợ kiểu binding tương ứng |
| schemas | Schema parameters cho create, update hoặc binding |
| dashboard_client | Thông tin dashboard client nếu được triển khai |
| instances_retrievable | Khả năng truy xuất thông tin instance khi được hỗ trợ |
| bindings_retrievable | Khả năng truy xuất thông tin binding khi được hỗ trợ |
| allow_context_updates | Cho phép cập nhật context theo contract OSB API khi broker hỗ trợ |

Các field và semantics phụ thuộc phiên bản OSB API. Hãy kiểm tra specification mà broker tuyên bố hỗ trợ và framework version đang dùng. Không tự tạo field tùy ý rồi mong platform hiểu như capability chuẩn.

### 3.1. Khai báo bindable

Nếu service hỗ trợ binding:

~~~json
{
  "id": "service-postgresql",
  "name": "managed-postgresql",
  "description": "Managed PostgreSQL service",
  "bindable": true,
  "plans": [
    {
      "id": "plan-standard",
      "name": "standard",
      "description": "Standard database plan"
    }
  ]
}
~~~

Nếu broker chưa thể tạo binding an toàn, khai báo bindable là false hoặc không công bố binding capability theo đúng catalog contract. Không để platform cho phép bind rồi mới phát hiện handler chưa được triển khai.

### 3.2. Khai báo plan update

Khi service thực sự cho phép chuyển instance sang plan khác, catalog có thể khai báo plan_updateable theo OSB API version được hỗ trợ.

~~~json
{
  "id": "service-postgresql",
  "name": "managed-postgresql",
  "description": "Managed PostgreSQL service",
  "bindable": true,
  "plan_updateable": true,
  "plans": [
    {
      "id": "plan-standard",
      "name": "standard",
      "description": "Standard database plan"
    },
    {
      "id": "plan-premium",
      "name": "premium",
      "description": "Premium database plan"
    }
  ]
}
~~~

Giá trị true phải phản ánh việc broker có thể xử lý update theo contract, bao gồm validation, quota, transition và backend operation. Không đặt true chỉ vì catalog có nhiều plan.

### 3.3. Khai báo platform requirements

Trường requires có thể mô tả capability platform cần có cho kiểu binding mà service yêu cầu. Các giá trị tiêu chuẩn thường được dùng cho những tích hợp như syslog_drain, route_forwarding hoặc volume_mount, theo OSB API version.

~~~json
{
  "id": "service-route-logger",
  "name": "route-aware-logger",
  "description": "A logging service that receives routed application traffic",
  "bindable": true,
  "requires": [
    "route_forwarding"
  ],
  "plans": [
    {
      "id": "plan-basic",
      "name": "basic",
      "description": "Basic route logging"
    }
  ]
}
~~~

Ví dụ này chỉ nên được công bố nếu platform đích hỗ trợ route forwarding theo mô hình tương ứng và broker/provider thực hiện đầy đủ việc đăng ký, cập nhật và thu hồi route. Nếu platform không hỗ trợ requirement đó, không nên quảng bá service như thể có thể bind bình thường.

### 3.4. Schema giúp platform và caller hiểu parameters

Plan có thể công bố schema cho parameters của service instance create/update hoặc service binding create khi phiên bản OSB API và framework hỗ trợ.

Schema nên phản ánh:

- Field bắt buộc và optional.
- Kiểu dữ liệu, miền giá trị và giới hạn.
- Default đã được xác định.
- Field nào chỉ được dùng khi feature tương ứng bật.
- Quy tắc tương thích khi schema thay đổi.

Không dùng schema như biện pháp bảo mật duy nhất. Broker vẫn phải validate request ở server vì client có thể bỏ qua schema hoặc gửi payload cũ.

## 4. Phân loại feature theo phạm vi áp dụng

Không phải tính năng nào cũng bật/tắt ở cùng một cấp.

| Phạm vi | Ví dụ | Nơi quyết định |
|---|---|---|
| Deployment-wide | OSB API versions, async worker, provider integration | Cấu hình deployment |
| Platform profile | Context mapping, route service, platform-specific binding | Profile của platform đã đăng ký |
| Service-level | bindable, retrieval capability, requires | Service catalog |
| Plan-level | Plan schema, maintenance metadata, giới hạn tài nguyên | Plan catalog và policy |
| Tenant-level | Cho phép plan premium hoặc dashboard | Entitlement/authorization |
| Instance-level | Feature snapshot, operation capability đã dùng | Instance record và lifecycle state |

Ví dụ, async worker có thể là capability deployment-wide vì tất cả replica cùng dùng một queue. Nhưng một plan có thể không hỗ trợ update; một tenant có thể không được phép dùng plan premium. Những quyết định này phải được tách khỏi nhau.

### 4.1. Không để caller tự bật capability

Không chấp nhận một request body kiểu enableRouteForwarding=true như bằng chứng platform hỗ trợ route forwarding. Caller có thể gửi field tùy ý.

Broker phải xác định platform profile từ registration hoặc identity đã xác thực, sau đó kiểm tra feature policy. Request chỉ được phép sử dụng capability đã được broker công bố và platform profile cho phép.

## 5. Thiết kế capability model trong ứng dụng Spring

Nên gom khả năng thành một mô hình rõ ràng, thay vì rải nhiều điều kiện boolean trong controller và service.

Ví dụ:

~~~java
public record BrokerCapabilities(
        boolean asyncProvisioning,
        boolean planUpdate,
        boolean binding,
        boolean instanceRetrieval,
        boolean bindingRetrieval,
        boolean contextUpdates
) {}
~~~

Một profile cho platform có thể chứa tập khả năng đã được kiểm chứng:

~~~java
public record PlatformProfile(
        String platformId,
        String osbApiVersion,
        Set<String> supportedRequirements,
        boolean acceptsAsyncOperations,
        boolean supportsContextUpdates
) {}
~~~

Đây là mô hình nội bộ minh họa. Không đưa profile do caller tự khai báo vào trust boundary; profile phải được tạo từ registration, cấu hình được quản lý và compatibility test.

### 5.1. Kết hợp các capability

Một tính năng được bật khi các điều kiện liên quan đều đúng:

~~~java
public boolean canUseAsyncProvisioning(
        BrokerCapabilities broker,
        PlatformProfile platform,
        ProviderCapabilities provider) {

    return broker.asyncProvisioning()
            && platform.acceptsAsyncOperations()
            && provider.supportsLongRunningProvision();
}
~~~

Trong triển khai thật, ProviderCapabilities có thể là một interface hoặc policy riêng. Điều quan trọng là quyết định không dựa trên một flag duy nhất.

### 5.2. Cấu hình feature flags

Ví dụ cấu hình:

~~~yaml
broker:
  features:
    async-provisioning: true
    plan-update: true
    binding: true
    instance-retrieval: false
    binding-retrieval: false
    context-updates: false
~~~

Đây là cấu hình do ứng dụng định nghĩa. Spring Boot không tự tạo các property này; cần bind bằng ConfigurationProperties, validate khi khởi động và expose một capability object immutable cho các service.

Nếu bật async-provisioning nhưng thiếu queue, worker hoặc operation persistence, ứng dụng nên fail startup hoặc từ chối quảng bá capability. Không chờ tới lúc request provision mới phát hiện worker chưa cấu hình.

### 5.3. Tách catalog builder khỏi handler

Catalog builder đọc capability đã được xác thực và tạo service catalog. Handler vẫn phải kiểm tra feature policy trước khi thực hiện request.

~~~java
public ServiceCatalog buildCatalog(BrokerCapabilities capabilities) {
    ServiceDefinition service = ServiceDefinition.builder()
            .id("service-postgresql")
            .name("managed-postgresql")
            .bindable(capabilities.binding())
            .planUpdateable(capabilities.planUpdate())
            .build();

    return new ServiceCatalog(List.of(service));
}
~~~

Đây là pseudocode, không phải tên API builder bắt buộc của mọi phiên bản Spring Cloud Open Service Broker. Dùng model và builder thực tế của dependency trong project.

Việc kiểm tra ở handler là cần thiết vì catalog có thể được cache, client có thể giữ catalog cũ hoặc request có thể được gửi trực tiếp. Catalog giúp discovery; server-side validation vẫn là lớp bảo vệ cuối cùng.

## 6. Bật tính năng bất đồng bộ đúng điều kiện

Async operation hữu ích khi provision, update hoặc deprovision có thể kéo dài. Tuy nhiên, broker chỉ nên nhận request async khi có đủ:

- Operation store bền vững.
- Worker hoặc cơ chế thực thi nền.
- Queue/outbox hoặc cách giao việc không mất.
- Idempotency cho request và backend side effect.
- Endpoint last_operation.
- Retry, backoff và reconciliation.
- Monitoring operation age và trạng thái stuck.

Trong OSB API, platform có thể gửi accepts_incomplete=true để cho biết nó chấp nhận xử lý bất đồng bộ. Broker không được giả định mọi platform hoặc mọi request đều chấp nhận async.

Luồng minh họa:

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Broker
    participant D as Broker DB
    participant W as Worker
    participant V as Provider
    P->>B: Provision + accepts_incomplete=true
    B->>D: Persist instance, operation and work item
    B-->>P: 202 Accepted + operation token
    W->>D: Claim operation
    W->>V: Provision resource
    V-->>W: Result
    W->>D: Update operation and instance
    P->>B: GET last_operation
    B-->>P: succeeded / in progress / failed
~~~

Nếu platform không chấp nhận incomplete operation và broker không thể hoàn tất đồng bộ, broker phải trả response theo quy tắc OSB API, thường là 422 Unprocessable Entity với lỗi AsyncRequired. Không tự ý trả 202 nếu request không cho phép.

### 6.1. Không bật async chỉ bằng catalog flag

Async là hành vi runtime, không chỉ là metadata. Nếu worker không chạy hoặc queue không bền vững, catalog và endpoint có thể tuyên bố một khả năng không tồn tại.

Test phải xác minh operation được ghi trước response 202, worker có thể tiếp tục sau restart và last_operation trả đúng trạng thái.

## 7. Bật binding và các kiểu binding tùy chọn

Service có thể bindable nhưng từng kiểu binding vẫn phụ thuộc platform và provider. Hãy xác định rõ broker đang cấp credentials thông thường, route service, syslog drain hay volume mount.

### 7.1. Binding credentials thông thường

Để bật binding, broker cần:

- Handler bind và unbind.
- Identity riêng cho binding.
- Cấp credential theo consumer hoặc binding.
- Lưu binding metadata an toàn.
- Revoke quyền khi unbind.
- Idempotency và recovery nếu provider timeout.

Nếu backend chỉ có một shared credential và không thể revoke riêng từng consumer, cần đánh giá kỹ rủi ro trước khi công bố bindable.

### 7.2. Route forwarding, syslog drain và volume mount

Các kiểu binding đặc thù cần platform capability và provider integration tương ứng. Chỉ thêm giá trị vào requires khi broker thật sự yêu cầu platform hỗ trợ kiểu đó.

Ví dụ route forwarding cần lifecycle cho route registration; volume mount cần cơ chế an toàn để cung cấp volume/mount data; syslog drain cần endpoint và quy trình nhận log phù hợp. Các yêu cầu này khác nhau theo platform và phiên bản tích hợp.

Không suy ra platform hỗ trợ chỉ vì OSB API có tên requirement đó. Chạy integration test trên đúng Cloud Foundry foundation hoặc Kubernetes controller/adapter mà hệ thống sử dụng.

## 8. Tính năng update, retrieval và context updates

### 8.1. Plan update

Nếu service công bố plan updateable, broker cần hỗ trợ kiểm tra:

- Plan nguồn và plan đích.
- Parameters update có hợp lệ không.
- Quota và entitlement của tenant.
- Provider có hỗ trợ chuyển plan không.
- Có cần migration hoặc restart resource không.
- Operation có cần async không.
- Có thể rollback/compensate nếu provider update một phần không.

Không đổi plan_updateable thành true chỉ để làm plan mới xuất hiện. Catalog phải phản ánh khả năng update đã được kiểm thử.

### 8.2. Instance và binding retrieval

Các capability retrieval chỉ nên được công bố khi broker lưu đủ dữ liệu và có thể trả kết quả an toàn. Cần bảo đảm:

- External ID và owner mapping còn tồn tại.
- Credentials không bị trả cho caller không có quyền.
- Response nhất quán với dữ liệu đã lưu.
- Secret được mã hóa hoặc tham chiếu qua secret manager.
- Việc retrieval không tạo side effect.

Nếu broker không hỗ trợ retrieval, không tạo endpoint giả trả dữ liệu không đầy đủ chỉ để platform thấy request thành công.

### 8.3. Context updates

Context có thể mang thông tin platform, organization, space hoặc consumer theo OSB API. Chỉ cho phép cập nhật context khi broker có quy tắc xác minh và migration dữ liệu rõ ràng.

Không coi context mới là bằng chứng caller có quyền đổi owner. Các trường ownership quan trọng cần được kiểm tra theo identity đã xác thực và policy của broker.

## 9. Rollout feature flags nhất quán giữa các replica

Trong deployment nhiều pod, catalog và runtime behavior phải nhất quán. Nếu một replica quảng bá binding nhưng replica khác từ chối bind, platform sẽ gặp lỗi ngẫu nhiên tùy request được route tới đâu.

Các nguyên tắc:

- Lưu cấu hình capability ở nguồn tập trung hoặc phát hành cùng một version.
- Validate config khi startup.
- Tạo capability snapshot immutable cho mỗi release/profile.
- Đồng bộ catalog cache giữa các replica.
- Không bật feature trên một pod trước khi dependency đã sẵn sàng trên toàn deployment.
- Có rollout stage và rollback plan.
- Ghi version cấu hình/capability trong log và operation metadata.

### 9.1. Catalog revision

Có thể quản lý một catalog revision hoặc deployment configuration version nội bộ để xác định catalog nào đang được công bố.

Khi rollout:

1. Deploy code có handler và dependency nhưng feature vẫn tắt.
2. Kiểm thử nội bộ trên staging.
3. Bật feature trên một môi trường/tenant canary nếu mô hình cho phép.
4. Xác nhận tất cả replica trả cùng catalog.
5. Chạy contract và lifecycle tests.
6. Mở rộng phạm vi.
7. Theo dõi lỗi và rollback nếu cần.

Không dùng random feature state theo request hoặc theo pod.

### 9.2. Giữ snapshot capability cho instance đang tồn tại

Một instance được tạo khi feature version A đang bật có thể cần được quản lý sau khi deployment chuyển sang version B.

Lưu các thông tin cần thiết:

- Service ID và plan ID tại thời điểm provision.
- Catalog/schema revision.
- Feature/capability profile version.
- Operation type và parameters đã chuẩn hóa.
- Provider resource ID và binding identity.

Khi feature bị tắt cho instance mới, broker vẫn phải có đường xử lý deprovision, unbind và reconciliation cho instance cũ. Không xóa handler hoặc metadata cần để thu hồi tài nguyên hiện hữu.

## 10. Tương thích ngược khi thay đổi capability

Capability là một phần của hợp đồng với platform và consumer. Thay đổi cách quảng bá có thể ảnh hưởng đến catalog cache, marketplace và instance đang hoạt động.

### 10.1. Thêm feature

Khi thêm tính năng:

1. Kiểm tra OSB API version hỗ trợ field/behavior.
2. Deploy handler và backend integration.
3. Bổ sung schema và metadata.
4. Kiểm thử platform capability.
5. Bật feature flag.
6. Công bố catalog mới.
7. Theo dõi request và operation.

Nếu feature cần thay đổi schema, hãy giữ default tương thích với request cũ.

### 10.2. Tắt feature

Tắt feature mới không đồng nghĩa được bỏ khả năng quản lý tài nguyên đã tạo bằng feature đó.

Ví dụ khi ngừng cho phép binding mới:

- Không nhận binding mới nếu policy đã tắt.
- Vẫn phải unbind binding hiện hữu.
- Vẫn phải revoke credentials cũ.
- Vẫn phải cho phép deprovision instance.
- Giữ metadata để biết binding được tạo theo contract nào.

### 10.3. Loại bỏ plan hoặc metadata

Không xóa plan đang có instance hoạt động chỉ vì không muốn bán plan đó nữa. Có thể ngừng cấp quyền tạo mới hoặc đánh dấu plan không còn được cung cấp theo cơ chế platform hỗ trợ, trong khi vẫn giữ khả năng quản lý instance cũ.

Service ID và plan ID cần ổn định. Thay ID có thể khiến platform không nhận diện được offering/plan cũ và gây khó khăn cho lifecycle.

## 11. Feature flags và entitlement không thay thế security

Feature flag quyết định code path nào được triển khai hoặc công bố. Entitlement quyết định tenant có được dùng feature/plan hay không. Authorization quyết định caller có quyền thực hiện hành động cụ thể hay không.

Ví dụ:

- binding=true: broker có implementation binding.
- Tenant A được phép dùng plan premium: entitlement.
- Platform caller có quyền bind instance X: authorization.
- Platform profile hỗ trợ route_forwarding: capability.

Cả bốn điều kiện có thể cần đồng thời đúng. Không dùng feature flag để thay thế kiểm tra ownership hoặc role.

Khi feature bị tắt, request trực tiếp vẫn phải bị từ chối an toàn. Không dựa vào việc platform sẽ không gửi request vì catalog đã ẩn tính năng.

## 12. Kiểm thử capability và feature rollout

Một bộ test tốt cần xác minh catalog và runtime cùng phản ánh một capability profile.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Broker hỗ trợ binding và provider revoke được | Catalog bindable đúng; bind/unbind hoạt động |
| Broker tắt binding | Catalog không quảng bá bindable; request bind trực tiếp bị từ chối |
| Platform không hỗ trợ requirement | Service có requirement không được đưa vào phạm vi platform đó |
| Async worker đầy đủ và platform chấp nhận incomplete | Broker trả 202 và last_operation theo dõi được |
| Async bị tắt hoặc thiếu worker | Không quảng bá/nhận async như thể đã hỗ trợ |
| Plan update bật | Catalog khai báo đúng; update validation và provider transition chạy |
| Plan update tắt | Không cho phép chuyển plan mới; vẫn quản lý instance cũ |
| Replica có config khác nhau | Test phát hiện catalog mismatch trước rollout |
| Feature flag thay đổi khi operation đang chạy | Operation cũ hoàn tất theo snapshot/policy đã lưu |
| Tenant không có entitlement | Không được sử dụng feature dù catalog chung có capability |
| Caller không sở hữu instance | Request bị từ chối trước provider side effect |
| OSB version ngoài range | Request bị từ chối theo protocol contract |

### 12.1. Test catalog theo profile

Với mỗi profile:

- Gọi catalog.
- Kiểm tra service/plan ID ổn định.
- Kiểm tra bindable, plan_updateable, requires và schema.
- Xác minh feature bị tắt không xuất hiện như capability được hỗ trợ.
- So sánh catalog từ nhiều replica.
- Kiểm tra OSB API version negotiation.

### 12.2. Test runtime behavior

Không dừng ở việc so sánh JSON catalog. Hãy gửi request thực:

- Bind khi bindable true.
- Bind khi bindable false.
- Update khi plan_updateable true và false.
- Provision async có và không có accepts_incomplete=true.
- Retrieval khi capability bật/tắt.
- Deprovision instance được tạo từ catalog revision cũ.
- Unbind binding được tạo trước khi feature bị tắt.

Kiểm tra database state, operation record, backend side effect và error response.

## 13. Những lỗi thiết kế thường gặp

- **Bật feature theo suy đoán platform:** catalog quảng bá khả năng mà controller không hỗ trợ.
- **Chỉ bật flag trong broker:** provider chưa có API hoặc chưa có quyền thực thi.
- **Quảng bá bindable khi không thể revoke:** tạo credentials không có vòng đời an toàn.
- **Quảng bá async khi thiếu worker/outbox:** operation có thể bị mất hoặc mắc kẹt.
- **Công bố plan_updateable nhưng update chưa idempotent:** retry có thể thay đổi resource nhiều lần.
- **Dùng User-Agent để xác định capability:** header không phải bằng chứng đáng tin cậy.
- **Để mỗi replica có config riêng:** catalog và runtime không nhất quán.
- **Tắt handler cùng lúc với feature mới:** instance cũ không thể unbind/deprovision.
- **Đổi service/plan ID khi rollout:** phá mapping của instance hiện hữu.
- **Dùng catalog làm lớp authorization duy nhất:** request trực tiếp vẫn có thể gọi endpoint.
- **Cho tenant tự bật capability:** vượt qua policy platform và broker.
- **Không version hóa schema/capability:** operation cũ bị diễn giải bằng quy tắc mới.

## 14. Quy trình giới thiệu một tính năng tùy chọn

Khi muốn thêm một feature vào Spring Cloud Service Broker, hãy thực hiện:

1. Mô tả hành vi và lý do cần feature.
2. Xác định OSB API version và catalog field liên quan.
3. Kiểm tra platform đích có hỗ trợ behavior đó.
4. Kiểm tra provider API, quota và khả năng thu hồi.
5. Xác định handler, state transition, persistence và idempotency.
6. Định nghĩa capability model và feature flag theo đúng scope.
7. Bổ sung schema/metadata và catalog builder.
8. Thêm server-side validation và authorization.
9. Viết contract, integration, failure và rollback tests.
10. Deploy code ở trạng thái feature tắt.
11. Bật canary và xác nhận catalog giống nhau trên các replica.
12. Mở rộng rollout và theo dõi metrics.
13. Lưu capability/schema revision cho instance và operation.
14. Giữ đường lifecycle cho resource cũ nếu sau này tắt feature.

## Kết luận

Tính năng tùy chọn chỉ nên được công bố khi platform, OSB API version, broker implementation, provider và quy trình vận hành đều hỗ trợ. Capability matrix giúp xác định giới hạn thật; catalog cho platform biết service có bindable, plan updateable hoặc yêu cầu binding nào; feature flags điều khiển rollout nội bộ; entitlement và authorization quyết định ai được sử dụng.

Trong Spring Cloud Service Broker, hãy kết hợp capability profile đã xác thực, catalog builder, server-side validation và cấu hình đồng nhất giữa các replica. Khi thêm hoặc tắt tính năng, giữ service/plan identity và metadata cần thiết cho instance cũ, đồng thời bảo đảm unbind, deprovision và reconciliation vẫn hoạt động. Cách làm này giúp broker công bố đúng năng lực, tránh hứa quá khả năng và nâng cấp từng bước mà không làm hỏng các service instance đang được sử dụng.
