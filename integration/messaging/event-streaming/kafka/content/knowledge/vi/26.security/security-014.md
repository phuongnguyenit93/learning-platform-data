# Kiểm tra quyền, ghi nhận hoạt động quản trị và ứng phó lộ thông tin

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, hiểu topic, partition, offset, producer, consumer group, replication và KRaft; triển khai luồng sự kiện Java/Spring Kafka, xử lý retry, ordering và giao dịch; tích hợp Kafka Connect/Streams rồi giám sát, tối ưu và phục hồi cụm. Bài học này tập trung vào vòng đời quyền truy cập: kiểm tra ACL đang có hiệu lực, rà soát quyền thừa, ghi lại thay đổi quản trị và xử lý khi password, token, certificate hoặc credential bị lộ.

Một Kafka cluster có thể đã bật TLS và SASL nhưng vẫn không an toàn nếu service account dùng chung, ACL cấp quá rộng, quyền quản trị không được audit hoặc credential bị lộ mà không được thu hồi. Bảo mật vận hành cần trả lời được ba câu hỏi: ai đang có quyền gì, ai đã thay đổi điều gì và cần làm gì khi danh tính bị xâm phạm.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích mối quan hệ giữa authentication, authorization và audit.
- Đọc cấu trúc ACL gồm principal, resource, operation, permission type, host và pattern type.
- Kiểm tra ACL bằng kafka-acls CLI và Kafka AdminClient.
- Đánh giá quyền hiệu lực từ literal, prefixed và wildcard resource pattern.
- Nhận diện quyền rộng, principal không còn owner và super user ngoài kiểm soát.
- Xây dựng ma trận service account, topic, consumer group và quyền cần thiết.
- Kiểm thử cả truy cập được phép và bị từ chối bằng đúng credential của workload.
- Ghi audit cho thay đổi ACL, topic, config, connector và schema.
- Phân biệt broker security log với audit trail đầy đủ của hoạt động dữ liệu.
- Quản lý vòng đời password, token, certificate và secret.
- Ứng phó khi lộ credential của producer, consumer, admin hoặc Connect worker.
- Thu thập bằng chứng, khoanh vùng ảnh hưởng, thu hồi quyền và xác minh phục hồi.
- Thiết kế access review định kỳ và quy trình break-glass có kiểm soát.

## 2. Authentication, authorization và audit

Ba cơ chế giải quyết ba câu hỏi khác nhau:

| Cơ chế | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Ai đang kết nối? | User orders-api xác thực bằng SCRAM hoặc client certificate |
| Authorization | Danh tính đó được làm gì? | orders-api được Write vào topic orders |
| Audit | Ai đã làm gì, lúc nào và kết quả ra sao? | Admin A thêm ACL Write cho principal orders-api lúc 09:15 |

Authentication thành công không có nghĩa client được phép đọc hoặc ghi mọi topic. ACL đúng cũng không giúp điều tra nếu không ghi nhận ai đã cấp quyền. Audit tốt không thay thế authorization: phát hiện hành động trái phép sau khi xảy ra vẫn có thể quá muộn.

~~~mermaid
flowchart TD
    A[Client request] --> B[Authenticate identity]
    B --> C{Identity valid?}
    C -->|No| D[Reject and record auth failure]
    C -->|Yes| E[Resolve Kafka principal]
    E --> F[Authorize resource and operation]
    F --> G{Allowed?}
    G -->|No| H[Reject and record denial]
    G -->|Yes| I[Execute request]
    I --> J[Record audit event where required]
    D --> K[Central security monitoring]
    H --> K
    J --> K
~~~

Audit event cần cho biết request đến từ đâu, dùng principal nào, thao tác trên resource nào và kết quả gì. Với thao tác quản trị, nên lưu cả thay đổi trước/sau hoặc hash của snapshot đã được loại bỏ secret.

## 3. Đọc cấu trúc Kafka ACL

ACL (Access Control List) mô tả principal nào được thực hiện operation trên resource nào, từ host nào và theo loại permission nào.

Một ACL gồm các thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Principal | Danh tính Kafka đã xác thực | User:orders-api |
| Host | Địa chỉ nguồn được áp dụng | * hoặc địa chỉ IP |
| Operation | Hành động được kiểm soát | Read, Write, Describe, Create, Delete |
| Permission type | Allow hoặc Deny | ALLOW |
| Resource type | Loại resource | TOPIC, GROUP, CLUSTER, TRANSACTIONAL_ID |
| Resource name | Tên resource | orders |
| Pattern type | Cách khớp tên resource | LITERAL, PREFIXED |

Principal string phụ thuộc authentication mechanism và principal mapping. Với SASL/SCRAM, principal thường có dạng User:username; với mTLS, principal có thể được tạo từ certificate identity theo cấu hình broker.

### 3.1. Các operation thường gặp

| Operation | Dùng cho |
|---|---|
| Read | Đọc topic hoặc sử dụng consumer group tùy resource |
| Write | Ghi record vào topic hoặc thao tác transactional ID tùy resource |
| Create | Tạo resource theo phạm vi được phép |
| Delete | Xóa resource |
| Alter | Thay đổi resource hoặc ACL theo loại resource |
| Describe | Xem metadata resource |
| DescribeConfigs | Đọc cấu hình |
| AlterConfigs | Thay cấu hình |
| ClusterAction | Một số hoạt động nội bộ giữa broker |
| IdempotentWrite | Quyền liên quan đến idempotent producer trong các trường hợp cần thiết |

Operation hợp lệ phụ thuộc resource type và phiên bản Kafka. Không suy luận một quyền trên TOPIC tự động cho phép cùng operation trên GROUP hoặc CLUSTER.

### 3.2. Resource pattern

Kafka hỗ trợ các kiểu pattern chính:

- **LITERAL:** khớp đúng tên resource.
- **PREFIXED:** khớp các resource có tên bắt đầu bằng prefix.
- **MATCH:** thường dùng trong filter/query để tìm các pattern phù hợp; không phải kiểu cấp ACL thông thường trong mọi thao tác.

Ví dụ:

~~~text
LITERAL topic orders
  -> chỉ áp dụng cho topic orders

