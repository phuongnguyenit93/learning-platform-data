# Nâng Wrapper và kiểm chứng convention plugin hoặc parent POM hiện có

## 1. Mục tiêu và nguyên tắc

Maven Wrapper và Gradle Wrapper cố định phiên bản build tool mà dự án sử dụng. Chúng giúp developer, CI và các máy build khác chạy cùng một phiên bản Maven/Gradle mà không phụ thuộc phiên bản cài toàn cục trên máy. Khi nâng Wrapper, cần kiểm tra thêm lớp cấu hình dùng chung của dự án: convention plugin trong Gradle hoặc parent POM trong Maven. Đây thường là nơi tập trung plugin versions, compiler/toolchain settings, test configuration, dependency management và các quy ước build của nhiều module.

Mục tiêu của quy trình:

- Nâng phiên bản Wrapper có kiểm soát, giữ các file wrapper đồng bộ và xác minh distribution được tải đúng.
- Xác định build dùng Gradle convention plugin hay Maven parent POM, sau đó kiểm chứng đúng cơ chế hiện hữu.
- Phát hiện cấu hình bị trùng, bị override, không còn tương thích hoặc chỉ hoạt động nhờ môi trường máy cá nhân.
- Chạy kiểm thử trên toàn reactor/multi-project build và trên CI bằng chính Wrapper vừa nâng.
- Tách thay đổi Wrapper khỏi thay đổi convention/parent khi có thể để xác định nguyên nhân nếu build hỏng.

**Không nâng phiên bản chỉ vì có bản mới.** Trước tiên xác định Java runtime, Spring Boot, plugin, repository, CI runner và các module đang dùng. Chọn phiên bản đích có hỗ trợ các thành phần đó, sau đó nâng theo từng bước có thể kiểm chứng.

## 2. Wrapper thực sự cố định điều gì?

Wrapper là script khởi chạy build tool đi kèm project. Khi chạy:

~~~bash
./gradlew clean build
~~~

hoặc:

~~~bash
./mvnw clean verify
~~~

script wrapper đọc cấu hình phân phối, tải đúng Maven/Gradle distribution nếu chưa có trong cache, rồi khởi chạy build bằng distribution đó.

| Dự án | File quan trọng | Vai trò |
| --- | --- | --- |
| Gradle | gradlew, gradlew.bat | Script cho Unix-like và Windows |
| Gradle | gradle/wrapper/gradle-wrapper.jar | Mã khởi chạy Wrapper |
| Gradle | gradle/wrapper/gradle-wrapper.properties | Distribution URL, checksum và tùy chọn tải |
| Maven | mvnw, mvnw.cmd | Script cho Unix-like và Windows |
| Maven | .mvn/wrapper/maven-wrapper.properties | Distribution URL và cấu hình Wrapper |
| Maven | .mvn/wrapper/maven-wrapper.jar (nếu loại Wrapper sử dụng file này) | Bootstrap Wrapper |

Wrapper **không tự khóa toàn bộ môi trường build**. Kết quả vẫn có thể khác nếu JDK, environment variables, OS, native libraries, repository content, plugin versions, dependency versions hoặc cấu hình CI khác nhau. Vì vậy phải kiểm chứng cả Wrapper lẫn lớp cấu hình chia sẻ.

Phân biệt hai khái niệm Java quan trọng:

- **JDK chạy build tool:** JVM dùng để chạy Gradle/Maven daemon hoặc process.
- **Java toolchain/compiler target:** JDK/compiler dùng để biên dịch và chạy test của project.

Nâng Gradle/Maven có thể thay đổi JDK tối thiểu cần để chạy build tool. Điều đó không có nghĩa ứng dụng phải đổi Java target cùng lúc. Kiểm tra cả hai yêu cầu riêng biệt.

## 3. Khảo sát trước khi nâng

Trước khi sửa file, ghi nhận trạng thái hiện tại và tạo một baseline có thể so sánh.

### 3.1. Xác định loại build và phạm vi module

Kiểm tra các dấu hiệu trong repository:

| Dấu hiệu | Kết luận thường gặp |
| --- | --- |
| settings.gradle hoặc settings.gradle.kts | Gradle build, có thể là multi-project |
| build.gradle hoặc build.gradle.kts | Gradle project/module |
| build-logic/ hoặc buildSrc/ | Có thể chứa convention plugins hoặc build logic |
| pom.xml ở root với packaging pom | Có thể là Maven aggregator/parent |
| Module POM có parent trỏ về root | Các module kế thừa parent POM nội bộ |
| Parent POM được khai báo qua groupId/artifactId/version | Có thể được tải từ Maven repository |
| .mvn/wrapper hoặc gradle/wrapper | Project đã có Wrapper tương ứng |

Đọc đúng file build và các file được tham chiếu trực tiếp. Với Gradle, tìm plugin được áp dụng bằng ID, pluginManagement, includeBuild, buildSrc và version catalog. Với Maven, xác định parent chain, dependencyManagement, pluginManagement, build/plugins và các module trong reactor.

