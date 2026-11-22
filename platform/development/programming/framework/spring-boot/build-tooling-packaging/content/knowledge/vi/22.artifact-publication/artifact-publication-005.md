# Lựa chọn artifact JAR thường, Boot JAR, WAR hoặc source JAR cần phát hành

## 1. Bắt đầu từ người nhận artifact và cách họ sử dụng

Trong một dự án Java/Spring Boot, build có thể tạo ra nhiều file mang đuôi JAR hoặc WAR. Chúng không thể thay thế tùy ý cho nhau. Một thư viện Java dùng làm dependency cho dự án khác cần **JAR thường**; một dịch vụ Spring Boot cần triển khai độc lập thường cần **executable Boot JAR**; một ứng dụng web Servlet theo hợp đồng của tổ chức có thể cần **WAR**; nhóm phát triển hoặc người dùng thư viện cần đọc/debug mã nguồn có thể cần **source JAR**.

Chọn sai artifact thường không làm task build thất bại. Vấn đề chỉ lộ ra khi người tiêu thụ tải file về:

- Dự án khác khai báo dependency tới Boot JAR nhưng compiler không tìm được class của ứng dụng.
- Pipeline chỉ publish JAR thường nên đội vận hành không thể chạy bằng java -jar như kỳ vọng.
- Hạ tầng yêu cầu deploy vào Servlet container nhưng nhóm phát hành chỉ có executable JAR.
- IDE không tải được mã nguồn khi debug vì thiếu artifact classifier sources.
- Maven publish file executable đè lên JAR thư viện, làm các consumer đang phụ thuộc GAV đó lỗi classpath.
- Một WAR chứa embedded server sai scope, gây xung đột với server mà tổ chức đã cung cấp.

Bài học này giúp chọn **đúng loại artifact**, hiểu cách Maven/Gradle đặt tên và publish, giữ plain archive khi cần, đóng gói source JAR và xác minh nội dung thực tế trước khi phát hành.

**Phiên bản thực hành:** Java 17, Spring Boot 3.3.5, Maven 3.9.x hoặc Gradle 8.5. Đây là phiên bản cố định cho ví dụ để có thể đối chiếu; không phải tuyên bố phiên bản mới nhất.

## 2. Bảng quyết định nhanh

| Nhu cầu của người nhận | Artifact phù hợp | Cách sử dụng | Có nên làm dependency compile? |
| --- | --- | --- | --- |
| Ứng dụng khác import class của thư viện | **JAR thường (library JAR)** | Build tool thêm JAR và dependency metadata vào classpath | **Có** |
| Vận hành một ứng dụng Spring Boot độc lập | **Executable Boot JAR** | java -jar application.jar hoặc container image | **Không** |
| Triển khai ứng dụng web Servlet vào Tomcat/Jetty bên ngoài | **WAR** phù hợp Servlet container | Deploy WAR vào container; có thể là executable WAR của Boot | **Không** |
| Cần mã nguồn để đọc/debug/IDE attach | **Source JAR** | IDE hoặc công cụ tài liệu tải theo classifier sources | **Không** |
| Cần cả library lẫn bản chạy độc lập | **JAR thường + Boot JAR riêng** | Publish hai artifact có quy ước rõ | Chỉ JAR thường |

**Quy tắc lựa chọn:**

1. Hỏi người nhận có **import class** hay **khởi động ứng dụng**.
2. Nếu import class, ưu tiên plain library JAR cùng POM/Gradle Module Metadata.
3. Nếu khởi động Spring Boot service, dùng executable Boot JAR hoặc Boot WAR theo môi trường triển khai.
4. Nếu hợp đồng triển khai yêu cầu Servlet container, xác định version Servlet/Jakarta và cấu hình WAR tương thích.
5. Nếu cần debug hoặc phân phối source, publish source JAR cùng đúng version của binary.
6. Nếu cần nhiều mục đích, phát hành nhiều artifact có tên/classifier rõ ràng; không dùng một file làm tất cả.

## 3. Hiểu đúng bốn loại artifact

### 3.1. JAR thường: thư viện hoặc archive Java không tự mang Boot loader

**JAR (Java Archive)** là ZIP archive chứa class, resource và metadata. Một thư viện Java thường có cấu trúc:

~~~text
catalog-core-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/example/catalog/
    ├── CatalogFormatter.class
    └── CatalogRecord.class
~~~

Class nằm ở package path chuẩn tính từ root của JAR. Khi một ứng dụng khai báo dependency tới thư viện này, compiler/runtime có thể tìm class bằng classpath thông thường.

JAR thư viện thường **không chứa toàn bộ dependency transitive** bên trong. Ví dụ CatalogFormatter sử dụng Commons Lang thì thư viện cần công bố dependency metadata để Maven/Gradle consumer tải Commons Lang riêng. Đây là lý do plain library JAR phải được phát hành cùng **POM hoặc Gradle Module Metadata** phù hợp.

Một JAR thường cũng có thể chứa main class. Tuy nhiên, nếu nó không mang các dependency cần thiết, việc chạy bằng java -jar có thể thất bại trừ khi dependencies đã được cung cấp trên classpath. **Có file .jar không đồng nghĩa là executable application package.**

**Khi chọn:**

- Module chia sẻ class giữa nhiều ứng dụng.
- SDK, utility, domain model, starter hoặc adapter.
- Module core trong dự án đa mô-đun.
- Artifact muốn consumer đưa vào compile/runtime classpath theo dependency metadata.

**Không nhầm plain JAR với shaded/uber JAR.** Shaded JAR thường hợp nhất class từ nhiều dependency vào một archive, có thể cần xử lý trùng resource, service descriptors và license files. JAR thường của Java Library plugin không tự làm điều đó.

### 3.2. Executable Spring Boot JAR: ứng dụng tự khởi động

**Executable Boot JAR** là archive được Spring Boot plugin đóng gói lại để có thể chạy bằng:

~~~bash
java -jar app-1.0.0.jar
~~~

Một JAR điển hình:

~~~text
app-1.0.0.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── com/example/app/Application.class
    └── lib/
        ├── spring-boot-*.jar
        ├── spring-context-*.jar
        └── ...
~~~

Khác biệt quan trọng:

- Class ứng dụng nằm trong **BOOT-INF/classes/**.
- Runtime dependency nằm trong các JAR lồng ở **BOOT-INF/lib/**.
- Spring Boot loader được dùng để khởi động và nạp nested dependencies.
- Manifest thường có **Main-Class** là launcher của Spring Boot và **Start-Class** là main class của ứng dụng.

Vì class ứng dụng nằm trong BOOT-INF/classes, **không dùng executable Boot JAR như một Java library dependency thông thường**. Compiler hoặc classloader của một ứng dụng khác không xem BOOT-INF/classes như package root của một plain JAR.

Boot JAR phù hợp cho:

- REST API/service, batch app, scheduler, command-line application.
- Container image hoặc nền tảng chạy Java process.
- Phát hành ứng dụng có runtime dependencies được đóng gói cùng.
- Đội vận hành cần một file có thể chạy nhất quán qua java -jar.

**Boot JAR không phải một JAR đã giải nén toàn bộ dependency thành một đống class duy nhất.** Spring Boot thường giữ dependencies dưới dạng nested JAR và dùng launcher riêng.

### 3.3. WAR: web application dành cho Servlet container

**WAR (Web Application Archive)** được định nghĩa cho ứng dụng web dựa trên Servlet. Một WAR truyền thống có bố cục:

~~~text
web-portal.war
├── META-INF/
└── WEB-INF/
    ├── classes/
    │   └── com/example/web/PortalApplication.class
    ├── lib/
    │   ├── application-library.jar
    │   └── ...
    └── web.xml (nếu ứng dụng dùng)
~~~

WAR được deploy vào một Servlet container đang chạy, ví dụ Tomcat/Jetty. Container quản lý web application lifecycle, Servlet registration, request dispatching và classloader theo hợp đồng Servlet.

**Spring Boot executable WAR** có thể hỗ trợ cả hai cách chạy:

- Deploy vào Servlet container bên ngoài, khi ứng dụng và dependencies được cấu hình đúng.
- Chạy trực tiếp bằng java -jar, khi archive đã được Spring Boot repackage.

WAR executable của Boot có thể chứa dependency server được đánh dấu provided ở **WEB-INF/lib-provided/** để không xung đột với Servlet container bên ngoài nhưng vẫn có sẵn khi chạy độc lập bằng Boot launcher.

**WAR không phải lựa chọn mặc định cho mọi ứng dụng web.** Nếu tổ chức cho phép chạy service độc lập hoặc container image, executable Boot JAR thường đơn giản hơn. WAR hợp lý khi hạ tầng, hợp đồng triển khai hoặc hệ thống legacy yêu cầu Servlet container bên ngoài.

Với Spring Boot 3.x, cần kiểm tra tương thích **Jakarta Servlet** và version container. Một container Servlet cũ dùng namespace javax không thể được coi là tương thích chỉ vì file có đuôi .war.

### 3.4. Source JAR: phân phối mã nguồn đi kèm binary

**Source JAR** là archive chứa source code của module, thường có tên:

~~~text
catalog-core-1.0.0-sources.jar
~~~

Bên trong có các file như:

~~~text
com/example/catalog/CatalogFormatter.java
com/example/catalog/CatalogRecord.java
~~~

Source JAR hữu ích cho:

- IDE hiển thị source khi điều hướng vào dependency.
- Debugger gắn source với bytecode.
- Người dùng đọc API implementation hoặc kiểm tra cách xử lý.
- Quy trình phân phối mã nguồn theo chính sách dự án.
- Review và đối chiếu source với đúng version binary.

Source JAR **không thay thế library JAR**, không phải executable artifact, không đóng gói runtime dependencies và không dùng làm dependency compile/runtime thông thường.

Source JAR phải khớp với **đúng version/commit của binary**. Không publish source mới hơn dưới cùng version với JAR cũ; khi debugger gắn nhầm source, line number và logic có thể không khớp bytecode.

Không phải mọi source code đều được phép public. Trước khi phát hành source JAR, kiểm tra license, mã nội bộ, secrets, generated sources và chính sách phân phối của tổ chức.

## 4. Phân biệt artifact, extension, classifier và tọa độ phát hành

Một Maven artifact thường được định danh bởi:

~~~text
groupId : artifactId : version : classifier @ extension
~~~

Ví dụ:

~~~text
com.example : catalog-core : 1.0.0
com.example : catalog-core : 1.0.0 : sources @ jar
com.example : catalog-app : 1.0.0 : exec @ jar
com.example : portal : 1.0.0 : exec @ war
~~~

Tên file thường có dạng:

~~~text
artifactId-version[-classifier].extension
~~~

Ví dụ:

| File | Ý nghĩa |
| --- | --- |
| catalog-core-1.0.0.jar | JAR chính của thư viện |
| catalog-core-1.0.0-sources.jar | Source JAR của thư viện |
| catalog-app-1.0.0.jar | Plain JAR của app nếu được giữ làm artifact chính |
| catalog-app-1.0.0-exec.jar | Executable Boot JAR được gắn classifier exec |
| portal-1.0.0.war | Plain/deployable WAR |
| portal-1.0.0-exec.war | Executable Boot WAR có classifier exec |

**Classifier** phân biệt các file bổ sung thuộc cùng tọa độ module. Nó không tạo một module hoàn toàn khác và không tự thay đổi dependency metadata. Các classifier thường gặp:

- **sources**: source JAR.
- **javadoc**: Javadoc archive.
- **tests** hoặc **test-jar**: test classes/artifact theo cấu hình.
- **exec** hoặc **boot**: executable artifact được tổ chức chọn tên.
- **plain**: archive thường khi plugin tạo song song executable archive.

Tên classifier là quy ước dự án, miễn là Maven/Gradle publication và consumer dùng thống nhất.

### 4.1. Classifier không biến Boot JAR thành library

Nếu publish:

~~~text
com.example:catalog-app:1.0.0:exec
~~~

consumer có thể tải artifact classified đó, nhưng **nội dung vẫn là Boot executable archive**. Classifier chỉ định danh biến thể; nó không di chuyển class từ BOOT-INF/classes về package root.

Tương tự, đổi tên file từ app.jar thành app-library.jar không thay đổi archive layout. Hãy kiểm tra nội dung JAR bằng jar tf trước khi quyết định cách consumer dùng.

### 4.2. Một GAV có thể phát hành nhiều file

Một module Maven có thể phát hành artifact chính cùng các classifier:

~~~text
catalog-core-1.0.0.jar
catalog-core-1.0.0-sources.jar
catalog-core-1.0.0-javadoc.jar
catalog-core-1.0.0.pom
~~~

Đây là một module thư viện với binary, source/documentation artifacts và POM chung.

Một ứng dụng có thể phát hành plain artifact cùng Boot artifact classifier nếu có nhu cầu. Nhưng vì POM chung có thể khiến người dùng nhầm app JAR với library, nên cần mô tả rõ trong repository README hoặc tách tọa độ/registry dành cho distribution artifact.

## 5. Chọn artifact theo từng loại sản phẩm

### 5.1. Thư viện Java dùng chung

**Nên phát hành:**

- JAR thường làm main artifact.
- POM hoặc Gradle Module Metadata mô tả dependency.
- Source JAR nếu chính sách cho phép.
- Javadoc JAR nếu muốn cung cấp tài liệu API.

**Không cần:** Boot JAR hoặc WAR. Thư viện không tự khởi động SpringApplication và không cần Servlet container.

### 5.2. Spring Boot service hoặc batch application

**Nên phát hành:**

- Executable Boot JAR làm deployment artifact.
- Có thể kèm source JAR nếu có nhu cầu debug/source distribution.
- SBOM/checksum/provenance theo quy trình release.

**Không nên:** dùng Boot JAR làm dependency compile cho module khác. Nếu cần chia sẻ code, tách core/library module thành plain JAR.

### 5.3. Ứng dụng Spring MVC triển khai lên Servlet container

**Nên phát hành:**

- WAR có cấu hình container compatibility.
- Có thể là executable/deployable Boot WAR nếu muốn hỗ trợ cả java -jar và external deployment.
- Source JAR nếu có nhu cầu phân phối source.

Ứng dụng Spring Boot WAR thường cần **SpringBootServletInitializer** và dependency embedded Servlet container được khai báo provided/providedRuntime đúng cách. Container bên ngoài phải tương thích Jakarta Servlet API mà Boot version yêu cầu.

### 5.4. Sản phẩm cần binary và source

Phát hành **binary JAR + source JAR cùng version**. Đặt source JAR ở classifier sources; không đặt source file trực tiếp vào dependency runtime. Kiểm tra nguồn được publish đúng commit và không chứa tệp nhạy cảm.

### 5.5. Nếu cần nhiều loại artifact cùng lúc

Một dự án có thể có nhiều module:

~~~text
platform/
├── core-library/      # JAR thường + sources
├── web-service/       # Boot JAR
├── legacy-web/        # WAR
└── docs/              # tài liệu
~~~

Đây thường là cách tổ chức rõ ràng hơn việc ép một module vừa làm library, vừa là service, vừa là WAR. Mỗi module có packaging, dependency graph, lifecycle và consumer contract riêng.

## 6. Java 17 mẫu: library core và Spring Boot application

Ta dùng một library nhỏ để minh họa vì sao cần giữ JAR thường riêng với Boot JAR.

### 6.1. Cấu trúc project đa-mô-đun

~~~text
artifact-demo/
├── pom.xml                 # root Maven, nếu chọn Maven
├── settings.gradle         # root Gradle, nếu chọn Gradle
├── core/
│   └── src/main/java/com/example/core/CatalogFormatter.java
└── app/
    └── src/main/java/com/example/app/CatalogApplication.java
~~~

Chọn Maven hoặc Gradle. Hai file Java dưới đây dùng chung.

### 6.2. Library class

File **core/src/main/java/com/example/core/CatalogFormatter.java**:

~~~java
package com.example.core;

import java.util.Locale;

public final class CatalogFormatter {

    private CatalogFormatter() {
    }

    public static String format(String raw) {
        return "CATALOG-" + raw.strip().toUpperCase(Locale.ROOT);
    }
}
~~~

Đây là class Java 17 hoàn chỉnh. Nó dùng API JDK, không cần Spring Boot hoặc dependency ngoài. Khi nhận input **"  book-42  "**, kết quả là **CATALOG-BOOK-42**.

Core được build thành plain JAR. Class nằm ở package path chuẩn:

~~~text
com/example/core/CatalogFormatter.class
~~~

### 6.3. Spring Boot application class

File **app/src/main/java/com/example/app/CatalogApplication.java**:

~~~java
package com.example.app;

import com.example.core.CatalogFormatter;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    CommandLineRunner runCatalog() {
        return args -> System.out.println(
                CatalogFormatter.format("  book-42  "));
    }
}
~~~

App dùng core như dependency. Ta chỉ dùng **spring-boot-starter** cơ bản, không cần HTTP server để minh họa đóng gói.

Khi chạy đúng executable Boot JAR:

~~~bash
java -jar app-1.0.0.jar
~~~

Dòng stdout do ứng dụng tự in:

~~~text
CATALOG-BOOK-42
~~~

Spring Boot có thể in banner/log trước hoặc sau dòng này. Đây là output nghiệp vụ, không phải toàn bộ terminal output.

**Điểm cần xác nhận:** app có thể gọi CatalogFormatter vì core JAR nằm trên classpath. Nếu core bị repackaged thành executable Boot JAR, class có thể nằm dưới BOOT-INF/classes và không còn được consumer nạp như plain dependency thông thường.

## 7. Maven: publish library JAR cùng source JAR

### 7.1. Root POM cho hai module

File **artifact-demo/pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>artifact-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>app</module>
    </modules>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
</project>
~~~

Root POM là aggregator và parent. Nó không sinh JAR ứng dụng vì packaging là **pom**.

### 7.2. core/pom.xml hoàn chỉnh

File **artifact-demo/core/pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>artifact-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>core</artifactId>
    <packaging>jar</packaging>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-source-plugin</artifactId>
                <version>3.4.0</version>
                <executions>
                    <execution>
                        <id>attach-sources</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>jar-no-fork</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là **library module**:

- Packaging **jar** tạo JAR thường.
- Không khai báo Spring Boot Maven Plugin tại core.
- Maven Source Plugin gắn source JAR vào lifecycle ở phase **verify**.
- Goal **jar-no-fork** tạo source archive và attach nó để install/deploy cùng binary.
- Source JAR có classifier **sources**.

Sau khi build, dự kiến:

~~~text
core/target/
├── core-1.0.0.jar
└── core-1.0.0-sources.jar
~~~

### 7.3. Build và kiểm tra Maven library

Từ root:

~~~bash
mvn -pl core -am clean verify
~~~

Nếu có Maven Wrapper:

~~~bash
./mvnw -pl core -am clean verify
~~~

Trên Windows dùng **mvnw.cmd**. Sau đó kiểm tra:

~~~bash
jar tf core/target/core-1.0.0.jar
jar tf core/target/core-1.0.0-sources.jar
~~~

JAR binary phải có **CatalogFormatter.class**. Source JAR phải có **CatalogFormatter.java** ở package path tương ứng.

**verify** tạo source JAR nhưng không tự deploy lên remote repository. Dùng **install** để cài vào local Maven repository hoặc **deploy** để phát hành lên repository được cấu hình.

## 8. Maven: Boot JAR giữ plain JAR và publish executable với classifier

### 8.1. app/pom.xml hoàn chỉnh

File **artifact-demo/app/pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>artifact-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>core</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
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
        </plugins>
    </build>
</project>
~~~

Do root dùng **spring-boot-starter-parent**, execution **repackage** đã được cấu hình trong parent. Ta chỉ bổ sung classifier **exec** cho execution có id repackage.

Kết quả có hai archive khác mục đích:

~~~text
app/target/
├── app-1.0.0.jar
└── app-1.0.0-exec.jar
~~~

- **app-1.0.0.jar**: JAR thường do Maven package tạo, giữ class ở package root.
- **app-1.0.0-exec.jar**: Boot executable JAR do repackage tạo, chứa Boot loader, BOOT-INF/classes và BOOT-INF/lib.

Nếu **không đặt classifier**, repackage mặc định thay artifact chính bằng executable archive; artifact gốc được đổi tên thành **.original** trong thư mục target. Đó là hành vi hợp lý cho một module chỉ đại diện ứng dụng, nhưng cần cẩn thận nếu module còn được tiêu thụ như dependency.

### 8.2. Build và chạy

~~~bash
mvn clean verify
java -jar app/target/app-1.0.0-exec.jar
~~~

Hoặc:

~~~bash
./mvnw clean verify
java -jar app/target/app-1.0.0-exec.jar
~~~

Dòng output nghiệp vụ:

~~~text
CATALOG-BOOK-42
~~~

Kiểm tra hai loại archive:

~~~bash
jar tf app/target/app-1.0.0.jar
jar tf app/target/app-1.0.0-exec.jar
~~~

Trong plain JAR, tìm **com/example/app/CatalogApplication.class**. Trong Boot JAR, tìm **BOOT-INF/classes/com/example/app/CatalogApplication.class** và **BOOT-INF/lib/**.

**Lưu ý về publication:** classifier exec giúp giữ cả hai file khi Maven install/deploy. Nhưng POM của module vẫn là POM chung. Không khuyến khích consumer khai báo Boot executable classifier làm dependency Java. Nếu app không có nhu cầu được sử dụng như library, có thể phát hành nó trong một distribution/artifact registry riêng thay vì đưa plain app JAR vào kho thư viện chung.

### 8.3. Khi chỉ muốn deploy artifact gốc

Spring Boot Maven Plugin có cấu hình **attach=false**. Trong trường hợp đó, plugin vẫn tạo file executable ở output build nhưng không attach nó để install/deploy; artifact được phát hành vẫn là JAR/WAR gốc.

Ví dụ fragment cấu hình execution:

~~~xml
<execution>
    <id>repackage</id>
    <configuration>
        <attach>false</attach>
    </configuration>
</execution>
~~~

Đây là lựa chọn khi quy trình deploy cần giữ main artifact gốc nhưng vẫn muốn có bản executable để chạy local/CI. Phải kiểm tra chính xác artifact nào được cài/deploy; **file tồn tại trong target không đồng nghĩa file đó được publish**.

## 9. Maven: chọn WAR cho ứng dụng Servlet

### 9.1. Khi nào dùng WAR?

Chọn WAR nếu hợp đồng triển khai yêu cầu ứng dụng web chạy trong **Servlet container** đã có sẵn. Ví dụ điển hình là ứng dụng Spring MVC, nơi container quản lý Servlet lifecycle.

Với Spring Boot 3.x, container ngoài phải hỗ trợ Jakarta Servlet API phù hợp. Ứng dụng thường cần kế thừa **SpringBootServletInitializer** để container khởi động Spring application context.

### 9.2. Main class cho Boot WAR

Một biến thể của class app:

~~~java
package com.example.app;

import com.example.core.CatalogFormatter;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CatalogApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(CatalogApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    CommandLineRunner runCatalog() {
        return args -> System.out.println(
                CatalogFormatter.format("  book-42  "));
    }
}
~~~

**configure()** phục vụ Servlet container khởi tạo ứng dụng qua SpringBootServletInitializer. **main()** vẫn cho phép chạy ứng dụng theo đường executable Boot archive khi cấu hình WAR đúng.

Đây là ví dụ **Servlet/MVC**. Không suy ra mọi web stack đều hỗ trợ WAR theo cùng cách; ví dụ WebFlux traditional WAR của Spring Boot có giới hạn hỗ trợ riêng.

### 9.3. Maven WAR POM: phần cấu hình cốt lõi

Trong module app WAR, dùng:

~~~xml
<packaging>war</packaging>

<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>core</artifactId>
        <version>${project.version}</version>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-tomcat</artifactId>
        <scope>provided</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
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
    </plugins>
</build>
~~~

Đây là **fragment thay cho packaging/dependencies/build của app JAR ở mục 8**, không ghép hai cấu hình packaging jar và war vào cùng một POM.

- **packaging war** yêu cầu Maven WAR Plugin tạo web archive.
- **spring-boot-starter-web** chọn Servlet/Spring MVC stack.
- **spring-boot-starter-tomcat** với scope **provided** để external container cung cấp Tomcat khi deploy.
- Spring Boot repackage tạo executable WAR với classifier exec.
- Trong executable WAR, provided server dependencies có thể được đặt dưới **WEB-INF/lib-provided/** để không xung đột với server ngoài, nhưng vẫn sẵn có cho java -jar.

Nếu dùng Spring Boot parent, execution repackage đã có sẵn; giữ đúng id **repackage** khi ghi đè cấu hình classifier.

### 9.4. Kết quả WAR và cách chạy

Khi cấu hình classifier exec, dự kiến:

~~~text
app/target/
├── app-1.0.0.war
└── app-1.0.0-exec.war
~~~

- **app-1.0.0.war**: WAR thường để deploy vào external Servlet container.
- **app-1.0.0-exec.war**: executable Boot WAR, có thể chạy bằng java -jar.

Chạy bản executable:

~~~bash
java -jar app/target/app-1.0.0-exec.war
~~~

Dòng stdout nghiệp vụ:

~~~text
CATALOG-BOOK-42
~~~

Deploy bản WAR thường lên container theo quy trình của môi trường. URL thường phụ thuộc context path mà container gán theo tên WAR hoặc cấu hình deployment; không mặc định endpoint ở root domain.

### 9.5. Đừng đặt embedded server sai scope

Nếu embedded Tomcat nằm trong WAR như dependency runtime thông thường, external Tomcat có thể gặp class/version conflicts. Nếu server cần được external container cung cấp, dùng provided scope theo cấu hình Boot WAR.

Spring Boot repackage có quy tắc riêng cho provided dependencies: executable WAR có thể đưa chúng vào **WEB-INF/lib-provided/**. Vì vậy **provided không có nghĩa server biến mất khỏi mọi dạng archive**; nó có nghĩa server được xử lý riêng để hai cách chạy (external container và java -jar) có thể cùng tồn tại.

## 10. Gradle: JAR thường và source JAR của library

### 10.1. settings.gradle

File **artifact-demo/settings.gradle**:

~~~groovy
rootProject.name = 'artifact-demo'
include 'core', 'app'
~~~

### 10.2. core/build.gradle hoàn chỉnh

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    withSourcesJar()
}

repositories {
    mavenCentral()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            pom {
                name = 'Catalog Core'
                description = 'Reusable Java library'
            }
        }
    }
    repositories {
        maven {
            name = 'localTest'
            url = uri("${rootProject.projectDir}/build/repository")
        }
    }
}
~~~

Đây là file **core/build.gradle** hoàn chỉnh dùng Groovy DSL:

- **java-library** tạo plain JAR và configurations API/runtime cho thư viện.
- **withSourcesJar()** tạo task **sourcesJar** với classifier **sources**.
- Source JAR được đăng ký như documentation variant của Java component.
- **maven-publish** cùng **from components.java** phát hành Java component, bao gồm binary và source variant.
- Repository **localTest** là Maven repository dạng thư mục để kiểm tra publication mà không cần server bên ngoài.

### 10.3. Build và publish library

Từ root:

~~~bash
./gradlew :core:clean :core:build
./gradlew :core:publishMavenJavaPublicationToLocalTestRepository
~~~

Khi có Gradle Wrapper tương thích. Trên Windows dùng **gradlew.bat**.

Artifacts dự kiến:

~~~text
core/build/libs/
├── core-1.0.0.jar
└── core-1.0.0-sources.jar
~~~

Repository local:

~~~text
build/repository/com/example/core/1.0.0/
├── core-1.0.0.jar
├── core-1.0.0-sources.jar
├── core-1.0.0.pom
└── core-1.0.0.module
~~~

Nếu bỏ **withSourcesJar()**, task sourcesJar và source variant không được tạo tự động theo cách trên. Có thể tự tạo task JAR, nhưng nên ưu tiên API chuẩn của Java plugin.

## 11. Gradle: executable Boot JAR và plain JAR

### 11.1. app/build.gradle hoàn chỉnh

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
    id 'maven-publish'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    withSourcesJar()
}

repositories {
    mavenCentral()
}

dependencies {
    implementation project(':core')
    implementation 'org.springframework.boot:spring-boot-starter'
}

tasks.named('jar') {
    archiveClassifier = ''
}

tasks.named('bootJar') {
    archiveClassifier = 'exec'
}

publishing {
    publications {
        appArtifacts(MavenPublication) {
            from components.java
            artifact(tasks.named('bootJar'))
            pom {
                name = 'Catalog Application'
                description = 'Spring Boot application and executable distribution'
            }
        }
    }
    repositories {
        maven {
            name = 'localTest'
            url = uri("${rootProject.projectDir}/build/repository")
        }
    }
}
~~~

**Cách cấu hình classifier trong ví dụ này có chủ đích:**

- Boot Gradle plugin thường cấu hình plain **jar** task với classifier **plain** khi bootJar cũng tồn tại.
- Ta đặt classifier rỗng cho **jar**, để plain archive giữ tên artifact chính.
- Ta đặt classifier **exec** cho **bootJar**, để executable archive có hậu tố -exec.
- **from components.java** publish plain Java component và source variant.
- **artifact(tasks.named('bootJar'))** thêm executable Boot JAR vào publication dưới dạng artifact phụ.
- Publication này là ví dụ phát hành cả hai file; app vẫn nên được xem là **ứng dụng/distribution**, không phải thư viện để module khác import class.

Nếu không cần publish executable artifact vào Maven repository, bỏ **maven-publish** và block **publishing**; chỉ cần chạy task bootJar để tạo file deployment.

### 11.2. Build và xem kết quả

~~~bash
./gradlew :app:clean :app:build
~~~

Với Spring Boot Gradle plugin, kết quả có thể gồm:

~~~text
app/build/libs/
├── app-1.0.0.jar
├── app-1.0.0-exec.jar
└── app-1.0.0-sources.jar
~~~

- **app-1.0.0.jar**: plain archive từ Java jar task.
- **app-1.0.0-exec.jar**: executable Boot JAR từ bootJar.
- **app-1.0.0-sources.jar**: source archive nếu withSourcesJar được bật.

Chạy executable:

~~~bash
java -jar app/build/libs/app-1.0.0-exec.jar
~~~

Output nghiệp vụ:

~~~text
CATALOG-BOOK-42
~~~

Kiểm tra plain JAR:

~~~bash
jar tf app/build/libs/app-1.0.0.jar
~~~

Kiểm tra Boot JAR:

~~~bash
jar tf app/build/libs/app-1.0.0-exec.jar
~~~

**Đừng publish hoặc triển khai file plain chỉ vì nó đứng đầu danh sách thư mục.** Luôn chọn đúng task/archive theo consumer contract.

## 12. Gradle: WAR và executable Boot WAR

Để tạo WAR, thêm plugin **war** và cấu hình Servlet dependencies trong app module.

### 12.1. Gradle WAR configuration

Phần plugins:

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}
~~~

Dependencies:

~~~groovy
dependencies {
    implementation project(':core')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

Với app class kế thừa **SpringBootServletInitializer** như mục 9.2, Gradle tạo task **bootWar** khi plugin war được áp dụng.

Nếu muốn plain WAR và executable WAR cùng tồn tại:

~~~groovy
tasks.named('war') {
    archiveClassifier = ''
}

tasks.named('bootWar') {
    archiveClassifier = 'exec'
}
~~~

Đây là các cấu hình task thay thế cho lựa chọn JAR ở mục 11. Không cấu hình cùng module để vừa chạy bootJar vừa bootWar nếu project chưa có chủ đích tạo cả hai packaging variants và kiểm soát publication.

### 12.2. Build và kiểm tra

~~~bash
./gradlew :app:clean :app:bootWar
~~~

Kết quả dự kiến:

~~~text
app/build/libs/
├── app-1.0.0.war
└── app-1.0.0-exec.war
~~~

Kiểm tra executable WAR:

~~~bash
jar tf app/build/libs/app-1.0.0-exec.war
~~~

Có thể thấy:

~~~text
WEB-INF/classes/com/example/app/CatalogApplication.class
WEB-INF/lib/...
WEB-INF/lib-provided/...
~~~

Chạy trực tiếp:

~~~bash
java -jar app/build/libs/app-1.0.0-exec.war
~~~

Hoặc deploy plain WAR vào Servlet container bên ngoài theo quy trình của tổ chức. Container phải tương thích Spring Boot/Jakarta Servlet version và WAR phải có Servlet bootstrap phù hợp.

### 12.3. Publish Boot WAR

Nếu muốn publish Boot WAR, Spring Boot Gradle Plugin cho phép thêm task output vào MavenPublication:

~~~groovy
publishing {
    publications {
        bootApplication(MavenPublication) {
            artifact(tasks.named('bootWar'))
        }
    }
}
~~~

Đây là **fragment publication**. Module cần plugin **maven-publish** và repository publish phù hợp. Nếu cần plain WAR làm main artifact cùng executable WAR classifier, hãy cấu hình classifier/Java-Web component và kiểm tra POM/artifact cuối thay vì giả định chỉ thêm một dòng artifact sẽ tự tạo mọi metadata mong muốn.

## 13. So sánh cấu trúc file để nhận diện đúng artifact

| Đặc điểm | JAR thường | Boot JAR | WAR thường | Boot WAR | Source JAR |
| --- | --- | --- | --- | --- | --- |
| Package chính | .jar | .jar | .war | .war | .jar |
| Java classes | package path root | BOOT-INF/classes | WEB-INF/classes | WEB-INF/classes | thường không có .class sản phẩm |
| Runtime dependencies | metadata riêng, thường không lồng | BOOT-INF/lib | WEB-INF/lib theo packaging | WEB-INF/lib và lib-provided | không đóng gói runtime deps |
| Spring Boot loader | Không | Có | Không nhất thiết | Có | Không |
| java -jar | Không mặc định | Có | Không mặc định | Có với executable Boot WAR | Không |
| External Servlet container | Không | Không phải mục đích | Có | Có nếu cấu hình deployable đúng | Không |
| Dùng làm compile dependency | Có | Không nên | Không | Không nên | Không |
| Mục đích chính | Library | App distribution | Web deployment | Boot app + Servlet deployment | Source/debug |

**Cấu trúc là bằng chứng nhanh.** Tên file và classifier có thể tùy chỉnh; nội dung archive mới cho biết loại artifact thực tế.

## 14. Cách kiểm tra manifest và entry của JAR/WAR

### 14.1. Xem file archive

Dùng JDK:

~~~bash
jar tf core/target/core-1.0.0.jar
jar tf app/target/app-1.0.0-exec.jar
jar tf app/target/app-1.0.0-exec.war
~~~

Lệnh **jar tf** liệt kê entry, không giải nén và không sửa file.

### 14.2. Xem manifest

Với công cụ unzip:

~~~bash
unzip -p app/target/app-1.0.0-exec.jar META-INF/MANIFEST.MF
~~~

Manifest Boot JAR thường có:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.app.CatalogApplication
~~~

Tên launcher cụ thể phụ thuộc Spring Boot version/loader implementation. Không hard-code giá trị này như hợp đồng của mọi Boot release; hãy xem manifest thực tế của artifact đang phát hành.

Với JAR thường, manifest có thể chỉ có version/creator hoặc Main-Class nếu cấu hình. Không kỳ vọng có Spring Boot Start-Class.

### 14.3. Source JAR

~~~bash
jar tf core/target/core-1.0.0-sources.jar
~~~

Kiểm tra source path tương ứng và không có file không được phép phát hành. Source JAR là nguồn để IDE attach, không phải bản copy runtime của thư viện.

### 14.4. So sánh checksum và kích thước

Có thể tính SHA-256:

~~~bash
sha256sum core/target/core-1.0.0.jar
sha256sum core/target/core-1.0.0-sources.jar
sha256sum app/target/app-1.0.0-exec.jar
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "app\target\app-1.0.0-exec.jar"
~~~

Lưu checksum cùng release metadata nếu chính sách phát hành yêu cầu. Hash khác nhau giữa plain JAR và Boot JAR là điều bình thường vì nội dung/packaging khác nhau; không so chúng để kết luận build tái lập.

## 15. Đưa đúng artifact vào Maven/Gradle publication

### 15.1. Maven install/deploy

Maven lifecycle:

- **package**: tạo file archive trong target.
- **verify**: chạy các kiểm tra và plugin đã gắn, ví dụ attach source JAR.
- **install**: cài artifact/POM/classifiers vào local Maven repository.
- **deploy**: publish artifact/POM/classifiers lên remote repository.

Với multi-module:

~~~bash
mvn clean verify
mvn install
mvn deploy
~~~

Các lệnh là các bước theo môi trường, không nhất thiết chạy tất cả liên tiếp trong mọi pipeline. **deploy** cần distributionManagement, credentials và quyền truy cập repository được cấu hình.

Kiểm tra log install/deploy để xác nhận cả:

- Main JAR hoặc WAR.
- Classifier **sources**.
- Classifier **exec** nếu có.
- POM đúng tọa độ.
- Checksums/signatures nếu repository hoặc policy tạo chúng.

### 15.2. Gradle publication

Gradle dùng **MavenPublication**:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
~~~

Với Java component có **withSourcesJar()**, source variant được thêm vào publication. Nếu publish Boot JAR/Boot WAR riêng, gắn output task qua **artifact(tasks.named(...))** theo đúng classifier.

Task publication cụ thể được sinh từ publication name và repository name, ví dụ:

~~~bash
./gradlew :core:publishMavenJavaPublicationToLocalTestRepository
~~~

Đừng giả định tên task giống nhau ở mọi project; kiểm tra tasks hoặc log Gradle để biết tên thực tế.

### 15.3. Một publication hay nhiều publication?

Chọn dựa trên mục đích:

| Trường hợp | Cách phát hành gợi ý |
| --- | --- |
| Core library | Java component plain JAR + sources + metadata |
| Boot service chỉ để deploy | Boot JAR qua artifact registry/build output |
| Cần giữ plain app JAR và Boot JAR cùng Maven GAV | Plain JAR làm main artifact, Boot JAR classifier rõ như exec |
| Servlet app | WAR deployable; có thể thêm executable Boot WAR classifier |
| Source code | Classifier sources gắn với đúng binary version |

Nếu artifact ứng dụng được lưu ở Maven repository, ghi rõ trong tài liệu phát hành rằng classifier exec là **deployment artifact**, không phải library dependency.

## 16. Lựa chọn artifact trong CI/CD và release pipeline

Một release pipeline tốt nên biết rõ file nào là output chính:

1. **Library pipeline:** compile/test, tạo JAR, tạo sources JAR, kiểm tra POM/Module Metadata, publish binary + source.
2. **Boot service pipeline:** test app, tạo bootJar, smoke test java -jar, tạo SBOM/checksum, publish deployment artifact hoặc container image.
3. **WAR pipeline:** test trên đúng Servlet/Jakarta API, tạo WAR, kiểm tra WEB-INF và provided libraries, deploy thử vào container mục tiêu.
4. **Source release:** xác nhận source thuộc đúng commit, không chứa secret/generated private files, đồng bộ classifier/version với binary.

### 16.1. Kiểm tra không publish nhầm file

Không dùng lệnh wildcard kiểu **upload mọi *.jar trong build/libs** nếu thư mục có plain, executable và source JAR. Hãy chỉ định đúng path hoặc task output.

Ví dụ:

~~~text
Library:
  core/build/libs/core-1.0.0.jar
  core/build/libs/core-1.0.0-sources.jar

Application:
  app/build/libs/app-1.0.0-exec.jar
~~~

Nếu Gradle/Maven đặt tên khác do classifier/finalName, pipeline phải lấy đúng artifact path từ task/build configuration.

### 16.2. Consumer smoke test

- Với library: tạo project consumer độc lập, khai báo GAV và compile một class gọi public API.
- Với Boot JAR: chạy java -jar artifact và kiểm tra health/output.
- Với WAR: deploy vào Servlet container tương thích và kiểm tra endpoint/context path.
- Với source JAR: mở archive và xác nhận source files tương ứng version.

**Build success không đồng nghĩa publication đúng.** Cần kiểm tra artifact cuối, classifier, metadata và cách consumer thực sự dùng file.

## 17. Các lỗi phổ biến và cách xử lý

**1. Dùng Boot JAR làm dependency của một module Java khác.** Class nằm dưới BOOT-INF/classes. **Sửa:** publish plain JAR của library module và giữ Boot JAR cho deployment.

**2. Chỉ phát hành plain JAR của Spring Boot app nhưng kỳ vọng java -jar chạy được.** Plain JAR thường không mang Boot loader và nested runtime dependencies. **Sửa:** phát hành executable Boot JAR hoặc đóng gói classpath riêng có chủ đích.

**3. Publish Boot JAR đè lên artifact library.** Consumer GAV có thể tải nhầm archive không có package root. **Sửa:** dùng module library riêng hoặc classifier exec, kiểm tra main artifact trước deploy.

**4. Nghĩ classifier exec biến artifact thành một tọa độ module độc lập.** Classifier chỉ phân biệt artifact phụ trong cùng GAV. **Sửa:** dùng tọa độ riêng nếu sản phẩm cần metadata/consumer contract khác.

**5. Dùng WAR cho một library Java.** WAR dành cho web application. **Sửa:** chọn JAR thường cho thư viện.

**6. Chọn WAR nhưng quên SpringBootServletInitializer.** External Servlet container có thể không khởi tạo Boot context theo cách mong muốn. **Sửa:** cấu hình initializer cho traditional Servlet deployment và thử container thật.

**7. Đưa embedded Tomcat vào WAR như dependency runtime bình thường.** External container có thể gặp xung đột class/server. **Sửa:** dùng provided/providedRuntime theo Maven/Gradle và kiểm tra WEB-INF/lib-provided trong executable Boot WAR.

**8. Nghĩ mọi Boot WAR đều deploy được vào mọi Tomcat.** Jakarta Servlet/API compatibility phụ thuộc Boot và container version. **Sửa:** xác nhận version container và namespace tương thích.

**9. Chọn WAR chỉ vì file có đuôi .war.** WAR có thể thiếu bootstrap hoặc dependencies cần thiết. **Sửa:** kiểm tra Servlet initialization, archive layout và deploy smoke test.

**10. Chỉ publish source JAR mà quên binary JAR.** Consumer không thể dùng source archive làm dependency sản phẩm. **Sửa:** publish source JAR như artifact bổ sung bên cạnh binary.

**11. Source JAR không được tạo trong Maven.** Chỉ thêm tên file trong README không tạo archive. **Sửa:** cấu hình Maven Source Plugin goal jar-no-fork ở lifecycle thích hợp.

**12. Quên withSourcesJar() trong Gradle.** Không có source variant tự động trong Java component. **Sửa:** bật java.withSourcesJar() và kiểm tra publication output.

**13. Source JAR không khớp binary version.** Debugger hiển thị dòng source sai. **Sửa:** build source và binary từ cùng commit, version, source set.

**14. Source JAR vô tình chứa secret hoặc source nội bộ.** Source archive thường được tải dễ dàng như artifact khác. **Sửa:** kiểm tra include/exclude patterns, license và policy trước release.

**15. Maven repackage mặc định thay artifact chính.** File gốc được giữ dưới dạng .original trong target nhưng không phải classifier được publish. **Sửa:** cấu hình classifier nếu cần giữ plain archive trong install/deploy.

**16. Dùng attach=false nhưng mong Boot JAR được deploy.** Plugin tạo executable file local nhưng không attach vào install/deploy. **Sửa:** bỏ attach=false hoặc publish file qua một distribution step riêng.

**17. Maven khai báo classifier exec nhưng execution id không trùng repackage.** Cấu hình có thể không áp dụng vào execution do parent tạo. **Sửa:** kiểm tra execution id của Spring Boot parent và plugin effective POM.

**18. Gradle chỉ chạy jar task khi muốn Boot JAR.** Task jar tạo plain archive. **Sửa:** chạy bootJar cho executable archive.

**19. Gradle chỉ chạy bootJar khi cần source archive.** Boot JAR không thay thế sourcesJar. **Sửa:** bật withSourcesJar và build task sourcesJar/assemble/build theo cấu hình.

**20. Gradle không đặt classifier rõ khi cần phát hành song song.** Plugin có thể gán plain classifier cho jar/war task mặc định. **Sửa:** cấu hình archiveClassifier cho cả plain và executable tasks, sau đó kiểm tra tên file.

**21. Publish mọi archive bằng wildcard.** Consumer có thể tải nhầm -plain.jar, -sources.jar hoặc Boot JAR. **Sửa:** khai báo chính xác artifact tasks/paths.

**22. Chỉ nhìn tên file để xác nhận loại artifact.** Classifier có thể được đổi tùy ý. **Sửa:** dùng jar tf, manifest và archive layout.

**23. Cho rằng plain JAR tự chứa dependency.** Plain JAR library thường chỉ chứa classes/resources của module. **Sửa:** publish POM/Gradle Module Metadata và để consumer resolve dependencies.

**24. Dùng source JAR làm runtime dependency.** Nó không cung cấp bytecode sản phẩm. **Sửa:** chỉ attach source để IDE/debug; dùng binary JAR trong dependency graph.

**25. Publish Boot JAR nhưng POM thiếu dependency metadata.** Một artifact có thể chạy độc lập nhưng metadata của consumer vẫn không đầy đủ. **Sửa:** phân biệt deployment package với library publication và kiểm tra POM.

**26. Dùng executable WAR với WebFlux mà giả định Boot traditional WAR được hỗ trợ.** WebFlux có giới hạn triển khai WAR riêng của Spring Boot. **Sửa:** kiểm tra tài liệu reactive deployment; với Boot WebFlux, ưu tiên executable JAR theo hướng được hỗ trợ.

**27. Không kiểm tra external container thực tế.** WAR có thể build thành công nhưng fail do Servlet version, classloader hoặc context path. **Sửa:** smoke test trên đúng container/version của môi trường.

**28. Tưởng source JAR tự chứa Javadoc.** Source archive chứa source; Javadoc là loại documentation artifact riêng. **Sửa:** nếu cần API docs, cấu hình Javadoc JAR riêng.

**29. Thay đổi classifier mà không cập nhật release pipeline.** CI có thể tiếp tục upload path cũ hoặc bỏ sót artifact mới. **Sửa:** kiểm tra output names, publication configuration và consumer contract.

**30. Publish cùng GAV nhưng ghi đè bytes khác.** Maven/Gradle cache có thể khiến consumer thấy artifact cũ/mới không đồng nhất. **Sửa:** release version immutable; tăng version khi nội dung binary thay đổi.

## 18. Checklist trước khi phát hành

- [ ] Xác định người nhận sẽ **import class**, **chạy app**, **deploy WAR** hay **đọc source**.
- [ ] Chọn đúng loại artifact: plain JAR, Boot JAR, WAR hoặc source JAR.
- [ ] Giữ library module tách khỏi executable application module.
- [ ] Kiểm tra GAV và classifier nhất quán giữa build, publication và consumer.
- [ ] Maven: kiểm tra packaging jar/war, repackage execution, classifier, attach và source plugin.
- [ ] Gradle: kiểm tra jar/bootJar hoặc war/bootWar, archiveClassifier và withSourcesJar().
- [ ] Không dùng Boot executable JAR làm dependency compile.
- [ ] Với WAR, xác nhận SpringBootServletInitializer và Servlet/Jakarta container compatibility.
- [ ] Với executable WAR, kiểm tra provided dependencies và WEB-INF/lib-provided.
- [ ] Source JAR phải cùng version/commit với binary.
- [ ] Source distribution không chứa secret hoặc code ngoài phạm vi được phép.
- [ ] Chạy jar tf và kiểm tra manifest/layout của artifact cuối.
- [ ] Chạy java -jar cho Boot JAR/Boot WAR.
- [ ] Deploy WAR vào container mục tiêu nếu đó là hợp đồng phát hành.
- [ ] Consumer độc lập resolve đúng binary và dependency metadata.
- [ ] CI upload đúng artifact, không wildcard tất cả file trong output directory.
- [ ] Lưu checksum/SBOM/signature/provenance theo chính sách release.
- [ ] Release version bất biến; thay đổi bytes cần version mới.

## 19. Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Packaging Executable Archives (Maven): https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Packaging Executable Archives (Gradle): https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 — Publishing an Application with Gradle: https://docs.spring.io/spring-boot/3.3/gradle-plugin/publishing.html
- Maven Source Plugin — Usage and source JAR attachment: https://maven.apache.org/plugins/maven-source-plugin/usage.html
- Maven Source Plugin — jar-no-fork goal: https://maven.apache.org/plugins/maven-source-plugin/jar-no-fork-mojo.html
- Gradle 8.5 — Java Plugin and sources JAR: https://docs.gradle.org/8.5/userguide/java_plugin.html
- Gradle 8.5 — Maven Publish Plugin: https://docs.gradle.org/8.5/userguide/publishing_maven.html
- Maven — POM Reference: https://maven.apache.org/pom.html
- Maven — Maven Deploy Plugin: https://maven.apache.org/plugins/maven-deploy-plugin/
- Java 17 — Jar tool: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html

**Kết luận:** Hãy chọn artifact theo **cách người nhận sẽ sử dụng sản phẩm**. **JAR thường** là binary cho thư viện, **Boot JAR** là deployment package tự chạy, **WAR** là web archive cho Servlet container và **source JAR** là mã nguồn đi kèm binary. Maven/Gradle có thể tạo và publish nhiều loại artifact cùng version bằng classifier, nhưng classifier không thay đổi cấu trúc bên trong file. Luôn kiểm tra **tọa độ, classifier, archive layout, dependency metadata và cách chạy/deploy thực tế** trước khi đánh dấu release hoàn tất.