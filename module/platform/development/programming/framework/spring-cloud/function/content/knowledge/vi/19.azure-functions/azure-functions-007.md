# Cấu hình lớp ứng dụng chính và đóng gói triển khai

## 1. Bài toán: một Spring Cloud Function chạy đúng trong Azure Functions

Trong **SPRING_CLOUD_FUNCTION**, nghiệp vụ được biểu diễn bằng các bean `Supplier<T>`, `Function<T,R>` và `Consumer<T>`, tra cứu qua `FunctionCatalog`, có thể ghép (*composition*) và tái sử dụng qua HTTP, sự kiện hoặc serverless adapter khác. Khi đưa các bean này lên **Azure Functions**, một đoạn Java đúng về nghiệp vụ **chưa đủ** để Azure Host gọi được.

Một ứng dụng Spring Cloud Function triển khai lên Azure cần ba lớp cấu hình tương đối độc lập:

1. **Spring application entrypoint:** class `@SpringBootApplication`/`@SpringBootConfiguration` giúp adapter tìm đúng cấu hình Spring, quét handler, tạo function beans và `FunctionCatalog`.
2. **Azure function entrypoints:** các phương thức Java `public` có `@FunctionName` và trigger/binding annotations để Azure Java Worker biết **khi nào** và **gọi phương thức nào**.
3. **Azure deployment package:** Azure Maven/Gradle plugin phân tích annotations, sinh metadata như `function.json`, đặt `host.json` đúng chỗ và tạo layout có application JAR cùng dependencies cho Azure Host.

Nếu một tầng sai, ta có thể gặp tình huống **Spring test chạy tốt nhưng Azure không thấy function**, hoặc **Azure thấy HTTP endpoint nhưng Spring dependency injection thất bại**.

### Sau bài học, bạn sẽ làm được gì?

- Viết class Spring Boot chính và xác định phạm vi component scanning.
- Hiểu cách adapter tìm `Main-Class`/`Start-Class` hoặc biến `MAIN_CLASS`.
- Phân biệt entrypoint Spring `main(...)` với handler Azure `@FunctionName`.
- Cấu hình Maven/Gradle để Azure plugin sinh package; tránh xung đột với Spring Boot *repackaged executable JAR*.
- Đọc đúng layout `target/azure-functions/<appName>/...`, `function.json` và `host.json`.
- Chạy local bằng Azure Functions Core Tools, sau đó chọn cách triển khai phù hợp với hosting plan.
- Thiết kế CI/CD, cấu hình bí mật, kiểm tra sau phát hành và rollback ở mức thực tế.
- Chẩn đoán theo thứ tự lỗi build, Azure discovery, Spring context, catalog, trigger và deployment.

**Phạm vi:** bài hướng dẫn cấu hình/đóng gói một **Azure adapter dạng annotated Java handlers**. Không sử dụng Docker hay một framework Azure Web khác trừ khi có lý do rõ.

## 2. Kiến trúc khởi tạo và triển khai

~~~mermaid
flowchart TB
    subgraph Source["Mã nguồn Java và cấu hình"]
      A["@SpringBootApplication<br/>OrderFunctionApplication"]
      B["@Bean Function / Supplier / Consumer"]
      C["@Component OrderAzureHandler<br/>@FunctionName + @HttpTrigger"]
      D["pom.xml hoặc build.gradle<br/>host.json"]
    end
    subgraph Build["Build và staging"]
      E["Java compile"]
      F["Azure Maven/Gradle plugin"]
      G["function.json cho từng Azure Function<br/>host.json + app jar + lib"]
    end
    subgraph Runtime["Azure Functions Host / Java Worker"]
      H["Đọc binding metadata và discover trigger"]
      I["Azure adapter tìm Spring main class"]
      J["Spring ApplicationContext<br/>DI + FunctionCatalog"]
      K["Azure handler được Spring quản lý"]
    end
    A --> E
    B --> E
    C --> E
    D --> F
    E --> F
    F --> G
    G --> H
    H --> K
    I --> J
    J --> K
    K --> L["HTTP response / Queue output / event"]
~~~

**Hai hướng đi trong cùng package:**

- **Build-time:** compiler/plugin tìm các annotations Azure, sinh metadata và staging layout. `@Bean Function` **không** tự sinh một `function.json`.
- **Runtime:** adapter tìm lớp cấu hình Spring, tạo `ApplicationContext`, inject các services và `FunctionCatalog` vào Azure handler. `@FunctionName` **không** tự biến class thành Spring component.

| Khái niệm | Ý nghĩa | Trạng thái khi thiếu |
| --- | --- | --- |
| `@SpringBootApplication` | Spring configuration root, component scan và auto-configuration. | Adapter có thể không xác định được context cần khởi tạo. |
| `@Bean Function<T,R>` | Đăng ký logic vào Spring context/SCF catalog. | Không tìm thấy function khi `catalog.lookup(...)`. |
| `@Component` trên handler | Cho Spring quản lý instance và constructor injection. | Azure method có thể được discover nhưng không có DI như kỳ vọng. |
| `@FunctionName` | Định danh Azure Function duy nhất trong Function App. | Azure Host không thấy entrypoint tương ứng. |
| `@HttpTrigger`/`@QueueTrigger` | Chỉ định nguồn kích hoạt và binding. | Không có trigger hợp lệ để host thực thi. |
| `Main-Class`/`MAIN_CLASS` | Chỉ đúng class cấu hình Spring cho adapter. | Spring startup có thể fail hoặc dùng sai main class. |
| Azure plugin | Sinh metadata và package Azure. | Có JAR nhưng không đủ deployment artifact hợp lệ. |

### 2.1. Spring main class không phải Azure entrypoint

`public static void main(String[] args)` là entrypoint của một **Spring Boot application khi chạy theo cách Java/Boot thông thường**. Trong Azure Functions, Java Worker thực thi phương thức Azure `@FunctionName` dựa trên binding metadata; Spring main class đóng vai trò **tìm cấu hình và tạo application context**, không phải endpoint để Azure Host gọi mỗi HTTP request.

**Không gọi `SpringApplication.run(...)` bên trong `@FunctionName` method cho mỗi invocation.** Làm như vậy tạo application context nhiều lần, tăng latency/chi phí và khiến lifecycle bean khó kiểm soát.

## 3. Thiết kế thư mục project trước khi viết code

Ví dụ một project Maven nhỏ:

~~~text
azure-order-functions/
├── pom.xml
├── local.settings.json              # Local only, không commit secret
└── src/
    ├── main/
    │   ├── java/
    │   │   └── example/azure/
    │   │       ├── OrderFunctionApplication.java
    │   │       └── OrderAzureHandler.java
    │   └── resources/
    │       ├── application.properties
    │       └── host.json
    └── test/
        └── java/example/azure/
            └── OrderFunctionApplicationTest.java
~~~

**Quy ước package:** đặt class `@SpringBootApplication` ở **package gốc** `example.azure`, cùng hoặc phía trên vị trí các Spring components. Mặc định component scan từ package này tìm được handler và các configurations bên dưới.

Nếu đưa handler sang `com.company.handlers` nằm ngoài package gốc, Spring có thể không tạo bean đó. Có thể sửa bằng bố cục package hợp lý hoặc cấu hình `scanBasePackages`/`@ComponentScan` rõ ràng. Đừng dùng scan toàn classpath không giới hạn vì dễ tạo bean ngoài chủ đích.

### 3.1. Cần tách handler và function bean

Handler phụ thuộc Azure SDK, còn function bean nghiệp vụ nên nhận/trả domain data hoặc Java types đơn giản:

~~~text
HTTP Trigger -> OrderAzureHandler -> FunctionCatalog
                                        |
                                        +-> normalizeOrder
                                        +-> addReferencePrefix
                                              -> "REF-DH-701"
~~~

Khi chuyển một nghiệp vụ sang Queue Trigger hoặc HTTP adapter khác, vẫn gọi cùng bean, chỉ thay boundary handler và serialization/ack policy.

## 4. Spring Boot main class và functional beans

