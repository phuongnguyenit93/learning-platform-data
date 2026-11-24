# HTTP trigger, các loại trigger khác và binding đầu vào đầu ra

## 1. Mục tiêu và bối cảnh

**Spring Cloud Function (SCF)** khuyến khích viết logic nghiệp vụ bằng `Supplier<T>`, `Function<T,R>` và `Consumer<T>`. Những hàm này có thể được đăng ký trong `FunctionCatalog`, ghép bằng *composition* và tái sử dụng khi ứng dụng được gọi qua HTTP, sự kiện hoặc môi trường serverless. Một function như `Function<String,String>` chuẩn hóa mã đơn không cần biết dữ liệu đến từ HTTP request, Azure Storage Queue hay Event Hubs.

**Azure Functions** đảm nhiệm phần kích hoạt và vận chuyển: nhận yêu cầu HTTP, đọc sự kiện từ dịch vụ ngoài, chạy theo lịch và ghi kết quả vào output binding. Để kết nối Azure Java Worker với Spring application context, Spring Cloud Function cung cấp **`spring-cloud-function-adapter-azure`**. Một class có `@Component` có thể inject `FunctionCatalog`; các phương thức `@FunctionName` với trigger/binding annotations trở thành entrypoint mà Azure Host phát hiện.

Bài này tập trung vào **ba khái niệm dễ nhầm**:

1. **Trigger:** xác định điều gì **khởi động một invocation**; mỗi Azure Function chỉ có **một trigger**.
2. **Input binding:** đọc dữ liệu **bổ sung** cho một invocation đã được kích hoạt.
3. **Output binding:** đưa kết quả đến một hệ thống đích, không bắt buộc trùng nơi nguồn kích hoạt.

Sau bài học, bạn có thể:

- Viết HTTP trigger nhận `HttpRequestMessage<Optional<String>>` và trả `HttpResponseMessage`.
- Dùng `@QueueOutput` kết hợp `OutputBinding<String>` để phát message ra Azure Storage Queue.
- Dùng `@QueueTrigger` để xử lý message và tiếp tục phát kết quả đến queue khác.
- Hiểu `@TimerTrigger`, `@BlobTrigger`, `@BlobInput` và khi nào nên cân nhắc Event Hubs, Service Bus, Event Grid.
- Giữ function nghiệp vụ độc lập trigger, dùng `FunctionCatalog.lookup(...)` hoặc composition, kiểm thử từng ranh giới và quản lý lỗi/redelivery/idempotency.

## 2. Trigger khác input binding và output binding như thế nào?

Một Azure Function có thể có **một trigger**, **không hoặc nhiều input bindings** và **không hoặc nhiều output bindings**, trong phạm vi những loại binding và Java signature mà extension hỗ trợ.

~~~mermaid
flowchart LR
    T["Trigger<br/>HTTP hoặc Queue hoặc Timer"] --> H["Azure Host / Java Worker"]
    I["Input binding tùy chọn<br/>Blob hoặc dữ liệu khác"] --> H
    H --> M["@FunctionName Java method"]
    S["Spring @Component<br/>+ FunctionCatalog"] --> M
    M --> O["Output binding<br/>Queue / Blob / Event Hub / ..."]
    M --> R["HTTP response<br/>nếu là HTTP trigger"]
~~~

| Khái niệm | Câu hỏi trả lời | Ví dụ Java | Không có nghĩa |
| --- | --- | --- | --- |
| **Trigger** | *Khi nào* và *vì sao* function chạy? | `@HttpTrigger`, `@QueueTrigger`, `@TimerTrigger` | Không mặc nhiên ghi dữ liệu ra một nơi khác. |
| **Input binding** | Invocation đang chạy cần *đọc thêm gì*? | `@BlobInput` | Không tự khởi động một invocation mới. |
| **Output binding** | *Đưa kết quả đi đâu*? | `@QueueOutput` + `OutputBinding<String>` | Không phải trigger mới hay transaction phân tán. |
| **Return value** | Phương thức trả dữ liệu cho binding/HTTP ra sao? | `HttpResponseMessage`, `String` | Không phải luôn là response HTTP; tùy output binding. |
| **Spring function** | *Nghiệp vụ gì* được chạy? | `Function<T,R>` từ catalog | Không tự tạo trigger/binding Azure. |

Cần phân biệt thêm:

- `@FunctionName("name")` là **tên Azure Function** do host nhận diện.
- `@Bean Function<T,R> methodName()` là **tên bean** mà SCF có thể đăng ký.
- `catalog.lookup("f1|f2")` là **composition** trong Spring Cloud Function, không phải tên Queue, topic hoặc function.json.
- Spring Cloud Function **`Supplier`** có thể được gọi từ Timer Trigger, nhưng chỉ có `@Bean Supplier` không tự tạo một Timer Trigger.

### 2.1. Một function không có hai trigger

Sai về mặt mô hình:

~~~java
// Không làm như sau: hai trigger trên một function.
@FunctionName("twoSources")
public void wrong(
        @HttpTrigger(name = "req", authLevel = AuthorizationLevel.FUNCTION)
        String httpBody,
        @QueueTrigger(name = "event", queueName = "order-work",
                      connection = "AzureWebJobsStorage")
        String queueBody) {
    // Azure Function chỉ được có một trigger.
}
~~~

Đây là **mã phản ví dụ**, không sao chép vào ứng dụng chạy thật. Nếu HTTP và Queue cùng cần chuẩn hóa mã đơn, tạo **hai phương thức `@FunctionName`** riêng cùng inject một business function.

### 2.2. Trigger event không giống webhook request

Azure Storage Queue Trigger có thể đọc lại item do retry/redelivery; HTTP request thường có caller đang đợi phản hồi; Timer Trigger chạy theo lịch mà không có body nghiệp vụ. Vì thế **đường lỗi/ack/retry khác nhau**, dù cả ba có thể gọi một `Function<String,String>`.

## 3. Tổng quan những trigger và binding thường gặp

| Nguồn/dịch vụ | Trigger | Input binding | Output binding | Dùng khi |
| --- | --- | --- | --- | --- |
| **HTTP** | `@HttpTrigger` | Request payload từ trigger | `HttpResponseMessage` hoặc HTTP output binding | Request/reply, API/webhook. |
| **Timer** | `@TimerTrigger` | Không có input binding Timer riêng | Có thể kết hợp Queue/Blob/... output | Chạy tác vụ theo lịch. |
| **Azure Storage Queue** | `@QueueTrigger` | Payload từ trigger | `@QueueOutput` | Xử lý công việc bất đồng bộ đơn giản. |
| **Azure Blob Storage** | `@BlobTrigger` | `@BlobInput` | `@BlobOutput` | Xử lý tệp được tạo/cập nhật hoặc đọc/ghi blob. |
| **Azure Service Bus** | `@ServiceBusQueueTrigger` / `@ServiceBusTopicTrigger` | Payload từ trigger | Queue/topic output bindings | Hàng đợi/topic doanh nghiệp với session, dead-letter và duplicate detection tùy cấu hình. |
| **Azure Event Hubs** | `@EventHubTrigger` | Payload event stream từ trigger | `@EventHubOutput` | Dòng sự kiện throughput cao, partition/consumer group. |
| **Event Grid** | `@EventGridTrigger` | Payload sự kiện từ trigger | Event Grid output binding | Thông báo thay đổi tài nguyên/dịch vụ. |
| **Azure Cosmos DB** | `@CosmosDBTrigger` | Cosmos DB input binding | Cosmos DB output binding | Change feed hoặc đọc/ghi tài liệu, theo extension. |

