# Ranh giới giữa gọi dịch vụ serverless và triển khai Spring Cloud Function

## 1. Bối cảnh và mục tiêu

Trong module **Spring Cloud Provider Integration**, ứng dụng Spring Boot tích hợp các dịch vụ managed của AWS, Azure và Google Cloud qua SDK, Spring Cloud và connector tương ứng. Một điểm dễ nhầm là khi ứng dụng sử dụng một dịch vụ serverless, điều đó không có nghĩa ứng dụng đang chạy dưới dạng serverless function.

Có hai hướng triển khai khác nhau:

- **Gọi dịch vụ serverless từ Spring Boot:** ứng dụng đang chạy như web service, worker hoặc batch process và gọi API của một dịch vụ do cloud quản lý. Ví dụ: gọi AWS Lambda bằng AWS SDK, gửi message vào SQS, gọi Azure Function qua HTTP, publish Pub/Sub hoặc gọi Cloud Run service.
- **Triển khai business function lên serverless runtime:** đóng gói logic Spring Cloud Function và triển khai lên AWS Lambda, Azure Functions hoặc Google Cloud Functions/Cloud Run functions. Runtime của provider khởi tạo function và gọi nó khi có HTTP request hoặc event.

Hai hướng có thể cùng xuất hiện trong một hệ thống. Một Spring Boot service có thể gọi Lambda để chạy tác vụ riêng; một Lambda khác có thể được trigger bởi SQS và dùng AWS SDK để ghi dữ liệu vào S3. Cần xác định thành phần nào là caller, thành phần nào là function runtime và ai chịu trách nhiệm trigger, retry, identity, timeout và observability.

**Spring Cloud Function** cung cấp programming model dựa trên các functional interface Java là **Function**, **Consumer** và **Supplier**, cùng Function Catalog, type conversion và adapter cho một số serverless runtime. Business logic có thể chạy như Spring Boot application thông thường hoặc được đóng gói cho nền tảng serverless. Adapter giúp nối function model với invocation contract của provider; nó không tự provision cloud resource, tạo trigger, cấp IAM role hay thay thế SDK của dịch vụ managed.

Sau bài học, bạn có thể:

1. Phân biệt gọi serverless API với triển khai ứng dụng thành serverless function.
2. Phân biệt Lambda, Azure Functions, Cloud Run functions và Cloud Run service.
3. Hiểu mô hình Function, Consumer, Supplier, Function Catalog và composition.
4. Chọn Spring Cloud Function adapter phù hợp cho AWS, Azure hoặc Google Cloud.
5. Gọi function/service serverless từ Spring Boot bằng SDK hoặc HTTP client.
6. Cấu hình trigger, event payload, function selection và deployment package.
7. Thiết kế identity, least privilege, secret, network và event delivery.
8. Đánh giá cold start, concurrency, timeout, state, retry và idempotency.
9. Kiểm thử function độc lập, adapter contract và cloud integration.
10. Quyết định khi nào nên dùng function runtime, container serverless hoặc Spring Boot service dài hạn.

> **Phạm vi:** Tài liệu phân biệt hai hướng tích hợp và giới thiệu cách triển khai theo provider. Tên artifact, runtime Java, plugin và deployment command phụ thuộc release train và phiên bản cloud runtime. Luôn kiểm tra ma trận tương thích trước khi chọn version; không sao chép runtime đã hết hỗ trợ từ ví dụ cũ.

## 2. Hai hướng tích hợp serverless

### 2.1. Gọi một dịch vụ serverless từ Spring Boot

Trong mô hình này, Spring Boot vẫn là caller. Nó có thể chạy trên ECS, EKS, Azure Container Apps, AKS, Cloud Run, GKE hoặc VM. Ứng dụng gọi một API được quản lý bởi cloud provider:

- AWS Lambda Invoke API, S3, SQS, SNS, EventBridge, Step Functions.
- Azure Functions HTTP endpoint, Service Bus, Event Grid, Blob Storage.
- Google Cloud Run endpoint, Cloud Run functions endpoint, Pub/Sub, Cloud Tasks, Eventarc.

Ví dụ Spring Boot gửi yêu cầu xử lý ảnh đến Lambda. Spring Boot cần quyền **lambda:InvokeFunction**; Lambda có execution role riêng để đọc ảnh từ S3 và ghi kết quả. Caller và function là hai workload khác nhau, có identity và lifecycle riêng.

### 2.2. Triển khai Spring Cloud Function lên serverless runtime

Trong mô hình này, business logic được đóng gói thành function. Provider runtime chịu trách nhiệm nhận invocation, tạo execution environment và gọi entry point:

- AWS Lambda dùng handler adapter như **FunctionInvoker**.
- Azure Functions dùng Java Worker, trigger annotation và Spring Cloud Function adapter.
- Google Cloud Functions/Cloud Run functions dùng Functions Framework và GCP adapter như **GcfJarLauncher**.

Function có thể được trigger bởi HTTP hoặc event từ queue, stream, object storage, scheduler hay event bus. Runtime quyết định cách truyền payload/context và cách ghi nhận invocation.

### 2.3. So sánh nhanh

| Tiêu chí | Gọi serverless service/API | Deploy Spring Cloud Function |
| --- | --- | --- |
| Vị trí business logic | Trong Spring Boot caller | Trong function runtime |
| Vai trò Spring Boot | Web service/worker gọi API | Ứng dụng chứa function bean |
| Entry point | SDK/HTTP client | Provider handler/adapter |
| Scale | Theo workload của caller | Theo invocation/trigger của function runtime |
| Identity chính | Caller identity và resource policy | Function execution identity; có thể thêm caller identity |
| Timeout | API/client timeout và downstream timeout | Function timeout cùng timeout của trigger/client |
| Retry | Caller/SDK hoặc service source | Provider trigger/runtime và application policy |
| Dữ liệu vào | Request do caller tạo | Event/HTTP payload do platform chuyển vào |
| Ví dụ | LambdaClient.invoke(...) | FunctionInvoker::handleRequest |

### 2.4. Ba câu hỏi để chọn đúng hướng

1. Logic cần chạy có phải là một đơn vị công việc độc lập, stateless hoặc có thể idempotent, được kích hoạt bởi HTTP/event không?
2. Có cần scale-to-zero và scale theo event burst, hay cần process dài hạn, connection pool và throughput ổn định?
3. Caller có cần đồng bộ kết quả ngay, hay có thể gửi event/message để xử lý bất đồng bộ?

