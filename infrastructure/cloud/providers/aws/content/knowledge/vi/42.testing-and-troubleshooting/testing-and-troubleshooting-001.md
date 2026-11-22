# Chiến lược unit, integration và end-to-end test trên AWS

Ứng dụng chạy trên AWS thường gồm nhiều dịch vụ phối hợp: API Gateway nhận request, Lambda hoặc ECS xử lý nghiệp vụ, DynamoDB hoặc RDS lưu dữ liệu, SQS và EventBridge truyền sự kiện, S3 lưu file, IAM kiểm soát quyền và CloudWatch theo dõi hoạt động. Một hàm xử lý có thể chạy đúng khi kiểm thử riêng nhưng vẫn thất bại trong môi trường thật vì policy thiếu quyền, event mapping sai, timeout không phù hợp, retry tạo dữ liệu trùng hoặc các dịch vụ được cấu hình không khớp nhau.

Chiến lược kiểm thử trên AWS cần xác minh từng phần ở mức phù hợp. Unit test kiểm tra logic nhỏ và chạy nhanh. Integration test kiểm tra hợp đồng giữa ứng dụng với AWS service hoặc giữa các dịch vụ. End-to-end (E2E) test xác minh một luồng nghiệp vụ hoàn chỉnh qua các thành phần đã triển khai. Các lớp kiểm thử này bổ sung cho nhau; không một lớp nào đủ để chứng minh toàn bộ hệ thống hoạt động đúng.

AWS cung cấp nhiều công cụ để hỗ trợ quy trình này: AWS SAM CLI và AWS CDK cho phát triển, AWS CodeBuild và CodePipeline cho CI/CD, CloudFormation để triển khai hạ tầng, CloudWatch và X-Ray để quan sát, CloudWatch Synthetics để kiểm tra hành trình người dùng, AWS Fault Injection Service (FIS) để thử khả năng chịu lỗi và các dịch vụ bảo mật để đánh giá cấu hình. Có thể kết hợp kiểm thử cục bộ, môi trường AWS dùng riêng và kiểm thử có kiểm soát trên production.

Bài học này thuộc phạm vi CLOUD_PROVIDERS_AWS: thiết kế và triển khai ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí. Trọng tâm là xây dựng chiến lược unit, integration và E2E test trên AWS, lựa chọn môi trường, dữ liệu kiểm thử, tự động hóa trong pipeline và xử lý lỗi dựa trên bằng chứng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt unit test, component test, integration test, contract test và end-to-end test.
- Xây dựng test pyramid phù hợp với ứng dụng dùng AWS.
- Xác định phần nào nên chạy cục bộ, phần nào cần kiểm thử trên AWS thật.
- Kiểm thử Lambda, API Gateway, S3, DynamoDB, RDS, SQS, EventBridge và Step Functions.
- Sử dụng AWS SAM CLI, AWS CDK và CloudFormation trong quy trình kiểm thử.
- Thiết kế test account, ephemeral environment và dữ liệu kiểm thử an toàn.
- Kiểm tra IAM permission theo cả trường hợp được phép và bị từ chối.
- Tự động hóa kiểm thử trong CodeBuild, CodePipeline hoặc CI/CD platform tương thích.
- Thiết kế performance, security, resilience, recovery và smoke test.
- Theo dõi kết quả bằng CloudWatch, X-Ray, CloudTrail và log có correlation ID.
- Đánh giá chất lượng kiểm thử, thời gian phản hồi và chi phí của pipeline.

## 2. Vì sao cần nhiều lớp kiểm thử?

### 2.1. Kiểm thử một hàm không chứng minh hệ thống hoạt động

Giả sử một API tạo đơn hàng:

1. API Gateway nhận request.
2. Lambda xác thực dữ liệu và kiểm tra quyền.
3. Lambda ghi đơn hàng vào DynamoDB.
4. Lambda gửi event tới EventBridge.
5. Consumer xử lý thanh toán hoặc thông báo.
6. Dashboard đọc trạng thái đơn hàng.

Unit test có thể xác nhận hàm tính tổng tiền trả kết quả đúng. Nhưng nó không chứng minh:

- API Gateway mapping đúng body và header.
- Lambda execution role có quyền ghi DynamoDB.
- DynamoDB table có key schema phù hợp.
- EventBridge rule khớp event.
- Consumer nhận event và xử lý idempotent.
- Retry hoặc DLQ hoạt động như thiết kế.
- Người dùng chỉ đọc được đơn hàng thuộc quyền của họ.

Do đó, kiểm thử cần bao phủ logic, ranh giới dịch vụ và hành trình nghiệp vụ.

### 2.2. Các lớp kiểm thử

| Lớp | Phạm vi | Mục tiêu | Đặc điểm |
|---|---|---|---|
| Unit test | Hàm, class hoặc module nhỏ | Xác minh logic và quy tắc nghiệp vụ | Nhanh, cô lập dependency |
| Component test | Một thành phần chạy gần môi trường thật | Kiểm tra handler, container hoặc worker | Có thể dùng dependency giả hoặc local emulator |
| Integration test | Hai hoặc nhiều thành phần/service | Kiểm tra API, permission, event và dữ liệu thực | Thường cần AWS test environment |
| Contract test | Hợp đồng producer-consumer | Phát hiện thay đổi schema/API gây lỗi | Có thể chạy nhanh trong CI |
| End-to-end test | Luồng nghiệp vụ xuyên hệ thống | Xác minh hành vi người dùng thực tế | Chậm hơn, ít trường hợp hơn |
| Non-functional test | Hiệu năng, bảo mật, phục hồi | Kiểm tra yêu cầu vận hành | Cần giới hạn và kế hoạch riêng |

### 2.3. Test pyramid

Một chiến lược thường dùng có nhiều unit test, ít integration test hơn và số lượng E2E test nhỏ hơn. Lý do là unit test nhanh, dễ chẩn đoán; E2E test bao phủ rộng nhưng tốn thời gian và dễ phụ thuộc trạng thái môi trường.

~~~mermaid
flowchart TB
    E["E2E tests<br/>Ít, bao phủ luồng nghiệp vụ chính"]
    I["Integration and contract tests<br/>Kiểm tra ranh giới AWS services"]
    U["Unit tests<br/>Nhiều, chạy nhanh và cô lập"]
    E --> I --> U
~~~

Đây là nguyên tắc định hướng, không phải tỷ lệ cứng. Một hệ thống event-driven có nhiều rủi ro ở integration boundary có thể cần nhiều integration test hơn ứng dụng CRUD đơn giản.

### 2.4. Test pyramid không thay thế production validation

Test pass trước khi deploy chưa chứng minh bản release hoạt động trong môi trường production. Cấu hình DNS, secret, quota, dữ liệu thật, traffic pattern và dependency bên ngoài có thể khác. Sau deploy cần smoke test, health check, canary hoặc synthetic monitoring và theo dõi metric để phát hiện regression.

## 3. Xác định phạm vi và tiêu chí kiểm thử

### 3.1. Bắt đầu từ yêu cầu và rủi ro

Không nên viết test chỉ để tăng số lượng hoặc coverage. Trước hết xác định:

