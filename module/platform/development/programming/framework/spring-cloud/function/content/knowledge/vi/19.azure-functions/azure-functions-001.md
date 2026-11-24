# Phụ thuộc adapter và tích hợp Spring với Azure Functions

## 1. Mục tiêu của bài học

**Azure Functions** cung cấp môi trường serverless chạy mã khi có *trigger* như HTTP request, timer, Queue Storage, Blob Storage hoặc sự kiện từ các dịch vụ Azure. Trong mô hình Java, Azure Functions tìm những phương thức `public` được đánh dấu `@FunctionName`, đọc annotation của trigger/binding, rồi chạy phương thức đó khi có sự kiện.

**Spring Cloud Function (SCF)** có mục tiêu khác: đóng gói nghiệp vụ thành `Supplier<T>`, `Function<T,R>` và `Consumer<T>`, đăng ký qua `FunctionCatalog`, hỗ trợ *composition* và chuyển đổi message để cùng một hàm có thể tái sử dụng trong HTTP, luồng sự kiện hoặc nền tảng serverless.

Để hai hệ thống phối hợp, **`spring-cloud-function-adapter-azure`** tạo cầu nối giữa **Azure Java Worker** và Spring application context: một handler có `@FunctionName` có thể được Spring quản lý như `@Component`, inject các Spring bean hoặc `FunctionCatalog`, rồi gọi lại logic nghiệp vụ.

Bài này giải thích **đúng dependency cần thêm**, vai trò và giới hạn của adapter, cách cấu hình Spring với Azure Functions, ví dụ HTTP trigger sử dụng composition, quy trình đóng gói bằng Azure plugin, cũng như cách chạy thử và chẩn đoán lỗi.

Sau bài học, bạn có thể:

1. Phân biệt Azure trigger/binding, Azure Java handler, Spring bean và Spring Cloud Function.
2. Chọn đúng `spring-cloud-function-adapter-azure` hoặc `spring-cloud-function-adapter-azure-web`.
3. Cấu hình Maven/Gradle và tránh sai định dạng executable Spring Boot JAR.
4. Viết handler Azure `@FunctionName` là Spring `@Component` và inject `FunctionCatalog`.
5. Kiểm thử nghiệp vụ độc lập với Azure, chạy bằng Functions Core Tools và đóng gói để triển khai.
6. Hiểu vì sao `FunctionInvoker` là mô hình cũ đã deprecated, và không dùng nó như cách tiếp cận mặc định.

## 2. Kiến trúc: adapter nối hai mô hình

~~~mermaid
flowchart LR
    A["HTTP / Timer / Queue / Blob Event"] --> B["Azure Functions Host"]
    B --> C["Azure Java Worker"]
    C --> D["Handler @FunctionName<br/>+ trigger annotation"]
    E["spring-cloud-function-adapter-azure"] -. "kết nối Spring DI" .-> D
    F["Spring ApplicationContext"] --> E
    F --> G["FunctionCatalog"]
    H["Bean Supplier / Function / Consumer"] --> G
    D -->|"lookup(name) / composition"| G
    G --> I["Business Function"]
    I --> D
    D --> J["HTTP response / output binding"]
~~~

**Một request đi qua các ranh giới:**

1. **Azure Functions Host** nhận trigger; nó không gọi trực tiếp một `@Bean Function` tùy ý.
2. **Azure Java Worker** dựa trên metadata do annotation và Azure build plugin tạo để gọi phương thức handler.
3. **Spring Cloud Function Azure adapter** hỗ trợ nối Azure Java Worker với Spring context, nhờ đó handler được Spring quản lý và có thể sử dụng dependency injection.
4. **Handler** làm phần chuyển đổi giữa trigger và business contract: đọc body, header, metadata; gọi `FunctionCatalog`; xây response hoặc output binding.
5. **Hàm nghiệp vụ** chỉ xử lý giá trị đầu vào/đầu ra, không cần import Azure Functions SDK nếu không phụ thuộc trực tiếp vào giao thức.

Đây là **serverless adapter**, không phải một message broker, cũng không phải một ứng dụng web server lắng nghe cổng HTTP của Spring Boot. Azure Host và worker quản lý vòng đời invocation; Spring context được adapter khởi tạo để cung cấp bean cho handler.

### 2.1. Ba loại interface không đồng nghĩa với ba Azure triggers

| Giao diện SCF | Ý nghĩa | Cách kết hợp với Azure Functions |
| --- | --- | --- |
| `Supplier<T>` | Tạo/lấy một giá trị không có input. | Có thể được handler gọi khi Timer Trigger hoặc sự kiện nguồn phù hợp kích hoạt; trigger vẫn do Azure khai báo. |
| `Function<T,R>` | Biến đổi `T` thành `R`. | Phù hợp HTTP request/reply, xử lý một message Queue/Event Hub rồi trả kết quả cho binding. |
| `Consumer<T>` | Tiêu thụ `T`, thường có side effect. | Phù hợp xử lý event/queue không cần giá trị trả về, nhưng cần quản lý lỗi, ack và idempotency. |

**Không tự suy ra:** chỉ cần khai báo `@Bean Supplier<T>` thì Azure sẽ tự tạo Timer Trigger; hoặc có `@Bean Consumer<T>` thì Azure sẽ tự lắng nghe Storage Queue. **Trigger và binding vẫn phải được khai báo** bằng annotation/configuration của Azure Functions hoặc dùng adapter có chức năng tương ứng.

## 3. Ma trận dependency và khi nào cần từng thành phần

### 3.1. Các dependency chính

