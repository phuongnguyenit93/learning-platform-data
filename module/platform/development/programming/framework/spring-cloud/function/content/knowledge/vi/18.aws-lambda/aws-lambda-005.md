# Định tuyến nhiều hàm qua một Lambda hoặc nhiều Lambda độc lập

Một dự án **SPRING_CLOUD_FUNCTION** có thể chứa nhiều bean **Supplier<T>**, **Function<T, R>** và **Consumer<T>**, nhưng khi triển khai trên **AWS Lambda** cần quyết định cách ánh xạ các bean đó thành tài nguyên AWS thực tế. Có hai hướng chính: **một Lambda nhận nhiều loại yêu cầu rồi định tuyến tới hàm thích hợp**, hoặc **nhiều Lambda độc lập, mỗi Lambda cố định một hàm hay pipeline**. Cả hai đều có thể dùng **FunctionInvoker** và **FunctionCatalog**, nhưng khác nhau về nơi đưa ra quyết định định tuyến, khả năng cách ly, quyền IAM, concurrency, chi phí vận hành và hợp đồng dữ liệu.

Bài thuộc chương **AWS Lambda**. Sau bài học, bạn có thể giải thích ba chiến lược triển khai, cấu hình **spring_cloud_function_definition**, dùng **RoutingFunction/functionRouter**, Message headers hoặc **MessageRoutingCallback** cho trường hợp cần định tuyến từng invocation, viết một lớp điều hợp an toàn cho AWS event, xây template AWS SAM và kiểm thử từng đường đi. Mục tiêu là giữ logic nghiệp vụ có thể tái sử dụng độc lập với HTTP, sự kiện hoặc môi trường serverless.

## 1. Ba hình thức triển khai cần phân biệt

Cụm từ “nhiều hàm” có thể nói về **bean Java**, **AWS Lambda function** hoặc cả hai. Đây là ba kiến trúc cụ thể:

| Kiến trúc | Lambda resource | JAR/code package | Quyết định chọn hàm |
| --- | --- | --- | --- |
| **A. Một Lambda, định tuyến động** | Một | Một JAR có nhiều bean | Theo từng invocation, bằng router hoặc lớp điều hợp |
| **B. Nhiều Lambda, cùng JAR** | Nhiều | Cùng một JAR chứa các bean | Mỗi Lambda chọn cố định bằng môi trường |
| **C. Nhiều Lambda, JAR riêng** | Nhiều | Mỗi Lambda có artifact riêng | Chọn trong từng ứng dụng/định nghĩa riêng |

~~~mermaid
flowchart TB
    S["Một codebase có các Function bean"] --> A["A: Một Lambda duy nhất"]
    S --> B["B: Nhiều Lambda cùng JAR"]
    S --> C["C: Nhiều Lambda/JAR độc lập"]
    A --> A1["Router chọn bean theo event"]
    B --> B1["Env var cố định cho mỗi Lambda"]
    C --> C1["Mỗi artifact chứa phần cần thiết"]
~~~

Hình thức A phù hợp khi các nghiệp vụ **liên quan chặt chẽ**, dùng chung quyền và cấu hình hạ tầng. B phù hợp khi các nghiệp vụ dùng chung mã nhưng cần **IAM, event source mapping, timeout hoặc khả năng scale riêng**. C phù hợp khi từng nghiệp vụ do các nhóm khác nhau quản lý, có chu kỳ phát hành và bộ dependency riêng.

**Một JAR chứa nhiều bean không đồng nghĩa chỉ được tạo một Lambda.** Ngược lại, một AWS Lambda resource không tự biết phải gọi bean nào trong JAR nếu thiếu definition hoặc quy tắc routing phù hợp.

## 2. Đường đi chung với FunctionInvoker

Dù chọn A hay B, cách tích hợp phổ biến là dùng handler do **spring-cloud-function-adapter-aws** cung cấp.

~~~text
AWS Lambda handler:
  org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest

Spring Boot main class:
  example.lambda.RoutingLambdaApplication

Tên bean trong FunctionCatalog:
  uppercase, lowercase, reverse, dispatchText, functionRouter
~~~

**Handler** là điểm vào Lambda runtime; **main class** giúp khởi tạo Spring application context; **tên bean** xác định logic bên trong context. Không dùng **uppercase** làm handler AWS, cũng không dùng tên **FunctionInvoker** làm tên bean nghiệp vụ.

~~~mermaid
sequenceDiagram
    participant AWS as AWS runtime
    participant INV as FunctionInvoker
    participant CAT as FunctionCatalog
    participant F as Function bean

    AWS->>INV: handleRequest(event, Context)
    INV->>CAT: lookup(definition / router)
    CAT-->>INV: wrapped Function
    INV->>F: apply(input)
    F-->>INV: output
    INV-->>AWS: serialized result
~~~

Khi có nhiều bean, hãy chọn tường minh một definition hoặc một router. Không dựa vào thứ tự các phương thức **@Bean** trong mã nguồn. Cơ chế fallback khi không có definition có thể khác theo phiên bản framework và số lượng bean.

## 3. Ví dụ Spring Boot: các phép biến đổi tái sử dụng

Ta tạo ba hàm xử lý chuỗi **uppercase**, **lowercase**, **reverse**, rồi thêm một bean **dispatchText** nhận một envelope chứa trường **operation** và chọn hàm bằng allowlist. Ví dụ sử dụng Java 17+.

Tệp **src/main/java/example/lambda/RoutingLambdaApplication.java**:

~~~java
package example.lambda;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class RoutingLambdaApplication {

    public static void main(String[] args) {
        SpringApplication.run(RoutingLambdaApplication.class, args);
    }

    // Hợp đồng riêng của Lambda làm gateway.
    public record TextCommand(
        String operation,
        String value
    ) {}

    public record TextResult(
        String operation,
        String value
    ) {}

    @Bean("uppercase")
    Function<String, String> uppercase() {
        return text -> text.toUpperCase(Locale.ROOT);
    }

    @Bean("lowercase")
    Function<String, String> lowercase() {
        return text -> text.toLowerCase(Locale.ROOT);
    }

    @Bean("reverse")
    Function<String, String> reverse() {
        return text -> new StringBuilder(text).reverse().toString();
    }

    // Đây là router tường minh của ứng dụng, KHÔNG PHẢI
    // RoutingFunction mặc định của Spring Cloud Function.
    @Bean("dispatchText")
    Function<TextCommand, TextResult> dispatchText(
            @Qualifier("uppercase") Function<String, String> upper,
            @Qualifier("lowercase") Function<String, String> lower,
            @Qualifier("reverse") Function<String, String> reversing) {

        return request -> {
            if (request == null
                    || request.operation() == null
                    || request.value() == null) {
                throw new IllegalArgumentException(
                    "operation and value are required");
            }

            String operation = request.operation()
                .trim().toLowerCase(Locale.ROOT);

            // Chỉ cho phép ba nghiệp vụ công khai.
            String result = switch (operation) {
                case "upper" -> upper.apply(request.value());
                case "lower" -> lower.apply(request.value());
                case "reverse" -> reversing.apply(request.value());
                default -> throw new IllegalArgumentException(
                    "Unsupported operation");
            };

            return new TextResult(operation, result);
        };
    }
}
~~~

Những điểm then chốt:

1. Ba bean **uppercase/lowercase/reverse** đều có hợp đồng **Function<String, String>** và có thể kiểm thử độc lập.
2. **dispatchText** là một **Function<TextCommand, TextResult>** khác; nó quyết định đường đi dựa trên input nghiệp vụ đã được chuyển đổi.
3. **@Qualifier** giúp Spring inject đúng ba bean có cùng generic type.
4. **switch** đóng vai trò một **allowlist**: người gọi chỉ chọn được ba operation được công khai, không truyền trực tiếp tên bean tùy ý vào catalog.
5. DTO input/output của gateway không phụ thuộc vào API Lambda hoặc HTTP.
6. Trong sản phẩm thật, quyền được phép thực hiện một operation cần được kiểm tra riêng; allowlist chỉ giới hạn tuyến, không thay cho authentication/authorization.

**Phân biệt:** ví dụ **dispatchText** là **router tự viết bằng Java**. Spring Cloud Function còn cung cấp **RoutingFunction** tên **functionRouter** để định tuyến dựa trên Message headers, application properties hoặc callback; đó là cơ chế thứ hai được giải thích ở phần sau.

## 4. Phương án A — một Lambda với router nghiệp vụ tường minh

Nếu các thao tác đều là xử lý chuỗi, dùng chung cấu hình, timeout và quyền, có thể triển khai **một AWS Lambda** nhận **TextCommand**.

~~~text
AWS Lambda: text-gateway
  Handler: FunctionInvoker
  MAIN_CLASS: example.lambda.RoutingLambdaApplication
  spring_cloud_function_definition: dispatchText
~~~

Một direct invocation gửi:

~~~json
{
  "operation": "upper",
  "value": "Hello Lambda"
}
~~~

Kết quả nghiệp vụ:

~~~json
{
  "operation": "upper",
  "value": "HELLO LAMBDA"
}
~~~

Cùng Lambda, request tiếp theo:

~~~json
{
  "operation": "reverse",
  "value": "abc-123"
}
~~~

cho:

~~~json
{
  "operation": "reverse",
  "value": "321-cba"
}
~~~

~~~mermaid
flowchart LR
    A["Lambda text-gateway"] --> B["dispatchText"]
    B --> C{"operation"}
    C -- "upper" --> D["uppercase"]
    C -- "lower" --> E["lowercase"]
    C -- "reverse" --> F["reverse"]
    D --> G["TextResult"]
    E --> G
    F --> G
~~~

Giá trị **spring_cloud_function_definition** ở đây là **dispatchText**, không thay đổi giữa các invocation. **Chính TextCommand.operation làm nhiệm vụ chọn hàm bên trong**. Đây là cách đơn giản và dễ kiểm thử cho một hợp đồng JSON thống nhất.

### Vì sao không dùng environment variable để đổi đường đi theo từng request?

Environment variable của Lambda là cấu hình ở cấp **function/version**, không phải tham số của một invocation. Nếu đặt:

~~~text
spring_cloud_function_definition=uppercase
~~~

thì function đó được chọn tĩnh ở cấp adapter theo cấu hình hiệu lực. Không nên cập nhật biến môi trường trên AWS trước mỗi request để chọn uppercase rồi lowercase; đó là thay đổi cấu hình triển khai, có độ trễ, ảnh hưởng đồng thời và không phù hợp routing theo request.

Một Lambda phục vụ nhiều hành động cần **routing động theo event hoặc metadata**, bằng lớp điều hợp như **dispatchText** hoặc cơ chế framework **functionRouter**.

## 5. Phương án A nâng cao — RoutingFunction của Spring Cloud Function

Spring Cloud Function đăng ký một router mặc định có tên:

~~~text
functionRouter
~~~

Lớp tương ứng là **RoutingFunction**, với hợp đồng tổng quát **Function<Object, Object>**. Router nhận một input kèm thông tin định tuyến rồi lựa chọn function definition cần gọi từ **FunctionCatalog**.

Các cách cung cấp chỉ dẫn routing gồm:

- **Message header** chứa key **spring.cloud.function.definition**, value là tên bean hoặc composition.
- **Message header** **spring.cloud.function.routing-expression**, dùng biểu thức Spring Expression Language (SpEL).
- **Application/system property**, thích hợp để chọn routing logic tĩnh.
- **MessageRoutingCallback**, một chiến lược tùy chỉnh được đăng ký thành Spring bean.

~~~mermaid
flowchart TD
    A["Incoming Message"] --> B["functionRouter"]
    C["Header / callback / property"] --> B
    B --> D{"Definition"}
    D --> E["uppercase"]
    D --> F["lowercase"]
    D --> G["reverse"]
~~~

Một điểm quan trọng: **FunctionInvoker** có thể mặc định chuyển sang **functionRouter** khi không có cách chọn một hàm đơn nhất, nhưng không nên coi điều này là thay thế cho thiết kế routing minh bạch. Với dự án có nhiều bean, hãy cấu hình chủ đích và test cách adapter phiên bản đang dùng xác định router.

### Test trực tiếp router bằng Message header

Có thể dùng **FunctionCatalog** để kiểm tra router độc lập với AWS:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest(classes = RoutingLambdaApplication.class)
class FrameworkRoutingTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void routePerMessageUsingHeader() {
        Function<Object, Object> router =
            catalog.lookup("functionRouter");

