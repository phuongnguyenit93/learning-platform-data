# Phân biệt JDK chạy build với JDK biên dịch và chạy ứng dụng trong Java 27

Một dự án Java có thể **build thành công** trên máy lập trình nhưng thất bại khi chạy trong container production. Nguyên nhân thường không nằm ở Maven hay Gradle “build sai”, mà ở việc dự án dùng **nhiều Java runtime/JDK khác nhau** trong các giai đoạn khác nhau nhưng không ghi rõ hợp đồng tương thích.

Ví dụ: chạy Gradle bằng **JDK 21**, dùng **JDK 27** để biên dịch chương trình và triển khai chương trình trên **Java 21**. Cấu hình đó **có thể hợp lệ**, nếu compiler được yêu cầu tạo mã tương thích Java 21 bằng `--release 21`, thư viện cũng tương thích và runtime đích đủ các tính năng cần thiết. Ngược lại, nếu compiler tạo bytecode Java 27, một JVM 21 không thể chạy những class đó, dù trình build Gradle đã chạy hoàn toàn bình thường trên 21.

Trong Java 27, cần phân biệt rõ:

1. **JDK/JVM chạy build tool**: Java dùng để chạy chính **Gradle daemon** hoặc **Maven** cùng plugin/build logic.
2. **JDK dùng biên dịch**: JDK cung cấp `javac`, `javadoc` và các công cụ cho task build, thường do **Java toolchains** chọn.
3. **JVM chạy test**: runtime mà Gradle `Test` hoặc Maven Surefire/Failsafe thực sự khởi động để chạy kiểm thử.
4. **JVM chạy ứng dụng**: runtime trong local command, IDE, máy chủ hoặc container production.
5. **Java release đích**: mức cú pháp, bytecode và Java/JDK API mà sản phẩm đã biên dịch **được phép dùng**, điều khiển bằng `javac --release`. Đây là **một hợp đồng tương thích**, không phải đường dẫn tới một JDK.

Bài thuộc chương **Build và quản lý phụ thuộc**, phục vụ module **JAVA_VERSION_JAVA27**. Chỉ dùng kiến thức và API còn áp dụng trong Java 27; những ví dụ không cần `--enable-preview`. Các cấu hình Gradle/Maven được đối chiếu với tài liệu chính thức vào tháng 11/2026.

## 1. Một chương trình có thể liên quan tới nhiều JDK cùng lúc

Hình dung pipeline sau:

```text
Máy developer hoặc CI
┌────────────────────────────────────────────────────────────────┐
│ JAVA_HOME / PATH / IDE                                        │
│       │                                                       │
│       ▼                                                       │
│ Build tool JVM: JDK 21 (Gradle daemon / Maven process)       │
│       │                                                       │
│       ├── chạy build script, plugin, dependency resolution    │
│       │                                                       │
│       └── yêu cầu Java toolchain JDK 27                       │
│                    │                                          │
│                    ├── javac 27 + --release 21                │
│                    │           │                              │
│                    │           └─ .class target Java 21      │
│                    │                                          │
│                    └── test JVM: JDK 21 hoặc 27 (tùy config) │
└────────────────────────────────────────────────────────────────┘
                             │ artifact
                             ▼
Production: Java 21 runtime ──> chạy class file Java 21
```

Đây là một ví dụ hợp lệ **nếu** phiên bản build tool hỗ trợ, compiler JDK 27 có mặt, ứng dụng chỉ dùng API/tính năng tương thích Java 21, các dependency cũng chạy được trên Java 21 và quá trình chạy thực tế được kiểm tra.

**Thông điệp trung tâm:** ba câu hỏi “`java -version` in gì?”, “`javac` nào đã biên dịch?” và “server dùng JVM nào?” có thể cho **ba kết quả khác nhau**. Phải xác minh từng vai trò trước khi kết luận môi trường là Java 27.

### 1.1. Bảng thuật ngữ

| Thành phần | Ai sử dụng? | Xác định bằng gì? | Ảnh hưởng chính |
| --- | --- | --- | --- |
| **Build JVM** | Gradle daemon hoặc tiến trình Maven | JAVA_HOME/PATH, Gradle daemon criteria, `org.gradle.java.home`, cấu hình IDE/CI | Chạy build scripts, Maven/Gradle plugins, bộ máy build |
| **Compiler JDK** | Task `JavaCompile`, Maven Compiler Plugin | Java toolchain/JDK đã chọn, đường dẫn `javac` | Cú pháp được hỗ trợ, khả năng biên dịch, annotation processors |
| **Target release** | `javac` | `--release N`, `options.release`, `maven.compiler.release` | Giới hạn cú pháp, Java/JDK API và class-file version |
| **Test JVM** | Gradle `Test`, Maven Surefire/Failsafe | `javaLauncher`/toolchain hoặc plugin test/JVM config | Kết quả runtime trong lúc test |
| **Application JVM** | Lệnh `java`, IDE run config, service/container | Runtime image hoặc Java installation của môi trường chạy | Class loading, thư viện, GC/JIT, OS/native integration |
| **Dependency JAR** | Compiler và runtime class loader | Dependency graph và bytecode/API của thư viện | Có thể phá tương thích dù source chính dùng `--release` |

**JDK** là bộ công cụ phát triển gồm trình biên dịch và runtime; **JVM** là máy ảo chạy bytecode. Trên production, ứng dụng có thể dùng một **runtime image được đóng gói** phù hợp mà không cần mang toàn bộ công cụ phát triển.

## 2. Ví dụ chọn phiên bản: JDK build 21, compiler 27, runtime 21

Giả sử nhóm phát triển cần **viết mã Java 21**, nhưng muốn CI sử dụng **JDK 27** cho compiler mới và giữ **Java 21** là baseline deployment.

Mục tiêu:

```text
Build tool Java:    21
Compiler JDK:       27
javac --release:    21
Tests trên JVM:     21
Production JVM:     21
```

Một cấu hình như vậy giúp tránh vô tình dùng `java.lang`/`java.util` API chỉ xuất hiện ở Java 25/26/27 trong source chính. Nhưng nó **không** tự kiểm tra tất cả thư viện bên thứ ba và những tính năng phụ thuộc vào runtime. Cần chạy test và smoke test thật trên **JVM 21**.

Ngược lại, nếu ứng dụng thật sự cần API được phát hành chính thức trong Java 27:

```text
Build tool Java:    21 hoặc 27 (nếu build tool hỗ trợ)
Compiler JDK:       27
javac --release:    27
Tests trên JVM:     27
Production JVM:     27 hoặc runtime mới hơn phù hợp
```

Sản phẩm biên dịch cho **27** thì không thể yêu cầu JVM 21 chạy nó. Đừng nhầm “máy build có JDK 27” với “artifact chạy được trên 27” hoặc “artifact cần 27” — các điều đó phải kiểm tra riêng.

## 3. javac --release: hợp đồng cú pháp, Java API và bytecode

Từ JDK 9, `javac --release N` cho phép biên dịch theo phiên bản Java SE được hỗ trợ:

```text
javac --release 21 -d out src/com/example/app/Main.java
```

Khi dùng **javac của JDK 27** với `--release 21`, compiler:

1. Cho phép cú pháp ngôn ngữ tương ứng mức Java **21**.
2. Chặn tham chiếu tới các **Java/JDK API** không có trong release 21 theo dữ liệu API mà compiler cung cấp.
3. Tạo class file phù hợp với JVM Java 21.
4. **Không** tự thay JVM của build tool, JVM chạy test hoặc JVM trên production.

### 3.1. Ví dụ class có thể chạy trên Java 21

Lưu thành `src/com/example/app/Main.java`:

```java
package com.example.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Runtime = "
            + Runtime.version().feature());
    }
}
```

Biên dịch với JDK 27:

```text
javac --release 21 -d out src/com/example/app/Main.java
```

Chạy bằng runtime Java 21:

```text
/path/to/jdk-21/bin/java -cp out com.example.app.Main
```

Đầu ra khi đúng JVM Java 21:

```text
Runtime = 21
```

Chạy bằng JVM 27 sẽ in `Runtime = 27`, **dù file class vẫn target Java 21**. Đó là vì `Runtime.version().feature()` đọc **runtime hiện đang thực thi**, không phải source/target release đã dùng khi biên dịch.

Đường dẫn `/path/to/jdk-21` là ví dụ; thay bằng installation path thực trên máy, và trên Windows dùng `java.exe` theo đường dẫn phù hợp.

### 3.2. Khác gì với --source và --target?

Các tham số dễ bị hiểu nhầm:

| Tùy chọn | Điều khiển | Không bảo đảm |
| --- | --- | --- |
| `--source 21` | Cú pháp ngôn ngữ Java 21 | Không tự giới hạn Java API hay JVM chạy chương trình |
| `--target 21` | Class-file format để hướng tới Java 21 | Không tự ngăn dùng API mới hơn của JDK đang biên dịch |
| `--release 21` | Cú pháp, target class format và API Java/JDK tương ứng Java 21 | Không khóa version của thư viện bên thứ ba hay runtime bên ngoài |
| Chọn compiler JDK 27 | Phiên bản `javac` chạy task | Không tự nói artifact target 21 hay 27 |

**Khuyến nghị:** dùng `--release` để cross-compile cho Java cũ hơn thay vì dựa riêng vào `--source` và `--target`. Trong cùng một lời gọi `javac`, **không kết hợp `--release` với `--source`/`--target`**; chúng không được phép dùng cùng nhau.

Không phải một bản JDK mới hỗ trợ **mọi** phiên bản release từ trước tới nay. Tập các release mà `javac --release` hỗ trợ là **một số release trước đó có giới hạn**, xem help của chính bản JDK đang dùng.

### 3.3. Java 27 có class-file major version 71

Theo JVMS Java SE 27:

| Java release | Class-file major |
| --- | ---: |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |
| Java 26 | 70 |
| **Java 27** | **71** |

Một class file có **major 71** không chạy được trên JVM Java 21 (chỉ hiểu class file đến major 65). Khi đó có thể thấy lỗi:

```text
java.lang.UnsupportedClassVersionError:
... has been compiled by a more recent version of the Java Runtime
(class file version 71.0), this runtime only recognizes
class file versions up to 65.0
```

Đây là **thông báo minh họa**; tên class và cách hiển thị có thể khác.

Có thể xem header class bằng:

```text
javap -verbose -classpath out com.example.app.Main
```

Tìm dòng `major version: 65` nếu chương trình được biên dịch với `--release 21`. Với `--release 27`, major tương ứng là **71**.

### 3.4. --release không kiểm soát toàn bộ hệ sinh thái

Kể cả khi source chính dùng `--release 21`:

- Một dependency có thể chứa class file **major 71**; runtime 21 có thể lỗi khi tải class đó.
- Một thư viện có thể sử dụng API không có ở runtime 21 qua reflection, JNI hoặc service provider.
- Annotation processors, compiler plugins và code generation tools cần tương thích với **compiler JDK** mà chúng được thực thi trên.
- Các tính năng runtime như GC options, crypto provider, charset, TLS và native library có thể khác nhau.
- Một ứng dụng biên dịch thành công vẫn có thể phụ thuộc vào thư viện/giao thức do CI hoặc máy lập trình cung cấp nhưng production thiếu.

**Không được xem `--release` là chứng nhận end-to-end compatibility.** Nó là hàng rào mạnh cho code nguồn được biên dịch với compiler Java, còn kiểm thử runtime thật vẫn là bắt buộc.

## 4. Gradle: JVM chạy Gradle khác Java toolchain của dự án

Trong các phiên bản Gradle hiện hành có ít nhất hai tầng JVM:

```text
gradlew / gradle client JVM
          │
          ▼
Gradle daemon JVM (chạy Gradle engine + build logic)
          │
          ├── compileJava -> JavaCompiler từ toolchain
          ├── test        -> JavaLauncher của task Test
          ├── run         -> JavaLauncher của task JavaExec
          └── javadoc     -> JavadocTool của toolchain
```

**Gradle client** là tiến trình khởi động từ wrapper/shell/IDE. **Gradle daemon** là tiến trình thực thi build, có thể dùng JVM khác client. Khi nói “JDK chạy Gradle”, nên ghi rõ **Gradle daemon JVM** vì phần lớn build logic/plugin thực thi trong daemon.

### 4.1. Phiên bản Gradle tương thích Java 27

Theo Gradle Compatibility Matrix (thời điểm 11/2026):

