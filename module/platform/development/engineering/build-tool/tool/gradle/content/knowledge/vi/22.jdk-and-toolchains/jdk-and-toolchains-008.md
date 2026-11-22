# Chẩn đoán unsupported class version và tổ hợp Gradle, JDK không tương thích

## 1. Vấn đề: build Java thất bại dù mã nguồn không đổi

Một dự án dùng Gradle và Java có thể chạy tốt trên laptop của một người, nhưng lỗi ngay khi CI hoặc IDE đổi JDK. Thông điệp thường thấy:

~~~text
java.lang.UnsupportedClassVersionError:
... has been compiled by a more recent version of the Java Runtime
(class file version 65.0), this version of the Java Runtime
only recognizes class file versions up to 61.0
~~~

Hoặc lỗi khác, nhìn giống nhưng xảy ra **trước khi Java application chạy**:

~~~text
Unsupported class file major version 65
~~~

Hai thông điệp **không nhất thiết cùng nguyên nhân**. Trường hợp đầu thường là **JVM đang nạp một class file được biên dịch cho Java mới hơn JVM hiện có**. Trường hợp thứ hai có thể đến từ **Gradle/Groovy/ASM/Kotlin DSL hoặc một plugin đọc class file** trong lúc cấu hình build, ngay cả khi ứng dụng Java chưa được chạy.

Bài học này nằm trong nhóm **JDK và toolchain** của Gradle. Mục tiêu là chẩn đoán **đúng tầng** và sửa **đúng tổ hợp phiên bản**, thay vì thay đổi ngẫu nhiên `JAVA_HOME`, `sourceCompatibility` hoặc xóa Gradle cache.

Sau bài học, bạn sẽ có thể:

- Đọc class-file major/minor version và chuyển sang Java version tương ứng.
- Phân biệt **JVM chạy Gradle**, **JDK toolchain biên dịch**, **JVM chạy test/JavaExec**, **JVM dùng chạy artifact bên ngoài Gradle**, và **JDK của IDE/CI**.
- Tra compatibility matrix của **đúng Gradle Wrapper version**, nhất là khi dùng Java 17/21/25/26.
- Phân biệt `UnsupportedClassVersionError`, `Unsupported class file major version`, `No matching variant`, `invalid source release`, `release version not supported` và `No matching toolchains found`.
- Dùng `./gradlew --version`, `java -version`, `javac -version`, `javaToolchains`, `javap -verbose`, `--stacktrace` và `--info` để khoanh vùng.
- Cấu hình Java toolchain, `options.release`, Java launcher cho tasks, Gradle daemon JVM và IntelliJ/CI đúng.
- Chạy một project Gradle Kotlin DSL **Java 17** tự đầy đủ, in class-file major version thật của chính nó.
- Tạo một lỗi tương thích có chủ đích với JDK 21 compiler + Java 17 runtime, rồi sửa bằng `--release 17` hoặc đổi đúng runtime.
- Viết checklist cho team để ngăn lỗi tái phát khi đổi máy, nâng Gradle, JDK hoặc plugin.

**Ý tưởng xuyên suốt:** “Dự án sử dụng Java 17” có thể nói tới **source syntax**, **bytecode target**, **toolchain compiler**, **runtime ứng dụng**, hoặc **JVM chạy Gradle**. Phải chỉ rõ đang nói đến tầng nào.

## 2. Đọc đúng “class file version 65.0”

### 2.1. Java source khác Java class file

`.java` là mã nguồn Java. `javac` biên dịch nó thành `.class` có định dạng nhị phân của JVM. Mỗi class file mang:

1. Magic header `0xCAFEBABE`.
2. `minor_version`.
3. `major_version`.
4. Constant pool và các cấu trúc mô tả class, methods, fields, attributes.

Một JVM chỉ nạp những class files có version được nó hỗ trợ. Java 17 thường tạo **major 61**; Java 21 thường tạo **major 65**. Nếu dùng **Java 17 runtime** để nạp class **major 65**, JVM không biết định dạng mới và ném `UnsupportedClassVersionError`.

### 2.2. Bảng tra class-file major version

| Java release | Major version của class file thông thường |
| --- | ---: |
| Java 8 | 52 |
| Java 9 | 53 |
| Java 10 | 54 |
| Java 11 | 55 |
| Java 12 | 56 |
| Java 13 | 57 |
| Java 14 | 58 |
| Java 15 | 59 |
| Java 16 | 60 |
| **Java 17** | **61** |
| Java 18 | 62 |
| Java 19 | 63 |
| Java 20 | 64 |
| **Java 21** | **65** |
| Java 22 | 66 |
| Java 23 | 67 |
| Java 24 | 68 |
| Java 25 | 69 |
| Java 26 | 70 |
| Java 27 | 71 |

Từ Java 5 trở đi trong bảng này, có thể nhận diện nhanh bằng quy tắc `major = Java release + 44`. Đây là **mẹo giải mã**, không phải cách để “hạ version” bằng tay.

Nguồn gốc định dạng: [JVM Specification — Chapter 4, The class File Format](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html). Với release mới hơn, hãy tra bản JVM specification phù hợp thay vì đoán.

### 2.3. Đọc câu thông báo lỗi

Ví dụ:

~~~text
class file version 65.0
runtime only recognizes class file versions up to 61.0
~~~

Diễn giải:

- **65.0**: class thực tế đang được tải được biên dịch thành định dạng Java 21 thông thường.
- **61.0**: JVM hiện tại chỉ hỗ trợ class files tối đa tới Java 17.
- Root cause: **runtime thấp hơn bytecode target** của class đang được tải.
- Hướng sửa: **dùng Java 21+ runtime tương thích** nếu môi trường cho phép, **hoặc build lại class với target Java 17** và chỉ dùng APIs sẵn có trên Java 17. Nếu class đến từ dependency ngoài, cần version dependency hỗ trợ Java 17 thay vì cố chỉnh main source.

Đừng chỉ thấy “65” rồi sửa ngẫu nhiên `gradle-wrapper.properties`: JVM có thể đang chạy **application**, không phải Gradle.

### 2.4. Minor version và preview feature

Thông thường class file có `minor_version=0`. Với preview features trong nhiều Java releases, compiler có thể tạo minor `65535`. Một class Java 17 preview có thể được nạp bởi Java 17 **khi được bật preview phù hợp**, nhưng không đơn giản được chấp nhận bởi Java 21 chỉ vì 21 mới hơn.

Vì vậy thông báo lỗi liên quan preview cần được phân loại riêng. `--enable-preview` không phải “thuốc” chung cho class major 65 chạy trên Java 17: **Java 17 không hỗ trợ định dạng class của Java 21**.

## 3. Năm JVM/JDK có thể cùng xuất hiện trong một build

Bảng dưới đây ngăn nhầm lẫn giữa **tầng chạy** và **tầng sản xuất bytecode**.

| Tầng | Nó làm gì? | Ví dụ kiểm tra / điều khiển |
| --- | --- | --- |
| **Gradle JVM** | Chạy Gradle daemon, Groovy/Kotlin DSL, plugin code và nhiều build tasks | `./gradlew --version`, Gradle JVM của IDE, daemon criteria/`org.gradle.java.home` |
| **Java compiler toolchain** | `javac` biên dịch Java source thành `.class` | `java.toolchain`, `javaToolchains`, `JavaCompile.javaCompiler` |
| **Bytecode target** | Đặt class-file major và mức Java API được phép sử dụng | `JavaCompile.options.release` |
| **Task runtime JVM** | Chạy `Test`, `JavaExec`, `application:run`, tools thực thi | `javaLauncher`, task toolchain, test configuration |
| **Production/runtime JVM** | Chạy JAR/distribution/container sau khi Gradle đã xong | `java -version` trong container/server, Docker image/JRE |

**Cùng một máy có thể có nhiều JDK**. Ví dụ:

~~~text
Gradle 8.4 daemon: chạy bằng Java 17
Java toolchain compiler: JDK 21
javac target: Java 17 (thông qua --release 17)
Gradle Test launcher: Java 17
Production container: Java 17
~~~

Đây có thể là **một thiết kế hợp lệ**, nếu Gradle version/plugin hỗ trợ tổ hợp đó và source không dùng API vượt release 17. Cũng có thể build sai nếu bạn chạy Gradle 8.4 **trên** Java 21 — Gradle 8.4 đã hỗ trợ **toolchain Java 21** nhưng chỉ từ **Gradle 8.5** mới có hỗ trợ chính thức để **chạy Gradle trên Java 21**.