        assertNotNull(router);

        Message<String> message =
            MessageBuilder.withPayload("Hello")
                .setHeader(
                    "spring.cloud.function.definition",
                    "uppercase")
                .build();

        Object result = router.apply(message);

        // Kết quả có thể là payload thuần hoặc Message
        // tùy wrapper và đường tích hợp.
        Object value = result instanceof Message<?> output
            ? output.getPayload()
            : result;

        assertEquals("HELLO", value);
    }
}
~~~

Bài test là ví dụ cho **imperative Function** và **Message** có header định tuyến được thêm **tường minh**. Đầu vào của **functionRouter** không giống một Function nghiệp vụ có signature DTO cố định; có thể cần xác minh conversion và output wrapper theo phiên bản Spring Cloud Function cụ thể.

**Cảnh báo đặc biệt khi dùng AWS:** gửi JSON chứa trường có tên **headers** không đồng nghĩa adapter AWS sẽ tự biến trường đó thành **Spring MessageHeaders**. Việc chuyển API Gateway header, SQS message attribute hoặc field event thành header của Spring cần được **xác minh hoặc triển khai ở lớp điều hợp**. Nếu chưa có bước ánh xạ đáng tin cậy, cách **dispatchText** ở phần 4 cho direct invocation có contract rõ ràng hơn.

## 6. RoutingFunction với callback kiểm soát đường đi

**MessageRoutingCallback** cho phép mã ứng dụng quyết định tên hàm theo một **Message<?>**, thay vì tin trực tiếp tên bean do caller đưa vào.

Ví dụ đoạn cấu hình cho Spring Cloud Function thế hệ hiện hành, nơi callback trả về **String**:

~~~java
import org.springframework.cloud.function.context.MessageRoutingCallback;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration(proxyBeanMethods = false)
class TrustedRoutingConfiguration {

    @Bean
    MessageRoutingCallback trustedRouter() {
        return new MessageRoutingCallback() {
            @Override
            public String routingResult(Message<?> message) {
                Object action = message.getHeaders()
                    .get("trustedAction");

                if ("upper".equals(action)) {
                    return "uppercase";
                }
                if ("lower".equals(action)) {
                    return "lowercase";
                }
                if ("reverse".equals(action)) {
                    return "reverse";
                }
                throw new IllegalArgumentException(
                    "Unsupported trusted action");
            }
        };
    }
}
~~~

**Chỉ dùng ví dụ khi header trustedAction được tạo/kiểm soát bởi adapter hoặc tầng xác thực đáng tin cậy.** Đây là **đoạn cấu hình tùy chọn** để minh họa một hướng routing khác. Không nên thêm nó vào ứng dụng của phần 3 và kỳ vọng mọi test Message header **spring.cloud.function.definition** tiếp tục được ưu tiên như cũ: callback có mức ưu tiên cao hơn và có thể thay đổi kết quả routing.

**Lưu ý phiên bản API:** các bản Spring Cloud Function cũ có thể dùng chữ ký callback trả về **FunctionRoutingResult** thay vì String. Kiểm tra JavaDoc/source và ví dụ đúng phiên bản dependency được khóa trong build trước khi sao chép code callback.

### Tại sao cần kiểm soát route?

Nếu người gọi được phép truyền thẳng:

~~~text
spring.cloud.function.definition=deleteAllRecords
~~~

và **functionRouter** làm theo mà không có lớp xác thực, một bean nội bộ nhạy cảm có thể bị gọi ngoài ý định. Đây là nguy cơ **authorization**, không phải lỗi cú pháp.

Giải pháp: định nghĩa allowlist của những nghiệp vụ được phép expose; xác thực caller tại API Gateway hoặc tầng tin cậy; ánh xạ đường dẫn/action công khai tới tên bean nội bộ bằng mã hoặc cấu hình quản trị; không cho caller không tin cậy tùy ý chỉ định mọi bean.

## 7. Routing theo SpEL: linh hoạt nhưng cần giới hạn

Spring Cloud Function còn hỗ trợ property **spring.cloud.function.routing-expression**. Khi dùng trên AWS Lambda, tài liệu cung cấp cách viết biến môi trường:

~~~text
spring_cloud_function_routingExpression
~~~

Đây là **key biến môi trường**, không phải name của một bean. Ví dụ một biểu thức được quản trị cấu hình để chọn hàm theo header đã được adapter gắn:

~~~properties
spring.cloud.function.routing-expression=headers['trustedAction']=='upper' ? 'uppercase' : 'lowercase'
~~~

Biểu thức trên là ví dụ cho context đã có **Spring Message headers**. Với Lambda invocation JSON thuần, cần bước ánh xạ header trước khi suy ra rằng **headers['trustedAction']** tồn tại.

Theo tài liệu Spring Cloud Function:

1. SpEL từ **Message header** được đánh giá trong **SimpleEvaluationContext** với khả năng bị giới hạn.
2. SpEL từ **application/system property** có thể dùng **StandardEvaluationContext** mạnh hơn, vì vậy nguồn cung cấp biểu thức phải được bảo vệ.
3. Những phiên bản/cơ chế routing có thể có quy tắc ưu tiên khác nhau; khi có callback thì callback được ưu tiên hơn header/property cho imperative functions.

**Không đưa biểu thức SpEL tùy ý của client vào môi trường cấu hình có đặc quyền.** Chỉ dùng biểu thức đã kiểm duyệt, và kiểm thử rõ các nhánh lỗi. Nếu chỉ có vài operation, dùng một **switch allowlist** hoặc **MessageRoutingCallback** thường dễ audit hơn.

## 8. Thứ tự ưu tiên của các cơ chế routing

Với **imperative functions** và cơ chế **RoutingFunction** theo tài liệu Spring Cloud Function, thứ tự ưu tiên khi có nhiều chỉ dẫn là:

| Mức ưu tiên | Cơ chế | Ý nghĩa |
| --- | --- | --- |
| **1 — cao nhất** | **MessageRoutingCallback** | Chính sách trong bean callback quyết định route |
| **2** | **Message headers** | Tên function hoặc SpEL đi cùng Message |
| **3** | **Application properties** | Chỉ dẫn từ cấu hình ứng dụng/môi trường |

