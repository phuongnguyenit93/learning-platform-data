# Custom runtime, bootstrap và đóng gói native image

AWS Lambda có thể chạy ứng dụng Java bằng runtime do AWS quản lý, nhưng cũng cho phép bạn tự cung cấp cách khởi động và xử lý invocation. Cơ chế đó gọi là **custom runtime**. Với Spring Cloud Function, custom runtime hữu ích khi muốn kiểm soát JVM, dùng một phiên bản runtime riêng hoặc chạy ứng dụng đã biên dịch thành **GraalVM Native Image**. Khi triển khai theo dạng ZIP, Lambda tìm một file thực thi tên **bootstrap** ở thư mục gốc của package. File này khởi động runtime và kết nối ứng dụng với **Lambda Runtime API**.

Bài thuộc chương **AWS Lambda**, trình bày cách runtime hoạt động, trách nhiệm của bootstrap, khác biệt giữa managed Java runtime và OS-only runtime, cách chạy Spring Cloud Function bằng JVM tùy chỉnh, cách build native image, đóng gói ZIP, khai báo AWS SAM, chạy thử và triển khai. Phần cuối giải thích giới hạn của Spring AOT/native image, cách bổ sung runtime hints, các lỗi thường gặp và tiêu chí đánh giá hiệu năng.

Mục tiêu là hiểu toàn bộ đường đi từ **Function bean** đến **Lambda invocation**: Spring Cloud Function giữ logic nghiệp vụ bằng Supplier, Function hoặc Consumer; custom runtime nhận event từ AWS; adapter/Runtime Interface Client (RIC) chuyển event đến hàm; bootstrap đưa response hoặc error về Lambda.

## 1. Managed runtime, custom runtime và native image

Lambda có thể chạy code bằng runtime do AWS cung cấp hoặc bằng runtime do người dùng quản lý.

| Mô hình | Runtime | Artifact điển hình | Ai chịu trách nhiệm khởi động |
| --- | --- | --- | --- |
| **Java managed runtime** | Ví dụ java21 | JAR/ZIP chứa Java classes và dependencies | AWS Java runtime |
| **JVM custom runtime** | OS-only runtime cộng JVM/launcher do package hoặc layer cung cấp | ZIP có bootstrap, JVM hoặc Java runtime phù hợp, JAR và dependencies | Bootstrap của ứng dụng |
| **Native image custom runtime** | OS-only runtime cộng executable Linux | ZIP có bootstrap và native executable | Bootstrap gọi executable; RIC phải có trong runtime |
| **Custom runtime container image** | Container image do bạn xây dựng | OCI image trong ECR | Lambda container entrypoint |

**Native Image không chạy trên JVM truyền thống.** GraalVM phân tích ứng dụng ở build time và tạo executable đặc thù cho hệ điều hành/kiến trúc đích. Vì vậy, không thể upload JAR rồi yêu cầu Lambda chạy native image; cần đóng gói executable cùng bootstrap theo custom runtime.

~~~mermaid
flowchart TD
    A["Lambda invocation"] --> B{"Deployment model"}
    B --> C["Managed Java runtime"]
    B --> D["Custom runtime: JVM"]
    B --> E["Custom runtime: native image"]
    C --> F["AWS Java runtime"]
    D --> G["bootstrap -> JVM -> Spring Function"]
    E --> H["bootstrap -> native executable + RIC"]
    F --> I["Function bean"]
    G --> I
    H --> I
    I --> J["Response / error"]
~~~

### Khi nào chọn custom runtime?

Một số lý do hợp lý:

- Cần một phiên bản ngôn ngữ/JVM mà managed runtime chưa cung cấp.
- Muốn kiểm soát launcher, runtime libraries hoặc cách khởi động.
- Muốn chạy GraalVM Native Image hoặc binary native khác.
- Có yêu cầu tích hợp RIC/runtime đặc thù.
- Muốn chuẩn hóa runtime dùng chung cho nhiều function.

Nếu managed Java runtime đã đáp ứng yêu cầu và ứng dụng Spring Cloud Function có thể chạy qua **FunctionInvoker**, đó thường là lựa chọn đơn giản hơn. Custom runtime làm tăng trách nhiệm về bootstrap, RIC, OS compatibility, patching và vận hành.

## 2. OS-only runtime là gì?

OS-only runtime thuộc nhóm **provided**. AWS cung cấp môi trường hệ điều hành Lambda nhưng không cung cấp runtime ngôn ngữ như Java, Node.js hay Python. Ví dụ hiện hành cho Amazon Linux 2023 là:

~~~text
provided.al2023
~~~

OS-only runtime vẫn cung cấp execution environment, biến môi trường, filesystem, logging integration và Runtime API endpoint. Ứng dụng phải cung cấp phần runtime còn thiếu.

**provided.al2023** là lựa chọn minh họa cho custom runtime ZIP trong bài. AWS vẫn duy trì các runtime cũ trong giai đoạn deprecation tương ứng, nhưng với triển khai mới nên xem danh sách runtime hiện hành và ưu tiên Amazon Linux 2023 khi tương thích.

| Thành phần | AWS cung cấp | Package/ứng dụng chịu trách nhiệm |
| --- | --- | --- |
| Hệ điều hành Lambda | Có | Chọn runtime family phù hợp |
| Runtime API endpoint | Có | Runtime client gọi API đúng contract |
| File bootstrap | Không tự sinh cho package | Cung cấp ở root và đặt executable permission |
| JVM | Không có trong OS-only runtime | Đóng gói/cung cấp qua layer hoặc dùng native executable |
| Spring Application | Không | Build ứng dụng và dependencies |
| RIC cho native binary | Không tự động thêm vào binary tùy ý | Dùng integration có RIC hoặc tự tích hợp RIC |
| Function code | Không | Triển khai Supplier/Function/Consumer |

