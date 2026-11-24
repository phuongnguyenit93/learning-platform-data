# Chọn hàm bằng biến môi trường spring_cloud_function_definition

Trong **SPRING_CLOUD_FUNCTION**, một ứng dụng có thể chứa nhiều bean kiểu **Supplier<T>**, **Function<T, R>** và **Consumer<T>**. Khi triển khai trên **AWS Lambda**, adapter **FunctionInvoker** cần biết bean nào cần được kích hoạt cho mỗi invocation. Biến môi trường **spring_cloud_function_definition** cho phép chọn tên bean hoặc chuỗi composition mà không phải chỉnh code nghiệp vụ, thay class handler hay build một JAR riêng cho từng hàm.

Bài thuộc chương **AWS Lambda**, tập trung vào cách đặt đúng key/value, liên hệ giữa AWS handler, main class và **FunctionCatalog**, dùng chung một JAR cho nhiều Lambda, cấu hình bằng Console/SAM/AWS CLI, xử lý lỗi khi chọn sai hàm và kiểm thử end-to-end. Mục tiêu là giữ các hàm **độc lập giao thức**, nhưng có thể triển khai linh hoạt qua HTTP, sự kiện và serverless.

## 1. Biến môi trường dùng để chọn hàm gì?

Thuộc tính cốt lõi của Spring Cloud Function là:

~~~properties
spring.cloud.function.definition=greet
~~~

Trong AWS Lambda, tài liệu Spring Cloud Function sử dụng biến môi trường:

~~~text
spring_cloud_function_definition=greet
~~~

Ở đây **greet** là **tên bean chức năng do Spring đăng ký**. Khi Lambda nhận invocation, **FunctionInvoker** dựa vào cấu hình definition, tìm hàm qua **FunctionCatalog** và áp dụng cơ chế chuyển đổi dữ liệu thích hợp.

~~~mermaid
flowchart LR
    A["AWS Lambda event"] --> B["FunctionInvoker"]
    C["spring_cloud_function_definition"] --> B
    B --> D["FunctionCatalog"]
    D --> E["Bean hoặc composition được chọn"]
    E --> F["Output / side effect"]
~~~

Biến này trả lời câu hỏi **chạy logic nào?**, nhưng **không** tự quyết định những việc sau:

- AWS Lambda có nạp được class **FunctionInvoker** từ JAR hay không.
- Lớp **@SpringBootApplication** nào được dùng để tạo context.
- Payload của API Gateway, SQS hoặc direct invocation có đúng schema hay không.
- Exception từ Function sẽ được retry/dead-letter thế nào.
- Lambda có IAM permission để đọc/ghi dịch vụ AWS hay không.

Đặt definition đúng là **một bước của đường triển khai**, không phải cấu hình thay thế mọi adapter và hạ tầng.

## 2. Phân biệt handler, main class, bean và tên Lambda

Giả sử có Spring application **example.lambda.MultiFunctionApplication**, bean **greet** và Lambda AWS **greeting-lambda**.

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Tên resource AWS Lambda | **greeting-lambda** | Định danh function ở AWS |
| Java handler | **org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest** | Điểm vào của AWS runtime |
| Spring application class | **example.lambda.MultiFunctionApplication** | Lớp cấu hình giúp tạo Spring ApplicationContext |
| Spring function bean | **greet** | Hàm nghiệp vụ trong FunctionCatalog |
| Spring function definition | **greet** | Tên bean được chọn cho invocation |

Ví dụ cấu hình:

~~~text
Handler = org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
MAIN_CLASS = example.lambda.MultiFunctionApplication
spring_cloud_function_definition = greet
~~~

**Không dùng greet làm AWS handler.** AWS handler phải trỏ đến class/method theo hợp đồng Java Lambda. **Không dùng FunctionInvoker làm MAIN_CLASS.** MAIN_CLASS chỉ lớp Spring Boot application. **Không dùng MultiFunctionApplication làm definition**, trừ khi ứng dụng thực sự đăng ký bean chức năng có tên đó.

Handler chung của adapter AWS có thể giữ nguyên trong nhiều Lambda; lựa chọn bean nằm ở **spring_cloud_function_definition**.

## 3. Ví dụ có nhiều bean chức năng

