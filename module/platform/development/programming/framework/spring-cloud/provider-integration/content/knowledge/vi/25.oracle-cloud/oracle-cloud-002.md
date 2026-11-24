# Chọn phiên bản tương thích trước khi thêm OCI starter

Thêm một OCI starter vào ứng dụng Spring Boot có vẻ chỉ là thêm một dependency Maven hoặc Gradle. Nhưng starter kéo theo Spring Boot APIs, Spring Framework, OCI Java SDK, HTTP client, Jackson và các thư viện nền khác. Nếu chọn sai dòng version, ứng dụng có thể compile nhưng lỗi khi khởi động, auto-configuration không tạo bean, hoặc gặp lỗi runtime như NoSuchMethodError sau khi triển khai.

Vì vậy, trước khi thêm spring-cloud-oci-starter-storage, spring-cloud-oci-starter-vault hay một starter khác, cần xác định **nền tảng Spring hiện tại**, **release line của Spring Cloud OCI**, **version của OCI SDK** và **các project Oracle liên quan**. Bài này trình bày quy trình chọn và xác minh các version đó, dùng tài liệu chính thức có sẵn tại ngày **24-11-2026** làm snapshot tham khảo.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Xác định version Java, Spring Boot và Spring Framework mà ứng dụng đang dùng.
2. Phân biệt Spring Cloud release train với Spring Cloud Oracle và Spring Cloud OCI.
3. Chọn release line OCI starter phù hợp với Spring Boot major version.
4. Đọc release notes để biết version cụ thể đã được xây dựng và kiểm thử trên nền tảng nào.
5. Hiểu vì sao Spring Cloud OCI, Oracle Database starters, TxEventQ binder và Spring AI Oracle có version độc lập.
6. Chọn đúng Maven/Gradle coordinates và cách quản lý version.
7. Tránh dùng nhầm BOM hoặc áp một version chung cho mọi artifact Oracle.
8. Kiểm tra dependency graph, transitive dependencies và version xung đột.
9. Xác minh auto-configuration, compile, startup và integration test.
10. Lập kế hoạch nâng major version và chẩn đoán lỗi tương thích.

## 2. Vì sao phải chọn version trước khi thêm starter?

Một starter không đứng riêng. Ví dụ, khi thêm OCI Object Storage starter, dependency graph có thể chứa:

- Spring Boot starter và auto-configuration.
- Spring Framework APIs.
- Spring Cloud OCI core.
- OCI Java SDK modules.
- HTTP client và TLS implementation.
- Jackson và thư viện serialize.
- Logging, metrics và các thư viện dùng chung.

Một ứng dụng đã có sẵn dependency của các thành phần này. Maven hoặc Gradle sẽ giải quyết version theo dependency management, constraints, conflict resolution và thứ tự khai báo. Nếu starter yêu cầu API của Spring Framework mới hơn nhưng ứng dụng đang chạy bản cũ, compile hoặc runtime có thể thất bại.

Một dependency có thể làm thay đổi cả graph:

~~~mermaid
flowchart TD
    A[Spring Boot application] --> B[Spring Boot dependency management]
    A --> C[Spring Cloud release train BOM nếu dùng]
    A --> D[Spring Cloud OCI starter]
    D --> E[Spring Cloud OCI core]
    E --> F[OCI Java SDK]
    D --> G[Spring Framework APIs]
    D --> H[Jackson / HTTP client / logging]
    C --> I[Spring Cloud Stream / Config / Commons]
    B --> J[Spring Boot + Spring Framework versions]
~~~

Các nguồn quản lý version này có phạm vi khác nhau. Không nên cho rằng một BOM tự động quản lý tất cả dependency Oracle chỉ vì tên dự án có chữ Spring Cloud.

### Hậu quả thường gặp khi chọn sai

| Dấu hiệu | Nguyên nhân có thể |
| --- | --- |
| UnsupportedClassVersionError | Runtime Java thấp hơn bytecode của dependency |
| NoClassDefFoundError | Thiếu class hoặc class bị loại khỏi dependency graph |
| NoSuchMethodError | Runtime nạp version thư viện không có method mà code đã compile cần |
| AbstractMethodError | API/implementation không cùng version tương thích |
| ClassNotFoundException | Thiếu module hoặc package đã đổi |
| BeanCreationException | Auto-configuration hoặc bean phụ thuộc API/config không tương thích |
| Không có bean Storage/VaultTemplate | Sai starter, auto-configuration bị tắt, thiếu property hoặc condition không khớp |
| Lỗi khi gọi OCI API | Có thể do SDK, authentication, IAM, region hoặc service config; không phải mọi lỗi đều là version conflict |
| Build thành công nhưng deploy lỗi | Test không chạy trên cùng runtime/configuration hoặc dependency graph khác môi trường |

Không thể sửa mọi lỗi bằng cách tăng version của starter. Trước tiên cần tìm đúng tầng không tương thích.

## 3. Bốn trục version cần kiểm tra

### 3.1. Java runtime và build tool

Java version phải đáp ứng yêu cầu của Spring Boot và mọi thư viện được kéo vào. Với Spring Boot 4.x, baseline Java tối thiểu là 17. Build tool cũng phải nằm trong dải được Spring Boot hỗ trợ.

Theo tài liệu Spring Boot hiện hành tại thời điểm viết bài:

- Spring Boot 4.2.0 yêu cầu Java 17 trở lên.
- Spring Framework 7.1.0 trở lên là nền tảng tương ứng của Boot 4.2.
- Maven 3.6.3 trở lên được hỗ trợ.
- Gradle 8.x cần ít nhất 8.14; Gradle 9.x cũng được hỗ trợ.

Đây là yêu cầu của Spring Boot 4.2.0. Hãy kiểm tra system requirements của đúng patch Boot mà ứng dụng chọn, vì các dòng version có thể khác nhau.

Kiểm tra môi trường:

~~~bash
java -version
mvn -version
gradle --version
~~~

Trong CI, kiểm tra JDK thực tế của build agent và container runtime. Một build chạy trên JDK mới không chứng minh image production cũng đang dùng JDK tương ứng.

### 3.2. Spring Boot và Spring Framework

Spring Boot quản lý một bộ Spring Framework và nhiều thư viện nền. Không nên nâng riêng spring-core, spring-context hoặc spring-web để chữa một lỗi mà không kiểm tra compatibility của Boot.

Ví dụ, Spring Boot 4.1.x và 4.2.x đều thuộc major 4, nhưng có thể dùng các minor line Spring Framework khác nhau. Một thư viện build với Framework 7.0 không mặc nhiên đã kiểm thử với Framework 7.1.

Cần xác định:

- org.springframework.boot version.
- Spring Framework version thực tế được resolve.
- Java target/release của project.
- Các dependency override hoặc BOM khác có thể ghi đè Spring Framework.

### 3.3. Spring Cloud release train

Spring Cloud release train là bộ version cho các project thuộc Spring Cloud như Spring Cloud Stream, Config, Circuit Breaker, Gateway hoặc Commons.

Nó có bảng tương thích với Spring Boot riêng. Ví dụ theo bảng chính thức hiện hành:

| Spring Cloud release train | Spring Boot tương thích |
| --- | --- |
| 2025.1.2 trở lên | 4.0.x và 4.1.x |
| 2025.1.x trước 2025.1.2 | 4.0.x |
| 2025.0.x | 3.5.x |
| 2024.0.x | 3.4.x |
| 2023.0.2 trở lên | 3.2.x và 3.3.x |
| 2022.0.3 trở lên | 3.0.x và 3.1.x |

Các release train có dấu sao trên trang Spring Cloud đã hết hỗ trợ OSS. Bảng tương thích cho biết một cặp version có quan hệ tương thích; nó không tự chứng minh release train đó còn được hỗ trợ hoặc phù hợp với OCI starter.

Nếu ứng dụng chỉ dùng Spring Boot và Spring Cloud OCI, không cần thêm Spring Cloud release train BOM chỉ vì tên thư viện là Spring Cloud OCI. Chỉ import Spring Cloud BOM khi ứng dụng có project thuộc release train cần quản lý.

### 3.4. Spring Cloud OCI và OCI Java SDK

Spring Cloud OCI có release line riêng. OCI starter lại kéo theo OCI Java SDK và các thư viện khác.

Theo thông tin dự án Oracle tại ngày 24-11-2026:

- Spring Cloud Oracle 1.x theo Spring Boot 3.
- Spring Cloud Oracle 2.x theo Spring Boot 4 và Spring Framework 7.
- Spring Cloud OCI 2.0.4 là bản hiện hành được công bố.
- Release notes 2.0.4 ghi rõ đã nâng Spring Boot lên 4.1.1.
- Các module OCI 2.0.4 sử dụng OCI Java SDK 3.91.1 trong dependency graph được công bố.

Điều này tạo ra một khác biệt quan trọng: **tương thích cùng major không có nghĩa mọi minor/patch đều đã được kiểm thử**. Dòng 2.x hướng tới Boot 4, nhưng release 2.0.4 ghi rõ baseline cập nhật là Boot 4.1.1. Spring Boot 4.2.0 vừa phát hành ngày 20-11-2026 và yêu cầu Spring Framework 7.1.0 trở lên. Không nên suy ra Spring Cloud OCI 2.0.4 đã được xác nhận với Boot 4.2 chỉ từ việc cả hai cùng thuộc major 4.

## 4. Snapshot version tham khảo ngày 24-11-2026

Bảng sau là snapshot để thực hành cách đọc version, không phải một bộ version bắt buộc cho mọi ứng dụng.

| Project/line | Version tham khảo | Nền tảng hoặc phạm vi |
| --- | --- | --- |
| Spring Cloud OCI | 2.0.4 | Spring Boot 4.1.1 theo release notes |
| Spring Cloud Oracle 1.x | 1.x line | Spring Boot 3 |
| Spring Cloud Oracle 2.x | 2.x line | Spring Boot 4, Spring Framework 7 |
| Oracle AI Database Spring Boot Starters | 26.3.0 | Database connectivity, UCP, Wallet, AQ/JMS, OKafka và các tính năng database |
| Spring Cloud Stream Binder for TxEventQ | 0.21.0 | Spring Cloud Stream trên Oracle AI Database TxEventQ |
| Spring AI Oracle | 2.0.1 | Spring AI 2.0.1; release notes ghi Spring Boot 4.1.1 |
| OCI Java SDK trong OCI 2.0.4 dependency graph | 3.91.1 | Transitive dependency của OCI modules |

