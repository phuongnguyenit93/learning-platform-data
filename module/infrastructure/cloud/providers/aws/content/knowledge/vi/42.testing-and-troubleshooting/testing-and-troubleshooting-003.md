# Giới hạn mô phỏng cục bộ và kiểm thử với dịch vụ thật

## Mục tiêu học tập

Khi phát triển ứng dụng trên AWS, lập trình viên thường muốn chạy và kiểm thử nhanh trên máy cá nhân trước khi triển khai. Mock, fake service, container và emulator giúp rút ngắn vòng phản hồi, kiểm tra business logic và mô phỏng một số API. Tuy nhiên, môi trường local không thể tái tạo đầy đủ cách AWS vận hành: IAM policy, resource policy, VPC routing, service quota, retry, event delivery, eventual consistency, failover và khả năng mở rộng của dịch vụ managed đều có thể khác.

Bài học thuộc chương **Kiểm thử và xử lý sự cố** của module CLOUD_PROVIDERS_AWS. Nội dung giúp người học phân biệt những gì có thể kiểm thử cục bộ với những gì cần kiểm thử trên AWS thật, lựa chọn mock/emulator phù hợp, xây dựng môi trường cloud test cô lập, tự động hóa kiểm thử và điều tra lỗi phát sinh khi chuyển từ local sang AWS.

Sau bài học, người học có thể:

- Phân biệt unit test, component test, integration test, end-to-end test, performance test và resilience test.
- Chọn mock, stub, fake, AWS Emulator, DynamoDB Local hoặc AWS SAM CLI theo mục tiêu.
- Nhận diện giới hạn về IAM, account/Region, network, quota, timing, performance và managed-service behavior.
- Thiết kế test trên AWS thật bằng account hoặc stack cô lập.
- Kiểm tra IAM role, resource policy, KMS, VPC, security group và endpoint policy.
- Kiểm thử event-driven workflow có retry, duplicate, DLQ và eventual consistency.
- Dùng cfn-lint và CloudFormation Guard để kiểm tra Infrastructure as Code.
- Tự động triển khai, kiểm thử và dọn dẹp môi trường tạm trong CI/CD.
- Thiết kế load test và fault-injection experiment có guardrail.
- Điều tra lỗi chỉ xuất hiện trên AWS bằng request ID, CloudTrail, CloudWatch và service logs.

## 1. Vì sao cần phân biệt local simulation và AWS thật?

Một bài test local có thể xác nhận rằng code gọi đúng hàm SDK và tạo đúng tham số. Nhưng điều đó chưa chứng minh AWS sẽ chấp nhận request hoặc dịch vụ sẽ hành xử đúng như ứng dụng kỳ vọng.

Ví dụ:

- Mock SQS trả về MessageId thành công, nhưng IAM role thật của Lambda thiếu quyền sqs:SendMessage.
- Emulator cho phép ứng dụng tạo S3 bucket, nhưng bucket policy, KMS key policy hoặc organization SCP trên AWS từ chối thao tác.
- Lambda chạy tốt trong Docker, nhưng khi triển khai thật không đọc được secret vì execution role thiếu secretsmanager:GetSecretValue.
- Local queue xử lý message gần như tức thời, trong khi SQS thật có visibility timeout, retry, redrive policy và duplicate delivery.
- Một test dùng một request chạy nhanh trên máy cá nhân, nhưng production endpoint bị throttling khi có hàng nghìn request đồng thời.
- Một function nhận event mẫu hợp lệ, nhưng event thật từ dịch vụ AWS có cấu trúc, header hoặc metadata khác.

Mục tiêu không phải bỏ local testing. Cần dùng local test cho những câu hỏi mà nó trả lời tốt, sau đó kiểm chứng trên AWS thật các thuộc tính phụ thuộc vào dịch vụ, cấu hình và hạ tầng.

## 2. Các tầng kiểm thử trong hệ thống AWS

| Tầng kiểm thử | Phạm vi | Môi trường thường dùng | Câu hỏi chính |
|---|---|---|---|
| Static validation | Cấu trúc code, template, policy, schema | Local/CI | Cấu hình có hợp lệ về cú pháp và quy tắc không? |
| Unit test | Hàm hoặc class riêng lẻ | Local | Business logic có đúng không? |
| Component test | Một component cùng dependency được thay thế | Local/container | Component xử lý input, output và lỗi đúng không? |
| Local integration test | Nhiều component qua emulator hoặc container | Local/CI | Các thành phần có giao tiếp theo hợp đồng đã mô phỏng không? |
| Cloud integration test | Tương tác với AWS service thật | AWS test account | IAM, network, API và service behavior có đúng không? |
| End-to-end test | Toàn bộ luồng nghiệp vụ | AWS test/staging | Event có đi qua mọi service và tạo kết quả đúng không? |
| Performance/load test | Throughput, latency, concurrency, saturation | AWS test environment | Hệ thống chịu được tải mục tiêu không? |
| Resilience test | Failover, dependency failure, recovery | Pre-production/AWS FIS | Hệ thống phục hồi trong RTO/RPO không? |

Mỗi tầng có mục tiêu và chi phí khác nhau. Static và unit test nên chạy thường xuyên vì nhanh. Cloud integration test chạy sau khi hạ tầng được tạo hoặc thay đổi. Performance và fault injection cần môi trường riêng, lịch chạy và guardrail rõ ràng.

~~~mermaid
flowchart TD
    A[Code and IaC change] --> B[Static validation]
    B --> C[Unit tests]
    C --> D[Local component / emulator tests]
    D --> E[Deploy isolated AWS test stack]
    E --> F[Cloud integration tests]
    F --> G[End-to-end tests]
    G --> H[Performance and resilience tests]
    H --> I[Promote to staging / production]
    B -->|Fail| X[Fix before deployment]
    C -->|Fail| X
    D -->|Fail| X
    F -->|Fail| X
    G -->|Fail| X
~~~

## 3. Mock, stub, fake và emulator khác nhau thế nào?

Các khái niệm này thường bị gọi chung là mock nhưng có mục đích khác nhau.

| Loại | Cách hoạt động | Ví dụ | Giá trị kiểm thử |
|---|---|---|---|
| Stub | Trả về response đã định trước | SQS client trả MessageId giả | Kiểm tra code xử lý một response |
| Mock | Ghi nhận interaction để xác minh lời gọi | Xác minh code gọi SendMessage đúng QueueUrl | Kiểm tra dependency được dùng đúng |
| Fake | Cài đặt đơn giản một phần hành vi thật | In-memory repository thay database | Kiểm tra luồng nghiệp vụ với state đơn giản |
| Emulator | Chạy service giả lập API/state của dịch vụ | AWS Emulator hoặc LocalStack | Kiểm tra tích hợp qua API được hỗ trợ |
| Real service | Gọi dịch vụ AWS thật | SQS, S3, DynamoDB trong test account | Kiểm tra behavior và cấu hình thực tế |

