# Truy cập ExecutionContext qua AzureFunctionUtil

## 1. Bài toán và mục tiêu

**Spring Cloud Function (SCF)** khuyến khích viết các hàm nghiệp vụ theo mô hình `Supplier<T>`, `Function<T,R>`, `Consumer<T>`, tra cứu qua `FunctionCatalog` và ghép (*composition*) để tái sử dụng cùng logic khi ứng dụng được gọi qua HTTP, sự kiện hay một nền tảng serverless. Trong module **SPRING_CLOUD_FUNCTION**, điều quan trọng là **không gắn chặt quy tắc nghiệp vụ vào giao thức gọi**.

Khi triển khai ứng dụng đó lên **Azure Functions**, mỗi lời gọi có một đối tượng riêng của Azure Java runtime: `com.microsoft.azure.functions.ExecutionContext`. Đối tượng này giúp lấy **invocation ID**, **function name**, **logger** và một số thông tin trace. Nhưng một bean Spring như `Function<String,String>` không tự có tham số `ExecutionContext` như Azure `@FunctionName` handler.

Để kết nối hai thế giới, Spring Cloud Function Azure adapter cung cấp tiện ích **`AzureFunctionUtil.enhanceInputIfNecessary(input, context)`**. Tiện ích đưa `ExecutionContext` của invocation vào **header** của Spring `Message<T>`, giúp một function có chữ ký `Function<Message<T>,R>` đọc ngữ cảnh khi cần.

Bài học tập trung vào những câu hỏi:

1. `ExecutionContext` là gì, có gì khác HTTP request, Spring `ApplicationContext` và `FunctionCatalog`?
2. Vì sao không nên inject `ExecutionContext` như một Spring singleton hoặc lưu nó trong field của handler?
3. `AzureFunctionUtil.enhanceInputIfNecessary` làm nhiệm vụ gì? Header `AzureFunctionUtil.EXECUTION_CONTEXT` được đọc ra sao?
4. Khi nào function cần `Message<T>` và khi nào nên để function nhận payload `T` thuần?
5. Làm sao giữ `FunctionCatalog`, conversion, correlation/tracing, logging và test đúng ranh giới?
6. Làm sao kiểm chứng trên Azure HTTP Trigger, Queue Trigger và trên một Spring context không có Azure runtime?

Kết quả cuối cùng là một ví dụ Java gồm **business service thuần**, **function nhận Spring Message**, **Azure handler** và **bộ test độc lập Azure Host**.

## 2. Phân biệt bốn đối tượng thường bị nhầm

| Đối tượng | Kiểu / package | Ai cấp hoặc quản lý? | Mục đích |
| --- | --- | --- | --- |
| **Azure ExecutionContext** | `com.microsoft.azure.functions.ExecutionContext` | Azure Java Worker theo **từng invocation** | Logger, invocation ID, function name, trace context. |
| **Spring ApplicationContext** | `org.springframework.context.ApplicationContext` | Spring | Quản lý bean, dependency injection, configuration/lifecycle. |
| **FunctionCatalog** | `org.springframework.cloud.function.context.FunctionCatalog` | Spring Cloud Function | Tra cứu/wrap `Supplier`, `Function`, `Consumer` và composition. |
| **Spring Message<T>** | `org.springframework.messaging.Message<T>` | Ứng dụng/adapter/message infrastructure | Mang payload và headers đến function hoặc các tầng messaging. |
| **Azure HttpRequestMessage<T>** | `com.microsoft.azure.functions.HttpRequestMessage<T>` | Azure HTTP binding | Body, method, query, HTTP headers và response builder. |

Một Azure handler có thể nhận đồng thời `HttpRequestMessage<Optional<String>>` và `ExecutionContext`:

~~~java
@FunctionName("normalizeAzureOrder")
public HttpResponseMessage execute(
        @HttpTrigger(
                name = "req",
                methods = {HttpMethod.POST},
                authLevel = AuthorizationLevel.FUNCTION,
                route = "orders/normalize")
        HttpRequestMessage<Optional<String>> request,
        ExecutionContext context) {
    // ...
}
~~~

Đây là chữ ký Azure handler, không phải một `Function<T,R>` bean của Spring.

**Không nhầm:**

- `@FunctionName("normalizeAzureOrder")` đặt tên cho **Azure Function**.
- `@Bean Function<Message<String>,String> normalizeOrderWithContext()` đặt tên cho **Spring functional bean**.
- `catalog.lookup("normalizeOrderWithContext")` tra cứu bean trong mô hình SCF.
- `context.getFunctionName()` trả **tên Azure Function đang thực thi**, không nhất thiết trùng tên bean.
- `context.getInvocationId()` trả **ID lần gọi** do Azure cấp, khác Spring `MessageHeaders.ID` và khác event ID nghiệp vụ.

## 3. ExecutionContext cung cấp những gì?

Theo Azure Java SDK, `ExecutionContext` là một **interface** với những phương thức cốt lõi:

| Phương thức | Giá trị trả về | Cách dùng |
| --- | --- | --- |
| `getInvocationId()` | `String` | Liên kết log/diagnostics của một invocation. |
| `getFunctionName()` | `String` | Phân biệt tên handler Azure được gọi. |
| `getLogger()` | `java.util.logging.Logger` | Ghi log tích hợp với Azure Functions logging/monitoring. |
| `getTraceContext()` | `TraceContext` trong phiên bản API hỗ trợ | Truy cập trace context do runtime cung cấp; kiểm tra giá trị thực tế và SDK đang dùng. |

Ví dụ trong Azure handler:

~~~java
context.getLogger().info(
        "Started function=" + context.getFunctionName()
        + ", invocation=" + context.getInvocationId());
~~~

**Thời gian sống:** context ứng với **lần gọi hiện tại**. Azure Functions Host có thể xử lý nhiều invocations song song và có thể scale ra nhiều process/instances; không giữ context trong một field mutable của Spring singleton rồi dùng ở lời gọi kế tiếp.

### 3.1. Invocation ID, event ID và trace ID khác nhau

~~~text
Azure Function name       normalizeAzureOrder
Azure invocation ID       8f...a9  (do host cấp mỗi lần gọi)
Spring Message ID         UUID do Spring MessageBuilder tạo
Business event ID         evt-order-601-v1 (do producer đặt)
Distributed trace ID      trace context của hạ tầng observability
~~~

Những giá trị này có thể liên hệ nhưng **không thay thế nhau**:

- Khi một Queue message được **giao lại**, Azure có thể tạo invocation mới với invocation ID mới.
- Nếu cùng một sự kiện nghiệp vụ được retry, business event ID nên **giữ ổn định** để hỗ trợ idempotency.
- `getTraceContext()` không tự thay thế cấu hình tracing instrumentation hoặc header propagation xuyên HTTP, Queue, Event Hubs.
- Spring message ID có thể đổi khi tạo message mới; không dùng nó làm khóa chống xử lý trùng nghiệp vụ.

### 3.2. ExecutionContext không cung cấp mọi thứ

