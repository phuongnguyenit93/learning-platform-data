# Nâng công cụ build và thư viện lên bản hỗ trợ JDK 17

**Chủ đề:** Java 17 → Nâng cấp lên Java 17  
**Trọng tâm:** Nâng Gradle/Maven, build plugins, test frameworks, annotation processors, thư viện phân tích bytecode và framework ứng dụng lên các phiên bản tương thích JDK 17; cấu hình toolchain và compiler release để build tái lập; xác minh môi trường biên dịch, kiểm thử, đóng gói và runtime.

Nâng ứng dụng lên Java 17 không chỉ là đổi JAVA_HOME hoặc thêm tùy chọn --release 17. Một dự án Java thường có nhiều thành phần chạy trong các JVM khác nhau: build tool, compiler, test runner, annotation processor, plugin, công cụ đo coverage, thư viện bytecode và ứng dụng sau khi đóng gói. Chỉ cần một thành phần cũ chưa hiểu class file hoặc API của JDK 17, build có thể lỗi dù mã nguồn ứng dụng không có vấn đề.

Quy trình nâng cấp nên kiểm tra ba lớp tương thích:

1. **Build chạy được trên JDK 17:** Gradle/Maven và plugin của chúng phải khởi động, thực thi task và truy cập JDK 17 đúng cách.
2. **Tooling xử lý được Java 17:** compiler, test framework, annotation processor, bytecode library, agent và công cụ phân tích phải hiểu cú pháp, class file và API cần dùng.
3. **Ứng dụng chạy được trên JDK 17:** mọi dependency trực tiếp và bắc cầu phải tương thích runtime; cấu hình module, reflection, TLS, logging và các tích hợp hệ thống cũng cần được kiểm tra.

Không nên chỉ nhìn vào phiên bản JDK mà một thư viện ghi trong mô tả. Cần xác định thư viện đó chạy ở giai đoạn nào, được build bằng bytecode nào, có dùng JDK internals không và phiên bản nào được nhà cung cấp xác nhận hỗ trợ.

## 1. Phân biệt JDK chạy build, JDK biên dịch và JDK chạy ứng dụng

Một dự án có thể dùng nhiều phiên bản Java cho những mục đích khác nhau:

| Thành phần | Vai trò | Câu hỏi cần kiểm tra |
| --- | --- | --- |
| JVM chạy Gradle/Maven | Chạy build daemon, plugin và các tác vụ của build tool. | Build tool có chạy trên JDK 17 không? |
| JDK toolchain/compiler | Cung cấp javac và công cụ biên dịch. | Compiler có phải JDK 17 không? |
| --release | Giới hạn ngôn ngữ, API nền tảng và bytecode đích. | Code có thực sự chỉ dùng API Java 17 không? |
| JVM chạy test | Thực thi unit/integration tests và agent. | Test fork có dùng JDK 17 không? |
| JVM runtime | Chạy ứng dụng trong container, VM hoặc máy chủ. | Tất cả dependency có chạy trên JDK 17 không? |
| JDK của IDE | Chạy IDE hoặc Gradle/Maven integration trong IDE. | Build từ IDE có dùng cùng cấu hình với CI không? |

Kiểm tra môi trường hiện tại:

~~~shell
java -version
javac -version
mvn -version
gradle --version
~~~

Nếu dự án có Maven Wrapper hoặc Gradle Wrapper, hãy kiểm tra cả wrapper:

~~~shell
./mvnw -version
./gradlew --version
~~~

Trên Windows có thể dùng mvnw.cmd và gradlew.bat. Kết quả của mvn -version hoặc gradle --version thường cho biết JVM đang chạy build tool; nó chưa chứng minh compiler/test task cũng dùng cùng JDK nếu dự án cấu hình toolchain riêng.

### 1.1. Vì sao chỉ đổi JAVA_HOME chưa đủ?

JAVA_HOME thường ảnh hưởng JVM mặc định của command line tool. Nhưng:

- Gradle có thể dùng một JVM khác cho daemon hoặc được IDE chỉ định Gradle JVM riêng.
- Gradle toolchain có thể chọn một JDK khác để compile, test và tạo Javadoc.
- Maven Toolchains có thể chọn compiler JDK độc lập với JVM chạy Maven.
- Surefire/Failsafe có thể fork JVM riêng để chạy test.
- Plugin có thể chạy trong JVM của build tool, trong JVM fork riêng hoặc thông qua native executable.
- CI/container có thể cài nhiều JDK và chọn khác với máy phát triển.

Vì vậy, hãy ghi rõ JDK cho từng giai đoạn và kiểm tra kết quả thực tế của build.

## 2. Mốc tương thích của các build tool

### 2.1. Gradle

Theo compatibility matrix chính thức:

- **Gradle 7.3** là phiên bản đầu tiên hỗ trợ chạy Gradle trên JDK 17.
- Gradle 7.3 cũng hỗ trợ Java 17 toolchain.
- Gradle 9 yêu cầu JDK 17 trở lên để chạy chính Gradle.
- Khả năng chạy Gradle trên một JDK và khả năng compile/test bằng JDK khác được quản lý riêng qua toolchain.

Do đó, Gradle cũ hơn 7.3 không phải lựa chọn phù hợp để chạy build trên JDK 17. Tuy nhiên, 7.3 chỉ là mốc tương thích lịch sử tối thiểu; không có nghĩa mọi plugin hoặc framework hiện tại đều còn hỗ trợ Gradle 7.3. Hãy chọn bản Gradle đang được duy trì và đáp ứng ma trận của các plugin chính trong dự án.

Kiểm tra:

~~~shell
./gradlew --version
./gradlew wrapper --gradle-version 9.9.1
./gradlew --stop
./gradlew --version
~~~

