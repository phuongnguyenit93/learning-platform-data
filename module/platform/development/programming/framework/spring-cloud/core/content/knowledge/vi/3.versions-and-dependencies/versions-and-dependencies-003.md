# Quản lý phụ thuộc bằng spring-cloud-dependencies BOM

Trong hệ thống Spring Boot sử dụng nhiều thành phần Spring Cloud, một câu hỏi quan trọng xuất hiện trước khi viết mã: **phải chọn phiên bản nào để Spring Cloud Commons, Context, Config, LoadBalancer và các tích hợp khác hoạt động cùng nhau và tương thích với Spring Boot?** Nếu mỗi thư viện được khai báo với phiên bản riêng, ứng dụng có thể biên dịch thành công nhưng lỗi khi khởi động hoặc khi gọi API do các thư viện sử dụng hợp đồng khác nhau.

Spring Cloud giải quyết phần lớn vấn đề quản lý phiên bản bằng **release train** và **BOM (Bill of Materials)** có tọa độ **org.springframework.cloud:spring-cloud-dependencies**. Bài học thuộc chương **Phiên bản và phụ thuộc** của module **SPRING_CLOUD_CORE**. Nội dung hướng dẫn nguyên lý BOM, cách khai báo trong Maven và Gradle, cách phối hợp với BOM Spring Boot, kiểm tra dependency graph và quy trình nâng cấp an toàn.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

- Giải thích được **release train**, **BOM**, **dependency management** và **starter** là những khái niệm khác nhau.
- Chọn release train Spring Cloud dựa trên phiên bản Spring Boot, thay vì tự ghép số phiên bản từng dự án.
- Import BOM Spring Cloud bằng Maven hoặc Gradle và khai báo starter mà không chép phiên bản riêng.
- Phân tích phiên bản thực sự được resolve, kể cả khi có dependency bắc cầu và ghi đè.
- Nhận biết lỗi do thiếu BOM, lệch phiên bản, dependency trùng lặp hoặc xung đột giữa các bộ quy tắc quản lý.
- Áp dụng quy trình kiểm thử khi nâng cấp các abstraction Commons/Context, discovery, service registry, client giao tiếp dịch vụ và cấu hình bên ngoài.

## 2. BOM là gì và không làm gì?

**BOM** là một POM chứa danh sách các artifact được quản lý cùng phiên bản phù hợp. Nó là một **bảng quy tắc chọn phiên bản** cho những dependency mà dự án sử dụng; không phải một thư viện có chức năng nghiệp vụ.

Ví dụ, một ứng dụng cần Spring Cloud Config Client và Spring Cloud LoadBalancer. Nếu dự án đã import BOM Spring Cloud thích hợp, có thể khai báo hai starter mà không ghi số phiên bản riêng. Build tool dùng quy tắc trong BOM để xác định phiên bản mà release train đã công bố.

| Khái niệm | Vai trò | Có tự thêm mã chạy vào ứng dụng? |
| --- | --- | --- |
| **Spring Cloud release train**, ví dụ 2025.1.x | Nhóm các phiên bản dự án Spring Cloud được phát hành và quản lý cùng nhau | Không |
| **spring-cloud-dependencies BOM** | Quản lý phiên bản dependency trong release train tương ứng | Không |
| **spring-boot-dependencies BOM** | Quản lý phiên bản thư viện Spring Boot và nhiều dependency liên quan | Không |
| **Starter**, ví dụ spring-cloud-starter-loadbalancer | Thêm các thư viện và auto-configuration cần thiết cho một tính năng | Có, khi được khai báo trong dependencies |
| **Spring Boot Maven parent / Gradle plugin** | Cung cấp các thiết lập build và tích hợp cho ứng dụng Spring Boot | Không thay thế vai trò của Cloud BOM |

Điều quan trọng: **import BOM không tự bật service discovery, service registry, refresh scope hay giao tiếp HTTP**. Các tính năng đó chỉ xuất hiện sau khi bạn thêm đúng dependency, cấu hình tích hợp và chạy ứng dụng.

Spring Cloud gồm các dự án có nhịp phát hành và số phiên bản riêng. Ví dụ, phiên bản release train **2025.1.2** không có nghĩa mọi JAR Spring Cloud đều phải mang số **2025.1.2**. BOM định nghĩa bộ phiên bản tương ứng của từng dự án. Vì vậy, tránh tự suy ra phiên bản của **spring-cloud-commons**, **spring-cloud-context** hoặc **spring-cloud-config** từ tên release train.

