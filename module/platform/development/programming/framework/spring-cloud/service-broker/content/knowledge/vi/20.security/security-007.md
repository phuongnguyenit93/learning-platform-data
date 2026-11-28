# Kiểm tra originating identity và context trong ranh giới tin cậy

Trong module **SPRING_CLOUD_SERVICE_BROKER**, broker nhận request từ platform để provision service instance, update, tạo binding và thu hồi tài nguyên. Những request này có thể mang thông tin về người dùng đã khởi tạo thao tác và môi trường platform nơi tài nguyên được tạo. Hai nguồn dữ liệu quan trọng là header **X-Broker-API-Originating-Identity** và trường **context** trong request body.

Hai dữ liệu này phục vụ những mục đích khác nhau. Originating identity mô tả danh tính người dùng hoặc tác nhân khởi tạo request theo cách platform cung cấp. Context mô tả phạm vi triển khai, chẳng hạn organization, space, cluster, namespace hoặc tenant metadata. Cả hai đều đi qua ranh giới giữa platform và broker, vì vậy broker phải xác định ai đã gửi chúng, mức độ tin cậy của nguồn, cách xác thực nội dung và phạm vi sử dụng.

Điểm cốt lõi là không đồng nhất thông tin nhận dạng do platform chuyển tiếp với thông tin xác thực của kết nối HTTP. Broker vẫn phải xác thực platform client, kiểm tra quyền trên resource và đối chiếu context với dữ liệu sở hữu đã lưu. Một header hoặc JSON object không tự chứng minh caller có quyền truy cập service instance.

## 1. Hai loại dữ liệu và hai câu hỏi khác nhau

Khi nhận request OSB API, broker có thể nhận:

- **Originating identity:** ai là người dùng hoặc tác nhân đã khởi tạo hành động ở phía platform?
- **Context:** request đang diễn ra trong organization, space, cluster, namespace hoặc phạm vi platform nào?

Ví dụ một người dùng trong organization payments yêu cầu tạo PostgreSQL instance cho ứng dụng billing. Originating identity có thể cho biết user GUID hoặc username mà Cloud Foundry chuyển tiếp. Context có thể cho biết organization GUID và space GUID. Broker dùng identity để audit actor và áp dụng policy người dùng; dùng context để xác định tenant scope và định tuyến tài nguyên.

| Tiêu chí | Originating identity | Context |
|---|---|---|
| Vị trí | HTTP header | Trường trong request JSON |
| Mục đích | Nhận diện actor khởi tạo thao tác | Mô tả môi trường/phạm vi platform |
| Nguồn tạo | Platform identity subsystem | Platform orchestration/context |
| Phạm vi | Người dùng hoặc tác nhân | Organization, space, cluster, namespace, tenant metadata |
| Cách dùng | Audit, policy, mapping actor | Tenant scoping, routing, quota, ownership checks |
| Có thay thế authentication không? | Không | Không |
| Có thể thiếu không? | Có, tùy platform và request | Có thể không có hoặc có cấu trúc khác theo platform |

Không lấy tenant ID từ originating identity nếu đó là một claim người dùng có thể thay đổi. Cũng không dùng context làm bằng chứng duy nhất rằng caller sở hữu instance. Broker cần liên kết các giá trị này với platform client đã xác thực và registry tài nguyên nội bộ.

## 2. Ranh giới tin cậy từ platform đến broker

Một kiến trúc điển hình:

~~~mermaid
flowchart LR
    U["Người dùng / Workload"] --> P["Platform"]
    P -->|"TLS + platform credentials"| B["Spring Cloud Service Broker"]
    B --> A["Authentication / Authorization"]
    A --> I["Identity parser"]
    A --> C["Context resolver"]
    I --> D["Actor policy + audit"]
    C --> E["Tenant / ownership policy"]
    D --> F["Lifecycle application service"]
    E --> F
    F --> R["Provider adapter"]
~~~

