# Application plugin, mainClass và chạy ứng dụng bằng run trong Gradle

## 1. Khi nào một dự án Java cần Application plugin?

Một dự án Java có thể biên dịch thành công bằng plugin `java` nhưng vẫn chưa có lệnh Gradle thuận tiện để **chạy phương thức `main`**. Nếu tự chạy bằng `java -cp ...`, developer phải lắp đúng compiled classes, resources và dependency JARs vào runtime classpath. Một dự án có nhiều thư viện chuyển tiếp sẽ rất khó bảo trì danh sách này bằng tay.

**Application plugin** cung cấp mô hình Gradle dành cho một **ứng dụng JVM có điểm vào**. Nó:

- Áp dụng Java plugin để quản lý source sets, biên dịch và runtime dependencies.
- Áp dụng Distribution plugin để tạo bản phân phối chứa launcher scripts và libraries.
- Tạo task `run` kiểu `JavaExec` để chạy ứng dụng ngay trong môi trường phát triển.
- Cung cấp extension `application` để khai báo `mainClass`, `mainModule` (nếu dùng Java modules), `applicationName` và các JVM arguments mặc định.
- Tạo `startScripts`, `installDist`, `distZip` và `distTar` để đưa ứng dụng tới máy không có Gradle.

Cú pháp tối thiểu trong file `build.gradle.kts`:

~~~kotlin
plugins {
    application
}

application {
    mainClass.set("com.example.cli.Main")
}
~~~

Chạy từ root dự án có Gradle Wrapper:

~~~bash
./gradlew run
~~~

Cần nhớ ba điểm:

1. `application.mainClass` là **tên class có `main`**, không phải task, file path hoặc tên artifact.
2. `run` là **task chạy ứng dụng** trong JVM con với runtime classpath; không bắt buộc tạo archive trước.
3. `installDist` và `distZip` tạo **bản phân phối**, không đồng nghĩa `run`.

**Mục tiêu học:** sau bài này, bạn có thể cấu hình `application`, chạy `run` và `--args`, phân biệt JVM/application/Gradle properties, hiểu cấu trúc task/classpath, dùng launcher phân phối và debug các lỗi phổ biến.

## 2. Phân biệt Java plugin, Java Library plugin và Application plugin

| Plugin | Trọng tâm | Task/đặc điểm |
| --- | --- | --- |
| `java` | Biên dịch, kiểm thử, tạo JAR của source set Java | `compileJava`, `classes`, `jar`, `test`, `build` |
| `java-library` | Phát triển và công bố thư viện với API riêng | Bổ sung phân biệt `api`/`implementation` và library variants |
| `application` | Chạy và phân phối chương trình JVM | `run`, `startScripts`, `installDist`, `distZip`, `distTar` |

Application plugin **đã áp dụng `java`**, vì vậy không cần viết:

~~~kotlin
plugins {
    java
    application
}
~~~

để mong có thêm `compileJava`: cấu hình `plugins { application }` là đủ cho Java ứng dụng.

### 2.1. Các task chính

| Task | Type thường gặp | Vai trò |
| --- | --- | --- |
| `run` | `JavaExec` | Chạy JVM con bằng main class và runtime classpath |
| `startScripts` | `CreateStartScripts` | Tạo script Unix-like và Windows |
| `installDist` | `Sync` | Cài bản phân phối vào thư mục build |
| `distZip` | `Zip` | Đóng gói application distribution thành ZIP |
| `distTar` | `Tar` | Đóng gói application distribution thành TAR |
| `assembleDist` | Lifecycle | Tạo các distribution archives |
| `jar` | `Jar` | Gói classes/resources thành JAR thông thường |
| `build` | Lifecycle | Tổng hợp build và verification tasks; thường gồm distribution archives |

Task `run` phụ thuộc kết quả `classes` khi cần. `startScripts` và các distribution tasks có những dependency graph khác để đưa scripts và JAR vào bản phân phối. Bạn không cần chạy `jar` rồi `run` theo trình tự thủ công.

Một module chỉ dùng như thư viện không cần áp dụng Application plugin. Với multi-project build, chỉ module có executable entry point thường sở hữu task `:app:run`.

## 3. Ví dụ hoàn chỉnh bằng Java 17+ và Gradle Kotlin DSL

Ví dụ này **không cần dependency ngoài JDK**. Nó in lời chào, đếm arguments và đọc JVM system property do Application plugin truyền vào. Toàn bộ mã nguồn dưới đây có thể dùng làm một dự án học độc lập.

### 3.1. Cấu trúc project

~~~text
hello-gradle-app/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── hello/
                        └── Main.java
~~~

Các file Gradle Wrapper phải là **Wrapper thật đã tạo từ Gradle**, không thể chỉ tạo file `gradlew` rỗng. Máy cần JDK 17 hoặc toolchain tương ứng và Gradle Wrapper phù hợp với JDK.

**`settings.gradle.kts`:**

~~~kotlin
rootProject.name = "hello-gradle-app"
~~~

**`build.gradle.kts`:**

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    application
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

application {
    mainClass.set("com.example.hello.Main")
    applicationName = "hello-cli"
    applicationDefaultJvmArgs = listOf("-Ddemo.mode=development")
}
~~~

**`src/main/java/com/example/hello/Main.java`:**

~~~java
package com.example.hello;