`ExecutionContext` **không phải** kho chứa toàn bộ HTTP headers, Queue delivery count, Blob path, access token, transaction state hoặc dữ liệu request. Những metadata ấy nằm ở trigger/binding request, `@BindingName`, SDK khác hoặc adapter tương ứng.

**Không nên chuyển nguyên `ExecutionContext` ra HTTP response hay broker**. Nó là runtime object có logger và tham chiếu tới môi trường thực thi; nếu cần correlation bền vững, chỉ trích xuất các **giá trị** như invocation ID khi phù hợp với contract.

## 4. AzureFunctionUtil chuyển context sang Spring Message như thế nào?

### 4.1. API và hằng số header

Spring Cloud Function Azure adapter cung cấp:

~~~java
AzureFunctionUtil.enhanceInputIfNecessary(input, context)
AzureFunctionUtil.EXECUTION_CONTEXT
~~~

Trong đó:

- `input` là dữ liệu mà handler muốn gửi vào functional layer, chẳng hạn `String` hoặc một Spring `Message<?>` phù hợp.
- `context` là `ExecutionContext` của **invocation hiện tại**.
- Kết quả là đối tượng đầu vào đã được hỗ trợ bổ sung context; trong trường hợp thông dụng **đầu vào payload thuần kèm ExecutionContext**, tài liệu Spring minh họa kết quả là một **Spring `Message`** chứa header.
- `EXECUTION_CONTEXT` là khóa do thư viện công bố; tên header trong tài liệu là **`executionContext`**.

Ví dụ tối giản tương đương tài liệu Spring:

~~~java
Message<?> enriched = (Message<?>)
        AzureFunctionUtil.enhanceInputIfNecessary(
                " dh-601 ", context);

ExecutionContext fromHeader = (ExecutionContext)
        enriched.getHeaders().get(
                AzureFunctionUtil.EXECUTION_CONTEXT);

String payload = (String) enriched.getPayload();
~~~

**Không dùng chuỗi literal `"executionContext"` rải khắp project khi đã có constant**. Hằng số vừa diễn đạt ý định vừa giảm sai chính tả khi đọc/ghi header.

### 4.2. Sơ đồ đường đi

~~~mermaid
sequenceDiagram
    participant Azure as Azure Java Worker
    participant Handler as @Component @FunctionName
    participant Util as AzureFunctionUtil
    participant Catalog as FunctionCatalog
    participant Business as Function<Message<String>,String>
    Azure->>Handler: request + ExecutionContext
    Handler->>Util: enhanceInputIfNecessary(body, context)
    Util-->>Handler: Message(payload, executionContext header)
    Handler->>Catalog: lookup("normalizeOrderWithContext")
    Catalog-->>Handler: function representation
    Handler->>Business: apply(Message<String>)
    Business->>Business: read header / log / normalize payload
    Business-->>Handler: "DH-601"
    Handler-->>Azure: HttpResponseMessage 200
~~~

### 4.3. Vì sao tên phương thức là enhanceInputIfNecessary?

Tên API nhấn mạnh đây là **một bước tăng cường đầu vào khi cần**, không phải serializer hay một cơ chế kích hoạt Azure. Hãy dựa vào hợp đồng **phiên bản adapter cụ thể** và test kiểu kết quả tại boundary; không giả định hàm này biến JSON, POJO, Azure HTTP request hoặc Azure Queue message thành mọi kiểu nghiệp vụ.

Một vấn đề khác: các docs có ví dụ ép kiểu `(Message)` vì input ban đầu có thể chỉ là `String`. Để tránh unchecked casts không kiểm soát, trong ứng dụng ta nên kiểm tra payload kiểu mong đợi tại boundary hoặc duy trì contract có kiểu rõ.

### 4.4. So sánh với MessageBuilder thủ công

Nếu chỉ muốn làm rõ envelope trong một unit test hoặc một adapter tự viết, có thể tạo Spring message thủ công:

~~~java
Message<String> message = MessageBuilder
        .withPayload(" dh-601 ")
        .setHeader(AzureFunctionUtil.EXECUTION_CONTEXT, context)
        .build();
~~~

Đoạn này dùng `org.springframework.messaging.support.MessageBuilder`. Nó minh họa rõ **dữ liệu nằm ở payload** và **ExecutionContext nằm ở header**. Tuy nhiên, trong Azure handler thực tế, dùng `AzureFunctionUtil.enhanceInputIfNecessary(...)` giúp theo quy ước adapter được Spring Cloud Function công bố.

Nếu đã có `Message<String>` và muốn giữ các header khác:

~~~java
Message<String> enriched = MessageBuilder
        .fromMessage(originalMessage)
        .setHeader(AzureFunctionUtil.EXECUTION_CONTEXT, context)
        .build();
~~~

Lưu ý message được xây lại có thể sinh Spring message ID/timestamp mới. Test nên kiểm tra **các header thuộc hợp đồng ứng dụng** thay vì giả định mọi metadata hệ thống bất biến.

## 5. Dependency và chọn mô hình adapter đúng

### 5.1. Mảnh dependency Maven

Giả sử project đã có Spring Boot parent, Spring Cloud BOM tương thích và Java 17+:

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

`spring-cloud-function-adapter-azure` đưa khả năng integration Spring/SCF vào Azure Java Worker, bao gồm `AzureFunctionUtil`. `azure-functions-java-library` chứa `ExecutionContext` và Azure trigger/binding APIs.

`1.3.1` của Azure Java library là **mốc minh họa trong tài liệu API Microsoft**, không phải lời khẳng định đây là phiên bản mới nhất. Đối chiếu template, Java runtime và release train trước khi khóa phiên bản. Spring Cloud Function adapter từ **4.0.0+** hỗ trợ mô hình `@Component`/`@FunctionName`; dùng cùng dòng với `spring-cloud-function-context` do BOM quản lý.

`spring-cloud-function-context` thường là dependency bắc cầu cung cấp `FunctionCatalog`. Với dependency management sai hoặc thiếu adapter, import `AzureFunctionUtil` có thể không tồn tại trên classpath.

### 5.2. Gradle tương ứng

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-adapter-azure'
    implementation 'com.microsoft.azure.functions:azure-functions-java-library:1.3.1'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Cần Spring Boot/Spring Cloud dependency management phù hợp. Azure Gradle plugin `com.microsoft.azure.azurefunctions` hoặc Azure Maven plugin `com.microsoft.azure:azure-functions-maven-plugin` dùng để tạo binding metadata/package; chúng **khác** adapter runtime.

### 5.3. So sánh theo phiên bản SCF

| Dòng tài liệu | Cách đưa ExecutionContext vào function | Ghi chú |
| --- | --- | --- |
| **SCF 4.x/5.x Azure adapter hiện đại** | Handler `@Component` nhận `ExecutionContext` từ Azure, gọi `AzureFunctionUtil.enhanceInputIfNecessary`, function đọc header. | Hướng bài học này dựa trên tài liệu chính thức hiện hành. |
| **Một số hướng dẫn SCF 3.x cũ** | `FunctionInvoker` có thể tự đưa context vào message hoặc mô tả cách đăng ký context với Spring. | **Không áp dụng nguyên xi** vào project mới; `FunctionInvoker` đã deprecated. |
| **Azure Web Adapter** | Ứng dụng Spring Web được triển khai thông qua HTTP trigger do adapter che đi. | Không mặc định có cùng handler `@FunctionName`/`enhanceInputIfNecessary` tùy chỉnh. |

