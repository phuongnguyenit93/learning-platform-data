# Bảo mật, xác thực IAM và kết nối client Kafka với MSK

## Mục tiêu học tập

Amazon Managed Streaming for Apache Kafka (Amazon MSK) quản lý hạ tầng broker Apache Kafka, nhưng ứng dụng vẫn phải kết nối đúng endpoint, xác thực danh tính và có quyền thực hiện thao tác trên cluster. Một client có thể phân giải DNS và mở được TCP connection nhưng vẫn không produce hoặc consume được vì thiếu quyền Kafka. Ngược lại, IAM policy có thể đúng nhưng kết nối vẫn timeout do security group, route hoặc bootstrap broker không phù hợp.

Trong module CLOUD_PROVIDERS_AWS, người học cần hiểu cách đặt MSK trong VPC, chọn cơ chế xác thực phù hợp và thiết kế quyền theo nguyên tắc least privilege. Bài học này tập trung vào IAM access control, cách kết nối Kafka client, cùng những lựa chọn SASL/SCRAM và mutual TLS (mTLS) để biết khi nào chúng phù hợp.

Sau bài học, người học có thể:

- Phân biệt authentication, authorization, network access và encryption.
- Giải thích IAM access control của MSK và sự khác nhau giữa API control plane với Kafka data plane.
- Chọn IAM, SASL/SCRAM hoặc mTLS theo danh tính, môi trường chạy và yêu cầu quản trị.
- Cấu hình Java Kafka client bằng cơ chế AWS_MSK_IAM và thư viện aws-msk-iam-auth.
- Cấu hình client không dùng Java bằng SASL_OAUTHBEARER và thư viện ký token tương ứng.
- Viết IAM policy giới hạn quyền theo cluster, topic, consumer group và transactional ID.
- Lấy đúng bootstrap broker string và chọn đúng port theo phương thức xác thực.
- Kết nối MSK Provisioned và MSK Serverless trong VPC.
- Thiết kế kết nối cross-account bằng MSK cluster policy và multi-VPC private connectivity.
- Điều tra lỗi DNS, TCP, TLS, SASL và authorization theo từng lớp.

## 1. Bốn lớp bảo vệ khi kết nối Kafka

Khi một ứng dụng kết nối đến broker MSK, có bốn câu hỏi độc lập:

1. **Network access:** client có route và được security group/network ACL cho phép đến broker không?
2. **Encryption:** dữ liệu trên đường truyền có được bảo vệ bằng TLS không?
3. **Authentication:** broker xác định client là ai bằng cách nào?
4. **Authorization:** danh tính đó được phép kết nối, đọc topic, ghi topic hoặc tham gia consumer group nào?

Một request chỉ thành công khi các lớp cần thiết đều đúng. IAM không mở cổng mạng; security group không cấp quyền đọc topic; TLS không tự chứng minh client được phép produce; bootstrap server không cấp quyền Kafka.

~~~mermaid
sequenceDiagram
    participant C as Kafka client
    participant N as VPC / Security Group
    participant B as MSK broker
    participant I as IAM / Kafka authorizer
    C->>N: DNS lookup và TCP connect
    N->>B: Cho phép kết nối đến listener
    C->>B: TLS handshake (kèm client certificate nếu dùng mTLS)
    C->>B: SASL authentication nếu dùng IAM hoặc SCRAM
    B->>I: Xác minh danh tính và quyền
    I-->>B: Allow hoặc Deny
    B-->>C: Kafka response
~~~

Ví dụ, lỗi **Connection timed out** thường cần điều tra network trước. Lỗi **SaslAuthenticationException** thường liên quan đến cơ chế xác thực hoặc credential. Lỗi **TopicAuthorizationException** cho thấy client đã đi xa hơn nhưng không có quyền trên topic. Đọc đúng lớp lỗi giúp tránh sửa IAM policy khi nguyên nhân thực tế là DNS hoặc port.

## 2. Authentication và authorization trong MSK

Authentication xác định principal đang kết nối. Principal có thể là IAM role, user SCRAM hoặc danh tính từ client certificate. Authorization quyết định principal đó được phép làm gì trên cluster.

Amazon MSK hỗ trợ các cơ chế chính sau cho MSK Provisioned:

| Cơ chế | Authentication | Authorization thường dùng | Đặc điểm |
|---|---|---|---|
| IAM access control | AWS IAM identity và chữ ký SigV4 | IAM policy với prefix kafka-cluster: | Gộp authentication và authorization; phù hợp workload dùng IAM role |
| SASL/SCRAM | Username/password lưu trong Secrets Manager | Apache Kafka ACL | Tách credential khỏi quyền topic; phù hợp khi cần mô hình user/password |
| Mutual TLS | Client certificate do AWS Private CA cấp | Apache Kafka ACL | Xác thực bằng certificate; phù hợp PKI và workload có certificate lifecycle |
| Unauthenticated | Không xác thực | Không có kiểm soát danh tính ở lớp client | Chỉ cân nhắc cho môi trường thử nghiệm cô lập |

Không bật nhiều cơ chế chỉ vì có thể. Mỗi cơ chế bổ sung làm tăng số credential, listener, quy trình rotation và cách xử lý incident. Chọn phương thức theo danh tính sẵn có và khả năng vận hành của tổ chức.

## 3. IAM access control giải quyết điều gì?

IAM access control cho MSK xử lý cả authentication và authorization cho IAM identity. Client dùng AWS credentials để chứng minh danh tính; MSK đánh giá IAM policy để xác định các thao tác Kafka được phép.

Ví dụ:

- Một ECS task chạy với task role orders-producer-role.
- Client Kafka lấy temporary credentials từ task metadata.
- Thư viện MSK IAM ký thông điệp xác thực bằng SigV4.
- Broker xác minh IAM principal và kiểm tra policy cho cluster/topic.
- Producer chỉ ghi được vào topic được policy cho phép.

Cách này tránh lưu username/password hoặc access key dài hạn trong file cấu hình. Khi task được thay thế hoặc credentials được làm mới, AWS credential provider chain có thể lấy temporary credentials mới.

IAM access control hoạt động với Java và các client không dùng Java như Python, Go, JavaScript và .NET. Với client không dùng Java, AWS nêu yêu cầu cluster chạy Kafka 2.7.1 trở lên cho IAM access control.

Một điểm quan trọng: Apache Kafka ACL APIs có thể được gọi trên cluster dùng IAM access control, nhưng ACL không quyết định quyền của IAM identity. Với principal IAM, phải dùng IAM authorization policy.

IAM access control cũng không bảo vệ Apache ZooKeeper nodes của các cluster còn dùng ZooKeeper. Nếu phải truy cập ZooKeeper, thiết kế security group và cơ chế kiểm soát ZooKeeper riêng; không suy ra rằng quyền IAM của Kafka broker đã bao phủ ZooKeeper.

## 4. Phân biệt control plane và Kafka data plane

MSK có hai nhóm hành động có tên gần giống nhau nhưng thuộc hai lớp khác nhau.

| Prefix | Lớp | Ví dụ | Mục đích |
|---|---|---|---|
| kafka: | MSK control plane | kafka:DescribeCluster, kafka:GetBootstrapBrokers | Quản lý hoặc truy vấn tài nguyên MSK qua AWS API |
| kafka-cluster: | Kafka data plane | kafka-cluster:Connect, kafka-cluster:WriteData | Cho phép Kafka client thực hiện thao tác trên cluster/topic/group |

