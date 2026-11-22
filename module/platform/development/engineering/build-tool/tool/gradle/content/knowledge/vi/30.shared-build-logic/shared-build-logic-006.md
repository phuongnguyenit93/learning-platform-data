# Convention plugin cho Java, kiểm thử, chất lượng và xuất bản trong Gradle

## 1. Vấn đề: build logic bị sao chép giữa nhiều module

Một hệ thống Java thường có nhiều subprojects: thư viện dùng chung, API, CLI, ứng dụng và công cụ nội bộ. Nếu mỗi module lặp lại các cấu hình **Java toolchain**, **JUnit 5**, **Checkstyle**, **JaCoCo** và **maven-publish**, những khác biệt nhỏ sẽ xuất hiện:

- Module A biên dịch Java 17 nhưng module B vẫn dùng sourceCompatibility cũ.
- Có module chạy JUnit Jupiter, module khác quên **useJUnitPlatform()**.
- Một module tạo JUnit XML để CI đọc, module khác chỉ in console logs.
- Module A có kiểm tra coverage nhưng module B không nối verification task vào **check**.
- Một số project dùng Checkstyle 10.x, số khác dùng cấu hình hoặc phiên bản khác.
- Mọi module đều lỡ áp dụng **maven-publish**, kể cả ứng dụng không cần phát hành thư viện.
- Khi đổi chính sách JDK/quality gate, nhóm phải sửa hàng chục build.gradle.
- Các khối **allprojects {} / subprojects {}** ở root có thể cấu hình chéo khiến build khó hiểu và ảnh hưởng khả năng mở rộng.

Giải pháp là đóng gói **các quy ước Gradle** thành những **convention plugins** có tên và phạm vi rõ. Mỗi module sẽ tự khai báo loại quy ước mình muốn dùng, thay vì chờ root build script thay đổi hành vi của module từ bên ngoài.

Bài học thuộc nhóm **Build logic dùng chung**, với đề tài **“Convention plugin cho Java, kiểm thử, chất lượng và xuất bản”**.

Sau bài này, bạn có thể:

1. Phân biệt script plugin, precompiled script plugin, binary plugin và convention plugin.
2. Tổ chức build logic trong **build-logic** dạng included build thay vì nhân bản build.gradle.
3. Đăng ký **Groovy DSL precompiled script plugins** bằng **groovy-gradle-plugin** và áp dụng bằng plugin IDs.
4. Thiết kế một lớp quy ước Java 17, một lớp JUnit 5, một lớp Checkstyle/JaCoCo và một lớp Maven publication.
5. Cho các convention plugins **ghép nhau** mà không áp dụng xuất bản cho mọi project.
6. Quản lý đúng ranh giới giữa repositories của main build và của included build.
7. Dùng **tasks.named** và **configureEach** để giữ cấu hình lười, tránh eager task realization.
8. Nối **test → JaCoCo report → verification** và phân biệt HTML/XML report với quality gate.
9. Thiết lập **publication chỉ trên Java library**, tạo JAR, sources JAR và Javadoc JAR cùng POM.
10. Chạy lab Java 17 gồm **:core** và **:app**, kiểm chứng bằng Gradle Wrapper và javac/java với stdout cụ thể.
11. Hiểu vì sao version catalogs/root configurations không tự kế thừa sang build-logic.
12. Nâng cấp kiến trúc lên binary plugin, plugin tests, CI và release signing khi cần.

## 2. Convention plugin là gì?

Một convention plugin là Gradle plugin chứa **các mặc định/quy tắc xây dựng** cho một loại project. Nó có thể:

- Apply các core plugins như **java**, **java-library**, **checkstyle**, **jacoco**, **maven-publish**.
- Cấu hình Java toolchain và compiler options.
- Thêm dependencies đúng scope, như **testImplementation**.
- Cấu hình **Test** tasks và JUnit XML/HTML reports.
- Thiết lập Checkstyle và JaCoCo verification rules.
- Tạo publications, thêm sources/Javadoc artifacts, cấu hình nơi phát hành.
- Đăng ký task mới hoặc áp dụng convention plugin khác.
- Bộc lộ extension cho module ghi đè các giá trị cấu hình khi cần.

Từ “convention” nhấn mạnh **một chính sách dùng chung, được áp dụng có chủ đích**. Plugin đó không nhất thiết phải có một class implement Plugin<Project>; một precompiled script plugin đã là plugin hợp lệ.

Ví dụ thay vì viết lại trong năm module:

~~~groovy
plugins {
    id 'java-library'
    id 'checkstyle'
    id 'jacoco'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

mỗi module chỉ cần:

~~~groovy
plugins {
    id 'team.java-quality'
}
~~~

**Điều kiện:** Plugin ID **team.java-quality** phải được cung cấp bởi **build-logic** hoặc plugin repository. Đây không phải core Gradle plugin có sẵn chỉ nhờ viết tên.

### 2.1. Convention không phải apply-from script

Một cách cũ là:

~~~groovy
apply from: rootProject.file('gradle/common-java.gradle')
~~~

Script plugin kiểu **apply from** có thể tái dùng một đoạn cấu hình nhỏ, nhưng không cung cấp đầy đủ mô hình plugin IDs, plugin resolution/classpath, testing/publishing và cấu trúc riêng như precompiled/binary plugin. Khi chính sách trở nên quan trọng và có nhiều người dùng, convention plugin là mô hình rõ ràng hơn.

### 2.2. Convention khác với core plugin

**java-library** là plugin có sẵn của Gradle, thêm Java API/runtime variants và tasks. **team.java-publish** sẽ là plugin **do đội dự án viết**, áp dụng/configure core plugins để tạo hành vi đúng chuẩn tổ chức.

Không thay thế Java plugin bằng tự đăng ký hàng chục tasks. Hãy **kết hợp plugin có sẵn**, để Gradle tiếp tục hiểu task inputs/outputs, variants, lifecycle và dependency graph.

## 3. Ba cách viết custom plugin

| Loại | Nơi viết | Cách dùng | Phù hợp |
| --- | --- | --- | --- |
| **Script plugin** | Một file Gradle script | **apply from:** | Thử nghiệm/small local script |
| **Precompiled script plugin** | **src/main/groovy/*.gradle** hoặc **src/main/kotlin/*.gradle.kts** | **plugins { id '...' }** | Conventions ngắn, dùng lặp lại giữa các modules |
| **Binary plugin** | Java/Groovy/Kotlin class implement **Plugin<Project>** | Plugin ID đăng ký qua **java-gradle-plugin** | Logic phức tạp, API/extension có kiểu, kiểm thử/phát hành rộng |
| **Convention plugin** | Một precompiled hoặc binary plugin | Plugin ID mô tả chính sách | Java/test/quality/publish conventions |

Đây là cách phân loại theo vai trò: convention plugin **không phải loại thứ tư loại trừ binary plugin**. Một binary plugin cũng có thể là convention plugin nếu nhiệm vụ của nó là cấu hình những plugin khác.

### 3.1. Groovy DSL và Kotlin DSL

Nếu codebase dùng **build.gradle**, có thể tạo Groovy precompiled scripts:

~~~text
build-logic/src/main/groovy/team.java-base.gradle
build-logic/src/main/groovy/team.java-tests.gradle
~~~

Nếu dùng **build.gradle.kts**, cách phổ biến là:

~~~text
build-logic/src/main/kotlin/team.java-base.gradle.kts
build-logic/src/main/kotlin/team.java-tests.gradle.kts
~~~

Groovy source build dùng plugin **groovy-gradle-plugin**; Kotlin DSL source build dùng **kotlin-dsl**. Các ví dụ runnable trong bài thống nhất **Groovy DSL** để tránh trộn cú pháp giữa hai DSL. Phần sau có hướng chuyển đổi khi cần.

### 3.2. Plugin ID từ tên file

Tệp:

~~~text
build-logic/src/main/groovy/team.java-tests.gradle
~~~

tạo plugin ID:

~~~groovy
plugins {
    id 'team.java-tests'
}
~~~

Nếu đặt package declaration hoặc thay directory/package của plugin, cách xác định ID có thể thay theo Gradle plugin source conventions. Với lab này ta **không khai báo package trong precompiled scripts**, để plugin ID chính xác là tên file bỏ hậu tố **.gradle**.

## 4. Tại sao nên có build-logic included build?

Gradle hỗ trợ hai nơi phổ biến để lưu shared build logic:

1. **buildSrc/**: thư mục đặc biệt được Gradle nhận diện, compile và đưa lên classpath build scripts tự động.
2. **build-logic/**: một Gradle build độc lập, được root settings thêm bằng **includeBuild**.

Trong các dự án có nhiều module và conventions có thể phát triển độc lập, tài liệu Best Practices hiện hành của Gradle ưu tiên **build-logic included build**. Nó có settings/build riêng, dễ kiểm thử và có ranh giới rõ hơn so với buildSrc. Không có nghĩa buildSrc “sai”: buildSrc vẫn đơn giản và hợp lý cho thử nghiệm nhỏ.

### 4.1. Hình dung mối quan hệ

~~~text
convention-lab/                main Gradle build
├── settings.gradle
├── core/                      subproject :core
│   └── build.gradle
├── app/                       subproject :app
│   └── build.gradle
└── build-logic/               included Gradle build
    ├── settings.gradle
    ├── build.gradle
    └── src/main/groovy/
        ├── team.java-base.gradle
        ├── team.java-tests.gradle
        ├── team.java-quality.gradle
        └── team.java-publish.gradle
~~~

**:core** và **:app** là subprojects của main build. **build-logic** là **included build độc lập**, không phải **:build-logic** project dependency của production code.

Không dùng:

~~~groovy
dependencies {
    implementation project(':build-logic')
}
~~~

để đưa convention plugin vào classpath ứng dụng. Build logic chạy lúc **Gradle cấu hình build**, không phải lúc JVM chạy ứng dụng Java. Đó là hai classpaths khác nhau.

### 4.2. Include ở settings

Một cách tiêu chuẩn:

~~~groovy
pluginManagement {
    includeBuild('build-logic')
}
~~~

làm các plugin của build-logic khả dụng cho **plugins {}**. Một included build cung cấp project plugins cũng có thể được đưa vào bằng **includeBuild('build-logic')** ở top-level settings. Dùng **pluginManagement.includeBuild** trong lab để nhấn mạnh plugin resolution sớm; trường hợp plugin áp dụng trong chính settings cần include theo đúng pluginManagement lifecycle.

### 4.3. build-logic có settings riêng

File:

~~~groovy
// build-logic/settings.gradle
rootProject.name = 'build-logic'
~~~

có vai trò xác định root project của included build. Nó **không tự kế thừa** dependency repositories, version catalog, plugins hoặc build script configuration từ settings của main build. Các phần dùng chung phải được thiết kế/công bố rõ.

## 5. Thiết kế các convention plugin thành các lớp

Không nên có một plugin “mega-conventions” tự apply mọi thứ. Một ứng dụng CLI có thể cần Java, JUnit, Checkstyle, JaCoCo nhưng **không cần Maven publication**; một thư viện cần thêm **java-library** và **maven-publish**.

Trong lab sẽ có bốn plugin:

| Plugin ID | Áp dụng/configure | Ai sử dụng? |
| --- | --- | --- |
| **team.java-base** | java, Java 17 toolchain, UTF-8, --release 17 | Mọi Java module |
| **team.java-tests** | team.java-base, JUnit Jupiter, test tasks/reports | Mọi Java module có test |
| **team.java-quality** | team.java-tests, Checkstyle, JaCoCo, coverage verification | Các modules cần quality gate |
| **team.java-publish** | team.java-quality, java-library, maven-publish, sources/Javadoc, local staging | Chỉ những libraries cần publish |

Điều này tạo một đồ thị:

~~~text
team.java-publish
  ├── team.java-quality
  │    ├── team.java-tests
  │    │    └── team.java-base
  │    │         └── java
  │    ├── checkstyle
  │    └── jacoco
  ├── java-library
  └── maven-publish

:core
  └── team.java-publish

:app
  ├── application
  └── team.java-quality
~~~

Từ đó:

- **:core** là Java library, có JUnit, Checkstyle, JaCoCo và publication.
- **:app** là Java application, có JUnit, Checkstyle, JaCoCo và **không có publication**.
- **Mỗi project tự khai báo plugin policy** trong build.gradle; root không cần viết **subprojects {}** áp dụng lén plugin.
- Core/Java plugin có thể được áp dụng lặp gián tiếp; Gradle quản lý plugin application để không tạo hai Java plugin instances độc lập vì trùng ID.

### 5.1. Quy ước là mặc định, module có thể thêm chuyên biệt

Module có thể thêm:

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

mà không cần sửa convention plugin. Convention nên chứa **chính sách chung**, còn business dependencies và entrypoints nằm ở module tương ứng.

### 5.2. Không ép mọi plugin vào mọi module

Một Java library không cần **application** plugin chỉ để build. Một CLI app không cần **maven-publish** khi chỉ chạy/đóng gói distribution. Một integration-test-only module có thể dùng plugin khác và quality gates riêng. Tách các plugin theo trách nhiệm giúp hệ thống dễ mở rộng và giảm task count.

## 6. Lab hoàn chỉnh: hai Java 17 modules với build-logic

Ta xây project **convention-lab** có:

- **:core** — Java library cung cấp câu chào và được xuất bản vào Maven repository thử nghiệm trong **build/staging-repo** của chính module.
- **:app** — Java application sử dụng **project(':core')**.
- **build-logic** — bốn precompiled convention plugins Groovy DSL.
- **JUnit 5** — hai test methods trong core, hai test methods trong app.
- **Checkstyle** — kiểm tra import rules theo một XML config nằm ở root, tạo report.
- **JaCoCo** — tạo HTML/XML coverage reports và áp dụng một coverage gate đơn giản, có thể điều chỉnh.
- **maven-publish** — publication của core có JAR, sources JAR, Javadoc JAR, POM và Gradle metadata (theo Gradle publish behavior).
- **Java 17** — có lệnh độc lập javac/java để xác minh code sản phẩm.

### 6.1. Cấu trúc đầy đủ

~~~text
convention-lab/
├── settings.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── config/
│   └── checkstyle/
│       └── checkstyle.xml
├── build-logic/
│   ├── settings.gradle
│   ├── build.gradle
│   └── src/main/groovy/
│       ├── team.java-base.gradle
│       ├── team.java-tests.gradle
│       ├── team.java-quality.gradle
│       └── team.java-publish.gradle
├── core/
│   ├── build.gradle
│   ├── src/main/java/org/example/core/Messages.java
│   └── src/test/java/org/example/core/MessagesTest.java
└── app/
    ├── build.gradle
    ├── src/main/java/org/example/app/Main.java
    └── src/test/java/org/example/app/MainTest.java
~~~

**Wrapper** được tạo một lần bằng Gradle CLI tương thích, commit các file vào repository. Để chạy lab cần JDK 17, Gradle Wrapper tương thích và kết nối tới Maven Central/mirror có JUnit, Checkstyle và JaCoCo dependencies. Một Gradle 9.x hiện đại phù hợp với các APIs đã trình bày; khi nâng phiên bản hãy kiểm tra release notes và plugin compatibility.

### 6.2. Root settings.gradle

~~~groovy
pluginManagement {
    includeBuild('build-logic')
}

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        mavenCentral()
    }
}

rootProject.name = 'convention-lab'
include 'core', 'app'
~~~

Giải thích:

1. **pluginManagement.includeBuild('build-logic')** làm các plugin IDs trong build-logic khả dụng cho subprojects.
2. **dependencyResolutionManagement** quản lý nơi resolve JUnit/Checkstyle/JaCoCo libraries cho main build.
3. **FAIL_ON_PROJECT_REPOS** không cho phép tùy ý thêm repositories vào từng project; điều này hỗ trợ quản trị dependency provenance.
4. **include 'core', 'app'** tạo hai subprojects trong **main build**, không tạo included builds cho code nghiệp vụ.
5. Không cần **subprojects {}** hoặc **allprojects {}** để áp dụng conventions.

Nếu tổ chức dùng internal Maven mirror, thay **mavenCentral()** bằng repository đã được phê duyệt cùng authentication/trust policy. Không tắt TLS verification để sửa lỗi proxy.

### 6.3. build-logic/settings.gradle

~~~groovy
rootProject.name = 'build-logic'
~~~

Đây là Gradle settings riêng. Nó không tự kế thừa root **dependencyResolutionManagement** của main build.

### 6.4. build-logic/build.gradle

~~~groovy
plugins {
    id 'groovy-gradle-plugin'
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}
~~~

**groovy-gradle-plugin** cho phép các file **src/main/groovy/*.gradle** trở thành precompiled script plugins.

- Với **core plugins** như java, jacoco, checkstyle và maven-publish, lab không cần khai báo implementation dependency cho một plugin bên thứ ba.
- Nếu precompiled plugin muốn áp dụng một **external community plugin**, cần khai báo artifact/plugin implementation trên **build-logic** classpath, không chỉ thêm plugin ID chưa có.
- **repositories** ở đây phục vụ build-logic, không trở thành main application repositories.
- Không dùng **application dependencies** của app để cung cấp classpath cho build-logic.

### 6.5. Plugin 1: team.java-base.gradle

Tạo **build-logic/src/main/groovy/team.java-base.gradle**:

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
    options.encoding = 'UTF-8'
    options.release.set(17)
}
~~~

Đây là plugin **độc lập** sau khi build-logic được include. Nó:

- Apply core **java** plugin.
- Chọn Java toolchain version **17**.
- Đặt encoding UTF-8 để mã Java có Unicode ổn định trên máy phát triển/CI.
- Dùng **options.release.set(17)** cho Java compiler để giới hạn API/classfile compatibility với Java 17.
- Dùng **configureEach** thay vì **tasks.withType(...).all** hoặc eager **getByName**.

**Toolchain** chọn compiler/JDK khi Gradle provisioning cho phép. **--release** kiểm soát Java API/classfile target; một runtime dependency JAR có bytecode Java cao hơn vẫn có thể làm ứng dụng fail khi chạy Java 17. Hãy kiểm soát dependency versions và kiểm thử trên target JDK.

### 6.6. Plugin 2: team.java-tests.gradle

Tạo **build-logic/src/main/groovy/team.java-tests.gradle**:

~~~groovy
plugins {
    id 'team.java-base'
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()

    reports {
        html.required = true
        junitXml.required = true
    }

    testLogging {
        events 'failed', 'skipped'
    }
}
~~~

Plugin này **ghép** Java conventions với JUnit 5. Mỗi consumer áp dụng **team.java-tests** sẽ có:

- JUnit Jupiter test API/engine theo dependency **testImplementation**.
- JUnit Platform Launcher trên **testRuntimeOnly**.
- **useJUnitPlatform()** cho mọi task loại **Test**, bao gồm những Test tasks được đăng ký thêm sau này.
- HTML/JUnit XML reports được yêu cầu.
- Chỉ log failed/skipped events để console không bị quá tải.

**Không đưa JUnit vào implementation** vì ứng dụng production thường không cần JUnit test libraries. **testRuntimeOnly** cũng không đi vào JAR production theo Java source sets model.

### 6.7. Plugin 3: team.java-quality.gradle

Tạo **build-logic/src/main/groovy/team.java-quality.gradle**:

~~~groovy
plugins {
    id 'team.java-tests'
    id 'checkstyle'
    id 'jacoco'
}

checkstyle {
    toolVersion = '10.24.0'
    configFile = file("$rootDir/config/checkstyle/checkstyle.xml")
    maxWarnings = 0
}

jacoco {
    toolVersion = '0.8.13'
}

tasks.named('test') {
    finalizedBy(tasks.named('jacocoTestReport'))
}

tasks.named('jacocoTestReport') {
    dependsOn(tasks.named('test'))

    reports {
        xml.required = true
        html.required = true
    }
}

tasks.named('jacocoTestCoverageVerification') {
    dependsOn(tasks.named('test'))

    violationRules {
        rule {
            limit {
                counter = 'LINE'
                value = 'COVEREDRATIO'
                minimum = 0.20
            }
        }
    }
}

tasks.named('check') {
    dependsOn(tasks.named('jacocoTestCoverageVerification'))
}
~~~

**Giải thích đầy đủ:**

1. Áp dụng **team.java-tests** nên tự có Java 17 + JUnit setup.
2. **checkstyle** tạo **checkstyleMain**, **checkstyleTest**, cấu hình chất lượng code bằng rules XML.
3. **jacoco** instrument Test JVM để ghi coverage execution data và tạo **jacocoTestReport**/**jacocoTestCoverageVerification**.
4. **configFile** trỏ tới file XML tại **rootDir/config/checkstyle/**. Đây là **quy ước cố ý**: các modules trong main build cùng dùng một policy file. Nếu đem plugin sang build khác, cần mang/configure policy resource tương ứng.
5. **maxWarnings = 0** nghĩa là warnings cũng có thể làm check fail (số lỗi mặc định của Checkstyle plugin cũng được kiểm soát).
6. **test.finalizedBy(jacocoTestReport)** yêu cầu tạo report sau test task khi có thể.
7. **jacocoTestReport.dependsOn(test)** xác định test cần chạy trước report; JaCoCo plugin không tự đảm bảo dependency này theo mặc định.
8. **jacocoTestCoverageVerification.dependsOn(test)** bảo đảm có execution data trước khi kiểm tra coverage.
9. **check.dependsOn(jacocoTestCoverageVerification)** thêm coverage verification vào quality lifecycle. Gradle mặc định **không** tự gắn coverage verification vào **check**.
10. Ngưỡng **0.20** chỉ là mức thấp để lab chạy ổn định khi Java Main và private constructors chưa được test, **không phải ngưỡng chất lượng khuyến nghị cho production**. Trong dự án thật phải đặt giới hạn hợp lý theo module/metric và theo dõi xu hướng.

**Về finalizer:** **finalizedBy** giúp report được lên lịch sau test, kể cả khi test task thất bại trong nhiều tình huống, nhưng report không thể tạo dữ liệu chưa có nếu compilation/configuration thất bại trước khi Test chạy. CI vẫn phải lưu các reports tồn tại bằng điều kiện always khi thích hợp.

### 6.8. Checkstyle XML ở root

Tạo **config/checkstyle/checkstyle.xml**:

~~~xml
<?xml version="1.0"?>
<!DOCTYPE module PUBLIC
    "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
    "https://checkstyle.org/dtds/configuration_1_3.dtd">
<module name="Checker">
    <property name="charset" value="UTF-8"/>

    <module name="TreeWalker">
        <module name="AvoidStarImport"/>
    </module>
</module>
~~~

Ruleset này có tính **minh họa và thực thi được**: nó cấm import dạng wildcard. Checkstyle có thể dùng DTD chuẩn được đóng gói/resolve theo tool behavior, không cần làm exception để tắt bảo vệ chỉ để đọc một file HTTP. File XML này chưa đại diện đầy đủ code style policy của tổ chức.

Các Java files của lab dùng imports tường minh; không có **import org.example.*;** nên expected Checkstyle result là không có violation của **AvoidStarImport**. Muốn kiểm chứng quality gate, có thể cố tình thêm wildcard import trong branch thử nghiệm rồi quan sát lỗi, sau đó hoàn tác.

### 6.9. Plugin 4: team.java-publish.gradle

Tạo **build-logic/src/main/groovy/team.java-publish.gradle**:

~~~groovy
plugins {
    id 'team.java-quality'
    id 'java-library'
    id 'maven-publish'
}

java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            pom {
                name = project.name
                description = 'Java library from convention-lab'
            }
        }
    }

    repositories {
        maven {
            name = 'localStaging'
            url = uri(
                layout.buildDirectory.dir('staging-repo')
                    .get().asFile)
        }
    }
}
~~~

Đây là **publication convention dành cho library**, không áp dụng ở **:app**.

- **java-library** cung cấp API/runtime outgoing variants và **components.java**.
- **withSourcesJar** tạo sources archive.
- **withJavadocJar** tạo Javadoc archive.
- **maven-publish** cung cấp **publishing** extension và MavenPublication.
- **mavenJava** là tên publication được đặt trong plugin; library nào apply plugin sẽ có publication tương ứng.
- **from components.java** lấy Java component/variants thay vì tự gom thư mục **build/classes** bằng Copy task.
- **localStaging** trỏ tới **build/staging-repo** của chính project consumer, **không publish lên Maven Central**.
- **pom.name** được lấy từ tên module, còn description là giá trị lab; trong dự án thật, có thể cung cấp extension/configuration để từng module đặt license, developers, SCM URL chính xác.

**Publication không tự trở thành release chính thức.** Cần credentials, legal metadata, artifact signing, repository policy và release governance nếu đẩy lên Maven Central hoặc kho công ty.

### 6.10. core/build.gradle

Tạo **core/build.gradle**:

~~~groovy
plugins {
    id 'team.java-publish'
}

group = 'org.example'
version = '1.0.0'
~~~

File này rất ngắn nhưng module **:core** nhận đầy đủ Java 17, test, quality, Maven publishing conventions qua plugin graph. **group/version** là dữ liệu nhận dạng của module và không nên hardcode cho tất cả modules trong convention nếu các thư viện có release versions khác nhau.

Java main artifact của :core sẽ có Maven coordinate:

~~~text
org.example:core:1.0.0
~~~

vì root module directory/project name là **core**. Nếu custom artifactId hoặc groupId ở publication, phải cập nhật ví dụ theo publication thực.

### 6.11. app/build.gradle

Tạo **app/build.gradle**:

~~~groovy
plugins {
    id 'application'
    id 'team.java-quality'
}

dependencies {
    implementation project(':core')
}

application {
    mainClass = 'org.example.app.Main'
}
~~~

Lưu ý:

- **application** cung cấp **run**, **installDist**, **distZip**, **distTar** và Java app convention.
- **team.java-quality** đưa Java 17, JUnit 5, Checkstyle, JaCoCo.
- **implementation project(':core')** là dependency cùng multi-project build.
- **app không apply team.java-publish**, nên không tự có MavenPublication của bài lab.
- app có thể có plugin **java** thông qua application và convention; Gradle quản lý việc apply plugin idempotently.
- Không cần khai báo lại JUnit version, Checkstyle, JaCoCo ở :app.

### 6.12. core/src/main/java/org/example/core/Messages.java

~~~java
package org.example.core;

/**
 * Các câu chào dùng chung trong bài thực hành Gradle.
 */
public final class Messages {
    private Messages() {
    }

    public static String hello(String rawName) {
        if (rawName == null || rawName.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }
        return "Xin chào, " + rawName.strip() + "!";
    }
}
~~~

Hàm sử dụng **String.isBlank()** và **String.strip()**, phù hợp Java 17. Không cần Apache Commons hoặc external runtime dependency. Javadoc ở đây giúp **javadocJar** sinh HTML docs phù hợp.

### 6.13. core/src/test/java/org/example/core/MessagesTest.java

~~~java
package org.example.core;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class MessagesTest {
    @Test
    void trimsName() {
        assertEquals(
                "Xin chào, Gradle!",
                Messages.hello("  Gradle  "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(
                IllegalArgumentException.class,
                () -> Messages.hello("   "));
    }
}
~~~

Có **hai JUnit Jupiter test methods** dự kiến pass. Không có import wildcard; XML Checkstyle rule cho project này dự kiến pass.

### 6.14. app/src/main/java/org/example/app/Main.java

~~~java
package org.example.app;

import org.example.core.Messages;

/**
 * Java CLI minh họa việc dùng thư viện core.
 */
public final class Main {
    private Main() {
    }

    public static String render(String name) {
        return "APP=" + Messages.hello(name);
    }

    public static void main(String[] args) {
        System.out.println(render("  Gradle  "));
    }
}
~~~

**Stdout chính xác từ Java Main:**

~~~text
APP=Xin chào, Gradle!
~~~

### 6.15. app/src/test/java/org/example/app/MainTest.java

~~~java
package org.example.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class MainTest {
    @Test
    void rendersMessage() {
        assertEquals(
                "APP=Xin chào, Gradle!",
                Main.render("Gradle"));
    }

    @Test
    void rejectsInvalidInput() {
        assertThrows(
                IllegalArgumentException.class,
                () -> Main.render(" "));
    }
}
~~~

Có **hai test methods** dự kiến pass. Tổng hai subprojects có **bốn JUnit test methods** trong lần chạy bình thường.

### 6.16. Lab tại sao được coi là runnable?

- Tất cả file paths khớp Java packages.
- Root settings include **core** và **app** là hai subprojects.
- **build-logic** có settings, build script và đúng **src/main/groovy** precompiled script sources.
- Plugin IDs được tạo từ file names và được apply bằng **plugins {}**.
- Các core plugins của Gradle được cấu hình qua precompiled scripts.
- Main build có repository cho JUnit/Checkstyle/JaCoCo dependencies; build-logic có repository riêng cho plugin build logic.
- Java 17 source code chỉ dùng JDK standard library.
- JUnit 5 API/engine + Launcher được khai báo đúng scope.
- Checkstyle config thật tồn tại dưới root **config/checkstyle**.
- **:core** có Maven publication; **:app** không bị buộc phát hành.
- Tất cả code fences của từng file trong lab là code nội dung để tạo tệp; không có lớp giả hoặc dependencies Maven “example” không tồn tại.

## 7. Chạy lab bằng Gradle Wrapper

### 7.1. Linux/macOS

Từ root **convention-lab/**:

~~~bash
./gradlew --version
./gradlew projects
./gradlew tasks --all

./gradlew :core:compileJava
./gradlew :app:compileJava
./gradlew :core:test :app:test
./gradlew :core:check :app:check

./gradlew :core:jacocoTestReport
./gradlew :app:jacocoTestReport
./gradlew :core:checkstyleMain :app:checkstyleMain

./gradlew :app:run
~~~

Stdout từ **:app:run**:

~~~text
APP=Xin chào, Gradle!
~~~

Gradle có thể in task status, deprecation warnings và daemon messages; khối trên chỉ là **stdout chính xác của Java Main**, không phải toàn bộ console log.

### 7.2. Windows PowerShell

~~~powershell
.\gradlew.bat --version
.\gradlew.bat projects
.\gradlew.bat tasks --all
.\gradlew.bat :core:test :app:test
.\gradlew.bat :core:check :app:check
.\gradlew.bat :app:run
~~~

**Unicode stdout:** Windows console có thể hiển thị tiếng Việt khác nhau tùy code page/terminal/JDK encoding. Java string literal và test assertion vẫn là Unicode text đúng nếu file được lưu UTF-8, compiler encoding=UTF-8. Khi so sánh stdout trực tiếp với script, dùng UTF-8 console hoặc decode phù hợp.

### 7.3. Maven publication local staging

Chỉ với :core:

~~~bash
./gradlew :core:publishMavenJavaPublicationToLocalStagingRepository
~~~

Tệp có thể xuất hiện dưới:

~~~text
core/build/staging-repo/
└── org/example/core/1.0.0/
    ├── core-1.0.0.jar
    ├── core-1.0.0-sources.jar
    ├── core-1.0.0-javadoc.jar
    ├── core-1.0.0.pom
    └── core-1.0.0.module
~~~

Đây là **layout dự kiến**. Gradle/repository có thể tạo thêm checksum/metadata files. **Publication core chưa được ký OpenPGP**, vì lab chưa áp dụng Signing plugin; đó là một bước mở rộng ở mục 17.

Không có **app/build/staging-repo** từ team.java-publish vì :app không áp dụng publishing convention. Nếu :app có tasks publication do một plugin khác hoặc được cấu hình ngoài lab, đó là phạm vi khác cần điều tra.

### 7.4. Phân biệt các lệnh quan trọng

| Lệnh | Ý nghĩa |
| --- | --- |
| **:core:compileJava** | Biên dịch Java 17 classes của library |
| **:app:compileJava** | Biên dịch app, kéo output :core theo project dependency |
| **:core:test** | Chạy hai test methods của core |
| **:app:test** | Chạy hai test methods của app |
| **:core:check** | Chạy Test, Checkstyle và coverage verification theo conventions |
| **:app:check** | Quality lifecycle tương tự, không publish |
| **:app:run** | Chạy Java app với runtimeClasspath |
| **:core:jar** | Tạo thin JAR của core |
| **:core:sourcesJar** | Tạo source archive |
| **:core:javadocJar** | Tạo documentation archive |
| **:core:publish...LocalStagingRepository** | Publish core Maven publication tới local staging |
| **:app:installDist** | Tạo distribution của Java app |
| **:app:distZip** | Tạo ZIP distribution của app |
| **:core:dependencies** | Xem dependency graph của core |
| **:app:dependencies** | Xem dependency graph của app |

Không coi **check** là đồng nghĩa **publish**. Quality checks kiểm tra code; publish là hành động phát hành artifact vào repository. Trong CI, nên chỉ publish nếu quality gate thành công.

## 8. Dùng javac/java xác minh source Java 17 độc lập

Lab code production không cần JUnit hoặc Gradle để biên dịch. Trên Linux/macOS, từ root:

~~~bash
mkdir -p out

javac --release 17 -encoding UTF-8 -d out \
  core/src/main/java/org/example/core/Messages.java \
  app/src/main/java/org/example/app/Main.java

java -cp out org.example.app.Main
~~~

**Stdout chính xác:**

~~~text
APP=Xin chào, Gradle!
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null

javac --release 17 -encoding UTF-8 -d out core\src\main\java\org\example\core\Messages.java app\src\main\java\org\example\app\Main.java

java -cp out org.example.app.Main
~~~

Lệnh **javac** này biên dịch đồng thời library và app Java classes vào một thư mục out. Nó kiểm tra source code và Java17 API compatibility.

**Nó không kiểm chứng các convention plugins**, JUnit 5 test execution, Checkstyle, JaCoCo, MavenPublication hoặc Gradle plugin resolution. Để xác minh những phần ấy phải chạy Gradle Wrapper thực và kiểm tra reports/artifacts.

## 9. Kiểm tra output của kiểm thử và chất lượng

### 9.1. JUnit HTML/XML

Sau khi chạy:

~~~bash
./gradlew :core:test :app:test
~~~

theo conventions, thường có:

~~~text
core/build/reports/tests/test/index.html
core/build/test-results/test/TEST-org.example.core.MessagesTest.xml

app/build/reports/tests/test/index.html
app/build/test-results/test/TEST-org.example.app.MainTest.xml
~~~

**Các đường dẫn dùng conventions của Java plugin**; nếu outputLocation bị sửa trong project, cần đọc đường dẫn thực tế. XML chứa số test/failure/skip được sinh ra thật; không tự tuyên bố đã đo từ một run chỉ dựa trên bốn @Test methods viết trong lab.

### 9.2. Checkstyle

Sau **:core:checkstyleMain**, Checkstyle plugin có reports tại **build/reports/checkstyle/** của module tương ứng; tên file thường là **main.html** và **main.xml** theo version/config.

Checkstyle kiểm tra source bằng rule **AvoidStarImport**. Nếu bạn thay:

~~~java
import static org.junit.jupiter.api.Assertions.*;
~~~

vào một class test trong branch thử nghiệm, **checkstyleTest** có thể báo violation. Đây là snippet **cố ý vi phạm**, không nằm trong lab runnable. Hoàn tác sau khi quan sát gate.

### 9.3. JaCoCo

Sau **:core:jacocoTestReport** hoặc **:app:jacocoTestReport**, theo conventions:

~~~text
core/build/reports/jacoco/test/html/index.html
core/build/reports/jacoco/test/jacocoTestReport.xml

app/build/reports/jacoco/test/html/index.html
app/build/reports/jacoco/test/jacocoTestReport.xml
~~~

Tên XML có thể thay theo Gradle/reporting output conventions; kiểm tra **jacocoTestReport** task outputs trên Wrapper thật. **jacocoTestCoverageVerification** kiểm tra ngưỡng, không tự là HTML report.

**Coverage không phải test pass rate.** Một test pass có thể không bao phủ main method, error branch hoặc edge cases. Bốn JUnit tests trong lab không đồng nghĩa coverage 100%.

### 9.4. Sao chụp artifact và metrics

Một CI job nên lưu:

- JUnit XML per Test task.
- HTML per Test task.
- Checkstyle XML/HTML.
- JaCoCo XML/HTML.
- Task failures và Gradle version.
- Maven staging artifacts khi đó là deliverable của job.

Không upload **toàn bộ Gradle user home hoặc workspace** để “chắc chắn có evidence”, vì có thể chứa tokens, cache lớn hoặc dữ liệu nhạy cảm.

## 10. Vì sao các convention plugins nên ghép được?

### 10.1. Một plugin trách nhiệm rõ

Nếu plugin **team.java-quality** chứa cả **publishing {...}**, mọi application áp dụng quality policy sẽ nhận thêm publish tasks và có thể bị yêu cầu nhập credentials phát hành.

Ngược lại, nếu chỉ tạo một plugin **team.java-publish** mà trong đó lại không bao gồm Java/test/quality conventions, library cần áp dụng nhiều plugins thủ công theo một thứ tự dễ sai.

Một thiết kế cân bằng:

- **Base:** Java toolchain/compiler.
- **Tests:** JUnit/test reports.
- **Quality:** Checkstyle/JaCoCo.
- **Publish:** Maven publication cho library.
- **Application:** application plugin + quality, có thể tách thêm **team.java-app** khi nhiều app giống nhau.

### 10.2. Chính sách opt-in thay vì cấu hình từ root

Nhìn vào:

~~~groovy
plugins {
    id 'team.java-publish'
}
~~~

người review biết :core sẽ có publication. Nhìn vào:

~~~groovy
plugins {
    id 'application'
    id 'team.java-quality'
}
~~~

biết :app sẽ có executable application và quality checks, nhưng không có Maven publication trong bài lab.

So với root:

~~~groovy
subprojects {
    apply plugin: 'maven-publish'
}
~~~

cấu hình tự khai báo ở module rõ ràng hơn và giảm sự phụ thuộc chéo. Đoạn **subprojects** trên là một **anti-pattern minh họa**, không phải code của lab.

### 10.3. Không lạm dụng inheritance

Khi convention plugin A phụ thuộc B, cần quyết định có nên thực sự **apply B** hay chỉ cấu hình B nếu module đã apply sẵn. Ví dụ plugin test có thể apply **java** vì mỗi Test task cần Java plugin model. Nhưng plugin publishing không nên apply lên module chỉ muốn Java utilities.

Với chính sách tùy chọn, binary plugin có thể dùng:

~~~groovy
pluginManager.withPlugin('java') {
    // Cấu hình riêng khi Java plugin đã được áp dụng.
}
~~~

**Đây là snippet Groovy trong phạm vi project plugin**, cần viết thêm logic thực khi dùng. **pluginManager.withPlugin** hữu ích để phản ứng khi plugin khác có mặt mà không cần ép tất cả modules apply nó.

## 11. Task configuration avoidance và Provider API

Các convention plugins chạy trong **configuration phase**. Nếu mọi plugin gọi **tasks.getByName**, **tasks.all** hoặc đọc outputs chưa có, Gradle có thể hiện thực tasks sớm, làm build lớn chậm hơn và ảnh hưởng configuration cache.

### 11.1. Ưu tiên named và configureEach

Nên:

~~~groovy
tasks.named('test') {
    useJUnitPlatform()
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

Kém phù hợp trong build lớn:

~~~groovy
tasks.getByName('test').useJUnitPlatform()

tasks.withType(JavaCompile).all {
    options.encoding = 'UTF-8'
}
~~~

Hai đoạn sau có thể trigger eager realization/configuration. Với modules lớn, chọn lazy APIs để Gradle chỉ cấu hình tasks khi cần.

### 11.2. Tasks được tạo sau

**tasks.withType(Test).configureEach** có lợi khi plugin JVM Test Suite hoặc một convention khác đăng ký **integrationTest** sau này: cấu hình JUnit/reports vẫn được áp dụng cho task loại Test tương ứng.

Tuy nhiên, **team.java-quality** trong lab nối **jacocoTestReport** và coverage verification theo task **test** mặc định. Nó **không tự gộp coverage từ mọi integrationTest task**. Muốn coverage tổng hợp, phải tạo JacocoReport/verification mới và cung cấp executionData từ các Test tasks phù hợp.

### 11.3. Không resolve dependencies khi cấu hình plugin

Sai:

~~~groovy
def jars = configurations.runtimeClasspath.files
~~~

nếu thực hiện trực tiếp trong configuration phase. Điều đó có thể buộc Gradle resolve dependencies sớm, làm chậm builds và khó hỗ trợ configuration cache.

Đúng hơn, nếu một task cần files, nối **ConfigurableFileCollection** hoặc Provider vào task inputs và để Gradle resolve khi task thực thi. Không copy cache files thủ công hay bắt tất cả modules resolve runtimeClasspath chỉ để đăng ký convention plugin.

### 11.4. Không giữ Project reference trong task action tùy tiện

Với task custom, tránh **doLast { println project.someMutableValue }** hoặc đọc Project model trong execution phase nếu muốn configuration cache/isolated projects hoạt động. Nên tạo task type có **@Input**/**@Output...** annotations, Property/Provider inputs và sử dụng những values đã được wiring từ configuration.

Convention plugin có thể đăng ký **tasks.register(...)** một cách lazy; plugin không cần tự thực thi file I/O trong configuration chỉ để sinh một report.

## 12. Version catalogs, plugin dependencies và build isolation

### 12.1. Main build catalog không tự xuất hiện trong build-logic

Nếu root main build có:

~~~text
gradle/libs.versions.toml
~~~

và code module dùng **libs.junit.jupiter**, **build-logic** là một included build riêng, nên nó **không tự có cùng catalog**.

Có thể định nghĩa catalog riêng trong **build-logic/settings.gradle**, hoặc import chung TOML qua versionCatalogs API với đường dẫn đúng; nhưng chính thao tác ấy phải được khai báo trong settings của build-logic, không tự động xảy ra.

### 12.2. Cách đơn giản cho lab

Lab pin JUnit Jupiter/Platform versions ngay trong **team.java-tests.gradle**:

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}
~~~

Điều này làm ví dụ runnable mà không cần catalog riêng. Ở production, nên quản lý versions qua catalog/platform/convention extension hoặc tổ chức release process phù hợp, tránh phiên bản khác nhau giữa root/main/build-logic.

### 12.3. External plugins phải có mặt trên build-logic classpath

Giả sử team muốn thêm một plugin community như SpotBugs hoặc Spotless vào precompiled script plugin. Không thể chỉ chép:

~~~groovy
plugins {
    id 'some.community.plugin'
}
~~~

mà không đảm bảo plugin implementation resolve được ở **build-logic**. Trong precompiled script plugin, external plugin thường phải là **implementation dependency của plugin build**; version nằm trong tọa độ artifact tương ứng, còn plugin ID ở script ứng dụng plugin.

Đây là **snippet minh họa**, không phải một plugin ID có thật cho lab. Khi thêm community plugin thật, đọc documentation của plugin đó để tìm artifact/plugin ID/version compatibility với Gradle/JDK. Tránh hardcode phiên bản giả hoặc đặt plugin version trùng nhau ở nhiều nơi.

### 12.4. Plugin repository khác library repository

- **pluginManagement.repositories** dùng để resolve plugin markers và plugin dependencies tại thời điểm settings/plugins.
- **dependencyResolutionManagement.repositories** dùng để resolve application/test/quality libraries của main build.
- **build-logic.repositories** dùng cho dependency cần để compile và chạy chính plugin code.
- **publishing.repositories** là nơi upload publication outputs, không phải nơi lấy JUnit libraries.

Không sửa một lỗi **Plugin not found** bằng cách chỉ thêm Maven Central vào **app.repositories**, vì plugin resolution xảy ra ở phạm vi khác.

## 13. Checkstyle policy nên được bảo trì thế nào?

Một convention plugin có thể yêu cầu Checkstyle ở mọi Java module, nhưng **ruleset** vẫn phải phản ánh sản phẩm thực:

- Quy tắc về imports, naming, whitespace hoặc maintainability.
- Ngoại lệ cho generated sources.
- Chính sách cho test source nếu khác production source.
- Java language level/Checkstyle tool version tương thích.
- Suppression files có review, không tắt toàn bộ rules.
- Cách báo cáo trên CI và bước sửa violation.
- Quy tắc phát hiện lỗi/warnings có nên fail build không.

### 13.1. Cấu hình hiện tại của lab

Lab chỉ bật **AvoidStarImport** để người học hiểu luồng:

~~~text
Java source
   |
   v
checkstyleMain / checkstyleTest
   |
   v
config/checkstyle/checkstyle.xml
   |
   v
XML + HTML report / build failure nếu vi phạm
~~~

Với file policy ở root, mọi module sử dụng **team.java-quality** đều đọc cùng config. Đây là lựa chọn hợp lệ cho một multi-project build. Nếu muốn đem plugin tới nhiều **independent builds**, có thể:

1. Đóng gói ruleset XML trong build-logic resources/JAR.
2. Cho plugin một extension **checkstyleConfigFile** để consumer tự chọn.
3. Dùng một shared policy artifact được version hóa.
4. Cung cấp convention plugin riêng cho test/generated sources.
5. Không hardcode đường dẫn filesystem của một developer.

### 13.2. Generated code

Nếu Gradle tạo Java sources từ OpenAPI/Protobuf/annotation processing, áp quy tắc style nghiêm ngặt lên generated files có thể gây lỗi mà developer không thể sửa trực tiếp. Cần đưa generated sources vào đúng source set/task outputs và có **Checkstyle exclusions/suppressions** rõ ràng.

Không tắt Checkstyle toàn project chỉ vì một thư mục generated Java; hãy cấu hình scope/filters đúng.

## 14. JaCoCo quality gate phải được hiểu đúng

### 14.1. Report và verification là hai tasks khác nhau

- **jacocoTestReport** tạo HTML/XML/CSV tùy reports đã bật.
- **jacocoTestCoverageVerification** so sánh execution data với rules và có thể làm build fail.
- **test** tạo execution data bằng JaCoCo agent khi plugin cấu hình cho Test task.
- **check** mặc định không tự dependsOn coverage verification; lab đã thêm phụ thuộc đó.

Dòng:

~~~groovy
tasks.named('check') {
    dependsOn(tasks.named('jacocoTestCoverageVerification'))
}
~~~

là điều khiến **./gradlew :core:check** bảo đảm chạy rule coverage của convention plugin.

### 14.2. Có test pass không bảo đảm coverage đủ

Ví dụ chỉ có một test cho hàm greeting, main method không được gọi. Các tests vẫn có thể pass nhưng một số instructions/lines bị bỏ qua.

Ngược lại, có thể viết test kém chất lượng chạy qua rất nhiều lines để tăng coverage nhưng không có assertions đúng. Coverage chỉ là **một chỉ số hỗ trợ**, không thay chất lượng kịch bản kiểm thử, mutation testing hay risk-based testing.

### 14.3. Threshold theo module

Mức **minimum=0.20** trong lab là để ví dụ ổn định; thực tế có thể đặt:

- Tỷ lệ line coverage cho library business logic cao hơn app bootstrap.
- Branch coverage cho validation code.
- Exclusions cho generated code và entrypoints hợp lý.
- Threshold khác theo migration phase.
- Reporting của test suite integration/bộ test full workflow khác unit test.
- Quality gates tăng dần theo baseline lịch sử.

Không đặt một tỷ lệ tùy ý rồi tuyên bố nó chứng minh chất lượng mọi module.

### 14.4. Khi có nhiều Test tasks

Nếu project có **integrationTest** ngoài **test**, riêng **jacocoTestReport** thường gắn với Test task mặc định, không tự bao gồm tất cả suites. Một plugin nâng cao có thể tạo aggregated **JacocoReport** với **executionData** của các Test tasks và Java source set tương ứng, nhưng phải chú ý:

- **dependsOn** các Test tasks để tạo dữ liệu trước khi report.
- Dùng Provider/FileCollection phù hợp thay vì resolve quá sớm.
- Tránh đếm execution data cũ/stale sau thay source.
- Không đồng nhất aggregate reports giữa multi-project với report của nhiều suites trong một project.

## 15. Maven publishing convention cần những quyết định gì?

### 15.1. Chỉ library có publication

Trong lab, **:core** có:

~~~groovy
plugins {
    id 'team.java-publish'
}
~~~

nên tạo MavenPublication. **:app** không áp dụng plugin này, nên việc chạy app/test không tạo JAR publication theo policy.

Cách thiết kế này hữu ích khi nhiều modules có chức năng khác nhau: api-client, data-model libraries, test-fixtures, CLI, demo app.

### 15.2. Maven component và dependency metadata

**from components.java** bảo đảm publication được xây từ Java component và metadata/variants đúng hơn so với tự copy JAR bằng task rồi publish như file vô danh.

Khi **java-library** được apply, consumer Java Gradle có thể dùng **api** và **implementation** scopes để xuất API/runtime dependency graph hợp lý. Publication không nhất thiết chỉ là “một file JAR”, vì **POM** và **Gradle Module Metadata** ảnh hưởng cách người khác resolve dependencies.

### 15.3. Sources/Javadoc artifacts

**withSourcesJar()/withJavadocJar()** tạo thêm artifacts hữu ích cho IDE/documentation. Nếu Java code có Javadoc errors do doclint, task **javadocJar** có thể fail dù JAR production compile pass. Đó là một quality issue cần sửa, không phải lý do xóa docs convention khi release policy yêu cầu tài liệu.

### 15.4. Local staging khác Maven Local

Trong lab:

~~~groovy
repositories {
    maven {
        name = 'localStaging'
        url = uri(
            layout.buildDirectory.dir('staging-repo')
                .get().asFile)
    }
}
~~~

đưa artifact vào **core/build/staging-repo** theo Maven directory structure khi chạy publish task tương ứng.

**publishToMavenLocal** đưa vào **~/.m2/repository** của người dùng và không dùng repository localStaging được khai báo; hai đích khác nhau.

**publish** có thể tạo nhiều repository upload tasks nếu bạn khai báo nhiều destinations. Không nhầm **build** với **publish**.

### 15.5. Release signing và credentials để ở đâu?

Lab không cấp secrets và không publish public. Khi nâng thành release pipeline:

- Repository credentials lấy từ CI secret manager/Gradle credentials Provider, không hardcode.
- Signing key/passphrase lưu ngoài source; có thể dùng Gradle **signing** plugin.
- Signing convention chỉ apply cho publication/release module cần ký.
- Release job chạy sau test/check và kiểm tra publication/signature outputs.
- CI tag/branch protection và approvals có vai trò quan trọng.
- Không trao repository write token hoặc signing private key cho PR build không tin cậy.

Một publish convention **không nên tự phát hành** artifact chỉ vì được apply. Tasks phải được gọi có chủ đích và quyền release được quản lý bên ngoài Gradle code.

## 16. Ví dụ mở rộng: signing convention tùy chọn

Đây là ví dụ **bổ sung, không thuộc bốn plugin runnable của lab**. Trong dự án thật có thể tạo plugin riêng **team.java-signing**:

~~~groovy
plugins {
    id 'team.java-publish'
    id 'signing'
}

def isRelease =
        !version.toString().endsWith('-SNAPSHOT')

signing {
    required = isRelease

    def key = providers.gradleProperty('signingKey').orNull
    def passphrase =
            providers.gradleProperty('signingPassword').orNull

    if (key != null && !key.isBlank()) {
        useInMemoryPgpKeys(key, passphrase)
    }

    sign publishing.publications.mavenJava
}
~~~

**Chỉ dùng sau khi** dự án đã xác định release version policy và cấp OpenPGP private key bằng secret manager. Thư viện có thể đọc biến **ORG_GRADLE_PROJECT_signingKey** và **ORG_GRADLE_PROJECT_signingPassword**, nhưng không in key vào Gradle logs.

**Lưu ý quan trọng:** Plugin ví dụ xác định **isRelease** từ **project.version** khi plugin được apply. Trong lab, module có thể đặt **version = '1.0.0'** sau **plugins {}**; nếu đưa nguyên logic trên vào plugin mà không thiết kế thời điểm cấu hình, **isRelease** có thể nhìn thấy version mặc định **unspecified**, dẫn đến chính sách sai. Trong production, đưa version qua settings/gradle.properties được xác định trước plugin hoặc dùng một Provider/extension và cấu hình signing theo lifecycle đúng. Không sao chép snippet này vào lab rồi tuyên bố release gate đã được đảm bảo.

Giải pháp an toàn hơn khi phát hành là CI **bắt buộc** có signature artifacts và dùng trusted release parameters, thay vì dựa duy nhất vào một if được evaluate quá sớm.

## 17. CI cho conventions: chạy checks, rồi mới publish

Một pipeline có thể có các bước:

~~~text
Checkout + Gradle Wrapper + JDK 17
             |
             v
      Build build-logic
             |
             v
     Configure :core + :app
             |
             v
         compileJava
             |
             v
         JUnit Tests
             |
             v
       Checkstyle checks
             |
             v
       JaCoCo verification
             |
             v
           check PASS
             |
             v
    Stage :core publication
             |
             v
     Verify artifact / release
~~~

Gradle tự compile included build plugin logic trước khi apply plugin IDs trong main projects theo plugin resolution. Không cần viết shell command build-logic mỗi lần nếu main build đã include đúng.

### 17.1. Lệnh CI tối thiểu

~~~bash
./gradlew --no-daemon \
  :core:check \
  :app:check \
  :app:run

./gradlew --no-daemon \
  :core:publishMavenJavaPublicationToLocalStagingRepository
~~~

Trong pipeline thực, **lệnh publish chỉ chạy nếu lệnh check trước thành công**; nếu dùng Bash shell script có nhiều lệnh, cần **set -e** hoặc step separation sao cho fail không bị bỏ qua. Không dùng **|| true** với các quality gate.

### 17.2. GitHub Actions minh họa

Tạo file **.github/workflows/verify.yml** nếu muốn chạy CI:

~~~yaml
name: Convention build verification

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Gradle environment
        uses: gradle/actions/setup-gradle@v6

      - name: Verify Java, tests and quality
        run: ./gradlew --no-daemon :core:check :app:check

      - name: Check application output
        shell: bash
        run: |
          actual="$(./gradlew --no-daemon -q :app:run)"
          test "$actual" = 'APP=Xin chào, Gradle!'

      - name: Stage Maven library
        run: ./gradlew --no-daemon :core:publishMavenJavaPublicationToLocalStagingRepository

      - name: Upload reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: convention-verification
          path: |
            core/build/reports/**
            app/build/reports/**
            core/build/test-results/test/TEST-*.xml
            app/build/test-results/test/TEST-*.xml
          if-no-files-found: warn
          retention-days: 14

      - name: Upload staging artifacts
        if: success()
        uses: actions/upload-artifact@v4
        with:
          name: core-local-staging
          path: core/build/staging-repo/**
          if-no-files-found: error
          retention-days: 14
~~~

**Phân biệt:** Đây là CI thử nghiệm với **localStaging**, không tự phát hành lên Maven Central hay signing release. Version actions/Gradle Wrapper phải phù hợp org security policy; nhiều tổ chức pin action commit SHA đã kiểm duyệt.

- **Upload reports** dùng **if: always()** để vẫn giữ bằng chứng khi code quality fail.
- **Upload staging artifacts** dùng **if: success()** để chỉ coi outputs là deliverable khi previous steps pass.
- Khi Gradle task fail, CI job vẫn đỏ. Không đặt **continue-on-error: true** trên quality verification.
- Nếu build fail trước khi có reports, upload step có thể không tìm thấy file; điều đó cần được ghi rõ, không tạo báo cáo pass giả.
- Không upload **~/.gradle**, secret files, environment dumps hoặc toàn workspace.

### 17.3. Runtime output trong CI

Lệnh:

~~~bash
./gradlew -q :app:run
~~~

được kỳ vọng in:

~~~text
APP=Xin chào, Gradle!
~~~

Tuy nhiên khi setup mới Gradle có thể ghi log/warnings ở stderr hoặc console khác tùy version; đoạn Bash assertion trong workflow so sánh stdout. Nếu Java console encoding hoặc CLI banner làm stdout khác, hãy điều tra môi trường thay vì bỏ smoke check vô điều kiện.

## 18. Viết plugin tests cho build-logic

Conventions cũng là code, có thể regress. Khi thay:

- JDK toolchain version.
- JUnit library version.
- Report output paths.
- Checkstyle XML rules.
- Coverage threshold.
- Maven publication metadata.
- Plugin application dependencies.

cần kiểm thử chính convention plugin, không chỉ dựa trên một ứng dụng thật đang sử dụng nó.

### 18.1. Các mức kiểm thử

1. **Smoke test:** một test project nhỏ apply plugin ID và chạy **help/tasks**.
2. **Functional TestKit:** tạo Gradle test fixture/temp project bằng **GradleRunner**, chạy tasks và assert outcome.
3. **Integration test:** áp dụng plugin trên dự án Java có test source, kiểm tra JUnit/JaCoCo/Checkstyle/Maven outputs.
4. **Compatibility matrix:** kiểm tra những Gradle/Java versions được tổ chức hỗ trợ.
5. **Consumer verification:** plugin được publish từ repository, một build khác apply theo chính plugin marker/coordinate thật.

### 18.2. TestKit không chỉ là unit test Java

Gradle TestKit cung cấp **GradleRunner** để chạy một build thử nghiệm trong một process Gradle, giúp kiểm tra một plugin có hoạt động trong Gradle lifecycle không. TestKit đặc biệt hữu ích khi plugin đăng ký tasks, extensions hoặc publications.

Ví dụ code Java minh họa API:

~~~java
import java.io.File;
import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.GradleRunner;

public final class PluginSmokeCheck {
    private PluginSmokeCheck() {
    }

    public static BuildResult run(File projectDir) {
        return GradleRunner.create()
                .withProjectDir(projectDir)
                .withArguments("help", "--stacktrace")
                .withPluginClasspath()
                .build();
    }
}
~~~

**Đây là snippet minh họa**, không phải chương trình độc lập: cần Gradle TestKit trên test classpath và một fixture Gradle project có settings/build.gradle thật. Nếu test plugin nằm trong build-logic, cần cấu hình test dependencies/fixtures và assertion framework phù hợp. Không đưa snippet này vào app/main Java source hoặc production Maven publication.

### 18.3. Điều nên assert

- Project apply **team.java-base** có Java toolchain 17.
- **team.java-tests** tạo Test task dùng JUnit Platform.
- **team.java-quality** tạo checkstyleMain và jacocoTestCoverageVerification.
- **check** thực sự dependsOn coverage verification.
- Một test failing làm Gradle build fail.
- :core có **mavenJava** publication và sources/Javadoc artifacts.
- :app không có Maven publication chỉ vì team.java-quality.
- Plugin không đọc file/secrets không có quyền.
- Configuration cache có thể được reuse nếu plugin hỗ trợ.

Có thể lưu golden test fixture trong **build-logic/src/test/** và chạy **./gradlew :build-logic:test** theo build-tree path nếu included build root project có Java test tasks; hoặc chạy **./gradlew test** từ chính **build-logic/**. Không tự giả precompiled script plugin build luôn có Test task sẵn được cấu hình JUnit nếu chưa khai báo test dependencies/framework.

## 19. Binary plugin khi convention logic lớn lên

Khi Groovy precompiled scripts trở nên quá phức tạp, có thể chuyển sang typed binary plugin viết bằng Java/Groovy/Kotlin.

Ví dụ Java Plugin<Project>:

~~~java
package org.example.buildlogic;

import org.gradle.api.Plugin;
import org.gradle.api.Project;
import org.gradle.api.plugins.JavaPlugin;

public final class JavaBaseConventionPlugin
        implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        project.getPluginManager()
                .apply(JavaPlugin.class);
    }
}
~~~

**Đây là một đoạn plugin class minh họa**, chưa có Gradle plugin metadata đăng ký ID. Một binary plugin runnable cần **java-gradle-plugin** và:

~~~groovy
gradlePlugin {
    plugins {
        javaBaseConventions {
            id = 'team.java-base'
            implementationClass =
                'org.example.buildlogic.JavaBaseConventionPlugin'
        }
    }
}
~~~

Cấu hình này cần đặt trong **build script của plugin-producing project** và class Java ở source set tương ứng; không đặt trực tiếp vào **app/build.gradle**.

### 19.1. Khi nào chuyển đổi?

- Cần custom Gradle extension có **Property<T>** và validation.
- Cần custom task class có typed inputs/outputs, Worker API, Build Services.
- Cần kiểm soát lifecycle/configuration cache chặt chẽ.
- Muốn publish plugin cho nhiều repositories/teams.
- Có nhiều provider properties, variations và testing surface.
- Code quality rules phải được chọn theo type-safe extension/module attributes.

Nếu plugin chỉ apply **java**, cấu hình JUnit/Checkstyle/JaCoCo và publication như lab, precompiled script plugin thường đủ rõ ràng.

### 19.2. Phân biệt versioned plugin và versioned dependencies

Binary plugin được publish có **plugin version** riêng. Nó có thể áp dụng external plugins/dependencies có versions khác. Khi upgrade plugin, đừng mặc định JUnit/Checkstyle/JaCoCo versions không đổi; những versions có thể nằm trong plugin logic hoặc policies.

Tài liệu release nên ghi rõ compatibility: Gradle version, JVM chạy Gradle, Java toolchain target, third-party plugins và CI environment.

## 20. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân phổ biến | Cách xử lý |
| --- | --- | --- |
| **Plugin [id: 'team.java-quality'] was not found** | Chưa include build-logic hoặc sai plugin file name/location | Kiểm tra settings.pluginManagement.includeBuild và src/main/groovy/team.java-quality.gradle |
| **build-logic không build được** | Thiếu groovy-gradle-plugin hoặc repositories của included build | Kiểm tra build-logic/build.gradle và dependencies |
| **Unknown plugin ID trong precompiled script** | Thiếu external plugin implementation dependency | Thêm dependency đúng ở build-logic và kiểm tra plugin ID |
| **No matching configuration/extension java** | Plugin Java chưa apply trước khi cấu hình | Cho team.java-base apply java; kiểm tra plugin graph |
| **No tests found** | JUnit engine/launcher sai, test source thiếu, useJUnitPlatform quên | Kiểm tra JUnit scopes và Test task |
| **Checkstyle config file does not exist** | Thiếu config/checkstyle/checkstyle.xml hoặc rootDir không phù hợp | Thêm file/rules đúng hoặc cấu hình extension |
| **Checkstyle violation** | Source vi phạm rule AvoidStarImport hoặc rules khác | Sửa source/suppress có review |
| **JaCoCo XML không có** | jacocoTestReport chưa chạy hoặc xml.required=false | Chạy test → report, kiểm tra outputs |
| **Coverage gate không chạy với check** | jacocoTestCoverageVerification chưa dependsOn check | Gắn check.dependsOn(verification) |
| **Coverage verification không có dữ liệu** | Test chưa chạy hoặc task order thiếu | Thêm dependsOn(test), kiểm tra execution data |
| **Check fail do threshold quá cao** | Ngưỡng không phù hợp với test suite/baseline | Cải thiện tests và điều chỉnh policy có căn cứ, không tắt gate |
| **core không có mavenJava** | Team publish plugin chưa apply | Kiểm tra core plugins và publishing DSL |
| **app có publish tasks ngoài ý muốn** | Root allprojects/subprojects hoặc plugin khác apply maven-publish | Xem plugin graph, loại implicit publication policy |
| **POM thiếu dependencies** | Tự publish file thay vì components.java | Dùng Java component và kiểm tra POM/metadata |
| **Không thấy sourcesJar** | Quên withSourcesJar hoặc task chưa chạy | Apply java convention và publish plugin |
| **Javadoc errors** | Java source/Javadoc không hợp lệ | Sửa Javadoc source, không tắt bừa release requirement |
| **Core staging path sai** | Đang tìm root/build thay vì core/build | Kiểm tra publication repository path trong consumer project |
| **Unresolved JUnit from Maven** | Root dependencyResolutionManagement thiếu repo/mirror | Kiểm tra settings/repository/TLS/credentials |
| **Không resolve plugin community** | Chỉ khai báo ở app repo, không ở build-logic plugin classpath | Cập nhật build-logic dependencies/repositories |
| **Build logic không thấy libs catalog** | Included build không kế thừa root catalog | Định nghĩa/import catalog trong build-logic settings |
| **Gradle project path :build-logic không tồn tại** | build-logic là included build chứ không phải subproject | Dùng included build task path hoặc chạy trong build-logic |
| **Conventions thay rồi app build vẫn dùng cũ** | Sử dụng cache/working copy khác hoặc apply sai plugin ID | Kiểm tra included build path, task outcomes và plugin jars |
| **Configuration cache không reuse** | Plugin đọc Project/IO/sources ở execution không đúng | Sử dụng Provider API, typed tasks và Gradle cache report |
| **Java 17 toolchain unavailable** | Runner không có JDK 17/toolchain provisioning | Cấu hình JDK + Gradle compatibility |
| **Gradle CLI đã update nhưng build fail** | Plugin/Checkstyle/JaCoCo API compatibility đổi | Pin/upgrade versions theo release notes, chạy TestKit/CI matrix |
| **CI mất report khi test fail** | Artifact upload chỉ chạy khi success | Dùng if: always() cho report upload |
| **Private credentials lộ trên CI** | In properties/env hoặc đưa key vào source/build artifacts | Revoke/rotate secrets, sửa logging và permission |

### 20.1. Trình tự debug

~~~text
Convention plugin không hoạt động?
             |
             v
1. root settings có includeBuild build-logic?
             |
             v
2. build-logic có settings/build.gradle riêng?
             |
             v
3. groovy-gradle-plugin đã được áp dụng?
             |
             v
4. File plugin ở đúng src/main/groovy và đúng tên ID?
             |
             v
5. Precompiled script plugin apply core/other plugins nào?
             |
             v
6. Module build.gradle có apply plugin ID dự định?
             |
             v
7. Task Java/Test/Checkstyle/JaCoCo/publish có trong tasks --all?
             |
             v
8. Checkstyle XML, JUnit dependencies, repositories có đúng?
             |
             v
9. Gradle check và publication tasks có outputs thật?
             |
             v
10. CI reports và published artifacts có khớp chính sách?
~~~

### 20.2. Lệnh chẩn đoán

~~~bash
./gradlew projects
./gradlew :core:tasks --all
./gradlew :app:tasks --all

./gradlew :core:dependencies \
  --configuration testRuntimeClasspath

./gradlew :app:dependencies \
  --configuration runtimeClasspath

./gradlew :core:check --info
./gradlew :app:check --info

./gradlew :core:publishMavenJavaPublicationToLocalStagingRepository \
  --dry-run
~~~

**--dry-run** chỉ xem graph, không kiểm chứng publication thực. Để biết POM/JAR thật có đúng, phải chạy publish task và đọc **core/build/staging-repo**.

## 21. So sánh trước và sau khi dùng convention plugins

### 21.1. Trước — mỗi project copy logic

~~~text
core/build.gradle:
    java-library + JDK + JUnit + Checkstyle + JaCoCo
    + maven-publish + duplicated versions

app/build.gradle:
    application + JDK + JUnit + Checkstyle + JaCoCo
    + duplicated versions

service/build.gradle:
    application + JDK + JUnit + Checkstyle + JaCoCo
    + duplicated versions
~~~

Sửa Java version, JUnit hoặc Checkstyle policy phải sửa nhiều file. Những changes rất dễ mất đồng bộ.

### 21.2. Sau — modules opt-in rõ ràng

~~~text
build-logic:
    team.java-base
    team.java-tests
    team.java-quality
    team.java-publish

core/build.gradle:
    plugins { id 'team.java-publish' }

app/build.gradle:
    plugins { id 'application'; id 'team.java-quality' }

service/build.gradle:
    plugins { id 'application'; id 'team.java-quality' }
~~~

Những tiêu chuẩn chung có một nơi quản lý. Nếu quy tắc cần ngoại lệ, module nên cấu hình override thông qua API/extension được phê duyệt thay vì copy/paste lại toàn convention plugin.

### 21.3. Không xây “god plugin”

Anti-pattern khác là **team.all-conventions** cùng lúc apply java, application, java-library, maven-publish, signing, jacoco, checkstyle, docker, native image cho mọi module. Điều đó tạo quá nhiều tasks, dependencies/credentials không cần thiết và coupling giữa release workflows.

Nên nhóm plugins theo **trách nhiệm**, và tách plugin application/library/publish khi workflow khác nhau.

## 22. Những yêu cầu nâng cao trong tổ chức lớn

### 22.1. Policy nhiều repository/builds

Nếu một tổ chức có nhiều independent Gradle builds, mỗi build có thể include một versioned **build-logic** plugin build hoặc tiêu thụ binary plugin đã publish. Không thể giả **root allprojects{}** từ build A sẽ tự cấu hình build B qua includeBuild.

Nếu tổ chức yêu cầu policy bắt buộc về repositories/TLS/secret managers, dùng settings/init plugins hoặc enterprise build policies đúng phạm vi; project convention plugin không tự có quyền thay đổi mọi global settings.

### 22.2. Multi-project vs included build boundary

Trong lab:

- :core/:app là **subprojects** trong một multi-project build.
- build-logic là **included build** chỉ cung cấp Gradle plugins.
- **implementation project(':core')** là dependency Java giữa subprojects.
- **plugins { id 'team.java-quality' }** là Gradle plugin resolution từ included build.
- Không dùng **implementation project(':build-logic')** cho Java app.
- Không đưa test/quality plugins vào production runtimeClasspath.
- Không viết **subprojects{}** trong main root để sửa included build internals.

### 22.3. Versioned policy artifacts

Khi convention plugins được tiêu thụ bởi nhiều teams/repositories:

1. Publish plugin với semantic version phù hợp.
2. Ghi Gradle/Java compatibility range.
3. Có migration guide khi task names/report paths đổi.
4. Pin plugin version trong pluginManagement/version catalogs theo policy.
5. Run TestKit và representative consumer builds trước release.
6. Phân tách stable APIs/extensions với internal implementation.
7. Có rollback strategy nếu một plugin release làm nhiều builds fail.
8. Không ép mọi team nâng JDK/JaCoCo phiên bản mới cùng lúc nếu hệ thống chưa sẵn sàng.

### 22.4. Configuration cache và isolated projects

Conventions nên tránh:

- Tự cấu hình sibling project bằng **project(':x')**.
- Đọc rootProject build extensions để suy đoán cấu hình mọi module.
- Mutable static/global state giữa plugins.
- Eager task realization trong configuration.
- Đọc filesystem không được khai báo là task input.
- Bắt Project model trong task action mà không có Provider.
- Dùng **afterEvaluate** làm giải pháp mặc định cho mọi plugin ordering issue.

Thay vào đó, dùng **pluginManager.withPlugin**, providers, extensions, configurations, task types và **tasks.register/named/configureEach**. Kiểm thử configuration cache và isolated project compatibility khi đó là requirement thật, không chỉ tin vào nhãn “convention plugin”.

## 23. Bài tập thực hành

### Bài 1 — Tạo build-logic

Tạo chính xác cấu trúc **build-logic/src/main/groovy** và bốn tệp plugin. Vì sao chúng không đặt trong **core/src/main/java**? Chạy **./gradlew :core:tasks --all** và nhận diện Test/Checkstyle/JaCoCo/publish tasks.

### Bài 2 — Bỏ một plugin

Bỏ **team.java-quality** khỏi **app/build.gradle**, giữ application. Điều gì xảy ra với JUnit dependencies, Checkstyle/JaCoCo? Sau đó khôi phục plugin để app có quality policy.

### Bài 3 — Thêm module mới

Thêm module **:util** có Java source và hai tests, apply **team.java-quality**, không apply publishing. Kiểm tra việc module tự nhận JDK 17, JUnit 5, Checkstyle, JaCoCo mà không copy code convention.

### Bài 4 — Java toolchain

Tạm đổi **JavaLanguageVersion.of(17)** trong **team.java-base.gradle** thành version khác mà CI có. Chạy task Java của cả core và app. Vì sao một thay đổi trong plugin ảnh hưởng nhiều modules?

### Bài 5 — Vi phạm Checkstyle

Thêm một wildcard import trong một Java test class, chạy **:core:checkstyleTest**. Xem report và khôi phục code. Vì sao Checkstyle config đặt ở root nhưng được áp dụng thông qua mỗi project plugin?

### Bài 6 — Cấu hình coverage gate

Thay ngưỡng coverage từ 0.20 lên 0.80 trong branch thử nghiệm, chạy **:app:check**, xem vi phạm nếu thực tế chưa đủ coverage. Bổ sung tests hoặc thảo luận threshold hợp lý. Không sửa report XML để làm gate pass giả.

### Bài 7 — Report XML

Chạy **:core:jacocoTestReport** và mở XML/HTML, so sánh với JUnit XML. Loại báo cáo nào chứa testcase pass/fail, loại nào chứa line/branch coverage?

### Bài 8 — Không publish app

Chạy **:app:tasks --all** và **:core:tasks --all**. Giải thích vì sao chỉ core có Maven publication từ team.java-publish. Nếu app có publication do plugin khác, hãy tìm rõ nguồn thay vì kết luận convention bị lỗi.

### Bài 9 — Local staging

Chạy:

~~~bash
./gradlew :core:publishMavenJavaPublicationToLocalStagingRepository
~~~

Kiểm tra JAR, sources JAR, Javadoc JAR, POM trong **core/build/staging-repo**. So sánh với **publishToMavenLocal**.

### Bài 10 — Tách policy publish

Giả sử một số libraries chỉ muốn Java/test/quality, số khác cần publish. Thiết kế một plugin **team.java-library** và plugin **team.java-publish** apply nó, tránh thêm Maven publish tasks cho module chưa phát hành.

### Bài 11 — Catalog của included build

Thêm version catalog vào main build. Thử dùng cùng **libs** từ build-logic mà không khai báo catalog trong build-logic settings. Giải thích sự khác nhau của build boundary và cách chia sẻ TOML có kiểm soát.

### Bài 12 — External plugin dependency

Chọn một community Gradle plugin thật đã được tổ chức duyệt và thử áp dụng trong precompiled script plugin. Vì sao phải đưa artifact plugin lên **build-logic implementation classpath**, không chỉ khai báo plugin ID trong module?

### Bài 13 — Task lazy APIs

Tìm một đoạn **tasks.getByName** hoặc **tasks.all** trong convention plugin thử nghiệm, đổi sang **tasks.named**/**configureEach**, so sánh task graph/configuration time bằng Gradle diagnostics.

### Bài 14 — TestKit

Tạo fixture build chỉ apply **team.java-tests**, dùng GradleRunner để chạy task **test** và xác minh JUnit Platform/report outputs. Vì sao unit test Java class đơn thuần không đủ để kiểm tra Gradle plugin wiring?

### Bài 15 — CI quality gate

Cấu hình GitHub Actions để chạy **:core:check :app:check**, upload reports theo **always**, chỉ stage/publish artifacts sau khi tests/quality pass. Nêu cách bảo vệ signing/repository credentials nếu sau này thêm release.

### Bài 16 — Project boundary

Tạo một second included build riêng chứa plugin khác. Vì sao root dependencyResolutionManagement không tự áp dụng cho included build đó, và vì sao app vẫn không nên lấy build-logic dependency qua project(':build-logic')?

## 24. Câu hỏi tự kiểm tra

1. Convention plugin là gì?
2. Tại sao nên dùng nó thay vì copy/paste build.gradle?
3. Convention plugin có bắt buộc là một binary Plugin<Project> class không?
4. Precompiled Groovy script plugin nằm ở directory nào?
5. Plugin ID được suy ra như thế nào từ tên file?
6. Tại sao build-logic là included build, không phải app subproject?
7. buildSrc khác build-logic ở đâu?
8. Vì sao cần **groovy-gradle-plugin** trong build-logic?
9. Plugin IDs trong main project được resolve nhờ câu lệnh settings nào?
10. Vì sao main repositories không tự áp vào build-logic?
11. Module nào trong lab có Maven publication?
12. Plugin **team.java-base** làm nhiệm vụ gì?
13. **team.java-tests** phải dùng **useJUnitPlatform()** để làm gì?
14. **testImplementation** khác **implementation** như thế nào?
15. **team.java-quality** cung cấp những kiểm tra nào?
16. Vì sao Checkstyle cần một file config thật?
17. **jacocoTestReport** và **jacocoTestCoverageVerification** khác nhau ra sao?
18. Vì sao phải nối coverage verification vào check?
19. **finalizedBy(jacocoTestReport)** có bảo đảm report luôn tồn tại khi compileJava fail không?
20. **team.java-publish** dùng plugin và component nào?
21. **withSourcesJar()** tạo artifact nào?
22. Maven repository localStaging có phải Maven Central không?
23. Vì sao app không apply team.java-publish?
24. **tasks.named** khác **tasks.getByName** ra sao?
25. Vì sao không nên resolve runtimeClasspath ngay trong configuration phase?
26. Version catalog của main có tự có trong build-logic không?
27. Khi áp dụng external plugin trong precompiled script plugin, classpath cần gì?
28. Binary convention plugin phù hợp khi nào?
29. TestKit kiểm tra điều gì ngoài unit tests của app?
30. Gradle task **check** có tự publish artifact không?
31. Vì sao build logic không được đưa vào production runtimeClasspath?
32. Khi muốn ký Maven publication, cần thêm chính sách bảo mật nào?
33. Vì sao nên có CI published-artifact verification ngoài local project test?
34. Nếu root dùng subprojects{} để apply mọi plugin, rủi ro kiến trúc là gì?
35. Java 17 compilation với javac có chứng minh Gradle convention plugin đã hoạt động không?

**Đáp án gợi ý:** (1) reusable build policy as plugin; (2) nhất quán/dễ bảo trì; (3) không, precompiled scripts cũng được; (4) build-logic/src/main/groovy; (5) tên file bỏ .gradle; (6) ranh giới Gradle plugin build riêng; (7) buildSrc tự nhận diện/inject, build-logic explicit included build; (8) biên dịch Groovy precompiled scripts; (9) pluginManagement.includeBuild; (10) khác settings/build; (11) core; (12) Java17/UTF-8/release 17; (13) JUnit5 test engine; (14) test scope và production scope; (15) Checkstyle/JaCoCo; (16) policy phải có rules; (17) báo cáo so với enforce rule; (18) check không tự phụ thuộc verify; (19) không; (20) java-library+maven-publish+components.java; (21) source JAR; (22) không, chỉ thư mục build; (23) app không cần publish thư viện; (24) lazy so với eager; (25) performance/config cache; (26) không; (27) plugin implementation dependency trong build-logic; (28) logic typed phức tạp/chia sẻ nhiều build; (29) plugin wiring/task outcomes; (30) không; (31) build classpath khác app runtime; (32) secret store, trusted release jobs, signing; (33) metadata/variants contract; (34) coupling/ẩn logic/performance; (35) không.

## 25. Checklist áp dụng convention plugin vào dự án thật

- [ ] Chia rõ trách nhiệm Java, tests, quality, publishing, optional signing.
- [ ] Đặt plugin logic trong build-logic included build hoặc cơ chế được phê duyệt.
- [ ] Plugin IDs có namespace và tên ổn định; không trùng core/external plugin IDs.
- [ ] build-logic có settings và repositories riêng.
- [ ] Root settings include build-logic ở đúng thời điểm plugin resolution.
- [ ] Không dùng project(':build-logic') như production Java dependency.
- [ ] Modules opt-in đúng plugin IDs; không apply publishing cho mọi app.
- [ ] Java toolchain/source compiler target và encoding rõ ràng.
- [ ] JUnit dependencies đúng testImplementation/testRuntimeOnly.
- [ ] Mọi Test task cần kiểm thử được cấu hình JUnit Platform và HTML/XML reports.
- [ ] Checkstyle config exists; rules/suppressions được review và version hóa.
- [ ] Checkstyle/JaCoCo tool versions tương thích Gradle/JDK.
- [ ] JaCoCo report và verification có dependencies thực sự với Test task.
- [ ] Coverage thresholds phù hợp từng loại module và test suite.
- [ ] Coverage verification được nối check nếu là quality gate.
- [ ] Generated sources và integration tests có policy/reporting riêng nếu cần.
- [ ] Không resolve dependencies hoặc đọc project khác quá sớm trong plugin configuration.
- [ ] Dùng tasks.register/named/configureEach và Provider API.
- [ ] Không dùng allprojects/subprojects broad cross-project mutation khi conventions đủ.
- [ ] External plugin implementations được khai báo trên build-logic classpath.
- [ ] Version catalogs giữa main và included builds được chia sẻ có chủ đích.
- [ ] Maven publication dùng components.java, metadata/POM đúng.
- [ ] Sources/Javadoc artifacts và release info đầy đủ.
- [ ] Không upload repo khác/lộ credentials từ build logic.
- [ ] Signing được giới hạn cho trusted release builds và keys ở ngoài source.
- [ ] TestKit/consumer fixtures kiểm tra plugin task wiring và regression.
- [ ] CI giữ reports khi fail nhưng không che quality failure status.
- [ ] Publishing chỉ xảy ra sau successful tests/quality checks và approval.
- [ ] Build-logic changes được review và thử trên representative projects.
- [ ] Gradle Wrapper/JDK/plugin versions được pin/upgrade có kiểm soát.
- [ ] Configuration cache và performance được đo thay vì giả định.
- [ ] Plugin API/extensions và migration notes được tài liệu hóa.

## 26. Tài liệu chính thức

- [Gradle — Best Practices for Structuring Builds](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html)
- [Gradle — Sharing Build Logic using buildSrc and build-logic](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html)
- [Gradle — Convention Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html)
- [Gradle — Pre-compiled Script Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html)
- [Gradle — Implementation Options for Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins.html)
- [Gradle — The Groovy Gradle Plugin](https://docs.gradle.org/current/userguide/groovy_gradle_plugin.html)
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html)
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — The Checkstyle Plugin](https://docs.gradle.org/current/userguide/checkstyle_plugin.html)
- [Gradle — The JaCoCo Plugin](https://docs.gradle.org/current/userguide/jacoco_plugin.html)
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Gradle — The Signing Plugin](https://docs.gradle.org/current/userguide/signing_plugin.html)
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html)
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Gradle — Gradle TestKit](https://docs.gradle.org/current/userguide/test_kit.html)
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html)
- [Gradle — Understanding Gradle's Plugin System](https://docs.gradle.org/current/userguide/plugins.html)

**Kết luận:** Convention plugins biến những quy tắc Java, kiểm thử, chất lượng và xuất bản thành **build logic có tên, có trách nhiệm và tái sử dụng được**. Dựng **build-logic** bằng **groovy-gradle-plugin**, tách các plugin **team.java-base → team.java-tests → team.java-quality → team.java-publish**, rồi cho từng module opt-in theo nhu cầu. Kết hợp JDK 17, JUnit 5, Checkstyle, JaCoCo và MavenPublication theo task/dependency APIs của Gradle sẽ tạo một multi-project build rõ ràng, có quality gates và sẵn sàng mở rộng. CI và release policy vẫn phải kiểm chứng artifact thật, bảo vệ secrets và kiểm tra các convention plugins như một phần mềm có thể lỗi.
