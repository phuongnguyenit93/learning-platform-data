# Chọn artifact output trong Java toolchain

**Artifact output** là sản phẩm mà build tạo ra để một bên khác sử dụng: thư viện JAR, ứng dụng chạy độc lập, WAR triển khai lên application server, gói phân phối ZIP/TAR, application image, native installer hoặc container image. Chọn đúng output là quyết định kiến trúc của toolchain vì nó ảnh hưởng tới cách chạy, dependency, runtime, bảo mật, cập nhật và môi trường triển khai.

Không có một định dạng duy nhất phù hợp cho mọi dự án Java. Một thư viện dùng làm dependency cần artifact khác với ứng dụng CLI, web application hoặc desktop application. Một dự án cũng có thể tạo nhiều output từ cùng source: JAR chính, sources JAR, Javadoc JAR, ZIP phân phối và installer theo từng hệ điều hành.

Bài này cung cấp cách chọn artifact theo deployment contract, phân biệt các dạng output, cấu hình Maven và Gradle, kiểm tra artifact thật và tổ chức pipeline phát hành có thể tái lập.

## 1. Bắt đầu từ nơi artifact sẽ được sử dụng

Trước khi chọn plugin hoặc packaging type, hãy xác định người nhận artifact và cách họ chạy nó.

Năm câu hỏi cần trả lời:

1. **Ai sử dụng?** Một ứng dụng Java khác, application server, người dùng desktop, người vận hành server hay package manager?
2. **Chạy ở đâu?** JVM có sẵn, container, máy không cài Java, application server hay môi trường native?
3. **Dependency được cung cấp thế nào?** Qua Maven/Gradle repository, thư mục lib, application server hay được bundle vào output?
4. **Cách triển khai là gì?** Copy JAR, chạy script, deploy WAR, cài installer hay pull container image?
5. **Cập nhật và rollback ra sao?** Thay file, deploy version mới, package manager upgrade hay thay container image?

Output phải đáp ứng đúng hợp đồng giữa bên build và bên triển khai. Ví dụ, một thư viện dùng trong nhiều ứng dụng thường cần JAR mỏng cùng metadata dependency. Một CLI phát hành cho người dùng cuối có thể cần ZIP/TAR chứa launcher script và dependency. Một ứng dụng desktop có thể cần application image hoặc native installer.

### Quyết định output theo consumer

| Consumer / môi trường | Output thường phù hợp | Cách sử dụng |
|---|---|---|
| Ứng dụng Java khác | Library JAR | Khai báo dependency trong Maven/Gradle |
| CLI chạy trên JVM có sẵn | Executable JAR hoặc distribution ZIP | java -jar hoặc launcher script |
| CLI cần bundle dependency | Fat/shaded JAR hoặc ZIP/TAR | Chạy bằng launcher với runtime classpath |
| Servlet container | WAR | Deploy vào container tương thích |
| Jakarta EE application server | EAR hoặc WAR theo server contract | Deploy theo cấu trúc enterprise |
| Java module consumer | Modular JAR | Dùng module path và JPMS |
| Desktop app | Application image hoặc native installer | Launcher riêng, runtime có thể được bundle |
| Server chạy trong container | Container image | Deploy bằng container platform |
| Môi trường không muốn phụ thuộc JVM | Native executable | Native-image toolchain riêng, ví dụ GraalVM |
| Người dùng cần source/API docs | Sources JAR và Javadoc JAR | Tài liệu và debugging, không phải runtime output |

Đây là các lựa chọn thường gặp, không phải quy tắc bắt buộc. Hãy kiểm tra framework, runtime và nền tảng mục tiêu trước khi chốt.

## 2. Các loại output Java thường gặp

### Compiled classes directory

Sau bước compile, class files thường nằm trong:

~~~text
target/classes/                 # Maven
build/classes/java/main/        # Gradle
~~~

Đây là output trung gian để test, đóng gói JAR/WAR hoặc chạy trong build. Thông thường không phát hành riêng thư mục này vì thiếu metadata, dependency declaration và cấu trúc phân phối hoàn chỉnh.

### Library JAR

Library JAR chứa class files, resource và manifest của một thư viện. Consumer khai báo dependency theo coordinate:

~~~text
com.acme.platform:customer-client:2.4.1
~~~

Library JAR thường không cần Main-Class. Dependency của thư viện được mô tả trong POM hoặc Gradle Module Metadata, không nên nhúng tất cả dependency vào một JAR chỉ để người dùng dễ copy.