Ví dụ nếu callback luôn trả **uppercase**, một Message header đòi **lowercase** không nhất thiết được tôn trọng. Vì vậy, khi test **functionRouter** qua headers, đừng đồng thời đăng ký callback có logic khác rồi kết luận framework “bỏ qua” header vì lỗi.

Với **reactive functions** nhận **Publisher** như **Flux<T>**, unit-of-work là publisher, không phải từng message đơn lẻ. Tài liệu chỉ hỗ trợ routing reactive dựa trên **application properties**, không bảo đảm route per-message theo header. Nếu cần routing từng event, cân nhắc đường **imperative** hoặc chia thành pipeline thích hợp.

## 9. Phương án B — nhiều Lambda độc lập dùng chung một JAR

Nếu ba hành động có quyền, trigger hoặc thông số vận hành khác nhau, thay vì một Lambda dispatch động, ta có thể triển khai **ba Lambda resources** cùng dùng JAR chứa ba bean:

~~~text
JAR: routing-lambda-1.0.0-aws.jar
  RoutingLambdaApplication
  uppercase bean
  lowercase bean
  reverse bean
  dispatchText bean
  Spring Cloud Function adapter

Lambda uppercase-lambda:
  spring_cloud_function_definition = uppercase

Lambda lowercase-lambda:
  spring_cloud_function_definition = lowercase

Lambda reverse-lambda:
  spring_cloud_function_definition = reverse
~~~

~~~mermaid
flowchart TB
    A["Một shaded JAR"] --> B["uppercase-lambda"]
    A --> C["lowercase-lambda"]
    A --> D["reverse-lambda"]
    B --> E["definition = uppercase"]
    C --> F["definition = lowercase"]
    D --> G["definition = reverse"]
~~~

Ở phương án này, **definition được cố định tại cấp mỗi Lambda resource**. Cùng một JAR và cùng handler **FunctionInvoker** nhưng mỗi Lambda chỉ expose đường gọi mà cấu hình môi trường của nó lựa chọn.

### Ưu điểm khi tách thành nhiều Lambda

- Có thể cấp **IAM execution role riêng** theo chức năng, tránh cấp quyền rộng cho cả một gateway.
- Có **memory/timeout/concurrency** độc lập để workload nặng không ảnh hưởng quota cấp function của workload nhẹ theo cách tương tự.
- Có thể gắn **SQS/Kinesis/EventBridge/S3** event source mapping riêng theo từng nghiệp vụ.
- Có CloudWatch logs, metrics, alarms, versions và aliases ở cấp Lambda resource riêng.
- Dễ rollback hoặc vô hiệu hóa một chức năng mà không đổi routing động của chức năng khác.

**Giới hạn:** dù AWS resources độc lập, dùng chung artifact có nghĩa một lần update JAR ảnh hưởng codebase của tất cả những Lambda nào được deploy lại bằng artifact mới. Ngoài ra, JAR chứa đủ bean có thể làm Spring khởi tạo những dependency không cần thiết cho một Lambda cụ thể, tùy cấu hình lazy/conditional của ứng dụng.

## 10. Ví dụ AWS SAM cho nhiều Lambda cùng JAR

Tệp **template.yaml** minh họa:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  UppercaseLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/routing-lambda-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 15
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.RoutingLambdaApplication
          spring_cloud_function_definition: uppercase

  LowercaseLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/routing-lambda-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 15
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.RoutingLambdaApplication
          spring_cloud_function_definition: lowercase

  ReverseLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/routing-lambda-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.lambda.RoutingLambdaApplication
          spring_cloud_function_definition: reverse
~~~

Giải thích:

- **Handler** là lớp adapter chung, đúng với ví dụ SAM trong tài liệu chính thức. Khi khai báo trong AWS Console, tài liệu cũng minh họa **org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest**.
- **CodeUri** trỏ tới cùng một **shaded JAR**. Tên file chỉ là mẫu; thay bằng artifact được build thật.
- **MAIN_CLASS** xác định Spring Boot application. Nếu JAR có manifest **Start-Class** tương thích, có thể không cần env var này.
- **spring_cloud_function_definition** cố định bean được gọi cho từng Lambda.
- **Runtime** và số liệu MemorySize/Timeout chỉ mang tính minh họa, cần phù hợp Java bytecode, Spring version và workload.

Mỗi Lambda có quyền, trigger và logs riêng. Ví dụ chưa khai báo IAM hoặc event source; phải thêm theo yêu cầu, không cho rằng SAM tự cấp mọi quyền nghiệp vụ.

### Khi nào dùng composition cố định?

Một Lambda cũng có thể chọn:

~~~yaml
Environment:
  Variables:
    spring_cloud_function_definition: "trimText|uppercase"
~~~

nhưng chỉ khi cả **trimText** và **uppercase** là bean hợp lệ, kiểu output của bước trước tương thích với input của bước sau. Chuỗi **|** là **composition tĩnh** cho Lambda đó, không phải routing động giữa nhiều nhánh per-request.

## 11. Phương án C — nhiều Lambda và artifact tách biệt

Khi hệ thống lớn dần, có thể tách codebase hoặc module thành các ứng dụng/function artifact khác nhau:

~~~text
order-query-lambda.jar      -> queryOrder
payment-command-lambda.jar -> processPayment
audit-event-lambda.jar     -> recordAudit
~~~

Lợi ích có thể gồm:

- Mỗi deploy chỉ mang dependency và bean của nghiệp vụ cần chạy.
- Đội phát triển có thể version và phát hành độc lập.
- Quyền hạ tầng, bộ test và cấu hình khởi động được tách rõ.
- Một thay đổi dependency của nghiệp vụ thanh toán không nhất thiết ảnh hưởng Lambda truy vấn đơn hàng.

Đổi lại, dự án phải quản lý thêm module/build pipeline, contract giữa các dịch vụ, thư viện chia sẻ, phiên bản và quan sát phân tán. **Tách JAR không đồng nghĩa không dùng lại được logic Java**: có thể đưa các DTO, service và chính sách nghiệp vụ chung vào thư viện Java được version hóa, trong khi mỗi Lambda chỉ đăng ký Function cần thiết.

Không nên tách mọi thao tác nhỏ thành một repository riêng chỉ để có nhiều Lambda. Cần cân nhắc ownership, mức độ gắn kết nghiệp vụ và yêu cầu vận hành.

## 12. Khi nào chọn một Lambda, khi nào chọn nhiều Lambda?

