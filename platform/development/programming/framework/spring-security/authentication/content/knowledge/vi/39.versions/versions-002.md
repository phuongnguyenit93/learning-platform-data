# Quản lý bộ phiên bản tương thích bằng Spring Boot BOM

## 1. Vì sao một ứng dụng xác thực cần quản lý cả bộ phiên bản?

Một dự án Spring Security không chỉ chạy một JAR `spring-security-core`. Đăng nhập bằng form, HTTP Basic, JWT, OAuth2 Login, LDAP, SAML hoặc session thường kéo theo nhiều module Spring Security, Spring Framework, Jakarta Servlet, Jackson, thư viện logging, test và các Spring Boot starters.

Nếu mỗi dependency được khai báo một phiên bản độc lập, ứng dụng có thể biên dịch ở một nơi nhưng lỗi khi khởi động hoặc xác thực ở nơi khác:

- `NoSuchMethodError`: module được build với API khác bản runtime.
- `ClassNotFoundException` hoặc `NoClassDefFoundError`: class không có trong phiên bản đang được tải.
- `NoSuchBeanDefinitionException`: configuration hoặc auto-configuration thay đổi, có thể do version drift.
- `IllegalArgumentException` hoặc `BeanCreationException` trong security filter chain vì dependencies không đồng bộ.
- Unit test chạy được nhưng integration test đăng nhập thất bại do `spring-security-test` khác đời với các module runtime.
- Người phát triển copy API Spring Security 7 (ví dụ `@EnableMultiFactorAuthentication`) vào dự án dùng Spring Security 6.5, khiến IDE không tìm thấy class.

**Spring Boot BOM** giúp quản lý một **tập phiên bản đã được Spring Boot chọn và thử nghiệm cùng nhau**, giảm việc pin thủ công từng thư viện. Người học cần hiểu:

1. BOM là gì và khác starter/parent/plugin thế nào.
2. Maven dùng `spring-boot-starter-parent` hoặc import `spring-boot-dependencies` ra sao.
3. Gradle dùng plugin quản lý dependency hoặc native `platform(...)` như thế nào.
4. Cách xác nhận Spring Security core/web/config/test được resolve theo một bộ tương thích.
5. Vì sao BOM không loại bỏ nhu cầu kiểm compatibility, security patch và migration.
6. Cách nhận diện version drift qua `dependency:tree`, `dependencyInsight`, CI và smoke tests.

Bài minh họa bằng **Spring Boot 3.5.16 / Spring Security 6.5.11 / Spring Framework 6.2.19 / Java 17+** — các phiên bản do trang managed-dependencies chính thức của Spring Boot 3.5.16 công bố. Đây là **bộ ví dụ xác định**, không phải mệnh đề rằng chúng luôn là bản mới nhất. Khi tạo dự án sản xuất, hãy xem lại các bản phát hành còn được hỗ trợ, bản vá mới và yêu cầu hệ thống tại thời điểm triển khai.

## 2. BOM là gì?

**BOM** (Bill of Materials) trong hệ sinh thái Java/Maven thường là một POM có `packaging=pom` và phần `dependencyManagement` quy định phiên bản cho nhiều artifacts.

Coordinate của Spring Boot BOM:

~~~text
groupId:    org.springframework.boot
artifactId: spring-boot-dependencies
version:    3.5.16
type:       pom
scope:      import  (khi Maven import vào dependencyManagement)
~~~

Hãy hình dung:

~~~text
              spring-boot-dependencies:3.5.16
                         |
       +-----------------+-----------------+
       |                 |                 |
spring-security-*     spring-*          thư viện khác
   6.5.11              6.2.19           (Jackson, Tomcat,
                                       logging, testing...)
       |                 |                 |
       +-----------------+-----------------+
                         |
                Dependency graph ứng dụng
~~~

Trong cấu hình minh họa, BOM quản lý các module `spring-security-core`, `spring-security-web`, `spring-security-config`, `spring-security-test`, `spring-security-oauth2-client`, `spring-security-oauth2-resource-server` ... cùng nhánh Security 6.5.11.

**BOM không tự thêm các dependencies vào classpath.** Nó **chọn phiên bản khi một artifact được khai báo hoặc được kéo vào qua quan hệ transitive**. Ví dụ, import BOM mà không thêm `spring-boot-starter-security` **không tự bật Spring Security**, không tạo login page và không cấu hình authentication.

### 2.1. BOM, Starter, Parent và Build Plugin không giống nhau

| Thành phần | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| **BOM** | `spring-boot-dependencies` | Quản lý phiên bản các dependencies |
| **Starter** | `spring-boot-starter-security` | Khai báo một nhóm dependencies cần thiết cho tính năng |
| **Maven Parent** | `spring-boot-starter-parent` | Kế thừa BOM, dependency management, plugin management và build defaults |
| **Maven Plugin** | `spring-boot-maven-plugin` | Chạy/đóng gói ứng dụng; không tự là BOM |
| **Gradle Plugin** | `org.springframework.boot` | Cung cấp tasks/integration build của Boot; dependency management cần cơ chế phù hợp |
| **Gradle platform** | `platform("org.springframework.boot:spring-boot-dependencies:...")` | Import BOM vào resolution configuration |
| **Spring Security BOM** | `spring-security-bom` | Quản lý riêng các module Security, thường dùng khi không sử dụng Boot BOM hoặc theo chiến lược đặc biệt |

Đặt `spring-security-core` và `spring-security-web` là hai dependencies cùng một version không tương đương với BOM quản lý **cả graph**. Một graph còn có thể gồm Spring Framework, Reactor, Jackson, Spring Data, test engines và servlet container.