Lệnh cập nhật wrapper chỉ là ví dụ dùng một bản Gradle hiện hành; trước khi áp dụng cần kiểm tra plugin, Android Gradle Plugin, Kotlin plugin và convention plugin của dự án có tương thích với bản chọn hay không. Không nên nâng major Gradle cùng lúc với nhiều plugin lớn nếu chưa có bộ kiểm thử đủ tin cậy.

### 2.2. Maven

Maven core và Maven Compiler Plugin là hai thành phần khác nhau:

- Maven 3.9.x có thể chạy trên JDK 17.
- Maven Compiler Plugin cần được pin phiên bản và cấu hình release rõ ràng.
- Test plugins, Javadoc plugin, enforcer, shade, code quality và các plugin khác cũng có vòng đời phát hành riêng.

Tài liệu Apache Maven hiện hướng dẫn dùng maven.compiler.release và pin maven-compiler-plugin; ví dụ hiện hành dùng Compiler Plugin 3.16.0. Plugin này hỗ trợ cấu hình release 17. Với dự án Maven, nên dùng Maven Wrapper để mọi developer và CI chạy cùng Maven distribution.

Kiểm tra:

~~~shell
./mvnw -version
./mvnw help:effective-pom
./mvnw dependency:tree
~~~

help:effective-pom cho biết cấu hình plugin thực tế sau khi kế thừa từ parent POM và profile; dependency:tree giúp tìm phiên bản thư viện được chọn sau khi Maven giải quyết dependency.

### 2.3. Không chọn build tool chỉ theo một con số tối thiểu

Mốc Gradle 7.3 cho biết Gradle có thể chạy trên JDK 17, nhưng một framework mới có thể đòi Gradle 8.14 hoặc 9.x. Tương tự, Maven core có thể chạy trên JDK 17 nhưng plugin cũ có thể gọi API nội bộ của javac hoặc không hiểu class file mới.

Ví dụ, Spring Boot 3.5.x yêu cầu Java 17 và công bố các mức build tool riêng; Spring Boot 4.1.x cũng yêu cầu Java 17 nhưng yêu cầu Gradle 8.14+ hoặc 9.x. Khi nâng framework, phải đọc system requirements của chính phiên bản framework đang chọn, không suy ra từ yêu cầu của JDK.

## 3. Cấu hình compiler để thật sự target Java 17

JDK dùng để chạy compiler và phiên bản Java mà output hỗ trợ là hai quyết định riêng. Nếu muốn compile bằng JDK 17 và tạo ứng dụng chạy trên JDK 17, cấu hình release 17.

### 3.1. Vì sao nên dùng --release?

javac --release 17 ràng buộc đồng thời:

- Cú pháp/ngôn ngữ Java được hỗ trợ.
- Phiên bản class file được tạo.
- Tập public Java SE APIs mà mã nguồn có thể tham chiếu.

Chỉ đặt -source 17 và -target 17 không bảo đảm mã không gọi API chỉ xuất hiện ở JDK mới hơn. --release kiểm tra cả API nền tảng của release đích.

Java 17 dùng class-file major version **61**. Nếu một thư viện được biên dịch cho JDK mới hơn, JVM 17 có thể không nạp được class đó và báo UnsupportedClassVersionError.

### 3.2. Toolchain kết hợp với release

Toolchain chọn JDK compiler; release giới hạn API và bytecode đích. Với mục tiêu Java 17, cả hai nên là 17:

~~~text
JDK toolchain 17
       |
       v
     javac
       |
       | --release 17
       v
Class file version 61
       |
       v
Runtime JDK 17
~~~

Đây là cấu hình rõ ràng hơn việc phụ thuộc vào JDK mặc định của máy developer hoặc CI.

## 4. Nâng và cấu hình Gradle

### 4.1. Cập nhật Gradle Wrapper

Gradle Wrapper lưu phiên bản distribution trong gradle/wrapper/gradle-wrapper.properties. Ví dụ:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.1-bin.zip
~~~

Wrapper giúp các môi trường dùng cùng một Gradle version:

~~~shell
./gradlew --version
./gradlew clean build
~~~

Commit cả wrapper script và file cấu hình distribution vào source control. Trong CI, ưu tiên gọi wrapper thay vì dùng Gradle cài global trên runner.

### 4.2. Cấu hình Java toolchain và release trong Groovy DSL

Trong build.gradle:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

toolchain yêu cầu Gradle tìm JDK 17 cho các task Java được hỗ trợ. options.release giới hạn API/bytecode ở Java 17. useJUnitPlatform() bật JUnit Platform nếu dự án dùng JUnit Jupiter hoặc một engine tương thích.

### 4.3. Kotlin DSL

Trong build.gradle.kts:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

tasks.test {
    useJUnitPlatform()
}
~~~

Nếu dự án dùng Kotlin, Scala hoặc Groovy, cần cấu hình compiler/toolchain tương ứng. Khối java toolchain không tự bảo đảm mọi plugin bên thứ ba đều sử dụng đúng JDK nếu plugin đó không tích hợp với Gradle toolchains.

### 4.4. Kiểm tra Gradle daemon và toolchain

Các lệnh hữu ích:

~~~shell
./gradlew --version
./gradlew javaToolchains
./gradlew buildEnvironment
./gradlew dependencies
./gradlew dependencyInsight --dependency byte-buddy
~~~

- --version cho biết JVM đang chạy Gradle.
- javaToolchains liệt kê JDK được Gradle phát hiện.
- buildEnvironment hiển thị dependency của buildscript/plugin classpath.
- dependencies hiển thị dependency của các configuration.
- dependencyInsight giải thích vì sao một phiên bản dependency được chọn.

Sau khi đổi toolchain hoặc JVM daemon, có thể dừng daemon để build sau khởi tạo lại:

~~~shell
./gradlew --stop
~~~

Không dùng org.gradle.java.home như cách thay thế cho toolchain trong mọi trường hợp. Thuộc tính này điều khiển JVM chạy Gradle; toolchain điều khiển JDK dùng cho task compile/test/javadoc.

## 5. Nâng và cấu hình Maven

### 5.1. Dùng Maven Wrapper

Maven Wrapper ghim phiên bản Maven cho dự án. Các lệnh build nên được chạy qua:

~~~shell
./mvnw -version
./mvnw clean verify
~~~

Wrapper giúp CI và developer không vô tình dùng các Maven version khác nhau. Vẫn cần cài JDK phù hợp; wrapper không tự bảo đảm mọi plugin dùng đúng compiler JDK nếu dự án chưa cấu hình toolchain.

### 5.2. Cấu hình Maven Compiler Plugin

Ví dụ phần liên quan trong pom.xml:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <junit.version>6.0.3</junit.version>
</properties>

<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
                <configuration>
                    <release>17</release>
                    <encoding>UTF-8</encoding>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.6.0</version>
            </plugin>
        </plugins>
    </pluginManagement>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-failsafe-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Đây là ví dụ cấu hình; nếu parent POM đã quản lý plugin version, hãy cập nhật ở đúng nơi thay vì khai báo trùng. Pin plugin version giúp build không âm thầm thay đổi khi Maven hoặc parent POM được cập nhật.

### 5.3. Thêm JUnit Jupiter

Nếu dự án dùng JUnit 6:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>6.0.3</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

JUnit 6 yêu cầu Java 17 làm baseline. JUnit 5 vẫn hỗ trợ Java 8 trở lên và có thể chạy trên JDK 17; vì vậy **không bắt buộc nâng JUnit 5 lên JUnit 6 chỉ để ứng dụng chạy trên Java 17**. Chỉ chuyển major khi dự án đã sẵn sàng xử lý các thay đổi trong migration guide.

Maven Surefire/Failsafe cần phiên bản hỗ trợ JUnit Platform và engine mà dự án dùng. Surefire 3.6.x hiện hỗ trợ chạy JUnit Platform với Jupiter/Vintage và TestNG qua provider tương ứng. Hãy giữ version của platform, engine và plugin tương thích với nhau.

### 5.4. Dùng Maven Toolchains

Maven Toolchains cho phép Maven chạy trên một JDK nhưng các plugin toolchain-aware dùng JDK khác. Điều này hữu ích khi developer có nhiều JDK hoặc Maven runtime của tổ chức được quản lý riêng.

Ví dụ cấu hình trong POM:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-toolchains-plugin</artifactId>
            <version>3.3.0</version>
            <executions>
                <execution>
                    <goals>
                        <goal>toolchain</goal>
                    </goals>
                </execution>
            </executions>
            <configuration>
                <toolchains>
                    <jdk>
                        <version>17</version>
                    </jdk>
                </toolchains>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Trên máy build, file ~/.m2/toolchains.xml khai báo JDK đã cài:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

Thay jdkHome và vendor bằng cài đặt thực tế của môi trường. Phiên bản trong provides phải khớp tiêu chí mà POM yêu cầu; Maven Toolchains không tự xác minh rằng một thư mục được gắn nhãn 17 thực sự chứa JDK 17. Quản trị môi trường build vẫn phải bảo đảm điều đó.

### 5.5. Phân biệt Maven runtime với toolchain

mvn -version cho biết JVM chạy Maven. Maven Toolchains có thể chọn JDK 17 cho compiler/test plugin mà không thay đổi JVM đó. Nếu muốn toàn bộ Maven và plugin chạy trực tiếp trên JDK 17, hãy cấu hình JAVA_HOME/runner tương ứng và kiểm tra lại bằng mvn -version.

## 6. Nâng test framework và test plugins

Test stack thường có nhiều tầng:

1. API viết test như JUnit Jupiter hoặc TestNG.
2. Engine chạy test như Jupiter Engine, Vintage Engine hoặc TestNG engine.
3. Launcher/platform điều phối khám phá và thực thi test.
4. Build plugin như Maven Surefire/Failsafe hoặc Gradle Test.
5. Agent, mocking library và instrumentation được nạp trong JVM chạy test.

Các tầng này phải tương thích với nhau và với JDK 17.

### 6.1. JUnit 5 và JUnit 6

| Dòng | Yêu cầu Java | Khi nào dùng |
| --- | --- | --- |
| JUnit 5 | Java 8 trở lên | Dự án muốn giữ tương thích với JDK cũ nhưng chạy test trên JDK 17. |
| JUnit 6 | Java 17 trở lên | Dự án đã chọn Java 17 làm baseline và có thể xử lý migration major. |

JUnit 6 hợp nhất số phiên bản Platform/Jupiter/Vintage và loại bỏ một số API/module cũ. Nếu nâng từ JUnit 5, đọc migration guide và rà soát extension, engine, test runner và IDE integration.

### 6.2. Maven Surefire và Failsafe

- Surefire chạy unit tests ở lifecycle phase test.
- Failsafe chạy integration tests ở các phase integration-test và verify.
- Cả hai cần phiên bản tương thích với JUnit Platform, TestNG hoặc framework đang sử dụng.

Nếu test không được phát hiện, đừng chỉ đổi JUnit version. Hãy kiểm tra provider được chọn, tên class theo quy ước discovery, fork JVM và báo cáo trong target/surefire-reports hoặc target/failsafe-reports.

### 6.3. Mockito, Byte Buddy và mocking/instrumentation

Mockito và một số mocking framework dựa vào Byte Buddy để tạo class hoặc instrument bytecode. Khi JDK tăng, các thư viện này phải hiểu class file mới và không phụ thuộc vào API nội bộ đã bị đóng gói.