| Tiêu chí | Một Lambda định tuyến động | Nhiều Lambda độc lập |
| --- | --- | --- |
| **IAM permissions** | Chia sẻ execution role cho các nhánh | Có thể phân quyền riêng |
| **Memory/timeout** | Cùng cấu hình ở cấp Lambda | Tùy chỉnh theo function |
| **Reserved concurrency** | Cùng giới hạn ở cấp Lambda | Có thể đặt riêng |
| **Event triggers** | Cần phân biệt và ánh xạ nhiều loại event | Event source mapping riêng cho mỗi Lambda |
| **API entrypoint** | Một endpoint chung thuận tiện | Nhiều integrations hoặc API routes |
| **Route selection** | Theo từng invocation | Thường tĩnh bằng definition |
| **Độ phức tạp code** | Có router, allowlist, error mapping | Có thêm hạ tầng, ít routing động |
| **Bảo mật** | Phải kiểm tra quyền theo nhánh | Cách ly tốt hơn ở IAM/function boundary |
| **Deploy/rollback** | Một Lambda version chứa mọi nhánh | Có thể version/rollback từng Lambda |
| **Cold start** | Có thể tận dụng environment ấm cho những nhánh liên tiếp | Mỗi Lambda có cold start riêng |
| **Blast radius** | Lỗi router hoặc dependency chung ảnh hưởng mọi nhánh | Tách tốt hơn, nhưng cùng JAR vẫn có coupling |

**Không có lựa chọn đúng tuyệt đối.** Nếu các nhánh cùng quyền, cùng data store, cùng kiểu tải và cần một endpoint đơn giản, **một Lambda** có thể hợp lý. Nếu một nhánh cần quyền đọc S3 còn nhánh khác cần ghi DynamoDB, hoặc nhiều loại workload có thời gian xử lý rất khác, **nhiều Lambda** thường giúp cách ly tốt hơn.

Tài liệu Spring Cloud Function AWS cũng nhấn mạnh việc dùng nhiều Lambda với **event source mapping riêng** cho các ứng dụng hướng messaging, bởi cấu hình nhận và xử lý message thường phụ thuộc nguồn sự kiện.

## 13. Một Lambda nhận nhiều loại event: đừng nhầm payload với metadata

Điểm dễ gặp sai lầm trong phương án A là cho rằng mỗi AWS event tự chứa một **Spring Message header** có thể đọc bằng functionRouter.

### Direct invoke với envelope do ứng dụng thiết kế

Với bean **dispatchText**, một direct event có cấu trúc:

~~~json
{
  "operation": "lower",
  "value": "MiXeD"
}
~~~

Adapter Lambda có thể deserialize vào **TextCommand**, sau đó router ứng dụng đọc **operation** và gọi **lowercase**.

### API Gateway event có envelope riêng

Một API Gateway proxy event thường bao gồm metadata như **headers**, **requestContext**, **body**. Body có thể là chuỗi JSON:

~~~json
{
  "rawPath": "/text/upper",
  "headers": {
    "content-type": "application/json"
  },
  "body": "{\"value\":\"Hello\"}",
  "isBase64Encoded": false
}
~~~

Đây chỉ là mô hình rút gọn để giải thích envelope; phải kiểm tra đúng API Gateway REST/HTTP API payload version và event contract thực tế.

**Không thể giả định direct Function<TextCommand, TextResult> luôn tự bóc body của API Gateway**. Cần một adapter hoặc function nhận kiểu AWS event phù hợp để: đọc route/path, parse body, xác thực, chuyển sang TextCommand và ánh xạ kết quả thành response theo contract API Gateway.

### SQS/S3 cũng khác

- **SQS:** event có **Records**, có thể batch nhiều message; xử lý partial failures và retry theo từng record là vấn đề quan trọng.
- **S3:** event chứa bucket/key, thường cần gọi API đọc object; phải có quyền IAM và tránh xử lý lặp.
- **EventBridge:** event có **detail**, **source**, **detail-type** và metadata liên quan.

**Routing cho business request không tự giải quyết event-source integration.** Khi một Lambda xử lý nhiều nguồn sự kiện, nên thiết kế một lớp điều hợp rõ ràng để nhận diện loại event đã xác thực và chuyển sang từng payload nghiệp vụ.

## 14. Bảo mật routing: không nhận tên bean trực tiếp từ client

Trong một codebase có thể có bean dành cho public API, batch job, audit, tác vụ quản trị hoặc tác vụ xóa dữ liệu. Nếu caller được quyền gửi tên bean tùy ý rồi router lookup và thực thi, một chức năng nội bộ có thể bị expose vô tình.

### Mẫu nên tránh

~~~text
Client gửi:
  {"function":"deleteAllOrders", "payload": {...}}

Adapter:
  catalog.lookup(userInput.function).apply(userInput.payload)
~~~

Đây là ý tưởng không an toàn khi client không được tin cậy. **Đừng chuyển trực tiếp untrusted input thành function definition**.

### Mẫu an toàn hơn

~~~text
Public operation "upper"   -> internal bean uppercase
Public operation "lower"   -> internal bean lowercase
Public operation "reverse" -> internal bean reverse

Mọi operation khác -> reject
~~~

Ngoài allowlist, vẫn cần:

1. **Authentication** ở API Gateway/authorizer hoặc cơ chế tin cậy thích hợp.
2. **Authorization** theo operation, tài nguyên và tenant; allowlist không đủ.
3. **Input validation** và giới hạn kích thước payload.
4. **IAM least privilege** cho Lambda execution role.
5. **Observability** ghi lại route đã chọn mà không lộ dữ liệu nhạy cảm.
6. **Không chạy SpEL expression do client tùy ý cung cấp** trong context đặc quyền.

Điều này càng quan trọng với **một Lambda**: mọi nhánh thường chia sẻ một execution role, nên lỗi ở router hoặc một nhánh có thể tác động đến tài nguyên mà role đó được phép truy cập.

## 15. Lỗi route không tồn tại: reject hay fallback?

Nếu route cần gọi không có trong FunctionCatalog, **functionRouter** thường báo lỗi. Spring Cloud Function còn có **DefaultMessageRoutingHandler** để xử lý các message không thể định tuyến; một cách mặc định có thể là log và bỏ qua.

