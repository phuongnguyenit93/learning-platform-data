# Manifest, Main-Class và cách chạy JAR trong Gradle

## 1. Bài toán: JAR tạo thành công nhưng không chạy được

Trong Gradle, bạn có thể chạy `./gradlew jar` và thấy một file `.jar` trong `build/libs/`, nhưng khi gõ:

```bash
java -jar build/libs/manifest-lab-1.0.0.jar
```

JVM báo:

```text
no main manifest attribute, in build/libs/manifest-lab-1.0.0.jar
```

Thông báo này **không nói rằng file JAR bị hỏng**. JAR là một archive chứa Java classes, resources và metadata. Một thư viện JAR có thể hợp lệ nhưng không có ứng dụng để chạy. Muốn chạy bằng `java -jar`, JVM phải đọc được **Main-Class** ở manifest, rồi tìm được lớp và phương thức `main` hợp lệ.

Trong môn **Build Tool Gradle → Đóng gói**, bài này tập trung vào ba câu hỏi:

1. **Đóng gói:** Gradle lấy file nào từ `sourceSets.main` để tạo JAR, manifest nằm đâu?
2. **Entry point:** `Main-Class` khác `application.mainClass` thế nào, và khi nào dùng `java -jar` hoặc `java -cp`?
3. **Runtime dependencies:** tại sao `implementation` không làm plain JAR tự mang toàn bộ thư viện phụ thuộc; cần manifest `Class-Path`, distribution hoặc fat JAR trong trường hợp nào?

Sau bài học, người đọc sẽ có thể tự xây một JAR Java 17+ chạy thật; giải nén, kiểm tra manifest; chạy trên Linux/macOS/Windows; truyền argument; xử lý tình huống class/resource không có; hiểu ranh giới giữa thin JAR, executable JAR, application distribution và uber JAR.

Ví dụ sử dụng **Gradle Groovy DSL** (`build.gradle`), Java 17+ và Gradle Wrapper. Các ví dụ Java baseline không cần thư viện ngoài; phần thực hành Commons Lang là một **biến thể riêng** cần Maven Central.

## 2. Cấu trúc một file JAR

**JAR (Java ARchive)** dựa trên định dạng ZIP. Một ứng dụng nhỏ có thể có:

```text
manifest-lab-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── example/
│   └── JarHello.class
└── messages.properties
```

- `example/JarHello.class`: bytecode của lớp Java `example.JarHello`.
- `messages.properties`: resource từ `src/main/resources`, được đặt ở classpath root trong archive.
- `META-INF/MANIFEST.MF`: file metadata theo JAR File Specification; có thể chứa `Main-Class`, `Class-Path` và thông tin đóng gói.
- Một JAR lớn còn có thể chứa `META-INF/services`, native resources, module metadata hoặc signature files.

**Phân biệt:** tên `example/JarHello.class` dùng dấu `/` trong archive; tên Java class trong manifest dùng dấu chấm `example.JarHello`. Đừng chép đường dẫn file `.class` vào Main-Class.

Với Java plugin, task `jar` đóng gói **sourceSets.main.output**: compiled classes và processed resources của main. Nó không mặc định nhét file `.java`, test sources, test resources hay mọi external dependency JAR vào bên trong.

### 2.1. Ba vai trò JAR thường gặp

| Kiểu gói | Chứa gì | Chạy thế nào |
| --- | --- | --- |
| **Library JAR** | Classes/resources để project khác sử dụng. | Được đưa vào classpath/module path; có thể không có Main-Class. |
| **Executable thin JAR** | App classes/resources và Main-Class, thường không chứa external libs. | `java -jar` khi không cần libs ngoài hoặc classpath đã được cấp đúng cách. |
| **Fat/uber JAR** | App classes cộng dependency classes/resources được đóng gói chung. | Có thể `java -jar` khi launcher/manifest và resource merging đúng. |

Còn **application distribution** là một folder hoặc ZIP/TAR chứa app JAR, runtime dependency JARs và startup scripts; nó không nhất thiết là một fat JAR.

## 3. Manifest và những header quan trọng

Manifest nằm ở path chuẩn:

```text
META-INF/MANIFEST.MF
```

Đối với lab, các dòng đáng chú ý sẽ tương tự:

```text
Manifest-Version: 1.0
Main-Class: example.JarHello
Implementation-Title: manifest-lab
Implementation-Version: 1.0.0
```

Đây là **trích đoạn nội dung**, không bảo đảm thứ tự chính xác hoặc tất cả headers; Gradle/JDK có thể thêm metadata và line endings khác.

| Header | Vai trò |
| --- | --- |
| `Manifest-Version: 1.0` | Phiên bản **định dạng manifest**, không phải Java 1.0, Gradle 1.0 hoặc version ứng dụng. |
| `Main-Class: example.JarHello` | Fully qualified name của Java class có phương thức main; launcher dùng khi `java -jar`. |
| `Implementation-Title` | Thông tin mô tả tên thành phần; tùy chọn, không tham gia Java class loading. |
| `Implementation-Version` | Thông tin mô tả version thành phần; tùy chọn, không quyết định Java runtime. |
| `Class-Path` | Relative URLs của các JAR/directories bên ngoài cần bổ sung vào search path. |
| `Automatic-Module-Name` | Module name cho automatic module trên JPMS module path; không phải Main-Class. |
| `Multi-Release: true` | Cho phép JDK nhận version-specific entries dưới `META-INF/versions`; không thay Main-Class. |

Manifest có **main section** và có thể có sections cho entries riêng. Định dạng chuẩn yêu cầu header dạng `Name: value`, một dấu cách sau dấu hai chấm, các sections cách nhau bằng dòng trống. Dòng manifest dài được gấp theo quy tắc **72 bytes/line** với continuation lines bắt đầu bằng dấu cách; đừng tự viết một JAR binary và cố giữ headers bằng editor text đơn giản.

