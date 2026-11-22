# Phân biệt nâng plugin Boot với nâng BOM và phụ thuộc ứng dụng

## Mục tiêu

Khi nâng cấp Spring Boot, ba thay đổi thường bị gọi chung là “nâng version Boot”:

1. **Nâng build plugin:** thay đổi plugin Gradle hoặc Maven chạy trong quá trình build, đóng gói và tạo executable artifact.
2. **Nâng BOM (Bill of Materials):** thay đổi bộ phiên bản dependency mà Spring Boot quản lý, ví dụ Spring Framework, Jackson, Hibernate và logging.
3. **Nâng dependency ứng dụng:** thêm, bỏ hoặc đổi một thư viện cụ thể mà code nghiệp vụ trực tiếp sử dụng.

Ba việc có liên quan nhưng tác động lên những phần khác nhau của build. Nếu thay nhầm version ở sai chỗ, dự án có thể build được nhưng runtime dùng bộ thư viện không tương thích, hoặc task bootJar/repackage không chạy như mong đợi.

Bài này dùng **Spring Boot 3.3.13** làm mốc ví dụ cố định theo tài liệu của release đó. Đây không phải khẳng định rằng 3.3.13 là release mới nhất. Khi nâng dự án thật, hãy chọn release còn được hỗ trợ và đọc system requirements, release notes và migration guide của release đích.

Sau bài này, bạn có thể phân biệt ba loại version, chọn chiến lược BOM cho Gradle/Maven, tìm version dependency thực tế đã resolve và nâng cấp theo quy trình có kiểm chứng.

---

## 1. Bốn lớp version trong dự án Spring Boot

| Lớp | Ví dụ | Vai trò |
| --- | --- | --- |
| Build tool và JDK | Gradle Wrapper, Maven Wrapper, JDK 17 | Chạy build, compile và kiểm soát bytecode |
| Spring Boot build plugin | org.springframework.boot Gradle plugin hoặc spring-boot-maven-plugin | Cung cấp task và hành vi đóng gói |
| Dependency platform/BOM | spring-boot-dependencies | Quản lý version dependency ứng dụng và dependency bắc cầu |
| Application dependencies | spring-boot-starter-web, SDK, JDBC driver | Xác định thư viện thực sự có trên classpath |

Ví dụ cấu hình:

~~~text
JDK:                         17
Gradle Wrapper:              8.x
Spring Boot Gradle plugin:   3.3.13
Spring Boot BOM:             3.3.13
Application dependency:     spring-boot-starter-web
Internal SDK:                4.2.0
~~~

Plugin org.springframework.boot nằm trong build logic; spring-boot-dependencies là platform quản lý dependency; starter và SDK nằm trong dependency graph của ứng dụng.

### 1.1 Build plugin

Plugin được khai báo trong Gradle plugins block hoặc Maven build/plugins. Nó chạy trong quá trình build và có thể:

- Đăng ký task tạo executable archive, ví dụ Gradle bootJar.
- Cấu hình task chạy ứng dụng, ví dụ bootRun.
- Tích hợp với Java, Kotlin, War hoặc plugin build khác.
- Cấu hình executable JAR/WAR và Maven repackage.
- Cung cấp các task build image hoặc build information khi tính năng tương ứng được bật.

Plugin không phải dependency mà code ứng dụng import trong src/main/java. Không thêm spring-boot-gradle-plugin vào implementation chỉ để nâng plugin build.

### 1.2 BOM

BOM là một POM có dependencyManagement mô tả phiên bản được quản lý cho một tập module. Spring Boot phát hành BOM có tọa độ:

~~~text
org.springframework.boot:spring-boot-dependencies:3.3.13
~~~

Khi BOM có hiệu lực, dependency được quản lý có thể khai báo mà không ghi version ở từng dòng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

BOM không tự tạo task bootJar, không đóng gói ứng dụng và không tự thêm mọi dependency vào project. Ứng dụng vẫn phải khai báo những starter/library mà nó thực sự dùng.

