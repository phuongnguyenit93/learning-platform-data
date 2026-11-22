# Phân biệt JDK, công cụ build, plugin Spring Boot và môi trường chạy

Một ứng dụng Spring Boot có thể được viết trên máy dùng JDK 21, build bằng Gradle, đóng gói bằng Spring Boot Gradle plugin rồi chạy trên máy chủ chỉ có Java Runtime 21. Bốn yếu tố này phối hợp trong cùng quy trình nhưng đảm nhiệm bốn việc khác nhau. Hiểu đúng ranh giới giúp chọn đúng công cụ, tạo đúng artifact và xử lý lỗi khi chuyển ứng dụng từ máy phát triển sang CI/CD hoặc môi trường triển khai.

## 1. Bản đồ tổng quan: ai làm việc gì?

| Thành phần | Câu hỏi nó giải quyết | Trách nhiệm chính | Ví dụ |
| --- | --- | --- | --- |
| **JDK (Java Development Kit)** | Dùng gì để biên dịch Java? | Cung cấp `javac`, `java`, `jar` và thư viện/công cụ phát triển; tạo bytecode từ mã nguồn. | Temurin JDK 21, Oracle JDK 21 |
| **Công cụ build** | Phải tải thư viện, biên dịch, test và tạo sản phẩm theo thứ tự nào? | Điều phối tác vụ, dependency, cache, build lifecycle và tự động hóa. | Gradle, Maven |
| **Plugin Spring Boot dành cho build tool** | Làm sao build/run/package ứng dụng theo quy ước Spring Boot? | Tích hợp các tác vụ hoặc goal chuyên biệt như `bootJar`, `bootRun`, `repackage`. | `org.springframework.boot` Gradle plugin, `spring-boot-maven-plugin` |
| **Môi trường chạy (runtime)** | Sản phẩm đã build chạy ở đâu, với JVM và cấu hình nào? | Nạp class, thực thi bytecode, cung cấp OS/tài nguyên/mạng/cấu hình và dịch vụ phụ thuộc. | Java 21 runtime trên máy chủ, container, VM |

Dòng chảy điển hình:

~~~text
Mã nguồn Java + build.gradle / pom.xml
                    |
                    v
        Gradle / Maven (điều phối)
             |               |
             v               v
   JDK + javac (compile)   Resolve dependencies, test
             \               /
              \             /
               v           v
         Spring Boot build plugin
        (bootJar / bootWar / repackage)
                    |
                    v
           Artifact triển khai
        (ví dụ: app.jar thực thi)
                    |
                    v
       JVM + hệ điều hành + cấu hình
       + database / network / secrets
                    |
                    v
            Ứng dụng đang chạy
~~~

**Điểm mấu chốt:** JDK có thể biên dịch một chương trình Java đơn giản mà không cần Gradle/Maven; Gradle/Maven có thể quản lý nhiều loại dự án chứ không chỉ Spring Boot; Spring Boot plugin cần một build tool để hoạt động; còn artifact đã build thường chỉ cần Java runtime tương thích để chạy.

## 2. JDK: cung cấp compiler và các công cụ Java

JDK chứa bộ biên dịch `javac` (biến `.java` thành `.class`), lệnh `java` để khởi động JVM và công cụ `jar` để tạo/kiểm tra Java archive. Java bytecode trong `.class` được JVM thực thi, không phải được Gradle hay Maven trực tiếp “chạy”.

Ví dụ tối giản, lưu thành **Hello.java**:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from JVM");
    }
}
~~~

Trên máy có JDK 17 trở lên:

~~~bash
javac Hello.java
java Hello
~~~

Đầu ra chính xác:

~~~text
Hello from JVM
~~~

Có thể tự đóng gói bằng công cụ `jar` của JDK:

~~~bash
jar --create --file hello.jar --main-class Hello Hello.class
java -jar hello.jar
~~~