Không phải dịch vụ nào cũng có cả ba loại binding. Ví dụ **Timer chỉ có trigger**, còn HTTP thường dùng trigger + response. Phải kiểm tra **binding extension**, Java annotation API, hosting plan và quyền kết nối của dịch vụ cụ thể. Khả năng hỗ trợ có thể thay đổi theo phiên bản extension và runtime.

**Azure Storage Queue không phải Azure Service Bus Queue.** Chúng có namespace, connection, retry, thông điệp và tính năng vận hành khác nhau; không thay `@QueueTrigger` bằng `@ServiceBusQueueTrigger` mà không đổi hạ tầng tương ứng.

## 4. Dependency và cách Azure phát hiện bindings

### 4.1. Dependency Maven

Ví dụ cho dự án Maven đã có Spring Boot parent và **Spring Cloud BOM tương thích**:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-function-adapter-azure</artifactId>
    </dependency>
    <dependency>
        <groupId>com.microsoft.azure.functions</groupId>
        <artifactId>azure-functions-java-library</artifactId>
        <version>1.3.1</version>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`1.3.1` là **phiên bản minh họa** của Azure Java Functions library, không phải khẳng định phiên bản mới nhất tại mọi thời điểm. Cần thống nhất với Azure Java project template đang dùng. `spring-cloud-function-adapter-azure` yêu cầu **SCF 4.0.0+** cho mô hình `@Component`/`@FunctionName` hiện đại; version adapter và `spring-cloud-function-context` phải cùng dòng được BOM quản lý.

### 4.2. Azure plugin và binding extensions

Ngoài thư viện runtime, Java Azure Functions cần **Azure Maven/Gradle plugin** để quét các annotations và sinh `function.json`, `host.json` cùng package Azure phù hợp.

Ví dụ các loại metadata được plugin tạo từ cùng một method:

~~~json
{
  "bindings": [
    {
      "type": "httpTrigger",
      "direction": "in",
      "name": "request",
      "route": "orders",
      "methods": ["post"],
      "authLevel": "function"
    },
    {
      "type": "queue",
      "direction": "out",
      "name": "work",
      "queueName": "order-work",
      "connection": "AzureWebJobsStorage"
    },
    {
      "type": "http",
      "direction": "out",
      "name": "$return"
    }
  ]
}
~~~

Đây là **minh họa binding metadata**, không phải `function.json` hoàn chỉnh cho mọi phiên bản. Plugin cũng tạo `scriptFile` và `entryPoint` phù hợp với Java application artifact và handler. Không chỉnh tay output staging để sửa một Java annotation bị khai báo sai.

HTTP và Timer thuộc những binding cơ bản của host; Blob/Queue, Event Hubs, Service Bus, Event Grid và các dịch vụ khác có thể cần **extension bundle/extension registration** tương thích. Một class Java biên dịch thành công không đảm bảo host load được extension để chạy trigger. Kiểm tra host startup logs và tài liệu binding được chọn.

### 4.3. Gradle tương ứng

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-adapter-azure'
    implementation 'com.microsoft.azure.functions:azure-functions-java-library:1.3.1'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Dùng plugin Gradle `com.microsoft.azure.azurefunctions` để package/run/deploy, hoặc Maven plugin `com.microsoft.azure:azure-functions-maven-plugin` nếu dùng Maven. Chỉ chọn một workflow build để tránh thay đổi artifact không kiểm soát.

## 5. Ví dụ đầy đủ: HTTP → Queue → Queue Trigger → Queue

### 5.1. Yêu cầu nghiệp vụ

Một ứng dụng nhận mã đơn hàng dạng text qua HTTP:

~~~text
POST /api/orders
Body: "  dh-301  "

→ HTTP 202 Accepted
→ Azure Storage Queue "order-work" nhận "DH-301"
→ Queue Trigger xử lý message
→ Azure Storage Queue "order-results" nhận "DH-301"
~~~

Cùng một quy tắc **chuẩn hóa mã đơn** có thể được tái sử dụng từ hai entrypoints bằng SCF composition:

~~~text
trimCode   : Function<String,String>
upperCode  : Function<String,String>

FunctionCatalog.lookup("trimCode|upperCode")
  → Function<String,String>
~~~

~~~mermaid
flowchart LR
    A["HTTP client"] --> B["@HttpTrigger<br/>submitOrder"]
    B --> C["FunctionCatalog<br/>trimCode|upperCode"]
    C --> D["@QueueOutput<br/>order-work"]
    D --> E["Azure Storage Queue"]
    E --> F["@QueueTrigger<br/>processOrder"]
    F --> G["Cùng FunctionCatalog"]
    G --> H["@QueueOutput<br/>order-results"]
~~~

**Chính sách bài tập:** nếu body rỗng, HTTP trả 400 và không đặt message vào queue. Queue Trigger ném exception với message rỗng hoặc xử lý thất bại để Azure Host áp dụng retry/poison-message policy phù hợp. Trong production, tránh log nguyên payload nhạy cảm và triển khai idempotency theo mã sự kiện/giao dịch riêng.

### 5.2. Spring Boot class khai báo business function

Tạo `src/main/java/example/azure/OrderFunctionsApplication.java`:

~~~java
package example.azure;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrderFunctionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderFunctionsApplication.class, args);
    }

    @Bean
    public Function<String, String> trimCode() {
        return String::strip;
    }

    @Bean
    public Function<String, String> upperCode() {
        return value -> value.toUpperCase(Locale.ROOT);
    }
}
~~~

Hai hàm không import Azure SDK, không biết Queue name/HTTP route. Có thể gọi trực tiếp trong Java, qua HTTP adapter khác hoặc từ một serverless runtime khác nếu adapter tương ứng chuyển dữ liệu đúng kiểu.

### 5.3. Azure handler với hai entrypoints và output bindings

Tạo `src/main/java/example/azure/OrderAzureHandlers.java`:

~~~java
package example.azure;

import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;

