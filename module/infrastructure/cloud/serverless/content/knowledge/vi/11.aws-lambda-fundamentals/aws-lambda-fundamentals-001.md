# Cấu trúc ứng dụng và mô hình tài nguyên AWS Lambda

AWS Lambda là dịch vụ FaaS của AWS: bạn triển khai mã xử lý, cấu hình cách chạy và kết nối function với nguồn kích hoạt; AWS quản lý việc cấp phát execution environment, mở rộng và hạ tầng máy chủ bên dưới. Một ứng dụng Lambda vì vậy không chỉ là một file JAR. Nó là tập hợp các tài nguyên có quan hệ với nhau: function, mã triển khai, runtime, execution role, quyền invoke, trigger, event source mapping, version, alias, cấu hình mạng, lưu trữ, concurrency và các thành phần quan sát vận hành.

Hiểu mô hình tài nguyên giúp xác định đúng nơi cấu hình một hành vi. Ví dụ, execution role quyết định function có thể đọc object trong S3 hay ghi vào DynamoDB; resource-based policy quyết định dịch vụ hoặc tài khoản nào được phép gọi function; event source mapping quyết định cách Lambda đọc message từ SQS hoặc stream; alias giúp client gọi một version ổn định trong khi nhóm triển khai version mới.

Với Java, mã ứng dụng thường được đóng gói dưới dạng ZIP/JAR cùng dependency hoặc container image. Runtime gọi handler theo contract của Lambda. Những object dùng chung như AWS SDK client có thể được khởi tạo một lần trong execution environment để tái sử dụng, nhưng dữ liệu nghiệp vụ và trạng thái cần tồn tại qua invocation phải được lưu trong dịch vụ bền vững như S3, DynamoDB hoặc database phù hợp.

## 1. Nhìn ứng dụng Lambda như một tập hợp tài nguyên

Một ứng dụng serverless điển hình có thể gồm nhiều function, mỗi function chịu trách nhiệm một bước nghiệp vụ. Các function được nối với nhau qua API Gateway, EventBridge, SNS, SQS, stream, workflow hoặc lời gọi trực tiếp.

~~~mermaid
flowchart LR
    C["Client"] --> APIGW["API Gateway"]
    APIGW --> F1["Order API function"]
    F1 --> DB[("DynamoDB / database")]
    F1 --> Q["SQS queue"]
    Q --> F2["Order worker function"]
    F2 --> S3[("S3 object storage")]
    EB["EventBridge rule"] --> F3["Notification function"]
    F3 --> SNS["SNS / email provider"]
    IAM["IAM roles and policies"] -.-> F1
    IAM -.-> F2
    IAM -.-> F3
    CW["CloudWatch logs and metrics"] -.-> F1
    CW -.-> F2
    CW -.-> F3
~~~

Có thể chia các tài nguyên thành những nhóm sau:

| Nhóm | Tài nguyên tiêu biểu | Vai trò |
|---|---|---|
| Compute | Lambda function, runtime, architecture, memory, timeout | Xác định mã nào chạy và giới hạn tài nguyên |
| Code packaging | ZIP deployment package, container image, Lambda layer | Cung cấp mã và thư viện cho runtime |
| Identity and access | Execution role, trust policy, permission policy, resource-based policy | Kiểm soát function gọi dịch vụ nào và ai được gọi function |
| Invocation | API Gateway integration, Function URL, EventBridge rule, SNS subscription | Kết nối nguồn sự kiện với function |
| Event consumption | Event source mapping, SQS queue, stream, batch settings | Điều khiển cách Lambda đọc và chuyển message vào function |
| Release | Published version, alias, weighted routing | Quản lý phiên bản và phát hành |
| State and storage | S3, DynamoDB, RDS, EFS, ephemeral storage | Lưu dữ liệu bền vững hoặc tạm thời |
| Network | VPC, subnet, security group, VPC endpoint, NAT | Kiểm soát kết nối tới tài nguyên mạng |
| Operations | CloudWatch Logs, metrics, alarms, tracing, destinations, DLQ | Quan sát, cảnh báo và phục hồi |

Một số tài nguyên thuộc chính function configuration; một số là tài nguyên độc lập tham chiếu đến function. Ví dụ, memory và timeout là cấu hình của function, còn event source mapping và alias là tài nguyên riêng. Khi triển khai bằng Infrastructure as Code, cần mô tả cả function lẫn các tài nguyên kết nối, thay vì chỉ tạo function rồi cấu hình trigger thủ công.

## 2. Lambda function là gì?

Lambda function là đơn vị triển khai và thực thi mã. Mỗi function có tên, ARN, code package hoặc image, runtime, handler, execution role và các thiết lập như memory, timeout, architecture, environment variables, VPC, layers, ephemeral storage và tracing.

Function không tương đương một máy chủ cố định. AWS tạo execution environment khi cần, có thể tái sử dụng môi trường đã khởi tạo cho invocation sau, và có thể tạo thêm môi trường khi tải tăng. Bạn không quản lý trực tiếp số máy ảo hoặc hệ điều hành bên dưới.

Một function thường có các thuộc tính:

- **Function name:** tên định danh trong một AWS account và Region.
- **Function ARN:** định danh tài nguyên để policy, trigger và client tham chiếu.
- **Code:** ZIP package hoặc container image URI.
- **Runtime:** môi trường thực thi được Lambda hỗ trợ, ví dụ Java runtime.
- **Handler:** entry point mà runtime gọi.
- **Execution role:** IAM role mà Lambda assume khi chạy function.
- **Memory size và timeout:** giới hạn tài nguyên và thời gian cho invocation.
- **Architecture:** kiến trúc CPU như x86_64 hoặc arm64 nếu runtime và package tương thích.
- **Environment variables:** cấu hình được truyền vào process.
- **VPC configuration:** subnet và security group nếu function cần truy cập tài nguyên trong VPC.
- **Layers và extensions:** thư viện hoặc tiến trình mở rộng được gắn vào execution environment.
- **Ephemeral storage:** dung lượng vùng lưu trữ tạm cục bộ.

Function có thể được gọi đồng bộ, bất đồng bộ hoặc thông qua event source mapping. Cách gọi quyết định ai chờ kết quả, ai chịu trách nhiệm retry và cách message được xác nhận.

## 3. Handler và runtime của Java

Runtime là thành phần khởi động ứng dụng và chuyển invocation đến handler. Với Java, handler thường là class triển khai interface của AWS Lambda Java Core hoặc class có method theo handler signature mà runtime hỗ trợ.

Ví dụ dùng RequestHandler:

~~~java
package com.example.orders;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;

public class OrderHandler
        implements RequestHandler<OrderRequest, OrderResponse> {

    @Override
    public OrderResponse handleRequest(
            OrderRequest request,
            Context context) {

        context.getLogger().log(
                "Processing order request: " + request.orderId()
        );

        return new OrderResponse(
                request.orderId(),
                "ACCEPTED"
        );
    }
}
~~~

Trong cấu hình function, handler được khai báo bằng tên class đầy đủ, ví dụ:

~~~text
com.example.orders.OrderHandler
~~~

Tên class và package phải khớp với nội dung artifact triển khai. Nếu đổi package hoặc class mà không cập nhật handler, Lambda không thể nạp entry point và invocation thất bại ngay ở giai đoạn khởi tạo.

Các lựa chọn phổ biến:

- RequestHandler<Input, Output> cho event được ánh xạ sang kiểu Java và trả về object.
- RequestStreamHandler khi cần tự đọc input stream và ghi output stream, thường hữu ích với payload hoặc adapter đặc thù.
- Handler tùy chỉnh theo contract runtime khi dùng custom runtime hoặc framework adapter.

Interface Context cung cấp thông tin invocation và runtime, ví dụ request ID, function name, memory limit, thời gian còn lại và logger. Không lưu Context vào static field hoặc dùng nó như state dùng chung giữa các invocation.

Với framework như Spring Boot, Quarkus hoặc Micronaut, cần dùng adapter hoặc integration phù hợp với Lambda runtime. Không phải mọi ứng dụng web server truyền thống đều có thể đưa nguyên trạng vào function mà không điều chỉnh bootstrap, handler và cách quản lý request.

## 4. Đóng gói mã: ZIP, JAR, layer và container image

Lambda hỗ trợ nhiều cách đóng gói mã. Chọn cách phù hợp với kích thước ứng dụng, dependency, native library, quy trình build và cách tổ chức release.

### ZIP deployment package

ZIP package chứa class đã biên dịch và dependency cần thiết. Với Java, một cách thường gặp là đặt class và resource trong thư mục gốc của archive, còn thư viện phụ thuộc trong thư mục lib theo cấu trúc runtime mong đợi. Cần kiểm tra cấu trúc artifact sau khi build; ZIP có thể tải lên thành công nhưng vẫn lỗi nếu handler hoặc dependency không nằm ở vị trí runtime tìm kiếm.

Ví dụ cấu trúc minh họa:

~~~text
function.zip
├── com/
│   └── example/
│       └── orders/
│           └── OrderHandler.class
└── lib/
    ├── aws-lambda-java-core.jar
    ├── jackson-databind.jar
    └── application-dependencies.jar
~~~

Có thể dùng Maven Shade Plugin hoặc Gradle Shadow Plugin để tạo artifact gộp dependency, hoặc tạo ZIP theo cấu trúc mà runtime hỗ trợ. Nếu dùng fat JAR, cần bảo đảm manifest, service loader, resource và metadata của dependency không bị ghi đè sai khi merge.

### Lambda layers

Layer là archive riêng chứa thư viện, custom runtime hoặc nội dung dùng chung cho nhiều function. Function có thể gắn nhiều layer theo giới hạn của Lambda. Layer giúp tách dependency dùng chung khỏi mã ứng dụng, nhưng cũng tạo thêm một thành phần version cần quản lý.

Nên dùng layer khi có thư viện hoặc công cụ thực sự được chia sẻ và cần phát hành độc lập. Không nên đưa mọi dependency vào một layer chung chỉ để giảm kích thước ZIP; version layer thay đổi có thể ảnh hưởng nhiều function, làm việc rollback và truy tìm dependency khó hơn.

