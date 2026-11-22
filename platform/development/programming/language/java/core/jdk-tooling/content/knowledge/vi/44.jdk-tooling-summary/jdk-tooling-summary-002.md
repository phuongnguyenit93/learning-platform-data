# Luồng từ source đến artifact trong Java

Một chương trình Java đi từ mã nguồn đến artifact qua nhiều bước: chuẩn bị source và resource, biên dịch thành bytecode, chạy kiểm thử, đóng gói, kiểm tra nội dung artifact rồi phân phối cho môi trường chạy. Mỗi bước tạo ra một loại đầu ra và có thể thất bại vì nguyên nhân khác nhau.

Hiểu luồng này giúp trả lời những câu hỏi thực tế: file .java biến thành .class ở đâu, resource được đưa vào JAR lúc nào, dependency có nằm trong JAR không, vì sao build thành công nhưng chạy bằng java -jar lại lỗi, và làm thế nào xác nhận file đã phát hành đúng với file đã kiểm thử.

## 1. Toàn cảnh pipeline

Luồng thông thường của một ứng dụng Java:

~~~text
Source + Resources + Generated Sources + Dependencies
                       |
                       v
             Compile production code
                       |
                       v
          Class files (.class / bytecode)
                       |
          Process and copy resources
                       |
                       v
               Production classes
                       |
             Compile test sources
                       |
                       v
              Run unit/integration tests
                       |
                       v
            Package JAR / WAR / other
                       |
                       v
           Verify contents and metadata
                       |
                       v
         Sign / checksum / publish artifact
                       |
                       v
           Deploy and run on a JVM
~~~

Mỗi giai đoạn có mục tiêu riêng:

- **Source:** mã Java, file cấu hình, resource, generated source và build configuration.
- **Compile:** chuyển source thành class file, kiểm tra kiểu, module và dependency.
- **Test:** kiểm tra hành vi của code đã biên dịch.
- **Package:** gom class, resource và metadata thành JAR hoặc WAR.
- **Verify:** xác nhận artifact chứa đúng file, đúng version và tương thích runtime.
- **Publish:** lưu artifact ở repository hoặc artifact store.
- **Deploy:** đưa artifact đã kiểm thử đến môi trường chạy.

Không phải dự án nào cũng cần mọi giai đoạn. Ứng dụng nhỏ có thể dùng javac và jar trực tiếp; dự án lớn thường dùng Gradle hoặc Maven để quản lý task, dependency và lifecycle.

## 2. Những đầu vào tạo nên artifact

Artifact không chỉ được quyết định bởi file .java. Các đầu vào quan trọng gồm:

| Đầu vào | Ví dụ | Vai trò |
|---|---|---|
| Java source | src/main/java | Mã được compiler biên dịch |
| Resources | src/main/resources | Properties, XML, JSON, template, ảnh |
| Generated source | Annotation processor, code generator | Source được tạo trong quá trình build |
| Dependencies | JAR, modular JAR | API và implementation từ thư viện khác |
| Build configuration | build.gradle, pom.xml | Quy định compiler, resource, test, package |
| JDK/toolchain | javac, jar, javadoc | Quyết định compiler và tool được dùng |
| Build properties | Version, release, flags | Thay đổi metadata và bytecode output |
| Environment | OS, locale, timezone, variables | Có thể ảnh hưởng resource filtering và tính tái lập |

Một artifact có thể khác dù source không đổi nếu dependency version, JDK, compiler flags, generated source hoặc build configuration thay đổi. Khi điều tra sự khác biệt, hãy lưu lại các đầu vào này cùng revision của source.

### 2.1. Cấu trúc source thông dụng

Một project Java theo quy ước Gradle/Maven thường có dạng:

~~~text
project/
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/app/Main.java
│   │   └── resources/
│   │       └── app.properties
│   └── test/
│       ├── java/
│       │   └── com/example/app/MainTest.java
│       └── resources/
│           └── test-data.json
├── build.gradle   # hoặc pom.xml
└── README.md
~~~

