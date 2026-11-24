# Lỗi tương thích SDK, classpath, Netty hoặc mô hình blocking/reactive

Một ứng dụng Spring Boot tích hợp nhiều cloud provider có thể biên dịch thành công nhưng lỗi khi khởi động, hoặc chỉ lỗi khi gọi một dịch vụ cụ thể. Dấu hiệu thường gặp là NoSuchMethodError, NoClassDefFoundError, ClassNotFoundException, AbstractMethodError, ALPN is not configured properly, lỗi tạo Netty channel, UnsatisfiedLinkError, timeout tăng đột biến hoặc WebFlux bị nghẽn event loop.

Những lỗi này thường thuộc một trong bốn nhóm:

1. **Không tương thích phiên bản nền tảng:** Spring Boot, Spring Framework, Spring Cloud release train và starter của provider thuộc các dòng không hỗ trợ lẫn nhau.
2. **Xung đột dependency/classpath:** nhiều phiên bản của Netty, Reactor, gRPC, protobuf, Guava, AWS SDK hoặc API Jakarta/Java EE cùng xuất hiện.
3. **HTTP transport không phù hợp:** client sync/async dùng sai transport, thiếu implementation, connection pool hoặc native library không tương thích.
4. **Sai mô hình xử lý I/O:** gọi thư viện blocking trên WebFlux event-loop, dùng reactive publisher mà không return/compose đúng cách, hoặc tạo quá nhiều thread và connection.

Không nên sửa lỗi bằng cách nâng tất cả dependency lên phiên bản mới nhất hoặc thêm một bản Netty ngẫu nhiên. Cần xác định dependency nào được chọn trong runtime, thư viện nào yêu cầu phiên bản đó, và request đang chạy trên thread model nào. Sau đó mới điều chỉnh BOM, loại bỏ dependency override hoặc chuyển sang client phù hợp.

Bài này hướng dẫn đọc compatibility matrix, phân tích dependency tree bằng Maven/Gradle, xử lý xung đột giữa AWS SDK, Azure SDK, Google Cloud libraries và Netty, phân biệt API blocking/reactive, rồi kiểm chứng bằng build và integration test.

## 1. Nhận diện triệu chứng theo lớp lỗi

| Triệu chứng | Lớp có khả năng lỗi | Dấu hiệu cần tìm |
| --- | --- | --- |
| Ứng dụng không khởi động, thiếu class | Classpath hoặc starter | ClassNotFoundException, NoClassDefFoundError, auto-configuration condition không match |
| Chạy được nhưng lỗi khi gọi method | Binary incompatibility | NoSuchMethodError, NoSuchFieldError, AbstractMethodError |
| ClassCastException dù hai object có cùng tên class | Classloader hoặc duplicate class | Class được nạp từ hai JAR/classloader khác nhau |
| ALPN is not configured properly | gRPC/Netty/TLS runtime | Netty version conflict, thiếu ALPN/native support hoặc platform không tương thích |
| UnsatisfiedLinkError khi khởi tạo transport | Native Netty/CRT | Sai OS/CPU classifier, native library không tải được |
| WebFlux phản hồi chậm, toàn bộ request bị treo | Blocking trên event loop | Thread dump có block(), JDBC, sync SDK call trên reactor-http-nio |
| PoolAcquireTimeoutException hoặc pending acquire tăng | Connection pool | Thiếu connection, request giữ connection quá lâu, không consume/close body |
| AWS async client không có HTTP implementation | HTTP client dependency | Loại netty-nio-client/CRT bị exclude hoặc không có async transport |
| Azure SDK không tạo được HttpClient | Azure HTTP transport | Đã exclude azure-core-http-netty nhưng chưa thêm OkHttp/JDK HttpClient |
| Google Cloud client lỗi linkage ở runtime | gRPC/Guava/protobuf/Netty | Version khác với Google Cloud Libraries BOM hoặc runtime thêm JAR ngoài |

**Quy tắc đầu tiên:** đọc exception sâu nhất (Caused by) và tên class/method bị thiếu. Exception ngoài cùng thường chỉ mô tả nơi lỗi được phát hiện, còn exception gốc chỉ ra dependency hoặc transport cần điều tra.

## 2. Chốt compatibility matrix trước khi sửa dependency

### 2.1. Spring Boot và Spring Cloud release train

Spring Cloud release train được phát hành để tương thích với một thế hệ Spring Boot cụ thể. Không chọn hai phiên bản chỉ vì chúng là bản mới nhất tại Maven Central.

Bảng dưới đây là các cặp chính được công bố trong compatibility mapping của Spring tại thời điểm biên soạn:

| Spring Boot | Spring Cloud release train tương ứng |
| --- | --- |
| 4.0.x / 4.1.x | 2025.1.x (Oakwood; hỗ trợ Boot 4.1 từ patch release được chỉ rõ trong mapping) |
| 3.5.x | 2025.0.x (Northfields) |
| 3.4.x | 2024.0.x (Moorgate) |
| 3.2.x / 3.3.x | 2023.0.x (Leyton) |
| 3.0.x / 3.1.x | 2022.0.x (Kilburn) |
| 2.6.x / 2.7.x | 2021.0.x (Jubilee) |

Bảng này thể hiện compatibility, không khẳng định mọi dòng vẫn còn hỗ trợ bảo mật hoặc còn nhận bản vá. Kiểm tra support status và patch version trên trang Spring Cloud Supported Versions trước khi nâng cấp production.

### 2.2. Mapping của các thư viện cloud provider

Các thư viện provider có BOM và lịch phát hành riêng. Ví dụ mapping đang được công bố:

| Thư viện | Spring Boot / Spring Cloud tương ứng | Ghi chú |
| --- | --- | --- |
| Spring Cloud AWS 4.x | Boot 4.0.x / Spring Cloud 2025.1.x | Dùng AWS SDK for Java 2.x |
| Spring Cloud AWS 3.4.x | Boot 3.5.x / Spring Cloud 2025.0.x | Dùng AWS SDK for Java 2.x |
| Spring Cloud AWS 3.3.x | Boot 3.4.x / Spring Cloud 2024.0.x | Dùng AWS SDK for Java 2.x |
| Spring Cloud AWS 3.1.x–3.2.x | Boot 3.2.x–3.3.x / Spring Cloud 2023.0.x | Kiểm tra patch tương thích chính xác |
| Spring Cloud AWS 2.4.x | Boot 2.6.x–2.7.x / Spring Cloud 2021.0.x | Maintenance line, dùng AWS SDK for Java 1.x |
| Spring Cloud Azure 7.x | Boot 4.0.x / Spring Cloud 2025.1.x | Kiểm tra JDK range của patch |
| Spring Cloud Azure 6.x | Boot 3.5.x / Spring Cloud 2025.0.x | Dòng hiện đại cho Boot 3.5 |
| Spring Cloud Azure 5.x | Boot 3.2.x–3.5.x tùy patch và Spring Cloud train | Không suy rộng một patch cho toàn bộ dòng |
| Spring Framework on Google Cloud 8.x | Boot 4.0.x / 4.1.x, Spring Cloud 2025.1.x | Kiểm tra module-specific exception |
| Spring Framework on Google Cloud 7.x | Boot 3.5.x / Spring Cloud 2025.0.x | Spring Framework 6.2.8+ theo mapping |
| Spring Framework on Google Cloud 6.x | Boot 3.4.x / Spring Cloud 2024.0.x | Spring Framework 6.2.x |
| Spring Framework on Google Cloud 5.x | Boot 3.2.x / 3.3.x, Spring Cloud 2023.0.x | Module trace có ngoại lệ tương thích |

