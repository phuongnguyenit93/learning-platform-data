# Dependency management trong Gradle hoặc Maven

Một ứng dụng Spring Boot hiếm khi chỉ dùng những lớp có sẵn trong Java. Để xây REST API, kết nối cơ sở dữ liệu, xử lý JSON, logging hoặc kiểm thử, dự án cần nhiều thư viện. Mỗi thư viện lại có thể cần những thư viện khác. Khi thêm một dependency, bạn đang đưa vào ứng dụng cả một **đồ thị phụ thuộc** mà không phải tất cả các thành phần đều được khai báo trực tiếp.

**Dependency management** là quá trình khai báo, lựa chọn phiên bản, giải quyết xung đột và kiểm soát các thư viện mà dự án cần ở từng giai đoạn biên dịch, chạy và kiểm thử. **Maven** và **Gradle** là hai công cụ xây dựng ứng dụng Java phổ biến. Spring Boot bổ sung các **starter** và một tập phiên bản thư viện được quản lý để giảm công sức lắp ghép thủ công.

Bài học giải thích cách khai báo dependency, vai trò của BOM, cách Spring Boot hỗ trợ cả Maven lẫn Gradle và cách kiểm tra phiên bản thực sự được sử dụng.

## 1. Dependency, repository, plugin và build tool khác nhau thế nào?

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| Dependency | Thư viện cung cấp API hoặc chức năng ứng dụng cần | `spring-boot-starter-web`, PostgreSQL JDBC driver |
| Repository | Nơi công cụ build tìm và tải artifact | Maven Central, artifact repository nội bộ |
| Build plugin | Mở rộng quá trình build, chạy và đóng gói | `spring-boot-maven-plugin`, Gradle plugin `org.springframework.boot` |
| Build tool | Đọc mô tả dự án, resolve dependency và thực hiện tác vụ build | Maven, Gradle |

Cần phân biệt rõ: khai báo repository không tự thêm thư viện; khai báo plugin Spring Boot không đồng nghĩa ứng dụng đã có Spring MVC. Một plugin điều khiển **quá trình build**, còn một dependency cung cấp mã và tài nguyên mà ứng dụng hoặc test sử dụng.

Maven thường sử dụng file `pom.xml`. Gradle thường sử dụng `build.gradle` (Groovy DSL) hoặc `build.gradle.kts` (Kotlin DSL). Cả hai có thể tải artifact, tính đồ thị phụ thuộc và biên dịch ứng dụng, nhưng khác nhau về cú pháp và một số quy tắc giải quyết phiên bản.

## 2. Một dependency được nhận diện ra sao?

Artifact trong hệ sinh thái Maven thường có tọa độ:

~~~text
groupId : artifactId : version
~~~

Ví dụ:

~~~text
org.springframework.boot : spring-boot-starter-web : 3.3.5
~~~

`groupId` định danh nhóm phát hành, `artifactId` định danh artifact và `version` chọn phiên bản cụ thể. Một artifact có thể có thêm packaging hoặc classifier trong những trường hợp đặc biệt, nhưng ba thành phần trên đủ cho bài học nhập môn.

Maven khai báo trực tiếp:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <version>3.3.5</version>
</dependency>
~~~

Gradle Groovy DSL tương ứng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web:3.3.5'
}
~~~

Hai ví dụ trên **ghi rõ version**. Trong dự án Spring Boot, chúng ta thường quản lý phiên bản ở một vị trí chung để các dependency được phối hợp nhất quán. Vì thế về sau bạn sẽ thấy nhiều khai báo không có `version`.

### 2.1. Direct và transitive dependency

**Direct dependency** là thư viện dự án khai báo trực tiếp trong file build. **Transitive dependency** là thư viện mà một dependency khác cần và được đưa vào thông qua metadata.

Chẳng hạn, dự án khai báo web starter:

~~~mermaid
flowchart TD
    A["Ứng dụng"] --> B["spring-boot-starter-web"]
    B --> C["Spring MVC"]
    B --> D["JSON support"]
    B --> E["Embedded servlet container"]
    D --> F["Các thư viện Jackson"]
    E --> G["Các thư viện Tomcat"]
~~~

Tên artifact cụ thể và những cạnh trong đồ thị thay đổi theo phiên bản Boot; sơ đồ diễn tả vai trò của các nhóm thành phần.

Một thư viện có thể xuất hiện qua nhiều nhánh:

~~~text
Ứng dụng
   ├── library-A ───► common-lib:1.0
   └── library-B ───► common-lib:2.0
~~~

Khi đó build tool phải chọn phiên bản `common-lib` cuối cùng trên classpath dựa vào các quy tắc giải quyết xung đột và dependency management có hiệu lực.

### 2.2. Classpath không chỉ có một loại

**Classpath** là tập class, thư viện và resource mà một tác vụ Java nhìn thấy. Một dự án thường có nhiều classpath:

- Classpath cho biên dịch mã chính.
- Classpath cho chạy ứng dụng.
- Classpath cho biên dịch và chạy test.
- Classpath riêng phục vụ annotation processor hoặc plugin build.

Ví dụ, JUnit cần cho kiểm thử nhưng thường không cần đóng gói cùng runtime production. JDBC driver có thể được khai báo chỉ cho runtime nếu mã nguồn không trực tiếp tham chiếu các lớp driver cụ thể.

Phân biệt scope hoặc configuration giúp dự án đưa đúng thư viện vào đúng giai đoạn.

## 3. Spring Boot starter và BOM giải quyết vấn đề gì?

Spring Boot cung cấp các **starter**: những dependency nhóm các thư viện thường dùng cho một khả năng, giúp bắt đầu nhanh hơn.

Ví dụ:

| Starter | Nhóm khả năng |
| --- | --- |
| `spring-boot-starter-web` | Ứng dụng web dựa trên Spring MVC |
| `spring-boot-starter-validation` | Jakarta Bean Validation |
| `spring-boot-starter-data-jpa` | Spring Data JPA |
| `spring-boot-starter-security` | Spring Security |
| `spring-boot-starter-test` | Công cụ kiểm thử thường dùng |
| `spring-boot-starter-actuator` | Endpoint và tích hợp hỗ trợ quan sát ứng dụng |

Starter giúp trả lời: **“Tôi cần những thư viện nào cho khả năng này?”**

Spring Boot còn cung cấp **BOM (Bill of Materials)** mang tọa độ:

~~~text
org.springframework.boot:spring-boot-dependencies:<boot-version>
~~~

BOM mô tả các phiên bản được quản lý cho nhiều artifact tương thích với một phiên bản Spring Boot. Nó giúp trả lời: **“Nếu dùng các thư viện này, tôi nên sử dụng phiên bản nào?”**

Ví dụ minh họa với Spring Boot `3.3.5`:

~~~text
org.springframework.boot:spring-boot-dependencies:3.3.5
~~~

Phiên bản này được dùng nhất quán trong bài để dễ hiểu cơ chế, không phải khuyến nghị phiên bản mới nhất cho mọi dự án. Khi tạo dự án thực tế, nên chọn bản Spring Boot đang được hỗ trợ và tương thích với JDK, plugin và các thư viện của hệ thống.

**BOM không tự thêm tất cả dependency vào dự án.** Nó cung cấp thông tin quản lý phiên bản cho các dependency được khai báo hoặc xuất hiện transitively theo quy tắc của build tool.

| Spring Boot starter | Spring Boot BOM |
| --- | --- |
| Thường là một dependency cần thêm vào dự án | Metadata quản lý các phiên bản |
| Kéo vào các thư viện cần cho một khả năng | Không tự kéo vào mọi thư viện được quản lý |
| Ví dụ `spring-boot-starter-web` | `spring-boot-dependencies` |
| Chọn **nhóm chức năng** | Điều phối **phiên bản** |

Một ứng dụng có thể vừa dùng starter để nhận chức năng web, vừa dùng BOM để tránh phải gán version thủ công cho từng dependency.

## 4. Maven: quản lý dependency bằng Spring Boot parent

Với dự án Spring Boot đầu tiên, cách phổ biến nhất là kế thừa `spring-boot-starter-parent`.

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>demo-api</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Cấu hình này cho thấy:

1. Spring Boot parent cung cấp dependency management tương ứng và nhiều quy ước Maven liên quan plugin/build.
2. `java.version` khai báo phiên bản Java dự án sử dụng theo quy ước của Boot parent.
3. Hai starter không cần ghi version riêng vì đã nằm trong nguồn quản lý của parent.
4. Starter test thuộc `test` scope nên được dùng cho kiểm thử.
5. `spring-boot-maven-plugin` nằm trong `build/plugins` vì nó phục vụ build, chạy và đóng gói.

Với JDK và Maven phù hợp, có thể dùng:

~~~bash
mvn test
mvn package
mvn spring-boot:run
~~~

`mvn test` chạy các bước đến test phase; `mvn package` đi qua những phase cần thiết rồi tạo artifact; `mvn spring-boot:run` khởi chạy ứng dụng qua plugin Spring Boot.

Tập dependency được tải về có thể gồm nhiều artifact dù trong `pom.xml` bạn chỉ khai báo hai starter.

### 4.1. `dependencies` khác `dependencyManagement` như thế nào?

`<dependencies>` khai báo thư viện **module thực sự cần**:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

`<dependencyManagement>` khai báo quy tắc quản lý version và một số thông tin dependency. Nó có thể được kế thừa từ parent hoặc được khai báo trong POM.

Ví dụ cách import một BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

**Import BOM không tự tạo REST API.** Nếu chưa khai báo starter web trong `<dependencies>`, việc import BOM không làm Spring MVC xuất hiện trên runtime classpath.

### 4.2. Khi dự án đã có parent riêng

