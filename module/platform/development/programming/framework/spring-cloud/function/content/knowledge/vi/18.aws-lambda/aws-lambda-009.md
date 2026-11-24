# Truy cập thông tin lần gọi và ngữ cảnh AWS

Khi một hàm **Spring Cloud Function** chạy trên **AWS Lambda**, ngoài payload nghiệp vụ, AWS còn cung cấp một đối tượng **Context** chứa thông tin của lần gọi hiện tại và môi trường thực thi. Context có thể cho biết **AWS request ID**, tên và version của Lambda, ARN được gọi, giới hạn bộ nhớ, CloudWatch log group/log stream và thời gian còn lại trước timeout. Những dữ liệu này hữu ích cho logging, correlation, giới hạn thời gian gọi dịch vụ downstream và chẩn đoán sự cố.

Với handler **FunctionInvoker** của **spring-cloud-function-adapter-aws**, ứng dụng không cần tự viết một AWS handler chỉ để nhận Context. Adapter đưa đối tượng Context của invocation vào **Spring Message header** có tên **aws-context**. Vì vậy, một bean có chữ ký **Function<Message<T>, R>** có thể đọc payload bằng **message.getPayload()** và lấy Context từ **message.getHeaders()**. Đây là cách giữ logic nghiệp vụ dựa trên Supplier, Function và Consumer, đồng thời chỉ phụ thuộc AWS khi thực sự cần thông tin runtime.

Bài thuộc chương **AWS Lambda**. Ta sẽ phân biệt **AWS Lambda Context** với **Spring ApplicationContext**, tìm hiểu các trường thông tin, đọc Context qua Message header, dùng request ID để truy vết, kiểm tra thời gian còn lại, ghi log, truyền context qua tác vụ bất đồng bộ, kiểm thử bằng mock và xử lý các rủi ro về bảo mật/vòng đời.

## 1. AWS Lambda Context là gì?

Khi Lambda runtime gọi handler Java, runtime truyền ba thành phần theo hợp đồng của **RequestStreamHandler**:

~~~java
void handleRequest(
    InputStream input,
    OutputStream output,
    Context context
) throws IOException;
~~~

- **InputStream** chứa payload của một invocation.
- **OutputStream** nhận kết quả mà handler trả về runtime.
- **Context** chứa metadata của invocation, function và execution environment.

AWS cung cấp interface **com.amazonaws.services.lambda.runtime.Context** trong thư viện **aws-lambda-java-core**. Một handler Java tự viết có thể nhận Context trực tiếp ở tham số thứ ba. Khi dùng **Spring Cloud Function FunctionInvoker**, adapter nhận tham số đó thay cho bạn và gắn đối tượng vào Message trước khi gọi bean nghiệp vụ.

~~~mermaid
sequenceDiagram
    participant AWS as AWS Lambda runtime
    participant INV as FunctionInvoker
    participant MSG as Spring Message
    participant FN as Function bean

    AWS->>INV: handleRequest(input, output, Context)
    INV->>MSG: tạo Message(payload, headers)
    Note over MSG: header aws-context chứa Context của invocation
    INV->>FN: apply(Message<T>)
    FN->>MSG: đọc payload và Context
    FN-->>INV: kết quả R
    INV-->>AWS: serialize và ghi output
~~~

**Context thuộc về một invocation cụ thể.** Nó không phải một cấu hình dùng chung của ứng dụng và không nên được giữ trong field static hoặc field của singleton Spring bean để sử dụng ở lần gọi sau.

## 2. Phân biệt AWS Context với Spring ApplicationContext

Hai tên có chữ Context nhưng phục vụ hai mục đích hoàn toàn khác nhau:

| Đối tượng | Package | Chứa gì? | Vòng đời điển hình |
| --- | --- | --- | --- |
| **AWS Lambda Context** | com.amazonaws.services.lambda.runtime.Context | Request ID, function ARN/version, memory limit, remaining time, logger... | Một invocation |
| **Spring ApplicationContext** | org.springframework.context.ApplicationContext | Bean, dependency injection, configuration, environment, lifecycle... | Thường khởi tạo khi execution environment bắt đầu và có thể được tái sử dụng giữa các invocation ấm |

~~~text
AWS Lambda Context
  -> awsRequestId
  -> functionName / functionVersion
  -> invokedFunctionArn
  -> remainingTimeInMillis
  -> LambdaLogger

Spring ApplicationContext
  -> FunctionCatalog
  -> Function beans
  -> Service / Repository
  -> Spring Environment
~~~

Không lấy **ApplicationContext** để đọc AWS request ID. Cũng không dùng **AWS Context** thay cho Spring bean container. Hai đối tượng có thể cùng tồn tại trong một invocation, nhưng không thay thế nhau.

### Vì sao phân biệt vòng đời quan trọng?

Spring bean mặc định thường là singleton trong một ApplicationContext. Một Lambda execution environment có thể giữ context đó qua nhiều invocation. Nếu gán AWS Context vào field singleton, lần gọi tiếp theo có thể đọc nhầm request ID hoặc metadata của invocation trước.

Mô hình an toàn:

