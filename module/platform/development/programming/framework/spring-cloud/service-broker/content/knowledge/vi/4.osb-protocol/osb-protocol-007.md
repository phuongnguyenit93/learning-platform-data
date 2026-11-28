# Trường context và dữ liệu riêng của từng nền tảng

Một service broker theo Open Service Broker API (OSB API) có thể nhận yêu cầu từ nhiều nền tảng. Mỗi nền tảng có cách biểu diễn tổ chức, không gian triển khai, namespace, ứng dụng và danh tính riêng. Trường `context` giúp nền tảng chuyển một phần thông tin môi trường đó cho broker để broker hiểu yêu cầu đang được thực hiện trong phạm vi nào.

Trong module `SPRING_CLOUD_SERVICE_BROKER`, context là đầu vào quan trọng để xác định chính sách cấp phát, ánh xạ khách hàng (tenant), ghi nhận quyền sở hữu service instance và tạo binding cho đúng consumer. Broker cần hiểu cấu trúc context theo hợp đồng của nền tảng tích hợp, đồng thời chuẩn hóa nó thành mô hình nội bộ ổn định. Context không thay thế xác thực, phân quyền hoặc dữ liệu cấu hình dịch vụ.

## 1. Context là gì trong OSB API?

`context` là một đối tượng JSON chứa thông tin ngữ cảnh do nền tảng gửi cùng request OSB API khi schema của thao tác hỗ trợ trường này. Nội dung thường mô tả nền tảng và phạm vi mà yêu cầu phát sinh, chẳng hạn nền tảng nào đang gọi, tổ chức hoặc không gian nào đang sở hữu service instance, hay thông tin môi trường mà broker cần để áp dụng chính sách.

Một context có thể chứa các nhóm thông tin như:

- **Platform identity hint:** tên hoặc loại nền tảng tích hợp, ví dụ Cloud Foundry hoặc một adapter chạy trên Kubernetes.
- **Platform scope:** organization, space, namespace, project, cluster hoặc workspace do nền tảng quản lý.
- **Resource ownership hint:** thông tin giúp xác định nhóm hoặc tài khoản sở hữu yêu cầu.
- **Consumer context:** thông tin về ứng dụng hoặc workload cần liên kết với service, tùy thao tác và cách nền tảng tích hợp.
- **Platform metadata:** nhãn hoặc thuộc tính phục vụ policy, audit và tích hợp, nếu chúng được định nghĩa trong hợp đồng.

Các trường cụ thể phụ thuộc nền tảng và phiên bản tích hợp. OSB API không yêu cầu mọi nền tảng phải gửi cùng một bộ thuộc tính nghiệp vụ. Vì vậy, broker nên xem context là dữ liệu có cấu trúc nhưng có nguồn gốc theo platform, không giả định mọi request đều có `organization_guid`, `namespace` hay một trường tên cố định nào đó.

Context thường có dạng JSON object. Ví dụ minh họa:

~~~json
{
  "platform": "cloudfoundry",
  "organization_guid": "org-8f21",
  "space_guid": "space-a912",
  "organization_name": "commerce",
  "space_name": "production"
}
~~~

Đây là ví dụ về một hợp đồng context cụ thể, không phải danh sách field bắt buộc cho mọi broker. Broker cần dựa trên tài liệu của platform client thực tế để xác định field nào được gửi, field nào ổn định và field nào chỉ có ý nghĩa hiển thị.

## 2. Phân biệt context với parameters và bind_resource

Một request OSB có thể chứa nhiều object hoặc định danh cùng lúc. Nếu gộp chúng thành một khái niệm chung, broker dễ dùng nhầm dữ liệu cấu hình làm dữ liệu định danh hoặc bỏ qua ranh giới tin cậy.

