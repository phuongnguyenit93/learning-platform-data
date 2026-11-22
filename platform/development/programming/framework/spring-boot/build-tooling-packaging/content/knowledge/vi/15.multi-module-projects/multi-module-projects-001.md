# Tách mô-đun thư viện, mô-đun ứng dụng và mô-đun cấu hình build

Khi một project Spring Boot phát triển lớn hơn, việc để toàn bộ mã nghiệp vụ, điểm khởi động, API HTTP, dependency và quy tắc Maven/Gradle chung trong cùng một module khiến hệ thống khó tái sử dụng, khó test độc lập và dễ đóng gói nhầm. Một **dự án đa mô-đun** được tổ chức hợp lý nên tách rõ **mô-đun thư viện** (mã có thể tái sử dụng), **mô-đun ứng dụng** (điểm chạy/deploy) và **mô-đun cấu hình build** (quy ước compiler, plugins, dependency version, test, publication).

Bài học này xây dựng cùng một ứng dụng mẫu bằng **Maven** và **Gradle**, dùng **Java 17** và **Spring Boot 3.3.13**. Sau khi thực hành, bạn sẽ biết cách để `boot-app` phụ thuộc `core-lib`, giữ `core-lib` dưới dạng plain JAR, chỉ đóng gói `boot-app` thành executable JAR, quản lý build convention qua Maven `build-parent` hoặc Gradle `build-logic` và xác minh task/reactor dependency graph. Version dùng để minh họa một cấu hình nhất quán, không có nghĩa là phiên bản Spring Boot mới nhất.

## 1. Ba vai trò và hướng phụ thuộc chuẩn

| Vai trò | Trách nhiệm chính | Chứa những gì? | Artifact/chức năng |
| --- | --- | --- | --- |
| **Thư viện — `core-lib`** | Cung cấp class, interface và logic có thể dùng lại, không phụ thuộc deploy runtime | Java domain model, utility, logic nghiệp vụ thuần, test riêng | **Plain JAR**, dùng làm dependency |
| **Ứng dụng — `boot-app`** | Ghép các thành phần, khởi chạy Spring Boot, expose endpoint, cấu hình vận hành | `@SpringBootApplication`, controller, DI/configuration, test tích hợp | **Spring Boot executable JAR/WAR**, chạy bằng `java -jar` |
| **Cấu hình build — `build-parent` / `build-logic`** | Chuẩn hóa build, toolchain, repository, version, test/plugin settings | Maven parent POM hoặc Gradle convention plugin | Cấu hình được kế thừa/áp dụng, **không thuộc runtime ứng dụng** |

Hướng phụ thuộc mã nguồn cần là:

```text
                +-------------------------+
                |  Shared Build Rules     |
                | Maven build-parent /    |
                | Gradle build-logic      |
                +-----------+-------------+
                            |
                  applied / inherited
                      /           \
                     v             v
              +-----------+     +-----------+
              | core-lib  |<----| boot-app  |
              | plain JAR |     | Boot JAR  |
              +-----------+     +-----------+
                   ^
                   |
           reusable classes/interfaces
```

`boot-app → core-lib` là một **dependency lập trình**: code app import class trong thư viện. `core-lib → boot-app` là hướng **không nên có**, vì sẽ tạo vòng tròn dependency và khiến library phụ thuộc vào điểm deploy.

Còn `build-parent`/`build-logic` chỉ chứa **build configuration**, không được thêm như một dependency `implementation` / `compile` của Java code. Những module này có lifecycle khác nhau:
- Thư viện chạy unit test rồi xuất plain JAR.
- Ứng dụng chạy test, đóng gói Boot JAR, có thể build image/container và deploy.
- Cấu hình build được Maven/Gradle đọc **để định nghĩa cách build**; không tự là ứng dụng chạy bằng JVM.

## 2. Module, package và microservice là ba khái niệm khác nhau

- **Java package** như `com.example.shared` chỉ tổ chức namespace, visibility và tên class.
- **Build module** như `core-lib` có file `pom.xml` hoặc `build.gradle` riêng, dependency graph, compile/test và artifact riêng. Một module có thể chứa nhiều package.
- **Deployable application** như `boot-app` sở hữu main class, runtime configuration và process đang chạy; có thể phụ thuộc hàng chục thư viện.
- **Microservice** là ranh giới triển khai, vận hành, dữ liệu, API và trách nhiệm hệ thống. Nhiều module trong một repository **không đồng nghĩa** phải có nhiều microservice.
- **Build logic module** dùng để tạo quy tắc build cho các project, không phải mã nghiệp vụ cần cho classpath runtime.

Bạn có thể có một mono-repo 10 library modules nhưng chỉ một Spring Boot app; điều đó vẫn là kiến trúc hợp lệ. Không nên đánh đồng “có file `.java`” với “phải bật Spring Boot plugin”.

## 3. Mã Java dùng chung cho cả Maven và Gradle

Cả hai phiên bản thực hành dùng chung cây mã:

```text
multi-module-demo/
├── core-lib/
│   └── src/main/java/com/example/shared/
│       └── GreetingService.java
└── boot-app/
    ├── src/main/java/com/example/app/
    │   ├── BootApplication.java
    │   └── GreetingController.java
    └── src/test/java/com/example/app/
        └── BootApplicationTest.java
```

### 3.1. Class Java thuần trong thư viện

Tạo `core-lib/src/main/java/com/example/shared/GreetingService.java`:

```java
package com.example.shared;

public final class GreetingService {

    public String greet() {
        return "hello-from-core-lib";
    }
}
```