Nên tạo thêm sources JAR và Javadoc JAR khi publish thư viện để IDE và developer có thể xem source/API docs.

### Executable JAR

Executable JAR có Main-Class trong manifest:

~~~text
Main-Class: com.acme.cli.Main
~~~

Có thể chạy:

~~~bash
java -jar app.jar
~~~

Một executable JAR mặc định vẫn có thể là **thin JAR**: chỉ chứa application code. Các dependency khác phải được cung cấp qua manifest Class-Path, launcher script hoặc cơ chế packaging của framework.

Đừng suy luận rằng có Main-Class nghĩa là JAR đã chứa mọi dependency. Nếu dependency không có trong runtime classpath, ứng dụng có thể lỗi NoClassDefFoundError.

### Fat JAR / shaded JAR

Fat JAR hoặc shaded JAR đóng gói application code cùng dependency classes/resources vào một archive. Đây là cách thuận tiện cho CLI hoặc service nhỏ cần một file JAR dễ chạy.

Ưu điểm:

- Phân phối một file.
- Không cần người dùng tự dựng thư mục lib.
- Dễ chạy bằng java -jar.
- Phù hợp một số môi trường triển khai đơn giản.

Nhược điểm:

- JAR lớn hơn.
- Có thể trùng resource hoặc class.
- Cần merge META-INF/services đúng cách.
- License và notice của dependency phải được xử lý.
- Chữ ký của JAR dependency thường không còn hợp lệ sau khi shade.
- Không tự động bảo đảm tương thích JPMS hoặc multi-release JAR.
- Dependency bị gộp khiến việc thay riêng một thư viện khó hơn.

Dùng shade/uber JAR khi deployment contract thực sự cần một archive tự chứa. Với service lớn hoặc nhiều dependency, distribution ZIP/TAR hay container image có thể dễ quản lý hơn.

### WAR

WAR (Web Application Archive) đóng gói web application để deploy vào servlet container tương thích. Thường chứa:

~~~text
WEB-INF/
├── classes/
├── lib/
└── web.xml  # nếu ứng dụng dùng deployment descriptor
~~~

WAR phù hợp khi tổ chức vận hành application server/container và quản lý vòng đời web app theo nền tảng đó.

Cần kiểm tra:

- Phiên bản Servlet/Jakarta Servlet API.
- Namespace javax.* hay jakarta.* theo nền tảng.
- Dependency nào được container cung cấp.
- Cấu hình context, security và resource.
- Application server có hỗ trợ đúng framework/runtime hay không.

Không đóng gói servlet API như dependency runtime thông thường nếu container phải cung cấp API đó; Maven thường khai báo scope provided.

### EAR

EAR (Enterprise Archive) có thể gom nhiều module enterprise, chẳng hạn WAR, EJB JAR và library. Nó phù hợp với application server hỗ trợ Jakarta EE enterprise packaging. Không dùng EAR chỉ vì dự án có nhiều JAR; nếu chỉ cần phát hành nhiều file độc lập, ZIP/TAR hoặc multi-module repository thường đơn giản hơn.

### Modular JAR

Modular JAR chứa module-info.class và được sử dụng trên module path. Output này phù hợp khi muốn công khai API qua exports, khai báo dependency qua requires và kiểm soát encapsulation.

Một JAR có module-info.class vẫn có thể được chạy như JAR trên classpath, nhưng khi đặt trên classpath thì module descriptor không được áp dụng như trên module path. Hãy xác định consumer sẽ dùng classpath hay JPMS.

### Application image và native installer

Application image có launcher, application files và runtime image. Native installer như MSI, EXE, DMG, PKG, DEB hoặc RPM cung cấp trải nghiệm cài đặt theo hệ điều hành. jpackage có thể tạo các dạng output này.

Application image không phải native executable được biên dịch từ Java thành machine code. Nó vẫn chạy bytecode trên Java runtime được bundle.

### Runtime image

jlink tạo runtime image chứa tập module JDK cần thiết. Runtime image có thể được dùng để chạy ứng dụng hoặc làm đầu vào cho jpackage qua --runtime-image. Nó không tự chứa toàn bộ application code và launcher trừ khi được đóng gói thêm.

### Distribution ZIP/TAR

Distribution archive chứa nhiều thành phần:

~~~text
acme-cli/
├── bin/
│   ├── acme
│   └── acme.bat
├── lib/
│   ├── acme-cli.jar
│   └── dependency-*.jar
├── conf/
├── README.txt
└── LICENSE
~~~

