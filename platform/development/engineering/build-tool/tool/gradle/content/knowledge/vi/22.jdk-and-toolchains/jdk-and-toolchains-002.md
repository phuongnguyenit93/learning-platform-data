# Java Toolchains và lựa chọn languageVersion trong Gradle

## 1. Tại sao cần Java Toolchains?

Một dự án Java có thể được xây trên máy chạy JDK 21, trong khi CI dùng JDK 17 và ứng dụng sau khi triển khai chỉ được phép chạy Java 17. Nếu không kiểm soát rõ JDK của các tác vụ, mã nguồn có thể vô tình dùng cú pháp/API Java quá mới, hoặc tạo bytecode không chạy được trên JVM đích.

**Java Toolchains** trong Gradle là cơ chế khai báo **yêu cầu đối với Java installation mà các tác vụ JVM cần sử dụng**. Thay vì hard-code đường dẫn `/opt/jdk-17/bin/javac`, bạn khai báo:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

Gradle sẽ tìm một installation phù hợp (JDK 17 khi cần compiler), từ các JDK được phát hiện trên máy hoặc một nguồn cấp phát JDK đã cấu hình. Các task như `JavaCompile`, `Test` và `Javadoc` của plugin JVM có hỗ trợ sẽ sử dụng công cụ từ toolchain được chọn.

Điểm quan trọng: **`languageVersion` chọn Java toolchain cho công việc build ứng dụng; nó không đồng nghĩa Java version của Gradle Daemon, Java trên `PATH` hoặc Java runtime trên server production.**

Bài học này đi qua các bước: hiểu bốn JVM/JDK context, cấu hình Groovy và Kotlin DSL, ví dụ Java 17 chạy được, task-level overrides, ràng buộc vendor, khác biệt `--release` với `sourceCompatibility`, auto-detection/provisioning, CI/multi-project, và quy trình debug có thể áp dụng thực tế.

## 2. Bốn tầng Java phải phân biệt

| Tầng | Nhiệm vụ | Nguồn chọn JVM/JDK |
| --- | --- | --- |
| **Gradle client/Launcher JVM** | Khởi động `gradlew` hoặc `gradle`, giao tiếp với daemon. | `JAVA_HOME`, Java trên PATH, hoặc IDE/launcher. |
| **Gradle Daemon JVM** | Chạy build scripts, plugins và Gradle build engine. | Daemon JVM criteria, `org.gradle.java.home`, JVM của client/Tooling API tùy môi trường. |
| **Project/task Java toolchain** | Chạy compiler, test JVM, JavaExec, Javadoc. | `java.toolchain.languageVersion` hoặc `javaToolchains.*For { ... }`. |
| **Production JVM** | Chạy ứng dụng đã phát hành trong container/server. | Runtime image/JDK/JRE được vận hành riêng, không do Gradle tự cài lên máy chủ production. |

Ví dụ hoàn toàn hợp lệ:

```text
Gradle Wrapper:           Gradle tương thích Java 21
Gradle Daemon:            JDK 21
java.toolchain:           JDK 17
compileJava:              javac của JDK 17
run/test:                 launcher Java 17
production Java runtime:  Java 17
```

Đồng thời có thể xảy ra lỗi nếu Gradle Wrapper **không chạy được** trên JVM của daemon, dù compiler toolchain phù hợp. Gradle phải chạy được trước khi nó lựa chọn toolchain cho các task.

### 2.1. JDK và JRE không giống nhau

- **JDK** có `javac`, `javadoc` và Java runtime. Task `JavaCompile` thường cần JDK.
- **JRE/runtime** có thể chạy Java nhưng thiếu compiler. Với `Test` hoặc `JavaExec`, Java launcher có thể là đủ, tùy yêu cầu Gradle/task.
- **Java toolchain** là mô tả lựa chọn các công cụ từ installation phù hợp; không phải một bản sao riêng của compiler được nhúng trong file `build.gradle`.
- **JavaLanguageVersion** biểu diễn major Java version như 17 hoặc 21, không biểu diễn patch version cụ thể như `17.0.10`.

Không hiểu nhầm “máy cài Java 17” với “Gradle phát hiện đúng JDK 17”. Cần kiểm tra toolchain list, vendor, location và `Is JDK`.

## 3. Cú pháp project-level Java Toolchain trong Kotlin DSL

**`build.gradle.kts`:**

