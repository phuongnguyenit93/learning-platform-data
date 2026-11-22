# Nhập dự án Spring Boot vào IDE và xác định cấu hình build có hiệu lực

## 1. Mục tiêu và vấn đề cần hiểu

Sau khi tạo hoặc nhận một dự án Spring Boot, việc mở được thư mục mã nguồn trong IDE chưa đồng nghĩa với việc IDE đã nhập đúng mô hình build. Bài này hướng dẫn cách nhận diện dự án Maven/Gradle, nhập dự án vào IntelliJ IDEA, Eclipse/Spring Tools hoặc VS Code, và tìm ra cấu hình **thực sự được áp dụng** khi biên dịch, kiểm thử, đóng gói.

Sau bài học, bạn có thể:

- Xác định thư mục gốc cần nhập, build tool, wrapper, các module và JDK cần dùng.
- Phân biệt cấu hình khai báo trong tệp với cấu hình đã được kết hợp, kích hoạt và giải quyết phụ thuộc.
- Kiểm tra Maven effective POM, active profiles, dependency tree; hoặc Gradle project model, task và dependency graph.
- Đối chiếu cấu hình trong IDE với lệnh build chuẩn của dự án, phát hiện nguyên nhân khác biệt về Java, plugin, profile, repository và thư viện.
- Xác nhận dự án có thể build và tạo đúng loại artifact trước khi bắt đầu phát triển tính năng.

**Nguyên tắc:** tệp cấu hình build cùng wrapper và cách gọi build của dự án là nguồn để xác minh. Các tùy chọn IDE là một phần của môi trường thực thi và có thể tạo ra khác biệt nếu không được đồng bộ.

## 2. Nhận diện dự án và chọn đúng thư mục gốc

Trước khi import, quan sát các tệp ngay trong thư mục nhận từ Git hoặc công cụ khởi tạo Spring Boot:

| Dấu hiệu | Maven | Gradle |
| --- | --- | --- |
| Tệp cấu hình dự án | pom.xml | build.gradle hoặc build.gradle.kts |
| Khai báo các project/module tham gia build | pom.xml của aggregator và các khai báo modules | settings.gradle hoặc settings.gradle.kts, thường chứa include |
| Wrapper trên Linux/macOS | mvnw | gradlew |
| Wrapper trên Windows | mvnw.cmd | gradlew.bat |
| Cấu hình wrapper | .mvn/wrapper/ | gradle/wrapper/ |
| Phụ thuộc đã tải về | Maven local repository, thường ở ~/.m2/repository | Gradle cache, thường ở ~/.gradle/caches |
| Kết quả build thông dụng | target/ | build/ |

**Wrapper** là script của dự án để chọn đúng phiên bản Maven/Gradle đã chuẩn bị. Ưu tiên wrapper nếu repository có cung cấp và script hoạt động; lệnh mvn hoặc gradle cài toàn máy có thể dùng phiên bản khác. Wrapper không tự chọn đúng JDK cho mọi trường hợp: phải kiểm tra JDK riêng.

Với **dự án một module**, nhập thư mục chứa pom.xml hoặc settings.gradle(.kts)/build.gradle(.kts). Với **dự án nhiều module**, thường cần nhập thư mục gốc của Maven reactor hoặc Gradle root build để giữ liên kết các module, dependency substitution và tác vụ liên quan. Nếu repository có cả Maven và Gradle, hãy xem README hướng dẫn chạy hoặc cấu hình CI của chính repository để chọn hệ build được duy trì; không tự giả định cả hai cùng là nguồn build chuẩn.

Ví dụ cấu trúc tối giản:

~~~text
demo/
├── pom.xml                  # Dự án Maven
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/
└── src/main/java/...
~~~

Hoặc:

~~~text
demo/
├── settings.gradle          # Gradle root project
├── build.gradle             # Gradle Groovy DSL
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
└── src/main/java/...
~~~

