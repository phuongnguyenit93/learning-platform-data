# Khai báo ứng dụng bằng Serverless Framework

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của Serverless Framework trong việc mô tả và triển khai ứng dụng serverless.
- Tổ chức một Java project theo khái niệm service, function, event, resource và provider.
- Viết `serverless.yml` để khai báo Lambda function, HTTP API, queue, lịch chạy và tài nguyên AWS.
- Đóng gói Java artifact bằng Maven và kết nối artifact với cấu hình triển khai.
- Quản lý stage, region, environment variable, IAM permission và cấu hình riêng cho từng function.
- Triển khai, kiểm tra, cập nhật và gỡ một service có kiểm soát.
- Thiết kế retry, idempotency, logging và quy trình CI/CD cho ứng dụng serverless.

## 1. Serverless Framework là gì?

Serverless Framework là công cụ Infrastructure as Code (IaC) giúp mô tả và triển khai ứng dụng serverless bằng file cấu hình. Với AWS, file chính thường là `serverless.yml`. File này khai báo provider, function, event trigger, quyền IAM, tài nguyên hạ tầng và các thiết lập triển khai.

Khi chạy lệnh deploy, Serverless Framework phân tích cấu hình, đóng gói artifact theo cách đã chọn, tạo template CloudFormation và triển khai các tài nguyên cần thiết lên AWS. Người phát triển quản lý ứng dụng qua source code và cấu hình có thể review trong Git.

Serverless Framework không thay thế AWS Lambda, API Gateway, SQS, EventBridge hoặc DynamoDB. Framework giúp mô tả cách các dịch vụ đó kết hợp thành một ứng dụng. Runtime vẫn thực thi function; dịch vụ AWS vẫn đảm nhiệm trigger, lưu trữ, mở rộng và bảo mật.

### 1.1. Mô hình tổng thể

~~~mermaid
flowchart TD
    A[Source Java và serverless.yml] --> B[Maven build]
    B --> C[JAR artifact]
    A --> D[Serverless Framework CLI]
    C --> D
    D --> E[CloudFormation template]
    E --> F[AWS resources]
    F --> G[Lambda functions]
    F --> H[API Gateway / SQS / EventBridge]
    H --> G
    G --> I[DynamoDB / S3 / dịch vụ khác]
~~~

Luồng triển khai cơ bản:

1. Developer viết Java handler và khai báo hạ tầng trong `serverless.yml`.
2. Maven biên dịch source và tạo artifact có dependency cần thiết.
3. Serverless Framework đọc cấu hình, tham chiếu artifact và tạo package triển khai.
4. Framework sinh hoặc cập nhật CloudFormation stack.
5. AWS tạo function, event source mapping, API route, IAM role và các resource được khai báo.
6. Event trigger gọi function khi có request hoặc sự kiện tương ứng.

### 1.2. Những khái niệm chính

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Service | Đơn vị ứng dụng được triển khai và quản lý cùng nhau | `order-service` |
| Provider | Nền tảng cloud đích | `aws` |
| Function | Một đơn vị code được triển khai riêng | `createOrder`, `processOrder` |
| Event | Sự kiện kích hoạt function | HTTP API, SQS, EventBridge |
| Resource | Tài nguyên hạ tầng được khai báo | DynamoDB table, SQS queue |
| Stage | Môi trường triển khai | `dev`, `staging`, `prod` |
| Plugin | Phần mở rộng cho quy trình Framework | Plugin local invoke hoặc đóng gói |

Một service có thể có nhiều function. Mỗi function có thể có handler, memory, timeout, environment và event riêng. Các function có thể dùng chung resource như DynamoDB table hoặc SQS queue được khai báo trong cùng service.

### 1.3. Vì sao dùng cấu hình thay cho tạo tài nguyên thủ công?

Khai báo bằng IaC giúp:

- Review thay đổi hạ tầng qua pull request và Git diff.
- Tạo lại môi trường dev/test/prod theo cùng một cấu trúc.
- Theo dõi quan hệ giữa function, trigger, IAM và resource.
- Giảm lỗi do cấu hình thủ công không đồng nhất.
- Dễ kiểm tra lịch sử thay đổi và quay lại phiên bản cấu hình trước.
- Tự động hóa triển khai trong CI/CD.

Tuy vậy, cấu hình IaC vẫn cần được thiết kế và kiểm thử. Một file YAML hợp lệ về cú pháp vẫn có thể tạo quyền quá rộng, trigger sai hoặc tải vượt capacity của database.

## 2. Cấu trúc project Java dùng Serverless Framework

Một cấu trúc Maven đơn giản:

~~~text
order-service/
├── pom.xml
├── serverless.yml
├── src/
│   └── main/
│       └── java/
│           └── com/
│               └── example/
│                   ├── CreateOrderHandler.java
│                   └── ProcessOrderHandler.java
└── target/
    └── order-service-1.0.0.jar
~~~

`serverless.yml` nằm ở thư mục gốc service. Java source được build bằng Maven. Artifact sau build được tham chiếu từ cấu hình để Serverless Framework đưa vào gói triển khai.

Với Java trên AWS Lambda, handler thường implement `com.amazonaws.services.lambda.runtime.RequestHandler` hoặc `RequestStreamHandler`. AWS Lambda Java runtime gọi handler theo tên class đã cấu hình.

### 2.1. Dependency cho Java handler

Ví dụ dependency tối thiểu trong `pom.xml`:

~~~xml
<dependencies>
  <dependency>
    <groupId>com.amazonaws</groupId>
    <artifactId>aws-lambda-java-core</artifactId>
    <version>1.2.3</version>
  </dependency>
</dependencies>
~~~

Version ở đây là ví dụ minh họa. Hãy pin phiên bản đã xác minh tương thích với runtime và thư viện ứng dụng. Không dùng version động trong pipeline production.

