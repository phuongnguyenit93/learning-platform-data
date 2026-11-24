# Quyền tối thiểu khi truy cập dịch vụ đám mây và broker

## 1. Bài toán: một function chỉ nên có quyền cần cho công việc của nó

Một hệ thống xử lý đơn hàng dùng Spring Cloud Function. Ứng dụng có ba function:

- `receiveOrder` nhận sự kiện từ broker và xác thực dữ liệu.
- `archiveOrder` ghi bản sao đơn hàng vào object storage.
- `publishOrderStatus` phát thông báo trạng thái sang một topic khác.

Nếu cả ba function dùng chung một credential có quyền quản trị bucket, queue, topic và database, một lỗi trong bất kỳ function nào cũng có thể ảnh hưởng đến toàn bộ hệ thống. Một function chỉ cần ghi object lại có thể xóa dữ liệu; một consumer chỉ cần đọc queue có thể publish message giả; một lỗi injection hoặc dependency compromise có thể dùng toàn bộ quyền của process.

**Quyền tối thiểu (least privilege)** là nguyên tắc cấp cho một workload đúng những thao tác cần thiết trên đúng tài nguyên cần thiết, trong khoảng thời gian cần thiết. Khi áp dụng cho Spring Cloud Function, phải xác định được:

1. Function chạy dưới **principal/identity** nào?
2. Function cần thực hiện **action** nào?
3. Action đó áp dụng trên **resource** nào?
4. Quyền được giới hạn bằng **scope, condition, network, thời hạn** nào?
5. Làm thế nào xác minh function không thể thực hiện thao tác ngoài mục đích?

