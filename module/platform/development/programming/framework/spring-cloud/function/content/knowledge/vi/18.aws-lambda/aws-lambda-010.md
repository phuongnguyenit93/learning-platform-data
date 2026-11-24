# Chạy thử cục bộ và triển khai bằng công cụ hạ tầng

Một ứng dụng **Spring Cloud Function** có thể chạy độc lập trên JVM, được gọi qua HTTP hoặc được triển khai như **AWS Lambda**. Khi đưa ứng dụng lên Lambda, nhóm phát triển cần kiểm tra cả logic nghiệp vụ lẫn những phần chỉ xuất hiện ở môi trường serverless: handler, payload event, biến môi trường, quyền IAM, timeout, memory, event source mapping và cấu hình hạ tầng. **AWS SAM CLI** giúp xây dựng, chạy thử Lambda trong container Docker, mô phỏng endpoint API Gateway và triển khai tài nguyên bằng Infrastructure as Code (IaC).

Bài thuộc chương **AWS Lambda**, hướng dẫn một quy trình từ project Spring Cloud Function đến môi trường AWS: tạo bean chức năng, đóng gói JAR dành cho Lambda, khai báo template SAM, chạy **sam build**, sinh event mẫu, dùng **sam local invoke**, **sam local start-api**, **sam local start-lambda**, kiểm tra cấu hình, rồi triển khai bằng **sam deploy**. Bài cũng so sánh các cấp độ kiểm thử, giải thích giới hạn của mô phỏng cục bộ, trình bày cấu hình môi trường/permissions, quy trình CI/CD và cách điều tra lỗi sau triển khai.

## 1. Các cấp độ chạy thử và triển khai

Không có một lệnh nào thay thế mọi loại kiểm thử. Mỗi cấp độ trả lời một nhóm câu hỏi khác nhau:

| Cấp độ | Công cụ | Câu hỏi chính |
| --- | --- | --- |
| **Unit test** | JUnit 5, Mockito | Logic Function có đúng với input/output đã định nghĩa không? |
| **Spring integration test** | Spring Boot Test, FunctionCatalog | Bean có được đăng ký đúng tên, dependency injection và composition có hoạt động không? |
| **Đóng gói** | Maven/Gradle, Shade/Shadow | JAR có chứa FunctionInvoker, dependency và metadata Spring cần thiết không? |
| **Local Lambda** | AWS SAM CLI + Docker | Handler, runtime container, event JSON và serialization có hoạt động trong môi trường gần Lambda không? |
| **Local HTTP** | sam local start-api | Route, HTTP request/response và API Gateway event mapping có hoạt động không? |
| **Cloud integration** | AWS SAM deploy, Lambda/SQS/S3/API Gateway thật | IAM, trigger, event source mapping, retry, concurrency và dịch vụ AWS có hoạt động không? |
| **Production rollout** | SAM/CloudFormation, version/alias, CI/CD | Thay đổi có được triển khai, quan sát và rollback có kiểm soát không? |

~~~mermaid
flowchart TD
    A["Viết Supplier / Function / Consumer"] --> B["JUnit + Spring tests"]
    B --> C["Build shaded JAR"]
    C --> D["sam validate"]
    D --> E["sam build"]
    E --> F["sam local invoke / start-api / start-lambda"]
    F --> G["Cloud integration test"]
    G --> H["sam deploy"]
    H --> I["Logs, metrics, alarms"]
    I --> J["Version / alias / rollback"]
~~~

**Unit test nhanh và rẻ** nên chạy thường xuyên. **SAM local** giúp kiểm tra event/handler gần với Lambda runtime. **Cloud integration test** vẫn cần thiết vì mô phỏng cục bộ không tái hiện đầy đủ IAM, event source mapping, retry, concurrency, quota, chính sách dịch vụ và mọi hành vi của AWS.

## 2. Bộ công cụ cần chuẩn bị

Để chạy các ví dụ trong bài, chuẩn bị:

| Công cụ | Mục đích | Kiểm tra |
| --- | --- | --- |
| **JDK** | Biên dịch ứng dụng Spring Boot | java -version |
| **Maven hoặc Gradle** | Resolve dependency, test, build JAR | mvn -version hoặc gradle -version |
| **AWS SAM CLI** | Validate, build, local invoke và deploy IaC | sam --version |
| **Docker Engine/Desktop** | Chạy Lambda runtime container khi dùng sam local | docker version |
| **AWS CLI v2** | Credentials, profile, kiểm tra tài nguyên và invoke | aws --version |
| **IDE** | Debug Java, chạy JUnit | IntelliJ IDEA/Eclipse/VS Code |
| **Git** | Version control và review IaC | git --version |

### Java runtime phải tương thích

Runtime khai báo trong SAM phải phù hợp với:

- JDK dùng để biên dịch.
- Bytecode target trong Maven/Gradle.
- Phiên bản Spring Boot và Spring Cloud Function.
- Kiến trúc Lambda được chọn, ví dụ **x86_64** hoặc **arm64**.
- Runtime AWS Lambda còn được hỗ trợ tại thời điểm triển khai.

Ví dụ template dùng **java21** không có nghĩa mọi JAR biên dịch bằng JDK mới hơn đều chạy được. Đặt compiler release tương thích với runtime đích và kiểm tra danh sách runtime Lambda hiện hành trước khi chọn.

### Docker cần chạy khi nào?

Các lệnh **sam local invoke**, **sam local start-api** và **sam local start-lambda** dùng container runtime để mô phỏng Lambda. Docker phải được cài và daemon phải đang chạy. Nếu chỉ chạy JUnit hoặc Spring Boot app trực tiếp trên JVM, không cần Docker.

### AWS credentials và profile

Lệnh triển khai lên AWS cần credentials có quyền tương ứng. Có thể dùng AWS IAM Identity Center/SSO hoặc profile đã được tổ chức cấp:

~~~bash
aws configure sso
aws sso login --profile dev
aws sts get-caller-identity --profile dev
~~~

Các lệnh trên là ví dụ; tên profile **dev** do người học tự cấu hình. Không đưa access key/secret vào source code, template SAM, file event JSON hoặc log. **sam local** chỉ cần credentials AWS nếu function đang gọi dịch vụ AWS thật; bản thân việc chạy một invocation cục bộ không bắt buộc phải deploy Lambda lên cloud.

## 3. Một Spring Cloud Function mẫu để thực hành

