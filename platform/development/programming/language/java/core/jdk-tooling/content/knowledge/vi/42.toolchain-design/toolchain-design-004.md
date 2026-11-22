# Chọn cách đóng gói ứng dụng Java

## Mục tiêu

Sau bài này, bạn có thể chọn định dạng artifact phù hợp với loại sản phẩm và môi trường triển khai; phân biệt library JAR, executable JAR, fat/uber JAR, WAR, EAR, application distribution, container image, runtime image và native executable; hiểu Maven packaging và các Gradle plugin tương ứng; cấu hình ví dụ cho từng cách đóng gói; cân nhắc dependency, runtime, platform, update, vận hành và bảo mật; kiểm tra nội dung package; và thiết kế pipeline tạo đúng deliverable cho consumer.

## 1. Đóng gói là bước nào trong build?

Đóng gói (packaging) là bước gom bytecode, resource, dependency, metadata và đôi khi cả runtime hoặc launcher thành một đơn vị có thể phân phối hoặc triển khai.

~~~text
Source code + resources
          |
          v
       Compile
          |
          v
        Test
          |
          v
   Package / Archive
          |
          +----> Library JAR
          +----> Executable JAR
          +----> WAR / EAR
          +----> ZIP / TAR distribution
          +----> Container image
          +----> Runtime image / installer
          +----> Native executable
~~~

Các định dạng này phục vụ những consumer và môi trường khác nhau. Một library được đưa vào compile classpath của project khác có contract khác với một ứng dụng web được deploy lên servlet container hoặc một desktop application được cài trên Windows/macOS.

Đừng chọn định dạng chỉ vì build tool tạo nó mặc định. Trước hết cần xác định ai sẽ nhận artifact, họ sẽ chạy nó như thế nào và môi trường đích đã cung cấp những gì.

### Phân biệt artifact, archive và deployment unit

- **Artifact:** file output được định danh và phân phối, ví dụ JAR hoặc WAR.
- **Archive:** container file như JAR, ZIP, TAR có cấu trúc entry.
- **Deployment unit:** gói mà nền tảng triển khai hiểu được, ví dụ WAR trên servlet container, EAR trên Jakarta EE server hoặc OCI image trên container platform.
- **Runtime image:** thư mục/gói chứa Java runtime đã được tùy chỉnh cùng ứng dụng.
- **Installer:** gói cài đặt theo hệ điều hành, ví dụ MSI, DMG, DEB hoặc RPM.

Một JAR có thể là artifact library, executable application hoặc thành phần nằm trong WAR/EAR. Phần mở rộng file một mình không nói hết cách ứng dụng được khởi chạy.

## 2. Ma trận chọn cách đóng gói

| Nhu cầu | Cách đóng gói thường phù hợp | Consumer / môi trường |
|---|---|---|
| Thư viện dùng trong project Java khác | Library JAR | Maven/Gradle repository, classpath hoặc module path |
| CLI nhỏ, ít dependency | Executable JAR | Người dùng chạy `java -jar` |
| Ứng dụng độc lập có nhiều dependency | Application distribution hoặc fat JAR | Server/VM có Java runtime |
| Spring Boot service tự chứa | Executable Boot JAR | JVM chạy `java -jar`, container |
| Web app deploy vào servlet container | WAR | Tomcat, Jetty hoặc container tương thích |
| Ứng dụng enterprise gồm nhiều module | EAR | Jakarta EE application server |
| CLI/service cần thư mục `bin`, `lib`, config và script | ZIP/TAR distribution | Máy chủ hoặc người dùng cài Java |
| Desktop app cần installer và runtime riêng | `jpackage` package | Windows, macOS, Linux |
| Service chạy trên Kubernetes/container platform | OCI container image | Docker/container runtime/orchestrator |
| Ứng dụng cần binary native, không yêu cầu cài JVM | GraalVM Native Image | OS/architecture đã build |

Đây là các lựa chọn phổ biến, không phải quy tắc cứng. Một Spring Boot application có thể phát hành executable JAR, WAR hoặc container image. Một Java CLI có thể phát hành ZIP distribution, installer hoặc native executable.

### Câu hỏi quyết định

1. Consumer là developer, application server, end user hay container platform?
2. Consumer đã có Java runtime chưa?
3. Ứng dụng có cần chạy độc lập bằng một lệnh không?
4. Có cần deploy lên servlet container/Jakarta EE server không?
5. Có cần bundle dependency, runtime, native library hoặc config không?
6. Cần cập nhật dependency riêng hay muốn một file duy nhất?
7. Phải hỗ trợ OS, CPU architecture nào?
8. Cần installer, service script, container orchestration hay chỉ một library?
9. Có dùng reflection, JNI, dynamic loading hoặc framework làm native image phức tạp không?

Trả lời các câu hỏi này trước khi chọn plugin hoặc sửa POM/build.gradle.

## 3. Library JAR — lựa chọn cho Java library

Nếu module cung cấp class, interface, API hoặc resource để project khác sử dụng, thông thường hãy tạo **library JAR**.

Ví dụ:

~~~text
domain-1.0.0.jar
validation-2.1.0.jar
client-sdk-3.0.0.jar
~~~

Một library JAR thường chứa:

~~~text
domain-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/acme/domain/
    ├── Customer.class
    └── CustomerService.class
~~~

Dependency thường được quản lý riêng qua POM hoặc Gradle Module Metadata. Consumer khai báo tọa độ library và build tool tải dependency bắc cầu theo metadata.