- Giữ dependency ổn định như repository, client và service trong Spring bean.
- Nhận AWS Context qua **Message header** cho từng lần gọi.
- Đọc các giá trị cần thiết ngay trong invocation.
- Truyền những giá trị đó tường minh cho tác vụ bất đồng bộ nếu cần.
- Không giữ đối tượng Context trong cache, static field hoặc singleton state.

## 3. Những thông tin quan trọng trong AWS Context

Các phương thức thường dùng của interface Context:

| Phương thức | Ý nghĩa | Trường hợp sử dụng |
| --- | --- | --- |
| **getAwsRequestId()** | ID duy nhất của lần invocation | Correlation log, hỗ trợ tra cứu sự cố |
| **getFunctionName()** | Tên Lambda function | Phân biệt service/function trong log |
| **getFunctionVersion()** | Version đang thực thi, có thể là $LATEST | Điều tra version hoặc alias |
| **getInvokedFunctionArn()** | ARN được dùng để gọi function | Biết qualifier/version/alias được invoke |
| **getRemainingTimeInMillis()** | Thời gian còn lại trước timeout, tính bằng ms | Quyết định có đủ thời gian gọi downstream hay không |
| **getMemoryLimitInMB()** | Mức memory đã cấu hình cho Lambda | Ghi nhận cấu hình và phân tích hiệu năng |
| **getLogGroupName()** | Tên CloudWatch log group | Liên hệ invocation với log group |
| **getLogStreamName()** | Log stream của execution environment | Hỗ trợ tìm log chi tiết |
| **getLogger()** | LambdaLogger của runtime | Ghi log qua API Lambda |
| **getIdentity()** | Cognito identity trong các kiểu invocation hỗ trợ | Thông tin identity theo ngữ cảnh mobile |
| **getClientContext()** | Client context do ứng dụng client cung cấp trong các kiểu invocation hỗ trợ | Metadata client tùy trường hợp |

Không phải mọi phương thức đều có giá trị hữu ích trong mọi loại invocation. Ví dụ **getIdentity()** và **getClientContext()** chủ yếu liên quan tới một số cách gọi từ mobile SDK; không nên giả định chúng có dữ liệu khi Lambda được kích hoạt bởi SQS, S3 hoặc API Gateway.

### Request ID không phải business event ID

**awsRequestId** định danh một lần Lambda invocation. Nếu một lần invocation xử lý batch 10 SQS messages, các message trong batch chia sẻ cùng request ID của invocation đó. Mỗi message vẫn có messageId riêng, và business event có thể có eventId riêng do producer tạo.

| ID | Phạm vi | Ví dụ dùng |
| --- | --- | --- |
| **awsRequestId** | Một lần Lambda invocation | Tra cứu log của invocation |
| **SQS messageId** | Một message trong queue | Partial batch failure, theo dõi message |
| **eventId** | Một business event theo contract ứng dụng | Idempotency và deduplication |
| **API request ID** | Một HTTP request theo gateway/integration | Đối chiếu request phía client và gateway |

Không dùng AWS request ID làm idempotency key của nghiệp vụ nếu producer có thể gửi lại cùng event trong một invocation mới. Với SQS, eventId ổn định thường phù hợp hơn cho dedup; messageId phù hợp với giao thức SQS.

## 4. Spring Cloud Function đưa Context vào Message header

Tài liệu AWS adapter của Spring Cloud Function mô tả: **mỗi invocation**, framework thêm một Message header tên **aws-context** và giá trị là đối tượng Context của invocation đó. Hàm nhận **Message<YourPojo>** có thể truy cập header này.

Spring Cloud Function cung cấp hằng số:

~~~java
org.springframework.cloud.function.adapter.aws.AWSLambdaUtils.AWS_CONTEXT
~~~

Hằng số này giúp tránh gõ sai tên header. Nếu cần đọc ví dụ độc lập với hằng số của adapter, key tương ứng là chuỗi **aws-context**.

~~~mermaid
flowchart LR
    A["Lambda invocation payload"] --> B["FunctionInvoker"]
    B --> C["Message<OrderRequest>"]
    D["AWS Context hiện tại"] --> C
    C --> E["Message headers"]
    C --> F["Payload"]
    E --> G["aws-context"]
    F --> H["OrderRequest"]
~~~

Ví dụ:

~~~java
Context context = message.getHeaders().get(
    AWSLambdaUtils.AWS_CONTEXT,
    Context.class
);
~~~

Sau khi lấy được Context, có thể đọc:

~~~java
String requestId = context.getAwsRequestId();
int remainingMs = context.getRemainingTimeInMillis();
String functionName = context.getFunctionName();
~~~

**Không nhận header này từ JSON body của caller.** Adapter tự thêm header khi nó xử lý invocation. Một client không thể tạo AWS Context thật bằng cách gửi một field có tên aws-context trong payload; đó chỉ là dữ liệu do client cung cấp, không phải đối tượng runtime được Lambda cấp.

## 5. Ví dụ Spring Boot: Function nhận Message và đọc Context

Ta tạo một ứng dụng Spring Boot với bean **inspectInvocation**. Hàm nhận **Message<InvocationRequest>**, đọc payload và lấy metadata từ AWS Context. Kết quả chỉ chứa một tập trường được chọn, không trả toàn bộ Context cho caller.

