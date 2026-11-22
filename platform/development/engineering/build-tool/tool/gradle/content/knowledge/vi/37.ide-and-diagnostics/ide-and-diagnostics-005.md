# Chẩn đoán lỗi plugin, repository, dependency và toolchain theo từng lớp

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** IDE và chẩn đoán

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Xác định **lớp hỏng đầu tiên** của một Gradle build, thay vì thử thay version hoặc xóa cache theo cảm tính.
2. Phân biệt lỗi **Wrapper/Gradle runtime JVM**, **settings**, **plugin marker**, **plugin implementation**, **repository policy**, **dependency resolution**, **variant**, **Java toolchain**, **javac/runtime** và **IDE sync**.
3. Giải thích vì sao **pluginManagement.repositories** khác **dependencyResolutionManagement.repositories**, **buildscript.repositories** và **publishing.repositories**.
4. Đọc plugin ID/version, plugin marker coordinates và implementation artifact; phân biệt core plugin **application** với external plugins cần resolve marker.
5. Dùng **RepositoriesMode.FAIL_ON_PROJECT_REPOS** để phát hiện repository injection; phân biệt GAV sai, thiếu artifact, group content-filter bị chặn, HTTP 401/403, proxy, TLS và repository stickiness.
6. Sử dụng đúng **projects, tasks, buildEnvironment, dependencies, dependencyInsight, resolvableConfigurations, outgoingVariants, javaToolchains**, cùng **--stacktrace**, **--info**, **--warning-mode all**.
7. Phân biệt **Client JVM**, **Gradle Daemon JVM**, **JavaCompiler/JavaLauncher toolchain** và IDE **Gradle JVM**; hiểu vì sao JAVA_HOME không luôn là javac compiler của project.
8. Đọc **compileClasspath** và **runtimeClasspath**, phân biệt version conflict, missing module, variant mismatch, compileOnly/runtimeOnly, noClassDefFound và NoSuchMethodError.
9. Tạo bài lab hoàn chỉnh **Gradle Groovy DSL + Java 17** dùng Maven repository trên filesystem, Java 17 Seeder tạo Maven POM/JAR, project application, JavaExec smoke task và stdout dự kiến rõ ràng.
10. Tái hiện, chẩn đoán và sửa lần lượt lỗi sai plugin ID, thiếu repository artifact, sai GAV, repository bị settings cấm, thiếu toolchain, javac missing symbol và task path không tồn tại.
11. Hiểu giới hạn của **--offline**, **--refresh-dependencies**, **--rerun-tasks**, **--no-build-cache**, **--no-configuration-cache** và **--stop**.
12. Thiết kế runbook chẩn đoán an toàn cho local/CI/IDE và ghi bằng chứng đủ dùng mà không lộ secrets.

**Quy tắc cốt lõi:** Tìm **thông báo nguyên nhân đầu tiên ở lớp sớm nhất**; chỉ dùng lệnh báo cáo của lớp ấy rồi sửa có mục tiêu. Lỗi plugin DSL không được giải quyết bằng repositories của application; lỗi Java toolchain không phải lỗi group:artifact:version; IDE đỏ nhưng Gradle CLI PASS không chứng minh source code sai.

## 1. Mô hình chẩn đoán nhiều lớp

~~~text
[0] Shell / Wrapper bootstrap
  gradlew, gradlew.bat, distribution ZIP, java executable
                 |
                 v
[1] JVM chạy Gradle
  Client / Daemon JVM, Gradle compatibility, JVM args
                 |
                 v
[2] settings.gradle
  pluginManagement, include, includeBuild, repository policy
                 |
                 v
[3] Plugin resolution / application
  core plugin, plugin marker, implementation class, extensions
                 |
                 v
[4] Repository routing / security
  URL, content filters, credentials, proxy, TLS
                 |
                 v
[5] Dependency graph / variant / artifact
  GAV, compileClasspath, runtimeClasspath, constraints
                 |
                 v
[6] Java toolchain
  JavaCompiler, JavaLauncher, JDK vendor, installation
                 |
                 v
[7] Task execution
  JavaCompile, Test, JavaExec, copy/generate/package
                 |
                 v
[8] IDE model/sync
  Tooling API, Gradle JVM, SDK, imported source sets
~~~

Đây là **thứ tự ưu tiên điều tra**, không phải một tuyên bố rằng Gradle resolve toàn bộ dependencies trước tất cả tasks. Gradle dùng cấu hình lười; một configuration có thể chỉ resolve khi task cần. Toolchain có thể được query trong configuration hoặc execution; plugin resolution có thể xảy ra ngay trong settings.

### 1.1. Năm câu hỏi chẩn đoán ban đầu

1. **Lệnh đầu tiên thất bại là gì?** Cần ghi đúng command, không chỉ “build fail”.
2. **Gradle Wrapper có chạy không?** Nếu ./gradlew --version còn fail, chưa cần dependencyInsight.
3. **Failure xảy ra ở giai đoạn nào?** Initialization, configuration, resolution hay task execution?
4. **Thông điệp ở Caused by nói gì?** Module not found khác TLS PKIX; toolchain missing khác javac cannot find symbol.
5. **Thay đổi cuối cùng ở lớp nào?** Wrapper version, pluginManagement, private repository, lockfile, Java toolchain, source code hay IDE Gradle JVM?

### 1.2. Triệu chứng thường gặp

| Dấu hiệu | Lớp xem trước | Không nên thử trước |
|---|---|---|
| Permission denied khi ./gradlew | Shell/Wrapper | Nâng Maven dependency |
| GradleWrapperMain not found | Wrapper JAR/files | Thêm Maven Central |
| Unsupported JVM to run Gradle | Daemon/client JDK | Đổi Java import |
| Plugin id/version was not found | Plugin marker repositories | Chỉ thêm project repositories |
| Failed to apply plugin | Plugin implementation/configuration | Xoá toàn bộ Gradle cache |
| Repository was added by project, forbidden | Repository policy | Bỏ enforcement vội vàng |
| Could not find GAV | Repository/artifact | Đổi Java sourceCompatibility |
| No matching variant | Consumer/producers attributes | Force một version bất kỳ |
| No matching Java installation | Toolchain | Đổi plugin ID |
| error: cannot find symbol | Java source/compileClasspath | Bắt đầu bằng TLS debug |
| UnsupportedClassVersionError | Runtime bytecode/JDK | Đổi Maven URL |
| NoClassDefFoundError / NoSuchMethodError | Runtime classpath | Chỉ nhìn compileClasspath |
| IDE sync fail nhưng CLI PASS | IDE Gradle JVM/model/plugin | Khẳng định source code sai |

Triệu chứng là gợi ý chọn lớp đầu tiên, không phải kết luận cuối cùng.

## 2. Xác định giai đoạn hỏng

Gradle có ba giai đoạn chính:

~~~text
INITIALIZATION
  settings.gradle -> projects -> pluginManagement
CONFIGURATION
  build scripts -> plugins -> extensions -> tasks registration
EXECUTION
  selected tasks, inputs/outputs, compiler/tests/JavaExec
~~~

Một số dependency resolution xảy ra theo nhu cầu trước/trong execution hoặc khi plugin cấu hình; không ép mọi lỗi “Could not resolve” vào cùng một thời điểm.

### 2.1. Phép thử phân tầng

~~~bash
./gradlew --version
./gradlew help --stacktrace --console=plain
./gradlew projects --console=plain
./gradlew :app:tasks --all --console=plain
./gradlew :app:compileJava --stacktrace --console=plain
./gradlew :app:run --stacktrace --console=plain
~~~

Cách đọc:
- **--version FAIL:** Wrapper/JDK/runtime chưa ổn.
- **--version PASS nhưng help FAIL:** settings, plugin resolution/application hoặc project configuration.
- **help PASS nhưng :app:tasks không có run:** app chưa apply application plugin, hoặc sai project path.
- **tasks PASS nhưng compileJava FAIL:** compileClasspath, toolchain hoặc javac source.
- **compileJava PASS nhưng run FAIL:** runtimeClasspath, mainClass, JavaLauncher hoặc runtime behavior.

**Không coi help PASS là app/test PASS.** help không gọi Java Main.main.

### 2.2. --dry-run không thực thi task

~~~bash
./gradlew :app:run --dry-run --console=plain
~~~

Dùng để quan sát task graph dự kiến. Nó không compile/run thật, không in ứng dụng stdout và không kiểm chứng repository artifacts đã được tải đúng trong mọi trường hợp. Nếu task graph đúng nhưng javac fail, hãy chạy command thật.

### 2.3. --stacktrace, --info và --warning-mode all

