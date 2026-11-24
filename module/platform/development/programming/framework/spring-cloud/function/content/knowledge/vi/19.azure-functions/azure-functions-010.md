# Mô hình FunctionInvoker cũ và hướng chuyển đổi theo phiên bản

## 1. Vì sao cần hiểu lịch sử FunctionInvoker?

Spring Cloud Function (SCF) giúp xây dựng nghiệp vụ có thể tái sử dụng qua các functional interface Java `Supplier<T>`, `Function<T,R>` và `Consumer<T>`. `FunctionCatalog` đăng ký, chuẩn hóa và tra cứu function; các adapter nối cùng logic đó với HTTP, messaging hoặc serverless runtime.

Azure Functions có một programming model riêng: Java handler được đánh dấu bằng `@FunctionName`, trigger/binding annotations và được Azure Java Worker gọi. Spring Cloud Function từng cung cấp một số lớp base để nối invocation Azure với function bean. Theo thời gian, mô hình này thay đổi:

- Các lớp handler đời đầu như `AzureSpringBootRequestHandler` được thay bằng `FunctionInvoker`.
- `FunctionInvoker` sau đó được đánh dấu legacy/deprecated trong tài liệu Azure adapter hiện hành.
- Mô hình được khuyến nghị hiện nay dùng Spring dependency injection với handler `@Component`/`@Service`, và `FunctionCatalog` khi cần thực thi function theo chuẩn SCF.
- `AzureFunctionUtil` hỗ trợ đưa Azure `ExecutionContext` vào `Message<T>` khi function cần metadata của invocation.

Đây là một chủ đề quan trọng khi bảo trì dự án Spring Cloud Function Azure: **không phải cứ thay tên superclass là đã hoàn thành migration**. Cần xác định đúng thế hệ adapter, function definition, cách truyền message/header, cách trả output và cấu hình package/runtime.

### Sau bài học, bạn có thể

1. Phân biệt Azure handler đời đầu, `FunctionInvoker` và mô hình dependency injection hiện tại.
2. Hiểu `handleRequest`, `handleOutput` và cách legacy invoker chọn function.
3. Xác định mốc phiên bản SCF 3.1, 3.2, 4.x và 5.x có ý nghĩa gì.
4. Chuyển handler kế thừa `FunctionInvoker` thành Spring bean có constructor injection.
5. Dùng `FunctionCatalog.lookup(...)` với tên function hoặc composition tường minh.
6. Chuyển `ExecutionContext` và HTTP headers sang `Message<T>` đúng cách.
7. Giữ nguyên contract của HTTP/Queue/Timer triggers trong quá trình migration.
8. Lập kế hoạch dependency alignment, package, test và triển khai an toàn.

## 2. Ba thế hệ tích hợp Azure cần phân biệt

### 2.1. Thế hệ đầu: AzureSpringBootRequestHandler

Trong các tài liệu SCF 3.1.x, mô hình phổ biến là kế thừa một base handler của adapter. Hai tên lớp thường gặp:

- `org.springframework.cloud.function.adapter.azure.AzureSpringBootRequestHandler`.
- `org.springframework.cloud.function.adapter.azure.AzureSpringBootHttpRequestHandler`.

Các lớp này dựa trên hạ tầng initializer/context của SCF để bootstrap Spring và chuyển request Azure sang function. Với HTTP, `AzureSpringBootHttpRequestHandler<I>` chuyên xử lý cặp `HttpRequestMessage<I>` và `HttpResponseMessage`.

Javadoc của SCF 3.1.5 đánh dấu `AzureSpringBootRequestHandler` và `AzureSpringBootHttpRequestHandler` deprecated từ **3.2**, thay bằng `FunctionInvoker`. Vì vậy, code kế thừa các lớp này là dấu hiệu của integration đời đầu.

### 2.2. Thế hệ giữa: FunctionInvoker

Từ dòng SCF 3.2, `FunctionInvoker<I,O>` là mô hình base class được tài liệu/Javadoc ghi nhận để thay thế các handler đời đầu. Handler Azure kế thừa nó, tạo `Message` nếu cần, rồi gọi `handleRequest(...)`:

~~~java
public class UppercaseHandler
        extends FunctionInvoker<Message<String>, String> {

    @FunctionName("uppercase")
    public String execute(
            @HttpTrigger(
                    name = "req",
                    methods = {HttpMethod.GET, HttpMethod.POST},
                    authLevel = AuthorizationLevel.ANONYMOUS)
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        Message<String> message =
                MessageBuilder.withPayload(
                        request.getBody().orElse(""))
                    .copyHeaders(request.getHeaders())
                    .build();

        return handleRequest(message, context);
    }
}
~~~

Function nghiệp vụ được khai báo trong Spring context:

~~~java
@Bean
public Function<String, String> uppercase() {
    return value -> value.toUpperCase(Locale.ROOT);
}
~~~

Hoặc function nhận trực tiếp message:

~~~java
@Bean
public Function<Message<String>, String> uppercase() {
    return message ->
            message.getPayload().toUpperCase(Locale.ROOT);
}
~~~