- Hành vi nghiệp vụ nào quan trọng?
- Dữ liệu nào không được mất hoặc bị lộ?
- Thành phần nào có quyền thay đổi dữ liệu?
- Những dependency nào có thể lỗi hoặc chậm?
- Hệ thống cần xử lý bao nhiêu request hoặc event?
- RPO, RTO và SLA là bao nhiêu?
- Hậu quả của lỗi là gì?

Từ đó chọn test có khả năng phát hiện lỗi tương ứng. Ví dụ, yêu cầu không tạo hai đơn hàng khi client retry cần unit test cho idempotency key, integration test cho conditional write và E2E test cho tình huống request bị timeout sau khi ghi thành công.

### 3.2. Viết acceptance criteria có thể kiểm chứng

Một acceptance criterion tốt mô tả đầu vào, hành động và kết quả quan sát được.

Ví dụ:

- Khi người dùng có quyền gửi request hợp lệ, API trả mã thành công và tạo đúng một order record.
- Khi người dùng không có quyền, API trả lỗi authorization và không ghi dữ liệu.
- Khi downstream consumer lỗi tạm thời, message được retry theo policy và không tạo side effect trùng.
- Khi số lượng message vượt khả năng xử lý, backlog được quan sát và hệ thống phục hồi sau khi tải giảm.
- Khi database mất kết nối, API trả lỗi có kiểm soát và không để request treo vô hạn.

### 3.3. Traceability

Gắn test case với yêu cầu, rủi ro hoặc issue. Khi một test thất bại, nhóm cần biết hành vi nào đang được bảo vệ và release có bị chặn hay không. Có thể lưu test ID, requirement ID, commit, build ID và deployment ID trong báo cáo.

### 3.4. Phân loại mức độ test

| Mức độ | Ví dụ | Hành động khi thất bại |
|---|---|---|
| Critical | Sai quyền truy cập, mất giao dịch, hỏng dữ liệu | Chặn release |
| High | Luồng nghiệp vụ chính không hoàn tất | Chặn release hoặc yêu cầu phê duyệt ngoại lệ |
| Medium | Một chức năng phụ bị lỗi | Đánh giá impact và kế hoạch sửa |
| Low | Sai lệch hiển thị không ảnh hưởng dữ liệu | Ghi nhận và xử lý theo backlog |

Không dùng một tiêu chí pass/fail duy nhất cho mọi test. Một unit test flaky không giống lỗi authorization ở production.

## 4. Thiết kế môi trường kiểm thử trên AWS

### 4.1. Local development

Local environment phù hợp cho:

- Unit test và kiểm tra logic.
- Test serialization/deserialization.
- Kiểm tra handler với event fixture.
- Chạy API hoặc Lambda handler trong runtime tương thích.
- Kiểm tra nhanh contract và validation.

Các công cụ:

- AWS SAM CLI hỗ trợ build, invoke và chạy một số thành phần Lambda/API cục bộ.
- AWS CDK hỗ trợ synthesize template và kiểm thử cấu trúc construct.
- DynamoDB Local hỗ trợ phát triển và kiểm thử một số hành vi DynamoDB.
- AWS SDK mock/stub hỗ trợ kiểm tra ứng dụng mà không gọi AWS.
- LocalStack là lựa chọn giả lập dịch vụ AWS do bên thứ ba cung cấp; cần xác minh tính năng và hành vi được hỗ trợ trước khi dùng làm bằng chứng tương thích AWS.

Môi trường local không thay thế integration test trên AWS. Emulator có thể không mô phỏng đầy đủ IAM, quota, event delivery, network, consistency hoặc giới hạn thực tế của dịch vụ.

### 4.2. AWS test account

Integration và E2E test thường cần AWS account hoặc environment riêng. Ưu tiên dùng AWS Organizations để tách account theo development, test, staging và production khi quy mô tổ chức cho phép.

Lợi ích:

- Giảm nguy cơ test xóa hoặc ghi đè dữ liệu production.
- Có thể cấp quota, policy và budget riêng.
- Dễ cleanup tài nguyên thử nghiệm.
- Có ranh giới bảo mật và audit rõ hơn.
- Kiểm thử cross-account nếu kiến trúc thật có sử dụng.

Không nên coi một VPC riêng trong cùng production account là ranh giới bảo vệ đầy đủ. IAM role, bucket, event bus, KMS key và nhiều tài nguyên khác vẫn có thể dùng chung account.

### 4.3. Ephemeral environment

Ephemeral environment là môi trường được tạo cho một branch, pull request hoặc test run rồi xóa sau khi hoàn tất. Có thể triển khai bằng CloudFormation/CDK/SAM và đặt tên theo build ID.

Một lifecycle:

1. CI tạo stack với tên duy nhất.
2. Tạo resource và dữ liệu kiểm thử.
3. Chạy integration/E2E test.
4. Thu thập log, report và metric.
5. Xóa stack và tài nguyên phụ thuộc.
6. Kiểm tra cleanup thành công.

Ephemeral environment giúp tránh test chạy trên tài nguyên dùng chung. Tuy nhiên, cần xử lý tài nguyên khó xóa như S3 bucket còn object, log group, snapshot, retained resource hoặc database có deletion protection.

### 4.4. Shared test environment

Một môi trường test dùng chung có thể tiết kiệm chi phí nhưng dễ xảy ra xung đột:

- Hai test run dùng cùng record hoặc queue.
- Một test xóa dữ liệu của test khác.
- Message từ run cũ được xử lý trong run mới.
- Test phụ thuộc thứ tự chạy.
- Một deployment thay đổi schema trong khi test khác đang chạy.

Giải pháp là namespace theo run ID, dữ liệu cô lập, queue/topic riêng hoặc ephemeral stack. Nếu phải dùng shared environment, cần quản lý lock và tránh test phá hủy dữ liệu chung.

### 4.5. Quản lý cấu hình và secret

Test environment không nên chứa credential production. Dùng IAM role, temporary credentials, AWS Secrets Manager hoặc Systems Manager Parameter Store theo nhu cầu.

Tách:

- Environment variables không nhạy cảm.
- Secret cần bảo vệ.
- Test fixture.
- Endpoint/resource ARN theo environment.

Không commit secret, private key, token hoặc dữ liệu thật vào repository. Pipeline chỉ nên cấp secret cho job cần dùng và giới hạn thời gian tồn tại của credential.

## 5. Unit test cho ứng dụng dùng AWS

### 5.1. Tách logic nghiệp vụ khỏi AWS SDK

Một Lambda handler không nên chứa toàn bộ validation, tính toán, gọi database, publish event và format response trong một hàm lớn. Tách logic thuần khỏi adapter giúp unit test nhanh và dễ hiểu.

Ví dụ cấu trúc:

~~~text
src/
  handlers/
    create_order.py
  domain/
    order.py
    pricing.py
  adapters/
    order_repository.py
    event_publisher.py
tests/
  unit/
    test_pricing.py
    test_create_order.py
~~~

Domain logic có thể kiểm thử mà không cần khởi tạo AWS client. Adapter chịu trách nhiệm chuyển lời gọi nghiệp vụ thành SDK request.

### 5.2. Ví dụ kiểm thử logic thuần

~~~python
from decimal import Decimal

def calculate_total(items, tax_rate):
    if not items:
        raise ValueError("Order must contain at least one item")

    subtotal = sum(
        Decimal(str(item["price"])) * item["quantity"]
        for item in items
    )
    return (subtotal * (Decimal("1") + Decimal(str(tax_rate)))).quantize(
        Decimal("0.01")
    )