**Không sửa manifest bằng cách tạo một `manifest.txt` ở root JAR**: JVM chỉ nhận file đúng path. Dùng `Jar.manifest` API của Gradle để tạo đúng cấu trúc.

### 3.1. Main-Class cần trùng Java binary class name

Trong Java 17, mẫu entry point tương thích rộng là:

```java
package example;

public final class JarHello {
    private JarHello() {
    }

    public static void main(String[] args) {
        System.out.println("Hello, Gradle!");
    }
}
```

`package example` khiến tên lớp là `example.JarHello`. `public static void main(String[] args)` cho phép Java launcher gọi entry point mà không tạo instance, đồng thời truyền CLI arguments qua mảng `String[]`.

Các giá trị sai điển hình:

| Giá trị Main-Class | Kết quả |
| --- | --- |
| `example.JarHello` | Đúng cho lab. |
| `JarHello` | Sai vì thiếu package. |
| `example/JarHello` | Sai vì dùng path separator. |
| `example.JarHello.class` | Sai vì thêm đuôi file. |
| `src.main.java.example.JarHello` | Sai vì đưa source root vào Java package. |
| `example.DoesNotExist` | Sai vì class không nằm trong archive. |

Khi class không được tìm hoặc không có main method đúng, lỗi thường là `Could not find or load main class`, `ClassNotFoundException` hoặc thông báo thiếu phương thức main; hãy đọc lỗi thật và kiểm tra entries.

## 4. Java plugin khác Application plugin

### 4.1. Plugin java và Jar task

```groovy
plugins {
    id 'java'
}
```

Java plugin tạo `compileJava`, `processResources`, `classes`, `jar`, `test`, `build`. `jar` lấy compiled main classes và resources rồi tạo archive. Plugin không tự đoán entry point: một thư viện JAR không nhất thiết có `main`.

Sơ đồ:

```text
src/main/java/*.java        -> compileJava      -> build/classes/java/main
src/main/resources/**       -> processResources -> build/resources/main
                                                |
                                                v
                                             jar task
                                                |
                                                v
                                   build/libs/<name>-<version>.jar
```

`src/test/java`/`src/test/resources` thuộc source set test; chúng không vào main JAR theo convention.

### 4.2. Plugin application

```groovy
plugins {
    id 'application'
}

application {
    mainClass = 'example.JarHello'
}
```

Plugin `application` áp dụng Java và Distribution plugins, thêm:

- `run` (`JavaExec`): chạy class trong `application.mainClass`, với `sourceSets.main.runtimeClasspath`.
- `startScripts`: tạo shell script Unix-like và `.bat` của Windows.
- `installDist`: tạo directory distribution gồm app JAR, runtime libs, scripts.
- `distZip`, `distTar`: đóng gói distribution thành ZIP/TAR.

**Quan trọng:** `application.mainClass` giúp `run` và generated scripts biết class được chạy. Nó **không phải lời hứa rằng task `jar` đã có header Main-Class**. Nếu cần `java -jar`, bạn phải cấu hình manifest của JAR một cách tường minh.

| Thao tác | Cơ chế tìm class |
| --- | --- |
| `./gradlew run` | Application plugin dùng `application.mainClass` và runtime classpath. |
| `java -jar app.jar` | JVM đọc `Main-Class` trong `META-INF/MANIFEST.MF`. |
| `java -cp app.jar example.JarHello` | Java launcher dùng class được chỉ định trực tiếp; không cần Main-Class. |
| `installDist` startup script | Generated script cấu hình main class và runtime libraries theo distribution. |

## 5. Cấu hình Main-Class trong Gradle Groovy DSL

Cấu hình tối thiểu cho một app JAR:

```groovy
tasks.named('jar', Jar) {
    manifest {
        attributes(
            'Main-Class': 'example.JarHello'
        )
    }
}
```

- `tasks.named('jar', Jar)` chỉ cấu hình task đã có; không tạo task mới.
- `manifest` là metadata của Gradle `Jar` task.
- `attributes` nhận map header name → value.
- `Main-Class` phải là class Java **có trong archive và có main hợp lệ**.
- `java -jar` không cần Gradle cài ở máy nhận file, nhưng vẫn cần Java runtime đúng và dependency runtime sẵn sàng.

Có thể thêm metadata:

```groovy
tasks.named('jar', Jar) {
    manifest {
        attributes(
            'Main-Class': 'example.JarHello',
            'Implementation-Title': project.name,
            'Implementation-Version': project.version.toString()
        )
    }
}
```

Đây là **phương án đầy đủ thay cho phương án tối thiểu**, không cần copy hai blocks đồng thời. `Implementation-Version` là metadata **tùy chọn**; việc đặt version của project không tự bảo đảm JAR có header này nếu bạn không cấu hình.

### 5.1. Tránh hai nơi khai báo Main-Class không nhất quán

Nếu đã dùng Application plugin:

```groovy
application {
    mainClass = 'example.JarHello'
}
```

Bạn có thể dùng cùng giá trị để cấu hình Jar:

```groovy
tasks.named('jar', Jar) {
    manifest {
        attributes('Main-Class': application.mainClass.get())
    }
}
```

Đây là **thay thế** cho header literal; nó giả định mainClass đã được gán trước khi lấy `.get()`. Gradle hỗ trợ Provider API cho manifest attributes khi cần giữ lazy, nhưng đừng eager resolve giá trị phụ thuộc network/environment ở configuration phase chỉ để sinh header.

### 5.2. Đổi archive filename không tự tạo executable JAR

```groovy
tasks.named('jar', Jar) {
    archiveFileName = 'app.jar'
}
```

Cấu hình trên thay tên output thành `build/libs/app.jar` (nếu không đổi build directory); nó **không** đặt `Main-Class`. Khi đổi tên, mọi command và deployment script phải dùng filename mới. Cách khác là dùng `archiveBaseName`, `archiveVersion` và `archiveClassifier` của archive task.

## 6. Dự án runnable hoàn chỉnh: Java 17+, Gradle và resource

