# Đồng bộ JDK của IDE, terminal, công cụ build và kiểm thử trong Java 17

Một dự án Java 17 có thể chạy thành công trong terminal nhưng báo lỗi trong IDE; biên dịch được bằng Gradle nhưng thất bại với Maven; hoặc biên dịch đúng Java 17 trong khi bộ kiểm thử lại chạy trên Java 21. Nguyên nhân thường là **mỗi thành phần đang chọn một JDK khác nhau**.

Đồng bộ JDK nghĩa là xác định rõ **JDK nào dùng để biên dịch, JDK nào dùng để chạy chương trình, JDK nào chạy công cụ build và JDK nào thực thi kiểm thử**. Bốn vai trò này có thể dùng cùng một bản JDK 17 hoặc dùng các bản JDK khác nhau theo chủ đích. Với người bắt đầu thực hành Java 17, cấu hình dễ kiểm soát nhất là sử dụng JDK 17 cho mọi tác vụ của dự án, sau đó đặt quy tắc phiên bản vào công cụ build để các thành viên và CI có cùng hành vi.

## 1. Phân biệt những nơi chọn JDK

| Thành phần | JDK có vai trò gì? | Cách kiểm tra chính |
| --- | --- | --- |
| **Terminal** | Chạy lệnh `java`, `javac`, công cụ dòng lệnh. | `java -version`, `javac -version`, đường dẫn lệnh thực tế. |
| **IDE** | Phân tích mã, chọn API/language level, biên dịch và chạy cấu hình riêng. | Project SDK, module SDK, language level, Run/Debug configuration. |
| **Gradle hoặc Maven** | Chạy chính công cụ build và chọn compiler khi tạo `.class`. | `./gradlew --version` / `mvn -version`, cấu hình compiler và toolchain. |
| **Bộ kiểm thử** | Chạy các test bằng JVM được IDE hoặc công cụ build khởi tạo. | Kiểm tra `java.version`, `java.home` ngay trong tiến trình test. |
| **CI** | Chạy build/test trên máy khác với máy lập trình viên. | Bước cài JDK, log phiên bản và kết quả build/test. |

Điểm dễ nhầm là **JDK để chạy một công cụ không nhất thiết là JDK để công cụ đó biên dịch dự án**. Chẳng hạn, Gradle có thể chạy bằng JVM 21 nhưng dùng Java toolchain 17 để gọi compiler Java 17. Ngược lại, Maven chạy bằng JDK 21 và cấu hình `--release 17` có thể tạo bytecode tương thích Java 17, nhưng các test vẫn có thể chạy trên JDK 21 nếu chưa chỉ định JVM cho bộ kiểm thử.

Hình dung các đường chọn phiên bản như sau:

```text
Terminal
  ├─ PATH  ───────────────────────────> java / javac đang được gọi
  └─ JAVA_HOME ───────┐
                      ├───────────────> JVM chạy Maven hoặc Gradle (*)
IDE ─────────────────┤
  ├─ Runtime của IDE ─────────────────> JVM chạy chính IDE
  ├─ Project / Module SDK ────────────> SDK phân tích và biên dịch của IDE
  ├─ Build tool JVM ──────────────────> JVM chạy Maven / Gradle từ IDE
  └─ Run / Test configuration ────────> JVM chạy ứng dụng và test trong IDE

Build configuration
  ├─ Java release / compiler options ─> Ngôn ngữ, API và bytecode đích
  ├─ Java toolchain ───────────────────> JDK dùng cho tác vụ hỗ trợ toolchain
  └─ Test runtime / launcher ─────────> JVM thực sự chạy test

(*) Còn phụ thuộc cấu hình riêng của build tool và môi trường khởi chạy.
```

Do đó, chỉ thấy IDE hiển thị **Project SDK = 17** hoặc lệnh `java -version` in ra **17** chưa đủ kết luận toàn bộ dự án dùng Java 17.

## 2. Chọn một hợp đồng phiên bản rõ ràng

Trước khi cấu hình, hãy chốt mục tiêu của dự án:

- **Mã nguồn Java 17:** sử dụng các cú pháp đã chính thức trong Java 17.
- **API nền tảng Java 17:** không vô tình gọi API chỉ xuất hiện trong JDK mới hơn.
- **Bytecode Java 17:** file `.class` dùng class-file major version **61**.
- **Runtime Java 17:** ứng dụng và các bài test cần chạy trên JVM 17 nếu Java 17 là môi trường triển khai cần hỗ trợ.