`FunctionInvoker` cung cấp hai phương thức thường thấy:

- `handleRequest(input, context)`: chuyển invocation sang function SCF tương ứng.
- `handleOutput(output)`: xử lý output theo quy ước của adapter cũ.

Tài liệu legacy giải thích tên function definition được lấy từ `ExecutionContext.getFunctionName()`. Vì vậy, tên Azure function và function definition trong SCF có thể được ghép ngầm với nhau. Cơ chế này tiện ở ứng dụng cũ nhưng tạo ra coupling mà code migration cần xử lý tường minh.

### 2.3. Thế hệ hiện tại: dependency injection + FunctionCatalog

Tài liệu Azure adapter hiện hành hướng dẫn:

- Thêm dependency `spring-cloud-function-adapter-azure`.
- Dùng `@Component` hoặc `@Service` cho class chứa Azure handler methods.
- Azure Java Worker gọi các method có `@FunctionName`.
- Spring inject service, bean hoặc `FunctionCatalog` vào handler.
- Dùng `FunctionCatalog` để lấy canonical function của SCF và composition.
- Dùng `AzureFunctionUtil.enhanceInputIfNecessary(...)` nếu cần truyền Azure `ExecutionContext` vào message header.

Ví dụ cấu trúc:

~~~text
Azure Functions Host
        |
        v
Java Worker
        |
        v
@Component OrderAzureHandler
        |
        +---- FunctionCatalog.lookup("normalizeOrder")
        |                  |
        |                  v
        |             SCF function bean
        |
        +---- AzureFunctionUtil (khi cần ExecutionContext)
~~~

Handler không còn phải kế thừa `FunctionInvoker`. Nó là một Spring bean bình thường, còn Azure annotations mô tả trigger/binding để Azure plugin sinh metadata.

Nếu ứng dụng thực chất là Spring MVC/WebFlux web app và chỉ cần HTTP trigger, có thể đánh giá riêng `spring-cloud-function-adapter-azure-web`. Đây là adapter web chuyên biệt, không phải tên mới của `FunctionInvoker`; với HTTP/Queue/Blob/Timer handler cần Azure annotations và bindings trực tiếp, dùng generic Azure adapter.

## 3. Bản đồ phiên bản và trạng thái hỗ trợ

Bảng sau tóm tắt các mốc được ghi nhận trong tài liệu và Javadoc chính thức:

| Dòng SCF | Mô hình Azure thường gặp | Trạng thái / hướng đi |
| --- | --- | --- |
| 3.1.x | `AzureSpringBootRequestHandler` / `AzureSpringBootHttpRequestHandler` | Mô hình đời đầu; các lớp này deprecated từ 3.2. |
| 3.2.x | `FunctionInvoker` / `HttpFunctionInvoker` | Hướng thay thế được ghi nhận cho các base handler cũ; Javadoc đánh dấu các lớp handler đời đầu deprecated since 3.2. |
| 4.0.x | Azure adapter với dependency injection; `FunctionInvoker` vẫn còn trong tài liệu legacy | Adapter yêu cầu 4.0.0+ để kích hoạt Azure Java Worker integration; tài liệu đã hướng người dùng sang `@Component` và `FunctionCatalog`. |
| 4.1–4.3.x | Dependency injection + Azure handler annotations | Mô hình mới là hướng dẫn chính; `FunctionInvoker` được đánh dấu deprecated. |
| 5.0.x | Dependency injection + Azure handler annotations | Tài liệu hiện hành vẫn đánh dấu legacy `FunctionInvoker` deprecated và khuyên dùng integration mới. |

Tại thời điểm soạn bài, tài liệu Spring Cloud Function hiện hành hiển thị dòng ổn định 5.0.x. Hãy chọn phiên bản adapter theo Spring Cloud BOM/release train của project, không ghép riêng adapter 5.x với các module context cũ hơn.

**Điều cần hiểu về mốc 4.0.0+:** tài liệu yêu cầu `spring-cloud-function-adapter-azure` từ 4.0.0 trở lên để kích hoạt Azure Java Worker integration. Điều đó không có nghĩa `FunctionInvoker` lập tức bị xóa ở 4.0.0. Tài liệu 4.x và 5.x vẫn có mục legacy/deprecated. Spring không công bố trong trang hướng dẫn một version removal cụ thể cho lớp này; hãy coi deprecated là tín hiệu cần lập kế hoạch thay thế, không đoán ngày bị xóa.

### 3.1. Đừng suy ra version chỉ từ tên class

Một số dự án có thể giữ nguyên code cũ nhưng nâng Spring Cloud BOM, hoặc có nhiều adapter dependency transitively. Trước khi thay đổi, xác minh:

- Version thực tế của `spring-cloud-function-adapter-azure`.
- Version `spring-cloud-function-context` và các module SCF liên quan.
- Spring Boot version và Spring Cloud release train.
- Java target/runtime.
- Azure Functions runtime và Azure Java library.
- Plugin Maven/Gradle đang sinh package.