Các project này có version riêng. Không đặt một biến spring-cloud-oracle.version rồi gán cùng giá trị cho OCI starter, database starter, TxEventQ binder và Spring AI Oracle.

### Chọn version theo nền tảng hiện có

| Nền tảng hiện tại | Hướng xử lý |
| --- | --- |
| Spring Boot 3.x | Chọn Spring Cloud Oracle 1.x/OCI starter 1.x tương thích; xác minh patch cụ thể và tài liệu 1.x |
| Spring Boot 4.0.x | Chọn OCI 2.x, xác minh release notes của patch OCI cụ thể |
| Spring Boot 4.1.x | OCI 2.0.4 là mốc tham khảo có release notes nâng lên Boot 4.1.1; kiểm tra patch Boot/Framework chính xác |
| Spring Boot 4.2.x | Xác minh Oracle đã phát hành OCI version có kiểm thử/ghi nhận Boot 4.2 và Framework 7.1 trước khi chọn |
| Ứng dụng có Spring Cloud Stream | Chọn Spring Cloud release train tương thích Boot, sau đó xác minh riêng TxEventQ binder version |
| Ứng dụng có Spring AI | Kiểm tra Spring AI version và Spring AI Oracle version độc lập |

### Không trộn 1.x và 2.x trong cùng một ứng dụng

Không thêm OCI starter 1.x vào ứng dụng đang dùng Boot 4 hoặc starter 2.x vào ứng dụng Boot 3 rồi kỳ vọng Maven tự giải quyết được. Hai release line có thể khác API nền, Jakarta/Spring Framework baseline, dependency graph và auto-configuration.

Nếu cần nâng từ Boot 3 lên Boot 4, hãy coi đó là một migration riêng: nâng JDK/build tool, Boot/Framework, Spring Cloud train nếu có, sau đó nâng OCI starter và các project Oracle liên quan. Chạy test sau từng bước để tìm đúng thay đổi gây lỗi.

## 5. Phân biệt Spring Cloud BOM với OCI starter version

Đây là một trong những điểm dễ gây lỗi nhất khi thêm dependency.

### Spring Cloud BOM quản lý điều gì?

org.springframework.cloud:spring-cloud-dependencies quản lý version của các artifact thuộc Spring Cloud release train. Ví dụ, nếu ứng dụng dùng Spring Cloud Stream, Config hoặc Circuit Breaker, BOM có thể quản lý version các project đó.

Nó không tự động có nghĩa là quản lý com.oracle.cloud.spring:spring-cloud-oci-starter-storage.

### OCI version quản lý điều gì?

OCI starter thuộc group com.oracle.cloud.spring. Tài liệu OCI 2.0.4 trình bày coordinates của các starter trong release line OCI. Hãy dùng version được công bố cho đúng starter và release.

Tài liệu 1.x cũ từng mô tả Spring Cloud OCI BOM. Không lấy ví dụ BOM cũ rồi giả định artifact/BOM đó vẫn là cách quản lý version cho 2.x. Với release 2.x, nếu tài liệu phiên bản đang dùng không chỉ rõ BOM, dùng version cụ thể trên starter hoặc một version catalog nội bộ do nhóm quản lý.

### Ví dụ Maven: Spring Boot 4.1.1 và OCI 2.0.4

Ví dụ sau minh họa cách khai báo explicit version cho OCI starter. Spring Cloud BOM chỉ cần khi ứng dụng thật sự dùng Spring Cloud projects.

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.1</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
    <spring-cloud.version>2025.1.2</spring-cloud.version>
    <spring-cloud-oci.version>2.0.4</spring-cloud-oci.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>2025.1.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.oracle.cloud.spring</groupId>
        <artifactId>spring-cloud-oci-starter-storage</artifactId>
        <version>2.0.4</version>
    </dependency>
</dependencies>
~~~

Nếu ứng dụng không dùng Spring Cloud projects, có thể bỏ spring-cloud-dependencies. Ví dụ này không yêu cầu import Spring Cloud BOM chỉ để dùng OCI Storage.

Khi dùng nhiều OCI starter cùng release, có thể khai báo version trong property để tránh lệch version giữa các starter. Điều quan trọng là tất cả starter OCI trong một ứng dụng phải theo cùng release line đã được xác minh.

### Ví dụ Gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.1'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'com.oracle.cloud.spring:spring-cloud-oci-starter-storage:2.0.4'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Nếu dùng Spring Cloud Stream hoặc project Spring Cloud khác, thêm dependency management cho release train phù hợp với Boot. Không dùng version của Spring Cloud train làm version của OCI starter.

### Chọn starter, không thêm implementation module trùng lặp

Ví dụ dùng Object Storage:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-storage</artifactId>
    <version>2.0.4</version>
</dependency>
~~~

Starter chứa module implementation và các transitive dependency cần thiết cho tích hợp đó. Không tự thêm spring-cloud-oci-storage cùng version nếu tài liệu không yêu cầu.

## 6. Cách xác định đúng artifact trước khi chọn version

Không tìm dependency chỉ bằng từ khóa oracle hoặc oci. Trước tiên xác định service và programming model:

| Nhu cầu | Artifact family cần xem |
| --- | --- |
| OCI Object Storage | spring-cloud-oci-starter-storage |
| OCI Vault | spring-cloud-oci-starter-vault |
| OCI Queue | spring-cloud-oci-starter-queue |
| OCI Streaming | spring-cloud-oci-starter-streaming |
| OCI Functions | spring-cloud-oci-starter-function |
| OCI Notifications | spring-cloud-oci-starter-notification |
| OCI Logging | spring-cloud-oci-starter-logging |
| OCI Autonomous Database lifecycle | spring-cloud-oci-starter-adb |
| Oracle AI Database JDBC/UCP | Oracle Database starter family |
| Oracle TxEventQ với JMS | AQ/JMS starter |
| Oracle TxEventQ với Spring Cloud Stream | TxEventQ binder |
| OCI Generative AI qua Spring AI | Spring AI Oracle |

Các artifact này không có chung lifecycle hoặc cùng version number. Chọn đúng artifact trước, sau đó mở release notes/API docs đúng version của artifact đó.

### Starter version và SDK version là hai việc khác nhau

Ứng dụng thường khai báo OCI starter. Starter kéo OCI SDK module phù hợp. Không cần khai báo thêm từng OCI SDK artifact nếu không có nhu cầu sử dụng trực tiếp.

Nếu ứng dụng dùng OCI SDK trực tiếp:

- Kiểm tra SDK version mà starter đã kéo.
- Dùng một bộ SDK version tương thích.
- Tránh một module OCI SDK 3.x nhưng module khác bị ép xuống version khác.
- Không override SDK chỉ để dùng một API mới mà chưa kiểm tra compatibility.
- Nếu cần override, ghi lại lý do, kiểm tra release notes và chạy integration tests.

## 7. Quy trình chọn version theo từng bước

~~~mermaid
flowchart TD
    A[Đọc build hiện tại] --> B[Chốt Java + Spring Boot]
    B --> C{Có Spring Cloud projects khác?}
    C -->|Có| D[Chọn Spring Cloud release train]
    C -->|Không| E[Bỏ qua Spring Cloud BOM]
    D --> F[Chọn OCI service starter]
    E --> F
    F --> G[Chọn OCI release line phù hợp Boot]
    G --> H[Đọc changelog và version docs]
    H --> I[Kiểm tra SDK/transitive graph]
    I --> J[Compile + startup + integration tests]
    J --> K{Tương thích và test đạt?}
    K -->|Có| L[Khóa version và triển khai thử]
    K -->|Không| M[Điều chỉnh đúng tầng version]
    M --> H
~~~

### Bước 1: ghi nhận baseline

Thu thập từ build file và resolved dependency graph:

- Java toolchain/source compatibility.
- Spring Boot plugin/parent.
- Spring Framework version thực tế.
- Spring Cloud release train nếu có.
- Spring Cloud Stream/Spring AI version nếu có.
- OCI starter hoặc OCI SDK đã tồn tại.
- Các override của Jackson, Netty, HTTP client, logging và test libraries.

Không chỉ nhìn version được khai báo trong pom.xml hoặc build.gradle; version thực tế sau resolution mới là thứ chạy trong ứng dụng.

### Bước 2: chốt Boot major/minor

Chọn Boot version dựa trên policy hỗ trợ và nền tảng ứng dụng. Kiểm tra Java runtime và Spring Framework version do Boot quản lý.

Nếu đang dùng Boot 3, chọn OCI 1.x line tương thích. Nếu đang dùng Boot 4, xem OCI 2.x line. Đừng nâng Boot major chỉ để có thể dùng một starter mới nếu ứng dụng chưa sẵn sàng migration.

### Bước 3: chọn release OCI có bằng chứng tương thích

Đọc:

- Spring Cloud Oracle release notes.
- OCI reference docs đúng version.
- README/release matrix của project.
- POM của artifact trên Maven Central.
- Sample app dùng cùng release line.
- Issue/release note về API hoặc transitive dependency có liên quan.

Tìm chính xác Boot version mà release được xây dựng/test. Nếu docs chỉ nêu major compatibility, hãy xem release notes và CI/test matrix để xác minh minor line.

### Bước 4: kiểm tra project Spring Cloud khác

Nếu ứng dụng dùng Spring Cloud Stream, chọn release train tương thích Boot. Sau đó kiểm tra TxEventQ binder version riêng. Không cho rằng Spring Cloud release train BOM quản lý binder Oracle.

Nếu ứng dụng không dùng Spring Cloud projects khác, đừng thêm BOM không cần thiết. Ít nguồn quản lý version hơn giúp dependency graph dễ hiểu hơn.

### Bước 5: thêm đúng starter

Thêm một service starter tối thiểu cho use case trước. Kiểm tra starter kéo theo core và SDK nào. Không thêm implementation module trực tiếp nếu starter đã cung cấp.

### Bước 6: kiểm tra graph

Dùng Maven/Gradle dependency report để xem version được resolve. Tìm duplicate hoặc override ngoài dự kiến.

### Bước 7: kiểm tra compile, startup và runtime

Chạy test trong cùng JDK/Boot/OCI release line. Kiểm tra auto-configuration và thực hiện một thao tác OCI thật trong test compartment. Compile thành công chưa chứng minh authentication, IAM hoặc service operation hoạt động.

### Bước 8: khóa và ghi nhận baseline

Lưu lại:

- Java version.
- Spring Boot version.
- Spring Cloud train nếu dùng.
- OCI starter version.
- Oracle Database/Binder/Spring AI version nếu dùng.
- OCI SDK resolved version.
- Dependency tree hoặc SBOM.
- Kết quả test và môi trường kiểm thử.