Ta tạo ứng dụng nhỏ có một bean **uppercase** nhận String và trả String. Đây là ví dụ đơn giản để tách vấn đề đóng gói, handler và hạ tầng khỏi logic nghiệp vụ phức tạp.

Tệp **src/main/java/example/lambda/FunctionApplication.java**:

~~~java
package example.lambda;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class FunctionApplication {

    public static void main(String[] args) {
        SpringApplication.run(FunctionApplication.class, args);
    }

    @Bean("uppercase")
    Function<String, String> uppercase() {
        return value -> {
            if (value == null) {
                throw new IllegalArgumentException(
                    "Input must not be null");
            }
            return value.toUpperCase(Locale.ROOT);
        };
    }
}
~~~

Bean **uppercase** là logic nghiệp vụ. Nó không phụ thuộc AWS Lambda, API Gateway hoặc SQS. Spring Cloud Function AWS adapter sẽ cung cấp entrypoint tương thích Lambda và chuyển đổi payload theo kiểu hàm.

Có thể thêm **application.yml** để chọn function mặc định khi chạy trong những ngữ cảnh cần thiết:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase
~~~

Trong AWS Lambda, có thể đặt biến môi trường:

~~~text
spring_cloud_function_definition=uppercase
~~~

Khi ứng dụng có nhiều bean Supplier/Function/Consumer, đặt definition tường minh giúp tránh việc framework phải tự suy đoán bean nào cần chạy. **Tên bean** là **uppercase**; handler AWS vẫn là **FunctionInvoker**.

### Test logic trước khi chạy SAM

Tệp **src/test/java/example/lambda/FunctionApplicationTest.java**:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class FunctionApplicationTest {

    private final FunctionApplication app =
        new FunctionApplication();

    @Test
    void uppercasesInput() {
        assertEquals(
            "HELLO SAM",
            app.uppercase().apply("hello sam"));
    }

    @Test
    void rejectsNullInput() {
        assertThrows(
            IllegalArgumentException.class,
            () -> app.uppercase().apply(null));
    }
}
~~~

Unit test gọi trực tiếp Function bean nên không cần Docker hoặc AWS credentials. Nó chứng minh logic hoạt động với String, nhưng chưa xác minh Spring context, FunctionCatalog, Lambda handler hay deployment package.

### Kiểm tra bean trong Spring context

Có thể thêm integration test để xác minh FunctionCatalog đã đăng ký đúng tên bean:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = FunctionApplication.class)
class FunctionCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void registersUppercaseFunction() {
        assertNotNull(catalog.lookup("uppercase"));
    }
}
~~~

Test này kiểm tra Spring context và tên bean. Nó chưa kiểm tra Lambda handler hoặc AWS event conversion; những phần đó cần SAM local và cloud integration test.

## 4. Đóng gói Spring Cloud Function cho AWS Lambda

Ứng dụng cần dependency **spring-cloud-function-adapter-aws**:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-aws</artifactId>
</dependency>
~~~

Spring Cloud Function AWS adapter cung cấp handler:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
~~~

Đây là entrypoint chung. Adapter triển khai giao diện Lambda **RequestStreamHandler**, khởi tạo Spring context, tìm function qua **FunctionCatalog**, chuyển đổi input và serialize output.

### Vì sao cần shaded JAR?

Một Spring Boot executable JAR thông thường có thể chứa dependency lồng trong **BOOT-INF/lib**. Cách đóng gói AWS Lambda của Spring Cloud Function sử dụng **shaded JAR** để gom class/dependency vào layout có thể được Java Lambda runtime tải trực tiếp.

Tên artifact ví dụ:

~~~text
target/function-app-1.0.0-aws.jar
~~~

Dự án Maven có thể tạo artifact classifier **aws** bằng **Maven Shade Plugin**. Dự án Gradle có thể dùng **Shadow Plugin**. Khi shade, cần giữ/merge các metadata Spring như **META-INF/spring.factories**, **AutoConfiguration.imports**, service files và resource khác theo hướng dẫn của phiên bản Spring Boot đang dùng.

### Maven Shade Plugin và metadata Spring

Một cấu hình rút gọn dưới đây minh họa cách tạo classifier **aws** và merge một số resource Spring. Phiên bản Maven Shade Plugin, Spring Boot Maven Plugin và các transformer phải tương thích với BOM/phiên bản dự án; tham khảo sample chính thức của Spring Cloud Function khi nâng major version.

Thuộc tính **spring-boot.version** trong ví dụ phải được khai báo trong POM và trùng phiên bản Spring Boot mà ứng dụng đang sử dụng.

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.0</version>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>${spring-boot.version}</version>
        </dependency>
    </dependencies>
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
                    <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                    <transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
                        <resource>META-INF/spring.handlers</resource>
                    </transformer>
                    <transformer implementation="org.springframework.boot.maven.PropertiesMergingResourceTransformer">
                        <resource>META-INF/spring.factories</resource>
                    </transformer>
                    <transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
                        <resource>META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports</resource>
                    </transformer>
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là phần minh họa cấu hình, không phải POM đầy đủ. Một số ứng dụng Spring Boot cần merge thêm **META-INF/spring.schemas**, **spring.components** hoặc metadata khác. Hãy đối chiếu danh sách transformer với hướng dẫn Spring Cloud Function của phiên bản đang dùng; nếu metadata bị ghi đè, context có thể không khởi tạo đúng dù JAR vẫn được tạo thành công.

Với Gradle, dùng Shadow Plugin và cấu hình merge service files/Spring metadata tương ứng. Không giả định task **bootJar** mặc định có layout tương đương shaded JAR AWS.

**Không chỉ đổi tên file .jar thành -aws.jar.** Artifact phải thực sự được build đúng cấu hình. Có thể kiểm tra:

~~~bash
jar tf target/function-app-1.0.0-aws.jar
~~~

Tìm những class quan trọng như:

~~~text
org/springframework/cloud/function/adapter/aws/FunctionInvoker.class
example/lambda/FunctionApplication.class
~~~

Nếu JAR thiếu handler hoặc Spring metadata bị ghi đè khi shade, Lambda có thể báo **ClassNotFoundException**, không khởi tạo được ApplicationContext hoặc không tìm thấy Function bean.

### Chạy Maven build

Với Maven Wrapper trên macOS/Linux:

~~~bash
./mvnw clean package
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd clean package
~~~

Nếu dùng Maven đã cài:

~~~bash
mvn clean package
~~~

Tên file output phụ thuộc cấu hình dự án. Không mặc định mọi project đều tạo đúng **function-app-1.0.0-aws.jar**.