Đây là lựa chọn tốt khi cần launcher script, cấu hình mẫu, nhiều JAR, native library và tài liệu. ZIP/TAR cũng có thể chứa application image, nhưng cần giữ đúng cấu trúc và quyền thực thi khi giải nén.

### Sources, Javadoc và test artifacts

Các artifact bổ trợ thường gặp:

- sources JAR: source code tương ứng với binary.
- Javadoc JAR: API documentation.
- tests JAR: test classes/resources nếu dự án có chủ đích publish test fixtures.
- SBOM, checksum, signature và provenance: metadata phát hành.

Các artifact này không thay thế runtime JAR. Chỉ publish test JAR khi consumer thực sự cần test fixtures hoặc shared test utilities.

## 3. Phân biệt fat JAR, distribution và application image

Ba dạng này thường bị nhầm lẫn:

| Tiêu chí | Fat JAR | Distribution ZIP/TAR | Application image |
|---|---|---|---|
| Application code | Có | Có | Có |
| Dependency | Gộp vào JAR | Các JAR riêng trong lib | Các file trong app image |
| Launcher | Main-Class hoặc script bên ngoài | Script đi kèm | Native launcher |
| Java runtime | Thường không bundle | Có thể không bundle | Thường bundle |
| Nhiều file cấu hình | Khó quản lý hơn | Thuận tiện | Có thể chứa trong image |
| OS-specific | Thường ít phụ thuộc OS nếu chỉ dùng Java | Có thể có script riêng | Có |
| Dùng cho | Một-file Java app | CLI/server distribution | Desktop hoặc app tự chứa runtime |

Chọn fat JAR nếu một file JAR là hợp đồng phân phối mong muốn. Chọn distribution khi cần quản lý nhiều file và script. Chọn application image khi muốn launcher native và runtime được bundle.

## 4. Những tiêu chí kỹ thuật khi chọn output

### Runtime availability

Nếu môi trường đích đã quản lý JDK/JRE, library JAR hoặc executable JAR mỏng có thể đủ. Nếu người dùng không cài Java, cân nhắc application image/native installer hoặc native image.

### Dependency model

- Library: dependency metadata rõ ràng.
- Thin executable JAR: dependency được cung cấp qua runtime classpath.
- Fat JAR: dependency được shade/merge.
- WAR/EAR: container có thể cung cấp một số API/runtime.
- Container image: dependency và runtime nằm trong image.

Không bundle dependency hai lần nếu application server hoặc container đã cung cấp chúng.

### Portability

JAR bytecode thuần Java thường có thể chạy trên nhiều OS tương thích. Native library, launcher, installer và native image phụ thuộc OS/architecture. Distribution ZIP có thể portable nếu chỉ chứa Java code, nhưng script và file permission có thể cần biến thể theo OS.

### Module compatibility

Nếu consumer dùng JPMS, kiểm tra module-info, automatic module name, split package và service loading. Shade nhiều module thành một JAR có thể làm mất module boundaries hoặc khiến descriptor không còn phản ánh nội dung.

### Startup, memory và size

Fat JAR không mặc nhiên khởi động nhanh hơn library JAR. Application image thường lớn hơn vì chứa runtime. Native image có thể giảm thời gian khởi động trong một số workload nhưng có trade-off về build time, reflection/configuration, compatibility và runtime behavior.

Đo trên workload thực tế trước khi chọn vì startup, memory và size phụ thuộc ứng dụng.

### Operations và update strategy

Hãy chọn output phù hợp cách tổ chức vận hành:

- Artifact repository: JAR/WAR/EAR với version immutable.
- Server deploy: WAR hoặc executable JAR.
- Desktop fleet: installer có identity và upgrade policy.
- Kubernetes: container image tag/digest.
- Linux workstation: DEB/RPM qua package repository.

### Security and compliance

Kiểm tra dependency licenses, SBOM, signing, checksum, vulnerability scanning và provenance. Với fat JAR, cần merge license/notice files và xử lý chữ ký dependency. Với installer, ký artifact theo yêu cầu nền tảng.

## 5. Chọn output theo loại dự án

### Library dùng bởi nhiều ứng dụng

Khuyến nghị:

- Main library JAR.
- POM/Gradle Module Metadata.
- Sources JAR.
- Javadoc JAR.
- SBOM/checksum/signature theo release policy.

Không cần Main-Class. Không shade dependency mặc định vì consumer cần khả năng chọn version và giải quyết dependency riêng.

