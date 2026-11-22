# Application distribution, start scripts, installDist và distZip trong Gradle

## 1. Vì sao một file JAR chưa chắc là một ứng dụng có thể giao cho người dùng?

Một project Java có thể biên dịch thành công, chạy được qua Gradle và tạo một file `.jar`. Tuy nhiên, khi mang JAR đó sang máy khác, người dùng còn cần biết:

- **Class `main`** nào phải được chạy và Java runtime nào cần có?
- Những **JAR phụ thuộc ở runtime** nằm ở đâu, có tương thích không?
- Classpath và các JVM options cần được thiết lập như thế nào?
- Người dùng Linux/macOS và Windows có thể khởi chạy bằng lệnh nào?
- Những file bổ sung (hướng dẫn, license, cấu hình mẫu) đi kèm bản phát hành ở đâu?
- Có cách nào đóng gói thành **một archive ZIP/TAR có cấu trúc ổn định** để phân phối và kiểm tra trên CI không?

Gradle **Application plugin** giải quyết một phần quan trọng của bài toán: tạo bản phân phối ứng dụng JVM bao gồm **launcher scripts, JAR của ứng dụng, các runtime dependencies và tài liệu/file bổ sung**. Những task then chốt là `run`, `startScripts`, `installDist`, `distZip`, `distTar` và `assembleDist`.

**Bản phân phối (application distribution)** không đồng nghĩa với việc đóng gói Java runtime vào ZIP và cũng không mặc định tạo native executable. Một bản phân phối tiêu chuẩn của Application plugin cần JVM phù hợp trên máy đích để chạy scripts.

### 1.1. Phân biệt các khái niệm

| Khái niệm | Kết quả chính | Dùng khi nào? |
| --- | --- | --- |
| `jar` | JAR chứa bytecode và resources của project | Thư viện hoặc thành phần ứng dụng |
| `run` | Chạy ứng dụng ngay trong Gradle bằng `JavaExec` | Phát triển/kiểm tra nhanh |
| `startScripts` | Sinh launcher cho Unix và Windows | Chuẩn bị cách chạy ứng dụng sau khi đóng gói |
| `installDist` | Dựng thư mục phân phối chưa nén | Chạy thử bản đã lắp đặt, staging nội bộ |
| `distZip` | Tạo archive ZIP chứa bản phân phối | Gửi artifact cho người dùng/CI/deploy |
| `distTar` | Tạo archive TAR chứa bản phân phối | Các quy trình phân phối qua TAR |
| `assembleDist` | Yêu cầu tạo cả ZIP và TAR của main distribution | Muốn hai định dạng trong một lệnh |
| `assemble` | Lifecycle task tạo những artifact đã cấu hình, thường bao gồm archives của distribution | Đóng gói nhiều đầu ra |
| `build` | Lifecycle task kết hợp đóng gói và kiểm tra theo plugins áp dụng | Build tổng hợp |
| `check` | Lifecycle task tập trung verification | Chạy test/kiểm tra mà không chủ đích tạo mọi archive |

Một JAR có thể được dùng bởi cả `distZip` và `installDist`, nhưng **không phải mọi JAR đều tự chạy được bằng `java -jar`**. Việc có `Main-Class` trong manifest và toàn bộ runtime dependencies là vấn đề khác. Launcher scripts của Application plugin giúp thiết lập entry point và classpath cho bản phân phối.

## 2. Application plugin kết hợp với Java và Distribution plugin

Áp dụng Application plugin bằng Kotlin DSL:

```kotlin
plugins {
    application
}

application {
    mainClass.set("demo.Main")
}
```

Groovy DSL tương đương:

```groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.Main'
}
```

Application plugin tự áp dụng **Java plugin** và **Distribution plugin**, vì vậy build có các source sets Java mặc định cùng những task đóng gói distribution.

`mainClass` là cấu hình bắt buộc về entry point: tên lớp có phương thức `public static void main(String[] args)` (hoặc entry point được Java/Gradle hỗ trợ theo cấu hình tương ứng).

Ví dụ class Java 17:

```java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Hello, Gradle!");
    }
}
```

Lớp trong package `demo` phải ở file `src/main/java/demo/Main.java` với fully qualified class name `demo.Main`. Đặt `mainClass.set("Main")` cho source có `package demo;` có thể làm lỗi khởi chạy vì không tìm đúng class.

### 2.1. Những phần Application plugin tự cấu hình

Với cách bố trí Java thông thường:

- `src/main/java`: source Java của ứng dụng.
- `src/main/resources`: resource nằm trên classpath của ứng dụng.
- `src/test/java` và `src/test/resources`: source/resource cho test.
- `src/dist`: file bổ sung được Application/Distribution plugin đưa vào **root của bản phân phối**.
- `lib` bên trong distribution: application JAR và các runtime dependency JAR.
- `bin` bên trong distribution: các start scripts Unix/Windows.

Ứng dụng có thể sử dụng các source sets khác, Java Module System hoặc plugin khác; khi đó nội dung distribution và classpath/module path cần được xem theo cấu hình thực tế. Ở bài này dùng **classpath application truyền thống** để học cơ chế cốt lõi trước.

## 3. Hình dáng một application distribution

Với project `distribution-demo`, version `1.0.0`, bản ZIP thường có cấu trúc tương đương:

```text
distribution-demo-1.0.0/
├── bin/
│   ├── distribution-demo
│   └── distribution-demo.bat
├── lib/
│   ├── distribution-demo-1.0.0.jar
│   └── commons-lang3-3.14.0.jar
├── README.txt
└── conf/
    └── example.properties
```

Ý nghĩa:

- `bin/distribution-demo`: script chạy trên hệ Unix-like (Linux/macOS).
- `bin/distribution-demo.bat`: batch script dành cho Windows.
- `lib/distribution-demo-1.0.0.jar`: JAR chứa classes/resources của ứng dụng.
- `lib/commons-lang3-3.14.0.jar`: dependency bên ngoài cần ở runtime trong ví dụ.
- `README.txt` và `conf/example.properties`: file tĩnh lấy từ `src/dist` của dự án.

Đây là **sơ đồ minh họa cho project sẽ xây ở mục 7**, không phải danh sách chính xác của mọi distribution. Khi có thêm runtime dependencies, `lib` có thể chứa nhiều JAR. Tên archive/scripts phụ thuộc `project.name`, `project.version`, `applicationName` và các tùy chỉnh distributions.

### 3.1. Source resources và distribution files khác nhau

| Nguồn | Đích thường gặp | Vai trò |
| --- | --- | --- |
| `src/main/java` | Class trong application JAR | Mã thực thi |
| `src/main/resources` | Resources trong application JAR | Dữ liệu lấy từ classpath Java |
| `src/dist/README.txt` | `README.txt` ở root bản distribution | Hướng dẫn cài/chạy |
| `src/dist/conf/example.properties` | `conf/example.properties` ở root distribution | Cấu hình mẫu nằm ngoài JAR |
| `implementation(...)`/`runtimeOnly(...)` | Những JAR tương ứng trong `lib` nếu cần ở runtime | Thư viện khi chạy |
| `src/test/java`/`testImplementation(...)` | Test outputs/classpath riêng | Không mặc định là nội dung chính của distribution |

Một file `src/dist/conf/example.properties` **không tự xuất hiện trên Java classpath**. Muốn chương trình đọc nó, cần thiết kế đường dẫn file hệ thống hoặc cơ chế chỉ định file cấu hình riêng. Trong ví dụ, đây là tài liệu cấu hình mẫu cho người vận hành, không được chương trình tự tải.

### 3.2. Distribution không bao gồm JRE/JDK theo mặc định

Dù project cấu hình:

```kotlin
java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}
```

