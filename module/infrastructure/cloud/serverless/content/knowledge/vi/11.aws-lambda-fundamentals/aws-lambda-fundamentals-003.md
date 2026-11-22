# Đóng gói Lambda bằng ZIP, JAR, layer và container image

Trong chương **AWS Lambda căn bản**, đóng gói là bước biến mã Java và các thành phần phụ thuộc thành artifact mà Lambda có thể tải, khởi tạo và chạy. Artifact cần chứa đúng class, thư viện, tài nguyên cấu hình và thông tin handler. Nếu thiếu dependency, sai cấu trúc thư mục hoặc không tương thích runtime/kiến trúc CPU, function có thể triển khai thành công nhưng thất bại ngay khi khởi tạo.

AWS Lambda hỗ trợ hai kiểu gói triển khai chính: **ZIP deployment package** và **container image**. Với Java, ZIP package có thể được tổ chức bằng một JAR độc lập hoặc các class cùng dependency JAR; **Lambda layer** bổ sung thư viện hoặc thành phần dùng chung vào ZIP package. Container image đóng gói cả runtime và ứng dụng theo định dạng OCI/Docker. JAR và layer vì vậy là cách tổ chức nội dung hoặc tái sử dụng thư viện trong hệ sinh thái ZIP, còn container image là một kiểu gói triển khai riêng.

Bài học thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng serverless, đặc biệt là Java function kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Khi chọn cách đóng gói, cần cân nhắc thời gian build, kích thước artifact, dependency, cold start, bảo mật, quyền truy cập registry, khả năng cập nhật và chi phí vận hành.

## 1. Các thành phần trong một gói Java Lambda

Một function Java thường cần các thành phần sau:

- **Application classes:** các class đã biên dịch chứa handler, use case, domain model và adapter.
- **Dependencies:** thư viện bên ngoài như Jackson, JDBC driver, SDK hoặc framework.
- **Resources:** file cấu hình, template, schema hoặc dữ liệu tĩnh cần lúc chạy.
- **Handler configuration:** tên class và method mà Lambda runtime gọi.
- **Runtime:** môi trường Java và Lambda Runtime Interface tương ứng.
- **Native libraries:** thư viện nhị phân nếu ứng dụng phụ thuộc vào mã native; phải tương thích Linux và kiến trúc CPU của function.

Có thể hình dung quy trình:

~~~mermaid
flowchart LR
    SRC["Java source"] --> BUILD["Maven / Gradle"]
    BUILD --> CLS["Compiled classes"]
    BUILD --> DEP["Runtime dependencies"]
    CLS --> PKG["Package assembly"]
    DEP --> PKG
    RES["Resources / config"] --> PKG
    PKG --> ZIP["ZIP / JAR artifact"]
    PKG --> IMG["Container image"]
    ZIP --> LAMBDA["AWS Lambda"]
    IMG --> LAMBDA
~~~

Lambda runtime tải artifact, thiết lập classpath và khởi tạo handler. Khi function được gọi, runtime chuyển event đến handler. Vì vậy, đóng gói cần bảo đảm handler và tất cả class mà handler sử dụng đều có thể được tìm thấy trong classpath.

## 2. Phân biệt ZIP, JAR, Lambda layer và container image

| Cách đóng gói | Nội dung chính | Điểm phù hợp |
|---|---|---|
| ZIP deployment package | Class, resource, dependency JAR và cấu trúc thư mục | Cách phổ biến cho Java Lambda; dễ triển khai bằng công cụ AWS |
| JAR deployment package | Java archive chứa class, resource và có thể cả dependency | Tiện cho ứng dụng Java gọn hoặc uber JAR |
| Lambda layer | ZIP riêng chứa thư viện hoặc thành phần dùng chung | Chia sẻ dependency giữa nhiều function ZIP |
| Container image | Image Linux chứa runtime, ứng dụng và dependency | Cần môi trường đóng gói tùy biến, công cụ container hoặc dependency lớn |

**ZIP và JAR** là các archive dựa trên định dạng ZIP. JAR có quy ước riêng cho Java như manifest và cấu trúc class. Có thể triển khai Java Lambda bằng JAR hoặc ZIP; nếu dùng ZIP, cần bảo đảm class và thư viện nằm ở vị trí runtime có thể nạp.

**Lambda layer** không phải một kiểu deployment package độc lập thay thế ZIP. Layer được gắn vào function ZIP để bổ sung thư viện hoặc thành phần dùng chung. Function vẫn có một deployment package riêng.

**Container image** là kiểu package khác. Lambda lấy image từ Amazon Elastic Container Registry (Amazon ECR), khởi chạy container theo Lambda Runtime API và thực thi handler được cấu hình.

Cần phân biệt **Lambda layer** với **Docker image layer**. Lambda layer là archive được gắn vào cấu hình function và giải nén vào /opt. Docker image layer là lớp filesystem bất biến được tạo trong quá trình build image theo cơ chế OCI/Docker.

## 3. Chọn handler và runtime Java

