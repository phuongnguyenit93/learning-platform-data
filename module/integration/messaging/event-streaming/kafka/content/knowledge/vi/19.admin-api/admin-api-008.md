# Quản lý ACL và quota bằng API

Kafka cho phép quản trị quyền truy cập và giới hạn tài nguyên của client thông qua các API quản trị. **ACL (Access Control List)** xác định principal nào được thực hiện thao tác nào trên topic, consumer group, cluster hoặc transactional ID. **Quota** giới hạn tốc độ dữ liệu hoặc mức sử dụng request của client, giúp một producer/consumer không chiếm quá nhiều tài nguyên broker.

Trong Java, các thao tác này được thực hiện qua `AdminClient`/`Admin` của Kafka Admin API. Ứng dụng quản trị có thể tạo, mô tả và xóa ACL; thay đổi và đọc quota theo user, client ID hoặc kết hợp nhiều thuộc tính entity. Để sử dụng an toàn, cần hiểu resource pattern, permission, phạm vi quota, quyền của principal quản trị và cách xác minh kết quả sau khi thay đổi.

## 1. Admin API quản lý ACL và quota như thế nào?

`AdminClient` là client quản trị giao tiếp với Kafka cluster để thực hiện các thao tác như quản lý topic, partition, config, ACL, quota và consumer group. Admin API không phải là API gửi/đọc event; nó thay đổi metadata hoặc cấu hình quản trị của cluster.

Hai nhóm API trong bài:

| Nhóm | API chính | Mục đích |
|---|---|---|
| ACL | `createAcls()`, `describeAcls()`, `deleteAcls()` | Cấp, kiểm tra và thu hồi quyền truy cập |
| Client quota | `alterClientQuotas()`, `describeClientQuotas()` | Thiết lập, xem và gỡ giới hạn theo client entity |

Các lời gọi Admin API thường trả về đối tượng kết quả bất đồng bộ chứa `KafkaFuture`. Ứng dụng cần chờ hoặc kết hợp future, đặt timeout, xử lý lỗi và đóng client đúng vòng đời. Không nên gọi các thao tác quản trị trên mỗi request nghiệp vụ; thường dùng trong provisioning pipeline, công cụ vận hành hoặc service quản trị riêng.

## 2. Bật authorizer để Kafka thực thi ACL

Khai báo ACL trong cluster chỉ có tác dụng khi broker được cấu hình authorizer phù hợp. Với Kafka chạy KRaft, authorizer tích hợp thường dùng là `StandardAuthorizer`:

```properties
authorizer.class.name=org.apache.kafka.metadata.authorizer.StandardAuthorizer
```

Với cluster dùng ZooKeeper và các bản Kafka cũ, cấu hình authorizer có thể là `kafka.security.authorizer.AclAuthorizer`. Không sao chép cấu hình authorizer giữa các kiến trúc/version mà không kiểm tra tài liệu đúng phiên bản.

Một số cấu hình liên quan:

```properties
super.users=User:admin;User:kafka-broker
allow.everyone.if.no.acl.found=false
```

- `super.users` liệt kê principal có quyền quản trị vượt qua kiểm tra ACL thông thường. Cần bảo vệ các principal này rất chặt.
- `allow.everyone.if.no.acl.found` điều khiển hành vi khi resource chưa có ACL phù hợp; với chế độ `false`, truy cập bị từ chối nếu không có ACL cho phép phù hợp.
- Nếu bật authorizer mà chưa chuẩn bị ACL và superuser quản trị, ứng dụng có thể mất quyền truy cập cluster. Hãy cấu hình principal bootstrap/quản trị trước khi bật enforcement.

Authorizer cũng có thể kiểm soát các API quản trị. Principal chạy AdminClient cần được cấp quyền thích hợp để tạo/xem/xóa ACL hoặc thay đổi quota. Không dùng credential của superuser trong ứng dụng nghiệp vụ thông thường.

## 3. Thành phần của một ACL

Một ACL Kafka kết hợp resource pattern và access control entry:

```text
AclBinding
  ├── ResourcePattern
  │     ├── resourceType
  │     ├── name
  │     └── patternType
  └── AccessControlEntry
        ├── principal
        ├── host
        ├── operation
        └── permissionType
```

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Resource type | Loại tài nguyên được bảo vệ | `TOPIC`, `GROUP`, `CLUSTER`, `TRANSACTIONAL_ID` |
| Resource name | Tên tài nguyên | `orders.events`, `order-handler` |
| Pattern type | Cách so khớp tên resource | `LITERAL`, `PREFIXED` |
| Principal | Danh tính client sau authentication | `User:orders-app` |
| Host | Địa chỉ nguồn được phép | `*` hoặc địa chỉ IP |
| Operation | Thao tác được kiểm soát | `READ`, `WRITE`, `DESCRIBE`, `ALTER` |
| Permission type | Cho phép hoặc từ chối | `ALLOW`, `DENY` |

Principal thường có dạng `User:<name>` với SASL/SCRAM hoặc principal mapping phù hợp. Khi dùng TLS client authentication, tên principal phụ thuộc certificate principal builder/mapping. Hãy lấy principal thực tế từ cấu hình authentication và broker log; đừng mặc định tên principal luôn bằng username ứng dụng.

## 4. Resource pattern: `LITERAL` và `PREFIXED`

ACL có thể áp dụng cho một resource cụ thể hoặc một nhóm resource có chung tiền tố:

| Pattern | Ví dụ | Phạm vi |
|---|---|---|
| `LITERAL` | `orders.events` | Topic có tên chính xác `orders.events` |
| `PREFIXED` | `orders.` | Các topic có tên bắt đầu bằng `orders.` |

Ví dụ `PREFIXED` có thể cấp quyền cho `orders.created`, `orders.cancelled` và `orders.retry`. Điều này thuận tiện khi một service sở hữu một namespace topic, nhưng cần tránh prefix quá rộng như chuỗi rỗng hoặc `*` nếu không chủ đích.

Khi tạo ACL, dùng `LITERAL` hoặc `PREFIXED`. Các pattern filter trong API truy vấn/xóa còn có thể dùng kiểu lọc như `ANY` hoặc `MATCH` tùy trường hợp; chúng là cách chọn ACL cần thao tác, không phải pattern cấp quyền để tạo mới.

## 5. Operation thường dùng

Một số operation phổ biến:

| Operation | Ý nghĩa khái quát |
|---|---|
| `READ` | Đọc dữ liệu hoặc sử dụng resource trong ngữ cảnh yêu cầu READ |
| `WRITE` | Ghi dữ liệu vào resource |
| `CREATE` | Tạo resource |
| `DELETE` | Xóa resource |
| `ALTER` | Thay đổi resource hoặc cấu hình trong phạm vi được hỗ trợ |
| `DESCRIBE` | Đọc metadata của resource |
| `DESCRIBE_CONFIGS` | Xem cấu hình resource |
| `ALTER_CONFIGS` | Thay đổi cấu hình resource |
| `CLUSTER_ACTION` | Thao tác nội bộ/cluster action theo yêu cầu của một số tính năng |
| `IDEMPOTENT_WRITE` | Quyền cần cho một số luồng producer idempotent khi authorizer kiểm tra cluster resource |
| `ALL` | Tất cả operation áp dụng cho resource đó |

Operation hợp lệ phụ thuộc resource type và Kafka version. Không cấp `ALL` chỉ để khắc phục lỗi authorization mà chưa xác định API nào đang bị từ chối.

### Ví dụ quyền tối thiểu theo workload