Maven chỉ cho phép một parent trực tiếp. Một doanh nghiệp có thể yêu cầu mọi dự án kế thừa POM nội bộ nên không thể đồng thời kế thừa `spring-boot-starter-parent`.

Khi đó dự án thường **import Boot BOM** trong `dependencyManagement` như trên. Sau đó khai báo dependency cần dùng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Import BOM không mang theo toàn bộ cấu hình plugin và lifecycle của starter parent. Nếu muốn executable JAR, phải cấu hình `spring-boot-maven-plugin` phù hợp (bao gồm version và mục tiêu `repackage` khi cần) hoặc sử dụng thiết lập đã được parent nội bộ cung cấp.

Ví dụ đoạn cấu hình plugin khi không dùng starter parent:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>3.3.5</version>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Ngoài plugin này, dự án không dùng starter parent cũng cần bảo đảm cấu hình Java compiler và phiên bản các Maven plugin liên quan được quản lý thích hợp. BOM chỉ là phần quản lý dependency.

## 5. Maven scope: khi nào dependency được sử dụng?

Maven cung cấp một số scope với ý nghĩa khác nhau.

| Scope | Ý nghĩa thông dụng | Ví dụ |
| --- | --- | --- |
| `compile` | Mặc định; thường dùng cho biên dịch và runtime | Spring MVC starter |
| `provided` | Có khi compile, nhưng môi trường triển khai dự kiến cung cấp dependency tương ứng | API servlet trong một số mô hình WAR |
| `runtime` | Không cần trực tiếp khi compile nhưng cần để chạy | JDBC driver |
| `test` | Phục vụ biên dịch và chạy test | Spring Boot test starter |
| `system` | Phụ thuộc theo đường dẫn JAR cục bộ; thường nên tránh | Mã di sản đặc biệt |
| `import` | Dùng trong `dependencyManagement` để import BOM kiểu POM | Spring Boot BOM |

Ví dụ PostgreSQL driver:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Nếu Boot BOM quản lý phiên bản driver tương ứng, bạn có thể bỏ version. Tuy nhiên, khai báo driver **chưa đủ** để kết nối database: ứng dụng cần cấu hình datasource, database hoạt động và các thư viện truy cập dữ liệu phù hợp.

Maven scope cũng tác động đến tính transitive của dependency. Không nên đưa toàn bộ test library vào compile classpath chỉ để tạm thời sửa lỗi một import.

## 6. Gradle: dependency management bằng plugin và BOM

Gradle tổ chức thư viện qua các **configuration**. Với Java plugin, những configuration quen thuộc là `implementation`, `runtimeOnly` và `testImplementation`.

Có hai cách phổ biến để dùng các phiên bản do Spring Boot quản lý:

- Kết hợp Spring Boot Gradle plugin với plugin `io.spring.dependency-management`.
- Sử dụng Gradle native BOM qua `platform(...)`.

Hai cách có ngữ nghĩa version resolution khác nhau. Hãy chọn một chiến lược nhất quán và kiểm tra resolved dependency khi cần.

### 6.1. Cách A: `io.spring.dependency-management`

Ví dụ `build.gradle` dùng Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Trong cấu hình này:

- Plugin `java` tạo các configuration và tác vụ biên dịch Java.
- Plugin `org.springframework.boot` bổ sung các task như `bootRun` và `bootJar` trong kiểu dự án thích hợp.
- Plugin `io.spring.dependency-management` tích hợp dependency management kiểu Maven. Khi kết hợp với Spring Boot Gradle plugin, nó có thể tự import BOM theo phiên bản Boot plugin.
- `repositories` cho biết nơi tải artifact.
- Các dependency có thể bỏ version vì đã được Boot BOM quản lý.
- `toolchain` cấu hình Java 21 cho công việc build liên quan.

**Chỉ thêm plugin `org.springframework.boot` không tự động bảo đảm tất cả dependency không version đều có thể resolve.** Cần dependency management plugin hoặc một cơ chế BOM/constraint tương ứng.

Các lệnh khi repository có Gradle Wrapper:

~~~bash
./gradlew bootRun
./gradlew test
./gradlew bootJar
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
.\gradlew.bat test
.\gradlew.bat bootJar
~~~

Wrapper phải có sẵn trong dự án để các lệnh `./gradlew` hoặc `.\gradlew.bat` hoạt động.

### 6.2. Cách B: Native Gradle BOM qua `platform(...)`

Gradle hỗ trợ nhập Maven BOM làm **platform constraints**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
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

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')

    implementation 'org.springframework.boot:spring-boot-starter-web'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`platform(...)` đưa các version constraints từ BOM vào những configuration cần thiết. Khai báo ở cả `implementation` và `testImplementation` giúp test dependencies cũng nhận các phiên bản được quản lý.

Cần hiểu một khác biệt: **Gradle native platform sử dụng thuật toán giải quyết phiên bản của Gradle**, không hoàn toàn giống `dependencyManagement` của Maven hoặc plugin `io.spring.dependency-management`. Nếu có một dependency yêu cầu version cao hơn hoặc ràng buộc chặt hơn, kết quả cuối có thể khác version được BOM gợi ý. Dùng `dependencyInsight` để biết nguyên nhân.