Tệp **src/main/java/example/lambda/LambdaContextApplication.java**:

~~~java
package example.lambda;

import java.util.function.Function;

import com.amazonaws.services.lambda.runtime.Context;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.function.adapter.aws.AWSLambdaUtils;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;

@SpringBootApplication
public class LambdaContextApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            LambdaContextApplication.class, args);
    }

    public record InvocationRequest(
        String operation,
        String resourceId
    ) {}

    public record InvocationSnapshot(
        String requestId,
        String functionName,
        String functionVersion,
        String invokedFunctionArn,
        int memoryLimitMb,
        int remainingTimeMs,
        String logGroup,
        String logStream
    ) {}

    @Bean("inspectInvocation")
    Function<Message<InvocationRequest>, InvocationSnapshot>
            inspectInvocation() {

        return message -> {
            Context awsContext = message.getHeaders().get(
                AWSLambdaUtils.AWS_CONTEXT,
                Context.class
            );

            if (awsContext == null) {
                throw new IllegalStateException(
                    "AWS Lambda Context header is unavailable");
            }

            return new InvocationSnapshot(
                awsContext.getAwsRequestId(),
                awsContext.getFunctionName(),
                awsContext.getFunctionVersion(),
                awsContext.getInvokedFunctionArn(),
                awsContext.getMemoryLimitInMB(),
                awsContext.getRemainingTimeInMillis(),
                awsContext.getLogGroupName(),
                awsContext.getLogStreamName()
            );
        };
    }
}
~~~

### Vì sao chữ ký dùng Message<InvocationRequest>?

Nếu khai báo:

~~~java
Function<InvocationRequest, InvocationSnapshot>
~~~

hàm chỉ nhận payload nghiệp vụ. Không có đối tượng Message để đọc header **aws-context**. Khi cần cả payload và metadata, khai báo:

~~~java
Function<Message<InvocationRequest>, InvocationSnapshot>
~~~

Payload vẫn lấy bằng **message.getPayload()**; header lấy bằng **message.getHeaders()**.

### Không trả toàn bộ Context

Ví dụ chỉ tạo **InvocationSnapshot** từ những trường cần thiết. Không serialize Context thành JSON và trả ra caller vì:

- Context là đối tượng runtime, không phải DTO API.
- Nó có thể chứa thông tin nội bộ về function, log và invocation.
- Một số trường không có ý nghĩa với caller.
- Việc serialize một implementation runtime không phải contract ổn định.

Chọn các trường cần thiết và chỉ công khai chúng khi có lý do nghiệp vụ rõ ràng.

## 6. Cấu hình Lambda chọn bean và handler

Ứng dụng cần dependency **spring-cloud-function-adapter-aws** và một artifact AWS deployable phù hợp (thường là shaded JAR). Ví dụ cấu hình Lambda:

~~~text
Handler:
  org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest

MAIN_CLASS:
  example.lambda.LambdaContextApplication

spring_cloud_function_definition:
  inspectInvocation
~~~

Ba giá trị có trách nhiệm khác nhau:

| Cấu hình | Vai trò |
| --- | --- |
| **FunctionInvoker::handleRequest** | Entry point của AWS Lambda runtime |
| **MAIN_CLASS** hoặc manifest Start-Class | Lớp khởi tạo Spring application |
| **spring_cloud_function_definition** | Tên bean được FunctionCatalog chọn |

Không đặt **inspectInvocation** làm handler AWS. Đó là tên bean trong Spring, không phải Java handler contract.

### Dependency khi mã nguồn import Context

Ứng dụng dùng trực tiếp kiểu **Context** cần có **aws-lambda-java-core** trên compile classpath. Adapter có thể khai báo thư viện này theo scope phục vụ runtime; vì mã ứng dụng import interface, hãy khai báo dependency phù hợp trực tiếp trong build và đồng bộ version tương thích.

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-aws</artifactId>
</dependency>

<dependency>
    <groupId>com.amazonaws</groupId>
    <artifactId>aws-lambda-java-core</artifactId>
    <version>1.4.0</version>
</dependency>
~~~

Đây là đoạn dependency minh họa, không phải POM đầy đủ. Version **aws-lambda-java-core** phải tương thích với adapter và runtime được khóa trong dự án. Quản lý Spring Boot/Spring Cloud bằng BOM hoặc dependencyManagement tương ứng.

Nếu chỉ dùng **FunctionInvoker** mà không import Context trong code ứng dụng, không nhất thiết phải thêm trực tiếp mọi AWS type dependency khác.

## 7. Dùng request ID để correlation log

Request ID giúp kết nối các log entry phát sinh trong cùng một lần Lambda invocation. Ví dụ:

~~~java
@Bean("processOrder")
Function<Message<OrderRequest>, OrderResult> processOrder(
        OrderService orderService) {

    return message -> {
        Context context = message.getHeaders().get(
            AWSLambdaUtils.AWS_CONTEXT,
            Context.class);

        if (context == null) {
            throw new IllegalStateException(
                "Missing AWS invocation context");
        }

        String requestId = context.getAwsRequestId();

        org.slf4j.Logger log =
            org.slf4j.LoggerFactory.getLogger(
                LambdaContextApplication.class);

        log.info(
            "Processing order: awsRequestId={}, operation={}",
            requestId,
            message.getPayload().operation());

        OrderResult result =
            orderService.process(message.getPayload());

        log.info(
            "Order processed: awsRequestId={}, orderId={}",
            requestId,
            result.orderId());

        return result;
    };
}
~~~

