# Xây dựng hạ tầng AWS bằng AWS CDK với Java

## 1. Infrastructure as Code và AWS CDK

Infrastructure as Code (IaC) là cách mô tả hạ tầng bằng mã nguồn để có thể kiểm tra, tái sử dụng, review và triển khai lặp lại. Thay vì tạo Lambda, API Gateway, SQS, IAM role và database bằng thao tác thủ công trên Console, nhóm phát triển định nghĩa các tài nguyên trong repository. Pipeline có thể kiểm tra thay đổi, tạo bản kế hoạch và triển khai cùng một cấu hình qua nhiều môi trường.

AWS Cloud Development Kit (AWS CDK) là framework IaC cho phép mô tả hạ tầng bằng ngôn ngữ lập trình. Với Java, người phát triển dùng class, object, method và type safety để tạo các construct. CDK tổng hợp mã Java thành CloudFormation templates; CloudFormation chịu trách nhiệm tạo, cập nhật và quản lý vòng đời tài nguyên AWS.

Trong module CLOUD_SERVERLESS, CDK giúp mô hình hóa các thành phần thường đi cùng Java function:

- AWS Lambda cho HTTP, queue và event trigger.
- API Gateway để tiếp nhận HTTP request.
- SQS và dead-letter queue để đệm công việc, retry và cách ly message lỗi.
- EventBridge để định tuyến sự kiện.
- DynamoDB hoặc các dịch vụ lưu trữ khác để giữ trạng thái bền vững.
- IAM role/policy để cấp quyền tối thiểu.
- CloudWatch Logs, metrics và tracing để quan sát hoạt động.
- VPC, subnet, security group và endpoint khi function cần mạng riêng.

CDK không thay thế kiến thức về dịch vụ AWS. Mã CDK chỉ mô tả cấu hình mong muốn; người thiết kế vẫn phải hiểu timeout, concurrency, retry, idempotency, retention, quyền truy cập và chi phí của từng dịch vụ.

## 2. Các khái niệm cốt lõi: App, Stack và Construct

CDK tổ chức mã theo ba khái niệm chính:

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| `App` | Điểm bắt đầu của ứng dụng CDK; chứa một hoặc nhiều stack | Ứng dụng triển khai toàn bộ nền tảng đơn hàng |
| `Stack` | Đơn vị triển khai CloudFormation trong một account/region | Stack `OrdersServerlessStack` |
| `Construct` | Thành phần mô tả một hoặc nhiều tài nguyên và hành vi | Lambda function, queue, API hoặc construct tự xây dựng |

Một construct có thể đại diện cho một CloudFormation resource hoặc gom nhiều resource thành một thành phần cấp cao. Ví dụ `Function` tạo Lambda function cùng các cấu hình liên quan; `LambdaRestApi` tạo API Gateway và quyền cho API gọi function. Construct tự xây dựng giúp đóng gói quy ước của tổ chức, chẳng hạn mọi Lambda đều có timeout, tracing, log retention và tags chuẩn.

CDK có ba cấp construct thường được nhắc đến:

- **L1 (Cfn*):** ánh xạ gần như trực tiếp tới CloudFormation resource, ví dụ `CfnFunction`. Dùng khi cần thuộc tính CloudFormation chưa được abstraction cấp cao hỗ trợ.
- **L2:** construct có API hướng đối tượng, default hợp lý và helper cấp quyền, ví dụ `Function`, `Queue`, `Table`.
- **L3 (pattern):** kết hợp nhiều construct thành một kiến trúc hoàn chỉnh, ví dụ `LambdaRestApi` hoặc pattern xử lý event.

Ưu tiên L2/L3 khi đáp ứng yêu cầu để giảm mã cấu hình. Dùng L1 khi cần kiểm soát chi tiết hoặc tính năng mới chưa được L2/L3 hỗ trợ. Không nên hạ xuống L1 chỉ để tránh tìm hiểu API của construct cấp cao.

## 3. Chuẩn bị môi trường Java và AWS CDK

Một máy phát triển thường cần:

- JDK tương thích với phiên bản CDK project và runtime Lambda dự kiến; ví dụ JDK 21 cho ứng dụng Java 21.
- Apache Maven hoặc Gradle để build mã Java.
- Node.js và npm để cài AWS CDK CLI.
- AWS CLI để xác thực và kiểm tra account.
- AWS CDK Toolkit (`cdk`) để synth, diff, bootstrap và deploy.
- Quyền AWS phù hợp cho môi trường phát triển và triển khai.

Cài CDK CLI bằng npm:

```bash
npm install -g aws-cdk
cdk --version
```

Tạo một ứng dụng Java mới:

```bash
mkdir orders-infrastructure
cd orders-infrastructure
cdk init app --language java
```

Lệnh khởi tạo tạo cấu trúc Maven, class ứng dụng, stack mẫu, cấu hình CDK và test mẫu. Nếu repository đã có dự án Maven, có thể tích hợp CDK vào module riêng thay vì khởi tạo một project lồng nhau.

Đăng nhập AWS bằng cơ chế phù hợp với tổ chức, ví dụ AWS IAM Identity Center:

```bash
aws configure sso
aws sso login --profile dev
aws sts get-caller-identity --profile dev
```

Không commit access key, secret key hoặc session token vào `pom.xml`, `cdk.json`, `context.json` hay source code. Dùng profile, credential process hoặc cơ chế identity của CI/CD.