`GreetingService` không sử dụng Spring Framework API, không cần `@SpringBootApplication`, không có `main`. Đây là ví dụ rõ nhất về **mã nên để trong library**. Package `com.example.shared` được giữ cố ý khác package ứng dụng để minh họa bean wiring không đồng nghĩa với component scanning.

### 3.2. Spring Boot entry point

Tạo `boot-app/src/main/java/com/example/app/BootApplication.java`:

```java
package com.example.app;

import com.example.shared.GreetingService;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BootApplication {

    public static void main(String[] args) {
        SpringApplication.run(BootApplication.class, args);
    }

    @Bean
    GreetingService greetingService() {
        return new GreetingService();
    }
}
```

Phương thức `@Bean` cho Spring biết cách tạo `GreetingService`. **Project dependency** đưa class thư viện vào classpath, nhưng **không tự đăng ký mọi class làm Spring bean**. Ở đây việc cấu hình explicit `@Bean` vừa rõ trách nhiệm của app vừa tránh package scan tràn lan.

### 3.3. REST controller ở application module

Tạo `boot-app/src/main/java/com/example/app/GreetingController.java`:

```java
package com.example.app;

import com.example.shared.GreetingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/hello")
    public String hello() {
        return greetingService.greet();
    }
}
```

Spring Boot sử dụng constructor injection để đưa bean `GreetingService` vào controller. Khi ứng dụng khởi động thành công, HTTP `GET /hello` có response body:

```text
hello-from-core-lib
```

Đây là **HTTP body**, không phải toàn bộ log Spring Boot hoặc dòng console chính xác của quá trình startup.

### 3.4. Test để xác minh liên kết module và DI

Tạo `boot-app/src/test/java/com/example/app/BootApplicationTest.java`:

```java
package com.example.app;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.example.shared.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class BootApplicationTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void findsLibraryBean() {
        assertEquals("hello-from-core-lib", greetingService.greet());
    }
}
```

JUnit Jupiter thực thi `@Test` khi build tool có dependency/runner phù hợp. `@SpringBootTest` kiểm tra Spring context và dependency injection; test này không phải một HTTP endpoint test trực tiếp. Trường hợp muốn test HTTP, dùng MockMvc hoặc chạy JAR và gọi `curl` như phần sau.

Tất cả file có `public class` và đường dẫn package phù hợp Java 17; mã thư viện không cần các starter hoặc Spring annotation.

## 4. Maven: vì sao cần hiểu cả aggregator và parent?

Maven có hai cơ chế thường bị gộp làm một:

1. **Aggregation**: root `pom.xml` có `<packaging>pom</packaging>` và `<modules>`, cho **Maven reactor** biết những project nào thuộc một lượt build. Maven đọc các module, tính dependency graph và xây theo thứ tự phù hợp.
2. **Inheritance**: mỗi project con khai báo `<parent>` để kế thừa properties, `dependencyManagement`, `pluginManagement` và cấu hình chung. **Một parent không buộc phải là aggregator**, và ngược lại một aggregator không tự thành parent của mọi module.

Để bài học thể hiện rõ **mô-đun cấu hình build**, ta chọn hai POM riêng:

```text
multi-module-demo/                      [Maven]
├── pom.xml                            # aggregator, packaging=pom
├── build-parent/
│   └── pom.xml                        # parent, packaging=pom
├── core-lib/
│   ├── pom.xml                        # library, packaging=jar
│   └── src/main/java/...
└── boot-app/
    ├── pom.xml                        # Spring Boot executable app
    ├── src/main/java/...
    └── src/test/java/...

root aggregator --> build-parent, core-lib, boot-app (reactor modules)
build-parent --> inherited by core-lib and boot-app
boot-app -----> depends on core-lib
```

Cấu trúc này có thể phát triển thành một **corporate parent POM** được publish riêng hoặc một root aggregator đơn giản mà không kéo theo plugin app cho mọi module. Maven reactor sắp xếp module bằng quan hệ parent/dependency, không chỉ thứ tự khai báo `<module>`.

## 5. Maven root `pom.xml` — chỉ gom các module

Tạo `multi-module-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>multi-module-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>build-parent</module>
        <module>core-lib</module>
        <module>boot-app</module>
    </modules>
</project>
```

Root này không có `spring-boot-maven-plugin` và không sinh ứng dụng executable JAR. Nó được Maven gọi ở gốc repository, sau đó Maven reactor tìm từng module theo đường dẫn tương đối từ POM.

**Đừng nhầm `<module>core-lib</module>` với dependency của `boot-app`:** một khai báo cho reactor biết project nằm ở đâu, khai báo còn lại đưa thư viện vào compile/runtime classpath. Bạn cần cả hai với mục đích khác nhau trong cấu trúc bài này.

## 6. Maven `build-parent/pom.xml` — cấu hình build chung