Các bảng này thay đổi theo patch release. Trước khi chọn version, đối chiếu ít nhất ba nguồn: Spring Boot/Cloud support mapping, BOM của provider và release notes của service starter cụ thể. Không dùng mapping của một provider để suy ra mapping cho provider khác.

### 2.3. Dấu hiệu trộn major version

- Spring Cloud AWS 2.x thuộc thế hệ AWS SDK v1; Spring Cloud AWS 3.x/4.x dùng SDK v2.
- Spring Boot 3.x chuyển sang Spring Framework 6 và Jakarta EE; nhiều API javax.* chuyển thành jakarta.*.
- Spring Cloud Azure 4.x trở lên dùng BOM hợp nhất spring-cloud-azure-dependencies; starter đời cũ azure-spring-* có thể thuộc cấu trúc trước đó.
- Spring Framework on Google Cloud có BOM riêng; các module trace/observability có thể có giới hạn khác với storage, Pub/Sub hoặc Secret Manager.
- Một ứng dụng có thể chứa nhiều AWS SDK hoặc nhiều HTTP client, nhưng việc chúng cùng tồn tại không có nghĩa auto-configuration, adapter hoặc model object của chúng tương thích.

Nếu stack trace có javax.servlet.* trong ứng dụng Boot 3/4, kiểm tra dependency cũ thay vì thêm javax.servlet-api để làm mất lỗi compile. Việc trộn API javax và jakarta thường tạo lỗi lúc deploy hoặc khi framework cast interface.

## 3. Dùng BOM để giữ các nhóm dependency nhất quán

### 3.1. Vai trò của từng BOM

| BOM | Phạm vi quản lý |
| --- | --- |
| spring-boot-dependencies | Spring Boot, Spring Framework và tập dependency nền được Boot kiểm thử |
| spring-cloud-dependencies | Spring Cloud release train |
| spring-cloud-aws-dependencies | Spring Cloud AWS starters và dependency liên quan |
| spring-cloud-azure-dependencies | Spring Cloud Azure starters và Azure SDK dependency set |
| spring-cloud-gcp-dependencies | Spring Framework on Google Cloud starters và dependency liên quan |
| libraries-bom | Google Cloud Java client libraries và nền tảng như gRPC, protobuf, Guava |

BOM là tập quy tắc chọn version, không phải dependency cần đóng gói trực tiếp. Khai báo starter mà BOM quản lý thì thường bỏ version trên từng starter.

### 3.2. Maven: import BOM theo nền tảng đang dùng

Ví dụ phần dependencyManagement dưới đây minh họa cấu trúc. Thay các property version bằng các phiên bản đã được đối chiếu trong compatibility matrix của dự án:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>SPRING_BOOT_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>SPRING_CLOUD_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <!-- Chỉ import BOM của provider thực sự được dùng. -->
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>SPRING_CLOUD_AWS_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>SPRING_CLOUD_AZURE_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>SPRING_CLOUD_GCP_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Nếu ứng dụng dùng Google Cloud Java client trực tiếp mà không dùng Spring Framework on Google Cloud starter, có thể cần com.google.cloud:libraries-bom thay cho BOM Spring GCP. Tránh import nhiều BOM quản lý cùng một artifact mà không hiểu thứ tự ưu tiên của Maven và version nào thực sự được chọn.

Ví dụ khai báo starter sau khi đã có BOM:

```xml
<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-s3</artifactId>
    </dependency>

    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
    </dependency>

    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-storage</artifactId>
    </dependency>
</dependencies>
```

Tên starter có thể thay đổi theo release line. Kiểm tra catalog của đúng BOM trước khi copy artifact ID vào dự án.

### 3.3. Gradle: dùng platform/BOM

Ví dụ Kotlin DSL:

```kotlin
dependencies {
    implementation(platform(
        "org.springframework.cloud:spring-cloud-dependencies:SPRING_CLOUD_VERSION"
    ))
    implementation(platform(
        "io.awspring.cloud:spring-cloud-aws-dependencies:SPRING_CLOUD_AWS_VERSION"
    ))
    implementation(platform(
        "com.azure.spring:spring-cloud-azure-dependencies:SPRING_CLOUD_AZURE_VERSION"
    ))
    implementation(platform(
        "com.google.cloud:spring-cloud-gcp-dependencies:SPRING_CLOUD_GCP_VERSION"
    ))

    implementation("io.awspring.cloud:spring-cloud-aws-starter-s3")
    implementation("com.azure.spring:spring-cloud-azure-starter-storage-blob")
    implementation("com.google.cloud:spring-cloud-gcp-starter-storage")
}
```

Khi dùng plugin Spring Boot, Boot BOM được áp dụng theo cấu hình plugin hoặc native Gradle platform support. Nếu dùng nhiều BOM, hãy kiểm tra dependency insight để biết version cuối cùng được chọn. Không thêm version trực tiếp lên một dependency chỉ để dập lỗi tạm thời.

### 3.4. Tránh override dependency nền tùy tiện

Các property như netty.version, reactor-bom.version, grpc.version, protobuf.version, guava.version hoặc slf4j.version có thể được BOM quản lý. Override một property có thể ảnh hưởng nhiều module cùng lúc.

Chỉ override khi:

1. Có advisory hoặc bug đã xác định cần bản vá.
2. Release notes của framework/provider xác nhận version đó tương thích.
3. Dependency tree cho thấy tất cả module liên quan sẽ cùng được cập nhật.
4. Build, linkage check và integration test đều chạy qua.

Không ép toàn bộ Netty sang một patch chỉ vì một thư viện yêu cầu patch mới hơn. Xác minh phiên bản tối thiểu của transport, module netty-common, netty-buffer, netty-codec, netty-transport, netty-handler, resolver và native artifact trước.

## 4. Đọc dependency tree và classpath thực tế

### 4.1. Maven

In dependency tree:

```bash
mvn dependency:tree -Dverbose
```

Lọc các nhóm thường liên quan tới sự cố:

```bash
mvn dependency:tree -Dverbose "-Dincludes=io.netty:*,io.projectreactor.netty:*,io.projectreactor:*,io.grpc:*,com.google.protobuf:*,com.google.guava:*,software.amazon.awssdk:*,com.amazonaws:*,com.azure:*,org.springframework:*"
```

Xem effective POM để biết BOM/property nào đã thắng:

```bash
mvn help:effective-pom
```

Tìm version mediation, đường dẫn transitive và dependency bị loại:

```bash
mvn dependency:tree -Dverbose -Dincludes=io.netty:netty-common
mvn dependency:tree -Dverbose -Dincludes=io.grpc:grpc-netty-shaded
mvn dependency:tree -Dverbose -Dincludes=software.amazon.awssdk:netty-nio-client
```

omitted for conflict cho biết Maven chọn một version khác theo mediation. Nó không tự chứng minh version được chọn là tương thích; so sánh version đó với BOM của từng thư viện.

### 4.2. Gradle

Xem toàn bộ runtime classpath:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Điều tra một artifact cụ thể:

```bash
./gradlew dependencyInsight --dependency netty-common --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-netty-http --configuration runtimeClasspath
./gradlew dependencyInsight --dependency grpc-netty-shaded --configuration runtimeClasspath
```

dependencyInsight cho biết dependency nào yêu cầu version, rule nào chọn version cuối cùng và có constraint nào tác động.

Trên Windows PowerShell, có thể chạy gradlew.bat thay cho ./gradlew.

### 4.3. So sánh compile classpath và runtime classpath

Một dependency có thể có ở compileClasspath nhưng không có trong runtimeClasspath, hoặc ngược lại do scope/exclusion. Ứng dụng có thể compile được nhưng thiếu transport khi chạy.

Kiểm tra cả:

- Compile classpath.
- Runtime classpath.
- Test runtime classpath.
- JAR thực tế trong image hoặc thư mục BOOT-INF/lib.
- Classpath do application server, Spark/Hadoop hoặc launcher bên ngoài bổ sung.

Nếu lỗi chỉ xảy ra ở production container, hãy so sánh nội dung JAR trong image với runtime tree của build. Dependency tree của máy phát triển không bao gồm JAR do nền tảng production tự thêm.

## 5. Các xung đột classpath thường gặp

### 5.1. AWS SDK for Java 1.x và 2.x

Hai major version có package khác nhau:

| Dòng SDK | Package chính |
| --- | --- |
| AWS SDK v1 | com.amazonaws.* |
| AWS SDK v2 | software.amazon.awssdk.* |

Spring Cloud AWS 2.x dùng SDK v1; Spring Cloud AWS 3.x/4.x dùng SDK v2. Nếu migration chưa hoàn tất, hai SDK có thể cùng tồn tại vì package khác nhau, nhưng:

- AmazonS3 và S3Client là hai API khác nhau.
- Credentials, request model, exception và HTTP client không dùng chung.
- Starter/autoconfiguration cũ có thể tạo bean khác kiểu hoặc yêu cầu property khác.
- BOM của SDK v1 không quản lý SDK v2 và ngược lại.

Không cast object SDK v1 sang SDK v2 hoặc truyền request model của một major version vào client major version kia. Chọn một major version cho code mới; nếu cần chạy song song trong migration, đặt adapter và bean name rõ ràng.

### 5.2. javax.* và jakarta.*

Spring Boot 3 trở lên dùng Jakarta EE namespace cho các API tương ứng. Ví dụ:

- javax.servlet.* → jakarta.servlet.*
- javax.persistence.* → jakarta.persistence.*
- javax.validation.* → jakarta.validation.*

Một dependency cũ có thể compile riêng nhưng không chạy cùng Servlet/JPA version của Boot 3/4. Tìm JAR cũ trong dependency tree, nâng thư viện lên dòng Jakarta hoặc thay adapter. Không thêm đồng thời cả hai API chỉ để ép compile nếu implementation runtime chỉ hỗ trợ một namespace.

### 5.3. Spring Framework 5/6/7 và Spring Cloud

Starter thường kéo transitive Spring modules. Nếu project dùng Boot 3 nhưng một starter cũ kéo Spring Framework 5, classpath có thể chứa API không tương thích.

Kiểm tra các artifact:

- org.springframework:spring-core
- org.springframework:spring-context
- org.springframework:spring-web
- org.springframework:spring-webflux
- org.springframework:spring-beans
- org.springframework:spring-aop

Các module Spring Framework trong một application context cần cùng release line. Dùng Spring Boot BOM và Spring Cloud BOM tương ứng thay vì pin riêng từng spring-* JAR.

### 5.4. SLF4J và logging implementation

Dấu hiệu thường gặp:

- NoSuchMethodError trong org.slf4j.
- NoClassDefFoundError: org/slf4j/impl/StaticLoggerBinder với binding cũ.
- Cảnh báo nhiều SLF4J providers/bindings.
- Log mất hoặc ghi hai lần do nhiều logging implementation cùng hoạt động.

Spring Boot quản lý logging stack tương thích. Không thêm slf4j-simple, log4j-slf4j-impl, logback-classic hoặc bridge tùy tiện nếu Boot đã cung cấp logging implementation. Chọn một backend và các bridge phù hợp với version SLF4J đang dùng.

### 5.5. Guava, protobuf và gRPC

Google Cloud Java libraries dùng các dependency nền như:

- Guava.
- protobuf-java.
- gRPC API/stub/core.
- GAX.
- Google Auth Library.
- HTTP transport.

Nếu một thư viện khác kéo Guava/protobuf quá cũ, lỗi có thể xuất hiện trong runtime khi Google client gọi method không có ở version đã chọn.

Ưu tiên spring-cloud-gcp-dependencies khi dùng Spring Framework on Google Cloud starter hoặc libraries-bom khi dùng trực tiếp Google Cloud Java clients. Không pin riêng protobuf/gRPC artifact nếu BOM đã quản lý chúng, trừ khi đã xác minh compatibility của cả nhóm.

## 6. Netty trong ứng dụng dùng nhiều cloud provider

### 6.1. Vì sao nhiều thư viện cùng kéo Netty?

Netty có thể xuất hiện từ các đường dependency khác nhau:

| Thành phần | Vai trò của Netty |
| --- | --- |
| Spring WebFlux / Reactor Netty | HTTP server và HTTP client non-blocking |
| AWS SDK v2 async | NettyNioAsyncHttpClient là async HTTP client mặc định |
| Azure SDK for Java | azure-core-http-netty là HTTP transport mặc định của Azure SDK |
| Google Cloud gRPC clients | Có thể dùng grpc-netty-shaded hoặc transport gRPC tương ứng |
| Một số SDK/connector khác | Có thể kéo Netty module hoặc native transport riêng |

Các thành phần này không nhất thiết dùng cùng một BOM. Khi chúng chia sẻ io.netty.* không-shaded trên cùng classloader, version mediation sai có thể tạo lỗi linkage.