## 4. Cấu trúc project CDK Java

Một project Maven do `cdk init app --language java` tạo thường có cấu trúc gần như sau:

```text
orders-infrastructure/
├── cdk.json
├── pom.xml
├── README.md
├── src/
│   ├── main/java/com/example/
│   │   ├── MyApp.java
│   │   └── OrdersServerlessStack.java
│   └── test/java/com/example/
│       └── OrdersServerlessStackTest.java
└── target/
```

Các file quan trọng:

- `cdk.json`: cấu hình cách CDK CLI chạy ứng dụng CDK và context mặc định.
- `pom.xml`: dependency của AWS CDK, constructs và plugin Maven.
- `MyApp.java`: tạo `App`, khởi tạo stack và gọi `synth()`.
- `OrdersServerlessStack.java`: mô tả các tài nguyên AWS.
- `src/test`: kiểm tra template được sinh ra có resource và thuộc tính mong đợi.

`cdk.json` do template Java tạo thường dùng một lệnh Maven tương tự:

```json
{
  "app": "mvn -e -q compile exec:java"
}
```

Giữ cấu hình được sinh bởi đúng phiên bản template nếu đã có plugin hoặc tham số bổ sung. Khi CDK CLI chạy `synth`, nó thực thi ứng dụng Java để tạo Cloud Assembly.

## 5. Dependency và phiên bản CDK

AWS CDK v2 gom các module dịch vụ vào artifact `aws-cdk-lib`; construct interface nằm trong artifact `constructs`. Project Maven thường có dependency tương tự:

```xml
<dependencies>
    <dependency>
        <groupId>software.amazon.awscdk</groupId>
        <artifactId>aws-cdk-lib</artifactId>
        <version>${cdk.version}</version>
    </dependency>
    <dependency>
        <groupId>software.constructs</groupId>
        <artifactId>constructs</artifactId>
        <version>${constructs.version}</version>
    </dependency>
</dependencies>
```

Các property `${cdk.version}` và `${constructs.version}` cần được khai báo trong `pom.xml` bằng phiên bản tương thích. Dự án khởi tạo bằng CDK CLI đã sinh sẵn phiên bản phù hợp; nên cập nhật theo kế hoạch và kiểm tra release notes trước khi nâng cấp.

Không trộn API CDK v1 (`@aws-cdk/...`) với CDK v2 (`software.amazon.awscdk:aws-cdk-lib`). CDK v2 là lựa chọn cho project mới. Hãy khóa version trong build để các máy và pipeline synth cùng một template.

## 6. Tạo App và Stack bằng Java

Class entry point tạo `App`, khởi tạo stack rồi tổng hợp Cloud Assembly:

```java
package com.example;

import software.amazon.awscdk.App;
import software.amazon.awscdk.Environment;
import software.amazon.awscdk.StackProps;

public final class MyApp {
    public static void main(final String[] args) {
        App app = new App();

        Environment deploymentEnv = Environment.builder()
                .account(System.getenv("CDK_DEFAULT_ACCOUNT"))
                .region(System.getenv("CDK_DEFAULT_REGION"))
                .build();

        new OrdersServerlessStack(
                app,
                "OrdersServerlessStack",
                StackProps.builder().env(deploymentEnv).build());

        app.synth();
    }
}
```

`account` và `region` xác định môi trường triển khai. CDK cũng hỗ trợ stack environment-agnostic, nhưng một số tính năng cần biết account/region tại thời điểm synth. Với ứng dụng có nhiều môi trường, nên truyền environment rõ ràng từ pipeline hoặc cấu hình được quản lý.

Một stack kế thừa `Stack`:

```java
package com.example;

import software.amazon.awscdk.Stack;
import software.constructs.Construct;
import software.amazon.awscdk.StackProps;

public class OrdersServerlessStack extends Stack {
    public OrdersServerlessStack(
            final Construct scope,
            final String id,
            final StackProps props) {
        super(scope, id, props);

        // Khai báo resource và construct tại đây.
    }
}
```

ID của construct phải duy nhất trong scope cha. CDK dùng đường dẫn construct để tạo logical ID trong CloudFormation. Đổi cây construct hoặc ID có thể làm logical ID thay đổi và khiến CloudFormation xem resource cũ cần thay thế. Với database, queue hoặc bucket có dữ liệu, thay thế ngoài dự kiến có thể gây gián đoạn hoặc mất dữ liệu.

## 7. Mô hình hóa Lambda Java

CDK L2 `Function` mô tả Lambda runtime, handler, artifact, timeout, memory, architecture, environment và quyền thực thi. Ví dụ:

```java
import java.util.Map;

import software.amazon.awscdk.Duration;
import software.amazon.awscdk.services.lambda.Architecture;
import software.amazon.awscdk.services.lambda.Code;
import software.amazon.awscdk.services.lambda.Function;
import software.amazon.awscdk.services.lambda.Runtime;

Function orderApi = Function.Builder.create(this, "OrderApiFunction")
        .runtime(Runtime.JAVA_21)
        .architecture(Architecture.ARM_64)
        .handler("com.example.orders.ApiHandler::handleRequest")
        .code(Code.fromAsset("../orders-function/target/orders-function.jar"))
        .memorySize(1024)
        .timeout(Duration.seconds(15))
        .environment(Map.of(
                "APP_ENV", "dev",
                "LOG_LEVEL", "INFO"))
        .tracing(software.amazon.awscdk.services.lambda.Tracing.ACTIVE)
        .build();
```

