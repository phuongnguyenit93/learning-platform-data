# Khai báo dependency bằng Gradle hoặc Maven

Spring Data Relational R2DBC cần hai nhóm thư viện để ứng dụng truy cập cơ sở dữ liệu quan hệ theo kiểu reactive: các thành phần Spring cung cấp repository và transaction abstraction, cùng driver R2DBC dành cho hệ quản trị cơ sở dữ liệu cụ thể. Khi dùng Spring Boot, dependency starter giúp đưa các thành phần Spring tương thích vào ứng dụng; driver vẫn phải được chọn theo database mà ứng dụng kết nối.

Bài học này trình bày cách khai báo các dependency đó bằng Gradle và Maven, cách quản lý phiên bản, cách chọn scope phù hợp và cách kiểm tra dependency đã được giải quyết đúng hay chưa.

## 1. Hiểu các dependency cần có

Trước khi sửa file build, hãy phân biệt vai trò của từng nhóm thư viện.

### 1.1. Spring Data R2DBC và Spring Boot starter

Spring Data R2DBC cung cấp khả năng ánh xạ dữ liệu quan hệ theo mô hình repository reactive. Ứng dụng có thể khai báo repository trả về `Mono`, `Flux`, dùng `R2dbcEntityTemplate` hoặc `DatabaseClient`, và tích hợp giao dịch reactive.

Với ứng dụng Spring Boot, dependency thường dùng là:

~~~text
org.springframework.boot:spring-boot-starter-data-r2dbc
~~~

Starter này tập hợp các thư viện Spring cần thiết cho Spring Data R2DBC và tích hợp tự động cấu hình của Spring Boot. Nhờ starter, ứng dụng không phải tự khai báo riêng từng thư viện nền tảng như Spring Data R2DBC, Spring R2DBC và các thành phần reactive mà chúng cần.

Starter không đại diện cho một hệ quản trị cơ sở dữ liệu cụ thể. Ứng dụng vẫn cần thêm driver R2DBC tương ứng với PostgreSQL, MySQL, H2 hoặc hệ quản trị khác.

Không cần khai báo thêm `spring-data-r2dbc` riêng khi starter đã cung cấp module đó. Việc khai báo trùng lặp có thể khiến người đọc khó biết dependency nào đang quyết định phiên bản thực tế.

### 1.2. Driver R2DBC của database

Driver chuyển các thao tác từ R2DBC SPI thành giao thức mà hệ quản trị cơ sở dữ liệu hiểu được. Chọn driver theo database và phiên bản tương thích với hệ thống triển khai.

Một số tọa độ dependency thường gặp:

| Hệ quản trị | Dependency driver R2DBC |
|---|---|
| PostgreSQL | `org.postgresql:r2dbc-postgresql` |
| MySQL | `io.asyncer:r2dbc-mysql` |
| H2 | `io.r2dbc:r2dbc-h2` |
| Microsoft SQL Server | `io.r2dbc:r2dbc-mssql` |
| Oracle Database | `com.oracle.database.r2dbc:oracle-r2dbc` |
| MariaDB | `org.mariadb:r2dbc-mariadb` |

Tên artifact và khả năng tương thích có thể thay đổi theo dòng phiên bản của driver. Hãy đối chiếu tài liệu của driver với phiên bản database và Spring Boot đang sử dụng trước khi chọn phiên bản.

Với ứng dụng chỉ sử dụng driver thông qua cấu hình kết nối, driver thường được khai báo ở runtime scope. Nếu mã nguồn trực tiếp tham chiếu lớp hoặc API riêng của driver, dependency có thể cần ở compile scope.

### 1.3. R2DBC driver khác JDBC driver

R2DBC và JDBC là hai API truy cập cơ sở dữ liệu khác nhau. Driver JDBC của PostgreSQL có tọa độ:

~~~text
org.postgresql:postgresql
~~~

Driver R2DBC của PostgreSQL có tọa độ:

~~~text
org.postgresql:r2dbc-postgresql
~~~

Thêm JDBC driver không làm cho Spring Data R2DBC kết nối được tới database. Với ứng dụng dùng R2DBC, phải khai báo driver R2DBC và cấu hình URL có scheme `r2dbc:`.