**Lưu ý:** Không inject `ExecutionContext` như `@Autowired private ExecutionContext context` trong Spring singleton dựa vào một tutorial cũ. Với hiện đại SCF Azure adapter, phương thức Azure handler nhận context **từ invocation** và truyền nó vào Spring `Message` khi cần.

## 6. Ví dụ hoàn chỉnh: nghiệp vụ thuần và function message-aware

Bài toán: HTTP POST nhận mã đơn dạng text. Ứng dụng chuẩn hóa mã rồi ghi log bằng logger gắn với **Azure invocation hiện tại**.

~~~text
POST /api/orders/context
Body:  " dh-601 "

Azure handler:
    request.getBody() -> String
    AzureFunctionUtil.enhanceInputIfNecessary(..., ExecutionContext)
    -> Message<String> + executionContext header
    -> FunctionCatalog.lookup("normalizeOrderWithContext")
    -> Function<Message<String>,String>

Response: "DH-601"
Log: function name và invocation ID (không log secret/body nhạy cảm)
~~~

### 6.1. Service nghiệp vụ không phụ thuộc Azure

Tạo `src/main/java/example/azure/OrderCodeService.java`:

~~~java
package example.azure;

import java.util.Locale;

import org.springframework.stereotype.Service;

@Service
public class OrderCodeService {

    public String normalize(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException(
                    "Mã đơn không được rỗng");
        }

        return raw.strip().toUpperCase(Locale.ROOT);
    }
}
~~~

Đây là thành phần **thuần nghiệp vụ**: không import `ExecutionContext`, `Message` hay bất kỳ Azure SDK type nào. Vì vậy có thể tái sử dụng khi một HTTP Trigger, Queue Trigger, Spring Integration flow hoặc serverless adapter khác cùng cần chuẩn hóa mã đơn.

### 6.2. Spring Boot application và function đọc context từ header

Tạo `src/main/java/example/azure/AzureOrderApplication.java`:

~~~java
package example.azure;

import java.util.function.Function;

import com.microsoft.azure.functions.ExecutionContext;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.function.adapter.azure.AzureFunctionUtil;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;

@SpringBootApplication
public class AzureOrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(AzureOrderApplication.class, args);
    }

    @Bean
    public Function<Message<String>, String> normalizeOrderWithContext(
            OrderCodeService orderCodes) {

        return message -> {
            ExecutionContext azureContext = (ExecutionContext)
                    message.getHeaders().get(
                            AzureFunctionUtil.EXECUTION_CONTEXT);

            if (azureContext != null) {
                azureContext.getLogger().info(
                        "Normalize order: function="
                        + azureContext.getFunctionName()
                        + ", invocation="
                        + azureContext.getInvocationId());
            }

            // Nghiệp vụ thực sự không phụ thuộc Azure.
            return orderCodes.normalize(message.getPayload());
        };
    }
}
~~~

**Giải thích chi tiết:**

1. `normalizeOrderWithContext` là một bean `Function<Message<String>,String>`, khác với `Function<String,String>` chỉ nhận payload.
2. Function lấy `ExecutionContext` từ `message.getHeaders()` bằng **`AzureFunctionUtil.EXECUTION_CONTEXT`**, không lấy từ một bean singleton.
3. Trong unit tests, môi trường ngoài Azure hoặc một adapter khác, header có thể không có. Mẫu này **chấp nhận `null` và vẫn chạy nghiệp vụ**, giúp logic có thể tái sử dụng.
4. Bước normalization thuộc `OrderCodeService`. Việc log Azure function/invocation ID là **adapter-aware concern** và có thể được chuyển sang handler nếu muốn function hoàn toàn không phụ thuộc Azure.
5. Không lưu `azureContext` trong field của service, function closure hay static variable sau khi lời gọi kết thúc.
6. Function trả `String`, không trả `ExecutionContext` hoặc toàn bộ `Message` cho HTTP client.

Nếu muốn tách biệt mạnh hơn, hãy dùng một interceptor/adapter logging trước khi gọi `Function<String,String>`. Bài này cố tình dùng **message-aware function** vì mục tiêu là hiểu cách truy cập ExecutionContext **qua AzureFunctionUtil**.

### 6.3. Vì sao dùng FunctionCatalog trong ví dụ?

`FunctionCatalog` đưa các function beans vào mô hình canonical của SCF, hỗ trợ composition, wrapper/type conversion trong phạm vi được hỗ trợ. Handler sẽ tra cứu `normalizeOrderWithContext` theo tên:

~~~java
Function<Message<String>, String> normalize =
        catalog.lookup("normalizeOrderWithContext");
~~~

Đây là **Spring function name**, không phải tên Azure `@FunctionName`. Nếu chỉ inject raw `Function<Message<String>,String>` trực tiếp, code có thể vẫn xử lý đúng Message được truyền; tuy nhiên catalog phù hợp với mục tiêu module là tái sử dụng function definition qua nhiều adapters.

## 7. Azure HTTP handler sử dụng AzureFunctionUtil

Tạo `src/main/java/example/azure/OrderAzureHandler.java`:

~~~java
package example.azure;

import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;
import java.util.logging.Level;

import com.microsoft.azure.functions.AuthorizationLevel;
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.HttpMethod;
import com.microsoft.azure.functions.HttpRequestMessage;
import com.microsoft.azure.functions.HttpResponseMessage;
import com.microsoft.azure.functions.HttpStatus;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.HttpTrigger;

import org.springframework.cloud.function.adapter.azure.AzureFunctionUtil;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class OrderAzureHandler {

    private final Function<Message<String>, String> normalize;

    public OrderAzureHandler(FunctionCatalog catalog) {
        this.normalize = Objects.requireNonNull(
                catalog.lookup("normalizeOrderWithContext"),
                "Không tìm thấy normalizeOrderWithContext");
    }

    @FunctionName("normalizeAzureOrder")
    public HttpResponseMessage normalize(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION,
                    route = "orders/context")
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        String raw = request.getBody().orElse("");
        if (raw.isBlank()) {
            return request
                    .createResponseBuilder(HttpStatus.BAD_REQUEST)
                    .body("Mã đơn không được rỗng")
                    .build();
        }

        try {
            Object input =
                    AzureFunctionUtil.enhanceInputIfNecessary(
                            raw, context);

            // Với payload String và ExecutionContext,
            // API hiện hành trả về Spring Message.
            if (!(input instanceof Message<?> message)
                    || !(message.getPayload() instanceof String)) {
                throw new IllegalStateException(
                        "Không tạo được Message<String>");
            }

            @SuppressWarnings("unchecked")
            Message<String> typed = (Message<String>) message;

            String normalized = normalize.apply(typed);

            return request
                    .createResponseBuilder(HttpStatus.OK)
                    .header("Content-Type",
                            "text/plain; charset=utf-8")
                    .body(normalized)
                    .build();
        }
        catch (RuntimeException error) {
            // Wrapper có thể bọc IllegalArgumentException.
            Throwable root = error;
            while (root.getCause() != null
                    && root.getCause() != root) {
                root = root.getCause();
            }
            if (root instanceof IllegalArgumentException) {
                return request
                        .createResponseBuilder(HttpStatus.BAD_REQUEST)
                        .body("Dữ liệu đơn không hợp lệ")
                        .build();
            }

            context.getLogger().log(
                    Level.SEVERE, "Normalize order failed", error);

            return request
                    .createResponseBuilder(
                            HttpStatus.INTERNAL_SERVER_ERROR)
                    .body("Không thể xử lý yêu cầu")
                    .build();
        }
    }
}
~~~