~~~mermaid
flowchart TD
    BOOT[Spring Boot version] --> BOOTBOM[spring-boot-dependencies BOM]
    BOOT --> CHOOSE[Chọn release train tương thích]
    CHOOSE --> CLOUDBOM[spring-cloud-dependencies BOM]
    BOOTBOM --> RESOLVE[Resolve dependency graph]
    CLOUDBOM --> RESOLVE
    STARTERS[Starter thực sự được khai báo] --> RESOLVE
    RESOLVE --> RUNTIME[Classpath của ứng dụng]
~~~

Sơ đồ cho thấy **BOM quản lý phiên bản**, còn **dependencies quyết định thư viện có mặt** trên classpath. Hai bước không thể thay thế cho nhau.

## 3. Chọn release train đúng với Spring Boot

Trước khi thêm Cloud BOM, hãy xác định phiên bản Spring Boot thực tế của dự án. Spring Cloud công bố **bảng tương thích giữa release train và thế hệ Spring Boot** tại trang dự án chính thức. Không thể giả định release train có năm phát hành mới nhất luôn tương thích với mọi dòng Boot.

Các ví dụ theo thông tin Spring Cloud công bố:

| Spring Cloud release train | Thế hệ Spring Boot tương thích | Lưu ý |
| --- | --- | --- |
| **2025.1.x (Oakwood)** | **4.0.x**; **4.1.x từ Spring Cloud 2025.1.2** | Ví dụ Spring Cloud 2025.1.2 được công bố tương thích Spring Boot 4.1.0 |
| **2025.0.x (Northfields)** | **3.5.x** | Dòng lịch sử; kiểm tra trạng thái hỗ trợ trước khi sử dụng cho dự án mới |
| **2024.0.x (Moorgate)** | **3.4.x** | Dòng lịch sử; không mặc định còn được hỗ trợ |

Các dòng được đánh dấu hết vòng đời trên trang Spring Cloud không nên được xem là khuyến nghị mặc định cho dự án mới. Bảng ở đây giúp hiểu cách đọc quan hệ phiên bản, **không thay thế ma trận tương thích và thông báo hỗ trợ tại thời điểm triển khai**.

Quy trình chọn:

1. Kiểm tra phiên bản Spring Boot trong parent POM, BOM hoặc Gradle plugin của ứng dụng.
2. Tra **Release Train Spring Boot Compatibility** tại https://spring.io/projects/spring-cloud/.
3. Chọn release train phù hợp và một **service release** ổn định của chính train đó.
4. Đọc ghi chú phát hành để biết điều kiện về bản vá Boot, thay đổi API hoặc starter đã đổi tên.
5. Dùng **một phiên bản BOM cụ thể**, có thể lặp lại khi build; đưa việc nâng cấp vào pull request riêng.

Trong các ví dụ tiếp theo, dùng **Spring Boot 4.1.0** và **Spring Cloud 2025.1.2** vì cặp này được thông báo tương thích khi Spring Cloud 2025.1.2 phát hành. Đây là **cặp phiên bản minh họa đã xác nhận**, không phải lời khẳng định rằng chúng là phiên bản mới nhất ở mọi thời điểm.

## 4. Maven: dùng Spring Boot parent và import Spring Cloud BOM

Đây là đường đi phổ biến cho ứng dụng Spring Boot dùng Maven. Spring Boot parent cung cấp thiết lập build và dependency management cho Spring Boot. Ta import thêm **spring-cloud-dependencies** trong **dependencyManagement** để quản lý các module Spring Cloud.

Ví dụ POM tối giản cho mục đích học tập:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>cloud-bom-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
        <spring-cloud.version>2025.1.2</spring-cloud.version>
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
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-loadbalancer</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Giải thích các dòng quyết định:

- **groupId + artifactId** xác định đúng BOM Spring Cloud.
- **version** chọn service release của release train. Biến **spring-cloud.version** giúp thay phiên bản tại một nơi.
- **type=pom** chỉ ra artifact được import là POM.
- **scope=import** chỉ hợp lệ cho dependency kiểu POM bên trong **dependencyManagement**. Maven đưa các quy tắc quản lý phiên bản từ BOM vào effective dependency management.
- Các starter trong **dependencies** không khai báo version vì phiên bản được quản lý bởi BOM tương ứng.