Một handler HTTP API có thể nhận event dạng map và trả response theo định dạng API Gateway HTTP API payload v2:

~~~java
package com.example;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;

import java.util.Map;
import java.util.Optional;

public final class HelloHandler
        implements RequestHandler<Map<String, Object>, Map<String, Object>> {

    @Override
    public Map<String, Object> handleRequest(
            Map<String, Object> event,
            Context context) {

        Object rawQuery = event.get("queryStringParameters");
        String name = "world";

        if (rawQuery instanceof Map<?, ?> query) {
            name = Optional.ofNullable(query.get("name"))
                    .map(Object::toString)
                    .filter(value -> !value.isBlank())
                    .orElse("world");
        }

        return Map.of(
                "statusCode", 200,
                "headers", Map.of(
                        "content-type", "text/plain; charset=utf-8"),
                "isBase64Encoded", false,
                "body", "Hello " + name
        );
    }
}
~~~

Ví dụ này minh họa response của HTTP API. Trong ứng dụng thực tế, hãy deserialize request body sang DTO, validate input, xác thực caller và gọi application service. Không coi các field do client gửi như `userId` hoặc `tenantId` là danh tính đã xác thực.

### 2.2. Đóng gói dependency vào JAR

AWS Lambda cần có các dependency runtime trong deployment artifact. Một cách phổ biến với Maven là dùng Maven Shade Plugin để tạo JAR chứa dependency:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-shade-plugin</artifactId>
      <version>3.6.0</version>
      <executions>
        <execution>
          <phase>package</phase>
          <goals>
            <goal>shade</goal>
          </goals>
          <configuration>
            <createDependencyReducedPom>false</createDependencyReducedPom>
          </configuration>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
~~~

Sau khi chạy `mvn clean package`, Maven tạo JAR đã đóng gói dependency. Tên file phụ thuộc `artifactId` và `version` trong POM. Hãy kiểm tra đúng đường dẫn trước khi khai báo `package.artifact`.

Nếu dependency dùng Java Service Provider Interface (SPI), một số thư viện có thể cần merge service descriptor khi shade. Kiểm tra resource và metadata sau đóng gói, đặc biệt khi dùng AWS SDK, logging backend hoặc driver. Một JAR có thể compile thành công nhưng lỗi lúc runtime vì thiếu class hoặc resource.

## 3. File serverless.yml

`serverless.yml` mô tả service và các tài nguyên liên quan. Cấu trúc thường có các phần:

- `service`: tên service.
- `frameworkVersion`: phiên bản Serverless Framework được yêu cầu.
- `provider`: cloud provider và cấu hình chung.
- `functions`: các function và event trigger.
- `resources`: resource CloudFormation bổ sung.
- `plugins`: plugin mở rộng.
- `package`: quy tắc đóng gói artifact.
- `custom`: cấu hình dành cho plugin hoặc biểu thức tái sử dụng.

Ví dụ cấu hình tối thiểu:

~~~yaml
service: order-service
frameworkVersion: '4'

provider:
  name: aws
  runtime: java21
  region: ap-southeast-1
  stage: dev
  memorySize: 512
  timeout: 15

package:
  artifact: target/order-service-1.0.0.jar

functions:
  hello:
    handler: com.example.HelloHandler
    events:
      - httpApi:
          method: GET
          path: /hello
~~~

Đây là cấu hình minh họa. Trước khi dùng, cần bảo đảm runtime Java được AWS Lambda hỗ trợ tại thời điểm deploy, JAR tồn tại đúng đường dẫn và handler class có trong artifact.

### 3.1. Khai báo service và provider

`service` đặt tên đơn vị triển khai. Tên này được dùng trong tên stack, resource hoặc artifact tùy quy tắc của Framework.

`provider.name` xác định nền tảng đích. Với bài học này là `aws`. `provider.runtime` xác định runtime cho các function nếu function không ghi đè. `region` và `stage` quyết định nơi và môi trường triển khai.

Các thiết lập chung thường dùng:

~~~yaml
service: order-service
frameworkVersion: '4'

provider:
  name: aws
  runtime: java21
  region: ap-southeast-1
  stage: ${opt:stage, 'dev'}
  memorySize: 512
  timeout: 15
  architecture: arm64
  logRetentionInDays: 14
~~~

Biểu thức `${opt:stage, 'dev'}` lấy giá trị từ CLI option `--stage`; nếu không truyền thì dùng `dev`. `architecture` có thể là `x86_64` hoặc `arm64` tùy runtime và dependency. Nếu JAR có JNI hoặc native binary, cần build và kiểm tra đúng kiến trúc.

### 3.2. Cấu hình riêng cho function

Function có thể ghi đè các giá trị provider:

~~~yaml
functions:
  createOrder:
    handler: com.example.CreateOrderHandler
    memorySize: 1024
    timeout: 20
    events:
      - httpApi:
          method: POST
          path: /orders

  processOrder:
    handler: com.example.ProcessOrderHandler
    memorySize: 1536
    timeout: 60
    events:
      - sqs:
          arn:
            Fn::GetAtt:
              - OrdersQueue
              - Arn
          batchSize: 10
          functionResponseType: ReportBatchItemFailures
~~~

`createOrder` phục vụ request đồng bộ và cần timeout phù hợp với deadline của client/API. `processOrder` xử lý message có thể cần thời gian dài hơn. `batchSize` điều chỉnh số message trong một batch; batch lớn giúp giảm overhead nhưng tăng memory, thời gian xử lý và phạm vi retry.

`functionResponseType: ReportBatchItemFailures` cho phép handler báo những message thất bại để event source mapping chỉ retry phần cần thiết theo cơ chế partial batch response. Handler Java cần trả về response theo contract của AWS Lambda SQS event source mapping; chỉ khai báo cấu hình mà handler không tạo response tương ứng sẽ không đạt hành vi mong muốn.