Đoạn mã Java 17+ dưới đây tạo năm bean để so sánh các kiểu đầu vào/đầu ra. Tệp **src/main/java/example/lambda/MultiFunctionApplication.java**:

~~~java
package example.lambda;

import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MultiFunctionApplication {

    private static final Logger log =
        LoggerFactory.getLogger(MultiFunctionApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(MultiFunctionApplication.class, args);
    }

    public record GreetingRequest(String name) {}
    public record GreetingResponse(String message) {}

    @Bean("greet")
    Function<GreetingRequest, GreetingResponse> greet() {
        return request -> {
            if (request == null
                    || request.name() == null
                    || request.name().isBlank()) {
                throw new IllegalArgumentException("Name is required");
            }
            return new GreetingResponse(
                "Xin chào, " + request.name().trim());
        };
    }

    @Bean("trimText")
    Function<String, String> trimText() {
        return input -> {
            if (input == null) {
                throw new IllegalArgumentException("Input is required");
            }
            return input.trim();
        };
    }

    @Bean("uppercaseText")
    Function<String, String> uppercaseText() {
        return input -> {
            if (input == null) {
                throw new IllegalArgumentException("Input is required");
            }
            return input.toUpperCase(Locale.ROOT);
        };
    }

    @Bean("heartbeat")
    Supplier<String> heartbeat() {
        return () -> "ready";
    }

    @Bean("auditGreeting")
    Consumer<GreetingRequest> auditGreeting() {
        return request -> {
            if (request == null
                    || request.name() == null
                    || request.name().isBlank()) {
                throw new IllegalArgumentException("Name is required");
            }
            log.info("Received a valid greeting event");
        };
    }
}
~~~

Các bean đều đăng ký trong Spring context nhưng có hợp đồng khác nhau:

| Bean | Kiểu | Kết quả / tác dụng |
| --- | --- | --- |
| **greet** | Function<GreetingRequest, GreetingResponse> | Tạo thông điệp chào |
| **trimText** | Function<String, String> | Loại khoảng trắng hai đầu |
| **uppercaseText** | Function<String, String> | Chuyển thành chữ hoa |
| **heartbeat** | Supplier<String> | Trả chuỗi trạng thái không nhận input nghiệp vụ |
| **auditGreeting** | Consumer<GreetingRequest> | Ghi log, không tạo output nghiệp vụ |

**auditGreeting** chỉ minh họa side effect. Trong sản phẩm thật, không ghi dữ liệu cá nhân hoặc payload nhạy cảm trực tiếp vào log. Nếu Consumer ghi database, cần thiết kế idempotency, transaction và retry phù hợp.

### Tên bean có phải tên phương thức Java không?

Trong ví dụ, **@Bean("greet")** quyết định tên bean. Khi một phương thức **@Bean** không ghi tên tường minh, Spring thường dùng tên phương thức làm tên bean. Nếu đổi annotation thành **@Bean("sendGreeting")** nhưng method vẫn là **greet()**, definition phải dùng **sendGreeting**, không phải **greet**.

Tên bean được dùng trong cấu hình deployment nên ổn định. Việc refactor và đổi tên bean có thể làm tất cả Lambda đang tham chiếu definition cũ bị lỗi.

## 4. Chọn Function theo tên

Khi Lambda đặt:

~~~text
spring_cloud_function_definition=greet
~~~

một **direct invocation** có thể gửi JSON object:

~~~json
{
  "name": "Lan"
}
~~~

Kết quả nghiệp vụ:

~~~json
{
  "message": "Xin chào, Lan"
}
~~~

Nếu thay definition thành:

~~~text
spring_cloud_function_definition=uppercaseText
~~~

thì input phù hợp với bean **Function<String,String>** có thể là **JSON string**:

~~~json
"hello"
~~~

Output tương ứng mang nội dung **HELLO**. Cần xác minh hình thức serialize chính xác trong adapter/runtime đang dùng.

**Definition đúng không bảo đảm payload đúng.** Nếu caller vẫn gửi object **{"name":"Lan"}** trong khi Function nhận String, adapter có thể gặp lỗi conversion hoặc dữ liệu không như kỳ vọng. Thay definition là thay đổi **hợp đồng input/output**, phải kiểm thử caller và trigger tương ứng.