Không nhầm **OS-only runtime** với một máy EC2 hoặc container Linux thông thường. Lambda vẫn quản lý vòng đời execution environment và gọi runtime thông qua Lambda Runtime API.

## 3. Lambda Runtime API và vòng đời invocation

Custom runtime phải giao tiếp với **Lambda Runtime API**. AWS đưa địa chỉ API vào biến môi trường:

~~~text
AWS_LAMBDA_RUNTIME_API
~~~

Một runtime cơ bản thực hiện các bước sau:

1. Đọc cấu hình môi trường và khởi tạo tài nguyên dùng chung.
2. Gọi endpoint **next invocation** để chờ event tiếp theo.
3. Đọc body của event và các header chứa request ID, deadline, ARN và trace metadata.
4. Tạo context cho invocation rồi gọi handler/function.
5. Nếu xử lý thành công, gửi output lên endpoint **response**.
6. Nếu xử lý thất bại, gửi thông tin lỗi lên endpoint **error**.
7. Lặp lại bước nhận invocation tiếp theo.

~~~mermaid
sequenceDiagram
    participant L as Lambda service
    participant R as Runtime API
    participant B as bootstrap / RIC
    participant F as Spring Function

    L->>R: Cấp invocation
    B->>R: GET /runtime/invocation/next
    R-->>B: Event body + request headers
    B->>F: Gọi function với event/context
    F-->>B: Kết quả
    B->>R: POST /runtime/invocation/{id}/response
    R-->>L: Response được ghi nhận
    B->>R: GET /runtime/invocation/next
~~~

### Các endpoint quan trọng

Runtime API dùng các endpoint theo phiên bản, ví dụ:

~~~text
GET  /2018-06-01/runtime/invocation/next
POST /2018-06-01/runtime/invocation/{awsRequestId}/response
POST /2018-06-01/runtime/invocation/{awsRequestId}/error
POST /2018-06-01/runtime/init/error
~~~

- **next**: long-poll để nhận invocation tiếp theo.
- **response**: gửi kết quả thành công.
- **error**: báo lỗi xử lý invocation.
- **init/error**: báo lỗi xảy ra trong giai đoạn khởi tạo runtime.

Runtime phải dùng đúng request ID nhận từ response header để tạo đường dẫn response/error. Ngoài event body, runtime còn nhận header deadline, invoked function ARN và trace ID.

### Truyền trace context

Nếu response của Runtime API có header **Lambda-Runtime-Trace-Id**, runtime cần đặt giá trị tương ứng vào biến môi trường **_X_AMZN_TRACE_ID** cho invocation để AWS X-Ray có thể liên kết trace. Runtime tự triển khai phải làm đúng việc này. Khi sử dụng RIC do framework cung cấp, RIC chịu trách nhiệm phần giao thức này.

### Không nên tự viết Runtime API client nếu không cần

Một RIC đã được kiểm thử xử lý nhiều chi tiết dễ sai: long polling, request ID, deadline, error body, trace header, retry/connection behavior và shutdown. Với Spring Cloud Function, hãy dùng custom runtime integration hoặc native sample phù hợp trước khi cân nhắc tự triển khai RIC.

## 4. Bootstrap là gì?

**bootstrap** là executable entrypoint của custom runtime ZIP. Khi Lambda khởi động execution environment, nó tìm bootstrap ở thư mục gốc của deployment package (hoặc layer theo cơ chế runtime). Nếu file không tồn tại, không có quyền thực thi hoặc sai định dạng, invocation có thể thất bại với lỗi như **Runtime.InvalidEntrypoint**.

Một bootstrap script thường có:

- Shebang chỉ định shell, ví dụ **#!/bin/sh**.
- Chuyển working directory đến **LAMBDA_TASK_ROOT**.
- Khởi chạy JVM/runtime hoặc native executable.
- Dùng **exec** để tiến trình chính thay thế shell và nhận tín hiệu/runtime lifecycle phù hợp.

Ví dụ cấu trúc custom runtime ZIP:

~~~text
lambda-custom-runtime.zip
├── bootstrap
├── function-sample-aws-native
└── lib/                         # chỉ cần nếu ứng dụng đóng gói dependency riêng
    └── dependency.jar
~~~

Bootstrap phải có quyền thực thi trên Linux. Trước khi tạo ZIP:

~~~bash
chmod 755 bootstrap
file bootstrap
head -n 5 bootstrap
~~~

Nếu tạo script trên Windows, kiểm tra:

- File dùng LF thay vì CRLF nếu shell/runtime không xử lý CRLF.
- Shebang trỏ đến shell có sẵn trong runtime.
- ZIP giữ permission executable.
- Bootstrap nằm ở root, không bị đặt bên trong một thư mục con.
- Script không phụ thuộc vào đường dẫn cố định của máy build.

**Không chỉ đổi tên một file text thành bootstrap.** Nó phải có shebang hợp lệ và executable bit.

## 5. Spring Cloud Function trên custom runtime: hai hướng triển khai

Spring Cloud Function cung cấp một programming model chung, nhưng entrypoint phụ thuộc runtime.

### 5.1. JVM custom runtime

Ở hướng này:

1. ZIP chứa bootstrap, JVM phù hợp, application và dependencies.
2. Bootstrap khởi chạy Spring Boot application.
3. Cơ chế custom runtime/RIC kết nối invocation với function theo hướng dẫn của Spring Cloud Function version đang dùng.
4. Tên handler/function được cấu hình theo contract của custom runtime.
5. Function bean vẫn là Supplier/Function/Consumer thông thường.

Tài liệu Spring Cloud Function mô tả custom runtime JVM có thể dùng HTTP export của **spring-cloud-function-web**. Với release áp dụng cách này, cần thêm module Web và bật:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-aws</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-web</artifactId>
</dependency>
~~~

~~~properties
spring.cloud.function.web.export.enabled=true
~~~

