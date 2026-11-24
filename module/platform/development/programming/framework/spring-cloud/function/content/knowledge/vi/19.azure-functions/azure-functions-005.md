# Phân biệt gọi bean trực tiếp với gọi hàm qua catalog

## 1. Tại sao hai cách gọi lại quan trọng trong Azure Functions?

**Spring Cloud Function (SCF)** tổ chức nghiệp vụ bằng các interface Java `Supplier<T>`, `Function<T,R>` và `Consumer<T>`. Các hàm có thể dùng chung qua nhiều giao thức, ghép nhiều bước với nhau và được tra cứu qua `FunctionCatalog`. Đây chính là cách xây logic tái sử dụng để một nghiệp vụ phục vụ HTTP, sự kiện hoặc một nền tảng serverless mà không viết lại phần xử lý cốt lõi.

Trong **Azure Functions**, phương thức Java `@FunctionName` là entrypoint được Azure Java Worker gọi khi có trigger. Với `spring-cloud-function-adapter-azure`, một handler gắn `@Component` được Spring quản lý và có thể **inject trực tiếp bean Function** hoặc **inject FunctionCatalog để lookup**.

Cả hai cách đều hợp lệ, nhưng **không tương đương hoàn toàn**:

- **Gọi bean trực tiếp:** `rawFunction.apply(input)` thực thi chính object mà Spring tạo từ `@Bean`; không mặc nhiên đi qua SCF wrapper.
- **Gọi qua catalog:** `catalog.lookup("name").apply(input)` thực thi biểu diễn *canonical* đã được Spring Cloud Function bọc, có cơ chế bổ sung như composition, quản lý chữ ký và type/message conversion trong những ngữ cảnh được hỗ trợ.
- **Gọi composition qua catalog:** `catalog.lookup("first|second|third")` tạo một pipeline hàm theo thứ tự, tránh việc handler phải tự nối từng bước.

Mục tiêu bài học là so sánh **từng đường gọi cụ thể trong Azure handler**, không xem catalog là phiên bản “tốt hơn trong mọi hoàn cảnh”.

### Kết quả cần đạt

Sau khi học, bạn có thể:

1. Phân biệt Spring bean `Function` gốc với function wrapper trong `FunctionCatalog`.
2. Viết handler Azure inject bean trực tiếp và handler Azure inject catalog, đều dùng lại một business pipeline.
3. Giải thích thứ tự `a|b|c`, chữ ký kiểu và giới hạn conversion.
4. Quyết định khi nào dùng direct DI, khi nào dùng catalog/composition.
5. Biết `@FunctionName`, `@HttpTrigger`, `@Bean` và tên catalog thuộc **những không gian tên khác nhau**.
6. Xử lý null lookup, lỗi parse/conversion, message headers, invocation context, concurrency và security.
7. Kiểm thử tách biệt Java function, Spring bean registration, catalog wrapper và Azure Host.

## 2. Bảng so sánh nhanh

| Khía cạnh | Bean trực tiếp | FunctionCatalog |
| --- | --- | --- |
| Cách lấy | `@Qualifier("parseOrder") Function<...>` hoặc `applicationContext.getBean(...)`. | Inject `FunctionCatalog` rồi `lookup("parseOrder")`. |
| Đối tượng nhận | **Bean gốc** do Spring khởi tạo. | **Biểu diễn đã được SCF bọc** (canonical/instrumented). |
| Gọi nghiệp vụ | `bean.apply(input)`. | `catalogFunction.apply(input)`. |
| Ghép nhiều bước | Java `andThen(...)` hoặc gọi tuần tự. | `lookup("parseOrder|classifyOrder|formatOrder")`. |
| Kiểu và conversion | Theo Java generic của bean, caller tự chuẩn hóa input. | SCF có wrapper/conversion hỗ trợ những chữ ký và media type nhất định. |
| Message metadata | Chỉ thấy header nếu bean nhận `Message<T>`. | Wrapper có hỗ trợ message-aware signatures; vẫn cần adapter truyền header đúng. |
| Điểm mạnh | Minh bạch, type-safe với compile-time contract, ít abstraction. | Reuse đa adapter, composition theo tên, contract/adapter thống nhất. |
| Rủi ro | Quên chuyển đổi body, lặp logic nối function trong handlers. | Lookup sai tên, ỷ lại conversion, cấu hình động không được kiểm soát. |
| Azure trigger/binding | **Không tự tạo**. | **Cũng không tự tạo**. |

**Kết luận quan trọng:** Nếu một bean là `Function<String,String>`, cả hai cách có thể trả **cùng dữ liệu** với đầu vào `String` phù hợp. Sự khác biệt về **đường thực thi và khả năng framework bổ sung** không có nghĩa mọi lần gọi catalog đều biến đổi kết quả hoặc luôn nhanh/chậm hơn direct call.

## 3. Sơ đồ hai đường đi

~~~mermaid
flowchart LR
    A["HTTP request"] --> B["Azure Functions Host / Java Worker"]
    B --> C["@Component handler có @FunctionName"]
    S["Spring ApplicationContext"] --> D["@Bean parseOrder"]
    S --> E["@Bean classifyOrder"]
    S --> F["@Bean formatOrder"]
    S --> G["FunctionCatalog"]
    D --> G
    E --> G
    F --> G
    C -->|"direct: parse→classify→format"| D
    D -. "raw Java function" .-> E
    E -. "raw Java function" .-> F
    C -->|"catalog.lookup('parseOrder|classifyOrder|formatOrder')"| G
    G --> H["SCF canonical composed function"]
    H --> I["HTTP response"]
    F --> I
~~~

**Điểm cần ghi nhớ về quyền sở hữu:**

- `@Bean` đăng ký function như một **Spring bean**.
- `FunctionCatalog` tìm các **functional beans** và trình bày chúng qua lớp wrapper, theo cơ chế SCF.
- `@Component` đưa Azure handler vào Spring component scanning/dependency injection.
- `@FunctionName` và `@HttpTrigger` cho Azure nhận diện **một function handler/HTTP route**.
- Azure Maven/Gradle plugin quét Azure annotations để sinh binding metadata `function.json`.

Azure không tự biến `catalog.lookup("myFunction")` thành HTTP Trigger. Muốn có trigger, phải khai báo ở handler hoặc dùng đúng adapter chuyên dụng có khả năng expose endpoint.

## 4. Chuẩn bị project và dependency

### 4.1. Các thư viện cần thiết

Với ứng dụng Java 17+ đã cấu hình **Spring Boot parent** và **Spring Cloud BOM tương thích**, một mảnh Maven `dependencies` có thể như sau:

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

`1.3.1` là **mốc dependency minh họa** của Azure Functions Java library, không phải khẳng định đây là bản mới nhất. Chọn phiên bản Java library từ template Microsoft được dự án sử dụng. Version `spring-cloud-function-adapter-azure` nên được quản lý cùng dòng với SCF context qua Spring Cloud BOM; tài liệu adapter hiện đại yêu cầu **SCF 4.0.0+**.