### Vì sao không nên mặc định gộp mọi dependency vào library JAR?

- Consumer có thể muốn dùng version dependency khác.
- Gộp dependency có thể gây trùng class với library khác.
- Khó xác định dependency gốc khi debug.
- Có thể làm mất metadata và license notice của dependency.
- Thay đổi dependency buộc phải phát hành lại một file lớn dù API library không đổi.

Chỉ shade/relocate dependency trong library khi đó là một phần có chủ đích của contract phân phối, ví dụ cần cô lập implementation dependency để tránh xung đột namespace.

### Maven

Maven mặc định dùng packaging `jar` nếu POM không khai báo packaging khác. Có thể ghi rõ:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme.platform</groupId>
    <artifactId>domain</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
</project>
~~~

Build:

~~~bash
./mvnw clean package
~~~

Artifact thường được tạo tại:

~~~text
target/domain-1.0.0.jar
~~~

### Gradle

Với Java library, dùng Java Library plugin:

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.acme.platform'
version = '1.0.0'
~~~

Build JAR:

~~~bash
./gradlew clean jar
~~~

Artifact thường ở `build/libs/domain-1.0.0.jar`.

Khi publish library, cấu hình Maven Publish để xuất bản component cùng POM/metadata. Sources JAR và Javadoc JAR có thể được tạo thêm nếu consumer cần IDE navigation hoặc API documentation.

## 4. Executable JAR — chạy bằng java -jar

Một executable JAR có entry point được chỉ ra trong manifest. Java launcher đọc trường `Main-Class` để biết class có phương thức `public static void main(String[] args)`.

Ví dụ chương trình Java 17:

~~~java
package com.example;

public class HelloApp {
    public static void main(String[] args) {
        System.out.println("Hello from packaged Java application");
    }
}
~~~

Lưu file tại `src/main/java/com/example/HelloApp.java`.

Compile và tạo JAR:

~~~bash
mkdir -p out build
javac -d out src/main/java/com/example/HelloApp.java
jar --create --file build/hello-app.jar \
    --main-class com.example.HelloApp -C out .
~~~

Chạy:

~~~bash
java -jar build/hello-app.jar
~~~

Stdout chính xác:

~~~text
Hello from packaged Java application
~~~

Lệnh `jar --main-class` tạo manifest entry `Main-Class`. Có thể kiểm tra:

~~~bash
unzip -p build/hello-app.jar META-INF/MANIFEST.MF
~~~

### Executable JAR không tự động chứa dependency

Ví dụ trên chỉ có class của ứng dụng và không cần thư viện ngoài. Nếu chương trình dùng dependency ngoài, JAR thông thường không tự nhúng các dependency đó.

Khi chạy `java -jar`, Java launcher lấy class của ứng dụng từ JAR được chỉ định và bỏ qua classpath bên ngoài được truyền bằng `-cp`/`-classpath`. Vì vậy, lệnh:

~~~bash
java -cp "lib/*" -jar app.jar
~~~

không phải cách bổ sung dependency cho executable JAR.

Các hướng xử lý:

- Dùng manifest `Class-Path` trỏ tới các JAR dependency bên cạnh.
- Phát hành application distribution có thư mục `lib` và launcher script.
- Tạo fat/uber JAR.
- Dùng framework hỗ trợ nested dependency như Spring Boot executable JAR.

### Khi nào chọn executable JAR đơn giản?

- Ứng dụng nhỏ.
- Dependency chỉ gồm JDK hoặc có classpath được quản lý rõ.
- Consumer có Java runtime tương thích.
- Cần một lệnh khởi chạy đơn giản.
- Không cần tích hợp deployment contract của application server.

## 5. Thin JAR, fat JAR và uber JAR

| Loại | Nội dung | Cách chạy |
|---|---|---|
| Thin JAR | Class/resource của project; dependency ở ngoài | Classpath/manifest Class-Path hoặc launcher |
| Fat/Uber JAR | Class/resource của project và dependency đã gộp vào một archive | Thường dùng `java -jar` nếu có launcher manifest phù hợp |
| Nested executable JAR | Dependency JAR được đặt bên trong archive theo định dạng loader hiểu | Dùng launcher của framework, ví dụ Spring Boot |

### Thin JAR

Ưu điểm:

- Giữ dependency tách biệt.
- Có thể thay dependency mà không rebuild application archive nếu contract cho phép.
- Dễ kiểm tra dependency và metadata.
- Tránh gộp class/resource trùng nhau.

Nhược điểm:

- Phải phát hành đủ dependency.
- Consumer cần launcher/classpath đúng.
- Cần quản lý version và thư mục lib.

### Fat/Uber JAR

Ưu điểm:

- Một file chính để copy/deploy.
- Dễ khởi chạy bằng `java -jar`.
- Ít bước thiết lập classpath cho consumer.

Nhược điểm:

- Dependency bị gộp có thể xung đột class hoặc resource.
- Khó cập nhật một dependency độc lập.
- Archive lớn hơn và có thể chứa nhiều code không dùng.
- Signature của dependency không còn có ý nghĩa sau khi nội dung bị tái đóng gói; cần quản lý license, notices và provenance đúng cách.

Nếu nhiều dependency có cùng package/class, cần xem xét relocation (đổi package namespace) hoặc chọn dependency version tương thích.

### Tài nguyên trùng và ServiceLoader

Khi gộp JAR, không thể chỉ copy đè mọi file cùng đường dẫn:

- `META-INF/services/*` có thể chứa nhiều provider declaration; cần merge đúng cách.
- Manifest cần được tạo lại cho artifact cuối.
- License/NOTICE resource cần được giữ theo policy.
- Signature file cũ như `.SF`, `.RSA`, `.DSA` không còn hợp lệ sau khi archive bị biến đổi.
- File cấu hình có thể cần resource transformer hoặc quy tắc merge riêng.

Test các tính năng dùng ServiceLoader, logging provider, JDBC driver, framework auto-configuration và resource lookup sau khi tạo uber JAR.

### Maven Shade Plugin

Maven Shade Plugin tạo uber JAR và hỗ trợ relocate package. Ví dụ cấu hình:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.2</version>
    <executions>
        <execution>
            <phase>package</phase>
            <goals>
                <goal>shade</goal>
            </goals>
            <configuration>
                <transformers>
                    <transformer implementation=
                      "org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                        <mainClass>com.example.Main</mainClass>
                    </transformer>
                    <transformer implementation=
                      "org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Build:

~~~bash
./mvnw clean package
~~~

Kiểm tra JAR được tạo trong `target/`, manifest, service descriptors và runtime behavior. Với project có nhiều resource trùng, cần cấu hình transformer phù hợp từng loại resource.

### Gradle

Gradle Java plugin tạo JAR thông thường, không tự động gộp toàn bộ dependency vào fat JAR. Có thể dùng plugin chuyên biệt hoặc cấu hình task archive tùy yêu cầu. Trước khi chọn plugin, xác định cách merge resource, service descriptors, signatures và package relocation sẽ được xử lý như thế nào.

## 6. Spring Boot executable JAR và WAR

Spring Boot hỗ trợ executable archive chứa application classes và dependency để có thể chạy bằng `java -jar`.

### Executable Boot JAR

Một Boot JAR thường có cấu trúc:

~~~text
application.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
└── BOOT-INF/
    ├── classes/
    └── lib/
        ├── dependency-a.jar
        └── dependency-b.jar
~~~

Các dependency vẫn là JAR riêng nằm bên trong archive. Spring Boot loader biết cách tải chúng khi chạy ứng dụng.

Đây không phải cách gộp mọi class thành một namespace duy nhất như shaded JAR.

Chạy:

~~~bash
java -jar application.jar
~~~

### Maven

Spring Boot Maven Plugin dùng goal `repackage` để tạo executable archive từ JAR/WAR đã được package:

~~~xml
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
~~~

Nếu project dùng Spring Boot parent, execution có thể đã được cấu hình sẵn. Chạy lifecycle `package` để tạo source archive và executable archive.

### Gradle

Spring Boot Gradle Plugin tạo task `bootJar` khi plugin được cấu hình cùng Java plugin:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
}

tasks.bootJar {
    archiveFileName = 'application.jar'
}
~~~

Version plugin chỉ là ví dụ; hãy chọn version tương thích với Spring Boot line và Gradle wrapper của project.

Build:

~~~bash
./gradlew clean bootJar
~~~

`bootJar` tạo executable archive; task `jar` có thể tạo plain JAR riêng. Nếu cả hai cùng tồn tại, kiểm tra classifier và tên file để tránh publish nhầm artifact.

### Khi nào chọn Boot JAR?

- Service được triển khai như process JVM độc lập.
- Runtime platform hỗ trợ chạy Java command hoặc container.
- Muốn đóng gói embedded server và dependency.
- Không cần deploy WAR vào servlet container bên ngoài.

Nếu nền tảng deployment đã chuẩn hóa WAR hoặc yêu cầu servlet container do tổ chức quản lý, cân nhắc executable/deployable WAR.

## 7. WAR — Web Application Archive

WAR là định dạng triển khai Java web application, thường dành cho Servlet-based application.

Cấu trúc phổ biến:

~~~text
web-app.war
├── index.html
├── assets/
└── WEB-INF/
    ├── classes/
    ├── lib/
    │   ├── application-library.jar
    │   └── another-library.jar
    └── web.xml
~~~

WAR chứa web resource như HTML/CSS/JavaScript, class production trong `WEB-INF/classes`, dependency runtime trong `WEB-INF/lib` và deployment descriptor/metadata phù hợp nền tảng.

Servlet container đọc WAR và triển khai web application. Tùy phiên bản Jakarta Servlet/Jakarta EE, container cung cấp API và runtime cần thiết.

### Khi nào chọn WAR?

- Ứng dụng web chạy trên servlet container do môi trường đích quản lý.
- Tổ chức cần deploy nhiều web application lên cùng container.
- Runtime lifecycle, thread pool, connector, TLS hoặc monitoring do container quản lý.
- Cần dùng deployment convention của application server.

Không chọn WAR chỉ vì ứng dụng có HTTP endpoint. Một service Spring Boot có thể dùng executable JAR và embedded server mà không cần WAR.

### Dependency do container cung cấp

Không đóng gói servlet API hoặc library mà container yêu cầu application server cung cấp theo policy. Với Maven, dependency thường có scope `provided`; với Gradle War plugin, dùng configuration provided phù hợp.

Nếu đóng gói nhầm API/container library, có thể gặp classloader conflict, `ClassCastException`, `NoSuchMethodError` hoặc lỗi khởi tạo servlet.

### Maven WAR

POM:

~~~xml
<packaging>war</packaging>
~~~