**Điểm quan trọng của handler:**

- `@Component` khiến Spring quản lý handler và inject `FunctionCatalog`.
- `@FunctionName("normalizeAzureOrder")` là **Azure Function** mà Azure Java Worker discover.
- `@HttpTrigger` khai báo POST, route và authorization policy.
- `ExecutionContext context` được **Azure cấp cho mỗi invocation**.
- `AzureFunctionUtil.enhanceInputIfNecessary(raw, context)` là **ranh giới truyền runtime context vào Spring Message**.
- `normalize.apply(typed)` gọi function có hợp đồng `Message<String> → String`.
- Handler chuyển validation errors thành HTTP 400 và lỗi khác thành 500; catalog không tự quyết định HTTP status.
- Không trả trực tiếp runtime context, stack trace hoặc nội dung header nhạy cảm cho caller.

Với `AuthorizationLevel.FUNCTION`, Azure Function App cloud yêu cầu function/host key theo cấu hình host. **Function key không thay thế đầy đủ authentication/authorization** của API nhạy cảm. Local Core Tools có thể xử lý key khác cloud, nên test bảo mật riêng trên môi trường triển khai.

### 7.1. Trường hợp không cần ExecutionContext

Nếu không có yêu cầu dùng logger/trace context từ Azure trong functional layer, cách đơn giản hơn là:

~~~java
@Bean
Function<String, String> normalizeOrder(
        OrderCodeService orderCodes) {
    return orderCodes::normalize;
}
~~~

Azure handler có thể inject function hoặc `catalog.lookup("normalizeOrder")` và gọi `apply(raw)` mà **không gọi AzureFunctionUtil**. Đây là thiết kế thường tốt hơn khi muốn logic hoàn toàn độc lập môi trường. Dùng `Message<T>` chỉ khi metadata thực sự là một phần của hợp đồng của function.

### 7.2. Tại sao không inject ExecutionContext bằng constructor?

Đoạn sau là **phản ví dụ** trong Spring component singleton:

~~~java
@Component
class UnsafeHandler {
    @Autowired
    private ExecutionContext currentContext; // Không nên làm.
}
~~~

Nó giả định Azure runtime context là bean Spring lâu dài, trong khi lifecycle thật là **mỗi invocation**. Cách đúng trong mẫu adapter mới là nhận `ExecutionContext` ở phương thức `@FunctionName` rồi chuyển vào Message nếu cần.

### 7.3. Kiểm tra header tại boundary

Trong lúc phát triển có thể xác minh:

~~~java
Message<?> enhanced = (Message<?>)
        AzureFunctionUtil.enhanceInputIfNecessary(
                " dh-601 ", context);

Object attached = enhanced.getHeaders().get(
        AzureFunctionUtil.EXECUTION_CONTEXT);

if (attached != context) {
    throw new IllegalStateException(
            "Thiếu ExecutionContext của invocation");
}
~~~

Đây là **đoạn chẩn đoán/test**, không nên đặt identity check vào business logic production. Hãy dùng test để kiểm tra input contract khi nâng major version SCF.


## 8. Khi nào truyền context qua Message?

Có ba chiến lược với cùng một nghiệp vụ:

| Chiến lược | Nơi xử lý metadata | Chữ ký function | Phù hợp khi |
| --- | --- | --- | --- |
| **A. Ghi log tại handler** | Azure `@FunctionName` method | `Function<String,String>` | Chỉ cần log invocation ở ranh giới Azure. |
| **B. Sử dụng AzureFunctionUtil** | Function message-aware | `Function<Message<String>,String>` | Function thực sự cần logger/invocation ID. |
| **C. Trích xuất DTO trung lập** | Handler chuyển Azure context thành giá trị | `Function<OrderRequest,R>` | Cần correlation nhưng không muốn domain phụ thuộc Azure. |

**A — Logger ở handler:**

~~~java
context.getLogger().info(
        "Start invocation " + context.getInvocationId());
String normalized = orderCodes.normalize(raw);
~~~

Chọn phương án A khi không có lý do để business function phải nhận `Message<T>`.

**B — Context qua Spring Message:**

~~~java
Message<?> enriched = (Message<?>)
        AzureFunctionUtil.enhanceInputIfNecessary(raw, context);
Object azure = enriched.getHeaders().get(
        AzureFunctionUtil.EXECUTION_CONTEXT);
~~~

Đây là phương án bài học minh họa xuyên suốt. Nó không có nghĩa mọi function trong catalog tự động nhận header nếu adapter không truyền.

**C — Chỉ chuyển dữ liệu correlation:**

~~~java
record InvocationInfo(String correlationId, String sourceSystem) {}

record OrderRequest(String code, InvocationInfo invocation) {}
~~~

Handler có thể tạo `new InvocationInfo(context.getInvocationId(), "AZURE")` rồi truyền vào `Function<OrderRequest,R>`. Azure SDK không cần xuất hiện trong business function. Chọn cách này nếu metadata thực sự là một phần của application contract.

**Quy tắc:** Không dùng `AzureFunctionUtil` chỉ vì nó có sẵn. Chỉ chuyển runtime object khi một function cần nó, và giữ một tầng nghiệp vụ độc lập Azure.

## 9. Header propagation và an toàn dữ liệu

### 9.1. Header chứa Java object, không phải JSON

Sau helper, thông điệp được hiểu như:

~~~text
Message<String>
  payload: " dh-601 "
  headers:
    id: [Spring message ID]
    timestamp: [Spring message timestamp]
    executionContext: [Azure ExecutionContext Java object]
~~~

`executionContext` chứa một runtime object trong **cùng process**, không phải một chuỗi có thể chuyển qua Kafka, Service Bus, Event Hubs hay HTTP.

Khi phát event ra ngoài, nên tạo message mới chỉ mang những scalar metadata được phép:

~~~java
Message<String> outbound = MessageBuilder
        .withPayload(normalized)
        .setHeader("businessCorrelationId", businessId)
        .build();
~~~

`normalized` và `businessId` là các biến giá trị được ứng dụng tính/validate. Không chuyển nguyên `ExecutionContext` ra broker hoặc lưu object này vào database.

