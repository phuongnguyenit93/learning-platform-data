# Tiêm dịch vụ nghiệp vụ và FunctionCatalog vào handler

## 1. Bài toán: Azure gọi handler, Spring cung cấp nghiệp vụ

**Spring Cloud Function (SCF)** giúp phát triển logic nghiệp vụ có thể tái sử dụng thông qua ba interface Java: `Supplier<T>`, `Function<T,R>` và `Consumer<T>`. Các function bean được đăng ký/tra cứu bằng **`FunctionCatalog`**, có thể ghép qua definition `f1|f2`, chuyển đổi dữ liệu theo hợp đồng SCF, và được gọi lại từ HTTP, sự kiện hoặc môi trường serverless qua adapter tương ứng.

**Azure Functions** giải quyết vấn đề kích hoạt và thực thi ở môi trường serverless. Với Java, Azure Java Worker gọi một **phương thức public** mang `@FunctionName` và trigger annotation như `@HttpTrigger` hoặc `@QueueTrigger`. Azure không tự coi mọi `@Bean Function` trong Spring là một Azure Function.

Khi triển khai SCF trên Azure, cách tổ chức bền vững là:

- **Azure handler** nhận input/metadata, gọi nghiệp vụ, tạo response hoặc output binding.
- **Spring service** thực hiện quy tắc nghiệp vụ có thể dùng lại và được inject vào handler.
- **Function bean** thích nghi phương thức của service thành `Function<T,R>` hoặc `Consumer<T>`.
- **FunctionCatalog** tra cứu một function hoặc một composition theo tên, thay vì để handler biết cách nối từng function.
- **`spring-cloud-function-adapter-azure`** kết nối Java Worker với Spring dependency injection.

Bài này thuộc chương **Azure Functions** của module **SPRING_CLOUD_FUNCTION**. Trọng tâm là **tiêm dịch vụ nghiệp vụ và `FunctionCatalog` vào handler**, không phải viết lại toàn bộ business logic bên trong phương thức `@FunctionName`.

Sau bài học, bạn có thể: cấu hình service, function beans và constructor injection; phân biệt inject bean trực tiếp với tra cứu catalog; viết hai Azure HTTP handlers cùng tái sử dụng một business service; hiểu vấn đề scope, concurrency và cold start; kiểm thử và chẩn đoán chính xác lỗi ở ba tầng Azure, Spring và SCF.

## 2. Sơ đồ kiến trúc và quyền sở hữu dependency

~~~mermaid
flowchart LR
    A["HTTP / Queue / Timer"] --> B["Azure Functions Host"]
    B --> C["Azure Java Worker"]
    C --> D["@FunctionName handler"]
    E["spring-cloud-function-adapter-azure"] -. "FunctionInstanceInjector / Spring DI" .-> D
    F["Spring ApplicationContext"] --> E
    F --> G["@Service OrderService"]
    F --> H["@Bean parseOrder / routeOrder"]
    H --> I["FunctionCatalog"]
    D -->|"gọi trực tiếp"| G
    D -->|"lookup parseOrder|routeOrder"| I
    I --> H
    H --> G
    D --> J["HTTP response / output binding"]
~~~

Sơ đồ có hai đường đi nghiệp vụ:

1. **Đường Spring service trực tiếp:** handler inject `OrderService` và gọi `service.parse(...)`, `service.classify(...)`.
2. **Đường qua FunctionCatalog:** handler inject `FunctionCatalog`, gọi `catalog.lookup("parseOrder|routeOrder")` để lấy một `Function<String,OrderDecision>`; các bean function ở bên dưới lại sử dụng **chính `OrderService`**.

Cả hai phải cho **cùng kết quả nghiệp vụ**, nhưng catalog cung cấp thêm cơ chế wrapping và composition của SCF.

### 2.1. Ai tạo đối tượng nào?

| Đối tượng | Người tạo/quản lý | Khi nào được dùng? |
| --- | --- | --- |
| `OrderService` gắn `@Service` | Spring ApplicationContext | Logic parse, validation và phân loại. |
| `@Bean Function<String,OrderCommand>` | Spring; SCF nhận diện trong FunctionCatalog | Bước chuyển input thành đối tượng nghiệp vụ. |
| `@Bean Function<OrderCommand,OrderDecision>` | Spring; SCF nhận diện trong catalog | Bước xử lý nghiệp vụ. |
| `FunctionCatalog` | Spring Cloud Function trong context | Tra cứu tên và composition. |
| `OrderAzureHandler` gắn `@Component` | Spring, được Azure adapter liên kết với Java Worker | Xử lý invocation được Azure trigger kích hoạt. |
| `ExecutionContext` | Azure Functions runtime | Metadata và logger của **từng invocation**. |
| `HttpRequestMessage<T>` | Azure Functions runtime/binding | Truy cập HTTP body, headers, query và tạo response. |

**Lưu ý:** `@Component` không tự tạo Azure HTTP endpoint; `@FunctionName` không tự tạo bean Spring. Handler cần **cả hai trách nhiệm**: Spring quản lý instance và Azure nhận diện method có trigger/binding.

### 2.2. Cơ chế injector

Azure Java Functions có **`FunctionInstanceInjector`** trong Java SPI để các DI frameworks cung cấp instance của lớp chứa handler. Adapter Spring Cloud Function Azure tích hợp với cơ chế này để dùng Spring-managed handler. Trong ứng dụng bình thường, **không tự viết một `FunctionInstanceInjector` riêng** hoặc tự gọi `new OrderAzureHandler(...)` nếu đang dùng adapter chính thức.

Nếu Azure tìm được method nhưng injector không tạo được bean, function vẫn có thể thất bại khi invocation đầu tiên. Hãy chẩn đoán cả **Azure discovery** và **Spring context creation**, không chỉ nhìn annotation `@FunctionName`.

## 3. Phụ thuộc và điều kiện phiên bản

Mô hình handler `@Component` dùng Spring DI qua adapter được tài liệu Spring Cloud Function mô tả cho **SCF 4.0.0+**. Chọn Spring Boot, Spring Cloud BOM, Azure Functions runtime và Java target **tương thích với nhau**; không ghép tùy tiện các major versions.