Không thêm **spring-cloud-dependencies** như một dependency chạy ứng dụng. Nó cũng không thay **spring-boot-starter-parent**; Cloud BOM chỉ quản lý dependency và không cung cấp cấu hình plugin thay Boot parent.

### 4.1. Nếu dự án dùng parent khác

Nhiều tổ chức dùng parent POM nội bộ nên không thể kế thừa trực tiếp **spring-boot-starter-parent**. Khi đó, có thể import cả **spring-boot-dependencies** và **spring-cloud-dependencies** trong **dependencyManagement**:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.1.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>2025.1.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đoạn trên là phần đặt vào POM có parent riêng, không phải một POM hoàn chỉnh. Việc import **spring-boot-dependencies** không tự cấu hình compiler, packaging, test plugin hoặc các quy tắc khác mà Boot parent thường cung cấp. Phải quản lý plugin build riêng khi cần.

### 4.2. Maven nhiều module

Nếu các module ứng dụng cùng kế thừa một parent nội bộ, đặt hai quy tắc BOM trong parent để các module con dùng chung chính sách phiên bản. Mỗi module chỉ khai báo starter nó cần. Module không kế thừa dependency management của parent đó phải import BOM theo cách phù hợp; việc hai thư mục nằm trong cùng reactor Maven **không tự đảm bảo** chúng có cùng effective dependency management.

Với thư viện tái sử dụng có thể được nhiều ứng dụng tiêu thụ, cần cân nhắc có nên áp đặt dependency management lên consumer hay không. BOM kiểm soát phiên bản của một ứng dụng chỉ khi nó được áp dụng trong dự án tiêu thụ; đừng giả định mọi consumer sẽ thừa hưởng parent nội bộ của thư viện.

## 5. Gradle: hai cách dùng BOM phổ biến

Gradle có thể dùng plugin quản lý dependency của Spring hoặc **native platform** của Gradle. Hai cách khác nhau ở cách nhập BOM và quy tắc chọn phiên bản. Cần xác định nhóm đã dùng cách nào để tránh nhiều nơi cùng quản lý một artifact mà không rõ ưu tiên.

### 5.1. Groovy DSL với io.spring.dependency-management

Ví dụ **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