Nếu chỉ cần gọi một managed API, dùng SDK/HTTP client. Nếu muốn tách một đơn vị business logic thành function do platform kích hoạt, dùng function adapter. Nếu workload cần chạy liên tục, nhiều endpoint, connection pool lâu dài hoặc xử lý nền dài, cân nhắc deploy Spring Boot container/service.

## 3. Spring Cloud Function programming model

### 3.1. Function, Consumer và Supplier

Spring Cloud Function dùng các functional interface chuẩn của Java:

| Kiểu | Hành vi | Ví dụ |
| --- | --- | --- |
| Function<I, O> | Nhận input và trả output | Chuẩn hóa reservation event |
| Consumer<I> | Nhận input, không trả output | Ghi audit hoặc xử lý event |
| Supplier<O> | Không nhận input, tạo output | Sinh heartbeat hoặc đọc batch |

Ví dụ:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ReservationFunctions {

    @Bean
    Function<ReservationCreated, ReservationAccepted> acceptReservation(
            ReservationService service) {
        return event -> service.accept(event);
    }

    @Bean
    Consumer<ReservationAccepted> auditReservation(
            AuditService auditService) {
        return event -> auditService.record(event);
    }

    @Bean
    Supplier<HealthSnapshot> healthSnapshot(
            HealthService healthService) {
        return healthService::snapshot;
    }
}
~~~

Các service được inject bởi Spring. Function bean giữ business logic và có thể test độc lập. Không lưu mutable request state trong field/static variable vì một function instance có thể được reuse qua nhiều invocation hoặc xử lý concurrency tùy runtime.

### 3.2. Function Catalog và function definition

Function Catalog là registry runtime của các function bean. Property **spring.cloud.function.definition** xác định function hoặc composition được expose cho adapter.

~~~yaml
spring:
  cloud:
    function:
      definition: acceptReservation
~~~

Nếu application có nhiều function, khai báo definition rõ ràng. Không dựa vào thứ tự component scan hoặc function bean đầu tiên được tìm thấy. Có thể truyền property qua environment variable **SPRING_CLOUD_FUNCTION_DEFINITION** tùy cơ chế configuration của Spring Boot.

### 3.3. Composition

Có thể nối các function tương thích input/output:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeReservation|validateReservation|persistReservation
~~~

Output của function trước trở thành input của function sau. Composition phù hợp với các bước biến đổi thuần hoặc workflow nhỏ. Không ghép các function có side effect khó rollback mà không thiết kế rõ transaction, retry và idempotency.

Composition trong Function Catalog là composition trong process. Nó không tự tạo distributed workflow, retry giữa các bước hoặc durable checkpoint. Nếu cần workflow dài hạn với compensation, timeout và state persistence, cân nhắc Step Functions, Azure Durable Functions hoặc Google Workflows.

### 3.4. Type conversion và Message

Spring Cloud Function có thể chuyển đổi payload theo type signature và content type. Function có thể nhận POJO thay vì tự parse JSON; adapter chịu trách nhiệm chuyển đổi payload theo runtime contract.

Khi cần metadata, header hoặc correlation ID, có thể dùng **Message<T>**:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Bean
Function<Message<ReservationCreated>, Message<ReservationAccepted>>
        acceptReservation(ReservationService service) {
    return message -> {
        ReservationAccepted result = service.accept(message.getPayload());

        return MessageBuilder.withPayload(result)
                .setHeader("correlationId",
                        message.getHeaders().get("correlationId"))
                .build();
    };
}
~~~

Không tin mọi header đến từ external event. Xác thực tenant/user context ở ingress boundary; không truyền token bí mật qua header hoặc log. Header của provider có thể có giới hạn kích thước và naming convention riêng.

### 3.5. Reactive function

Spring Cloud Function hỗ trợ kiểu reactive như **Flux** và **Mono** trong các integration tương thích. Reactive không tự biến function thành streaming platform. Cần kiểm tra adapter có hỗ trợ kiểu input/output, backpressure và lifecycle của provider trigger hay không.

Với function runtime giới hạn thời gian invocation, không giữ một reactive stream vô hạn nếu platform không cung cấp execution model phù hợp. Dùng queue/stream service chuyên dụng cho consumer liên tục hoặc workload cần checkpoint dài hạn.

### 3.6. Function có thể chạy như Spring Boot application

Một function bean không bắt buộc phải deploy lên Lambda/Functions. Có thể chạy trong Spring Boot app và expose qua HTTP hoặc messaging adapter phù hợp. Điều này giúp giữ business logic độc lập với target runtime:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import java.util.function.Function;

@SpringBootApplication
public class ReservationFunctionApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ReservationFunctionApplication.class, args);
    }

    @Bean
    Function<String, String> uppercase() {
        return String::toUpperCase;
    }
}
~~~

Cùng business function có thể được gọi từ test, HTTP adapter hoặc serverless adapter. Các adapter vẫn có event/HTTP contract và packaging khác nhau; không giả định một JAR có thể deploy nguyên trạng lên mọi provider mà không cần cấu hình build.

## 4. Gọi dịch vụ serverless từ Spring Boot

### 4.1. Gọi AWS Lambda bằng AWS SDK

Spring Boot caller có thể dùng AWS SDK for Java v2 **LambdaClient** để invoke function. Ứng dụng caller không cần thêm **spring-cloud-function-adapter-aws** chỉ để gọi Lambda.

~~~java
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.SdkBytes;
import software.amazon.awssdk.services.lambda.LambdaClient;
import software.amazon.awssdk.services.lambda.model.InvokeRequest;
import software.amazon.awssdk.services.lambda.model.InvokeResponse;
import software.amazon.awssdk.services.lambda.model.InvocationType;

@Component
public class ImageProcessorClient {

    private final LambdaClient lambdaClient;

    public ImageProcessorClient(LambdaClient lambdaClient) {
        this.lambdaClient = lambdaClient;
    }

    public String process(String functionName, String jsonPayload) {
        InvokeResponse response = lambdaClient.invoke(
                InvokeRequest.builder()
                        .functionName(functionName)
                        .invocationType(InvocationType.REQUEST_RESPONSE)
                        .payload(SdkBytes.fromUtf8String(jsonPayload))
                        .build());

        if (response.functionError() != null) {
            throw new IllegalStateException(
                    "Lambda execution failed: " + response.functionError());
        }

        return response.payload().asUtf8String();
    }
}
~~~