- **Gradle 9.8.0 trở lên** được xác nhận hỗ trợ **Java 27** khi chạy Gradle daemon và sử dụng Java 27 toolchains.
- Gradle **9.x** cần **JVM từ Java 17 trở lên** để chạy daemon; điều này không buộc compiler hay runtime ứng dụng cũng phải là 17.
- Nếu dự án dùng một Gradle wrapper cũ hơn, **không** giả định nó chạy trên JDK 27. Kiểm tra Compatibility Matrix của **phiên bản Gradle đang thực sự dùng**, không chỉ phiên bản JDK.
- Một số plugin Gradle hoặc tool tĩnh/bytecode analyzer có thể chưa hỗ trợ class file Java 27 dù Gradle core đã hỗ trợ.

**Không nên để mỗi developer tự chạy một Gradle toàn cục khác nhau.** Commit Gradle Wrapper (`gradlew`, `gradlew.bat` và cấu hình wrapper) để cả CI/IDE dùng cùng version build tool.

### 4.2. Mẫu Gradle Kotlin DSL: compiler JDK 27, target Java 21

Ví dụ `build.gradle.kts` cho Java application đơn giản:

```kotlin
plugins {
    application
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        // Chọn JDK 27 cho các Java toolchain-aware tasks.
        languageVersion = JavaLanguageVersion.of(27)
    }
}

tasks.withType<JavaCompile>().configureEach {
    // Mã đầu ra phải tương thích cú pháp và Java API của Java 21.
    options.release = 21
}

application {
    mainClass = "com.example.app.Main"
}
```

Giải thích:

- `java.toolchain.languageVersion = 27` yêu cầu JDK 27 cho compilation, mặc định các task Java plugin hỗ trợ toolchain, như `Test` và `Javadoc`.
- `options.release = 21` truyền mức release cho trình biên dịch; source phải tuân theo API/cú pháp Java 21.
- Không có dòng nào ở đây bắt Gradle daemon chạy JDK 27.
- Plugin `application` định nghĩa task `run`; `mainClass` trỏ tới entry point có `public static void main(String[] args)`.
- Với cấu hình trên, `run`/`test` do Gradle cung cấp **có thể dùng Java 27** theo toolchain mặc định, vì vậy chưa phải bằng chứng app chạy được trên Java 21.

Muốn chọn **Java 27 cho cả artifact và runtime**, chỉ cần đổi thành `options.release = 27` nếu toàn bộ stack và nơi triển khai đều hỗ trợ 27. Khi đó test/prod cũng phải dùng JVM tương thích 27.

### 4.3. Ép task test chạy trên JVM 21

Nếu yêu cầu sản phẩm chạy trên Java 21, kiểm thử trên Java 21 để phát hiện lỗi runtime hoặc dependency:

```kotlin
tasks.named<Test>("test") {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Với đoạn trên, ba lớp độc lập:

```text
Gradle daemon: 21 hoặc 27  (do môi trường/daemon criteria quyết định)
compileJava:   javac 27    (toolchain = 27)
--release:     21          (class file Java 21)
test JVM:      java 21     (javaLauncher riêng cho task test)
```

Nếu dự án có **test source** dùng API riêng của Java 27, nhưng phải chạy test trên Java 21, source test hoặc test dependencies cũng có thể không tương thích. Khi đó cần tách test theo mục tiêu, thay `options.release`/test toolchain tương ứng hoặc dùng một **test matrix** chứ không gán bừa cùng một cấu hình cho mọi task.

### 4.4. Ép task run dùng JVM 21

Nếu muốn task `run` của `application` chạy trên Java 21:

```kotlin
tasks.named<JavaExec>("run") {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Dùng với `--release 21` để chạy smoke test ở runtime thấp nhất dự án hỗ trợ. Đây là **runtime của Gradle task run**, **không** thay thế Java trong Docker image hoặc trên server production.

**Tương tự**, có thể tạo những task `Test` và `JavaExec` khác dùng Java 27 nếu muốn kiểm thử hai runtime theo ma trận.

### 4.5. Khi nào chỉ cần toolchain 27?

Nếu sản phẩm thật sự target Java 27 và CI cùng production đã xác định dùng Java 27:

```kotlin
plugins { java }

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 27
}
```

Đây là cấu hình nhất quán cho Java 27 và chỉ dùng API đã phát hành chính thức. Tuy nhiên, **toolchain 27 không tự khiến Gradle wrapper bản cũ hỗ trợ JVM 27**; cần phiên bản Gradle đủ mới và plugin tương thích.

## 5. Gradle daemon JVM: JAVA_HOME, org.gradle.java.home, Daemon JVM criteria

Trong hệ sinh thái Gradle, những nguồn chọn JVM có phạm vi khác nhau:

| Cơ chế | Điều khiển | Điều không tự điều khiển |
| --- | --- | --- |
| `JAVA_HOME`/`PATH` | JVM mà script/IDE có thể dùng để khởi chạy Gradle client; thường ảnh hưởng daemon khi không có cấu hình ưu tiên cao hơn | Không buộc Java compiler toolchain theo dự án |
| `org.gradle.java.home` | JVM mà Gradle dùng cho daemon theo cấu hình phù hợp | Không thay thế `java.toolchain` |
| **Daemon JVM criteria** | Tiêu chí version/vendor của JVM dành riêng cho Gradle daemon | Không quyết định target release của code |
| `java.toolchain` | JDK mà các Java tasks của Gradle dùng theo khả năng toolchain | Không thay JVM production |
| `tasks.test.javaLauncher` | JVM chạy một task test cụ thể | Không điều khiển Maven/Gradle daemon |
| `tasks.run.javaLauncher` | JVM chạy một task JavaExec | Không thay Docker base image |

Gradle hỗ trợ **Daemon JVM criteria**, được quản lý bằng task `updateDaemonJvm` và lưu trong cấu hình dự án, nhằm tránh để daemon phụ thuộc tình cờ vào mỗi máy.

Ví dụ minh họa thao tác thiết lập **daemon JVM 21** (chạy trên môi trường Gradle hỗ trợ tính năng):

```text
./gradlew updateDaemonJvm --jvm-version=21
```

Khi cấu hình Daemon JVM criteria hiện diện, nó có thể **ưu tiên hơn** `JAVA_HOME` và `org.gradle.java.home` để chọn daemon JVM. Hãy kiểm tra cách Gradle wrapper và IDE thực sự xử lý tiêu chí này.

**Không nhầm** task trên với `java { toolchain { languageVersion = 21 } }`: tiêu chí daemon chỉ chọn môi trường chạy **Gradle**, còn toolchain chọn JDK phục vụ **các task Java**.

### 5.1. Gradle toolchain detection và auto-provisioning

Gradle có thể tìm JDK qua cài đặt trên máy, cấu hình environment và các vị trí đã biết. Khi có **toolchain download repositories/resolver** được cấu hình, Gradle có thể tự tải một JDK đáp ứng yêu cầu toolchain:

```text
./gradlew -q javaToolchains
```

Lệnh hiển thị những toolchain mà Gradle phát hiện. **Không** suy đoán “khai báo toolchain 27 là sẽ tự tải được JDK 27”: auto-provisioning phụ thuộc cấu hình resolver/repository, quyền truy cập mạng, chính sách và môi trường CI.

Nếu thiếu toolchain, build thường báo lỗi không tìm được Java installation phù hợp. Điều này tốt hơn việc vô tình dùng JDK khác mà vẫn build ra artifact sai.

### 5.2. IDE có thể dùng JVM khác terminal

IDE thường có ít nhất hai cài đặt:

- **Project SDK/Java language level** của code và editor.
- **Gradle JVM** mà IDE dùng cho Gradle client/daemon.
- **Run/test configuration JRE** dành cho ứng dụng/tests do IDE tự chạy.

Nếu `./gradlew test` trong terminal thành công nhưng “Run tests” trong IDE thất bại, hãy xác nhận IDE đang chạy test **qua Gradle** hay runner riêng của IDE. Nếu IDE bỏ qua task test launcher của Gradle và dùng runtime mặc định khác, kết quả sẽ khác mặc dù cùng source.

## 6. Maven: JDK chạy Maven không bắt buộc là compiler JDK

Với Maven, bắt đầu từ:

```text
mvn -version
```

Dòng `Java version`/`Java home` trong output cho biết JDK đang chạy **Maven process**. Nhưng khi dự án đã cấu hình **Maven Toolchains**, Maven Compiler Plugin có thể dùng **JDK khác** để biên dịch.

```text
Maven process JVM: JDK 21
   │
   ├── Maven core/plugin logic chạy trong Maven process
   ├── Maven Toolchains chọn JDK 27
   │       ├── Compiler Plugin -> javac 27 --release 21
   │       ├── Javadoc Plugin -> JDK toolchain (nếu hỗ trợ)
   │       └── Surefire -> test JVM theo toolchain hoặc override
   └── package artifact Java 21
            │
            └── production java 21
```

Khác với Gradle, Maven **không có một Gradle daemon** tương đương trong mô hình Maven CLI thông thường. Khi nói “JDK chạy Maven”, ý là JVM của **lệnh Maven** mà người dùng/CI đã khởi động, không phải JDK toolchain.

### 6.1. Maven 3: compiler JDK 27, --release 21

Ví dụ một `pom.xml` nhỏ có thể dùng làm điểm xuất phát:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>jdk-toolchain-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <!-- Java API/language/bytecode target -->
        <maven.compiler.release>21</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <!-- Maven process vẫn có thể chạy bằng JDK 21. -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-toolchains-plugin</artifactId>
                <version>3.3.0</version>
                <executions>
                    <execution>
                        <goals>
                            <goal>select-jdk-toolchain</goal>
                        </goals>
                    </execution>
                </executions>
                <configuration>
                    <!-- Chọn đúng major 27 từ các JDK phát hiện được. -->
                    <version>[27,28)</version>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Mẫu trên minh họa **Maven 3**, dùng Maven Toolchains Plugin **3.3.0** với goal `select-jdk-toolchain` để tìm một JDK 27, Compiler Plugin **3.16.0** và Surefire **3.6.1** — là những phiên bản plugin đã phát hành ở thời điểm đối chiếu. Dự án thật còn cần cấu hình dependency, test framework và chính sách build riêng.

Lưu ý:

- `<maven.compiler.release>21</maven.compiler.release>` quyết định **Java target**, không yêu cầu `mvn` chạy JDK 21.
- `<version>[27,28)</version>` chọn JDK **27.x** trong khoảng phiên bản theo Maven toolchain selection.
- `select-jdk-toolchain` sử dụng JDK discovery; trong môi trường quản lý thủ công có thể dùng `~/.m2/toolchains.xml` và goal `toolchain` theo hướng dẫn Maven.
- Plugin **có hỗ trợ toolchain** mới có thể dùng JDK được chọn. Các Maven plugins khác vẫn có thể chạy trong Maven process và chịu yêu cầu Java runtime của chính plugin đó.
- Surefire mặc định có thể dùng toolchain do Maven chọn để khởi động forked test JVM; nếu cần chạy tests trên **JDK 21**, phải chỉ định riêng runtime cho Surefire.
- Nếu CI không có JDK 27 tương thích, Maven phải báo không thỏa yêu cầu thay vì âm thầm dùng một compiler tùy ý.

### 6.2. Chạy Maven test trên JVM 21

Thêm cấu hình vào `maven-surefire-plugin`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.6.1</version>
    <configuration>
        <jdkToolchain>
            <version>[21,22)</version>
        </jdkToolchain>
    </configuration>
</plugin>
```

Đây là **đoạn thay thế** cho plugin Surefire trong ví dụ trên, không phải một plugin thứ hai có cùng artifact ID. Build/CI phải có JDK 21 mà Surefire có thể tìm qua Maven Toolchains.

Nếu mục tiêu là sản phẩm Java 27, để test JDK 27 theo toolchain chung hoặc chỉ rõ JDK 27. Không thể bắt JVM 21 chạy test class đã biên dịch thành bytecode 27.

**Lưu ý:** Surefire chọn JVM dùng chạy kiểm thử; source code của tests vẫn cần được **biên dịch** trước đó bằng `maven-compiler-plugin`, và các JUnit/JVM libraries phải tương thích với test JVM.

### 6.3. Maven Compiler Plugin có thể chọn JDK riêng

Khi không cần một toolchain dùng chung toàn bộ lifecycle, Compiler Plugin có thể chọn JDK cho riêng nó:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.16.0</version>
    <configuration>
        <release>21</release>
        <jdkToolchain>
            <version>27</version>
        </jdkToolchain>
    </configuration>
</plugin>
```

Đoạn này giả định Maven có **toolchain metadata phù hợp** (chẳng hạn `toolchains.xml` khai báo đúng `version`) và được cấu hình theo tài liệu plugin. Nếu đã có toolchain chung, cấu hình `jdkToolchain` ở compiler plugin có thể **ghi đè toolchain chung chỉ cho compiler**. Điều đó hữu ích cho project đa module/test nhưng dễ tạo lỗi nếu không ghi rõ mục tiêu từng phase.

Không sử dụng `<executable>/absolute/path/to/javac</executable>` hard-coded như lựa chọn mặc định cho dự án nhóm; nó làm build kém di động giữa Windows/Linux/CI.

### 6.4. Maven Wrapper khác Maven Toolchains

`mvnw`/`mvnw.cmd` thường giúp dự án dùng **một phiên bản Maven được chốt**; nó **không** tự bảo đảm các JDK phù hợp đều được cài đặt.

Phân biệt:

- **Maven Wrapper**: chốt build-tool distribution/version.
- **Maven Toolchains**: chọn JDK cung cấp các công cụ phục vụ plugin.
- **`maven.compiler.release`**: chốt mức tương thích của class/API Java.
- **Surefire/Failsafe runtime**: chốt JVM chạy kiểm thử.
- **Production image**: quyết định JVM chạy artifact khi deploy.

## 7. Phân biệt compile, test và production qua một ví dụ nhỏ

Ví dụ `Main.java`:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Running on Java "
                + Runtime.version().feature());
    }
}
```

Có thể dùng source này cho cả Gradle hoặc Maven:

```text
Gradle layout: src/main/java/com/example/app/Main.java
Maven layout:  src/main/java/com/example/app/Main.java
```

Để kiểm tra JVM chạy chương trình, dùng lệnh Java của runtime đích, ví dụ:

```text
/path/to/jdk-21/bin/java -cp build/classes/java/main com.example.app.Main
```

Lệnh trên minh họa **layout của Gradle Java plugin** sau khi compile; với Maven layout thường là:

```text
/path/to/jdk-21/bin/java -cp target/classes com.example.app.Main
```

Nếu target là Java 21 và runtime 21, chương trình in `Running on Java 21`. Nếu chọn Java 27, nó in `Running on Java 27`. Một lệnh chạy chương trình trong IDE có thể dùng JVM khác nếu run configuration trỏ đến installation khác.

### 7.1. Bảng kết quả kỳ vọng

| Build JVM | Compiler JDK | `--release` | Test/Prod JVM | Kỳ vọng |
| --- | --- | --- | --- | --- |
| 21 | 27 | 21 | 21 | **Hợp lệ** nếu mọi dependency và runtime behavior tương thích |
| 21 | 27 | 27 | 27 | **Hợp lệ** nếu build tool, plugins và runtime hỗ trợ |
| 27 | 27 | 21 | 21 | **Hợp lệ**; build JVM không quyết định class version |
| 27 | 27 | 27 | 21 | **Không**: Java 21 không hiểu class-file major 71 |
| 21 | 21 | 27 | 27 | **Không**: javac 21 không biết Java release 27 |
| 17 | 27 | 21 | 21 | **Có thể hợp lệ** với build tool/plugins hỗ trợ và toolchain |
| 27 | 27 | 27 | 27 | **Hợp lệ** nếu plugin/CI hỗ trợ Java 27; không mặc nhiên được hỗ trợ bởi mọi Gradle version |

“**Hợp lệ**” ở bảng này chỉ xét khả năng tương thích chính về **phiên bản Java**. Nó không thay cho việc kiểm thử API bên thứ ba, module system, native libraries, quyền OS, version dependencies hoặc cấu hình ứng dụng.

### 7.2. Vì sao không dùng runtime nhỏ hơn class target?

JVM kiểm tra **class-file format** khi tải class. Một class được biên dịch cho release mới có thể chứa instruction/metadata mà JVM cũ chưa được thiết kế để hiểu; JVM cũ từ chối nó bằng `UnsupportedClassVersionError`.

Đổi `JAVA_HOME` trên máy build sau khi đã tạo artifact **không viết lại bytecode**. Để chạy ở Java thấp hơn, phải biên dịch lại với release tương thích và kiểm tra dependencies. Một số API mới không có phương án thay thế trên Java cũ.

## 8. Build tools và plugin cũng có yêu cầu Java của riêng chúng

Một dự án Java 27 có thể chứa:

```text
Gradle/Maven core
   ├── Java compiler plugin/tool
   ├── test runner (JUnit/Surefire)
   ├── code coverage agent
   ├── static analyzer/linter
   ├── annotation processor
   ├── dependency resolution plugin
   ├── packaging/image plugin
   └── publish/deploy plugin