## 5. Supplier và Consumer cũng được chọn theo definition

Spring Cloud Function có ba mô hình chính:

- **Supplier<T>**: **get()**, không có đối số nghiệp vụ, tạo dữ liệu.
- **Function<T,R>**: **apply(T)**, nhận T, trả R.
- **Consumer<T>**: **accept(T)**, nhận T, trả void.

Với ví dụ:

~~~text
spring_cloud_function_definition=heartbeat
~~~

Lambda chọn bean **Supplier<String>**. Runtime vẫn có invocation event, nhưng **Supplier** không dùng input nghiệp vụ như Function.

Với:

~~~text
spring_cloud_function_definition=auditGreeting
~~~

Lambda chọn bean **Consumer<GreetingRequest>**, xử lý payload rồi không trả một **GreetingResponse**.

**Đừng kỳ vọng Consumer tự có response DTO.** Nếu yêu cầu có kết quả xác nhận, cân nhắc **Function<T,ProcessingResult>**, một trạng thái bền vững hoặc event phản hồi theo hợp đồng. Cách adapter biểu diễn đầu ra rỗng của Consumer cần được kiểm chứng cho từng trigger.

## 6. Chọn composition bằng dấu |

Definition không chỉ nhận một tên bean. Spring Cloud Function cho phép ghép các hàm tương thích bằng **|**.

~~~text
spring_cloud_function_definition=trimText|uppercaseText
~~~

Pipeline:

~~~mermaid
flowchart LR
    A["Input String"] --> B["trimText"]
    B --> C["Trimmed String"]
    C --> D["uppercaseText"]
    D --> E["Uppercase String"]
~~~

Với input:

~~~json
"  item-a  "
~~~

đầu ra mong muốn có giá trị **ITEM-A**.

**Điều kiện:** kiểu output của hàm trước phải tương thích input của hàm sau. **greet** trả **GreetingResponse**, còn **uppercaseText** nhận String; không tự ghép **greet|uppercaseText** nếu không có bước chuyển đổi có chủ đích.

### Quote chuỗi composition trong YAML và shell

~~~yaml
Environment:
  Variables:
    spring_cloud_function_definition: "trimText|uppercaseText"
~~~

Trong shell, ký tự **|** thường biểu diễn pipe giữa hai command. Vì vậy khi đưa definition trực tiếp vào command line, cần quote đúng hoặc dùng file JSON/YAML để khỏi bị shell phân tích sai. **Đặt quote không làm thay đổi thứ tự composition**, chỉ bảo toàn chuỗi nguyên vẹn.

## 7. Dùng chung một JAR cho nhiều Lambda

Khi cả hai bean **greet** và **trimText/uppercaseText** cùng nằm trong một ứng dụng, có thể dùng chung shaded JAR:

~~~text
Artifact: multi-function-aws.jar
  + MultiFunctionApplication
  + FunctionInvoker
  + greet
  + trimText
  + uppercaseText
  + heartbeat
  + auditGreeting
~~~

Hai Lambda AWS riêng:

~~~text
AWS Lambda "greeting-lambda"
  Handler: FunctionInvoker
  MAIN_CLASS: example.lambda.MultiFunctionApplication
  spring_cloud_function_definition: greet

AWS Lambda "normalization-lambda"
  Handler: FunctionInvoker
  MAIN_CLASS: example.lambda.MultiFunctionApplication
  spring_cloud_function_definition: trimText|uppercaseText
~~~

Hai function có thể dùng **memory, timeout, IAM policy, trigger và concurrency limit** khác nhau. Bean **greet** và composition vẫn là logic Java có thể được tái sử dụng qua HTTP hoặc event binder với adapter phù hợp.

**Dùng chung JAR không có nghĩa dùng chung bộ nhớ singleton.** Mỗi Lambda execution environment có thể tạo Spring context riêng; biến static hoặc cache in-memory không được đồng bộ giữa hai Lambda hoặc giữa các replica.

## 8. AWS Lambda Console: nhập key và value

Trong Lambda Console, sau khi upload đúng Java JAR và đặt handler adapter:

1. Mở Lambda cần cấu hình, ví dụ **greeting-lambda**.
2. Tới khu vực cấu hình **Environment variables**.
3. Thêm key **spring_cloud_function_definition**, value **greet**.
4. Kiểm tra **Handler** vẫn là **FunctionInvoker**, và **MAIN_CLASS** hoặc **Start-Class** tìm đúng Spring application.
5. Lưu cấu hình, invoke bằng payload của bean đã chọn và kiểm tra logs.

~~~text
Handler:
  org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest

Environment variables:
  MAIN_CLASS = example.lambda.MultiFunctionApplication
  spring_cloud_function_definition = greet
~~~

Tên menu có thể khác theo phiên bản AWS Console, nhưng các trường có ý nghĩa riêng: **Handler** là điểm vào runtime, **MAIN_CLASS** giúp khởi tạo Spring context, **definition** chỉ định bean hoặc pipeline.

Các environment variables thuộc cấu hình của **từng Lambda function**, không phải cấu hình chung của cả tài khoản hoặc của artifact JAR.

## 9. AWS SAM: cùng JAR, hai definition

Ví dụ **template.yaml**:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  GreetingLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
      CodeUri: target/multi-function-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.MultiFunctionApplication
          spring_cloud_function_definition: greet

  NormalizeLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
      CodeUri: target/multi-function-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.MultiFunctionApplication
          spring_cloud_function_definition: "trimText|uppercaseText"
~~~

**Đây là cấu hình minh họa**, không phải deployment artifact hoàn chỉnh:

- **CodeUri** phải trỏ đến shaded JAR có thật sau build.
- Runtime **java21** chỉ thích hợp nếu Java bytecode và Spring dependencies tương thích.
- Handler phải được xác nhận theo adapter, Lambda runtime và công cụ deploy.
- MemorySize/Timeout chỉ là ví dụ; IAM và trigger phải được thiết kế riêng.
- Khi dùng IaC, sửa definition trong source YAML/Terraform rồi deploy lại, tránh cấu hình drift do chỉnh tay.

Spring Cloud Function AWS có thể dùng handler **FunctionInvoker** ở dạng class-only trong những ví dụ runtime. Bài này dùng dạng **FunctionInvoker::handleRequest** để minh họa rõ entrypoint; không thay bằng tên bean.

### Tại sao IAM nên tách riêng?

Nếu **normalization-lambda** chỉ xử lý chuỗi nhưng **greeting-lambda** được mở rộng để truy cập cơ sở dữ liệu, không nên cấp IAM quyền đọc database cho cả hai function chỉ vì cùng JAR. **spring_cloud_function_definition** chọn logic nhưng không tự thay execution role hay phân quyền theo bean.

## 10. AWS CLI: kiểm tra và cập nhật đúng cách

Đọc cấu hình Lambda đã triển khai:

~~~bash
aws lambda get-function-configuration \
  --function-name greeting-lambda
~~~

Trong output, đối chiếu:

~~~text
Handler
Runtime
Environment.Variables.MAIN_CLASS
Environment.Variables.spring_cloud_function_definition
~~~

Có thể cập nhật biến môi trường bằng AWS CLI, nhưng **update-function-configuration với Environment.Variables có thể thay thế toàn bộ map đã khai báo**, không chỉ thêm một key. Nếu chỉ gửi definition mà quên MAIN_CLASS hoặc các biến cũ, cấu hình có thể hỏng.

Ví dụ tệp **lambda-env.json** dùng trong bài thực hành:

~~~json
{
  "Variables": {
    "MAIN_CLASS": "example.lambda.MultiFunctionApplication",
    "spring_cloud_function_definition": "greet"
  }
}
~~~

Lệnh minh họa:

~~~bash
aws lambda update-function-configuration \
  --function-name greeting-lambda \
  --environment file://lambda-env.json
~~~

**Tệp lambda-env.json chỉ là ví dụ để người học tạo trong dự án riêng, không phải file được ghi trong bước soạn bài này.** Trong hệ thống thực, hãy đọc cấu hình hiện tại và giữ lại đầy đủ các biến cần thiết trước khi cập nhật; chờ trạng thái update hoàn tất rồi kiểm tra giá trị mới.

Nếu tổ chức quản lý Lambda bằng SAM/CloudFormation/Terraform, **ưu tiên cập nhật nguồn IaC** thay vì sửa tay qua CLI làm lệch cấu hình.