Broker cần phân biệt ít nhất các lớp sau:

1. **Transport trust:** kết nối TLS và các proxy/gateway được phép đứng trước broker.
2. **Platform authentication:** xác minh platform client đang gọi broker.
3. **Originating identity:** dữ liệu actor mà platform chuyển tiếp trong header.
4. **Context validation:** kiểm tra cấu trúc và ý nghĩa của context.
5. **Resource authorization:** xác minh actor/platform được phép thao tác đúng instance hoặc binding.
6. **Provider credentials:** danh tính kỹ thuật broker dùng để gọi cloud provider hoặc Kubernetes API.

Các lớp này không được gộp thành một. Ví dụ, platform client xác thực thành công không có nghĩa user trong originating identity được quyền xóa mọi instance. Ngược lại, originating identity hợp lệ cũng không thay thế xác thực platform client.

## 3. Xác thực platform client trước khi tin dữ liệu chuyển tiếp

OSB API thường được triển khai sau một cơ chế xác thực broker-client, chẳng hạn HTTP Basic Authentication qua TLS hoặc cơ chế authentication do platform và broker thống nhất. Spring Security có thể bảo vệ các endpoint broker, xác thực credential platform và áp dụng policy cho request.

Một luồng xử lý an toàn:

1. Kết thúc TLS tại broker hoặc trusted ingress.
2. Nếu có reverse proxy, chỉ chấp nhận forwarded headers từ proxy đã được cấu hình tin cậy.
3. Xác thực platform client bằng credential hoặc cơ chế đã thỏa thuận.
4. Kiểm tra header phiên bản OSB API.
5. Parse originating identity và context sau khi xác định nguồn request.
6. Resolve tenant và resource ownership.
7. Kiểm tra quyền cho operation cụ thể.
8. Chỉ sau đó mới gọi application service và provider adapter.

Không cho phép client bên ngoài gọi trực tiếp broker với một header originating identity tùy ý rồi coi đó là danh tính đã xác thực. Nếu kiến trúc cho phép request đi qua nhiều gateway, phải xác định gateway nào có quyền thêm hoặc thay header này, và ingress nào sẽ loại bỏ header giả từ phía client.

Không ghi credential Basic Auth, access token hoặc client secret vào log. TLS bảo vệ dữ liệu trên đường truyền; nó không thay thế authorization ở tầng ứng dụng.

## 4. Định dạng và cách xử lý X-Broker-API-Originating-Identity

Header **X-Broker-API-Originating-Identity** được dùng để platform chuyển tiếp thông tin về actor khởi tạo request. Định dạng OSB API sử dụng tên platform và payload JSON được Base64 encode, thường có dạng:

~~~http
X-Broker-API-Originating-Identity: cloudfoundry eyJ1c2VyX2lkIjoi...
~~~

Phần trước dấu phân cách cho biết platform; phần sau là Base64 representation của JSON identity payload. Cấu trúc cụ thể của payload phụ thuộc platform. Ví dụ Cloud Foundry có thể chuyển user GUID hoặc các claim identity mà platform hỗ trợ.

Base64 chỉ là encoding, không phải encryption, chữ ký số hoặc bằng chứng chống giả mạo. Nếu bất kỳ client nào có thể gửi header này trực tiếp đến broker, họ có thể tự tạo payload. Broker chỉ nên xem header là platform assertion khi request đến từ platform đã xác thực và kiến trúc mạng bảo đảm client không thể giả mạo header được platform tin cậy.

### 4.1. Decode có kiểm soát

Khi parse header, broker nên:

- Giới hạn tổng độ dài header và payload sau decode.
- Kiểm tra tên platform thuộc danh sách adapter được hỗ trợ.
- Decode Base64 theo đúng format; từ chối payload malformed.
- Parse JSON với giới hạn độ sâu và kích thước.
- Chỉ nhận các claim cần thiết theo platform adapter.
- Kiểm tra kiểu dữ liệu, định dạng và giới hạn độ dài của từng claim.
- Không thực thi nội dung hoặc dùng claim làm đường dẫn, URL hay câu lệnh.
- Không log toàn bộ payload nếu có PII hoặc dữ liệu nhạy cảm.