PREFIXED topic orders-
  -> áp dụng cho topic orders-created, orders-paid, orders-dlq...
~~~

PREFIXED thuận tiện cho service sở hữu một nhóm topic, nhưng có thể mở rộng quyền đến topic mới được tạo sau này. Chỉ dùng prefix khi naming convention và ownership rõ ràng.

### 3.3. Allow, deny và quyền mặc định

Khi một ACL phù hợp với request:

- ACL ALLOW cho phép operation.
- ACL DENY từ chối operation.
- Quy tắc DENY phù hợp có độ ưu tiên cao hơn ALLOW phù hợp.
- Nếu không có ACL phù hợp, kết quả phụ thuộc allow.everyone.if.no.acl.found.
- Super user được cấu hình trong super.users có quyền vượt qua ACL thông thường.

Trong production, thường đặt allow.everyone.if.no.acl.found=false để mặc định từ chối khi không có ACL phù hợp. Kiểm tra cấu hình authorizer thực tế thay vì giả định mọi cluster dùng cùng default.

Một ACL ALLOW trên topic không có nghĩa principal được phép đọc mọi topic. Nhưng ACL PREFIXED, wildcard principal/host hoặc super user có thể tạo phạm vi lớn hơn tên resource được nhìn thấy trong một dòng ACL. Cần đánh giá quyền hiệu lực, không chỉ đếm số ACL.

## 4. Xây dựng ma trận quyền theo service

Trước khi rà soát ACL, lập danh sách principal và owner. Một principal không có owner hoặc không còn workload sử dụng là ứng viên cần điều tra.

Ví dụ ma trận:

| Principal | Resource | Quyền cần thiết | Owner | Ghi chú |
|---|---|---|---|---|
| User:orders-producer | TOPIC orders | Write, Describe nếu cần | Orders API team | Chỉ phát event đơn hàng |
| User:orders-consumer | TOPIC orders | Read, Describe | Order worker team | Đọc event đơn hàng |
| User:orders-consumer | GROUP orders-service | Read | Order worker team | Join group và commit offset |
| User:payments-streams | TOPIC payments | Read | Payments team | Input topology |
| User:payments-streams | TOPIC prefix payments-enriched- (PREFIXED) | Write | Payments team | Output/repartition theo policy |
| User:connect-worker | Internal Connect topics | Quyền cần cho worker | Data integration team | Không dùng chung với app nghiệp vụ |
| User:kafka-admin-automation | CLUSTER và resource quản trị | Chỉ quyền quản trị được phê duyệt | Platform team | Credential tách riêng |

Đây là ví dụ định hướng. Kafka Streams và Kafka Connect có thể cần quyền bổ sung cho consumer group, transactional ID, internal topic hoặc topic được tạo tự động. Hãy lấy topology/config thực tế và kiểm thử bằng đúng principal trước khi thu hồi ACL.

### 4.1. Tách identity theo workload

Không dùng một user chung cho producer, consumer, Connect và admin. Khi identity bị lộ, phạm vi quyền của nó quyết định phạm vi sự cố.

Mỗi service account nên có:

- Tên gắn với service và môi trường.
- Owner chịu trách nhiệm.
- Mục đích sử dụng.
- Resource được phép truy cập.
- Credential và cơ chế rotation.
- Ngày tạo, ngày rà soát và ngày hết hạn nếu có.
- Quy trình thu hồi khi service ngừng hoạt động.

Không tái sử dụng credential production trong local development, CI test hoặc staging.

## 5. Kiểm tra ACL bằng kafka-acls CLI

Dùng kafka-acls.sh để liệt kê ACL. Lệnh cần kết nối bằng principal có quyền Describe ACL trên cluster.

Liệt kê toàn bộ ACL:

~~~bash
kafka-acls.sh --bootstrap-server broker-1.internal:9093 --command-config admin-client.properties --list
~~~

Lọc ACL liên quan đến topic orders:

~~~bash
kafka-acls.sh --bootstrap-server broker-1.internal:9093 --command-config admin-client.properties --list --topic orders
~~~

Lọc theo consumer group:

~~~bash
kafka-acls.sh --bootstrap-server broker-1.internal:9093 --command-config admin-client.properties --list --group orders-service
~~~

Cấu hình admin-client.properties phải dùng TLS/SASL và credential quản trị được bảo vệ. Không đặt password thật trực tiếp trong command line hoặc shell history.

### 5.1. Đọc output ACL

Ví dụ output minh họa:

~~~text
Current ACLs for resource ResourcePattern(resourceType=TOPIC, name=orders, patternType=LITERAL):
  (principal=User:orders-producer, host=*, operation=WRITE, permissionType=ALLOW)
  (principal=User:orders-producer, host=*, operation=DESCRIBE, permissionType=ALLOW)
  (principal=User:orders-consumer, host=*, operation=READ, permissionType=ALLOW)
~~~

Cần xác định:

- Principal có đúng workload không?
- Host là * hay bị giới hạn?
- Operation có đúng nhiệm vụ không?
- Resource pattern là LITERAL hay PREFIXED?
- Có ACL DENY nào ảnh hưởng không?
- Có super user hoặc wildcard principal không?
- ACL có owner và change ticket không?

Không kết luận quyền hiệu lực chỉ từ một dòng ACL. Một principal có thể nhận quyền qua nhiều pattern hoặc có đặc quyền super user.

### 5.2. Kiểm tra credential metadata

Với SCRAM, có thể mô tả user configuration bằng kafka-configs.sh:

~~~bash
kafka-configs.sh --bootstrap-server broker-1.internal:9093 --command-config admin-client.properties --describe --entity-type users --entity-name orders-producer
~~~

Lệnh này không hiển thị password gốc. Nó giúp xác nhận credential mechanism đã được cấu hình; việc xác minh credential còn hoạt động phải thực hiện bằng một client test có kiểm soát.

Không gửi password thật qua lệnh chia sẻ, ảnh chụp màn hình hoặc log. Nếu credential đã bị lộ, không dùng lệnh describe để kết luận nó còn an toàn.

## 6. Kiểm tra ACL bằng Kafka AdminClient