| Workload | ACL thường cần xem xét |
|---|---|
| Producer ghi topic | `WRITE` và thường cần `DESCRIBE` trên topic; `CREATE` chỉ khi ứng dụng được phép tạo topic |
| Consumer đọc topic | `READ` và thường cần `DESCRIBE` trên topic; `READ` trên consumer group |
| Producer idempotent | Ngoài quyền topic, có thể cần `IDEMPOTENT_WRITE` trên `CLUSTER` tùy authorizer/version/cấu hình |
| Transactional producer | Quyền trên topic và `WRITE`/`DESCRIBE` trên `TRANSACTIONAL_ID`; quyền cluster liên quan idempotent producer tùy phiên bản |
| Admin quản lý ACL | Quyền quản trị ACL trên cluster theo authorizer và principal được cấu hình |
| Admin thay đổi quota | Quyền quản trị cấu hình/quota theo authorizer và phiên bản Kafka |

Đây là hướng dẫn phân loại quyền, không phải một bộ ACL cố định cho mọi cluster. Một số API kiểm tra nhiều resource trong một thao tác; hãy kiểm tra `AuthorizationException` và broker audit/log để xác định resource/operation thực tế bị từ chối.

## 6. ALLOW, DENY và nguyên tắc cấp quyền

ACL `ALLOW` cho phép principal thực hiện operation phù hợp trên resource. ACL `DENY` từ chối thao tác khi điều kiện principal/host/resource/operation khớp.

Trong mô hình ACL Kafka, một rule DENY khớp có thể chặn quyền được cấp bởi rule ALLOW khác. Vì vậy, không nên tạo DENY rộng như `User:*` hoặc prefix lớn nếu chưa mô phỏng đầy đủ các principal bị ảnh hưởng.

Nguyên tắc thực hành:

- Mặc định từ chối và cấp đúng quyền cần thiết.
- Cấp ACL cho service principal riêng, không dùng chung một user cho nhiều ứng dụng.
- Giới hạn resource theo `LITERAL` nếu chỉ cần một topic.
- Dùng `PREFIXED` khi namespace được quản lý và có owner rõ ràng.
- Hạn chế host bằng IP/network identity khi kiến trúc cho phép; `*` mở rộng phạm vi tới mọi host.
- Không dùng `ALL` nếu chỉ cần `READ` hoặc `WRITE`.
- Kiểm tra ACL hiện tại trước khi thêm DENY hoặc xóa hàng loạt.

## 7. Tạo ACL bằng Kafka Admin API

Ví dụ cấp quyền cho principal `User:orders-app` ghi topic `orders.events` từ mọi host:

```java
import java.util.List;
import java.util.Properties;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.common.acl.AclBinding;
import org.apache.kafka.common.acl.AclOperation;
import org.apache.kafka.common.acl.AclPermissionType;
import org.apache.kafka.common.resource.PatternType;
import org.apache.kafka.common.resource.ResourcePattern;
import org.apache.kafka.common.resource.ResourceType;
import org.apache.kafka.common.acl.AccessControlEntry;

Properties props = new Properties();
props.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(AdminClientConfig.CLIENT_ID_CONFIG, "acl-quota-admin");
// Thêm security.protocol, SASL/TLS properties theo cluster thực tế.

try (AdminClient admin = AdminClient.create(props)) {
    AclBinding binding = new AclBinding(
            new ResourcePattern(
                    ResourceType.TOPIC,
                    "orders.events",
                    PatternType.LITERAL),
            new AccessControlEntry(
                    "User:orders-app",
                    "*",
                    AclOperation.WRITE,
                    AclPermissionType.ALLOW));

    admin.createAcls(List.of(binding))
            .all()
            .get(10, TimeUnit.SECONDS);
}
```

Đoạn code dùng `LITERAL` và chỉ cấp `WRITE` trên một topic. Nếu producer cần metadata topic, hãy xem xét cấp thêm `DESCRIBE`. `AdminClient` phải được tạo bằng principal có quyền quản trị ACL; credential và TLS properties nên lấy từ secret/configuration an toàn.

### Cấp quyền theo prefix

Đổi `PatternType.LITERAL` thành `PatternType.PREFIXED` và tên resource thành `orders.` để áp dụng cho namespace topic. Trước khi dùng prefix, xác nhận không có topic ngoài phạm vi nghiệp vụ đang dùng cùng tiền tố.

