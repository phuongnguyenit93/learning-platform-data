# Loại bỏ khác biệt cấu hình giữa IDE, dòng lệnh và CI

Một dự án Java có thể biên dịch thành công trong IDE nhưng thất bại khi chạy `./gradlew build` hoặc `./mvnw verify`. Cũng có trường hợp lệnh trên máy lập trình viên thành công, nhưng CI báo `UnsupportedClassVersionError`, không tìm thấy dependency, test lệch múi giờ hoặc annotation processor tạo source khác. Khi nâng JDK và thư viện trong **Java Advance Compatibility Migration**, những khác biệt này dễ bị nhầm thành lỗi tương thích của chính Java.

Nguyên nhân thường nằm ở việc **ba môi trường không thực sự dùng cùng một mô hình build**: IDE có thể chọn compiler và classpath riêng, terminal dùng JDK từ `JAVA_HOME` hoặc `PATH`, trong khi CI dùng một container/JDK khác và các biến môi trường, repository, profile hoặc credential riêng. Việc chỉ đổi “Project SDK” trong IDE không bảo đảm Gradle daemon, Maven, task biên dịch, test worker và ứng dụng đều sử dụng đúng JDK.

Mục tiêu của bài học là thiết lập một hệ thống build **có thể dự đoán và tái lập**: cùng source revision, cùng dependency và cùng điều kiện đã công bố sẽ cho kết quả kiểm tra tương đương giữa IDE, dòng lệnh và CI; khi môi trường cố tình khác, khác biệt phải được khai báo, đo được và kiểm thử rõ ràng.

## 1. Hiểu đúng: không phải tất cả tiến trình đều phải dùng một JDK

Một dự án Java có thể có nhiều JVM phục vụ những vai trò khác nhau:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| IDE runtime | JVM chạy bản thân IDE | JVM do IDE đi kèm hoặc được cấu hình |
| Project SDK | JDK IDE dùng để hiểu source, index, code completion | JDK 21 |
| Gradle daemon | JVM thực thi Gradle build và plugin | JDK 21 |
| Maven runtime | JVM chạy Maven core và plugin | JDK 21 |
| Java compiler/toolchain | `javac` được chọn để biên dịch source | JDK 21, với `--release 17` |
| Test worker | JVM thực thi unit/integration tests | JDK 17 |
| Application runtime | JVM chạy artifact thật | JDK 17 hoặc 21 theo support matrix |
| Annotation processor/plugin | Code chạy ở build time, có classpath riêng | Phụ thuộc JDK/compiler/plugin |
| CI agent/container | Hệ điều hành và image triển khai build | Linux x64, JDK cụ thể |

**Giống cấu hình** không có nghĩa “ép mọi thứ dùng cùng phiên bản Java”. Chẳng hạn, thư viện có thể chủ động dùng compiler JDK 21 để tạo bytecode Java 17, rồi chạy test bằng JDK 17 để xác nhận baseline tối thiểu. Đây là khác biệt **có chủ đích, được quản lý**, không phải sự lệch cấu hình.

Điểm cần loại bỏ là khác biệt **không được biết hoặc không được kiểm soát**: IDE chạy test bằng JDK 21 trong khi CI chạy JDK 17 mà build không ghi rõ; hoặc một máy dùng bản Gradle mới hơn chỉ vì không gọi wrapper.

## 2. Một mô hình “single source of truth” thực tế

Không có một file cấu hình đơn lẻ chứa được mọi yếu tố: build tool, JDK, credential và hạ tầng chạy test có trách nhiệm khác nhau. Thay vào đó, cần xác định **nguồn khai báo có thẩm quyền cho từng quyết định**.

| Quyết định | Nơi nên khai báo/kiểm soát | Điều cần tránh |
|---|---|---|
| Phiên bản Gradle/Maven | Wrapper được commit vào repository | Dùng Gradle/Maven global ngẫu nhiên |
| JDK/compiler target | Build file, toolchain và `--release` | Chỉ thiết lập IDE Project SDK |
| Phiên bản plugin | `settings.gradle(.kts)`, build logic hoặc Maven POM | Plugin tự lấy phiên bản theo máy |
| Dependency versions | Build files, catalog/BOM/constraints và lock nếu áp dụng | Version động không kiểm soát |
| Repositories | Cấu hình build chuẩn và quản trị mirror | Chỉ chạy nhờ Maven/Gradle cache cục bộ |
| Secrets | Secret store, CI credentials, user-local settings | Commit token/password vào source |
| Profiles/variants | Cấu hình được đặt tên và tiêu chí lựa chọn rõ ràng | Tự đổi behavior theo hostname người dùng |
| Test environment | Build task, fixture/container hoặc pipeline khai báo | Test “ngẫu nhiên” theo timezone, locale, service cục bộ |
| Deploy/runtime | Container/IaC và thông số được quản lý | Giả định test JVM đồng nhất với production |

Một repository nên chỉ rõ câu lệnh build chuẩn. IDE được khuyến nghị **chạy hoặc ủy quyền tới lệnh build chuẩn**, chứ không tự tạo một quy trình biên dịch có quy tắc khác.

## 3. Bắt đầu bằng việc quan sát phiên bản thực sự được sử dụng

Khi gặp lỗi “IDE chạy nhưng CI không”, đừng sửa code ngay. Trước hết hãy đo những gì từng môi trường thực sự chạy.

Trên terminal:

~~~bash
java -version
javac -version
echo "$JAVA_HOME"
~~~

Trên PowerShell:

~~~powershell
java -version
javac -version
$env:JAVA_HOME
Get-Command java
Get-Command javac
~~~

Kiểm tra build tool của dự án qua wrapper:

~~~bash
./gradlew --version
./mvnw --version
~~~

Trên Windows có thể dùng `gradlew.bat` và `mvnw.cmd` theo terminal và dự án.

Đừng chỉ quan sát kết quả `java -version` rồi kết luận compiler, Gradle daemon và test dùng JVM ấy. Ví dụ:

- `JAVA_HOME` trỏ tới JDK 17, nhưng IDE cấu hình Gradle JVM là JDK 21.
- `PATH` ưu tiên executable Java 21, trong khi Maven dùng `JAVA_HOME` ở JDK 17.
- Gradle toolchain chọn JDK 21 cho compile, nhưng test dùng launcher khác.
- CI chạy trong image có JDK 17 và không provision toolchain 21.
- IDE test runner chạy bằng Project SDK, không qua Gradle/Maven.

Ghi ít nhất: **JDK feature/update/vendor**, Gradle/Maven version, compiler target, test launcher và môi trường của tiến trình lỗi.

### 3.1. Một kết luận đúng phải ghi rõ vai trò

Thay vì viết “dự án sử dụng Java 17”, nên ghi:

~~~text
Build tool runtime: JDK 21 (vendor/build đã ghi lại)
JavaCompile compiler: JDK 21
javac --release: 17
Unit test launcher: JDK 17
Application minimum runtime: Java 17
CI baseline OS: Linux x64
~~~