Kafka AdminClient cung cấp API để liệt kê và thay đổi ACL. Công cụ nội bộ có thể dùng API này để tạo báo cáo access review hoặc so sánh ACL thực tế với desired policy.

Ví dụ liệt kê ACL:

~~~java
import org.apache.kafka.clients.admin.AclBinding;
import org.apache.kafka.clients.admin.AclBindingFilter;
import org.apache.kafka.clients.admin.AdminClient;

import java.util.Collection;
import java.util.Properties;

public class AclInventory {

    public static void main(String[] args) throws Exception {
        Properties properties = new Properties();
        properties.put(
            "bootstrap.servers",
            "broker-1.internal:9093"
        );
        // Bổ sung security.protocol, SASL/TLS và secret
        // từ cấu hình runtime an toàn.

        try (AdminClient admin = AdminClient.create(properties)) {
            Collection<AclBinding> bindings =
                admin.describeAcls(AclBindingFilter.ANY)
                    .values()
                    .get();

            for (AclBinding binding : bindings) {
                System.out.printf(
                    "resource=%s principal=%s host=%s operation=%s permission=%s%n",
                    binding.pattern(),
                    binding.entry().principal(),
                    binding.entry().host(),
                    binding.entry().operation(),
                    binding.entry().permissionType()
                );
            }
        }
    }
}
~~~

describeAcls cần quyền Describe trên CLUSTER. Việc trả về ACL phụ thuộc authorizer và phạm vi request. Nếu API bị từ chối, hãy kiểm tra principal quản trị và ACL cluster-level.

### 6.1. Tạo một ACL bằng AdminClient

Ví dụ tạo quyền Write cho principal orders-producer trên topic literal orders:

~~~java
import org.apache.kafka.clients.admin.AclBinding;
import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.common.acl.AccessControlEntry;
import org.apache.kafka.common.acl.AclOperation;
import org.apache.kafka.common.acl.AclPermissionType;
import org.apache.kafka.common.resource.PatternType;
import org.apache.kafka.common.resource.ResourcePattern;
import org.apache.kafka.common.resource.ResourceType;

import java.util.List;

ResourcePattern resource = new ResourcePattern(
    ResourceType.TOPIC,
    "orders",
    PatternType.LITERAL
);

AccessControlEntry entry = new AccessControlEntry(
    "User:orders-producer",
    "*",
    AclOperation.WRITE,
    AclPermissionType.ALLOW
);

AclBinding binding = new AclBinding(resource, entry);

// admin là AdminClient đã được khởi tạo với cấu hình bảo mật phù hợp.
admin.createAcls(List.of(binding)).all().get();
~~~

Tạo ACL yêu cầu quyền Alter trên CLUSTER. Trong ứng dụng thật, cần xử lý ACL đã tồn tại, lỗi authorization và timeout; sau timeout, đọc lại ACL trước khi retry để xác định request trước đã được áp dụng hay chưa.

### 6.2. Thu hồi ACL

Có thể dùng CLI để xóa ACL cụ thể:

~~~bash
kafka-acls.sh --bootstrap-server broker-1.internal:9093 --command-config admin-client.properties --remove --allow-principal User:orders-producer --operation Write --topic orders
~~~

Trước khi xóa, xác nhận chính xác principal, resource pattern, operation và host. Nếu principal có nhiều ACL, xóa một ACL không đồng nghĩa thu hồi toàn bộ quyền. Sau thao tác, liệt kê lại ACL và kiểm thử cả truy cập được phép lẫn bị từ chối.

## 7. Đánh giá quyền hiệu lực và phát hiện quyền thừa

Access review không chỉ tìm ACL sai. Nó phải xác định quyền mà principal thực sự có thể sử dụng.

Các dấu hiệu cần xem xét:

- Principal có ACL trên mọi topic hoặc prefix quá rộng.
- Host là * trong khi workload chỉ chạy từ một network zone.
- ACL DENY và ALLOW chồng lấn gây khó hiểu.
- Principal được cấp Create hoặc Delete nhưng không phải workload quản trị.
- Consumer được Read trên nhiều topic không liên quan.
- Producer có quyền Read hoặc Alter không cần thiết.
- Service account được cấp All trên CLUSTER.
- Principal nằm trong super.users dù chỉ là service nghiệp vụ.
- ACL không có owner, mục đích hoặc ngày rà soát.
- User credential còn tồn tại sau khi service đã decommission.
- ACL prefixed cho phép truy cập các topic mới ngoài dự kiến.
- Connector hoặc Streams application dùng identity chia sẻ.

### 7.1. Rà soát theo nguyên tắc least privilege

Với từng principal:

1. Xác định owner và workload đang dùng.
2. Liệt kê topic, group, transactional ID và cluster resource được truy cập.
3. So sánh operation với nhiệm vụ thực tế.
4. Kiểm tra literal/prefixed pattern và host restriction.
5. Kiểm tra quyền quản trị và super user.
6. Xác định credential còn hoạt động và lần sử dụng gần nhất nếu telemetry có.
7. Ghi đề xuất giữ, thu hẹp, chuyển owner hoặc thu hồi.
8. Thử policy mới trên staging hoặc principal thử nghiệm.
9. Thực hiện thay đổi có audit và kế hoạch rollback.
10. Kiểm thử lại workload hợp lệ sau thay đổi.

Không xóa ACL chỉ vì tên principal lạ. Trước tiên xác minh owner, dependency, connector và application.id; thu hồi nhầm quyền có thể làm gián đoạn pipeline production.

### 7.2. Access review theo chu kỳ

Tổ chức có thể chọn chu kỳ hàng tháng, hàng quý hoặc theo mức độ nhạy cảm. Review bổ sung sau các sự kiện:

- Nhân sự hoặc nhóm vận hành thay đổi.
- Service được decommission.
- Connector/plugin được cài mới.
- Topic hoặc data classification thay đổi.
- Credential bị lộ.
- Thay đổi listener, authorizer hoặc identity provider.
- Kết quả pentest hoặc audit phát hiện quyền quá rộng.

Kết quả review cần lưu người thực hiện, người phê duyệt, ACL giữ lại, ACL thu hồi và thời hạn xử lý ngoại lệ.