Cấu hình **LambdaClient** bằng Region và credential provider chain của AWS SDK. Không nhúng access key vào code. Caller role cần **lambda:InvokeFunction** trên ARN function cụ thể. Function execution role là identity khác, dùng để truy cập S3, database, queue hoặc logging.

Kiểm tra **functionError** và payload response; HTTP/API status của Invoke không thay thế việc kiểm tra lỗi thực thi trong function. Với **InvocationType.EVENT**, caller nhận xác nhận tiếp nhận bất đồng bộ, không nhận kết quả business cuối cùng.

### 4.2. Gọi Azure Function qua HTTP

Một Azure Function có HTTP trigger có thể được gọi như một HTTP endpoint. Spring Boot dùng **RestClient** hoặc **WebClient**:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class AzureFunctionClient {

    private final RestClient restClient;

    public AzureFunctionClient(RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("https://reservation-func.azurewebsites.net")
                .build();
    }

    public String calculate(String payload, String functionKey) {
        return restClient.post()
                .uri("/api/calculate")
                .header("x-functions-key", functionKey)
                .body(payload)
                .retrieve()
                .body(String.class);
    }
}
~~~

Ví dụ dùng function key để minh họa. Trong production, lấy key từ Key Vault/secret injection, không commit hoặc log. Nếu kiến trúc hỗ trợ Entra ID authentication, ưu tiên identity-based authentication và kiểm tra audience/authorization policy. Không để HTTP trigger ở chế độ anonymous nếu endpoint không thực sự public.

### 4.3. Gọi Cloud Run service hoặc function trên Google Cloud

Cloud Run service và Cloud Run functions có HTTP endpoint. Với endpoint yêu cầu authentication, caller cần lấy Google-signed OIDC ID token có audience phù hợp với URL service và gửi trong Authorization header. Workload identity/service account của caller cần được cấp Cloud Run Invoker (**roles/run.invoker**) trên service đích.

Luồng tổng quát:

1. Spring Boot chạy với service account/workload identity.
2. Google Auth Library lấy ID token cho audience là URL service.
3. HTTP client gửi Authorization: Bearer token.
4. Cloud Run xác thực token và IAM invoker role trước khi chuyển request tới application.

Không dùng OAuth access token của API khác thay cho ID token invocation nếu tài liệu yêu cầu ID token. Không đưa token vào query string hoặc log.

### 4.4. Gọi managed serverless data/messaging service

Nhiều dịch vụ serverless không phải function runtime:

- S3, Blob Storage, Cloud Storage: gọi SDK/API để đọc/ghi object.
- SQS, Service Bus, Pub/Sub: publish/consume message.
- EventBridge, Event Grid, Eventarc: phát hoặc route event.
- Step Functions, Durable Functions, Workflows: điều phối workflow.

Spring Boot có thể dùng AWSpring, Spring Cloud Azure, Spring Cloud GCP, Spring Integration hoặc SDK tương ứng. Không cần Spring Cloud Function adapter nếu chỉ gọi API của dịch vụ đó.

### 4.5. Đồng bộ hay bất đồng bộ?

| Kiểu gọi | Caller nhận gì? | Phù hợp |
| --- | --- | --- |
| HTTP/synchronous invoke | Response hoặc lỗi trong request | API cần kết quả ngay và thời gian xử lý có giới hạn |
| Asynchronous invoke | Xác nhận đã nhận yêu cầu | Tác vụ có thể xử lý sau |
| Queue/event publish | Broker xác nhận publish/accept | Tách producer-consumer, buffer và retry |
| Scheduled trigger | Runtime gọi theo lịch | Batch, cleanup, polling định kỳ |
| Storage/event trigger | Runtime gọi khi resource phát event | File processing, event-driven integration |

Không dùng synchronous function invoke cho workflow kéo dài vượt timeout của caller/API gateway. Với tác vụ bất đồng bộ, trả về operation ID/correlation ID và cung cấp trạng thái qua database hoặc event callback.
## 5. Triển khai Spring Cloud Function lên AWS Lambda

### 5.1. AWS adapter

AWS adapter chuyển một Spring Cloud Function application thành artifact có thể chạy trên AWS Lambda. Dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-aws</artifactId>
</dependency>
~~~

Quản lý version qua Spring Cloud BOM tương thích với Spring Boot. Không tự chọn version adapter độc lập với release train.

### 5.2. Function handler

Spring Cloud Function cung cấp handler tổng quát:

**org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest**

Khi cấu hình handler này cho Lambda, adapter nhận payload/context của AWS, khởi tạo Spring function context và dispatch tới function được chọn. Function business không cần implement trực tiếp AWS RequestHandler nếu không cần xử lý sâu AWS event type.

Nếu có nhiều function bean, cấu hình **spring.cloud.function.definition** hoặc environment variable tương ứng để chọn function. Không dựa vào default selection trong production vì application có thể có nhiều Function/Consumer/Supplier.

### 5.3. Trigger và event payload

Lambda có thể được invoke bởi API Gateway, Function URL, S3, SQS, SNS, EventBridge, Kinesis hoặc service khác. Event payload phụ thuộc trigger:

| Trigger | Input thường gặp | Lưu ý |
| --- | --- | --- |
| API Gateway/Function URL | HTTP event/request body | Mapping status/header và auth |
| S3 | S3 event record | Function có thể nhận event object hoặc raw stream |
| SQS | Batch message records | Có thể cần partial batch response |
| Kinesis | Batch stream records | Ordering/checkpoint và retry theo shard |
| EventBridge | Event envelope | Kiểm tra detail/type/version |
| SNS | Notification envelope | Xem message attributes và subscription |

AWS adapter hỗ trợ type conversion cho nhiều payload, nhưng khi cần metadata riêng của AWS, có thể nhận event type tương ứng. Không parse mọi event thành POJO nghiệp vụ mà bỏ qua envelope, request ID, record ID hoặc retry context.

### 5.4. Synchronous và asynchronous invoke

