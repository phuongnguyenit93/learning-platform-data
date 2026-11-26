# Đồng bộ JDK của IDE, javac, java và công cụ build cho từng bài thực hành

## 1. Mục tiêu và phạm vi

Một bài Java có thể chạy được trong IDE nhưng thất bại ở terminal, hoặc biên dịch được nhưng không chạy được. Trước khi sửa thuật toán, cần xác định **chương trình nào đang dùng JDK nào**. Cài một JDK mới chưa đủ để mọi công cụ tự chuyển sang JDK đó.

Trong chương **Vận dụng và nâng cấp** của module Java 22, bài này giúp bạn:

- Chọn phiên bản thực hành trước khi viết mã.
- Kiểm tra đường dẫn thực của `java`, `javac` và JVM chạy công cụ build.
- Đồng bộ IDE, compiler, JVM chạy test và JVM chạy ứng dụng.
- Dùng toolchain và `--release` đúng vai trò.
- Đưa cùng cấu hình vào máy khác hoặc CI và chẩn đoán lỗi lệch phiên bản.

Ta học những kiến thức của Java 22 còn dùng được ở Java hiện đại. Ví dụ xuyên suốt dùng **unnamed variable `_` trong `catch`**, tính năng đã trở thành chính thức ở Java 22 và vẫn có trong Java 25. Bài không yêu cầu bật preview. Xem [bảng tính năng ngôn ngữ theo phiên bản của Oracle](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-summary.html).

**Quy ước thực hành:** cấu hình mặc định dùng JDK 25, biên dịch cho Java 25 và chạy trên Java 25. Đây là một mốc hiện đại cụ thể để các ví dụ nhất quán; khi dự án chọn mốc khác, thay đổi theo hợp đồng phiên bản của dự án. Nhánh tùy chọn `--release 22` chỉ minh họa việc giữ mức tương thích Java 22 cho tính năng đã ổn định, không yêu cầu lấy JDK 22 làm môi trường mặc định.

Các tệp Java, POM và Gradle bên dưới là mẫu cho **một project thực hành riêng**. Chọn Maven hoặc Gradle theo project; không cần đưa cả hai vào cùng một bài.

## 2. Hiểu các lớp phiên bản trước khi đồng bộ

| Thành phần | Quyết định điều gì? | Bằng chứng nên kiểm tra |
| --- | --- | --- |
| JDK chạy IDE hoặc language server | Vận hành phần mềm hỗ trợ lập trình | Thông tin runtime của IDE/extension |
| Project SDK và module SDK | Thư viện nền tảng và môi trường dự án trong IDE | Project/module settings |
| Language level | Cú pháp mà IDE phân tích và cho phép | Cấu hình dự án sau khi import build |
| `javac` hoặc compiler toolchain | Trình biên dịch thực sự được dùng | Đường dẫn compiler và build log |
| `--release` | Mức ngôn ngữ, API nền tảng và định dạng class đầu ra | Cấu hình compiler có hiệu lực |
| JVM chạy Maven hoặc Gradle | Chạy plugin, build script và điều phối build | Wrapper `--version` hoặc `-v` |
| JVM chạy test | Thực thi các test của ứng dụng | Toolchain/launcher và log trong test |
| JVM chạy ứng dụng | Nạp và thực thi class đầu ra | `java.home`, `java.version` trong ứng dụng |