import java.util.Locale;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Gradle";
        boolean upper = args.length > 1
                && "--upper".equals(args[1]);

        if (upper) {
            name = name.toUpperCase(Locale.ROOT);
        }

        String mode = System.getProperty("demo.mode", "unset");

        System.out.println("Hello, " + name + "!");
        System.out.println("Mode: " + mode);
        System.out.println("Arguments: " + args.length);
    }
}
~~~

### 3.2. Hiểu cấu hình

- `plugins { application }` áp dụng cả Java và Distribution model.
- `version = "1.0.0"` được dùng trong artifact/distribution naming theo convention.
- `java.toolchain` yêu cầu JDK major version 17. Nếu chưa tìm/provision được Java 17, build có thể thất bại thay vì tự chọn JDK khác.
- `options.encoding` và `options.release` làm compilation rõ ràng hơn, tránh phụ thuộc charset và target API không mong muốn.
- `mainClass` xác định **fully qualified class name**. Nó phải khớp `package com.example.hello;` và class `Main`.
- `applicationName` đặt tên launcher/distribution. Nó không đổi tên package hoặc class Java.
- `applicationDefaultJvmArgs` đưa option `-Ddemo.mode=development` tới JVM ứng dụng khi chạy `run` và tới generated start scripts của distribution.

Không cần `repositories { mavenCentral() }` trong ví dụ vì Java code chỉ dùng JDK. Khi có external dependencies, phải khai báo repository phù hợp với policy của dự án.

### 3.3. Chạy không tham số

Linux/macOS:

~~~bash
./gradlew -q run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat -q run
~~~

**Ba dòng do Java Main in ra:**

~~~text
Hello, Gradle!
Mode: development
Arguments: 0
~~~

`-q` làm giảm logging Gradle, nhưng tùy môi trường có thể vẫn thấy warning/JVM logs. Ba dòng trên là **output từ chương trình**, không phải toàn bộ log bất biến của Gradle.

### 3.4. Chạy với arguments

Linux/macOS:

~~~bash
./gradlew -q run --args="Lan --upper"
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat -q run --args="Lan --upper"
~~~

Kết quả từ Java:

~~~text
Hello, LAN!
Mode: development
Arguments: 2
~~~

Gradle truyền `Lan` và `--upper` vào `String[] args`. Code của chính ứng dụng kiểm tra `args[1]` và chuyển tên thành chữ hoa. `--upper` **không phải Gradle option**; nó là tham số của chương trình Java.

## 4. mainClass là gì?

`application.mainClass` là một `Property<String>` chứa tên class JVM sẽ gọi như điểm vào:

~~~kotlin
application {
    mainClass.set("com.example.hello.Main")
}
~~~

| Giá trị | Có phù hợp demo? | Vì sao |
| --- | --- | --- |
| `com.example.hello.Main` | Có | Đúng fully qualified name |
| `Main` | Không | Thiếu package |
| `src/main/java/com/example/hello/Main.java` | Không | Source file path |
| `com.example.hello.Main.class` | Không | Thừa suffix |
| `main` | Không | Method name, không phải class |
| `hello-cli` | Không | Application launcher name |

Một class Java 17 có điểm vào rõ ràng như:

~~~java
package com.example.tool;

public class Launcher {
    public static void main(String[] args) {
        System.out.println("Started");
    }
}
~~~

cần cấu hình `mainClass.set("com.example.tool.Launcher")`.

### 4.1. mainClass và Main-Class của manifest không giống nhau

- `application.mainClass` giúp `run` và generated launcher scripts xác định entry class.
- `Main-Class` trong **JAR manifest** được Java launcher dùng khi gọi `java -jar some.jar`.
- Application plugin không tự biến JAR thông thường thành **fat/uber-JAR** chứa mọi runtime dependency.

Dù có `application.mainClass`, `java -jar build/libs/...jar` có thể báo `no main manifest attribute` hoặc thiếu dependencies. Thay vào đó, dùng `run` khi phát triển và generated launcher scripts để chạy bản phân phối.

Với chính demo **không có external dependencies**, có thể chạy:

~~~bash
./gradlew jar
java -cp build/libs/hello-gradle-app-1.0.0.jar com.example.hello.Main
~~~

Lệnh này chạy Java class qua classpath và **không tự truyền** `applicationDefaultJvmArgs`, vì vậy Java sẽ in `Mode: unset` nếu không có JVM option `-Ddemo.mode=development`.

### 4.2. Nếu thật sự cần java -jar

Có thể thêm vào `build.gradle.kts`:

~~~kotlin
import org.gradle.api.tasks.bundling.Jar

tasks.named<Jar>("jar") {
    manifest {
        attributes["Main-Class"] = "com.example.hello.Main"
    }
}
~~~

Đây là **snippet mở rộng**, không phải một script độc lập. Nó bổ sung entry point metadata cho JAR; **không đóng gói các runtime dependencies**. Với ứng dụng dùng nhiều libraries, generated start scripts và distribution `lib` là phương án chuẩn của Application plugin. Nếu cần một executable single JAR, phải thiết kế dependency packaging phù hợp hoặc dùng plugin được duy trì cho mục đích đó.

## 5. run dưới lớp vỏ là JavaExec

Task `run` của Application plugin có type `JavaExec`: nó khởi động một **Java process con**, độc lập với Gradle Daemon JVM.

~~~text
./gradlew run
       |
       v