Layer không phải nơi lưu dữ liệu nghiệp vụ và không tự cấp quyền truy cập cho function. Với Java, kiểm tra cấu trúc thư mục của layer để runtime nhận đúng JAR và classpath.

### Container image

Function có thể được triển khai dưới dạng container image lưu trong Amazon ECR. Cách này phù hợp khi cần kiểm soát môi trường đóng gói, có native dependency hoặc muốn dùng quy trình build container thống nhất. Image phải tuân theo Lambda container image contract, gồm runtime interface; AWS base image thường đã cung cấp các thành phần cần thiết.

Container image không biến Lambda thành một container service chạy liên tục. Lambda vẫn quản lý invocation, execution environment, scale và giới hạn runtime. Image cần được build cho kiến trúc CPU đã cấu hình và phải được cập nhật khi có bản vá runtime hoặc dependency.

### Chọn hình thức đóng gói

| Tiêu chí | ZIP/JAR | Layer | Container image |
|---|---|---|---|
| Mã ứng dụng | Đóng gói trực tiếp | Không phải nơi chính chứa handler | Đóng trong image |
| Dependency | Có thể đi cùng package | Tách thư viện dùng chung | Cài trong image |
| Tái sử dụng giữa function | Qua build artifact hoặc layer | Mục tiêu chính của layer | Qua base image/build pipeline |
| Kiểm soát hệ điều hành và native library | Hạn chế theo runtime | Hạn chế theo layer contract | Linh hoạt hơn trong giới hạn Lambda |
| Quy trình phát hành | ZIP upload hoặc S3 | Phát hành version layer riêng | Build, scan và push ECR image |

## 5. Execution role và resource-based policy

Một điểm dễ nhầm là quyền function dùng để gọi dịch vụ khác khác với quyền dịch vụ hoặc principal dùng để gọi function.

### Execution role

Execution role là IAM role Lambda assume khi thực thi. Trust policy của role cho phép service principal của Lambda assume role. Permission policies gắn với role quyết định function có thể thực hiện hành động nào trên tài nguyên AWS.

Ví dụ, một order worker có thể cần:

- Đọc message từ một queue cụ thể thông qua cơ chế trigger.
- Đọc hoặc ghi một bảng DynamoDB nhất định.
- Ghi log vào CloudWatch Logs.
- Đọc secret cần thiết từ Secrets Manager.
- Gọi một function khác nếu nghiệp vụ yêu cầu.

Hãy cấp quyền tối thiểu theo từng function. Không dùng một execution role rộng cho mọi function chỉ vì chúng thuộc cùng ứng dụng. Nếu function chỉ cần ghi object vào một prefix của bucket, policy nên giới hạn bucket, prefix và action cần thiết.

### Resource-based policy

Resource-based policy của Lambda quy định principal nào được phép invoke function hoặc qualifier của function. Policy này thường được bổ sung bằng quyền cho dịch vụ như API Gateway, S3, SNS hoặc EventBridge gọi function.

Ví dụ, một S3 bucket có thể được phép invoke function khi object được tạo trong một prefix cụ thể. Việc cấp quyền invoke cho S3 không làm function có quyền đọc mọi object trong bucket; function vẫn cần execution role cho hành động S3 mà nó thực hiện.

### Phân biệt hai hướng quyền

| Câu hỏi | Cơ chế chính |
|---|---|
| Function có thể đọc S3 hoặc ghi DynamoDB không? | Execution role và permission policy |
| EventBridge hoặc S3 có thể invoke function không? | Resource-based policy của function hoặc cơ chế tích hợp tương ứng |
| User hoặc service có thể gọi API Gateway không? | Authorization tại API Gateway và policy liên quan |
| Function có thể gọi function khác không? | Execution role của function gọi, cùng resource policy của function đích khi cần |

Với trigger và tích hợp AWS, kiểm tra cả hai đầu: nguồn có quyền invoke đích hay không, và function có quyền truy cập tài nguyên mà logic cần hay không. Không coi việc tạo trigger thành công là bằng chứng mọi quyền runtime đã đúng.

## 6. Các kiểu invocation và trigger

Lambda có thể được gọi theo nhiều cách. Kiểu invocation ảnh hưởng đến latency, response, retry và cách xử lý lỗi.

### Đồng bộ (synchronous)

Caller chờ function xử lý và nhận response. Các ví dụ thường gặp:

- API Gateway gọi Lambda cho HTTP API hoặc REST API.
- Application Load Balancer gọi Lambda target.
- Function URL cung cấp endpoint HTTPS cho function.
- Một ứng dụng gọi Lambda Invoke API với invocation type RequestResponse.
- Một function khác gọi trực tiếp function đích.

Nếu function timeout hoặc trả lỗi, caller nhận kết quả lỗi theo integration. Client có thể retry, vì vậy thao tác có side effect vẫn cần idempotency.

### Bất đồng bộ (asynchronous)

Nguồn gửi event và không chờ kết quả nghiệp vụ cuối cùng. Lambda tiếp nhận event vào hàng đợi nội bộ để xử lý sau. Ví dụ:

- S3 notification.
- SNS notification.
- EventBridge rule hoặc event bus.
- Lời gọi Invoke API với invocation type Event.

Cần cấu hình retry, maximum event age và dead-letter queue hoặc on-failure destination theo nhu cầu. Việc Lambda đã nhận event không có nghĩa handler đã xử lý thành công. Một event có thể được thử lại và tạo duplicate delivery; consumer phải idempotent.

### Poll-based với event source mapping

Với một số nguồn như SQS, Kinesis Data Streams, DynamoDB Streams, Amazon MSK hoặc nguồn tương thích, Lambda dùng event source mapping để đọc dữ liệu và chuyển batch vào function. Event source mapping là tài nguyên cấu hình riêng.

Nó có thể điều khiển:

- Nguồn event và function đích.
- Batch size và maximum batching window.
- Starting position đối với stream.
- Filter criteria.
- Parallelization và concurrency controls.
- Partial batch response hoặc bisect batch tùy nguồn.
- Retry, bisect và destination/error handling theo semantics của nguồn.

Với SQS, event source mapping poll queue và invoke function theo batch. Với Kinesis hoặc DynamoDB Streams, tiến độ đọc gắn với shard và sequence/iterator semantics. Không áp dụng cùng một mô hình acknowledgment cho mọi nguồn.

### Bảng so sánh

| Invocation type | Ai chờ kết quả? | Thành phần thường quản lý retry | Ví dụ |
|---|---|---|---|
| Synchronous | Caller | Caller hoặc integration theo cấu hình | API Gateway, Function URL |
| Asynchronous | Không chờ kết quả handler | Lambda async invocation configuration | S3, SNS, EventBridge |
| Event source mapping | Nguồn được poll và batch chuyển vào function | Event source mapping và broker semantics | SQS, Kinesis, DynamoDB Streams |

## 7. Event source mapping là tài nguyên riêng

Event source mapping kết nối một event source được hỗ trợ với một Lambda function. Đây không đơn thuần là một thuộc tính của handler. AWS quản lý poller hoặc việc đọc nguồn theo cấu hình mapping rồi invoke function.

Các thuộc tính quan trọng tùy loại nguồn:

- ARN của event source, ví dụ queue ARN hoặc stream ARN.
- Function ARN hoặc qualifier đích.
- Enabled/disabled state.
- Batch size và batching window.
- Starting position và starting position timestamp với nguồn stream.
- Filter criteria.
- Maximum concurrency hoặc scaling settings khi nguồn hỗ trợ.
- Partial batch response, bisect batch và retry policy.
- Tumbling window hoặc destination cho một số stream integration.

Với SQS, function có thể nhận nhiều message trong một invocation. Nếu một message lỗi, có thể bật partial batch response để chỉ báo message thất bại nếu integration hỗ trợ. Nếu không, cả batch có thể được giao lại; idempotency theo message là cần thiết.

Với stream, record được chia theo shard hoặc partition và có yêu cầu về thứ tự. Một lỗi ở record có thể ảnh hưởng tiến độ shard; cấu hình bisect batch hoặc failure destination có thể giúp cách ly record lỗi. Hãy hiểu chính sách retry và checkpoint của từng event source trước khi thay đổi batch size hoặc concurrency.

Event source mapping thường cần quyền đọc nguồn ở execution role của function. Ví dụ, mapping SQS cần quyền receive, delete và đọc thuộc tính queue theo yêu cầu của Lambda; quyền cụ thể cần được cấp tối thiểu. Khi mapping không hoạt động, kiểm tra trạng thái mapping, permission, encryption key policy, network/dependency và metric của nguồn.

## 8. Versions, aliases và phát hành có kiểm soát

Lambda có khái niệm version và alias để tách việc cập nhật function khỏi cách client gọi function.

- **$LATEST:** bản function mutable, thay đổi khi cập nhật code hoặc configuration.
- **Published version:** snapshot bất biến của code và phần cấu hình versioned tại thời điểm publish.
- **Alias:** tên tham chiếu đến một version cụ thể; alias có thể được cập nhật để trỏ sang version khác và hỗ trợ weighted routing trong các trường hợp phù hợp.

ARN không qualifier tham chiếu function không chỉ rõ version; qualifier có thể là version hoặc alias. Khi API Gateway, event source mapping hoặc client tham chiếu alias, nhóm có thể phát hành version mới rồi chuyển alias sau khi kiểm thử.

Ví dụ quy trình:

1. Cập nhật code và cấu hình của $LATEST.
2. Chạy kiểm thử và xác minh artifact.
3. Publish version mới.
4. Cập nhật alias staging hoặc production trỏ tới version đó.
5. Nếu cần, chia traffic giữa version hiện tại và version mới theo tỷ lệ.
6. Theo dõi error rate, latency và business metrics.
7. Chuyển toàn bộ traffic hoặc rollback alias về version trước.

Alias không phải một function độc lập và không tạo execution role hay storage riêng. Nó là một điểm tham chiếu tới version. Weighted routing có thể hỗ trợ canary release nhưng không thay thế kiểm thử tương thích database/schema hoặc xử lý event đang tồn đọng.

