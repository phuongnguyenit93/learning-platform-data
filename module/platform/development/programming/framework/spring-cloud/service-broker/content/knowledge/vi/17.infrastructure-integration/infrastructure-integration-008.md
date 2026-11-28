# Đặt tên, gắn nhãn và truy vết tài nguyên do broker tạo

Một service broker không chỉ tạo service instance trong cơ sở dữ liệu của chính nó. Khi provision PostgreSQL, Redis, object storage hoặc message queue, broker còn tạo một hay nhiều tài nguyên ở hệ thống hạ tầng bên ngoài. Những tài nguyên này cần tên có quy tắc, metadata nhận diện chủ sở hữu và mối liên hệ rõ ràng với service instance, binding và operation trong Open Service Broker API (OSB API).

Với `SPRING_CLOUD_SERVICE_BROKER`, đặt tên và gắn nhãn đúng giúp broker tìm lại tài nguyên sau timeout, tránh tạo trùng khi retry, chỉ thu hồi tài nguyên thuộc quyền quản lý của mình và điều tra sự cố xuyên suốt từ request platform tới provider. Tên tài nguyên hỗ trợ con người và công cụ hạ tầng nhận diện; tags/labels hỗ trợ lọc và phân loại; external resource ID là định danh do provider cấp; còn operation/correlation ID giúp nối các sự kiện trong toàn bộ vòng đời.

## 1. Vì sao broker cần naming convention và ownership metadata?

Giả sử platform yêu cầu provision service instance `instance-123`. Broker có thể tạo database, database user quản trị, network endpoint, backup policy và monitoring rule. Nếu mỗi lần gọi provider đều dùng tên ngẫu nhiên hoặc tên không có quy tắc, broker khó tìm lại những tài nguyên đó khi:

- Provider đã tạo tài nguyên nhưng response bị timeout.
- Worker restart trước khi lưu external resource ID.
- Platform retry cùng request provision.
- Broker cần update hoặc deprovision instance sau nhiều tháng.
- Operator cần điều tra tài nguyên mồ côi hoặc chi phí bất thường.
- Một provider account được dùng chung bởi nhiều broker, môi trường hoặc tenant.

Một naming convention ổn định và ownership metadata cho phép broker truy vấn lại tài nguyên theo dấu vết đã lưu. Tuy nhiên, tên hoặc tag không thay thế database state và cũng không phải cơ chế authorization duy nhất. Broker vẫn phải lưu external ID, kiểm tra ownership và xác minh phạm vi trước khi update/delete.

## 2. Phân biệt các loại định danh

Trong một workflow OSB, nhiều định danh cùng xuất hiện nhưng không thể thay thế nhau:

| Định danh | Nguồn tạo | Vai trò |
|---|---|---|
| `service_instance_id` | Platform | Nhận diện service instance trong hợp đồng OSB API. |
| `binding_id` | Platform | Nhận diện một liên kết giữa instance và consumer. |
| `operation_id` | Broker | Theo dõi một lần provision, update, bind, unbind hoặc deprovision. |
| `external_resource_id` | Provider | Khóa định danh tài nguyên thực tế trong hệ thống hạ tầng. |
| `resource_name` | Broker hoặc provider | Tên dễ nhận biết để operator và công cụ hạ tầng sử dụng. |
| `correlation_id` | Gateway, platform hoặc broker | Liên kết log/trace của một lần trao đổi hoặc một workflow. |
| `provider_request_id` | Provider | Mã request do provider trả về để hỗ trợ tra cứu sự cố. |

`service_instance_id` là định danh của platform; nó không nhất thiết là tên hợp lệ trong provider. `external_resource_id` là định danh provider; nó có thể là UUID hoặc chuỗi opaque và không nên được tự dựng từ tên. `resource_name` chỉ là tên hiển thị hoặc tên dùng trong API provider. Broker cần lưu mapping giữa các giá trị này.

Ví dụ một bản ghi mapping:

```json
{
  "service_instance_id": "instance-123",
  "service_id": "postgres-service-id",
  "plan_id": "postgres-standard-plan",
  "operation_id": "op-provision-456",
  "provider": "example-cloud",
  "provider_account_ref": "account-prod-a",
  "resource_type": "managed-database",
  "resource_name": "sb-prod-ap1-pg-a1b2c3d4",
  "external_resource_id": "db-8f7a21",
  "lifecycle_state": "AVAILABLE"
}
```