`spring-cloud-function-adapter-azure` đưa tích hợp Spring/SCF vào Azure Java Worker. `spring-cloud-function-context` cung cấp `FunctionCatalog` và thường là dependency transitively. Thư viện Azure Java mang các annotations và đối tượng request/response.

**Phân biệt:** `azure-functions-maven-plugin` hoặc Azure Gradle plugin là **công cụ build/package/run**, không phải một Spring bean hay FunctionCatalog.

### 4.2. Gradle tương ứng

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-adapter-azure'
    implementation 'com.microsoft.azure.functions:azure-functions-java-library:1.3.1'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Cần có Spring Boot/Spring Cloud dependency management cho Gradle. Dùng Azure Gradle plugin `com.microsoft.azure.azurefunctions` khi đóng gói bằng Gradle; không trộn thêm quy trình Maven mà không có mục đích.

### 4.3. Chọn đúng Azure adapter

Bài học sử dụng **`spring-cloud-function-adapter-azure`**, nơi bạn tự khai báo `@FunctionName` và `@HttpTrigger`. Nếu ứng dụng dùng Spring MVC controllers/filters theo mô hình Spring Web, có một adapter chuyên dụng `spring-cloud-function-adapter-azure-web`. Đó là **chiến lược khác**, không cần thêm đồng thời chỉ để gọi một bean `Function`.

## 5. Ví dụ xuyên suốt: một nghiệp vụ, hai cách gọi

Bài toán: HTTP POST nhận mã đơn và tổng tiền theo format text:

~~~text
Input : "  dh-501  |  1500000  "
Output: "DH-501|PRIORITY|1500000"
~~~

Ta chia một business pipeline thành **ba function beans**:

| Function bean | Input | Output | Trách nhiệm |
| --- | --- | --- | --- |
| `parseOrder` | `String` | `OrderInput` | Parse, validate và chuẩn hóa mã đơn. |
| `classifyOrder` | `OrderInput` | `OrderDecision` | Phân loại theo ngưỡng tiền. |
| `formatOrder` | `OrderDecision` | `String` | Tạo text response. |

Cả direct bean handler lẫn catalog handler dùng cùng ba bean này. Không viết hai copy của quy tắc phân loại.

~~~mermaid
flowchart LR
    A["String"] --> B["parseOrder"]
    B --> C["OrderInput"]
    C --> D["classifyOrder"]
    D --> E["OrderDecision"]
    E --> F["formatOrder"]
    F --> G["String"]
~~~

### 5.1. Lớp Spring Boot và ba function beans

Tạo tệp `src/main/java/example/azure/OrderFunctionsApplication.java`:

~~~java
package example.azure;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

record OrderInput(String orderId, long totalVnd) {}

record OrderDecision(String orderId, long totalVnd, String lane) {}

@SpringBootApplication
public class OrderFunctionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderFunctionsApplication.class, args);
    }

    @Bean
    public Function<String, OrderInput> parseOrder() {
        return raw -> {
            if (raw == null) {
                throw new IllegalArgumentException("Thiếu đơn hàng");
            }

            String[] parts = raw.split("\\|", -1);
            if (parts.length != 2) {
                throw new IllegalArgumentException(
                        "Định dạng phải là orderId|totalVnd");
            }

            String id = parts[0].strip()
                    .toUpperCase(Locale.ROOT);
            if (id.isBlank()) {
                throw new IllegalArgumentException("Mã đơn rỗng");
            }

            final long total;
            try {
                total = Long.parseLong(parts[1].strip());
            }
            catch (NumberFormatException ex) {
                throw new IllegalArgumentException(
                        "Tổng tiền không phải số nguyên", ex);
            }
            if (total <= 0) {
                throw new IllegalArgumentException(
                        "Tổng tiền phải lớn hơn 0");
            }

            return new OrderInput(id, total);
        };
    }

    @Bean
    public Function<OrderInput, OrderDecision> classifyOrder() {
        return order -> {
            String lane = order.totalVnd() >= 1_000_000
                    ? "PRIORITY" : "STANDARD";
            return new OrderDecision(
                    order.orderId(), order.totalVnd(), lane);
        };
    }

    @Bean
    public Function<OrderDecision, String> formatOrder() {
        return result -> result.orderId() + "|"
                + result.lane() + "|"
                + result.totalVnd();
    }
}
~~~

Đây là một **Spring Cloud Function application**: không import Azure SDK trong nghiệp vụ. Hai records ở cùng package có quyền truy cập package-private; nếu chuyển ra các package khác, hãy tách thành public records theo quy tắc Java.

Ba function beans có chữ ký rõ và **không chứa state mutable**. Java `Function.andThen(...)` hoặc `FunctionCatalog` đều có thể ghép chúng vì output của bước trước khớp input của bước sau.

### 5.2. Gọi bean trực tiếp từ Java

Nếu đang ở một Spring-managed component, có thể inject từng function:

~~~java
private final Function<String, OrderInput> parser;
private final Function<OrderInput, OrderDecision> classifier;
private final Function<OrderDecision, String> formatter;
~~~

Trong một phương thức:

~~~java
String output = formatter.apply(
        classifier.apply(
                parser.apply(rawInput)));
~~~

Đây là đường **raw Java function**. Nếu `rawInput` là `byte[]`, compiler sẽ không chấp nhận gửi thẳng bytes vào `Function<String,OrderInput>`. Caller phải chuyển bytes thành String, deserialize JSON hoặc đọc POJO theo contract.

### 5.3. Dùng FunctionCatalog

Nếu inject `FunctionCatalog catalog`:

~~~java
Function<String, String> pipeline =
        catalog.lookup("parseOrder|classifyOrder|formatOrder");

String output = pipeline.apply(rawInput);
~~~

Đây là một **function composition** do SCF quản lý. Thứ tự `parseOrder|classifyOrder|formatOrder` nghĩa là:

~~~text
formatOrder(classifyOrder(parseOrder(rawInput)))
~~~

Bởi vậy kết quả với `" dh-501 | 1500000 "` giống đường direct call. Đây là trường hợp **cùng một business outcome, khác cơ chế invocation**.

### 5.4. Có nên dùng FunctionCatalog cho một function đơn lẻ?

Có, nếu cần dùng representation có wrapper/canonical behavior của SCF:

~~~java
Function<String, OrderInput> fromCatalog =
        catalog.lookup("parseOrder");

OrderInput value = fromCatalog.apply(" dh-501 | 1500000 ");
~~~

Nhưng nếu chỉ muốn một Java function đã được inject đúng kiểu và không cần SCF instrumentation/composition, direct bean là lựa chọn đơn giản và hợp lý.

## 6. Azure handler chứa cả hai đường gọi