def test_calculate_total():
    items = [
        {"price": "10.00", "quantity": 2},
        {"price": "5.50", "quantity": 1},
    ]
    assert calculate_total(items, "0.10") == Decimal("28.05")
~~~

Test này kiểm tra quy tắc tính tiền và không phụ thuộc AWS. Nên bổ sung case danh sách rỗng, số lượng âm, giá không hợp lệ, rounding và mức thuế biên.

### 5.3. Mock AWS SDK ở ranh giới

Khi kiểm tra adapter, có thể mock client hoặc dùng stub để xác minh ứng dụng gọi đúng operation và xử lý response/error. Với Python, botocore Stubber có thể cung cấp response đã định nghĩa cho AWS SDK client. Với Java, có thể dùng Mockito để mock interface/client của AWS SDK v2.

Ví dụ khái quát:

~~~python
from botocore.stub import Stubber
import boto3

client = boto3.client("dynamodb", region_name="ap-southeast-1")
stubber = Stubber(client)

stubber.add_response(
    "put_item",
    {"ConsumedCapacity": {"CapacityUnits": 1.0}},
    {
        "TableName": "orders-test",
        "Item": {
            "orderId": {"S": "order-123"},
            "status": {"S": "PENDING"},
        },
    },
)

with stubber:
    response = client.put_item(
        TableName="orders-test",
        Item={
            "orderId": {"S": "order-123"},
            "status": {"S": "PENDING"},
        },
    )
    assert response["ConsumedCapacity"]["CapacityUnits"] == 1.0
~~~

Đây là ví dụ kiểm tra request/response ở SDK boundary. Stubber không xác minh IAM permission, table schema thật, network hoặc hành vi DynamoDB service. Những phần đó cần integration test trên AWS.

### 5.4. Mock vừa đủ

Mock quá sâu có thể khiến test chỉ chứng minh mock hoạt động. Không nên mock mọi class nội bộ rồi kiểm tra số lần gọi từng hàm nếu điều quan trọng là kết quả nghiệp vụ.

Nên mock:

- Clock khi cần kiểm thử thời gian.
- Random generator khi cần kết quả xác định.
- External API không thuộc phạm vi test.
- AWS client ở unit test adapter.

Không nên mock:

- Toàn bộ domain logic.
- Mọi hàm nội bộ của cùng một module.
- Response theo giả định không khớp AWS API.

Với mỗi mock, xác định rõ hợp đồng mà nó đại diện và có integration test kiểm chứng hợp đồng đó.

### 5.5. Test case và property-based testing

Unit test nên bao gồm:

- Happy path.
- Input thiếu hoặc sai kiểu.
- Boundary values.
- Duplicate request.
- Timeout/exception từ dependency.
- Retry và idempotency.
- Quyền truy cập và validation.

Property-based testing có thể sinh nhiều input để kiểm tra bất biến, ví dụ tổng tiền không âm khi mọi item hợp lệ, hoặc encode rồi decode một event không làm mất field bắt buộc. Dùng thư viện phù hợp ngôn ngữ và giới hạn seed để kết quả có thể tái lập.

## 6. Component test và kiểm thử Lambda

### 6.1. Kiểm thử Lambda handler

Lambda handler nhận event, context và trả response hoặc thực hiện side effect. Unit/component test cần kiểm tra:

- Event shape đúng với nguồn kích hoạt.
- Validation và error mapping.
- Timeout-sensitive logic.
- Idempotency.
- Structured logging.
- Không ghi dữ liệu nhạy cảm vào log.

Tạo fixture riêng cho API Gateway proxy event, SQS event, EventBridge event, S3 notification hoặc DynamoDB Streams. Không dùng một JSON event chung cho mọi trigger vì envelope và semantics khác nhau.

### 6.2. AWS SAM CLI

AWS SAM CLI có thể:

- Build ứng dụng theo template.
- Invoke Lambda function cục bộ với event JSON.
- Chạy API Gateway-compatible local endpoint cho một số loại API.
- Tạo package/deployment artifact.
- Kiểm tra template và hỗ trợ triển khai stack.

Ví dụ:

~~~bash
sam build
sam local invoke CreateOrderFunction --event events/api-create-order.json
~~~

Ví dụ chạy API cục bộ:

~~~bash
sam local start-api
~~~

SAM local hữu ích cho vòng lặp phát triển nhanh, nhưng không mô phỏng đầy đủ IAM, service integration, concurrency, VPC networking và mọi runtime behavior của AWS. Cần kiểm thử function đã deploy trong test account.

### 6.3. Lambda execution role

Lambda chạy bằng execution role. Kiểm thử trên AWS cần xác minh:

- Role có quyền tối thiểu cần thiết.
- Resource ARN và Region đúng.
- KMS permission nếu dữ liệu mã hóa.
- VPC security group, subnet và endpoint nếu function chạy trong VPC.
- Secret/parameter có thể đọc được.
- Permission boundary hoặc SCP không chặn operation.

Unit test không thể chứng minh role có quyền thật. Integration test nên gọi luồng bằng function đã deploy và kiểm tra cả thao tác được phép lẫn bị từ chối.

### 6.4. Lambda retry và duplicate

Hành vi retry phụ thuộc nguồn gọi:

- Synchronous invocation thường trả lỗi cho caller; caller quyết định retry.
- Asynchronous invocation có cơ chế retry và destination/DLQ theo cấu hình.
- SQS event source mapping poll queue và xử lý theo batch; lỗi có thể khiến message được giao lại.
- Stream event source mapping có checkpoint và retry semantics theo cấu hình.

Không giả định mọi trigger có cùng retry behavior. Kiểm tra cấu hình thực tế, partial batch response, maximum record age, retry attempts và DLQ/destination khi phù hợp.

### 6.5. Kiểm thử concurrency và cold start

Với workload nhạy latency, đo:

- Duration và init duration.
- Concurrent executions.
- Throttles.
- Memory và CPU behavior.
- Connection reuse tới database.
- Timeout khi dependency chậm.

Không chỉ chạy một lần trong local để kết luận hiệu năng. Cần tải đại diện trên AWS test environment, với concurrency và dữ liệu gần production.

## 7. Integration test với AWS services

### 7.1. Nguyên tắc

Integration test cần kiểm tra hợp đồng thật giữa các thành phần. Một test nên:

1. Tạo hoặc xác định resource test riêng.
2. Chuẩn bị dữ liệu đầu vào.
3. Gọi service/API thật.
4. Chờ kết quả theo điều kiện có timeout.
5. Đọc output và xác minh trạng thái.
6. Dọn dữ liệu/resource đã tạo.

Dùng tên resource có build ID hoặc test run ID để tránh xung đột. Cleanup nên chạy cả khi test fail; có thể dùng teardown hook và một scheduled cleanup cho tài nguyên còn sót.

### 7.2. Amazon S3

Các trường hợp cần kiểm tra:

- PutObject và GetObject với role thực tế.
- Bucket policy và KMS encryption.
- Event notification hoặc EventBridge event sau object creation.
- Prefix, metadata và content type.
- Multipart upload và cleanup incomplete upload nếu ứng dụng dùng.
- Versioning và restore khi ứng dụng dựa vào object version.
- Lifecycle không xóa dữ liệu còn cần.