điều đó **chọn JDK phục vụ các task Java của build**, không có nghĩa ZIP đã mang theo một JVM 17. Người dùng cần runtime tương thích trên máy đích, hoặc dự án phải dùng giải pháp bổ sung như `jlink`/`jpackage`, container image hoặc công cụ tạo runtime image theo nhu cầu cụ thể.

## 4. Các task quan trọng và quan hệ phụ thuộc

Theo Application plugin, các task tiêu biểu:

| Task | Kiểu task | Phụ thuộc/ý định nổi bật | Đầu ra |
| --- | --- | --- | --- |
| `run` | `JavaExec` | Cần classes của main source set | Chạy một Java process |
| `startScripts` | `CreateStartScripts` | Cần metadata/classpath ứng dụng, thường nối với `jar` | Sinh launcher Unix/Windows |
| `installDist` | `Sync` | Cần application JAR và start scripts | Thư mục phân phối đã lắp đặt |
| `distZip` | `Zip` | Cần application JAR và start scripts | ZIP của main distribution |
| `distTar` | `Tar` | Cần application JAR và start scripts | TAR của main distribution |
| `assembleDist` | Lifecycle task | Phụ thuộc `distZip` và `distTar` | Cả hai archive |
| `assemble` | Lifecycle task | Bao gồm distribution archives do Distribution plugin nối | Các artifact được cấu hình |
| `build` | Lifecycle task | Thường yêu cầu `assemble` và `check` | Build + verification |

Mô hình:

```text
                  source Java + resources
                             |
                             v
                   compileJava / classes
                             |
                +------------+-------------+
                |                          |
                v                          v
               run                        jar
                                           |
                                           v
                                      startScripts
                                           |
                      +--------------------+-------------------+
                      |                    |                   |
                      v                    v                   v
                  installDist            distZip             distTar
                                           \                  /
                                            \                /
                                             v              v
                                               assembleDist
```

Đây là sơ đồ **khái niệm**, không cố định trình tự mọi task: Gradle xác định dependencies từ plugin và có thể thực thi một số công việc độc lập song song. Nếu task `UP-TO-DATE` hoặc `FROM-CACHE`, Gradle có thể không chạy lại action, miễn là outputs hợp lệ.

### 4.1. `run` không phải `installDist`

`./gradlew run` là cách chạy nhanh từ Gradle, sử dụng các output/classes và runtime classpath do build quản lý. Nó **không buộc** phải tạo ZIP hoặc install distribution.

`./gradlew installDist` là cách xây dựng **một thư mục phân phối giống bản giao cho người dùng**, gồm scripts và JAR dependencies. Sau đó ta chạy **script trong thư mục install** để kiểm tra bản phân phối thực tế.

Vì vậy cần thử cả hai khi đóng gói ứng dụng: chạy được với `run` chưa chắc archive đúng (ví dụ thiếu runtime JAR hoặc extra file bị đặt sai path).

### 4.2. `distZip` khác `distTar` ở định dạng đóng gói

`distZip` tạo ZIP, tiện chia sẻ đa nền tảng. `distTar` tạo TAR, thường dùng trong môi trường Unix/tooling tương ứng. Cả hai lấy nội dung từ cùng main distribution specification, nên về ý tưởng có cùng scripts/libs/extra files, nhưng archive metadata, quyền file, quy tắc giải nén và công cụ xử lý có thể khác.

Đừng nghĩ `distZip` và `distTar` tạo **một file với hai extension**; chúng là hai archive artifacts riêng với format/metadata khác.

### 4.3. `assembleDist` và `assemble`

`assembleDist` được Distribution plugin tạo để gom `distZip` cùng `distTar` của main distribution. `assemble` là lifecycle task của build, và Distribution plugin nối các archive tasks của distributions vào đó. Vì thế trên Java Application build thông thường, chạy:

```bash
./gradlew assemble
```

có thể tạo **cả ZIP và TAR**, không chỉ ứng dụng JAR. Nếu CI chỉ muốn một ZIP để upload, dùng `distZip` trực tiếp thay vì mặc định `assemble` rồi phải lọc artifact.

Ngược lại, `check` chạy verification tasks nhưng không chủ đích yêu cầu tạo mọi distribution archive; có thể tách job test và job package một cách rõ ràng.

## 5. Generated start scripts hoạt động ra sao?

Task `startScripts` tạo hai launcher scripts cho ứng dụng. Chúng được thiết kế để tìm application home/distribution layout, dựng classpath từ JAR và thư viện trong `lib`, rồi gọi JVM với main class đã cấu hình.

Đây là lý do có thể chuyển **cả thư mục distribution** sang máy khác rồi chạy script mà không cần cài Gradle tại đó.

### 5.1. Unix launcher và Windows launcher

Ví dụ đường chạy sau `installDist`:

```bash
./build/install/distribution-demo/bin/distribution-demo gradle
```

Windows PowerShell:

```powershell
.\build\install\distribution-demo\bin\distribution-demo.bat gradle
```

Hai script được sinh theo môi trường hệ điều hành; không phải Java source code. Chúng có thể thiết lập classpath, JVM options, command-line args và đường dẫn `APP_HOME` tương đối.

Nếu chỉ copy riêng `bin/distribution-demo` mà bỏ thư mục `lib`, application có thể fail do không tìm được main class hoặc thư viện. **Giữ nguyên cấu trúc tương đối `bin` và `lib`** khi phân phối.

### 5.2. `applicationDefaultJvmArgs` và `JAVA_OPTS`

Cấu hình:

```kotlin
application {
    mainClass.set("demo.Main")
    applicationDefaultJvmArgs = listOf("-Ddemo.channel=demo")
}
```

`applicationDefaultJvmArgs` cung cấp JVM options cho **`run` và generated start scripts**. Trong ví dụ, ứng dụng có thể đọc:

```java
String channel = System.getProperty("demo.channel", "unset");
```

Các scripts còn hỗ trợ cách thêm JVM options ở runtime, ví dụ qua `JAVA_OPTS` hoặc biến environment mang tên ứng dụng. Những biến này phục vụ **JVM flags**, khác với **application arguments** truyền sau tên script.

### 5.3. Biến môi trường dành riêng cho ứng dụng

Application plugin hỗ trợ biến environment dạng **`<APPLICATION_NAME>_OPTS`** (chuyển tên ứng dụng thành chữ hoa, các ký tự không phải chữ/số thành `_`). Với application name `distribution-demo`, tên tương ứng là:

```text
DISTRIBUTION_DEMO_OPTS
```

Ví dụ Linux/macOS:

```bash
export DISTRIBUTION_DEMO_OPTS="-Xmx512m"
./build/install/distribution-demo/bin/distribution-demo gradle
```

Cấu hình bổ sung `-Xmx512m` ảnh hưởng giới hạn heap JVM, không phải tham số `args[0]` của `Main.main`. Các options này bổ sung vào options mặc định của scripts.

**Bảo mật:** tránh đưa mật khẩu/token vào JVM `-Dsecret=...`, `JAVA_OPTS` hoặc command line nếu không cần; chúng có thể xuất hiện qua process listing, logs, crash dumps hay chính script cấu hình. Với secret, dùng cơ chế runtime injection/secret manager có kiểm soát.

### 5.4. `--args` chỉ dành cho `run`

Khi chạy bằng Gradle:

```bash
./gradlew run --args="gradle"
```

`--args` là tùy chọn của task `run`/`JavaExec` để truyền **application arguments**.

Khi chạy script đã cài:

```bash
./build/install/distribution-demo/bin/distribution-demo gradle
```

ta truyền trực tiếp `gradle` cho launcher, **không** viết `--args="gradle"` trừ khi chính ứng dụng định nghĩa tùy chọn có tên đó.