~~~bash
./gradlew :app:run --stacktrace
./gradlew :app:run --info
./gradlew help --warning-mode all
~~~

- **--stacktrace:** exception hierarchy và Caused by.
- **--info:** thêm thông tin tasks, caches, dependency/toolchain resolution.
- **--warning-mode all:** hiển thị warnings/deprecations.
- **--debug:** chỉ dùng khi cần, vì logs rất dài và có thể chứa dữ liệu nhạy cảm.
- **--scan:** Build Scan hữu ích khi so CI/IDE, nhưng phải xem chính sách privacy trước khi chia sẻ.

Mẹo: ghi nguyên văn **exception root cause đầu tiên**, đồng thời lưu vài dòng context về requested configuration, project và task.

## 3. Lớp Wrapper và Gradle runtime

### 3.1. Wrapper gồm những gì?

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
~~~

Ví dụ trong **gradle-wrapper.properties**:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
~~~

Đây là version ví dụ từ tài liệu. Dự án thật phải pin Wrapper version đã được xác nhận tương thích với plugins và JDK. Gradle Wrapper không tự xuất hiện khi tạo file build.gradle; cần tạo/commit các file Wrapper qua workflow tin cậy.

### 3.2. Những kiểm tra đầu tiên

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

Nếu java không chạy, kiểm JAVA_HOME/PATH. Nếu javac không có, có thể bạn chỉ cài JRE. Nếu ./gradlew permission denied ở Unix, kiểm executable bit:

~~~bash
chmod +x gradlew
~~~

Nếu lỗi GradleWrapperMain, kiểm gradle-wrapper.jar đúng từ source đáng tin và có trong version control. Không download một JAR lạ để chép vào Wrapper.

### 3.3. Wrapper distribution download lỗi

Khả năng:
- distributionUrl sai hoặc server không khả dụng.
- Proxy/DNS/TLS/certificate chain.
- Corporate firewall.
- Gradle distribution đã bị đổi bytes, checksum verification fail.
- GRADLE_USER_HOME permissions hoặc filesystem hết dung lượng.
- Offline machine chưa cache distribution.

**Đúng cách:** Kiểm URL HTTPS và sha256 được publish từ nguồn độc lập; sửa CA/proxy/permission. **Sai cách:** vô hiệu TLS hoặc tự cập nhật checksum theo file đáng nghi để làm build chạy.

### 3.4. Compatibility không chỉ là số Gradle

Gradle runtime Java và Java toolchain có compatibility khác nhau. Theo tài liệu Gradle 9.9, JVM chạy Gradle cần một runtime được hỗ trợ (Java 17 trở lên trong phạm vi hỗ trợ của phiên này). Một compiler toolchain Java 17 **không làm daemon đang chạy bằng Java 11 tự trở nên hợp lệ**.

## 4. Client JVM, Daemon JVM và Toolchain JVM

Một build có thể dùng nhiều JVM:

~~~text
Shell -> Wrapper / Gradle Client JVM
            |
            v
       Gradle Daemon JVM
            |
            +-- JavaCompiler toolchain -> javac
            +-- JavaLauncher toolchain -> app/test Java
            +-- Javadoc toolchain
~~~

**JAVA_HOME:** ảnh hưởng JVM khởi chạy Wrapper/client trong cấu hình thường gặp.  
**org.gradle.java.home:** có thể cấu hình JVM cho Gradle Daemon.  
**gradle-daemon-jvm.properties:** daemon JVM criteria, có thứ tự ưu tiên riêng khi hiện diện.  
**java.toolchain:** chọn compiler/launcher cho project Java tasks.  
**IDE Gradle JVM:** có thể khác terminal và phải tương thích với Gradle distribution.

### 4.1. Daemon JVM và compiler toolchain có thể khác

Ví dụ Daemon JVM chạy Java 21, nhưng project chọn Java 17 compiler:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Điều này có thể **hợp lệ và có chủ đích**. Ngược lại, nếu Daemon chạy Java 11 không được Gradle 9.9 hỗ trợ, build có thể fail trước khi toolchain Java 17 được chọn.

### 4.2. Kiểm toolchains Gradle thấy

~~~bash
./gradlew --version
./gradlew -q javaToolchains
~~~

**--version** nói về Gradle/runtime JVM. **javaToolchains** báo JDK installations được Gradle phát hiện, including version, vendor, path, JDK/JRE status tùy bản Gradle.

Nếu Gradle báo không có Java toolchain 17:
- Cài JDK 17 theo policy.
- Kiểm installation paths/auto-detection.
- Kiểm yêu cầu vendor hoặc architecture có quá chặt không.
- Nếu muốn auto-provision, phải có **toolchain resolver/download repositories** phù hợp.
- Không giả định Gradle tự tải mọi JDK khi chưa cấu hình resolver.
- Không dùng Maven dependency repository để tải compiler JDK.

### 4.3. Java 17 và --release

JavaCompile toolchain chọn compiler; nếu cần hạn chế API cho release cụ thể, có thể dùng:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Trong project đã chọn toolchain Java 17, setting trên củng cố target compatibility. Không nhất thiết dùng song song trong mọi build; **toolchain** và **--release** giải quyết vấn đề liên quan nhưng khác nhau.

### 4.4. Compiler error khác toolchain error

Nếu báo:

~~~text
error: cannot find symbol
symbol:   method source()
location: class Greeter
~~~

javac đã chạy và đang kiểm API/source. Đây không phải bằng chứng thiếu toolchain. Cần xem selected compileClasspath và Java source.

Nếu báo:

~~~text
No matching Java installation found for languageVersion=17
~~~

thì Gradle không chọn/provision được compiler/launcher phù hợp. Không cần đổi group/artifact/version khi vấn đề là JDK.

### 4.5. Bytecode không tương thích runtime

Một số Java class major versions:

| Java release | Major |
|---|---|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |

Class compiled Java 21 (major 65) không thể chạy trong JVM Java 17 (tối đa major 61). **UnsupportedClassVersionError** là lỗi runtime compatibility, khác với error: cannot find symbol do javac.

## 5. Plugin resolution: plugin ID và marker artifact

### 5.1. pluginManagement là một scope riêng

Ví dụ settings.gradle:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = 'demo'
~~~

Và consumer:

~~~groovy
plugins {
    id 'com.example.quality' version '1.2.0'
}
~~~

Đây chỉ là snippet minh họa; com.example.quality có thể không được publish. Gradle thường tìm plugin marker module có GAV dạng:

~~~text
com.example.quality:
com.example.quality.gradle.plugin:
1.2.0
~~~

Marker sẽ dẫn tới implementation JAR và dependencies. Vì vậy **Plugin ... was not found** có thể xuất phát từ:
- Sai plugin ID/version.
- Missing plugin marker trong plugin repository.
- Plugin implementation JAR hoặc transitive dependency không được cung cấp.
- Plugin Portal/private mirror không truy cập được.
- pluginManagement repositories thiếu source.
- Plugin local trong included build chưa được includeBuild đúng.

### 5.2. Gradle core plugins không cần external marker

~~~groovy
plugins {
    id 'java'
    id 'application'
}
~~~

java/application là Gradle core plugins. Nếu chúng không áp được, nhìn configuration/Gradle version/plugin conflict; **không** lập tức quy về network plugin marker.

### 5.3. Vì sao app.repositories không chữa plugin lỗi?

~~~groovy
repositories {
    mavenCentral()
}
~~~

Block này nói về **project dependencies** khi đặt trong build.gradle của project. Nó **không thay pluginManagement.repositories** phục vụ plugins DSL requests.

Nếu internal plugin dùng custom Maven repository, hãy khai đúng nguồn ở pluginManagement; phải có marker và implementation artifact hợp lệ hoặc resolutionStrategy.useModule theo kiến trúc plugin. Đừng đưa Maven Central vào mọi scope chỉ để thử.

### 5.4. Local plugin và included build

Nếu bạn có plugin source trong **build-logic**, settings có thể:

~~~groovy
pluginManagement {
    includeBuild('build-logic')
    repositories {
        gradlePluginPortal()
    }
}
~~~

Nhưng build-logic directory/settings/build files phải tồn tại và khai đúng plugin ID/implementationClass. Không thêm includeBuild vào đường dẫn chưa tồn tại như mẹo chữa mọi lỗi plugin.

### 5.5. Plugin tìm được nhưng apply fail