Đây là bốn điều kiện liên quan nhưng khác nhau. Ví dụ `sourceCompatibility = 17` không phải lúc nào cũng chặn việc tham chiếu API mới của JDK đang dùng để biên dịch. Khi cần ràng buộc chính xác ngôn ngữ, API và bytecode Java 17, hãy dùng **`javac --release 17`** (hoặc cấu hình tương đương của Maven/Gradle).

Với một bài thực hành Java 17 thuần, có thể đặt mục tiêu đơn giản:

```text
JDK cài trên máy:       17
Terminal java/javac:    17
IDE Project SDK:        17
Gradle/Maven compiler:  --release 17
Application JVM:        17
Unit-test JVM:          17
CI test JVM:            17
```

Đây là **mục tiêu cấu hình**, không phải yêu cầu mọi công cụ IDE hoặc build hiện đại đều bắt buộc phải tự chạy trên JDK 17. Một số bản IDE, extension hoặc phiên bản Gradle mới có yêu cầu runtime khác; trường hợp đó có thể để công cụ chạy trên JDK được hỗ trợ, đồng thời chọn toolchain và test JVM 17 cho dự án.

## 3. Cài JDK 17 và nhận biết đúng bộ JDK

Java 17 là bản **LTS**. Có thể sử dụng bản phân phối OpenJDK 17 phù hợp hệ điều hành, kiến trúc CPU và chính sách của môi trường thực hành, chẳng hạn Eclipse Temurin, Amazon Corretto, Microsoft Build of OpenJDK hoặc Oracle JDK. Cần phân biệt rõ **JDK** với môi trường chỉ dùng để chạy Java: bài thực hành có biên dịch phải có `javac`.

Thư mục gốc của JDK thường có cấu trúc:

```text
<JDK_17_HOME>/
├── bin/
│   ├── java      (hoặc java.exe trên Windows)
│   ├── javac     (hoặc javac.exe trên Windows)
│   └── javap     (hoặc javap.exe trên Windows)
├── conf/
├── jmods/
└── release
```

`JAVA_HOME` phải trỏ đến **thư mục gốc của JDK**, không trỏ đến `bin`, `java.exe` hoặc `javac.exe`. Ví dụ đường dẫn chỉ có tính minh họa: cần thay bằng đường dẫn JDK 17 đã cài trên máy.

### Windows PowerShell

Kiểm tra phiên bản và các vị trí đang được hệ điều hành tìm thấy:

```powershell
java -version
javac -version
$env:JAVA_HOME
where.exe java
where.exe javac
Get-Command java -All | Select-Object Name, Source
Get-Command javac -All | Select-Object Name, Source
```

Để chọn JDK 17 **chỉ cho phiên PowerShell hiện tại**:

```powershell
# Thay bằng thư mục cài đặt JDK 17 thực tế.
$env:JAVA_HOME = 'C:\Java\jdk-17'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

Test-Path "$env:JAVA_HOME\bin\javac.exe"
& "$env:JAVA_HOME\bin\java.exe" -version
java -version
javac -version
```

`Test-Path` cần trả về `True`. Thiết lập này chỉ tồn tại trong cửa sổ terminal hiện tại. Muốn dùng lâu dài, hãy đặt `JAVA_HOME` trong **Environment Variables** của Windows và đưa `%JAVA_HOME%\bin` lên `Path` theo thứ tự mong muốn; sau đó **mở terminal mới** để nhận biến môi trường mới. Kiểm tra lại `where.exe java` vì máy có thể có nhiều thư mục Java trong `Path`.

Lưu ý: một cửa sổ IDE đã mở trước khi chỉnh biến môi trường có thể vẫn giữ môi trường cũ; khởi động lại IDE hoặc chỉnh JDK trực tiếp trong phần cấu hình của nó.

### macOS

Trên macOS có thể liệt kê các JDK đã cài và chọn phiên bản 17:

```bash
/usr/libexec/java_home -V
export JAVA_HOME=$(/usr/libexec/java_home -v 17)
export PATH="$JAVA_HOME/bin:$PATH"

echo "$JAVA_HOME"
command -v java
command -v javac
java -version
javac -version
```

Nếu lệnh `java_home -v 17` không tìm thấy JDK, cần cài JDK 17 đúng kiến trúc rồi thử lại. Muốn sử dụng trong terminal mới, đặt các lệnh `export` vào file khởi tạo shell đang dùng, chẳng hạn `~/.zshrc` cho nhiều cấu hình Zsh. Chỉ đặt vào file phù hợp với cách shell được khởi chạy thực tế.

