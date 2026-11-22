# Lambda runtime, handler và triển khai bằng ZIP hoặc container

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **AWS Lambda**, **runtime**, **handler**, **event**, **context**, **execution environment** và cách Lambda khởi tạo, thực thi, tái sử dụng môi trường chạy.
- Nhận diện runtime AWS quản lý, runtime tùy chỉnh và sự khác biệt giữa **mã nguồn Java**, **bản biên dịch**, **đóng gói dependency**, **hình thức triển khai**.
- Viết Java handler theo **RequestHandler** hoặc **RequestStreamHandler**, đặt giá trị handler đúng định dạng và phân biệt payload invoke trực tiếp với sự kiện API Gateway, S3, SQS.
- Build và triển khai **Java Lambda bằng JAR/ZIP**, xử lý classpath, Maven Shade, Lambda layers, giới hạn dung lượng và lỗi `ClassNotFoundException`.
- Build và triển khai **Lambda container image** từ AWS Java base image, dùng Runtime Interface Client, ECR, kiến trúc CPU phù hợp và thử cục bộ.
- Chọn **ZIP hay container** theo mức độ phức tạp dependency, vòng đời artifact, quy trình CI/CD, giới hạn gói và chi phí vận hành.
- Thiết kế quyền **IAM execution role**, resource-based permission, AWS KMS, VPC, Secrets Manager, logging và quyền truy cập sự kiện.
- Quản lý **versions/aliases**, cold start, memory/timeout, concurrency, lỗi retry, idempotency, monitoring, khả năng phục hồi và ngân sách.
- Chẩn đoán Lambda không thể khởi tạo, handler sai, image không được truy cập, timeout, hết bộ nhớ, không kết nối VPC hoặc không có quyền AWS API.

**Bối cảnh:** Bài thuộc chương **Điện toán Lambda**, module **CLOUD_PROVIDERS_AWS**. Trong hệ sinh thái AWS gồm **Region/AZ, IAM, VPC, EC2/ECS/EKS, S3, RDS, DynamoDB, SQS, API Gateway và CloudWatch**, Lambda phù hợp khi muốn chạy logic theo sự kiện mà không phải quản trị một nhóm máy chủ luôn hoạt động. Mục tiêu thiết kế không chỉ là chạy được hàm, mà còn **an toàn, quan sát được, mở rộng, phục hồi và kiểm soát chi phí**.

> **Phạm vi:** Bài dùng **AWS Lambda Event Function** thông thường với **Java 21**, triển khai theo hai cách: JAR/ZIP và container image. Lambda có thêm các biến thể/chế độ compute tùy thời điểm; đừng lấy một quota mặc định của mô hình này để suy ra mọi chế độ Lambda. Ví dụ dùng tài khoản, Region và ARN **minh họa**, không chạy trên production khi chưa rà soát.

## 1. AWS Lambda là gì, và khác EC2/ECS ở đâu?

**AWS Lambda** là dịch vụ thực thi mã theo yêu cầu hoặc theo sự kiện. Bạn cung cấp artifact của ứng dụng, cấu hình runtime, tài nguyên, IAM role, nguồn kích hoạt và giới hạn. AWS quản lý phần lớn hạ tầng thực thi và tạo thêm **execution environments** để xử lý lượng yêu cầu tăng trong khả năng quota/cấu hình.

Ví dụ một hệ thống bán hàng:

1. Người dùng đặt hàng qua API.
2. Ứng dụng đưa sự kiện `OrderCreated` vào **Amazon SQS**.
3. Lambda nhận một batch message, tạo hóa đơn PDF hoặc ghi dữ liệu tổng hợp.
4. Kết quả được lưu **S3** và trạng thái được ghi vào **DynamoDB/RDS**.
5. CloudWatch ghi metric, log, alarm; lỗi được retry/DLQ theo cơ chế nguồn sự kiện.

~~~mermaid
flowchart LR
    Client[Người dùng] --> API[API Gateway / ứng dụng]
    API --> Queue[(Amazon SQS)]
    Queue --> ESM[Event source mapping]
    ESM --> Lambda[Lambda function: Java handler]
    Lambda --> S3[(S3: hóa đơn)]
    Lambda --> DB[(DynamoDB / RDS)]
    Lambda --> Logs[CloudWatch]
~~~

| Giải pháp | Bạn quản lý | Cách hoạt động phù hợp |
| --- | --- | --- |
| **EC2** | OS, patching, service/process, capacity và deployment trên máy | Ứng dụng chạy lâu dài, yêu cầu host tùy chỉnh |
| **ECS/EKS** | Image, service/task/Pod, network/capacity tùy mô hình | Web/API/microservices liên tục, container orchestration |
| **Lambda** | Mã, dependencies, runtime/config, IAM và hành vi ứng dụng | Sự kiện, jobs ngắn, API có burst, xử lý bất đồng bộ |
| **Step Functions** | Workflow và trạng thái điều phối | Nhiều bước, retry/timeout/compensation; có thể gọi Lambda |

**Lambda không phải container service chạy HTTP server mãi mãi.** Bạn cung cấp **handler**, Lambda gọi handler khi có sự kiện. Container image của Lambda cũng phải tuân theo **Lambda Runtime API**, không phải cứ đưa Docker image của một web server bất kỳ vào là hoạt động.

Lambda đặc biệt hữu ích cho tác vụ không cần duy trì máy chủ riêng, nhưng phải xét **timeout, memory, concurrency, cold start, số request, network và chi phí**. Công việc rất dài hoặc cần kết nối lâu sống, GPU/host đặc biệt, hay dữ liệu lớn gắn filesystem theo mô hình riêng có thể phù hợp ECS, Batch hoặc giải pháp khác hơn.

## 2. Runtime: môi trường đưa sự kiện vào mã ứng dụng

**Runtime** là lớp phần mềm cung cấp môi trường ngôn ngữ và giao tiếp giữa hệ thống thực thi Lambda với handler. Runtime nhận event/context, gọi mã phù hợp rồi gửi response hoặc error về Lambda.

### 2.1. Managed runtime

AWS quản lý những runtime chính thức cho Java, Python, Node.js, .NET và những ngôn ngữ được công bố. Khi dùng **ZIP/JAR**, bạn chọn **runtime identifier** trong cấu hình function, ví dụ:

| Runtime Java | Identifier hiện hành | Điểm cần nhớ |
| --- | --- | --- |
| Java 25 | `java25` | Runtime mới trên Amazon Linux 2023 |
| Java 21 | `java21` | Runtime dùng trong ví dụ bài học |
| Java 17 trên AL2023 | `java17.al2023` | Phân biệt với `java17` trên Amazon Linux 2 |
| Java 11 trên AL2023 | `java11.al2023` | Phù hợp khi chưa nâng cấp được Java |
| Java 17 đời AL2 | `java17` | Runtime cũ hơn, cần xem lịch deprecation cụ thể |

Danh sách runtime hỗ trợ và lịch ngừng hỗ trợ thay đổi theo thời gian. Trước khi dùng, mở tài liệu **Lambda runtimes**, kiểm tra Region và thời gian còn được hỗ trợ; không chọn runtime cũ chỉ vì Maven project đang build bằng Java phiên bản đó.

**Runtime và compiler phải tương thích.** Ví dụ build bytecode Java 25 rồi chạy bằng runtime Java 21 có thể gây `UnsupportedClassVersionError`. Khi ứng dụng build cho Java 21, cần chọn runtime Java 21 hoặc môi trường hỗ trợ bytecode và dependencies đã được thử.

### 2.2. Custom runtime

Với ngôn ngữ hoặc phiên bản không có managed runtime phù hợp, có thể dùng **OS-only runtime** như `provided.al2023` và tự triển khai cơ chế gọi **Lambda Runtime API**, thường qua một **runtime interface client**. Đây là giải pháp có tính linh hoạt cao hơn nhưng tăng trách nhiệm bảo trì, bảo mật và tương thích.

### 2.3. Runtime trong container image

Với **container image**, thông thường runtime/handler nằm trong **image** (hoặc được cấu hình qua image configuration). Khi tạo function kiểu image, bạn **không cung cấp `--runtime java21` và `--handler ...` như function kiểu ZIP**. AWS Java Lambda base image đã có runtime và Runtime Interface Client.

**Trách nhiệm cập nhật khác nhau:**

- **ZIP + managed runtime:** Lambda quản lý và cập nhật bản vá runtime theo cơ chế runtime management, nhưng bạn vẫn phải cập nhật dependency/SDK trong artifact.
- **Container image:** bạn kiểm soát image và phải **rebuild, scan, push, deploy lại** khi base image hoặc library cần vá, kể cả khi bắt đầu từ AWS official base image.
- **Custom runtime:** bạn tự chịu trách nhiệm nhiều hơn về runtime bootstrap và lớp tích hợp.

## 3. Handler: điểm bắt đầu xử lý sự kiện

**Handler** là hàm/method được Lambda gọi mỗi lần invoke. Tùy ngôn ngữ, handler nhận input event và context theo runtime. Java thường dùng class và method.

Định dạng handler Java:

~~~text
com.example.lambda.OrderHandler::handleRequest
        └── tên class ┘    └── tên method
~~~

**Chỗ hay nhầm:**

- `OrderHandler` là **class Java**, không phải tên file JAR hay function name.
- `handleRequest` phải có signature tương thích; phương thức có thể được định nghĩa qua interface hỗ trợ.
- `com.example.lambda` là package chính xác; sai một ký tự sẽ gặp lỗi load class hoặc tìm method.
- Lambda function `orders-zip-lab` là tên resource AWS, **không phải** class handler.

### Hai interface Java chuẩn

AWS cung cấp package `com.amazonaws.services.lambda.runtime`:

| Interface | Đầu vào/đầu ra | Khi sử dụng |
| --- | --- | --- |
| **`RequestHandler<I,O>`** | Java object vào và trả object ra; runtime serialize/deserialize | JSON event và response đơn giản, typed DTO/record |
| **`RequestStreamHandler`** | `InputStream` và `OutputStream` | Tự xử lý byte streams, serialization custom |
| **Method không implement interface** | Signature tương thích, thường nhận input + optional `Context` | Handler đơn giản, vẫn phải đặt tên method chính xác |

**Interface giúp kiểm tra type/signature lúc build**, còn việc event JSON có đúng cấu trúc bạn mong đợi không vẫn cần test. Event của S3, SQS và API Gateway có cấu trúc khác nhau; đừng xem mọi input đều là một object `{"orderId": "..."}`.

## 4. Viết handler Java RequestHandler hoàn chỉnh

Để tập trung vào runtime, ví dụ dùng **direct invocation event**:

~~~json
{
  "orderId": "ORD-1001",
  "currency": "VND"
}
~~~

File `src/main/java/com/example/lambda/OrderHandler.java`:

~~~java
package com.example.lambda;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;

import java.util.Map;
import java.util.Objects;

public class OrderHandler implements RequestHandler<Map<String, Object>, Map<String, Object>> {

    // Instance có thể được Lambda giữ lại cho các lần invoke tiếp theo.
    // Chỉ giữ trạng thái/đối tượng dùng chung khi thread-safe và hợp lệ.
    public OrderHandler() {
    }

    @Override
    public Map<String, Object> handleRequest(Map<String, Object> event, Context context) {
        String orderId = Objects.toString(event.get("orderId"), "").trim();
        if (orderId.isEmpty()) {
            throw new IllegalArgumentException("orderId is required");
        }

        String currency = Objects.toString(event.getOrDefault("currency", "VND"));

        // Chỉ log dữ liệu không bí mật; không log nguyên payload nhạy cảm.
        context.getLogger().log("Accepted order: " + orderId);

        return Map.of(
            "orderId", orderId,
            "currency", currency,
            "accepted", true
        );
    }
}
~~~

**Ý nghĩa:**

- `RequestHandler<Map<String,Object>, Map<String,Object>>` giúp runtime chuyển JSON object đầu vào thành Map và serialize kết quả ra JSON.
- `Context` cung cấp request ID, remaining time, log API và thông tin invocation; không dùng Context như nơi cất giữ secret.
- `IllegalArgumentException` thể hiện **function error** khi input sai. Với invoke bất đồng bộ, lỗi có thể được retry nên cần phân loại lỗi dữ liệu vĩnh viễn với lỗi tạm thời.
- Constructor và thành phần khởi tạo ngoài handler có thể chạy trong pha **Init**; **handler** được gọi ở pha **Invoke**.
- Ví dụ chưa ghi DB/S3, nên chưa cần quyền S3/KMS/DB. Khi bổ sung API call, role phải được cấp quyền theo tài nguyên thực.

### Vì sao không đọc toàn bộ event như `Map<String,String>` cho mọi trigger?

Với một số event, JSON chứa map lồng nhau, array, boolean, number, base64 payload hoặc metadata. `Map<String,Object>` hoặc typed event class giúp giữ cấu trúc tốt hơn. Thư viện `aws-lambda-java-events` có những DTO event phù hợp như API Gateway, S3 hoặc SQS; phải chọn đúng loại và version của trigger.

**Không nhầm trực tiếp invoke payload với API Gateway event.** Nếu API Gateway proxy integration truyền `body` dạng chuỗi JSON kèm headers/context, code đọc `event.get("orderId")` ở cấp root sẽ không ra dữ liệu mong đợi. Cần parse `body` hoặc dùng adapter/framework thích hợp.

## 5. RequestStreamHandler: khi cần tự điều khiển serialization

Với `RequestStreamHandler`, Lambda cung cấp luồng bytes:

~~~java
package com.example.lambda;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestStreamHandler;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class EchoStreamHandler implements RequestStreamHandler {

    @Override
    public void handleRequest(
        InputStream input,
        OutputStream output,
        Context context
    ) throws IOException {
        byte[] eventBytes = input.readAllBytes();

        // Ví dụ nhận nguyên JSON event và trả lại như JSON response.
        // Chỉ minh họa stream; không dùng echo với dữ liệu bí mật trên production.
        output.write(eventBytes);
        output.flush();
    }
}
~~~

Handler config:

~~~text
com.example.lambda.EchoStreamHandler::handleRequest
~~~

Dạng stream có ích khi bạn muốn tự chọn parser, codec, không phụ thuộc quá nhiều vào mapping mặc định của runtime hoặc xử lý contract dữ liệu riêng. Tuy nhiên `readAllBytes()` **nạp toàn bộ event vào RAM**, không phải cách xử lý streaming payload lớn trên production. Lambda invocation vẫn chịu giới hạn kích thước event; muốn xử lý file lớn thường nhận một **S3 object key** rồi đọc object qua SDK theo luồng phù hợp.

## 6. Event source và kiểu invoke: handler nhận dữ liệu nào?

Một function có thể được gọi bởi nhiều dịch vụ. Phân biệt **direct/synchronous invoke**, **asynchronous invoke** và **event source mapping (poll-based)**:

| Nguồn | Luồng phổ biến | Payload/điều kiện | Lỗi xử lý |
| --- | --- | --- | --- |
| **AWS CLI/SDK Invoke** | Đồng bộ `RequestResponse` hoặc bất đồng bộ `Event` | Payload do client cung cấp | Đồng bộ: xem response/`FunctionError`; bất đồng bộ: retry/destination theo chính sách |
| **API Gateway** | Đồng bộ | Event có headers, path, method, body, context theo integration | Response contract, timeout, HTTP code, integration error |
| **Lambda Function URL** | Đồng bộ HTTP | HTTP event theo payload format | Authorization IAM/NONE, CORS và response tương ứng |
| **Amazon S3 notifications** | Bất đồng bộ | Event có bucket/key/records | Có thể trùng hoặc đến không đúng thứ tự; idempotent |
| **EventBridge** | Bất đồng bộ | Event có `source`, `detail-type`, `detail` | Retry và DLQ/destination theo cấu hình dịch vụ |
| **SQS** | Event source mapping poll queue | Batch `Records`, có receipt handle/message body | Retry batch/message, visibility timeout, DLQ |
| **Kinesis/DynamoDB Streams** | Event source mapping đọc shard | Records theo stream/batch | Checkpoint, retry, ordering/bisect hoặc partial batch theo hỗ trợ |

**Sự khác biệt quan trọng:** Khi API Gateway gọi Lambda đồng bộ, một lỗi handler có thể dẫn tới HTTP error tùy mapping; với **SQS**, Lambda poll một batch records và phải quản lý thành công/thất bại để tránh xử lý trùng/lặp vô hạn. Không có một cơ chế retry giống nhau cho tất cả trigger.

Ví dụ event SQS (rút gọn):

~~~json
{
  "Records": [
    {
      "messageId": "m-123",
      "body": "{\"orderId\":\"ORD-1001\"}",
      "eventSource": "aws:sqs"
    }
  ]
}
~~~

Nếu handler Java mong `orderId` trực tiếp ở root thì sẽ lỗi. Khi dùng SQS, hãy parse `Records[i].body` rồi xử lý từng message; kết hợp **idempotency key**, partial batch response theo trường hợp hỗ trợ và DLQ/alert phù hợp.

## 7. Lambda execution environment và vòng đời Init / Invoke

Để xử lý sự kiện, Lambda cấp một **execution environment** chứa runtime, function code và tài nguyên cấu hình. Môi trường có thể được **tái sử dụng** cho nhiều invoke, nhưng AWS **không bảo đảm cùng một instance được dùng mãi mãi**.

~~~mermaid
flowchart TD
    A[Event đến Lambda] --> B{Có environment sẵn?}
    B -->|Không| C[Init: tải runtime, code, dependencies]
    C --> D[Init handler class / static resources]
    B -->|Có| E[Warm invoke]
    D --> F[Invoke handler]
    E --> F
    F --> G[Return / error / timeout]
    G --> H{Có thể tái sử dụng?}
    H -->|Có| I[Environment tạm thời được giữ]
    I --> E
    H -->|Không| J[Environment bị loại bỏ]
~~~

### Init

Lambda chuẩn bị runtime, tải code/dependencies và thực hiện phần khởi tạo được định nghĩa ngoài handler. Với Java, startup JVM, class loading, dependency injection và static initialization có thể làm **cold start** dài.

Nên:

- Giảm dependency/JAR không cần thiết;
- tránh dựng toàn bộ web server nếu chỉ xử lý một event đơn giản;
- tạo AWS SDK client/HTTP connection pool có thể tái sử dụng ở phạm vi instance khi thread-safe;
- không thực hiện migration nặng hoặc gọi service mạng không có timeout trong static initializer;
- đặt timeout hợp lý và log phase init nếu có.

### Invoke

Lambda gọi handler theo sự kiện. Một environment của mô hình Lambda Event Function thông thường **không xử lý nhiều invocations đồng thời trong cùng một execution environment**, nhưng có thể chứa background threads hoặc async operations của ứng dụng; phải quản lý thread safety và kết thúc tài nguyên đúng cách.

### Freeze / reuse

Sau invoke, Lambda có thể đóng băng rồi tái sử dụng execution environment. Biến static và nội dung `/tmp` **có thể còn**, nhưng không được coi là một cơ sở dữ liệu bền vững hoặc trạng thái chia sẻ giữa các environments.

**Không lưu giỏ hàng, phiên người dùng hay kết quả giao dịch duy nhất trong RAM của Lambda.** Với trạng thái cần bền vững, dùng S3/DynamoDB/RDS/ElastiCache theo bài toán.

### SnapStart và Provisioned Concurrency