Khi exception nói **Failed to apply plugin**:
- Plugin marker/JAR có thể đã resolve thành công.
- Vấn đề nằm ở **Plugin.apply**, Gradle API compatibility, extension/task registration, lifecycle hoặc plugin order.
- Đọc root Caused by từ --stacktrace.
- So Gradle Wrapper version với plugin compatibility docs.
- Kiểm plugin có áp cho đúng project role không.
- Đừng thêm repositories khi lỗi là một IllegalArgumentException bên trong plugin implementation.

### 5.6. Legacy buildscript.repositories

Có thể thấy plugin cũ được load qua:

~~~groovy
buildscript {
    repositories {
        mavenCentral()
    }
    dependencies {
        classpath 'com.example:legacy-gradle-plugin:1.0.0'
    }
}
~~~

Đây là **buildscript classpath resolution**, không đồng nhất với dependencies { implementation ... } của application. Nếu tổ chức có internal plugins, inventory các scope khác nhau và đừng cho rằng một settings repository rule tự bảo vệ tất cả.

## 6. Repository policy: URL, quyền truy cập và content filters

Một settings Groovy DSL tập trung project repositories:

~~~groovy
import org.gradle.api.initialization.resolve.RepositoriesMode

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        mavenCentral()
    }
}
~~~

**FAIL_ON_PROJECT_REPOS**: Nếu project/plugin tự thêm repositories trong project scope, Gradle fail configuration. Đây có thể là kết quả đúng của security policy.

### 6.1. Ba repositoriesMode

| Mode | Ý nghĩa |
|---|---|
| **PREFER_PROJECT** | Project repositories ưu tiên khi được khai báo; thường là mặc định |
| **PREFER_SETTINGS** | Settings repositories ưu tiên; cảnh báo nếu project thêm repo |
| **FAIL_ON_PROJECT_REPOS** | Cấm project/plugin thêm repo ở project scope |

Không tắt FAIL_ON_PROJECT_REPOS chỉ để che lỗi plugin tự thêm một nguồn chưa duyệt. Hãy sửa/chuyển repository declaration đúng settings policy.

### 6.2. Project, plugin, publishing và included builds

| Nơi khai | Nhu cầu |
|---|---|
| pluginManagement.repositories | Plugin marker/implementation resolution |
| dependencyResolutionManagement.repositories | App/library project dependencies |
| buildscript.repositories | Legacy Gradle plugin/buildscript classpath |
| publishing.repositories | Nơi upload/release artifact |
| included build settings | Plugins/dependencies của included build riêng |

Các scopes phải được review độc lập. Một plugin implementation module có thể nằm group khác marker group; filter chỉ marker group chưa đủ.

### 6.3. Lỗi repository thường gặp

| HTTP/Transport | Nguyên nhân cần kiểm |
|---|---|
| 401 | Credentials thiếu hoặc sai |
| 403 | Identity không có quyền |
| 404 | URL path/POM/JAR version không có |
| 407 | Proxy authentication |
| TLS PKIX | CA/certificate chain |
| Connection timeout | Network/firewall/DNS/proxy |
| Module not allowed by filter | Repository content ownership rule |
| Repository injection forbidden | FAIL_ON_PROJECT_REPOS |

Không biến mọi lỗi thành “module version sai”. Với private repository trả **401**, hãy sửa credentials/ACL, không thêm public fallback trùng GAV.

### 6.4. includeGroup khác exclusiveContent

~~~groovy
repositories {
    maven {
        url = uri('https://repo.example.invalid/internal')
        content {
            includeGroup('com.example.internal')
        }
    }
    mavenCentral()
}
~~~

Trong ví dụ này, **includeGroup** chỉ giới hạn repository private ở đây; nó **không tự ngăn** mavenCentral phục vụ cùng group. Với một internal namespace độc quyền, dùng **exclusiveContent** ở đúng scope hoặc exclusions nhất quán ở mọi public repositories.

~~~groovy
repositories {
    exclusiveContent {
        forRepository {
            maven {
                url = uri('https://repo.example.invalid/internal')
            }
        }
        filter {
            includeGroup('com.example.internal')
        }
    }
    mavenCentral()
}
~~~

Host **.invalid** là placeholder, không có server thật. Không dùng example này như một lab kết nối mạng.

### 6.5. Repository stickiness

Gradle dependency cache có metadata theo repository origin và cơ chế repository stickiness. Đổi thứ tự repositories không luôn khiến artifact được tải lại từ nguồn khác. Dùng cache/user home riêng khi kiểm source routing, đọc logs và dependency verification; **không tự xóa toàn bộ ~/.gradle** như bước đầu.

## 7. Dependency resolution: GAV, versions và configurations

Dependency request Maven thường:

~~~text
group:artifact:version

edu.example.diagnostic:greeter:1.0.0
~~~

Gradle cần tìm metadata/artifact đúng ở nguồn được phép rồi chọn version/variant tương thích với consumer.

### 7.1. Ba báo cáo quan trọng

~~~bash
./gradlew :app:dependencies \
  --configuration compileClasspath --console=plain

./gradlew :app:dependencies \
  --configuration runtimeClasspath --console=plain

./gradlew :app:dependencyInsight \
  --dependency greeter \
  --configuration runtimeClasspath --console=plain
~~~

**dependencies** hiển thị dependency graph/selected versions; **dependencyInsight** giúp hiểu vì sao một module/version được chọn. **Không cái nào tự là chứng chỉ về artifact provenance hoặc checksum**.

### 7.2. Task báo cáo bổ sung

~~~bash
./gradlew :app:resolvableConfigurations --console=plain
./gradlew :app:outgoingVariants --console=plain
./gradlew :app:buildEnvironment --console=plain
~~~

- **resolvableConfigurations:** các configurations có thể resolve, attributes/role.
- **outgoingVariants:** những variants producer công bố cho consumer.
- **buildEnvironment:** legacy buildscript classpath dependencies, không phải app.runtimeClasspath.
- **projects/tasks:** có đúng project/task được include/apply chưa.

Các report phụ thuộc plugin/Gradle version; đừng kỳ vọng một project không có Java plugin vẫn có compileClasspath.

### 7.3. Missing module hay version conflict?

**Missing module:** Không tìm được group:artifact:version ở approved sources. Kiểm GAV, POM/JAR, content filter, auth, proxy, offline mode.

**Version conflict:** Có nhiều requested versions, Gradle chọn một version theo conflict resolution, constraints, platform BOM, locking hoặc force. Dùng dependencyInsight.

**Variant mismatch:** Module hiện diện nhưng attributes không phù hợp (usage, category, library elements, Java target compatibility, capabilities...). Dùng outgoingVariants và resolvableConfigurations, không mặc định ép force(version) để lách.

### 7.4. compileClasspath vs runtimeClasspath

- **compileClasspath:** những APIs javac được phép thấy.
- **runtimeClasspath:** các modules thực sự có khi app/Test/JavaExec chạy.
- **compileOnly:** không tự xuất hiện lúc runtime.
- **runtimeOnly:** chỉ runtime.
- **annotationProcessor:** compile-time processors, khác implementation.
- **api** trên java-library: public types được exposed cho downstream compile.
- **implementation:** library internal dependencies.

Một app có thể compile PASS nhưng run báo **NoClassDefFoundError**, do runtimeClasspath thiếu class. Một app có thể compile với version A nhưng runtime chạy JAR ABI khác rồi báo **NoSuchMethodError**. Hai lỗi đó cần xem runtimeClasspath, không chỉ javac logs.

### 7.5. Cây dependencies report minh họa

~~~text
+--- org.example:lib-a:1.0
|    \--- org.example:common:1.2 -> 1.4
\--- org.example:lib-b:2.0
     \--- org.example:common:1.4
~~~

Dấu **->** nói version đã chọn khác requested version. Đây là một cây **minh họa**, không phải output lab. Dùng dependencyInsight để biết lý do thật; không đoán rằng “repo đã chọn version cao nhất” trong mọi trường hợp.

### 7.6. Không xem dependency cache là remote repository

Cached metadata có thể khiến **--offline** build thành công dù server đang lỗi. Ngược lại, build trên CI sạch có thể fail vì artifact chưa được cache. Đó không phải bằng chứng task code khác nhau.

## 8. Java toolchain: nhận diện lỗi đúng

Trong Java build:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Nếu yêu cầu JDK 17 nhưng Gradle không phát hiện:
- Kiểm ./gradlew -q javaToolchains.
- Kiểm installation path/vendor.
- Cài đúng JDK/hoặc cấu hình trusted resolver download.
- Đảm bảo JVM để chạy Gradle tương thích với Wrapper version.
- So JAVA_HOME, org.gradle.java.home và IDE Gradle JVM.
- Không thêm Maven dependency để “có javac”.

### 8.1. Javac cannot find symbol không chứng minh thiếu JDK

