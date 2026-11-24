# Quản lý phiên bản thư viện bằng Spring Cloud BOM

Một ứng dụng Spring Cloud thường sử dụng nhiều thư viện có quan hệ phiên bản với nhau: Spring Boot, Spring Cloud Commons, Spring Cloud LoadBalancer, client của Eureka hoặc Consul và các thư viện nền tảng khác. Nếu tự chọn phiên bản cho từng dependency, dự án dễ rơi vào trạng thái các thành phần không tương thích dù từng thư viện vẫn tải và biên dịch được.

**Spring Cloud BOM (Bill of Materials)** giải quyết việc này bằng cách công bố một tập phiên bản đã được quản lý theo một Spring Cloud release train. Khi import BOM vào Maven hoặc Gradle, dự án có thể khai báo dependency mà không phải ghi phiên bản cho từng starter Spring Cloud. BOM giúp các thành phần cùng một release train phối hợp đúng với nhau; người phát triển vẫn phải chọn release train tương thích với phiên bản Spring Boot đang dùng.

## 1. Vì sao cần quản lý phiên bản tập trung?

Một ứng dụng thực hiện service discovery có thể cần các dependency như:

- Spring Boot để khởi tạo ứng dụng và cung cấp nền tảng Spring.
- Spring Cloud Commons để dùng các abstraction như DiscoveryClient và ServiceRegistry.
- Spring Cloud Netflix Eureka Client hoặc Spring Cloud Consul Discovery để kết nối registry.
- Spring Cloud LoadBalancer để chọn instance khi gọi service theo tên.
- Các thư viện HTTP, cấu hình và quan sát được những thành phần trên sử dụng gián tiếp.

Mỗi dependency có thể kéo theo nhiều dependency bắc cầu (transitive dependency). Ví dụ, một starter có thể phụ thuộc vào Spring Cloud Commons và các thư viện Spring khác. Nếu các phiên bản bị lệch, có thể xuất hiện lỗi biên dịch, lỗi `NoSuchMethodError`, `ClassNotFoundException`, lỗi tạo bean hoặc hành vi không nhất quán khi chạy.

| Cách quản lý | Đặc điểm | Hệ quả |
|---|---|---|
| Ghi phiên bản từng dependency | Mỗi starter và thư viện có version riêng | Khó nâng cấp, dễ lệch phiên bản |
| Dùng Spring Cloud BOM | Phiên bản được quản lý tập trung theo release train | Dependency Spring Cloud đồng bộ hơn, file build gọn hơn |
| Trộn BOM với nhiều version override tùy ý | Một số thư viện theo BOM, một số bị ghim riêng | Có thể phá vỡ tập phiên bản đã được kiểm thử cùng nhau |

Ví dụ khai báo thủ công dễ tạo ra sự không nhất quán:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    <version>VERSION_A</version>
</dependency>

<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    <version>VERSION_B</version>
</dependency>
~~~

Nếu hai version thuộc những release train khác nhau, chúng có thể không tương thích. BOM cho phép dự án chọn một release train rồi để bộ quản lý dependency cung cấp version phù hợp cho các artifact mà BOM quản lý.

## 2. BOM là gì?

BOM là một POM Maven có packaging là `pom`, chứa các quy tắc quản lý dependency. Trong Spring Cloud, BOM chính là artifact:

~~~text
org.springframework.cloud:spring-cloud-dependencies
~~~

Version của artifact này đại diện cho Spring Cloud release train. Một release train có thể có nhiều bản service release; dự án thường chọn bản phù hợp và được hỗ trợ theo ma trận tương thích chính thức.

BOM cung cấp **dependency management**:

- Khai báo version được quản lý cho nhiều artifact.
- Đồng bộ các thành phần Spring Cloud thuộc cùng release train.
- Quản lý một số dependency liên quan để hạn chế xung đột.
- Cho phép module khai báo dependency mà không lặp lại version.

BOM không tự thêm thư viện vào ứng dụng. Dự án vẫn phải khai báo dependency cần dùng trong phần `dependencies`.

Ví dụ, import BOM chỉ thiết lập quy tắc quản lý phiên bản:

~~~xml
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
~~~

Sau đó, dependency thực tế được khai báo riêng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
~~~

