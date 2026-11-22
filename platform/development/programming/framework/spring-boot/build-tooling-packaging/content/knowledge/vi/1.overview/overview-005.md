# Quan hệ giữa starter, BOM và plugin đóng gói trong Spring Boot

## 1. Mục tiêu

Sau bài này, bạn có thể phân biệt ba vai trò trong quá trình xây dựng ứng dụng Spring Boot:

- **Starter** trả lời câu hỏi **“Ứng dụng cần những thư viện nào để dùng một nhóm chức năng?”**
- **BOM (Bill of Materials)** trả lời câu hỏi **“Các thư viện đó nên dùng phiên bản nào để phối hợp với nhau?”**
- **Plugin đóng gói** trả lời câu hỏi **“Làm cách nào biến mã đã biên dịch và các thư viện runtime thành sản phẩm có thể chạy, phát hành hoặc tạo container image?”**

Ba thành phần bổ sung cho nhau nhưng không thay thế nhau. Một ứng dụng có thể khai báo đúng starter và được BOM quản lý phiên bản mà vẫn chỉ tạo ra JAR thông thường nếu chưa cấu hình đóng gói executable JAR.

**Phạm vi:** Maven và Gradle, tập trung vào việc hiểu và kiểm chứng dependency, build và artifact. Ví dụ dùng **Spring Boot 4.1.2, Java 17** để nhất quán; khi nâng phiên bản, cần cập nhật và kiểm tra tương thích theo tài liệu chính thức.

## 2. Bản đồ khái niệm

| Thành phần | Đối tượng | Nó làm gì? | Nó không tự làm gì? |
| --- | --- | --- | --- |
| Starter, ví dụ `spring-boot-starter-webmvc` | Dependency | Khai báo nhóm dependency phù hợp để viết ứng dụng MVC và kéo theo các dependency bắc cầu cần thiết. | Không ấn định toàn bộ chiến lược phiên bản, không biên dịch, không tự tạo JAR chạy bằng `java -jar`. |
| BOM, `org.springframework.boot:spring-boot-dependencies` | Dependency management / platform | Đưa ra bộ phiên bản được Spring Boot quản lý và kiểm thử cùng nhau. | Không tự thêm thư viện vào classpath, không chứa code ứng dụng, không điều khiển trực tiếp quy trình đóng gói. |
| Maven plugin `spring-boot-maven-plugin` | Build plugin | Cung cấp các goal như `repackage`, `run`, `build-image`; biến JAR/WAR thành executable archive theo cấu hình. | Không thay thế việc khai báo starter hoặc import BOM; không phải runtime dependency của ứng dụng. |
| Gradle plugin `org.springframework.boot` | Build plugin | Bổ sung và cấu hình task như `bootJar`, `bootRun`, `bootBuildImage` khi kết hợp với Java plugin. | Không mặc nhiên quản lý tất cả dependency nếu chưa áp dụng cơ chế BOM thích hợp. |
| Maven `spring-boot-starter-parent` | Parent POM | Gom các mặc định Maven, dependency management và plugin management; cấu hình sẵn execution `repackage` khi sử dụng Boot plugin. | Không phải một starter được khai báo trong `<dependencies>`; không trực tiếp kéo thư viện web vào ứng dụng. |

Dòng chảy tổng quát:

```text
Khai báo starter ──> dependency trực tiếp + dependency bắc cầu
                              │
                              ▼
                    BOM quản lý phiên bản
                              │
                              ▼
                    Resolve dependency graph
                              │
                              ▼
                 Biên dịch + chạy kiểm thử
                              │
                              ▼
             Maven/Gradle plugin đóng gói
                              │
                              ▼
        Executable JAR/WAR (hoặc container image)
                              │
                              ▼
                     java -jar / triển khai
```

Lưu ý: đây là sơ đồ trách nhiệm, không có nghĩa BOM “chạy” như một bước thực thi riêng trong build. Công cụ build áp dụng thông tin của BOM **khi phân giải dependency**; plugin chạy theo lifecycle/task được cấu hình.

## 3. Starter: chọn khả năng, kéo đúng tập thư viện

