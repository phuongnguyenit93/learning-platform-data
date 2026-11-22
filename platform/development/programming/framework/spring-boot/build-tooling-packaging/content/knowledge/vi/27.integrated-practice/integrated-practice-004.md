# Thiết kế ứng dụng đa-mô-đun với thư viện chung được đóng gói đúng

## 1. Bài thực hành tổng hợp: module và artifact

Khi một Spring Boot application lớn dần, việc đặt domain, business rules, persistence, web endpoints và integration code trong một module khiến build khó kiểm soát và code khó tái sử dụng. Tách module giúp xác định ranh giới phụ thuộc, kiểm thử độc lập và chia sẻ code giữa nhiều ứng dụng.

Một module Java được dùng làm thư viện phải được đóng gói như **JAR thư viện thông thường**. Executable Spring Boot JAR có cấu trúc riêng: application classes nằm trong `BOOT-INF/classes` và dependencies nằm trong `BOOT-INF/lib`. Module khác không thể đọc classes trong executable archive đó như một JAR thư viện thông thường.

Bài thực hành tổng hợp này hướng dẫn thiết kế multi-module Spring Boot với Maven là ví dụ chính, kèm mô hình tương ứng cho Gradle. Trọng tâm là cấu trúc module, dependency graph, quản lý version và cách đóng gói shared library để ứng dụng tiêu thụ đúng artifact.

Sau bài này, bạn có thể phân biệt aggregator POM, parent POM, BOM và module dependency; thiết kế shared library có ranh giới rõ; cấu hình Maven reactor; chọn packaging đúng; quản lý dependency scopes và version; xác minh JAR; build module trong reactor hoặc publish library để nhiều repository cùng sử dụng.

## 2. Chọn ranh giới module

Ví dụ một hệ thống catalog:

| Module | Trách nhiệm | Artifact |
| --- | --- | --- |
| `shared-kernel` | Value objects, domain primitives, interfaces và code dùng chung | JAR thường |
| `catalog-app` | HTTP API, application services, runtime configuration và entry point | Executable Boot JAR |
| `catalog-persistence` | Repository implementations, database mapping và migrations | JAR thường |
| `catalog-messaging` | Message adapters, producers/consumers | JAR thường |
| `catalog-contracts` | DTO/event contracts được nhiều service cùng dùng | JAR thường |

Không cần tạo tất cả module ngay từ đầu. Chỉ tách khi có ranh giới trách nhiệm hoặc nhu cầu tái sử dụng đủ rõ.

### 2.1. Dependency direction

Một dependency graph lành mạnh có hướng từ application đến các library/adapter mà nó sử dụng:

~~~text
             catalog-app
              /      \
             v        v
    shared-kernel   catalog-persistence
             ^
             |
      catalog-contracts
~~~

catalog-app phụ thuộc shared-kernel và catalog-persistence. catalog-persistence có thể phụ thuộc shared-kernel để dùng domain types. shared-kernel không phụ thuộc catalog-app. catalog-contracts chứa kiểu dữ liệu giao tiếp ổn định, không chứa controller hoặc database implementation.

Tránh dependency cycle như shared-kernel → catalog-app → shared-kernel. Nếu hai module cần dùng code của nhau, hãy trích abstraction chung vào module nhỏ hơn hoặc điều chỉnh ranh giới để dependency chỉ đi một hướng.

### 2.2. Giữ shared library có phạm vi rõ

Module common hoặc utils dễ trở thành nơi chứa mọi thứ, khiến API lớn và khó thay đổi. Hãy đặt tên theo năng lực/ngữ cảnh như catalog-domain, identity-contracts, observability-support. Chỉ dùng shared-kernel cho abstraction thực sự ổn định và được nhiều module dùng.

Giữ public API nhỏ. Không export implementation classes chỉ vì chúng đang nằm trong cùng module.

## 3. Cấu trúc repository Maven

~~~text
catalog-platform/
├── pom.xml
├── shared-kernel/
│   ├── pom.xml
│   └── src/main/java/com/example/shared/
└── catalog-app/
    ├── pom.xml
    └── src/main/java/com/example/catalog/
~~~

Root POM quản lý version và liệt kê modules. Mỗi module có POM, source tree và artifact riêng.

Maven có hai khái niệm liên quan nhưng khác nhau:

- **Aggregation:** root POM liệt kê modules để Maven reactor build chúng cùng nhau.
- **Inheritance:** module khai báo root POM trong parent để kế thừa properties, dependency management, plugin management và cấu hình chung.

Một POM có thể vừa là aggregator vừa là parent. Hai vai trò này không bắt buộc nằm trong cùng một POM.

## 4. Root POM: parent, aggregator và dependency management

Ví dụ root pom.xml cho Spring Boot **4.1.2** và Java 17:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>catalog-platform</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>
    <modules>
        <module>shared-kernel</module>
        <module>catalog-app</module>
    </modules>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example</groupId>
                <artifactId>shared-kernel</artifactId>
                <version>${project.version}</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
~~~

- `packaging=pom` cho biết root là aggregator/parent, không phải JAR chạy được.
- `modules` khai báo các thư mục tham gia reactor.
- `parent` kế thừa cấu hình từ Spring Boot Starter Parent.
- `java.version` đặt Java release mà parent/plugin sử dụng.
- `dependencyManagement` quản lý version của shared module; nó không tự thêm dependency vào module con.
- Version module nội bộ trong ví dụ này theo version của platform.

Starter Parent quản lý nhiều dependency versions và cấu hình plugin. Nếu tổ chức dùng corporate parent riêng, có thể import `spring-boot-dependencies` BOM vào `dependencyManagement`. Import BOM quản lý dependency versions; nó không tự thêm Spring Boot Maven Plugin execution vào từng module.

## 5. Shared library: đóng gói thành JAR Java thông thường

POM của shared-kernel/pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>catalog-platform</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>shared-kernel</artifactId>
    <packaging>jar</packaging>
</project>
~~~

Module này có packaging jar. Maven JAR Plugin tạo package path thông thường, ví dụ:

~~~text
com/example/shared/GreetingFormatter.class
~~~

Nó không cần Spring Boot loader, `BOOT-INF/classes` hoặc `BOOT-INF/lib`. Thư viện dùng làm dependency thông thường không cần Spring Boot Maven Plugin.

### 5.1. Ví dụ class dùng chung

File shared-kernel/src/main/java/com/example/shared/GreetingFormatter.java:

~~~java
package com.example.shared;

public final class GreetingFormatter {
    public String format(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + name.trim() + "!";
    }
}
~~~

Đây là Java library code thuần. Nó không cần biết ứng dụng nào sẽ gọi nó hoặc application khởi động ra sao.

Build riêng module trong reactor:

~~~bash
mvn -pl :shared-kernel clean verify
~~~

Nếu module này phụ thuộc vào các module nội bộ khác, thêm `-am` để Maven build cả những module dependency cần thiết.

## 6. Application module: tiêu thụ shared library

POM của catalog-app/pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>catalog-platform</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>catalog-app</artifactId>
    <packaging>jar</packaging>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>shared-kernel</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Dependency shared-kernel không cần version trong module vì root quản lý version trong dependencyManagement. Spring Boot dependency version cũng được quản lý bởi Starter Parent.

Starter Parent cấu hình sẵn execution ID `repackage`. Chỉ khai báo plugin trong `build/plugins` của application module để kích hoạt executable packaging. Module library không khai báo plugin nên giữ JAR thuần.

### 6.1. Sử dụng class từ library

File catalog-app/src/main/java/com/example/catalog/GreetingController.java:

~~~java
package com.example.catalog;

import com.example.shared.GreetingFormatter;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingFormatter formatter;

    public GreetingController(GreetingFormatter formatter) {
        this.formatter = formatter;
    }

    @GetMapping(value = "/greet", produces = MediaType.TEXT_PLAIN_VALUE)
    public String greet(@RequestParam(defaultValue = "world") String name) {
        return formatter.format(name);
    }
}
~~~

File catalog-app/src/main/java/com/example/catalog/CatalogApplication.java:

~~~java
package com.example.catalog;

import com.example.shared.GreetingFormatter;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    GreetingFormatter greetingFormatter() {
        return new GreetingFormatter();
    }
}
~~~

Bean được đăng ký tường minh bằng `@Bean`. Component scanning mặc định quét package của application class và các package con. Nếu library nằm ở package sibling như `com.example.shared`, nó không tự động được quét chỉ vì JAR đã có trên classpath. Với thư viện có Spring components, dùng `@Import`, `@ComponentScan` có chủ đích hoặc auto-configuration phù hợp.