## 5. AWS SAM làm gì trong quy trình?

**AWS Serverless Application Model (SAM)** là một framework IaC mở rộng CloudFormation. Template SAM mô tả Lambda, API, queue, bucket, environment variables, IAM policies và các tài nguyên liên quan. SAM CLI cung cấp các lệnh để:

- **sam init**: khởi tạo project mẫu.
- **sam validate**: kiểm tra template.
- **sam build**: build và sắp xếp artifact cho các bước tiếp theo.
- **sam local**: chạy thử ứng dụng trong container local.
- **sam deploy**: triển khai template và artifact lên AWS thông qua CloudFormation.
- **sam logs**: đọc/tail log của Lambda đã deploy.
- **sam sync**: đồng bộ thay đổi nhanh lên môi trường cloud trong quy trình phát triển.
- **sam remote invoke**: invoke tài nguyên cloud từ SAM CLI.

~~~mermaid
flowchart LR
    A["template.yaml"] --> B["sam validate"]
    B --> C["sam build"]
    C --> D[".aws-sam/build"]
    D --> E["sam local"]
    D --> F["sam deploy"]
    F --> G["CloudFormation stack"]
    G --> H["Lambda / API / IAM / Event sources"]
~~~

SAM không thay thế Maven/Gradle hoặc Spring Cloud Function. Nó điều phối build artifact và mô tả hạ tầng. Code Java vẫn cần được biên dịch, test và đóng gói theo yêu cầu của Lambda.

## 6. Khai báo SAM template cho Spring Cloud Function

Ví dụ **template.yaml**:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: Spring Cloud Function running on AWS Lambda

Resources:
  UppercaseFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
      CodeUri: .
      MemorySize: 512
      Timeout: 15
      Architectures:
        - x86_64
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.FunctionApplication
          spring_cloud_function_definition: uppercase
      Events:
        UppercaseApi:
          Type: HttpApi
          Properties:
            Path: /uppercase
            Method: POST
            PayloadFormatVersion: "2.0"

Outputs:
  UppercaseApiUrl:
    Description: HTTP API endpoint
    Value: !Sub "https://${ServerlessHttpApi}.execute-api.${AWS::Region}.amazonaws.com"
~~~

Template trên minh họa một Lambda có API Gateway HTTP API event. Các trường quan trọng:

- **Runtime**: môi trường Java của Lambda; phải khớp bytecode.
- **Handler**: FunctionInvoker, không phải tên bean uppercase.
- **CodeUri**: thư mục mã/build context dùng bởi SAM.
- **MemorySize/Timeout**: cấu hình tài nguyên của Lambda.
- **Architectures**: kiến trúc CPU của Lambda.
- **Environment.Variables**: chọn bean qua **spring_cloud_function_definition**.
- **Events**: khai báo API Gateway route kích hoạt Lambda.

**Tên logical ID UppercaseFunction khác tên bean uppercase và khác tên handler.** Khi chạy **sam local invoke**, truyền logical ID của resource, còn Spring Cloud Function dùng environment variable để tìm bean.

## 7. Dùng Makefile để SAM build shaded JAR

Java Lambda thông thường có thể dùng Java builder mặc định của SAM. Tuy nhiên, ứng dụng Spring Cloud Function cần cấu hình Maven Shade/Gradle Shadow và giữ metadata Spring. Nếu SAM build theo quy trình Maven mặc định, các bước build tùy chỉnh trong POM có thể không tạo ra đúng shaded artifact mà adapter cần.

Một cách rõ ràng là khai báo **Metadata: BuildMethod: makefile**. SAM sẽ gọi target tương ứng trong Makefile để tạo artifact.

Thêm vào resource:

~~~yaml
  UppercaseFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
      CodeUri: .
      MemorySize: 512
      Timeout: 15
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.FunctionApplication
          spring_cloud_function_definition: uppercase
    Metadata:
      BuildMethod: makefile
~~~

Tệp **Makefile** ở thư mục CodeUri:

~~~makefile
build-UppercaseFunction:
	mvn -B -DskipTests clean package
	mkdir -p "$(ARTIFACTS_DIR)/lib"
	cp target/function-app-1.0.0-aws.jar "$(ARTIFACTS_DIR)/lib/"
~~~

Thay **function-app-1.0.0-aws.jar** bằng đúng tên shaded JAR do Maven tạo ra. Makefile cần giữ indent bằng **tab** trước mỗi lệnh. Môi trường build phải có Maven và JDK phù hợp; nếu dùng Maven Wrapper, thay lệnh **mvn** bằng wrapper tương ứng với hệ điều hành/build container.