Nếu trình biên dịch chạy và báo method không có:
- Kiểm Java source calls/imports.
- Kiểm selected compileClasspath version.
- Kiểm source generated bởi annotationProcessor.
- Kiểm public API vs implementation dependency ở producer.

Nếu bản JAR bạn muốn không có method đó, đổi source/API hoặc dependency version đã review; **không** tắt Java toolchain.

### 8.2. Runtime bytecode version

Các class file major versions thông dụng:
- Java 8: 52.
- Java 11: 55.
- Java 17: 61.
- Java 21: 65.

Nếu class major 65 chạy trên Java 17 runtime, **UnsupportedClassVersionError** có thể xảy ra. Sửa JavaLauncher/runtime hoặc biên dịch target tương thích, không chuyển repository tùy tiện.

## 9. IDE sync: vì sao khác command line?

IDEs như IntelliJ IDEA và Eclipse/Buildship thường dùng **Gradle Tooling API** để import project model. IDE có thể chạy Gradle bằng JVM khác shell và có cached source set/index.

### 9.1. CLI PASS nhưng IDE báo đỏ

Kiểm:
1. IDE dùng **Gradle Wrapper** hay global Gradle?
2. IDE **Gradle JVM** có tương thích Wrapper version và có cùng intent với CLI?
3. Project SDK/Module SDK/language level có phù hợp Java toolchain?
4. IDE có linked đúng root chứa settings.gradle?
5. Đã Reload/Sync Gradle sau thay settings/build files?
6. Generated sources và annotation processors có được IDE nhận diện?
7. IDE Gradle sync log có plugin failure khác CLI không?
8. Cache/index IDE có stale không?

Nếu ./gradlew :app:compileJava PASS nhưng editor đỏ, ưu tiên **Gradle sync/IDE indexing**, không đổi dependency random. Chỉ invalidate/reindex IDE cache sau khi đã xác định CLI source model đúng.

### 9.2. IDE Run PASS nhưng Gradle test FAIL

IDE có thể dùng classpath, Java launcher, workdir, env vars hoặc test runner riêng. Nên so:
- Main/test class.
- Gradle testRuntimeClasspath/runtimeClasspath.
- Gradle JVM/toolchain và IDE JDK.
- Environment variables/Java system properties.
- Test fixture/resource directories.
- Working directory.
- Test filters và reports.

**IDE test PASS không thay thế CI Gradle test PASS**. Luôn chạy chính Gradle task tương ứng để so kết quả.

### 9.3. Android build khác Java JVM lab

Android Gradle Plugin có matrix **AGP–Gradle–JDK**, Android SDK, compileSdk, variants và plugin model riêng. Bài lab này là Java 17 JVM thuần; với Android, phải tra compatibility matrix của AGP/version cụ thể trước khi nâng Gradle hoặc JDK.

## 10. Bảng công cụ chẩn đoán

| Command | Dùng khi | Không giải quyết trực tiếp |
|---|---|---|
| ./gradlew --version | Gradle/runtime JVM/Wrapper | GAV sai |
| ./gradlew help --stacktrace | Settings/plugin/config lỗi | Java runtime behavior |
| ./gradlew projects | Sai module path/include | JAR checksum |
| ./gradlew :app:tasks --all | Task run/check missing | Repository credentials |
| ./gradlew :app:buildEnvironment | Buildscript classpath | App runtimeClasspath |
| ./gradlew :app:dependencies --configuration compileClasspath | Javac dependencies | Plugin marker origin |
| ./gradlew :app:dependencies --configuration runtimeClasspath | Runtime dependencies | Task đã chạy chưa |
| ./gradlew :app:dependencyInsight --dependency greeter --configuration runtimeClasspath | Version selection | Bytes provenance |
| ./gradlew :app:resolvableConfigurations | Config attributes/roles | Java source error |
| ./gradlew :app:outgoingVariants | Producer variants | Remote registry ACL |
| ./gradlew -q javaToolchains | JDK availability/vendor/path | Maven module missing |
| ./gradlew :app:run --dry-run | Task graph | Main stdout |
| ./gradlew :app:run --stacktrace | Exception chain | Tự sửa root cause |
| ./gradlew :app:run --info | Resolution/task info | Nên chia sẻ logs không redact |
| ./gradlew help --warning-mode all | Deprecations | Plugin version upgrade tự động |
| ./gradlew --stop | Dừng Gradle daemon | Xóa artifact cache |
| ./gradlew :app:run --offline | Thử cached/local dependency behavior | Remote server hiện có chạy không |
| ./gradlew :app:run --refresh-dependencies | Refresh resolution metadata/artifact checks | Java compile syntax |
| ./gradlew :app:run --rerun-tasks | Ép task rerun | Chọn lại GAV |
| ./gradlew :app:run --no-build-cache | Tắt task output cache | Tắt up-to-date |
| ./gradlew :app:run --no-configuration-cache | Không tái sử dụng configuration cache | Sửa plugin ID sai |

**Cảnh báo:** --debug và --scan có thể công bố thông tin hệ thống, project paths, logs hoặc nội dung nhạy cảm. Kiểm policies trước khi gửi Build Scan hoặc log ra ngoài team.

## 11. Bài lab đầy đủ: lỗi ở từng lớp, artifact nội bộ hoàn toàn offline

Tạo **diagnostic-layers-lab**, gồm:
- Root settings.gradle tập trung local Maven repository.
- **app** là application Gradle project dùng Java 17.
- Library Maven GAV **edu.example.diagnostic:greeter:1.0.0** được tạo bằng chương trình Java 17 do bạn kiểm soát.
- Java application nhận method **Greeter.source()**.
- Task **smokeCheck** dùng JavaExec chạy một assertion trong test source set.
- Sau baseline, từng thay đổi có kiểm soát cho thấy lỗi ở một lớp riêng.

### 11.1. Yêu cầu

- JDK 17 đầy đủ (java, javac).
- Gradle Wrapper tương thích, ví dụ phiên Gradle 9.x hỗ trợ JVM 17.
- Không cần third-party Java dependencies; JavaCompiler và JarOutputStream thuộc JDK.
- Không cần Maven Central để resolve library của lab.
- Wrapper distribution có thể cần mạng nếu chưa tải lần đầu.
- Chỉ sửa/làm thí nghiệm trên bản sao dự án, không áp dụng cấu hình cố ý sai vào production.

### 11.2. Cây thư mục

~~~text
diagnostic-layers-lab/
├── settings.gradle
├── gradlew                       # khi đã tạo Wrapper
├── gradlew.bat
├── gradle/wrapper/...
├── tools/
│   └── SeedLocalRepository.java
├── repos/training/              # Seeder sẽ tạo
│   └── edu/example/diagnostic/greeter/1.0.0/
│       ├── greeter-1.0.0.pom
│       └── greeter-1.0.0.jar
└── app/
    ├── build.gradle
    ├── src/main/java/demo/app/Main.java
    └── src/test/java/demo/app/AppCheck.java
~~~

### 11.3. settings.gradle (Groovy DSL)

~~~groovy
import org.gradle.api.initialization.resolve.RepositoriesMode

pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = 'diagnostic-layers-lab'
include 'app'

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        maven {
            name = 'TrainingLocal'
            url = uri(new File(settingsDir, 'repos/training'))

            content {
                includeGroup('edu.example.diagnostic')
            }
        }
    }
}
~~~

Ý nghĩa:
- application là core plugin nên baseline không cần tải plugin marker.
- dependencyResolutionManagement chỉ cho local Maven repository; app không tự khai thêm.
- group filter đúng GAV Seeder sẽ tạo.
- FAIL_ON_PROJECT_REPOS giúp phân biệt lỗi repository injection.
- Nếu Seeder chưa tạo POM/JAR, dependency resolution fail đúng lớp.

### 11.4. app/build.gradle

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

application {
    mainClass = 'demo.app.Main'
}

dependencies {
    implementation 'edu.example.diagnostic:greeter:1.0.0'
}

tasks.register('smokeCheck', JavaExec) {
    group = 'verification'
    description = 'Verifies local Maven dependency at runtime'
    classpath = sourceSets.test.runtimeClasspath
    mainClass = 'demo.app.AppCheck'
}

tasks.named('check') {
    dependsOn tasks.named('smokeCheck')
}
~~~

- application cung cấp task **run**.
- Java toolchain 17 cho compile và Java launcher tasks được plugin hỗ trợ.
- JavaExec smokeCheck chạy class thuộc test source set mà không cần JUnit.
- check dependsOn smokeCheck nên :app:check kiểm tra behavior thật.
- Không có repositories block trong project.

