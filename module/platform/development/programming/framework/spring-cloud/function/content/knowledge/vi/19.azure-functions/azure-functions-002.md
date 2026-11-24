# Đăng ký lớp handler bằng @Component và phương thức @FunctionName

## 1. Bối cảnh và mục tiêu

**Spring Cloud Function (SCF)** đóng gói logic nghiệp vụ bằng `Supplier<T>`, `Function<T,R>`, `Consumer<T>`; các bean được tra cứu qua `FunctionCatalog` và có thể ghép (*composition*) để dùng lại qua HTTP, sự kiện hoặc môi trường serverless. Logic nghiệp vụ không cần trực tiếp biết giao thức nào đang gọi nó.

Trong **Azure Functions**, entrypoint của Java lại là một **phương thức public** có annotation `@FunctionName`, cùng annotation xác định trigger/binding như `@HttpTrigger`, `@QueueTrigger` hoặc `@TimerTrigger`. Azure Java Worker gọi phương thức đó mỗi khi nguồn tương ứng kích hoạt.

Module **`spring-cloud-function-adapter-azure`** nối hai mô hình: lớp handler đánh dấu **`@Component`** được Spring quản lý, inject bean và `FunctionCatalog`; phương thức mang **`@FunctionName`** được Azure Functions discover và gọi theo trigger. Mô hình này được tài liệu Spring Cloud Function công bố từ **4.0.0+** và là cách tiếp cận hiện đại thay cho `FunctionInvoker` đã deprecated.

Bài học này thuộc chương **Azure Functions** của module **SPRING_CLOUD_FUNCTION**, tập trung vào cách đăng ký và vận hành **lớp handler** chứ không chỉ cách viết một Azure HTTP Function đơn lẻ.

### Sau bài học, bạn có thể

1. Phân biệt vai trò của `@Component`, `@FunctionName` và trigger/binding annotations.
2. Viết một lớp Spring handler có **hai phương thức Azure Functions** dùng chung các bean nghiệp vụ.
3. Inject `Function<T,R>` có `@Qualifier` và dùng `FunctionCatalog.lookup("f1|f2")`.
4. Hiểu Azure plugin tạo `function.json`, trong khi Spring component scan tạo các bean runtime.
5. Chạy thử qua Azure Functions Core Tools, kiểm tra tên function, route, Spring DI và lỗi composition.
6. Thiết kế handler stateless, phân tách `ExecutionContext` theo invocation và bảo vệ HTTP endpoint.

## 2. Hai hệ thống đăng ký khác nhau

~~~mermaid
flowchart LR
    T["HTTP / Queue / Timer / Event"] --> H["Azure Functions Host"]
    H --> W["Azure Java Worker"]
    W --> F["Method @FunctionName"]
    P["Azure Maven / Gradle plugin"] -. "Quét annotations, sinh metadata" .-> F
    S["Spring ApplicationContext"] -. "@Component, inject" .-> C["Handler bean"]
    C --> F
    S --> K["FunctionCatalog"]
    B["Bean Supplier / Function / Consumer"] --> K
    F -->|"lookup(name|composition)"| K
    K --> R["Logic nghiệp vụ"]
    R --> F
    F --> O["Response / output binding"]
~~~

Có **hai cơ chế** không thay thế cho nhau:

- **Azure discovery tại build/deploy:** Azure Maven/Gradle plugin phân tích `@FunctionName` cùng các annotation binding, tạo metadata như `function.json` và package để Azure Java Worker tìm đúng handler.
- **Spring bean registration tại runtime:** `@SpringBootApplication` quét class có `@Component`/`@Service`, tạo instance và inject các bean do Spring sở hữu. Azure adapter nối worker với instance được Spring quản lý.

| Annotation | Đặt ở đâu? | Hệ thống dùng | Ý nghĩa |
| --- | --- | --- | --- |
| `@SpringBootApplication` | Main application class | Spring Boot | Khởi tạo cấu hình, component scan, auto-configuration. |
| `@Bean` | Method trong Spring configuration | Spring | Đăng ký một service/function object. |
| **`@Component`** | **Lớp Azure handler** | **Spring** | Spring tạo và inject bean handler. |
| **`@FunctionName("name")`** | **Phương thức public** | **Azure** | Xác định tên Azure Function được host gọi. |
| `@HttpTrigger` | Tham số method | Azure | Định nghĩa HTTP trigger, route, method, auth level. |
| `@QueueTrigger` | Tham số method | Azure | Định nghĩa Azure Storage Queue trigger. |
| `@BindingName` | Tham số method | Azure | Lấy dữ liệu route/trigger metadata. |
| `@Qualifier` | Constructor/field/parameter | Spring | Chỉ định bean khi có nhiều ứng viên cùng kiểu. |

**Ba tên không đồng nghĩa:** `@FunctionName("normalizeByCatalog")` là tên Azure Function; `@Bean upperCode()` đăng ký bean có tên `upperCode`; `"trimCode|upperCode"` là function composition do `FunctionCatalog` giải quyết.

### 2.1. Chỉ có @Component thì sao?