Một ứng dụng có thể dùng cả JDBC và R2DBC nếu có nhu cầu rõ ràng, nhưng khi đó cần hiểu rằng chúng có các connection factory/data source, transaction manager và cơ chế truy cập riêng. Thêm `spring-boot-starter-jdbc` không thay thế `spring-boot-starter-data-r2dbc`.

## 2. Quản lý phiên bản dependency

Các thư viện trong hệ sinh thái Spring phụ thuộc lẫn nhau. Spring Boot, Spring Framework, Spring Data, Reactor, R2DBC SPI và driver phải tương thích về phiên bản.

Spring Boot cung cấp BOM (Bill of Materials) để quản lý các phiên bản thư viện đã được kiểm tra cùng nhau. Khi dùng dependency management của Spring Boot, thông thường chỉ khai báo group, artifact và scope; không tự đặt version cho từng dependency do BOM quản lý.

Ví dụ, nên để BOM quản lý phiên bản của starter và driver:

~~~text
org.springframework.boot:spring-boot-starter-data-r2dbc
org.postgresql:r2dbc-postgresql
~~~

Không nên tùy tiện kết hợp một phiên bản `spring-data-r2dbc` mới với một phiên bản Spring Framework cũ, hoặc nâng riêng `r2dbc-spi` mà không kiểm tra driver. Việc ép một dependency về phiên bản khác với BOM có thể gây lỗi biên dịch, `NoSuchMethodError`, `ClassNotFoundException` hoặc lỗi khởi tạo connection factory khi chạy.

Nếu dự án chưa dùng Spring Boot, hãy quản lý phiên bản theo BOM và bảng tương thích của Spring Data/Spring Framework, đồng thời kiểm tra yêu cầu của driver R2DBC. Tránh sao chép các version rời rạc từ nhiều ví dụ không cùng dòng phát hành.

## 3. Khai báo bằng Gradle

Gradle hỗ trợ Groovy DSL trong file `build.gradle` và Kotlin DSL trong file `build.gradle.kts`. Cách viết khác nhau nhưng ý nghĩa dependency configuration tương đương.

### 3.1. Gradle với Groovy DSL

Một ứng dụng Spring Boot dùng PostgreSQL có thể khai báo như sau:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'io.spring.dependency-management' version '<dependency-management-plugin-version>'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Thay các placeholder version bằng phiên bản Spring Boot và plugin tương thích với dự án. Khi Spring Boot Gradle plugin được cấu hình cùng dependency management plugin, BOM của Spring Boot có thể quản lý các phiên bản thư viện. Vì vậy, dependency starter và driver trong ví dụ không cần khai báo version riêng.

Ý nghĩa các cấu hình:

- `implementation`: dependency có mặt trên compile classpath và runtime classpath của module.
- `runtimeOnly`: dependency cần khi chạy ứng dụng nhưng mã nguồn không cần tham chiếu trực tiếp khi biên dịch.
- `testImplementation`: dependency chỉ phục vụ biên dịch và chạy test.
- `repositories`: nơi Gradle tìm và tải artifact; `mavenCentral()` là repository công khai thường dùng.
- `java.toolchain`: chọn phiên bản JDK dùng để biên dịch và chạy các task Java của Gradle.

Spring Data R2DBC được truy cập qua starter ở `implementation`. Driver PostgreSQL được dùng khi tạo kết nối ở runtime nên thường đặt ở `runtimeOnly`.

Nếu ứng dụng tham chiếu trực tiếp các lớp của driver, chẳng hạn cấu hình riêng một tùy chọn đặc thù của driver bằng API Java, hãy cân nhắc chuyển driver sang `implementation`. Chỉ làm vậy khi mã nguồn thực sự cần API đó.

### 3.2. Gradle với Kotlin DSL

Nếu dự án dùng `build.gradle.kts`, cách khai báo tương ứng là:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "<spring-boot-version>"
    id("io.spring.dependency-management") version "<dependency-management-plugin-version>"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
}
~~~

Kotlin DSL dùng lời gọi hàm và dấu ngoặc thay cho cú pháp chuỗi của Groovy. Không trộn cú pháp hai DSL trong cùng một file build.

### 3.3. Dùng BOM trực tiếp trong Gradle

Một dự án có thể muốn dùng BOM của Spring Boot nhưng không dùng dependency management plugin. Gradle hỗ trợ native platform dependency:

~~~kotlin
dependencies {
    implementation(platform(
        "org.springframework.boot:spring-boot-dependencies:<spring-boot-version>"
    ))

    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
~~~

`platform(...)` đưa các ràng buộc phiên bản trong BOM vào cấu hình dependency. Khi dùng cách này, cần bảo đảm BOM được áp dụng cho đúng configuration/module và không đồng thời tạo ra các quy tắc version mâu thuẫn.

Nếu dự án dùng plugin Spring Boot để đóng gói executable jar hoặc quản lý task Boot, có thể tiếp tục dùng plugin đó. Plugin đóng gói và cách quản lý phiên bản dependency là hai trách nhiệm có liên quan nhưng không đồng nhất.

### 3.4. Dùng version catalog trong dự án nhiều module

Gradle version catalog cho phép đặt tên dependency và plugin ở một nơi, thường trong file `gradle/libs.versions.toml`. Cách này giúp các module dùng cùng tọa độ dependency và giảm việc lặp lại chuỗi khai báo.

Ví dụ catalog:

~~~toml
[versions]
spring-boot = "<spring-boot-version>"

[libraries]
spring-boot-starter-data-r2dbc = {
    module = "org.springframework.boot:spring-boot-starter-data-r2dbc"
}
postgresql-r2dbc = {
    module = "org.postgresql:r2dbc-postgresql"
}
~~~

Trong module:

~~~kotlin
dependencies {
    implementation(libs.spring.boot.starter.data.r2dbc)
    runtimeOnly(libs.postgresql.r2dbc)
}
~~~

Version catalog quản lý tên và tọa độ dependency; nó không thay thế BOM. Nếu BOM đã quản lý version, không cần gắn một version độc lập vào từng library alias. Hãy chọn một cách quản lý phiên bản thống nhất cho toàn bộ dự án.

## 4. Khai báo bằng Maven

Maven khai báo dependency trong phần `dependencies` của `pom.xml`. Có hai cách phổ biến để dùng dependency management của Spring Boot: kế thừa `spring-boot-starter-parent` hoặc import BOM trong `dependencyManagement`.

### 4.1. Kế thừa Spring Boot parent

Nếu dự án có thể dùng Spring Boot parent, khai báo parent và dependency như sau:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>REPLACE_WITH_SPRING_BOOT_VERSION</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>r2dbc-sample</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-r2dbc</artifactId>
        </dependency>

        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>r2dbc-postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Thay `REPLACE_WITH_SPRING_BOOT_VERSION` bằng phiên bản Spring Boot mà dự án chọn. Parent quản lý nhiều dependency version, vì vậy các dependency nằm trong BOM thường không cần khai báo thẻ `<version>`.

Các Maven scope tương ứng với ví dụ Gradle:

| Maven scope | Vai trò |
|---|---|
| `compile` (mặc định) | Có trên compile classpath và runtime classpath; dùng cho starter |
| `runtime` | Cần khi chạy ứng dụng nhưng không cần để biên dịch mã nguồn; phù hợp với driver nếu không tham chiếu API của driver |
| `test` | Chỉ dùng trong test compile và test runtime |
| `provided` | Môi trường chạy cung cấp dependency; thường không phải lựa chọn cho driver R2DBC của ứng dụng độc lập |

Không nên bỏ `<scope>runtime</scope>` chỉ vì driver không có import trong mã Java; scope runtime diễn đạt đúng vai trò của driver trong trường hợp này.

### 4.2. Import Spring Boot BOM khi không dùng parent

Một dự án có thể đã kế thừa parent POM khác hoặc có quy ước quản lý parent riêng. Khi đó, import BOM của Spring Boot trong `dependencyManagement`:

~~~xml
<properties>
    <spring-boot.version>REPLACE_WITH_SPRING_BOOT_VERSION</spring-boot.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-r2dbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>r2dbc-postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Trong `pom.xml` thực tế, biểu thức version của property phải là `${spring-boot.version}`. Ví dụ trên dùng property để chỉ cần đổi một chỗ khi nâng Spring Boot.

Import BOM chỉ đưa quy tắc quản lý dependency vào dự án. Nếu cần đóng gói ứng dụng thành executable jar, hãy cấu hình `spring-boot-maven-plugin` phù hợp với cách build của dự án. BOM không tự thay thế chức năng đóng gói của Maven plugin.

### 4.3. Quản lý dependency trong Maven nhiều module

Trong dự án nhiều module, có thể đặt BOM và các quy tắc dependency chung tại parent POM. Các module con kế thừa `dependencyManagement` và chỉ khai báo dependency thực sự sử dụng trong phần `dependencies`.

Cần phân biệt:

- `dependencyManagement` quy định version và metadata mặc định cho dependency khi module con khai báo nó.
- `dependencies` thực sự đưa dependency vào module hiện tại và classpath tương ứng.
- Khai báo một dependency trong `dependencyManagement` không có nghĩa mọi module con tự động sử dụng dependency đó.

Ví dụ, module truy cập PostgreSQL có thể khai báo starter và driver; module chỉ chứa DTO hoặc domain model không cần nhận driver R2DBC.

## 5. Chọn driver và scope theo môi trường

### 5.1. Ứng dụng kết nối PostgreSQL

Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-r2dbc</artifactId>
</dependency>
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>r2dbc-postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

### 5.2. Ứng dụng kết nối MySQL

Thay driver PostgreSQL bằng driver MySQL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("io.asyncer:r2dbc-mysql")
}
~~~