Ví dụ, một pipeline quản trị cần gọi AWS CLI để lấy bootstrap broker có thể cần kafka:GetBootstrapBrokers. Nhưng quyền đó không tự cho phép producer ghi message vào topic.

Ngược lại, role chỉ có kafka-cluster:Connect và kafka-cluster:WriteData có thể thực hiện thao tác Kafka phù hợp nhưng chưa chắc có quyền gọi AWS API để liệt kê cluster hoặc lấy endpoint.

Tách hai nhóm quyền giúp role ứng dụng không vô tình có quyền tạo, xóa hoặc thay đổi cluster.

## 5. IAM principal và nguồn credential của client

Client cần một nguồn AWS credential hợp lệ. Trong môi trường AWS, ưu tiên temporary credentials từ IAM role:

| Môi trường client | Nguồn danh tính nên dùng |
|---|---|
| Amazon EC2 | Instance profile role |
| Amazon ECS | Task role của task |
| Amazon EKS | EKS Pod Identity hoặc IAM Roles for Service Accounts (IRSA) |
| AWS Lambda | Execution role |
| Máy phát triển | AWS IAM Identity Center hoặc named profile |
| Workload ở account khác | AssumeRole hoặc cross-account IAM setup theo kiến trúc |

Thư viện aws-msk-iam-auth dùng AWS credential provider chain. Không đưa access key và secret key vào source code, image, client.properties, manifest hoặc log.

Với named profile, có thể cấu hình awsProfileName trong JAAS options. Trong production, nên để workload identity cung cấp credential tự động. Nếu role cần assume role ở account khác, kiểm tra cả trust policy của role đích và quyền sts:AssumeRole của principal nguồn.

Kiểm tra danh tính hiện tại bằng AWS CLI:

~~~bash
aws sts get-caller-identity
~~~

Kết quả phải là role hoặc principal mà nhóm vận hành dự kiến. Nếu CLI và Kafka client chạy trong hai môi trường khác nhau, không giả định chúng dùng cùng một credential source.

## 6. Bật IAM access control trên MSK Provisioned

Khi tạo MSK Provisioned cluster, bật IAM role-based authentication trong phần Security settings. Nếu tạo bằng API hoặc AWS CLI, phần client authentication có dạng:

~~~json
{
  "ClientAuthentication": {
    "Sasl": {
      "Iam": {
        "Enabled": true
      }
    }
  }
}
~~~

IAM authentication yêu cầu mã hóa client-to-broker bằng TLS. Không cấu hình IAM listener trên kết nối plaintext. Nếu bật IAM trên cluster đã tồn tại, kiểm tra trạng thái cluster, cấu hình encryption-in-transit và tác động đến client trước khi thay đổi.

Cluster có thể bật thêm phương thức xác thực khác nếu dịch vụ và cấu hình cho phép. Tuy nhiên, mỗi listener phải được dùng với đúng bootstrap string, port và client properties tương ứng.

## 7. Cấu hình Java client với AWS_MSK_IAM

Java có thể dùng cơ chế SASL tùy biến AWS_MSK_IAM. Cơ chế này được triển khai bởi thư viện aws-msk-iam-auth.

Thêm dependency Maven. Phiên bản 2.3.9 là bản phát hành ổn định được công bố tại Maven Central tại thời điểm biên soạn; kiểm tra release mới nhất và tương thích với Kafka client trước khi nâng cấp.

~~~xml
<dependency>
    <groupId>software.amazon.msk</groupId>
    <artifactId>aws-msk-iam-auth</artifactId>
    <version>2.3.9</version>
</dependency>
~~~

Cấu hình client:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=AWS_MSK_IAM
sasl.jaas.config=software.amazon.msk.auth.iam.IAMLoginModule required;
sasl.client.callback.handler.class=software.amazon.msk.auth.iam.IAMClientCallbackHandler
~~~

Nếu cần dùng named profile trên máy phát triển, thêm option vào JAAS config:

~~~properties
sasl.jaas.config=software.amazon.msk.auth.iam.IAMLoginModule required awsProfileName="dev-msk";
~~~

Không cần tự sinh SASL password hoặc chép access key vào cấu hình. Thư viện tìm AWS credentials từ provider chain, tạo chữ ký xác thực và xử lý việc làm mới credential theo cơ chế của thư viện.

### 7.1. Java producer tối giản

Ví dụ dưới đây đọc bootstrap string từ environment variable và sử dụng IAM role của tiến trình:

~~~java
import java.util.Properties;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;

public class MskIamProducer {
    public static void main(String[] args) {
        String bootstrapServers =
            System.getenv("MSK_BOOTSTRAP_SERVERS");

        if (bootstrapServers == null || bootstrapServers.isBlank()) {
            throw new IllegalStateException(
                "MSK_BOOTSTRAP_SERVERS is required"
            );
        }

        Properties props = new Properties();
        props.put("bootstrap.servers", bootstrapServers);
        props.put("key.serializer",
            "org.apache.kafka.common.serialization.StringSerializer");
        props.put("value.serializer",
            "org.apache.kafka.common.serialization.StringSerializer");

        props.put("security.protocol", "SASL_SSL");
        props.put("sasl.mechanism", "AWS_MSK_IAM");
        props.put("sasl.jaas.config",
            "software.amazon.msk.auth.iam.IAMLoginModule required;");
        props.put("sasl.client.callback.handler.class",
            "software.amazon.msk.auth.iam.IAMClientCallbackHandler");

        try (KafkaProducer<String, String> producer =
                 new KafkaProducer<>(props)) {
            ProducerRecord<String, String> record =
                new ProducerRecord<>(
                    "orders",
                    "order-1001",
                    "{\"orderId\":\"order-1001\",\"status\":\"CREATED\"}"
                );

            producer.send(record).get();
            producer.flush();
        } catch (Exception e) {
            throw new RuntimeException("Cannot publish to MSK", e);
        }
    }
}
~~~

Producer phải có quyền Connect, DescribeTopic và WriteData trên tài nguyên tương ứng. Nếu topic chưa tồn tại, cần tạo topic bằng quy trình quản trị hoặc cấp thêm quyền CreateTopic theo policy được phê duyệt.

### 7.2. Java consumer tối giản

Consumer cần thêm quyền trên consumer group. Ví dụ:

~~~java
import java.time.Duration;
import java.util.Collections;
import java.util.Properties;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;

public class MskIamConsumer {
    public static void main(String[] args) {
        String bootstrapServers =
            System.getenv("MSK_BOOTSTRAP_SERVERS");

        Properties props = new Properties();
        props.put("bootstrap.servers", bootstrapServers);
        props.put("group.id", "orders-reader");
        props.put("auto.offset.reset", "earliest");
        props.put("enable.auto.commit", "false");
        props.put("key.deserializer",
            "org.apache.kafka.common.serialization.StringDeserializer");
        props.put("value.deserializer",
            "org.apache.kafka.common.serialization.StringDeserializer");

        props.put("security.protocol", "SASL_SSL");
        props.put("sasl.mechanism", "AWS_MSK_IAM");
        props.put("sasl.jaas.config",
            "software.amazon.msk.auth.iam.IAMLoginModule required;");
        props.put("sasl.client.callback.handler.class",
            "software.amazon.msk.auth.iam.IAMClientCallbackHandler");

        try (KafkaConsumer<String, String> consumer =
                 new KafkaConsumer<>(props)) {
            consumer.subscribe(Collections.singletonList("orders"));

            while (true) {
                ConsumerRecords<String, String> records =
                    consumer.poll(Duration.ofSeconds(1));

                for (ConsumerRecord<String, String> record : records) {
                    System.out.printf(
                        "topic=%s partition=%d offset=%d key=%s value=%s%n",
                        record.topic(),
                        record.partition(),
                        record.offset(),
                        record.key(),
                        record.value()
                    );
                }

                if (!records.isEmpty()) {
                    consumer.commitSync();
                }
            }
        }
    }
}
~~~