Các giá trị trên chỉ là ví dụ ban đầu. Chọn runtime còn được AWS hỗ trợ, architecture phù hợp với native library và build artifact, memory/timeout theo số liệu đo. Java handler phải tồn tại trong JAR và tuân theo interface mà Lambda Java runtime mong đợi.

`Code.fromAsset` đóng gói file hoặc thư mục thành asset. Đường dẫn được phân giải từ working directory của CDK app khi synth. Vì vậy, pipeline cần build function trước khi chạy `cdk synth`; nếu JAR chưa tồn tại, CDK không thể đóng gói asset như mong muốn.

Nếu function cần biến môi trường chứa ARN hoặc tên tài nguyên, lấy giá trị từ construct như `table.getTableName()` hoặc `queue.getQueueUrl()` thay vì hardcode. CDK sẽ tạo CloudFormation reference và triển khai đúng giá trị theo stack.

## 8. Xây dựng API Gateway cho Lambda

Với REST API đơn giản, `LambdaRestApi` tạo API Gateway REST API và tích hợp Lambda:

```java
import software.amazon.awscdk.services.apigateway.LambdaRestApi;

LambdaRestApi api = LambdaRestApi.Builder.create(this, "OrdersApi")
        .handler(orderApi)
        .proxy(true)
        .build();
```

`proxy(true)` chuyển các path/method chưa khai báo riêng đến Lambda handler. Ứng dụng có thể định tuyến trong framework hoặc tự phân tích path. CDK tạo Lambda resource-based permission để API Gateway được phép invoke function.

Nếu chọn API Gateway HTTP API, dùng construct `HttpApi` và `HttpLambdaIntegration`:

```java
import software.amazon.awscdk.services.apigatewayv2.HttpApi;
import software.amazon.awscdk.aws_apigatewayv2_integrations.HttpLambdaIntegration;
import software.amazon.awscdk.services.apigatewayv2.AddRoutesOptions;
import software.amazon.awscdk.services.apigatewayv2.HttpMethod;
import java.util.List;

HttpApi httpApi = new HttpApi(this, "OrdersHttpApi");
HttpLambdaIntegration integration = new HttpLambdaIntegration(
        "OrdersIntegration", orderApi);

httpApi.addRoutes(AddRoutesOptions.builder()
        .path("/")
        .methods(List.of(HttpMethod.ANY))
        .integration(integration)
        .build());
httpApi.addRoutes(AddRoutesOptions.builder()
        .path("/{proxy+}")
        .methods(List.of(HttpMethod.ANY))
        .integration(integration)
        .build());
```

`LambdaRestApi` và `HttpApi` là hai loại API Gateway khác nhau. REST API có nhiều tính năng quản lý API hơn; HTTP API thường có cấu hình gọn và chi phí thấp hơn cho proxy/route đơn giản. Chọn theo yêu cầu về authorizer, mapping, validation, logging, throttling và giá.

Nếu cần REST API với method/model/authorizer cụ thể, có thể tạo `RestApi`, `Resource`, `Method` và `LambdaIntegration` riêng. Nếu ưu tiên chi phí và tính năng HTTP hiện đại, hãy so sánh API Gateway HTTP API với REST API trước khi chọn; hai loại có khả năng, logging, authorization và giá khác nhau.

Đối với endpoint production, cân nhắc:

- Authentication/authorization bằng JWT authorizer, Cognito hoặc Lambda authorizer.
- Throttling và quota để bảo vệ function/dependency.
- Access logging và request ID.
- CORS nếu browser gọi cross-origin.
- Custom domain, TLS certificate và DNS.
- Request validation và giới hạn payload.
- Timeout giữa API Gateway và Lambda.

Không dùng API Gateway như lớp duy nhất bảo vệ dữ liệu. Function vẫn cần xác thực quyền trên tài nguyên và tenant ở cấp nghiệp vụ.

## 9. Tạo SQS queue, DLQ và Lambda event source mapping

Queue giúp tách tốc độ nhận request khỏi tốc độ xử lý. Dead-letter queue giữ message sau nhiều lần xử lý thất bại.

```java
import software.amazon.awscdk.Duration;
import software.amazon.awscdk.services.sqs.DeadLetterQueue;
import software.amazon.awscdk.services.sqs.Queue;
import software.amazon.awscdk.services.lambda.eventsources.SqsEventSource;
import software.amazon.awscdk.services.lambda.eventsources.SqsEventSourceProps;

Queue ordersDlq = Queue.Builder.create(this, "OrdersDlq")
        .retentionPeriod(Duration.days(14))
        .build();

Queue ordersQueue = Queue.Builder.create(this, "OrdersQueue")
        .retentionPeriod(Duration.days(4))
        .visibilityTimeout(Duration.seconds(180))
        .deadLetterQueue(DeadLetterQueue.builder()
                .queue(ordersDlq)
                .maxReceiveCount(5)
                .build())
        .build();

Function orderWorker = Function.Builder.create(this, "OrderWorker")
        .runtime(Runtime.JAVA_21)
        .architecture(Architecture.ARM_64)
        .handler("com.example.orders.SqsHandler::handleRequest")
        .code(Code.fromAsset("../orders-function/target/orders-function.jar"))
        .memorySize(1024)
        .timeout(Duration.seconds(30))
        .build();

orderWorker.addEventSource(new SqsEventSource(
        ordersQueue,
        SqsEventSourceProps.builder()
                .batchSize(10)
                .reportBatchItemFailures(true)
                .build()));
```