Một dự án Gradle dùng Kotlin DSL sẽ có settings.gradle.kts và build.gradle.kts. Hai cú pháp Groovy và Kotlin DSL có ý nghĩa tương tự trong nhiều trường hợp, nhưng không được sao chép nguyên cú pháp của ngôn ngữ này sang tệp ngôn ngữ kia.

## 3. Chuẩn bị môi trường trước khi import

1. Kiểm tra nhánh Git và thư mục root; đọc phiên bản Java, Maven/Gradle và Spring Boot đã khai báo trong build.
2. Cài JDK phù hợp với phiên bản Spring Boot và plugin của dự án. Phân biệt **JDK chạy Maven/Gradle**, **JDK/toolchain dùng biên dịch**, và **JDK chạy ứng dụng**: ba giá trị có thể khác nhau.
3. Chạy lệnh kiểm tra trên terminal tại đúng root. Trên Linux/macOS:

~~~bash
java -version
./mvnw -version
# Hoặc, với dự án Gradle:
./gradlew --version
~~~

Trên Windows PowerShell:

~~~powershell
java -version
.\mvnw.cmd -version
# Hoặc:
.\gradlew.bat --version
~~~

Chỉ chạy lệnh của **build tool thực tế**. Nếu wrapper không tồn tại, dùng mvn -version hoặc gradle --version sau khi xác minh phiên bản cài sẵn phù hợp. Trên Linux/macOS, nếu script chưa có quyền chạy, kiểm tra executable bit từ Git trước khi điều chỉnh quyền theo quy trình dự án.

4. Đảm bảo có kết nối đến repository được phép (Maven Central, repository nội bộ, proxy/mirror nếu có). Lần import đầu có thể cần tải Gradle distribution, plugin và thư viện.
5. Nếu dùng repository chưa tin cậy, xem lại build scripts trước khi cho IDE tự động sync hoặc chạy task: build scripts và plugin có thể thực thi mã.

Đừng kết luận dự án lỗi chỉ vì IDE báo đỏ ngay khi vừa mở. Các công cụ import có thể chưa tải xong dependency, chưa chọn đúng JDK, hoặc chưa hoàn tất indexing; xem lỗi cụ thể của quá trình sync trước.

## 4. Import trong các IDE phổ biến

### 4.1. IntelliJ IDEA

- Chọn **File → Open**, mở **thư mục root** của dự án; khi được hỏi, xác nhận mở như Maven/Gradle project. Nếu chỉ đang mở tệp riêng lẻ, dùng chức năng thêm Maven/Gradle project từ pom.xml hoặc build.gradle(.kts).
- Đợi Maven/Gradle sync. Kiểm tra **Project Structure → Project SDK** và JDK cho module; với Gradle còn kiểm tra **Settings → Build, Execution, Deployment → Build Tools → Gradle → Gradle JVM**, ưu tiên phân phối từ wrapper. Tên menu có thể khác nhẹ theo phiên bản IDE.
- Với Maven, kiểm tra Maven home/wrapper, user settings, local repository và các profile đang bật trong cửa sổ Maven.
- Với Gradle, mở công cụ Gradle để thấy root, subprojects, tasks. Kiểm tra tùy chọn IDE dùng **Gradle** hay IntelliJ để build/run; lựa chọn này có thể khiến kết quả chạy trong IDE khác lệnh ./gradlew.
- Dùng **Reload All Maven Projects** hoặc **Reload All Gradle Projects** sau khi thay đổi tệp build; chỉ xóa cache/reimport toàn bộ khi sync cụ thể không thể phục hồi bằng reload thông thường.

### 4.2. Eclipse / Spring Tools (STS)