Đoạn này minh họa cách gắn request ID vào log. Các kiểu **OrderRequest**, **OrderResult** và **OrderService** là hợp đồng giả định của ví dụ, cần được định nghĩa trong ứng dụng thực tế.

### AWS Lambda logger và SLF4J

Có hai cách ghi log thường gặp:

~~~java
context.getLogger().log(
    "awsRequestId=" + context.getAwsRequestId()
        + " operation=processOrder");
~~~

hoặc dùng logger của ứng dụng:

~~~java
log.info(
    "Processing request awsRequestId={} operation={}",
    requestId,
    operation);
~~~

**LambdaLogger** là logger do AWS cung cấp trong Context. **SLF4J** giúp ứng dụng dùng cùng logging API với Spring ecosystem. Khi chọn một cách, cấu hình log level/JSON format phù hợp với CloudWatch. Không log nguyên payload, access token, cookie hoặc dữ liệu nhạy cảm chỉ để có thêm thông tin debug.

### Request ID và log stream

**getLogGroupName()** thường trả tên log group, còn **getLogStreamName()** giúp định vị stream của execution environment. Dùng request ID để tìm invocation trong log; dùng log group/stream làm thông tin hỗ trợ điều tra. Không coi log stream là định danh business request hoặc một ID ổn định qua mọi lần gọi.

## 8. Dùng remaining time để bảo vệ downstream call

Một trong những giá trị hữu ích nhất của Context là:

~~~java
int remainingMs = context.getRemainingTimeInMillis();
~~~

Giá trị này cho biết số mili giây còn lại trước khi Lambda timeout. Thời gian giảm trong lúc Function chạy; không nên đọc một lần ở đầu invocation rồi giả định nó không đổi.

Một cách tiếp cận an toàn là giữ **buffer** để còn đủ thời gian serialize response, ghi log và kết thúc invocation:

~~~java
private static final int RESPONSE_BUFFER_MS = 1_500;

static long downstreamBudgetMs(Context context) {
    long remaining = context.getRemainingTimeInMillis();
    long budget = remaining - RESPONSE_BUFFER_MS;

    if (budget <= 0) {
        throw new IllegalStateException(
            "Insufficient Lambda time for downstream call");
    }

    return budget;
}
~~~

Nếu Lambda còn 4.000 ms và buffer 1.500 ms, budget lý thuyết cho phần downstream là khoảng 2.500 ms. Đây chỉ là **giới hạn thời gian đề xuất cho call**, không phải cam kết call sẽ hoàn thành trong khoảng đó.

### Truyền timeout sang HTTP client hoặc AWS SDK

Không để request downstream chờ lâu hơn phần thời gian Lambda còn lại. Ví dụ với một API client có hỗ trợ request timeout:

~~~java
long budgetMs = downstreamBudgetMs(context);

java.time.Duration timeout =
    java.time.Duration.ofMillis(budgetMs);

// Đặt timeout cho request cụ thể bằng API của HTTP client
// đang dùng; tránh tạo một client mới cho mỗi invocation.
~~~

Với AWS SDK for Java v2, có thể dùng per-request override configuration để đặt **apiCallTimeout** hoặc timeout phù hợp. Cú pháp cụ thể tùy service/client và version SDK.

**Không chỉ đặt timeout của Lambda rồi để downstream request chạy mặc định.** Nếu downstream timeout dài hơn Lambda, invocation có thể bị runtime kết thúc trước khi code nhận được kết quả và xử lý lỗi.

### Kiểm tra lại trước mỗi bước dài

Nếu một Function xử lý nhiều mục:

~~~java
for (OrderItem item : items) {
    if (context.getRemainingTimeInMillis() < 2_000) {
        throw new IllegalStateException(
            "Not enough time to continue safely");
    }

    processItem(item);
}
~~~

Đoạn code là minh họa chính sách dừng trước timeout. Ứng dụng thật cần quyết định phần công việc đã hoàn thành được ghi nhận thế nào. Nếu đang xử lý SQS batch, hãy kết hợp với **partial batch response** khi contract cho phép; nếu không, ném lỗi có thể khiến cả batch được giao lại.

**Buffer phải dựa trên số liệu thực tế**: thời gian serialize, thời gian cleanup, retry và latency downstream. Không sao chép 2.000 ms vào mọi Lambda như một giá trị tối ưu chung.

## 9. Dùng Context để quan sát function version và ARN

Các trường:

~~~java
context.getFunctionName();
context.getFunctionVersion();
context.getInvokedFunctionArn();
~~~

có thể hỗ trợ quan sát và chẩn đoán:

- Xác định function resource nào đang chạy.
- Xem invocation đi qua version hoặc alias nào.
- Phân tách log giữa staging/production khi tổ chức dùng các Lambda resources riêng.
- Hỗ trợ điều tra sự cố rollout.