Đối với những runtime/configuration hỗ trợ, **Lambda SnapStart** có thể giảm thời gian init bằng cách lưu/khôi phục trạng thái khởi tạo của phiên bản đã publish. Ứng dụng phải bảo đảm **tính duy nhất của secret/random state, network connections và state cần được tái tạo sau restore**; snapshot khởi tạo không phải checkpoint của mỗi giao dịch.

**Provisioned concurrency** giữ sẵn một số environments được khởi tạo, giảm tác động cold start cho phần traffic được provision, nhưng có phí và cần quản lý theo alias/version. **SnapStart không hỗ trợ mọi runtime, package type và cấu hình**; đặc biệt không mặc định áp dụng được cho Lambda container image.

## 8. ZIP và container image: hai cách đóng gói chính

AWS Lambda hỗ trợ hai package types cho function:

| Tiêu chí | **ZIP/JAR** | **Container image** |
| --- | --- | --- |
| Cách xác định runtime | Chọn managed/custom runtime identifier trong cấu hình | Runtime/RIC nằm trong image |
| Artifact | ZIP hoặc Java JAR, dependencies/layers | Linux OCI/Docker-compatible image |
| Dung lượng tối đa | **50 MB nén khi upload trực tiếp**, **250 MB giải nén** gồm layers/custom runtime | **10 GB** image giải nén gồm tất cả layers |
| Nơi lưu khi deploy | Upload trực tiếp hoặc lấy artifact từ S3 cùng Region theo cơ chế | **Amazon ECR cùng Region** với function |
| Layers Lambda | **Có**, trong giới hạn hỗ trợ | **Không hỗ trợ Lambda layers** như ZIP; dependencies trong image |
| Quản lý OS/dependencies | AWS managed runtime; phụ thuộc do bạn đóng gói | Bạn chọn base image/OS, rebuild khi có bản vá |
| Khả năng triển khai | CLI, Console, SAM, CloudFormation, CDK | Docker build + ECR + CLI/IaC |
| Vận hành tối giản | Thường đơn giản cho Java code/dependency thông thường | Phù hợp native libs, toolchain đặc biệt, pipeline Docker có sẵn |
| Đổi ZIP ↔ image trên cùng function | **Không được** | Phải tạo function mới và chuyển trigger/routing |

**Giới hạn 250 MB** tính **toàn bộ nội dung giải nén của package cộng layers**, không phải 250 MB cho từng layer. Với ZIP > 50 MB nén nhưng vẫn trong hạn mức nội dung, có thể chuyển artifact qua **S3 cùng Region** để deploy.

**Container image 10 GB** là trần kỹ thuật, không phải khuyến nghị. Image quá lớn vẫn ảnh hưởng build/push/scan, bảo mật và cold start/khả năng hoạt động. Không dùng container chỉ để lách việc loại dependency thừa.

### Tại sao không thể đổi PackageType tại chỗ?

Một function được tạo bằng ZIP không thể cập nhật bằng cách đưa ECR image rồi coi đó là cùng resource, và ngược lại. Nếu muốn chuyển loại:

1. Tạo function mới có package type mới.
2. Đặt IAM role, VPC, env, KMS, timeout, memory và triggers tương ứng.
3. Kiểm thử trên alias/routing tích hợp theo khả năng hỗ trợ.
4. Chuyển event source/API/mapping/permission một cách có kiểm soát.
5. Theo dõi error/latency/retry trước khi xóa function cũ.

**Đổi artifact không chỉ là đổi cách nén file**: handler bootstrap, runtime patching, IAM và CI/CD cũng đổi.

## 9. Chuẩn bị project Java Lambda dùng Maven

Ví dụ Java 21, Maven, AWS Lambda Java Core.

Cấu trúc:

~~~text
order-lambda/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/lambda/
    │           └── OrderHandler.java
    └── test/
        └── java/  (unit tests, nếu có)
~~~

File `pom.xml` tối thiểu cho **JAR có dependency đóng gói sẵn**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>order-lambda</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>com.amazonaws</groupId>
      <artifactId>aws-lambda-java-core</artifactId>
      <version>1.2.2</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
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
          </execution>
        </executions>
        <configuration>
          <createDependencyReducedPom>false</createDependencyReducedPom>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Cách hiểu dependency:** `aws-lambda-java-core` cung cấp `RequestHandler`, `RequestStreamHandler`, `Context`. Khi xử lý SQS/S3/API Gateway typed events, bổ sung thư viện `aws-lambda-java-events`. Khi gọi AWS S3/DynamoDB, bổ sung các module **AWS SDK for Java v2** cần dùng và quản trị version bằng BOM thích hợp.

**Không chọn ngẫu nhiên một version SDK mà không chạy compatibility test.** Các version trong ví dụ minh họa cấu hình Maven; trên production nên dùng dependency management có kiểm tra CVE, build reproducibility và integration tests.

### Build JAR

~~~bash
mvn -DskipTests=false clean package
~~~

Artifact sau khi Shade thường là:

~~~text
target/order-lambda-1.0.0.jar
~~~

Có thể inspect class/package bằng công cụ Java:

~~~bash
jar tf target/order-lambda-1.0.0.jar
~~~

Cần tìm thấy `com/example/lambda/OrderHandler.class` và những class dependency cần thiết. Nếu build chỉ tạo một JAR mỏng không kèm thư viện, Lambda có thể gặp `NoClassDefFoundError` khi runtime không có dependency.

### Shaded JAR, ZIP có lib và lớp Java

AWS Lambda Java cũng hỗ trợ layout ZIP có JAR files trong `lib/` và classpath tương ứng. **Maven Shade** tạo fat/uber JAR tiện cho ví dụ nhỏ; **Gradle Zip task** có thể đưa JAR của ứng dụng và runtime dependencies vào `lib/`.

**Cảnh báo khi đóng gói:** Một số dependency Java dùng `META-INF/services`, service loaders, Log4j2 cache, Spring resource merging hoặc multi-release JAR. Nếu dùng Shade mà không merge metadata/service files cần thiết, ứng dụng có thể compile nhưng chạy lỗi. Chọn transformer đúng theo thư viện, kiểm thử artifact cuối cùng thay vì chỉ test code trong IDE.

## 10. Triển khai ZIP/JAR lên Lambda bằng AWS CLI

> **Điều kiện:** Máy lab đã cài JDK 21, Maven, AWS CLI v2; AWS credentials dùng qua SSO/role/profile, không hardcode access key. Bạn có IAM quyền tạo/triển khai Lambda và **quyền `iam:PassRole`** đối với execution role. Bài thực hành có chi phí invocation/logs và có thể có phí tài nguyên phụ trợ.

### 10.1. Execution role và trust policy

Lambda function cần một **execution role**. Trust policy cho service Lambda assume role:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Giả sử lưu JSON ở file lab `lambda-trust.json`. Nếu có quyền IAM, có thể tạo role:

~~~bash
aws iam create-role \
  --role-name order-lambda-execution-lab \
  --assume-role-policy-document file://lambda-trust.json \
  --profile lab

aws iam attach-role-policy \
  --role-name order-lambda-execution-lab \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
  --profile lab
~~~

Policy `AWSLambdaBasicExecutionRole` cung cấp các quyền **CloudWatch Logs cơ bản**, không tự cấp quyền đọc S3 hay truy cập DB. Nếu function cần `s3:PutObject`, `dynamodb:PutItem` hoặc Secrets Manager, thêm identity policy đúng resource ARN. Đợi IAM role/permissions có hiệu lực trước khi tạo/invoke function; IAM có thể có độ trễ propagation.

### 10.2. Tạo function kiểu ZIP

~~~bash
aws sts get-caller-identity --profile lab

aws lambda create-function \
  --function-name orders-zip-lab \
  --package-type Zip \
  --runtime java21 \
  --handler com.example.lambda.OrderHandler::handleRequest \
  --role arn:aws:iam::111122223333:role/order-lambda-execution-lab \
  --architectures x86_64 \
  --memory-size 512 \
  --timeout 15 \
  --zip-file fileb://target/order-lambda-1.0.0.jar \
  --region ap-southeast-1 \
  --profile lab
~~~

Các ARNs/tên chỉ minh họa. Nếu function đã tồn tại, **`create-function` không dùng để update code**; dùng `update-function-code` và `update-function-configuration` theo mục đích.

### 10.3. Invoke test event bằng file

Tạo `event.json`:

~~~json
{
  "orderId": "ORD-1001",
  "currency": "VND"
}
~~~

Gọi trực tiếp:

~~~bash
aws lambda invoke \
  --function-name orders-zip-lab \
  --invocation-type RequestResponse \
  --payload fileb://event.json \
  --log-type Tail \
  --region ap-southeast-1 \
  --profile lab \
  response.json
~~~

Kết quả `response.json` (nếu thành công):

~~~json
{
  "orderId": "ORD-1001",
  "currency": "VND",
  "accepted": true
}
~~~

Đọc thêm metadata CLI response:

- `StatusCode=200` với synchronous invoke **không tự chứng minh handler thành công**. Nếu `FunctionError` xuất hiện, handler đã lỗi và payload thường chứa thông tin lỗi.
- `LogResult` là đoạn log được mã hóa base64 trong phản hồi nếu yêu cầu log tail và API hỗ trợ.
- Log đầy đủ xem qua CloudWatch Logs group `/aws/lambda/orders-zip-lab`.

### 10.4. Cập nhật artifact ZIP

Sau khi sửa code và build lại:

~~~bash
mvn clean package

aws lambda update-function-code \
  --function-name orders-zip-lab \
  --zip-file fileb://target/order-lambda-1.0.0.jar \
  --region ap-southeast-1 \
  --profile lab

aws lambda wait function-updated \
  --function-name orders-zip-lab \
  --region ap-southeast-1 \
  --profile lab
~~~