Mock quá sâu có thể khiến test chỉ xác nhận implementation hiện tại. Nếu code thay đổi cách gọi dependency nhưng business behavior vẫn đúng, test có thể fail không cần thiết. Ngược lại, mock quá đơn giản có thể không mô phỏng lỗi, retry hoặc state transition quan trọng.

Hãy mock ở ranh giới external dependency và giữ business logic độc lập với SDK. Dùng cloud integration test để kiểm tra những hợp đồng mà mock không thể chứng minh.

## 4. Unit test business logic và kiểm tra lời gọi SDK

Ví dụ một component gửi sự kiện đơn hàng vào SQS. Business logic tạo message body; SQS client chỉ là adapter.

~~~python
import json

def publish_order(queue_client, queue_url, order):
    message = {
        "eventType": "OrderCreated",
        "orderId": order["order_id"],
        "amount": order["amount"]
    }

    return queue_client.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(message)
    )
~~~

Có thể dùng mock để xác minh message và tham số:

~~~python
from unittest.mock import Mock
import json

def test_publish_order_sends_expected_message():
    queue = Mock()
    queue.send_message.return_value = {"MessageId": "test-message-1"}

    result = publish_order(
        queue,
        "https://sqs.example.test/orders",
        {"order_id": "ORD-1001", "amount": 250000}
    )

    assert result["MessageId"] == "test-message-1"
    queue.send_message.assert_called_once()

    args = queue.send_message.call_args.kwargs
    assert args["QueueUrl"] == "https://sqs.example.test/orders"

    body = json.loads(args["MessageBody"])
    assert body["eventType"] == "OrderCreated"
    assert body["orderId"] == "ORD-1001"
~~~

Test này chứng minh code tạo đúng message và gọi dependency với đúng URL. Nó không chứng minh queue tồn tại, role có quyền gửi, KMS key policy đúng hoặc SQS thực sự nhận message.

## 5. Stub AWS SDK với Botocore Stubber

Với Python/Boto3, Botocore Stubber có thể kiểm tra API operation và expected parameters. Nó hữu ích hơn một mock chung khi cần phát hiện code truyền sai tên field hoặc kiểu dữ liệu.

~~~python
import boto3
from botocore.stub import Stubber

sqs = boto3.client(
    "sqs",
    region_name="ap-southeast-1",
    aws_access_key_id="test",
    aws_secret_access_key="test"
)

queue_url = "https://sqs.ap-southeast-1.amazonaws.com/123456789012/orders"

expected_params = {
    "QueueUrl": queue_url,
    "MessageBody": "{\"eventType\": \"OrderCreated\"}"
}

response = {
    "MD5OfMessageBody": "00000000000000000000000000000000",
    "MessageId": "message-test-001"
}

with Stubber(sqs) as stubber:
    stubber.add_response(
        "send_message",
        response,
        expected_params
    )

    result = sqs.send_message(**expected_params)

    assert result["MessageId"] == "message-test-001"
    stubber.assert_no_pending_responses()
~~~

Stubber xác minh request khớp contract của SDK và trả response giả lập. Nó không gọi SQS, không kiểm tra IAM, queue policy, KMS hoặc network. Khi cần xác minh các điều kiện đó, chạy integration test với queue thật trong account test.

## 6. AWS Emulator: kiểm thử API cục bộ

AWS Emulator là emulator API AWS do AWS công bố, có thể chạy trên máy phát triển hoặc CI. AWS CLI và AWS SDK có thể trỏ tới endpoint emulator; request được xử lý bởi emulator thay vì AWS account thật. Dịch vụ hỗ trợ stateful resource trong phiên chạy và công bố fidelity checks theo từng release.

AWS Emulator phù hợp để:

- Phát triển và kiểm thử API integration cục bộ.
- Chạy test CI mà không cần AWS account hoặc resource AWS.
- Tạo resource, đọc lại state và kiểm tra một số validation error.
- Prototyping ứng dụng dùng AWS API trước khi deploy.

Các giới hạn phải nhớ:

- Emulator không đánh giá IAM identity policy và resource-based policy giống AWS; không dùng nó làm bằng chứng security test.
- Emulator không cô lập state theo AWS account và Region. Một instance emulator cần được dùng như một môi trường account/Region thống nhất.
- Fidelity khác nhau theo service và API operation. AWS công bố emulator khớp AWS rõ nhất ở control-plane API; data-plane fidelity và hỗ trợ IaC thay đổi theo dịch vụ. API chưa được triển khai có thể trả HTTP 501 NotImplemented. Phải xem bảng fidelity của release đang dùng.
- AWS công bố kiểm tra behavior đối chiếu với AWS tại us-west-2, ngoại trừ global services được kiểm tra tại us-east-1. Khác biệt về feature availability theo Region có thể không được phản ánh.
- Resource state lưu trong memory và mất khi emulator dừng.
- Emulator không được thiết kế hoặc kiểm thử cho workload dài hạn và load test.

Vì emulator được cập nhật thường xuyên, hãy pin version trong CI và ghi nhận version trong test report. Khi nâng version, chạy lại bộ contract test và kiểm tra fidelity cho những API mà ứng dụng sử dụng.

## 7. LocalStack và các emulator bên thứ ba

LocalStack là một lựa chọn phổ biến để mô phỏng nhiều AWS service trong cùng môi trường local. Có thể dùng nó để kiểm thử luồng nhiều service như S3 → SQS → Lambda hoặc API Gateway → Lambda → DynamoDB.

Emulator bên thứ ba có thể cung cấp API coverage và trải nghiệm tiện lợi, nhưng behavior không nhất thiết giống AWS trên mọi feature. Trước khi dùng, kiểm tra:

- Service và API operation nào được hỗ trợ.
- Feature nào chỉ được mô phỏng một phần.
- IAM và resource policy được thực thi ở mức nào.
- Sự kiện, retry, visibility timeout và eventual consistency có tương đương không.
- Có hỗ trợ VPC, PrivateLink, KMS, STS và cross-account không.
- Version và licensing có phù hợp CI/team không.

Không suy luận rằng emulator hỗ trợ S3 API thì đã mô phỏng được mọi behavior của S3, ví dụ event notification, lifecycle, replication, object lock, KMS hoặc cross-account access.

## 8. DynamoDB Local: hữu ích nhưng không thay thế DynamoDB managed service