Nếu header không có, broker cần có policy rõ: dùng platform service identity cho audit, yêu cầu header cho một số operation, hoặc từ chối khi sản phẩm yêu cầu actor cụ thể. Không tự suy đoán người dùng từ parameters hoặc context.

### 4.2. Ví dụ payload identity

Ví dụ minh họa payload JSON sau khi decode:

~~~json
{
  "user_id": "user-8f2a",
  "username": "phuong",
  "email": "user@example.invalid"
}
~~~

Các field chỉ là ví dụ, không phải schema chung bắt buộc của mọi platform. Broker không nên giả định mọi platform đều gửi username hoặc email. Hãy dùng platform adapter để chuyển payload thành mô hình nội bộ với các trường tùy chọn và nguồn gốc rõ ràng.

Ví dụ model nội bộ:

~~~java
public record OriginatingActor(
    String platform,
    String subjectId,
    String username,
    String email,
    String identitySource
) {}
~~~

Nếu không có email hoặc username, subject ID vẫn có thể đủ để audit. Tránh dùng email làm khóa ổn định nếu platform cung cấp một subject identifier không thay đổi.

## 5. Context trong request OSB API

Context là object platform gửi trong request để mô tả môi trường mà service instance hoặc binding thuộc về. Tùy platform, context có thể chứa:

- Platform name hoặc platform instance.
- Organization, space hoặc project identifiers.
- Cluster và namespace.
- Tenant hoặc account reference.
- Metadata về application/workload.
- Các thuộc tính phục vụ routing hoặc policy tích hợp.

Ví dụ context theo một integration Cloud Foundry:

~~~json
{
  "platform": "cloudfoundry",
  "organization_guid": "org-42",
  "space_guid": "space-payments"
}
~~~

Ví dụ context của một integration Kubernetes:

~~~json
{
  "platform": "kubernetes",
  "cluster": "prod-cluster-a",
  "namespace": "payments",
  "tenant_ref": "tenant-42"
}
~~~

Đây là ví dụ platform context; không phải mọi platform gửi cùng key hoặc cùng cấu trúc. Broker nên có adapter riêng để parse context theo platform, sau đó ánh xạ về mô hình tenant và deployment nội bộ.

Context không phải nơi gửi password, access token, private key hoặc credential provider. Nếu context có dữ liệu nhạy cảm ngoài dự kiến, broker cần từ chối hoặc loại bỏ theo policy, đồng thời tránh log raw body.

## 6. Context không phải authorization claim

Một request có thể chứa:

~~~json
{
  "context": {
    "platform": "kubernetes",
    "namespace": "payments",
    "tenant_ref": "tenant-42"
  }
}
~~~

Các giá trị này giúp broker xác định phạm vi request, nhưng không chứng minh caller có quyền trên tenant-42. Một client có thể thử thay namespace hoặc tenant_ref để truy cập tài nguyên của tenant khác nếu broker tin JSON trực tiếp.

Broker nên thực hiện các bước:

1. Xác thực platform client.
2. Resolve platform/cluster từ cấu hình trust đã biết, không chỉ từ chuỗi do caller gửi.
3. Ánh xạ context vào tenant registry.
4. Tải instance hoặc binding theo ID.
5. So sánh tenant owner đã lưu với tenant được resolve từ context.
6. Kiểm tra actor/platform có quyền thực hiện operation.
7. Từ chối nếu có mismatch hoặc context không thuộc platform đã xác thực.

Một rule quan trọng: **resource ownership đã được lưu trong broker là nguồn dữ liệu chuẩn cho quyền sở hữu**. Context request là bằng chứng bổ sung để xác minh scope hiện tại. Không tự đổi owner chỉ vì context mới chứa tenant ID khác.