### 11.5. app/src/main/java/demo/app/Main.java

~~~java
package demo.app;

import edu.example.diagnostic.Greeter;

public final class Main {
    private Main() {
    }

    public static String report() {
        return "status=READY\nsource=" + Greeter.source();
    }

    public static void main(String[] args) {
        System.out.println(report());
    }
}
~~~

### 11.6. app/src/test/java/demo/app/AppCheck.java

~~~java
package demo.app;

public final class AppCheck {
    private AppCheck() {
    }

    public static void main(String[] args) {
        String expected = "status=READY\nsource=local-maven";

        if (!expected.equals(Main.report())) {
            throw new AssertionError("Unexpected dependency source");
        }

        System.out.println("check=PASS");
    }
}
~~~

AppCheck có assertion thực, không chỉ println. Nếu library trả chuỗi khác, smokeCheck fail.

### 11.7. tools/SeedLocalRepository.java

Tạo JAR và Maven POM bằng Java 17 standard library, không tải code từ bên ngoài:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.jar.JarEntry;
import java.util.jar.JarOutputStream;

import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class SeedLocalRepository {
    private SeedLocalRepository() {
    }

    public static void main(String[] args) throws Exception {
        Path temp = Files.createTempDirectory("gradle-layers-");
        Path javaFile = temp.resolve(
                "src/edu/example/diagnostic/Greeter.java"
        );
        Path classes = temp.resolve("classes");
        Files.createDirectories(javaFile.getParent());
        Files.createDirectories(classes);

        String source = """
                package edu.example.diagnostic;

                public final class Greeter {
                    private Greeter() {
                    }

                    public static String source() {
                        return "local-maven";
                    }
                }
                """;

        Files.writeString(
                javaFile, source, StandardCharsets.UTF_8
        );

        JavaCompiler compiler =
                ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "Need a JDK with JavaCompiler"
            );
        }

        int result = compiler.run(
                null, null, null,
                "--release", "17",
                "-encoding", "UTF-8",
                "-d", classes.toString(),
                javaFile.toString()
        );
        if (result != 0) {
            throw new IllegalStateException(
                    "javac exit code " + result
            );
        }

        Path module = Path.of(
                "repos/training/edu/example/diagnostic/"
                    + "greeter/1.0.0"
        );
        Files.createDirectories(module);

        Path jar = module.resolve("greeter-1.0.0.jar");
        Path bytecode = classes.resolve(
                "edu/example/diagnostic/Greeter.class"
        );

        try (JarOutputStream output =
                new JarOutputStream(Files.newOutputStream(jar))) {
            JarEntry entry = new JarEntry(
                    "edu/example/diagnostic/Greeter.class"
            );
            entry.setTime(0L);
            output.putNextEntry(entry);
            Files.copy(bytecode, output);
            output.closeEntry();
        }

        String pom = """
                <?xml version="1.0" encoding="UTF-8"?>
                <project xmlns="http://maven.apache.org/POM/4.0.0">
                  <modelVersion>4.0.0</modelVersion>
                  <groupId>edu.example.diagnostic</groupId>
                  <artifactId>greeter</artifactId>
                  <version>1.0.0</version>
                  <packaging>jar</packaging>
                </project>
                """;

        Files.writeString(
                module.resolve("greeter-1.0.0.pom"),
                pom,
                StandardCharsets.UTF_8
        );

        System.out.println("seed=OK");
    }
}
~~~

**Kiểm tra code:** 
- JavaCompiler từ **ToolProvider** cần full JDK, không phải JRE thiếu javac.
- --release 17 giữ compiled API/bytecode mục tiêu.
- POM path đúng Maven layout group/artifact/version.
- JarOutputStream tạo đúng entry Greeter.class.
- Class Greeter.source() chỉ trả String constant, hoàn toàn vô hại.
- Seeder in đúng một dòng **seed=OK** sau khi hoàn thành.

### 11.8. Biên dịch Seeder trên Linux/macOS

~~~bash
mkdir -p tools/classes
javac --release 17 -encoding UTF-8 \
  -d tools/classes tools/SeedLocalRepository.java

java -cp tools/classes SeedLocalRepository
~~~

**Stdout chính xác:**

~~~text
seed=OK
~~~

### 11.9. Biên dịch Seeder trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force tools\classes | Out-Null
javac --release 17 -encoding UTF-8 -d tools\classes tools\SeedLocalRepository.java
java -cp tools\classes SeedLocalRepository
~~~

**Stdout:**

~~~text
seed=OK
~~~

### 11.10. Xác minh JAR/POM

Linux/macOS:

~~~bash
jar --list --file \
  repos/training/edu/example/diagnostic/greeter/1.0.0/greeter-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
jar --list --file repos\training\edu\example\diagnostic\greeter\1.0.0\greeter-1.0.0.jar
~~~

Entry cần có:

~~~text
edu/example/diagnostic/Greeter.class
~~~

Nếu chưa có, kiểm Seeder stdout/exit code/JDK rồi mới chuyển sang Gradle repository resolution.

### 11.11. Chạy lần lượt báo cáo Gradle

~~~bash
./gradlew --version
./gradlew help --console=plain
./gradlew projects --console=plain
./gradlew :app:tasks --all --console=plain

./gradlew :app:dependencies \
  --configuration compileClasspath --console=plain

./gradlew :app:dependencies \
  --configuration runtimeClasspath --console=plain

./gradlew :app:dependencyInsight \
  --dependency greeter \
  --configuration runtimeClasspath --console=plain

./gradlew -q javaToolchains
./gradlew :app:run --quiet
./gradlew :app:smokeCheck --quiet
./gradlew :app:check --console=plain
~~~

**Stdout của riêng app/Main.main khi chạy :app:run --quiet:**

~~~text
status=READY
source=local-maven
~~~

**Stdout của riêng AppCheck.main khi chạy :app:smokeCheck --quiet:**

~~~text
check=PASS
~~~

Gradle :app:check có thể in thêm task outcomes, BUILD SUCCESSFUL và console logs; không nhập các dòng ấy vào stdout Java.

### 11.12. Windows PowerShell

~~~powershell
.\gradlew.bat --version
.\gradlew.bat help --console=plain
.\gradlew.bat projects --console=plain
.\gradlew.bat :app:tasks --all --console=plain
.\gradlew.bat :app:dependencies --configuration runtimeClasspath
.\gradlew.bat :app:dependencyInsight --dependency greeter --configuration runtimeClasspath
.\gradlew.bat -q javaToolchains
.\gradlew.bat :app:run --quiet
.\gradlew.bat :app:smokeCheck --quiet
~~~

PowerShell dùng Wrapper batch **.\gradlew.bat**; không tự gọi ./gradlew shell script nếu không có Bash/WSL.

## 12. Đối chiếu bằng javac/java độc lập

Sau Seeder, có thể chứng minh Java source và JAR chạy được **ngoài Gradle**. Phép thử này hữu ích khi Gradle compile fail nhưng không chắc lỗi có thuộc repository/toolchain hay không.

### 12.1. Linux/macOS

~~~bash
mkdir -p build/manual

javac --release 17 \
  -cp repos/training/edu/example/diagnostic/greeter/1.0.0/greeter-1.0.0.jar \
  -d build/manual \
  app/src/main/java/demo/app/Main.java

java -cp "build/manual:repos/training/edu/example/diagnostic/greeter/1.0.0/greeter-1.0.0.jar" \
  demo.app.Main
~~~

**Stdout:**

~~~text
status=READY
source=local-maven
~~~

### 12.2. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build\manual | Out-Null
javac --release 17 -cp repos\training\edu\example\diagnostic\greeter\1.0.0\greeter-1.0.0.jar -d build\manual app\src\main\java\demo\app\Main.java
java -cp "build\manual;repos\training\edu\example\diagnostic\greeter\1.0.0\greeter-1.0.0.jar" demo.app.Main
~~~

Windows classpath ngăn bằng **;**, Linux/macOS bằng **:**. Biên dịch thủ công không thay được Gradle task graph/repository policy tests, nhưng giúp cô lập một lớp lỗi.

## 13. Các phép thử lỗi có kiểm soát

**Chỉ sửa một điều mỗi lượt, trong bản sao lab.** Sau khi thấy lỗi, hoàn nguyên rồi chạy :app:run và :app:smokeCheck. Mỗi tình huống giải thích lớp lỗi, lệnh điều tra và phương án xử lý; không yêu cầu mở external service không tin cậy.

### 13.1. Lỗi plugin ID: plugin resolution

Trong app/build.gradle, tạm đổi:

~~~groovy
plugins {
    id 'application'
    id 'edu.example.plugin-does-not-exist' version '0.0.1'
}
~~~

Chạy:

~~~bash
./gradlew help --stacktrace --console=plain
~~~

**Kỳ vọng:** Gradle báo không thể resolve plugin ID/version/marker. Nếu Plugin Portal có mạng, Gradle có thể thực hiện lookup; đây không phải phần baseline offline.

**Giải pháp:** Kiểm plugin ID/version và pluginManagement.repositories/includeBuild. **Không** thêm mavenCentral vào application project repositories để chữa plugin DSL.

### 13.2. Lỗi repository injection bị cấm

Trong app/build.gradle, tạm thêm:

~~~groovy
repositories {
    mavenCentral()
}
~~~

Chạy:

~~~bash
./gradlew help --stacktrace --console=plain
~~~

**Kỳ vọng:** Configuration fail do **FAIL_ON_PROJECT_REPOS**. Đây là policy hoạt động đúng.

**Giải pháp:** Bỏ project repositories và khai approved source trong settings nếu thật sự cần. Không bỏ enforcement không review.

### 13.3. Sai dependency version

Tạm sửa:

~~~groovy
dependencies {
    implementation 'edu.example.diagnostic:greeter:9.9.9'
}
~~~

Chạy:

~~~bash
./gradlew :app:compileJava --stacktrace --info
~~~

**Kỳ vọng:** Local repo chỉ có version 1.0.0, nên version 9.9.9 không resolve được. Plugin application đã chạy; lỗi nằm ở **GAV/artifact resolution**, không phải Java toolchain.

### 13.4. Sai repository directory

Tạm đổi settings repository URL:

~~~groovy
maven {
    name = 'TrainingLocal'
    url = uri(new File(settingsDir, 'repos/not-existing'))
    content {
        includeGroup('edu.example.diagnostic')
    }
}
~~~

Chạy một build trong Gradle User Home tạm và repository clean để tránh cached origin cũ. Khi không có artifact, resolution phải fail. **Không** thử “chữa” bằng cách thêm public repository chứa internal GAV.

### 13.5. Yêu cầu toolchain không có

Trong app/build.gradle:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(99)
    }
}
~~~

**99 là giá trị cố ý sai để tạo lỗi**, không phải Java version được đề xuất. Chạy:

~~~bash
./gradlew -q javaToolchains
./gradlew :app:compileJava --stacktrace --info
~~~

Nếu không có JDK 99 và resolver không provision được, Gradle báo thiếu toolchain. Trả version về 17, bảo đảm JDK 17 có sẵn.

**Không** đổi dependency version để sửa.

### 13.6. Lỗi Java API compile

Tạm sửa Main.report():

~~~java
return "status=READY\nsource=" + Greeter.unknownMethod();
~~~

Chạy:

~~~bash
./gradlew :app:compileJava --stacktrace
~~~

**Kỳ vọng:** Javac error: cannot find symbol method unknownMethod(). Đây là lỗi **source/API** khi JAR có mặt, không phải plugin marker hay TLS.

Khôi phục **Greeter.source()**.

### 13.7. Lỗi task :app:run không tồn tại

Tạm thay plugin application bằng java:

~~~groovy
plugins {
    id 'java'
}
~~~

Chạy:

~~~bash
./gradlew :app:run --stacktrace
~~~

Java plugin không tạo Application **run** task, nên lỗi là **task model/plugin selection**. Không cần thay JVM hoặc repositories.

### 13.8. Lỗi Wrapper không tìm java

Trong một shell thử riêng, nếu JAVA_HOME chỉ tới đường dẫn giả và không có Java executable, Wrapper script có thể fail **trước settings**. Không sửa system-wide JAVA_HOME để thử trên máy chính; chỉ làm trong môi trường disposable.

Sau khi khôi phục JAVA_HOME, chạy java -version, javac -version và ./gradlew --version. Nếu ba bước PASS, tiếp tục từ settings.

### 13.9. Lỗi runtime dù compile PASS

Mô phỏng ở mức kiến thức: nếu compileClasspath có Greeter.source() nhưng runtimeClasspath dùng một JAR khác không còn method ấy, JavaExec có thể báo **NoSuchMethodError**. Nếu thiếu class hoàn toàn có thể báo **NoClassDefFoundError**.

Bài lab baseline không cố ý thay JAR runtime để tránh giữ hai artifact cùng GAV trong cùng Gradle dependency cache. Với tình huống thật, so runtimeClasspath/compileClasspath và verification metadata, không sửa mọi thứ bằng **--refresh-dependencies**.

## 14. Dùng đúng các flags khi nghi cache hoặc môi trường

| Flag | Làm gì | Không làm gì |
|---|---|---|
| **--refresh-dependencies** | Refresh resolution metadata/artifact checks | Không chữa plugin ID sai hoặc Java source lỗi |
| **--offline** | Tránh remote network resolution | Không tạo missing cached artifact |
| **--rerun-tasks** | Buộc tasks chạy lại khi có thể | Không tự thay selected dependency GAV |
| **--no-build-cache** | Không dùng task output build cache | Không tắt UP-TO-DATE checks |
| **--no-configuration-cache** | Không reuse configuration state | Không thêm JDK toolchain |
| **--stop** | Dừng Gradle daemon | Không xoá remote repo caches |
| **--stacktrace** | Hiện exception chains | Không tự sửa source |
| **--info** | Log thêm task/resolution context | Không nên chia sẻ nguyên văn nếu có secrets |
| **--warning-mode all** | Hiện warnings/deprecations | Không tự cập nhật plugins |
| **--dry-run** | Liệt kê task graph | Không thực thi Java Main.main |

Nếu task UP-TO-DATE và bạn muốn chứng minh task action thật chạy, dùng --rerun-tasks có chủ đích. Nếu remote artifact có version sai do lockfile, sửa lock/dependency policy; --rerun-tasks không thay dependency graph.

### 14.1. Khi nào --refresh-dependencies hữu ích?

- Changing/SNAPSHOT artifact được cập nhật.
- Module metadata vừa được publish.
- Một repository/proxy trước đó trả metadata lỗi.
- Cần điều tra local cache có stale/incorrect origin.

**Không tự động xóa ~/.gradle**. Dependency cache có metadata origin; cần giữ bằng chứng khi điều tra một artifact từ nguồn không tin cậy.

### 14.2. Khi nào --no-configuration-cache hữu ích?

Nếu task action bị lỗi Configuration Cache requirements hoặc plugin chứa unsupported state, tắt cache tạm thời giúp so sánh. Nhưng đó là diagnostic workaround; fix bền là sửa plugin/task model, không giữ Project references trong task actions và dùng managed task inputs/outputs khi phù hợp.

### 14.3. Khi nào --stop hữu ích?

Khi đổi Daemon JVM criteria/JVM args hoặc daemon bị treo, dừng daemon có thể giúp dùng cấu hình mới. Không xem --stop là cách xử lý mọi ModuleNotFoundException.

## 15. Kiểm tra plugin failures theo thứ tự

1. Plugin ID là **core** hay **external**?
2. Nếu external, version có được publish không?
3. Plugin request nằm trong plugins DSL hay legacy buildscript.classpath?
4. **pluginManagement.repositories** có approved source?
5. Plugin marker có đúng GAV không?
6. Marker POM dẫn tới implementation artifact nào?
7. Implementation JAR/transitives có available và permissions phù hợp?
8. Plugin local có includeBuild('build-logic') đúng path không?
9. Plugin áp cho đúng project role không?
10. Plugin có yêu cầu một plugin khác được apply trước không?
11. Gradle Wrapper version có tương thích plugin API không?
12. Lỗi thực sự xảy ra ở marker resolution hay Plugin.apply?
13. Có project repository injection bị settings block không?
14. IDE dùng cùng Gradle Wrapper và Gradle JVM?
15. Có thể tái hiện bằng ./gradlew help --stacktrace không?

**Mẫu sai:** afterEvaluate { ... } được thêm để chữa plugin not found. Plugin marker phải resolve **trước** khi callback được đăng ký; afterEvaluate không giải quyết nguồn plugin.

## 16. Kiểm tra dependency failures theo thứ tự