### Command-line tool

Có ba lựa chọn phổ biến:

1. Executable JAR nếu người dùng có Java và dependency đơn giản.
2. Distribution ZIP/TAR nếu cần scripts, lib/, conf/ và docs.
3. Native installer/application image nếu muốn trải nghiệm cài đặt và runtime riêng.

Chọn theo đối tượng người dùng và môi trường triển khai. CLI nội bộ có thể chỉ cần distribution archive; CLI phát hành rộng có thể cần installer.

### Web service

Có thể phát hành:

- Executable JAR cho framework có embedded server.
- WAR nếu deployment target là servlet container.
- Container image nếu platform vận hành bằng container.

Không chọn WAR hay executable JAR theo thói quen. Hãy theo deployment contract của platform, cách cấu hình và cách quản lý lifecycle.

### Desktop application

Thường cần:

- Application image để smoke test.
- Native installer để cài đặt.
- Runtime bundle nếu không muốn phụ thuộc Java cài sẵn.
- Code signing/notarization theo nền tảng.

Build riêng trên Windows, macOS và Linux; kiểm tra từng architecture mục tiêu.

### Enterprise application

Nếu application server yêu cầu EAR, hãy tạo EAR theo module structure của server. Nếu không, nhiều JAR/WAR độc lập được triển khai bằng pipeline riêng có thể đơn giản và dễ scale hơn.

### Native executable

Nếu yêu cầu là binary native không cần JVM runtime riêng, cân nhắc GraalVM Native Image hoặc công nghệ tương đương. Đây là toolchain riêng, cần kiểm tra reflection, resource configuration, JNI, dynamic class loading và compatibility. Không gọi application image của jpackage là native image.

## 6. Maven: chọn packaging type và plugin

Maven <packaging> xác định lifecycle/package type cơ bản. Các loại phổ biến gồm jar, war, ear và pom. Các plugin bổ sung có thể tạo thêm output như shaded JAR, ZIP/TAR hoặc installer input.

### Library JAR

POM tối thiểu:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.acme</groupId>
    <artifactId>customer-client</artifactId>
    <version>2.4.1</version>
    <packaging>jar</packaging>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
</project>
~~~

Build:

~~~bash
mvn clean package
~~~

Output:

~~~text
target/customer-client-2.4.1.jar
~~~

### Executable JAR

Thêm Maven JAR Plugin để ghi Main-Class:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.4.2</version>
    <configuration>
        <archive>
            <manifest>
                <mainClass>com.acme.cli.Main</mainClass>
                <addDefaultImplementationEntries>true</addDefaultImplementationEntries>
            </manifest>
        </archive>
    </configuration>
</plugin>
~~~

Sau build:

~~~bash
java -jar target/customer-client-2.4.1.jar
~~~

Lệnh chỉ thành công nếu mọi dependency runtime đều có mặt. Main-Class không tự đóng gói dependency.

### Sources và Javadoc JAR

Có thể dùng Maven Source Plugin và Javadoc Plugin để attach sources/Javadoc artifacts trong lifecycle release:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-source-plugin</artifactId>
    <version>3.3.1</version>
    <executions>
        <execution>
            <id>attach-sources</id>
            <goals><goal>jar-no-fork</goal></goals>
        </execution>
    </executions>
</plugin>
~~~

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <version>3.11.2</version>
    <executions>
        <execution>
            <id>attach-javadocs</id>
            <goals><goal>jar</goal></goals>
        </execution>
    </executions>
</plugin>
~~~

Pin plugin versions và kiểm tra Javadoc generation trong CI. Javadoc lỗi có thể phản ánh API docs không hoàn chỉnh hoặc toolchain incompatibility.

### WAR

Đặt:

~~~xml
<packaging>war</packaging>
~~~

và cấu hình Maven WAR Plugin. Với Servlet API do container cung cấp, khai báo dependency scope provided:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>6.1.0</version>
    <scope>provided</scope>
</dependency>
~~~

Chọn đúng version theo servlet container mục tiêu. Không lấy ví dụ version ở đây làm chuẩn cho mọi application server.

### Fat JAR bằng Maven Shade Plugin

Shade Plugin tạo JAR đã gộp dependency. Cấu hình Main-Class và service resource transformer nếu application sử dụng ServiceLoader:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.0</version>
    <executions>
        <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
                <transformers>
                    <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                    <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                        <mainClass>com.acme.cli.Main</mainClass>
                    </transformer>
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Kiểm tra thêm duplicate resources, license notices, signatures, multi-release entries và module descriptor. Không bật shade mà không có lý do triển khai rõ ràng.