DynamoDB Local cho phép phát triển ứng dụng mà không gọi DynamoDB web service. Có thể chạy bằng Docker, Maven hoặc bản tải xuống. Endpoint mặc định là localhost:8000.

Ví dụ chạy Docker:

~~~bash
docker run --rm -p 8000:8000 amazon/dynamodb-local \
  -jar DynamoDBLocal.jar -sharedDb -inMemory
~~~

Gọi CLI với endpoint local:

~~~bash
aws dynamodb list-tables \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1
~~~

DynamoDB Local phù hợp để kiểm tra repository, key condition, query expression, serialization và luồng đọc/ghi cơ bản. Tuy nhiên, behavior khác DynamoDB managed service ở các điểm quan trọng:

- Không hỗ trợ tách AWS account và Region như dịch vụ thật.
- Provisioned throughput setting bị bỏ qua; không thể dùng local để kiểm tra throttling hoặc capacity behavior.
- Scan chạy tuần tự; Parallel Scan và Segment/TotalSegments không có behavior như dịch vụ thật.
- CreateTable/UpdateTable/DeleteTable thường hoàn tất gần như tức thời và table có thể luôn ở trạng thái ACTIVE; không mô phỏng đầy đủ timing của control plane.
- Read thường xuất hiện như strongly consistent do tốc độ local, dù DynamoDB Local mô tả read behavior là eventually consistent.
- Không hỗ trợ Point-in-Time Recovery.
- Behavior của Streams shard và partitioning khác dịch vụ managed.
- Hiệu năng phụ thuộc máy tính cá nhân, không dự báo được latency, throughput hay durability trên AWS.

Nếu ứng dụng phụ thuộc GSI creation state, throttling, Streams, PITR, TTL hoặc transaction behavior, hãy kiểm thử phần liên quan trên DynamoDB thật. Dùng local để kiểm tra query logic, không dùng kết quả local làm bằng chứng capacity hoặc resilience.

## 9. AWS SAM CLI: chạy Lambda và API Gateway cục bộ

AWS SAM CLI có thể chạy Lambda function trong Docker container với runtime gần môi trường Lambda. SAM local hữu ích để:

- Kiểm tra handler và event parsing.
- Debug function trong IDE.
- Gửi mẫu event API Gateway, SQS, S3 hoặc EventBridge.
- Chạy API local cho frontend hoặc component test.
- Giảm thời gian deploy trong vòng lặp phát triển.

Các lệnh cơ bản:

~~~bash
sam build
sam local invoke OrderFunction --event events/order-created.json
sam local start-api
~~~

Một giới hạn quan trọng: nếu Lambda function gọi AWS SDK, request có thể đi đến AWS resource thật trừ khi endpoint được cấu hình để trỏ tới emulator hoặc dependency giả lập. Vì vậy, SAM local không tự động biến S3, SQS, DynamoDB hoặc Secrets Manager thành service local.

Trước khi chạy local test, xác định credential và endpoint mà code sử dụng. Không để một test local vô tình xóa object hoặc gửi message vào account production. Dùng profile riêng, endpoint rõ ràng và resource có prefix test.

## 10. Local simulation không kiểm chứng được IAM và resource policy

IAM là một trong những khác biệt quan trọng nhất giữa local và AWS thật.

Một test local có thể chạy với developer credential quyền Administrator. Nhưng khi deploy, Lambda chạy bằng execution role khác. Những vấn đề thường chỉ xuất hiện trên AWS:

- Trust policy không cho phép Lambda hoặc ECS assume role.
- Identity policy thiếu action.
- Resource policy của S3, SQS, SNS, KMS hoặc Secrets Manager từ chối.
- Explicit Deny trong SCP, permissions boundary hoặc session policy.
- KMS key policy không cho phép service principal hoặc role.
- Cross-account trust không đúng.
- VPC endpoint policy chặn API request.
- Role session hoặc credential source khác với giả định của ứng dụng.

Để kiểm tra security, triển khai test workload với đúng IAM role, resource policy và service integration như production. Dùng IAM Access Analyzer, CloudTrail và response error để xác minh quyền thực tế. Không dựa vào emulator hoặc mock để tuyên bố least privilege đã được kiểm chứng.

## 11. Local simulation không tái tạo đầy đủ VPC và network

Network behavior phụ thuộc nhiều resource mà emulator không thể đại diện đầy đủ:

- VPC, subnet và route table.
- Security group stateful rules.
- Network ACL stateless rules.
- NAT Gateway, Internet Gateway và egress path.
- VPC endpoints và endpoint policies.
- PrivateLink, Transit Gateway, peering và DNS resolution.
- Route 53 private hosted zone và resolver rules.
- TLS certificate, hostname verification và proxy.
- Cross-AZ hoặc cross-Region network behavior.

Một container local gọi được endpoint không chứng minh Lambda đặt trong private subnet có thể gọi API đó. Cần chạy test từ đúng network boundary: EC2 test instance, Lambda test function, ECS task hoặc EKS pod trong VPC tương ứng.

Khi test connectivity, ghi lại source subnet/security group, destination hostname, resolved IP, port, route và endpoint policy. Kiểm tra từng hop thay vì chỉ quan sát một lỗi timeout ở ứng dụng.

## 12. API contract và schema compatibility

Contract test xác minh hai phía của integration thống nhất về input, output và error behavior. Nó hữu ích ngay cả khi chưa có AWS resource thật.

Ví dụ, event OrderCreated cần có schema version, order ID, amount và event timestamp. Consumer phải xác định behavior khi thiếu field hoặc gặp version mới.

Một contract tốt xác định:

- Required và optional fields.
- Data type, format, enum và bounds.
- Schema version và compatibility policy.
- Idempotency key hoặc event ID.
- Error response và retryability.
- Content type và encoding.
- Event source và metadata.
- PII/secret fields không được log.

Contract test có thể chạy local. Nhưng cần thêm cloud integration test để xác nhận event thực tế từ AWS service có đúng shape và metadata mà consumer mong đợi.

## 13. Kiểm tra Infrastructure as Code trước khi deploy

CloudFormation template, SAM template hoặc cấu hình IaC có thể được kiểm tra tĩnh trước khi tạo resource.

Hai công cụ hữu ích:

- cfn-lint kiểm tra cấu trúc template, resource property, value, reference và một số best-practice rules theo CloudFormation resource schema.
- CloudFormation Guard kiểm tra JSON/YAML theo policy-as-code, ví dụ bucket phải mã hóa hoặc security group không được mở SSH ra internet.

Ví dụ:

~~~bash
cfn-lint --regions ap-southeast-1 template.yaml
~~~

~~~bash
cfn-guard validate \
  --rules security-rules.guard \
  --data template.yaml \
  --type CFNTemplate