Construct `SqsEventSource` tạo event source mapping và các quyền cần thiết để Lambda đọc queue. `reportBatchItemFailures(true)` bật partial batch response; handler cần trả về danh sách message thất bại theo đúng định dạng Lambda Events. Nếu handler ném exception cho toàn batch, cả batch vẫn có thể được giao lại.

Visibility timeout phải đủ dài cho thời gian function xử lý batch và retry. AWS khuyến nghị đặt visibility timeout của queue ít nhất sáu lần function timeout, có tính thêm batching window nếu dùng. Ví dụ function timeout 30 giây và queue visibility timeout 180 giây đáp ứng mức khuyến nghị cơ bản; tải thực tế có thể cần thêm khoảng đệm.

SQS Standard có semantics at-least-once, vì vậy handler phải idempotent. `maxReceiveCount` không thay thế logic chống trùng; nó chỉ xác định số lần nhận trước khi message được chuyển sang DLQ.

## 10. Tạo DynamoDB table và cấp quyền bằng grant

CDK L2 cung cấp helper để cấp quyền tối thiểu theo tài nguyên. Ví dụ tạo bảng đơn hàng:

```java
import software.amazon.awscdk.RemovalPolicy;
import software.amazon.awscdk.services.dynamodb.Attribute;
import software.amazon.awscdk.services.dynamodb.AttributeType;
import software.amazon.awscdk.services.dynamodb.BillingMode;
import software.amazon.awscdk.services.dynamodb.Table;

Table ordersTable = Table.Builder.create(this, "OrdersTable")
        .partitionKey(Attribute.builder()
                .name("orderId")
                .type(AttributeType.STRING)
                .build())
        .billingMode(BillingMode.PAY_PER_REQUEST)
        .removalPolicy(RemovalPolicy.RETAIN)
        .build();

ordersTable.grantReadWriteData(orderApi);
ordersTable.grantReadWriteData(orderWorker);
```

`grantReadWriteData` tạo policy cho các thao tác đọc/ghi dữ liệu cần thiết trên bảng. Nếu function chỉ cần đọc, dùng `grantReadData`; nếu chỉ ghi, dùng `grantWriteData`. Không gán `AdministratorAccess` hoặc `dynamodb:*` trên toàn account cho Lambda chỉ để tránh lỗi permission.

`RemovalPolicy.RETAIN` giúp giữ bảng khi stack bị xóa, phù hợp với dữ liệu cần bảo vệ. Tài nguyên được retain sẽ tồn tại ngoài vòng đời stack; cần quy trình quản lý và xóa riêng nếu muốn loại bỏ. Với môi trường test có thể dùng `DESTROY`, nhưng không dùng mặc định đó cho dữ liệu production.

## 11. Tổ chức Stack hoàn chỉnh cho một ứng dụng serverless

Một stack có thể kết hợp API, function, queue, DLQ và database. Để dễ quản lý, chia code thành các method hoặc construct nhỏ:

```java
public class OrdersServerlessStack extends Stack {
    public OrdersServerlessStack(
            Construct scope,
            String id,
            StackProps props) {
        super(scope, id, props);

        Table ordersTable = createOrdersTable();
        Queue ordersDlq = createOrdersDlq();
        Queue ordersQueue = createOrdersQueue(ordersDlq);

        Function apiHandler = createApiFunction(ordersTable);
        Function worker = createQueueWorker(ordersTable);

        LambdaRestApi.Builder.create(this, "OrdersApi")
                .handler(apiHandler)
                .proxy(true)
                .build();

        worker.addEventSource(new SqsEventSource(
                ordersQueue,
                SqsEventSourceProps.builder()
                        .batchSize(10)
                        .reportBatchItemFailures(true)
                        .build()));
    }

    // Các method create... tạo construct như những ví dụ ở trên.
}
```

Đây là khung tổ chức, cần import và định nghĩa các method `create...` theo project. Với stack lớn, tạo construct riêng như `OrdersApi`, `OrderProcessing` và `Persistence` để cô lập trách nhiệm. Đừng chia stack quá nhỏ nếu chúng có nhiều tham chiếu chéo và cần deploy đồng bộ; mỗi stack tạo thêm ranh giới CloudFormation và phụ thuộc triển khai.

## 12. Cấu hình môi trường và không đưa secret vào mã

CDK có thể nhận cấu hình từ context, environment variable, CloudFormation parameter hoặc resource reference. Chọn một nguồn có quy ước rõ ràng cho từng loại cấu hình.

| Loại cấu hình | Cách lưu phù hợp |
|---|---|
| Region/account deploy | Stack environment hoặc pipeline |
| Tên môi trường, log level, feature flag không nhạy cảm | CDK context hoặc environment variables |
| ARN/name của resource cùng stack | Lấy từ construct reference |
| Secret, password, API token | Secrets Manager hoặc Systems Manager Parameter Store |
| Cấu hình thay đổi thường xuyên khi runtime | Parameter Store/AppConfig hoặc config service |

Không ghi secret trong `cdk.json`, `cdk.context.json`, `pom.xml` hoặc Git. Context có thể được lưu vào repository và xuất hiện trong template. Nếu cần Lambda đọc secret, cấp quyền runtime để function lấy secret từ Secrets Manager thay vì resolve secret thành plaintext trong lúc synth.