Starter thường là một artifact có POM khai báo các dependency liên quan. Thay vì tự chọn từng thư viện Spring MVC, logging, container nhúng và các dependency phụ trợ, bạn thêm starter tương ứng. Với Spring Boot 4, starter khuyến nghị cho ứng dụng Servlet MVC là `spring-boot-starter-webmvc`; tên cũ `spring-boot-starter-web` đã bị deprecated. Với ứng dụng reactive, cân nhắc `spring-boot-starter-webflux`. Các starter cho persistence, validation hoặc test phục vụ nhu cầu riêng, ví dụ `spring-boot-starter-data-jpa`, `spring-boot-starter-validation`, `spring-boot-starter-test`.

Ví dụ dependency Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Hai dependency trên **không ghi `<version>`** chỉ khi dự án đã nhận dependency management phù hợp từ parent hoặc BOM. Starter đưa các thư viện lên classpath; sau đó cơ chế **auto-configuration** của Spring Boot đánh giá classpath, bean và properties để cấu hình những thành phần phù hợp. Do đó không nên hiểu rằng “thêm starter” đồng nghĩa mọi tính năng luôn được bật: auto-configuration có điều kiện, có thể bị thay đổi bởi cấu hình, dependency bị exclude và bean do lập trình viên định nghĩa.

Có thể bỏ một dependency bắc cầu không mong muốn bằng `<exclusions>` (Maven) hoặc `exclude` (Gradle), nhưng phải đánh giá hậu quả. Ví dụ loại bỏ embedded server mà không khai báo server thay thế có thể khiến ứng dụng web không chạy như dự kiến.

## 4. BOM: thống nhất các phiên bản

**BOM** là một POM liệt kê phiên bản được quản lý của các dependency. `spring-boot-dependencies` quản lý nhiều thư viện Spring và bên thứ ba tương thích với một dòng Spring Boot. Khi khai báo dependency được BOM quản lý, bạn có thể bỏ phiên bản tại nơi sử dụng.

Điểm cần nhớ:

1. BOM **quản lý phiên bản**, không tự thêm dependency. Import BOM nhưng không khai báo starter sẽ không làm Spring MVC xuất hiện.
2. Dependency có `<version>` tường minh (hoặc rule/constraint Gradle khác) có thể thay đổi phiên bản được chọn; đừng cho rằng BOM luôn thắng mọi yêu cầu.
3. Một bản phát hành Spring Boot được thử nghiệm với tập phiên bản phụ thuộc tương ứng. Ghi đè các phiên bản nền tảng như Spring Framework, Jackson hoặc logging cần kiểm thử kỹ vì dễ phát sinh lỗi liên kết hoặc tương thích.
4. **Maven BOM import không mang theo plugin management** của parent. Đây là khác biệt thiết yếu khi dự án phải dùng parent POM riêng của tổ chức.
5. Nên đồng bộ dòng phiên bản BOM, Boot build plugin và các artifact Spring Boot; dùng một biến phiên bản chung nếu cấu hình cho phép.

### Maven: hai cách nhận BOM