Tạo `src/main/java/example/azure/OrderAzureHandlers.java`:

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

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class OrderAzureHandlers {

    private final Function<String, OrderInput> parser;
    private final Function<OrderInput, OrderDecision> classifier;
    private final Function<OrderDecision, String> formatter;
    private final Function<String, String> catalogPipeline;

    public OrderAzureHandlers(
            @Qualifier("parseOrder")
            Function<String, OrderInput> parser,

            @Qualifier("classifyOrder")
            Function<OrderInput, OrderDecision> classifier,

            @Qualifier("formatOrder")
            Function<OrderDecision, String> formatter,

            FunctionCatalog catalog) {

        this.parser = parser;
        this.classifier = classifier;
        this.formatter = formatter;

        this.catalogPipeline = Objects.requireNonNull(
                catalog.lookup(
                        "parseOrder|classifyOrder|formatOrder"),
                "Không tìm thấy function composition");
    }

    @FunctionName("directBeanOrder")
    public HttpResponseMessage directBeanOrder(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION,
                    route = "orders/direct")
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        Function<String, String> rawPipeline = text ->
                formatter.apply(classifier.apply(parser.apply(text)));

        return handle(request, context, rawPipeline);
    }

    @FunctionName("catalogOrder")
    public HttpResponseMessage catalogOrder(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION,
                    route = "orders/catalog")
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        return handle(request, context, catalogPipeline);
    }

    private HttpResponseMessage handle(
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context,
            Function<String, String> operation) {

        String body = request.getBody().orElse("");

        try {
            String output = operation.apply(body);
            return request.createResponseBuilder(HttpStatus.OK)
                    .header("Content-Type",
                            "text/plain; charset=utf-8")
                    .body(output)
                    .build();
        }
        catch (IllegalArgumentException invalid) {
            return request
                    .createResponseBuilder(HttpStatus.BAD_REQUEST)
                    .body("Định dạng đơn hàng không hợp lệ")
                    .build();
        }
        catch (RuntimeException failure) {
            // SCF wrapper có thể bọc lỗi validation gốc.
            Throwable root = failure;
            while (root.getCause() != null
                    && root.getCause() != root) {
                root = root.getCause();
            }

            if (root instanceof IllegalArgumentException) {
                return request
                        .createResponseBuilder(HttpStatus.BAD_REQUEST)
                        .body("Định dạng đơn hàng không hợp lệ")
                        .build();
            }

            context.getLogger().log(
                    Level.SEVERE, "Order processing failed", failure);

            return request
                    .createResponseBuilder(
                            HttpStatus.INTERNAL_SERVER_ERROR)
                    .body("Không thể xử lý đơn hàng")
                    .build();
        }
    }
}
~~~

**Điểm khác nhau nằm ở hai đường gọi:**

- `directBeanOrder` nối ba raw Java functions bằng lời gọi trực tiếp.
- `catalogOrder` gọi một `Function<String,String>` được SCF trả về từ definition `parseOrder|classifyOrder|formatOrder`.
- `handle(...)` chứa xử lý HTTP boundary giống nhau cho cả hai, nên dễ so sánh output.
- Hai đường gọi tái sử dụng **cùng ba business function beans**. Không thay đổi nội dung dữ liệu chỉ để chứng minh sự khác biệt.
- `@Component` giúp Spring tạo handler và inject dependencies; `@FunctionName` cùng `@HttpTrigger` cho Azure Host biết entrypoint và binding.

### 6.1. Vì sao constructor injection và @Qualifier?

Ba bean `Function` đều là cùng raw Java interface với generic types khác nhau. Spring có thể dựa vào type information, nhưng `@Qualifier` làm rõ **chính xác tên bean** được sử dụng, tránh mơ hồ khi project có thêm function cùng chữ ký.

Constructor injection làm dependency được giải quyết khi Spring khởi tạo handler; field `final` giúp tránh thay đổi ngoài ý muốn. Nếu `catalog.lookup(...)` trả `null`, `Objects.requireNonNull` tạo lỗi **fail fast** ngay lúc khởi tạo, thay vì chờ invocation đầu tiên.

### 6.2. Không cache request context trong bean

`OrderAzureHandlers` mặc định là Spring singleton. `ExecutionContext` do Azure cung cấp **cho từng invocation** nên phải là method parameter, không giữ trong mutable field hoặc cố inject như singleton bean. Các functional beans nên stateless hoặc có thread-safety phù hợp khi nhiều invocation xử lý song song.

### 6.3. Một số tên dễ nhầm

| Tên | Thuộc hệ thống nào? | Mục đích |
| --- | --- | --- |
| `directBeanOrder` | Azure Function name | Azure Host discover và chạy handler direct. |
| `catalogOrder` | Azure Function name | Azure Host discover và chạy handler catalog. |
| `orders/direct` | Azure HTTP Trigger route | Đường URL của handler direct. |
| `orders/catalog` | Azure HTTP Trigger route | Đường URL của handler catalog. |
| `parseOrder` | Spring bean / SCF function name | Parse input. |
| `classifyOrder` | Spring bean / SCF function name | Phân loại. |
| `formatOrder` | Spring bean / SCF function name | Tạo text response. |
| `parseOrder|classifyOrder|formatOrder` | SCF composition definition | Ghép ba function beans. |

Azure Function name **không phải** Spring bean name. Thay tên `@FunctionName` không tự đổi definition trong catalog; thay `@Bean` name có thể làm catalog lookup cũ không còn hợp lệ.

## 7. Kết quả thử và nguyên tắc đồng nhất nghiệp vụ

Sau khi Azure Functions Host chạy local với prefix `/api` mặc định:

~~~text
POST http://localhost:7071/api/orders/direct
POST http://localhost:7071/api/orders/catalog
~~~

Gửi body giống nhau:

~~~bash
curl -i -X POST "http://localhost:7071/api/orders/direct" \
  -H "Content-Type: text/plain" \
  --data " dh-501 | 1500000 "
~~~

~~~bash
curl -i -X POST "http://localhost:7071/api/orders/catalog" \
  -H "Content-Type: text/plain" \
  --data " dh-501 | 1500000 "
~~~

Kỳ vọng cả hai đều trả:

~~~text
HTTP/1.1 200 OK

DH-501|PRIORITY|1500000
~~~

### 7.1. Trường hợp đầu vào cần kiểm thử

| Body | Kết quả | HTTP |
| --- | --- | --- |
| `"dh-501|1500000"` | `DH-501|PRIORITY|1500000` | 200 |
| `" dh-502 | 999999 "` | `DH-502|STANDARD|999999` | 200 |
| `"dh-503|1000000"` | `DH-503|PRIORITY|1000000` | 200 |
| `"dh-504|abc"` | Validation error | 400 |
| `"dh-505|0"` | Validation error | 400 |
| `" | 2000000"` | Validation error | 400 |
| `"dh-506"` | Validation error | 400 |
| Body rỗng | Validation error | 400 |

Nếu hai endpoint cho kết quả khác nhau trong cùng dữ liệu/phiên bản, đây là dấu hiệu cần kiểm tra **direct pipeline**, **catalog wrapper**, **composition order** hoặc conversion. Không nên lập tức kết luận “catalog bị lỗi” vì cả hai không hẳn thực thi trong cùng context khi adapter đóng gói input khác nhau.

## 8. FunctionCatalog không chỉ là ApplicationContext.getBean

