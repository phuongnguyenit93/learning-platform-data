# Phân phối cấu hình chung bằng Maven parent POM hoặc Gradle convention plugin

## 1. Mục tiêu học tập và bài toán đa mô-đun

Trong repository Spring Boot có nhiều module, việc sao chép cấu hình Java, compiler, Surefire/JUnit, dependency versions, build plugins, publishing và quality gates vào từng module tạo ra sự **lệch cấu hình**: module A dùng Java 17, module B âm thầm đổi compiler version; module thư viện bị đóng gói như executable Boot JAR; dịch vụ mới thiếu test engine hoặc BOM. Một cách làm tốt là **định nghĩa chính sách build ở một nơi và áp dụng có chủ đích cho từng nhóm module**.

Hai công cụ giải bài toán này bằng cơ chế khác nhau:

- **Maven:** sử dụng **parent POM** để *kế thừa cấu hình* và có thể kết hợp **aggregator POM** để *xây dựng nhiều modules trong một reactor*.
- **Gradle:** sử dụng **convention plugin** (thường là *precompiled script plugin* ở `build-logic`) để *đóng gói và tái sử dụng cấu hình*; mỗi subproject **chủ động áp dụng plugin**.

Sau bài này, bạn có thể:

1. Phân biệt Maven `<parent>` với `<modules>`; Gradle `include(...)` với `includeBuild(...)`.
2. Dùng Maven `<properties>`, `<dependencyManagement>` và `<pluginManagement>` để chia sẻ cấu hình mà không tự kéo mọi dependency hoặc tự chạy mọi plugin.
3. Tạo **Maven multi-module Spring Boot project** gồm `shared` (library JAR) và `service` (Boot executable JAR) từ các POM hoàn chỉnh.
4. Tạo **Gradle multi-project build** tương đương, tổ chức build logic bằng một *included build* và các convention plugins.
5. Phân biệt **library module** với **application module** để không vô tình chạy `spring-boot:repackage` hoặc `bootJar` cho thư viện.
6. Hiểu cách Spring Boot BOM, Gradle platform và version catalog liên quan nhưng **không đồng nghĩa** với Maven parent hoặc Gradle convention plugin.
7. Kiểm tra cấu hình hiệu dụng, task/plugin đã áp dụng và dependency graph bằng CLI; khắc phục các lỗi cấu hình đa module.
8. Quyết định khi nào nên đặt policy ở root, parent trung gian hoặc convention plugin chuyên biệt; có quy trình thay đổi an toàn cho CI.

**Phạm vi ví dụ:** Java 17+, Maven 3.9+ hoặc Gradle 8.14.x, Spring Boot `3.5.16`. Đây là các mốc minh họa đã xác định, **không phải yêu cầu tất cả dự án phải dùng đúng chúng**. Với Spring Boot 3.5, tài liệu chính thức hỗ trợ Maven 3.6.3+ và các dòng Gradle 7.x/8.x đáp ứng phiên bản tối thiểu tương ứng. Khi nâng Gradle/Boot, đối chiếu tài liệu tương thích chính thức của **đúng release**, không suy luận chỉ từ số version.

## 2. Bản đồ khái niệm: shared policy khác dependency giữa modules

Một repository có:

~~~text
repository
├── shared     # Java library: lớp Greeter
└── service    # Spring Boot app: phụ thuộc shared
~~~

có ít nhất **hai quan hệ độc lập**:

1. **Quan hệ cấu hình build:** `shared` và `service` dùng chung Java release, encoding, plugin/test conventions.
2. **Quan hệ dependency mã nguồn/runtime:** `service` gọi `Greeter` từ `shared`.

Trong Maven, quan hệ (1) thường thể hiện bằng `<parent>`; quan hệ (2) bằng `<dependency>com.example:shared:...`. Trong Gradle, quan hệ (1) bằng `plugins { id("company.java-conventions") }`; quan hệ (2) bằng `implementation(project(":shared"))`.

Đừng lẫn:

- “Module có cùng parent” **không** có nghĩa các module tự nhìn thấy classes của nhau.
- “Module có cùng convention plugin” **không** tự tạo dependency Java giữa chúng.
- “Module được liệt kê trong reactor/settings” **không** có nghĩa project ứng dụng sẽ automatically include bytecode của mọi module khác.
- “Dependency version đã được quản lý” **không** có nghĩa dependency đã được khai báo trên classpath.

## 3. Maven: parent POM và aggregator POM không phải một khái niệm

### 3.1. Maven inheritance: child chỉ có một parent trực tiếp

Một Maven module chỉ có **một `<parent>` trực tiếp**:

~~~xml
<parent>
    <groupId>com.example</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

Maven kế thừa những phần tử được phép từ parent, có thể gồm `groupId`, `version`, `properties`, `dependencyManagement`, `pluginManagement`, một số plugin executions, repositories và nhiều build settings.

Không thể viết hai `<parent>` để vừa kế thừa `company-parent` vừa kế thừa `spring-boot-starter-parent`. Nếu tổ chức đã có parent riêng, thường **giữ parent đó và import Spring Boot BOM** dưới `dependencyManagement`, rồi chủ động quản lý Spring Boot Maven Plugin.

### 3.2. Maven aggregation: root biết các module nào được build

Một POM có packaging `pom` có thể khai báo:

~~~xml
<packaging>pom</packaging>

<modules>
    <module>shared</module>
    <module>service</module>
</modules>
~~~

`<modules>` cho Maven reactor biết những project nào tham gia khi chạy Maven tại root. **Aggregation không thay thế inheritance**: module hoàn toàn có thể thuộc reactor nhưng có parent khác. Ngược lại, child có thể kế thừa một parent ở repository mà không nằm trong `<modules>` của parent đó.

| Maven concept | Khai báo ở đâu? | Mục đích |
| --- | --- | --- |
| Parent inheritance | Child `<parent>` | Lấy cấu hình chung |
| Aggregation | Root `<modules>` | Build nhiều Maven projects cùng reactor |
| Inter-module dependency | Child `<dependencies>` | Dùng mã/thư viện của module khác |
| Dependency management | Parent/child `<dependencyManagement>` | Quản lý versions/scopes khi dependency được sử dụng |
| Plugin management | Parent/child `<build><pluginManagement>` | Quản lý plugin versions/configuration; không tự chạy goal tùy ý |
| Actual plugin execution | `<build><plugins>` và lifecycle bindings | Kích hoạt build plugin/goal phù hợp |

Một root POM **có thể đồng thời** là parent và aggregator như ví dụ mục 5, nhưng đó là **hai vai trò**. Trong mono-repo lớn, tổ chức có thể tách corporate parent thành artifact versioned ở Maven repository, còn root aggregator chỉ điều phối modules.

### 3.3. dependencyManagement khác dependencies

Ví dụ trong parent:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

BOM `spring-boot-dependencies` quản lý nhiều versions tương thích. Nhưng `<dependencyManagement>` **không tự đưa `spring-boot-starter` vào `shared` và `service`**. Module ứng dụng phải khai báo starter thực sự cần.