### 6.2. Nhận biết Netty version skew

Các dấu hiệu:

- NoSuchMethodError trong io.netty.*.
- NoSuchFieldError ở ByteBuf, ChannelOption, SslContext hoặc class Netty khác.
- AbstractMethodError trong handler/codec.
- Lỗi tạo channel/event loop sau khi nâng một SDK.
- Chỉ một transport lỗi trong khi các HTTP client khác vẫn hoạt động.
- ClassNotFoundException cho module Netty mà transport cần.

Tìm toàn bộ nhóm io.netty trong runtime tree. Các module cùng dòng Netty phải được quản lý đồng bộ; không chỉ kiểm tra netty-all, vì nhiều SDK khai báo từng module riêng.

### 6.3. grpc-netty-shaded khác netty-* như thế nào?

grpc-netty-shaded đóng gói Netty dưới package đã relocate. Nó không giống việc thêm một bản io.netty:netty-transport thông thường vào classpath.

Không xóa grpc-netty-shaded chỉ vì thấy chữ Netty trong tên artifact. Xác định gRPC transport thực tế đang được Google client dùng. Nếu ứng dụng có cả Reactor Netty, Azure Netty và gRPC shaded transport, kiểm tra version của từng nhóm độc lập theo BOM tương ứng.

### 6.4. Không tự nâng Netty bằng một dependency đơn lẻ

Ví dụ lỗi thường gặp là thêm netty-handler phiên bản mới nhưng để netty-common, netty-buffer, netty-codec hoặc netty-transport ở phiên bản cũ do BOM khác chọn. Kết quả có thể tệ hơn vì class có mặt nhưng method signature không khớp.

Cách xử lý:

1. Tìm dependency đầu tiên đưa Netty vào tree.
2. Tìm tất cả module Netty và version được chọn.
3. Xác định BOM nào quản lý từng version.
4. Nâng BOM/starter tới patch tương thích nếu có.
5. Chỉ dùng dependency constraint/override có kiểm soát nếu vendor xác nhận.
6. Chạy linkage check và integration test trên runtime image.

### 6.5. AWS SDK v2: sync và async dùng HTTP client khác nhau

AWS SDK for Java 2.x phân biệt rõ:

| Service client | Mô hình | HTTP client thường dùng mặc định |
| --- | --- | --- |
| S3Client, SqsClient, DynamoDbClient | Synchronous | Apache-based sync HTTP client |
| S3AsyncClient, SqsAsyncClient, DynamoDbAsyncClient | Asynchronous | Netty-based async HTTP client |
| Async dùng CRT | Asynchronous | AWS Common Runtime HTTP client |

Nếu loại netty-nio-client khỏi classpath để giảm dependency nhưng vẫn tạo S3AsyncClient, SDK không còn async HTTP implementation phù hợp. Ngược lại, thêm Netty vào ứng dụng không tự biến S3Client sync thành non-blocking.

Có thể chọn HTTP client rõ ràng trong builder:

```java
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;

S3AsyncClient s3AsyncClient = S3AsyncClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .httpClientBuilder(NettyNioAsyncHttpClient.builder()
                .maxConcurrency(64))
        .build();
```

Đây là cấu hình minh họa; chọn concurrency theo tải, giới hạn service và pool. Không tạo client mới cho mỗi request. Tái sử dụng client theo lifecycle ứng dụng và đóng client khi shutdown.

Nếu chỉ dùng sync client và muốn giảm dependency, AWS SDK có URLConnection hoặc Apache-based client tùy phiên bản. Khi loại HTTP client mặc định, phải thêm implementation thay thế tương thích và kiểm tra tính năng HTTP method/timeout cần thiết.

### 6.6. Azure SDK for Java: Netty là HTTP client mặc định

Azure SDK dùng abstraction HttpClient; azure-core-http-netty là implementation mặc định phổ biến. Có thể dùng OkHttp hoặc JDK HttpClient nếu dependency set và JDK version đáp ứng yêu cầu.

Nếu exclude azure-core-http-netty, phải cung cấp implementation khác. Nếu loại Netty mà không thêm HTTP client thay thế, Azure SDK có thể lỗi khi tạo client hoặc gửi request.

Ví dụ tạo Azure HTTP client mặc định:

```java
import com.azure.core.http.HttpClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

HttpClient httpClient = HttpClient.createDefault();

BlobServiceClient blobClient =
        new BlobServiceClientBuilder()
                .endpoint(blobEndpoint)
                .credential(credential)
                .httpClient(httpClient)
                .buildClient();
```

Chỉ dùng HttpClient.createDefault() khi implementation mặc định có mặt trong classpath. Nếu dùng transport khác, thêm đúng artifact và cấu hình builder theo tài liệu Azure SDK. Đảm bảo version azure-core-http-netty đáp ứng minimum version được Microsoft công bố cho release đang dùng.

### 6.7. Google Cloud: gRPC transport và ALPN

Một số Google Cloud Java clients dùng gRPC. Lỗi ALPN is not configured properly thường cần kiểm tra:

- Java runtime và nền tảng được gRPC hỗ trợ.
- gRPC Java version.
- Netty/transport version.
- TLS provider và ALPN support.
- Classpath có nhiều phiên bản Netty, Guava hoặc protobuf không.
- Runtime container/server có thêm JAR khác với build artifact không.

Dùng compatibility checker và troubleshooting guide của Google Cloud Java. Đừng thêm netty-tcnative hoặc đổi JDK một cách mù quáng trước khi xem gRPC error và runtime compatibility.

## 7. Chọn blocking hay reactive cho đúng

### 7.1. Spring MVC và Spring WebFlux có thread model khác nhau

| Mô hình | Cách xử lý request | Blocking I/O |
| --- | --- | --- |
| Spring MVC / Servlet | Request được xử lý trên servlet thread pool | Có thể dùng sync SDK nếu giới hạn thread, timeout và connection pool phù hợp |
| Spring WebFlux | Event loop xử lý nhiều request với số thread nhỏ | Không gọi blocking API trực tiếp trên event-loop |
| Worker/background job | Tùy executor và workload | Có thể dùng blocking API trên thread pool chuyên biệt |
| Reactive pipeline xuyên suốt | Truyền Mono/Flux tới tầng gọi | Ưu tiên async/reactive SDK và không gọi block() trong pipeline |

WebFlux không làm cho mọi thư viện Java trở thành non-blocking. Một controller trả về Mono nhưng bên trong gọi JDBC, S3Client sync hoặc Storage.get() vẫn có thể chặn event-loop nếu không chuyển sang scheduler dành cho blocking work.

### 7.2. AWS SDK v2: S3Client và S3AsyncClient

Sync API:

```java
HeadObjectResponse response = s3Client.headObject(request);
```