### 3.1. Maven dependencies

Với project đã cấu hình Spring Boot parent và Spring Cloud BOM phù hợp:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-function-adapter-azure</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
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

Version `1.3.1` của Azure Java library là **mốc minh họa API**, không phải khẳng định bản mới nhất. Khi làm dự án mới, lấy version của Java library và Azure plugin từ template/release notes đang được tổ chức sử dụng. Version SCF adapter nên được Spring Cloud BOM quản lý đồng bộ với `spring-cloud-function-context`.

| Thành phần | Mục đích |
| --- | --- |
| `spring-cloud-function-adapter-azure` | Spring/SCF dependency injection cho Java Azure Functions. |
| `spring-cloud-function-context` | `FunctionCatalog`, registration và composition; thường là dependency bắc cầu của adapter. |
| `spring-boot-starter` | Spring context, dependency injection, cấu hình ứng dụng; không yêu cầu embedded HTTP server. |
| `azure-functions-java-library` | `@FunctionName`, trigger annotations, `HttpRequestMessage` và `ExecutionContext`. |
| `azure-functions-maven-plugin` | Build plugin sinh `function.json`, staging layout và package; **không phải runtime dependency**. |
| `spring-boot-starter-test` | JUnit/Spring integration tests. |

Không cần thêm `spring-boot-starter-web` chỉ để nhận một `@HttpTrigger`: Azure Host là HTTP runtime ở đây. Nếu muốn dùng các Spring MVC controllers và filters, hãy đánh giá adapter khác là `spring-cloud-function-adapter-azure-web`; đừng trộn hai chiến lược không có lý do.

### 3.2. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-adapter-azure'
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'com.microsoft.azure.functions:azure-functions-java-library:1.3.1'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Gradle cần dependency management cho Spring Boot/Cloud và plugin `com.microsoft.azure.azurefunctions` nếu dùng Gradle packaging. Chỉ chọn **một** quy trình Azure Maven/Gradle cho một project.

### 3.3. Không nhầm adapter với FunctionInvoker

Một số hướng dẫn cũ dùng lớp `FunctionInvoker`. Tài liệu SCF hiện hành đánh dấu hướng này là **deprecated**; với project mới nên viết **`@Component` handler + Azure `@FunctionName` annotations + injected service/catalog**.

## 4. Thiết kế bài toán ví dụ

Một công ty nhận đơn hàng theo dữ liệu text do HTTP trigger gửi:

~~~text
Input:  "  dh-401  |  1500000  "
Output: "DH-401|PRIORITY|1500000"
~~~

Quy tắc:

- Mã đơn không được rỗng, được `strip()` và đổi uppercase theo `Locale.ROOT`.
- Tổng tiền VND phải là số nguyên dương; input dùng dấu `|` để ngăn cách hai trường.
- Đơn từ **1.000.000 VND trở lên** được phân loại `PRIORITY`; còn lại `STANDARD`.
- Input sai định dạng là **validation error** (HTTP 400), không phải lỗi server.
- Logic chỉ nhận/trả kiểu Java domain; không chứa import của Azure SDK.

Hai endpoint được minh họa:

| Azure Function | HTTP route | Cách gọi |
| --- | --- | --- |
| `classifyByService` | `POST /api/orders/direct` | Handler → `OrderService` trực tiếp. |
| `classifyByCatalog` | `POST /api/orders/catalog` | Handler → `FunctionCatalog.lookup("parseOrder|routeOrder")`. |

Trong hệ thống production, thường chỉ cần **một** endpoint công khai cho cùng nghiệp vụ. Hai endpoint ở đây chỉ để người học so sánh đường đi.

### 4.1. Hai Java records

Tạo `src/main/java/example/azure/OrderData.java`:

~~~java
package example.azure;

record OrderCommand(String id, long totalVnd) {}

record OrderDecision(String id, long totalVnd, String lane) {}
~~~

Hai record có phạm vi truy cập package-private và handler/service cùng package `example.azure`, nên chúng được sử dụng hợp lệ trong bài. Nếu muốn tái sử dụng qua package/API khác, có thể chuyển mỗi record thành một `public record` trong tệp Java mang cùng tên.

### 4.2. Service nghiệp vụ được Spring quản lý

Tạo `src/main/java/example/azure/OrderService.java`:

~~~java
package example.azure;

import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    public OrderCommand parse(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Thiếu dữ liệu đơn");
        }

        String[] parts = raw.split("\\|", -1);
        if (parts.length != 2) {
            throw new IllegalArgumentException(
                    "Định dạng phải là orderId|totalVnd");
        }

        String id = parts[0].strip().toUpperCase(Locale.ROOT);
        String money = parts[1].strip();

        if (id.isEmpty()) {
            throw new IllegalArgumentException("Mã đơn không được rỗng");
        }

        final long total;
        try {
            total = Long.parseLong(money);
        }
        catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "Tổng tiền phải là số nguyên", ex);
        }

        if (total <= 0) {
            throw new IllegalArgumentException(
                    "Tổng tiền phải lớn hơn 0");
        }

        return new OrderCommand(id, total);
    }

    public OrderDecision classify(OrderCommand order) {
        if (order == null) {
            throw new IllegalArgumentException("Thiếu đối tượng đơn");
        }

        String lane = order.totalVnd() >= 1_000_000
                ? "PRIORITY" : "STANDARD";

        return new OrderDecision(
                order.id(),
                order.totalVnd(),
                lane);
    }
}
~~~

`@Service` là một stereotype của Spring, về bản chất là một loại `@Component` có ý nghĩa diễn đạt tầng nghiệp vụ. Nó **không** có nghĩa service này được tự động đăng ký là một function trong catalog: đối tượng `OrderService` không triển khai `java.util.function.Function`.

**Vì sao service riêng quan trọng?** Nếu nghiệp vụ nằm hết trong `@FunctionName`, việc đổi sang Queue Trigger, Spring Cloud Stream, HTTP adapter khác hoặc AWS Lambda phải sao chép code. Một service thuần Java giúp unit test, tái sử dụng và tập trung business rules.

## 5. Đăng ký Function beans từ Spring service

Tạo `src/main/java/example/azure/OrderFunctionConfig.java`:

~~~java
package example.azure;

import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctionConfig {

    @Bean
    public Function<String, OrderCommand> parseOrder(
            OrderService service) {
        return service::parse;
    }

    @Bean
    public Function<OrderCommand, OrderDecision> routeOrder(
            OrderService service) {
        return service::classify;
    }
}
~~~

Spring inject cùng một `OrderService` vào hai `@Bean` factory methods. Hai function beans được SCF nhận diện với tên `parseOrder` và `routeOrder`.

`FunctionCatalog` có thể:

~~~java
Function<String, OrderCommand> parser =
        catalog.lookup("parseOrder");

Function<OrderCommand, OrderDecision> classifier =
        catalog.lookup("routeOrder");

Function<String, OrderDecision> pipeline =
        catalog.lookup("parseOrder|routeOrder");
~~~

Vì đầu ra `OrderCommand` của `parseOrder` khớp đầu vào `OrderCommand` của `routeOrder`, composition là:

~~~mermaid
flowchart LR
    A["String: dh-401|1500000"] --> B["parseOrder"]
    B --> C["OrderCommand"]
    C --> D["routeOrder"]
    D --> E["OrderDecision"]
~~~

**Phân biệt rõ:**

- `OrderService` là một Spring service được tiêm trực tiếp.
- `parseOrder` và `routeOrder` là các bean `Function` do service cung cấp implementation.
- `FunctionCatalog` cung cấp **canonical function representation**, có thể kèm wrapper/type conversion/composition; nó không chỉ là `ApplicationContext.getBean("parseOrder")`.
- Không cần đăng ký handler Azure trong catalog. `@FunctionName` là Azure entrypoint, không phải SCF function name.

### 5.1. Vì sao không dùng composition sai thứ tự?

Chuỗi `routeOrder|parseOrder` sai hợp đồng:

~~~text
routeOrder:  OrderCommand → OrderDecision
parseOrder:  String → OrderCommand

routeOrder|parseOrder: OrderDecision không phải String
~~~

Composition SCF có khả năng conversion ở một số ranh giới, nhưng không được suy ra rằng mọi domain type đều tự chuyển thành mọi type khác. Một pipeline kiểu chặt chẽ cần test với payload thực tế và converter của adapter.

### 5.2. Supplier/Consumer cũng có thể dùng lại service

Ngoài `Function`, có thể tạo:

~~~java
@Bean
public Consumer<OrderCommand> auditOrder(OrderAuditService audit) {
    return audit::record;
}
~~~