AWS Lambda Invoke API hỗ trợ invocation đồng bộ và bất đồng bộ. Đồng bộ trả response từ function; bất đồng bộ chỉ xác nhận request đã được nhận vào queue xử lý. Retry và duplicate behavior phụ thuộc invocation type, event source và cấu hình. Caller phải phân biệt:
- API call thành công.
- Function thực thi thành công.
- Side effect nghiệp vụ đã commit.
- Kết quả đã được lưu hoặc gửi callback.

Không coi status tiếp nhận async là kết quả business. Dùng correlation ID, operation record, destination/DLQ và idempotency để theo dõi tác vụ.

### 5.5. Execution role và quyền invoke

Có ít nhất hai lớp quyền:

1. **Caller permission:** Spring Boot caller có quyền invoke Lambda function cụ thể, ví dụ action **lambda:InvokeFunction** trên ARN cần thiết.
2. **Function execution role:** Lambda assume role khi chạy để đọc S3, ghi CloudWatch Logs, đọc secret, publish message hoặc truy cập database.

Nếu SQS là event source, Lambda event source mapping cần quyền poll/delete message theo cấu hình. Nếu S3/EventBridge là push source, cần resource-based permission cho service được phép invoke function. Không gộp tất cả permission vào một role admin.

### 5.6. API Gateway, Function URL và Lambda web container

Spring Cloud Function phù hợp với function nhỏ, event/message-driven hoặc API đơn nhiệm. Nếu cần migrate một Spring Boot Web application lớn với nhiều REST controller, có thể cân nhắc AWS Serverless Java Container để chạy Spring Boot Web trên Lambda. Đây là cách tích hợp khác với Spring Cloud Function adapter.

Không chọn Function adapter chỉ vì ứng dụng có một endpoint HTTP. Xét số endpoint, framework startup, request routing, memory, cold start và compatibility của dependency.

## 6. Triển khai Spring Cloud Function lên Azure Functions

### 6.1. Azure adapter

Azure adapter tích hợp Spring và Spring Cloud Function với Azure Java Worker. Dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-azure</artifactId>
</dependency>
~~~

Azure Functions Java model dùng annotation để khai báo function handler và trigger. Azure Maven/Gradle plugin xử lý annotation và tạo metadata/package cần thiết. Adapter cho phép handler inject Spring bean hoặc dùng Function Catalog.

Kiểm tra Spring Cloud Function version, Azure Functions Java Worker version và plugin compatibility. Một số tài liệu cũ có ví dụ FunctionInvoker kế thừa; với release hiện hành, ưu tiên hướng dẫn adapter/dependency injection và sample tương ứng, tránh dùng integration đã deprecated.

### 6.2. Function handler và Function Catalog

Ví dụ khái niệm handler HTTP:

~~~java
@Component
public class ReservationHttpFunction {

    private final FunctionCatalog functionCatalog;

    public ReservationHttpFunction(FunctionCatalog functionCatalog) {
        this.functionCatalog = functionCatalog;
    }

    @FunctionName("acceptReservation")
    public String accept(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION)
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        Function<String, String> function =
                functionCatalog.lookup("acceptReservation");

        return function.apply(request.getBody().orElse(""));
    }
}
~~~

Đây là ví dụ minh họa handler/annotation; import, trigger binding và generic signature cần khớp Azure Java library cùng adapter release. Handler gọi Function Catalog để sử dụng function canonical của Spring Cloud Function. Một Spring bean thông thường được inject vào handler không tự động trở thành function trong Function Catalog.

### 6.3. Trigger của Azure Functions

Azure Functions hỗ trợ nhiều trigger/binding:

- HTTP Trigger cho request/response.
- Timer Trigger cho lịch.
- Blob Storage Trigger cho file event.
- Service Bus Trigger cho queue/topic subscription.
- Event Hubs Trigger cho stream.
- Event Grid Trigger cho event routing.

Trigger quyết định cách payload được truyền, checkpoint/lock/ack và retry. Ví dụ Service Bus có message lock và dead-letter; Event Hubs dùng partition/checkpoint. Không suy ra semantics từ Java Function signature.

### 6.4. Azure Web Adapter

Nếu ứng dụng đã dùng Spring Web và cần deploy như HTTP-triggered Azure Function, có adapter chuyên biệt **spring-cloud-function-adapter-azure-web**. Adapter này giúp dùng Spring Web programming model và giảm phần annotation Azure trong handler.

Đây là lựa chọn khác với adapter function tổng quát. Cần xác định ứng dụng là HTTP web app hay function/event handler. Không trộn Azure Web Adapter với generic handler nếu chưa kiểm tra routing và packaging.

### 6.5. Identity và secret

Function App có thể dùng Managed Identity để truy cập Key Vault, Storage, Service Bus hoặc Event Hubs. Cấp role data-plane theo resource và operation. Nếu dùng connection string/SAS key, coi đó là secret và lấy từ Key Vault/Application Settings theo policy.

HTTP trigger có auth level như anonymous/function/admin; production nên chọn cơ chế xác thực phù hợp, ưu tiên Entra ID hoặc gateway auth khi có thể. Function key là secret dùng để bảo vệ endpoint, không thay thế authorization theo user/tenant trong business API.

### 6.6. Deployment và configuration

Azure Functions package cần function metadata được plugin tạo ra. Các thiết lập như function app name, runtime, region, trigger, app settings, scale plan và identity thường được quản lý qua IaC hoặc pipeline.

Không commit publish profile, host key hoặc function key. Tách application setting không nhạy cảm khỏi Key Vault secret reference. Với deployment slot, xác định setting nào sticky theo slot và cách promote cấu hình cùng code.

## 7. Triển khai Spring Cloud Function lên Google Cloud

### 7.1. GCP adapter và Functions Framework

Spring Cloud Function có adapter cho Google Cloud Functions. Dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-gcp</artifactId>
</dependency>
~~~

Adapter cần được đưa vào quá trình đóng gói theo hướng dẫn Spring Cloud Function. Với Maven, plugin Spring Boot có thể cần adapter như plugin dependency để tạo JAR đúng layout; Google Functions Framework Maven plugin dùng để chạy function cục bộ.

Entry point adapter thường là:

**org.springframework.cloud.function.adapter.gcp.GcfJarLauncher**

Đây là launcher nối runtime Google Functions Framework với Spring Cloud Function application. Không thay entry point này bằng tên bean function nếu đang dùng GCP adapter.

### 7.2. HTTP function và background function

GCP adapter hỗ trợ HTTP function và background/event-driven function:

- HTTP function nhận HTTP request và trả HTTP response.
- Background function nhận event từ Pub/Sub, Cloud Storage hoặc event source khác.
- Eventarc có thể route event tới Cloud Run functions hoặc Cloud Run service theo trigger configuration.

Ví dụ function HTTP:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import java.util.function.Function;

@SpringBootApplication
public class CloudFunctionApplication {

    public static void main(String[] args) {
        SpringApplication.run(CloudFunctionApplication.class, args);
    }

    @Bean
    Function<String, String> uppercase() {
        return String::toUpperCase;
    }
}
~~~

Ví dụ consumer nhận event Pub/Sub theo payload model mà adapter yêu cầu:

~~~java
@Bean
Consumer<PubSubMessage> handleReservationEvent(
        ReservationService reservationService) {
    return event -> reservationService.process(event);
}
~~~

Tên event class và fields cần khớp payload/event format thực tế của trigger. Khi dùng Eventarc CloudEvents, xác minh adapter đang nhận CloudEvent envelope hay payload đã được giải bọc. Không giả định mọi trigger gửi cùng JSON schema.

### 7.3. Cloud Run service khác Cloud Run functions

**Cloud Run service** chạy container HTTP do ứng dụng đóng gói; có thể deploy Spring Boot Web app hoặc Spring Boot application có HTTP server. Không bắt buộc dùng GCP function adapter.

**Cloud Run functions** (tên hiện hành cho trải nghiệm functions dựa trên Cloud Run; tài liệu Spring Cloud Function có thể vẫn gọi Google Cloud Functions) dùng Functions Framework/entry point và trigger function. Spring Cloud Function GCP adapter giúp đóng gói function model theo runtime đó.

Chọn Cloud Run service khi cần kiểm soát container, nhiều route, web framework đầy đủ hoặc runtime lâu dài. Chọn Cloud Run functions khi đơn vị xử lý là function gắn với HTTP/event trigger và contract Functions Framework phù hợp.

### 7.4. Workload identity và invocation

Function hoặc Cloud Run service có service identity riêng. Dùng service account gắn với workload và IAM role tối thiểu để truy cập Pub/Sub, Cloud Storage, Secret Manager, Cloud SQL hoặc API khác.

Để gọi một Cloud Run service/function private từ Spring Boot, caller cần:
- Identity riêng có quyền **roles/run.invoker** trên service đích.
- ID token do Google ký với audience là URL service.
- HTTP request có Authorization Bearer token.

Với Pub/Sub/Eventarc trigger, service account của trigger cần quyền invoke target. Quyền publisher trên topic, quyền tạo trigger và quyền invoke function là các quyền khác nhau.

### 7.5. Deployment và runtime compatibility

Spring Cloud Function GCP adapter sử dụng Functions Framework và launcher riêng. Build có thể cần điều chỉnh plugin dependency và output JAR directory. Runtime Java mà provider hỗ trợ thay đổi theo thế hệ function/API; kiểm tra runtime hiện được hỗ trợ và deployment flow tương ứng trước khi dùng ví dụ CLI từ tài liệu cũ.

Không coi lệnh triển khai Cloud Functions đời cũ là mặc định cho mọi môi trường. Tùy target, dùng Cloud Run functions deployment flow hoặc deploy container lên Cloud Run service. Cả hai đều có thể dùng cùng business function nếu đóng gói adapter/entry point đúng.

## 8. Đối chiếu adapter và trigger theo provider

| Provider | Function runtime | Spring Cloud Function adapter | Trigger/event thường gặp |
| --- | --- | --- | --- |
| AWS | AWS Lambda | spring-cloud-function-adapter-aws | API Gateway, Function URL, S3, SQS, SNS, EventBridge, Kinesis |
| Azure | Azure Functions | spring-cloud-function-adapter-azure; azure-web adapter cho Spring Web | HTTP, Timer, Blob, Service Bus, Event Hubs, Event Grid |
| Google Cloud | Cloud Run functions/Google Cloud Functions | spring-cloud-function-adapter-gcp | HTTP, Pub/Sub, Cloud Storage, Eventarc |

Adapter giúp chuẩn hóa business function model; nó không làm trigger contract đồng nhất. Mỗi provider vẫn có event envelope, retry, batch, timeout, authentication, scaling và deployment package riêng.

## 9. Event delivery, retry và idempotency

### 9.1. Function invocation không tự bảo đảm exactly-once

Một event có thể được giao lại khi function timeout, process crash, acknowledgment thất bại hoặc provider không nhận được kết quả xác nhận. Function cần xử lý duplicate an toàn bằng event ID, idempotency key hoặc inbox/deduplication store.

Không tuyên bố exactly-once chỉ vì function runtime có retry hoặc event source có checkpoint. Semantics thực tế phụ thuộc trigger, adapter, broker và side effect của ứng dụng.

### 9.2. AWS Lambda

Với SQS event source mapping, Lambda poll queue và gửi batch tới function. Nếu batch lỗi, hành vi retry phụ thuộc batch response configuration. Có thể bật partial batch response để chỉ báo những message thất bại; nếu không, một record lỗi có thể khiến cả batch được giao lại. Visibility timeout phải đủ cho function timeout và thời gian retry.

Với invocation bất đồng bộ, Lambda có retry/destination/DLQ policy riêng. Với Kinesis, checkpoint và retry theo shard có thể làm record phía sau bị chặn bởi record lỗi. Thiết kế idempotency theo message/event ID và tránh side effect không thể lặp.

### 9.3. Azure Functions

Retry và settlement phụ thuộc trigger extension:
- Service Bus có lock/complete/abandon/dead-letter; message lock expiry có thể dẫn tới redelivery.
- Event Hubs dùng partition checkpoint; checkpoint sau xử lý có thể tạo duplicate nếu process dừng trước khi ghi checkpoint.
- Queue/Blob/Timer trigger có retry và poison-message behavior riêng theo extension/plan.

Không giả định mọi trigger dùng cùng retry count hoặc cùng cách ack. Kiểm tra tài liệu extension/version, host.json và dead-letter policy. Nếu function gọi database rồi timeout trước khi runtime ghi nhận thành công, database side effect có thể đã commit dù event được giao lại.

### 9.4. Google Cloud Functions/Cloud Run functions