### Linux

Trên Linux, đường dẫn JDK khác nhau giữa bản phân phối và phương thức cài đặt. Hãy tìm đường dẫn thực tế trước khi cấu hình:

```bash
type -a java
type -a javac
readlink -f "$(command -v java)"
readlink -f "$(command -v javac)"
java -version
javac -version
```

Sau khi xác định đúng thư mục gốc JDK 17:

```bash
# Ví dụ; sửa đường dẫn theo cài đặt trên máy.
export JAVA_HOME=/usr/lib/jvm/jdk-17
export PATH="$JAVA_HOME/bin:$PATH"

test -x "$JAVA_HOME/bin/javac" && echo "JDK đã sẵn sàng"
"$JAVA_HOME/bin/java" -version
java -version
javac -version
```

Trên một số bản Linux, `update-alternatives` hoặc `alternatives` quản lý `java`/`javac` mặc định. Không nên tự suy luận rằng việc đổi một liên kết `java` sẽ tự đổi cả `javac`; kiểm tra cả hai. Đối với máy dùng chung hoặc nhiều dự án, ưu tiên cấu hình theo shell/dự án thay vì đổi JDK mặc định toàn hệ thống một cách không cần thiết.

### Khi kết quả `java` và `javac` khác nhau

Ví dụ:

```text
java -version   -> 21
javac -version  -> 17.0.x
JAVA_HOME       -> thư mục JDK 17
```

Trường hợp này thường xảy ra vì `PATH` ưu tiên một thư mục `bin` khác. Phải xem đường dẫn lệnh đang được tìm thấy, không chỉ đọc giá trị `JAVA_HOME`. Ngay cả khi cả hai lệnh cùng in `17`, chúng vẫn có thể đến từ các bản phân phối/cài đặt khác nhau; nếu cần tái lập môi trường chính xác, kiểm tra đường dẫn và vendor bằng `java -XshowSettings:properties -version` rồi tìm các thuộc tính như `java.home`, `java.vendor`.

## 4. Đồng bộ JDK trong IDE

IDE thường có **JVM chạy chính IDE**, **JDK gán cho dự án**, **JVM chạy build tool** và **JVM cho Run/Test configuration**. Các vị trí này có thể độc lập. Mục tiêu là dự án được phân tích theo Java 17 và các tác vụ thực tế dùng JDK phù hợp.

### IntelliJ IDEA

Với một dự án Java 17:

1. Vào **File → Project Structure → SDKs**, thêm đường dẫn JDK 17 nếu chưa có.
2. Trong **Project**, chọn **Project SDK = JDK 17**, và chọn **Language level = 17** hoặc mức lấy theo SDK phù hợp.
3. Kiểm tra **Modules → Dependencies** để chắc chắn module đang dùng Project SDK hoặc SDK 17 được chọn rõ ràng.
4. Với dự án Gradle, vào **Settings → Build, Execution, Deployment → Build Tools → Gradle**, xem **Gradle JVM**. Đây là JVM chạy Gradle từ IDE; kiểm tra thêm tùy chọn **Build and run using** và **Run tests using** để biết IDE có giao việc cho Gradle hay không.
5. Với dự án Maven, xem thiết lập **Maven Runner → JRE** và cấu hình JDK cho **Importer** nếu phiên bản IDEA hiện tại cung cấp mục đó.
6. Mở **Run → Edit Configurations**, kiểm tra JRE/JDK trong cấu hình chạy chương trình và JUnit. Cấu hình dùng Gradle test runner có thể lấy JVM từ Gradle toolchain, không phải từ Project SDK đơn thuần.

Tên menu có thể thay đổi giữa các phiên bản IntelliJ IDEA. Điều cần kiểm tra là **SDK của source**, **JVM của tiến trình Gradle/Maven** và **JVM của Run/Test**, thay vì chỉ tìm một ô cài đặt duy nhất. Runtime tích hợp của chính IntelliJ (thường là JetBrains Runtime) có thể có phiên bản khác JDK 17 mà dự án dùng; không cần ép runtime của IDE về 17 nếu phiên bản IDE yêu cầu JDK mới hơn.

### Visual Studio Code với Java Extension Pack

Trong VS Code, mở **Command Palette → Java: Configure Java Runtime** để xem các runtime Java mà Java extension phát hiện và cấu hình cho dự án. Với thư mục Java không do Maven/Gradle quản lý, có thể chỉ định Java 17 bằng `settings.json`:

```json
{
  "java.configuration.runtimes": [
    {
      "name": "JavaSE-17",
      "path": "C:\\Java\\jdk-17",
      "default": true
    }
  ]
}
```

Đây là ví dụ đường dẫn Windows; trên macOS/Linux dùng đường dẫn JDK của hệ tương ứng. Đối với dự án Maven/Gradle, **`pom.xml`/`build.gradle` và toolchain vẫn phải được cấu hình đúng** vì chúng quyết định nhiều tác vụ build/test thực tế.

Một số phiên bản Java Language Server cần JDK mới hơn 17 để **chạy language server**, trong khi dự án vẫn được biên dịch cho Java 17. Thuộc tính `java.jdt.ls.java.home` (khi extension đang dùng hỗ trợ) chọn JDK khởi chạy language server; nó không thay thế `java.configuration.runtimes` hoặc cấu hình compiler của Maven/Gradle. Chọn runtime cho extension theo yêu cầu của **phiên bản extension đang cài**, rồi cấu hình JDK dự án là 17.

### Eclipse IDE

Trong Eclipse, kiểm tra các vị trí:

1. **Preferences → Java → Installed JREs**: thêm đường dẫn **JDK 17** rồi chọn đúng JDK cho dự án.
2. **Project → Properties → Java Build Path → Libraries**: kiểm tra `JRE System Library` hoặc execution environment tương ứng **JavaSE-17**.
3. **Project → Properties → Java Compiler**: kiểm tra compiler compliance level 17 và thiết lập nguồn/đích nếu dự án có cấu hình riêng.
4. **Run Configurations / Debug Configurations → JRE**: chọn JDK 17 cho chương trình hoặc JUnit launch khi cần chạy trực tiếp từ Eclipse.
5. Nếu dự án import qua Maven/Gradle, kiểm tra thêm cấu hình build tool và làm mới cấu hình dự án sau khi chỉnh `pom.xml`/`build.gradle`.

Execution environment `JavaSE-17` mô tả môi trường Java 17 của dự án; JVM chạy chính Eclipse có thể khác. Với IDE nào cũng vậy, **thao tác Run trong IDE** và **lệnh `gradlew test`/`mvn test` trong terminal** không tự động đồng nghĩa với việc dùng cùng test JVM.

## 5. Gradle: phân biệt JVM chạy Gradle và Java toolchain

Gradle có ít nhất hai quyết định độc lập:

1. **Gradle JVM/daemon JVM:** JVM chạy chính Gradle. JVM này phải đáp ứng yêu cầu của phiên bản Gradle được dự án sử dụng.
2. **Java toolchain:** JDK mà các tác vụ Java có hỗ trợ toolchain dùng để biên dịch, chạy test và tạo tài liệu.

Nên dùng **Gradle Wrapper** của dự án để cố định phiên bản Gradle thay vì phụ thuộc vào một bản Gradle cài toàn cục:

```bash
# macOS/Linux, khi dự án có Gradle Wrapper
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains
.\gradlew.bat clean test
```

Kết quả `--version` cho biết phiên bản Gradle và thông tin JVM đang khởi chạy Gradle; format có thể thay đổi theo bản Gradle. Tác vụ `javaToolchains` cho thấy những JDK Gradle có thể phát hiện và dùng làm toolchain. **Không kết luận JDK biên dịch từ `./gradlew --version` một mình**.

### Cấu hình Gradle Groovy DSL cho Java 17

Trong `build.gradle`:

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
    options.release = 17
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()  // Khi dự án dùng JUnit Jupiter/JUnit Platform.
}
```

Ý nghĩa:

- `java.toolchain` yêu cầu các tác vụ Java hỗ trợ toolchain sử dụng JDK có **feature version 17**. Nó không bắt Gradle daemon phải chạy trên JDK 17.
- `options.release = 17` đưa ràng buộc `--release 17` vào compiler Java, bảo vệ đồng thời cú pháp/bytecode/API nền tảng Java 17.
- Tác vụ `Test` tiêu chuẩn của Java plugin thường chọn Java launcher theo toolchain đã khai báo. Những tác vụ `Test`/`JavaExec` tự tạo hoặc plugin chuyên biệt có thể cấu hình launcher khác; phải kiểm tra cấu hình riêng của chúng.
- `useJUnitPlatform()` chỉ cần khi dự án chạy JUnit trên JUnit Platform; cần khai báo test dependencies phù hợp riêng. Không dùng cấu hình này để suy ra JDK của test.

Nếu muốn chỉ rõ **test JVM là Java 17** ngay tại tác vụ `Test`, có thể cấu hình Java launcher trong cùng `build.gradle`:

```groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Đoạn này hữu ích khi cần đọc ngay trong build script rằng unit test phải chạy trên JDK 17, đặc biệt trong dự án có nhiều JVM hoặc nhiều test task.