import com.microsoft.azure.functions.AuthorizationLevel;
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.HttpMethod;
import com.microsoft.azure.functions.HttpRequestMessage;
import com.microsoft.azure.functions.HttpResponseMessage;
import com.microsoft.azure.functions.HttpStatus;
import com.microsoft.azure.functions.OutputBinding;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.HttpTrigger;
import com.microsoft.azure.functions.annotation.QueueOutput;
import com.microsoft.azure.functions.annotation.QueueTrigger;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class OrderAzureHandlers {

    private final Function<String, String> normalize;

    public OrderAzureHandlers(FunctionCatalog catalog) {
        this.normalize = Objects.requireNonNull(
                catalog.lookup("trimCode|upperCode"),
                "Không tìm thấy function trimCode|upperCode");
    }

    @FunctionName("submitOrder")
    public HttpResponseMessage submitOrder(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION,
                    route = "orders")
            HttpRequestMessage<Optional<String>> request,

            @QueueOutput(
                    name = "work",
                    queueName = "order-work",
                    connection = "AzureWebJobsStorage")
            OutputBinding<String> work,

            ExecutionContext context) {

        String body = request.getBody().orElse("");
        if (body.isBlank()) {
            return request.createResponseBuilder(HttpStatus.BAD_REQUEST)
                    .body("Mã đơn không được rỗng")
                    .build();
        }

        String normalized = normalize.apply(body);
        work.setValue(normalized);

        context.getLogger().info("Order submitted");
        return request.createResponseBuilder(HttpStatus.ACCEPTED)
                .body("Accepted: " + normalized)
                .build();
    }

    @FunctionName("processOrder")
    public void processOrder(
            @QueueTrigger(
                    name = "order",
                    queueName = "order-work",
                    connection = "AzureWebJobsStorage")
            String orderCode,

            @QueueOutput(
                    name = "result",
                    queueName = "order-results",
                    connection = "AzureWebJobsStorage")
            OutputBinding<String> result,

            ExecutionContext context) {

        if (orderCode == null || orderCode.isBlank()) {
            throw new IllegalArgumentException(
                    "Message chứa mã đơn không hợp lệ");
        }

        String normalized = normalize.apply(orderCode);
        result.setValue(normalized);
        context.getLogger().info("Order processed");
    }
}
~~~

**Phân tích các ranh giới:**

1. `submitOrder` có **một** trigger HTTP và **một** Queue output binding. Hàm trả `HttpResponseMessage` cho HTTP client, trong khi `work.setValue(...)` khai báo một message sẽ được runtime ghi vào Queue output.
2. `processOrder` có **một** Queue trigger và **một** Queue output binding; nó **không** là một HTTP endpoint. Return type `void` phù hợp vì kết quả được đặt bằng `result.setValue(...)`.
3. `@Component` đảm bảo Spring quản lý handler và inject `FunctionCatalog`; `@FunctionName` đảm bảo Azure nhận diện từng Azure Function.
4. Tên `submitOrder`/`processOrder` thuộc **Azure Host**; tên `trimCode`/`upperCode` thuộc **SCF catalog**.
5. `OutputBinding<String>` là vùng đặt giá trị cho output binding; gọi `setValue` **không đồng nghĩa** message đã được downstream xử lý xong hoặc được một transaction phân tán commit cùng HTTP response.
6. Azure Host điều phối kết nối/ghi binding khi function thực thi. Nếu ghi queue thất bại, toàn invocation có thể được báo lỗi; vì vậy HTTP 202 trong thiết kế này không phải xác nhận nghiệp vụ hoàn tất ở queue đích.
7. `ExecutionContext` là ngữ cảnh của invocation, thích hợp cho logger, không nên được lưu trong singleton handler.

### 5.4. Vì sao lựa chọn HTTP 202 thay vì 200?

HTTP 202 `Accepted` diễn đạt yêu cầu đã được nhận vào **quy trình bất đồng bộ**, không khẳng định bước Queue Trigger đã hoàn thành. Đây là **chính sách API của ví dụ**; trong production, nếu client cần tra cứu trạng thái, nên trả về mã yêu cầu/correlation ID và cung cấp status endpoint hoặc event thông báo sau xử lý.

Lưu ý thời điểm output binding thực sự được commit phụ thuộc runtime và extension. Không triển khai logic coi `work.setValue(...)` là một xác nhận durable end-to-end khi chưa kiểm thử/thiết kế tính nhất quán.

### 5.5. Main class và Azure Functions Host

`OrderFunctionsApplication` cùng package `example.azure` với `OrderAzureHandlers`, nên component scan có thể thấy handler. Đặt `MAIN_CLASS=example.azure.OrderFunctionsApplication` nếu adapter cần chỉ định tường minh main class trong local/Azure settings.

Function App dùng **Azure Functions runtime 4.x** cùng Java runtime phù hợp, Azure Maven/Gradle plugin tạo `function.json` và package hợp lệ. **Không tự chạy `SpringApplication.run(...)` mỗi invocation**; adapter quản lý việc tạo Spring context theo vòng đời worker.

## 6. Chi tiết HTTP trigger và response

### 6.1. @HttpTrigger

~~~java
@FunctionName("submitOrder")
public HttpResponseMessage submitOrder(
        @HttpTrigger(
                name = "request",
                methods = {HttpMethod.POST},
                authLevel = AuthorizationLevel.FUNCTION,
                route = "orders")
        HttpRequestMessage<Optional<String>> request,
        @QueueOutput(name = "work",
                     queueName = "order-work",
                     connection = "AzureWebJobsStorage")
        OutputBinding<String> work,
        ExecutionContext context) {
    // Logic ở phần 5.
}
~~~

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `name` | Tên parameter binding trong metadata (ví dụ `request`). |
| `methods` | HTTP methods được phép kích hoạt. |
| `authLevel` | Chính sách authorization key: `ANONYMOUS`, `FUNCTION`, `ADMIN` tùy tình huống. |
| `route` | URL path tương đối; prefix mặc định là `/api`. |
| `HttpRequestMessage<T>` | Đọc body, query parameters, headers, URI và method. |
| `HttpResponseMessage` | Trả status, headers và body cho HTTP caller. |

`@HttpTrigger` được đặt trên **tham số**, `@FunctionName` đặt trên **phương thức**. Các Java entrypoints của Azure phải là `public`. Azure Maven/Gradle plugin dùng annotations để tạo metadata; chỉ đặt `@Component` không tự tạo HTTP route.

### 6.2. Query, path parameter và header

Có thể đọc query string bằng:

~~~java
String orderId = request.getQueryParameters().get("orderId");
String correlation = request.getHeaders().get("x-correlation-id");
~~~

Nếu route khai báo `route = "orders/{id}"`, có thể thêm tham số:

~~~java
@BindingName("id") String id
~~~

với import `com.microsoft.azure.functions.annotation.BindingName`. Bài demo nhận text body để tránh parsing phức tạp; khi nhận JSON, cần deserialize và validate domain object ở ranh giới trước khi gọi `Function<OrderRequest,OrderDecision>`.

Không tin tuyệt đối header/route/query do client cung cấp: chúng cần validation, authorization và giới hạn kích thước; không dùng input ngoài để tự ý chọn `catalog.lookup(...)` theo tên function.

### 6.3. Auth và lỗi HTTP