- src/main/java chứa production source.
- src/main/resources chứa resource được đưa vào production artifact.
- src/test/java chứa test source.
- src/test/resources chứa resource chỉ phục vụ test.

Tên thư mục không phải yêu cầu của javac. Đây là quy ước được build tool hiểu tự động. Nếu gọi javac trực tiếp, bạn phải chỉ rõ source file, output directory và dependency path.

## 3. Từ Java source đến bytecode

Compiler javac đọc source, phân tích cú pháp và kiểu, kiểm tra access/dependency, rồi tạo class file. Class file chứa bytecode cho JVM, constant pool, thông tin method/field, attribute và metadata cần thiết.

Ví dụ:

~~~java
package com.example.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
~~~

Biên dịch bằng JDK 17:

~~~bash
mkdir -p build/classes
javac --release 17 -encoding UTF-8 -d build/classes src/main/java/com/example/app/Main.java
~~~

Kết quả:

~~~text
build/
└── classes/
    └── com/
        └── example/
            └── app/
                └── Main.class
~~~

Các option có ý nghĩa:

- **--release 17:** biên dịch theo ngôn ngữ, class-file target và Java SE API của release 17.
- **-encoding UTF-8:** chỉ định encoding của source file.
- **-d build/classes:** nơi ghi class file theo package hierarchy.
- **-classpath / --class-path:** nơi tìm class/JAR dependency trên classpath.
- **--module-path:** nơi tìm named module hoặc automatic module.
- **-processorpath:** nơi tìm annotation processor khi cần cấu hình riêng.

Không nên nhầm --release với JDK đang chạy javac. Compiler có thể chạy từ JDK mới hơn nhưng tạo output tương thích một release cũ hơn nếu release đó được hỗ trợ.

### 3.1. Class-file version

Mỗi class file có major version. JVM dùng thông tin này để xác định bytecode có thuộc phiên bản mà nó hỗ trợ hay không.

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |

Ví dụ Java 17 tạo major version 61. Nếu chạy class file mới hơn bằng JVM cũ, có thể gặp UnsupportedClassVersionError.

Kiểm tra class file:

~~~bash
javap -verbose -classpath build/classes com.example.app.Main
~~~

Tìm dòng major version trong output. Nếu build dùng --release 17 nhưng runtime báo class version mới hơn, hãy kiểm tra compiler thực tế, output cũ còn sót lại hoặc class file dependency được đóng gói.

### 3.2. Generated source và annotation processor

Một số dự án tạo Java source trong quá trình build:

- Annotation processor sinh mapper, metamodel hoặc implementation.
- OpenAPI/Protocol Buffers compiler sinh client/server source.
- Plugin tạo source từ schema hoặc DSL.
- Code generator tạo class từ cấu hình.

Generated source thường được ghi vào thư mục build, không nằm trong src/main/java. Build tool phải chạy task generate trước compile và thêm thư mục output vào source set. Nếu compile chạy trước generator, lỗi thường là không tìm thấy class/package.

Không sửa thủ công file generated nếu nó sẽ bị tạo lại ở build sau. Hãy sửa schema, annotation hoặc cấu hình generator tạo ra file đó.

## 4. Resource được đưa vào artifact như thế nào?

Resource không được javac biên dịch thành class. Build tool hoặc lệnh copy đưa resource vào output directory, giữ đường dẫn tương đối để ứng dụng đọc qua classpath/module.

Ví dụ src/main/resources/app.properties:

~~~properties
message=Hello
~~~

Resource được copy vào:

~~~text
build/classes/app.properties
~~~

Ứng dụng có thể đọc bằng Class.getResourceAsStream:

~~~java
try (InputStream input = Main.class.getResourceAsStream("/app.properties")) {
    if (input == null) {
        throw new IllegalStateException("Missing app.properties");
    }
    Properties properties = new Properties();
    properties.load(input);
}
~~~

Đường dẫn bắt đầu bằng / được hiểu từ root của classpath resource. Nếu bỏ dấu / thì việc tra cứu tương đối với package của class.