Đầu ra vẫn là `Hello from JVM`. Ví dụ này **không dùng** Gradle, Maven hay Spring Boot: nó chứng minh `javac`/`jar` là công cụ thuộc JDK, còn `java -jar` là hành động thực thi artifact bằng JVM. Với ứng dụng có nhiều thư viện, việc quản lý classpath và đóng gói bằng tay nhanh chóng trở nên phức tạp; đó là một lý do dùng build tool.

### JDK khác Java runtime như thế nào?

- **JDK** phục vụ phát triển và thường có cả công cụ thực thi. Máy build cần compiler và các công cụ thích hợp.
- **Java runtime/JRE** là phần cần thiết để chạy ứng dụng đã biên dịch; không nhất thiết chứa `javac`. Các bản phân phối Java hiện đại có thể cung cấp JDK đầy đủ hoặc runtime image rút gọn; không phải phiên bản nào cũng phát hành JRE riêng.
- **JVM** là máy ảo thực thi bytecode; JVM là một thành phần của môi trường Java runtime, không đồng nghĩa toàn bộ JDK.
- **JDK version** dùng để build và **Java runtime version** khi deploy có thể khác nhau, nhưng bytecode và các API được sử dụng phải tương thích. Class biên dịch cho Java 21 theo mặc định không chạy trên runtime Java 17.

Kiểm tra từng công cụ:

~~~bash
java --version
javac --version
jar --version
~~~

`java` hoạt động nhưng `javac` không có thường nghĩa là môi trường chỉ cung cấp runtime, hoặc `PATH`/`JAVA_HOME` chưa trỏ đúng JDK. `java --version` cho biết Java đang được gọi bởi shell hiện tại, chưa chắc là JDK mà IDE, Gradle toolchain hoặc CI dùng để biên dịch.

## 3. Gradle và Maven: điều phối quá trình build

Một dự án thực tế phải xác định dependencies, compile, xử lý resources, chạy test, đóng gói, có thể chạy kiểm tra chất lượng và xuất bản artifact. **Build tool** mô tả quan hệ giữa các công việc đó và thực hiện chúng theo thứ tự cần thiết.

| Nội dung | Gradle | Maven |
| --- | --- | --- |
| File cấu hình thường gặp | `build.gradle` hoặc `build.gradle.kts`; `settings.gradle` | `pom.xml` |
| Đơn vị tổ chức | Task và task dependency graph | Lifecycle phase và plugin goal |
| Biên dịch/test Java thông dụng | `compileJava`, `test`, `build` | `compile`, `test`, `package` |
| Quản lý thư viện | Dependency configurations, repositories, constraints/platforms | Dependencies, repositories, dependency management/BOM |
| Tác vụ Boot thường gặp | `bootRun`, `bootJar`, `bootWar` | `spring-boot:run`, `spring-boot:repackage` |

Ví dụ: `./gradlew build` kích hoạt các task phù hợp với plugin đang áp dụng; `mvn package` chạy các phase đến `package`. Đây là **lệnh điều phối**, không phải tên compiler. Bên dưới, Java compiler vẫn do JDK/toolchain cung cấp.

### Phân biệt ba phiên bản Java dễ nhầm

1. **JVM chạy build tool:** bản Java dùng để khởi động tiến trình Gradle daemon hoặc Maven. Kiểm tra qua `./gradlew --version` hoặc `mvn --version`.
2. **JDK/toolchain biên dịch project:** bản JDK Gradle/Maven chọn để thực hiện compile/test theo cấu hình. Nó có thể khác Java đang chạy build tool.
3. **JVM chạy ứng dụng sau deploy:** bản Java trong máy chủ/container khi thực thi `java -jar`. Nó độc lập với JDK trên máy build.

Ví dụ hợp lệ về mặt ý tưởng: Gradle chạy trên JDK 21, compile ứng dụng với toolchain JDK 21, và runtime sản xuất là Java 21. Nếu muốn chạy trên Java 17, phải chọn target/API phù hợp với Java 17 và bảo đảm phiên bản Spring Boot cũng hỗ trợ Java 17.