Điểm then chốt: đặt:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

**không chuyển JVM chạy Gradle daemon sang Java 17**. Nó chỉ mô tả toolchain dùng bởi các tasks JVM có hỗ trợ Java toolchains.

## 4. Bảng tương thích Gradle và Java: đọc hai cột khác nhau

Gradle công bố [Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html) với các cột **Support for toolchains** và **Support for running Gradle**. Hai cột có thể **khác số phiên bản tối thiểu**.

Những mốc có ích khi chẩn đoán:

| Java | Class major | Gradle đầu tiên hỗ trợ Java đó làm toolchain | Gradle đầu tiên hỗ trợ chạy Gradle trên JVM đó |
| --- | ---: | --- | --- |
| Java 17 | 61 | **7.3** | **7.3** |
| Java 18 | 62 | 7.5 | 7.5 |
| Java 19 | 63 | 7.6 | 7.6 |
| Java 20 | 64 | 8.1 | 8.3 |
| **Java 21** | **65** | **8.4** | **8.5** |
| Java 22 | 66 | 8.7 | 8.8 |
| Java 23 | 67 | 8.10 | 8.10 |
| Java 24 | 68 | 8.14 | 8.14 |
| Java 25 | 69 | 9.1.0 | 9.1.0 |
| Java 26 | 70 | 9.4.0 | 9.4.0 |
| Java 27 | 71 | 9.8.0 | 9.8.0 |

Bảng tóm tắt từ [Gradle 9.9 Compatibility Matrix](https://docs.gradle.org/9.9.0/userguide/compatibility.html). Đây là **mốc hỗ trợ chính thức đã được công bố**, không phải bảo đảm mọi plugin bên thứ ba đều tương thích, và không phải khẳng định “bản mới hơn sẽ hỗ trợ mọi JDK trong tương lai”.

### 4.1. Đặc biệt: Gradle 9 yêu cầu JDK tối thiểu 17 để chạy

Dòng Gradle 9.x yêu cầu **Java 17 trở lên để chạy chính Gradle**, trong giới hạn tối đa mà release đó đã hỗ trợ. Không thể dùng Java 8 hoặc Java 11 để chạy Gradle 9 chỉ vì project cần **target Java 8** hoặc Java 11.

Hướng đúng khi project vẫn phải tạo bytecode Java 8/11:

- Chạy Gradle 9 bằng một **Gradle JVM được hỗ trợ**, ví dụ Java 17.
- Dùng Java toolchain phù hợp với task biên dịch, hoặc compiler mới hơn kết hợp `options.release.set(8)`/`set(11)`.
- Test ứng dụng trên Java runtime mục tiêu.
- Kiểm tra phiên bản Gradle, plugin và Java compiler hỗ trợ cụ thể cho cross-compilation.

### 4.2. Phân biệt “minimum Gradle support” với “chọn bản phù hợp”

Ví dụ chọn **Gradle 7.3 + Java 17** có thể đáp ứng một phép kiểm tra cơ bản, nhưng một plugin hiện đại khác có thể yêu cầu Gradle 8/9. Ngược lại, build cũ có plugin chỉ tương thích Gradle 7 có thể hỏng khi nâng thẳng Gradle 9.

Do đó phải kiểm tra đồng thời:

1. **Gradle Wrapper version**.
2. **JVM chạy Gradle**.
3. **Java toolchain/bytecode target**.
4. **Plugin versions** (Android Gradle Plugin, Kotlin, Groovy, Spring Boot, bytecode processing plugins...).
5. **Runtime Java cuối** của ứng dụng.
6. **Metadata variants/JVM target** của dependencies.

Sửa tương thích không phải lúc nào cũng là “nâng mọi thứ lên latest”.

## 5. Nhận diện nhanh triệu chứng theo tầng

| Thông điệp / triệu chứng | Thường xảy ra ở đâu? | Điều cần kiểm tra đầu tiên |
| --- | --- | --- |
| `java.lang.UnsupportedClassVersionError`, class 65.0 vs runtime 61.0 | JVM **load** class | JDK runtime đang thực thi; class/JAR nào là thủ phạm |
| `Unsupported class file major version 65` trong `org.codehaus.groovy`, `groovyjarjarasm.asm` hoặc Gradle script compilation | Gradle/Groovy/ASM phân tích class | Gradle Wrapper + JVM chạy Gradle + plugin/build logic |
| `Could not open cp_settings generic class cache` cùng major version | Gradle configuration/script cache (thường lỗi phụ theo) | Root `--stacktrace`, class major, Gradle/JVM compatibility |
| `invalid source release: 21` | `javac` không hiểu yêu cầu source Java 21 | Compiler thật là JDK mấy? |
| `error: release version 21 not supported` | `javac --release 21` chạy bởi JDK quá cũ | `javac -version` hoặc selected toolchain |
| `No matching toolchains found for ... languageVersion=17` | Gradle không tìm được JDK 17 phù hợp | `javaToolchains`; detection/provisioning và vendor |
| `No matching variant of project :lib was found`, JVM target mismatch | Dependency **variant selection** | Producer JVM target, consumer requested JVM target |
| `NoSuchMethodError` hoặc `NoClassDefFoundError` | Runtime linking/classpath | Dependency versions, classpath, runtime; không nhất thiết Java major mismatch |
| `Unsupported Java. Your build is currently configured to use Java ... and Gradle ...` | IDE/Gradle integration | IDE Gradle JVM và Wrapper version |
| `java.lang.IllegalAccessError`, `InaccessibleObjectException` | Java module access / encapsulation | Plugin/library access to JDK internals, `--add-opens` chỉ khi có căn cứ |
| `Could not determine java version from ...` | Gradle rất cũ gặp Java mới | Gradle version hỗ trợ JVM đó hay chưa |

**Quy tắc chẩn đoán:** Ghi lại **exception class đầy đủ** và **5–15 dòng stacktrace quan trọng**, đừng chỉ tìm một chuỗi `unsupported`.

## 6. Checklist 10 phút trước khi chỉnh build script

Bắt đầu bằng các lệnh *không thay đổi build scripts*.

### 6.1. Gradle Wrapper và Gradle JVM

Trên macOS/Linux:

~~~bash
./gradlew --version
./gradlew --status
~~~

Windows:

~~~bat
gradlew.bat --version
gradlew.bat --status
~~~

Nếu project **không có Wrapper**, dùng `gradle --version` của bản cài sẵn để kiểm tra; không tưởng tượng `./gradlew` tồn tại.

Đọc output:

- `Gradle <version>`: **bản Gradle đang chạy**.
- `Launcher JVM` và `Daemon JVM` ở các Gradle mới (hoặc `JVM` ở bản cũ): JDK dùng để chạy Gradle.
- `Java home`/vendor/version nếu có: đường JDK tương ứng.
- Gradle daemon còn hoạt động không và daemon nào được reuse.

`--version` là cách kiểm tra nền, nhưng khi cần biết daemon thực sự đã chọn gì, kết hợp output `--info`, daemon criteria, IDE Gradle JVM settings và log task.

### 6.2. Java và javac trong shell

macOS/Linux:

~~~bash
java -version
javac -version
which java
which javac
echo "$JAVA_HOME"
~~~

PowerShell:

~~~powershell
java -version
javac -version
Get-Command java
Get-Command javac
$env:JAVA_HOME
where.exe java
where.exe javac
~~~

Windows Command Prompt:

~~~bat
java -version
javac -version
where java
where javac
echo %JAVA_HOME%
~~~

Các lệnh này cho biết Java/Javac mà **shell** tìm thấy. **Không tự chứng minh** đó là JVM của Gradle daemon hay compiler toolchain được task lựa chọn.

### 6.3. Kiểm tra JDK toolchains Gradle nhìn thấy

~~~bash
./gradlew -q javaToolchains
~~~

Trên Windows:

~~~bat
gradlew.bat -q javaToolchains
~~~

Task báo cáo JDK/JRE được Gradle phát hiện, version, vendor, location và nguồn phát hiện. Không có JDK thích hợp trong report là manh mối cho lỗi thiếu toolchain.

Nếu task report không có trong một Gradle quá cũ hoặc build không thể configuration thành công, cần xử lý lỗi runtime Gradle trước hoặc dùng `./gradlew tasks --all` để xem tasks thực tế.

### 6.4. Lấy stacktrace có đủ bối cảnh

~~~bash
./gradlew help --stacktrace --info
./gradlew compileJava --stacktrace --info
~~~

Nếu `help` đã fail, lỗi có thể nằm ở **Gradle startup/configuration, buildscript/plugin**, chưa tới Java compiler. Nếu `help` pass nhưng `compileJava` fail, tập trung vào JavaCompile task, source/release/toolchain và compile classpath.

Với project multi-project:

~~~bash
./gradlew :app:compileJava --stacktrace --info
./gradlew :app:run --stacktrace --info
~~~

Không chạy mọi task nặng một cách ngẫu nhiên. Xác định **task đầu tiên thực sự fail**, exception đầu tiên trong `Caused by` và class được nêu trong message.

### 6.5. Đối chiếu với Wrapper file

Nhìn `gradle/wrapper/gradle-wrapper.properties` và key `distributionUrl` để biết bản Gradle dự kiến. Nếu shell gọi `gradle` thay vì `./gradlew`, rất có thể đang dùng bản Gradle khác.

Trong hướng dẫn debug, không sửa tự động `distributionUrl` bằng một chuỗi “latest” mà chưa kiểm tra plugin compatibility và checksum. Nên upgrade Wrapper có chủ đích, test và commit version rõ ràng.

## 7. JVM chạy Gradle khác compiler toolchain: ví dụ quan trọng

### 7.1. Java toolchain

Kotlin DSL (`build.gradle.kts`):

~~~kotlin
plugins {
    id("java")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Groovy DSL (`build.gradle`):

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

Điều này yêu cầu Java tasks có hỗ trợ toolchain dùng **JDK 17** thích hợp. Nó **không khởi động lại Gradle bằng JDK 17** và không ép mọi custom plugin/tool tự dùng Java 17.

### 7.2. Lựa chọn task launcher độc lập

Một task JavaExec chạy JDK 17 rõ ràng:

~~~kotlin
tasks.register<JavaExec>("runOn17") {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(17))
    })
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("demo.App")
}
~~~