Nếu gặp lỗi như Unsupported class file major version, IllegalAccessError, InaccessibleObjectException hoặc lỗi agent attach, hãy xem cả dependency Byte Buddy/ASM bên dưới framework. Không nên override một dependency bắc cầu bằng phiên bản tùy ý nếu framework đã quản lý version tương thích.

## 7. Nâng annotation processors và compiler extensions

Annotation processor chạy trong quá trình compile, thường trong JVM của compiler. Chúng có thể phụ thuộc vào:

- javax.annotation.processing và javax.lang.model.
- Các chi tiết nội bộ của javac.
- AST hoặc compiler internals.
- API tạo mã nguồn, class file hoặc metadata.

Các thư viện thường gặp gồm Lombok, MapStruct, QueryDSL, Error Prone, Checker Framework và các processor do dự án tự viết.

### 7.1. Lombok

Lombok sử dụng tích hợp sâu với compiler. Phiên bản **1.18.22** là mốc công bố hỗ trợ JDK 17. Đây là mốc lịch sử tối thiểu để nhận biết một dependency quá cũ; không nên xem nó là phiên bản nên giữ trong dự án hiện nay. Hãy chọn bản Lombok còn được duy trì, tương thích JDK/compiler và IDE của dự án.

Sau khi nâng, kiểm tra:

- Maven/Gradle compiler có nạp đúng Lombok annotation processor không?
- IDE có plugin Lombok tương thích không?
- Build command line và build trong IDE có sinh cùng code không?
- Các annotation trên record hoặc sealed types có được hỗ trợ đúng trong phiên bản đang dùng không?

### 7.2. MapStruct và processor khác

Với processor sinh mapper hoặc code, kiểm tra release notes về JDK 17 và compiler compatibility. Nếu processor chỉ hỗ trợ JDK cũ, lỗi có thể xuất hiện ở compile time dù runtime library không có vấn đề.

Với Maven, khai báo processor trong annotationProcessorPaths của Compiler Plugin nếu dự án cần kiểm soát processor path riêng. Với Gradle, dùng annotationProcessor configuration. Tránh đưa processor vào classpath runtime chỉ vì muốn compiler tìm thấy nó.

### 7.3. Kiểm tra processor path

Maven:

~~~shell
./mvnw dependency:tree -Dscope=compile
./mvnw help:effective-pom
~~~

Gradle:

~~~shell
./gradlew dependencies --configuration annotationProcessor
./gradlew dependencyInsight --dependency lombok --configuration annotationProcessor
~~~

Nếu processor chạy trong compiler fork, hãy xác nhận JDK fork thực tế. Việc build tool chạy trên JDK 17 không tự bảo đảm một compiler executable riêng cũng là JDK 17.

## 8. Nâng thư viện xử lý bytecode và instrumentation

Java 17 tạo class file major version 61. Các thư viện đọc, phân tích, sửa hoặc tạo bytecode cần hiểu class file version này và các cấu trúc mới mà compiler có thể sinh ra.

Các thành phần cần kiểm tra:

- ASM.
- Byte Buddy.
- Javassist.
- CGLIB hoặc thư viện proxy.
- Mockito và mocking framework.
- JaCoCo và coverage agent.
- APM/profiling/security agents.
- Công cụ obfuscation, shading, weaving hoặc enhancement.

Một số mốc hỗ trợ Java 17 được công bố:

| Thành phần | Mốc hỗ trợ Java 17 được ghi nhận | Cách áp dụng |
| --- | --- | --- |
| ASM | 9.1 bổ sung hỗ trợ JDK 17. | Dùng phiên bản được thư viện phụ thuộc hỗ trợ; tránh ép ASM trực tiếp nếu framework đóng gói hoặc quản lý version riêng. |
| Byte Buddy | 1.10.19 bổ sung hỗ trợ Java 17 class files. | Kiểm tra version do Mockito, agent hoặc plugin kéo vào. |
| JaCoCo | 0.8.8 chính thức hỗ trợ Java 17. | Dùng release hiện hành còn duy trì; 0.8.8 chỉ là mốc tối thiểu lịch sử. |

Đến năm 2026, các dự án này đã có nhiều bản mới hơn các mốc đầu tiên. Hãy chọn phiên bản còn được duy trì, có sửa lỗi và bảo mật mới nhất trong nhánh tương thích với ứng dụng; không ghim vào bản đầu tiên chỉ vì nó từng bổ sung Java 17.

### 8.1. Coverage agent và class instrumentation

JaCoCo agent được nạp trong JVM test hoặc JVM ứng dụng. Nếu agent không hiểu class file hoặc thay đổi bytecode không đúng, test có thể lỗi trước khi code ứng dụng chạy.

Khi nâng JaCoCo:

- Cập nhật cả Maven/Gradle plugin và agent/runtime tương ứng.
- Kiểm tra report goal/task có dùng cùng version.
- Kiểm tra tương thích với Kotlin compiler, record, sealed class và generated code.
- Chạy lại unit test, integration test và tạo report.

### 8.2. Không chỉ kiểm tra dependency trực tiếp

Ví dụ dự án không khai báo ASM trực tiếp, nhưng Mockito hoặc một plugin bytecode kéo ASM vào. Nếu dependency resolution chọn một phiên bản quá cũ, lỗi vẫn xảy ra. Dùng dependency tree và dependency insight để truy nguồn version thực tế trước khi thay đổi.

## 9. Nâng framework và thư viện ứng dụng

Build thành công không chứng minh toàn bộ runtime dependencies tương thích. Cần đọc system requirements của framework chính và kiểm tra dependency bắc cầu.

### 9.1. Spring Boot