Tạo `build-parent/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>build-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example</groupId>
                <artifactId>core-lib</artifactId>
                <version>1.0.0</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

Giải thích:
- `build-parent` là **POM mang config**, không có `src/main/java` hay `main`; `<packaging>pom</packaging>` là đúng chức năng.
- Kế thừa `spring-boot-starter-parent` mang mặc định compiler Java, dependency BOM, plugin management và execution `repackage` được chuẩn bị; **không tự buộc mọi child chạy Boot plugin**.
- `java.version=17` xác định mức Java của ví dụ; kiểm tra Maven chạy trên JDK phù hợp.
- `<dependencyManagement>` cố định version của `core-lib` để app khai báo dependency không cần lặp `<version>`.
- Vì **không** khai báo `spring-boot-maven-plugin` ở `<build><plugins>` của parent, các module thư viện không vô tình chạy `repackage`.
- `<relativePath/>` của Spring Boot parent tránh Maven cố tìm POM parent từ một đường dẫn local sai.

Trong project thực, version của các module cùng release nên có **chiến lược đồng bộ** để không phải sửa nhiều literal `1.0.0`. Bài để version cố định nhằm tập trung vào ranh giới build và packaging; khi nâng cấp cần thay nhất quán cả parent/dependency coordinates.

## 7. Maven `core-lib/pom.xml` — plain Java JAR

Tạo `core-lib/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>build-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../build-parent/pom.xml</relativePath>
    </parent>

    <artifactId>core-lib</artifactId>
    <packaging>jar</packaging>
</project>
```

Library kế thừa group/version `com.example:core-lib:1.0.0` từ parent; `GreetingService` chỉ cần JDK, không thêm dependency. Maven đóng gói bằng quy tắc `jar` thông thường.

Đầu ra dự kiến: `core-lib/target/core-lib-1.0.0.jar`, bên trong có `com/example/shared/GreetingService.class` ở root. File này là **library JAR**, không có main method và không cần Boot loader.

Không thêm `spring-boot-starter-web` vào đây chỉ để module build được. Khi library thật sự cần Spring API hoặc một thư viện khác, khai báo đúng dependency/scope của library. Spring Boot executable packaging được quyết định bởi vai trò **deployable app**, không phải việc một library có class được Spring sử dụng.

## 8. Maven `boot-app/pom.xml` — module duy nhất chạy Spring Boot

Tạo `boot-app/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>build-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../build-parent/pom.xml</relativePath>
    </parent>

    <artifactId>boot-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>core-lib</artifactId>
        </dependency>
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
```

Bốn điểm đáng chú ý:

1. Dependency `com.example:core-lib` được app khai báo **thật**. Version đến từ parent `dependencyManagement`; riêng việc parent quản lý version **không** tự thêm library vào runtime.
2. `spring-boot-starter-web` kéo Spring MVC và các thành phần web server thích hợp; library không phải khai báo lại.
3. `spring-boot-starter-test` chỉ ở test scope, không được đóng gói mặc định vào production `BOOT-INF/lib`.
4. Chỉ app khai báo `spring-boot-maven-plugin`. Spring Boot starter parent ở chuỗi parent đã chuẩn bị plugin version và execution `repackage`, nên `mvn package` tạo executable JAR.

Không sửa `<parent>` ở `boot-app` thành root aggregator POM nếu vẫn muốn nhận build configuration ở `build-parent`. Maven chỉ có **một parent trực tiếp** cho một module. Aggregation và inheritance vẫn là hai quan hệ tách biệt.

## 9. Maven reactor: build đúng thứ tự và kiểm tra artifact

Từ **root** chứa aggregator POM:

```bash
./mvnw clean verify
```

`verify` kích hoạt các phase trước, bao gồm test/package theo lifecycle của từng project. Maven reactor có thể build parent trước child và library trước application. Thứ tự module trong XML không phải thứ tự dependency bắt buộc vì Maven reactor sắp xếp dựa trên quan hệ giữa các project.

Muốn chỉ build ứng dụng cùng những upstream reactor projects cần cho nó:

```bash
./mvnw -pl boot-app -am clean package
```

- `-pl boot-app` chọn module app.
- `-am` (also make) kéo các reactor projects app cần, trong đó có library và parent khi thuộc reactor.
- Khi chạy từ root, Maven không yêu cầu bạn install thủ công `core-lib` ở local repository trước cho trường hợp dependency thuộc cùng reactor.
- Chạy `mvn package` trực tiếp trong `boot-app` khi các parent/dependency chưa resolve có thể thất bại; dùng lệnh reactor hoặc install các module cần thiết.

Đầu ra dự kiến:

```text
core-lib/target/core-lib-1.0.0.jar
boot-app/target/boot-app-1.0.0.jar
```

Kiểm tra:

```bash
jar tf core-lib/target/core-lib-1.0.0.jar
jar tf boot-app/target/boot-app-1.0.0.jar
```

Các entry quan trọng:

```text
# Bên trong core-lib plain JAR
com/example/shared/GreetingService.class

# Bên trong boot-app executable JAR
BOOT-INF/classes/com/example/app/BootApplication.class
BOOT-INF/classes/com/example/app/GreetingController.class
BOOT-INF/lib/core-lib-1.0.0.jar
BOOT-INF/lib/spring-boot-3.3.13.jar
```

Đây là **trích đoạn minh họa**, không phải toàn bộ danh sách `jar tf`. `core-lib` tồn tại như một nested runtime JAR trong `boot-app`: điều này cho phép app tải class thư viện qua Boot launcher. `core-lib` vẫn là artifact plain JAR của chính nó.

Chạy:

```bash
java -jar boot-app/target/boot-app-1.0.0.jar
```

Terminal thứ hai:

```bash
curl -s http://localhost:8080/hello
```

Kỳ vọng HTTP body:

```text
hello-from-core-lib
```

Nếu cổng 8080 đang bị chiếm, chạy `java -jar boot-app/target/boot-app-1.0.0.jar --server.port=8091` và gọi endpoint ở 8091. Dừng ứng dụng sau kiểm tra.

## 10. Maven không dùng Spring Boot starter parent: phải quản lý gì?

Nhiều doanh nghiệp yêu cầu **corporate parent POM**. Maven chỉ có một `<parent>` trực tiếp, vì vậy `build-parent` có thể kế thừa corporate parent rồi **import Spring Boot BOM** để quản lý dependency versions.

Ví dụ các phần liên quan trong `build-parent/pom.xml` (đây là **đoạn POM để ghép**, không phải file `pom.xml` độc lập):

```xml
<properties>
    <spring-boot.version>3.3.13</spring-boot.version>
    <maven.compiler.release>17</maven.compiler.release>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>${spring-boot.version}</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Trong POM thực, **hợp nhất** đoạn `dependencyManagement` này với dependency management hiện có của công ty và với `core-lib`; không tạo hai khối `<dependencyManagement>` cạnh nhau chỉ vì chép ví dụ. Corporate parent cũng có thể quản lý compiler/Surefire; kiểm tra bằng `help:effective-pom`.