Một lớp `@Component` có thể được Spring tạo bean và inject bình thường. Nhưng nếu không có phương thức `@FunctionName` cùng trigger/binding phù hợp, Azure Host **không tự xuất bản một HTTP/Queue/Timer Function** cho lớp ấy.

### 2.2. Chỉ có @FunctionName thì sao?

Một lớp có `@FunctionName` mà không phải Spring component có thể vẫn là một Azure Java Function thông thường. Tuy nhiên, **không được bảo đảm** Spring Cloud Function adapter sẽ inject `FunctionCatalog` hoặc các Spring beans vào một đối tượng không do Spring quản lý. Với mục tiêu tích hợp SCF hiện đại, hãy đánh dấu lớp `@Component` hoặc `@Service` và đảm bảo nó thuộc phạm vi component scan.

### 2.3. Một lớp có thể chứa nhiều Azure Functions

Có thể đặt nhiều phương thức `public` mang `@FunctionName` trong một class Spring component, mỗi method có trigger/route riêng. Tên Azure Function phải **duy nhất trong Function App**. Tên method Java không phải tên function bắt buộc:

~~~java
@FunctionName("orderStatus")
public String calculateStatus(/* Azure trigger argument */) {
    return "DONE";
}
~~~

Đây là fragment giải thích annotation, không phải handler đầy đủ vì phần trigger parameter còn phải được định nghĩa. Ví dụ hoàn chỉnh nằm ở mục 4.

## 3. Dependency của adapter và công cụ build

### 3.1. Maven

Ứng dụng cần dependency tương thích với **Spring Boot** và **Spring Cloud BOM** đã chọn:

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

Version `1.3.1` của Azure Java library là **mốc API minh họa theo Microsoft Learn**, không phải lời khẳng định đây là version mới nhất. Khi khởi tạo project mới, hãy dùng template và phiên bản được dự án phê duyệt. Version của adapter Spring Cloud Function cần được quản lý **cùng dòng** với `spring-cloud-function-context`, tránh pha trộn major version.

| Thành phần | Chức năng |
| --- | --- |
| `spring-cloud-function-adapter-azure` | Kết nối Spring context, bean và FunctionCatalog với Azure Worker. |
| `azure-functions-java-library` | Chứa `@FunctionName`, `@HttpTrigger`, `HttpRequestMessage`, `ExecutionContext`... |
| `spring-cloud-function-context` | `FunctionCatalog`, function registration và composition; thường là dependency transitively của adapter. |
| `azure-functions-maven-plugin` | Quét Azure annotations, tạo `function.json`, staging layout, run/deploy. |
| `spring-boot-starter-test` | Unit/integration tests cho Spring/SCF. |

**Build plugin không phải thư viện runtime.** Chỉ thêm adapter vào `dependencies` chưa tạo package mà Azure Host có thể discover. Ngược lại, Azure Maven plugin có thể tạo Java Function thông thường nhưng không tự làm cho class thành Spring component.

### 3.2. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-adapter-azure'
    implementation 'com.microsoft.azure.functions:azure-functions-java-library:1.3.1'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Dự án Gradle sẽ dùng plugin `com.microsoft.azure.azurefunctions` để package/run/deploy. Không dùng đồng thời Maven/Gradle chỉ vì dự án có cả hai hướng dẫn. SCF 4.0.0+ được tài liệu yêu cầu cho mô hình `@Component` + Azure handler hiện đại.

### 3.3. Không dùng FunctionInvoker cho dự án mới

Hướng dẫn SCF 3.x có ví dụ kế thừa `FunctionInvoker`. Tài liệu hiện hành đánh dấu `FunctionInvoker` **deprecated**; ví dụ trong bài dùng Spring-managed `@Component` và Azure annotations như mô hình được khuyến nghị. Khi nâng từ project cũ, cần đối chiếu code và release train trước khi thay API.

## 4. Ví dụ hoàn chỉnh: một @Component, hai @FunctionName

### 4.1. Yêu cầu

Một endpoint nhận `POST` body là mã đơn hàng dạng text:

~~~text
Input:  "  dh-207  "
Output: "DH-207"
~~~

Ta tách nghiệp vụ thành hai bean:

- `trimCode: Function<String,String>` cắt khoảng trắng.
- `upperCode: Function<String,String>` chuyển sang chữ hoa với `Locale.ROOT`.

Trong cùng một Spring component handler có **hai Azure Functions**:

1. `normalizeByBean`: dùng bean injection trực tiếp.
2. `normalizeByCatalog`: dùng composition `trimCode|upperCode` tra cứu qua FunctionCatalog.

~~~mermaid
flowchart LR
    A["POST /api/orders/bean"] --> B["normalizeByBean"]
    C["POST /api/orders/catalog"] --> D["normalizeByCatalog"]
    E["@Component OrderAzureHandler"] -. "Spring quản lý" .-> B
    E -. "Spring quản lý" .-> D
    B --> F["Injected trimCode và upperCode"]
    D --> G["FunctionCatalog: trimCode|upperCode"]
    F --> H["Kết quả DH-207"]
    G --> H
~~~