```kotlin
plugins {
    id("java")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

- `id("java")` áp dụng core Java plugin và tạo `java` extension.
- `toolchain { ... }` quy định yêu cầu mặc định cho Java tasks.
- `JavaLanguageVersion.of(17)` chọn major version Java 17.
- `languageVersion.set(...)` là cú pháp Gradle Property API. Trong một số phiên bản tài liệu Kotlin DSL có thể dùng `languageVersion = JavaLanguageVersion.of(17)`; bản dùng `set` thể hiện rõ kiểu Property.

### 3.1. Dạng Groovy DSL tương đương

**`build.gradle`:**

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Groovy và Kotlin khác cú pháp nhưng cùng một ý nghĩa. Khi chuyển giữa DSL, không đưa dòng kiểu `id 'java'` vào file `*.gradle.kts`, hay nhầm cú pháp `.set(...)` với Java code.

### 3.2. Cấu hình có thể được áp dụng ở những project nào?

Java toolchains ở `java` extension thường có khi dùng `java`, `java-library`, `application` hoặc plugin JVM phù hợp. Nếu build không áp dụng plugin tạo `java` extension, Gradle có thể báo lỗi không tìm thấy `java` block.

Khi dùng Kotlin, Groovy, Scala hoặc Android plugin, **không giả định tất cả compiler/test tasks đều tự tuân theo cùng một Java toolchain property**. Hệ sinh thái này còn có Kotlin JVM target, Android compileOptions, task implementation riêng, và các ma trận hỗ trợ khác. Kiểm tra tài liệu plugin và Gradle Wrapper đang sử dụng.

## 4. languageVersion thực chất yêu cầu điều gì?

Với `JavaLanguageVersion.of(17)`, Gradle tìm Java installation thỏa **major version 17**. Nó không tự:

- Đặt `JAVA_HOME=17` cho cả hệ điều hành.
- Đổi JVM của Gradle Daemon đang chạy sang Java 17.
- Chọn chính xác JDK patch `17.0.x` trên mọi máy.
- Bắt mọi process do custom task tự tạo dùng Java 17.
- Đổi Docker runtime image thành Java 17.
- Tải JDK từ Internet khi chưa cấu hình toolchain download resolver/repository.

Ngược lại, project toolchain giúp Gradle điều khiển công cụ của các Java tasks có hỗ trợ và cung cấp thông tin đó cho caching/up-to-date checks khi plugin tích hợp đúng.

**Ví dụ:** Daemon chạy JDK 21 nhưng `compileJava` dùng compiler JDK 17 là chủ đích được hỗ trợ. Trong tình huống này, `System.getProperty("java.version")` trong build script có thể khác `Runtime.version().feature()` của chương trình Java được chạy bởi `JavaExec`.

## 5. Ví dụ runnable đầy đủ: Java 17 Application

Bài tập sau dùng Java 17 record, plugin `application` có sẵn của Gradle và **không cần dependency từ Internet**. Máy chỉ cần Gradle Wrapper hỗ trợ Java 17 cùng JDK 17 đã được phát hiện hoặc provision được theo chính sách.

### 5.1. Cây thư mục

```text
toolchain-lab/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    └── main/
        └── java/
            └── demo/
                └── Main.java
```

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "toolchain-lab"
```

**`build.gradle.kts`:**

```kotlin
plugins {
    id("application")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.Main")
}
```

**`src/main/java/demo/Main.java`:**

```java
package demo;

public record Main(String message) {
    public static void main(String[] args) {
        Main example = new Main("Hello from Java 17 toolchain");
        System.out.println(example.message());
        System.out.println("runtime.major=" + Runtime.version().feature());
    }
}
```

Đây là mã Java hợp lệ: `record` là một kiểu được hỗ trợ trong Java 17, có thể có `public static void main(String[] args)`. Tên file `Main.java`, package `demo` và `application.mainClass` khớp nhau.

### 5.2. Cách chạy