Không nên dùng `enforcedPlatform(...)` chỉ vì muốn “BOM luôn thắng”. Nó áp đặt ràng buộc mạnh hơn và có thể ảnh hưởng cả những module khác khi dependency được tiêu thụ transitively.

### 6.3. Gradle Kotlin DSL

Nếu dự án dùng `build.gradle.kts`, cú pháp là Kotlin DSL:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.5"
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

dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:3.3.5"))
    testImplementation(platform("org.springframework.boot:spring-boot-dependencies:3.3.5"))

    implementation("org.springframework.boot:spring-boot-starter-web")
    runtimeOnly("org.postgresql:postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Groovy DSL và Kotlin DSL cùng diễn tả dependency và task của Gradle nhưng khác cú pháp. Đừng sao chép cú pháp `implementation '...'` từ Groovy vào một file Kotlin DSL.

## 7. Gradle configuration: dependency thuộc classpath nào?

| Configuration | Vai trò | Ví dụ |
| --- | --- | --- |
| `implementation` | Dependency cho mã ứng dụng, thường tham gia compile/runtime | Starter web |
| `compileOnly` | Cần khi compile, không tự đưa vào runtime | Một số API hoặc annotation |
| `runtimeOnly` | Cần lúc chạy, không bắt buộc khi compile | Driver JDBC trong nhiều dự án |
| `testImplementation` | Phục vụ compile và runtime của test | Starter test |
| `testRuntimeOnly` | Thêm vào runtime của test | Một số test engine |
| `annotationProcessor` | Dependency dùng cho xử lý annotation khi compile | Configuration processor |

Ví dụ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Configuration processor sinh metadata hỗ trợ tooling khi xử lý cấu hình Spring Boot; nó không phải dependency phục vụ xử lý HTTP request.

Với dự án thư viện dùng plugin `java-library`, `api` có thêm ý nghĩa: những dependency thuộc API công khai của thư viện có thể lộ ra cho consumer. Dự án ứng dụng Spring Boot thông thường thường dùng `implementation`, còn việc công bố API của module thư viện cần được thiết kế riêng.

## 8. Maven và Gradle khác nhau ở những điểm nào?

| Chủ đề | Maven | Gradle |
| --- | --- | --- |
| File build | `pom.xml` | `build.gradle` hoặc `build.gradle.kts` |
| Khai báo dependency | `<dependencies>` và `<dependency>` | `dependencies { ... }` |
| BOM Spring Boot | Parent hoặc `dependencyManagement` import BOM | Dependency Management plugin hoặc `platform(...)` |
| Phân loại classpath | Scope `compile`, `runtime`, `test`... | `implementation`, `runtimeOnly`, `testImplementation`... |
| Chạy ứng dụng Boot | `mvn spring-boot:run` | `./gradlew bootRun` |
| Xem dependency graph | `mvn dependency:tree` | `./gradlew dependencies` |
| Điều tra nguyên nhân version | Dependency tree và effective POM | `dependencyInsight` |
| Conflict version mặc định | Mediation dựa trên khoảng cách trong cây phụ thuộc | Thường chọn version cao hơn trong các yêu cầu có thể giải quyết, chịu ràng buộc bởi constraints/rules |

Không thể dịch từng Maven scope trực tiếp sang một Gradle configuration mà không xét classpath. Ví dụ Gradle `implementation` vừa phục vụ compile của module hiện tại vừa ảnh hưởng runtime theo mô hình của Java plugin; nó còn che dependency khỏi compile classpath của consumer trong mô hình thư viện. Maven `compile` có quy tắc transitive riêng.

## 9. Vì sao version conflict xuất hiện?

Giả sử:

~~~text
Ứng dụng
    ├── module-A ──► api-lib:1.0
    └── module-B ──► api-lib:2.0
~~~

Một số phương thức có thể đã thay đổi giữa hai version. Nếu runtime chỉ dùng một bản không tương thích với một trong các module, lỗi có thể xuất hiện trong khi khởi động hoặc khi chạy đến một nhánh code cụ thể.

### 9.1. Maven: dependency mediation

Maven thường ưu tiên dependency gần root hơn trong cây (“nearest definition”). Nếu hai đường phụ thuộc có cùng độ sâu, thứ tự khai báo có thể ảnh hưởng version được chọn. Quy tắc `dependencyManagement` được áp dụng cũng có thể điều khiển version một artifact.

Vì vậy, **không thể chỉ nhìn một library POM để kết luận version nào sẽ được chạy**. Cần xem dependency tree của ứng dụng.

### 9.2. Gradle: version constraints và conflict resolution

Gradle thường chọn version cao nhất trong những yêu cầu tương thích, trừ khi có constraints, strict version, forced version, platform hoặc quy tắc resolution khác. Khi native BOM được import qua `platform(...)`, các phiên bản từ BOM tham gia quá trình resolution dưới dạng constraints.

Điều này giải thích vì sao version thực sự có thể khác bản được BOM đề xuất khi tồn tại yêu cầu khác. Đừng giả định rằng BOM luôn “khóa cứng” mọi phiên bản trong Gradle.

### 9.3. Lỗi runtime có thể liên quan dependency

Một số lỗi cần xem xét dependency graph:

~~~text
java.lang.NoSuchMethodError: ...
java.lang.NoClassDefFoundError: ...
java.lang.ClassNotFoundException: ...
~~~

`NoSuchMethodError` có thể cho biết mã gọi một method không tồn tại ở class mà runtime đã nạp. `ClassNotFoundException` có thể do dependency cần thiết không nằm trên runtime classpath. `NoClassDefFoundError` cũng có thể phát sinh do lỗi khởi tạo class, không chỉ thiếu JAR.

Lỗi cụ thể cần được phân tích qua stack trace, dependency graph và cách đóng gói thực tế; không phải lỗi nào cũng giải quyết bằng nâng version tùy ý.

## 10. Xem phiên bản đã được resolve bằng Maven

Từ thư mục chứa `pom.xml`:

~~~bash
mvn dependency:tree
~~~

Kết quả cho biết các dependency và nhánh transitive đang được sử dụng. Để tập trung vào Jackson:

~~~bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
~~~

Để xem POM sau khi áp dụng kế thừa parent, property và dependency management:

~~~bash
mvn help:effective-pom
~~~

Những công cụ này trả lời các câu hỏi khác nhau:

- **Đang khai báo gì?** Đọc `pom.xml`.
- **Các quy tắc quản lý version có hiệu lực là gì?** Xem effective POM.
- **Đồ thị dependency cuối cùng gồm gì?** Xem dependency tree.

Nếu POM khai báo thư viện không version nhưng effective POM không có quy tắc quản lý version cho artifact ấy, Maven có thể báo lỗi thiếu version trước khi build.

## 11. Xem phiên bản đã được resolve bằng Gradle

Với Gradle Wrapper:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Lệnh này hiển thị dependency graph của classpath chạy ứng dụng.

Để xem lý do một phiên bản cụ thể được chọn:

~~~bash
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

`dependencyInsight` đặc biệt hữu ích khi Gradle chọn version khác version bạn nhìn thấy trong một dependency declaration. Kết quả giúp xác định đường phụ thuộc, yêu cầu version và các quy tắc resolution liên quan.

Để xem phụ thuộc của test, hãy chọn đúng configuration cho test. Để xem dependency của bản thân quá trình build hoặc plugin, cần công cụ và configuration thích hợp; chúng không nhất thiết nằm trên runtimeClasspath của ứng dụng.

## 12. Thêm dependency mới theo một quy trình có kiểm chứng

Giả sử cần kiểm tra dữ liệu đầu vào bằng Bean Validation.

### Bước 1: Chọn dependency phù hợp

Với Spring Boot 3.x, starter thường dùng là:

~~~text
org.springframework.boot:spring-boot-starter-validation
~~~

### Bước 2: Khai báo đúng vị trí

Maven, nếu đã có parent/BOM:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Gradle, nếu BOM đã được áp dụng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

### Bước 3: Resolve và biên dịch

Maven:

~~~bash
mvn compile
~~~

Gradle:

~~~bash
./gradlew compileJava
~~~

Build tool tải dependency từ repository, tính version và thiết lập classpath. Nếu lỗi ở giai đoạn này, cần kiểm tra tọa độ, repository hoặc nguồn version management trước.

### Bước 4: Sử dụng khả năng đã thêm

Ví dụ DTO trong Spring Boot 3.x:

~~~java
import jakarta.validation.constraints.NotBlank;

public record CreateUserRequest(@NotBlank String name) {
}
~~~

Trong controller Spring MVC:

~~~java
@PostMapping("/users")
public ResponseEntity<String> create(
        @Valid @RequestBody CreateUserRequest request) {
    return ResponseEntity.ok("Created: " + request.name());
}
~~~

Đoạn controller trên minh họa việc sử dụng `@Valid` và `@RequestBody`; nó cần các import Spring MVC/Jakarta Validation và một controller hợp lệ để biên dịch trong dự án.

Dependency mới cho phép sử dụng Bean Validation, nhưng ứng dụng vẫn phải khai báo constraint và kích hoạt validation tại vị trí phù hợp. **Dependency có mặt trên classpath không đồng nghĩa hành vi mong muốn tự diễn ra**.

### Bước 5: Kiểm tra kết quả

Sau khi build được, chạy kiểm thử hoặc gửi request hợp lệ và không hợp lệ. Nếu cần xác định version cụ thể, dùng dependency tree/dependencyInsight.

Đây là vòng làm việc hữu ích: **xác định chức năng → chọn dependency → khai báo đúng scope → resolve → dùng API → quan sát hành vi**.

## 13. Ghi đè version: khi nào và bằng cách nào?

Spring Boot BOM giúp bạn bắt đầu từ bộ phiên bản đã được chọn cho dòng Boot tương ứng. Đôi khi cần nâng một artifact vì lỗi bảo mật, lỗi chức năng hoặc yêu cầu tính năng mới.

Trước khi ghi đè, hãy xem:

1. Version đang được resolve là gì?
2. Thư viện có nằm trong BOM Boot hay không?
3. Bản Boot mới hơn có giải quyết nhu cầu qua một bộ phiên bản đồng bộ không?
4. Version mới có tương thích với Spring Framework và các thư viện liên quan không?
5. Có test nào xác nhận các chức năng bị ảnh hưởng không?

Trong Maven, bạn có thể khai báo version cụ thể cho dependency ngoài BOM:

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>some-library</artifactId>
    <version>1.4.0</version>
</dependency>
~~~

Đây là tọa độ **minh họa**. Với dependency được quản lý, dự án có thể sử dụng `dependencyManagement` hoặc property override của starter parent theo cách mà phiên bản Boot tương ứng hỗ trợ.

Với Gradle:

~~~groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.example:some-library:1.4.0'
}
~~~