Với Pub/Sub/Eventarc, delivery và retry phụ thuộc trigger configuration, subscription và event delivery mode. HTTP function trả response thành công là một tín hiệu cho hệ thống giao event; lỗi/timeout có thể dẫn tới retry nếu retry được bật. Cloud Run service nhận Pub/Sub push cũng cần xử lý duplicate và ack/response đúng contract.

Eventarc trigger có service account riêng để invoke target. Cấu hình retry, dead-letter và retention ở event source/trigger phù hợp; không dựa vào function code để tự tạo semantics broker.

### 9.5. Thiết kế idempotent handler

Ví dụ handler ghi nhận event ID trước khi thực hiện side effect:

~~~java
@Component
public class ReservationEventHandler {

    private final InboxService inbox;
    private final ReservationService reservations;

    public ReservationEventHandler(
            InboxService inbox,
            ReservationService reservations) {
        this.inbox = inbox;
        this.reservations = reservations;
    }

    public void handle(ReservationCreated event) {
        if (!inbox.tryRegister("reservation-worker", event.eventId())) {
            return;
        }

        reservations.create(event.reservationId());
    }
}
~~~

Phương thức tryRegister cần dùng unique constraint và ghi inbox trong cùng transaction với side effect khi cùng database. Nếu side effect gọi API ngoài transaction, truyền idempotency key tới API đích hoặc ghi command vào outbox. Không chỉ kiểm tra event ID rồi mới insert bằng hai query không atomic.

## 10. Identity, secret và network

### 10.1. Tách identity caller và identity function

| Vai trò | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Spring Boot caller | ECS task role, EKS Pod Identity/IRSA, EC2 role | Managed Identity/Workload Identity | Cloud Run service account, GKE Workload Identity |
| Function runtime | Lambda execution role | Function App managed identity | Function/Cloud Run service identity |
| Event trigger | Service/resource permission và event source mapping | Trigger extension identity/connection | Eventarc/Pub/Sub trigger service account |
| Secret access | Secrets Manager/KMS IAM | Key Vault RBAC | Secret Manager IAM |

Caller có quyền invoke function không đồng nghĩa function có quyền truy cập resource. Tương tự, trigger service account có quyền invoke function không có nghĩa business function được phép đọc mọi secret trong project.

### 10.2. Least privilege

Cấp quyền theo function và resource:
- Caller chỉ invoke function ARN/endpoint cần thiết.
- Lambda execution role chỉ đọc bucket/prefix, queue, secret hoặc database cần thiết.
- Azure Function identity chỉ nhận data-plane role trên resource cần dùng.
- Google service account chỉ có role tối thiểu trên topic, bucket, secret hoặc Cloud Run target.

Không cấp quyền admin/subscription owner/project editor cho function chỉ để tránh lỗi permission. Dùng resource policy, IAM/RBAC scope, network boundary và audit riêng.

### 10.3. Secret và connection material

Không commit function key, AWS access key, SAS connection string, service account key, OAuth client secret hoặc database password. Dùng:
- AWS Secrets Manager/SSM SecureString.
- Azure Key Vault và managed identity.
- Google Secret Manager và workload identity.

Nếu function chỉ gọi API bằng workload identity, không cần tạo static credential chỉ để nhét vào environment. Environment variable phù hợp với non-secret configuration; secret phải được inject/resolve theo policy của runtime. Không log full environment, event payload nhạy cảm hoặc authorization header.

### 10.4. Network và private access

Function runtime có thể cần VPC/VNet/VPC connector để truy cập database/private endpoint. Network attachment làm tăng cấu hình vận hành và có thể ảnh hưởng cold start/throughput. Xác định outbound path, DNS, NAT, firewall, private endpoint và TLS.

Không mặc định function serverless có thể truy cập private database chỉ vì cùng cloud account/project. Kiểm tra subnet, route, security group/NSG, connector và database allow-list. Với synchronous HTTP invocation, caller cũng cần route và DNS tới endpoint function.

## 11. Runtime behavior: cold start, concurrency và state

### 11.1. Cold start

Cold start là thời gian tạo execution environment và khởi tạo application trước khi xử lý invocation. Spring Boot context, classpath lớn, bean initialization, secret retrieval và network connection có thể làm tăng startup time.

Có thể giảm bằng cách:
- Giữ dependency/classpath cần thiết, loại adapter không dùng.
- Tránh gọi nhiều remote service trong bean constructor/startup hook.
- Lazy initialize client hoặc resource không cần ngay khi invocation đầu tiên.
- Dùng SDK client reuse an toàn giữa các invocation trong cùng environment.
- Chọn memory/CPU và provisioned/minimum instance phù hợp.
- Đo startup và first-request latency riêng với warm invocation.

Không tối ưu bằng cách bỏ validation hoặc TLS. Tính đúng đắn và security vẫn phải giữ.

### 11.2. Concurrency và thread safety

Provider có thể tạo nhiều execution environment hoặc cho phép nhiều request đồng thời trên một instance/container. Mức concurrency khác nhau theo runtime, plan và cấu hình. Không giả định mỗi function instance luôn xử lý đúng một invocation tại một thời điểm.

Spring singleton bean cần thread-safe nếu runtime có thể gọi đồng thời. Không lưu request data vào field mutable. Connection pool, executor và SDK client cần giới hạn resource để không vượt database connection limit hoặc downstream quota.

### 11.3. Stateless và external state

Function nên stateless giữa invocation. Không lưu session, lock hoặc durable progress chỉ trong heap/static field. Runtime có thể recycle instance bất kỳ lúc nào; scale-out tạo instance khác.

Lưu state vào database, cache, object storage, queue hoặc workflow service. Nếu cần orchestration dài hạn, compensation và durable timer, dùng workflow engine thay vì giữ function invocation mở lâu.

### 11.4. Timeout và resource limit

Mỗi provider/plan có giới hạn thời gian, memory, payload, temporary storage và concurrency riêng. Tổng thời gian xử lý phải phù hợp với:
- Function timeout.
- HTTP gateway/client timeout.
- Queue visibility/lock/ack deadline.
- Event source retry/checkpoint.
- Database/SDK request timeout.

Không tăng timeout một cách độc lập. Ví dụ function timeout dài hơn queue visibility timeout có thể khiến message được giao lại trong khi invocation cũ vẫn đang chạy.

### 11.5. Scale-to-zero và minimum instances