### 9.2. Dùng business event ID khác invocation ID

Một Queue message được giao lại có thể có **Azure invocation ID mới**. Business event ID nên ổn định khi retry:

~~~text
Business event ID:  evt-order-601-v1
Invocation A:       inv-123
Invocation B:       inv-987 (retry cùng event)
~~~

Dùng business event ID/idempotency key với storage bền vững, có unique constraint hoặc atomic operation. `context.getInvocationId()` phù hợp cho **log một lần thực thi**, không phải mặc định làm khóa chống xử lý trùng.

### 9.3. Loại Azure header trước khi rời process

~~~java
Message<String> safe = MessageBuilder
        .fromMessage(internalMessage)
        .removeHeader(AzureFunctionUtil.EXECUTION_CONTEXT)
        .build();
~~~

`internalMessage` là message trong flow. Việc bỏ header Azure chỉ là bước đầu: các header còn lại vẫn cần outbound mapper/allowlist. Tuyệt đối tránh ghi log function key, token, Authorization header, cookies, connection strings hoặc payload riêng tư.

### 9.4. Khi function composition thay đổi kiểu

Nếu một function `Function<Message<String>,String>` trả String, bước sau không mặc nhiên còn nhìn thấy Azure context. SCF wrapper, Spring Integration transformer và outbound adapter có thể có cơ chế metadata propagation riêng.

Khi downstream cần correlation, hãy thiết kế `Message<T>` hoặc DTO có hợp đồng rõ và kiểm thử tại ranh giới thực. Không giả định mọi header đi qua mọi kiểu conversion.

### 9.5. Azure HTTP headers và Spring Message headers

`request.getHeaders()` thuộc Azure HTTP binding; `message.getHeaders()` thuộc Spring Messaging. `AzureFunctionUtil.enhanceInputIfNecessary` truyền context, **không có nghĩa đã copy và validate toàn bộ HTTP headers**. Khi cần trace context xuyên dịch vụ, cần header mapping và instrumentation riêng, theo từng transport.

## 10. Lỗi, retry và lifecycle

**`AzureFunctionUtil` chỉ mang context, không xử lý lỗi tự động.**

| Bối cảnh | Hành vi khi exception | Cần thiết kế |
| --- | --- | --- |
| HTTP Trigger | Handler/runtime map HTTP status. | 4xx/5xx schema, timeout, client retry. |
| Storage Queue Trigger | Host/extension có retry/poison queue. | Idempotency, max retry, quarantine. |
| Service Bus Trigger | Message settlement, lock/delivery và DLQ. | Broker retry policy, duplicate handling. |
| Timer Trigger | Tác vụ lịch thất bại. | Checkpoint, missed schedule và recovery. |
| SCF FunctionCatalog | Wrapper có thể bọc lỗi business. | Phân loại lỗi domain, kiểm root cause. |

### 10.1. Context bị thiếu: policy optional hay required?

Trong ví dụ mục 6, function bỏ qua Azure logging khi header vắng; business service vẫn hoạt động. Điều này phù hợp khi function được gọi từ unit test hoặc serverless adapter khác.

Nếu application bắt buộc ghi audit theo Azure invocation, cần **required policy**: validation tại boundary và fail fast. Không lặng lẽ bỏ một sự kiện audit bắt buộc.

Nếu header có thể được tạo từ nguồn ngoài, kiểm tra kiểu trước khi dùng:

~~~java
Object candidate = message.getHeaders().get(
        AzureFunctionUtil.EXECUTION_CONTEXT);

if (candidate instanceof ExecutionContext azureContext) {
    azureContext.getLogger().info("Azure invocation");
}
~~~

Đây là biến thể an toàn hơn phép cast trực tiếp trong function demo, đặc biệt khi message đi vào từ nhiều adapter.

### 10.2. Không lưu context trong singleton hoặc async job

Không giữ `ExecutionContext` trong field mutable của Spring `@Component`, `@Service` hoặc static variable. Azure có thể xử lý nhiều invocation song song và scale ra nhiều worker instances.

Nếu tách một tác vụ chạy sau khi invocation kết thúc, hãy **chụp các giá trị String** như invocation ID/correlation ID vào DTO của job thay vì giữ nguyên runtime context object:

~~~java
String invocationId = context.getInvocationId();
String functionName = context.getFunctionName();
// Đưa scalar values vào job metadata, không chuyển context.
~~~

Không dựa vào `ThreadLocal` hoặc `ExecutionContext` của một invocation đã kết thúc để logging công việc được phát sang hệ thống khác.

### 10.3. Context không là giải pháp tracing tự động

`getLogger()` tích hợp logging Azure, `getInvocationId()` giúp điều tra một invocation, `getTraceContext()` cung cấp trace context theo SDK/runtime. Tuy nhiên, distributed tracing giữa HTTP, Queue, Service Bus và Event Hubs đòi hỏi **instrumentation và propagation** theo giao thức. Log có invocation ID không đồng nghĩa mọi request đã có end-to-end trace.

## 11. Queue và Timer Trigger có dùng AzureFunctionUtil được không?

### 11.1. Queue Trigger

Phương thức **mở rộng tùy chọn** trong `OrderAzureHandler` dùng lại field `normalize` từ mục 7:

~~~java
@FunctionName("normalizeQueuedOrder")
public void normalizeQueuedOrder(
        @QueueTrigger(
                name = "order",
                queueName = "orders-input",
                connection = "AzureWebJobsStorage")
        String orderCode,

        @QueueOutput(
                name = "result",
                queueName = "orders-output",
                connection = "AzureWebJobsStorage")
        OutputBinding<String> output,

        ExecutionContext context) {

    Message<?> enriched = (Message<?>)
            AzureFunctionUtil.enhanceInputIfNecessary(
                    orderCode, context);

    if (!(enriched.getPayload() instanceof String)) {
        throw new IllegalArgumentException("Sai Queue payload");
    }

    @SuppressWarnings("unchecked")
    Message<String> typed = (Message<String>) enriched;

    output.setValue(normalize.apply(typed));
}
~~~

Cần imports `com.microsoft.azure.functions.OutputBinding`, `com.microsoft.azure.functions.annotation.QueueTrigger` và `QueueOutput`. Để chạy cần Azure Storage queues, extension và connection settings tương thích.

Queue redelivery có thể tạo invocation ID mới. `OutputBinding.setValue(...)` không bảo đảm transaction phân tán hoặc exactly-once với database và downstream. Không catch mọi exception rồi return thành công nếu hệ thống cần Azure retry.

### 11.2. Timer Trigger

~~~java
@FunctionName("scheduledDiagnostics")
public void scheduledDiagnostics(
        @TimerTrigger(
                name = "timer",
                schedule = "0 */5 * * * *")
        String timerInfo,

        ExecutionContext context) {

    context.getLogger().info(
            "Timer invocation=" + context.getInvocationId());
}
~~~

Đây là phương thức minh họa riêng, cần import `TimerTrigger`. Chỉ log tại handler **không cần helper**. Khi Timer handler gọi một function message-aware và function cần Azure context, khi đó mới dùng `AzureFunctionUtil`. Một bean `Supplier<T>` không tự tạo lịch; Azure Trigger mới điều phối việc gọi theo NCRONTAB.