Spring Boot 3.x đặt Java 17 làm mức tối thiểu. Các dòng Spring Boot mới hơn cũng công bố build tool matrix riêng; ví dụ Spring Boot 4.1.x yêu cầu Java 17, Maven 3.6.3+ và Gradle 8.14+ hoặc 9.x. Spring Boot 3.5.x cũng yêu cầu Java 17 nhưng mức Gradle được công bố khác.

Khi nâng từ Spring Boot 2.x lên 3.x hoặc mới hơn, cần dự trù thay đổi lớn ngoài JDK:

- Chuyển nhiều API Java EE từ namespace javax.* sang jakarta.*.
- Cập nhật Spring Framework, Hibernate, servlet container và các starter.
- Kiểm tra Security configuration, validation, persistence và integration libraries.
- Rà soát third-party starter chưa hỗ trợ major version mới.

Không nâng riêng Spring Boot parent mà bỏ qua compatibility matrix của các starter và plugin.

### 9.2. Các nhóm dependency cần rà soát

| Nhóm | Ví dụ cần kiểm tra | Vì sao |
| --- | --- | --- |
| Web/framework | Spring, Jakarta APIs, servlet container, REST client | Yêu cầu JDK và API nền tảng có thể thay đổi theo major. |
| Persistence | Hibernate, JDBC driver, migration tool | Có thể dùng reflection, bytecode enhancement hoặc driver native. |
| Serialization | Jackson, JAXB, Kryo, protobuf | Có thể dùng reflection, generated code hoặc class metadata. |
| Logging | Logback, Log4j, SLF4J binding | Cần đồng bộ API và implementation; agent/bridge cũ có thể gây xung đột. |
| Network/security | Netty, TLS provider, crypto provider | Có thể phụ thuộc native library, module access hoặc security provider. |
| Cloud/messaging | Kafka, AMQP, cloud SDK | Cần kiểm tra runtime support và dependency alignment. |
| Database | JDBC driver, pool, ORM | Driver cần hỗ trợ JDK 17 và database/server version tương ứng. |
| Observability | APM agent, tracing, metrics | Agent thường instrument class và có thể cần bản hỗ trợ JDK mới. |

Với mỗi nhóm, kiểm tra phiên bản Java tối thiểu, phiên bản Java tối đa được test, module/reflective access, native dependency và release notes. “Chạy được trên Java 17” không đồng nghĩa “đã được vendor hỗ trợ trong production”.

## 10. Quản lý dependency và plugin có kiểm soát

### 10.1. Lập inventory

Ghi lại:

- Build tool và wrapper version.
- Plugin version và buildscript dependencies.
- Runtime dependencies trực tiếp.
- Runtime dependencies bắc cầu.
- Test-only dependencies.
- Annotation processors.
- Agents và native tools.
- Container base image và JDK distribution.

Không chỉ rà soát pom.xml hoặc build.gradle; plugin có thể được khai báo trong parent POM, version catalog, pluginManagement, convention plugin hoặc build logic riêng.

### 10.2. Dùng BOM và dependency constraints

BOM (Bill of Materials) giúp đồng bộ các artifact cùng một hệ sinh thái, ví dụ Spring Boot dependency management hoặc JUnit BOM. Với Gradle, version catalog và constraints giúp quản lý version tập trung.

Không nên ép mọi thư viện về cùng một version chỉ để giải quyết một lỗi. Hãy dùng version mà framework/plugin hỗ trợ, đọc dependency convergence report và tránh trộn các major version không tương thích.

### 10.3. Phân biệt plugin dependency với application dependency

Plugin được nạp vào classloader của build tool, còn application dependency được đóng gói hoặc đưa vào runtime classpath của ứng dụng. Hai nhóm này có thể có cùng tên thư viện nhưng yêu cầu version khác nhau.

Ví dụ, ASM trong build plugin có thể không phải ASM nằm trong ứng dụng. Khi gặp NoSuchMethodError hoặc ClassNotFoundException, cần xác định classloader và dependency graph của đúng giai đoạn bị lỗi.

### 10.4. Dùng dependency tree để truy nguồn

Maven:

~~~shell
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.ow2.asm:asm
./mvnw dependency:tree -Dincludes=net.bytebuddy:byte-buddy
~~~

Gradle:

~~~shell
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency asm --configuration runtimeClasspath
./gradlew dependencyInsight --dependency byte-buddy --configuration testRuntimeClasspath
~~~

Đổi configuration cho đúng mục đích: compileClasspath, runtimeClasspath, testRuntimeClasspath, annotationProcessor hoặc buildscript/plugin classpath.

## 11. Kiểm tra thư viện có bytecode mới hơn Java 17 không

JVM 17 không thể nạp class file được biên dịch cho Java mới hơn. Java 17 có major version 61; thư viện được biên dịch cho Java 21, chẳng hạn, có major version 65 và không chạy trên JVM 17.

Có thể kiểm tra class file bằng:

~~~shell
javap -verbose -classpath library.jar com.example.SomeClass
~~~

Tìm dòng major version. Với JDK 17, class file mục tiêu phải không vượt quá 61, trừ khi JAR là multi-release và runtime 17 chọn đúng base/version phù hợp.

### 11.1. Multi-release JAR

Một JAR có thể chứa class dành cho nhiều Java release trong META-INF/versions/. JVM chọn phần phù hợp với runtime. Vì vậy, chỉ nhìn một class entry hoặc metadata chung của JAR có thể chưa đủ; cần kiểm tra manifest Multi-Release: true và cấu trúc archive.

Các công cụ phân tích dependency như jdeps có tùy chọn --multi-release 17 để chọn nội dung phù hợp với release đích khi phân tích JAR đa phiên bản.

### 11.2. Kiểm tra JDK internals