| Thành phần | Nguồn và mục đích | Ví dụ | Cách broker sử dụng |
|---|---|---|---|
| `context` | Thông tin môi trường do platform cung cấp | Platform, organization, space, namespace | Phân giải platform scope, tenant và policy |
| `parameters` | Tham số cấu hình do người dùng hoặc client gửi cho dịch vụ | Số GB lưu trữ, database name, retention days | Validate theo schema và giới hạn của service/plan |
| `bind_resource` | Thông tin tài nguyên consumer liên quan đến một binding | App GUID, route hoặc thông tin bind resource | Xác định consumer hoặc cách cấp quyền cho binding |
| `service_id` | Định danh service trong catalog | `svc-postgresql` | Chọn service definition |
| `plan_id` | Định danh plan thuộc service | `plan-postgresql-standard` | Chọn cấu hình dịch vụ |
| `instance_id` | Định danh instance trong đường dẫn API | `orders-db-prod` | Tìm và quản lý service instance |
| `binding_id` | Định danh binding trong đường dẫn API | `orders-api-binding` | Tìm và quản lý quyền truy cập của consumer |

### Context không phải tham số cấu hình

Giả sử người dùng muốn tạo database tên `orders` với dung lượng 100 GB. `database_name` và `storage_gb` là tham số cấu hình của dịch vụ, do đó thuộc `parameters`. Organization hoặc namespace mà platform gắn với yêu cầu là context. Nếu broker lấy `tenant_id` từ `parameters`, caller có thể thử thay đổi giá trị đó để tạo tài nguyên trong tenant khác.

### Context không phải bằng chứng xác thực

Một request có thể chứa:

~~~json
{
  "context": {
    "platform": "cloudfoundry",
    "organization_guid": "org-8f21"
  }
}
~~~

Giá trị `platform` trong JSON chỉ là dữ liệu request. Broker không được coi nó là bằng chứng caller thực sự là Cloud Foundry. Danh tính platform phải được xác thực qua cơ chế kết nối đã cấu hình, chẳng hạn credential riêng, mutual TLS hoặc gateway tin cậy. Sau khi xác thực, broker mới dùng context để phân giải phạm vi tổ chức và tenant.

### Context của provision và context của binding

Context trong yêu cầu provision thường giúp xác định môi trường sở hữu instance. Context trong yêu cầu bind, nếu được platform gửi, có thể cung cấp thêm thông tin về phạm vi hoặc consumer thực hiện binding. Hai context này có mục đích liên quan nhưng không nhất thiết giống nhau.

Broker cần lưu quan hệ sở hữu instance từ lúc provision. Khi bind, broker kiểm tra consumer và binding có được phép sử dụng instance đó hay không. Không nên lấy context mới của binding để âm thầm thay đổi tenant sở hữu instance.

## 3. Dữ liệu riêng của Cloud Foundry

Cloud Foundry tổ chức ứng dụng trong các organization và space. Khi tích hợp một broker, platform có thể gửi context chứa định danh organization/space và các metadata liên quan để broker biết yêu cầu phát sinh từ đâu.

Một ví dụ minh họa:

~~~json
{
  "context": {
    "platform": "cloudfoundry",
    "organization_guid": "org-8f21",
    "space_guid": "space-a912",
    "organization_name": "commerce",
    "space_name": "production"
  }
}
~~~

Broker có thể ánh xạ cặp organization/space của một Cloud Foundry foundation đã xác thực thành platform scope và tenant nội bộ. Ví dụ:

| Dữ liệu từ Cloud Foundry | Ý nghĩa có thể dùng | Mô hình nội bộ |
|---|---|---|
| Foundation hoặc platform registration | Nền tảng Cloud Foundry cụ thể | `platform_id` |
| Organization GUID | Định danh organization trên foundation | `organization_ref` |
| Space GUID | Định danh space trong organization | `platform_scope_id` |
| Organization/space name | Tên hiển thị hoặc metadata | Thuộc tính mô tả, không dùng làm khóa chính |

Tên organization hoặc space có thể được đổi. GUID cũng chỉ duy nhất trong phạm vi nền tảng tương ứng. Vì vậy, không nên dùng tên hiển thị hoặc GUID đơn lẻ làm định danh toàn cục. Khóa ánh xạ cần bao gồm platform đã xác thực.

Trong các phiên bản hoặc profile OSB API cũ, request có thể có những trường cấp cao nhất như `organization_guid` và `space_guid`. Các trường này được xem là dạng tương thích cũ trong những phiên bản API đã chuyển sang sử dụng context. Khi triển khai broker, cần xác định rõ phiên bản API và hành vi của Cloud Foundry client đang kết nối; nếu phải hỗ trợ field cũ, hãy chuyển chúng qua cùng một lớp chuẩn hóa và phát hiện trường hợp dữ liệu cũ mâu thuẫn với context.