Environment variables và một số cấu hình nhạy cảm cần được quản lý theo versioning và deployment process của Lambda. Hãy xác minh rõ thuộc tính nào được đóng băng khi publish version và thuộc tính nào có thể thay đổi ngoài version theo tài liệu AWS hiện hành.

## 9. Memory, timeout, architecture và concurrency

Lambda cho phép cấu hình tài nguyên và giới hạn cho mỗi function. Những thiết lập này ảnh hưởng đến latency, khả năng xử lý, mở rộng và chi phí.

### Memory và CPU

Memory setting xác định bộ nhớ cấp cho execution environment; CPU capacity được phân bổ tương ứng với cấu hình memory theo mô hình của Lambda. Tăng memory có thể làm giảm thời gian chạy CPU-bound và một số bước khởi tạo, nhưng chi phí mỗi đơn vị thời gian cũng thay đổi.

Hãy benchmark nhiều mức memory với cùng artifact và workload. So sánh latency p95/p99, throughput, memory usage và chi phí cho mỗi invocation thành công. Không chọn memory chỉ dựa vào heap tối thiểu của JVM.

### Timeout

Timeout giới hạn thời gian một invocation được phép chạy. Chọn timeout theo SLA, thời gian dependency, batch size và thời gian cần để ghi kết quả hoặc xử lý lỗi. Timeout quá dài có thể giữ tài nguyên và message lâu; timeout quá ngắn tạo lỗi không cần thiết và retry.

### Architecture

Lambda hỗ trợ architecture như x86_64 và arm64 tùy runtime. Package và native dependency phải tương thích với architecture được cấu hình. Nếu dùng JNI, thư viện native hoặc container image, build và kiểm thử cho đúng target architecture.

### Concurrency

Concurrency là số invocation đang chạy đồng thời. Các khái niệm chính:

- **Account concurrency limit:** giới hạn concurrency ở cấp account/Region.
- **Reserved concurrency:** dành riêng và đồng thời giới hạn concurrency tối đa cho một function.
- **Provisioned concurrency:** chuẩn bị sẵn execution environment để giảm cold start cho capacity được cấu hình.
- **Maximum concurrency của event source mapping:** giới hạn tốc độ hoặc số invocation do một mapping tạo ra khi loại nguồn hỗ trợ.

Reserved concurrency giúp bảo vệ dependency và bảo đảm một function có capacity riêng, nhưng cũng có thể giới hạn khả năng mở rộng của chính function. Provisioned concurrency giúp giảm cold start cho traffic cần độ trễ ổn định nhưng có chi phí duy trì. Đây là hai mục tiêu khác nhau; không dùng chúng thay thế cho nhau.

Khi tính concurrency, hãy nhân số invocation tối đa với số lời gọi song song, connection pool và batch size. Function scale tốt nhưng database hoặc API đối tác có thể trở thành nút thắt.

## 10. Environment variables, secrets và cấu hình

Environment variables cung cấp cấu hình runtime như tên bảng, bucket, endpoint, feature flag hoặc mức timeout ứng dụng. Không nên đưa password, API key hoặc credential dài hạn vào source code hay file cấu hình được commit.

Với secret, ưu tiên AWS Secrets Manager hoặc Systems Manager Parameter Store cùng execution role giới hạn quyền đọc. Cân nhắc cache secret trong execution environment để giảm latency và chi phí, nhưng phải có TTL/refresh phù hợp với rotation. Không cache vô thời hạn một credential có thể bị thu hồi.

Một số nguyên tắc:

- Tách cấu hình theo environment như dev, staging và production.
- Không dùng tên tài nguyên cố định nếu triển khai nhiều stack hoặc Region.
- Validate cấu hình bắt buộc khi khởi tạo function.
- Không log toàn bộ environment variables.
- Mã hóa environment variables bằng cơ chế của Lambda/KMS khi cần.
- Giới hạn quyền KMS decrypt theo key và principal.
- Xác định cách cập nhật secret và thời gian function nhận giá trị mới.

Environment variables không phải kho lưu trữ state. Giá trị trong process có thể còn tồn tại khi environment được tái sử dụng nhưng có thể biến mất khi environment bị thu hồi.

## 11. VPC, mạng và quyền truy cập tài nguyên riêng

Mặc định, Lambda có thể truy cập các dịch vụ AWS qua endpoint công khai của dịch vụ theo cấu hình mạng của nền tảng. Nếu function cần truy cập database hoặc service chỉ nằm trong VPC, có thể gắn function vào một hoặc nhiều subnet và security group phù hợp.

Khi gắn VPC:

- Chọn subnet có route phù hợp với tài nguyên đích.
- Security group của function phải cho phép egress cần thiết.
- Security group của database hoặc service phải cho phép ingress từ security group của function.
- Nếu cần gọi internet công khai, thiết kế NAT hoặc egress path phù hợp.
- Cân nhắc VPC endpoint cho dịch vụ AWS để truy cập riêng tư và giảm phụ thuộc NAT.
- Kiểm tra DNS, route table, NACL, security group và quota liên quan.