```

Các thành phần này có **runtime và compatibility matrix riêng**:

- Plugin Gradle được tải/chạy trong môi trường của Gradle daemon hoặc worker process do plugin tạo; plugin có thể đòi Java tối thiểu cao hơn daemon JVM.
- Maven plugin thường chạy trong Maven process, trừ khi plugin chủ động fork tool/process.
- Annotation processor thường được trình biên dịch thực thi ở compile phase; bộ xử lý và compiler JDK phải tương thích.
- Code coverage/bytecode weaving có thể không đọc được class-file major 71 nếu phiên bản công cụ quá cũ.
- Kotlin/Scala/Groovy hoặc một plugin đa ngôn ngữ có logic riêng; **Java toolchain** không bảo đảm mọi compiler không phải Java đều tự cấu hình đúng.
- Một plugin có thể thất bại ngay ở **build script configuration phase** trước khi Gradle kịp chạy `compileJava`.

**Chẩn đoán chính xác:** tìm phase lỗi và process thực thi phase đó. Đừng sửa `options.release` khi lỗi là plugin không chạy được trên daemon JVM, và đừng nâng Gradle daemon JVM chỉ để giải quyết một class-file mismatch ở production.

## 9. Phụ thuộc thư viện: Java release không khóa toàn bộ dependency graph

Tình huống thường gặp:

- Ứng dụng đặt `--release 21` để hỗ trợ server Java 21.
- Một dependency được build cho Java 27.
- App build/test trên Java 27 nên không phát hiện.
- Khi deploy trên Java 21, class loader chạm tới class trong dependency có major 71 và ném `UnsupportedClassVersionError`.

Vì vậy, ngoài `--release` cho source chính:

1. Kiểm tra **minimum supported Java** của từng thư viện runtime.
2. Chạy test (và smoke test) với **JVM thấp nhất** mà sản phẩm công bố hỗ trợ.
3. Dùng dependency constraints/lockfile/version catalog/`dependencyManagement` để chốt phiên bản cần thiết.
4. Với thư viện phát hành **multi-release JAR**, kiểm tra bytecode và hành vi theo runtime thực, không chỉ một class đơn lẻ.
5. Kiểm tra annotation processors, test frameworks, agents và build plugins theo JVM mà **chúng** chạy.
6. Kiểm tra OS/architecture/JNI khi chuyển từ máy developer sang container/production.

### 9.1. Build reproducible không chỉ là JDK major

Để hai môi trường cho artifact và behavior tương đương, thường cần ghi nhận:

```text
Build tool distribution/version
Build tool runner JDK (major + vendor + patch nếu cần)
Compiler JDK/toolchain (major + vendor + patch policy)
Target release (--release)
Runtime/test JVM (major + vendor + patch)
Plugin versions
Dependency versions / lockfiles / verified artifacts
OS/architecture (nếu có native)
Build environment variables/cấu hình liên quan
```

`Gradle Wrapper` và `Maven Wrapper` giúp chốt **build tool**, còn toolchains giúp chốt **JDK requirements**. Kết hợp dependency locking/verification và CI kiểm thử mới giúp nâng mức tái lập. Không dùng dependency phiên bản động một cách tùy tiện trong build cần điều tra chính xác sự cố.

## 10. Kiểm tra môi trường thật bằng những lệnh nào?

### 10.1. Đọc JVM của terminal

```text
java -version
javac -version
```

- `java -version` cho biết lệnh `java` hiện được shell chọn qua `JAVA_HOME`/`PATH`.
- `javac -version` cho biết trình biên dịch **mặc định trong shell**.
- Cả hai **không chứng minh** Gradle/Maven toolchain hoặc JVM của app ở production dùng phiên bản đó.

Trên Linux/macOS có thể kiểm tra:

```text
which java
which javac
echo "$JAVA_HOME"
```

Trên Windows PowerShell:

```powershell
Get-Command java
Get-Command javac
$env:JAVA_HOME
```

Kiểm tra đường dẫn executable và JDK cài đặt, tránh phụ thuộc vào một chuỗi version không có path.

### 10.2. Gradle: wrapper, daemon và toolchains

```text
./gradlew --version
./gradlew -q javaToolchains
./gradlew compileJava --info
./gradlew test --info
```

Trên Windows dùng `gradlew.bat`/`.\gradlew.bat` theo shell đang chạy. Các lệnh này là **hướng dẫn cho người học**, không phải thao tác đã thực hiện trên project của module này.

- `--version` hiển thị version Gradle và thông tin Launcher/Daemon JVM khi Gradle có hỗ trợ.
- `javaToolchains` liệt kê các JDK mà Gradle đã phát hiện.
- `--info` giúp quan sát việc chọn compiler và Java launcher cho task; nội dung log phụ thuộc Gradle/plugin.
- Nếu dùng Daemon JVM criteria, xem version/vendor được yêu cầu và daemon phù hợp.

### 10.3. Maven: process và toolchain

```text
./mvnw -version
./mvnw -X compile
./mvnw -X test
```

Với Maven cài toàn cục, thay `./mvnw` bằng `mvn`. Khi cần kiểm tra JDKs được phát hiện qua Toolchains Plugin, dùng goal được tài liệu hỗ trợ:

```text
./mvnw toolchains:display-discovered-jdk-toolchains
```

Maven debug log có thể chứa local paths/environment và thông tin cấu hình; **không** chia sẻ nguyên vẹn nếu có secret trong log.

### 10.4. Chứng minh runtime trong chính ứng dụng

```java
public final class RuntimeInfo {
    public static void main(String[] args) {
        System.out.println("Java feature = "
                + Runtime.version().feature());
        System.out.println("Java home = "
                + System.getProperty("java.home"));
        System.out.println("Java vendor = "
                + System.getProperty("java.vendor"));
    }
}
```

Giá trị này mô tả **JVM của process đang chạy class**, giúp phân biệt test/production runtime. Không dùng `System.getProperty("java.home")` từ Gradle build logic rồi tưởng đó là Java home của test task đã fork.

## 11. CI/CD: chốt runner, compiler, test và production riêng

Một CI pipeline có thể cài hai JDK:

```text
CI worker
 ├─ JDK 21: Gradle daemon / Maven process
 ├─ JDK 27: Java compiler toolchain
 ├─ JDK 21: integration/smoke tests
 └─ Artifact được build bằng --release 21