Broker không nên giả định organization hoặc space là tenant theo quan hệ một-một. Một khách hàng có thể có nhiều organization/space; một organization hoặc space cũng có thể được ánh xạ theo mô hình hợp đồng khác. Quy tắc ánh xạ cần do hệ thống quản trị tenant xác định.

## 4. Dữ liệu riêng của Kubernetes và adapter OSB

Kubernetes sử dụng các khái niệm như cluster, namespace, workload, service account và project do hệ sinh thái quản trị cung cấp. Tuy nhiên, Kubernetes core không tự động định nghĩa một bộ context OSB thống nhất cho mọi client. Nếu một service catalog, controller hoặc adapter tương thích OSB gọi broker, thành phần tích hợp đó quyết định cách biểu diễn thông tin Kubernetes trong request.

Ví dụ minh họa một hợp đồng riêng của adapter:

~~~json
{
  "context": {
    "platform": "kubernetes",
    "cluster_id": "cluster-prod-a",
    "namespace": "orders",
    "project_id": "commerce-team",
    "controller_id": "osb-controller-prod"
  }
}
~~~

Broker có thể chuẩn hóa dữ liệu trên như sau:

| Field ví dụ | Ý nghĩa | Kiểm tra cần thiết |
|---|---|---|
| `cluster_id` | Cluster phát sinh request | Cluster phải thuộc platform registration đã xác thực |
| `namespace` | Namespace mà workload hoạt động | Namespace phải được ánh xạ trong cluster đó |
| `project_id` | Project hoặc nhóm sở hữu theo quy ước của tổ chức | Phải được đối chiếu với tenant mapping |
| `controller_id` | Thành phần điều khiển gửi request | Chỉ chấp nhận nếu được đăng ký và xác thực |

Không nên lấy riêng tên namespace làm tenant ID. Hai cluster khác nhau có thể cùng có namespace `orders`; một cluster cũng có thể được chia sẻ bởi nhiều khách hàng. Khóa scope nên kết hợp cluster hoặc platform registration với namespace và ánh xạ tenant do broker quản lý.

Khi Kubernetes integration sử dụng Service Binding Specification, operator hoặc controller riêng, cần phân biệt đối tượng binding của Kubernetes với service binding trong OSB API. Thành phần adapter chịu trách nhiệm chuyển đổi mô hình và truyền context theo hợp đồng đã chọn. Không nên giả định mọi Kubernetes cluster đều có sẵn một client OSB hoặc gửi cùng các field context.

## 5. Chuẩn hóa context thành mô hình nội bộ

Các handler OSB không nên chứa nhiều nhánh như “nếu Cloud Foundry thì đọc field A, nếu Kubernetes thì đọc field B”. Hãy đặt logic đọc và chuyển đổi context trong một thành phần chuyên trách, ví dụ platform context resolver.

Mô hình nội bộ có thể gồm:

- `platform_id`: platform registration đã được xác thực.
- `platform_scope_id`: phạm vi tổ chức hoặc môi trường đã chuẩn hóa.
- `tenant_id`: khách hàng nội bộ sở hữu tài nguyên.
- `consumer_id`: ứng dụng hoặc workload, nếu thao tác cần xác định consumer.
- `attributes`: tập metadata đã được cho phép sử dụng.
- `context_schema_version`: phiên bản quy tắc diễn giải context.
- `raw_context_reference`: tham chiếu đến bản context đã lọc nếu cần lưu để audit hoặc điều tra.

Ví dụ kiểu dữ liệu Java ở tầng nghiệp vụ:

~~~java
public record ResolvedPlatformContext(
    String platformId,
    String platformScopeId,
    String tenantId,
    String consumerId,
    String schemaVersion
) {}
~~~

Đây là mô hình nội bộ minh họa; có thể thay đổi theo cấu trúc ứng dụng. Điểm quan trọng là các service nghiệp vụ sử dụng định danh đã chuẩn hóa thay vì tự đọc các field platform-specific.

Một resolver có thể thực hiện quy trình:

~~~java
ResolvedPlatformContext resolve(
        AuthenticatedPlatform platform,
        Map<String, Object> context) {

    // 1. Chọn parser theo platform đã xác thực.
    PlatformContextParser parser = parsers.get(platform.platformId());

    // 2. Kiểm tra cấu trúc và lấy platform scope ổn định.
    PlatformScopeReference scope = parser.parseScope(context);

    // 3. Đối chiếu scope với mapping đã đăng ký.
    TenantMapping mapping = tenantMappingRepository
        .findActive(platform.platformId(), scope)
        .orElseThrow(UnknownPlatformScopeException::new);

    // 4. Trả về định danh nội bộ đã được xác minh.
    return new ResolvedPlatformContext(
        platform.platformId(),
        mapping.platformScopeId(),
        mapping.tenantId(),
        parser.consumerId(context),
        parser.schemaVersion()
    );
}
~~~

Đoạn mã mô tả cấu trúc xử lý ở tầng ứng dụng, không phải API cố định của Spring Cloud Service Broker. Trong triển khai thật, cần bổ sung kiểm tra null, kiểu dữ liệu, kích thước payload, quyền truy cập và xử lý lỗi phù hợp.

### Trình tự xử lý request

Một request có context nên được xử lý theo thứ tự:

1. Xác thực kết nối và principal của platform.
2. Kiểm tra request theo schema OSB API.
3. Chọn parser theo platform principal đã xác thực.
4. Phân tích context và kiểm tra các field bắt buộc theo hợp đồng tích hợp.
5. Tra cứu mapping platform scope sang tenant nội bộ.
6. Kiểm tra tenant, entitlement, quota và quyền thao tác.
7. Gắn `ResolvedPlatformContext` vào execution context của nghiệp vụ.
8. Ghi nhận ownership vào instance, binding hoặc operation tương ứng.

Nếu context thiếu field bắt buộc, chứa giá trị sai kiểu hoặc không ánh xạ được sang tenant hợp lệ, broker cần từ chối request theo quy tắc lỗi OSB API. Không tự tạo mapping mới trong luồng provision chỉ vì một namespace hoặc organization chưa được nhận diện.

## 6. Sử dụng context trong các thao tác vòng đời

### Provision

Provision tạo service instance mới. Context giúp broker xác định tenant và platform scope sở hữu instance. Broker nên lưu các định danh đã chuẩn hóa cùng service ID, plan ID và resource reference.

Ví dụ request rút gọn:

~~~json
{
  "service_id": "svc-postgresql",
  "plan_id": "plan-postgresql-standard",
  "context": {
    "platform": "cloudfoundry",
    "organization_guid": "org-8f21",
    "space_guid": "space-a912"
  },
  "parameters": {
    "database_name": "orders",
    "storage_gb": 100
  }
}
~~~

Trước khi gọi backend, broker xác minh caller, ánh xạ context, kiểm tra tenant được phép dùng plan và xác nhận quota. Khi lưu instance, cần lưu `platform_id`, `tenant_id`, `platform_scope_id` cùng các định danh OSB.

### Retrieve và kiểm tra trạng thái

Khi nền tảng truy vấn instance, broker phải tìm instance trong đúng phạm vi ownership. Nếu hai platform tạo cùng một chuỗi `instance_id`, truy vấn từ platform A không được trả về instance của platform B.

Việc tra cứu nên dùng định danh đã xác thực từ request hiện tại và ownership đã lưu trong instance. Không dựa vào tên organization hoặc namespace gửi lại trong một request bất kỳ để tìm kiếm toàn cục.

### Update và deprovision

Update và deprovision phải kiểm tra quyền trên instance đã tồn tại. Broker không nên phụ thuộc vào việc platform gửi lại đầy đủ context ban đầu ở mọi request vòng đời. Bản ghi instance đã lưu là nguồn dữ liệu chính về tenant và platform scope sở hữu tài nguyên; thông tin request hiện tại chỉ được dùng để kiểm tra bổ sung theo hợp đồng.

Khi platform hoặc tenant mapping bị vô hiệu hóa, broker cần có chính sách rõ ràng cho tài nguyên hiện hữu: cho phép thu hồi để dọn dẹp, khóa các thao tác tạo mới, hoặc yêu cầu quy trình quản trị. Không xóa mapping theo cách khiến broker mất khả năng xác định chủ sở hữu của instance đang tồn tại.