Đây là ví dụ kết nối và đọc message để học. Ứng dụng production cần bổ sung shutdown handling, retry có giới hạn, xử lý lỗi theo loại, commit offset theo semantics nghiệp vụ và quản lý consumer rebalance.

## 8. IAM access control cho client không dùng Java

Client không dùng Java sử dụng SASL mechanism OAUTHBEARER. AWS cung cấp thư viện ký MSK auth token cho các ngôn ngữ như Python, JavaScript, Go và .NET.

Luồng hoạt động:

1. Client lấy AWS credentials từ môi trường hoặc workload role.
2. Thư viện signer tạo token IAM cho Region của cluster.
3. Kafka client đưa token vào SASL/OAUTHBEARER.
4. Broker xác minh token và đánh giá IAM policy.

Ví dụ Python theo mô hình kafka-python và signer của AWS:

~~~python
import socket
from kafka import KafkaProducer
from aws_msk_iam_sasl_signer import MSKAuthTokenProvider

AWS_REGION = "ap-southeast-1"
BOOTSTRAP_SERVERS = "replace-with-iam-bootstrap-brokers"

class MskTokenProvider:
    def token(self):
        token, expiry_ms = MSKAuthTokenProvider.generate_auth_token(
            AWS_REGION
        )
        return token

producer = KafkaProducer(
    bootstrap_servers=BOOTSTRAP_SERVERS,
    security_protocol="SASL_SSL",
    sasl_mechanism="OAUTHBEARER",
    sasl_oauth_token_provider=MskTokenProvider(),
    client_id=socket.gethostname()
)

try:
    producer.send(
        "orders",
        key=b"order-1001",
        value=b'{"orderId":"order-1001","status":"CREATED"}'
    ).get()
    producer.flush()
finally:
    producer.close()
~~~

API của token provider và tham số của Kafka client phụ thuộc phiên bản thư viện. Dùng ví dụ Getting Started của signer tương ứng với ngôn ngữ và phiên bản client đang triển khai. Không tự lưu token dài hạn: token có thời hạn và cần được tạo lại khi client xác thực lại.

## 9. IAM authorization policy và ARN của Kafka resource

IAM data-plane policy dùng bốn loại resource:

| Resource | ARN format |
|---|---|
| Cluster | arn:aws:kafka:region:account-id:cluster/cluster-name/cluster-uuid |
| Topic | arn:aws:kafka:region:account-id:topic/cluster-name/cluster-uuid/topic-name |
| Consumer group | arn:aws:kafka:region:account-id:group/cluster-name/cluster-uuid/group-name |
| Transactional ID | arn:aws:kafka:region:account-id:transactional-id/cluster-name/cluster-uuid/transactional-id |

Ví dụ cluster ARN:

~~~text
arn:aws:kafka:ap-southeast-1:123456789012:cluster/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1
~~~

Topic ARN phải chứa cùng cluster name và UUID:

~~~text
arn:aws:kafka:ap-southeast-1:123456789012:topic/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1/orders
~~~