Resource filtering là một chức năng riêng của build tool. Một số dự án thay placeholder trong resource bằng version hoặc environment value khi build. Điều này có thể làm artifact khác nhau giữa staging và production dù source giống nhau. Không đưa secret vào resource được đóng gói; secret nên được cấp qua secret manager, environment hoặc cấu hình ngoài artifact.

## 5. Test nằm ở đâu trong pipeline?

Test source thường được biên dịch riêng và chạy trong test JVM:

~~~text
Production:
src/main/java       -> build/classes/.../main
src/main/resources  -> build/resources/.../main

Test:
src/test/java       -> build/classes/.../test
src/test/resources  -> build/resources/.../test
~~~

Test có thể dùng production class và test dependency. Test class và test report thường không được đưa vào production JAR.

Các nhóm test thường gặp:

- Unit test: kiểm tra class/method riêng lẻ.
- Integration test: kiểm tra nhiều module, database, filesystem hoặc service.
- Contract test: kiểm tra tương thích với API/protocol.
- Smoke test: kiểm tra artifact có khởi động và đáp ứng chức năng cơ bản.

Build thành công không đồng nghĩa test đã chạy. Nếu log ghi NO-SOURCE, NO-SOURCE test hoặc tests skipped, hãy kiểm tra task/phase tương ứng trước khi kết luận pipeline đã kiểm thử.

## 6. Đóng gói class và resource thành JAR

JAR là archive dựa trên ZIP, thường chứa:

- Class file đã biên dịch.
- Resource cần ở runtime.
- META-INF/MANIFEST.MF.
- Module descriptor nếu là modular JAR.
- Signature metadata nếu JAR được ký.

JAR mặc định không tự nhúng mọi dependency mà project sử dụng. Một JAR tiêu chuẩn thường là **thin JAR**: chứa code của chính ứng dụng, dependency được cung cấp riêng trên classpath hoặc module path.

### 6.1. Manifest và Main-Class

Manifest là metadata trong META-INF/MANIFEST.MF. Thuộc tính Main-Class chỉ định class có phương thức main để launcher có thể chạy JAR bằng java -jar.

Ví dụ MANIFEST.MF:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Implementation-Version: 1.2.3

~~~

Đóng gói từ output directory:

~~~bash
jar --create --file build/hello-app.jar --manifest build/MANIFEST.MF -C build/classes .
~~~

Trong lệnh trên:

- --create tạo archive mới.
- --file chỉ định file JAR đích.
- --manifest chỉ định manifest.
- -C chuyển vào build/classes trước khi thêm nội dung.
- Dấu chấm thêm toàn bộ nội dung của output directory.

Chạy executable JAR:

~~~bash
java -jar build/hello-app.jar
~~~

Khi dùng java -jar, launcher lấy entry point từ Main-Class. Không truyền classpath theo cách thông thường cùng lệnh này; dependency ngoài cần được cấu hình theo packaging/launcher phù hợp.

### 6.2. Thin JAR và fat/uber JAR

| Kiểu | Nội dung | Cách chạy |
|---|---|---|
| Thin JAR | Class/resource của ứng dụng | Cung cấp dependency qua classpath hoặc module path |
| Fat/uber JAR | Ứng dụng và dependency được gom vào một archive | Thường chạy bằng java -jar |
| Modular JAR | Có module-info.class và module descriptor | Chạy bằng module path/module launcher |
| WAR | Web application và web metadata/resource | Deploy vào servlet container hoặc runtime tương thích |

Fat JAR thường được tạo bằng plugin hoặc task chuyên biệt, không phải hành vi mặc định của lệnh jar. Khi gộp dependency, cần xử lý file trùng tên, service descriptor, license, signature và resource merge. Không sao chép nguyên signature metadata của dependency đã được ký vào một JAR mới vì nội dung archive đã thay đổi.

### 6.3. Modular JAR