## 8. Ghi nhận hoạt động quản trị

Audit trail là bằng chứng có thể truy vết về hành động quản trị và thay đổi quyền. Một dòng log thông báo authorization denied chưa phải audit trail đầy đủ.

Kafka có broker/controller logs và log liên quan đến authentication/authorization. Tuy nhiên, không nên mặc định Kafka tự cung cấp một audit record hoàn chỉnh cho mọi lần đọc từng record, mọi thay đổi ở ứng dụng ngoài hoặc mọi thao tác trên Connect REST/Schema Registry. Phạm vi log và nội dung chi tiết phụ thuộc phiên bản, cấu hình logger, authorizer và dịch vụ tích hợp.

### 8.1. Những hoạt động cần audit

| Nhóm | Hoạt động cần ghi |
|---|---|
| Identity | Tạo, disable, rotate hoặc xóa principal/credential |
| ACL | Add, remove, alter và list ACL khi dùng để review |
| Topic | Create, delete, alter config, tăng partition |
| Consumer group | Thay đổi hoặc reset offset bởi admin |
| Transaction | Thay đổi quyền transactional ID hoặc cấu hình liên quan |
| KRaft/cluster | Thay đổi security config, listener và super user |
| Kafka Connect | Create, update, pause, resume, restart, delete connector |
| Schema Registry | Register, update compatibility, delete schema |
| Secret provider | Đọc, rotate hoặc revoke secret/certificate |
| Admin access | Đăng nhập, truy cập UI, dùng break-glass và phê duyệt |

### 8.2. Trường thông tin của audit event

Một audit event quản trị nên có:

| Trường | Mục đích |
|---|---|
| event_time | Thời điểm xảy ra theo UTC |
| actor | Người hoặc automation khởi tạo |
| principal | Kafka principal hoặc identity của REST API |
| source_ip / source_host | Nguồn request |
| action | CREATE_ACL, DELETE_TOPIC, UPDATE_CONNECTOR... |
| resource_type | TOPIC, GROUP, CLUSTER, CONNECTOR... |
| resource_name | Tên resource bị tác động |
| before / after | Snapshot hoặc diff đã redact |
| result | SUCCESS, DENIED, FAILED |
| reason | Lý do hoặc change ticket |
| request_id | Correlation ID để nối log |
| approver | Người phê duyệt nếu thao tác cần approval |

Không ghi password, SASL JAAS config, bearer token, private key hoặc payload nhạy cảm vào audit log. Với cấu hình có secret, chỉ ghi tên secret reference, version hoặc hash phù hợp.

### 8.3. Audit thao tác quản trị qua automation

Cách đáng tin cậy để ghi nhận thay đổi ACL/topic là đưa thao tác qua một lớp automation có kiểm soát:

1. Xác thực người yêu cầu.
2. Kiểm tra quyền và change ticket.
3. Đọc trạng thái hiện tại.
4. Tính diff so với desired state.
5. Ghi audit event trước khi thay đổi.
6. Gọi AdminClient hoặc CLI wrapper.
7. Đọc lại trạng thái sau thay đổi.
8. Ghi kết quả, diff và request ID.
9. Gửi log tới hệ thống tập trung.

Nếu quản trị viên chạy lệnh trực tiếp trên broker host, cần có shell audit hoặc session recording phù hợp để vẫn ghi nhận được thao tác. Không nên phụ thuộc vào lời khai thủ công sau sự cố.

### 8.4. Audit đọc và ghi dữ liệu

Kafka authorization thường kiểm soát quyền ở cấp resource và operation, không phải ghi audit business event cho từng record đã được consumer đọc hoặc producer ghi.

Nếu cần chứng minh dữ liệu nào được truy cập ở cấp nghiệp vụ:

- Ghi audit tại application/service boundary.
- Ghi principal, topic, business request ID và mục đích truy cập.
- Không log toàn bộ payload nếu không cần.
- Dùng trace/correlation ID để nối service log với Kafka client log.
- Kết hợp broker metrics, network telemetry và log của consumer/producer.
- Đặt retention và quyền truy cập cho audit data riêng.

Một consumer có ACL Read không chứng minh nó đã đọc từng record; ngược lại, absence của một log record cũng không chứng minh dữ liệu chưa bị truy cập nếu audit chưa được bật đầy đủ.

## 9. Bảo vệ audit log và bằng chứng

Audit chỉ hữu ích khi log không thể bị người bị điều tra sửa hoặc xóa dễ dàng.

Các nguyên tắc:

- Gửi log đến hệ thống tập trung độc lập với Kafka cluster đang được bảo vệ.
- Giới hạn người có quyền đọc, xóa hoặc thay đổi retention.
- Dùng immutable storage hoặc retention lock khi yêu cầu tuân thủ cần.
- Đồng bộ thời gian giữa broker, controller, worker và hệ thống audit.
- Theo dõi log pipeline bị gián đoạn hoặc mất event.
- Tách quyền vận hành Kafka khỏi quyền xóa audit.
- Mã hóa log và backup; tránh lưu secret trong log.
- Kiểm tra khả năng truy vấn lại log trong thời gian retention.
- Lưu request ID và change ticket để đối chiếu nhiều hệ thống.

Nếu audit pipeline bị ngừng, cần cảnh báo riêng. Không được coi việc không có cảnh báo là bằng chứng không có hoạt động đáng ngờ khi nguồn log đang mất dữ liệu.

## 10. Quản lý vòng đời credential

Credential có thể là SCRAM password, OAuth token, client certificate, private key, cloud IAM role, REST API credential hoặc secret cho connector.

| Loại credential | Nơi xác thực | Hành động khi bị lộ |
|---|---|---|
| SCRAM password | Kafka broker | Đổi credential hoặc vô hiệu hóa user/mechanism, cập nhật client |
| OAuth access token | Identity provider / SASL/OAUTHBEARER | Revoke token/session hoặc client, phát hành token mới |
| mTLS certificate | PKI/TLS listener | Revoke qua CRL/OCSP nếu đã cấu hình hoặc thay đổi trust/identity policy |
| Cloud IAM credential | Cloud IAM | Disable key/role session, rotate và review cloud audit |
| Connect REST credential | REST proxy/extension/identity provider | Disable identity, chặn endpoint và thay credential |
| Secret của connector | Secret provider và hệ thống ngoài | Rotate secret nguồn/đích, cập nhật connector và kiểm tra egress |
| Admin credential | Kafka admin identity | Dùng break-glass identity khác để thu hồi quyền và rotate |