Lệnh trên block thread gọi nó cho tới khi nhận response. Trong Spring MVC, điều này có thể phù hợp nếu thread pool và timeout được cấu hình đúng.

Trong WebFlux, có thể bọc một lời gọi blocking trên boundedElastic:

Giả sử s3Client và HeadObjectRequest request đã được tạo/inject trước đó:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<HeadObjectResponse> result =
        Mono.fromCallable(() -> s3Client.headObject(request))
                .subscribeOn(Schedulers.boundedElastic());
```

Đây là cầu nối cho thư viện blocking, không biến SDK sync thành non-blocking. Giới hạn concurrency và theo dõi hàng đợi boundedElastic; không dùng cách này để che một workload blocking không giới hạn.

Async API:

Với cùng request và một S3AsyncClient đã được tái sử dụng:

```java
Mono<HeadObjectResponse> result =
        Mono.fromFuture(s3AsyncClient.headObject(request));
```

S3AsyncClient trả CompletableFuture; có thể chuyển sang Reactor bằng Mono.fromFuture. Trả Mono cho caller thay vì gọi join() hoặc get() trong WebFlux event-loop.

### 7.3. Azure SDK: client sync và async là hai kiểu riêng

Azure SDK thường cung cấp client sync và async riêng:

- BlobClient là synchronous.
- BlobAsyncClient trả reactive types.
- ServiceBusClient và ServiceBusAsyncClient có model tương ứng.
- SecretClient và SecretAsyncClient có model tương ứng.

Ví dụ async Blob:

```java
import com.azure.storage.blob.BlobAsyncClient;
import com.azure.storage.blob.BlobClientBuilder;
import com.azure.storage.blob.models.BlobProperties;
import reactor.core.publisher.Mono;

BlobAsyncClient blobAsyncClient =
        new BlobClientBuilder()
                .endpoint(blobEndpoint)
                .credential(credential)
                .buildAsyncClient();

Mono<BlobProperties> properties =
        blobAsyncClient.getProperties();
```

Mono là cold publisher: request chỉ được thực thi khi có subscription. Trong controller WebFlux, return publisher để framework subscribe; không gọi subscribe() thủ công rồi trả response rỗng.

Nếu dùng client sync trong WebFlux, bọc call trong Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic()) và quản lý concurrency. Không gọi block() trên event-loop.

### 7.4. Google Cloud Java clients không có một mô hình async chung

Google Cloud Java libraries có API theo từng dịch vụ:

- Nhiều service client cung cấp method đồng bộ.
- Một số API long-running trả OperationFuture hoặc OperationCallable.
- Pub/Sub Publisher trả ApiFuture khi publish.
- Một số dịch vụ có async stub hoặc callback riêng qua gRPC.
- Cloud Storage Storage interface có nhiều method synchronous.

Không suy luận rằng mọi class có tên Client đều non-blocking. Đọc API của đúng service và method đang gọi.

Ví dụ Cloud Storage synchronous trong WebFlux:

```java
Mono<Blob> blobMono =
        Mono.fromCallable(() -> storage.get(bucketName, objectName))
                .subscribeOn(Schedulers.boundedElastic());
