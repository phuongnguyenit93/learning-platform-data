# Kiến trúc AWS SDK for Java v2 và quản lý dependency bằng BOM

Một ứng dụng Java có thể gọi Amazon S3, DynamoDB, SQS, SNS, Step Functions hoặc STS bằng AWS SDK for Java. Nhưng SDK không phải một JAR đơn lẻ chứa mọi service. **AWS SDK for Java 2.x được chia thành nhiều module**, mỗi module cung cấp client và model cho một AWS service hoặc một chức năng dùng chung. Dự án chỉ cần phụ thuộc vào những thành phần cần thiết, nhưng phải quản lý phiên bản nhất quán để tránh lỗi classpath khi compile hoặc runtime.

**Bill of Materials (BOM)** là cơ chế Maven/Gradle dùng để quản lý phiên bản tập trung. Khi import `software.amazon.awssdk:bom`, các dependency SDK v2 có thể bỏ version riêng; build tool lấy phiên bản đã được BOM quản lý. Điều này giảm tình trạng `s3`, `dynamodb`, `sts` và các thư viện nền của SDK bị kéo về những phiên bản không tương thích.

Bài thuộc chương **AWS SDK cho Java** của mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung gắn với Region/AZ, IAM, VPC, dịch vụ tính toán và lưu trữ, database, messaging, serverless, giám sát và vận hành ứng dụng AWS an toàn, phục hồi được, kiểm soát chi phí. Ví dụ sử dụng **AWS SDK for Java 2.x**, Maven, Gradle và Java 17/21; version SDK trong cấu hình là ví dụ pin cố định để build tái lập, cần được cập nhật theo quy trình dependency management của dự án.

> **Nguyên tắc:** Import BOM một lần ở dependency management, khai báo đúng các SDK modules ứng dụng sử dụng và giữ **một phiên bản SDK v2 thống nhất trong toàn bộ dependency graph**. BOM quản lý phiên bản; nó **không tự thêm service module, không cấu hình IAM/Region, không khóa tất cả thư viện bên thứ ba và không làm ứng dụng tự kết nối AWS**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích kiến trúc modular của AWS SDK for Java 2.x.
2. Phân biệt service client, model/request/response, shared core, authentication, HTTP transport và AWS service endpoint.
3. Nhận biết artifact coordinates: `groupId`, `artifactId`, `version`, Maven scope và Gradle configuration.
4. Hiểu BOM, dependency management, version alignment và transitive dependencies.
5. Import AWS SDK v2 BOM trong Maven `pom.xml` và Gradle Kotlin/Groovy DSL.
6. Giải thích vì sao từng service dependency không cần khai báo version khi đã import BOM.
7. Biết phạm vi BOM: SDK v2 modules trong `software.amazon.awssdk`; không tự quản lý SDK v1, Lambda Java runtime, Spring, logging hoặc JUnit.
8. Dùng Maven Enforcer và Gradle dependency insight để phát hiện version divergence.
9. Chọn đúng HTTP client cho synchronous/asynchronous clients.
10. Quản lý service client thread-safe, connection pools, lifecycle và configuration.
11. Hiểu credentials provider chain, Region provider chain, IAM roles và SigV4 signing.
12. Phân biệt synchronous, asynchronous và high-level clients.
13. Cấu hình timeout/retry có kiểm soát và hiểu thay đổi default retry từ v2.58.0.
14. Tích hợp SDK với Spring Boot, Lambda, ECS/EC2 và môi trường local.
15. Chẩn đoán lỗi compile/runtime do BOM, classpath, transport, credentials và Region.

## 2. SDK v2 nằm ở đâu trong ứng dụng Java?

Ứng dụng gọi service thông qua **service client**. Client đóng gói phần lớn giao tiếp với AWS: tạo request, serialize dữ liệu, ký request, gửi qua HTTP, nhận response, deserialize và áp dụng retry theo cấu hình.

~~~mermaid
flowchart TD
    APP["Java application / Spring service"] --> CLIENT["Service client<br/>S3Client / DynamoDbClient / SqsClient"]
    CLIENT --> MODEL["Generated request/response models"]
    CLIENT --> CORE["SDK core<br/>configuration, protocol, auth, retry"]
    CORE --> SIGN["AWS Signature Version 4 signing"]
    CORE --> HTTP["HTTP transport<br/>Apache5 / Netty / URLConnection / CRT"]
    HTTP --> ENDPOINT["Regional AWS service endpoint"]
    ENDPOINT --> SVC["Amazon S3 / DynamoDB / SQS / STS ..."]
    BOM["Maven/Gradle BOM<br/>aligns SDK module versions"] -. "Build-time dependency management" .-> CLIENT
~~~

BOM chỉ tham gia **ở thời điểm build/resolve dependencies**. Nó không phải một thành phần runtime nằm giữa ứng dụng và AWS.

### 2.1. Các lớp thành phần chính

| Thành phần | Ví dụ | Trách nhiệm |
|---|---|---|
| Service module | `software.amazon.awssdk:s3` | `S3Client`, `S3AsyncClient`, request/response models |
| Service module | `software.amazon.awssdk:dynamodb` | `DynamoDbClient` và API models |
| Shared SDK core | `sdk-core`, `aws-core` | Client runtime, execution pipeline, configuration |
| Auth | `auth`, `sts` | Credentials providers, request signing, STS operations |
| Region/config | `regions`, shared config providers | Region and profile resolution |
| HTTP transport | `apache5-client`, `netty-nio-client` | Kết nối HTTP đồng bộ/bất đồng bộ |
| High-level library | `dynamodb-enhanced`, `s3-transfer-manager` | API cấp cao hơn service API cơ bản |
| BOM | `software.amazon.awssdk:bom` | Version management cho SDK modules |

Service dependency thường kéo shared modules cần thiết theo transitive dependencies. Không cần tự khai báo từng JAR core nếu service module đã quản lý chúng.

### 2.2. Service client xử lý điều gì?

Khi code gọi:

~~~java
HeadObjectResponse response = s3.headObject(
    HeadObjectRequest.builder()
        .bucket(bucket)
        .key(key)
        .build()
);
~~~

Client thực hiện chuỗi công việc:

1. Kiểm tra và chuẩn bị request model.
2. Chuyển request thành giao thức AWS service yêu cầu.
3. Xác định Region/endpoint và credentials.
4. Ký request theo AWS Signature Version 4 (SigV4) khi cần.
5. Gửi request qua HTTP client và xử lý response.
6. Áp retry/timeout theo policy đã cấu hình.
7. Chuyển response/error thành kiểu Java tương ứng.

SDK giảm phần boilerplate nhưng **không thay thế IAM least privilege, input validation, business idempotency hoặc kiểm soát lỗi nghiệp vụ**.

## 3. Modular artifacts: chỉ thêm module ứng dụng cần

AWS SDK v2 phân phối từng service dưới artifact riêng:

| Nhu cầu | Artifact | Class thường dùng |
|---|---|---|
| Object storage | `software.amazon.awssdk:s3` | `S3Client`, `S3AsyncClient` |
| NoSQL database | `software.amazon.awssdk:dynamodb` | `DynamoDbClient` |
| Queue | `software.amazon.awssdk:sqs` | `SqsClient` |
| Notification | `software.amazon.awssdk:sns` | `SnsClient` |
| Identity/token service | `software.amazon.awssdk:sts` | `StsClient` |
| Step Functions | `software.amazon.awssdk:sfn` | `SfnClient` |
| Key management | `software.amazon.awssdk:kms` | `KmsClient` |
| Secrets Manager | `software.amazon.awssdk:secretsmanager` | `SecretsManagerClient` |
| SSO login/profile | `software.amazon.awssdk:sso`, `ssooidc` | SSO credential providers |
| DynamoDB Enhanced Client | `software.amazon.awssdk:dynamodb-enhanced` | `DynamoDbEnhancedClient` |
| S3 high-level transfers | `software.amazon.awssdk:s3-transfer-manager` | `S3TransferManager` |