- `AuthorizationLevel.FUNCTION` yêu cầu function/host key theo chính sách host trên Azure; key không thay thế đầy đủ user authentication/authorization cho API nhạy cảm.
- Local Core Tools có thể xử lý authorization khác production; kiểm tra cloud staging trước khi mở endpoint công khai.
- Input rỗng/sai schema nên trả 4xx theo hợp đồng API.
- Lỗi hạ tầng có thể cần 5xx/timeout và request ID để tra cứu.
- Response status HTTP không nên được dùng làm nguồn duy nhất xác định việc downstream đã xử lý Queue message.

## 7. Queue Trigger và Queue Output Binding

### 7.1. Queue Trigger

~~~java
@FunctionName("processOrder")
public void processOrder(
        @QueueTrigger(name = "order",
                      queueName = "order-work",
                      connection = "AzureWebJobsStorage")
        String orderCode,
        ExecutionContext context) {
    // Gọi business function.
}
~~~

`queueName` là tên Azure Storage Queue, còn `connection` là **tên app setting/connection configuration**, không phải chuỗi connection string viết trực tiếp trong annotation. Queue trigger có cơ chế host đọc queue và đánh thức function khi message sẵn sàng.

**Queue không phải SCF Supplier:** Azure Host/extension chủ động kích hoạt theo Queue trigger. Một `@Bean Supplier<T>` không tự đọc queue; nếu muốn dùng supplier thì handler/adapter phải gọi nó theo cơ chế rõ ràng.

### 7.2. Queue Output Binding

~~~java
@QueueOutput(
        name = "result",
        queueName = "order-results",
        connection = "AzureWebJobsStorage")
OutputBinding<String> result
~~~

Trong thân handler:

~~~java
result.setValue(normalized);
~~~

`OutputBinding<T>` là abstraction của Azure Java library để đặt output, không phải `java.util.function.Consumer<T>` hoặc một Spring Integration channel. Azure host/binding extension xử lý việc ghi giá trị đến Queue.

Ngoài dạng tham số `OutputBinding<T>`, Azure Java cũng hỗ trợ khai báo output binding trên return value theo API/annotation tương ứng. Với **HTTP response và Queue output cùng lúc**, cách tham số `OutputBinding<String>` làm rõ rằng HTTP return và Queue message là **hai đầu ra độc lập**.

### 7.3. Retry, poison queue và dữ liệu trùng

Queue Trigger có thể thử lại một message khi invocation lỗi; sau nhiều lần thất bại, message có thể chuyển sang **poison queue** theo cơ chế/cấu hình Azure Queue Storage extension. Thời điểm retry, dequeue count, encoding và giới hạn xử lý phụ thuộc version host/extension.

Vì thế:

- Không nuốt exception nếu hệ thống cần trigger retry.
- Không retry vô hạn với dữ liệu validation sai; cần quarantine/poison-message policy.
- Không giả định exactly-once; cùng message có thể đến lại.
- Dùng `eventId` hoặc khóa nghiệp vụ ổn định, lưu trạng thái bằng storage có đảm bảo atomicity.
- Phân biệt **Azure Storage Queue poison queue** với **Service Bus DLQ**, vì đó là hai cơ chế thuộc hai dịch vụ khác nhau.
- Khi đặt Queue message text từ SDK ngoài, xác nhận **message encoding** tương ứng với Queue extension để tránh xử lý sai base64/plain text theo phiên bản.

### 7.4. Không gán mặc định output binding là một transaction

Nếu business function ghi DB rồi output binding phát Queue message, hai thao tác không tự nằm trong một transaction phân tán. Nếu phải bảo đảm phát sự kiện sau commit, cân nhắc **transactional outbox** và idempotency. HTTP response 202 không thay thế acknowledgement của message broker.


## 8. Timer Trigger: lịch kích hoạt khác Supplier.get()

### 8.1. Biểu thức NCRONTAB

Azure Timer Trigger chạy một phương thức `@FunctionName` theo lịch được Azure Host quản lý:

~~~java
@FunctionName("scheduledHeartbeat")
public void scheduledHeartbeat(
        @TimerTrigger(
                name = "timer",
                schedule = "0 */5 * * * *")
        String timerInfo,
        ExecutionContext context) {
    context.getLogger().info("Timer triggered");
}
~~~

Cần import `com.microsoft.azure.functions.annotation.TimerTrigger`. Lịch `0 */5 * * * *` nghĩa là tại giây 0, **mỗi năm phút**, theo định dạng **NCRONTAB sáu trường**:

~~~text
{second} {minute} {hour} {day} {month} {day-of-week}
~~~

Azure Functions mặc định dùng **UTC**; cấu hình timezone bằng `WEBSITE_TIME_ZONE` có giới hạn theo hosting plan/OS, đặc biệt các plan Linux Consumption/Flex Consumption. Không dùng cấu hình timezone tùy tiện mà chưa đối chiếu tài liệu triển khai.

Ví dụ khác:

| NCRONTAB | Ý nghĩa |
| --- | --- |
| `0 */5 * * * *` | Mỗi 5 phút. |
| `0 0 * * * *` | Đầu mỗi giờ. |
| `0 30 9 * * *` | Mỗi ngày lúc 09:30 theo timezone của host. |
| `0 0 */2 * * *` | Mỗi 2 giờ, tại phút/giây 0. |

**Timer không phải một input binding bổ sung:** nó là trigger. Nếu Timer Function cần đọc DB, Blob hoặc service, có thể gọi SDK/service bean hoặc có input binding tương ứng trong giới hạn Azure extension.

### 8.2. Timer Trigger gọi SCF Supplier rồi phát Queue output

Nếu muốn phát một heartbeat/event mới theo lịch, bean `Supplier<String>` cung cấp dữ liệu:

~~~java
@Bean
Supplier<String> createHeartbeat() {
    return () -> "heartbeat-" + UUID.randomUUID();
}
~~~

Cần import `java.util.function.Supplier` và `java.util.UUID` trong Spring configuration. Một Azure handler có thể inject catalog và dùng supplier:

~~~java
@Component
class HeartbeatHandler {

    private final Supplier<String> heartbeat;

    HeartbeatHandler(FunctionCatalog catalog) {
        this.heartbeat = Objects.requireNonNull(
                catalog.lookup("createHeartbeat"),
                "Không tìm thấy createHeartbeat");
    }

    @FunctionName("sendHeartbeat")
    public void sendHeartbeat(
            @TimerTrigger(
                    name = "timer",
                    schedule = "0 */5 * * * *")
            String timerInfo,

            @QueueOutput(
                    name = "out",
                    queueName = "order-ops",
                    connection = "AzureWebJobsStorage")
            OutputBinding<String> out,

            ExecutionContext context) {

        out.setValue(heartbeat.get());
        context.getLogger().info("Heartbeat generated");
    }
}
~~~

Đây là **cấu hình bổ sung độc lập**; cần các imports Azure/Spring tương ứng và bean `createHeartbeat` được đăng ký. Nó không phải một phần bắt buộc của hai handlers trong ví dụ chính.

Điểm mấu chốt:

- `@TimerTrigger` quyết định **thời điểm** invoke.
- `Supplier.get()` quyết định **giá trị** muốn phát.
- `@QueueOutput` chỉ định **đích** của sự kiện.
- Nếu supplier luôn trả cùng một giá trị, mỗi lần chạy lịch có thể phát các message giống nhau.
- Timer Trigger có cách quản lý lỗi và miss schedule riêng; không tự áp dụng poison-queue retry như Queue Trigger. Nếu cần retry, sử dụng cơ chế mà Azure Functions hỗ trợ cho loại trigger/runtime đã chọn, hoặc thiết kế job có trạng thái và checkpoint.

## 9. Blob Trigger và Blob Input Binding

### 9.1. Blob Trigger: tệp làm nguồn kích hoạt

Khi một blob được tạo hoặc cập nhật ở container được quan sát, `@BlobTrigger` có thể kích hoạt Java handler:

~~~java
@FunctionName("inspectIncomingBlob")
public void inspectIncomingBlob(
        @BlobTrigger(
                name = "blob",
                path = "incoming/{name}",
                connection = "AzureWebJobsStorage",
                dataType = "binary")
        byte[] content,

        @BindingName("name") String filename,
        ExecutionContext context) {

    context.getLogger().info(
            "Blob received, size=" + content.length);
}
~~~

Cần import `com.microsoft.azure.functions.annotation.BlobTrigger` và `BindingName`. Đây là **method độc lập**, giả định có Azure Storage container `incoming` và Blob extension tương thích. `{name}` là binding expression cho blob name. `dataType = "binary"` phù hợp khi Java parameter nhận `byte[]`.

**Cẩn thận kích thước:** đọc cả blob vào `byte[]` có thể tốn nhiều RAM. Với file lớn, nên kiểm tra những kiểu stream/SDK binding được extension Java hỗ trợ hoặc dùng Azure Blob SDK để tải theo luồng. Không áp dụng mặc định cơ chế tải toàn bộ file cho dữ liệu lớn.

Blob Trigger có cách phát hiện và retry khác nhau tùy extension/`source` (ví dụ cơ chế quét container so với Event Grid-based trigger). Kiểm tra latency, concurrency và điều kiện tạo/cập nhật blob trong tài liệu extension thực tế.

### 9.2. Blob Input: đọc tệp bổ sung cho một Queue Trigger

Một item Queue chứa **tên file**; chính Queue Trigger khởi động invocation, còn Blob Input chỉ đọc nội dung của file liên quan:

~~~java
@FunctionName("inspectQueuedDocument")
public void inspectQueuedDocument(
        @QueueTrigger(
                name = "filename",
                queueName = "document-work",
                connection = "AzureWebJobsStorage")
        String filename,

        @BlobInput(
                name = "document",
                path = "documents/{queueTrigger}",
                dataType = "binary")
        byte[] document,

        ExecutionContext context) {

    context.getLogger().info(
            "Document size=" + document.length);
}
~~~

Cần import `com.microsoft.azure.functions.annotation.BlobInput`. Trong ví dụ, `BlobInput` dùng storage mặc định `AzureWebJobsStorage`; muốn storage khác, khai báo connection/`@StorageAccount` theo API/extension tương ứng.

**Đây là trường hợp minh họa quan trọng:** Queue event là **trigger**, Blob được đọc bằng **input binding**, và handler có thể xử lý cả hai dữ liệu. Không xuất hiện một Blob Trigger thứ hai trong method này.

Dữ liệu Queue do bên ngoài cung cấp không nên được tin tuyệt đối khi dùng làm blob path. Kiểm tra tên file, namespace, access control, kích thước và hành vi khi blob không tồn tại. Với file lớn, lựa chọn SDK stream hoặc quản lý bằng service riêng phù hợp hơn.

### 9.3. Blob Output

Azure Java còn có `@BlobOutput` để ghi kết quả vào Blob Storage bằng output binding. Một pipeline có thể:

~~~text
Queue Trigger (tên file)
    +
Blob Input (dữ liệu file)
    ↓
Business Function
    ↓
Blob Output (file đã xử lý)
~~~

Chọn `path`, `connection`, content type và quyền ghi theo dữ liệu thực tế. Nếu output path trùng với container/pattern được Blob Trigger theo dõi, có thể vô tình tạo vòng lặp event; tách vùng input/output hoặc có policy chống xử lý lại.

## 10. Event Hubs, Service Bus, Event Grid và Cosmos DB

### 10.1. Event Hubs Trigger

Event Hubs phù hợp các luồng telemetry/event throughput cao, có **partition**, **consumer group** và checkpoint. Ví dụ một Java method:

~~~java
@FunctionName("receiveOrderEvents")
public void receiveOrderEvents(
        @EventHubTrigger(
                name = "event",
                eventHubName = "order-events",
                consumerGroup = "$Default",
                connection = "EventHubConnection")
        String payload,
        ExecutionContext context) {

    String normalized = normalize.apply(payload);
    context.getLogger().info("Event Hub event handled");
}
~~~

Cần import `com.microsoft.azure.functions.annotation.EventHubTrigger`; đây là **fragment của một handler riêng**, giả định field `normalize` được inject như ví dụ phần 5 và đã có Event Hubs extension/connection. Khi nhận event JSON thay vì mã đơn text, phải deserialize/validate trước khi gọi function.

`EventHubTrigger` hỗ trợ cấu hình `cardinality` (một event hoặc batch) theo Java API và phiên bản extension. Khi chọn batch, chữ ký tham số và cách xử lý lỗi/checkpoint khác với event đơn. Đừng sao chép phương thức nhận `String` rồi chỉ đổi `cardinality` thành `MANY` mà không xem kiểu input được binding hỗ trợ.

### 10.2. Service Bus Queue và Topic Trigger

Service Bus cung cấp nhiều tính năng message broker như sessions, dead-letter và duplicate detection theo cấu hình. Ví dụ Queue Trigger:

~~~java
@FunctionName("receiveServiceBusOrder")
public void receiveServiceBusOrder(
        @ServiceBusQueueTrigger(
                name = "message",
                queueName = "orders",
                connection = "ServiceBusConnection")
        String payload,
        ExecutionContext context) {

    String normalized = normalize.apply(payload);
    context.getLogger().info("Service Bus message handled");
}
~~~

Cần import `com.microsoft.azure.functions.annotation.ServiceBusQueueTrigger`. Với topic subscription dùng `@ServiceBusTopicTrigger`, cấu hình `topicName` và `subscriptionName`. Ở chiều phát, dùng `@ServiceBusQueueOutput` hoặc `@ServiceBusTopicOutput` chứ **không dùng `@QueueOutput` của Azure Storage Queue**.

Chú ý đối với dự án Java hiện đại: nếu sử dụng Service Bus SDK trực tiếp, chọn thư viện được Microsoft hỗ trợ như `com.azure:azure-messaging-servicebus`; những SDK Service Bus cũ đã hết hỗ trợ vào năm 2026. Dùng Functions binding không đồng nghĩa tự đưa những SDK legacy vào classpath.