Không tạo convention plugin mới hoặc parent POM mới nếu dự án đã có cơ chế chia sẻ cấu hình. Mục tiêu của bài là nâng và kiểm chứng cơ chế đang dùng.

### 3.2. Ghi baseline phiên bản

Gradle:

~~~bash
./gradlew --version
~~~

Maven:

~~~bash
./mvnw --version
~~~

Ghi lại:

- Phiên bản Wrapper và phiên bản build tool thực tế.
- JVM được dùng để chạy build tool.
- Java toolchain/release mà project yêu cầu.
- Phiên bản Spring Boot và plugin build quan trọng.
- Các plugin tùy chỉnh hoặc plugin nội bộ.
- Module nào dùng convention plugin/parent POM nào.
- Các lệnh CI đang chạy và profile/environment được bật.

Chạy baseline trước khi nâng:

~~~bash
./gradlew clean check
~~~

hoặc:

~~~bash
./mvnw -B -ntp clean verify
~~~

Nếu baseline đã lỗi, ghi rõ lỗi cũ trước khi thay đổi. Nếu không có baseline, rất khó kết luận lỗi phát sinh do Wrapper hay do cấu hình build vốn đã hỏng.

### 3.3. Kiểm tra compatibility matrix

Đối chiếu ít nhất các quan hệ sau:

1. Gradle/Maven version với JDK dùng để chạy build tool.
2. Spring Boot version với Java version và Gradle/Maven plugin version được hỗ trợ.
3. Convention plugin hoặc parent POM với phiên bản plugin mà nó quản lý.
4. Plugin bên thứ ba với Gradle/Maven API mới.
5. CI runner image với JDK, shell, Docker daemon và tool cần thiết.
6. Repository nội bộ với TLS, authentication, mirror và metadata format.

Đặc biệt, Gradle có hai mốc compatibility khác nhau: JVM chạy Gradle và Java toolchain của ứng dụng. Một Gradle mới có thể yêu cầu JDK mới hơn để chạy, dù project vẫn compile bằng toolchain cũ hơn nếu tổ hợp đó được hỗ trợ.

Với Maven, kiểm tra Maven runtime JDK, Maven Compiler Plugin, Surefire/Failsafe và các plugin đóng gói. Đừng suy ra rằng Maven chạy được trên một JDK thì mọi compiler/plugin trong project cũng tương thích với JDK đó.

## 4. Nâng Gradle Wrapper

### 4.1. Chọn phiên bản và cập nhật bằng Wrapper task

Chọn phiên bản Gradle đã kiểm tra compatibility. Nếu Wrapper hiện tại chạy được, dùng chính Wrapper để nâng:

~~~bash
./gradlew wrapper --gradle-version 8.14.3 --distribution-type bin
~~~

Phiên bản trong ví dụ chỉ minh họa cú pháp; thay bằng phiên bản đích đã được dự án phê duyệt. Có thể chọn distribution type `bin` để tải bộ chạy nhỏ hơn; chọn `all` nếu team cần source/documentation đi kèm khi debug trong IDE.

Sau khi task hoàn tất, kiểm tra thay đổi trong:

- `gradle/wrapper/gradle-wrapper.properties`
- `gradle/wrapper/gradle-wrapper.jar`
- `gradlew`
- `gradlew.bat`

Tùy phiên bản Wrapper và trạng thái file hiện tại, có trường hợp cần chạy Wrapper task thêm lần nữa bằng Wrapper mới để đồng bộ script/JAR. Không áp dụng máy móc: xem diff và hướng dẫn của phiên bản Gradle đích, sau đó xác nhận tất cả file cần thiết đã được cập nhật.

### 4.2. Kiểm tra gradle-wrapper.properties

Ví dụ cấu hình:

~~~properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https://services.gradle.org/distributions/gradle-8.14.3-bin.zip
networkTimeout=10000
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
~~~

Trong file thật, nếu chính sách yêu cầu checksum, đặt `distributionSha256Sum` bằng SHA-256 chính thức tương ứng chính xác với file distribution được chọn. Không sao chép checksum của bản `all` sang bản `bin` hoặc của một phiên bản khác.

Các điểm cần kiểm tra:

- Distribution URL dùng HTTPS và trỏ tới đúng phiên bản.
- Checksum được lấy từ trang checksum chính thức của Gradle và được review cùng URL.
- Không trỏ tới file ZIP tùy ý trên máy developer hoặc URL không được kiểm soát.
- Không bỏ checksum chỉ để build qua nhanh nếu chính sách dự án yêu cầu xác minh distribution.
- Đường dẫn cache là đường dẫn trong Gradle User Home, không phải thư mục build output của ứng dụng.

`distributionSha256Sum` xác minh distribution ZIP được tải. Nó không thay thế việc kiểm tra tính toàn vẹn của Wrapper JAR hoặc review script wrapper.