Không giữ đồng thời nhiều driver chỉ để “phòng khi cần”. Chỉ thêm driver cho các database mà ứng dụng thực sự hỗ trợ. Nếu có nhiều database, hãy cấu hình rõ connection factory tương ứng và kiểm tra cách tự động cấu hình hoạt động trong ứng dụng.

### 5.3. Dùng H2 cho môi trường thử nghiệm

H2 có driver R2DBC riêng:

~~~kotlin
dependencies {
    runtimeOnly("io.r2dbc:r2dbc-h2")
}
~~~

Có thể dùng H2 để kiểm thử một số luồng truy cập dữ liệu nhanh. Tuy nhiên, H2 không thay thế hoàn toàn PostgreSQL, MySQL hoặc database production. Cú pháp SQL, kiểu dữ liệu, isolation, khóa và hành vi driver có thể khác nhau. Các kiểm thử cần xác nhận hành vi concurrency nên chạy trên đúng hệ quản trị mục tiêu, chẳng hạn bằng Testcontainers.

Nếu cấu hình driver H2 chỉ dành cho test, hãy đặt dependency ở `testRuntimeOnly` thay vì `runtimeOnly` để tránh đóng gói nó vào runtime production.

## 6. Kết nối dependency với cấu hình ứng dụng

Sau khi thêm starter và driver, ứng dụng Spring Boot có thể cấu hình kết nối bằng các thuộc tính R2DBC. Ví dụ với PostgreSQL:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/appdb
    username: app_user
    password: ${DB_PASSWORD}
~~~

URL bắt đầu bằng `r2dbc:postgresql:` để driver PostgreSQL R2DBC nhận diện giao thức. Driver phải có trên runtime classpath để Spring Boot có thể tạo connection factory phù hợp.

Với MySQL, URL có scheme tương ứng, ví dụ `r2dbc:mysql://localhost:3306/appdb`. Scheme và các tùy chọn cụ thể phải theo tài liệu driver.

Không nhầm các thuộc tính sau:

| R2DBC | JDBC |
|---|---|
| `spring.r2dbc.url` | `spring.datasource.url` |
| `spring.r2dbc.username` | `spring.datasource.username` |
| `spring.r2dbc.password` | `spring.datasource.password` |
| URL có scheme `r2dbc:` | URL có scheme `jdbc:` |

Nếu chỉ cấu hình `spring.datasource.*` và chỉ thêm JDBC driver, Spring Boot sẽ cấu hình theo JDBC khi có các dependency phù hợp; điều đó không tạo kết nối R2DBC.

Không nhất thiết phải khai báo `driver-class-name` như cách làm JDBC truyền thống. Driver R2DBC thường được tìm qua cơ chế SPI và scheme trong URL. Chỉ thêm cấu hình riêng khi tài liệu driver hoặc cấu hình đa database yêu cầu.

Thông tin mật khẩu không nên commit vào file cấu hình được chia sẻ. Dùng biến môi trường, secret manager hoặc cơ chế cấu hình bảo mật của môi trường triển khai.

## 7. Khi nào không dùng Spring Boot starter?

Một ứng dụng Spring Framework hoặc thư viện độc lập có thể khai báo Spring Data R2DBC trực tiếp thay vì dùng Spring Boot starter. Khi đó, nhóm dependency thường bao gồm:

- `org.springframework.data:spring-data-r2dbc` cho repository và ánh xạ dữ liệu.
- Spring R2DBC cho tích hợp connection và thao tác R2DBC.
- R2DBC SPI và driver của database.
- Reactor Core cho kiểu publisher reactive được Spring Data sử dụng.
- Các thành phần Spring Framework cần thiết cho context, cấu hình và quản lý transaction.

Nhiều dependency nền tảng được kéo vào theo quan hệ transitive từ Spring Data R2DBC. Không nên thêm từng artifact theo một danh sách tùy ý rồi chọn version độc lập. Hãy dùng BOM tương thích của Spring Data và căn chỉnh với phiên bản Spring Framework cùng driver.

Khi dùng Spring Boot, starter là lựa chọn đơn giản và dễ bảo trì hơn cho ứng dụng thông thường. Chỉ khai báo thủ công khi có lý do kiến trúc cụ thể, chẳng hạn tích hợp vào ứng dụng Spring Framework không dùng Boot hoặc xây dựng một thư viện có phạm vi dependency được kiểm soát riêng.

## 8. Dependency dành cho kiểm thử

Ứng dụng R2DBC thường cần kiểm thử publisher và tương tác database.

Một số dependency hữu ích:

| Dependency | Mục đích |
|---|---|
| `spring-boot-starter-test` | JUnit, Spring Test, AssertJ và các thư viện kiểm thử phổ biến |
| `io.projectreactor:reactor-test` | `StepVerifier` và công cụ kiểm thử Reactor publisher |
| Driver R2DBC của database kiểm thử | Kết nối database trong integration test |
| Testcontainers cho database mục tiêu | Khởi chạy database cô lập gần với môi trường production |

Gradle:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
    testRuntimeOnly("io.r2dbc:r2dbc-h2")
}
~~~

Đoạn này minh họa trường hợp test dùng H2; nếu integration test dùng PostgreSQL trong Testcontainers, cần khai báo module Testcontainers phù hợp và driver R2DBC PostgreSQL trong test runtime hoặc runtime classpath theo cách test khởi chạy ứng dụng.

Không đưa thư viện chỉ dùng để test vào `implementation` hoặc dependency production nếu không có nhu cầu chạy thực tế.

## 9. Kiểm tra dependency đã được giải quyết

Khai báo trong file build mới chỉ là bước đầu. Cần xác nhận Gradle hoặc Maven đã tải đúng artifact và chọn phiên bản tương thích.

### 9.1. Kiểm tra bằng Gradle

Xem toàn bộ runtime dependency:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Trên Windows có thể dùng wrapper `gradlew.bat`:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

Tìm dependency cụ thể và lý do Gradle chọn phiên bản:

~~~bash
./gradlew dependencyInsight --dependency r2dbc-postgresql --configuration runtimeClasspath
~~~

`dependencyInsight` hữu ích khi nhiều thư viện yêu cầu các version khác nhau. Kết quả cho biết dependency nào kéo artifact vào và quy tắc nào khiến Gradle chọn version cuối cùng.

### 9.2. Kiểm tra bằng Maven

Xem cây dependency:

~~~bash
./mvnw dependency:tree
~~~

Có thể giới hạn theo nhóm artifact để kết quả dễ đọc hơn:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.boot,org.springframework.data,io.r2dbc,org.postgresql
~~~

Trên Windows dùng `mvnw.cmd` nếu dự án cung cấp Maven Wrapper.

Kiểm tra cây dependency giúp phát hiện trường hợp starter bị khai báo trùng, JDBC driver được thêm nhầm, hoặc một thư viện transitively kéo vào phiên bản khác dự kiến.

### 9.3. Kiểm tra runtime

Sau khi dependency được giải quyết:

1. Xác nhận driver R2DBC có trong runtime classpath.
2. Kiểm tra scheme URL khớp với driver.
3. Khởi động ứng dụng và xem lỗi tạo connection factory hoặc kết nối database.
4. Chạy một truy vấn repository đơn giản để xác nhận driver, credentials và database hoạt động.
5. Với integration test, xác nhận test thực sự dùng database dự kiến thay vì vô tình kết nối vào database local khác.