### Bind

Bind tạo quyền truy cập cho một consumer. Context trong bind request có thể giúp xác định platform scope hoặc môi trường của consumer. Broker cần kiểm tra instance thuộc tenant nào, consumer có thuộc phạm vi được phép không và binding ID đã được sử dụng hay chưa.

Một binding nên lưu ownership và consumer identity riêng. Nếu một instance thuộc tenant A nhưng context binding ánh xạ sang tenant B, broker phải từ chối. Nếu cùng tenant nhưng consumer nằm trong một scope khác, quyết định cho phép cần dựa trên policy chia sẻ tài nguyên được định nghĩa rõ ràng.

### Unbind

Unbind thu hồi quyền của một binding. Broker tìm binding theo instance, binding ID và ownership đã lưu. Việc unbind không được xóa hoặc thay đổi tenant ownership của instance. Context thiếu trong request unbind không nên làm broker mất khả năng thu hồi credential nếu caller đã được xác thực và binding được định danh hợp lệ.

## 7. Lưu trữ context và dữ liệu ownership

Không nhất thiết phải lưu nguyên vẹn mọi field context trong mọi bảng. Nên tách dữ liệu định danh chuẩn hóa khỏi metadata tùy chọn.

Một mô hình lưu trữ tham khảo:

| Bản ghi | Trường gợi ý | Mục đích |
|---|---|---|
| Platform registration | `platform_id`, credential reference, trạng thái | Nhận diện caller đã đăng ký |
| Tenant mapping | `platform_id`, external scope key, `tenant_id`, trạng thái | Ánh xạ platform scope sang tenant |
| Service instance | `instance_id`, `platform_id`, `tenant_id`, `platform_scope_id`, `service_id`, `plan_id` | Lưu ownership và lựa chọn dịch vụ |
| Binding | `binding_id`, `instance_id`, `tenant_id`, `consumer_id`, `secret_ref` | Lưu quan hệ consumer và quyền truy cập |
| Operation | `operation_id`, resource key, `tenant_id`, trạng thái | Theo dõi công việc bất đồng bộ |
| Context audit | `schema_version`, filtered attributes, timestamp | Hỗ trợ audit và diễn giải dữ liệu cũ |

Khóa duy nhất cần phản ánh phạm vi thực tế. Ví dụ, nếu instance ID chỉ duy nhất trong một platform, có thể dùng unique key gồm `platform_id` và `instance_id`; nếu broker cho phép cùng platform có các tenant scope độc lập dùng chung ID, khóa cần bao gồm thêm `tenant_id` hoặc một internal resource ID. Quy tắc chính xác phải thống nhất với hợp đồng OSB API và cách platform tạo ID.

Context có thể thay đổi theo thời gian. Organization có thể đổi tên, namespace có thể được tái tạo, platform có thể nâng cấp adapter. Vì vậy:

- Lưu ID ổn định làm khóa quan hệ; giữ tên hiển thị như metadata.
- Lưu phiên bản schema hoặc phiên bản parser đã dùng để diễn giải context.
- Chỉ lưu các field cần cho vận hành, policy hoặc audit.
- Có thể lưu snapshot đã lọc để giải thích quyết định cấp phát trong quá khứ.
- Giữ mapping cũ đủ lâu để quản lý và thu hồi tài nguyên đã tạo.
- Không dùng raw context làm nguồn ownership duy nhất nếu nó chưa được xác thực và chuẩn hóa.

## 8. Context trong xử lý bất đồng bộ và idempotency

Provision hoặc update có thể mất nhiều thời gian. Nếu broker trả response bất đồng bộ, worker xử lý sau đó phải có đủ dữ liệu để tiếp tục mà không cần request HTTP ban đầu còn tồn tại.

Trước khi enqueue job, broker nên lưu operation cùng các giá trị đã chuẩn hóa:

~~~json
{
  "operation_id": "op-2026-00421",
  "operation_type": "PROVISION",
  "platform_id": "cf-prod",
  "tenant_id": "tenant-commerce",
  "platform_scope_id": "scope-production",
  "instance_id": "orders-db-prod",
  "service_id": "svc-postgresql",
  "plan_id": "plan-postgresql-standard",
  "status": "PENDING"
}
~~~