**Quan trọng:** import `spring-boot-dependencies` BOM **chỉ** quản lý dependency version; nó **không** tự bổ sung plugin version hoặc execution `repackage`. Do vậy, nếu không nhận execution từ Spring Boot parent, `boot-app` cần plugin execution tường minh:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>repackage</id>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Đây là **cách cấu hình thay thế cho app không kế thừa Boot parent**. Với POM đầy đủ ở mục 8, không thêm execution lần nữa: parent Spring Boot đã có execution id `repackage`.

## 11. Gradle: `settings.gradle` và `build-logic` khác Maven parent

Gradle không có hệ `<parent>` như Maven; nó dùng:
- `settings.gradle` để xác định **project graph**.
- `build.gradle` của từng subproject để áp dụng plugin và khai báo dependency.
- **Convention plugin** để gom cấu hình chung, được project opt-in.
- **Included build `build-logic`** để xây các convention plugin cho build scripts.

Cấu trúc tương đương với cùng mã Java:

```text
multi-module-demo/                      [Gradle]
├── settings.gradle
├── build.gradle                        # có thể để trống
├── build-logic/
│   ├── settings.gradle
│   ├── build.gradle
│   └── src/main/groovy/
│       └── java-common-conventions.gradle
├── core-lib/
│   ├── build.gradle
│   └── src/main/java/com/example/shared/
│       └── GreetingService.java
└── boot-app/
    ├── build.gradle
    ├── src/main/java/com/example/app/
    │   ├── BootApplication.java
    │   └── GreetingController.java
    └── src/test/java/com/example/app/
        └── BootApplicationTest.java
```

`build-logic` là một **build được include cho mục đích plugin resolution**, không phải subproject nghiệp vụ `:build-logic`. Sự khác nhau này quyết định cách khai báo và sử dụng nó.

## 12. Gradle `settings.gradle`: đưa subprojects và plugin build vào đúng chỗ

Tạo `multi-module-demo/settings.gradle`:

```groovy
pluginManagement {
    includeBuild('build-logic')

    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = 'multi-module-demo'

include 'core-lib', 'boot-app'
```

- `include 'core-lib', 'boot-app'` tạo project paths `:core-lib` và `:boot-app` với source/build logic riêng.
- `pluginManagement { includeBuild('build-logic') }` cung cấp convention plugins từ included build cho `plugins { id '...' }` trong subprojects.
- `pluginManagement.repositories` dùng cho **plugin resolution** (ví dụ `org.springframework.boot`); repository dành cho mã ứng dụng có thể cấu hình trong convention plugin hoặc `dependencyResolutionManagement`.
- Root `build.gradle` có thể để trống cho ví dụ, vì không có application ở root.

**Không thay `includeBuild('build-logic')` thành `include 'build-logic'`** nếu mục đích là tạo Gradle convention plugin theo cấu trúc này. Một bên là **included build** độc lập, một bên là **subproject** thông thường.

## 13. Gradle `build-logic`: convention plugin cho cấu hình Java chung

### 13.1. Tạo included build

`build-logic/settings.gradle`:

```groovy
rootProject.name = 'build-logic'
```

`build-logic/build.gradle`:

```groovy
plugins {
    id 'groovy-gradle-plugin'
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}
```

`groovy-gradle-plugin` cung cấp khả năng biên dịch và đăng ký **precompiled Groovy script plugins** từ `src/main/groovy`. Với Kotlin DSL, plugin tương ứng thường là `kotlin-dsl` và file `.gradle.kts`; bài này giữ thống nhất Groovy DSL để dễ chạy.

### 13.2. Viết plugin dùng chung

Tạo `build-logic/src/main/groovy/java-common-conventions.gradle`:

```groovy
plugins {
    id 'java'
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

tasks.withType(org.gradle.api.tasks.testing.Test).configureEach {
    useJUnitPlatform()
}
```

Tên file `java-common-conventions.gradle` tạo plugin id **`java-common-conventions`**. Khi được áp dụng, mỗi module nhận:
- Java plugin, compile/test/jar task mặc định.
- Java 17 toolchain (Gradle có thể cần JDK/toolchain provisioning phù hợp).
- Group/version cho artifact module.
- Maven Central để resolve dependency.
- `useJUnitPlatform()` cho task `Test`, nhưng **không tự thêm** các dependency JUnit Engine/Launcher.

**Cố ý không áp dụng Spring Boot plugin trong convention chung.** Nếu làm vậy, `core-lib` cũng bị tạo Boot tasks như `bootJar` trong khi thư viện không có main class. Cấu hình chung nên chứa những điều **mọi module nhận nó đều cần**.