### 5.5. Tùy chỉnh sâu templates cần kiểm tra hai hệ điều hành

`CreateStartScripts` hỗ trợ tùy chỉnh scripts và script generators/templates. Đây là điểm mở rộng mạnh nhưng cũng dễ gây lỗi quoting, khoảng trắng trong đường dẫn, Windows batch escaping và cách lấy classpath.

Nên bắt đầu từ scripts mặc định và chỉ chỉnh khi có yêu cầu thực. Nếu override template, bắt buộc kiểm thử cả Unix và Windows, truyền args có dấu cách, thư mục install có khoảng trắng và JVM options trên máy đích.

## 6. Nguồn file ngoài JAR: `src/dist` và `distributions { main { contents { ... } } }`

Application plugin tạo một distribution tên **`main`**. Các file trong `src/dist` được đưa vào **root của distribution**, không phải tự động đóng thành classpath resource.

Ví dụ:

```text
src/dist/
├── README.txt
└── conf/
    └── example.properties
```

Sau `installDist`:

```text
build/install/distribution-demo/
├── README.txt
└── conf/example.properties
```

bên cạnh `bin` và `lib`.

### 6.1. Tùy chỉnh bằng CopySpec của main distribution

Kotlin DSL minh họa:

```kotlin
distributions {
    main {
        contents {
            from("legal") {
                into("legal")
            }
        }
    }
}
```

Khi project có thư mục `legal`, nội dung của thư mục đó được copy vào `legal` ở root distribution. Đoạn này có thể nằm trong `build.gradle.kts` của project đã áp dụng `application`.

Groovy DSL tương ứng:

```groovy
distributions {
    main {
        contents {
            from('legal') {
                into 'legal'
            }
        }
    }
}
```

Không cần dùng `from("src/dist")` để thêm lại toàn bộ nội dung nếu Application plugin đã cấu hình thư mục đó. Đừng thêm cùng một file hai lần rồi tìm cách “chữa” bằng `duplicatesStrategy = INCLUDE` một cách tùy tiện: ZIP có thể chứa các entries trùng, và consumer sẽ gặp hành vi khó dự đoán.

### 6.2. Dữ liệu được tạo bởi task khác

Có thể thêm tài liệu sinh tự động vào distribution nếu khai báo dependency/outputs đúng, ví dụ Kotlin DSL minh họa:

```kotlin
val generateInfo = tasks.register("generateInfo") {
    val outputDir = layout.buildDirectory.dir("generated-distribution-info")
    outputs.dir(outputDir)

    doLast {
        val directory = outputDir.get().asFile
        directory.mkdirs()
        directory.resolve("build-info.txt").writeText("Distribution example")
    }
}

distributions {
    main {
        contents {
            from(generateInfo) {
                into("docs")
            }
        }
    }
}
```

Khi `from(taskProvider)` được dùng theo Gradle CopySpec với task có output files, Gradle có thể thiết lập dependency trên task tạo output để archive/install nhận dữ liệu đã sinh. Đối với build production, nên định nghĩa task type có input/output annotations phù hợp; đây chỉ là ví dụ ngắn cho quan hệ task producer → distribution content.

**Không** tạo file ngay trong `src/dist` bằng các action không khai báo đúng rồi kỳ vọng Gradle tự luôn biết nó thay đổi. Với nội dung sinh tự động, tốt hơn tạo dưới `build/` và kết nối output qua provider/task.

## 7. Ví dụ hoàn chỉnh Java 17: từ `run` đến ZIP có thể phân phối

Bây giờ tạo một ứng dụng có dependency ngoài thật (`commons-lang3`), JUnit 5 test, JVM option mặc định và hai file distribution extras. Mục tiêu:

- `run` và scripts đều chạy cùng class `demo.Main`.
- JAR ứng dụng và `commons-lang3` nằm trong thư mục `lib`.
- `README.txt`/`conf/example.properties` có mặt ở root distribution.
- `installDist` cho phép thử bản phân phối không nén.
- `distZip` tạo archive có cấu trúc như sản phẩm giao cho người dùng.
- `check` có test thực và có thể được CI chạy trước khi upload archive.

### 7.1. Cây thư mục

```text
distribution-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── src/
│   ├── main/
│   │   └── java/
│   │       └── demo/
│   │           └── Main.java
│   ├── test/
│   │   └── java/
│   │       └── demo/
│   │           └── MainTest.java
│   └── dist/
│       ├── README.txt
│       └── conf/
│           └── example.properties
└── gradle/wrapper/...  (được tạo nếu sử dụng Wrapper)
```

Không cần tạo thư mục `build/` từ đầu. Gradle sẽ sinh output khi tasks được chạy. Trong ví dụ này, tên project `distribution-demo` cũng chính là application name mặc định và distribution base name mặc định.

### 7.2. Settings

**File `settings.gradle.kts`:**

```kotlin
rootProject.name = "distribution-demo"
```

Đặt tên cố định giúp dự đoán tên scripts và archive của ví dụ. Nếu tổ chức sử dụng một tên project khác, kiểm tra tên output thực tế thay vì sao chép đường dẫn một cách máy móc.

### 7.3. Build script

**File `build.gradle.kts`:**

```kotlin
plugins {
    application
}

group = "demo"
version = "1.0.0"

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")

    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.10.2")
}

application {
    mainClass.set("demo.Main")
    applicationDefaultJvmArgs = listOf("-Ddemo.channel=demo")
}

tasks.test {
    useJUnitPlatform()
}
```

Giải thích:

- `application` đồng thời áp dụng Java và Distribution plugins; không cần liệt kê lại `java` và `distribution`.
- `version = "1.0.0"` giúp tạo artifact names ổn định cho bài thực hành.
- `toolchain.languageVersion = 17` dùng compiler JDK 17 khi Gradle tìm được JDK phù hợp; **không** đóng gói JDK 17 vào ZIP.
- `implementation("...commons-lang3...")` cần ở runtime và được đưa vào distribution `lib` cùng application JAR.
- `testImplementation` và `testRuntimeOnly` chỉ phục vụ test classpath, không tự trở thành runtime dependencies của ứng dụng.
- `applicationDefaultJvmArgs` được sử dụng khi `run` và scripts khởi chạy ứng dụng; tham số `demo.channel` là một giá trị minh họa không nhạy cảm.
- `tasks.test { useJUnitPlatform() }` giúp `test` chạy JUnit Jupiter.

### 7.4. Mã Java có thể chạy

**File `src/main/java/demo/Main.java`:**

```java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static String greeting(String name) {
        return "Hello, " + StringUtils.capitalize(name) + "!";
    }

    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "world";
        String channel = System.getProperty("demo.channel", "unset");

        System.out.println(greeting(name));
        System.out.println("Channel: " + channel);
    }
}
```

Cách chạy mặc định không có argument sẽ chào `World`; nếu truyền argument `gradle`, `StringUtils.capitalize` đổi chữ đầu thành `Gradle`. Chương trình đọc JVM system property `demo.channel` do `applicationDefaultJvmArgs` thiết lập.

**File `src/test/java/demo/MainTest.java`:**

```java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

final class MainTest {
    @Test
    void producesGreeting() {
        assertEquals("Hello, Gradle!", Main.greeting("gradle"));
        assertEquals("Hello, World!", Main.greeting("world"));
    }
}
```

Test kiểm tra logic tạo lời chào, không cần ghi đè `System.out`. Nó không kiểm chứng trực tiếp nội dung ZIP; phần đó sẽ được kiểm tra bằng `installDist`/`distZip`.

### 7.5. Distribution extras

**File `src/dist/README.txt`:**