Với dự án dùng **Gradle Kotlin DSL**, cấu hình tương ứng trong `build.gradle.kts`:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

### Khi Gradle không tìm thấy JDK 17

Thông báo kiểu **“No matching toolchains found”** cho thấy Gradle chưa tìm được toolchain đáp ứng yêu cầu. Kiểm tra:

- JDK 17 có được cài và có đường dẫn `bin/javac` hợp lệ hay chưa.
- `./gradlew -q javaToolchains` có thấy JDK 17 hay không.
- Các tiêu chí `languageVersion`, `vendor`, `implementation` (nếu dự án ràng buộc thêm) có khớp JDK đang cài không.
- Dự án có chủ động cấu hình nguồn tải toolchain tự động hay không. **Không giả định** Gradle luôn tự tải JDK còn thiếu: cơ chế cung cấp toolchain phụ thuộc phiên bản Gradle và cấu hình repository/resolver.

Khi cần, có thể chỉ ra nơi tìm JDK bằng `org.gradle.java.installations.paths` trong `gradle.properties` theo cú pháp và quy ước của bản Gradle đang dùng. Không nên đưa một đường dẫn máy cá nhân cố định vào cấu hình chung cho toàn nhóm; ưu tiên toolchain detection, quy ước cài đặt của CI hoặc cấu hình tại máy người dùng.

### Khi Gradle daemon vẫn chạy JDK khác

`JAVA_HOME` là một nguồn để xác định JVM khởi động Gradle, nhưng Gradle cũng có cấu hình JVM riêng: **Gradle JVM trong IDE**, `org.gradle.java.home` và, ở những phiên bản hỗ trợ, **Daemon JVM criteria** của dự án. Vì vậy, `java -version` trong terminal có thể là 17 trong khi Gradle daemon chạy một JDK khác.

Để xử lý, kiểm tra `./gradlew --version`, cấu hình Gradle JVM của IDE, `gradle.properties` ở dự án và môi trường người dùng; nếu dự án dùng tiêu chí JVM cho daemon, kiểm tra cả `gradle/gradle-daemon-jvm.properties`. Chọn JVM chạy Gradle phù hợp **ma trận tương thích của phiên bản Gradle**, rồi giữ **Java toolchain 17** cho tác vụ biên dịch/test. Không vội đổi toàn bộ máy về JDK mới chỉ vì một phiên bản Gradle có yêu cầu runtime mới.

## 6. Maven: `JAVA_HOME`, `--release` và Maven Toolchains

Maven thông thường chạy bằng JDK mà lệnh Maven nhận từ môi trường khởi chạy; hãy kiểm tra bằng:

```bash
mvn -version
mvn clean test
```

Nếu dự án có **Maven Wrapper**, sử dụng wrapper của dự án để giữ phiên bản Maven nhất quán:

```bash
# macOS/Linux
./mvnw -version
./mvnw clean test
```

```powershell
# Windows PowerShell
.\mvnw.cmd -version
.\mvnw.cmd clean test
```

`mvn -version` hiển thị phiên bản Maven và **Java version / Java home mà Maven đang chạy**. Nếu Maven báo JDK 11 khi dự án yêu cầu compiler Java 17, chỉ đổi `pom.xml` thành `release=17` sẽ không làm JDK 11 có khả năng biên dịch Java 17.

### Cấu hình mức Java 17 trong `pom.xml`

Với dự án Maven thông thường, đặt:

```xml
<project>
    <!-- Các phần tử project, modelVersion, groupId, artifactId... của dự án. -->
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
</project>
```

Đây là **đoạn cấu hình minh họa**, cần đặt vào `pom.xml` hợp lệ sẵn có của dự án (không thay toàn bộ POM bằng đoạn trên). `maven.compiler.release` được Maven Compiler Plugin hỗ trợ và sử dụng để chỉ định `--release 17`; dự án phải dùng phiên bản compiler plugin thích hợp và JDK compiler hỗ trợ target 17.