Không dùng các trường này làm cách thay thế cho **configuration management**. Nếu behavior phải khác giữa môi trường, cấu hình bằng Spring property/environment variable hoặc resource riêng. Tránh viết business rule phụ thuộc tên Lambda rải rác trong code.

### Version và alias

Một invocation có thể đi qua ARN chứa qualifier/version hoặc alias. **getFunctionVersion()** và **getInvokedFunctionArn()** giúp hiểu context được invoke. Khi điều tra kết quả không khớp cấu hình, hãy kiểm tra cả alias/version mà caller thực sự gọi.

Không lấy **$LATEST** làm mặc định trong mọi log hoặc test; version thực tế phụ thuộc cách deploy/invoke.

## 10. ClientContext và Cognito Identity có phải dữ liệu xác thực không?

AWS Context có các phương thức:

~~~java
context.getClientContext();
context.getIdentity();
~~~

Những phương thức này có thể trả dữ liệu khi Lambda được gọi theo một số cơ chế mobile client tương ứng. Trong nhiều invocation khác, chúng có thể là **null**.

Không suy luận:

- **ClientContext** là token xác thực của API Gateway.
- **CognitoIdentity** luôn tồn tại trong mọi invocation.
- **awsRequestId** chứng minh người gọi đã được xác thực.
- Một field client gửi trong payload tương đương AWS Context do runtime cấp.

Authentication và authorization phải dựa vào cơ chế tin cậy của nguồn gọi, chẳng hạn API Gateway authorizer, IAM policy hoặc hệ thống xác thực ứng dụng. AWS Context chủ yếu là **metadata runtime**.

Nếu có sử dụng Cognito identity, kiểm tra đúng kiểu invocation, cấu hình authorizer/identity pool và contract AWS đang triển khai. Không đưa các trường identity vào log hoặc output nếu không cần.

## 11. Không inject Context như một Spring singleton

Một cách dễ bị nhầm là:

~~~java
@Component
class BadContextHolder {

    private Context context;

    public void setContext(Context context) {
        this.context = context;
    }
}
~~~

Nếu bean này là singleton và nhiều invocation sử dụng chung execution environment, giá trị context có thể bị ghi đè hoặc giữ lại từ invocation khác. Trong môi trường có concurrency, nguy cơ race condition càng rõ.

Cũng không nên viết:

~~~java
private static Context currentContext;
private static String currentRequestId;
~~~

để lưu thông tin invocation hiện tại. Đây là **request-scoped data**, không phải application-scoped state.

Mẫu đúng là truyền Message hoặc trích các giá trị cần thiết trong lời gọi:

~~~java
Function<Message<OrderRequest>, OrderResult>
~~~

Nếu một service cần request ID, truyền nó qua tham số rõ ràng hoặc một object metadata bất biến được tạo cho invocation. Không để service tự đọc một singleton mutable.

## 12. Context trong tác vụ bất đồng bộ

Một Function có thể khởi tạo tác vụ async, CompletableFuture hoặc gửi công việc vào executor. Không giả định AWS Context tự động có mặt trong mọi thread mới.

Ví dụ:

~~~java
Context context = message.getHeaders().get(
    AWSLambdaUtils.AWS_CONTEXT,
    Context.class);

String requestId = context.getAwsRequestId();

executor.submit(() -> {
    log.info(
        "Background step: awsRequestId={}",
        requestId);
});
~~~

Đoạn này truyền **requestId** đã trích xuất vào tác vụ, thay vì giữ Context trong field toàn cục.

### Một nguyên tắc quan trọng

**Lambda chỉ bảo đảm invocation trong thời gian handler còn chạy theo contract của runtime.** Không tạo background task rồi trả response trước khi task hoàn tất và mong Lambda tiếp tục thực hiện sau đó. Runtime có thể freeze hoặc tái sử dụng execution environment; task có thể không hoàn thành hoặc chạy xen với invocation tiếp theo tùy loại runtime/cấu hình.

Nếu công việc phải tiếp tục sau response:

- Đẩy công việc sang SQS, EventBridge hoặc workflow phù hợp.
- Ghi trạng thái bền vững trước khi trả kết quả.
- Dùng một Lambda invocation riêng để thực hiện phần tiếp theo.
- Truyền request ID/correlation ID rõ ràng như metadata, không truyền Context object qua queue.

Nếu tác vụ vẫn chạy trong invocation, hãy truyền **deadline/budget** đã tính và chờ hoàn tất trước khi Function return. Với Lambda Managed Instances có thể có nhiều request thread đồng thời trong cùng execution environment; không chia sẻ mutable per-invocation state qua static field.

## 13. Context không thay thế trace và correlation trong hệ thống phân tán

AWS request ID hữu ích trong một Lambda invocation, nhưng một nghiệp vụ có thể đi qua nhiều dịch vụ:

~~~mermaid
flowchart LR
    A["API Gateway"] --> B["Lambda A"]
    B --> C["SQS"]
    C --> D["Lambda B"]
    D --> E["Database / API downstream"]
~~~

Trong chuỗi này:

- Lambda A có **awsRequestId** riêng.
- Lambda B có **awsRequestId** khác.
- SQS message có **messageId** riêng.
- Business event có thể giữ một **eventId/correlationId** xuyên toàn luồng.
- Trace system có trace/span identifiers riêng.