Đoạn này là **snippet minh họa**, yêu cầu plugin Java tạo `sourceSets["main"]` và project thật có `demo.App`. Dùng toolchain launcher để nói rõ JDK chạy task; không nhầm với JVM chạy daemon.

Một Test task tùy chỉnh:

~~~kotlin
tasks.withType<Test>().configureEach {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(17))
    })
}
~~~

Nếu code test được compile thành Java 21 class files nhưng chạy bằng JDK 17, task sẽ gặp `UnsupportedClassVersionError`. Chọn Java 17 launcher **không tự làm bytecode thấp xuống**.

### 7.3. JDK chạy Gradle cần tương thích với Gradle release

Với Gradle 8.4 + JDK 21:

- **Không** dùng Java 21 để chạy Gradle 8.4 vì hỗ trợ chính thức cho Java 21 runtime bắt đầu từ Gradle 8.5.
- Có thể chạy Gradle 8.4 trên một JVM được nó hỗ trợ (ví dụ Java 17) và dùng Java 21 **toolchain** để compile/test dự án, vì hỗ trợ toolchain Java 21 bắt đầu từ 8.4.
- Hoặc nâng Gradle lên 8.5+ phù hợp plugins để chạy Gradle bằng Java 21.

Với Gradle 9 + Java 11:

- Gradle 9 yêu cầu JVM chạy **tối thiểu Java 17**.
- Không thể “chữa” bằng cách đặt `sourceCompatibility=11` vì sourceCompatibility chỉ điều khiển compiler target.
- Dùng Gradle JVM được hỗ trợ, rồi `options.release.set(11)` nếu ứng dụng cần chạy Java 11.

### 7.4. Gradle daemon JVM, JAVA_HOME và IDE

Có nhiều nơi chọn JVM chạy Gradle:

- `JAVA_HOME`/`PATH` của shell và Wrapper bootstrap.
- `org.gradle.java.home` trong `gradle.properties` (khi được dùng).
- **Daemon JVM criteria** trong một số Gradle mới, được quản lý qua `updateDaemonJvm` và file `gradle/gradle-daemon-jvm.properties`; những tiêu chí này có thể được ưu tiên so với `JAVA_HOME`/`org.gradle.java.home`.
- Gradle JVM/Gradle JDK do IntelliJ IDEA, Android Studio hoặc Eclipse cấu hình.
- IDE/tooling launcher có thể dùng môi trường riêng so với terminal.
- CI setup-java/container image và env scope của từng build step.

Vì thế `echo "$JAVA_HOME"` và `./gradlew --version` có thể chỉ về những JDK khác nhau. Khi sửa, kiểm tra **đường JDK thực sự được daemon sử dụng**, không chỉ biến môi trường của shell.

### 7.5. Khi đổi JDK mà daemon vẫn dùng Java cũ

Có thể dừng các daemons do đúng Wrapper quản lý rồi chạy lại:

~~~bash
./gradlew --stop
./gradlew --version
~~~

Windows:

~~~bat
gradlew.bat --stop
gradlew.bat --version
~~~

`--stop` không đổi cấu hình JDK; nó chỉ dừng daemons để lần chạy sau lựa chọn lại theo cấu hình hiện tại. Nếu Gradle không thể khởi động đủ để thực thi `--stop`, dừng daemon bằng cơ chế quản trị tiến trình có kiểm soát hoặc sửa JVM configuration trước.

**Không xóa toàn bộ `~/.gradle` hoặc Gradle cache làm bước đầu tiên.** Caches không thay đổi được định dạng class 65 thành class 61; việc xóa cache làm mất dữ liệu và tăng thời gian resolution mà chưa giải quyết root cause.

## 8. `--release`, `sourceCompatibility` và `targetCompatibility`

### 8.1. Tại sao chỉ đổi targetCompatibility có thể chưa đủ?

~~~kotlin
java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
~~~

Đây là các tùy chọn hữu ích với một số build cũ, nhưng **không chỉ định chắc compiler JDK** nào được dùng để build. Quan trọng hơn, đặt target thấp trong khi dùng compiler JDK mới hơn **không tự chặn** việc vô tình gọi một API chỉ tồn tại ở JDK mới.

Ví dụ bạn compile trên JDK 21 với `-source 17 -target 17` nhưng code tham chiếu API standard library được thêm sau 17. Classfile có major 61, nhưng runtime Java 17 có thể gặp `NoSuchMethodError` vì API không tồn tại.

### 8.2. `options.release` mạnh hơn để cross-compile

Kotlin DSL:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

`--release 17` yêu cầu javac:

1. Chấp nhận ngôn ngữ Java tới release 17.
2. Tạo class file major 61.
3. Giới hạn **Java platform APIs** mà compiler cho phép theo Java 17 (trong phạm vi javac hỗ trợ).

Nó **không** tự xác minh mọi third-party dependency hỗ trợ Java 17, cũng không ép JVM **chạy Gradle** hoặc **chạy production** là Java 17.

### 8.3. Kết hợp toolchain và --release

~~~kotlin
plugins {
    id("java")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Với Gradle version có thể dùng Java 21 toolchain, đây là một cấu hình hợp lệ: **javac JDK 21** tạo bytecode và Java platform API tương thích **Java 17**. Nếu project phải build trên máy chỉ có JDK 17, chọn toolchain 17 đơn giản hơn.

**Không thể** dùng javac 17 để `--release 21`: javac 17 không hỗ trợ target tương lai. Lỗi `release version 21 not supported` yêu cầu sửa **compiler JDK**, không chỉ đổi runtime Java.

### 8.4. Nếu phải hỗ trợ Java 8/11

Dùng Gradle/JDK runtime thỏa compatibility matrix của Gradle release, rồi cấu hình compiler target riêng:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
}
~~~

Đây là **snippet minh họa** cho ứng dụng Java có source/API tương thích Java 11. Cần chạy test trên **Java 11 runtime thực tế** nếu sản phẩm phải hỗ trợ Java 11. Compiler Java 17 với `--release 11` chưa bảo đảm external dependency cũng tương thích Java 11.

## 9. Project thực hành hoàn chỉnh Java 17

Phần này có **một Java program runnable** và build script Kotlin DSL. Không cần Maven Central hoặc external modules, nên bạn có thể thực hành bằng Gradle đã cài và JDK 17.

Chương trình sẽ tự mở file `App.class` của chính nó, đọc magic/minor/major, rồi in ra thông tin. Khi dùng javac Java 17 hoặc `--release 17`, kết quả xác định là `major=61`, `minor=0`.

### 9.1. Cấu trúc thư mục

~~~text
class-version-lab/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    └── main/
        └── java/
            └── demo/
                └── App.java