Maven WAR Plugin thu thập dependency, class và resource của web application trong phase `package`.

Build:

~~~bash
./mvnw clean package
~~~

Artifact thường nằm ở `target/<artifactId>-<version>.war`.

### Gradle WAR

~~~groovy
plugins {
    id 'war'
}
~~~

War plugin thu thập static resource từ `src/main/webapp`, class production vào `WEB-INF/classes` và dependency runtime vào `WEB-INF/lib`.

Build:

~~~bash
./gradlew clean war
~~~

Artifact thường ở `build/libs/`.

### Spring Boot WAR

Spring Boot có thể tạo WAR vừa deploy lên external servlet container vừa chạy bằng `java -jar`. Khi deploy truyền thống, cần cấu hình embedded servlet container ở dạng provided/providedRuntime và tích hợp application với servlet initializer theo hướng dẫn Spring Boot.

Kiểm tra `WEB-INF/lib` và `WEB-INF/lib-provided` để chắc chắn dependency container không bị đóng gói sai.

## 8. EAR — Enterprise Archive

EAR là gói enterprise application dành cho Jakarta EE application server. Nó có thể gom nhiều thành phần như:

- Web module (WAR).
- Enterprise bean module (EJB JAR).
- Java library module.
- Resource adapter (RAR).
- Deployment descriptor và metadata của application.

Ví dụ cấu trúc:

~~~text
enterprise-app.ear
├── META-INF/
│   └── application.xml
├── web-portal.war
├── business-ejb.jar
└── lib/
    └── shared-library.jar
~~~

EAR cho phép triển khai một bộ module enterprise như một application unit. Application server quản lý module lifecycle, classloader, transaction, security và dịch vụ enterprise theo platform.

### Khi nào chọn EAR?

- Tổ chức dùng Jakarta EE application server hỗ trợ EAR.
- Ứng dụng có nhiều module enterprise cần deploy cùng nhau.
- Cần chia web module, EJB module và shared library theo deployment contract.
- Cần quản lý cấu hình application ở cấp enterprise.

Không chọn EAR cho một Spring Boot microservice độc lập hoặc một web app đơn giản nếu không có yêu cầu application server.

### Maven EAR

POM của EAR project:

~~~xml
<packaging>ear</packaging>
~~~

Maven EAR Plugin gom các module đã khai báo và có thể tạo deployment descriptor như `application.xml`.

Build:

~~~bash
./mvnw clean package
~~~

### Gradle EAR

~~~groovy
plugins {
    id 'ear'
}
~~~

Gradle Ear plugin cung cấp task `ear` để assemble enterprise archive. Các module triển khai có thể được khai báo trong configuration `deploy`; shared library có thể được đưa vào `earlib`.

Build:

~~~bash
./gradlew clean ear
~~~

EAR phải được kiểm tra trên đúng phiên bản Jakarta EE/application server đích. Một EAR đóng gói thành công chưa chứng minh descriptor, module version hoặc server-specific deployment configuration tương thích.

## 9. Application distribution — ZIP/TAR với bin và lib

Nếu cần phát hành một ứng dụng có nhiều dependency, config, script và tài liệu, **application distribution** thường dễ vận hành hơn việc gộp tất cả thành một JAR.

Ví dụ:

~~~text
my-app-1.0.0/
├── bin/
│   ├── my-app
│   └── my-app.bat
├── lib/
│   ├── my-app.jar
│   ├── dependency-a.jar
│   └── dependency-b.jar
├── conf/
│   └── application.properties
├── README.txt
└── LICENSE
~~~

Ưu điểm:

- Giữ dependency riêng, dễ kiểm tra và thay thế.
- Có launcher script cho Linux/macOS và Windows.
- Có thể kèm config mẫu, license, tài liệu và migration notes.
- Không cần sửa class/resource để merge dependency.
- Dễ phát hành cùng Java runtime riêng nếu cần.

Nhược điểm:

- Nhiều file cần được giữ đồng bộ.
- Cần launcher và classpath đúng.
- Nếu không bundle runtime, máy đích phải cài Java phù hợp.

### Gradle Application plugin

Application plugin hỗ trợ JVM application, yêu cầu khai báo main class:

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'com.example.Main'
}
~~~

Các task chính:

~~~bash
./gradlew run
./gradlew installDist
./gradlew distZip
./gradlew distTar
./gradlew assembleDist
~~~

- `run`: chạy ứng dụng trong môi trường build.
- `installDist`: tạo thư mục cài đặt có launcher và runtime dependencies.
- `distZip`: tạo ZIP distribution.
- `distTar`: tạo TAR distribution.
- `assembleDist`: assemble các định dạng distribution được cấu hình.

Gradle tạo script Unix và Windows trong thư mục `bin`; runtime dependency được đặt trong `lib`.

### Maven Assembly Plugin

Maven Assembly Plugin có thể gom project output, dependency, module, documentation và file tùy chỉnh vào ZIP/TAR distribution.

Có thể dùng assembly descriptor có sẵn hoặc descriptor riêng để quyết định file nào được đưa vào package, dependency nào được copy, cấu trúc thư mục, script/config đi kèm và format ZIP/TAR.

Assembly Plugin phù hợp cho distribution nhiều file. Nếu mục tiêu là một uber JAR cần merge class/resource và xử lý manifest, hãy dùng Shade Plugin hoặc công cụ phù hợp với yêu cầu đó.

## 10. Runtime image và installer bằng jlink/jpackage