```text
Distribution Demo 1.0.0

Unix/Linux/macOS:
  bin/distribution-demo gradle

Windows:
  bin\distribution-demo.bat gradle

Requires a compatible Java runtime (Java 17 for this sample).
```

**File `src/dist/conf/example.properties`:**

```properties
app.mode=example
app.docs=https://example.org/docs
```

`example.properties` chỉ là **mẫu cấu hình công khai**, không chứa secret. Ứng dụng ví dụ **không tự đọc file này**; nó sử dụng JVM property `demo.channel`. Nếu ứng dụng thật cần đọc file bên ngoài, phải viết cơ chế đọc đường dẫn rõ ràng và có hướng dẫn về working directory/permissions.

### 7.6. Chạy bản development

Nếu project đã có Gradle Wrapper, sử dụng Wrapper. Nếu chỉ mới tạo các file trên, cần có Gradle tương thích cài sẵn để tạo Wrapper một lần:

```bash
gradle wrapper
```

Sau đó, trên Linux/macOS:

```bash
./gradlew --version
./gradlew --quiet run --args="gradle"
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat --quiet run --args="gradle"
```

Khi dependency resolution, toolchain và compilation thành công, **stdout do `Main.main` in**:

```text
Hello, Gradle!
Channel: demo
```

Đây là stdout của chương trình, không phải cam kết log Gradle/Wrapper từ mọi máy chỉ có hai dòng. Lần đầu có thể cần mạng để tải Maven modules hoặc Gradle distribution, phụ thuộc cache.

### 7.7. Chạy test và đối chiếu với `run`

```bash
./gradlew test --console=plain
```

Test `producesGreeting` cần thành công. JUnit reports thường nằm dưới:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

Task `run` không phải một bài kiểm tra tự động toàn diện; một app có thể chạy với một input nhưng fail với các input khác. CI nên chạy `check`/`test` trước khi chấp nhận bản ZIP.

## 8. Task `startScripts`: sinh launcher trước khi install/archive

Chạy:

```bash
./gradlew startScripts --console=plain
```

Trong layout Application plugin thông thường, task sinh scripts dưới `build/scripts`:

```text
build/scripts/
├── distribution-demo
└── distribution-demo.bat
```

Đây là **output trung gian của task `startScripts`**, chưa phải thư mục distribution hoàn chỉnh. Nó chưa chứa `lib` hoặc `README.txt` để người dùng cuối mang đi chạy.

Kiểm tra scripts theo hệ điều hành:

```bash
ls build/scripts
```

PowerShell:

```powershell
Get-ChildItem build\scripts
```

Có thể mở file bằng text editor để xem launcher thiết lập Java command/classpath từ application metadata. **Không sửa trực tiếp file trong `build/scripts` để tùy biến lâu dài**: Gradle có thể tạo lại và ghi đè output khi task chạy lần sau. Hãy sửa ở `build.gradle.kts`, Application extension hoặc cấu hình `CreateStartScripts` chính thức.

### 8.1. Lỗi nếu main class sai

Trong bản sao project, đổi:

```kotlin
application {
    mainClass.set("demo.DoesNotExist")
}
```

Task `startScripts` có thể **vẫn tạo ra scripts**: nó không nhất thiết load main class để kiểm tra tồn tại. Nhưng khi chạy script, Java sẽ báo không tìm thấy entry point class. Điều đó cho thấy **sinh launcher thành công chưa đồng nghĩa application chạy thành công**.

Khôi phục `mainClass.set("demo.Main")` rồi chạy `installDist` và chạy thực tế.

### 8.2. Lỗi nếu chỉ copy scripts

Dù script được sinh đúng, nó vẫn cần application JAR và dependency JAR phù hợp trong `lib`. Chỉ upload `build/scripts/distribution-demo` lên server thường không đủ. Hãy phân phối **cả distribution** thay vì một file script lẻ.

## 9. Task `installDist`: lắp đặt bản chưa nén để test như người dùng

Chạy:

```bash
./gradlew installDist --console=plain
```

Với tên project `distribution-demo` và cấu hình mặc định của ví dụ, Gradle dựng thư mục:

```text
build/install/distribution-demo/
├── bin/
│   ├── distribution-demo
│   └── distribution-demo.bat
├── lib/
│   ├── distribution-demo-1.0.0.jar
│   └── commons-lang3-3.14.0.jar
├── README.txt
└── conf/
    └── example.properties
```

Đường dẫn install mặc định dựa trên tên main distribution/project; khi đã tùy chỉnh distributions, base name hoặc install task destination, cần dùng path thực tế.

### 9.1. Chạy từ distribution đã được install

Linux/macOS:

```bash
./build/install/distribution-demo/bin/distribution-demo gradle
```

Windows PowerShell:

```powershell
.\build\install\distribution-demo\bin\distribution-demo.bat gradle
```

Stdout mong đợi:

```text
Hello, Gradle!
Channel: demo
```

Quan trọng: đây **không phải lệnh `./gradlew run`**. Nó thực sự khởi chạy generated script và classpath từ thư mục distribution, giúp phát hiện các lỗi đóng gói mà task `run` có thể không bộc lộ.

### 9.2. Vì sao `installDist` là `Sync`?

Task install dùng cơ chế `Sync` để đưa các file distribution vào một thư mục đích đồng bộ. Những file cũ không còn trong nguồn có thể bị xóa khỏi destination khi sync.

**Hệ quả vận hành:** mặc định cài dưới `build/install` là phù hợp để dựng bản thử. Nếu tùy biến destination sang thư mục dùng chung hoặc một thư mục trên máy production, cần cực kỳ cẩn thận: một task `Sync` có thể xóa file không còn thuộc bản phân phối. Không trỏ tùy tiện `installDist` tới nơi chứa dữ liệu người dùng, log hoặc file cấu hình runtime cần giữ lại.

### 9.3. Kiểm tra file bổ sung

Linux/macOS:

```bash
cat build/install/distribution-demo/README.txt
cat build/install/distribution-demo/conf/example.properties
```

Windows PowerShell:

```powershell
Get-Content build\install\distribution-demo\README.txt
Get-Content build\install\distribution-demo\conf\example.properties
```

Nếu không thấy file, kiểm tra `src/dist` có đúng tên/path, plugin `application` được áp dụng và không có rules `exclude` hoặc CopySpec thay đổi cấu trúc.

## 10. Task `distZip`: đóng gói bản phát hành

Chạy:

```bash
./gradlew distZip --console=plain
```

Với project `distribution-demo` version `1.0.0` không sửa archive base name, file ZIP mặc định thường nằm ở:

```text
build/distributions/distribution-demo-1.0.0.zip
```

Bên trong ZIP là **thư mục root có tên/version của distribution**, chứa `bin`, `lib`, `README.txt` và `conf`.

### 10.1. Xem ZIP mà không giải nén

Vì đang dùng JDK 17, có thể dùng lệnh `jar tf` để liệt kê ZIP:

```bash
jar tf build/distributions/distribution-demo-1.0.0.zip
```

Các đường dẫn quan trọng cần thấy trong output:

```text
distribution-demo-1.0.0/bin/distribution-demo
distribution-demo-1.0.0/bin/distribution-demo.bat
distribution-demo-1.0.0/lib/distribution-demo-1.0.0.jar
distribution-demo-1.0.0/lib/commons-lang3-3.14.0.jar
distribution-demo-1.0.0/README.txt
distribution-demo-1.0.0/conf/example.properties
```

Đây là **các entry cần kiểm chứng**, không phải toàn bộ output/entry ordering bắt buộc: ZIP có thể chứa các thư mục entries và metadata khác. Nếu plugin/Gradle đổi tên archive hoặc dùng thêm dependency, danh sách thực có thể dài hơn.