### 4.3. Kiểm tra Wrapper JAR và script

Wrapper JAR là file thực thi được commit trong repository. Nếu JAR bị thay thế, wrapper có thể thực hiện hành vi ngoài dự kiến trước khi build bắt đầu. Vì vậy:

- Giữ Wrapper JAR từ nguồn tạo Wrapper chính thức.
- Review diff của JAR và script; không lấy file từ commit/URL không rõ nguồn.
- Dùng Gradle Wrapper Validation Action trong GitHub Actions hoặc quy trình xác minh tương đương của tổ chức.
- Pin CI action theo commit SHA đã review nếu chính sách supply-chain yêu cầu.
- Không chỉnh sửa thủ công script chỉ để che một lỗi tương thích.

Sau khi nâng, chạy:

~~~bash
./gradlew --version
./gradlew help
./gradlew tasks
~~~

Lệnh đầu xác nhận distribution/JVM. Hai lệnh sau buộc Gradle cấu hình build và liệt kê task, nhờ đó phát hiện sớm lỗi plugin hoặc build logic trước khi chạy test lâu.

### 4.4. Kiểm tra từ môi trường sạch

Wrapper có thể chạy trên máy đã cache distribution, nhưng CI hoặc developer mới có thể chưa có. Kiểm tra trên runner/container sạch hoặc xóa đúng cache Wrapper trong một môi trường thử nghiệm riêng rồi chạy lại.

Không xóa toàn bộ Gradle User Home của máy dùng chung để kiểm tra. Có thể dùng một Gradle User Home tạm:

~~~bash
GRADLE_USER_HOME="$(mktemp -d)"
export GRADLE_USER_HOME
./gradlew --version
./gradlew help
~~~

Trên PowerShell, dùng thư mục tạm riêng và đặt biến môi trường tương ứng cho process. Sau kiểm tra, dọn đúng thư mục tạm đã tạo.

Mục đích là xác nhận distribution có thể tải từ URL đã commit, checksum hợp lệ, Wrapper khởi chạy được và build không phụ thuộc vào file cục bộ không được quản lý.

## 5. Nâng Maven Wrapper

### 5.1. Chọn Maven distribution đích

Kiểm tra phiên bản Maven hiện tại:

~~~bash
./mvnw --version
~~~

Nâng Wrapper bằng Maven Wrapper Plugin theo phiên bản plugin và cú pháp được tài liệu chính thức của plugin đang sử dụng hỗ trợ. Một dạng lệnh phổ biến là:

~~~bash
mvn wrapper:wrapper -Dmaven=3.9.9
~~~

Thay phiên bản minh họa bằng phiên bản Maven đã được chọn sau khi kiểm tra JDK và plugin compatibility. Nếu Wrapper hiện tại vẫn hoạt động, có thể dùng nó để chạy plugin; nếu chưa có Wrapper, dùng Maven cài đặt trên máy build để bootstrap một lần, rồi commit đầy đủ file wrapper sinh ra.

### 5.2. Kiểm tra maven-wrapper.properties

Ví dụ distribution URL:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
~~~

Một số phiên bản/kiểu Maven Wrapper hỗ trợ thêm checksum hoặc cấu hình wrapper artifact. Chỉ thêm các thuộc tính mà implementation đang dùng thực sự hỗ trợ; xác minh tên property và semantics trong tài liệu Maven Wrapper tương ứng. Không đoán tên thuộc tính từ Gradle Wrapper vì hai implementation không hoàn toàn giống nhau.

Kiểm tra:

- URL HTTPS trỏ tới đúng Maven distribution và phiên bản.
- Distribution được lấy từ Apache Maven hoặc mirror nội bộ đáng tin cậy.
- Nếu Wrapper hỗ trợ checksum distribution/JAR, pin checksum chính thức tương ứng và review thay đổi.
- Commit cả `mvnw`, `mvnw.cmd`, `.mvn/wrapper/maven-wrapper.properties` và JAR bootstrap nếu loại Wrapper sử dụng.
- Không commit file cache đã tải hoặc Maven local repository.

### 5.3. Kiểm tra Maven Wrapper trên Windows và Unix

Chạy:

~~~bash
./mvnw --version
./mvnw -B -ntp help:effective-pom
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd -B -ntp help:effective-pom
~~~

Kiểm tra cả hai script có trong repository và có thể chạy trong CI tương ứng. Với script Unix, giữ executable bit nếu repository/CI cần gọi trực tiếp bằng `./mvnw`. Kiểm tra line endings và quyền thực thi khi diff wrapper files.

## 6. Kiểm chứng Gradle convention plugin hiện có

Convention plugin tập trung quy tắc build dùng chung để các module áp dụng bằng plugin ID. Nó có thể đặt Java toolchain, test framework, compiler flags, Spring Boot conventions, dependency constraints, lint/check tasks và các quy ước packaging.

### 6.1. Xác định plugin được khai báo ở đâu