~~~

cfn-lint không chứng minh CloudFormation stack sẽ tạo thành công trong account cụ thể. Guard cũng không tự thực thi enforcement phía server; để chặn thay đổi ở thời điểm provisioning, xem CloudFormation Hooks hoặc governance control phù hợp.

Static validation không thay thế deployment test. Resource quota, service-linked role, account setting, Region availability, IAM permission và dependency state chỉ được xác nhận đầy đủ khi làm việc với AWS.

## 14. Khi nào cần kiểm thử với AWS service thật?

Hãy kiểm thử trên AWS thật khi kết quả phụ thuộc vào:

| Thuộc tính cần xác minh | Vì sao cần AWS thật |
|---|---|
| IAM và resource policy | Cần evaluation của AWS authorization engine |
| KMS | Cần key policy, grants và service integration thực |
| VPC và PrivateLink | Cần route, SG, NACL, DNS và endpoint thực |
| Service quota/throttling | Quota và throttling thực thi ở account/Region |
| Managed service timing | Provisioning, failover, retry và state transition có thời gian thực |
| Event delivery | Cần xác minh integration, retry, duplicate và DLQ |
| Performance | Cần compute, storage, network và capacity thật |
| Regional feature availability | Feature và quota có thể khác theo Region |
| Backup/restore | Cần kiểm tra snapshot, restore và data durability workflow |
| Failover/resilience | Cần mô phỏng resource failure và quan sát recovery thật |

Không cần deploy toàn bộ production stack cho mọi commit. Có thể chia test cloud thành smoke test nhỏ sau mỗi deploy, integration suite theo lịch hoặc trước release, và performance/resilience test theo kế hoạch riêng.

## 15. Thiết kế AWS test account và môi trường cô lập

Môi trường test nên có boundary rõ ràng để test không chạm dữ liệu hoặc resource production.

Các lựa chọn thường gặp:

- AWS account riêng cho từng developer.
- Account dùng chung cho team nhưng mỗi test có stack name và resource prefix riêng.
- AWS Organizations account riêng cho dev/test/staging.
- Ephemeral account được tạo theo pipeline hoặc landing zone khi tổ chức hỗ trợ.

Nguyên tắc:

1. Tách production account khỏi dev/test.
2. Dùng IAM role giới hạn theo workload và environment.
3. Dùng resource tag để nhận diện owner, environment, build ID và expiry.
4. Không copy PII hoặc secret production sang test nếu không có phê duyệt và masking.
5. Dùng S3 bucket, queue, topic, table và secret riêng cho test.
6. Cấu hình budget alert và service quota phù hợp.
7. Dùng IaC để tạo và hủy môi trường có thể lặp lại.
8. Không dùng resource name chung dễ xung đột giữa parallel test run.

Nếu team dùng account chung, hãy tạo unique suffix từ pipeline run ID và xóa đúng stack tương ứng sau test. Không dùng wildcard cleanup có thể xóa resource của người khác.

## 16. Test data: dữ liệu giả lập và dữ liệu đã ẩn danh

Test data ảnh hưởng trực tiếp tới độ tin cậy của kết quả và rủi ro bảo mật.

Các loại dữ liệu nên cân nhắc:

- Synthetic data tạo theo schema và phân bố dự kiến.
- Masked data đã loại bỏ hoặc biến đổi định danh.
- Fixture nhỏ cho unit/component test.
- Dataset đại diện đã được phê duyệt cho performance test.
- Edge-case data như null, Unicode, payload lớn, duplicate ID, out-of-order event và malformed JSON.

Một bộ test data tốt phải bao phủ happy path, boundary, invalid input và retry. Dữ liệu synthetic cần phản ánh độ dài chuỗi, cardinality, skew, size và distribution gần thực tế; một dataset quá đồng đều có thể che giấu hot partition hoặc query bottleneck.

Không ghi dữ liệu thật vào test report, CloudWatch logs hoặc artifact CI nếu chưa có kiểm soát truy cập và retention.

## 17. Kiểm thử service integration theo từng lớp

Một integration test nên xác minh cả resource, permission và data flow.

Ví dụ luồng đơn hàng:

1. API Gateway nhận request.
2. Lambda validate và ghi order vào DynamoDB.
3. Lambda gửi OrderCreated event tới EventBridge.
4. Rule chuyển event sang SQS.
5. Consumer Lambda xử lý và ghi trạng thái fulfillment.
6. CloudWatch ghi log và metrics.

Test chỉ gọi Lambda handler trực tiếp không chứng minh API Gateway mapping, EventBridge rule, queue policy, DLQ và Lambda event source mapping hoạt động.

Nên có ít nhất một test end-to-end chạy trên AWS thật để tạo một order test, đợi trạng thái downstream và xác minh record/event. Dùng unique order ID để tránh va chạm và có cleanup policy riêng.

~~~mermaid
sequenceDiagram
    participant T as Test runner
    participant A as API Gateway
    participant L as Order Lambda
    participant D as DynamoDB
    participant E as EventBridge
    participant Q as SQS
    participant C as Consumer Lambda
    T->>A: POST test order
    A->>L: Invoke handler
    L->>D: PutItem
    L->>E: PutEvents
    E->>Q: Deliver event
    Q->>C: Event source mapping
    C->>D: Update fulfillment state
    T->>D: Poll for expected state
    D-->>T: Fulfillment status
~~~

## 18. Kiểm thử event-driven behavior: retry, duplicate và DLQ

Event-driven system thường bất đồng bộ. Một API trả HTTP 202 hoặc Lambda invocation thành công không chứng minh downstream đã hoàn tất.

Các kịch bản cần kiểm tra:

- Event đến một lần và consumer xử lý thành công.
- Event bị gửi lặp.
- Consumer xử lý thành công nhưng crash trước khi ack/delete message.
- Handler lỗi tạm thời và được retry.
- Message vượt maxReceiveCount và đi vào DLQ.
- Message hết visibility timeout trong lúc đang xử lý.
- Event đến sai thứ tự.
- Event thiếu field hoặc schema version mới.
- Downstream service throttling hoặc timeout.
- Event bridge rule/target bị disabled hoặc thiếu permission.

Consumer nên idempotent. Có thể lưu event ID hoặc business key cùng trạng thái xử lý trong transaction/conditional write để duplicate không tạo side effect hai lần.

Đối với SQS, test visibility timeout, message retention, redrive policy và DLQ bằng queue thật. Với Lambda, kiểm tra retry semantics theo loại event source; behavior của asynchronous invocation khác event source mapping của SQS/Kinesis.

## 19. Eventual consistency và timing trong cloud test