Nếu `jar` trên PATH là JDK khác nhưng vẫn hỗ trợ đọc ZIP, công cụ có thể liệt kê file; hãy kiểm tra `jar --help` và JDK cài trên máy khi cần.

### 10.2. Giải nén và chạy như người nhận

Linux/macOS với `unzip` đã cài:

```bash
mkdir -p staging
unzip -q build/distributions/distribution-demo-1.0.0.zip -d staging
./staging/distribution-demo-1.0.0/bin/distribution-demo gradle
```

Stdout của app:

```text
Hello, Gradle!
Channel: demo
```

Windows PowerShell:

```powershell
Expand-Archive -Path build\distributions\distribution-demo-1.0.0.zip -DestinationPath staging
.\staging\distribution-demo-1.0.0\bin\distribution-demo.bat gradle
```

Nếu chạy Unix script gặp lỗi permission sau khi giải nén bằng công cụ không bảo toàn executable flag, kiểm tra quyền và dùng `chmod +x` cho script đã xác nhận nguồn trước khi thực thi. Đừng dùng `chmod -R 777` hoặc tắt chính sách bảo vệ hệ thống chỉ để vượt lỗi permissions.

### 10.3. ZIP không phải installer và không phải fat JAR

Một ZIP distribution khác:

- **Installer GUI/OS package:** có thể cần MSI, DEB, RPM hoặc công cụ riêng.
- **Native executable:** cần cơ chế đóng gói runtime/launcher đặc thù.
- **Fat/uber JAR:** gộp dependency classes vào một JAR; Distribution plugin mặc định dùng nhiều JAR trong `lib`.
- **Container image:** chứa filesystem layers và runtime/container configuration, thường do Docker/OCI tooling tạo.

Với ứng dụng JVM truyền thống, ZIP distribution cung cấp cách giao **một gói có cấu trúc chạy được**, mà không cần đóng tất cả dependencies vào một JAR. Nó vẫn cần Java runtime được hỗ trợ trên máy đích.

## 11. Task `distTar` và `assembleDist`

`distTar` tạo TAR của main distribution:

```bash
./gradlew distTar --console=plain
```

Một file tương ứng thường nằm dưới `build/distributions`, ví dụ:

```text
build/distributions/distribution-demo-1.0.0.tar
```

Có thể liệt kê với công cụ tar tương thích:

```bash
tar -tf build/distributions/distribution-demo-1.0.0.tar
```

`assembleDist` yêu cầu cả ZIP và TAR:

```bash
./gradlew assembleDist --console=plain
```

Khi chỉ cần ZIP, `distZip` thường tiết kiệm công việc đóng gói hơn. Khi cần cả hai format để phát hành, `assembleDist` hoặc `assemble` phù hợp hơn.

### 11.1. Khi chạy `assemble` và `build`

Application plugin kéo theo Distribution plugin và các archive tasks được nối vào lifecycle `assemble`. Vì vậy với project này, `./gradlew assemble` có thể tạo cả application JAR, ZIP và TAR; `./gradlew build` còn bao gồm verification tasks qua `check`.

Không suy ra `distZip` tự chạy `test`: `distZip` cần artifacts và launcher, nhưng **không mặc định là quality gate**. Một pipeline tốt nên chạy:

```bash
./gradlew clean check distZip --console=plain
```

Lệnh trên yêu cầu verification và tạo ZIP trong một invocation. CI phải dựa vào exit code để chặn upload nếu bước chất lượng thất bại, đồng thời có thể lưu test reports theo policy.

## 12. Đổi tên ứng dụng và thư mục scripts

Application plugin cung cấp các thuộc tính như `applicationName` và `executableDir`.

### 12.1. `applicationName`

Kotlin DSL:

```kotlin
application {
    mainClass.set("demo.Main")
    applicationName = "greeter"
}
```

Groovy DSL:

```groovy
application {
    mainClass = 'demo.Main'
    applicationName = 'greeter'
}
```

`applicationName` mặc định là `project.name`. Khi đổi, generated scripts thường có tên mới, ví dụ `greeter` và `greeter.bat`. Biến environment ứng dụng cũng đổi thành `GREETER_OPTS`.

**Không áp dụng đoạn này vào project thực hành ở mục 7 nếu còn dùng đường dẫn cũ `bin/distribution-demo`.** Đây là một phương án tùy chỉnh riêng; sau khi đổi app name, phải kiểm tra output scripts và archive/distribution naming mà Gradle thực tạo.

### 12.2. `executableDir`

Kotlin DSL:

```kotlin
application {
    executableDir = "scripts"
}
```

Khi cấu hình như vậy, launcher được đặt dưới `scripts` trong distribution thay vì `bin`. Tất cả hướng dẫn vận hành phải đổi tương ứng, ví dụ:

```text
.../scripts/distribution-demo
.../scripts/distribution-demo.bat
```

Không nhầm `executableDir` với `src/main/java` hoặc thư mục output của compiled classes. Nó là **đường dẫn launcher bên trong distribution**.

### 12.3. `applicationDefaultJvmArgs`

Kotlin DSL:

```kotlin
application {
    applicationDefaultJvmArgs = listOf(
        "-Xmx256m",
        "-Ddemo.channel=demo"
    )
}
```

Đây là các JVM flags mặc định được đưa vào `run` và start scripts. Đừng đặt credential nhạy cảm trực tiếp trong `applicationDefaultJvmArgs` vì generated scripts có thể chứa cờ đó. Các giá trị nhạy cảm nên được cấp ở runtime qua cơ chế được quản lý.

## 13. Thêm một named distribution khác

Distribution plugin cho phép nhiều distributions. Ví dụ project đã áp dụng `application` và muốn có một gói riêng chứa tài liệu vận hành:

```kotlin
distributions {
    create("ops") {
        contents {
            from("operations") {
                into("operations")
            }
        }
    }
}
```

Các task bổ sung có thể là:

- `opsDistZip`: ZIP của distribution `ops`.
- `opsDistTar`: TAR của distribution `ops`.
- `assembleOpsDist`: tạo cả ZIP và TAR.
- `installOpsDist`: dựng thư mục install riêng.

**Quan trọng:** một named distribution mới không tự được mặc định cấu hình giống hệt Application plugin `main` distribution. Nếu muốn gói `ops` cũng có application JAR/start scripts/runtime libraries, phải thêm/định nghĩa content một cách chủ đích. Đoạn trên chỉ minh họa một gói tài liệu, không phải một launcher đầy đủ thứ hai.

Tên archive của distribution phụ như `ops` thường chứa cả project name và distribution name, ví dụ `distribution-demo-ops-1.0.0.zip`. Khi đã custom distributionBaseName hoặc archive naming, cần dùng output thực tế.

### 13.1. Khi nào nên dùng distribution phụ?

Ví dụ:

- Gói tài liệu offline hoặc sample config riêng.
- Gói scripts triển khai khác bản application.
- Gói công cụ vận hành cho một nhóm người dùng khác.
- Gói tài nguyên không nên đưa vào ZIP chạy ứng dụng.

Nếu chỉ cần thêm `README.txt` hoặc `conf/example.properties` vào main distribution, dùng `src/dist`/`distributions.main.contents` đơn giản hơn việc tạo distribution mới.

## 14. Runtime dependencies được đưa vào `lib` như thế nào?

Khi sử dụng Application plugin, main distribution lấy **runtime dependencies** của application cùng JAR đã build để đưa vào `lib`.

Ví dụ:

```kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
```

Thư viện này được cần cả lúc compile và chạy, nên hiện diện trong runtime classpath/distribution.

Nếu một dependency chỉ cần khi chạy, có thể dùng:

```kotlin
dependencies {
    runtimeOnly("org.example:runtime-adapter:1.0.0")
}
```