## 8. Kiểm tra dependency graph với Maven

### Xem dependency tree

~~~bash
mvn dependency:tree
~~~

Lọc các dependency quan trọng:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.boot,org.springframework,org.springframework.cloud,com.oracle.cloud.spring,com.oracle.oci.sdk
~~~

Xem dependency bị loại do conflict:

~~~bash
mvn dependency:tree -Dverbose
~~~

Kiểm tra dependency management:

~~~bash
mvn help:effective-pom
~~~

Các lệnh này giúp xác định:

- OCI starter version nào được resolve.
- OCI SDK module nào xuất hiện và version có đồng bộ không.
- Spring Boot/Framework có bị override không.
- Spring Cloud release train đang quản lý artifact nào.
- Một transitive dependency có bị chọn version thấp hơn hoặc cao hơn dự kiến không.

### Enforcer và convergence

Trong project lớn, có thể dùng Maven Enforcer để phát hiện dependency convergence và rule về Java/Maven. Không bật rule cứng một cách máy móc nếu project có dependency hợp lệ cần nhiều version; phải xử lý exception có lý do và được review.

Không dùng dependencyManagement để ép tất cả com.oracle.oci.sdk sang version mới hơn mà chưa kiểm tra tương thích của OCI starter.

## 9. Kiểm tra dependency graph với Gradle

### Xem toàn bộ dependency

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

### Xem dependency cụ thể

~~~bash
./gradlew dependencyInsight --dependency spring-cloud-oci --configuration runtimeClasspath
~~~

~~~bash
./gradlew dependencyInsight --dependency oci-java-sdk-common --configuration runtimeClasspath
~~~

~~~bash
./gradlew dependencyInsight --dependency spring-framework --configuration runtimeClasspath
~~~

Các lệnh cho biết dependency nào đưa module vào graph và vì sao Gradle chọn version đó.

### Version catalog

Khi nhiều module trong tổ chức cùng dùng OCI starter, có thể tập trung version vào Gradle version catalog. Cần cập nhật catalog sau khi đã xác minh compatibility; catalog không thay thế việc đọc release notes.

Không khai báo một version catalog alias dùng chung cho OCI, Oracle Database starter và TxEventQ binder nếu chúng có version line khác nhau.

## 10. Các lỗi tương thích thường gặp và cách xử lý

### 10.1. NoSuchMethodError

Thường xảy ra khi compile và runtime dùng hai version khác nhau của cùng thư viện. Ví dụ code được compile với Spring Framework hoặc OCI SDK mới nhưng runtime nạp version cũ.

Cách xử lý:

1. Đọc class/method trong stack trace.
2. Xác định artifact chứa class đó.
3. Dùng dependency tree/dependencyInsight tìm tất cả version.
4. Kiểm tra BOM/constraint/explicit dependency đã override chưa.
5. Đồng bộ đúng release line thay vì thêm ngẫu nhiên một jar.

### 10.2. NoClassDefFoundError hoặc ClassNotFoundException

Có thể do starter thiếu, module implementation không có trong graph, package đã thay đổi giữa major version hoặc classpath runtime khác build classpath.

Cách xử lý:

- Xác minh đúng artifact starter.
- Không chỉ thêm module core theo phỏng đoán.
- Kiểm tra compileClasspath và runtimeClasspath.
- Kiểm tra shaded/packaged jar hoặc container image.
- So sánh dependency graph của local và CI.

### 10.3. BeanCreationException

Bean có thể không tạo được vì:

- Spring Boot/Framework API không tương thích.
- Property binding sai tên.
- Authentication provider không được khởi tạo.
- Region/compartment thiếu.
- Một dependency transitive bị thiếu hoặc lệch version.
- Auto-configuration condition không thỏa.

Đọc nguyên nhân sâu nhất trong stack trace. Không phải mọi BeanCreationException đều là version issue.

### 10.4. Không có bean Storage

Kiểm tra:

1. Có dùng spring-cloud-oci-starter-storage đúng group/artifact không?
2. Version có cùng release line với Spring Boot không?
3. Starter có nằm trên runtime classpath không?
4. Auto-configuration có bị exclude không?
5. Property enabled hoặc profile có tắt tích hợp không?
6. Có bean tùy chỉnh xung đột hoặc điều kiện thiếu không?

Dùng Actuator conditions report trong môi trường debug có kiểm soát để biết auto-configuration nào được áp dụng hoặc bị bỏ qua. Không expose endpoint nhạy cảm ra public.

### 10.5. Lỗi OCI SDK hoặc HTTP client

Nếu stack trace nhắc OCI SDK, Jersey, Netty, Jackson hoặc TLS:

- Xem version OCI SDK thực tế.
- Kiểm tra có SDK module bị ép sang version khác không.
- Kiểm tra HTTP client dependency và transport được chọn.
- Kiểm tra Java runtime và TLS provider.
- Xác minh starter release đang yêu cầu version nào.

Không thêm cả Jersey và Apache HTTP client chỉ vì một ví dụ cũ có dùng; theo dependency và cấu hình của release đang chạy.

### 10.6. Compile thành công nhưng gọi OCI bị 401/403

Đây thường là authentication/authorization hoặc cấu hình runtime, không phải compile compatibility:

- Xác minh authentication mode.
- Xác minh workload identity/API key.
- Kiểm tra region và compartment.
- Kiểm tra IAM policy và dynamic group.
- Kiểm tra network route, endpoint và clock skew nếu dùng token/signature.

Giữ phân biệt giữa lỗi dependency version và lỗi quyền OCI.

## 11. Migration từ Spring Boot 3/OCI 1.x sang Boot 4/OCI 2.x

Migration major cần được lập kế hoạch như một thay đổi nền tảng.

### Trước migration

- Ghi baseline Java, Boot, Framework và OCI starter.
- Lưu dependency tree và test report.
- Kiểm tra các API đã deprecated.
- Xác định project Oracle nào đang dùng.
- Kiểm tra sample/release note của OCI 2.x.
- Chọn target JDK/build tool phù hợp.
- Kiểm tra Spring Cloud release train cần nâng cùng Boot.

### Trong migration

1. Nâng JDK/build tool nếu cần.
2. Nâng Spring Boot và Spring Framework theo cặp được hỗ trợ.
3. Nâng Spring Cloud release train nếu ứng dụng có project Spring Cloud.
4. Nâng Spring Cloud OCI sang 2.x tương thích.
5. Nâng database starters, TxEventQ binder và Spring AI Oracle theo version riêng.
6. Cập nhật package/API/config đã thay đổi.
7. Kiểm tra OCI SDK resolved graph.
8. Chạy compile, unit, integration và smoke tests.
9. Kiểm tra auth, Object Storage, Vault và messaging trên OCI test compartment.

Không đổi toàn bộ version cùng lúc rồi chỉ nhìn lỗi cuối cùng. Chia thay đổi thành các nhóm để xác định nguồn gây lỗi và rollback dễ hơn.

### Sau migration

- Khóa dependency version.
- Cập nhật container base image/JDK.
- Lưu SBOM.
- Kiểm tra CVE và license.
- Chạy test trên runtime giống production.
- Theo dõi startup, auth, latency, retries và resource usage sau rollout.
## 12. Dependency version độc lập giữa các nhánh Oracle

Spring Cloud Oracle là umbrella project nhưng các subproject không nhất thiết phát hành cùng số version.

| Nhánh | Ví dụ version snapshot | Cần kiểm tra |
| --- | --- | --- |
| Spring Cloud OCI | 2.0.4 | Spring Boot/Framework, OCI SDK, auto-configuration |
| Oracle AI Database starters | 26.3.0 | JDBC/UCP/Wallet, Oracle Database version, Boot compatibility |
| TxEventQ Stream Binder | 0.21.0 | Spring Cloud Stream train, Boot, database connectivity |
| Spring AI Oracle | 2.0.1 | Spring AI API version, Boot, OCI Generative AI |

Ví dụ, spring-cloud-oci-starter-storage:2.0.4 không có nghĩa Oracle Database UCP starter cũng phải dùng 2.0.4. Hai artifact thuộc hai project/version family khác nhau.

Khi một ứng dụng dùng nhiều nhánh:

- Đọc compatibility của từng nhánh.
- Kiểm tra Spring Boot baseline chung.
- Kiểm tra Spring Cloud Stream/Spring AI version riêng.
- Kiểm tra dependency graph hợp nhất.
- Không giả định các project đã được test cùng nhau nếu release notes không nói vậy.

### Ví dụ một ứng dụng có nhiều project Oracle

Giả sử Invoice Service cần:

- Oracle AI Database qua UCP.
- OCI Object Storage để lưu PDF.
- TxEventQ để phát event.
- OCI Vault để đọc secret.

Ứng dụng có thể cần các version family khác nhau. Hãy xác minh từng starter/binder theo Boot baseline, sau đó kiểm tra graph hợp nhất. Nếu mỗi project đều hoạt động riêng nhưng khi ghép lại xảy ra conflict, nguyên nhân thường nằm ở dependency dùng chung như Spring Framework, Jackson, OCI SDK, JDBC driver hoặc Spring Cloud Stream.

Không ép tất cả artifact về cùng version chỉ để nhìn build file gọn hơn. Dùng version đúng theo release của từng project.

## 13. Version alignment và OCI runtime configuration

Sau khi version tương thích, ứng dụng vẫn cần cấu hình OCI đúng. Đây là bước khác với dependency alignment.

### Authentication

Chọn auth theo môi trường:

- FILE cho local development.
- Instance Principal cho OCI Compute.
- Resource Principal cho Functions/resource được hỗ trợ.
- Workload Identity cho OKE khi đã cấu hình federation.
- SIMPLE/API key khi môi trường và policy cho phép.

Không commit private key hoặc profile file vào repository.

### Region và compartment

Kiểm tra region của resource và compartment target. Cấu hình region sai có thể tạo cảm giác starter lỗi dù dependency graph hoàn toàn đúng.

### IAM policy

Identity được xác thực không đồng nghĩa được phép gọi service. Cấp quyền tối thiểu cho Object Storage, Vault, Queue hoặc Streaming theo use case.

### Timeout/retry và client lifecycle

OCI SDK có retry/timeout behavior. Tránh thêm retry ở nhiều tầng không có budget chung. Dùng client bean được auto-configure và không tạo client mới cho mỗi request.

## 14. Kiểm thử tương thích trước khi merge