### 1.3 Application dependency

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
    implementation 'com.acme:partner-sdk:4.2.0'
}
~~~

Các dòng này thêm module vào dependency graph. BOM có thể quản lý version của một số module; dependency không nằm trong BOM có thể cần version riêng. Nâng một dependency ứng dụng không đồng nghĩa phải nâng Spring Boot plugin.

### 1.4 Plugin và BOM có thể được liên kết

Đây là điểm quan trọng khi dùng Gradle:

- Khi Spring Boot Gradle plugin được dùng cùng io.spring.dependency-management, plugin này tự import spring-boot-dependencies theo **version Spring Boot plugin đang dùng**.
- Khi dùng Gradle native BOM support, project khai báo platform("org.springframework.boot:spring-boot-dependencies:...") trong dependencies. Version BOM được ghi rõ trong dependency declaration.
- Hai chiến lược đều hợp lệ. Chọn một cách quản lý rõ ràng và kiểm tra version thực tế được resolve.

Vì vậy, trong cấu hình Gradle dùng dependency-management plugin, đổi version Spring Boot plugin thường đồng thời đổi BOM được import tự động. Không được giả định rằng chỉ nâng plugin sẽ luôn giữ nguyên bộ dependency.

---

## 2. Nâng Spring Boot Gradle plugin

### 2.1 Khai báo plugin

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}
~~~

org.springframework.boot là plugin ID. 3.3.13 ở đây là version của **Gradle plugin**, được Gradle resolve từ plugin repositories. Nó không phải dependency runtime mà JVM tải khi ứng dụng khởi động.

Khi plugin được apply cùng Java plugin, Spring Boot có thể cấu hình executable JAR task và các task liên quan. Nếu plugin không được apply đúng, task bootJar có thể không tồn tại dù project có khai báo thư viện Spring Boot.

### 2.2 Plugin repositories khác dependency repositories

Gradle plugins block dùng cơ chế plugin resolution. Repository thường được cấu hình trong pluginManagement ở settings.gradle:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
~~~

Nếu tổ chức dùng plugin repository nội bộ, thêm endpoint đó theo chính sách của tổ chức. Không nhầm pluginManagement.repositories với repositories dùng để tải application dependencies.

### 2.3 Quản lý plugin version tập trung

Trong multi-project build, root có thể khai báo version với apply false:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.13' apply false
}
~~~

Module application sau đó apply plugin:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
}
~~~

Chỉ apply Boot plugin cho module thực sự là Boot application. Một module Java library thuần thường không cần plugin này.

Version plugin cũng có thể được lưu trong gradle/libs.versions.toml:

~~~toml
[versions]
springBoot = "3.3.13"

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "springBoot" }
~~~

Version catalog giúp gom alias/version, nhưng bản thân nó không thay thế BOM. Plugin alias chỉ quản lý plugin build; muốn quản lý dependency bắc cầu vẫn cần BOM/platform hoặc dependency constraints.

---

## 3. Hai chiến lược dùng Spring Boot BOM trong Gradle

### 3.1 Cách A — dependency-management plugin

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

apply plugin: 'io.spring.dependency-management'

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Khi io.spring.dependency-management được apply, Spring Boot Gradle plugin tự import BOM spring-boot-dependencies tương ứng với version Boot plugin. Dependency được BOM quản lý có thể bỏ version trong declaration.

Plugin Spring Boot mang dependency của dependency-management plugin trong build plugin classpath; vì vậy có thể apply plugin bằng ID như ví dụ trên mà không nhất thiết khai báo thêm version độc lập cho nó.

**Hệ quả khi nâng version:** nếu đổi Boot Gradle plugin từ 3.3.13 sang release khác và vẫn dùng cơ chế import tự động, BOM mặc định cũng chuyển theo version plugin mới. Hãy review đồng thời dependency graph.

Plugin dependency-management cho phép tùy chỉnh các version property mà BOM công bố. Ví dụ cấu trúc:

~~~groovy
ext['slf4j.version'] = '2.0.16'
~~~