Lỗi `Failed to determine a suitable R2DBC Connection URL` thường liên quan đến thiếu hoặc sai thuộc tính URL. Lỗi không tìm thấy provider/driver thường liên quan đến thiếu driver trên classpath hoặc scheme không được driver hỗ trợ. Lỗi xác thực hay kết nối mạng cần kiểm tra credentials, hostname, port, database và quyền truy cập.

## 10. Những lỗi khai báo dependency thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chỉ thêm `spring-boot-starter-data-r2dbc` nhưng không thêm driver | Starter không chọn database driver cụ thể | Thêm driver R2DBC của hệ quản trị đang dùng |
| Thêm JDBC driver thay cho R2DBC driver | Hai driver triển khai hai API khác nhau | Dùng artifact R2DBC tương ứng |
| Khai báo `spring-data-r2dbc` riêng bên cạnh Boot starter | Trùng module và có nguy cơ lệch version | Dùng starter hoặc tự quản lý toàn bộ stack, tránh khai báo chồng |
| Tự đặt version cho từng thư viện Spring | Các module có thể không tương thích | Dùng Spring Boot BOM hoặc BOM tương ứng |
| Đặt driver ở test scope nhưng ứng dụng cần chạy production | Driver vắng mặt trên runtime production | Dùng `runtimeOnly` của Gradle hoặc Maven `runtime` |
| Đặt dependency test ở compile/runtime production | Tăng dependency không cần thiết | Chuyển sang `testImplementation` hoặc Maven `test` |
| Cấu hình `spring.datasource.url` cho ứng dụng chỉ dùng R2DBC | Thuộc tính thuộc cấu hình JDBC | Dùng `spring.r2dbc.url` với scheme `r2dbc:` |
| Thêm nhiều driver không cần thiết | Classpath phức tạp, khó xác định cấu hình tự động | Chỉ khai báo driver được ứng dụng hỗ trợ |
| Kiểm thử bằng H2 rồi suy luận hành vi production | Khác biệt giữa database và driver | Kiểm thử tích hợp trên database mục tiêu |
| Dùng version catalog như thể nó tự quản lý BOM | Catalog chủ yếu đặt tên và tọa độ dependency | Kết hợp version catalog với BOM hoặc quy tắc version rõ ràng |

## 11. Quy trình khai báo dependency cho dự án mới

Khi bắt đầu một ứng dụng Spring Data R2DBC, có thể thực hiện theo trình tự:

1. Xác định hệ quản trị cơ sở dữ liệu và driver R2DBC được hỗ trợ.
2. Xác định phiên bản Spring Boot mà dự án sử dụng, hoặc phiên bản Spring Data/Spring Framework nếu không dùng Boot.
3. Chọn một cơ chế quản lý phiên bản thống nhất, ưu tiên BOM của Spring Boot cho ứng dụng Boot.
4. Thêm `spring-boot-starter-data-r2dbc` vào compile dependency.
5. Thêm driver R2DBC của database vào runtime dependency.
6. Thêm thư viện test vào test dependency, và driver test riêng nếu cần.
7. Cấu hình URL, username và password bằng thuộc tính `spring.r2dbc.*`.
8. Kiểm tra runtime dependency tree và khởi động ứng dụng để xác nhận driver được nạp.
9. Viết integration test trên database tương thích với môi trường triển khai.

## 12. Ghi nhớ

- Ứng dụng Spring Boot dùng Spring Data R2DBC thường bắt đầu với `spring-boot-starter-data-r2dbc`.
- Starter cung cấp tích hợp Spring Data và reactive; driver R2DBC của database phải được khai báo riêng.
- PostgreSQL JDBC driver và PostgreSQL R2DBC driver là hai artifact khác nhau.
- Dùng BOM của Spring Boot để đồng bộ version; tránh nâng riêng Spring Data, Spring Framework, Reactor hoặc R2DBC SPI khi chưa kiểm tra tương thích.
- Trong Gradle, starter thường là `implementation`, driver là `runtimeOnly`, thư viện test là `testImplementation`.
- Trong Maven, starter mặc định ở compile scope, driver thường ở `runtime`, thư viện test ở `test`.
- URL kết nối R2DBC dùng scheme `r2dbc:` và cấu hình Spring Boot nằm dưới `spring.r2dbc`.
- Kiểm tra dependency tree và chạy integration test giúp phát hiện lỗi thiếu driver, lệch version và nhầm JDBC/R2DBC trước khi triển khai.