Lấy dependency tree thay vì chỉ đọc version khai báo trực tiếp:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.cloud
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Các lệnh trên giúp phát hiện trường hợp adapter và context bị resolve về các version không cùng bộ.

## 4. FunctionInvoker cũ hoạt động như thế nào?

### 4.1. Azure handler là cầu nối

Trong mô hình legacy, class handler kế thừa `FunctionInvoker<Message<String>, String>`. Azure Host gọi method có `@FunctionName`; method đó:

1. Nhận request Azure và `ExecutionContext`.
2. Đọc payload.
3. Tạo `Message<String>`.
4. Có thể copy HTTP headers sang message.
5. Gọi `handleRequest(message, context)`.
6. Trả output cho Azure runtime.

FunctionInvoker đảm nhận một phần việc kết nối Spring function context với Azure invocation.

### 4.2. Function name được chọn ngầm

Mô hình cũ dùng `ExecutionContext.getFunctionName()` để tìm function definition. Ví dụ:

~~~java
@FunctionName("uppercase")
public String execute(...) {
    return handleRequest(message, context);
}
~~~

Nếu bean SCF được đăng ký với tên `uppercase`, việc chọn function có thể diễn ra tự động theo tên Azure function.

Điều này tạo ra một quy ước ngầm:

~~~text
@FunctionName("uppercase")
        |
        v
ExecutionContext.getFunctionName()
        |
        v
FunctionInvoker chọn definition "uppercase"
        |
        v
FunctionCatalog / SCF function
~~~

Nếu đổi tên Azure function mà không đổi bean, hoặc đổi bean mà không đổi Azure function name, ứng dụng có thể lookup sai function. Trong migration sang mô hình mới, cần ghi rõ hai tên này.

### 4.3. handleRequest và handleOutput không phải business logic

`handleRequest` và `handleOutput` là API của base class adapter cũ. Chúng không phải method của `Function<T,R>` và cũng không phải Azure Java Worker API.

Khi chuyển sang handler dependency injection:

- Handler chịu trách nhiệm gọi function hoặc service phù hợp.
- Handler chuyển kết quả thành kiểu output Azure binding yêu cầu.
- Với HTTP, handler có thể tạo `HttpResponseMessage`.
- Với Queue/Blob/Service Bus output, dùng các output binding annotations/types phù hợp.
- Không giữ lời gọi `handleRequest` hoặc `handleOutput` trong class đã bỏ kế thừa `FunctionInvoker`.

## 5. FunctionCatalog trong mô hình mới

### 5.1. Bean Spring và function SCF là hai khái niệm khác nhau

Spring có thể inject trực tiếp một bean `Function<String,String>` vào handler. Cách này gọi đúng Java bean, nhưng nếu cần các tính năng chuẩn hóa của SCF như type conversion, composition và canonical function wrapper, hãy tra cứu qua `FunctionCatalog`.

Ví dụ:

~~~java
@Bean
Function<String, String> normalizeOrder() {
    return value -> value.strip().toUpperCase(Locale.ROOT);
}

@Bean
Function<String, String> addPrefix() {
    return value -> "REF-" + value;
}
~~~

Trong Azure handler:

~~~java
Function<Object, Object> pipeline =
        functionCatalog.lookup("normalizeOrder|addPrefix");
Object result = pipeline.apply(input);
~~~

`FunctionCatalog.lookup(...)` trả về function đã được SCF instrument/wrap. Dùng tên bean function và cú pháp composition của SCF, không dùng tên Azure route thay thế trừ khi hai tên tình cờ giống nhau.

### 5.2. Function name và Azure function name

| Tên | Thuộc về | Ví dụ |
| --- | --- | --- |
| `normalizeOrder` | Spring bean / SCF function | Method `@Bean normalizeOrder()` |
| `addPrefix` | Spring bean / SCF function | Method `@Bean addPrefix()` |
| `normalizeOrder|addPrefix` | SCF composition definition | Hai function chạy nối tiếp |
| `normalizeAzureOrder` | Azure Function name | `@FunctionName("normalizeAzureOrder")` |
| `orders/normalize` | HTTP route | `route = "orders/normalize"` |

Mô hình mới làm mối quan hệ này rõ ràng: Azure handler được Azure gọi theo function name/trigger; bên trong handler, ứng dụng chủ động lookup function definition mong muốn.

### 5.3. Vì sao nên lookup rõ ràng?

Lookup tường minh có các lợi ích:

- Không phụ thuộc vào việc Azure function name phải trùng với bean name.
- Dễ dùng một function trong nhiều Azure handlers.
- Có thể gọi composition mà không tạo thêm function bean.
- Dễ test function definition độc lập với Azure trigger.
- Khi đổi tên route/handler, business function vẫn giữ nguyên.

Nếu catalog lookup trả về null, hãy fail fast khi tạo handler hoặc kiểm tra startup; không đợi request production đầu tiên mới phát hiện sai tên.

## 6. Ví dụ migration hoàn chỉnh: HTTP uppercase

### 6.1. Business functions dùng lại được

Tạo hai function bean trong Spring configuration:

~~~java
package example.azure;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TextFunctions {

    @Bean
    public Function<String, String> normalizeText() {
        return value -> {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException("Input is empty");
            }
            return value.strip().toUpperCase(Locale.ROOT);
        };
    }

    @Bean
    public Function<String, String> addReferencePrefix() {
        return value -> "REF-" + value;
    }
}
~~~

Các bean này không import Azure SDK. Có thể gọi chúng từ Azure handler, HTTP adapter khác hoặc unit test.

### 6.2. Handler dependency injection mới

~~~java
package example.azure;

import java.util.Optional;
import java.util.Objects;
import java.util.function.Function;

import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.HttpRequestMessage;
import com.microsoft.azure.functions.HttpResponseMessage;
import com.microsoft.azure.functions.HttpStatus;
import com.microsoft.azure.functions.annotation.AuthorizationLevel;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.HttpTrigger;
import com.microsoft.azure.functions.HttpMethod;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class OrderAzureHandler {

    private final Function<Object, Object> pipeline;

    public OrderAzureHandler(FunctionCatalog functionCatalog) {
        this.pipeline = Objects.requireNonNull(
                functionCatalog.lookup("normalizeText|addReferencePrefix"));
    }

    @FunctionName("normalizeAzureOrder")
    public HttpResponseMessage normalize(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION,
                    route = "orders/normalize")
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        String input = request.getBody().orElse("");

        if (input.isBlank()) {
            return request
                    .createResponseBuilder(HttpStatus.BAD_REQUEST)
                    .body("Mã đơn không được rỗng")
                    .build();
        }

        try {
            Object result = pipeline.apply(input);

            context.getLogger().info(
                    "Order normalized: " + context.getInvocationId());

            return request
                    .createResponseBuilder(HttpStatus.OK)
                    .header("Content-Type", "text/plain; charset=utf-8")
                    .body(result)
                    .build();
        }
        catch (IllegalArgumentException invalidInput) {
            return request
                    .createResponseBuilder(HttpStatus.BAD_REQUEST)
                    .body(invalidInput.getMessage())
                    .build();
        }
    }
}
~~~

Với input `" dh-901 "`, output là `REF-DH-901`. Tên Azure function là `normalizeAzureOrder`, còn composition SCF là `normalizeText|addReferencePrefix`. Hai tên được phân biệt rõ.

Đây là handler minh họa tập trung vào luồng migration. Trong ứng dụng thật, hãy bổ sung error mapping theo domain, logging không chứa dữ liệu nhạy cảm, timeout và output contract của API.

### 6.3. Khác biệt chính so với FunctionInvoker

| Legacy | Mô hình mới |
| --- | --- |
| `extends FunctionInvoker<Message<String>, String>` | `@Component` / `@Service` |
| Gọi `handleRequest(message, context)` | Gọi `functionCatalog.lookup("...").apply(input)` |
| Function definition lấy từ Azure function name | Function definition được chỉ định tường minh |
| Base class quản lý phần lớn việc dispatch | Handler chịu trách nhiệm mapping request/output |
| Legacy header convention | `AzureFunctionUtil.EXECUTION_CONTEXT` khi cần Azure context trong Message |

## 7. Chuyển ExecutionContext và Message headers

### 7.1. Legacy FunctionInvoker tự thêm context

Mô hình cũ thêm Azure `ExecutionContext` vào Message header với key `executionContext`. Một function nhận `Message<T>` có thể lấy header đó:

~~~java
import java.util.Locale;
import java.util.function.Function;

import com.microsoft.azure.functions.ExecutionContext;
import org.springframework.messaging.Message;

@Bean
public Function<Message<String>, String> uppercase() {
    return message -> {
        String payload = message.getPayload();

        ExecutionContext context =
                (ExecutionContext) message.getHeaders()
                        .get("executionContext");

        if (context != null) {
            context.getLogger().info("Processing message");
        }

        return payload.toUpperCase(Locale.ROOT);
    };
}
~~~

Đoạn code này phản ánh cách legacy sample truy cập header. Khi migration, tránh rải chuỗi literal `"executionContext"` trong business code.

### 7.2. Mô hình mới dùng AzureFunctionUtil

Azure adapter hiện hành cung cấp:

~~~java
AzureFunctionUtil.enhanceInputIfNecessary(input, context)
~~~

Helper này thêm instance `ExecutionContext` vào header của Spring `Message` bằng key:

~~~java
AzureFunctionUtil.EXECUTION_CONTEXT
~~~

Ví dụ:

~~~java
import java.util.function.Function;

import com.microsoft.azure.functions.ExecutionContext;
import org.springframework.cloud.function.adapter.azure.AzureFunctionUtil;
import org.springframework.messaging.Message;

String payload = request.getBody().orElse("");

Message<?> message = (Message<?>)
        AzureFunctionUtil.enhanceInputIfNecessary(
                payload, context);

Function<Object, Object> uppercaseWithContext =
        functionCatalog.lookup("uppercaseWithContext");
Object result = uppercaseWithContext.apply(message);
~~~