Handler là điểm vào mà Lambda runtime gọi khi function nhận invocation. Với Java, có thể triển khai handler bằng interface hoặc method signature phù hợp với runtime.

Ví dụ handler dùng RequestHandler:

~~~java
package com.example.orders;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;

public class OrderHandler
        implements RequestHandler<OrderEvent, OrderResult> {

    @Override
    public OrderResult handleRequest(
            OrderEvent event,
            Context context) {

        context.getLogger().log(
                "Processing order " + event.orderId());

        return new OrderResult(event.orderId(), "ACCEPTED");
    }
}
~~~

Các DTO minh họa:

~~~java
package com.example.orders;

public record OrderEvent(String orderId, String customerId) {
}

public record OrderResult(String orderId, String status) {
}
~~~

Với handler triển khai RequestHandler, cấu hình handler thường là tên class đầy đủ, ví dụ **com.example.orders.OrderHandler**. Với handler method theo kiểu POJO, có thể cấu hình dạng **package.Class::method**. Hãy dùng đúng convention mà runtime Java và framework đang sử dụng.

Khi tạo function, cần chọn runtime Java được AWS Lambda hỗ trợ tại thời điểm triển khai. Danh sách runtime được cập nhật theo vòng đời hỗ trợ của AWS; không nên sao chép một phiên bản Java cũ từ ví dụ mà không kiểm tra trạng thái hỗ trợ hiện hành. Runtime phải tương thích với bytecode, thư viện và native dependency của ứng dụng.

## 4. Đóng gói Java Lambda bằng JAR

### 4.1. Thin JAR và uber JAR

Có hai cách tổ chức JAR thường gặp:

- **Thin JAR:** chỉ chứa class và resource của ứng dụng. Dependency được đặt riêng, ví dụ trong thư mục lib.
- **Uber JAR / fat JAR:** chứa class của ứng dụng cùng nội dung dependency đã được gộp vào một archive.

Thin JAR có artifact ứng dụng nhỏ hơn và giữ dependency tách biệt. Uber JAR thuận tiện khi triển khai một file, nhưng cần xử lý cẩn thận tài nguyên trùng tên, service provider và chữ ký thư viện.

Nếu upload một JAR trực tiếp làm deployment package, JAR đó phải chứa đủ dependency cần thiết (thường là uber JAR), hoặc function phải nhận được dependency qua một layer tương thích. Một thin JAR đứng riêng không tự mang theo các thư viện Maven/Gradle bên ngoài.

Không nên mặc định mọi JAR sinh ra từ Maven hoặc Gradle đều chứa đầy đủ dependency. JAR mặc định có thể chỉ chứa class của dự án. Hãy kiểm tra nội dung archive trước khi upload.

### 4.2. Tạo uber JAR bằng Maven Shade Plugin

Ví dụ cấu hình plugin trong pom.xml:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-shade-plugin</artifactId>
      <version>3.6.0</version>
      <executions>
        <execution>
          <phase>package</phase>
          <goals>
            <goal>shade</goal>
          </goals>
          <configuration>
            <createDependencyReducedPom>false</createDependencyReducedPom>
            <transformers>
              <transformer implementation=
                "org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
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

Build:

~~~bash
mvn clean package
~~~

Maven Shade Plugin tạo JAR đã gộp dependency trong thư mục target theo cấu hình artifact của dự án. Transformer cho service resource giúp hợp nhất các file đăng ký Service Provider Interface (SPI) khi nhiều dependency cùng khai báo provider. Bộ lọc chữ ký loại các file chữ ký cũ vì nội dung JAR đã được đóng gói lại; không được xóa hoặc bỏ qua cơ chế xác minh chữ ký theo một chính sách bảo mật khác mà dự án yêu cầu.

Nếu dùng thư viện có cấu hình hoặc resource trùng tên, cần kiểm tra cách plugin hợp nhất. Gộp JAR không tự giải quyết mọi xung đột dependency.

### 4.3. Tạo JAR bằng Gradle

Với Gradle, có thể dùng plugin Shadow để tạo uber JAR. Khai báo plugin và cấu hình phiên bản theo chính sách dependency của dự án, sau đó chạy:

~~~bash
./gradlew clean shadowJar
~~~

Artifact thường được tạo trong build/libs. Cần kiểm tra tên file, manifest nếu ứng dụng cần, service resource và các file cấu hình trước khi triển khai.

### 4.4. Khi nào nên dùng JAR?

JAR phù hợp khi:

- Function Java có cấu trúc đơn giản.
- Muốn một artifact dễ lưu, ký, kiểm tra và chuyển giữa các môi trường.
- Dependency không quá lớn hoặc có thể gộp vào uber JAR.
- Không cần kiểm soát hệ điều hành bằng container image.

JAR không làm giảm kích thước dependency một cách tự động. Một uber JAR có thể lớn hơn thin JAR vì nó chứa toàn bộ thư viện. Hãy đo kích thước và kiểm tra classpath thay vì chỉ dựa vào phần mở rộng file.

## 5. Đóng gói ZIP với class và dependency riêng