**Cách A — kế thừa `spring-boot-starter-parent`:** parent đã đưa dependency management từ BOM vào dự án, đồng thời cung cấp mặc định compile/plugin. Bạn thường chỉ khai báo version ở thẻ `<parent>`.

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>
```

**Cách B — import BOM khi dùng parent khác hoặc không có parent Boot:**

```xml
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
```

Trong cách B, **phải chủ động cấu hình plugin và các mặc định build cần thiết**. Chỉ import `spring-boot-dependencies` không khiến Maven tự biết phiên bản `spring-boot-maven-plugin`, không tự thiết lập execution `repackage`, cũng không tương đương với việc kế thừa `spring-boot-starter-parent`.

### Gradle: hai cơ chế quản lý dependency

- **Gradle native BOM:** thêm `platform(...)` trong cấu hình dependency cần quản lý. Đây là lựa chọn gọn, không cần plugin quản lý dependency riêng.
- **Plugin `io.spring.dependency-management`:** khi dùng cùng Spring Boot Gradle plugin, BOM tương ứng với phiên bản Boot plugin được import tự động; cơ chế này hỗ trợ tùy chỉnh một số phiên bản qua property của BOM.

Với Gradle native `platform`, BOM đặt các **constraint**. Một constraint ở `implementation` không đồng nghĩa mọi cấu hình độc lập đều nhận nó; hãy đưa BOM vào những configuration cần thiết như `testImplementation` khi phù hợp. `enforcedPlatform` cưỡng chế mạnh hơn nhưng có thể ảnh hưởng các thành phần phụ thuộc, nên chỉ dùng khi có lý do rõ ràng.

## 5. Plugin đóng gói: tạo sản phẩm chạy được

Trong Maven, `spring-boot-maven-plugin` có goal `repackage`. Nó xử lý JAR/WAR đã được build để tạo **executable archive** chứa class ứng dụng, thư viện runtime và Spring Boot loader. Khi dùng Boot parent, execution `repackage` đã được định nghĩa; chỉ cần khai báo plugin tại `<build><plugins>`. Khi chỉ import BOM, cần khai báo version plugin và execution phù hợp.

Trong Gradle, plugin `org.springframework.boot` phối hợp với `java` plugin để tạo task `bootJar`; với WAR dùng `bootWar` khi cấu hình WAR tương ứng. Task `jar` chuẩn tạo JAR thông thường; task `bootJar` tạo executable JAR. Với cấu hình phổ biến, bản JAR thông thường có classifier `plain` để phân biệt với bản chạy được.

Executable JAR điển hình chứa:

```text
demo-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── BOOT-INF/classes/      # .class và resources của ứng dụng
├── BOOT-INF/lib/          # dependency runtime dưới dạng nested JAR
└── org/springframework/boot/loader/...  # Boot launcher
```

Vì thế, executable JAR của Spring Boot **không đơn thuần** là JAR mỏng chứa mỗi class, cũng không nhất thiết là shaded JAR đã giải nén rồi trộn mọi dependency thành một cây class. Các dependency runtime được đóng gói thành nested JAR để Boot launcher tải được. Plugin có thể thêm thông tin phân lớp (layers) giúp tối ưu container image; khi cần, plugin còn có task/goal tạo OCI image bằng buildpacks, với các điều kiện môi trường tương ứng.

## 6. Ví dụ chạy được: Maven dùng starter-parent

Tạo ba tệp sau. Đây là ví dụ Spring Boot 4.1.2, Java 17; Maven cần phiên bản được Spring Boot hỗ trợ. Tên tệp và vị trí package phải khớp.

**`pom.xml`**

```xml
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
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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

**`src/main/java/com/example/demo/DemoApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "Hello Boot";
    }
}
```

**Lệnh:**

```bash
mvn clean package
java -jar target/demo-0.0.1-SNAPSHOT.jar
```

Ở terminal khác:

```bash
curl http://localhost:8080/hello
```

HTTP response body chính xác là `Hello Boot` (không có ký tự xuống dòng trong chuỗi được controller trả về). Log khởi động phụ thuộc môi trường nên không coi là stdout cố định. Quy trình thực tế: starter mang các dependency MVC; parent quản lý phiên bản; Maven biên dịch code; Boot Maven plugin repackage JAR; Boot launcher khởi động ứng dụng và embedded Tomcat xử lý endpoint.

**Đổi từ parent sang BOM thuần:** nếu dự án không kế thừa parent Boot, dùng `<dependencyManagement>` ở mục 4, giữ dependency `spring-boot-starter-webmvc`, rồi chủ động thêm cấu hình plugin như sau:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
        </plugin>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>4.1.2</version>
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
```

Đây là **đoạn cấu hình bổ sung cho POM dùng BOM**, không phải toàn bộ `pom.xml` độc lập. Trong POM thực, chỉ có **một** khối `<build>` và **một** khối `<properties>` tương ứng; hợp nhất chúng với các phần hiện có. Nếu không cấu hình execution `repackage`, lệnh `mvn package` có thể chỉ sinh JAR thường dù ứng dụng vẫn compile được. Có thể chạy tường minh `mvn package spring-boot:repackage` nếu plugin được khai báo/phân giải chính xác.

## 7. Cấu hình tương đương với Gradle

Dùng cùng file Java ở mục 6, thay build Maven bằng hai tệp Gradle Groovy DSL sau.

**`settings.gradle`**

```groovy
rootProject.name = 'demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    testImplementation platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)

    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Ở đây:

- `id 'java'` phụ trách compile/test/JAR nền tảng.
- `id 'org.springframework.boot' version '4.1.2'` cung cấp task Boot, trong đó có `bootJar`.
- `platform(SpringBootPlugin.BOM_COORDINATES)` nhập BOM khớp phiên bản plugin mà không cần lặp lại số phiên bản.
- `implementation` khai báo starter thực sự cần; `testImplementation` khai báo thư viện phục vụ test.

Nếu dự án có Gradle Wrapper, chạy:

```bash
./gradlew clean bootJar
java -jar build/libs/demo-0.0.1-SNAPSHOT.jar
```

Trên Windows có thể dùng `gradlew.bat clean bootJar` thay cho `./gradlew`. Lệnh `bootRun` chạy ứng dụng từ cấu hình phát triển và **không bắt buộc tạo JAR trước**; `bootJar` mới là task đóng gói executable JAR. Dự án dùng Gradle 4.1.2 plugin phải chạy bằng phiên bản Gradle được Spring Boot 4.1.x hỗ trợ (Gradle 8.14+ trong nhánh 8.x hoặc Gradle 9.x).

Nếu chọn `io.spring.dependency-management` thay vì native `platform`, áp dụng plugin này và bỏ khai báo `platform` trùng lặp; Boot plugin sẽ tự import BOM tương ứng. Tránh pha nhiều cách quản lý phiên bản không có chủ đích.

## 8. Kiểm chứng từng trách nhiệm khi build

| Cần xác nhận | Maven | Gradle | Dấu hiệu cần thấy |
| --- | --- | --- | --- |
| Starter kéo những dependency nào? | `mvn dependency:tree` | `./gradlew dependencies --configuration runtimeClasspath` | Các artifact Spring MVC, embedded server và thư viện liên quan xuất hiện trong dependency graph. |
| BOM/parent đã quản lý phiên bản? | `mvn help:effective-pom` | `./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath` | Dependency được phân giải về phiên bản cụ thể mà không cần ghi version ở mỗi khai báo starter. |
| Plugin và task đóng gói có mặt? | Kiểm tra effective POM và log `spring-boot:repackage` của `mvn package` | `./gradlew tasks --all` tìm `bootJar` | Có bước tạo executable artifact. |
| JAR có phụ thuộc runtime? | `jar tf target/demo-0.0.1-SNAPSHOT.jar` | `jar tf build/libs/demo-0.0.1-SNAPSHOT.jar` | Có `BOOT-INF/classes/`, `BOOT-INF/lib/` và Spring Boot loader. |
| Chạy được độc lập? | `java -jar target/demo-0.0.1-SNAPSHOT.jar` | `java -jar build/libs/demo-0.0.1-SNAPSHOT.jar` | Ứng dụng khởi động và trả về `Hello Boot` ở `/hello`. |

Để chẩn đoán phiên bản bị ghi đè, hãy xem **resolved dependency graph** thay vì chỉ đọc `pom.xml`/`build.gradle`; kết quả phân giải còn chịu tác động từ dependency bắc cầu, constraint, cấu hình dự án và rule giải quyết xung đột.

## 9. Tình huống sử dụng thực tế

**Tình huống A — ứng dụng mới:** chọn starter cần thiết, dùng parent Boot (Maven) hoặc Boot plugin + BOM (Gradle), bật đóng gói executable artifact, chạy test rồi thử `java -jar`. Đây là chuỗi tối giản cho service Spring Boot.

**Tình huống B — Maven có corporate parent:** giữ parent tổ chức, import `spring-boot-dependencies` vào `dependencyManagement`, đặt phiên bản Boot Maven plugin và cấu hình `repackage` rõ ràng. Vì Maven chỉ có một parent trực tiếp, không thể vừa khai báo corporate parent và Boot parent làm hai thẻ `<parent>`.

**Tình huống C — dự án đa module:** module `domain`/`common` thường là thư viện JAR thông thường; module `service` chứa `main` và cần executable JAR. Có thể chia sẻ quản lý phiên bản từ BOM ở cấp phù hợp, nhưng chỉ áp dụng việc repackage/bootJar ở module cần chạy độc lập. Đóng gói module thư viện thành executable JAR rồi dùng như dependency có thể gây vấn đề vì class của ứng dụng nằm ở `BOOT-INF/classes`, không theo cấu trúc JAR thư viện bình thường.