### 10.1. Không chỉ đổi password trong source code

Nếu secret từng xuất hiện trong Git, image, CI log, terminal history hoặc ticket, hãy coi nó đã bị lộ. Xóa dòng secret khỏi nhánh hiện tại không làm credential cũ mất hiệu lực. Cần rotate/revoke trước, sau đó xử lý lịch sử repository và các bản sao theo chính sách tổ chức.

### 10.2. Rotation có kế hoạch

Một quy trình rotation thông thường:

1. Tạo credential/certificate mới.
2. Cập nhật secret provider hoặc identity provider.
3. Chuyển client sang credential mới.
4. Xác minh authentication và authorization bằng workload thực.
5. Theo dõi lỗi kết nối, retry và throughput.
6. Thu hồi credential cũ sau khi xác nhận chuyển đổi.
7. Ghi audit và cập nhật inventory.

Với certificate CA, có thể cần giai đoạn trust cả CA cũ và mới. Với token ngắn hạn, cần xác minh refresh và cache behavior. Không thu hồi credential cũ trước khi có đường khôi phục nếu việc chuyển đổi có thể làm mất toàn bộ admin access.

## 11. Phản ứng khi phát hiện lộ thông tin

Ứng phó credential leak cần vừa containment nhanh vừa bảo toàn bằng chứng. Thứ tự cụ thể phụ thuộc mức độ tấn công đang diễn ra; nếu dữ liệu tiếp tục bị exfiltrate, ưu tiên chặn đường truy cập ngay sau khi thu thập bằng chứng tối thiểu cần thiết.

~~~mermaid
flowchart TD
    A[Phát hiện secret hoặc credential bị lộ] --> B[Xác định loại identity và phạm vi]
    B --> C[Thu thập log và snapshot cần thiết]
    C --> D[Contain: disable, revoke, rotate hoặc chặn network]
    D --> E[Kiểm tra ACL, topic, group, connector và audit]
    E --> F{Có dấu hiệu truy cập trái phép?}
    F -->|Có| G[Đánh giá dữ liệu và downstream impact]
    F -->|Chưa thấy| H[Xác minh credential cũ đã mất hiệu lực]
    G --> I[Khôi phục policy và xử lý dữ liệu bị ảnh hưởng]
    H --> J[Cấp credential mới và kiểm thử]
    I --> J
    J --> K[Theo dõi, thông báo và đóng incident]
~~~

### 11.1. Các bước ban đầu

1. Mở incident và chỉ định người điều phối.
2. Ghi thời điểm phát hiện, nguồn cảnh báo và người báo cáo.
3. Xác định loại secret, owner, môi trường và thời gian có thể bị lộ.
4. Xác định principal, host, listener, topic, group và dịch vụ liên quan.
5. Bảo toàn log, ACL snapshot, connector config và request metadata.
6. Nếu có truy cập trái phép đang diễn ra, disable/revoke identity hoặc chặn network path.
7. Rotate credential và thu hẹp ACL cần thiết.
8. Xác minh credential cũ không còn được chấp nhận.
9. Điều tra thao tác và dữ liệu trong khoảng thời gian bị ảnh hưởng.
10. Ghi lại quyết định, bằng chứng và người phê duyệt.

Không gửi secret thật vào ticket hoặc chat incident. Dùng secret reference, fingerprint hoặc ID từ secret manager.

## 12. Playbook: lộ credential của producer

Producer credential bị lộ có thể cho phép giả mạo event, spam topic hoặc phát dữ liệu sai.

### 12.1. Khoanh vùng

- Xác định principal và toàn bộ ACL Write/Create/Alter liên quan.
- Liệt kê topic literal/prefixed mà principal có thể ghi.
- Kiểm tra host restriction và service account có bị dùng chung không.
- Xác định transactional ID nếu producer dùng transaction.
- Kiểm tra thời gian bắt đầu lộ và lần sử dụng credential gần nhất.

### 12.2. Containment

- Disable hoặc rotate credential.
- Thu hồi ACL Write không cần thiết.
- Chặn host hoặc network path bị xâm nhập nếu cần.
- Cấp credential mới riêng cho workload hợp lệ.
- Không xóa topic hoặc record trước khi bảo toàn bằng chứng.

### 12.3. Điều tra tác động

Kiểm tra producer/client logs, broker logs, audit automation, event metadata, source IP và downstream processing. Tìm record bất thường theo key, event ID, schema version, timestamp và pattern volume.

Kafka không tự chứng minh nguồn nghiệp vụ của một record chỉ từ key/value. Nếu event không có producer identity trong payload hoặc audit correlation, có thể khó phân biệt record hợp lệ và record giả. Vì vậy, nên đưa event ID, source service và trace ID vào metadata nghiệp vụ phù hợp, có chữ ký hoặc cơ chế xác minh bổ sung khi mức rủi ro yêu cầu.

## 13. Playbook: lộ credential của consumer

Consumer credential bị lộ có thể cho phép đọc dữ liệu trái phép hoặc dò topic/group.

### 13.1. Khoanh vùng

- Xác định topic có ACL Read phù hợp.
- Kiểm tra group ACL và wildcard/prefixed pattern.
- Xác định principal có được dùng bởi nhiều ứng dụng không.
- Kiểm tra client host, network zone và consumer group bất thường.
- Xác định data classification của topic bị truy cập.

### 13.2. Containment và điều tra

- Revoke/rotate credential và ACL Read liên quan.
- Chặn host hoặc workload bị xâm nhập.
- Kiểm tra broker/security logs, network flow và consumer application logs.
- Kiểm tra consumer group mới, offset thay đổi hoặc hoạt động replay bất thường.
- Đánh giá dữ liệu đã bị đọc hoặc chuyển ra ngoài.
- Nếu principal dùng chung, tách identity cho từng workload và rotate toàn bộ client phụ thuộc.