### 10.3. Event Grid và Cosmos DB

- **Event Grid Trigger** thường nhận thông báo về sự kiện tài nguyên hoặc nghiệp vụ. Event Grid event schema và CloudEvents schema có thể khác; cần xác nhận contract payload trước khi gọi function.
- **Cosmos DB Trigger** theo dõi change feed theo cơ chế extension; cần xác định cách đọc batch, lease container, idempotency và trường hợp update cùng tài liệu nhiều lần.
- **Azure Storage Queue** thường thích hợp cho công việc bất đồng bộ đơn giản; **Service Bus** thích hợp khi cần các cơ chế của broker; **Event Hubs** phù hợp stream volume lớn; **Event Grid** phù hợp thông báo sự kiện phân phối. Không thay chúng chỉ bằng cách đổi annotation mà không thay hạ tầng.

### 10.4. Bảng chọn nguồn theo yêu cầu

| Nhu cầu | Điểm bắt đầu phù hợp | Rủi ro phải kiểm soát |
| --- | --- | --- |
| HTTP request/reply | `@HttpTrigger` | Auth, validation, timeouts, synchronous workload. |
| Nhận công việc từ hàng đợi đơn giản | `@QueueTrigger` | Redelivery, poison queue, encoding, storage permission. |
| Message broker có topics/sessions | Service Bus Trigger | Lock/settlement, dead-letter, duplicate detection. |
| Stream telemetry/event throughput cao | Event Hubs Trigger | Partition ordering, checkpoint, batch, consumer group. |
| Xử lý file mới | Blob Trigger | File size, trigger source, lặp vô hạn khi ghi lại file. |
| Đọc file được chỉ ra bởi message khác | Queue Trigger + Blob Input | Blob path, quyền truy cập, file mất hoặc chưa sẵn sàng. |
| Tác vụ định kỳ | Timer Trigger | Timezone, missed schedule, idempotent job, cold start. |

## 11. Binding data, metadata và conversion

### 11.1. Dữ liệu từ trigger không tự thành domain object

Ví dụ HTTP body JSON:

~~~json
{
  "eventId": "evt-301",
  "orderId": " dh-301 ",
  "totalVnd": 1500000
}
~~~

Có thể định nghĩa:

~~~java
record OrderRequest(
        String eventId,
        String orderId,
        long totalVnd) {}
~~~

và business function:

~~~java
@Bean
Function<OrderRequest, String> normalizeOrderRequest() {
    return order -> order.orderId()
            .strip()
            .toUpperCase(Locale.ROOT);
}
~~~

Tuy nhiên, **HTTP `HttpRequestMessage<Optional<String>>` trong phần 5 trả body String**, không tự là một `OrderRequest`. Handler cần bước JSON deserialization và validation hoặc dùng POJO binding do Azure Java Worker hỗ trợ với type hợp lệ. SCF FunctionCatalog có khả năng wrapper/conversion, nhưng không có nghĩa mọi format trong HTTP/Queue/Blob được tự giải mã thành mọi Java record.

Đồng thời, cấu trúc `OrderRequest` chỉ dùng để trình bày contract; nếu gọi production, hãy kiểm tra null, schema version, enum, numeric range, content type và kích thước input.

### 11.2. Trigger metadata là dữ liệu của invocation

Các trigger có thể mang:

| Trigger | Metadata thường quan trọng |
| --- | --- |
| HTTP | Method, route/query, request headers, correlation/trace context. |
| Storage Queue | Message ID, dequeue count, thời điểm enqueue và thông tin retry. |
| Blob | Container/path/name, ETag, blob properties. |
| Event Hubs | Partition/sequence/offset, enqueued time, consumer group. |
| Service Bus | Message ID, correlation ID, delivery count, session, lock. |
| Timer | Thời điểm schedule, thông tin past-due theo model. |

Azure Java có `@BindingName` để lấy một số trigger/binding metadata được hỗ trợ. Không giả định mọi metadata đều tồn tại dưới cùng tên hay cùng kiểu ở tất cả extensions.

### 11.3. Spring Message<T> và Azure binding metadata

Một business function đơn giản `Function<String,String>` chỉ cần payload. Nếu cần trace/correlation, handler có thể:

- Đọc metadata từ `HttpRequestMessage` hoặc binding context.
- Chuyển metadata vào domain input khi nó có ý nghĩa nghiệp vụ.
- Hoặc xây `Message<T>` của Spring và gọi function có chữ ký `Function<Message<T>,R>` trong những trường hợp SCF adapter/wrapper đã được kiểm chứng.

Tài liệu SCF cung cấp `AzureFunctionUtil.enhanceInputIfNecessary(...)` để đưa `ExecutionContext` vào Spring message header khi cần. Nhưng không nên truyền toàn bộ Azure runtime object vào business function nếu mục tiêu tái sử dụng ở HTTP/broker/serverless khác.

### 11.4. CloudEvents không thay trigger

CloudEvents là một **đặc tả envelope sự kiện** (id, source, type, specversion, data), không phải một loại Azure trigger mặc định cho tất cả hạ tầng. Event Grid, Event Hubs hoặc HTTP có thể mang CloudEvent theo contract riêng. Vẫn cần trigger/binding phù hợp, parser/converter, validation và metadata propagation tương ứng.

## 12. Local settings, extensions và đóng gói

### 12.1. local.settings.json

Ví dụ local **chỉ dành cho Storage emulator**:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "FUNCTIONS_EXTENSION_VERSION": "~4",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "MAIN_CLASS": "example.azure.OrderFunctionsApplication"
  }
}
~~~

Khi sử dụng `UseDevelopmentStorage=true`, cần chạy **Azurite** hoặc storage emulator tương thích. Ví dụ không có Service Bus/Event Hubs credentials; nếu chạy thêm hai trigger đó, cần app settings và identity/connection tương ứng. **Không commit secrets trong local.settings.json** vào repository.

Trong môi trường Azure, thiết lập Function App settings/managed identity/Key Vault theo chính sách vận hành. `connection` trong annotation thường chỉ tên setting hoặc prefix cấu hình kết nối; không đặt connection string trực tiếp trong source code.

### 12.2. host.json và extension bundle

Mẫu tối thiểu:

~~~json
{
  "version": "2.0"
}
~~~

Một số host/bindings cần extension bundle hoặc đăng ký extension được cấu hình theo runtime. Khi dùng Queue/Blob/Event Hubs/Service Bus, phải đối chiếu **version của binding extension** và cách cung cấp qua package hoặc extension bundle; không tự coi Java annotation đủ để extension xuất hiện.

### 12.3. Maven / Gradle package

Với Maven:

~~~bash
./mvnw clean package
./mvnw azure-functions:run
~~~

Với Gradle nếu dự án đã có Azure Functions plugin:

~~~bash
./gradlew azureFunctionsPackage
./gradlew azureFunctionsRun
~~~

Azure plugin tạo package với metadata/binding files do annotations sinh ra. **Spring Boot repackaged executable fat JAR thông thường không phải layout Azure Worker mong đợi**; cần tắt/điều chỉnh Boot repackage hoặc dùng cấu hình packaging chính thức phù hợp với adapter.