### 8.1. Direct bean: chính đối tượng đã khai báo

Trong Spring:

~~~java
Function<String, OrderInput> raw =
        applicationContext.getBean("parseOrder", Function.class);
~~~

Đây là ví dụ `getBean` theo tên và raw class type; Java sẽ có unchecked generic cast nếu gán trực tiếp. Trong ứng dụng thực, ưu tiên constructor injection với `@Qualifier` và khai báo `Function<String,OrderInput>` đúng kiểu để tránh raw cast.

Khi gọi `raw.apply(...)`, thực thi chính implementation của bean và những decorator/`BeanPostProcessor` mà Spring có thể đã áp dụng. **Không tự nhận wrapper canonical của SCF** chỉ vì bean thuộc loại `Function`.

### 8.2. FunctionCatalog: canonical function wrapper

Tài liệu SCF nói `FunctionCatalog` chuyển các user-defined functional beans sang representation thống nhất, bổ sung nhiều khả năng hơn raw Java invocation.

~~~java
Function<String, OrderInput> wrapped =
        catalog.lookup("parseOrder");
~~~

Một số khả năng mà SCF wrapper/canonical model cung cấp tùy chữ ký và context:

- **Composition** theo definition `f1|f2` hoặc `f1,f2` trong những ngữ cảnh được hỗ trợ.
- **Type conversion** giữa payload/message representations trong phạm vi converter, content type và chữ ký mà SCF hỗ trợ.
- **Message-aware signatures** có thể nhận `Message<T>` và làm việc với headers.
- **Metadata/arity/reactive models** của SCF, bao gồm những giới hạn riêng khi function nhận `Flux`/`Mono`.
- **Input/output header enrichment** theo configuration của SCF khi áp dụng đúng wrapper và message contract.

**Không hứa quá mức:** wrapper không tự hiểu một JSON tùy ý, một schema chưa đăng ký, một đối tượng Azure `HttpRequestMessage` hoặc một event payload bất kỳ. Cần adapter/converter thích hợp, content type đúng và kiểm thử contract ở biên.

### 8.3. Một function từ catalog có phải cùng instance với bean gốc?

Không nên kiểm tra tính đúng bằng:

~~~java
assertSame(rawFunction, catalog.lookup("parseOrder"));
~~~

Function từ catalog có thể là wrapper/composed representation thay vì cùng object identity với Spring bean gốc. Kiểm thử **đầu vào, đầu ra và behavior** cần thiết, không dựa vào việc hai object có cùng reference.

### 8.4. Chi phí thực thi có luôn khác nhau không?

Không có quy tắc rằng direct bean **luôn nhanh hơn** hoặc catalog **luôn chậm hơn** một cách có ý nghĩa với workload thực. Catalog có wrapper và có thể thực hiện conversion, nhưng chi phí I/O Azure, database, network hoặc cold start thường quan trọng hơn. Nên resolve composition cố định **một lần trong constructor**, sau đó đo throughput/latency nếu hiệu năng là yêu cầu.

**Chọn direct** khi rõ kiểu, thao tác ít và không cần SCF-specific features. **Chọn catalog** khi cần composition, uniform invocation giữa nhiều adapters hoặc những tính năng canonical được hỗ trợ.


## 9. Type conversion: điểm khác biệt cần kiểm chứng

### 9.1. Direct bean chịu trách nhiệm kiểu Java rõ ràng

Một bean có chữ ký:

~~~java
Function<String, OrderInput> parseOrder = ...;
~~~

yêu cầu đầu vào là `String`. Với data từ Azure:

~~~java
HttpRequestMessage<Optional<String>> request = ...;
String body = request.getBody().orElse("");
OrderInput order = parseOrder.apply(body);
~~~

Đây là đường trực tiếp và type-safe ở tầng Java nếu đã deserialize/chuyển request body thành kiểu phù hợp. Nếu thay `String` bằng `OrderRequest`, handler phải có converter hoặc Azure POJO binding tương ứng.

Không làm như sau:

~~~java
// Sai hợp đồng kiểu: Object không tự thành String.
byte[] bytes = ...;
OrderInput order = parseOrder.apply(bytes);
~~~

Đoạn trên là **phản ví dụ**, không biên dịch khi Java generic type đúng. Trường hợp dùng raw `Function` hoặc ép kiểu không kiểm soát có thể chuyển lỗi sang runtime `ClassCastException`.

### 9.2. Catalog wrapper có thể chuyển đổi ở ranh giới, nhưng có điều kiện

SCF chuẩn hóa function signatures và cung cấp conversion/wrapping trong những ngữ cảnh được hỗ trợ. Chẳng hạn khi adapter có `Message<?>` và `contentType` hợp lệ, wrapper có thể làm việc với message payload khác kiểu gốc và bộ converter được đăng ký.

Tuy nhiên:

- **Không bảo đảm** mọi `byte[]`, `String` hoặc Azure POJO đều tự biến thành `OrderInput`.
- **Không bảo đảm** một JSON body lạ schema sẽ được deserialize đúng mà không có cấu hình.
- Conversion phụ thuộc **chữ ký function**, **content type**, **type information**, **message converters**, và adapter nào tạo/đọc message.
- Azure `HttpRequestMessage<?>` **không phải** Spring `Message<?>`. Handler có thể cần chuyển dữ liệu/metadata ở biên.
- Khi catalog trả function wrapper, không nên dùng raw `Function` và cast kết quả tùy tiện.

Vì vậy trong **ví dụ chạy**, cả direct handler và catalog handler đều đưa **String đã đọc từ HTTP body** vào pipeline. Ta không sử dụng conversion như một “ma thuật” để che giấu contract.

### 9.3. Message-aware function và metadata

Giả sử domain service cần thêm `traceId` khi ghi audit. Một function riêng có thể nhận **`Message<OrderInput>`**:

~~~java
@Bean
Function<Message<OrderInput>, Message<OrderDecision>> classifyWithTrace(
        Function<OrderInput, OrderDecision> classifier) {

    return incoming -> MessageBuilder
            .withPayload(classifier.apply(incoming.getPayload()))
            .copyHeaders(incoming.getHeaders())
            .setHeader("processingStage", "CLASSIFIED")
            .build();
}
~~~

Đây là **ví dụ mở rộng**, cần imports `org.springframework.messaging.Message` và `org.springframework.messaging.support.MessageBuilder`, và nên inject classifier với `@Qualifier("classifyOrder")` nếu Spring có nhiều bean phù hợp. `classifyWithTrace` không phải bean có trong ví dụ tối thiểu phần 5; chỉ thêm nó khi đã thống nhất contract metadata.

Trong handler Azure, metadata có thể được đưa vào Spring Message một cách chủ đích:

~~~java
Message<String> message = MessageBuilder
        .withPayload(request.getBody().orElse(""))
        .setHeader("correlationId", context.getInvocationId())
        .build();
~~~

Cách này **tạo envelope ở tầng application**, không biến `HttpRequestMessage` thành Spring Message một cách tự động. Nếu function chỉ nhận `String`, nó không tự nhìn thấy header `correlationId`. Nếu function nhận `Message<String>`, có thể dùng header này theo hợp đồng.