### 4.2. Cấu hình Spring Boot và các hàm nghiệp vụ

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
    public Function<String, String> trimCode() {
        return String::strip;
    }

    @Bean
    public Function<String, String> upperCode() {
        return value -> value.toUpperCase(Locale.ROOT);
    }
}
~~~

Đây là code **Spring Cloud Function thuần**: chưa import Azure Java SDK. Hai hàm có thể được dùng lại qua HTTP, luồng sự kiện, một IntegrationFlow hoặc serverless adapter khác nếu adapter có chuyển đổi dữ liệu phù hợp.

`@SpringBootApplication` đặt ở package `example.azure` giúp component scan nhận lớp handler cùng package. Azure Worker sẽ gọi handler, không phải gọi `main(...)` trên mỗi request.

### 4.3. Handler với constructor injection

Tạo `src/main/java/example/azure/OrderAzureHandler.java`:

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
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.HttpTrigger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class OrderAzureHandler {

    private final Function<String, String> trimCode;
    private final Function<String, String> upperCode;
    private final Function<String, String> composed;

    public OrderAzureHandler(
            @Qualifier("trimCode") Function<String, String> trimCode,
            @Qualifier("upperCode") Function<String, String> upperCode,
            FunctionCatalog catalog) {

        this.trimCode = trimCode;
        this.upperCode = upperCode;
        this.composed = Objects.requireNonNull(
                catalog.lookup("trimCode|upperCode"),
                "Không tìm thấy composition trimCode|upperCode");
    }

    @FunctionName("normalizeByBean")
    public HttpResponseMessage normalizeByBean(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION,
                    route = "orders/bean")
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        String input = request.getBody().orElse("");
        if (input.isBlank()) {
            return badRequest(request);
        }

        String normalized = upperCode.apply(trimCode.apply(input));
        context.getLogger().info("normalizeByBean processed");
        return ok(request, normalized);
    }

    @FunctionName("normalizeByCatalog")
    public HttpResponseMessage normalizeByCatalog(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION,
                    route = "orders/catalog")
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        String input = request.getBody().orElse("");
        if (input.isBlank()) {
            return badRequest(request);
        }

        String normalized = composed.apply(input);
        context.getLogger().info("normalizeByCatalog processed");
        return ok(request, normalized);
    }

    private HttpResponseMessage badRequest(
            HttpRequestMessage<Optional<String>> request) {
        return request
                .createResponseBuilder(HttpStatus.BAD_REQUEST)
                .header("Content-Type", "text/plain; charset=utf-8")
                .body("Mã đơn không được rỗng")
                .build();
    }

    private HttpResponseMessage ok(
            HttpRequestMessage<Optional<String>> request,
            String value) {
        return request
                .createResponseBuilder(HttpStatus.OK)
                .header("Content-Type", "text/plain; charset=utf-8")
                .body(value)
                .build();
    }
}
~~~

**Kỳ vọng:** `POST /api/orders/bean` và `POST /api/orders/catalog` với body `"  dh-207  "` đều trả `"DH-207"`. Body rỗng/chỉ chứa khoảng trắng được xử lý HTTP 400. Hai phương thức là hai Azure Functions khác nhau nhưng dùng cùng logic trong Spring context.

### 4.4. Ý nghĩa của constructor injection

Vì có hai bean `Function<String,String>`, nếu inject theo type mà không xác định bean, Spring có thể không biết chọn cái nào. `@Qualifier("trimCode")` và `@Qualifier("upperCode")` giải quyết sự mơ hồ này.

Với `FunctionCatalog`, constructor tra cứu `"trimCode|upperCode"` **một lần** khi bean được tạo. `Objects.requireNonNull` làm ứng dụng fail fast nếu cấu hình tên sai, thay vì chờ đến khi có HTTP request đầu tiên. Lúc xử lý request, method chỉ gọi function đã resolve.

Constructor injection cũng giúp field là `final` và ngăn việc vô tình tạo handler ngoài Spring. **Không nên tự `new OrderAzureHandler(...)` trong mã xử lý Azure**, vì như vậy sẽ bỏ qua cơ chế Spring adapter quản lý instance.

## 5. Chữ ký của Azure handler

Ví dụ:

~~~java
@FunctionName("normalizeByCatalog")
public HttpResponseMessage normalizeByCatalog(
        @HttpTrigger(
                name = "request",
                methods = {HttpMethod.POST},
                authLevel = AuthorizationLevel.FUNCTION,
                route = "orders/catalog")
        HttpRequestMessage<Optional<String>> request,
        ExecutionContext context) {
    // ...
}
~~~

| Thành phần | Giải thích |
| --- | --- |
| `@FunctionName("normalizeByCatalog")` | Định danh Azure Function khi package/discover/invoke. |
| `public` | Azure Java Functions yêu cầu entrypoint method public. |
| `@HttpTrigger` | Đánh dấu input được Azure HTTP trigger kích hoạt. |
| `name = "request"` | Tên binding, không đồng nhất với tên Java method. |
| `methods = {POST}` | Chỉ nhận POST theo thiết kế trigger. |
| `authLevel = FUNCTION` | Host dùng function/host key policy cho HTTP trigger trong môi trường cloud. |
| `route = "orders/catalog"` | Route tương đối; mặc định tiền tố `/api` trừ khi host config đổi. |
| `HttpRequestMessage<Optional<String>>` | Body String có thể vắng, kèm headers/query parameters. |
| `ExecutionContext` | Context của invocation hiện tại: logger, invocation ID... |