Tên property và version phải được xác nhận trong bảng dependency version properties của đúng release Spring Boot. Không đoán tên property hoặc sao chép property từ release khác. Override có thể làm bộ dependency lệch khỏi tập hợp mà Boot đã kiểm thử; chỉ làm khi có yêu cầu cụ thể và có test chứng minh.

### 3.2 Cách B — Gradle native BOM support

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Ở cách này, version BOM được khai báo rõ trong platform(...). Boot Gradle plugin vẫn cung cấp task/packaging; platform(...) quản lý version của application dependencies.

Spring Boot ghi nhận native BOM support có thể làm build nhanh hơn. Đổi lại, việc tùy chỉnh version dựa trên Maven properties của BOM không được hỗ trợ giống dependency-management plugin; hãy dùng dependency constraints hoặc cơ chế version resolution của Gradle.

### 3.3 platform và enforcedPlatform

~~~groovy
dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
}
~~~

~~~groovy
dependencies {
    implementation enforcedPlatform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
}
~~~

| Cách khai báo | Ý nghĩa |
| --- | --- |
| platform(...) | Dùng constraints của BOM trong version resolution; các constraint/version khác trong dependency graph vẫn có thể ảnh hưởng kết quả |
| enforcedPlatform(...) | Áp dụng version từ platform như yêu cầu bắt buộc, ghi đè các version khác trong graph |

Không chọn enforcedPlatform chỉ để build hết conflict. Nó có thể ép version lên dependency bắc cầu mà một library khác không tương thích. Bắt đầu với platform và chỉ dùng enforced behavior khi đã hiểu phạm vi ảnh hưởng.

### 3.4 Không import BOM hai lần vô ý

Nếu đã apply dependency-management plugin và Boot plugin tự import BOM, thường không cần thêm một platform cùng BOM vào dependencies.

Nếu đã chọn native BOM support, không đồng thời apply dependency-management plugin rồi import lại BOM nếu không có thiết kế rõ ràng. Hai cơ chế có thể cùng tham gia quản lý version và làm người đọc khó hiểu nguồn version cuối cùng.

### 3.5 Chọn chiến lược nào?

| Nhu cầu | Gợi ý |
| --- | --- |
| Dự án hiện tại dùng dependency-management plugin ổn định | Tiếp tục cách hiện tại khi nâng Boot |
| Muốn dùng Gradle native BOM support | Dùng platform(...), kiểm tra constraints và version resolution |
| Cần tùy chỉnh BOM properties do Spring Boot công bố | Dependency-management plugin thuận tiện hơn |
| Muốn BOM version được ghi rõ, tách khỏi Boot plugin version | Native platform(...) làm mối quan hệ này minh bạch |
| Nhiều module cần version policy chung | Cân nhắc convention plugin hoặc platform nội bộ |

Không có một chiến lược duy nhất đúng cho mọi repository. Quan trọng là xác định nguồn version, áp dụng nhất quán và giải thích được vì sao Gradle resolve ra version cuối.

---

## 4. Maven: parent POM và BOM import không giống nhau

### 4.1 Dùng spring-boot-starter-parent

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
</parent>

<groupId>com.example</groupId>
<artifactId>orders-service</artifactId>
<version>1.0.0</version>

<properties>
    <java.version>17</java.version>
</properties>
~~~

Parent cung cấp dependency management và plugin defaults:

- Dependency management được kế thừa từ spring-boot-dependencies.
- Plugin management cho plugin build liên quan.
- Cấu hình Maven compiler/resource và các default khác.
- Execution repackage của Spring Boot Maven plugin theo cấu hình parent.

Khi nâng version parent, cần review cả dependency management lẫn plugin management mà parent cung cấp.

### 4.2 Import riêng spring-boot-dependencies

Nếu dự án không thể kế thừa spring-boot-starter-parent vì đã có corporate parent, có thể import BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Cách này cung cấp dependency management của Spring Boot nhưng **không mang theo plugin management của starter parent**. Nếu cần executable JAR, phải cấu hình spring-boot-maven-plugin phù hợp trong build/plugins:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>3.3.13</version>
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