- Maven: **File → Import → Maven → Existing Maven Projects**, chọn root chứa pom.xml, xác nhận các module được phát hiện. Maven integration thường là m2e.
- Gradle: **File → Import → Gradle → Existing Gradle Project** (Buildship), chọn Gradle root và thiết lập Java/Gradle distribution phù hợp.
- Kiểm tra **Installed JREs / Execution Environment**, Java compiler compliance và classpath của project. Với Maven, sử dụng **Maven → Update Project** khi POM đổi; với Gradle, dùng **Refresh Gradle Project**.
- Nếu project vẫn báo lỗi, xem **Problems**, **Maven/Gradle Console** và quá trình tải dependency trước khi sửa thủ công Build Path; chỉnh trực tiếp classpath sinh từ build tool thường bị ghi đè khi refresh.

### 4.3. Visual Studio Code

- Cài JDK và các extension Java phù hợp, thường là **Extension Pack for Java**, cùng **Spring Boot Extension Pack** nếu cần tính năng Spring Boot.
- Dùng **File → Open Folder** trên root. Để extension nhận diện pom.xml hoặc Gradle build, chờ **Java Projects**, **Maven for Java** hoặc **Gradle for Java** hoàn tất import.
- Chọn Java runtime cho workspace và JDK mà extension/build tool sẽ chạy. Xem **Output** của Java/Maven/Gradle và **Problems** nếu import lỗi.
- Sau khi đổi build files, refresh project/dependencies bằng lệnh tương ứng của extension. Với build phức tạp, terminal chạy wrapper là điểm đối chiếu đáng tin cậy để biết IDE có thực hiện cùng cấu hình hay không.

**Điểm chung của cả ba IDE:** việc source folder được tô màu đúng hoặc class có nút Run không chứng minh build đã đồng nhất. Bằng chứng mạnh hơn là wrapper thực hiện được cùng tác vụ với cùng biến môi trường, JDK, profile/properties và dependency resolution.

## 5. “Cấu hình build có hiệu lực” nghĩa là gì?

Cấu hình bạn nhìn thấy trong một file chỉ là **đầu vào**. Khi chạy build, công cụ còn kết hợp kế thừa, plugin, cấu hình của module cha, cài đặt người dùng/máy, biến môi trường, tùy chọn dòng lệnh và quá trình chọn phiên bản dependency. Vì vậy cần trả lời ba câu hỏi riêng:

1. **Mô hình dự án sau cấu hình là gì?** Group/artifact/version, module, plugin, task/goal, Java target, repository, active profile hoặc property nào đang áp dụng?
2. **Các phiên bản thư viện thực tế nào được chọn?** Phiên bản khai báo có thể khác phiên bản được quản lý từ BOM, bị thay bởi rule hoặc được chọn qua giải quyết xung đột transitive dependency.
3. **Điều gì thực sự chạy?** Wrapper nào, JVM nào, task/goal nào, thông số chạy nào và artifact đầu ra nào?

Không có một màn hình IDE nào trả lời đầy đủ cả ba câu hỏi. Cần phối hợp inspection trong IDE và báo cáo trực tiếp từ Maven/Gradle.

### 5.1. Maven: effective POM và dependency tree

Với Maven, mô hình có hiệu lực kết hợp pom.xml hiện tại, parent POM, Super POM, dependencyManagement, pluginManagement và các profile đang kích hoạt. Settings ở user/global level và tùy chọn lệnh có thể ảnh hưởng đến repository, mirror, credential, profile và cách thực thi. BOM Spring Boot quản lý nhiều phiên bản thư viện, nhưng nó **không** biến mọi dependency transitive thành dependency trực tiếp trong POM.

Ví dụ **POM minh họa** cho một module Spring Boot (phiên bản là ví dụ cụ thể, phải tuân theo phiên bản được dự án chọn):

~~~xml
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
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
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

Ở đây, dependency spring-boot-starter-web không khai báo version trong phần dependencies vì parent/BOM cung cấp quản lý phiên bản. Điều đó không có nghĩa toàn bộ bản đồ dependency đã hiển thị trong POM gốc. Muốn xem kết quả thực tế, chạy trong root Maven:

~~~bash
./mvnw -version
./mvnw help:active-profiles
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
./mvnw help:effective-settings
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.springframework:spring-core
./mvnw test
~~~

Ý nghĩa của từng lệnh:

- **-version:** phiên bản Maven và Java runtime dùng để khởi động Maven; chưa chắc là release của bytecode.
- **help:active-profiles:** những profile Maven thực sự được kích hoạt bởi POM, settings, environment/activation và tham số lệnh.
- **help:effective-pom:** POM sau kế thừa, profile và quản lý cấu hình; phù hợp để tìm Java properties, plugin version/goal hoặc repository được áp dụng. File target/effective-pom.xml là **kết quả chẩn đoán**, không nên chỉnh thay pom.xml.
- **help:effective-settings:** cài đặt Maven đã kết hợp, hữu ích khi kiểm tra mirror và repository; cần tránh công bố bí mật/credential từ log hoặc cấu hình.
- **dependency:tree:** đồ thị dependency đã giải quyết, bao gồm transitive dependency và phiên bản được chọn; bộ lọc includes giúp truy nguyên một thư viện.
- **test:** kiểm tra compile/test theo lifecycle Maven với cấu hình hiện hành; kết quả phụ thuộc mã và môi trường thực tế.

Đối với profile riêng, chạy lại cả lệnh chẩn đoán và build với đúng lựa chọn, chẳng hạn:

~~~bash
./mvnw -Pdev help:active-profiles
./mvnw -Pdev help:effective-pom -Doutput=target/effective-dev.xml
./mvnw -Pdev test
~~~

**Chỉ dùng -Pdev khi project có profile dev hợp lệ.** Đối chiếu profile IntelliJ/Eclipse đang kích hoạt với profile dòng lệnh. Ngoài POM, Maven còn có .mvn/maven.config, .mvn/jvm.config, settings.xml (thường trong ~/.m2), Maven toolchains và các tham số -D có thể thay đổi kết quả; hãy đọc đúng nguồn được dự án sử dụng khi điều tra mismatch.

### 5.2. Gradle: mô hình đã evaluate và dependency resolution

Gradle không có một file “effective POM” tương đương. Mô hình sau cấu hình đến từ settings.gradle(.kts), build.gradle(.kts) ở root/subproject, plugin và convention plugin, init scripts, gradle.properties, version catalogs, project properties và các task được chọn. Sau đó Gradle giải quyết phiên bản/phụ thuộc theo từng **configuration** (ví dụ compileClasspath hoặc runtimeClasspath).

Một build.gradle Groovy DSL **minh họa** cho Spring Boot:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Ví dụ settings.gradle đi kèm:

~~~groovy
rootProject.name = 'demo'
~~~

Plugin Spring Boot cung cấp task đặc thù như bootJar; trong ví dụ có thêm io.spring.dependency-management để dependency versions được quản lý theo BOM Spring Boot. **Chỉ áp dụng plugin Spring Boot không tự động có nghĩa tất cả starter dependency đều được quản lý version**; dự án cũng có thể chọn cách khác là khai báo Gradle platform/enforcedPlatform cho BOM. Không được bỏ qua cơ chế quản lý version thực tế trong build.

Để xem cấu hình hiệu lực, chạy từ Gradle root:

~~~bash
./gradlew --version
./gradlew projects
./gradlew tasks --all
./gradlew properties
./gradlew javaToolchains
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
./gradlew test
~~~

Diễn giải:

- **--version:** Gradle distribution và JVM chạy Gradle.
- **projects:** root/subprojects mà settings đã đưa vào build (quan trọng trong multi-module).
- **tasks --all:** các task Gradle đã khai báo hoặc sinh bởi plugin; thấy bootJar không có nghĩa task chắc chắn chạy thành công.
- **properties:** thuộc tính project đã evaluate; thận trọng vì properties hoặc log plugin có thể lộ thông tin nội bộ.
- **javaToolchains:** các toolchain Java Gradle phát hiện; kiểm tra JVM dùng compile khác JVM chạy daemon hay không.
- **dependencies:** dependency graph của configuration được chọn; tên configuration có thể khác ở project/plugin khác.
- **dependencyInsight:** tại sao một phiên bản module được chọn, rule/constraint hay dependency nào dẫn đến lựa chọn đó.
- **test:** chạy thử task kiểm thử với cấu hình thực tế.