SCF Azure còn có `AzureFunctionUtil.enhanceInputIfNecessary(...)` để đưa Azure `ExecutionContext` vào Spring Message trong trường hợp chữ ký phù hợp; không cần sử dụng tiện ích đó khi function thuần không cần Azure context.

### 9.4. Header propagation không đồng nghĩa truyền mọi header

Nếu dùng `MessageBuilder.copyHeaders(...)`, hãy nhớ:

- `replyChannel`/`errorChannel` và các metadata hệ thống có ý nghĩa điều phối riêng.
- Một adapter outbound có thể loại hoặc đổi header.
- Không truyền nguyên token, cookie, function key hay acknowledgement handle ra hệ thống ngoài.
- Với HTTP request headers, chỉ map những giá trị đã validate và thực sự cần.
- Khi đi qua Service Bus, Queue hoặc Event Hubs, phải kiểm tra header mapping theo **binding/adapter tương ứng**.

**Thiết kế tốt:** business function nhận domain object khi không cần metadata; sử dụng `Message<T>` hoặc một context DTO trung lập khi metadata là phần của contract.

## 10. Composition có thêm những quy tắc nào?

### 10.1. Thứ tự và khả năng ghép kiểu

Trong ví dụ:

~~~text
parseOrder    : String        → OrderInput
classifyOrder : OrderInput    → OrderDecision
formatOrder   : OrderDecision → String
~~~

Có thể ghép:

~~~text
parseOrder|classifyOrder|formatOrder
~~~

Nhưng không thể kỳ vọng:

~~~text
formatOrder|parseOrder|classifyOrder
~~~

hoạt động đúng, vì output `String` từ `formatOrder` không xuất phát từ đầu vào kiểu `OrderDecision` khi bắt đầu, và các bước không khớp kiểu theo pipeline dự kiến.

Java direct composition cũng phải tuân theo type contract:

~~~java
Function<String, String> directComposition =
        parseOrder.andThen(classifyOrder).andThen(formatOrder);
~~~

Đây là cách có thể thực hiện khi đã có đúng ba function instances và generic types của chúng được khai báo như mục 5. Khác với catalog definition, Java `andThen` kiểm tra tương thích generic ở compile time tốt hơn trong nhiều trường hợp.

### 10.2. Supplier, Function, Consumer khi composition

SCF hỗ trợ mô hình composition rộng hơn Java `Function.andThen` cơ bản.

| Composition | Kết quả khái niệm | Phù hợp |
| --- | --- | --- |
| `Function<A,B> + Function<B,C>` | `Function<A,C>` | HTTP request/reply, transform message. |
| `Supplier<A> + Function<A,B>` | `Supplier<B>` | Nguồn dữ liệu/timer tạo ra giá trị đã biến đổi. |
| `Function<A,B> + Consumer<B>` | `Consumer<A>` | Event/Queue handler có side effect, không cần trả kết quả nghiệp vụ. |
| `Supplier<A> + Consumer<A>` | `Runnable` | Tạo và tiêu thụ giá trị không có external input. |
| `Consumer<A> + Function<...>` | Không phải composition tuyến tính hợp lệ | Consumer không trả output cho bước kế tiếp. |

Vì vậy, nếu một Azure HTTP handler mong response `OrderDecision`, đừng dùng definition kết thúc bằng `Consumer<OrderDecision>` mà vẫn cast về `Function<String,OrderDecision>`. Cần chọn đúng kết quả của pipeline.

### 10.3. Reactive function không phải direct event invocation thông thường

Ví dụ:

~~~java
@Bean
Function<Flux<OrderInput>, Flux<OrderDecision>> classifyReactive() {
    return stream -> stream.map(order ->
            new OrderDecision(order.orderId(),
                    order.totalVnd(),
                    order.totalVnd() >= 1_000_000
                            ? "PRIORITY" : "STANDARD"));
}
~~~

Đây là **ví dụ độc lập**, cần import `reactor.core.publisher.Flux` và dependency Reactor thích hợp. Không thêm vào demo HTTP tối thiểu nếu không có pipeline reactive.

Với reactive function, SCF có các quy tắc riêng về việc gọi function với stream/Publishers. Không mặc định gọi `classifyReactive.apply(oneOrder)` như imperative `Function<OrderInput,OrderDecision>`, hoặc mong Azure HTTP adapter tự tạo `Flux` đúng cho mọi invocation.

### 10.4. Khi function catalog có nhiều function

SCF có thể tự nhận diện một function duy nhất nếu catalog chỉ có **một** functional bean; tài liệu cho biết cơ chế single-function fallback thậm chí có thể lookup bằng tên không khớp. Khi ứng dụng phát triển có **nhiều functions**, hãy **luôn dùng tên chính xác**, đặc biệt ở Azure handler và test.

Nếu muốn tắt fallback một-function, có thể dùng:

~~~properties
spring.cloud.function.single-function-fallback-enabled=false
~~~

Và nếu có bean kiểu `Function` không muốn xuất hiện trong catalog:

~~~properties
spring.cloud.function.ineligible-definitions=someInfrastructureFunction
~~~

Đây là các tùy chọn **cấu hình SCF**, không phải quy tắc để Azure plugin sinh thêm/bớt trigger.

### 10.5. spring.cloud.function.definition có tự chọn Azure method không?

Không. Thuộc tính:

~~~properties
spring.cloud.function.definition=parseOrder|classifyOrder|formatOrder
~~~

được các integration frameworks/adapters của SCF sử dụng trong những ngữ cảnh nhất định để chỉ định definition mặc định. Nó không tự tạo một Azure `@FunctionName` hoặc route `orders/catalog`. Trong ví dụ, handler gọi `catalog.lookup(...)` **tường minh** nên definition được xác định bởi chính đoạn code đó.

## 11. Azure ExecutionContext, tracing và security

### 11.1. Direct call và catalog call đều cần adapter boundary

Azure HTTP method nhận:

~~~java
@HttpTrigger(
        name = "request",
        methods = {HttpMethod.POST},
        authLevel = AuthorizationLevel.FUNCTION,
        route = "orders/catalog")
HttpRequestMessage<Optional<String>> request
~~~

Bất kể chọn direct bean hay catalog, handler đều phải quản lý:

- Dữ liệu từ request body/query/route và input validation.
- Azure `ExecutionContext`, invocation ID và logger.
- HTTP response status, content type và body.
- Authorization của trigger và xác thực người gọi khi cần.
- Lỗi transport, timeout và chính sách retry của client.
- Khi đổi sang Queue/Event trigger: message serialization, output binding, retry và idempotency.

`FunctionCatalog` không tự quyết định HTTP status **400** hay **500**. Error mapping là trách nhiệm của handler/adapter hoặc lớp exception mapping được cấu hình riêng.

### 11.2. Lỗi có thể được wrapper bọc lại