## 4. Khai báo event trigger

Event mô tả điều kiện làm function được gọi. Serverless Framework chuyển khai báo event thành tích hợp AWS tương ứng.

### 4.1. HTTP API

Ví dụ:

~~~yaml
functions:
  getOrder:
    handler: com.example.GetOrderHandler
    events:
      - httpApi:
          method: GET
          path: /orders/{orderId}

  createOrder:
    handler: com.example.CreateOrderHandler
    events:
      - httpApi:
          method: POST
          path: /orders
~~~

HTTP API phù hợp với REST endpoint và webhook. Framework cấu hình route và tích hợp API Gateway với Lambda. Handler cần trả response đúng định dạng integration, bao gồm status code, headers và body.

Không nhầm `httpApi` với event `http` của API Gateway REST API. Chúng có cấu hình, tính năng và payload contract khác nhau. Chọn một loại API có chủ đích rồi dùng event shape tương ứng trong Java handler.

### 4.2. SQS queue

Queue tách bước nhận yêu cầu khỏi xử lý nền:

~~~yaml
functions:
  processOrder:
    handler: com.example.ProcessOrderHandler
    timeout: 30
    events:
      - sqs:
          arn:
            Fn::GetAtt: [OrdersQueue, Arn]
          batchSize: 10
          maximumBatchingWindow: 5
          functionResponseType: ReportBatchItemFailures

resources:
  Resources:
    OrdersQueue:
      Type: AWS::SQS::Queue
      Properties:
        VisibilityTimeout: 185
~~~

Queue buffer giúp hấp thụ tải đột biến. Lambda poll message và gọi worker theo event source mapping. Cần đặt visibility timeout đủ dài để message không bị giao lại khi invocation trước còn chạy. Hướng dẫn AWS thường khuyến nghị visibility timeout tối thiểu bằng sáu lần function timeout, cộng thêm batch window nếu có; hãy xác minh hướng dẫn hiện hành và cấu hình thực tế của event source mapping.

Khi dùng batch, một message lỗi có thể khiến cả batch được giao lại nếu không bật và xử lý partial batch response đúng cách. Handler cần theo dõi từng message và trả về danh sách `batchItemFailures` theo contract.

### 4.3. EventBridge schedule

Function có thể chạy định kỳ bằng EventBridge schedule:

~~~yaml
functions:
  dailySummary:
    handler: com.example.DailySummaryHandler
    timeout: 120
    events:
      - schedule:
          rate: cron(0 1 * * ? *)
          enabled: true
~~~

Biểu thức cron của EventBridge dùng múi giờ UTC theo cấu hình schedule truyền thống. `cron(0 1 * * ? *)` nghĩa là chạy lúc 01:00 UTC mỗi ngày, không tự động theo múi giờ địa phương. Nếu nghiệp vụ yêu cầu múi giờ cụ thể, cần kiểm tra khả năng cấu hình timezone của loại schedule đang dùng hoặc chuyển đổi thời gian phù hợp.

### 4.4. EventBridge event pattern

Một function có thể nhận event theo source và detail type:

~~~yaml
functions:
  orderCreated:
    handler: com.example.OrderCreatedHandler
    events:
      - eventBridge:
          pattern:
            source:
              - com.example.orders
            detail-type:
              - OrderCreated
~~~

Event pattern lọc event theo cấu trúc. Handler vẫn cần validate payload vì event có thể thiếu field hoặc chứa dữ liệu không hợp lệ. Không xem việc event đến từ EventBridge là bằng chứng rằng mọi giá trị trong `detail` đều đáng tin cậy.

### 4.5. S3 event

Có thể đăng ký function nhận sự kiện object được tạo trong bucket đã tồn tại:

~~~yaml
functions:
  imageUploaded:
    handler: com.example.ImageUploadedHandler
    events:
      - s3:
          bucket: company-upload-bucket
          event: s3:ObjectCreated:*
          existing: true
~~~

`existing: true` dùng khi bucket được quản lý bên ngoài service này. Trong trường hợp đó, deployment không sở hữu vòng đời bucket. Cần bảo đảm bucket notification có thể cấu hình cho trigger và tránh để nhiều stack cùng ghi đè cấu hình notification của một bucket.

Nếu Serverless Framework quản lý bucket trong cùng stack, hãy khai báo resource rõ ràng và cấu hình event theo hướng dẫn tương thích với phiên bản Framework. Chú ý tránh vòng phụ thuộc giữa bucket notification và quyền Lambda invoke.

## 5. Khai báo resource và quyền IAM

Một service thường cần tài nguyên ngoài Lambda như DynamoDB table, SQS queue, S3 bucket hoặc EventBridge bus. Có thể khai báo các resource CloudFormation trong phần `resources`.

### 5.1. Khai báo DynamoDB table

Ví dụ:

~~~yaml
resources:
  Resources:
    OrdersTable:
      Type: AWS::DynamoDB::Table
      Properties:
        BillingMode: PAY_PER_REQUEST
        AttributeDefinitions:
          - AttributeName: orderId
            AttributeType: S
        KeySchema:
          - AttributeName: orderId
            KeyType: HASH
~~~

CloudFormation tạo table cùng stack. `PAY_PER_REQUEST` phù hợp với workload biến động hoặc chưa biết trước throughput; với workload ổn định, có thể đánh giá provisioned capacity và autoscaling theo nhu cầu.

Trong function, tên table nên được truyền qua environment variable hoặc tham chiếu CloudFormation thay vì hardcode. Ví dụ:

~~~yaml
provider:
  environment:
    ORDERS_TABLE:
      Ref: OrdersTable
~~~

Trong Java:

~~~java
String tableName = System.getenv("ORDERS_TABLE");
if (tableName == null || tableName.isBlank()) {
    throw new IllegalStateException("ORDERS_TABLE is not configured");
}
~~~