Nếu chỉ ghi awsRequestId, không thể luôn nối mọi bước của một business operation. Nên giữ **correlationId/eventId** trong message hoặc metadata có kiểm soát, đồng thời ghi request ID của từng Lambda invocation.

Không dùng correlation ID do client tự gửi làm bằng chứng xác thực. Nếu cần ngăn giả mạo hoặc ghi đè, xác định nguồn tin cậy, xác thực/chuẩn hóa ID ở ranh giới đầu vào.

### X-Ray và tracing

AWS Lambda có thể tích hợp tracing thông qua cấu hình runtime và AWS X-Ray/OpenTelemetry. **Context interface cơ bản** không phải nơi thay thế toàn bộ trace propagation API. Hãy dùng tracing SDK/agent tương thích và truyền trace context qua cơ chế được hỗ trợ. Không tự suy ra trace ID bằng cách parse request ID hoặc log stream.

## 14. Unit test bằng mock Context

Không cần AWS thật để test một Function đọc Context. Dùng Mockito tạo một **Context** giả và gắn nó vào Message header.

Tệp **src/test/java/example/lambda/LambdaContextFunctionTest.java**:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.amazonaws.services.lambda.runtime.Context;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.function.adapter.aws.AWSLambdaUtils;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class LambdaContextFunctionTest {

    @Test
    void readsContextFromAwsHeader() {
        Context context = mock(Context.class);

        when(context.getAwsRequestId())
            .thenReturn("request-test-001");
        when(context.getFunctionName())
            .thenReturn("quote-function");
        when(context.getFunctionVersion())
            .thenReturn("42");
        when(context.getInvokedFunctionArn())
            .thenReturn(
                "arn:aws:lambda:ap-southeast-1:123456789012:function:quote-function:42");
        when(context.getMemoryLimitInMB())
            .thenReturn(512);
        when(context.getRemainingTimeInMillis())
            .thenReturn(4500);
        when(context.getLogGroupName())
            .thenReturn("/aws/lambda/quote-function");
        when(context.getLogStreamName())
            .thenReturn("2026/11/24/[$LATEST]sample");

        var app = new LambdaContextApplication();

        Message<LambdaContextApplication.InvocationRequest> message =
            MessageBuilder.withPayload(
                new LambdaContextApplication.InvocationRequest(
                    "quote", "BOOK"))
                .setHeader(AWSLambdaUtils.AWS_CONTEXT, context)
                .build();

        var result = app.inspectInvocation().apply(message);

        assertEquals("request-test-001", result.requestId());
        assertEquals("quote-function", result.functionName());
        assertEquals(4500, result.remainingTimeMs());
        assertEquals(512, result.memoryLimitMb());
    }
}
~~~

Test này kiểm tra logic đọc header và ánh xạ metadata. Nó **không** chứng minh AWS runtime thật đã truyền Context; phần tích hợp đó do FunctionInvoker thực hiện. Khi chạy test, cần có dependency **mockito** trong starter test phù hợp với Spring Boot version.

### Test khi thiếu Context

Một unit test khác nên bảo đảm hàm không âm thầm tiếp tục khi header không có:

~~~java
@Test
void rejectsMissingAwsContext() {
    var app = new LambdaContextApplication();

    Message<LambdaContextApplication.InvocationRequest> message =
        MessageBuilder.withPayload(
            new LambdaContextApplication.InvocationRequest(
                "quote", "BOOK"))
            .build();

    org.junit.jupiter.api.Assertions.assertThrows(
        IllegalStateException.class,
        () -> app.inspectInvocation().apply(message));
}
~~~

Nếu cùng bean còn được dùng ngoài AWS (ví dụ unit test, HTTP adapter hoặc một môi trường khác), có thể thiết kế một **InvocationMetadataProvider** tùy chọn và cách xử lý khi không có AWS Context. Đừng mặc định header này tồn tại khi bean chạy qua mọi protocol.

## 15. Kiểm thử deadline và remaining time

Có thể test helper tính budget độc lập:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.amazonaws.services.lambda.runtime.Context;
import org.junit.jupiter.api.Test;

class LambdaTimeBudgetTest {

    @Test
    void reservesTimeForResponse() {
        Context context = mock(Context.class);
        when(context.getRemainingTimeInMillis())
            .thenReturn(4000);

        long budget = 4000 - 1500;

        assertEquals(2500, budget);
    }

    @Test
    void doesNotStartWhenBudgetIsExhausted() {
        Context context = mock(Context.class);
        when(context.getRemainingTimeInMillis())
            .thenReturn(1000);

        assertThrows(IllegalStateException.class, () -> {
            long budget =
                context.getRemainingTimeInMillis() - 1500;

            if (budget <= 0) {
                throw new IllegalStateException(
                    "Insufficient time");
            }
        });
    }
}
~~~

Ví dụ này kiểm tra nguyên tắc reserve time. Trong ứng dụng thật nên tách helper **downstreamBudgetMs(Context)** thành method dùng chung và test method đó, thay vì lặp phép trừ trong nhiều Function.