### 11.3. Service Bus và Event Hubs

Tương tự, Azure handler nhận event và ExecutionContext, chuyển payload đúng type, gọi helper nếu function cần context, sau đó xử lý output phù hợp. Ack/checkpoint/retry/DLQ do binding extension và broker quyết định, không phải do Spring header `executionContext`.

## 12. Unit test AzureFunctionUtil

### 12.1. Test double cho ExecutionContext

Tạo `src/test/java/example/azure/TestExecutionContexts.java`:

~~~java
package example.azure;

import java.util.logging.Logger;
import com.microsoft.azure.functions.ExecutionContext;

final class TestExecutionContexts {

    static ExecutionContext withInvocationId(String id) {
        return new ExecutionContext() {
            @Override
            public String getInvocationId() {
                return id;
            }

            @Override
            public String getFunctionName() {
                return "normalizeAzureOrder";
            }

            @Override
            public Logger getLogger() {
                return Logger.getLogger("azure-context-test");
            }
        };
    }

    private TestExecutionContexts() {}
}
~~~

`getTraceContext()` là default method trên những phiên bản Azure Java library hỗ trợ nên test double không cần override nếu không dùng; cần đối chiếu SDK của dự án.

### 12.2. Test context được gắn đúng header

Tạo `src/test/java/example/azure/AzureFunctionUtilTest.java`:

~~~java
package example.azure;

import com.microsoft.azure.functions.ExecutionContext;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.function.adapter.azure.AzureFunctionUtil;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;

class AzureFunctionUtilTest {

    @Test
    void attachesSameContextToMessage() {
        ExecutionContext context =
                TestExecutionContexts.withInvocationId("inv-test-601");

        Message<?> message = (Message<?>)
                AzureFunctionUtil.enhanceInputIfNecessary(
                        " dh-601 ", context);

        assertEquals(" dh-601 ", message.getPayload());
        assertSame(context,
                message.getHeaders().get(
                        AzureFunctionUtil.EXECUTION_CONTEXT));
    }
}
~~~

`assertSame` phù hợp **ở test này**, bởi ta kiểm tra reference của context object được gắn trong cùng Java process, không phải xác minh Spring `FunctionCatalog` wrapper có giữ nguyên bean identity.

### 12.3. Unit test service không cần Azure

~~~java
OrderCodeService service = new OrderCodeService();

assertEquals("DH-601", service.normalize(" dh-601 "));
assertThrows(IllegalArgumentException.class,
        () -> service.normalize("   "));
~~~

Test này chứng minh nghiệp vụ độc lập Azure Worker và function context.


## 13. Kiểm thử Spring context và FunctionCatalog

Unit test `AzureFunctionUtil` chứng minh khả năng gắn context vào Message. Để kiểm tra function được đăng ký và hoạt động khi gọi qua catalog, sử dụng Spring Boot test.

Tạo `src/test/java/example/azure/AzureContextCatalogTest.java`:

~~~java
package example.azure;

import java.util.function.Function;

import com.microsoft.azure.functions.ExecutionContext;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.adapter.azure.AzureFunctionUtil;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = AzureOrderApplication.class)
class AzureContextCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    OrderAzureHandler handler;

    @Test
    void handlerAndFunctionExistInSpringContext() {
        assertNotNull(handler);
        assertNotNull(
                catalog.lookup("normalizeOrderWithContext"));
    }

    @Test
    void catalogFunctionReceivesAzureHeader() {
        ExecutionContext context =
                TestExecutionContexts.withInvocationId("inv-test-602");

        Message<?> enriched = (Message<?>)
                AzureFunctionUtil.enhanceInputIfNecessary(
                        " dh-602 ", context);

        assertSame(context, enriched.getHeaders().get(
                AzureFunctionUtil.EXECUTION_CONTEXT));
        assertInstanceOf(String.class, enriched.getPayload());

        @SuppressWarnings("unchecked")
        Message<String> typed = (Message<String>) enriched;

        Function<Message<String>, String> function =
                catalog.lookup("normalizeOrderWithContext");

        assertNotNull(function);
        assertEquals("DH-602", function.apply(typed));
    }

    @Test
    void functionWorksWithoutAzureHeader() {
        Function<Message<String>, String> function =
                catalog.lookup("normalizeOrderWithContext");

        assertNotNull(function);

        assertEquals("DH-603",
                function.apply(
                        MessageBuilder.withPayload(" dh-603 ")
                                .build()));
    }
}
~~~

**Ý nghĩa của từng assertion:**

1. Spring `ApplicationContext` có handler bean do `@Component` tạo.
2. `FunctionCatalog` có `normalizeOrderWithContext` với chữ ký message-aware.
3. `enhanceInputIfNecessary` mang đúng `ExecutionContext` vào header.
4. Function trả đúng nghiệp vụ ngay cả khi context là một test double.
5. Function vẫn xử lý được lời gọi **không có Azure context**, theo chính sách optional.

`assertInstanceOf` thuộc các bản JUnit 5 hiện đại; nếu cần tương thích JUnit cũ, dùng `assertTrue(enriched.getPayload() instanceof String)`.

### 13.1. Nếu header có sai kiểu

Trong môi trường không chắc header có đúng object Azure hay không, kiểm tra `instanceof` thay vì ép kiểu trực tiếp:

~~~java
Object candidate = message.getHeaders().get(
        AzureFunctionUtil.EXECUTION_CONTEXT);

if (candidate instanceof ExecutionContext azureContext) {
    azureContext.getLogger().info("Processing Azure invocation");
}
~~~

Đây là **biến thể** cho bean function mục 6, hữu ích khi một function được gọi qua nhiều adapters hoặc một message không hoàn toàn được kiểm soát.

### 13.2. FunctionCatalog test khác Azure Host test

`@SpringBootTest` chưa chạy Azure Java Worker, chưa sinh metadata `function.json` và chưa chứng minh authorization/route HTTP thực sự hoạt động. Các mức kiểm thử bổ sung cho nhau:

| Mức | Điều được kiểm chứng |
| --- | --- |
| Unit service | `OrderCodeService.normalize` xử lý dữ liệu đúng. |
| Unit helper | `AzureFunctionUtil` giữ context trong header. |
| Spring Boot test | DI, function registration, catalog lookup và message-aware call. |
| Azure Functions Host local | `@FunctionName` discovery, HTTP route, body/response và runtime context thật. |
| Cloud staging | Authorization, logs, Java runtime, scale/retry, observability và performance. |

### 13.3. Không dùng test object identity cho function wrapper

Khi tra cứu qua `FunctionCatalog`, function có thể được SCF bọc. **Không** khẳng định:

~~~java
assertSame(rawBean, catalog.lookup("normalizeOrderWithContext"));
~~~

Thay vào đó, kiểm behavior, type contract và việc header được đọc theo đúng nghiệp vụ. `assertSame` chỉ có ý nghĩa đặc biệt ở unit test **context header** vì helper phải gắn chính context instance của invocation.

