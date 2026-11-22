# Tái hiện rồi xử lý xung đột dependency, variant và toolchain trong Gradle

## 1. Bài thực hành tổng hợp giải quyết vấn đề gì?

Một dự án Java dùng Gradle có thể biên dịch tốt hôm qua nhưng hôm nay thất bại sau khi thêm thư viện, đổi plugin hoặc nâng JDK. Thông báo cuối cùng đều có thể là **BUILD FAILED**, nhưng có ít nhất ba cơ chế độc lập:

- **Dependency version conflict:** cùng một module được yêu cầu ở nhiều phiên bản; Gradle phải quyết định chọn phiên bản nào hoặc báo lỗi theo chính sách.
- **Variant conflict:** Gradle không tìm thấy biến thể của component đáp ứng các attributes mà consumer yêu cầu, chẳng hạn Java 17 consumer không thể dùng thư viện chỉ tương thích Java 21.
- **Java toolchain conflict:** Gradle cần một JDK/compiler đáp ứng languageVersion/vendor/implementation nhưng không tìm thấy, hoặc toolchain provisioning bị ngăn bởi chính sách môi trường.

Chúng khác nhau ở **giai đoạn thất bại, bằng chứng và cách sửa**. Một dependency graph conflict không thể sửa bằng cách cài thêm JDK. Một thư viện Java 21 không nên được ép thành Java 17 bằng việc sửa metadata cho Gradle khỏi phàn nàn. Một JDK chưa được cài không xuất hiện chỉ vì thêm **--refresh-dependencies**.

Bài thuộc nhóm **Thực hành tổng hợp** trong **Build Tool Gradle**, theo đúng đề bài **“Tái hiện rồi xử lý xung đột dependency, variant và toolchain”**.

### Kết quả cần đạt

Sau bài này, bạn có thể:

1. Dựng một project Gradle Java 17 với hai modules **:library** và **:app** có thể chạy độc lập.
2. Tạo ba lỗi có kiểm soát bằng **Gradle project properties**, mỗi lần chỉ kích hoạt một loại.
3. Nhận diện Gradle **default version selection**, **failOnVersionConflict**, dependency constraints, strict versions và locking.
4. Đọc **dependencies** và **dependencyInsight** để biết requested/selected versions và selection reasons.
5. Đọc **outgoingVariants** của producer và **resolvableConfigurations** của consumer.
6. Hiểu attributes **org.gradle.jvm.version**, **org.gradle.usage**, **org.gradle.category**, **org.gradle.libraryelements**, custom attributes và capabilities.
7. Hiểu Java toolchain khác **Gradle Daemon JVM**, **options.release** và **runtime JVM**.
8. Dùng **javaToolchains**, **--info** và **--stacktrace** mà không gây lộ dữ liệu nhạy cảm.
9. Phân biệt **No matching variant**, **No matching toolchains**, **Could not resolve**, **UnsupportedClassVersionError**.
10. Chứng minh bản sửa bằng compile, tests, runtime output và báo cáo graph/attributes.
11. Ghi MRE, CI regression và checklist ngăn tái phát lỗi.
12. Tránh các “giải pháp” nguy hiểm như ép version tùy ý, hạ minimum JVM giả hoặc xóa cache không có giả thuyết.

**Nguyên tắc xuyên suốt:** **baseline xanh → chỉ thay một biến → tái hiện lỗi → lấy bằng chứng đúng tầng → sửa → chạy regression**.

## 2. Ba tầng lỗi trong Gradle

| Tầng | Gradle thực hiện điều gì? | Biểu hiện điển hình | Công cụ hữu ích |
| --- | --- | --- | --- |
| Module version resolution | Chọn component version cho cùng group:name | 3.12.0 bị nâng lên 3.14.0, hoặc conflict fail | dependencyInsight, dependencies |
| Variant-aware resolution | Chọn variant có attributes phù hợp | No matching variant / ambiguous variants | outgoingVariants, resolvableConfigurations |
| Java toolchain selection | Tìm một compiler/JDK installation phù hợp | No matching toolchains, auto-provisioning error | javaToolchains, --version |
| JVM runtime verification | JVM tải compiled class files | UnsupportedClassVersionError | java -version, javap |
| Repository/artifact download | Lấy metadata/POM/JAR qua mạng | HTTP 401, PKIX, timeout, 404 | --info, repositories |
| Task execution | Chạy compiler/tests/packager | Compile error, test failure, OOM | Task log, reports, --stacktrace |

Một lỗi có thể che lỗi khác: nếu compileClasspath không resolve vì variant mismatch, Gradle chưa cần khởi động javac để phát hiện toolchain thiếu. Sau khi sửa variant, lỗi toolchain mới có thể xuất hiện. Vì vậy phải lặp toàn bộ quy trình sau từng bản sửa.

### 2.1. Không phải mọi conflict đều gây failure

Khi module được yêu cầu ở 3.12.0 và 3.14.0, mặc định Gradle chọn phiên bản phù hợp theo version conflict resolution (thông thường là phiên bản cao hơn). **Chỉ khi cấu hình yêu cầu conflict phải fail hoặc versions/constraints không thể cùng thỏa mãn**, build mới phải dừng ở tầng version.

### 2.2. Java compatibility không phải phép so bằng nhau tuyệt đối

Đối với JVM library variants, producer báo minimum JVM 11 thường có thể dùng trong Java17 consumer. Producer báo min21 không thể dùng với Java17 consumer. Gradle dùng compatibility và disambiguation rules, không chỉ so hai version có bằng nhau hay không.

~~~text
Producer JVM minimum 11 -> Consumer JVM 17 : phù hợp
Producer JVM minimum 17 -> Consumer JVM 17 : phù hợp
Producer JVM minimum 21 -> Consumer JVM 17 : không phù hợp
Producer JVM minimum 17 -> Consumer JVM 21 : phù hợp
~~~

## 3. Chuẩn bị trước khi thực hành

Ví dụ sử dụng:

- **JDK 17** có javac và java.
- Gradle Wrapper **9.1.0**, bản phát hành chính thức 18/9/2025, phù hợp với cấu hình lab.
- Java application và Java library Gradle core plugins.
- Commons Lang3 **3.14.0** và **3.12.0** làm tình huống conflict.
- JUnit Jupiter **5.11.4** và Platform Launcher **1.11.4**.
- Maven Central hoặc mirror đã được tổ chức cho phép.
- Không cần Docker, database, API token, JDK21 hay JDK99.

Để thử với một Wrapper khác, phải đối chiếu tài liệu Gradle của đúng phiên bản đó. Không tự nâng Gradle Wrapper và JDK trong cùng một phép kiểm thử rồi kết luận lỗi đã được sửa.

### 3.1. Xác minh Java/Gradle

Linux/macOS:

~~~bash
java -version
javac -version
./gradlew --version
~~~

Windows PowerShell:

~~~powershell
java -version
javac -version
.\gradlew.bat --version
~~~

Không có stdout version cố định vì mỗi máy khác nhau. Cần ghi chính xác Java vendor, major version, Gradle version, OS/architecture khi gửi issue.

### 3.2. Tạo Wrapper

Nếu chưa có Wrapper, dùng một Gradle CLI tin cậy để tạo trong project:

~~~bash
gradle wrapper --gradle-version 9.1.0
~~~

Commit **gradlew**, **gradlew.bat**, **gradle/wrapper/gradle-wrapper.properties** và **gradle-wrapper.jar**. Kiểm tra distribution checksum và nguồn Wrapper theo chính sách security. Từ lần sau, dùng **./gradlew** thay vì bản Gradle toàn máy.

### 3.3. Nếu baseline không tải được dependency

Một lỗi TLS/HTTP/proxy khi tải JUnit hoặc Commons Lang là **repository failure**, chưa phải conflict được tạo bởi lab. Hãy làm môi trường có thể resolve Maven artifacts trước khi thực nghiệm. Không tắt certificate verification hoặc tải JAR từ nguồn không tin cậy để làm build xanh.

## 4. Thiết kế lab: ba tình huống độc lập

Cấu trúc:

~~~text
gradle-conflict-clinic/
├── settings.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── library/
│   ├── build.gradle
│   └── src/main/java/clinic/library/
│       ├── Greeter.java
│       └── DirectRunner.java
└── app/
    ├── build.gradle
    ├── src/main/java/clinic/app/Main.java
    └── src/test/java/clinic/app/AppTest.java
~~~

Quan hệ:

~~~text
:app (consumer Java 17)
  |-- project(':library') -> API/runtime variants
  |-- org.apache.commons:commons-lang3:3.14.0
  |-- optional 3.12.0 version request
  |-- JUnit 5 on test configurations

:library (producer Java 17)
  |-- Java source compiled with --release 17
  |-- apiElements / runtimeElements
  |-- optional synthetic metadata JVM minimum 21
~~~

Các properties:

| Property | Mặc định | Khi cố tình gây lỗi |
| --- | --- | --- |
| **addOldCommons** | false | true: thêm yêu cầu Commons Lang3 3.12.0 |
| **failOnConflict** | false | true: yêu cầu Gradle báo version conflict |
| **producerVariantJdk** | 17 | 21: công bố JVM version attribute giả lập |
| **appToolchainJdk** | 17 | 99: yêu cầu Java compiler JDK99 |

Có bốn thuộc tính điều khiển vì một version conflict có hai trạng thái cần quan sát: **Gradle tự chọn** và **Gradle bị yêu cầu fail khi conflict**.

Không bật cả ba lỗi cùng lúc; mỗi lượt bắt đầu từ baseline/default properties.

## 5. File settings.gradle

~~~groovy
rootProject.name = 'gradle-conflict-clinic'

include 'library', 'app'

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
~~~

**Ý nghĩa:**

- Root project đặt tên cố định.
- Hai subprojects có riêng build.gradle.
- Dependency repositories được khai báo tại settings; không cần lặp repositories ở :app hoặc :library.
- Plugins **application** và **java-library** là core Gradle plugins, không cần tải một plugin cộng đồng chỉ để chạy lab.

Nếu tổ chức có Maven mirror, sử dụng settings/repository policy của tổ chức với TLS và credentials đúng API; không hardcode token trong URL hoặc source file.

## 6. library/build.gradle: producer và metadata điều khiển được

Tạo **library/build.gradle**:

~~~groovy
plugins {
    id 'java-library'
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

// Synthetic variant-mismatch switch.
// Bytecode thực của library vẫn là Java 17.
def reportedJdk = providers.gradleProperty('producerVariantJdk')
        .map { Integer.parseInt(it) }
        .getOrElse(17)

['apiElements', 'runtimeElements'].each { variantName ->
    configurations.named(variantName) {
        attributes {
            attribute(
                org.gradle.api.attributes.java.TargetJvmVersion.TARGET_JVM_VERSION_ATTRIBUTE,
                reportedJdk
            )
        }
    }
}
~~~

**Đây là một mô phỏng lỗi metadata có chủ đích.** Trong lab, **-PproducerVariantJdk=21** chỉ đổi thuộc tính mà producer công bố, **không đổi JDK compiler hoặc bytecode thực tế**. Bằng cách này có thể tái hiện **No matching variant** trên máy chỉ có JDK17.

Trong production, tuyệt đối không khai báo minimum JVM giả. Nếu artifact thực sự biên dịch với Java21, metadata min17 là sai và có thể khiến ứng dụng Java17 vỡ lúc chạy. Cách sửa production là biên dịch artifact phù hợp Java17 hoặc nâng consumer/runtime theo chính sách, không đơn giản đổi metadata.

### 6.1. Vì sao java-library tạo variants?

Java Library plugin công bố các variants như **apiElements** và **runtimeElements**; Gradle sẽ chọn tùy compile/runtime usage của consumer. Những attributes chính có thể gồm:

~~~text
org.gradle.category            = library
org.gradle.usage               = java-api / java-runtime
org.gradle.libraryelements     = jar
org.gradle.dependency.bundling = external
org.gradle.jvm.version         = 17
~~~

Có thể có secondary variants như compiled classes directories, sources hoặc javadoc tùy cấu hình. Đọc report thực tế:

~~~bash
./gradlew :library:outgoingVariants --console=plain
~~~

Tên variant là nhãn chẩn đoán; Gradle dùng **attributes và selection rules** để quyết định, không chỉ nhìn tên.

### 6.2. Tại sao override cả API và runtime variants?

Compile classpath tiêu thụ API variant, runtime classpath tiêu thụ runtime variant. Nếu chỉ override một bên, có thể thấy compile fail nhưng runtime report vẫn khác, khiến bài thực hành khó giải thích. Lab cố ý công bố cùng một minimum JVM synthetic cho cả hai.

## 7. Greeter.java: phần thư viện Java17

Tạo **library/src/main/java/clinic/library/Greeter.java**:

~~~java
package clinic.library;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }
        return "Hello, " + name.trim() + "!";
    }
}
~~~

Public API là **Greeter.greet(String)**. Java17 hỗ trợ String.isBlank(). Class không phụ thuộc một Maven module bên ngoài.

### 7.1. DirectRunner.java: kiểm chứng bằng javac

Tạo **library/src/main/java/clinic/library/DirectRunner.java**:

~~~java
package clinic.library;

public final class DirectRunner {
    private DirectRunner() {
    }

    public static void main(String[] args) {
        System.out.println(
                Greeter.greet(" Gradle "));
    }
}
~~~

Linux/macOS từ root:

~~~bash
mkdir -p out

javac --release 17 -encoding UTF-8 -d out \
  library/src/main/java/clinic/library/Greeter.java \
  library/src/main/java/clinic/library/DirectRunner.java

java -cp out clinic.library.DirectRunner
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null

javac --release 17 -encoding UTF-8 -d out library\src\main\java\clinic\library\Greeter.java library\src\main\java\clinic\library\DirectRunner.java

java -cp out clinic.library.DirectRunner
~~~

**Stdout chính xác:**

~~~text
Hello, Gradle!
~~~

Phép thử javac độc lập chỉ xác nhận Java source hợp lệ. Nó **không kiểm tra** Gradle project dependency, Maven resolution, outgoing variant hoặc missing toolchain trong :app.

## 8. app/build.gradle hoàn chỉnh

Tạo **app/build.gradle**:

~~~groovy
plugins {
    id 'application'
}

def addOldCommons = providers.gradleProperty('addOldCommons')
        .map { it.toBoolean() }
        .getOrElse(false)

def failOnConflict = providers.gradleProperty('failOnConflict')
        .map { it.toBoolean() }
        .getOrElse(false)

def requestedJdk = providers.gradleProperty('appToolchainJdk')
        .map { Integer.parseInt(it) }
        .getOrElse(17)

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(requestedJdk)
    }
}

application {
    mainClass = 'clinic.app.Main'
}

dependencies {
    implementation project(':library')

    implementation 'org.apache.commons:commons-lang3:3.14.0'

    if (addOldCommons) {
        implementation 'org.apache.commons:commons-lang3:3.12.0'
    }

    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

configurations.configureEach {
    if (failOnConflict) {
        resolutionStrategy.failOnVersionConflict()
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release.set(17)
}

tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'failed', 'skipped'
    }
}
~~~

**Giải thích:**

- **application** tích hợp Java plugin và tạo **run/installDist**.
- Java toolchain version của :app lấy qua **appToolchainJdk**, mặc định17.
- **options.release=17** buộc javac biên dịch code cho APIs/classfile Java17; nó không quyết định JDK installation được dùng.
- **implementation project(':library')** làm Gradle chọn API/runtime variants thích hợp của subproject.
- **Commons Lang3 3.14.0** được khai báo direct.
- **addOldCommons=true** tạo thêm direct request **3.12.0** cùng group:name.
- **failOnConflict=true** bật policy yêu cầu lỗi nếu configuration cần chọn giữa nhiều requested versions.
- **JUnit** chỉ nằm trên test classpaths.
- Không có một secret hoặc external service không thể giả lập nào trong code.

### 8.1. Vì sao không dùng hai project repositories?

Repository declaration là chính sách settings; tránh lặp repositories tạo khác biệt giữa subprojects. Nếu Maven Central timeout, đó là lỗi network/precondition, không phải lab xung đột.