Đây là cấu hình minh họa, không phải thông số đã được kiểm chứng của một repository cụ thể.

## 4. Sử dụng Gradle Wrapper và Maven Wrapper

Wrapper cho phép repository chỉ định cách lấy và chạy phiên bản build tool thay vì dựa vào bản cài global của từng developer.

Một dự án Gradle thường có:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.properties
gradle/wrapper/gradle-wrapper.jar
~~~

Một dự án Maven Wrapper thường có:

~~~text
mvnw
mvnw.cmd
.mvn/wrapper/maven-wrapper.properties
~~~

Các file thực tế phụ thuộc phiên bản/kiểu Maven Wrapper được cấu hình. Không nên suy ra file thiếu là lỗi nếu cơ chế wrapper của dự án khác cấu trúc minh họa; xác định từ repository.

Lệnh dùng thống nhất:

~~~bash
./gradlew clean test
./mvnw clean verify
~~~

**Không cần chạy cả hai**: chọn build tool mà dự án thực sự sử dụng.

Lợi ích của wrapper:

- Giảm khác biệt phiên bản build tool giữa máy cá nhân và CI.
- Giúp chạy đúng CLI của repository khi tái hiện lỗi.
- Giúp kiểm soát nâng cấp Gradle/Maven qua commit có thể review.
- Tránh “IDE dùng Gradle A nhưng terminal dùng Gradle B”.
- Hỗ trợ tài liệu hóa entrypoint cho build trong CI.

Tuy nhiên, wrapper **không tự chọn đúng JDK**, không giải quyết dependency conflict và không bảo đảm mọi plugin tương thích. Cần kết hợp với toolchain, dependency management và kiểm thử.

### 4.1. Quản lý tính toàn vẹn của wrapper

Wrapper là thành phần được thực thi khi build. Nên review thay đổi wrapper scripts, wrapper binary/config, nguồn tải distribution và checksum/verification theo hỗ trợ của từng wrapper. Chỉ dùng nguồn phân phối được phê duyệt. Không tùy tiện tải wrapper binary từ nguồn không rõ hoặc tự chỉnh URL sang một mirror chưa được kiểm soát.

## 5. Gradle: phân biệt Gradle JVM, Java toolchain và `--release`

Trong Gradle, có ít nhất ba quyết định độc lập:

1. **Gradle JVM:** JDK chạy Gradle daemon và plugin.
2. **Java toolchain:** JDK được chọn cho task cần compiler/launcher.
3. **Compiler release:** luật ngôn ngữ, class-file target và API Java SE mà source được phép dùng.

Ví dụ `build.gradle.kts`:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}
~~~

Trong ví dụ:

- Toolchain yêu cầu compiler Java 21.
- `options.release = 17` yêu cầu biên dịch source theo Java 17 và API Java SE 17.
- Artifact Java được biên dịch ở mức class-file Java 17, với điều kiện mọi compiler task liên quan được cấu hình như dự kiến.
- `options.encoding` giảm khác biệt đọc source giữa máy.
- Không có bảo đảm test đang chạy JDK 17 nếu chưa cấu hình test launcher.

Không nên chỉ dùng `sourceCompatibility = JavaVersion.VERSION_17` và `targetCompatibility = JavaVersion.VERSION_17` khi mục tiêu là ngăn source gọi API Java SE 21. Với compiler hỗ trợ, `--release 17` giới hạn API nền tảng theo release đích; source/target riêng lẻ không có hiệu lực tương đương.

### 5.1. Đặt JVM cho test

Có thể yêu cầu test thực thi trên JDK tối thiểu mà artifact được công bố hỗ trợ:

~~~kotlin
tasks.withType<Test>().configureEach {
    javaLauncher.set(
        javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(17))
        }
    )
}
~~~

Task `Test` được cấu hình như trên sẽ dùng launcher được Gradle toolchain chọn. Nếu có integration test task ở class hoặc plugin khác, cần xác định nó có được áp dụng cấu hình tương đương không.

**Không nên dựa vào mặc định Gradle JVM cho test** nếu nhóm cần xác nhận runtime Java 17, hoặc cần một test matrix trên nhiều JDK.

### 5.2. Task chạy ứng dụng khác task chạy test

`JavaExec`, `Test` và các plugin riêng có thể chọn JVM theo cơ chế khác. Ví dụ, nếu có task chạy một chương trình Java:

~~~kotlin
tasks.withType<JavaExec>().configureEach {
    javaLauncher.set(
        javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(17))
        }
    )
}
~~~

Dùng cấu hình này khi tất cả `JavaExec` task thực sự phải chạy bằng Java 17. Nếu code generator hoặc tool build cần Java 21, không nên áp dụng toàn cục mà phải cấu hình từng task tương ứng.

### 5.3. Đừng ép mọi thứ qua `org.gradle.java.home`

`org.gradle.java.home` có thể chọn JVM chạy Gradle trong những điều kiện phù hợp; nó **không thay thế Java toolchain** và `options.release`. Commit một đường dẫn tuyệt đối như `C:\Program Files\...\jdk-21` vào `gradle.properties` của repository sẽ gây lỗi trên Linux/CI hoặc máy khác.

Nếu cần cấu hình JDK cục bộ, ưu tiên cơ chế toolchain và provisioning được quản lý, hoặc cài đặt user-local theo tài liệu. Trong CI, provision JDK rõ ràng và đảm bảo Gradle có thể phát hiện/chọn đúng JDK.

## 6. Maven: phân biệt JVM chạy Maven, compiler và test

Maven cũng có những tầng tương tự:

- Wrapper xác định phiên bản Maven theo cơ chế đã cấu hình.
- `JAVA_HOME` và môi trường launcher ảnh hưởng JDK chạy Maven.
- Maven Compiler Plugin có thể dùng compiler từ JDK chạy Maven hoặc toolchain đã khai báo.
- Maven Surefire/Failsafe và test fork có cơ chế chọn Java execution riêng tùy cấu hình/plugin.
- Các plugin tạo source, đóng gói hoặc phân tích bytecode có yêu cầu JDK riêng.

Ví dụ cấu hình Maven Compiler Plugin cho Java 17:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <encoding>UTF-8</encoding>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Phiên bản plugin ở đây minh họa một cấu hình; dự án phải chọn phiên bản theo compatibility matrix với Maven/JDK thực tế. `release` giúp compiler giới hạn luật ngôn ngữ, class-file target và API Java SE ở release mục tiêu khi compiler hỗ trợ.

Có thể đặt property tập trung:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
</properties>
~~~

Nếu cần compiler JDK 21 trong khi JVM chạy Maven khác, dùng Maven Toolchains theo phiên bản plugin và hỗ trợ của build. Việc cung cấp `toolchains.xml` phải có quy ước triển khai ở developer/CI. **Không được mặc định rằng có toolchain cho Compiler Plugin thì mọi Maven plugin và test fork sẽ dùng cùng JDK đó.**