Trong multi-project Gradle, chọn đúng subproject nếu cấu hình không có ở root:

~~~bash
./gradlew :service:dependencies --configuration runtimeClasspath
./gradlew :service:dependencyInsight --dependency spring-core --configuration runtimeClasspath
./gradlew :service:test
~~~

Các lệnh trên chỉ dùng khi project thật có module tên service. Đừng nhầm **Gradle project property** (ví dụ -Penv=dev trong build script có xử lý) với **Maven profile**: Gradle không tự cung cấp cơ chế Maven profiles. Hãy xem plugin/build logic đang đọc property hoặc environment nào, và truyền đúng chúng vào lần chạy so sánh.

Ngoài các file trong repository, Gradle có thể đọc user-level gradle.properties, init scripts, environment variables và tham số -P/-D; vì vậy hai máy có cùng build.gradle vẫn có thể chạy khác nhau. Version catalog trong gradle/libs.versions.toml quản lý alias/version theo cấu hình dự án, nhưng phiên bản thực sự được chọn vẫn phải kiểm qua dependency graph.

## 6. Xác định đúng phiên bản Java và cấu hình compiler

Ba khái niệm dễ bị nhầm:

| Thành phần | Câu hỏi xác minh | Nơi kiểm tra |
| --- | --- | --- |
| JVM chạy IDE | IDE đang mở bằng Java nào? | About/Runtime của IDE |
| JVM chạy build tool | Maven/Gradle daemon/client chạy Java nào? | ./mvnw -version hoặc ./gradlew --version; Gradle JVM trong IDE |
| Java dùng để biên dịch | Compiler/toolchain phát ra bytecode phiên bản nào? | maven-compiler-plugin release/source/target hoặc Gradle java.toolchain/options.release |

Ví dụ Gradle daemon chạy JDK 21 trong khi java.toolchain đặt 17: mã có thể được biên dịch bằng compiler JDK 17. Tương tự Maven chạy bằng JDK 21 nhưng cấu hình maven.compiler.release=17 có thể tạo class tương thích Java 17 (với API check của --release). Ngược lại, chỉ đặt “Project SDK=17” trong IDE **không bảo đảm** wrapper ngoài terminal cũng chạy JDK 17.

Nếu dự án Spring Boot yêu cầu Java 17 nhưng terminal vẫn dùng Java 11, import/build có thể thất bại vì plugin hoặc class file cần runtime mới hơn. Kiểm tra JAVA_HOME, PATH, IDE Gradle JVM/Maven runner, Gradle toolchain hay Maven toolchains.xml tùy dự án; không sửa mỗi “language level” rồi coi như đã giải quyết.

Để xác nhận chính xác bytecode của class sau build, có thể dùng javap trên class đã biên dịch:

~~~bash
javap -verbose -classpath target/classes com.example.demo.DemoApplication
# Với Gradle, thường là:
javap -verbose -classpath build/classes/java/main com.example.demo.DemoApplication
~~~

Chỉ dùng ví dụ trên khi class thực tế có tên com.example.demo.DemoApplication và đường dẫn output như đã nêu; tìm dòng **major version**. Chẳng hạn major 61 tương ứng Java 17, major 65 tương ứng Java 21. Sự tương thích chạy chương trình còn phụ thuộc dependency và JVM thực tế.

## 7. Đối chiếu build trong IDE với terminal

Một cách làm có thể lặp lại:

1. **Chọn baseline:** xác định root, nhánh Git, wrapper, JDK, profile/properties và lệnh mà CI hoặc nhóm đang dùng.
2. **Chạy build qua wrapper ngoài IDE:** Maven dùng ./mvnw test hoặc ./mvnw package; Gradle dùng ./gradlew test hoặc ./gradlew build. Ghi nhận task/goal thất bại đầu tiên và nguyên nhân chi tiết.
3. **Lấy mô hình hiệu lực:** Maven effective POM + active profiles + dependency tree; Gradle projects/tasks/properties + dependencyInsight của thư viện đang nghi vấn.
4. **Đối chiếu màn hình IDE:** project/module import, Gradle JVM/Maven runner, selected profiles, offline mode, settings.xml/Gradle user home, build delegation, run configuration.
5. **Sync lại build project**, rồi chạy **cùng** goal/task với cùng JDK và tham số trong IDE. Không sửa source để che lỗi dependency trước khi xác định nguyên nhân.
6. **Kiểm tra kết quả:** compilation/test thành công và artifact đúng loại nếu bài toán yêu cầu packaging; nếu IDE và CLI khác nhau, giữ log lệnh, phiên bản Java/build tool và tọa độ dependency được chọn để chứng minh sai khác.

Ví dụ thực tế: pom.xml của một project Spring Boot dùng Java 17, nhưng IntelliJ mở root bằng JDK 21 và Maven chạy bằng JDK 11. Nếu Maven plugin báo không hỗ trợ runtime Java 11, lỗi nằm ở JVM **khởi động Maven**, dù IDE báo Project SDK 21. Sửa JDK cho Maven runner/JAVA_HOME về phiên bản được dự án hỗ trợ, kiểm tra ./mvnw -version rồi reload. Nếu vẫn có version conflict, dùng dependency:tree để kiểm tra dependency được chọn.

Ví dụ khác: build.gradle yêu cầu plugin Spring Boot theo phiên bản wrapper đã chọn nhưng IDE dùng Gradle local cũ. Sync IDE báo lỗi plugin, còn ./gradlew projects chạy thành công. Chuyển IDE sang Gradle Wrapper rồi sync lại; nếu hai bên đã dùng cùng wrapper/JDK mà kết quả vẫn khác, kiểm tra init scripts, gradle.properties và task/arguments.

## 8. Build thành công có tạo đúng Spring Boot artifact không?

**Compile/test**, **jar thường** và **executable Spring Boot jar** là những kết quả khác nhau.

- Maven: lifecycle package tạo artifact dựa trên packaging và các plugin đã cấu hình. Với spring-boot-maven-plugin được tích hợp đúng, mục tiêu repackage có thể biến JAR thành executable Spring Boot archive. Kiểm tra cấu hình plugin/effective POM và file trong target/.
- Gradle: khi plugin org.springframework.boot cùng Java plugin được áp dụng phù hợp, thường có bootJar để tạo executable JAR; task jar thông thường vẫn có mục đích khác. Xem task thực tế và file trong build/libs/ của đúng subproject.
- Nếu build module là **library**, đừng tự áp dụng kỳ vọng có bootJar; packaging phải tuân theo vai trò module và task/lifecycle đã khai báo.

Lệnh kiểm tra khi module có entrypoint Spring Boot hợp lệ:

~~~bash
# Maven:
./mvnw package

# Gradle:
./gradlew bootJar
~~~

Không gộp hai lệnh cho cùng dự án. Kiểm tra log goal/task và artifact được tạo; tên file phụ thuộc group, project name, version, classifier và cấu hình build. Một script build mẫu chưa có lớp main Spring Boot thì task đóng gói executable có thể thất bại dù import và dependency resolution hoàn toàn đúng.

## 9. Các lỗi thường gặp và cách xác minh trước khi sửa

