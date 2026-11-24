# Đóng gói JAR cho Lambda và xác định lớp ứng dụng

Trong **SPRING_CLOUD_FUNCTION**, ta có thể viết logic bằng **Supplier<T>**, **Function<T, R>** hoặc **Consumer<T>** mà không cần phụ thuộc trực tiếp vào HTTP, message broker hay AWS Lambda. Tuy nhiên, để chạy những bean đó trên **AWS Lambda**, hệ thống cần một artifact Java có cấu trúc phù hợp: Lambda phải nạp được **handler**, adapter phải tìm được **lớp ứng dụng Spring Boot**, và **FunctionCatalog** phải tra cứu đúng tên hàm.

Bài thuộc chương **AWS Lambda**, tập trung vào hai việc: **đóng gói JAR có đủ lớp và metadata** và **xác định main class để Spring Cloud Function khởi tạo context**. Ta dùng mô hình Java Lambda JAR với **spring-cloud-function-adapter-aws**; các đường triển khai container image hoặc custom runtime có quy tắc packaging khác.

## 1. Ba định danh phải phân biệt

Một ứng dụng Spring Cloud Function chạy trên Lambda có thể dùng ba tên hoàn toàn khác nhau:

| Tên | Ví dụ | Vai trò |
| --- | --- | --- |
| **AWS Lambda handler** | **org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest** | Điểm vào mà Lambda runtime gọi |
| **Spring Boot application class** | **example.lambda.QuoteLambdaApplication** | Lớp giúp adapter khởi tạo Spring ApplicationContext |
| **Function bean name** | **calculateQuote** | Tên logic được FunctionCatalog tra cứu |

~~~mermaid
flowchart LR
    A["AWS Lambda invocation"] --> B["FunctionInvoker"]
    B --> C["QuoteLambdaApplication"]
    C --> D["Spring ApplicationContext"]
    D --> E["FunctionCatalog"]
    E --> F["calculateQuote bean"]
    F --> B
    B --> G["Lambda response"]
~~~

- **Handler** là lớp/phương thức do adapter AWS cung cấp; nó phải xuất hiện trên runtime classpath.
- **Application class** thường được đánh dấu **@SpringBootApplication**; adapter dùng nó để tạo context.
- **Function bean** là đối tượng Java implement **Function**, **Supplier** hoặc **Consumer**; tên bean có thể được chọn bằng property **spring.cloud.function.definition**.

Không dùng **calculateQuote** làm tên Lambda handler. Cũng không trỏ handler tới **QuoteLambdaApplication::main**, vì **main(String[] args)** không phải chữ ký xử lý AWS invocation trong mô hình adapter này.

## 2. Vì sao JAR chạy được bằng java -jar vẫn có thể lỗi trên Lambda?

Một **Spring Boot executable JAR** thường có cấu trúc:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/example/lambda/QuoteLambdaApplication.class
BOOT-INF/lib/spring-cloud-function-adapter-aws-....jar
BOOT-INF/lib/spring-context-....jar
org/springframework/boot/loader/...
~~~

Khi chạy **java -jar**, Spring Boot launcher hiểu cấu trúc **BOOT-INF** và nạp các dependency JAR lồng nhau. Nhưng với đường triển khai **Java JAR trên AWS Lambda**, runtime cố gắng tải lớp handler qua classpath theo cơ chế của Lambda; nó không mặc nhiên vận hành giống Boot launcher.

Do đó, các mẫu **Spring Cloud Function AWS adapter** thường sử dụng **shaded JAR (uber JAR)** cho đường deploy JAR: lớp ứng dụng, adapter và dependency xuất hiện theo bố cục mà classloader Java có thể nạp trực tiếp.

~~~mermaid
flowchart TB
    A["Java source + Maven/Gradle dependencies"] --> B{"Kiểu đóng gói"}
    B --> C["Boot executable JAR"]
    B --> D["Shaded JAR"]
    C --> E["BOOT-INF/classes + nested BOOT-INF/lib"]
    D --> F["Classes/resources trên Java classpath"]
    E --> G["Thường chạy với java -jar"]
    F --> H["Dùng cho Lambda Java handler"]
~~~