Worker đọc operation và gọi backend bằng quyền được cấp cho đúng tenant hoặc nhóm tài nguyên. Không nên chỉ đưa raw context vào message rồi để worker tự tin tưởng và diễn giải lại mà không kiểm tra. Nếu cần raw metadata, hãy lưu snapshot đã lọc và tham chiếu đến nó.

Idempotency key nên dựa trên định danh ổn định của platform, tenant, thao tác và resource ID. Request fingerprint có thể bao gồm những phần context thực sự ảnh hưởng đến kết quả, nhưng không nên bao gồm tên hiển thị hoặc field biến động không liên quan.

~~~text
idempotency_key = hash(
    platform_id,
    tenant_id,
    operation_type,
    instance_id,
    binding_id_if_present,
    request_fingerprint
)
~~~

Nếu cùng một instance ID được gửi từ hai platform khác nhau, hai yêu cầu phải được phân biệt theo platform scope. Nếu cùng một ID trong cùng phạm vi được gửi lại với nội dung context hoặc parameters mâu thuẫn, broker cần phát hiện xung đột thay vì ghi đè ownership cũ.

## 9. Bảo mật và quyền riêng tư của context

Context đến từ request bên ngoài nên phải được kiểm tra như mọi dữ liệu đầu vào khác. Việc platform đã xác thực không có nghĩa mọi field trong context đều đúng hoặc được phép sử dụng cho mọi mục đích.

Các nguyên tắc cần áp dụng:

- **Xác thực độc lập:** danh tính platform đến từ cơ chế xác thực kết nối, không đến từ field `platform` trong JSON.
- **Kiểm tra ownership:** đối chiếu organization, space, namespace hoặc project với platform registration và tenant mapping đã được quản trị.
- **Allowlist field:** chỉ diễn giải field đã được định nghĩa trong hợp đồng tích hợp; bỏ qua hoặc từ chối field không hỗ trợ theo policy.
- **Validate cấu trúc:** kiểm tra kiểu dữ liệu, độ dài, kích thước object, ký tự và giới hạn nesting để tránh payload bất thường.
- **Least privilege:** backend credential và quyền binding chỉ có phạm vi cần thiết cho tenant/consumer.
- **Data minimization:** không lưu thông tin cá nhân hoặc metadata không cần thiết; không đưa secret vào context.
- **Log an toàn:** chỉ log platform ID, tenant ID nội bộ, operation ID và field đã được lọc; không ghi toàn bộ raw context tùy tiện.
- **Phân quyền quản trị:** thao tác sửa tenant mapping hoặc platform registration phải có audit và quyền quản trị riêng.

Không nên trả lại toàn bộ context trong response OSB hoặc đưa nó vào credentials. Response chỉ nên chứa thông tin theo schema và mục đích của operation. Nếu một field context được dùng để hiển thị hoặc audit, hãy kiểm soát quyền truy cập và thời gian lưu giữ.

## 10. Xử lý lỗi context

Broker nên phân loại lỗi để platform có thể xử lý đúng:

| Tình huống | Ví dụ | Hướng xử lý |
|---|---|---|
| Context thiếu dữ liệu bắt buộc | Thiếu namespace trong adapter yêu cầu namespace | Từ chối request và trả lỗi validation phù hợp |
| Sai kiểu hoặc sai định dạng | `organization_guid` là object thay vì string | Từ chối, ghi audit an toàn |
| Platform chưa đăng ký | Credential hợp lệ về mặt cú pháp nhưng không ánh xạ được platform | Từ chối xác thực hoặc quyền truy cập |
| Scope chưa được ánh xạ | Namespace chưa có tenant mapping | Từ chối; yêu cầu quy trình đăng ký/quản trị |
| Scope thuộc platform khác | Context khai báo cluster không nằm trong registration của caller | Từ chối và ghi nhận sự kiện bảo mật |
| Context mâu thuẫn | Field legacy khác giá trị context chuẩn | Từ chối hoặc áp dụng quy tắc tương thích đã công bố; không chọn tùy tiện |
| Tenant bị khóa | Mapping tồn tại nhưng tenant đã bị vô hiệu hóa | Từ chối thao tác tạo mới; xử lý tài nguyên cũ theo chính sách |
| Context thay đổi sau provision | Organization đổi tên hoặc namespace được tái tạo | Dùng ownership đã lưu và quy trình cập nhật mapping có kiểm soát |