### 6.1. Maven Toolchains: tách yêu cầu khỏi đường dẫn cục bộ

Maven Toolchains cho phép một số plugin có hỗ trợ chọn tool như JDK theo yêu cầu thay vì phụ thuộc hoàn toàn vào JVM chạy Maven. Cấu hình toolchains thực tế có thể nằm trong file cục bộ của người dùng và chỉ định vị trí JDK đã cài.

Đối với repository:

- Công bố JDK/version tối thiểu và tiêu chí vendor nếu cần.
- Chọn plugin versions hỗ trợ toolchain và JDK đích.
- Provision JDK trong CI hoặc tài liệu hóa thao tác cài.
- Không commit file machine-specific chứa đường dẫn JDK cá nhân hoặc credential.
- Kiểm tra compiler và test plugin thực sự dùng toolchain nào.

Nếu một plugin không hỗ trợ toolchain, nó có thể vẫn chạy trong JVM Maven. Điều này phải được kiểm trong pipeline thay vì chỉ nhìn cấu hình.

## 7. IDE phải sử dụng mô hình build chuẩn

IDE hỗ trợ nhiều tiện ích: index, code completion, auto-compile, test runner, debug và import dependency. Chúng hữu ích nhưng có thể sử dụng classpath/JDK khác với Gradle hoặc Maven.

Ví dụ trong IntelliJ IDEA, cần kiểm tra các nhóm thiết lập sau:

| Nhóm | Điều cần đối chiếu |
|---|---|
| Project SDK và language level | Khớp với cấu hình source và API mục tiêu của module |
| Gradle JVM | JDK chạy Gradle thông qua IDE |
| Gradle import/sync | Module và dependency được lấy từ build definition |
| Build/run delegation | Đối với Gradle, IDE có thể ủy quyền build/test cho Gradle |
| Test runner | Đang dùng Gradle, Maven goal hay IDE built-in test runner? |
| Run configuration | Main class, working directory, env vars, VM args và JDK |
| Annotation processing | IDE có bật processing hoặc ủy quyền build đúng không? |
| Generated sources | IDE index đúng directory mà build tool tạo ra không? |

Với Maven, IDE có thể import dự án từ POM và chạy goal từ Maven tool window, nhưng **không nên giả định mọi nút “Run” đều thực thi `mvn verify`**. Khi kết quả khác nhau, so sánh lệnh Maven thực tế với run configuration của IDE.

Nguyên tắc:

> IDE là giao diện phát triển; build definition được commit phải là nguồn quyết định dependency, compiler, code generation và test contract.

Nếu IDE-built-in compiler chạy một đường khác build tool, nó có thể hữu ích cho phản hồi nhanh, nhưng không được dùng làm bằng chứng cuối cùng cho artifact phát hành.

### 7.1. Nhập đúng repository từ Gradle/Maven project

Khi mở project, nhập từ `settings.gradle.kts`/`build.gradle.kts` hoặc `pom.xml` tương ứng, tránh tự tạo IDE module riêng với thư viện JAR thêm thủ công. Một JAR được add qua IDE classpath nhưng không có trong Gradle/Maven có thể khiến IDE compile pass, CI fail.

Nếu module không được IDE nhận diện đúng, kiểm tra project import/sync và build definitions trước khi thêm dependency trực tiếp trong IDE.

### 7.2. Generated code và annotation processors

Lombok, MapStruct, QueryDSL, Dagger, JPA metamodel, OpenAPI generators hoặc annotation processors khác có thể tạo source trong build.

Khác biệt thường thấy:

- IDE bật processor plugin riêng nhưng build tool thiếu dependency processor.
- Build tool có `annotationProcessor`, IDE chưa sync generated source.
- IDE tạo code bằng JDK khác với task compiler trong CLI.
- CI clean build không có file generated từng tồn tại ở máy dev.
- Version processor không tương thích với compiler JDK mới.
- Một task code generator phụ thuộc file/resource chưa khai báo.

Cần cấu hình processor và generator **trong build**, không dựa vào file được tạo thủ công hoặc plugin chỉ cài trên máy developer. Những generated source bắt buộc phải được tạo lại trong clean checkout và clean CI build.

## 8. Tránh phụ thuộc vào cache cục bộ và file không được commit

IDE và terminal thường chạy trên máy có cache lâu năm. CI chạy trong checkout sạch nên phát hiện những dependency ẩn:

- JAR từng được cài thủ công vào Maven local repository.
- Artifact được Gradle cache nhưng không còn ở repository được cấu hình.
- Generated source có từ build trước.
- File cấu hình môi trường chỉ có trên máy developer.
- Jar trong một thư mục `libs` của IDE không được build tool khai báo.
- Test fixture/dữ liệu nằm ngoài repository.
- Một version SNAPSHOT có artifact khác nhau ở hai nơi.
- CI cần network nhưng developer đang làm offline.

Không nên xử lý bằng cách copy cả `~/.m2/repository` hoặc Gradle cache từ một máy cá nhân sang CI như nguồn dependency lâu dài. Việc đó che giấu vấn đề về repository và provenance.

Dùng repository được quản lý, khóa phiên bản và metadata xác minh artifact khi phù hợp; nếu có private artifact, đảm bảo CI và developer được cấp quyền theo cùng mô hình.

### 8.1. Thử nghiệm một checkout sạch

Một cách để xác minh cấu hình không lệ thuộc IDE/cached files là chạy build từ checkout mới trên môi trường đã provision JDK và build tool, với dependencies được resolve từ repository chuẩn. Đây là ví dụ về **bài kiểm tra cần thực hiện trong dự án**, không phải bắt buộc chạy khi biên soạn tài liệu.

Không nhất thiết phải xóa toàn bộ Maven/Gradle cache của developer. Khi nghi ngờ cache, chỉ điều tra artifact cụ thể hoặc so sánh trong môi trường sạch; xóa cache hàng loạt thường làm mất thời gian và không tìm nguyên nhân gốc.

## 9. Thống nhất dependency versions và plugin versions

Một dependency graph thống nhất là điều kiện để IDE, CLI và CI sử dụng cùng API/runtime library.

Với Gradle, có thể quản lý bằng:

- Version catalog.
- Platform/BOM cho một nhóm artifact cần version alignment.
- Dependency constraints phù hợp.
- Dependency locking khi cần tái lập resolved versions.
- Dependency verification metadata hoặc cơ chế provenance được quản lý.

Ví dụ Kotlin DSL với một phiên bản rõ ràng:

~~~kotlin
dependencies {
    implementation("com.example:client-api:2.4.1")
}
~~~

Tọa độ trên là placeholder. Với dependency thật, dùng artifact/version đã được chọn theo compatibility/support policy.

Một version catalog:

~~~toml
# gradle/libs.versions.toml
[versions]
client = "2.4.1"

[libraries]
client-api = { module = "com.example:client-api", version.ref = "client" }
~~~