Cách bootstrap, dependency và handler cần đối chiếu với sample đúng release line. Với custom runtime Spring Cloud Function, trường Handler thường mang tên function bean (ví dụ **uppercase**); bootstrap vẫn là tên file entrypoint ở ZIP root. Không trộn sample Spring Cloud Function 3.x/4.x với dependency 5.x mà không kiểm tra migration notes.

### 5.2. GraalVM Native Image

Ở hướng này:

1. Spring AOT và GraalVM tạo executable Linux.
2. Executable chứa ứng dụng đã biên dịch và cơ chế runtime/RIC cần thiết.
3. ZIP có bootstrap ở root và executable native.
4. Lambda dùng OS-only runtime như **provided.al2023**.
5. Bootstrap chạy executable, không khởi động JVM.

Spring Cloud Function có sample native image dành cho AWS Lambda. Hình dạng package được tài liệu mô tả:

~~~text
lambda-custom-runtime.zip
├── bootstrap
└── function-sample-aws-native
~~~

Bootstrap tối giản:

~~~sh
#!/bin/sh

cd "$LAMBDA_TASK_ROOT"
exec ./function-sample-aws-native
~~~

Đây là bootstrap cho sample mà **native executable đã có RIC/integration cần thiết**. Nếu bạn tự tạo một native Spring Boot executable không có Lambda Runtime Interface Client, chỉ chạy binary bằng bootstrap sẽ chưa đủ để nhận invocation. Phải thêm RIC tương thích hoặc dùng Spring Cloud Function AWS native integration theo sample.

## 6. Ví dụ Function bean dùng cho custom runtime

Ta dùng một Function đơn giản để tập trung vào runtime:

Tệp **src/main/java/example/lambda/NativeFunctionApplication.java**:

~~~java
package example.lambda;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class NativeFunctionApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            NativeFunctionApplication.class, args);
    }

    public record TextRequest(String value) {}

    public record TextResponse(String value) {}

    @Bean("uppercase")
    Function<TextRequest, TextResponse> uppercase() {
        return request -> {
            if (request == null
                    || request.value() == null) {
                throw new IllegalArgumentException(
                    "value is required");
            }

            return new TextResponse(
                request.value().toUpperCase(Locale.ROOT));
        };
    }
}
~~~

Payload direct invoke:

~~~json
{
  "value": "hello lambda"
}
~~~

Kết quả nghiệp vụ:

~~~json
{
  "value": "HELLO LAMBDA"
}
~~~

Logic Function không cần biết nó đang chạy trong JVM managed runtime hay GraalVM native image. Adapter chịu trách nhiệm nhận event và chuyển đổi input/output theo hợp đồng runtime.

### Functional bean registration

Spring Cloud Function cũng hỗ trợ đăng ký function theo kiểu functional thông qua **ApplicationContextInitializer** và **FunctionRegistration**. Cách này giảm một phần cấu hình bean runtime, có thể hữu ích với ứng dụng rất nhỏ và yêu cầu cold start nghiêm ngặt.

Ví dụ khái niệm:

~~~java
FunctionRegistration<Function<TextRequest, TextResponse>> registration =
    new FunctionRegistration<>(function)
        .type(FunctionType.from(TextRequest.class)
            .to(TextResponse.class));
~~~

Đây là đoạn minh họa API registration, chưa phải application hoàn chỉnh. Cần dùng đúng API và Spring Cloud Function version đang khóa. Functional registration không tự loại bỏ các giới hạn AOT hoặc thay thế RIC.

## 7. Cấu hình JVM custom runtime bằng bootstrap

Một JVM custom runtime có thể khởi động Java process từ package. Ví dụ bootstrap dạng shell:

~~~sh
#!/bin/sh
set -eu

cd "$LAMBDA_TASK_ROOT"

CLASSPATH=".:lib/*"

exec java \
  -Dspring.main.web-application-type=none \
  -Dspring.jmx.enabled=false \
  -cp "$CLASSPATH" \
  example.lambda.NativeFunctionApplication
~~~