Scale-to-zero tiết kiệm chi phí khi idle nhưng có thể làm tăng first-request latency. Minimum/provisioned instances giảm cold start nhưng tạo chi phí cố định. Chọn theo latency SLO, burst pattern, event backlog và cost budget; dùng load test với cold/warm scenario.

## 12. Kiểm thử Spring Cloud Function và adapter

### 12.1. Kiểm thử function bean trong Spring context

Business function có thể được kiểm tra trong Spring test context với dependency được mock hoặc thay bằng test bean:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class AcceptReservationFunctionTest {

    @Autowired
    @Qualifier("acceptReservation")
    Function<ReservationCreated, ReservationAccepted> acceptReservation;

    @Test
    void acceptsReservation() {
        ReservationCreated input =
                new ReservationCreated("evt-1", "res-1001");

        ReservationAccepted result = acceptReservation.apply(input);

        assertThat(result.reservationId()).isEqualTo("res-1001");
    }
}
~~~

Test tập trung vào validation, transformation và business rules. Không cần AWS/Azure/GCP credentials để kiểm tra function bean nếu test không gọi managed service thật.

### 12.2. Test Function Catalog

Có thể dùng Spring Boot test context để lookup function theo tên và xác minh composition/type conversion:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest
class FunctionCatalogTest {

    @Autowired
    FunctionCatalog functionCatalog;

    @Test
    void looksUpAcceptReservation() {
        Function function =
                functionCatalog.lookup("acceptReservation");

        assertThat(function).isNotNull();
    }
}
~~~

Test Catalog kiểm tra Spring wiring và function selection; không chứng minh provider adapter đã đóng gói đúng hoặc trigger cloud đã gọi function.

### 12.3. Local runtime test

| Provider | Công cụ/local mode cần xem xét | Điều cần kiểm tra |
| --- | --- | --- |
| AWS Lambda | AWS SAM CLI hoặc Lambda test event | Handler, event payload, environment, timeout |
| Azure Functions | Azure Functions Core Tools | Java Worker, trigger binding, host settings |
| Google Cloud | Google Functions Framework for Java | GCF adapter, HTTP/background event |
| Spring Boot standalone | Spring Boot test/HTTP adapter | Function behavior và dependency injection |

Local emulator không mô phỏng đầy đủ IAM, network, quota, trigger delivery, retry, cold start hoặc managed secret. Cần một bộ integration test trên staging cloud.

Testcontainers có thể cung cấp database/broker phụ trợ để kiểm tra side effect của function trong CI; nó không mô phỏng Lambda/Azure Functions/Cloud Run runtime, IAM hay trigger delivery của provider.

Testcontainers có thể cung cấp database/broker phụ trợ để kiểm tra side effect của function trong CI; nó không mô phỏng Lambda/Azure Functions/Cloud Run runtime, IAM hay trigger delivery của provider.

Testcontainers có thể cung cấp database/broker phụ trợ để kiểm tra side effect của function trong CI; nó không mô phỏng Lambda/Azure Functions/Cloud Run runtime, IAM hay trigger delivery của provider.

### 12.4. Cloud contract test

Staging contract test cần xác minh:
1. Artifact/handler/entry point đúng runtime.
2. Trigger tạo đúng event envelope và content type.
3. Function selection chọn đúng bean.
4. Caller/trigger identity có quyền invoke.
5. Function execution identity có quyền downstream.
6. Timeout, retry, batch và DLQ theo policy.
7. Duplicate event không tạo side effect lặp.
8. Logs/traces có invocation ID và correlation ID.
9. Secret không xuất hiện trong logs/build artifacts.
10. Deployment rollback và version routing hoạt động.

### 12.5. Test lỗi và retry

Mô phỏng:
- Function throw exception trước khi commit.
- Function commit DB rồi timeout trước khi trả response.
- Event được gửi lại.
- Downstream API throttling.
- Secret provider unavailable.
- Trigger identity thiếu invoke permission.
- Function execution role thiếu quyền resource.
- Batch có một record poison.

Kết quả mong đợi phải được định nghĩa trước: retry, DLQ, partial batch response, alert hay fail fast. Không chỉ assert status 200.

## 13. Observability và vận hành

### 13.1. Metric quan trọng

| Metric | Ý nghĩa |
| --- | --- |
| Invocation count | Lưu lượng và trigger hoạt động |
| Duration/p95/p99 | Latency function |
| Cold start/init duration | Chi phí khởi tạo |
| Error/timeout/throttle | Function hoặc downstream không đáp ứng |
| Concurrent executions/instances | Mức scale và capacity |
| Queue age/backlog | Consumer không theo kịp event |
| Retry/DLQ count | Poison event hoặc dependency failure |
| Downstream latency/error | SDK/service dependency |
| Memory/CPU utilization | Resource sizing |
| Cost per invocation | Hiệu quả chi phí |

### 13.2. Log và trace

Log nên có function name, provider invocation ID, event ID, correlation ID, trigger type, duration và error category. Propagate trace context nếu trigger hỗ trợ. Không log secret, token, function key, full payload có PII hoặc connection string.

### 13.3. Runbook theo triệu chứng

**Function timeout:** kiểm tra cold start, downstream latency, pool wait, payload size và timeout chain. Không chỉ tăng function timeout.

**Invocation thành công nhưng business side effect thiếu:** kiểm tra function error payload, transaction commit, asynchronous invoke và retry/DLQ.

**Message bị lặp:** kiểm tra ack/visibility/lock/checkpoint và inbox/idempotency.

**Permission denied:** xác định caller identity, trigger identity hay function execution identity; kiểm tra đúng action/resource scope.

**Cold start tăng:** kiểm tra dependency, initialization, secret/network calls và instance policy.

**Backlog tăng:** kiểm tra concurrency, batch size, downstream capacity, throttling và retry loop.

### 13.4. Deployment và rollback

Quản lý function package, runtime config, trigger và IAM policy bằng IaC/pipeline. Dùng alias/version hoặc deployment slot/ring theo provider để rollout có kiểm soát. Theo dõi error/latency sau deploy và rollback code/config cùng trigger khi cần.

Không xóa version cũ trước khi xác minh invocation đang chạy, event backlog và retry/DLQ đã xử lý. Với schema event, giữ backward compatibility trong thời gian producer/consumer rollout.