| Artifact / plugin | Vai trò | Bắt buộc khi nào? |
| --- | --- | --- |
| `org.springframework.cloud:spring-cloud-function-adapter-azure` | Tích hợp Azure Java Worker với Spring dependency injection và SCF. | **Có** khi triển khai handler Azure theo mô hình `@Component`/`@FunctionName` dùng Spring bean. |
| `org.springframework.cloud:spring-cloud-function-adapter-azure-web` | Adapter chuyên dụng để chạy ứng dụng Spring Web qua Azure HTTP Trigger, ẩn chi tiết annotation ở lớp ứng dụng web. | **Thay thế** adapter chung khi bài toán chủ yếu là Spring MVC/Web application. |
| `org.springframework.cloud:spring-cloud-function-context` | Cung cấp `FunctionCatalog`, đăng ký và composition các bean `Function`. | Cần về mặt chức năng; thường được kéo vào qua adapter SCF tương ứng. |
| `org.springframework.boot:spring-boot-starter` | Spring Boot configuration, application context và các thành phần nền. | Phù hợp để tổ chức ứng dụng Spring Boot làm cấu hình cho adapter. |
| `com.microsoft.azure.functions:azure-functions-java-library` | `@FunctionName`, `@HttpTrigger`, `HttpRequestMessage`, `ExecutionContext` và những API/binding Java. | Cần trên compile classpath cho handler dùng Azure annotations/API; có thể là dependency transitively, nhưng nên khai báo rõ nếu code dùng trực tiếp. |
| **`com.microsoft.azure:azure-functions-maven-plugin`** | Đọc annotation, tạo `function.json`, bố cục staging/package và hỗ trợ run/deploy. | Cần cho quy trình build/deploy bằng Maven. |
| **`com.microsoft.azure.azurefunctions`** (Gradle plugin) | Tác vụ build/package/run/deploy Azure Functions trong Gradle. | Tương ứng khi dự án dùng Gradle. |
| `org.springframework.boot:spring-boot-starter-test` | Unit/integration tests trên Spring context. | Test scope. |
| Các Azure extension / SDK cho trigger đặc thù | Queue/Blob/Event Hubs, output bindings hoặc client API. | Chỉ thêm khi dùng trigger/binding hoặc thao tác Azure tương ứng. |

**Phân biệt dependency với plugin:** `spring-cloud-function-adapter-azure` là **thư viện runtime**. `azure-functions-maven-plugin` là **công cụ build/package/deploy**, không phải thư viện nghiệp vụ để inject. Chỉ có adapter trên classpath chưa đủ tạo đúng cấu trúc function app để Azure Host phát hiện function.

### 3.2. Chọn adapter chung hay Azure Web Adapter

| Câu hỏi | Adapter chung | Azure Web Adapter |
| --- | --- | --- |
| Có muốn viết handler `@FunctionName` với `@HttpTrigger`/`@TimerTrigger`/`@QueueTrigger`? | Phù hợp. | Không phải trường hợp dùng chính. |
| Có muốn dùng trực tiếp `HttpRequestMessage`, `ExecutionContext`, output bindings? | Phù hợp. | Được adapter ẩn bớt ở lớp Spring Web. |
| Ứng dụng đã có controller/router theo Spring Web? | Có thể tự làm handler chuyển request, nhưng thêm boilerplate. | Phù hợp hơn với ứng dụng web thuần. |
| Có cần biến mỗi Spring `@Bean Function` thành Azure trigger tự động? | **Không**; vẫn cần handler/binding. | **Không** tự sinh mọi loại trigger. |
| Có cần chạy cả sự kiện không-HTTP? | Chọn adapter chung và annotation/binding thích hợp. | Không nên lấy Web Adapter làm giải pháp chung cho mọi trigger. |

Thông thường **chọn một chiến lược làm đầu vào chính**, không thêm cả hai adapter vào project chỉ vì tên gần giống. Nếu app chỉ cần SCF `Function<String,String>` qua HTTP, một handler Azure mỏng với adapter chung đã đủ; nếu app cần Spring MVC routes/filters/controllers, cân nhắc Web Adapter.

## 4. Phiên bản và tương thích: tránh đánh đồng bốn lớp

Tài liệu Spring Cloud Function hiện hành ghi rõ adapter Azure theo mô hình DI yêu cầu **SCF 4.0.0+**. **`FunctionInvoker`** là mô hình cũ và đã được Spring đánh dấu **deprecated**. Cách viết handler bằng `@Component`/`@FunctionName` là hướng nên học cho project mới.

Bốn lớp phiên bản cần xem độc lập:

| Lớp | Ví dụ | Điều phải khớp |
| --- | --- | --- |
| Spring Boot / Spring Cloud release train | Boot 3.x hoặc 4.x và Cloud BOM tương ứng | Phải chọn release train tương thích; nó quản lý version SCF. |
| Spring Cloud Function Azure Adapter | SCF 4.x hoặc 5.x tương thích với BOM | Adapter cùng dòng với `spring-cloud-function-context`. |
| Azure Functions Host runtime | `FUNCTIONS_EXTENSION_VERSION=~4` | Chọn version Host hỗ trợ Java runtime và trigger extensions đang dùng. |
| Java runtime / build JDK | Java 17 hoặc 21 theo Functions v4 | Java compile target, worker runtime và hosting OS/plan phải tương thích. |
| Azure Maven/Gradle plugin | Plugin do Microsoft phát hành | Tạo metadata/package đúng mẫu host và Java runtime đã chọn. |

Ví dụ **Azure Functions runtime 4.x** hỗ trợ Java 17 và 21 theo tài liệu Microsoft, nhưng phải kiểm tra tổ hợp **hệ điều hành, hosting plan và ngày hỗ trợ** trước khi chọn version triển khai. Đừng suy ra Azure Functions runtime `4.x` đồng nghĩa với Spring Cloud Function `4.x`; đây là hai phần mềm riêng.

### 4.1. Vì sao không hard-code “latest” cho tất cả?

Một `pom.xml` mới với Spring Boot 4.x nhưng trộn `spring-cloud-function-adapter-azure` 4.x hoặc dùng Spring Cloud BOM cũ có thể tạo lỗi classpath/Jackson/auto-configuration. Ngược lại, plugin build Azure cũ có thể không hiểu target runtime/Java mới. Cách an toàn là:

1. Chọn JDK và Azure Functions Host được Microsoft hỗ trợ.
2. Chọn Spring Boot và Spring Cloud BOM **đã công bố tương thích**.
3. Dùng adapter Azure cùng dòng SCF được BOM quản lý.
4. Dùng Azure Maven/Gradle plugin đáp ứng Java version, OS và plan.
5. Kiểm tra dependency tree và chạy thử trên Azure Functions Core Tools.

Bài dùng **Java 17** làm ví dụ vì đây là target được Azure Functions runtime 4.x hỗ trợ và phù hợp với nhiều bản Spring Boot hiện đại. Không giả định mọi tài khoản/plan đều đang chạy cùng patch runtime.

## 5. Maven: khai báo thư viện và plugin

### 5.1. Phụ thuộc cần thêm

Với project đã có **Spring Boot parent**, **Spring Cloud BOM** và dependency management phù hợp, phần `dependencies` có thể bắt đầu như sau:

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

`1.3.1` của Azure Java library ở đây là **mốc ví dụ được tài liệu API Microsoft mô tả**, không phải khẳng định đây là version mới nhất. Hãy đối chiếu Azure Java library và Azure Maven plugin được template hiện tại sử dụng trước khi khóa dependency. Một số adapter đã kéo thư viện Java Azure transitively; nếu thêm trực tiếp thì bảo đảm không sinh ra version conflict.

`spring-cloud-function-adapter-azure` đã tích hợp với SCF context, vì vậy không nhất thiết thêm riêng `spring-cloud-function-context` nếu dependency transitively đã đúng. Có thể kiểm tra:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.cloud,com.microsoft.azure.functions
~~~

Nếu project chưa quản lý version của adapter qua BOM, **đừng để Maven tự đoán**. Cần bổ sung dependency management theo đúng Spring Cloud release train trước khi chạy.

### 5.2. Azure Functions Maven plugin

Đoạn sau minh họa phần `build/plugins`; bạn cần chọn app name, resource group, region, plan theo môi trường Azure đã chuẩn bị:

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
                <appName>demo-orders-functions-unique</appName>
                <resourceGroup>demo-functions-rg</resourceGroup>
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

**Đây là cấu hình minh họa cần ghép vào project đầy đủ**, không phải `pom.xml` hoàn chỉnh. Các giá trị `appName`/`resourceGroup`/`region` là ví dụ và phải đổi khi triển khai. Version Maven plugin `1.22.0` là mức hướng dẫn Spring Cloud Function nêu làm mốc tối thiểu; hãy kiểm tra bản plugin hiện hành được đội dự án phê duyệt và hỗ trợ đúng hosting plan.

Spring Boot Maven plugin được đặt `skip=true` vì **Azure Functions packaging không tương thích với Spring Boot repackaged executable JAR mặc định**. Có thể dùng cấu hình thin layout phù hợp ở những project cũ, nhưng với handler DI mới thì một JAR chuẩn cùng dependencies trong cấu trúc Azure package thường dễ kiểm soát hơn. Azure Maven plugin chịu trách nhiệm dựng staging layout.

### 5.3. Chỉ rõ Spring application main class

Adapter cần xác định ứng dụng Spring Boot để khởi tạo context. Trong `pom.xml` có thể khai báo:

~~~xml
<properties>
    <java.version>17</java.version>
    <start-class>example.azure.AzureOrderApplication</start-class>
</properties>
~~~

Tùy công cụ build, cũng có thể dùng `Main-Class` trong manifest hoặc biến môi trường `MAIN_CLASS`. Nếu có nhiều JAR chứa cấu hình Spring, chỉ rõ main class sẽ tránh việc adapter chọn nhầm Spring Boot application.

Không nhầm `main()` với Azure entrypoint:

- `AzureOrderApplication.main(...)` hữu ích cho Spring Boot và xác định lớp cấu hình ứng dụng.
- `@FunctionName("normalizeOrderCode")` là **Azure Function entrypoint**, được Azure Java Worker gọi bởi trigger.
- Azure Functions không yêu cầu chạy một embedded HTTP server của Spring Boot để thực thi handler Azure.

## 6. Ví dụ Java: một business function dùng lại qua Azure HTTP Trigger

### 6.1. Quy tắc nghiệp vụ

Ứng dụng nhận mã đơn dạng text:

~~~text
Request body: " dh-102 "
Result:       "DH-102"
~~~

Có hai bước xử lý độc lập:

- `trimCode: Function<String,String>` bỏ khoảng trắng đầu/cuối.
- `upperCode: Function<String,String>` đổi chữ hoa theo `Locale.ROOT`.

Trong `FunctionCatalog`, định nghĩa ghép là **`trimCode|upperCode`**. Nếu sau này triển khai qua HTTP adapter khác, sự kiện Queue hoặc serverless khác, ta tái sử dụng nguyên các hàm này.

~~~mermaid
sequenceDiagram
    participant Client
    participant Host as Azure Functions Host
    participant Worker as Azure Java Worker
    participant Handler as @Component @FunctionName
    participant Catalog as FunctionCatalog
    Client->>Host: POST /api/orders/normalize
    Host->>Worker: HTTP trigger invocation
    Worker->>Handler: HttpRequestMessage + ExecutionContext
    Handler->>Catalog: lookup("trimCode|upperCode")
    Catalog-->>Handler: Function<String,String>
    Handler->>Catalog: apply(" dh-102 ")
    Catalog-->>Handler: "DH-102"
    Handler-->>Worker: HttpResponseMessage(200)
    Worker-->>Client: HTTP response
~~~

### 6.2. Spring Boot application và các bean function

Tạo `src/main/java/example/azure/AzureOrderApplication.java`:

~~~java
package example.azure;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class AzureOrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(AzureOrderApplication.class, args);
    }

    @Bean
    Function<String, String> trimCode() {
        return value -> value.strip();
    }

    @Bean
    Function<String, String> upperCode() {
        return value -> value.toUpperCase(Locale.ROOT);
    }
}
~~~

Đây là logic **Spring Cloud Function**, không có import `com.microsoft.azure.functions.*`. Cả hai hàm có thể kiểm thử thuần Java. Chúng cũng được Spring phát hiện và đăng ký để catalog có thể tra cứu bằng tên.

### 6.3. Azure handler là một Spring component

Tạo `src/main/java/example/azure/OrderAzureHandler.java`:

~~~java
package example.azure;

import java.util.Optional;
import java.util.function.Function;

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

    private final FunctionCatalog catalog;

    public OrderAzureHandler(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    @FunctionName("normalizeOrderCode")
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
            return request.createResponseBuilder(HttpStatus.BAD_REQUEST)
                    .body("Mã đơn không được rỗng")
                    .build();
        }

        Function<String, String> normalize =
                this.catalog.lookup("trimCode|upperCode");

        if (normalize == null) {
            context.getLogger().severe(
                    "Không tìm thấy composition trimCode|upperCode");
            return request.createResponseBuilder(
                            HttpStatus.INTERNAL_SERVER_ERROR)
                    .body("Function chưa được cấu hình")
                    .build();
        }

        try {
            String result = normalize.apply(input);
            return request.createResponseBuilder(HttpStatus.OK)
                    .header("Content-Type", "text/plain; charset=utf-8")
                    .body(result)
                    .build();
        }
        catch (RuntimeException ex) {
            context.getLogger().severe(
                    "Lỗi xử lý đơn: " + ex.getClass().getSimpleName());
            return request.createResponseBuilder(
                            HttpStatus.INTERNAL_SERVER_ERROR)
                    .body("Xử lý thất bại")
                    .build();
        }
    }
}
~~~

**Điểm kỹ thuật quan trọng:**

1. `@Component` cho phép Spring quản lý class handler. Adapter Azure kết nối mô hình Azure Java Worker với Spring dependency injection.
2. `@FunctionName` khai báo **tên Azure Function**. Nó không cần trùng tên bean `trimCode` hoặc `upperCode`.
3. `@HttpTrigger` xác định phương thức, route, authorization level và input binding.
4. `FunctionCatalog.lookup("trimCode|upperCode")` tra cứu composition của SCF. Lấy trực tiếp bean `Function` bằng `@Autowired` cũng dùng được, nhưng không cho thấy lợi ích của catalog/composition và wrapper.
5. `HttpRequestMessage<Optional<String>>` biểu diễn HTTP body dạng string có thể vắng. Dùng Optional tránh giả định request nào cũng có body.
6. `ExecutionContext` là ngữ cảnh Azure cho từng invocation. Trong ví dụ chỉ dùng logger; không lưu đối tượng này vào singleton lâu dài.
7. Handler chuyển input không hợp lệ thành HTTP 400, lỗi bất ngờ thành HTTP 500; ứng dụng thực tế nên dùng error schema thống nhất và không trả stack trace cho caller.

`AuthorizationLevel.FUNCTION` yêu cầu chính sách function key phù hợp trên Azure. Trong ví dụ, **không dùng ANONYMOUS** để mở endpoint công khai vô tình; vẫn cần xác thực/ủy quyền phù hợp với môi trường và không coi function key là thay thế hoàn toàn cho IAM/API gateway.

### 6.4. Vì sao không để business function biết HttpRequestMessage?

Nếu viết:

~~~java
Function<HttpRequestMessage<String>, HttpResponseMessage> process() {
    // Logic trực tiếp phụ thuộc Azure Java SDK.
}
~~~

thì hàm khó tái sử dụng khi được gọi từ Kafka event, HTTP adapter khác hay môi trường serverless khác. Nên giữ `Function<String,String>` hoặc `Function<OrderRequest,OrderDecision>`, còn handler Azure xử lý phần chuyển giao protocol.

**Không nhất thiết mọi handler phải dùng String.** Với JSON body, có thể dùng Azure POJO binding hoặc deserialize/validate ở ranh giới để gọi `Function<OrderRequest,OrderDecision>`. Phải xác minh contract JSON, content type, nullability, serializer và converter thay vì ép kiểu tùy ý.

## 7. Azure Functions packaging khác Spring Boot JAR

Một điểm thường gây deploy thất bại là chạy `spring-boot:repackage` và đưa nguyên **executable fat JAR** cho Azure Java Worker. Theo tài liệu SCF Azure, Azure Functions cần cấu trúc do **Azure Maven/Gradle plugin** tạo: class/handler có thể được worker tìm thấy, dependency nằm đúng chỗ, và các tệp `function.json`, `host.json` có mặt.

### 7.1. Cấu trúc điển hình sau packaging

~~~text
target/
  azure-functions/
    demo-orders-functions-unique/
      host.json
      demo-orders-functions-unique.jar
      normalizeOrderCode/
        function.json
      lib/
        [các dependency JAR được plugin đóng gói]
~~~

Tên JAR, thư mục và layout chính xác có thể khác theo plugin, nhưng **điểm cần kiểm chứng** là Azure Java Worker tìm được method `example.azure.OrderAzureHandler.normalize` và các thư viện Spring/SCF khi function thực thi.

`function.json` là metadata binding **do Azure plugin sinh từ annotation**; không nên vừa dùng annotation vừa sửa thủ công metadata đó trong staging output để “chữa” lỗi. Hãy sửa annotation hoặc build config, rồi package lại.

### 7.2. host.json dùng để làm gì?

Ví dụ `src/main/resources/host.json` tối giản:

~~~json
{
  "version": "2.0"
}
~~~