~~~

Nếu chưa có Wrapper, lệnh `./gradlew` chưa tồn tại. Trong ví dụ dưới, dùng `gradle` của bản đã cài; có thể tạo Wrapper sau khi xác định version phù hợp. Chạy Gradle bằng JDK được release đó hỗ trợ.

### 9.2. settings.gradle.kts

~~~kotlin
rootProject.name = "class-version-lab"
~~~

### 9.3. build.gradle.kts đầy đủ

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    id("application")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}

application {
    mainClass.set("demo.App")
}
~~~

Giải thích:

- Plugin `application` áp dụng Java support, tạo `compileJava` và `run`.
- `java.toolchain` yêu cầu JDK 17.
- `options.release.set(17)` yêu cầu bytecode Java 17 (major 61) và kiểm soát Java APIs.
- `mainClass.set("demo.App")` trùng package/class của source Java.
- Không có `repositories` hay dependencies bên ngoài; lỗi resolve Maven Central sẽ không đến từ code chính của project này.
- `run` do Application plugin thiết lập với runtime Java toolchain phù hợp; nếu có custom task đổi Java launcher, hãy kiểm tra override đó.

### 9.4. src/main/java/demo/App.java đầy đủ

~~~java
package demo;

import java.io.DataInputStream;
import java.io.IOException;
import java.io.InputStream;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws IOException {
        try (InputStream stream =
                     App.class.getResourceAsStream("/demo/App.class")) {
            if (stream == null) {
                throw new IOException("App.class not found on classpath");
            }

            DataInputStream input = new DataInputStream(stream);
            int magic = input.readInt();
            if (magic != 0xCAFEBABE) {
                throw new IOException("Invalid class-file header");
            }

            int minor = input.readUnsignedShort();
            int major = input.readUnsignedShort();

            System.out.println(
                    "runtime.feature=" + Runtime.version().feature());
            System.out.println("class.major=" + major);
            System.out.println("class.minor=" + minor);
            System.out.println("message=Hello from Java 17");
        }
    }
}
~~~

Code dùng API `DataInputStream` đọc header `CAFEBABE + minor + major` của chính classfile. Không dùng thư viện ngoài. `Runtime.version().feature()` là API Java có thể dùng trên Java 17.

### 9.5. Chạy Gradle Application

~~~bash
gradle --quiet run
~~~

Khi toolchain 17 đã sẵn, Gradle version hỗ trợ, source và build script đúng như trên, **stdout của Java program**:

~~~text
runtime.feature=17
class.major=61
class.minor=0
message=Hello from Java 17
~~~

Giải thích từng dòng:

- `runtime.feature=17`: JVM của **task run** là Java 17.
- `class.major=61`: compiler đã tạo bytecode Java 17.
- `class.minor=0`: không compile class với preview marker.
- `message=...`: ứng dụng chạy thành công.

**Chú ý:** Nếu bạn chạy code bằng một launcher Java 21 bên ngoài Gradle, dòng runtime.feature sẽ là 21 dù class.major vẫn 61. Đây là hành vi đúng: **runtime mới hơn có thể chạy class file cũ hơn** trong giới hạn compatibility của nó.

### 9.6. Dùng Gradle Wrapper (nếu đã có)

macOS/Linux:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew --quiet run
~~~

Windows PowerShell/cmd:

~~~bat
gradlew.bat --version
gradlew.bat -q javaToolchains
gradlew.bat --quiet run
~~~

Nếu có lỗi chạy Gradle trước `compileJava`, ưu tiên sửa JVM chạy Gradle/Wrapper/plugin thay vì sửa source `App.java`.

### 9.7. Đọc bytecode bằng javap

Sau khi đã chạy `gradle classes`:

~~~bash
javap -verbose -classpath build/classes/java/main demo.App
~~~

Tìm các dòng:

~~~text
minor version: 0
major version: 61
~~~

Toàn bộ output `javap -verbose` dài và khác theo JDK, nên hai dòng trên là **trích đoạn cần kiểm tra**. Trên Windows có thể lọc bằng:

~~~bat
javap -verbose -classpath build\classes\java\main demo.App | findstr /C:"major version" /C:"minor version"
~~~

PowerShell:

~~~powershell
javap -verbose -classpath build\classes\java\main demo.App |
    Select-String "major version", "minor version"
~~~

Lệnh `javap` của JDK mới có thể đọc định dạng class mới hơn JDK cũ. Nếu chính `javap` báo không hiểu class version, dùng `javap` từ JDK phù hợp để kiểm tra hoặc đọc header bằng một công cụ binary an toàn.

### 9.8. Biên dịch/chạy riêng bằng javac/java

macOS/Linux:

~~~bash
mkdir -p out
javac --release 17 -d out src/main/java/demo/App.java
java -cp out demo.App
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out src\main\java\demo\App.java
java -cp out demo.App
~~~

**Nếu cả `javac` và `java` thực sự là JDK 17**, stdout giống mục 9.5:

~~~text
runtime.feature=17
class.major=61
class.minor=0
message=Hello from Java 17
~~~

`javac` ở đây chạy **không qua Gradle**: nó chứng minh Java source hợp lệ và target đúng, nhưng không chứng minh Gradle toolchain/daemon đã chọn đúng. Nếu `java` trong PATH thực ra là Java 21, nó sẽ in runtime.feature=21; phải kiểm tra `java -version` và đường executable thực tế trước khi so sánh.

## 10. Tạo lỗi unsupported class version có chủ đích

Thí nghiệm này cần **hai JDK được cài đặt**: JDK 21 để compile và Java 17 runtime để chạy. Đừng làm trên project production; sử dụng project mẫu ở mục 9.

### 10.1. Biên dịch bằng javac 21 cho Java 21

Ví dụ Linux/macOS với paths thay bằng **đường thật của máy**:

~~~bash
/path/to/jdk21/bin/javac --release 21 -d out21 src/main/java/demo/App.java
/path/to/jdk21/bin/javap -verbose -classpath out21 demo.App
~~~

Trong `javap` tìm:

~~~text
minor version: 0
major version: 65
~~~

Nếu bạn dùng JDK 21 compiler mặc định mà không chỉ định `--release`, class cũng thường có major 65, nhưng dùng `--release 21` sẽ minh bạch hơn.

### 10.2. Chạy class Java 21 bằng Java 17 runtime

~~~bash
/path/to/jdk17/bin/java -cp out21 demo.App
~~~

Kết quả là **lỗi** `java.lang.UnsupportedClassVersionError`. Một dạng message điển hình:

~~~text
Error: LinkageError occurred while loading main class demo.App
    java.lang.UnsupportedClassVersionError: demo/App has been compiled
    by a more recent version of the Java Runtime (class file version 65.0),
    this version of the Java Runtime only recognizes class file versions
    up to 61.0
~~~

Đây là **trích đoạn đại diện**, không cam kết toàn bộ stdout/stderr giống y hệt trên mọi vendor/JDK update. Điều không đổi là **bytecode 65.0 vượt khả năng runtime 61.0**.

### 10.3. Cách sửa A: chạy bằng Java 21

~~~bash
/path/to/jdk21/bin/java -cp out21 demo.App
~~~

Java program chạy được và có output:

~~~text
runtime.feature=21
class.major=65
class.minor=0
message=Hello from Java 17
~~~

Dòng message chỉ là chuỗi cố định trong source; tên “Hello from Java 17” không phản ánh runtime hay class version. Thí nghiệm cố tình giữ dòng ấy để bạn thấy **text do lập trình viên in ra không thể dùng thay `Runtime.version()`/`javap`**.

### 10.4. Cách sửa B: giữ runtime Java 17, compile lại với --release 17

Dùng **javac JDK 21** để target Java 17:

~~~bash
/path/to/jdk21/bin/javac --release 17 -d out17 src/main/java/demo/App.java
/path/to/jdk17/bin/java -cp out17 demo.App
~~~

Stdout:

~~~text
runtime.feature=17
class.major=61
class.minor=0
message=Hello from Java 17
~~~

Lưu ý `--release 17` bảo đảm mã Java chỉ dùng những **Java platform APIs** trong Java 17, nhưng không ép third-party dependencies có cùng target bytecode. Nếu bạn vẫn dùng một JAR bên ngoài có class.major=65, JVM Java 17 vẫn có thể lỗi khi nạp class đó.

### 10.5. Windows PowerShell tương đương

Giả sử bạn có các executable JDK 21/JDK 17 tại paths thực tế, PowerShell gọi bằng call operator `&`:

~~~powershell
& "C:\Java\jdk-21\bin\javac.exe" --release 21 -d out21 src\main\java\demo\App.java
& "C:\Java\jdk-17\bin\java.exe" -cp out21 demo.App
~~~

`C:\Java\jdk-21` và `C:\Java\jdk-17` ở trên là **ví dụ đường cài đặt**, hãy thay bằng đường thật. Chạy lệnh thứ hai sẽ thất bại như mục 10.2 nếu compiler tạo major 65 và runtime chỉ hỗ trợ 61.

Sửa bằng cách biên dịch lại:

~~~powershell
& "C:\Java\jdk-21\bin\javac.exe" --release 17 -d out17 src\main\java\demo\App.java
& "C:\Java\jdk-17\bin\java.exe" -cp out17 demo.App
~~~

Stdout giống mục 10.4. Không cần sửa `PATH` toàn máy chỉ để thử; gọi executable bằng absolute path làm thí nghiệm dễ lặp lại hơn.

## 11. Lỗi Gradle 8.4 + Java 21: phân biệt toolchain với Gradle runtime

Đây là một ca điển hình dễ sửa sai.

### 11.1. Tổ hợp A: không phù hợp với JVM chạy Gradle

~~~text
Gradle Wrapper: 8.4
Gradle daemon JVM: Java 21
Project Java toolchain: Java 21
~~~

Gradle 8.4 đã hỗ trợ dùng **Java 21 làm toolchain**, nhưng chưa hỗ trợ **chạy Gradle trên Java 21** một cách chính thức. Build có thể fail ở script/plugin parsing trước khi biên dịch `src/main/java`.

**Sửa hướng 1:** Nâng Gradle Wrapper lên **ít nhất Gradle 8.5**, đồng thời kiểm tra plugin versions và build logic.

**Sửa hướng 2:** Giữ Gradle 8.4 nhưng chạy daemon trên JDK được hỗ trợ (ví dụ Java 17); vẫn dùng JDK 21 như compiler toolchain nếu cần.

### 11.2. Tổ hợp B: có thể hợp lệ

~~~text
Gradle Wrapper: 8.4
Gradle daemon JVM: Java 17
Java toolchain compiler: JDK 21
Java bytecode target: 17 nếu options.release=17
Application runtime: Java 17
~~~

Yêu cầu là plugin/task tương thích và Java sources/dependencies hỗ trợ target 17. Gradle 8.4 có thể sử dụng JDK 21 toolchain để compile, nhưng **JavaCompile --release 17** bảo vệ Java platform APIs và bytecode target.

Nếu chỉ cấu hình `languageVersion=21` mà **không có `options.release=17`**, compiler thường tạo bytecode 65 → khi chạy bằng Java 17 có thể xuất hiện `UnsupportedClassVersionError`. Thấy build compile thành công **không chứng minh** app có thể chạy Java 17.

### 11.3. Nâng Wrapper khác thay Java launcher

- Đổi Wrapper để một Gradle version hỗ trợ **JVM chạy Gradle**.
- Đổi toolchain để chọn **JDK compiler/test/JavaExec**.
- Đổi `options.release` để chọn **bytecode/API level**.
- Đổi runtime Docker image/JRE để chọn **JVM chạy artifact cuối**.

Không thay cả bốn nếu chỉ một tầng sai. Một lần thay đổi nhỏ, chạy lại đúng task fail và ghi rõ version trước/sau giúp tránh tạo thêm lỗi plugin.

## 12. Khi `Unsupported class file major version 65` đến từ Gradle/Groovy/ASM

Thông báo **không có tên exception `UnsupportedClassVersionError`** có thể được ném bởi **thư viện phân tích bytecode** như ASM được Gradle/Groovy/plugin sử dụng, thường trong pha **configuration**.

### 12.1. Dấu hiệu

Stacktrace có thể chứa:

~~~text
org.codehaus.groovy.control.MultipleCompilationErrorsException
groovyjarjarasm.asm.ClassReader
Unsupported class file major version 65
~~~

Hoặc:

~~~text
Could not open cp_settings generic class cache for settings file
Unsupported class file major version 65
~~~

**Không suy ra tuyệt đối:** Tên package khác đi tùy Gradle/Groovy/ASM/plugin version. Quan trọng là lỗi xảy ra **ở đâu** và class nào đang được thư viện đọc.

### 12.2. Vì sao đổi targetCompatibility không giải quyết?

Nếu Gradle/Groovy đã fail **khi parse `settings.gradle`/`build.gradle`**, JavaCompile task **chưa chạy**. `targetCompatibility = 17` chỉ tác động compiler Java application, không thay đổi class files của JDK đang chạy Gradle, compiled plugin classes hay khả năng parser của Gradle phiên bản cũ.

Phải kiểm tra:

1. Gradle Wrapper version đang dùng.
2. JVM của Gradle daemon và IDE.
3. Plugins/buildscript dependencies đã được compile cho Java nào.
4. Nếu stacktrace chỉ vào plugin class, plugin đó có yêu cầu JVM cao hơn runtime Gradle không?
5. Các bundled Groovy/ASM/Kotlin libraries của Gradle version có hỗ trợ class version đó không?
6. Cấu hình Daemon JVM, `JAVA_HOME` và versions bị IDE ghi đè.

### 12.3. Hướng sửa cụ thể

- Nếu **Gradle version không hỗ trợ JDK hiện tại**, chạy Gradle bằng một JDK được hỗ trợ hoặc nâng Wrapper sau khi test plugin compatibility.
- Nếu **plugin class được compile Java 21** nhưng daemon chạy Java 17, dùng plugin build cho Java 17, nâng Gradle JVM lên Java 21 **và** dùng bản Gradle hỗ trợ nó, hoặc build lại plugin target17 nếu source/API cho phép.
- Nếu **ASM/Groovy quá cũ** không đọc Java 21 class files, nâng thành phần/plugin/Gradle phù hợp; đổi JavaCompile của app không đủ.
- Nếu lỗi là do **init script / ~/.gradle/init.d plugin**, kiểm tra stacktrace nêu đường script. Không mặc định mã nguồn app có vấn đề.
- Nếu IDE chạy Gradle bằng JDK khác terminal, sửa **Gradle JVM setting** ở IDE và thử lại.

**Không nên** tải một JAR ASM mới rồi tự chèn vào Gradle distribution để “vá” nếu chưa hiểu binary compatibility; Gradle có hệ phụ thuộc nội bộ, thay lung tung có thể gây xung đột nghiêm trọng.

## 13. Plugin bytecode và custom Gradle tasks

### 13.1. Plugin chạy trên JVM Gradle

Một binary Gradle plugin có class files riêng. Ví dụ plugin được compile target Java 21 (**major 65**) trong khi daemon Gradle chạy Java 17 (**hỗ trợ 61**).

Ngay cả khi project khai báo:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

plugin vẫn không được nạp nếu daemon JVM Java 17 không hỗ trợ bytecode của plugin. Toolchain của **project Java tasks** không “biên dịch lại” plugin binary ở runtime.

Hướng sửa:

- Chọn plugin version target Java 17 hoặc build lại plugin với target tương thích.
- Hoặc nâng Gradle JVM và Wrapper lên một **tổ hợp được hỗ trợ** bởi cả Gradle và plugin.
- Kiểm tra các convention plugins trong `buildSrc`/included builds, init scripts, annotation/bytecode enhancement plugins.
- Đọc stacktrace để tìm **class của plugin** đang được load/scan.

### 13.2. buildSrc và included builds

`buildSrc` và các included builds chứa build logic được compile/running theo mô hình Gradle riêng. Mã chúng có thể dùng JDK/compiler/toolchain khác với `src/main/java`. Nếu class của build logic có major 65 mà Gradle runtime là Java 17, lỗi có thể xảy ra **trước compileJava của ứng dụng**.

Đừng chỉ kiểm tra `build/classes/java/main`; còn có các artifacts của plugins/build logic. Dùng `--stacktrace` xác định source của class và phiên bản producer.

### 13.3. Plugin Android/Kotlin/Spring Boot cần ma trận riêng

Một tổ hợp được Gradle hỗ trợ **không đồng nghĩa** Android Gradle Plugin hoặc Kotlin compiler plugin đã hỗ trợ nó. Với Android:

- Kiểm tra **AGP version ↔ Gradle version ↔ Gradle JDK** theo tài liệu Android chính thức.
- Phân biệt Java/Kotlin bytecode target và Android desugaring/minSdk.
- Không tự nâng Gradle 9 nếu AGP của project chỉ được kiểm chứng với một Gradle 8.x cụ thể.
- Cần kiểm tra IDE embedded JDK và Gradle JDK setting.

Với Kotlin:

- `kotlinOptions.jvmTarget` hoặc `compilerOptions.jvmTarget` điều khiển **Kotlin bytecode**, khác `JavaCompile.options.release`.
- Nếu Java target17 nhưng Kotlin target21, những class Kotlin có thể major65 dù Java files là61; Gradle có thể kiểm tra target consistency nhưng không phải mọi build/plugin đều giống nhau.
- Cần cấu hình Kotlin JVM toolchain và compiler target tương thích theo **Kotlin Gradle Plugin version**.

## 14. `No matching variant` vì JVM target không tương thích

Đây là lỗi **dependency resolution** trước khi JVM cố nạp class, không phải chính `UnsupportedClassVersionError`.

Giả sử:

~~~text
Consumer :app compileClasspath:
    org.gradle.jvm.version = 17
    org.gradle.usage = java-api

Producer :library apiElements:
    org.gradle.jvm.version = 21
    org.gradle.usage = java-api
~~~

Consumer đang yêu cầu thư viện tương thích **Java 17**, trong khi producer chỉ công bố variant **Java 21**. Gradle có thể từ chối với `No matching variant of project :library` và mô tả JVM target không phù hợp.

Các lệnh để đọc đúng mô hình:

~~~bash
./gradlew :library:outgoingVariants --variant apiElements
./gradlew :app:resolvableConfigurations --configuration compileClasspath
./gradlew :app:dependencyInsight --dependency library --configuration compileClasspath
~~~

Phân tích:

- `:library` đang compile target Java 21 hay toolchain release bao nhiêu?
- `:app` yêu cầu Java 17 do toolchain/targetCompatibility?
- Có một producer variant tương thích Java 17 được công bố không?
- Tại sao `:app` lại cần API từ thư viện Java 21 nếu production JDK chỉ 17?

**Sửa đúng:** build library target Java 17 nếu source/API cho phép, hoặc nâng runtime và consumer target lên Java 21 khi yêu cầu sản phẩm cho phép. Không sửa giả `org.gradle.jvm.version` của variant thành17 trong khi JAR thực tế chứa class major65: điều này chỉ che chẩn đoán và sẽ tạo runtime failure.

## 15. Runtime của test và application có thể khác Gradle daemon

### 15.1. Gradle chạy trên Java 21, test cần Java 17

Một project có thể chạy Gradle daemon trên Java 21 nhưng test trên Java 17 bằng toolchain.

~~~kotlin
tasks.withType<Test>().configureEach {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(17))
    })
}
~~~

Nếu `compileTestJava` tạo class.major65 (do không cấu hình release hoặc compile toolchain sai), `test` trên Java17 sẽ fail, dù `./gradlew --version` cho thấy daemon Java21 chạy tốt.

Cách sửa: kiểm tra **toolchain của JavaCompile và Test riêng**, target bytecode/test dependencies, không chỉ nhìn daemon JVM.

### 15.2. `run` thành công nhưng production Java17 thất bại

Giả sử local `./gradlew run` dùng Java21, còn Docker image chứa Java17. App class.major65 vẫn chạy local nhưng lỗi production.

Kiểm tra:

~~~bash
java -version
javap -verbose -classpath build/classes/java/main demo.App
~~~

Ở **container** chạy:

~~~bash
java -version
~~~

Với executable Java17 trong container, class.major65 là root cause. Chọn target17 bằng `options.release` và kiểm tra toàn bộ dependencies, hoặc nâng production runtime khi thích hợp.

**Không coi `java -version` ở laptop là bằng chứng runtime JDK của container**. Dockerfile base image, Kubernetes runtime image hoặc cloud deployment runtime mới là nơi quan trọng.

### 15.3. Build task khác dùng JVM riêng

Các task codegen, checkstyle, PMD, annotation processors hoặc custom JavaExec có thể dùng Java launcher khác compiler. Một plugin có thể tự fork JVM mà **không dùng Gradle Java toolchain mặc định**. Khi stacktrace từ công cụ cụ thể, đọc task inputs/configuration của công cụ và phiên bản nó hỗ trợ.

## 16. Đọc class version bên trong JAR thật

### 16.1. Liệt kê artifacts

~~~bash
jar --list --file build/libs/app.jar
~~~

Điều này **chỉ liệt kê entries**; không cho biết major version. Trong multi-project hoặc build khác, JAR file có thể tên khác `app.jar`; dùng đường output thật của task `jar`.

### 16.2. Dùng javap với JAR

~~~bash
javap -verbose -classpath libs/some-library.jar package.name.SomeClass
~~~

Thay đường JAR và fully qualified class name thật. Tìm:

~~~text
minor version: 0
major version: 65
~~~

Nếu dùng `javap` cũ không đọc được class version mới, chạy `javap` của JDK tương thích. Để kiểm tra từng class trong multi-release JAR, phải quan tâm `META-INF/versions/` và lựa chọn runtime version, không chỉ nhìn class ở root.

### 16.3. Thư viện bên ngoài có thể mới hơn source của bạn

Ví dụ `src/main/java` của app được compile `--release 17` → major61; một dependency JAR chứa class.major65 vẫn có thể gây lỗi khi JVM Java17 nạp class đó.

Cách xử lý:

1. Dùng `dependencies --configuration runtimeClasspath` hoặc `dependencyInsight` tìm module/version thực tế.
2. Xác định **class nào** trong exception thuộc JAR nào.
3. Đọc class major bằng javap.
4. Chọn version dependency có **Java17 baseline** hoặc nâng runtime target nếu hợp đồng cho phép.
5. Kiểm tra lại transitive dependencies và runtime variant.
6. Test trên chính Java17 runtime, không chỉ compile source.

Đừng “hạ” classfile bằng cách sửa 2 byte của header từ65 xuống61. Bytecode/constant pool/API mới có thể không được JVM cũ hiểu; làm vậy chỉ biến một lỗi rõ ràng thành lỗi khó đoán.

## 17. Preview features: lỗi tương thích dù cùng Java major

Preview-enabled classfile (ví dụ major61, minor65535) có thể yêu cầu Java17 **và** bật preview để chạy. Nó không tự chạy trên Java21 dù runtime mới hơn.

Ví dụ minh họa cho Java17 compiler (khi mã thực sự dùng preview syntax):

~~~bash
javac --enable-preview --release 17 -d out17 src/main/java/demo/PreviewExample.java
java --enable-preview -cp out17 demo.PreviewExample
~~~

`PreviewExample.java` là **tên giả trong ví dụ lệnh**, không thuộc project runnable ở mục 9. Đừng copy lệnh này nếu chưa có source dùng preview features. Để chẩn đoán, dùng `javap -verbose` xem minor; nếu `65535`, kiểm tra Java release cụ thể và `--enable-preview`.

Chỉ thêm flag preview khi project chủ đích dùng preview API/language feature và Java runtime/compiler cùng release. Không dùng `--enable-preview` để chữa Java21 bytecode trên Java17.

## 18. Quy trình xử lý theo decision tree

~~~text
Lệnh Gradle bị lỗi
       |
       v
Chạy ./gradlew --version / đọc Gradle JVM và Wrapper
       |
       +--> Gradle không start/configure được?
       |       |
       |       +--> So JVM chạy Gradle với Compatibility Matrix
       |       +--> Xem plugin/buildSrc/Groovy/ASM trong stacktrace
       |       +--> Đổi đúng Gradle JVM hoặc nâng Wrapper/plugin
       |
       +--> compileJava fail?
       |       |
       |       +--> javac -version / javaToolchains
       |       +--> Xem --release/source/target
       |       +--> Xem dependency compiled class versions
       |
       +--> dependency resolution fail?
       |       |
       |       +--> No matching variant -> xem JVM target attributes
       |       +--> Dependency không có class compatible -> chọn version khác
       |
       +--> test/run/deploy fail?
               |
               +--> Xác định Java runtime của task/container
               +--> javap -verbose class bị lỗi
               +--> So major với runtime maximum
               +--> Recompile đúng release hoặc đổi runtime phù hợp
~~~

### 18.1. Ưu tiên sửa đúng điểm