Function bean có thể đọc metadata:

~~~java
import java.util.Locale;
import java.util.function.Function;

import com.microsoft.azure.functions.ExecutionContext;
import org.springframework.cloud.function.adapter.azure.AzureFunctionUtil;
import org.springframework.messaging.Message;

@Bean
public Function<Message<String>, String> uppercaseWithContext() {
    return message -> {
        String payload = message.getPayload();

        Object value = message.getHeaders().get(
                AzureFunctionUtil.EXECUTION_CONTEXT);

        if (value instanceof ExecutionContext context) {
            context.getLogger().info("Uppercase function invoked");
        }

        return payload.toUpperCase(Locale.ROOT);
    };
}
~~~

Nếu function chỉ cần payload, hãy giữ chữ ký `Function<String,String>` và log tại Azure handler. Chỉ dùng `Message<T>` khi cần metadata hoặc headers; không buộc mọi business function phụ thuộc Azure runtime.

### 7.3. HTTP headers không tự động đồng nghĩa với Azure context

Legacy sample thường copy HTTP headers vào Message:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> message =
        MessageBuilder.withPayload(payload)
                .copyHeaders(request.getHeaders())
                .build();
~~~

`AzureFunctionUtil.enhanceInputIfNecessary` giải quyết việc gắn `ExecutionContext`. Khi migration, đừng giả định helper này tự copy mọi HTTP headers theo đúng chính sách cũ. Nếu nghiệp vụ cần correlation ID hoặc tenant metadata, hãy chọn lọc và map chúng rõ ràng:

~~~java
import org.springframework.cloud.function.adapter.azure.AzureFunctionUtil;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> input = MessageBuilder.withPayload(payload)
        .setHeader("correlationId",
                request.getHeaders().get("x-correlation-id"))
        .build();

Message<?> enriched = (Message<?>)
        AzureFunctionUtil.enhanceInputIfNecessary(input, context);
~~~

Không copy toàn bộ header tùy tiện: HTTP headers có thể chứa authorization token, cookie, function key hoặc dữ liệu nhạy cảm. Chỉ truyền header đã được allowlist và xác thực.

### 7.4. Đừng lưu ExecutionContext vào singleton state

Azure handler bean thường là Spring singleton. Không giữ context invocation trong field mutable:

~~~java
// Không nên
private ExecutionContext currentContext;
~~~

Nhiều invocation đồng thời có thể ghi đè context của nhau. Truyền context qua tham số hoặc message của đúng invocation; không lưu nó vào static field, cache dùng chung hay message broker.

## 8. Chuyển đổi HTTP input/output

### 8.1. Legacy handler có thể trả payload trực tiếp

FunctionInvoker cũ cho phép handler gọi `handleRequest` rồi trả giá trị nghiệp vụ. Khi chuyển sang DI, handler cần chịu trách nhiệm rõ ràng hơn về Azure output type.

Ví dụ:

~~~java
@FunctionName("normalizeAzureOrder")
public HttpResponseMessage normalize(
        @HttpTrigger(
                name = "request",
                methods = {HttpMethod.POST},
                authLevel = AuthorizationLevel.FUNCTION,
                route = "orders/normalize")
        HttpRequestMessage<Optional<String>> request,
        ExecutionContext context) {
    Function<Object, Object> normalizeText =
            functionCatalog.lookup("normalizeText");
    String result = (String) normalizeText.apply(
            request.getBody().orElse(""));
    return request.createResponseBuilder(HttpStatus.OK)
            .body(result)
            .build();
}
~~~

Với HTTP Trigger, có thể trả `HttpResponseMessage` để kiểm soát status, headers và body. Cũng có thể dùng output type khác nếu binding và contract cho phép; hãy giữ response semantics cũ trong migration.

### 8.2. Error mapping phải được giữ nguyên

Lập bảng đối chiếu trước khi thay code:

| Tình huống | Contract cũ | Cần xác minh ở handler mới |
| --- | --- | --- |
| Body rỗng | Có thể exception hoặc 400 tùy code | Status 400 và message ổn định |
| Input không hợp lệ | Error do function/adapter mapping | Không biến lỗi validation thành 500 ngoài ý muốn |
| Business exception | Legacy handler behavior | HTTP 4xx/5xx theo domain |
| Downstream timeout | Adapter/host behavior | Timeout status và retry policy |
| Output null | Có thể được adapter serialize khác nhau | Azure response/output binding đúng contract |
| Header content type | Có thể qua converter cũ | Giữ content type/JSON shape |

Không cho rằng `handleOutput` có thể được bỏ mà không test. Hãy so sánh output JSON, encoding, status code và headers của bản cũ với bản mới.

### 8.3. Non-HTTP triggers

Với Queue, Blob, Timer, Event Hubs hoặc Service Bus, phần Azure annotations vẫn thuộc handler. Migration thay cơ chế gọi function SCF, không thay trigger contract:

- `@QueueTrigger` tiếp tục xác định queue và connection.
- `@BlobTrigger` tiếp tục xác định container/path.
- `@TimerTrigger` tiếp tục xác định lịch.
- Output bindings tiếp tục dùng kiểu/annotation Azure tương ứng.

Handler mới có thể gọi `FunctionCatalog` rồi map kết quả vào output binding. Không biến mọi trigger thành HTTP chỉ để tận dụng code mẫu.

## 9. Những lỗi thường gặp khi migration

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Azure Host không thấy function | Handler không còn được phát hiện hoặc thiếu `@FunctionName` | Giữ method public, annotations và package metadata. |
| Spring không inject handler | Class mới chưa có `@Component`/`@Service` hoặc nằm ngoài component scan | Kiểm tra package root và Spring main class. |
| Catalog lookup trả null | Dùng Azure function name thay bean name; sai tên hoặc bean không được đăng ký | Kiểm tra `@Bean` method name và lookup definition. |
| Composition lỗi | Sai thứ tự hoặc type đầu ra/đầu vào không khớp | Kiểm từng function và composition `a|b`. |
| Output thay đổi | Bỏ `handleOutput` nhưng chưa map lại HTTP/binding response | So sánh status, body, headers và serialization. |
| Function không thấy header | Chữ ký nhận payload thay vì `Message<T>` | Dùng `Message<T>` nếu thực sự cần metadata. |
| Không thấy Azure logger | Đọc literal header cũ hoặc không gọi helper mới | Dùng `AzureFunctionUtil.enhanceInputIfNecessary` và constant. |
| Header request biến mất | Không copy allowlisted headers khi bỏ legacy MessageBuilder | Map correlation/tenant headers tường minh. |
| Ứng dụng gọi nhầm function | Legacy dựa trên `getFunctionName()`; code mới lookup nhầm tên | Tách Azure function name và SCF function definition. |
| Context khởi động nhiều lần | Tự gọi `SpringApplication.run` trong mỗi invocation | Để adapter bootstrap context và inject bean. |
| `ClassNotFoundException` sau nâng version | BOM/dependency adapter/context không đồng bộ | Kiểm dependency tree và release train. |
| Azure package không discover | JAR layout/Boot repackage hoặc plugin staging sai | Kiểm `function.json`, `host.json`, manifest và package layout. |
| Test Spring pass nhưng Host fail | Unit/context test không chạy Azure Java Worker | Chạy Core Tools integration test và kiểm function discovery. |

### 9.1. Không tìm một lớp Helper/Initializer thay thế FunctionInvoker

Tên `FunctionInvoker` xuất hiện trong nhiều tài liệu legacy, nhưng không nên tự suy ra rằng có một class công khai ổn định tên `FunctionInvokerHelper` hoặc `FunctionInvokerInitializer` cho mọi phiên bản Azure adapter. Hãy kiểm tra package/API đúng version trong Javadoc và dependency thực tế. Mô hình hiện hành dựa trên Spring component, Azure handler annotations, FunctionCatalog và helper cụ thể `AzureFunctionUtil`.

## 10. Kế hoạch migration theo từng bước

### Bước 1: Lập danh sách handler hiện tại

Tìm trong source:

~~~bash
rg -n "FunctionInvoker|AzureSpringBootRequestHandler|AzureSpringBootHttpRequestHandler|handleRequest|handleOutput" src
~~~

Với từng handler, ghi lại:

- Azure function name.
- Trigger và bindings.
- Function definition mà legacy invoker đang chọn.
- Input/output type.
- Headers được copy.
- Error/status/serialization behavior.
- Có đọc `ExecutionContext` không.

### Bước 2: Xác minh dependency/version

- Chọn Spring Cloud release train tương thích với Spring Boot.
- Dùng BOM để quản lý các module SCF đồng bộ.
- Nâng `spring-cloud-function-adapter-azure` lên dòng 4.0.0+ nếu chuyển sang mô hình Azure Java Worker hiện hành.
- Kiểm tra Azure Java Functions library và Maven/Gradle plugin.
- Không chỉ nâng adapter mà giữ các module SCF ở version cũ bằng explicit dependency overrides.

### Bước 3: Tách nghiệp vụ khỏi Azure handler

Giữ function beans hoặc service thuần Java. Đừng chuyển logic nghiệp vụ vào method `@FunctionName` nếu mục tiêu là tái sử dụng qua adapter khác.

Nếu business function đang nhận `Message<T>` chỉ vì cần Azure context, cân nhắc tách thành:
- Domain function nhận payload/domain object.
- Adapter handler xử lý `ExecutionContext`, logging và correlation.
- Message-aware wrapper chỉ ở nơi thật sự cần metadata.

### Bước 4: Chuyển handler sang Spring component

- Xóa `extends FunctionInvoker<...>`.
- Thêm `@Component` hoặc `@Service`.
- Dùng constructor injection cho service/catalog.
- Giữ `@FunctionName` và trigger/binding annotations.
- Giữ public method signature mà Azure plugin cần scan.

### Bước 5: Thay implicit dispatch bằng explicit lookup

Thay:

~~~java
return handleRequest(message, context);
~~~

bằng:

~~~java
import java.util.function.Function;

Function<Object, Object> pipeline =
        functionCatalog.lookup("normalizeText|addReferencePrefix");
Object result = pipeline.apply(input);
~~~

Dùng đúng bean names/SCF definition. Nếu chỉ cần gọi service Java, có thể inject service trực tiếp; nếu cần type conversion/composition/canonical SCF wrapper, dùng FunctionCatalog.

### Bước 6: Thay header propagation

- Xác định header nào đang được function dùng.
- Với Azure context, gọi `AzureFunctionUtil.enhanceInputIfNecessary(input, context)`.
- Đọc header bằng `AzureFunctionUtil.EXECUTION_CONTEXT`.
- Map correlation ID/tenant metadata bằng allowlist.
- Bỏ các header legacy không còn được sử dụng.

### Bước 7: Map output/error lại

Tái tạo HTTP response hoặc output binding tương ứng. Kiểm thử status, body, content type, null output, error mapping và retry behavior.

### Bước 8: Build/package và kiểm tra metadata

- Kiểm tra main class và `MAIN_CLASS`.
- Kiểm tra Maven/Gradle Azure plugin.
- Xác nhận `function.json` trỏ đúng handler.
- Kiểm tra JAR layout, dependencies và `host.json`.
- Tránh Spring Boot fat JAR mặc định nếu không tương thích package Azure.

### Bước 9: Kiểm thử song song và phát hành

Chạy unit test, Spring context test và Azure Host local. Deploy staging, gửi cùng test vectors cho bản cũ/mới nếu có thể, so sánh output. Chỉ promotion sau khi trigger, auth, logs và downstream integrations được xác minh.

## 11. Kiểm thử sau migration

### 11.1. Unit test business function

~~~java
@Test
void normalizesAndAddsPrefix() {
    String normalized = " dh-901 ".strip().toUpperCase(Locale.ROOT);
    String output = "REF-" + normalized;
    assertEquals("REF-DH-901", output);
}
~~~

Trong project thật, test trực tiếp service/function bean, không chép logic production vào test như ví dụ tối giản này.

### 11.2. Spring context và FunctionCatalog

~~~java
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class AzureFunctionMigrationTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void migratedCompositionIsRegistered() {
        Function<Object, Object> pipeline =
                catalog.lookup("normalizeText|addReferencePrefix");
        assertNotNull(pipeline);

        Object result = pipeline.apply(" dh-901 ");

        assertEquals("REF-DH-901", result);
    }
}
~~~

Test này kiểm tra Spring context và SCF catalog. Nó không khởi động Azure Functions Host.

### 11.3. Azure Host integration test

Dùng Azure Functions Core Tools local để xác minh:

- Host discover đúng tên function.
- HTTP method/route/auth level đúng.
- Java worker và Spring context khởi tạo.
- Invocation trả đúng status/body/header.
- Queue/Blob/Timer triggers chạy theo binding contract.
- Log/ExecutionContext được gắn đúng invocation.
- Không có function trùng tên khi migration song song.

### 11.4. Regression test matrix

| Nhóm | Test case |
| --- | --- |
| Payload | String rỗng, Unicode, JSON object, payload lớn |
| Message | Content-Type, correlation ID, allowlisted headers |
| Context | ExecutionContext header có/không có, invocation ID |
| Function selection | Tên bean, composition, Azure function name khác bean name |
| HTTP | GET/POST, 200/400/401/403/500, response headers |
| Output | String, JSON, null, OutputBinding |
| Trigger | Queue redelivery, Blob event, Timer schedule |
| Failure | Validation, downstream timeout, dependency unavailable |
| Concurrency | Nhiều invocation đồng thời không lẫn context |
| Packaging | function.json, main class, classpath, Java runtime |

## 12. Chiến lược phát hành và rollback

Không cần đổi tất cả handlers trong một release lớn nếu ứng dụng có nhiều triggers.

Có thể chia theo nhóm:

1. Chọn một HTTP function đơn giản làm pilot.
2. Chuyển handler sang dependency injection và FunctionCatalog.
3. Chạy regression tests trên cùng test vectors.
4. Deploy vào staging Function App hoặc slot được hosting plan hỗ trợ.
5. So sánh telemetry, latency, error rate và trigger discovery.
6. Chuyển từng trigger/handler tiếp theo.
7. Xóa code legacy sau khi tất cả callers và deployment packages đã được xác minh.

Không giữ hai handler cùng `@FunctionName` trong một Function App. Nếu cần so sánh old/new đồng thời, dùng Function App staging riêng hoặc tên Azure function khác nhau và tránh consume cùng queue/topic production.

Rollback cần quay lại artifact và cấu hình dependency tương ứng. Không chỉ revert Java source nếu pipeline đã thay BOM, Java runtime, function metadata hoặc settings.

## 13. Checklist migration