Không chạy cả Maven lẫn Gradle cho cùng một project chỉ vì bài học cung cấp hai tùy chọn.

## 13. Kiểm thử theo từng ranh giới

### 13.1. Unit test function nghiệp vụ

Không cần Azure Functions Host:

~~~java
OrderFunctionsApplication application =
        new OrderFunctionsApplication();

String normalized =
        application.upperCode().apply(
                application.trimCode().apply(" dh-301 "));

assertEquals("DH-301", normalized);
~~~

Cần JUnit 5 `assertEquals`. Unit test chỉ kiểm tra business function, không xác nhận Queue Output binding, retry hoặc host discovery.

### 13.2. Spring context / FunctionCatalog test

~~~java
@SpringBootTest(classes = OrderFunctionsApplication.class)
class CatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void compositionShouldNormalize() {
        Function<String, String> normalize =
                catalog.lookup("trimCode|upperCode");

        assertNotNull(normalize);
        assertEquals("DH-301",
                normalize.apply(" dh-301 "));
    }
}
~~~

Thêm imports của Spring Boot Test, `@Autowired`, `FunctionCatalog`, `Function` và JUnit Assertions. Test này phát hiện lỗi component scanning, dependency injection và composition name/type.

### 13.3. Azure Functions Host integration test

Chạy Core Tools local với Azurite. Gửi:

~~~bash
curl -i -X POST "http://localhost:7071/api/orders" \
  -H "Content-Type: text/plain" \
  --data " dh-301 "
~~~

Kỳ vọng về mặt hợp đồng demo: HTTP 202, Queue `order-work` nhận `DH-301`, sau đó `processOrder` được host kích hoạt và Queue `order-results` nhận `DH-301`.

Nếu host khởi động chưa có `@QueueTrigger` do extension chưa sẵn sàng, test có thể dừng ở bước HTTP hoặc thông báo lỗi ngay khi startup. Không khẳng định pipeline đạt yêu cầu nếu chỉ quan sát response HTTP.

### 13.4. Ma trận test lỗi tối thiểu

| Kiểm thử | Kỳ vọng |
| --- | --- |
| HTTP body hợp lệ | 202, message vào queue, downstream xử lý đúng. |
| HTTP body trống | 400 và **không** có output queue message. |
| HTTP method sai | Không được invoke như POST hợp lệ. |
| Không có function key trên Azure | Bị từ chối theo authorization policy. |
| Queue message rỗng | Queue Trigger ném lỗi; kiểm tra retry/poison behavior theo extension. |
| Queue output không có quyền ghi | Invocation bị lỗi hoặc output không commit; có log/monitoring. |
| Nhiều message cùng order/event ID | Consumer idempotent, không gây side effect trùng. |
| Restart host giữa pipeline | Dữ liệu được tiếp tục/xử lý lại theo thiết kế, không giả định exactly-once. |
| File Blob không tồn tại | Blob Input thất bại có phân loại và error handling. |
| Timer chạy muộn | Có chính sách past-due/đối soát dữ liệu theo lịch. |
| Event Hubs batch lỗi | Có chính sách xử lý từng item hoặc batch/checkpoint rõ. |

### 13.5. Không nhầm unit test và integration test

Một `Function<String,String>` xử lý đúng dữ liệu **không chứng minh**:

- Azure plugin đã sinh đúng `function.json`.
- Host đã load đúng Queue/Blob extension.
- `AzureWebJobsStorage` có quyền đọc/ghi.
- JSON/content type đã được map đúng.
- Retry/dead-letter/idempotency hoạt động.
- Azure Function App Java runtime khớp bytecode của JDK build.

Cần kiểm thử từng tầng và có test end-to-end trên môi trường staging gần production cho các loại trigger quan trọng.

## 14. Lỗi, retry, ACK và idempotency

| Trigger | Thông thường khi lỗi | Điều phải thiết kế |
| --- | --- | --- |
| HTTP | Trả lỗi cho caller hoặc timeout theo host/adapter. | HTTP status/schema, request timeout, client retry. |
| Storage Queue | Có cơ chế dequeue retry và poison queue tùy extension. | Max retry, message encoding, xử lý trùng và quan sát poison queue. |
| Service Bus | Message lock/settlement, delivery count, DLQ theo broker/extension. | Session/ordering, lock duration, duplicate detection/idempotency. |
| Event Hubs | Cơ chế xử lý batch/partition và checkpoint theo extension. | Replay, partition ordering, error/retry/throughput. |
| Blob | Retry/phát hiện sự kiện tùy trigger source và extension. | Lưu trạng thái, giới hạn file, tránh phát event vòng lặp. |
| Timer | Tác vụ theo lịch, không có Queue poison-message semantics. | Missed runs, retry phù hợp, idempotent scheduled job. |

**Không có bảo đảm exactly-once chỉ vì dùng Azure Functions hoặc Spring Cloud Function.** Trigger redelivery có thể dẫn tới xử lý lặp. Nếu consumer ghi database, gửi email hoặc gọi API thanh toán, hãy dùng idempotency key ổn định như `eventId` hoặc `orderId + eventVersion` với storage atomic/unique constraint.

Không catch tất cả exception rồi chỉ log và trả thành công với Queue/Service Bus trigger nếu mong Azure retry. Ngược lại, validation error không thể sửa bằng retry vô hạn; cân nhắc dead-letter/quarantine có lý do rõ.

### 14.1. Retry ở đâu?

- **Trong business handler:** retry/backoff có giới hạn với hạ tầng tạm thời.
- **Trong Azure binding extension:** trigger-specific redelivery/poison policies.
- **Ở client HTTP:** caller có thể gửi lại yêu cầu.
- **Ở downstream broker:** event có thể được đưa lại vào queue theo thiết kế.

Tránh để nhiều tầng retry độc lập tạo số lần xử lý vượt xa dự kiến. Đặt timeout/deadline và chỉ rõ tầng sở hữu retry chính.

### 14.2. Quan sát end-to-end

Đối với HTTP → Queue, sinh `eventId` hoặc `requestId` ở ingress, đưa vào payload/message contract để có thể truy vết. Khi log, ưu tiên invocation ID, correlation ID, tên Azure Function, trạng thái và loại lỗi; tránh log function key, connection string hoặc payload riêng tư.

Azure `ExecutionContext` thuộc từng invocation, không nên giữ trong singleton Spring handler. Nếu cần metadata trong function nghiệp vụ, truyền dữ liệu tối thiểu qua domain contract hoặc `Message<T>` được kiểm soát.

## 15. Troubleshooting và quyết định thiết kế