Chạy ứng dụng sau khi build:

~~~bash
java -jar catalog-app/target/catalog-app-1.0.0-SNAPSHOT.jar
~~~

Gọi endpoint:

~~~bash
curl "http://localhost:8080/greet?name=Ada"
~~~

Output:

~~~text
Hello, Ada!
~~~

## 7. Maven reactor và build order

Khi chạy ở root:

~~~bash
mvn clean verify
~~~

Maven reactor thu thập modules, sắp xếp theo quan hệ phụ thuộc và build theo thứ tự phù hợp. Vì catalog-app khai báo dependency trực tiếp đến shared-kernel, reactor build library trước application.

Có thể build riêng application cùng các module cần thiết:

~~~bash
mvn -pl :catalog-app -am clean verify
~~~

- `-pl :catalog-app` chọn module theo artifactId.
- `-am` (also make) thêm các module trong reactor mà module được chọn phụ thuộc.
- `clean verify` xóa output cũ và chạy lifecycle đến verify, gồm compile, test và package.

Khai báo version trong dependencyManagement không tự tạo quan hệ build order. Quan hệ reactor được hình thành khi module thực sự khai báo dependency đến module khác. Chỉ liệt kê hai module trong `modules` cũng không có nghĩa module sau tự động phụ thuộc module trước.

Các lệnh hữu ích:

~~~bash
mvn -pl :shared-kernel -am clean verify
mvn -pl :catalog-app -am package
mvn -pl :catalog-app dependency:tree
~~~

Maven reactor cũng hỗ trợ `-amd` để build các module phụ thuộc vào module được chọn, `-N` để tắt recursive build và `-rf` để resume từ một project.

## 8. Library JAR và executable Boot JAR có cấu trúc khác nhau

| Artifact | Cấu trúc chính | Dùng làm dependency Java thông thường? |
| --- | --- | --- |
| JAR library | Package classes ở root, ví dụ com/example/shared/GreetingFormatter.class | Có |
| Executable Spring Boot JAR | Classes ứng dụng ở BOOT-INF/classes, dependency JAR ở BOOT-INF/lib | Không dùng như library JAR thông thường |
| Executable Spring Boot WAR | Classes ở WEB-INF/classes, dependencies ở WEB-INF/lib và WEB-INF/lib-provided | Dùng để triển khai/chạy theo WAR layout |

Spring Boot repackage biến archive được tạo ở package phase thành executable archive để chạy bằng java -jar. Mặc định, goal này thay artifact chính bằng archive đã repackaged; artifact thường được giữ lại với hậu tố .original trong thư mục output.

Khi module khác phụ thuộc vào JAR đã repackaged, Java compiler/runtime không thể tìm class theo package path thông thường vì classes nằm trong BOOT-INF/classes. Vì vậy, **module được tái sử dụng phải xuất bản JAR thường**.

### 8.1. Cấu hình đúng

- shared-kernel: Maven jar, không chạy Spring Boot repackage.
- catalog-app: Maven jar và chạy Spring Boot repackage.
- Các adapter/library khác: JAR thường, chỉ phụ thuộc vào API cần thiết.
- Executable artifact chỉ được tạo ở module đại diện cho application.

Đừng thêm Spring Boot Maven Plugin vào parent build chung rồi vô tình kích hoạt repackage ở tất cả module. Nếu cần quản lý plugin version tập trung, dùng `pluginManagement` ở parent và chỉ khai báo plugin trong `build/plugins` của application module.

## 9. Khi một module cần cả library JAR và executable JAR

Một số module vừa cung cấp API cho module khác vừa có chương trình demo/CLI có thể chạy độc lập. Khi đó có thể giữ artifact thường và attach executable artifact với classifier, ví dụ `exec`.

Nếu dùng Spring Boot Starter Parent, customize execution ID `repackage`:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>repackage</id>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Kết quả mong muốn:

~~~text
shared-kernel-1.0.0.jar
shared-kernel-1.0.0-exec.jar
~~~

Artifact không có classifier là JAR thường để module khác phụ thuộc; artifact có classifier exec là executable archive để chạy độc lập. Consumer thông thường không khai báo classifier nên nhận JAR thường.