### 5.2. Cấp quyền tối thiểu cho function

Khai báo resource không tự động có nghĩa function được quyền truy cập resource đó. Lambda execution role cần IAM permission tương ứng.

Ví dụ cấp quyền đọc/ghi item trong đúng table:

~~~yaml
provider:
  iam:
    role:
      statements:
        - Effect: Allow
          Action:
            - dynamodb:GetItem
            - dynamodb:PutItem
            - dynamodb:UpdateItem
          Resource:
            Fn::GetAtt:
              - OrdersTable
              - Arn
~~~

Dùng ARN được tham chiếu từ resource giúp tránh hardcode account ID hoặc region. Nếu function chỉ cần đọc, chỉ cấp `GetItem`; không cấp `Scan`, `DeleteItem` hoặc quyền quản trị table khi không cần.

Nếu nhiều function có nhu cầu quyền rất khác nhau, cân nhắc IAM role riêng cho từng function thay vì cấp một bộ quyền rộng cho toàn provider. Cấu hình quyền theo nguyên tắc least privilege và review IAM diff trước khi deploy.

### 5.3. Khai báo queue, dead-letter queue và redrive

Ví dụ một queue có DLQ:

~~~yaml
resources:
  Resources:
    OrdersDeadLetterQueue:
      Type: AWS::SQS::Queue
      Properties:
        MessageRetentionPeriod: 1209600

    OrdersQueue:
      Type: AWS::SQS::Queue
      Properties:
        VisibilityTimeout: 185
        RedrivePolicy:
          deadLetterTargetArn:
            Fn::GetAtt:
              - OrdersDeadLetterQueue
              - Arn
          maxReceiveCount: 5
~~~

`maxReceiveCount` xác định số lần message được nhận trước khi chuyển sang DLQ theo redrive policy. DLQ giúp cô lập message lỗi kéo dài để điều tra và xử lý lại có kiểm soát. Cần theo dõi số message trong DLQ và đặt quy trình replay sau khi đã sửa nguyên nhân.

Ví dụ này đặt function timeout 30 giây và batch window 5 giây, nên visibility timeout 185 giây tương ứng sáu lần timeout cộng batch window. Hãy điều chỉnh theo timeout thực tế và hướng dẫn AWS hiện hành.

### 5.4. Quyền đọc queue

Nếu function dùng SQS event source mapping, execution role cần quyền đọc và quản lý message. Ví dụ:

~~~yaml
provider:
  iam:
    role:
      statements:
        - Effect: Allow
          Action:
            - sqs:ReceiveMessage
            - sqs:DeleteMessage
            - sqs:GetQueueAttributes
            - sqs:ChangeMessageVisibility
          Resource:
            Fn::GetAtt:
              - OrdersQueue
              - Arn
~~~

Các quyền cần thiết phụ thuộc trigger và cấu hình. Không cấp `sqs:*` trên mọi queue chỉ để tránh lỗi permission. Khi dùng encryption với KMS hoặc queue policy tùy chỉnh, có thể cần thêm quyền phù hợp cho key hoặc principal liên quan.

## 6. Environment variable và quản lý stage

Stage tách môi trường triển khai, ví dụ `dev`, `test`, `staging` và `prod`. Mỗi stage có thể dùng resource, log retention, memory, concurrency và cấu hình dependency khác nhau.

### 6.1. Truyền stage vào cấu hình

Một cách phổ biến:

~~~yaml
provider:
  stage: ${opt:stage, 'dev'}
  environment:
    APP_STAGE: ${sls:stage}
    LOG_LEVEL: info
~~~

Triển khai stage dev:

~~~bash
serverless deploy --stage dev
~~~

Triển khai stage production:

~~~bash
serverless deploy --stage prod
~~~

`${sls:stage}` lấy stage đã được Framework giải quyết. `opt:stage` đọc CLI option. Khi dùng stage variable, tên stack và tên resource nên có stage để tránh dev ghi đè production hoặc hai môi trường dùng chung tài nguyên ngoài ý muốn.

### 6.2. Cấu hình riêng cho từng stage

Pipeline có thể đặt environment variable khác nhau trước khi chạy lệnh deploy. Ví dụ:

~~~yaml
provider:
  environment:
    APP_STAGE: ${sls:stage}
    ORDERS_TABLE: ${self:service}-${sls:stage}-orders
    LOG_LEVEL: ${env:LOG_LEVEL, 'info'}
~~~

CI có thể đặt `LOG_LEVEL=debug` cho stage dev và `LOG_LEVEL=warn` cho production. Framework resolve biến lúc deploy rồi đưa giá trị vào cấu hình Lambda. Dùng cách này cho cấu hình không nhạy cảm; secret vẫn cần được quản lý qua Secrets Manager hoặc Parameter Store.

### 6.3. Không đặt secret trực tiếp trong serverless.yml

Không commit API key, password, private key hoặc credential vào Git. Dùng AWS Secrets Manager hoặc Systems Manager Parameter Store để lưu secret; cấp quyền đọc secret cho đúng execution role. Có thể tham chiếu giá trị từ nguồn secret theo cơ chế biến của Framework, nhưng cần bảo đảm secret không bị in ra log, output hoặc file package.

Environment variable phù hợp với cấu hình không nhạy cảm như tên table, feature flag hoặc log level. Secret nên có vòng đời, quyền truy cập và quy trình rotation riêng.

## 7. Package và quy trình build Java

Serverless Framework cần artifact sẵn sàng cho runtime. Với Java, cần phối hợp Maven build và cấu hình `package`.

### 7.1. Chỉ định artifact

Ví dụ:

~~~yaml
package:
  artifact: target/order-service-1.0.0.jar
~~~

Khi khai báo `package.artifact`, Framework sử dụng artifact đã được build ở đường dẫn đó. Vì vậy, pipeline phải chạy Maven trước khi chạy `serverless package` hoặc `serverless deploy`.