Configuration / task graph
       |
       +--> compileJava (nếu cần)
       +--> processResources (nếu cần)
       +--> classes
       |
       v
run: JavaExec
       |
       +--> mainClass
       +--> main runtimeClasspath
       +--> JVM options
       +--> String[] args
       +--> environment / working directory
       |
       v
Java child process
       |
       v
Main.main(String[] args)
~~~

**Điểm cần hiểu:**

- `run` không tự gọi `main` khi Gradle chỉ đọc build script.
- Các khối `application { ... }` là **mã cấu hình**, không phải code Java đang thực thi.
- `run` dùng **runtimeClasspath của source set main**, bao gồm compiled classes, processed resources và runtime dependencies.
- `run` không phải task tạo file deterministic để cache output; mỗi khi thực sự được yêu cầu chạy, nó thường chạy chương trình. Các task compilation phía trước vẫn có thể `UP-TO-DATE`.
- `JavaExec` mặc định forward stdout/stderr của process con ra console. Nếu JVM trả exit code khác 0, task thường fail do `ignoreExitValue` mặc định `false`.
- Nếu main chạy một server không kết thúc, task `run` có thể giữ terminal/CI job đang bận cho đến khi process dừng.

### 5.1. Runtime classpath là gì?

Ví dụ nếu bổ sung dependencies vào project:

~~~kotlin
repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
~~~

Gradle có thể resolve JAR từ Maven Central/mirror hợp lệ khi `run` cần `runtimeClasspath`. `run` dùng đúng source set runtime model, không yêu cầu developer nối thủ công mọi JAR vào `-cp`.

Đoạn trên là **snippet mở rộng**, không thuộc demo Java `Main` vì demo không gọi Commons Lang.

Nếu dependency chỉ được khai báo `compileOnly`, class có thể tồn tại khi compile nhưng vắng khi chạy, gây `NoClassDefFoundError` hoặc lỗi liên quan. Cần dùng đúng `implementation`/`runtimeOnly` theo nhu cầu thực, không sửa bằng cách hardcode đường dẫn JAR.

### 5.2. Không bắt buộc tạo JAR trước run

`run` sử dụng kết quả `classes`; nó không đòi hỏi `jar`, `distZip` hay `installDist`. Nếu class Java biên dịch được, Gradle có thể khởi động bằng source set outputs và runtime dependencies mà không cần một ZIP/TAR.

Đây là lý do `run` phù hợp cho chu kỳ sửa mã–chạy–debug. Distribution tasks là bước khác dành cho packaging.

## 6. Phân biệt arguments, JVM options, Gradle project properties

Một lỗi thường gặp là đặt option đúng tên nhưng vào **sai lớp**.

| Cách truyền | Bên nhận | Cách đọc |
| --- | --- | --- |
| `run --args="Lan --upper"` | Ứng dụng Java | `main(String[] args)` |
| JVM option `-Ddemo.mode=development` | JVM chạy ứng dụng | `System.getProperty("demo.mode")` |
| `./gradlew -Pprofile=qa run` | Gradle project | Gradle project property `profile` |
| Environment `APP_PROFILE` | Process được kế thừa/cấp biến | `System.getenv("APP_PROFILE")` |
| `org.gradle.jvmargs` | Gradle Daemon | Không tự là JavaExec JVM args |
| `--debug-jvm` | Gradle `JavaExec` task | Bật debugger cho JVM ứng dụng |
| `--info`/`--stacktrace` | Gradle CLI | Build diagnostics |

### 6.1. --args là tham số main

Ví dụ:

~~~bash
./gradlew run --args="Lan --upper"
~~~

JavaExec phân tách chuỗi này thành `args[0]="Lan"`, `args[1]="--upper"`. Cách quote chuỗi có dấu cách khác nhau theo bash/PowerShell/CMD; cần tính đến **hai lớp parser** (shell và JavaExec argument parser).

`--args` không được xem như một environment variable hoặc JVM system property. Đừng truyền password/token bí mật trên CLI nếu có thể xuất hiện trong process listing, shell history hoặc CI logs.

### 6.2. Arguments mặc định trong run

Nếu cần set application args cho task `run`:

~~~kotlin
import org.gradle.api.tasks.JavaExec

tasks.named<JavaExec>("run") {
    args("DefaultUser")
}
~~~

Đây là **snippet cấu hình tùy chọn**. `args(...)` thêm arguments của chương trình; nó khác với `applicationDefaultJvmArgs` là JVM arguments. Khi chạy với `--args`, Gradle thiết lập danh sách arguments từ CLI; không dựa vào giả định hai danh sách sẽ luôn được tự ghép theo ý bạn.

### 6.3. -P không tự đi vào chương trình

Lệnh:

~~~bash
./gradlew -Pprofile=qa run
~~~

tạo Gradle project property `profile`. Nó **không tự động** làm Java `System.getProperty("profile")` trả về `qa`. Muốn truyền từ Gradle qua JavaExec, cần cấu hình ánh xạ property, hoặc dùng application arguments/environment/runtime config phù hợp.

## 7. applicationDefaultJvmArgs: cấu hình chung cho run và start scripts

Trong demo:

~~~kotlin
application {
    applicationDefaultJvmArgs = listOf("-Ddemo.mode=development")
}
~~~

Lợi ích: option này được áp dụng vào **task `run`** và cũng được xét trong **start scripts sinh ra**. Vì vậy cùng một Java Main khi gọi qua `run` hay qua launcher trong `installDist` có thể đọc `demo.mode=development`.