## 8. Đọc ACL hiện tại

Để kiểm tra ACL của cluster, dùng `describeAcls()`:

```java
import java.util.Collection;

import org.apache.kafka.common.acl.AclBinding;
import org.apache.kafka.common.acl.AclBindingFilter;

Collection<AclBinding> bindings = admin
        .describeAcls(AclBindingFilter.ANY)
        .values()
        .get(AclBindingFilter.ANY)
        .get(10, TimeUnit.SECONDS);

for (AclBinding binding : bindings) {
    System.out.println(binding);
}
```

`AclBindingFilter.ANY` truy vấn các ACL mà principal hiện tại có quyền xem. Với cluster lớn, có thể tạo filter cụ thể theo resource/principal để giảm dữ liệu trả về. Kết quả describe là cơ sở để xác minh thay đổi và lập kế hoạch thu hồi quyền.

Không ghi toàn bộ ACL hoặc principal nhạy cảm vào log công khai. Kết quả này có thể tiết lộ cấu trúc topic, service identity và quyền truy cập của hệ thống.

## 9. Xóa ACL bằng filter

API xóa ACL nhận danh sách `AclBindingFilter`. Mỗi filter có thể khớp một hoặc nhiều rule; filter càng rộng thì nguy cơ xóa nhầm càng cao.

Ví dụ xóa đúng quyền `WRITE` của `User:orders-app` trên topic literal `orders.events`:

```java
import org.apache.kafka.common.acl.AclBindingFilter;
import org.apache.kafka.common.acl.AccessControlEntryFilter;
import org.apache.kafka.common.resource.ResourcePatternFilter;

AclBindingFilter filter = new AclBindingFilter(
        new ResourcePatternFilter(
                ResourceType.TOPIC,
                "orders.events",
                PatternType.LITERAL),
        new AccessControlEntryFilter(
                "User:orders-app",
                "*",
                AclOperation.WRITE,
                AclPermissionType.ALLOW));

admin.deleteAcls(List.of(filter))
        .all()
        .get(10, TimeUnit.SECONDS);
```

Trước khi xóa, nên `describeAcls()` với filter tương ứng để biết chính xác rule nào sẽ bị ảnh hưởng. Không dùng `AclBindingFilter.ANY` cho thao tác xóa trong routine thông thường. Sau khi xóa, đọc lại ACL và chạy kiểm tra truy cập từ principal liên quan.

## 10. Quota là gì?

Quota giới hạn mức sử dụng tài nguyên của client để một ứng dụng không làm ảnh hưởng quá lớn tới các workload khác. Kafka có thể áp dụng quota theo user, client ID hoặc kết hợp các thuộc tính entity.

Các quota thường gặp:

| Quota key | Đơn vị/ý nghĩa |
|---|---|
| `producer_byte_rate` | Tốc độ dữ liệu producer gửi, tính theo byte/giây |
| `consumer_byte_rate` | Tốc độ dữ liệu consumer nhận, tính theo byte/giây |
| `request_percentage` | Tỷ lệ phần trăm thời gian xử lý request được phân bổ cho client trên broker |

Kafka thực thi quota bằng cơ chế throttle/delay request khi client vượt mức. Quota không phải giới hạn chính xác kiểu “không bao giờ vượt một byte”; request có thể được chấp nhận rồi bị trì hoãn để tốc độ trung bình trở về giới hạn. Client có thể quan sát thời gian throttle trong response và metric.

Quota thường được thực thi theo broker. Khi client kết nối tới nhiều broker, tổng thông lượng quan sát được phụ thuộc số broker, phân bố partition, request routing và cách quota được áp dụng trên từng broker. Không coi `producer_byte_rate=1 MB/s` là cam kết tổng throughput toàn cluster luôn chính xác 1 MB/s cho mọi topology.

## 11. Quota entity: user và client ID

Một quota entity có thể gồm một hoặc nhiều thành phần:

| Entity component | Ví dụ | Mục đích |
|---|---|---|
| `user` | `orders-app` | Áp dụng cho các client xác thực dưới cùng user principal |
| `client-id` | `orders-producer-1` | Áp dụng cho client có `client.id` tương ứng |
| Kết hợp `user` + `client-id` | user `orders-app`, client ID `orders-producer-1` | Giới hạn riêng một client trong phạm vi user |

`client.id` là metadata định danh client do ứng dụng cấu hình; nó không thay thế authentication principal và không phải secret. Nếu chỉ đặt quota theo client ID mà ứng dụng có thể tự đổi client ID, quota không phải cơ chế bảo mật. Dùng user identity để phân tách workload đáng tin cậy, sau đó thêm client ID nếu cần tinh chỉnh.

Quota có thể có cấu hình cụ thể cho entity và cấu hình mặc định theo loại entity. Khi cần quản trị default quota, phải hiểu cách Kafka kết hợp entity cụ thể và entity mặc định ở phiên bản đang chạy; không suy ra rằng quota của user và quota của client ID luôn cộng hoặc thay thế nhau theo một phép tính đơn giản.

## 12. Thay đổi quota bằng `alterClientQuotas()`

Ví dụ đặt giới hạn producer 1 MiB/s và consumer 2 MiB/s cho user `orders-app`:

```java
import java.util.List;
import java.util.Map;

import org.apache.kafka.clients.admin.ClientQuotaAlteration;
import org.apache.kafka.clients.admin.ClientQuotaEntity;

ClientQuotaEntity entity = new ClientQuotaEntity(
        Map.of(ClientQuotaEntity.USER, "orders-app"));

ClientQuotaAlteration alteration = new ClientQuotaAlteration(
        entity,
        List.of(
                new ClientQuotaAlteration.Op("producer_byte_rate", 1_048_576.0),
                new ClientQuotaAlteration.Op("consumer_byte_rate", 2_097_152.0),
                new ClientQuotaAlteration.Op("request_percentage", 25.0)));

admin.alterClientQuotas(List.of(alteration))
        .all()
        .get(10, TimeUnit.SECONDS);
```

Giá trị `request_percentage=25` là 25% theo quota metric của broker, không phải 25% CPU máy chủ theo cách đo tùy ý của ứng dụng. Các quota key được hỗ trợ và cách đo có thể khác theo Kafka version; xác minh với cluster trước khi áp dụng.

### Quota theo user và client ID kết hợp

```java
ClientQuotaEntity entity = new ClientQuotaEntity(Map.of(
        ClientQuotaEntity.USER, "orders-app",
        ClientQuotaEntity.CLIENT_ID, "orders-producer-1"));
```

Entity kết hợp giúp đặt quota cụ thể cho một client của một user. Cần chọn `client.id` ổn định và duy nhất theo workload để metric và quota dễ quản trị.

## 13. Đọc quota đã cấu hình

Dùng `describeClientQuotas()` với filter theo entity:

```java
import java.util.Map;

import org.apache.kafka.clients.admin.ClientQuotaFilter;
import org.apache.kafka.clients.admin.ClientQuotaFilterComponent;

ClientQuotaFilter filter = ClientQuotaFilter.contains(
        ClientQuotaFilterComponent.ofEntity(
                ClientQuotaEntity.USER, "orders-app"));

Map<ClientQuotaEntity, Map<String, Double>> quotas = admin
        .describeClientQuotas(filter)
        .entities()
        .get(10, TimeUnit.SECONDS);

quotas.forEach((quotaEntity, values) ->
        System.out.println(quotaEntity + " -> " + values));
```

Filter `contains` cho phép tìm entity có thành phần user tương ứng; entity có thể còn chứa client ID nếu quota được cấu hình theo tổ hợp. Nếu cần khớp chính xác toàn bộ entity, dùng filter chính xác phù hợp với API version và kiểm tra kết quả trả về.

## 14. Gỡ một quota

Để xóa một quota key khỏi entity, truyền giá trị `null` cho operation tương ứng:

```java
ClientQuotaAlteration removeProducerRate = new ClientQuotaAlteration(
        entity,
        List.of(new ClientQuotaAlteration.Op("producer_byte_rate", null)));

admin.alterClientQuotas(List.of(removeProducerRate))
        .all()
        .get(10, TimeUnit.SECONDS);
```

Thao tác này loại bỏ cấu hình `producer_byte_rate` của entity cụ thể. Sau khi xóa, Kafka có thể áp dụng quota phù hợp khác từ entity/default configuration. Nó không có nghĩa là producer được miễn mọi quota.

Để gỡ nhiều key, thêm một `Op(key, null)` cho từng key. Trước khi xóa quota, đọc cấu hình hiện tại và xác định default quota nào sẽ có hiệu lực sau thao tác.

## 15. `AdminClient` trong Spring Boot

Trong ứng dụng Spring, có thể tạo một bean `AdminClient` dùng chung cho các service quản trị:

```java
import org.apache.kafka.clients.admin.AdminClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaAdmin;

@Configuration
public class KafkaAdminApiConfiguration {

    @Bean(destroyMethod = "close")
    AdminClient kafkaAdminClient(KafkaAdmin kafkaAdmin) {
        return AdminClient.create(kafkaAdmin.getConfigurationProperties());
    }
}
```

Bean này dùng cấu hình từ `KafkaAdmin`, bao gồm bootstrap server và security properties đã khai báo trong Spring Boot. Tên method/cách expose configuration có thể khác theo Spring Kafka version; nếu dự án quản lý nhiều cluster hoặc nhiều principal, nên tạo AdminClient riêng theo cluster và mục đích quản trị.

Không inject AdminClient quản trị quyền cao vào mọi business service. Có thể tách một provisioning/admin service có API nội bộ được xác thực và audit, còn producer/consumer chỉ nhận credential quyền tối thiểu của mình.

## 16. Xử lý lỗi và timeout của Admin API

Admin API bất đồng bộ và có thể gặp các lỗi:

| Lỗi/hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `AuthorizationException` | Principal không có quyền thực hiện thao tác quản trị hoặc truy cập resource | Xác minh principal, authorizer và resource/operation cần cấp |
| `ClusterAuthorizationException` | Thiếu quyền trên cluster cho API quản trị | Cấp quyền quản trị tối thiểu theo authorizer/version; không nâng thành superuser ngay |
| `InvalidRequestException` | ACL/filter/quota entity hoặc giá trị không hợp lệ | Kiểm tra resource type, pattern, operation, entity key và quota key |
| `UnsupportedVersionException` | Broker không hỗ trợ API version/feature client yêu cầu | Dùng client tương thích hoặc nâng cấp broker theo kế hoạch |
| `TimeoutException` | Broker/coordinator/network không trả kết quả đúng hạn | Kiểm tra cluster health và kết quả trạng thái trước khi gửi lại thao tác |
| `SaslAuthenticationException` / lỗi TLS | Credential, mechanism hoặc certificate sai | Kiểm tra cấu hình bảo mật và secret/certificate |
| Một phần thao tác thành công | Batch có nhiều ACL/entity và một số phần tử lỗi | Kiểm tra kết quả theo từng filter/entity; không giả định cả batch rollback |

Với `createAcls`, `deleteAcls` và `alterClientQuotas`, cần phân biệt timeout với thao tác chắc chắn thất bại. Nếu client timeout sau khi broker đã áp dụng thay đổi, gửi lại có thể không tạo kết quả như dự kiến hoặc tác động lên trạng thái mới hơn. Sau timeout, gọi describe để xác minh trạng thái hiện tại trước khi retry.

Đặt timeout chờ future trong ứng dụng và cấu hình request timeout phù hợp. Không block event loop hoặc request thread quan trọng trong thời gian dài chỉ để chờ thao tác Admin API.

## 17. Quy trình thay đổi ACL/quota an toàn

Một quy trình vận hành có thể gồm:

1. Xác định owner, principal, resource và lý do thay đổi.
2. Đọc ACL/quota hiện tại bằng `describeAcls()` hoặc `describeClientQuotas()`.
3. Xây dựng thay đổi nhỏ nhất đáp ứng yêu cầu; xác định rõ literal/prefix, host, operation và quota entity.
4. Review tác động tới producer, consumer, transactional producer và workload khác.
5. Áp dụng trước trên môi trường staging hoặc một principal/topic thử nghiệm.
6. Gọi Admin API và chờ kết quả với timeout.
7. Đọc lại cấu hình sau thay đổi để xác minh.
8. Kiểm tra truy cập thực tế bằng principal liên quan và theo dõi throttle/authorization error.
9. Lưu audit: người yêu cầu, người duyệt, thời điểm, diff trước/sau và lý do.
10. Có phương án rollback cụ thể, không xóa ACL/quota rộng khi chưa xác định trạng thái ban đầu.

Admin API không cung cấp một dry-run tổng quát bảo đảm mô phỏng mọi tác động của ACL/quota. Có thể xây dựng bước preview trong tooling bằng cách đọc trạng thái hiện tại và tính diff, nhưng preview của ứng dụng không thay thế kiểm thử trên cluster.

## 18. Theo dõi quota và tác động tới client

Khi quota bị vượt, broker có thể throttle request thay vì từ chối ngay. Ứng dụng nên quan sát:

- Producer `produce-throttle-time-avg` và `produce-throttle-time-max`.
- Consumer `fetch-throttle-time-avg` và `fetch-throttle-time-max`.
- Request latency, request rate và throughput theo client ID/user.
- Consumer lag và producer delivery latency.
- Broker request queue, network processor và request handler utilization.
- Sự khác biệt giữa client có quota và client không có quota.

Tên metric phụ thuộc Kafka client/broker version và hệ thống exporter. Quota quá thấp có thể làm consumer lag tăng hoặc producer delivery timeout xảy ra nếu ứng dụng không tính thời gian throttle vào deadline. Quota quá cao có thể không tạo được sự cô lập tài nguyên mong muốn.

Nên điều chỉnh quota bằng cách quan sát tải baseline và tải đỉnh, sau đó thay đổi từng bước. Quota không thay thế capacity planning, partition planning hoặc giới hạn concurrency ở ứng dụng.

## 19. Ví dụ chính sách cho hệ thống orders

Giả sử hệ thống có:

- Producer `orders-app` ghi `orders.events`.
- Consumer `billing-app` đọc `orders.events` trong group `billing-workers`.
- Producer `orders-app` có `client.id=orders-producer-1`.

Một chính sách tối thiểu có thể là:

| Principal | Resource | Operation | Permission |
|---|---|---|---|
| `User:orders-app` | Topic `orders.events` (LITERAL) | `WRITE`, `DESCRIBE` | ALLOW |
| `User:billing-app` | Topic `orders.events` (LITERAL) | `READ`, `DESCRIBE` | ALLOW |
| `User:billing-app` | Group `billing-workers` (LITERAL) | `READ` | ALLOW |

Quota có thể đặt cho user `orders-app` và tinh chỉnh thêm theo client ID `orders-producer-1`, ví dụ `producer_byte_rate` và `request_percentage`. Giá trị quota phải dựa trên throughput cần thiết và capacity broker, không chọn tùy ý.

Nếu `orders-app` dùng transactional producer, bổ sung ACL trên transactional ID tương ứng và quyền cluster cần thiết theo cấu hình. Không cấp quyền đọc topic cho producer chỉ vì producer cần ghi; tách quyền theo vai trò thực tế.