**Không publish version cũ trước khi update hoàn tất.** Để release có thể rollback, hãy publish một **version** sau khi code/config phù hợp rồi dùng alias cho production (xem mục 16).

### 10.5. ZIP lớn hơn 50 MB

Nếu ZIP vượt giới hạn upload trực tiếp nhưng nội dung giải nén vẫn trong quota 250 MB:

1. Tải artifact lên **S3 bucket cùng Region**;
2. Deploy Lambda qua `--code S3Bucket=...,S3Key=...` khi create hoặc các tham số S3 tương ứng khi update;
3. Dùng object version/checksum và S3 access phù hợp để có artifact bất biến.

**Không giải quyết gói vượt 250 MB giải nén chỉ bằng cách tải lên S3.** Khi quá quota, cần tối ưu dependencies, chia layers (vẫn tính vào giới hạn tổng), hoặc xem container image nếu có lý do.

## 11. Lambda layers với Java ZIP

**Lambda layer** là artifact phụ chứa libraries, custom runtime hoặc tài nguyên dùng chung. Khi function ZIP được triển khai, layers được nạp vào môi trường ở đường dẫn do Lambda quy định.

Với Java, layout layer tham khảo:

~~~text
my-java-dependencies-layer.zip
└── java/
    └── lib/
        ├── dependency-one.jar
        └── dependency-two.jar
~~~

Thư viện Java trong layer được Lambda nạp vào classpath theo cơ chế hỗ trợ. Tránh cất JAR ở root ZIP nếu runtime mong `java/lib`.

### Dùng layers khi nào?

- Nhiều ZIP functions chia sẻ một thư viện lớn và release lifecycle tương đối độc lập.
- Muốn tách các package nặng khỏi code handler để quản lý artifact dễ hơn.
- Có custom runtime/extensions phụ trợ phù hợp.

### Giới hạn và rủi ro

- Mỗi function có thể dùng tối đa **5 layers** trong giới hạn phổ biến.
- **Tổng dung lượng giải nén** package và layers vẫn bị giới hạn chung (250 MB với mô hình ZIP thông thường).
- Layer version là phiên bản được tham chiếu; cập nhật layer mới **không tự làm function đang dùng version cũ đổi dependencies**.
- Lỗi lớp trùng package/version có thể gây `ClassNotFoundException`, `NoSuchMethodError`, `ServiceConfigurationError`.
- **Lambda container image không gắn Lambda layers**: dependencies cần ở trong image.

**Bài học:** Tách layer không mặc định làm cold start nhỏ hơn hay giảm toàn bộ chi phí. Phải đo kích thước artifact, init latency và vận hành versioning thật.

## 12. Container image cho Lambda: khác container ECS như thế nào?

Lambda container image vẫn chạy trong **Lambda execution model**, không phải một Docker daemon luôn phục vụ HTTP trên cổng tự chọn. Image phải đáp ứng **Lambda Runtime API**.

### Ba kiểu image

1. **AWS Lambda language base image:** có sẵn runtime (ví dụ Java 21), Runtime Interface Client (**RIC**) và Runtime Interface Emulator (**RIE**) cho local testing.
2. **AWS OS-only base image:** chứa Amazon Linux và công cụ cơ sở, bạn phải thêm runtime/interface client phù hợp.
3. **Base image tùy chỉnh (Debian/Alpine, v.v.):** phải tích hợp RIC hoặc tự thực thi Runtime API; kiểm tra compatibility hệ điều hành và thư viện.

### Các điều kiện quan trọng

- Image phải là **Linux**; Lambda function image dùng **một kiến trúc CPU duy nhất** (`x86_64` hoặc `arm64`), không gửi multi-architecture manifest rồi kỳ vọng Lambda chọn.
- Root filesystem phải hoạt động ở chế độ **read-only**; thư mục writable mặc định là `/tmp`, có thể cấu hình từ **512 MB tới 10.240 MB** theo quota.
- AWS Lambda chạy image với **least-privileged user**; code không nên cần `root` hoặc ghi vào `/var/task`/`/opt`.
- Image tối đa **10 GB uncompressed**, gồm các layers; nên giữ nhỏ hơn nhiều nếu có thể.
- Image phải nằm trong **Amazon ECR cùng AWS Region** với function; cross-account repository được hỗ trợ với ECR policy phù hợp.
- Lambda không dùng ECR FIPS endpoint cho image theo những hạn chế được AWS công bố.
- **Cần rebuild/push/deploy** khi cập nhật base image; thay tag image trong ECR **không tự cập nhật** image đã được function resolve.

## 13. Dockerfile Java 21 chạy Lambda

Dùng cùng `OrderHandler` ở mục 4, nhưng artifact được đưa vào image.

### 13.1. Chuẩn bị compiled classes và dependencies

Trong thư mục Maven project:

~~~bash
mvn clean compile dependency:copy-dependencies -DincludeScope=runtime
~~~

Dự kiến:

~~~text
target/
├── classes/
│   └── com/example/lambda/OrderHandler.class
└── dependency/
    ├── aws-lambda-java-core-*.jar
    └── ... dependencies khác ...
~~~

Nếu plugin chạy tạo dependency directory khác, điều chỉnh Dockerfile theo output thực. Build phải thành công trước khi container được tạo; không đưa source `.java` vào runtime image rồi mong Lambda tự compile.

### 13.2. Dockerfile dựa trên official base image

File `Dockerfile`:

~~~dockerfile
FROM public.ecr.aws/lambda/java:21

# LAMBDA_TASK_ROOT của AWS Java base image tương ứng /var/task.
COPY target/classes/ /var/task/
COPY target/dependency/ /var/task/lib/

# Handler Java dùng package.Class::method.
CMD ["com.example.lambda.OrderHandler::handleRequest"]
~~~

**Tại sao dùng base này?**

- Chứa Java runtime phù hợp và Runtime Interface Client.
- Biết cách nhận event từ Lambda Runtime API.
- Có Runtime Interface Emulator cho local test.
- Bạn không phải tự viết bootstrap poll `/runtime/invocation/next`.

Nếu dùng base image không phải Lambda, phải cung cấp runtime interface client và entrypoint tương thích. Một image Java thông thường chạy `java -jar app.jar` liên tục chưa chắc là một Lambda image hợp lệ.

### 13.3. Build image đúng kiến trúc

Ví dụ tạo image **linux/amd64** cho function `x86_64`:

~~~bash
docker buildx build \
  --platform linux/amd64 \
  --provenance=false \
  --load \
  -t orders-lambda:1.0.0 \
  .
~~~

AWS hướng dẫn dùng `--provenance=false` trong ví dụ build Lambda-compatible images để tránh kiểu metadata/manifest không tương thích với môi trường áp dụng. Với ARM, chọn `linux/arm64` và cấu hình Lambda `arm64`, đồng thời bảo đảm native libraries tương thích.

**Không cần cấu hình Dockerfile `EXPOSE 8080` để Lambda public HTTP**: cổng 8080 của base image/RIE dùng cho cách nhận invocation trong môi trường local, không biến function thành ECS web server.

## 14. Chạy container Lambda thử tại local

Với AWS Java Lambda base image, có RIE cho thử invocation local.

Khởi động:

~~~bash
docker run --rm -p 9000:8080 orders-lambda:1.0.0
~~~

Ở terminal khác:

~~~bash
curl -X POST \
  "http://localhost:9000/2015-03-31/functions/function/invocations" \
  -H "Content-Type: application/json" \
  -d '{"orderId":"ORD-1001","currency":"VND"}'
~~~

Dự kiến output JSON có `accepted: true`.

**Giới hạn của local test:**

- RIE mô phỏng một phần giao thức invoke; **không hoàn toàn tái hiện** IAM, VPC/ENI, service limits, KMS, concurrency và mọi hành vi của Lambda runtime trên AWS.
- Nếu function thực sự gọi AWS SDK, local credentials phải được cấp bằng cơ chế phát triển an toàn; không hardcode secret vào image hoặc `Dockerfile`.
- Test unit Java và integration test ở môi trường lab thực vẫn cần cho release.
- Nếu dùng máy Windows/ARM laptop, đặc biệt kiểm tra image architecture và builder; Docker Desktop là công cụ local, còn function AWS phải chỉ định architecture phù hợp.

## 15. Push image lên Amazon ECR và tạo Lambda function

### 15.1. Tạo repository ở đúng Region

~~~bash
aws ecr create-repository \
  --repository-name orders-lambda \
  --image-scanning-configuration scanOnPush=true \
  --region ap-southeast-1 \
  --profile lab
~~~

Nếu repository đã tồn tại, chỉ cần xác nhận URI và policies thay vì tạo trùng.

### 15.2. Đăng nhập Docker vào ECR

~~~bash
aws ecr get-login-password \
  --region ap-southeast-1 --profile lab \
  | docker login \
      --username AWS \
      --password-stdin 111122223333.dkr.ecr.ap-southeast-1.amazonaws.com
~~~

Đây là **ECR authentication token tạm**, không phải secret cố định để ghi vào source. Không log `docker login` token hoặc nhúng AWS access keys trong image.

### 15.3. Gắn tag và push

~~~bash
docker tag orders-lambda:1.0.0 \
  111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/orders-lambda:1.0.0

docker push \
  111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/orders-lambda:1.0.0
~~~

### 15.4. Tạo function từ image

~~~bash
aws lambda create-function \
  --function-name orders-image-lab \
  --package-type Image \
  --code ImageUri=111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/orders-lambda:1.0.0 \
  --role arn:aws:iam::111122223333:role/order-lambda-execution-lab \
  --architectures x86_64 \
  --memory-size 512 \
  --timeout 15 \
  --region ap-southeast-1 \
  --profile lab
~~~

**Chú ý:** Với package type `Image`, không truyền `--runtime java21`, `--handler ...` hay `--zip-file` vào lệnh tạo. Handler nằm trong `CMD` của image hoặc image configuration override; runtime nằm trong image.