| Option | Ví dụ | Tác động |
| --- | --- | --- |
| Java system property | `-Ddemo.mode=development` | `System.getProperty` |
| Heap giới hạn tối đa | `-Xmx512m` | JVM application memory |
| Java assertions | `-ea` | Bật assertions |
| Module access | `--add-opens=...` | Java Module System khi thực sự cần |

**Không đưa API tokens, database passwords hoặc private keys** vào `applicationDefaultJvmArgs`: nó có thể được nhúng vào generated start scripts và distribution artifact, cũng như lộ qua process/log. Cấp secrets từ secret store/runtime environment có phạm vi phù hợp.

### 7.1. Cấu hình chỉ cho task run

~~~kotlin
import org.gradle.api.tasks.JavaExec

tasks.named<JavaExec>("run") {
    systemProperty("demo.runOnly", "yes")
    maxHeapSize = "512m"
}
~~~

Snippet này chỉ cấu hình task `run`, không tự làm generated launcher scripts thay đổi theo các values đó. Nếu muốn launcher scripts cũng nhận JVM defaults, dùng `applicationDefaultJvmArgs`.

Cấp biến môi trường cho riêng `run`:

~~~kotlin
tasks.named<JavaExec>("run") {
    environment("APP_PROFILE", "local")
}
~~~

Trong Java, đọc bằng `System.getenv("APP_PROFILE")`, **không** bằng `System.getProperty("APP_PROFILE")`. Generated launcher chạy trong một process khác và nhận environment của nơi nó được gọi; setting `environment(...)` trên run task không tự được đóng gói thành launcher default.

## 8. Java toolchain: Gradle JVM khác application JVM

Một máy có thể chạy Gradle bằng JDK A nhưng biên dịch/chạy ứng dụng bằng JDK B đã cấu hình trong toolchain.

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Application/JavaExec được tích hợp với Java plugin toolchain model phù hợp. Vì vậy không nên chỉ nhìn `JAVA_HOME` rồi kết luận task `run` chắc chắn dùng JDK đó. Trong môi trường dùng toolchains, launcher có thể là một JDK khác.

Lệnh:

~~~bash
./gradlew --version
~~~

cho thông tin version/JVM của Gradle runtime. Khi cần biết Java chạy **trong application process**, tạm in:

~~~java
System.out.println(System.getProperty("java.version"));
System.out.println(System.getProperty("java.home"));
~~~

Đây là snippet debug, **không thuộc stdout cố định** của demo mục 3 vì phiên bản và đường dẫn JVM phụ thuộc môi trường.

### 8.1. options.release và runtime version

`options.release.set(17)` giới hạn API/bytecode mục tiêu của JavaCompile. Nó không cho phép chạy bytecode 17 trên JVM 11. Nếu thấy `UnsupportedClassVersionError`, kiểm tra launcher của process và version class file; đừng chỉnh mainClass ngẫu nhiên.

Nếu Gradle báo không có matching toolchain, cài/provision Java 17 hợp lệ hoặc cấu hình toolchain download theo chính sách tổ chức. `javaLauncher` là property trên JavaExec khi cần lựa chọn launcher riêng, nhưng với bài học cơ bản nên dùng toolchain model nhất quán.

## 9. Chạy từ bản phân phối: installDist và distZip

`run` thuận tiện khi phát triển. Khi gửi chương trình cho người dùng **không có Gradle**, Application plugin tạo bản phân phối chuẩn có:

- Start scripts cho Unix/macOS và Windows.
- JAR ứng dụng.
- Runtime dependency JARs trong thư mục `lib`.
- Các file bổ sung từ `src/dist` và distribution CopySpecs.

Với demo `rootProject.name="hello-gradle-app"`, `version="1.0.0"` và `applicationName="hello-cli"`, các output mặc định thường có dạng:

~~~text
build/
├── libs/
│   └── hello-gradle-app-1.0.0.jar
├── install/
│   └── hello-cli/
│       ├── bin/
│       │   ├── hello-cli
│       │   └── hello-cli.bat
│       └── lib/
│           └── hello-gradle-app-1.0.0.jar
└── distributions/
    ├── hello-cli-1.0.0.zip
    └── hello-cli-1.0.0.tar
~~~

Đây là **layout dự kiến nếu chạy các task liên quan**, không phải tất cả file tự tạo chỉ bằng `run`. Tùy phiên bản Gradle và settings về distribution/archive naming, tên/đường dẫn có thể được tùy chỉnh.

### 9.1. installDist

Linux/macOS:

~~~bash
./gradlew installDist
./build/install/hello-cli/bin/hello-cli Lan --upper
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat installDist
.\build\install\hello-cli\bin\hello-cli.bat Lan --upper
~~~

Output từ Main:

~~~text
Hello, LAN!
Mode: development
Arguments: 2
~~~

Generated launcher xử lý JVM options và classpath dựa trên distribution `lib`. Trên máy đích cần có **Java runtime tương thích**; Application plugin không tự đóng gói một JRE/JDK tiêu chuẩn.

### 9.2. distZip và distTar

~~~bash
./gradlew distZip
./gradlew distTar
~~~

Các archives chứa ứng dụng và launch scripts. Người dùng thường giải nén rồi chạy script phù hợp OS. Khác với việc chạy trực tiếp một fat JAR, distribution thông thường giữ các dependencies thành file riêng trong `lib`.