**Lưu ý:** `AuthorizationLevel.FUNCTION` không đồng nghĩa có giải pháp auth hoàn chỉnh cho mọi kịch bản public/multi-tenant. Local Core Tools có thể không enforce key giống cloud; phải kiểm thử phân quyền trên môi trường đích. Tránh dùng `ANONYMOUS` nếu không chủ đích mở endpoint.

### 5.1. Tên method Java và tên Azure Function khác nhau

Method có thể tên `execute(...)` nhưng dùng `@FunctionName("normalizeByCatalog")`. Azure Java Worker nhận diện từ annotation/metadata, không dựa vào tên method nếu annotation đã chỉ rõ function name.

### 5.2. Route parameter với @BindingName

Một biến thể lấy mã đơn qua URL:

~~~java
@FunctionName("orderLookup")
public HttpResponseMessage lookup(
        @HttpTrigger(
                name = "req",
                methods = {HttpMethod.GET},
                authLevel = AuthorizationLevel.FUNCTION,
                route = "orders/{id}")
        HttpRequestMessage<Optional<String>> request,
        @BindingName("id") String id,
        ExecutionContext context) {
    return request.createResponseBuilder(HttpStatus.OK)
            .body(id)
            .build();
}
~~~

Phải import `com.microsoft.azure.functions.annotation.BindingName`. Đây là một function độc lập để minh họa route parameter, không phải phần cần thêm vào demo chính. Phân quyền, validation ID và response serialization cần thiết kế riêng nếu triển khai thật.

### 5.3. Một function có một trigger

Một Azure Function được kích hoạt bởi **một trigger**: HTTP, Queue, Timer hoặc loại khác. Có thể dùng thêm input/output bindings nhưng không gắn hai trigger đồng thời lên cùng một method để Azure “tự chọn”. Nếu cùng nghiệp vụ có hai nguồn, viết hai handler methods và gọi chung bean `Function`/`Consumer`.

## 6. Ai tạo function.json?

Azure Maven/Gradle plugin quét `@FunctionName`, `@HttpTrigger`, `@QueueTrigger` ... trong quá trình build để tạo binding metadata và package Azure Functions.

Metadata **minh họa** cho method catalog:

~~~json
{
  "bindings": [
    {
      "type": "httpTrigger",
      "direction": "in",
      "name": "request",
      "methods": ["post"],
      "authLevel": "function",
      "route": "orders/catalog"
    },
    {
      "type": "http",
      "direction": "out",
      "name": "$return"
    }
  ],
  "scriptFile": "../<artifact-name>.jar",
  "entryPoint": "example.azure.OrderAzureHandler.normalizeByCatalog"
}
~~~

Đây **không phải** output bảo đảm byte-for-byte ở mọi version plugin. Tên JAR và layout thực tế phụ thuộc build configuration. Không sửa metadata trong staging như nguồn chân lý; sửa annotation hoặc plugin config rồi package lại.

Hai `@FunctionName` thường tạo hai thư mục function metadata riêng:

~~~text
Azure Function App package
  host.json
  normalizeByBean/
    function.json
  normalizeByCatalog/
    function.json
  lib/
    ...
  [application artifact]
~~~

Nếu Azure Host chỉ hiển thị một function, hãy kiểm tra **Azure discovery**, không chỉ việc Spring đã tạo bean.

## 7. Main class, Azure package và runtime

### 7.1. Khai báo main class của Spring

Spring adapter cần biết class `@SpringBootApplication`:

~~~xml
<properties>
    <java.version>17</java.version>
    <start-class>example.azure.AzureOrderApplication</start-class>
</properties>
~~~

Có thể khai báo biến môi trường `MAIN_CLASS=example.azure.AzureOrderApplication` ở local settings hoặc trên Azure Function App. Nếu có nhiều Spring Boot entrypoints trong classpath, nên chỉ định tường minh.

### 7.2. Maven plugin và Boot repackaging

`spring-cloud-function-adapter-azure` là thư viện runtime; Azure Functions Maven/Gradle plugin phải tạo đúng Azure function package. **Spring Boot executable fat JAR thông thường không tương thích trực tiếp với package layout mà Azure Java Worker mong đợi.** Vì vậy tài liệu SCF hướng dẫn tắt/điều chỉnh Boot repackage hoặc dùng thin layout phù hợp.

Khung `build/plugins`:

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
                <appName>orders-functions-unique-name</appName>
                <resourceGroup>example-functions-rg</resourceGroup>
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

**Lưu ý:** `1.22.0` là mức plugin được tài liệu Spring minh họa/đặt làm mốc tối thiểu, không phải khẳng định đây là bản mới nhất. Đây là fragment cấu hình, cần ghép với POM có Boot parent/Spring Cloud BOM, dependency management, Java target và Azure plan phù hợp; `appName`, resource group, region phải thay theo dự án.