Một thư viện có thể biên dịch được nhưng truy cập package nội bộ của JDK bằng reflection hoặc bytecode. Java 17 áp dụng strong encapsulation đối với các thành phần nội bộ. Chạy:

~~~shell
jdeps --jdk-internals --recursive path/to/application.jar
~~~

Khai báo class path/module path cho dependency nếu cần mở rộng phạm vi phân tích. jdeps là phân tích tĩnh nên có thể bỏ sót reflection với tên lớp tạo động, native code và dependency không nằm trong phạm vi quét. Hãy kết hợp với integration test trên JDK 17 và log runtime.

## 12. Kiểm tra cấu hình CI, container và IDE

### 12.1. CI phải dùng cùng JDK và wrapper

Pipeline cần:

- Cài JDK 17 distribution đã được tổ chức phê duyệt.
- Gọi ./gradlew hoặc ./mvnw, không dùng build tool global không kiểm soát.
- Chạy compiler và test bằng JDK/toolchain được khai báo.
- Cache dependency theo wrapper và không tái sử dụng cache sai môi trường.
- Chạy unit test, integration test, packaging và smoke test.
- Lưu lại phiên bản JDK/build tool trong log build.

Ví dụ các bước kiểm tra tổng quát:

~~~shell
java -version
./gradlew --version
./gradlew clean test
./gradlew check
~~~

Hoặc Maven:

~~~shell
java -version
./mvnw -version
./mvnw clean verify
~~~

### 12.2. Container image

Kiểm tra cả JDK/JRE trong image build và image runtime. Multi-stage Docker build có thể dùng JDK 17 để compile nhưng vô tình copy artifact sang image runtime với JRE thấp hơn hoặc khác vendor.

Ví dụ:

~~~dockerfile
FROM eclipse-temurin:17-jdk AS build
WORKDIR /workspace
COPY . .
RUN ./gradlew clean build

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/build/libs/app.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

Tag image ở đây là ví dụ. Trong production, hãy pin image digest hoặc tag patch cụ thể theo quy trình cập nhật bảo mật của tổ chức, và giữ build/runtime vendor cùng chính sách hỗ trợ khi cần.

### 12.3. IDE

Đặt:

- Project SDK/language level phù hợp Java 17.
- Gradle JVM hoặc Maven runner JDK phù hợp với build tool.
- Compiler/toolchain giống cấu hình dự án.
- Annotation processor và plugin IDE ở phiên bản tương thích.

Nếu build từ terminal thành công nhưng IDE báo lỗi, kiểm tra JDK mà IDE dùng để chạy Gradle/Maven và cấu hình annotation processing. Ngược lại, nếu IDE build được nhưng CI lỗi, kiểm tra wrapper, toolchain provisioning, environment variables và phiên bản plugin trên runner.

## 13. Những lỗi phổ biến khi nâng lên JDK 17

| Lỗi/thông báo | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Unsupported class file major version 61 | Bytecode parser/plugin cũ không hiểu Java 17 class file. | Nâng ASM/Byte Buddy/Javassist hoặc plugin chứa chúng. |
| UnsupportedClassVersionError | Dependency được compile cho JDK mới hơn runtime 17. | Chọn artifact có bytecode tương thích Java 17 hoặc dùng đúng runtime được yêu cầu. |
| invalid target release: 17 | Compiler thực tế quá cũ hoặc build đang chọn nhầm JDK. | Kiểm tra toolchain và compiler executable. |
| InaccessibleObjectException | Thư viện reflection truy cập package/member bị đóng gói. | Nâng thư viện; nếu cần chuyển đổi tạm thời, mở đúng package có kiểm soát và lập kế hoạch loại bỏ. |
| IllegalAccessError | Liên kết tới type/member không còn truy cập được theo module/access rules. | Xác định module/package, cập nhật dependency hoặc module descriptor. |
| NoSuchMethodError | Phiên bản dependency runtime khác version mà plugin/framework mong đợi. | Xem dependency tree, BOM và classloader; đồng bộ version. |
| NoClassDefFoundError | Thiếu class hoặc lỗi khởi tạo class trước đó. | Đọc nguyên nhân đầu tiên trong log, kiểm tra runtime dependency và JDK-specific code path. |
| Lombok/processor lỗi khi compile | Processor cũ phụ thuộc javac internals hoặc chưa hỗ trợ JDK 17. | Nâng processor và cấu hình lại processor path. |
| Test không được phát hiện | Surefire/Failsafe/provider hoặc JUnit engine không tương thích. | Kiểm tra plugin version, engine và test discovery. |
| Coverage report lỗi | JaCoCo/ASM cũ không hiểu class file hoặc instrumentation mới. | Nâng JaCoCo và plugin/agent đồng bộ. |
| Build terminal và IDE khác kết quả | Dùng JVM, toolchain, wrapper hoặc annotation processor khác nhau. | Đồng bộ JDK và cấu hình build. |
| App chạy local nhưng lỗi trong container | Runtime image dùng JRE/JDK khác hoặc thiếu native dependency. | Kiểm tra image thực tế, java -version, module và thư viện native. |

### 13.1. Không dùng --add-opens để che mọi lỗi

--add-opens có thể giúp một số thư viện cũ tiếp tục deep reflection trong giai đoạn chuyển đổi. Nhưng nó không:

- Làm cho bytecode cũ hiểu class file mới.
- Sửa UnsupportedClassVersionError.
- Khắc phục dependency version conflict.
- Biến JDK internal API thành API được hỗ trợ.
- Sửa mọi trường hợp thiếu module readability hoặc native access.

Nếu cần mở package tạm thời, ghi rõ module/package/consumer, giới hạn phạm vi và theo dõi issue nâng thư viện. Giải pháp lâu dài là dùng phiên bản thư viện hỗ trợ JDK 17.