Với hệ thống nghiệp vụ, **bỏ qua silently** có thể rất nguy hiểm, nhất là khi message mang lệnh thanh toán hoặc cập nhật trạng thái. Nên chọn chính sách rõ ràng:

| Nhóm tình huống | Ứng xử nên cân nhắc |
| --- | --- |
| Operation lạ do caller gửi | Trả lỗi validation/authorization có mã rõ |
| Bean cấu hình thiếu | Báo lỗi triển khai, không giả vờ xử lý thành công |
| SQS message không có route hợp lệ | Reject/quarantine/DLQ theo chính sách nguồn |
| Transient error của downstream | Retry giới hạn với backoff |
| Business rejection | Trả decision/result theo contract hoặc báo lỗi phù hợp |

**Fallback không nên tự động thành “xử lý thành công”**. Với broker, điều đó có thể dẫn tới message bị ack dù chưa thực hiện nghiệp vụ. Cần kiểm thử semantics của adapter và event source mapping thật.

## 16. Retry, idempotency và giao dịch giữa các nhánh

Một Function xử lý chuỗi thuần như **uppercase** có thể gọi lại nhiều lần mà không tạo side effect. Nhưng nếu router phân nhánh tới **recordAudit**, **chargePayment** hoặc **updateInventory**, đặc tính hệ thống thay đổi hoàn toàn.

~~~mermaid
flowchart TD
    A["Event nhận từ nguồn"] --> B["Router"]
    B --> C{"Operation"}
    C --> D["Read-only Function"]
    C --> E["Write Consumer/Function"]
    E --> F["Database/external API"]
    F --> G["Response / Ack"]
~~~

Nếu nguồn gửi lại event sau một lỗi timeout hoặc ack thất bại, một operation ghi dữ liệu có thể chạy lặp. **Idempotency cần được bảo đảm ở nơi tạo tác dụng phụ**, không chỉ trong router:

- Mỗi event/command nên có **idempotency key** ổn định.
- Database có thể áp dụng **unique constraint**/transaction theo event ID hoặc business key.
- Với quy trình ghi dữ liệu rồi phát message, cân nhắc **outbox** hoặc cơ chế giao dịch phù hợp.
- Đặt retry/backoff/DLQ theo nguồn AWS và phân biệt lỗi vĩnh viễn với lỗi tạm thời.
- Không dùng một HashMap singleton trong JVM làm kho idempotency bền vững qua restart/nhiều replica.

Khi dùng nhiều Lambda độc lập, từng function có thể có retry policy, timeout và event source mapping riêng. Khi dùng một Lambda xử lý nhiều operation, **chính sách ở cấp Lambda/trigger có thể được chia sẻ**, nên cần cân nhắc có đủ linh hoạt không.

## 17. Cold start, scaling và chi phí vận hành

### Một Lambda

Một Lambda duy nhất có thể tái sử dụng application context và dependency đã khởi tạo giữa những invocation liên tiếp trên cùng execution environment. Nếu những nhánh chức năng liên quan gọi nối tiếp nhau, chúng **có thể** hưởng lợi từ warm environment sẵn có.

Tuy nhiên:

- Không bảo đảm hai invocation sẽ chạy trên cùng environment.
- Khi traffic tăng, AWS vẫn có thể tạo thêm environment và phát sinh cold start.
- Một nhánh nặng có thể ảnh hưởng latency/chi phí của các nhánh nhẹ vì phải dùng chung code/package và cấu hình cấp function.
- Reserved concurrency, memory và timeout thường được cấu hình ở cấp resource, không theo từng Java bean.

### Nhiều Lambda

Nhiều Lambda có thể chọn memory/timeout/concurrency riêng, mỗi function có metrics và alarms riêng. Nhưng mỗi Lambda vẫn có môi trường khởi tạo và warm pool riêng; khi traffic thấp, một Lambda không tự dùng lại JVM đang ấm của một Lambda khác.

### Cùng JAR có nhược điểm gì?

Một artifact chứa nhiều dependency/bean có thể có kích thước lớn và startup phức tạp hơn so với JAR tối giản theo nghiệp vụ. Tuy vậy, không nên đoán chênh lệch cold-start từ số bean: phải đo **Init Duration**, **Duration**, mức memory và dependency initialization trên workload thực tế.

**Không dùng cache/field singleton để chia sẻ trạng thái giữa các Lambda**. Mỗi execution environment là một vùng nhớ riêng; dùng database, cache phân tán hoặc messaging khi nghiệp vụ cần trạng thái chung.

## 18. Kiểm thử unit cho router tường minh

Vì **dispatchText** là Java Function nhận DTO, có thể test mà không khởi động Spring hoặc AWS.

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class DispatchTextUnitTest {

    private final RoutingLambdaApplication app =
        new RoutingLambdaApplication();

    @Test
    void dispatchesUpperAndReverse() {
        var router = app.dispatchText(
            app.uppercase(), app.lowercase(), app.reverse());

        var upper = router.apply(
            new RoutingLambdaApplication.TextCommand(
                "upper", "Hello"));
        var reverse = router.apply(
            new RoutingLambdaApplication.TextCommand(
                "reverse", "abc"));

        assertEquals("HELLO", upper.value());
        assertEquals("cba", reverse.value());
    }

    @Test
    void rejectsUnknownOperation() {
        var router = app.dispatchText(
            app.uppercase(), app.lowercase(), app.reverse());

        assertThrows(IllegalArgumentException.class,
            () -> router.apply(
                new RoutingLambdaApplication.TextCommand(
                    "delete", "value")));
    }

    @Test
    void rejectsNullInput() {
        var router = app.dispatchText(
            app.uppercase(), app.lowercase(), app.reverse());

        assertThrows(IllegalArgumentException.class,
            () -> router.apply(null));
    }
}
~~~

Bài test này chứng minh tính đúng đắn của **switch allowlist** và logic Function. Nó không xác minh Spring đã inject đúng bean hoặc FunctionCatalog đã đăng ký **dispatchText**.

## 19. Kiểm thử Spring FunctionCatalog và router mặc định