Ví dụ cấp quyền đọc secret:

```java
import software.amazon.awscdk.services.secretsmanager.ISecret;
import software.amazon.awscdk.services.secretsmanager.Secret;

ISecret paymentSecret = Secret.fromSecretNameV2(
        this,
        "PaymentSecret",
        "production/payment-provider");

orderApi.addEnvironment("PAYMENT_SECRET_ARN", paymentSecret.getSecretArn());
paymentSecret.grantRead(orderApi);
```

Function nhận ARN qua environment variable và dùng AWS SDK/Secrets Manager client để đọc secret khi cần. Nếu cache secret trong memory để giảm latency, đặt TTL và xem xét hành vi khi secret được xoay vòng. Không log giá trị secret.

## 13. IAM least privilege và resource policy

CDK có helper `grant...` để cấp quyền theo tài nguyên. Hãy ưu tiên quyền cụ thể:

- `table.grantReadData(function)` thay vì `dynamodb:*`.
- `queue.grantSendMessages(producer)` thay vì `sqs:*`.
- `secret.grantRead(function)` thay vì quyền đọc mọi secret.
- Event source construct cấp quyền poll/consume cần thiết cho function.

IAM role của Lambda là identity policy gắn với function. Một số dịch vụ còn cần resource policy để cho principal khác account hoặc dịch vụ AWS được truy cập. Ví dụ API Gateway cần quyền invoke Lambda; S3 bucket có thể cần bucket policy; KMS key cần key policy cho principal sử dụng key.

Không nhầm quyền deploy với quyền runtime. Developer/CI role cần quyền CloudFormation và tạo resource; Lambda execution role chỉ cần quyền function dùng khi chạy. Tách hai role giúp giảm phạm vi ảnh hưởng nếu function bị xâm nhập.

## 14. VPC và kết nối riêng tư

Nếu Lambda cần truy cập database hoặc dịch vụ nội bộ trong VPC, CDK có thể tạo VPC, subnet và security group rồi gắn function vào VPC:

```java
import software.amazon.awscdk.services.ec2.Vpc;
import software.amazon.awscdk.services.ec2.SubnetSelection;
import software.amazon.awscdk.services.ec2.SubnetType;
import software.amazon.awscdk.services.ec2.SecurityGroup;
import software.amazon.awscdk.services.ec2.Peer;
import software.amazon.awscdk.services.ec2.Port;
import java.util.List;

Vpc vpc = Vpc.Builder.create(this, "ApplicationVpc")
        .maxAzs(2)
        .natGateways(1)
        .build();

SecurityGroup functionSecurityGroup = SecurityGroup.Builder.create(
        this, "FunctionSecurityGroup")
        .vpc(vpc)
        .allowAllOutbound(false)
        .build();

SecurityGroup databaseSecurityGroup = SecurityGroup.Builder.create(
        this, "DatabaseSecurityGroup")
        .vpc(vpc)
        .allowAllOutbound(false)
        .build();

functionSecurityGroup.addEgressRule(
        Peer.securityGroup(databaseSecurityGroup),
        Port.tcp(5432),
        "Allow PostgreSQL traffic to database");
databaseSecurityGroup.addIngressRule(
        Peer.securityGroup(functionSecurityGroup),
        Port.tcp(5432),
        "Allow PostgreSQL traffic from function");

Function privateWorker = Function.Builder.create(this, "PrivateWorker")
        .runtime(Runtime.JAVA_21)
        .handler("com.example.orders.PrivateHandler::handleRequest")
        .code(Code.fromAsset("../orders-function/target/orders-function.jar"))
        .vpc(vpc)
        .vpcSubnets(SubnetSelection.builder()
                .subnetType(SubnetType.PRIVATE_WITH_EGRESS)
                .build())
        .securityGroups(List.of(functionSecurityGroup))
        .timeout(Duration.seconds(30))
        .build();
```

Đây là cấu hình minh họa cho PostgreSQL; database cần gắn `databaseSecurityGroup` và port phải khớp dịch vụ thực tế. Cần thêm outbound rule tới VPC endpoint hoặc NAT Gateway cho các dịch vụ AWS/public endpoint cần dùng. VPC attachment làm Lambda cần ENI và ảnh hưởng thời gian khởi tạo, IP capacity, NAT cost và routing. Lambda đặt trong private subnet không tự có Internet access; nếu cần gọi public endpoint, phải có NAT Gateway hoặc đường egress được thiết kế phù hợp.

Nếu chỉ cần truy cập dịch vụ AWS qua PrivateLink, có thể dùng VPC endpoint tương ứng để tránh NAT cho traffic đó. Cân nhắc chi phí NAT Gateway, data processing và endpoint trước khi đưa mọi function vào VPC.

## 15. Logging, tracing và monitoring

CDK có thể bật tracing cho Lambda:

```java
.tracing(Tracing.ACTIVE)
```

X-Ray giúp nối trace qua các service được tích hợp. Function cũng cần quyền ghi CloudWatch Logs; L2 `Function` thường tạo execution role với các quyền cơ bản cần thiết. Trong môi trường production, cấu hình retention log, encryption, metric filter và alarm theo chính sách tổ chức.

Những chỉ số nên quan sát:

- Lambda `Invocations`, `Errors`, `Duration`, `Throttles` và `ConcurrentExecutions`.
- Tuổi message, số message visible/in-flight và độ sâu DLQ của SQS.
- API Gateway 4xx/5xx, latency và throttling.
- DynamoDB throttled requests, consumed capacity và latency.
- Workflow execution failed/timed out nếu có Step Functions.
- Chi phí theo function, API, queue, database, NAT và log.

Log có cấu trúc nên có `requestId`, `eventId`, `correlationId`, `orderId`, function version và error code. Không ghi token, secret hoặc toàn bộ payload chứa dữ liệu cá nhân.

## 16. Kiểm thử CDK bằng assertions

CDK synth tạo CloudFormation template; test có thể kiểm tra template đó mà không cần deploy tài nguyên thật. Artifact test của CDK v2 nằm trong package assertions.

Ví dụ JUnit:

```java
package com.example;

import java.util.Map;

import org.junit.jupiter.api.Test;
import software.amazon.awscdk.App;
import software.amazon.awscdk.StackProps;
import software.amazon.awscdk.assertions.Template;

class OrdersServerlessStackTest {
    @Test
    void createsJavaFunctionsAndApi() {
        App app = new App();
        OrdersServerlessStack stack = new OrdersServerlessStack(
                app,
                "TestOrdersStack",
                StackProps.builder().build());

        Template template = Template.fromStack(stack);

        template.resourceCountIs("AWS::Lambda::Function", 2);
        template.resourceCountIs("AWS::ApiGateway::RestApi", 1);
        template.hasResourceProperties(
                "AWS::Lambda::Function",
                Map.of("Runtime", "java21"));
    }
}
```

Test minh họa giả định stack tạo hai Lambda và một REST API. Nếu cấu trúc stack thay đổi, cập nhật assertion theo hành vi mong đợi. Không chỉ kiểm tra số resource; nên kiểm tra timeout, runtime, memory, environment, IAM action/resource, queue visibility timeout, redrive policy, encryption và retention.

Các loại kiểm thử:

- **Unit test cho construct tự xây dựng:** kiểm tra logic tạo resource và default.
- **Template assertion:** xác minh CloudFormation resource/properties/outputs.
- **Snapshot test:** phát hiện thay đổi template lớn; cần review diff vì snapshot có thể thay đổi hợp lệ.
- **Integration test:** deploy vào account test rồi kiểm tra trigger, permission, log và behavior.
- **Policy/security test:** kiểm tra IAM wildcard, resource public, encryption và policy bắt buộc.

## 17. Các lệnh CDK thường dùng

Sau khi viết code và build artifact:

```bash
mvn test
mvn package
cdk ls
cdk synth OrdersServerlessStack
cdk diff OrdersServerlessStack
cdk deploy OrdersServerlessStack --profile dev
```

Ý nghĩa:

| Lệnh | Tác dụng |
|---|---|
| `cdk ls` | Liệt kê stack trong ứng dụng |
| `cdk synth` | Tổng hợp construct thành CloudFormation template và Cloud Assembly |
| `cdk diff` | So sánh template sắp triển khai với trạng thái stack hiện tại |
| `cdk deploy` | Gửi Cloud Assembly/CloudFormation change set để triển khai |
| `cdk destroy` | Xóa stack và các tài nguyên không được retain |
| `cdk doctor` | Kiểm tra một số vấn đề môi trường CDK |

Luôn xem `cdk diff` trước khi deploy. Đặc biệt chú ý resource replacement, deletion, IAM policy mở rộng, public endpoint, subnet/route và thay đổi database. Một thay đổi nhỏ trong construct ID hoặc logical ID có thể khiến CloudFormation thay resource.

`cdk destroy` chỉ phù hợp với môi trường có thể xóa. Với production, cần quy trình phê duyệt và retention cho dữ liệu. `RemovalPolicy.RETAIN` giữ tài nguyên sau khi stack bị xóa nhưng cũng có nghĩa resource cần được quản lý riêng sau đó.

## 18. Bootstrap account và region

Trước lần deploy đầu tiên vào một account/region, CDK thường cần bootstrap môi trường. Bootstrap tạo các tài nguyên hỗ trợ như S3 bucket chứa asset, ECR repository cho container asset và IAM roles dùng trong deployment.

Ví dụ:

```bash
cdk bootstrap aws://123456789012/ap-southeast-1 --profile dev
```

Bootstrap là thao tác ở phạm vi account/region, không phải mỗi stack. Nó cần quyền tạo các tài nguyên bootstrap và có thể cần cấu hình trust nếu pipeline triển khai từ account khác.

Không bootstrap tùy tiện trong production bằng danh tính cá nhân có quyền rộng. Hãy xác định bootstrap execution policy, trusted accounts, qualifier và version theo chuẩn nền tảng của tổ chức. Không xóa bootstrap stack khi còn ứng dụng dùng asset hoặc deployment role của nó.

## 19. Phân chia stack và môi trường

Một hệ thống lớn có thể chia thành nhiều stack:

- `NetworkStack`: VPC, subnet, route, endpoint.
- `DataStack`: DynamoDB, S3, database và encryption key.
- `ApplicationStack`: Lambda, API Gateway, queue và event routing.
- `ObservabilityStack`: dashboard, alarm, log group và tracing configuration.

Chỉ tách khi ranh giới ownership, vòng đời hoặc quyền triển khai khác nhau. Nếu mọi stack luôn phải deploy cùng nhau và có nhiều cross-stack reference, việc chia quá nhỏ có thể làm deployment phức tạp.