Nếu parent đặt starter vào **`<dependencies>`**, dependency có thể được **kế thừa bởi tất cả child**, kể cả thư viện không dùng Spring Boot. Vì vậy hãy quản lý versions tại `dependencyManagement` và giữ danh sách thư viện thực sự cần ở POM module. Điều này tránh phình compile/runtime classpath.

### 3.4. pluginManagement khác plugins

Trong parent:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>3.5.16</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Đoạn này **quản lý version**, nhưng **không tự làm `shared` và `service` đều chạy `repackage`**. `service` cần khai báo Spring Boot Maven Plugin trong `<build><plugins>` và bind goal `repackage` nếu corporate parent chưa cung cấp execution.

Ngược lại, nếu đặt plugin `spring-boot-maven-plugin` kèm execution trực tiếp trong **`<build><plugins>` của parent**, các child có thể kế thừa execution đó và library `shared` cũng bị áp dụng goal không phù hợp. Vì vậy trong parent chung, **ưu tiên pluginManagement**; mỗi loại module kích hoạt plugin khi cần.

Maven lifecycle vẫn tự gọi những plugin goals đã được bind mặc định theo packaging (ví dụ compiler/surefire cho `jar`), sử dụng version/config được quản lý nếu có. Quy tắc “pluginManagement không chạy gì” cần hiểu là **nó không tự kích hoạt một execution không được lifecycle hay plugin declaration gọi đến**.

## 4. Gradle: convention plugin là đơn vị chia sẻ policy

### 4.1. Project không tự kế thừa script của root như Maven parent

Trong một Gradle multi-project build:

~~~kotlin
// settings.gradle.kts
rootProject.name = "company-gradle-sample"
include("shared", "service")
~~~

`include(...)` tạo Gradle subprojects. Những module này **không có mô hình `<parent>` XML giống Maven**. Gradle có project hierarchy và root build, nhưng việc cấu hình Java toolchain, tests, compiler và plugin phải được áp dụng qua script/plugin thích hợp.

Cách làm cũ là sao chép nhiều `subprojects { ... }` vào root; cách này dễ tạo cross-project configuration coupling và gây khó khăn cho configuration cache/isolated projects. **Convention plugins** giúp chia sẻ có chọn lọc: library áp dụng Java convention; executable app áp dụng Java + Spring Boot conventions.

### 4.2. Precompiled script plugin

Một tệp:

~~~text
build-logic/src/main/kotlin/company.java-conventions.gradle.kts
~~~

được Gradle Kotlin DSL plugin biên dịch thành **plugin có ID `company.java-conventions`** (khi không khai báo package khác). Module sử dụng qua:

~~~kotlin
plugins {
    id("company.java-conventions")
}
~~~

**Điểm khác Maven parent:** module nào **không** áp dụng plugin này thì **không** tự nhận policy từ nó. Một convention plugin có thể áp dụng các core/community plugins, tạo tasks, set default values cho toolchain, cấu hình test tasks và khai báo các dependencies cần thiết.

### 4.3. buildSrc và build-logic included build

| Cách chia sẻ Gradle logic | Tính chất | Khi nào dùng |
| --- | --- | --- |
| Sao chép vào từng build script | Đơn giản lúc đầu, nhanh bị drift | Project rất nhỏ |
| Root `allprojects/subprojects` block | Áp dụng chéo nhiều modules, coupling lớn | Legacy builds; tránh phát triển thêm nếu có thể |
| `buildSrc` | Tự được Gradle biên dịch và đưa lên buildscript classpath | Prototype nhỏ, chưa muốn included build |
| Included build `build-logic` | Build riêng cho convention plugins, khai báo bằng `includeBuild` | Multi-project lớn, cấu trúc rõ, tác động thay đổi có phạm vi |
| Plugin binary được publish | Plugin versioned trong Maven/Plugin Portal nội bộ | Chia sẻ policy giữa nhiều repositories/teams |

Gradle khuyến nghị **included build** cho build logic phức tạp. Nếu làm settings plugin, cách include vào `pluginManagement` có quy tắc riêng và phải xảy ra sớm; ví dụ ở phần thực hành chỉ tạo **Project convention plugins**, không tạo Settings plugin.

### 4.4. include khác includeBuild

~~~kotlin
pluginManagement {
    includeBuild("build-logic")
}

rootProject.name = "company-gradle-sample"
include("shared", "service")
~~~

- `include("shared", "service")`: tạo **subprojects của chính multi-project build** để chứa source/module code.
- `includeBuild("build-logic")`: gắn một **Gradle build độc lập** làm nguồn plugin/build logic. `build-logic` không trở thành module runtime dependency `:build-logic` của app.
- `pluginManagement.includeBuild(...)`: giúp Gradle resolve plugin IDs ngay trong `plugins { }`, kể cả plugin chưa publish lên public repository. Thứ tự và vị trí block cần theo Gradle Settings DSL.

Một included build có `settings.gradle.kts` và `build.gradle.kts` **riêng**. Dependencies/repositories của `build-logic` không mặc nhiên được chia sẻ với runtime classpath của `service`.

## 5. Ví dụ Maven hoàn chỉnh: parent POM + library + Spring Boot service

### 5.1. Cây thư mục

Ví dụ dùng **Maven reactor** ở root, gồm hai modules thực sự có dependency với nhau:

~~~text
company-maven-sample/
├── pom.xml                              # Parent + aggregator
├── shared/
│   ├── pom.xml
│   └── src/main/java/com/example/shared/
│       └── Greeter.java
└── service/
    ├── pom.xml
    ├── src/main/java/com/example/service/
    │   └── ServiceApplication.java
    └── src/test/java/com/example/service/
        └── ServiceApplicationTests.java
~~~

Ví dụ dùng **Spring Boot starter cơ bản**, không dùng web server/database, nên việc kiểm tra stdout không phụ thuộc cổng 8080. Cùng các Java source ở đây sẽ được dùng lại trong project Gradle tương đương ở mục 7.

### 5.2. Root pom.xml — cấu hình chung

Tạo `company-maven-sample/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>shared</module>
        <module>service</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.14.0</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.5</version>
                </plugin>
                <plugin>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-maven-plugin</artifactId>
                    <version>${spring-boot.version}</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

**Maven property `${spring-boot.version}`** được nội suy từ `<properties>`. Chỉ version BOM và Boot Maven Plugin được tập trung vào một property; những plugin Maven khác có version tường minh theo policy.

Tại root, cần chú ý:

- `<packaging>pom</packaging>` giúp root vừa là parent vừa aggregate modules.
- `<modules>` chỉ định thứ tự danh sách, nhưng **Maven reactor cũng xét quan hệ dependencies để tính build order**. `service` phụ thuộc `shared` nên Maven build `shared` trước `service` khi cần.
- `<dependencyManagement>` nhập Spring Boot BOM, **không** làm cả hai module phụ thuộc tất cả Spring libraries.
- `<pluginManagement>` thống nhất compiler, Surefire và Boot Maven Plugin versions, nhưng Boot `repackage` **không tự được kích hoạt** trên library.
- `maven.compiler.release=17` áp dụng cho compiler plugin được lifecycle gọi ở các module Java.
- Không đặt `<dependencies><dependency>spring-boot-starter...</dependency>` tại parent, vì library `shared` không cần Spring Boot runtime.

### 5.3. shared/pom.xml — JAR thư viện

Tạo `company-maven-sample/shared/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>company-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>shared</artifactId>
    <packaging>jar</packaging>