Trong Gradle, cấu hình toolchain có thể là:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Cấu hình này yêu cầu JDK 21 cho tác vụ Java tương ứng. Nó không tự cài Java 21 lên máy sản xuất và không bảo đảm bản Gradle đang dùng có thể chạy trên bất kỳ phiên bản Java nào. Nếu muốn tạo bytecode tương thích Java 17 bằng compiler mới hơn, có thể cần cấu hình `options.release = 17`; việc chọn `--release` còn giới hạn API Java tiêu chuẩn được phép sử dụng. Tính tương thích của framework/dependency vẫn phải được kiểm tra riêng.

### Dependency management khác plugin đóng gói

Dependency `spring-boot-starter-web` đem các thư viện cần cho chức năng web và embedded server vào classpath khi cấu hình phù hợp. BOM (Bill of Materials), `spring-boot-starter-parent` hoặc plugin quản lý dependency giúp chọn **phiên bản thư viện đồng bộ**. Trong khi đó, Spring Boot build plugin cung cấp **tác vụ/goal** để build, chạy và đóng gói. Có Boot plugin không có nghĩa tự động có mọi starter; thêm starter cũng không thay thế tác vụ đóng gói executable archive.

## 4. Spring Boot build plugin: nối quy trình build với ứng dụng Boot

Spring Boot cung cấp tích hợp riêng cho Gradle/Maven:

- **Gradle `org.springframework.boot` plugin:** thêm/cấu hình các task như `bootRun` (chạy từ classpath lúc phát triển), `bootJar` (tạo executable JAR), `bootWar` khi cấu hình WAR phù hợp, và `bootBuildImage` cho OCI image bằng buildpacks khi đáp ứng điều kiện môi trường.
- **Maven `spring-boot-maven-plugin`:** cung cấp goal `run`, `repackage` và các goal hỗ trợ khác. Goal `repackage` biến archive Java thông thường thành gói có bố cục/launcher cho ứng dụng Boot; nó có thể được gắn vào lifecycle `package` tùy cách cấu hình.
- **Spring Boot framework và starters:** là dependency nằm trong ứng dụng khi chạy. **Build plugin không phải bản thân Spring Boot runtime, và không phải web server.**

Với executable Boot JAR thông dụng, artifact có bố cục đặc trưng như `BOOT-INF/classes` (class/resources của ứng dụng), `BOOT-INF/lib` (thư viện) và manifest chỉ đến Boot launcher. Khi gọi `java -jar app.jar`, launcher sắp xếp classpath để khởi động entry point. Không nên suy luận mọi file có đuôi `.jar` đều tự chạy được: **plain JAR** có thể thiếu manifest khởi chạy hoặc runtime dependencies.

So sánh:

| Lệnh/artifact | Ý nghĩa | Dùng khi nào |
| --- | --- | --- |
| `jar` task của Gradle Java plugin | Tạo JAR Java thông thường; không mặc định gom đủ dependency để chạy Boot trực tiếp | Xuất thư viện hoặc archive thường |
| `bootJar` | Tạo executable Spring Boot JAR với cấu trúc/launcher thích hợp | Đóng gói ứng dụng Boot kiểu JAR để deploy |
| `bootRun` | Chạy ứng dụng qua Gradle bằng classpath của dự án | Phát triển/thử chạy, không tạo artifact phân phối thay thế |
| `bootWar` | Tạo executable WAR khi dự án cấu hình WAR | Kịch bản deploy WAR hoặc yêu cầu container tương ứng |
| Maven `package` + `repackage` | Maven package archive, Boot plugin đóng gói lại khi được cấu hình | Cách Maven tạo executable Boot archive |