**Không nên thêm toàn bộ SDK chỉ vì tiện.** Artifact tổng hợp `aws-sdk-java` có thể kéo nhiều service modules không cần thiết, làm tăng dependency graph, artifact size, classpath scanning và thời gian build/startup. Chọn các modules thực sự được sử dụng.

### 3.1. Artifact coordinates

Một Maven coordinate cơ bản:

~~~text
groupId    = software.amazon.awssdk
artifactId = dynamodb
version    = 2.59.1
~~~

- `groupId` định danh tổ chức/namespace phát hành.
- `artifactId` định danh module.
- `version` định danh release.
- Maven `scope`/Gradle configuration quyết định module tham gia compile, runtime, test hay packaging.

Trong SDK v2, service modules có namespace `software.amazon.awssdk`. SDK v1 dùng namespace `com.amazonaws` và artifact names kiểu `aws-java-sdk-s3`. **Đừng nhầm hai hệ coordinates** khi khai báo BOM hoặc đọc dependency tree.

### 3.2. Low-level service client và high-level library

`DynamoDbClient` cung cấp API gần với DynamoDB service operations. `DynamoDbEnhancedClient` là thư viện bổ sung giúp map Java objects, schema và table operations; nó **không thay** low-level client và được khai báo qua module `dynamodb-enhanced` riêng.

Tương tự, `S3TransferManager` cung cấp API transfer cấp cao, dùng các transport/client phù hợp. Khi dùng high-level library, kiểm tra module và HTTP client dependencies mà tài liệu của library yêu cầu.

## 4. BOM là gì?

**Bill of Materials** là một POM/Gradle platform chứa danh sách dependency versions tương thích. AWS SDK v2 phát hành BOM có coordinates:

~~~text
software.amazon.awssdk:bom:<sdk-version>
~~~

BOM giúp build tool biết rằng các SDK v2 artifacts như `s3`, `dynamodb`, `sdk-core`, `aws-core` và các modules liên quan nên được resolve theo cùng một release/version.

Nếu không có BOM, ứng dụng có thể khai báo:

~~~xml
<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>s3</artifactId>
        <version>2.59.1</version>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>dynamodb</artifactId>
        <version>2.51.0</version>
    </dependency>
</dependencies>
~~~

Hai modules có thể kéo shared dependency khác phiên bản. Kết quả có thể compile nhưng runtime ném `NoSuchMethodError`, `NoClassDefFoundError`, `ClassNotFoundException` hoặc lỗi linkage khó hiểu.

### 4.1. BOM giải quyết điều gì?

| Không dùng BOM | Dùng BOM |
|---|---|
| Khai báo version cho từng module | Khai báo một SDK version tập trung |
| Dễ lệch version giữa service modules | Build tool quản lý version theo BOM |
| Upgrade nhiều dependency statements | Nâng BOM version một nơi |
| Shared modules có thể bị kéo lệch | Giảm rủi ro version mismatch |
| Khó review version policy | Dependency policy rõ hơn |

### 4.2. BOM không làm gì?

BOM:

- **Không tự thêm** S3/DynamoDB/SQS vào classpath; phải khai báo dependency module.
- Không tự tạo IAM role, credentials, Region hay VPC endpoint.
- Không ép tất cả dependencies ngoài `software.amazon.awssdk` về cùng version.
- Không thay thế Maven/Gradle dependency lock hoặc kiểm tra convergence.
- Không bảo đảm mọi transitive dependency bên thứ ba tương thích với Java runtime.
- Không phải runtime client và không tạo network connection.

Một BOM là **version catalog**, không phải danh sách các modules ứng dụng thực sự cần.


## 5. Maven: import BOM trong `pom.xml`

Đặt BOM trong `dependencyManagement`, dùng `type=pom` và `scope=import`:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>2.59.1</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **phần quản lý phiên bản**, chưa thêm S3/DynamoDB service dependencies vào project.

### 5.1. Khai báo modules, bỏ version riêng

~~~xml
<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>s3</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>dynamodb</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sts</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>apache5-client</artifactId>
    </dependency>
</dependencies>
~~~

Maven tra version từ BOM cho các artifacts được BOM quản lý. **Không khai báo version khác** ở từng service module nếu không có lý do tương thích đã được review.

`apache5-client` ở ví dụ được khai báo ở compile scope để code có thể **cấu hình `Apache5HttpClient` trực tiếp**. Khi chỉ khai báo service module, SDK đã kéo Apache5 và Netty HTTP artifacts ở runtime; nếu không cần cấu hình transport, không bắt buộc khai báo `apache5-client` riêng ở compile scope. Nếu chọn transport khác, thay module tương ứng và cấu hình client phù hợp; không cần khai báo mọi HTTP clients cùng lúc.