S3 có strong read-after-write consistency cho các thao tác object được hỗ trợ, nhưng event notification và các consumer downstream vẫn là luồng bất đồng bộ. Test nên đợi event bằng polling có timeout thay vì sleep cố định.

### 7.3. Amazon DynamoDB

Kiểm tra:

- Partition key và sort key.
- Conditional write và optimistic locking.
- Update expression.
- TTL behavior theo kỳ vọng nghiệp vụ.
- GSI/LSI query.
- Transaction khi dùng TransactWriteItems.
- IAM policy giới hạn table/index.
- Throttling và retry.

Một số truy vấn index có eventual consistency. Test không nên giả định mọi GSI query phản ánh write ngay tức thì. Nếu nghiệp vụ cần đọc nhất quán, chọn cách đọc và mô hình dữ liệu phù hợp.

### 7.4. Amazon RDS/Aurora

Kiểm tra:

- Kết nối qua network path thực tế.
- Security group và subnet routing.
- Database credentials/Secrets Manager.
- Schema migration.
- Transaction commit/rollback.
- Constraint, index và query behavior.
- Connection pool và giới hạn connection.
- Failover hoặc reconnect nếu workload cần.

Test migration trên database dùng riêng, có dữ liệu đại diện và backup/snapshot theo yêu cầu. Không chạy migration phá hủy trên database dùng chung mà không có quy trình phê duyệt.

### 7.5. Amazon SQS

Kiểm tra:

- SendMessage và ReceiveMessage.
- Visibility timeout.
- Long polling.
- Redrive policy và DLQ.
- Batch size và partial batch response.
- Duplicate delivery và idempotency.
- FIFO ordering và message group khi dùng FIFO queue.

SQS standard queue cung cấp at-least-once delivery; consumer phải chịu được duplicate. FIFO queue có ordering/deduplication features nhưng không loại bỏ mọi yêu cầu idempotency ở tầng nghiệp vụ.

### 7.6. Amazon EventBridge

Kiểm tra:

- Event schema và required fields.
- Event bus, rule pattern và target.
- Input transformer.
- Retry policy và DLQ.
- Permission cho target.
- Duplicate event và consumer idempotency.
- Archive/replay nếu ứng dụng dùng.

Một rule không khớp pattern có thể khiến event không tới target mà không làm producer publish thất bại. Cần test positive case và negative case của event pattern.

### 7.7. API Gateway

Kiểm tra:

- Route và method.
- Request/response mapping.
- JWT/IAM/Lambda authorizer.
- CORS.
- Validation và error mapping.
- Throttling và quota.
- Timeout/integration behavior.
- Access logging và stage configuration.

Test API trực tiếp qua endpoint đã deploy để kiểm tra gateway configuration. Unit test handler không thể phát hiện mapping template hoặc authorizer bị cấu hình sai.

### 7.8. AWS Step Functions

Kiểm tra:

- State transition và branching.
- Retry/Catch.
- Timeout và heartbeat.
- Input/output path.
- Service integration permission.
- Callback pattern hoặc wait state.
- Compensation khi một bước thất bại.

Unit test cho function/task logic vẫn cần thiết. Integration test cần chạy state machine trong test account để xác minh service integration và execution role.

### 7.9. Lambda với SQS hoặc EventBridge

Ví dụ luồng:

1. Gửi một message có testRunId vào SQS.
2. Event source mapping kích hoạt Lambda.
3. Lambda ghi kết quả vào DynamoDB test table.
4. Test polling DynamoDB theo testRunId.
5. Xác minh số record và trạng thái.
6. Dọn message/record.

Test cần có timeout và diagnostic khi chờ quá lâu. Tránh sleep cố định vài giây vì môi trường nhanh/chậm khác nhau sẽ làm test flaky.

## 8. Contract test và schema compatibility

### 8.1. Vì sao cần contract test?

Trong hệ thống event-driven, producer và consumer có thể được deploy độc lập. Producer đổi tên field hoặc kiểu dữ liệu có thể làm consumer lỗi dù từng service vẫn pass unit test.

Contract test kiểm tra:

- Event name/type.
- Required fields và optional fields.
- Data type và format.
- Version.
- Semantics của field.
- Backward/forward compatibility theo chiến lược đã chọn.

### 8.2. Event versioning

Ví dụ event order:

~~~json
{
  "version": "1",
  "source": "commerce.orders",
  "detail-type": "OrderCreated",
  "detail": {
    "orderId": "order-123",
    "customerId": "customer-456",
    "totalAmount": 125.50,
    "currency": "VND"
  }
}
~~~

Khi thêm field, consumer cũ thường có thể bỏ qua field không biết nếu parser được thiết kế linh hoạt. Đổi tên hoặc thay kiểu field có thể phá vỡ contract. Dùng schema registry hoặc JSON Schema/Avro/Protobuf phù hợp với hệ thống để quản lý version.

### 8.3. Consumer-driven contract

Consumer mô tả phần event/API mà nó cần. Producer chạy contract test để đảm bảo thay đổi không phá vỡ các consumer đã đăng ký. Điều này hữu ích khi nhiều team phát triển độc lập và không thể chạy toàn bộ E2E cho mọi thay đổi.

## 9. End-to-end test

### 9.1. Chọn luồng quan trọng

E2E test nên tập trung vào hành trình nghiệp vụ mang lại giá trị hoặc có rủi ro cao. Ví dụ:

- Đăng nhập và tạo đơn hàng.
- Thanh toán thành công và cập nhật trạng thái.
- Upload file và xử lý bất đồng bộ.
- Người dùng chỉ đọc được dữ liệu của tenant mình.
- Hoàn tất workflow có nhiều bước và rollback khi lỗi.

Không cần kiểm tra mọi tổ hợp đầu vào qua E2E nếu unit/integration test đã bao phủ. Giữ số lượng E2E vừa phải để giảm thời gian và flaky test.

### 9.2. Test qua endpoint đã deploy

E2E test nên đi qua đường giao tiếp giống người dùng hoặc client thực:

1. Lấy token test từ identity provider hoặc fixture an toàn.
2. Gửi request qua API Gateway/ALB/custom domain.
3. Theo dõi trạng thái qua API hoặc event/result store.
4. Xác minh dữ liệu và side effect.
5. Kiểm tra quyền truy cập.
6. Dọn dữ liệu test.

Không gọi trực tiếp Lambda function nếu mục tiêu là kiểm thử API Gateway, authorizer, routing và integration mapping.

### 9.3. Correlation ID

Gắn testRunId hoặc correlationId vào request và truyền qua log/event. Khi E2E test thất bại, có thể tìm log từ API Gateway, Lambda, SQS, EventBridge và consumer bằng cùng ID.

Không dùng correlation ID làm credential hoặc đưa dữ liệu cá nhân vào đó.

### 9.4. Polling thay vì sleep

Luồng bất đồng bộ cần chờ trạng thái hoàn tất. Dùng polling với:

- Timeout tổng.
- Khoảng chờ tăng dần hoặc interval phù hợp.
- Điều kiện thành công cụ thể.
- Điều kiện thất bại sớm.
- Diagnostic khi hết timeout.

Ví dụ: chờ order status chuyển từ PENDING sang PAID hoặc FAILED. Nếu hết timeout, báo testRunId, query execution ID hoặc message ID để điều tra.

### 9.5. Test tính idempotent