**Build success chưa phải deploy success.** Một JAR có thể chứa đủ mã nghiệp vụ nhưng không chứa được lớp **FunctionInvoker** ở nơi Lambda classloader mong đợi; hoặc chứa các lớp nhưng mất metadata Spring khi shade.

Nếu deploy bằng **Lambda container image**, cách tạo image/entrypoint riêng có thể thay thế hướng shaded JAR ở đây. Không dùng một hướng đóng gói cho mọi loại Lambda deployment.

## 3. Cấu trúc dự án mẫu

Giả sử dự án Maven có cấu trúc:

~~~text
quote-lambda/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/example/lambda/
│   │   │   └── QuoteLambdaApplication.java
│   │   └── resources/
│   │       └── application.yml
│   └── test/java/example/lambda/
│       └── QuoteLambdaApplicationTest.java
└── target/
    ├── quote-lambda-1.0.0.jar
    └── quote-lambda-1.0.0-aws.jar
~~~

Các tên ở **target** chỉ là minh họa sau build. Đuôi **-aws.jar** đến từ classifier cấu hình trong Maven Shade Plugin, không phải tên bắt buộc của Spring Cloud Function.

Cần giữ tách biệt:

1. **Source code** định nghĩa Spring Boot application và các bean chức năng.
2. **Build configuration** quyết định dependency và hình thức JAR.
3. **Runtime configuration** trên AWS quyết định handler, main class, function definition, Java runtime và event source.

## 4. Ví dụ lớp ứng dụng Spring Boot

Tệp **src/main/java/example/lambda/QuoteLambdaApplication.java**:

~~~java
package example.lambda;

import java.math.BigDecimal;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class QuoteLambdaApplication {

    public static void main(String[] args) {
        SpringApplication.run(QuoteLambdaApplication.class, args);
    }

    public record QuoteRequest(
        String orderId,
        int quantity,
        BigDecimal unitPrice
    ) {}

    public record QuoteResponse(
        String orderId,
        BigDecimal subtotal
    ) {}

    @Bean("calculateQuote")
    Function<QuoteRequest, QuoteResponse> calculateQuote() {
        return request -> {
            if (request == null
                    || request.orderId() == null
                    || request.orderId().isBlank()
                    || request.quantity() <= 0
                    || request.unitPrice() == null
                    || request.unitPrice().signum() < 0) {
                throw new IllegalArgumentException(
                    "Invalid quote request");
            }

            BigDecimal subtotal = request.unitPrice().multiply(
                BigDecimal.valueOf(request.quantity()));

            return new QuoteResponse(request.orderId(), subtotal);
        };
    }
}
~~~

Hàm **calculateQuote** không import API Lambda, AWS SDK hay Spring HTTP request. Nó giữ hợp đồng **QuoteRequest → QuoteResponse**, nên có thể được gọi trực tiếp trong unit test hoặc qua FunctionCatalog.

Ví dụ input cho **direct Lambda invocation**:

~~~json
{
  "orderId": "ORD-101",
  "quantity": 2,
  "unitPrice": 85000
}
~~~

Ví dụ output:

~~~json
{
  "orderId": "ORD-101",
  "subtotal": 170000
}
~~~

**Lưu ý nghiệp vụ:** đơn giá được truyền vào để minh họa kiểu dữ liệu. Hệ thống bán hàng thực tế cần xác minh giá từ nguồn đáng tin cậy, đồng thời quy định tiền tệ và làm tròn.

## 5. Adapter tìm lớp ứng dụng Spring như thế nào?

Để chạy mã trên, **FunctionInvoker** cần tìm được lớp khởi tạo Spring context. Có hai cơ chế quan trọng cần hiểu:

- **Start-Class** trong **META-INF/MANIFEST.MF** do công cụ đóng gói/Boot cung cấp ở một số cách build.
- **MAIN_CLASS** được cấu hình tường minh trong môi trường thực thi, trỏ đến fully qualified class name của ứng dụng.

Ví dụ manifest của một Spring Boot executable JAR:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: example.lambda.QuoteLambdaApplication
~~~