`bootBuildImage` có thể tạo container image mà không cần tự viết Dockerfile, nhưng nó vẫn là **bước build**; khi container chạy, Java runtime trong image mới thực thi ứng dụng.

## 5. Ví dụ đầy đủ: một ứng dụng Spring Boot dùng Gradle

Ví dụ cố định Spring Boot **3.3.5** và Java **21** để minh họa các lớp công cụ; đây là phiên bản mẫu, không phải khuyến nghị rằng nó mới nhất. Máy build cần JDK 21, Gradle tương thích với JDK/Boot plugin, và truy cập repository để tải dependency. Khi làm dự án mới, chọn phiên bản plugin/framework đang được hỗ trợ và kiểm tra bảng tương thích của phiên bản đó.

Tạo ba file:

**settings.gradle**

~~~groovy
rootProject.name = 'boot-packaging-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
}

tasks.named('bootJar') {
    archiveFileName = 'boot-packaging-demo.jar'
}
~~~

**src/main/java/com/example/demo/DemoApplication.java**

~~~java
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
        return "Hello from Spring Boot";
    }
}
~~~

Thực hiện tại thư mục chứa `build.gradle`:

~~~bash
gradle clean bootJar
java -jar build/libs/boot-packaging-demo.jar
~~~

Lệnh trên giả định có bản Gradle phù hợp đã cài. Trong dự án đã có Gradle Wrapper, ưu tiên `./gradlew clean bootJar` trên Linux/macOS hoặc `gradlew.bat clean bootJar` trên Windows để dùng đúng phiên bản Gradle mà dự án cố định. Tên file JAR ở ví dụ được đặt rõ bởi `archiveFileName`, nên không phải đoán tên từ version.

Khi ứng dụng đang chạy, gọi ở terminal khác:

~~~bash
curl -s http://localhost:8080/hello
~~~

Nội dung HTTP response chính xác:

~~~text
Hello from Spring Boot
~~~

Các dòng log khởi động, thời gian, PID và cổng có thể thay đổi theo môi trường; không coi chúng là stdout cố định. Cổng mặc định ở cấu hình web tiêu chuẩn là 8080, trừ khi được đổi bằng cấu hình hoặc đang có xung đột.

**Ai làm phần nào trong ví dụ?**

1. Gradle đọc `settings.gradle` và `build.gradle`, tải plugin/dependency, lập graph và gọi task `bootJar`.
2. JDK 21/toolchain biên dịch `DemoApplication.java` thành bytecode; Gradle cũng xử lý resource và các bước phụ thuộc của task.
3. Boot Gradle plugin tổ chức các class và runtime dependency thành `build/libs/boot-packaging-demo.jar` có thể khởi chạy.
4. `java -jar` dùng JVM hiện có trên máy chạy để nạp executable JAR; framework Spring Boot khởi tạo application context và embedded web server từ starter web.
5. HTTP request `/hello` được ứng dụng đang chạy xử lý và trả về chuỗi trên. Gradle và compiler không tham gia xử lý từng HTTP request.

Với máy deploy, không phải chép Gradle, source Java hay compiler nếu đã có artifact phù hợp và runtime Java tương thích. Ngược lại, chỉ có JDK và Gradle mà thiếu Boot plugin/cấu hình package phù hợp cũng chưa bảo đảm sinh ra executable Boot JAR.

### Nếu dự án dùng Maven thì sao?

Tư duy không thay đổi. File `pom.xml` khai báo dependencies, dependency management và plugin. Dự án dùng `spring-boot-starter-parent` thường khai báo `spring-boot-maven-plugin` để goal `repackage` tích hợp vào packaging lifecycle. Lệnh điển hình:

~~~bash
mvn clean package
java -jar target/ten-ung-dung.jar
~~~