Gửi cùng một request hai lần với cùng idempotency key. Kết quả mong đợi là một giao dịch nghiệp vụ duy nhất, dù client không nhận được response lần đầu và retry.

Kiểm tra:

- Database chỉ có một record nghiệp vụ.
- Event downstream không tạo side effect trùng hoặc consumer deduplicate được.
- Response lần retry nhất quán với giao dịch ban đầu.
- Idempotency key có TTL/retention phù hợp.

## 10. Infrastructure as Code testing

### 10.1. Vì sao cần kiểm thử IaC?

Ứng dụng có thể đúng nhưng hạ tầng triển khai sai: bucket public, Lambda role quá rộng, SQS visibility timeout thấp hơn thời gian xử lý, security group mở inbound rộng hoặc API không bật access log.

IaC test giúp phát hiện lỗi cấu hình trước khi deploy.

### 10.2. AWS CDK assertions

AWS CDK hỗ trợ synthesize CloudFormation template và assertions để kiểm tra resource được tạo đúng. Có thể xác minh:

- Lambda runtime, timeout và memory.
- IAM policy action/resource.
- S3 Block Public Access và encryption.
- SQS DLQ và redrive policy.
- DynamoDB encryption và point-in-time recovery.
- API Gateway logging/throttling.

Ví dụ TypeScript minh họa:

~~~typescript
import { Template } from "aws-cdk-lib/assertions";
import { App, Stack } from "aws-cdk-lib";
import * as s3 from "aws-cdk-lib/aws-s3";

test("data bucket blocks public access", () => {
  const app = new App();
  const stack = new Stack(app);

  new s3.Bucket(stack, "DataBucket", {
    blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    enforceSSL: true,
  });

  const template = Template.fromStack(stack);
  template.hasResourceProperties("AWS::S3::Bucket", {
    PublicAccessBlockConfiguration: {
      BlockPublicAcls: true,
      BlockPublicPolicy: true,
      IgnorePublicAcls: true,
      RestrictPublicBuckets: true,
    },
  });
});
~~~

Đây là ví dụ kiểm tra template đã synthesize. Nó không chứng minh bucket được deploy đúng hoặc policy ở cấp account không làm thay đổi kết quả; cần thêm kiểm tra sau deploy.

### 10.3. CloudFormation validation

Trong CI có thể:

- Validate template syntax.
- Lint CloudFormation.
- Kiểm tra drift hoặc change set theo quy trình.
- Dùng CloudFormation Guard để áp dụng rule về cấu hình.
- Kiểm tra dependency và parameter.

CloudFormation Guard giúp kiểm tra template theo policy như encryption, public access hoặc network configuration. Nó không thay thế security review và runtime test.

### 10.4. Kiểm tra sau triển khai

Sau khi deploy:

- Xác minh resource tồn tại và đúng configuration.
- Kiểm tra IAM role assume được và operation cần thiết hoạt động.
- Kiểm tra log group, alarm và dashboard.
- Kiểm tra S3 public access và encryption.
- Kiểm tra security group/routing.
- Kiểm tra service integration.

IaC unit test và post-deployment integration test cần đi cùng nhau.

## 11. Kiểm thử bảo mật

### 11.1. IAM positive và negative tests

Không chỉ kiểm tra role có thể thực hiện hành động cần thiết. Cần kiểm tra role không thể truy cập resource ngoài phạm vi.

Ví dụ:

| Principal | Hành động | Kết quả mong đợi |
|---|---|---|
| Order Lambda role | PutItem vào orders table | Allow |
| Order Lambda role | Scan bảng payroll | Deny |
| Analyst role | Query curated dataset được cấp | Allow |
| Analyst role | Đọc raw PII prefix | Deny |
| Unauthenticated user | Gọi API yêu cầu đăng nhập | Deny |

Kiểm tra permission thật trong test account bằng role tương đương production. IAM policy simulator có thể hỗ trợ phân tích policy nhưng không thay thế kiểm thử end-to-end với resource policy, SCP, permission boundary và KMS key policy thực tế.

### 11.2. Kiểm thử authentication và authorization

Các case nên có:

- Token hợp lệ.
- Token hết hạn.
- Token sai issuer/audience.
- Người dùng không thuộc tenant.
- Người dùng có role nhưng thiếu permission trên resource.
- Request giả mạo tenant ID.
- Truy cập trực tiếp object URL hoặc endpoint.

Kiểm tra cả response và side effect. Request bị từ chối không được tạo record, gửi event hoặc để lộ dữ liệu trong error message.

### 11.3. Dependency và vulnerability scanning

CI có thể quét dependency, container image, IaC và secret. Amazon Inspector hỗ trợ phát hiện lỗ hổng cho các tài nguyên được hỗ trợ; Amazon ECR enhanced scanning tích hợp với Inspector cho container image theo cấu hình. Các công cụ khác có thể bổ sung SAST, DAST và license checks.

Kết quả scan cần có severity, exploitability, owner và thời hạn xử lý. Không tự động coi mọi finding là cùng mức độ rủi ro; cần đánh giá runtime exposure và khả năng khai thác.

### 11.4. Kiểm thử dữ liệu và privacy

- Dùng synthetic hoặc masked data.
- Không sao chép PII production vào môi trường test nếu không có phê duyệt.
- Giới hạn quyền truy cập test artifacts.
- Dọn dữ liệu sau test.
- Kiểm tra log không chứa token, secret hoặc dữ liệu nhạy cảm.
- Xác minh encryption at rest và in transit.

## 12. Performance và load testing

### 12.1. Mục tiêu

Performance test đo latency, throughput, concurrency, error rate và mức sử dụng tài nguyên. Load test xác minh hệ thống đáp ứng tải dự kiến; stress test tìm giới hạn; spike test đánh giá tải tăng đột ngột; soak test tìm memory leak hoặc suy giảm sau thời gian dài.

### 12.2. Thiết kế workload

Xác định:

- Request per second hoặc message per second.
- Tỷ lệ read/write.
- Kích thước payload.
- Phân bố request và burst.
- Concurrency.
- Thời gian chạy.
- Tỷ lệ lỗi chấp nhận được.
- p50, p95 và p99 latency mục tiêu.

Dùng dữ liệu đại diện và hành vi gần thực tế. Test chỉ gửi một endpoint đơn giản có thể không phản ánh workload thật nếu production có join, fan-out hoặc downstream call.

### 12.3. Công cụ trên AWS

Có thể dùng:

- Distributed Load Testing on AWS solution để tạo và điều phối load generator theo kiến trúc mẫu.
- AWS CodeBuild hoặc compute riêng để chạy k6, JMeter hoặc công cụ phù hợp.
- CloudWatch để theo dõi metric dịch vụ.
- X-Ray/OpenTelemetry để tìm bottleneck xuyên request.
- AWS Lambda Power Tuning cho một số workload Lambda để so sánh cấu hình memory/latency/cost.

Distributed Load Testing on AWS là solution triển khai trên AWS, không phải một service miễn phí mặc định. Cần tính chi phí load generator, network, log và dịch vụ bị kiểm thử.

### 12.4. Theo dõi giới hạn dịch vụ

Load test có thể chạm quota hoặc service quota trước khi ứng dụng đạt giới hạn thực. Theo dõi:

- Lambda concurrency và throttles.
- API Gateway throttling.
- DynamoDB throttled requests và consumed capacity.
- SQS queue depth và age of oldest message.
- Kinesis shard/throughput limits.
- RDS connection count và CPU.
- NAT Gateway/egress và network bottleneck.

Phân biệt giới hạn ứng dụng, giới hạn dịch vụ và giới hạn load generator. Nếu test environment có quota thấp hơn production, kết quả cần được diễn giải theo bối cảnh.

### 12.5. An toàn khi load test

- Chỉ test account và endpoint đã được xác định.
- Đặt ngân sách và thời lượng.
- Dùng ramp-up và ramp-down có kiểm soát.
- Có kill switch và người trực theo dõi.
- Không tạo tải lên dịch vụ bên thứ ba nếu chưa được phép.
- Không chạy stress test trên production nếu chưa có kế hoạch và phê duyệt.
- Xác minh cleanup sau khi test.

## 13. Resilience, chaos và disaster recovery testing

### 13.1. Resilience test

Kiểm tra hệ thống khi dependency chậm hoặc lỗi:

- Database connection timeout.
- SQS consumer bị dừng.
- Lambda throttling.
- External API trả 5xx.
- DNS hoặc network bị gián đoạn.
- KMS hoặc secret access thất bại.
- Một Availability Zone không khả dụng theo kịch bản thử nghiệm.

Xác minh retry, circuit breaker, timeout, fallback, DLQ, backpressure và alert hoạt động đúng.

### 13.2. AWS Fault Injection Service

AWS Fault Injection Service (FIS) giúp chạy fault injection experiment có kiểm soát trên tài nguyên AWS được hỗ trợ. Có thể dùng để thử các kịch bản như tăng độ trễ, làm gián đoạn network hoặc dừng tài nguyên theo action được dịch vụ hỗ trợ.

Một experiment cần:

1. Xác định giả thuyết và mục tiêu.
2. Chọn resource target rõ ràng.
3. Đặt IAM role và permission tối thiểu.
4. Cấu hình stop condition và CloudWatch alarm.
5. Thông báo người vận hành và giới hạn blast radius.
6. Chạy trong môi trường phù hợp.
7. Quan sát tác động và dừng khi vượt ngưỡng.
8. Ghi lại kết quả, sửa hệ thống và chạy lại.

Không chạy fault injection tùy tiện trên production. Bắt đầu ở test/staging và chỉ mở rộng khi có kế hoạch kiểm soát rủi ro được phê duyệt.

### 13.3. Backup và restore test

Backup job thành công không chứng minh có thể phục hồi. Restore test cần:

- Khôi phục snapshot hoặc backup vào môi trường riêng.
- Kiểm tra schema và dữ liệu.
- Xác minh ứng dụng kết nối được.
- Kiểm tra quyền và KMS key.
- Đo thời gian phục hồi.
- Đối chiếu dữ liệu với RPO.
- Chạy smoke test nghiệp vụ sau restore.

### 13.4. RPO và RTO

- RPO (Recovery Point Objective): lượng dữ liệu tối đa có thể mất tính theo thời gian.
- RTO (Recovery Time Objective): thời gian mục tiêu để khôi phục dịch vụ.

Test DR cần đo RPO/RTO thực tế. Ví dụ, nếu RTO mục tiêu là 60 phút nhưng restore database và cập nhật endpoint mất 3 giờ, kiến trúc chưa đáp ứng yêu cầu.

### 13.5. Failover test

Kiểm tra chuyển đổi sang database replica, Region dự phòng hoặc queue/consumer dự phòng nếu kiến trúc có các thành phần đó. Xác minh:

- DNS/endpoint và client reconnect.
- Không có split-brain hoặc ghi đồng thời ngoài ý muốn.
- Secret, certificate và KMS key khả dụng.
- Event backlog được xử lý.
- Dữ liệu nhất quán sau failover.
- Quy trình failback có thể thực hiện.

## 14. CI/CD và tự động hóa kiểm thử

### 14.1. Pipeline tham khảo

Một pipeline có thể chia thành các stage:

~~~mermaid
flowchart LR
    A[Commit / Pull request] --> B[Lint + SAST + dependency scan]
    B --> C[Unit tests]
    C --> D[Build artifact + IaC synth]
    D --> E[Template / policy tests]
    E --> F[Deploy ephemeral test stack]
    F --> G[Integration + contract tests]
    G --> H[E2E + smoke tests]
    H --> I[Deploy staging]
    I --> J[Performance / security / resilience checks]
    J --> K[Approval / release]
    K --> L[Canary or rolling deployment]
    L --> M[Production smoke + monitoring]
    M --> N[Promote or rollback]
~~~

Không nhất thiết mọi commit đều chạy full performance hoặc chaos test. Có thể chạy unit và IaC test mỗi pull request, integration/E2E trên branch chính, còn load/chaos/DR theo lịch hoặc trước release lớn.

### 14.2. AWS CodeBuild

CodeBuild chạy build/test command trong build environment. Có thể dùng buildspec để:

- Cài dependency.
- Chạy lint và unit test.
- Build Lambda/container artifact.
- Synth CloudFormation từ CDK.
- Chạy contract/integration test.
- Tạo report và lưu artifact.

Ví dụ buildspec rút gọn:

~~~yaml
version: 0.2
phases:
  install:
    runtime-versions:
      python: 3.12
    commands:
      - pip install -r requirements-dev.txt
  build:
    commands:
      - python -m pytest tests/unit --junitxml=reports/unit.xml
      - sam build
reports:
  unit-tests:
    files:
      - reports/unit.xml
    file-format: JUNITXML
~~~

Phiên bản runtime phải được CodeBuild image hỗ trợ. Ví dụ chỉ minh họa cấu trúc; project cần pin dependency và tạo thư mục report trước khi ghi file.

### 14.3. AWS CodePipeline

CodePipeline điều phối source, build, test, approval và deployment action. Có thể dùng CodeBuild action cho unit/integration test, CloudFormation action cho deploy stack và manual approval trước production nếu quy trình yêu cầu.

Pipeline nên lưu artifact và report theo build ID để điều tra. Không để một stage test dùng credential rộng hơn stage deploy cần thiết.

### 14.4. GitHub Actions hoặc hệ thống CI khác

AWS không bắt buộc phải dùng CodePipeline. GitHub Actions, Jenkins hoặc CI platform khác có thể triển khai lên AWS bằng OpenID Connect (OIDC) để nhận temporary credentials qua IAM role. Ưu tiên federation và role ngắn hạn thay vì access key dài hạn lưu trong CI secret.

### 14.5. Quality gate

Quality gate có thể yêu cầu:

- Unit test pass.
- Integration test critical pass.
- IaC security checks pass.
- Không có secret trong artifact.
- Coverage đạt ngưỡng phù hợp với code quan trọng.
- Không có vulnerability mức nghiêm trọng chưa được xử lý.
- E2E smoke test pass.
- Deployment alarm ở trạng thái tốt.

Coverage chỉ là một chỉ số. 95% line coverage không chứng minh test có assertion đúng hoặc kiểm tra được hành vi quan trọng.

### 14.6. Cleanup và artifact retention

CI cần:

- Xóa ephemeral stack sau test.
- Dọn object, queue message và dữ liệu test.
- Lưu report/log đủ lâu để điều tra.
- Có scheduled cleanup cho stack mồ côi.
- Theo dõi chi phí của test environment.
- Không xóa artifact hoặc log cần cho audit trước thời hạn.