Các vị trí thường gặp:

- `buildSrc/src/main/kotlin` hoặc `buildSrc/src/main/groovy`.
- Included build như `build-logic`.
- Precompiled script plugin trong `build-logic/src/main/kotlin`.
- Binary plugin được publish từ repository nội bộ.
- Plugin được khai báo qua `pluginManagement` trong `settings.gradle.kts`.

Tìm plugin ID trong các module và truy ngược đến implementation. Xác định version của plugin và dependency của chính build logic. Không nhầm plugin application trong module với dependency/plugin version được khai báo trong build logic.

### 6.2. Ví dụ included build chứa precompiled convention plugin

Cấu trúc minh họa:

~~~text
project/
├── settings.gradle.kts
├── build.gradle.kts
├── build-logic/
│   ├── build.gradle.kts
│   └── src/main/kotlin/
│       └── acme.java-conventions.gradle.kts
├── service-a/
│   └── build.gradle.kts
└── service-b/
    └── build.gradle.kts
~~~

Trong `settings.gradle.kts`:

~~~kotlin
pluginManagement {
    includeBuild("build-logic")
}

rootProject.name = "sample-platform"
include("service-a", "service-b")
~~~

Trong `build-logic/build.gradle.kts`:

~~~kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}
~~~

Trong `build-logic/src/main/kotlin/acme.java-conventions.gradle.kts`:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

Module áp dụng convention:

~~~kotlin
plugins {
    id("acme.java-conventions")
}
~~~

Tên file precompiled script plugin quyết định plugin ID theo quy tắc Gradle. Ví dụ trên tạo ID `acme.java-conventions`. Trong dự án thật, không đổi ID tùy tiện vì các module, plugin aliases hoặc build scripts khác có thể đang phụ thuộc vào ID đó.

Ví dụ này chỉ minh họa một Java convention nhỏ. Nếu convention hiện tại còn cấu hình Spring Boot, publishing, dependency management hoặc kiểm tra chất lượng, hãy giữ những hành vi đó và kiểm chứng sau khi nâng Wrapper.

### 6.3. Kiểm tra version của plugin dependency

Convention plugin có thể phụ thuộc vào Gradle API, Kotlin DSL plugin, Spring Boot Gradle Plugin hoặc plugin bên thứ ba. Khi nâng Gradle:

- Kiểm tra plugin có hỗ trợ phiên bản Gradle đích.
- Pin version của plugin dependency trong build logic.
- Tránh khai báo cùng plugin version ở nhiều nơi nếu có thể quản lý tập trung.
- Kiểm tra plugin marker/artifact có thể tải từ repository cấu hình trong build logic.
- Kiểm tra plugin không sử dụng API Gradle đã bị deprecated hoặc removed.
- Kiểm tra plugin có hỗ trợ Configuration Cache nếu dự án bật tính năng đó.

Nếu convention plugin dùng Spring Boot Gradle Plugin, hãy nâng và xác minh version Spring Boot theo compatibility matrix riêng. Không mặc định rằng nâng Wrapper sẽ tự nâng Spring Boot plugin.

### 6.4. Kiểm tra convention có thực sự được áp dụng

Một plugin tồn tại trong build logic chưa có nghĩa mọi module đều sử dụng nó. Kiểm tra:

- Module nào khai báo plugin ID.
- Module nào có cấu hình riêng ghi đè convention.
- Plugin có bị áp dụng hai lần qua root plugin và module plugin không.
- Root project có áp dụng nhầm plugin chỉ dành cho application module không.
- Các task được convention tạo ra có tồn tại và đúng cấu hình không.

Chạy:

~~~bash
./gradlew projects
./gradlew tasks --all
./gradlew help
~~~

Sau đó chạy task của từng loại module, chẳng hạn:

~~~bash
./gradlew :service-a:tasks --all
./gradlew :service-a:clean :service-a:check :service-a:bootJar
~~~

Không dựa vào việc root build thành công nếu module ứng dụng hoặc module thư viện chưa được cấu hình/test.

### 6.5. Kiểm thử convention plugin bằng Gradle TestKit

Với convention plugin có logic đáng kể, dùng Gradle TestKit để tạo một project mẫu tạm, áp dụng plugin và kiểm tra kết quả. TestKit chạy build thật thông qua GradleRunner.

Ví dụ test khái niệm:

~~~kotlin
class JavaConventionsPluginTest {
    @TempDir
    lateinit var projectDir: File

    @Test
    fun `applies java plugin and configures toolchain`() {
        projectDir.resolve("settings.gradle.kts")
            .writeText("rootProject.name = \"sample\"")

        projectDir.resolve("build.gradle.kts").writeText(
            """
            plugins {
                id("acme.java-conventions")
            }
            """.trimIndent()
        )

        val result = GradleRunner.create()
            .withProjectDir(projectDir)
            .withPluginClasspath()
            .withArguments("tasks", "--stacktrace")
            .build()

        assertTrue(result.output.contains("build"))
    }
}
~~~