Để tạo cả archives theo model, dùng `assembleDist` hoặc lifecycle `assemble`/`build` thích hợp; những task này được nối vào distribution model, nhưng chạy `run` thì không cần tạo ZIP/TAR.

### 9.3. src/dist và tài liệu kèm theo

Có thể đặt:

~~~text
src/dist/
├── README.txt
└── conf/
    └── example.properties
~~~

để đưa vào root distribution. Chỉ thêm **sample config không nhạy cảm**; đừng đóng gói production secrets.

Khi muốn thêm file do task khác sinh, dùng distribution CopySpec và output provider thay vì hardcode một file chưa tồn tại. Gradle có thể suy ra dependency tới task producer khi FileCollection/TaskProvider được dùng phù hợp.

### 9.4. Name của launcher khác name của JAR

`applicationName="hello-cli"` điều khiển tên launch scripts và distribution identity; `rootProject.name="hello-gradle-app"` và `version` thường ảnh hưởng tên JAR. Không chỉnh package Java hoặc class name chỉ để đổi launcher file.

## 10. Groovy DSL tương đương

Nếu project sử dụng `build.gradle`, một build script tương đương demo:

~~~groovy
plugins {
    id 'application'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}

application {
    mainClass = 'com.example.hello.Main'
    applicationName = 'hello-cli'
    applicationDefaultJvmArgs = ['-Ddemo.mode=development']
}
~~~

Đây là phương án **thay thế** file `build.gradle.kts`, không dùng đồng thời hai scripts khác DSL trong cùng root để “nhân đôi” plugin.

Cấu hình run trong Groovy:

~~~groovy
tasks.named('run', JavaExec) {
    systemProperty 'demo.runOnly', 'yes'
    maxHeapSize = '512m'
}
~~~

Kotlin DSL dùng `mainClass.set("...")` và `tasks.named<JavaExec>("run")`; Groovy DSL thường dùng `mainClass = '...'` và closure. Hai cú pháp có cùng mục tiêu nhưng không thay thế nhau nguyên văn.

## 11. Ứng dụng đa module: chạy đúng project

Giả sử:

~~~text
workspace/
├── settings.gradle.kts
├── core/
│   └── build.gradle.kts
└── app/
    └── build.gradle.kts
~~~

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "workspace"
include(":core", ":app")
~~~

`core/build.gradle.kts`:

~~~kotlin
plugins {
    id("java-library")
}
~~~

`app/build.gradle.kts`:

~~~kotlin
plugins {
    application
}

dependencies {
    implementation(project(":core"))
}

application {
    mainClass.set("com.example.app.Main")
}
~~~

Đây là **sơ đồ snippets**; để chạy thật phải tạo code cho `com.example.app.Main` và các classes ở `core` khi dùng. Lệnh từ root:

~~~bash
./gradlew :app:run
~~~

Khi có program arguments:

~~~bash
./gradlew :app:run --args="Lan --upper"
~~~

Task path `:app:run` tránh mơ hồ về project sở hữu task. Application plugin ở `:app`, không bắt buộc ở root hoặc `:core`. Runtime classpath của `:app` bao gồm outputs và dependencies từ `:core` khi project dependency được khai báo đúng.

## 12. Ứng dụng Java module: mainModule và mainClass

Nếu project dùng Java Module System (JPMS), cần khai báo module name ngoài main class name.

Ví dụ descriptor thêm vào demo:

**`src/main/java/module-info.java`:**

~~~java
module com.example.hello {
}
~~~

Cấu hình:

~~~kotlin
application {
    mainModule.set("com.example.hello")
    mainClass.set("com.example.hello.Main")
}
~~~

Đây là **biến thể modular** của demo. Chỉ thêm `mainModule` nếu thực sự có module descriptor hợp lệ; trong project classpath-only thông thường chỉ cần `mainClass`. Java module name phải khớp descriptor, còn mainClass là fully qualified class name.

Với dependencies modular/non-modular, module path có thể gặp các vấn đề về exported packages, required modules hoặc reflection. Không cố sửa bằng cách bỏ `mainClass`; cần phân biệt lỗi module resolution với lỗi entry point.

## 13. Debug chương trình bằng --debug-jvm

Vì `run` là `JavaExec`, Gradle có option:

~~~bash
./gradlew run --debug-jvm
~~~

Windows:

~~~powershell
.\gradlew.bat run --debug-jvm
~~~

Trong cấu hình mặc định, Java process thường **chờ debugger kết nối** tại cổng **5005**. Thao tác cơ bản:

1. Gọi `run --debug-jvm` trong terminal local.
2. Trong IDE, tạo cấu hình Remote JVM Debug đến host/port được in trong log.
3. Đặt breakpoint trong Java `Main.main`.
4. Attach để JVM tiếp tục, rồi debug.
5. Ngắt session khi đã hoàn tất.

**Phân biệt:**

- `--debug-jvm`: bật Java remote debugger cho JVM con.
- `--debug`: tăng độ chi tiết logging của Gradle.
- `--stacktrace`: in nguyên nhân lỗi của Gradle task/build.
- `--info`: thêm thông tin build, resolution và task execution.

Không mở debug port ra mạng không tin cậy; debug JVM cho phép quan sát/can thiệp mạnh vào process.