Version Maven plugin là build plugin version. Version trong BOM là dependency platform version. Hai dòng có thể được quản lý độc lập khi không dùng starter parent.

### 4.3 So sánh parent và BOM import

| Khả năng | spring-boot-starter-parent | Import spring-boot-dependencies |
| --- | --- | --- |
| Quản lý dependency versions | Có | Có |
| Plugin management | Có | Không |
| Cấu hình repackage mặc định | Có execution từ parent | Cần khai báo plugin/execution nếu muốn |
| Dùng khi đã có corporate parent | Không thể kế thừa hai parent trực tiếp | Phù hợp hơn |
| Version Boot nằm ở đâu | Parent version | BOM version; plugin version cấu hình riêng |

Maven chỉ cho phép một parent trực tiếp. Nếu tổ chức có parent riêng, import BOM là cách phổ biến để nhận dependency management của Spring Boot mà vẫn giữ corporate parent.

### 4.4 Version khai báo trực tiếp có thể override BOM

BOM quản lý version khi dependency không khai báo version riêng. Nếu application khai báo version trực tiếp cho jackson-databind hoặc một module khác, version đó có thể ghi đè version được quản lý. Chỉ làm vậy khi có compatibility/security rationale và đã kiểm thử.

Parent/BOM có thể công bố property điều khiển version một số dependency. Khi đúng property được hỗ trợ, có thể override trong project:

~~~xml
<properties>
    <java.version>17</java.version>
    <slf4j.version>2.0.16</slf4j.version>
</properties>
~~~

Tên property và giá trị minh họa phải được đối chiếu với bảng dependency version properties của release cụ thể. Khi chỉ import BOM mà không dùng starter parent, cơ chế override property không giống kế thừa parent; cần khai báo dependency management entry phù hợp hoặc dùng cơ chế quản lý version khác.

---

## 5. Nâng application dependencies mà không nâng Boot plugin

### 5.1 Thêm starter được BOM quản lý

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Nếu BOM quản lý starter, không cần version riêng. Đây là thay đổi tính năng của application.

### 5.2 Nâng thư viện không nằm trong BOM

~~~groovy
dependencies {
    implementation 'com.acme:partner-sdk:4.2.0'
}
~~~

Khi cần nâng SDK lên 4.3.0, thay version ở declaration hoặc version catalog. Không cần thay Boot plugin nếu không có yêu cầu tương thích khác.

### 5.3 Nâng một dependency đã được BOM quản lý

Có ba tình huống:

1. BOM release mới đã nâng dependency: nâng BOM theo Boot release phù hợp.
2. Cần security fix trước khi nâng Boot: override dependency version có kiểm soát, theo property/constraint/dependency-management policy phù hợp.
3. Dependency không nằm trong BOM: quản version ở application/platform của tổ chức.

Không tự thêm version vào mọi dependency chỉ để pin cho chắc. Làm vậy khiến dự án khó nhận các bản cập nhật tương thích từ BOM trong lần nâng tiếp theo.

### 5.4 Direct dependency và transitive dependency

Version ghi trong declaration không luôn là version cuối cùng của mọi dependency bắc cầu. Cần phân biệt:

- Direct dependency: module mà ứng dụng khai báo.
- Transitive dependency: module do direct dependency kéo vào.
- Constraint/BOM: quy tắc tham gia chọn version.
- Resolved version: version cuối cùng build tool thực sự chọn.

Ví dụ spring-boot-starter-web kéo theo nhiều Spring/Jackson modules. Để biết version cuối, xem runtime dependency graph thay vì suy ra từ tên starter.

---

## 6. Quy trình nâng cấp an toàn

### Bước 1 — lập baseline

Ghi lại version hiện tại:

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration compileClasspath
~~~

Với Maven:

~~~bash
./mvnw --version
./mvnw help:effective-pom
./mvnw dependency:tree -Dscope=runtime
~~~