### Distribution ZIP/TAR

Maven Assembly Plugin hoặc Maven Distribution Plugin có thể tạo ZIP/TAR chứa JAR, lib, script và docs. Định nghĩa descriptor để quy định chính xác file nào được đưa vào archive.

Ví dụ nội dung distribution:

~~~text
acme-cli/
├── bin/
├── lib/
├── conf/
└── README.md
~~~

Dùng mvn package hoặc goal đã gắn vào lifecycle để tạo archive. Kiểm tra archive list và chạy launcher sau khi giải nén vào thư mục sạch.

## 7. Gradle: chọn plugin và task

Gradle Java Plugin tạo class directories và JAR. Application Plugin bổ sung cách chạy application và tạo distribution. War Plugin tạo WAR. Các plugin ngoài có thể tạo fat JAR hoặc native package.

### Library JAR

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.acme'
version = '2.4.1'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Build:

~~~bash
./gradlew clean jar
~~~

Output thường nằm trong:

~~~text
build/libs/<project-name>-2.4.1.jar
~~~

### Executable application và distribution

~~~groovy
plugins {
    id 'application'
}

group = 'com.acme'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'com.acme.cli.Main'
}
~~~

Các task hữu ích:

~~~bash
./gradlew run
./gradlew jar
./gradlew installDist
./gradlew distZip
./gradlew distTar
~~~

- run: chạy application trong môi trường Gradle.
- jar: tạo JAR chính.
- installDist: tạo thư mục distribution có scripts và dependency.
- distZip: tạo ZIP distribution.
- distTar: tạo TAR distribution.

Application Plugin phù hợp khi cần phân phối nhiều file thay vì chỉ một JAR.

### WAR

~~~groovy
plugins {
    id 'war'
}

group = 'com.acme'
version = '2.4.1'
~~~

Build:

~~~bash
./gradlew war
~~~

Output mặc định ở build/libs. Kiểm tra dependency scope và target container compatibility.

### Thay đổi tên archive

~~~groovy
tasks.named('jar', Jar) {
    archiveBaseName = 'customer-client'
    archiveVersion = project.version.toString()
    archiveClassifier = 'desktop'
}
~~~

Tên output:

~~~text
build/libs/customer-client-2.4.1-desktop.jar
~~~

Classifier nên biểu diễn biến thể có ý nghĩa, chẳng hạn sources, javadoc, linux-x64 hoặc tests; đừng dùng classifier để che giấu nhiều artifact không tương thích dưới cùng một tên.

### Fat JAR trên Gradle

Gradle core Java Plugin không tự cung cấp một quy tắc universal để merge mọi dependency thành fat JAR. Dùng plugin phù hợp như Shadow Plugin và pin version; cấu hình merge service files, manifest, license và duplicate policy. Với ứng dụng cần nhiều file, Application Plugin distribution thường minh bạch hơn.

## 8. jlink, jpackage và container image

### jlink runtime image

Dùng khi muốn bundle tập module JDK tối thiểu cần thiết:

~~~bash
jlink --add-modules java.base,java.logging,java.sql --strip-debug --no-header-files --no-man-pages --output build/runtime
~~~

Danh sách module ở đây chỉ là ví dụ; phải xác định từ dependency thật của ứng dụng. Với JPMS application, có thể phân tích bằng jdeps và kiểm tra module graph.

### jpackage application image

~~~bash
jpackage --type app-image --input input --name AcmeDesktop --main-jar app.jar --main-class com.acme.desktop.Main --dest dist
~~~

Application image thường chứa launcher, application files và runtime. Chạy thử image trước khi tạo native installer.

### Native installer

Trên Windows, macOS và Linux, jpackage có thể tạo các package phù hợp như MSI/EXE, DMG/PKG, DEB/RPM. Các package cần được build trên nền tảng mục tiêu và có toolchain native tương ứng.

### Container image

Nếu ứng dụng chạy trong Kubernetes hoặc container platform, output cuối có thể là OCI container image. Build container image thường dùng Dockerfile/Buildpacks/Jib hoặc pipeline tương đương. Chọn base image, JRE/JDK, OS packages, user permissions, CA certificates và architecture theo runtime contract.

Không nhầm container image với JAR: JAR là một phần trong container filesystem; image còn bao gồm runtime, OS layers, entrypoint và metadata.