## 7. Lưu context và bảo vệ tính nhất quán của ownership

Khi provision thành công, broker nên lưu snapshot context cần thiết cùng service instance. Khi tạo binding, broker có thể lưu context hoặc consumer identity liên quan tới binding. Những dữ liệu này giúp broker xác minh request sau, thực hiện audit và đối soát tenant.

Một record instance có thể gồm:

| Field | Mục đích |
|---|---|
| **instance_id** | Định danh service instance từ platform |
| **tenant_id** | Tenant nội bộ đã resolve và xác minh |
| **platform_type** | Loại platform adapter |
| **platform_instance_id** | Định danh platform/cluster đã được trust |
| **organization_id / space_id** | Scope platform nếu có |
| **cluster_id / namespace** | Scope Kubernetes nếu có |
| **context_snapshot** | Phần context đã chuẩn hóa và được phép lưu |
| **created_by_subject** | Actor subject ID nếu platform cung cấp |
| **created_at** | Thời điểm tạo |

Không cần lưu toàn bộ raw context nếu chỉ một số field có ý nghĩa. Lưu dữ liệu tối thiểu cần thiết, có retention và access policy. Nếu cần giữ raw payload để audit hoặc điều tra, hãy mã hóa, giới hạn quyền truy cập và loại bỏ secret/PII không cần thiết.

Tenant ownership không nên thay đổi theo cách ghi đè context. Nếu sản phẩm hỗ trợ chuyển instance giữa tenant, hãy thiết kế một workflow riêng có authorization, kiểm tra quota hai phía, audit và migration dữ liệu.

## 8. Context update và allow_context_updates

Một số phiên bản OSB API hỗ trợ capability **allow_context_updates** trong service definition để broker cho biết nó có chấp nhận cập nhật context trong update service instance hay không.

Chỉ công bố capability này khi broker có semantics rõ ràng và implementation thực sự xử lý context update. Khi capability không được hỗ trợ hoặc là false, broker không nên âm thầm nhận một context mới rồi thay owner hoặc routing metadata.

Khi hỗ trợ, cần phân biệt:

- Context không được gửi: giữ snapshot đã lưu theo policy.
- Context được gửi lại với giá trị tương đương: không tạo thay đổi sở hữu.
- Context có metadata bổ sung được phép cập nhật: merge theo allowlist và lưu audit.
- Context thay đổi cluster/namespace hoặc tenant scope: yêu cầu policy riêng; không mặc định cho phép.
- Context mâu thuẫn với owner hoặc platform đã xác thực: từ chối.

Ví dụ request update:

~~~json
{
  "service_id": "service-postgresql",
  "plan_id": "plan-standard",
  "context": {
    "platform": "kubernetes",
    "cluster": "prod-cluster-a",
    "namespace": "payments"
  },
  "parameters": {
    "backup_enabled": true
  }
}
~~~

Context trong update phải được đối chiếu với snapshot đã lưu. Nếu chỉ namespace đổi, broker cần xác định đó là metadata refresh, thay đổi workload placement hay một yêu cầu chuyển ownership. Không dùng một phép merge JSON chung cho mọi field.

## 9. Phân biệt context với bind_resource và parameters

OSB request có thể có nhiều object chứa dữ liệu platform hoặc caller. Broker cần hiểu đúng mục đích:

| Trường | Vai trò | Ví dụ |
|---|---|---|
| **context** | Môi trường và scope do platform cung cấp | organization, space, cluster, namespace |
| **bind_resource** | Thông tin resource consumer cần cho binding | app GUID, route hoặc workload reference |
| **parameters** | Cấu hình service/binding do caller gửi theo schema | role, storage, backup |
| **X-Broker-API-Originating-Identity** | Actor do platform chuyển tiếp qua header | user subject, username |
| **service_id / plan_id** | Offering và plan được chọn | PostgreSQL, standard |

