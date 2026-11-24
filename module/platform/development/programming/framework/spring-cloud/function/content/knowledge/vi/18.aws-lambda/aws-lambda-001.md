# Phụ thuộc spring-cloud-function-adapter-aws

**spring-cloud-function-adapter-aws** là thư viện điều hợp giúp một ứng dụng **Spring Cloud Function** chạy trên **AWS Lambda** mà không cần đưa API Lambda vào từng hàm nghiệp vụ. Khi ứng dụng đã khai báo các bean **Supplier<T>**, **Function<T, R>** hoặc **Consumer<T>**, adapter cung cấp điểm vào **FunctionInvoker** để nhận lời gọi của Lambda, khởi tạo Spring context, tìm hàm trong **FunctionCatalog**, chuyển đổi dữ liệu và trả kết quả theo khả năng của runtime.

Bài thuộc chương **AWS Lambda**, tập trung vào **khai báo đúng dependency**, quản lý phiên bản Spring Boot/Spring Cloud, phân biệt adapter với các thư viện web và AWS SDK, hiểu vai trò của handler, đóng gói JAR phù hợp với Lambda, xác minh sau build và chẩn đoán lỗi. Các bước triển khai được minh họa trên Java 17+; phải chọn phiên bản Java và Spring tương thích với runtime thực tế.

## 1. Vì sao cần một AWS Lambda adapter?

Trong ứng dụng Java thông thường, người gọi có thể lấy bean **Function** và gọi **apply(input)**. Trong AWS Lambda, nền tảng không tìm kiếm Spring bean. Nó gọi **handler** được khai báo trong cấu hình Lambda và chuyển sự kiện đến handler đó.

Nếu không có adapter, mỗi ứng dụng sẽ cần tự xử lý các bước như khởi tạo Spring application context, tra cứu bean, deserialize event, gọi hàm và serialize kết quả.

~~~mermaid
flowchart LR
    A["AWS Lambda invocation"] --> B["FunctionInvoker"]
    B --> C["Spring ApplicationContext"]
    C --> D["FunctionCatalog"]
    D --> E["Function<T, R>"]
    E --> F["Result R"]
    F --> B
    B --> G["Lambda response"]
~~~

**spring-cloud-function-adapter-aws** cung cấp cơ chế tích hợp cho luồng trên. Phần nghiệp vụ vẫn có thể được viết độc lập:

~~~java
Function<String, String> normalize =
    text -> text.trim().toUpperCase(java.util.Locale.ROOT);
~~~

Dù dùng HTTP, Spring Cloud Stream hay AWS Lambda, hàm vẫn biến đổi **String → String**. Điểm khác nhau nằm ở **đường nhận sự kiện, chuyển đổi dữ liệu, cấu hình khởi chạy và cơ chế trả kết quả**.

### Phân biệt hai lớp trách nhiệm

| Thành phần | Vai trò |
| --- | --- |
| **Spring Cloud Function Core / Context** | Nhận diện bean chức năng, cung cấp **FunctionCatalog**, composition, conversion và các cơ chế liên quan |
| **spring-cloud-function-adapter-aws** | Tích hợp Spring Cloud Function với mô hình handler/invocation của AWS Lambda |
| **spring-cloud-function-web** | Điều hợp HTTP cho ứng dụng Spring Cloud Function ở môi trường web |
| **Spring Cloud Stream + binder** | Tích hợp luồng message với Kafka, RabbitMQ hoặc hệ thống tương ứng |
| **AWS SDK / aws-lambda-java-events** | Gọi dịch vụ AWS hoặc dùng các lớp sự kiện AWS cụ thể khi ứng dụng cần |

**Cài adapter không đồng nghĩa bật HTTP server** và cũng không tự thêm Kafka/SQS event source mapping. Handler Lambda và các trigger được thiết lập ở lớp cấu hình AWS.

## 2. Tọa độ Maven chính xác của adapter

Dependency cần đưa vào dự án:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-aws</artifactId>
</dependency>
~~~

Tọa độ đầy đủ có dạng:

~~~text
org.springframework.cloud:spring-cloud-function-adapter-aws:<phiên bản>
~~~

Đây là **dependency của ứng dụng**, không phải Maven build plugin. Không viết:

~~~xml
<!-- Sai: adapter không phải plugin dùng để đóng gói -->
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-aws</artifactId>
</plugin>
~~~

Tên artifact cần chính xác. **spring-cloud-starter-function-web** phục vụ đường HTTP, còn **spring-cloud-function-adapter-aws** phục vụ handler của Lambda; hai dependency không thể thay thế cho nhau.

### Dependency nào là bắt buộc, dependency nào tùy chọn?

Đối với một hàm Spring Boot chạy trên Lambda theo mô hình chức năng, thường cần:

- **Spring Boot** để tạo application context và quản lý bean.
- **spring-cloud-function-adapter-aws** để kết nối runtime Lambda với Spring Cloud Function.
- **Spring Cloud Function context/core** đi qua dependency tree tương ứng; có thể khai báo **spring-cloud-function-context** tường minh nếu muốn rõ ý định và mã nguồn import **FunctionCatalog**.
- **Thư viện phục vụ nghiệp vụ** như JDBC, JSON, HTTP client hoặc AWS SDK chỉ khi code thực sự dùng.
- **Công cụ tạo deployable JAR** như Maven Shade Plugin hoặc Gradle Shadow Plugin ở lớp **build**, không phải một dependency runtime.

Không nên thêm toàn bộ Spring Cloud Stream, WebFlux, Spring MVC hoặc AWS SDK vào một Lambda chỉ vì tên thư viện có chữ “cloud”. Dependency thừa có thể làm JAR lớn hơn, tăng số lớp cần nạp và tạo bề mặt bảo trì không cần thiết.