### 7.3. host.json và local.settings.json

Ví dụ `src/main/resources/host.json`:

~~~json
{
  "version": "2.0"
}
~~~

Ví dụ `local.settings.json` khi phát triển:

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

Local settings không phải production settings; không commit secret thực vào repository. `UseDevelopmentStorage=true` cần Azurite/emulator tương ứng khi runtime hoặc trigger dùng Azure Storage. Java target trong compiler, Azure Host/runtime và môi trường deploy phải tương thích.


## 8. Chạy local và kiểm tra discovery

### 8.1. Công cụ và các bước

Để thử Azure Functions Java trên máy phát triển, chuẩn bị JDK phù hợp, Maven hoặc Gradle, **Azure Functions Core Tools v4** và Azurite/storage emulator nếu các binding cần Azure Storage.

Với ví dụ Maven:

~~~bash
./mvnw clean package
./mvnw azure-functions:run
~~~

Lệnh package phải sinh được metadata cho cả **`normalizeByBean`** và **`normalizeByCatalog`**. Khi Functions Host khởi động, xem log để xác nhận hai tên function và route đã được nhận diện.

Với host configuration mặc định, các URL thường có dạng:

~~~text
POST http://localhost:7071/api/orders/bean
POST http://localhost:7071/api/orders/catalog
~~~

Tiền tố `/api` và port có thể được sửa trong host configuration. Core Tools local có thể áp dụng function key khác môi trường cloud, nên local smoke test không thay thế test authentication/authorization khi deploy.

### 8.2. Gửi request

~~~bash
curl -i -X POST "http://localhost:7071/api/orders/catalog" \
  -H "Content-Type: text/plain" \
  --data "  dh-207  "
~~~

Kết quả mong đợi:

~~~text
HTTP/1.1 200 OK

DH-207
~~~

Endpoint `/orders/bean` cũng trả cùng body. Request chỉ có khoảng trắng được handler kiểm tra và trả 400. Đây là validation chủ đích của handler, không phải Azure Host tự hiểu quy tắc nghiệp vụ.

### 8.3. Phân biệt lỗi từ log

- **Host không thấy function:** kiểm tra `@FunctionName`, trigger annotation, build plugin, `function.json` và package layout.
- **Host thấy function nhưng không inject được:** kiểm tra `@Component`, `@SpringBootApplication` main class, phạm vi component scan và adapter.
- **Spring inject thành công nhưng lookup thất bại:** kiểm tra tên `trimCode|upperCode`, chữ ký generic và bean registration.
- **Xử lý được nhưng trả kết quả sai:** kiểm tra HTTP body, validation, converter và code nghiệp vụ.

Một ứng dụng có thể có đầy đủ Spring beans nhưng vẫn không được Azure Host discover nếu build metadata sai. Ngược lại, một function có metadata hợp lệ vẫn có thể lỗi khi tạo Spring bean.

## 9. Vòng đời bean và ExecutionContext

### 9.1. Spring singleton và nhiều invocation

`@Component` mặc định có scope singleton. Azure Worker có thể tái sử dụng Spring context/handler giữa nhiều invocation; một Function App có thể chạy song song và scale ra nhiều instances. Vì vậy:

- Không lưu request body, function key, trace ID hoặc `ExecutionContext` vào field mutable để dùng cho lần gọi tiếp theo.
- Tránh cache không đồng bộ nếu nhiều invocation có thể ghi cùng dữ liệu.
- Không dùng memory trong một Spring singleton như kho trạng thái bền vững xuyên các Azure Functions instances.
- Client tài nguyên như DB/HTTP client nên có lifecycle và thread-safety được quản lý rõ ràng.

Ví dụ sai:

~~~java
@Component
class UnsafeState {
    private String lastOrderCode;

    String process(String input) {
        lastOrderCode = input;
        return lastOrderCode;
    }
}
~~~

Khi hai invocation chạy đồng thời, giá trị có thể bị ghi đè. Đoạn này là **minh họa lỗi thiết kế**, không đưa vào cấu hình demo.

### 9.2. Constructor injection và instance của Azure

Handler:

~~~java
public OrderAzureHandler(
        @Qualifier("trimCode") Function<String, String> trim,
        @Qualifier("upperCode") Function<String, String> upper,
        FunctionCatalog catalog) {
    // ...
}
~~~

cần Spring giải quyết ba dependencies. Không tự tạo `new OrderAzureHandler(...)` ngoài Spring nếu mong handler được adapter quản lý. Cũng không nên gọi `SpringApplication.run(...)` trong mỗi phương thức `@FunctionName`: Spring context thường được khởi tạo trong vòng đời worker, việc tạo context mỗi request gây tốn tài nguyên và có thể dẫn tới cấu hình mâu thuẫn.

### 9.3. ExecutionContext thuộc invocation

`ExecutionContext` là Azure invocation context, thường dùng để log và lấy invocation ID:

~~~java
context.getLogger().info(
        "Invocation: " + context.getInvocationId());