Thông tin account trong ví dụ là reference nội bộ. Không đưa credential hoặc access token của provider vào mapping record.

## 3. Thiết kế naming convention

Tên tài nguyên nên ngắn, ổn định, có thể đọc và tuân thủ giới hạn của provider. Một cấu trúc tham khảo:

```text
sb-{environment}-{region}-{service-code}-{instance-key}-{resource-kind}
```

Ví dụ:

```text
sb-prod-ap1-pg-a1b2c3d4-database
sb-prod-ap1-pg-a1b2c3d4-network
sb-prod-ap1-pg-a1b2c3d4-backup
sb-dev-ap1-redis-71c93a20-cache
```

Ý nghĩa các thành phần:

- `sb`: prefix nhận diện tài nguyên do service broker quản lý.
- `environment`: môi trường như `dev`, `staging`, `prod`.
- `region`: mã vùng ngắn theo quy ước nội bộ, ví dụ `ap1`.
- `service-code`: mã service ổn định như `pg`, `redis`, `mq`.
- `instance-key`: phần rút gọn hoặc hash ổn định từ service instance ID.
- `resource-kind`: loại tài nguyên con, ví dụ `database`, `network`, `backup`.

Không nhất thiết phải đưa mọi thành phần vào tên. Nếu provider giới hạn độ dài, ký tự hoặc uniqueness scope, hãy ưu tiên prefix quản lý, instance key và resource kind; các thông tin còn lại có thể lưu trong tags/labels và database. Không thêm tên người dùng, email, tên ứng dụng nội bộ hoặc dữ liệu tenant nhạy cảm vào resource name.

### Quy tắc tên nên có

1. **Deterministic:** cùng một instance và resource kind tạo ra cùng tên trong các lần retry.
2. **Unique trong phạm vi provider:** tránh trùng giữa tenant, môi trường hoặc account dùng chung.
3. **Stable:** không thay đổi khi plan đổi tên hoặc description được sửa.
4. **Provider-compatible:** chỉ dùng ký tự, độ dài và pattern được provider chấp nhận.
5. **Không chứa secret/PII:** tên có thể xuất hiện trong console, audit và log.
6. **Có version khi cần:** thay đổi quy tắc naming có thể được quản lý bằng `naming_version` trong metadata.

Không dùng `plan.name` làm thành phần định danh bắt buộc vì tên plan có thể thay đổi. Nên dùng service code được quản lý ổn định hoặc ID rút gọn có kiểm soát.

## 4. Chuẩn hóa và tạo instance key ổn định

Platform có thể cấp `instance_id` với ký tự hoặc độ dài không phù hợp cho provider. Broker nên chuẩn hóa đầu vào trước khi tạo tên. Không nên chỉ cắt chuỗi tùy tiện vì hai ID khác nhau có thể bị rút gọn thành cùng một tên.

Một cách thường dùng là kết hợp phần dễ đọc với hash ổn định:

```text
{sanitized-prefix}-{short-hash(instance-id)}
```

Ví dụ Java:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Locale;

public final class ResourceNameFactory {