Đây là **tọa độ minh họa**, không xác nhận artifact giả đó tồn tại trong repository. `runtimeOnly` có nghĩa là dependency được thêm vào runtime classpath chứ không phải compile classpath. Để thực hành, giữ dependency `commons-lang3` thật trong ví dụ.

Ngược lại:

```kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
}
```

được dùng cho test, không mặc định sao chép vào main application distribution chỉ vì nó tồn tại trong build. Khi JUnit không phải runtime dependency của app, file JUnit không cần xuất hiện trong `lib` của bản phân phối.

### 14.1. Project dependencies trong multi-project

Nếu ứng dụng `:app` phụ thuộc project thư viện nội bộ `:core`:

```kotlin
dependencies {
    implementation(project(":core"))
}
```

Gradle sử dụng variant/output phù hợp của `:core` để tạo runtime classpath. Distribution của `:app` cần mang theo những JAR/output phù hợp ở runtime, nếu Application plugin và các project được cấu hình đúng. Đừng copy thủ công vài class files từ `:core` vào `src/dist/lib` khi project dependencies đã biểu đạt quan hệ producer–consumer.

Ví dụ này là **mảnh cấu hình trong multi-project đã include `:core`**, không phải áp dụng vào project một module của mục 7.

### 14.2. Xung đột JAR names hoặc runtime versions

Nếu `lib` chứa các JAR có class trùng nhau, version không tương thích hoặc hai artifact cùng tên gây collision, launcher có thể chạy sai hoặc build distribution fail. Hãy kiểm tra `runtimeClasspath` bằng:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
```

Không nên giải quyết classpath conflict bằng cách đặt ngẫu nhiên các JAR vào `src/dist/lib`. Gradle dependency resolution, constraints/platform/locking và phiên bản được chọn mới là nơi cần xử lý quan hệ dependency.

### 14.3. Vì sao `java -jar` không đủ trong nhiều trường hợp?

`./gradlew jar` tạo application JAR. Nhưng:

- JAR thường không tự bao gồm các third-party runtime dependencies.
- Manifest `Main-Class` không nhất thiết đã được cấu hình theo ý định chạy trực tiếp.
- JVM cần classpath/module path đúng.
- JVM options/args có thể cần cấu hình.

Vì vậy, `java -jar build/libs/distribution-demo-1.0.0.jar` **không phải phép thử tương đương** với generated start script. Với ví dụ có commons-lang3, ngay cả khi JAR có main manifest, chạy riêng JAR mà không cung cấp dependency có thể gặp `NoClassDefFoundError`. Hãy thử `installDist` hoặc ZIP đã giải nén để kiểm tra gói phân phối đúng nghĩa.

## 15. Kiểm tra sự tương thích Java trên máy đích

Với ứng dụng Java 17 trong ví dụ:

- Java toolchain 17 được dùng để compile.
- Output classes có thể yêu cầu runtime Java 17, trừ khi cấu hình release target thấp hơn rõ ràng và code/dependencies tương thích.
- ZIP chứa start scripts và JAR, **không chứa JVM** theo mặc định.
- Generated script sẽ tìm JVM trên máy đích theo cấu hình/biến môi trường/`PATH` tùy script.

Nếu người dùng có Java 11 nhưng application JAR biên dịch cho Java 17, có thể gặp `UnsupportedClassVersionError`. Không sửa lỗi đó bằng cách chỉ đổi `executableDir` hoặc chạy `distZip` lại: phải chọn đúng Java baseline/runtime hoặc biên dịch với target phù hợp.

### 15.1. Kiểm tra JVM trước khi chạy distribution

Linux/macOS:

```bash
java -version
./build/install/distribution-demo/bin/distribution-demo gradle
```

PowerShell:

```powershell
java -version
.\build\install\distribution-demo\bin\distribution-demo.bat gradle
```

Nếu `java -version` ở terminal khác JVM script chọn qua `JAVA_HOME` hoặc script environment, hãy kiểm tra `JAVA_HOME` và việc script thực thi. Đừng suy ra “build bằng JDK 17” chứng minh máy deploy có Java 17.

### 15.2. Distribution và Docker image

Khi tạo container image, có thể đưa distribution ZIP hoặc thư mục đã install vào image **có Java runtime phù hợp**. Nhưng Application plugin **không tự build Docker image**; đó là công việc Docker/OCI tooling hoặc plugin khác. Phải kiểm tra user permissions, executable flags, layer caching, secret injection và CVE của runtime image riêng.

### 15.3. Java Module System

Nếu ứng dụng có `module-info.java` và dùng module path, Application plugin có hỗ trợ mô hình modular application với `mainModule` phù hợp. Đây là một nhánh triển khai khác với classpath demo. Không chép tùy tiện `mainModule` khi project chưa có module descriptor; cần kiểm tra tên module, exports/requires và quy tắc reflective access. Launcher Java modular có thể đòi runtime flags khác; kiểm thử distribution trên máy đích.

## 16. Reproducible archives và phân phối qua CI

Một mục tiêu quan trọng là cùng source/dependency/configuration tạo được distribution đáng tin và kiểm tra được.

### 16.1. Cố định version đầu ra

Trong ví dụ:

```kotlin
version = "1.0.0"
```

Version giúp tên artifact có thể dự đoán và phân biệt release. Đừng nhúng trực tiếp timestamp ngẫu nhiên hoặc đường dẫn cá nhân vào JAR/resources/scripts nếu muốn byte-for-byte reproducibility.

### 16.2. Cấu hình reproducible archive metadata

Mảnh Kotlin DSL thường dùng với archive tasks:

```kotlin
tasks.withType<org.gradle.api.tasks.bundling.AbstractArchiveTask>()
    .configureEach {
        isPreserveFileTimestamps = false
        isReproducibleFileOrder = true
    }
```

Đây là **mảnh bổ sung tùy chọn** để kiểm soát timestamps và file ordering trong archives theo API của Gradle. Nó không tự đảm bảo mọi byte giống nhau nếu có metadata động, nội dung sinh không ổn định, nguồn dependency thay đổi hoặc plugin chèn timestamp khác.

Kiểm tra `SHA-256`/checksum trên CI khi cần bảo đảm artifact không bị thay đổi giữa các bước. Cũng cần kiểm soát dependency versions, repository, toolchain và Gradle Wrapper để tăng tính tái lập.

### 16.3. Quy trình CI đề xuất

Lệnh trên Linux/macOS:

```bash
./gradlew --version
./gradlew clean check distZip --console=plain
jar tf build/distributions/distribution-demo-1.0.0.zip
```

Sau đó pipeline có thể:

1. Xác minh task `test` và quality checks thực sự chạy/đạt.
2. Kiểm tra ZIP chứa `bin`, `lib`, các tài liệu bắt buộc.
3. Giải nén ZIP ở thư mục sạch và chạy launcher bằng Java runtime chuẩn.
4. Kiểm tra stdout/exit code và log lỗi có ý nghĩa.
5. Tạo SHA-256/checksum và lưu với artifact.
6. Upload **ZIP đã kiểm tra** vào artifact repository hoặc release storage.
7. Đảm bảo người deploy tải đúng artifact hash, không tự build lại từ môi trường khác.
8. Không upload toàn bộ workspace nếu có file nhạy cảm hoặc dữ liệu test riêng.

**Bước `distZip` không tự kiểm chứng test.** CI nên yêu cầu `check` riêng hoặc chạy `build` khi phù hợp; nếu chỉ chạy `distZip`, một build có thể tạo archive dù unit tests chưa được yêu cầu chạy.

### 16.4. Vì sao không nên build lại cho từng môi trường?

Một chiến lược là **build once, deploy many**:

```text
Source + reviewed dependencies
            |
            v
        Gradle check
            |
            v
         distZip
            |
            v
  immutable ZIP + checksum
      /             \
     v               v
  Staging         Production
  runtime         runtime
  config          config