~~~

Nó do **Azure Java Worker cung cấp như tham số method**, không phải dependency singleton nên inject qua Spring constructor. Tài liệu SCF có tiện ích `AzureFunctionUtil.enhanceInputIfNecessary(...)` để đưa execution context vào một `Message<?>` khi function có hợp đồng message-aware. Tuy nhiên, để business logic độc lập Azure, nên truyền chỉ những metadata domain thực sự cần hoặc giữ logging tại handler.

## 10. Bean injection trực tiếp và FunctionCatalog

### 10.1. Hai cách gọi cùng một nghiệp vụ

**Spring beans trực tiếp:**

~~~java
String result = upperCode.apply(trimCode.apply(input));
~~~

**FunctionCatalog composition:**

~~~java
Function<String, String> pipeline =
        catalog.lookup("trimCode|upperCode");

String result = pipeline.apply(input);
~~~

| Khía cạnh | Bean trực tiếp | FunctionCatalog |
| --- | --- | --- |
| Nguồn instance | Spring dependency injection. | Tìm hàm theo definition trong catalog. |
| Composition | Tự nối hoặc dùng Java `andThen`. | Chuỗi `"f1|f2"`. |
| Wrapper/type conversion | Không mặc định có wrapper của catalog. | Theo mô hình SCF và type converter được cấu hình. |
| Phù hợp | Handler biết rõ vài bean cố định. | Muốn composition, abstraction và reuse đa adapter. |
| Lỗi dễ gặp | Thiếu `@Qualifier` khi nhiều bean cùng type. | Sai function name hoặc generic type không tương thích. |

Composition `trimCode|upperCode` có nghĩa kết quả `trimCode` đi vào `upperCode`. Nếu đầu ra một hàm là `Integer` còn đầu vào hàm sau là `OrderRequest`, không thể mặc nhiên cho rằng hai hàm tương thích chỉ nhờ dấu `|`. Conversion phải rõ ràng và có test.

### 10.2. Không lấy tên bean tùy ý từ HTTP input

Đoạn mã không nên dùng với request không tin cậy:

~~~java
String definition =
        request.getQueryParameters().get("functionName");

Function<?, ?> selected = catalog.lookup(definition);
~~~

Một endpoint như vậy có thể cho người gọi quyền chọn các function không dành cho API công khai. Nếu muốn dynamic routing, cần allowlist tên function, authorization và logging có kiểm soát. Trong ví dụ chính, function definition là chuỗi cố định tại constructor.

## 11. Nhiều @FunctionName cho các trigger khác nhau

### 11.1. Queue Trigger gọi lại nghiệp vụ

Cùng một Spring bean `Function<String,String>` có thể được gọi từ handler nhận event:

~~~java
@FunctionName("normalizeQueueOrder")
public void normalizeQueueOrder(
        @QueueTrigger(
                name = "orderMessage",
                queueName = "order-events",
                connection = "AzureWebJobsStorage")
        String orderId,
        ExecutionContext context) {

    String normalized = composed.apply(orderId);
    context.getLogger().info("Queue item processed");
}
~~~

Đây là **phương thức bổ sung minh họa** cho lớp `OrderAzureHandler`, cần import `com.microsoft.azure.functions.annotation.QueueTrigger`. Muốn chạy cần Queue Storage, connection và extension phù hợp. Việc chỉ gọi function và log không tự tạo output message; nếu cần gửi sự kiện ra broker/queue khác, phải khai báo output binding hoặc dùng client API tương ứng.

Với Queue Trigger, Azure quản lý acknowledgement/retry/poison queue theo hosting/extension settings. Có thể xảy ra redelivery, do đó consumer thực hiện side effect phải idempotent theo business key hoặc event ID.

### 11.2. Timer Trigger gọi Supplier hay service

~~~java
@FunctionName("scheduledAudit")
public void scheduledAudit(
        @TimerTrigger(
                name = "timer",
                schedule = "0 0 */5 * * *")
        String scheduleInfo,
        ExecutionContext context) {

    context.getLogger().info("Timer triggered");
    // Gọi Supplier hoặc service Spring khi đã inject.
}
~~~

Đây là **ví dụ method riêng**, cần import `com.microsoft.azure.functions.annotation.TimerTrigger`. Azure dùng lịch NCRONTAB sáu trường; biểu thức trên minh họa chu kỳ mỗi năm giờ. Không suy ra rằng khai báo `@Bean Supplier<T>` tự tạo Timer Trigger: lịch và entrypoint vẫn cần Azure binding.

**Không tạo một method với cả HTTP và Queue triggers.** Mỗi Azure Function chỉ có một trigger; muốn hai nguồn gọi cùng logic, dùng hai handler methods, chia sẻ cùng business service/function.

## 12. Kiểm thử theo ba lớp

### 12.1. Unit test nghiệp vụ

Không cần Azure Host:

~~~java
AzureOrderApplication config = new AzureOrderApplication();

String result = config.upperCode()
        .apply(config.trimCode().apply("  dh-207  "));

assertEquals("DH-207", result);
~~~