## 3. Quản lý phiên bản bằng BOM thay vì đoán số version

Spring Cloud Function, Spring Boot và các module Spring Cloud phải thuộc các phiên bản **tương thích**. Một lỗi phổ biến là dùng phiên bản mới nhất của adapter với Spring Boot quá cũ, hoặc để Maven kéo vào nhiều phiên bản **spring-cloud-function-context** khác nhau.

**BOM (Bill of Materials)** giúp quản lý phiên bản thống nhất. Trong dự án Maven đã dùng **Spring Boot parent** hoặc có cơ chế quản lý Boot tương đương, có thể khai báo Spring Cloud BOM:

~~~xml
<properties>
    <!-- Khai báo giá trị release train phù hợp với Spring Boot của dự án. -->
    <spring-cloud.version>YOUR_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
</properties>

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

**Đây là đoạn cấu hình minh họa**, không phải **pom.xml** hoàn chỉnh: phải thay **YOUR_COMPATIBLE_RELEASE_TRAIN** bằng một phiên bản thật được xác nhận tương thích với Spring Boot và thiết lập parent/plugin của dự án. Không sao chép nguyên placeholder rồi kỳ vọng Maven resolve thành công.

Một số điểm cần kiểm tra:

1. **Spring Boot** cung cấp phiên bản dependency Boot và cơ chế khởi động.
2. **Spring Cloud BOM** quản lý các module tương thích trong release train.
3. Nếu BOM của dự án chưa quản lý phiên bản adapter mong muốn, dùng cơ chế quản lý dependency chuyên biệt của Spring Cloud Function theo hướng dẫn phiên bản đang chọn, không đặt version tùy ý trên từng artifact.
4. **Java language level** khi compile phải phù hợp với runtime Lambda đã chọn.
5. Một dependency transitive đang kéo phiên bản khác có thể cần được xử lý bằng **dependencyManagement** hoặc loại trừ có cơ sở; không nên loại trừ bừa để hết lỗi build.

**Không có một cặp version Spring Boot/Spring Cloud đúng cho mọi thời điểm.** Hãy khóa phiên bản trong build và xác minh theo tài liệu release train tương ứng, thay vì ghép những bản mới nhất độc lập.

## 4. Khai báo tương đương trong Gradle

Ví dụ **build.gradle** dùng Gradle Groovy DSL với BOM:

~~~groovy
dependencies {
    implementation platform(
        "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    )

    implementation "org.springframework.boot:spring-boot-starter"
    implementation "org.springframework.cloud:spring-cloud-function-adapter-aws"

    testImplementation "org.springframework.boot:spring-boot-starter-test"
}

tasks.named("test") {
    useJUnitPlatform()
}
~~~

Biến **springCloudVersion** cần được khai báo trong Gradle project hoặc **gradle.properties**, và dự án cần cấu hình các plugin Java/Spring Boot cùng repository như Maven Central. Đoạn này mô tả **dependency và test task**, chưa cấu hình **Shadow JAR** để deploy.

Dùng **implementation** thay cho cấu hình **compile** đã bị loại bỏ trong Gradle hiện đại. Nếu dự án dùng Kotlin DSL, cú pháp sẽ khác một chút:

~~~kotlin
dependencies {
    implementation(platform(
        "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    ))
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.cloud:spring-cloud-function-adapter-aws")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

**Không chạy đồng thời Maven và Gradle cho cùng một module chỉ để thêm hai khai báo.** Chọn công cụ build mà dự án đang sử dụng.

## 5. Ví dụ ứng dụng: bean Function không import AWS API

Sau khi khai báo dependency, ứng dụng Spring Boot có thể tiếp tục sử dụng mô hình lập trình của Spring Cloud Function.

Tệp **GreetingLambdaApplication.java**:

~~~java
package example.lambda;

import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class GreetingLambdaApplication {

    public static void main(String[] args) {
        SpringApplication.run(GreetingLambdaApplication.class, args);
    }

    public record GreetingRequest(String name) {}

    public record GreetingResponse(String message) {}

    @Bean("greet")
    Function<GreetingRequest, GreetingResponse> greet() {
        return request -> {
            if (request == null
                    || request.name() == null
                    || request.name().isBlank()) {
                throw new IllegalArgumentException(
                    "name must not be blank");
            }

            String name = request.name().trim();

            return new GreetingResponse("Xin chào, " + name);
        };
    }
}
~~~

Lớp trên **không implements RequestHandler**, không có phương thức **handleRequest(...)** và không cần đọc trực tiếp object **Context** của AWS. **@Bean("greet")** khai báo một Function có kiểu rõ ràng; **FunctionInvoker** đảm nhận vai trò handler Lambda.

Khi phần thân sự kiện tương ứng trực tiếp với kiểu **GreetingRequest**, một payload JSON minh họa là:

~~~json
{
  "name": "Lan"
}
~~~

Kết quả nghiệp vụ dự kiến:

~~~json
{
  "message": "Xin chào, Lan"
}
~~~

Kết quả cuối do AWS trả về còn phụ thuộc kiểu invocation và cách adapter serialize. Ví dụ này giả định **gọi trực tiếp Lambda bằng object JSON** có cấu trúc phù hợp; **không** mặc định rằng toàn bộ event của API Gateway hay SQS chỉ có trường **name**.

### Điều gì xảy ra bên trong?

~~~mermaid
sequenceDiagram
    participant AWS as AWS Lambda
    participant Invoker as FunctionInvoker
    participant Spring as Spring Context
    participant Cat as FunctionCatalog
    participant Fn as greet Function

    AWS->>Invoker: invoke JSON event
    Invoker->>Spring: khởi tạo / lấy context
    Spring-->>Invoker: application context
    Invoker->>Cat: lookup("greet")
    Cat-->>Invoker: Function được chọn
    Invoker->>Fn: apply(GreetingRequest)
    Fn-->>Invoker: GreetingResponse
    Invoker-->>AWS: serialized response
~~~

Spring có thể tái sử dụng application context trong một execution environment Lambda đã được khởi tạo. Tuy nhiên, một lần **cold start** có thể tạo context mới, và những instance Lambda khác nhau không chia sẻ trực tiếp singleton bean trong bộ nhớ.

## 6. FunctionInvoker là handler, không phải tên bean nghiệp vụ

Với adapter AWS, điểm vào được Spring Cloud Function khuyến nghị là lớp:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker
~~~

Trong giao diện cấu hình **Java Lambda handler**, cách viết được tài liệu minh họa là:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
~~~

Đây là tên **lớp handler/method của adapter**. Nó khác với **greet**, là tên bean Function được đăng ký trong Spring.

Không cấu hình handler thành:

~~~text
example.lambda.GreetingLambdaApplication::greet
~~~

Phương thức **greet()** trong lớp ứng dụng là phương thức factory có annotation **@Bean**, không phải handler AWS được thiết kế để nhận event và runtime context.

| Giá trị | Ý nghĩa | Vị trí |
| --- | --- | --- |
| **FunctionInvoker::handleRequest** | Điểm vào Lambda của adapter | Cấu hình handler trong AWS |
| **greet** | Bean Function nghiệp vụ | Spring ApplicationContext / FunctionCatalog |
| **spring.cloud.function.definition** | Tên hoặc composition cần gọi | Cấu hình Spring |
| **spring_cloud_function_definition** | Biến môi trường tương ứng dùng trong Lambda | Lambda Environment variables |
| **MAIN_CLASS** | Gợi ý lớp Spring Boot main khi adapter không tìm được | Manifest hoặc cấu hình Lambda |

**Không cần tự viết handler AWS** trong ví dụ này. Chỉ cần handler riêng nếu có yêu cầu tích hợp đặc thù không được adapter chung đáp ứng; khi đó phải tự chịu trách nhiệm phù hợp với event contract của Lambda.

## 7. Chọn bean qua spring.cloud.function.definition

Một ứng dụng có thể có nhiều bean chức năng. Nếu không chỉ định hàm, adapter có thể cần cơ chế định tuyến mặc định; đừng dựa vào việc “Spring sẽ chọn đúng” khi có nhiều lựa chọn.

Ví dụ khai báo thêm bean trong lớp ứng dụng:

~~~java
@Bean("uppercase")
Function<String, String> uppercase() {
    return value -> value.toUpperCase(java.util.Locale.ROOT);
}
~~~

Lúc này ứng dụng có ít nhất **greet** và **uppercase**. Để mỗi Lambda function chọn đúng bean, đặt cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: greet
~~~

Khi khai báo qua **AWS Lambda environment variables**, tên biến tương ứng có thể viết:

~~~text
spring_cloud_function_definition=greet
~~~

AWS không chấp nhận dấu chấm trong tên environment variable. Spring Boot hỗ trợ ánh xạ biến có dấu gạch dưới sang property tương ứng; tài liệu Spring Cloud Function AWS Lambda dùng **spring_cloud_function_definition** làm ví dụ.

Một JAR có thể được triển khai cho **hai Lambda function riêng biệt**, cùng trỏ tới **FunctionInvoker** nhưng dùng hai biến môi trường khác nhau:

~~~text
Lambda "greeting-lambda"
  Handler = FunctionInvoker
  spring_cloud_function_definition = greet

Lambda "uppercase-lambda"
  Handler = FunctionInvoker
  spring_cloud_function_definition = uppercase
~~~

Đối với các hàm có quyền truy cập tài nguyên, mức concurrency, thời gian timeout hoặc nguồn event khác nhau, triển khai thành những Lambda function riêng thường giúp cấu hình IAM và vận hành rõ ràng hơn.

**Composition** cũng có thể được chọn bằng definition, ví dụ **normalize|validate|persist**, miễn mỗi bước có kiểu tương thích và cơ chế tích hợp hỗ trợ đường gọi đó. Tuy nhiên, bài này tập trung vào dependency AWS adapter; định tuyến động trong cùng một Lambda function cần cân nhắc **RoutingFunction**, message headers hoặc callback theo tài liệu riêng.

## 8. Đóng gói đúng quan trọng không kém khai báo dependency

**Có adapter trong pom.xml không có nghĩa JAR tạo ra tự chạy được trên Lambda.** Một ứng dụng Spring Boot thường được đóng gói dưới dạng executable JAR với lớp ứng dụng trong **BOOT-INF/classes** và dependency ở **BOOT-INF/lib**. Đây là cấu trúc phù hợp cho **java -jar**, nhưng không nhất thiết phù hợp cách Lambda Java runtime nạp lớp handler từ một JAR tải lên.

Theo hướng dẫn Spring Cloud Function AWS, để triển khai kiểu **Lambda Java JAR**, thường cần **shaded JAR**: một artifact có classpath thích hợp, bao gồm lớp ứng dụng và các thư viện cần thiết.

~~~text
Maven/Gradle source
  ├── Java classes và resources
  ├── spring-cloud-function-adapter-aws
  ├── Spring context/Boot và dependency nghiệp vụ
  │
  ├── JAR phục vụ chạy local (tùy cấu hình)
  └── Shaded JAR dùng để deploy AWS Lambda
~~~

### Khác biệt giữa các artifact

| Artifact | Cách dùng | Điều cần xác minh |
| --- | --- | --- |
| **JAR thường** | Library hoặc input cho build bước sau | Có đủ class nhưng có thể chưa chứa dependencies |
| **Spring Boot executable JAR** | Chạy **java -jar** | Có cấu trúc nested JAR; không mặc nhiên upload làm Lambda handler JAR |
| **Shaded JAR** | Một JAR có cấu trúc phù hợp cho Java Lambda | Có handler, classes, resources, merged metadata và dependency |
| **Container image** | Triển khai Lambda bằng image | Dùng Dockerfile/base image và handler phù hợp; không giống deploy JAR |
| **Native image/custom runtime** | Thực thi native hoặc runtime tùy biến | Có bootstrap/package và quy tắc khác hoàn toàn |

Chọn **một đường đóng gói đúng với kiểu triển khai**. Đừng đặt một file Spring Boot JAR thông thường làm Lambda artifact chỉ vì đuôi tệp đều là **.jar**.

## 9. Maven Shade Plugin: ghép dependency và Spring metadata

Maven Shade Plugin có thể tạo artifact gắn classifier **aws**. Một cấu hình thực tế phải được đồng bộ với phiên bản Spring Boot/Spring Cloud và build lifecycle.

Ví dụ **phần cấu hình plugin** minh họa ý tưởng:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <!-- Khóa version plugin phù hợp trong build của dự án. -->
    <executions>
        <execution>
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
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

**Đây là một phần cấu hình minh họa, không phải POM triển khai hoàn chỉnh.** Một ứng dụng dùng Spring Boot auto-configuration còn cần xử lý phù hợp cho **META-INF/spring.factories** và các resource metadata khác như **META-INF/spring.components** hoặc metadata auto-configuration của Actuator. Tài liệu chính thức mô tả **PropertiesMergingResourceTransformer** cùng các **AppendingTransformer**; với transformer do Spring Boot cung cấp còn cần cấu hình plugin dependency tương ứng. Cấu hình không đầy đủ có thể tạo JAR build thành công nhưng Spring Boot không tìm thấy auto-configuration khi chạy trên Lambda.

Một số lưu ý thiết yếu:

1. **Giữ metadata Spring:** resource ở **META-INF/** có thể tồn tại trùng tên trong nhiều dependency; không để Shade ghi đè tùy ý những danh sách phải được merge.
2. **Giữ đường tìm main class:** Spring Cloud Function có thể dùng **Start-Class** trong manifest; nếu thiếu, cung cấp **MAIN_CLASS** theo tài liệu adapter.
3. **Điều phối plugin:** nếu dùng cả Spring Boot repackage và Maven Shade, thứ tự và artifact input phải đúng; không tùy tiện shade một BOOT-INF nested JAR rồi coi đó là deployable JAR.
4. **Gắn classifier:** cấu hình **shadedClassifierName=aws** giúp phân biệt với artifact phục vụ mục đích khác.
5. **Khóa plugin version:** kiểm tra tương thích và chọn version cụ thể, không để build phụ thuộc vào thay đổi bất ngờ của công cụ.
6. **Kiểm thử artifact cuối:** tên tệp, manifest, các class và metadata phải được kiểm tra trên chính JAR định upload.

Nếu chưa có quy trình build chuẩn, nên bắt đầu từ **sample AWS Lambda chính thức của Spring Cloud Function** cho phiên bản đã chọn, rồi chỉnh lại source/dependency và kiểm tra artifact. Không nên ghép nhiều cấu hình Maven Shade rời rạc từ các phiên bản Spring khác nhau.

### Lệnh kiểm tra Maven

Trong dự án Maven đã cấu hình đầy đủ:

~~~bash
mvn clean package

# Tìm các JAR đã tạo.
ls -lh target/*.jar

# Kiểm tra một artifact dự kiến deploy.
jar tf target/your-app-aws.jar | grep 'FunctionInvoker.class'
jar tf target/your-app-aws.jar | grep 'GreetingLambdaApplication.class'
jar tf target/your-app-aws.jar | grep 'AutoConfiguration.imports'
~~~

**your-app-aws.jar** là tên mẫu; thay bằng **tệp thật** sau build. Lệnh grep phù hợp shell Unix; trên Windows dùng công cụ tìm chuỗi tương ứng. Việc tìm thấy class chưa đảm bảo ứng dụng khởi tạo thành công, nhưng thiếu handler class chắc chắn là một dấu hiệu đóng gói sai.

Theo dõi **META-INF/MANIFEST.MF**, đặc biệt thuộc tính **Start-Class** hoặc cấu hình **MAIN_CLASS** nếu adapter không tự phát hiện entrypoint.

## 10. Gradle Shadow JAR và resources

Với Gradle, cách tương ứng là dùng **Shadow Plugin** để tạo JAR chứa dependency và các resource cần thiết. Đoạn dưới mô tả **những cấu hình cốt lõi của task**; tên DSL và version plugin phụ thuộc phiên bản Shadow đang sử dụng:

~~~groovy
tasks.named("shadowJar") {
    archiveClassifier = "aws"

    // Merge file đăng ký dịch vụ cho các thư viện hỗ trợ ServiceLoader.
    mergeServiceFiles()

    // Một số metadata Spring cần được nối thay vì ghi đè.
    append("META-INF/spring.handlers")
    append("META-INF/spring.schemas")
    append("META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports")
}
~~~

Cần khai báo plugin Shadow tương thích ở phần **plugins**, và nếu có **spring.factories** thì phải merge các thuộc tính đúng cách; một thao tác nối file văn bản đơn giản không luôn đúng khi các tệp chứa **cùng khóa property**. Hướng dẫn Spring Cloud Function có ví dụ **PropertiesFileTransformer** cho trường hợp này.

**Không coi đoạn Shadow task trên là file Gradle độc lập đã đủ deploy.** Nên dùng cấu hình tham chiếu chính thức với phiên bản plugin tương ứng và kiểm tra rằng task **assemble/package** thực sự tạo JAR theo classifier mong muốn.

### Vì sao cần cẩn thận với metadata?

Spring Boot dùng các resources để phát hiện auto-configuration, service provider hoặc khai báo thành phần khác. Khi các dependency có file metadata trùng tên, thao tác shade/merge không đúng có thể làm mất một phần danh sách lớp cần tải. Kết quả là:

- Build báo thành công nhưng application context không tạo bean.
- FunctionCatalog không tìm được **greet**.
- Converter hoặc serializer thiếu một service provider.
- Lỗi chỉ xảy ra trên Lambda nhưng không xảy ra khi chạy **java -jar** ở local.

Do đó, **đóng gói là một phần của hợp đồng triển khai**, không chỉ là bước nén file.

## 11. MAIN_CLASS, manifest và khởi tạo Spring application

Khi Lambda gọi **FunctionInvoker**, adapter cần biết lớp ứng dụng Spring Boot để tạo context. Tài liệu Spring Cloud Function cho biết adapter thử tìm thông tin **Start-Class** trong JAR manifest. Nếu không có, có thể khai báo **MAIN_CLASS** dưới dạng environment variable hoặc system property.

Ví dụ:

~~~text
MAIN_CLASS=example.lambda.GreetingLambdaApplication
~~~

**MAIN_CLASS** phải là tên lớp đầy đủ (fully qualified class name) của lớp ứng dụng, không phải tên Function bean **greet**.

Sơ đồ định danh:

~~~text
Lambda handler
    org.springframework.cloud.function.adapter.aws.FunctionInvoker

Spring Boot main class
    example.lambda.GreetingLambdaApplication

Spring Function bean
    greet
~~~

Một cấu hình có thể khởi chạy được locally nhưng lỗi trên Lambda nếu main-class discovery phụ thuộc cấu trúc executable JAR đã bị thay đổi khi shade. Đặc biệt, khi tạo JAR thủ công thay vì sử dụng sample đã kiểm thử, nên đặt **MAIN_CLASS** tường minh và kiểm tra log khởi động.

## 12. Ví dụ AWS SAM: dependency, JAR và handler phối hợp

Sau khi build đúng artifact, có thể dùng **AWS SAM** để mô tả Lambda function. Ví dụ **template.yaml** minh họa:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  GreetingFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/your-app-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          spring_cloud_function_definition: greet
          MAIN_CLASS: example.lambda.GreetingLambdaApplication
~~~

Giải thích:

- **Runtime: java21** chỉ là lựa chọn minh họa. Cần compile bằng Java phù hợp và xác minh runtime Java do AWS hỗ trợ tại thời điểm triển khai.
- **Handler** trỏ tới adapter, không trỏ trực tiếp tới phương thức **@Bean greet()**.
- **CodeUri** phải trỏ tới **JAR thực sự được build** và đóng gói đúng. **your-app-aws.jar** không phải tên cố định do framework sinh ra.
- **spring_cloud_function_definition** chọn bean **greet**.
- **MAIN_CLASS** dùng làm gợi ý tìm lớp Spring Boot main; nếu manifest đã đầy đủ thì có thể không cần.
- **MemorySize** và **Timeout** là cấu hình vận hành minh họa, không phải giá trị tối ưu cố định.

Nếu dùng AWS Console thay vì SAM, phần handler theo hướng dẫn của Spring Cloud Function có thể nhập:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
~~~

Đừng trộn lẫn một runtime cấu hình cho Java JAR với quá trình deploy **container image** hoặc **GraalVM native custom runtime**: những đường triển khai đó có cơ chế khởi chạy và packaging riêng.

### Thử sự kiện trong AWS Lambda

Nếu Lambda nhận trực tiếp JSON object dành cho **GreetingRequest**, có thể tạo test event:

~~~json
{
  "name": "Lan"
}
~~~

Kết quả nghiệp vụ là thông điệp chào **Xin chào, Lan**.

**Cảnh báo về trigger:** sự kiện do **API Gateway**, **SQS**, **S3** hoặc **EventBridge** tạo có cấu trúc bao ngoài (event envelope) khác test event trực tiếp. Không được giả định adapter tự bóc trường **body** của mọi loại event thành **GreetingRequest**. Hãy chọn kiểu Java đầu vào hoặc một bước chuyển đổi đúng với event contract và kiểm thử bằng payload thật từ trigger đã chọn.

## 13. Gọi thử Lambda và phân biệt output với log

Ví dụ AWS CLI dành cho môi trường đã cấu hình AWS credentials/quyền gọi Lambda, ở shell hỗ trợ cú pháp nháy đơn:

~~~bash
aws lambda invoke \
  --function-name greeting-lambda \
  --cli-binary-format raw-in-base64-out \
  --payload '{"name":"Lan"}' \
  response.json

cat response.json
~~~

**greeting-lambda** là tên triển khai minh họa; **response.json** là file output của lệnh CLI. Đây không phải file cần tạo trong phạm vi bài học đang soạn.

Điều nên xác minh trong bài thực hành:

1. Lời gọi không bị lỗi khởi tạo handler.
2. Spring context tìm được bean **greet**.
3. Input JSON được chuyển đúng thành **GreetingRequest**.
4. Output có cấu trúc của **GreetingResponse**.
5. CloudWatch logs không chứa exception hoặc dữ liệu nhạy cảm.

**Lệnh CLI có thể hoàn tất thao tác gọi Lambda ngay cả khi Lambda trả lỗi ứng dụng.** Cần xem metadata phản hồi (ví dụ dấu hiệu function error), nội dung response và log; không chỉ dựa vào exit code của lệnh CLI.

## 14. Phụ thuộc AWS adapter không thay thế event-type libraries

Với event đầu vào đặc thù, mã ứng dụng có thể cần các lớp như **SQSEvent**, **S3Event**, **SQSBatchResponse** hoặc **Context**. Khi đó có thể cần khai báo **aws-lambda-java-events** hoặc **aws-lambda-java-core** một cách tường minh, đúng version và scope theo phần API được import.

Ví dụ chữ ký dành cho SQS:

~~~java
// Minh họa chữ ký, không phải xử lý batch hoàn chỉnh.
Function<com.amazonaws.services.lambda.runtime.events.SQSEvent,
         com.amazonaws.services.lambda.runtime.events.SQSBatchResponse>
    processSqsBatch = event -> {
        // Kiểm tra từng record và xây kết quả theo contract AWS.
        throw new UnsupportedOperationException(
            "Implement batch processing and partial failure response");
    };
~~~

Đoạn trên chỉ cho thấy vì sao một kiểu **SQSEvent** khác **GreetingRequest**. Nó cố ý chưa triển khai xử lý SQS và **không được dùng trực tiếp ở production**. Nếu muốn trả partial batch response, cần tuân thủ đúng event source mapping và cấu hình hỗ trợ report batch item failures của AWS; một giá trị **SQSBatchResponse** tự tạo không đủ nếu trigger chưa được cấu hình theo cơ chế tương ứng.

**spring-cloud-function-adapter-aws** giải quyết đường tích hợp chung. Nó không tự cấp IAM role, tạo SQS queue, bảo đảm idempotency hoặc quyết định chính sách retry/dead-letter của từng nguồn sự kiện.

Tương tự, nếu nghiệp vụ gọi DynamoDB hoặc S3 bằng AWS SDK, dependency SDK, client configuration và quyền IAM cần được khai báo riêng. Không nên mặc định adapter kéo theo một AWS SDK đầy đủ có thể sử dụng cho mọi dịch vụ.

## 15. Chuyển đổi dữ liệu và generic types

**FunctionInvoker** có thể cố gắng chuyển payload đầu vào thành kiểu khai báo trên Function.

Ví dụ:

~~~java
Function<GreetingRequest, GreetingResponse>
~~~

giúp adapter hiểu đích conversion rõ hơn so với:

~~~java
@SuppressWarnings("rawtypes")
Function genericFunction
~~~

Khi dùng kiểu raw hoặc đối số generic không rõ, converter có thể chọn biểu diễn chung như **Map**, làm logic nghiệp vụ dễ gặp lỗi cast hoặc sai schema.

Bảng lưu ý:

| Chữ ký | Trường hợp sử dụng | Rủi ro cần kiểm tra |
| --- | --- | --- |
| **Function<String, String>** | Sự kiện văn bản đơn giản | Event JSON string và plain text có thể khác nhau |
| **Function<DTO, Result>** | Sự kiện có schema rõ ràng | Field thiếu, kiểu số, nullability, serializing records |
| **Function<Map<String,Object>, R>** | Event linh hoạt hoặc chưa biết schema | Dễ ép kiểu thủ công, khó versioning |
| **Function<InputStream, R>** | Cần xử lý raw input | Logic tự chịu trách nhiệm parse và lỗi dữ liệu |
| **Function<SQSEvent, SQSBatchResponse>** | Xử lý sự kiện batch từ SQS | Batch semantics, retry và partial failure |

Những thư viện hỗ trợ JSON có thể nằm trong dependency tree của adapter, nhưng **kiểu dữ liệu do bạn chọn vẫn phải được serialization hỗ trợ**. Cần test những sự kiện thực tế thay vì chỉ gọi trực tiếp Java Function.

## 16. Local test: kiểm thử nghiệp vụ trước khi deploy

Lợi thế của Spring Cloud Function là logic có thể kiểm thử không cần AWS credentials, Lambda service hoặc một HTTP server.

Ví dụ unit test JUnit 5 cho bean **greet**:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class GreetingFunctionUnitTest {

    private final GreetingLambdaApplication application =
        new GreetingLambdaApplication();

    @Test
    void greetsValidName() {
        var result = application.greet().apply(
            new GreetingLambdaApplication.GreetingRequest("Lan")
        );

        assertEquals("Xin chào, Lan", result.message());
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
            () -> application.greet().apply(
                new GreetingLambdaApplication.GreetingRequest("  ")
            ));
    }
}
~~~

Bài test trên chỉ xác minh **logic Java**. Nó không kiểm tra class handler, AWS runtime, conversion JSON hay JAR layout.

### Kiểm thử FunctionCatalog trong Spring context

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest
class GreetingFunctionCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void findsGreetByName() {
        Function<GreetingLambdaApplication.GreetingRequest,
                GreetingLambdaApplication.GreetingResponse> fn =
            catalog.lookup("greet");

        assertNotNull(fn);

        var output = fn.apply(
            new GreetingLambdaApplication.GreetingRequest("Lan")
        );

        assertEquals("Xin chào, Lan", output.message());
    }
}
~~~

Khi chạy test, dự án cần **spring-boot-starter-test** và các dependency Spring Cloud Function thích hợp. Nếu test sử dụng **@SpringBootTest**, Spring context cần khởi tạo được mà không phụ thuộc dịch vụ AWS thật (trừ khi bạn đang viết integration test chủ đích với dịch vụ bên ngoài).

### Cấp kiểm thử cần phân biệt

| Cấp kiểm thử | Kiểm tra điều gì? |
| --- | --- |
| **Unit test** | Quy tắc trong **Function.apply(...)**, validation và output |
| **Spring integration test** | Bean discovery, DI và **FunctionCatalog.lookup(...)** |
| **Artifact verification** | Shaded JAR có handler, classes, manifest và metadata cần thiết |
| **Lambda invocation test** | Handler, runtime, event conversion, serialization, logs |
| **Trigger integration test** | Event envelope SQS/S3/API Gateway, retry, batching, IAM và timeout |

**Test pass ở cấp trước không bảo đảm cấp sau pass**. Ví dụ unit test có thể chạy bình thường nhưng Lambda trả **ClassNotFoundException** nếu shade JAR thiếu **FunctionInvoker.class**.

## 17. Chẩn đoán lỗi dependency và packaging

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| **ClassNotFoundException: FunctionInvoker** | Chưa thêm adapter hoặc shaded JAR không chứa dependency | Kiểm tra dependency tree và artifact upload |
| **ClassNotFoundException** cho lớp ứng dụng | Sai JAR layout hoặc thiếu lớp main | Kiểm tra **jar tf**, **Start-Class**, **MAIN_CLASS** |
| **FunctionCatalog không tìm thấy greet** | Sai tên bean/definition, Spring context không quét lớp | Kiểm tra **@Bean**, package scan và env var |
| Lambda khởi tạo nhưng lỗi auto-configuration | Spring metadata bị ghi đè khi shade | Kiểm tra resource transformers và Spring Boot version |
| **NoSuchMethodError** hoặc xung đột lớp Spring | Phiên bản Boot/Cloud/Function không tương thích | Kiểm tra BOM, dependency tree, duplicate versions |
| Input được nhận dưới dạng Map không mong muốn | Generic không rõ hoặc converter không biết DTO | Khai báo **Function<DTO, R>**, test event JSON thật |
| Output khác khi gọi qua API Gateway | Sự kiện có event envelope khác direct invoke | Ánh xạ **body**, status, headers theo trigger |
| AWS handler sai | Đặt tên bean Java làm Lambda handler | Dùng **FunctionInvoker**, chọn bean qua definition |
| Runtime báo unsupported class version | Compile Java cao hơn runtime Lambda | Đồng bộ compiler release và Java runtime |
| Cold start quá lâu | Application context lớn, quá nhiều dependency/init | Giảm auto-configuration và dependency, đo cold-start |
| Không gọi được S3/DynamoDB | Thiếu SDK, endpoint/region hoặc IAM permissions | Kiểm tra dependency dịch vụ, client config và IAM |
| Build chạy local nhưng Lambda lỗi | Upload nhầm Boot executable JAR thay vì shaded JAR | Xác minh classifier/tên artifact và cấu trúc trong JAR |

### Kiểm tra dependency tree

Với Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.cloud
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Các lệnh này giúp thấy adapter, Spring Cloud Function context và phiên bản đã resolve. Trường hợp có nhiều phiên bản module hoặc dependency không mong đợi, điều chỉnh BOM và exclusion theo lý do xác định; không nên loại bỏ ngẫu nhiên dependency chỉ để build tạm qua.

## 18. Vận hành: lạnh/nóng, IAM và bảo mật cấu hình

Một JAR đầy đủ vẫn có thể khó vận hành nếu ứng dụng khởi tạo quá nặng hoặc phụ thuộc bên ngoài.

**Cold start:** khi Lambda tạo execution environment mới, hệ thống phải tải artifact, khởi động Java runtime, khởi tạo Spring context và các dependency. Thêm Spring Web, quá nhiều auto-configuration hoặc tạo các client nặng tại startup có thể ảnh hưởng độ trễ và chi phí.

**Warm invocation:** một environment có thể được tái sử dụng. Bean singleton có thể tồn tại qua nhiều invocation cùng environment, nhưng **không thể dựa vào việc tái sử dụng này để giữ trạng thái nghiệp vụ**. Nhiều environment không tự chia sẻ bộ nhớ.

**IAM:** cấp quyền tối thiểu cho Lambda execution role, ví dụ chỉ cho phép đọc bucket hoặc ghi vào bảng mà nghiệp vụ thực sự cần. Adapter AWS không tự tạo quyền. Không nên coi event payload hoặc header do nguồn gửi là đã xác thực nếu chưa qua kiểm soát phù hợp.

**Secrets:** tránh hard-code access key hoặc secret trong source và biến môi trường không được quản lý bảo mật. Sử dụng cơ chế cấu hình/bí mật được quản lý thích hợp cho dự án; không log credentials hay toàn bộ payload nhạy cảm.

**Observability:** sử dụng log có request ID/correlation ID được chuẩn hóa, theo dõi error, duration, cold start và timeout. Exception từ Function phải được phân loại để tránh retry không cần thiết với dữ liệu sai.

**Tối ưu nâng cao:** Lambda SnapStart, cấu hình memory/CPU và functional bean registration có thể giúp giảm cold-start trong những trường hợp phù hợp; cần đo thực tế, kiểm tra tương thích runtime và tác động đến việc khởi tạo client/trạng thái. Không bật một cơ chế tối ưu chỉ vì thấy cấu hình trong ví dụ không cùng phiên bản.

## 19. Checklist trước khi triển khai

| Câu hỏi | Trạng thái mong đợi |
| --- | --- |
| Đã khai báo **spring-cloud-function-adapter-aws**? | Có |
| Spring Boot/Cloud/Function có release version tương thích? | Có, được quản lý bằng BOM/phiên bản khóa |
| Ứng dụng có bean Function/Supplier/Consumer phù hợp? | Có, tên rõ ràng |
| **spring_cloud_function_definition** có trỏ đúng bean khi cần? | Có |
| Đã tạo artifact **shaded JAR** phù hợp runtime? | Có |
| JAR có **FunctionInvoker**, lớp main, metadata Spring? | Có, đã kiểm tra |
| AWS handler trỏ tới **FunctionInvoker**? | Có |
| **Start-Class** hoặc **MAIN_CLASS** cho main discovery đã được xác minh? | Có |
| Java bytecode tương thích Lambda runtime? | Có |
| Đã test direct invoke với input JSON thực tế? | Có |
| Nếu dùng API Gateway/SQS/S3, đã test event envelope? | Có |
| IAM, timeout, memory và retry phù hợp? | Có |
| Đã kiểm tra log, dữ liệu nhạy cảm và tác dụng phụ/idempotency? | Có |

Checklist này nhấn mạnh rằng **dependency là điều kiện cần, chưa phải điều kiện đủ**. Deploy thành công phụ thuộc cả bean registration, version, packaging, handler, event mapping và cấu hình vận hành.

## 20. Bài tập thực hành

**Bài tập 1 — Phân biệt dependency.** Một ứng dụng hiện có **spring-cloud-starter-function-web** muốn chạy trên Lambda. Hãy nêu artifact cần bổ sung, vì sao Web starter không thay thế AWS adapter và khi nào có thể loại trừ Web/Stream adapter khỏi artifact deploy.

**Bài tập 2 — Maven/Gradle.** Viết một cấu hình BOM và dependency cho **spring-cloud-function-adapter-aws**. Giải thích tại sao không nên điền version Spring Cloud Function không tương thích với Spring Boot, và lệnh nào giúp kiểm tra dependency tree.

**Bài tập 3 — Bean và handler.** Tạo **@Bean("normalizeSku") Function<String,String>**, cấu hình handler **FunctionInvoker** và environment variable để Lambda chọn **normalizeSku**. Giải thích sự khác nhau giữa Lambda handler và tên bean.

**Bài tập 4 — Shaded JAR.** Từ một dự án có executable Boot JAR và AWS shaded JAR, hãy nhận diện artifact nào dùng để upload. Kiểm tra **FunctionInvoker.class**, lớp **@SpringBootApplication**, manifest và **AutoConfiguration.imports**. Mô tả hậu quả khi shade làm mất metadata Spring.

**Bài tập 5 — DTO conversion.** Đổi hàm từ **Function<String, String>** sang **Function<GreetingRequest, GreetingResponse>**. Kiểm thử direct Lambda JSON object có trường **name**, sau đó giải thích vì sao API Gateway event không nhất thiết có cấu trúc trực tiếp đó.

**Bài tập 6 — Nhiều Lambda từ một JAR.** Đăng ký hai bean **uppercase** và **lowercase**; triển khai thành hai Lambda dùng chung artifact nhưng có **spring_cloud_function_definition** khác nhau. Nêu lợi ích của việc cấu hình IAM, timeout và trigger riêng.

**Bài tập 7 — Vận hành.** Một Lambda cold start chậm sau khi thêm Spring Web và AWS SDK không cần thiết. Lập kế hoạch rà soát dependency, auto-configuration, thời gian khởi tạo, memory/CPU và kiểm thử trước/sau tối ưu.

**Bài tập 8 — Phân tích lỗi.** Lambda báo **ClassNotFoundException: FunctionInvoker** dù unit test **Function.apply(...)** pass. Xác định cần kiểm tra những lớp nào: dependency, artifact build, handler và runtime, và giải thích vì sao unit test không phát hiện lỗi này.

### Ghi nhớ

- Dependency trung tâm là **org.springframework.cloud:spring-cloud-function-adapter-aws**; đây là **runtime adapter**, không phải plugin build.
- **FunctionInvoker** là handler AWS Lambda, còn **FunctionCatalog** tra cứu bean như **greet**, **normalizeSku** hoặc một chuỗi composition theo definition.
- **Spring Cloud BOM và phiên bản Boot tương thích** giúp tránh xung đột giữa adapter, context và thư viện Spring khác.
- Khi deploy Java JAR cho Lambda, phải **đóng gói shaded JAR đúng**, bảo toàn metadata Spring và xác minh **Start-Class/MAIN_CLASS** cùng handler.
- **AWS Lambda event envelope** khác nhau giữa direct invoke, API Gateway, SQS và S3; adapter không làm biến mất nhu cầu thiết kế schema và conversion.
- Unit test xác minh logic, integration test xác minh Spring, còn kiểm thử artifact/Lambda xác nhận dependency thực sự hoạt động trong môi trường triển khai.

### Tài liệu tham khảo

- [Spring Cloud Function — AWS Lambda](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): dependency, FunctionInvoker, handler, routing, shaded JAR và lưu ý triển khai.
- [Spring Cloud Function — Reference](https://docs.spring.io/spring-cloud-function/reference/): mô hình hàm, FunctionCatalog, composition và adapters.
- [AWS Lambda — Java handler](https://docs.aws.amazon.com/lambda/latest/dg/java-handler.html): hợp đồng handler và runtime Java.
- [AWS Lambda — Deployment packages for Java](https://docs.aws.amazon.com/lambda/latest/dg/java-package.html): cách đóng gói và deploy Java code.