Nếu đang dùng JDK 17 để chạy Maven và không có cấu hình riêng, việc thống nhất `JAVA_HOME`, `mvn -version` và `maven.compiler.release=17` thường đủ cho dự án đơn giản. Tuy nhiên, nếu Maven chạy trên JDK mới hơn, các unit test có thể chạy trên JVM đang chạy Maven hoặc JVM khác theo cấu hình Surefire/Failsafe.

### Maven Toolchains khi một máy có nhiều JDK

Maven Toolchains cho phép các plugin có hỗ trợ toolchain dùng một JDK được chọn mà không phụ thuộc hoàn toàn vào JDK chạy Maven. Ví dụ file người dùng `~/.m2/toolchains.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/jdk-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

Đường dẫn là ví dụ trên hệ Unix; thay bằng thư mục JDK thực tế. File này đặt ở máy người dùng/CI, không yêu cầu mọi thành viên có cùng đường dẫn. Để Maven **chọn** JDK 17, thêm Maven Toolchains Plugin vào phần `<build><plugins>` của POM:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.2.0</version>
    <executions>
        <execution>
            <goals>
                <goal>toolchain</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <toolchains>
            <jdk>
                <version>17</version>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
```

Maven Toolchains không phải công tắc khiến **mọi plugin** lập tức chạy Java 17: chỉ những plugin và tác vụ biết sử dụng toolchain mới tôn trọng lựa chọn đó. Cần đảm bảo Maven Compiler Plugin và các plugin test được cấu hình tương thích. Với Maven Surefire Plugin có hỗ trợ, có thể chỉ rõ JDK cho tiến trình kiểm thử:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <!-- Dùng phiên bản Surefire dự án đang quản lý có hỗ trợ jdkToolchain. -->
    <configuration>
        <jdkToolchain>
            <version>17</version>
        </jdkToolchain>
    </configuration>
</plugin>
```

Nếu dùng Maven Failsafe Plugin cho integration test, phải xem cấu hình JVM/toolchain của **Failsafe** riêng. Cấu hình Surefire không tự đảm bảo mọi bài integration test cũng dùng cùng JVM. Khi Maven có nhiều toolchain khả dụng, xem log plugin và xác minh ngay trong JVM của test để biết JDK nào thực sự được chọn.

## 7. Kiểm chứng JDK thực sự chạy ứng dụng và kiểm thử

Lệnh `java -version`, thông tin IDE và `--release 17` chỉ cho biết **một phần cấu hình**. Muốn biết chương trình thực sự đang chạy ở JDK nào, hãy in thông tin từ **chính tiến trình đó**.

### Kiểm tra từ một chương trình Java

Lưu thành `RuntimeProbe.java`:

```java
public class RuntimeProbe {
    public static void main(String[] args) {
        System.out.println("Java version: " + System.getProperty("java.version"));
        System.out.println("Feature version: " + Runtime.version().feature());
        System.out.println("Java home: " + System.getProperty("java.home"));
        System.out.println("Java vendor: " + System.getProperty("java.vendor"));
        System.out.println("Class format: " + System.getProperty("java.class.version"));
    }
}
```

Biên dịch và chạy trong terminal:

```bash
javac --release 17 RuntimeProbe.java
java RuntimeProbe
```

Ví dụ đầu ra khi **thực sự chạy trên JDK 17**:

```text
Java version: 17.0.x
Feature version: 17
Java home: <đường dẫn tới JDK 17 đang chạy>
Java vendor: <nhà cung cấp JDK>
Class format: 61.0
```

Giá trị `java.home` mới là nơi runtime đang chạy; không mặc định đồng nhất nó với `$JAVA_HOME` hoặc đường dẫn JDK đã chọn trong editor. `java.class.version` ở đây mô tả JVM hiện tại; để xem **major version của file `.class` đã biên dịch**, cần đọc file class bằng `javap -verbose` và tìm dòng `major version` (Java 17 là 61).

### Kiểm tra trong JUnit 5

Khi dự án đã có JUnit Jupiter và chạy test bằng Gradle/Maven/IDE, có thể thêm **bài kiểm tra môi trường tạm thời**:

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class TestRuntimeProbe {
    @Test
    void testJvmMustBeJava17() {
        System.out.println("Test java.version = " + System.getProperty("java.version"));
        System.out.println("Test java.home = " + System.getProperty("java.home"));

        assertEquals(17, Runtime.version().feature(),
                "Bài kiểm thử này phải chạy trên JVM 17");
    }
}
```

Chạy bài test **một lần trong IDE và một lần qua lệnh build** rồi so sánh `Test java.home`. Nếu hai kết quả khác nhau, hai đường chạy test đang chọn hai JVM khác nhau.