### 8.2. failOnVersionConflict không tự có trong Gradle mặc định

Gradle mặc định có version resolution strategy xử lý nhiều requests cùng module. **failOnVersionConflict()** là kiểm tra bổ sung mà team có thể bật để không vô tình nâng dependencies. Đây là policy, không phải một thông báo lỗi luôn xảy ra khi hai versions xuất hiện.

### 8.3. Không dùng options.release để sửa thiếu toolchain

Toolchain yêu cầu một Java compiler installation. **options.release.set(17)** hướng dẫn compiler đã được chọn phải dùng Java17 language/API target. Nếu không có JDK đúng toolchain spec, compiler không thể bắt đầu chỉ nhờ --release.

## 9. Main.java: dùng cả project và external dependency

Tạo **app/src/main/java/clinic/app/Main.java**:

~~~java
package clinic.app;

import clinic.library.Greeter;
import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static String message() {
        return "APP=" + Greeter.greet(" Gradle ");
    }

    public static String normalized() {
        return "COMMONS=" +
                StringUtils.upperCase(
                        "java 17", Locale.ROOT);
    }

    public static void main(String[] args) {
        System.out.println(message());
        System.out.println(normalized());
    }
}
~~~

Main dùng:
1. **:library** qua Gradle project dependency.
2. **org.apache.commons:commons-lang3** qua Maven Central.

**Stdout chính xác của Java Main khi baseline chạy thành công:**

~~~text
APP=Hello, Gradle!
COMMONS=JAVA 17
~~~

Đây là stdout của Main, không phải toàn bộ Gradle console. Khi chạy task **run**, Gradle có thể in thêm task statuses/warnings và thời gian khác nhau.

## 10. AppTest.java: regression ở hai nhánh dependency

Tạo **app/src/test/java/clinic/app/AppTest.java**:

~~~java
package clinic.app;

import clinic.library.Greeter;
import java.util.Locale;
import org.apache.commons.lang3.StringUtils;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void projectDependencyWorks() {
        assertEquals(
                "Hello, Gradle!",
                Greeter.greet(" Gradle "));
    }

    @Test
    void externalDependencyWorks() {
        assertEquals(
                "JAVA 17",
                StringUtils.upperCase(
                        "java 17", Locale.ROOT));
    }
}
~~~

Hai methods kiểm tra output của project dependency và Maven dependency. Test task dùng JUnit Platform qua **useJUnitPlatform()**. Cần xác nhận hai tests được phát hiện thực sự, không bị NO-SOURCE/SKIPPED.

## 11. Baseline: chạy tất cả trước khi tạo lỗi

Linux/macOS:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew :library:outgoingVariants --console=plain
./gradlew clean :app:test --console=plain
./gradlew :app:run --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains
.\gradlew.bat :library:outgoingVariants --console=plain
.\gradlew.bat clean :app:test --console=plain
.\gradlew.bat :app:run --console=plain
~~~

**Kỳ vọng:**
- Cả library và app compile được bằng Java17.
- AppTest có **2 test methods pass**.
- Library outgoing JVM attribute báo17.
- App chọn được Java17 toolchain.
- Main in:

~~~text
APP=Hello, Gradle!
COMMONS=JAVA 17
~~~

Nếu baseline fail do Maven Central không tải được, cấu hình JDK17 thiếu hoặc Wrapper không chạy, hãy xử lý baseline trước. Đừng kích hoạt scenario lỗi rồi gộp hai nguyên nhân.

### 11.1. Những gì clean thực sự làm

Gradle **clean** thường xóa build outputs thuộc project, nhưng không xóa toàn bộ downloaded module caches hoặc Gradle User Home. Một build vẫn có thể dùng JUnit/Commons Lang đã tải. Không coi clean là phép “reset mọi thứ” hoặc giải pháp cho source của một dependency conflict.

## 12. Thí nghiệm A — phát hiện version conflict nhưng Gradle vẫn chạy

Thêm request cũ:

~~~bash
./gradlew :app:dependencyInsight \
  --dependency commons-lang3 \
  --configuration runtimeClasspath \
  -PaddOldCommons=true \
  --console=plain
~~~

Trong :app, direct dependencies lúc này yêu cầu:
- **org.apache.commons:commons-lang3:3.14.0**.
- **org.apache.commons:commons-lang3:3.12.0**.

Mặc định, Gradle thường chọn **3.14.0**. Có thể thấy report dạng **minh họa**:

~~~text
org.apache.commons:commons-lang3:3.14.0
Selection reasons:
  By conflict resolution: between versions 3.14.0 and 3.12.0

org.apache.commons:commons-lang3:3.12.0 -> 3.14.0
~~~

Đây không phải stdout nguyên văn cố định. Tên section/order khác nhau theo Gradle version, nhưng điều cần xác nhận là:
- Module **group:name** giống nhau.
- Có nhiều requested versions.
- Version cuối cùng được selected.
- Reason cho selection là conflict resolution.

### 12.1. Xem cây dependency

~~~bash
./gradlew :app:dependencies \
  --configuration runtimeClasspath \
  -PaddOldCommons=true \
  --console=plain
~~~

Dòng **3.12.0 -> 3.14.0** (nếu report hiển thị) biểu thị yêu cầu cũ được chọn thành phiên bản mới. Không coi yêu cầu cũ là JAR đã được đóng gói song song với JAR mới. Gradle thường resolve một module version cho một configuration.

### 12.2. Vì sao build vẫn có thể pass?

Default version conflict resolution chọn phiên bản cao hơn khi các requirements cho phép. Một conflict được giải quyết tự động không nhất thiết làm task fail. Tuy nhiên lựa chọn tự động **không chứng minh** binary/source compatibility với tất cả consumers. Cần chạy tests và kiểm tra API được sử dụng.

### 12.3. Khi dependency cũ đến từ một nhánh transitive

Nếu trong ứng dụng thật, :app phụ thuộc library X→Commons Lang3 3.12.0 và Y→3.14.0, dependencyInsight sẽ giúp tìm đường đi. Không cần sửa source của X nếu có thể nâng X/Y hay áp constraints an toàn. Phải kiểm tra release notes, tests và security, không đơn giản chọn version lớn nhất rồi bỏ qua.

## 13. Thí nghiệm A tiếp — dùng failOnVersionConflict để tạo lỗi rõ ràng

Chạy:

~~~bash
./gradlew :app:compileJava \
  -PaddOldCommons=true \
  -PfailOnConflict=true \
  --console=plain --stacktrace
~~~

Vì **failOnVersionConflict()** đã bật, Gradle phải từ chối chọn một version khi module xuất hiện với hai requested versions. Dạng lỗi có thể gần như sau:

~~~text
Could not resolve all files for configuration ':app:compileClasspath'.
Conflict found for module org.apache.commons:commons-lang3
between versions 3.12.0 and 3.14.0
~~~

Thông báo trên **chỉ minh họa failure signature**. Gradle có thể ghi thêm **Execution failed for task**, variant/dependency path hoặc suggestion tùy bản.

### 13.1. Tại sao dùng compileJava để xác nhận lỗi?

Task report **dependencies** có thể hiển thị unresolved graph theo kiểu lenient mà vẫn in report. Task **compileJava** thực sự phải resolve compile classpath để biên dịch, vì vậy conflict trên classpath có thể khiến invocation kết thúc nonzero rõ ràng.

### 13.2. Cách sửa cho lab

Không thêm requirement 3.12.0:

~~~bash
./gradlew :app:compileJava \
  -PfailOnConflict=true \
  --console=plain

./gradlew :app:dependencyInsight \
  --dependency commons-lang3 \
  --configuration runtimeClasspath \
  -PfailOnConflict=true \
  --console=plain
~~~

Sau sửa, chỉ còn Commons Lang3 3.14.0 do lab yêu cầu. Xác minh end-to-end:

~~~bash
./gradlew :app:test :app:run \
  -PfailOnConflict=true \
  --console=plain
~~~

Kỳ vọng hai tests pass và Main in hai dòng đúng. **Giữ strict conflict policy** trong verification để chứng minh yêu cầu phiên bản đã được align, thay vì chỉ tắt policy làm lỗi biến mất.