ext {
    springCloudVersion = '2025.1.2'
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

Khi **org.springframework.boot** và **io.spring.dependency-management** cùng được áp dụng, Spring Boot Gradle plugin tự import **spring-boot-dependencies** phù hợp với phiên bản plugin Boot. Ta import thêm Cloud BOM bằng **mavenBom**. Đây là cách được minh họa trên trang dự án Spring Cloud.

### 5.2. Kotlin DSL với Gradle native platform

Nếu không dùng plugin **io.spring.dependency-management**, khai báo cả Boot BOM và Cloud BOM như các **platform dependencies**. Ví dụ **build.gradle.kts**:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "4.1.0"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

repositories {
    mavenCentral()
}

val springBootVersion = "4.1.0"
val springCloudVersion = "2025.1.2"

dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:${springBootVersion}"))
    implementation(platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"))

    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
}
~~~

Trong Gradle native platform, các version từ BOM trở thành **dependency constraints**. Với **platform(...)**, chúng thường là phiên bản ưu tiên; Gradle vẫn có thể chọn phiên bản khác trong quá trình giải quyết xung đột. Vì vậy, **không được suy kết quả cuối chỉ từ mã build**: kiểm tra bằng **dependencyInsight**.

Gradle còn có **enforcedPlatform(...)** để ép phiên bản chặt hơn, nhưng không nên dùng theo thói quen. Constraint nghiêm ngặt có thể xung đột với dependency khác và lan sang consumer khi xuất bản thư viện. Dùng khi thật sự cần và đã kiểm tra tác động.

**Lưu ý về cấu hình:** ví dụ sử dụng **implementation**. Với cấu hình riêng (ví dụ một source set đặc biệt), cần kiểm tra cấu hình đó có thừa hưởng platform constraints không. Trong dự án nhiều module Gradle, thường áp dụng BOM qua convention plugin hoặc cấu hình chung để các module liên quan sử dụng chính sách thống nhất.

## 6. Chọn các starter theo nhu cầu chức năng

Sau khi import BOM, bước tiếp theo là thêm **đúng dependency** cho chức năng cần dùng. Ví dụ:

~~~xml
<dependencies>
    <!-- Discovery/LoadBalancer cho lời gọi theo service ID -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>

    <!-- Chỉ thêm nếu ứng dụng lấy cấu hình từ Config Server -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>
</dependencies>
~~~

Mỗi starter kéo theo những dependency bắc cầu cần thiết, có thể bao gồm **Spring Cloud Commons** và **Spring Cloud Context**. Nếu ứng dụng sử dụng trực tiếp API trong các module này, kiểm tra dependency tree và cân nhắc khai báo dependency trực tiếp phù hợp với quy ước dự án.

Các tình huống trong phạm vi **SPRING_CLOUD_CORE**:

| Bài toán | Phần Spring Cloud có liên quan | Vai trò của BOM |
| --- | --- | --- |
| Truy vấn **DiscoveryClient**, **ServiceInstance** | Spring Cloud Commons và tích hợp discovery được chọn | Quản lý phiên bản module Commons cùng adapter discovery |
| Dùng **ServiceRegistry** | Commons và adapter registry cụ thể (nếu hỗ trợ) | Giúp các module Cloud cùng thuộc tập phiên bản đã phối hợp |
| Client gọi theo **service ID** | Spring Cloud LoadBalancer | Quản lý dependency của starter và các module liên quan |
| Đọc cấu hình ngoài qua Config Server | Spring Cloud Config Client và Context | Giữ Config Client đồng bộ với bộ Spring Cloud được chọn |
| Dùng **@RefreshScope** và refresh event | Spring Cloud Context | Quản lý Context phù hợp với môi trường Boot/Cloud |
| Phối hợp gọi dịch vụ và cơ chế chịu lỗi | Starter giao tiếp và tích hợp resilience phù hợp | Cung cấp version management; **không tự thiết lập** timeout, retry hoặc circuit breaker |

Import BOM và thêm starter **không tạo registry server**, không tự đăng ký instance vào hạ tầng cụ thể và không tự mở endpoint quản trị. Những phần đó vẫn cần dependency, cấu hình và quyền truy cập tương ứng.

## 7. Maven và Gradle thực sự chọn phiên bản như thế nào?

Điểm dễ nhầm là BOM **quản lý** phiên bản, trong khi build tool vẫn phải **resolve** một dependency graph có thể chứa dependency bắc cầu, version ghi trực tiếp và các BOM khác.

### 7.1. Ví dụ Maven

Giả sử Cloud BOM quản lý một module Cloud với phiên bản **A**, một starter khai báo phiên bản không ghi rõ, và một dependency bắc cầu khác yêu cầu phiên bản **B**. Quy tắc **dependencyManagement** có thể quyết định phiên bản được chọn cho module được quản lý. Tuy nhiên:

- Một dependency **ghi version trực tiếp** trong POM dự án có thể vượt qua phiên bản mặc định từ BOM.
- Quy tắc dependency management khai báo ngay tại POM hiện tại có thể ưu tiên hơn quy tắc kế thừa từ parent.
- Khi nhiều BOM quản lý cùng một tọa độ, **thứ tự và vị trí khai báo có thể tác động đến effective dependency management**.
- Maven còn áp dụng các quy tắc dependency mediation cho dependency không được quản lý phù hợp.

Vì vậy, không nên dựa vào câu “đã import BOM là mọi thứ chắc chắn đúng”. Xác minh **effective POM** và **dependency tree** của module thực sự chạy.

### 7.2. Ví dụ Gradle

Gradle native platform biến các version được quản lý thành constraints; xung đột có thể dẫn đến phiên bản được chọn khác với phiên bản ưu tiên trong BOM. Plugin dependency management của Spring có cơ chế nhập BOM riêng. Hai kiểu quản lý này **không hoàn toàn tương đương**; khi chuyển công cụ hoặc cập nhật plugin, cần so sánh resolved graph trước và sau.

Điểm chung cho cả hai hệ build: **BOM không bảo vệ khỏi một bản nâng cấp thiếu kiểm soát nếu bạn ép version, import BOM khác mâu thuẫn hoặc để nhiều đường phụ thuộc cùng đưa vào các API không tương thích**.

## 8. Kiểm tra dependency graph

Các lệnh sau là **ví dụ để chạy trong dự án mẫu của người học**, không phải thao tác bắt buộc cho tài liệu này. Nếu dùng Maven Wrapper hoặc Gradle Wrapper, ưu tiên wrapper đã cam kết phiên bản trong repository.

### 8.1. Maven

~~~bash
# Xem effective POM và dependencyManagement được kế thừa/import
mvn help:effective-pom

# Xem toàn bộ dependency tree
mvn dependency:tree

# Khoanh vùng các dependency thuộc Spring Cloud
mvn dependency:tree -Dincludes=org.springframework.cloud

# Kiểm tra một nhóm phụ thuộc khi nghi có xung đột
mvn dependency:tree -Dincludes=org.springframework:spring-core
~~~

Trong kết quả, đối chiếu **spring-cloud-commons**, **spring-cloud-context**, **spring-cloud-config-client** hoặc module đang gây lỗi với release train đã chọn. Xem cả các module Boot/Framework; một graph nhìn có vẻ đúng tên Cloud chưa bảo đảm phù hợp với Spring Boot.

### 8.2. Gradle

~~~bash
# Xem dependency graph được resolve tại runtime
./gradlew dependencies --configuration runtimeClasspath

# Giải thích lý do chọn phiên bản của một module
./gradlew dependencyInsight --dependency spring-cloud-commons --configuration runtimeClasspath

# Xem cách chọn một dependency có nhiều yêu cầu phiên bản
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

Trên Windows, thay **./gradlew** bằng **gradlew.bat** nếu cần. Lệnh **dependencyInsight** đặc biệt hữu ích để biết dependency nào yêu cầu phiên bản khác và constraint nào tham gia chọn kết quả.

Đừng chỉ nhìn version trong **pom.xml** hoặc **build.gradle**. Điều cần kiểm chứng là **phiên bản cuối cùng nằm trên compile/runtime classpath của module triển khai**.

## 9. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra và sửa |
| --- | --- | --- |
| Maven báo dependency không có version | Starter không được quản lý do thiếu BOM, import sai vị trí hoặc tọa độ | Đảm bảo BOM nằm trong **dependencyManagement**, có **type=pom** và **scope=import** |
| **Non-resolvable import POM** | Phiên bản BOM không tồn tại hoặc repository/proxy không tải được | Kiểm tra tọa độ BOM, repository và kết nối; không tùy tiện thay bằng version bất kỳ |
| Ứng dụng báo Spring Boot không tương thích với Spring Cloud | Chọn sai release train hoặc patch Boot ngoài phạm vi hỗ trợ của Cloud | So ma trận chính thức, nâng Cloud train/service release hoặc điều chỉnh Boot cho đúng cặp |
| **NoSuchMethodError**, **ClassNotFoundException**, **NoClassDefFoundError** | Có thể do JAR xung đột, ép version hoặc API đã thay đổi; còn có thể do nguyên nhân khác | Xem dependency tree/insight, stack trace và ghi chú phát hành; loại bỏ ghi đè gây xung đột |
| Hai module nội bộ dùng version Commons/Context khác nhau | Các module không kế thừa cùng BOM/convention, hoặc có override | So effective POM/resolved runtimeClasspath của **từng module** |
| Đã import BOM nhưng không có bean **DiscoveryClient** hoặc client load-balanced | BOM không thêm starter/adapter, hoặc chưa cấu hình | Kiểm tra dependency và cấu hình feature; BOM chỉ quản lý version |
| Config Client chạy nhưng không đọc cấu hình như mong đợi | Thiếu cấu hình import, server không có dữ liệu, hoặc thay đổi cơ chế khởi tạo giữa các phiên bản | Kiểm tra Config Data, log khởi động, profile/label và tài liệu theo train |
| Build qua nhưng lỗi chỉ xuất hiện khi chạy | Tương thích nhị phân/auto-configuration chưa được thử ở runtime | Bổ sung integration test và smoke test, không coi resolve thành công là đủ |

### 9.1. Spring Cloud Compatibility Verifier

Spring Cloud Commons có cơ chế **Compatibility Verifier** để phát hiện một số cặp Spring Boot–Spring Cloud không tương thích khi ứng dụng chạy, và có thể trả thông báo **APPLICATION FAILED TO START** kèm phiên bản Boot phù hợp. Đây là một lớp bảo vệ, **không phải cam kết mọi dependency và API đều tương thích**.

Nếu gặp lỗi, cách sửa ưu tiên là **chọn lại cặp Boot/Cloud đúng ma trận**. Tài liệu có đề cập thuộc tính **spring.cloud.compatibility-verifier.enabled** để điều khiển cơ chế kiểm tra ở những phiên bản hỗ trợ; không tắt xác minh chỉ để che đi sự lệch phiên bản. Cần đối chiếu cả cấu hình mặc định của nhánh tài liệu đang sử dụng.

### 9.2. Vì sao không nên ép version của một JAR?

Giả sử dự án dùng BOM Cloud đã kiểm thử cùng một nhóm module, nhưng bạn tự gắn version mới hơn cho **spring-cloud-commons** trong dependency trực tiếp. Lúc này **spring-cloud-context** và các adapter registry có thể vẫn dùng API theo bản cũ. Lỗi chỉ xuất hiện khi Spring tạo bean hoặc khi một phương thức được gọi.

Khi có nhu cầu sửa CVE hoặc lỗi cụ thể:

1. Tìm bản vá của **cùng release train** hoặc một train được khuyến nghị nâng cấp.
2. Đánh giá release notes và thay đổi chức năng ảnh hưởng đến ứng dụng.
3. Nếu buộc phải override một thư viện, ghi rõ lý do, phạm vi, phiên bản bị ảnh hưởng và kiểm thử runtime.
4. Xóa override khi BOM chính thức đã quản lý bản sửa tương ứng.

Version ghi đè có thể hợp lệ về mặt kỹ thuật, nhưng tạo thêm trách nhiệm bảo trì.

## 10. Quy trình nâng cấp BOM an toàn

Một lần nâng cấp release train có thể tác động cả những phần không xuất hiện trong feature đang sửa: Commons API, Context lifecycle, Config Client, adapter registry, LoadBalancer, quy tắc auto-configuration và dependency bắc cầu.

~~~mermaid
flowchart TD
    A[Xác định Boot đang dùng] --> B[Tra release train phù hợp]
    B --> C[Chọn service release cụ thể]
    C --> D[Cập nhật BOM tập trung]
    D --> E[So resolved dependency graph]
    E --> F[Chạy compile và test]
    F --> G[Thử startup, discovery và config]
    G --> H[Canary hoặc rollout có giám sát]
    H --> I[Chốt phiên bản và kế hoạch rollback]
~~~

### 10.1. Các phép thử nên có

| Nhóm kiểm thử | Tình huống | Tại sao cần |
| --- | --- | --- |
| **Build** | Resolve dependency, compile, chạy test hiện có | Bắt lỗi artifact, version và API tại compile time |
| **Khởi động** | Chạy ứng dụng với profile sản xuất giả lập | Bắt lỗi auto-configuration, bean creation và Compatibility Verifier |
| **Commons / discovery** | Tra instance theo service ID; registry không khả dụng | Xác nhận adapter và abstraction còn hoạt động cùng nhau |
| **LoadBalancer / giao tiếp** | Gọi một service, instance biến mất, timeout hoặc trả lỗi | Xác nhận đường gọi và chính sách lỗi không đổi ngoài ý muốn |
| **Config Client** | Startup khi Config Server hoạt động và khi mất kết nối | Kiểm tra hành vi fail-fast/optional và nguồn cấu hình được nhận |
| **Context / refresh** | Cập nhật cấu hình, kích hoạt refresh trong môi trường an toàn | Kiểm tra bean được làm mới đúng và không mất tính nhất quán |
| **Vận hành** | Health, metrics, log correlation, rollback | Phát hiện thay đổi không mong đợi sau khi triển khai |

Đối với thư viện có **API công khai**, phải kiểm tra cả consumer. Đối với ứng dụng đa dịch vụ, nên nâng cấp theo từng nhóm có tương tác rõ ràng, theo dõi lỗi HTTP, độ trễ, khả năng truy cập registry và nguồn cấu hình. Không đẩy toàn bộ cụm lên release train mới chỉ vì build của một module đã xanh.

### 10.2. Đo khác biệt trước và sau

Một bản ghi nâng cấp hữu ích cần có:

- **Cặp phiên bản cũ/mới:** Spring Boot, Spring Cloud release train, Java và build tool.
- **Resolved graph:** các artifact Commons, Context, Config, LoadBalancer và module tích hợp quan trọng.
- **Các override còn tồn tại:** lý do giữ hoặc bỏ.
- **Kết quả kiểm thử:** startup, discovery, giao tiếp, config, refresh, tình huống lỗi.
- **Tín hiệu vận hành:** error rate, P95/P99, số lần retry, lỗi kết nối registry và thời gian khởi động.

Nếu cần rollback, khôi phục **cả bộ phiên bản đã được kiểm thử**, không chỉ hạ một starter trong khi giữ các module Cloud khác ở bản mới.

## 11. Bài tập tự thực hành

Bạn có một ứng dụng **order-service** dùng Spring Boot và muốn thêm **Spring Cloud LoadBalancer** để gọi **inventory-service** theo service ID. Sau đó nhóm muốn dùng **Config Client** để lấy cấu hình ngoài.

Hãy thực hiện trong một dự án thử nghiệm:

1. Từ phiên bản Spring Boot đã chọn, tra ma trận tương thích và ghi lại **release train + service release**.
2. Import **spring-cloud-dependencies** vào Maven hoặc Gradle, không đặt version trực tiếp trên starter Cloud.
3. Chỉ thêm **spring-cloud-starter-loadbalancer**; kiểm tra dependency tree và nhận diện Commons/Context nếu chúng có trên classpath.
4. Thêm **spring-cloud-starter-config**; so sánh dependency graph trước và sau.
5. Thử một bản Spring Cloud train không tương thích trên nhánh thử nghiệm; ghi nhận lỗi resolve/startup nếu có, sau đó khôi phục bộ phiên bản phù hợp.
6. Viết một checklist ngắn về startup khi Config Server mất kết nối, gọi inventory khi instance mất kết nối và kiểm tra refresh scope khi thay đổi cấu hình.

**Tiêu chí hoàn thành:** có thể giải thích vì sao một starter chọn phiên bản cụ thể từ BOM, chứng minh bằng dependency graph và nêu được rủi ro runtime mà chỉ kiểm tra compile không bắt được.

## 12. Tổng kết

**spring-cloud-dependencies** là cơ chế chuẩn để quản lý một bộ dependency Spring Cloud theo release train. Nó giúp giảm việc gắn phiên bản từng JAR và hạn chế những tổ hợp Commons, Context, Config, discovery, registry hay LoadBalancer không được thiết kế để hoạt động cùng nhau. Tuy nhiên, BOM **không tự thêm chức năng** và **không bảo đảm** toàn bộ runtime tương thích khi có ghi đè hoặc cấu hình sai.

Khi thêm Spring Cloud vào Spring Boot, luôn bắt đầu từ ma trận tương thích, import BOM của đúng train, chỉ khai báo các starter cần thiết, kiểm tra resolved dependency graph và thử nghiệm cả hành vi phân tán. Quản lý phiên bản là một phần của khả năng **kiểm thử và vận hành** hệ thống, chứ không dừng lại ở một đoạn XML hay Gradle script.

## Tài liệu tham khảo

- [Spring Cloud — Release Trains, Compatibility và Getting Started](https://spring.io/projects/spring-cloud/): ma trận Boot/Cloud, ví dụ Maven và Gradle import BOM.
- [Spring Cloud 2025.1.2 release announcement](https://spring.io/blog/2026/06/11/spring-cloud-2025-1-2-aka-oakwood-has-been-released/): xác nhận hỗ trợ Spring Boot 4.1.0 ở bản train minh họa.
- [Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): dependencyManagement, import scope, transitive dependencies và dependency mediation.
- [Spring Boot Gradle Plugin — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html): dùng io.spring.dependency-management hoặc native BOM.
- [Gradle — Platforms](https://docs.gradle.org/current/userguide/platforms.html): platform, dependency constraints, enforcedPlatform và cách inspect kết quả.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): DiscoveryClient, ServiceRegistry và Compatibility Verifier.

**Ghi nhớ:** ví dụ phiên bản trong bài dùng cho học tập. Khi lập dự án thực tế, đối chiếu tài liệu chính thức tại thời điểm triển khai, trạng thái hỗ trợ của release train và bản vá bảo mật đang áp dụng.