### 2.2. “Managed” không có nghĩa “cưỡng ép tất cả phiên bản”

Đặc biệt trong Gradle native `platform(...)`, BOM cung cấp **version constraints**; phiên bản thực tế vẫn có thể bị nâng bởi constraint khác hoặc dependency graph. Với Maven, explicit `<version>` và local `dependencyManagement` có thể thay kết quả. Vì vậy luôn **kiểm resolved dependency tree**, không chỉ đọc version trong POM/BOM.

**Phân biệt ba nơi:**

~~~text
DECLARED VERSION        Giá trị developer ghi trong POM/build.gradle
MANAGED VERSION         Giá trị được BOM hoặc dependency management cung cấp
RESOLVED VERSION        JAR cuối cùng build tool thực sự chọn
~~~

Một ứng dụng được coi là “đang dùng Spring Security X” theo nghĩa thực thi khi **resolved runtime classpath** phù hợp, không phải chỉ vì một dòng trong README ghi X.

## 3. Bộ ví dụ Spring Boot 3.5.16 tương thích

Trang managed dependency coordinates của **Spring Boot 3.5.16** cho các ví dụ cụ thể:

| Thành phần | Phiên bản trong BOM ví dụ | Vai trò |
| --- | --- | --- |
| Spring Boot starters | 3.5.16 | Auto-configuration và starter dependencies |
| Spring Security core/web/config | 6.5.11 | Authentication, authorization, filters, DSL |
| Spring Security test | 6.5.11 | MockMvc/security test helpers |
| Spring Security OAuth2 Client/Resource Server | 6.5.11 | OAuth2 login, JWT resource server |
| Spring Framework modules | 6.2.19 | Context, Beans, WebMVC, Servlet integration |
| Spring Boot Maven/Gradle plugin | Chọn cùng Boot release khi dùng | Build/run/package; không phải runtime library |

**Không tự suy** mọi artifact có tiền tố `spring-security` đều mang phiên bản 6.5.11: một số sản phẩm có version line độc lập, ví dụ Spring Authorization Server và các module tích hợp đặc thù. Luôn tra bảng managed coordinates theo **artifact ID chính xác**.

Spring Boot 4.0+ gắn với hệ Spring Framework 7 / Spring Security 7 và có breaking changes so với Boot 3.5 / Security 6.5. Không đổi riêng Security core từ 6.x lên 7.x bên trong Boot 3.x rồi mặc định rằng stack vẫn tương thích; đây là **major migration**, không phải cập nhật một patch JAR.

## 4. Maven: cách đơn giản nhất là spring-boot-starter-parent

Maven Parent thường là cách ít cấu hình nhất cho ứng dụng Boot.

### 4.1. pom.xml độc lập, có đủ BOM và dependencies