Dùng **@SpringBootTest** để xác minh bean discovery và composition/routing thực sự:

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = RoutingLambdaApplication.class)
class FunctionSelectionIntegrationTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void individualBeansAreDiscoverable() {
        assertNotNull(catalog.lookup("uppercase"));
        assertNotNull(catalog.lookup("lowercase"));
        assertNotNull(catalog.lookup("reverse"));
        assertNotNull(catalog.lookup("dispatchText"));
        assertNotNull(catalog.lookup("functionRouter"));
    }

    @Test
    void dispatchBeanUsesExpectedContract() {
        Function<
            RoutingLambdaApplication.TextCommand,
            RoutingLambdaApplication.TextResult> dispatch =
                catalog.lookup("dispatchText");

        assertNotNull(dispatch);

        var output = dispatch.apply(
            new RoutingLambdaApplication.TextCommand(
                "lower", "MiXeD"));

        assertEquals("mixed", output.value());
    }
}
~~~

Với framework **functionRouter**, dùng thêm test **MessageBuilder** ở phần 5 hoặc các test riêng cho **MessageRoutingCallback** nếu bật callback. Tránh gộp các cấu hình route có mức ưu tiên khác nhau trong một test rồi khó giải thích kết quả.

### Vì sao phải test hai cấp?

| Test | Điều được xác minh |
| --- | --- |
| **Unit** | Logic Java, ranh giới validation và allowlist |
| **Spring integration** | Bean tên đúng, DI và FunctionCatalog lookup |
| **Artifact inspection** | Shaded JAR chứa FunctionInvoker và lớp Spring |
| **AWS invocation** | Handler, env var, conversion và output thực |
| **Trigger integration** | Envelope, IAM, batch, retry, DLQ và idempotency |

Unit test pass không chứng minh **CodeUri** đúng; test catalog pass cũng chưa chứng minh API Gateway sẽ gửi đúng dữ liệu mà bean mong đợi.

## 20. Kiểm tra shaded JAR và cấu hình AWS

Để dùng **FunctionInvoker** ở Java Lambda JAR, project cần dependency **spring-cloud-function-adapter-aws** và cách đóng gói đúng, thường là **shaded JAR**.

Maven dependency minh họa:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-aws</artifactId>
</dependency>
~~~

Dự án phải quản lý version bằng bộ Spring Boot/Spring Cloud BOM tương thích, cấu hình Maven Shade hoặc Gradle Shadow giữ **META-INF/spring.factories**, **AutoConfiguration.imports** và các service metadata cần thiết.

Lệnh kiểm tra minh họa:

~~~bash
mvn clean package

jar tf target/routing-lambda-1.0.0-aws.jar |
  grep 'FunctionInvoker.class'

jar tf target/routing-lambda-1.0.0-aws.jar |
  grep 'RoutingLambdaApplication.class'
~~~

Không dùng Spring Boot executable JAR có nested **BOOT-INF/lib** làm deployable JAR chỉ vì nó chạy được với **java -jar**. Tên artifact trong ví dụ cần thay bằng file thực tế sau build.

**Bài này chỉ soạn nội dung kiến thức**: các lệnh Maven/AWS là hướng dẫn cho người học, không phải thao tác được thực hiện trong bước viết tài liệu.

## 21. Kiểm thử AWS Lambda của cả hai phương án

### A. Một Lambda với dispatchText

Direct invocation dùng một envelope có operation:

~~~bash
aws lambda invoke \
  --function-name text-gateway \
  --cli-binary-format raw-in-base64-out \
  --payload '{"operation":"upper","value":"Hello Lambda"}' \
  response.json

cat response.json
~~~

Mong đợi kết quả nghiệp vụ có **operation=upper** và **value=HELLO LAMBDA**.

### B. Hai Lambda tách resource

Lambda chọn **uppercase**:

~~~bash
aws lambda invoke \
  --function-name uppercase-lambda \
  --cli-binary-format raw-in-base64-out \
  --payload '"Hello Lambda"' \
  response.txt
~~~

Lambda chọn **lowercase**:

~~~bash
aws lambda invoke \
  --function-name lowercase-lambda \
  --cli-binary-format raw-in-base64-out \
  --payload '"HeLLo Lambda"' \
  lower.txt
~~~

Các lệnh là ví dụ cho môi trường đã cấu hình AWS credentials, IAM và artifact deploy. **Tên Lambda resource** như uppercase-lambda khác với **Function bean** uppercase.

Sau invocation, không chỉ xem file output. Hãy xem **FunctionError** trong metadata AWS CLI nếu có, logs, timeout, Java runtime, env var, function version/alias và nội dung đã serialize. Một AWS invoke API call có thể thành công ở cấp vận chuyển trong khi logic Function thất bại.

## 22. Vận hành và phiên bản khi có nhiều Lambda

### Cùng JAR, nhiều cấu hình

Với phương án B, các Lambda có thể cùng dùng artifact version **1.0.0** nhưng mỗi Lambda lưu biến môi trường khác nhau. Khi phát hành JAR mới, cần biết **những Lambda nào đang dùng bản nào**; có thể cập nhật từng Lambda và kiểm thử riêng.

### Mỗi Lambda có version/alias

Một AWS Lambda version thường lưu snapshot code và cấu hình. Nếu production alias trỏ một version cũ, việc thay biến môi trường ở một configuration mới không có nghĩa alias đã chuyển. Khi test, ghi rõ function name và qualifier.

### Một Lambda định tuyến động

Với A, thay router hoặc một bean trong JAR có thể ảnh hưởng tất cả nhánh cùng Lambda. Cần chạy regression test đầy đủ cho các route trước khi publish version hoặc chuyển alias. Khi sự cố xảy ra với một route, rollback toàn Lambda có thể tác động route khác.

### Observability

Nên ghi route/operation đã xác thực trong structured logs, phân tách latency và error count theo route. Với nhiều Lambda, có thêm metric/alarms ở cấp resource; với một Lambda, cần metric theo nhánh để không che khuất lỗi một tuyến dưới tổng tỉ lệ thành công.

Không log raw payload nhạy cảm, secrets hoặc dữ liệu cá nhân không cần thiết. Correlation ID chỉ dùng để truy vết, không phải bằng chứng phân quyền.