Convention plugin khác `allprojects { ... }` ở chỗ module nào muốn quy ước nào sẽ **áp dụng rõ plugin tương ứng**. Điều này dễ test và thay đổi hơn khi số lượng module tăng.

## 14. Gradle `core-lib`: áp dụng Java Library plugin

Tạo `core-lib/build.gradle`:

```groovy
plugins {
    id 'java-common-conventions'
    id 'java-library'
}
```

Plugin `java-common-conventions` đã áp dụng `java`. Plugin `java-library` bổ sung cấu hình `api`/`implementation` và các quy tắc outgoing variants cho thư viện. Áp dụng cùng nhau trong module này là hợp lệ; `java-library` không tự bật Spring Boot.

Build plain JAR:

```bash
./gradlew :core-lib:jar
```

Artifact dự kiến:

```text
core-lib/build/libs/core-lib-1.0.0.jar
```

Chạy `jar tf` sẽ thấy `com/example/shared/GreetingService.class` tại root archive; **không** có Spring Boot nested JAR layout `BOOT-INF/classes`/`BOOT-INF/lib`.

Khi library cần external dependencies, dùng:
- `api` nếu dependency là một phần của **public API** của thư viện mà consumer cần biết để biên dịch;
- `implementation` nếu là chi tiết triển khai nội bộ;
- `testImplementation` và `testRuntimeOnly` cho các dependency chỉ cần trong kiểm thử.

Ví dụ cú pháp, **không thêm vào bài thực hành** vì tọa độ dưới đây là placeholder thuộc một hệ thống ví dụ không có thật:

```groovy
dependencies {
    api 'com.acme:public-contract:1.0.0'
    implementation 'com.acme:internal-helper:1.0.0'
}
```

Trong code thực tế, dùng artifact có thật của dự án. Với `GreetingService` thuần Java ở mục 3, bạn **không cần** đoạn dependency này.

## 15. Gradle `boot-app`: project dependency và Boot tasks

Tạo `boot-app/build.gradle`:

```groovy
plugins {
    id 'java-common-conventions'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation project(':core-lib')
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

springBoot {
    mainClass = 'com.example.app.BootApplication'
}
```

Đây là **file `build.gradle` đầy đủ** của app, bổ sung vào cấu hình plugin chung từ `build-logic`. Ý nghĩa:

1. `implementation project(':core-lib')` là một **project dependency**. Nó vừa cung cấp compile/runtime classpath vừa để Gradle biết task output nào cần được xây trước app.
2. `spring-boot-starter-web` và starter test được giải version theo dependency management phù hợp với Spring Boot version đã chọn.
3. `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'` bổ sung launcher trong runtime test; `useJUnitPlatform()` đã được convention plugin định nghĩa.
4. `springBoot.mainClass` xác định entry point của executable JAR. Nó **không** ảnh hưởng đến cách `core-lib` tạo plain JAR.
5. Chỉ `boot-app` áp dụng `org.springframework.boot`, nên Boot tasks không chạy ở library.

### 15.1. Build và test

```bash
./gradlew :boot-app:test
./gradlew :boot-app:bootJar
```

Hoặc:

```bash
./gradlew :core-lib:jar :boot-app:bootJar
```

Gradle nhìn project dependency và tự kéo upstream compile/jar tasks của `core-lib` cần thiết. Không nên chạy shell script copy một JAR cũ từ thư mục `build/libs` để tạo dependency, vì như vậy không còn đúng graph/up-to-date behavior.

Executable archive dự kiến:

```text
boot-app/build/libs/boot-app-1.0.0.jar
```

Chạy:

```bash
java -jar boot-app/build/libs/boot-app-1.0.0.jar
```

Terminal thứ hai:

```bash
curl -s http://localhost:8080/hello
```

Kết quả body:

```text
hello-from-core-lib
```

Với Windows PowerShell dùng `.\gradlew.bat` thay `./gradlew`. Nếu cần cổng khác, truyền `--server.port=8091` vào cuối lệnh `java -jar`.

### 15.2. Kiểm tra đóng gói thư viện

```bash
jar tf core-lib/build/libs/core-lib-1.0.0.jar
jar tf boot-app/build/libs/boot-app-1.0.0.jar
```

Trích đoạn mong đợi:

```text
# Plain library JAR
com/example/shared/GreetingService.class

# Spring Boot application JAR
BOOT-INF/classes/com/example/app/BootApplication.class
BOOT-INF/classes/com/example/app/GreetingController.class
BOOT-INF/lib/core-lib-1.0.0.jar
```

Spring Boot loader xử lý `BOOT-INF/lib/core-lib-1.0.0.jar` như một nested dependency JAR. **Không** mong class của `core-lib` bị bung trực tiếp vào `BOOT-INF/classes/com/example/shared` trong kiểu đóng gói mặc định này.

`boot-app` có thể tạo thêm plain JAR với classifier `plain` nếu Gradle Java task `jar` được bật. Với CI, **chỉ chọn đúng executable JAR**; tránh dùng wildcard `*.jar` rồi deploy nhầm `-plain.jar` hoặc thư viện.

## 16. Phân biệt quan hệ module và phạm vi runtime