Không lấy app GUID trong bind_resource làm bằng chứng duy nhất cho user identity. Không coi parameters.role là quyền đã được xác thực. Broker cần resolve consumer và permission profile bằng policy, đối chiếu context và authenticated platform.

Một ví dụ binding request:

~~~json
{
  "service_id": "service-postgresql",
  "plan_id": "plan-standard",
  "context": {
    "platform": "cloudfoundry",
    "organization_guid": "org-42",
    "space_guid": "space-payments"
  },
  "bind_resource": {
    "app_guid": "app-billing"
  },
  "parameters": {
    "role": "read_write"
  }
}
~~~

Broker kiểm tra app thuộc scope hợp lệ, caller có quyền bind, role nằm trong tập policy cho phép và instance thuộc đúng tenant. Không chỉ vì request gửi role read_write mà broker tự cấp quyền đó.

## 10. Trust boundary qua reverse proxy và gateway

Nhiều broker chạy phía sau ingress, API gateway hoặc load balancer. Các proxy có thể thêm header như X-Forwarded-For, X-Forwarded-Proto hoặc chuyển tiếp originating identity. Nếu broker tin mọi header từ mọi nguồn, attacker có thể giả địa chỉ IP, scheme hoặc actor.

Một số nguyên tắc:

- Chỉ tin forwarded headers từ IP/network hoặc identity của proxy được cấu hình.
- Ingress cần loại bỏ header originating identity do client tự gửi trước khi platform assertion được thêm.
- Không expose broker trực tiếp ra Internet nếu chỉ dự định nhận traffic từ platform.
- Dùng network policy/firewall hoặc mTLS giữa platform/ingress và broker khi phù hợp.
- Không dùng X-Forwarded-For làm actor identity.
- Xác định proxy nào chịu trách nhiệm ghi đè header và kiểm tra chuỗi proxy.
- Giới hạn request size và header size.
- Ghi lại nguồn kết nối theo metadata đã được ingress xác thực, không tin giá trị client tự khai.

Nếu broker dùng Spring Boot forwarded-header support, cấu hình phải khớp với topology proxy. Không bật trust tất cả forwarded headers trong môi trường mà client có thể gọi trực tiếp ứng dụng.

## 11. Identity propagation xuống provider

Broker thường dùng service account hoặc cloud credential riêng để gọi provider. Danh tính người dùng từ originating identity không nên được chuyển thẳng thành credential provider nếu chưa có cơ chế delegation được thiết kế rõ.

Có ba mô hình phổ biến:

| Mô hình | Cách hoạt động | Điều cần kiểm soát |
|---|---|---|
| Broker service identity | Broker gọi provider bằng service account của mình | Broker thực hiện authorization và audit actor ở application layer |
| Delegated identity | Platform cấp token có thể trao đổi hoặc delegate theo user | Audience, scope, expiry và token exchange |
| Per-tenant provider identity | Mỗi tenant có credential/role riêng | Mapping tenant, secret rotation và least privilege |

Không gửi raw originating identity header tới provider như một access token. Header đó là metadata nhận dạng, không nhất thiết là token có thể dùng để xác thực với provider. Nếu cần delegated access, dùng cơ chế token exchange hoặc federation được provider hỗ trợ và giới hạn audience/scope.

Với Kubernetes, broker có thể dùng service account riêng và RBAC giới hạn namespace. Với cloud provider, dùng workload identity hoặc role theo account/project. Không dùng một credential quản trị toàn tổ chức nếu broker chỉ cần tạo database trong một project.

## 12. Các kiểu tấn công và cách phòng vệ