### 13.3. Cách sửa trong project thật

Nếu xung đột đến từ nhiều subprojects/transitive libraries:

1. Tìm all requested versions bằng dependencyInsight.
2. Xác định vì sao mỗi dependency yêu cầu version cụ thể.
3. Kiểm tra compatibility và known vulnerabilities.
4. Cân nhắc nâng direct dependencies, thay version constraint, BOM/platform.
5. Dùng dependency locking để giữ graph đã kiểm tra ổn định.
6. Chạy compilation, unit tests, integration tests và runtime smoke tests.
7. Không áp force xuống phiên bản cũ nếu library khác cần API mới.

## 14. Dependency constraints và strictly

**Dependency constraint** mô tả version requirement trên một module khi module được resolve. Nó không tự thêm một dependency vào classpath.

Snippet Groovy DSL **chính sách mở rộng**, không thêm nguyên xi vào build.gradle lab:

~~~groovy
dependencies {
    constraints {
        implementation('org.apache.commons:commons-lang3') {
            version {
                strictly '3.14.0'
            }
            because 'Approved and tested API compatibility'
        }
    }
}
~~~

Khác biệt giữa:
- **require:** version tối thiểu/điều kiện tương thích theo Gradle rich versions.
- **prefer:** version ưu tiên, có thể bị chọn khác nếu requirements khác mạnh hơn.
- **strictly:** giới hạn cứng vào version/range.
- **reject:** loại những versions không được phép.

**Lưu ý quan trọng:** các strict constraints cùng cấp và khác cấp có precedence rules; resolutionStrategy.force hoặc rules từ consumer có thể override. Không mô tả strictly như một bảo đảm không thể bị ghi đè trong mọi hoàn cảnh. Xem Gradle dependency constraints docs để hiểu graph thật.

### 14.1. Vì sao không lạm dụng force?

~~~groovy
configurations.configureEach {
    resolutionStrategy.force(
        'org.apache.commons:commons-lang3:3.12.0'
    )
}
~~~

Đây là snippet **anti-pattern nếu dùng mù quáng**: ép 3.12.0 có thể làm một consumer cần API của 3.14.0 gặp **NoSuchMethodError** hoặc sai hành vi ở runtime. Force không tự sửa compatibility.

Chỉ force khi đã chứng minh tính tương thích, có phạm vi hẹp, ghi lý do, có tests và biết nó sẽ ảnh hưởng các configurations nào.

### 14.2. Platform/BOM và version catalog

- **Version catalog** giúp tập trung cách viết version/alias trong build scripts.
- **Platform/BOM** giúp truyền version constraints xuyên các modules/dependencies thích hợp.
- **Dependency locking** ghi selected module versions để resolution có thể tái lập.
- **Dependency verification** kiểm tra nguồn/tính toàn vẹn artifacts theo policy.

Các kỹ thuật trên hỗ trợ nhau, nhưng **không sửa một Java21 variant mismatch hoặc JDK99 toolchain missing**. Đừng dùng cơ chế của tầng dependency để che lỗi thuộc tầng khác.

## 15. Thí nghiệm B — No matching variant do Java 17/21

Trước khi gây lỗi, kiểm tra producer:

~~~bash
./gradlew :library:outgoingVariants \
  -PproducerVariantJdk=17 \
  --console=plain
~~~

Trong outgoing **apiElements** và **runtimeElements**, JVM compatibility là17.

Bật công tắc metadata sai:

~~~bash
./gradlew :library:outgoingVariants \
  -PproducerVariantJdk=21 \
  --console=plain
~~~

Giờ producer báo **org.gradle.jvm.version=21**. Java source và bytecode **vẫn target17**. Đây là lỗi metadata giả để học selection, **không phải artifact Java21 thật**.

Thử consumer:

~~~bash
./gradlew :app:compileJava \
  -PproducerVariantJdk=21 \
  --console=plain --stacktrace
~~~

App yêu cầu Java17 API variant, nhưng :library giờ công bố minimum Java21. Gradle có thể báo:

~~~text
No matching variant of project :library was found.
The consumer was configured to find a library for use
during compile-time, compatible with Java 17.
The producer declares compatibility with Java 21.
~~~

Thông báo mang tính minh họa; cần đọc **candidate variants và rejected attributes** trong log thật. Nếu lỗi xảy ra ở dependency/variant selection, **javac có thể chưa chạy**.

### 15.1. Vì sao Gradle từ chối?

JVM17 không chạy được class files đòi JVM21. Producer minimum21 không phải một biến thể phù hợp với consumer target17. Variant matching giúp phát hiện compatibility mismatch sớm thay vì cho build chạy rồi vỡ trong production.

### 15.2. Tìm consumer attributes

~~~bash
./gradlew :app:resolvableConfigurations \
  --configuration compileClasspath \
  --console=plain
~~~

Nhìn **compileClasspath** attributes như:
- **org.gradle.usage=java-api**.
- **org.gradle.category=library**.
- **org.gradle.jvm.version=17**.
- Các attributes khác theo Gradle/plugin convention.

Đối chiếu với **:library:outgoingVariants**. Nếu lỗi thật là usage/category mismatch, tăng JDK không giải quyết nguyên nhân.

### 15.3. Cách sửa variant trong lab

Vì bytecode thật target17, trả metadata về17 là đúng:

~~~bash
./gradlew :app:compileJava \
  -PproducerVariantJdk=17 \
  --console=plain

./gradlew :app:test :app:run \
  -PproducerVariantJdk=17 \
  --console=plain
~~~

Kiểm tra build không còn No matching variant và test output không đổi. Đó là bản sửa chính xác **trong lab**, nơi metadata là yếu tố duy nhất bị cố ý làm sai.

### 15.4. Với thư viện thật dùng Java 21, sửa ra sao?

**Không được hạ advertised JVM minimum xuống17** nếu thư viện được biên dịch bằng Java21 bytecode hoặc dùng Java21-only APIs. Hai lựa chọn đúng là:

1. **Giữ consumer Java17:** biên dịch producer với bytecode/API target17 (ví dụ toolchain phù hợp và **options.release=17**), thay thế Java21-only APIs, chạy regression trên Java17 rồi publish metadata17.
2. **Nâng cả hệ thống lên Java21:** nâng consumer compiler target, JDK chạy tests/app/CI/production, image, plugin compatibility và xử lý backward compatibility.

Nếu chỉ sửa metadata, Gradle có thể chọn variant nhưng JVM17 vẫn báo **UnsupportedClassVersionError** khi tải class file Java21.

## 16. Đọc variants và attributes một cách có hệ thống

Một component có thể có:

~~~text
library-1.0:
  apiElements       -> java-api
  runtimeElements   -> java-runtime
  sourcesElements   -> documentation
  javadocElements   -> documentation
~~~

Tên là để chẩn đoán. Gradle sử dụng **attribute compatibility và disambiguation**.

| Attribute | Giá trị phổ biến | Ý nghĩa |
| --- | --- | --- |
| **org.gradle.usage** | java-api / java-runtime | Compile hoặc runtime usage |
| **org.gradle.category** | library / platform / documentation | Loại component |
| **org.gradle.libraryelements** | jar / classes | Hình thức binary/source artifact |
| **org.gradle.dependency.bundling** | external / embedded / shadowed | Cách packaging dependencies |
| **org.gradle.jvm.version** | 11 / 17 / 21 | JVM compatibility requirement |
| **org.gradle.jvm.environment** | standard-jvm / android | JVM environment |
| **org.jetbrains.kotlin.platform.type** | jvm / js / androidJvm | Platform riêng của Kotlin ecosystem khi có |
| **Custom attributes** | flavor, architecture | Quy tắc do plugin/team định nghĩa |

### 16.1. No matching và ambiguous khác nhau

- **No matching variant:** không có producer candidate đủ compatible.
- **Ambiguous variants:** nhiều producer candidates compatible nhưng không có disambiguation rule đủ để chọn.
- **Missing attribute:** một bên không khai báo attribute; cần xem default compatibility/missing-value rules trước khi kết luận fail.
- **Incorrect attribute:** producer công bố không đúng với artifact thực, có thể làm resolution sai dù code compile được.