Không nhầm cluster ARN với topic ARN. Dùng wildcard * để mở rộng phạm vi chỉ khi có lý do rõ ràng. Policy cho topic orders nên giới hạn đúng topic đó thay vì cấp quyền topic/* cho toàn cluster.

## 10. Policy tối thiểu cho producer

Producer ghi message vào topic orders. Nó cần kết nối cluster và mô tả/ghi dữ liệu vào topic đó.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConnectToOrdersCluster",
      "Effect": "Allow",
      "Action": [
        "kafka-cluster:Connect"
      ],
      "Resource": [
        "arn:aws:kafka:ap-southeast-1:123456789012:cluster/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1"
      ]
    },
    {
      "Sid": "WriteOrdersTopic",
      "Effect": "Allow",
      "Action": [
        "kafka-cluster:DescribeTopic",
        "kafka-cluster:WriteData"
      ],
      "Resource": [
        "arn:aws:kafka:ap-southeast-1:123456789012:topic/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1/orders"
      ]
    }
  ]
}
~~~

Policy này không cấp quyền tạo hoặc xóa topic. Một producer chỉ gửi message không nên mặc định có kafka-cluster:* hoặc quyền quản trị cluster.

## 11. Policy tối thiểu cho consumer

Consumer đọc topic orders bằng consumer group orders-reader. Ngoài quyền đọc topic, consumer cần quyền tham gia và cập nhật offset của group.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConnectToOrdersCluster",
      "Effect": "Allow",
      "Action": [
        "kafka-cluster:Connect"
      ],
      "Resource": [
        "arn:aws:kafka:ap-southeast-1:123456789012:cluster/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1"
      ]
    },
    {
      "Sid": "ReadOrdersTopic",
      "Effect": "Allow",
      "Action": [
        "kafka-cluster:DescribeTopic",
        "kafka-cluster:ReadData"
      ],
      "Resource": [
        "arn:aws:kafka:ap-southeast-1:123456789012:topic/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1/orders"
      ]
    },
    {
      "Sid": "UseOrdersConsumerGroup",
      "Effect": "Allow",
      "Action": [
        "kafka-cluster:DescribeGroup",
        "kafka-cluster:AlterGroup"
      ],
      "Resource": [
        "arn:aws:kafka:ap-southeast-1:123456789012:group/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1/orders-reader"
      ]
    }
  ]
}
~~~

ReadData cần các quyền phụ thuộc được MSK định nghĩa, gồm Connect, DescribeTopic và AlterGroup. AlterGroup cho phép client tham gia group và cập nhật trạng thái/offset liên quan. Nếu consumer dùng group ID khác, ARN group trong policy phải khớp.

## 12. Các quyền Kafka data plane thường gặp

| Nhu cầu | Action cần xem xét | Resource |
|---|---|---|
| Kết nối cluster | kafka-cluster:Connect | Cluster |
| Xem topic | kafka-cluster:DescribeTopic | Topic |
| Ghi message | kafka-cluster:WriteData | Topic |
| Đọc message | kafka-cluster:ReadData | Topic |
| Tạo topic | kafka-cluster:CreateTopic | Topic |
| Sửa topic | kafka-cluster:AlterTopic | Topic |
| Xóa topic | kafka-cluster:DeleteTopic | Topic |
| Xem consumer group | kafka-cluster:DescribeGroup | Group |
| Tham gia/cập nhật group | kafka-cluster:AlterGroup | Group |
| Xóa group | kafka-cluster:DeleteGroup | Group |
| Dùng transactional ID | kafka-cluster:DescribeTransactionalId, kafka-cluster:AlterTransactionalId | Transactional ID |
| Thay đổi cluster | kafka-cluster:AlterCluster | Cluster |

Một số action yêu cầu action khác đi kèm. Ví dụ AlterTopic yêu cầu Connect và DescribeTopic; AlterGroup yêu cầu Connect và DescribeGroup. Luôn đối chiếu bảng Required actions của AWS trước khi viết policy.

kafka-cluster:*Topic* không bao gồm tất cả action có chữ Topic. Theo định nghĩa của AWS, wildcard này bao gồm các action topic cơ bản như CreateTopic, DescribeTopic, AlterTopic và DeleteTopic, nhưng không bao gồm các action dynamic configuration. Không dùng wildcard như một cách thay thế cho việc đọc danh sách quyền cần thiết.

## 13. Idempotence và transaction khi dùng IAM

Producer idempotent giảm khả năng ghi trùng khi retry. Producer transaction có thể ghi nguyên tử qua nhiều partition và kết hợp offset trong một số luồng xử lý.

Khi dùng IAM:

- Idempotent write cần quyền kafka-cluster:WriteDataIdempotently ở phạm vi cluster cùng các quyền kết nối/ghi cần thiết.
- Transaction cần quyền mô tả và thay đổi transactional ID trên resource tương ứng.
- Với Kafka 2.8 trở lên, enable.idempotence mặc định bật; IAM có một số khác biệt so với Kafka ACL khi giới hạn WriteData ở một topic cụ thể.
- AWS ghi rõ IAM access control hỗ trợ API WriteTxnMarkers để kết thúc transaction trên cluster Kafka 3.8 trở lên. Với version trước 3.8, internal action này không được IAM hỗ trợ; cần đánh giá SCRAM hoặc mTLS cùng ACL nếu workload phụ thuộc transaction.

Ví dụ policy cần có transactional ID riêng:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConnectAndEnableIdempotentWrites",
      "Effect": "Allow",
      "Action": [
        "kafka-cluster:Connect",
        "kafka-cluster:WriteDataIdempotently"
      ],
      "Resource": [
        "arn:aws:kafka:ap-southeast-1:123456789012:cluster/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1"
      ]
    },
    {
      "Sid": "WriteOrders",
      "Effect": "Allow",
      "Action": [
        "kafka-cluster:DescribeTopic",
        "kafka-cluster:WriteData"
      ],
      "Resource": [
        "arn:aws:kafka:ap-southeast-1:123456789012:topic/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1/orders"
      ]
    },
    {
      "Sid": "UseOrderTransactions",
      "Effect": "Allow",
      "Action": [
        "kafka-cluster:DescribeTransactionalId",
        "kafka-cluster:AlterTransactionalId"
      ],
      "Resource": [
        "arn:aws:kafka:ap-southeast-1:123456789012:transactional-id/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1/orders-writer-*"
      ]
    }
  ]
}
~~~

Đây là mẫu định hướng. Kiểm tra lại yêu cầu phụ thuộc action và phiên bản Kafka đang chạy. Không cấp quyền transactional ID rộng toàn cluster nếu producer chỉ cần một namespace ID.

## 14. IAM control-plane policy cho người vận hành

Một role quản trị hoặc pipeline có thể cần lấy thông tin cluster và bootstrap broker. Đây là policy khác với quyền produce/consume.

Ví dụ chỉ cho phép mô tả cluster và lấy bootstrap broker:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOrdersClusterMetadata",
      "Effect": "Allow",
      "Action": [
        "kafka:DescribeCluster",
        "kafka:DescribeClusterV2",
        "kafka:GetBootstrapBrokers"
      ],
      "Resource": [
        "arn:aws:kafka:ap-southeast-1:123456789012:cluster/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1"
      ]
    }
  ]
}
~~~

Nếu pipeline tạo cluster với custom configuration, AWS đánh giá kafka:CreateCluster hoặc kafka:CreateClusterV2 trên cả cluster resource và configuration resource. Một policy chỉ cho phép cluster ARN có thể gây AccessDeniedException với configuration ARN. Tách statement tạo cluster và cấp resource phù hợp theo tài liệu control-plane policy.

## 15. SASL/SCRAM với AWS Secrets Manager

SASL/SCRAM xác thực client bằng username/password. MSK lưu thông tin đăng nhập trong AWS Secrets Manager và đồng bộ credential được liên kết với cluster theo chu kỳ. SCRAM dùng cơ chế challenge-response và không gửi password dạng plaintext qua mạng; MSK bật TLS cho client-broker traffic khi cấu hình SCRAM.

Các yêu cầu khi tạo secret:

- Chọn loại secret là Other type of secrets.
- Tên secret phải bắt đầu bằng prefix AmazonMSK_.
- Dùng customer managed AWS KMS key; secret dùng mặc định AWS managed key của Secrets Manager không thể liên kết với MSK.
- Credential JSON có hai field username và password.
- Ghi lại ARN của secret để associate với cluster.

Ví dụ giá trị secret:

~~~json
{
  "username": "orders-writer",
  "password": "replace-with-a-generated-long-random-secret"
}
~~~

Tạo secret bằng console hoặc AWS CLI, sau đó associate với cluster bằng console hoặc BatchAssociateScramSecret. Khi associate, MSK gắn resource policy vào secret để cluster đọc credential. Không tự sửa policy đó; nếu policy hoặc KMS key thay đổi, cần associate lại secret theo hướng dẫn AWS.

MSK hỗ trợ SCRAM-SHA-512. Không dùng SASL/PLAIN với MSK. Khi ứng dụng lấy credential, đọc từ Secrets Manager qua IAM role và inject vào Kafka client tại runtime; tránh ghi username/password vào source control hoặc image.

### 15.1. Java client properties cho SCRAM

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="INJECT_USERNAME" password="INJECT_PASSWORD";
~~~

Các giá trị INJECT_USERNAME và INJECT_PASSWORD là giá trị minh họa. Ứng dụng phải đọc secret bằng role được cấp secretsmanager:GetSecretValue trên đúng secret ARN, sau đó tạo cấu hình client an toàn. Không commit file đã chứa credential thật.

Với SCRAM, authorization topic/group dựa trên Apache Kafka ACL. Hãy tạo ACL trước và cấu hình allow.everyone.if.no.acl.found=false để resource không có ACL không mặc định mở cho mọi principal. Thực hiện thay đổi này có kế hoạch vì nó ảnh hưởng toàn bộ client đang dùng cluster.

## 16. Mutual TLS (mTLS) với AWS Private CA

mTLS yêu cầu client trình certificate khi thiết lập TLS. MSK xác minh certificate chain theo AWS Private CA được cấu hình trên cluster. CA có thể ở cùng account hoặc account khác.

Quy trình tổng quát:

1. Tạo hoặc chọn AWS Private CA dành cho MSK cluster.
2. Client tạo private key và CSR.
3. AWS Private CA ký certificate.
4. Client lưu private key và certificate chain trong keystore.
5. Client tin cậy certificate của broker thông qua truststore.
6. Kafka client kết nối bằng security.protocol=SSL.
7. Apache Kafka ACL quyết định principal certificate được phép đọc/ghi topic nào.

AWS khuyến nghị dùng Private CA độc lập cho mỗi MSK cluster để certificate của cluster này không vô tình được chấp nhận trên cluster khác.

### 16.1. Client properties cho mTLS

~~~properties
security.protocol=SSL
ssl.truststore.location=/secure/path/kafka.client.truststore.jks
ssl.keystore.location=/secure/path/kafka.client.keystore.p12
ssl.keystore.type=PKCS12
ssl.keystore.password=INJECT_STORE_PASSWORD
ssl.key.password=INJECT_KEY_PASSWORD
~~~

Bảo vệ private key, keystore và password như secret. Không đặt keystore trong image công khai hoặc repository. Thiết lập quy trình cấp mới, thay thế, hết hạn và xử lý certificate bị lộ.

### 16.2. Giới hạn certificate revocation

Amazon MSK không hỗ trợ Certificate Revocation List (CRL) cho mTLS. Để chặn client certificate bị xâm phạm, cần kế hoạch thu hồi ở lớp vận hành: cập nhật trust boundary/CA theo quy trình, điều chỉnh Kafka ACL và security group, thay certificate và đánh giá kết nối còn hiệu lực. Không giả định xóa certificate ở ACM tự động làm broker từ chối mọi certificate đã phát hành.

Khi dùng mTLS, principal có thể được ánh xạ từ Distinguished Name, ví dụ User:CN=orders-writer. Kafka ACL phải khớp principal thực tế được broker nhận diện.

## 17. So sánh IAM, SCRAM và mTLS

| Tiêu chí | IAM | SASL/SCRAM | mTLS |
|---|---|---|---|
| Danh tính | IAM user/role | Username/password | Client certificate |
| Kho credential | AWS credential provider chain | Secrets Manager | Keystore/PKI |
| Authorization | IAM data-plane policy | Kafka ACL | Kafka ACL |
| Rotation | Temporary credential tự làm mới | Rotate secret và đồng bộ user | Renew/reissue certificate |
| Hợp với workload AWS | Rất phù hợp | Phù hợp nếu cần user/password | Phù hợp nếu đã có PKI |
| Hợp với client ngoài AWS | Có thể dùng federation/role | Có thể | Có thể |
| MSK Serverless | Bắt buộc | Không hỗ trợ | Không hỗ trợ |
| Quản trị quyền topic | IAM resource policy | Kafka ACL | Kafka ACL |

IAM thường là lựa chọn đơn giản cho workload chạy trên AWS vì tận dụng role và temporary credentials. SCRAM phù hợp khi tổ chức đã có quy trình user/password. mTLS phù hợp khi danh tính thiết bị hoặc ứng dụng được quản trị bằng PKI.

## 18. Encryption in transit và encryption at rest

Amazon MSK luôn mã hóa dữ liệu lưu trữ (at rest) bằng AWS KMS. Khi tạo cluster, có thể chọn customer managed key; nếu không chọn, MSK dùng AWS managed key.

Đối với dữ liệu truyền:

- TLS 1.2 là cấu hình mặc định được MSK công bố.
- MSK Provisioned có thể dùng TLS security policy để bật TLS 1.3 theo điều kiện hỗ trợ.
- IAM và SASL/SCRAM yêu cầu TLS cho client-broker.
- mTLS cũng dùng TLS và client certificate.
- Không mở plaintext listener cho workload production chỉ để giải quyết lỗi client.

Mã hóa giữa broker với broker là một cấu hình riêng. Không nhầm encryption at rest với TLS client-to-broker. Dữ liệu đã mã hóa trên disk vẫn có thể đi qua một kết nối plaintext nếu cluster cho phép và client chọn sai listener.

## 19. Lấy bootstrap broker đúng cơ chế

Bootstrap brokers là danh sách điểm vào ban đầu để Kafka client tìm metadata và các broker khác. Danh sách này không nhất thiết chứa mọi broker trong cluster. Không tự tạo endpoint bằng cách ghép hostname hoặc đoán port.

Lấy thông tin bằng AWS CLI:

~~~bash
aws kafka get-bootstrap-brokers --cluster-arn "$MSK_CLUSTER_ARN"
~~~

Với cluster dùng IAM, lấy field BootstrapBrokerStringSaslIam:

~~~bash
aws kafka get-bootstrap-brokers \
  --cluster-arn "$MSK_CLUSTER_ARN" \
  --query BootstrapBrokerStringSaslIam \
  --output text
~~~

Các field thường gặp:

| Field | Dùng khi |
|---|---|
| BootstrapBrokerStringTls | Client dùng TLS listener |
| BootstrapBrokerStringSaslScram | Client dùng SASL/SCRAM |
| BootstrapBrokerStringSaslIam | Client dùng SASL/IAM |
| BootstrapBrokerStringPublicTls | Client kết nối public qua TLS |
| BootstrapBrokerStringPublicSaslScram | Client kết nối public qua SCRAM |
| BootstrapBrokerStringPublicSaslIam | Client kết nối public qua IAM |
| BootstrapBrokerStringVpcConnectivityTls | Client dùng multi-VPC private connectivity với TLS |
| BootstrapBrokerStringVpcConnectivitySaslScram | Client dùng multi-VPC private connectivity với SCRAM |
| BootstrapBrokerStringVpcConnectivitySaslIam | Client dùng multi-VPC private connectivity với IAM |

Nếu cluster bật public access, dùng đúng field Public cho client ngoài VPC. Không dùng public bootstrap string cho workload nội bộ khi đã có endpoint private.

## 20. Port và network rule theo listener

Các port phổ biến của MSK Provisioned:

| Phương thức | Truy cập trong AWS | Public access |
|---|---:|---:|
| Plaintext | 9092 | Không nên dùng |
| TLS | 9094 | 9194 |
| SASL/SCRAM | 9096 | 9196 |
| SASL/IAM | 9098 | 9198 |

MSK có thêm port riêng cho IPv6. Nếu dùng dual-stack, lấy bootstrap string IPv6 tương ứng và đối chiếu port trong tài liệu port information.

Security group của broker cần cho phép inbound từ security group của client trên listener port đang dùng. Với IAM, ví dụ cho phép TCP 9098 từ client security group. Không mở toàn bộ port hoặc 0.0.0.0/0 chỉ để khắc phục timeout.

Client phải phân giải được broker DNS và kết nối được các broker mà cluster trả về sau bước bootstrap. Một TCP test tới bootstrap broker thành công chưa chứng minh mọi broker đều reachable. Kiểm tra route table, DNS, security group, network ACL, firewall trung gian và outbound rule của client.

## 21. Kết nối MSK Provisioned trong cùng VPC

Mặc định, MSK Provisioned cluster được truy cập private từ client nằm trong cùng VPC. Cấu hình tối thiểu:

1. Đặt EC2/ECS/EKS client trong VPC có route đến MSK broker.
2. Gắn security group cho client.
3. Trong security group broker, cho phép inbound TCP từ security group client trên port của auth listener.
4. Đảm bảo DNS resolution và network ACL không chặn luồng.
5. Lấy bootstrap broker string đúng phương thức xác thực.
6. Cấu hình client properties.
7. Kiểm tra get-caller-identity và thử Kafka operation trên topic được cấp quyền.

Ví dụ IAM listener: broker security group cho phép TCP 9098 từ client security group. Nếu dùng SCRAM, listener trong AWS thường là 9096; nếu dùng mTLS/TLS là 9094.

Không dùng một rule mở rộng cho tất cả workload. Có thể tách security group theo service, ví dụ sg-orders-producer và sg-orders-consumer, rồi cấp quyền inbound cụ thể.

## 22. Multi-VPC private connectivity và cross-account

Amazon MSK hỗ trợ multi-VPC private connectivity qua AWS PrivateLink để client ở VPC/account khác kết nối private đến cluster. Đây là lựa chọn hữu ích khi các VPC có CIDR overlap hoặc tổ chức muốn tránh quản lý peering và route phức tạp.

Đặc điểm cần nhớ:

- Hỗ trợ Kafka 2.7.1 trở lên.
- Hỗ trợ IAM, TLS/mTLS và SASL/SCRAM; không hỗ trợ unauthenticated access.
- Kết nối multi-VPC chỉ trong cùng AWS Region, không phải cross-Region.
- Không hỗ trợ kết nối multi-VPC tới ZooKeeper.
- Không hỗ trợ t3.small trong cấu hình multi-VPC.
- Client VPC cần số subnet tương ứng và Availability Zone ID phù hợp với cluster theo hướng dẫn dịch vụ.

Quy trình tổng quát:

1. Cluster owner bật multi-VPC connectivity cho authentication scheme đã chọn.
2. Cluster owner gắn cluster policy cho account/principal bên ngoài.
3. Account client tạo managed VPC connection và endpoint theo hướng dẫn.
4. Role của client có quyền tạo VPC connection và các EC2 endpoint resource cần thiết.
5. Lấy VPC connectivity bootstrap broker string.
6. Cấu hình client với auth scheme đã được cluster cho phép.

## 23. MSK cluster policy cho cross-account

Cluster policy là resource-based policy gắn với MSK cluster. Nó cho phép account khác thiết lập private connectivity; khi dùng IAM client authentication, cluster policy cũng có thể cấp Kafka data-plane permissions cho principal kết nối.

Ví dụ rút gọn cho Account B thiết lập kết nối tới cluster ở Account A:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "123456789012"
      },
      "Action": [
        "kafka:CreateVpcConnection",
        "kafka:GetBootstrapBrokers",
        "kafka:DescribeCluster",
        "kafka:DescribeClusterV2"
      ],
      "Resource": "arn:aws:kafka:ap-southeast-1:111122223333:cluster/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1"
    },
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "123456789012"
      },
      "Action": [
        "kafka-cluster:Connect"
      ],
      "Resource": "arn:aws:kafka:ap-southeast-1:111122223333:cluster/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1"
    },
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "123456789012"
      },
      "Action": [
        "kafka-cluster:DescribeTopic",
        "kafka-cluster:ReadData"
      ],
      "Resource": "arn:aws:kafka:ap-southeast-1:111122223333:topic/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1/orders"
    }
  ]
}
~~~

Đây chỉ là ví dụ minh họa; policy thực tế phải giới hạn account, role, topic và group cụ thể. Client account còn cần identity policy cho kafka:CreateVpcConnection, ec2:CreateTags, ec2:CreateVPCEndpoint và ec2:DescribeVpcAttribute theo hướng dẫn kết nối. Cluster policy có giới hạn kích thước; giữ policy gọn và quản lý version khi cập nhật.

## 24. MSK Serverless và IAM

MSK Serverless yêu cầu IAM access control cho mọi cluster. Serverless không hỗ trợ Apache Kafka ACL; authorization được thực hiện bằng IAM policy.

Điều này có một số hệ quả:

- Client Java có thể dùng AWS_MSK_IAM hoặc cơ chế IAM được tài liệu hóa.
- Client không dùng Java dùng SASL_OAUTHBEARER.
- Role cần quyền theo cluster, topic và group ARN.
- Một số action không áp dụng cho Serverless, ví dụ kafka-cluster:AlterCluster và các action dynamic cluster configuration.
- Không thể chuyển hướng dẫn SCRAM hoặc mTLS của Provisioned sang Serverless.

Lấy endpoint bằng phần View client information của cluster hoặc API phù hợp. Dùng bootstrap string do MSK trả về và policy action được đánh dấu hỗ trợ Serverless trong IAM action reference.

## 25. Bảo vệ credential, secret và certificate

Credential Kafka là đường vào dữ liệu streaming. Quản trị vòng đời của nó cần gắn với owner và ứng dụng.

Với IAM:

- Mỗi producer/consumer nên có role riêng theo service.
- Ưu tiên temporary credentials và workload identity.
- Không dùng IAM user access key dài hạn nếu có thể dùng role.
- Thu hồi quyền bằng policy/role và theo dõi thay đổi.
- Giới hạn topic, group và transactional ID.

Với SCRAM:

- Sinh password ngẫu nhiên đủ mạnh.
- Lưu trong Secrets Manager với customer managed KMS key.
- Tách user theo workload; tránh dùng chung một credential cho mọi ứng dụng.
- Rotate secret theo quy trình và kiểm tra thời gian MSK đồng bộ credential.
- Không log secret hoặc đặt password trên command line trong môi trường nhiều người dùng.

Với mTLS:

- Bảo vệ private key.
- Cấp certificate riêng theo workload hoặc trust boundary.
- Theo dõi expiration và tự động renew/reissue.
- Có runbook khi certificate bị lộ vì MSK không hỗ trợ CRL.
- Dùng Kafka ACL và security group để kiểm soát quyền và giới hạn kết nối.

## 26. Audit và vận hành bảo mật

Một hệ thống production cần có khả năng trả lời: principal nào kết nối, từ workload nào, vào cluster nào và có thể thực hiện thao tác gì.

Các kiểm soát nên có:

- CloudTrail để ghi nhận thao tác MSK API và một số thao tác quản trị Kafka. Tích hợp CloudTrail cho Amazon MSK yêu cầu cluster dùng IAM access control; sự kiện bao gồm các API MSK và một số hành động Kafka như tạo, sửa hoặc xóa topic.
- Với Standard và Express brokers, bật broker logs để phân tích giao tiếp giữa client và cluster; bật authorizer logs để ghi nhận quyết định authorization và hỗ trợ điều tra lỗi quyền. Có thể gửi log đến CloudWatch Logs, S3 hoặc Amazon Data Firehose.
- IAM Access Analyzer và policy review để phát hiện quyền chia sẻ ngoài dự kiến.
- AWS Config/Security Hub control để phát hiện cluster bật unauthenticated access hoặc cấu hình security chưa đạt.
- Inventory của cluster ARN, listener, port, auth scheme, owner và data classification.
- Quy trình duyệt thay đổi IAM policy, cluster policy, ACL, certificate và Secrets Manager resource policy.

Không bật log ở mức quá chi tiết mà không có retention và cost model. Đảm bảo log không chứa password, token hoặc dữ liệu nhạy cảm trong message payload.

## 27. Quy trình kết nối và kiểm thử end-to-end

Dùng một môi trường non-production và topic thử nghiệm để xác minh từng lớp.

~~~mermaid
flowchart TD
    A[Nhận cluster ARN và auth scheme] --> B[Lấy bootstrap broker]
    B --> C[Kiểm tra DNS, route và TCP port]
    C --> D[Xác minh IAM identity hoặc SCRAM/mTLS credential]
    D --> E[Kiểm tra policy / ACL]
    E --> F[Chạy Kafka CLI producer]
    F --> G[Chạy Kafka CLI consumer]
    G --> H[Kiểm tra offset, group và log]
~~~

### 27.1. Lấy bootstrap broker IAM

~~~bash
aws kafka get-bootstrap-brokers \
  --cluster-arn "$MSK_CLUSTER_ARN" \
  --query BootstrapBrokerStringSaslIam \
  --output text
~~~

Đặt kết quả vào biến MSK_BOOTSTRAP_SERVERS của client. Dùng IAM broker string tương ứng với môi trường private hoặc public đã chọn.

### 27.2. Kiểm tra network

Trên client, xác minh DNS của từng broker trong bootstrap string. Kiểm tra TCP đến port 9098 với IAM listener trong AWS. Công cụ như nc hoặc Test-NetConnection chỉ xác minh TCP reachability, không xác minh IAM policy hoặc Kafka authorization.

### 27.3. Dùng Kafka CLI

Với Kafka CLI đã có thư viện IAM plugin trong classpath và file client.properties đã cấu hình:

~~~bash
kafka-topics.sh --bootstrap-server "$MSK_BOOTSTRAP_SERVERS" --list --command-config client.properties
~~~

Tạo topic chỉ khi role có quyền và quy trình cho phép:

~~~bash
kafka-topics.sh --bootstrap-server "$MSK_BOOTSTRAP_SERVERS" --create --topic msk-auth-lab --partitions 3 --replication-factor 3 --command-config client.properties
~~~

Produce:

~~~bash
kafka-console-producer.sh --bootstrap-server "$MSK_BOOTSTRAP_SERVERS" --topic msk-auth-lab --producer.config client.properties
~~~

Consume:

~~~bash
kafka-console-consumer.sh --bootstrap-server "$MSK_BOOTSTRAP_SERVERS" --topic msk-auth-lab --from-beginning --consumer.config client.properties
~~~

Nếu policy không cấp CreateTopic, dùng topic được administrator tạo trước. Không mở quyền quản trị chỉ để chạy lab.

## 28. Troubleshooting theo triệu chứng

| Triệu chứng | Lớp cần kiểm tra | Hướng xử lý |
|---|---|---|
| DNS lookup thất bại | DNS/VPC | Kiểm tra private DNS, resolver, route và bootstrap string đúng cluster/Region |
| Connection timeout | Network | Kiểm tra SG inbound, outbound, NACL, route, firewall và listener port |
| Connection refused | Endpoint/port | Đối chiếu port với auth scheme và field bootstrap broker |
| TLS handshake failure | TLS | Kiểm tra listener, truststore, keystore, certificate chain, protocol và thời gian hệ thống |
| SaslAuthenticationException | Authentication | Kiểm tra IAM credentials, Region ký token, SASL mechanism, plugin/classpath hoặc SCRAM credential |
| TopicAuthorizationException | Topic authorization | Kiểm tra ARN topic, DescribeTopic, WriteData hoặc ReadData |
| GroupAuthorizationException | Consumer group | Kiểm tra DescribeGroup, AlterGroup và group ARN |
| ClusterAuthorizationException | Cluster authorization | Kiểm tra Connect và cluster ARN |
| Không lấy được bootstrap broker | Control plane | Kiểm tra kafka:GetBootstrapBrokers, kafka:DescribeCluster và cluster ARN |
| Consumer không đọc được dù đã Connect | Data plane/group | Kiểm tra topic read, group permissions, offset và subscription |
| Producer transaction không kết thúc | Kafka version/transaction | Kiểm tra Kafka version, transactional ID actions và giới hạn WriteTxnMarkers |

### 28.1. Phân biệt lỗi xác thực và lỗi authorization

- SaslAuthenticationException thường xảy ra khi broker không xác minh được credential hoặc cơ chế SASL.
- TopicAuthorizationException thường cho biết client đã xác thực nhưng bị từ chối quyền trên topic.
- GroupAuthorizationException thường liên quan đến group ARN hoặc quyền group.
- TimeoutException cần kiểm tra network và broker availability trước khi sửa policy.

Nếu vừa cập nhật IAM policy, chờ propagation và thử lại. AWS nêu rằng thay đổi IAM policy thường có hiệu lực trong vòng chưa đến một phút, nhưng điều kiện mạng có thể làm chậm hơn.

### 28.2. Lỗi do dùng nhầm listener

Một số lỗi phổ biến:

- Dùng port 9094 nhưng cấu hình SASL_SSL và IAM mechanism.
- Dùng BootstrapBrokerStringTls cho client SCRAM.
- Dùng public broker string từ client trong VPC dù muốn kết nối private.
- Dùng IAM bootstrap string nhưng thiếu aws-msk-iam-auth trong classpath.
- Dùng AWS_MSK_IAM với Python client thay vì cơ chế OAUTHBEARER.

Đối chiếu bootstrap field, port, security.protocol và sasl.mechanism như một bộ cấu hình thống nhất.

## 29. Case study: tách producer và consumer cho hệ thống đơn hàng

Một nền tảng thương mại điện tử có hai ứng dụng:

- checkout-service ghi sự kiện OrderCreated vào topic orders.
- fulfillment-service đọc topic orders bằng consumer group fulfillment-workers.

Thiết kế bảo mật:

1. Cả hai ứng dụng chạy trong ECS với task role riêng.
2. MSK Provisioned cluster bật IAM authentication và TLS.
3. Broker security group chỉ nhận traffic từ security group của ECS service trên port 9098.
4. Producer role chỉ có Connect, DescribeTopic và WriteData trên topic orders.
5. Consumer role chỉ có Connect, DescribeTopic, ReadData trên topic orders, và DescribeGroup/AlterGroup trên group fulfillment-workers.
6. Cluster ARN, topic ARN và group ARN được đưa vào policy qua IaC.
7. CloudTrail theo dõi thao tác control plane; broker logs và application metrics hỗ trợ điều tra.
8. Consumer xử lý message idempotently theo order ID để tránh duplicate side effect khi retry.

Khi nhóm fulfillment cần đọc thêm topic returns, họ đề xuất thay đổi policy có scope rõ ràng. Không cấp kafka-cluster:* chỉ để giải quyết nhanh lỗi authorization.

## 30. Checklist production readiness

### Cluster và network

- [ ] Cluster đã bật authentication phù hợp; không để unauthenticated listener ngoài môi trường thử nghiệm.
- [ ] Client-broker encryption được bật.
- [ ] Bootstrap broker string lấy từ MSK API/console và đúng auth scheme.
- [ ] Security group chỉ cho phép nguồn client đã xác định.
- [ ] DNS, route, NACL và firewall cho phép client đến tất cả broker cần thiết.
- [ ] Public access được tắt nếu workload chỉ cần private connectivity.

### IAM và authorization

- [ ] Workload dùng IAM role hoặc credential provider phù hợp.
- [ ] Producer và consumer dùng role tách biệt.
- [ ] Policy dùng kafka-cluster: cho data plane và kafka: cho control plane.
- [ ] ARN cluster/topic/group/transactional ID đã kiểm tra chính xác.
- [ ] Không cấp wildcard rộng nếu không có lý do.
- [ ] Transactional/idempotent producer đã kiểm tra Kafka version và quyền phụ thuộc.
- [ ] Cross-account policy và trust policy được review.

### SCRAM/mTLS nếu sử dụng

- [ ] SCRAM secret có prefix AmazonMSK_ và customer managed KMS key.
- [ ] Secret resource policy do MSK gắn được giữ đúng.
- [ ] SCRAM user có rotation và owner.
- [ ] mTLS certificate có expiration monitoring và quy trình reissue.
- [ ] Private key được bảo vệ.
- [ ] Kafka ACL đã được cấu hình đúng principal.
- [ ] Với mTLS, đã có runbook xử lý certificate bị lộ vì MSK không hỗ trợ CRL.

### Vận hành

- [ ] Có test producer/consumer trên môi trường non-production.
- [ ] Có alert cho authentication/authorization failures và connection errors.
- [ ] Có log retention và access control phù hợp.
- [ ] Có quy trình review IAM policy và cluster policy.
- [ ] Có kế hoạch xoay credential/certificate và xử lý incident.
- [ ] Client dùng nhiều broker bootstrap để hỗ trợ failover.
- [ ] Consumer group, offset, retry và dead-letter strategy được kiểm thử.

## 31. Bài tập tự kiểm tra

### Câu 1

IAM authentication của MSK giải quyết hai việc nào?

**Đáp án:** Xác thực IAM principal và kiểm tra quyền Kafka data-plane thông qua IAM policy.

### Câu 2

Sự khác nhau giữa kafka: và kafka-cluster: là gì?

**Đáp án:** kafka: kiểm soát API quản lý MSK như DescribeCluster/GetBootstrapBrokers; kafka-cluster: kiểm soát thao tác Kafka như Connect, ReadData và WriteData.

### Câu 3

Một producer chỉ cần ghi vào topic orders. Nên cấp kafka-cluster:* hay Connect, DescribeTopic, WriteData với ARN topic cụ thể?

**Đáp án:** Cấp các action cần thiết trên cluster/topic ARN cụ thể theo least privilege.

### Câu 4

Vì sao consumer cần quyền trên group ARN?

**Đáp án:** Consumer phải tham gia group và cập nhật offset/trạng thái group; các quyền này được kiểm soát bằng DescribeGroup và AlterGroup.

### Câu 5

Java client dùng IAM mechanism nào?

**Đáp án:** Có thể dùng custom AWS_MSK_IAM hoặc SASL_OAUTHBEARER; custom mechanism cần thư viện aws-msk-iam-auth.

### Câu 6

Client Python dùng IAM access control với cơ chế nào?

**Đáp án:** Dùng SASL/OAUTHBEARER và thư viện signer tạo MSK auth token theo AWS Region.

### Câu 7

Port 9098 thường dùng cho gì?

**Đáp án:** SASL/IAM listener cho client truy cập trong AWS. Public IAM listener dùng port 9198 khi public access được bật.

### Câu 8

Port 9096 và 9094 khác nhau thế nào?

**Đáp án:** 9096 là listener SASL/SCRAM; 9094 là listener TLS.

### Câu 9

SASL/SCRAM secret của MSK cần prefix nào và loại KMS key nào?

**Đáp án:** Tên secret bắt đầu bằng AmazonMSK_ và secret phải được mã hóa bằng customer managed KMS key; AWS managed default key của Secrets Manager không dùng được để associate.

### Câu 10

MSK Serverless có hỗ trợ Kafka ACL không?

**Đáp án:** Không. MSK Serverless yêu cầu IAM access control và không hỗ trợ Apache Kafka ACL.

### Câu 11

MSK có hỗ trợ CRL cho mTLS không?

**Đáp án:** Không. Cần dùng Kafka ACL, security group và quy trình thay/reissue certificate để xử lý certificate bị lộ.

### Câu 12

Nếu get-bootstrap-brokers thành công nhưng producer timeout, nên kiểm tra gì?

**Đáp án:** Kiểm tra DNS, route, security group, NACL, firewall và khả năng truy cập mọi broker qua đúng listener port. Lấy bootstrap string thành công chỉ chứng minh control-plane API trả endpoint.

### Câu 13

Nếu producer nhận TopicAuthorizationException, cần xem action nào?

**Đáp án:** Kiểm tra Connect, DescribeTopic, WriteData và ARN topic; cũng kiểm tra explicit Deny hoặc permission boundary/SCP.

### Câu 14

Tại sao không dùng public bootstrap string cho workload nội bộ?

**Đáp án:** Workload nội bộ nên dùng private endpoint và network path được kiểm soát; public listener làm tăng bề mặt truy cập và phụ thuộc cấu hình public access.

### Câu 15

MSK multi-VPC private connectivity có thể kết nối xuyên Region không?

**Đáp án:** Không. Multi-VPC private connectivity cho MSK áp dụng giữa VPC/account trong cùng Region.

### Câu 16

Với Kafka trước version 3.8, IAM có hỗ trợ WriteTxnMarkers để kết thúc transaction không?

**Đáp án:** Không. Tài liệu AWS nêu hỗ trợ API này cho Kafka 3.8 trở lên; version cũ cần đánh giá SCRAM hoặc mTLS với ACL nếu workload yêu cầu transaction termination.

## 32. Tài liệu tham khảo chính thức

- [IAM access control for Amazon MSK](https://docs.aws.amazon.com/msk/latest/developerguide/iam-access-control.html)
- [How IAM access control for Amazon MSK works](https://docs.aws.amazon.com/msk/latest/developerguide/how-to-use-iam-access-control.html)
- [Configure clients for IAM access control](https://docs.aws.amazon.com/msk/latest/developerguide/configure-clients-for-iam-access-control.html)
- [Create authorization policies for the IAM role](https://docs.aws.amazon.com/msk/latest/developerguide/create-iam-access-control-policies.html)
- [Common use cases for client authorization policy](https://docs.aws.amazon.com/msk/latest/developerguide/iam-access-control-use-cases.html)
- [Semantics of IAM authorization policy actions and resources](https://docs.aws.amazon.com/msk/latest/developerguide/kafka-actions.html)
- [Get the bootstrap brokers for an Amazon MSK cluster](https://docs.aws.amazon.com/msk/latest/developerguide/msk-get-bootstrap-brokers.html)
- [Get the bootstrap brokers using the AWS CLI](https://docs.aws.amazon.com/msk/latest/developerguide/get-bootstrap-cli.html)
- [Port information for Amazon MSK](https://docs.aws.amazon.com/msk/latest/developerguide/port-info.html)
- [Sign-in credentials authentication with AWS Secrets Manager](https://docs.aws.amazon.com/msk/latest/developerguide/msk-password.html)
- [Set up SASL/SCRAM authentication for an Amazon MSK cluster](https://docs.aws.amazon.com/msk/latest/developerguide/msk-password-tutorial.html)
- [Mutual TLS client authentication for Amazon MSK](https://docs.aws.amazon.com/msk/latest/developerguide/msk-authentication.html)
- [Set up a client to use authentication](https://docs.aws.amazon.com/msk/latest/developerguide/msk-authentication-client.html)
- [Apache Kafka ACLs in Amazon MSK](https://docs.aws.amazon.com/msk/latest/developerguide/msk-acls.html)
- [Amazon MSK encryption](https://docs.aws.amazon.com/msk/latest/developerguide/msk-encryption.html)
- [Amazon MSK logging and authorizer logs](https://docs.aws.amazon.com/msk/latest/developerguide/msk-logging.html)
- [Log Amazon MSK API calls and Kafka actions with CloudTrail](https://docs.aws.amazon.com/msk/latest/developerguide/logging-API-using-cloudtrail.html)
- [Connect to an Amazon MSK Provisioned cluster](https://docs.aws.amazon.com/msk/latest/developerguide/client-access.html)
- [Amazon MSK multi-VPC private connectivity](https://docs.aws.amazon.com/msk/latest/developerguide/aws-access-mult-vpc.html)
- [MSK Serverless](https://docs.aws.amazon.com/msk/latest/developerguide/serverless.html)
- [AWS MSK IAM authentication library releases](https://github.com/aws/aws-msk-iam-auth/releases)
- [AWS MSK IAM authentication library on Maven Central](https://central.sonatype.com/artifact/software.amazon.msk/aws-msk-iam-auth)

Các tính năng, port, phiên bản Kafka và thư viện client có thể thay đổi. Trước khi triển khai, đối chiếu tài liệu hiện hành, bootstrap broker string và IAM action reference của đúng loại cluster, Region và phiên bản Kafka.