Ví dụ này **không phụ thuộc thư viện ngoài**, giúp thấy rõ sự khác biệt giữa lỗi Java, lỗi manifest và lỗi runtime classpath. Cần JDK 17+ và Gradle Wrapper tương thích. Với Gradle 9, JVM chạy Gradle phải là Java 17+.

### 6.1. Cấu trúc project

```text
manifest-lab/
├── gradlew
├── gradlew.bat
├── gradle/wrapper/gradle-wrapper.jar
├── gradle/wrapper/gradle-wrapper.properties
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/example/JarHello.java
        └── resources/messages.properties
```

Wrapper phải được tạo bằng `gradle wrapper` từ Gradle tương thích hoặc có sẵn qua `gradle init`. Chỉ tạo `build.gradle` không làm `gradlew` tự xuất hiện.

### 6.2. File settings.gradle

```groovy
rootProject.name = 'manifest-lab'
```

### 6.3. File build.gradle (toàn bộ)

```groovy
plugins {
    id 'application'
}

group = 'example'
version = '1.0.0'

application {
    mainClass = 'example.JarHello'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

tasks.named('jar', Jar) {
    manifest {
        attributes(
            'Main-Class': 'example.JarHello',
            'Implementation-Title': project.name,
            'Implementation-Version': project.version.toString()
        )
    }
}
```

**Đọc từng dòng:**

1. `application` bao gồm Java plugin, tạo task compile, resources, JAR, run và distribution.
2. `group='example'` là metadata nhóm, không phải Java package bắt buộc trùng. `version='1.0.0'` ảnh hưởng archive file name convention.
3. `application.mainClass` dùng cho Gradle `run` và startup scripts.
4. `options.release=17` kiểm tra Java source/API target Java 17 bằng compiler hỗ trợ; **không tự tải JDK 17**. Có thể compile bằng JDK 21 để tạo bytecode Java 17.
5. `jar.manifest.attributes` ghi Main-Class thật vào archive, độc lập với câu lệnh `run`.
6. Không cần `repositories` vì mã baseline chỉ dùng Java standard library; không có dependencies cần resolve qua Maven Central.

### 6.4. File src/main/resources/messages.properties

```properties
greeting=Hello
```

Java sẽ tìm resource theo tên `messages.properties` ở classpath root. Sau `processResources`, resource thường ở `build/resources/main/messages.properties`; bên trong JAR được đóng tại `messages.properties`.

### 6.5. File src/main/java/example/JarHello.java

```java
package example;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class JarHello {
    private JarHello() {
    }

    public static void main(String[] args) throws IOException {
        String who = args.length == 0 ? "Gradle" : args[0];

        Properties messages = new Properties();
        try (InputStream in = JarHello.class.getClassLoader()
                .getResourceAsStream("messages.properties")) {
            if (in == null) {
                throw new IllegalStateException(
                        "Missing classpath resource: messages.properties");
            }
            messages.load(new InputStreamReader(
                    in, StandardCharsets.UTF_8));
        }

        System.out.println(
                messages.getProperty("greeting") + ", " + who + "!");
    }
}
```

**Cơ chế chính:**

- `args.length == 0` chọn `Gradle`, còn khi có argument thì `args[0]` được sử dụng.
- `getResourceAsStream("messages.properties")` đọc từ **classpath/JAR**, không phải đường dẫn source trong project.
- `Properties.load(Reader)` nhận text UTF-8; key `greeting` có giá trị `Hello`.
- Null check tạo lỗi rõ nếu quên đóng gói resource.
- `println` in đúng một dòng với newline. Không có random/time/locale phụ thuộc môi trường.

### 6.6. Build và chạy Linux/macOS

```bash
./gradlew clean jar --console=plain
java -jar build/libs/manifest-lab-1.0.0.jar
java -jar build/libs/manifest-lab-1.0.0.jar Team
```

Lệnh đầu tạo JAR; hai lệnh tiếp theo là **hai lần chạy chương trình khác nhau**. Stdout của lần không có argument:

```text
Hello, Gradle!
```

Stdout của lần có `Team`:

```text
Hello, Team!
```

Gradle có thể in thông tin daemon, task outcomes hoặc `BUILD SUCCESSFUL`; đó không phải stdout từ phương thức `JarHello.main`. Nếu Java version dùng để chạy chưa hỗ trợ bytecode Java 17, nó sẽ fail trước khi in kết quả.

### 6.7. Chạy Windows PowerShell

```powershell
.\gradlew.bat clean jar --console=plain
java -jar .\build\libs\manifest-lab-1.0.0.jar
java -jar .\build\libs\manifest-lab-1.0.0.jar Team
```