Trong module **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`), nghiệp vụ được tổ chức bằng `Supplier<T>`, `Function<T,R>` và `Consumer<T>`, tra cứu qua `FunctionCatalog`, composition và chuyển đổi message. Function model giúp tách logic khỏi giao thức gọi; **nó không tự cấp hoặc giới hạn quyền truy cập cloud/broker**. Quyền được quyết định bởi identity mà runtime sử dụng, policy của dịch vụ và cấu hình bảo mật của adapter/binder.

Bài này tập trung vào quyền truy cập AWS, Google Cloud, Azure và broker Kafka/RabbitMQ. Các tên role, action, property và ví dụ policy phải được đối chiếu với dịch vụ, phiên bản và mô hình triển khai thực tế.

## 2. Phân biệt authentication, authorization và network access

Ba lớp bảo vệ thường bị gộp thành một:

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Authentication (xác thực)** | Ai đang gọi? | IAM role, workload identity, managed identity, SASL/SCRAM, mTLS. |
| **Authorization (phân quyền)** | Principal được làm gì trên tài nguyên nào? | IAM policy cho `s3:GetObject`, Kafka ACL `READ` trên topic, RabbitMQ read permission trên queue. |
| **Network access** | Kết nối có đến được endpoint không? | VPC route, security group, firewall, private endpoint, TLS. |

Một kết nối TCP thành công không có nghĩa principal được phép đọc queue. Ngược lại, IAM policy có quyền `s3:GetObject` không giúp ứng dụng truy cập bucket nếu route, DNS hoặc endpoint bị chặn.

### 2.1. Identity, action và resource

Một quyết định authorization thường có thể biểu diễn bằng:

```text
Principal:  order-archiver-role
Action:     s3:PutObject
Resource:   arn:aws:s3:::order-archive/orders/*
Condition:  region / encryption / tenant / network (nếu cần)
```

Ví dụ này chỉ cho biết ý định cấp quyền. Policy thực tế còn chịu ảnh hưởng của resource policy, explicit deny, permission boundary, session policy, organization policy và các điều kiện dịch vụ.

### 2.2. Quyền của function khác quyền của người gọi function

Có hai hướng truy cập:

- **Inbound:** người dùng, API gateway, scheduler hoặc broker có quyền kích hoạt function.
- **Outbound:** function có quyền gọi object storage, database, secret manager hoặc broker.

Không dùng một policy duy nhất để mô tả cả hai hướng. Ví dụ trên AWS, execution role cấp quyền cho code Lambda truy cập dịch vụ; resource-based policy trên Lambda có thể cho phép một service/account khác invoke function. Hai policy này có mục đích khác nhau. Xem [quản lý quyền Lambda](https://docs.aws.amazon.com/us_en/lambda/latest/dg/lambda-permissions.html).

## 3. Xác định principal mà function thực sự sử dụng

Một bean Spring có thể được gọi qua HTTP, Stream hoặc serverless, nhưng credential thường đến từ **runtime/process hoặc binder/client**, không đến từ tên bean trong `FunctionCatalog`.

| Môi trường chạy | Identity thường dùng |
| --- | --- |
| AWS Lambda | Lambda execution role được runtime cấp temporary credentials. |
| AWS ECS/EKS/EC2 | Task role, pod/workload identity hoặc instance profile tương ứng. |
| Google Cloud Run/GKE/Functions | Service account gắn với workload hoặc Workload Identity. |
| Azure Functions/Container Apps/AKS | Managed identity hoặc workload identity. |
| Kubernetes tự quản | Service account kết hợp OIDC federation hoặc secret do hệ thống quản lý. |
| Broker self-managed | Principal từ SASL/SCRAM, Kerberos, mTLS certificate hoặc cơ chế xác thực broker hỗ trợ. |

### 3.1. Một process thường chia sẻ một workload identity

Giả sử cùng một Spring Boot process chứa:

```java
@Bean
Function<OrderEvent, ArchiveResult> archiveOrder(ArchiveService service) {
    return service::archive;
}

@Bean
Function<OrderEvent, Notification> publishOrderStatus(
        NotificationService service) {
    return service::publish;
}
```

Hai bean có tên khác nhau nhưng cùng chạy trong một process. Nếu process dùng một AWS execution role, cả hai function có thể sử dụng credential của role đó thông qua AWS SDK default credential provider chain. **Không có chuyện mỗi bean tự động nhận một IAM role riêng chỉ vì nó là một function riêng.**

Nếu cần quyền tách biệt mạnh:

- Triển khai function thành các workload/Lambda riêng, mỗi workload có execution role riêng.
- Với một số kiến trúc, workload có thể assume role khác qua STS khi được thiết kế rõ ràng; giới hạn trust policy, thời hạn session và quyền assume.
- Nếu các function cùng process và cùng credential, phải coi tập quyền của process là quyền tối đa của mọi code chạy trong process.

Đây là lý do tách function theo deployment boundary đôi khi quan trọng hơn tách bean trong cùng context.

## 4. Cấp credential an toàn cho ứng dụng Spring

### 4.1. Ưu tiên workload identity thay cho access key tĩnh

Thứ tự lựa chọn thường nên là:

1. **Managed/workload identity** do nền tảng cấp.
2. Federation/OIDC hoặc STS short-lived session cho workload cần assume role.
3. Secret manager cấp credential có vòng đời ngắn nếu broker không hỗ trợ workload identity.
4. Credential tĩnh chỉ khi không có lựa chọn tốt hơn, có owner, rotation và giới hạn phạm vi rõ.

Không commit access key, password broker, private key hoặc token vào Git, Docker image, JAR, `application.yml` hay log. Không đặt secret trong tên function hoặc message header.

### 4.2. AWS SDK dùng credential provider chain

Ví dụ tạo S3 client:

```java
@Configuration(proxyBeanMethods = false)
class CloudClientConfiguration {

    @Bean(destroyMethod = "close")
    S3Client s3Client() {
        return S3Client.builder()
                .region(Region.of(System.getenv("AWS_REGION")))
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();
    }
}
```

`DefaultCredentialsProvider` cho phép AWS SDK tìm credential theo các nguồn được hỗ trợ trong runtime; trong Lambda, SDK có thể sử dụng credential tạm thời của execution role. Ứng dụng không cần nhúng access key vào code. Đóng client theo lifecycle của Spring context để giải phóng resource.

Trong production, kiểm tra credential provider chain mà SDK version thực tế hỗ trợ và tránh để biến môi trường/local profile vô tình override workload role.

### 4.3. Không dùng identity của developer trong production

Một ứng dụng chạy local có thể dùng profile cá nhân có quyền rộng. Nếu deploy nguyên cấu hình đó hoặc đóng credential file vào container, function có thể hoạt động với quyền vượt xa workload cần.

Local development nên dùng profile riêng có quyền giới hạn; production dùng role/managed identity riêng. Không dùng credential của người vận hành để chạy workload lâu dài.

## 5. Thiết kế policy theo hành động và tài nguyên

Trước khi viết policy, lập bảng quyền cho từng function:

| Function | Thao tác | Tài nguyên | Quyền tối thiểu dự kiến |
| --- | --- | --- | --- |
| `receiveOrder` | Consume event | Queue `orders.in` | Read/consume trên queue hoặc subscription và consumer group cần thiết. |
| `archiveOrder` | Ghi object | Prefix `orders/*` trong bucket `order-archive` | Put object trên prefix. |
| `publishOrderStatus` | Publish event | Topic `orders.status` | Write/publish trên topic. |
| `loadShippingPolicy` | Đọc secret | Secret `shipping-api-key` | Get/read đúng secret. |

Policy tốt phải giới hạn cả **action** lẫn **resource**. `s3:*` trên `*`, `pubsub.*` ở project hoặc user `administrator` trên toàn broker không phải cách cấp quyền cho một function nghiệp vụ thông thường.

### 5.1. Không cấp quyền quản trị chỉ để ứng dụng tự tạo resource

Tạo bucket, queue, topic, subscription, exchange và binding thường là trách nhiệm của provisioning/deployment pipeline hoặc platform administrator. Runtime function chỉ cần đọc, ghi, consume hoặc publish.

Trong môi trường production, cân nhắc:

- Tắt topic/queue auto-creation nếu không cần.
- Provision resource bằng IaC hoặc pipeline riêng.
- Cấp quyền data-plane cho function; quyền control-plane để quản trị resource nằm ở deployment identity.
- Không dùng cùng một principal vừa deploy hạ tầng vừa xử lý message.

## 6. AWS IAM: execution role và quyền trên S3

Mỗi Lambda cần execution role. Role có **trust policy** cho phép Lambda service assume role và **permission policies** mô tả code được truy cập dịch vụ nào. Quyền gọi Lambda từ service/account khác có thể nằm ở resource-based policy của Lambda. Xem tài liệu [AWS Lambda execution role](https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html) và [quản lý quyền Lambda](https://docs.aws.amazon.com/us_en/lambda/latest/dg/lambda-permissions.html).

### 6.1. Chỉ đọc object trong một prefix

Giả sử function `loadOrderArchive` chỉ cần đọc object dưới `orders/` trong bucket `order-archive`. Policy identity-based minh họa:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOrderArchiveObjects",
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": [
        "arn:aws:s3:::order-archive/orders/*"
      ]
    }
  ]
}
```

Policy trên không cấp quyền liệt kê bucket, ghi object, xóa object hoặc truy cập prefix khác. Nếu function cần `ListObjectsV2`, phải thêm `s3:ListBucket` trên **bucket ARN** và giới hạn bằng condition `s3:prefix`; không thêm `s3:ListAllMyBuckets` chỉ để duyệt console.

Ví dụ statement riêng cho việc list một prefix:

```json
{
  "Sid": "ListOnlyOrderArchivePrefix",
  "Effect": "Allow",
  "Action": ["s3:ListBucket"],
  "Resource": ["arn:aws:s3:::order-archive"],
  "Condition": {
    "StringLike": {
      "s3:prefix": ["orders/", "orders/*"]
    }
  }
}
```

Bucket-level action dùng bucket ARN; object action dùng object ARN. Đây là khác biệt quan trọng khi debug `AccessDenied`. Xem [cách S3 kết hợp IAM](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security_iam_service-with-iam.html) và [quyền cho S3 API operations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-with-s3-policy-actions.html).

### 6.2. Chỉ ghi object vào prefix

Function `archiveOrder` chỉ upload object:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "WriteOrderArchiveObjects",
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": [
        "arn:aws:s3:::order-archive/orders/*"
      ]
    }
  ]
}
```

Không thêm `s3:GetObject`, `s3:DeleteObject` hoặc `s3:*` nếu function chỉ upload. Nếu ghi object có SSE-KMS, có thể cần quyền KMS như `kms:GenerateDataKey` trên key cụ thể; nếu đọc object mã hóa, có thể cần `kms:Decrypt`. Key policy và IAM policy phải cùng cho phép thao tác. Chỉ cấp quyền KMS cần thiết và kiểm tra encryption context/`kms:ViaService` khi phù hợp với thiết kế.

### 6.3. Đừng quên resource policy và explicit deny

Một request S3 có thể chịu ảnh hưởng của:

- Identity-based policy trên execution role.
- Bucket/access point policy.
- KMS key policy nếu object dùng SSE-KMS.
- VPC endpoint policy.
- Organization SCP, permission boundary hoặc session policy.
- Explicit `Deny` trong bất kỳ lớp áp dụng nào.

Một `Allow` ở execution role không tự động vượt qua explicit deny hoặc policy boundary khác.

## 7. AWS SQS: phân biệt event source mapping với SDK send

Khi Lambda được kết nối với SQS qua **event source mapping**, Lambda poll queue và đưa batch message vào function. Execution role cần các quyền đọc/xóa/đọc thuộc tính queue tương ứng, thường gồm:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConsumeOrdersQueue",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-in"
    }
  ]
}
```

Nếu queue mã hóa bằng KMS, có thể cần thêm `kms:Decrypt` trên key tương ứng. AWS có tài liệu [cấu hình SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html), gồm quyền execution role và xử lý queue mã hóa.

**Đây là quyền của Lambda poller thông qua execution role.** Nếu code bên trong function tự gọi AWS SDK để gửi message sang queue `orders-out`, đó là một thao tác khác và cần `sqs:SendMessage` trên queue đích. Không cấp `SendMessage` cho consumer chỉ vì nó đang nhận message từ SQS.

### 7.1. DLQ và retry cũng cần được thiết kế

Khi xử lý batch message:

- Chọn batch size và visibility timeout phù hợp với thời gian xử lý.
- Cấu hình redrive policy/max receive count và DLQ.
- Dùng partial batch response nếu adapter/trigger và ứng dụng hỗ trợ.
- Thiết kế idempotency vì message có thể được gửi lại.
- Chỉ cấp quyền đọc/xóa trên source queue và quyền cần thiết trên DLQ theo vai trò thực tế.

Quyền tối thiểu không thay thế delivery semantics. Một function có quyền đúng nhưng xử lý trùng message vẫn có thể gây side effect lặp.

## 8. Google Cloud Pub/Sub: role theo topic và subscription

Pub/Sub dùng IAM và cho phép gán quyền ở project hoặc resource. Với function chỉ publish, role `roles/pubsub.publisher` chứa `pubsub.topics.publish` và có thể được gán trực tiếp trên topic. Với function consume, role `roles/pubsub.subscriber` có các quyền consume subscription và có thể được gán ở phạm vi subscription phù hợp. Tránh cấp `roles/pubsub.admin` hoặc basic role rộng cho runtime. Tham khảo [Pub/Sub access control](https://docs.cloud.google.com/pubsub/docs/access-control).

| Function | Role gợi ý | Scope |
| --- | --- | --- |
| `publishOrderStatus` | Pub/Sub Publisher | Topic `orders.status`. |
| `receiveOrder` | Pub/Sub Subscriber | Subscription `orders-normalizer-sub`. |
| `provisionTopics` | Role quản trị riêng | Chỉ pipeline triển khai, không gắn cho function runtime. |

### 8.1. Workload identity

Gắn service account/workload identity với workload đang chạy. Tránh tải service account JSON key vào image hoặc lưu trong `application.yml`. Nếu phải dùng cross-project Pub/Sub, cấp permission cho service account trên đúng topic/subscription của project đích; không cần cấp quyền toàn project nếu chỉ một resource được dùng.

### 8.2. Chẩn đoán PERMISSION_DENIED

Xác minh principal đang hoạt động, project chứa resource, topic/subscription name và role được gán ở scope nào. Một service account có quyền publisher trên topic A vẫn không publish được vào topic B. Thay đổi IAM có thể có độ trễ do policy propagation/cache.

## 9. Azure Service Bus: Managed Identity và Data Sender/Receiver

Azure Service Bus cung cấp các role data-plane:

- **Azure Service Bus Data Sender:** gửi message vào queue/topic.
- **Azure Service Bus Data Receiver:** nhận message từ queue/subscription.
- **Azure Service Bus Data Owner:** quyền quản trị data-plane rộng hơn, không nên dùng cho function chỉ gửi hoặc nhận.

Gán role ở scope hẹp nhất: queue, topic hoặc subscription khi hỗ trợ; sau đó mới đến namespace/resource group/subscription nếu thực sự cần. Microsoft mô tả các role và scope trong [hướng dẫn Managed Identity cho Service Bus](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-managed-service-identity).

| Function | Role | Scope |
| --- | --- | --- |
| `publishOrderStatus` | Data Sender | Topic `orders.status`. |
| `receiveOrder` | Data Receiver | Queue `orders.in` hoặc subscription cụ thể. |
| `manageBrokerTopology` | Role quản trị riêng | Pipeline/provisioning identity. |

### 9.1. Managed Identity thay cho connection string có SAS key

Khi runtime hỗ trợ, dùng Managed Identity và Microsoft Entra authentication. Connection string chứa shared access key có thể cấp quyền rộng cho toàn namespace và khó phân biệt workload. Nếu vẫn cần SAS policy, tạo policy riêng cho send hoặc listen; không dùng RootManageSharedAccessKey cho ứng dụng.

Role assignment trên Azure có thể cần thời gian để propagation; tài liệu Service Bus lưu ý độ trễ có thể lên đến vài phút. Khi vừa gán role, kiểm tra principal và scope trước khi kết luận SDK hoặc binder bị lỗi.

## 10. Kafka: ACL phải giới hạn topic và consumer group

Kafka có hai lớp độc lập:

1. **Authentication:** broker xác định principal từ SASL/SCRAM, SASL/OAUTHBEARER, Kerberos hoặc TLS client certificate.
2. **Authorization:** authorizer kiểm tra ACL cho principal trên topic, group, cluster hoặc transactional ID.

Một consumer cần đọc topic và tham gia đúng consumer group. Một producer cần ghi vào topic. Quyền quản trị cluster/topic không cần thiết cho function xử lý message thông thường. Xem [Kafka authorization and ACLs](https://kafka.apache.org/44/security/authorization-and-acls/).

### 10.1. Ma trận quyền cơ bản

| Vai trò | Topic | Consumer group | Cluster |
| --- | --- | --- | --- |
| Consumer `order-normalizer` | `READ` (và `DESCRIBE` khi cần metadata) trên `orders.in` | `READ` trên group `order-normalizers` | Không cần quyền quản trị. |
| Producer `order-status-publisher` | `WRITE` (và `DESCRIBE` khi cần metadata) trên `orders.status` | Không cần quyền consumer group | Không cần quyền quản trị. |
| Topic provisioner | `CREATE`/`ALTER`/`DELETE` theo nhiệm vụ | Không gắn cho runtime | Chỉ cấp quyền cluster cần thiết cho pipeline. |

Kafka CLI convenience option `--producer` có thể tạo ACL `WRITE`, `DESCRIBE` và `CREATE` trên topic; `--consumer` tạo quyền `READ`, `DESCRIBE` trên topic và `READ` trên group. Để theo least privilege, nếu topic đã được provision sẵn, hãy xem ACL cụ thể và bỏ `CREATE` nếu producer không cần tự tạo topic.

### 10.2. Tên consumer group là một phần của quyền

Consumer có ACL `READ` trên topic nhưng không có quyền `READ` trên group có thể gặp lỗi `GROUP_AUTHORIZATION_FAILED`. Nếu ứng dụng đổi `group` trong Spring Cloud Stream, ACL group cũng phải được cập nhật. Không cấp `READ` trên mọi group bằng wildcard chỉ để khắc phục một lỗi group name sai.

### 10.3. Producer idempotent/transactional

Producer dùng idempotence hoặc transaction có thể cần ACL bổ sung như `IdempotentWrite` trên cluster hoặc quyền trên transactional ID, tùy cấu hình/version broker. Không cấp `All` hoặc cluster admin để làm producer transaction chạy được; hãy lấy protocol error và xác định đúng resource/operation còn thiếu.

## 11. RabbitMQ: vhost và regex permissions

RabbitMQ kiểm soát quyền theo **virtual host** và tên resource. Ba nhóm permission chính:

- `configure`: khai báo, thay đổi hoặc xóa queue/exchange/binding.
- `write`: publish hoặc thao tác ghi lên resource.
- `read`: consume hoặc thao tác đọc từ resource.

Permission là regex được đánh giá trên tên resource trong vhost. Tài liệu [RabbitMQ access control](https://www.rabbitmq.com/docs/access-control) mô tả `set_permissions`, `clear_permissions` và cách giới hạn theo virtual host.

### 11.1. Consumer chỉ đọc một queue

Ví dụ principal `order-consumer` chỉ consume queue `orders.input` trong vhost `orders-vhost`:

```bash
rabbitmqctl set_permissions -p "orders-vhost" "order-consumer" "^$" "^$" "^orders\.input$"
```

Ba regex theo thứ tự là `configure`, `write`, `read`. Consumer không được khai báo queue/exchange, không publish và chỉ được đọc resource khớp tên `orders.input`.

### 11.2. Producer chỉ ghi vào exchange đã có

```bash
rabbitmqctl set_permissions -p "orders-vhost" "order-publisher" "^$" "^orders\.status$" "^$"
```

Exchange phải được provisioning trước bởi identity có quyền cấu hình. Producer chỉ được publish vào exchange `orders.status`; không có quyền consume hoặc tạo resource.

### 11.3. Không nhầm management tag với resource permission

Tag như `administrator`, `management` hoặc `monitoring` điều khiển khả năng truy cập management UI/API. Chúng khác với configure/write/read permission trên resource. Một worker không cần quyền quản trị RabbitMQ chỉ để consume queue. Không gán tag administrator cho service account của function.

## 12. Cấu hình bảo mật Kafka binder trong Spring Cloud Stream

Spring Cloud Function mô tả business function; Spring Cloud Stream binder kết nối function với broker. Với Kafka binder, cấu hình security client được chuyển qua `spring.cloud.stream.kafka.binder.configuration`. Tài liệu [Spring Cloud Stream Kafka security configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/security-config.html) mô tả cách cấu hình SASL/JAAS và các client properties.

Ví dụ consumer binding:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.in
          group: order-normalizers
      kafka:
        binder:
          brokers: ${KAFKA_BOOTSTRAP_SERVERS}
          autoCreateTopics: false
          configuration:
            security.protocol: SASL_SSL
            sasl.mechanism: SCRAM-SHA-512
            sasl.jaas.config: >-
              org.apache.kafka.common.security.scram.ScramLoginModule required
              username="${KAFKA_USERNAME}"
              password="${KAFKA_PASSWORD}";
```

Đây là cấu hình minh họa cho broker hỗ trợ SASL/SCRAM-SHA-512. Cần TLS trust configuration phù hợp và principal đã được tạo ACL trên topic/group. `SASL_SSL` bảo vệ đường truyền bằng TLS; SASL xác thực principal; ACL mới quyết định principal được làm gì.

**Không commit giá trị `KAFKA_USERNAME` hoặc `KAFKA_PASSWORD`.** Cung cấp chúng qua secret manager hoặc cơ chế injection được quản lý. Nếu có nhiều Kafka clusters với credential khác nhau, dùng multi-binder và cấu hình security riêng cho từng binder thay vì dùng một credential rộng cho toàn ứng dụng.

### 12.1. Tắt auto-create khi runtime không có quyền quản trị

Trong môi trường được kiểm soát, topic nên được tạo bởi pipeline provisioning. Đặt `autoCreateTopics: false` (theo cấu hình binder/version) giúp runtime không cố tạo topic khi broker không cấp quyền `CREATE`. Kiểm tra thêm `autoAddPartitions`; không bật tính năng quản trị partition nếu workload không cần.

### 12.2. Consumer group phải trùng với ACL

Nếu binding khai báo:

```yaml
spring:
  cloud:
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.in
          group: order-normalizers
```

thì Kafka principal cần quyền trên topic `orders.in` và group `order-normalizers`. Đổi tên group là thay đổi security contract, không chỉ là một thay đổi cấu hình vận hành.

## 13. RabbitMQ binder và credential riêng cho workload

Với RabbitMQ binder, ứng dụng cần credential có quyền đúng trên vhost và resource. Ví dụ cấu hình connection:

```yaml
spring:
  rabbitmq:
    host: ${RABBITMQ_HOST}
    port: 5671
    virtual-host: orders-vhost
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    ssl:
      enabled: true
```

Đây là ví dụ Spring Boot RabbitMQ connection properties; kiểm tra binder và version đang dùng để xác nhận cách chia sẻ connection factory. Username/password được lấy từ secret injection, không đặt giá trị thật trong file. TLS cần trust chain/hostname verification phù hợp.

Một consumer và publisher nên có principal riêng nếu chúng có nhiệm vụ/quyền khác nhau. Nếu cùng một principal dùng cho cả hai, quyền hiệu lực của process là hợp của cả read và write permission.

## 14. Ví dụ function chỉ có quyền ghi vào một prefix

Function có thể dùng AWS SDK mà không biết IAM policy cụ thể:

```java
@Configuration(proxyBeanMethods = false)
class ArchiveFunctions {

    @Bean
    Function<OrderArchiveCommand, String> archiveOrder(S3Client s3) {
        return command -> {
            String key = "orders/" + command.orderId() + ".json";

            s3.putObject(
                    PutObjectRequest.builder()
                            .bucket("order-archive")
                            .key(key)
                            .contentType("application/json")
                            .build(),
                    RequestBody.fromString(command.json()));

            return key;
        };
    }
}
```

Function chỉ gọi `PutObject`; execution role tương ứng chỉ cần `s3:PutObject` trên prefix `arn:aws:s3:::order-archive/orders/*` (cộng quyền KMS nếu encryption policy yêu cầu). Nó không cần `s3:GetObject`, `s3:DeleteObject` hoặc quyền quản trị bucket.

`orderId` và `json` trong ví dụ là input contract. Trong hệ thống nhiều tenant, không tin `tenantId`/object key do caller tùy ý gửi. Xác thực tenant ở boundary và tự tạo key từ principal/claim đã được xác minh; policy prefix chỉ là một lớp bảo vệ bổ sung, không thay thế kiểm tra authorization trong nghiệp vụ.

## 15. Secret, rotation và vòng đời kết nối

### 15.1. Lấy secret theo đúng nhu cầu

Nếu function cần một API key hoặc broker password:

- Cấp quyền đọc đúng secret/version cho workload.
- Không cấp quyền list toàn bộ secrets nếu chỉ cần đọc một secret có tên cố định.
- Tách secret theo môi trường và theo workload.
- Không đưa secret vào event, function output, exception message hoặc log.
- Hạn chế quyền người có thể đọc secret trong console và quyền của deployment pipeline.

### 15.2. Rotation không được làm function ngừng hoạt động

Khi secret thay đổi:

1. Broker/API chấp nhận credential mới.
2. Secret manager cập nhật version mới.
3. Workload lấy credential mới theo cơ chế cache/refresh đã thiết kế.
4. Client connection pool hoặc broker connection được reconnect an toàn.
5. Credential cũ bị thu hồi sau thời gian overlap phù hợp.

Không giả định Spring singleton tự reload password khi secret manager đổi version. Nếu binder/client chỉ đọc credential lúc tạo connection factory, cần cơ chế refresh/restart hoặc rebind có kiểm soát.

### 15.3. Không log thông tin xác thực

Log principal/service account ID có thể hữu ích cho audit; log password, access token, SASL JAAS string, private key hoặc full connection URI có secret thì không. Khi log exception, kiểm tra thư viện có in cấu hình nhạy cảm hay không.

## 16. Trust boundary của message và function routing

Message header và payload là dữ liệu có thể đến từ bên ngoài. Một trường như `tenantId`, `role`, `principal`, `functionName` hoặc `routingExpression` không tự trở thành bằng chứng authorization.

Ví dụ một event có:

```json
{
  "tenantId": "tenant-a",
  "orderId": "ORD-204",
  "action": "archive"
}
```

Function phải xác minh caller/event source được phép xử lý tenant `tenant-a`, rồi mới tạo object key hoặc gọi service. Không lấy `tenantId` từ payload để quyết định quyền truy cập chỉ vì JSON parse thành công.

### 16.1. Broker ACL không thay thế authorization trong domain

Kafka ACL có thể cho service đọc topic `orders.in`; nó không đảm bảo từng message trong topic đều thuộc tenant mà service được phép xử lý. Nếu một topic chứa nhiều tenant, ứng dụng phải kiểm tra tenant/ownership theo một nguồn tin cậy.

Ngược lại, authorization trong code không thay thế broker ACL. Một consumer có quyền đọc mọi topic nhưng chỉ kiểm tra tenant trong function vẫn có thể bị cấu hình sai, đọc dữ liệu ngoài phạm vi và làm tăng blast radius.

### 16.2. Routing không được mở rộng quyền

Nếu dùng `FunctionCatalog` routing để chọn function theo message header:

- Chỉ cho phép danh sách function cụ thể.
- Không cho event bên ngoài chọn function quản trị hoặc `Consumer` có side effect.
- Xác minh nguồn header; không tin header do client tự đặt nếu adapter không xác thực nó.
- Ghi audit tên route và principal đã xác thực, không ghi secret/payload nhạy cảm.

## 17. Chẩn đoán lỗi AccessDenied và broker authorization

Khi function nhận lỗi authorization, hãy xác định **principal, action, resource và policy layer** trước khi thêm quyền.

| Lỗi | Câu hỏi đầu tiên |
| --- | --- |
| AWS `AccessDenied` | Role nào đang được assume? Action và ARN chính xác là gì? Có explicit deny, bucket policy, KMS key policy hoặc SCP không? |
| S3 `403 AccessDenied` | Object ARN có đúng prefix? Có cần `ListBucket` hay chỉ `GetObject`? Bucket dùng SSE-KMS không? |
| SQS `AccessDenied` | Lỗi từ event source mapping poller hay code gọi SDK? Queue ARN/region/account có đúng? |
| GCP `PERMISSION_DENIED` | Service account nào? Role được gán ở topic/subscription/project nào? |
| Azure `Unauthorized`/`Forbidden` | Managed identity đúng chưa? Role Data Sender/Receiver có đúng scope và đã propagation chưa? |
| Kafka `TOPIC_AUTHORIZATION_FAILED` | Principal có `READ`/`WRITE` trên đúng topic không? |
| Kafka `GROUP_AUTHORIZATION_FAILED` | Consumer group có trùng tên trong ACL không? |
| RabbitMQ `ACCESS_REFUSED` | Principal có quyền trên đúng vhost và resource regex không? |

### 17.1. Quy trình xử lý AWS AccessDenied

1. Đọc ARN principal trong exception hoặc CloudTrail event.
2. Xác nhận Lambda execution role thực tế, không nhầm với deployer/user đang deploy.
3. Xác định action và resource ARN chính xác.
4. Kiểm tra identity policy, resource policy, KMS key policy, VPC endpoint policy, SCP và permission boundary.
5. Nếu cần list S3, phân biệt `s3:ListBucket` trên bucket ARN với `s3:GetObject` trên object ARN.
6. Thêm đúng một quyền/resource/condition cần thiết.
7. Thử lại thao tác bị từ chối và chạy negative test để chắc chắn quyền ngoài phạm vi vẫn bị từ chối.

AWS IAM Access Analyzer có thể tạo policy template từ CloudTrail activity để gợi ý các action đã được sử dụng. Đây là **đầu vào để rà soát**, không phải bảo đảm đầy đủ: hành vi hiếm, nhánh lỗi, sự kiện định kỳ hoặc chức năng mới có thể chưa xuất hiện trong log. AWS khuyến nghị dùng Access Analyzer để tinh chỉnh execution role trước production. Xem [AWS execution role least privilege](https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html).

### 17.2. Không chữa lỗi bằng wildcard rộng

Tránh phản xạ thêm:

```json
{
  "Effect": "Allow",
  "Action": "*",
  "Resource": "*"
}
```

hoặc cấp `AdministratorAccess`, Kafka superuser, RabbitMQ administrator hay Azure Data Owner cho workload chỉ vì một request bị từ chối. Hãy xác định chính xác permission thiếu và phạm vi resource.

## 18. Kiểm thử least privilege

Policy cần được kiểm tra cả **đường đi được phép** và **đường đi bị cấm**.

### 18.1. Positive test

| Function | Thao tác phải thành công |
| --- | --- |
| `archiveOrder` | Put object vào `order-archive/orders/ORD-204.json`. |
| `loadOrderArchive` | Get object thuộc prefix được cấp. |
| `receiveOrder` | Consume từ queue/topic và group được chỉ định. |
| `publishOrderStatus` | Publish vào `orders.status`. |

### 18.2. Negative test

| Function | Thao tác phải bị từ chối |
| --- | --- |
| `archiveOrder` | Get hoặc delete object; put vào bucket/prefix khác. |
| `loadOrderArchive` | Đọc prefix của tenant khác hoặc bucket khác. |
| `receiveOrder` | Consume topic/group không được cấp ACL. |
| `publishOrderStatus` | Publish topic khác hoặc tạo topic mới. |

### 18.3. Kiểm tra trong CI/CD

- Validate JSON/YAML policy và IaC.
- Dùng IAM policy simulator/Access Analyzer hoặc công cụ tương ứng của cloud provider.
- Kiểm tra Kafka ACL bằng tooling của broker; thử consumer group thực tế.
- Kiểm tra RabbitMQ permission theo vhost/resource và test user không có admin tag.
- Test workload identity trong môi trường gần production; local mock không chứng minh policy cloud thực tế.
- Chạy smoke test sau deployment và lưu kết quả principal/action/resource.

LocalStack, emulator hoặc mock client có thể hữu ích cho logic, nhưng không thay thế authorization test trên AWS/GCP/Azure hoặc broker thực tế. Một mock có thể bỏ qua resource policy, KMS, ACL, IAM propagation hoặc cấu hình TLS.

## 19. Quy trình thiết kế quyền cho một function mới

Khi thêm function vào Spring Cloud Function:

1. **Mô tả nghiệp vụ:** function đọc, ghi, publish, consume hay gọi secret/API nào?
2. **Xác định workload boundary:** function có process/deployment riêng hay chia sẻ identity với các function khác?
3. **Chọn identity:** execution role, managed identity, service account hoặc broker principal.
4. **Liệt kê action/resource:** ghi rõ API operation, bucket prefix, queue, topic, subscription, consumer group và secret.
5. **Tách control-plane khỏi data-plane:** provisioning tạo resource; runtime chỉ xử lý dữ liệu.
6. **Viết policy hẹp:** không wildcard action/resource khi chưa có lý do.
7. **Cấu hình client/binder:** dùng credential provider/workload identity, TLS và secret injection.
8. **Chạy positive và negative test:** xác nhận quyền cần có hoạt động và quyền không cần vẫn bị từ chối.
9. **Quan sát/audit:** ghi nhận principal và resource, theo dõi denied events, rotation và thay đổi policy.
10. **Rà soát định kỳ:** thu hồi quyền không còn dùng và đánh giá lại sau khi function thay đổi.

## 20. Bài tập thực hành

### Bài 1 — Chỉ ghi object vào một prefix

Tạo function `archiveOrder` dùng AWS SDK `S3Client` để ghi object vào bucket `order-archive`, prefix `orders/`.

1. Gắn execution role riêng cho Lambda.
2. Chỉ cấp `s3:PutObject` trên `arn:aws:s3:::order-archive/orders/*`.
3. Gọi function và xác nhận upload thành công.
4. Thử `GetObject`, `DeleteObject` và ghi vào prefix `private/`; các thao tác đó phải bị từ chối.
5. Nếu bật SSE-KMS, cấp quyền KMS đúng key và thử lại.

### Bài 2 — Consumer Kafka chỉ đọc một topic/group

1. Tạo principal `order-normalizer`.
2. Tạo topic `orders.in` và consumer group `order-normalizers` trước bằng pipeline quản trị.
3. Cấp `READ`/`DESCRIBE` trên topic và `READ` trên group tương ứng.
4. Cấu hình Spring Cloud Stream binding đúng destination/group và SASL_SSL.
5. Xác nhận consume thành công; thử đổi sang topic/group khác và xác nhận broker từ chối.
6. Kiểm tra runtime không có quyền CREATE/DELETE topic.

### Bài 3 — Phân quyền producer/consumer RabbitMQ

1. Tạo vhost `orders-vhost`, queue `orders.input`, exchange `orders.status`.
2. Cấp cho `order-consumer` chỉ quyền read trên queue.
3. Cấp cho `order-publisher` chỉ quyền write trên exchange.
4. Xác nhận consumer không publish và publisher không consume.
5. Xác nhận cả hai không có configure permission hoặc administrator tag.

### Bài 4 — Tách function theo identity

Có `archiveOrder` cần ghi S3 và `publishOrderStatus` cần publish Kafka. Hãy triển khai hai workload riêng, cấp role/credential khác nhau, rồi thử dùng credential của workload thứ nhất gọi thao tác của workload thứ hai. Request phải bị từ chối.

**Tiêu chí đạt:** giải thích được vì sao `FunctionCatalog` không tạo security boundary, vì sao bean trong cùng process thường chia sẻ workload identity, và chứng minh được cả thao tác hợp lệ lẫn thao tác vượt quyền.

## 21. Tài liệu tham khảo

- [AWS Lambda — Execution role và least privilege](https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html): execution role, policy tinh gọn và IAM Access Analyzer.
- [AWS Lambda — Managing permissions](https://docs.aws.amazon.com/lambda/latest/dg/lambda-permissions.html): identity-based và resource-based policies.
- [AWS Lambda — SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html): quyền poll queue và KMS.
- [Amazon S3 — IAM integration](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security_iam_service-with-iam.html): bucket ARN, object ARN và quyền S3.
- [Google Cloud Pub/Sub — Access control](https://docs.cloud.google.com/pubsub/docs/access-control): Publisher/Subscriber roles và resource-level IAM.
- [Azure Service Bus — Managed Identity](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-managed-service-identity): Data Sender/Receiver và RBAC scope.
- [Apache Kafka — Authorization and ACLs](https://kafka.apache.org/44/security/authorization-and-acls/): topic, group, cluster ACLs và operation.
- [RabbitMQ — Access control](https://www.rabbitmq.com/docs/access-control): vhost, configure/write/read permission và management tags.
- [Spring Cloud Stream — Kafka security configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/security-config.html): SASL/JAAS và binder client properties.

Tên role, property và hành vi binder phụ thuộc version. Đối chiếu tài liệu đúng release và kiểm thử với broker/cloud runtime thực tế trước khi đưa policy vào production.

## 22. Kết luận

**Quyền tối thiểu bắt đầu từ identity của workload và kết thúc ở từng resource/action cụ thể.** Với Spring Cloud Function, `Supplier`, `Function`, `Consumer` và `FunctionCatalog` giúp tổ chức nghiệp vụ; chúng không tự giới hạn quyền cloud hoặc broker. Một process có thể chứa nhiều bean nhưng vẫn dùng chung execution role hoặc broker credential, vì vậy tách bean không đồng nghĩa tách security boundary.

Thiết kế an toàn là dùng workload identity/managed credentials, tách inbound permission khỏi outbound permission, giới hạn action và resource, tách provisioning khỏi data-plane, dùng broker ACL theo topic/group/vhost, quản lý secret và TLS, rồi kiểm thử cả quyền được phép lẫn quyền bị từ chối. Khi cần các function có quyền khác nhau, hãy cân nhắc tách chúng thành workload riêng để có identity, policy, audit và vòng đời độc lập.