**Không giả lập thời gian còn lại bằng một giá trị cố định trong production.** Runtime cung cấp giá trị động; một lần đọc chỉ là snapshot tại thời điểm gọi. Đo lại trước các bước dài và cấu hình timeout downstream tương ứng.

## 16. FunctionCatalog integration test

Ngoài unit test trực tiếp method **@Bean**, cần xác minh Spring đăng ký bean theo đúng tên:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = LambdaContextApplication.class)
class LambdaContextCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void registersInvocationFunction() {
        assertNotNull(catalog.lookup("inspectInvocation"));
    }
}
~~~

Test này xác minh FunctionCatalog tìm được bean **inspectInvocation**. Nó chưa kiểm tra header **aws-context**, vì header chỉ được adapter thêm khi có invocation Lambda thật hoặc khi test tự tạo Message có header đó.

Không ép kiểu hoặc so sánh identity của FunctionCatalog wrapper với bean gốc; catalog có thể bọc function để hỗ trợ conversion và message handling.

## 17. Logging và CloudWatch: biết mình đang xem thông tin nào

AWS Lambda Java runtime ghi các dòng hệ thống như **START**, **END** và **REPORT**. REPORT thường có các số liệu:

- **RequestId**: ID của invocation.
- **Duration**: thời gian handler xử lý.
- **Billed Duration**: thời gian được tính phí.
- **Memory Size**: memory limit được cấu hình.
- **Max Memory Used**: mức memory sử dụng cao nhất được báo cáo.
- **Init Duration**: thời gian khởi tạo cho cold start trong trường hợp áp dụng.

Các số liệu trong REPORT không phải tất cả đều nằm trên AWS Context. Ví dụ **getMemoryLimitInMB()** trả memory limit cấu hình, không phải **Max Memory Used**. Muốn biết memory sử dụng thực tế, xem Lambda REPORT/log metrics phù hợp.

### Structured logging

Có thể bật JSON log format và log level thông qua advanced logging controls của Lambda, kết hợp logger tương thích. Khi log theo cấu trúc, nên có các trường:

~~~json
{
  "level": "INFO",
  "message": "Order processing completed",
  "awsRequestId": "request-test-001",
  "functionName": "quote-function",
  "operation": "quote",
  "outcome": "SUCCESS"
}
~~~

Đây là **ví dụ cấu trúc do ứng dụng định nghĩa**, không khẳng định Lambda tự tạo mọi key như vậy. AWS Java runtime có thể dùng key **AWSrequestId** trong JSON log record tùy logger/runtime configuration. Nếu tự ghi field **awsRequestId**, tránh tạo hai key có nghĩa tương đương nhưng tên khác nhau mà không có quy ước.

Không log toàn bộ object Context bằng cách gọi toString/serialize để debug. Chỉ ghi những trường được phép và cần thiết.

## 18. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Header **aws-context** null | Không chạy qua FunctionInvoker AWS adapter hoặc unit test chưa gắn header | Xác minh handler/adapter; tạo Message header trong test |
| ClassNotFound **Context** | Thiếu aws-lambda-java-core trên compile classpath | Khai báo dependency tương thích |
| **getRemainingTimeInMillis()** gần 0 | Downstream call hoặc xử lý trước đó tốn thời gian | Tính budget, đặt timeout, dừng trước khi hết thời gian |
| Request ID của nhiều request giống nhau trong log | Đã giữ Context/request ID trong singleton/static field | Đọc header cho từng Message, không lưu mutable state |
| Không tìm thấy function | Sai **spring_cloud_function_definition** hoặc bean không được scan | Kiểm tra @Bean và FunctionCatalog |
| Context không serialize được | Trả cả Context ra output hoặc đưa vào DTO | Chỉ map trường cần thiết sang DTO |
| getIdentity/getClientContext null | Loại invocation không cung cấp các trường đó | Xem contract nguồn gọi, xử lý optional |
| Log có request ID nhưng không nối được SQS record | Dùng invocation ID thay cho messageId/eventId | Ghi cả ID invocation và ID record/business |
| Async task thiếu context | Không truyền metadata vào thread mới | Truyền requestId/deadline tường minh |
| Lambda timeout khi downstream treo | Timeout downstream dài hơn thời gian Lambda còn lại | Tính timeout theo remaining time và buffer |
| MemoryLimit bị hiểu là memory đã dùng | Nhầm cấu hình với runtime metric | Xem REPORT Max Memory Used |
| Log group/stream không có | Context/logging chưa sẵn sàng hoặc môi trường khác | Xác minh runtime và quyền log |
| Context header hoạt động trong Lambda nhưng null ở HTTP test | HTTP invocation không tạo AWS Context | Thiết kế metadata abstraction/optional context |
| Dùng request ID để xác thực user | Nhầm correlation với identity | Xác thực qua authorizer/IAM/application security |

## 19. Checklist sử dụng Context an toàn