Khi ambiguous, cần phân tích các candidates còn lại; không mặc định rằng Java toolchain lỗi. Khi no matching, xác định **attribute nào bị từ chối** và vì sao.

### 16.2. Capability conflict không phải version conflict

Hai modules khác group:name có thể cùng cung cấp một capability (ví dụ hai implementations cùng API). Gradle có thể cần chọn một provider. Điều này khác với hai versions của **cùng** module Commons Lang3.

Khi gặp capability conflict:
1. Liệt kê providers và capability identifier.
2. Xác định provider mong muốn.
3. Cân nhắc excludes/substitution/capabilitiesResolution có giải thích.
4. Kiểm chứng runtime behavior.
5. Không dùng force một version của một module để giải quyết hai providers khác nhau.

### 16.3. Không ép configuration selection để né attributes

Chọn thẳng một named configuration của producer có thể bypass logic variant-aware matching và dẫn đến sai artifacts hoặc thiếu transitive dependencies. Chỉ làm khi published component có contract đặc thù và bạn hiểu hậu quả.

## 17. Thí nghiệm C — không tìm được Java toolchain

Đầu tiên:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
~~~

**./gradlew --version** phản ánh Gradle runtime/JVM mà build dùng. **javaToolchains** liệt kê Java installations Gradle phát hiện và một số metadata (JDK/JRE, vendor, version, path, architecture).

Kích hoạt lỗi:

~~~bash
./gradlew :app:compileJava \
  -PappToolchainJdk=99 \
  -Dorg.gradle.java.installations.auto-download=false \
  --console=plain --stacktrace
~~~

Bây giờ :app yêu cầu compiler **languageVersion 99**, một bản Java không có trong môi trường lab. **auto-download=false** ngăn provision JDK để kết quả tập trung vào local toolchain matching. :library vẫn dùng toolchain17.

Failure signature dạng minh họa:

~~~text
No matching toolchains found for requested specification:
languageVersion=99
~~~

Hoặc thông điệp tương đương **Cannot find a Java installation matching...** tùy Gradle version và toolchain provisioning policy. Không phụ thuộc vào từng chữ của exception message.

### 17.1. Vì sao options.release=17 không tránh lỗi này?

**options.release=17** là tham số của **javac đã được chọn**. Nếu Gradle không tìm thấy javac đáp ứng toolchain specification, compiler không khởi chạy. Khi đó release target17 chưa có cơ hội giải quyết gì.

### 17.2. Cách sửa

~~~bash
./gradlew :app:compileJava \
  -PappToolchainJdk=17 \
  -Dorg.gradle.java.installations.auto-download=false \
  --console=plain
~~~

Nếu vẫn fail vì JDK17 chưa cài/không được phát hiện:
- Cài JDK17 từ nguồn đáng tin.
- Xem **javaToolchains**.
- Kiểm tra **JAVA_HOME**, các nguồn auto-detection, **org.gradle.java.installations.paths/fromEnv**.
- Nếu dùng auto-provisioning, thiết lập một toolchain resolver repository hợp lệ, có mạng/TLS/quyền truy cập thích hợp.
- Kiểm tra Gradle Wrapper/Daemon JVM compatibility.
- Chạy lại compiler/test, không hạ release target bừa.

### 17.3. Auto-download không tự bảo đảm luôn có JDK

Gradle có thể download toolchain **nếu** được cấu hình resolver/repository phù hợp. Một project không có resolver hoặc CI bị chặn mạng vẫn có thể thiếu JDK. Vì vậy trong CI dùng **setup-java** hoặc container/JDK image được quản lý là lựa chọn rõ ràng.

### 17.4. Gradle JVM và toolchain là hai nguồn khác nhau

Một project có thể chạy Gradle bằng JDK21 nhưng compiler Java17 nhờ toolchain17. Tuy nhiên nếu Gradle Wrapper không chạy được trên JDK launch, build sẽ fail **trước khi project toolchain được giải quyết**. Khi phân tích, luôn ghi cả Gradle version và Gradle JVM, không chỉ languageVersion trong build.gradle.

## 18. So sánh Java source, Java bytecode và variant metadata

~~~text
Java sources
    |
    v
JDK compiler (toolchain)
    |
    +-- options.release / source/target compatibility
    v
class files with major version
    |
    +-- org.gradle.jvm.version advertised by producer
    v
consumer variant selection
    |
    v
runtime JVM loads .class
~~~

### 18.1. Major class version

Java 17 class file major version là **61**. Java21 class file major là **65**. Nếu JVM17 cố tải major65, xảy ra **UnsupportedClassVersionError**.

Để kiểm tra sau khi baseline compile:

~~~bash
./gradlew :library:classes :app:classes --console=plain

javap -verbose \
  library/build/classes/java/main/clinic/library/Greeter.class
~~~

Tìm trường **major version: 61**. Đây là output mong đợi cho class được compile với **--release17**. Trên Windows:

~~~powershell
javap -verbose library\build\classes\java\main\clinic\library\Greeter.class
~~~

### 18.2. Metadata và binary phải nhất quán

Trong lab, producerVariantJdk21 cố ý **không đúng bytecode** để học Gradle variant matching. Không dùng thủ thuật này để ship artifact. Với thực tế, producer min JVM phải phản ánh version tối thiểu của bytecode và APIs được sử dụng.

### 18.3. Tại sao không chỉnh consumer target lên21 chỉ để qua Gradle?

Nếu CI/production vẫn JDK17, consumer target21 sẽ dẫn tới vấn đề compiler/runtime. Mỗi quyết định nâng Java target có tác động tới Docker image, server runtime, app distribution, tests, libraries, JVM monitoring và hỗ trợ người dùng.

## 19. Ma trận lệnh tái hiện và phục hồi

| Case | Lệnh gây lỗi (thêm vào ./gradlew) | Lỗi chính | Phục hồi |
| --- | --- | --- | --- |
| Version | :app:compileJava -PaddOldCommons=true -PfailOnConflict=true | Module versions conflict | :app:compileJava -PfailOnConflict=true |
| Variant | :app:compileJava -PproducerVariantJdk=21 | No matching variant Java17/21 | :app:compileJava -PproducerVariantJdk=17 |
| Toolchain | :app:compileJava -PappToolchainJdk=99 -Dorg.gradle.java.installations.auto-download=false | Missing JDK99 | :app:compileJava -PappToolchainJdk=17 |

Chạy mỗi case từ baseline riêng, **không kết hợp property của case này với case khác**. Sau mỗi fix, chạy **:app:test :app:run** để phát hiện lỗi còn ẩn.

### 19.1. Lệnh end-to-end sau khi tất cả đã sửa

~~~bash
./gradlew clean :app:test :app:run \
  -PaddOldCommons=false \
  -PfailOnConflict=true \
  -PproducerVariantJdk=17 \
  -PappToolchainJdk=17 \
  --console=plain
~~~

Kỳ vọng:
- Module graph không còn Commons Lang3 conflict.
- Producer API/runtime variants công bố JVM17.
- App compiler tìm JDK17.
- Hai JUnit tests pass.
- Java Main in:

~~~text
APP=Hello, Gradle!
COMMONS=JAVA 17
~~~

## 20. Các công cụ Gradle tương ứng từng loại lỗi

### 20.1. dependencies

~~~bash
./gradlew :app:dependencies \
  --configuration compileClasspath \
  --console=plain

./gradlew :app:dependencies \
  --configuration runtimeClasspath \
  --console=plain
~~~

Hiển thị dependency graph cho một configuration. Nó có thể resolve metadata mà chưa cần tải toàn bộ JAR artifact files.

### 20.2. dependencyInsight

~~~bash
./gradlew :app:dependencyInsight \
  --dependency commons-lang3 \
  --configuration runtimeClasspath \
  --console=plain
~~~

Giúp biết version được chọn, những yêu cầu version nào tham gia và selection reasons như **By conflict resolution**, **By constraint**, **Forced**, **Selected by rule**. Có thể thêm **--all-variants** khi cần xem candidates.

### 20.3. outgoingVariants