Thứ tự cơ bản:

~~~bash
mvn clean package
serverless package --stage dev
serverless deploy --stage dev
~~~

Lệnh `serverless deploy` thường thực hiện package trước khi deploy; bước `serverless package` riêng hữu ích để kiểm tra package hoặc lưu artifact làm đầu vào cho pipeline sau.

### 7.2. Package theo từng function

Nếu mỗi function có artifact khác nhau, có thể dùng cấu hình package ở cấp function hoặc `package.individually` tùy cách tổ chức service. Cách này giảm kích thước artifact của từng function, nhưng tăng số gói cần quản lý và yêu cầu build pipeline tạo đúng JAR cho từng handler.

Không bật package riêng lẻ nếu tất cả function dùng chung một JAR mà không có lý do rõ ràng. Trước khi deploy, kiểm tra package chứa đúng class handler và dependency cần thiết.

### 7.3. Tối ưu artifact Java

Một số cách giảm kích thước và thời gian khởi tạo:

- Chỉ đưa dependency thực sự cần vào runtime artifact.
- Tránh đóng gói nhiều phiên bản thư viện trùng nhau.
- Kiểm tra resource/service descriptor sau Maven Shade.
- Dùng Java runtime và architecture phù hợp với dependency.
- Tách function theo bounded context khi dependency và mục tiêu mở rộng khác nhau.
- Tránh tạo một JAR quá lớn chỉ vì gom toàn bộ ứng dụng vào một function.

Nếu function dùng AWS SDK, ưu tiên dependency đúng module cần dùng và kiểm tra version compatibility. Không dựa vào việc runtime tự có mọi phiên bản SDK mà ứng dụng cần.

## 8. Plugin và custom configuration

Plugin mở rộng hành vi của Serverless Framework, ví dụ hỗ trợ chạy local, đóng gói, kiểm tra hoặc tích hợp công cụ triển khai. Cấu hình plugin trong `plugins`:

~~~yaml
plugins:
  - serverless-offline
~~~

Plugin `serverless-offline` có thể mô phỏng một phần HTTP API trên máy phát triển. Nó hữu ích để kiểm tra route và handler nhanh, nhưng không mô phỏng hoàn toàn IAM, retry, concurrency, cold start, API Gateway hoặc hành vi của mọi dịch vụ AWS.

Chỉ thêm plugin có nhu cầu cụ thể. Pin phiên bản plugin, kiểm tra khả năng tương thích với Serverless Framework và Java runtime, đồng thời đưa plugin vào lockfile hoặc quy trình dependency management phù hợp.

`custom` là vùng cấu hình để lưu giá trị phục vụ plugin hoặc tái sử dụng trong file. Không đặt logic nghiệp vụ hoặc secret tùy tiện vào `custom`; cấu hình nên có tên rõ ràng và dễ review.

## 9. Xem cấu hình đã được giải quyết và package trước deploy

YAML có thể chứa biến từ CLI, environment, provider hoặc CloudFormation. Trước khi triển khai, hãy kiểm tra cấu hình sau khi Framework thay thế biến.

In cấu hình đã giải quyết:

~~~bash
serverless print --stage dev
~~~

Tạo package mà chưa deploy:

~~~bash
serverless package --stage dev
~~~

Các bước này giúp phát hiện biến không được resolve, sai đường dẫn artifact, thiếu file hoặc cấu hình function/event không hợp lệ trước khi thay đổi stack trên AWS.

Không đưa kết quả `serverless print` vào nơi công khai nếu cấu hình có chứa giá trị nhạy cảm được resolve từ environment hoặc secret source. Hạn chế quyền đọc file package và log CI/CD.

## 10. Deploy và quản lý vòng đời service

Serverless Framework cung cấp các lệnh để kiểm tra, đóng gói, triển khai, gọi function và xem log. Nên phân biệt thao tác deploy toàn service với cập nhật riêng code của một function.

### 10.1. Chuẩn bị môi trường

Trước khi deploy:

1. Cài Node.js và Serverless Framework CLI theo phiên bản tổ chức đang sử dụng.
2. Cài AWS CLI và cấu hình danh tính deploy.
3. Chọn AWS account, region và stage đích.
4. Bật các AWS service/API cần thiết nếu quy trình yêu cầu.
5. Kiểm tra IAM permission cho người deploy và service role của CloudFormation.
6. Build Java artifact bằng Maven.
7. Kiểm tra cấu hình đã resolve và package trước khi thay đổi stack.

Không commit AWS access key vào repository. Với CI/CD, ưu tiên danh tính ngắn hạn qua OIDC hoặc cơ chế assume role. Tách quyền deploy khỏi quyền runtime của Lambda: deployer cần tạo/cập nhật resource, còn runtime role chỉ cần quyền mà function sử dụng khi chạy.

### 10.2. Triển khai service

Ví dụ:

~~~bash
mvn clean package
serverless print --stage dev
serverless package --stage dev
serverless deploy --stage dev --region ap-southeast-1
~~~

Framework tạo hoặc cập nhật CloudFormation stack cho service. Sau khi deploy, kiểm tra output và function URL/API endpoint được tạo. Không giả định deploy thành công đồng nghĩa mọi lời gọi dependency đều hoạt động; cần chạy smoke test qua trigger thật.

Đối với production, nên triển khai trước vào stage thử nghiệm, xác minh request/event, log, quyền và tải rồi mới triển khai production.

### 10.3. Cập nhật code riêng một function

Có thể dùng lệnh:

~~~bash
serverless deploy function --function createOrder --stage dev
~~~

Lệnh này cập nhật code của function được chỉ định và phù hợp khi chỉ thay đổi code mà không đổi cấu hình hạ tầng. Nếu thay đổi event, IAM, environment, memory, timeout hoặc resource, hãy deploy toàn service để CloudFormation được cập nhật.