### Dev, staging và production

Có thể triển khai cùng một CDK app vào nhiều account/region bằng context hoặc environment variables:

```bash
CDK_DEFAULT_ACCOUNT=111111111111 \
CDK_DEFAULT_REGION=ap-southeast-1 \
cdk synth
```

Ví dụ trên minh họa biến môi trường trong shell kiểu Unix; trên Windows PowerShell, dùng cú pháp `$env:CDK_DEFAULT_ACCOUNT = "..."` và `$env:CDK_DEFAULT_REGION = "..."` trước khi chạy CDK.

Không hardcode account ID production vào source. Pipeline nên chọn account và role theo môi trường, còn code dùng cùng construct với cấu hình khác nhau. Dùng tags như `Environment`, `Service`, `Owner` và `CostCenter` để hỗ trợ inventory, governance và cost allocation.

## 20. CI/CD cho AWS CDK Java

Một pipeline có thể gồm:

1. Checkout source và khóa phiên bản JDK, Maven, CDK CLI.
2. Chạy unit test cho function và construct.
3. Build JAR/container asset của function.
4. Chạy dependency/security scan.
5. Chạy `cdk synth` và lưu Cloud Assembly làm artifact.
6. Chạy policy checks trên template (IAM, encryption, public access, retention).
7. Tạo và review `cdk diff` hoặc CloudFormation change set.
8. Triển khai vào dev/staging bằng role của pipeline.
9. Chạy integration test/smoke test.
10. Yêu cầu phê duyệt trước khi triển khai production.
11. Theo dõi alarm và rollback theo chiến lược release.

Pipeline nên dùng OIDC hoặc cơ chế federation tương đương để lấy credential ngắn hạn, thay vì lưu access key dài hạn. Role deploy và role runtime cần tách riêng. Nếu dùng cross-account deployment, bootstrap trust phải giới hạn đúng account và pipeline principal.

## 21. Quản lý thay đổi và tránh mất dữ liệu

CloudFormation cập nhật resource theo template mới. Một số thuộc tính được cập nhật tại chỗ; một số yêu cầu replacement. CDK không tự biết dữ liệu trong resource có thể xóa hay không.

Trước khi thay đổi resource stateful:

- Kiểm tra `cdk diff` và CloudFormation replacement behavior.
- Dùng `RemovalPolicy.RETAIN` cho database, bucket hoặc queue cần giữ dữ liệu.
- Bật deletion protection nếu dịch vụ hỗ trợ.
- Lập kế hoạch backup/restore và migration.
- Giữ tương thích schema giữa phiên bản function cũ và mới trong giai đoạn rollout.
- Tránh đổi construct path/ID nếu không có chủ đích thay resource.
- Không hardcode tên physical resource nếu không cần; tên do CloudFormation tạo giúp tránh xung đột và dễ thay thế hơn.

Với Lambda, có thể dùng version và alias để chuyển traffic có kiểm soát. Với API Gateway hoặc event source mapping, cần kiểm tra việc thay đổi integration có tạo khoảng gián đoạn hoặc xử lý trùng. Rollback code không tự hoàn tác message đã xử lý hoặc giao dịch database đã commit.

## 22. Chi phí và lựa chọn kiến trúc

CDK giúp nhìn rõ các resource được tạo, nhưng không tự tối ưu chi phí. Hãy đánh giá chi phí toàn luồng:

- Lambda invocation, duration, memory, architecture và provisioned concurrency.
- API Gateway request, data transfer và logging.
- SQS request, message retention và DLQ.
- DynamoDB read/write capacity, storage và backup.
- NAT Gateway hourly/data processing, VPC endpoint và data transfer.
- CloudWatch Logs ingestion, retention, metrics và tracing.
- KMS key, Secrets Manager và các dịch vụ tích hợp.

Ví dụ, thêm NAT Gateway vào mỗi VPC có thể tạo chi phí cố định đáng kể ngay cả khi function ít chạy. Tạo một VPC endpoint cho mỗi dịch vụ cũng có chi phí riêng. Nếu function chỉ gọi dịch vụ AWS public endpoint và không cần private network, không nên gắn VPC một cách mặc định.

Tags và stack outputs giúp quản lý inventory, nhưng cost allocation cần bật các cost allocation tags ở tài khoản và kiểm tra báo cáo Cost Explorer/Billing. Hãy đo chi phí theo giao dịch nghiệp vụ thay vì chỉ nhìn hóa đơn tổng.