`host.json` điều khiển cấu hình **toàn function app**, không chứa business function của Spring. Với extension/binding đặc thù, có thể cần extension bundle phù hợp hoặc những thiết lập bổ sung theo tài liệu Azure. Không chép nguyên một bộ extension config nếu không dùng trigger tương ứng.

### 7.3. MAIN_CLASS và scan package

Nếu adapter không tìm ra Spring Boot main configuration:

- Kiểm tra `<start-class>` hoặc `Main-Class` manifest.
- Hoặc đặt biến `MAIN_CLASS=example.azure.AzureOrderApplication` trong local settings hoặc Azure Function App settings.
- Đặt `OrderAzureHandler` cùng package hoặc package con để `@SpringBootApplication` quét được `@Component`.
- Không đặt nhiều main classes mà không xác định rõ class sẽ được adapter sử dụng.

**Spring context cần được tạo phù hợp với vòng đời Azure Worker.** Không tự gọi `SpringApplication.run(...)` trên mỗi HTTP request trong handler: làm như vậy tốn thời gian, tài nguyên và có thể tạo nhiều context không cần thiết.

## 8. Chạy local với Azure Functions Core Tools

Cần chuẩn bị:

- JDK đúng với compile target, ví dụ 17.
- Maven hoặc Gradle theo project.
- **Azure Functions Core Tools v4**.
- **Azure CLI** nếu deploy/quản lý resource Azure.
- **Azurite** hoặc storage account nếu trigger/binding yêu cầu Azure Storage (Queue, Blob, Table và một số tình huống host).

### 8.1. local.settings.json

Ví dụ cho môi trường phát triển:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "FUNCTIONS_EXTENSION_VERSION": "~4",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "MAIN_CLASS": "example.azure.AzureOrderApplication"
  }
}
~~~

Đây là **cấu hình local**, không phải cấu hình production. `UseDevelopmentStorage=true` cần Azurite hoặc storage emulator tương thích nếu host/trigger sử dụng storage. Không commit `local.settings.json` có connection string, token hoặc key thật vào repository. Khi triển khai, dùng Azure Function App settings/Key Vault hoặc cơ chế quản lý bí mật thích hợp.

### 8.2. Build và chạy bằng Maven

~~~bash
./mvnw clean package
./mvnw azure-functions:run
~~~

Azure Maven plugin sẽ tạo package/binding metadata từ annotation. Sau khi host khởi động, kiểm tra log xem function `normalizeOrderCode` có được discovery và route `orders/normalize` có hiển thị không.

Với route mặc định của Functions Host, endpoint local thường có dạng:

~~~text
POST http://localhost:7071/api/orders/normalize
Body:  dh-102
Expected 200: DH-102
~~~

Địa chỉ, cổng và URL prefix có thể thay đổi theo `host.json` và cấu hình plugin. Local auth behavior có thể khác production, nên test riêng authorization khi deploy.

Ví dụ gọi bằng curl (giả sử endpoint local dùng prefix `/api`):

~~~bash
curl -i -X POST "http://localhost:7071/api/orders/normalize" \
  -H "Content-Type: text/plain" \
  --data " dh-102 "
~~~

Kỳ vọng HTTP 200 với body `DH-102`. Thử body chỉ có dấu cách để xác nhận HTTP 400.

### 8.3. Với Gradle

Dependency runtime tương ứng:

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-adapter-azure'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Plugin Gradle do Microsoft cung cấp có ID `com.microsoft.azure.azurefunctions`. Sau khi plugin và `azurefunctions { ... }` đã được cấu hình đúng cho project:

~~~bash
./gradlew azureFunctionsPackage
./gradlew azureFunctionsRun
~~~

Không tự chạy hai bộ plugin Maven và Gradle trong cùng một build nếu project chỉ dùng một công cụ. Trên Gradle, cần bảo đảm task tạo JAR có manifest `Main-Class`, runtime Java phù hợp, dependencies được Azure plugin đóng gói và Spring Boot executable bootJar không thay thế nhầm artifact Azure cần.

## 9. Triển khai lên Azure

Khi Azure resource (subscription, resource group, Function App, hosting plan, storage) đã được chuẩn bị và build plugin được cấu hình đúng:

~~~bash
az login
./mvnw azure-functions:deploy
~~~

Hoặc với Gradle:

~~~bash
./gradlew azureFunctionsDeploy
~~~

**Đây là các lệnh hướng dẫn, không phải lệnh cần chạy trong bài tập này.** Deploy có thể thay đổi tài nguyên đám mây, cấu hình, chi phí và quyền truy cập; hãy dùng subscription/resource group được phê duyệt và xác minh plan, region, runtime trước khi thực thi.

Các bước kiểm chứng sau triển khai:

1. Function App chạy đúng **Java version** và `FUNCTIONS_EXTENSION_VERSION`.
2. Azure Portal/CLI phát hiện `normalizeOrderCode` cùng HTTP trigger đúng route/method.
3. Spring context khởi tạo thành công trong Azure Worker; log không có `NoSuchBeanDefinitionException`.
4. FunctionCatalog tra cứu được `trimCode|upperCode`.
5. App settings chứa những cấu hình cần thiết, không có bí mật hard-code trong code hoặc JAR.
6. Function key/identity/network access phù hợp với yêu cầu bảo mật.
7. Lỗi input được map đúng 4xx; lỗi không mong đợi thành response an toàn/telemetry cần thiết.

## 10. So sánh Azure adapter với Azure Web Adapter

### 10.1. Adapter chung

Khi dùng `spring-cloud-function-adapter-azure`:

~~~text
@FunctionName + @HttpTrigger/@TimerTrigger/@QueueTrigger...
               ↓
Azure Java Worker + Spring DI
               ↓
@Component handler
               ↓
FunctionCatalog.lookup("name|composition")
               ↓
Business Function
~~~

Bạn có thể tự chọn trigger của Azure, truy cập `ExecutionContext`, dùng SDK-specific binding annotation và kiểm soát response bằng `HttpResponseMessage`. Mô hình này phù hợp bài học vì làm rõ ranh giới giữa nền tảng Azure và nghiệp vụ.