## 20. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Producer bị `TopicAuthorizationException` | Thiếu `WRITE` hoặc `DESCRIBE` trên topic | Xác định principal thật và cấp đúng operation trên topic |
| Consumer bị `GroupAuthorizationException` | Thiếu `READ` trên group hoặc group ID không khớp ACL | Kiểm tra `group.id` và ACL resource `GROUP` |
| ACL tồn tại nhưng client vẫn bị từ chối | Principal mapping/host/resource pattern/operation không khớp hoặc có DENY | Describe ACL, kiểm tra broker log và principal thực tế |
| ACL prefix cấp rộng hơn dự kiến | Dùng `PREFIXED` với namespace chung | Thu hẹp prefix hoặc chuyển sang `LITERAL` |
| Xóa ACL làm service khác mất quyền | Filter xóa khớp nhiều binding hơn dự kiến | Describe trước, dùng filter cụ thể và lưu diff/rollback |
| Admin API bị authorization exception | AdminClient dùng principal không có quyền quản trị | Cấp quyền quản trị tối thiểu hoặc dùng principal quản trị riêng |
| Producer bị throttle | Quota producer byte rate hoặc request percentage thấp | Describe quota, kiểm tra client identity và điều chỉnh theo capacity |
| Client ID quota không áp dụng | `client.id` runtime khác giá trị entity | Kiểm tra cấu hình client ID và entity trong quota |
| Quota xóa nhưng client vẫn bị giới hạn | Có quota cụ thể/default khác còn hiệu lực | Describe các entity liên quan và kiểm tra quota kế thừa/áp dụng |
| Admin future timeout nhưng thay đổi đã có hiệu lực | Broker áp dụng xong nhưng response bị mất | Describe trạng thái trước khi retry |

## 21. Checklist production

**ACL:**

- Authorizer được bật và tương thích với kiến trúc/version Kafka.
- Có principal quản trị bootstrap/superuser được bảo vệ.
- Principal ứng dụng tách biệt theo service.
- Resource type, tên, pattern, host và operation được xác định cụ thể.
- Dùng `LITERAL` mặc định; chỉ dùng `PREFIXED` khi namespace được quản lý.
- Kiểm tra DENY và ALLOW trước khi thay đổi.
- Producer, consumer, group và transactional ID có đúng quyền tối thiểu.
- Admin API principal có quyền quản trị nhưng không chia sẻ với workload thường.

**Quota:**

- Chọn entity theo user, client ID hoặc tổ hợp có chủ đích.
- Dùng đơn vị byte/giây và phần trăm request đúng semantics.
- Xác minh quota key được broker version hỗ trợ.
- Đo baseline và tải đỉnh trước khi đặt giới hạn.
- Theo dõi throttle time, request latency, throughput và consumer lag.
- Kiểm tra quota cụ thể và default quota sau khi thay đổi/xóa.

**Vận hành Admin API:**

- Đặt timeout cho AdminClient future.
- Xử lý kết quả theo từng ACL/entity khi batch có phần tử lỗi.
- Sau timeout, describe để xác minh trước khi retry.
- Ghi audit và lưu diff trước/sau.
- Có phương án rollback và kiểm thử staging.
- Đóng AdminClient theo vòng đời ứng dụng.

## 22. Ghi nhớ

ACL xác định principal được phép thực hiện operation nào trên resource nào. Một binding kết hợp resource pattern (`TOPIC`, `GROUP`, `CLUSTER`, `TRANSACTIONAL_ID`...), principal, host, operation và permission `ALLOW`/`DENY`. `LITERAL` giới hạn đúng tên resource; `PREFIXED` áp dụng cho namespace. Cấp quyền tối thiểu và kiểm tra cả DENY lẫn ALLOW trước khi thay đổi.

Quota giới hạn producer byte rate, consumer byte rate hoặc request percentage theo user/client ID entity. Khi vượt quota, broker thường throttle request để điều tiết tốc độ; quota không phải cam kết throughput tổng toàn cluster. Dùng `AdminClient` để tạo/xem/xóa ACL và thay đổi/xem quota, luôn đặt timeout, xác minh trạng thái sau thao tác và lưu audit. Quản lý ACL/quota theo quy trình có kiểm soát giúp bảo vệ cluster và phân chia tài nguyên công bằng giữa các workload.