Đây là ví dụ cấu trúc test; project test cần khai báo Gradle TestKit, JUnit và plugin classpath phù hợp với cách tổ chức build logic. Assertion thực tế nên kiểm tra behavior quan trọng: Java plugin đã áp dụng, toolchain/release đúng, test task dùng JUnit Platform, task convention tồn tại và override được hỗ trợ đúng.

Nếu convention plugin chỉ là một vài dòng cấu hình đơn giản, một fixture integration test chạy các module đại diện có thể đủ. Không cần dựng TestKit phức tạp cho mỗi dòng cấu hình.

### 6.6. Kiểm tra convention và Configuration Cache

Nếu dự án bật Configuration Cache, chạy build hai lần:

~~~bash
./gradlew check --configuration-cache
./gradlew check --configuration-cache
~~~

Lần sau cần tái sử dụng cache nếu build và plugin tương thích. Đọc cảnh báo về task/plugin không tương thích; không tắt Configuration Cache toàn cục chỉ để làm cho lỗi biến mất mà chưa xác định nguyên nhân.

Kiểm tra plugin custom không đọc environment/filesystem một cách eager hoặc giữ state không an toàn trong configuration phase. Sửa convention plugin hoặc task implementation tại nơi tạo ra lỗi, rồi chạy lại đúng build đại diện.

## 7. Kiểm chứng Maven parent POM hiện có

Parent POM thường quản lý phiên bản dependency, plugin, compiler, test plugin, profile, repository policy và properties dùng chung. Trong Maven multi-module, POM root có thể vừa là aggregator vừa là parent, nhưng hai vai trò này khác nhau:

- **Aggregator:** khai báo các module để Maven reactor build cùng nhau.
- **Parent:** cung cấp cấu hình được module kế thừa qua phần parent.

Một POM có modules không tự động trở thành parent của mọi module. Module phải khai báo đúng parent coordinates để kế thừa.

### 7.1. Phân biệt dependencyManagement và pluginManagement

| Khu vực | Quản lý gì? | Có tự kích hoạt không? |
| --- | --- | --- |
| dependencyManagement | Dependency versions, scope/type/exclusions mặc định | Không tự thêm dependency vào module |
| dependencies | Dependency thực sự có trên classpath của project | Có |
| pluginManagement | Plugin versions và cấu hình mặc định | Không tự chạy plugin chỉ vì được quản lý |
| build/plugins | Plugin được khai báo cho build; có thể kế thừa | Có, theo lifecycle/execution/goal cấu hình |

Một parent POM tốt giúp module tránh khai báo lại version và cấu hình giống nhau. Tuy nhiên, nếu chỉ đặt plugin trong pluginManagement, module vẫn cần khai báo plugin trong build/plugins khi muốn áp dụng plugin đó (trừ plugin được lifecycle hoặc cơ chế khác gọi theo cách riêng).

### 7.2. Ví dụ parent POM quản lý compiler và Spring Boot BOM

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme.build</groupId>
    <artifactId>acme-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-boot.version>3.5.0</spring-boot.version>
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
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.14.0</version>
                    <configuration>
                        <release>${maven.compiler.release}</release>
                    </configuration>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.3</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

Đây là parent POM minh họa. Trong dự án thực, chọn các version theo compatibility matrix đã kiểm tra và tập trung chúng ở một nơi. Không copy version ví dụ vào production mà không xác nhận.

Module con khai báo parent:

~~~xml
<parent>
    <groupId>com.acme.build</groupId>
    <artifactId>acme-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

Nếu parent được phát hành riêng và không có file POM tại relative path dự kiến, cấu hình relativePath phù hợp; relativePath rỗng có thể dùng để yêu cầu Maven resolve parent từ repository thay vì tìm POM local mặc định.

### 7.3. Spring Boot parent hay Spring Boot BOM?

Maven chỉ cho phép một parent trực tiếp trong phần parent. Nếu dự án đã có parent POM nội bộ, không thể đồng thời khai báo spring-boot-starter-parent làm parent thứ hai của module.

Có hai hướng phổ biến:

1. Parent nội bộ kế thừa Spring Boot parent, sau đó các module kế thừa parent nội bộ.
2. Parent nội bộ độc lập và import spring-boot-dependencies BOM trong dependencyManagement, đồng thời tự quản lý plugin versions/configuration cần thiết.

Import BOM quản lý dependency versions; nó không tự mang toàn bộ plugin management, build defaults hoặc execution của Spring Boot parent. Nếu dùng BOM, kiểm tra riêng Spring Boot Maven Plugin và execution repackage khi ứng dụng cần tạo executable archive.

Không giả định việc import BOM đồng nghĩa với việc Spring Boot Maven Plugin đã được kích hoạt.

### 7.4. Kiểm tra effective POM