```

Cấu hình nhạy cảm (DB password, access tokens, private keys) nên được cấp ở **runtime**, không dùng `src/dist` hoặc `applicationDefaultJvmArgs` để đóng gói secret vào ZIP. Một archive có thể bị upload, cache, sao chép và truy cập bởi nhiều người hơn máy deploy.

## 17. Bảo mật distribution và quyền file

Distribution artifacts thường có quyền đọc rộng hơn secret store. Những file không nên đưa vào `src/dist` hoặc distribution:

```text
src/dist/.env
src/dist/credentials.json
src/dist/private.key
src/dist/conf/application-prod-with-password.properties
src/dist/secret-token.txt
```

Nếu có dữ liệu nhạy cảm trong ZIP, đổi tên file hoặc nén không làm nó an toàn. Người nhận có thể giải nén và đọc nội dung. Nên:

- Chỉ đóng gói cấu hình mẫu **không chứa credential**.
- Kiểm tra contents bằng `jar tf` và scan file đã render.
- Đặt token ở runtime environment, secret manager hoặc volume được quản lý.
- Không đưa secret vào `applicationDefaultJvmArgs` hoặc viết thẳng vào scripts.
- Không upload test fixtures chứa credential thật.
- Giới hạn artifact retention và quyền tải bản release.
- Nếu đã lộ secret, cần rotate/revoke và xử lý các bản archive/log/cache đã phát hành; chỉ xóa bản local là chưa đủ.

### 17.1. Đường dẫn có dấu cách và tên file đặc biệt

Generated scripts thường xử lý các đường dẫn tương đối và các trường hợp đường dẫn có dấu cách tốt hơn script tùy viết vội. Tuy nhiên, mọi tùy chỉnh thủ công có thể làm hỏng quoting.

Trong CI, nên thử cài distribution vào đường dẫn có dấu cách trên Windows và Unix-like nếu sản phẩm phục vụ cả hai hệ điều hành. Không hardcode `/home/user/app/lib` hoặc `C:\app\lib` trong script được phân phối đa nền tảng.

### 17.2. Quyền executable trên Unix

Unix launcher cần quyền thực thi thích hợp sau khi giải nén/copy. Công cụ ZIP/TAR và hệ điều hành có thể xử lý permission metadata khác nhau. Nếu `Permission denied`, kiểm tra quyền thực thi và nguồn archive. Không đặt quyền quá rộng cho cả thư mục `lib` hoặc file config chỉ để chạy được một script.

## 18. Lỗi phổ biến khi dùng Application distribution

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `Task 'run' not found` | Chưa áp dụng `application` ở đúng project | Kiểm tra `plugins` và project path |
| `No main class specified` | `application.mainClass` thiếu hoặc rỗng | Cấu hình fully qualified class name |
| `ClassNotFoundException: demo.Main` | Package/class name sai hoặc JAR thiếu class | Kiểm tra `src/main/java`, `jar tf` |
| `NoClassDefFoundError: StringUtils` | Thiếu runtime JAR hoặc phân phối bị copy thiếu `lib` | Xem `runtimeClasspath` và distribution `lib` |
| `run` chạy được nhưng installed script lỗi | Script/classpath/extras/working dir khác cách chạy Gradle | Kiểm tra `installDist` và launcher |
| `startScripts` thành công nhưng ứng dụng không chạy | Generator không luôn xác minh main class có tồn tại | Chạy thật sau `installDist` |
| Script báo `JAVA_HOME is set to an invalid directory` | Máy đích cấu hình `JAVA_HOME` sai | Sửa runtime environment/JDK path |
| `UnsupportedClassVersionError` | JVM đích quá cũ so với bytecode | Cung cấp Java runtime phù hợp hoặc đổi Java baseline |
| `Permission denied` khi chạy script Unix | Thiếu executable bit sau giải nén/copy | Kiểm tra chmod/permissions và tool archive |
| `distZip` có JAR nhưng thiếu README | File không nằm `src/dist` hoặc CopySpec sai | Kiểm tra source/path và `jar tf ZIP` |
| App không tự đọc `conf/example.properties` | File distribution extra không tự là resource trên classpath | Viết runtime config reader rõ ràng |
| `installDist` xóa file có sẵn ở destination | `Sync` đồng bộ thư mục và loại file ngoài nguồn | Không trỏ destination tới thư mục dữ liệu |
| `distZip` tạo thành công nhưng test fail khi chạy riêng | Packaging không tự là verification gate | CI chạy `check` trước publish |
| Script có tên khác `distribution-demo` | `applicationName` hoặc project name đổi | Kiểm tra output `build/scripts`/`bin` |
| Script nằm ngoài `bin` | `executableDir` đã được tùy chỉnh | Kiểm tra application extension |
| `distZip` có hai bản cùng thư viện | Đưa JAR thủ công vào `src/dist/lib` và dependency runtime | Loại cách copy trùng, dùng dependency graph |
| ZIP và TAR khác nội dung kỳ vọng | Customization/chế độ lọc/permissions khác | So sánh danh sách entries của hai archive |
| `distZip` tạo sai tên archive so với CI | Project/version/archive base name đã đổi | Đọc `build/distributions` thay vì hardcode ngầm |
| `check` không chạy khi chỉ gọi `distZip` | `distZip` thiên về packaging, không phải quality gate | Yêu cầu `check` trong pipeline |
| Build quá chậm vì tạo cả ZIP/TAR | Gọi `assemble`/`build` khi chỉ cần một archive | Dùng `distZip` riêng sau `check` |
| Windows script dùng đường dẫn sai | Quoting hoặc script template custom hỏng | Thử trên Windows, phục hồi default template |
| Thư viện Java 21 nằm trong distribution Java 17 | Dependency JVM target không tương thích | Xem runtime graph/variant/Java baseline |
| File cấu hình bí mật lộ trong ZIP | Vô tình đưa vào `src/dist` hay CopySpec | Rotate secret, thu hồi artifact và sửa pipeline |

## 19. Quy trình debug theo từng bước

### 19.1. Xác nhận project và task names

```bash
./gradlew tasks --all
./gradlew help --task startScripts
./gradlew help --task installDist
./gradlew help --task distZip
```

Nếu là multi-project, dùng đường dẫn task đầy đủ như `:app:distZip`, `:app:installDist`. Không mặc định chạy root task mà project con chưa được áp dụng plugin.

### 19.2. Xem graph mà chưa thực thi

```bash
./gradlew distZip --dry-run --console=plain
```

`--dry-run` cho biết kế hoạch tasks, nhưng không tạo ZIP hoặc xác nhận launcher chạy đúng. Không dùng `--dry-run` như một cách kiểm thử sản phẩm đóng gói.

### 19.3. Thử bước nhỏ nhất gây lỗi

```bash
./gradlew compileJava --console=plain
./gradlew jar --console=plain
./gradlew startScripts --console=plain
./gradlew installDist --console=plain
./gradlew distZip --console=plain
```

Nếu `compileJava` lỗi: kiểm tra JDK/toolchain/source. Nếu `startScripts` lỗi: kiểm tra `mainClass`, Application extension và metadata/task settings. Nếu `installDist` lỗi: kiểm tra CopySpec/destination/file collisions. Nếu `distZip` lỗi: kiểm tra file paths, duplicate entries/permissions/archive settings.

### 19.4. Kiểm tra runtime dependencies

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
```

Lệnh này giúp biết version module thật sự được chọn và có sẵn trong runtime graph. File nằm ở `testRuntimeClasspath` nhưng không nằm `runtimeClasspath` không nhất thiết xuất hiện trong distribution.