Ghi lại Boot plugin, BOM, Java, Gradle/Maven Wrapper, direct dependencies có version override và các dependency constraints. Không chỉ lưu build.gradle; cần lưu dependency graph đã resolve vì version thực tế có thể khác version được ghi trong declaration.

### Bước 2 — chọn release Boot đích và kiểm tra compatibility

Với ví dụ Spring Boot 3.3.13, tài liệu công bố:

| Thành phần | Yêu cầu/tương thích |
| --- | --- |
| Java | Tối thiểu Java 17; tương thích tới Java 23 |
| Spring Framework | 6.1.21 trở lên |
| Gradle | Gradle 7.x (7.5 or later) and 8.x |
| Maven | 3.6.3 or later |

Không suy rộng bảng này cho mọi Boot 3.x hoặc Boot 4.x. Mỗi release line có giới hạn riêng. Plugin bên thứ ba, annotation processor hoặc native tool có thể yêu cầu phiên bản cao hơn.

### Bước 3 — xác định chiến lược dependency management

Trả lời rõ:

- Gradle đang dùng io.spring.dependency-management hay native platform?
- Nếu dùng dependency-management plugin, BOM có tự theo version Boot plugin không?
- Nếu dùng native BOM, version platform được khai báo ở file nào?
- Maven đang dùng starter parent hay import BOM riêng?
- Có corporate platform/parent nào đang thêm constraints không?

Chỉ sau khi trả lời được mới chỉnh version.

### Bước 4 — nâng plugin và BOM đúng nơi

- Gradle dependency-management strategy: nâng Boot plugin và kiểm tra BOM tự import.
- Gradle native BOM strategy: cập nhật plugin và platform version theo release target.
- Maven starter parent: nâng parent version và review plugin/dependency management.
- Maven BOM import: nâng BOM version; cập nhật Maven plugin version riêng nếu cần.

Không thay đổi nhiều cơ chế quản lý version trong cùng một bước nếu không cần. Nếu muốn chuyển từ dependency-management plugin sang native BOM, hãy tách thành thay đổi có test riêng để dễ so sánh dependency graph.

### Bước 5 — xem dependency diff

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Maven:

~~~bash
./mvnw dependency:tree -Dscope=runtime -Dverbose
./mvnw help:effective-pom
~~~

Kiểm tra các version được chọn, đường dependency kéo chúng vào và lý do chọn. Đặc biệt chú ý direct version override đang làm lệch khỏi BOM.

### Bước 6 — nâng application dependencies riêng

Sau khi Boot plugin/BOM được ổn định:

- Thêm/bỏ starter theo tính năng.
- Nâng SDK không được BOM quản lý.
- Xem xét dependency override bắt buộc.
- Xóa version declaration không cần thiết nếu BOM đã quản lý và policy cho phép.
- Kiểm tra dependency scope: implementation, runtimeOnly, compileOnly, Maven provided, runtime và test.

### Bước 7 — xử lý thay đổi API/configuration

Compile errors sau khi nâng BOM có thể đến từ Spring Framework, Jackson, Hibernate hoặc thư viện khác. Đọc migration guide và release notes của dependency liên quan. Không hạ BOM ngay chỉ vì một lỗi compile nếu lỗi đến từ API đã thay đổi và có cách migration được hỗ trợ.

### Bước 8 — xác minh executable artifact

Gradle:

~~~bash
./gradlew clean check bootJar
java -jar build/libs/orders-service-1.0.0.jar
~~~

Maven:

~~~bash
./mvnw clean verify
java -jar target/orders-service-1.0.0.jar
~~~

Tên file tùy cấu hình project và version. Dùng đúng output path thực tế. Kiểm tra ứng dụng khởi động, health endpoint, kết nối DB, serialization, security filter và các luồng quan trọng.

### Bước 9 — kiểm tra container

Nếu production chạy container, build image từ đúng executable artifact đã test, ghi image digest và chạy smoke test trong cùng base image/JRE. Promote đúng image digest đã kiểm thử, tránh rebuild một artifact khác sau bước test.

---

## 7. Đọc dependency graph để xác định version cuối