## 14. Quy trình nâng cấp theo từng bước

Một lộ trình có kiểm soát giúp dễ xác định thay đổi nào gây lỗi:

### Bước 1: Chụp hiện trạng

Ghi phiên bản JDK, Maven/Gradle, wrapper, plugin, framework, test framework, annotation processor, agents và dependency tree. Lưu log build hiện tại làm baseline.

### Bước 2: Nâng build tool và wrapper

Chọn phiên bản Gradle/Maven được hỗ trợ trên JDK 17 và tương thích với plugin/framework. Pin wrapper và kiểm tra build tool khởi động trước khi thay đổi nhiều dependency.

### Bước 3: Chuyển compiler sang Java 17

Cấu hình toolchain JDK 17 và --release 17. Xác nhận source, test source, generated source và module đều compile đúng release.

### Bước 4: Nâng build plugins

Ưu tiên compiler, test, Javadoc, coverage, code quality, packaging, shading, enhancement và plugin triển khai. Kiểm tra từng plugin chạy trong JVM nào và hỗ trợ JDK 17 ra sao.

### Bước 5: Nâng test stack và annotation processors

Đồng bộ JUnit/TestNG, engine, Surefire/Failsafe hoặc Gradle Test; nâng Lombok/MapStruct và processor khác; chạy test nhỏ trước để phát hiện lỗi compile/test discovery.

### Bước 6: Nâng bytecode libraries và agents

Rà soát ASM, Byte Buddy, Javassist, JaCoCo, mocking framework, APM/security agent và công cụ instrument. Kiểm tra cả dependency bắc cầu và plugin classpath.

### Bước 7: Nâng framework và runtime dependencies

Đọc compatibility matrix của framework, database driver, ORM, messaging, web server, logging và cloud SDK. Xử lý breaking changes theo từng major release.

### Bước 8: Chạy build/test trên JDK 17

Chạy clean build, unit test, integration test, coverage, packaging, smoke test và kiểm tra dependency. Không chỉ chạy compile.

### Bước 9: Kiểm tra image và môi trường triển khai

Đảm bảo container/VM chạy JDK 17 phù hợp, startup command, agents, module flags, native library và biến môi trường đều được cập nhật.

### Bước 10: Chạy thử dưới tải và theo dõi

Đối chiếu startup time, memory, GC, latency, throughput, lỗi kết nối và log. Chỉ chuyển hoàn toàn sau khi các luồng nghiệp vụ quan trọng được xác minh trên môi trường gần production.

## 15. Ma trận tương thích mẫu

Bảng dưới đây là các mốc tham khảo được công bố; chúng không thay thế compatibility matrix của đúng phiên bản dự án:

| Thành phần | Mốc hỗ trợ JDK 17 được ghi nhận | Ghi chú |
| --- | --- | --- |
| Gradle | 7.3 | Phiên bản đầu tiên chạy Gradle trên JDK 17; Gradle 9 yêu cầu JDK 17 làm runtime tối thiểu. |
| Maven Compiler Plugin | 3.16.0 là ví dụ hiện hành | Cấu hình release=17; pin plugin version. |
| JUnit 5 | Java 8+ | Có thể tiếp tục dùng trên JDK 17. |
| JUnit 6 | Java 17+ | Chọn khi đã sẵn sàng migration major. |
| Lombok | 1.18.22 | Mốc đầu tiên công bố JDK 17 support; dùng bản maintained hiện tại. |
| ASM | 9.1 | Mốc hỗ trợ JDK 17; nâng cùng thư viện sử dụng ASM. |
| Byte Buddy | 1.10.19 | Mốc hỗ trợ class file Java 17; kiểm tra version bắc cầu. |
| JaCoCo | 0.8.8 | Mốc đầu tiên chính thức hỗ trợ Java 17; ưu tiên bản maintained mới hơn. |
| Spring Boot | 3.0+ | Java 17 là baseline của dòng 3; dòng mới có build tool requirements riêng. |

Khi chọn version:

1. Ưu tiên bản stable còn được duy trì.
2. Kiểm tra JDK runtime tối thiểu và tối đa được hỗ trợ.
3. Kiểm tra Gradle/Maven plugin compatibility.
4. Kiểm tra dependency tree và BOM.
5. Đọc release notes/migration guide cho major changes.
6. Xác nhận bằng build/test trên JDK 17 thực tế.

Không nên nâng tất cả dependency lên latest cùng lúc nếu dự án có nhiều framework lớn. Hãy nâng theo nhóm có quan hệ phụ thuộc và giữ lại thông tin version trước/sau để dễ rollback.

## 16. Lệnh kiểm tra tổng hợp

### Gradle

~~~shell
java -version
./gradlew --version
./gradlew javaToolchains
./gradlew buildEnvironment
./gradlew dependencies
./gradlew clean check
./gradlew test
~~~

### Maven

~~~shell
java -version
./mvnw -version
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw clean verify
~~~

### Kiểm tra bytecode và JDK internals

~~~shell
javap -verbose -classpath path/to/library.jar com.example.SomeClass
jdeps --multi-release 17 --jdk-internals --recursive path/to/application.jar
~~~

Nếu dependency nằm ngoài JAR đầu vào, bổ sung --class-path hoặc --module-path phù hợp. jdeps không thay thế runtime tests, đặc biệt với reflection và dynamic class loading.

## 17. Những sai lầm thường gặp