PowerShell path dùng `\` theo thông lệ Windows, nhưng Java manifest vẫn lưu class name `example.JarHello` với dấu chấm, không dùng `\`.

### 6.8. So sánh Gradle run

```bash
./gradlew -q run
./gradlew -q run --args="Team"
```

Kết quả Java tương ứng:

```text
Hello, Gradle!
Hello, Team!
```

Hai dòng là kết quả của **hai command riêng**. `run` dùng `application.mainClass` và classpath của main source set, không mở JAR để đọc manifest. Vì vậy một build **có thể chạy `run` thành công trong khi `java -jar` thất bại** nếu manifest không có Main-Class.

## 7. Kiểm tra nội dung JAR bằng công cụ JDK

### 7.1. Liệt kê archive entries

```bash
jar tf build/libs/manifest-lab-1.0.0.jar
```

Trong kết quả sẽ có các entries quan trọng:

```text
META-INF/
META-INF/MANIFEST.MF
example/JarHello.class
messages.properties
```

Thứ tự/directory entries có thể khác tùy Gradle. Cú pháp hiện đại tương đương:

```bash
jar --list --file build/libs/manifest-lab-1.0.0.jar
```

`jar tf` chứng minh file nằm trong ZIP, không tự chứng minh Java launcher sẽ chạy được hoặc external dependencies có đủ.

### 7.2. Giải nén đúng manifest trên Linux/macOS

```bash
mkdir -p jar-inspect
cd jar-inspect
jar xf ../build/libs/manifest-lab-1.0.0.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
cd ..
```

Cần tìm:

```text
Manifest-Version: 1.0
Main-Class: example.JarHello
Implementation-Title: manifest-lab
Implementation-Version: 1.0.0
```

Đây chỉ là những headers cần kiểm tra, có thể không đúng thứ tự hoặc có thêm metadata `Created-By`. `jar xf` giải nén ra `jar-inspect`, không thay archive gốc. Không chỉnh file manifest đã giải nén rồi kỳ vọng file JAR nguồn thay đổi.

### 7.3. Giải nén manifest trên Windows PowerShell

```powershell
New-Item -ItemType Directory -Force -Path jar-inspect | Out-Null
Push-Location jar-inspect
jar xf ..\build\libs\manifest-lab-1.0.0.jar META-INF/MANIFEST.MF
Get-Content META-INF/MANIFEST.MF
Pop-Location
```

`Push-Location` và `Pop-Location` giúp quay về root để chạy Gradle tiếp theo. Không cần cài unzip ngoài JDK khi đã có `jar` tool.

### 7.4. Kiểm tra resources

Nếu code đọc `messages.properties`, archive phải chứa entry `messages.properties`. Đừng đặt file chỉ ở `src/test/resources` rồi mong JAR main chứa nó. Nếu đổi file thành `config/messages.properties` trong resources, Java phải đọc `config/messages.properties`, không phải original source tree path.

**Tránh dùng:**

```java
new java.io.File("src/main/resources/messages.properties");
```

Đây là cách tra đường dẫn source theo current working directory. Khi chạy một JAR trên máy khác, thường không có `src/main/resources`. **Dùng ClassLoader resource API** trong code production.

## 8. Phân biệt java -jar, java -cp và JVM/app arguments

### 8.1. java -jar dựa vào Main-Class

```bash
java -jar build/libs/manifest-lab-1.0.0.jar Alice
```

Java launcher đọc `Main-Class` từ `META-INF/MANIFEST.MF`, load class, gọi main, truyền `Alice` thành `args[0]`. Stdout:

```text
Hello, Alice!
```

Khi dùng `-jar`, các user class path settings như `-cp` hoặc biến `CLASSPATH` không được áp dụng theo cơ chế classpath thông thường; **các entries hợp lệ của manifest Class-Path vẫn được JVM xử lý**.

### 8.2. java -cp chỉ định class trực tiếp

```bash
java -cp build/libs/manifest-lab-1.0.0.jar example.JarHello Alice
```

Stdout vẫn là:

```text
Hello, Alice!
```

`-cp` chỉ nơi tìm classes/resources; `example.JarHello` chỉ tên main class và `Alice` là application argument. Lệnh này **không cần Main-Class trong manifest**. Vì vậy khi `-cp` thành công còn `-jar` báo thiếu main manifest, nguyên nhân nằm ở **entry point metadata**, không phải source thiếu class.

### 8.3. Classpath separator khác trên Unix và Windows

Sau `./gradlew classes`, có thể chạy từ class + resource directories:

Linux/macOS:

```bash
java -cp "build/classes/java/main:build/resources/main" example.JarHello
```

Windows PowerShell:

```powershell
java -cp "build\classes\java\main;build\resources\main" example.JarHello
```

Cả hai in:

```text
Hello, Gradle!
```

Dấu **hai chấm** là classpath separator trên Unix, **dấu chấm phẩy** trên Windows. Cần có cả `build/classes/java/main` và `build/resources/main`, nếu thiếu resources sẽ gặp lỗi `Missing classpath resource`.

### 8.4. Phân biệt JVM option và argument

```bash
java -Duser.language=vi -jar build/libs/manifest-lab-1.0.0.jar Team
```

`-Duser.language=vi` xuất hiện **trước** `-jar` nên là JVM system property. Ngược lại:

```bash
java -jar build/libs/manifest-lab-1.0.0.jar -Duser.language=vi
```

Trong lệnh thứ hai, `-Duser.language=vi` là **args[0]** của chương trình (và với lab được in như một tên), không thiết lập system property. Đây là một nguyên nhân cấu hình JAR chạy từ terminal khác với Gradle `run`.

### 8.5. JAR có Main-Class chưa chắc là file tự thực thi bằng ./app.jar

Manifest không tự cấp Unix executable permission, shebang hay native launcher. Câu lệnh an toàn, portable là `java -jar app.jar`. Một số packaging tools tạo wrapper/native launcher riêng; đừng mặc định mọi JAR đều chạy được trực tiếp bằng `./app.jar`.

## 9. Vấn đề lớn nhất: có external dependency nhưng plain JAR thiếu thư viện

Đây là **thí nghiệm mở rộng trên bản sao lab**, không áp dụng vào baseline nếu chỉ muốn kiểm tra Main-Class.

### 9.1. Thêm một dependency thật

Bổ sung vào cuối `build.gradle`:

```groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

`implementation` đưa Commons Lang vào compile/runtime dependency graph của Gradle. Nó **không** tự nhúng dependency JAR vào plain application JAR.

### 9.2. Chỉnh code để thật sự dùng dependency

Trong `src/main/java/example/JarHello.java`, thêm sau dòng `package`:

```java
import org.apache.commons.lang3.StringUtils;
```

Sau đó **thay** lệnh in ở cuối main:

```java
System.out.println(
        messages.getProperty("greeting") + ", " + who + "!");
```

thành:

```java
String greeting = StringUtils.capitalize(
        messages.getProperty("greeting"));
System.out.println(greeting + ", " + who + "!");
```

Đây là **hai chỉnh sửa trên cùng file Java**; không phải một class mới. `StringUtils.capitalize("Hello")` vẫn là `Hello`, nên output không đổi khi có đúng dependency.

### 9.3. Lỗi có thể tái hiện

```bash
./gradlew clean jar --console=plain
./gradlew -q run
java -jar build/libs/manifest-lab-1.0.0.jar
```