### 7.1 Gradle dependencies và dependencyInsight

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

Nếu là single-project build, bỏ :app:. dependencyInsight cho biết module nào yêu cầu dependency, có bao nhiêu đường transitive, version nào được chọn và lý do chọn (conflict resolution, constraint, platform, force hoặc rule).

Nếu nâng BOM nhưng spring-core vẫn ở version cũ, kiểm tra direct dependency/constraint hoặc platform khác đang tham gia graph.

### 7.2 Maven dependency:tree

~~~bash
./mvnw dependency:tree -Dscope=runtime -Dverbose
./mvnw dependency:tree -Dincludes=org.springframework:spring-core
~~~

-Dverbose giúp nhìn node bị omitted do conflict mediation. Kết hợp với help:effective-pom để tìm version đến từ parent, BOM, profile hay dependency declaration.

### 7.3 Build file là đầu vào, dependency graph là kết quả

Nếu pom.xml import BOM 3.3.13 nhưng direct dependency khai báo Jackson version riêng, hoặc Gradle dùng platform nhưng constraint khác yêu cầu version cao hơn, version cuối phải được xác định từ dependency resolution output.

Không chỉ nhìn version trong source file. Khi review upgrade, cần so sánh dependency graph trước và sau.

---

## 8. Multi-project build

Một hệ thống có thể gồm:

~~~text
platform/
├── settings.gradle
├── build.gradle
├── orders-service/
│   └── build.gradle
├── billing-service/
│   └── build.gradle
└── shared-library/
    └── build.gradle
~~~

Không phải module nào cũng cần Spring Boot plugin. orders-service và billing-service là application có thể apply plugin; shared-library có thể chỉ cần java-library.

### 8.1 Khai báo plugin version ở root

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.13' apply false
}
~~~

Module application:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
}
~~~

Cách này đồng bộ plugin version giữa các application modules. Tránh apply Boot plugin cho mọi subproject nếu module không cần task/packaging của Boot.

### 8.2 Quản BOM ở một nơi

Nếu dùng native platform, có thể tạo convention plugin hoặc shared platform dependency để các application modules cùng import một BOM version. Nếu dùng dependency-management plugin, giữ chiến lược import BOM nhất quán và tránh module này dùng plugin trong khi module kia import BOM khác version mà không có lý do.

### 8.3 Shared library không nhất thiết phải dùng Boot BOM

Một Java library thuần có thể được dùng bởi nhiều ứng dụng với Boot release khác nhau. Cân nhắc library nên quản lý dependency API của chính nó bằng platform riêng hay để consumer application quản lý version thông qua BOM.

Không áp đặt một Boot BOM lên mọi module nếu module đó không phụ thuộc hệ sinh thái Spring Boot.

---

## 9. Dấu hiệu cho thấy đã nâng nhầm lớp

| Triệu chứng | Nguyên nhân có thể | Cần kiểm tra |
| --- | --- | --- |
| bootJar không tồn tại | Boot plugin chưa apply hoặc plugin resolution thất bại | plugins, plugin repositories, module build file |
| Starter báo thiếu version | BOM chưa được import vào configuration đang dùng | Dependency-management plugin/platform và scope |
| Nâng plugin làm nhiều thư viện đổi version | BOM tự theo plugin version | Dependency-management plugin và resolved graph |
| Nâng BOM nhưng task build không đổi | BOM chỉ quản dependency | Plugin version và plugin tasks |
| Maven có dependency versions nhưng không tạo executable JAR | Import BOM không cấu hình Maven plugin/repackage | spring-boot-maven-plugin và execution |
| Maven parent upgrade đổi compiler/plugin defaults | Parent quản cả dependency và plugin defaults | Effective POM và release notes |
| Dependency vẫn ở version cũ sau nâng BOM | Explicit version/constraint/another platform | dependencyInsight hoặc dependency:tree |
| Một SDK không có version sau bỏ version | SDK không được BOM quản lý | Dependency declaration/catalog/platform |
| Runtime lỗi dù compile pass | Runtime graph khác compile graph hoặc dependency scope sai | runtimeClasspath, archive contents |
| Boot plugin mới nhưng Gradle không tương thích | Gradle Wrapper quá cũ | System requirements của Boot release |