**Tình huống D — nâng phiên bản Spring Boot:** cập nhật Boot parent hoặc BOM và Boot plugin cùng dòng phù hợp; rà soát starter bị đổi tên, API, Java, Maven/Gradle và thư viện được quản lý. Đặc biệt, Spring Boot 4 dùng `spring-boot-starter-webmvc` thay cho tên `spring-boot-starter-web` đã deprecated; không nên sao chép nguyên dependency list từ ví dụ Boot 3 mà không kiểm tra migration guide.

## 10. Lỗi thường gặp và nguyên nhân gốc

1. **“Có starter rồi, sao Maven báo thiếu version?”** Dự án không nhận BOM/parent phù hợp, khai báo dependency sai scope hoặc dùng artifact không được BOM quản lý. Kiểm tra `dependencyManagement` và effective POM.
2. **“Import BOM rồi mà không thấy Spring MVC?”** BOM không thêm dependency. Cần khai báo `spring-boot-starter-webmvc` và kiểm tra dependency tree.
3. **“`mvn package` thành công, `java -jar` không chạy?”** Có thể mới tạo JAR thường; thiếu Boot Maven plugin hoặc execution `repackage` (khi không dùng Boot parent). Xác minh manifest, `BOOT-INF` và log build.
4. **“Gradle tạo cả `-plain.jar` lẫn một JAR khác?”** Đó thường là hai artifact của `jar` và `bootJar`. Chạy JAR executable mà `bootJar` tạo ra.
5. **“Đã khai báo Boot Gradle plugin, tại sao dependency version vẫn rối?”** Plugin build không tự thay thế việc cấu hình BOM; dùng native `platform` hoặc `io.spring.dependency-management` một cách nhất quán.
6. **“Tại sao runtime bị `NoSuchMethodError`/`ClassNotFoundException`?”** Có thể dependency được override hoặc exclude không tương thích, hay JAR không gồm thư viện runtime cần thiết. Xem resolved graph, scopes/configurations, artifact đã package và phiên bản Java.
7. **“Tại sao có starter nhưng bean không xuất hiện?”** Auto-configuration phụ thuộc classpath, condition, properties và bean đã tồn tại. Xem điều kiện auto-configuration và cấu hình thực tế, không đổ lỗi ngay cho BOM hay plugin.
8. **“Đưa executable JAR của service vào module thư viện được không?”** Thường không phù hợp. Phân tách executable module và library module; dùng JAR thông thường cho library.

## 11. Bài tập tự kiểm tra

1. Nếu chỉ thêm `spring-boot-dependencies` BOM mà không thêm `spring-boot-starter-webmvc`, ứng dụng có tự có web server không? **Không**; BOM chỉ quản lý phiên bản.
2. Nếu thêm `spring-boot-starter-webmvc` nhưng bỏ Boot Maven plugin trong project dùng starter-parent, `mvn package` có chắc tạo executable JAR không? **Không**; parent cung cấp cấu hình execution, còn plugin vẫn phải có mặt trong build để thực thi.
3. Với Maven parent khác, import BOM có thay cho cấu hình `spring-boot-maven-plugin` không? **Không**; import BOM không nhập plugin management/execution.
4. Trong Gradle, `jar` và `bootJar` có đồng nghĩa không? **Không**; `bootJar` tạo executable archive với Boot loader và runtime dependencies.
5. Để biết phiên bản Jackson hoặc Spring Framework cuối cùng là gì, nên xem cấu hình khai báo hay kết quả phân giải dependency? **Kết quả phân giải** là bằng chứng quyết định.

**Ghi nhớ:** **Starter = chọn tập thư viện; BOM = căn chỉnh phiên bản; plugin đóng gói = tạo artifact thực thi.** Parent POM của Maven có thể gom quản lý dependency và cấu hình plugin, nhưng đó vẫn là các trách nhiệm khác nhau.

## 12. Tài liệu tham khảo chính thức

- [Spring Boot — Build Systems và Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot Maven Plugin — Using the Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html)
- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
- [Spring Boot Gradle Plugin — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
- [Spring Boot Gradle Plugin — Getting Started](https://docs.spring.io/spring-boot/gradle-plugin/getting-started.html)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