Khi parent đã cung cấp execution ID repackage, chỉ customize đúng execution đó. Tạo execution ID khác có thể khiến goal chạy hai lần. Nếu không dùng Starter Parent, khai báo plugin version và một execution repackage ở module cần thiết.

## 10. Dependency scopes và API của library

| Maven scope | Compile classpath | Runtime classpath | Truyền transitive cho consumer? |
| --- | --- | --- | --- |
| compile (mặc định) | Có | Có | Có |
| provided | Có | Không theo Maven runtime classpath | Không |
| runtime | Không | Có | Có ở runtime |
| test | Chỉ test | Chỉ test | Không |
| system | Theo systemPath | Theo systemPath | Không khuyến nghị |
| import | Dùng để import BOM trong dependencyManagement | Không phải scope dependency thông thường | Import dependency management |

### 10.1. Dependency cần thiết cho public API

Nếu public method của library nhận/trả một type thuộc dependency bên ngoài, consumer thường cần dependency đó trên compile classpath. Maven compile scope là mặc định và được truyền transitive.

Ví dụ library public API dùng type Money từ artifact khác:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>money-types</artifactId>
    <version>2.1.0</version>
</dependency>
~~~

Nếu dependency chỉ được dùng bên trong implementation và không xuất hiện trong public API, hãy cân nhắc thiết kế API để consumer không cần phụ thuộc trực tiếp vào type đó. Maven không có scope tương đương chính xác với Gradle api/implementation; kiểm soát dependency exposure bằng thiết kế API, scopes, optional dependencies và exclusions phù hợp.

### 10.2. Optional, provided và systemPath

Nếu library có tích hợp tùy chọn với hệ thống ngoài, có thể đánh dấu dependency là optional:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>remote-adapter</artifactId>
    <version>2.1.0</version>
    <optional>true</optional>
</dependency>
~~~

Consumer cần tính năng đó phải khai báo dependency tương ứng. Đừng đánh dấu optional cho dependency mà mọi public API hoặc mọi code path đều bắt buộc phải có.

`provided` thường biểu thị dependency được môi trường triển khai cung cấp và không được truyền transitive theo Maven dependency semantics. Đừng đặt dependency thành provided chỉ để làm JAR nhỏ hơn. Spring Boot repackage có quy tắc riêng và mặc định bao gồm cả provided dependencies đã khai báo trong project vì chúng có thể cần cho runtime của executable archive.

Không dùng `systemPath` trỏ đến file như ../shared-kernel/target/shared-kernel.jar. Cách này phụ thuộc working directory, không tham gia dependency graph bình thường và khó dùng trên CI. Dùng Maven coordinates; trong cùng reactor, Maven tìm artifact theo module dependency, còn giữa các build độc lập thì lấy artifact từ repository.

## 11. Dependency management, BOM và plugin management

| Cơ chế | Quản lý | Tự thêm dependency/plugin vào module? |
| --- | --- | --- |
| dependencyManagement | Dependency versions, scopes và exclusions mặc định | Không |
| BOM import | Dependency management từ một POM khác | Không |
| pluginManagement | Plugin versions và default plugin configuration | Không tự kích hoạt plugin execution |

Ví dụ root quản lý version của library nội bộ:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>shared-kernel</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Module consumer chỉ cần khai báo coordinates:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>shared-kernel</artifactId>
</dependency>
~~~

Nếu dùng Spring Boot BOM mà không dùng Starter Parent, import BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.1.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

BOM quản lý dependency versions. Plugin version và execution của Spring Boot Maven Plugin cần được cấu hình riêng trong pluginManagement/build/plugins.

## 12. Publish shared library độc lập

Nếu application và library ở cùng repository/reactor, Maven có thể build trực tiếp từ source modules. Nếu library nằm ở repository khác hoặc được nhiều nhóm dùng, hãy publish artifact chuẩn.

~~~bash
mvn clean verify
mvn install
mvn deploy
~~~

- verify chạy các bước kiểm tra trước khi phát hành.
- install cài artifacts vào local Maven repository của máy đang build; hữu ích cho phát triển và kiểm thử consumer trên cùng máy.
- deploy đưa artifacts và POM lên remote repository đã cấu hình.
- install không thay thế publish cho các developer hoặc CI khác.