Kafka không mặc định tạo audit record đầy đủ cho từng record consumer fetch. Nếu cần xác định dữ liệu đã bị truy cập, phải kết hợp application audit, network telemetry, client logs và các nguồn quan sát khác. Thiếu log không đồng nghĩa không có exfiltration.

## 14. Playbook: lộ credential quản trị hoặc Connect REST

Credential quản trị có phạm vi tác động lớn vì có thể thay đổi ACL, topic, config hoặc connector.

### 14.1. Admin credential bị lộ

Kiểm tra:

- ACL mới hoặc ACL bị xóa.
- Principal được thêm vào super.users hoặc security configuration.
- Topic bị tạo/xóa hoặc retention bị thay đổi.
- Consumer group offset bị reset.
- Connector/schema/config thay đổi.
- Admin UI, bastion và CI/CD activity.
- Broker/controller log trong khoảng thời gian nghi vấn.

Dùng một break-glass identity khác đã được kiểm thử để thu hồi credential bị lộ. Nếu chỉ có một admin identity và identity đó bị xâm phạm, containment có thể cần thao tác từ control plane hoặc quy trình vận hành khẩn cấp được tổ chức chuẩn bị trước.

### 14.2. Connect REST credential bị lộ

Người có quyền quản trị connector có thể thay đổi nguồn hoặc đích dữ liệu. Hãy:

1. Chặn REST endpoint khỏi nguồn không tin cậy.
2. Disable/revoke identity dùng cho REST.
3. Liệt kê connector mới và connector có config thay đổi.
4. So sánh connector config với snapshot/desired state.
5. Kiểm tra plugin path và worker image integrity.
6. Kiểm tra egress từ worker đến database, API và object storage.
7. Rotate secret của hệ thống nguồn/đích mà worker có thể truy cập.
8. Khôi phục connector config đã xác minh.
9. Kiểm tra dữ liệu đã bị đọc hoặc chuyển tới destination lạ.
10. Ghi audit và theo dõi sau phục hồi.

Broker ACL và Connect REST authorization là hai lớp riêng. Thu hồi ACL broker không tự động vô hiệu hóa REST credential; khóa REST API cũng không tự thu hồi credential database mà connector đã lưu.

## 15. Thu hồi theo từng loại credential

### 15.1. SCRAM

Với SCRAM, cần đổi password hoặc loại bỏ credential mechanism của user bị lộ, sau đó cập nhật client và xác minh password cũ bị từ chối.

Có thể quản lý SCRAM credential bằng kafka-configs.sh hoặc cơ chế identity provisioning của tổ chức. Cú pháp cụ thể phụ thuộc phiên bản và mechanism. Không truyền password thật trực tiếp trong command line vì có thể lộ qua shell history, process list hoặc log. Dùng secret injection an toàn và kiểm tra lại user config sau thao tác.

Nếu một username được chia sẻ cho nhiều workload, rotation sẽ ảnh hưởng tất cả workload đó. Đây là lý do mỗi service cần principal riêng.

### 15.2. OAuth token

- Revoke token hoặc session qua identity provider nếu hỗ trợ.
- Disable client/service identity nếu private credential của client bị lộ.
- Rotate client secret hoặc signing credential.
- Xem thời gian token hết hạn và cache/refresh behavior.
- Xác minh token cũ không còn được broker chấp nhận.

Nếu token đã được phát hành và không có cơ chế revoke tức thời, cần kết hợp disable client, giảm thời gian hiệu lực và chặn principal/ACL trong thời gian chờ token hết hạn.

### 15.3. mTLS certificate

Certificate bị lộ cần được revoke theo PKI. Kafka/JVM chỉ thực thi CRL hoặc OCSP khi cấu hình và trust validation hỗ trợ tương ứng. Nếu deployment không có revocation checking, chỉ xóa một file certificate khỏi client không làm certificate cũ mất hiệu lực tại broker.

Biện pháp containment có thể gồm thu hồi ACL của principal đã map từ certificate, chặn host/network, thay trust/identity policy hoặc triển khai CA/intermediate riêng cho workload bị ảnh hưởng. Sau đó cấp certificate mới và kiểm thử xác thực.

### 15.4. Secret của connector

Secret có thể được lưu trực tiếp trong connector config hoặc được resolve từ ConfigProvider. Khi bị lộ:

- Rotate credential ở database/API đích trước hoặc theo thứ tự rollout phù hợp.
- Cập nhật secret reference.
- Restart/reconfigure connector theo quy trình.
- Kiểm tra connector log và destination.
- Xác nhận secret cũ không còn được chấp nhận ở hệ thống ngoài.

Không giả định xóa connector sẽ thu hồi password database hoặc token ở hệ thống nguồn.

## 16. Kiểm chứng sau containment và recovery

Containment chưa hoàn tất cho đến khi chứng minh credential cũ bị vô hiệu hóa và workload hợp lệ hoạt động bằng identity mới.

Checklist xác minh:

1. Credential cũ bị từ chối khi thử bằng môi trường kiểm thử an toàn.
2. Credential mới xác thực thành công.
3. Principal mới chỉ có ACL cần thiết.
4. Principal bị xâm phạm không còn quyền không cần thiết.
5. Không có ACL wildcard hoặc super user mới ngoài dự kiến.
6. Connector, topic config và consumer group trở về desired state.
7. Producer/consumer hợp lệ hoạt động bình thường.
8. Không còn egress đến destination đáng ngờ.
9. Audit pipeline đang nhận log trở lại.
10. Alert và metric phản ánh đúng trạng thái sau sự cố.
11. Downstream đã xử lý hoặc cô lập event giả/record bị ảnh hưởng.
12. Owner, approver và incident timeline đã được ghi nhận.

Nếu dữ liệu đã bị đọc trái phép, không thể “thu hồi” bản sao đã exfiltrate bằng cách đổi ACL. Cần đánh giá nghĩa vụ thông báo, phạm vi dữ liệu, người bị ảnh hưởng và yêu cầu pháp lý theo quy trình tổ chức.

## 17. Thiết kế quy trình access review và audit

Một quy trình định kỳ có thể triển khai như sau:

~~~mermaid
flowchart TD
    A[Thu thập principal và ACL] --> B[Ghép owner và workload]
    B --> C[Tính quyền hiệu lực]
    C --> D[So sánh desired policy]
    D --> E{Có quyền thừa hoặc không owner?}
    E -->|Không| F[Ghi nhận kết quả review]
    E -->|Có| G[Đánh giá dependency và impact]
    G --> H[Owner/approver xác nhận]
    H --> I[Thu hẹp hoặc thu hồi quyền]
    I --> J[Test allow và deny]
    J --> K[Ghi audit và đóng review]
    F --> K
~~~

Các đầu ra cần lưu:

- Danh sách principal và owner.
- ACL inventory có resource pattern.
- Quyền hiệu lực và ngoại lệ.
- Các ACL được giữ, sửa hoặc thu hồi.
- Người thực hiện và người phê duyệt.
- Change ticket và thời gian áp dụng.
- Kết quả kiểm thử sau thay đổi.
- Ngày review tiếp theo.

Nên quản lý ACL dưới dạng policy/configuration as code khi có thể. Pipeline có thể so sánh desired ACL với cluster state, hiển thị diff và yêu cầu approval trước khi apply. Tránh tự động xóa mọi ACL không nằm trong file nếu chưa có quy trình xử lý ngoại lệ và resource do hệ thống khác quản lý.

## 18. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| kafka-acls --list bị AuthorizationException | Admin principal thiếu Describe trên CLUSTER | Kiểm tra identity và quyền quản trị ACL |
| createAcls bị từ chối | Thiếu Alter trên CLUSTER | Dùng admin identity được cấp quyền phù hợp |
| Principal vẫn đọc được topic sau khi xóa một ACL | Còn ACL khác, prefixed pattern hoặc super user | Tính lại toàn bộ quyền hiệu lực |
| ACL mới không có tác dụng như mong muốn | Sai principal mapping, resource pattern, host hoặc operation | Kiểm tra identity thực tế và ACL match |
| Producer bị từ chối Write | Thiếu Write, topic sai hoặc ACL chưa được áp dụng | Kiểm tra broker response và ACL inventory |
| Consumer join group thất bại | Thiếu Read trên GROUP hoặc topic | Kiểm tra cả topic ACL và group ACL |
| AdminClient timeout khi thay ACL | Request có thể đã được xử lý nhưng response mất | List ACL lại trước khi retry |
| Audit thiếu sự kiện quản trị | Thao tác chạy ngoài automation hoặc log pipeline mất dữ liệu | Kiểm tra shell audit, broker/controller logs và log forwarding |
| Không xác định được ai đã đọc record | Chưa có application-level data access audit | Bổ sung audit tại consumer/service boundary |
| SCRAM password mới không hoạt động | Client chưa reload secret hoặc mechanism không khớp | Kiểm tra user config, client config và restart policy |
| Certificate cũ vẫn kết nối được | Chưa có CRL/OCSP hoặc identity/ACL chưa bị thu hồi | Chặn principal/network và cập nhật PKI policy |
| Connect tiếp tục truy cập database sau khi xóa connector | Credential database vẫn còn hiệu lực hoặc task chưa dừng | Rotate credential hệ thống ngoài và xác minh worker/task |
| ACL review gây gián đoạn service | Thu hồi quyền trước khi kiểm tra dependency | Rollback có kiểm soát và chạy access test trên staging |

## 19. Checklist production

Trước và sau mỗi access review hoặc incident, hãy xác nhận:

1. Mọi principal đều có owner và mục đích sử dụng.
2. Service account được tách theo workload và môi trường.
3. ACL literal/prefixed/wildcard đã được đánh giá.
4. DENY, ALLOW và super.users được kiểm tra cùng nhau.
5. Producer/consumer chỉ có quyền cần thiết trên topic và group.
6. AdminClient dùng credential quản trị riêng.
7. Quyền DescribeAcls và AlterAcls được giới hạn.
8. ACL thay đổi có approval và audit event.
9. Audit log có actor, principal, action, resource, source, result và request ID.
10. Secret không xuất hiện trong audit, log, Git hoặc CI artifact.
11. Audit được gửi đến hệ thống độc lập và có retention phù hợp.
12. Có kiểm thử truy cập được phép và bị từ chối.
13. Có quy trình rotation/revocation cho SCRAM, OAuth, mTLS và connector secret.
14. Có break-glass admin identity được bảo vệ và kiểm thử.
15. Khi credential bị lộ, có thể xác định topic/group/connector bị ảnh hưởng.
16. Có thể chứng minh credential cũ đã mất hiệu lực.
17. Có kiểm tra downstream event và dữ liệu đã bị truy cập.
18. Có người phê duyệt và timeline incident.
19. Có lịch access review và theo dõi ngoại lệ.
20. Có diễn tập thu hồi credential và phục hồi workload.

## 20. Bài tập thực hành

### Bài 1: Kiểm tra ACL hiện tại

1. Tạo hai principal lab: orders-producer và orders-consumer.
2. Cấp Write cho producer và Read cho consumer trên topic orders-lab.
3. Cấp Read trên group orders-lab-group cho consumer.
4. Chạy kafka-acls.sh --list.
5. Ghi lại principal, host, operation và resource pattern.
6. Thử truy cập trái quyền bằng từng principal.
7. Giải thích vì sao authentication thành công nhưng request vẫn bị từ chối.

### Bài 2: Rà soát quyền thừa

1. Tạo một ACL PREFIXED cho topic orders-.
2. Tạo thêm một ACL literal cho topic payments-lab.
3. Liệt kê ACL và tính quyền hiệu lực của principal.
4. Kiểm tra có super user hoặc wildcard nào ảnh hưởng không.
5. Đề xuất policy tối thiểu cho từng service.
6. Thử policy trên môi trường lab trước khi thu hồi ACL cũ.

### Bài 3: Dùng AdminClient inventory ACL

1. Tạo chương trình Java dùng AdminClient.
2. Gọi describeAcls(AclBindingFilter.ANY).
3. In resource pattern, principal, host, operation và permission type.
4. Xuất báo cáo không chứa secret.
5. So sánh kết quả với desired ACL list.
6. Xử lý AuthorizationException và timeout.