`assertEquals(17, ...)` là ràng buộc phù hợp khi **bài tập hoặc môi trường triển khai yêu cầu runtime đúng Java 17**. Nếu dự án chủ ý kiểm tra tương thích trên nhiều JDK (ví dụ 17 và 21), không nên giữ assertion cố định này trong bộ test chung; thay bằng kiểm tra tương thích phù hợp mục tiêu và dùng ma trận CI khi cần.

Lưu ý: nhiều test runner ẩn hoặc gom `System.out` vào báo cáo. Khi không thấy đầu ra trên console, xem báo cáo test của Gradle/Maven hoặc cấu hình test logging; **một test pass không tự chứng minh đúng JVM nếu chưa kiểm tra runtime**.

## 8. Duy trì cùng cấu hình trong CI

Trên máy CI, lệnh `java` mặc định của runner có thể khác máy phát triển. Cần cài/chọn JDK theo hợp đồng dự án trong pipeline, sau đó dùng wrapper của build tool:

```text
CI job
  ├─ Provision/select JDK 17
  ├─ Print java -version, javac -version, JAVA_HOME
  ├─ Gradle: ./gradlew --version && ./gradlew clean test
  │           hoặc
  └─ Maven:  ./mvnw -version   && ./mvnw clean verify
```

Nếu dùng toolchain, công cụ build có thể chạy trên JDK khác 17 theo chủ đích; trong trường hợp đó phải cung cấp **cả JDK dùng cho Gradle/Maven lẫn JDK 17 mà toolchain/test launcher cần**, và ghi log để truy vết. Với Maven Failsafe, `verify` thường là lifecycle chạy integration test đã cấu hình; với Gradle, chạy các test task tương ứng dự án, vì `test` không nhất thiết bao gồm mọi integration test tùy chỉnh.

Những thứ nên nằm trong repository để có thể tái lập:

- **Gradle Wrapper/Maven Wrapper** và tệp cấu hình tương ứng để chọn đúng bản build tool.
- **Cấu hình Java release 17** (`options.release` hoặc `maven.compiler.release`).
- **Cấu hình toolchain/test launcher** nếu dự án cần chạy trên nhiều JDK khác nhau.
- **Hướng dẫn cài JDK 17**, cách kiểm tra môi trường và yêu cầu CI.

Không nên commit đường dẫn JDK tuyệt đối thuộc riêng một máy lập trình viên hoặc thông tin môi trường cá nhân vào cấu hình chung. Những tệp như `.java-version`, `.sdkmanrc`, `mise.toml` có thể hữu ích nếu cả nhóm đã thống nhất một trình quản lý JDK; chúng là **công cụ chọn phiên bản**, không thay thế việc cấu hình đúng compiler và test runtime của Gradle/Maven.

## 9. Những lỗi thường gặp và cách truy nguyên

| Triệu chứng | Nguyên nhân thường gặp | Việc cần kiểm tra |
| --- | --- | --- |
| `java -version` là 17 nhưng `javac -version` là 21 | `PATH` đang trỏ tới hai cài đặt khác nhau. | `where.exe` hoặc `type -a`/`command -v`; sắp lại `PATH`. |
| `JAVA_HOME` là 17 nhưng `mvn -version` báo Java khác | Maven được khởi chạy từ môi trường khác, IDE runner khác, hoặc cấu hình runtime đang ưu tiên JDK khác. | `mvn -version`, đường dẫn Maven thực tế, Maven Runner JRE trong IDE. |
| `release version 17 not supported` hoặc `invalid target release: 17` | Compiler đang chạy không hỗ trợ target 17 (chẳng hạn JDK cũ hơn 17). | JDK của `javac`/Maven compiler hoặc Gradle toolchain. |
| `No matching toolchains found` | Toolchain yêu cầu Java 17 nhưng không phát hiện JDK phù hợp. | Đường dẫn JDK, `javaToolchains`, tiêu chí toolchain và cấu hình cấp phát JDK. |
| Gradle không khởi động với JDK đang chọn | Phiên bản Gradle và JVM chạy Gradle không tương thích. | Gradle Wrapper, `./gradlew --version`, Gradle JVM/daemon JVM criteria. |
| Biên dịch `--release 17` thành công nhưng chạy trên JDK 17 bị lỗi | Có thể do runtime thực tế khác, thư viện phụ thuộc không tương thích, hoặc hành vi không nằm trong phạm vi compiler kiểm tra. | `java.home` khi chạy, dependency versions, log đầy đủ và test trên JDK 17 thật. |
| IDE báo lỗi cú pháp Java 17 nhưng terminal build được | Project SDK, module SDK hoặc language level của IDE chưa đồng bộ. | Project/Module SDK, Java compiler settings, cấu hình import Maven/Gradle. |
| Test pass trong IDE, fail trong CI | JVM test, biến môi trường, dependency, hệ điều hành hoặc cấu hình task khác nhau. | `java.home` từ cả hai tiến trình test, lệnh wrapper và log CI. |
| Test compile được nhưng không tìm thấy hoặc không chạy | JUnit engine/dependencies hoặc cấu hình test runner không phù hợp; không nhất thiết do JDK. | JUnit Platform, Surefire/Gradle `Test`, tên test, báo cáo chạy test. |
| `UnsupportedClassVersionError` | JVM đang chạy không hỗ trợ major version của class đã tạo. | Major version thực tế bằng `javap -verbose` và phiên bản JVM chạy. |