Tạo `src/main/java/example/azure/OrderFunctionApplication.java`:

~~~java
package example.azure;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrderFunctionApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderFunctionApplication.class, args);
    }

    @Bean
    public Function<String, String> normalizeOrder() {
        return text -> {
            if (text == null || text.isBlank()) {
                throw new IllegalArgumentException(
                        "Mã đơn không được rỗng");
            }
            return text.strip().toUpperCase(Locale.ROOT);
        };
    }

    @Bean
    public Function<String, String> addReferencePrefix() {
        return code -> "REF-" + code;
    }
}
~~~

Ở đây:

- `@SpringBootApplication` là **root Spring configuration**, cung cấp component scan.
- Hai `@Bean` methods đăng ký functional beans có tên **`normalizeOrder`** và **`addReferencePrefix`**.
- `FunctionCatalog` có thể trả composition `normalizeOrder|addReferencePrefix` khi cả hai bean được phát hiện.
- Chữ ký `Function<String,String>` dễ thử và độc lập với Azure.
- `main(...)` hữu ích khi dùng Spring Boot ở môi trường khác; Azure adapter vẫn chọn class này làm application entrypoint từ config/manifest.

### 4.1. Tên cần phân biệt

| Tên | Hệ thống | Trách nhiệm |
| --- | --- | --- |
| `example.azure.OrderFunctionApplication` | Spring application | Lớp cấu hình chính. |
| `normalizeOrder` | Spring bean / SCF catalog | Chuẩn hóa mã. |
| `addReferencePrefix` | Spring bean / SCF catalog | Tạo tiền tố tham chiếu. |
| `normalizeOrder|addReferencePrefix` | SCF composition | Nối hai phép biến đổi. |
| `normalizeAzureOrder` | Azure Function | Tên Azure Host hiển thị và gọi. |
| `orders/normalize` | Azure HTTP trigger | URL route, mặc định nằm dưới `/api`. |
| `order-functions-demo-unique` | Azure Function App resource | Container quản lý và triển khai các Azure functions. |

Một Spring application có thể có **nhiều function beans** nhưng Azure Host chỉ nhìn thấy những Azure handler methods được annotation và package đúng. Một Azure Function App cũng có thể chứa nhiều `@FunctionName` methods nhưng chúng chia sẻ host settings và deployment boundary.

## 5. Azure handler dùng FunctionCatalog

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

    private final Function<String, String> pipeline;

    public OrderAzureHandler(FunctionCatalog catalog) {
        this.pipeline = Objects.requireNonNull(
                catalog.lookup("normalizeOrder|addReferencePrefix"),
                "Không tìm thấy function composition");
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
            String result = pipeline.apply(input);

            context.getLogger().info("Order normalized");

            return request
                    .createResponseBuilder(HttpStatus.OK)
                    .header("Content-Type",
                            "text/plain; charset=utf-8")
                    .body(result)
                    .build();
        }
        catch (RuntimeException failure) {
            context.getLogger().log(
                    Level.SEVERE, "Order processing failed", failure);

            return request
                    .createResponseBuilder(
                            HttpStatus.INTERNAL_SERVER_ERROR)
                    .body("Không thể xử lý mã đơn")
                    .build();
        }
    }
}
~~~

Nếu body là `" dh-701 "`, kết quả kỳ vọng là **`REF-DH-701`**. Trong ứng dụng thực, nên dùng error taxonomy rõ ràng: validation error → HTTP 400, hệ thống lỗi → 5xx, không log payload nhạy cảm. Ví dụ đã chủ động chặn body rỗng trước khi gọi pipeline.

### 5.1. Chỉ một Azure Function dù có hai @Bean

Class trên có **một** method `@FunctionName("normalizeAzureOrder")`, nên Azure plugin sinh metadata cho **một Azure Function**, không tự sinh hai Azure Functions từ `normalizeOrder`/`addReferencePrefix`.

### 5.2. Vì sao constructor injection?

`OrderAzureHandler` do Spring quản lý nhờ `@Component`. Khi tạo bean, Spring inject `FunctionCatalog` rồi lookup composition một lần; `Objects.requireNonNull` giúp lỗi tên function bị phát hiện sớm (*fail fast*). Không tự khởi tạo handler bằng `new OrderAzureHandler(...)` bên ngoài Spring adapter nếu muốn dùng DI.

### 5.3. @FunctionName và @HttpTrigger nằm ở đâu?

- `@FunctionName` nằm trên **public method**.
- `@HttpTrigger` nằm trên **tham số đầu vào** của method đó.
- `@Component` nằm trên **class handler**.
- `@SpringBootApplication` nằm trên **class cấu hình Spring**.

Azure Maven/Gradle plugin tạo binding metadata từ Azure annotations; Spring component scanning không thay thế bước này.

## 6. Dependencies và version alignment

### 6.1. Maven dependencies

Trong project đã có **Spring Boot parent** và **Spring Cloud BOM** tương thích:

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

**Đây là mảnh POM, không phải toàn bộ `pom.xml`.** Cần dùng Spring Boot parent/Cloud BOM thuộc một release train được công bố là tương thích; `spring-cloud-function-adapter-azure` yêu cầu mô hình hiện đại SCF **4.0.0+**. `1.3.1` ở Azure Java library chỉ là **phiên bản minh họa API**, không phải bản mới nhất tại mọi thời điểm; khi làm project thật hãy dùng version từ Azure Java template/version policy.

| Thành phần | Tại sao cần? |
| --- | --- |
| `spring-cloud-function-adapter-azure` | Spring DI và FunctionCatalog trong Azure Java Worker. |
| `spring-cloud-function-context` | Catalog và function wrapping/composition; thường được adapter kéo vào transitively. |
| `azure-functions-java-library` | `@FunctionName`, `@HttpTrigger`, `HttpRequestMessage`, `ExecutionContext`. |
| `spring-boot-starter-test` | JUnit 5/Spring context tests. |
| `azure-functions-maven-plugin` | **Build plugin** sinh metadata và package, không phải runtime dependency. |

Không cần `spring-boot-starter-web` chỉ để nhận Azure `@HttpTrigger`. Nếu muốn chạy Spring MVC controllers qua Azure HTTP, đó là một chiến lược adapter khác (`spring-cloud-function-adapter-azure-web`).

### 6.2. Gradle dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-adapter-azure'
    implementation 'com.microsoft.azure.functions:azure-functions-java-library:1.3.1'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Gradle vẫn cần Spring Boot/Spring Cloud dependency management và Azure Functions Gradle plugin riêng. **Chọn một** công cụ build chính cho project; đừng thêm Maven và Gradle với cấu hình khác nhau rồi deploy lẫn lộn.

### 6.3. Chọn Java và Azure Functions runtime

Azure Functions runtime **4.x** hỗ trợ các dòng Java phụ thuộc OS/hosting plan; các phiên bản thường gặp là Java 11, 17 và 21. Một project dùng Java records hoặc các tính năng Java 17 nên biên dịch và triển khai với Java 17+ tương thích. **Kiểm tra bảng support hiện hành của Microsoft** vì khả năng hỗ trợ còn tùy image, hosting plan và lịch vòng đời.

Cần khớp **ba giá trị**:

- JDK dùng compile và test local.
- Java target/release mà Maven/Gradle compiler tạo ra.
- Java runtime được cấu hình trên Azure Function App.

Lỗi `UnsupportedClassVersionError` là dấu hiệu bytecode Java mới hơn runtime đích.

## 7. Chỉ định main class: ba cơ chế

Đây là **phần then chốt** của chủ đề.

Spring Cloud Function Azure adapter cần biết **lớp `@SpringBootApplication`/`@SpringBootConfiguration`** để khởi tạo context. Theo tài liệu Spring, có thể dùng:

1. **Maven `start-class`** hoặc thông tin `Main-Class` trong JAR manifest.
2. **Gradle `jar.manifest`** ghi `Main-Class`.
3. **Biến môi trường `MAIN_CLASS`** ở local hoặc Azure App Settings.

