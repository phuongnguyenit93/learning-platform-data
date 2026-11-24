# Cấu hình FunctionInvoker::handleRequest làm điểm vào

Trong **SPRING_CLOUD_FUNCTION**, logic nghiệp vụ được khai báo bằng các bean **Supplier<T>**, **Function<T, R>** hoặc **Consumer<T>**. Khi triển khai cùng logic lên **AWS Lambda**, nền tảng không tự biết Spring bean nào cần gọi; nó cần một **handler** (điểm vào) theo hợp đồng runtime Java. Thư viện **spring-cloud-function-adapter-aws** cung cấp lớp **org.springframework.cloud.function.adapter.aws.FunctionInvoker** và phương thức **handleRequest** để nối invocation của AWS với **FunctionCatalog**.

Bài thuộc chương **AWS Lambda**, tập trung thiết lập **FunctionInvoker::handleRequest** làm handler đúng cách qua AWS Console hoặc Infrastructure as Code, xác định lớp Spring Boot cần khởi tạo, chọn Function bean nghiệp vụ, chuyển đổi event, kiểm thử và chẩn đoán lỗi. Mục tiêu là giữ nguyên logic ứng dụng khi đổi giữa HTTP, sự kiện và Lambda, trong khi trách nhiệm riêng của AWS nằm ở lớp điều hợp.

## 1. Ba tên khác nhau trong một Lambda Spring Cloud Function

Một ứng dụng có thể chứa những định danh sau:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| **Lambda handler** | **org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest** | Hàm đầu vào mà AWS Lambda runtime gọi |
| **Spring Boot application class** | **example.lambda.GreetingApplication** | Lớp cấu hình để tạo Spring ApplicationContext |
| **Function bean name** | **greet** | Định danh logic được FunctionCatalog tìm và thực thi |
| **Function definition** | **spring.cloud.function.definition=greet** | Quy tắc chọn bean hoặc composition cần chạy |

Đây là bốn khái niệm liên quan nhưng **không thể dùng thay thế nhau**. AWS không dùng tên **greet** để trực tiếp tìm một Java handler; còn **FunctionInvoker** không phải bản thân logic chào hỏi.

~~~mermaid
flowchart LR
    A["AWS Lambda invocation"] --> B["FunctionInvoker.handleRequest"]
    B --> C["Spring ApplicationContext"]
    C --> D["FunctionCatalog"]
    D --> E["greet Function bean"]
    E --> B
    B --> F["Lambda response"]
~~~

**Lỗi hay gặp:** đặt handler thành **example.lambda.GreetingApplication::main** hoặc **greet**. Phương thức **main(String[] args)** không nhận AWS event theo handler contract, còn **greet** chỉ là tên Spring bean.

## 2. Handler nghĩa là gì trong AWS Lambda Java?

Mỗi AWS Lambda function cấu hình một **handler**. Khi nhận invocation, runtime nạp class/method tương ứng trong artifact và chuyển **event** cùng thông tin **Context** theo hợp đồng của Java runtime.

AWS hỗ trợ các mô hình handler, trong đó có:

- **RequestHandler<I, O>**: Java handler nhận đối tượng input và **Context**, trả kết quả output.
- **RequestStreamHandler**: handler đọc **InputStream**, ghi **OutputStream**, nhận **Context**.
- Các phương thức Java phù hợp với quy tắc handler thông thường khi không triển khai hai interface trên.

Spring Cloud Function **FunctionInvoker** tích hợp với **RequestStreamHandler**. Chữ ký cốt lõi có dạng:

~~~java
@Override
public void handleRequest(
        java.io.InputStream input,
        java.io.OutputStream output,
        com.amazonaws.services.lambda.runtime.Context context)
        throws java.io.IOException {
    // Adapter thực hiện khởi tạo context, conversion,
    // lựa chọn Function trong catalog và ghi phản hồi.
}
~~~

Đoạn trên minh họa chữ ký để người đọc hiểu giao diện. **Không cần tự viết thân handler này** khi dùng adapter có sẵn. Trong ứng dụng, chỉ cần khai báo bean Function với kiểu dữ liệu cụ thể.

### Cú pháp handler được dùng như thế nào?

Trong AWS Lambda Console, Spring Cloud Function hướng dẫn nhập:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
~~~

Tài liệu AWS Java cũng mô tả việc dùng tên **package.Class** khi class triển khai **RequestHandler** hoặc **RequestStreamHandler**. Vì vậy nhiều ví dụ SAM của Spring Cloud Function dùng:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker
~~~

Cả hai cách đều xuất hiện trong hướng dẫn chính thức, ở các ngữ cảnh khác nhau. **Đối với bài này**, cấu hình minh họa ưu tiên **FunctionInvoker::handleRequest** đúng đề bài; khi dùng template/công cụ triển khai, phải kiểm tra giá trị handler hỗ trợ bởi **phiên bản adapter và Lambda runtime**.

Không suy ra rằng cú pháp Java method reference trong mã nguồn, chẳng hạn **service::process**, có thể đưa thẳng vào AWS handler field. AWS handler field thuộc về **runtime**, không phải tham chiếu tới Spring bean được tạo bằng **@Bean**.

## 3. FunctionInvoker thực hiện những gì?

Handler chung xử lý nhiều công việc mà một hàm nghiệp vụ không nên gánh:

1. Nhận **InputStream** sự kiện và **Context** do Lambda cung cấp.
2. Khởi tạo/lấy lại **Spring ApplicationContext** khi phù hợp với vòng đời execution environment.
3. Lấy **FunctionCatalog** từ context.
4. Xác định **function definition** hoặc áp dụng định tuyến đã cấu hình.
5. Sử dụng kiểu input của Function để chuyển event thành payload Java thích hợp khi converter hỗ trợ.
6. Gọi **Supplier**, **Function** hoặc **Consumer** đã chọn bằng wrapper tương ứng.
7. Chuyển kết quả sang output stream hoặc để lỗi lan ra runtime theo quy tắc adapter.

~~~mermaid
sequenceDiagram
    participant AWS as AWS Lambda
    participant Invoker as FunctionInvoker
    participant Spring as Spring context
    participant Cat as FunctionCatalog
    participant Fn as Function<T,R>

    AWS->>Invoker: handleRequest(input, output, Context)
    Invoker->>Spring: khởi tạo/lấy context
    Spring-->>Invoker: beans
    Invoker->>Cat: tra cứu definition
    Cat-->>Invoker: Function wrapper
    Invoker->>Fn: apply(T)
    Fn-->>Invoker: R
    Invoker-->>AWS: ghi output stream
~~~

Chữ ký **Function<T, R>** không phải đối tượng được AWS trực tiếp khởi tạo. Bean **Function** nằm trong Spring context, còn **FunctionInvoker** là điểm vào được AWS tìm từ JAR hoặc package đã deploy.

Adapter có thể dùng wrapper hỗ trợ **conversion, Message và composition**. Đối tượng catalog trả về không nhất thiết giống identity của bean gốc; không ép kiểu wrapper về một implementation cụ thể của ứng dụng nếu không có hợp đồng bảo đảm.

## 4. Ví dụ hoàn chỉnh: một Spring Boot application có hai Function

Để thể hiện rõ handler và việc chọn bean, ta tạo hai hàm: **greet** nhận DTO JSON và trả kết quả JSON; **uppercase** nhận chuỗi và trả chuỗi. Cả hai nằm trong cùng Spring Boot application nhưng AWS Lambda chỉ chọn một definition cho invocation theo cấu hình.

Tệp **src/main/java/example/lambda/GreetingApplication.java**:

~~~java
package example.lambda;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class GreetingApplication {

    public static void main(String[] args) {
        SpringApplication.run(GreetingApplication.class, args);
    }

    public record GreetingRequest(
        String name
    ) {}

    public record GreetingResponse(
        String message
    ) {}

    @Bean("greet")
    Function<GreetingRequest, GreetingResponse> greet() {
        return request -> {
            if (request == null
                    || request.name() == null
                    || request.name().isBlank()) {
                throw new IllegalArgumentException(
                    "Name must not be blank");
            }

            return new GreetingResponse(
                "Xin chào, " + request.name().trim());
        };
    }

    @Bean("uppercase")
    Function<String, String> uppercase() {
        return text -> {
            if (text == null) {
                throw new IllegalArgumentException(
                    "Text must not be null");
            }

            return text.toUpperCase(Locale.ROOT);
        };
    }
}
~~~

Ứng dụng có hai bean, với tên khác nhau:

~~~text
greet      : Function<GreetingRequest, GreetingResponse>
uppercase  : Function<String, String>
~~~

Nếu AWS chỉ định **greet**, event trực tiếp kiểu JSON object có thể là:

~~~json
{
  "name": "Lan"
}
~~~

Output nghiệp vụ dự kiến:

~~~json
{
  "message": "Xin chào, Lan"
}
~~~

**uppercase** có hợp đồng đầu vào khác: chuỗi JSON, ví dụ **"hello"**, không phải object **{"name":"Lan"}**. Khi chuyển function definition, payload test phải phù hợp chữ ký mới; nếu không, lỗi xảy ra ở conversion hoặc trong logic.

Ứng dụng không import AWS **RequestStreamHandler** hoặc tự tạo subclass **FunctionInvoker**. Việc đó chính là mục đích của adapter: giữ logic nghiệp vụ là Java Function có thể tái sử dụng.

## 5. Dependency cần có trước khi cấu hình handler

Handler chỉ hoạt động nếu artifact chứa thư viện adapter AWS. Maven dependency:

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

Đây là phần khai báo dependency, **chưa phải pom.xml hoàn chỉnh**. Dự án phải có version Spring Boot/Spring Cloud Function tương thích và Maven Shade/Gradle Shadow setup nếu triển khai qua JAR.

**Không nhầm hai loại dependency:**

| Thành phần | Dùng khi nào |
| --- | --- |
| **spring-cloud-function-adapter-aws** | Lambda handler để gọi FunctionCatalog |
| **spring-cloud-starter-function-web** | Expose function qua HTTP server; không cần chỉ để chạy Lambda |
| **spring-cloud-stream + binder** | Xử lý message qua broker theo mô hình Spring Cloud Stream |
| **aws-lambda-java-events** | Dùng kiểu sự kiện AWS cụ thể như SQSEvent/S3Event trong chữ ký |
| **aws-sdk-java** | Gọi API của dịch vụ AWS từ logic/adapter ứng dụng |