Một version được ghi trực tiếp vẫn tham gia thuật toán resolution của Gradle cùng các ràng buộc khác; hãy xem `dependencyInsight` trước khi kết luận.

**Không nên ghi đè phiên bản của nhiều thư viện có liên quan bằng những số rời rạc nếu chưa hiểu quan hệ tương thích giữa chúng.** Ví dụ, các module Jackson thường cần được phối hợp theo cùng một dòng phiên bản; nâng đồng bộ Boot hoặc BOM liên quan thường dễ kiểm soát hơn.

## 14. Exclusion: loại bỏ dependency kéo theo

Đôi khi một starter mang theo thành phần mà dự án muốn thay bằng lựa chọn khác. Build tool cho phép loại bỏ một transitive dependency tại cạnh khai báo.

Ví dụ minh họa chuyển logging starter của Spring Boot:

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-log4j2</artifactId>
</dependency>
~~~

Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-logging'
    }

    implementation 'org.springframework.boot:spring-boot-starter-log4j2'
}
~~~

Đây là một thay đổi có chủ đích với các yêu cầu về logging, không phải thao tác bắt buộc cho mọi ứng dụng.

Cần lưu ý:

- Exclude theo một nhánh không chắc đã loại artifact khỏi toàn bộ đồ thị nếu nhánh khác vẫn yêu cầu nó.
- Loại bỏ dependency có thể làm class hoặc dịch vụ cần thiết biến mất.
- Khi thay logging, phải kiểm tra các starter khác có mang logging mặc định vào không.
- Sau khi loại bỏ, xem dependency tree và kiểm thử hành vi.