## 9. Cấu trúc output và quy tắc đặt tên

Một project có thể tạo nhiều deliverables:

~~~text
release/
├── maven/
│   ├── customer-client-2.4.1.jar
│   ├── customer-client-2.4.1-sources.jar
│   └── customer-client-2.4.1-javadoc.jar
├── distribution/
│   └── acme-cli-2.4.1.zip
├── desktop/
│   ├── AcmeDesktop-2.4.1-windows-x64.msi
│   ├── AcmeDesktop-2.4.1-macos-aarch64.dmg
│   └── AcmeDesktop-2.4.1-linux-x64.deb
└── checksums/
~~~

Quy tắc đặt tên nên thể hiện:

- Product/artifact name.
- Version.
- Classifier hoặc distribution type.
- OS và architecture khi output phụ thuộc nền tảng.

Với Maven repository, dùng GAV và classifier thay vì tự đặt tên tùy tiện. Với release download, tên file cần dễ nhận diện nhưng vẫn phải ánh xạ được về coordinate/version.

### Không publish output trung gian

Không publish các thư mục target/classes, build/classes, temporary staging directories hoặc file intermediate do plugin tạo, trừ khi có use case rõ ràng. Publish artifact cuối đã được test, ký và tạo checksum.

## 10. Kiểm tra artifact trước khi phát hành

Build thành công không chứng minh output đúng deployment contract.

### Kiểm tra JAR

Liệt kê nội dung:

~~~bash
jar --list --file target/app.jar
~~~

Kiểm tra manifest:

~~~bash
jar --extract --file target/app.jar META-INF/MANIFEST.MF
~~~

Xác nhận Main-Class nếu cần chạy java -jar, Implementation-Version, service descriptors và resource.

### Kiểm tra modular JAR

~~~bash
jar --describe-module --file target/library.jar
~~~

Xác nhận module name, requires, exports và packages.

### Kiểm tra executable JAR

~~~bash
java -jar target/app.jar --help
~~~

Chạy bằng môi trường runtime mục tiêu, không chỉ bằng classpath của IDE. Nếu app cần dependency ngoài JAR, kiểm tra launcher classpath hoặc fat JAR.

### Kiểm tra WAR

Liệt kê WAR và deploy lên đúng servlet container/version. Kiểm tra context startup, endpoints, security, static resources, database connections và shutdown behavior.

### Kiểm tra distribution

Giải nén vào thư mục sạch:

~~~bash
unzip -l dist/acme-cli-1.0.0.zip
~~~

Sau đó chạy launcher script từ thư mục giải nén. Không chạy từ project root vì working directory và relative paths có thể che giấu lỗi đóng gói.

### Kiểm tra application image/installer

Chạy application image trên máy không có JDK riêng. Với native installer, kiểm tra install, launch, upgrade và uninstall trên VM sạch của từng OS/architecture.

### Kiểm tra checksum và signature

Windows PowerShell:

~~~powershell
Get-FileHash .\dist\app.jar -Algorithm SHA256
~~~

Linux/macOS:

~~~bash
sha256sum dist/app.jar
~~~

Kiểm tra chữ ký theo công cụ của nền tảng. Checksum cần được đối chiếu với giá trị tham chiếu đáng tin cậy; hash tự nó không xác thực người phát hành.

## 11. Reproducibility và artifact provenance

Hai lần build cùng source nên tạo output có thể so sánh và truy vết. Với archive, kiểm soát:

- Entry order.
- Timestamp.
- Manifest metadata.
- File permissions.
- Line endings.
- Compiler/JDK version.
- Maven/Gradle và plugin versions.
- Dependency versions.
- Generated files.
- Absolute paths, hostname và build time.

Maven có thể dùng project.build.outputTimestamp cho reproducible archives. Gradle archive tasks có reproducibleFileOrder và preserveFileTimestamps.

Ghi lại metadata phát hành:

~~~text
Artifact: customer-client-2.4.1.jar
Version: 2.4.1
Git revision: abc1234
JDK: 24.0.2
Build tool: Maven 3.9.12
OS/architecture: windows-x64
SHA-256: <computed value>
~~~

Giá trị SHA-256 phải được tính từ file cuối cùng; không hard-code checksum giả định vào source.

### Version và classifier

Version xác định bản artifact; classifier phân biệt biến thể. Ví dụ customer-client-2.4.1-sources.jar và customer-client-2.4.1.jar thuộc cùng version nhưng có nội dung và mục đích khác nhau.