**ARTIFACTS_DIR** là biến môi trường do SAM cung cấp cho custom Makefile build. Đối với Java ZIP deployment, dependency JAR được đặt trong **lib/** để Java Lambda runtime có thể tải từ classpath.

Trên Windows, custom Makefile cần có GNU Make và shell phù hợp. Có thể dùng WSL/Git Bash hoặc chuẩn hóa build trong Linux CI container; nếu build thủ công bằng PowerShell, dùng Maven Wrapper Windows và bảo đảm SAM template trỏ tới artifact đã tạo đúng layout.

### Những điều phải kiểm tra

- Makefile nằm đúng thư mục **CodeUri**.
- Target có tên **build-UppercaseFunction**, khớp logical ID resource.
- Build tạo đúng shaded JAR classifier **aws**.
- JAR được copy vào **$(ARTIFACTS_DIR)/lib/**.
- JAR có **FunctionInvoker.class**, application class và Spring metadata.
- Template và artifact trong **.aws-sam/build** được tạo mới sau khi sửa source.

Không chỉnh trực tiếp file bên trong **.aws-sam/build**. Đây là output của SAM; hãy sửa source/Makefile rồi chạy lại **sam build**.

## 8. Kiểm tra template trước khi build

Chạy từ thư mục có **template.yaml**:

~~~bash
sam validate
~~~

Nếu đã cài công cụ lint tương ứng, có thể chạy:

~~~bash
sam validate --lint
~~~

SAM validation kiểm tra cấu trúc và quy tắc của template. Nó không thay thế kiểm tra toàn bộ quyền IAM, logic Java hoặc khả năng chạy thực tế của Lambda.

Khi template tham chiếu file, Makefile hoặc artifact không tồn tại, kiểm tra đường dẫn tương đối từ thư mục project root. Tránh dùng đường dẫn tuyệt đối chỉ có trên máy cá nhân trong template được chia sẻ cho CI/CD.

## 9. Build ứng dụng bằng SAM

Chạy:

~~~bash
sam build
~~~

SAM tạo thư mục:

~~~text
.aws-sam/
  build/
    UppercaseFunction/
      lib/
        function-app-1.0.0-aws.jar
    template.yaml
  build.toml
~~~

Đây là cấu trúc minh họa; file thực tế phụ thuộc template và build method.

Nếu muốn build trong container gần với môi trường Lambda:

~~~bash
sam build --use-container
~~~

**sam build** chuẩn bị artifact để local test hoặc deploy, thường tạo **.aws-sam/build**. Với Makefile custom, SAM chạy các lệnh trong target của bạn. Vì vậy, chỉ build project tin cậy và xem xét Makefile, POM, Gradle scripts trước khi thực thi.

### Khi nào dùng --use-container?

- Muốn giảm khác biệt giữa môi trường build local và runtime Linux.
- Có dependency native hoặc cần build theo môi trường tương thích Lambda.
- Muốn chuẩn hóa build trên các máy phát triển khác nhau.

**--use-container** cần Docker và image build tương ứng. Nó không tự đảm bảo ứng dụng đã được test trên mọi kiến trúc CPU hay mọi dịch vụ AWS.

## 10. Tạo event mẫu để kiểm thử

AWS SAM CLI có thể sinh payload event theo định dạng AWS service. Ví dụ:

~~~bash
sam local generate-event apigateway http-api-proxy > events/http-api-v2.json
~~~

~~~bash
sam local generate-event s3 put --bucket sample-input --key incoming/demo.csv > events/s3-put.json
~~~

~~~bash
sam local generate-event sqs receive-message --body '{"orderId":"ORD-101"}' > events/sqs.json
~~~

Những lệnh trên tạo event mẫu với metadata/shape gần cấu trúc nguồn AWS. Hãy chỉnh lại bucket, ARN, body, headers, region hoặc trường nghiệp vụ theo ứng dụng. Giá trị được sinh ra thường là placeholder; event mẫu không tự tạo S3 bucket hay SQS queue thật.

Có thể xem các nguồn/event được hỗ trợ:

~~~bash
sam local generate-event --help
~~~

Hoặc xem các tùy chọn của một loại event:

~~~bash
sam local generate-event s3 put --help
~~~

### Event direct invoke đơn giản

Với bean **Function<String,String> uppercase**, file **events/uppercase.json** có thể chứa:

~~~json
"hello sam"
~~~

Đây là payload nghiệp vụ gửi trực tiếp cho Lambda. Nó không phải API Gateway event envelope. Nếu Lambda được gọi qua API Gateway, payload có thể nằm trong field **body** của event; khi đó phải kiểm tra conversion/adapter và signature của function tương ứng.

## 11. Chạy một lần bằng sam local invoke

Sau khi **sam build** thành công:

~~~bash
sam local invoke UppercaseFunction --event events/uppercase.json
~~~

SAM CLI:

1. Tìm logical ID **UppercaseFunction** trong template.
2. Dùng artifact đã build trong **.aws-sam/build** nếu có.
3. Khởi tạo Lambda runtime container bằng Docker.
4. Gửi event JSON vào handler.
5. Hiển thị log và output của invocation.

Đây là cách kiểm tra một lần gọi cụ thể mà không deploy Lambda lên AWS.

### Override environment khi chạy local

Tạo **env.local.json**:

~~~json
{
  "UppercaseFunction": {
    "spring_cloud_function_definition": "uppercase"
  }
}
~~~

Chạy:

~~~bash
sam local invoke UppercaseFunction --event events/uppercase.json --env-vars env.local.json
~~~

File env này có thể chứa giá trị cấu hình dành riêng cho local. Không lưu secrets thật vào repository. Nếu Function gọi AWS SDK, credentials trong máy có thể được sử dụng theo cấu hình SAM/CLI; cần cấp quyền tối thiểu và tránh để test ghi dữ liệu vào production.

### Đọc output và logs

**sam local invoke** chạy code trong môi trường local; runtime logs thường được ghi ra stderr và kết quả function ra stdout. Khi điều tra:

- Xem dòng **START/END/REPORT** của Lambda runtime.
- Xem lỗi Spring ApplicationContext hoặc FunctionCatalog.
- Xem input JSON có đúng kiểu mà bean khai báo không.
- Xem function definition đã được chọn đúng chưa.
- Xem response serialization có thành công không.

Nếu invocation fail trước khi chạy bean, kiểm tra handler, JAR và main class trước khi sửa logic nghiệp vụ.

## 12. Chạy API Gateway cục bộ bằng sam local start-api

Khi template có **Events: Api** hoặc **Events: HttpApi**, có thể khởi động local HTTP server:

~~~bash
sam local start-api
~~~

SAM hiển thị các route local tương ứng. Ví dụ:

~~~text
Mounting UppercaseFunction at http://127.0.0.1:3000/uppercase [POST]
~~~

Gửi request:

~~~bash
curl -X POST http://127.0.0.1:3000/uppercase \
  -H "Content-Type: application/json" \
  -d '"hello sam"'
~~~

Đây là ví dụ payload JSON string cho function **String → String**. Nếu function của bạn nhận DTO hoặc dùng API Gateway proxy envelope cụ thể, body và mapping phải theo đúng contract của function/adapter. Không mặc định mọi route đều chuyển HTTP body thành cùng một kiểu Java.

### Test response HTTP

Kiểm tra:

- Status code.
- Response body.
- Content-Type.
- Header do adapter trả về.
- Cách xử lý JSON sai hoặc body rỗng.
- Route không tồn tại và method không hỗ trợ.

**sam local start-api** hữu ích cho phát triển HTTP nhưng không phải API Gateway service thật. Authorization, custom domain, throttling, WAF, usage plans, mapping, authorizer và nhiều cấu hình cloud vẫn cần kiểm thử trên AWS.

## 13. Mở endpoint Lambda cục bộ bằng sam local start-lambda

Nếu muốn gọi function local qua AWS CLI hoặc SDK, dùng:

~~~bash
sam local start-lambda --port 3001
~~~

Lệnh mở endpoint Lambda local, ví dụ:

~~~text
http://127.0.0.1:3001
~~~

Trong terminal khác, gọi bằng AWS CLI:

~~~bash
aws lambda invoke \
  --function-name UppercaseFunction \
  --endpoint-url http://127.0.0.1:3001 \
  --cli-binary-format raw-in-base64-out \
  --payload fileb://events/uppercase.json \
  response.json
~~~

Xem output:

~~~bash
cat response.json
~~~

**UppercaseFunction** là logical ID trong template; endpoint là local, không phải AWS Lambda ARN. AWS CLI ở đây dùng để gửi request tới SAM local endpoint. Không cần deploy resource thật chỉ để thử đường gọi SDK/CLI.

### Phân biệt ba lệnh local

| Lệnh | Cách gọi | Dùng khi |
| --- | --- | --- |
| **sam local invoke** | Một event file, một lần gọi | Test nhanh một Lambda event |
| **sam local start-api** | HTTP client gọi route | Test API Gateway HTTP route |
| **sam local start-lambda** | AWS CLI/SDK gọi endpoint Lambda local | Test integration code đang dùng Lambda API |

Cả ba vẫn chạy function code trên máy của bạn qua môi trường local/container; không phải một Lambda execution environment đang chạy trong AWS account.

## 14. Spring Cloud Function và event khi chạy local

**FunctionInvoker** là entrypoint AWS adapter. Nó nhận stream invocation, tạo Message, tìm function qua **FunctionCatalog**, thực thi và serialize output. Khi chạy local bằng SAM, adapter vẫn cần các cấu hình giống deployment:

~~~text
Handler:
  org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest

spring_cloud_function_definition:
  uppercase
~~~

Nếu ứng dụng có nhiều bean, definition phải xác định bean hoặc composition đúng. Không nhầm:

- **SAM logical ID**: tên resource trong template, ví dụ UppercaseFunction.
- **AWS Lambda function name**: tên tài nguyên sau deploy.
- **Spring bean name**: tên Function trong FunctionCatalog, ví dụ uppercase.
- **Handler**: FunctionInvoker::handleRequest.

### Kiểm thử các loại event

| Event | File mẫu | Điều cần xác minh |
| --- | --- | --- |
| Direct invoke | uppercase.json | Payload đúng kiểu T |
| API Gateway | http-api-v2.json | Event envelope, body, HTTP response |
| S3 | s3-put.json | Records, bucket/key và xử lý metadata |
| SQS | sqs.json | Records, body và batch response |
| EventBridge | eventbridge.json | source, detail-type, detail và schema |

Với **S3/SQS**, event mẫu chỉ mô phỏng cấu trúc JSON. Nếu code gọi S3/SQS API thật, function có thể cần AWS credentials, IAM permission và tài nguyên thật. SAM local không tự dựng đầy đủ mọi dịch vụ AWS.

### Context và metadata invocation khi chạy local

Một số metadata của Lambda như request ID, function name, log stream, remaining time được tạo bởi runtime. SAM local mô phỏng một phần thông tin này; không nên dùng giá trị local làm bằng chứng về ARN/version/permission của Lambda production.

Nếu function dựa vào AWS Context, test unit có thể mock Context, còn kiểm thử adapter cần gọi qua SAM local và sau đó xác nhận trên Lambda staging thật.

## 15. Giới hạn của SAM local

Local emulation rất hữu ích nhưng không phải bản sao đầy đủ của AWS.

| Thành phần | SAM local hỗ trợ | Phần vẫn cần cloud test |
| --- | --- | --- |
| Lambda handler/runtime | Chạy trong runtime container phù hợp | Cold start, scaling, quota và behavior runtime production |
| Input/output | Gửi event JSON và xem response | Serialization thực tế qua từng AWS trigger/adapter |
| API Gateway | Local HTTP endpoint | Authorizer, WAF, custom domain, throttling, mapping đầy đủ |
| S3/SQS | Có thể dùng event JSON mẫu | Notification delivery, poller, visibility timeout, retry, DLQ thật |
| IAM | Có thể dùng credentials local để gọi API | Execution role, resource policy, trust policy và least privilege |
| AWS SDK | Function có thể gọi dịch vụ AWS thật | KMS, VPC, endpoint policy, throttling và service behavior |
| CloudWatch | Xem log local của container | Log group, retention, subscription, alarms và metric thật |
| Concurrency | Mô phỏng invocation đơn giản | Scale-out, reserved concurrency, burst và race conditions |

**Đặc biệt:** khi function gọi AWS service bằng SDK, request có thể đi tới **tài nguyên AWS thật** bằng credentials local. Local testing không có nghĩa mọi dịch vụ được giả lập hoặc mọi request đều miễn phí.

Các lệnh local chạy code của project trên máy thông qua container và có thể cho code truy cập file/môi trường local. Chỉ chạy source đáng tin cậy; không coi container SAM local là ranh giới cách ly an toàn cho code không rõ nguồn gốc.

Nếu muốn môi trường dịch vụ giả lập, có thể nghiên cứu công cụ như LocalStack. Đây là lựa chọn bổ sung; behavior của emulator vẫn cần đối chiếu AWS thật trước khi phát hành.

## 16. Khai báo môi trường local và môi trường AWS

Không hard-code endpoint, database password, token hoặc tên bucket vào Java source. Dùng cấu hình theo môi trường:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase

app:
  quote:
    currency: VND
~~~

Trong SAM template:

~~~yaml
Environment:
  Variables:
    spring_cloud_function_definition: uppercase
    APP_QUOTE_CURRENCY: VND
~~~

Trong file **env.local.json**, có thể override những biến cần thiết cho local:

~~~json
{
  "UppercaseFunction": {
    "spring_cloud_function_definition": "uppercase",
    "APP_QUOTE_CURRENCY": "VND"
  }
}
~~~

Các giá trị nhạy cảm nên lấy từ AWS Secrets Manager/Systems Manager Parameter Store hoặc cơ chế secrets được tổ chức phê duyệt, với IAM permission phù hợp. Không commit secrets vào env.local.json.

### Tách cấu hình theo môi trường

Có thể duy trì các cấu hình:

~~~text
samconfig.toml
  [default.deploy.parameters]
  stack_name = "function-dev"
  region = "ap-southeast-1"

  [staging.deploy.parameters]
  stack_name = "function-staging"
  region = "ap-southeast-1"

  [production.deploy.parameters]
  stack_name = "function-production"
  region = "ap-southeast-1"
~~~

Đây là cấu trúc minh họa; cú pháp chính xác của samconfig phụ thuộc phiên bản SAM CLI và các tham số đã chọn trong **sam deploy --guided**. Không lưu credentials trong samconfig. Sử dụng named profile/SSO và phân quyền riêng theo environment.

## 17. IAM và các tài nguyên hạ tầng trong SAM

Template SAM có thể khai báo permission và trigger cùng Lambda. Ví dụ nếu function chỉ log và không gọi dịch vụ AWS khác, cần quyền logging cơ bản. Nếu function đọc S3, thêm quyền đọc đúng bucket/prefix. Nếu xử lý SQS, thêm quyền poll queue.

~~~yaml
Policies:
  - S3ReadPolicy:
      BucketName: !Ref InputBucket
~~~

Ví dụ này là SAM policy template minh họa cho quyền đọc S3. Cần xác minh policy được sinh ra phù hợp với yêu cầu cụ thể; không dùng quyền **AdministratorAccess** để giải quyết lỗi AccessDenied.

Trong ví dụ, **InputBucket** phải là logical resource của bucket được khai báo trong cùng template, hoặc được thay bằng tên bucket/ARN phù hợp với cách quản lý tài nguyên của dự án.

Một số cấu hình thường cần khai báo:

- **Execution role**: quyền mà function được phép sử dụng.
- **Resource-based policy**: dịch vụ nào được phép invoke Lambda.
- **Timeout/MemorySize**: giới hạn runtime.
- **ReservedConcurrency**: giới hạn concurrency nếu workload cần.
- **Dead-letter queue / destinations**: nơi xử lý invocation lỗi bất đồng bộ.
- **Event source mapping**: cấu hình batch, retry, filter và partial batch response cho queue/stream.
- **Log retention**: thời gian lưu CloudWatch logs.
- **Tracing**: X-Ray/OpenTelemetry theo chiến lược observability.

### Không nhầm IAM của deployer với IAM của Lambda

Có hai danh tính khác nhau:

1. **Developer/CI deploy identity**: được phép tạo/update CloudFormation stack, upload artifact và truyền role theo chính sách.
2. **Lambda execution role**: được Lambda assume khi function chạy, chỉ nên có quyền nghiệp vụ tối thiểu.

Một lệnh **sam deploy** thành công không có nghĩa execution role có đủ quyền gọi S3/SQS/DynamoDB. Ngược lại, quyền runtime của Lambda không cấp quyền deploy CloudFormation cho developer.

## 18. Triển khai lần đầu bằng sam deploy --guided

Sau khi build và local test:

~~~bash
sam deploy --guided
~~~

SAM CLI hỏi những thông tin như:

| Prompt | Ý nghĩa |
| --- | --- |
| **Stack Name** | Tên CloudFormation stack |
| **AWS Region** | Region triển khai |
| **Confirm changes before deploy** | Xem changeset trước khi áp dụng |
| **Allow SAM CLI IAM role creation** | Cho phép SAM tạo IAM role nếu template cần |
| **Disable rollback** | Tùy chọn xử lý rollback khi deploy lỗi |
| **Save arguments to configuration file** | Lưu lựa chọn vào samconfig.toml |

Khi deploy lần đầu, SAM có thể hỏi về S3 artifact bucket hoặc cách quản lý artifact. Artifact được upload lên S3 rồi CloudFormation tạo/cập nhật tài nguyên Lambda và các resource khác.

Sau lần guided đầu tiên, các tham số thường được lưu trong **samconfig.toml**. Lần deploy sau có thể dùng:

~~~bash
sam deploy
~~~

Nếu cần chọn environment trong samconfig:

~~~bash
sam deploy --config-env staging
~~~

Tên environment **staging** phải tồn tại trong cấu hình dự án. Trước khi deploy, đọc lại template và config vì chúng có thể tạo IAM role, API, queue, bucket hoặc thay đổi resource đang chạy.

### Xem changeset trước khi xác nhận

Nếu SAM hỏi xác nhận changes, kiểm tra:

- Resource nào được tạo mới.
- Resource nào bị thay đổi hoặc thay thế.
- IAM policy nào được mở rộng.
- API route, event source mapping và environment variables nào đổi.
- Tài nguyên stateful như S3 bucket, DynamoDB table hoặc SQS queue có nguy cơ bị thay thế/xóa không.

Không chấp nhận changeset chỉ vì code compile thành công. Hạ tầng có thể thay đổi data lifecycle và quyền truy cập.

## 19. Deploy theo CI/CD và quản lý nhiều môi trường

Trong dự án nhóm, không nên phụ thuộc vào thao tác deploy thủ công trên máy một developer. Một pipeline thường có:

~~~mermaid
flowchart TD
    A["Commit / Pull Request"] --> B["Compile + Unit tests"]
    B --> C["Build shaded JAR"]
    C --> D["SAM validate + SAM build"]
    D --> E["Local / contract tests"]
    E --> F["Deploy development"]
    F --> G["Cloud integration tests"]
    G --> H["Approval / promotion"]
    H --> I["Deploy staging / production"]
    I --> J["Canary / alias / alarms"]
    J --> K["Rollback nếu vi phạm ngưỡng"]
~~~

### Pipeline gợi ý

1. **Checkout** source code theo commit đã review.
2. Chạy **Maven/Gradle tests**.
3. Build shaded JAR và kiểm tra artifact.
4. Chạy **sam validate** và **sam build**.
5. Có thể chạy một số **sam local invoke** contract tests.
6. Deploy vào môi trường development/staging bằng role CI có giới hạn.
7. Chạy integration test trên API Gateway/SQS/S3 thật.
8. Kiểm tra logs, metrics, alarms, permission và output contract.
9. Promote artifact đã kiểm chứng sang production; tránh build lại artifact khác giữa staging và production nếu không cần.
10. Theo dõi version/alias và rollback khi health checks thất bại.

Có thể dùng CodePipeline/CodeBuild, GitHub Actions hoặc hệ thống CI/CD của tổ chức. Điều quan trọng là **cùng một artifact đã kiểm thử được đưa qua các môi trường**, còn cấu hình hạ tầng/environment được quản lý bằng IaC.

### sam sync trong phát triển

**sam sync --watch** có thể đồng bộ thay đổi nhanh lên cloud để phát triển/test. Nó hữu ích khi cần kiểm tra behavior trên dịch vụ AWS thật mà chưa muốn chạy đầy đủ pipeline mỗi lần. Tuy nhiên, đây vẫn là thay đổi cloud resource; dùng stack dev riêng, profile/role có giới hạn và không chạy trên production nếu chưa có quy trình phê duyệt.

## 20. Kiểm thử sau deploy

Sau khi deploy thành công, xem outputs của stack:

~~~bash
aws cloudformation describe-stacks \
  --stack-name function-dev \
  --query "Stacks[0].Outputs"
~~~

Nếu có API endpoint, gọi thử:

~~~bash
curl -X POST https://example.execute-api.ap-southeast-1.amazonaws.com/uppercase \
  -H "Content-Type: application/json" \
  -d '"hello aws"'
~~~

Endpoint **example** chỉ là placeholder; lấy URL thật từ CloudFormation Outputs hoặc SAM CLI. Kiểm tra status code, body, headers và logs.

Có thể invoke Lambda trực tiếp bằng SAM:

~~~bash
sam remote invoke UppercaseFunction --stack-name function-dev --event '"hello aws"'
~~~

**sam remote invoke** gọi tài nguyên cloud thật. Không nhầm với **sam local invoke**; request có thể chạy trên AWS, tiêu thụ quota và gọi các dịch vụ thật.

### Xem log sau triển khai

~~~bash
sam logs -n UppercaseFunction --stack-name function-dev --tail
~~~

Có thể xem bằng CloudWatch Logs console hoặc AWS CLI. Khi điều tra, đối chiếu:

- AWS request ID.
- Lambda function/version/alias.
- Function definition.
- Event source và payload schema.
- Duration, memory, timeout, cold start.
- Error stack trace và downstream request.
- IAM AccessDenied, throttling hoặc network timeout.

## 21. Version, alias và rollback

Trong production, nên tách **$LATEST** khỏi version được phát hành và alias trỏ tới version đã kiểm chứng. Quy trình triển khai có thể:

1. Deploy code/config mới.
2. Kiểm thử $LATEST hoặc version mới.
3. Publish version.
4. Chuyển alias có kiểm soát.
5. Theo dõi errors, duration, business metrics và alarms.
6. Chuyển alias về version trước nếu lỗi vượt ngưỡng.

SAM/CloudFormation hỗ trợ cấu hình deployment preference/alias theo loại deployment strategy phù hợp. Canary/linear deployment cần có alarm và quyền liên quan. Không cho rằng chỉ chạy **sam deploy** là tự động tạo rollout an toàn; cần khai báo rõ cơ chế version/alias và policy.

### Khi rollback

Rollback code không luôn rollback được dữ liệu đã ghi hoặc schema database đã đổi. Với migration, event schema hoặc message contract, phải thiết kế backward compatibility và quy trình xử lý dữ liệu. Giữ lại artifact/version trước đó, ghi nhận commit/config đã deploy và kiểm tra alias sau rollback.

## 22. Các lỗi thường gặp khi chạy local

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Docker is not running | Docker daemon chưa khởi động | Mở Docker Desktop/Engine rồi kiểm tra docker version |
| Template file not found | Chạy SAM sai thư mục hoặc sai template path | Chạy từ project root hoặc truyền --template-file |
| Function not found | Dùng nhầm bean name thay logical ID | sam local invoke cần logical ID trong template |
| ClassNotFoundException: FunctionInvoker | Artifact thiếu adapter hoặc JAR layout sai | Kiểm tra shaded JAR, handler và CodeUri |
| Failed to determine main class | Không có Start-Class/MAIN_CLASS phù hợp | Đặt MAIN_CLASS hoặc kiểm tra manifest |
| FunctionCatalog không thấy bean | Sai function definition hoặc component scan | Kiểm tra @Bean name, spring_cloud_function_definition |
| Local output khác cloud | Event JSON, runtime, env hoặc architecture khác | So sánh event, runtime, env và cloud integration |
| AWS SDK gọi nhầm account | Credentials/profile local không đúng | Kiểm tra aws sts get-caller-identity và profile |
| AccessDenied | Execution role hoặc local credentials thiếu quyền | Xác định principal thực sự và cấp quyền tối thiểu |
| Port already in use | start-api/start-lambda đã chạy ở port | Dùng port khác hoặc dừng process cũ |
| Sửa code nhưng local vẫn chạy bản cũ | Chưa sam build lại hoặc dùng build artifact cũ | Chạy sam build và khởi động lại server local |
| JSON conversion lỗi | Event shape không khớp Function input | Kiểm tra payload trực tiếp và event envelope |
| sam deploy không upload artifact | Thiếu bucket/quyền upload/region | Kiểm tra artifact bucket, profile và region |
| CloudFormation rollback | Template, IAM, quota hoặc resource conflict | Đọc stack events và sửa nguyên nhân gốc |
| Function timeout | Downstream chậm hoặc timeout quá thấp | Xem remaining time, timeout và dependency latency |

## 23. Các lỗi thường gặp khi triển khai hạ tầng

| Triệu chứng | Nguyên nhân | Hướng điều tra |
| --- | --- | --- |
| SAM báo thiếu CAPABILITY | Template tạo IAM resources | Xem capability prompt/option và review IAM |
| Lambda update nhưng API không đổi | API route/deployment stage hoặc alias chưa được cập nhật | Kiểm tra CloudFormation resources và endpoint |
| Function runtime không tương thích | Runtime và bytecode lệch | Đối chiếu Java compiler release và Lambda Runtime |
| Artifact lớn hoặc thiếu class | Shade sai, dependency trùng hoặc bị loại | Kiểm tra JAR contents và transformer |
| Lambda không đọc S3 | Execution role thiếu s3:GetObject hoặc bucket policy | Kiểm tra role, bucket, prefix và KMS |
| SQS mapping không hoạt động | Thiếu poll permission, queue ARN hoặc mapping sai | Xem event source mapping state và LastProcessingResult |
| Log không xuất hiện | Role thiếu quyền logging hoặc log group chưa tạo | Kiểm tra AWSLambdaBasicExecutionRole/log group |
| Secret không đọc được | Thiếu secretsmanager/ssm/KMS permissions | Kiểm tra policy và resource ARN |
| Deploy thay thế resource stateful | Logical ID/properties đổi gây replacement | Đọc changeset, retention policy và migration plan |
| Production alias vẫn chạy version cũ | Alias chưa chuyển version mới | Kiểm tra alias routing configuration |
| Local pass nhưng cloud fail | Khác IAM, networking, trigger, concurrency hoặc service behavior | Chạy cloud integration test với role/resource thật |

## 24. Checklist trước khi triển khai

- [ ] Unit tests và Spring integration tests pass.
- [ ] Bean được đăng ký đúng tên và function definition rõ ràng.
- [ ] Artifact AWS là shaded JAR/ZIP đúng cấu trúc.
- [ ] FunctionInvoker có trong deployment package.
- [ ] Spring metadata được merge khi shade.
- [ ] Java runtime, compiler release và architecture tương thích.
- [ ] sam validate pass.
- [ ] sam build tạo artifact mới trong .aws-sam/build.
- [ ] Event JSON mẫu phản ánh đúng direct invoke hoặc trigger envelope.
- [ ] sam local invoke/start-api/start-lambda được chạy với payload phù hợp.
- [ ] Local credentials không trỏ nhầm production account.
- [ ] IAM execution role theo least privilege.
- [ ] Timeout, memory, concurrency, retry và DLQ phù hợp.
- [ ] Environment variables và secrets được quản lý an toàn.
- [ ] Changeset CloudFormation đã được review.
- [ ] Cloud integration test hoàn thành.
- [ ] Logs, metrics, alarms và rollback/version/alias đã chuẩn bị.

## 25. Bài tập thực hành

**Bài tập 1 — Unit test và local invoke.** Tạo bean **uppercase** kiểu Function<String,String>. Viết JUnit test cho chuỗi thường, chuỗi rỗng và null. Tạo event JSON rồi chạy **sam local invoke**; giải thích mỗi bước xác minh điều gì.

**Bài tập 2 — Đóng gói shaded JAR.** Thêm **spring-cloud-function-adapter-aws** vào Maven. Cấu hình Shade plugin tạo artifact classifier **aws**, giữ metadata Spring. Dùng **jar tf** để xác minh FunctionInvoker và application class.

**Bài tập 3 — SAM Makefile.** Tạo resource **UppercaseFunction**, đặt **Metadata BuildMethod: makefile** và viết target build-UppercaseFunction copy JAR vào **ARTIFACTS_DIR/lib**. Chạy sam build và mô tả artifact được tạo.

**Bài tập 4 — Sinh event mẫu.** Dùng **sam local generate-event** tạo API Gateway HTTP API, S3 put và SQS receive-message. So sánh event envelope, rồi sửa dữ liệu để phù hợp với từng Function signature.

**Bài tập 5 — Local HTTP.** Thêm HttpApi event vào template, chạy **sam local start-api**, gọi route bằng curl. Kiểm tra status, body, content type và trường hợp body sai JSON.

**Bài tập 6 — Local Lambda endpoint.** Chạy **sam local start-lambda**, gọi bằng AWS CLI với **--endpoint-url**. Giải thích vì sao lệnh này không cần deploy function lên AWS.

**Bài tập 7 — Môi trường local.** Tạo **env.local.json** override function definition và một biến cấu hình nghiệp vụ. Giải thích vì sao không nên commit credentials vào file này.

**Bài tập 8 — Deploy bằng SAM.** Dùng **sam deploy --guided** để tạo stack dev. Ghi lại stack name, region, artifact bucket và các IAM capabilities; đọc CloudFormation Outputs sau deploy.

**Bài tập 9 — IAM least privilege.** Mở rộng Function để đọc object từ một prefix S3. Khai báo policy chỉ cho phép s3:GetObject trên prefix đó, deploy staging và kiểm tra AccessDenied khi thiếu quyền.

**Bài tập 10 — Cloud integration.** Cấu hình SQS trigger, gửi message vào queue thật và quan sát Lambda logs, receive count, retry và DLQ. So sánh kết quả với sam local invoke bằng event JSON.

**Bài tập 11 — Version và rollback.** Deploy version mới, chuyển alias staging, theo dõi metrics rồi rollback alias khi response sai contract. Giải thích tại sao rollback code không tự hoàn tác dữ liệu đã ghi.

**Bài tập 12 — CI/CD.** Thiết kế pipeline gồm compile, test, shaded package, sam validate, sam build, local contract test, deploy dev, integration test và approval production. Chỉ ra artifact nào được promote qua các môi trường.

### Ghi nhớ

- **JUnit/Spring tests** kiểm tra logic và FunctionCatalog; **SAM local** kiểm tra handler/event trong container; **cloud integration tests** kiểm tra IAM, trigger và behavior AWS thật.
- **sam build** chuẩn bị artifact trong **.aws-sam/build**; với Spring Cloud Function cần bảo đảm custom Shade/Shadow configuration tạo đúng shaded JAR.
- **sam local invoke** chạy một event; **sam local start-api** phục vụ HTTP route; **sam local start-lambda** mở endpoint tương thích AWS CLI/SDK; **sam local generate-event** tạo payload mẫu.
- Local testing cần Docker và có thể gọi dịch vụ AWS thật bằng credentials local. Không coi SAM local là emulator hoàn chỉnh của AWS.
- **sam deploy --guided** cấu hình lần triển khai đầu, lưu tham số trong **samconfig.toml** và deploy stack qua CloudFormation.
- **FunctionInvoker** là Lambda handler; **spring_cloud_function_definition** chọn bean; SAM logical ID là tên resource trong template.
- IaC cần review IAM, event source mapping, timeout, memory, environment, stateful resources và CloudFormation changeset.
- Production cần quan sát logs/metrics, version/alias, kiểm thử integration và rollback có kiểm soát.

### Tài liệu tham khảo

- [Spring Cloud Function — AWS Lambda adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): FunctionInvoker, handler, build Maven/Gradle, shaded JAR, FunctionCatalog và routing.
- [AWS SAM CLI — Core commands](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-corecommands.html): sam init, build, local, deploy, sync và remote invoke.
- [AWS SAM — Building applications](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-build.html): sam build, build container, artifact và Makefile.
- [AWS SAM — Local testing](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-local.html): local generate-event, invoke, start-api và start-lambda.
- [AWS SAM — Local invoke](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-local-invoke.html): một lần invocation trong Docker container.
- [AWS SAM — Local start-api](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-local-start-api.html): kiểm thử API Gateway routes cục bộ.
- [AWS SAM — Local start-lambda](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-local-start-lambda.html): endpoint Lambda local cho AWS CLI/SDK.
- [AWS SAM — Deploy applications](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-deploy.html): deploy --guided, samconfig.toml và CloudFormation.
- [AWS Lambda — Java deployment packages](https://docs.aws.amazon.com/lambda/latest/dg/java-package.html): JAR/ZIP, dependencies, Maven và Gradle.
- [AWS Lambda — Testing guide](https://docs.aws.amazon.com/lambda/latest/dg/testing-guide.html): local container testing và giới hạn so với cloud.