## 14. Concurrency, async và observability

### 14.1. Một context cho mỗi invocation

Azure có thể xử lý nhiều invocations đồng thời:

~~~text
Request A → ExecutionContext A → Message A → Function
Request B → ExecutionContext B → Message B → Function
~~~

Nếu Spring handler giữ `ExecutionContext` trong một field mutable `currentContext`, request B có thể ghi đè giá trị của A. Với Message input, context đi theo **lời gọi cụ thể**, không phụ thuộc vào singleton field.

Một kiểu code **không nên dùng**:

~~~java
@Component
class UnsafeContextHolder {

    private ExecutionContext current;

    void setCurrent(ExecutionContext context) {
        this.current = context;
    }

    void log() {
        current.getLogger().info("May log wrong invocation");
    }
}
~~~

Nguy cơ tương tự xuất hiện nếu business function dùng `static` variable hoặc một mutable closure để giữ request/context.

### 14.2. Async job cần lưu scalar correlation thay vì runtime object

Nếu một job tiếp tục sau khi invocation kết thúc, hãy giữ các giá trị bền vững:

~~~java
String invocationId = context.getInvocationId();
String azureFunctionName = context.getFunctionName();
// Dùng scalar values trong JobMetadata của ứng dụng.
~~~

Không giữ nguyên `ExecutionContext` trong queue nội bộ/broker hoặc một long-running reactive publisher nếu không có hợp đồng lifecycle rõ. Nếu phải log ở background worker, dùng logger/tracing của **môi trường thực thi worker đó** cùng correlation ID, không mặc định logger của invocation Azure cũ vẫn hợp lệ.

### 14.3. Tracing khác logging

- `getLogger()` tích hợp với hệ thống log Azure Functions.
- `getInvocationId()` giúp tìm log của một lần thực thi.
- `getFunctionName()` xác định entrypoint Azure.
- `getTraceContext()` có thể cung cấp trace metadata tùy SDK/runtime.
- End-to-end distributed tracing qua HTTP, Queue, Service Bus hoặc Event Hubs cần instrumentation và propagation phù hợp.

**Đừng gọi invocation ID là distributed trace ID.** Khi một event được redeliver, bạn có thể nhận một invocation ID mới nhưng vẫn là cùng business event.

### 14.4. Cold start

Azure Worker khởi tạo Spring application context và FunctionCatalog có thể tạo độ trễ cold start. AzureFunctionUtil chỉ là bước gắn metadata, không thay thế/khắc phục chi phí khởi tạo container.

Cách giảm rủi ro:

1. Chỉ thêm dependency/starter cần cho chức năng.
2. Không gọi `SpringApplication.run(...)` trên mỗi invocation.
3. Tránh constructor/service initialization thực hiện network I/O dài hoặc blocking không cần thiết.
4. Giữ domain function stateless, thread-safe.
5. Đo startup, memory và throughput trên Azure hosting plan thực tế.

## 15. Packaging và chạy local với Azure Functions Core Tools

### 15.1. Khai báo Spring main class

Trong Maven:

~~~xml
<properties>
    <java.version>17</java.version>
    <start-class>example.azure.AzureOrderApplication</start-class>
</properties>
~~~

`AzureOrderApplication` là cấu hình Spring Boot; Azure entrypoint vẫn là phương thức `@FunctionName("normalizeAzureOrder")`.

### 15.2. Plugin build Azure và Spring Boot repackaging

Azure Maven/Gradle plugin quét Java annotations, tạo `function.json`, `host.json` và package layout mà Azure Java Worker cần. **Spring Boot repackaged executable fat JAR thông thường không tương thích trực tiếp với Azure Java Functions packaging**, nên cần tắt/điều chỉnh `spring-boot:repackage` hoặc dùng cách đóng gói SCF Azure adapter hỗ trợ.

Ví dụ fragment Maven, phải kết hợp với POM có Boot parent và Spring Cloud BOM phù hợp:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <skip>true</skip>
            </configuration>
        </plugin>
        <plugin>
            <groupId>com.microsoft.azure</groupId>
            <artifactId>azure-functions-maven-plugin</artifactId>
            <version>1.22.0</version>
            <configuration>
                <appName>azure-context-demo-unique</appName>
                <resourceGroup>azure-context-example-rg</resourceGroup>
                <region>eastasia</region>
                <hostJson>src/main/resources/host.json</hostJson>
                <runtime>
                    <os>linux</os>
                    <javaVersion>17</javaVersion>
                </runtime>
                <appSettings>
                    <property>
                        <name>FUNCTIONS_EXTENSION_VERSION</name>
                        <value>~4</value>
                    </property>
                </appSettings>
            </configuration>
            <executions>
                <execution>
                    <id>package-functions</id>
                    <goals>
                        <goal>package</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

`1.22.0` là **mốc plugin tham khảo**, không phải khẳng định bản mới nhất. Các tên Function App, resource group và region đều là ví dụ; cần thay theo Azure project đã được phê duyệt.

### 15.3. host.json và local.settings.json

Mẫu `src/main/resources/host.json` tối thiểu:

~~~json
{
  "version": "2.0"
}
~~~

Mẫu `local.settings.json`:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "FUNCTIONS_EXTENSION_VERSION": "~4",
    "MAIN_CLASS": "example.azure.AzureOrderApplication",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true"
  }
}
~~~

`UseDevelopmentStorage=true` cần **Azurite** khi host/trigger sử dụng Azure Storage emulator. Không commit bí mật trong `local.settings.json`. Trên Azure, dùng Function App settings, identity/Key Vault hay secret management phù hợp.

### 15.4. Khởi động và thử nghiệm

Sau khi cài JDK tương thích, Azure Functions Core Tools v4 và Maven:

~~~bash
./mvnw clean package
./mvnw azure-functions:run
~~~

Với HTTP prefix/port mặc định:

~~~bash
curl -i -X POST "http://localhost:7071/api/orders/context" \
  -H "Content-Type: text/plain" \
  --data " dh-601 "
~~~

Kỳ vọng HTTP 200 với body `DH-601`, đồng thời log chứa function name `normalizeAzureOrder` và invocation ID của lời gọi hiện tại. Thử body rỗng hoặc chỉ có dấu cách để nhận HTTP 400.

**Lưu ý:** Local Core Tools có thể xử lý function key khác với môi trường cloud; `AuthorizationLevel.FUNCTION` cần được test lại tại Azure staging. Không nhầm test HTTP local với việc đã kiểm chứng authorization production.

### 15.5. Triển khai lên cloud là bước riêng

Azure Maven plugin có thể sử dụng:

~~~bash
az login
./mvnw azure-functions:deploy
~~~

Deploy có thể làm thay đổi tài nguyên và phát sinh chi phí. Đây là hướng dẫn, **không phải thao tác cần thực thi trong STEP 4**.

## 16. Troubleshooting và checklist