Function gắn vào private subnet không tự động có internet access. Một route tới Internet Gateway từ subnet private không cấp public IP cho Lambda ENI theo cách của một EC2 instance public. Hãy thiết kế egress qua NAT hoặc endpoint theo nhu cầu.

VPC configuration ảnh hưởng tới khả năng kết nối và cold start behavior tùy kiến trúc dịch vụ. Không gắn function vào VPC nếu không có yêu cầu truy cập tài nguyên private; nếu cần, đo latency và kiểm thử đường mạng từ môi trường triển khai thực tế.

## 12. Storage: ephemeral storage, S3, DynamoDB và EFS

Lambda có vùng lưu trữ tạm cục bộ, thường được truy cập qua thư mục /tmp. Vùng này hữu ích cho file trung gian, giải nén package hoặc xử lý payload lớn trong phạm vi invocation/environment. Nó không phải durable storage và có thể còn nội dung khi environment được tái sử dụng.

| Storage | Tính chất | Dùng cho |
|---|---|---|
| Memory/heap | Nhanh, chỉ tồn tại trong process | Cache nhỏ, object trong một invocation |
| /tmp ephemeral storage | Lưu file tạm cục bộ của execution environment | Giải nén, chuyển đổi file, staging ngắn hạn |
| Amazon S3 | Object storage bền vững, mở rộng | File upload, báo cáo, artifact, payload lớn |
| DynamoDB | NoSQL database được quản lý | State, idempotency, metadata, lookup |
| RDS/Aurora | Database quan hệ | Transaction và truy vấn quan hệ |
| Amazon EFS | File system dùng chung có thể mount vào Lambda | Workload cần filesystem bền vững/chia sẻ và được hỗ trợ |

Nếu cần dữ liệu sống qua invocation hoặc được nhiều environment chia sẻ, lưu ở dịch vụ bền vững. Đừng dùng static map hoặc /tmp như nguồn sự thật duy nhất. Với EFS, kiểm tra VPC, mount target, security group, throughput và quyền truy cập file.

## 13. Layers, extensions và runtime configuration

Layer cung cấp thư viện hoặc nội dung bổ sung cho function. Extension là tiến trình mở rộng có thể tham gia lifecycle của execution environment, ví dụ gửi telemetry hoặc lấy cấu hình. Chúng có thể giúp tái sử dụng công cụ giữa nhiều function, nhưng cũng tiêu thụ tài nguyên và ảnh hưởng thời gian khởi tạo.

Khi thêm layer hoặc extension:

- Xác định version cụ thể và owner của artifact.
- Kiểm tra tương thích runtime và architecture.
- Kiểm tra thứ tự hoặc cách merge file nếu nhiều layer có nội dung trùng.
- Đo ảnh hưởng đến cold start, memory và thời gian shutdown.
- Giới hạn quyền của extension và endpoint mà nó gọi.
- Theo dõi version và phát hành cập nhật bảo mật.
- Không đặt logic nghiệp vụ cốt lõi vào extension khó quan sát hoặc khó kiểm thử.

Lambda extensions có thể chạy trong execution environment cùng function, nhưng chúng không phải một function riêng được invoke theo cách độc lập. Chúng có lifecycle và giới hạn tài nguyên cần được hiểu theo runtime.

## 14. Logging, metrics, tracing và destinations

CloudWatch Logs thường được dùng để lưu log của function. Execution role cần quyền ghi log phù hợp; khi thiếu quyền, handler có thể chạy nhưng log không xuất hiện như mong đợi. Log cần có request ID, correlation ID, function version hoặc alias, kết quả và latency; không ghi token, secret hoặc payload nhạy cảm.

Các lớp quan sát:

- **Logs:** chi tiết một invocation và lỗi.
- **Metrics:** invocation count, error count, duration, throttles, concurrency, iterator age hoặc queue age tùy nguồn.
- **Tracing:** theo dõi đường đi qua API Gateway, Lambda và dependency bằng AWS X-Ray hoặc OpenTelemetry theo cấu hình.
- **Alarms:** cảnh báo khi error rate, latency, throttling, DLQ hoặc backlog vượt ngưỡng.
- **Destinations:** định tuyến kết quả invocation bất đồng bộ thất bại hoặc thành công tới tài nguyên đích theo cấu hình.

Không nhầm asynchronous invocation destination với DLQ. Destination có thể nhận metadata và context về invocation result; DLQ thường giữ event/message thất bại theo semantics cấu hình. Chọn cơ chế theo nhu cầu điều tra, replay và xử lý tiếp.

Với event source mapping, theo dõi metric của queue hoặc stream bên cạnh Lambda. Function có thể có error rate thấp nhưng queue age tăng do concurrency thấp hoặc dependency bị throttle. Với Kinesis/DynamoDB Streams, iterator age và shard-level progress là chỉ báo quan trọng.

## 15. Triển khai ứng dụng bằng Infrastructure as Code

Một ứng dụng Lambda cần nhiều tài nguyên liên kết. Infrastructure as Code giúp tạo môi trường nhất quán, review thay đổi, kiểm soát drift và tái tạo stack.

Các công cụ thường gặp:

- AWS SAM: mô hình hóa Lambda, API, event source và các tài nguyên serverless bằng template.
- AWS CDK: định nghĩa tài nguyên bằng ngôn ngữ lập trình và sinh CloudFormation.
- CloudFormation: khai báo tài nguyên AWS theo template.
- Terraform: quản lý hạ tầng qua provider và state của Terraform.

Một template function cần khai báo hoặc tham chiếu các thuộc tính như:

~~~yaml
Resources:
  OrderFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: order-api
      Runtime: java21
      Handler: com.example.orders.OrderHandler
      Role: !GetAtt OrderExecutionRole.Arn
      Code:
        S3Bucket: deployment-artifacts
        S3Key: orders/order-function.zip
      MemorySize: 1024
      Timeout: 15
      Architectures:
        - arm64
      Environment:
        Variables:
          ORDERS_TABLE: orders
~~~

Đây là ví dụ CloudFormation rút gọn để minh họa resource model. Giá trị runtime phải nằm trong danh sách runtime được AWS hỗ trợ tại thời điểm triển khai; bucket, key, role và tên tài nguyên cần được điều chỉnh theo môi trường. Template production còn cần policy, logging, tracing, VPC nếu cần, version/alias, trigger và các thiết lập bảo vệ dữ liệu.

Nên triển khai theo thứ tự phụ thuộc: tạo role và policy, tạo function, publish version, tạo alias, sau đó kết nối API/trigger/event source mapping theo ARN qualifier mong muốn. CloudFormation có thể quản lý quan hệ phụ thuộc nếu khai báo đúng resource reference.

Không chỉnh sửa trực tiếp tài nguyên production ngoài IaC mà không cập nhật source of truth. Thay đổi thủ công dễ tạo configuration drift và khiến lần deploy sau ghi đè thiết lập quan trọng.

## 16. Ví dụ mô hình tài nguyên cho một ứng dụng xử lý đơn hàng

Giả sử ứng dụng có API tạo đơn, worker xử lý thanh toán và function gửi thông báo.

| Tài nguyên | Cấu hình hoặc quyền chính | Mục đích |
|---|---|---|
| API Gateway route | POST /orders, authorizer, integration | Nhận request và gọi Order API |
| Order API Lambda | Java handler, memory, timeout, execution role | Validate và ghi đơn hàng |
| Order execution role | Ghi bảng Orders, publish queue, ghi log | Quyền outbound của API function |
| Orders table | Partition key theo order ID hoặc tenant design | Lưu trạng thái đơn |
| Payment queue | Retention, visibility timeout, redrive policy | Tách xử lý thanh toán khỏi request |
| Payment worker Lambda | Event source mapping, batch size, concurrency | Xử lý message thanh toán |
| Payment worker role | Consume queue, cập nhật trạng thái đơn, gọi secret service | Quyền outbound của worker |
| Notification rule/queue | EventBridge hoặc SNS tùy luồng | Phát thông báo sau trạng thái phù hợp |
| Notification Lambda | Java handler và quyền gửi notification | Gửi thông báo |
| Versions and aliases | Version đã publish và alias production | Phát hành/rollback có kiểm soát |
| CloudWatch | Logs, metrics, alarms, tracing | Theo dõi lỗi, latency và backlog |

Luồng xử lý:

1. Client gọi API Gateway.
2. API Gateway xác thực và invoke Order API Lambda.
3. Function kiểm tra quyền, validate dữ liệu và ghi đơn hàng với trạng thái PENDING_PAYMENT.
4. Function gửi message vào payment queue và trả 202 hoặc 201 tùy contract nghiệp vụ.
5. Event source mapping đọc queue và invoke Payment worker.
6. Worker gọi payment provider, cập nhật trạng thái đơn hàng và xác nhận message theo contract.
7. Khi thanh toán thành công, event được phát để notification function gửi thông báo.
8. CloudWatch metrics và logs giúp theo dõi từng bước bằng correlation ID.

Mỗi function có execution role riêng và chỉ có quyền cần thiết. Queue có DLQ hoặc redrive policy; worker xử lý duplicate message bằng idempotency. API, worker và notification có thể được phát hành version độc lập nhưng phải duy trì tương thích event contract.

## 17. Naming, tagging và phân tách môi trường

Khi số lượng function tăng, naming và tagging giúp xác định owner, môi trường, chi phí và mục đích. Một quy ước có thể gồm tên sản phẩm, domain, workload và environment, ví dụ:

~~~text
orders-api-dev
orders-worker-staging
orders-notification-prod
~~~

Tag có thể gồm:

- Application hoặc system.
- Environment.
- Team/owner.
- Cost center.
- Data classification.
- ManagedBy hoặc IaC stack.
- Repository hoặc release identifier nếu chính sách cho phép.

Không đưa secret, thông tin cá nhân hoặc dữ liệu nhạy cảm vào tên function hay tag. Tên function, ARN và tag có thể xuất hiện trong log, metric, audit và console.

Tách account hoặc environment theo ranh giới bảo mật và vận hành phù hợp. Không dùng chung role production với staging chỉ để giảm số lượng policy. Cấu hình endpoint, bucket, table và secret nên được truyền theo environment và được kiểm tra khi deploy.