Nếu muốn người dùng chạy ứng dụng mà không phải tự cài Java, có thể đóng gói runtime cùng ứng dụng.

Hai công cụ JDK có vai trò khác nhau:

| Công cụ | Kết quả | Mục đích |
|---|---|---|
| `jlink` | Custom runtime image | Tạo Java runtime chứa các module cần thiết |
| `jpackage` | Application image hoặc native installer | Đóng gói app và runtime thành deliverable theo OS |

### jlink

`jlink` ghép các Java module và dependency bắc cầu thành custom runtime image.

Ví dụ với ứng dụng modular:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:build/mods" \
  --add-modules com.example.app \
  --output build/runtime
~~~

Liệt kê module trong runtime:

~~~bash
build/runtime/bin/java --list-modules
~~~

Runtime image chỉ chứa những module đã được liên kết cùng dependency của chúng. Điều này có thể giảm kích thước so với phát hành toàn bộ JDK.

Lưu ý:

- `jlink` làm việc với module path và các module quan sát được.
- Ứng dụng cần có module graph phù hợp.
- Nếu dùng service provider, cân nhắc `--bind-services`.
- Team chịu trách nhiệm cập nhật custom runtime image khi có bản vá Java.
- Runtime image không tự tạo installer hoặc desktop launcher hoàn chỉnh.

### jpackage

`jpackage` đóng gói ứng dụng thành application image hoặc package native theo OS.

Ví dụ tạo application image:

~~~bash
jpackage \
  --type app-image \
  --name HelloApp \
  --input build/input \
  --main-jar hello-app.jar \
  --main-class com.example.Main \
  --dest build/packages
~~~

Thư mục `build/input` phải chứa main JAR và các dependency cần thiết. Nếu không truyền runtime image riêng, `jpackage` có thể dùng `jlink` để tạo runtime cho ứng dụng.

Các loại package có thể gồm:

- Windows: EXE, MSI.
- macOS: PKG, DMG.
- Linux: DEB, RPM.

Mỗi định dạng native cần được build trên platform tương ứng; `jpackage` không cung cấp cross-platform packaging cho mọi OS từ một host duy nhất.

### Khi nào chọn jlink/jpackage?

- Desktop application cần installer và launcher native.
- CLI/application phân phối cho end user không nên yêu cầu cài JDK.
- Muốn kiểm soát runtime Java được ship cùng ứng dụng.
- Có quy trình build và test riêng cho từng OS/architecture.

Nếu deployment là container platform, OCI image có thể phù hợp hơn installer desktop. Nếu người dùng đã quản lý Java runtime tập trung, ZIP distribution có thể đơn giản hơn.

## 11. Container image — gói để triển khai trên container platform

Container image là deployment unit chứa application, runtime/base filesystem và metadata để container runtime khởi chạy process.

Một Java service có thể được đóng gói bằng cách:

1. Build JAR hoặc application distribution.
2. Chọn runtime base image.
3. Copy artifact và file cần thiết vào image.
4. Khai báo user, working directory, environment và entrypoint.
5. Build image và publish tới container registry.

Ví dụ Dockerfile tối giản dùng distribution đã tạo:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY build/install/my-app/ ./

ENTRYPOINT ["bin/my-app"]
~~~

Đây là ví dụ minh họa. Trong production, pin base image theo version/digest đã phê duyệt, cấu hình user không đặc quyền, health check phù hợp và giới hạn quyền/secret theo môi trường.

### Multi-stage build

Multi-stage build tách môi trường compile khỏi runtime image cuối:

~~~dockerfile
FROM gradle:9.0-jdk21 AS build
WORKDIR /workspace
COPY . .
RUN gradle --no-daemon clean installDist

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/build/install/my-app/ ./
ENTRYPOINT ["bin/my-app"]
~~~

Version image trong ví dụ cần được pin theo policy của project. Stage cuối chỉ nhận distribution cần chạy; không cần mang theo Gradle cache, source tree và JDK compiler nếu runtime không cần chúng.

### Khi nào chọn container image?

- Platform triển khai bằng Docker/Kubernetes hoặc OCI-compatible runtime.
- Team muốn đóng gói runtime và app cùng một đơn vị.
- Cần deploy/rollback theo image digest.
- Có registry, orchestration, logging, networking và secret management ở cấp platform.

Container image không thay thế artifact JAR. Thường JAR vẫn là build output, còn image là deployment package được tạo từ JAR/distribution đó.

## 12. Native executable bằng GraalVM Native Image

GraalVM Native Image biên dịch Java bytecode ahead-of-time thành native executable cho một OS/architecture cụ thể.

Ưu điểm có thể gồm khởi động nhanh, không cần JVM riêng khi chạy executable và có thể giảm footprint trong workload phù hợp.

Đổi lại, Native Image có mô hình build khác JVM truyền thống. Nó phân tích tĩnh các code path có thể truy cập tại build time; reflection, JNI, resource loading, serialization hoặc dynamic proxy có thể cần reachability metadata.

Ví dụ mức cơ bản:

~~~bash
native-image -jar application.jar
~~~

Lệnh trên giả định môi trường đã cài Native Image và JAR có cấu hình entry point phù hợp. Với application thực tế, cần cấu hình dependency và metadata đúng theo framework.

### Khi nào nên cân nhắc native image?

- Startup latency và memory footprint là yêu cầu quan trọng.
- Workload có thời gian sống ngắn hoặc scale-to-zero.
- Framework và dependency hỗ trợ Native Image.
- Có thể duy trì build pipeline, metadata và test native riêng.