Đặt version trong catalog giúp giảm trùng lặp, nhưng **không bảo đảm runtimeClasspath resolve chính phiên bản đó** nếu có constraint hoặc transitive dependency tác động. Phải kiểm tra graph thực tế.

Với Maven, `dependencyManagement`, BOM import và pluginManagement có thể quản lý phiên bản. Cần nhớ:

- Dependency management không tự làm dependency xuất hiện nếu chưa được khai báo hoặc kéo theo bởi cấu trúc khác.
- `pluginManagement` xác định cấu hình/phiên bản cho plugin được sử dụng theo cơ chế Maven tương ứng, không phải mọi goal tự thực thi.
- Parent POM có thể áp dụng cấu hình qua inheritance.
- Active profiles và settings có thể tác động resolution.

Bất kể build tool, **không dùng version “latest” không kiểm soát** để CI tự đổi binary giữa hai lần build. Chỉ dùng version ranges/dynamic versions khi có lý do, cơ chế lock và bằng chứng đi kèm.

## 10. Maven effective POM và Gradle resolved graph

Khi thấy IDE và CI nhận dependency khác nhau, so sánh **cấu hình hiệu lực** chứ không chỉ so sánh vài dòng source.

Với Maven, các goal hỗ trợ điều tra:

~~~bash
./mvnw help:active-profiles
./mvnw help:effective-pom
./mvnw dependency:tree
~~~

Những lệnh trên có thể resolve Maven Help/Dependency Plugin theo cấu hình thực tế. Output `effective-pom` bao gồm cấu hình từ parent và profile; cần cẩn thận không chia sẻ secret hoặc thông tin nhạy cảm trong report.

Với Gradle:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency client-api
~~~

Các command dùng để **điều tra trong dự án**, và tên configuration cần chọn đúng module. Với multi-project Gradle build, có thể dùng project path như `:app:dependencies`.

Báo cáo tốt nên lưu phiên bản **đã resolve**, không chỉ phiên bản được khai báo. Một conflict hoặc substitution rule có thể khiến kết quả khác điều developer nghĩ.

## 11. Profiles và biến môi trường: chọn explicit thay vì tự đoán

Maven profiles và Gradle properties giúp cấu hình môi trường nhưng cũng là nguồn gây drift.

Maven có thể active profile theo:

- Chỉ định rõ bằng `-P`.
- Một số điều kiện trong POM như property, JDK hoặc OS.
- Settings của người dùng hoặc hệ thống theo cơ chế Maven.
- Activation trong cấu hình đã được khai báo.

Gradle có thể nhận project/system properties từ command line, environment và những vị trí `gradle.properties` được hỗ trợ. Các tầng cấu hình có thứ tự ưu tiên riêng; không nên giả định hai máy có cùng effective properties chỉ vì cùng source.

Ví dụ Maven chỉ định profile:

~~~bash
./mvnw -P integration verify
~~~

Ví dụ Gradle chỉ định property do dự án tự định nghĩa:

~~~bash
./gradlew test -PtargetEnvironment=integration
~~~

`targetEnvironment` là property minh họa; không phải Gradle tự hiểu hoặc tự tạo một environment. Build logic phải khai báo ý nghĩa rõ ràng.

### 11.1. Cấu hình nào nên là mặc định?

Chỉ dùng mặc định cho những điều **thực sự bất biến** giữa môi trường: source encoding, baseline compiler, conventions hoặc test behavior không phụ thuộc secret.

Những khác biệt có chủ đích như endpoint test, database fixture, môi trường integration hoặc private repository nên được khai báo bằng named profile/property và được chọn rõ trong CI.

Không nên:

~~~text
Nếu tên máy là "dev-laptop" thì dùng mode A;
nếu không thì tự chọn mode B.
~~~

Cách này tạo build không thể đoán trước và khó tái lập.

## 12. Secrets và repository credentials

Một dự án có thể resolve dependency trên máy developer nhưng CI fail vì credential/mirror khác. Không nên “sửa” bằng cách commit password hoặc token vào repository.

Nguyên tắc:

- Build file công bố repository URL hoặc một alias được quản lý.
- Secret đến từ cơ chế user-local hoặc CI secret store.
- CI cung cấp credential với quyền tối thiểu.
- Developer có cách cấu hình account được tài liệu hóa.
- Không in password/token trong build log hay report.
- Không đưa secret vào `gradle.properties` được commit hoặc POM công khai.
- Khi debug, kiểm tra quyền repository, mirror, TLS và artifact existence nhưng che credential.

Ví dụ Gradle đọc credential từ biến môi trường trong build script phải được thiết kế cẩn thận theo mô hình tổ chức. Một pattern minh họa:

~~~kotlin
repositories {
    maven {
        url = uri("https://repo.example.org/maven")
        credentials {
            username = providers.environmentVariable("REPO_USER").orNull
            password = providers.environmentVariable("REPO_PASSWORD").orNull
        }
    }
}
~~~

URL và tên biến là placeholder; chỉ dùng khi môi trường thực tế cung cấp và cơ chế được phép. Cần xác minh plugin/Gradle version và cách cấp quyền phù hợp. Điều quan trọng là **không gắn giá trị bí mật trực tiếp vào source**.

Với Maven, credential/mirror thường được quản lý qua `settings.xml` ở phạm vi user/CI phù hợp. Nếu server id trong POM và settings không khớp, có thể dẫn đến 401/403 dù dependency đã được khai báo đúng.

## 13. Thống nhất encoding, locale và timezone

Các khác biệt nhỏ của môi trường có thể gây test flakiness, đặc biệt khi nâng Java.

### 13.1. Encoding source

Với Gradle JavaCompile:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

Với Maven:

~~~xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Đây là encoding của **source** hoặc tài nguyên/report theo plugin tương ứng, không phải một cờ duy nhất tự điều chỉnh mọi luồng I/O của ứng dụng.

### 13.2. Runtime charset

Trên các JDK hiện đại, mặc định UTF-8 đã được chuẩn hóa trong nhiều bối cảnh, nhưng code cũ vẫn có thể giả định platform encoding hoặc sử dụng API đọc file không nêu charset. Cách bền vững là chỉ rõ encoding tại điểm đọc/ghi:

~~~java
String content = java.nio.file.Files.readString(
        path,
        java.nio.charset.StandardCharsets.UTF_8);
~~~

Nếu ứng dụng phải đọc dữ liệu lịch sử với encoding khác, cần khai báo và kiểm tra conversion thay vì mặc định UTF-8 cho mọi dữ liệu cũ.

### 13.3. Locale và timezone

Ví dụ một test định dạng ngày:

~~~java
String output = java.time.LocalDate.of(2026, 11, 12)
        .format(java.time.format.DateTimeFormatter
                .ofPattern("dd MMM yyyy", java.util.Locale.ENGLISH));
~~~

Chỉ định locale giúp output không thay đổi theo ngôn ngữ mặc định của máy.