## 23. Lỗi thường gặp khi dùng CDK Java

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Không build JAR trước `cdk synth` | Asset không tồn tại hoặc đóng gói artifact cũ | Thêm bước Maven build trước synth |
| Handler sai tên class/method | Lambda khởi động nhưng không tìm được handler | Kiểm tra JAR, package và handler signature |
| Dùng CDK v1 với dependency v2 | Compile lỗi hoặc API không tương thích | Dùng `aws-cdk-lib` và `constructs` cùng version phù hợp |
| Không bootstrap account/region | Deploy thiếu asset bucket hoặc role | Chạy `cdk bootstrap` bằng role phù hợp |
| Cấp IAM wildcard | Function có quyền vượt nhu cầu | Dùng `grantReadData`, `grantConsumeMessages` và policy theo ARN |
| Dùng `RemovalPolicy.DESTROY` cho dữ liệu production | Mất database/bucket/queue khi xóa stack | Dùng RETAIN, backup và deletion protection |
| Đổi construct ID không chủ ý | CloudFormation tạo resource mới hoặc thay resource | Giữ construct path ổn định và review diff |
| Hardcode secret trong context | Secret có thể lọt vào Git/template | Dùng Secrets Manager/Parameter Store và runtime grant |
| Thêm VPC không cần thiết | Tăng cold start và chi phí NAT/endpoint | Chỉ gắn VPC khi workload cần tài nguyên private |
| Không test template | Sai runtime, timeout, IAM hoặc redrive chỉ phát hiện khi deploy | Dùng CDK assertions và integration test |
| Deploy từ credential cá nhân | Khó audit và khó kiểm soát quyền | Dùng pipeline role/federation và phê duyệt |

## 24. Quy trình xây dựng hạ tầng serverless bằng CDK

Một quy trình thực hành có thể thực hiện theo thứ tự:

1. **Mô tả workload:** xác định HTTP/event/message trigger, dữ liệu, trạng thái và SLA.
2. **Vẽ kiến trúc:** chọn API Gateway, Lambda, queue/event bus, database, network và observability.
3. **Xác định ownership:** chọn stack và construct boundary theo vòng đời tài nguyên.
4. **Khởi tạo CDK Java:** khóa JDK, Maven, CDK CLI và dependency version.
5. **Viết construct:** dùng L2/L3 trước, L1 khi cần thuộc tính chi tiết.
6. **Cấp quyền:** dùng grant helper, tách deploy role khỏi runtime role.
7. **Đặt chính sách vận hành:** timeout, memory, concurrency, retry, DLQ, retention và encryption.
8. **Cấu hình môi trường:** account/region, tags, non-secret config và secret reference.
9. **Kiểm thử:** unit test, CDK assertions, synth và policy checks.
10. **Bootstrap:** chuẩn bị account/region và trust của pipeline.
11. **Review diff:** kiểm tra replacement, deletion, IAM và public exposure.
12. **Deploy và verify:** triển khai theo môi trường, chạy smoke test và kiểm tra metrics/log.
13. **Theo dõi chi phí:** phân bổ theo tag và tối ưu theo dữ liệu thực tế.

## 25. Checklist trước khi triển khai production

- [ ] Dùng AWS CDK v2 và khóa phiên bản dependency/CLI.
- [ ] App, Stack và Construct được tổ chức theo ranh giới ownership rõ ràng.
- [ ] Runtime/handler/architecture của Lambda khớp artifact Java.
- [ ] Artifact được build trước `cdk synth` và asset path được xác minh.
- [ ] API Gateway, queue/event source mapping và DLQ được cấu hình đúng semantics.
- [ ] Timeout, memory, batch size, visibility timeout và concurrency phù hợp.
- [ ] IAM role của Lambda theo least privilege; deploy role tách riêng.
- [ ] Secret không nằm trong source, context hoặc CloudFormation plaintext.
- [ ] Database/bucket/queue quan trọng có retention, backup và deletion protection phù hợp.
- [ ] VPC chỉ được bật khi cần; subnet, NAT, endpoint và security group đã được tính chi phí.
- [ ] Logging, tracing, metrics, alarm và retention đã được cấu hình.
- [ ] Có CDK assertions cho runtime, resource, IAM, encryption và policy quan trọng.
- [ ] `cdk synth` và `cdk diff` đã được review.
- [ ] Account/region đã bootstrap và pipeline dùng identity ngắn hạn.
- [ ] Đã deploy thử, chạy integration test và có phương án rollback.
- [ ] Tags và cost allocation hỗ trợ theo dõi chi phí theo service/environment.

## Tài liệu AWS tham khảo

- [AWS CDK Developer Guide](https://docs.aws.amazon.com/cdk/v2/guide/home.html)
- [Getting started with the AWS CDK for Java](https://docs.aws.amazon.com/cdk/v2/guide/work-with-cdk-java.html)
- [AWS CDK constructs](https://docs.aws.amazon.com/cdk/v2/guide/constructs.html)
- [AWS CDK bootstrapping](https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping.html)
- [AWS CDK testing](https://docs.aws.amazon.com/cdk/v2/guide/testing.html)
- [AWS Lambda with Java](https://docs.aws.amazon.com/lambda/latest/dg/lambda-java.html)
- [Using AWS Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [AWS Well-Architected Serverless Applications Lens](https://docs.aws.amazon.com/wellarchitected/latest/serverless-applications-lens/welcome.html)

## Kết luận

AWS CDK cho phép xây dựng hạ tầng serverless bằng Java theo cách có cấu trúc, có thể kiểm thử và triển khai lặp lại. `App` tổ chức ứng dụng, `Stack` xác định đơn vị CloudFormation và `Construct` mô tả tài nguyên hoặc pattern. Khi kết hợp Lambda, API Gateway, SQS, database và IAM, hãy ưu tiên construct cấp cao cùng quyền tối thiểu, giữ trạng thái ở dịch vụ bền vững, cấu hình retry/DLQ/timeout đúng trigger và bảo vệ tài nguyên stateful khi thay đổi. Quy trình `test → synth → diff → bootstrap → deploy → verify` giúp biến mã CDK thành hạ tầng có thể review, audit và vận hành an toàn qua nhiều môi trường.