---

## 10. Lỗi cấu hình thường gặp

### 10.1 Đặt Gradle plugin vào dependencies

Sai mục đích:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-gradle-plugin:3.3.13'
}
~~~

Đây là khai báo library dependency trong application graph. Nó không apply Gradle plugin và không tự tạo task bootJar.

Cách đúng là apply plugin:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.13'
}
~~~

### 10.2 Nghĩ rằng import BOM sẽ thêm starter

Import spring-boot-dependencies không làm ứng dụng có Spring MVC. BOM chỉ quản version; phải khai báo spring-boot-starter-web nếu ứng dụng cần web stack.

### 10.3 Nâng plugin nhưng quên BOM strategy

Với dependency-management plugin, BOM tự theo plugin version. Với native BOM, version BOM được ghi riêng. Kiểm tra đúng chiến lược trước khi thay version; không suy đoán dựa vào tên file.

### 10.4 Import BOM nhưng quên Maven plugin

Khi dùng corporate parent và chỉ import BOM, Maven nhận dependency management nhưng không tự kế thừa plugin management/repackage execution của spring-boot-starter-parent. Nếu mục tiêu là executable JAR, cấu hình spring-boot-maven-plugin và execution repackage.

### 10.5 Dùng version override để che conflict

Một dòng version trực tiếp có thể làm build resolve được nhưng tạo bộ Spring modules lệch release train. Trước khi override, dùng dependencyInsight hoặc dependency:tree để xác định module nào kéo version khác và vì sao.

### 10.6 Dùng enforcedPlatform như cách mặc định

enforcedPlatform ép version của platform lên dependency graph. Nó có thể ảnh hưởng cả dependency bắc cầu mà library khác yêu cầu. Chỉ dùng khi có policy rõ ràng và test đủ.

### 10.7 Nâng plugin, Gradle Wrapper và JDK cùng lúc mà không có baseline

Khi nhiều lớp thay đổi cùng lúc, lỗi phát sinh khó quy nguyên nhân. Nếu không bắt buộc phải thay đồng thời, tách thay đổi build tool/JDK và thay đổi Boot plugin/BOM để có diff và test rõ hơn.

---

## 11. Checklist review Pull Request nâng cấp

### Version và nguồn quản lý

- [ ] Đã ghi version Boot hiện tại và version đích.
- [ ] Đã xác định Gradle dependency-management plugin hay native BOM support.
- [ ] Nếu dùng dependency-management plugin, đã hiểu BOM tự import theo Boot plugin version.
- [ ] Nếu dùng native BOM, đã cập nhật và review platform version riêng.
- [ ] Nếu dùng Maven, đã phân biệt starter parent với BOM import.
- [ ] Đã xác định plugin version/execution khi không dùng Spring Boot parent.
- [ ] Đã review direct dependency overrides, constraints và version catalog.
- [ ] Không có nhiều nguồn quản lý cùng một version mà không giải thích.

### Compatibility và verification

- [ ] JDK phù hợp với Boot release.
- [ ] Gradle/Maven Wrapper nằm trong version range được hỗ trợ.
- [ ] Plugin bên thứ ba tương thích.
- [ ] Đã đọc release notes và migration guide.
- [ ] Đã lưu runtime dependency tree trước/sau.
- [ ] Đã kiểm tra Spring Framework modules và các thư viện quan trọng.
- [ ] Các override dependency có rationale và test.
- [ ] clean check hoặc clean verify pass.
- [ ] Executable JAR/WAR được tạo và java -jar chạy được.
- [ ] Container smoke test pass nếu có deploy container.
- [ ] Đã ghi artifact/image digest được kiểm thử.

---

## 12. Bài thực hành

### A. Nhận diện đúng lớp version

Với từng thay đổi, xác định nó thuộc plugin, BOM hay application dependency:

1. Đổi org.springframework.boot Gradle plugin từ 3.2.x sang 3.3.13.
2. Đổi spring-boot-dependencies platform từ 3.2.x sang 3.3.13.
3. Thêm spring-boot-starter-validation.
4. Nâng com.acme:partner-sdk từ 4.2.0 lên 4.3.0.
5. Đổi Gradle Wrapper từ 7.x lên 8.x.
6. Đổi Java toolchain từ 17 lên 21.

Giải thích những thay đổi nào có thể làm dependency graph runtime đổi và những thay đổi nào chủ yếu ảnh hưởng build environment.

### B. Chuyển từ dependency-management plugin sang native BOM

1. Lưu runtime dependency tree trước chuyển đổi.
2. Ghi lại Boot plugin version và BOM thực tế.
3. Bỏ apply dependency-management plugin trong branch lab.
4. Import cùng BOM bằng platform(...).
5. Resolve lại dependency graph.
6. So sánh các version khác nhau và giải thích nguyên nhân.
7. Chạy tests và executable packaging.
8. Chỉ kết luận hai cách tương đương khi đã xác minh dependency graph và behavior cần thiết.

### C. Maven parent và BOM import

1. Tạo project Maven dùng spring-boot-starter-parent.
2. Xem help:effective-pom.
3. Chuyển sang corporate parent giả lập và import spring-boot-dependencies.
4. Thêm spring-boot-maven-plugin với version và repackage execution.
5. So sánh effective POM và artifact tạo ra.
6. Giải thích phần plugin management nào không còn được kế thừa từ Spring Boot parent.

### D. Tìm dependency override

1. Chạy dependencyInsight hoặc dependency:tree.
2. Chọn một module do BOM quản lý.
3. Thêm direct version override trên branch lab.
4. Quan sát version thực tế thay đổi.
5. Xóa override và xác minh BOM quản lý lại.
6. Ghi lý do vì sao override có thể làm bộ dependency lệch khỏi release train.

### E. Thiết kế quy trình nâng cấp

Viết một kế hoạch PR gồm Boot release đích, JDK/Gradle/Maven compatibility, plugin/BOM strategy, application dependency changes, dependency graph diff, test matrix, artifact/container verification và rollback plan.

Không ghi “upgrade thành công” chỉ vì build script không còn báo lỗi cấu hình.

---

## 13. Tài liệu tham khảo chính thức

- Spring Boot 3.3.13 — Gradle Plugin Getting Started: https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html
- Spring Boot 3.3.13 — Managing Dependencies with dependency-management plugin or native BOM support: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
- Spring Boot 3.3.13 — Gradle Plugin Reference: https://docs.spring.io/spring-boot/3.3/gradle-plugin/
- Spring Boot 3.3.13 — System Requirements: https://docs.spring.io/spring-boot/3.3/system-requirements.html
- Spring Boot 3.3.13 — Maven Plugin, parent POM and importing BOM without parent: https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html
- Spring Boot — Build Systems and Dependency Management: https://docs.spring.io/spring-boot/reference/using/build-systems.html
- Gradle — Platforms and BOM support: https://docs.gradle.org/current/userguide/platforms.html
- Gradle — Dependency Constraints: https://docs.gradle.org/current/userguide/dependency_constraints.html
- Gradle — Version Catalogs: https://docs.gradle.org/current/userguide/version_catalogs.html
- Gradle — Plugin Management: https://docs.gradle.org/current/userguide/plugins_intermediate.html
- Apache Maven — Dependency Management: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html

**Ghi nhớ:** Spring Boot Gradle plugin quản lý hành vi build và packaging; BOM quản lý version của dependency; application dependency xác định thư viện nào được đưa vào ứng dụng. Với Gradle dependency-management plugin, BOM mặc định tự theo Boot plugin version. Với native BOM hoặc Maven BOM import riêng, version BOM được khai báo riêng. Trước khi nâng, hãy xác định nguồn version, đọc dependency graph thực tế và kiểm chứng executable artifact.