Một ZIP package Java có thể chứa class ứng dụng tại thư mục gốc và dependency JAR trong thư mục lib.

Cấu trúc minh họa:

~~~text
function.zip
├── com/
│   └── example/
│       └── orders/
│           ├── OrderHandler.class
│           ├── OrderEvent.class
│           └── OrderResult.class
├── application.properties
└── lib/
    ├── jackson-databind.jar
    ├── jackson-core.jar
    ├── jackson-annotations.jar
    └── aws-lambda-java-core.jar
~~~

Lambda Java runtime tìm các class trong package và dependency JAR ở vị trí classpath được quy định. Với ZIP Java thông thường, đặt dependency JAR trong thư mục lib ở gốc archive.

Một quy trình Maven tổng quát:

~~~bash
mvn clean package
mvn dependency:copy-dependencies \
  -DincludeScope=runtime \
  -DoutputDirectory=target/dependency

mkdir -p target/lambda/lib
cp -R target/classes/. target/lambda/
cp target/dependency/*.jar target/lambda/lib/
(cd target/lambda && zip -r ../function.zip .)
~~~

Các lệnh copy và zip trên dùng cú pháp shell kiểu Unix. Trên Windows PowerShell, thay bằng lệnh tạo thư mục và copy tương ứng; cấu trúc bên trong ZIP phải giữ nguyên.

Nếu dùng uber JAR, có thể triển khai archive JAR như package Java hoặc đặt JAR ở vị trí lib trong một ZIP package. Không tạo một ZIP có thêm một thư mục cha không cần thiết, chẳng hạn archive chứa toàn bộ thư mục target/function thay vì nội dung của function. Runtime cần nhìn thấy classpath ở đúng cấp thư mục.

### 5.1. Kiểm tra nội dung ZIP

Trước khi upload, kiểm tra:

- Handler class có tồn tại đúng package.
- Dependency cần ở runtime nằm trong archive.
- Resource được đóng gói ở đường dẫn mà ứng dụng đọc.
- Không vô tình đóng gói file test, source code hoặc cache build không cần thiết.
- Không có credential, secret hoặc file môi trường local.
- Không có dependency version xung đột.
- ZIP không có thêm một lớp thư mục gốc ngoài ý muốn.

Có thể xem danh sách file bằng lệnh:

~~~bash
unzip -l target/function.zip
~~~

Nếu không có công cụ unzip, dùng lệnh jar hoặc công cụ archive tương đương để kiểm tra nội dung. Việc archive mở được chưa chứng minh handler có thể nạp; nên có bước kiểm tra classpath hoặc smoke test.

## 6. Triển khai ZIP/JAR lên AWS Lambda

Khi tạo function, chọn package type Zip, runtime Java phù hợp, handler, execution role và file archive. Ví dụ AWS CLI minh họa:

~~~bash
aws lambda create-function \
  --function-name order-handler \
  --runtime java21 \
  --handler com.example.orders.OrderHandler \
  --role arn:aws:iam::123456789012:role/lambda-execution-role \
  --zip-file fileb://target/function.zip
~~~

Tên runtime trong ví dụ cần được xác nhận còn được AWS hỗ trợ ở thời điểm triển khai. ARN role là giá trị minh họa; phải thay bằng execution role thực tế có quyền tối thiểu cần thiết.

Với Java, có thể upload trực tiếp một JAR đã đóng gói đầy đủ bằng tham số --zip-file, ví dụ thay đường dẫn function.zip bằng target/order-function.jar. Lambda vẫn dùng package type Zip; JAR là archive Java mà dịch vụ có thể đọc. Chỉ dùng cách này khi JAR chứa đủ class và dependency, hoặc các dependency còn thiếu được cung cấp qua layer đã gắn.

Để cập nhật mã function đã tồn tại:

~~~bash
aws lambda update-function-code \
  --function-name order-handler \
  --zip-file fileb://target/function.zip
~~~

Nếu archive vượt giới hạn upload trực tiếp, đưa artifact lên Amazon S3 rồi dùng tham chiếu S3 trong lệnh cập nhật hoặc tạo function. Bucket phải ở Region phù hợp với function theo yêu cầu của API triển khai.

Với hệ thống production, nên triển khai bằng AWS SAM, AWS CDK, CloudFormation hoặc công cụ IaC tương đương để lưu cấu hình runtime, handler, memory, timeout, environment variables, layers, role và concurrency cùng với mã nguồn.

## 7. Lambda layers là gì?

Lambda layer là một archive ZIP chứa thư viện, runtime component hoặc dữ liệu dùng chung. Khi gắn layer vào function, Lambda giải nén nội dung layer vào thư mục /opt trong execution environment.

Layer hữu ích khi nhiều function cần dùng cùng một thư viện hoặc extension. Ví dụ, nhiều function Java trong cùng hệ thống cùng dùng một thư viện nội bộ, bộ chứng thư hoặc thành phần giám sát.

Một layer Java thường có cấu trúc:

~~~text
shared-java-layer.zip
└── java/
    └── lib/
        ├── company-common.jar
        ├── jackson-databind.jar
        └── shared-security.jar
~~~

Đối với Java, đặt thư viện trong java/lib ở gốc layer để runtime có thể đưa chúng vào classpath. Nội dung layer được giải nén dưới /opt; do đó thư viện có thể xuất hiện dưới /opt/java/lib.

Theo cách tổ chức thông dụng, handler riêng của function nằm trong deployment package của function; layer dành cho thư viện và thành phần dùng chung. Về mặt kỹ thuật, class trong layer cũng có thể nằm trên classpath, nhưng đưa handler riêng vào layer thường làm ranh giới triển khai và tái sử dụng khó quản lý hơn.

### 7.1. Tạo và publish layer

Sau khi tạo archive theo cấu trúc đúng, publish layer version bằng AWS CLI:

~~~bash
aws lambda publish-layer-version \
  --layer-name shared-java-dependencies \
  --zip-file fileb://shared-java-layer.zip \
  --compatible-runtimes java21 \
  --compatible-architectures x86_64 arm64
~~~

Ví dụ runtime cần được xác nhận theo danh sách hỗ trợ hiện hành. Chỉ khai báo architecture mà thư viện trong layer thực sự hỗ trợ. Nếu layer chứa native library, không đánh dấu tương thích với cả x86_64 và arm64 khi binary chỉ được build cho một kiến trúc.

Kết quả publish trả về ARN có số version. Gắn đúng version đó vào function:

~~~bash
aws lambda update-function-configuration \
  --function-name order-handler \
  --layers arn:aws:lambda:ap-southeast-1:123456789012:layer:shared-java-dependencies:3
~~~

Layer version là bất biến sau khi publish. Khi thay đổi thư viện, publish version mới rồi cập nhật function để tham chiếu version mới. Việc này giúp deployment có thể tái lập và rollback về layer version cũ.

### 7.2. Giới hạn và đánh đổi của layer

Một function có thể gắn tối đa 5 layer. Tổng kích thước giải nén của deployment package cùng tất cả layer không được vượt giới hạn kích thước package giải nén của Lambda.

Layer giúp tránh sao chép cùng thư viện trong nhiều ZIP, nhưng cũng tạo thêm phụ thuộc phiên bản. Nếu layer thay đổi mà function không được cập nhật đúng version, có thể phát sinh khác biệt giữa môi trường. Nếu hai layer chứa cùng thư viện hoặc cùng class, classpath có thể gặp xung đột.

Không nên tách mọi dependency thành layer chỉ để làm ZIP nhỏ hơn. Chỉ tạo layer khi có nhiều function thực sự dùng chung thành phần và có quy trình quản lý version rõ ràng.

### 7.3. Khi nào nên dùng layer?

Nên cân nhắc layer khi:

- Nhiều function dùng cùng thư viện nội bộ.
- Có thành phần quan sát, chứng thư hoặc công cụ hỗ trợ dùng chung.
- Muốn cập nhật dependency dùng chung có kiểm soát.
- Cần tách lifecycle của thư viện khỏi lifecycle code nghiệp vụ.

Không nên dùng layer nếu chỉ một function cần dependency đó, nếu việc chia nhỏ làm tăng phức tạp hoặc nếu container image đã là mô hình triển khai phù hợp hơn.

## 8. Đóng gói Lambda bằng container image

Container image cho phép đóng gói ứng dụng Java cùng runtime, thư viện hệ điều hành và công cụ cần thiết. Lambda tải image từ Amazon ECR và chạy image theo hợp đồng Lambda Runtime API.

Container image phù hợp khi:

- Ứng dụng cần thư viện hệ điều hành hoặc native dependency đặc thù.
- Build hiện tại đã dùng Docker/OCI làm artifact chuẩn.
- Muốn kiểm soát môi trường runtime và công cụ đi kèm.
- Dependency hoặc tài nguyên của ứng dụng khiến cách ZIP khó quản lý.
- Nhóm phát triển đã có quy trình build, scan, push và triển khai image.

Image Lambda phải dựa trên Linux và hỗ trợ một kiến trúc CPU tương thích với cấu hình function. Lambda hỗ trợ image theo một kiến trúc tại một thời điểm, chẳng hạn x86_64 hoặc arm64; không dùng một multi-architecture manifest như thể function tự chọn kiến trúc lúc chạy.

### 8.1. Dùng AWS Lambda base image cho Java

AWS cung cấp base image tương ứng với các runtime Lambda. Base image bao gồm thành phần runtime và Runtime Interface Client phù hợp để nhận invocation từ Lambda service.

Ví dụ Dockerfile dùng base image Java:

~~~dockerfile
FROM public.ecr.aws/lambda/java:21

COPY target/order-function.jar $LAMBDA_TASK_ROOT/lib/

CMD ["com.example.orders.OrderHandler::handleRequest"]
~~~

Ví dụ giả định JAR đã chứa code ứng dụng và dependency cần thiết. Nếu dùng thin JAR, phải copy thêm dependency JAR vào thư mục lib phù hợp. Cần kiểm tra classpath mà base image Java sử dụng và tên handler đúng với artifact.

Không nên dùng tag runtime trong ví dụ mà không xác nhận runtime đó đang được hỗ trợ. Có thể cố định base image bằng digest để tăng khả năng tái lập build, đồng thời cập nhật digest định kỳ khi cần nhận bản vá bảo mật.

### 8.2. Build image

Ví dụ build image cho kiến trúc x86_64:

~~~bash
docker buildx build \
  --platform linux/amd64 \
  -t order-handler:1.0.0 \
  .
~~~

Với kiến trúc arm64, dùng platform linux/arm64 và bảo đảm native dependency được build đúng kiến trúc. Không build image trên Windows hoặc macOS theo kiến trúc host rồi giả định image đó tương thích Lambda; cần chỉ định target platform rõ ràng.

### 8.3. Đẩy image lên Amazon ECR

Tạo repository nếu chưa có:

~~~bash
aws ecr create-repository \
  --repository-name order-handler \
  --image-scanning-configuration scanOnPush=true
~~~

Đăng nhập Docker vào ECR:

~~~bash
aws ecr get-login-password --region ap-southeast-1 |
  docker login --username AWS --password-stdin \
  123456789012.dkr.ecr.ap-southeast-1.amazonaws.com
~~~

Gắn tag và push:

~~~bash
docker tag order-handler:1.0.0 \
  123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/order-handler:1.0.0

docker push \
  123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/order-handler:1.0.0
~~~

Ví dụ dùng Region và account ID minh họa. Repository ECR phải đáp ứng yêu cầu Region của Lambda function. Với cross-account image, cần thiết lập quyền repository để Lambda service có thể lấy image.

### 8.4. Tạo hoặc cập nhật function dùng image

Tạo function với package type Image:

~~~bash
aws lambda create-function \
  --function-name order-handler-image \
  --package-type Image \
  --code ImageUri=123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/order-handler:1.0.0 \
  --role arn:aws:iam::123456789012:role/lambda-execution-role
~~~

Với image package, không cấu hình runtime và handler theo cách của ZIP package nếu handler đã được chỉ định trong image CMD hoặc image configuration. Có thể override command trong cấu hình Lambda khi cần.

Khi phát hành image mới, cần cập nhật function code để Lambda dùng digest mới:

~~~bash
aws lambda update-function-code \
  --function-name order-handler-image \
  --image-uri 123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/order-handler:1.0.1
~~~

Lambda phân giải tag thành image digest khi tạo hoặc cập nhật function. Nếu chỉ push image mới lên cùng một tag mà không cập nhật function, function hiện tại không tự động chuyển sang digest mới. Nên dùng tag bất biến theo version hoặc commit và thực hiện update-function-code trong pipeline.

## 9. Dùng custom base image

Có thể dùng image Linux khác thay cho AWS Lambda base image. Khi đó, image phải có **Lambda Runtime Interface Client (RIC)** để giao tiếp với Lambda Runtime API và chuyển invocation đến handler. RIC là thành phần cần thiết trong môi trường container không dùng base image Lambda đã tích hợp sẵn client.

Với Java, cần thêm dependency Runtime Interface Client phù hợp và cấu hình entrypoint khởi chạy client. Phải bảo đảm runtime, classpath, handler và hệ điều hành tương thích. Không thể chỉ đưa một JAR vào bất kỳ image Java nào rồi kỳ vọng Lambda tự hiểu cách gọi handler.

AWS cung cấp Runtime Interface Emulator (RIE) để hỗ trợ chạy thử container Lambda trên máy local. RIE mô phỏng một phần giao tiếp invocation để kiểm thử tích hợp; nó không thay thế môi trường Lambda thật và không xác nhận quyền IAM, VPC, ECR hoặc các dịch vụ AWS đã cấu hình đúng.

## 10. Giới hạn kích thước và tài nguyên đóng gói

Kích thước artifact ảnh hưởng upload, thời gian tải, dung lượng lưu trữ và khả năng khởi tạo. Cần phân biệt kích thước nén và kích thước sau giải nén.

Các quota Lambda phổ biến cần kiểm tra trong tài liệu AWS tại thời điểm triển khai:

| Loại giới hạn | Giá trị thường áp dụng | Ý nghĩa |
|---|---:|---|
| ZIP upload trực tiếp qua API/console | 50 MB | Gói lớn hơn cần tải qua S3 |
| Tổng package sau giải nén, gồm layer | 250 MB | Bao gồm code, dependency và layer |
| Container image sau giải nén | 10 GB | Giới hạn kích thước image |
| Số layer gắn vào một function | 5 | Tổng package vẫn phải trong quota giải nén |

Quota dịch vụ có thể thay đổi. Hãy kiểm tra AWS Lambda quotas chính thức trước khi thiết kế artifact hoặc pipeline production. Khi dùng ZIP lớn hơn giới hạn upload trực tiếp, S3 là phương án truyền deployment package; nó không làm tăng giới hạn package sau giải nén.

Cần tối ưu kích thước bằng cách:

- Chỉ đóng gói dependency cần ở runtime.
- Không đưa test framework, source code, cache build hoặc tài liệu không dùng vào artifact.
- Loại dependency trùng và kiểm tra dependency tree.
- Dùng thin JAR và lib khi cần quản lý thư viện riêng.
- Dùng layer cho dependency dùng chung thực sự.
- Chỉ đưa file hệ điều hành cần thiết vào container image.
- Dùng multi-stage build để không đưa compiler và build cache vào runtime image.

Không loại bỏ file chỉ vì tên có vẻ không cần thiết. Một số thư viện cần resource, service descriptor, native library hoặc metadata trong META-INF để hoạt động đúng.

## 11. Native dependency và kiến trúc CPU

Java bytecode thường chạy trên nhiều kiến trúc JVM, nhưng dependency native không có tính di động như vậy. Thư viện dùng JNI, Netty native transport, image processing hoặc database driver có thể chứa binary riêng cho Linux x86_64 hoặc arm64.

Khi đóng gói, cần kiểm tra:

- Function dùng kiến trúc x86_64 hay arm64.
- Native binary được build cho Linux, không phải Windows hoặc macOS.
- libc và các thư viện hệ điều hành có tương thích với runtime image không.
- Layer và container image có cùng kiến trúc với function không.
- Dependency có fallback thuần Java hay bắt buộc native library.

Một JAR có thể chứa native library cho nhiều nền tảng, nhưng runtime chỉ có thể nạp binary phù hợp với hệ điều hành và kiến trúc hiện tại. Nếu thư viện không cung cấp binary tương thích, function có thể lỗi khi nạp class hoặc gọi native method.

## 12. Quản lý dependency và classpath

Class path là danh sách vị trí JVM tìm class và resource. Lỗi classpath thường biểu hiện bằng ClassNotFoundException, NoClassDefFoundError hoặc lỗi khởi tạo service provider.

Các nguyên tắc:

- Khai báo dependency có version rõ ràng.
- Dùng dependency tree để tìm nhiều phiên bản cùng một thư viện.
- Tránh đóng gói trùng dependency giữa JAR ứng dụng và layer nếu không cần.
- Kiểm tra META-INF/services khi dùng SPI.
- Kiểm tra resource có cùng tên giữa các JAR sau khi shade.
- Không phụ thuộc vào thư viện ngẫu nhiên có sẵn trong runtime.
- Đóng gói phiên bản AWS SDK hoặc thư viện khác mà ứng dụng yêu cầu để kiểm soát hành vi.

Khi dùng Lambda layer, cần xác định thư viện nào nằm trong function package và thư viện nào nằm trong layer. Nếu cùng một class xuất hiện ở nhiều vị trí, kết quả nạp có thể phụ thuộc classpath order và runtime. Cách an toàn là có một nguồn version rõ ràng cho từng dependency.

## 13. Cold start và thời gian khởi tạo

Cold start là khoảng thời gian Lambda chuẩn bị execution environment mới trước khi xử lý invocation. Kích thước artifact và cách đóng gói có thể ảnh hưởng thời gian tải, giải nén hoặc khởi tạo, nhưng không có quy tắc đơn giản rằng ZIP luôn nhanh hơn container hoặc ngược lại.

Các yếu tố cần xem xét:

- Kích thước archive hoặc image.
- Số lượng dependency và thời gian nạp class.
- Công việc static initialization.
- Khởi tạo framework, dependency injection và client.
- Kết nối database hoặc dịch vụ bên ngoài trong giai đoạn init.
- Native library và thao tác filesystem.

Một số cách giảm chi phí khởi tạo:

- Loại bỏ dependency không dùng.
- Tái sử dụng client và ObjectMapper sau khi cấu hình.
- Tránh scan classpath quá rộng nếu framework cho phép cấu hình hẹp.
- Không tạo kết nối database hoặc tải dữ liệu lớn nếu invocation không cần.
- Đo thời gian init và duration riêng trong telemetry.
- Cân nhắc tính năng tối ưu khởi tạo của Lambda nếu runtime và package type hỗ trợ.

Đừng đánh đổi khả năng bảo trì hoặc bảo mật để giảm vài KB. Hãy đo cold start trên artifact thực tế và lưu ý rằng kết quả phụ thuộc runtime, memory, kiến trúc CPU, cấu hình và trạng thái tải.

## 14. Bảo mật artifact và chuỗi cung ứng phần mềm

Deployment package và image là một phần của chuỗi cung ứng phần mềm. Nếu artifact chứa secret hoặc dependency có lỗ hổng, rủi ro được đưa thẳng vào môi trường chạy.

Các biện pháp nên áp dụng:

- Không đóng gói password, API key, private key hoặc file .env thật.
- Lấy secret lúc chạy từ AWS Secrets Manager, Systems Manager Parameter Store hoặc cơ chế phù hợp.
- Quét dependency và image để phát hiện lỗ hổng đã biết.
- Quản lý license của thư viện bên thứ ba.
- Tạo Software Bill of Materials (SBOM) nếu quy trình tổ chức yêu cầu.
- Pin dependency và base image theo version/digest có kiểm soát.
- Ký và xác minh artifact theo chính sách triển khai.
- Giới hạn quyền đọc ECR, cập nhật function và publish layer.
- Dùng IAM execution role với quyền tối thiểu.
- Không đưa dữ liệu nhạy cảm vào Docker build argument hoặc image layer.

Với ZIP package, AWS Lambda hỗ trợ code signing configuration để chỉ cho phép package được ký bởi profile được tin cậy theo cấu hình. Container image cần áp dụng cơ chế kiểm soát image, ECR scanning, chính sách ký và quy trình phê duyệt tương ứng. Không giả định code signing cho ZIP tự động bảo vệ image.

## 15. Tích hợp build và deploy bằng CI/CD

Một pipeline triển khai Java Lambda nên có các bước có thể tái lập:

~~~mermaid
flowchart TD
    A["Commit source"] --> B["Compile và unit test"]
    B --> C["Resolve dependency"]
    C --> D["Build ZIP/JAR hoặc image"]
    D --> E["Inspect package và scan"]
    E --> F["Publish artifact / push ECR"]
    F --> G["Deploy Lambda"]
    G --> H["Smoke test"]
    H --> I["Promote version / alias"]
~~~

Với ZIP/JAR, pipeline build archive, kiểm tra classpath, scan dependency và upload artifact lên S3 hoặc deploy qua SAM/CDK.

Với container image, pipeline build đúng target architecture, scan image, push lên ECR, sau đó cập nhật Lambda bằng image URI hoặc digest. Không dùng tag latest như cơ chế duy nhất để xác định bản phát hành trong production.

Nên tách build artifact khỏi bước deploy môi trường. Cùng một artifact đã được kiểm tra có thể được promote qua dev, staging và production; chỉ cấu hình runtime, environment variable, role, VPC và alias thay đổi theo môi trường.

## 16. Rollback và quản lý version

Một bản triển khai cần có khả năng quay lại artifact đã biết là tốt. Với ZIP/JAR, lưu artifact có version hoặc checksum và giữ lại bản trước đó. Với layer, function tham chiếu ARN của một layer version cụ thể. Với image, dùng tag bất biến và lưu digest.

Lambda version và alias có thể giúp quản lý phát hành. Một version đã publish là snapshot cấu hình và code của function tại thời điểm publish; alias có thể trỏ đến version cụ thể và hỗ trợ chuyển traffic theo chiến lược triển khai phù hợp.

Rollback cần đồng bộ code, layer, environment configuration và schema tương thích. Nếu code mới đã ghi dữ liệu theo schema mới, quay lại code cũ có thể không an toàn. Cần thiết kế migration theo hướng tương thích trong giai đoạn chuyển đổi.

## 17. Chọn ZIP/JAR, layer hay container image?

| Tiêu chí | ZIP/JAR | ZIP + layer | Container image |
|---|---|---|---|
| Độ đơn giản | Cao với function Java thông thường | Trung bình, thêm quản lý layer version | Cần Docker và ECR |
| Dependency dùng chung | Có thể phải lặp trong từng package | Phù hợp khi nhiều function dùng chung | Có thể dùng base image chung |
| Kiểm soát OS | Hạn chế theo managed runtime | Hạn chế theo managed runtime | Cao hơn |
| Kích thước | Hợp với package vừa và nhỏ | Tổng quota package/layer vẫn áp dụng | Hợp với image lớn hơn, theo quota image |
| Quy trình build | Maven/Gradle và archive | Build thêm layer archive | Docker build, scan và push |
| Tính tái lập | Dựa vào archive và dependency pin | Cần pin layer version | Có thể pin base image và digest |
| Use case | Java handler tiêu chuẩn | Nhiều function chia sẻ thư viện | Native dependency hoặc môi trường tùy biến |

Có thể bắt đầu với ZIP/JAR khi dùng managed Java runtime và dependency ở mức phù hợp. Thêm layer khi nhiều function cần cùng thư viện. Chọn container image khi cần kiểm soát môi trường hoặc đã có quy trình container trưởng thành.

Không nên chọn container image chỉ vì dự án có Dockerfile, cũng không nên dùng layer chỉ để chia nhỏ một function đơn lẻ. Hãy xét lợi ích thực tế về tái sử dụng, kiểm soát runtime, kích thước, bảo mật và vận hành.

## 18. Ví dụ quy trình đóng gói một Order Lambda

Giả sử Order Lambda nhận HTTP request để tạo đơn, dùng Jackson để đọc JSON và AWS SDK để phát event sau khi lưu dữ liệu.

Quy trình đóng gói bằng ZIP/JAR:

1. Viết handler theo RequestHandler hoặc signature được runtime hỗ trợ.
2. Khai báo DTO, use case và adapter trong source.
3. Khai báo dependency runtime trong Maven hoặc Gradle.
4. Build uber JAR hoặc ZIP gồm class và dependency.
5. Kiểm tra handler class, resource và dependency.
6. Kiểm tra artifact không chứa secret.
7. Deploy ZIP package với runtime Java được hỗ trợ và handler đúng.
8. Cấu hình execution role, timeout, memory, environment variables và trigger.
9. Chạy smoke test qua HTTP hoặc test event.
10. Publish version và trỏ alias sau khi kiểm tra thành công.

Nếu có nhiều function cùng dùng thư viện nội bộ, có thể tách thư viện thành layer version dùng chung. Nếu ứng dụng cần native library hoặc OS package riêng, build container image từ Lambda base image hoặc image custom có RIC.

## 19. Các lỗi thường gặp khi đóng gói

**Thiếu dependency runtime:** JAR chỉ chứa class ứng dụng nên function lỗi NoClassDefFoundError. Kiểm tra dependency scope và nội dung archive.

**Đặt sai cấu trúc ZIP:** ZIP có thêm thư mục cha khiến runtime không tìm thấy class. Đóng gói nội dung từ thư mục staging ở gốc archive.

**Handler sai tên:** Class hoặc method trong cấu hình không khớp artifact. Kiểm tra package, class, method và signature.

**Dùng JAR không phải uber JAR:** Nghĩ rằng JAR mặc định chứa dependency. Kiểm tra nội dung và chọn thin JAR + lib hoặc uber JAR.

**Xung đột dependency:** Nhiều phiên bản thư viện hoặc service descriptor bị ghi đè. Kiểm tra dependency tree và transformer khi shade.

**Layer chứa sai đường dẫn:** Thư viện Java không nằm trong java/lib nên không được nạp đúng cách. Kiểm tra cấu trúc archive trước khi publish.

**Layer version không được cập nhật:** Publish version mới nhưng function vẫn tham chiếu version cũ. Cập nhật cấu hình function với ARN version mới.

**Vượt giới hạn kích thước:** Chỉ nhìn kích thước ZIP nén mà quên tổng dung lượng sau giải nén và layer. Kiểm tra cả hai trước deploy.

**Image sai kiến trúc:** Build trên máy ARM nhưng function dùng x86_64 hoặc ngược lại. Chỉ định platform khi build và khớp cấu hình Lambda.

**Container image thiếu RIC:** Dùng custom base image nhưng không thêm Runtime Interface Client. Dùng AWS base image hoặc cấu hình RIC đúng cách.

**Push image nhưng function không đổi:** Ghi đè tag ECR nhưng không gọi update-function-code. Triển khai bằng tag bất biến hoặc digest và cập nhật function.

**Đóng gói secret:** File .env hoặc credential bị đưa vào archive/image. Quét artifact và lấy secret lúc runtime.

## 20. Checklist trước khi triển khai

- [ ] Đã chọn ZIP/JAR hay container image dựa trên runtime và dependency.
- [ ] Handler class/method đúng với cấu hình Lambda.
- [ ] Java runtime còn được AWS hỗ trợ và tương thích bytecode.
- [ ] Artifact chứa đủ class, dependency và resource runtime.
- [ ] Dependency scope, version và service descriptor đã được kiểm tra.
- [ ] ZIP không có thư mục cha thừa.
- [ ] Nếu dùng layer, cấu trúc Java là java/lib và function tham chiếu đúng layer version.
- [ ] Tổng kích thước package giải nén và layer nằm trong quota.
- [ ] Nếu dùng image, image dựa trên Linux và có đúng runtime interface.
- [ ] Image chỉ build cho kiến trúc function đang dùng.
- [ ] Image được push lên ECR phù hợp Region và quyền truy cập.
- [ ] Sau khi push image mới, pipeline cập nhật Lambda bằng image URI/digest mới.
- [ ] Artifact/image không chứa secret hoặc file local không cần thiết.
- [ ] Dependency và image đã được scan theo chính sách.
- [ ] Có checksum, version hoặc digest để tái lập và rollback.
- [ ] Đã chạy smoke test trên môi trường Lambda.
- [ ] Đã đo kích thước artifact, init duration, cold start và invocation duration.

## Kết luận

Java Lambda có thể được đóng gói dưới dạng ZIP hoặc JAR khi dùng managed Java runtime. ZIP chứa class, resource và dependency ở cấu trúc runtime có thể nạp; JAR có thể là thin JAR hoặc uber JAR tùy cách quản lý classpath. Lambda layer bổ sung thư viện dùng chung vào /opt và được quản lý theo version. Container image đóng gói runtime cùng ứng dụng, được lưu trong ECR và phù hợp khi cần môi trường Linux hoặc dependency tùy biến.

Lựa chọn nên dựa trên kích thước, dependency, native library, khả năng tái sử dụng, cold start, bảo mật và năng lực CI/CD. Dù dùng cách nào, cần kiểm tra handler, classpath, runtime, kiến trúc CPU, quota và nội dung artifact trước khi deploy. Một quy trình build có version, scan, smoke test và rollback rõ ràng giúp Lambda chạy nhất quán giữa các môi trường.