Không dùng deploy function riêng lẻ như thay thế cho quản lý IaC. Nếu chỉ code đã thay đổi trên AWS mà source/deployment state không được cập nhật đồng bộ, các lần deploy sau có thể tạo khác biệt khó truy vết.

### 10.4. Gọi function và xem thông tin

Gọi function trực tiếp:

~~~bash
serverless invoke --function createOrder --stage dev --data '{"queryStringParameters":{"name":"Lan"}}'
~~~

Xem thông tin service:

~~~bash
serverless info --stage dev
~~~

Xem log của function:

~~~bash
serverless logs --function createOrder --stage dev --tail
~~~

Lệnh invoke trực tiếp không đi qua đầy đủ đường đi HTTP API hoặc event source mapping. Để kiểm tra tích hợp thực tế, hãy gọi API Gateway endpoint hoặc phát message/event từ đúng dịch vụ nguồn.

### 10.5. Gỡ service

Lệnh:

~~~bash
serverless remove --stage dev
~~~

sẽ yêu cầu Framework gỡ CloudFormation stack do service quản lý và các resource được stack sở hữu theo chính sách xóa của chúng. Đây có thể là thao tác phá hủy dữ liệu nếu resource được cấu hình xóa cùng stack. Trước khi chạy, kiểm tra retention policy, snapshot/backup, resource có dữ liệu và tài nguyên được chia sẻ với hệ thống khác.

Không dùng lệnh remove như cách dọn môi trường production. Với database, bucket hoặc queue chứa dữ liệu quan trọng, thiết kế retention và backup ngay từ lúc khai báo resource.

## 11. Retry, idempotency và xử lý lỗi

Serverless Framework khai báo trigger và một số chính sách của dịch vụ, nhưng logic xử lý lỗi vẫn thuộc về ứng dụng. Mỗi trigger có semantics riêng.

### 11.1. HTTP API

HTTP API thường gọi Lambda đồng bộ. Nếu client timeout hoặc nhận lỗi mạng, client có thể không biết function đã thực hiện side effect hay chưa. Client thử lại có thể tạo thao tác trùng.

Với endpoint tạo đơn hàng hoặc thanh toán:

- Nhận header Idempotency-Key từ client hoặc tạo khóa nghiệp vụ ổn định.
- Lưu khóa và kết quả vào database với unique constraint.
- Nếu nhận lại cùng khóa, trả kết quả đã lưu thay vì tạo nghiệp vụ mới.
- Đặt timeout dependency ngắn hơn timeout Lambda và deadline của client.
- Phân biệt lỗi xác thực, lỗi input, conflict và lỗi server.

### 11.2. SQS và batch processing

SQS event source mapping poll message và gửi batch vào Lambda. Nếu handler lỗi, message có thể xuất hiện lại sau visibility timeout. Nếu một message trong batch lỗi và handler không dùng partial batch response, cả batch có thể bị retry.

Handler nên xử lý từng message độc lập và trả về danh sách message ID thất bại khi bật ReportBatchItemFailures. Mỗi message cần idempotency key ổn định để message được giao lại không tạo tác động lặp.

Đối với lỗi dữ liệu vĩnh viễn, cần chính sách quarantine hoặc DLQ và cảnh báo. Đừng để message poison được retry mãi mà không có người theo dõi.

### 11.3. Asynchronous invocation và EventBridge

Với asynchronous Lambda invocation, Lambda có cơ chế retry cho một số lỗi function theo cấu hình dịch vụ. EventBridge cũng có retry policy và dead-letter queue cho target. Những cơ chế này khác với SQS event source mapping.

Khi khai báo trigger, kiểm tra retry policy tại đúng dịch vụ nguồn. Không suy luận rằng một cấu hình retry của SQS tự động áp dụng cho EventBridge hoặc async invoke.

### 11.4. Idempotency key trong Java

Ví dụ một handler tạo khóa từ event ID hoặc khóa nghiệp vụ:

~~~java
String idempotencyKey = eventId + ":" + operationVersion;
~~~

Đây chỉ là bước tạo khóa. Để có hiệu lực, ứng dụng cần lưu khóa bền vững bằng thao tác nguyên tử, kiểm tra trạng thái đã hoàn tất, và phối hợp việc ghi kết quả với tác động nghiệp vụ. Một HashSet hoặc static Map trong JVM không bảo đảm chống trùng khi Lambda chạy nhiều instance hoặc bị khởi tạo lại.

Nếu side effect nằm ở dịch vụ bên ngoài, dùng idempotency key mà dịch vụ đó hỗ trợ hoặc một quy trình outbox/inbox và đối soát. Không giả định timeout đồng nghĩa thao tác bên ngoài đã thất bại.

## 12. Concurrency, memory và giới hạn downstream

Một khai báo service có thể tạo nhiều Lambda function và mỗi function có thể mở rộng độc lập. Tổng tải lên database hoặc API ngoài là tổng của các invocation đang chạy trên tất cả instance và function liên quan.

### 12.1. Giới hạn concurrency

Có thể giới hạn concurrency cho một function bằng cấu hình tương ứng:

~~~yaml
functions:
  processOrder:
    handler: com.example.ProcessOrderHandler
    reservedConcurrency: 20
~~~

Reserved concurrency vừa đặt giới hạn đồng thời, vừa dành phần concurrency đó cho function theo cơ chế Lambda. Nếu đặt quá thấp, function có thể bị throttle; nếu đặt quá cao, downstream có thể bị quá tải.

Với SQS, có thể điều chỉnh batch size và maximum concurrency của event source mapping theo khả năng của hệ thống. Hãy tính cả số queue, số function và các producer khác cùng truy cập database.

### 12.2. Memory và timeout