Khi function ném `IllegalArgumentException` do dữ liệu không hợp lệ, **direct call** thường ném loại exception đó trực tiếp. Với đường catalog/adapter, lỗi có thể được bọc trong một `RuntimeException`/`MessagingException` khác tùy wrapper và path xử lý.

Vì vậy:

- Không buộc test vào **một loại wrapper exception** nếu hợp đồng chỉ yêu cầu validation failure.
- Khi map HTTP 400, phân tích nguyên nhân gốc hoặc dùng một lỗi domain/validation có kiểu rõ.
- Không viết logic cho rằng mọi `RuntimeException` đều là HTTP 400.
- Nếu root cause không rõ hoặc nghi lỗi hệ thống, trả 500/503 theo hợp đồng và log có kiểm soát.

**Nhánh xử lý lỗi được áp dụng trong phương thức `handle(...)`** ở mục 6: sau khi bắt `RuntimeException failure`, tìm nguyên nhân cuối cùng để nhận diện lỗi validation:

~~~java
catch (RuntimeException failure) {
    Throwable root = failure;
    while (root.getCause() != null
            && root.getCause() != root) {
        root = root.getCause();
    }

    if (root instanceof IllegalArgumentException) {
        return request.createResponseBuilder(HttpStatus.BAD_REQUEST)
                .body("Định dạng đơn hàng không hợp lệ")
                .build();
    }

    context.getLogger().log(
            Level.SEVERE, "Order processing failed", failure);

    return request.createResponseBuilder(
            HttpStatus.INTERNAL_SERVER_ERROR)
            .body("Không thể xử lý đơn hàng")
            .build();
}
~~~

Đây là phần giải thích riêng cho nhánh `catch (RuntimeException)` đã có trong mã hoàn chỉnh; **không dán thêm một nhánh catch trùng** vào phương thức gốc. Trong production, phân loại lỗi theo **application exception types** rõ ràng thường tốt hơn dựa vào deepest cause của mọi ngoại lệ.

### 11.3. Không nhận tùy ý tên function từ HTTP

Ví dụ không nên dùng trực tiếp:

~~~java
String requestedDefinition =
        request.getQueryParameters().get("function");

Function<?, ?> selected =
        catalog.lookup(requestedDefinition);
~~~

Nếu caller không được tin cậy, việc này có thể cho họ gọi những function nội bộ không phải API public, thay đổi business workflow hoặc tạo tải bất thường. Nếu thực sự cần routing động, hãy xác định **allowlist function definitions**, quyền từng caller, input schema cho từng function và giới hạn tài nguyên.

SCF còn có `RoutingFunction` và `spring.cloud.function.routing-expression` trong các ngữ cảnh hỗ trợ. Không để input không tin cậy trực tiếp điều khiển biểu thức thực thi; sử dụng các cơ chế evaluation restriction/authorization được document và test theo môi trường.

### 11.4. Thread-safety và cold start

`OrderAzureHandlers`, ba function beans và `catalogPipeline` có thể được dùng lại giữa nhiều Azure invocations trên cùng worker. Nếu một function lưu mutable request state ở field, cả direct và catalog path đều chịu rủi ro race condition. SCF wrapper **không tự biến business function stateful thành thread-safe**.

Catalog cần khởi tạo/resolve dependency khi handler được tạo; điều này có thể góp vào cold start nhưng giúp phát hiện typo sớm. Đừng tạo một Spring ApplicationContext trong mỗi invocation; hãy để Azure adapter quản lý context.

## 12. Kiểm thử: khác biệt giữa raw bean và catalog wrapper

### 12.1. Unit test thuần Java cho nghiệp vụ

Không cần Azure runtime hoặc Spring context:

~~~java
OrderFunctionsApplication configuration =
        new OrderFunctionsApplication();

Function<String, OrderInput> parse =
        configuration.parseOrder();

Function<OrderInput, OrderDecision> classify =
        configuration.classifyOrder();

Function<OrderDecision, String> format =
        configuration.formatOrder();

String actual = format.apply(
        classify.apply(parse.apply(" dh-501 | 1500000 ")));

assertEquals("DH-501|PRIORITY|1500000", actual);
~~~

`assertEquals` từ `org.junit.jupiter.api.Assertions`. Đây là unit test của **raw function beans**, không test khả năng catalog wrapper chuyển đổi message.

### 12.2. Spring integration test: so sánh hai đường

Tạo `src/test/java/example/azure/DirectVsCatalogTest.java`:

~~~java
package example.azure;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = OrderFunctionsApplication.class)
class DirectVsCatalogTest {

    @Autowired
    @Qualifier("parseOrder")
    Function<String, OrderInput> parser;

    @Autowired
    @Qualifier("classifyOrder")
    Function<OrderInput, OrderDecision> classifier;

    @Autowired
    @Qualifier("formatOrder")
    Function<OrderDecision, String> formatter;

    @Autowired
    FunctionCatalog catalog;

    @Test
    void bothInvocationPathsGiveSameBusinessResult() {
        String input = " dh-501 | 1500000 ";

        String direct = formatter.apply(
                classifier.apply(parser.apply(input)));

        Function<String, String> fromCatalog =
                catalog.lookup(
                        "parseOrder|classifyOrder|formatOrder");

        assertNotNull(fromCatalog);
        String viaCatalog = fromCatalog.apply(input);

        assertEquals("DH-501|PRIORITY|1500000", direct);
        assertEquals(direct, viaCatalog);
    }

    @Test
    void catalogCanLookUpOneFunction() {
        Function<String, OrderInput> fromCatalog =
                catalog.lookup("parseOrder");

        assertNotNull(fromCatalog);

        OrderInput result =
                fromCatalog.apply(" dh-502 | 999999 ");

        assertEquals("DH-502", result.orderId());
        assertEquals(999_999L, result.totalVnd());
    }

    @Test
    void directValidationFailsForInvalidAmount() {
        assertThrows(IllegalArgumentException.class,
                () -> parser.apply("dh-503|abc"));
    }
}
~~~

`@SpringBootTest` xác nhận Spring tạo ba beans, catalog nhận diện chúng và pipeline từ catalog có đúng kết quả với payload typed. Để test conversion khác kiểu, cần thêm message/content type/converter thật và assertions theo version; không lấy việc test String→String làm bằng chứng đã hỗ trợ mọi JSON schema.

### 12.3. Test lỗi theo root cause, không giả định wrapper class

~~~java
@Test
void catalogPathRejectsInvalidInput() {
    Function<String, String> pipeline =
            catalog.lookup(
                    "parseOrder|classifyOrder|formatOrder");

    assertNotNull(pipeline);

    RuntimeException exception = assertThrows(
            RuntimeException.class,
            () -> pipeline.apply("dh-503|abc"));

    Throwable root = exception;
    while (root.getCause() != null
            && root.getCause() != root) {
        root = root.getCause();
    }

    assertInstanceOf(IllegalArgumentException.class, root);
}
~~~

Đây là **test bổ sung** có thể đưa vào class `DirectVsCatalogTest`, cần JUnit 5 phiên bản hỗ trợ `assertInstanceOf`. Nếu project dùng JUnit cũ hơn, thay bằng `assertTrue(root instanceof IllegalArgumentException)`.