Với native output, thêm OS/architecture vào tên file và release metadata. Không để artifact Windows ghi đè artifact Linux chỉ vì chúng cùng version.

## 12. Các anti-pattern khi chọn output

### Chọn fat JAR cho mọi loại dự án

Fat JAR tiện cho ứng dụng đơn giản nhưng không phải lựa chọn mặc định cho library, WAR hoặc mọi service. Nó làm dependency khó thay thế và có thể gây resource/signature conflicts.

### Dùng library JAR như executable JAR

JAR thư viện không nhất thiết có Main-Class. Consumer nên khai báo dependency; không nên kỳ vọng mọi JAR đều chạy bằng java -jar.

### Đưa dependency container vào WAR

Nếu application server cung cấp Servlet/Jakarta APIs, đóng gói thêm phiên bản khác có thể gây classloader conflict. Dùng provided scope theo contract của container.

### Chọn application image nhưng tưởng đó là native machine-code binary

jpackage bundle runtime và launcher; bytecode vẫn chạy trên JVM. Nếu yêu cầu là native executable, đánh giá Native Image riêng.

### Build một installer trên OS khác

Native installer phụ thuộc OS và toolchain. Tạo output trên runner phù hợp, không copy package từ nền tảng khác rồi đổi extension.

### Dùng một output cho cả library và application

Một project có thể tạo library JAR và executable distribution riêng. Đừng ép một archive phải vừa là dependency ổn định vừa là bundle triển khai có mọi runtime dependency.

### Publish artifact trước khi test

Artifact phải được smoke test và kiểm tra metadata trước khi publish. Build exit code 0 không xác nhận application khởi chạy hoặc deploy đúng.

### Dùng tên file làm nguồn version duy nhất

Tên file có thể bị rename. Giữ version trong build metadata, manifest, repository coordinates và release provenance.

## 13. Quy trình chọn output và triển khai trong CI

Một pipeline gọn có thể tổ chức như sau:

~~~text
Source + dependency lock
        |
        v
Compile / unit tests
        |
        v
Build primary artifact
        |
        +----> Library JAR + sources/Javadoc
        |
        +----> Executable JAR / WAR / EAR
        |
        +----> Distribution ZIP/TAR
        |
        +----> Application image / installer
        |
        +----> Container image
        |
        v
Smoke test each output
        |
        v
Verify metadata / dependency / licenses
        |
        v
Sign + checksum + provenance
        |
        v
Publish immutable release
~~~

Không phải dự án nào cũng cần tất cả output. Chỉ tạo deliverable đã được deployment contract yêu cầu.

### Build matrix

Nếu output native, dùng runner theo OS/architecture:

| Runner | Output |
|---|---|
| Windows x64 | MSI/EXE, Windows app image |
| macOS arm64 | DMG/PKG, macOS app image |
| Linux x64 | DEB/RPM, Linux app image |
| Linux container runner | OCI image theo target architecture |

Mỗi runner cần JDK, build tool, native packaging tools và signing identity tương ứng.

### Release gates

Trước khi publish:

1. Version và Git tag khớp.
2. Dependency tree được kiểm tra.
3. Artifact có đúng cấu trúc và metadata.
4. Smoke test thành công từ chính output đã đóng gói.
5. OS/architecture tương thích.
6. License/SBOM và security scan đạt policy.
7. Checksum và chữ ký đã xác minh.
8. Artifact được lưu bất biến.

## 14. Lab Java 17+: tạo executable JAR bằng Maven và distribution bằng Gradle

Chương trình mẫu Main.java:

~~~java
package com.acme.output;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Artifact output demo");
        System.out.println("Mode="
                + (args.length == 0 ? "default" : args[0]));
    }
}
~~~

### Maven executable JAR

POM:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.acme</groupId>
    <artifactId>output-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>com.acme.output.Main</mainClass>
                            <addDefaultImplementationEntries>true</addDefaultImplementationEntries>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Build:

~~~bash
mvn clean package
~~~

Output:

~~~text
target/output-demo-1.0.0.jar
~~~

Chạy:

~~~bash
java -jar target/output-demo-1.0.0.jar cli
~~~

Stdout chính xác:

~~~text
Artifact output demo
Mode=cli
~~~

Đây là executable JAR không có dependency bên ngoài. Nếu thêm dependency, hãy chọn thin JAR với launcher classpath hoặc cấu hình shade plugin có kiểm soát.