POM mà Maven thực sự dùng là kết quả của parent inheritance, profiles, properties, dependency management, plugin management và các cấu hình khác. Dùng Help Plugin để xem effective POM:

~~~bash
./mvnw -pl :service-a help:effective-pom -Dverbose
~~~

Có thể xuất ra file trong thư mục build để so sánh:

~~~bash
./mvnw -pl :service-a help:effective-pom -Dverbose -Doutput=target/effective-pom.xml
~~~

Kiểm tra:

- Parent coordinates và version thực tế.
- Maven Compiler Plugin version và release.
- Surefire/Failsafe version, includes/excludes và system properties.
- Spring Boot Maven Plugin version, executions và repackage goal.
- Dependency versions được quản lý từ BOM/parent.
- Profile nào đang active và property nào ghi đè parent.
- Plugin configuration nào bị module con override.
- Các plugin có version tường minh, tránh phụ thuộc version mặc định không kiểm soát.

Verbose output giúp truy dấu nguồn cấu hình ở các phiên bản Help Plugin hỗ trợ. Effective POM là công cụ chẩn đoán, không phải file để commit thay cho POM gốc.

### 7.5. Kiểm tra reactor và từng module

Chạy từ root:

~~~bash
./mvnw -N -B -ntp validate
./mvnw -B -ntp clean verify
~~~

Nếu chỉ cần kiểm tra một module cùng các module phụ thuộc trong reactor:

~~~bash
./mvnw -pl :service-a -am -B -ntp clean verify
~~~

`-pl` chọn project; `-am` thêm các module mà project đó cần trong reactor. Chạy thêm các module có packaging khác nhau (library, application, integration test) nếu parent POM áp dụng cấu hình khác nhau.

Đối với parent POM được publish riêng, cần kiểm tra cả hai trường hợp: module build cùng reactor và module resolve parent từ repository. Một build reactor thành công chưa chứng minh parent artifact được publish/resolve đúng trên môi trường clean.

## 8. Kiểm chứng cấu hình được kế thừa và override

Nâng Wrapper có thể làm lộ khác biệt giữa cấu hình trung tâm và cấu hình cục bộ. Kiểm tra có hệ thống:

| Câu hỏi | Gradle convention plugin | Maven parent POM |
| --- | --- | --- |
| Cấu hình nằm ở đâu? | build-logic/buildSrc/plugin artifact | Parent POM |
| Module áp dụng bằng gì? | Plugin ID | Parent coordinates |
| Phiên bản plugin được quản lý ở đâu? | Plugin management/build logic/version catalog | pluginManagement/plugin declaration |
| Dependency versions ở đâu? | Version catalog/platform/constraints | dependencyManagement/BOM |
| Cách xem cấu hình hiệu lực? | tasks, dependencies, task reports, test fixtures | help:effective-pom, dependency:tree |
| Kiểm tra kế thừa/override? | So plugin application và module-specific configuration | So effective POM và profiles |
| Test logic tùy chỉnh? | Gradle TestKit/integration build | Reactor fixture/sample module/integration test |

### 8.1. Tránh cấu hình trùng

Ví dụ Gradle: root plugin block pin Spring Boot version, build logic lại khai báo một version khác; một module tự áp dụng plugin với version riêng. Đây là nguồn gây lệch hành vi giữa modules.

Ví dụ Maven: parent quản lý Surefire 3.x, module con ghi version cũ trong build/plugins; module con có thể override cấu hình parent. Effective POM sẽ cho thấy version và cấu hình cuối cùng.

Khi phát hiện trùng, xác định nơi sở hữu version/configuration. Đưa giá trị dùng chung về đúng cơ chế hiện hữu, xóa khai báo cũ chỉ sau khi xác minh không còn module cần nó.

### 8.2. Kiểm tra profile và môi trường

Maven profiles có thể được kích hoạt bởi JDK, OS, property, settings hoặc tham số CLI. Gradle có thể thay đổi cấu hình theo project property, environment variable, settings plugin hoặc init script. CI cũng có thể cung cấp init script/settings khác máy local.

Vì vậy, ghi lại chính xác command và properties dùng để kiểm tra. So sánh:

- Local build với CI build.
- Build mặc định với profile/release profile.
- Build từ root với build trực tiếp module.
- Build có cache với build clean.
- Build trong reactor với build resolve parent/plugin từ repository.

Không thêm credentials hoặc secrets vào output chẩn đoán. Khi cần xem property, chỉ hiển thị tên và trạng thái đã được cấp; không in giá trị bí mật.

## 9. Quy trình nâng cấp đề xuất

Thực hiện theo các bước sau để dễ xác định thay đổi gây lỗi.

### Bước 1 — Chụp baseline

Lưu kết quả Wrapper version, JVM, test/verify, module list và effective configuration. Ghi rõ lỗi tồn tại trước khi thay đổi.

### Bước 2 — Nâng Wrapper riêng