Thông báo lỗi gửi cho platform cần đủ rõ để sửa request nhưng không tiết lộ tenant hoặc tài nguyên của khách hàng khác. Ví dụ, có thể báo scope không hợp lệ mà không trả tên tenant nội bộ mà scope đó thực sự thuộc về.

## 11. Tổ chức xử lý context trong Spring Cloud Service Broker

Spring Cloud Service Broker cung cấp các model request và service interface cho các thao tác OSB. Ở tầng xử lý, ứng dụng có thể lấy context từ request model tương ứng, sau đó chuyển qua resolver riêng trước khi gọi domain service.

Một cấu trúc package tham khảo:

~~~text
broker/
  api/
    instance/
    binding/
  platform/
    AuthenticatedPlatform.java
    PlatformContextParser.java
    PlatformContextResolver.java
    CloudFoundryContextParser.java
    KubernetesContextParser.java
  tenant/
    TenantMappingRepository.java
    TenantPolicyService.java
  lifecycle/
    ServiceInstanceOrchestrator.java
    ServiceBindingOrchestrator.java
  persistence/
    ServiceInstanceEntity.java
    ServiceBindingEntity.java
    OperationEntity.java
~~~

Các handler nên giữ luồng xử lý ngắn:

~~~java
public CreateInstanceResult provision(
        CreateServiceInstanceRequest request,
        AuthenticatedPlatform platform) {

    ResolvedPlatformContext context =
        platformContextResolver.resolve(platform, request.getContext());

    tenantPolicyService.assertCanProvision(
        context.tenantId(),
        request.getServiceDefinitionId(),
        request.getPlanId(),
        request.getParameters()
    );

    return serviceInstanceOrchestrator.provision(request, context);
}
~~~

Tên model và chữ ký phương thức trong ví dụ minh họa cách phân lớp; cần đối chiếu với phiên bản Spring Cloud Service Broker đang dùng. Không nên để resolver tự đọc header HTTP tùy ý hoặc tự xác định principal. Principal đã xác thực cần được truyền từ lớp bảo mật vào tầng nghiệp vụ.

Đối với binding, dùng resolver tương tự nhưng bổ sung bước xác minh instance ownership và consumer context:

~~~java
public CreateBindingResult bind(
        CreateServiceInstanceBindingRequest request,
        AuthenticatedPlatform platform,
        ServiceInstance instance) {

    ResolvedPlatformContext context =
        platformContextResolver.resolve(platform, request.getContext());

    tenantPolicyService.assertCanBind(
        context,
        instance,
        request.getBindResource(),
        request.getParameters()
    );

    return serviceBindingOrchestrator.bind(request, instance, context);
}
~~~

Nếu phiên bản thư viện không cung cấp context theo đúng kiểu dữ liệu trong ví dụ, hãy chuyển đổi từ model request thực tế tại adapter. Mục tiêu là để domain service chỉ nhận dữ liệu đã chuẩn hóa, không phụ thuộc cấu trúc JSON riêng của platform.

## 12. Kiểm thử tích hợp context

Kiểm thử cần bao phủ cả dữ liệu hợp lệ, dữ liệu thiếu và tình huống cố ý giả mạo.