Đây chỉ là **biến thể thiết kế**: cần có `OrderAuditService` nếu đưa code vào project. `Consumer<T>` kết thúc pipeline và không trả giá trị để làm HTTP response. Chẳng hạn `parseOrder|auditOrder` tạo **Consumer<String>`, không phải `Function<String,OrderDecision>`. Đừng dùng một consumer void làm request/reply endpoint mà vẫn kỳ vọng một `OrderDecision`.

## 6. Spring Boot entrypoint và phạm vi component scanning

Tạo `src/main/java/example/azure/AzureOrderApplication.java`:

~~~java
package example.azure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AzureOrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(AzureOrderApplication.class, args);
    }
}
~~~

Với các lớp đều ở `example.azure`:

- `@SpringBootApplication` sẽ quét `OrderService` (`@Service`).
- `OrderFunctionConfig` (`@Configuration`) tạo hai function beans.
- `OrderAzureHandler` (`@Component`, viết ở phần 7) được Spring tạo instance.
- SCF đăng ký các function beans vào catalog.
- Azure adapter sử dụng Spring context để cung cấp instance cho Azure Java Worker.

Không tự gọi `SpringApplication.run(...)` trong mỗi invocation; ứng dụng Azure chạy dưới Azure Host, còn Spring context cần được adapter khởi tạo và có thể được tái sử dụng trong vòng đời worker.

Khi handler nằm ngoài package gốc, có thể dùng `@ComponentScan` hoặc đặt lại cấu trúc package cho đúng. Nếu Spring không quét được service/handler, việc Azure discover method chưa đủ giúp dependency injection thành công.

## 7. Handler inject đồng thời OrderService và FunctionCatalog

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

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class OrderAzureHandler {

    private final OrderService orderService;
    private final Function<String, OrderDecision> pipeline;

    public OrderAzureHandler(
            OrderService orderService,
            FunctionCatalog catalog) {

        this.orderService = orderService;
        this.pipeline = Objects.requireNonNull(
                catalog.lookup("parseOrder|routeOrder"),
                "Không tìm thấy function composition");
    }

    @FunctionName("classifyByService")
    public HttpResponseMessage classifyByService(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION,
                    route = "orders/direct")
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        return respond(request, context,
                raw -> orderService.classify(
                        orderService.parse(raw)));
    }

    @FunctionName("classifyByCatalog")
    public HttpResponseMessage classifyByCatalog(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION,
                    route = "orders/catalog")
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        return respond(request, context, pipeline);
    }

    private HttpResponseMessage respond(
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context,
            Function<String, OrderDecision> operation) {

        String input = request.getBody().orElse("");

        try {
            OrderDecision result = operation.apply(input);
            String output = result.id() + "|"
                    + result.lane() + "|"
                    + result.totalVnd();

            return request.createResponseBuilder(HttpStatus.OK)
                    .header("Content-Type",
                            "text/plain; charset=utf-8")
                    .body(output)
                    .build();
        }
        catch (IllegalArgumentException invalid) {
            return request
                    .createResponseBuilder(HttpStatus.BAD_REQUEST)
                    .body("Dữ liệu đơn không hợp lệ")
                    .build();
        }
        catch (RuntimeException failure) {
            context.getLogger().log(
                    Level.SEVERE,
                    "Unexpected order processing error",
                    failure);
            return request.createResponseBuilder(
                            HttpStatus.INTERNAL_SERVER_ERROR)
                    .body("Không thể xử lý yêu cầu")
                    .build();
        }
    }
}
~~~

Hai phương thức Azure:

1. `classifyByService` dùng **`OrderService`** đã được Spring inject.
2. `classifyByCatalog` dùng **composition** trả về từ `FunctionCatalog`.
3. Cả hai đều tái sử dụng cùng hai quy tắc parse/phân loại và trả dữ liệu theo cùng một contract.
4. `respond(...)` là phần xử lý HTTP boundary: nhận body, phân biệt lỗi 400/500, tạo response.
5. `ExecutionContext` nằm ở **method parameter** do Azure runtime cấp cho từng invocation, không phải Spring singleton.
6. `@Component` thuộc **class** để Spring quản lý bean; `@FunctionName` thuộc **method** để Azure Host discover; `@HttpTrigger` thuộc **parameter** để khai báo HTTP binding.

### 7.1. Vì sao constructor injection?

Constructor injection làm dependency bắt buộc được xác định khi Spring tạo handler, thay vì chỉ phát hiện lỗi khi method được invoke. Field được khai báo `final` giúp giảm accidental mutation. `Objects.requireNonNull(...)` khiến sai tên composition **fail fast**.

Nếu hai function beans cùng kiểu `Function<String,String>` được inject trực tiếp, dùng `@Qualifier("beanName")` để tránh ambiguity; ví dụ handler chỉ inject `OrderService` và `FunctionCatalog` nên không gặp vấn đề này.

### 7.2. Kiểm tra HTTP status và log an toàn

- Input sai định dạng hoặc thiếu body → HTTP 400.
- Input hợp lệ và xử lý thành công → HTTP 200 với body mã đơn/loại/tổng tiền.
- Exception hạ tầng/không dự kiến → HTTP 500 và log server.
- Không trả stack trace hoặc thông tin nội bộ về FunctionCatalog cho client.
- Không dùng function key như cơ chế auth duy nhất cho hệ thống nhạy cảm; kiểm tra Function App authentication, API gateway, identity và quyền truy cập.
- Trong production, hãy có error schema và correlation ID thống nhất thay vì chỉ trả text như demo.

### 7.3. Vì sao không tra cứu catalog mỗi request?

Nếu definition cố định như `parseOrder|routeOrder`, resolve composition **một lần trong constructor** giúp phát hiện lỗi cấu hình sớm và tránh lookup lặp. Với Spring-managed singleton, pipeline là dependency dùng chung; nó phải **thread-safe** như service/function bên dưới.

Trường hợp definition thực sự cần chọn động nên có allowlist và authorization rõ ràng. Không lấy tên function trực tiếp từ query/header không tin cậy rồi gọi catalog tùy ý.

## 8. Chạy thử và quan sát hai đường đi

Giả sử Azure Functions Host chạy local ở cổng mặc định:

~~~text
POST http://localhost:7071/api/orders/direct
POST http://localhost:7071/api/orders/catalog
~~~

Gửi cùng request tới từng endpoint:

~~~bash
curl -i -X POST "http://localhost:7071/api/orders/direct" \
  -H "Content-Type: text/plain" \
  --data "  dh-401  |  1500000  "
~~~

~~~bash
curl -i -X POST "http://localhost:7071/api/orders/catalog" \
  -H "Content-Type: text/plain" \
  --data "  dh-401  |  1500000  "
~~~

Kết quả mong đợi của cả hai:

~~~text
HTTP/1.1 200 OK

DH-401|PRIORITY|1500000
~~~

Thử các trường hợp khác:

| Input | Kết quả hợp lệ | HTTP |
| --- | --- | --- |
| `"dh-402|500000"` | `DH-402|STANDARD|500000` | 200 |
| `" dh-403 | 1000000 "` | `DH-403|PRIORITY|1000000` | 200 |
| `"  | 100000 "` | Không có mã đơn | 400 |
| `"dh-404|abc"` | Tổng tiền không là số nguyên | 400 |
| `"dh-405|0"` | Tổng tiền không dương | 400 |
| `"dh-406"` | Thiếu dấu phân cách/tổng tiền | 400 |
| Body rỗng | Không có dữ liệu hợp lệ | 400 |

**Không cần hai copy của business rule** để có hai Azure endpoints. Khác biệt là một bên gọi injected service, bên kia gọi SCF-wrapped composed function.


## 9. Kiểm thử độc lập Azure: từ service tới FunctionCatalog

Dependency injection cho phép kiểm thử các lớp khác nhau mà **không cần Azure subscription**.

### 9.1. Unit test OrderService

Tạo `src/test/java/example/azure/OrderServiceTest.java`:

~~~java
package example.azure;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class OrderServiceTest {

    private final OrderService service = new OrderService();

    @Test
    void normalizesAndClassifiesPriorityOrder() {
        OrderCommand order =
                service.parse("  dh-401  | 1500000 ");

        assertEquals("DH-401", order.id());
        assertEquals(1_500_000L, order.totalVnd());

        OrderDecision result = service.classify(order);
        assertEquals("PRIORITY", result.lane());
    }

    @Test
    void classifiesStandardOrder() {
        OrderDecision result = service.classify(
                service.parse("dh-402|500000"));

        assertEquals("STANDARD", result.lane());
        assertEquals("DH-402", result.id());
    }

    @Test
    void rejectsInvalidInput() {
        assertThrows(IllegalArgumentException.class,
                () -> service.parse("  | 100000 "));
        assertThrows(IllegalArgumentException.class,
                () -> service.parse("dh-403|abc"));
        assertThrows(IllegalArgumentException.class,
                () -> service.parse("dh-403|0"));
    }
}
~~~

Unit test xác minh quy tắc nghiệp vụ, không kiểm tra Spring context, Azure Host, function binding hoặc JSON serialization. Khi chuyển sang Queue Trigger, các quy tắc parse/phân loại vẫn được xác minh bằng cùng bộ test.

### 9.2. Kiểm tra Spring context và catalog composition

Tạo `src/test/java/example/azure/OrderCatalogTest.java`:

~~~java
package example.azure;

import java.util.function.Function;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = AzureOrderApplication.class)
class OrderCatalogTest {

    @Autowired
    OrderService orderService;

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    OrderAzureHandler azureHandler;

    @Test
    void serviceAndHandlerAreSpringBeans() {
        assertNotNull(orderService);
        assertNotNull(azureHandler);
    }

    @Test
    void catalogComposesFunctionsUsingService() {
        Function<String, OrderDecision> pipeline =
                catalog.lookup("parseOrder|routeOrder");

        assertNotNull(pipeline);

        OrderDecision result =
                pipeline.apply(" dh-401 | 1500000 ");

        assertEquals("DH-401", result.id());
        assertEquals("PRIORITY", result.lane());
        assertEquals(1_500_000L, result.totalVnd());
    }
}
~~~

Test này chứng minh Spring scan được `OrderService` và handler; hai `Function` beans được catalog nhận diện; và composition có hợp đồng kiểu tương thích. Handler constructor dùng `Objects.requireNonNull(...)`, nên typo trong definition có thể làm **Spring test context thất bại ở startup** — đó là *fail fast* hữu ích.

### 9.3. Kiểm tra Azure annotations nhưng không nhầm với Host-level test

Một test reflection có thể xác nhận hai phương thức Azure:

~~~java
@Test
void handlerMethodsExposeDistinctAzureNames()
        throws NoSuchMethodException {

    var direct = OrderAzureHandler.class.getMethod(
            "classifyByService",
            HttpRequestMessage.class,
            ExecutionContext.class);

    var catalog = OrderAzureHandler.class.getMethod(
            "classifyByCatalog",
            HttpRequestMessage.class,
            ExecutionContext.class);

    assertEquals("classifyByService",
            direct.getAnnotation(FunctionName.class).value());
    assertEquals("classifyByCatalog",
            catalog.getAnnotation(FunctionName.class).value());
}
~~~

Cần các import Azure types, `FunctionName`, JUnit Assertions. Test này **không** chứng minh build plugin sinh `function.json` hay host đã discover đúng các function.

### 9.4. Ma trận integration test ở Azure Functions Host local

Sau khi Azure Maven/Gradle plugin package, chạy Azure Functions Core Tools v4 và gửi POST đến hai routes.

| Kiểm thử | Kỳ vọng |
| --- | --- |
| Input hợp lệ đến endpoint service | HTTP 200 và body đúng. |
| Cùng input đến endpoint catalog | Cùng kết quả nghiệp vụ. |
| Sai định dạng, mã rỗng, tổng tiền không hợp lệ | HTTP 400, không lộ stack trace. |
| GET đến route chỉ khai báo POST | Không được xử lý như POST hợp lệ. |
| Thiếu function key trên Azure cloud | Bị từ chối theo authorization policy. |
| Spring context lỗi | Log chỉ rõ dependency hoặc catalog lookup thất bại. |
| Azure Host không nhận ra method | Kiểm metadata từ annotations/plugin. |
| Thay JDK target hoặc runtime | Kiểm compile target và Java runtime tương thích. |

`@SpringBootTest` không khởi động Azure Worker. Đặc biệt, nếu HTTP service hoạt động nhưng catalog fails, bạn cần kiểm tra Spring function registration thay vì sửa HTTP annotation.

## 10. Khi nào inject service, function bean hay catalog?

Không phải mọi handler đều cần tất cả loại dependency.

| Nhu cầu | Inject nên chọn | Lý do |
| --- | --- | --- |
| Nhiều phương thức nghiệp vụ, validation và repository | `OrderService` hoặc service interface | Phân tầng, dễ unit test và mock. |
| Một phép biến đổi cố định | `Function<T,R>`, thêm `@Qualifier` khi cần | Đơn giản, không cần catalog lookup. |
| Ghép nhiều phép biến đổi | `FunctionCatalog` | Composition và SCF wrapper. |
| Definition cấu hình có kiểm soát | `FunctionCatalog` với allowlist | Linh hoạt nhưng cần validation và authorization. |
| Side effect không cần reply | `Consumer<T>` hoặc domain service | Phù hợp event/queue nhưng có contract lỗi/ack riêng. |
| Phát dữ liệu khi Timer kích hoạt | `Supplier<T>` được handler gọi | Azure vẫn cần Timer Trigger. |

### 10.1. Nhiều bean Function giống generic type

Giả sử có hai bean:

~~~java
@Bean
Function<String, String> trimCode() {
    return String::strip;
}

@Bean
Function<String, String> upperCode() {
    return String::toUpperCase;
}
~~~

Inject chỉ theo `Function<String,String>` có thể gây ambiguity. Dùng qualifier:

~~~java
@Component
class ExampleDependency {

    private final Function<String, String> trim;

    ExampleDependency(
            @Qualifier("trimCode")
            Function<String, String> trim) {
        this.trim = trim;
    }
}
~~~

Đây là một **fragment minh họa**, không cần thêm class này vào demo chính. Import `org.springframework.beans.factory.annotation.Qualifier`. Với nhiều service implementations, có thể dùng `@Qualifier` hoặc `@Primary` khi có ý nghĩa thiết kế, nhưng đừng dùng `@Primary` chỉ để che giấu việc chọn nhầm service.

### 10.2. FunctionCatalog không phải bản đồ mọi Spring bean

`FunctionCatalog` không thay thế `ApplicationContext`. `OrderService` là bean nghiệp vụ bình thường; nó không tự được catalog đăng ký vì không phải functional bean. Nếu cần xuất bản nghiệp vụ theo mô hình hàm, khai báo:

~~~java
@Bean
Function<OrderCommand, OrderDecision> routeOrder(
        OrderService service) {
    return service::classify;
}
~~~

SCF sẽ nhận diện `Function` bean, trong khi service vẫn giữ trách nhiệm về quy tắc nghiệp vụ.

### 10.3. Catalog không tạo HTTP route

`catalog.lookup("parseOrder|routeOrder")` chỉ giải quyết **function definition**. HTTP route đến từ `@HttpTrigger(route = "orders/catalog")` và Azure Function name từ `@FunctionName`.

Không cho request không tin cậy gọi tùy ý:

~~~java
// Không nên làm nếu không có allowlist/authorization:
String definition =
        request.getQueryParameters().get("function");
catalog.lookup(definition);
~~~

Với routing động, hãy dùng allowlist tên/kiểu function, xác thực caller, giới hạn quyền và audit. Một số cơ chế routing SCF cho phép biểu thức, nên càng cần kiểm soát đầu vào không tin cậy.

## 11. Scope, vòng đời bean và concurrency trên Azure

### 11.1. Spring singleton khác Azure invocation

`@Service` và `@Component` mặc định dùng singleton scope trong Spring context. Một Azure Java Worker có thể tái sử dụng context/handler qua nhiều invocation; Azure cũng có thể chạy song song và scale nhiều worker instances.

- `OrderService` trong demo là **stateless**.
- `pipeline` được giữ ở một field `final`, nhưng các function/service bên dưới cũng phải an toàn khi concurrent.
- Không đưa request body, trace ID, token hoặc `ExecutionContext` vào mutable field của handler.
- Một Spring singleton không phải kho dữ liệu chia sẻ bền vững giữa nhiều Azure instances.
- Với state thật, sử dụng database/queue/store phù hợp và chiến lược transaction/concurrency.

Ví dụ sai:

~~~java
@Service
class UnsafeService {

    private String lastOrderId;

    String normalize(String id) {
        lastOrderId = id.strip();
        return lastOrderId;
    }
}
~~~

Khi nhiều invocation cùng gọi, field có thể bị ghi đè. Đây là phản ví dụ, không đưa vào code production.

### 11.2. ExecutionContext thuộc từng invocation

`ExecutionContext` do Azure runtime tạo ra, thích hợp để lấy invocation ID và logger:

~~~java
context.getLogger().info(
        "Invocation: " + context.getInvocationId());
~~~

Không inject `ExecutionContext` vào constructor của Spring singleton. Trong SCF có tiện ích `AzureFunctionUtil.enhanceInputIfNecessary(...)` để thêm context vào header của `Message<?>` khi function thực sự có hợp đồng message-aware. Nhưng khi nghiệp vụ không cần metadata Azure, giữ `ExecutionContext` ở handler sẽ giúp function dùng lại dễ hơn.

### 11.3. Cold start và dependency graph

Khởi tạo Spring application context trong Azure Worker có thể tăng **cold start latency**, nhất là khi nhiều starter/auto-configuration hoặc bean constructors thực hiện I/O chặn lâu.

1. Chỉ đưa các dependency cần thiết vào classpath.
2. Không tạo Spring context mới trong mỗi invocation.
3. Không dùng constructor để chạy một workflow hoặc phát event.
4. Quản lý HTTP/database clients theo lifecycle và thread-safety phù hợp.
5. Đo startup time, memory và độ trễ trên hosting plan thực tế.
6. Phân biệt lỗi khởi tạo bean với lỗi nghiệp vụ sau khi handler đã được gọi.

## 12. Tiêm cấu hình và phụ thuộc ngoài

Một service có thể cần threshold, repository, API client hoặc secret. Nên dùng Spring DI và Azure App Settings/managed identity, thay vì hard-code thông tin cấu hình tại Azure handler.

### 12.1. Thay threshold bằng cấu hình

Biến thể của `OrderService` (thay thế constructor/logic cũ, **không tạo hai bean cùng tên**):

~~~java
@Service
public class OrderService {

    private final long priorityThreshold;

    public OrderService(
            @Value("${orders.priority-threshold:1000000}")
            long priorityThreshold) {
        this.priorityThreshold = priorityThreshold;
    }

    // Các phương thức parse/classify đã trình bày ở mục 4
    // cần dùng priorityThreshold thay cho hằng 1_000_000.
}
~~~

Cần import `org.springframework.beans.factory.annotation.Value`. Biến thể chỉ mô tả cách inject cấu hình, **không phải class đầy đủ có thể copy riêng**. Trong `application.properties`:

~~~properties
orders.priority-threshold=1000000
~~~

Trên Azure, sử dụng Function App settings để cung cấp cấu hình theo môi trường. Khi dùng environment variable naming convention, hãy xác minh Spring Boot thực sự bind giá trị mong muốn ở release train đang chạy trước khi dựa vào nó.

### 12.2. Service phụ thuộc repository có cần catalog không?

Không. Repository và HTTP client có thể là các Spring beans thông thường:

~~~java
@Service
class OrderAuditService {

    private final AuditRepository repository;

    OrderAuditService(AuditRepository repository) {
        this.repository = repository;
    }

    void record(OrderDecision decision) {
        repository.save(decision);
    }
}
~~~

Đây là **pseudocode thiết kế**; cần định nghĩa `AuditRepository`/`save(...)` thật nếu thêm vào project. `FunctionCatalog` quản lý mô hình chức năng `Supplier`/`Function`/`Consumer`; các service/repository vẫn dùng Spring DI.

### 12.3. Secrets và quyền truy cập

- Không commit `local.settings.json` chứa connection strings/tokens.
- Sử dụng Azure App Settings, managed identity/Key Vault hoặc cơ chế secret management thích hợp.
- Không để function key trong log hoặc response body.
- Đừng nhầm **có thể inject service** với **đã có quyền truy cập Azure Storage/Database**.
- Cấu hình quyền, connection và retry theo từng adapter và dịch vụ ngoài.


## 13. Tái sử dụng service và catalog từ Queue Trigger

Hai HTTP endpoints ở phần 7 phục vụ so sánh hai kiểu injection. Nhưng cùng **`OrderService`** và composition `parseOrder|routeOrder` có thể được gọi bởi một Azure Storage Queue Trigger mà không sao chép business rules.

Ví dụ **phương thức bổ sung** vào `OrderAzureHandler`:

~~~java
@FunctionName("classifyQueuedOrder")
public void classifyQueuedOrder(
        @QueueTrigger(
                name = "order",
                queueName = "orders-input",
                connection = "AzureWebJobsStorage")
        String rawOrder,

        @QueueOutput(
                name = "decision",
                queueName = "orders-decisions",
                connection = "AzureWebJobsStorage")
        OutputBinding<String> output,

        ExecutionContext context) {

    OrderDecision decision = pipeline.apply(rawOrder);

    output.setValue(
            decision.id() + "|"
            + decision.lane() + "|"
            + decision.totalVnd());
}
~~~

Cần thêm imports:

~~~java
import com.microsoft.azure.functions.OutputBinding;
import com.microsoft.azure.functions.annotation.QueueOutput;
import com.microsoft.azure.functions.annotation.QueueTrigger;
~~~

Phương thức này chỉ chạy khi có Azure Storage extension, connection settings, các queue nguồn/đích và package metadata phù hợp. Nó là **phần mở rộng tùy chọn**, không cần cho hai HTTP routes của demo chính.

### 13.1. Điểm khác biệt về ngữ nghĩa lỗi

Ở HTTP handler, `IllegalArgumentException` được chuyển thành **HTTP 400** cho caller. Với Queue Trigger, nếu một exception được ném từ pipeline, Azure Functions Host/extension quyết định retry/poison-message theo cấu hình. Vì vậy:

- Không tự catch mọi exception rồi chỉ log và trả `void` thành công nếu mong Azure retry.
- Dữ liệu validation sai thường không thể sửa bằng retry vô hạn; cần quarantine/dead-letter/poison-message có chủ đích.
- `OutputBinding.setValue(...)` chỉ đặt giá trị cho binding, không đảm bảo transaction phân tán với thao tác DB trong service.
- Message có thể được giao lại; dùng event ID/business key để chống side effect trùng.
- Nếu queue message ở định dạng JSON hoặc CloudEvents, cần giải mã đúng ở **adapter boundary** trước khi gọi `Function<String,OrderDecision>`.

### 13.2. Khi nào dùng Supplier hoặc Consumer?

Một `Supplier<OrderCommand>` có thể được Timer Trigger gọi để lấy dữ liệu, nhưng **Supplier không tự tạo Timer schedule**. Một `Consumer<OrderDecision>` có thể gọi `OrderAuditService` để ghi audit khi Queue Trigger kích hoạt, nhưng **Consumer không trả response**. Muốn HTTP request/reply, handler phải dùng function/service có kết quả hoặc chủ động tạo phản hồi.

~~~java
@Bean
Consumer<OrderDecision> auditDecision(
        OrderAuditService audit) {
    return audit::record;
}
~~~

Đây là biến thể có dependency `OrderAuditService` được định nghĩa trong phần 12, không phải bean bổ sung cần thiết cho demo chạy tối thiểu. Composition `parseOrder|routeOrder|auditDecision` sẽ là một **Consumer<String>**, không còn `Function<String,OrderDecision>`.

## 14. Đóng gói và khởi động Spring context trên Azure

Việc Spring đã inject thành công trong `@SpringBootTest` **không bảo đảm** Azure Functions Host nhận ra function. Azure plugin phải tạo binding metadata `function.json` từ Java annotations và package đúng layout.

### 14.1. Chỉ rõ main class

Với Maven:

~~~xml
<properties>
    <java.version>17</java.version>
    <start-class>example.azure.AzureOrderApplication</start-class>
</properties>
~~~

Có thể đặt `MAIN_CLASS=example.azure.AzureOrderApplication` trong local/Azure application settings. Adapter có thể tìm main class qua manifest khi không chỉ định, nhưng việc khóa tường minh tránh mơ hồ khi có nhiều Spring Boot configurations trong classpath.

### 14.2. Cấu hình Maven plugin

Đây là **fragment** cần kết hợp với POM có Boot parent và Cloud BOM phù hợp:

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
                <appName>orders-functions-unique-demo</appName>
                <resourceGroup>orders-example-rg</resourceGroup>
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

`1.22.0` là mốc Azure Maven plugin được tài liệu Spring Cloud Function dùng làm **mức tối thiểu tham khảo**, không phải phiên bản mới nhất. Thay tên app/resource group/region và kiểm tra runtime, hosting plan, Azure Java SDK/library phù hợp trước khi triển khai.

**Lý do tắt Boot repackage:** Azure Java Worker mong layout do Azure plugin tạo; một **Spring Boot repackaged executable fat JAR** mặc định không cùng định dạng đó. Nếu dùng cách packaging khác, phải theo hướng dẫn adapter của phiên bản đang triển khai.

### 14.3. host.json và local.settings.json

`src/main/resources/host.json` đơn giản:

~~~json
{
  "version": "2.0"
}
~~~

`local.settings.json` khi phát triển:

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

`UseDevelopmentStorage=true` thường cần **Azurite** khi Azure Host hoặc trigger dùng Storage emulator. Đừng commit file chứa credentials thật. Trên cloud, sử dụng Function App settings, managed identity và secret management theo chính sách vận hành.

### 14.4. Package và chạy local

~~~bash
./mvnw clean package
./mvnw azure-functions:run
~~~

Với Gradle khi đã có Azure Functions plugin và cấu hình runtime tương ứng:

~~~bash
./gradlew azureFunctionsPackage
./gradlew azureFunctionsRun
~~~

Azure Host cần nhận được **`classifyByService`** và **`classifyByCatalog`** dưới hai function definitions riêng. Nếu không, hãy kiểm tra Azure plugin output, annotation scanning và `function.json`, không chỉ log của Spring component scanning.

Lệnh deploy như `./mvnw azure-functions:deploy` có thể thay đổi tài nguyên và chi phí đám mây. Bài này chỉ giải thích quy trình, không thực hiện deploy hoặc chạy build trong STEP 4.

## 15. Troubleshooting: phân biệt ba tầng lỗi

| Triệu chứng | Tầng có khả năng lỗi | Cách chẩn đoán |
| --- | --- | --- |
| Azure Host không liệt kê handler | **Azure discovery/package** | Kiểm `@FunctionName`, trigger, method public, Azure Maven/Gradle plugin, `function.json`. |
| Host liệt kê function nhưng không xử lý HTTP | **Azure route/auth** | Kiểm POST, URL prefix, function key, host/runtime settings. |
| Constructor handler không được Spring quản lý | **Adapter/DI** | Kiểm `@Component`, `spring-cloud-function-adapter-azure`, main class và Java Worker integration. |
| `NoSuchBeanDefinitionException` với OrderService | **Spring component scanning** | Kiểm `@Service` và package `example.azure`. |
| `NoSuchBeanDefinitionException` với FunctionCatalog | **SCF context** | Kiểm adapter version, dependencies, Boot/Cloud BOM, auto-configuration. |
| `catalog.lookup("parseOrder|routeOrder")` trả null | **Catalog registration** | Kiểm tên `@Bean`, definition và generic input/output. |
| Inject nhiều `Function<String,String>` bị mơ hồ | **Spring bean resolution** | Dùng `@Qualifier` hoặc thiết kế bean rõ ràng. |
| HTTP 400 dù tưởng input đúng | **Input contract** | Kiểm dấu `|`, khoảng trắng, numeric parse và validation. |
| `ClassCastException` khi gọi composition | **Type conversion** | Kiểm wrapper SCF, generic signature, serialized payload và catalog test. |
| Spring test PASS nhưng Azure Worker lỗi | **Packaging/runtime** | Kiểm JAR layout, main class, Java target và dependencies. |
| Cold start chậm | **Application context** | Giảm starter không cần, kiểm I/O khi tạo bean, đo startup. |
| Queue event bị xử lý lặp | **Delivery/retry semantics** | Kiểm idempotency key và Queue Trigger poison/retry policy. |
| Dữ liệu hai requests bị trộn | **Concurrency** | Loại field mutable khỏi singleton service/handler. |
| Có `@Bean Function` nhưng không có HTTP endpoint | **Azure annotation** | `@Bean` không tạo `@FunctionName` hoặc `@HttpTrigger`. |

### 15.1. Thứ tự điều tra khuyến nghị

1. Azure Maven/Gradle plugin đã tạo metadata cho hai `@FunctionName` chưa?
2. Azure Host có discover đúng tên method, trigger và route chưa?
3. Spring adapter/runtime classpath đã có và các phiên bản tương thích chưa?
4. `AzureOrderApplication` được chọn đúng làm main class chưa?
5. Spring có quét được service, function configuration và handler không?
6. Constructor có inject được `OrderService` và `FunctionCatalog` không?
7. Catalog có hai functions và composition đúng kiểu không?
8. HTTP body, output, security, retry và environment settings có đúng không?

Phân loại theo thứ tự trên giúp không nhầm **Azure discovery**, **Spring dependency injection**, **SCF function lookup** và **business validation**.

## 16. Bài tập thực hành và câu hỏi tự đánh giá

### Bài tập

1. **Thay đổi rule:** chuyển ngưỡng đơn ưu tiên sang Spring configuration; xác minh cả hai endpoints nhận cùng kết quả.
2. **Thêm function:** tạo `Function<OrderDecision,String> formatDecision`, ghép `parseOrder|routeOrder|formatDecision` và so sánh output với response builder trong handler.
3. **Thử lỗi dependency:** tạm bỏ `@Service` khỏi `OrderService`, chạy Spring context test rồi giải thích root cause.
4. **Thử lỗi tên:** đổi composition sang `parseOrder|missingRoute` và kiểm tra fail-fast ở constructor.
5. **Qualifier:** tạo hai bean `Function<String,String>` rồi thử inject không qualifier/sau khi thêm qualifier.
6. **Queue reuse:** thêm method `classifyQueuedOrder`, kiểm tra input validation, retry, idempotency và output binding.
7. **Concurrency:** thử thêm mutable field vào service, chạy nhiều requests và sửa thành stateless.
8. **Lỗi hạ tầng:** thêm một service phụ thuộc API ngoài, thiết kế retry/backoff giới hạn và response mapping.
9. **Đọc Azure package:** tìm `function.json` của hai routes và so sánh Azure metadata với Spring bean definitions.
10. **Thay text bằng JSON:** tách serializer/validator ở handler, giữ service độc lập Azure SDK.

### Tự đánh giá

- Vì sao `@Service OrderService` không tự có tên trong `FunctionCatalog`?
- Vì sao cùng handler có thể inject service thông thường và catalog?
- Khác biệt giữa lấy một function bean trực tiếp với `catalog.lookup("parseOrder")` là gì?
- Tại sao `parseOrder|routeOrder` phù hợp nhưng `routeOrder|parseOrder` không phải composition type-safe?
- Vì sao không được tự gọi `SpringApplication.run(...)` trong mỗi invocation?
- `ExecutionContext` được Azure cung cấp khi nào và vì sao không nên giữ trong singleton?
- Khi Spring test PASS mà Azure Host không thấy function, phải điều tra lớp nào?
- Với Queue Trigger, vì sao catch mọi exception rồi trả thành công có thể làm mất cơ hội retry?
- Vì sao không cho client tự do chỉ định tên function lookup qua query?
- Làm sao dùng lại cùng `OrderService` qua HTTP, Queue và serverless khác mà không trộn Azure API vào domain layer?

## 17. Tài liệu tham khảo chính thức

- [Spring Cloud Function — Microsoft Azure Functions](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): `@Component`, injected services, `FunctionCatalog`, Azure Java Worker, main class và packaging.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `Supplier`, `Function`, `Consumer`, catalog wrapping, composition và type conversion.
- [Microsoft Learn — Azure Functions Java Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-java): `@FunctionName`, `FunctionInstanceInjector`, Java triggers/bindings và runtime.
- [Microsoft Learn — Azure HTTP Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-http-webhook-trigger): HTTP request/response, route, authorization levels.
- [Microsoft Learn — Run Functions Locally](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local): Functions Core Tools và local testing.
- [Microsoft Learn — Azure Functions Java Quickstart](https://learn.microsoft.com/en-us/azure/azure-functions/create-first-function-cli-java): Maven package/run/deploy và metadata.
- [Microsoft Learn — Azure Storage Queue Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-queue-trigger): retry, poison queue và semantics khác HTTP.
- [Spring Cloud Function Azure samples](https://github.com/spring-cloud/spring-cloud-function/tree/main/spring-cloud-function-samples): HTTP/Blob/Timer examples và các biến thể adapter.

**Kết luận:** Spring dependency injection cho phép Azure handler gọi **business service thông thường**, còn `FunctionCatalog` cung cấp cách gọi **`Supplier`, `Function` và `Consumer` qua tên/composition**. Giữ logic trong service, xuất bản các phép biến đổi thành function beans khi cần, rồi inject service/catalog vào `@Component` chứa `@FunctionName` methods. Việc tách DI, function lookup và Azure trigger/binding giúp một logic được tái sử dụng qua HTTP, sự kiện và serverless mà vẫn kiểm soát kiểu dữ liệu, vòng đời bean, retry, idempotency và bảo mật.