| Quan hệ | Ví dụ | Tác dụng |
| --- | --- | --- |
| Maven aggregator modules | Root `<modules><module>core-lib</module>...` | Đưa project vào reactor |
| Maven parent | `<parent>build-parent</parent>` | Kế thừa properties, plugin/dependency management |
| Maven dependency | `<dependency>com.example:core-lib</dependency>` | Đưa class library vào classpath app |
| Gradle included build | `includeBuild('build-logic')` | Cung cấp convention plugins cho build scripts |
| Gradle project inclusion | `include 'core-lib','boot-app'` | Tạo `:core-lib` / `:boot-app` |
| Gradle project dependency | `implementation project(':core-lib')` | Đưa thư viện vào compile/runtime graph app |
| Gradle task dependency | `dependsOn(':core-lib:jar')` | Yêu cầu chạy task theo graph, **không tự thêm library vào classpath** |

**Không thể thay thế Maven `<dependency>` bằng một `<module>`**, hoặc thay Gradle `implementation project(...)` bằng `dependsOn(...)`. Một cơ chế chọn **dự án/lifecycle**, một cơ chế chọn **mã và artifact trên classpath**.

Với Maven, `dependencyManagement` quản lý version nhưng **không tự kéo dependency**; `pluginManagement` quản lý version/config nhưng không bắt plugin chạy trong mọi module. Với Gradle, `pluginManagement.repositories` phục vụ plugin resolution, không tự là repository cho Java application dependencies.

## 17. Spring component scan qua module: hiểu đúng cơ chế

`@SpringBootApplication` trong `com.example.app` mặc định quét class ở package `com.example.app` và các package con. Nhưng Java class của library nằm ở `com.example.shared`. Dù Gradle/Maven đã đóng gói `core-lib` đúng, **một `@Service` ở package anh em vẫn có thể không được component-scan tìm thấy**.

Trong ví dụ, `@Bean` trên `BootApplication` giải quyết minh bạch:

```java
@Bean
GreetingService greetingService() {
    return new GreetingService();
}
```

Đây chỉ là **đoạn method** nằm trong class `BootApplication` đã có ở mục 3, không phải file Java độc lập.

Trong hệ thống thực, các lựa chọn khác có thể gồm:
- `@Import` một configuration từ library.
- Auto-configuration có điều kiện, được đăng ký theo cơ chế Spring Boot phù hợp version.
- `scanBasePackages` có chủ đích khi library thật sự chứa component cần được quét.
- Đặt package dưới cùng một root namespace khi thiết kế cho phép.

Đừng dùng `scanBasePackages="com.example"` vô điều kiện nếu repo lớn: nó có thể quét nhầm bean của module khác, tạo nhiều configuration không mong muốn hoặc xung đột tên bean. **Module dependency không thay thế kiến trúc DI/component scanning.**

## 18. Vì sao không bật Spring Boot plugin cho mọi library?

Một anti-pattern trong Gradle:

```groovy
// Tránh làm vậy cho mọi project không phân biệt vai trò.
subprojects {
    apply plugin: 'org.springframework.boot'
}
```

Nếu `core-lib` không có `main`, `bootJar` có thể lỗi không tìm thấy main class hoặc xuất ra executable archive không phù hợp làm library dependency. Việc áp plugin ngầm từ root còn khiến module khó đoán cách build.

Với Maven, lỗi tương tự là đặt `spring-boot-maven-plugin` trong `<build><plugins>` của parent để mọi child đều kế thừa. Khi goal `repackage` chạy trên library, Maven có thể tạo Boot archive sai vai trò hoặc thất bại do không có entry point.

Cách phù hợp:
- **Maven:** để version/default config của plugin trong `pluginManagement` ở parent; chỉ app khai báo plugin ở `build.plugins`.
- **Gradle:** để Java/toolchain/test conventions trong plugin chung; chỉ module runnable ứng dụng áp dụng `org.springframework.boot` và có `bootJar`.
- **Library:** xuất plain JAR để consumer import class đúng layout.
- **Build config:** không có lý do để sản xuất Boot executable JAR.

Một library có annotation Spring như `@Configuration` hoặc `@Component` vẫn **có thể là library JAR**; loại artifact phụ thuộc trách nhiệm deploy, không phụ thuộc việc có import Spring package nào.

## 19. Test từng tầng và kiểm tra build

Tách test theo trách nhiệm giúp xác định lỗi ở đâu:

| Test | Module | Mục tiêu |
| --- | --- | --- |
| Unit test hàm/thuật toán | `core-lib` | Chứng minh Java logic không phụ thuộc Spring context |
| Wiring/context integration test | `boot-app` | Chứng minh bean library được app kết nối đúng |
| HTTP adapter test | `boot-app` | Chứng minh endpoint/JSON/status xử lý đúng |
| Executable JAR smoke test | CI/deploy | Chứng minh artifact thật chạy và trả HTTP đúng |
| Build convention tests | `build-logic` / POM validation | Chứng minh quy tắc build không làm hỏng các module |

Ở ví dụ, `BootApplicationTest` dùng `@SpringBootTest` và JUnit Jupiter để kiểm tra wiring. Nếu thêm JUnit tests vào `core-lib` thuần Java, module thư viện phải **tự có dependency test thích hợp**, không được giả định test dependency của app sẽ tự chảy ngược sang library.

### 19.1. Maven CI

Chạy từ root:

```bash
./mvnw -B clean verify
```

Nếu chỉ cần build app cùng dependencies trong reactor:

```bash
./mvnw -B -pl boot-app -am clean verify
```

`-B` là batch mode, phù hợp CI. Lấy test XML từ `boot-app/target/surefire-reports` và các module có test. JAR deploy là `boot-app/target/boot-app-1.0.0.jar`, không phải `core-lib/target/core-lib-1.0.0.jar`.

### 19.2. Gradle CI

```bash
./gradlew :boot-app:test :boot-app:bootJar
```