Với bài đơn giản, chọn cùng major version cho compiler, test và ứng dụng giúp giảm số biến cần kiểm tra. Tuy nhiên, JVM chạy build tool có thể khác compiler toolchain nếu tổ hợp đó được công cụ hỗ trợ và đã cấu hình rõ ràng. Maven có thể chọn một JDK build khác JDK đang chạy Maven; Gradle cũng phân biệt JVM của build với toolchain cho các task. Xem [Maven Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html) và [Gradle Toolchains](https://docs.gradle.org/current/userguide/toolchains.html).

Hai ví dụ cần phân biệt:

```text
Bài thực hành mặc định:
IDE project SDK 25 → compiler JDK 25 → release 25 → chạy/test Java 25

Biên dịch cho mức tương thích Java 22:
IDE project SDK 25, language level 22
                   → compiler JDK 25 → release 22 → chạy trên Java 25
```

Ví dụ thứ hai không chứng minh ứng dụng đã được kiểm thử trên Java 22. Nó chỉ cho biết compiler tạo đầu ra theo mức 22; muốn cam kết hỗ trợ runtime 22 phải chạy thử trên runtime đó, kiểm tra dependency và những hành vi liên quan.

## 3. Chốt hợp đồng phiên bản cho từng bài

Trước khi bắt đầu, ghi được các giá trị sau từ cấu hình project hoặc yêu cầu bài học:

| Thuộc tính | Mẫu mặc định trong bài |
| --- | --- |
| Compiler JDK | 25 |
| Release đích | 25 |
| Runtime ứng dụng | 25 |
| Runtime test nếu có | 25 |
| Preview | Tắt |
| Build tool | Phiên bản được cố định bằng Wrapper và tương thích JDK đã chọn |

Phân biệt **major version** và **bản vá**. `25.0.x` cùng thuộc major 25, nhưng để tái lập một kết quả cụ thể có thể cần ghi thêm vendor, bản vá, hệ điều hành và kiến trúc. Cấu hình toolchain chỉ chọn major 25 chưa khóa toàn bộ các thông tin đó.

Không suy phiên bản JDK đang chạy từ tên folder bài học, tên repository hoặc chỉ từ nhãn SDK trong IDE. Dùng cấu hình có hiệu lực và đường dẫn được công cụ báo ra.

## 4. Kiểm tra terminal: JAVA_HOME và PATH là hai đầu vào khác nhau

### 4.1. Thu thập bằng chứng trên PowerShell

Chạy trong terminal mà bạn sẽ dùng để build:

```powershell
$env:JAVA_HOME
Get-Command java -All | Select-Object CommandType, Name, Source, Definition
Get-Command javac -All | Select-Object CommandType, Name, Source, Definition
where.exe java
where.exe javac
java --version
javac --version
```

`Get-Command` giúp phát hiện cả alias hoặc function có cùng tên. `where.exe` liệt kê executable được tìm thấy theo cơ chế tìm đường dẫn của Windows. Nếu hai lệnh chỉ tới hai bộ cài khác nhau, sửa cách chọn executable trước khi sửa source code.

`JAVA_HOME` nên trỏ tới **thư mục gốc JDK**, chẳng hạn `C:\Java\jdk-25`, nơi có `bin\java.exe` và `bin\javac.exe`. `PATH` thường cần mục `C:\Java\jdk-25\bin`. Giá trị `JAVA_HOME` không chứa sẵn dấu ngoặc kép và không kết thúc bằng `\bin`.

Đặt `JAVA_HOME` không tự thay executable mà lệnh `java` trên terminal tìm thấy. Một mục PATH cũ, shim của trình quản lý phiên bản hoặc alias vẫn có thể được chọn.

### 4.2. Chọn JDK trong phiên terminal hiện tại

Thay đường dẫn dưới đây bằng bộ JDK đã cài trên máy:

```powershell
$practiceJdkPath = 'C:\Java\jdk-25'

if (-not (Test-Path -LiteralPath "$practiceJdkPath\bin\java.exe")) {
    throw 'Không tìm thấy java.exe của JDK thực hành'
}
if (-not (Test-Path -LiteralPath "$practiceJdkPath\bin\javac.exe")) {
    throw 'Không tìm thấy javac.exe của JDK thực hành'
}

$env:JAVA_HOME = $practiceJdkPath
$env:Path = "$practiceJdkPath\bin;$env:Path"

& "$practiceJdkPath\bin\java.exe" --version
& "$practiceJdkPath\bin\javac.exe" --version
java --version
javac --version
```

Hai lời gọi có đường dẫn tuyệt đối xác nhận bộ cài mong muốn. Hai lời gọi cuối kiểm tra cách terminal phân giải lệnh. Nếu kết quả khác nhau, quay lại `Get-Command`; không mặc định cho rằng thay PATH đã xử lý được alias hoặc function.

Thay đổi trên chỉ áp dụng cho process PowerShell này và process con được tạo sau đó. Một IDE đã mở trước đó không nhận lại môi trường mới từ terminal này. Sau khi sửa biến môi trường ở cấp hệ điều hành, mở terminal mới và khởi động lại IDE khi cần.

Trên Bash hoặc Zsh, thực hiện bước tương đương:

```bash
export JAVA_HOME=/duong/dan/toi/jdk-25
export PATH="$JAVA_HOME/bin:$PATH"
command -v java
command -v javac
java --version
javac --version
```

Các lệnh terminal chỉ xác nhận terminal. IDE và build tool có thể có lựa chọn JDK riêng.

## 5. Hiểu đúng --release

Với JDK 25, lệnh sau biên dịch theo Java 25:

```powershell
javac --release 25 -encoding UTF-8 -d out src/main/java/lab/JdkAlignmentDemo.java
```

`--release` kiểm soát mức ngôn ngữ, API nền tảng được tham chiếu và class file đích. Tùy chọn này không cài JDK, không thay JVM chạy ứng dụng và không đổi phiên bản thư viện bên thứ ba. Không thể dùng compiler JDK 21 để yêu cầu `--release 25`. Danh sách release mà một compiler hỗ trợ có trong `javac --help`. Xem [đặc tả lệnh javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html).

Nếu bài chỉ dùng tính năng chính thức đã có ở Java 22, JDK 25 có thể biên dịch cùng source cho release 22:

```powershell
javac --release 22 -encoding UTF-8 -d out22 src/main/java/lab/JdkAlignmentDemo.java
```

Chọn `22` chỉ khi đó là mục tiêu tương thích của bài. Nếu source dùng một tính năng hoặc API mới hơn 22, compiler phải báo lỗi ở chế độ này. Giữ cấu hình `release` trong build file thay vì phụ thuộc vào tùy chọn gõ tay.

Ví dụ về ba câu hỏi độc lập:

| Câu hỏi | Đầu vào cần xem |
| --- | --- |
| Ai biên dịch? | JDK compiler/toolchain |
| Biên dịch cho mức nào? | `--release` |
| Ai thực thi kết quả? | Java launcher/runtime |

Maven cũng khuyến khích dùng thuộc tính `maven.compiler.release` để biểu đạt mức Java đích. Xem [hướng dẫn chọn Java target của Maven](https://maven.apache.org/guides/mini/guide-java-target.html).

## 6. Chương trình kiểm tra dùng tính năng chính thức từ Java 22

Tạo `src/main/java/lab/JdkAlignmentDemo.java` trong project thực hành:

```java
package lab;

import java.util.List;

public class JdkAlignmentDemo {
    public static void main(String[] args) {
        int expectedFeature = args.length == 0 ? 25 : Integer.parseInt(args[0]);
        int actualFeature = Runtime.version().feature();

        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("java.home=" + System.getProperty("java.home"));

        if (actualFeature != expectedFeature) {
            throw new IllegalStateException(
                    "Expected Java " + expectedFeature + ", got " + actualFeature);
        }

        int accepted = 0;
        int rejected = 0;

        for (String input : List.of("22", "invalid", "25")) {
            try {
                Integer.parseInt(input);
                accepted++;
            } catch (NumberFormatException _) {
                rejected++;
            }
        }

        if (accepted != 2 || rejected != 1) {
            throw new IllegalStateException("Unexpected validation result");
        }

        System.out.println("accepted=" + accepted + ", rejected=" + rejected);
    }
}
```

Đây là bài kiểm tra đầu vào có parse được hay không, nên khối `catch` chỉ cần loại ngoại lệ và không cần giữ đối tượng ngoại lệ. `_` thể hiện điều đó; không thể đọc giá trị của `_` ở bên trong khối. Cú pháp này thuộc tính năng chính thức của Java 22, không cần `--enable-preview` khi dùng JDK 22 hoặc 25. Xem [unnamed variables và patterns trong tài liệu Java 25](https://docs.oracle.com/en/java/javase/25/language/unnamed-variables-patterns.html).

Biên dịch và chạy trực tiếp từ thư mục gốc project:

```powershell
javac --release 25 -encoding UTF-8 -d out src/main/java/lab/JdkAlignmentDemo.java
if ($LASTEXITCODE -ne 0) { throw 'Biên dịch thất bại' }
java -cp out lab.JdkAlignmentDemo
if ($LASTEXITCODE -ne 0) { throw 'Chạy kiểm tra thất bại' }
```

Đầu ra phải có `java.version` thuộc major 25, `java.home` trỏ đúng bộ cài và dòng cuối:

```text
accepted=2, rejected=1
```

Chương trình chỉ báo runtime đang thực thi; nó không tự xác nhận JDK từng biên dịch class. Để kiểm tra compiler, vẫn cần đường dẫn `javac` và log toolchain.

Kiểm tra thêm đầu ra compiler:

```powershell
javap -verbose -classpath out lab.JdkAlignmentDemo |
    Select-String 'minor version|major version'
```

Release 25 thông thường cho `major version: 69`; release 22 cho `major version: 66`. Class thông thường trong ví dụ có minor version 0. Class phụ thuộc preview có quy tắc minor version riêng; không diễn giải major version như bằng chứng về vendor hay bản vá compiler. Xem [định dạng class file trong JVM Specification](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html).

Nếu biên dịch vào `out22`, có thể chạy kết quả trên Java 25:

```powershell
java -cp out22 lab.JdkAlignmentDemo 25
```

Tham số `25` là runtime mong đợi, không phải release từng dùng để biên dịch. Nếu có một runtime 22 dành riêng cho kiểm tra tương thích, chạy bằng đường dẫn tuyệt đối tới runtime đó và truyền `22`.

## 7. Nhánh Maven: cố định toolchain và release

### 7.1. POM cho bài thực hành

Mẫu này dùng Maven 3.9.x qua Wrapper của project. Các phiên bản plugin được ghi rõ để ví dụ có cấu hình xác định; chúng không biểu đạt yêu cầu phải dùng bản mới nhất tại mọi thời điểm.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>jdk-alignment-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <practice.jdk>25</practice.jdk>
        <maven.compiler.release>25</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-toolchains-plugin</artifactId>
                <version>3.3.0</version>
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
                            <version>${practice.jdk}</version>
                        </jdk>
                    </toolchains>
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
                <version>3.5.4</version>
                <configuration>
                    <forkCount>1</forkCount>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Goal `toolchain` chọn toolchain trong phase `validate`, trước phase biên dịch. Việc có cấu hình plugin mà không có execution sẽ không tự chạy goal này trong lifecycle. Xem [maven-toolchains-plugin:toolchain](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchain-mojo.html).

### 7.2. Ánh xạ JDK trên từng máy

Với cơ chế toolchain khai báo tường minh của mẫu trên, đặt ánh xạ trong `toolchains.xml` thuộc thư mục `.m2` của tài khoản người dùng. Trên Windows, vị trí mặc định thường là `%USERPROFILE%\.m2\toolchains.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>25</version>
        </provides>
        <configuration>
            <jdkHome>C:\Java\jdk-25</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

Thay `jdkHome` bằng đường dẫn thật. Nhãn `<version>25</version>` do người cấu hình khai báo; cần kiểm tra executable ở `jdkHome` thực sự thuộc JDK 25. Không coi nhãn đó là bằng chứng thay thế cho `java --version` và `javac --version`.

POM giữ yêu cầu của project; `toolchains.xml` giữ vị trí bộ cài trên máy. Không đưa đường dẫn cá nhân vào POM dùng chung. Xem [cách khai báo và chọn toolchain Maven](https://maven.apache.org/plugins/maven-toolchains-plugin/usage.html).

### 7.3. Xác minh bằng Wrapper

Nếu project đã có Maven Wrapper:

```powershell
.\mvnw.cmd -v
.\mvnw.cmd clean verify
if ($LASTEXITCODE -ne 0) { throw 'Maven build thất bại' }
java -cp target/classes lab.JdkAlignmentDemo
```

Trên Linux/macOS, dùng `./mvnw`. Nếu chưa có Wrapper, có thể kiểm tra ban đầu bằng `mvn` đã cài, nhưng cần cố định phiên bản Maven theo quy ước project trước khi dùng kết quả cho máy khác hoặc CI.

Đọc kết quả theo từng vai trò:

- `mvnw -v` cho biết JVM đang chạy Maven.
- Build log phải cho thấy toolchain phù hợp và đường dẫn JDK được chọn.
- `maven.compiler.release` quyết định release đích.
- Lệnh `java -cp ...` ở cuối dùng Java mà terminal phân giải; kiểm tra `java.home` được chương trình in ra.

Surefire mặc định có thể dùng JDK toolchain của Maven để khởi chạy JVM test. Nếu project có `<jvm>`, `<jdkToolchain>` riêng hoặc cấu hình không fork, phải đối chiếu lại; ví dụ trên dùng fork để test có JVM riêng. Chỉ plugin hỗ trợ toolchain mới nhận lựa chọn đó. Xem [Surefire và Maven Toolchains](https://maven.apache.org/surefire/maven-surefire-plugin/examples/toolchains.html).

Mẫu không thêm framework unit test. Vì vậy `verify` thành công khi chưa có test **không phải** bằng chứng rằng JVM test đã chạy. Với bài có test, kiểm tra test thực sự được thực thi và ghi `java.home`, `java.version` ngay từ test khi cần xác minh runner.

Khi cần chẩn đoán cấu hình Maven kế thừa từ parent hoặc profile, xem effective POM và log chi tiết:

```powershell
.\mvnw.cmd help:effective-pom
.\mvnw.cmd -X test
```

Kiểm tra cấu hình có hiệu lực thay vì chỉ nhìn một thuộc tính vừa sửa. Không đăng nguyên log chi tiết nếu log có đường dẫn nội bộ hoặc thông tin cấu hình không cần thiết cho người nhận.

## 8. Nhánh Gradle: phân biệt daemon JVM và task toolchain

### 8.1. Chọn Wrapper tương thích

JDK chạy Gradle và JDK dùng để compile là hai điều kiện tương thích khác nhau. Mốc hỗ trợ đã được công bố:

| JDK | Gradle bắt đầu hỗ trợ toolchain | Gradle bắt đầu chạy được trên JDK đó |
| --- | --- | --- |
| 22 | 8.7 | 8.8 |
| 25 | 9.1.0 | 9.1.0 |

Đây là mốc tối thiểu liên quan đến Java, không phải đề xuất giữ mãi các bản Gradle đầu tiên ấy. Chọn bản Wrapper được dự án duyệt, kiểm tra plugin đi kèm và [ma trận tương thích chính thức](https://docs.gradle.org/current/userguide/compatibility.html).

### 8.2. build.gradle.kts cho bài thực hành

Mẫu dưới đây chọn compiler, runtime của task `Test` và runtime của task `JavaExec` ở cùng major 25:

```kotlin
import org.gradle.api.tasks.JavaExec
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test

plugins {
    application
}

val practiceJdk = 25
val practiceRelease = 25

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(practiceJdk))
    }
}