Nếu `MAIN_CLASS` không được đặt, adapter tìm thông tin `Main-Class` ở JARs trên classpath và xác định lớp có Spring Boot application/configuration annotations thích hợp. Vì classpath có thể chứa nhiều JAR/entrypoints, dự án nên chọn **một cấu hình tường minh, có test**.

### 7.1. Maven start-class

~~~xml
<properties>
    <java.version>17</java.version>
    <start-class>example.azure.OrderFunctionApplication</start-class>
</properties>
~~~

`start-class` là convention của Spring Boot build. Nhưng khi **đã tắt Spring Boot repackage**, đừng mặc định mọi build tool sẽ tự viết manifest mong muốn. Cách chắc chắn là **kiểm tra JAR manifest** sau build, hoặc dùng `maven-jar-plugin` tạo `Main-Class` rõ ràng.

### 7.2. Maven JAR manifest tường minh

Một cách cấu hình manifest khi dùng **JAR thường**, không dùng Boot executable fat JAR:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <configuration>
        <archive>
            <manifest>
                <mainClass>example.azure.OrderFunctionApplication</mainClass>
            </manifest>
        </archive>
    </configuration>
</plugin>
~~~

Khi package, JAR thông thường sẽ chứa `META-INF/MANIFEST.MF` với:

~~~text
Manifest-Version: 1.0
Main-Class: example.azure.OrderFunctionApplication
~~~

**Quan trọng:** `Main-Class` phải trỏ tới **Spring application class**, không trỏ tới `OrderAzureHandler`. Azure worker dùng `function.json.entryPoint` để tìm annotated handler method; Spring adapter dùng `Main-Class`/`MAIN_CLASS` để tìm cấu hình context.

### 7.3. Gradle JAR manifest

~~~groovy
tasks.named('jar') {
    manifest {
        attributes(
            'Main-Class': 'example.azure.OrderFunctionApplication'
        )
    }
}
~~~

Nếu dùng Spring Boot Gradle plugin, cần tránh để `bootJar` thay thế artifact mà Azure plugin cần. Tùy version/build, có thể tắt `bootJar` hoặc cấu hình Azure Gradle plugin lấy standard JAR đúng layout.

### 7.4. MAIN_CLASS trong environment

Local `local.settings.json`:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "FUNCTIONS_EXTENSION_VERSION": "~4",
    "MAIN_CLASS": "example.azure.OrderFunctionApplication",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true"
  }
}
~~~

Trong Azure Function App, đặt **application setting**:

~~~text
MAIN_CLASS=example.azure.OrderFunctionApplication
~~~

Azure App Settings được Function App đưa vào môi trường runtime. **Không chỉ set `MAIN_CLASS` trong local settings rồi mặc định nó đã xuất hiện trên Azure**: local.settings.json không được đồng bộ lên cloud theo mặc định.

### 7.5. Thứ tự khuyến nghị

1. Đặt `@SpringBootApplication` ở package gốc.
2. Khóa `MAIN_CLASS` trong môi trường chạy khi cần, nhất là project có nhiều cấu hình.
3. Bảo đảm JAR manifest hoặc Maven `start-class` được khai báo đúng.
4. Kiểm tra runtime Spring logs và `@SpringBootTest`.
5. Không tạo nhiều class `@SpringBootApplication` cạnh tranh trong cùng deployment nếu không có lý do và chiến lược chọn rõ.

## 8. Azure Maven plugin: đóng gói chứ không chỉ biên dịch

`spring-cloud-function-adapter-azure` là thư viện runtime; **Azure Functions Maven plugin** chịu trách nhiệm sinh Azure package từ Java annotations.

### 8.1. Cấu hình plugin minh họa

Thêm vào `<build><plugins>` trong `pom.xml` đang có Spring Boot/Cloud dependency management:

~~~xml
<plugin>
    <groupId>com.microsoft.azure</groupId>
    <artifactId>azure-functions-maven-plugin</artifactId>
    <version>1.22.0</version>
    <configuration>
        <appName>order-functions-demo-unique</appName>
        <resourceGroup>order-demo-rg</resourceGroup>
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
~~~

Tài liệu Spring Cloud Function lấy **`1.22.0 hoặc mới hơn`** làm mốc Azure Maven plugin cho adapter hiện đại. Đây **không phải lời khẳng định `1.22.0` là bản mới nhất**. Trên dự án thật, khóa plugin version mới tương thích, Java runtime, hosting plan và resource settings.

**`appName`, `resourceGroup`, `region` trong mẫu đều là placeholder/giá trị minh họa**. Khi plugin tạo tài nguyên trên Azure, resource group, Azure subscription, service plan, pricing tier và tên Function App phải được quản trị theo chính sách. `appName` cần phù hợp quy tắc tên và duy nhất theo namespace Azure liên quan.

### 8.2. Vì sao cần plugin goal package?

Compiler Java chỉ tạo class/JAR. Azure plugin đọc `@FunctionName` và `@HttpTrigger` rồi sinh function metadata, staging layout cùng dependencies để Azure Host nhận diện method.

Một phần metadata **minh họa** cho handler của mục 5:

~~~json
{
  "scriptFile": "../order-functions-demo.jar",
  "entryPoint": "example.azure.OrderAzureHandler.normalize",
  "bindings": [
    {
      "type": "httpTrigger",
      "direction": "in",
      "name": "request",
      "methods": ["post"],
      "authLevel": "function",
      "route": "orders/normalize"
    },
    {
      "type": "http",
      "direction": "out",
      "name": "$return"
    }
  ]
}
~~~

Đây không phải file output byte-for-byte bắt buộc; `scriptFile` phụ thuộc artifact name và plugin layout. Các điểm đáng kiểm:

- `entryPoint` trỏ tới **handler Azure**.
- `httpTrigger` khai báo method/route/auth.
- HTTP output binding khai báo cách trả response.
- `function.json` được plugin sinh từ annotations, không phải file nguồn cần sửa tay.

### 8.3. Một Function App có nhiều Functions

Nếu source có thêm method `@FunctionName("receiveOrderQueue")` với `@QueueTrigger`, plugin sẽ tạo **một function metadata folder khác** trong cùng Function App package. Điều này **khác** việc tạo thêm Spring bean `@Bean Function` — bean đó không tự xuất hiện như Azure endpoint.

## 9. Vấn đề Spring Boot repackaged JAR và cách xử lý

### 9.1. Vì sao Spring Boot fat JAR gây xung đột?

Mặc định, `spring-boot-maven-plugin` có thể **repackage** application JAR theo cấu trúc executable Boot archive với `BOOT-INF/classes`, `BOOT-INF/lib` và launcher. Azure Java Worker lại mong layout Azure package do Azure Maven/Gradle plugin tạo, với JAR/classpath và metadata Azure tương ứng.

Do đó, **không chỉ copy `target/*.jar` lên Azure và mong nó chạy**. Một executable Boot fat JAR có thể chạy bằng `java -jar` nhưng Azure Host vẫn không tìm được `@FunctionName` handler hoặc Spring adapter.

### 9.2. Lựa chọn đơn giản: tắt Boot repackage

Trong `<build><plugins>`:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <skip>true</skip>
    </configuration>
</plugin>
~~~

Cách này phù hợp khi dự án dựa vào Azure plugin để tạo package. **Sau khi tắt**, cần chắc chắn Maven vẫn tạo JAR thường và có `Main-Class`/`MAIN_CLASS` để adapter tìm Spring application. Một số project cần cấu hình `maven-jar-plugin` như mục 7.

### 9.3. Các phương án khác

Tài liệu Spring cũng đề cập **Spring Boot Thin Launcher/layout** như một phương án thay cho tắt plugin, nhưng compatibility phụ thuộc bản Boot/SCF và build ecosystem. **Không tự thêm `spring-boot-thin-layout` vào project hiện đại** khi chưa xác minh artifact còn hỗ trợ trong version đang dùng.

Với Gradle, tùy project:

~~~groovy
tasks.named('bootJar') {
    enabled = false
}
tasks.named('jar') {
    enabled = true
    manifest {
        attributes('Main-Class':
                'example.azure.OrderFunctionApplication')
    }
}
~~~