### 19.5. Chạy bản đã được install và giải nén

Đây là bước không thể thay bằng việc `./gradlew run` thành công. Cần chạy cả:

```bash
./build/install/distribution-demo/bin/distribution-demo gradle
./staging/distribution-demo-1.0.0/bin/distribution-demo gradle
```

chỉ sau khi đã tạo `installDist` và giải nén ZIP như mục 9–10. Nếu installed version chạy nhưng unpacked version không chạy, nghi ngờ quyền file, cách giải nén hoặc nội dung archive.

## 20. Bài tập thực hành

**Bài tập A — mapping nhiệm vụ.** Gán các nhu cầu “chạy trong Gradle”, “sinh launcher”, “dựng thư mục chưa nén”, “gói ZIP”, “gói TAR”, “tạo cả hai archives” tương ứng với `run`, `startScripts`, `installDist`, `distZip`, `distTar`, `assembleDist`.

**Bài tập B — xây ví dụ Java 17.** Tạo file mục 7, chạy `./gradlew --quiet run --args="gradle"`. Giải thích vì sao output gồm `Hello, Gradle!` và `Channel: demo`.

**Bài tập C — kiểm tra launcher.** Chạy `startScripts`, mở hai file trong `build/scripts`, xác định tên application, Java command, classpath và JVM flags. Vì sao chỉ copy file Unix script chưa phải một bản phân phối hoàn chỉnh?

**Bài tập D — install.** Chạy `installDist`, kiểm tra `bin` và `lib`, rồi chạy script. So sánh output của script với `run`. Khi nào hai cách chạy có thể khác nhau?

**Bài tập E — ZIP.** Chạy `distZip`, dùng `jar tf` kiểm tra có application JAR, commons-lang3 JAR, hai launcher scripts và hai file extras. Giải nén ở thư mục sạch và chạy.

**Bài tập F — TAR.** Chạy `distTar` rồi liệt kê entries bằng `tar -tf`. So sánh nội dung với ZIP và khác biệt khi bảo toàn file permissions.

**Bài tập G — thay `applicationName`.** Đặt `applicationName = "greeter"` trong bản sao rồi xây lại scripts/distribution. Xác định script names mới và biến environment `GREETER_OPTS`. Cập nhật README phân phối theo tên thực tế.

**Bài tập H — tùy chỉnh `executableDir`.** Đặt `executableDir = "scripts"`, tạo lại `installDist`. Vì sao hướng dẫn `bin/distribution-demo` cũ không còn đúng?

**Bài tập I — thêm extra files.** Tạo thư mục `legal` với license và dùng `distributions.main.contents.from(...)` để đặt vào `legal` bên trong distribution. Kiểm tra cả ZIP và installDir.

**Bài tập J — sai main class.** Tạm đổi `mainClass` sang `demo.DoesNotExist` và chạy `startScripts`, sau đó chạy launcher. Giải thích vì sao việc có script không chứng minh app chạy thành công. Khôi phục đúng `demo.Main`.

**Bài tập K — thiếu runtime dependency.** Trong bản sao archive đã giải nén, tạm di chuyển commons-lang3 JAR ra ngoài `lib` và chạy launcher. Tại sao ứng dụng có thể báo `NoClassDefFoundError` dù application JAR vẫn tồn tại? Khôi phục JAR sau thử nghiệm.

**Bài tập L — kiểm thử CI.** Thiết kế pipeline chạy `check`, `distZip`, kiểm tra ZIP contents, giải nén chạy smoke test, tạo checksum và upload artifact chỉ khi bước bắt buộc đạt.

**Bài tập M — bảo mật.** Có người muốn đặt `APP_API_TOKEN` vào `src/dist/conf/prod.properties`. Hãy nêu ít nhất bốn nơi token có thể xuất hiện sau khi release và thiết kế thay thế bằng runtime injection.

**Bài tập N — distribution phụ.** Tạo `ops` distribution chỉ chứa tài liệu, kiểm tra `opsDistZip` và `installOpsDist`. Vì sao nó không tự mang launcher của main application?

**Bài tập O — phân biệt artifact.** So sánh `java -jar build/libs/distribution-demo-1.0.0.jar` với chạy `bin/distribution-demo`. Tại sao script của distribution có khả năng cung cấp runtime classpath tốt hơn với project dùng dependency ngoài?

### Câu hỏi tự kiểm tra

1. Application plugin tự áp dụng hai plugin nền tảng nào?
2. `application.mainClass` có vai trò gì?
3. `run` là task kiểu gì, khác `installDist` ra sao?
4. `startScripts` tạo những loại launcher nào?
5. `installDist` cho ra thư mục chưa nén hay file archive?
6. `distZip` có chỉ đóng gói application JAR không?
7. `distTar` và `assembleDist` khác nhau ra sao?
8. Vì sao `assemble` có thể tạo cả ZIP và TAR?
9. `src/dist` được đặt ở đâu trong distribution?
10. `src/main/resources` có giống `src/dist` không?
11. JAR của dependencies runtime được đặt ở đâu?
12. `testImplementation` có tự đi vào `lib` của main distribution không?
13. Biến `DISTRIBUTION_DEMO_OPTS` dùng làm gì?
14. `applicationDefaultJvmArgs` có ảnh hưởng cả `run` và generated scripts không?
15. `--args="foo"` của Gradle khác `bin/app foo` ở chỗ nào?
16. Vì sao generated script không tự cung cấp JDK/JRE?
17. `applicationName` ảnh hưởng gì tới launcher?
18. `executableDir` có ảnh hưởng `src/main/java` không?
19. Khi nào cần `distributions.main.contents` thay vì `src/dist` đơn giản?
20. Vì sao named distribution mới không mặc định là ứng dụng hoàn chỉnh thứ hai?
21. Vì sao không nên trỏ `installDist` tới thư mục có dữ liệu người dùng?
22. Những bước kiểm tra gì chứng minh ZIP thật sự chạy được trên máy đích?
23. Vì sao quality gate trong CI nên chạy `check` trước khi publish `distZip`?
24. Khi Java version của dependency cao hơn runtime đích, điều gì có thể xảy ra?
25. Vì sao artifact chứa secret không an toàn dù được nén ZIP?
26. Vì sao cần kiểm tra archive paths/scripts trên cả Windows và Unix-like?
27. `java -jar` khác generated launcher ở cách thiết lập classpath thế nào?
28. Muốn phát hành một ZIP có thể tái lập, cần kiểm soát thêm những yếu tố nào ngoài task `distZip`?

**Tài liệu chính thức:** [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html), [Gradle — Distribution Plugin](https://docs.gradle.org/current/userguide/distribution_plugin.html), [Gradle — JavaApplication DSL](https://docs.gradle.org/current/dsl/org.gradle.api.plugins.JavaApplication.html), [Gradle — CreateStartScripts](https://docs.gradle.org/current/dsl/org.gradle.jvm.application.tasks.CreateStartScripts.html), [Gradle — Building Java projects](https://docs.gradle.org/current/userguide/building_java_projects.html).

**Ghi nhớ:** Application plugin giúp tạo **bản phân phối JVM có thể vận hành** với generated scripts ở `bin`, application JAR và runtime dependencies ở `lib`, extra files từ `src/dist`. `startScripts` sinh launcher; `installDist` dựng thư mục chưa nén; `distZip` và `distTar` tạo archive; `assembleDist` tạo cả hai. Hãy chạy thử **chính bản distribution** trên Java runtime đích, kiểm tra dependency/files/quyền/chính sách CI, và đừng nhầm ZIP distribution với fat JAR hoặc bundle đã kèm JVM.