### 5.2. Một POM hoàn chỉnh tối giản

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>aws-order-service</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <aws.sdk.version>2.59.1</aws.sdk.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>software.amazon.awssdk</groupId>
                <artifactId>bom</artifactId>
                <version>${aws.sdk.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>s3</artifactId>
        </dependency>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>dynamodb</artifactId>
        </dependency>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>sts</artifactId>
        </dependency>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>apache5-client</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Phiên bản `2.59.1` là **ví dụ version pin** để minh họa BOM, không phải yêu cầu mọi dự án phải dùng đúng bản này. Trong dự án thật, chọn bản SDK được team chấp thuận, có security review và tương thích Java/runtime; nâng version bằng một pull request có kiểm thử.

### 5.3. Phạm vi BOM và dependencies khác groupId

BOM `software.amazon.awssdk:bom` quản lý SDK v2 artifacts trong namespace của SDK. Ví dụ `aws-lambda-java-core` có coordinates `com.amazonaws:aws-lambda-java-core`, do đó **không được quản lý bởi SDK v2 BOM** và phải khai báo version/managed BOM phù hợp riêng.

Tương tự, BOM SDK v2 không tự quản lý:

- AWS SDK v1 modules `com.amazonaws:aws-java-sdk-*`.
- Spring Boot, Spring Cloud AWS, Micrometer, Logback/Log4j.
- JUnit, Mockito, Testcontainers, LocalStack test dependencies.
- AWS Lambda Java runtime/API libraries ở group khác.
- AWS CRT platform artifacts nếu chúng có version scheme độc lập.

Không giả định “đã import AWS BOM là toàn bộ AWS dependencies đều không cần version”. Kiểm tra đúng groupId/artifactId.

## 6. Gradle: BOM với Kotlin DSL và Groovy DSL

Gradle dùng `platform(...)` để import Maven BOM như một **platform**.

### 6.1. Kotlin DSL — `build.gradle.kts`

~~~kotlin
plugins {
    java
    application
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(platform("software.amazon.awssdk:bom:2.59.1"))

    implementation("software.amazon.awssdk:s3")
    implementation("software.amazon.awssdk:dynamodb")
    implementation("software.amazon.awssdk:sts")
    implementation("software.amazon.awssdk:apache5-client")

    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

### 6.2. Groovy DSL — `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('software.amazon.awssdk:bom:2.59.1')

    implementation 'software.amazon.awssdk:s3'
    implementation 'software.amazon.awssdk:dynamodb'
    implementation 'software.amazon.awssdk:sts'
    implementation 'software.amazon.awssdk:apache5-client'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
}
~~~

`implementation(platform(...))` cho phép Gradle đưa BOM constraints vào dependency resolution. Nếu một thư viện khác yêu cầu SDK module version cao hơn, Gradle có thể chọn version cao hơn BOM. Vì vậy **platform không tự bảo đảm mọi modules cuối cùng cùng một version** trong mọi dependency graph.

### 6.3. Khi nào dùng `enforcedPlatform`?

~~~kotlin
dependencies {
    implementation(enforcedPlatform("software.amazon.awssdk:bom:2.59.1"))
    implementation("software.amazon.awssdk:s3")
    implementation("software.amazon.awssdk:dynamodb")
}
~~~

`enforcedPlatform` biến BOM constraints thành **forced versions**, có thể override hoặc downgrade một version cao hơn mà thư viện khác yêu cầu. Điều này giúp ứng dụng cuối giữ version đã chọn, nhưng có thể tạo runtime linkage errors nếu một dependency thật sự cần API mới hơn.

- **Ứng dụng deploy cuối:** có thể chọn `enforcedPlatform` nếu đã kiểm soát dependency graph và test tương thích.
- **Thư viện publish cho bên khác:** tránh ép version xuống consumer; dùng `platform`/constraints để không áp đặt version của thư viện lên ứng dụng sử dụng nó.
- Dù dùng cách nào, vẫn phải inspect dependency graph và test runtime.

## 7. BOM trong multi-module và Spring Boot

### 7.1. Maven parent POM

Một project multi-module có thể import AWS BOM tại **parent POM** trong `dependencyManagement`. Các child modules khai báo service artifacts mà không cần version riêng.

~~~text
aws-platform-parent
├── order-api       → dynamodb, sqs
├── file-service    → s3
├── identity-api    → sts
└── notification    → sns
~~~

Không cần mọi child module đều phụ thuộc tất cả service clients. BOM quản lý versions tập trung; mỗi module vẫn khai báo dependency thực tế của nó.

### 7.2. Gradle root project

Trong multi-project Gradle, đặt platform trong convention plugin hoặc root dependency constraints để các subprojects dùng một version. Tránh copy BOM versions khác nhau vào nhiều subprojects; chúng có thể resolve khác nhau nếu cấu hình lệch.

### 7.3. Kết hợp với Spring Boot BOM

Spring Boot BOM và AWS SDK BOM là **hai platform độc lập**:

- Spring Boot BOM quản lý Spring Boot ecosystem.
- AWS SDK BOM quản lý `software.amazon.awssdk` modules.
- Spring Cloud AWS có BOM/starter versions riêng, không tự đồng nhất chỉ vì đã import AWS SDK BOM.

Nếu nhiều BOM quản lý cùng một artifact, kiểm tra precedence trong effective POM/Gradle resolution. Đừng nâng Spring Boot chỉ để nâng SDK hoặc tự override version transitive mà chưa xác minh compatibility.

## 8. BOM không phải version lock hay convergence enforcement

Một BOM là một nguồn version management, nhưng dependency khác có thể yêu cầu version riêng, POM có thể khai báo explicit override hoặc Gradle conflict resolution chọn version cao hơn. **Build có thể vẫn thành công dù SDK modules bị lệch version.**

~~~text
Application
├── software.amazon.awssdk:s3:2.59.1
│   └── software.amazon.awssdk:aws-core:2.59.1
└── library-x
    └── software.amazon.awssdk:dynamodb:2.51.0
        └── software.amazon.awssdk:aws-core:2.51.0
~~~

Đây là dependency graph **không hội tụ**, không phải graph mà BOM mong muốn. Tùy build tool/version selection, classpath có thể đưa shared modules về một phiên bản khác; không được dựa vào compile success để kết luận an toàn.

### 8.1. Maven Enforcer — fail build khi versions phân kỳ

AWS hướng dẫn dùng Maven Enforcer Plugin với `dependencyConvergence` và scope `software.amazon.awssdk`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-enforcer-plugin</artifactId>
            <version>3.6.3</version>
            <executions>
                <execution>
                    <id>enforce-aws-sdk-version-convergence</id>
                    <goals>
                        <goal>enforce</goal>
                    </goals>
                    <configuration>
                        <rules>
                            <dependencyConvergence>
                                <includes>
                                    <include>software.amazon.awssdk</include>
                                </includes>
                            </dependencyConvergence>
                        </rules>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Nếu transitive graph chứa nhiều versions của SDK modules, build fail trong phase `validate` và liệt kê artifacts có divergence. Điều này giúp phát hiện sớm thay vì chờ lỗi ở production.

### 8.2. Gradle dependency insight

~~~bash
# Liệt kê dependency graph.
./gradlew dependencies --configuration runtimeClasspath

# Xem lý do module DynamoDB chọn version hiện tại.
./gradlew dependencyInsight \
  --dependency software.amazon.awssdk:dynamodb \
  --configuration runtimeClasspath

# Trên Windows dùng gradlew.bat thay cho ./gradlew.
~~~

`dependencyInsight` giải thích version nào được yêu cầu, version nào được chọn và tại sao (constraint, conflict resolution, enforced platform).

### 8.3. Maven dependency tree và effective POM

~~~bash
# Chỉ xem các AWS SDK v2 dependencies.
mvn dependency:tree -Dincludes=software.amazon.awssdk

# Hiển thị POM sau khi hợp nhất parent/dependencyManagement.
mvn help:effective-pom

# Validate để chạy Maven Enforcer nếu đã cấu hình.
mvn validate
~~~

Đọc `dependency:tree` để tìm module nào kéo version lệch; đọc effective POM để biết BOM import có thực sự áp dụng hay bị override.

## 9. Chọn HTTP client và dependency phù hợp

Service client cần HTTP transport để gửi request tới AWS endpoint. SDK v2 tách HTTP implementation khỏi service APIs, giúp lựa chọn theo sync/async, latency, startup, TLS, proxy và concurrency.

| HTTP artifact | Kiểu client | Khi phù hợp |
|---|---|---|
| `apache5-client` | Synchronous | HTTP connection pooling, cấu hình chi tiết, client truyền thống |
| `url-connection-client` | Synchronous | Nhẹ, giảm startup/dependency trong use cases đơn giản |
| `netty-nio-client` | Asynchronous | Non-blocking network I/O, async service clients |
| `aws-crt-client` | Sync/async theo hỗ trợ của client | Native AWS Common Runtime, workload/network cần tối ưu chuyên biệt |

**Từ AWS SDK for Java 2.x version 2.46.0**, `Apache5HttpClient` là HTTP client synchronous mặc định, thay cho `ApacheHttpClient` dựa trên Apache HttpClient 4.x. Artifact để cấu hình trực tiếp là `apache5-client`; nhiều bài hướng dẫn cũ còn ghi `apache-client`. Khi copy dependency từ blog cũ, kiểm tra đúng phiên bản và artifact docs.

Service modules mặc định đưa **Apache5 synchronous** và **Netty asynchronous** HTTP artifacts vào runtime classpath. Nếu không chỉ định transport, SDK chọn implementation mặc định theo loại client; khi có nhiều HTTP implementations trên classpath, Apache5 có ưu tiên cao cho sync. Muốn ép transport cụ thể, dùng `httpClientBuilder(...)` ở từng service client.

### 9.1. Synchronous HTTP client

`UrlConnectionHttpClient` không tự được thêm vào project trong các cấu hình yêu cầu explicit dependency. Nếu chọn nó, thêm:

~~~xml
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>url-connection-client</artifactId>
</dependency>
~~~

Với service dependencies có transitive HTTP clients không dùng, có thể cần exclusions theo hướng dẫn hiện hành. Ví dụ loại `apache5-client` và `netty-nio-client` khỏi module S3 rồi dùng URLConnection; **không áp dụng mù quáng** nếu còn asynchronous clients.

URLConnection có startup nhẹ nhưng **không hỗ trợ HTTP PATCH** (một số service operations cần PATCH) và không có per-client configurable idle connection timeout. Kiểm tra operation API trước khi chọn transport; với workload cần tính năng/connection controls phong phú hơn, Apache5 phù hợp hơn.

URLConnection chỉ hỗ trợ synchronous service clients; nếu ứng dụng có `S3AsyncClient`/`DynamoDbAsyncClient` thì cần một asynchronous HTTP transport phù hợp, ví dụ Netty hoặc CRT.

### 9.2. HTTP transport và client lifecycle

Mỗi service client có thể giữ connection pool/HTTP resources. Đừng tạo `S3Client` mới cho từng request. Chọn một client lâu dài cho mỗi cấu hình Region/credentials/endpoint; tái sử dụng trong application và đóng khi shutdown.

Nếu tự inject HTTP client đã build, hiểu rõ ai sở hữu lifecycle và ai phải close. Nếu builder tạo HTTP client qua `httpClientBuilder`, SDK thường quản lý lifecycle cùng service client; xem API docs của phiên bản cụ thể.


## 10. Service clients: thread-safe và nên tái sử dụng

AWS SDK v2 service clients là **thread-safe** và immutable sau khi build. Mỗi client có thể giữ connection pool, credentials provider và configuration. Vì vậy:

- Tạo một client dùng chung cho mỗi service/configuration trong application lifecycle.
- Không tạo/close client ở mỗi HTTP request hoặc mỗi lần gọi database.
- Dùng dependency injection (Spring singleton bean) hoặc application-scoped holder.
- Đóng client khi ứng dụng shutdown.
- Nếu cần Region/endpoint/credentials khác, tạo client riêng cho cấu hình đó; không mutate một client đã build.

### 10.1. Client dùng chung

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

public final class AwsClients {
    private static final DynamoDbClient DYNAMODB =
            DynamoDbClient.builder()
                    .region(Region.AP_SOUTHEAST_1)
                    .build();

    private AwsClients() {
    }

    public static DynamoDbClient dynamodb() {
        return DYNAMODB;
    }

    public static void shutdown() {
        DYNAMODB.close();
    }
}
~~~

Đây là ví dụ Java thuần. Ứng dụng Spring nên để container quản lý lifecycle bằng bean; Lambda nên tạo client ở static initialization/ngoài handler để tận dụng reuse qua nhiều invocations trong cùng execution environment.

### 10.2. Vì sao không tạo client cho mỗi request?

Mỗi lần tạo client có thể khởi tạo HTTP connection pool, credential provider, endpoint/config resolution và resources khác. Nếu tạo liên tục, ứng dụng tốn CPU/memory, tăng handshake và dễ cạn sockets/threads. Reuse clients giúp connection pooling và startup hiệu quả hơn.

## 11. Credentials provider chain và IAM

SDK phải lấy credentials để ký AWS API requests. **Default credentials provider chain** tìm nguồn credentials theo thứ tự provider. Nếu builder không chỉ định provider, service client dùng chain mặc định.

Các nguồn phổ biến gồm:

1. Java system properties.
2. Environment variables.
3. Web identity token / IAM role for service account.
4. Shared AWS config/credentials profiles, gồm cấu hình IAM Identity Center/SSO phù hợp.
5. Container credential provider (ECS).
6. EC2 instance profile credentials qua Instance Metadata Service (IMDS).

Thứ tự và chi tiết provider phụ thuộc cấu hình/SDK version; xem tài liệu credential chain thay vì tự hardcode.

### 11.1. Local development với IAM Identity Center

~~~bash
aws configure sso
aws sso login --profile dev
aws sts get-caller-identity --profile dev
~~~

Java có thể dùng `ProfileCredentialsProvider` cho profile rõ ràng:

~~~java
import software.amazon.awssdk.auth.credentials.ProfileCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

S3Client s3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .credentialsProvider(
                ProfileCredentialsProvider.builder()
                        .profileName("dev")
                        .build())
        .build();
~~~

Nếu không chỉ định provider, SDK dùng `DefaultCredentialsProvider` và tự tra các nguồn phù hợp. Explicit profile hữu ích cho local tools/test, nhưng không nên buộc production app phụ thuộc file profile trên host.

### 11.2. Production workload

| Runtime | Nguồn credentials khuyến nghị |
|---|---|
| AWS Lambda | Execution role của function |
| Amazon ECS/Fargate | Task role |
| Amazon EC2 | Instance profile role |
| Amazon EKS | EKS Pod Identity hoặc IAM Roles for Service Accounts (IRSA), tùy cluster setup |
| On-premises | IAM Identity Center/STS assume role hoặc federation có kiểm soát |

**Không hardcode access key/secret key trong source, YAML, Docker image, build logs hoặc application properties.** Dùng temporary credentials, IAM least privilege và provider có khả năng refresh. Tránh tự copy access key từ console vào environment variables production.

### 11.3. STS và assume role

Nếu application cần truy cập account/resource khác, dùng STS AssumeRole và provider hỗ trợ refresh credentials. Không tự viết vòng lặp gọi STS mỗi request. Thiết kế trust policy, external ID khi cần và session duration phù hợp; role ở account đích chỉ cấp actions/resources cần thiết.

## 12. Region provider chain và endpoint

Credentials xác định **ai gọi**, Region xác định **gọi service endpoint ở đâu**. Hai cấu hình này độc lập.

SDK có thể resolve Region qua:

1. Region set trực tiếp trên client builder.
2. JVM system property `aws.region`.
3. Environment variable `AWS_REGION`.
4. Region trong shared AWS config profile.
5. EC2 Instance Metadata Service trong môi trường phù hợp.

### 12.1. Chỉ định Region rõ ràng

~~~java
S3Client s3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build();
~~~

Hoặc dùng Region external config khi cùng artifact chạy nhiều môi trường. Explicit Region giúp review dễ hơn và tránh ứng dụng vô tình gọi sai Region/table/bucket. Region không được suy ra chỉ từ IAM role.

### 12.2. Endpoint override

`endpointOverride(URI.create(...))` hữu ích cho local test service, LocalStack hoặc endpoint đặc thù được AWS hỗ trợ. Khi override endpoint, request vẫn có thể cần Region và signing credentials đúng. **Không hardcode LocalStack endpoint hoặc endpoint private của môi trường dev vào production configuration**.

Với private connectivity, service client thường vẫn dùng regional endpoint; VPC endpoint DNS/routing làm request đi theo đường private. Không tự đổi endpoint sang IP tĩnh nếu tài liệu AWS không yêu cầu.


## 13. Synchronous và asynchronous service clients

### 13.1. Synchronous client

`S3Client`, `DynamoDbClient` và `SqsClient` thực thi API call đồng bộ: thread gọi bị block đến khi nhận response hoặc lỗi. Cách này dễ đọc, phù hợp Spring MVC, batch job và workload có concurrency vừa phải.

~~~java
S3Client s3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build();

HeadBucketResponse response = s3.headBucket(
        HeadBucketRequest.builder()
                .bucket("example-bucket")
                .build());
~~~

Trong ứng dụng server, đừng đóng client sau mỗi call; hãy reuse và close ở shutdown. Ví dụ CLI/lifecycle ngắn có thể dùng try-with-resources.

### 13.2. Asynchronous client

`S3AsyncClient` và `DynamoDbAsyncClient` trả `CompletableFuture`. Async clients hỗ trợ non-blocking network I/O và high concurrency với ít request threads hơn:

~~~java
import java.util.concurrent.CompletableFuture;
import software.amazon.awssdk.services.dynamodb.DynamoDbAsyncClient;
import software.amazon.awssdk.services.dynamodb.model.DescribeTableRequest;
import software.amazon.awssdk.services.dynamodb.model.DescribeTableResponse;

DynamoDbAsyncClient db = DynamoDbAsyncClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build();

CompletableFuture<DescribeTableResponse> future =
        db.describeTable(DescribeTableRequest.builder()
                .tableName("Orders")
                .build());

future.thenAccept(response ->
        System.out.println(response.table().tableStatus()));
~~~

Trong ứng dụng server, xử lý errors bằng `exceptionally`/`handle` hoặc compose futures; không gọi `join()` ngay trên event-loop/request thread nếu mục tiêu là non-blocking. Đóng client ở lifecycle shutdown.

### 13.3. Async không đồng nghĩa mọi thao tác đều non-blocking

Async HTTP I/O không bảo đảm toàn bộ SDK pipeline non-blocking. Một số công đoạn như credential retrieval, SigV4 signing, endpoint discovery hoặc user callbacks có thể thực hiện công việc blocking/CPU. Thiết kế thread pools, callback execution và backpressure; tránh xử lý nặng trực tiếp trên Netty event-loop.

### 13.4. Chọn client theo application architecture

| Kiểu ứng dụng | Lựa chọn thường gặp |
|---|---|
| Spring MVC / traditional servlet | Sync clients |
| Spring WebFlux / reactive integration | Async clients, adapter phù hợp |
| Batch job đơn luồng | Sync clients |
| Fan-out nhiều service calls | Async clients nếu có thể compose futures |
| Lambda handler đơn giản | Sync client thường đủ; reuse client |
| High-throughput S3 transfer | Đánh giá S3 Transfer Manager/CRT |

Không chọn async chỉ vì “mới hơn”. So sánh throughput, tail latency, memory, thread utilization và độ phức tạp code trong workload thực tế.

## 14. Request/response models và error handling

SDK v2 dùng immutable models và **builder pattern**. Ví dụ:

~~~java
GetItemRequest request = GetItemRequest.builder()
        .tableName("Orders")
        .key(key)
        .consistentRead(true)
        .build();

GetItemResponse response = dynamoDb.getItem(request);
~~~

Request sau khi build không nên được coi như mutable bean. Tạo request mới hoặc builder mới cho từng call, tránh chia sẻ mutable builders giữa threads.

### 14.1. Exception hierarchy

| Exception type | Ý nghĩa | Ví dụ xử lý |
|---|---|---|
| `SdkException` | Base exception SDK | Bắt ở boundary nếu cần |
| `AwsServiceException` | AWS service trả error response | Đọc status, error code, request ID |
| `DynamoDbException`, `S3Exception` | Service-specific exceptions | Phân nhánh business/service error |
| `SdkClientException` | Lỗi client/network/credentials/config | Kiểm tra DNS, TLS, credentials, timeout |
| `ConditionalCheckFailedException` | Conditional write không thỏa | Xử lý conflict/business rule |
| `ProvisionedThroughputExceededException` | DynamoDB throttle/capacity | Retry có backoff, xem hot keys/capacity |

### 14.2. Service error khác client error

- Service error có HTTP status/error code và request ID từ AWS. Ví dụ `AccessDeniedException`, `ResourceNotFoundException`, `ThrottlingException`.
- Client error có thể do network timeout, TLS handshake, credentials provider, Region config hoặc serialization trước khi request được gửi.
- Đừng retry tất cả exceptions như nhau. Validation/authorization errors thường cần sửa request/policy; transient throttling/network có thể retry theo policy.
- Log request ID, service, operation, Region và error code; **không log credentials, authorization headers, raw payload PII hoặc secrets**.

## 15. Retry strategy và timeout: thay đổi theo version

SDK v2 có retry mechanism tích hợp. Retry strategy phân loại lỗi transient/throttling, backoff và circuit-breaking behavior. Cấu hình phải được đặt khi build client.

### 15.1. Default retry từ v2.58.0

Từ **AWS SDK for Java 2.x version 2.58.0**, **Standard retry strategy** trở thành default. Theo tài liệu hiện hành:

- Nhiều service clients thực hiện tối đa **3 attempts tổng cộng** (bao gồm lần gọi đầu).
- DynamoDB clients có default tối đa **4 attempts tổng cộng** với Standard/Adaptive strategy.
- Retry throttling có backoff riêng; circuit breaker có thể ngừng retries khi downstream liên tục lỗi.
- Legacy strategy giữ behavior cũ nếu workload cần compatibility, nhưng không nên chọn chỉ vì số lần retry cao hơn mà không đo.

Các defaults có thể thay đổi ở bản SDK tương lai. Xem release notes/retry strategy docs của đúng SDK version mà dự án pin.

### 15.2. Cấu hình timeout và retry mode

~~~java
import java.time.Duration;
import software.amazon.awssdk.core.retry.RetryMode;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

DynamoDbClient db = DynamoDbClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .overrideConfiguration(o -> o
                .apiCallTimeout(Duration.ofSeconds(30))
                .apiCallAttemptTimeout(Duration.ofSeconds(8))
                .retryStrategy(RetryMode.STANDARD))
        .build();
~~~

`apiCallAttemptTimeout` giới hạn một lần attempt; `apiCallTimeout` giới hạn toàn bộ logical API call, gồm attempts/retry delay. Đặt attempt timeout nhỏ hơn tổng timeout để có thời gian cho retry. Đây là ví dụ; chọn budgets theo SLA, service latency và business deadline.

### 15.3. Retry không tự làm mọi operation idempotent

Một retry có thể xảy ra khi service đã nhận request nhưng client mất response. Với một số API write, cùng request lặp có thể tạo duplicate side effects nếu service/application không hỗ trợ idempotency. Dùng:

- Idempotency token của API khi có.
- Stable business request/operation ID.
- Conditional writes/unique constraints.
- Transactional outbox/inbox cho event processing.
- Reconciliation khi kết quả write không rõ.

SDK retry là **cơ chế transport/service call**, không thay thế idempotency của nghiệp vụ.

### 15.4. Tránh retry storm

Không đặt max attempts vô hạn, không retry validation/access denied và không tạo vòng retry riêng ở application chồng lên SDK retry mà không tính tổng attempts. Nếu SDK retry 4 lần và application retry 5 lần, một business request có thể tạo tới 20 network attempts (hoặc hơn nếu nested calls). Quan sát retries/throttles và dùng bounded exponential backoff/jitter ở tầng phù hợp.


## 16. Cấu hình service client và HTTP transport

Service client được cấu hình qua builder. Một cấu hình thường gồm:

- **Region** và credentials provider.
- HTTP client/connection pool, proxy, TLS và socket settings.
- API call timeout, attempt timeout và retry strategy.
- Endpoint override (chỉ khi use case thực sự cần).
- Metrics/interceptors/logging theo observability policy.

### 16.1. Cấu hình synchronous HTTP client

~~~java
import java.time.Duration;
import software.amazon.awssdk.http.apache5.Apache5HttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

S3Client s3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .httpClientBuilder(Apache5HttpClient.builder()
                .maxConnections(100)
                .connectionTimeout(Duration.ofSeconds(5))
                .socketTimeout(Duration.ofSeconds(20)))
        .overrideConfiguration(o -> o
                .apiCallTimeout(Duration.ofSeconds(30))
                .apiCallAttemptTimeout(Duration.ofSeconds(10)))
        .build();
~~~

Đây là cấu hình minh họa, không phải giá trị tối ưu cho mọi ứng dụng. `maxConnections`, connect/socket timeout và API timeouts phải khớp traffic, latency SLO, server request timeouts và retry budgets.

### 16.2. Cấu hình asynchronous Netty HTTP client

~~~java
import java.time.Duration;
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;

S3AsyncClient s3 = S3AsyncClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .httpClientBuilder(NettyNioAsyncHttpClient.builder()
                .maxConcurrency(200)
                .connectionTimeout(Duration.ofSeconds(5))
                .readTimeout(Duration.ofSeconds(30)))
        .build();
~~~

Concurrency quá cao có thể tăng memory, sockets, downstream throttling và connection contention. Đặt backpressure và limits phù hợp; tăng `maxConcurrency` không tự làm AWS service có capacity vô hạn.

### 16.3. Một HTTP client dùng chung hay một client mỗi service?

Một service client có thể sở hữu HTTP client riêng; cũng có thể chia sẻ một HTTP client object giữa nhiều service clients nếu cấu hình và lifecycle tương thích. Nếu chia sẻ, developer chịu trách nhiệm đóng đúng thời điểm và không đóng khi một client khác còn sử dụng. Đơn giản nhất là để service client quản lý transport của nó trừ khi có nhu cầu tối ưu đã đo.

### 16.4. Chọn URLConnection cho ứng dụng cần nhẹ

`UrlConnectionHttpClient` phù hợp use case synchronous đơn giản, nhưng không hỗ trợ async clients. Nếu chọn nó:

- Thêm `url-connection-client` dependency.
- Exclude HTTP implementations khác chỉ khi đã xác định không dùng chúng.
- Nếu có async service client, thêm async HTTP provider riêng.
- Kiểm tra cold start, TLS, connection behavior và throughput thực tế.

Không copy exclusions từ ví dụ cũ một cách máy móc. Artifact `apache-client` là tên cũ; với SDK từ v2.46.0, Apache HTTP client hiện hành là `apache5-client`.

## 17. Spring Boot integration: tạo client singleton beans

Spring application thường khai báo mỗi AWS service client thành **singleton bean**. Spring quản lý injection và đóng client khi ApplicationContext shutdown.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
public class AwsSdkConfiguration {

    @Bean(destroyMethod = "close")
    DynamoDbClient dynamoDbClient() {
        return DynamoDbClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build();
    }

    @Bean(destroyMethod = "close")
    S3Client s3Client() {
        return S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build();
    }
}
~~~

Service dùng constructor injection:

~~~java
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

@Service
public class OrderRepository {
    private final DynamoDbClient dynamoDb;

    public OrderRepository(DynamoDbClient dynamoDb) {
        this.dynamoDb = dynamoDb;
    }

    // Business methods gọi DynamoDB qua client dùng chung.
}
~~~

Trong production, lấy Region từ external configuration/profile theo environment (dev/staging/prod), không duplicate string trong nhiều classes. Với nhiều Regions, tạo named/qualified beans và routing policy rõ ràng.

### 17.1. Spring Boot BOM và AWS SDK BOM

Nếu dự án dùng Spring Boot dependency management:

- Giữ Spring Boot BOM cho Spring modules.
- Import AWS SDK BOM cho `software.amazon.awssdk`.
- Nếu dùng Spring Cloud AWS, import đúng BOM tương thích với Spring Boot version; đây là project dependency riêng.
- Kiểm tra effective POM hoặc Gradle dependencyInsight nếu một artifact được nhiều BOM quản lý.

Đừng nâng riêng `spring-cloud-aws` hoặc AWS SDK mà không kiểm tra compatibility matrix/release notes của phiên bản tích hợp.

## 18. Lambda, ECS và EC2: credentials/lifecycle theo runtime

### 18.1. AWS Lambda

Trong Lambda, execution role cấp quyền cho function. SDK dùng provider chain để lấy temporary role credentials; không đóng client sau mỗi invocation. Tạo service client ở static initialization để reuse trong execution environment:

~~~java
public final class Handler {
    private static final S3Client S3 = S3Client.builder()
            .region(Region.of(System.getenv("AWS_REGION")))
            .build();

    public Response handleRequest(Request request, Context context) {
        // Dùng S3 client đã khởi tạo ở ngoài handler.
        return process(request, S3);
    }
}
~~~

Lambda environment có thể bị recycle bất cứ lúc nào; không dựa vào static memory làm nơi lưu business state lâu dài. Chọn HTTP transport và dependencies để cân bằng cold start, connection reuse và request duration. Với function chỉ gọi sync API, URLConnection có thể giảm một số dependency; đo trước khi thay đổi.

### 18.2. ECS/Fargate

Gán **task role** cho task definition. SDK credential chain đọc container credentials được runtime cung cấp. Không đặt IAM user access keys trong task environment. Với private subnet, network cần đường tới regional service endpoints qua NAT hoặc VPC endpoints tương ứng; SDK không tự tạo network route.

### 18.3. EC2

Gán instance profile role cho EC2 instance. SDK có thể lấy temporary credentials qua IMDS; bảo vệ IMDS và hạn chế IMDSv1 theo security baseline. Không ghi credential response vào logs hoặc truyền role credentials qua environment variables.

### 18.4. EKS

Ưu tiên EKS Pod Identity hoặc IRSA theo cấu hình cluster/namespace/service account. SDK cần module/providers phù hợp với cơ chế identity đã chọn và quyền trust policy đúng. Đừng nhầm IAM role của node với role riêng của application pod.

## 19. SDK v1 và v2: nhận biết và lộ trình migration

AWS SDK for Java **1.x đã end-of-support ngày 31-12-2025**. Existing applications vẫn có thể chạy với những release đã phát hành, nhưng v1 không còn nhận updates/releases. Dự án mới nên dùng v2; hệ thống đang chạy v1 cần kế hoạch nâng cấp có kiểm soát.

| Khía cạnh | SDK v1 | SDK v2 |
|---|---|---|
| Maven groupId | `com.amazonaws` | `software.amazon.awssdk` |
| Service artifact | `aws-java-sdk-s3` | `s3` |
| BOM | `aws-java-sdk-bom` | `bom` |
| Client example | `AmazonS3` | `S3Client` |
| Request construction | Mutable model/with methods phổ biến | Immutable models + builders |
| Async APIs | Khác biệt theo client/API | Async clients trả `CompletableFuture` |
| HTTP client | Ít lựa chọn tích hợp hơn | Pluggable HTTP implementations |
| Dependency modules | Thường service artifacts trong v1 namespace | Modular artifacts + shared core |
| Support lifecycle | End-of-support 2025-12-31 | Đang được duy trì |

### 19.1. Có thể cùng tồn tại trong giai đoạn chuyển đổi

Một ứng dụng có thể tạm dùng v1 và v2 cùng lúc nếu dependencies không xung đột và code được cô lập. Hai SDK có namespace khác nhau và BOM riêng:

- V1 BOM: `com.amazonaws:aws-java-sdk-bom`.
- V2 BOM: `software.amazon.awssdk:bom`.

Tuy nhiên, tránh tạo kiến trúc mới phụ thuộc cả hai lâu dài. Chia migration theo service/module, có thể chuyển từng service client trước, giữ API nội bộ của application ổn định và test behavior trước khi xóa v1.

### 19.2. Các thay đổi code thường gặp

- `AmazonS3` → `S3Client`.
- Request mutable/`withBucketName` → immutable request builder.
- Credentials/Region classes đổi package/API.
- Exception types, paginator/waiter và async APIs thay đổi.
- S3 transfer utilities và DynamoDBMapper/high-level APIs có migration path riêng.

AWS có **OpenRewrite-based migration tool** để chuyển nhiều service client patterns, nhưng không transform mọi high-level API. Ví dụ DynamoDBMapper và một số API chuyên biệt cần manual migration. Luôn chạy dry-run, review diff, bổ sung tests và tìm v1 imports còn sót.

### 19.3. Tìm v1 còn tồn tại

- Search source imports `com.amazonaws.services.`.
- Kiểm tra Maven/Gradle dependency tree cho `com.amazonaws:aws-java-sdk-*`.
- Kiểm tra logs deprecation warning của v1 trong các version đã phát hành warning.
- Với fat JAR/container image, inspect nested libraries; dependency tree của module riêng có thể không thấy shaded/nested artifacts.

## 20. Nâng cấp SDK BOM an toàn

Nâng version BOM là một **dependency upgrade**, cần review release notes và test cả compile lẫn runtime.

Quy trình đề xuất:

1. Chọn version đã được phê duyệt; pin version cụ thể, tránh dynamic version.
2. Nâng BOM version tại một nơi (parent POM/platform plugin).
3. Kiểm tra các modules trong dependency graph có cùng SDK version.
4. Đọc release notes, deprecations, Java runtime compatibility và default behavior changes (đặc biệt retry/HTTP).
5. Chạy compile/test/unit/integration tests và test trên sandbox AWS/LocalStack phù hợp.
6. Kiểm tra startup/cold start, TLS/HTTP pool, P95/P99, retries và throttling.
7. Deploy canary/staged rollout, theo dõi CloudWatch/application telemetry.
8. Có rollback version và lockfile/build artifact để tái lập.

**Không chỉ nâng BOM rồi assume không có behavioral change.** SDK có thể thay đổi default retry strategy, HTTP implementation artifact, service model hoặc API behavior giữa các releases.



## 21. Troubleshooting dependency và runtime

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `NoSuchMethodError` | SDK shared modules lệch version | Dependency tree, BOM, convergence rule |
| `NoClassDefFoundError` | Thiếu service/HTTP module ở runtime | Kiểm tra compile/runtime scope và packaging |
| `ClassNotFoundException` cho HTTP provider | Thiếu `apache5-client`/`netty-nio-client` hoặc dependency bị exclude | Kiểm tra HTTP transport artifact |
| Maven báo version missing cho `s3` | BOM chưa import đúng scope/type hoặc sai groupId | Effective POM, dependencyManagement |
| Gradle chọn SDK version cao hơn BOM | `platform` constraint là recommendation và graph có request cao hơn | dependencyInsight; xem xét enforcedPlatform |
| Runtime downgrade sau enforcedPlatform | Forced version thấp hơn API dependency khác cần | Update BOM, kiểm tra compatibility |
| Client không tìm thấy Region | Không có Region explicit/env/profile/IMDS | Region chain và deployment config |
| `Unable to load credentials` | Chain không tìm thấy provider hoặc SSO token hết hạn | Profile/SSO login/IAM role/metadata |
| `AccessDeniedException` | Role thiếu action/resource hoặc resource policy deny | Caller identity, IAM policy, SCP, endpoint policy |
| TLS/connection timeout | DNS, proxy, SG/NACL, VPC endpoint, HTTP pool | Network path và HTTP configuration |
| Too many retries/throttling | Hot key, request burst, retry budgets chồng nhau | CloudWatch, SDK retry config, backpressure |
| Client connection pool cạn | Tạo quá nhiều clients hoặc pool không phù hợp | Reuse clients, resource lifecycle |
| Async requests không scale | Callback block event loop, thread pool/buffer không phù hợp | Profiling, backpressure, completion executor |
| Cold start tăng sau thêm SDK | Thêm quá nhiều modules/HTTP providers, classpath scanning | Chỉ giữ modules cần, đo startup |
| AWS SDK v1 warning | Artifact v1 còn trong graph/runtime | Search `com.amazonaws:aws-java-sdk-*`, migration plan |
| LocalStack signature error | Region/credentials/signing/endpoint mismatch | Cấu hình test endpoint và credentials phù hợp |

### 21.1. Phân biệt lỗi build và runtime

- **Build-time:** Maven không resolve BOM, artifact not found, version conflict, compiler không nhận API. Xem effective POM, repositories, compiler JDK và dependency tree.
- **Classpath/runtime:** thiếu class, `NoSuchMethodError` hoặc HTTP provider không load được. Xem packaged JAR/container libs, dependency convergence và shading.
- **Authentication:** credentials chain không tìm thấy hoặc IAM deny. Kiểm tra `GetCallerIdentity`, role trust và resource policy.
- **Network:** timeout/TLS/DNS. Kiểm tra endpoint, VPC routes, SG/NACL, proxy và HTTP transport.
- **Service behavior:** throttling, validation, resource not found. Đọc service error code/request ID và CloudWatch.

Đừng khắc phục `NoSuchMethodError` bằng cách thêm ngẫu nhiên một dependency core version mới. Tìm module nào kéo version lệch và sửa **nguyên nhân trong dependency graph**.


## 22. Bài lab: thiết lập project dùng AWS SDK v2 BOM

### 22.1. Lab A — Maven

Tạo project Java mới hoặc dùng project sandbox:

1. Import `software.amazon.awssdk:bom` trong `dependencyManagement`.
2. Thêm `s3` và `dynamodb` không có version riêng.
3. Thêm HTTP transport đúng với client sync/async mà bài lab chọn.
4. Thêm Maven Enforcer `dependencyConvergence` chỉ áp dụng cho group `software.amazon.awssdk`.
5. Chạy:

~~~bash
mvn validate
mvn dependency:tree -Dincludes=software.amazon.awssdk
mvn help:effective-pom
mvn test
~~~

Kết quả cần kiểm tra: SDK v2 modules resolve theo BOM, HTTP provider có mặt trong runtime classpath và không có module bị version override ngoài ý muốn.

### 22.2. Lab B — Gradle

1. Import BOM bằng `platform("software.amazon.awssdk:bom:2.59.1")`.
2. Thêm `s3` và `dynamodb`.
3. Xem graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency software.amazon.awssdk:s3 --configuration runtimeClasspath
./gradlew dependencyInsight --dependency software.amazon.awssdk:dynamodb --configuration runtimeClasspath
~~~

4. Thêm một dependency thử nghiệm yêu cầu SDK version khác trong sandbox, xem Gradle chọn version nào.
5. So sánh `platform` với `enforcedPlatform` và giải thích vì sao enforced platform có thể downgrade dependency transitive.

### 22.3. Lab C — Client và credentials

1. Dùng AWS CLI profile SSO sandbox, xác minh `aws sts get-caller-identity`.
2. Tạo `DynamoDbClient` hoặc `S3Client` dùng Region rõ ràng và default credentials chain.
3. Gọi một read operation trên resource được cấp quyền.
4. Log operation name, request ID, latency và consumed capacity nếu service hỗ trợ; không log item PII/secrets.
5. Chạy lại với role thiếu quyền để nhận diện service authorization error.
6. Đóng client ở application shutdown.

**Không cần tạo bucket/table hoặc ghi dữ liệu thật để hoàn thành phần dependency-management.** Nếu muốn chạy write operations, chỉ dùng sandbox có budget/cleanup được xác nhận.

### 22.4. Lab D — Phân tích version conflict

Giả sử runtime graph có:

~~~text
software.amazon.awssdk:s3:2.59.1
software.amazon.awssdk:dynamodb:2.59.1
software.amazon.awssdk:aws-core:2.51.0
software.amazon.awssdk:sdk-core:2.59.1
~~~

Trả lời:

- Có thể build thành công không? Có thể, tùy resolution.
- Graph có hội tụ không? Không.
- BOM có tự chặn mọi override không? Không.
- Nên xử lý ra sao? Tìm dependency kéo `aws-core:2.51.0`, loại override hoặc nâng dependency phù hợp, enforce convergence và test runtime.

## 23. Checklist review trước khi merge

### Dependency management

- [ ] Có đúng một AWS SDK v2 BOM version cho application?
- [ ] Service dependencies không tự khai version khác BOM?
- [ ] BOM được đặt trong Maven `dependencyManagement` hoặc Gradle `platform` đúng cách?
- [ ] Không nhầm SDK v1 BOM với SDK v2 BOM?
- [ ] Dependencies khác groupId (Lambda runtime, Spring, JUnit, CRT platform) có version management riêng?
- [ ] Có dependency convergence check/dependency insight phù hợp?
- [ ] Không sử dụng dynamic version/SNAPSHOT cho production release nếu chưa có policy?

### Runtime architecture

- [ ] Chỉ khai báo service modules cần dùng?
- [ ] HTTP transport phù hợp sync/async?
- [ ] Client được reuse và close đúng lifecycle?
- [ ] Region/endpoint lấy từ config rõ ràng?
- [ ] Credentials dùng IAM role/SSO/temporary credentials, không hardcode?
- [ ] IAM least privilege và VPC/network policy đúng?
- [ ] Timeout/retry budgets phù hợp SLA và idempotency?
- [ ] Logs không chứa credentials, tokens, secrets hoặc raw PII?
- [ ] Metrics/tracing có request IDs, operation, latency, retries và throttles?
- [ ] Đã kiểm tra migration/support lifecycle của SDK v1 nếu còn dependency?

### Upgrade/release

- [ ] Release notes và breaking/default changes đã review?
- [ ] Compile, unit/integration tests pass?
- [ ] Packaged runtime artifact có HTTP provider cần thiết?
- [ ] Staging/canary latency, error rate, retry rate và cold start được theo dõi?
- [ ] Có version rollback/build artifact để tái lập?

## 24. Câu hỏi tự đánh giá

1. AWS SDK for Java v2 là một JAR khổng lồ hay tập hợp modules?
2. Service client có nhiệm vụ gì trong request pipeline?
3. `groupId` và `artifactId` khác nhau thế nào?
4. BOM là gì và được import ở đâu trong Maven?
5. Vì sao service dependency có thể bỏ version sau khi import BOM?
6. BOM có tự thêm S3/DynamoDB modules vào project không?
7. AWS SDK v2 BOM quản lý `com.amazonaws:aws-lambda-java-core` không?
8. `platform` trong Gradle khác `enforcedPlatform` ra sao?
9. Vì sao enforcedPlatform có thể tạo runtime downgrade?
10. Làm thế nào Maven Enforcer phát hiện version divergence?
11. Lệnh Gradle nào giúp biết vì sao một SDK version được chọn?
12. Vì sao chỉ nên khai báo service modules ứng dụng thực sự dùng?
13. `S3Client` và `S3AsyncClient` khác nhau về execution model?
14. Async client có bảo đảm mọi phần của pipeline đều non-blocking không?
15. Vì sao service clients nên là singleton/long-lived?
16. Credentials provider chain tìm credentials từ những nguồn nào?
17. Region provider chain và credentials chain có cùng nhiệm vụ không?
18. Vì sao production nên dùng task role/instance profile thay access keys?
19. Khi nào cần `apache5-client`, `url-connection-client` hoặc `netty-nio-client`?
20. Vì sao `url-connection-client` không đủ cho async clients?
21. API attempt timeout khác API call timeout thế nào?
22. Retry của SDK có làm mọi write operations idempotent không?
23. Điều gì thay đổi với default retry từ SDK v2.58.0?
24. Vì sao `NoSuchMethodError` thường là dấu hiệu dependency graph lệch?
25. AWS SDK for Java v1 đã end-of-support ngày nào?
26. Migration tool v1-to-v2 có tự chuyển mọi high-level API không?
27. Tại sao không nên đặt LocalStack endpoint trong production config?
28. Những thông tin nào nên log để debug SDK mà không lộ secrets?

### Định hướng đáp án

- **Architecture:** Service module + generated models + shared core/auth/protocol + HTTP transport + regional endpoint.
- **BOM:** Import `software.amazon.awssdk:bom`; bỏ version ở từng SDK module; BOM không tự add modules và không manage mọi groupId.
- **Convergence:** Maven Enforcer/Gradle dependencyInsight kiểm tra graph; `enforcedPlatform` có thể force/downgrade version.
- **Client runtime:** Thread-safe, immutable, reuse; credentials/Region chains độc lập; chọn HTTP sync/async đúng workload.
- **Reliability:** Retry/timeouts có budget; idempotency là business responsibility; quan sát request IDs, latency, errors, retries.
- **Migration:** SDK v1 end-of-support 2025-12-31; v2 có modular architecture, builders, async API và migration cần review/test.


## 25. Tài liệu AWS và build tools chính thức

1. [AWS SDK for Java documentation](https://docs.aws.amazon.com/sdk-for-java/) — Developer Guide, API Reference và Migration Guide.
2. [Set up a Maven project for AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/setup-project-maven.html) — Import BOM, add modules, Maven Enforcer.
3. [Set up a Gradle project for AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/setup-project-gradle.html) — Kotlin/Groovy DSL, platform và enforcedPlatform.
4. [Configuring service clients](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/configuring-service-clients.html) — Client builders, singleton, Region, credentials, retry, timeout, HTTP.
5. [Making service requests](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/work-witih-clients.html) — Service client behavior.
6. [Use singleton service client instances](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/singleton-service-clients.html) — Thread safety, connection pools, reuse.
7. [Credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html) — Default credential sources.
8. [Using credentials providers](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials.html) — SSO, profiles, role providers, temporary credentials.
9. [Setting the AWS Region](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/region-selection.html) — Region provider chain.
10. [Configure service clients in code](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/configuring-service-clients-code.html) — HTTP/configuration builders.
11. [Configure HTTP clients](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration.html) — Sync/async HTTP transports.
12. [URLConnection-based HTTP client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration-url.html) — Lightweight synchronous transport.
13. [Apache 5 HTTP client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration-apache5.html) — Apache5 transport configuration and lifecycle.
14. [Programming asynchronously](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/asynchronous.html) — CompletableFuture and non-blocking I/O.
15. [Retry strategy](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html) — Standard/Legacy/Adaptive and default behavior.
16. [Troubleshooting the AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/troubleshooting.html) — Classpath/version conflicts and runtime issues.
17. [SDK v1-to-v2 migration guide](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/migration.html) — API and architecture differences.
18. [Migration tool](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/migration-tool.html) — OpenRewrite automation and limitations.
19. [AWS SDK for Java v1 end-of-support announcement](https://aws.amazon.com/blogs/developer/announcing-end-of-support-for-aws-sdk-for-java-v1-x-on-december-31-2025/) — Lifecycle through 2025-12-31.
20. [AWS SDK for Java v2 GitHub repository](https://github.com/aws/aws-sdk-java-v2) — Source, releases, BOM and versioning information.
21. [Maven dependency management](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html) — `dependencyManagement` and imported BOM.
22. [Maven Enforcer dependency convergence](https://maven.apache.org/enforcer/enforcer-rules/dependencyConvergence.html) — Detect conflicting transitive versions.
23. [Gradle platforms](https://docs.gradle.org/current/userguide/platforms.html) — Platform constraints and enforced platforms.

> **Ghi nhớ cuối bài:** AWS SDK for Java 2.x là một tập hợp modules có shared core và service clients. **BOM giúp đồng bộ version**, còn Maven Enforcer/Gradle dependency insight giúp phát hiện graph lệch. Ở runtime, tái sử dụng thread-safe clients, chọn HTTP transport phù hợp, dùng IAM temporary credentials, cấu hình Region/timeout/retry rõ ràng và không giả định SDK retry thay thế idempotency. Nâng BOM phải đi cùng dependency review, tests và quan sát runtime.