Ví dụ trên minh họa việc khởi chạy Spring application với dependency JAR trong **lib/**. Nó giả định ZIP đã cung cấp Java executable trên PATH hoặc bootstrap đã cấu hình đường dẫn tới JVM được đóng gói.

**Quan trọng:** lệnh khởi chạy Spring Boot đơn thuần không tự tạo một custom runtime hoàn chỉnh. Phải có RIC hoặc cơ chế custom runtime tương thích để polling Lambda Runtime API và chuyển event vào function. Với Spring Cloud Function, hãy theo đúng custom runtime sample của release đang dùng; đừng copy bootstrap JVM này vào native image package.

### JVM custom runtime ZIP

Ví dụ layout:

~~~text
lambda-jvm-runtime.zip
├── bootstrap
├── bin/
│   └── java
├── lib/
│   ├── app.jar
│   └── dependency-1.jar
└── runtime/
    └── ...                      # JVM files nếu bạn đóng gói JVM riêng
~~~

Layout thực tế phụ thuộc cách bạn mang JVM và RIC. Nếu dùng Lambda layer để cung cấp Java runtime, bootstrap phải trỏ đến đúng path trong layer và layer phải tương thích OS/architecture.

### Khi dùng managed Java runtime

Nếu không cần tự quản lý JVM, chọn runtime managed như **java21** và dùng handler **FunctionInvoker::handleRequest**. Khi đó không cần bootstrap. Đây là mô hình ở các bài AWS Lambda trước; custom runtime chỉ nên chọn khi yêu cầu runtime/native image thực sự cần nó.

## 8. GraalVM Native Image và Spring AOT

**GraalVM Native Image** thực hiện ahead-of-time compilation (AOT). Thay vì JVM tải class và phân tích code khi chạy, native-image compiler phân tích entry point, các đường code có thể truy cập và metadata được cung cấp ở build time để tạo executable.

Spring Boot có quy trình **Spring AOT** để chuẩn bị bean definitions, proxy và runtime hints cho GraalVM.

~~~mermaid
flowchart TD
    A["Java source + dependencies"] --> B["Spring AOT processing"]
    B --> C["Generated bean definitions"]
    B --> D["Reflection / resource / serialization hints"]
    C --> E["GraalVM native-image compiler"]
    D --> E
    A --> E
    E --> F["Linux native executable"]
    F --> G["bootstrap + ZIP"]
    G --> H["AWS Lambda provided.al2023"]
~~~

### Những khác biệt so với JVM

| Đặc điểm | JVM | Native Image |
| --- | --- | --- |
| Biên dịch | Bytecode chạy trên JVM, JIT có thể tối ưu khi runtime | AOT compile thành binary ở build time |
| JVM runtime | Cần JVM | Không cần JVM riêng |
| Reflection | Có thể truy cập động theo runtime | Cần hints cho những đường dynamic chưa được suy ra |
| Classpath | Có thể nạp class theo cơ chế JVM | Đóng tại build time |
| Class loading | Có thể lazy load | Không có lazy class loading tương tự JVM |
| Spring bean definitions | Thường xử lý khi app khởi động | Spring AOT tạo metadata/code trước |
| Artifact | JAR/ZIP | Executable native + bootstrap |
| Tính di động | Bytecode tương đối độc lập OS/CPU | Binary phụ thuộc OS, libc và architecture |

### Closed-world assumption

Native Image giả định tập code có thể chạy được được xác định trong build. Những class hoặc resource chỉ được tải động bằng tên chuỗi có thể không xuất hiện trong binary nếu compiler không biết chúng cần thiết.

Một số hạn chế cần lưu ý:

- Reflection phải có hint phù hợp.
- Resource đọc bằng tên/path động có thể cần resource hints.
- Serialization cần biết type và member cần truy cập.
- Dynamic proxy phải được đăng ký trước.
- Classpath không thể bổ sung tùy ý khi ứng dụng đã chạy.
- Cấu hình Spring làm thay đổi tập bean ở runtime có thể bị giới hạn trong native mode.
- Một số thư viện dùng JNI, class loading động hoặc bytecode generation có thể chưa tương thích.

Không nên coi lỗi native image là lỗi của AWS Lambda ngay lập tức. Một ứng dụng có thể chạy tốt trên JVM nhưng thiếu hint hoặc không tương thích khi AOT compile.

## 9. Thêm Runtime Hints khi cần

Spring AOT và các thư viện Spring hỗ trợ nhiều hint tự động. Chỉ thêm hint thủ công khi build/runtime report cho thấy một type, field, constructor, method hoặc resource chưa được nhận diện.

Ví dụ đăng ký reflection cho DTO:

~~~java
package example.lambda;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(TextRuntimeHints.class)
class NativeHintsConfiguration {
}

class TextRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
            NativeFunctionApplication.TextRequest.class,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
            MemberCategory.INVOKE_PUBLIC_METHODS);

        hints.reflection().registerType(
            NativeFunctionApplication.TextResponse.class,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
            MemberCategory.INVOKE_PUBLIC_METHODS);
    }
}
~~~

Đây là ví dụ minh họa Spring Runtime Hints API. DTO record có thể đã được framework/serializer xử lý tự động tùy version và đường conversion; không thêm hint dư thừa chỉ để làm build pass.

### Resource hints

Nếu ứng dụng đọc file template hoặc schema theo đường dẫn động, cần đảm bảo resource được đưa vào native image. Có thể đăng ký resource pattern bằng RuntimeHints:

~~~java
hints.resources().registerPattern("templates/*.txt");
~~~

Pattern phải khớp đường dẫn resource thực tế trong classpath. Không dùng pattern rộng tùy tiện nếu chỉ cần một vài file.

### Kiểm tra native-image agent

GraalVM Native Image Agent có thể quan sát một lần chạy JVM và ghi lại một số truy cập reflection/resource/serialization. Các cấu hình thu được giúp tìm hint còn thiếu, nhưng agent chỉ ghi nhận những đường code đã chạy trong quá trình quan sát. Nó không chứng minh tất cả code path đều được bao phủ.

Quy trình hợp lý:

1. Chạy test với các input/event đại diện.
2. Thu thập agent configuration nếu cần.
3. Review cấu hình sinh ra, bỏ những entry không cần.
4. Chuyển thành Spring Runtime Hints hoặc native-image metadata theo cách phù hợp.
5. Build lại native executable và test đường chạy tương ứng.

## 15. Kiểm thử Spring AOT và native image

JVM unit test vẫn hữu ích, nhưng không đảm bảo native image sẽ hoạt động. Cần kiểm tra thêm:

- Spring AOT có hoàn tất không?
- Native compiler có tìm được mọi reflection/resource/proxy cần thiết không?
- Jackson/serialization có nhận biết DTO không?
- Dependency có dùng JNI hoặc thư viện native tương thích Linux không?
- FunctionCatalog có đăng ký đúng function trong native mode không?
- Function definition và environment có được đọc như kỳ vọng không?
- AWS Runtime Interface Client có nhận event và gửi response không?

### Test trên JVM

~~~bash
./mvnw test
~~~

### Build native image

~~~bash
./mvnw -Pnative native:compile
~~~

### Test bằng SAM local

~~~bash
sam local invoke NativeFunction --event events/request.json
~~~

### Test trên Lambda staging

Deploy ZIP lên một function staging, gọi bằng event representative, rồi kiểm tra:

- Init duration và duration.
- Request ID, logs và runtime error.
- Output serialization.
- Memory used và configured memory.
- Timeout, downstream access và IAM.
- Behavior với payload rỗng/sai schema.
- Sự khác nhau giữa cold start và warm invocation.

Native image cần kiểm thử trên chính Linux architecture mà Lambda dùng. Không chỉ chạy unit test trên Windows/macOS rồi kết luận binary sẵn sàng deploy.

## 16. GraalVM Native Image và cold start: đo trước khi chọn

Native Image có thể giảm thời gian khởi động ứng dụng và memory footprint so với một số ứng dụng JVM. Nhưng không có bảo đảm nó luôn nhanh hơn hoặc rẻ hơn cho mọi Lambda.

Tổng thời gian cold start còn gồm:

- Lambda chuẩn bị execution environment.
- Tải/extract deployment package.
- Khởi động bootstrap và RIC.
- Khởi tạo Spring context.
- Khởi tạo SDK clients, connection pools và các bean.
- Thực hiện bước xử lý event đầu tiên.

Một native executable có thể khởi tạo Spring nhanh hơn nhưng lại tăng thời gian build, kích thước binary, chi phí tối ưu và giới hạn tương thích. Với managed Java runtime, có thể cân nhắc các cơ chế như **SnapStart** nếu runtime/workload hỗ trợ.

| Tiêu chí | JVM managed/custom runtime | GraalVM Native Image |
| --- | --- | --- |
| Build | Compile bytecode nhanh hơn | AOT compile lâu hơn, tốn tài nguyên build |
| Startup ứng dụng | Có JVM và Spring startup | Có thể nhanh hơn do không cần JVM |
| Tối ưu warm execution | JIT có thể tối ưu sau warm-up | Không có JIT tương tự |
| Dynamic Java | Linh hoạt hơn | Cần hints, hạn chế class loading động |
| Runtime maintenance | Managed runtime hoặc tự quản JVM | Binary phải build lại khi cập nhật dependency/toolchain |
| Debug | Tooling JVM phong phú | Debugging/observability native có khác biệt |
| Portability | Bytecode đa nền tảng | Binary phụ thuộc OS/architecture |
| Cold start tổng thể | Phụ thuộc JVM, Spring và Lambda | Phụ thuộc build, bootstrap, RIC và Lambda |

### Benchmark đúng cách

Không chỉ so sánh thời gian khởi động Spring trên laptop. Đo ở Lambda staging với:

- Cùng payload và business logic.
- Cùng region và architecture.
- Memory/timeout được tuning công bằng.
- Nhiều lần cold start và warm invoke.
- Duration, Init Duration, billed duration và memory.
- Tỷ lệ lỗi và thời gian xử lý downstream.

Dùng workload thực tế để quyết định. Không chọn native image chỉ vì một benchmark đơn lẻ hoặc vì con số startup trên máy phát triển.

## 17. Bảo mật và bảo trì custom runtime

Khi tự quản lý runtime, nhóm phát triển chịu trách nhiệm nhiều hơn:

- **Patch OS/runtime**: chọn OS-only runtime được AWS duy trì và cập nhật package khi cần.
- **Patch JVM** nếu mang JVM trong ZIP/layer.
- **Cập nhật RIC**: sử dụng phiên bản phù hợp với Lambda Runtime API.
- **Supply chain**: pin dependency, kiểm tra artifact và scan image/package.
- **Least privilege**: execution role chỉ có quyền cần thiết.
- **Secrets**: lấy từ Secrets Manager/Parameter Store hoặc cơ chế quản lý secrets được duyệt; không đóng secret vào native binary.
- **Logging**: tránh log payload/token/PII; ghi request ID và error metadata cần thiết.
- **Rebuild native image** khi dependency hoặc runtime hints thay đổi.
- **Architecture**: phát hành artifact riêng cho x86_64 và arm64 nếu cần hỗ trợ cả hai.
- **Rollback**: giữ artifact trước đó và version/alias đã kiểm thử.

Native image không có nghĩa binary miễn nhiễm với lỗ hổng dependency. Các thư viện được link/compile vào executable vẫn cần được cập nhật bằng cách build và phát hành lại.

## 18. Troubleshooting custom runtime và bootstrap

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| **Runtime.InvalidEntrypoint** | Không có bootstrap ở root hoặc file không executable | Kiểm tra ZIP layout và mode 755 |
| **Permission denied** | Bootstrap/native binary thiếu execute permission | chmod 755 trước khi zip |
| **Exec format error** | Binary build cho Windows/macOS hoặc sai architecture | file binary, Linux target và x86_64/arm64 |
| **No such file or directory** dù file có tồn tại | Thiếu dynamic loader hoặc thư viện native | Kiểm tra ELF interpreter, glibc và linked libraries |
| Bootstrap thoát ngay | Shell syntax, path sai hoặc binary trả exit code | Xem shebang, working directory và stderr |
| Runtime không nhận event | Thiếu RIC hoặc custom runtime không gọi Runtime API | Xác minh RIC/integration, AWS_LAMBDA_RUNTIME_API |
| Invocation timeout | Runtime không gọi next/response đúng hoặc app startup treo | Kiểm tra polling, deadline và initialization |
| Không gửi được response | Dùng sai request ID hoặc endpoint response/error | Đối chiếu Runtime API contract |
| Trace không liên kết | Không propagate Lambda-Runtime-Trace-Id | Kiểm tra _X_AMZN_TRACE_ID |
| Spring không tìm thấy Function | Function bean chưa đăng ký hoặc definition sai | Kiểm tra FunctionCatalog và function definition |
| ClassNotFound trên JVM custom runtime | Classpath/lib layout thiếu dependency | Kiểm tra bootstrap classpath và ZIP |
| Native image thiếu class | Code path/reflection bị loại ở build time | Đọc native-image report, bổ sung hints |
| JSON parse/serialize lỗi chỉ ở native | Reflection/serialization hints chưa đủ | Kiểm tra Spring AOT và serializer hints |
| Không đọc được config/resource | Resource chưa được đóng vào image | Thêm resource hints và kiểm tra package |
| Bean khác giữa JVM và native | Runtime conditional/profile/config động | Rà soát closed-world/AOT restrictions |
| Chạy local được nhưng AWS fail | Khác libc, architecture, IAM hoặc runtime API | Test trên Lambda staging với đúng artifact |
| ZIP deploy được nhưng invocation fail | ZIP đúng định dạng nhưng binary/RIC sai | Kiểm tra bootstrap và CloudWatch logs |
| Binary quá lớn | Dependency/native metadata không cần thiết | Phân tích dependency và reachability report |

### Đọc log khởi tạo

Khi custom runtime không khởi động, lỗi có thể xuất hiện trước khi Spring Function được gọi. Phân loại theo thứ tự:

1. Lambda có tìm thấy bootstrap không?
2. Bootstrap có được thực thi không?
3. Binary/JVM có chạy được trên Linux target không?
4. RIC có kết nối Runtime API không?
5. Spring ApplicationContext có khởi tạo không?
6. FunctionCatalog có tìm thấy function không?
7. Payload conversion và business logic có thành công không?
8. Runtime có gửi response/error về AWS không?

Sửa đúng tầng lỗi giúp tránh thay đổi Function code khi vấn đề thực tế nằm ở ZIP permission, architecture hoặc RIC.

## 19. Checklist phát hành custom runtime

- [ ] Chọn rõ JVM custom runtime hay native image.
- [ ] Chọn OS-only runtime còn được hỗ trợ, ví dụ provided.al2023.
- [ ] Spring Boot và Spring Cloud Function version tương thích.
- [ ] Custom runtime có Runtime Interface Client phù hợp.
- [ ] Bootstrap nằm ở root ZIP và có quyền executable.
- [ ] Bootstrap dùng đúng shell/line endings và working directory.
- [ ] Native executable build cho Linux và đúng architecture.
- [ ] Binary tương thích libc/system libraries của runtime.
- [ ] Spring AOT build thành công và runtime hints đầy đủ.
- [ ] FunctionCatalog/bean definition được xác minh.
- [ ] ZIP chỉ chứa artifact cần thiết, đúng root layout.
- [ ] SAM template dùng Runtime/Handler/CodeUri đúng custom runtime.
- [ ] IAM execution role theo least privilege.
- [ ] Timeout, memory và environment variables đã được tuning.
- [ ] Unit test, native build, SAM local và staging invoke đều pass.
- [ ] Logs/metrics/alarms và rollback đã chuẩn bị.

## 20. Bài tập thực hành

**Bài tập 1 — Phân biệt runtime.** So sánh Java managed runtime, JVM custom runtime và GraalVM native image. Với từng cách, nêu runtime do ai cung cấp, artifact cần đóng gói và thành phần khởi động.

**Bài tập 2 — Runtime API.** Vẽ vòng đời một invocation từ GET next đến POST response/error. Chỉ ra vị trí request ID, deadline và trace header.

**Bài tập 3 — Bootstrap.** Viết bootstrap script chạy một chương trình native. Giải thích shebang, LAMBDA_TASK_ROOT, exec và quyền thực thi.

**Bài tập 4 — JVM custom runtime.** Đóng gói một Spring Cloud Function JVM cùng bootstrap và dependency. Cấu hình handler/function name theo sample đúng release; xác minh RIC nhận event.

**Bài tập 5 — Native build.** Thêm Native Build Tools vào Maven, chạy Spring AOT và GraalVM native compile. Ghi lại thời gian build và vị trí executable.

**Bài tập 6 — Architecture.** Tạo hai build Linux x86_64 và arm64. Giải thích vì sao không thể dùng binary Windows/macOS trong Lambda Linux.

**Bài tập 7 — ZIP layout.** Tạo ZIP gồm bootstrap và native executable ở root. Kiểm tra bằng unzip -l và xác minh permission sau khi giải nén trên Linux.

**Bài tập 8 — Runtime hints.** Tạo DTO được Jackson đọc qua reflection hoặc resource được tải theo tên động. Chạy native image, phân tích lỗi và bổ sung RuntimeHints cần thiết.

**Bài tập 9 — SAM local.** Tạo resource Runtime provided.al2023, Handler bootstrap, CodeUri native ZIP. Dùng sam local invoke với event JSON và phân loại lỗi nếu invocation không tới Function bean.

**Bài tập 10 — Cloud staging.** Deploy native ZIP vào Lambda staging. Kiểm tra init duration, duration, memory, logs, architecture, IAM và response.

**Bài tập 11 — So sánh JVM/native.** Chạy cùng business function trên managed Java runtime và native custom runtime. Đo cold start, warm duration, billed duration, memory và chi phí theo workload.

**Bài tập 12 — Vận hành runtime.** Lập quy trình cập nhật RIC, OS-only runtime, GraalVM và dependencies. Thiết kế version/alias/rollback cho artifact native.

### Ghi nhớ

- **Custom runtime** dùng bootstrap làm entrypoint; bootstrap và RIC phải kết nối với Lambda Runtime API.
- **provided.al2023** là OS-only runtime trên Amazon Linux 2023; Lambda không tự cung cấp JVM hoặc language runtime trong mô hình này.
- Spring Cloud Function hỗ trợ custom runtime cho JVM và GraalVM native image. Hãy dùng sample đúng release line để bảo đảm handler, RIC, dependency và bootstrap khớp nhau.
- **Native image** là executable phụ thuộc Linux OS/architecture, không phải JAR. ZIP thường có bootstrap và native binary ở root.
- **Spring AOT** tạo bean definitions và hints cho reflection/resource/serialization/proxy. Native image có closed-world restrictions, nên code dynamic có thể cần điều chỉnh.
- Build native cho **Linux x86_64 hoặc arm64** tương ứng với Lambda; kiểm tra libc và shared libraries.
- Native image có thể giảm startup/memory nhưng tăng thời gian build và giới hạn tương thích. Benchmark trên Lambda thật trước khi chọn.
- Kiểm thử cần đi qua unit test, AOT/native build, SAM local và cloud staging; build pass không chứng minh Runtime API, IAM hoặc trigger đã đúng.

### Tài liệu tham khảo

- [Spring Cloud Function — AWS Lambda adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): custom runtime, bootstrap, GraalVM Native Image, handler, routing và sample package.
- [AWS Lambda — Building a custom runtime](https://docs.aws.amazon.com/lambda/latest/dg/runtimes-custom.html): Runtime API, initialization, invocation loop, bootstrap và RIC.
- [AWS Lambda — Runtime API](https://docs.aws.amazon.com/lambda/latest/dg/runtimes-api.html): endpoint nhận invocation, response, error và context headers.
- [AWS Lambda — OS-only runtimes](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html): provided runtime family, Amazon Linux 2023 và native executable requirements.
- [AWS Lambda — Creating a Bash custom runtime](https://docs.aws.amazon.com/lambda/latest/dg/runtimes-walkthrough.html): bootstrap script, Runtime API và package permissions.
- [Spring Boot — GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html): AOT, closed-world assumptions, generated hints và native limitations.
- [Spring Boot — Building a native executable](https://docs.spring.io/spring-boot/how-to/native-image/developing-your-first-application.html): Maven/Gradle Native Build Tools và buildpacks.
- [GraalVM Native Build Tools — Maven guide](https://graalvm.github.io/native-build-tools/latest/end-to-end-maven-guide.html): cấu hình native-maven-plugin và build executable.
- [Spring Cloud Function — Native Image blog](https://spring.io/blog/2020/05/04/spring-cloud-function-native-images/): ví dụ Spring Cloud Function native image trên AWS Lambda.

## 10. Build native image bằng Maven

Để tạo native executable, dự án cần một tổ hợp Spring Boot, Spring Cloud Function và GraalVM Native Build Tools tương thích.

Dependency chính của Spring Cloud Function AWS:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-aws</artifactId>
</dependency>
~~~

Plugin Native Build Tools:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
</plugin>
~~~

Với **spring-boot-starter-parent** phù hợp, Spring Boot có thể cung cấp profile **native** và cấu hình AOT liên quan. Nếu không dùng parent này, cần tự cấu hình các goal Spring AOT và Native Build Tools theo tài liệu của phiên bản.

Lệnh build native executable trên môi trường GraalVM/Linux phù hợp:

~~~bash
./mvnw -Pnative native:compile
~~~

Với Maven đã cài:

~~~bash
mvn -Pnative native:compile
~~~

Executable được tạo trong **target/**. Tên binary phụ thuộc cấu hình artifact/plugin và cần kiểm tra thực tế.

### Gradle

Với Gradle, thêm Native Build Tools plugin vào project:

~~~groovy
plugins {
    id 'org.springframework.boot'
    id 'org.graalvm.buildtools.native'
}
~~~

Spring Boot Gradle plugin sẽ kích hoạt AOT task phù hợp khi native plugin được áp dụng. Build executable:

~~~bash
./gradlew nativeCompile
~~~

Binary thường nằm trong **build/native/nativeCompile/**. Tên file phụ thuộc tên project và cấu hình plugin. Nếu build native container image thay vì ZIP, có thể dùng **bootBuildImage**; khi đó deployment model là container image và cần Lambda-compatible base image/entrypoint.

### Build bằng container/buildpacks

Spring Boot cũng hỗ trợ build OCI image chứa native executable bằng Cloud Native Buildpacks:

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

Lệnh này tạo **container image**, không tự tạo ZIP có bootstrap cho custom runtime. Nếu chọn Lambda PackageType Image, cần dùng Lambda-compatible base image/entrypoint phù hợp. Nếu chọn ZIP với **provided.al2023**, cần lấy native executable, tạo bootstrap và đóng gói ZIP riêng.

### Chọn đúng OS và architecture

Native executable phải được build cho Linux và đúng architecture của Lambda:

| Lambda Architecture | Native build target |
| --- | --- |
| **x86_64** | Linux AMD64 / x86-64 |
| **arm64** | Linux AArch64 / ARM64 |

Build trên Windows tạo Windows executable không thể chạy trên Lambda Linux. Build trên macOS cũng không tự động tạo Linux executable tương thích. Hãy build trong Linux container/CI image phù hợp hoặc dùng khả năng container build của Native Build Tools đã được cấu hình.

Ngoài architecture, cần chú ý **glibc** và thư viện native liên kết. Binary build trên một Linux distribution mới hơn có thể phụ thuộc glibc mà môi trường Lambda không có. Build trong môi trường tương thích Amazon Linux 2023 hoặc kiểm tra dependencies bằng công cụ Linux phù hợp.

## 11. Đóng gói native image thành ZIP

Giả sử native executable đã được build và tên file là:

~~~text
target/function-sample-aws-native
~~~

Tạo thư mục package:

~~~bash
mkdir -p target/lambda-package
cp target/function-sample-aws-native target/lambda-package/
~~~

Tạo bootstrap ở root package:

~~~sh
#!/bin/sh
set -eu

cd "$LAMBDA_TASK_ROOT"
exec ./function-sample-aws-native
~~~

Đặt quyền thực thi:

~~~bash
chmod 755 target/lambda-package/bootstrap
chmod 755 target/lambda-package/function-sample-aws-native
~~~

Tạo ZIP:

~~~bash
cd target/lambda-package
zip -r ../lambda-native.zip bootstrap function-sample-aws-native
cd ../..
~~~

Kiểm tra nội dung:

~~~bash
unzip -l target/lambda-native.zip
~~~

Package phải có hai entry ở root:

~~~text
bootstrap
function-sample-aws-native
~~~

Không được đóng ZIP theo kiểu có một thư mục cha:

~~~text
lambda-native.zip
└── lambda-package/
    ├── bootstrap
    └── function-sample-aws-native
~~~

Nếu ZIP có thư mục cha, Lambda không tìm thấy bootstrap ở vị trí yêu cầu.

### Kiểm tra binary trên Linux

Trong môi trường build Linux:

~~~bash
file target/function-sample-aws-native
ldd target/function-sample-aws-native
~~~

**file** giúp xem định dạng/architecture. **ldd** giúp kiểm tra dynamic libraries nếu binary được liên kết động. Không phải native executable nào cũng có thể dùng lệnh ldd theo cùng cách; nếu binary static hoặc công cụ báo không áp dụng, hãy kiểm tra bằng phương pháp phù hợp với toolchain.

## 12. AWS SAM template cho native image ZIP

Ví dụ **template.yaml**:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: Spring Cloud Function GraalVM native image

Resources:
  NativeFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: provided.al2023
      Handler: uppercase
      CodeUri: target/lambda-native.zip
      Architectures:
        - x86_64
      MemorySize: 512
      Timeout: 20
      Policies:
        - AWSLambdaBasicExecutionRole

Outputs:
  NativeFunctionArn:
    Description: Lambda function ARN
    Value: !GetAtt NativeFunction.Arn
~~~

Các điểm cần hiểu:

- **Runtime: provided.al2023** chọn OS-only runtime trên Amazon Linux 2023.
- **Handler: uppercase** là tên function bean mà custom runtime Spring Cloud Function sẽ chọn. File khởi động của OS-only runtime vẫn phải tên **bootstrap** ở root ZIP; đó là entrypoint của runtime, không phải tên function bean.
- **CodeUri** trỏ tới ZIP đã đóng gói.
- **Architectures** phải trùng architecture của native executable.
- **MemorySize/Timeout** là giá trị minh họa, cần benchmark.
- **spring_cloud_function_definition** chọn bean khi ứng dụng/adapter hỗ trợ property này.
- **AWSLambdaBasicExecutionRole** cấp quyền logging cơ bản; nếu Function gọi S3, SQS, DynamoDB hoặc dịch vụ khác, bổ sung quyền tối thiểu tương ứng.

Với custom runtime Spring Cloud Function, **Handler: uppercase** biểu thị function bean mà runtime sẽ gọi; file **bootstrap** vẫn là executable được Lambda tìm thấy ở root ZIP. Nếu sample release dùng property **spring_cloud_function_definition** thay cho handler để chọn bean, hãy đặt hai giá trị nhất quán theo hướng dẫn của sample. Khi có nhiều function và muốn routing động, dùng **functionRouter** nếu runtime integration hỗ trợ. Không sao chép cấu hình managed Java **FunctionInvoker::handleRequest** sang OS-only native runtime vì native package không chạy Java handler class trên JVM.

### SAM build và deploy

Vì ZIP native đã được build trước, có thể kiểm tra template:

~~~bash
sam validate
~~~

Sau đó deploy:

~~~bash
sam deploy --guided
~~~

SAM/CloudFormation tạo hoặc cập nhật Lambda resource. Nếu muốn SAM quản lý luôn native build/package, cần khai báo build workflow phù hợp (Makefile/custom build) để tạo executable Linux và ZIP đúng layout. Không giả định SAM Java builder mặc định tự tạo GraalVM native image cho Spring Cloud Function.

## 13. Tạo Lambda bằng AWS CLI

Nếu đã có ZIP và execution role, có thể tạo function bằng CLI:

~~~bash
aws lambda create-function \
  --function-name spring-function-native \
  --runtime provided.al2023 \
  --handler uppercase \
  --architectures x86_64 \
  --role arn:aws:iam::123456789012:role/lambda-execution-role \
  --zip-file fileb://target/lambda-native.zip \
  --timeout 20 \
  --memory-size 512
~~~

ARN role và tên function ở trên là placeholder. Lệnh tạo resource thật trong AWS account và có thể phát sinh chi phí khi invoke. Hãy dùng account/region dev và role đã được cấp đúng quyền.

Kiểm tra function:

~~~bash
aws lambda get-function-configuration \
  --function-name spring-function-native
~~~

Invoke với payload JSON:

~~~bash
aws lambda invoke \
  --function-name spring-function-native \
  --cli-binary-format raw-in-base64-out \
  --payload '{"value":"hello lambda"}' \
  response.json
~~~

Xem kết quả:

~~~bash
cat response.json
~~~

Nếu dùng Spring Cloud Function definition qua environment variable, kiểm tra giá trị đã được cấu hình trong Lambda:

~~~text
spring_cloud_function_definition=uppercase
~~~

Đừng coi **aws lambda create-function** thành công là bằng chứng native executable đã chạy đúng. Chỉ invocation thực tế mới kiểm tra được bootstrap, ABI, RIC, AOT hints và event conversion.

## 14. Chạy thử custom runtime bằng SAM local

SAM local có thể khởi chạy Lambda runtime container qua Docker và gửi event vào custom runtime package:

~~~bash
sam local invoke NativeFunction --event events/request.json
~~~

File event mẫu:

~~~json
{
  "value": "hello lambda"
}
~~~

Với native ZIP, cần bảo đảm:

- Docker có thể chạy container runtime phù hợp.
- ZIP chứa bootstrap executable ở root.
- Binary là Linux executable.
- Architecture của binary phù hợp môi trường container/target.
- Runtime configuration trong SAM là **provided.al2023**.
- Native executable có RIC hoặc integration tương ứng.

### Test binary trước khi đưa vào SAM

Trong Linux build environment, có thể chạy binary trực tiếp nếu sample hỗ trợ một chế độ local/test. Nhưng **Lambda native executable có RIC** có thể đòi biến môi trường Runtime API chỉ có trong Lambda/SAM container. Vì vậy, việc chạy binary trực tiếp trên terminal không phải lúc nào cũng là test invocation hoàn chỉnh.

Hãy phân biệt:

1. **Unit test**: test logic Function trên JVM.
2. **Native smoke test**: xác minh binary khởi động/không thiếu thư viện.
3. **SAM local invoke**: test bootstrap, runtime container và event path.
4. **Cloud integration**: xác minh AWS Runtime API, IAM, event source và behavior thực tế.