## 14. Chọn serverless function hay container service?

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Event nhỏ, độc lập, scale theo burst | Function runtime | Trigger tích hợp và scale theo invocation |
| HTTP endpoint đơn giản, ít state | Function HTTP hoặc Cloud Run service nhỏ | Vận hành gọn; chọn theo runtime/latency |
| Spring Boot Web nhiều controller | Container service hoặc adapter web chuyên dụng | Giữ routing/filter/security model hiện có |
| Consumer chạy liên tục, throughput ổn định | Container worker/managed stream consumer | Kiểm soát concurrency/checkpoint lâu dài |
| Workflow nhiều bước, compensation, timer | Workflow engine | Durable orchestration và retry theo step |
| Batch dài, resource nặng | Container job/batch service | Giới hạn runtime và resource phù hợp |
| Gọi S3/SQS/Pub/Sub từ ứng dụng hiện có | SDK/connector trong Spring Boot | Không cần chuyển ứng dụng thành function |

Serverless không mặc nhiên rẻ hơn hoặc đơn giản hơn. Tính cả request volume, execution duration, minimum instances, network/NAT, logging, retry, cold start và chi phí vận hành. Với Spring Boot context lớn, chi phí startup có thể làm function không phù hợp cho latency SLO rất thấp nếu không dùng biện pháp tối ưu tương ứng.

## 15. Checklist trước production

1. **Architecture:** xác định caller, function runtime, trigger và managed services riêng biệt.
2. **Function model:** Function/Consumer/Supplier và function definition rõ ràng.
3. **Adapter:** đúng AWS/Azure/GCP adapter, handler/launcher và package layout.
4. **Compatibility:** Spring Boot, Spring Cloud BOM, adapter, Java runtime và plugin tương thích.
5. **Trigger:** event schema, batch, HTTP auth, retry, ack/checkpoint và DLQ được kiểm tra.
6. **Identity:** caller, trigger và function execution identity được tách riêng.
7. **Least privilege:** chỉ invoke function và truy cập resource cần thiết.
8. **Secrets:** function key, SAS, token và database credential không ở source/log.
9. **Network:** VPC/VNet/VPC connector, DNS, private endpoint và TLS đã được kiểm tra.
10. **State:** function không phụ thuộc in-memory state giữa invocation.
11. **Idempotency:** duplicate event không lặp side effect.
12. **Timeout/capacity:** timeout chain, concurrency, memory và downstream pool phù hợp.
13. **Testing:** unit, Function Catalog, local runtime và cloud contract test.
14. **Observability:** invocation ID, trace, cold start, timeout, retry, DLQ và cost có metric.
15. **Rollback:** có version/alias/slot, schema compatibility và runbook.

## 16. Bài tập tự luyện

1. Viết ba bean Function, Consumer và Supplier cho Reservation service; test từng bean độc lập.
2. Tạo Function Catalog lookup và composition gồm normalize, validate và persist.
3. Viết Spring Boot client gọi AWS Lambda đồng bộ; xử lý function error và timeout.
4. Viết client gọi Azure HTTP Function; lấy function key từ secret source và không log key.
5. Gọi Cloud Run service private bằng ID token; xác minh roles/run.invoker và audience.
6. Đóng gói function Spring Cloud Function cho AWS Lambda bằng AWS adapter và FunctionInvoker.
7. Tạo Azure Function HTTP trigger dùng Function Catalog; kiểm tra adapter/plugin và authorization.
8. Đóng gói GCP function bằng GCP adapter/Functions Framework; chạy local trước khi deploy.
9. So sánh trigger SQS, Service Bus và Pub/Sub về batch, ack, retry và DLQ.
10. Mô phỏng duplicate event sau DB commit; dùng inbox/idempotency để tránh side effect lặp.
11. Đo cold start và warm latency; thử giảm dependency hoặc thay đổi memory/instance policy.
12. So sánh chi phí và vận hành giữa Lambda, Azure Functions, Cloud Run functions và Spring Boot container service.
13. Thiết kế identity matrix gồm caller, trigger và function execution role cho một workflow xử lý file.
14. Viết runbook cho timeout, AccessDenied, DLQ tăng và downstream throttling.

**Tiêu chí hoàn thành:** người học phân biệt được gọi serverless API với deploy function; viết và test được Spring Cloud Function; chọn đúng adapter/trigger cho ít nhất một provider; cấu hình identity riêng cho caller và function; giải thích retry, idempotency, timeout, cold start và có contract test trên staging.

## Tài liệu tham khảo

- [Spring Cloud Function Reference](https://docs.spring.io/spring-cloud-function/reference/): programming model, Function Catalog, composition và serverless adapters.
- [Spring Cloud Function — AWS Lambda adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): FunctionInvoker, handler, event payload và deployment.
- [Spring Cloud Function — Azure Functions adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): Java Worker, trigger handler, Function Catalog và Azure Web Adapter.
- [Spring Cloud Function — Google Cloud Functions adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/gcp-intro.html): GCP adapter, GcfJarLauncher, HTTP và background functions.
- [AWS Lambda Invoke API](https://docs.aws.amazon.com/lambda/latest/api/API_Invoke.html): synchronous/asynchronous invocation và response.
- [AWS Lambda invocation methods](https://docs.aws.amazon.com/lambda/latest/dg/lambda-invocation.html): trigger, event source mapping và retry.
- [AWS Lambda execution role](https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html): quyền của function runtime.
- [AWS Lambda with SQS](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html): event source mapping, batch, visibility timeout và execution role.
- [Azure Functions HTTP trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-http-webhook-trigger): HTTP trigger và authorization level.
- [Azure Functions triggers and bindings](https://learn.microsoft.com/en-us/azure/azure-functions/functions-triggers-bindings): trigger, binding và extension model.
- [Google Cloud Run service-to-service authentication](https://docs.cloud.google.com/run/docs/authenticating/service-to-service): ID token và Cloud Run Invoker.
- [Cloud Run functions triggers](https://docs.cloud.google.com/run/docs/function-triggers): HTTP và event trigger.
- [Local functions development on Cloud Run](https://docs.cloud.google.com/run/docs/local-dev-functions): Functions Framework và local testing.
- [Pub/Sub triggers for Cloud Run](https://docs.cloud.google.com/run/docs/triggering/pubsub-triggers): Pub/Sub direct trigger và Eventarc.