Consumer khai báo groupId, artifactId và version đã phát hành. Không copy JAR bằng tay vào thư mục project, không commit binary vào source tree và không dựa vào local repository của một developer.

### 12.1. Quản lý version

**Cùng release version:** tất cả module trong platform dùng chung version, ví dụ 1.4.0. Cách này đơn giản khi chúng được release cùng nhau.

**Version độc lập:** library có version riêng, ví dụ shared-kernel:2.3.1, application release theo chu kỳ riêng. Cách này phù hợp khi library được nhiều ứng dụng tiêu thụ và có compatibility policy rõ.

Với SNAPSHOT, consumer có thể nhận thay đổi chưa phát hành theo repository update policy. Release version nên bất biến; nếu cần thay đổi code, phát hành version mới. Không republish một release version với nội dung khác.

Nếu library build độc lập nhưng kế thừa parent POM, parent coordinates cũng phải resolve được. Publish parent trước hoặc dùng corporate parent đã có sẵn.

## 13. Kiểm tra dependency graph và artifact

Đừng chỉ dựa vào BUILD SUCCESS. Kiểm tra cả dependency graph lẫn nội dung archive.

### 13.1. Dependency tree

~~~bash
mvn -pl :catalog-app dependency:tree -Dincludes=com.example:shared-kernel
mvn -pl :catalog-app dependency:tree -Dverbose
~~~

Xác nhận đúng groupId/artifactId/version, dependency scope phù hợp, không có version cũ bị kéo vào và không có duplicate artifact ngoài dự kiến.

### 13.2. Kiểm tra library JAR

~~~bash
jar tf shared-kernel/target/shared-kernel-1.0.0-SNAPSHOT.jar
~~~

Tìm class:

~~~text
com/example/shared/GreetingFormatter.class
~~~

Library JAR phải có package path thông thường ở root. Nếu thấy BOOT-INF/classes/com/example/shared/GreetingFormatter.class trong artifact được dùng làm dependency, module đang bị repackaged như Boot application.

### 13.3. Kiểm tra executable application JAR

~~~bash
jar tf catalog-app/target/catalog-app-1.0.0-SNAPSHOT.jar
~~~

Các entry quan trọng:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/com/example/catalog/CatalogApplication.class
BOOT-INF/lib/shared-kernel-1.0.0-SNAPSHOT.jar
BOOT-INF/lib/spring-boot-*.jar
~~~

Tên version và dependency JAR cụ thể phụ thuộc build. Điều cần xác nhận là application classes nằm trong BOOT-INF/classes và shared library được đóng gói như dependency JAR trong BOOT-INF/lib.

### 13.4. Chạy artifact cuối

~~~bash
java -jar catalog-app/target/catalog-app-1.0.0-SNAPSHOT.jar
curl "http://localhost:8080/greet?name=Ada"
~~~

Expected response:

~~~text
Hello, Ada!
~~~

Nếu runtime báo ClassNotFoundException hoặc NoClassDefFoundError, kiểm tra library JAR đã được đưa vào executable archive chưa, version/scope có đúng không và class có nằm ở package path đúng không.

## 14. Component scanning và Spring configuration trong library

Một JAR thuần có thể chứa Spring components, nhưng việc có mặt trên classpath không đồng nghĩa Spring tự động quét mọi package.

Mặc định @SpringBootApplication bao gồm component scanning từ package của application class xuống các package con. Nếu application ở com.example.catalog còn library component ở com.example.shared, hai package là sibling; component trong shared không tự động được phát hiện.

Có ba hướng xử lý:

1. **Đăng ký rõ ràng:** application khai báo @Bean hoặc @Import cấu hình từ library.
2. **Mở rộng component scan:** dùng @ComponentScan với base packages được kiểm soát.
3. **Tạo auto-configuration module:** library cung cấp cấu hình tự động và metadata theo cơ chế Spring Boot auto-configuration.

Với library Spring Boot có auto-configuration, metadata được đặt tại:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Đừng đưa @SpringBootApplication vào shared library. Application module nên sở hữu entry point, component scan root và runtime configuration của chính nó.

## 15. Gradle multi-project: mô hình tương đương

Gradle sử dụng settings.gradle(.kts) để định nghĩa root project và subprojects. Project dependency tạo quan hệ build order và đưa output/dependencies của module được yêu cầu vào classpath consumer.