**Cách chẩn đoán theo lớp**: tìm lệnh hoặc tác vụ **thất bại đầu tiên**, xác định nó chạy trong terminal, IDE, Gradle daemon, Maven process hay test JVM; kiểm tra **đúng tiến trình đó** trước khi thay đổi cấu hình. Lỗi do compiler chọn nhầm JDK sẽ không được giải quyết bền vững bằng cách chỉ đổi JRE của một Run configuration.

### Phân biệt lỗi tương thích bytecode với lỗi thiếu API

Giả sử một `.class` được biên dịch trên JDK mới hơn rồi chạy bằng Java 17. Nếu file class dùng major version vượt **61**, JVM 17 sẽ từ chối nạp class với `UnsupportedClassVersionError`. Trường hợp source và target đều đặt 17 nhưng compiler đang dùng API chỉ có trên JDK mới hơn cũng có thể dẫn đến lỗi khi triển khai; vì vậy **`--release 17` và chạy test trên JDK 17** giải quyết hai lớp vấn đề bổ sung cho nhau.

## 10. Quy trình thực hành đồng bộ từ đầu đến cuối

Với một dự án Java 17 mới hoặc vừa được import sang máy khác, có thể làm tuần tự:

1. **Cài JDK 17**. Xác nhận có `java` và `javac` trong cùng một thư mục JDK.
2. **Chỉnh terminal**. Kiểm tra `JAVA_HOME`, `PATH`, `java -version`, `javac -version` và đường dẫn lệnh được hệ điều hành chọn.
3. **Cấu hình build script**. Với Gradle, khai báo toolchain 17 và `options.release = 17`. Với Maven, khai báo `maven.compiler.release=17`; dùng toolchains nếu cần phân tách JDK chạy Maven với JDK compiler.
4. **Dùng wrapper** (`gradlew` hoặc `mvnw` nếu repository có) để cả nhóm chạy cùng bản build tool. Kiểm tra JVM mà build tool đang dùng.
5. **Cấu hình IDE**. Chọn Project/Module SDK 17, language level 17, rồi kiểm tra Gradle JVM/Maven Runner và Run/Test configuration.
6. **Biên dịch, chạy ứng dụng và kiểm thử**. In `java.version`, `java.home` từ tiến trình ứng dụng/test để xác nhận runtime thực tế.
7. **Cấu hình CI tương ứng**. Cho CI dùng wrapper và cung cấp JDK 17 cho các tác vụ yêu cầu; so sánh log phiên bản giữa local và CI khi kết quả khác nhau.

Ví dụ một hệ thống **đồng bộ đúng theo mục tiêu Java 17** có thể hiển thị:

```text
Terminal java/javac   : 17 / 17
IntelliJ Project SDK  : 17
Gradle toolchain      : 17
Compiler --release    : 17
JUnit test java.home  : <đường dẫn JDK 17>
CI compiler/test JDK  : 17
```

Nếu Gradle hoặc Java Language Server dùng một JVM mới hơn theo yêu cầu riêng của công cụ, hệ thống vẫn có thể đáp ứng mục tiêu Java 17 miễn là **compiler, API đích, bytecode và runtime kiểm thử/triển khai** được cấu hình và xác minh đúng. Điểm mấu chốt là **đồng bộ theo vai trò và có bằng chứng từ tiến trình thực tế**, thay vì cố ép mọi phần mềm trong máy dùng cùng một giá trị `JAVA_HOME`.