1. Đây là external GAV hay project(':module') dependency?
2. Project/configuration có tồn tại và resolvable không?
3. Đang lỗi compileClasspath, runtimeClasspath hay annotationProcessor?
4. GAV group/artifact/version có đúng không?
5. POM/Gradle Module Metadata/JAR có trong repository?
6. Repository URL/TLS/credentials/ACL đúng?
7. Content include/exclude rules có cho namespace?
8. Dynamic version/constraints/platform BOM hoặc locking làm chọn version khác?
9. Có duplicate modules/capabilities/variants?
10. Java target compatibility attrs có hợp lệ?
11. Có API/implementation separation làm consumer thiếu type?
12. compileOnly được dùng nhầm cho library cần runtime?
13. Annotation processors được khai đúng configuration?
14. Maven Local hoặc cache source origin cũ làm chọn sai artifact?
15. Dependency verification checksum/signature có mismatch?
16. Đã chạy dependencyInsight trên đúng configuration?
17. Có negative test nếu trusted private module missing phải fail closed?
18. Có test clean CI workspace để tránh cache che lỗi?

**Nhớ:** dependencyInsight giải thích **vì sao chọn version**, không tự chứng minh **ai publish JAR** hoặc bytes đã được xác nhận. Khi nghi supply-chain tampering, dùng dependency verification/provenance và incident response.

## 17. Kiểm tra toolchain failures theo thứ tự

1. ./gradlew --version có JVM được Gradle version hỗ trợ?
2. java -version và javac -version có chạy?
3. ./gradlew -q javaToolchains liệt kê JDK nào?
4. Java toolchain spec đang yêu cầu version nào?
5. Vendor/implementation filters có quá chặt?
6. JDK cài dưới path nào, Gradle có scan path ấy?
7. Toolchain download resolver đã được cấu hình nếu cần?
8. CI có cho phép internet/provision toolchain?
9. IDE Gradle JVM có khác Daemon JVM trong terminal?
10. org.gradle.java.home/daemon criteria có override?
11. JavaCompile.javaCompiler và JavaExec.javaLauncher có bị plugin override?
12. Bytecode major version có vượt runtime target?
13. options.release có tương thích với target APIs?
14. Error là toolchain missing hay javac cannot find symbol?
15. Có service process khác dùng JDK phiên bản cũ trên CI?

**Đừng coi một JDK duy nhất là lời giải cho mọi lớp.** JVM chạy Gradle và Java compiler có thể khác có chủ đích.

## 18. Troubleshooting 24 tình huống thực tế

### 1 — ./gradlew Permission denied

**Lớp:** Shell/Wrapper. Kiểm executable mode, dùng chmod +x trên Unix. Không thay POM.

### 2 — GradleWrapperMain not found

**Lớp:** Wrapper files. Khôi phục gradle-wrapper.jar tin cậy, kiểm integrity/commit.

### 3 — Gradle runtime không hỗ trợ Java version

**Lớp:** Daemon/client JVM. So compatibility matrix và Wrapper version; đổi JVM chạy Gradle đúng policy.

### 4 — External plugin not found

**Lớp:** Plugin marker. Kiểm plugin ID/version, pluginManagement repositories và marker publication.

### 5 — Plugin marker tồn tại nhưng implementation không tải

**Lớp:** Plugin implementation dependency. Kiểm implementation GAV/transitives, repositories và permissions.

### 6 — Plugin apply lỗi extension

**Lớp:** Plugin configuration. Đọc Caused by, Gradle API version, plugin ordering và typed extension.

### 7 — Project repo injection bị chặn

**Lớp:** Settings repository policy. Chuyển repo approved vào settings, không disable enforcement vô điều kiện.

### 8 — GAV missing

**Lớp:** Artifact resolution. Kiểm group/name/version/POM/JAR và approved repo.

### 9 — Private Maven 401/403

**Lớp:** Auth/ACL. Kiểm CI secrets/rights, không public fallback.

### 10 — PKIX path building failed

**Lớp:** TLS/CA. Sửa certificate/proxy trust chain; không tắt TLS verification.

### 11 — Maven module available nhưng --offline fail

**Lớp:** Local cache; offline không tải remote missing artifact. Cho phép online đúng policy khi cần.

### 12 — dependencyInsight không hiện expected module

**Lớp:** Sai configuration/project/module request. Đọc dependencies tree/selected configuration.

### 13 — Version chọn cao hơn requested

**Lớp:** Dependency conflict/constraints/platform. Dùng dependencyInsight; không tự force một version.

### 14 — No matching variant

**Lớp:** Attribute matching. Đọc consumer attributes và producer outgoingVariants.

### 15 — javac cannot find symbol

**Lớp:** Source/API/compileClasspath. Kiểm import/method/generation/JAR API.

### 16 — No matching Java installation

**Lớp:** Toolchain resolver. Kiểm javaToolchains, version/vendor/provisioning.

### 17 — UnsupportedClassVersionError

**Lớp:** Bytecode/runtime JVM. Chọn JavaLauncher đúng hoặc compile target compatible.

### 18 — NoClassDefFoundError

**Lớp:** Runtime classpath. Kiểm runtimeOnly/compileOnly/selected JAR.

### 19 — NoSuchMethodError

**Lớp:** Runtime binary API mismatch. So compileClasspath và runtimeClasspath/locks.

### 20 — IDE đỏ, ./gradlew compileJava PASS

**Lớp:** IDE sync/SDK/index. Chọn Wrapper/JVM đúng, reload Gradle, kiểm source roots.

### 21 — IDE Run PASS, :app:check FAIL

**Lớp:** Different launcher/classpath/workdir/test runner. So runtime env và tests.

### 22 — Daemon JVM không như JAVA_HOME

**Lớp:** org.gradle.java.home, Daemon criteria hoặc IDE Tooling API. Đọc precedence.

### 23 — Configuration Cache báo task action đọc Project

**Lớp:** Custom task design. Dùng managed @Input/@Output properties và Provider wiring; không chỉ tắt cache vĩnh viễn.

### 24 — --refresh-dependencies không sửa plugin ID sai

**Lớp:** Sai diagnostic flag. Sửa plugin marker/source đúng; refresh dependencies không tạo plugin chưa publish.

## 19. Runbook cho incident trên CI

Một CI failure report đủ giúp tái hiện nên ghi:

- **Git commit SHA** và branch/PR reference.
- **Command** và **task path**.
- **Gradle Wrapper version**.
- **Gradle runtime JVM** và **toolchain version/vendor**.
- OS/architecture/CI runner class.
- Layer phân loại và **root Caused by**.
- Exact requested plugin ID hoặc GAV (nếu permitted).
- Configuration: compileClasspath, runtimeClasspath, testRuntimeClasspath, pluginManagement, ...
- Repository category/host approved đã được redact theo policy.
- So sánh **local/IDE vs CI**.
- Commands diagnostics đã thử, kết quả từng command.
- Cache state/flags ảnh hưởng sự tái hiện.
- Test reports/task outcomes.
- Fix đã áp và command re-run PASS.

Không gửi credentials, authenticated URLs, access tokens hay logs chưa redact lên public issue/Build Scan. Một lỗi checksum/signature mismatch hoặc nghi dependency confusion có thể là **supply-chain incident**: dừng và xác minh nguồn độc lập, không tự update hash theo artifact nghi vấn.

### 19.1. Tái hiện có thứ tự

~~~bash
./gradlew --version
./gradlew help --stacktrace --console=plain
./gradlew projects --console=plain
./gradlew :app:dependencies \
  --configuration runtimeClasspath --console=plain
./gradlew -q javaToolchains
./gradlew :app:compileJava --stacktrace --console=plain
./gradlew :app:run --stacktrace --console=plain
~~~

Không chạy hàng loạt commands không liên quan nếu bước đầu đã fail rõ; chỉ chuyển sang lớp sau khi lớp trước đã đủ tin cậy.

### 19.2. CI gates theo layer

| Gate | Khi cần |
|---|---|
| Wrapper URL/integrity verification | Mọi CI |
| Gradle/JDK version check | CI image updates |
| ./gradlew help | Settings/plugins sanity |
| ./gradlew projects | Multi-module include validation |
| Plugin source/marker verification | Thay pluginManagement/build-logic |
| Dependency verification/locking | Thay repo/versions |
| javaToolchains inventory | Thay JDK/toolchain resolver |
| compileJava + tests | PR theo impact policy |
| Runtime smoke/integration | Main/release |
| IDE sync validation nếu có automation | IDE/plugin integration changes |

## 20. Checklist trước khi chốt chẩn đoán