| Rủi ro | Cách xảy ra | Biện pháp |
|---|---|---|
| Identity spoofing | Client tự gửi header originating identity giả | Authenticate platform; ingress strip/overwrite header |
| Tenant spoofing | Client sửa tenant hoặc namespace trong context | Resolve context qua trusted platform registry và đối chiếu owner |
| Confused deputy | Broker dùng quyền provider rộng để thực hiện request trái tenant | Authorization trước provider call, tenant-scoped adapter |
| Context injection | Giá trị context được dùng trực tiếp trong SQL, command hoặc path | Validate, encode theo ngữ cảnh, dùng API có kiểu |
| SSRF/routing abuse | Context chứa URL/host do caller kiểm soát | Không dùng URL tự do; allowlist endpoint/cluster |
| PII leakage | Log toàn bộ identity payload/context | Data minimization, redaction và access control |
| Header smuggling | Proxy và broker diễn giải header khác nhau | Chuẩn hóa header tại ingress, từ chối duplicate/malformed |
| Replay | Request hợp lệ bị phát lại trong scope khác | Idempotency, resource ownership và authorization |
| Cross-tenant access | Instance ID đoán được và thiếu tenant check | Kiểm tra owner trên mọi endpoint |
| Privilege escalation | Parameters hoặc bind_resource yêu cầu role cao | Permission policy server-side và least privilege |

Base64 không bảo vệ tính toàn vẹn. TLS bảo vệ kênh truyền nhưng nếu một proxy được cấu hình sai hoặc client có thể bypass platform, header vẫn có thể bị giả. Trust cần dựa trên toàn bộ đường đi của request, không chỉ một format payload.

## 13. Thiết kế platform adapter

Để hỗ trợ Cloud Foundry, Kubernetes và các platform khác, không nên để domain service phụ thuộc trực tiếp vào tên field của từng platform.

Một adapter có thể cung cấp các chức năng:

- Parse originating identity header theo platform.
- Parse context theo schema hoặc contract platform.
- Xác định platform instance đã được trust.
- Resolve tenant nội bộ.
- Chuẩn hóa actor subject.
- Xác minh ownership và scope.
- Tạo audit metadata đã làm sạch.

Interface nội bộ minh họa:

~~~java
public interface PlatformTrustAdapter {
    boolean supports(String platformType);

    OriginatingActor resolveActor(String encodedIdentity);

    ResolvedPlatformContext resolveContext(
        Map<String, Object> context
    );

    AuthorizationScope resolveScope(
        OriginatingActor actor,
        ResolvedPlatformContext context
    );
}
~~~

Adapter Cloud Foundry có thể ánh xạ organization GUID và space GUID. Adapter Kubernetes có thể ánh xạ cluster và namespace theo cấu hình trust của broker. Cả hai đều trả về một mô hình nội bộ chung, giúp lifecycle service không phải chứa nhiều nhánh platform-specific.

Không để adapter tự quyết định mọi quyền nghiệp vụ. Adapter xác minh và chuẩn hóa nguồn; authorization policy quyết định actor đó có được thực hiện provision, update, bind hoặc deprovision trên resource cụ thể hay không.

## 14. Ánh xạ vào Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp model request cho các thao tác OSB và có thể expose originating identity cùng context theo cách phụ thuộc phiên bản thư viện. Ở tầng tích hợp, broker nên lấy dữ liệu từ request model đã parse, sau đó chuyển thành trusted request context nội bộ.

Một kiến trúc gợi ý:

| Thành phần | Trách nhiệm |
|---|---|
| Spring Security filter chain | Xác thực platform client |
| Trusted proxy configuration | Kiểm soát forwarded headers và nguồn kết nối |
| OSB request adapter | Nhận request model và header giao thức |
| Originating identity parser | Decode và validate actor assertion |
| Platform context adapter | Chuẩn hóa context theo platform |
| Tenant resolver | Ánh xạ scope platform sang tenant nội bộ |
| Authorization service | Kiểm tra quyền trên instance/binding |
| Audit service | Ghi actor, tenant, resource và quyết định |
| Provider adapter | Gọi hạ tầng bằng credential kỹ thuật được giới hạn |

Pseudocode minh họa:

~~~java
public ProvisionCommand toCommand(
        CreateServiceInstanceRequest request,
        AuthenticatedPlatform platform) {

    OriginatingActor actor =
        originatingIdentityResolver.resolve(
            request.getOriginatingIdentity(),
            platform
        );

    ResolvedPlatformContext context =
        platformContextResolver.resolve(
            request.getContext(),
            platform
        );

    TenantId tenantId = tenantResolver.requireTenant(context);

    authorization.requireCanProvision(
        platform,
        actor,
        tenantId,
        request.getServiceDefinitionId(),
        request.getPlanId()
    );

    return new ProvisionCommand(
        request.getServiceInstanceId(),
        tenantId,
        actor,
        context,
        request.getServiceDefinitionId(),
        request.getPlanId(),
        request.getParameters()
    );
}
~~~

Đây là pseudocode mô tả trách nhiệm, không khẳng định getter hoặc kiểu request giống nhau ở mọi phiên bản Spring Cloud Open Service Broker. Hãy đối chiếu API model của dependency đang sử dụng. Nếu originating identity không có trong request model hoặc được expose qua một abstraction khác, lấy từ extension point chính thức của thư viện và giữ cùng quy tắc trust.

### 14.1. Không đặt authorization chỉ trong controller

Mọi use case có thể được gọi từ handler khác, worker hoặc tác vụ nội bộ. Vì vậy, authorization cần được thực hiện trong application service/domain policy với trusted actor và tenant scope đã chuẩn hóa.

Worker bất đồng bộ phải lưu actor/tenant context tối thiểu cùng operation để audit và thực hiện policy cần thiết. Không serialize raw HTTP request hoặc access token vào queue. Worker nên nhận command đã chuẩn hóa và tham chiếu tới dữ liệu cần thiết từ store an toàn.

### 14.2. Lưu audit có nguồn gốc

Một audit event có thể có:

~~~json
{
  "event_type": "service_instance.provision",
  "actor_platform": "cloudfoundry",
  "actor_subject": "user-8f2a",
  "tenant_id": "tenant-42",
  "instance_id": "instance-7f3a",
  "decision": "ALLOW",
  "correlation_id": "req-991a",
  "timestamp": "2026-11-27T10:30:00Z"
}
~~~

Không đưa email, raw identity payload, access token hoặc context đầy đủ vào audit nếu không cần. Audit nên cho biết ai đã thực hiện hành động, trên tài nguyên nào, theo tenant nào và quyết định ra sao. Quyền đọc audit phải được giới hạn và có retention phù hợp.

## 15. Chính sách khi identity hoặc context thiếu và không hợp lệ

Không phải platform nào cũng gửi cùng dữ liệu. Broker cần phân loại tình huống:

| Tình huống | Hành vi gợi ý |
|---|---|
| Originating identity hợp lệ | Chuẩn hóa actor và dùng cho audit/policy |
| Originating identity không có | Dùng platform service identity hoặc từ chối theo yêu cầu sản phẩm |
| Originating identity malformed | Từ chối request theo contract; không fallback sang actor tự suy đoán |
| Platform type không được hỗ trợ | Từ chối hoặc dùng adapter được cấu hình rõ |
| Context hợp lệ và khớp owner | Tiếp tục authorization |
| Context thiếu field tùy chọn | Dùng policy mặc định đã định nghĩa |
| Context thiếu tenant scope bắt buộc | Từ chối vì không thể xác định ownership |
| Context không khớp tenant owner | Từ chối và ghi audit security event |
| Context có field lạ | Bỏ qua hoặc từ chối theo schema/compatibility policy; không dùng field lạ cho quyết định bảo mật |
| Context thay đổi trong update | Chỉ xử lý theo allow_context_updates và policy đã công bố |

Không fallback từ context không hợp lệ sang tenant mặc định. Điều đó có thể làm request của một tenant bị xử lý dưới quyền của tenant khác.

## 16. Kiểm thử trust boundary