Tại root có Gradle Wrapper:

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew compileJava
./gradlew -q run
```

Khi project toolchain/launcher của `run` đúng Java 17, **stdout do chương trình in ra**:

```text
Hello from Java 17 toolchain
runtime.major=17
```

`./gradlew -q javaToolchains` cho danh sách JDK mà Gradle phát hiện, không có stdout cố định vì tùy máy. `./gradlew --version` cho thông tin Gradle/JVM, **không** đồng nghĩa compiler của `compileJava`.

Trên Windows dùng `gradlew.bat` hoặc `.\gradlew.bat`. Nếu tạo project từ đầu chưa có Gradle Wrapper, có thể dùng Gradle cài sẵn chạy `gradle wrapper` rồi dùng wrapper sau đó. Giữ các file Wrapper trong version control cho CI và mọi lập trình viên.

### 5.3. Groovy DSL chạy cùng Java source

Dùng **`settings.gradle`** thay Settings Kotlin:

```groovy
rootProject.name = 'toolchain-lab'
```

Dùng **`build.gradle`** thay build script Kotlin:

```groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.Main'
}
```

File `src/main/java/demo/Main.java` không thay đổi. Hai DSL là **hai lựa chọn thay thế**, không dán Groovy và Kotlin syntax vào cùng một build script. Với JDK/launcher 17, stdout của `run` vẫn là hai dòng ở trên.

### 5.4. javac/java thủ công so với Gradle

Nếu shell đang dùng đúng JDK 17, bạn có thể thử độc lập:

```bash
mkdir -p out
javac --release 17 -d out src/main/java/demo/Main.java
java -cp out demo.Main
```

Nếu lệnh `java` thực thi bằng JDK/JRE 17, kết quả cũng là:

```text
Hello from Java 17 toolchain
runtime.major=17
```

Nhưng khi PATH dùng Java 21, dòng thứ hai sẽ là `runtime.major=21` dù bạn đã biên dịch `--release 17`. `--release` kiểm soát output từ compiler, **không thay đổi lệnh `java` chọn runtime nào**. Với Gradle, toolchain/launcher của task giúp kiểm soát điều này tốt hơn.

## 6. JavaExec riêng với JavaLauncher từ toolchain

Khi một task JavaExec tự tạo phải chạy đúng Java 17, nên gắn `javaLauncher` một cách tường minh.

**Bổ sung vào `build.gradle.kts` của demo:**

```kotlin
tasks.register<JavaExec>("runWith17") {
    group = "verification"
    description = "Run demo on Java 17"

    mainClass.set("demo.Main")
    classpath = sourceSets["main"].runtimeClasspath

    javaLauncher.set(
        javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(17))
        }
    )
}
```

**Groovy:**

```groovy
tasks.register('runWith17', JavaExec) {
    group = 'verification'
    description = 'Run demo on Java 17'

    mainClass = 'demo.Main'
    classpath = sourceSets.main.runtimeClasspath

    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Chạy:

```bash
./gradlew -q runWith17
```

Stdout:

```text
Hello from Java 17 toolchain
runtime.major=17
```

`javaToolchains.launcherFor { ... }` trả `Provider<JavaLauncher>`. Gradle resolve Provider và chọn installation phù hợp khi cần. `classpath = sourceSets["main"].runtimeClasspath` đưa output của Java compilation và các runtime dependencies của source set vào JVM mới; `JavaExec` không tự chạy Gradle Daemon JVM.

**Không gọi `launcher.get()` tại cấp script chỉ để lấy absolute path**, khi property `javaLauncher` có thể nhận Provider. Tránh hard-code `C:\Program Files\Java\...` hoặc `/usr/lib/jvm/...` trong build script dùng chung nhiều máy.

## 7. JavaToolchainService: JavaCompiler, JavaLauncher, JavadocTool

| API Gradle | Kết quả | Tác vụ liên quan |
| --- | --- | --- |
| `javaToolchains.compilerFor { ... }` | `Provider<JavaCompiler>` | `JavaCompile.javaCompiler` |
| `javaToolchains.launcherFor { ... }` | `Provider<JavaLauncher>` | `Test.javaLauncher`, `JavaExec.javaLauncher` |
| `javaToolchains.javadocToolFor { ... }` | `Provider<JavadocTool>` | `Javadoc.javadocTool` |

### 7.1. Gán compiler cụ thể cho JavaCompile

**Kotlin DSL:**

```kotlin
tasks.withType<JavaCompile>().configureEach {
    javaCompiler.set(
        javaToolchains.compilerFor {
            languageVersion.set(JavaLanguageVersion.of(17))
        }
    )
}
```

**Groovy DSL:**

```groovy
tasks.withType(JavaCompile).configureEach {
    javaCompiler = javaToolchains.compilerFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Đây là task-level override. Với project thông thường, hãy cấu hình `java.toolchain` một lần và để Java plugin truyền thông số mặc định cho compile/test/Javadoc; chỉ override khi có lý do như compatibility testing hoặc nhiều JDK versions.

### 7.2. Gán launcher cho Test tasks

**Kotlin DSL:**

```kotlin
tasks.withType<Test>().configureEach {
    javaLauncher.set(
        javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(17))
        }
    )
}
```

**Groovy DSL:**

```groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Đoạn này chọn JVM thực thi test, **không tự bổ sung thư viện JUnit hoặc tạo test source**. Nếu muốn chạy JUnit Jupiter, còn cần framework dependencies và `useJUnitPlatform()`, ví dụ:

```kotlin
repositories {
    mavenCentral()
}
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
}
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
```

Snippet JUnit là mở rộng có điều kiện: Maven Central cần truy cập được, test classes phải hợp lệ và version JUnit/Gradle phải tương thích. Không nhầm lựa chọn toolchain của test với việc cấu hình test framework.

### 7.3. Dùng JavadocTool

**Kotlin:**

```kotlin
tasks.withType<Javadoc>().configureEach {
    javadocTool.set(
        javaToolchains.javadocToolFor {
            languageVersion.set(JavaLanguageVersion.of(17))
        }
    )
}
```

**Groovy:**

```groovy
tasks.withType(Javadoc).configureEach {
    javadocTool = javaToolchains.javadocToolFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Ví dụ này minh họa việc custom Javadoc tasks dùng JDK 17. Những task do Java plugin tạo thường đã dùng project toolchain; custom third-party tasks không nhất thiết được tích hợp tự động.

## 8. languageVersion là major version, không phải JDK patch

`JavaLanguageVersion.of(17)` nói “Java 17”, không nói “chỉ JDK 17.0.12 của vendor X”. Nếu nhiều JDK 17 thỏa mãn, Gradle lựa chọn một installation theo quy tắc precedence của Gradle version hiện tại.

### 8.1. Chọn vendor

**Kotlin:**

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
        vendor.set(JvmVendorSpec.ADOPTIUM)
    }
}
```

**Groovy:**

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
```

`JvmVendorSpec.ADOPTIUM` biểu thị yêu cầu vendor cụ thể. Có thể dùng `JvmVendorSpec.matching("...")` cho tên vendor không có constant được định nghĩa sẵn. Chỉ dùng vendor filter khi có yêu cầu tương thích/compliance; nếu CI có JDK 17 của vendor khác, filter có thể khiến Gradle báo không tìm được toolchain.

### 8.2. Chọn JVM implementation

Ví dụ riêng cho môi trường yêu cầu OpenJ9:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
        vendor.set(JvmVendorSpec.IBM)
        implementation.set(JvmImplementation.J9)
    }
}
```