Nếu module có module-info.java, compiler tạo module-info.class. Khi đóng gói, file đó nằm ở root của JAR và JAR trở thành explicit modular JAR.

~~~java
module com.example.app {
    requires java.logging;
    exports com.example.app.api;
}
~~~

Kiểm tra module descriptor:

~~~bash
jar --describe-module --file build/hello-app.jar
~~~

Một JAR không có module-info.class nhưng đặt trên module path có thể được xem là automatic module. Tên module được lấy từ Automatic-Module-Name trong manifest nếu có, hoặc suy ra từ tên JAR. Đừng nhầm automatic module với explicit modular JAR.

## 7. WAR, runtime image và installer

JAR không phải định dạng duy nhất:

- **WAR:** đóng gói web application, class, resource và WEB-INF metadata; được triển khai lên servlet container hoặc application server tương thích.
- **jlink image:** tạo runtime image chỉ gồm các JDK modules cần thiết cho ứng dụng modular.
- **jpackage installer:** tạo gói cài đặt phù hợp với nền tảng như MSI, EXE, PKG hoặc DEB tùy môi trường và option.
- **Container image:** chứa runtime, artifact và cấu hình triển khai để chạy ứng dụng trong container.

Các định dạng này nằm ở các tầng khác nhau. JAR là application artifact; jlink image là runtime image; jpackage là installer; container image là đơn vị triển khai. Đừng gọi tất cả là JAR hoặc cho rằng tạo JAR đồng nghĩa đã tạo một bản cài đặt hoàn chỉnh.

## 8. Dependency được phân phối cùng artifact ra sao?

Với thin JAR, dependency phải có sẵn lúc runtime. Có một số cách phổ biến:

1. Đưa các JAR dependency vào thư mục lib và cấu hình classpath.
2. Dùng module path nếu ứng dụng là modular.
3. Dùng manifest Class-Path cho layout đơn giản và cố định.
4. Tạo fat JAR bằng plugin/task có hỗ trợ merge.
5. Dùng launcher hoặc script do build tạo để lắp ráp classpath.

Ví dụ chạy thin JAR cùng thư mục lib trên Linux/macOS:

~~~bash
java -cp "build/hello-app.jar:lib/*" com.example.app.Main
~~~

Trên Windows, separator giữa các path element là dấu chấm phẩy:

~~~powershell
java -cp "build\hello-app.jar;lib\*" com.example.app.Main
~~~

Manifest Class-Path có quy tắc URI tương đối với vị trí JAR, không phải một biến môi trường. Khi dependency path thay đổi, manifest cũ có thể trỏ sai.

Không dùng -cp để thay thế module path khi ứng dụng khai báo requires cho named module. Nếu dùng JPMS, hãy cung cấp đúng module path và module graph.

## 9. Gradle: từ source set đến JAR

Với Java plugin, Gradle cung cấp các task tiêu chuẩn:

| Task | Công việc |
|---|---|
| compileJava | Biên dịch production source |
| processResources | Copy/filter production resources |
| classes | Tổng hợp production class và resource |
| compileTestJava | Biên dịch test source |
| processTestResources | Copy test resources |
| test | Chạy test |
| jar | Tạo JAR |
| check | Chạy các verification task |
| build | Tổng hợp assemble và check |

Cấu trúc output thông thường:

~~~text
build/
├── classes/java/main/
├── resources/main/
├── classes/java/test/
├── resources/test/
├── reports/tests/
├── test-results/
└── libs/
    └── project-version.jar
~~~

Các lệnh hữu ích:

~~~bash
./gradlew clean
./gradlew compileJava
./gradlew test
./gradlew jar
./gradlew build
./gradlew tasks --all
./gradlew jar --info
~~~

Một build.gradle tối thiểu:

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.2.3'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named('jar') {
    manifest {
        attributes(
            'Main-Class': 'com.example.app.Main',
            'Implementation-Version': project.version
        )
    }
}
~~~

Toolchain chọn JDK cho task Java; Gradle daemon JVM có thể khác JDK compiler. Để xem JDK được phát hiện:

~~~bash
./gradlew -q javaToolchains
~~~

Gradle Wrapper nên được commit trong repository để nhóm và CI dùng cùng Gradle version. Dùng Wrapper của project thay cho một bản Gradle global khi kiểm tra pipeline.

## 10. Maven: từ lifecycle đến JAR

Maven dùng lifecycle và các phase tiêu chuẩn:

| Phase | Công việc chính |
|---|---|
| validate | Kiểm tra project và cấu hình |
| compile | Biên dịch production source |
| test | Chạy unit test |
| package | Tạo JAR/WAR |
| verify | Chạy các kiểm tra bổ sung |
| install | Cài artifact vào local repository |
| deploy | Đưa artifact lên remote repository |

Một số phase gọi các phase trước nó. Ví dụ mvn package sẽ chạy các phase cần thiết trước package, gồm compile và test theo lifecycle mặc định.

Các lệnh hữu ích:

~~~bash
mvn clean
mvn compile
mvn test
mvn package
mvn verify
mvn install
mvn deploy
~~~

Cấu trúc output thông thường:

~~~text
target/
├── classes/
├── test-classes/
├── surefire-reports/
└── artifactId-version.jar
~~~

Một pom.xml tối thiểu cho Java 17 và executable JAR:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>hello-app</artifactId>
  <version>1.2.3</version>
  <properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.release>17</maven.compiler.release>
  </properties>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.4.2</version>
        <configuration>
          <archive>
            <manifest>
              <mainClass>com.example.app.Main</mainClass>
            </manifest>
          </archive>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Maven Wrapper cũng nên được commit để CI và developer dùng cùng Maven distribution. Maven compiler plugin, jar plugin, surefire plugin và plugin khác nên được quản lý version rõ ràng trong build.

## 11. Kiểm tra artifact sau khi đóng gói

Không dừng ở thông báo BUILD SUCCESSFUL. Kiểm tra chính file được tạo.

### 11.1. Liệt kê nội dung JAR

~~~bash
jar --list --file build/hello-app.jar
~~~

Kiểm tra có:

- META-INF/MANIFEST.MF.
- Class chính và package hierarchy.
- Resource cần thiết.
- module-info.class nếu là explicit modular JAR.
- Không có source, test class, file tạm hoặc secret không mong muốn.

### 11.2. Đọc manifest

~~~bash
jar --extract --file build/hello-app.jar META-INF/MANIFEST.MF
~~~

Mở file META-INF/MANIFEST.MF và kiểm tra Main-Class, Implementation-Version, Class-Path hoặc metadata cần thiết. Lưu ý lệnh extract ghi file ra working directory; thực hiện trong thư mục kiểm tra riêng nếu không muốn ghi vào project.

### 11.3. Kiểm tra bytecode và dependency

~~~bash
javap -classpath build/hello-app.jar -verbose com.example.app.Main
jdeps --print-module-deps build/hello-app.jar
~~~

javap cho biết class file có tồn tại và version bytecode. jdeps phân tích dependency ở cấp class/module; nó không thay thế test runtime và không xác nhận mọi dependency động hoặc reflection.

### 11.4. Tính checksum

Windows PowerShell:

~~~powershell
Get-FileHash build/hello-app.jar -Algorithm SHA256
~~~

Linux/macOS:

~~~bash
sha256sum build/hello-app.jar
~~~

Checksum giúp phát hiện file thay đổi hoặc truyền tải sai. Hai lần build không tạo checksum giống nhau chưa chắc source khác nhau; archive timestamp, entry order, manifest metadata hoặc nội dung sinh từ thời gian có thể làm file khác byte.

### 11.5. Chữ ký JAR

Nếu phát hành yêu cầu ký, dùng jarsigner với khóa và chứng thư được quản lý an toàn:

~~~bash
jarsigner -keystore release-keystore.p12 -storetype PKCS12 build/hello-app.jar release-key
jarsigner -verify -verbose -certs build/hello-app.jar
~~~