Tệp `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>boot-bom-auth-demo</artifactId>
    <version>1.0.0</version>
    <name>boot-bom-auth-demo</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

**Điểm quan trọng:**

- Chỉ **parent** pin Boot version `3.5.16`.
- Các dependencies được BOM quản lý nên **không có `<version>` ở từng dependency**.
- Parent cung cấp build defaults, dependency management và plugin management phù hợp; vì vậy `spring-boot-maven-plugin` cũng không cần ghi version riêng trong cấu hình trên.
- `<java.version>17</java.version>` nói về bytecode/toolchain của project, **không phải phiên bản Spring Security**.
- `spring-security-test` được dùng cho test; BOM quản lý đồng bộ với các Spring Security modules khác.
- `spring-boot-starter-security` chứa dependencies thích hợp cho security cơ bản; nếu cần OAuth2 Resource Server hay SAML, phải **thêm starter/module tương ứng**, BOM không tự bật chúng.

### 4.2. Parent đã kế thừa BOM như thế nào?

Mối quan hệ:

~~~text
POM dự án
    |
    +-- parent: spring-boot-starter-parent:3.5.16
              |
              +-- spring-boot-dependencies:3.5.16
                       |
                       +-- dependencyManagement
                       |      spring-security-core 6.5.11
                       |      spring-security-web  6.5.11
                       |      spring-security-test 6.5.11
                       |      spring-webmvc         6.2.19
                       |      ...
                       |
                       +-- properties cho managed versions
~~~

Khi Maven gặp:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nó dùng phiên bản được quản lý, **không dùng một phiên bản ngẫu nhiên** và không bắt developer nhớ phiên bản Spring Security nào tương ứng với Boot.

### 4.3. Tại sao dùng parent sẽ tiện hơn import BOM?

Parent đem thêm các defaults mà BOM import riêng **không** có đầy đủ: cấu hình Maven plugin, cấu hình compiler/encoding, resource filtering và repackage tasks. Nếu corporate project cho phép kế thừa parent Boot, chọn parent giảm công việc bảo trì build.

Nếu doanh nghiệp **phải dùng một parent POM riêng**, không thể khai báo hai Maven parents cùng lúc. Khi đó dùng import BOM theo mục tiếp theo.

## 5. Maven: import BOM khi dự án có parent riêng

Ví dụ dự án dùng `com.example.build:company-parent` nên không thể dùng `spring-boot-starter-parent` trực tiếp.

**Đây là fragment POM**, cần đặt trong POM thật có corporate parent/build plugins phù hợp:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
    <spring-boot.version>3.5.16</spring-boot.version>
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
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

**Khác biệt rất dễ bỏ sót:** import `spring-boot-dependencies` **chỉ** mang dependency management, không mang plugin management và tất cả parent defaults. Phải tự cấu hình/điều phối compiler, Surefire, Spring Boot Maven plugin và repackage nếu cần, theo corporate parent.

Ví dụ plugin build khi không dùng Boot parent:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>${spring-boot.version}</version>
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

Đây cũng là **fragment**, cần đối chiếu plugin management của parent doanh nghiệp để tránh khai báo trùng, đặc biệt nếu parent đã có quy trình package riêng.

### 5.1. Property override không giống nhau giữa parent và import

Khi dùng **Spring Boot parent**, có thể điều chỉnh phiên bản được quản lý bằng property phù hợp, chẳng hạn:

~~~xml
<!-- Mảnh ví dụ để nhận biết cách override, KHÔNG khuyến nghị tùy tiện. -->
<properties>
    <spring-security.version>6.5.11</spring-security.version>
</properties>
~~~

Nhưng khi **import BOM dưới `dependencyManagement`** mà không kế thừa parent Boot, khai báo property `spring-security.version` tại POM dự án **không tự thay property đã được nội suy trong imported BOM**. Nếu cần override, phải dùng dependency management entry tường minh hoặc chiến lược BOM/parent đã được build tool hỗ trợ, và kiểm effective POM.

**Khuyến nghị:** tránh override trừ khi có lý do chính thức (security advisory/compatibility test), vì đổi riêng một module có thể làm graph mất đồng bộ.

### 5.2. Khi có nhiều BOM

Doanh nghiệp có thể import Spring Cloud BOM, Spring Boot BOM, một corporate BOM và BOM của vendor khác. Đừng tin rằng “BOM import sau luôn thắng” trong mọi trường hợp.

Trong Maven, **direct management/parent precedence và thứ tự khai báo imported BOM** có thể quyết định phiên bản được chọn; riêng những coordinates được quản lý trùng nhau giữa imported BOMs, thứ tự import có quy tắc riêng. Để tránh sai, **xem effective POM và dependency tree**, sau đó có test bảo đảm modules cần đồng bộ không bị drift.

Nếu dùng **Spring Cloud**, phải chọn **release train được tài liệu Spring Cloud xác nhận tương thích với Boot line đang dùng**. Import Spring Cloud BOM không phải giấy phép nâng Boot tùy ý.

## 6. Maven: thực sự đang dùng phiên bản nào?

Dù đã có BOM, vẫn cần inspect **effective model** và **resolved graph**.

### 6.1. Các lệnh kiểm tra

Trong thư mục có `pom.xml`:

~~~bash
mvn -version
mvn help:effective-pom -Doutput=effective-pom.xml
mvn help:evaluate -Dexpression=spring-security.version -q -DforceStdout
mvn dependency:tree -Dincludes=org.springframework.security:*
mvn dependency:tree -Dincludes=org.springframework:*
mvn test
~~~

Giải thích:

- `mvn -version`: Maven/JDK mà build đang chạy; không dùng output này suy ra Security version.
- `help:effective-pom`: model đã merge parent, properties và dependency/plugin management.
- `help:evaluate`: với Boot parent, xem property Spring Security được quản lý; nếu dùng import BOM riêng, property ở POM hiện tại có thể không được expose như bạn nghĩ.
- `dependency:tree`: **đây là bằng chứng quan trọng** về resolved versions, transitive dependencies và mediation; có thể thấy các module `spring-security-*` thực sự trên classpath.
- `mvn test`: kiểm build+tests thực tế; chưa đủ nếu thiếu test login/API security quan trọng.

Trong shell có ký tự wildcard đặc biệt, có thể quote giá trị `-Dincludes=org.springframework.security:*`. Trên Windows PowerShell, dùng cú pháp quote phù hợp; mục tiêu không phải glob của filesystem mà là filter của Maven dependency plugin.

**Không commit `effective-pom.xml` tự tạo** nếu nó chứa secrets/build metadata hoặc không thuộc chính sách repo.

### 6.2. Cách đọc một dependency tree

Trích đoạn **minh họa**, không phải output build đã thực hiện:

~~~text
demo:boot-bom-auth-demo:jar:1.0.0
+- org.springframework.boot:spring-boot-starter-security:jar:3.5.16:compile
|  +- org.springframework.security:spring-security-config:jar:6.5.11:compile
|  \- org.springframework.security:spring-security-web:jar:6.5.11:compile
\- org.springframework.security:spring-security-test:jar:6.5.11:test
~~~

Còn `spring-security-core` thường là transitive dependency. Cấu trúc chính xác của cây phụ thuộc version và dependencies cụ thể, không cố định số dòng hoặc indentation.

Nếu thấy:

~~~text
spring-security-core:6.5.11
spring-security-web:6.4.3
spring-security-config:6.5.11
spring-security-test:6.5.11
~~~

đó là dấu hiệu **version skew** cần điều tra. Đừng “fix” bằng cách thêm `spring-security-core:6.4.3` cho khớp với web; hãy xác định **ai ép web xuống phiên bản sai** và khôi phục cách quản lý BOM thống nhất.

### 6.3. Kiểm build plugin và artifact runtime

BOM quản lý **library versions**, nhưng bản JAR runtime còn bị tác động bởi Maven plugins như compiler, surefire, shade và Spring Boot repackage. Với POM không dùng Boot parent, phải kiểm những plugin này được pin và tương thích.

Kiểm:

~~~bash
mvn clean verify
mvn dependency:tree
mvn help:effective-pom
~~~

Sau khi package, chạy ứng dụng từ **artifact được deploy** để phát hiện vấn đề duplicate/shaded JAR hoặc classpath khác ở container. Chỉ việc IDE hiển thị dependency version đúng chưa chứng minh image cuối cùng dùng đúng graph.

## 7. Gradle có hai cách quản lý BOM

Gradle dùng `build.gradle` (Groovy DSL) hoặc `build.gradle.kts` (Kotlin DSL). Với Spring Boot Gradle plugin, có hai hướng:

1. **`io.spring.dependency-management` plugin:** khi được apply cùng Boot plugin, plugin import BOM tương ứng và hỗ trợ property-based version override.
2. **Native Gradle `platform(...)`:** import BOM trực tiếp qua constraint của Gradle, thường đơn giản và nhanh; nhưng **không dùng property của BOM giống cách dependency-management plugin** để override.

Chọn **một chiến lược rõ ràng**, tránh áp nhiều mechanism trùng nhau không cần thiết.

### 7.1. Kotlin DSL với Gradle native platform

Tệp `build.gradle.kts` đầy đủ cho cùng ứng dụng demo:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
}

group = "demo"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    ))
    testImplementation(platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    ))

    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

**Ý nghĩa:**

- Boot Gradle plugin có cùng version `3.5.16`.
- `SpringBootPlugin.BOM_COORDINATES` cung cấp coordinate tương ứng với **version Boot plugin hiện hành**, tránh copy hai version strings có thể lệch.
- `platform(...)` đưa managed constraints vào Gradle configurations. Ở đây khai báo cả `implementation` và `testImplementation` để phạm vi test rõ ràng.
- Các dependencies managed **không ghi version**.
- Gradle Java toolchain dùng JDK 17+ đúng baseline.
- Không cần apply thêm `io.spring.dependency-management` trong ví dụ này.

Có thể thay `SpringBootPlugin.BOM_COORDINATES` bằng coordinate tường minh:

~~~kotlin
implementation(platform(
    "org.springframework.boot:spring-boot-dependencies:3.5.16"
))
~~~

Nhưng nếu plugin được nâng lên 3.5.x khác mà quên nâng chuỗi trên, graph có thể dùng **plugin version A, BOM version B**. Dùng constant giúp giảm sai lệch.

### 7.2. Groovy DSL tương đương (mảnh)

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    testImplementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là cấu hình **minh họa**, cần khai báo Java toolchain và JUnit Platform khi dùng với project thực. Kotlin DSL ở trên là ví dụ đầy đủ cho project demo.

### 7.3. Lựa chọn io.spring.dependency-management

Với Gradle plugin này, khi dùng cùng Spring Boot Gradle plugin, BOM được tự import:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

Đây là **mảnh build**, cần thêm Java toolchain/test dependencies nếu biến thành project runnable. **Không** copy đồng thời hai block quản lý BOM của mục 7.1 và mục này vào một build nếu chưa có thiết kế cụ thể.

Trong cách dùng dependency management plugin, các properties do Spring Boot BOM công bố như `spring-security.version` có thể được tùy chỉnh theo tài liệu Gradle plugin. Với native `platform(...)`, phải dùng Gradle constraints, resolution strategy hoặc cơ chế phù hợp để thay managed version; setting property POM đơn thuần sẽ không tự có hiệu lực.

### 7.4. platform so với enforcedPlatform

| Cách | Bản chất | Khi dùng |
| --- | --- | --- |
| `platform("group:artifact:version")` | Phiên bản trong BOM là **constraints/recommendations** | Mặc định hợp lý trong nhiều app |
| `enforcedPlatform("group:artifact:version")` | Ép constraints theo dạng mạnh hơn, có thể override versions khác | Khi thực sự cần strict alignment, đã phân tích ảnh hưởng |
| `io.spring.dependency-management` | Maven-like dependency management trong Gradle | Khi muốn dùng managed-version properties |
| Pin `implementation("...:6.5.11")` riêng lẻ | Explicit version, có thể ảnh hưởng resolution | Chỉ khi có lý do và đã test cả graph |

Theo tài liệu Gradle, `enforcedPlatform` còn có thể **xuất constraints mạnh theo dependency graph**, gây khó cho project khác consume **library** của bạn; không tự bật enforcedPlatform trong shared libraries nếu không hiểu hệ quả.

Native `platform` không luôn buộc runtime lấy đúng 100% version BOM nếu graph có các constraints/requests khác. **Kiểm resolved graph** là bước bắt buộc.

## 8. Gradle: xem kết quả resolution thay vì đoán

Trong project Kotlin/Groovy DSL có Gradle Wrapper, chạy:

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
.\gradlew.bat test
~~~

**Diễn giải:**

- `dependencies` hiển thị resolved version và dependency graph.
- `dependencyInsight` giải thích vì sao Gradle chọn phiên bản cho module, gồm lý do selection/constraints và ai yêu cầu nó.
- `testRuntimeClasspath` có thể khác `runtimeClasspath`, nên kiểm `spring-security-test` ở đúng scope.
- `--version` chỉ cho biết Gradle/JVM, không cho biết Security version runtime.
- Sau nâng version, kiểm lại cả `runtimeClasspath` và `testRuntimeClasspath`; Gradle có thể chọn version được constraint khác nâng lên.

## 9. Ví dụ Java 17+ chạy được: Spring Security xác thực bằng BOM-managed dependencies

Sử dụng **pom.xml ở mục 4** hoặc **build.gradle.kts ở mục 7.1**. File Java bên dưới dùng đúng những API Spring Security có trong nhánh 6.5 được Boot 3.5.16 quản lý.

Cấu trúc thư mục:

~~~text
boot-bom-auth-demo/
├── pom.xml                   (hoặc build.gradle.kts + settings.gradle.kts)
└── src/
    ├── main/java/demo/bom/BomAuthDemoApplication.java
    └── test/java/demo/bom/BomAuthDemoTests.java
~~~

Với Gradle tạo thêm `settings.gradle.kts`:

~~~kotlin
rootProject.name = "boot-bom-auth-demo"
~~~

### 9.1. BomAuthDemoApplication.java

~~~java
package demo.bom;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BomAuthDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BomAuthDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("lab-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @RestController
    static class Routes {

        @GetMapping("/health")
        String health() {
            return "ready";
        }

        @GetMapping("/me")
        String me(Authentication authentication) {
            return "hello:" + authentication.getName();
        }
    }
}
~~~

**Giải thích:**

1. `SpringApplication` thuộc Spring Boot.
2. `HttpSecurity` và `SecurityFilterChain` thuộc Spring Security config/web.
3. `UserDetailsService`, `User`, `Authentication` thuộc Spring Security core.
4. `BCryptPasswordEncoder` thuộc Spring Security crypto.
5. `httpBasic` yêu cầu caller cung cấp user/password; `/me` phải authenticated và `/health` public.
6. Các class đó đến từ nhiều JAR nhưng **Boot BOM đã lựa chọn versions phối hợp**.
7. Lab sử dụng user in-memory, không có database, và không đưa password rõ vào HTTP response; chỉ dùng HTTP local hoặc HTTPS khi test bên ngoài.

Đừng cấu hình `@EnableMultiFactorAuthentication` trong sample Boot 3.5/Security 6.5; class này thuộc Spring Security 7+, không có trong BOM ví dụ.

### 9.2. BomAuthDemoTests.java — kiểm tra integration

~~~java
package demo.bom;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BomAuthDemoTests {

    @Autowired
    MockMvc mvc;

    @Test
    void healthIsPublic() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ready"));
    }

    @Test
    void meRequiresAuthentication() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void correctHttpBasicAuthenticates() throws Exception {
        mvc.perform(get("/me").with(httpBasic("learner", "lab-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello:learner"));
    }

    @Test
    void badPasswordIsRejected() throws Exception {
        mvc.perform(get("/me").with(httpBasic("learner", "wrong")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

**Lưu ý về import static:** vì cần một import dài, Java cho phép xuống dòng sau từ khóa `import static` nhưng dễ nhầm khi copy; có thể viết gọn **một dòng** như sau thay cho hai dòng trên:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
~~~

Không giữ cả hai imports trùng nhau trong file thật. Trong mã ở trên, import dài được xuống dòng theo cú pháp Java (whitespace được cho phép giữa các token), vẫn là một import statement.

### 9.3. Chạy build

Với Maven:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Với Gradle:

~~~bash
./gradlew clean test
./gradlew bootRun
~~~

Khi dependencies đúng và Java 17+ có sẵn, **kết quả kỳ vọng** của bộ test:

~~~text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là **trích đoạn kết quả mong đợi cho Maven**, không phải kết quả đã chạy trên máy của người học. Gradle dùng định dạng báo cáo khác, ví dụ `BUILD SUCCESSFUL`.

Thử local HTTP Basic:

~~~bash
curl -i http://localhost:8080/health
curl -i --user learner:lab-password http://localhost:8080/me
curl -i --user learner:wrong http://localhost:8080/me
~~~

Kỳ vọng:

~~~text
GET /health                 -> HTTP 200, body: ready
GET /me với đúng Basic      -> HTTP 200, body: hello:learner
GET /me với sai Basic       -> HTTP 401
~~~

**Không** dùng HTTP Basic hoặc credentials lab trên mạng công cộng không có TLS; command line có thể lưu secrets trong shell history/process list.

## 10. Java 17 độc lập: phát hiện version skew ở các module

Khi đọc dependency tree, điều quan trọng không chỉ là “có Spring Security” mà còn là các module thuộc **cùng bộ được quản lý**. Demo sau mô phỏng thao tác rà soát. Nó không đọc Maven/Gradle graph thật; graph phải được xuất từ build tool.

Tạo file `SecurityVersionAlignmentDemo.java`:

~~~java
import java.util.List;

public class SecurityVersionAlignmentDemo {

    record Module(String artifactId, String version) {}

    static boolean allSameVersion(List<Module> modules) {
        if (modules.isEmpty()) {
            return true;
        }
        String expected = modules.get(0).version();
        return modules.stream()
            .allMatch(m -> expected.equals(m.version()));
    }

    public static void main(String[] args) {
        List<Module> aligned = List.of(
            new Module("spring-security-core", "6.5.11"),
            new Module("spring-security-web", "6.5.11"),
            new Module("spring-security-config", "6.5.11"),
            new Module("spring-security-test", "6.5.11")
        );

        List<Module> skewed = List.of(
            new Module("spring-security-core", "6.5.11"),
            new Module("spring-security-web", "6.4.3"),
            new Module("spring-security-config", "6.5.11")
        );

        System.out.println("aligned=" + allSameVersion(aligned));
        System.out.println("mixed=" + allSameVersion(skewed));
        System.out.println("artifactCount=" + aligned.size());
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac --release 17 SecurityVersionAlignmentDemo.java
java SecurityVersionAlignmentDemo
~~~

**Stdout chính xác:**

~~~text
aligned=true
mixed=false
artifactCount=4
~~~

Lưu ý: đây chỉ là **kiểm tra equality** trên các module Spring Security trong ví dụ. Trong đời thực, nhiều artifact Spring thuộc **version lines khác nhau theo thiết kế**, ví dụ Spring Framework 6.2.19 và Boot 3.5.16, nên **không** viết một rule bắt tất cả `org.springframework.*` dùng cùng số version.

Cũng không tự coi toàn bộ artifact có chữ `security` đều phải bằng 6.5.11: cần chọn **tập module nằm trong một BOM family** mà release notes/managed coordinates thực sự yêu cầu cùng version.

## 11. Nguyên tắc override version có kiểm soát

Khi phát hiện CVE hoặc lỗi thư viện, phản xạ thường thấy là pin:

~~~xml
<!-- PHẢN VÍ DỤ: pin tùy tiện một module từ dòng khác. -->
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-core</artifactId>
    <version>7.0.0</version>
</dependency>
~~~

**Không** làm vậy với project Boot 3.5/Security 6.5 khi chưa lên kế hoạch nâng major stack. Hậu quả có thể là core 7.0 đi với config/web 6.5, hoặc Security 7 kỳ vọng Spring Framework 7/Jackson mới hơn mà Boot 3.5 không cung cấp.

Thứ tự xử lý hợp lý:

1. Tìm phiên bản Boot **patch mới hơn trong cùng dòng hỗ trợ** đã quản lý bản sửa.
2. Nâng **Boot parent/Boot plugin cùng BOM**, sau đó kiểm dependency tree, smoke tests và regression security tests.
3. Nếu advisory yêu cầu nâng một module ngay nhưng Boot patch chưa có, xem hướng dẫn Spring Security và mức tương thích, ưu tiên override **cả Security BOM train** (trong phạm vi hỗ trợ), không chỉ core. Lưu lý do, ngày dự kiến xóa override.
4. Với upgrade lớn 3.x → 4.x, thực hiện migration theo từng bước, không dùng pin một JAR.
5. Chạy test login, OAuth/OIDC, JWT, CSRF, password encoding, LDAP/SAML và session ở những cơ chế dự án thực sự sử dụng.
6. Kiểm image triển khai, SBOM, dependency vulnerabilities và các bản plugin build, không chỉ POM.
7. Có rollback và giám sát sau deploy.

**Không dùng `latest.release`, `+` hoặc dynamic versions không kiểm soát** cho security-critical production dependencies; build phải tái lập được. BOM được pin theo một Boot release, còn upgrade là thay đổi được review/test.

### 11.1. Override cả train vẫn cần kiểm compatibility

Việc Maven property `spring-security.version` tồn tại không có nghĩa **mọi bản Spring Security tương lai** chạy tốt trên một Boot release cũ. Spring Security 7 có breaking changes; Spring Framework, Jackson, Servlet stack và Boot auto-configuration có thể cần nâng tương ứng.

“Có thể khai báo một version override” là một khả năng của build tool; “nó tương thích” là một **kết luận cần chứng minh bằng tài liệu và tests**.

### 11.2. Maven precedence và dependency convergence

Maven có nhiều nguồn version:

- Explicit version trên direct dependency.
- Local `dependencyManagement`.
- Parent inheritance.
- Imported BOMs, với quy tắc ưu tiên theo cấu trúc/khai báo.
- Transitive dependency version từ upstream POM.

Với graph phức tạp, dùng Maven Enforcer rules theo policy, ví dụ `dependencyConvergence` hoặc `requireUpperBoundDeps` (tùy use case), nhưng **đừng bật mà không review**: một số thư viện có nhiều đường phụ thuộc hợp lệ và rule có thể báo nhiều conflicts cần xử lý.

Không chỉ xóa tất cả `<version>` rồi mặc định đã đúng; library **không có trong BOM** vẫn cần version có chủ đích, chẳng hạn API của một nhà cung cấp ít dùng.

## 12. Spring Boot BOM so với Spring Security BOM

| Tình huống | Nên cân nhắc | Vì sao |
| --- | --- | --- |
| Ứng dụng Spring Boot bình thường | **Spring Boot BOM** | Quản lý cả Boot, Security, Framework và hệ thư viện liên quan |
| Ứng dụng không dùng Spring Boot | Spring Security BOM + Spring Framework BOM khi cần | Quản lý nhất quán các Security modules |
| Corporate Maven parent đã có | Import Spring Boot BOM | Không cần bỏ parent doanh nghiệp |
| Gradle với Spring Boot plugin | Dependency-management plugin hoặc native platform | Version constraints cho runtime/test dependencies |
| Build đa module | Một nguồn BOM version ở root/corporate convention | Tránh mỗi module tự chọn một stack |
| Dự án có Spring Cloud | Boot BOM + Spring Cloud BOM release train phù hợp | Cloud components có compatibility policy riêng |
| Migrate Boot 3 → 4 | Nâng stack có kiểm thử | Security 6 → 7 và Framework 6 → 7 có breaking changes |

**Không import thêm Spring Security BOM một cách máy móc vào ứng dụng đã dùng Spring Boot BOM**. Khi cần chiến lược override, hiểu rõ BOM precedence và audit resolved graph để tránh Security train bị thay ngoài ý muốn.

## 13. Khi nâng Spring Boot BOM, những gì cần kiểm trong authentication?

Một smoke test chỉ xác nhận ứng dụng startup có thể bỏ sót hàng loạt lỗi bảo mật. Trước và sau upgrade, kiểm các đường thực sự sử dụng:

### 13.1. Session-based form login

- [ ] GET protected khi anonymous chuyển đúng trang login.
- [ ] Login đúng/sai password cho đúng success/failure flow.
- [ ] CSRF token vẫn được yêu cầu cho unsafe requests.
- [ ] Session fixation protection, logout và session timeout đúng policy.
- [ ] Cookie `Secure`/`HttpOnly`/`SameSite` đúng trên public HTTPS ingress.
- [ ] Remember-me hoặc custom security context repository không bị thay hành vi bất ngờ.

### 13.2. REST/JWT/Bearer

- [ ] JWT signature/algorithm/JWK, `iss`, `aud`, `exp` được validate đúng.
- [ ] Authorities/scopes mapping và authorization matchers không bị thay.
- [ ] API trả 401/403 theo contract, không redirect form login ngoài ý muốn.
- [ ] Không log raw tokens/claims nhạy cảm khi có exception mới.
- [ ] CORS/CSRF được áp theo threat model thật, không tắt CSRF vì upgrade lỗi.

### 13.3. OAuth2/OIDC/SAML/LDAP

- [ ] OAuth2 Login callback, redirect URI, state/nonce và cookies còn hoạt động.
- [ ] OIDC issuer/JWK/userinfo validation, scopes và principal mapping đúng.
- [ ] SAML signature, destination, relay state và clocks đúng.
- [ ] LDAP/AD TLS, bind và role mapping không bị thay hành vi.
- [ ] Custom authentication providers hỗ trợ đúng token types và exception mapping.

### 13.4. API/DSL migration

Nếu nâng Security 6 → 7, đọc migration guide, đặc biệt những API bị đổi/xóa và các cơ chế serialization/trust boundary. Ví dụ `FactorGrantedAuthority`/`@EnableMultiFactorAuthentication` thuộc Security 7.0+; không giả định chúng có trong 6.5.

Boot 4 chuyển sang Spring Framework 7 và có những thay đổi về Jackson, starters, API requirements và auto-configuration; không chỉ tăng version string rồi bỏ qua compiler và integration tests.

## 14. CI/CD: giữ nhất quán khi cả nhóm cùng phát triển

Một quy trình CI tối thiểu:

~~~text
1. Checkout source + versioned Maven Wrapper / Gradle Wrapper
2. Xác minh JDK/toolchain và dependency repositories
3. Resolve graph từ một BOM/version duy nhất
4. Kiểm BOM precedence, dependency convergence/alignment
5. Build + unit tests + Spring Security integration tests
6. Scan vulnerabilities + tạo SBOM (nếu policy yêu cầu)
7. Package artifact/container
8. Verify runtime artifact and startup smoke tests
9. Deploy staging; chạy login/session/JWT/CSRF/OIDC regression
10. Review/approve production release, monitor và rollback policy
~~~

Các kiểm soát cụ thể:

- **One source of truth:** parent/BOM version được pin trong POM root hoặc build convention và được review qua pull request.
- **Dependency lockfile/verification:** dùng Maven/Gradle wrapper và cơ chế dependency locking/verification phù hợp.
- **Known-good graph:** lưu kết quả resolved dependency tree/SBOM trong build artifact được bảo vệ.
- **Security checks:** scan CVEs theo SBOM đã resolve, không chỉ khai báo dependencies.
- **Automated tests:** kiểm cả classpath không drift và hành vi authentication/authorization quan trọng.
- **Review overrides:** mọi version override có lý do, người chịu trách nhiệm, link advisory và thời hạn gỡ.
- **Repository safety:** không dùng untrusted artifact repositories hoặc dependency substitution không kiểm soát.
- **Build reproducibility:** không để dynamic versions làm build hôm nay khác build ngày mai khi source không đổi.

### 14.1. Quy trình nâng patch ví dụ

Giả sử đang dùng Boot `3.5.15` và muốn lên `3.5.16`:

1. Thay **một Boot parent/plugin version** ở nguồn quản lý chính.
2. Đảm bảo Gradle BOM constant/import theo cùng Boot version nếu dùng platform.
3. Chạy `dependency:tree` hoặc `dependencyInsight` để xem Security core/web/config/test theo graph mới.
4. Chạy unit/integration authentication tests.
5. Kiểm vulnerability report và release notes.
6. Đóng gói artifact, chạy startup smoke và E2E login ở staging.
7. Chỉ sau đó deploy; nếu regression, rollback cả build, không trộn các JAR cũ mới.

Đây là **ví dụ quy trình**, không ám chỉ 3.5.16 là bản vá cần thiết cho mọi project.

## 15. Phân tích lỗi thường gặp khi BOM không như mong đợi

| Hiện tượng | Nguyên nhân có thể | Cách chẩn đoán / khắc phục |
| --- | --- | --- |
| `spring-security-core` 6.5 nhưng `web` 6.4 | Pin riêng, BOM khác hoặc override | Dependency tree/insight, xóa pin sai |
| Boot plugin 3.5.x nhưng runtime dùng Boot dependencies 3.4.x | Gradle import BOM thủ công sai version | Dùng BOM_COORDINATES, kiểm constraints |
| Maven parent đúng nhưng JAR khác version | Direct `<version>` / local dependencyManagement | Kiểm effective POM + tree |
| Import BOM nhưng plugin version không được quản lý | BOM import không thay Maven plugin management | Pin/configure plugins tường minh |
| `ClassNotFoundException` sau copy mã Security 7 | BOM vẫn quản lý Security 6.5 | Dùng API đúng version hoặc migrate Boot 4/Security 7 |
| `NoSuchMethodError` runtime | Classpath drift hoặc jar shaded/packaged khác | In graph, inspect packaged artifact, kiểm transitive conflicts |
| `spring-security-test` helper không compile | Test dependency không được khai báo hoặc version skew | Add test module không version, kiểm testRuntimeClasspath |
| `Could not resolve version` | Không import BOM hoặc dependency ngoài BOM | Kiểm plugin/platform/dependencyManagement |
| Gradle platform bị nâng ngoài BOM | Version constraint khác thắng | `dependencyInsight` xác định lý do selection |
| Build success nhưng login fail | API/config/behavioral incompatibility | Integration tests trên filter chain thực |
| Spring Cloud lỗi sau nâng Boot | Release train không phù hợp | Tra compatibility matrix trước upgrade |
| CVE scanner vẫn thấy JAR cũ | Image build cache/shaded artifact hoặc graph cũ | Scan packaged artifact/SBOM |
| Maven property override không có tác dụng khi import BOM | Imported BOM không sử dụng project property như parent inheritance | Local managed entry có chủ đích, kiểm effective POM |
| Có hai BOM quản lý cùng tọa độ | Precedence và thứ tự imports | Rà soát BOMs, giảm duplication, kiểm resolved graph |
| Parent công ty xung đột compiler/plugin | BOM import không mang plugin defaults | Pin Maven plugins/toolchain theo chính sách |

## 16. Checklist thực hành

**Cấu hình**

- [ ] Dự án chọn một Spring Boot BOM version rõ ràng, có hỗ trợ.
- [ ] Maven dùng starter-parent hoặc import BOM đúng mục đích, không dùng hai parents.
- [ ] Dependencies managed bỏ version riêng.
- [ ] Gradle có dependency management plugin hoặc platform import đúng phạm vi.
- [ ] Boot plugin/build plugins và dependencies khớp release policy.
- [ ] Java 17+ và toolchain/compiler options phù hợp Boot version.
- [ ] Spring Security core/web/config/test được resolve theo train đúng.

**Kiểm tra**

- [ ] Maven effective POM và dependency tree đã được xem.
- [ ] Gradle dependencyInsight cho security modules và testRuntimeClasspath đã được xem.
- [ ] Có test authentication success/failure, authorization, CSRF và session hoặc JWT tùy app.
- [ ] Các module ngoài BOM được pin/test riêng.
- [ ] Mọi override được audit và có kế hoạch loại bỏ.
- [ ] CI scan SBOM của artifact cuối và kiểm release notes.
- [ ] Runtime image không trộn nhiều JAR cùng nhóm khác version.

**Nâng cấp**

- [ ] Ưu tiên nâng Boot patch đã kiểm tra hơn pin riêng một module.
- [ ] Với major migration, đọc Spring Security/Boot migration guide.
- [ ] Không bật API của Security 7 trong stack Security 6.x.
- [ ] Kiểm compatibility của Spring Cloud release train.
- [ ] Có staging E2E login, logout, OAuth/OIDC/JWT/SAML/LDAP tùy use case.
- [ ] Có rollback và giám sát sau deploy.

## 17. Câu hỏi tự kiểm tra

1. BOM có tự thêm `spring-boot-starter-security` vào classpath không?
2. Khác nhau giữa `spring-boot-dependencies`, `spring-boot-starter-parent` và `spring-boot-starter-security` là gì?
3. Vì sao dependency được BOM quản lý không cần `<version>` ở mỗi declaration?
4. Imported Maven BOM có tự cấu hình compiler/Surefire/repackage plugins như Boot parent không?
5. Vì sao không thể có hai Maven parents? Khi có company parent, nên làm gì?
6. Maven `dependency:tree` khác `help:effective-pom` ở điểm nào?
7. Gradle `platform(...)` khác `enforcedPlatform(...)` ra sao?
8. Vì sao version property của imported BOM không được override giống inherited parent?
9. Tại sao `spring-security-test` cũng phải nằm trong kiểm tra alignment?
10. Nếu Security core 6.5.11 và web 6.4.3, bước đầu tiên nên làm gì?
11. Tại sao Boot 3.5/Security 6.5 không tự có `@EnableMultiFactorAuthentication`?
12. Vì sao một CVE chưa được fix không đồng nghĩa phải pin Security core từ 6 lên 7?
13. Maven/Gradle có thể show managed version đúng nhưng packaged JAR sai không? Nêu một nguyên nhân.
14. BOM có thay thế integration tests cho JWT, CSRF, session hoặc SSO không?
15. Vì sao Spring Cloud BOM cần compatibility matrix với Spring Boot?
16. Cách dùng Gradle `dependencyInsight` để biết ai nâng một version ngoài BOM?
17. Nếu import nhiều BOM, vì sao cần kiểm effective graph?
18. Nâng một Boot patch phải kiểm điều gì trước khi triển khai production?

**Kết luận:** Spring Boot BOM là **nguồn quản lý phiên bản phối hợp** cho cả stack, không phải một thư viện chức năng và không tự bảo đảm mọi dependency luôn tương thích khi có override. Đối với Spring Security authentication, quy trình đáng tin là **chọn Boot release được hỗ trợ → dùng starter-parent/BOM hoặc Gradle platform → bỏ pin thủ công cho managed dependencies → kiểm resolved graph → kiểm thử đăng nhập/ủy quyền và runtime artifact → nâng cấp đồng bộ có kiểm soát**.

## 18. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Maven Plugin: Using the Starter Parent or importing BOM](https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html)
- [Spring Boot 3.5 — Gradle Plugin: Managing Dependencies](https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html)
- [Spring Boot 3.5 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Boot 3.5 — Managed Version Properties](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/properties.html)
- [Spring Security — Getting Spring Security](https://docs.spring.io/spring-security/reference/7.0/getting-spring-security.html)
- [Spring Security — Migration to 7.0](https://docs.spring.io/spring-security/reference/migration/)
- [Gradle — Platforms and BOM support](https://docs.gradle.org/current/userguide/platforms.html)
- [Maven — Introduction to Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