| Sai lầm | Vì sao không đủ | Cách làm đúng |
| --- | --- | --- |
| Chỉ đổi JAVA_HOME | IDE, daemon, toolchain và test fork có thể dùng JDK khác. | Kiểm tra JVM từng giai đoạn và cấu hình toolchain. |
| Chỉ nâng Gradle/Maven | Plugin hoặc dependency bắc cầu vẫn có thể không tương thích. | Rà soát toàn build/plugin/dependency graph. |
| Chỉ đặt source/target 17 | Không khóa tập Java SE APIs của release đích. | Dùng --release 17. |
| Chỉ compile thành công | Runtime library, reflection, agent và native integration có thể lỗi. | Chạy test, integration, packaging và smoke test. |
| Nâng mọi thư viện lên latest không theo kế hoạch | Major versions có thể phá API hoặc kéo theo thay đổi khác. | Nâng theo nhóm, dùng BOM và migration guide. |
| Chỉ xem direct dependencies | Dependency bắc cầu có thể chứa ASM/Byte Buddy cũ. | Kiểm tra dependency tree và plugin classpath. |
| Nghĩ JUnit phải lên major 6 | JUnit 5 vẫn chạy trên JDK 17. | Chỉ nâng JUnit 6 khi dự án sẵn sàng baseline Java 17 và breaking changes. |
| Dùng --add-opens như giải pháp chung | Không sửa class-file, API hay version conflicts. | Nâng thư viện và mở package chỉ trong trường hợp chuyển đổi có kiểm soát. |
| Không pin plugin version | Build có thể thay đổi khi parent/tool version thay đổi. | Quản lý plugin version tập trung và dùng wrapper. |
| Bỏ qua IDE/CI/container | Môi trường local có thể khác production. | Dùng cùng JDK, wrapper, toolchain và image policy. |

## 18. Câu hỏi thường gặp

**Có bắt buộc dùng Gradle 7.3 trở lên để build Java 17 không?**  
Nếu muốn chạy chính Gradle trên JDK 17, 7.3 là phiên bản đầu tiên hỗ trợ. Plugin/framework cụ thể có thể yêu cầu Gradle mới hơn; hãy kiểm tra compatibility matrix của chúng.

**Maven có cần nâng major version chỉ để chạy JDK 17 không?**  
Không nhất thiết. Maven 3.9.x có thể chạy trên JDK 17. Điều quan trọng là dùng wrapper, compiler plugin tương thích, cấu hình release=17 và nâng các plugin khác theo yêu cầu.

**Dùng JDK 17 compile nhưng muốn output chạy trên Java 11 được không?**  
Có thể dùng toolchain JDK 17 kết hợp --release 11. Nhưng nếu mục tiêu của dự án là Java 17, hãy đặt release 17 để sử dụng đúng API và language features của nền tảng đích.

**Có phải nâng JUnit 5 lên JUnit 6?**  
Không. JUnit 5 yêu cầu Java 8 trở lên nên chạy được trên JDK 17. JUnit 6 có baseline Java 17 và có breaking changes; chỉ nâng khi muốn chuyển sang major mới.

**Tại sao Mockito hoặc coverage agent lỗi dù ứng dụng compile được?**  
Mocking và coverage thường instrument bytecode trong JVM test. Hãy kiểm tra Byte Buddy, ASM, JaCoCo, test plugin và agent version.

**Tại sao build chạy được trên máy developer nhưng CI lỗi?**  
Có thể khác JDK của Gradle/Maven runtime, toolchain, wrapper, plugin cache, dependency resolution, environment variables hoặc container image. In version của từng thành phần trong CI để tìm khác biệt.

**Có thể dùng sourceCompatibility và targetCompatibility thay --release không?**  
Hai thuộc tính đó không bảo đảm tập Java SE APIs của release đích. Với JDK 9 trở lên, ưu tiên --release để khóa cả ngôn ngữ, bytecode và API nền tảng.

**Một thư viện ghi “Java 17 compatible” có đủ để kết luận không?**  
Chưa đủ. Kiểm tra version bytecode, runtime minimum, dependency bắc cầu, module/reflection, native library, framework matrix và release notes. Sau đó chạy integration tests trên JDK 17.

## 19. Tài liệu tham khảo chính thức

- [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): phiên bản Java được hỗ trợ để chạy Gradle và dùng Java toolchains.
- [Gradle Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): cấu hình JDK cho compile, test và Javadoc; phân biệt toolchain với JVM chạy Gradle.
- [Gradle Building Java Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): cấu hình Java release và compiler compatibility.
- [Apache Maven — Guide to Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html): cấu hình maven.compiler.release và --release.
- [Apache Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/): version, cấu hình compiler và system requirements.
- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html): chọn JDK độc lập với JVM chạy Maven.
- [Apache Maven Surefire — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html): tích hợp test engine với Surefire.
- [JUnit 6 Release Notes](https://docs.junit.org/6.0.3/release-notes.html): Java 17 baseline và các thay đổi khi chuyển từ JUnit 5.
- [JaCoCo Change History](https://www.jacoco.org/jacoco/trunk/doc/changes.html): các mốc hỗ trợ class file/JDK và thay đổi của coverage tool.
- [ASM Versions](https://asm.ow2.io/versions.html): lịch sử hỗ trợ class-file version và JDK.
- [Byte Buddy README](https://github.com/raphw/byte-buddy/blob/master/README.md): bảng version hỗ trợ Java class file.
- [Lombok Changelog](https://projectlombok.org/changelog): lịch sử hỗ trợ JDK, bao gồm mốc JDK 17.
- [Spring Boot System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): Java runtime và build tool requirements theo phiên bản Spring Boot.

**Nguyên tắc áp dụng:** Nâng wrapper/build tool trước, cấu hình JDK toolchain và --release 17, rồi nâng compiler/test plugins, annotation processors, bytecode tools, framework và runtime dependencies theo compatibility matrix của từng thành phần. Kiểm tra dependency bắc cầu, CI, IDE và container; cuối cùng chạy đầy đủ build, test và smoke test trên JDK 17.