## 23. Bảng chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Handler không nạp được | Thiếu adapter hoặc sai shaded JAR | Kiểm tra FunctionInvoker.class, CodeUri |
| Main class không được tìm thấy | Sai MAIN_CLASS/Start-Class | Kiểm tra package và manifest |
| Nhiều bean nhưng chọn sai | Thiếu/sai function definition | Đặt definition rõ ràng, test catalog |
| Một Lambda chỉ chạy một bean | Đã cấu hình definition tĩnh | Dùng router per-invocation nếu cần |
| functionRouter không thấy route header | AWS event chưa ánh xạ thành Spring MessageHeaders | Tạo adapter tin cậy hoặc dispatchText |
| Callback bỏ qua header definition | Callback ưu tiên hơn header | Chỉ dùng một chiến lược có chủ đích |
| Route không tồn tại | Sai tên bean hoặc chưa scan vào context | Kiểm tra @Bean, FunctionCatalog |
| JSON bị parse sai sau đổi definition | Hợp đồng input của bean mới khác | Cập nhật caller/conversion/schema |
| API Gateway body không thành DTO | Envelope khác direct invoke | Dùng event adapter đúng trigger |
| Route lạ được gọi đến bean nhạy cảm | Không có allowlist/authorization | Mapping operation tường minh, IAM tối thiểu |
| SQS event bị ghi hai lần | Redelivery và thiếu idempotency | Event ID + transaction/unique key |
| Một operation gây timeout toàn Lambda | Timeout/memory chung, branch nặng | Cân nhắc tách Lambda riêng |
| Nhiều Lambda vẫn có dependency chung lỗi | Tất cả cùng dùng JAR lỗi | Version artifact và kiểm thử trước rollout |
| Bản Lambda qua alias không nhận config mới | Alias vẫn trỏ published version cũ | Kiểm tra qualifier/version, deploy có kiểm soát |
| Thấy lỗi SpEL hoặc rủi ro route | Nhận expression không đáng tin cậy | Chặn untrusted expression, dùng allowlist |
| Reactive route theo từng message không hoạt động | Routing reactive theo publisher, không per-message | Dùng property routing hoặc đổi thiết kế |

## 24. Bài tập thực hành

**Bài tập 1 — So sánh kiến trúc.** Một hệ thống có **readOrder**, **payOrder** và **notifyOrder**. Hãy chọn A, B hoặc C cho từng thao tác nếu payOrder cần IAM và timeout riêng. Nêu đánh đổi về deploy, quan sát và quyền.

**Bài tập 2 — Router tường minh.** Viết thêm operation **titleCase** vào ứng dụng ví dụ. Bổ sung bean mới, cập nhật allowlist trong **dispatchText** và viết unit test cho input hợp lệ/sai. Không cho caller truyền trực tiếp tên bean bất kỳ.

**Bài tập 3 — RoutingFunction.** Dùng **catalog.lookup("functionRouter")** với **MessageBuilder** đặt header **spring.cloud.function.definition=uppercase**. Kiểm tra output, sau đó đổi header sang **lowercase** và xác định điều kiện để router chọn khác.

**Bài tập 4 — MessageRoutingCallback.** Xây một callback chỉ cho phép **uppercase** và **reverse** dựa trên header **trustedAction** do adapter tạo. Viết test từ chối action không được phép, và giải thích vì sao callback có thể ghi đè routing header.

**Bài tập 5 — Hai Lambda cùng JAR.** Viết SAM template tạo Lambda uppercase và lowercase cùng CodeUri/Handler/MAIN_CLASS, nhưng khác definition, memory và timeout. Mô tả cách deploy/staging riêng.

**Bài tập 6 — Tách artifact.** Khi uppercase chỉ cần Java Core nhưng payment cần JDBC, AWS SDK và secret manager, hãy đề xuất cấu trúc module, dependency và pipeline build phù hợp. Nêu ưu/nhược điểm so với cùng JAR.

**Bài tập 7 — Event envelope.** Lambda text-gateway nhận API Gateway event có trường body là chuỗi JSON. Thiết kế adapter chuyển body thành TextCommand và ánh xạ TextResult thành response, kiểm thử lỗi JSON/operation không hợp lệ.

**Bài tập 8 — SQS idempotency.** Một Lambda xử lý **Consumer<OrderPaid>**, event bị gửi lại cùng event ID sau timeout. Đề xuất unique key, transaction và DLQ; giải thích vì sao router đúng không bảo đảm xử lý đúng một lần.

**Bài tập 9 — Quan sát và rollback.** Một Lambda duy nhất phục vụ ba route; sau deploy, reverse tăng lỗi nhưng upper/lower vẫn thành công. Đề xuất metrics theo route, chiến lược giảm rủi ro và các tình huống nên tách reverse thành Lambda riêng.

### Ghi nhớ

- **Một Lambda nhiều hàm** cần **định tuyến theo invocation**, qua FunctionRouter/MessageRoutingCallback/headers đã ánh xạ đúng hoặc một bean gateway có allowlist; environment definition tĩnh không tự thay đổi theo từng event.
- **Nhiều Lambda cùng JAR** thường dùng **spring_cloud_function_definition** khác nhau, nhưng đều giữ handler **FunctionInvoker** và main class Spring chung.
- **Nhiều Lambda/JAR riêng** cho phép chia tách dependency, quyền, sở hữu và vòng đời deploy tốt hơn, đổi lại thêm chi phí quản lý.
- **functionRouter** là router do Spring Cloud Function cung cấp; callback, Message headers và application properties có thứ tự ưu tiên cần nắm rõ.
- **AWS event envelope không tự trở thành Spring Message headers**. Cần xác minh adapter hoặc tự viết lớp điều hợp đáng tin cậy.
- **IAM, authentication, authorization, idempotency và retry** không được giải quyết chỉ bằng việc chọn function bean.
- Kiểm thử cả logic Java, FunctionCatalog, shaded JAR, cấu hình Lambda và event source thực tế trước khi công bố dịch vụ.

### Tài liệu tham khảo

- [Spring Cloud Function — AWS Lambda](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): phần AWS Function Routing, cách chọn một/nhiều Lambda và FunctionInvoker.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): FunctionCatalog, functionRouter, MessageRoutingCallback, Message headers, SpEL và routing priority.
- [AWS Lambda — Environment variables](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html): cấu hình tĩnh cho từng Lambda và version.
- [AWS Lambda — Event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/invocation-eventsourcemapping.html): tích hợp stream/queue, batch và retry.
- [AWS SAM — AWS::Serverless::Function](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-resource-function.html): tài nguyên Lambda và cấu hình IaC.