### 10.2. Azure Web Adapter

Khi ứng dụng thực sự dùng Spring Web theo mô hình controller:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-azure-web</artifactId>
</dependency>
~~~

Kèm Spring Web dependency phù hợp với phiên bản Boot và các plugin đóng gói Azure. Web Adapter cho phép dùng mô hình Spring Web, ẩn phần lớn chi tiết Azure HTTP annotations và đưa ứng dụng web lên HTTP Trigger.

**Không nhầm đây là một “thư viện gọi REST ra Azure”.** Nó là adapter **host ứng dụng Spring Web bằng Azure Functions**. Nó cũng không tự biến Queue/Timer/Blob trigger thành Spring MVC request. Đối với nghiệp vụ `Function<T,R>` đơn giản hoặc sự kiện không phải HTTP, adapter chung thường rõ ràng hơn.

### 10.3. Khi nào dùng Spring Cloud Function Web adapter?

`spring-cloud-function-web` là một adapter của SCF có thể cung cấp HTTP invocation cho function trong những cấu hình Spring Web được hỗ trợ, nhưng **không phải Azure runtime adapter**. Để triển khai lên Azure Functions, vẫn phải chọn cơ chế nối với Azure Host và packaging tương ứng. Thêm nhiều HTTP adapter chồng nhau có thể gây route ambiguity hoặc kỳ vọng sai về chức năng.

## 11. Truyền ExecutionContext và metadata

Azure cung cấp `ExecutionContext` theo từng invocation, với logger và thông tin ngữ cảnh như invocation ID. Trong handler có thể dùng trực tiếp:

~~~java
context.getLogger().info(
        "Processing Azure invocation " + context.getInvocationId());
~~~

Không bắt buộc đưa `ExecutionContext` vào domain function. Giữ nó ở adapter/handler giúp nghiệp vụ độc lập với Azure.

Khi function **thực sự cần** dữ liệu ngữ cảnh từ Azure, SCF có tiện ích `AzureFunctionUtil.enhanceInputIfNecessary(...)` để gắn execution context dưới header `AzureFunctionUtil.EXECUTION_CONTEXT`. Tuy nhiên, việc dùng `Message<T>` thay vì payload thuần phải được thiết kế rõ, có test type/header propagation; đừng cho domain function vô tình phụ thuộc runtime.

### 11.1. Metadata tại biên trigger

| Nguồn | Metadata có thể có | Điều cần làm |
| --- | --- | --- |
| HTTP Trigger | Method, headers, route/query, authentication context. | Validate input, lọc header nhạy cảm, map 4xx/5xx hợp lý. |
| Queue Trigger | Message ID, dequeue count, correlation data. | Xác định retry/poison queue/idempotency theo extension và host. |
| Blob Trigger | Blob path/name, properties, metadata. | Xác định kích thước, stream và quyền storage. |
| Timer Trigger | Thời điểm scheduled/past due. | Không coi Timer Trigger tự tạo business input hay đúng một lần tuyệt đối. |
| Event Hub/Kafka | Partition, offset, event key. | Quản lý ordering, checkpoint và redelivery theo adapter. |

Lỗi thường gặp là chuyển **toàn bộ** metadata Azure thành domain object hoặc lưu trữ `ExecutionContext` trong singleton cho lần invocation sau. Nên chỉ trích xuất những trường thật sự là contract ứng dụng; dùng trace/correlation có chiến lược riêng.

## 12. Lifecycle, concurrency và tài nguyên

### 12.1. Spring context không phải một request scope mặc định

Adapter có thể giữ và tái sử dụng Spring application context trong vòng đời một Java Worker/process. Do đó Spring singleton beans và function objects có thể được nhiều invocation dùng lại. Viết function **stateless** hoặc bảo vệ trạng thái chia sẻ để an toàn khi chạy đồng thời.

Ví dụ nên tránh:

~~~java
@Bean
Function<String, String> unsafe() {
    StringBuilder shared = new StringBuilder();

    return value -> {
        shared.setLength(0);
        shared.append(value);
        return shared.toString();
    };
}
~~~

`StringBuilder shared` có trạng thái mutable dùng chung cho các invocation. Thay bằng:

~~~java
@Bean
Function<String, String> safe() {
    return value -> new StringBuilder(value)
            .reverse()
            .toString();
}
~~~

### 12.2. Cold start

Spring context khởi tạo có thể làm tăng **cold start latency**, nhất là khi dependency nhiều, bean eager initialization phức tạp hoặc function chạy trên plan có khả năng scale về zero. Để giảm chi phí:

- Chỉ đưa vào classpath những starter/auto-config cần thiết.
- Tránh tải toàn bộ web stack nếu chỉ xử lý một HTTP Trigger bằng Azure annotations.
- Không khởi tạo Spring context trong mỗi invocation.
- Đo startup time, memory, CPU và điều kiện scale thực tế.
- Chọn hosting plan/always-ready hoặc các tùy chọn tương ứng khi độ trễ đầu tiên quan trọng.

### 12.3. Không gộp mọi loại lỗi thành HTTP 500

Đối với HTTP Trigger, có thể map validation thành 400, lỗi xác thực/ủy quyền theo security policy, transient failure thành response phù hợp với retry contract và lỗi không mong đợi thành 500. Đối với Queue/Event Hub, không có HTTP response; retry/poison messages, retry interval và checkpoint phụ thuộc host/extension. Một `Function.apply(...)` ném exception chỉ là điểm bắt đầu cho chính sách lỗi của adapter.

## 13. FunctionCatalog, composition và chuyển đổi dữ liệu

### 13.1. Lấy bean trực tiếp so với tra cứu catalog

Hai cách sau đều có thể dùng trong handler Spring:

~~~java
@Autowired
private Function<String, String> upperCode;
~~~

và:

~~~java
@Autowired
private FunctionCatalog catalog;

// Trong handler:
Function<String, String> pipeline =
        catalog.lookup("trimCode|upperCode");
~~~

**Lấy bean trực tiếp** phù hợp khi chỉ cần một Spring `Function` thông thường. **Dùng `FunctionCatalog`** khi cần tên definition, composition, wrapper/type conversion hoặc muốn phần gọi tương thích với các adapter khác của SCF.

### 13.2. Đừng gán nhầm tên Azure Function cho catalog

`@FunctionName("normalizeOrderCode")` là tên **Azure handler**. `trimCode|upperCode` là definition trong **SCF catalog**. Thuộc tính `spring.cloud.function.definition` (khi adapter đọc) cũng có ngữ nghĩa chọn function, nhưng không tự tạo Azure `@FunctionName` hay binding.

Không nhận trực tiếp query parameter như `?functionName=...` rồi gọi `catalog.lookup(input)` nếu không có allowlist. Việc này có thể để client chọn những function nhạy cảm hoặc gây tải không mong muốn. Ở ví dụ, definition được xác định sẵn trong code.

### 13.3. JSON, POJO và Message<T>

Bài minh họa `String` để tránh chi tiết serialization. Với request thực:

~~~json
{
  "orderId": "dh-102",
  "totalVnd": 1500000
}
~~~

có thể dùng Java record:

~~~java
record OrderRequest(String orderId, long totalVnd) {}
record OrderDecision(String orderId, String lane) {}
~~~

và function:

~~~java
@Bean
Function<OrderRequest, OrderDecision> classifyOrder() {
    return request -> new OrderDecision(
            request.orderId().strip().toUpperCase(),
            request.totalVnd() >= 1_000_000 ? "PRIORITY" : "STANDARD");
}
~~~

Nhưng **adapter phải tạo được `OrderRequest`** trước khi gọi function; còn response phải được serialize theo định dạng thống nhất. SCF có converter/wrapper, Azure Functions Java Worker cũng có POJO binding, và chúng không nhất thiết sử dụng cùng hợp đồng serialization trong mọi trường hợp. Kiểm thử ranh giới thực tế.

Nếu cần headers như `traceId` hay Azure execution context, có thể dùng `Function<Message<T>,Message<R>>`, song cần hiểu cách adapter map headers; không giả định một `Message<T>` của Spring tồn tại nguyên vẹn qua mọi transport.

## 14. Kiểm thử theo từng lớp

### 14.1. Unit test nghiệp vụ không cần Azure

~~~java
AzureOrderApplication config = new AzureOrderApplication();

String normalized = config.upperCode()
        .apply(config.trimCode().apply(" dh-102 "));

assertEquals("DH-102", normalized);
~~~

Test thuần Java xác nhận nghiệp vụ. Có thể dùng JUnit 5; ví dụ cần `assertEquals` từ `org.junit.jupiter.api.Assertions`. Không cần Core Tools hoặc Azure subscription.

### 14.2. Spring context + FunctionCatalog test

~~~java
@SpringBootTest(classes = AzureOrderApplication.class)
class CatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void compositionNormalizesOrderCode() {
        Function<String, String> pipeline =
                catalog.lookup("trimCode|upperCode");

        assertNotNull(pipeline);
        assertEquals("DH-102", pipeline.apply(" dh-102 "));
    }
}
~~~

Các import gồm Spring Boot Test, `@Autowired`, `FunctionCatalog`, `Function`, JUnit `@Test` cùng `assertNotNull`/`assertEquals`. Test phát hiện lỗi bean scanning, tên definition hoặc composition trước khi chạy Azure Host.

### 14.3. Test HTTP trigger trong Azure Functions runtime local

Sau khi `azure-functions:run` hoạt động:

| Trường hợp | Request | Kỳ vọng |
| --- | --- | --- |
| Hợp lệ | `POST /api/orders/normalize` với body `" dh-102 "` | HTTP 200, body `"DH-102"`. |
| Rỗng | Body `"   "` | HTTP 400, thông báo validation. |
| Thiếu body | Không có body | HTTP 400, không ném `NoSuchElementException`. |
| Wrong method | GET khi chỉ khai báo POST | Không xử lý như một POST hợp lệ; kiểm tra phản hồi host. |
| Authentication | Thiếu/sai function key trên Azure | Bị từ chối theo authLevel/host policy đã cấu hình. |
| Startup | Spring application main class sai | Host log lỗi startup và không xử lý invocation. |

Local Core Tools có thể có cơ chế xử lý function key khác cloud; vì vậy yêu cầu bảo mật phải được kiểm tra **sau khi deploy trên môi trường đúng chính sách**.

### 14.4. Integration test deployment

Ngoài kết quả body, nên kiểm tra:

- Azure plugin tạo `function.json` đúng route/entrypoint.
- Runtime Java tương thích với target bytecode.
- FunctionCatalog được inject vào handler.
- Dependency Spring/SCF không bị thiếu trong package.
- Logs có invocation ID/correlation, không log secret.
- Cold start, concurrency và memory dưới tải.
- Với trigger không phải HTTP: retry, poison queue, checkpoint, idempotency.