Deployment
 └─ Java 21 runtime image: chạy artifact
```

### 11.1. Ma trận test theo runtime

Nếu thư viện công bố hỗ trợ Java 21 và 27:

| Job | Compiler | Target release | Test JVM | Mục tiêu |
| --- | --- | --- | --- | --- |
| Main compatibility | JDK 27 | 21 | 21 | Bảo đảm baseline |
| Forward compatibility | JDK 27 | 21 | 27 | Phát hiện sai khác runtime mới |
| Java 27-only feature branch | JDK 27 | 27 | 27 | Kiểm tra những API/tính năng chính thức ở 27 |

Không bắt buộc mọi dự án phải chạy tất cả tổ hợp; tùy target thực tế. Nhưng nếu sản phẩm **hứa** chạy Java 21, có ít nhất một test/smoke job chạy trên **Java 21** sẽ phát hiện lỗi mà test chỉ chạy Java 27 không thấy.

### 11.2. Container runtime khác container build

Một Docker multi-stage build thường có **hai base image** khác nhau:

```text
Build stage (có compiler JDK + Gradle/Maven)
   └── tạo JAR/class phù hợp target

Runtime stage (chỉ runtime phù hợp release đích)
   └── chạy artifact
```

Nếu compile bằng JDK 27 và `--release 21`, runtime stage có thể dùng **Java 21** nếu dependencies và ứng dụng thật sự tương thích. Nếu compile `--release 27`, runtime stage phải dùng **Java 27 hoặc runtime mới hơn tương thích**.

Không chỉ nhìn Dockerfile ở stage **builder** để đoán JVM mà service thực sự chạy. Cần kiểm tra stage cuối, image digest, lệnh `java` và runtime Java ở container deployed.

### 11.3. Production startup là tiêu chuẩn cuối cùng

`mvn package`/`gradlew build` thành công chỉ xác nhận build/test đã hoàn tất theo cấu hình đó; nó **không** chứng minh artifact sẽ khởi chạy trên một container khác.

Một smoke test production-like nên kiểm tra:

- `java -version` bên trong image/runtime.
- Startup class loading và dependency resolution.
- Health check và một request nghiệp vụ đại diện.
- JNI/crypto/TLS, filesystem, timezone/locale nếu liên quan.
- Các VM options, memory limits và runtime flags có được phiên bản JVM đó hỗ trợ hay không.

## 12. Các lỗi thường gặp và cách chẩn đoán

### 12.1. UnsupportedClassVersionError

```text
Class file 71.0 is not supported by runtime with max class file 65.0
```

**Bản chất:** class/dependency được biên dịch cho Java 27 nhưng chạy bằng Java 21.

**Cách xử lý:**

1. Xác định class gây lỗi là source chính hay dependency.
2. Kiểm tra `javap -verbose` và class-file major.
3. Nếu app phải chạy Java 21, biên dịch lại với `--release 21` **và chọn thư viện tương thích**.
4. Nếu app thực sự yêu cầu Java 27, nâng runtime ở môi trường deployment **theo chính sách vận hành**.
5. Đừng chỉ nâng build JVM — điều đó không thay deployment JVM.

### 12.2. error: release version 27 not supported

Nếu compiler đang dùng là JDK 21 nhưng `--release 27`, javac báo không hỗ trợ release 27. Cần cấu hình **compiler JDK 27** thông qua toolchain (và dùng build tool đủ mới), không chỉ thay `sourceCompatibility`.

### 12.3. No matching toolchains found

Gradle hoặc Maven không tìm thấy JDK đáp ứng version/vendor/implementation đã khai báo:

- Xem danh sách JDK đã cài đặt hoặc được phát hiện.
- Kiểm tra version range/vendor constraints.
- Nếu muốn toolchain tự tải, cấu hình resolver/repository phù hợp, quyền mạng và chính sách pinning.
- Trên CI, chuẩn bị JDK đúng release trước phase build.

**Không** âm thầm bỏ cấu hình toolchain để build “qua” bằng JDK tình cờ có sẵn.

### 12.4. Gradle bản cũ không chạy được trên Java 27

Nếu daemon Gradle quá cũ và JVM của daemon được đổi sang 27, có thể gặp lỗi Gradle runtime, Groovy/Kotlin, plugin hay class-file parsing. Kiểm tra **Gradle Compatibility Matrix**, nâng Gradle Wrapper và các plugin phù hợp, hoặc giữ daemon trên JDK tương thích rồi dùng JDK 27 qua toolchain khi phiên bản build tool hỗ trợ.

Đối với Java 27, Gradle 9.8.0 trở lên đã được xác nhận hỗ trợ cho daemon và toolchains. Không dùng thông tin của Gradle 8/9 phiên bản khác như thể mọi version đã được hỗ trợ.

### 12.5. Chạy IDE thành công, CI thất bại

Có thể IDE chọn một compiler và runtime khác Gradle/Maven command line:

- IDE Project SDK = 27.
- Gradle daemon JVM = 21.
- Gradle compiler toolchain = 27, `--release 21`.
- CI chỉ có JDK 21 và không tự provision được JDK 27.

Phương án: chốt build tool wrapper và toolchain requirements trong project, cập nhật CI và kiểm tra run/test JVM ở IDE.

### 12.6. Build thành công nhưng test runner lỗi class mới

Nếu test được **biên dịch cho Java 27** nhưng Surefire/Gradle `Test` được cấu hình chạy Java 21, test class không tải được. Giữ test code và test dependency target tương ứng với test JVM, hoặc thay test JVM theo mục tiêu kiểm thử. Nếu cần kiểm tra compatibility Java21, test code cũng cần chạy trên Java21.

### 12.7. Plugin lỗi khi JVM chạy build được nâng

Một plugin có thể không tương thích với phiên bản **build runtime** hoặc Gradle API, dù source Java vẫn biên dịch bằng toolchain cũ. Kiểm tra bản plugin và phase lỗi, không lấy `--release` làm phương tiện sửa lỗi Gradle/Maven plugin classloading.

## 13. Bảng quyết định cấu hình trong dự án thực

| Câu hỏi | Nếu câu trả lời là… | Việc cần làm |
| --- | --- | --- |
| Production phải hỗ trợ Java 21? | Có | `--release 21`, test/smoke trên JVM 21 |
| Source dùng Java 27 API? | Có | `--release 27` và runtime tối thiểu Java 27 |
| Gradle daemon đang dùng JDK 21? | Có | Có thể giữ nếu Gradle/plugin tương thích; toolchain 27 cho compiler |
| CI có nhiều JDK không? | Không | Cài/provision compiler JDK và test JDK theo chính sách |
| Chạy Maven bằng 21 nhưng compile bằng 27? | Có | Maven Toolchains hoặc compiler plugin `jdkToolchain` |
| Muốn chắc dependencies chạy trên 21? | Có | Test với JVM21, kiểm tra class version và dependency metadata |
| IDE dùng SDK khác shell? | Có | Chốt IDE Gradle/Maven runtime và chạy build qua wrapper |
| Artifact class major 71 nhưng deploy Java 21? | Có | Không tương thích; đổi target hoặc nâng runtime |
| Có build multi-module? | Có | Xác định release/toolchain cho từng module và test matrix |
| Phụ thuộc annotation processor? | Có | Kiểm tra processor với compiler JDK, plugin và runtime |
| Đang dùng Gradle cũ? | Có | Kiểm tra support Java 27 trước khi dùng JDK27 làm daemon/compiler |

## 14. Bài tập thực hành và câu hỏi kiểm tra

### 14.1. Bài tập A — tìm đúng JVM từng vai trò

Trong một project Gradle Java:

1. Chạy `java -version` trong shell để biết runtime mặc định của terminal.
2. Chạy `./gradlew --version` để xem Gradle version và thông tin JVM.
3. Chạy `./gradlew -q javaToolchains` để xem JDK đã phát hiện.
4. Đặt `java.toolchain.languageVersion = 27` và `options.release = 21`.
5. Chạy `compileJava --info`, ghi nhận JDK compiler đã chọn.
6. Dùng `tasks.named<Test>("test")` với Java 21 để kiểm tra runtime thấp nhất (khi project có test framework).
7. Biên dịch/chạy `Main.java`, ghi lại `Runtime.version().feature()` bên trong ứng dụng.

**Câu hỏi:** tại sao bước 1 có thể in 21 nhưng bước 5 dùng javac 27? Vì shell JVM và **compiler toolchain** là hai cơ chế chọn JDK khác nhau.

### 14.2. Bài tập B — nhận biết class-file major

Với cùng source `Main.java`:

```text
javac --release 21 -d out21 src/com/example/app/Main.java
javac --release 27 -d out27 src/com/example/app/Main.java