| Triệu chứng | Kiểm tra trước |
| --- | --- |
| Azure Host không thấy `submitOrder` | `@FunctionName`, `@HttpTrigger`, Java method public, Azure plugin và `function.json`. |
| HTTP 404/405 | Route, URL prefix `/api`, HTTP method và host configuration. |
| HTTP 401/403 trên cloud | Function key/authorization level, identity/network settings. |
| `FunctionCatalog` không inject được | `spring-cloud-function-adapter-azure`, Spring main class, auto-configuration/BOM. |
| `catalog.lookup(...)` không trả function | Tên bean, composition, generic types và component scan. |
| HTTP 202 nhưng queue trống | Output binding, Storage connection, extension, logs, permissions; không chỉ đọc response. |
| Queue Trigger không chạy | Sai queue name/connection, thiếu extension, encoding, host đang dừng. |
| Message liên tục retry | Handler ném exception, validation chưa phân loại, poison queue policy. |
| `@BlobInput` trả lỗi | Path expression, file không tồn tại, storage permissions hoặc dataType. |
| Timer không chạy đúng giờ | NCRONTAB, UTC/timezone, host state, plan và schedule monitoring. |
| Event Hubs chỉ xử lý một số event | Consumer group/partition, batch/cardinality, checkpoint, handler errors. |
| Dữ liệu bị xử lý hai lần | Retry/redelivery, duplicate messages, thiếu idempotency. |
| Local chạy cloud lỗi Java version | JDK target và Azure Functions Java runtime không khớp. |
| Azure Worker không tải JAR | Boot executable fat JAR sai layout, thiếu Azure plugin output/dependencies. |

### Lựa chọn kiến trúc nhanh

- Muốn client **nhận kết quả ngay**: HTTP Trigger trả `HttpResponseMessage` chứa kết quả từ `Function<T,R>`, với timeout và validation rõ.
- Muốn **nhận request rồi xử lý nền**: HTTP Trigger + Queue Output + Queue Trigger; trả 202 và cung cấp trạng thái qua API/event khi cần.
- Muốn **đẩy event theo lịch**: Timer Trigger gọi `Supplier.get()` + output binding.
- Muốn **kích hoạt theo file**: Blob Trigger. Muốn **đọc file cho một event khác**: Queue Trigger + Blob Input.
- Muốn xử lý **message broker features**: Service Bus. Muốn xử lý **luồng sự kiện số lượng lớn**: Event Hubs.
- Muốn áp dụng **nhiều EIP** giữa các bước: có thể kết hợp Spring Integration/Stream, nhưng tránh đưa framework không cần thiết vào Azure Function gây tăng cold start.

## 16. Bài tập và câu hỏi tự đánh giá

### Bài tập

1. Thay `trimCode|upperCode` bằng hai business functions nhận/trả Java records; bổ sung JSON validation ở HTTP handler.
2. Thêm một `eventId` vào message trước khi ghi `order-work`; viết consumer idempotent bằng unique key trong storage.
3. Chuyển phương thức `processOrder` sang Service Bus Trigger, so sánh connection, DLQ và settlement semantics.
4. Viết một Timer Trigger gọi `Supplier<String>` để tạo heartbeat và dùng Queue Output. Kiểm tra việc gửi lặp khi cùng dữ liệu được phát nhiều lần.
5. Tạo Queue Trigger nhận tên file và `@BlobInput` đọc nội dung. Giải thích vì sao Blob Input không tự kích hoạt.
6. Cố ý cấu hình sai `AzureWebJobsStorage` rồi quan sát sự khác biệt giữa lỗi host startup, lỗi output binding và lỗi FunctionCatalog.
7. Bổ sung test với body rỗng, duplicate queue event, retry và permission failure.
8. Xem Azure plugin staging metadata, ghi lại số lượng trigger, input/output bindings trên từng Azure Function.

### Tự đánh giá

- Một Azure Function có thể có bao nhiêu triggers? Có bao nhiêu input/output bindings?
- Vì sao `@QueueOutput` không phải `@QueueTrigger`?
- Khi HTTP handler trả 202, điều đó có khẳng định Queue Trigger đã xử lý xong không?
- Vì sao `Supplier<T>` không tự thành Timer Trigger?
- Khi nào dùng `@BlobTrigger` và khi nào dùng `@BlobInput`?
- Azure Storage Queue khác Service Bus Queue ở những điểm vận hành nào?
- Ai tạo `function.json` và vì sao Spring `@Bean` không đủ để Azure discover một function?
- Tại sao cần idempotency khi Queue/Service Bus/Event Hubs có thể giao lại event?
- Khi nào cần chuyển từ `Function<String,String>` sang `Function<OrderRequest,OrderDecision>`?
- Những kiểm thử nào cần chạy ngoài unit test để xác nhận pipeline đa trigger hoạt động đúng?

## 17. Nguồn tham khảo chính thức

- [Spring Cloud Function — Microsoft Azure Functions](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): Azure adapter, `@Component`, handler annotations, `FunctionCatalog`, đóng gói và chạy local.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `Supplier`, `Function`, `Consumer`, composition và conversion.
- [Microsoft Learn — Triggers and Bindings](https://learn.microsoft.com/en-us/azure/azure-functions/functions-triggers-bindings): bảng những trigger/input/output bindings được hỗ trợ.
- [Microsoft Learn — Java Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-java): `@FunctionName`, `ExecutionContext`, metadata và Java annotations.
- [Microsoft Learn — HTTP Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-http-webhook-trigger): route, request/response và authorization.
- [Microsoft Learn — Azure Storage Queue Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-queue-trigger) và [Queue Output](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-queue-output): Queue Trigger, `OutputBinding<T>`, retry và encoding.
- [Microsoft Learn — Timer Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-timer): NCRONTAB, timezone, schedule monitoring và lỗi.
- [Microsoft Learn — Blob Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-blob-trigger) và [Blob Input](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-blob-input): phát hiện tệp và đọc dữ liệu bổ sung.
- [Microsoft Learn — Event Hubs Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-event-hubs-trigger): partition, consumer group và cardinality.
- [Microsoft Learn — Service Bus Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-service-bus-trigger) và [Service Bus Output](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-service-bus-output): queue/topic, retry, settlement và dead-letter.
- [Microsoft Learn — Error Handling and Retries](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-error-pages): các chính sách retry và annotation được runtime hỗ trợ.
- [Microsoft Learn — Java Output Binding to Azure Storage](https://learn.microsoft.com/en-us/azure/azure-functions/functions-add-output-binding-storage-queue-java): ví dụ Java `@QueueOutput` + `OutputBinding<String>`.

**Kết luận:** **Trigger** quyết định **khi nào** Azure Function chạy, **input binding** cung cấp dữ liệu bổ sung và **output binding** đưa kết quả ra hệ thống ngoài. Với **`spring-cloud-function-adapter-azure`**, Spring component handlers dùng `FunctionCatalog` để gọi lại `Supplier`, `Function` hoặc `Consumer` độc lập giao thức; cùng một hàm có thể phục vụ HTTP, Storage Queue, Event Hubs, Service Bus, Timer hoặc Blob. Thiết kế từng ranh giới rõ ràng, xác định quy tắc kết nối, serialization, retry, idempotency và kiểm thử host thực tế là điều kiện để hệ thống serverless vận hành an toàn.