### 15.5. Invoke và update image

Tạo/invoke giống function ZIP, chỉ khác tên:

~~~bash
aws lambda invoke \
  --function-name orders-image-lab \
  --payload fileb://event.json \
  --region ap-southeast-1 \
  --profile lab \
  image-response.json
~~~

Khi push image `1.0.1` mới:

~~~bash
aws lambda update-function-code \
  --function-name orders-image-lab \
  --image-uri 111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/orders-lambda:1.0.1 \
  --region ap-southeast-1 \
  --profile lab
~~~

Lambda **resolve image tag thành digest** khi cập nhật code. Chỉ **đẩy lại một tag giống tên vào ECR** không tự làm function đang tồn tại chuyển sang digest mới. Tốt nhất dùng **immutable image tags hoặc SHA digest** và thay version/alias thông qua pipeline được ghi nhận.

### 15.6. Cross-account ECR image

Một function ở Account B có thể dùng image ECR tại Account A **cùng Region** khi:

- Principal tạo/cập nhật function có quyền truy cập ECR cần thiết theo API;
- **ECR repository policy** cho phép dịch vụ Lambda và account/principal phù hợp đọc image trong các giai đoạn vận hành;
- image và repository còn tồn tại, không bị lifecycle policy xóa mất digest cần thiết.

**Không suy luận task execution role của ECS giống Lambda execution role**. Quyền Lambda lấy image từ ECR và quyền mã ứng dụng gọi S3 là hai lớp khác nhau; xem quy định về **ECR repository permissions for Lambda** của AWS.

## 16. Versions, aliases và release an toàn

Lambda có **`$LATEST`**, **published versions** và **aliases**.

- **`$LATEST`:** bản làm việc có thể cập nhật code/config.
- **Published version:** snapshot phần lớn code và cấu hình ở thời điểm publish; hầu hết thuộc tính được khóa không sửa trực tiếp.
- **Alias:** tên logic như `dev`, `staging`, `prod` trỏ một published version; có thể được dùng để triển khai/canary theo tính năng hỗ trợ.

~~~mermaid
flowchart LR
    CI[CI/CD build artifact] --> Latest[Lambda $LATEST]
    Latest --> V7[Published version 7]
    Latest --> V8[Published version 8]
    Alias[Alias prod] -->|90%| V7
    Alias -->|10%| V8
    Client[API Gateway / EventBridge / SDK] --> Alias
~~~

**Ví dụ publish và tạo alias:**

~~~bash
aws lambda publish-version \
  --function-name orders-zip-lab \
  --description "release-1.0.0" \
  --region ap-southeast-1 \
  --profile lab

aws lambda create-alias \
  --function-name orders-zip-lab \
  --name prod \
  --function-version 1 \
  --region ap-southeast-1 \
  --profile lab
~~~

**`--function-version 1` chỉ là ví dụ**, phải dùng version ID mà `publish-version` thực sự trả về. Nếu function đã có nhiều lần publish, version không nhất thiết là 1.

Khi có release mới:

1. Cập nhật `$LATEST`, chờ trạng thái update hoàn tất và chạy integration tests.
2. Publish version mới.
3. Đổi alias `prod` sang version mới hoặc cấu hình **weighted alias** để chia traffic giữa hai published versions khi điều kiện hỗ trợ.
4. Giám sát error/latency, cold start, hệ thống phụ thuộc và business metrics.
5. Nếu có lỗi, đưa alias về version đã biết tốt, đồng thời xử lý sự kiện bị retry/idempotency.

**Lưu ý:** Rollback alias **không tự hoàn tác** dữ liệu S3/DB đã ghi bởi version lỗi. Muốn rollback an toàn, cần versioned schema, idempotency và kế hoạch xử lý dữ liệu.

## 17. IAM: hai loại quyền rất dễ nhầm

### 17.1. Execution role: function có thể làm gì?

Khi Lambda chạy handler, code nhận credentials tạm qua **execution role**. IAM policy của role quyết định API mà function gọi được.