Cấu hình memory ảnh hưởng đến RAM và năng lực CPU của Lambda. Tăng memory có thể giảm duration cho workload CPU-intensive nhưng làm tăng đơn giá theo thời gian. Timeout phải phù hợp với p95/p99 và deadline của trigger/caller.

Ví dụ:

~~~yaml
functions:
  resizeImage:
    handler: com.example.ResizeImageHandler
    memorySize: 2048
    timeout: 90
    ephemeralStorageSize: 2048
~~~

Cấu hình trên minh họa function xử lý ảnh có thể cần memory và /tmp lớn hơn. Thuộc tính ephemeralStorageSize là dung lượng tạm của Lambda tại /tmp; kiểm tra thuộc tính được hỗ trợ bởi phiên bản Serverless Framework và runtime đang dùng trước khi triển khai.

### 12.3. Tính capacity từ downstream

Giả sử mỗi Lambda invocation mở tối đa 5 database connection và function có concurrency 40. Database có thể nhận khoảng 200 connection từ function đó. Nếu có thêm function khác hoặc service khác dùng cùng database, tổng số kết nối còn cao hơn.

Hãy đặt pool size, reserved concurrency, event source maximum concurrency và batch size dựa trên capacity thực tế của downstream. Tăng concurrency không tự động làm throughput hữu ích tăng nếu database đã là bottleneck.

## 13. Logging, monitoring và chi phí

Serverless Framework có thể cấu hình retention log và triển khai các tài nguyên cần thiết, nhưng vận hành vẫn cần metric, dashboard và cảnh báo ở CloudWatch.

### 13.1. Log và metric

Các chỉ số nên theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Invocation count | Số lần function được gọi |
| Duration p50/p95/p99 | Thời gian thực thi theo percentile |
| Errors | Số invocation lỗi |
| Throttles | Số invocation bị giới hạn concurrency |
| Concurrent executions | Mức chạy đồng thời |
| Iterator age hoặc queue age | Độ trễ xử lý sự kiện/queue |
| DLQ messages | Message lỗi cần điều tra |
| Max memory used | Dấu hiệu thiếu memory |
| Downstream latency | Thời gian chờ database hoặc API |

Log nên chứa request ID, event ID, operation ID và mã kết quả để truy vết. Không log credential, token hoặc dữ liệu cá nhân không cần thiết. Với HTTP API, có thể dùng correlation ID xuyên suốt client, API Gateway, Lambda và dependency.

### 13.2. Retention log

Có thể cấu hình log retention ở provider:

~~~yaml
provider:
  logRetentionInDays: 14
~~~

Chọn retention dựa trên yêu cầu điều tra, bảo mật và chi phí lưu trữ. Log dài hạn có thể được export sang kho lưu trữ phù hợp; không giữ log vô thời hạn nếu không có yêu cầu.

### 13.3. Những thành phần tạo chi phí

Chi phí của ứng dụng không chỉ là Lambda invocation:

- Lambda request count và thời gian compute theo memory.
- API Gateway request và dữ liệu truyền.
- SQS request, message retention và DLQ.
- EventBridge event và rule invocation.
- DynamoDB read/write, storage và backup.
- S3 storage, request và data transfer.
- CloudWatch log ingestion, retention và metric.
- NAT Gateway hoặc network egress nếu kiến trúc sử dụng.

Một service có thể có ít invocation nhưng vẫn tốn chi phí do NAT Gateway, log volume hoặc resource chạy thường trực. Khi thiết kế, ước lượng cost per successful request/job và theo dõi chi phí theo stage/tag.

## 14. CI/CD cho Serverless Framework

CI/CD nên tái tạo cùng một quy trình build, package, kiểm tra và deploy. Không phụ thuộc vào file JAR còn sót lại từ lần build trước trên máy developer.

Một pipeline đơn giản:

~~~mermaid
flowchart TD
    A[Commit hoặc pull request] --> B[Compile và unit test]
    B --> C[Maven package]
    C --> D[Kiểm tra serverless.yml]
    D --> E[Serverless package]
    E --> F[Review artifact/template]
    F --> G[Deploy stage test]
    G --> H[Smoke test và kiểm tra log]
    H --> I[Approval hoặc policy gate]
    I --> J[Deploy production]
~~~

Các bước thường gồm:

1. Checkout source và cài đúng Java/Maven/Node version.
2. Chạy unit test và static checks.
3. Build JAR có dependency.
4. Kiểm tra serverless.yml và biến được resolve.
5. Tạo package CloudFormation và artifact.
6. Lưu artifact theo commit/version để có thể truy vết.
7. Deploy vào stage test.
8. Chạy smoke test qua HTTP API hoặc event trigger.
9. Kiểm tra log, IAM diff, error rate và downstream.
10. Deploy production theo quyền và quy trình của tổ chức.

Trong CI/CD, cấp AWS credential qua OIDC hoặc assume role với permission tối thiểu. Không lưu access key lâu dài trong file cấu hình hoặc log pipeline.

### 14.1. Quản lý version và rollback

Lưu version code, Maven artifact, Serverless Framework version và cấu hình deploy cùng một commit. Khi deploy lỗi, có thể redeploy artifact đã biết hoặc khôi phục CloudFormation stack theo quy trình phù hợp.

Rollback code không nhất thiết đảo ngược mọi thay đổi dữ liệu đã thực hiện. Với thay đổi schema database, queue payload hoặc event contract, cần thiết kế tương thích ngược và migration riêng. Không xem CloudFormation rollback là cơ chế hoàn tác nghiệp vụ.

## 15. Những lỗi thường gặp