val practiceCompiler = javaToolchains.compilerFor {
    languageVersion.set(JavaLanguageVersion.of(practiceJdk))
}

val practiceLauncher = javaToolchains.launcherFor {
    languageVersion.set(JavaLanguageVersion.of(practiceJdk))
}

tasks.withType<JavaCompile>().configureEach {
    javaCompiler.set(practiceCompiler)
    options.release.set(practiceRelease)
    options.encoding = "UTF-8"
}

tasks.withType<Test>().configureEach {
    javaLauncher.set(practiceLauncher)
}

tasks.withType<JavaExec>().configureEach {
    javaLauncher.set(practiceLauncher)
}

application {
    mainClass.set("lab.JdkAlignmentDemo")
}

tasks.register("showPracticeJdk") {
    doLast {
        println("gradle.java.home=" + System.getProperty("java.home"))
        println("compiler=" + practiceCompiler.get().executablePath)
        println("launcher=" + practiceLauncher.get().executablePath)
    }
}
```

Compiler và launcher được gắn tường minh giúp quan sát từng vai trò trong bài này. Xem [cách cấu hình Java task của Gradle](https://docs.gradle.org/current/userguide/building_java_projects.html). Plugin `application` cung cấp task `run` để chạy main class; xem [Gradle Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html).

Chạy từ thư mục gốc project có Gradle Wrapper:

```powershell
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains
.\gradlew.bat showPracticeJdk
.\gradlew.bat clean build run --info
if ($LASTEXITCODE -ne 0) { throw 'Gradle build hoặc chạy thất bại' }
```

Trên Linux/macOS, dùng `./gradlew`. Phân biệt thông tin JVM launcher/daemon trong `--version`, danh sách JDK phát hiện được trong `javaToolchains`, và JDK đã chọn cho task trong `showPracticeJdk` hoặc log task. Có JDK trong danh sách không có nghĩa task đã chọn JDK đó.

Gradle cần tìm thấy JDK đáp ứng yêu cầu. Nếu không tìm thấy, cài hoặc khai báo đúng vị trí JDK, hay dùng cơ chế tải toolchain đã cấu hình của project. Khai báo `JavaLanguageVersion.of(25)` không đồng nghĩa mọi máy tự tải được JDK mà không có cấu hình bổ sung.

Nếu project không có test, task `test` có thể báo `NO-SOURCE`; khi ấy chưa có JVM test thực thi mã. Với project có test, xác nhận test chạy thật và quan sát runtime ngay trong test. Xem [các task của Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html).

### 8.3. Khi daemon hoặc cấu hình riêng làm kết quả khác dự kiến

Sau khi đổi JDK, kiểm tra cấu hình JVM của IDE, `org.gradle.java.home` và tiêu chí JVM daemon nếu project đã dùng tính năng đó. Toolchain task không tự thay JVM chạy daemon.

Có thể dừng daemon của phiên bản Gradle đang dùng rồi build lại để loại bỏ nhầm lẫn khi chẩn đoán:

```powershell
.\gradlew.bat --stop
.\gradlew.bat --version
.\gradlew.bat clean build run --info
```

Dừng daemon không sửa được một đường dẫn JDK đã cấu hình sai. Cần tìm lựa chọn có hiệu lực, sửa nó và kiểm tra lại đường dẫn task.

## 9. Đồng bộ IDE theo cấu hình build

### 9.1. IntelliJ IDEA

Kiểm tra các lớp cấu hình tương ứng với cách bạn chạy bài:

1. Thêm JDK thật vào danh sách SDK của IDE; chọn thư mục gốc JDK.
2. Chọn Project SDK 25 và để các module thực hành kế thừa SDK đó, trừ khi bài có yêu cầu riêng.
3. Chọn language level tương ứng release đích và tắt preview cho bài này.
4. Trong cấu hình Run/Debug của ứng dụng và test, kiểm tra JRE/JDK được chọn.
5. Reload project từ Maven hoặc Gradle sau khi thay build file.

Project SDK và module SDK là các lựa chọn riêng; một module vẫn có thể giữ SDK cũ dù Project SDK đã đổi. Xem [cấu hình SDK của IntelliJ IDEA](https://www.jetbrains.com/help/idea/sdk.html).

Với Maven, kiểm tra thêm **JDK for importer** và **Maven Runner JRE**. JVM dùng để import hoặc chạy Maven goals không tự chứng minh compiler đã chọn đúng toolchain. Xem [tích hợp Maven trong IntelliJ IDEA](https://www.jetbrains.com/help/idea/maven-support.html).

Với Gradle, kiểm tra **Gradle JVM**, chọn Wrapper của project và thống nhất cách build/run/test. Trong bài này, dùng Gradle để build và chạy test giúp bám cấu hình task đã khai báo. Nếu dùng runner riêng của IDE, kiểm tra runtime riêng của runner đó. Xem [Gradle settings của IntelliJ IDEA](https://www.jetbrains.com/help/idea/gradle-settings.html).

Tên hoặc vị trí một số mục có thể thay đổi giữa các bản IDE; đối chiếu theo vai trò trên. Runtime dùng để khởi động IDE có thể do IDE quản lý riêng, không cần thay nó chỉ để đổi JDK của project.

### 9.2. Visual Studio Code

Dùng lệnh **Java: Configure Java Runtime** để xem các runtime của project. Có thể ánh xạ JDK đã cài trong thiết lập cá nhân hoặc workspace phù hợp:

```json
{
  "java.configuration.runtimes": [
    {
      "name": "JavaSE-25",
      "path": "C:/Java/jdk-25",
      "default": true
    }
  ]
}
```

`default: true` dành cho folder Java không có build tool quản lý. Với project Maven/Gradle, vẫn phải sửa `pom.xml` hoặc Gradle build rồi import lại. JDK vận hành language server là lớp cấu hình khác; kiểm tra yêu cầu của extension đang dùng khi lớp đó gặp lỗi. Xem [quản lý Java project trong VS Code](https://code.visualstudio.com/docs/java/java-project).

Sau khi cấu hình, chạy `JdkAlignmentDemo` bằng nút Run của IDE và bằng Wrapper ở terminal. So sánh `java.home`, major version và kết quả nghiệp vụ nhỏ trong ví dụ. Nếu hai nơi khác nhau, đã có bằng chứng để tìm runner đang dùng JDK ngoài dự kiến.

## 10. Preview: chỉ bật khi bài thực sự yêu cầu

Một tính năng từng ở trạng thái preview tại Java 22 có thể có cú pháp hoặc API khác khi trở thành chính thức. Với bài học hiện đại, dùng dạng chính thức ở release đích và bỏ cờ preview nếu không còn tính năng preview nào được dùng.

Quy tắc cần nhớ:

- Preview gắn với một release cụ thể.
- Compiler dùng preview phải thuộc chính release đó; không dùng JDK 25 với `--enable-preview --release 22` để tái hiện preview của Java 22.
- Chương trình phụ thuộc preview cần được bật preview ở runtime và các runner liên quan; bật ở IDE hoặc compiler một nơi chưa đủ.
- Với `_` trong ví dụ này, preview phải để tắt.

Xem [quy tắc biên dịch và chạy preview của Oracle](https://docs.oracle.com/en/java/javase/25/language/preview-language-vm-features.html). Không dùng `--enable-preview` như một cách sửa chung cho mọi lỗi cú pháp mới.

## 11. Chẩn đoán theo triệu chứng

| Triệu chứng | Giả thuyết cần kiểm tra | Bước xác minh hoặc sửa |
| --- | --- | --- |
| `java` là 25 nhưng `javac` là 21 | Hai lệnh trỏ vào hai bộ cài | Xem `Get-Command -All`, PATH và đường dẫn tuyệt đối |
| `release version 25 not supported` | Compiler thực tế chưa hỗ trợ release 25 | Xem compiler toolchain và `javac --help`; đổi compiler đúng hợp đồng |
| `UnsupportedClassVersionError` | Runtime đang nạp class có phiên bản cao hơn nó hỗ trợ | Xem tên class trong lỗi; đối chiếu JVM thực thi và class file, kể cả dependency |
| IDE báo lỗi `_` nhưng Wrapper build được | Language level, SDK hoặc bộ phân tích của IDE không phù hợp | Kiểm tra SDK, language level, hỗ trợ phiên bản Java của IDE rồi reload build |
| IDE chạy được nhưng terminal không chạy | Terminal phân giải Java khác Run configuration | So sánh `java.home` của hai lần chạy |
| Maven báo không có toolchain phù hợp | Yêu cầu POM không khớp ánh xạ JDK máy | Kiểm tra `toolchains.xml`, nhãn version và `jdkHome` thật |
| Gradle không tìm thấy toolchain | Không có hoặc không phát hiện được JDK yêu cầu | Xem `javaToolchains`, vị trí JDK và cấu hình tải toolchain |
| Gradle lỗi trước phase compile sau khi đổi Java | Wrapper hoặc plugin không tương thích JVM chạy build | Đối chiếu ma trận tương thích và JVM daemon |
| Test lỗi class version nhưng main chạy được | JVM test và JVM ứng dụng khác nhau | Kiểm tra Surefire/Gradle Test launcher hoặc IDE test runner |
| `NoSuchMethodError` sau build thành công | API/runtime hoặc các bản dependency không khớp | Xem method/class trong lỗi, release đích và classpath thực tế |
| `verify` hoặc `build` xanh nhưng chưa có bằng chứng JVM test | Không có test, test bị bỏ qua hoặc bị skip | Xem số test chạy và runtime được ghi ngay trong test |

Đây là các giả thuyết khởi đầu, không phải ánh xạ tuyệt đối. Ví dụ `UnsupportedClassVersionError` có thể đến từ plugin được build bằng Java mới hơn JVM chạy Maven/Gradle, trước khi compiler đụng tới mã ứng dụng. Xác định process và class gây lỗi trước khi đổi cấu hình.

## 12. Quy trình lặp lại cho từng bài và trên CI

1. **Đọc yêu cầu bài:** xác định tính năng nào đã chính thức, release đích và runtime cần kiểm tra.
2. **Chọn compiler JDK:** cấu hình toolchain thay vì trông vào JDK tình cờ đứng đầu PATH.
3. **Kiểm tra terminal:** lưu thông tin version và đường dẫn `java`, `javac` cần thiết cho việc tái lập.
4. **Kiểm tra Wrapper:** xác nhận phiên bản build tool và JVM chạy nó tương thích nhau.
5. **Đồng bộ IDE:** Project/module SDK, language level, build JVM và Run/Debug runner.
6. **Build sạch một lần sau khi đổi hợp đồng:** tránh kết luận từ class cũ; dùng thư mục đầu ra riêng khi thử nhiều release bằng `javac`.
7. **Chạy kiểm tra thực tế:** compile tính năng trong bài, chạy main, chạy test nếu có và xem runtime từ chính process đó.
8. **Lặp lại bằng Wrapper ngoài IDE:** một kết quả chỉ có trong IDE chưa đủ chứng minh máy khác build được.

Trên CI, áp dụng đúng hợp đồng như máy cá nhân: cung cấp JDK mong muốn, dùng Wrapper đã commit, cấu hình toolchain và chạy cùng lệnh kiểm tra. Nếu có container build hoặc container chạy ứng dụng, kiểm tra JDK bên trong từng container; JDK trên host không quyết định runtime bên trong chúng.

Giữ yêu cầu phiên bản trong build file dùng chung, còn vị trí cài JDK ở cấu hình của máy hoặc môi trường CI. Khi hai máy cùng major nhưng vẫn cho kết quả khác, bổ sung thông tin vendor, bản vá, kiến trúc, dependency và cấu hình chạy vào bằng chứng chẩn đoán.

## 13. Bài thực hành và tiêu chí hoàn thành

Thực hiện tuần tự trong project thực hành:

1. Chạy các lệnh kiểm tra terminal, ghi lại `JAVA_HOME` và đường dẫn hai executable.
2. Biên dịch/chạy `JdkAlignmentDemo` trực tiếp với release 25.
3. Chọn Maven hoặc Gradle, áp dụng cấu hình mẫu và build bằng Wrapper.
4. Chạy lại bằng IDE; đối chiếu `java.home` với lần chạy terminal.
5. Biên dịch cùng source với `--release 22`, dùng thư mục `out22` riêng và xem major version bằng `javap`.
6. Chạy bản `out22` trên Java 25 và giải thích vì sao runtime vẫn là 25.
7. Tạo lỗi có kiểm soát bằng cách chạy trên Java 25 nhưng truyền kỳ vọng 22: `java -cp out22 lab.JdkAlignmentDemo 22`. Chương trình phải báo runtime không khớp; chạy lại với kỳ vọng 25 để hoàn tất.

Đạt yêu cầu khi bạn có thể chỉ ra:

- Compiler thực sự dùng thuộc JDK nào và ở đường dẫn nào.
- Release đích nằm ở đâu trong build file.
- JVM chạy build tool và JVM chạy ứng dụng có đúng hợp đồng hay không.
- JVM test được chọn thế nào, và có test thực sự chạy hay chưa.
- Cách IDE lấy cấu hình từ build và cách phát hiện một runner riêng đang dùng JDK khác.
- Lý do ví dụ `_` chạy được mà không bật preview.

Kết quả cần đạt là một bài thực hành có cấu hình rõ ràng và kiểm chứng được ở từng process. Khi đổi bài hoặc nâng JDK, áp dụng lại quy trình này thay vì tiếp tục dựa vào một môi trường chưa được xác nhận.