Đây là mẫu định hướng: tên task/plugin và thứ tự đóng gói có thể khác theo phiên bản Gradle/Spring Boot/Azure plugin. Hãy xác nhận Azure plugin dùng **JAR thường** và tạo staging package đúng layout.

### 9.4. Checklist quyết định trước khi package

| Câu hỏi | Nếu câu trả lời là “không” |
| --- | --- |
| Maven/Gradle tạo standard application JAR phù hợp Azure? | Kiểm tra Boot repackage/bootJar. |
| `Main-Class` hoặc `MAIN_CLASS` trỏ đúng Spring configuration? | Sửa manifest/app setting. |
| Azure plugin quét được annotated handler? | Kiểm `@FunctionName`, trigger và public method. |
| Package có `host.json` và function metadata? | Kiểm Azure plugin goal và source hostJson path. |
| Dependencies runtime nằm trong layout Azure? | Kiểm plugin staging/lib và dependency resolution. |
| Java target tương thích Function App? | Kiểm compiler release và Azure runtime. |

**Tuyệt đối không sửa `function.json` trong staging rồi coi như đã sửa nguồn**. Thay đổi Java annotations/plugin config và build lại để có artifact có thể tái tạo.


## 10. Đọc package Azure sau khi build

### 10.1. Phân biệt source folder, build output và deployment artifact

Một cấu trúc Maven staging điển hình theo Microsoft Learn:

~~~text
azure-order-functions/
├── pom.xml
├── src/main/java/example/azure/...
├── src/main/resources/host.json
└── target/
    ├── classes/
    │   └── example/azure/...
    ├── order-functions-demo.jar
    └── azure-functions/
        └── order-functions-demo-unique/
            ├── host.json
            ├── order-functions-demo.jar
            ├── normalizeAzureOrder/
            │   └── function.json
            ├── bin/
            └── lib/
                └── [dependencies]
~~~

**Đây là sơ đồ minh họa**, không phải danh sách tên file chính xác mọi version. Tên JAR, `appName` và một số thư mục phụ tùy cấu hình plugin; không giả định có hai file JAR độc lập cần deploy riêng. Điều cốt lõi là **đóng gói và phát hành nội dung staging của Function App**, không lấy mỗi file JAR ở `target/`.

Theo tài liệu Microsoft về Java Functions, một Function App có thể chứa nhiều Java `@FunctionName` methods; tất cả thuộc **cùng một deployment context/package**. Không dùng nhiều application JARs độc lập như nhiều Function Apps bên trong một Function App.

### 10.2. Vai trò của các file sau package

| File/thư mục | Ý nghĩa | Cần kiểm tra |
| --- | --- | --- |
| `host.json` tại root | Cấu hình chung cho toàn Function App. | Đúng version/extension bundle/host settings. |
| `normalizeAzureOrder/function.json` | Metadata cho một Azure Function. | `entryPoint`, trigger/bindings, method, route, auth level. |
| Application `.jar` | Java bytecode và resources của project. | Package class và manifest đúng. |
| `lib/` | Dependencies runtime đi theo artifact. | Có Spring, SCF Azure adapter, Azure Java SDK cần thiết. |
| `bin/` hoặc thư mục phụ | Phần build/runtime phụ thuộc plugin. | Do plugin sinh; không tự suy đoán hoặc chỉnh tay. |
| `local.settings.json` | File settings cho phát triển local. | Không chứa trong package production trừ trường hợp quy trình đặc biệt được kiểm soát. |

### 10.3. Kiểm tra artifact thay vì chỉ tin build success

Sau khi đã chạy Maven package trong môi trường thực hành:

~~~bash
./mvnw clean package
~~~

Có thể kiểm nội dung staging bằng công cụ phù hợp hệ điều hành:

~~~bash
# Bash/macOS/Linux: khám phá package thực tế
find target/azure-functions -maxdepth 4 -type f

# Java JDK: xem nội dung JAR hoặc manifest
jar tf target/order-functions-demo.jar
unzip -p target/order-functions-demo.jar META-INF/MANIFEST.MF
~~~

Đây là ví dụ shell **phụ thuộc tên JAR của project**, không phải lệnh đã được thực thi trong bài. Với PowerShell:

~~~powershell
Get-ChildItem -Path target/azure-functions -Recurse -File
jar tf target/order-functions-demo.jar
~~~

Nếu build output không có đúng đường dẫn ví dụ, tìm tên artifact do plugin in ra thay vì tạo thêm bản sao thủ công để khớp tài liệu.

**Mẹo:** kiểm tra `function.json.entryPoint` phải trỏ tới `example.azure.OrderAzureHandler.normalize`, còn `Main-Class` hoặc `MAIN_CLASS` trỏ tới `example.azure.OrderFunctionApplication`. Đây là **hai class có vai trò khác nhau**.

### 10.4. Khi đóng ZIP thủ công: lấy đúng nội dung root

Nếu dùng phương án ZIP/package deployment phù hợp hosting plan, archive phải có `host.json` **ngay ở root khi giải nén**:

~~~text
ĐÚNG:
  host.json
  normalizeAzureOrder/function.json
  application.jar
  lib/...

SAI:
  target/azure-functions/order-functions-demo-unique/
    host.json
    normalizeAzureOrder/function.json
    application.jar
~~~

Nếu gói cả thư mục mẹ vào ZIP, Azure Host có thể không thấy `host.json` tại expected root. Ưu tiên dùng Azure build/deployment plugin để giảm nguy cơ đóng gói sai. Với các hosting plan và deployment technologies khác nhau, **không giả định một lệnh ZIP thủ công áp dụng được cho mọi Function App**.

## 11. host.json, application.properties và local.settings.json

Ba file này cùng xuất hiện trong project nhưng thuộc **ba tầng cấu hình khác nhau**.

### 11.1. host.json: cấu hình Azure Functions Host

`src/main/resources/host.json` tối thiểu:

~~~json
{
  "version": "2.0"
}
~~~

Nếu binding cần extension bundle và project dùng cách phân phối extension tương ứng, một ví dụ theo Spring reference là:

~~~json
{
  "version": "2.0",
  "extensionBundle": {
    "id": "Microsoft.Azure.Functions.ExtensionBundle",
    "version": "[4.*, 5.0.0)"
  }
}
~~~

Chọn extension bundle **đúng theo host, loại trigger và extension version được Microsoft hỗ trợ**. Không sao chép bundle version chỉ vì một sample HTTP dùng nó. `host.json` có thể chứa các cấu hình concurrency, logging và binding-specific settings ảnh hưởng đến **tất cả functions** trong cùng Function App.

Nếu `host.json` đặt tại `src/main/resources/host.json`, Azure Maven plugin phải được trỏ bằng `<hostJson>src/main/resources/host.json</hostJson>` như ví dụ. Sửa `host.json` ở source, package lại và phát hành artifact mới; không sửa trực tiếp bản trong staging sau khi build rồi mong CI tái lập được.

### 11.2. application.properties: cấu hình Spring

Ví dụ `src/main/resources/application.properties`:

~~~properties
orders.reference-prefix=REF-
logging.level.example.azure=INFO
~~~

Đây là properties tùy chọn. **Mẫu Java ở mục 4 cố định tiền tố `REF-`**, nên nếu muốn property trên thực sự có tác dụng, cần sửa bean `addReferencePrefix` để inject giá trị, chẳng hạn một `@Value` hoặc `@ConfigurationProperties` được test.

Không nhầm Spring properties với Azure app settings. Một số settings của Spring được Spring Boot bind từ environment variables và Azure Application Settings, nhưng cách đặt tên và độ ưu tiên nguồn cấu hình phải được kiểm chứng ở release train thực tế.

### 11.3. local.settings.json: cấu hình Azure Functions trên máy dev

Mẫu ở thư mục gốc project:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "FUNCTIONS_EXTENSION_VERSION": "~4",
    "MAIN_CLASS": "example.azure.OrderFunctionApplication",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true"
  }
}
~~~