### Bài 4: Audit thay đổi quản trị

1. Tạo một ACL qua automation wrapper.
2. Ghi audit event trước và sau thay đổi.
3. Lưu actor, principal, resource, operation, result và request ID.
4. Thử một thao tác bị từ chối.
5. Xác nhận audit có cả success và denial.
6. Kiểm tra log không chứa password hoặc token.

### Bài 5: Diễn tập lộ SCRAM credential

1. Tạo principal producer lab riêng.
2. Giả lập credential bị lộ trong môi trường test.
3. Thu thập ACL snapshot và log cần thiết.
4. Rotate hoặc disable credential.
5. Thử xác thực bằng credential cũ và xác nhận bị từ chối.
6. Cập nhật producer bằng credential mới.
7. Xác nhận producer vẫn chỉ có quyền Write trên topic lab.

### Bài 6: Diễn tập lộ Connect REST credential

1. Tạo connector lab có secret giả lập.
2. Ghi snapshot connector config đã redact.
3. Giả lập REST identity bị lộ.
4. Chặn endpoint và disable identity.
5. Kiểm tra connector mới/config thay đổi và worker egress.
6. Rotate secret hệ thống đích.
7. Khôi phục connector bằng identity mới.
8. Xác minh task và data flow hoạt động đúng.

## 21. Câu hỏi tự kiểm tra

1. Authentication, authorization và audit khác nhau thế nào?
2. Một ACL Kafka gồm những thành phần nào?
3. LITERAL và PREFIXED resource pattern khác nhau ra sao?
4. DENY và ALLOW được đánh giá như thế nào?
5. super.users ảnh hưởng access review ra sao?
6. Vì sao không nên dùng một principal cho producer, consumer và admin?
7. Producer cần operation nào trên topic?
8. Consumer cần kiểm tra quyền trên topic và group ra sao?
9. kafka-acls.sh --list dùng để làm gì?
10. AdminClient describeAcls cần quyền nào trên cluster?
11. createAcls cần quyền quản trị nào?
12. Vì sao phải tính quyền hiệu lực thay vì chỉ đọc một ACL?
13. Audit trail quản trị cần lưu các trường nào?
14. Kafka có mặc định ghi audit đầy đủ từng record consumer đọc không?
15. Vì sao cần application-level audit cho dữ liệu nhạy cảm?
16. Tại sao audit log nên được gửi đến hệ thống độc lập?
17. Khi SCRAM password bị lộ, cần làm gì để credential cũ mất hiệu lực?
18. Vì sao xóa file certificate ở client không thu hồi certificate đã lộ?
19. Khi Connect REST credential bị lộ, tại sao phải kiểm tra cả egress và secret hệ thống đích?
20. Sau containment, cần chứng minh những gì trước khi đóng incident?

## Kết luận

Kiểm tra quyền là quá trình xác định principal nào có thể thực hiện operation trên topic, group, cluster và resource khác. Cần đánh giá ACL literal, prefixed, host, ALLOW/DENY, super user và quyền được kế thừa từ nhiều pattern. kafka-acls CLI và AdminClient hỗ trợ inventory, nhưng access review vẫn cần owner, desired policy và kiểm thử bằng credential thực tế.

Audit cần ghi nhận đầy đủ thay đổi quản trị, identity, resource, nguồn request và kết quả. Kafka broker logs hỗ trợ điều tra authentication/authorization, nhưng không nên coi đó là audit trail đầy đủ cho mọi lần đọc/ghi record hoặc mọi dịch vụ ngoài broker. Hãy bổ sung audit tại automation, Connect REST, Schema Registry và application boundary; gửi log tập trung, bảo vệ khỏi sửa/xóa và không ghi secret.

Khi credential bị lộ, cần xác định phạm vi, bảo toàn bằng chứng, disable/revoke hoặc rotate identity, thu hẹp ACL, kiểm tra topic/group/connector và đánh giá downstream impact. Sau đó chứng minh credential cũ đã mất hiệu lực, workload hợp lệ hoạt động bằng credential mới và audit pipeline đã phục hồi. Access review định kỳ, identity riêng cho từng workload và least privilege giúp giảm phạm vi thiệt hại khi một thành phần bị xâm phạm.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| ACL | Danh sách quy tắc cho phép hoặc từ chối principal thực hiện operation trên resource. |
| Principal | Danh tính Kafka được tạo sau authentication và principal mapping. |
| Resource pattern | Cách ACL khớp resource, ví dụ LITERAL hoặc PREFIXED. |
| LITERAL | Pattern chỉ khớp chính xác tên resource. |
| PREFIXED | Pattern khớp resource có tên bắt đầu bằng prefix. |
| ALLOW | Quyền cho phép operation khi ACL phù hợp. |
| DENY | Quyền từ chối operation khi ACL phù hợp. |
| super.users | Danh sách principal có đặc quyền vượt ACL thông thường. |
| Access review | Quy trình rà soát quyền theo owner, workload và nhu cầu thực tế. |
| Effective access | Tập quyền thực tế sau khi xét mọi ACL, pattern và đặc quyền. |
| AdminClient | Java client quản trị Kafka, bao gồm API đọc và thay đổi ACL. |
| Audit trail | Dấu vết actor, action, resource, thời gian, nguồn và kết quả. |
| Change ticket | Mã yêu cầu/phê duyệt thay đổi có thể truy vết. |
| Credential rotation | Thay password, token hoặc key bằng credential mới. |
| Revocation | Vô hiệu hóa credential, certificate, token hoặc quyền đã cấp. |
| Break-glass identity | Danh tính quản trị khẩn cấp được bảo vệ và chỉ dùng khi cần. |
| Containment | Hành động giới hạn khả năng tiếp tục xâm nhập hoặc truy cập trái phép. |
| Evidence preservation | Bảo toàn log, snapshot và metadata phục vụ điều tra. |
| Secret manager | Dịch vụ lưu trữ, phân phối và quản lý vòng đời secret. |
| Data access audit | Ghi nhận truy cập dữ liệu ở tầng ứng dụng/nghiệp vụ khi cần chi tiết từng lần đọc. |