| Nhóm kiểm thử | Dữ liệu hoặc tình huống | Kết quả mong đợi |
|---|---|---|
| Platform hợp lệ | Credential Cloud Foundry và organization/space đã mapping | Resolver trả đúng platform scope và tenant |
| Kubernetes hợp lệ | Controller đã đăng ký, cluster và namespace đã mapping | Resolver trả đúng tenant |
| Thiếu context | Request thiếu field bắt buộc theo adapter | Request bị từ chối rõ ràng |
| Platform giả mạo | JSON ghi `platform=kubernetes` nhưng principal là platform khác | Broker vẫn dùng danh tính principal; scope không hợp lệ bị từ chối |
| Tenant giả mạo | Caller thay namespace/organization để trỏ sang tenant khác | Ownership check từ chối |
| Trùng tên scope | Hai cluster có namespace cùng tên | Hai scope được phân biệt bằng platform/cluster ID |
| Context cũ | Request dùng field tương thích cũ | Adapter xử lý theo quy tắc version đã công bố |
| Context mâu thuẫn | Field legacy và context có giá trị khác nhau | Phát hiện và từ chối hoặc xử lý theo quy tắc tương thích rõ ràng |
| Retry | Provision được gửi lại với cùng định danh và fingerprint | Trả operation/kết quả cũ, không tạo tài nguyên trùng |
| Async restart | Worker khởi động lại khi operation đang pending | Tiếp tục bằng context đã chuẩn hóa và state đã lưu |
| Tenant bị khóa | Tenant mapping bị vô hiệu hóa trước request mới | Từ chối thao tác mới; tài nguyên cũ vẫn có thể được quản trị theo policy |

Ngoài unit test cho từng parser, cần có integration test kiểm tra toàn bộ đường đi từ xác thực platform đến tenant mapping, state store và backend adapter. Một bài test quan trọng là tạo hai instance có cùng chuỗi `instance_id` ở hai platform khác nhau, sau đó xác nhận mỗi platform chỉ truy cập được tài nguyên thuộc scope của mình.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Rủi ro | Cách xử lý |
|---|---|---|
| Coi context là dữ liệu đã tin cậy | Caller có thể giả mạo tenant hoặc platform scope | Xác thực platform và đối chiếu mapping |
| Dùng tên organization/namespace làm khóa | Tên có thể đổi hoặc trùng giữa platform | Dùng ID ổn định kèm platform scope |
| Trộn context với parameters | Người dùng có thể thay đổi dữ liệu ownership qua cấu hình dịch vụ | Tách metadata platform khỏi input cấu hình |
| Parse context trong mọi handler | Logic khác nhau giữa provision, update và bind | Dùng resolver/parser dùng chung |
| Lưu nguyên raw context không lọc | Lộ dữ liệu nhạy cảm và khó migration | Allowlist, lọc và version hóa |
| Yêu cầu mọi platform gửi cùng schema | Khó tích hợp các nền tảng có mô hình khác nhau | Adapter riêng và mô hình nội bộ chuẩn hóa |
| Worker chỉ nhận raw context | Công việc async phụ thuộc request ban đầu và dễ diễn giải sai | Lưu resolved context cùng operation |
| Không giữ mapping cũ | Không thể xác định ownership khi thu hồi tài nguyên cũ | Version hóa và quản lý vòng đời mapping |

## 14. Nguyên tắc cần ghi nhớ

Context giúp broker hiểu yêu cầu OSB API phát sinh từ platform và phạm vi nào. Dữ liệu riêng của từng nền tảng có thể khác nhau, nhưng broker cần chuyển chúng thành một mô hình nội bộ thống nhất để xử lý service instance, binding, operation và tenant policy.

Khi triển khai bằng Spring Cloud Service Broker, hãy giữ các ranh giới sau:

- Principal đã xác thực xác định platform caller.
- Context cung cấp metadata để phân giải platform scope và tenant.
- Parameters mô tả cấu hình dịch vụ do người dùng yêu cầu.
- Bind resource và binding context giúp xác định consumer theo hợp đồng tích hợp.
- Resolver chuẩn hóa dữ liệu platform-specific thành định danh nội bộ.
- State store giữ ownership đã xác minh để các thao tác vòng đời và worker bất đồng bộ dùng nhất quán.

Cloud Foundry có thể cung cấp thông tin organization/space; adapter Kubernetes có thể cung cấp cluster/namespace/project theo hợp đồng riêng. Broker không cần ép hai nền tảng dùng cùng JSON schema. Điều cần thống nhất là cách xác thực caller, ánh xạ scope sang tenant, lưu ownership, kiểm tra quyền và xử lý retry. Nhờ vậy, cùng một broker có thể phục vụ nhiều nền tảng mà vẫn bảo vệ ranh giới dữ liệu và vòng đời tài nguyên của từng khách hàng.