Không nên xóa dependency transitively chỉ vì nhìn thấy nó trong đồ thị mà chưa hiểu vai trò của nó.

## 15. Repository và lỗi không tải được thư viện

Gradle khai báo repository thường dùng:

~~~groovy
repositories {
    mavenCentral()
}
~~~

Maven thường có Maven Central qua cấu hình mặc định và có thể sử dụng `settings.xml` hoặc POM để khai báo repository/mirror theo môi trường.

Những nguyên nhân hay gặp khi tải artifact thất bại:

- Sai `groupId`, `artifactId` hoặc version.
- Repository không có artifact đó.
- Mất kết nối mạng, sai proxy hoặc lỗi DNS/TLS.
- Repository nội bộ yêu cầu xác thực.
- Build đang offline nhưng artifact chưa có trong cache.
- Metadata của artifact không hợp lệ hoặc thiếu.

Nếu gặp `401 Unauthorized` hoặc `403 Forbidden` khi truy cập repository nội bộ, hãy xem cấu hình credential và quyền truy cập. Không ghi secret thật vào file build rồi commit để “sửa nhanh” lỗi tải dependency.

Phân biệt lỗi **không resolve được artifact** với lỗi **code không biên dịch**. Một lỗi xảy ra trước khi dependency được tải; lỗi kia xảy ra khi compiler kiểm tra mã hoặc API đã được đưa vào classpath.

## 16. Build có thể tái tạo và chính sách nâng phiên bản

Một dự án dễ bảo trì cần có khả năng build lại với các dependency phù hợp trên máy khác hoặc trong CI.

Các thói quen giúp ổn định:

- Dùng phiên bản Spring Boot và plugin rõ ràng.
- Quản lý các dependency theo BOM thích hợp.
- Tránh dùng version động như `1.+` nếu chưa có quy trình quản trị.
- Kiểm soát repository và nguồn artifact.
- Nâng dependency có mục đích, kiểm tra release notes và chạy test tương ứng.
- Ghi nhận quyết định thay version trong code review khi cần.

### 16.1. Gradle dependency locking