Với thời gian thực, nên chọn rõ `ZoneId` hoặc `ZoneOffset` ở domain layer. Không dựa vào timezone mặc định nếu hợp đồng nghiệp vụ cần một zone cụ thể.

Trong Gradle test có thể đặt system property:

~~~kotlin
tasks.withType<Test>().configureEach {
    systemProperty("user.timezone", "UTC")
}
~~~

Việc đặt `user.timezone` giúp giảm drift ở một số code path, nhưng không thay thế việc thiết kế API thời gian đúng. Nếu ứng dụng cần thử nhiều timezone, nên chạy matrix test với các zone đại diện thay vì ép mọi test UTC.

### 13.4. Đồng hồ và ngẫu nhiên

Test dùng `Instant.now()` hoặc random seed không cố định có thể fail theo thời gian hoặc thứ tự chạy. Để tái lập, có thể inject `Clock`:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-11-12T00:00:00Z"),
        ZoneOffset.UTC);
~~~

`Clock`, `Instant`, `ZoneOffset` thuộc `java.time`. Test cần đảm bảo class đang kiểm tra thực sự dùng clock được inject thay vì gọi đồng hồ hệ thống trực tiếp.

## 14. Working directory, đường dẫn và hệ điều hành

IDE có thể chạy ứng dụng với working directory ở module con, terminal từ repository root, còn CI từ workspace khác. Code sử dụng đường dẫn tương đối như:

~~~java
Path file = Path.of("config/application.properties");
~~~

có thể đọc file khác hoặc không tìm thấy file.

Đối với config/resources thuộc ứng dụng, ưu tiên cách đóng gói rõ ràng:

~~~java
try (InputStream stream =
         MyApp.class.getResourceAsStream("/application.properties")) {
    if (stream == null) {
        throw new IllegalStateException("Resource not found");
    }
    // Read the resource.
}
~~~

Không phải mọi file config nên đóng trong JAR: external config, certificate hoặc secret cần đường dẫn do môi trường cung cấp. Quan trọng là **đường dẫn và ownership phải được định nghĩa**, không phụ thuộc tình cờ vào working directory của IDE.

Những khác biệt OS cần chú ý:

- Dấu phân cách classpath: `:` trên Unix và `;` trên Windows.
- Shell quoting và cách truyền biến môi trường.
- Đường dẫn phân biệt chữ hoa/thường trên những filesystem nhất định.
- Ký tự xuống dòng, file permission và executable bit của wrapper.
- Locale/timezone mặc định.
- Native library và OS architecture.
- Path length và ký tự đặc biệt trong tên thư mục.

CI có thể chạy Linux trong khi developer dùng Windows. Với dự án cần hỗ trợ cả hai, chạy một matrix hoặc ít nhất test các phần xử lý file/native code liên quan trên từng OS.

## 15. Phân biệt compile/test/package giữa IDE và build tool

Một nút “Build Project” của IDE có thể không tương đương:

~~~bash
./gradlew clean build
~~~

và cũng không đương nhiên tương đương:

~~~bash
./mvnw clean verify
~~~

Trong Gradle, `build` phụ thuộc các task và plugin đã cấu hình; trong Maven, `verify` thực hiện các phase lifecycle cùng plugin bindings. Test tùy chỉnh có thể không được nối vào lifecycle chuẩn nếu nhóm chưa khai báo.

Vì vậy, để đảm bảo CI chạy đúng bài test cần thiết:

- Xác định task/goal chuẩn cho build release.
- Đảm bảo integration test hoặc verification task cần thiết được nối vào pipeline.
- Công bố lệnh dùng cho developer và CI.
- Cho IDE chạy cùng Gradle/Maven tasks/goals khi xác nhận kết quả.
- Ghi rõ task nào IDE có thể chạy riêng để debug mà không thay thế full verification.

Ví dụ task `integrationTest` trong Gradle **không mặc định tồn tại** ở mọi dự án. Chỉ tài liệu hóa lệnh đó nếu build đã tạo task tương ứng.

## 16. Cấu hình test framework và engine discovery

Một IDE có thể chạy JUnit test bằng runner riêng nhưng CLI không phát hiện test do thiếu test engine, plugin hoặc cấu hình task.

Trong Gradle Java plugin, có thể cần khai báo nền tảng JUnit phù hợp:

~~~kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

Đồng thời dependency của JUnit API và engine phải được quản lý theo phiên bản được dự án chọn. Việc chỉ viết `useJUnitPlatform()` không tự thêm mọi library cần thiết.

Với Maven, việc test có được phát hiện/chạy có thể phụ thuộc version/cấu hình Maven Surefire/Failsafe, test naming và JUnit/Jupiter engine tương ứng. Khi IDE chạy được nhưng `./mvnw test` báo “0 tests”, hãy điều tra test discovery trước khi kết luận test pass.

Test report nên nêu số lượng test thực sự chạy. **Không có test được thực thi không phải bằng chứng test suite thành công về mặt nghiệp vụ.**

## 17. Mô phỏng CI ở local mà không giả định hoàn toàn giống production

Một môi trường CI tốt có các đặc điểm:

- Checkout sạch theo commit.
- Wrapper/build tool được pin.
- JDK được provision theo ma trận được khai báo.
- Repository access và secret được cung cấp rõ.
- Đơn vị môi trường test được quản lý.
- Không phụ thuộc IDE hay file user-local.
- Có log và artifact report.
- Có phân biệt test job, packaging job, deploy job.

Tại local, developer có thể chạy **lệnh giống CI** để tái hiện nhiều lỗi:

~~~bash
./gradlew clean test
~~~

hoặc:

~~~bash
./mvnw clean verify
~~~

Nhưng local và CI không nhất thiết phải có mọi dịch vụ giống production. Những yếu tố như database server, external API, queue hoặc TLS endpoint cần test container, môi trường integration riêng hay mock có contract rõ ràng.

Không nên yêu cầu mọi developer duy trì toàn bộ hạ tầng production ở máy cá nhân. Thay vào đó, định nghĩa **tập test có thể chạy local**, **tập test cần hạ tầng CI** và những điều mỗi tập chứng minh.

## 18. CI pipeline mẫu theo tư duy kiểm chứng

Một pipeline độc lập nhà cung cấp có thể gồm:

~~~text
Checkout commit
    |
Provision JDK/build-tool prerequisites
    |
Use committed Gradle/Maven wrapper
    |
Resolve and verify dependencies
    |
Compile and run unit tests
    |
Run contract/integration tests
    |
Test minimum supported Java runtime
    |
Package and inspect artifact
    |
Archive logs, reports, dependency and JDK metadata
    |
Promote only when gates pass
~~~

Không phải mọi bước bắt buộc nằm trong một job. Nếu có nhiều JDK hoặc hệ điều hành, dùng matrix phù hợp:

| Job | JDK compiler/build | JDK runtime test | Mục tiêu |
|---|---|---|---|
| Compile | 21 | — | Biên dịch với `--release 17` |
| Baseline runtime | 21 hoặc theo build | 17 | Xác nhận artifact chạy trên Java tối thiểu |
| Current runtime | 21 hoặc theo build | 21 | Kiểm hành vi trên JDK đích khác |
| Integration | JDK được chọn | 17/21 theo support | JDBC, HTTP, framework và serializer |
| Platform-specific | Theo build | Theo môi trường | Kiểm file/native/network behavior |

Đây là ma trận ví dụ, không phải chỉ dẫn dùng JDK 17/21 cho mọi dự án. Nếu ứng dụng chỉ hỗ trợ Java 21, không cần bắt buộc có test Java 17. Nếu sản phẩm hỗ trợ nhiều JDK, cần xác định tập đại diện và giới hạn coverage.

### 18.1. Không dùng cache CI như nguồn chân lý

CI cache có thể tăng tốc nhưng không nên khiến artifact của pipeline thay đổi theo lịch sử cache. Dependency versions phải được xác định bởi build và repository đã khai báo, còn cache chỉ là tầng tăng tốc được kiểm soát.

Nên có định kỳ kiểm tra clean resolution/build và cơ chế invalidation phù hợp. Nếu chỉ CI có cache mới chạy được mà clean CI thất bại, đó là một lỗi reproducibility cần sửa.

## 19. Quản lý môi trường integration test

Nhiều sai khác giữa IDE/CLI/CI đến từ database, message broker hoặc external service.

Ví dụ:

- IDE kết nối database cục bộ với schema S1.
- CLI dùng environment variable trỏ tới schema S2.
- CI dựng database bằng container nhưng thiếu migration.
- Test data ở máy cá nhân có record đặc biệt mà CI không có.
- Server timezone hoặc collation khác.
- Credential local có quyền cao hơn CI account.

Hướng xử lý:

1. Ghi version của database/service và cấu hình thực sự có hiệu lực.
2. Tạo schema qua migration scripts được version-control.
3. Dùng fixtures độc lập, có thể reset và không phụ thuộc dữ liệu developer.
4. Quản lý container image/digest hoặc test environment theo chính sách tái lập.
5. Tách endpoint/credential qua biến môi trường hoặc secret store.
6. Kiểm tra negative cases, timeout, lỗi quyền và network failure.
7. Đảm bảo integration test fail rõ ràng khi service không sẵn sàng, không âm thầm bỏ qua.

Nếu một test dùng service thật, cần tránh tác động dữ liệu production. Dùng môi trường test chuyên dụng và account có quyền tối thiểu.

## 20. JPMS, `--add-opens` và VM arguments

Trong migration Java, framework cũ có thể bị `InaccessibleObjectException` khi dùng deep reflection vào package nội bộ hoặc DTO nằm trong named module.

Một nguyên nhân “IDE chạy, CI lỗi” là IDE run configuration có thêm:

~~~text
--add-opens=java.base/java.lang=ALL-UNNAMED
~~~

trong khi CLI/CI không có. Nhưng sao chép cờ đó vào mọi nơi không tự động là cách sửa đúng.

Để xử lý:

- Đọc source module/package và target module từ exception.
- Xác định thư viện nào đang gọi `setAccessible`.
- Ưu tiên nâng framework hoặc chuyển sang public API được hỗ trợ.
- Nếu module thuộc dự án, dùng `opens package to framework.module` có chủ đích.
- Chỉ dùng `--add-opens` như workaround hẹp, có owner và kế hoạch loại bỏ.
- Ghi rõ JVM nào cần cờ: Gradle daemon, test worker hay application runtime.

Nếu test cần tạm cờ trong Gradle, có thể cấu hình đúng task:

~~~kotlin
tasks.withType<Test>().configureEach {
    jvmArgs("--add-opens=java.base/java.lang=ALL-UNNAMED")
}
~~~

Cấu hình này không tự truyền tới `JavaExec` hoặc production container. Khi CI/test fail, phải xác định đúng JVM có lỗi. Không nên ghi một biến `JAVA_TOOL_OPTIONS` toàn cục để mở quyền cho tất cả tiến trình nếu chỉ một thư viện cần sửa.

## 21. Khác biệt TLS và truststore

Một ứng dụng dùng HTTPS/database TLS có thể thất bại chỉ ở CI:

~~~text
javax.net.ssl.SSLHandshakeException:
PKIX path building failed
~~~

Điều này có thể do:

- CI dùng một JDK distribution/truststore khác local.
- Container thiếu CA nội bộ đã được cài trên máy developer.
- Endpoint qua proxy hoặc DNS khác.
- Hostname của URL không khớp certificate SAN.
- Chứng chỉ thiếu intermediate chain hoặc hết hạn.
- JDK update/build có security algorithm constraints khác.

Không nên sửa bằng một TrustManager chấp nhận mọi chứng chỉ, hoặc tắt hostname verification. Cách đúng là xác minh chain, CA, DNS, endpoint và truststore của môi trường theo chính sách tổ chức.

Trong hồ sơ test, ghi **loại truststore/CA** và đường dẫn quản lý, nhưng không ghi password, private key hoặc token. Nếu CI cần certificate nội bộ, provision qua cơ chế bảo mật phù hợp; không dựa vào thao tác thủ công trên máy cá nhân.

## 22. Maven/Gradle plugin và build logic khác nhau qua môi trường

Ngoài dependency runtime, plugin build có thể gây drift:

- Gradle plugin hoặc Maven plugin được chọn bằng version khác.
- Một profile chỉ active trên một JDK/OS.
- Plugin truy cập JDK internals và chạy lỗi trên JDK mới.
- Build script dùng file hoặc command chỉ có ở máy developer.
- Plugin code generation không chạy trong lifecycle CI.
- Một task dựa vào biến môi trường chưa được khai báo.
- Script dựa vào thời gian hiện tại hoặc thứ tự file system.
- Build cache che mất missing input/output declaration.

Cách tiếp cận:

1. Pin version build tool và plugin.
2. Định nghĩa task dependencies và inputs/outputs rõ ràng.
3. Đảm bảo generated sources tạo được từ checkout sạch.
4. Kiểm tra JDK runtime của từng plugin.
5. Review profile activation và system properties.
6. Khi debug, chạy build với log phù hợp, nhưng che secrets.
7. Nếu lỗi chỉ ở incremental build, so sánh với clean build để khoanh vùng caching.

Không nên khắc phục bằng cách bật `clean` ở mọi task mãi mãi nếu lỗi do task khai báo input/output sai; có thể cần sửa build logic.

## 23. Một số lỗi điển hình và cách khoanh vùng