**Main-Class** trong executable JAR có thể là lớp Boot launcher. Đây không phải điều đồng nghĩa với **lớp ứng dụng**. Chính **Start-Class** mô tả lớp cần chạy bên trong Boot; tên launcher thay đổi giữa các thế hệ Boot.

Ví dụ cấu hình AWS Lambda environment:

~~~text
MAIN_CLASS=example.lambda.QuoteLambdaApplication
~~~

Tên này là **class thật** trong mã Java, không phải tên **@Bean**, tên Lambda function, tên Java file không có package hoặc tên handler.

~~~text
ĐÚNG: MAIN_CLASS=example.lambda.QuoteLambdaApplication

SAI:  MAIN_CLASS=calculateQuote
SAI:  MAIN_CLASS=FunctionInvoker
SAI:  MAIN_CLASS=QuoteLambdaApplication::main
~~~

Nếu cả manifest và environment đều xác định lớp ứng dụng, nên giữ các giá trị thống nhất. Cách adapter ưu tiên hoặc phát hiện nguồn metadata phải được kiểm tra theo **phiên bản spring-cloud-function-adapter-aws** đang sử dụng, không suy đoán một quy tắc tuyệt đối cho mọi release.

### Cách kiểm tra class có trong JAR

Lớp trên tương ứng đường dẫn:

~~~text
example/lambda/QuoteLambdaApplication.class
~~~

Vì vậy, một câu lệnh kiểm tra artifact:

~~~bash
jar tf target/quote-lambda-1.0.0-aws.jar |
  grep 'example/lambda/QuoteLambdaApplication.class'
~~~

Nếu không thấy class này trong artifact thực tế, việc đặt **MAIN_CLASS** đúng vẫn không giải quyết được lỗi **ClassNotFoundException**.

## 6. Vị trí package và component scanning

Khi Spring khởi tạo **QuoteLambdaApplication**, **@SpringBootApplication** thông thường quét component dưới package chứa lớp ứng dụng.

Ví dụ:

~~~text
example.lambda.QuoteLambdaApplication
example.lambda.config.QuoteConfiguration
example.lambda.service.PriceService
~~~

Trong bố cục trên, configuration/service ở package con có thể được Spring phát hiện theo cơ chế scanning thông thường.

Ngược lại, nếu bean chức năng nằm ở **com.other.functions** nhưng application ở **example.lambda**, Spring sẽ không tự quét qua mọi package trong classpath. Cần sử dụng **@Import**, cấu hình scan chủ động hoặc đăng ký bean đúng nơi.

Ví dụ một lớp cấu hình bổ sung:

~~~java
package example.lambda.config;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TextFunctions {

    @Bean("normalizeText")
    Function<String, String> normalizeText() {
        return value -> value.trim()
            .toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Nếu **QuoteLambdaApplication** nằm ở **example.lambda**, lớp **TextFunctions** ở package con sẽ có thể được phát hiện. Không cần đổi **MAIN_CLASS** thành **TextFunctions** vì đó là lớp cấu hình, không phải entrypoint ứng dụng.

## 7. Dependency nào cần cho JAR Lambda?

Maven cần **spring-cloud-function-adapter-aws**:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-function-adapter-aws</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Phiên bản Boot và Spring Cloud Function phải được quản lý đồng bộ bằng **parent/BOM hoặc dependencyManagement**. Ví dụ phần Spring Cloud BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Thuộc tính **spring-cloud.version** phải được khai báo bằng một release train thật phù hợp với Boot version của dự án. Đây là **đoạn POM**, không phải file pom.xml đầy đủ có thể chạy nguyên xi.

Phân biệt hai loại:

| Loại | Ví dụ | Công dụng |
| --- | --- | --- |
| **Runtime dependency** | **spring-cloud-function-adapter-aws** | Tạo handler và tích hợp FunctionCatalog trên Lambda |
| **Build plugin** | **maven-shade-plugin** | Tạo shaded JAR chứa lớp và dependency |
| **Core/application dependency** | **spring-boot-starter** | Tạo application context |
| **Dependency tùy chọn** | JDBC, AWS SDK, Stream binder | Chỉ có khi logic thực sự sử dụng |

Không đặt **spring-cloud-function-adapter-aws** trong mục Maven **plugins**. Tương tự, không thêm Spring MVC hoặc Kafka binder chỉ vì Lambda là môi trường serverless.

## 8. Maven Shade Plugin: tạo artifact triển khai

Mục tiêu của **Maven Shade Plugin** là đóng gói lớp ứng dụng, dependency và resources vào artifact mà AWS Lambda Java runtime có thể nạp.

Một phần cấu hình minh họa:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-shade-plugin</artifactId>
            <version>3.6.0</version>
            <executions>
                <execution>
                    <id>lambda-jar</id>
                    <phase>package</phase>
                    <goals>
                        <goal>shade</goal>
                    </goals>
                    <configuration>
                        <createDependencyReducedPom>false</createDependencyReducedPom>
                        <shadedArtifactAttached>true</shadedArtifactAttached>
                        <shadedClassifierName>aws</shadedClassifierName>
                        <transformers>
                            <transformer
                              implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>

                            <transformer
                              implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
                                <resource>META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports</resource>
                            </transformer>

                            <transformer
                              implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
                                <resource>META-INF/spring.handlers</resource>
                            </transformer>

                            <transformer
                              implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
                                <resource>META-INF/spring.schemas</resource>
                            </transformer>

                            <transformer
                              implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                <manifestEntries>
                                    <Start-Class>example.lambda.QuoteLambdaApplication</Start-Class>
                                </manifestEntries>
                            </transformer>
                        </transformers>
                        <filters>
                            <filter>
                                <artifact>*:*</artifact>
                                <excludes>
                                    <exclude>META-INF/*.SF</exclude>
                                    <exclude>META-INF/*.DSA</exclude>
                                    <exclude>META-INF/*.RSA</exclude>
                                </excludes>
                            </filter>
                        </filters>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

**Đây không phải POM deploy hoàn chỉnh cho mọi phiên bản Spring.** Cần bổ sung cơ chế merge đúng cho **META-INF/spring.factories** (dạng properties, có thể nhiều giá trị trên cùng key) và những Spring resources khác mà dependency tree sử dụng. Trong tài liệu Spring Cloud Function, các transformer chuyên biệt được dùng để tránh mất metadata khi shade. Không đơn giản dùng AppendingTransformer cho mọi resource dạng properties.

Cũng cần kiểm soát **spring-boot-maven-plugin repackage** nếu dự án khai báo plugin đó: Shade phải nhận đúng artifact đầu vào, không vô tình gom một Boot nested-JAR không phù hợp. Tốt nhất dùng mẫu Lambda packaging chính thức của **cùng release Spring Cloud Function** và kiểm thử artifact cuối.

### Vì sao đặt classifier aws?

Với artifactId **quote-lambda** và version **1.0.0**, cấu hình trên có thể tạo:

~~~text
target/quote-lambda-1.0.0.jar
target/quote-lambda-1.0.0-aws.jar
~~~

**-aws.jar** giúp phân biệt shaded artifact với JAR khác. Nhưng tên thực phụ thuộc project build; trước khi upload luôn xác minh đường dẫn file thực.

## 9. Metadata Spring quan trọng thế nào?

Những resource phổ biến trong Spring ecosystem:

~~~text
META-INF/MANIFEST.MF
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring.handlers
META-INF/spring.schemas
META-INF/services/...
~~~

Không phải dự án nào cũng cần tất cả. Những resource xuất hiện thực tế phụ thuộc Spring Boot, Spring Cloud và các thư viện đi kèm.

| Resource | Nội dung | Điều cần bảo toàn |
| --- | --- | --- |
| **META-INF/services/** | Danh sách service provider | Merge danh sách |
| **AutoConfiguration.imports** | Tên class auto-configuration | Giữ tất cả mục cần thiết |
| **spring.factories** | Dạng properties, nhiều module cùng khai báo | Merge đúng khóa và giá trị |
| **spring.handlers/schemas** | Metadata cấu hình XML | Giữ ánh xạ từ các dependency cần dùng |
| **MANIFEST.MF** | Metadata artifact như **Start-Class** | Ghi thông tin main class nhất quán |

Một trường hợp rất dễ gây nhầm: JAR có **FunctionInvoker.class** và **QuoteLambdaApplication.class**, nhưng **Spring context vẫn khởi động lỗi** vì shade chỉ giữ một file **spring.factories** thay vì merge dữ liệu nhiều thư viện.

Vì thế, **kiểm tra file .class chỉ là điều kiện cần**. Phải bảo toàn resource metadata, test khởi động context và nếu có thể thực hiện một Lambda invocation với chính artifact deploy.

## 10. Kiểm tra nội dung JAR sau khi build

Các lệnh sau dành cho dự án Maven đã cấu hình hoàn chỉnh:

~~~bash
mvn clean package
ls -lh target/*.jar

jar tf target/quote-lambda-1.0.0-aws.jar |
  grep 'org/springframework/cloud/function/adapter/aws/FunctionInvoker.class'

jar tf target/quote-lambda-1.0.0-aws.jar |
  grep 'example/lambda/QuoteLambdaApplication.class'

jar tf target/quote-lambda-1.0.0-aws.jar |
  grep 'META-INF/spring/'
~~~

Đường dẫn **target/quote-lambda-1.0.0-aws.jar** là minh họa. Trên PowerShell, thay grep bằng:

~~~powershell
jar tf target/quote-lambda-1.0.0-aws.jar |
  Select-String 'FunctionInvoker.class|QuoteLambdaApplication.class'
~~~

Để xem manifest trên hệ thống có unzip:

~~~bash
unzip -p target/quote-lambda-1.0.0-aws.jar META-INF/MANIFEST.MF
~~~

Tìm:

~~~text
Start-Class: example.lambda.QuoteLambdaApplication
~~~

Nếu shaded JAR không có **Start-Class**, có thể đặt **MAIN_CLASS** tường minh theo cơ chế adapter hỗ trợ. Nhưng nếu JAR hoàn toàn thiếu lớp main thì chỉ đặt biến môi trường không đủ.

### Kiểm tra phiên bản dependency

~~~bash
mvn dependency:tree -Dincludes=org.springframework.cloud
mvn dependency:tree -Dincludes=org.springframework.boot
~~~

Nếu thấy nhiều version bất ngờ, hãy đối chiếu BOM và plugin với dependency tree. Không xóa bừa dependency chỉ để hết một exception ở runtime.

## 11. Gradle: tạo JAR cho Lambda bằng Shadow

Nếu dự án dùng Gradle, hướng tương ứng là dùng **Shadow Plugin** tạo uber JAR. Ví dụ **Groovy DSL** mô tả những thao tác chính:

~~~groovy
// Giả sử plugin Shadow đã được khai báo phù hợp với Gradle project.
tasks.named("shadowJar") {
    archiveClassifier.set("aws")

    mergeServiceFiles()
    append("META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports")
    append("META-INF/spring.handlers")
    append("META-INF/spring.schemas")

    manifest {
        attributes(
            "Start-Class": "example.lambda.QuoteLambdaApplication"
        )
    }
}
~~~

**Không coi snippet trên là build.gradle hoàn chỉnh**. Phải có plugin, dependency, Java toolchain, task wiring và đặc biệt một transformer merge **spring.factories** theo đúng định dạng properties. Cú pháp API của plugin cũng có thể thay đổi theo phiên bản.

Để tránh conflict giữa Spring Boot **bootJar** và Shadow **shadowJar**, cần xác định rõ **artifact nào được giao cho AWS**. Ví dụ hai file khác nhau có thể được tạo:

~~~text
build/libs/quote-lambda-1.0.0.jar
build/libs/quote-lambda-1.0.0-aws.jar
~~~

Hãy kiểm tra lớp handler và metadata bên trong file cuối, không chỉ dựa vào hậu tố tên.

## 12. Cấu hình Lambda handler và main class

Sau khi có shaded JAR, cấu hình Lambda tương ứng:

~~~text
Handler:
  org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest

Environment:
  MAIN_CLASS=example.lambda.QuoteLambdaApplication
  spring_cloud_function_definition=calculateQuote
~~~

Một số cách cấu hình handler theo phiên bản adapter hoặc công cụ deploy có thể dùng **org.springframework.cloud.function.adapter.aws.FunctionInvoker** (tên lớp) thay vì cú pháp **::handleRequest**. Kiểm tra chính xác handler mà phiên bản adapter/runtime hỗ trợ; không đặt tên bean nghiệp vụ vào trường này.

Biến **spring_cloud_function_definition** chọn bean trong **FunctionCatalog**. Nếu có nhiều Function bean, đây là cách rõ ràng để tránh ứng dụng chọn không đúng hàm.

### AWS SAM ví dụ

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  QuoteFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java17
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
      CodeUri: target/quote-lambda-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.QuoteLambdaApplication
          spring_cloud_function_definition: calculateQuote
~~~

**CodeUri phải trỏ tới JAR thực có sau build**. Runtime Java 17 chỉ là lựa chọn minh họa, cần kiểm tra phiên bản Java AWS hỗ trợ và cấu hình compiler/release tương ứng. Memory/timeout cũng là tham số demo, không phải cấu hình tối ưu cố định.

Với AWS Console, AWS CLI, Terraform hoặc CloudFormation, ba ý nghĩa vẫn giữ nguyên: handler của adapter, main class của Spring, bean được chọn trong FunctionCatalog.

## 13. Cách kiểm thử từng lớp trách nhiệm

### 13.1. Unit test nghiệp vụ không cần AWS

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class QuoteLambdaApplicationTest {

    private final QuoteLambdaApplication app =
        new QuoteLambdaApplication();

    @Test
    void calculatesSubtotal() {
        var result = app.calculateQuote().apply(
            new QuoteLambdaApplication.QuoteRequest(
                "ORD-101", 2, new BigDecimal("85000")
            )
        );

        assertEquals(
            new BigDecimal("170000"), result.subtotal());
    }

    @Test
    void rejectsInvalidQuantity() {
        assertThrows(IllegalArgumentException.class,
            () -> app.calculateQuote().apply(
                new QuoteLambdaApplication.QuoteRequest(
                    "ORD-101", 0, new BigDecimal("85000")
                )
            ));
    }
}
~~~

Unit test này không kiểm tra FunctionInvoker, JAR layout hay main-class discovery.

### 13.2. Integration test của FunctionCatalog

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.math.BigDecimal;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = QuoteLambdaApplication.class)
class QuoteCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void findsBeanByName() {
        Function<QuoteLambdaApplication.QuoteRequest,
                QuoteLambdaApplication.QuoteResponse> fn =
            catalog.lookup("calculateQuote");

        assertNotNull(fn);

        var quote = fn.apply(
            new QuoteLambdaApplication.QuoteRequest(
                "ORD-101", 2, new BigDecimal("85000")
            )
        );

        assertEquals(
            new BigDecimal("170000"), quote.subtotal());
    }
}
~~~

Test này chứng minh Spring context có thể tạo và catalog tra cứu bean. Nhưng cần kiểm tra **đúng shaded JAR cuối** rồi gọi thử Lambda để phát hiện lỗi handler/classpath hoặc conversion trong runtime.

### 13.3. Direct invocation sau deploy

Ví dụ event trực tiếp:

~~~json
{
  "orderId": "ORD-101",
  "quantity": 2,
  "unitPrice": 85000
}
~~~

Lệnh AWS CLI trên shell hỗ trợ cú pháp nháy đơn:

~~~bash
aws lambda invoke \
  --function-name quote-lambda \
  --cli-binary-format raw-in-base64-out \
  --payload '{"orderId":"ORD-101","quantity":2,"unitPrice":85000}' \
  response.json

cat response.json
~~~

**quote-lambda** là tên hàm AWS ví dụ, không phải tên bean **calculateQuote**. Cần kiểm tra metadata trả về, nội dung response và CloudWatch logs để phát hiện lỗi function dù lệnh CLI gửi request thành công.

**Direct invoke không tương đương API Gateway/SQS/S3 trigger**: mỗi nguồn có event envelope, batch semantics hoặc error mapping riêng. Nếu Lambda nhận event có trường **body** hoặc **Records**, phải chọn kiểu đầu vào/bộ chuyển đổi đúng; đổi **MAIN_CLASS** không giải quyết vấn đề schema.

## 14. Bảng chẩn đoán lỗi đóng gói và lớp ứng dụng

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| **ClassNotFoundException: FunctionInvoker** | Chưa include adapter hoặc upload nhầm JAR | **jar tf**, dependency tree, CodeUri |
| **ClassNotFoundException: QuoteLambdaApplication** | Sai class path, package đổi hoặc JAR thiếu class | **jar tf** theo tên class đầy đủ |
| Không tìm được main class | Thiếu **Start-Class** và **MAIN_CLASS** | Manifest, env var, adapter version |
| Spring context không tìm thấy bean | Package scan/definition sai | **@Bean**, FunctionCatalog test, config |
| Build pass nhưng Lambda lỗi auto-configuration | Merge metadata Spring thiếu | **spring.factories**, **AutoConfiguration.imports**, service resources |
| **java -jar** chạy được nhưng Lambda không nạp handler | Boot executable JAR không đúng layout | Kiểm tra **BOOT-INF** và shaded JAR |
| **NoSuchMethodError** hoặc lỗi linkage | Boot/Cloud/adapter lệch version | BOM và dependency tree |
| **UnsupportedClassVersionError** | Build bytecode cao hơn runtime Java AWS | Compiler release, Runtime |
| Không deserialize được QuoteRequest | JSON/schema/generic type không khớp | Chữ ký Function, input event thật |
| Kết quả khác với direct invoke | API Gateway/SQS event envelope khác | Điều hợp theo trigger |
| **MAIN_CLASS** đặt đúng nhưng vẫn lỗi | Main class không có trong JAR hoặc metadata xung đột | So sánh package/class, artifact, manifest |
| Cold start quá lâu | Context lớn, quá nhiều dependency hoặc I/O khởi tạo | Đo duration, rà dependency, startup logs |

Một quy trình chẩn đoán hiệu quả là kiểm tra theo thứ tự: **(1) handler có được nạp không**, **(2) main class/context khởi tạo được không**, **(3) catalog có tìm được bean không**, **(4) event có chuyển đổi đúng không**. Không thay đổi ngẫu nhiên nhiều cấu hình cùng lúc.

## 15. Java runtime, cold start và trạng thái

Build phải dùng Java target phù hợp Lambda runtime. Ví dụ Maven:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Ví dụ Gradle toolchain:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Cần kiểm tra cả version Spring Boot, Spring Cloud Function và dependency transitives có tương thích Java runtime hay không.

Khi Lambda khởi tạo execution environment mới, quá trình nạp JAR, tạo application context và khởi tạo dependency có thể làm tăng **cold-start latency**. Một instance ấm có thể tái sử dụng singleton Function bean; nhưng các instance không chia sẻ bộ nhớ và Lambda có thể tạo mới environment bất cứ lúc nào.

Vì vậy:

- Không dùng field singleton để lưu trạng thái nghiệp vụ bền vững.
- Không dựa vào việc cùng một Lambda instance luôn xử lý tất cả event.
- Đo cold start thật trước khi tối ưu dependency và auto-configuration.
- Không cắt bỏ metadata Spring hoặc library cần thiết chỉ để giảm kích thước JAR.
- Với Consumer có tác dụng phụ, xử lý retry và idempotency ở mức dữ liệu/hạ tầng, không dựa vào classloader hoặc singleton.

## 16. Checklist trước khi triển khai

| Kiểm tra | Dấu hiệu đạt |
| --- | --- |
| **Source** | Có **@SpringBootApplication** với package/class rõ ràng |
| **Bean** | Có **Function/Consumer/Supplier** đúng kiểu, đúng tên |
| **Adapter** | Dependency **spring-cloud-function-adapter-aws** được resolve |
| **Compatibility** | Boot/Cloud/Java tương thích và version được khóa |
| **Artifact** | Có **shaded JAR** thật, không upload nhầm Boot JAR |
| **Handler class** | **FunctionInvoker.class** nằm trong deploy JAR |
| **Application class** | **QuoteLambdaApplication.class** nằm trong deploy JAR |
| **Metadata** | Resource Spring được merge đúng và context khởi tạo |
| **Discovery** | **Start-Class** hoặc **MAIN_CLASS** hợp lệ |
| **Function selection** | **spring_cloud_function_definition=calculateQuote** |
| **AWS configuration** | Handler, CodeUri, Runtime, memory, timeout và IAM đúng |
| **Invocation** | JSON được chuyển thành DTO, output đúng, log không có lỗi |

Nếu một mục chưa xác minh, chưa nên kết luận artifact đã sẵn sàng chỉ vì Maven/Gradle trả exit code 0.

## 17. Bài tập vận dụng

**Bài tập 1 — Ba tên.** Ứng dụng có **@SpringBootApplication com.shop.QuoteApplication**, bean **@Bean("quoteOrder")**. Viết giá trị cho Lambda handler, **MAIN_CLASS** và **spring_cloud_function_definition**. Nêu lỗi nếu dùng tên bean làm handler.

**Bài tập 2 — JAR khác nhau.** Một build sinh **service.jar** có **BOOT-INF/lib** và **service-aws.jar** có lớp ở classpath. Giải thích artifact nào phù hợp cho đường deploy Java Lambda JAR và những mục cần kiểm tra trong manifest.

**Bài tập 3 — Thiếu Start-Class.** Shaded JAR chứa **com.shop.QuoteApplication.class** nhưng không có **Start-Class**. Hãy đề xuất biến môi trường tương ứng và cách kiểm chứng Lambda khởi tạo được Spring context.

**Bài tập 4 — Metadata.** Một shade task chỉ giữ một **spring.factories** từ nhiều dependency. Mô tả triệu chứng có thể gặp và khác biệt giữa merge file properties với nối file danh sách class.

**Bài tập 5 — Đổi package.** Refactor **example.lambda.QuoteLambdaApplication** sang **example.serverless.QuoteLambdaApplication**. Liệt kê vị trí cần cập nhật: manifest, **MAIN_CLASS**, source package, scan, SAM và test.

**Bài tập 6 — Nhiều Function.** Đăng ký thêm **normalizeSku** bên cạnh **calculateQuote**. Mô tả cách dùng cùng shaded JAR để triển khai hai Lambda nhưng cấu hình definition khác nhau.

**Bài tập 7 — Lỗi ClassNotFound.** Unit test và **@SpringBootTest** pass, nhưng Lambda báo không tìm được **FunctionInvoker**. Lập quy trình điều tra dependency, artifact, handler và CodeUri theo thứ tự.

**Bài tập 8 — Event envelope.** Direct invoke với **QuoteRequest** thành công nhưng trigger API Gateway gửi một object có **body**. Đề xuất giải pháp ánh xạ event sang DTO thay vì sửa main class hoặc handler.

### Ghi nhớ

- **AWS Lambda handler**, **Spring Boot main class** và **Function bean** là ba định danh riêng biệt.
- Với **Java JAR + spring-cloud-function-adapter-aws**, cần **shaded JAR** có handler, application classes, dependencies và Spring metadata phù hợp; executable Boot JAR không mặc nhiên dùng được.
- **Start-Class** trong manifest hoặc **MAIN_CLASS** theo cơ chế adapter giúp xác định lớp ứng dụng; **spring_cloud_function_definition** chọn bean nghiệp vụ.
- Maven Shade/Gradle Shadow phải merge đúng **META-INF**. Chỉ kiểm tra file .class là chưa đủ.
- Unit test xác minh logic, Spring integration test xác minh context/catalog; **kiểm tra artifact và gọi thử Lambda** xác nhận đường deploy thực tế.

### Tài liệu tham khảo

- [Spring Cloud Function — AWS Lambda](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): handler, main class, shaded JAR và integration.
- [Spring Cloud Function — Reference](https://docs.spring.io/spring-cloud-function/reference/): FunctionCatalog, model và composition.
- [AWS Lambda — Java deployment packages](https://docs.aws.amazon.com/lambda/latest/dg/java-package.html): artifact và cách deploy Java.
- [AWS Lambda — Java handler](https://docs.aws.amazon.com/lambda/latest/dg/java-handler.html): cách runtime gọi handler.