1. **Lỗi ở Gradle startup:** sửa JVM chạy Gradle hoặc version Wrapper/plugin, chưa đụng Java source target.
2. **Lỗi ở JavaCompile:** sửa compiler toolchain/release/API compatibility.
3. **Lỗi ở project dependency matching:** sửa producer/consumer JVM variants, đừng giả attributes.
4. **Lỗi ở Test/JavaExec:** sửa task runtime Java launcher, test class bytecode/dependencies.
5. **Lỗi ở production:** xác nhận JRE thật và mọi classfiles của artifact/runtime dependencies.
6. **Lỗi ở external plugin:** plugin baseline JDK và binary compatibility với Gradle daemon.

## 19. Checklist theo môi trường

### 19.1. Terminal trên macOS/Linux

~~~bash
./gradlew --version
java -version
javac -version
which java
which javac
echo "$JAVA_HOME"
./gradlew -q javaToolchains
./gradlew help --stacktrace
~~~

Nếu có custom `org.gradle.java.home` hoặc Daemon JVM criteria, kiểm tra chúng thay vì giả định `JAVA_HOME` quyết định tất cả.

### 19.2. Windows PowerShell

~~~powershell
.\gradlew.bat --version
java -version
javac -version
Get-Command java
Get-Command javac
where.exe java
where.exe javac
$env:JAVA_HOME
.\gradlew.bat -q javaToolchains
.\gradlew.bat help --stacktrace
~~~

`where.exe` là tiện ích Windows liệt kê executables trong PATH; `Get-Command` phản ánh resolution của PowerShell. Khác nhau có thể do alias/function/launcher khác.

### 19.3. IntelliJ IDEA / Android Studio

1. Xem **Gradle JVM / Gradle JDK** trong Settings.
2. Đối chiếu **Project SDK** và **language level** (chúng không tự là Gradle daemon JDK).
3. Đối chiếu Gradle Wrapper distribution trong project.
4. Đọc thông điệp lỗi trong Gradle Tool Window cùng `--stacktrace`.
5. Với Android, đối chiếu riêng AGP–Gradle–JDK và Java/Kotlin compile target.
6. Khi IDE khác terminal, so đầu ra `Gradle --version` từ hai môi trường trước khi sửa source.

### 19.4. CI/CD

1. In `./gradlew --version` và `java -version` ngay đầu job.
2. Pin JDK setup và Gradle Wrapper.
3. Kiểm tra Gradle daemon JVM criteria / `org.gradle.java.home`.
4. Kiểm tra compiler/toolchain thực tế bằng `javaToolchains` hoặc task info.
5. Chạy test trên đúng runtime target (17, 21...), không chỉ trên JDK mới nhất.
6. Nếu deploy container, kiểm tra `java -version` **bên trong container**.
7. Khi build artifact dùng native image/shading/bytecode transforms, kiểm tra classfile **sau** transformation.
8. Không nâng plugin/Gradle/JDK cùng lúc nếu chưa có compatibility plan.

## 20. Những lỗi thường gặp và cách sửa

### Lỗi 1: “Gradle chạy bằng Java 17 vì tôi đặt toolchain 17”

**Sai.** Java toolchain chỉ chọn công cụ cho tasks hỗ trợ; Gradle daemon có JVM riêng. Kiểm tra `./gradlew --version`.

### Lỗi 2: “JDK 21 có thể chạy Gradle 8.4 vì toolchain 21 được hỗ trợ”

Không đúng. Gradle 8.4 hỗ trợ **toolchain 21**, nhưng chạy Gradle trên Java21 có hỗ trợ chính thức từ **8.5**.

### Lỗi 3: “Đổi targetCompatibility của app sẽ chữa Groovy parser”

Không nếu Gradle fail khi parse buildscript. Xem JVM chạy Gradle, Groovy/ASM/plugin versions.

### Lỗi 4: “Major 65 có nghĩa Java 17”

Sai; Java17 là **61**, Java21 là **65**. Đọc bảng mapping.

### Lỗi 5: “Runtime Java21 load class Java17 thì báo lỗi vì major khác”

Thông thường **không**: JVM mới hỗ trợ classfiles các releases cũ. Khả năng tương thích **không đối xứng**: Java17 không load Java21 class, nhưng Java21 thường load Java17 class hợp lệ. Vẫn có thể có API/module/security issues khác.

### Lỗi 6: “Dùng --enable-preview để đọc mọi class mới”

Sai. Preview flag không khiến JVM Java17 hiểu bytecode Java21. Với preview, release compiler/runtime phải phù hợp.

### Lỗi 7: “Pin sourceCompatibility là đã pin compiler JDK”

Sai. Cần `java.toolchain` hoặc task `javaCompiler`. `sourceCompatibility` chỉ nói mức ngôn ngữ.

### Lỗi 8: “Pin targetCompatibility đủ để không dùng API mới”

Sai. Nếu javac mới compile với `-source`/`-target` cũ mà không `--release`, có thể vẫn cho tham chiếu API JDK mới. Dùng `options.release`.

### Lỗi 9: “javac 17 có thể --release 21”

Không thể. Compiler cũ không hỗ trợ release tương lai. Dùng JDK21 compiler.

### Lỗi 10: “Đã compile app --release 17 thì mọi JAR chạy Java17”

Không. Third-party dependencies vẫn có thể chứa class major65. Kiểm tra JAR gây lỗi.

### Lỗi 11: “Chỉ cần cập nhật JAVA_HOME là IDE/daemon đổi ngay”

Không chắc. IDE Gradle JDK, daemon criteria hoặc `org.gradle.java.home` có thể override. Xem Gradle JVM thực tế, rồi dừng daemon nếu cần.

### Lỗi 12: “Cứ xóa ~/.gradle là hết unsupported class”

Không có căn cứ. Xóa cache không biến class bytecode mới thành cũ. Chỉ xóa cache có chọn lọc khi xác định cache corruption, và sao lưu/đánh giá tác động.

### Lỗi 13: “No matching variant = UnsupportedClassVersionError”

Không. No matching variant có thể xảy ra ở dependency selection **trước khi load class**; nó dựa trên attributes/metadata.

### Lỗi 14: “Chạy ./gradlew run pass nghĩa production chắc chắn pass”

Không nếu `run` và container dùng JVM khác. Kiểm tra JVM target/runtime production.

### Lỗi 15: “Plugin compile Java21 nhưng Gradle daemon Java17, toolchain17 chữa được”

Không. Plugin chạy trên Gradle JVM; cần plugin version có bytecode tương thích hoặc Gradle runtime JDK phù hợp.

### Lỗi 16: “Mọi UnsupportedClassVersionError đều do class main của app”

Không. Có thể class từ dependency, plugin, buildSrc, test class hoặc Java agent. Đọc **tên class trong exception** và task/stacktrace.

### Lỗi 17: “Java 17 và Java 21 test cùng kết quả vì source giống nhau”

Không tự đảm bảo nếu target APIs/dependencies/runtime khác. Test thực sự trên runtime thấp nhất mà sản phẩm cam kết.

### Lỗi 18: “Thấy Unsupported class file major version trong Kotlin/Groovy thì bắt buộc nâng JDK”

Không nhất thiết. Parser/ASM có thể **quá cũ** để đọc class mới, dù JVM hiện tại có thể hiểu. Cần xét Gradle/plugin compatibility, không chỉ JDK.

### Lỗi 19: “Tôi tự sửa header CAFEBABE major=61 sẽ dùng được JAR Java21 trên Java17”

Nguy hiểm và không hợp lệ. Định dạng, opcodes, constant pool, APIs có thể không tương thích; phải rebuild/cross-compile bằng toolchain/release thích hợp hoặc thay dependency.

### Lỗi 20: “Gradle 9 có thể chạy Java11 vì project target11”

Không. Gradle9 yêu cầu JVM chạy từ Java17. Project vẫn có thể target Java11 bằng compiler phù hợp và `--release 11`, sau đó test trên Java11.

## 21. Bài tập thực hành có đáp án

### Bài 1. Giải mã class major

Class trong dependency có `major version: 65`. Production Java17 chạy được không?

**Đáp án:** Không, Java17 tối đa hiểu major61. Cần dependency bản target17 hoặc runtime Java21+ phù hợp.

### Bài 2. Hai phiên bản trong lỗi

~~~text
class file version 61.0, runtime recognizes up to 55.0
~~~

**Đáp án:** Class được compile Java17 (61), runtime là Java11 (55). Hạ bytecode target và API về11 (khi source/libs cho phép) hoặc nâng runtime lên Java17 tương thích.

### Bài 3. Gradle8.4 và Java21