### Khi nào không nên chọn vội?

- Ứng dụng phụ thuộc reflection/dynamic class loading phức tạp.
- Một số thư viện chưa hỗ trợ Native Image.
- Build native tốn thời gian hoặc cần toolchain/platform riêng.
- Cần cùng một artifact chạy trên nhiều OS/architecture mà không muốn build riêng.

Native executable không phải JAR nhỏ hơn. Đây là một deliverable khác với compatibility, debugging và build requirements riêng.

## 13. Maven packaging và Gradle plugin mapping

### Maven packaging

Maven packaging type xác định lifecycle goals được gắn vào các phase. Các giá trị thường gặp:

| Packaging | Kết quả chính | Plugin/lifecycle |
|---|---|---|
| `jar` | Java library/application JAR | Maven JAR Plugin |
| `war` | Web application archive | Maven WAR Plugin |
| `ear` | Enterprise application archive | Maven EAR Plugin |
| `pom` | POM metadata/parent/aggregator | Không tạo runtime JAR |

Nếu không khai báo packaging, Maven mặc định là `jar`.

Một số plugin có thể bổ sung kiểu package hoặc deliverable khác. Ví dụ Shade tạo uber JAR, Assembly tạo ZIP/TAR distribution, Spring Boot `repackage` tạo executable archive. Đừng nhầm plugin goal với packaging type cốt lõi của Maven.

### Gradle plugin mapping

| Gradle plugin | Deliverable/task |
|---|---|
| `java` | JAR, `jar` |
| `java-library` | Library JAR và API/implementation model |
| `application` | JVM application distribution, `installDist`, `distZip`, `distTar` |
| `war` | WAR archive, `war` |
| `ear` | EAR archive, `ear` |
| `distribution` | ZIP/TAR distribution tùy chỉnh |
| `maven-publish` | Publish artifact/metadata tới Maven repository |
| Spring Boot plugin | `bootJar`, `bootWar` |

Gradle plugin xác định cách tạo archive; Maven Publish hoặc repository publisher xác định cách xuất bản. Tạo file trong build directory và publish file lên repository là hai hành động riêng.

## 14. Chọn theo kiểu sản phẩm

### Java library

Chọn library JAR và publish POM/Gradle metadata. Thêm sources/Javadoc nếu cần. Tránh gộp dependency nếu consumer nên quản lý dependency riêng.

### CLI tool

Nếu chỉ dùng JDK, executable JAR có thể đủ. Nếu có nhiều dependency, chọn ZIP/TAR distribution có launcher script hoặc fat JAR nếu muốn một file duy nhất.

Nếu tool dành cho end user và cần runtime riêng, cân nhắc jpackage hoặc native executable.

### Backend service

Nếu dùng Spring Boot và platform chạy JVM/container, executable Boot JAR là lựa chọn đơn giản. Nếu tổ chức yêu cầu external servlet container, chọn WAR. Nếu deployment platform chuẩn hóa container, build OCI image từ artifact đã kiểm tra.

### Traditional Java web application

Chọn WAR khi runtime đích là servlet container. Chọn EAR khi application server cần quản lý nhiều module enterprise trong một application unit.

### Desktop application

Chọn distribution hoặc jpackage để tạo launcher, runtime và installer theo OS. Nếu cần native startup/resource profile, đánh giá Native Image.

### Enterprise platform

Chọn EAR khi có module và server contract phù hợp. Không tạo EAR chỉ để gom nhiều JAR nếu deployment runtime không hiểu EAR.

## 15. Những yếu tố phải kiểm tra trước khi chốt

### Runtime compatibility

- Java version tối thiểu của consumer.
- JDK/JRE hay runtime image đã bundle.
- Class file version và module path.
- Servlet/Jakarta EE version nếu dùng WAR/EAR.
- OS, CPU architecture và native library.

### Dependency model

- Dependency nằm ngoài, trong archive hay nested?
- Ai chịu trách nhiệm cập nhật dependency?
- Có class/resource trùng không?
- Có ServiceLoader, reflection hoặc framework scanning không?
- License/NOTICE có được giữ khi gộp dependency không?

### Vận hành

- Khởi chạy bằng `java -jar`, script, service manager hay container entrypoint?
- Config đặt trong archive hay mount từ ngoài?
- Log ghi ra stdout/stderr hay file?
- Cách stop/graceful shutdown và health check?
- Có cần native installer hoặc service registration không?

### Release và bảo mật

- Artifact có tọa độ/version rõ ràng?
- Có checksum, signature và provenance?
- Runtime/base image có được vá định kỳ?
- Release archive có reproducible hoặc ít nhất có manifest đầu vào?
- Có SBOM và license notice khi phân phối dependency?

## 16. Kiểm tra package sau khi build

Không chỉ kiểm tra build exit code. Hãy mở archive và xác minh deliverable thực tế.

### Kiểm tra tên và kích thước

Linux/macOS:

~~~bash
ls -lh target/*.jar target/*.war target/*.ear
~~~

Gradle:

~~~bash
ls -lh build/libs/
~~~

PowerShell:

~~~powershell
Get-ChildItem target -File
Get-ChildItem build\libs -File
~~~

### Liệt kê nội dung JAR/WAR/EAR

~~~bash
jar --list --file application.jar
jar --list --file application.war
jar --list --file enterprise-app.ear
~~~

Hoặc kiểm tra ZIP archive:

~~~bash
unzip -t application.jar
unzip -t application.war
unzip -t enterprise-app.ear
~~~

Xác nhận class/resource cần thiết có mặt; manifest và Main-Class/launcher metadata đúng; dependency được đặt đúng vị trí; WAR có `WEB-INF/classes` và `WEB-INF/lib` phù hợp; EAR có module và deployment descriptor cần thiết; distribution có launcher, config mẫu và license; container image có entrypoint, runtime và user đúng; runtime image chạy được trên target platform.

### Kiểm tra từ môi trường consumer

Với JAR:

~~~bash
java -jar application.jar
~~~

Với distribution:

~~~bash
./bin/my-app
~~~

Với WAR/EAR, deploy lên container/server đúng phiên bản và chạy smoke test. Với container, chạy image trong môi trường tương đương production. Với jpackage/native image, test trên từng OS/architecture được hỗ trợ.

## 17. Lỗi thường gặp và cách xử lý

### JAR chạy được trên máy developer nhưng fail trên máy khác

**Nguyên nhân:** máy developer có dependency trong CLASSPATH, local repository hoặc thư mục lib không được phát hành.

**Cách xử lý:** kiểm tra package contents; dùng clean environment; chọn distribution/fat JAR hoặc cấu hình manifest classpath đúng.

### java -jar báo không tìm thấy Main-Class

**Nguyên nhân:** manifest thiếu Main-Class, sai tên class hoặc build nhầm plain JAR.

**Cách xử lý:** kiểm tra META-INF/MANIFEST.MF; cấu hình entry point trong Maven/Gradle hoặc dùng jar --main-class; build lại và chạy smoke test.

### java -jar không tìm thấy dependency

**Nguyên nhân:** JAR là thin JAR nhưng dependency không có trong manifest Class-Path hoặc external launcher.

**Cách xử lý:** phát hành distribution với lib/launcher, cấu hình manifest Class-Path hoặc dùng fat/nested executable JAR phù hợp.

### Fat JAR lỗi ServiceLoader hoặc framework auto-configuration

**Nguyên nhân:** resource trong META-INF/services hoặc metadata framework bị ghi đè khi merge.

**Cách xử lý:** cấu hình resource transformer/merge strategy; kiểm tra service descriptors trong archive cuối; chạy integration test với JAR đã đóng gói.

### Fat JAR gặp duplicate class hoặc NoSuchMethodError

**Nguyên nhân:** hai dependency chứa class trùng hoặc version không tương thích.

**Cách xử lý:** xem dependency tree; chọn version thống nhất; loại dependency không cần; dùng relocation có kiểm soát nếu cần cô lập namespace.

### WAR deploy lỗi do servlet API hoặc classloader

**Nguyên nhân:** đóng gói thư viện mà container đã cung cấp, hoặc dùng API version không tương thích server.

**Cách xử lý:** chuyển dependency container sang provided/providedRuntime; xác nhận Servlet/Jakarta EE version; kiểm tra WEB-INF/lib.

### WAR chạy local nhưng không deploy được lên server

**Nguyên nhân:** app phụ thuộc embedded container, descriptor hoặc API riêng của framework nhưng server không tương thích.

**Cách xử lý:** xác nhận deployment target; cấu hình WAR mode đúng; chạy integration test trên cùng loại/version container.

### EAR deploy nhưng module không được nhận diện

**Nguyên nhân:** module không được khai báo đúng, descriptor sai hoặc server không hỗ trợ version/spec mà package yêu cầu.

**Cách xử lý:** kiểm tra application.xml, cấu trúc EAR, module URI và phiên bản Jakarta EE/application server.

### Distribution thiếu file config hoặc launcher

**Nguyên nhân:** assembly descriptor/CopySpec chưa include file hoặc task tạo file chưa được khai báo là input.

**Cách xử lý:** kiểm tra archive listing; khai báo file/task output rõ ràng; chạy assembleDist/package rồi test từ thư mục đã giải nén.

### jpackage không tạo được installer

**Nguyên nhân:** build trên sai OS, thiếu tool native, runtime image không tương thích hoặc package format không được hỗ trợ.

**Cách xử lý:** build trên target OS; kiểm tra jpackage --help, toolchain và quyền ký/notarize; tạo application image trước để tách lỗi packaging khỏi lỗi app.

### jlink báo không tìm thấy module

**Nguyên nhân:** module path thiếu module hoặc ứng dụng chưa có module descriptor hợp lệ.

**Cách xử lý:** kiểm tra module-info.class, module path và module name; chạy java --list-modules; bổ sung module/dependency cần thiết.

### Native Image thiếu reflection/resource

**Nguyên nhân:** static analysis không nhận diện được truy cập động tại runtime.

**Cách xử lý:** thêm reachability metadata phù hợp, dùng tracing agent khi cần và test native executable với các đường chạy thực tế.

### Container image quá lớn

**Nguyên nhân:** image cuối chứa JDK/compiler, build cache, source tree hoặc file không cần runtime.

**Cách xử lý:** dùng multi-stage build; copy chỉ distribution cần chạy; chọn runtime base image phù hợp; kiểm tra layer và dependency.

### Đổi packaging nhưng consumer vẫn resolve artifact cũ

**Nguyên nhân:** tên artifact, classifier, version hoặc publication mapping không thay đổi như dự kiến.

**Cách xử lý:** kiểm tra output filename và publication metadata; xác nhận tọa độ trong repository; dùng version mới hoặc classifier riêng theo release policy.

## 18. Quy trình chọn và xác nhận packaging

1. Xác định consumer và deployment target.
2. Xác định runtime Java có sẵn hay phải bundle.
3. Xác định application/library và API/dependency contract.
4. Chọn JAR, WAR, EAR, distribution, container, runtime image hoặc native executable.
5. Chọn Maven packaging/plugin hoặc Gradle plugin phù hợp.
6. Cấu hình dependency, manifest, resource merge và launcher.
7. Build package sạch.
8. Kiểm tra archive contents và metadata.
9. Chạy artifact trong môi trường gần với production.
10. Xác minh checksum/signature/provenance theo release policy.
11. Publish đúng deliverable và ghi rõ cách cài/chạy.

Không cần tạo mọi định dạng cùng lúc. Có thể phát hành nhiều deliverable khi có nhiều nhóm consumer, nhưng mỗi deliverable cần có mục đích, version, test và release record rõ ràng.

## 19. Checklist trước khi phát hành

### Chọn đúng định dạng

- [ ] Đã xác định consumer và deployment platform.
- [ ] Đã phân biệt library JAR với application package.
- [ ] Đã xác nhận Java runtime được cài sẵn hay bundle.
- [ ] WAR/EAR chỉ được chọn khi target server hỗ trợ đúng specification.
- [ ] Container/native/installer phù hợp OS và architecture.

### Nội dung package

- [ ] Class, resource và manifest đúng.
- [ ] Main-Class hoặc launcher script đúng.
- [ ] Dependency đầy đủ và không bị trùng/xung đột.
- [ ] ServiceLoader/resource metadata được merge đúng.
- [ ] Config, license, NOTICE và tài liệu cần thiết có mặt.
- [ ] Không đóng gói secret, local config hoặc build cache.

### Runtime và vận hành

- [ ] Chạy được từ package đã giải nén/tải xuống.
- [ ] Runtime version tương thích.
- [ ] Config externalization và logging đúng.
- [ ] Có smoke/integration test trên môi trường đích.
- [ ] Native/installer đã test trên từng platform được hỗ trợ.

### Release

- [ ] Artifact identity/version rõ ràng.
- [ ] Checksum/signature/provenance được tạo theo policy.
- [ ] SBOM/license review được thực hiện nếu cần.
- [ ] Repository/registry đích đúng.
- [ ] Hướng dẫn cài đặt, chạy, nâng cấp và rollback được lưu.

## 20. Tài liệu tham khảo chính thức

- [Maven Build Lifecycle — Packaging](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — packaging type jar, war, ear, pom và lifecycle goal binding.
- [Maven Shade Plugin](https://maven.apache.org/components/plugins/maven-shade-plugin/) — tạo uber JAR, relocate dependency và transformer.
- [Maven Shade Plugin: Executable JAR](https://maven.apache.org/plugins/maven-shade-plugin/examples/executable-jar.html) — cấu hình Main-Class và executable uber JAR.
- [Maven WAR Plugin](https://maven.apache.org/plugins/maven-war-plugin/) — đóng gói web application archive.
- [Maven EAR Plugin](https://maven.apache.org/plugins/maven-ear-plugin/) — gom enterprise modules thành EAR.
- [Maven Assembly Plugin](https://maven.apache.org/plugins/maven-assembly-plugin/) — tạo ZIP/TAR distribution với dependency và file tùy chỉnh.
- [Gradle Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html) — main class, start scripts, installDist, distZip, distTar.
- [Gradle WAR Plugin Reference](https://docs.gradle.org/current/userguide/war_plugin.html) — WAR layout và dependency placement.
- [Gradle EAR Plugin](https://docs.gradle.org/current/userguide/ear_plugin.html) — EAR modules, shared libraries và deployment descriptor.
- [Gradle Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html) — library component và API/implementation separation.
- [Spring Boot Executable Archives — Gradle](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html) — bootJar, bootWar, nested dependencies và layered archives.
- [Spring Boot Executable Archives — Maven](https://docs.spring.io/spring-boot/maven-plugin/packaging.html) — repackage, executable JAR/WAR và archive layout.
- [Java Launcher — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — java -jar, Main-Class và classpath behavior.
- [jlink Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html) — tạo custom runtime image từ module graph.
- [jpackage Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html) — application image và native installer theo platform.
- [GraalVM Native Image](https://www.graalvm.org/latest/reference-manual/native-image/) — biên dịch Java thành native executable.
- [GraalVM Reachability Metadata](https://www.graalvm.org/jdk25/reference-manual/native-image/metadata/) — reflection, JNI, resource và metadata cho Native Image.
- [Docker Multi-stage Builds](https://docs.docker.com/get-started/docker-concepts/building-images/multi-stage-builds/) — tách build stage khỏi runtime image.

Chọn cách đóng gói bắt đầu từ consumer và môi trường chạy. Library thường cần JAR có metadata dependency; ứng dụng độc lập có thể dùng executable JAR hoặc ZIP/TAR distribution; web application dùng WAR khi triển khai trên servlet container; enterprise application dùng EAR khi application server yêu cầu; desktop app có thể dùng jpackage; container platform dùng OCI image; Native Image dành cho trường hợp cần native executable và chấp nhận các yêu cầu tương thích riêng. Hãy kiểm tra chính package cuối cùng trong môi trường mà consumer sẽ sử dụng.