| Biểu hiện | Nguyên nhân có khả năng | Hướng kiểm chứng |
|---|---|---|
| IDE compile pass, Gradle CLI fail | IDE dùng JDK/classpath khác; chưa import sync | So sánh Project SDK, Gradle JVM, toolchain và resolved graph |
| Local CLI pass, CI `invalid source release` | Compiler ở CI thấp hơn release cấu hình | Ghi `javac -version` và compiler toolchain |
| CI `UnsupportedClassVersionError` | Runtime cũ hơn bytecode hoặc dependency | Kiểm class-file version và JDK test worker |
| Maven local pass, CI thiếu artifact | Local repository có JAR thủ công; mirror/credential khác | Kiểm repo, settings, dependency tree và clean resolution |
| IDE test pass, Maven báo 0 tests | Test runner/engine/plugin discovery khác | Kiểm Surefire/Failsafe, JUnit engine và report |
| Gradle test fail vì timezone | JVM/user.timezone hoặc test dựa vào default | Đặt contract thời gian và test zone rõ |
| Code generation CI thiếu class | Generated source không được tạo từ build | Kiểm annotation processor và task dependencies |
| Test CI lỗi `InaccessibleObjectException` | JDK/framework và module openness khác | Stack trace, dependency version, đúng test JVM |
| CI TLS handshake fail | Truststore/CA/hostname/proxy khác | Certificate chain và JDK security config |
| Khác biệt kết quả `getObject` JDBC | Driver/server/session settings khác | Kiểm mapping, driver version, timezone, fixtures |
| Local dùng config mặc định khác CI | Profiles/environment activation hoặc precedence khác | In effective config có che secrets |
| Artifact khác checksum | Non-reproducible input, metadata timestamp, dependency drift | So sánh build inputs và reproducible packaging |

Bảng chỉ là hướng điều tra; một lỗi có thể có nhiều nguyên nhân. Cần thu thập bằng chứng trước khi thay đổi build hoặc code.

## 24. Quy trình điều tra khi IDE, CLI và CI cho kết quả khác

### Bước 1: Ghi ba lần chạy trên cùng commit

Xác nhận IDE, terminal và CI đang dùng cùng source revision. Nếu một môi trường chưa sync branch hoặc có file chưa commit, không thể so sánh như cùng một build.

### Bước 2: Ghi command line và vai trò JVM

Nêu chính xác task/goal được gọi, JDK chạy build tool, compiler/toolchain, test launcher, VM args, working directory, OS và environment. Không chỉ ghi “Java 21”.

### Bước 3: So sánh cấu hình hiệu lực

Kiểm Gradle resolved graph hoặc Maven effective POM/active profiles; đối chiếu dependency versions, repository và plugin versions. Không suy luận từ POM/build.gradle rời rạc.

### Bước 4: Tách lỗi build và lỗi runtime

Nếu lỗi compile, kiểm source, target, release và compiler classpath. Nếu lỗi khi tải class, kiểm JDK runtime, dependency và class-file version. Nếu hành vi test lệch, kiểm dữ liệu, timezone, locale, network và framework settings.

### Bước 5: Tái hiện bằng wrapper

Dùng lệnh chuẩn của repository từ terminal hoặc môi trường gần CI. Nếu IDE runner khác, thử ủy quyền task/goal cho build tool để xác định khác biệt nằm ở đâu.

### Bước 6: Thu nhỏ thay đổi

Không thay hàng loạt JDK, plugin và dependency để “thử”. Chọn thay đổi nhỏ nhất đủ tái hiện lỗi: một module, một test, một dependency hoặc một cấu hình JVM.

### Bước 7: Sửa ở đúng nguồn khai báo

Ví dụ:

- Sai JDK/compiler → sửa toolchain hoặc CI provisioning.
- Sai dependency → sửa build dependency/constraint.
- Sai test runner → sửa build test plugin/task.
- Sai timezone → sửa contract thời gian và cấu hình test.
- Sai certificate → sửa truststore/endpoint đúng môi trường.
- Reflection không được phép → nâng framework hoặc mở package có kiểm soát.

Không nên chỉ sửa IDE-local setting nếu lỗi thuộc build definition và mọi developer/CI đều cần quy tắc ấy.

### Bước 8: Chạy lại phép kiểm tương đương

Thực hiện lệnh build/test được định nghĩa cho cả ba môi trường liên quan, ghi kết quả và giới hạn. Nếu CI có test sâu hơn local, vẫn cần phân biệt “tương đương ở tầng unit” với “tương đương toàn pipeline”.

### Bước 9: Cập nhật tài liệu và guardrails

Sau khi sửa, commit cấu hình thuộc repository; cập nhật setup guide, version requirement, profile selection và CI matrix. Thêm test hoặc kiểm tra đơn giản để tránh cấu hình drift tái diễn.

## 25. Mẫu hồ sơ bằng chứng môi trường

Một bản ghi có thể giúp đối chiếu nhiều lần chạy:

~~~yaml
buildEvidence:
  commit: "example-commit-id"
  tool:
    name: "Gradle"
    wrapperVersion: "record actual version"
  compile:
    compilerJdk: "21"
    javaRelease: "17"
    sourceEncoding: "UTF-8"
  tests:
    runtimeJdk: "17"
    timezone: "UTC"
    locale: "record required locale"
  dependencyGraph:
    reference: "archived report path"
  environment:
    os: "linux-x64"
    ciImageDigest: "record exact image digest"
  results:
    compilation: "PASS"
    unitTests: "PASS"
    integrationTests: "NOT_RUN"
  limitations:
    - "windows-runtime-not-tested"
    - "external-plugin-consumers-not-covered"
~~~

Đây là dữ liệu minh họa, không phải kết quả kiểm thử đã diễn ra. Khi áp dụng cần lưu timestamp, JDK vendor/build, resolved dependency checksums, test report, artifact digest và những trường môi trường thực sự có ý nghĩa.

Để tránh lộ thông tin, không xuất nguyên environment variables hoặc Maven settings có secret vào report. Chỉ ghi những tên biến/cấu hình cần thiết và các giá trị không nhạy cảm.

## 26. Thiết kế guardrail để cấu hình không trôi lại

Sau khi thống nhất môi trường, nên biến các giả định quan trọng thành phép kiểm tự động:

| Ràng buộc | Guardrail gợi ý |
|---|---|
| Build tool version | Wrapper bắt buộc trong tài liệu/pipeline |
| Compiler release | Cấu hình `--release` tập trung và compile test |
| Test JDK tối thiểu | CI job chạy trên đúng JDK baseline |
| Dependency consistency | Lock/verification và resolved graph report khi cần |
| Test discovery | Kiểm số lượng test và test engine được nạp |
| Generated source | Clean checkout build và khai báo task dependencies |
| Encoding/timezone | Cấu hình rõ trong build và test fixture |
| Profiles | Pipeline chọn profile bằng tên, không theo hostname |
| Private repository | Secret store và permission rõ; kiểm 401/403 |
| Artifact identity | Ghi digest, commit và dependency metadata |
| Module/JVM flags | Giới hạn VM args và review workaround |
| Compatibility contracts | Unit, integration và consumer tests theo rủi ro |

Một guardrail phải kiểm điều kiện thật. Ví dụ, lệnh `./gradlew test` trả exit code 0 trong khi **không có test nào được chạy** không đáp ứng mục tiêu “test suite đã chạy đủ”.