Chữ ký bảo vệ tính toàn vẹn của các entry đã ký và gắn chúng với signer certificate. Kết quả verify cần được đánh giá cùng trust chain, thời hạn, chính sách certificate và cảnh báo. Chữ ký không thay thế checksum trong quy trình truyền tải; checksum cũng không chứng minh danh tính người phát hành.

Không đưa private key, keystore password hoặc signing credential vào source control hay artifact.

## 12. Reproducible build

Một build có tính tái lập khi cùng source revision và cùng đầu vào được kiểm soát có thể tạo ra artifact giống nhau theo tiêu chí đã đặt ra, thường là byte-for-byte.

Các yếu tố có thể làm artifact khác nhau:

- Timestamp của từng ZIP/JAR entry.
- Thứ tự file trong archive.
- JDK/compiler version và compiler flags.
- Dependency version không được pin.
- Generated source chứa thời gian hoặc đường dẫn tuyệt đối.
- Locale, timezone, environment variables.
- Resource filtering theo môi trường.
- Build plugin version thay đổi.
- File permission hoặc line ending khác nhau.

Gradle có thể cấu hình archive task:

~~~groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Maven Archiver hỗ trợ output timestamp thông qua project.build.outputTimestamp. Ví dụ cấu hình property cố định và để plugin JAR sử dụng giá trị đó:

~~~xml
<properties>
  <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Hãy kiểm tra version plugin và tài liệu tương ứng để xác nhận option được hỗ trợ. Reproducibility còn cần dependency, toolchain, generated content và môi trường được kiểm soát; chỉ đặt timestamp không đảm bảo toàn bộ build tái lập.

Dependency locking, checksum verification và Wrapper giúp giảm biến động đầu vào. Không dùng version động như latest hoặc 1.+ trong build phát hành nếu yêu cầu là tạo artifact ổn định.

## 13. CI, artifact repository và triển khai

Pipeline CI nên tách rõ build, test, package, verify và publish:

1. Checkout đúng commit.
2. Cài/chọn JDK và build tool theo cấu hình dự án.
3. Resolve dependency theo lock/version policy.
4. Compile và chạy test.
5. Package artifact.
6. Kiểm tra nội dung, version và checksum.
7. Ký artifact nếu quy trình phát hành yêu cầu.
8. Upload đúng artifact vào artifact repository/store.
9. Triển khai chính artifact đó sang môi trường tiếp theo.

Sau khi artifact đã được kiểm thử, hãy promote chính artifact đó qua staging và production. Tránh build lại độc lập cho từng môi trường vì build thứ hai có thể tạo nội dung khác. Cấu hình môi trường nên được cung cấp ngoài artifact khi có thể.

Metadata nên lưu cùng bản phát hành:

- Artifact coordinates: group, artifact, version, classifier.
- Source revision/commit.
- JDK vendor/version và compiler release.
- Gradle/Maven Wrapper version.
- Dependency lock/manifest.
- Build timestamp hoặc provenance record.
- SHA-256 checksum.
- Chữ ký và signer identity nếu có.
- Kết quả test/verification liên quan.

Artifact repository thường giữ version bất biến. Nếu cần sửa code, tạo version mới thay vì ghi đè một release đã phát hành.

## 14. Chạy artifact trong môi trường đích

Artifact được tạo bởi build tool nhưng runtime quyết định nó có thể chạy hay không.

Với executable JAR:

~~~bash
java -jar build/hello-app.jar
~~~

Với thin JAR:

~~~bash
java -cp "build/hello-app.jar:lib/*" com.example.app.Main
~~~

Với modular JAR:

~~~bash
java --module-path lib --module com.example.app
~~~

Trên Windows, classpath separator là dấu chấm phẩy; trên Linux/macOS là dấu hai chấm. Module path và classpath phải được cấu hình đúng theo loại ứng dụng.

Khi triển khai, kiểm tra:

- JDK/runtime version có hỗ trợ class-file version không?
- Dependency có đầy đủ và đúng version không?
- Resource có nằm trong artifact hoặc đường dẫn runtime không?
- Main-Class/module name có đúng không?
- Cấu hình ngoài artifact có sẵn không?
- Port, filesystem permission, certificate và network có phù hợp không?
- JVM options, memory limit và container limit có hợp lý không?

Không nhúng mật khẩu, private key hoặc secret vào JAR. File JAR có thể được giải nén và đọc; secret trong archive không thể được bảo vệ chỉ bằng cách đổi tên file.

## 15. Ví dụ Java 17 hoàn chỉnh: source đến executable JAR

Ví dụ này có một class Java, một resource properties và manifest. Nó minh họa compile, copy resource, package, run và inspect.

Cấu trúc project:

~~~text
hello-app/
├── src/
│   ├── main/
│   │   ├── java/com/example/app/Main.java
│   │   └── resources/app.properties
└── build/
    └── MANIFEST.MF
~~~

Nội dung src/main/java/com/example/app/Main.java:

~~~java
package com.example.app;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class Main {
    private Main() { }

    public static void main(String[] args) throws IOException {
        Properties config = new Properties();
        try (InputStream input =
                 Main.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException("Missing app.properties");
            }
            config.load(input);
        }

        String name = args.length == 0 ? "Java" : args[0];
        String version = Main.class.getPackage().getImplementationVersion();
        System.out.println(config.getProperty("message") + ", " + name + "!");
        System.out.println("ARTIFACT_VERSION=" + version);
        System.out.println("RESOURCE_STATUS=LOADED");
    }
}
~~~

Nội dung src/main/resources/app.properties:

~~~properties
message=Hello
~~~

Nội dung build/MANIFEST.MF:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Implementation-Version: 1.2.3

~~~

### 15.1. Biên dịch

Từ thư mục hello-app:

~~~bash
mkdir -p build/classes
javac --release 17 -encoding UTF-8 -d build/classes src/main/java/com/example/app/Main.java
~~~

### 15.2. Copy resource

Linux/macOS:

~~~bash
cp src/main/resources/app.properties build/classes/
~~~

Windows PowerShell:

~~~powershell
Copy-Item src/main/resources/app.properties build/classes/
~~~

### 15.3. Package

~~~bash
jar --create --file build/hello-app.jar --manifest build/MANIFEST.MF -C build/classes .
~~~

### 15.4. Chạy artifact

~~~bash
java -jar build/hello-app.jar Toolchain
~~~

Output đã kiểm thử bằng Amazon Corretto 17.0.15+6-LTS trên Windows:

~~~text
Hello, Toolchain!
ARTIFACT_VERSION=1.2.3
RESOURCE_STATUS=LOADED
~~~

### 15.5. Kiểm tra artifact

~~~bash
jar --list --file build/hello-app.jar
javap -classpath build/hello-app.jar -verbose com.example.app.Main
jdeps --print-module-deps build/hello-app.jar
~~~

Các kết quả đã xác nhận:

- JAR chứa META-INF/MANIFEST.MF.
- JAR chứa app.properties và com/example/app/Main.class.
- Class file có major version 61, tương ứng Java 17.
- Dependency module tối thiểu là java.base.
- Chương trình đọc resource từ chính JAR và lấy Implementation-Version từ manifest.

Có thể tính checksum sau khi package:

~~~powershell
Get-FileHash build/hello-app.jar -Algorithm SHA256
~~~

Checksum sẽ thay đổi nếu byte của archive thay đổi, kể cả khi output chương trình giống nhau.