Một số thao tác AWS không hoàn tất ngay lập tức. Ví dụ:

- CloudFormation stack chuyển qua nhiều trạng thái.
- Lambda version/alias hoặc event source mapping cần thời gian cập nhật.
- IAM policy propagation có thể có độ trễ.
- S3 event notification và EventBridge delivery là bất đồng bộ.
- DynamoDB GSI hoặc stream resource có trạng thái tạo/xóa.
- ECS task, EKS workload hoặc EC2 instance cần thời gian khởi động.
- DNS cache và service discovery có thể giữ kết quả cũ.

Test không nên dùng sleep cố định dài cho mọi trường hợp. Dùng polling có timeout và backoff:

~~~python
import time

def wait_until(check, timeout_seconds=120, interval_seconds=2):
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(interval_seconds)

    raise TimeoutError("Condition was not met before timeout")
~~~

Hàm check cần thực hiện read-only operation và trả kết quả khi điều kiện mong muốn đã đạt. Timeout nên phản ánh SLO hoặc thời gian provisioning dự kiến. Khi timeout, ghi lại trạng thái cuối, request ID và resource ARN để điều tra.

## 20. Kiểm thử S3, DynamoDB và RDS

| Dịch vụ | Local test có thể xác minh | Cloud test cần xác minh |
|---|---|---|
| S3 | SDK parameters, object serialization, basic put/get qua emulator | Bucket policy, KMS, versioning, lifecycle, event notification, replication, Object Lock, access point |
| DynamoDB | Key design, query expression, marshalling, basic CRUD với local DB | Throughput, throttling, GSI/LSI timing, Streams, TTL, PITR, transactions và hot partition |
| RDS/Aurora | SQL logic với database container tương thích engine | IAM DB auth, subnet group, SG, failover, parameter group, backup/restore và managed maintenance |

Local database container có thể kiểm tra SQL và repository logic, nhưng không đại diện cho RDS failover, Multi-AZ, storage performance hoặc backup restoration.

Với S3, kiểm tra cả bucket policy và KMS key policy khi object mã hóa bằng customer managed key. Với DynamoDB, test conditional write, transaction conflict, throttling và hot partition trên account test có traffic đại diện.

## 21. Kiểm thử Lambda, API Gateway và Step Functions

Lambda local test hữu ích cho handler logic và event parsing. Cloud test cần kiểm tra:

- Execution role và trust relationship.
- Timeout, memory, ephemeral storage và concurrency.
- Environment variables và Secrets Manager integration.
- VPC attachment, subnet IP capacity và NAT/endpoint path.
- Event source mapping, batch size và partial batch response.
- Async retry, destination hoặc DLQ.
- API Gateway authorizer, throttling, mapping template và CORS.
- Step Functions state transition, retry/catch, timeout và service integration.

Với Step Functions, test một state machine local hoặc mocked service integration có thể kiểm tra branch logic. End-to-end test trên AWS cần xác minh IAM role, service integration, payload path và execution status thực tế.

Không dùng cùng một Lambda function production để test event gây side effect. Tạo function/alias test hoặc stack riêng và dùng test data riêng.

## 22. Kiểm thử IAM và bảo mật trên AWS

Security test phải chạy dưới principal và resource policy thật. Một bộ test nên có:

- Positive test: principal hợp lệ thực hiện được action cần thiết.
- Negative test: principal không hợp lệ bị từ chối.
- Resource scope test: role chỉ truy cập đúng bucket/table/queue/secret.
- Cross-account test: trust và resource policy cho phép đúng account/role.
- KMS test: encryption/decryption được phép hoặc bị từ chối đúng.
- VPC endpoint test: request đi qua endpoint và policy đúng.
- Audit test: CloudTrail ghi nhận API calls cần theo dõi.