Cấu trúc:

~~~text
catalog-platform/
├── settings.gradle.kts
├── build.gradle.kts
├── shared-kernel/build.gradle.kts
└── catalog-app/build.gradle.kts
~~~

settings.gradle.kts:

~~~kotlin
rootProject.name = "catalog-platform"
include(":shared-kernel", ":catalog-app")
~~~

Root build.gradle.kts:

~~~kotlin
plugins {
    id("org.springframework.boot") version "4.1.2" apply false
}
allprojects {
    group = "com.example"
    version = "1.0.0-SNAPSHOT"
}
~~~

Shared library build.gradle.kts:

~~~kotlin
plugins {
    id("java-library")
}
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Java Library Plugin cung cấp hai cấu hình:

- `api`: dependency được export tới compile classpath của consumer khi public API của library cần type đó.
- `implementation`: dependency chỉ dùng nội bộ, không bị lộ vào compile classpath của consumer.

Application build.gradle.kts:

~~~kotlin
plugins {
    java
    id("org.springframework.boot")
}
dependencies {
    implementation(project(":shared-kernel"))
    implementation("org.springframework.boot:spring-boot-starter-web:4.1.2")
}
~~~

Project dependency implementation(project(":shared-kernel")) cho Gradle biết application cần shared library. Gradle build library trước và đưa compiled classes cùng transitive dependencies vào classpath của application. Spring Boot plugin chỉ áp dụng ở catalog-app; task bootJar tạo executable archive, còn shared module dùng task jar để tạo JAR thông thường.

Các lệnh kiểm tra:

~~~bash
./gradlew :shared-kernel:jar
./gradlew :catalog-app:bootJar
./gradlew :catalog-app:dependencies --configuration runtimeClasspath
~~~

Không cấu hình bootJar cho shared library nếu nó chỉ được tiêu thụ như dependency Java.

## 16. CI pipeline, lỗi thường gặp và quy trình triển khai

CI nên build từ root reactor để dependency giữa modules được giải quyết trong cùng một lần build.

Ví dụ GitHub Actions job:

~~~yaml
name: Multi-module build
on:
  push:
  pull_request:
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Verify reactor
        run: ./mvnw -B -ntp clean verify
~~~

Quality gates nên gồm: build toàn reactor từ clean workspace; unit tests của library và application đều chạy; dependency tree không có version ngoài policy; shared library JAR không chứa Boot layout; application JAR có manifest và Boot layout hợp lệ; runtime smoke test chạy được bằng java -jar; artifact release được lưu hoặc publish; build không phụ thuộc JAR còn sót trong workspace/local repository của runner.

Nếu thay đổi ở shared-kernel, các downstream modules có thể cần build lại:

~~~bash
./mvnw -pl :shared-kernel -amd verify
~~~

### 16.1. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Application không tìm thấy class trong shared library | Dependency chưa khai báo hoặc scope không phù hợp | Kiểm tra POM và dependency tree |
| Module library được đóng gói thành Boot JAR | Spring Boot repackage chạy trong library | Bỏ Boot plugin khỏi library hoặc dùng classifier để giữ JAR thường |
| Maven build app riêng bị thiếu shared artifact | Chỉ build app mà không build/install/deploy library | Dùng -am trong reactor hoặc publish library |
| Module chạy local nhưng CI không chạy | Dựa vào JAR đã cài trong local Maven repository | Build toàn reactor hoặc lấy artifact từ repository |
| Hai module dùng version shared library khác nhau | Version khai báo rải rác | Quản lý version tập trung và kiểm tra dependency tree |
| JAR thường bị thay bằng executable archive | Repackage không có classifier | Bỏ plugin ở library hoặc đặt classifier |
| Repackage chạy hai lần | Parent execution và child execution khác ID | Customize execution ID repackage thay vì thêm ID mới |
| Shared Spring bean không được tìm thấy | Package library nằm ngoài component scan root | Dùng @Import, @ComponentScan hoặc auto-configuration |
| Dependency cycle giữa modules | Ranh giới module và chiều phụ thuộc chưa rõ | Trích abstraction/contracts |
| App JAR thiếu shared library | Dependency bị excluded, scope sai hoặc packaging sai | Kiểm tra BOOT-INF/lib |
| Library JAR có BOOT-INF/classes | Đang dùng nhầm executable Boot JAR | Build library bằng JAR plugin |
| Dùng systemPath chạy được local nhưng fail CI | Đường dẫn local không tồn tại trên runner | Dùng Maven coordinates |
| Gradle app không build shared project trước | Dùng file JAR thủ công | Dùng implementation(project(":shared-kernel")) |
| Runtime thiếu class dù compile pass | Dependency bị exclude khỏi runtime archive | Kiểm tra runtimeClasspath và executable archive |