```

Nếu service có API future/callback, chuyển future sang reactive type bằng adapter phù hợp. Tránh gọi future.get() hoặc chờ callback bằng latch trên event-loop.

### 7.5. Không gọi subscribe() để bỏ quên kết quả

Mẫu dễ gây lỗi:

```java
@GetMapping("/orders/{id}")
Mono<Order> getOrder(@PathVariable String id) {
    paymentClient.lookup(id)
            .subscribe(result -> log.info("Lookup completed"));
    return Mono.just(new Order(id));
}
```

Request trả về trước khi lookup hoàn tất; exception, cancellation và context của lookup không còn gắn với response pipeline.

Nên compose publisher:

```java
@GetMapping("/orders/{id}")
Mono<Order> getOrder(@PathVariable String id) {
    return paymentClient.lookup(id)
            .map(result -> new Order(id, result.status()));
}
```

Chỉ dùng fire-and-forget khi đó là yêu cầu nghiệp vụ rõ ràng và đã có queue/retry/observability riêng, không dùng subscribe() để né việc thiết kế luồng async.

## 8. Dấu hiệu event-loop starvation và pool exhaustion

### 8.1. Event-loop bị block

Dấu hiệu:

- Nhiều request chậm cùng lúc dù CPU không cao.
- Thread reactor-http-nio-* nằm trong socket read, JDBC call, Future.get(), Thread.sleep() hoặc block().
- Reactor cảnh báo blocking call trên non-blocking thread.
- Timeout tăng đồng loạt ở nhiều endpoint.
- Request không liên quan tới cloud SDK cũng bị chậm.

Kiểm tra thread dump và xác định stack frame đầu tiên thuộc code ứng dụng hoặc SDK sync. Di chuyển blocking call sang bounded elastic hoặc chuyển sang async client.

### 8.2. Connection pool cạn

Một pool có thể hết connection do:

- Max connection thấp hơn concurrency thực tế.
- Request giữ connection trong lúc chờ downstream.
- Response body/stream không được consume hoặc close.
- Timeout acquire quá ngắn so với hàng đợi hợp lệ.
- Retry làm tăng số request đồng thời.
- Tạo quá nhiều service client, mỗi client có pool riêng.
- Không tái sử dụng client.

Phân biệt pending acquire với downstream timeout. Tăng pool size mà không kiểm soát concurrency có thể làm service provider bị quá tải hơn.

### 8.3. Backpressure và concurrency

Reactive không đồng nghĩa vô hạn throughput. Khi gọi cloud service, đặt giới hạn concurrency dựa trên:

- Quota/rate limit của provider.
- Max concurrency của SDK HTTP client.
- Số connection khả dụng.
- Dung lượng thread pool/executor.
- Kích thước payload và thời gian response.
- Số replica cùng gọi một resource.

Dùng flatMap có concurrency cap khi fan-out tới nhiều object/message. Tránh flatMap không giới hạn với hàng nghìn request cùng lúc.

## 9. Cấu hình HTTP client và lifecycle

### 9.1. Tái sử dụng client

Service clients thường thread-safe và được thiết kế để tái sử dụng. Tạo một client cho mỗi request gây:

- Tạo nhiều connection pool và event loop.
- DNS/TLS handshake lặp lại.
- Tăng thread, socket và file descriptor.
- Tăng thời gian startup/latency.
- Khó đóng tài nguyên khi ứng dụng shutdown.

Tạo client bằng Spring bean singleton hoặc factory có lifecycle rõ ràng. Đóng client/transport theo hướng dẫn của SDK khi ApplicationContext dừng.

### 9.2. Timeout cần được cấu hình theo từng lớp

| Timeout | Giới hạn |
| --- | --- |
| Connection timeout | Thời gian mở TCP/TLS connection |
| TLS handshake timeout | Thời gian hoàn tất handshake |
| Read/response timeout | Thời gian chờ response hoặc dữ liệu |
| API call timeout | Tổng thời gian cho một SDK call, có thể gồm retry |
| Pool acquire timeout | Thời gian chờ lấy connection từ pool |
| Reactor timeout | Deadline của publisher trong pipeline |
| Business deadline | Thời gian tối đa nghiệp vụ chấp nhận |

Đặt Reactor timeout ngắn hơn SDK API timeout có thể làm caller hủy subscription nhưng SDK request vẫn đang chạy nếu cancellation không truyền hết tới transport. Kiểm tra cancellation semantics của client cụ thể.

### 9.3. Đóng stream và response body

Các API stream có thể giữ socket/connection mở cho tới khi body được consume hoặc close. Ví dụ AWS ResponseInputStream, Azure download stream và Google ReadChannel cần được xử lý theo contract của SDK.

Dùng try-with-resources cho stream synchronous. Với reactive stream, propagate cancellation và không bỏ subscriber giữa chừng mà không giải phóng resource.

### 9.4. Không chia sẻ một HTTP client sai loại

Một HTTP client async không nhất thiết có thể dùng cho service client synchronous. Tương tự, Reactor Netty HttpClient, AWS SdkHttpClient, Azure HttpClient và gRPC ManagedChannel là các abstraction khác nhau dù một số cùng dùng Netty bên dưới.

Chia sẻ connection pool chỉ khi SDK hỗ trợ rõ ràng và transport type tương thích. Không truyền Reactor Netty client trực tiếp vào AWS SDK chỉ vì cả hai cùng dựa trên Netty.

## 10. Xử lý theo từng cloud provider

### 10.1. AWS SDK for Java 2.x

Kiểm tra:

- Các service module AWS SDK v2 cùng version theo AWS SDK BOM.
- Không trộn dependency software.amazon.awssdk:* phiên bản khác nhau.
- S3Client dùng sync HTTP client; S3AsyncClient cần async HTTP client.
- Nếu exclude Apache/Netty để giảm dependency, thêm HTTP implementation thay thế cho đúng client type.
- AWS CRT có native dependency và yêu cầu runtime/OS phù hợp.
- Dùng một client dùng chung cho mỗi cấu hình region/endpoint/credential phù hợp; đóng client khi shutdown.
- Không chặn join() trên Netty/Reactor event loop.

Ví dụ Maven import AWS SDK v2 BOM cho client SDK trực tiếp:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>AWS_SDK_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Nếu dùng Spring Cloud AWS, ưu tiên BOM của Spring Cloud AWS và chỉ override AWS SDK BOM khi có lý do tương thích rõ ràng. Kiểm tra AWS SDK v1 cũ có bị kéo vào bởi một integration legacy hay không.

### 10.2. Azure SDK for Java

Kiểm tra:

- Spring Cloud Azure BOM khớp Spring Boot/Spring Cloud.
- Azure SDK libraries được quản lý bằng BOM phù hợp.
- azure-core-http-netty có version tương thích; nếu exclude phải thay bằng OkHttp hoặc JDK HttpClient được hỗ trợ.
- Sync client không được gọi trực tiếp trên WebFlux event-loop.
- Async client trả Mono/Flux; return/compose publisher thay vì subscribe thủ công.
- Netty transport dùng chung với Reactor Netty nên cần kiểm tra version skew.
- Service Bus, Event Hubs và các client AMQP có transport riêng; không đánh đồng với HTTP Netty client.
- Đóng HttpClient/client resources nếu ứng dụng tự tạo và SDK yêu cầu quản lý lifecycle.

### 10.3. Google Cloud Java libraries

Kiểm tra:

- Dùng spring-cloud-gcp-dependencies cho Spring Framework on Google Cloud starter.
- Dùng libraries-bom khi trực tiếp khai báo Google Cloud Java clients theo hướng dẫn của thư viện.
- Không pin riêng Guava, protobuf hoặc gRPC mà không kiểm tra toàn bộ dependency graph.
- Dùng gRPC compatibility checker nếu gặp ALPN error.
- Phân biệt API sync, ApiFuture, OperationFuture, callback và async stub theo từng dịch vụ.
- Kiểm tra runtime container có thêm Netty/Guava/protobuf JAR ngoài build artifact không.
- Tái sử dụng Publisher, Storage, SecretManagerServiceClient và client tương ứng theo lifecycle; không tạo lại client mỗi request.

## 11. Công cụ phát hiện lỗi linkage sớm

### 11.1. Maven Enforcer dependency convergence

Có thể bật rule để phát hiện nhiều version của cùng artifact trong dependency tree:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>MAVEN_ENFORCER_VERSION</version>
    <executions>
        <execution>
            <id>enforce-dependency-convergence</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <dependencyConvergence/>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Rule này có thể báo xung đột hợp lệ ở test scope hoặc các dependency mà BOM được thiết kế để chọn version. Đọc từng path trước khi thêm exclusion. Không dùng danh sách exclusion rộng để ép build xanh.

### 11.2. Google Linkage Checker

Google Cloud Java troubleshooting guide đề xuất Linkage Checker Enforcer Rule để phát hiện một số linkage error trước runtime. Đây là bước bổ sung hữu ích khi dùng nhiều Google Cloud libraries hoặc gặp NoSuchMethodError/NoClassDefFoundError.

Linkage checker không thay thế integration test trên runtime image. Một app server hoặc container có thể thêm JAR ngoài dependency graph của Maven/Gradle.

### 11.3. Kiểm tra artifact đóng gói

Với Spring Boot executable JAR:

```bash
jar tf target/orders-api.jar
```

Kiểm tra thư viện runtime dưới BOOT-INF/lib. Với Docker image, kiểm tra đúng image digest được deploy và danh sách JAR thực tế trong image. Nếu dùng layered jar/buildpack, so sánh dependency layer và image đã phát hành.

### 11.4. Bật diagnostic có kiểm soát

Khi cần, log:

- Version Spring Boot/Spring Framework/Spring Cloud.
- Version SDK/provider starter.
- Version Netty, Reactor Netty, gRPC, protobuf, Guava.
- Tên HTTP transport thực tế.
- Số connection active/pending và timeout.
- Thread name và stack trace liên quan.

Không log access token, credential, SAS token, signed URL hoặc payload nghiệp vụ. Tắt debug log sau khi khoanh vùng để tránh tăng chi phí và lộ thông tin.

## 12. Ma trận troubleshooting theo lỗi cụ thể

| Lỗi | Nguyên nhân thường gặp | Cách xử lý đầu tiên |
| --- | --- | --- |
| NoSuchMethodError | Runtime chọn version class cũ hơn version lúc compile | Tìm artifact chứa class, dùng dependency tree/insight để tìm đường kéo version |
| NoClassDefFoundError | Thiếu JAR, class init thất bại hoặc runtime classpath khác | Đọc Caused by đầu tiên, kiểm tra runtime JAR và initializer |
| ClassNotFoundException | Thiếu dependency hoặc classloader không thấy JAR | Kiểm tra scope, packaging và classloader |
| AbstractMethodError | Interface/implementation không cùng binary contract | Align version Spring/provider/SDK |
| NoSuchFieldError | Class version không có field mà caller mong đợi | Tìm JAR chứa class và bỏ override lệch |
| ALPN is not configured properly | gRPC/Netty/JDK/platform không tương thích | Chạy gRPC compatibility checker, kiểm tra Netty và runtime JDK |
| UnsatisfiedLinkError | Native library/classifier không khớp | Kiểm tra OS, CPU, libc, native artifact và fallback transport |
| NoClassDefFoundError: io/netty/... | Async HTTP transport thiếu hoặc Netty bị exclude | Thêm đúng Netty transport hoặc chọn client khác |
| NoSuchMethodError: io.netty... | Netty module version skew | Align toàn bộ Netty modules theo BOM tương thích |
| NoSuchMethodError: reactor... | Reactor Core/Reactor Netty không đồng bộ | Bỏ version override, dùng Spring Boot BOM |
| ALPN/gRPC fail chỉ trong container | Runtime image có JAR hoặc JDK khác build | So sánh image runtime, JDK, gRPC và Netty |
| NoSuchBeanDefinitionException cho provider client | Thiếu starter, auto-config bị exclude hoặc condition không match | Kiểm tra starter, property, classpath và condition evaluation report |
| AWS async client thiếu HTTP implementation | Exclude Netty/CRT nhưng vẫn dùng async client | Thêm netty-nio-client/CRT hoặc cấu hình async transport khác |
| Azure client không có HttpClient implementation | Exclude Azure Netty nhưng không thêm transport khác | Thêm azure-core-http-okhttp hoặc JDK HttpClient phù hợp |
| WebFlux cảnh báo blocking call | Gọi sync SDK/JDBC trên event loop | Chuyển sang async API hoặc boundedElastic |
| WebFlux bị treo nhưng không có exception | Event loop starvation hoặc deadlock | Lấy thread dump, tìm block(), Future.get(), JDBC/socket read |
| PoolAcquireTimeoutException | Pool cạn hoặc request giữ connection lâu | Kiểm tra active/pending, response body close, concurrency và timeout |
| RejectedExecutionException | Executor bị shutdown hoặc quá tải | Kiểm tra lifecycle, queue size và thread pool |
| Reactive pipeline không chạy | Publisher cold nhưng không được return/subscribe | Compose và return Mono/Flux; không tạo publisher rồi bỏ |
| Reactive request trả sớm | Gọi subscribe() rồi trả response khác | Kết hợp publisher vào chain nghiệp vụ |
| Request bị gửi hai lần | Subscribe nhiều lần hoặc retry không idempotent | Kiểm tra số subscription và retry policy |
| Bộ nhớ tăng khi tải object | Stream/body không được đóng hoặc buffer quá lớn | Stream dữ liệu, close resource và giới hạn concurrency |
| Latency tăng sau khi tạo client per request | Nhiều pool/event loop và TLS handshake | Tái sử dụng singleton client, giới hạn pool |
| Timeout dù CPU thấp | Blocking thread, pool acquire, DNS hoặc downstream chậm | Đo riêng connect/read/pool/API timeout và thread state |

## 13. Quy trình sửa lỗi có kiểm soát

Thực hiện theo thứ tự để tránh tạo thêm xung đột:

1. **Chụp lỗi gốc:** lưu stack trace đầy đủ, JDK version, image digest, profile và thời điểm phát sinh.
2. **Xác định lớp:** Spring compatibility, classpath, transport, TLS/native hay blocking/reactive.
3. **Lấy dependency tree runtime:** lọc Spring, Netty, Reactor, gRPC, protobuf, Guava và SDK provider.
4. **Tìm nguồn version:** BOM nào quản lý artifact, dependency nào kéo version, rule nào override.
5. **Đối chiếu compatibility matrix:** Boot, Cloud release train, provider starter, SDK và JDK.
6. **Chọn thay đổi nhỏ nhất:** nâng BOM/starter đúng dòng, bỏ dependency version pin, sửa exclusion hoặc chuyển client sync/async.
7. **Kiểm tra code model:** không block event-loop, không subscribe bỏ quên, close stream và tái sử dụng client.
8. **Build lại từ clean state:** tránh dựa vào JAR cũ trong cache hoặc thư mục build.
9. **Chạy integration test trên runtime tương đương production:** đúng JDK, container base image, native architecture, proxy và transport.
10. **Theo dõi sau rollout:** thread pool, event loop, connection pool, timeout, error rate và số request thực tế.

Nếu lỗi bắt đầu sau khi thêm một provider starter, so sánh dependency tree trước và sau thay đổi. Starter mới có thể kéo một phiên bản Netty, Reactor, gRPC hoặc Spring module khác vào classpath dù code nghiệp vụ không đổi.

## 14. Bài thực hành: một Orders API gọi cả ba cloud

Mục tiêu: Orders API chạy Spring Boot và cung cấp WebFlux endpoint. Service cần:

- Đọc object từ Amazon S3.
- Lấy metadata blob từ Azure Blob Storage.
- Truy vấn object metadata từ Google Cloud Storage.

Một phiên bản code dùng cả ba synchronous clients trong reactive controller. Sau khi tải tăng, event-loop bị block; đồng thời Azure Netty và AWS async Netty kéo hai nhóm version khác nhau.

### Bước 1 — Ghi nhận nền tảng

Ghi lại Spring Boot, Spring Cloud train, JDK và version provider BOM. Xác nhận các phiên bản nằm trong compatibility matrix của từng provider. Không nâng dependency trước khi lưu lại trạng thái ban đầu.

### Bước 2 — Phân tích dependency tree

Chạy Maven:

```bash
mvn dependency:tree -Dverbose "-Dincludes=io.netty:*,io.projectreactor.netty:*,io.projectreactor:*,io.grpc:*,com.google.protobuf:*,com.google.guava:*,software.amazon.awssdk:*,com.azure:*"
```

Hoặc Gradle:

```bash
./gradlew dependencyInsight --dependency netty-common --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-netty-http --configuration runtimeClasspath
./gradlew dependencyInsight --dependency grpc-netty-shaded --configuration runtimeClasspath
```

Ghi lại version được chọn và đường dependency đã đưa artifact vào.

### Bước 3 — Chọn I/O model cho từng SDK

- AWS: dùng S3AsyncClient nếu muốn giữ pipeline reactive; chuyển CompletableFuture thành Mono.
- Azure: dùng BlobAsyncClient, trả Mono/Flux trực tiếp.
- Google Cloud Storage: nếu dùng Storage synchronous, bọc operation trong boundedElastic; nếu service có async API riêng thì dùng API đó.

Không gọi block() trên event-loop và không gọi subscribe() bên trong controller.

### Bước 4 — Chuẩn hóa dependency

Dùng Spring Boot/Cloud BOM phù hợp và BOM của provider. Không pin riêng Netty module để chữa một lỗi NoSuchMethodError. Nếu gRPC/Netty conflict, xác định shaded transport hay unshaded transport trước khi sửa.

### Bước 5 — Kiểm tra lifecycle

Đảm bảo mỗi SDK client được tạo một lần, pool có giới hạn, response stream được close và client được đóng khi ứng dụng shutdown.

### Bước 6 — Kiểm thử

Chạy các kiểm tra:

- Context startup và auto-configuration.
- Một request tới mỗi provider.
- Nhiều request đồng thời có giới hạn.
- Timeout/cancellation khi downstream chậm.
- Kiểm tra không có blocking call trên event-loop.
- Kiểm tra pool active/pending và thread count.
- Chạy trong đúng Docker image/architecture production.

Bài thực hành hoàn thành khi dependency graph nhất quán theo BOM, cả ba provider trả kết quả đúng, không có linkage error, event-loop không bị block và pool không tăng vô hạn dưới tải.

## 15. Nguyên tắc vận hành

- Chọn Spring Boot và Spring Cloud release train trước; sau đó chọn provider starter theo compatibility matrix.
- Dùng BOM của Spring Boot, Spring Cloud và provider để quản lý dependency.
- Dùng Google libraries-bom khi khai báo trực tiếp Google Cloud Java libraries theo hướng dẫn.
- Không trộn Spring Cloud AWS 2.x với 3.x/4.x starter trong cùng cấu hình mà không có kế hoạch migration.
- Không thêm nhiều logging backend hoặc nhiều phiên bản SLF4J.
- Kiểm tra javax/jakarta khi nâng Boot 2 lên Boot 3/4.
- Kiểm tra toàn bộ Netty modules, không chỉ netty-all.
- Phân biệt grpc-netty-shaded với io.netty.
- AWS async client cần async HTTP transport; Azure SDK cần HTTP implementation; Google gRPC client cần runtime ALPN/Netty tương thích.
- Dùng async SDK trong WebFlux khi có thể; nếu dùng blocking SDK, chuyển sang scheduler dành cho blocking work và giới hạn concurrency.
- Không gọi block(), Future.get() hoặc JDBC sync trên event-loop.
- Không gọi subscribe() rồi bỏ publisher trong controller.
- Tái sử dụng client, cấu hình timeout/pool có giới hạn và đóng stream/resource.
- Build và kiểm thử trên runtime image thật, không chỉ trên IDE hoặc máy developer.
- Khi lỗi xuất hiện sau khi thêm starter, so sánh dependency tree trước/sau để xác định transitive dependency gây thay đổi.

## 16. Ghi nhớ

- NoSuchMethodError, NoClassDefFoundError và AbstractMethodError thường chỉ ra binary dependency mismatch.
- Spring Boot, Spring Cloud release train và provider starter phải nằm trong compatibility matrix tương ứng.
- BOM giúp quản lý version đồng bộ; không override Netty/Reactor/gRPC tùy tiện.
- AWS SDK v1 (com.amazonaws) và v2 (software.amazon.awssdk) có API riêng; Spring Cloud AWS 2.x và 3.x/4.x không phải cùng major line.
- Spring Boot 3+ dùng Jakarta namespace cho các API tương ứng; dependency javax.* cũ có thể gây lỗi runtime.
- AWS SDK v2 async mặc định dùng Netty HTTP client; sync và async client có yêu cầu transport khác nhau.
- Azure SDK dùng azure-core-http-netty mặc định và cho phép thay transport nếu thêm implementation phù hợp.
- Google Cloud Java libraries có thể dùng gRPC; kiểm tra ALPN, Netty, Guava và protobuf bằng compatibility checker.
- WebFlux dùng event loop nhỏ; không thực hiện blocking I/O trực tiếp trên event-loop.
- Azure async clients trả Reactor types; AWS async clients trả CompletableFuture; Google Cloud async model phụ thuộc từng service API.
- Reactive publisher phải được compose và return; không subscribe bỏ quên trong controller.
- Client và connection pool cần được tái sử dụng, giới hạn concurrency, timeout và đóng đúng lifecycle.
- Chỉ kết luận lỗi đã sửa sau khi kiểm thử dependency graph và runtime image thực tế.

## Tài liệu tham khảo chính thức

1. [Spring Cloud — Release train and Spring Boot compatibility](https://spring.io/projects/spring-cloud/)
2. [Spring Cloud — Supported Versions](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions)
3. [Spring Boot — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
4. [Spring Boot — Migration Guide 3.0 and Jakarta EE](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
5. [Spring Cloud AWS — Compatibility matrix and supported integrations](https://github.com/awspring/spring-cloud-aws)
6. [AWS SDK for Java 2.x — Configure HTTP clients](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration.html)
7. [AWS SDK for Java 2.x — Configure the Netty async HTTP client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration-netty.html)
8. [AWS SDK for Java 2.x — Asynchronous programming](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/asynchronous.html)
9. [Spring Cloud Azure — Spring version mapping](https://github.com/Azure/azure-sdk-for-java/wiki/Spring-Versions-Mapping)
10. [Spring Cloud Azure — BOM and dependency setup](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/developer-guide-overview)
11. [Azure SDK for Java — HTTP clients and pipelines](https://learn.microsoft.com/en-us/azure/developer/java/sdk/http-client-pipeline)
12. [Azure SDK for Java — Asynchronous programming](https://learn.microsoft.com/en-us/azure/developer/java/sdk/async-programming)
13. [Spring Framework on Google Cloud — Compatibility and dependency setup](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/getting-started.html)
14. [Google Cloud Java — Use the Libraries BOM](https://docs.cloud.google.com/java/docs/bom)
15. [Google Cloud Java — Troubleshooting classpath and ALPN](https://docs.cloud.google.com/java/docs/troubleshooting)
16. [Spring Framework — WebFlux concurrency model and blocking APIs](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
17. [Project Reactor — Wrapping synchronous blocking calls](https://projectreactor.io/docs/core/release/reference/faq.html)
18. [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html)
19. [Gradle — Viewing and debugging dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
20. [Maven Enforcer — Dependency convergence](https://maven.apache.org/components/enforcer/enforcer-rules/dependencyConvergence.html)

Compatibility matrix, minimum dependency versions và transport behavior có thể thay đổi giữa các patch release. Luôn xác minh BOM và release notes mà ứng dụng sử dụng, sau đó kiểm tra runtime classpath đã resolve trước khi thay đổi transitive dependency.