Dùng JUnit 5 với `assertEquals`. Test trực tiếp bean xác nhận kết quả nghiệp vụ, không khẳng định Spring DI hay Azure annotation discovery đúng.

### 12.2. Spring context và catalog

~~~java
@SpringBootTest(classes = AzureOrderApplication.class)
class OrderCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    OrderAzureHandler handler;

    @Test
    void handlerIsSpringManagedAndCompositionWorks() {
        assertNotNull(handler);

        Function<String, String> normalize =
                catalog.lookup("trimCode|upperCode");

        assertNotNull(normalize);
        assertEquals("DH-207",
                normalize.apply("  dh-207  "));
    }
}
~~~

Cần imports cho Spring Boot Test, `@Autowired`, `FunctionCatalog`, `Function`, JUnit 5 và Assertions. Spring context test phát hiện lỗi component scan, bean ambiguity, catalog definition và thiếu adapter dependency.

### 12.3. Annotation test với reflection

~~~java
@Test
void functionNamesAreDistinct() throws NoSuchMethodException {
    Method direct = OrderAzureHandler.class.getMethod(
            "normalizeByBean",
            HttpRequestMessage.class,
            ExecutionContext.class);

    Method viaCatalog = OrderAzureHandler.class.getMethod(
            "normalizeByCatalog",
            HttpRequestMessage.class,
            ExecutionContext.class);

    assertEquals("normalizeByBean",
            direct.getAnnotation(FunctionName.class).value());
    assertEquals("normalizeByCatalog",
            viaCatalog.getAnnotation(FunctionName.class).value());
}
~~~

Thêm import `java.lang.reflect.Method`, Azure `FunctionName`, `HttpRequestMessage` và `ExecutionContext`. Test annotation này không thay thế việc Azure build plugin sinh đúng metadata.

### 12.4. Host-level integration test

| Trường hợp | Kỳ vọng |
| --- | --- |
| `POST /api/orders/bean` với `" dh-207 "` | 200, body `DH-207`. |
| `POST /api/orders/catalog` với cùng body | 200, kết quả giống endpoint bean. |
| POST body rỗng/chỉ khoảng trắng | 400 theo validation của handler. |
| GET tới route chỉ khai báo POST | Không được xử lý như POST hợp lệ; status cụ thể do host định nghĩa. |
| Không có function key trên cloud khi authLevel=FUNCTION | Bị từ chối theo host policy. |
| Function name trùng/method thiếu annotation | Build hoặc discovery phải phát hiện vấn đề. |
| Main class/adapter sai | Spring context hoặc injection thất bại; xem host log. |

Khi dùng Queue/Timer triggers, cần test thêm extension, schedule, connection, retry/redelivery và idempotency.

## 13. Troubleshooting theo tầng

| Triệu chứng | Nguyên nhân tiềm năng | Hướng xử lý |
| --- | --- | --- |
| Azure Host không thấy handler | Annotation/build metadata sai. | Kiểm method public, `@FunctionName`, trigger và `function.json`. |
| Host thấy function, nhưng method không chạy | Route/auth/binding sai. | Kiểm HTTP method, prefix, key và connection settings. |
| Không inject được Spring bean | Handler không do Spring quản lý. | Kiểm `@Component`, component scan, main class, Azure adapter. |
| `NoSuchBeanDefinitionException` cho FunctionCatalog | SCF context/version/auto-configuration sai. | Kiểm dependency management và adapter. |
| Có nhiều bean `Function<String,String>` | Spring không biết chọn bean. | Dùng `@Qualifier`. |
| Lookup composition trả null | Function name sai hoặc bean không được đăng ký. | Kiểm catalog, type/signature và tên. |
| HTTP 500/`ClassCastException` | Serialization/conversion sai. | Kiểm body và generic type ở ranh giới. |
| Boot fat JAR không được Azure Worker load | Package layout sai. | Tắt/điều chỉnh Boot repackage, dùng Azure plugin. |
| Azure Host load function nhưng startup Spring lỗi | Main class sai, thư viện thiếu hoặc version conflict. | Kiểm `MAIN_CLASS`, package và dependency tree. |
| Local chạy, cloud lỗi | Runtime Java, auth hoặc app settings khác. | Đối chiếu Function App plan, Java version, secrets. |
| Dữ liệu từ request này lọt request khác | Mutable state trong singleton handler. | Dùng local variables và thiết kế stateless. |
| Queue event bị xử lý lại | Retry/redelivery. | Idempotency theo event ID, error policy theo trigger. |

### Quy trình chẩn đoán ngắn

1. Azure plugin có tạo metadata cho đúng số function names không?
2. Azure Host có discover đúng names, trigger, route không?
3. Spring adapter có trên classpath runtime và tương thích với Boot/SCF không?
4. Main class có chính xác và component scan có thấy handler không?
5. Constructor injection có đủ beans không?
6. Catalog composition có đúng thứ tự và kiểu dữ liệu không?
7. HTTP body/response hoặc Queue event có đúng contract không?
8. Bảo mật, retry, idempotency và observability đã đúng môi trường chưa?

## 14. Quy tắc thiết kế production