Để build toàn bộ projects, có thể dùng `./gradlew build` và kiểm tra task graph thực tế. Test reports mặc định thường ở `boot-app/build/test-results/test` và `boot-app/build/reports/tests/test`.

Sau build, xác minh:
1. Plain JAR `core-lib` thực sự chứa `GreetingService.class`.
2. Boot JAR có `BOOT-INF/classes/...BootApplication.class` và nested `BOOT-INF/lib/core-lib-1.0.0.jar`.
3. `java -jar` startup thành công.
4. `GET /hello` trả `hello-from-core-lib`.
5. Pipeline deploy **đúng artifact**, không dùng wildcard chọn JAR đầu tiên.

Một build xanh nhưng không tạo/kiểm tra artifact cuối **chưa đủ** để chứng minh khả năng deploy. Cũng đừng lấy build logic `build-logic` làm artifact Java để publish như thư viện nghiệp vụ.

## 20. Khác biệt về phiên bản và publication

Maven:
- Parent `build-parent` có `groupId:artifactId:version` và packaging `pom`.
- `core-lib` và `boot-app` có artifact riêng; bài mẫu dùng chung version `1.0.0`.
- `dependencyManagement` chọn version của core-lib nhưng app vẫn khai báo dependency thật.
- `pluginManagement` chọn version/config của Maven plugins nhưng không tự áp dụng Boot plugin ở library.
- Nếu corporate parent không phải Boot parent, import BOM và khai báo plugin execution phù hợp.

Gradle:
- `java-common-conventions` đặt Java toolchain/group/version chung ở subprojects áp dụng plugin.
- Gradle `project(':core-lib')` resolve project dependency qua outgoing variants, không copy JAR thủ công.
- Spring Boot plugin version và BOM/dependency version là các khái niệm riêng, cần giữ tương thích.
- `build-logic` chứa plugin code cho build, có thể được version hóa riêng nếu sau này publish cho nhiều repository.

Nếu `core-lib` được nhiều ứng dụng tiêu thụ theo lịch phát hành khác nhau, cân nhắc **version độc lập**, compatibility rules và repository publish. Nếu app và library luôn phát hành chung, một version đồng bộ thường đơn giản hơn. Không đổi tên file `.jar` thủ công để thay version mà không cập nhật dependency coordinates/POM/publication metadata.

## 21. Khắc phục sự cố thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Kiểm tra / sửa |
| --- | --- | --- |
| Maven `boot-app` báo không tìm thấy `core-lib` | Chưa build qua reactor, version không khớp, library chưa install | Chạy ở root với `-pl boot-app -am`, xem `dependency:tree` |
| Maven không resolve `build-parent` | Sai `<relativePath>` hoặc parent coordinates | Đối chiếu `../build-parent/pom.xml` và group/version |
| Root Maven không thấy module | `<module>` sai path hoặc thiếu POM con | Kiểm tra root aggregator và thư mục module |
| Library Maven bị `repackage` | Boot plugin kế thừa ở `build.plugins` parent | Chỉ app bật plugin, parent quản lý version trong `pluginManagement` |
| Gradle không tìm thấy `java-common-conventions` | Included build/configuration chưa đúng | Kiểm tra `pluginManagement.includeBuild`, tên script và `groovy-gradle-plugin` |
| Gradle không tìm thấy project `:core-lib` | `settings.gradle` thiếu/sai `include` | Kiểm tra `./gradlew projects` |
| `core-lib` Gradle bị tạo `bootJar` | Boot plugin áp dụng đại trà | Bỏ Spring Boot plugin khỏi library |
| Boot JAR thiếu library | App chưa khai báo dependency hoặc sai scope | Kiểm tra `runtimeClasspath` / Maven dependency tree |
| Gradle compiler không thấy `GreetingService` | Chỉ có task `dependsOn` chứ không có project dependency | Thêm `implementation project(':core-lib')` |
| ApplicationContext không tìm bean `GreetingService` | Package library ngoài component scan | `@Bean`, `@Import` hoặc scan phù hợp |
| HTTP 404 khi gọi `/hello` | Controller không được scan hoặc endpoint path khác | Kiểm tra package `com.example.app` và `@GetMapping` |
| Spring test không được phát hiện | Gradle thiếu `useJUnitPlatform()`, thiếu test engine; Maven Surefire sai | Xem `testRuntimeClasspath`/Surefire report |
| JAR ở app là plain, chạy `java -jar` lỗi | Boot plugin hoặc repackage/bootJar chưa chạy, chọn sai classifier | Kiểm tra `BOOT-INF/classes`, manifest, output filename |
| Library phụ thuộc ngược app | Module cycle / API boundary sai | Đẩy interface xuống thư viện/lower-level module |
| CI chạy local được nhưng pipeline fail | Wrapper/JDK/version/environment khác | Pin JDK/toolchain, kiểm tra plugins và dependency versions |
| `spring-boot-starter-web` lặp ở mọi library | Spring Boot hóa library không cần thiết | Chỉ dependency nào module thật sự cần |
| Chỉ có `<dependencyManagement>` nhưng app thiếu class library | Version management không kéo dependency | Khai báo `<dependency>core-lib</dependency>` trong app |
| Gradle root `build` không rõ module nào chạy | Task graph đa project khác dự kiến | Dùng project paths `:boot-app:bootJar` và `--dry-run` để kiểm chứng |

### 21.1. Lệnh chẩn đoán Maven

```bash
./mvnw -pl boot-app -am validate
./mvnw -pl boot-app -am dependency:tree
./mvnw -pl boot-app help:effective-pom -Doutput=effective-pom.xml
```