Ví dụ một role chỉ cần ghi object `invoices/*` vào S3:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "WriteInvoices",
      "Effect": "Allow",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::orders-invoices-example/invoices/*"
    }
  ]
}
~~~

Nếu bucket dùng **SSE-KMS**, cần xét thêm `kms:GenerateDataKey` với customer managed key và **KMS key policy** theo ngữ cảnh. Nếu đọc object SSE-KMS, thường cần `kms:Decrypt`.

### 17.2. Resource-based policy: ai được gọi function?

Ví dụ API Gateway, EventBridge hoặc S3 trigger có thể cần **resource-based permission** trên Lambda để dịch vụ được invoke. Đó là lớp quyền khác với execution role.

| Câu hỏi | Nơi kiểm soát |
| --- | --- |
| S3/EventBridge có được **gọi Lambda** không? | Lambda resource-based policy / quyền event source theo tích hợp |
| Code Lambda có được **ghi S3 object** không? | Execution role, bucket policy, KMS policy |
| Ai được **deploy/update function**? | Identity policy, `iam:PassRole`, SCP/boundary và policy liên quan |
| Ai được đọc **secret runtime**? | Execution role + secret resource policy + KMS |
| Function có truy cập **private RDS** được không? | VPC route/SG/DNS **và** DB auth, không chỉ IAM |

### 17.3. Trust policy và PassRole

Execution role có trust cho `lambda.amazonaws.com`. Principal triển khai có thể cần `iam:PassRole` để gắn role vào function. Việc caller có quyền `lambda:CreateFunction` **không có nghĩa tự động được pass mọi role**.

**Security guideline:** Không nhúng AWS access key vào code, image, environment hoặc JAR. Ưu tiên IAM role temporary credentials, điều kiện IAM tối thiểu, Secrets Manager, encryption và audit CloudTrail.

## 18. Environment variables, Secrets Manager, KMS và filesystem

### Environment variables

Có thể khai báo `APP_ENV`, `TABLE_NAME`, `LOG_LEVEL` trong function configuration. Dữ liệu environment variables được AWS mã hóa at rest theo cơ chế Lambda/KMS; nhưng:

- Env vars **không phải nơi ưu tiên chứa password/token**, đặc biệt nếu nhiều người có quyền xem cấu hình function.
- Kích thước tổng environment variables có quota (thông thường **4 KB** trong Lambda Event Functions).
- Thay env vars của `$LATEST` là thay cấu hình function; published version cũ giữ snapshot cấu hình.
- Khi key là customer managed KMS key, IAM/key policy cho quản trị và xử lý cấu hình có thể phải được kiểm tra.

### Secrets

Với database password/API token, dùng **AWS Secrets Manager** hoặc SSM Parameter Store thích hợp. Code dùng SDK lấy secret khi cần và có thể cache an toàn trong execution environment trong thời gian phù hợp.

Không log secret, không đặt secret trong Dockerfile `ENV`, không commit secrets vào Git và không gắn vào image layers (dù sau đó xóa file, layer cũ có thể vẫn lưu).

### Filesystem

- **Code/package root** là vùng read-only ở runtime; không ghi dữ liệu nghiệp vụ vào thư mục source hoặc library.
- **`/tmp`** là vùng ghi tạm, cho phép cấu hình **512–10.240 MB** trong giới hạn hỗ trợ.
- Dữ liệu `/tmp` có thể tồn tại khi environment được reuse nhưng **không được bảo đảm**.
- Với shared filesystem cần POSIX, có thể tích hợp **Amazon EFS** khi function được cấu hình VPC/Access Point theo yêu cầu.
- Với object như hóa đơn/ảnh, **S3** thường đơn giản hơn việc chia sẻ filesystem.
- Với database, nên sử dụng **RDS/Aurora/DynamoDB** hoặc hệ thống tương ứng; không coi local `/tmp` là persistent DB.

## 19. VPC: kết nối RDS private không phải thao tác mặc định

Lambda function thông thường không nhất thiết phải đặt trong VPC của bạn để gọi các dịch vụ AWS public endpoints theo quyền IAM. Nhưng nếu cần truy cập **RDS/private endpoint/EC2 trong VPC**, phải cấu hình **Lambda VPC networking** phù hợp.

~~~mermaid
flowchart LR
    Event[SQS / API Gateway / EventBridge] --> Lambda[Lambda function]
    subgraph VPC["VPC của ứng dụng"]
      SG[Lambda SG / private subnets] --> DB[(Private RDS)]
      SG --> Endpoint[VPC endpoints / NAT route]
    end
    Lambda --> SG
    Endpoint --> S3[S3 / Secrets Manager / dịch vụ AWS]
~~~

**Checklist:**

1. Chọn subnets phù hợp trong **nhiều AZ** nếu ứng dụng cần khả năng phục hồi, và security group cho Lambda.
2. Cho outbound tới DB port cần thiết, ví dụ TCP/5432; DB SG cho inbound từ Lambda SG.
3. Có DNS resolver/route phù hợp tới private endpoint.
4. Nếu function cần gọi Internet public endpoints, phải có NAT/egress path thích hợp. **Gắn Lambda vào public subnet không tự cấp public IPv4 hoặc Internet access cho function**.
5. Nếu dùng VPC endpoints, kiểm tra private DNS, SG endpoint, endpoint policy và IAM.
6. Execution role cần những quyền network interface/VPC cần thiết theo hướng dẫn AWS. Không gán toàn bộ EC2 API quyền quản trị nếu không cần.

**Cạm bẫy ZIP/container:** Khi Lambda triển khai **container image**, việc Lambda service tải ECR image là giai đoạn do dịch vụ quản lý, **không có nghĩa function VPC runtime cần NAT chỉ để ECR tải image lúc khởi tạo**. Runtime code gọi ECR/S3/Secrets Manager mới cần network path và IAM tương ứng.

### Cold start và VPC

VPC có thể ảnh hưởng việc cấu hình/khởi tạo và network behavior, nhưng không nên mặc định các số liệu cold start từ mô hình VPC đời cũ còn đúng. Với Hyperplane ENIs và platform hiện hành, hãy đo thực tế theo subnets/SG, load, runtime và integration. Một yêu cầu timeout do SG/route thiếu là **lỗi kết nối**, không phải bằng chứng JVM cold start.

## 20. Timeout, memory, concurrency và tối ưu Java

### 20.1. Timeout và memory

Các mức phổ biến cho Lambda Event Functions thông thường:

| Thuộc tính | Khoảng/giới hạn theo tài liệu AWS | Ảnh hưởng |
| --- | --- | --- |
| **Timeout** | Tối đa **900 giây (15 phút)** cho Event Function thông thường | Handler chạy quá hạn sẽ bị dừng; cần retry/idempotency |
| **Memory** | **128–10.240 MB** | CPU power tăng theo memory; không phải chỉ là RAM |
| **Temporary storage** | **512–10.240 MB** ở `/tmp` | Scratch, file tạm, native libs cần writable path |
| **Invocation payload đồng bộ** | Có quota payload/request-response theo mode, ví dụ **6 MB** cho loại thường | File lớn nên gửi S3 key thay vì đẩy toàn bộ file vào event |
| **Concurrency** | Giới hạn account/Region và quota riêng | Throttling khi tăng tải; cần giới hạn/điều phối |

Các chế độ Lambda mới có thể có quota hoặc hành vi khác; đối chiếu bảng **Lambda quotas** hiện hành cho đúng loại function.

### 20.2. Tăng memory cũng có thể làm hàm nhanh hơn

Lambda cấp CPU proportionally với memory. Một Java function CPU-bound có thể chạy nhanh đáng kể khi tăng từ 512 MB lên 1.024 hoặc 2.048 MB. Vì billing thường dựa trên memory và execution duration, tăng RAM **có thể giảm duration đủ để tổng phí không tăng tương ứng**, nhưng phải benchmark.

### 20.3. Concurrency và Little's Law

Quy tắc xấp xỉ cho traffic ổn định:

\[
\text{Concurrency} \approx \text{Requests/second} \times \text{Duration (seconds)}
\]

Ví dụ 300 RPS, duration trung bình 0,2 giây:

\[
300 \times 0.2 = 60\ \text{concurrent invocations}
\]

Nếu duration tăng lên 2 giây do DB chậm:

\[
300 \times 2 = 600\ \text{concurrent invocations}
\]

**Thêm concurrency không chắc giải quyết nút nghẽn DB**; Lambda có thể tạo thêm nhiều DB connections và làm quá tải downstream.

### Reserved concurrency và provisioned concurrency

| Loại | Ý nghĩa | Dùng khi |
| --- | --- | --- |
| **Reserved concurrency** | Giới hạn/đảm bảo quota concurrency dành cho function theo cấu hình | Chặn function gây quá tải downstream, phân bổ capacity |
| **Provisioned concurrency** | Chuẩn bị trước execution environments cho version/alias | Giảm cold start ở phần traffic nhạy latency, có phí bổ sung |
| **Event source maximum concurrency** | Giới hạn/concurrency control tại mapping hoặc nguồn được hỗ trợ | Kiểm soát consumer SQS/stream và downstream |
| **Account concurrency quota** | Trần toàn account/Region hoặc các quota cấu hình | Cần xem headroom cho các function khác |

**Reserved concurrency = 0** có thể được dùng để tạm chặn invokes theo ngữ cảnh, nhưng tác động vận hành rất lớn; đừng dùng trên production mà không có change plan.

### Java startup/cold start

Một số tối ưu:

- Dùng handler gọn, giảm classpath và số bean/services tạo lúc init;
- giữ JDK/runtime version được hỗ trợ, cân nhắc architecture `arm64` khi dependencies tương thích và lợi ích được đo;
- dùng SDK client singleton/reusable, cấu hình timeouts;
- tránh synchronous remote calls ở static initializer;
- cân nhắc **SnapStart** hoặc **provisioned concurrency** trên cấu hình đủ điều kiện;
- dùng Lambda Power Tuning/benchmark theo dữ liệu thực và so p95/p99;
- kiểm tra CPU, memory, GC và I/O; không quy mọi timeout thành “Java cold start”.

## 21. Retry, DLQ, idempotency và bảo vệ dữ liệu

Lambda có thể được invoke lại vì retry nguồn sự kiện, client retry hoặc failure giữa việc ghi dữ liệu và acknowledgment. **“At least once”** là tình huống thực tế quan trọng với S3/SQS/EventBridge: code nên được thiết kế **idempotent**.

### Ví dụ lỗi xử lý hóa đơn trùng

1. Lambda nhận `OrderCreated: ORD-1001`.
2. Lambda ghi file `invoices/ORD-1001.pdf` vào S3.
3. Handler timeout **trước khi SQS batch được xác nhận**.
4. SQS message được gửi lại cho Lambda.
5. Nếu không kiểm tra `orderId`, handler có thể tạo hóa đơn lần hai, ghi đè hoặc gửi email trùng.

**Phương án:**

- Dùng khóa idempotency ổn định như `orderId` hoặc `eventId`;
- ghi trạng thái xử lý vào DynamoDB/DB bằng condition/transaction phù hợp;
- tách external side effects và retries theo thiết kế;
- quy định DLQ, maxReceiveCount/visibility timeout, failure destination theo từng event source;
- xử lý partial failures trong SQS batches khi được hỗ trợ để giảm retry message đã thành công;
- đo retry/error/DLQ backlog và đặt alarm.

### Không có một DLQ chung cho mọi kiểu invoke

- **Asynchronous invocation** của Lambda có cấu hình retry, event age, destinations/DLQ theo chế độ Lambda.
- **SQS event source mapping** lấy message từ queue, lỗi làm message visible lại theo visibility timeout; redrive policy của **SQS queue/DLQ** quan trọng.
- **Kinesis/DynamoDB Streams** checkpoint/ordering/batch retry theo event source mapping; tránh suy từ SQS.
- **Synchronous API** trả lỗi cho caller; phía client/API có thể retry độc lập.

**Handler phải nhận diện loại event trước khi quyết định throw exception, trả response hay ack batch.** Trả `{"accepted":false}` không đồng nghĩa mọi nguồn sự kiện sẽ coi đó là failure.

## 22. Monitoring: chứng minh function hoạt động tốt

Kết hợp **CloudWatch Logs**, **CloudWatch Metrics**, **X-Ray/traces** và log của hệ thống gọi đến.

| Metric/thành phần | Câu hỏi trả lời | Khi nào cảnh báo |
| --- | --- | --- |
| `Invocations` | Có bao nhiêu lần Lambda được invoke? | Tăng đột biến hoặc không có traffic kỳ vọng |
| `Errors` | Handler/runtime có lỗi? | Error rate vượt SLO |
| `Duration` | Thời gian xử lý (p95/p99) | Gần timeout, latency tăng |
| `Throttles` | Có bị giới hạn concurrency? | Throttling kéo dài và backlog tăng |
| `ConcurrentExecutions` | Mức đồng thời đang sử dụng | Chạm reserved/account quota |
| `IteratorAge` hoặc metrics mapping phù hợp | Consumer stream/batch có bị trễ? | Backlog/lag tăng |
| `DeadLetterErrors` / destination failures theo tính năng | Ghi sự kiện lỗi ra DLQ/destination có lỗi không? | Mất khả năng lưu/chẩn đoán sự kiện lỗi |
| `Init Duration` trong log/report/telemetry khi có | Cold start/init tốn bao lâu? | Init latency tăng sau cập nhật dependency |
| `Max Memory Used` trong REPORT logs | Memory peak so với cấu hình | Gần OOM hoặc có memory waste |
| S3/SQS/RDS/KMS metric | Downstream có chậm/hết quota? | Dependency bottleneck tạo timeout |

### Xem logs bằng CLI

~~~bash
aws logs tail /aws/lambda/orders-zip-lab \
  --since 30m \
  --follow \
  --region ap-southeast-1 \
  --profile lab
~~~

Đối với function image, log group tương ứng tên function `orders-image-lab`. Log group phải được tạo/ghi thành công và role có quyền Logs; nếu init lỗi quá sớm, log có thể thiếu stack trace mong đợi.

### Structured logging, correlation IDs

Trong ứng dụng Java, nên log JSON có:

~~~json
{
  "level": "INFO",
  "service": "orders-invoice",
  "requestId": "aws-request-id-example",
  "orderId": "ORD-1001",
  "stage": "invoice-generated",
  "durationMs": 123
}
~~~

Tránh log password, bearer token, object PII, toàn bộ request body, credentials hoặc connection strings nhạy cảm. Truyền correlation ID từ API/SQS để nối trace nhiều dịch vụ. Có thể dùng **AWS Lambda Powertools for Java**, AWS X-Ray/OpenTelemetry theo khả năng và chính sách của hệ thống.

### Đừng nhầm code deploy success với request success

`LastUpdateStatus=Successful` chỉ nói bản cập nhật code/config được chấp nhận và áp dụng. Một function có thể update thành công nhưng invocation `FunctionError=Unhandled`, timeout, bị KMS AccessDenied hoặc trả response sai contract. **Phải test invoke và business behavior thực**.

## 23. Bảo mật, độ tin cậy và chi phí theo kiến trúc tổng thể

### 23.1. Bảo mật

- Dùng execution role **least privilege**, tách role deploy, `iam:PassRole`, function resource policy và IAM/KMS của dữ liệu.
- Tránh secrets trong ZIP/JAR, Docker image, ENV plaintext hoặc log. Secrets Manager/SSM + customer managed key khi cần.
- Quét CVE dependencies và image; quản lý runtime deprecation/updates.
- Bắt buộc TLS cho API, AuthN/AuthZ phù hợp ở API Gateway/Function URL và WAF/rate limiting nếu trường hợp cần.
- Khi dùng VPC, chỉ cấp subnet/SG/endpoint permissions tối thiểu.
- Dùng CloudTrail để audit code update, configuration, IAM policy và các trigger permission.

### 23.2. Khả năng phục hồi

- Lambda thuộc một **Region** và được AWS thực thi qua hạ tầng khu vực, nhưng application HA còn phụ thuộc VPC subnet selection và các hệ thống backend.
- Với RDS single-AZ, một Lambda tự scale không biến database thành Multi-AZ.
- Tác vụ ghi S3/DB cần retries và idempotency; backup/versioning/replication tùy RPO/RTO.
- Với cross-Region DR, cần triển khai function/artifact/triggers/roles/KMS/data ở Region dự phòng và test routing, không tự giả định function có code ở Region khác.
- Nếu một event kéo dài vượt 15 phút, cân nhắc Step Functions, ECS/Fargate, Batch hoặc kỹ thuật chia job thành những bước phù hợp.

### 23.3. Chi phí: tính đủ những phần ngoài function

Chi phí thường gồm:

1. **Số lượng requests/invocations**;
2. **Compute GB-seconds** dựa trên memory và duration trong model pricing phù hợp;
3. **Provisioned concurrency/SnapStart hoặc chi phí tính năng** khi áp dụng;
4. **Ephemeral storage vượt mức miễn phí chuẩn**, streaming/network theo biểu giá;
5. **CloudWatch Logs/Metrics/X-Ray**;
6. **ECR image storage/scan**, S3 artifacts/layers, NAT Gateway/VPC endpoints và data transfer;
7. **SQS/S3/DynamoDB/RDS/KMS** do handler gọi.

Một công thức sơ bộ cho phần compute với Event Function On-Demand:

\[
\text{GB-seconds} \approx
\text{số invocation} \times
\frac{\text{memory (MB)}}{1024}\times
\text{billed duration (seconds)}
\]

Ví dụ **1.000.000 invocation**, **512 MB**, **0,2 giây**:

\[
1{,}000{,}000\times 0.5\times 0.2
=100{,}000\ \text{GB-seconds}
\]

Đây là **ước lượng đơn giản**, chưa tính free tier, duration rounding, init/snapshot charges, request pricing, provisioned concurrency hoặc các chế độ pricing mới. Dùng **AWS Pricing Calculator/Cost Explorer/AWS Budgets** theo đúng Region và loại function.

**Bài học chi phí:** ZIP và image không có một quy tắc “cái nào luôn rẻ hơn khi invoke”. Package type chủ yếu làm khác quy trình artifact, quản lý dependencies/runtime và chi phí ECR/CI; compute billing còn phụ thuộc memory, duration, concurrency và cấu hình.

## 24. Troubleshooting: từ build đến invocation

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra đúng |
| --- | --- | --- |
| `ClassNotFoundException` hoặc `HandlerNotFound` | Sai package/class, handler string, artifact không chứa class | So `--handler`, `jar tf`, source package và build output |
| `NoClassDefFoundError` | Dependency không được đưa vào JAR/ZIP hoặc sai layer path | Kiểm tra Shade, `lib/`, layer `java/lib`, version dependencies |
| `UnsupportedClassVersionError` | Bytecode compile mới hơn runtime đang dùng | `maven.compiler.release`, Java runtime identifier, base image Java version |
| `ExceptionInInitializerError` | Static initializer bị lỗi, DB/secret call trong init, env thiếu | CloudWatch init logs, static fields, timeout, quyền IAM/network |
| `Task timed out after ...` | DB/API chậm, network không thông, retries vô hạn, memory/CPU thiếu | Duration, DNS/VPC/SG, SDK timeouts, DB metrics và code |
| `Runtime.OutOfMemory` hoặc OOM | Memory cấu hình quá nhỏ, nạp payload/file vào heap | REPORT Max Memory Used, JVM heap settings, streaming file |
| ZIP bị `RequestEntityTooLargeException` | Upload trực tiếp >50 MB hoặc giải nén vượt quota | ZIP/JAR size, S3 deployment, loại dependency, limit 250 MB |
| Image không tạo function được | ECR Region khác, repository policy thiếu, manifest/architecture sai | ECR URI/region, lambda permission, image digest, `docker buildx` |
| `Runtime.InvalidEntrypoint` / lỗi startup image | ENTRYPOINT/CMD không đúng Lambda Runtime API, native binary lỗi | Dockerfile, RIC, handler string, local RIE logs |
| Local Docker chạy được nhưng AWS lỗi | RIE không mô phỏng IAM/VPC/KMS/platform hoàn toàn | Test trên AWS, CloudWatch, SG, image architecture, IAM |
| Container không ghi được file | Root filesystem read-only, user không đủ quyền | Chỉ ghi `/tmp`, sửa file permissions, tránh chạy root |
| `AccessDenied` gọi S3/KMS | Role thiếu `s3:...`, `kms:...`, bucket/key policy Deny | Get caller identity qua SDK/log thích hợp, policy IAM/S3/KMS |
| Không gọi được RDS private | Lambda chưa vào VPC, subnet/SG/route/DNS sai | VPC config, DB SG, resolver, test TCP, CloudWatch logs |
| Không gọi được Internet sau khi attach VPC | Private subnet không có NAT/endpoint phù hợp | Route table, SG, NACL, NAT/endpoint, DNS |
| API Gateway báo 502 dù invoke success | Handler trả response sai proxy integration format | Event contract, response headers/statusCode/body |
| SQS message xử lý trùng | Retry, batch fail, visibility timeout, handler không idempotent | Event source mapping, DLQ, message ID, idempotency store |
| Image tag đã đổi nhưng code vẫn cũ | Lambda resolve tag sang digest tại deploy | Update-function-code bằng URI mới, get-function và log version |
| Không publish được version | Chưa có thay đổi từ version trước hoặc update đang diễn ra | `LastUpdateStatus`, code SHA/digest và deployment state |
| Logs không xuất hiện | Basic execution role/CloudWatch Logs permission thiếu, runtime fail sớm | Role, log group, init error, CloudTrail, Logs retention |
| Chi phí tăng nhanh | Memory/duration tăng, retry loop, provisioned concurrency, NAT/logs | Cost Explorer, metrics invocation/errors/concurrency, budget |

### Quy trình điều tra theo thứ tự

~~~text
1. Xác định account, Region, function name, package type và alias/version.
2. Kiểm tra GetFunction/GetFunctionConfiguration:
   runtime/handler hoặc ImageUri, role, memory, timeout, architecture, VPC.
3. Kiểm tra LastUpdateStatus, State và artifact (JAR classes / ECR digest).
4. Invoke với event đúng contract, xem CLI FunctionError và payload trả về.
5. Xem CloudWatch Logs, INIT/REPORT, stack trace, memory/timeout.
6. Nếu lỗi truy cập dịch vụ: IAM execution role + S3/KMS/secret/DB policies.
7. Nếu lỗi kết nối: VPC subnets, SG, route, DNS, NAT/endpoints, DB SG.
8. Nếu lỗi ở trigger: loại invoke, retry, DLQ, event source mapping,
   permissions của service gọi function và idempotency.
9. Sửa thay đổi nhỏ nhất, build/deploy revision mới, test canary/rollback.
10. Giám sát lỗi/latency/chi phí và ghi lại nguyên nhân gốc.
~~~

**Không chữa lỗi bằng** `AdministratorAccess` cho Lambda role, mở DB SG ra `0.0.0.0/0`, đưa access keys vào image hoặc bỏ retry/idempotency. Những thay đổi đó làm mất khả năng bảo vệ dữ liệu và che giấu nguyên nhân.

## 25. Kiến trúc minh họa: hóa đơn đơn hàng bằng Lambda Java

Bài toán: hệ thống bán hàng cần tạo PDF hóa đơn, lưu S3 và gửi thông báo sau khi khách đặt hàng.

~~~mermaid
flowchart TB
    User[Khách hàng] --> API[API Gateway + Auth]
    API --> Order[Order API / Lambda hoặc ECS]
    Order --> DB[(RDS / DynamoDB: order)]
    Order --> Q[(SQS: OrderCreated)]
    Q --> Map[Lambda event source mapping]
    Map --> Handler[Lambda Java OrderInvoiceHandler]
    Handler --> S3[(S3 invoices / SSE-KMS)]
    Handler --> Audit[(DynamoDB: idempotency)]
    Handler --> Email[SES / notification]
    Handler --> CW[CloudWatch Logs/Metrics]
    Q --> DLQ[(SQS DLQ)]
    S3 --> Backup[Versioning / lifecycle / backup]
~~~

### Thiết kế từng lớp

- **Event:** SQS record chứa `orderId`/metadata; không truyền cả PDF hoặc password trong event.
- **Handler:** đọc `Records`, kiểm tra input, dùng idempotency key `orderId`, fetch dữ liệu đơn hàng, tạo PDF và ghi S3.
- **Artifact:** Java 21 ZIP nếu dependencies vừa phải; container nếu cần native PDF rendering tools hoặc font/binary dependencies đặc thù đã kiểm tra.
- **IAM:** task/API/handler roles riêng; handler có quyền SQS theo integration, S3 PutObject trên prefix hóa đơn, KMS GenerateDataKey và quyền DB/DynamoDB cần thiết.
- **VPC:** chỉ attach function vào VPC nếu cần truy cập private DB hoặc tài nguyên private; kiểm soát NAT/VPC endpoints cho S3/Secrets Manager.
- **Data:** S3 SSE-KMS, versioning/retention, DLQ/retry, DB backup và idempotency storage.
- **Monitoring:** CloudWatch Errors/Duration/Throttles, SQS queue age, DLQ count, S3/KMS access errors, business rate hóa đơn hoàn tất.
- **Khả dụng:** Multi-AZ cho DB/queue theo tính năng AWS, đủ concurrency có giới hạn, cơ chế replay từ DLQ và kiểm thử phục hồi.
- **Chi phí:** số event, duration tạo PDF, memory/CPU, KMS API, S3 requests, logs và NAT/ECR storage theo package type.

**Giới hạn thực tế:** Nếu tạo PDF vượt timeout/memory hoặc cần binary rất nặng, có thể dùng **Step Functions + ECS Fargate/AWS Batch** thay vì ép vào một Lambda duy nhất.

## 26. Các bài tập áp dụng

### Bài tập 1 — Đọc đúng runtime và handler

**Đề bài:** Function `orders-zip-lab` dùng `runtime=java21`, handler config `com.example.lambda.Handler::handleRequest`; nhưng JAR có class `com/example/lambda/OrderHandler.class` triển khai `RequestHandler`.

1. Dự đoán loại lỗi khi invoke.
2. Nêu handler config đúng.
3. Chỉ ra cách kiểm tra JAR bằng `jar tf` và logs Lambda.
4. Giải thích khác biệt giữa function name và Java class name.

**Gợi ý:** Runtime phải tìm đúng class/method có thể tải từ classpath.

### Bài tập 2 — Chọn ZIP hay container image

**Yêu cầu:**

- Function A: nhận JSON nhỏ, dùng AWS SDK, chạy dưới 1 giây, build Java 21 Maven.
- Function B: tạo thumbnail cần native libraries được cài vào OS image, có pipeline Docker/ECR đã được kiểm soát.
- Function C: app đóng gói 300 MB khi giải nén vì có nhiều dependencies, muốn upload qua S3 rồi dùng ZIP.
- Function D: team muốn chuyển function đã triển khai ZIP sang image ngay trên cùng function resource.

**Kỳ vọng:** A ưu tiên ZIP; B đánh giá image; C S3 upload **không giải quyết** quota 250 MB, phải tối ưu artifact hoặc dùng image; D cần tạo function mới.

### Bài tập 3 — Phân biệt execution role và quyền trigger

S3 event notification gọi Lambda `invoice-processor`. Event được gửi nhưng function báo `AccessDenied` khi ghi object sang bucket khác.

Hãy phân biệt:

- Ai được quyền gọi Lambda?
- Execution role có `s3:PutObject` và `kms:GenerateDataKey` chưa?
- Bucket policy/KMS key policy có Deny hay thiếu allow?
- Tại sao thêm `lambda:InvokeFunction` vào execution role không giải quyết quyền ghi S3?

### Bài tập 4 — Tính concurrency và downstream capacity

API đạt **500 RPS**, mỗi invocation mất **0,4 giây**:

\[
\text{Concurrency} \approx 500 \times 0.4 = 200
\]

Nếu RDS chỉ chịu được 100 kết nối đồng thời trong configuration hiện tại, tại sao đặt reserved concurrency 500 có thể gây sự cố? Đề xuất pooling/RDS Proxy, cache, queue hoặc tối ưu query, và xác định metric cần giám sát.

### Bài tập 5 — Thiết kế CI/CD và rollback

Một function image đã dùng tag `v1`; nhóm đẩy image mới lên **cùng tag** và tin rằng production đã cập nhật.

Hãy trình bày:

1. Lambda resolve image tag/digest khi nào?
2. Vì sao tag thay đổi không đủ để production dùng code mới?
3. Các bước build, scan, push immutable artifact, update code, publish version, chuyển alias.
4. Cách rollback alias khi tỷ lệ `Errors`/p95 latency tăng.
5. Tại sao rollback không hoàn tác object/DB data đã bị ghi bởi release lỗi?

### Bài tập 6 — Java cold start và timeout

Java Lambda cold start 2 giây, xử lý nghiệp vụ 0,3 giây, memory 512 MB, timeout 3 giây; đôi lúc lời gọi DB mất 2 giây.

Hãy:

- phân biệt init latency với handler duration;
- đề xuất benchmark memory cao hơn, init optimization, SDK timeout, DB performance;
- đánh giá SnapStart/provisioned concurrency nếu đủ điều kiện;
- giải thích vì sao chỉ tăng timeout có thể làm concurrency và chi phí tăng.

### Bài tập 7 — Retry và idempotency

SQS chứa 10 messages/batch. Lambda đã ghi hóa đơn cho 9 messages rồi throw exception ở message thứ 10.

**Yêu cầu:** Giải thích nguy cơ xử lý lại 9 messages, đề xuất dùng partial batch response khi cấu hình hỗ trợ, idempotency key/conditional writes và DLQ. So sánh với API Gateway synchronous invocation.

## 27. Checklist trước khi triển khai production

- [ ] Đã chọn Lambda phù hợp workload theo thời gian chạy, memory, event model và độ nhạy latency.
- [ ] Xác nhận runtime còn được hỗ trợ, Java bytecode version và architecture phù hợp.
- [ ] Handler class/method/signature chính xác; test event phù hợp trigger chứ không chỉ direct invocation.
- [ ] Chọn package type ZIP hay Image có lý do; biết không thể chuyển cùng function tại chỗ.
- [ ] Với ZIP: build artifact có dependencies, kiểm tra classpath, size nén/giải nén, layers và S3 Region khi áp dụng.
- [ ] Với Image: Linux single-arch, RIC/runtime đúng, ECR đúng Region/policy, digest bất biến, chỉ ghi `/tmp`.
- [ ] Không lưu password/access key trong JAR/image/ENV/log; secrets và KMS được quản lý đúng.
- [ ] Execution role least privilege, resource-based policy chỉ cho nguồn invoke hợp lệ; deployer có `iam:PassRole` tối thiểu.
- [ ] Function VPC config chỉ khi cần, subnets/SG/route/DNS/NAT/endpoints phù hợp, test kết nối DB/service thực.
- [ ] Memory, CPU, timeout và `/tmp` được đặt theo benchmark, không chỉ mặc định.
- [ ] Xác định concurrency/quotas, reserved/provisioned concurrency và khả năng downstream chịu tải.
- [ ] Khi dùng S3/SQS/EventBridge, đã thiết kế retries, idempotency, failure destination/DLQ và alert.
- [ ] Có CloudWatch log/metrics, structured tracing, error rate, p95/p99, throttles và chi phí.
- [ ] Mỗi release có artifact/version/alias, integration tests, canary/rollback và dữ liệu tương thích.
- [ ] Runtime/image dependencies được scan/patch, có policy dọn ECR images/ZIP layers cũ mà không phá published versions.
- [ ] Có backup/DR cho S3/DB và kiểm thử business recovery; Lambda scale không thay database HA.
- [ ] Số invocation, GB-seconds, ECR, logs, NAT, KMS và dịch vụ phụ trợ có ngân sách/tags rõ ràng.

## 28. Tổng kết

**AWS Lambda runtime** là môi trường nhận sự kiện và gọi ứng dụng; **handler** là entry point phải khớp tên class/method/signature; **ZIP/JAR và container image** là hai cách triển khai mã khác nhau, mỗi cách có trách nhiệm, giới hạn và pipeline riêng.

Với **Java 21**, một luồng học cơ bản là: **viết `RequestHandler` → build shaded JAR → tạo execution role → deploy ZIP → invoke và đọc CloudWatch Logs**. Khi cần native dependencies hoặc hệ sinh thái Docker, có thể: **build Lambda-compatible image → thử bằng RIE → push ECR cùng Region → deploy function kiểu Image → invoke và giám sát**.

Cần nhớ **một deploy thành công không đồng nghĩa ứng dụng ổn định**. Khi đưa Lambda vào kiến trúc AWS thực tế, phải gắn với **IAM/KMS, Region/AZ, VPC, S3/SQS/RDS/DynamoDB, monitoring, retries/idempotency, concurrency, backups và ngân sách**. Đó là cách vận hành serverless an toàn, có khả năng phục hồi và đáp ứng nhu cầu người dùng.

### Tài liệu chính thức để đối chiếu

- [AWS Lambda runtimes](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html)
- [Building Lambda functions with Java](https://docs.aws.amazon.com/lambda/latest/dg/lambda-java.html)
- [Define Lambda handler in Java](https://docs.aws.amazon.com/lambda/latest/dg/java-handler.html)
- [Deploy Java functions with ZIP/JAR](https://docs.aws.amazon.com/lambda/latest/dg/java-package.html)
- [Working with layers for Java](https://docs.aws.amazon.com/lambda/latest/dg/java-layers.html)
- [Deploy Java Lambda with container images](https://docs.aws.amazon.com/lambda/latest/dg/java-image.html)
- [Create a Lambda function using a container image](https://docs.aws.amazon.com/lambda/latest/dg/images-create.html)
- [Lambda quotas and deployment limits](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)
- [Lambda execution environment lifecycle](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html)
- [Manage Lambda versions](https://docs.aws.amazon.com/lambda/latest/dg/configuration-versions.html)
- [Use Lambda aliases](https://docs.aws.amazon.com/lambda/latest/dg/configuration-aliases.html)
- [Lambda execution role](https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html)
- [Configure Lambda functions to access resources in a VPC](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html)
- [Lambda invocation models](https://docs.aws.amazon.com/lambda/latest/dg/lambda-invocation.html)
- [Using Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [AWS Lambda pricing](https://aws.amazon.com/lambda/pricing/)
- [AWS CLI Lambda command reference](https://docs.aws.amazon.com/cli/latest/reference/lambda/)

**Lưu ý triển khai:** Runtime identifiers, policy, quotas, package support, tính năng và giá có thể thay đổi theo Region, loại function và thời điểm. Đối chiếu tài liệu AWS hiện hành và thử nghiệm trong account/Region thực trước khi áp dụng vào production.