Gradle cung cấp **dependency locking** để lưu kết quả resolution của các configuration được bật locking.

Ví dụ Groovy DSL:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau đó tạo/cập nhật lock state theo những task phù hợp, ví dụ:

~~~bash
./gradlew dependencies --write-locks
~~~

Nếu dùng locking, file lock cần được quản lý cùng source và cập nhật có chủ đích khi nâng dependency. Không nên xóa lockfile chỉ để một version conflict biến mất mà chưa hiểu nguyên nhân.

### 16.2. Maven và quản lý phiên bản

Maven sử dụng dependency management, effective POM và version cụ thể. Một dự án Maven cơ bản không có sẵn mô hình lockfile tương đương trực tiếp Gradle dependency locking. Tổ chức có thể bổ sung Maven Enforcer Plugin, artifact repository mirror và quy định nâng phiên bản để tăng khả năng tái tạo.

BOM cung cấp điểm xuất phát nhất quán, nhưng build reproducibility cũng phụ thuộc vào plugin, repository, biến môi trường và quy trình phát hành artifact.

## 17. Dự án nhiều module cần quản lý gì?

Giả sử hệ thống có cấu trúc:

~~~text
shopping-system/
├── web-api/
├── domain/
└── persistence/
~~~

Một quan hệ hợp lý có thể là:

~~~mermaid
flowchart TD
    W["web-api"] --> D["domain"]
    W --> P["persistence"]
    P --> D
    W --> S["Web starter"]
    P --> J["JDBC/JPA libraries"]
~~~

Không phải module nào cũng cần mọi starter. Domain module thuần Java có thể không cần Spring Web hoặc runtime server. Các module dùng chung thư viện nên thống nhất về version, nhưng mỗi module chỉ khai báo dependency thực sự sử dụng.

**Maven multi-module** thường dùng parent POM và `dependencyManagement` cho version chung. Mỗi module con tự khai báo những dependency cần thiết.

**Gradle multi-project** có thể tập trung version qua convention plugin, version catalog hoặc platform dùng chung, trong khi từng subproject dùng configuration phù hợp.

Mục tiêu là giảm trùng lặp quy tắc phiên bản và kiểm soát ranh giới module, không phải thêm toàn bộ thư viện vào mọi module.

### 17.1. Gradle version catalog

Version catalog giúp tập trung alias và version, ví dụ trong `gradle/libs.versions.toml`:

~~~toml
[versions]
springBoot = "3.3.5"

[libraries]
spring-web = { module = "org.springframework.boot:spring-boot-starter-web" }

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "springBoot" }
~~~

Khi catalog mặc định tên `libs` có hiệu lực, Gradle có thể tham chiếu dependency qua `libs.spring.web`.

Tuy nhiên, version catalog **không tự biến thành BOM**. Với alias dependency không có version ở ví dụ trên, dự án vẫn cần dependency management hoặc platform constraints cho configuration liên quan.

Catalog tập trung cách gọi và version do dự án quản lý; BOM tập trung các phiên bản phù hợp cho một hệ sinh thái dependency; Gradle tiếp tục là công cụ quyết định resolved graph sau cùng.

## 18. Các lỗi dependency thường gặp và cách khoanh vùng

### Lỗi A: Maven thiếu version

Thông báo có thể chứa:

~~~text
'dependencies.dependency.version' for ... is missing
~~~

Dự án có thể khai báo dependency không version nhưng chưa kế thừa parent hoặc import BOM quản lý artifact ấy.

**Kiểm tra:** `pom.xml`, `mvn help:effective-pom`, sau đó xác định artifact có nằm trong nguồn quản lý version không.

### Lỗi B: Gradle không resolve được một starter không version

Thông báo có thể chứa:

~~~text
Could not find org.springframework.boot:spring-boot-starter-web:
~~~

Một nguyên nhân là chưa áp dụng `io.spring.dependency-management` hoặc `platform(...)` vào configuration đang khai báo.

**Kiểm tra:** build script, repository, BOM và configuration; không vội gán version cho từng starter theo cảm tính.

### Lỗi C: Build xong, runtime báo thiếu class hoặc method

**Kiểm tra:** stack trace, runtime classpath và version được resolve. Có thể là xung đột version, thiếu runtime dependency, exclusion sai hoặc packaging/classloader khác dự kiến.

Không thể suy ra một nguyên nhân duy nhất chỉ từ tên exception.

### Lỗi D: Thêm driver rồi vẫn không kết nối database

Driver chỉ cung cấp một phần khả năng truy cập dữ liệu. Ứng dụng có thể còn thiếu datasource URL, username, password, database thực sự đang hoạt động hoặc starter truy cập dữ liệu.

**Kiểm tra:** dependency, cấu hình datasource, network và log kết nối theo đúng thứ tự lỗi.

### Lỗi E: Dependency chỉ có trong test nhưng runtime production cần nó

Nếu dependency khai báo `test`/`testImplementation` thì thường không thuộc runtime classpath của ứng dụng chính.