Có thể chạy **Gradle8.4 daemon** trên Java21 không? Có thể dùng **toolchain21** không?

**Đáp án:** Chạy Gradle8.4 trên Java21 **chưa được hỗ trợ chính thức**; Java21 toolchain **được hỗ trợ** từ Gradle8.4. Có thể chạy daemon trên Java17 và compile bằng JDK21 toolchain, hoặc nâng Gradle>=8.5 nếu muốn daemon Java21.

### Bài 4. Gradle9, target Java11

Project cần deploy trên Java11 và dùng Gradle9. Gradle daemon cần Java mấy?

**Đáp án:** Từ Java17 đến mức tối đa Gradle release hỗ trợ. Compiler có thể dùng `options.release.set(11)`; test/deploy phải dùng Java11 runtime.

### Bài 5. Phân loại stacktrace

Lỗi chứa `groovyjarjarasm.asm.ClassReader` trước `compileJava` cùng `Unsupported class file major version 65`.

**Đáp án:** Nghi vấn parser/ASM của Gradle/Groovy/plugin quá cũ hoặc Gradle chạy JVM không hợp lệ; trước hết kiểm tra Wrapper/Gradle JVM và plugin. Không sửa `App.java` trước khi xác định root cause.

### Bài 6. java -version khác Gradle JVM

Terminal in Java21, nhưng `./gradlew --version` cho thấy Daemon JVM Java17.

**Đáp án:** Có lựa chọn JVM riêng cho Gradle; kiểm tra `org.gradle.java.home`, daemon criteria và IDE settings. Không kết luận lệnh `java` trong shell đang chạy daemon.

### Bài 7. Chỉ dùng targetCompatibility=17 khi javac21

App có tham chiếu API chỉ có ở JDK21 nhưng class major61. Vì sao Java17 runtime vẫn có thể fail?

**Đáp án:** `-target 17` có thể tạo bytecode61 mà không chặn JDK21 APIs. Dùng `--release 17` hoặc API compatibility tests; không chỉ nhìn major.

### Bài 8. javac17 và --release21

~~~bash
javac --release 21 -d out src/main/java/demo/App.java
~~~

Nếu `javac -version` là17, kết quả?

**Đáp án:** Compiler báo `release version 21 not supported` hoặc thông điệp tương tự; cần javac21, không phải nâng Java runtime của app một cách vô cớ.

### Bài 9. Gradle toolchain17, run17

Dự án lab không có override, source `App.java` được compile `options.release=17`. Stdout của `gradle --quiet run`?

**Đáp án:**

~~~text
runtime.feature=17
class.major=61
class.minor=0
message=Hello from Java 17
~~~

### Bài 10. JDK21 compiler tạo target17

Dùng `javac21 --release 17`, rồi Java17 runtime chạy class. Class major mấy?

**Đáp án:** Major61, minor0 nếu không preview; mã được phép sử dụng Java17 platform APIs. Phải kiểm tra external libraries riêng.

### Bài 11. Multi-project producer/consumer

Library công bố `org.gradle.jvm.version=21`, app yêu cầu17. Gradle báo `No matching variant`. Có nên sửa producer attribute thành17 nhưng giữ JAR major65?

**Đáp án:** Không. Phải compile library thực sự target17 hoặc nâng runtime/consumer target theo hợp đồng, không quảng cáo sai bytecode.

### Bài 12. Test Java17 trong daemon Java21

Gradle chạy bằng Java21, Test launcher là Java17, test class major65. Lỗi ở tầng nào?

**Đáp án:** Test execution JVM nạp class quá mới. Sửa compiler target/test toolchain hoặc nâng test launcher nếu mục tiêu cho phép. Daemon Java21 không cứu được JVM fork Java17.

### Bài 13. Lỗi trong plugin

Build failure nêu một class của plugin có major65, daemon Java17. `java.toolchain=17` ở application project có tác dụng gì?

**Đáp án:** Không sửa plugin binary. Cần plugin version target17, rebuild plugin đúng target, hoặc dùng Gradle daemon Java21 trên Gradle hỗ trợ.

### Bài 14. Container khác local

Local `gradle run` chạy Java21 thành công, Docker image chỉ Java17. Cần kiểm tra điều gì?

**Đáp án:** Bytecode target của app và **mọi runtime dependencies**; nếu major65, compile/resolve version tương thích Java17 hoặc nâng image Java21 theo yêu cầu.

### Bài 15. Preview

Class major61/minor65535 được compile với preview Java17. Có nên chạy nó trực tiếp trên Java21 với `--enable-preview`?

**Đáp án:** Không dựa vào giả định đó. Preview class của một release bị ràng buộc release tương ứng; cần Java17 với preview enabled khi hợp lệ hoặc compile lại không dùng preview.

### Bài 16. Chẩn đoán tập trung

Một build không chạy được `./gradlew help`. Bạn chọn thao tác đầu tiên?

**Đáp án:** Kiểm tra Wrapper/JDK bằng `./gradlew --version`, Java runtime thực tế, stacktrace và plugins/build scripts. Vì `help` chưa chạy, chưa có bằng chứng lỗi do JavaCompile.

## 22. Checklist trước khi merge thay đổi Gradle/JDK

| Kiểm tra | Tiêu chí đạt |
| --- | --- |
| Gradle Wrapper | Version được pin trong `distributionUrl`; Gradle/JDK compatibility được tra theo release |
| Gradle daemon | JVM nằm trong vùng version được hỗ trợ của Gradle đó |
| Build plugins | Plugin versions tương thích cả Gradle và Gradle JVM |
| Java compiler | Toolchain/compiler JDK được chỉ định rõ |
| Bytecode | `options.release` hoặc policy target hợp lệ, major đúng |
| Java API | Compiler không dùng API vượt minimum supported runtime |
| External modules | Dependency class major không vượt runtime mục tiêu |
| JVM tests | Test chạy ít nhất trên JVM cũ nhất mà app cam kết hỗ trợ |
| Runtime app | `run`, scripts và container dùng JDK dự kiến |
| IDE | Gradle JVM setting không xung đột Wrapper/toolchains |
| CI | In Gradle JVM, `java -version` và `javaToolchains` khi debug |
| Android/Kotlin | Ma trận AGP/Kotlin plugin/Gradle/JDK được xác minh riêng |
| Variants | `org.gradle.jvm.version` producer phù hợp consumer target |
| Preview | Preview flags và release version nhất quán khi có dùng |
| Caches/daemon | Chỉ reset daemon/cache có kiểm soát sau khi tìm nguyên nhân |
| Regressions | Compile, test, run và artifact deployment pass trên target |

**Kết luận:** `UnsupportedClassVersionError` là tín hiệu **JVM không nạp được class với phiên bản bytecode cao hơn khả năng của nó**. Còn `Unsupported class file major version` trong Gradle/Groovy/ASM có thể là vấn đề **Gradle JVM/plugin parser**. Muốn sửa đúng, luôn kiểm tra **cả** Gradle Wrapper, JVM chạy Gradle, compiler toolchain, bytecode target (`--release`), runtime test/application và JVM trong deployment. **Không dùng một cài đặt Java duy nhất để suy ra năm tầng đều đã đúng.**

## 23. Tài liệu tham khảo chính thức

- [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html) — xem cột toolchain và cột running Gradle riêng, và tối thiểu JVM của release.
- [Gradle 9.9 Compatibility Matrix](https://docs.gradle.org/9.9.0/userguide/compatibility.html) — bản tham chiếu cho các mốc trong bảng bài học.
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html) — `java.toolchain`, `options.release`, JVM launcher, phát hiện/provisioning.
- [Gradle — Gradle Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html) — JVM chạy daemon và vòng đời daemon.
- [Gradle — Configuring the Gradle Daemon JVM](https://docs.gradle.org/current/userguide/gradle_daemon.html#sec:configuring_daemon_jvm) — Daemon JVM criteria và file `gradle-daemon-jvm.properties`.
- [Gradle — The Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html) — JavaCompile, Test, Java toolchain và configurations.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html) — chọn version Gradle dự án.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html) — kiểm tra Java runtime dependency graph.
- [Gradle — Variant Selection](https://docs.gradle.org/current/userguide/variant_aware_resolution.html) — JVM attributes và `No matching variant`.
- [Oracle JVM Specification, Chapter 4](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html) — classfile header, major/minor version, preview constraints.
- [Oracle javac Documentation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html) — `--release`, source/target và version support.
- [Oracle javap Documentation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html) — `-verbose` và đọc major/minor classfile.