| Triệu chứng | Nguyên nhân có thể | Kiểm tra và cách xử lý |
| --- | --- | --- |
| IDE không thấy module hoặc task | Import nhầm src/ hoặc chỉ nhập subproject thay vì root | Xác nhận root POM/settings, xem Maven projects hoặc ./gradlew projects rồi import lại root |
| IDE đỏ dependency, terminal build được | IDE chưa sync, dùng offline, khác mirror/repository hoặc build tool/JDK | Reload project; so sánh wrapper version, settings.xml, Gradle JVM, repository và log sync |
| Terminal build lỗi nhưng IDE chạy được | IDE compiler và build tool dùng cấu hình khác, cached classes, tham số riêng | Chạy cùng goal/task qua wrapper, cùng profile và JDK; so sánh build delegation |
| “Unsupported class file major version” | JDK/Gradle/plugin/runtime không tương thích với bytecode đang đọc | Đọc major version, xem ./gradlew --version hoặc ./mvnw -version; kiểm tra toolchain/plugin compatibility |
| Version thư viện không giống khai báo | BOM, dependency management, transitive conflict, constraints hoặc resolution rule | Maven dependency:tree; Gradle dependencyInsight theo configuration đúng |
| Plugin/task thiếu | Import sai root, plugin chưa áp dụng vào module, cấu hình lỗi | Maven effective POM hoặc Gradle tasks --all, kiểm tra log plugin resolution |
| Profile hoặc môi trường không tác dụng | Maven profile chưa active; Gradle property không được script đọc; IDE không truyền args | Maven help:active-profiles; kiểm tra xử lý -P/-D và run configuration |
| Tải dependency thất bại | Proxy, mirror, credential, repository, mạng, offline mode | Xem thông báo lỗi repository cụ thể; kiểm tra effective settings/Gradle repositories, tránh đưa secret lên log công khai |
| Có JAR nhưng không chạy bằng java -jar | Tạo plain JAR thay vì bootJar/repackage, thiếu main class hoặc manifest sai | Kiểm tra task/goal, entrypoint Spring Boot và cấu hình packaging |
| Build IDE/CI khác nhau theo máy | Khác JDK, wrapper, user-level properties/settings, environment, cache | Ghi lại version và lệnh tái hiện, chuẩn hóa nguồn cấu hình trong repository/CI |

Không nên xóa toàn bộ ~/.m2 hoặc ~/.gradle như bước đầu tiên. Việc đó có thể gây tải lại lớn mà không giải quyết lỗi phiên bản, profile hay Java. Dùng thông tin từ log và lệnh chẩn đoán để xác định đúng cấu hình trước.

## 10. Bài thực hành có tiêu chí hoàn thành

Chọn một dự án Spring Boot hiện có, thực hiện trên terminal và trong IDE:

1. Xác định dự án Maven hay Gradle; tìm root, wrapper và liệt kê các module.
2. Nhập root vào IDE, đợi sync thành công và ghi lại JDK/Gradle JVM/Maven runtime.
3. Chạy -version bằng wrapper, ghi tên build tool và JDK thực tế.
4. Với Maven, lấy effective POM, active profiles và dependency:tree; với Gradle, xem projects, tasks và runtimeClasspath.
5. Tìm phiên bản thực tế của spring-core (hoặc dependency có trong dự án) cùng nguyên nhân chọn version.
6. Chạy test bằng wrapper, sau đó thử đóng gói đúng cách theo loại module; xác nhận đường dẫn và loại artifact sinh ra.
7. Thử thay một cấu hình hợp lệ theo quy trình nhóm (ví dụ bật Maven profile đã có hoặc property Gradle đã được script hỗ trợ), chạy lại lệnh chẩn đoán và chỉ ra chính xác điều gì thay đổi. Khôi phục cấu hình sau bài thực hành nếu đó chỉ là thử nghiệm.

**Đạt yêu cầu khi:** bạn giải thích được dự án nhập từ root nào, build tool và wrapper dùng phiên bản nào, JDK nào chạy build và JDK nào biên dịch, profile/properties nào đang hiệu lực, thư viện được chọn version ra sao, task/goal nào tạo artifact và IDE có tái hiện được cùng kết quả terminal hay không.

Khi có sai khác, hãy lưu **lệnh đã chạy + điều kiện môi trường + đoạn log lỗi có liên quan**. Đó là bằng chứng giúp sửa đúng nguyên nhân, đồng thời giúp người khác nhập lại dự án và build nhất quán.