</project>
~~~

Module này kế thừa `groupId`, `version`, encoding, Java release và plugin management. Nó **không** khai báo Spring Boot starter hay Boot Maven Plugin. Kết quả thường là thin/library JAR như `shared/target/shared-1.0.0-SNAPSHOT.jar`.

### 5.4. shared/Greeter.java — Java thuần

Tạo `shared/src/main/java/com/example/shared/Greeter.java`:

~~~java
package com.example.shared;

public final class Greeter {

    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

`Greeter` là lớp public Java 17 hợp lệ, không cần Spring annotation. File này tự biên dịch được bằng JDK:

~~~bash
javac -d /tmp/greeter-classes \
  shared/src/main/java/com/example/shared/Greeter.java
~~~

Lệnh ví dụ dành cho Linux/macOS, giả định có JDK và quyền tạo thư mục `/tmp/greeter-classes`. Nó không tạo stdout khi compile thành công. Trong project đa mô-đun, **ưu tiên dùng Maven/Gradle build**, vì công cụ build chịu trách nhiệm classpath, compiler flags và kết quả đóng gói.

### 5.5. service/pom.xml — ứng dụng Spring Boot

Tạo `company-maven-sample/service/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>company-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>service</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>shared</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
</project>
~~~

Lưu ý:

1. `shared` là một **dependency có version** (`${project.version}`) của `service`, không phải “module cùng parent nên tự thấy nhau”.
2. Hai Spring Boot starters **không ghi version**, vì BOM đã được parent nhập vào dependency management.
3. Boot Maven Plugin **không ghi version ở child** vì parent quản lý trong `pluginManagement`.
4. `repackage` chỉ khai báo **ở `service`**; `shared` không bị biến thành executable Boot JAR.
5. Nếu không kế thừa `spring-boot-starter-parent`, đừng mặc định execution `repackage` có sẵn. Cần bind nó như POM trên.

### 5.6. ServiceApplication.java — sử dụng library bean

Tạo `service/src/main/java/com/example/service/ServiceApplication.java`:

~~~java
package com.example.service;

import com.example.shared.Greeter;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServiceApplication.class, args);
    }

    @Bean
    Greeter greeter() {
        return new Greeter();
    }

    @Bean
    ApplicationRunner printGreeting(Greeter greeter) {
        return args -> System.out.println(greeter.greet("team"));
    }
}
~~~

Đây là một file Java hoàn chỉnh trong project đã có Spring Boot và module `shared` trên classpath. `Greeter` thuộc package `com.example.shared` khác package của Spring Boot app, nên ví dụ **đăng ký nó qua một `@Bean` rõ ràng**; không phụ thuộc việc component scanning tự phát hiện class Java thuần.

**Dòng do ứng dụng in ra** sau khi Spring context khởi tạo là:

~~~text
Hello, team!
~~~

Spring Boot có thể in thêm startup logs, nên dòng này là output của `ApplicationRunner` chứ không phải toàn bộ stdout bất biến.

### 5.7. ServiceApplicationTests.java — test Spring context

Tạo `service/src/test/java/com/example/service/ServiceApplicationTests.java`:

~~~java
package com.example.service;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ServiceApplicationTests {

    @Test
    void contextLoads() {
        // Test pass khi Spring ApplicationContext khởi tạo được.
    }
}
~~~

Surefire được parent quản lý version và JUnit Jupiter/Boot testing dependencies do `spring-boot-starter-test` cung cấp. `@SpringBootTest` giúp kiểm cấu hình context, nhưng test này không phải integration test mọi endpoint hoặc service bên ngoài. Vì ứng dụng ví dụ không có Web starter, không chạy HTTP server và không cần port.

### 5.8. Build và chạy Maven reactor

Tại `company-maven-sample/`, nơi có root POM:

~~~bash
java -version
mvn -version
mvn clean verify
java -jar service/target/service-1.0.0-SNAPSHOT.jar
~~~

Nếu project có Maven Wrapper được sinh hợp lệ, dùng `./mvnw` trên Linux/macOS hoặc `.\mvnw.cmd` trên Windows PowerShell. **Ví dụ cây file tự tạo không mặc định có Wrapper**, nên lệnh `mvn` là đúng khi Maven đã được cài.

Lệnh riêng module có tự build các reactor dependencies:

~~~bash
mvn -pl service -am clean package
~~~

- `-pl service` chỉ chọn module `service` trong reactor.
- `-am` (also make) cho phép Maven build thêm những reactor projects mà `service` cần, cụ thể `shared`.
- Nếu bạn đi vào thư mục `service` rồi chạy `mvn package` mà `shared` chưa được build/install vào local repository, Maven có thể **không resolve được dependency `com.example:shared`**. Đó là lỗi phạm vi reactor/dependency resolution, không phải lỗi Spring Boot.

**Artifact cuối:** `shared` tạo thin JAR. `service` tạo Boot executable JAR nhờ `repackage`, trong đó dependency `shared-1.0.0-SNAPSHOT.jar` thường có mặt dưới `BOOT-INF/lib/`. Khi thực hiện `java -jar`, Boot Loader đọc nested dependencies và Spring app in `Hello, team!`.

## 6. Kiểm chứng Maven đã kế thừa đúng cấu hình

### 6.1. Effective POM

Kiểm tra riêng `service`:

~~~bash
mvn -pl service help:effective-pom
~~~

Trong output, tìm:

- `parent = com.example:company-parent:1.0.0-SNAPSHOT`.
- `maven.compiler.release=17` hoặc compiler effective configuration tương đương.
- `spring-boot-dependencies` đã đóng góp managed dependencies.
- `maven-compiler-plugin` và `maven-surefire-plugin` nhận đúng versions từ parent management.
- `spring-boot-maven-plugin` có version và execution `repackage` trong `service`.

Lệnh `help:effective-pom` không chứng minh artifact runtime chạy được, nhưng nó cho biết cấu hình sau inheritance và profiles. Đọc effective POM của `shared` để xác nhận **không** có Boot `repackage` execution áp vào module library.

### 6.2. Dependency tree và reactor order

~~~bash
mvn -pl service dependency:tree
mvn -pl service dependency:tree -Dincludes=com.example:shared
mvn -pl service -am package
~~~

`dependency:tree` cho biết module `service` thật sự phụ thuộc `shared` với version nào. Reactor sẽ phải build `shared` trước khi đóng gói `service` nếu quan hệ dependency như POM mẫu.

Đừng suy ra rằng thứ tự `<modules>` là thứ tự build duy nhất; Maven xét **các quan hệ dependency thực tế**, ví dụ nếu `service` đứng trước `shared` trong danh sách mà phụ thuộc `shared` thì Maven vẫn cần sắp xếp cho hợp lệ.

### 6.3. Phân biệt thin library và Boot executable JAR

~~~bash
jar tf shared/target/shared-1.0.0-SNAPSHOT.jar
jar tf service/target/service-1.0.0-SNAPSHOT.jar
~~~

Trong thin library JAR, tìm `com/example/shared/Greeter.class` tại root package path. Trong Boot executable JAR, tìm:

~~~text
BOOT-INF/classes/com/example/service/ServiceApplication.class
BOOT-INF/lib/shared-1.0.0-SNAPSHOT.jar
org/springframework/boot/loader/launch/JarLauncher.class
~~~

Các version filenames khác phụ thuộc build thực tế. **Nếu `shared` có `BOOT-INF/classes` và Boot Loader**, có thể bạn đã vô tình bind `repackage` ở parent hoặc library module, điều này thường sai khi module cần được Java compiler của `service` tiêu thụ như thư viện thông thường.

## 7. Ví dụ Gradle hoàn chỉnh: build-logic + hai convention plugins

Ví dụ này dùng **Gradle Kotlin DSL** và Spring Boot Gradle Plugin. Khác Maven, module không kế thừa parent POM. Cấu hình chung được **biên dịch thành plugins** từ included build `build-logic`.

### 7.1. Cấu trúc repository

~~~text
company-gradle-sample/
├── settings.gradle.kts
├── build-logic/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/main/kotlin/
│       ├── company.java-conventions.gradle.kts
│       └── company.boot-app.gradle.kts
├── shared/
│   ├── build.gradle.kts
│   └── src/main/java/com/example/shared/
│       └── Greeter.java
└── service/
    ├── build.gradle.kts
    ├── src/main/java/com/example/service/
    │   └── ServiceApplication.java
    └── src/test/java/com/example/service/
        └── ServiceApplicationTests.java
~~~

Sử dụng **chính ba Java source files** ở mục 5.4, 5.6 và 5.7. Các file đó độc lập với Maven API; Spring Boot dependency và JUnit sẽ do Gradle quản lý. Cây ví dụ tự viết không liệt kê Gradle Wrapper, nhưng trong dự án thật nên tạo và commit các file `gradlew`/`gradlew.bat` và `gradle/wrapper/*`.

### 7.2. Root settings.gradle.kts — plugin resolution và modules

Tạo `company-gradle-sample/settings.gradle.kts`:

~~~kotlin
pluginManagement {
    includeBuild("build-logic")
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = "company-gradle-sample"
include("shared", "service")
~~~

**Giải thích chính xác:**

- `pluginManagement.includeBuild("build-logic")` cho phép các `plugins { id("company...") }` ở subproject resolve plugin chưa publish.
- `pluginManagement.repositories` dùng giải quyết Gradle plugins và plugin markers.
- `dependencyResolutionManagement.repositories` dùng cho **application/library dependencies** trong root build.
- `include("shared", "service")` tạo các subprojects Java.
- Không khai báo `include("build-logic")`: đó **không** là module code của ứng dụng, mà là included build có vòng đời và build scripts riêng.

### 7.3. build-logic/settings.gradle.kts

Tạo `build-logic/settings.gradle.kts`:

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = "build-logic"
~~~

Included build tự có settings; root main build `dependencyResolutionManagement` **không mặc nhiên cấu hình repositories cho build-logic**. Đây là lý do tệp build-logic tiếp theo cũng định nghĩa repositories cần thiết.

### 7.4. build-logic/build.gradle.kts

~~~kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}

dependencies {
    implementation(
        "org.springframework.boot:spring-boot-gradle-plugin:3.5.16"
    )
}
~~~

`kotlin-dsl` là core Gradle plugin dùng để biên dịch precompiled Kotlin DSL script plugins. `spring-boot-gradle-plugin` nằm trên **plugin implementation classpath của build-logic**, để file convention `company.boot-app.gradle.kts` có thể apply `org.springframework.boot` **không khai báo lại version** trong chính precompiled script.

**Lưu ý quan trọng từ tài liệu Gradle:** precompiled script plugin **không hỗ trợ** cú pháp `version "..."` hoặc `apply false` trong block `plugins { }` của script. Version community/external plugin phải đến từ **dependency của build-logic**, như file trên. Không đặt `id("org.springframework.boot") version "3.5.16"` bên trong `company.boot-app.gradle.kts`.

### 7.5. Java convention plugin: company.java-conventions.gradle.kts

Tạo `build-logic/src/main/kotlin/company.java-conventions.gradle.kts`:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test

plugins {
    `java-library`
}

group = "com.example"
version = "1.0.0-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

Khi module áp dụng `company.java-conventions`, nó nhận:

- `java-library` plugin (bao gồm Java compilation, JAR và dependency configurations).
- Java **toolchain** mục tiêu 17 cho tasks hỗ trợ.
- Compiler encoding UTF-8 và `--release 17`.
- `Test` tasks dùng JUnit Platform.
- Group/version chung dùng để đặt tọa độ artifacts.

Đây là **policy của ví dụ**, không phải công thức duy nhất: với tổ chức đa sản phẩm, hãy tránh hard-code `group/version` chung nếu modules cần versioning riêng. Có thể dùng Gradle properties/version catalogs hoặc extension conventions, và để từng module chủ động khai báo exceptions có lý do.

**Không thêm `org.springframework.boot` vào Java convention này**, vì library `shared` không phải executable app. Cũng không thêm Spring Boot starters vào mọi Java module chỉ vì những service modules đang dùng Spring Boot.

### 7.6. Boot convention plugin: company.boot-app.gradle.kts

Tạo `build-logic/src/main/kotlin/company.boot-app.gradle.kts`:

~~~kotlin
plugins {
    java
    id("org.springframework.boot")
}

dependencies {
    implementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
    )
    testImplementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
    )
}
~~~

Plugin `company.boot-app` mang theo:

- Spring Boot Gradle Plugin (version được quản lý qua `build-logic/build.gradle.kts`).
- Java plugin để Boot nhận diện project Java và tạo task `bootJar`.
- Spring Boot BOM ở dạng **Gradle native platform** cho production và test dependencies. Đây là cơ chế quản lý version, **không** tự thêm starter.

Vì file này được precompile và **áp dụng `java` ở cùng script**, các dependency configurations như `implementation` và `testImplementation` có thể dùng trong Kotlin DSL của script. `company.java-conventions` cũng áp dụng `java-library` (bao gồm Java plugin); Gradle plugin application cùng ID/type có tính idempotent, nên không tự tạo hai bộ Java compiler tasks.

BOM trên `implementation` đã tham gia nhiều classpaths liên quan; việc khai báo thêm trên `testImplementation` trong ví dụ khiến ý định quản lý test dependencies rõ ràng, tránh phụ thuộc vào cách tổ chức configurations khác ở project tùy biến.

**Cần phân biệt:** Gradle `platform` nhận BOM như những dependency version constraints. Không giả định Gradle native BOM ép mọi version bất kể conflict; Gradle có cơ chế version selection của nó. Nếu tổ chức cần giới hạn version cứng, cần giải pháp constraints/strictly/enforcedPlatform có đánh giá ảnh hưởng tới consumers.

### 7.7. shared/build.gradle.kts — chỉ áp dụng Java convention

~~~kotlin
plugins {
    id("company.java-conventions")
}
~~~

`shared` không áp dụng `company.boot-app` nên **không có task `bootJar` từ Boot plugin**, không import Boot BOM trừ khi có yêu cầu khác và chỉ tạo JAR Java library thông thường.

File `shared/src/main/java/com/example/shared/Greeter.java` giống mục 5.4. Gradle không bắt buộc dùng Spring Boot dependencies để compile Java source đó.

### 7.8. service/build.gradle.kts — áp dụng cả hai conventions

~~~kotlin
plugins {
    id("company.java-conventions")
    id("company.boot-app")
}

dependencies {
    implementation(project(":shared"))
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
~~~

Các dependencies Spring Boot không ghi version vì `company.boot-app` đã khai báo BOM platform. `implementation(project(":shared"))` là **dependency giữa modules** — không phải chỉ vì áp dụng cùng convention plugin.

`testRuntimeOnly("org.junit.platform:junit-platform-launcher")` giúp test runtime có launcher theo khuyến nghị của Gradle/JUnit hiện đại; version có thể được BOM quản lý. `company.java-conventions` đã bật `useJUnitPlatform()`, nên `@Test` từ JUnit Jupiter được phát hiện. Không cần cài Spring Boot plugin vào `shared`.

Với service này, Spring Boot plugin thấy Java plugin và cung cấp `bootJar`. Trong những dòng Boot 3.x, một plain JAR task có thể vẫn tồn tại với classifier khác (ví dụ `plain`); **artifact ứng dụng cần triển khai là output `bootJar`**, không tự lấy đại bất kỳ JAR nào trong `build/libs`.

### 7.9. Build và chạy Gradle

Dùng Gradle Wrapper được tạo/cập nhật và commit đúng cho project:

~~~bash
./gradlew clean build
./gradlew :service:bootJar
java -jar service/build/libs/service-1.0.0-SNAPSHOT.jar
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat clean build
.\gradlew.bat :service:bootJar
java -jar .\service\build\libs\service-1.0.0-SNAPSHOT.jar
~~~

Nếu ví dụ tự tạo **chưa có Wrapper**, dùng `gradle clean build` và `gradle :service:bootJar` với một Gradle release tương thích. Boot 3.5.16 cần Java 17+ và Gradle release phù hợp theo tài liệu Spring Boot 3.5; ví dụ chọn **Gradle 8.14.x**, không đổi sang Gradle 9 chỉ vì tài liệu Gradle hiện tại đã nói đến 9.x.

**Dòng do ứng dụng in:** `Hello, team!`, cùng business logic như Maven demo. Không đảm bảo toàn bộ stdout giống Maven vì Gradle/Maven không chạy lúc `java -jar` và Boot log format phụ thuộc môi trường.

### 7.10. Kiểm tra Gradle cấu hình và dependency resolution

~~~bash
./gradlew projects
./gradlew :shared:tasks --all
./gradlew :service:tasks --all
./gradlew :service:dependencies --configuration runtimeClasspath
./gradlew :service:dependencyInsight \
  --dependency spring-boot-starter \
  --configuration runtimeClasspath
~~~

`projects` cho thấy subprojects `shared` và `service`. `tasks` cho thấy `bootJar` ở `service`, nhưng **không nên** có `bootJar` ở `shared` vì shared không áp dụng Boot convention. `dependencies` và `dependencyInsight` hiển thị versions đã resolve sau BOM platform, constraints và transitive dependencies.

Thư mục `build-logic` là **included build**, không nhất thiết hiển thị như một subproject `:build-logic`; điều đó không phải lỗi. Nếu `Plugin [id: 'company...'] was not found`, hãy kiểm `pluginManagement.includeBuild(...)`, tên script, file path và build-logic compilation trước khi sửa application code.

### 7.11. Kiểm tra JAR library và Boot JAR

~~~bash
./gradlew :shared:jar :service:bootJar
jar tf shared/build/libs/shared-1.0.0-SNAPSHOT.jar
jar tf service/build/libs/service-1.0.0-SNAPSHOT.jar
~~~

Trong thin library JAR, class `com/example/shared/Greeter.class` nằm ở root archive. Trong Boot executable JAR, ứng dụng nằm ở `BOOT-INF/classes` và dependency shared thường nằm tại `BOOT-INF/lib/shared-1.0.0-SNAPSHOT.jar`, cùng các Spring Boot runtime libraries.

Nếu output name khác do `archiveBaseName`, `archiveClassifier` hoặc `version` đã được override, dùng **đường dẫn thực tế trong `build/libs`**, không dựa vào tên ví dụ.

## 8. So sánh cùng một chính sách giữa Maven và Gradle

| Mong muốn chung | Maven parent/aggregator | Gradle convention plugin/included build |
| --- | --- | --- |
| Chọn Java release 17 | Parent `maven.compiler.release` + Compiler Plugin | Java toolchain + `JavaCompile.options.release` trong Java convention |
| UTF-8 | Parent `project.build.sourceEncoding` | `JavaCompile.options.encoding` |
| JUnit 5 | Parent Surefire version; module khai báo test dependency | Java convention `useJUnitPlatform()`; module khai báo test deps |
| Quản lý Spring Boot versions | Parent `dependencyManagement` import Boot BOM | Boot convention `platform("...spring-boot-dependencies...")` |
| Quản lý version Boot build plugin | Parent `pluginManagement` | Dependency `spring-boot-gradle-plugin` của `build-logic` |
| Kích hoạt executable packaging | Chỉ `service` khai báo plugin + goal `repackage` | Chỉ `service` áp dụng `company.boot-app` → `bootJar` |
| Tạo library JAR | `shared` packaging `jar`, không `repackage` | `shared` áp dụng Java convention, task `jar` |
| Xác định modules | Root `<modules>` | Root `settings.gradle.kts include(...)` |
| Dependency giữa modules | `<dependency>shared</dependency>` với GAV | `implementation(project(":shared"))` |
| Chia sẻ logic giữa repositories | Parent POM publish vào Maven repository | Publish binary convention plugin hoặc dùng included build/versioned plugin |
| Kiểm tra cấu hình hiệu dụng | `help:effective-pom`, `dependency:tree` | `tasks`, `dependencies`, `dependencyInsight`, build reports |

Đây là **bảng đối chiếu chức năng**, không phải chuyển đổi cú pháp 1–1. Parent inheritance của Maven và Gradle plugin application có các rules về merge, override, evaluation và resolution khác nhau.

## 9. Phiên bản phụ thuộc: Maven BOM, Gradle platform và version catalog

### 9.1. Version policy và build policy là hai tầng

**Version policy** trả lời “thư viện `spring-context`/JUnit đang dùng version nào?”. **Build policy** trả lời “compiler, tests, packaging và quality tasks chạy như thế nào?”.

Một parent POM/convention plugin có thể làm cả hai, nhưng không nên đồng nhất chúng:

- Maven `dependencyManagement` và imported BOM quản lý versions; `dependencies` thêm thư viện.
- Gradle `platform(...)` nhập BOM constraints; `implementation(...)` thêm thư viện.
- Gradle **version catalog** (ví dụ `gradle/libs.versions.toml`) đặt aliases/versions cho dependencies/plugins, giúp module tham chiếu bằng `libs....`. Catalog **không tự áp dụng Java compiler conventions**, không tự tạo Boot tasks hay thêm dependencies trừ khi build script sử dụng aliases đó.
- Gradle convention plugin áp dụng/configure plugins và tasks; có thể dùng version catalog, nhưng đó là hai khái niệm khác nhau.

### 9.2. Maven BOM không thay parent

Nếu parent của tổ chức là `company-parent`, bạn có thể import BOM của Spring Boot trong `dependencyManagement` ở parent hoặc tại module Boot. Cần chọn nơi có phạm vi tác động phù hợp: một corporate parent dùng chung cho mọi Java projects có thể không nên buộc tất cả modules lên cùng Boot release.

Nếu nhiều modules cùng là Spring Boot apps, có thể tạo **parent trung gian** kế thừa corporate parent và thêm Boot conventions/version management, trong khi root aggregator độc lập. Một Maven project vẫn chỉ có **một parent trực tiếp**, nhưng chuỗi parent inheritance có thể nhiều tầng.

### 9.3. Gradle không tự nhập BOM khi chỉ áp dụng org.springframework.boot

Spring Boot Gradle Plugin cung cấp tasks và integration với dependency management, nhưng **chỉ áp dụng Boot plugin không tự có nghĩa tất cả versionless dependencies đều được quản lý**. Theo tài liệu, bạn dùng `io.spring.dependency-management` (Boot plugin phối hợp để import BOM) hoặc Gradle native `platform(...)`.

Trong ví dụ này, `company.boot-app` cố ý dùng **native platform**, nên không cần thêm `io.spring.dependency-management`. Không trộn cả hai cơ chế chỉ vì muốn “chắc chắn có BOM”; có thể tạo conflict/khác biệt resolution khó giải thích.

### 9.4. Override managed version cần kiểm soát

Một Boot BOM là tập versions có tính tương thích. Khi doanh nghiệp override một thư viện vì security patch, phải dùng dependency management/Gradle constraints phù hợp, đọc dependency tree và chạy regression tests. **Không sửa một property trùng tên với property nằm trong imported BOM Maven rồi tự cho rằng nó đã override** như trường hợp kế thừa starter parent; cần cấu hình management tường minh.

Trong Gradle, `platform` là **constraints**, không tự biến version được BOM đề nghị thành hard requirement khi graph có constraints/conflicts khác. Đừng dùng `enforcedPlatform` rộng rãi nếu chưa hiểu tác động lên consumers.

## 10. Tổ chức nhiều loại module không chung tất cả plugins

Một repository doanh nghiệp có thể gồm:

~~~text
platform
├── domain-api/                 # Java library
├── core-data/                  # Java library
├── http-service/               # Spring Boot executable app
├── batch-worker/               # Spring Boot executable app
└── integration-tests/          # Tests / fixtures / performance
~~~

Đặt Java toolchain, encoding, kiểm thử cơ bản ở **base convention**. Đặt packaging/lifecycle riêng vào những nhóm:

- **Java library convention:** `java-library`, Java release, test tasks, publication conventions; không đóng Boot executable JAR.
- **Spring Boot app convention:** apply Boot plugin, BOM/dependency management, `bootJar`, integration smoke-test packaging; chỉ cho services/workers thật.
- **Integration-test convention:** test suites, testcontainers dependencies, resource limits và báo cáo CI khi cần.
- **Publishing convention:** signing, Maven publication/group/version policies khi thực sự publish; đừng ép mọi module phát hành.

Ở Maven có thể tạo parent inheritance tiers, parent `pluginManagement`, profile phù hợp hoặc company Maven plugins để đạt phân tầng tương tự. **Không nhồi tất cả executions vào một parent để tự động chạy trên mọi loại module**; ví dụ `spring-boot:repackage` ở parent có thể làm Java library trở thành artifact không phù hợp để modules khác compile against.

## 11. Các quy tắc override và phạm vi tác động

### 11.1. Parent POM: child được phép cấu hình khác

Maven child có thể thêm hoặc override các cấu hình quản lý của parent theo quy tắc model merge. Một số thứ như `<inherited>false</inherited>` trên plugin execution có thể hạn chế inheritance theo ý đồ của parent, nhưng không nên dùng làm biện pháp “vá” tràn lan sau khi đặt execution ở sai cấp.

Parent doanh nghiệp versioned và publish sẽ tạo **change boundary**: child đổi version parent khi chủ động nhận policy mới. Trong monorepo, dùng cùng parent version ở modules giúp thống nhất trong một build. Với Maven reactor có parent local `../pom.xml`, parent phải có version/coordinates đúng như child khai báo.

### 11.2. Gradle: conventions và project-specific overrides

Convention plugin thường đặt **defaults**. Module có thể thêm config riêng một cách rõ ràng:

~~~kotlin
// Trong service/build.gradle.kts, sau plugins { ... }
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-Xlint:unchecked")
}
~~~

Đây là **đoạn Gradle Kotlin DSL** trong project có Java plugin; thêm warning lint mà vẫn giữ Java 17, encoding và Test conventions. **Không tự thay version Java khi service khác biệt** nếu không xác định rõ sự tương thích của library boundary.

Thứ tự plugin application/configuration và Gradle lazy Provider API ảnh hưởng thời điểm cuối cùng của một property. Một convention nên dùng `Property.convention(...)` khi khai báo extension có thể override, thay vì luôn gọi `set(...)` sau các giá trị của module nếu bạn thực sự muốn default. Trong ví dụ, `options.release.set(17)` là **policy được ấn định** cho mọi module áp dụng Java convention, có thể được module override ở giai đoạn phù hợp nhưng không nên dựa vào thứ tự vô tình.

### 11.3. Vì sao tránh subprojects { ... } ở root

Một root `subprojects { apply(plugin = "java") ... }` có thể khiến module không phải Java bị cấu hình sai, tăng cross-project access, khó test/plugin isolation và tạo rào cản cho configuration cache/isolated projects. Convention plugin cho phép modules **tự khai báo loại của mình**. Nếu có một số global constraints thực sự áp dụng mọi project, đặt chúng ở settings/plugin management/enterprise policy phù hợp thay vì dùng root script để thay thế mọi convention plugin.

## 12. CI và quản trị build logic

### 12.1. Thực thi đúng module trong CI

Maven:

~~~bash
mvn -B -ntp clean verify
mvn -B -ntp -pl service -am package
~~~

Gradle:

~~~bash
./gradlew --no-daemon clean build
./gradlew --no-daemon :service:bootJar
~~~

Trong CI, chọn Maven/Gradle Wrapper (khi repository có) để khóa tool version và giảm lệch local/runner. Không cần build toàn bộ repository trong mọi bước nếu có cơ chế affected modules, nhưng phải giữ dependency graph chính xác: `service` cần `shared`.

### 12.2. Kiểm tra artifact cùng module

Một release pipeline cần:

- Xác định rõ artifact **service executable JAR** hay library JAR.
- Chạy tests trên cả library và service theo phạm vi yêu cầu.
- Kiểm Boot executable JAR có `BOOT-INF/classes` và `BOOT-INF/lib`.
- Đọc manifest khi cần (Boot loader `JarLauncher` và `Start-Class`).
- Chạy `java -jar` trên chính artifact sẽ triển khai, không chỉ lệnh `mvn test` hoặc `gradlew test`.
- Cố định versions và kiểm tra dependency graph để tránh một module dùng Boot release khác mà không chủ đích.

### 12.3. Kiểm soát thay đổi parent/convention plugin

Một sửa đổi có vẻ nhỏ ở Java convention (ví dụ nâng `--release`, bật test parallel, đổi dependency constraints) có thể ảnh hưởng hàng chục modules. Quy trình:

1. Mô tả phạm vi policy thay đổi và modules chịu ảnh hưởng.
2. Nếu dùng Maven parent publish, chọn parent version mới và có changelog/migration notes; không sửa artifact release đã publish.
3. Nếu dùng Gradle included build trong cùng repo, review code ở `build-logic` như code production/CI; mọi thay đổi plugin có thể chạy trong giai đoạn configuration.
4. Có integration tests cho ít nhất một **library module** và một **Boot app module** để bắt lỗi packaging.
5. Dùng dependency reports/effective POM so sánh trước/sau.
6. Chạy clean build trong CI và thử release artifact.
7. Ưu tiên các bước nâng version nhỏ, có rollback plan.

**Bảo mật:** build scripts/convention plugins là **mã có thể được thực thi trên máy phát triển và CI**, có quyền truy cập environment, credentials và filesystem. Chỉ dùng plugins/dependencies từ nguồn tin cậy, kiểm soát changes, không hard-code secrets trong `pom.xml`, `build.gradle.kts` hoặc `gradle.properties` commit lên repository.

### 12.4. Khi nào publish một convention plugin?

Nếu một tổ chức có hàng chục repositories phải chia sẻ chính sách, một included build copy-paste giữa repos sẽ có drift. Có thể chuyển convention plugin thành **binary Gradle plugin** và publish version vào internal plugin repository, cho từng repo chủ động nâng version.

Nếu chỉ một multi-project repo, included build `build-logic` thường đơn giản hơn: cùng source-control, không cần release plugin riêng. Maven parent POM versioned có thể được publish tương đối dễ dàng vào Maven artifact repository để phục vụ nhiều repos. Không nhất thiết có “một parent Maven duy nhất cho toàn công ty”; khi nhu cầu khác nhau, cân nhắc parent tầng dưới hoặc build extension/convention policy theo nhóm.

## 13. Troubleshooting đa module: 15 tình huống thực tế

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Maven service báo không tìm được `com.example:shared` | Build `service` riêng, `shared` chưa install; sai GAV | Chạy `mvn -pl service -am package` tại aggregator, kiểm dependency coordinates |
| Maven `Non-resolvable parent POM` | `<parent>` version/relativePath sai hoặc repository không có parent | Kiểm `../pom.xml`, GAV và settings repositories |
| Parent có BOM nhưng child starter vẫn thiếu version | Sai type/import scope, parent không thực sự được kế thừa | Kiểm `help:effective-pom` và `dependencyManagement` |
| Maven build tất cả module nhưng không kế thừa Java release | Root chỉ aggregate qua `<modules>`, child dùng parent khác | Kiểm child `<parent>` và effective POM, không suy từ root location |
| `shared` bị biến thành Boot executable JAR | Boot plugin execution ở parent `build/plugins` hoặc child shared | Đưa Boot plugin version vào parent `pluginManagement`, execution ở app |
| `spring-boot:repackage` không chạy trên service | Không dùng starter parent; child chỉ có BOM/import plugin version | Khai báo Boot plugin + goal `repackage` trong service |
| Gradle báo `Plugin [id: 'company.java-conventions'] was not found` | `includeBuild` sai, filename/ID khác, `build-logic` không compile | Kiểm settings `pluginManagement.includeBuild("build-logic")`, build-logic logs |
| Gradle báo lỗi khi dùng `version "..."` trong precompiled plugin | External plugin version đặt sai chỗ | Đưa plugin artifact vào `build-logic` `implementation(...)`, dùng ID không version trong convention script |
| Gradle `shared:bootJar` xuất hiện và fail tìm main class | Boot convention bị áp dụng cho library | Chỉ áp dụng Java convention ở library |
| Gradle service starter thiếu version | Boot plugin được apply nhưng BOM chưa nhập | Thêm `implementation(platform(...spring-boot-dependencies...))` hoặc dependency-management plugin |
| `useJUnitPlatform` có mà không có test được phát hiện | Thiếu JUnit engine/launcher hoặc test deps | Kiểm `testRuntimeClasspath`, starter-test, launcher và Gradle Test reports |
| Build local chạy, CI báo `invalid target release` | Maven/Gradle JVM/toolchain không có JDK phù hợp | Kiểm `java -version`, `mvn -version`, `./gradlew --version` và toolchain |
| Gradle included build dùng repository khác main build | `build-logic` là build độc lập, không kế thừa settings repos | Khai báo repositories của included build hoặc dùng policy chung có kiểm soát |
| Service JAR thiếu `shared` lúc runtime | Gradle dùng `compileOnly`/Maven provided sai, hoặc deploy thin JAR | Kiểm runtime dependency graph và `BOOT-INF/lib` |
| Mỗi module resolve thư viện khác version | Parent/BOM/Gradle platform không được áp dụng nhất quán | Xem `dependency:tree`, `dependencyInsight` và effective configuration |

### 13.1. Phương pháp gỡ lỗi theo thứ tự

**Bước A — Module topology:** Root đã khai báo đúng Maven `<modules>`/Gradle `include` chưa? Module `service` có dependency thật vào `shared` chưa?

**Bước B — Policy propagation:** Maven child có parent chính xác không? Gradle subproject có áp dụng đúng convention plugin không?

**Bước C — Versions:** Maven `dependencyManagement` và `pluginManagement`, Gradle `platform`/plugin classpath có đang chọn versions kỳ vọng không?

**Bước D — Execution:** Boot plugin/execution được kích hoạt **chỉ** ở service? `shared` còn là library JAR bình thường?

**Bước E — Artifact:** Run test và inspect chính executable JAR. Nếu output khác dự kiến, không sửa Java code trước khi kiểm build graph và tasks.

## 14. Bài tập có đáp án

**Câu 1.** Root POM có `<modules><module>shared</module>...`, nhưng `shared/pom.xml` không khai báo `<parent>`. Module có tự kế thừa parent properties không?  
**Đáp án:** Không. Aggregation và inheritance độc lập; phải khai báo đúng `<parent>` hoặc nhận policy qua cơ chế khác.

**Câu 2.** Parent có `spring-boot-dependencies` trong `dependencyManagement`. `shared` không khai báo Spring dependencies. Nó có tự kéo Spring Boot runtime không?  
**Đáp án:** Không. Dependency management chỉ quản lý metadata cho dependency được dùng.

**Câu 3.** Parent quản lý `spring-boot-maven-plugin` version trong `pluginManagement`. Vì sao `mvn package` ở service có thể vẫn tạo plain JAR?  
**Đáp án:** Vì goal `repackage` chưa được kích hoạt. Service cần plugin/execution phù hợp hoặc kế thừa cấu hình execution thực sự từ parent.

**Câu 4.** Gradle `settings.gradle.kts` có `include("shared","service")`. Vì sao hai modules chưa dùng được convention `company.java-conventions`?  
**Đáp án:** Chưa khai báo nguồn plugin (`pluginManagement.includeBuild("build-logic")` hoặc cách publish/resolve tương ứng), hoặc module chưa áp dụng plugin.

**Câu 5.** Trong Gradle precompiled plugin, thêm `id("org.springframework.boot") version "3.5.16"` có đúng không?  
**Đáp án:** Không. Với precompiled script plugin, thêm external plugin artifact như dependency của `build-logic` và áp dụng plugin ID không ghi version trong script.

**Câu 6.** Cùng áp dụng `company.java-conventions` có khiến `service` nhìn thấy class `Greeter` của `shared` không?  
**Đáp án:** Không. Cần `implementation(project(":shared"))` trong Gradle, hoặc dependency `com.example:shared:...` trong Maven.

**Câu 7.** Tại sao library không nên chạy Boot `repackage`?  
**Đáp án:** Executable Boot JAR có layout `BOOT-INF/classes`; không phải classpath root thông thường của library JAR để compiler của dependent project đọc trực tiếp. Library nên dùng thin JAR.

**Câu 8.** Bạn muốn đổi Java release cho 30 modules. Nên sửa ở đâu?  
**Đáp án:** Maven: parent `maven.compiler.release`/compiler configuration; Gradle: Java convention plugin/toolchain. Phải kiểm cả module library và Boot app sau khi thay đổi.

**Câu 9.** Một dependency đã nằm trong BOM nên có sẵn trên app classpath hay chưa?  
**Đáp án:** Chưa. BOM chỉ cung cấp version constraints/managed versions; dependency phải được module khai báo hoặc xuất hiện qua đường transitive hợp lệ.

**Câu 10.** Có nên dùng `subprojects { ... }` để ép Spring Boot plugin lên mọi module trong Gradle?  
**Đáp án:** Không. Java libraries, tools và Boot apps có packaging khác nhau. Tạo conventions có phân loại và áp dụng ở module thích hợp.

## 15. Checklist thực hành trước khi merge

- [ ] Cấu trúc modules được định nghĩa đúng: Maven `<modules>` hoặc Gradle `include(...)`.
- [ ] Quan hệ dependencies giữa modules tồn tại rõ ràng, không dựa vào cùng parent/convention.
- [ ] Maven child có `<parent>` đúng GAV/relativePath nếu cần inheritance.
- [ ] Maven parent có `dependencyManagement`, `pluginManagement` phù hợp; không vô tình thêm Boot starters hoặc `repackage` cho mọi module.
- [ ] Gradle `build-logic` có settings/build file riêng và được đưa vào plugin management bằng `includeBuild`.
- [ ] Precompiled scripts có plugin IDs và file names đúng; external plugin artifacts/versions khai báo ở build-logic classpath.
- [ ] Java release/encoding/test framework thống nhất và kiểm tra ở từng module.
- [ ] Spring Boot BOM/platform đã quản lý versions; modules chỉ thêm dependencies thật sự sử dụng.
- [ ] Spring Boot plugin/packaging chỉ được kích hoạt trên executable apps; thin libraries giữ layout đúng.
- [ ] Build toàn reactor/multi-project chạy được bằng Wrapper hoặc tool versions được nhóm quản lý.
- [ ] Đã so sánh effective POM/dependency tree hoặc Gradle tasks/dependencyInsight khi có sự khác nhau.
- [ ] CI kiểm đúng artifact cuối cùng, không deploy nhầm thin JAR hoặc `plain` artifact.
- [ ] Build logic được review như code có thể thực thi; không commit secrets vào scripts.
- [ ] Có regression test bao phủ ít nhất một module library và một module Spring Boot app.

## 16. Tài liệu chính thức

- Apache Maven — Introduction to the POM (Inheritance vs Aggregation): https://maven.apache.org/guides/introduction/introduction-to-the-pom.html
- Apache Maven — POM Reference (dependencyManagement, pluginManagement): https://maven.apache.org/pom.html
- Apache Maven — Introduction to Dependency Mechanism (BOM import): https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Maven Compiler Plugin — Setting compiler release: https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html
- Maven Help Plugin — Effective POM: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Gradle — Best Practices for Structuring Builds: https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html
- Gradle — Implementing Precompiled Script Plugins: https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html
- Gradle — Convention Plugins: https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html
- Gradle — Sharing Build Logic between Subprojects: https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html
- Gradle — Composite Builds: https://docs.gradle.org/current/userguide/composite_builds.html
- Gradle — BOM/Platform Dependency Management: https://docs.gradle.org/current/userguide/platforms.html
- Spring Boot 3.5 — Maven Using Boot without Parent POM: https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html
- Spring Boot 3.5 — Gradle Plugin Managing Dependencies: https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html
- Spring Boot 3.5 — Gradle Plugin Getting Started: https://docs.spring.io/spring-boot/3.5/gradle-plugin/getting-started.html
- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html

**Kết luận:** Trong Maven, hãy dùng **parent POM cho inheritance**, **aggregator cho reactor** và khai báo **dependency giữa modules** riêng biệt. Trong Gradle, hãy đóng gói policy thành **convention plugins** từ `build-logic`, rồi để các subprojects chủ động áp dụng đúng loại convention. Với Spring Boot, nên phân biệt thật rõ **library JAR** và **executable Boot JAR**: quản lý version chung không có nghĩa mọi module phải nhận cùng starter hoặc cùng executable packaging.