Kiểm thử cần bao phủ header, context, proxy và authorization ở nhiều lớp.

| Nhóm | Trường hợp | Kết quả mong đợi |
|---|---|---|
| Platform authentication | Credential platform sai | Request bị từ chối trước business side effect |
| Originating identity | Header hợp lệ từ platform tin cậy | Actor được chuẩn hóa đúng |
| Spoofing | Client gửi header giả qua ingress | Ingress loại bỏ hoặc broker từ chối |
| Base64 | Payload malformed | Không parse hoặc authorize bằng dữ liệu lỗi |
| JSON payload | Payload quá lớn/độ sâu bất thường | Bị giới hạn an toàn |
| Unknown platform | Platform type ngoài allowlist | Từ chối theo policy |
| Missing identity | Platform không gửi header | Dùng policy đã định nghĩa, không suy đoán actor |
| Context ownership | Tenant context khớp instance owner | Authorization tiếp tục |
| Tenant mismatch | Context trỏ tenant khác owner | Từ chối, không gọi provider |
| Context injection | Namespace hoặc URL chứa giá trị độc hại | Không tạo path/URL/command tùy ý |
| Context update | Capability không cho phép thay đổi | Từ chối thay đổi context |
| Cross-tenant ID | Caller đoán instance ID tenant khác | Không truy cập resource |
| Provider identity | Broker dùng role thiếu quyền | Provider call bị giới hạn đúng scope |
| Audit | Request chứa PII/secret | Audit không ghi dữ liệu nhạy cảm |
| Async worker | Worker chạy sau HTTP request kết thúc | Dùng actor/tenant snapshot an toàn, không dùng token hết hạn |

Một integration test quan trọng là gửi request với platform credential hợp lệ nhưng context tenant sai. Kết quả phải bị từ chối trước khi provider adapter được gọi. Một test khác gửi originating identity giả qua đường truy cập không đi qua platform; broker không được tin payload đó.

## 17. Checklist triển khai

Trước khi phát hành tích hợp identity và context, hãy xác nhận:

- [ ] Platform client được xác thực qua TLS và cơ chế credential đã thỏa thuận.
- [ ] Originating identity được xem là platform assertion, không phải credential tự xác thực.
- [ ] Ingress loại bỏ hoặc ghi đè header originating identity do client tự gửi.
- [ ] Header được parse theo đúng format và platform adapter.
- [ ] Base64/JSON có giới hạn kích thước, độ sâu và kiểu dữ liệu.
- [ ] Context được validate theo platform-specific schema/allowlist.
- [ ] Tenant được resolve qua registry và gắn với authenticated platform scope.
- [ ] Resource owner trong broker là nguồn chuẩn để authorization.
- [ ] Mọi endpoint instance và binding đều kiểm tra tenant ownership.
- [ ] Context không được dùng làm secret store hoặc lệnh provider.
- [ ] Context update chỉ được chấp nhận khi capability và policy cho phép.
- [ ] Bind resource, parameters và originating identity được xử lý riêng.
- [ ] Provider adapter dùng service identity/delegation có scope tối thiểu.
- [ ] Worker async chỉ nhận trusted command và tham chiếu an toàn.
- [ ] Audit lưu actor, tenant, resource và decision nhưng không lưu secret/PII thừa.
- [ ] Có test spoofing, malformed header, tenant mismatch, cross-tenant access và proxy trust.

Originating identity và context giúp broker hiểu ai khởi tạo request và request thuộc môi trường nào. Chúng chỉ trở thành dữ liệu đáng tin khi được tiếp nhận qua platform đã xác thực, parse theo adapter được kiểm soát và đối chiếu với resource ownership đã lưu. Khi Spring Cloud Service Broker tách authentication, identity resolution, context resolution, authorization và provider identity thành các lớp rõ ràng, broker tránh được identity spoofing, tenant confusion và confused-deputy trong môi trường nhiều platform.