### 12.4. Test handler annotation và host integration

Một Spring context test chưa chứng minh Azure Host đã tạo `function.json`. Sau Azure plugin packaging, cần xác minh **hai** function names và routes:

| Đường kiểm thử | Nội dung xác minh |
| --- | --- |
| Java unit | Logic từng function, input validation, composition Java. |
| Spring context | Bean injection, catalog lookup, kiểu generics, behavior raw vs wrapped. |
| Azure package | `directBeanOrder` và `catalogOrder` có metadata/trigger. |
| Azure local Host | Hai POST endpoints, HTTP status, body, error mapping. |
| Azure staging | Function key/auth, Java runtime, cold start, logs, scaling. |
| Event/Queue mở rộng | Retry/poison queue, idempotency, content type và output binding. |

### 12.5. Không nên kiểm thử wrapper bằng object identity

Không khẳng định `assertSame(parser, catalog.lookup("parseOrder"))`. Catalog được thiết kế để trả một representation có thể được instrumented; **behavior** và contract quan trọng hơn việc giữ object identity.

## 13. Dùng lại cùng function trong Queue hoặc Timer Trigger

Việc có direct bean hoặc catalog không ràng buộc function với HTTP. Azure handler có thể được gọi từ Azure Storage Queue và dùng lại chính pipeline:

~~~java
@FunctionName("catalogQueueOrder")
public void catalogQueueOrder(
        @QueueTrigger(
                name = "event",
                queueName = "orders-input",
                connection = "AzureWebJobsStorage")
        String rawOrder,

        @QueueOutput(
                name = "decision",
                queueName = "orders-decisions",
                connection = "AzureWebJobsStorage")
        OutputBinding<String> output,

        ExecutionContext context) {

    output.setValue(catalogPipeline.apply(rawOrder));
}
~~~

Đây là **phương thức mở rộng tùy chọn** trong `OrderAzureHandlers`. Cần imports:

~~~java
import com.microsoft.azure.functions.OutputBinding;
import com.microsoft.azure.functions.annotation.QueueOutput;
import com.microsoft.azure.functions.annotation.QueueTrigger;
~~~

Muốn chạy cần Azure Storage Queue extension, connection settings và queue nguồn/đích, không chỉ Spring function beans. Khi một message được giao lại, cả direct và catalog paths đều cần **idempotency** nếu nghiệp vụ tạo side effects. FunctionCatalog không tự thiết lập acknowledgement, broker retry hoặc exactly-once.

Tương tự, một Azure `@TimerTrigger` có thể gọi `Supplier.get()` hoặc `Function.apply(...)` vào thời điểm do **Azure schedule** quyết định. `@Bean Supplier` không tự tạo lịch chạy. Các trigger/bindings thuộc Azure Host; function business thuộc Spring.

## 14. Packaging Azure và cấu hình cần thiết

### 14.1. Cấu hình main class của Spring

Với Maven:

~~~xml
<properties>
    <java.version>17</java.version>
    <start-class>example.azure.OrderFunctionsApplication</start-class>
</properties>
~~~

Có thể chỉ định `MAIN_CLASS=example.azure.OrderFunctionsApplication` qua Azure application settings/local settings khi cần. Một Spring Boot `main(...)` là cấu hình ứng dụng, **không phải** Azure trigger entrypoint cho HTTP function.

### 14.2. Vì sao dùng Azure Functions plugin?

Azure Maven/Gradle plugin xử lý Java annotations và tạo Azure function metadata, thư mục package và dependencies phù hợp. **Spring Boot repackaged executable JAR mặc định không phải Azure package layout mà Java Worker mong đợi**, vì vậy cần tắt/điều chỉnh Boot repackage.

Ví dụ một fragment Maven:

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
                <appName>orders-catalog-demo-unique</appName>
                <resourceGroup>orders-demo-rg</resourceGroup>
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

`1.22.0` là mốc plugin tham khảo trong các hướng dẫn Spring Cloud Function Azure adapter; không phải lời khẳng định bản mới nhất. Thay tên Function App/resource group/region và xác minh Azure hosting plan, Java runtime cùng Spring Cloud release train tương thích. Đây chỉ là **fragment `pom.xml`**, cần dependency management phù hợp.

### 14.3. host.json và local.settings.json

`src/main/resources/host.json` tối giản:

~~~json
{
  "version": "2.0"
}
~~~

Ví dụ `local.settings.json`:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "FUNCTIONS_EXTENSION_VERSION": "~4",
    "MAIN_CLASS": "example.azure.OrderFunctionsApplication",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true"
  }
}
~~~

`UseDevelopmentStorage=true` có thể yêu cầu **Azurite** hoặc emulator tương thích khi Host/trigger dùng Azure Storage. Không commit secret thực vào repository. Trong môi trường cloud, dùng Azure Function App settings, managed identity/Key Vault và chính sách connection phù hợp.

### 14.4. Chạy local

~~~bash
./mvnw clean package
./mvnw azure-functions:run
~~~

Hoặc với Gradle khi đã cấu hình Azure Functions plugin:

~~~bash
./gradlew azureFunctionsPackage
./gradlew azureFunctionsRun
~~~

Sau khi host khởi chạy, cần thấy `directBeanOrder` và `catalogOrder`. Nếu một handler không xuất hiện, kiểm tra Azure `@FunctionName`/`@HttpTrigger` và `function.json`, không vội quy kết lỗi cho SCF catalog.

Bài này **không chạy lệnh build, deploy hoặc thay đổi tài nguyên Azure**. Những lệnh trên là hướng dẫn thực hành để bạn thử trong project tương thích.

## 15. Bảng chẩn đoán direct bean vs catalog

| Triệu chứng | Khả năng gây lỗi | Cách điều tra |
| --- | --- | --- |
| Direct bean inject không được | `@Qualifier` sai hoặc bean chưa được đăng ký/scan. | Spring context logs, bean names, generic types. |
| Catalog lookup trả `null` | Tên function definition sai hoặc function không đủ điều kiện đăng ký. | Kiểm `@Bean` name, `ineligible-definitions` và catalog test. |
| Catalog có function nhưng Azure Host không thấy endpoint | Azure discovery và Spring DI là hai cơ chế khác nhau. | Kiểm `@FunctionName`, trigger, plugin và `function.json`. |
| Direct path hoạt động, catalog path lỗi | Composition, wrapper, conversion hoặc error propagation khác. | Test từng `lookup("name")` và composition, root cause. |
| Catalog path hoạt động, direct path lỗi kiểu dữ liệu | Handler đưa raw payload sai generic type. | Thêm conversion/validation tại biên. |
| HTTP 400 ở direct, 500 ở catalog | Wrapper có thể bọc validation exception. | Phân loại nguyên nhân gốc hoặc dùng domain error type. |
| Nhập đúng tên nhưng lookup nhầm function duy nhất | Single-function fallback khi catalog chỉ có một functional bean. | Tắt fallback và test tên chính xác khi cần. |
| `ClassCastException` sau JSON request | Sai POJO/type conversion/content type. | Kiểm payload deserializer và SCF conversion contract. |
| Mất `traceId` | Handler không chuyển headers vào Spring Message, hoặc adapter lọc. | Kiểm ingress mapping và function signature. |
| Nhiều functions cùng type không inject được | Spring bean ambiguity. | Dùng `@Qualifier` hoặc thiết kế bean names rõ ràng. |
| Direct/catalog đều xử lý lặp Queue event | Retry/redelivery không do SCF kiểm soát. | Thiết kế idempotency key và ACK/poison policy. |
| Spring tests PASS, Azure Worker lỗi | Runtime/package/main class/Java target khác. | Azure plugin output, `MAIN_CLASS`, library versions. |
| Context cold start chậm | Nhiều bean/starter, lookup/khởi tạo tốn thời gian. | Profiling startup, giảm phụ thuộc, cache definition cố định. |
| Client có thể chọn function nhạy cảm | Dynamic catalog lookup từ input ngoài. | Allowlist, authorization, audit và giới hạn tài nguyên. |