Chỉ cập nhật Gradle Wrapper hoặc Maven Wrapper và các file thuộc Wrapper. Không đồng thời nâng Spring Boot, plugin, dependency hoặc cấu trúc build.

### Bước 3 — Xác minh Wrapper

Kiểm tra URL, checksum, Wrapper JAR/scripts, quyền thực thi và chạy version/help từ môi trường sạch. Nếu Wrapper chưa chạy được, chưa chuyển sang sửa convention/parent.

### Bước 4 — Kiểm tra cơ chế chia sẻ hiện có

- Nếu Gradle: kiểm tra convention plugin, included build/buildSrc, pluginManagement và version catalog.
- Nếu Maven: kiểm tra parent chain, dependencyManagement, pluginManagement, profiles và effective POM.

Xác định thay đổi tương thích tối thiểu cần thiết; không chuyển từ convention plugin sang parent POM hoặc ngược lại trong cùng một lần nâng Wrapper.

### Bước 5 — Sửa cấu hình trung tâm

Nâng plugin dependency hoặc sửa API deprecated/removed tại nơi quản lý tập trung. Giữ module-specific override nếu đó là chủ ý và có test xác nhận.

### Bước 6 — Kiểm thử module đại diện rồi toàn bộ build

Chọn ít nhất một module application, một module library và module có cấu hình đặc biệt (integration test, publishing hoặc custom packaging). Sau đó chạy toàn bộ multi-project/reactor build.

### Bước 7 — Kiểm chứng CI

CI phải gọi Wrapper đã commit, không dùng lệnh Maven/Gradle cài global để thay thế. Chạy wrapper validation, kiểm JDK và thực hiện cùng các lệnh verify như local. Kiểm tra build từ checkout sạch và cache rỗng.

### Bước 8 — Review diff và ghi nhận kết quả

Review toàn bộ Wrapper files, build logic/parent POM, version changes và effective configuration. Ghi lại lý do nâng, phiên bản đích, compatibility đã kiểm tra, test commands và mọi thay đổi behavior.

## 10. Bộ lệnh kiểm chứng tham khảo

### 10.1. Gradle

~~~bash
./gradlew --version
./gradlew help
./gradlew projects
./gradlew tasks --all
./gradlew clean check
./gradlew build
./gradlew check --configuration-cache
./gradlew check --configuration-cache
~~~

Với module cụ thể:

~~~bash
./gradlew :service-a:clean :service-a:check :service-a:bootJar
~~~

Nếu dự án không có task bootJar (ví dụ module library), thay bằng task đúng với loại module. Không thêm task giả chỉ để lệnh mẫu chạy được.

### 10.2. Maven

~~~bash
./mvnw --version
./mvnw -N -B -ntp validate
./mvnw -pl :service-a help:effective-pom -Dverbose
./mvnw -pl :service-a -am -B -ntp clean verify
./mvnw -B -ntp clean verify
~~~

Nếu module dùng Failsafe integration tests, kiểm tra các integration-test/verify executions và môi trường cần thiết. Nếu parent POM có profile release, kiểm profile đó riêng trong CI được bảo vệ.

### 10.3. Những gì cần lưu lại

Một báo cáo nâng cấp hữu ích có:

- Wrapper cũ và mới.
- URL/checksum distribution đã xác minh.
- JDK chạy build tool và Java toolchain.
- Plugin/convention/parent versions bị tác động.
- Effective POM hoặc Gradle task/configuration evidence cho module đại diện.
- Test commands và exit status.
- CI run từ checkout sạch.
- Known limitation hoặc module chưa kiểm được.

Không đưa nội dung secret, settings credentials hoặc token vào báo cáo.