## 11. application.yml và biến môi trường: nguồn nào có hiệu lực?

Trong ứng dụng Spring, default có thể viết:

~~~yaml
spring:
  cloud:
    function:
      definition: greet
~~~

Trong Lambda, có thể đặt:

~~~text
spring_cloud_function_definition=trimText|uppercaseText
~~~

Theo cơ chế externalized configuration thông thường của Spring Boot, environment variables có thể override những giá trị trong **application.yml** được đóng gói. Tuy nhiên, thứ tự thực tế còn phụ thuộc nguồn cấu hình khác như system property, command-line argument, profile hoặc property source tùy biến.

Vì vậy, với một Lambda quan trọng:

- Định nghĩa các bean trong source code.
- Dùng environment variable ở môi trường triển khai để chọn bean/pipeline.
- Chỉ giữ default trong application.yml nếu có mục đích local/test rõ ràng.
- Kiểm tra **effective definition** thay vì đoán dựa vào một file.
- Tránh có nhiều nơi ghi những giá trị definition trái nhau mà không có quy trình kiểm soát.

Tên **spring_cloud_function_definition** được hướng dẫn dùng ở adapter AWS; không mặc định biến thể chữ hoa/lowercase bất kỳ đều được mọi lớp tích hợp xử lý giống nhau. Nếu chuẩn đặt tên của hệ thống khác, cần kiểm thử binding thực tế.

## 12. Lambda version và alias có thể giữ cấu hình khác

Cấu hình environment thuộc về **Lambda function version**. Một published version thường lưu snapshot code/configuration và không được sửa như phần cấu hình chưa publish. Vì thế, khi muốn đổi definition đang phục vụ production qua alias, nên:

1. Sửa environment trên cấu hình có thể cập nhật theo quy trình deploy.
2. Chạy test với payload tương ứng.
3. Publish/deploy version mới khi cần.
4. Kiểm tra alias đang trỏ tới đúng version.
5. Chuyển traffic có kiểm soát và chuẩn bị rollback.

Một Lambda alias trỏ version cũ có thể tiếp tục dùng **greet** trong khi cấu hình hiện tại đã được sửa thành **uppercaseText**. Điều này giải thích trường hợp nhìn Console thấy definition mới nhưng invocation qua alias lại chạy hàm cũ.

Không gọi nhầm **$LATEST** khi bạn muốn kiểm thử traffic trên production alias. Ghi rõ function name, qualifier/version/alias trong kế hoạch thử nghiệm.

## 13. Vì sao cấu hình rõ ràng tốt hơn chọn mặc định?

Nếu chỉ có một bean chức năng, Spring Cloud Function có thể có cơ chế phát hiện/chọn hàm mặc định. Nhưng thêm bean mới, thay cấu hình hoặc refactor có thể khiến việc chọn hàm trở nên khó đoán.

Với Lambda được triển khai để phục vụ một nghiệp vụ xác định, đặt **spring_cloud_function_definition** tường minh giúp:

1. **Dễ kiểm toán**: đọc config là biết tên logic đang chạy.
2. **Độc lập mã nguồn**: nhiều Lambda dùng cùng JAR nhưng chọn các hàm khác nhau.
3. **Ít bất ngờ** khi ứng dụng có thêm Supplier/Function/Consumer.
4. **Dễ kiểm thử** tên bean qua FunctionCatalog trước deploy.
5. **Dễ rollback** theo version/configuration đã biết.

Không dựa vào thứ tự khai báo **@Bean** trong code, tên file Java hoặc tên Lambda resource để suy ra bean được chọn.

## 14. FunctionCatalog: kiểm thử tên trước khi triển khai

Một lớp Spring có thể nhận **FunctionCatalog** bằng constructor injection:

~~~java
package example.lambda;