Một Lambda nhận event từ SQS không có nghĩa ứng dụng nhất thiết cần chạy Spring Cloud Stream binder. **AWS Lambda event source mapping** đã là một đường gọi khác; chọn đúng mô hình kiến trúc và event type trước khi thêm dependency.

Các dependency của Spring nên được quản lý bằng **Spring Boot BOM/parent** và **Spring Cloud BOM** tương thích. Không chọn phiên bản adapter tùy tiện chỉ vì artifact đó là mới nhất.

## 6. Chọn bean bằng spring.cloud.function.definition

Khi application có hai bean **greet** và **uppercase**, cần chỉ rõ Lambda muốn gọi hàm nào. Cách cấu hình trong Spring:

~~~yaml
spring:
  cloud:
    function:
      definition: greet
~~~

Trong môi trường AWS Lambda, property có thể được truyền qua environment variable:

~~~text
spring_cloud_function_definition=greet
~~~

Tên biến này được Spring Cloud Function hướng dẫn sử dụng cho AWS Lambda, nhằm thay dấu chấm trong tên Spring property bằng gạch dưới theo cách hỗ trợ bởi Spring Boot binding.

**Handler vẫn là FunctionInvoker**, không đổi theo bean:

~~~text
Handler = org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
spring_cloud_function_definition = greet
~~~

Nếu cần dùng **uppercase**:

~~~text
Handler = org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
spring_cloud_function_definition = uppercase
~~~

Điều khác nhau là **function definition** và **hợp đồng input/output**. Không cần tạo một lớp Java handler mới cho mỗi bean trong những trường hợp này.

### Nếu không chỉ định definition?

Spring Cloud Function có cơ chế tìm kiếm hàm mặc định và routing khi không có chỉ dẫn. Tuy nhiên, trong ứng dụng có nhiều Function/Supplier/Consumer, lựa chọn có thể mơ hồ hoặc phụ thuộc cơ chế ưu tiên được framework xác định.

**Không nên dựa vào thứ tự bean trong source code**. Khi triển khai một Lambda cho một nghiệp vụ cụ thể, đặt **spring_cloud_function_definition** tường minh, rồi kiểm thử đúng bean được gọi.

### Nếu definition là composition?

Ví dụ hai bean có kiểu phù hợp:

~~~java
@Bean("trimText")
Function<String, String> trimText() {
    return String::trim;
}

@Bean("uppercaseText")
Function<String, String> uppercaseText() {
    return text -> text.toUpperCase(Locale.ROOT);
}
~~~

Có thể chọn pipeline:

~~~text
spring_cloud_function_definition=trimText|uppercaseText
~~~

Handler vẫn giữ nguyên. **Composition** theo thứ tự trái sang phải và phải bảo đảm output của bước trước tương thích input của bước sau. Cần test thực tế với kiểu dữ liệu, converter và môi trường chạy; không ghép tùy ý hai bean chỉ vì cùng có interface Function.

## 7. Đóng gói ứng dụng để Lambda nạp được handler

Đặt handler đúng nhưng upload **JAR sai cấu trúc** sẽ vẫn gặp **ClassNotFoundException**. Với đường triển khai Java JAR của Spring Cloud Function AWS, tài liệu khuyến nghị **shaded JAR** chứa lớp handler, lớp ứng dụng, dependency và những Spring resources cần thiết.

Để ý khác biệt:

~~~text
Spring Boot executable JAR:
  BOOT-INF/classes/
  BOOT-INF/lib/...
  org/springframework/boot/loader/...

Lambda shaded JAR:
  example/lambda/GreetingApplication.class
  org/springframework/cloud/function/adapter/aws/FunctionInvoker.class
  org/springframework/... (các lớp dependency)
  META-INF/... (metadata Spring)
~~~

Với Spring Boot executable JAR, Boot launcher biết nạp nested dependencies khi chạy **java -jar**. Lambda Java runtime nạp handler từ classpath và không mặc nhiên chạy qua Boot launcher. Vì thế không upload một Spring Boot executable JAR bất kỳ rồi giả định runtime sẽ đọc lớp trong **BOOT-INF/lib**.

### Dependency và build plugin là hai việc khác nhau

- **spring-cloud-function-adapter-aws** là **runtime dependency**.
- **maven-shade-plugin** hoặc **Gradle Shadow** là công cụ **đóng gói**.
- **aws-lambda-java-core** và event SDK dùng khi ứng dụng/adapter cần API tương ứng; không thay thế handler adapter.

Một cấu hình Shade/Shadow phải merge **META-INF/spring.factories**, **AutoConfiguration.imports** và những resources liên quan theo định dạng của từng loại file. Nếu chỉ lấy một file khi nhiều dependency có metadata cùng tên, Spring context có thể lỗi dù lớp **FunctionInvoker** còn nguyên.

### Xác minh artifact

Lệnh minh họa trên hệ thống có **jar** và **grep**:

~~~bash
mvn clean package
ls -lh target/*.jar

jar tf target/greeting-aws.jar |
  grep 'org/springframework/cloud/function/adapter/aws/FunctionInvoker.class'

jar tf target/greeting-aws.jar |
  grep 'example/lambda/GreetingApplication.class'

jar tf target/greeting-aws.jar |
  grep 'META-INF/spring/'
~~~

**target/greeting-aws.jar** là tên mẫu; phải thay bằng file thật sau build, thường có version và classifier **aws**. Đảm bảo lệnh kiểm tra là trên **artifact thực tế sẽ upload**, không phải JAR khác sinh ra cùng lúc.

Nếu JAR thiếu **FunctionInvoker.class**, lỗi thuộc dependency hoặc packaging, không phải tên bean hay JSON input. Nếu thiếu **GreetingApplication.class**, **MAIN_CLASS** không thể cứu được artifact.

## 8. Xác định lớp ứng dụng bằng Start-Class hoặc MAIN_CLASS

FunctionInvoker cần biết **lớp Spring application** để khởi tạo context. Spring Cloud Function có thể đọc **Start-Class** từ JAR manifest; nếu không có hoặc muốn chỉ định rõ, có thể cung cấp environment variable **MAIN_CLASS**:

~~~text
MAIN_CLASS=example.lambda.GreetingApplication
~~~

Ví dụ manifest:

~~~text
Manifest-Version: 1.0
Start-Class: example.lambda.GreetingApplication
~~~

**MAIN_CLASS là fully qualified class name**, không phải:

~~~text
MAIN_CLASS=greet                                  # Sai: tên bean
MAIN_CLASS=FunctionInvoker                        # Sai: tên handler
MAIN_CLASS=GreetingApplication::main              # Sai: tên method
~~~

Có thể đặt các environment variables trong AWS:

~~~text
MAIN_CLASS = example.lambda.GreetingApplication
spring_cloud_function_definition = greet
~~~

Nếu manifest đã xác định đúng lớp ứng dụng, **MAIN_CLASS có thể không cần thiết**. Khi đặt cả hai, giữ chúng nhất quán và xác minh hành vi của phiên bản adapter đang dùng.

**Lưu ý:** đoạn main thông thường vẫn có thể tồn tại trong source:

~~~java
public static void main(String[] args) {
    SpringApplication.run(GreetingApplication.class, args);
}
~~~

Nhưng Lambda **không gọi main() như handler**. Adapter khởi tạo application context theo cơ chế Spring Cloud Function; việc main class được tìm thấy không đồng nghĩa AWS chạy main method theo cách giống **java -jar**.

## 9. Cấu hình AWS Lambda Console

Quy trình triển khai thủ công có thể diễn ra như sau:

1. Tạo một Lambda function với **Java managed runtime** phù hợp với bytecode ứng dụng.
2. Upload **JAR dành cho AWS** đã build, không nhầm với artifact Boot executable JAR.
3. Mở **Runtime settings** và chỉnh **Handler** thành:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
~~~

4. Ở **Configuration → Environment variables**, khai báo **spring_cloud_function_definition=greet**; thêm **MAIN_CLASS** nếu cần.
5. Đặt memory, timeout, execution role và IAM permissions phù hợp.
6. Tạo một test event chứa JSON object đúng hợp đồng của **greet**.
7. Invoke và xem output, function error và CloudWatch logs.

Tên menu có thể thay đổi theo giao diện AWS Console, nhưng các khái niệm **runtime**, **handler**, **artifact** và **environment variables** vẫn là các trường cần xác nhận.

**Không tự đặt handler bằng tên method tạo bean** như **GreetingApplication::greet**: phương thức này trả về một Function, không nhận **InputStream, OutputStream, Context** của Lambda.

## 10. Cấu hình AWS SAM / Infrastructure as Code

Có thể mô tả function bằng **AWS Serverless Application Model (SAM)**. Ví dụ một Lambda dùng bean **greet**:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  GreetingLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
      CodeUri: target/greeting-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.GreetingApplication
          spring_cloud_function_definition: greet
~~~

Giải thích:

- **Runtime: java21** là ví dụ tương thích với source/bytecode được build cho Java 21 hoặc thấp hơn theo yêu cầu runtime; phải kiểm tra danh sách runtime AWS thực tế và Spring version.
- **Handler** là điểm vào AWS, không phải function bean name.
- **CodeUri** cần trỏ đến file JAR **thực có sau build**; tên file là minh họa.
- **MAIN_CLASS** là lớp ứng dụng Spring; **spring_cloud_function_definition** là tên bean nghiệp vụ.
- **MemorySize** và **Timeout** minh họa, phải đo và điều chỉnh theo ứng dụng.
- **Role/IAM** cần được cấu hình theo mục đích gọi các dịch vụ AWS. SAM có thể sinh role mặc định cho một số cấu hình, nhưng không nên mặc định role đó đủ quyền cho mọi tác vụ.

Tài liệu Spring Cloud Function cũng có ví dụ SAM dùng giá trị **Handler** chỉ là tên lớp:

~~~yaml
Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
~~~

Lý do: FunctionInvoker triển khai interface handler Java mà runtime có thể nhận diện bằng tên lớp. Trong cùng một dự án, nên thống nhất **một cú pháp đã được kiểm thử với runtime và công cụ deploy**; bài này dùng dạng **::handleRequest** để thể hiện rõ entry method.

### Hai Lambda dùng chung một JAR

Nếu hai nghiệp vụ có quyền truy cập hoặc quy mô xử lý khác nhau, một JAR có thể được deploy thành hai Lambda riêng:

~~~yaml
Resources:
  GreetingLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
      CodeUri: target/greeting-aws.jar
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.GreetingApplication
          spring_cloud_function_definition: greet

  UppercaseLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
      CodeUri: target/greeting-aws.jar
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.GreetingApplication
          spring_cloud_function_definition: uppercase
~~~

Ví dụ minh họa chỉ tập trung handler và definition; trong SAM thực tế cần kiểm tra đủ memory, timeout, IAM, trigger và packaging. Không nên cho rằng **greet** và **uppercase** có cùng payload test: chúng nhận hai kiểu khác nhau.

## 11. Kiểm tra cấu hình qua AWS CLI

Khi đã có tên Lambda thật và quyền AWS phù hợp, có thể xem runtime/handler hiện tại:

~~~bash
aws lambda get-function-configuration --function-name greeting-lambda
~~~

Trong output, kiểm tra **Handler**, **Runtime**, **Environment.Variables**, trạng thái cấu hình và những lỗi liên quan. **greeting-lambda** ở đây là tên AWS function ví dụ, không phải Spring bean name.

Có thể cập nhật handler qua CLI:

~~~bash
aws lambda update-function-configuration --function-name greeting-lambda --handler 'org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest'
~~~

Hoặc cập nhật cấu hình qua SAM/CloudFormation/Terraform thay vì sửa trực tiếp trên Console/CLI. **Nếu dự án quản lý bằng Infrastructure as Code, nên sửa nguồn IaC rồi deploy lại**, tránh lệch trạng thái hạ tầng.

Khi cập nhật environment variables bằng CLI, lưu ý API có thể **thay thế cả tập Environment.Variables**, không chỉ chèn một key. Cần đọc cấu hình hiện tại và gửi đầy đủ các biến muốn giữ; không đưa secrets thật vào ví dụ, shell history hoặc output log.

## 12. Gọi thử direct invocation với JSON phù hợp

Sau khi deploy bean **greet**, test event:

~~~json
{
  "name": "Lan"
}
~~~

Ví dụ AWS CLI, trên shell hỗ trợ dấu nháy đơn:

~~~bash
aws lambda invoke --function-name greeting-lambda --cli-binary-format raw-in-base64-out --payload '{"name":"Lan"}' response.json

cat response.json
~~~

Kết quả nghiệp vụ mong muốn:

~~~json
{
  "message": "Xin chào, Lan"
}
~~~

Đầu ra thực tế được serialize theo adapter và event invocation. **Lệnh aws lambda invoke có thể trả về metadata thành công ở cấp API trong khi Function có lỗi thực thi**. Cần xem cả thuộc tính **FunctionError** nếu có, nội dung **response.json** và log CloudWatch.

Khi đổi **spring_cloud_function_definition** sang **uppercase**, event tương thích với **Function<String,String>** có thể là một **JSON string**:

~~~json
"hello"
~~~

Không truyền object **{"name":"Lan"}** vào **uppercase** rồi kết luận handler lỗi vì payload không khớp generic signature.

### Tự kiểm tra từng tầng

~~~text
1. Lambda nạp handler?
2. FunctionInvoker khởi tạo được Spring context?
3. FunctionCatalog tìm đúng bean theo definition?
4. Input được convert đúng kiểu?
5. Function thực thi và trả kết quả?
6. Output được serialize đúng cho caller?
~~~

Việc test theo từng tầng giúp tách **lỗi handler** khỏi **lỗi chuyển đổi dữ liệu** hoặc **lỗi nghiệp vụ**.

## 13. Direct invoke khác API Gateway, SQS, S3 và EventBridge

Một direct invoke JSON như **{"name":"Lan"}** không giống event đầy đủ do dịch vụ AWS khác phát.

| Nguồn invocation | Điểm cần lưu ý |
| --- | --- |
| **Direct invoke** | Payload do caller tự gửi; có thể là DTO JSON trực tiếp |
| **API Gateway** | Event thường có **body**, headers, request context và metadata route |
| **SQS** | Event chứa **Records** và có thể nhiều message trong một batch |
| **S3** | Event chứa thông tin bucket, object key và event type |
| **EventBridge** | Event envelope có **detail**, **source**, **detail-type** và metadata |

FunctionInvoker có khả năng chuyển đổi dữ liệu dựa trên generic type của bean. Nhưng **không nên giả định mọi event envelope tự động được bóc thành DTO nghiệp vụ trong mọi phiên bản và trigger**. Cần viết integration test với event thực tế hoặc dùng kiểu AWS event tương ứng khi cần.

Ví dụ xử lý SQS sử dụng một chữ ký riêng:

~~~java
@Bean("processSqs")
Function<
    com.amazonaws.services.lambda.runtime.events.SQSEvent,
    com.amazonaws.services.lambda.runtime.events.SQSBatchResponse>
        processSqs() {
    return event -> {
        // Phân tích từng record và trả partial batch failure
        // theo hợp đồng AWS nếu ứng dụng dùng tính năng đó.
        throw new UnsupportedOperationException(
            "Implement batch processing before deployment");
    };
}
~~~

Đoạn này **chỉ minh họa chữ ký**, cố ý chưa triển khai batch logic; không dùng nguyên trong production. Tính năng partial batch response cần event source mapping tương ứng và kiểu output hỗ trợ đúng. Khi dùng lớp **SQSEvent/SQSBatchResponse**, dự án có thể cần **aws-lambda-java-events**.

Trong mô hình SQS, một record thất bại có thể được giao lại. Handler được cấu hình đúng **không tự bảo đảm idempotency**, ordering, xử lý partial failure hoặc DLQ.

## 14. Metadata Context và thiết kế hàm độc lập AWS

AWS truyền một **Context** cho handler. Context có thể chứa thông tin invocation như AWS request ID, timeout còn lại hoặc runtime logger. **FunctionInvoker** nhận đối tượng này ở lớp adapter.

Nếu nghiệp vụ chỉ cần biến đổi payload, hãy giữ hàm đơn giản:

~~~java
Function<GreetingRequest, GreetingResponse>
~~~

Nếu cần correlation ID hoặc metadata từ context để phục vụ nghiệp vụ, hãy xác định rõ đường đưa metadata vào code. Không mặc định mọi trường của **Context** luôn nằm trong payload DTO hoặc Spring Message headers.

Có thể đặt adapter riêng ở ranh giới nếu cần chuyển metadata kỹ thuật thành một input Java có hợp đồng rõ ràng. Khi cần bảo toàn headers qua composition, sử dụng **Message<T>** và **MessageBuilder** có chủ đích; không copy toàn bộ metadata nhạy cảm không cần thiết.

Không đưa **aws-lambda-java-core.Context** vào chữ ký của mọi Function chỉ để ghi log. Càng buộc nhiều lớp nghiệp vụ trực tiếp vào AWS API, khả năng tái sử dụng qua HTTP/Stream càng giảm.

### Tránh nhầm authentication với correlation

Một header hoặc field event như **correlationId** chỉ hỗ trợ truy vết. Nếu được client tự gửi, nó **không phải bằng chứng định danh hay phân quyền**. Các kiểm tra xác thực nên thực hiện tại API Gateway/authorizer hoặc ranh giới tin cậy tương ứng.

## 15. Lỗi nghiệp vụ, conversion và retry không phải một loại

Khi Lambda báo lỗi, phải phân biệt:

1. **Lỗi runtime/handler:** Lambda không nạp được FunctionInvoker.
2. **Lỗi khởi tạo:** handler nạp được nhưng Spring context không khởi động.
3. **Lỗi chọn hàm:** catalog không tìm được bean/definition.
4. **Lỗi chuyển đổi:** event JSON không khớp kiểu input.
5. **Lỗi validation/nghiệp vụ:** Function được gọi nhưng từ chối input.
6. **Lỗi hạ tầng:** database/API/broker bị timeout hoặc không có quyền.

~~~mermaid
flowchart TD
    A["Lambda invocation"] --> B{"Handler load?"}
    B -- "Không" --> C["ClassNotFound / config lỗi"]
    B -- "Có" --> D{"Spring context?"}
    D -- "Không" --> E["Main class / dependency lỗi"]
    D -- "Có" --> F{"FunctionCatalog lookup?"}
    F -- "Không" --> G["Definition / bean lỗi"]
    F -- "Có" --> H{"Input conversion?"}
    H -- "Không" --> I["Schema / type lỗi"]
    H -- "Có" --> J["Business Function"]
    J --> K["Output hoặc exception"]
~~~

**Không mặc định mọi exception cần retry**. Payload sai format thường là lỗi vĩnh viễn; API timeout có thể là lỗi tạm thời. Với invocation bất đồng bộ hoặc nguồn event như SQS, cơ chế retry và thất bại do AWS trigger/event source mapping quy định.

Một **Consumer** ghi vào database cần thiết kế idempotency bằng khóa sự kiện ổn định, unique constraint/giao dịch hoặc outbox theo yêu cầu. AWS có thể giao lại cùng event sau khi tác dụng phụ đã hoàn thành nhưng response/ack thất bại.

## 16. Vòng đời Spring context và cold start

Với Lambda Java, một execution environment có thể được dùng cho nhiều invocation. FunctionInvoker có thể giữ và sử dụng lại context sau khi khởi tạo, giảm chi phí startup ở những lần gọi sau.

~~~text
Cold start:
  Lambda tải artifact
  -> JVM / handler class
  -> Spring context và bean khởi tạo
  -> FunctionCatalog lookup
  -> Function invocation

Warm invocation:
  Handler/context có thể được dùng lại
  -> Function invocation
~~~

Không bảo đảm mọi invocation đều warm: Lambda có thể tạo execution environment mới, scale ra nhiều instance hoặc recycle instance. **Singleton Spring bean chỉ là singleton trong context của một instance**, không phải một đối tượng chung trên mọi Lambda.

Để giảm cold start:

- Chỉ thêm dependency adapter và hạ tầng thực sự cần.
- Hạn chế cấu hình web server nếu function chỉ chạy trong Lambda.
- Tránh I/O khởi tạo nặng không cần thiết.
- Đo **Init Duration**, **Duration**, memory và startup logs trên workload thực tế.
- Xem xét các cơ chế như AWS SnapStart hoặc provisioned concurrency khi phù hợp, sau khi kiểm tra giới hạn/runtime và trạng thái được snapshot.

Handler đúng **không tự giảm latency**. Đây là điều kiện để Function chạy; performance cần được phân tích riêng.

## 17. Kiểm thử Java Function độc lập với Lambda

Lợi thế của Spring Cloud Function là hàm nghiệp vụ có thể được kiểm thử không cần AWS. Ví dụ JUnit 5 cho bean **greet**:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class GreetingApplicationUnitTest {

    private final GreetingApplication application =
        new GreetingApplication();

    @Test
    void greetReturnsExpectedMessage() {
        var result = application.greet().apply(
            new GreetingApplication.GreetingRequest("Lan")
        );

        assertEquals("Xin chào, Lan", result.message());
    }

    @Test
    void greetRejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
            () -> application.greet().apply(
                new GreetingApplication.GreetingRequest("  ")
            ));
    }
}
~~~

Unit test chỉ xác minh logic và validation. Nó **không chứng minh** FunctionInvoker nằm trong JAR hoặc AWS sẽ nạp được handler.

### Integration test cho FunctionCatalog

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = GreetingApplication.class)
class GreetingCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void catalogResolvesGreetBean() {
        Function<GreetingApplication.GreetingRequest,
                GreetingApplication.GreetingResponse> function =
            catalog.lookup("greet");

        assertNotNull(function);

        var response = function.apply(
            new GreetingApplication.GreetingRequest("Lan")
        );

        assertEquals("Xin chào, Lan", response.message());
    }
}
~~~

Integration test xác minh context và catalog, nhưng **không thay thế** việc kiểm tra shaded JAR hoặc gọi thử Lambda thật. Dự án cần Spring Boot Test, JUnit và Spring Cloud Function dependencies phù hợp.

## 18. Kiểm thử cấu hình handler và artifact

Một bộ test triển khai nên có các bước:

| Cấp kiểm tra | Nội dung |
| --- | --- |
| **Unit** | Function xử lý đúng input hợp lệ và từ chối input sai |
| **ApplicationContext** | Spring khởi tạo; catalog thấy bean **greet** |
| **Artifact inspection** | JAR chứa **FunctionInvoker.class**, lớp ứng dụng, resources |
| **Lambda configuration** | Handler, MAIN_CLASS, definition, Runtime và CodeUri đúng |
| **Direct invocation** | Event JSON thành DTO, output và log đúng |
| **Trigger integration** | API Gateway/SQS/S3 envelope, retry, batch, IAM theo nguồn event |

Không cần chạy Gradle/Maven/AWS deployment chỉ để kiểm thử logic Java. Ngược lại, không thể chỉ dựa vào unit test để khẳng định handler hoạt động trên Lambda.

### Kiểm tra một JAR cụ thể

~~~bash
jar tf target/greeting-aws.jar |
  grep 'FunctionInvoker.class'

jar tf target/greeting-aws.jar |
  grep 'GreetingApplication.class'
~~~

Có thể kiểm tra manifest nếu adapter cần **Start-Class**:

~~~bash
unzip -p target/greeting-aws.jar META-INF/MANIFEST.MF
~~~

Nếu adapter không xác định được main class từ manifest, cung cấp **MAIN_CLASS** đúng tên lớp. Không thay **Handler** thành tên main class để tránh lỗi Spring initialization.

## 19. Những lỗi cấu hình thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| **ClassNotFoundException: FunctionInvoker** | Thiếu adapter hoặc upload sai JAR | Kiểm tra dependency và shaded JAR |
| **ClassNotFoundException** cho lớp ứng dụng | Sai package/MAIN_CLASS hoặc JAR thiếu class | Kiểm tra **jar tf** và manifest |
| Lambda gọi nhầm Function | Có nhiều bean, thiếu/sai definition | Đặt **spring_cloud_function_definition** chính xác |
| **lookup("greet")** không thành công | Bean không được đăng ký hoặc không nằm trong component scan | Kiểm tra Spring context, tên @Bean |
| Cấu hình handler thành **GreetingApplication::main** | Nhầm Boot main với AWS handler | Dùng **FunctionInvoker::handleRequest** |
| Handler đã đúng nhưng Spring khởi tạo lỗi | Thiếu auto-configuration hoặc resource metadata | Kiểm tra Shade transformers và Spring version |
| **NoSuchMethodError** lúc startup | Dependency Spring không tương thích | Đồng bộ Boot/Cloud/Function BOM |
| JSON input biến thành Map không mong muốn | Generic type không xác định hoặc converter không phù hợp | Dùng **Function<DTO,R>**, test event |
| Direct invoke thành công nhưng API Gateway lỗi | Event envelope khác DTO | Ánh xạ request body/headers rõ ràng |
| SQS batch bị giao lại toàn bộ | Không xử lý batch failure/retry phù hợp | Cấu hình event source mapping và idempotency |
| **UnsupportedClassVersionError** | Java compile release cao hơn runtime | Đồng bộ toolchain, runtime |
| Timeout trước khi logic chạy | Cold start, dependency khởi tạo lâu | Xem Init Duration, memory, startup |
| Sửa environment khiến mất biến khác | Update CLI thay thế tập biến | Đọc cấu hình hiện tại và gửi đầy đủ keys |
| Lambda trả function error nhưng CLI request thành công | Nhầm API invoke status và kết quả handler | Kiểm tra FunctionError, body và logs |

Một lỗi phải được truy ở **tầng nơi nó xuất hiện**. Thay đổi handler string không sửa được schema sai; đổi DTO không giải quyết được ClassNotFoundException; tăng timeout không thay thế merge metadata Spring.

## 20. Checklist trước khi triển khai

- [ ] Có dependency **org.springframework.cloud:spring-cloud-function-adapter-aws** đúng phiên bản.
- [ ] Đã tạo **shaded JAR** phù hợp Java Lambda runtime, có handler và lớp ứng dụng.
- [ ] Handler được cấu hình thành **FunctionInvoker::handleRequest** hoặc dạng class-only đã kiểm chứng.
- [ ] **MAIN_CLASS** hoặc **Start-Class** xác định đúng Spring Boot application.
- [ ] Bean **greet** có tên đúng và nằm trong Spring context.
- [ ] **spring_cloud_function_definition** chọn đúng bean hoặc pipeline.
- [ ] Java compile release tương thích Lambda Runtime.
- [ ] JSON test event phù hợp kiểu input và đúng event envelope của trigger.
- [ ] Tên JAR trong CodeUri/upload trỏ tới artifact mới nhất của build.
- [ ] Lambda execution role có quyền tối thiểu cho nghiệp vụ.
- [ ] Đã kiểm tra CloudWatch logs, errors, timeouts và cold-start.
- [ ] Với sự kiện có tác dụng phụ, đã thiết kế idempotency, retry và DLQ khi cần.

## 21. Bài tập thực hành

**Bài tập 1 — Phân biệt ba tên.** Ứng dụng có lớp **com.shop.QuoteApplication** và bean **@Bean("quoteOrder")**. Ghi chính xác handler AWS, MAIN_CLASS và spring_cloud_function_definition. Giải thích vì sao không cấu hình handler bằng tên bean.

**Bài tập 2 — Console.** Tạo một Lambda dùng JAR chứa **FunctionInvoker** và bean **uppercase**. Xác định Runtime settings, Handler và environment variable. Dự đoán điều gì xảy ra nếu gửi JSON object thay vì chuỗi JSON.

**Bài tập 3 — SAM.** Tạo hai Lambda **UppercaseLambda** và **GreetingLambda** từ cùng một JAR. Dùng FunctionInvoker làm handler, nhưng mỗi Lambda đặt definition khác nhau. Phân tích khả năng cấp IAM và memory riêng.

**Bài tập 4 — Class-only và method form.** So sánh **org.springframework.cloud.function.adapter.aws.FunctionInvoker** với **org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest** dựa trên Java RequestStreamHandler và tài liệu runtime. Xác minh một cú pháp được công cụ deploy của bạn chấp nhận.

**Bài tập 5 — Sửa handler sai.** Một Lambda được cấu hình **com.example.GreetingApplication::main** và log báo lỗi khởi tạo handler. Chỉ ra giá trị handler đúng, sau đó giải thích vì sao vẫn cần main class Spring ở lớp khác.

**Bài tập 6 — FunctionCatalog.** Một app có ba bean **greet**, **uppercase**, **trim**. Viết test tra cứu **greet**; sau đó cấu hình **trim|uppercase** và dự đoán output cho chuỗi có khoảng trắng.

**Bài tập 7 — Event envelope.** Direct invoke với JSON **{"name":"Lan"}** thành công, nhưng API Gateway gửi event có **body** chứa JSON. Thiết kế bước adapter để đọc body đúng cách; không thay tên handler để sửa lỗi mapping.

**Bài tập 8 — Chẩn đoán deploy.** Unit test pass nhưng Lambda gặp **ClassNotFoundException: FunctionInvoker**. Lập thứ tự kiểm tra dependency, shaded JAR, CodeUri, handler và manifest.

**Bài tập 9 — Lỗi tạm thời và vĩnh viễn.** Consumer ghi database nhận SQS event cùng eventId hai lần. Đề xuất idempotency key, unique constraint, cách xử lý retry và cách kiểm tra partial batch response phù hợp.

### Ghi nhớ

- **FunctionInvoker::handleRequest là entrypoint AWS Lambda**, không phải tên hàm nghiệp vụ. Nó nối runtime AWS với Spring ApplicationContext và FunctionCatalog.
- **MAIN_CLASS/Start-Class xác định Spring Boot application**, còn **spring_cloud_function_definition** chọn một bean hoặc composition.
- Tài liệu chính thức có ví dụ handler dạng **class-only** lẫn **::handleRequest**; kiểm tra cú pháp phù hợp với Java runtime và công cụ triển khai.
- **Shaded JAR, dependency tương thích và metadata Spring** là điều kiện cần để runtime nạp handler và khởi động context.
- **Direct invoke, API Gateway, SQS và S3** có các hợp đồng event khác nhau; adapter không tự loại bỏ nhu cầu conversion, retry và kiểm thử trigger.
- Giữ logic **Supplier/Function/Consumer** độc lập AWS để tái sử dụng qua HTTP, sự kiện hoặc serverless; kiểm tra riêng tầng runtime/handler khi triển khai.

### Tài liệu tham khảo

- [Spring Cloud Function — AWS Lambda](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): FunctionInvoker, handler, routing, packaging, main class và conversion.
- [Spring Cloud Function — Reference](https://docs.spring.io/spring-cloud-function/reference/): FunctionCatalog, mô hình hàm và composition.
- [AWS Lambda — Java handler](https://docs.aws.amazon.com/lambda/latest/dg/java-handler.html): RequestHandler, RequestStreamHandler và cú pháp đặt tên handler.
- [AWS Lambda — Java deployment packages](https://docs.aws.amazon.com/lambda/latest/dg/java-package.html): deploy Java JAR/ZIP và runtime.