### 16.2. Quy trình triển khai

1. Vẽ dependency graph; xác định application, library, contracts và adapters; kiểm tra không có cycle.
2. Tạo aggregator/parent; root POM dùng packaging pom và khai báo modules.
3. Quyết định version policy: cùng version theo platform hoặc version độc lập.
4. Tạo shared library với packaging jar và code framework-independent khi có thể.
5. Tạo application module và khai báo dependency tới library bằng Maven coordinates.
6. Chỉ bật Spring Boot repackage ở application; library giữ JAR thường.
7. Quản lý dependencies bằng dependencyManagement/BOM, scopes và optional có chủ đích.
8. Build bằng reactor với mvn clean verify hoặc mvn -pl :catalog-app -am verify.
9. Dùng jar tf xác nhận layout của library JAR và executable application JAR.
10. Chạy smoke test bằng java -jar và gọi endpoint.
11. Dùng mvn install cho local development và mvn deploy cho remote repository.
12. Thêm CI gates cho tests, dependency tree, artifact layout và runtime.

## 17. Bài tập tự kiểm tra

**1. Aggregator POM và parent POM khác nhau thế nào?**

Đáp án: Aggregator liệt kê modules để reactor build cùng nhau; parent cung cấp cấu hình được module kế thừa. Một POM có thể làm cả hai vai trò.

**2. Vì sao shared library nên dùng packaging jar?**

Đáp án: Nó tạo JAR với classes ở package path thông thường, có thể được compiler/classloader của module khác sử dụng trực tiếp.

**3. Vì sao không nên chạy Spring Boot repackage trong mọi module?**

Đáp án: Repackage chuyển classes vào Boot archive layout. Executable JAR không dùng làm library dependency thông thường.

**4. dependencyManagement có tự thêm shared library vào application không?**

Đáp án: Không. Nó quản lý version/configuration; application vẫn phải khai báo dependency trong dependencies.

**5. Maven reactor biết build shared library trước application bằng cách nào?**

Đáp án: Application khai báo project dependency đến shared library; reactor dùng quan hệ đó để sắp xếp build order.

**6. Khi nào dùng -pl :catalog-app -am?**

Đáp án: Khi chỉ muốn build application và các module trong reactor mà nó phụ thuộc.

**7. Class executable Boot JAR nằm ở đâu?**

Đáp án: Application classes nằm trong BOOT-INF/classes; dependencies nằm trong BOOT-INF/lib.

**8. Làm sao giữ cả JAR thường và executable JAR trong một module?**

Đáp án: Cấu hình Spring Boot repackage với classifier, ví dụ exec, để executable archive được attach bên cạnh artifact thường.

**9. Vì sao shared Spring bean không tự được phát hiện?**

Đáp án: Component scanning mặc định bắt đầu từ package của application class và các package con; package sibling cần được import hoặc scan rõ ràng.

**10. Gradle api và implementation khác nhau thế nào?**

Đáp án: api export dependency tới compile classpath của consumer khi public API cần type đó; implementation giữ dependency trong implementation của library.

## 18. Tài liệu tham khảo chính thức

1. [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
2. [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
3. [Apache Maven — Dependency Scopes](https://maven.apache.org/repositories/dependencies.html)
4. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
5. [Apache Maven — Maven Install Plugin](https://maven.apache.org/plugins/maven-install-plugin/)
6. [Apache Maven — Maven Deploy Plugin](https://maven.apache.org/plugins/maven-deploy-plugin/)
7. [Spring Boot 4.1.2 — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
8. [Spring Boot 4.1.2 — Maven Plugin Goals](https://docs.spring.io/spring-boot/maven-plugin/goals.html)
9. [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
10. [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html)
11. [Gradle — The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
12. [Gradle — Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies.html)