Ví dụ test negative: application role có quyền đọc prefix test/orders/* nhưng không được đọc test/payroll/*. Gọi hai resource thật trong account test để xác minh allow và deny.

Không dùng quyền Administrator trong integration test vì nó che giấu lỗi least privilege. Test nên assume đúng application role bằng STS hoặc chạy workload bằng execution role thực tế.

## 23. Kiểm thử quota, throttling và retry

Service quota là một phần của contract vận hành. Local emulator không thể dự báo quota của account/Region.

Kiểm thử cần xem xét:

- API request rate và burst quota.
- Lambda concurrency và reserved concurrency.
- SQS throughput và message size.
- Kinesis shard capacity hoặc on-demand capacity.
- DynamoDB read/write capacity và hot partition.
- API Gateway throttling.
- SageMaker endpoint invocation concurrency.
- RDS connection limit và connection pool.
- Bedrock model quota/token throughput.

Không cố tình gây throttling trên production để kiểm tra. Dùng test account, quota phù hợp và workload giới hạn. Khi nhận throttling, client nên exponential backoff với jitter và giới hạn tổng retry. Retry vô hạn có thể làm sự cố quá tải nặng hơn.

## 24. Performance test và load test

Performance test đo thời gian xử lý và tài nguyên ở một mức tải xác định. Load test tăng tải để xem hệ thống hoạt động dưới expected peak. Stress test vượt tải mục tiêu để tìm giới hạn. Soak test giữ tải trong thời gian dài để phát hiện leak, backlog hoặc suy giảm dần.

Các chỉ số cần theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| p50/p95/p99 latency | Độ trễ trung vị và tail latency |
| Throughput | Số request/transaction hoàn tất mỗi giây |
| Error rate | Tỷ lệ request thất bại |
| Throttles/rejections | Request bị từ chối do quota/capacity |
| Queue depth/age | Backlog và thời gian chờ |
| CPU/memory/network | Tài nguyên compute |
| Database connections/latency | Tải và phản hồi database |
| Cost per request/job | Chi phí theo workload |

Load test phải dùng payload và phân bố dữ liệu gần thực tế. Chạy từ vị trí network phù hợp với client production. Nếu ứng dụng production chạy trong VPC, test từ VPC tương ứng để đo network path đúng.

Không dùng emulator local làm bằng chứng performance của AWS. CPU, disk, network và service scaling trên máy phát triển không đại diện cho managed service.

## 25. Kiểm thử resilience và chaos engineering với AWS FIS

AWS Fault Injection Service (AWS FIS) cho phép chạy fault-injection experiment trên resource AWS thật. Có thể dùng để kiểm tra ứng dụng khi xảy ra disruption được dịch vụ hỗ trợ, ví dụ instance bị dừng, CPU/memory stress, API throttling hoặc failover.

Một experiment template gồm:

- **Actions:** hành động gây lỗi hoặc thay đổi trạng thái.
- **Targets:** resource sẽ chịu tác động, có thể chọn theo tag hoặc điều kiện.
- **Stop conditions:** CloudWatch alarm tự dừng experiment khi vượt ngưỡng.
- **Role:** IAM role cho phép FIS thực hiện action trên resource.
- **Experiment report:** trạng thái, action đã chạy và kết quả.

AWS FIS thực hiện hành động thật trên resource thật. Bắt đầu ở test/pre-production, xác định steady state, lập hypothesis, chọn target nhỏ và có stop condition trước khi chạy. Không chạy fault injection trên production chỉ vì đã tạo được experiment template.

Ví dụ hypothesis:

"Nếu một EC2 instance trong Auto Scaling group bị dừng, số request lỗi không vượt 1% và service phục hồi trong 3 phút."

Đo baseline trước experiment, chạy action trên một target, theo dõi CloudWatch metrics và xác minh hệ thống đạt RTO. Nếu stop alarm kích hoạt, dừng experiment và xử lý trước khi thử lại.

## 26. Kiểm thử backup, restore và disaster recovery

Có snapshot hoặc backup thành công không đồng nghĩa ứng dụng có thể khôi phục đúng hạn.

Một bài test restore cần xác minh:

1. Backup/snapshot được tạo theo lịch.
2. Retention và encryption key còn khả dụng.
3. Có quyền restore trong account/Region mục tiêu.
4. Resource mới có thể được tạo từ backup.
5. Application có thể kết nối tới resource đã restore.
6. Dữ liệu và consistency được kiểm tra.
7. DNS/endpoint/secret/config được chuyển sang resource mới.
8. RTO và RPO thực tế được đo.
9. Runbook có thể được thực hiện bởi người trực khác.

Với RDS, test restore snapshot và kết nối application. Với DynamoDB, kiểm tra PITR hoặc on-demand backup restore. Với S3, kiểm tra versioning, replication và object recovery. Với EBS/EC2, kiểm tra snapshot restore và boot. Với multi-Region architecture, kiểm tra cả quyền, KMS, network và service quota ở Region đích.

## 27. Tự động hóa cloud test bằng Infrastructure as Code

Môi trường cloud test nên được tạo từ template versioned thay vì click tay. Có thể dùng CloudFormation, AWS SAM, AWS CDK hoặc Terraform để:

- Tạo resource và IAM role.
- Cấu hình event source và permission.
- Tạo test data fixture.
- Ghi stack output cho test runner.
- Gắn tag owner/build/expiry.
- Xóa resource khi test kết thúc.

Một pipeline điển hình:

~~~mermaid
flowchart TD
    A[Commit / Pull request] --> B[Lint code and IaC]
    B --> C[Unit and component tests]
    C --> D[Local emulator tests]
    D --> E[Deploy ephemeral AWS stack]
    E --> F[Cloud integration tests]
    F --> G[End-to-end smoke tests]
    G --> H[Publish test report]
    H --> I[Delete ephemeral stack]
    F -->|Failure| J[Collect logs and resource state]
    G -->|Failure| J
    J --> I
~~~

Nếu stack deploy thất bại một phần, cleanup cần xử lý cả resource được tạo dở. Giữ log và CloudFormation events trước khi xóa stack để không mất bằng chứng điều tra.

## 28. Ví dụ cloud integration test với AWS SAM

Một pipeline có thể build và deploy stack riêng cho mỗi run:

~~~bash
sam build

sam deploy \
  --stack-name orders-it-build-1042 \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=Integration
~~~

Sau khi deploy, lấy API endpoint hoặc resource ARN từ CloudFormation stack outputs rồi chạy integration test:

~~~bash
aws cloudformation describe-stacks \
  --stack-name orders-it-build-1042 \
  --query "Stacks[0].Outputs"
~~~

Test runner có thể gọi API, gửi order test và polling trạng thái downstream. Sau khi lưu test report, xóa đúng stack ephemeral:

~~~bash
sam delete --stack-name orders-it-build-1042
~~~

Stack name cần chứa build ID hoặc UUID để tránh xung đột. Chỉ cleanup stack được pipeline tạo và xác minh account/Region trước khi xóa. Nếu cần giữ resource để điều tra, dùng TTL tag và quy trình cleanup có kiểm soát.

## 29. Quản lý chi phí và cleanup của test environment

Cloud test sử dụng resource thật nên có thể phát sinh chi phí. Một test bị bỏ quên có thể để lại NAT Gateway, RDS instance, OpenSearch domain, SageMaker endpoint, EBS volume hoặc log group.

Biện pháp kiểm soát:

- Dùng budget và billing alarm cho account test.
- Tag resource với Owner, Environment, BuildId, CreatedAt và ExpiresAt.
- Đặt timeout/TTL cho test run.
- Xóa endpoint, cluster, database và NAT resource sau test.
- Giới hạn instance size và số lượng test song song.
- Dùng schedule để dừng resource có thể stop/start.
- Chỉ giữ log/test artifact theo retention cần thiết.
- Có cleanup job cho stack bị bỏ lại sau pipeline failure.
- Kiểm tra resource không được CloudFormation quản lý trước khi xóa thủ công.

Một số resource xóa lâu hoặc có phí trong lúc xóa. Theo dõi deletion status thay vì giả định lệnh delete trả về là resource đã biến mất.

## 30. Điều tra lỗi chỉ xuất hiện trên AWS

Khi test local pass nhưng cloud test fail, thu thập bằng chứng theo thứ tự:

1. **Identity:** principal ARN, assumed role session, credential source.
2. **Request:** API action, resource ARN, request ID, Region và timestamp.
3. **Authorization:** identity policy, resource policy, SCP, permission boundary, KMS key policy.
4. **Network:** VPC, subnet, route, SG, NACL, endpoint và DNS.
5. **Service state:** resource status, deployment event, quota, throttling và service health.
6. **Data:** event payload, schema version, idempotency key và encryption.
7. **Timing:** timeout, retry, visibility timeout, event delivery delay và eventual consistency.
8. **Observability:** CloudWatch logs/metrics, CloudTrail event, X-Ray trace và service-specific logs.

Các nguồn bằng chứng:

| Nguồn | Dùng để |
|---|---|
| CloudTrail | Xác định ai gọi AWS API, action, resource và error |
| CloudWatch Logs | Xem application logs, Lambda logs và service logs |
| CloudWatch Metrics | Xác định throttling, saturation, queue và health |
| X-Ray / OpenTelemetry | Theo dõi request qua nhiều service |
| CloudFormation Events | Tìm resource provisioning failure |
| Service-specific events | Xem trạng thái ECS, RDS, Lambda, SageMaker hoặc resource khác |
| AWS Health Dashboard | Kiểm tra sự kiện dịch vụ ảnh hưởng account/Region |

Luôn ghi request ID, stack ID, resource ARN và thời điểm UTC. Không đưa secret, access key hoặc payload nhạy cảm vào ticket/log khi chia sẻ lỗi.

## 31. Ma trận chọn công cụ và môi trường

| Câu hỏi cần trả lời | Công cụ/môi trường phù hợp | Cần test thêm trên AWS thật? |
|---|---|---|
| Hàm tính giá có đúng không? | Unit test | Không, nếu không phụ thuộc AWS |
| SDK được gọi với đúng tham số không? | Mock hoặc Stubber | Có, nếu cần xác minh service nhận request |
| Lambda parse event mẫu đúng không? | SAM local | Có, để xác minh event integration thật |
| DynamoDB query logic có đúng không? | DynamoDB Local hoặc emulator | Có, cho throughput, Streams, PITR, GSI timing |
| Các service có trao đổi qua API không? | AWS Emulator/LocalStack | Có, để xác minh IAM, network và service behavior |
| IAM role có quyền đúng không? | AWS test account với role thật | Có |
| PrivateLink/VPC route hoạt động không? | Workload trong VPC test | Có |
| Stack có tạo được trong account/Region không? | Deploy CloudFormation/SAM/CDK | Có |
| Hệ thống chịu peak load không? | AWS load test environment | Có |
| Ứng dụng phục hồi sau fault không? | AWS FIS pre-production experiment | Có |

Một bộ test tốt thường dùng nhiều công cụ. Emulator không cạnh tranh với AWS integration test; mỗi loại kiểm tra một lớp khác nhau.

## 32. Case study: kiểm thử hệ thống xử lý đơn hàng

Một ứng dụng thương mại điện tử dùng API Gateway, Lambda, DynamoDB, EventBridge và SQS. Nhóm muốn xác minh luồng OrderCreated trước khi release.

**Tầng local:**

- Unit test kiểm tra validation, tính phí và tạo event.
- Stubber xác minh SDK gọi PutItem/PutEvents với đúng tham số.
- SAM local chạy handler với API Gateway event và SQS event fixture.
- AWS Emulator hoặc LocalStack kiểm tra luồng API giữa một số service được hỗ trợ.

**Tầng cloud integration:**

- Tạo stack ephemeral với API, Lambda, DynamoDB, EventBridge và SQS thật.
- Dùng execution role giới hạn quyền.
- Gửi order test qua API Gateway.
- Poll DynamoDB tới khi trạng thái fulfillment được cập nhật.
- Xác minh event đi vào đúng queue và consumer xử lý đúng.
- Gửi lại cùng event ID để kiểm tra idempotency.
- Gửi event sai schema để xác minh error handling và DLQ.
- Kiểm tra CloudTrail, Lambda logs và CloudWatch metrics.

**Tầng performance và resilience:**

- Tăng request rate trong test account và theo dõi p95/p99, throttling, Lambda concurrency và queue age.
- Tạm giảm consumer capacity hoặc dùng fault injection phù hợp để xác minh backlog và recovery.
- Xác minh stop condition và runbook trước mọi experiment FIS.

Sau test, lưu report, CloudFormation events, log link và metrics. Cleanup stack đúng build ID; không xóa dữ liệu hoặc resource dùng chung của team.

## 33. Lab: so sánh local và cloud test

Thực hiện với dữ liệu giả lập trong project hoặc AWS test account được phê duyệt.

### Bước 1: Viết unit test

Tạo một function xử lý order và test các trường hợp hợp lệ, thiếu field, amount âm và duplicate event ID. Chạy test mà không cần AWS credentials.

### Bước 2: Kiểm tra SDK call bằng Stubber

Stub SQS hoặc DynamoDB operation. Xác minh operation name, input parameters và response/error path.

### Bước 3: Chạy SAM local

Dùng event JSON mẫu để invoke Lambda handler. Xác định rõ các SDK calls có trỏ tới AWS thật hay emulator.

### Bước 4: Chạy emulator

Tạo resource local và thực hiện một luồng API được emulator hỗ trợ. Ghi lại emulator version, service/API operation và fidelity limitation.

### Bước 5: Deploy test stack lên AWS

Dùng IaC tạo resource có tag Environment=Integration và BuildId riêng. Xác nhận CLI đang dùng đúng account và Region.

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

### Bước 6: Chạy cloud integration test

Gửi event test, kiểm tra dữ liệu và trạng thái downstream. Xác minh role và resource policy bằng chính workload identity.

### Bước 7: Ghi nhận khác biệt

So sánh response, timing, error, retry, permission và state transition giữa local và AWS. Phân loại mỗi khác biệt thành emulator gap, configuration issue, IAM issue, network issue hoặc service behavior.

### Bước 8: Cleanup

Xác minh stack name và account/Region rồi xóa stack ephemeral. Kiểm tra resource còn sót và giữ lại test report/log cần thiết.

## 34. Checklist production readiness cho chiến lược kiểm thử

### Coverage

- [ ] Có unit test cho business logic và edge case.
- [ ] Có component test cho adapter và serialization.
- [ ] Có local integration test cho luồng có thể mô phỏng.
- [ ] Có cloud integration test cho IAM, network và managed-service behavior.
- [ ] Có end-to-end test cho critical business workflow.
- [ ] Có performance test theo SLO và peak traffic.
- [ ] Có resilience/restore test theo RTO/RPO.

### Local simulation

- [ ] Emulator version được pin trong CI.
- [ ] Đã kiểm tra API/feature fidelity cần thiết.
- [ ] Không dùng emulator làm security hoặc performance proof.
- [ ] AWS SAM local không vô tình gọi resource production.
- [ ] DynamoDB Local limitations được xét trong test design.
- [ ] Credential và endpoint được cô lập rõ ràng.

### AWS test environment

- [ ] Test account/environment tách khỏi production.
- [ ] Role và resource policy giống production về mặt quyền cần kiểm chứng.
- [ ] Network path phù hợp workload thật.
- [ ] Test data được synthetic hoặc masking.
- [ ] Service quota và Region availability đã kiểm tra.
- [ ] Resource có tag owner/build/expiry.
- [ ] Budget, alarm và cleanup automation hoạt động.

### CI/CD và vận hành

- [ ] cfn-lint/Guard chạy trước deploy.
- [ ] Integration test chạy sau khi stack ở trạng thái sẵn sàng.
- [ ] Test report có request ID, resource ARN và timestamp.
- [ ] Failure logs được lưu trước cleanup.
- [ ] Retry và polling có timeout/backoff.
- [ ] Fault injection có hypothesis, target và stop condition.
- [ ] Restore test xác minh được RTO/RPO thực tế.
- [ ] Có quy trình xử lý test stack bị bỏ lại.

## 35. Bài tập tự kiểm tra

### Câu 1

Unit test và integration test khác nhau thế nào?

**Đáp án:** Unit test kiểm tra một đơn vị code cô lập; integration test kiểm tra nhiều thành phần tương tác qua dependency hoặc service.

### Câu 2

Mock thành công có chứng minh AWS API thực tế sẽ thành công không?

**Đáp án:** Không. Mock chỉ trả behavior định trước; nó không kiểm tra service, IAM, resource policy, network hoặc quota thật.

### Câu 3

AWS Emulator có đánh giá IAM identity policy và resource-based policy giống AWS không?

**Đáp án:** Không. Không dùng AWS Emulator làm bằng chứng kiểm thử bảo mật.

### Câu 4

Vì sao emulator có thể không phát hiện lỗi VPC?

**Đáp án:** Emulator không tái tạo đầy đủ route table, security group, NACL, endpoint policy, PrivateLink và DNS của VPC thật.

### Câu 5

AWS SAM local có tự động mô phỏng mọi AWS service mà Lambda gọi không?

**Đáp án:** Không. SDK calls có thể đi tới AWS resource thật trừ khi được trỏ tới emulator hoặc dependency thay thế.

### Câu 6

DynamoDB Local có thể dùng để benchmark provisioned throughput không?

**Đáp án:** Không. Provisioned throughput setting bị bỏ qua; hiệu năng phụ thuộc máy local.

### Câu 7

Tại sao local DynamoDB có thể che giấu vấn đề eventual consistency hoặc GSI timing?

**Đáp án:** Thao tác local thường hoàn tất rất nhanh, table có thể luôn ACTIVE và read thường xuất hiện như strongly consistent.

### Câu 8

Cloud integration test nên dùng credential nào?

**Đáp án:** Nên dùng IAM role riêng của workload/test với quyền tối thiểu tương ứng production.

### Câu 9

Tại sao cần test cả positive và negative authorization?

**Đáp án:** Positive test chứng minh quyền cần thiết hoạt động; negative test chứng minh role không truy cập được resource ngoài phạm vi.

### Câu 10

SQS consumer cần xử lý duplicate message thế nào?

**Đáp án:** Thiết kế idempotent bằng event ID hoặc business key và lưu trạng thái xử lý để duplicate không tạo side effect hai lần.

### Câu 11

Tại sao không nên dùng sleep cố định dài trong integration test?

**Đáp án:** Nó làm test chậm và không bảo đảm resource đã sẵn sàng; dùng polling có timeout/backoff và kiểm tra trạng thái thực.

### Câu 12

cfn-lint kiểm tra điều gì?

**Đáp án:** Kiểm tra cấu trúc template, resource property, value, reference và các rule theo CloudFormation schema.

### Câu 13

CloudFormation Guard có thay thế cfn-lint không?

**Đáp án:** Không. Guard đánh giá policy-as-code trên dữ liệu JSON/YAML; cfn-lint kiểm tra schema và cấu trúc template.

### Câu 14

CloudFormation Guard CLI có tự chặn mọi deployment không?

**Đáp án:** Không. Guard CLI là bước validation trong pipeline; cần CloudFormation Hooks hoặc cơ chế enforcement phía server để chặn provisioning.

### Câu 15

Vì sao performance test phải chạy trên AWS thật?

**Đáp án:** Cần compute, network, storage, quota và managed scaling thực tế; emulator/local hardware không đại diện production capacity.

### Câu 16

AWS FIS có tác động lên resource giả lập không?

**Đáp án:** AWS FIS thực hiện hành động trên AWS resource thật; cần target, IAM permission, hypothesis và stop condition.

### Câu 17

Một test stack bị lỗi giữa quá trình deploy cần giữ bằng chứng nào?

**Đáp án:** CloudFormation events, request ID, resource status, CloudWatch logs/metrics và deployment output trước khi cleanup.

### Câu 18

Tại sao mỗi parallel test run cần resource name riêng?

**Đáp án:** Tránh collision, ghi đè dữ liệu hoặc cleanup nhầm resource của test run khác.

### Câu 19

Một test local pass nhưng AWS test fail 403. Cần kiểm tra gì trước?

**Đáp án:** Principal thực tế, identity policy, resource policy, SCP, permissions boundary, KMS policy và endpoint policy.

### Câu 20

Có backup thành công đã đủ chứng minh disaster recovery không?

**Đáp án:** Chưa. Phải restore, kiểm tra dữ liệu, kết nối ứng dụng và đo RTO/RPO thực tế.

## 36. Tài liệu tham khảo chính thức

- [How to test serverless functions and applications](https://docs.aws.amazon.com/lambda/latest/dg/testing-guide.html)
- [Local testing with AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-local-testing.html)
- [AWS Emulator documentation](https://docs.aws.amazon.com/emulator/)
- [What is AWS Emulator and its limitations](https://docs.aws.amazon.com/emulator/latest/userguide/what-is-service.html)
- [Fidelity in AWS Emulator](https://docs.aws.amazon.com/emulator/latest/userguide/fidelity.html)
- [DynamoDB Local setup](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.html)
- [DynamoDB Local usage notes and differences](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.UsageNotes.html)
- [Validate CloudFormation templates with cfn-lint](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cfn-lint.html)
- [Validate templates with CloudFormation Guard](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-guard.html)
- [Testing CloudFormation Guard rules](https://docs.aws.amazon.com/cfn-guard/latest/ug/testing-rules.html)
- [CloudFormation best practices](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html)
- [What is AWS Fault Injection Service](https://docs.aws.amazon.com/fis/latest/userguide/what-is.html)
- [Planning AWS FIS experiments](https://docs.aws.amazon.com/fis/latest/userguide/getting-started-planning.html)
- [Test resiliency using chaos engineering](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_testing_resiliency_failure_injection_resiliency.html)
- [Best practices for testing serverless applications](https://docs.aws.amazon.com/prescriptive-guidance/latest/serverless-application-testing/best-practices.html)
- [Challenges when testing serverless applications](https://docs.aws.amazon.com/prescriptive-guidance/latest/serverless-application-testing/challenges.html)
- [Pre-deployment activities and integration testing](https://docs.aws.amazon.com/prescriptive-guidance/latest/resilience-lifecycle-framework/pre-deployment.html)

Service features, emulator fidelity, quotas and regional availability change over time. Pin tool versions in CI, inspect the official compatibility/fidelity documentation for the APIs under test, and keep at least one test stage against the actual AWS services used by the application.