| Setting | Vai trò |
| --- | --- |
| `FUNCTIONS_WORKER_RUNTIME=java` | Chọn worker runtime Java. |
| `FUNCTIONS_EXTENSION_VERSION=~4` | Chọn dòng Azure Functions runtime 4.x. |
| `MAIN_CLASS=...` | Chọn Spring Boot application configuration. |
| `AzureWebJobsStorage` | Host storage/trigger connection theo môi trường. |
| Các settings nghiệp vụ khác | URL/threshold/feature flags, phải khớp Spring binding. |

`UseDevelopmentStorage=true` yêu cầu **Azurite** hoặc emulator tương thích khi Host hoặc bindings cần storage. Khi dùng real Azure Storage, thay bằng phương thức connection/identity theo policy, không đưa connection string thật vào bản hướng dẫn hay commit.

**Bảo mật quan trọng:**

- `local.settings.json` có thể chứa secrets, nên không commit remote repository.
- Core Tools có tính năng mã hóa local settings, nhưng việc mã hóa không thay thế secret management cho production.
- Khi publish project, **local settings không được tự động đưa lên cloud theo mặc định**. Cấu hình Azure Function App settings riêng qua công cụ được phê duyệt.
- Nếu dùng CI, không xuất secrets ra logs hoặc lưu trong build artifacts.
- Với managed identity, các setting kết nối có thể dùng mô hình identity-based, nhưng binding extension và quyền IAM phải hỗ trợ đúng.

### 11.4. Phân biệt settings và code artifact

~~~mermaid
flowchart LR
    H["host.json"] --> A["Azure Host configuration"]
    L["local.settings.json"] --> B["Local environment"]
    P["Application properties"] --> C["Spring ApplicationContext"]
    S["Azure App Settings"] --> D["Cloud environment"]
    B --> A
    D --> A
    D --> C
~~~

Khi đổi `MAIN_CLASS` trên Azure, bạn thay **runtime configuration**. Khi đổi Java annotations của handler, bạn phải **rebuild/redeploy** để cập nhật binding metadata. Khi đổi `host.json`, nên phát hành config như một phần artifact có kiểm soát.

## 12. Gradle: cùng mục tiêu với Maven nhưng cấu hình khác

Nếu project dùng Gradle, không phải xây POM tương đương chỉ để deploy Azure. Azure Functions Gradle plugin cũng có nhiệm vụ quét annotations và sinh staging package.

### 12.1. Plugin và dependencies

Ví dụ định hướng cho dự án đã có Spring Boot/Spring Cloud dependency management:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '...'
    id 'com.microsoft.azure.azurefunctions' version '1.11.0'
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-adapter-azure'
    implementation 'com.microsoft.azure.functions:azure-functions-java-library:1.3.1'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`'...'` là **placeholder phải thay bằng version Spring Boot thật được project chọn**. Azure plugin `1.11.0` chỉ là một **ví dụ từ tài liệu Spring**, không phải version mới nhất hay lời khuyên cố định version. Dự án cần Spring Cloud BOM và dependency version alignment theo release train.

### 12.2. Không đóng gói bootJar sai

Với Spring Boot Gradle plugin, cần kiểm soát task `bootJar` nếu Azure plugin mong standard jar:

~~~groovy
tasks.named('bootJar') {
    enabled = false
}

tasks.named('jar') {
    enabled = true
    manifest {
        attributes('Main-Class':
                'example.azure.OrderFunctionApplication')
    }
}
~~~

Không áp dụng nguyên mẫu này vào mọi build chưa kiểm tra dependencies/plugin tasks. Trong các Gradle versions, task configuration và artifact selection có thể khác. Hãy xác nhận staging package được tạo hợp lệ.

### 12.3. Azure Gradle config

Ví dụ theo cấu trúc plugin:

~~~groovy
azurefunctions {
    appName = 'order-functions-demo-unique'
    resourceGroup = 'order-demo-rg'
    region = 'eastasia'

    runtime {
        os = 'linux'
        javaVersion = '17'
    }

    auth {
        type = 'azure_cli'
    }

    appSettings {
        FUNCTIONS_EXTENSION_VERSION = '~4'
    }
}
~~~

Tùy Azure Functions Gradle plugin version, syntax/value của properties và thông tin hosting plan có thể khác. Kiểm tra version đã khóa và docs của plugin. Không giả định plugin sẽ tự chọn hosting plan/price tier theo kỳ vọng doanh nghiệp nếu cấu hình bỏ trống.

### 12.4. Các lệnh Gradle

~~~bash
./gradlew clean azureFunctionsPackage
./gradlew azureFunctionsRun
~~~

Đây là lệnh **để người học chạy trong project Gradle phù hợp**, không phải đã được chạy trong bước tạo bài. Sau package, kiểm Azure metadata, Java runtime và main class như với Maven.

## 13. Chạy local bằng Azure Functions Core Tools

### 13.1. Điều kiện cần

Chuẩn bị:

- JDK phù hợp Java target, ví dụ Java 17.
- Maven hoặc Gradle cùng wrapper đã được project thiết lập.
- Azure Functions Core Tools **v4**.
- Azurite khi host/binding cần local Azure Storage.
- Azure CLI khi định triển khai/kiểm tra tài nguyên cloud, không bắt buộc để unit test.

**Đừng dùng `java -jar` để thay thế một Azure Host integration test.** Đích chạy thực tế là Azure Java Worker do Azure Functions Host điều phối; `java -jar` không kiểm chứng `@FunctionName` metadata hoặc HTTP trigger.

### 13.2. Maven local workflow

~~~bash
./mvnw clean package
./mvnw azure-functions:run
~~~

Với project không có Maven wrapper, dùng `mvn` đã cài và khóa version theo quy trình tổ chức. Quan sát log startup xem host có discover `normalizeAzureOrder` không.

Route mặc định:

~~~text
POST http://localhost:7071/api/orders/normalize
~~~

Cổng và `routePrefix` có thể thay đổi theo host config. Gửi request:

~~~bash
curl -i -X POST "http://localhost:7071/api/orders/normalize" \
  -H "Content-Type: text/plain" \
  --data " dh-701 "
~~~

Kết quả mong đợi:

~~~text
HTTP/1.1 200 OK

REF-DH-701
~~~

Thử body rỗng/chỉ có dấu cách → HTTP 400. Nếu host không liệt kê `normalizeAzureOrder`, kiểm Azure annotation/metadata trước; nếu host liệt kê nhưng invocation lỗi Spring, kiểm main class và dependency injection.

### 13.3. Kiểm tra function key

`AuthorizationLevel.FUNCTION` là policy của Azure Host cho HTTP trigger. Local Core Tools có thể không enforce key giống cloud. Khi triển khai thật, dùng function/host key theo policy, nhưng **function key không thay thế hoàn toàn authentication/authorization** cho API nhạy cảm hoặc ứng dụng đa tenant.

Không đặt key trong ví dụ công khai, log hoặc query string không được quản lý an toàn. Ưu tiên cơ chế API gateway/authentication và network policy phù hợp.

### 13.4. Vì sao không test bằng Spring MVC?

Handler dùng `@HttpTrigger` là một **Azure Functions Java method**. Không cần `@RestController`, `spring-boot-starter-web` hoặc embedded Tomcat cho ví dụ này. Nếu muốn Spring MVC/WebFlux controllers trong Azure, hãy cân nhắc adapter chuyên dụng `spring-cloud-function-adapter-azure-web`; không pha trộn hai mô hình mà thiếu lý do thiết kế.

## 14. Kiểm thử trước khi triển khai

Có thể chia kiểm thử thành bốn tầng, mỗi tầng phát hiện một nhóm lỗi khác nhau.

### 14.1. Unit test hai function beans

Không cần Azure Host:

~~~java
OrderFunctionApplication application =
        new OrderFunctionApplication();

String value = application.addReferencePrefix()
        .apply(application.normalizeOrder().apply(" dh-701 "));

assertEquals("REF-DH-701", value);
~~~

Thêm test input chỉ có khoảng trắng và case Unicode; import JUnit 5 `assertEquals`/`assertThrows`. Đoạn này kiểm **business logic** chứ chưa kiểm DI/catalog.