## 16. Checklist quyết định và bài tập

### 16.1. Checklist chọn cách gọi

- [ ] Nếu chỉ có một function ổn định và input đã đúng kiểu, **direct bean** có đủ không?
- [ ] Nếu cần ghép nhiều function hoặc dùng definition nhất quán qua adapters, **FunctionCatalog** có phù hợp hơn không?
- [ ] Chữ ký đầu vào/đầu ra của các bước composition có khớp không?
- [ ] Azure adapter có chuẩn hóa body thành đúng Java type trước khi gọi function không?
- [ ] Có test với content type/Message headers nếu dựa vào conversion/wrapper không?
- [ ] Error mapping đã xử lý nguyên nhân gốc và phân biệt validation với infrastructure chưa?
- [ ] Tên Azure Function, HTTP route, bean name và catalog definition đã được phân biệt rõ chưa?
- [ ] FunctionCatalog lookup cố định có được resolve sớm và test fail fast chưa?
- [ ] Có tránh dynamic lookup do caller không tin cậy điều khiển không?
- [ ] Có bảo đảm thread safety, idempotency khi xử lý event/redelivery không?
- [ ] Package Azure có metadata cho đúng các `@FunctionName` và Java runtime tương thích không?

### 16.2. Bài tập thực hành

1. **So sánh output:** viết test đối chiếu direct vs catalog với các đơn ở ngưỡng 999.999, 1.000.000 và 1.000.001 VND.
2. **Thêm function bước 4:** `Function<String,String> addPrefix` để tạo `ORD-...`; cập nhật `parseOrder|classifyOrder|formatOrder|addPrefix` và so sánh Java `andThen`.
3. **Thử tên sai:** đổi lookup thành `parseOrder|missingFunction`, quan sát fail-fast ở constructor và sửa.
4. **Thử single-function fallback:** tạo test context chỉ có một function, thử lookup tên sai, sau đó bật `single-function-fallback-enabled=false`.
5. **Message-aware:** tạo function nhận `Message<OrderInput>` và ghi audit với `correlationId`; test direct call bằng Spring Message và catalog call theo contract.
6. **Sai kiểu:** cố gửi `byte[]` vào raw `Function<String,OrderInput>`, giải thích compiler/runtime behavior; bổ sung converter explicit.
7. **Thử validation wrapper:** gây lỗi tổng tiền không phải số, xác nhận HTTP 400 ở cả hai handler hoặc điều chỉnh mapper dựa trên nguyên nhân gốc.
8. **Thử Queue Trigger:** gọi catalog pipeline từ Queue output, xác định event ID/idempotency key và poison queue policy.
9. **Phân tích cold start:** đo thời gian khởi tạo context và thời gian gọi function, phân biệt chi phí I/O Azure với wrapper.
10. **Kiểm tra Azure package:** tìm metadata `function.json` của hai routes, chứng minh chỉ thêm `@Bean Function` không tạo Azure endpoint.

### 16.3. Tự đánh giá

- `@Bean Function` được Spring tạo khác function từ `FunctionCatalog.lookup(...)` ở đâu?
- Vì sao `@Qualifier` giúp inject raw function nhưng không giải quyết definition bị sai trong catalog?
- Tại sao `parseOrder|classifyOrder|formatOrder` ghép hợp lệ, còn thứ tự đảo khác có thể sai kiểu?
- Nếu hai đường trả cùng String, ta có thể kết luận hai object function là một instance không?
- Catalog wrapper có tự deserialize mọi JSON thành mọi POJO không? Vì sao?
- Ai quyết định HTTP 400/500, Azure Host hay một raw Spring `Function`?
- Một `@Bean` được catalog nhìn thấy có tự trở thành `@HttpTrigger` không?
- Vì sao không nên lấy tên function từ query/header tùy ý?
- Tại sao direct/catalog paths đều cần idempotency với Queue Trigger?
- Khi nào giữ metadata ở `Message<T>` tốt hơn thêm trực tiếp Azure `ExecutionContext` vào domain object?

## 17. Tài liệu chính thức

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): bean gốc và canonical wrapper, `FunctionCatalog`, composition, conversion, single-function fallback, reactive signatures và routing.
- [Spring Cloud Function — Microsoft Azure Functions](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): direct bean invocation so với FunctionCatalog trong Azure handler, `@Component`, Azure adapter và packaging.
- [Microsoft Learn — Azure Functions Java Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-java): `@FunctionName`, trigger/binding annotations, Java worker và dependency injection.
- [Microsoft Learn — Azure HTTP Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-http-webhook-trigger): request body, route, response, authorization và status handling.
- [Microsoft Learn — Azure Functions Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local): cách chạy Azure Functions Host local.
- [Microsoft Learn — Azure Functions Java CLI Quickstart](https://learn.microsoft.com/en-us/azure/azure-functions/create-first-function-cli-java): Azure Maven plugin, package và deploy.
- [Microsoft Learn — Azure Storage Queue Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-queue-trigger): retry, message redelivery và poison queue.
- [Spring Cloud Function Samples](https://github.com/spring-cloud/spring-cloud-function/tree/main/spring-cloud-function-samples): các ví dụ Azure handler gọi bean hoặc catalog.

**Kết luận:** **Gọi bean trực tiếp** nghĩa là dùng chính implementation `Function<T,R>` mà Spring inject, phù hợp khi dependency và kiểu Java đã rõ. **Gọi qua `FunctionCatalog`** dùng representation được SCF bọc, phù hợp khi cần **composition**, conversion/message-aware behavior trong phạm vi hỗ trợ và tái sử dụng định nghĩa hàm qua HTTP, sự kiện hoặc serverless. Với Azure Functions, hai cách đều phải đi qua **`@Component` handler**, **`@FunctionName` method** và **Azure trigger/binding** phù hợp; catalog không thay thế tầng vận chuyển. Hãy chọn theo contract, kiểm thử cả hai đường, quản lý lỗi, header, security và idempotency tại đúng ranh giới.