Một bộ test tối thiểu nên kiểm tra nhiều lớp:

| Lớp | Điều cần xác minh |
| --- | --- |
| Build | Compile với JDK và build tool đúng |
| Dependency graph | Không có Spring/OCI SDK version conflict ngoài dự kiến |
| Context startup | Application context khởi động được |
| Auto-configuration | Bean OCI cần thiết được tạo |
| Authentication | Workload xác thực bằng identity dự kiến |
| IAM | Có quyền đúng và không cấp quá rộng |
| Service integration | Thao tác thật với test resource thành công |
| Retry/timeout | Lỗi transient và throttling được xử lý đúng |
| Shutdown | Client/connection được đóng đúng |
| Packaging | Container runtime dùng cùng JDK/dependency graph |

### Test context và auto-configuration

Một test khởi động Spring context giúp phát hiện lỗi thiếu class hoặc bean condition trước khi triển khai:

~~~java
@SpringBootTest
class OciStorageContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void storageBeanIsConfigured() {
        assertThat(context.getBean(Storage.class)).isNotNull();
    }
}
~~~

Test này cần môi trường test có cấu hình phù hợp. Nếu auto-configuration cần OCI identity ngay lúc startup, có thể dùng profile/test configuration hoặc mock phù hợp cho context test. Integration test gọi OCI thật vẫn cần một test compartment và test identity.

Không viết một context test chỉ assert context loads rồi coi đó là bằng chứng đầy đủ cho upload/download hoặc IAM.

### Test local không thay thế test workload identity

FILE profile có thể chạy tốt trên laptop nhưng production OKE/Compute dùng identity khác. Cần ít nhất một integration test trên môi trường runtime gần production để xác minh principal và IAM policy.

### Kiểm thử theo service

Với Storage:

- Upload object.
- Download và kiểm tra checksum.
- Xác minh metadata/content type.
- Test overwrite/conditional write nếu use case cần.

Với Vault:

- Đọc secret bằng identity test.
- Xác minh quyền bị từ chối khi thiếu policy.
- Kiểm tra rotation/refresh theo bean lifecycle.

Với Queue/Streaming:

- Gửi và nhận message.
- Kiểm tra redelivery hoặc checkpoint/replay.
- Xác minh idempotency và consumer concurrency.

## 15. Quản lý version trong CI/CD

Version được chọn cần được khóa và kiểm tra liên tục.

- Không dùng dynamic version như latest.release trong production build.
- Không dùng snapshot ngoài môi trường thử nghiệm.
- Dùng Maven/Gradle dependency locking khi phù hợp.
- Lưu SBOM theo build.
- Quét CVE và theo dõi OCI SDK transitive updates.
- Kiểm tra dependency convergence.
- Chạy build với JDK/container giống production.
- Cập nhật version có chủ đích qua pull request và test.
- Ghi lý do nếu phải override dependency do starter kéo theo.

Một release patch mới có thể cập nhật OCI SDK, Netty, Jackson hoặc Spring Framework. Đọc release notes trước khi nâng, vì patch không chỉ là con số thay đổi.

### Version catalog và central properties

Nếu nhiều service cùng dùng OCI starter, quản lý version ở một nơi giúp tránh mỗi module tự chọn một patch. Có thể dùng Maven properties, Gradle version catalog hoặc platform nội bộ.

Tuy nhiên, centralization chỉ giải quyết việc lặp version. Nó không chứng minh version đó tương thích. Trước khi cập nhật central property:

1. Xác minh release line và compatibility.
2. Kiểm tra release notes và security updates.
3. Chạy dependency graph checks.
4. Chạy test cho các service bị ảnh hưởng.
5. Triển khai canary hoặc staging trước production.

### Reproducible build

Giữ dependency resolution có thể lặp lại:

- Pin plugin và dependency version.
- Không dùng version range cho dependency production.
- Dùng dependency lock khi phù hợp.
- Lưu SBOM và build metadata.
- Kiểm tra container image chứa đúng JDK.
- Không để local Maven cache che giấu artifact chưa được khai báo.

## 16. Bài thực hành: chọn OCI Storage starter cho Invoice Service

**Bối cảnh:** Invoice Service hiện chạy Spring Boot 4.1.1, Java 17 và cần lưu PDF vào OCI Object Storage. Ứng dụng chưa dùng Spring Cloud Stream. Nhiệm vụ là thêm OCI Storage starter và chứng minh version graph tương thích.

### Phần A — Xác định baseline

1. Chạy java -version.
2. Kiểm tra Maven/Gradle version.
3. Xác định Spring Boot parent/plugin version.
4. In dependency tree hiện tại.
5. Xác minh Spring Framework version thực tế.

### Phần B — Chọn starter

1. Chọn com.oracle.cloud.spring:spring-cloud-oci-starter-storage.
2. Chọn release line OCI 2.x phù hợp Boot 4.
3. Dùng 2.0.4 làm snapshot tham khảo cho Boot 4.1.1 theo release notes.
4. Không thêm Spring Cloud BOM nếu không có Spring Cloud project khác.
5. Không thêm spring-cloud-oci-storage implementation module riêng khi starter đã kéo theo.

### Phần C — Kiểm tra graph

1. Chạy mvn dependency:tree hoặc Gradle dependencies.
2. Xác minh OCI core và SDK modules cùng release tương thích.
3. Xác minh không có Spring Framework version bị override.
4. Ghi lại resolved graph/SBOM.
5. Chạy compile và test.