Tên file thực tế phụ thuộc `artifactId`/`version`/plugin configuration. Nếu không dùng starter parent, phải cấu hình tương ứng cho plugin version, goal/execution và dependency management; **đừng giả định mọi `mvn package` tự động tạo Boot JAR thực thi**. Khi học Maven, tra `mvn help:effective-pom` và log phase/goal để xác nhận những gì thực sự chạy.

## 6. Runtime: thứ xảy ra sau khi build xong

Một artifact có thể build thành công trên laptop nhưng vẫn lỗi trên server vì **môi trường chạy** quyết định:

- **Java runtime version và kiến trúc:** bytecode và native library phải tương thích với JVM/OS/CPU.
- **Cấu hình ứng dụng:** `application.yml`, biến môi trường, active profiles, system properties, tham số dòng lệnh; giá trị runtime có thể khác máy build.
- **Hạ tầng bên ngoài:** database, message broker, DNS, TLS certificate, credentials, network và firewall.
- **Tài nguyên và quyền:** memory/CPU, port binding, file permissions, mounted volumes, đường dẫn cấu hình.
- **Cách triển khai:** máy vật lý, VM, container hoặc orchestration; `java -jar` vẫn chạy bằng JVM bên trong môi trường tương ứng.

Ví dụ **Dockerfile chỉ cho giai đoạn chạy** sau khi `bootJar` đã sinh artifact:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY build/libs/boot-packaging-demo.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Image trên dùng Java 21 **runtime**, không mang Gradle hay compiler vào container. Lệnh `COPY` yêu cầu artifact đã được build và nằm trong Docker build context. Đây là ví dụ về runtime image, không phải Dockerfile tự build từ source.

`gradle bootRun` và `java -jar ...` đều có thể khởi động cùng logic ứng dụng, nhưng khác quy trình: `bootRun` sử dụng classpath/build environment hiện hành, còn `java -jar` kiểm chứng chính artifact sẽ được phân phối. Vì vậy trước khi deploy nên chạy thử executable artifact với runtime và cấu hình gần môi trường đích nhất.

## 7. Tương thích phiên bản: ba phép kiểm tra khác nhau

**Kiểm tra 1 — Build tool có chạy được với JDK điều khiển nó không?** Gradle/Maven bản hiện tại cần hỗ trợ JVM dùng để khởi động chính build tool. Lỗi xảy ra ngay khi gọi `gradle`/`mvn` có thể thuộc lớp này, trước cả khi code ứng dụng được compile.

**Kiểm tra 2 — Plugin Spring Boot có tương thích với build tool và Java của dự án không?** Version của Boot Gradle/Maven plugin, framework Spring Boot, Gradle/Maven và JDK cần theo tài liệu tương thích cho phiên bản cụ thể. Spring Boot 3.x yêu cầu tối thiểu Java 17; các dòng Spring Boot khác có thể thay đổi yêu cầu. Không chọn version chỉ vì “bản mới nhất” của một thành phần.

**Kiểm tra 3 — Runtime đích có thực thi được artifact không?** Java class-file version phụ thuộc target compile. Ví dụ Java 17 sử dụng class-file major version 61, Java 21 là 65. Artifact compile cho Java 21 rồi chạy bằng Java 17 có thể gặp `UnsupportedClassVersionError`, dù build đã PASS. Dùng `--release`/toolchain đúng cách và thử trên runtime thật để tránh lệch môi trường.

Các lệnh kiểm tra thường dùng:

~~~bash
java --version
javac --version
gradle --version
mvn --version
~~~

Chỉ chạy lệnh cho công cụ đang có trên máy. Với Gradle Wrapper, `./gradlew --version` hữu ích hơn `gradle --version` vì phản ánh Gradle của dự án. Kết quả `gradle --version` cho biết JVM chạy Gradle, nhưng không tự chứng minh compiler toolchain hoặc JVM production là phiên bản nào.

## 8. Chẩn đoán lỗi bằng cách xác định đúng lớp