- [ ] Đã xác định đúng thế hệ cũ: `AzureSpringBootRequestHandler` hay `FunctionInvoker`.
- [ ] Đã ghi nhận function definition mà legacy invoker tự chọn.
- [ ] Đã xác định Spring bean names và Azure function names.
- [ ] Đã căn chỉnh Spring Boot, Spring Cloud BOM và SCF adapter.
- [ ] Handler mới là `@Component`/`@Service`.
- [ ] Constructor injection thay cho legacy base class.
- [ ] FunctionCatalog lookup dùng tên/composition tường minh.
- [ ] `ExecutionContext` được truyền bằng `AzureFunctionUtil` khi cần.
- [ ] HTTP headers được allowlist thay vì copy toàn bộ mặc định.
- [ ] Output/error mapping giữ nguyên contract.
- [ ] `function.json` và package layout được tạo lại.
- [ ] Unit, Spring context và Azure Host tests đều đạt.
- [ ] Staging smoke test và rollback artifact đã sẵn sàng.
- [ ] Không còn handler legacy trùng tên hoặc chưa được chuyển đổi.

## 14. Câu hỏi tự đánh giá

- Vì sao `AzureSpringBootRequestHandler` bị thay thế từ SCF 3.2?
- `FunctionInvoker` khác `AzureSpringBootRequestHandler` ở điểm nào?
- Vì sao `FunctionInvoker` vẫn có trong tài liệu 4.x nhưng được đánh dấu legacy/deprecated?
- SCF adapter 4.0.0+ có ý nghĩa gì với Azure Java Worker integration?
- `handleRequest` và `handleOutput` thuộc lớp nào?
- Vì sao FunctionInvoker cũ có thể dùng `ExecutionContext.getFunctionName()` để chọn function?
- Trong mô hình mới, tên Azure function có cần trùng tên bean SCF không?
- Khi nào nên inject bean trực tiếp, khi nào nên dùng FunctionCatalog?
- `AzureFunctionUtil.EXECUTION_CONTEXT` giải quyết việc gì?
- Vì sao không nên copy toàn bộ HTTP headers sang Message?
- Handler mới cần chịu trách nhiệm gì với HTTP status và output binding?
- Vì sao Spring context test không đủ để xác nhận Azure Host integration?
- Làm thế nào để rollback khi dependency BOM và function metadata cùng thay đổi?

## 15. Tài liệu tham khảo chính thức

- [Spring Cloud Function — Microsoft Azure Functions, current reference](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): mô hình dependency injection hiện hành, FunctionCatalog, AzureFunctionUtil và ghi chú FunctionInvoker deprecated.
- [Spring Cloud Function 4.3 — Azure adapter reference](https://docs.spring.io/spring-cloud-function/reference/4.3/adapters/azure-intro.html): hướng dẫn Azure adapter và mục FunctionInvoker deprecated.
- [Spring Cloud Function 4.0.4 — Reference guide](https://docs.spring.io/spring-cloud-function/docs/4.0.4/reference/html/spring-cloud-function.html): lịch sử FunctionInvoker và programming model SCF.
- [Spring Cloud Function 3.2.5 — Azure reference](https://docs.spring.io/spring-cloud-function/docs/3.2.5/reference/html/azure.html): mô hình FunctionInvoker đời 3.2.
- [Javadoc 3.2.7 — Deprecated API](https://javadoc.io/static/org.springframework.cloud/spring-cloud-function-adapter-azure/3.2.7/deprecated-list.html): AzureSpringBootRequestHandler và AzureSpringBootHttpRequestHandler deprecated since 3.2.
- [Javadoc 4.0.2 — HttpFunctionInvoker](https://javadoc.io/static/org.springframework.cloud/spring-cloud-function-adapter-azure/4.0.2/org/springframework/cloud/function/adapter/azure/HttpFunctionInvoker.html): class HTTP invoker thuộc thế hệ FunctionInvoker.
- [Spring Cloud Function Azure sample — Legacy FunctionInvoker and current samples](https://github.com/spring-cloud/spring-cloud-function/tree/main/spring-cloud-function-samples/function-sample-azure): ví dụ legacy và liên kết đến các mẫu dependency-injection adapter.
- [Spring Cloud Function — Programming Model and FunctionCatalog](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): function registration, lookup, canonical wrapper và composition.
- [Spring Cloud Function for Azure Function — Spring Blog](https://spring.io/blog/2023/02/24/spring-cloud-function-for-azure-function/): giới thiệu Azure adapter và bối cảnh sử dụng SCF với Azure.

**Kết luận:** Azure integration của Spring Cloud Function đã đi qua ba thế hệ: các lớp `AzureSpringBootRequestHandler` đời đầu, `FunctionInvoker` từ SCF 3.2, và mô hình dependency injection hiện hành. Tài liệu Spring hiện đánh dấu `FunctionInvoker` legacy/deprecated và hướng người dùng sang handler `@Component`/`@Service`, `FunctionCatalog` và `AzureFunctionUtil` khi cần message metadata. Khi migration, hãy căn chỉnh dependency theo release train, tách tên Azure function khỏi SCF function definition, giữ nguyên HTTP/trigger output contract, kiểm tra header/context và xác minh package bằng Azure Host trước khi phát hành.