### 14.2. Spring context + FunctionCatalog

Tạo `src/test/java/example/azure/OrderFunctionApplicationTest.java`:

~~~java
package example.azure;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = OrderFunctionApplication.class)
class OrderFunctionApplicationTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    OrderAzureHandler handler;

    @Test
    void springCreatesHandlerAndCatalog() {
        assertNotNull(handler);
        assertNotNull(catalog);
    }

    @Test
    void compositionReturnsExpectedOutput() {
        Function<String, String> function =
                catalog.lookup("normalizeOrder|addReferencePrefix");

        assertNotNull(function);
        assertEquals("REF-DH-701",
                function.apply(" dh-701 "));
    }
}
~~~

Nếu context test fail do không có `OrderAzureHandler`, kiểm `@Component` và component scan. Nếu `catalog.lookup(...)` trả null, kiểm tên `@Bean` và definition. Nếu cả test này PASS nhưng Azure Host không discover function, vấn đề nhiều khả năng nằm ở **Azure annotations/build metadata/package**, không phải Spring DI.

### 14.3. Kiểm Azure handler annotations qua reflection

Ví dụ JUnit bổ sung:

~~~java
@Test
void azureHandlerHasExpectedName()
        throws NoSuchMethodException {

    var method = OrderAzureHandler.class.getMethod(
            "normalize",
            HttpRequestMessage.class,
            ExecutionContext.class);

    assertEquals("normalizeAzureOrder",
            method.getAnnotation(FunctionName.class).value());
}
~~~

Import `HttpRequestMessage`, `ExecutionContext` và `FunctionName` của Azure. Test reflection chỉ kiểm source annotation, **không** thay thế Azure plugin packaging.

### 14.4. Host-level smoke test

| Bài kiểm tra | Điều cần chứng minh |
| --- | --- |
| Maven/Gradle package | Azure plugin tạo metadata và staging layout. |
| Function discovery | Host liệt kê đúng `normalizeAzureOrder`. |
| HTTP POST hợp lệ | Body `REF-DH-701`, HTTP 200. |
| Body rỗng | HTTP 400, không ném exception không cần thiết. |
| Sai HTTP method | Không được xử lý như POST hợp lệ; status cụ thể do host quyết định. |
| Main class sai | Spring context startup log chỉ rõ lý do. |
| Java target sai | Runtime phát hiện `UnsupportedClassVersionError` hoặc class load failure. |
| Cloud staging key/auth | Request thiếu/sai key bị từ chối theo policy thực. |

Các test này nên chạy trong environment gần production trước khi publish rộng.

### 14.5. Điều Spring test chưa chứng minh

`@SpringBootTest` không khởi động Azure Functions Host, nên chưa chứng minh `function.json` được tạo, Azure extension đã được load, route/auth hoạt động, app settings cloud đúng hoặc classpath Azure runtime có đủ dependencies. Đừng báo “Azure-ready” chỉ vì tất cả Java unit tests xanh.


## 15. Triển khai lên Azure: runtime, plan và phương pháp deployment

### 15.1. Trước khi deploy cần có gì?

Triển khai cloud là **thao tác khác với package local**. Trước khi chạy, cần xác định:

- Azure subscription và tenant đã được cấp quyền.
- Resource group, Function App name, region.
- Hosting plan: Flex Consumption, Consumption (legacy), Elastic Premium, Dedicated (App Service) hoặc Container Apps theo nhu cầu.
- OS và **Java runtime version** đúng với bytecode của build.
- Azure Functions runtime 4.x và app settings cần thiết.
- Host storage, trigger-specific connections và identity/RBAC.
- Network restrictions, authentication, observability, retention và quy trình rollback.

Không coi `resourceGroup`/`region` trong ví dụ Maven plugin là cấu hình đủ cho production. Một số project còn cần app service plan, pricing tier, storage account, app insights, identities và secret configuration — tốt nhất được quản lý bằng **infrastructure as code (IaC)**.

### 15.2. Package deployment khác nhau theo hosting plan

Microsoft hiện cung cấp nhiều deployment technologies, không có một lệnh ZIP thủ công tối ưu cho mọi loại Function App:

| Hosting plan / trường hợp | Cách triển khai cần hiểu | Điểm cần tránh |
| --- | --- | --- |
| **Flex Consumption** | Code package deployment được platform quản lý; có cơ chế rolling update khi cấu hình hỗ trợ. | **Không đặt `WEBSITE_RUN_FROM_PACKAGE=1`** theo kiểu ZIP deployment truyền thống; Flex **không có deployment slots**. |
| **Elastic Premium** | ZIP deployment/run-from-package được hỗ trợ; có thể dùng deployment slots theo tài liệu. | Không deploy ZIP sai root hoặc bỏ quên slot-specific settings. |
| **Dedicated (App Service)** | ZIP deployment/run-from-package hoặc phương án được plan hỗ trợ. | Không dùng production slot để thử thay đổi không qua kiểm thử. |
| **Consumption Windows (legacy)** | ZIP deployment/run-from-package theo quy tắc plan. | Không giả định cấu hình của Linux Consumption áp dụng nguyên xi. |
| **Consumption Linux (legacy)** | Cơ chế remote build/external package URL tùy quy trình; có ràng buộc riêng. | Không mặc định `WEBSITE_RUN_FROM_PACKAGE=1` dùng được như trên Windows. |
| **Azure Container Apps** | Triển khai container image và revisions. | Không coi Java Azure Functions ZIP artifact là một container image. |

**Phải kiểm tra lại tài liệu Microsoft cho đúng plan/OS tại thời điểm phát hành.** Tình trạng hỗ trợ và chính sách vòng đời có thể thay đổi; các lệnh plugin thường chọn deployment flow theo tài nguyên đã cấu hình nhưng bạn vẫn phải hiểu resource target và xác minh kết quả.

### 15.3. Triển khai bằng Azure Maven plugin

Sau khi đã package và có quyền Azure CLI:

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

./mvnw clean package
./mvnw azure-functions:deploy
~~~

Đây là **các lệnh minh họa**, không được chạy trong bước tạo bài và có thể **tạo/sửa tài nguyên, thay đổi phiên bản code đang chạy, phát sinh chi phí**. `<SUBSCRIPTION_ID>` phải thay bằng subscription thực đã được tổ chức phê duyệt.

Đối với Gradle:

~~~bash
az login
./gradlew azureFunctionsPackage
./gradlew azureFunctionsDeploy
~~~

`az login` không tự bảo đảm tài khoản đang ở đúng subscription/resource group. Kiểm tra danh tính và target configuration trước khi bấm phát hành, tránh deploy nhầm môi trường.

### 15.4. Nếu dùng ZIP deployment

Một số hosting plan hỗ trợ deployment bằng ZIP của **Azure staging package**. Microsoft hướng dẫn Azure CLI tương ứng:

~~~bash
az functionapp deployment source config-zip \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<FUNCTION_APP_NAME>" \
  --src "<AZURE_PACKAGE_ZIP>"
~~~

**Chỉ dùng với plan hỗ trợ ZIP deployment và artifact đã đúng layout**. Không đưa JAR đơn lẻ hoặc ZIP gồm một thư mục mẹ sai root. Với Flex Consumption, phải dùng **Flex package deployment** qua công cụ hỗ trợ plan — không lấy lệnh config-zip mặc định của các plan khác rồi áp dụng.

Nếu triển khai từ một URL package bên ngoài, cơ chế URL, storage credentials/managed identity và đồng bộ triggers có yêu cầu riêng. Không gắn blob URL có token dài hạn vào tài liệu hoặc log.

### 15.5. App settings cloud khác local settings

Ví dụ những settings cần được bảo đảm trên Azure:

~~~text
FUNCTIONS_WORKER_RUNTIME=java
FUNCTIONS_EXTENSION_VERSION=~4
MAIN_CLASS=example.azure.OrderFunctionApplication
AzureWebJobsStorage=[connection hoặc identity settings theo kế hoạch]
~~~