`effective-pom` cho biết parent/plugins/dependency management đã hợp nhất. `dependency:tree` cho biết vì sao core-lib/version của nó được chọn. Nếu là multi-module, nhớ chạy ở root và chọn đúng module.

### 21.2. Lệnh chẩn đoán Gradle

```bash
./gradlew projects
./gradlew :core-lib:tasks --all
./gradlew :boot-app:tasks --all
./gradlew :boot-app:dependencies --configuration runtimeClasspath
./gradlew :boot-app:dependencyInsight --dependency core-lib --configuration runtimeClasspath
./gradlew :boot-app:bootJar --dry-run
```

`--dry-run` chỉ hiển thị task graph, **không tạo hoặc kiểm tra file JAR**. Muốn biết class/runtime dependency có trong JAR thật không, phải chạy build và dùng `jar tf`.

## 22. Khi nào mở thêm module hoặc repository?

Ba vai trò trên là điểm khởi đầu, không phải giới hạn cứng:

- **API/contracts module:** chứa DTO/interface dùng chung nếu nhiều app cần cùng hợp đồng.
- **Domain module:** tách logic nghiệp vụ không phụ thuộc framework khỏi adapter web/persistence.
- **Persistence adapter module:** chứa JPA/JDBC implementation và dependency database riêng.
- **Batch/worker app module:** có main class và deployment khác REST app.
- **Integration-test module:** nếu test cần infrastructure và lifecycle riêng, được nối vào build đúng.
- **Build convention repo riêng:** chỉ khi nhiều repository cùng dùng và cần policy/version độc lập.

Mỗi module thêm chi phí quản lý dependency, kiểm thử, publish và phát hành. **Không tách module chỉ vì muốn chia thư mục**; nên tách khi có ranh giới trách nhiệm, coupling, dependency, ownership hoặc cadence phát hành rõ ràng.

Một lộ trình chuyển từ project đơn sang multi-module:
1. Tách Java domain/utility thuần thành `core-lib`.
2. Giữ main class, HTTP adapter và runtime configuration ở `boot-app`.
3. Đảm bảo dependency chỉ đi từ app xuống library, không vòng lặp.
4. Dời compiler/test/plugin rules chung vào Maven `build-parent` hoặc Gradle convention plugin.
5. Chỉ bật Spring Boot packaging trên app.
6. Chạy test và build reactor/task graph.
7. Kiểm tra JAR library vs executable JAR.
8. Cập nhật CI artifact paths và smoke tests trên **file deploy thật**.

## 23. Checklist kiến trúc và build

- [ ] Phân vai rõ **thư viện**, **ứng dụng**, **build configuration** và hướng dependency.
- [ ] `core-lib` chứa mã Java dùng lại, không có Spring Boot main/packaging plugin.
- [ ] `boot-app` có `@SpringBootApplication`, controller, DI/configuration và phụ thuộc `core-lib`.
- [ ] Build configuration không bị thêm vào Java runtime dependencies.
- [ ] Maven root aggregator `<modules>` liệt kê đúng các project; các POM con dùng đúng `build-parent`.
- [ ] Maven parent dùng `dependencyManagement`/`pluginManagement` đúng; chỉ app bật `spring-boot-maven-plugin`.
- [ ] Nếu không kế thừa Boot parent, Maven app có version và execution `repackage` phù hợp.
- [ ] Gradle `settings.gradle` phân biệt `include 'core-lib','boot-app'` với `pluginManagement.includeBuild('build-logic')`.
- [ ] Gradle convention plugin Java không áp dụng Boot plugin cho library.
- [ ] Gradle app khai báo `implementation project(':core-lib')`, không chỉ `dependsOn` hay copy file JAR thủ công.
- [ ] Bean wiring/component scan qua module đã được kiểm thử; không mặc định mọi class trong dependency trở thành Spring bean.
- [ ] Maven reactor với `-am` hoặc Gradle project dependency build đúng thứ tự.
- [ ] Test JUnit Platform/Surefire được phát hiện, report ghi nhận kết quả.
- [ ] Plain library JAR chứa class ở root; app Boot JAR chứa `BOOT-INF/classes` và `BOOT-INF/lib/core-lib-1.0.0.jar`.
- [ ] `java -jar` app chạy được, `GET /hello` trả `hello-from-core-lib`.
- [ ] CI/CD chỉ lấy executable artifact của app; không nhầm với thư viện hay plain JAR.
- [ ] Java, Spring Boot, Gradle/Maven plugins và module versions được quản lý nhất quán.

**Kết luận:** **Thư viện** sở hữu *mã và API tái sử dụng*, đóng gói **plain JAR**. **Ứng dụng** sở hữu *entry point, DI và vận hành*, đóng gói **Spring Boot executable JAR/WAR**. **Build configuration** sở hữu *cách build* và được kế thừa/áp dụng mà không đi vào runtime. Maven cần phân biệt **aggregator và parent**; Gradle cần phân biệt **subproject và included build convention plugin**. Từ đó mới có dependency graph rõ ràng, build tái lập được và artifact deploy đúng chức năng.

## Tài liệu tham khảo

- [Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Maven — POM Reference](https://maven.apache.org/pom.html)
- [Spring Boot 3.3 — Using the Maven Plugin](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html)
- [Spring Boot 3.3 — Gradle Plugin Packaging](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Gradle — Convention Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html)
- [Gradle — Precompiled Script Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html)
- [Gradle — Sharing Build Logic Between Subprojects](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html)
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)