~~~bash
./gradlew :library:outgoingVariants --console=plain
~~~

Giúp xem producer variants và các attributes/outputs được công bố. Đặc biệt có ích cho Java17/21 mismatch, usage/category/libraryelements hoặc capability cases.

### 20.4. resolvableConfigurations

~~~bash
./gradlew :app:resolvableConfigurations \
  --configuration compileClasspath \
  --console=plain
~~~

Giúp xem consumer configurations và các requested attributes. Khi so với outgoingVariants, sẽ biết chính xác attributes nào không tương thích.

### 20.5. javaToolchains

~~~bash
./gradlew -q javaToolchains
~~~

Giúp xem JDK/JRE được phát hiện cùng version/vendor/installation. Không phải Maven dependencies hoặc Gradle Daemon versions report.

### 20.6. --stacktrace, --info, --debug

- **--stacktrace:** exception/cause chain.
- **--info:** thêm task/configuration/dependency/toolchain details, có thể chứa internal paths.
- **--debug:** rất dài, có thể chứa secrets; chỉ dùng trong môi trường kiểm soát và khi có nhu cầu thực sự.

**--console=plain** giúp logs dễ đọc, không phải security flag. Build Scan có thể hữu ích nhưng chỉ publish khi server/permissions/data policy cho phép.

## 21. Cách tìm root cause khi một lệnh báo nhiều thông tin

Một chu trình đáng tin cậy:

1. Xác định **task failed** và **configuration** trong error.
2. Xem phase: settings/plugin, dependency resolution, variant selection, toolchain, compiler, test hay runtime.
3. Trích **What went wrong** và nguyên nhân thấp nhất có ý nghĩa.
4. Nếu là version, chạy dependencyInsight.
5. Nếu là variant, đối chiếu producer/consumer attributes.
6. Nếu là toolchain, chạy javaToolchains và --version.
7. Chỉ thay một property/configuration của nguyên nhân đã xác định.
8. Chạy lại đúng lệnh lỗi.
9. Chạy toàn bộ compile/test/run.
10. Ghi một MRE với command, expected, actual, fix và regression result.

Nếu sau khi sửa version conflict lại xuất hiện No matching variant, không kết luận bản sửa version là sai; có thể đó là lỗi thứ hai bị che. Hãy đánh giá mỗi tầng theo bằng chứng riêng.

## 22. Caches: khi nào liên quan, khi nào không?

Các cache Gradle thường gặp:

| Cơ chế | Lưu cái gì? | Có sửa được xung đột không? |
| --- | --- | --- |
| Dependency cache | Module metadata và downloaded artifacts | Không tự thay version requirements |
| Task output build cache | Outputs của cacheable tasks | Không sửa outgoing attributes/toolchains |
| Configuration cache | Configuration model/task graph | Có thể giữ config state nhưng không chữa khai báo sai |
| UP-TO-DATE | Inputs/outputs workspace hợp lệ | Không phải cơ chế resolution version |
| Gradle daemon state | JVM/process state | Có thể gây một số vấn đề riêng nhưng không thay source declarations |

**--refresh-dependencies** khiến Gradle kiểm tra dependency metadata/artifacts mới, có thể tái sử dụng bytes đã cache nếu không đổi. Nó không tải JDK99 và không biến producer Java21 thành Java17.

**--no-build-cache** ngăn task output cache restore nhưng task vẫn có thể UP-TO-DATE. **--rerun-tasks** ép task execution, hữu ích cho một số diagnostics nhưng không cần thiết để chứng minh conflict tồn tại; nó có thể làm build chậm và che tối ưu incremental.