1. **Handler mỏng:** nhận trigger input, validate contract ở biên, gọi function/service và trả output.
2. **Function thuần nghiệp vụ:** không trộn `HttpRequestMessage`, `ExecutionContext` và Azure SDK vào logic không cần chúng.
3. **Tách tên Azure và catalog:** đừng để sai tên function definition làm người dùng nhầm lỗi HTTP route.
4. **Fail fast:** resolve composition cố định khi tạo bean, có thông báo tên definition rõ ràng.
5. **Không giữ invocation state trong singleton:** ưu tiên immutable dependencies và local variables.
6. **Chính sách lỗi riêng theo trigger:** HTTP 4xx/5xx khác Queue retry/poison queue.
7. **Chống xử lý trùng:** Azure có thể scale và redeliver, cần idempotency key bền vững.
8. **Bảo mật:** không log secret/function key hoặc để caller tùy ý điều khiển FunctionCatalog.
9. **Quan sát:** log function name, invocation/correlation ID và metrics có giới hạn dữ liệu nhạy cảm.
10. **Khóa phiên bản:** kiểm Boot, Spring Cloud BOM, SCF Azure adapter, Azure Java library/plugin và Java runtime cùng nhau.

## 15. Bài tập thực hành

- Chuyển `trimCode` và `upperCode` sang class `@Configuration` riêng; đảm bảo handler vẫn inject được.
- Đổi tên Java method `normalizeByCatalog` thành `execute` nhưng giữ `@FunctionName("normalizeByCatalog")`; build và xác nhận tên Azure không đổi.
- Thay `@Component` bằng `@Service`; kiểm tra Spring bean registration và Azure discovery.
- Đổi catalog definition thành `trimCode|missingBean` để quan sát lỗi fail-fast ở startup.
- Thêm `Function<String,Integer> codeLength` và composition `trimCode|upperCode|codeLength` cho một Azure function mới.
- Thêm Queue Trigger dùng cùng business function, sau đó thiết kế idempotency khi event được gửi lại.
- Chuyển handler ra package ngoài main scan; dùng test Spring để tìm lỗi rồi bổ sung `@ComponentScan`.
- Mở staging package, đối chiếu `function.json` của hai Azure Functions với annotations tương ứng.

## 16. Câu hỏi tự đánh giá

- `@Component` và `@FunctionName` thuộc hai framework nào?
- Tại sao `@Component` một mình không tạo một Azure HTTP function?
- Tại sao một handler `@FunctionName` có thể chạy như Java Function nhưng không inject được Spring beans?
- Khi một class có hai `@FunctionName` methods, các method có được gọi chung một `FunctionCatalog` không?
- Tại sao cần `@Qualifier` khi có hai bean function cùng kiểu?
- Composition `trimCode|upperCode` có khác Java `upperCode(trimCode(input))` về logic chính không? Có khác về wrapper/catalog không?
- Tại sao `ExecutionContext` nên là method parameter thay vì singleton dependency?
- Nếu Host không thấy function nhưng Spring context test PASS, nên kiểm tra gì tiếp?
- HTTP Trigger và Queue Trigger có thể cùng đặt lên một method không?
- Tại sao cần idempotency khi consumer được Azure Queue Trigger gọi?

## 17. Nguồn chính thức

- [Spring Cloud Function — Microsoft Azure Functions](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): adapter 4.0+, `@Component`, `@FunctionName`, FunctionCatalog, main class, packaging, Core Tools và `FunctionInvoker` deprecated.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `Supplier`, `Function`, `Consumer`, catalog và composition.
- [Microsoft Learn — Azure Functions Java Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-java): public handler method, `@FunctionName`, trigger và binding metadata.
- [Microsoft Learn — Azure Java HttpTrigger API](https://learn.microsoft.com/en-us/java/api/com.microsoft.azure.functions.annotation.httptrigger): route, HTTP method, auth level và request types.
- [Microsoft Learn — HTTP Trigger and Binding](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-http-webhook-trigger): HTTP request/response.
- [Microsoft Learn — Core Tools Local Run](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local): local runtime và HTTP/Queue bindings.
- [Microsoft Learn — Java CLI Quickstart](https://learn.microsoft.com/en-us/azure/azure-functions/create-first-function-cli-java): build/package/run/deploy với Maven.
- [Spring Cloud Function Examples](https://github.com/spring-cloud/spring-cloud-function/tree/main/spring-cloud-function-samples): các mẫu handler Azure, Timer, Blob và Web Adapter.

**Kết luận:** `@Component` đánh dấu **lớp handler do Spring quản lý và inject**, còn `@FunctionName` đánh dấu **phương thức Azure Functions được Host discover và gọi** theo trigger/binding. Với `spring-cloud-function-adapter-azure`, một handler có thể dùng trực tiếp `Function<T,R>` hoặc composition qua `FunctionCatalog` trong khi nghiệp vụ vẫn độc lập Azure. Cần kiểm soát Spring main class, Azure metadata/package, scope bean, bảo mật và xử lý lỗi theo trigger để tái sử dụng cùng hàm qua HTTP, sự kiện hay serverless.