Đây là **cấu hình ràng buộc đặc biệt**, không mặc định thích hợp cho mọi JDK 17. Cần một JDK implementation/vendor thỏa điều kiện. Nếu môi trường chỉ có HotSpot, build có thể fail khi không có matching toolchain.

### 8.3. Một JavaToolchainSpec phải hợp lệ

Đối với Gradle 8.0+ theo tài liệu API, toolchain spec hợp lệ nếu **trống hoàn toàn** hoặc có **languageVersion**, tùy chọn thêm vendor/implementation.

Ví dụ chỉ có vendor nhưng thiếu languageVersion là cấu hình không hợp lệ:

```kotlin
// Ví dụ lỗi, không đưa vào build thật:
java {
    toolchain {
        vendor.set(JvmVendorSpec.ADOPTIUM)
        // Thiếu languageVersion.
    }
}
```

Cách sửa: đặt `languageVersion.set(JavaLanguageVersion.of(17))` bên cạnh vendor. Điều này tránh một yêu cầu mơ hồ khi Gradle chọn JDK.

## 9. Auto-detection: Gradle tìm các JDK ở đâu?

Mặc định Gradle tìm Java installations từ nhiều nguồn tùy hệ điều hành, ví dụ:

- Thư mục cài JDK chuẩn trên Linux/macOS/Windows.
- `JAVA_HOME` hoặc các environment variables được cấu hình.
- Những trình quản lý JDK như SDKMAN!, asdf, Jabba (tùy platform/Gradle version).
- Một số Java installations của IDE.
- Các JDK trước đó đã được Gradle tải trong Gradle User Home.
- Những đường dẫn bổ sung từ Gradle properties.

Gradle **không chỉ dùng `java` trên PATH** khi bạn yêu cầu một toolchain. Nếu JDK chạy Daemon cũng thỏa điều kiện, Gradle có thể ưu tiên installation đó; nếu không, nó chọn từ các installations khác.

### 9.1. Xem danh sách toolchains thực tế

```bash
./gradlew -q javaToolchains
```

Bạn cần đọc: `Language Version`, `Vendor`, `Is JDK`, `Installation Path/Location`, `Detected by`, trạng thái auto-detection và auto-download. Output chi tiết không giống nhau giữa máy dev và CI; không dùng bản ví dụ trong tài liệu làm chuỗi cố định để so sánh từng ký tự.

### 9.2. Khai báo đường dẫn installations

Ví dụ trong `gradle.properties`:

```properties
org.gradle.java.installations.paths=/opt/jdks/jdk-17,/opt/jdks/jdk-21
```

Đây là **đường dẫn minh họa**. Nó phải trỏ đến Java installation có thật; Gradle xem các directories này như ứng viên và không tự tìm kiếm đệ quy sâu tùy ý. Nếu auto-detection vẫn bật, entries custom không được tự ưu tiên hơn các JDK khác chỉ vì được khai báo trước.

Nếu CI cung cấp biến môi trường trỏ tới JDK homes:

```properties
org.gradle.java.installations.fromEnv=JDK17_HOME,JDK21_HOME
```

Gradle dùng giá trị của những biến môi trường này (nếu có) làm nguồn tìm installations. Dòng này không tự đặt giá trị biến hoặc tải JDK.

### 9.3. Tắt auto-detection có mục đích

```properties
org.gradle.java.installations.auto-detect=false
```

Khi tắt, bạn phải cung cấp installation paths hoặc nguồn JDK phù hợp; nếu không `languageVersion=17` có thể không tìm được JDK, dù máy đã cài ở một thư mục mà Gradle không còn tự quét.

## 10. Auto-provisioning: thiếu JDK không có nghĩa tự tải được

Nếu không có installation phù hợp, Gradle có thể tự tải một JDK, **nhưng chỉ khi đã cấu hình toolchain download repositories/resolver**. Không phải mọi máy có Internet đều tự động tải JDK chỉ nhờ dòng `languageVersion.of(17)`.

### 10.1. Settings plugin cấp phát toolchain

Tài liệu Gradle hiện hành dùng Foojay resolver convention như một ví dụ. Khi tổ chức cho phép tải JDK từ nguồn đó, có thể cấu hình trong **Settings**:

**`settings.gradle.kts`:**

```kotlin
plugins {
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}

rootProject.name = "toolchain-lab"
```

**`settings.gradle` Groovy:**

```groovy
plugins {
    id 'org.gradle.toolchains.foojay-resolver-convention' version '1.0.0'
}

rootProject.name = 'toolchain-lab'
```

Đây là **external Settings plugin**. Plugin itself phải resolve được qua plugin repository; Gradle/JDK/network phải đáp ứng yêu cầu. Phiên bản `1.0.0` là ví dụ từ tài liệu Gradle, hãy kiểm tra tương thích với Wrapper hiện hành khi áp dụng vào dự án thật.

Các tổ chức có thể dùng **custom resolver plugin** để giới hạn JDK sources, policy và credentials. Với một JDK17 đã cài đúng trên máy, bài tập ở mục 5 không bắt buộc cần Foojay.

### 10.2. toolchainManagement khác repositories của project

`toolchainManagement { jvm { javaRepositories { ... } } }` trong Settings quản lý các resolver repositories cho **JDK installations**. Nó khác `pluginManagement.repositories` dùng tải Gradle plugin và khác `dependencyResolutionManagement.repositories` dùng tải Java libraries.