### 13.1. debugOptions tùy chỉnh

~~~kotlin
import org.gradle.api.tasks.JavaExec

tasks.named<JavaExec>("run") {
    debugOptions {
        enabled.set(true)
        port.set(5006)
        server.set(true)
        suspend.set(false)
    }
}
~~~

**Snippet tùy chọn**, không thuộc demo gốc. Bật debug mỗi lần `run` không thích hợp cho CI/production. `suspend=false` khiến JVM chạy ngay nên breakpoint đầu có thể bị bỏ qua trước khi debugger attach.

## 14. stdin: chương trình cần nhập liệu

JavaExec mặc định thường cung cấp **input stream rỗng** cho ứng dụng. Nếu Java main gọi `Scanner(System.in)` để chờ tương tác, nó có thể nhận EOF thay vì đợi phím từ terminal.

Với chạy cục bộ có thể forward stdin:

~~~kotlin
import org.gradle.api.tasks.JavaExec

tasks.named<JavaExec>("run") {
    standardInput = System.`in`
}
~~~

Đây là **snippet độc lập về cấu hình**; sau bước chuyển đổi inline delimiters, `System.`in`` trở thành cú pháp Kotlin dùng backtick để truy cập Java field tên `in` (vì `in` là keyword Kotlin). Để dùng phải có chương trình thật đọc stdin.

Một số môi trường IDE/CI và Configuration Cache có hạn chế với việc forward process stdin. Nếu ứng dụng được thiết kế tương tác lâu dài, bạn có thể chạy **generated launcher** sau `installDist` trong terminal thay vì phụ thuộc task Gradle. Không lưu password vào file source để mô phỏng interactive input.

## 15. workingDir, tài nguyên và file cấu hình

Working directory mặc định của `JavaExec` thường là **project directory** có task `run`. Với multi-project, `:app:run` thường nhìn đường dẫn tương đối từ thư mục `app`, không phải root.

Java:

~~~java
var path = java.nio.file.Path.of("config/local.properties");
System.out.println(path.toAbsolutePath());
~~~

Đây là **snippet minh họa phụ thuộc môi trường**, không phải output cố định của demo mục 3.

Nếu muốn chỉ rõ working directory khi thư mục có thật:

~~~kotlin
tasks.named<JavaExec>("run") {
    workingDir = layout.projectDirectory.dir("local-data").asFile
}
~~~

**Tuy nhiên:** việc sửa workingDir không giúp generated start scripts luôn tìm được config ở cùng đường dẫn. Thiết kế ứng dụng nên phân biệt:

- **Classpath resources:** đặt trong `src/main/resources`, đọc bằng `ClassLoader` hoặc `Class.getResourceAsStream`.
- **Runtime config do user cấp:** path/environment/arguments explicit.
- **Writable data:** thư mục runtime riêng, không ghi vào JAR hoặc source tree.
- **Distribution extras:** template trong `src/dist`, không chứa credentials.

Ví dụ snippet đọc classpath resource:

~~~java
try (var input = Main.class.getResourceAsStream("/banner.txt")) {
    if (input == null) {
        throw new IllegalStateException("banner.txt is missing");
    }
    String banner = new String(
            input.readAllBytes(),
            java.nio.charset.StandardCharsets.UTF_8
    );
    System.out.println(banner);
}
~~~

Đoạn này **không độc lập**: nó cần `src/main/resources/banner.txt` và method xử lý/khai báo `IOException`. Nó minh họa đúng hướng đọc tài nguyên, không phải thay nguyên code Main trong demo mà không bổ sung xử lý exception.

## 16. Application scripts và runtime JVM options

Generated start scripts thường có tên theo `applicationName`, ví dụ `hello-cli` và `hello-cli.bat`. Ngoài default JVM arguments cấu hình trong build, chúng có thể đọc environment variable dành cho app:

~~~text
<APPLICATION_NAME>_OPTS
~~~

Tên ứng dụng được uppercase, ký tự không phải chữ/số đổi thành underscore. Với `hello-cli`, tên tương ứng là `HELLO_CLI_OPTS`.

Linux/macOS:

~~~bash
HELLO_CLI_OPTS="-Xmx512m -Ddemo.flag=1" \
  ./build/install/hello-cli/bin/hello-cli
~~~

PowerShell:

~~~powershell
$env:HELLO_CLI_OPTS = "-Xmx512m -Ddemo.flag=1"
.\build\install\hello-cli\bin\hello-cli.bat
~~~

Đây là cách cấu hình generated **launcher**, không tác động trực tiếp tới `./gradlew run`. Không đặt secrets nhạy cảm vào JVM options hoặc scripts được phát hành.

Có thể đổi thư mục chứa scripts trong distribution:

~~~kotlin
application {
    executableDir = "scripts"
}
~~~

Khi đó script có thể xuất hiện dưới `scripts` thay cho `bin` trong distribution; class name của Java vẫn không thay đổi.