## 15. Kiểm thử sau triển khai và production validation

### 15.1. Smoke test

Smoke test là tập kiểm tra ngắn sau deploy để xác minh hệ thống sẵn sàng. Ví dụ:

- API health endpoint trả kết quả thành công.
- Authentication hoạt động.
- Có thể tạo và đọc một resource test.
- Queue consumer nhận được một message mẫu.
- Database connection và migration hợp lệ.

Smoke test cần ít side effect và có cleanup. Không dùng test tạo giao dịch thật hoặc gửi thông báo tới khách hàng thật.

### 15.2. CloudWatch Synthetics

CloudWatch Synthetics dùng canary để chạy script kiểm tra endpoint hoặc hành trình người dùng theo lịch. Canary có thể xác minh API response, TLS, DNS hoặc workflow đơn giản và gửi metric/alarm khi thất bại.

Canary nên dùng tài khoản test, dữ liệu riêng và secret được bảo vệ. Nếu canary chạy trên production endpoint, phải thiết kế request không gây side effect và không truy cập dữ liệu người dùng thật.

### 15.3. Deployment strategies

Các chiến lược phổ biến:

- Rolling deployment: thay dần instance/task.
- Blue/green: triển khai môi trường mới rồi chuyển traffic.
- Canary: chuyển một phần traffic và quan sát trước khi mở rộng.
- Linear: tăng traffic theo từng bước.

AWS CodeDeploy hỗ trợ deployment pattern cho các compute target được tích hợp, như Lambda và ECS blue/green. Chọn chiến lược theo khả năng rollback, schema compatibility và thời gian khởi động.

### 15.4. Automated rollback

Rollback có thể được kích hoạt khi alarm hoặc deployment health check thất bại. Cần định nghĩa:

- Metric/error threshold.
- Thời gian quan sát.
- Điều kiện rollback.
- Phiên bản artifact quay lại.
- Cách xử lý database migration không tương thích ngược.
- Cách xử lý message đã được consumer phiên bản mới tạo.

Rollback code không tự động rollback dữ liệu hoặc schema. Dùng expand-and-contract migration để phiên bản cũ và mới có thể cùng hoạt động trong thời gian chuyển đổi.

## 16. Observability và troubleshooting test failures

### 16.1. Log có cấu trúc

Log nên có các trường:

- timestamp.
- level.
- service/function name.
- environment.
- requestId hoặc correlationId.
- testRunId/buildId.
- operation.
- outcome/errorCode.
- duration.

Không log secret, token, private key hoặc toàn bộ payload nhạy cảm. Dùng redaction và giới hạn quyền đọc log.

### 16.2. CloudWatch

CloudWatch Logs, Metrics, Alarms và Dashboards giúp theo dõi:

- Lambda errors, duration, throttles và concurrency.
- API Gateway 4xx/5xx và latency.
- SQS queue depth và age of oldest message.
- DynamoDB throttling và consumed capacity.
- RDS CPU, connections, storage và failover events.
- Step Functions execution failures.
- Custom business metrics.

Test failure cần liên kết với metric/log ở đúng khoảng thời gian. Dùng testRunId để tìm các request liên quan.

### 16.3. AWS X-Ray và distributed tracing

AWS X-Ray hoặc OpenTelemetry có thể theo dõi request qua nhiều service. Trace giúp xác định latency nằm ở API, Lambda, database, downstream HTTP call hay queue processing.

Để trace hữu ích:

- Propagate trace/correlation context.
- Bật instrumentation cho service phù hợp.
- Không tạo cardinality quá cao ở metric dimension.
- Giữ trace sampling phù hợp với tải.
- Bảo vệ trace nếu metadata có thông tin nhạy cảm.

### 16.4. CloudTrail

CloudTrail ghi nhận hoạt động API control plane và các data event được cấu hình. Khi test hoặc deploy thất bại vì permission, CloudTrail có thể giúp xác định principal đã gọi API nào và lỗi authorization ra sao.

Không phải mọi data event đều được bật mặc định; cần cấu hình loại event và resource cần audit. Logging quá rộng có thể tăng chi phí.

### 16.5. Phân loại test failure

| Loại lỗi | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Product defect | Assertion sai ổn định | Sửa code hoặc yêu cầu |
| Environment defect | Endpoint/resource thiếu hoặc sai config | Sửa IaC/test environment |
| Permission defect | AccessDenied hoặc KMS denied | Kiểm tra role, policy, boundary, SCP |
| Flaky test | Lúc pass lúc fail không theo code | Loại race, sleep cố định, dữ liệu dùng chung |
| Quota/throttling | Throttled hoặc rate exceeded | Điều tiết tải, kiểm tra quota |
| Test data defect | Fixture không hợp lệ hoặc stale | Tạo data setup có version |
| External dependency | API bên ngoài lỗi | Mock ở unit, contract hoặc test sandbox riêng |

Không retry vô hạn để biến test flaky thành pass. Ghi nhận retry count và giữ lại failure đầu tiên để điều tra.

## 17. Quản lý dữ liệu kiểm thử

### 17.1. Synthetic data

Synthetic data được tạo cho test, không chứa thông tin thật của người dùng. Có thể tạo:

- Khách hàng giả.
- Đơn hàng với trạng thái và giá trị biên.
- Tài liệu mẫu.
- Event theo schema.
- Dữ liệu lớn để load test.

Synthetic data giúp tái lập và tránh rủi ro privacy. Cần đảm bảo dữ liệu đủ giống phân bố production để test performance và edge case có ý nghĩa.

### 17.2. Masking production data

Nếu cần dữ liệu production để tái tạo lỗi, dùng quy trình được phê duyệt, giảm trường dữ liệu, mask hoặc tokenize PII, giới hạn account, mã hóa và đặt retention ngắn. Không sao chép production snapshot vào laptop hoặc shared test account mà không kiểm soát.

### 17.3. Data isolation

Mỗi test run nên có namespace hoặc key riêng. Ví dụ:

~~~text
test-run-8f31/orders/order-001
test-run-8f31/events/order-created
test-run-8f31/uploads/input.csv
~~~

Dùng run ID để phân biệt dữ liệu và tránh test cleanup xóa tài nguyên của run khác.

### 17.4. Cleanup và TTL

Thiết lập TTL/lifecycle cho dữ liệu tạm khi phù hợp. Tuy nhiên, TTL không phải cleanup tức thời; DynamoDB TTL xóa item theo cơ chế nền. Với test cần dọn ngay, gọi delete rõ ràng và xác minh kết quả.

## 18. Ví dụ chiến lược kiểm thử: Order API trên AWS

### 18.1. Kiến trúc

Một ứng dụng order service có:

- API Gateway nhận request.
- Lambda xử lý tạo đơn.
- DynamoDB lưu order.
- EventBridge phát OrderCreated.
- SQS nhận event cho consumer.
- Lambda consumer cập nhật trạng thái xử lý.
- CloudWatch ghi log và metric.

~~~mermaid
flowchart LR
    U[Client] --> A[API Gateway]
    A --> L[Create Order Lambda]
    L --> D[(DynamoDB)]
    L --> E[EventBridge]
    E --> Q[SQS]
    Q --> C[Consumer Lambda]
    C --> D
    A -. logs/metrics .-> O[CloudWatch]
    L -. traces .-> X[X-Ray]
    C -. traces .-> X