| Hiện tượng | Lớp cần kiểm tra trước | Cách tìm nguyên nhân |
| --- | --- | --- |
| `javac: command not found` hoặc `javac` không được nhận diện | JDK/PATH | Kiểm tra JDK đã cài, `JAVA_HOME`, `PATH`; phân biệt runtime-only image |
| `invalid source release: 21` | Compiler/toolchain | Kiểm tra compiler thật được gọi và target Java cấu hình |
| Gradle không khởi động hoặc báo JVM không được hỗ trợ | Build tool và JVM chạy build tool | Xem `./gradlew --version`, Gradle wrapper version và compatibility |
| Không resolve được Boot plugin hoặc dependency | Plugin/repository/network | Xem version plugin, plugin repositories, Maven Central, proxy, offline mode |
| Task `bootJar` không tồn tại | Plugin/cấu hình build | Kiểm tra đã apply Boot plugin và đây có phải ứng dụng Boot được cấu hình đúng không |
| `no main manifest attribute` khi chạy JAR | Loại artifact/packaging | Có thể đã chạy plain JAR thay vì executable Boot JAR; xem task/goal và manifest |
| `Unable to access jarfile` | Đường dẫn artifact | Kiểm tra build output, tên file, working directory, quyền đọc |
| `UnsupportedClassVersionError` | Runtime JVM so với bytecode | So sánh Java runtime đích, toolchain và target compile |
| `ClassNotFoundException`/`NoClassDefFoundError` | Classpath/dependency/packaging | Kiểm tra dependency scope, nội dung JAR, launcher và thư viện bị thiếu |
| Boot khởi động nhưng lỗi kết nối DB | Runtime/config/hạ tầng | Kiểm tra URL, credentials, mạng, database sẵn sàng, profile |
| `Port 8080 was already in use` | Runtime/port | Đổi `server.port` hoặc giải phóng port theo quy trình môi trường |

Các lỗi nhiều lớp có thể trông giống nhau. Đọc **stack trace và lệnh thực sự gây lỗi**, sau đó xác định lỗi ở lúc resolve plugin, compile, package hay khởi chạy; đừng mặc định mọi lỗi Boot đều do “Gradle” hoặc “JDK”.

## 9. Cách tự kiểm chứng và ghi nhớ

Dùng bài thực hành sau để tách bốn vai trò:

1. Biên dịch/chạy **Hello.java** chỉ với `javac` và `java`. Kết luận: JDK và JVM đủ cho chương trình Java tối giản.
2. Chạy `gradle clean bootJar` trong ví dụ Boot. Quan sát Gradle điều phối task, JDK biên dịch và Boot plugin tạo executable JAR.
3. Kiểm tra archive bằng `jar tf build/libs/boot-packaging-demo.jar` (lệnh `jar` thuộc JDK), tìm `BOOT-INF/classes` và `BOOT-INF/lib`.
4. Dùng `java -jar build/libs/boot-packaging-demo.jar` rồi gọi `/hello`. Kết luận: artifact được thực thi bằng JVM và các thư viện đã đóng gói.
5. Khi deploy, kiểm tra runtime Java, profile, biến môi trường và dịch vụ bên ngoài. Một bản build PASS chỉ xác nhận giai đoạn build; nó không thay thế việc kiểm tra điều kiện chạy thật.

Tự trả lời ba câu hỏi: **“Ai biên dịch mã nguồn?” → JDK/toolchain. “Ai quyết định thứ tự build và ai đóng gói theo chuẩn Boot?” → Gradle/Maven và Spring Boot build plugin. “Ai thực sự chạy ứng dụng sau deploy?” → JVM trong môi trường runtime cùng dependencies/cấu hình/hạ tầng cần thiết.**

Khi phân biệt được ba bước này, bạn sẽ biết nên sửa `JAVA_HOME`, build script, cấu hình Boot plugin hay cấu hình môi trường triển khai, thay vì đổi ngẫu nhiên nhiều thành phần cùng lúc.