`AzureWebJobsStorage` ở cloud không được để `UseDevelopmentStorage=true` vì giá trị đó dành cho emulator local. Với identity-based connections, tên và giá trị settings sẽ khác connection string thông thường và phụ thuộc extension/permissions.

**Không đưa production secrets vào `pom.xml`, `host.json` hoặc Git repository.** Dùng Azure App Settings, Key Vault references/managed identity và quyền tối thiểu khi phù hợp. Khi đổi app settings, ứng dụng có thể cần restart; quy trình phát hành phải tính đến ảnh hưởng này.

### 15.6. Kiểm tra ngay sau deployment

Không chỉ nhìn log “deployment succeeded”. Trên môi trường staging/production đã được cấp phép, cần xác minh:

1. Function App đang chọn đúng Azure runtime và **Java version**.
2. Host startup log không báo lỗi class loading, Spring context hoặc adapter.
3. Azure Host liệt kê `normalizeAzureOrder` (và những function khác nếu có).
4. HTTP POST trả `REF-DH-701` cho input hợp lệ và 400 cho body rỗng.
5. Authorization/authentication/network policies đúng trên cloud.
6. App Settings và trigger connections hoạt động; không có secrets trong log.
7. Nếu có Queue/Timer/Event triggers, chúng chạy và retry/ack theo chính sách.
8. Telemetry, health/alerts và business metrics hiển thị đúng.
9. Artifact đã triển khai có version/commit ID đủ để rollback.

Một chức năng nhìn thấy trên Azure Portal nhưng không gọi được vẫn có thể do route, key, dependency initialization, storage hoặc network policies; phải đọc logs và diagnostic details.

## 16. CI/CD, staging, rollback và vận hành production

### 16.1. Quy trình phát hành khuyến nghị

Một pipeline có thể gồm:

~~~mermaid
flowchart LR
    A["Commit có review"] --> B["Build / dependency resolution"]
    B --> C["Unit + Spring context tests"]
    C --> D["Azure plugin package"]
    D --> E["Inspect host.json, function.json, Main-Class"]
    E --> F["Lưu immutable versioned artifact"]
    F --> G["Deploy staging hoặc release environment"]
    G --> H["Smoke test: discovery / HTTP / trigger"]
    H --> I{"Đạt release gate?"}
    I -->|Có| J["Promote / deploy production"]
    I -->|Không| K["Dừng phát hành, rollback"]
    J --> L["Monitor / alert / audit"]
~~~

**Một lần build — nhiều môi trường:** nếu có thể, build ra một artifact đã khóa version, phát hành đúng artifact qua staging → production, còn môi trường khác nhau dùng App Settings/identity. Tránh rebuild cùng commit bằng dependency versions không khóa rồi tạo các JAR khác nhau cho mỗi environment.

### 16.2. Chính sách artifact

- Khóa Spring Boot/Cloud BOM, Azure Maven/Gradle plugin và Java toolchain; review các bản cập nhật.
- Giữ artifact hash, commit SHA, build metadata và dependency SBOM theo quy trình tổ chức.
- Không cache và deploy nhầm một `target/azure-functions` cũ từ branch khác.
- Không chỉnh tay `function.json` sau build.
- Scan dependencies và secrets theo yêu cầu bảo mật.
- Kiểm tra Java target/OS/runtime tương thích trước khi release.

### 16.3. Staging và deployment slots

Với hosting plan **có hỗ trợ deployment slots**, có thể deploy vào staging slot, chạy smoke tests rồi **swap** sang production để giảm ảnh hưởng. Các settings có đánh dấu *slot setting* phải được kiểm tra để không làm staging dùng production connections nhầm.

**Flex Consumption không hỗ trợ deployment slots**. Với Flex cần dùng chiến lược package deployment/rolling updates tương ứng hoặc tách staging thành một Function App riêng, tùy yêu cầu. Không tự giả định mọi hosting plan có nút “swap slot”.

### 16.4. Phát hành có thể ảnh hưởng invocation đang chạy

Một deployment có thể restart hoặc thay process của Function App. Khi các invocations đang chạy bị ngắt, hệ thống event-driven có thể **retry/redeliver** tùy trigger.

Vì vậy:

- Thiết kế handler stateless và **idempotent** với event/Queue workloads.
- Phân biệt **Azure invocation ID** với **business event ID**; khi retry invocation ID có thể đổi.
- Đối với HTTP, xác định contract timeout/client retry và correlation ID.
- Đối với broker, có poison queue/dead-letter và hành vi khi processing bị ngắt.
- Giám sát tỷ lệ lỗi, queue backlog, latency/cold start và tài nguyên sau deploy.

### 16.5. Rollback theo loại triển khai

Nếu release lỗi:

1. **Dừng promotion** khi staging smoke tests không đạt.
2. Nếu dùng slots được hỗ trợ, dùng quy trình swap/revert theo tài liệu để quay về phiên bản ổn định.
3. Nếu dùng package/ZIP deployment, **redeploy artifact ổn định trước đó** bằng đúng công cụ/plan.
4. Kiểm tra app settings và schema changes: rollback code không tự rollback database hoặc event schema.
5. Chạy lại smoke tests, xác nhận Host discovery và nghiệp vụ hoạt động.
6. Đối soát Queue/Event messages, retry và idempotency để không bỏ sót công việc bị ngắt.

**Không dùng “rollback bằng cách sửa trực tiếp file trên portal”** như quy trình chuẩn nếu triển khai theo package read-only. Rollback nên dựa trên artifact/version có thể truy vết.

### 16.6. Tại sao cần monitoring?

Một thành công HTTP 200 chỉ chứng minh request/reply đó hoạt động; với những function khác, cần theo dõi:

- Startup failures (Spring/Java/adapter).
- Trigger discovery/binding extension errors.
- HTTP 4xx/5xx và latency, cold start.
- Queue/event backlog, retries, dead-letter/poison queues.
- JVM memory, thread/concurrency và dependency response times.
- Thời gian và kết quả của deployment/rollback.

Không ghi log function keys, HTTP Authorization headers, tokens hoặc toàn bộ payload nhạy cảm.

## 17. Troubleshooting: lỗi nào thuộc tầng nào?

| Triệu chứng | Tầng | Nguyên nhân/cách xử lý |
| --- | --- | --- |
| `@SpringBootTest` không tìm handler | **Spring DI** | `@Component` thiếu, handler nằm ngoài package scan, main class sai. |
| `FunctionCatalog` lookup trả null | **SCF registration** | Sai `@Bean` name/definition, dependency context hoặc composition. |
| Azure Host không liệt kê function | **Azure discovery/build** | Thiếu `@FunctionName`/trigger, method không public, plugin không sinh `function.json`. |
| Azure Host liệt kê nhưng gọi 404/405 | **HTTP route** | Sai routePrefix, path, HTTP method hoặc hostname. |
| Azure HTTP 401/403 trên cloud | **Auth/network** | Function key, authentication provider, access restrictions. |
| `MAIN_CLASS` không trỏ tới class Spring | **Spring startup** | Sai fully qualified name hoặc chọn nhầm configuration. |
| Manifest Main-Class trỏ vào handler | **Packaging/config** | Sửa thành `OrderFunctionApplication`, build/redeploy. |
| `ClassNotFoundException` cho handler/SCF | **Classpath** | JAR/lib staging thiếu dependencies, fat JAR sai layout. |
| `UnsupportedClassVersionError` | **Java runtime** | Bytecode build mới hơn Azure runtime; căn chỉnh Java target. |
| Plugin package không có `host.json` | **Azure plugin config** | Sai `hostJson` path hoặc copy resources lỗi. |
| `function.json` có `entryPoint` sai | **Build metadata** | Package lại từ Java method annotations đúng. |
| Boot fat JAR chạy bằng `java -jar` nhưng Azure lỗi | **Artifact format** | Tắt/điều chỉnh repackage, dùng Azure plugin staging. |
| Maven build fail version conflict | **Dependency management** | Khóa Boot/Cloud release train và Azure Java library phù hợp. |
| Local chạy, cloud không inject bean | **Environment/runtime** | `MAIN_CLASS`, settings, classpath hoặc Spring profiles khác. |
| Local storage chạy, cloud storage lỗi | **Connections/identity** | AzureWebJobsStorage/permissions; đừng dùng emulator setting cloud. |
| Không thấy log/telemetry | **Observability** | Log level, monitoring integration, retention hoặc sampling. |
| App scale lỗi state lẫn requests | **Concurrency** | Không giữ invocation state trong singleton; dùng immutable/local values. |
| Queue event xử lý trùng sau deploy | **Delivery/retry** | Idempotency, retry/poison policy và resume logic. |
| ZIP deploy thành công nhưng app không thấy functions | **ZIP root/layout** | `host.json` phải ở package root, không ở thư mục mẹ. |
| Flex deployment lỗi với config ZIP truyền thống | **Hosting plan** | Dùng Flex package deployment đúng plan; không set `WEBSITE_RUN_FROM_PACKAGE=1`. |