~~~

### 18.2. Unit tests

- Tính tổng tiền và thuế.
- Validate item quantity, currency và địa chỉ.
- Kiểm tra idempotency key.
- Xác định trạng thái order hợp lệ.
- Map lỗi domain sang HTTP response.
- Xử lý event schema.

Mock repository và event publisher ở boundary để test logic độc lập.

### 18.3. Integration tests

- Deploy stack test riêng.
- Gọi Create Order Lambda hoặc API thật.
- Xác minh record được ghi vào DynamoDB test table.
- Kiểm tra EventBridge rule match OrderCreated.
- Xác minh message đến SQS.
- Invoke consumer qua event source mapping hoặc gửi message theo test flow.
- Kiểm tra trạng thái cuối và DLQ khi consumer thất bại.
- Chạy role negative test để xác minh không truy cập bảng ngoài phạm vi.

### 18.4. E2E tests

- Gửi request qua API Gateway với token hợp lệ.
- Poll API đến khi order ở trạng thái cuối.
- Xác minh order chỉ được tạo một lần khi retry cùng idempotency key.
- Gọi API bằng user tenant khác và xác minh không đọc được order.
- Gửi request sai schema và xác minh không phát event.

### 18.5. Non-functional tests

- Load test tạo order theo tải dự kiến.
- Kiểm tra p95/p99 latency và throttling.
- Dừng consumer trong thời gian ngắn, quan sát queue backlog và recovery.
- Kiểm thử DLQ và replay.
- Restore DynamoDB backup vào môi trường riêng và chạy smoke test.
- Theo dõi cost per order trong test run.

## 19. Các lỗi thường gặp khi xây dựng test strategy

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ viết unit test | Bỏ sót IAM, network và service integration | Bổ sung integration test trên AWS |
| Chỉ viết E2E test | Pipeline chậm, lỗi khó định vị | Tăng unit và contract test |
| Mock mọi AWS service | Test không phát hiện sai policy hoặc event mapping | Kiểm thử một số luồng bằng service thật |
| Dùng production data trong test | Rủi ro privacy và phá dữ liệu | Synthetic/masked data và account riêng |
| Dùng chung resource cho nhiều test | Race condition và test flaky | Namespace theo run hoặc ephemeral stack |
| Sleep cố định để chờ event | Test không ổn định | Polling theo điều kiện và timeout |
| Không test negative permission | Quyền quá rộng không bị phát hiện | Thêm IAM deny/authorization tests |
| Chỉ kiểm tra deploy thành công | Ứng dụng có thể không hoạt động | Smoke test và canary validation |
| Không test retry/duplicate | Tạo side effect nhiều lần | Idempotency và failure injection |
| Không cleanup | Tài nguyên và chi phí tích lũy | Teardown và orphan cleanup |
| Coverage là mục tiêu duy nhất | Test nhiều nhưng không bảo vệ hành vi | Ưu tiên risk và assertion có ý nghĩa |
| Chaos test không có stop condition | Có thể gây gián đoạn ngoài dự kiến | Giới hạn blast radius và alarm |

## 20. Checklist chiến lược kiểm thử trên AWS

### Thiết kế

1. Xác định luồng nghiệp vụ, yêu cầu và rủi ro.
2. Phân loại unit, component, contract, integration và E2E tests.
3. Xác định AWS services và ranh giới cần kiểm tra thật.
4. Định nghĩa test data, account, environment và cleanup.
5. Xác định tiêu chí pass/fail và quality gate.

### Triển khai

1. Tách domain logic khỏi AWS adapters.
2. Viết unit test cho happy path, boundary và failure path.
3. Test IaC và IAM policy.
4. Tạo test environment cô lập.
5. Chạy integration test với AWS resources thật cho các luồng trọng yếu.
6. Chạy E2E qua endpoint đã deploy.
7. Thu thập log, metric, trace và test report.

### Trước release

1. Kiểm tra performance và quota.
2. Kiểm tra authorization và dữ liệu nhạy cảm.
3. Kiểm tra retry, DLQ và idempotency.
4. Kiểm tra backup/restore và failover theo yêu cầu.
5. Chạy smoke test trên staging.
6. Xác định rollback condition và người chịu trách nhiệm.

### Sau release

1. Chạy smoke test an toàn.
2. Theo dõi canary và CloudWatch alarms.
3. Quan sát error rate, latency và business metrics.
4. Rollback nếu vượt ngưỡng đã định.
5. Lưu test report và deployment traceability.
6. Dọn test data/resource đúng retention.

## 21. Kết luận

Chiến lược kiểm thử trên AWS cần kết hợp unit, component, contract, integration và end-to-end test. Unit test xác minh logic nhanh; integration test kiểm tra service boundary, IAM, network và event behavior; E2E test chứng minh luồng nghiệp vụ hoạt động qua các thành phần đã triển khai. Các lớp non-functional bổ sung bằng chứng về hiệu năng, bảo mật, khả năng chịu lỗi và phục hồi.

AWS SAM CLI và CDK hỗ trợ vòng lặp phát triển, CodeBuild và CodePipeline tự động hóa CI/CD, CloudFormation giúp quản lý hạ tầng, còn CloudWatch, X-Ray và CloudTrail hỗ trợ điều tra. Test account, ephemeral environment, synthetic data và cleanup giúp giảm rủi ro cũng như chi phí. Sau deployment, smoke test, canary và production monitoring tiếp tục xác minh release trong điều kiện thực tế.

Một test strategy tốt bắt đầu từ yêu cầu và rủi ro, chọn đúng lớp kiểm thử cho từng hành vi, kiểm tra cả trường hợp được phép và bị từ chối, đồng thời giữ kết quả có thể tái lập. Khi pipeline có quality gate rõ ràng, dữ liệu test an toàn và observability đủ tốt, nhóm có thể phát hành thay đổi trên AWS với độ tin cậy cao hơn.

## 22. Tài liệu tham khảo chính thức

- [AWS Well-Architected Framework – Testing](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_testing.html)
- [AWS Serverless Application Model – Testing and debugging](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli.html)
- [AWS CDK – Testing constructs](https://docs.aws.amazon.com/cdk/v2/guide/testing.html)
- [AWS CodeBuild](https://docs.aws.amazon.com/codebuild/latest/userguide/welcome.html)
- [AWS CodePipeline](https://docs.aws.amazon.com/codepipeline/latest/userguide/welcome.html)
- [AWS CloudFormation Guard](https://docs.aws.amazon.com/cfn-guard/latest/ug/what-is-guard.html)
- [CloudWatch Synthetics](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Synthetics_Canaries.html)
- [AWS X-Ray](https://docs.aws.amazon.com/xray/latest/devguide/aws-xray.html)
- [AWS Fault Injection Service](https://docs.aws.amazon.com/fis/latest/userguide/what-is.html)
- [Distributed Load Testing on AWS](https://docs.aws.amazon.com/solutions/latest/distributed-load-testing-on-aws/solution-overview.html)
- [AWS IAM policy simulator](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_testing-policies.html)
- [AWS CodeDeploy deployment configurations](https://docs.aws.amazon.com/codedeploy/latest/userguide/deployment-configurations.html)