### Phần D — Kiểm thử runtime

1. Cấu hình FILE authentication cho local test.
2. Cấu hình region và compartment.
3. Cấp policy tối thiểu cho test identity.
4. Upload/download một PDF test.
5. Kiểm tra checksum và metadata.
6. Chạy test trong OCI runtime dùng principal production tương ứng.

### Phần E — Kiểm tra nâng version

1. Thử đánh giá Boot 4.2.0 nhưng chưa nâng OCI 2.0.4 một cách mặc định.
2. Đọc release notes mới hơn của Spring Cloud OCI.
3. Xác minh OCI starter có build/test với Boot 4.2 và Framework 7.1 chưa.
4. Nếu chưa có xác nhận, giữ baseline đã kiểm thử hoặc chạy compatibility test có kiểm soát trước khi nâng.
5. Ghi quyết định version và lý do vào pull request.

### Sản phẩm cần nộp

- Bảng version Java/Boot/Framework/Spring Cloud/OCI SDK.
- Dependency declaration của OCI Storage starter.
- Dependency tree hoặc dependencyInsight output.
- Bằng chứng application context tạo Storage bean.
- Integration test upload/download.
- IAM policy tối thiểu cho test workload.
- SBOM và kết quả dependency vulnerability scan.
- Ghi chú về compatibility evidence và quyết định upgrade.

## 17. Câu hỏi tự kiểm tra

1. Vì sao phải xác định Java và Spring Boot trước khi thêm OCI starter?
2. Spring Cloud release train BOM quản lý những project nào?
3. Vì sao Spring Cloud OCI version không phải Spring Cloud release train version?
4. Spring Cloud Oracle 1.x và 2.x theo các Spring Boot major nào?
5. Release notes 2.0.4 ghi nền tảng Spring Boot cụ thể nào?
6. Vì sao không mặc định OCI 2.0.4 tương thích đã được kiểm thử với Boot 4.2?
7. OCI SDK version được kéo vào dependency graph từ đâu?
8. Vì sao không nên ép tất cả OCI SDK modules sang version tùy ý?
9. Vì sao database starter, TxEventQ binder và Spring AI Oracle có version độc lập?
10. Khi nào cần import spring-cloud-dependencies?
11. Vì sao starter không cần thêm implementation module nếu nó đã kéo transitive dependency?
12. NoSuchMethodError thường chỉ ra loại xung đột nào?
13. Build thành công có chứng minh workload identity hoạt động không?
14. Cần kiểm tra gì khi auto-configuration không tạo Storage bean?
15. Những bằng chứng nào cần lưu trước khi merge dependency update?

## 18. Ghi nhớ

- Chọn version trước khi thêm starter bằng cách xác định Java, Spring Boot, Spring Framework và OCI release line.
- Spring Cloud release train và Spring Cloud OCI là hai trục version khác nhau.
- OCI 1.x theo Boot 3; OCI 2.x theo Boot 4 và Spring Framework 7.
- Release notes của OCI 2.0.4 ghi nâng lên Spring Boot 4.1.1; không suy ra mọi patch Boot 4 đều đã được kiểm thử.
- Spring Boot 4.2.0 yêu cầu Spring Framework 7.1+, vì vậy phải kiểm tra release OCI hỗ trợ cụ thể trước khi nâng.
- Oracle Database starters, TxEventQ binder và Spring AI Oracle có version family riêng.
- Không dùng Spring Cloud BOM để thay thế OCI starter version management.
- Chỉ thêm starter service cần thiết; không thêm implementation module trùng lặp.
- Kiểm tra resolved dependency graph thay vì chỉ đọc version khai báo.
- Compile, startup, auto-configuration và integration test là các bước xác minh riêng.
- Phân biệt lỗi dependency compatibility với lỗi OCI authentication, IAM, region và network.
- Khóa version, lưu SBOM và cập nhật dependency có chủ đích trong CI/CD.

## Tài liệu tham khảo

- [Spring Cloud Oracle — Project overview](https://oracle.github.io/spring-cloud-oracle/site/docs/intro/)
- [Spring Cloud Oracle — Release notes](https://oracle.github.io/spring-cloud-oracle/site/docs/releases/changelog/)
- [Spring Cloud OCI 2.0.4 — OCI Core](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/core/)
- [Spring Cloud OCI — Configuration properties](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/configuration/)
- [Spring Cloud — Boot compatibility and getting started](https://spring.io/projects/spring-cloud/)
- [Spring Cloud — Supported versions](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions)
- [Spring Boot 4.2 — System requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot 4.0 — System requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html)
- [Spring Cloud Oracle — Archived 1.4.5 documentation](https://oracle.github.io/spring-cloud-oracle/latest/reference/html/index.html)
- [Maven Central — Spring Cloud OCI core 2.0.4](https://central.sonatype.com/artifact/com.oracle.cloud.spring/spring-cloud-oci-core)
- [Maven Central — Spring Cloud OCI Vault 2.0.4](https://central.sonatype.com/artifact/com.oracle.cloud.spring/spring-cloud-oci-vault)
- [Maven Central — Spring Cloud OCI Queue 2.0.4](https://central.sonatype.com/artifact/com.oracle.cloud.spring/spring-cloud-oci-queue)