## 27. Maven và Gradle: điểm giống và khác khi đồng bộ ba môi trường

| Mối quan tâm | Gradle | Maven |
|---|---|---|
| Entrypoint chuẩn | `gradlew` / `gradlew.bat` | `mvnw` / `mvnw.cmd` |
| Compiler target | `JavaCompile.options.release` | Maven Compiler Plugin `release` |
| Chọn JDK | Java toolchains, daemon JVM và task launchers | Maven runtime, Maven Toolchains và plugin support |
| Dependency versions | Catalog, constraints, platform/BOM, lock | Dependency management, BOM, POM hierarchy |
| Plugin versions | Plugin management/build logic | Plugins, pluginManagement và parent POM |
| Config biến thể | Properties, tasks, source sets, build logic | Profiles, properties, lifecycle/plugin bindings |
| Test execution | Gradle Test task/JUnit platform, custom tasks | Surefire/Failsafe và test engines |
| Dependency investigation | `dependencies`, `dependencyInsight` | `dependency:tree`, `help:effective-pom` |
| Điểm dễ lệch IDE | IDE JDK, Gradle JVM, delegated vs IDE runner | Maven runtime, active profiles, IDE runner và import |

Không nhất thiết chuyển đổi giữa Maven và Gradle để loại bỏ drift. Một build có thể tái lập bằng cả hai công cụ nếu được thiết kế và quản lý đúng. Chỉ nên đổi build tool khi có lý do riêng, vì đó cũng là một thay đổi lớn cần kiểm thử.

## 28. Những hiểu lầm thường gặp

**“Project SDK trong IDE đã là Java 21 nên CI cũng phải là Java 21.”** Không. CI dùng JDK riêng; Gradle/Maven có JVM, toolchain và test launcher riêng.

**“Wrapper giải quyết mọi khác biệt.”** Wrapper giúp cố định build tool, không cố định mọi JDK, dependency, secret, OS và test environment.

**“Cấu hình `sourceCompatibility = 17` đủ để bảo đảm không dùng API mới.”** Không hoàn toàn. Khi compiler hỗ trợ, cần `--release 17` để giới hạn API Java SE.

**“Gradle toolchain Java 21 nghĩa là test chạy Java 21.”** Test launcher có thể được cấu hình riêng; không được suy đoán.

**“Maven `<release>17</release>` nghĩa là production đang chạy Java 17.”** Đây là compiler configuration, không tự chọn runtime triển khai.

**“IDE có Lombok plugin nên annotation processor chắc chắn chạy trên CI.”** Plugin IDE không thay thế build-time annotation processor dependency/configuration.

**“Một test pass trong IDE chứng minh `mvn verify` hoặc `gradle build` pass.”** Có thể là runner, JDK, classpath và lifecycle khác nhau.

**“Local dependency cache có artifact thì repository configuration đúng.”** CI clean environment có thể không resolve được artifact ấy.

**“Đặt `user.timezone=UTC` sửa mọi lỗi thời gian.”** Không. Dữ liệu thời gian phải có semantics đúng; cần test các timezone khác nếu hợp đồng yêu cầu.

**“Có thể copy toàn bộ `gradle.properties` và `settings.xml` từ developer lên CI.”** Có thể lộ secret hoặc mang path cục bộ; phải tách cấu hình công khai khỏi credential.

**“Cờ `--add-opens` có trong IDE nên cứ đưa vào production.”** Phải xác định root cause, đúng JVM, phạm vi cờ và giải pháp lâu dài.

**“Build xanh trên CI nghĩa là artifact dùng được trên mọi JVM hỗ trợ.”** Cần runtime test trên JDK tối thiểu và các môi trường được công bố.

**“Cần đồng nhất 100% OS/JDK để test có giá trị.”** Không phải lúc nào cũng có thể; cần ghi các khác biệt có chủ đích và chạy matrix đủ để hỗ trợ kết luận.

## 29. Checklist triển khai trong dự án

- [ ] Đã xác định build tool chính và wrapper được commit, có nguồn tải đáng tin cậy.
- [ ] Đã xác nhận IDE, CLI, CI sử dụng cùng commit và build definition.
- [ ] Đã ghi JDK runtime của IDE, Gradle/Maven, compiler, test và application.
- [ ] Đã đặt compiler release/source target theo baseline Java được hỗ trợ.
- [ ] Đã provision Java toolchains hoặc Maven compiler/toolchain đúng phiên bản.
- [ ] Đã cấu hình test runner và JVM test, xác nhận test thực sự được thực thi.
- [ ] Đã đưa annotation processors, generated source và code generators vào build.
- [ ] Đã quản lý dependency, plugin versions và repository theo cấu hình chung.
- [ ] Đã kiểm resolved graph, profile và configuration hiệu lực.
- [ ] Đã loại bỏ dependency chỉ tồn tại trong IDE hoặc cache cục bộ.
- [ ] Đã chọn rõ working directory, external config và resource paths.
- [ ] Đã kiểm soát UTF-8, timezone, locale, clock và fixture test.
- [ ] Đã tách secret khỏi repository, dùng credential store phù hợp cho developer/CI.
- [ ] Đã kiểm TLS/truststore và module/JVM flags mà không nới bảo mật tùy tiện.
- [ ] Đã xác định những test có thể chạy local và những test cần hạ tầng CI.
- [ ] Đã chạy clean build trong môi trường tái lập và lưu report.
- [ ] Đã có CI JDK/OS matrix theo support policy và giới hạn nguồn lực.
- [ ] Đã lưu commit, artifact digest, test results và các phạm vi chưa kiểm.
- [ ] Đã tạo guardrail tránh drift tái diễn sau migration.

## Kết luận

**Loại bỏ khác biệt cấu hình giữa IDE, dòng lệnh và CI** không phải là việc buộc mọi tiến trình sử dụng cùng một JVM hoặc cùng một giao diện. Đó là việc biến những quyết định quan trọng thành cấu hình có thẩm quyền, được version-control và có thể kiểm chứng: wrapper cho build tool, compiler `--release` và toolchain cho Java, dependency management cho artifact, task/goal cho test, và CI provisioning cho môi trường.

Khi Java Advance Compatibility Migration, hãy xem IDE như một cách sử dụng build chuẩn, không phải nguồn cấu hình độc lập. Kiểm tra từng vai trò JVM, resolved graph, profiles, generated source, encoding, timezone, repository và security settings; sau đó chứng minh tính tương đương bằng build/test trên cùng commit với log và artifact có thể truy vết. Những khác biệt có chủ đích giữa compiler, test JDK và production runtime vẫn hợp lệ nếu được mô tả và kiểm tra rõ ràng. Mục tiêu cuối cùng là: **một thay đổi Java hoặc dependency cho kết quả có thể giải thích, tái hiện và triển khai an toàn — bất kể thao tác được bắt đầu từ IDE, terminal hay pipeline CI.**