### Gradle distribution

File settings.gradle:

~~~groovy
rootProject.name = 'output-demo'
~~~

File build.gradle:

~~~groovy
plugins {
    id 'application'
}

group = 'com.acme'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'com.acme.output.Main'
}
~~~

Đặt Main.java trong src/main/java/com/acme/output/.

Chạy:

~~~bash
./gradlew clean run distZip
~~~

Output chính:

~~~text
build/libs/output-demo-1.0.0.jar
build/distributions/output-demo-1.0.0.zip
~~~

Chạy từ Gradle:

~~~text
Artifact output demo
Mode=default
~~~

Giải nén ZIP vào thư mục sạch rồi chạy script trong bin/ để xác minh distribution không phụ thuộc working directory của project.

## 15. Checklist chọn artifact output

- Consumer và deployment environment đã được xác định.
- Đã chọn JAR, WAR, EAR, distribution, app image, installer hay container image theo deployment contract.
- Library JAR có dependency metadata phù hợp.
- Executable JAR có Main-Class nếu dùng java -jar.
- Thin JAR có runtime dependency classpath rõ ràng.
- Fat JAR xử lý service files, duplicate resources, license và signatures.
- WAR/EAR tương thích container/application server.
- Modular JAR có module name, requires và exports đúng.
- Distribution có launcher scripts, lib, conf và docs cần thiết.
- Application image chứa runtime tương thích.
- Installer được build trên OS/architecture mục tiêu.
- Native image được phân biệt với jpackage application image.
- Sources/Javadoc/test artifacts chỉ được publish khi có nhu cầu.
- Tên file, version và classifier nhất quán.
- Artifact được kiểm tra bằng cách chạy/deploy chính output cuối.
- Checksum, signature, SBOM và provenance được lưu.
- Reproducibility và immutable release policy được áp dụng.

## 16. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Artifact output | Sản phẩm build được phân phối hoặc triển khai |
| Library JAR | JAR làm dependency cho ứng dụng khác |
| Executable JAR | JAR có Main-Class để chạy bằng java -jar |
| Thin JAR | JAR không gộp toàn bộ dependency |
| Fat/Shaded JAR | JAR gộp application code và dependency |
| WAR | Web Application Archive |
| EAR | Enterprise Archive |
| Modular JAR | JAR có module descriptor |
| Distribution archive | ZIP/TAR chứa app, lib, scripts và config |
| Application image | Launcher, application files và runtime image |
| Runtime image | Java runtime tùy chỉnh từ jlink |
| Native installer | Package cài đặt theo OS |
| Native image | Binary machine-code tạo bởi native-image toolchain |
| Container image | Image chứa filesystem, runtime, application và entrypoint |
| Classifier | Nhãn phân biệt biến thể artifact |
| Main-Class | Manifest attribute chỉ entry point |
| SBOM | Danh sách thành phần phần mềm |
| Provenance | Thông tin source và quy trình tạo artifact |
| Immutable release | Artifact phát hành không bị thay thế |

Chọn artifact output bằng cách bắt đầu từ cách consumer sẽ triển khai và vận hành ứng dụng. Library thường cần JAR cùng dependency metadata; ứng dụng có thể cần executable JAR hoặc distribution; web app có thể cần WAR/EAR; desktop app cần application image/installer; container platform cần OCI image. Sau khi chọn, kiểm tra chính artifact cuối trong môi trường gần production, đồng bộ version/metadata, tạo checksum và giữ release bất biến.

## Tài liệu tham khảo

- Apache Maven — POM Reference and Packaging: https://maven.apache.org/pom.html
- Apache Maven — Maven JAR Plugin: https://maven.apache.org/plugins/maven-jar-plugin/
- Apache Maven — Maven WAR Plugin: https://maven.apache.org/plugins/maven-war-plugin/
- Apache Maven — Maven Shade Plugin: https://maven.apache.org/plugins/maven-shade-plugin/
- Apache Maven — Maven Assembly Plugin: https://maven.apache.org/plugins/maven-assembly-plugin/
- Gradle — Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle — Application Plugin: https://docs.gradle.org/current/userguide/application_plugin.html
- Gradle — War Plugin: https://docs.gradle.org/current/userguide/war_plugin.html
- Oracle JDK 24 — jar Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html
- Oracle JDK 24 — jlink Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html
- Oracle JDK 24 — jpackage Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jpackage.html
- Eclipse Adoptium — Java Packaging and Runtime Images: https://adoptium.net/