Với Maven Central truy cập được, `run` thành công và in:

```text
Hello, Gradle!
```

Nhưng `java -jar` với **plain JAR** dự kiến thất bại:

```text
Exception in thread "main" java.lang.NoClassDefFoundError: org/apache/commons/lang3/StringUtils
```

Stack trace thực có thể có thêm `Caused by` và line numbers. Sự cố **không phải thiếu Main-Class**: JVM đã load main của app, nhưng khi chạy tới `StringUtils` thì không tìm thấy class của Commons Lang trên runtime classpath.

Vì `jar` chỉ đóng main output, `jar tf build/libs/manifest-lab-1.0.0.jar` không chứa `org/apache/commons/lang3/StringUtils.class`. Điều này đúng theo cách thiết kế plain JAR.

**Câu hỏi chẩn đoán:** `./gradlew run` chạy được nhưng `java -jar` không chạy? Hãy kiểm tra **runtime dependency packaging**, không chỉ xem lại Main-Class.

## 10. Ba cách giải quyết dependency runtime

### 10.1. Cách A — Application distribution (nên ưu tiên khi có nhiều JAR phụ thuộc)

Plugin `application` của baseline đã cung cấp:

```bash
./gradlew installDist --console=plain
```

Output thường có:

```text
build/install/manifest-lab/
├── bin/
│   ├── manifest-lab
│   └── manifest-lab.bat
└── lib/
    ├── manifest-lab-1.0.0.jar
    └── commons-lang3-3.17.0.jar
```

Chạy script trên Linux/macOS:

```bash
./build/install/manifest-lab/bin/manifest-lab
```

Windows PowerShell:

```powershell
.\build\install\manifest-lab\bin\manifest-lab.bat
```

Kết quả Java là `Hello, Gradle!`. Generated startup scripts tính classpath dựa trên app JAR và runtime dependencies, không yêu cầu `Class-Path` do bạn tự liệt kê từng version. Nếu thêm transitive libraries sau này, distribution plugin sẽ đưa các runtime artifacts vào `lib/`.

Các task liên quan:

- `installDist`: thư mục cài đặt trực tiếp.
- `distZip`/`distTar`: ZIP/TAR chứa distribution.
- `startScripts`: launcher Unix/Windows.
- `run`: chạy tại project build, không cần đóng JAR rồi giải nén distribution.

**Không chạy `java -jar` trực tiếp trên app JAR bên trong `lib/` và mặc định rằng JVM tự tìm các JAR còn lại**. Distribution scripts mới là thành phần chủ động thiết lập classpath.

### 10.2. Cách B — java -cp với wildcard trên thư mục lib

Sau `installDist`, directory `lib/` chứa app JAR và runtime dependency JARs.

Linux/macOS:

```bash
java -cp 'build/install/manifest-lab/lib/*' example.JarHello
```

Windows PowerShell:

```powershell
java -cp "build\install\manifest-lab\lib\*" example.JarHello
```

Output:

```text
Hello, Gradle!
```

Dấu `*` ở đây được **Java launcher hỗ trợ trong `-cp`**, mở rộng thành các JAR trực tiếp trong directory. Hãy quote path để shell không tự mở rộng wildcard. Không nhầm với `Class-Path: lib/*` trong manifest: **manifest Class-Path không có cùng quy tắc wildcard**.

### 10.3. Cách C — manifest Class-Path + copy runtime libs

JAR File Specification cho phép header:

```text
Class-Path: lib/commons-lang3-3.17.0.jar
```

Nó trỏ tới file **bên ngoài JAR**, tính từ directory chứa JAR. Muốn `java -jar` chạy được, phải có:

```text
build/libs/
├── manifest-lab-1.0.0.jar
└── lib/
    └── commons-lang3-3.17.0.jar
```

Bổ sung vào cuối `build.gradle` của **dependency lab**:

```groovy
tasks.register('copyRuntimeLibs', Copy) {
    from(configurations.runtimeClasspath)
    into(layout.buildDirectory.dir('libs/lib'))
}

tasks.named('jar', Jar) {
    manifest {
        attributes('Class-Path': 'lib/commons-lang3-3.17.0.jar')
    }
}
```

Cấu hình Jar trước đó vẫn đặt `Main-Class`; đoạn bổ sung chỉ thêm `Class-Path`.

Chạy **cả hai tasks**:

```bash
./gradlew clean jar copyRuntimeLibs --console=plain
java -jar build/libs/manifest-lab-1.0.0.jar
```

Khi directory/files đúng, program in:

```text
Hello, Gradle!
```

**Lưu ý:** script này chỉ liệt kê **một** JAR cố định và do đó chỉ là bài học về nguyên lý. Khi dependency có transitive JARs, bạn cần cập nhật manifest Class-Path để chứa **từng runtime JAR thực sự cần**. `copyRuntimeLibs` tự copy graph nhưng **không tự cập nhật header**. Nếu chỉ chạy `./gradlew jar` trên một môi trường clean, task `copyRuntimeLibs` cũng **chưa chắc được chạy** vì hai tasks không có quan hệ dependsOn trong snippet; muốn một lệnh phân phối hoàn chỉnh, đăng ký distribution/Sync task phù hợp.

### 10.4. Class-Path trong manifest không giống PATH hay -cp

Một header hợp lệ:

```text
Class-Path: lib/a.jar lib/b.jar
```

- Các entries cách nhau bằng **dấu cách**, theo cú pháp relative URL.
- Không dùng separator hệ điều hành `:`/`;` như `java -cp`.
- `lib/a.jar` tính tương đối với **app JAR**, không phải shell current directory.
- Không viết `C:\somewhere\lib.jar` hoặc URL remote tùy tiện để mong launcher tự lấy library.
- Không trông chờ wildcard `lib/*` trong manifest.
- Manifest Class-Path **không nhúng bytes**: khi chuyển archive sang máy khác phải chuyển kèm libraries đúng layout.