Một custom toolchain resolver có thể thiết lập `resolverClass` và authentication cho JDK downloads. Không thể thêm `mavenCentral()` vào `repositories` của project rồi coi như đã có Java 17 JDK download source.

### 10.3. Tắt auto-provisioning

`gradle.properties`:

```properties
org.gradle.java.installations.auto-download=false
```

Sau khi tắt, build yêu cầu local JDK đáp ứng spec. Lựa chọn này phù hợp CI kín mạng, nhưng team phải provision JDK trong runner/image trước.

Gradle auto-provisioning khi được cấu hình cũng **không phải công cụ tự cập nhật các bản vá JDK đã cài**. Nó thường tải một JDK khi không có local match và tái sử dụng installation trong Gradle User Home. Security patch/rotation cần một quy trình quản trị JDK riêng.

## 11. languageVersion và --release giải quyết hai câu hỏi khác nhau

`languageVersion` quyết định **compiler/JDK nào** được dùng. `options.release` quyết định **language level, class-file target và Java standard APIs** mà compiler được phép dùng.

| Cơ chế | Chọn compiler JDK? | Chọn bytecode/source target? | Hạn chế sử dụng JDK APIs mới hơn target? |
| --- | --- | --- | --- |
| `java.toolchain.languageVersion = 17` | Có, compiler của Java 17 nếu thỏa spec. | Mặc định thường tương ứng compiler/toolchain khi không override. | Không tự giả lập API của Java 11. |
| `options.release = 11` | Không. | Có, biên dịch theo `javac --release 11`. | Có, dùng Java 11 platform APIs tương thích. |
| `sourceCompatibility` | Không. | Ngôn ngữ source. | Không đủ. |
| `targetCompatibility` | Không. | Bytecode version. | Không đủ. |
| `JAVA_HOME` | Có thể ảnh hưởng Java chạy Gradle (không phải explicit toolchain). | Không tự kiểm soát toàn bộ task target. | Không. |

### 11.1. Compiler Java 17, bytecode Java 11

**Kotlin DSL — project Java riêng, không dùng source record Java 17 ở mục 5:**

```kotlin
plugins {
    id("java")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
}
```

**Groovy DSL:**

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 11
}
```

Gradle dùng compiler JDK 17 nhưng compile code theo `--release 11`. Code Java 17 record **không hợp lệ** trong project target Java 11, và việc build fail trong trường hợp này là kiểm soát compatibility đúng.

Một Java 11 source hợp lệ để thử riêng:

```java
package demo;

public final class Legacy {
    private Legacy() {
    }

    public static void main(String[] args) {
        System.out.println("  Gradle Java 11  ".strip());
    }
}
```

Lưu file thành `src/main/java/demo/Legacy.java` rồi kiểm tra trực tiếp bằng compiler JDK 17:

```bash
mkdir -p out
javac --release 11 -d out src/main/java/demo/Legacy.java
java -cp out demo.Legacy
```

Stdout với runtime Java 11 hoặc mới hơn:

```text
Gradle Java 11
```

`String.strip()` được bổ sung từ Java 11, nên phù hợp `--release 11`. Nếu thay bằng API chỉ có từ Java 17, compiler dùng `--release 11` sẽ từ chối dù `javac` thật sự được gọi từ JDK 17.

### 11.2. Vì sao sourceCompatibility/targetCompatibility không đủ?

Một build cũ có thể đặt:

```kotlin
java {
    sourceCompatibility = JavaVersion.VERSION_11
    targetCompatibility = JavaVersion.VERSION_11
}
```

Cách này điều khiển source/bytecode, nhưng nếu dùng compiler mới, mã có thể tham chiếu một API Java 17 không có trên Java 11 do platform classpath không được giới hạn đầy đủ. Chương trình sau đó có thể gặp `NoSuchMethodError` trên runtime Java 11. `--release` tránh rủi ro này bằng cách giới hạn Java platform APIs theo release đích.

**Lưu ý:** `JavaVersion.VERSION_11` (JavaVersion của Gradle) và `JavaLanguageVersion.of(11)` (Java toolchain spec) là những kiểu/cơ chế khác nhau.

### 11.3. Không yêu cầu release cao hơn compiler hỗ trợ

Nếu chỉ có toolchain compiler JDK17 nhưng đặt `options.release.set(21)`, javac17 không thể biên dịch release21. Gradle hoặc compiler sẽ báo lỗi như `release version 21 not supported`. Hãy dùng compiler JDK21+ hoặc hạ target theo requirements.

## 12. JDK chạy Gradle không phải JDK compile ứng dụng

`JAVA_HOME` và Java trên `PATH` thường ảnh hưởng JVM khởi động Gradle client. Gradle Daemon có thể chọn Java installation qua `org.gradle.java.home` hoặc **Daemon JVM criteria**. Nhưng project có toolchain 17 vẫn được phép dùng compiler/launcher Java17 ngay cả khi Daemon là Java21.

Để xem:

```bash
./gradlew --version
java -version
javac -version
./gradlew -q javaToolchains
```

- `./gradlew --version` nói về Gradle version/JVM của launcher/daemon theo output của phiên bản.
- `java -version` và `javac -version` là executable shell đang tìm thấy; không chắc cùng toolchain JavaCompile.
- `javaToolchains` liệt kê các Java installations mà Gradle biết, gồm cả installation ngoài PATH.
- `./gradlew compileJava --info` giúp quan sát lựa chọn compiler/task khi debug.

### 12.1. Daemon JVM criteria (Gradle hiện đại)

Gradle hỗ trợ một cơ chế riêng để chốt JVM chạy Daemon. Ở bản Gradle hỗ trợ, bạn có thể chạy:

```bash
./gradlew updateDaemonJvm --jvm-version=17
```

Task này tạo/cập nhật `gradle/gradle-daemon-jvm.properties`. Một số trường hợp cần cấu hình toolchain download repositories để sinh URLs; không dùng lệnh này như bước bắt buộc trong bài tập Java17 đơn giản.

Khi Daemon JVM criteria đã được cấu hình, Gradle có thể ưu tiên nó hơn `JAVA_HOME` và `org.gradle.java.home`. Nhưng nó **không** tự thay `options.release`/target của Java task, và chỉ có ở những Gradle versions hỗ trợ. Đọc tài liệu Daemon theo đúng Gradle Wrapper.

## 13. Chọn toolchains khác nhau trong multi-project build

Một Gradle multi-project build có thể có module `:lib` cần Java17 và `:app` dùng Java21.

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "multi-jdk-lab"
include(":lib", ":app")
```