Trong ví dụ này, version của Eureka Client được lấy từ dependency management nếu artifact đó được BOM quản lý. Nếu chỉ import BOM mà không khai báo starter, ứng dụng sẽ không tự có Eureka Client trên classpath.

## 3. Phân biệt Spring Boot BOM và Spring Cloud BOM

Spring Boot và Spring Cloud là hai dự án có nhịp phát hành riêng:

| BOM | Phạm vi quản lý | Ví dụ artifact |
|---|---|---|
| Spring Boot dependency management | Spring Boot và hệ sinh thái thư viện mà Boot quản lý | `spring-boot-starter-web`, logging, Jackson |
| Spring Cloud dependency management | Các thành phần thuộc Spring Cloud release train | Eureka Client, Consul Discovery, LoadBalancer, Config |
| BOM của thư viện khác | Phạm vi riêng của thư viện hoặc nền tảng đó | Bộ thư viện quan sát, kiểm thử hoặc cloud SDK |

Một dự án Spring Cloud thường cần cả hai lớp quản lý: Spring Boot cung cấp nền tảng ứng dụng, Spring Cloud bổ sung các thành phần microservice tương thích với nền tảng đó.

Không chọn Spring Cloud version chỉ vì số version trông giống Spring Boot version. Ví dụ, một release train có thể mang tên theo năm trong khi Spring Boot dùng cách đánh số khác. Hai version phải được ghép theo ma trận tương thích do dự án Spring Cloud công bố.

## 4. Chọn release train tương thích

Trước khi import BOM, hãy xác định phiên bản Spring Boot và Java mà dự án đang dùng. Sau đó tra ma trận tương thích của Spring Cloud để chọn release train phù hợp.

Quy trình chọn phiên bản:

1. Xác định Spring Boot version đang được quản lý ở root project hoặc parent POM.
2. Xác định phiên bản Java và các giới hạn nền tảng của dự án.
3. Tra bảng tương thích Spring Boot ↔ Spring Cloud release train trong tài liệu chính thức của Spring Cloud.
4. Chọn một release train tương thích và một service release phù hợp trong train đó.
5. Khóa lựa chọn trong cấu hình tập trung để các module dùng cùng một bộ phiên bản.
6. Kiểm tra dependency đã resolve, build và chạy thử luồng ứng dụng quan trọng.

Không nên chọn Spring Cloud release train mới nhất một cách độc lập rồi ghép vào Spring Boot cũ. Tương tự, không nên nâng Spring Boot mà giữ nguyên một Spring Cloud train đã hết tương thích.

Ví dụ dưới đây dùng placeholder để minh họa. Thay `BOOT_VERSION_COMPATIBLE` và `CLOUD_TRAIN_VERSION` bằng các phiên bản cụ thể đã được đối chiếu với ma trận tương thích của dự án:

| Giá trị | Nơi dùng | Ý nghĩa |
|---|---|---|
| `BOOT_VERSION_COMPATIBLE` | Spring Boot parent hoặc plugin | Phiên bản Spring Boot của ứng dụng |
| `CLOUD_TRAIN_VERSION` | `spring-cloud-dependencies` | Service release thuộc release train tương thích |
| Java version | Maven compiler hoặc Gradle toolchain | Phiên bản JDK đáp ứng yêu cầu của Boot và Cloud |

Hãy kiểm tra tài liệu chính thức mỗi khi nâng cấp. Bảng tương thích thay đổi theo release train; một ví dụ version cũ trong bài hướng dẫn trên mạng không đảm bảo còn phù hợp với dự án hiện tại.

## 5. Import Spring Cloud BOM trong Maven

### 5.1. Khai báo property và import BOM

Nếu dự án dùng `spring-boot-starter-parent`, có thể đặt Spring Cloud version trong `properties` và import BOM trong `dependencyManagement`:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>BOOT_VERSION_COMPATIBLE</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>inventory-service</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>JAVA_VERSION</java.version>
        <spring-cloud.version>CLOUD_TRAIN_VERSION</spring-cloud.version>
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
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-loadbalancer</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Trong cấu hình trên:

- `spring-cloud.version` là nơi duy nhất lưu version của Spring Cloud BOM.
- `spring-cloud-dependencies` được import bằng `type` là `pom` và `scope` là `import`.
- Eureka Client và LoadBalancer không cần khai báo version riêng nếu BOM đang quản lý chúng.
- `spring-boot-starter-web` được Spring Boot parent quản lý.
- Các dependency được thêm vào ứng dụng vì chúng nằm trong phần `dependencies`, không phải vì BOM đã được import.

### 5.2. Nếu không dùng Spring Boot parent

Một số dự án dùng parent POM nội bộ hoặc parent khác. Trong trường hợp đó, vẫn có thể import Spring Boot BOM và Spring Cloud BOM trong `dependencyManagement`:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>BOOT_VERSION_COMPATIBLE</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>CLOUD_TRAIN_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Cách này giữ được parent POM hiện có mà vẫn quản lý version tập trung. Khi nhiều BOM cùng quản lý một artifact, cần kiểm tra effective POM để biết quy tắc cuối cùng. Quy tắc quản lý trực tiếp trong project có thể ghi đè version từ BOM; thứ tự import và cấu trúc parent cũng ảnh hưởng đến kết quả hòa giải. Không nên giải quyết xung đột bằng cách thêm version tùy ý mà chưa hiểu dependency nào đang cung cấp version đó.

## 6. Dùng BOM trong Gradle

Gradle có thể nhập Maven BOM thông qua dependency management plugin hoặc cơ chế platform gốc của Gradle. Chọn một cách nhất quán theo quy ước của dự án.

### 6.1. Dùng Spring dependency management plugin

Ví dụ với Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'BOOT_VERSION_COMPATIBLE'
    id 'io.spring.dependency-management' version 'DEPENDENCY_MANAGEMENT_PLUGIN_VERSION'
}

ext {
    set('springCloudVersion', 'CLOUD_TRAIN_VERSION')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-client'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

Plugin đọc BOM và áp dụng các version được quản lý cho dependency tương ứng. Khi đã được quản lý bởi BOM, dependency Spring Cloud không cần khai báo version ở từng dòng.

Ví dụ với Kotlin DSL, phần cấu hình tương đương có thể viết như sau:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "BOOT_VERSION_COMPATIBLE"
    id("io.spring.dependency-management") version "DEPENDENCY_MANAGEMENT_PLUGIN_VERSION"
}

val springCloudVersion = "CLOUD_TRAIN_VERSION"

dependencyManagement {
    imports {
        mavenBom(
            "org.springframework.cloud:spring-cloud-dependencies:$springCloudVersion"
        )
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-netflix-eureka-client")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
}
~~~

### 6.2. Dùng platform gốc của Gradle

Gradle hỗ trợ import BOM trực tiếp qua `platform()`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'BOOT_VERSION_COMPATIBLE'
}

ext {
    springCloudVersion = 'CLOUD_TRAIN_VERSION'
}