## 15. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Điều kiểm tra |
| --- | --- | --- |
| `NoClassDefFoundError` với Azure SDK annotation | Thiếu `azure-functions-java-library` trên compile/runtime classpath hoặc conflict. | Dependency tree và package layout. |
| `FunctionCatalog` không inject được | Adapter SCF/context không có hoặc Spring configuration sai. | Adapter version, BOM, main class, auto-configuration. |
| `OrderAzureHandler` không được Spring quản lý | Quên `@Component` hoặc class ngoài package scan. | Annotation, Spring component scan, main class. |
| Azure Host không liệt kê `normalizeOrderCode` | `function.json` chưa được tạo/không hợp lệ, plugin bỏ sót annotation hoặc package lỗi. | Azure staging directory, function.json và plugin logs. |
| Không tìm được Spring main class | `start-class`/`Main-Class`/`MAIN_CLASS` thiếu hoặc sai. | Manifest, biến môi trường, lớp `@SpringBootApplication`. |
| Có Boot fat JAR nhưng host không chạy handler | Spring Boot repackage làm sai bố cục package Azure mong đợi. | Tắt `spring-boot:repackage` và dùng Azure plugin package. |
| `catalog.lookup("trimCode|upperCode")` trả null | Sai tên bean, thiếu component scan hoặc definition không tương thích. | Unit test catalog, danh sách bean và generic types. |
| HTTP 500 với `ClassCastException` | Request body/POJO/converter không khớp generic. | Test serialization, content type và Azure/SCF adapter. |
| Local chạy nhưng deploy lỗi Java class version | Build JDK cao hơn runtime Java trong Function App. | Compiler target, runtime OS/Java, Azure settings. |
| Chạy local thiếu Azure Storage | Trigger dùng Storage chưa có `AzureWebJobsStorage`/Azurite hoặc credential hợp lệ. | local settings, Azurite, permissions. |
| Lỗi `FunctionInvoker` hoặc sample không còn áp dụng | Dùng hướng dẫn legacy/adapter đời cũ. | Chuyển sang `@Component` + Azure annotations với SCF 4.0+. |
| Handler có side effect bị xử lý trùng | Client retry, trigger redelivery hoặc concurrent invocation. | Idempotency theo business key; retry/ack theo trigger. |
| Function cold start lâu | Context quá lớn, nhiều auto-config/dependencies. | Profile startup, memory, hosting plan và context initialization. |

### 15.1. Checklist trước khi deploy

- [ ] Đã chọn **một** adapter phù hợp: generic Azure hoặc Azure Web.
- [ ] Azure handler có `@FunctionName` và trigger/binding annotations cần thiết.
- [ ] Handler là Spring `@Component` và nằm trong package scan.
- [ ] Spring main class được khai báo/giải quyết chính xác.
- [ ] `FunctionCatalog` lookup đúng tên bean/composition.
- [ ] JDK, Azure Functions runtime và Spring Boot/SCF/BOM tương thích.
- [ ] Azure Maven/Gradle plugin tạo `function.json` và package chuẩn.
- [ ] Spring Boot executable JAR repackage không phá cấu trúc Azure cần.
- [ ] App settings/secret/identity được cấu hình an toàn, không commit credentials.
- [ ] Test business function, Spring catalog và Azure runtime local đã đạt.
- [ ] Retry, idempotency, logging và security được kiểm tra theo loại trigger.

## 16. Bài tập mở rộng

1. Viết thêm `Function<String,Integer> lengthCode` và gọi `catalog.lookup("trimCode|upperCode|lengthCode")` từ một Azure handler khác. Kiểm chứng composition đầu vào/đầu ra.
2. Thay `String` bằng `OrderRequest`/`OrderDecision`, kiểm thử JSON body, null field, validation và HTTP response.
3. Thử một `@TimerTrigger` gọi `Supplier<String>`, đối chiếu lịch của Azure với việc gọi `Supplier.get()` và giải thích vì sao một Supplier không tự là timer.
4. Tạo một Queue Trigger gọi `Consumer<OrderEvent>`; mô tả retry, poison message và idempotency theo event ID khi handler ném lỗi.
5. So sánh việc inject bean `Function` trực tiếp với inject `FunctionCatalog` rồi composition: lợi ích về abstraction và rủi ro cấu hình tên sai.
6. Thử đóng gói bằng Azure Maven plugin sau khi tắt Boot repackage; xem `function.json` và cấu trúc staging để phân biệt Azure Function App với executable Boot JAR.

## 17. Tài liệu tham khảo chính thức

- [Spring Cloud Function — Microsoft Azure Functions](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): adapter chung, Web Adapter, `@Component` handler, FunctionCatalog, Azure packaging, chạy local/deploy và cảnh báo `FunctionInvoker` deprecated.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `Supplier`/`Function`/`Consumer`, composition, `FunctionCatalog` và type conversion.
- [Microsoft Learn — Azure Functions Java Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-java): `@FunctionName`, trigger/binding, packaging, Java versions, metadata và execution context.
- [Microsoft Learn — Spring Cloud Function in Azure](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/getting-started-with-spring-cloud-function-in-azure): quy trình tạo, chạy, debug và deploy Spring Cloud Function lên Azure.
- [Azure Functions Maven Plugin](https://github.com/microsoft/azure-maven-plugins/tree/develop/azure-functions-maven-plugin): plugin package, run, deploy và cấu hình Function App.
- [Spring Cloud Function — Azure samples](https://github.com/spring-cloud/spring-cloud-function/tree/main/spring-cloud-function-samples): ví dụ handler HTTP, Blob, Timer, Kafka và Web Adapter.
- [Microsoft Learn — Java functions reference / supported Java versions](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-java#java-versions): đối chiếu Azure Functions Host với Java runtime.

**Kết luận:** Để dùng Spring Cloud Function trên Azure, hãy giữ nghiệp vụ trong `Supplier`/`Function`/`Consumer` và `FunctionCatalog`, dùng **`spring-cloud-function-adapter-azure`** để tích hợp Spring dependency injection vào các Azure `@FunctionName` handlers, và dùng **Azure Maven/Gradle plugin** tạo package đúng chuẩn Azure Functions. Nếu ứng dụng chủ yếu là Spring Web, cân nhắc **`spring-cloud-function-adapter-azure-web`** thay thế. Không dùng `FunctionInvoker` legacy làm hướng mặc định; kiểm tra release train, main class, Java runtime, trigger/binding, bảo mật và vòng đời lỗi để cùng một hàm nghiệp vụ có thể tái sử dụng qua HTTP, sự kiện hoặc các môi trường serverless khác.