import java.util.function.Function;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class GreetingInvoker {

    private final FunctionCatalog catalog;

    public GreetingInvoker(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public MultiFunctionApplication.GreetingResponse greet(
            MultiFunctionApplication.GreetingRequest request) {

        Function<
            MultiFunctionApplication.GreetingRequest,
            MultiFunctionApplication.GreetingResponse> fn =
                catalog.lookup("greet");

        if (fn == null) {
            throw new IllegalStateException(
                "Function 'greet' not registered");
        }

        return fn.apply(request);
    }
}
~~~

FunctionCatalog có thể trả wrapper phục vụ conversion, composition và message handling. Vì thế không giả định object tra cứu luôn là cùng instance/class với bean implementation.

Có thể tra cứu một composition với hai Function String:

~~~java
Function<String, String> pipeline =
    catalog.lookup("trimText|uppercaseText");

if (pipeline == null) {
    throw new IllegalStateException("Pipeline not found");
}

String output = pipeline.apply("  item-a  ");
// "ITEM-A"
~~~

Đoạn thứ hai minh họa ngữ cảnh đã có **FunctionCatalog catalog** được Spring inject; không phải một file Java độc lập.

Nếu catalog không tìm được **greet**, vấn đề có thể do tên bean sai, lớp cấu hình không nằm trong component scan hoặc dependency Spring Cloud Function chưa được thiết lập đúng.

## 15. Test trực tiếp Java không chứng minh Lambda chọn đúng definition

### 15.1. Unit test logic

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class MultiFunctionApplicationTest {

    private final MultiFunctionApplication app =
        new MultiFunctionApplication();

    @Test
    void greetReturnsExpectedMessage() {
        var response = app.greet().apply(
            new MultiFunctionApplication.GreetingRequest(" Lan ")
        );
        assertEquals("Xin chào, Lan", response.message());
    }

    @Test
    void greetRejectsBlankInput() {
        assertThrows(IllegalArgumentException.class,
            () -> app.greet().apply(
                new MultiFunctionApplication.GreetingRequest(" ")
            ));
    }

    @Test
    void twoFunctionsCanBeComposed() {
        String trimmed = app.trimText().apply("  item-a  ");
        String upper = app.uppercaseText().apply(trimmed);
        assertEquals("ITEM-A", upper);
    }
}
~~~

Các test trên kiểm tra nghiệp vụ nhưng không xác minh bean registration hay biến môi trường Lambda.

### 15.2. Integration test Spring FunctionCatalog

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = MultiFunctionApplication.class)
class FunctionCatalogSelectionTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void namedFunctionsExist() {
        assertNotNull(catalog.lookup("greet"));
        assertNotNull(catalog.lookup("trimText"));
        assertNotNull(catalog.lookup("uppercaseText"));
    }

    @Test
    void compositionRunsInOrder() {
        Function<String, String> chain =
            catalog.lookup("trimText|uppercaseText");

        assertNotNull(chain);
        assertEquals("ITEM-A", chain.apply("  item-a  "));
    }
}
~~~

Test tích hợp chứng minh context có bean và catalog tìm được chúng. Muốn xác minh environment variable của **một Lambda đã triển khai**, phải kiểm tra configuration/version thực tế rồi gọi invocation tương ứng.

### 15.3. Kiểm tra artifact

AWS Lambda Java runtime phải nạp được **FunctionInvoker** và main class từ deployable JAR:

~~~bash
jar tf target/multi-function-1.0.0-aws.jar |
  grep 'FunctionInvoker.class'

jar tf target/multi-function-1.0.0-aws.jar |
  grep 'MultiFunctionApplication.class'
~~~

Đây là lệnh ví dụ, không được chạy như một phần STEP 4 của bài soạn. Nếu artifact thiếu handler, sửa dependency/packaging chứ không sửa definition.

## 16. Kiểm thử AWS Lambda sau deploy

Ví dụ invocation tới Lambda chọn **greet**:

~~~bash
aws lambda invoke \
  --function-name greeting-lambda \
  --cli-binary-format raw-in-base64-out \
  --payload '{"name":"Lan"}' \
  response.json

cat response.json
~~~

Với Lambda chọn **trimText|uppercaseText**:

~~~bash
aws lambda invoke \
  --function-name normalization-lambda \
  --cli-binary-format raw-in-base64-out \
  --payload '"  item-a  "' \
  response.txt

cat response.txt
~~~

Lệnh chỉ hướng dẫn cách thử trong môi trường AWS đã có credentials và quyền invoke. **API gọi Lambda thành công không đồng nghĩa Function không lỗi**: kiểm tra metadata như **FunctionError**, nội dung response và CloudWatch logs.

Một checklist kiểm tra kết quả:

- Đang gọi đúng Lambda, version hoặc alias chưa?
- Environment có **spring_cloud_function_definition** đúng chưa?
- Handler có trỏ **FunctionInvoker** và main class có đúng chưa?
- Input event có hợp đồng tương ứng với bean được chọn chưa?
- Có lỗi conversion, validation, exception hay timeout không?
- Output thực tế có khớp với logic được chọn không?

## 17. Event envelope không được đổi chỉ bằng definition

Direct invocation nhận JSON object như **{"name":"Lan"}** khác với sự kiện do API Gateway, SQS, S3 hoặc EventBridge phát.

| Nguồn | Nội dung thường thấy | Cần xử lý |
| --- | --- | --- |
| Direct invoke | Payload caller tự gửi | Deserialize sang DTO |
| API Gateway | **body**, headers, requestContext | Đọc body và ánh xạ response HTTP |
| SQS | **Records** và có thể nhiều message | Batch, retry, partial failure |
| S3 | Bucket, key, event metadata | Đọc object, quyền truy cập, idempotency |
| EventBridge | **source**, **detail-type**, **detail** | Ánh xạ event detail sang hợp đồng |

**spring_cloud_function_definition** chỉ chọn hàm; nó **không** bóc mọi loại event envelope thành DTO nghiệp vụ. Nếu Function nhận **GreetingRequest** nhưng trigger thực tế gửi **SQSEvent**, cần kiểu input hoặc adapter chuyển đổi phù hợp, thay vì chỉ đổi tên bean trong environment.

Với Consumer có tác dụng phụ, phải thiết kế retry và idempotency vì Lambda/broker có thể gửi lại cùng event. Một environment variable không thể đảm bảo exactly-once.

## 18. Tình huống lỗi và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Lambda không thấy **FunctionInvoker** | Sai JAR hoặc thiếu adapter AWS | Kiểm tra shaded JAR/handler |
| Lambda không tìm được main class | **MAIN_CLASS** hoặc Start-Class sai | Kiểm tra tên class đầy đủ, manifest |
| Catalog không tìm được bean | Definition sai hoặc bean không được đăng ký | Đối chiếu @Bean và lookup |
| Lambda chạy bean khác mong đợi | Env trên version/alias khác | Xem get-function-configuration với qualifier đúng |
| Composition lỗi | Một tên sai hoặc kiểu dữ liệu không tương thích | Test lookup("a|b") và T/R |
| Dấu **|** bị shell xử lý như pipe | Không quote giá trị | Dùng quote hoặc file JSON/YAML |
| CLI update làm mất biến khác | Variables map bị thay thế | Đọc cấu hình trước, gửi map đầy đủ |
| IaC deploy làm mất thay đổi Console | Drift giữa Console và IaC | Sửa cấu hình nguồn IaC |
| JSON parse thất bại | Payload không khớp generic input | Kiểm tra schema và adapter |
| Function được gọi nhưng ném exception | Dữ liệu sai hoặc lỗi nghiệp vụ | Phân loại validation/business errors |
| Supplier không nhận input như Function | Supplier không có tham số nghiệp vụ | Thiết kế invocation đúng |
| Consumer không có DTO output | Consumer trả void | Dùng Function nếu cần kết quả |
| Trigger SQS giao lại sự kiện | Retry/redelivery | Dùng eventId, unique constraint, DLQ theo chính sách |
| IAM AccessDenied | Role không đủ quyền | Cấp permission tối thiểu phù hợp |
| Phiên bản Java không tương thích | Bytecode/runtime lệch | Đồng bộ compiler release và Runtime |

**Thứ tự chẩn đoán hữu ích:** handler có nạp được không → Spring context có khởi tạo không → FunctionCatalog có tìm đúng bean không → converter có hiểu event không → logic có thành công không.

## 19. Bảo mật và vận hành khi đổi definition

Đổi definition có thể làm thay đổi chức năng của Lambda dù JAR không đổi. Vì vậy nó phải được xem như **thay đổi hành vi triển khai**:

- Quản lý qua review và Infrastructure as Code.
- Kiểm thử staging với input/output đúng hợp đồng.
- Dùng version và alias khi muốn rollout/rollback có kiểm soát.
- Theo dõi log, lỗi, cold start, duration và metric nghiệp vụ.
- Không dùng definition như cơ chế phân quyền thay IAM/authorization.
- Không cho caller không tin cậy tự chọn bean nhạy cảm thông qua routing không kiểm soát.
- Không ghi credentials hoặc raw secrets vào environment variable hoặc log.

Một execution environment Lambda có thể tái sử dụng Spring singleton, nhưng nhiều instance không chia sẻ bộ nhớ. Không lưu trạng thái bền vững hay idempotency key chỉ trong field của Function bean nếu workload cần an toàn khi scale/restart.

## 20. Bài tập vận dụng

**Bài tập 1 — Phân biệt ba tên.** Một ứng dụng có lớp **com.shop.PricingApplication**, bean **@Bean("calculatePrice")** và Lambda tên **price-prod**. Hãy đặt đúng Handler, MAIN_CLASS và spring_cloud_function_definition, rồi giải thích vì sao không được tráo chúng.

**Bài tập 2 — Hai Lambda dùng chung JAR.** Tạo hai bean **reverseText** và **uppercaseText**. Viết một template SAM tạo hai Lambda cùng Handler/CodeUri/MAIN_CLASS nhưng definition khác nhau. Mỗi Lambda cần test event gì?

**Bài tập 3 — Composition.** Với **trimText** và **uppercaseText**, hãy cấu hình definition có dấu **|**, gửi một JSON string chứa khoảng trắng rồi chứng minh output cuối bằng unit test và FunctionCatalog test.

**Bài tập 4 — Sai contract.** Lambda chọn **greet** có input **GreetingRequest**, nhưng API Gateway gửi event chứa **body**. Phân biệt lỗi do definition với lỗi chuyển đổi envelope và thiết kế cách ánh xạ đúng.

**Bài tập 5 — AWS CLI.** Một Lambda có ba environment variables, trong đó có MAIN_CLASS và definition. Lập kế hoạch đổi definition mà không làm mất biến còn lại; sau đó dùng get-function-configuration để xác minh.

**Bài tập 6 — Version/alias.** Cấu hình mới chọn **uppercaseText** nhưng alias production vẫn trỏ version chọn **greet**. Nêu cách kiểm tra đúng version, rollout và rollback.

**Bài tập 7 — Supplier và Consumer.** Tạo **Supplier<String> heartbeat** và **Consumer<Event> auditEvent**, triển khai bằng hai Lambda chọn definition tương ứng. Giải thích vì sao một hàm không có input nghiệp vụ, hàm còn lại không có output nghiệp vụ.

**Bài tập 8 — Event retry.** Lambda chọn Consumer ghi database, nhận lại cùng eventId từ SQS. Đề xuất idempotency key, unique constraint, retry/dead-letter và giải thích vì sao lựa chọn bean đúng vẫn chưa đủ.

### Ghi nhớ

- **spring_cloud_function_definition** chọn **bean chức năng hoặc composition** của Spring Cloud Function; nó không phải AWS handler hay Spring main class.
- **FunctionInvoker** vẫn là entrypoint của Lambda; **MAIN_CLASS/Start-Class** giúp xác định ứng dụng Spring; **FunctionCatalog** tìm logic theo definition.
- Một **shaded JAR** có thể dùng cho nhiều Lambda với definition, IAM, trigger, timeout và version riêng.
- Composition dùng **|** theo thứ tự; cần quote khi đưa vào shell/YAML và bảo đảm kiểu dữ liệu các bước tương thích.
- Đổi definition có thể đổi input/output contract. Cần kiểm tra event envelope, effective environment, Lambda version/alias và test sau deploy.
- Quản lý cấu hình qua IaC và chuẩn bị rollback để thay đổi logic Lambda có kiểm soát.

### Tài liệu tham khảo

- [Spring Cloud Function — AWS Lambda](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): FunctionInvoker, biến môi trường, definition, routing.
- [Spring Cloud Function — Reference](https://docs.spring.io/spring-cloud-function/reference/): FunctionCatalog, programming model, composition.
- [AWS Lambda — Environment variables](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html): môi trường và version.
- [AWS CLI — update-function-configuration](https://docs.aws.amazon.com/cli/latest/reference/lambda/update-function-configuration.html): cập nhật environment variables.