1. Đã ghi command và lỗi đầu tiên?
2. Đã phân biệt Wrapper/JVM/plugin/repository/dependency/toolchain/source/IDE?
3. Gradle Wrapper được pin và chạy được?
4. Client/Daemon JVM có version tương thích?
5. settings.gradle include đúng projects?
6. Plugin ID/version/marker/source đúng?
7. Plugin apply thành công, không thiếu extension?
8. Repository policy ở đúng resolution scope?
9. Project repository injection có được xử lý đúng?
10. Private repository TLS/credentials/ACL đúng?
11. GAV/POM/JAR/metadata có đúng approved source?
12. compileClasspath và runtimeClasspath được kiểm riêng?
13. Version conflicts/constraints/locking được giải thích?
14. Consumer/producer variants tương thích?
15. javaToolchains hiển thị JDK/toolchain cần thiết?
16. Compiler error đúng source/API, không bị nhầm toolchain?
17. Runtime class file/API version tương thích?
18. IDE import dùng Wrapper và Gradle JVM đúng?
19. Cache flags được dùng đúng ý nghĩa?
20. Không xóa caches hoặc disable security không cần thiết?
21. Đã rerun đúng command fail ban đầu?
22. Smoke/tests thật sự được thực thi và PASS?
23. Logs có redact private/secrets?
24. Có ghi runbook/fix ngắn cho đội?

## 21. Bài tập và đáp án

**Bài 1.** Vì sao ./gradlew --version fail thì chưa nên chạy dependencyInsight?  
**Đáp:** Gradle chưa bootstrap/runtime thành công nên report dependencies không thể chạy đáng tin.

**Bài 2.** Thêm mavenCentral vào app.repositories có tự sửa Plugin not found của plugins DSL?  
**Đáp:** Không; kiểm pluginManagement.repositories, marker và version.

**Bài 3.** application plugin cần tải marker từ Plugin Portal không?  
**Đáp:** Không, đây là core Gradle plugin.

**Bài 4.** Marker GAV cho com.example.quality version 1.2.0?  
**Đáp:** com.example.quality:com.example.quality.gradle.plugin:1.2.0.

**Bài 5.** Plugin marker có nhưng Plugin.apply fail, đó vẫn là marker-resolution error?  
**Đáp:** Không; xem plugin implementation/configuration stacktrace.

**Bài 6.** FAIL_ON_PROJECT_REPOS làm gì?  
**Đáp:** Cấm project/plugin thêm repository trong project dependency scope, không thay pluginManagement policy.

**Bài 7.** Thiếu GAV trong local Maven lab thì kiểm gì?  
**Đáp:** Seeder, POM/JAR path, group/artifact/version, settings repositories/filter.

**Bài 8.** --refresh-dependencies và --rerun-tasks có cùng tác dụng?  
**Đáp:** Không; cái đầu refresh dependency resolution, cái sau ép task execution.

**Bài 9.** --no-build-cache có tắt UP-TO-DATE?  
**Đáp:** Không; UP-TO-DATE checks độc lập Build Cache.

**Bài 10.** --version và javaToolchains trả lời cùng câu hỏi?  
**Đáp:** Không; một cái runtime Gradle, cái kia inventory JDK toolchains.

**Bài 11.** Daemon chạy Java 21, toolchain 17 có chắc sai?  
**Đáp:** Không; có thể là cấu hình được chủ ý.

**Bài 12.** Có JAVA_HOME=17 thì compiler cho task chắc chắn Java 17?  
**Đáp:** Không; toolchain spec/Gradle Daemon/IDE/plugin có thể khác.

**Bài 13.** cannot find symbol có nhất thiết thiếu JDK?  
**Đáp:** Không; source/API/compileClasspath thường là nơi cần điều tra.

**Bài 14.** Variant mismatch nên fix bằng force version bất kỳ?  
**Đáp:** Không; xem attributes/producer variants.

**Bài 15.** Compile PASS, run NoClassDefFoundError thì xem gì?  
**Đáp:** runtimeClasspath và packaging/runtime dependencies.

**Bài 16.** Artifact greeter:1.0.0 trong lab từ đâu?  
**Đáp:** Local Maven repository repos/training do SeedLocalRepository tạo.

**Bài 17.** Chưa chạy Seeder, app:run có thể fail ở lớp nào?  
**Đáp:** Dependency/artifact resolution, vì local repo chưa có POM/JAR.

**Bài 18.** Đổi greeter version thành 9.9.9 làm hỏng core application plugin?  
**Đáp:** Không; GAV không resolve ở repo chứa 1.0.0.

**Bài 19.** app thêm repositories với FAIL_ON_PROJECT_REPOS?  
**Đáp:** Configuration fail theo repository policy.

**Bài 20.** Chỉ apply java plugin thì :app:run có tự có?  
**Đáp:** Không; application plugin mới tạo task run.

**Bài 21.** Java 17 runtime chạy class major version 65 được không?  
**Đáp:** Không, 65 là Java 21 bytecode.

**Bài 22.** IDE Run PASS thay Gradle test PASS được không?  
**Đáp:** Không; classpath/JVM/test runner có thể khác.

**Bài 23.** IDE sync fail CLI PASS, so ba thứ nào đầu tiên?  
**Đáp:** Wrapper distribution, IDE Gradle JVM, IDE sync error/root project model.

**Bài 24.** Vì sao không xoá ~/.gradle ngay?  
**Đáp:** Có thể mất evidence, tốn download và không sửa source/API/policy thật.

**Bài 25.** --offline PASS chứng minh remote repository TLS hiện đúng?  
**Đáp:** Không; build có thể dùng cached/local artifact.

**Bài 26.** dependencyInsight chứng minh artifact checksum và provenance?  
**Đáp:** Không; cần dependency verification/source audit riêng.

**Bài 27.** Internal repo 401 nên thêm public fallback?  
**Đáp:** Không; sửa credentials/ACL của trusted source.

**Bài 28.** Khi checksum mismatch, không nên làm gì?  
**Đáp:** Không tự update verification metadata từ artifact nghi vấn hoặc tắt verification.

**Bài 29.** --dry-run :app:run có thực thi Main.main?  
**Đáp:** Không; chỉ xem graph.

**Bài 30.** Một ticket tốt cho CI fail khác local cần gì?  
**Đáp:** Commit, command, Gradle/JDK/toolchain, selected configuration/GAV, logs đã redact, failing task và reproduction steps.

## 22. Tài liệu tham khảo chính thức

- [Gradle User Manual — Troubleshooting Builds](https://docs.gradle.org/current/userguide/troubleshooting.html): phân loại failure, stacktraces, Build Scans và environment.
- [Gradle User Manual — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): help/projects/tasks/dependencies/dependencyInsight/buildEnvironment.
- [Gradle User Manual — Gradle Command Line](https://docs.gradle.org/current/userguide/gradle_command_line.html): flags, --refresh-dependencies, --offline, --dry-run, --info.
- [Gradle User Manual — Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): Wrapper files, distribution, integrity và version pins.
- [Gradle User Manual — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): supported Gradle runtime and Java versions.
- [Gradle User Manual — Gradle Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html): client/daemon JVM và criteria.
- [Gradle User Manual — Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): JavaCompiler/JavaLauncher, detection/provisioning, javaToolchains.
- [Gradle User Manual — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html): plugin marker artifacts, pluginManagement/includeBuild.
- [Gradle User Manual — Declaring Repositories](https://docs.gradle.org/current/userguide/declaring_repositories_adv.html): plugin vs project dependency scopes.
- [Gradle User Manual — Centralizing Repository Declarations](https://docs.gradle.org/current/userguide/centralizing_repositories.html): RepositoriesMode policy.
- [Gradle User Manual — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependencyInsight/constraints/selected versions.
- [Gradle User Manual — Variant-Aware Resolution](https://docs.gradle.org/current/userguide/variant_aware_resolution.html): consumer/producer attributes và variant matching.
- [Gradle User Manual — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): offline, cache origin và refresh.
- [Gradle User Manual — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): verification metadata và integrity.
- [Gradle User Manual — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration model reuse.
- [Gradle User Manual — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): api/implementation classpath.
- [Gradle User Manual — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): test source sets và Test tasks.
- [Gradle User Manual — Build Environment](https://docs.gradle.org/current/userguide/build_environment.html): Gradle properties, JAVA_HOME, environment precedence.

**Ghi nhớ:** Đi theo lớp **Wrapper/runtime JVM → settings/plugin marker → plugin implementation → repository policy → dependency/variant → toolchain → javac/runtime → IDE sync**. Một lệnh không thể trả lời mọi câu hỏi: --version cho biết JVM Gradle, dependencyInsight giải thích selected module, javaToolchains kiểm inventory JDK, compileJava kiểm API/source và :app:run kiểm runtime. Đừng vô hiệu TLS/verification, không thêm repository public tùy tiện hoặc xoá cache toàn máy; hãy sửa nguyên nhân ở đúng lớp và kiểm lại command thất bại cùng bài test hành vi.