Một file JAR được di chuyển khỏi `lib/` của distribution sẽ không tự tìm thấy dependencies dù manifest có header đúng nếu relative path không còn khớp.

## 11. Fat JAR / uber JAR: khi nào cần?

**Fat (uber) JAR** đưa compiled app classes và các classes/resources từ runtime dependencies vào cùng một archive. Đây là lựa chọn khi deployment cần một file đơn với `java -jar`, nhưng **không phải** sản phẩm mặc định của Java/Application plugin.

Gradle docs giới thiệu plugin **Shadow** (`com.gradleup.shadow`) cho bài toán này. Không nên tự nghĩ rằng câu lệnh:

```groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

sẽ tạo fat JAR; nó chỉ khai báo dependency.

**Vì sao không bung tất cả dependencies bằng zipTree một cách vội vàng?**

- Nhiều libraries có `META-INF/services/...`, cần merge để `ServiceLoader` tìm được nhiều implementations.
- Có `META-INF/MANIFEST.MF` trùng giữa các JAR; phải chọn archive manifest đúng.
- Signature files `META-INF/*.SF`, `*.RSA` có thể không còn hợp lệ sau khi repack.
- Có thể cần package relocation để tránh class conflicts.
- Multi-release entries, native libraries, license/notice, module-info và resource duplicates cần xử lý cẩn thận.
- Một JAR khổng lồ có trade-off về thời gian build, deployment và auditing.

**Đừng nhầm framework executable JAR với plain JAR.** Spring Boot `bootJar` có launcher và cơ chế nested libraries riêng; không nên chép cấu hình `Main-Class` của plain `jar` sang `bootJar` mà không xem tài liệu framework.

| Nhu cầu | Lựa chọn hợp lý |
| --- | --- |
| Chạy/debug code đang phát triển | `./gradlew run` |
| Publish thư viện Java | Plain library JAR + POM/Gradle metadata |
| Chạy ứng dụng gồm nhiều runtime JARs theo thư mục | `installDist` hoặc `distZip` |
| Tự quản lý JAR + lib directory | Manifest `Class-Path` và copy runtime dependencies có quy trình |
| Deploy một archive đơn | Plugin fat JAR đáng tin, cấu hình Main-Class/merge resources đúng |
| Framework như Spring Boot | Plugin packaging riêng của framework |

## 12. Lỗi khi chạy JAR: triệu chứng và hướng kiểm tra

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `no main manifest attribute` | Không có `Main-Class` trong archive đang chạy. | Đọc manifest thật, thêm `jar.manifest.attributes`, rebuild. |
| `Could not find or load main class` | Sai package/class name hoặc thiếu bytecode. | So sánh `Main-Class` và `jar tf` entries. |
| `Main method not found` | Chữ ký main không phù hợp với launcher. | Dùng `public static void main(String[] args)` trên Java 17. |
| `NoClassDefFoundError` | Class external hoặc transitive dependency thiếu ở runtime. | Dùng distribution/scripts, `-cp`, Class-Path manifest đúng hoặc fat JAR. |
| `ClassNotFoundException` | Lớp không có trên runtime search path. | Xem archive entries, runtime graph, launch mode. |
| `UnsupportedClassVersionError` | JVM chạy quá cũ so với class file target. | Kiểm tra `java -version`, compiler, `options.release`. |
| `Missing classpath resource` | Resource thiếu/sai path. | Kiểm tra `processResources` và `jar tf`; dùng ClassLoader path. |
| `./gradlew run` OK nhưng `java -jar` fail | Gradle run dùng runtimeClasspath, JAR không có manifest/classpath thích hợp. | Kiểm tra riêng Main-Class và external libs. |
| `Class-Path: lib/*` không hoạt động | Manifest không expand wildcard như launcher `-cp`. | Liệt kê các relative JAR URLs hoặc dùng scripts. |
| Thấy `Main-Class` đúng nhưng dependency JAR đã dời | Relative paths bị phá vỡ. | Giữ đúng release tree tính từ app JAR. |
| `jar tf` không có | Shell chỉ cài JRE/toolchain sai. | Kiểm tra JDK `JAVA_HOME`, `PATH`, version. |
| `gradlew jar` không có file như hướng dẫn | Đổi archiveFileName, project version, buildDirectory hoặc build fail. | Kiểm tra `archiveFile` task property và `build/libs`. |
| `Invalid or corrupt jarfile` | File không là archive hợp lệ, copy/download hỏng. | `jar tf`, đối chiếu checksum và artifact nguồn. |
| Test pass nhưng artifact deploy fail | Test chạy classes/resource dưới Gradle, packaging sai hoặc thiếu libs. | Smoke test **file JAR/distribution thực** trên JVM mục tiêu. |
| Lỗi service discovery sau làm fat JAR | `META-INF/services` hoặc signatures merge sai. | Dùng plugin packaging chuyên dụng và xác minh runtime. |

### 12.1. Quy trình 7 bước

1. **Xác định đúng file** app đang chạy: build mới, path và version nào? Đừng debug một JAR cũ.
2. Chạy `java -version` trên môi trường chạy, và `./gradlew --version` nếu cần phân biệt JVM Gradle.
3. Dùng `jar tf ...` kiểm tra `META-INF/MANIFEST.MF`, main class và resources.
4. Giải nén manifest, đọc `Main-Class` và `Class-Path`.
5. So sánh `./gradlew run`, `java -cp` và `java -jar`. Mỗi cách load entry point/classpath khác nhau.
6. Nếu thiếu class, xem `./gradlew -q dependencies --configuration runtimeClasspath`, chọn cách phân phối phụ thuộc rõ ràng.
7. Rebuild, chạy artifact thật từ thư mục khác, ghi lại stdout/exit code, không kết thúc ở thông báo build success.

### 12.2. Các lệnh chẩn đoán hữu ích

```bash
java -version
./gradlew --version
./gradlew clean jar --console=plain
jar tf build/libs/manifest-lab-1.0.0.jar
java -jar build/libs/manifest-lab-1.0.0.jar
./gradlew -q dependencies --configuration runtimeClasspath
```

Lệnh `dependencies` cho biết Gradle giải quyết những runtime dependencies nào; nó **không có nghĩa tất cả chúng đã nằm trong JAR**. Chỉ việc kiểm tra archive/distribution mới trả lời điều đó.

## 13. Kiểm thử artifact và metadata phát hành

### 13.1. Smoke test JAR chứ không chỉ test method Java

Một ứng dụng có thể pass unit tests nhưng JAR thiếu Main-Class hoặc thiếu resource. Vì vậy trước khi phát hành, kiểm tra:

1. `jar` tạo archive đúng tên/version.
2. `jar tf` có main class bytecode, `META-INF/MANIFEST.MF` và required resources.
3. Manifest có `Main-Class` đúng package/name.
4. `java -jar` chạy thành công bằng **JVM của môi trường triển khai**.
5. Đầu ra, exit code và arguments được kiểm tra.
6. Nếu có external dependencies, smoke test startup script hoặc bộ `Class-Path` đầy đủ, không chỉ một app JAR tách khỏi libs.
7. Chạy từ current working directory khác để phát hiện code hardcode source path.
8. CI lưu đúng file artifact đã kiểm tra, hash và build metadata; không deploy JAR khác với file đã pass.

### 13.2. Chạy từ thư mục khác để kiểm tra ClassLoader resource

Từ project root trên Unix:

```bash
cd ..
java -jar manifest-lab/build/libs/manifest-lab-1.0.0.jar Team
```

Stdout:

```text
Hello, Team!
```

Vì Java đọc resource từ archive, chương trình **không phụ thuộc** vào việc terminal đang ở root source project. Sau đó dùng `cd manifest-lab` nếu cần tiếp tục làm việc.

### 13.3. Version trong project, tên file và manifest khác nhau

```groovy
group = 'example'
version = '1.0.0'
```

Có thể làm tên JAR thành `manifest-lab-1.0.0.jar` theo convention. Header `Implementation-Version: 1.0.0` chỉ xuất hiện vì bạn cấu hình trong Jar manifest. Header `Manifest-Version: 1.0` là phiên bản định dạng manifest, **không đổi thành 1.0.0**.

Muốn phát hành artifact lên Maven repository, cần thêm `maven-publish` hoặc hệ thống publication khác; `./gradlew jar` **chỉ xây file local**. Manifest không thay POM, Gradle Module Metadata hay các dependency constraints của consumer.

### 13.4. Bảo mật và tính tái lập

Manifest metadata không tự xác minh tác giả artifact. Một JAR có `Implementation-Title` rất đẹp vẫn có thể không đáng tin. Khi tải JAR từ nguồn bên ngoài, hãy kiểm tra repository, checksum/chữ ký và dependency verification policy; không chỉ đọc Main-Class.

Khi cần output dễ tái lập, Gradle archive tasks có các tùy chọn:

```groovy
tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

Đây là **tùy chọn bổ sung**, không bắt buộc trong baseline. Nó hỗ trợ thứ tự file và timestamp ổn định; không tự bảo đảm hash giống nhau khi compiler version, generated code, annotation processors hoặc manifest data biến động. Tránh đưa giờ build ngẫu nhiên vào manifest nếu mục tiêu là bit-for-bit reproducibility.

Cần đặc biệt cẩn thận khi repack các signed JARs hoặc merge dependencies: signatures có thể mất hiệu lực, Services metadata cần merge và licenses phải được tuân thủ.

## 14. Tạo JAR thủ công bằng JDK: đối chiếu với Gradle

Nếu muốn kiểm tra riêng Java code trước khi build Gradle, từ root lab baseline sử dụng:

Linux/macOS:

```bash
javac --release 17 -d out src/main/java/example/JarHello.java
java -cp "out:src/main/resources" example.JarHello Team
```

Windows PowerShell:

```powershell
javac --release 17 -d out src\main\java\example\JarHello.java
java -cp "out;src\main\resources" example.JarHello Team
```

Output:

```text
Hello, Team!
```

Các lệnh trên **không tạo JAR**; chúng chỉ compile Java vào `out/` và cho runtime tìm classes/resources từ directories.

Để tạo executable JAR bằng chính JDK jar tool (chỉ với source **baseline**, không phải bản đã thêm Commons Lang):

Linux/macOS:

```bash
jar --create --file hello-manual.jar \
  --main-class example.JarHello \
  -C out . -C src/main/resources .
java -jar hello-manual.jar Team
```

Windows PowerShell dùng một dòng, tránh tiếp dòng kiểu Bash:

```powershell
jar --create --file hello-manual.jar --main-class example.JarHello -C out . -C src/main/resources .
java -jar hello-manual.jar Team
```

Stdout:

```text
Hello, Team!
```

`jar --main-class` tạo đúng manifest entry point trong archive, còn `-C out .` đưa compiled classes ở root archive và `-C src/main/resources .` đưa resources vào. Dù có thể tạo JAR thủ công như vậy, Gradle vẫn giúp quản lý source sets, tasks, dependencies, outputs và build reproducibility tốt hơn trong project thực.

**Đừng chạy lệnh manual sau khi đã đổi source sang `StringUtils`** nếu bạn chưa cung cấp Commons Lang cho `javac`/`java`. Lab manual này chỉ tự chứa khi mã dùng Java standard library như baseline.

## 15. Bài tập thực hành có đáp án định hướng

**Bài 1 — Từ JAR thư viện sang executable JAR.** Bỏ cấu hình Main-Class ở `jar.manifest`, rebuild, thử `java -jar`. Vì sao báo `no main manifest attribute`? Dùng `java -cp build/libs/manifest-lab-1.0.0.jar example.JarHello` để chứng minh class vẫn tồn tại.

**Bài 2 — Sai tên class.** Thay Main-Class thành `JarHello` nhưng giữ package `example`. Quan sát lỗi, kiểm tra `jar tf`, rồi sửa thành `example.JarHello`.

**Bài 3 — Arguments.** Chạy `java -jar ... Alice`. Dự đoán output. Đáp án: `Hello, Alice!`.

**Bài 4 — Resources.** Đổi `greeting=Hello` thành `greeting=Welcome`, rebuild rồi chạy. Stdout dự kiến `Welcome, Gradle!`. Tại sao chương trình đọc được resource dù bạn chạy từ directory khác?

**Bài 5 — Thiếu resource.** Di chuyển `messages.properties` sang `src/test/resources`, rebuild main JAR. Dự đoán lỗi và giải thích main JAR không đóng gói test resources.

**Bài 6 — Manifest metadata.** Đổi `version='2.0.0'`, rebuild. Phân biệt archive filename, Implementation-Version và Manifest-Version.

**Bài 7 — run vs -jar.** Giữ `application.mainClass` nhưng xóa `Main-Class` của Jar task. Vì sao `run` vẫn hoạt động mà `java -jar` có thể fail?

**Bài 8 — Dependency runtime.** Thực hiện mục 9 với Commons Lang. So sánh `./gradlew run` và plain `java -jar`. Class nào bị thiếu ở runtime? Cách dùng `installDist` giúp gì?

**Bài 9 — Class-Path tương đối.** App JAR nằm `release/app.jar`, library ở `release/lib/x.jar`. Manifest cần `Class-Path: lib/x.jar`. Nếu JAR được copy sang directory khác mà không copy `lib/` thì sao?

**Bài 10 — Wildcard.** Vì sao `java -cp 'lib/*'` và manifest `Class-Path: lib/*` không tương đương? Cách nào mở rộng tên JAR tự động?

**Bài 11 — Startup scripts.** Tạo `installDist`, chạy script Unix/Windows. Tại sao đây có thể là lựa chọn tốt hơn tự viết manifest Class-Path cho 20 runtime JARs?

**Bài 12 — CI.** Thiết kế một smoke test sau `jar`: đọc manifest, kiểm tra JAR entries, chạy file thật trên Java 17+, xác minh stdout, exit code và lưu hash artifact.

### Tự kiểm tra nhanh

1. JAR có bắt buộc có `Main-Class` không? **Không**, thư viện JAR thường không cần.
2. Manifest chuẩn ở đâu? **`META-INF/MANIFEST.MF`**.
3. Main-Class của lab là gì? **`example.JarHello`**.
4. Main-Class có đuôi `.class` không? **Không**.
5. `Manifest-Version: 1.0` có nghĩa Java 1.0 không? **Không**.
6. `jar` mặc định đóng gói những gì? **Main compiled classes + resources**.
7. `application.mainClass` để làm gì? **Gradle run/scripts**.
8. `Main-Class` trong manifest để làm gì? **java -jar**.
9. `implementation` có tự làm fat JAR không? **Không**.
10. `java -jar` có dùng external `-cp` như thông thường không? **Không; dùng manifest Class-Path hợp lệ**.
11. Manifest `Class-Path` có nhúng JAR bên ngoài không? **Không**.
12. Cơ sở relative của manifest Class-Path là gì? **Directory chứa app JAR**.
13. `java -cp 'lib/*'` có khác `Class-Path: lib/*` không? **Có**.
14. `installDist` tạo gì? **Distribution chứa app JAR, runtime libs, startup scripts**.
15. `jar tf` dùng để làm gì? **Liệt kê archive entries**.
16. Lỗi thiếu external class có thể là gì? **NoClassDefFoundError**.
17. JVM quá cũ có thể báo gì? **UnsupportedClassVersionError**.
18. Đổi archiveFileName có tự đặt Main-Class không? **Không**.
19. Resource production đặt mặc định ở đâu? **src/main/resources**.
20. Fat JAR có phải luôn tốt hơn distribution không? **Không**.

## 16. Tài liệu tham khảo chính thức

- **Gradle — Building Java & JVM Projects**: đóng gói Jar, thay đổi manifest, layout classes/resources: https://docs.gradle.org/current/userguide/building_java_projects.html
- **Gradle — Java Plugin**: `sourceSets.main.output`, `jar`, dependency configurations: https://docs.gradle.org/current/userguide/java_plugin.html
- **Gradle — Application Plugin**: `run`, `application.mainClass`, `installDist`, `distZip`, startup scripts: https://docs.gradle.org/current/userguide/application_plugin.html
- **Gradle — Jar task DSL**: `manifest`, `archiveFileName`: https://docs.gradle.org/current/dsl/org.gradle.jvm.tasks.Jar.html
- **Gradle — Working With Files**: Copy/Sync, reproducible archives, fat JAR và Shadow plugin: https://docs.gradle.org/current/userguide/working_with_files.html
- **Gradle — Dependency Configurations**: `implementation` và runtimeClasspath: https://docs.gradle.org/current/userguide/declaring_configurations.html
- **Gradle — Shadow plugin**: packaging uber JAR và merge service descriptors: https://gradleup.com/shadow/
- **Oracle/OpenJDK Java 17 — JAR File Specification**: Manifest-Version, Main-Class, Class-Path và relative URLs: https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html
- **Oracle/OpenJDK Java 17 — jar Command**: `--create`, `--list`, `--main-class`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
- **Oracle/OpenJDK Java 17 — java Launcher**: `-jar`, `-cp` và argument order: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html

**Kết luận:** JAR là archive Java, nhưng muốn **`java -jar`** cần manifest có **Main-Class** đúng và class chứa phương thức main hợp lệ. Gradle `application.mainClass` là cấu hình cho `run`/scripts, khác với `jar.manifest`. Khi có external libraries, plain JAR thường không chứa chúng: nên chọn Application distribution, classpath đúng, manifest Class-Path được quản lý hoặc fat JAR chuyên dụng. Việc quan trọng nhất khi debug là kiểm tra **artifact thực tế** bằng `jar tf`, đọc manifest và chạy đúng archive trên JVM mục tiêu.