### 17.1. Một trình tự điều tra hiệu quả

~~~text
1. Source: @SpringBootApplication và @FunctionName có đúng?
2. Compile: Java target, imports và dependencies có hợp lệ?
3. Azure package: host.json, function.json, JAR, lib có đầy đủ?
4. Main class: MAIN_CLASS/manifest trỏ đúng Spring config?
5. Runtime: Azure Host có discover đúng function/trigger?
6. Spring: DI và FunctionCatalog khởi tạo đúng?
7. Business: handler response và errors đúng schema?
8. Cloud: auth, storage, identity, Java runtime, hosting plan?
9. Operation: metrics, retry, scaling, CI/CD và rollback?
~~~

**Không sửa vấn đề Spring DI bằng cách chỉnh HTTP route; không sửa lỗi Azure discovery bằng cách thay function bean name.** Phải xác định đúng tầng trước khi can thiệp.

## 18. Bài tập thực hành và tự đánh giá

### 18.1. Bài tập theo thứ tự tăng dần

1. **Cấu hình root package:** chuyển `OrderAzureHandler` ra một package không được scan; chạy Spring context test rồi sửa bố cục package hoặc `@ComponentScan`.
2. **Đổi main class:** khai báo `MAIN_CLASS` sai, quan sát Spring startup failure rồi chỉnh lại.
3. **Manifest:** inspect `META-INF/MANIFEST.MF` trong JAR; phân biệt `Main-Class` với `function.json.entryPoint`.
4. **Fat JAR:** thử package với Boot repackage bật/tắt trong nhánh thử nghiệm; so sánh artifact và Azure staging layout.
5. **Function metadata:** đổi `@FunctionName("normalizeAzureOrder")` thành tên khác, package lại và xem thư mục/function.json mới. Xác minh bean name/catalog definition không tự thay đổi.
6. **Thêm một Azure Function:** tạo Queue Trigger riêng cùng gọi `FunctionCatalog.lookup("normalizeOrder")`; so sánh package có thêm function metadata nhưng Spring functional bean vẫn dùng lại.
7. **Host settings:** thêm extension bundle được tài liệu hỗ trợ rồi xác nhận binding load đúng, không đơn thuần copy config.
8. **Runtime mismatch:** biên dịch class cho Java target cao hơn runtime test (trong môi trường riêng) để phân tích lỗi class version; không áp dụng lên production.
9. **Smoke test:** gửi POST hợp lệ và rỗng, kiểm HTTP 200/400, function key trên cloud staging.
10. **Artifact release:** thiết kế pipeline lưu artifact version/hash, deploy staging, kiểm tra function discovery, promotion và rollback.
11. **Hosting plan:** so sánh Flex Consumption với Premium về ZIP/package deployment và deployment slots; giải thích vì sao không dùng cùng `WEBSITE_RUN_FROM_PACKAGE` value.
12. **Secrets:** chuyển storage connection từ local emulator sang managed identity trong một environment thử nghiệm được cấp quyền; kiểm tra quyền extension và không commit settings nhạy cảm.

### 18.2. Câu hỏi tự đánh giá

- `@SpringBootApplication` và `@FunctionName` khác nhau ở vai trò gì?
- Tại sao có hai `@Bean Function` nhưng chỉ một `@FunctionName` sẽ chỉ có một Azure function metadata?
- Khi nào adapter sử dụng `MAIN_CLASS` và vì sao nên chỉ định rõ trong ứng dụng nhiều entrypoints?
- Sự khác biệt giữa `Main-Class` trong JAR và `entryPoint` của `function.json` là gì?
- Vì sao `spring-boot:repackage` có thể làm Azure Java Worker không load được code?
- Azure Maven/Gradle plugin làm gì ngoài việc biên dịch Java?
- Vì sao ZIP phải chứa `host.json` ở root sau giải nén?
- Vì sao `local.settings.json` không nên commit và không tự trở thành Azure App Settings?
- Tại sao Java target và Java runtime Azure phải tương thích?
- `@SpringBootTest` PASS chứng minh điều gì và **không** chứng minh điều gì?
- Vì sao Flex Consumption không được áp dụng trực tiếp quy trình deployment slots/ZIP run-from-package của Premium?
- Cần giữ những artifact và metadata gì để rollback một release có thể tái tạo?

## 19. Tài liệu tham khảo chính thức

- [Spring Cloud Function — Microsoft Azure Functions](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): Azure adapter, `@Component`, `FunctionCatalog`, Maven/Gradle plugins, Spring Boot packaging, main class, host.json và build/run/deploy.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `Supplier`, `Function`, `Consumer`, composition, wrapper và type conversion.
- [Microsoft Learn — Azure Functions Java Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-java): Java project layout, `@FunctionName`, `function.json`, runtime/JDK support và deployment.
- [Microsoft Learn — Java Azure Functions Quickstart](https://learn.microsoft.com/en-us/azure/azure-functions/create-first-function-cli-java): Maven archetype, package, local run và deployment.
- [Microsoft Learn — Run Azure Functions Locally](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local): Core Tools, local.settings.json, storage và settings deployment.
- [Microsoft Learn — Deployment Technologies](https://learn.microsoft.com/en-us/azure/azure-functions/functions-deployment-technologies): các phương thức phát hành theo hosting plan, deployment slots và Flex package deployment.
- [Microsoft Learn — Package-based Deployment](https://learn.microsoft.com/en-us/azure/azure-functions/deployment-zip-push): ZIP root layout, run-from-package settings, Flex và các hosting plans.
- [Microsoft Learn — Azure Functions Hosting Options](https://learn.microsoft.com/en-us/azure/azure-functions/functions-scale): kế hoạch hosting, scale và những giới hạn liên quan.
- [Microsoft Learn — Azure Functions Deployment Slots](https://learn.microsoft.com/en-us/azure/azure-functions/functions-deployment-slots): quản lý staging/production slots trên các plan hỗ trợ.
- [Spring Cloud Function Samples](https://github.com/spring-cloud/spring-cloud-function/tree/main/spring-cloud-function-samples): các project mẫu HTTP Trigger Maven/Gradle, Blob, Timer và Azure Web Adapter.

**Kết luận:** Để triển khai Spring Cloud Function lên Azure, cần cấu hình đúng **Spring main class** (qua `@SpringBootApplication`, `Main-Class`/`Start-Class` hoặc `MAIN_CLASS`), khai báo **Azure handler methods** bằng `@FunctionName` và trigger annotations, rồi dùng **Azure Maven/Gradle plugin** sinh `function.json` và package hợp lệ thay vì đưa Boot fat JAR trực tiếp lên host. Khi đã căn chỉnh Java runtime, `host.json`, secrets/app settings và hosting plan, hãy kiểm tra artifact, chạy Azure Host local, triển khai qua môi trường staging/CI và chuẩn bị rollback. Tách biệt rõ Spring DI/FunctionCatalog với Azure discovery và deployment là điều kiện để cùng logic `Supplier`, `Function` và `Consumer` có thể được tái sử dụng an toàn qua HTTP, sự kiện hoặc các nền tảng serverless khác.