## 16. Lỗi thường gặp trong luồng source đến artifact

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Class không xuất hiện trong JAR | Source chưa được compile hoặc package task không nhận output | Kiểm tra compile task và source set |
| Resource không đọc được | Resource chưa được copy hoặc sai đường dẫn | Kiểm tra processResources, target/classes và JAR contents |
| Build thành công nhưng java -jar báo no main manifest attribute | Thiếu Main-Class trong manifest | Cấu hình manifest hoặc jar plugin |
| java -jar không tìm thấy dependency | JAR là thin JAR, dependency chưa được cung cấp | Cấu hình classpath/module path, launcher hoặc fat JAR |
| UnsupportedClassVersionError | Bytecode mới hơn JVM runtime | Kiểm tra class major version và --release |
| Artifact thiếu class generated | Generator chưa chạy hoặc output chưa nằm trong source set | Đặt dependency task và generated source directory |
| Test không chạy | Test source không được phát hiện hoặc task bị skip | Kiểm tra test source set, test filter và reports |
| JAR có file thừa/secret | Resource folder chứa dữ liệu không dành cho release | Rà soát nội dung archive trước publish |
| JAR khác checksum giữa hai build | Timestamp, order, generated content hoặc toolchain khác | Kiểm soát reproducibility và đầu vào |
| Artifact chạy ở local nhưng lỗi trên server | Runtime/JDK, dependency, config hoặc OS khác | Chạy chính artifact trên môi trường đích và so sánh baseline |
| Modular JAR không resolve | Thiếu module-info hoặc sai module path/requires | Dùng jar --describe-module và java --show-module-resolution |
| Chữ ký không hợp lệ sau khi chỉnh JAR | Archive đã thay đổi sau khi ký | Ký lại sau bước package cuối cùng |

## 17. Checklist trước khi phát hành artifact

- [ ] Đã xác định source, resources, generated sources và dependencies.
- [ ] JDK/toolchain và compiler release đã được pin phù hợp.
- [ ] Production source đã compile thành công.
- [ ] Resource cần thiết đã được copy đúng đường dẫn.
- [ ] Unit/integration test đã chạy và kết quả được lưu.
- [ ] Artifact có đúng loại JAR/WAR/module/runtime image cần phát hành.
- [ ] Manifest có Main-Class và version metadata nếu cần.
- [ ] Dependency runtime được cung cấp đúng cách.
- [ ] Đã kiểm tra nội dung archive bằng jar --list.
- [ ] Đã kiểm tra bytecode bằng javap khi cần.
- [ ] Đã kiểm tra dependency bằng jdeps khi cần.
- [ ] Checksum được tính và lưu cùng artifact.
- [ ] Chữ ký được xác minh nếu quy trình yêu cầu.
- [ ] Reproducibility và dependency locking được cấu hình phù hợp.
- [ ] CI lưu đúng artifact được test.
- [ ] Chính artifact đó được promote sang môi trường tiếp theo.
- [ ] Runtime, config, permission và secret đã sẵn sàng khi deploy.

## 18. Ghi nhớ

Source, resource, generated source và dependency là đầu vào. Compiler chuyển Java source thành bytecode trong class file; build tool xử lý resource và test; packaging task tạo JAR/WAR; bước verify kiểm tra nội dung, metadata và dependency; publish phân phối artifact; deploy chạy artifact trong runtime phù hợp.

JAR tiêu chuẩn không tự chứa toàn bộ dependency. Manifest xác định entry point và metadata; module descriptor điều khiển JPMS; checksum giúp xác nhận tính toàn vẹn; chữ ký gắn nội dung với signer. Một build đáng tin cậy phải ghi lại toolchain và dependency, kiểm tra artifact thực tế, và đưa chính file đã kiểm thử đến môi trường triển khai.

Tài liệu tham khảo:

- [Oracle Java SE 17 — The javac Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Oracle Java SE 17 — The jar Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html)
- [Oracle Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle Java SE 17 — The javap Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html)
- [Oracle Java SE 17 — The jdeps Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html)
- [Oracle Java SE 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html)
- [Oracle Java SE 17 — JAR Manifest](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html#jar-manifest)
- [Oracle Java SE 17 — jarsigner](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html)
- [Gradle — The Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle — Reproducible Archives](https://docs.gradle.org/current/userguide/working_with_files.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Maven JAR Plugin](https://maven.apache.org/plugins/maven-jar-plugin/)
- [Apache Maven — Maven Archiver](https://maven.apache.org/shared/maven-archiver/)