## 18. Chi phí và giới hạn cần tính trong resource model

Chi phí Lambda không chỉ là số lần gọi function. Tùy cấu hình và cách tích hợp, chi phí có thể gồm request, duration theo memory, provisioned concurrency, ephemeral storage vượt mức bao gồm, data transfer, CloudWatch Logs, API Gateway, queue, database, NAT và các dịch vụ khác.

Các thiết lập ảnh hưởng chi phí:

- Memory và thời gian thực thi.
- Số invocation và concurrency.
- Provisioned concurrency và thời gian duy trì.
- Kích thước log, retention và tần suất trace.
- Số lần retry, batch size và message backlog.
- Số connection và request tới dependency.
- Data transfer qua NAT hoặc giữa AZ/Region.
- Storage, versioning và lifecycle của object.

Hãy đo chi phí theo luồng nghiệp vụ thay vì chỉ theo function. Một function rẻ nhưng gọi database quá nhiều hoặc tạo nhiều log có thể làm tổng chi phí ứng dụng cao. Giới hạn concurrency có thể giảm tải và chi phí downstream, nhưng nếu đặt quá thấp sẽ làm tăng queue age và thời gian hoàn thành.

## 19. Quy trình thiết kế và triển khai một function

Có thể dùng trình tự sau cho mỗi function:

1. **Xác định trách nhiệm:** function thực hiện một bước nghiệp vụ rõ ràng và có input/output contract.
2. **Chọn trigger:** HTTP, direct invocation, async event hoặc event source mapping.
3. **Chọn runtime và handler:** xác định Java runtime, handler signature và framework adapter.
4. **Đóng gói artifact:** ZIP/JAR, layers hoặc container image; kiểm tra dependency và architecture.
5. **Tạo execution role:** trust policy cho Lambda và permission tối thiểu tới tài nguyên cần thiết.
6. **Cấu hình resource:** memory, timeout, ephemeral storage, environment variables, VPC và concurrency.
7. **Cấp quyền invoke:** resource-based policy hoặc tích hợp phù hợp cho principal/trigger.
8. **Thiết kế state và retry:** database, queue, idempotency, DLQ và timeout.
9. **Tạo release resources:** publish version, alias và chiến lược chuyển traffic.
10. **Quan sát:** logs, metrics, traces, alarms và destination.
11. **Triển khai bằng IaC:** khai báo function cùng trigger và dependency.
12. **Kiểm thử và phát hành:** kiểm tra quyền, trigger, duplicate event, timeout, scale, rollback và chi phí.

Một bài kiểm tra hữu ích là truy vết hai hướng quyền: từ caller đến function và từ function đến tài nguyên. Nếu không thể xác định principal nào invoke function, function assume role nào, role đó có quyền gì và trigger được cấu hình ở đâu, resource model vẫn chưa đầy đủ.

## 20. Checklist rà soát ứng dụng AWS Lambda

Trước khi đưa function vào production, hãy kiểm tra:

1. Tên, ARN, Region và account của function đã đúng chưa?
2. Runtime, handler và artifact có tương thích không?
3. Package ZIP hoặc image có đầy đủ class, resource và dependency không?
4. Architecture của function có khớp artifact và native library không?
5. Execution role có trust policy và permission tối thiểu không?
6. Resource-based policy có giới hạn đúng principal và nguồn invoke không?
7. Trigger là synchronous, asynchronous hay event source mapping?
8. Retry, timeout, batch, visibility/ack và DLQ có đúng semantics nguồn không?
9. Function có lưu state quan trọng ra dịch vụ bền vững không?
10. Memory, timeout, ephemeral storage và concurrency có được benchmark không?
11. VPC, subnet, security group, route và endpoint có cho phép kết nối cần thiết không?
12. Secret và environment variables có được quản lý an toàn không?
13. Version và alias có hỗ trợ release/rollback không?
14. Logs, metrics, tracing và alarms có đủ để điều tra không?
15. IaC có quản lý function và các tài nguyên liên quan không?
16. Có kiểm thử duplicate event, burst, dependency failure và permission denial không?
17. Có theo dõi chi phí của Lambda và toàn bộ dependency không?

## Kết luận

Một ứng dụng AWS Lambda là tập hợp tài nguyên liên kết quanh function: code package, runtime, handler, execution role, trigger, event source mapping, resource policy, storage, network, concurrency, version/alias và thành phần vận hành. Function xác định mã và cấu hình thực thi; IAM quyết định quyền theo hai hướng; trigger hoặc event source mapping xác định cách sự kiện đi vào; version và alias kiểm soát phát hành.

Với Java, hãy chọn runtime và handler phù hợp, đóng gói dependency có thể tái tạo, tái sử dụng client thread-safe trong execution environment và lưu state nghiệp vụ ở dịch vụ bền vững. Khi các tài nguyên được mô hình hóa bằng IaC, cấp quyền tối thiểu, quan sát đầy đủ và kiểm thử theo đúng semantics invocation, ứng dụng Lambda sẽ dễ triển khai, mở rộng và vận hành hơn.