## 17. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `Task 'run' not found` | Không có plugin `application` trong module đang gọi | Áp dụng plugin đúng project; dùng `:app:run` |
| Không khai báo main class | Chưa set `application.mainClass` | Set fully qualified class name |
| `Could not find or load main class` | Sai package/name hoặc classpath | Kiểm tra `package`, `src/main/java`, `mainClass` |
| `Main method not found` | Chữ ký main không đúng cho Java launcher | `public static void main(String[] args)` |
| `No matching toolchains found` | JDK 17 chưa có/provision sai | Kiểm tra Java toolchains, JDK installation |
| `UnsupportedClassVersionError` | JVM chạy cũ hơn bytecode | Dùng compatible runtime/toolchain |
| `NoClassDefFoundError` | Thiếu runtime dependency hoặc binary mismatch | Xem `runtimeClasspath` và dependency scopes |
| Program không nhận arguments | Thiếu `--args` hoặc quote sai | Kiểm tra CLI và in `args.length` |
| Mode hiện `unset` | Dùng Gradle `-P` thay vì JVM `-D` | Cấp property qua `applicationDefaultJvmArgs`/JavaExec |
| Ứng dụng nhận EOF khi đọc input | `standardInput` của JavaExec rỗng | Forward stdin phù hợp hoặc dùng launcher |
| `java -jar` báo no main manifest attribute | JAR không có `Main-Class` | Dùng launcher hoặc cấu hình manifest |
| `java -jar` chạy nhưng thiếu dependencies | JAR không phải fat JAR | Dùng distribution `lib`/classpath đúng |
| Launcher chạy ở IDE nhưng lỗi khi install | Khác workingDir/JDK/resources/runtime libs | Smoke-test `installDist`/script |
| `run` không kết thúc | Server còn chạy hoặc chờ debugger | Kiểm tra lifecycle và `--debug-jvm` |
| `--debug` không dừng breakpoint | Nhầm Gradle logging với JVM debugger | Dùng `--debug-jvm` |
| Application heap khác Gradle daemon heap | Cấu hình nhầm `org.gradle.jvmargs` | Cấu hình JVM options của app |
| `distZip` thiếu file cấu hình mẫu | File ngoài `src/dist` hoặc CopySpec sai | Kiểm tra distribution contents |

### 17.1. Quy trình debug nhanh

1. Chạy `./gradlew tasks` và `./gradlew help --task run` ở project phù hợp.
2. Kiểm tra class đầy đủ ở `application.mainClass`.
3. Kiểm tra `compileJava`/`classes` thành công chưa.
4. Xem `./gradlew --version` và launcher/toolchain của `run`.
5. Kiểm tra `--args`, JVM properties, environment và working directory.
6. Nếu lỗi thư viện, chạy `./gradlew dependencies --configuration runtimeClasspath` trên project ứng dụng.
7. Nếu error sau packaging, inspect `build/install/<name>/lib` và generated start scripts.
8. Chạy lại cả `run` và `installDist`/launcher để xác nhận chính xác tình huống.

Không phải lỗi nào cũng chữa bằng thay đổi `mainClass`. Đặc biệt 401/403/PKIX hoặc Maven dependency resolution là vấn đề repository/proxy/TLS, không phải do Java main method.

## 18. Run trong CI và dự án thật

`run` là công cụ tốt cho **development** và smoke-test CLI kết thúc nhanh; nó không phải deployment manager.

- Với ứng dụng server chạy lâu, task `run` chiếm terminal; trong CI cần timeout/lifecycle hoặc dùng deployment phù hợp.
- Với CLI cần publish, build distribution và thử generated scripts bên ngoài Gradle.
- Với secret, cấp tại runtime từ secret manager theo quyền tối thiểu; không commit password vào build script, `applicationDefaultJvmArgs` hay `src/dist`.
- Với ứng dụng có dependencies ngoài, dùng repository policy, dependency locking/verification và runtimeClasspath đúng.
- Với nhiều projects, task path `:app:run` giúp xác định module chịu trách nhiệm entry point.
- Với phát hành đa OS, kiểm tra Unix script permissions và Windows batch script trên môi trường đích; Java runtime vẫn cần cài tương thích.
- Với reproducibility, không nhúng build timestamp hoặc absolute workspace path vô cớ vào JAR/distribution.

Ví dụ kịch bản kiểm tra trên Unix-like:

~~~bash
./gradlew clean test
./gradlew installDist
./build/install/hello-cli/bin/hello-cli Lan --upper
./gradlew distZip
~~~

Đây là demo workflow; nếu project không có test sources, task `test` có thể báo `NO-SOURCE`, không có nghĩa đã kiểm thử đầy đủ. CI thật cần tests cho business logic và integration smoke tests.

## 19. Bài tập thực hành có đáp án

**Bài 1.** Bạn có thư viện không có method main, có nên áp dụng `application` cho mọi module?  
**Đáp án:** không; `java-library` phù hợp hơn cho module thư viện.

**Bài 2.** Class `com.acme.tools.Start` có `public static void main(String[] args)`. Giá trị `mainClass`?  
**Đáp án:** `"com.acme.tools.Start"`.

**Bài 3.** Muốn chạy project đơn từ shell bằng Gradle Wrapper?  
**Đáp án:** `./gradlew run` trên Unix-like, `.\gradlew.bat run` trên PowerShell.

**Bài 4.** Với ví dụ `run --args="Lan --upper"`, hai dòng đầu là gì?  
**Đáp án:** `Hello, LAN!` và `Mode: development`.

**Bài 5.** Tại sao demo không có arguments in `Arguments: 0`?  
**Đáp án:** main nhận mảng `String[] args` rỗng khi không cấp `--args`.

**Bài 6.** `applicationDefaultJvmArgs` đưa `-Ddemo.mode=development` vào đâu?  
**Đáp án:** JVM của `run` và generated start scripts.