### 16.1. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Import `AzureFunctionUtil` thất bại | Thiếu Azure SCF adapter hoặc sai version. | Dependency tree, Spring Cloud BOM và import path. |
| `ClassCastException` khi ép kết quả helper | Input/context hoặc API version không khớp giả định. | Test `Message<?>` và payload type tại boundary. |
| Header `executionContext` rỗng | Không gọi helper hoặc message được tạo từ nguồn khác. | Đặt assertion ở ingress trước khi gọi function. |
| Header có kiểu `String` thay vì `ExecutionContext` | Một nguồn ngoài đặt trùng tên. | Kiểm `instanceof ExecutionContext`. |
| Function `Function<String,String>` không đọc header | Chữ ký nhận payload, không nhận envelope. | Dùng `Message<T>` khi cần metadata. |
| Catalog lookup trả null | Sai bean name/registration hoặc cấu hình SCF. | `@Bean` name và catalog test. |
| Function chạy nhưng log không lên Azure | Logger level/filter hoặc monitoring config khác. | Host logs, Application Insights và policy quan sát. |
| Azure Host không thấy endpoint | Sai `@FunctionName`/`@HttpTrigger` hoặc package. | `function.json` và Azure plugin output. |
| Spring test PASS nhưng cloud runtime lỗi | Main class/JAR/Java runtime/permissions khác nhau. | `MAIN_CLASS`, classpath, runtime version, settings. |
| Header Azure bị gửi ra broker | Copy headers/serializer không lọc. | Loại runtime header, dùng outbound allowlist. |
| Nhiều requests log sai invocation | Context bị lưu trong singleton/static field. | Truyền context per Message, dùng stateless handler. |
| Queue event bị xử lý trùng | Retry/redelivery, dùng invocation ID làm key. | Business event ID/idempotency store. |
| Tracing không nối được các hop | Thiếu instrumentation/propagation. | Kiểm trace context trên từng transport. |

### 16.2. Checklist thực hành

- [ ] Azure handler nhận `ExecutionContext` ở tham số `@FunctionName`.
- [ ] Function chỉ nhận `Message<T>` khi thực sự cần context/header.
- [ ] Header được truy cập bằng `AzureFunctionUtil.EXECUTION_CONTEXT` thay vì key literal rải rác.
- [ ] Khi gọi ngoài Azure, đã quy định cách xử lý thiếu header.
- [ ] Context không được lưu trong field singleton hoặc serialize ra broker.
- [ ] Phân biệt invocation ID, business event ID và distributed trace ID.
- [ ] Đã có unit test helper với fake `ExecutionContext`.
- [ ] Có Spring Boot test cho `FunctionCatalog` và kiểu function.
- [ ] Có Azure Host test cho request, logs, security và binding.
- [ ] Error mapping/retry/idempotency được thiết kế riêng theo loại trigger.
- [ ] Java runtime, Azure package, Spring Cloud BOM và adapter cùng tương thích.
- [ ] Không sao chép mô hình `FunctionInvoker` legacy như hướng mặc định cho SCF 4.x/5.x.

## 17. Bài tập và tài liệu chính thức

### 17.1. Bài tập

1. Viết function `Function<Message<String>,String>` in `getFunctionName()` và `getInvocationId()` trong Azure logger, không log payload nhạy cảm.
2. Viết một Azure HTTP handler khác dùng `Function<String,String>`, log trực tiếp tại handler, so sánh với đường AzureFunctionUtil.
3. Test function khi thiếu header `EXECUTION_CONTEXT` và giải thích chính sách optional.
4. Gắn một header sai kiểu, sửa code theo `instanceof` và test không bị `ClassCastException`.
5. Thêm `businessCorrelationId` khác invocation ID; kiểm chứng nó giữ nguyên sau redelivery.
6. Loại header runtime trước khi output message sang Queue, test serialization không nhận object `ExecutionContext`.
7. Thử Queue Trigger với cùng business event được giao hai lần; thiết kế idempotency bằng event ID.
8. Đổi model thành `OrderRequest` chứa `InvocationInfo` trung lập và giữ domain service không import Azure.
9. Kiểm tra `getTraceContext()` theo Java SDK, phân biệt với Azure invocation ID.
10. Nâng adapter trong một nhánh thử nghiệm, kiểm lại helper, catalog và Azure package trước khi deploy.

### 17.2. Câu hỏi tự đánh giá

- `ExecutionContext` khác Spring `ApplicationContext` và `FunctionCatalog` thế nào?
- Vì sao Azure cấp `ExecutionContext` theo invocation?
- `AzureFunctionUtil.enhanceInputIfNecessary` giúp function đọc metadata bằng cách nào?
- Header `AzureFunctionUtil.EXECUTION_CONTEXT` chứa String ID hay Java runtime object?
- Nếu function nhận `Function<String,String>`, vì sao nó không đọc được message headers?
- Khi nào nên log tại Azure handler thay vì viết function message-aware?
- Vì sao invocation ID không phải idempotency key thích hợp cho Queue redelivery?
- Vì sao phải bỏ runtime context header khi gửi dữ liệu tới broker?
- `catalog.lookup("normalizeOrderWithContext")` có tự tạo Azure HTTP route không?
- Những test nào xác minh helper, Spring DI và Azure Host theo từng tầng?

### 17.3. Tài liệu tham khảo

- [Spring Cloud Function — Microsoft Azure Functions](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): `AzureFunctionUtil.enhanceInputIfNecessary`, `AzureFunctionUtil.EXECUTION_CONTEXT`, FunctionCatalog, packaging và Core Tools.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `Supplier`, `Function`, `Consumer`, message-aware contracts, composition và type conversion.
- [Microsoft Learn — Java ExecutionContext API](https://learn.microsoft.com/en-us/java/api/com.microsoft.azure.functions.executioncontext): `getLogger`, `getInvocationId`, `getFunctionName` và `getTraceContext`.
- [Microsoft Learn — Azure Functions Java Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-java): Java handler methods, annotations, execution context và logging.
- [Microsoft Learn — HTTP Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-http-webhook-trigger): route, authorization, request/response.
- [Microsoft Learn — Azure Storage Queue Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-queue-trigger): retry, poison message và redelivery.
- [Microsoft Learn — Functions Core Tools Local Run](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local): chạy host local.
- [Spring Cloud Function Azure Samples](https://github.com/spring-cloud/spring-cloud-function/tree/main/spring-cloud-function-samples): mẫu HTTP, Timer, Blob và Web Adapter.

**Kết luận:** `AzureFunctionUtil.enhanceInputIfNecessary(input, context)` cho phép đưa **ExecutionContext của Azure invocation hiện tại** vào header `AzureFunctionUtil.EXECUTION_CONTEXT` của Spring `Message<T>`. Một function nhận `Message<T>` có thể đọc metadata đó để ghi log/tracing khi cần, trong khi business service vẫn nên độc lập Azure. Giữ rõ ranh giới adapter, function và transport; không dùng invocation ID thay business event ID; không lưu hoặc phát nguyên runtime context ra ngoài process. Kiểm thử helper, FunctionCatalog, Spring DI và Azure Host riêng biệt trước khi vận hành production.