javap -verbose -classpath out21 com.example.app.Main
javap -verbose -classpath out27 com.example.app.Main
```

Đây là các lệnh cần **javac 27** được chọn đúng trên shell và output directories được tạo theo môi trường. Kết quả kỳ vọng:

- `out21` có major **65**.
- `out27` có major **71**.
- Java 21 chạy được `out21`, nhưng sẽ từ chối `out27`.
- Java 27 chạy được cả hai trong tình huống ví dụ đơn giản.

### 14.3. Bài tập C — sửa lỗi release mismatch

Một CI sử dụng Maven với:

```text
Maven JVM = 21
maven.compiler.release = 27
Compiler Plugin không có toolchain
```

Kết quả thường là compiler đang dùng **JDK 21** không hỗ trợ `--release 27`. Cách đúng: chọn **compiler JDK 27** bằng Maven Toolchains, cấu hình đủ Maven/plugin compatibility và xác nhận test/production runtime là 27 nếu artifact cần 27.

### 14.4. Bài tập D — khác nhau giữa build và runtime

Hai build đều tạo artifact Java21:

- Build A chạy Gradle daemon Java 21, compiler Java 27 với `--release 21`.
- Build B chạy Gradle daemon Java 27, compiler Java 27 với `--release 21`.

Chúng có thể tạo **các class file tương thích Java21** nhưng không mặc nhiên tạo artifact byte-for-byte giống nhau: plugin, compiler patch level, tài nguyên, timestamp trong archive và dependency graph còn ảnh hưởng. Nếu cần reproducibility mạnh, phải kiểm soát thêm những yếu tố này.

## 15. Checklist triển khai Java 27 đúng vai trò

- **Chốt build tool** qua Gradle/Maven Wrapper.
- **Ghi build JVM requirement** cho Gradle daemon/Maven và plugin runtime; xác minh compatibility.
- **Ghi compiler toolchain** riêng, không dựa ngẫu nhiên vào `JAVA_HOME` của từng máy.
- **Ghi target release** bằng `--release`/Gradle `options.release`/Maven `maven.compiler.release`.
- **Chạy test trên JVM deployment thấp nhất được hỗ trợ**, không chỉ trên JVM mới nhất.
- **Chạy application smoke test trong image/runtime thật**.
- **Kiểm tra dependency class versions** và yêu cầu JDK tối thiểu của thư viện.
- **Kiểm tra annotation processors/bytecode agents** phù hợp compiler JDK/class-file version.
- **Giữ Gradle và Maven plugins ở bản được hỗ trợ**, không tự cho rằng plugin cũ hiểu Java27.
- **Phân biệt client JVM và daemon JVM ở Gradle**; daemon criteria có thể ưu tiên cấu hình môi trường.
- **Phân biệt Maven process JVM với toolchain JDK** của Compiler/Surefire.
- **Không trộn `--release` với `--source`/`--target`** cho cùng lần biên dịch.
- **Không dùng preview API/flags** nếu chính sách nội dung/dự án chỉ cho phép Java stable.
- **Không coi Java 27 build thành công là có thể deploy trên Java 21**.
- **Ghi nhận vendor/patch version của JDK** và mô hình cập nhật bảo mật trong CI/production.
- **Kiểm thử lại sau khi nâng Gradle/Maven/JDK** vì behavior của plugin/runtime có thể thay đổi.
- **Không đọc các lệnh in version của terminal làm bằng chứng về tất cả task**; xác minh từng process.
- **Lưu cấu hình và kết quả test** để xử lý được lỗi không tái lập giữa local, IDE và CI.

## Tài liệu tham khảo chính thức

- [`javac` — Java SE 27 Command Reference](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) — `--release`, giới hạn API ngôn ngữ và class output.
- [JVMS Java SE 27 — Chapter 1](https://docs.oracle.com/en/java/javase/27/docs/specs/jvms/jvms-1.html) — bảng class-file major versions (Java 27 = 71).
- [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html) — Java runtime của Gradle và bảng hỗ trợ toolchains/daemon, gồm Java 27.
- [Gradle 9.8 Release Notes](https://docs.gradle.org/9.8.0/release-notes.html) — lần đầu hỗ trợ chính thức JDK 27 cho Gradle daemon và toolchains.
- [Gradle Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html) — `java.toolchain`, `options.release`, Java compiler, Java launcher, auto provisioning.
- [Gradle Daemon and Daemon JVM Criteria](https://docs.gradle.org/current/userguide/gradle_daemon.html) — client vs daemon JVM, `JAVA_HOME`, `org.gradle.java.home`, daemon criteria.
- [Gradle Building Java Projects](https://docs.gradle.org/current/userguide/building_java_projects.html) — Java compilation, release targeting và test.
- [Maven Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html) — Maven process JDK khác compiler/test JDK.
- [Maven Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/) — discovery, `select-jdk-toolchain`, `toolchains.xml`.
- [Maven Toolchains: select-jdk-toolchain](https://maven.apache.org/plugins/maven-toolchains-plugin/select-jdk-toolchain-mojo.html) — ràng buộc version/vendor và JDK discovery.
- [Maven Compiler Plugin — `--release`](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html) — property `maven.compiler.release`.
- [Maven Compiler Plugin — Compiling Sources Using a Different JDK](https://maven.apache.org/plugins/maven-compiler-plugin/examples/compile-using-different-jdk.html) — compiler toolchain.
- [Maven Surefire Plugin — Using Toolchains](https://maven.apache.org/surefire/maven-surefire-plugin/examples/toolchains.html) — chọn JVM cho test.