    public String instanceKey(String instanceId) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(instanceId.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest).substring(0, 12);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }

    public String normalizeToken(String value) {
        String normalized = value.toLowerCase(Locale.ROOT)
                .replaceAll("[^a-z0-9-]", "-")
                .replaceAll("-+", "-")
                .replaceAll("^-|-$", "");
        return normalized.isBlank() ? "x" : normalized;
    }

    public String databaseName(String environment, String region,
                               String serviceCode, String instanceId) {
        return "sb-" + normalizeToken(environment)
                + "-" + normalizeToken(region)
                + "-" + normalizeToken(serviceCode)
                + "-" + instanceKey(instanceId)
                + "-database";
    }
}
```

Đây là ví dụ minh họa. Trong triển khai thực tế, cần giới hạn độ dài sau khi ghép, kiểm tra ký tự theo provider, xử lý tên đã tồn tại và chọn độ dài hash phù hợp với số lượng tài nguyên dự kiến. Hash rút gọn có xác suất collision khác không; database vẫn phải lưu mapping và provider uniqueness constraint vẫn phải được xử lý. Không dùng hash của secret hoặc dữ liệu nhạy cảm để tạo tên.

Nếu tên provider phải unique toàn account, có thể cần thêm mã region/account alias hoặc một suffix khác. Không đưa credential/account number nhạy cảm vào tên; dùng alias nội bộ không chứa bí mật.

## 5. Tags và labels để nhận diện quyền sở hữu

Tags/labels là metadata gắn với tài nguyên provider. Chúng giúp broker hoặc operator lọc tài nguyên, phân nhóm chi phí, tìm resource theo instance và xác định tài nguyên do broker quản lý.

Một bộ tag gợi ý:

| Key | Ví dụ value | Mục đích |
|---|---|---|
| `managed-by` | `spring-cloud-service-broker` | Nhận diện hệ thống quản lý. |
| `broker-instance-id` | `instance-123` | Liên kết với service instance. |
| `broker-operation-id` | `op-provision-456` | Truy vết lần tạo hoặc thay đổi. |
| `broker-service-id` | `postgres-service-id` | Liên kết service trong catalog. |
| `broker-plan-id` | `postgres-standard-plan` | Liên kết plan đã chọn. |
| `broker-environment` | `prod` | Phân biệt môi trường. |
| `broker-resource-kind` | `database` | Phân loại tài nguyên con. |
| `broker-schema-version` | `1` | Phiên bản quy ước metadata. |

Ví dụ provider API payload:

```json
{
  "name": "sb-prod-ap1-pg-a1b2c3d4-database",
  "engine": "postgresql",
  "tags": {
    "managed-by": "spring-cloud-service-broker",
    "broker-instance-id": "instance-123",
    "broker-operation-id": "op-provision-456",
    "broker-service-id": "postgres-service-id",
    "broker-plan-id": "postgres-standard-plan",
    "broker-environment": "prod",
    "broker-resource-kind": "database",
    "broker-schema-version": "1"
  }
}
```

Tên field thực tế có thể là `tags`, `labels`, `metadata` hoặc một cấu trúc riêng theo provider. Broker adapter phải chuyển đổi mô hình metadata nội bộ sang API cụ thể. Không giả định mọi provider hỗ trợ cùng bộ key, cùng kiểu dữ liệu hoặc cùng giới hạn số lượng tag.

## 6. Labels, annotations và tags không hoàn toàn giống nhau

Các nền tảng có mô hình metadata khác nhau:

| Nền tảng | Cơ chế thường gặp | Lưu ý |
|---|---|---|
| Cloud provider | Tags hoặc resource labels | Có giới hạn key/value, số lượng, ký tự và scope; một số tài nguyên không hỗ trợ tag giống nhau. |
| Kubernetes | `metadata.labels` và `metadata.annotations` | Labels dùng cho selector/filter; annotations chứa metadata không dùng làm selector. |
| Cloud Foundry | Context, service instance metadata và thông tin do broker lưu | Không phải mọi provider resource được Cloud Foundry tự động gắn tag; broker cần chuyển context vào adapter nếu phù hợp. |
| Hệ thống tự quản lý | Metadata field hoặc ownership table | Cần định nghĩa schema và quyền cập nhật rõ ràng. |

Với Kubernetes, label value có quy tắc ký tự và độ dài chặt hơn annotation. Một ID dài hoặc chứa ký tự đặc biệt có thể phù hợp trong annotation nhưng không hợp lệ trong label. Có thể dùng label ngắn để chọn tài nguyên theo `managed-by` hoặc loại resource, và annotation để lưu instance ID đầy đủ, operation ID hoặc thông tin truy vết dài hơn.

Ví dụ Kubernetes metadata:

```yaml
metadata:
  name: sb-prod-pg-a1b2c3d4
  labels:
    app.kubernetes.io/managed-by: spring-cloud-service-broker
    broker.example.com/resource-kind: database
    broker.example.com/environment: prod
  annotations:
    broker.example.com/instance-id: instance-123
    broker.example.com/operation-id: op-provision-456
    broker.example.com/service-id: postgres-service-id
    broker.example.com/plan-id: postgres-standard-plan