## 11. Lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Wrapper tải nhầm phiên bản | distributionUrl chưa được cập nhật hoặc cache cũ che lỗi | Kiểm properties, chạy trong Gradle User Home/Maven cache tạm |
| Gradle Wrapper báo checksum mismatch | Checksum không khớp ZIP hoặc version/type | Lấy lại checksum chính thức đúng distribution; không bỏ kiểm tra |
| Wrapper chạy local nhưng fail CI | Thiếu script/JAR, executable bit, shell hoặc JDK khác | Commit đầy đủ wrapper files, kiểm Unix/Windows scripts và JDK |
| Gradle không khởi động với JDK hiện tại | Gradle đích yêu cầu JVM mới hơn | Nâng JDK chạy Gradle trong CI/developer, tách khỏi toolchain target |
| Gradle báo plugin không tương thích | Plugin dùng API cũ hoặc version chưa hỗ trợ Gradle mới | Kiểm compatibility, nâng plugin hoặc sửa convention plugin |
| Convention plugin không tìm thấy | includeBuild/plugin ID/source layout sai | Kiểm settings, tên file plugin và plugin classpath |
| Plugin được áp dụng hai lần | Root và module cùng áp dụng hoặc convention chồng lặp | Xác định một nơi sở hữu plugin application |
| Gradle task không có ở một module | Convention plugin không áp dụng cho module đó hoặc loại module khác | Kiểm plugin ID và task phù hợp với module |
| Configuration Cache không reuse | Plugin/task chưa tương thích hoặc configuration đọc state không an toàn | Đọc problem report, sửa plugin/task và chạy hai lần |
| Maven parent không resolve | Coordinates/version/relativePath sai hoặc artifact chưa publish | Kiểm parent declaration và repository resolution |
| Maven module không kế thừa plugin | Chỉ có pluginManagement, chưa khai báo plugin trong build/plugins | Kích hoạt plugin tại module/parent theo mục đích |
| Effective POM có version cũ | Module/profile override parent | Tìm nguồn override và thống nhất nơi quản lý version |
| Spring Boot repackage không chạy | Dùng BOM nhưng thiếu plugin execution | Cấu hình Spring Boot Maven Plugin và repackage rõ ràng |
| Build reactor pass nhưng build module độc lập fail | Parent nội bộ chỉ có trong reactor/local repo | Kiểm parent artifact publish/resolve từ repository sạch |
| CI và local cho effective config khác nhau | Profile, init script, env hoặc settings khác nhau | So sánh command, active profiles và cấu hình build |
| Build pass nhờ cache nhưng clean build fail | Cache che thiếu dependency hoặc task input | Chạy clean từ môi trường sạch và sửa khai báo dependency/input |
| Nâng Wrapper kéo theo nhiều diff khó review | Cập nhật đồng thời Wrapper, plugin, dependency và format | Tách thay đổi thành các bước/commit có mục tiêu riêng |

## 12. Checklist trước khi merge

- [ ] Đã ghi baseline Wrapper version, JVM và kết quả build trước nâng cấp.
- [ ] Đã xác định Gradle convention plugin hoặc Maven parent POM đang được dùng.
- [ ] Đã kiểm tra compatibility của build tool, JDK, Spring Boot và plugin.
- [ ] Gradle distribution URL hoặc Maven distribution URL trỏ tới nguồn tin cậy.
- [ ] Gradle distribution checksum được xác minh nếu chính sách yêu cầu.
- [ ] Wrapper JAR và script được review/validation; không lấy file từ nguồn không rõ.
- [ ] Đã commit đầy đủ wrapper scripts, properties và bootstrap JAR cần thiết.
- [ ] Unix và Windows wrapper scripts được kiểm tra theo môi trường CI hỗ trợ.
- [ ] Gradle convention plugin ID, plugin classpath và module application không bị lệch.
- [ ] Maven parent chain, relativePath và artifact resolution hoạt động.
- [ ] Đã phân biệt dependencyManagement với dependencies và pluginManagement với build/plugins.
- [ ] Effective POM hoặc Gradle task/configuration evidence đã được kiểm tra trên module đại diện.
- [ ] Module-specific overrides đã được rà soát.
- [ ] Build/test chạy thành công từ checkout sạch và cache rỗng.
- [ ] Toàn bộ multi-project/reactor build đã được xác minh.
- [ ] CI sử dụng Wrapper trong repository, đúng JDK và không phụ thuộc tool cài global.
- [ ] Không có credentials, token, cache hoặc file tạm được commit/upload.
- [ ] Diff chỉ chứa thay đổi có chủ đích và có thể review/rollback.

## 13. Tài liệu chính thức

- Gradle — The Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- Gradle — Compatibility Matrix: https://docs.gradle.org/current/userguide/compatibility.html
- Gradle — Pre-compiled Script Plugins: https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html
- Gradle — Sharing Build Logic Between Subprojects: https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html
- Gradle — Testing Gradle Plugins: https://docs.gradle.org/current/userguide/testing_gradle_plugins.html
- Gradle — Configuration Cache Requirements: https://docs.gradle.org/current/userguide/configuration_cache_requirements.html
- Apache Maven — Maven Wrapper: https://maven.apache.org/tools/wrapper/
- Apache Maven — POM Reference: https://maven.apache.org/pom.html
- Apache Maven — Introduction to the POM: https://maven.apache.org/guides/introduction/introduction-to-the-pom.html
- Apache Maven Help Plugin — effective-pom: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Apache Maven — Maven Enforcer Plugin: https://maven.apache.org/enforcer/maven-enforcer-plugin/
- Spring Boot — Build Tool Plugins: https://docs.spring.io/spring-boot/gradle-plugin/
- Spring Boot — Maven Plugin: https://docs.spring.io/spring-boot/maven-plugin/

**Kết luận:** Nâng Wrapper là thay đổi về phiên bản build tool; kiểm chứng convention plugin hoặc parent POM là xác nhận toàn bộ module vẫn nhận đúng quy ước build sau thay đổi đó. Hãy chụp baseline, nâng Wrapper, xác minh distribution và script, kiểm tra cấu hình chia sẻ ở đúng nơi, xem cấu hình hiệu lực, chạy module đại diện rồi toàn bộ build và CI từ checkout sạch.