**clean** không xóa toàn Gradle User Home. Tránh xóa **~/.gradle/caches/** trừ khi có một giả thuyết cache corruption có chứng cứ và dùng môi trường thử nghiệm riêng.

## 23. Dependency locking khi graph đã được sửa

Sau khi version conflict được giải quyết và tests pass, một project có thể bật dependency locking ở :app:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Đây là **snippet mở rộng**, không nằm trong build.gradle cơ sở của lab. Sau đó resolve những configurations cần khóa:

~~~bash
./gradlew :app:dependencies \
  --configuration runtimeClasspath \
  --write-locks \
  --console=plain
~~~

Gradle có thể tạo lockfile ở :app. Hãy commit/review lockfiles theo policy và dùng **--update-locks** hoặc **--write-locks** khi chủ đích nâng version.

### 23.1. Lockfile không giải quyết Java17/21 mismatch

Lockfile có thể cố định Commons Lang3 3.14.0; nó **không tự đổi** **org.gradle.jvm.version** hoặc cài toolchain JDK17. Không áp cơ chế khóa module vào vấn đề target/runtime.

### 23.2. Lockfile không thay thế verification

Locking giúp giữ selected module versions ổn định. Dependency verification/checksums và repository trust bảo vệ integrity. Tests bảo đảm behavior. Các lớp này phục vụ những mục tiêu khác nhau.

### 23.3. Không dùng dynamic versions tùy tiện

Một dependency như **3.+** có thể resolve ra release mới khi metadata cache được refresh. Điều này khiến CI và developer khác nhau khó tái hiện. Pin versions hoặc dùng constraints/locking theo yêu cầu; không cho một dependency upgrade ngầm chỉ vì hôm nay repository có artifact mới.

## 24. Những anti-pattern phải tránh

| Anti-pattern | Vì sao nguy hiểm? | Cách đúng |
| --- | --- | --- |
| Force Commons Lang3 về3.12.0 vì “bản cũ ổn” | API/ABI mismatch với library khác | dependencyInsight và tests |
| Bỏ failOnVersionConflict ngay lập tức | Che policy về graph consistency | Align/version constraints |
| Khai producer min JVM17 khi class thực Java21 | JVM17 có thể crash | Hạ bytecode/API thật hoặc nâng consumer |
| Tăng consumer target21 nhưng runtime17 | UnsupportedClassVersionError | Nâng runtime cùng policy |
| Đặt options.release17 để chữa thiếu JDK99 | Release không tìm compiler | Sửa toolchain và JDK installations |
| Bật --offline khi cache trống | Tạo lỗi thiếu artifact khác | Warm caches/kiểm tra network |
| Dùng --refresh-dependencies để sửa variant | Không ảnh hưởng attrs thật | outgoingVariants/resolvableConfigurations |
| Xóa toàn ~/.gradle/caches | Ảnh hưởng nhiều repo và che nguyên nhân | Khoanh vùng chính xác |
| Chọn runtimeElements bằng tên để né compatibility | Có thể lấy sai artifact | Giữ variant-aware matching |
| Đổi Wrapper/plugin/JDK cùng lúc | Không biết yếu tố nào sửa lỗi | A/B một biến |
| Tắt warnings/validation | Ẩn compatibility bug | Sửa model |
| Chỉ compile rồi coi đã sửa | Runtime/packaging có thể sai | Test/run/smoke test |
| Lấy lỗi fail của lab làm bug Gradle | Thí nghiệm được thiết kế fail | Phân biệt intentional failure |
| Đăng --debug log có token lên public issue | Rò dữ liệu nhạy cảm | Sanitize, kênh nội bộ |

## 25. Kịch bản production khó hơn

### 25.1. Thư viện A đòi Commons Lang3 cũ, B đòi mới

Không chỉ nhìn dependency được khai báo trong app. Chạy **dependencyInsight** để thấy **A -> Commons 3.12.0** và **B -> Commons 3.14.0**. Xem liệu:
- Có release của A tương thích3.14 không?
- Có BOM/platform quản lý cùng bộ thư viện không?
- Constraint nào đang chọn phiên bản thực?
- Có Gradle Module Metadata giàu thông tin hơn POM không?
- Có unresolved security advisory không?

Nếu phải chọn 3.14, compile/test toàn app; không coi chọn thành công là binary compatibility được bảo đảm.

### 25.2. Java21 library từ một team khác

Có thể producer publish **apiElements** min21. App Java17 không thể chọn variant. Thay vì ép attribute xuống17:
- Thỏa thuận library build Java17 API target nếu yêu cầu consumer17 còn tồn tại.
- Hoặc nâng consumer Java toolchain/production JVM lên21 có kiểm soát.
- Review release compatibility và supported runtime matrix.
- Publish đúng attributes và kiểm chứng tiêu thụ từ một Java17 test project.

### 25.3. CI báo thiếu JDK17 nhưng IDE chạy được

Các khả năng:
- IDE có JDK17 cài sẵn, runner không có.
- JAVA_HOME của CI chỉ tới JRE hoặc JDK khác.
- CI không cấu hình auto-provisioning resolver.
- Architecture/vendor filter quá chặt.
- Gradle Daemon JVM và JavaCompile toolchain khác nhau.
- Container image thay đổi giữa runs.

Đọc **javaToolchains** và **--version** từ **chính CI runner**, không lấy kết quả từ máy developer làm bằng chứng thay.

### 25.4. Plugin Gradle cũ với Gradle Wrapper mới

Một lỗi plugin API có thể xuất hiện trước dependency/variant toolchain. Ghi plugin version, Gradle version và compatibility matrix. Đừng force dependency hoặc thay Java target nếu nguyên nhân là Gradle plugin không tương thích.

### 25.5. Capability conflict

Hai modules cùng cung cấp một capability không phải là nhiều versions của cùng group:name. Cần xem providers, capability IDs và configure selection/excludes theo chủ đích. Không dùng **resolutionStrategy.force** một version rồi giả conflict đã hết.

## 26. CI regression dùng Java17

Ví dụ tạo **.github/workflows/gradle-conflict-lab.yml**:

~~~yaml
name: Gradle dependency variant toolchain clinic

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

      - name: Install Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v4

      - name: Compile and test
        run: |
          ./gradlew clean :app:test \
            -PaddOldCommons=false \
            -PfailOnConflict=true \
            -PproducerVariantJdk=17 \
            -PappToolchainJdk=17 \
            --console=plain

      - name: Verify Java output
        shell: bash
        run: |
          actual="$(./gradlew -q :app:run)"
          expected="$(printf '%s\n' \
            'APP=Hello, Gradle!' \
            'COMMONS=JAVA 17')"
          test "$actual" = "$expected"

      - name: Store JUnit XML
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: java17-conflict-clinic-tests
          path: app/build/test-results/test/TEST-*.xml
          if-no-files-found: warn
          retention-days: 14
~~~

Job trên **chỉ chạy baseline đã sửa**, không cố tình tạo failure ở workflow production. Nếu muốn automation kiểm thử negative cases, viết harness xác minh **nonzero exit code và đúng failure signature**. Đừng dùng **|| true** để biến mọi lỗi thành BUILD SUCCESSFUL.

### 26.1. Những điều CI phải kiểm soát

- Wrapper version pin trong repository.
- JDK17 toolchain có sẵn.
- Maven Central/mirror tin cậy với TLS.
- Không dùng dynamic library versions thiếu kiểm soát.
- Tránh mix CPU/OS/architecture khi so behavior của toolchain.
- Không cấp publish/signing secrets cho untrusted pull requests.
- Khi upload JUnit XML, kiểm tra logs/reports không chứa PII/secrets.
- Nếu CI fail vì network, không đánh dấu nó là version conflict của lab.

## 27. Cách viết minimal reproducible issue

Một ticket tốt cần:

~~~markdown
# Gradle issue: version / variant / toolchain conflict

## Environment
- Gradle Wrapper: exact version
- Gradle JVM: JDK vendor and version
- Java compiler toolchain: requested version
- OS/architecture: relevant values

## Steps to reproduce
1. Run exact Wrapper command.
2. Observe task and configuration.
3. Compare producer/consumer or version selection report.

## Expected
Describe the contract that should hold.

## Actual
Exact error category and essential cause chain.

## Evidence
- Dependency: dependencyInsight excerpt
- Variant: outgoingVariants + resolvableConfigurations excerpt
- Toolchain: javaToolchains excerpt

## Fix / verification
One changed property or configuration and repeated compile/test/run.

## Data hygiene
No passwords, private URLs, tokens or real customer records.
~~~

Mẫu trên cần thay bằng kết quả thực tế trước khi gửi. Đừng gửi cả **~/.gradle/**, source private hoặc debug logs lớn nếu không cần. Nếu report có usernames/internal paths, redact nhất quán nhưng vẫn giữ attribute names, versions và error categories.

## 28. Bài tập thực hành

### Bài 1 — Baseline sạch

Dựng tất cả files, chạy **clean :app:test** rồi **:app:run**, ghi kết quả hai tests và hai dòng stdout.

### Bài 2 — Javac đơn

Chạy Greeter/DirectRunner bằng **javac --release17**. Vì sao đây không phải phép thử version/variant/toolchain của Gradle?

### Bài 3 — Nhìn conflict không làm build fail

Bật **addOldCommons=true** nhưng không bật strict policy, chạy dependencyInsight. Version nào được selected, vì sao?

### Bài 4 — Fail on conflict

Thêm **failOnConflict=true**, chạy :app:compileJava. Xác định group:name, requested versions và configuration gây lỗi.

### Bài 5 — Khôi phục có kiểm chứng

Tắt addOldCommons nhưng giữ failOnConflict; chạy compile/test/run. Vì sao giữ policy sau sửa giúp kiểm chứng tốt hơn chỉ tắt policy?

### Bài 6 — Thử constraint

Trong branch thử nghiệm, dùng **strictly 3.14.0**, đọc selection reason. Constraint khác dependency declaration thế nào?

### Bài 7 — Thử force an toàn

Ép 3.12.0 trong sandbox, đọc graph và chạy tests. Vì sao force có thể làm runtime errors dù Gradle resolve thành công?

### Bài 8 — Producer attributes

Chạy outgoingVariants với producerVariantJdk17 rồi21. Ghi khác biệt của **org.gradle.jvm.version**.

### Bài 9 — Consumer attributes

Chạy resolvableConfigurations cho app compileClasspath. Tìm **org.gradle.usage** và JVM compatibility.

### Bài 10 — No matching variant

Bật producerVariantJdk21, chạy app compileJava; giải thích tại sao đây là **metadata mismatch synthetic** chứ không phải compiler JDK21 thất bại.

### Bài 11 — Sửa variant

Trả producerVariantJdk về17. Giải thích vì sao cách này đúng trong lab nhưng không được hạ một Java21 artifact thật xuống metadata17.

### Bài 12 — Java21 producer thật

Nếu có JDK21, tạo producer thật target21 trong nhánh riêng và thử consumer17. Đề xuất hai hướng sửa có đảm bảo runtime compatibility.

### Bài 13 — Toolchain report

Chạy javaToolchains, ghi JDK installations. Phân biệt JVM chạy Gradle và javac toolchain.

### Bài 14 — Thiếu JDK99

Bật appToolchainJdk99 với auto-download=false. Xác định lỗi thật sự liên quan JDK, không phải Maven dependency.

### Bài 15 — Sửa JDK requirement

Đưa appToolchainJdk về17. Kiểm chứng compiler/test/run. Vì sao options.release17 không đủ để tìm javac?

### Bài 16 — Inspect bytecode

Dùng javap -verbose với Greeter.class sau baseline, tìm **major version 61**; liên hệ với runtime Java17.

### Bài 17 — Dependency locking

Sau khi sửa conflict, bật lockAllConfigurations ở :app và tạo lockfile cho configuration cần bảo vệ. Khi đổi version, cập nhật lock có review.

### Bài 18 — Capability conflict

Giải thích vì sao hai logging implementations cung cấp chung capability khác với hai Commons Lang3 versions cùng group:name.

### Bài 19 — CI kiểm chứng

Thiết kế CI JDK17 chạy compile/test/run. Không bỏ qua failures bằng --continue hoặc || true.

### Bài 20 — Bug report

Viết ba issue reports tối giản, mỗi report có command, expected/actual, Gradle version, JVM/toolchain, evidence, fix và regression.

## 29. Câu hỏi tự kiểm tra

1. Version conflict là gì?
2. Gradle mặc định chọn version như thế nào khi có nhiều requests?
3. failOnVersionConflict() làm gì?
4. Có phải mọi conflict mặc định đều fail build không?
5. dependencyInsight khác dependencies ở điểm nào?
6. Requested và selected versions khác gì?
7. Vì sao compileClasspath khác runtimeClasspath?
8. Constraint có tự thêm module vào graph không?
9. strictly khác prefer thế nào?
10. resolutionStrategy.force có thể gây hậu quả gì?
11. Version catalog có ép mọi transitive dependencies cùng version không?
12. Dependency locking giải quyết vấn đề gì?
13. Lockfile có giúp cài JDK17 không?
14. Variant là gì?
15. Gradle chọn variant bằng tên hay attributes?
16. org.gradle.usage=java-api khác java-runtime ở đâu?
17. org.gradle.category=platform có giống library không?
18. org.gradle.jvm.version biểu thị điều gì?
19. Producer minimum21 có dùng trong consumer17 không?
20. Producer minimum17 có dùng trong consumer21 không?
21. outgoingVariants dùng để xem bên nào?
22. resolvableConfigurations dùng để xem bên nào?
23. No matching variant khác ambiguous variants thế nào?
24. Capability conflict có giống version conflict không?
25. Vì sao lab không cần JDK21 để tạo variant mismatch?
26. Vì sao không hạ metadata nếu bytecode thật Java21?
27. Toolchain chọn compiler hay bytecode target?
28. options.release=17 có tự cài JDK17 không?
29. javaToolchains báo thông tin gì?
30. JDK chạy Gradle khác compiler toolchain khi nào?
31. appToolchainJdk99 gây lỗi ở tầng nào?
32. Gradle có luôn auto-download JDK không?
33. Java17 class file major version bao nhiêu?
34. UnsupportedClassVersionError do Gradle variant matching hay JVM runtime?
35. --refresh-dependencies có tải JDK99 không?
36. Vì sao xóa ~/.gradle/caches không sửa version requests?
37. Vì sao cần kiểm tra đúng error category?
38. Tại sao ba lỗi cùng lúc có thể chỉ thấy một?
39. Hai JUnit tests trong lab kiểm chứng điều gì?
40. Main có hai dòng stdout nào?
41. Vì sao nên dùng ./gradlew :app:run cho app dùng Maven library?
42. Compile pass có bảo đảm runtime pass không?
43. Khi producer Java21 thật, hai hướng sửa an toàn là gì?
44. Vì sao không cấp signing secrets cho untrusted PR?
45. Khi nào có thể coi bản sửa hoàn tất?

**Đáp án gợi ý:** (1) nhiều requested versions cùng module; (2) mặc định chọn version phù hợp, thường cao hơn; (3) fail thay vì auto-select; (4) không; (5) cây tổng thể vs đường đi/selection reason; (6) yêu cầu vs kết quả; (7) usage/variants khác; (8) không; (9) cứng vs ưu tiên; (10) binary/runtime mismatch; (11) không; (12) giữ resolved versions ổn định; (13) không; (14) một cách cung cấp component; (15) attributes; (16) compile vs runtime; (17) không; (18) JVM minimum compatibility; (19) không; (20) có; (21) producer; (22) consumer; (23) không ứng viên vs nhiều ứng viên; (24) không; (25) đổi metadata có kiểm soát; (26) runtime có thể crash; (27) JDK installation; (28) không; (29) discovered JDKs; (30) Gradle runtime và compiler có selection khác nhau; (31) toolchain selection; (32) không, cần resolver; (33) 61; (34) JVM runtime; (35) không; (36) requirements vẫn sai; (37) tránh sửa nhầm tầng; (38) fail sớm; (39) project dependency và external dependency; (40) APP=Hello, Gradle! và COMMONS=JAVA 17; (41) đúng runtimeClasspath; (42) không; (43) biên dịch producer cho17 hoặc nâng consumer/runtime21; (44) bảo vệ credentials; (45) graph/variants/JDK đúng, compile/test/run pass.

## 30. Checklist QA bài thực hành

- [ ] Đã dùng Gradle Wrapper và JDK17 được hỗ trợ.
- [ ] Có đủ settings.gradle, :library và :app build scripts.
- [ ] Có Greeter.java, DirectRunner.java, Main.java và AppTest.java đúng path/package.
- [ ] Baseline compile/test/run pass với hai JUnit tests.
- [ ] Main stdout đúng APP=Hello, Gradle! và COMMONS=JAVA 17.
- [ ] Javac DirectRunner stdout đúng Hello, Gradle!.
- [ ] Commons Lang3 3.12.0 và 3.14.0 tạo version requests khác nhau.
- [ ] Mặc định Gradle có thể resolve conflict mà không fail.
- [ ] dependencyInsight chỉ ra selected version và reason.
- [ ] failOnVersionConflict tạo failure khi hai versions được yêu cầu.
- [ ] Sau sửa giữ strict policy và graph không còn conflict của lab.
- [ ] Không dùng force để che thiếu API compatibility.
- [ ] Library outgoingVariants mặc định có org.gradle.jvm.version17.
- [ ] producerVariantJdk21 tạo No matching variant với consumer17.
- [ ] Đã hiểu variant21 của lab là metadata synthetic, không phải bytecode21 thật.
- [ ] Không khai sai min JVM trong sản phẩm thật.
- [ ] Consumer resolvableConfigurations được đối chiếu.
- [ ] Phân biệt usage/category/libraryelements/capability attributes.
- [ ] appToolchainJdk99 làm thiếu compiler JDK.
- [ ] javaToolchains cho thấy JDK17 có thể được chọn.
- [ ] Không nhầm toolchain selection với options.release.
- [ ] Không nhầm Gradle Daemon JVM và Java compiler.
- [ ] Không dùng --refresh-dependencies để sửa variant/toolchain.
- [ ] Không xóa Gradle caches thiếu giả thuyết có bằng chứng.
- [ ] Ba lỗi được chạy riêng, không bật cùng lúc.
- [ ] Mỗi lỗi đều có lệnh tái hiện và lệnh phục hồi.
- [ ] Sau sửa chạy lại compile, unit tests và runtime Main.
- [ ] Dependency constraints/locking chỉ dùng khi hiểu phạm vi.
- [ ] Logs đã review/redact và không chứa secrets.
- [ ] CI chạy trên JDK17 và kiểm tra output thật.
- [ ] Bản báo lỗi nêu đúng category, version, attributes và toolchain spec.

## 31. Tài liệu Gradle chính thức

- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Gradle — Understanding Dependency Resolution](https://docs.gradle.org/current/userguide/dependency_resolution.html)
- [Gradle — Dependency Constraints](https://docs.gradle.org/current/userguide/dependency_constraints.html)
- [Gradle — Rich Dependency Versions](https://docs.gradle.org/current/userguide/dependency_versions.html)
- [Gradle — Resolving Dependency Conflicts](https://docs.gradle.org/current/userguide/dependency_constraints_conflicts.html)
- [Gradle — Variant-Aware Dependency Resolution](https://docs.gradle.org/current/userguide/variant_aware_resolution.html)
- [Gradle — Variants and Attributes](https://docs.gradle.org/current/userguide/variant_attributes.html)
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle — Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html)
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html)
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Gradle — Command Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html)
- [Gradle 9.1.0 Release Notes](https://docs.gradle.org/9.1.0/release-notes.html)

Khi dùng Wrapper version khác, hãy đối chiếu docs và plugin APIs của chính phiên bản ấy. Các lỗi Gradle được trích trong bài là **minh họa về failure signatures**, không phải output chạy thử trên mọi môi trường.

**Kết luận:** Xung đột dependency, variant và toolchain đều có thể làm Java build thất bại nhưng nằm ở **ba tầng khác nhau**. Với version, đọc **dependencyInsight** và chọn/align module versions có kiểm chứng; với variant, so producer **outgoingVariants** và consumer **resolvableConfigurations**, giữ metadata đúng với binary compatibility; với toolchain, kiểm tra **javaToolchains** và JDK được yêu cầu, không lẫn với **options.release**. Cách khắc phục đáng tin là tái hiện một lỗi duy nhất, thu bằng chứng đúng tầng, sửa nguyên nhân, rồi chạy lại compile/test/run để chắc chắn bản sửa không chỉ làm biến mất một thông báo.