**Bài 7.** `./gradlew -Pprofile=qa run` có tự tạo `System.getProperty("profile")="qa"` không?  
**Đáp án:** không; `-P` là Gradle project property.

**Bài 8.** Application plugin có tự tạo task `run` và `installDist` không?  
**Đáp án:** có; `run` kiểu `JavaExec`, distribution tasks qua plugin được áp dụng.

**Bài 9.** Có cần chạy `jar` trước `run` để có classpath?  
**Đáp án:** không; `run` dựa trên source set main runtime classpath.

**Bài 10.** Dự án nhiều module có ứng dụng ở `:cli`, gọi task thế nào từ root?  
**Đáp án:** `./gradlew :cli:run`.

**Bài 11.** Muốn tạo thư mục chạy ngoài Gradle trên máy có Java runtime?  
**Đáp án:** `./gradlew installDist` rồi chạy script trong `build/install/.../bin`.

**Bài 12.** `java -jar` báo thiếu `Main-Class` dù application.mainClass đã set. Vì sao?  
**Đáp án:** Application extension và JAR manifest là hai cơ chế khác nhau.

**Bài 13.** JAR có Main-Class nhưng chạy thiếu một dependency ngoài. Thêm manifest có đủ không?  
**Đáp án:** không; cần runtime classpath phù hợp hoặc packaging strategy chứa dependencies.

**Bài 14.** Muốn debug main bằng breakpoint trong IDE?  
**Đáp án:** `./gradlew run --debug-jvm`, attach Remote JVM Debug ở cổng được báo (thường 5005).

**Bài 15.** Program cần đọc stdin nhưng Gradle run nhận EOF. Hướng giải quyết?  
**Đáp án:** xem `standardInput` của JavaExec hoặc dùng generated launcher trong terminal tương tác.

**Bài 16.** Gradle Daemon chạy JDK 21, code yêu cầu Java toolchain 17. Có thể `run` dùng JDK 17 không?  
**Đáp án:** có, khi launcher được cấu hình theo toolchain và JDK phù hợp hiện diện/provision được.

**Bài 17.** `applicationName="hello-cli"` có đổi package `com.example.hello` không?  
**Đáp án:** không; launcher/distribution identity khác Java entry point.

**Bài 18.** Vì sao không ghi API token vào `applicationDefaultJvmArgs`?  
**Đáp án:** option có thể nằm trong generated scripts/process logs hoặc artifact phát hành.

**Bài 19.** `:app:run` thành công nhưng launch script sau `installDist` fail. Kiểm tra gì?  
**Đáp án:** runtime JDK, working directory, resources, generated scripts, thư mục `lib` và JVM/env args.

**Bài 20.** Khác biệt giữa `run` và `distZip`?  
**Đáp án:** `run` khởi động Java process; `distZip` tạo ZIP distribution để chuyển/cài đặt.

## 20. Checklist và tài liệu tham khảo

Trước khi bàn giao Java application Gradle:

- [ ] `application` ở đúng module executable.
- [ ] `mainClass` là fully qualified class có method `main`.
- [ ] Source path/package đúng và Java 17 toolchain có thể sử dụng.
- [ ] `./gradlew -q run` ra output kiểm chứng được.
- [ ] `--args` được parse đúng và có xử lý argument thiếu.
- [ ] `applicationDefaultJvmArgs` không chứa secrets.
- [ ] Phân biệt app args, JVM args, Gradle `-P` và environment.
- [ ] `runtimeClasspath` có đủ dependencies.
- [ ] `installDist` và generated start scripts chạy được bên ngoài Gradle.
- [ ] Không lầm `jar` thường với fat JAR.
- [ ] Với Java Module System, cấu hình `mainModule` có descriptor thật.
- [ ] Không mở JVM debug port cho mạng không tin cậy.
- [ ] Có smoke test distribution và kiểm thử ứng dụng thật.

Tài liệu chính thức:

- [Gradle — The Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): `run`, `--args`, `mainClass`, default JVM args và distributions.
- [Gradle — JavaApplication DSL](https://docs.gradle.org/current/dsl/org.gradle.api.plugins.JavaApplication.html): `applicationName`, `mainModule`, `executableDir`, `applicationDistribution`.
- [Gradle — JavaExec DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.JavaExec.html): classpath, args, environment, working directory, stdin và debugging.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): source sets, `runtimeClasspath` và lifecycle tasks.
- [Gradle — Distribution Plugin](https://docs.gradle.org/current/userguide/distribution_plugin.html): `installDist`, archive layout và CopySpec.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): compiler/JVM launcher configuration.
- [Gradle — Java Module System](https://docs.gradle.org/current/userguide/java_library_plugin.html#sec:java_library_modular): module descriptor và module path.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): task paths, CLI flags và debugging.

**Kết luận:** Application plugin kết nối **điểm vào Java `mainClass`** với task `run` và packaging model. `run` dùng JavaExec cùng `main.runtimeClasspath` để khởi chạy JVM con; `--args` cấp application arguments, `applicationDefaultJvmArgs` cấp JVM defaults áp dụng cho cả `run` lẫn generated launcher; `installDist` và `distZip` dùng cho phân phối. Hiểu ranh giới này giúp tránh sai classpath, nhầm `java -jar`, thiếu dependencies hoặc vận hành sai giữa development và production.