**Kiểm tra:** scope/configuration trước khi tìm lỗi trong Java source.

### Lỗi F: Thư viện được yêu cầu ở nhiều version

**Kiểm tra:** `dependency:tree` hoặc `dependencyInsight` để tìm các nhánh gây xung đột. Sau đó đánh giá compatibility và quyết định nâng Boot, sửa constraint, bỏ thư viện hoặc cấu hình version có chủ đích.

Tránh loại bỏ transitive dependency khi chưa biết module nào đang sử dụng nó.

## 19. Thực hành: đọc và sửa file build

### Bài 1: Nhận diện vai trò

Phân loại các thành phần sau:

| Thành phần | Đáp án |
| --- | --- |
| `spring-boot-starter-web` | Starter dependency |
| `spring-boot-dependencies` | BOM quản lý version |
| `spring-boot-maven-plugin` | Maven build plugin |
| `mavenCentral()` | Cấu hình repository trong Gradle |
| `spring-boot-starter-test` | Dependency phục vụ test |

Giải thích: starter được thêm như thư viện, BOM quản lý phiên bản, plugin giúp build, repository giúp tải artifact.

### Bài 2: Vì sao test starter cần scope đúng?

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Hãy trả lời:

1. Library này phục vụ source chính hay test?
2. Nếu bỏ `<scope>test</scope>`, classpath nào có thể nhận thêm những thư viện không cần thiết?
3. BOM có tự thêm starter test nếu không khai báo nó không?

**Gợi ý:** Starter test phục vụ kiểm thử; scope giúp giới hạn việc đưa thư viện vào classpath; BOM không tự thêm dependency.

### Bài 3: Tìm lỗi quản lý version của Gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

**Câu hỏi:** Vì sao dependency này có thể không resolve được?

**Gợi ý:** Chưa có nguồn version management cho `implementation`. Có thể thêm `implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')` hoặc dùng plugin `io.spring.dependency-management` theo cấu hình phù hợp.

### Bài 4: Chọn scope/configuration

Một REST API cần:

- Spring MVC để nhận HTTP và trả JSON.
- Spring Data JPA để truy cập dữ liệu.
- PostgreSQL driver ở runtime.
- Các thư viện kiểm thử controller.

Các dependency thông dụng gồm:

~~~text
spring-boot-starter-web
spring-boot-starter-data-jpa
org.postgresql:postgresql
spring-boot-starter-test
~~~

Hãy viết dưới dạng Maven `dependencies` hoặc Gradle `dependencies { ... }` và chỉ ra scope/configuration thích hợp. Đừng quên nguồn version management (parent/BOM/plugin/platform).

Một lựa chọn Gradle Groovy DSL, giả sử BOM đã được áp dụng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Điều này chưa tạo database hoặc entity. Hãy phân biệt việc **có dependency** với việc **ứng dụng đã được cấu hình và thực thi đúng**.

### Bài 5: Tìm phiên bản Jackson thật sự

Maven:

~~~bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Ghi lại version được resolve. Nếu không thấy artifact, kiểm tra configuration hoặc tập dependency thực tế. Giải thích artifact xuất hiện từ dependency trực tiếp hay transitive.

### Bài 6: Nêu hệ quả khi đổi phiên bản

Hãy tưởng tượng một đồng nghiệp đổi version của một thư viện JSON trong khi giữ nguyên Boot BOM.

Cần trả lời được:

- Vì sao phải ghi đè?
- Có những module liên quan nào cần cùng version?
- Dependency graph thực sự chọn version nào?
- Cần chạy test nào sau khi đổi?
- Nâng phiên bản Boot đồng bộ có phải phương án phù hợp hơn không?

Những câu hỏi này giúp thay đổi dependency trở thành quyết định có chứng cứ.

## 20. Những điểm cần nắm vững

**Dependency management không chỉ là cú pháp viết trong file build.** Nó bao gồm việc hiểu dependency trực tiếp, dependency transitive, nguồn tải artifact, classpath và cách một version được chọn khi có nhiều yêu cầu.

Với **Maven**, mô hình Spring Boot dễ bắt đầu là `spring-boot-starter-parent`; khi phải dùng parent khác, có thể import `spring-boot-dependencies` BOM trong `dependencyManagement` và cấu hình plugin cần thiết. Với **Gradle**, có thể dùng `io.spring.dependency-management` hoặc native `platform(...)`, chú ý sự khác biệt trong giải quyết phiên bản.

Một cách làm đáng tin cậy là: **chọn starter phù hợp, khai báo đúng scope, thống nhất BOM và plugin, để build tool resolve, rồi kiểm tra dependency graph khi phát sinh thay đổi hoặc xung đột**. Khi nắm rõ thư viện đến từ đâu và vì sao phiên bản đó được chọn, bạn sẽ chủ động hơn trong việc xây dựng, nâng cấp và sửa lỗi ứng dụng Spring Boot.