dependencies {
    implementation platform(
        "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-client'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

`platform()` đưa các dependency constraints trong BOM vào cấu hình dependency của Gradle. Những dependency được BOM quản lý có thể được khai báo mà không cần version riêng.

Gradle còn có `enforcedPlatform()`. Cơ chế này áp dụng các version trong platform với mức ép buộc cao hơn và có thể tác động đến dependency bắc cầu của các thành phần khác. Chỉ dùng khi có lý do rõ ràng và đã đánh giá ảnh hưởng đến toàn bộ dependency graph. Với phần lớn ứng dụng, `platform()` là lựa chọn phù hợp hơn để bắt đầu.

Nếu dự án đã dùng Spring dependency management plugin để import BOM, không cần thêm một platform trùng lặp cho cùng BOM. Trộn nhiều cơ chế quản lý version mà không có chủ đích làm cho việc truy tìm version cuối cùng khó hơn.

## 7. Quản lý BOM trong dự án nhiều module

Một hệ thống microservice hoặc một repository nhiều module có thể có nhiều module cùng sử dụng Spring Cloud. Nếu mỗi module tự chọn BOM version, các service có thể build thành công riêng nhưng lại dùng những bộ thư viện khác nhau.

Với Maven multi-module:

- Đặt property `spring-cloud.version` ở parent POM chung.
- Import Spring Cloud BOM trong `dependencyManagement` của parent.
- Khai báo dependency thực tế trong module cần sử dụng.
- Module con kế thừa quản lý version từ parent, không import lại một BOM version khác.
- Nếu một module thực sự cần release train khác, cần tách rõ ranh giới quản lý và kiểm tra tương thích độc lập.

Ví dụ parent quản lý BOM:

~~~xml
<properties>
    <spring-cloud.version>CLOUD_TRAIN_VERSION</spring-cloud.version>
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
~~~

Module con chỉ khai báo dependency cần thiết:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-consul-discovery</artifactId>
    </dependency>
</dependencies>
~~~

Với Gradle multi-project, có thể khai báo platform ở root convention plugin hoặc cấu hình chung cho các subproject cần Spring Cloud. Không nên áp dụng mọi starter vào tất cả module nếu module đó không sử dụng. Mỗi service chỉ nên mang dependency cần thiết cho vai trò của nó.

## 8. Version override và dependency bắc cầu

BOM quản lý version mặc định cho artifact thuộc phạm vi của nó. Tuy nhiên, dự án vẫn có thể ghi version trực tiếp hoặc thêm một quy tắc dependency management khác. Khi đó, version được resolve có thể khác version trong BOM.

Một số nguyên tắc:

- Không khai báo version riêng cho Spring Cloud starter nếu không có lý do cụ thể.
- Tránh override riêng Spring Framework, Spring Cloud Commons hoặc thư viện nền tảng chỉ để xử lý một lỗi chưa được xác định.
- Nếu cần dùng bản vá đặc biệt, hãy kiểm tra release note, dependency tree và hướng dẫn override của Spring.
- Ghi lại lý do override, phạm vi ảnh hưởng và điều kiện để gỡ override.
- Kiểm tra lại toàn bộ dependency graph sau mỗi lần nâng cấp BOM.

Ví dụ khai báo version trực tiếp có thể làm thay đổi version được chọn:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    <version>ANOTHER_VERSION</version>
</dependency>
~~~

Cấu hình như trên bỏ qua version được quản lý của BOM cho dependency trực tiếp đó. Chỉ làm vậy khi đã xác nhận phiên bản thay thế tương thích với release train và các dependency liên quan.

Cần phân biệt hai tình huống:

1. **BOM không quản lý artifact:** dependency cần khai báo version theo hướng dẫn của thư viện đó.
2. **BOM có quản lý artifact nhưng version bị ghi đè:** tìm nơi khai báo version trực tiếp, parent POM, platform khác hoặc quy tắc resolution đang tác động.

Không phải mọi dependency bắc cầu đều có version trong Spring Cloud BOM. Một số thư viện được quản lý bởi Spring Boot BOM hoặc BOM của bên thứ ba. Khi xử lý xung đột, hãy xác định nguồn quản lý version của từng artifact thay vì mặc định mọi version đều đến từ Spring Cloud BOM.

## 9. Kiểm tra version đã được resolve

Sau khi import BOM, cần kiểm tra version thực tế mà Maven hoặc Gradle chọn. Cấu hình nhìn có vẻ đúng chưa đủ chứng minh dependency graph không có xung đột.

### Maven

Xem dependency tree:

~~~bash
mvn dependency:tree
~~~

Lọc theo nhóm Spring Cloud:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.cloud
~~~

Xem POM sau khi Maven áp dụng parent, property và dependency management:

~~~bash
mvn help:effective-pom
~~~

Có thể ghi kết quả effective POM ra file để đối chiếu khi nâng cấp. Khi cần điều tra một dependency cụ thể, dùng `dependency:tree` với `includes` phù hợp và xem dependency nào đưa artifact đó vào graph.

### Gradle

Xem dependency graph của runtime classpath:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Kiểm tra lý do một version cụ thể được chọn:

~~~bash
./gradlew dependencyInsight \
    --dependency spring-cloud-commons \
    --configuration runtimeClasspath
~~~

Trên Windows có thể dùng `gradlew.bat` thay cho `./gradlew`.

Sau khi xác nhận version, tiếp tục:

- Build module để phát hiện lỗi compile hoặc dependency resolution.
- Chạy test khởi động Spring context để phát hiện lỗi tạo bean.
- Kiểm tra ứng dụng có kết nối được Eureka hoặc Consul trong môi trường kiểm thử hay không.
- Thử luồng gọi service theo tên nếu ứng dụng có dùng LoadBalancer.
- Kiểm tra log để tìm cảnh báo về version, classpath hoặc cấu hình không tương thích.

## 10. Lỗi thường gặp khi sử dụng Spring Cloud BOM

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Maven báo thiếu version cho dependency | BOM chưa được import đúng hoặc artifact không thuộc BOM | Kiểm tra `dependencyManagement`, `type`, `scope` và artifact |
| Gradle không resolve được version | BOM chưa được import vào configuration phù hợp | Kiểm tra plugin hoặc `platform()` |
| `NoSuchMethodError` khi chạy | Các thư viện liên quan bị lệch version | Kiểm tra dependency tree và release train |
| Ứng dụng không khởi tạo được bean | Spring Boot và Spring Cloud không tương thích hoặc thiếu starter | Đối chiếu ma trận tương thích, kiểm tra classpath |
| Một module dùng version khác module còn lại | BOM được khai báo phân tán hoặc có override | Đưa version về cấu hình chung và rà soát module |
| Version thực tế không như mong đợi | Parent, BOM khác, dependency trực tiếp hoặc resolution rule ghi đè | Xem effective POM hoặc dependencyInsight |
| Nâng BOM làm phát sinh lỗi cấu hình | Release train mới có thay đổi hoặc loại bỏ API | Đọc release notes và nâng cấp theo từng bước |

Một lỗi dependency không nên được xử lý bằng cách thêm version ngẫu nhiên cho đến khi build thành công. Cần xác định thư viện nào được resolve, ai quản lý version đó và vì sao version được chọn không tương thích.

## 11. Quy trình nâng cấp Spring Cloud BOM

Nâng BOM có thể kéo theo thay đổi ở nhiều thành phần cùng lúc. Nên thực hiện có kiểm soát:

1. Ghi nhận Spring Boot version, Spring Cloud train và Java version hiện tại.
2. Tra release train tương thích với phiên bản Spring Boot đích.
3. Đọc release notes của Spring Cloud và các thành phần mà service đang dùng.
4. Chỉ thay đổi property hoặc platform version tại một điểm quản lý chung.
5. Resolve lại dependency graph và kiểm tra các version quan trọng.
6. Chạy build, unit test, integration test và kiểm thử khởi động ứng dụng.
7. Kiểm thử đăng ký, discovery và gọi service nếu service có sử dụng các chức năng đó.
8. Theo dõi log và metric sau khi triển khai; giữ lại version cũ để có thể rollback theo quy trình phát hành của tổ chức.

Nếu nâng cả Spring Boot và Spring Cloud, hãy chọn một cặp version tương thích rồi nâng cấp có kiểm soát. Khi có lỗi, so sánh dependency graph trước và sau nâng cấp để khoanh vùng nguyên nhân.

## 12. Ghi nhớ

- Spring Cloud BOM là bộ quản lý version cho các dependency thuộc một Spring Cloud release train.
- Import BOM chỉ cung cấp quy tắc dependency management; nó không tự thêm starter vào ứng dụng.
- Spring Boot BOM và Spring Cloud BOM có phạm vi quản lý khác nhau, thường được sử dụng cùng nhau.
- Chọn Spring Cloud train theo ma trận tương thích với Spring Boot và Java của dự án.
- Maven import BOM qua `dependencyManagement` với `type=pom` và `scope=import`; Gradle có thể dùng dependency management plugin hoặc `platform()`.
- Quản lý BOM ở một điểm chung giúp các module giữ cùng bộ phiên bản.
- Sau khi thay đổi BOM, kiểm tra dependency tree, build, test và luồng service discovery trước khi triển khai.

Khi quản lý phiên bản bằng Spring Cloud BOM, dự án có một nền tảng dependency nhất quán để phát triển DiscoveryClient, ServiceRegistry, Eureka, Consul và LoadBalancer. Việc chọn đúng release train và kiểm tra version đã resolve là hai bước quan trọng để tránh xung đột khi vận hành microservice.