- **Không build JAR trước khi deploy:** Framework không tìm thấy artifact được khai báo.
- **JAR thiếu dependency:** function compile được nhưng lỗi ClassNotFoundException lúc runtime.
- **Sai handler name:** class không tồn tại hoặc không implement đúng interface.
- **Nhầm HTTP API và REST API:** event payload và integration contract không tương thích.
- **Cấu hình stage dùng chung resource:** dev và prod ghi vào cùng table hoặc bucket ngoài ý muốn.
- **IAM role quá rộng:** function có quyền truy cập tài nguyên không cần thiết.
- **Quên visibility timeout:** SQS giao lại message trong lúc invocation trước còn xử lý.
- **Không có idempotency:** retry tạo đơn hàng hoặc tác động lặp.
- **Không cấu hình DLQ:** message poison không có nơi cô lập và điều tra.
- **Dùng deploy function riêng lẻ sau khi đổi hạ tầng:** CloudFormation stack không được cập nhật theo cấu hình mới.
- **Xóa stack mà không xem retention:** resource có thể bị xóa cùng dữ liệu.
- **Tin local emulator giống AWS hoàn toàn:** khác biệt IAM, event delivery, retry và scaling chỉ xuất hiện khi chạy trên cloud.
- **Không theo dõi chi phí phụ trợ:** log, network và database có thể chiếm phần lớn chi phí.

## 16. Checklist trước khi deploy production

- [ ] serverless.yml có service, provider, stage và runtime rõ ràng.
- [ ] Java handler implement đúng AWS Lambda handler interface.
- [ ] Maven artifact có đủ dependency runtime và đúng đường dẫn.
- [ ] Function/event mapping khớp payload contract.
- [ ] HTTP endpoint có authentication/authorization phù hợp.
- [ ] SQS/EventBridge retry và DLQ đã được xác định.
- [ ] Handler có idempotency cho tác động có side effect.
- [ ] IAM role chỉ có quyền tối thiểu cần thiết.
- [ ] Environment variable không chứa secret hardcode.
- [ ] Memory, timeout và concurrency phù hợp với workload.
- [ ] Visibility timeout phù hợp với function timeout và batch window.
- [ ] Resource có tên/stage riêng và retention policy phù hợp.
- [ ] serverless print và serverless package chạy thành công.
- [ ] Đã deploy stage thử nghiệm và chạy smoke test qua trigger thật.
- [ ] Có log, metric, dashboard và cảnh báo.
- [ ] CI/CD dùng danh tính deploy ngắn hạn và lưu artifact theo commit.
- [ ] Có kế hoạch rollback code và xử lý migration dữ liệu.

## 17. Tự kiểm tra

**Câu 1.** Serverless Framework đóng vai trò gì trong một ứng dụng Java serverless?

**Gợi ý trả lời:** Framework đọc cấu hình service, function, event, resource và provider; đóng gói artifact và tạo/cập nhật CloudFormation stack để triển khai tài nguyên AWS. Logic Java vẫn chạy trong Lambda runtime.

**Câu 2.** Phân biệt service, function, event và resource.

**Gợi ý trả lời:** Service là đơn vị triển khai; function là code được Lambda thực thi; event là trigger gọi function; resource là tài nguyên hạ tầng như queue, table hoặc bucket.

**Câu 3.** Vì sao phải build Java JAR trước khi chạy Serverless Framework deploy khi dùng package.artifact?

**Gợi ý trả lời:** Framework sử dụng artifact có sẵn ở đường dẫn đã khai báo. Nếu Maven chưa tạo file hoặc JAR thiếu dependency, package/deploy sẽ thất bại hoặc function lỗi lúc runtime.

**Câu 4.** Vì sao serverless deploy function không phù hợp sau khi thay đổi IAM hoặc event trigger?

**Gợi ý trả lời:** Lệnh này cập nhật code của một function, không đồng bộ toàn bộ thay đổi hạ tầng trong CloudFormation. Khi thay đổi cấu hình hoặc resource, cần deploy service để stack được cập nhật.

**Câu 5.** Vì sao cần stage riêng và resource naming có stage?

**Gợi ý trả lời:** Stage giúp cô lập dev/test/prod. Tên resource có stage ngăn các môi trường ghi đè dữ liệu hoặc dùng chung tài nguyên ngoài ý muốn.

**Bài tập tình huống:** Thiết kế một service Java nhận đơn hàng qua HTTP API, ghi đơn vào DynamoDB và gửi message vào SQS. Một worker khác xử lý message và phát event OrderProcessed lên EventBridge. Hãy khai báo các function, event, resource, environment variable và IAM permission trong serverless.yml. Xác định memory, timeout, batch size, visibility timeout, DLQ và idempotency key. Đề xuất các lệnh build, package, deploy stage dev và smoke test.

**Gợi ý:** Tách createOrder và processOrder thành hai function. HTTP handler xác thực input, tạo order ID ổn định và ghi dữ liệu; sau khi commit, publish message hoặc dùng outbox để tránh mất message giữa hai thao tác. Worker đọc SQS batch, xử lý từng message idempotently và trả partial batch failures. Khai báo DynamoDB table, SQS queue, DLQ và EventBridge event bus/rule nếu cần. Cấp PutItem cho producer, quyền đọc/xóa message cho worker và quyền publish event cho worker. Đặt visibility timeout ít nhất sáu lần timeout cộng batch window theo hướng dẫn AWS hiện hành. Chạy Maven package, kiểm tra cấu hình đã resolve, package, deploy dev rồi gửi HTTP request và xác minh item, message, event cùng log.

## Kết luận

Serverless Framework biến cấu hình service thành các tài nguyên serverless có thể triển khai và quản lý bằng IaC. Với Java, Maven tạo artifact; serverless.yml khai báo provider, handler, event, resource, IAM, stage và package. Một cấu hình tốt phải thể hiện đúng trigger contract, quyền tối thiểu, retry/idempotency, giới hạn concurrency và vòng đời dữ liệu. Quy trình build, print, package, deploy và smoke test theo stage giúp phát hiện lỗi trước production. Khi vận hành, cần theo dõi Lambda cùng API Gateway, queue, database, log và network để kiểm soát độ tin cậy và chi phí của toàn service.