**`lib/build.gradle.kts`:**

```kotlin
plugins {
    id("java-library")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

**`app/build.gradle.kts`:**

```kotlin
plugins {
    id("application")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

application {
    mainClass.set("demo.App")
}

dependencies {
    implementation(project(":lib"))
}
```

Đây là **mẫu cấu hình có điều kiện**, không phải một app hoàn chỉnh: phải có source `demo.App` và JDK21 nếu muốn chạy. App Java21 có thể tiêu thụ library được compile cho Java17 khi variant/bytecode/API tương thích. Chiều ngược lại không chắc đúng: app Java17 không thể chạy bytecode chỉ dành cho Java21 và Gradle variant matching có thể cảnh báo sớm.

### 13.1. Groovy DSL tương đương phần toolchain module

**`lib/build.gradle`:**

```groovy
plugins {
    id 'java-library'
}
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

**`app/build.gradle`:**

```groovy
plugins {
    id 'application'
}
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
application {
    mainClass = 'demo.App'
}
dependencies {
    implementation project(':lib')
}
```

Một build chỉ nên áp dụng shared convention toolchain nếu phù hợp với loại project. Không ép `java` extension vào subprojects không có Java plugin chỉ vì muốn thống nhất JDK trong repository.

## 14. Compile một lần, test trên nhiều Java runtimes

Một library compile theo Java17 có thể cần kiểm thử trên Java17 và Java21. Toolchain của Test task quyết định JVM chạy test, còn compiler target phải tương thích với JVM thấp nhất mà bạn muốn test.

Ví dụ custom Test task trên Java21 (**yêu cầu test classes và framework đã được cấu hình**):

**Kotlin DSL:**

```kotlin
tasks.register<Test>("testOn21") {
    group = "verification"
    testClassesDirs = sourceSets["test"].output.classesDirs
    classpath = sourceSets["test"].runtimeClasspath

    javaLauncher.set(
        javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(21))
        }
    )
    useJUnitPlatform()
}
```

**Groovy DSL:**

```groovy
tasks.register('testOn21', Test) {
    group = 'verification'
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
    useJUnitPlatform()
}
```

Nếu project có JUnit Jupiter dependencies và test source hợp lệ, chạy:

```bash
./gradlew test
./gradlew testOn21
```

Task `testOn21` yêu cầu Java21 launcher; task `test` mặc định dùng Java toolchain của project nếu đã áp dụng plugin tích hợp. **Không có stdout chính xác cố định** vì test framework và mã test khác nhau giữa dự án.

Đừng chỉ đổi `javaLauncher` sang Java17 nếu test classes đã compile với target Java21. Khi đó runtime17 có thể báo `UnsupportedClassVersionError`; phải kiểm soát `options.release`/compile toolchain trước.

## 15. Phiên bản Gradle và Java compatibility matrix

Mỗi Gradle version có ma trận tương thích khi **chạy Gradle** và khi **dùng Java toolchain để compile/test**. Đó là hai cột khác nhau. Tài liệu Gradle hiện hành có các mốc ví dụ:

| Java | Hỗ trợ toolchain từ | Chạy Gradle trên JVM này từ |
| --- | --- | --- |
| 17 | Gradle 7.3 | Gradle 7.3 |
| 21 | Gradle 8.4 | Gradle 8.5 |
| 25 | Gradle 9.1.0 | Gradle 9.1.0 |

Hãy xem [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html) gắn với đúng Wrapper, thay vì giả định bản Java mới nhất luôn chạy được với bản Gradle bất kỳ.

Ví dụ: một Gradle bản cũ có thể hỗ trợ Java21 làm **toolchain compile/test** trước khi hỗ trợ Java21 để **chạy Daemon**. Dùng `java.toolchain` không sửa được lỗi Gradle daemon runtime không tương thích. Nếu cần nâng JDK chạy Gradle, kiểm tra plugins và nâng Wrapper theo ma trận.

### 15.1. Java target thực tế của sản phẩm

Nếu sản phẩm chạy Java17 ở production:
- Dùng toolchain Java17 cho compiler/test hoặc compiler mới + `options.release=17`.
- Test bằng Java17 runtime, không chỉ JDK21.
- Kiểm tra transitive dependencies có bytecode tương thích Java17.
- Đừng dùng `--release 21` cho một artifact cần chạy trên Java17.
- Với thư viện multi-release JAR hoặc JNI/native modules, còn cần kiểm thử hành vi runtime thật.

## 16. CI, Docker và IDE

### 16.1. CI không có mạng tải JDK

Nếu CI runner chỉ có JDK21 mà build cần Java17 toolchain, có thể nhận lỗi no matching toolchain. Các lựa chọn hợp lệ:

1. Cài sẵn JDK17 trong runner/CI image.
2. Cung cấp installation paths hoặc environment variables (`org.gradle.java.installations.paths`/`fromEnv`).
3. Bật approved toolchain resolver/provisioning nếu mạng và chính sách tổ chức cho phép.
4. Không tùy tiện đổi `languageVersion=21` chỉ để qua lỗi nếu sản phẩm cần Java17.

Nếu tổ chức yêu cầu build hermetic, tắt auto-download sau khi đảm bảo toolchain local tồn tại.

### 16.2. Docker build và runtime là hai image khác nhau

Build stage có thể chạy Gradle/Java21 rồi compile bằng toolchain17; runtime stage vẫn phải dùng image Java phù hợp với bytecode/API của ứng dụng. Dòng `languageVersion.set(JavaLanguageVersion.of(17))` **không tự thay base image Docker thành Java17**.

### 16.3. IntelliJ IDEA, Eclipse và CLI

IDE có thể có **Project SDK**, **Gradle JVM** và thông tin toolchain được import từ Gradle build. Chúng không luôn trùng nhau. Khi IDE build khác CLI:

- Chọn Gradle Wrapper của repository.
- Kiểm tra Gradle JVM trong IDE và JDK chạy Gradle Daemon.
- Chạy Gradle task `javaToolchains`/`compileJava --info` từ IDE/terminal.
- Kiểm tra Java toolchain và Java target settings của đúng module.
- So sánh biến môi trường/paths/resolver giữa IDE và terminal.

## 17. Các lỗi thường gặp và cách chẩn đoán

| Lỗi/triệu chứng | Nguyên nhân có thể | Hướng sửa |
| --- | --- | --- |
| `No matching toolchains found` | Không phát hiện Java version/vendor/implementation yêu cầu. | Chạy `javaToolchains`; cài đúng JDK hoặc cấu hình resolver. |
| `toolchain download repositories have not been configured` | Thiếu toolchain resolver khi không có JDK local. | Provision JDK local hoặc cấu hình Settings toolchain resolver. |
| Chỉ phát hiện Java17 **JRE** | Không có `javac` cho compile task. | Cài Java17 JDK, xem `Is JDK`. |
| `Invalid JavaToolchainSpec` | Cấu hình vendor/implementation mà thiếu languageVersion. | Thêm `JavaLanguageVersion.of(...)`. |
| `error: release version 21 not supported` | Compiler JDK17 bị yêu cầu `--release 21`. | Dùng JDK21 compiler hoặc hạ release. |
| `record is not supported in -source 11` | Code Java17 nhưng `options.release=11`. | Chọn source phù hợp release hoặc chỉnh target có chủ đích. |
| `UnsupportedClassVersionError` | JVM runtime thấp hơn class-file version. | Compile với target thấp hơn hoặc nâng runtime tương thích. |
| `NoSuchMethodError` chỉ ở Java11 | Compile dùng API quá mới, source/target không giới hạn APIs. | Dùng `options.release` và test trên Java11. |
| `runtime.major=21` thay vì 17 | Task JavaExec/launcher không dùng Java17 toolchain. | Gán `javaLauncher` từ `javaToolchains.launcherFor`, xem plugin/task. |
| Gradle không chạy trên JDK mới | Wrapper không tương thích Java của daemon. | Kiểm tra `--version`/compatibility matrix, cập nhật Wrapper/JVM phù hợp. |
| JDK17 có trên máy nhưng Gradle không thấy | Auto-detection tắt, path sai hoặc vendor filter. | Kiểm tra `javaToolchains` và `fromEnv`/`paths`. |
| CI bị 401/403 hoặc không tải JDK | Resolver network/credentials/proxy/policy. | Dùng approved mirror, credentials, hoặc preinstalled JDK. |
| JavaCompile chạy đúng nhưng test fail JVM | `Test.javaLauncher`/target versions lệch nhau. | So sánh compiler release, Java launcher và runtime đích. |
| Sau đổi JDK Gradle vẫn dùng installation cũ | Daemon cache/env chưa cập nhật. | Kiểm tra output, cân nhắc `./gradlew --stop` rồi thử lại. |
| `JvmVendorSpec.ADOPTIUM` khiến build fail | Chỉ có JDK vendor khác. | Cài đúng vendor hoặc bỏ constraint nếu không cần. |
| Plugin Kotlin/Android target khác Java | Plugin có JVM target/compileOptions riêng. | Đồng bộ settings theo tài liệu plugin tương ứng. |

### 17.1. Checklist debug nhanh

1. Xác định lớp nào bị sai: launcher/daemon, compiler, test/JavaExec hay production JVM?
2. Xem `./gradlew --version` và compatibility matrix.
3. Chạy `./gradlew -q javaToolchains`, kiểm tra vendor/location/version và `Is JDK`.
4. Xác định `languageVersion` trong đúng module và mọi override `javaCompiler`/`javaLauncher`.
5. Xem `options.release`, `sourceCompatibility`/`targetCompatibility` nếu phải hỗ trợ runtime cũ.
6. Chạy `./gradlew compileJava --info` và task JavaExec/test.
7. Nếu thiếu JDK, xem `toolchainManagement`/resolver, các Java installations paths và CI image.
8. Chạy ứng dụng trên JVM production tối thiểu; kiểm tra bytecode/API và dependencies.
9. Ghi lại JDK/Wrapper/policy đã chọn trong tài liệu nhóm và CI.

## 18. Hướng dẫn áp dụng cho dự án thật

- **Ưu tiên project-level toolchain** khi project Java cần một major JDK xác định.
- **Chọn major theo yêu cầu runtime và API**, không theo JDK mới nhất có trên laptop.
- **Dùng `options.release` cho strict compatibility** với Java runtime thấp hơn compiler.
- **Dùng `javaCompiler`/`javaLauncher`/`javadocTool` provider** khi task riêng cần override, không ghép path Java executable bằng chuỗi thủ công.
- **Không cố định vendor/implementation trừ khi thật sự cần**, và không xem major toolchain là pin patch security.
- **Phân biệt Gradle Daemon JVM criteria với Java toolchain**; quản trị cả hai khi cần build tái lập.
- **Dùng Wrapper trong CI**, kiểm tra compatibility matrix và plugins trước nâng version.
- **Với mạng bị hạn chế**, chuẩn bị JDK trước, không trông chờ auto-download ngầm.
- **Tránh ép resolve toolchain sớm** ở configuration time; cho Gradle dùng Property/Provider và task inputs.
- **Kiểm thử runtime cuối cùng**, bao gồm Docker image, Java versions và transitive dependencies.
- **Tôn trọng các plugin JVM khác**: Kotlin, Android, Scala có thể yêu cầu cấu hình target tương ứng.

## 19. Bảng tra nhanh

| Mục tiêu | Cú pháp/công cụ |
| --- | --- |
| Chọn JDK17 cho Java plugin | `java { toolchain { languageVersion.set(JavaLanguageVersion.of(17)) } }` |
| Groovy tương đương | `java { toolchain { languageVersion = JavaLanguageVersion.of(17) } }` |
| Chọn compiler cho task | `javaToolchains.compilerFor { languageVersion.set(JavaLanguageVersion.of(17)) }` |
| Chọn runtime JavaExec/Test | `javaToolchains.launcherFor { languageVersion.set(JavaLanguageVersion.of(17)) }` |
| Chọn Javadoc tool | `javaToolchains.javadocToolFor { languageVersion.set(JavaLanguageVersion.of(17)) }` |
| Dùng compiler17, API/bytecode Java11 | `java.toolchain = 17` + `options.release.set(11)` |
| Chọn vendor | `vendor.set(JvmVendorSpec.ADOPTIUM)` kèm languageVersion |
| Xem danh sách JDK | `./gradlew -q javaToolchains` |
| Xem JVM chạy Gradle | `./gradlew --version` |
| Khai báo JDK locations | `org.gradle.java.installations.paths=...` |
| Đọc environment JDK homes | `org.gradle.java.installations.fromEnv=JDK17_HOME,JDK21_HOME` |
| Tắt auto detection | `org.gradle.java.installations.auto-detect=false` |
| Tắt auto JDK download | `org.gradle.java.installations.auto-download=false` |
| Bật auto JDK download | Áp dụng Settings resolver plugin như Foojay (theo policy) |
| Chốt Gradle Daemon JDK | Daemon JVM criteria/`org.gradle.java.home`; khác `java.toolchain` |
| Chẩn đoán compile | `./gradlew compileJava --info` |
| Biết JVM thực thi mã Java | `Runtime.version().feature()` trong ứng dụng |

**Kết luận:** `languageVersion` trong `java.toolchain` yêu cầu Gradle chọn công cụ Java theo major version cho những Java tasks hỗ trợ toolchains. Nó không phải `JAVA_HOME`, không tự điều khiển JVM của Gradle Daemon, không pin patch version, không biến compiler Java17 thành Java11, và không đảm bảo tự tải JDK nếu thiếu resolver. Kết hợp **Java Toolchains + `options.release` + test trên production runtime + Gradle Wrapper** là cách quản lý Java version rõ ràng giữa laptop, IDE, CI và production.

### Nguồn tham khảo chính thức

- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): cấu hình project/task, compiler/launcher, vendor, detection/provisioning.
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): phiên bản Java cho toolchain và chạy Gradle.
- [Gradle — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): Java plugin và các phương pháp chọn Java version.
- [Gradle — Gradle Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html): launcher JVM, daemon JVM và Daemon JVM criteria.
- [Gradle — Build Environment](https://docs.gradle.org/current/userguide/build_environment.html): `org.gradle.java.home` và properties liên quan đến Java installations.
- [Gradle — JavaToolchainService API](https://docs.gradle.org/current/javadoc/org/gradle/jvm/toolchain/JavaToolchainService.html): JavaCompiler, JavaLauncher, JavadocTool và Provider APIs.