```

Prefix domain trong ví dụ là placeholder của tổ chức. Trong cluster dùng chung, hãy chọn prefix thuộc quyền kiểm soát của tổ chức và tránh dùng key thuộc Kubernetes hoặc controller khác.

## 7. Tags không phải ranh giới bảo mật

Ownership tag hỗ trợ truy vấn và đối soát, nhưng không tự chứng minh rằng broker có quyền xóa tài nguyên. Một người có quyền sửa tag có thể gắn `managed-by=spring-cloud-service-broker` lên tài nguyên không thuộc broker. Vì vậy, trước khi update/delete, broker cần xác minh nhiều yếu tố:

- External resource ID khớp với mapping record đã lưu.
- Provider account/project/region đúng với phạm vi của instance.
- Ownership tag hoặc label khớp `broker-instance-id` và resource kind.
- Tenant context và service instance được xác thực.
- Tài nguyên không bị chuyển quyền sở hữu hoặc thay đổi ngoài quy trình được phép.
- Provider API caller chỉ có quyền cần thiết trong account/project tương ứng.

Nếu external ID không tồn tại trong database nhưng provider tìm thấy resource có tag của broker, không nên tự động xóa ngay. Hãy kiểm tra owner, instance identity, trạng thái operation và quy tắc phục hồi trước. Một tài nguyên có tag đúng vẫn có thể thuộc một lần tạo khác hoặc đã được operator tiếp nhận.

## 8. Lưu mapping external resource trong broker database

Broker nên có bảng riêng để liên kết service instance với các tài nguyên provider. Một instance có thể tạo nhiều resource nên không nên chỉ lưu một external ID duy nhất nếu nghiệp vụ có nhiều thành phần.

Ví dụ schema khái niệm:

```sql
CREATE TABLE broker_external_resource (
    id BIGINT PRIMARY KEY,
    instance_id VARCHAR(255) NOT NULL,
    operation_id VARCHAR(255),
    provider_name VARCHAR(100) NOT NULL,
    provider_account_ref VARCHAR(255) NOT NULL,
    region VARCHAR(100),
    resource_type VARCHAR(100) NOT NULL,
    resource_name VARCHAR(255) NOT NULL,
    external_resource_id VARCHAR(512),
    ownership_tag_value VARCHAR(255) NOT NULL,
    lifecycle_state VARCHAR(40) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_external_resource_instance
    ON broker_external_resource(instance_id);

CREATE UNIQUE INDEX uq_provider_external_resource
    ON broker_external_resource(
        provider_name, provider_account_ref, external_resource_id
    );
```

Schema thực tế cần xử lý `external_resource_id` có thể chưa biết trước khi provider trả response, ràng buộc uniqueness theo provider, account và resource type nếu provider định nghĩa scope khác. Có thể dùng `resource_key` nội bộ làm khóa chính và cập nhật external ID sau khi tạo thành công.

Mapping nên lưu tối thiểu:

- Instance ID và service/plan ID đã dùng.
- Provider name và account/project reference.
- Region hoặc scope cần thiết.
- Resource type, resource name và external resource ID.
- Ownership metadata đã gắn.
- Operation ID tạo hoặc cập nhật resource.
- Lifecycle state và thời điểm cập nhật.

Không lưu access key, secret token, password hoặc private key trong bảng mapping. Thông tin xác thực provider nên nằm trong secret manager hoặc cơ chế credential injection của nền tảng.

## 9. Truy vết xuyên suốt từ OSB request đến provider

Để điều tra một thao tác, operator cần nối được các sự kiện:

```text
OSB request
  -> service_instance_id / binding_id
  -> broker operation_id
  -> outbox event_id
  -> provider request_id
  -> external_resource_id
  -> resource tags/labels
```

Mỗi log event nên chứa những định danh an toàn cần thiết, ví dụ `operation_id`, `instance_id`, `resource_type` và provider request ID. Nếu platform gửi correlation ID, broker có thể tiếp tục truyền nó qua các lớp nội bộ và gửi tới provider nếu provider hỗ trợ metadata tương ứng.

Ví dụ log có cấu trúc:

```json
{
  "event": "provider.resource.created",
  "operation_id": "op-provision-456",
  "instance_id": "instance-123",
  "service_id": "postgres-service-id",
  "plan_id": "postgres-standard-plan",
  "provider": "example-cloud",
  "resource_type": "managed-database",
  "external_resource_id": "db-8f7a21",
  "provider_request_id": "req-91b2",
  "result": "success"
}
```

Không log raw request body, Authorization header, provider credentials, connection string hoặc secret. Correlation ID giúp tìm log nhưng không nên được dùng làm quyền truy cập hay idempotency key nếu semantics của nó không ổn định qua retry.

## 10. Truyền correlation metadata qua Spring

Ứng dụng có thể chuẩn hóa các ID trong một context nội bộ để adapter/provider client dùng nhất quán:

```java
public record ResourceOperationContext(
        String instanceId,
        String operationId,
        String serviceId,
        String planId,
        String correlationId,
        String environment
) {}
```

Context này được tạo sau khi request đã được xác thực và validate. Không lấy mọi header tùy ý từ client rồi chuyển thẳng sang provider. Chỉ truyền correlation header đã được allowlist, chẳng hạn `X-Correlation-ID`, và tạo giá trị mới nếu đầu vào thiếu hoặc không hợp lệ.

Ví dụ WebClient filter cho provider:

```java
ExchangeFilterFunction correlationFilter() {
    return (request, next) -> Mono.deferContextual(contextView -> {
        String correlationId = contextView.getOrDefault(
                "correlationId", "unavailable");

        ClientRequest enriched = ClientRequest.from(request)
                .header("X-Correlation-ID", correlationId)
                .build();

        return next.exchange(enriched);
    });
}
```

Đây là ví dụ minh họa cho Reactor Context; ứng dụng cần đảm bảo correlation ID được đặt vào context ở đúng ranh giới request/worker. Với worker chạy qua message queue, phải serialize correlation ID an toàn trong job metadata vì Reactor Context không tự đi qua process hoặc queue boundary.

## 11. Gắn tag trong provider adapter

Không nên để nghiệp vụ service tự biết cấu trúc tag riêng của từng cloud provider. Tạo một mô hình metadata chung và để adapter chuyển đổi sang API cụ thể.

```java
public record ResourceOwnershipMetadata(
        String managedBy,
        String instanceId,
        String operationId,
        String serviceId,
        String planId,
        String environment,
        String resourceKind,
        String schemaVersion
) {}
```

Một factory có thể tạo metadata từ operation context:

```java
public final class OwnershipMetadataFactory {
    public ResourceOwnershipMetadata create(
            ResourceOperationContext context,
            String resourceKind
    ) {
        return new ResourceOwnershipMetadata(
                "spring-cloud-service-broker",
                context.instanceId(),
                context.operationId(),
                context.serviceId(),
                context.planId(),
                context.environment(),
                resourceKind,
                "1"
        );
    }
}
```

Adapter chuyển record này thành `Map<String,String>` cho provider hỗ trợ tags, hoặc thành Kubernetes labels/annotations. Nếu provider giới hạn số tag hoặc độ dài value, adapter cần kiểm tra và chọn tập trường ưu tiên; không âm thầm bỏ `instance_id` hoặc ownership marker quan trọng.

## 12. Sử dụng metadata khi retry và reconciliation

Nếu broker timeout sau khi provider tạo resource nhưng trước khi external ID được lưu, broker có thể tìm resource bằng:

1. Provider idempotency key hoặc request ID đã gửi.
2. Ownership tag `broker-instance-id` và `broker-operation-id`.
3. Resource name deterministic theo naming convention.
4. Provider account/project, region và resource type.

Kết quả truy vấn cần được xác minh. Nếu tìm thấy đúng một resource và tags/owner khớp, broker có thể nhận lại external ID rồi tiếp tục operation. Nếu không tìm thấy resource, có thể retry theo idempotency policy. Nếu tìm thấy nhiều resource cùng tag, không chọn ngẫu nhiên; chuyển sang trạng thái cần reconcile hoặc can thiệp để tránh xóa nhầm.

Một reconcile job có thể so sánh:

- Desired state trong broker database.
- External resource mapping và lifecycle state đã lưu.
- Trạng thái thực tế provider trả về.
- Ownership metadata của tài nguyên.

Nếu instance đang `AVAILABLE` nhưng provider resource không còn tồn tại, broker cần áp dụng policy phục hồi hoặc đánh dấu lỗi. Nếu instance đang `DEPROVISIONING` nhưng provider resource vẫn tồn tại, worker tiếp tục cleanup. Không xóa tài nguyên chỉ vì không thấy mapping trong database; cần xác minh ownership và quy trình orphan cleanup riêng.

## 13. Xử lý thay đổi tên và phiên bản naming convention

Resource name có thể tồn tại lâu hơn phiên bản code đã tạo ra nó. Nếu broker thay đổi quy tắc từ `sb-prod-pg-{hash}` sang `broker-prod-postgres-{hash}`, các instance cũ vẫn mang tên cũ. Vì vậy:

- Lưu resource name thực tế trong mapping record; không tính lại tên cũ từ code mới để update/delete.
- Lưu `naming_version` hoặc `broker-schema-version` trong metadata.
- Khi tạo resource mới, dùng convention hiện hành.
- Khi xử lý resource cũ, dùng external ID và metadata đã lưu; không ép rename chỉ vì convention đổi.
- Nếu provider hỗ trợ rename, thực hiện qua migration có kiểm soát và cập nhật mapping sau khi xác nhận.
- Không tái sử dụng tên cũ cho một instance khác nếu provider giữ resource cũ hoặc tombstone.

Ví dụ record:

```json
{
  "resource_name": "sb-prod-ap1-pg-a1b2c3d4-database",
  "naming_version": 1,
  "external_resource_id": "db-8f7a21"
}
```

Thay đổi plan name hoặc description không nên làm đổi resource name. Nếu plan mới tạo ra loại tài nguyên khác, dùng resource kind hoặc naming version phù hợp nhưng vẫn giữ mapping với cùng instance/operation theo nghiệp vụ.

## 14. Xóa tài nguyên an toàn dựa trên ownership

Deprovision có tác động phá hủy. Broker chỉ được xóa tài nguyên khi xác định chắc chắn nó thuộc instance đang thu hồi.

Quy trình đề xuất:

1. Đọc mapping theo `instance_id` từ database broker.
2. Xác minh provider/account/region và external resource ID.
3. Truy vấn provider để xác nhận resource tồn tại và đọc ownership metadata hiện tại.
4. So sánh `managed-by`, instance ID, resource kind và các trường owner đã lưu.
5. Kiểm tra tài nguyên không phải tài nguyên dùng chung hoặc đã được chuyển quyền sở hữu.
6. Gọi delete bằng external resource ID, không chỉ bằng tên.
7. Nếu provider trả not found, xác minh đúng resource identity rồi ghi nhận bước xóa đã đạt mục tiêu.
8. Lưu kết quả operation, tombstone và audit event.

Nếu tag đã bị thay đổi hoặc không khớp, không tự động xóa. Đưa resource vào trạng thái `OWNERSHIP_MISMATCH`/`RECONCILIATION_REQUIRED` và yêu cầu quy trình xử lý phù hợp. Không được dùng quyền quản trị rộng để xóa mọi tài nguyên có tên bắt đầu bằng `sb-`.

## 15. Giới hạn provider và chiến lược fallback

Không phải provider nào cũng hỗ trợ tags trên mọi loại tài nguyên. Có tài nguyên chỉ cho phép một số tag lúc tạo, một số không hỗ trợ cập nhật metadata, một số giới hạn key/value hoặc không cho phép truy vấn theo tag.

| Hạn chế | Hướng xử lý |
|---|---|
| Không hỗ trợ tags | Dựa vào external ID và mapping DB; dùng deterministic name nếu provider cho phép. |
| Chỉ gắn tags lúc create | Tạo ownership metadata ngay từ request đầu tiên. |
| Giới hạn số tag | Ưu tiên managed-by, instance ID, operation ID, resource kind và schema version. |
| Tag value quá ngắn | Lưu ID đầy đủ trong DB; dùng key/hash ngắn có mapping rõ ràng. |
| Không query theo tags | Tra cứu theo external ID/name hoặc provider operation ID. |
| Resource name không unique toàn account | Thêm scope alias hoặc suffix hash; xử lý collision bằng unique constraint. |
| Metadata bị operator sửa | Phát hiện mismatch, không tự xóa; yêu cầu reconcile có kiểm soát. |

Nếu provider không hỗ trợ tag, không được giả vờ rằng ownership đã được xác minh bằng metadata. Cần dựa vào mapping bền vững, external ID, account scope và audit. Nếu không thể khôi phục external ID sau timeout và provider cũng không hỗ trợ lookup bằng name/correlation, cần đánh giá giới hạn đó trước khi triển khai provisioning tự động.

## 16. Tích hợp Cloud Foundry và Kubernetes

### Cloud Foundry

Cloud Foundry gửi context như organization và space trong các request OSB theo platform/version. Broker có thể dùng context đã xác thực để chọn provider account/project hoặc gắn metadata tương ứng vào tài nguyên. Không nên đưa nguyên tên organization/space hoặc thông tin người dùng vào resource name nếu chúng có thể chứa dữ liệu riêng tư; dùng mã định danh hoặc alias nội bộ đã chuẩn hóa.

Tên service instance hiển thị trong Cloud Foundry và tên resource thực tế ở provider là hai khái niệm khác nhau. Broker nên giữ mapping từ instance ID, context, resource name và external ID. Khi người dùng đổi tên hiển thị service instance, broker không nên đổi tên tài nguyên provider một cách tự động nếu không có yêu cầu và quy trình migration riêng.

### Kubernetes

Nếu broker tạo resource trong Kubernetes, có thể dùng labels để selector và quản lý tập tài nguyên, annotations để lưu ID đầy đủ và thông tin truy vết. Ví dụ:

```yaml
metadata:
  labels:
    app.kubernetes.io/managed-by: spring-cloud-service-broker
    broker.example.com/instance-key: a1b2c3d4
  annotations:
    broker.example.com/instance-id: instance-123
    broker.example.com/operation-id: op-provision-456
```

RBAC cần giới hạn broker chỉ tạo, đọc, cập nhật và xóa loại resource/namespace cần thiết. Labels không thay thế Kubernetes authorization. Trước khi xóa, broker cần kiểm tra namespace, resource kind, owner reference và metadata theo chính sách. Không xóa object chỉ vì label `managed-by` có giá trị phù hợp nếu không xác minh instance mapping.

## 17. Observability và báo cáo chi phí

Ownership metadata còn giúp theo dõi tài nguyên và chi phí:

- Nhóm chi phí theo service, plan, môi trường hoặc broker instance nếu provider hỗ trợ cost allocation tags.
- Phát hiện resource không có mapping hoặc resource đã deprovision nhưng vẫn tồn tại.
- Theo dõi thời gian từ operation bắt đầu tới khi provider tạo/xóa xong.
- Liên kết cảnh báo provider với operation ID và instance ID.
- Đếm resource theo loại và lifecycle state.

Không dùng instance ID, binding ID hoặc tenant ID làm metric label không giới hạn vì cardinality có thể tăng rất nhanh. Dùng log có cấu trúc hoặc trace cho định danh chi tiết; metric chỉ nên dùng các chiều có tập giá trị hữu hạn như provider, resource type, operation type, environment và result.

Một số metric gợi ý:

| Metric | Ý nghĩa |
|---|---|
| `broker_provider_operation_duration` | Thời gian gọi provider theo operation/resource type. |
| `broker_external_resource_count` | Số tài nguyên theo provider, resource type và lifecycle state. |
| `broker_orphan_resource_detected_total` | Số resource có dấu hiệu mồ côi được phát hiện. |
| `broker_ownership_mismatch_total` | Số trường hợp ownership metadata không khớp. |
| `broker_reconciliation_attempt_total` | Số lần reconcile theo kết quả. |

## 18. Checklist triển khai

- Naming convention deterministic, stable và phù hợp giới hạn provider.
- Resource name không chứa secret hoặc PII.
- Không dùng plan display name làm định danh tài nguyên dài hạn.
- Tags/labels có ownership marker, instance ID, resource kind và schema version.
- Phân biệt tags của cloud provider với Kubernetes labels/annotations.
- Lưu external resource ID và resource name thực tế trong mapping database.
- Correlation ID, operation ID và provider request ID được liên kết xuyên suốt workflow.
- Provider adapter kiểm tra giới hạn tags và chuẩn hóa metadata.
- Không coi ownership tag là cơ chế authorization duy nhất.
- Trước update/delete, xác minh external ID, account scope và ownership.
- Retry sau timeout dùng lookup/idempotency trước khi tạo resource mới.
- Naming convention có version và không ép rename tài nguyên cũ ngoài kế hoạch.
- Có reconciliation và quy trình orphan cleanup an toàn.
- Log/trace không chứa credential; metric không dùng ID có cardinality cao.
- Có test cho collision, tag limit, metadata mismatch, retry và deprovision.

Đặt tên, gắn nhãn và truy vết là một phần của thiết kế vòng đời tài nguyên, không chỉ là quy ước đặt chuỗi. Khi broker dùng tên deterministic, gắn ownership metadata phù hợp với provider, lưu external resource ID và nối các ID OSB với operation/correlation ID, nó có thể phục hồi sau timeout, đối soát tài nguyên, thu hồi đúng phạm vi và giúp operator điều tra sự cố mà không phụ thuộc vào suy đoán từ tên hoặc tag.