- [ ] Function nhận **Message<T>** khi cần đọc header AWS Context.
- [ ] Lấy Context từ **AWSLambdaUtils.AWS_CONTEXT** (header **aws-context**).
- [ ] Kiểm tra Context có tồn tại nếu bean có thể chạy ngoài AWS.
- [ ] Dùng **awsRequestId** để correlation log của invocation.
- [ ] Dùng **messageId/eventId** riêng cho từng record/business event.
- [ ] Đọc **getRemainingTimeInMillis()** trước tác vụ dài.
- [ ] Đặt timeout downstream nhỏ hơn budget còn lại và chừa buffer cho response.
- [ ] Không lưu Context trong singleton/static field hoặc cache.
- [ ] Truyền metadata tường minh vào async task nếu cần.
- [ ] Không trả hoặc serialize toàn bộ Context cho client.
- [ ] Không dùng Context/request ID làm authentication hoặc authorization.
- [ ] Không log payload/headers/secrets không cần thiết.
- [ ] Kiểm thử cả function logic, FunctionCatalog và adapter invocation.
- [ ] Đo duration/memory/cold start bằng metrics/logs thực tế, không suy từ Context.

## 20. Bài tập thực hành

**Bài tập 1 — Phân biệt Context.** Giải thích khác nhau giữa **com.amazonaws.services.lambda.runtime.Context** và **org.springframework.context.ApplicationContext**. Đưa ra ví dụ dữ liệu thuộc về invocation và dữ liệu thuộc về ứng dụng.

**Bài tập 2 — Đọc header.** Viết một bean **Function<Message<OrderRequest>, OrderResult>** đọc **aws-context**, lấy request ID và function version, rồi ghi log có correlation.

**Bài tập 3 — Không lưu singleton.** Tìm lỗi trong một service lưu **Context currentContext** ở field. Mô tả tình huống execution environment ấm tái sử dụng giữa hai invocation khiến request ID bị nhầm.

**Bài tập 4 — Timeout budget.** Lambda còn 2.800 ms, cần reserve 800 ms để ghi response và cleanup. Tính budget cho downstream; đề xuất cách truyền timeout vào HTTP client/AWS SDK.

**Bài tập 5 — SQS batch.** Một invocation nhận 10 SQS records. Giải thích vì sao cả 10 records có thể dùng chung awsRequestId nhưng vẫn cần messageId/eventId riêng. Thiết kế log cho từng record.

**Bài tập 6 — Async task.** Một Function submit tác vụ vào executor rồi trả ngay. Giải thích vì sao Lambda không bảo đảm tác vụ hoàn tất sau response và đề xuất dùng SQS/Step Functions hoặc chờ hoàn tất trong invocation.

**Bài tập 7 — Unit test.** Dùng Mockito tạo Context giả với requestId và remaining time. Gắn nó vào Message header bằng AWSLambdaUtils.AWS_CONTEXT, kiểm tra output snapshot.

**Bài tập 8 — Context null.** Một Function được dùng cả trong Lambda và unit test thông thường. Đề xuất contract xử lý khi không có AWS Context, không dùng một Context giả toàn cục.

**Bài tập 9 — Observability.** Thiết kế structured log có awsRequestId, functionName, eventId, operation, outcome và duration. Giải thích trường nào là invocation metadata và trường nào là business metadata.

**Bài tập 10 — Bảo mật.** Một caller gửi JSON có field **awsRequestId** và **identity**. Giải thích vì sao không được coi các field này là Context thật hoặc bằng chứng xác thực.

### Ghi nhớ

- AWS Lambda truyền **Context** cho handler ở mỗi invocation; Spring Cloud Function AWS adapter đưa Context vào Message header **aws-context**.
- Dùng **Function<Message<T>, R>** khi cần cả payload và metadata; lấy Context qua **AWSLambdaUtils.AWS_CONTEXT**.
- **AWS Context** là dữ liệu theo invocation; **Spring ApplicationContext** là container quản lý bean. Không lưu Context trong singleton hoặc static field.
- **awsRequestId** giúp truy vết invocation; **messageId/eventId** vẫn cần cho từng record và business operation.
- **getRemainingTimeInMillis()** hỗ trợ giới hạn downstream timeout; phải chừa buffer cho serialization/response và recheck trước tác vụ dài.
- Context không thay authentication/authorization, tracing framework, idempotency hoặc storage bền vững.
- Kiểm thử bằng Context mock và FunctionCatalog; xác minh đường adapter bằng Lambda staging khi cần.

### Tài liệu tham khảo

- [Spring Cloud Function — AWS Lambda: AWS Context](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): header aws-context, Message input và AWSLambdaUtils.AWS_CONTEXT.
- [AWS Lambda — Using the Lambda context object in Java](https://docs.aws.amazon.com/lambda/latest/dg/java-context.html): các phương thức Context, request ID, remaining time và logger.
- [AWS Lambda — Java handler](https://docs.aws.amazon.com/lambda/latest/dg/java-handler.html): hợp đồng handler Java và tham số Context.
- [AWS Lambda — Log and monitor Java functions](https://docs.aws.amazon.com/lambda/latest/dg/java-logging.html): LambdaLogger, START/END/REPORT và log output.
- [AWS Lambda — JSON log format](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-cloudwatchlogs-logformat.html): structured JSON application logs và request ID.
- [AWS Lambda Managed Instances — Java runtime](https://docs.aws.amazon.com/lambda/latest/dg/lambda-managed-instances-java-runtime.html): request context theo request thread, remaining time và concurrency.
