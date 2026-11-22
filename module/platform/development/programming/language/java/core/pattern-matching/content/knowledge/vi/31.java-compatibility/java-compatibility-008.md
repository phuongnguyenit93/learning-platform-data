# Kiểm tra toolchain của dự án khi dùng Java Pattern Matching

Một đoạn mã dùng `record pattern` hoặc `case Type variable when ...` có thể **biên dịch thành công trên máy của lập trình viên** nhưng thất bại trong CI, IDE hoặc container triển khai. Nguyên nhân thường không nằm ở logic pattern matching mà ở **toolchain**: phiên bản JDK thực sự dùng để biên dịch, mức ngôn ngữ `--release`, JDK mà Maven/Gradle lựa chọn, JVM chạy chương trình và các cấu hình riêng của IDE/test.

Bài học thuộc **Java Core Pattern Matching → Tương thích Java**, hướng dẫn cách **kiểm tra toolchain của dự án từ đầu đến cuối** trước khi sử dụng tính năng ngôn ngữ mới. Trọng tâm là những tính năng Java 16–21 thường gặp trong pattern matching, đặc biệt **record patterns** và **pattern matching for switch** đã hoàn thiện trong **Java 21**.

> **Nguyên tắc quan trọng:** “Máy có cài JDK 24” không đồng nghĩa “dự án đang biên dịch cho Java 24”; “`javac --release 21` thành công” cũng không đồng nghĩa “ứng dụng chắc chắn chạy được trên JVM 17”. Cần tách **JDK đang chạy compiler**, **mức target**, **các thư viện phụ thuộc**, và **JVM thực sự chạy ứng dụng**.

## 1. Toolchain trong một dự án Java gồm những gì?

**Java toolchain** không chỉ là một lệnh `java` trong terminal. Với một dự án thông thường, cần biết:

1. **JDK chạy trình biên dịch**: chẳng hạn `javac` của JDK 21 hoặc JDK 24.
2. **Mức source/release**: Java compiler được yêu cầu chấp nhận cú pháp và API của phiên bản nào.
3. **Build tool và wrapper**: Maven hoặc Gradle phiên bản nào đang thực thi build; wrapper có được pin trong repo không.
4. **JDK được build tool lựa chọn**: có thể khác với JDK đang chạy chính Maven/Gradle.
5. **JVM chạy unit/integration tests**: test có thể chạy với JVM khác JVM biên dịch.
6. **JVM production**: image Docker, máy chủ, runtime CI/CD hoặc thiết bị của khách hàng chạy phiên bản nào.
7. **IDE project SDK / language level**: IntelliJ IDEA, Eclipse, VS Code có thể chọn SDK khác biến môi trường shell.
8. **Dependency và plugin**: thư viện được build ở phiên bản Java khác, hoặc build plugin quá cũ để hiểu target mới.

Một cấu hình phải phù hợp **qua tất cả các chặng**:

~~~text
Source code + language level
          |
          v
JDK compiler --release + build plugins
          |
          v
.class bytecode + dependencies
          |
          v
Test JVM ---------> CI JVM ---------> Deployment JVM
~~~

Nếu thiếu một chặng, một dự án có thể “xanh” ở máy cá nhân nhưng “đỏ” ở hệ thống khác.

## 2. Biết chính xác tính năng Pattern Matching cần Java nào

| Tính năng ngôn ngữ | Bản ổn định đầu tiên | Dấu hiệu trong source |
| --- | --- | --- |
| `instanceof` kiểu cũ + cast | Có từ trước Java 8 | `if (x instanceof String) { String s = (String) x; }` |
| Switch expression | Java 14 (JEP 361) | `return switch (x) { case 1 -> "one"; default -> "other"; };` |
| Pattern matching for `instanceof` | Java 16 (JEP 394) | `if (x instanceof String text)` |
| Records | Java 16 (JEP 395) | `record Point(int x, int y) {}` |
| Sealed classes/interfaces | Java 17 (JEP 409) | `sealed interface Shape permits Circle, Square` |
| Record patterns | Java 21 (JEP 440) | `case Point(var x, var y) -> ...` |
| Pattern matching for `switch` | Java 21 (JEP 441) | `case String text -> ...` và `when` guard |

Những mốc trên là **phiên bản tính năng ổn định**, không phải lần đầu thử nghiệm trong preview. Chẳng hạn pattern matching for switch từng đi qua các bản preview, nhưng cú pháp ổn định trong Java 21 có `when` guard. Nếu cần dùng đúng cú pháp đã hoàn thiện, chọn **Java 21 trở lên** và không bật preview chỉ để sử dụng tính năng đã chính thức.

**Lưu ý về API:** `String.isBlank()` có từ Java 11. Mã dùng type patterns có thể chỉ cần mức ngôn ngữ Java 16, nhưng nếu đồng thời gọi một API được giới thiệu ở phiên bản mới hơn, target còn phải hỗ trợ API đó. Toolchain phải kiểm tra **cả cú pháp lẫn API**.

### Đừng đoán version qua phần mở rộng `.java`

Một tệp `.java` không mang thông tin phiên bản ngôn ngữ. Cùng một source có thể:
- Hợp lệ ở Java 21 nhưng sai ở Java 17.
- Hợp lệ về cú pháp Java 17 nhưng gọi API không có ở Java 17.
- Biên dịch ở JDK mới rồi tạo bytecode mà runtime cũ không thể nạp.

Muốn xác nhận, cần chạy compiler **với target thật sự được cấu hình**.

## 3. Bước đầu tiên: kiểm tra `java`, `javac` và `JAVA_HOME`

Mở terminal **đang dùng để build dự án** và chạy:

~~~bash
java -version
javac -version
~~~

`java -version` cho biết launcher/runtime đang được gọi; `javac -version` cho biết compiler đang được gọi. Cả hai cần được kiểm tra vì `PATH` có thể chứa các JDK khác nhau.

Trên Linux/macOS:

~~~bash
echo "$JAVA_HOME"
command -v java
command -v javac
java -version
javac -version
~~~

Trên Windows PowerShell:

~~~powershell
$env:JAVA_HOME
Get-Command java
Get-Command javac
where.exe java
where.exe javac
java -version
javac -version
~~~

**Cách diễn giải:**

- `JAVA_HOME` là vị trí JDK mà một số công cụ sử dụng; giá trị này **không tự thay đổi PATH** của mọi shell.
- `java` và `javac` có thể đến từ đường dẫn khác nhau; cần xem lệnh nào thực sự được shell chọn.
- IDE có thể khởi chạy bằng biến môi trường khác terminal.
- Maven/Gradle có thể dùng **toolchain JDK được chọn riêng**, dù launcher chạy từ JDK khác.

Nếu `javac` không tìm thấy, máy có thể chỉ có runtime hoặc `PATH` chưa trỏ đến compiler. Java Compiler API và `javac` yêu cầu môi trường có công cụ biên dịch; chỉ có một JRE cũ sẽ không đủ.

**Không kết luận chỉ từ một dòng phiên bản.** Hãy kiểm tra cả lệnh build thật của dự án.

## 4. Phân biệt JDK đang chạy và target `--release`

Với `javac` của một JDK đủ mới, có thể yêu cầu biên dịch theo phiên bản Java cũ hơn bằng:

~~~bash
javac --release 21 ToolchainSmokeTest.java
~~~

`--release 21` kiểm soát **mức cú pháp**, **định dạng class file mục tiêu** và các **API Java Platform công khai** sẵn có theo release được hỗ trợ. Đây là cách thường được ưu tiên khi cross-compile bằng JDK mới.

So sánh:

| Tùy chọn | Vai trò | Giới hạn cần nhớ |
| --- | --- | --- |
| `javac --release 21` | Biên dịch với ngôn ngữ/API/platform target Java 21 theo khả năng của JDK hiện dùng | Không biến JVM đang chạy thành Java 21; không kiểm chứng mọi dependency ngoài Java Platform |
| `javac -source 21 -target 21` | Chọn source grammar và bytecode target | Không có cùng bảo đảm chặn việc dùng API Java Platform mới hơn như `--release` |
| `java -version` | Xem JVM được launcher chọn | Không cho biết chắc compiler dùng trong Maven/Gradle |
| `javac -version` | Xem phiên bản compiler gọi trực tiếp | Không cho biết chắc IDE/toolchain đã chọn compiler nào |
| `java --enable-preview` | Bật tính năng preview phù hợp lúc chạy khi thật sự cần | Không tự biến cú pháp Java 21 thành cú pháp được hỗ trợ trên JVM 17 |

**Điểm cốt lõi:** Nếu máy cài JDK 24, `javac --release 21` vẫn có thể tạo class file chạy trên Java 21, miễn là source/API/dependencies tương thích. Cần **chạy thử trên JVM 21** để xác nhận hệ thống thực tế, vì build trên JDK 24 không phải phép thử runtime JDK 21.

Ngược lại, `javac --release 17` **không thể biên dịch** source chứa record pattern và pattern matching for switch theo cú pháp Java 21. Không có flag nào “backport” tự động ngôn ngữ Java 21 xuống Java 17.

### Bẫy của một lần biên dịch lỗi

Sau khi biên dịch thành công, nếu chạy lại `javac --release 17 ...` và compiler báo lỗi, một tệp `.class` cũ từ lần build trước có thể vẫn còn trong thư mục. **Đừng chạy class file cũ rồi cho rằng build 17 đã thành công.** Hãy dùng thư mục build sạch cho mỗi phép kiểm tra.

## 5. Ví dụ Java 21 dùng để smoke-test toolchain

Một smoke test nên dùng **đúng các tính năng mà module cần**, thay vì chỉ in `"Hello World"`. Ví dụ dưới đây kiểm tra đồng thời:

- `sealed interface` và các `record` implementations.
- Record pattern `Greet(User(var name))` và guard `when`.
- `switch expression` trả về kết quả từ các subtype.
- Nhánh fallback khi nested record không khớp.
- Xử lý selector `null` bằng `case null`.

Tạo tệp **`ToolchainSmokeTest.java`**:

~~~java
public class ToolchainSmokeTest {
    sealed interface Task permits Greet, Add, Ping {}

    record User(String name) {}
    record Greet(User user) implements Task {}
    record Add(int left, int right) implements Task {}
    record Ping() implements Task {}

    static String handle(Task task) {
        return switch (task) {
            case Greet(User(var name))
                    when name != null && !name.isBlank() ->
                    "Hello, " + name;
            case Greet(var user) -> "Invalid greeting";
            case Add(var left, var right) -> "Sum: " + (left + right);
            case Ping() -> "Pong";
            case null -> "No task";
        };
    }

    public static void main(String[] args) {
        System.out.println(handle(new Greet(new User("Mai"))));
        System.out.println(handle(new Greet(new User("   "))));
        System.out.println(handle(new Greet(null)));
        System.out.println(handle(new Add(2, 3)));
        System.out.println(handle(new Ping()));
        System.out.println(handle(null));
    }
}
~~~

### Biên dịch và chạy bằng JDK 21 trở lên

~~~bash
javac --release 21 -encoding UTF-8 ToolchainSmokeTest.java
java ToolchainSmokeTest
~~~

Đầu ra:

~~~text
Hello, Mai
Invalid greeting
Invalid greeting
Sum: 5
Pong
No task
~~~

**Giải thích:**

- `Greet(User("Mai"))` khớp nested record pattern, guard tên hợp lệ trả `"Hello, Mai"`.
- `Greet(User("   "))` khớp cấu trúc nhưng không qua guard, nên chọn `case Greet(var user)`.
- `Greet(null)` không khớp nested `User(var name)`; fallback nhận record `Greet` và trả `"Invalid greeting"`.
- `Add(2,3)` được phân rã thành hai số nguyên; `Ping()` là record không có component.
- `null` selector được xử lý riêng. `switch expression` không cần `default` vì những subtype đã bao phủ đầy đủ một sealed hierarchy và có nhánh null.

### Negative check: target cũ phải bị từ chối

Trên JDK đủ mới có hỗ trợ cả hai release, chạy riêng:

~~~bash
javac --release 17 ToolchainSmokeTest.java
~~~

**Kỳ vọng:** Compiler **từ chối** vì các pattern và `switch` patterns của ví dụ yêu cầu Java 21. Thông báo lỗi chính xác tùy phiên bản JDK; không nên dựa vào một câu chữ chẩn đoán bất biến.

Trong kiểm tra với Java Compiler API trên **JDK 24**, một phiên bản rút gọn dùng `sealed + record pattern + switch` cho kết quả:

~~~text
release 21: COMPILED; errors=0
release 17: REJECTED; errors=2
~~~

Đây là **kết quả kiểm tra target phiên bản**, không phải phép đo hiệu năng. Số lượng lỗi có thể khác nếu thay source, flags hoặc compiler; điều cốt lõi là success/failure đúng kỳ vọng.

## 6. Hiểu lỗi class-file version và runtime mismatch

Java biên dịch thành bytecode `.class` có **class file major version**. JVM quá cũ không thể nạp bytecode dành cho phiên bản mới hơn. Ví dụ những mốc thường dùng:

| Java target | Class file major version |
| --- | --- |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |

Có thể xem phiên bản class file đã biên dịch bằng:

~~~bash
javap -verbose ToolchainSmokeTest
~~~

Tìm dòng `major version: 65` khi class được tạo với target Java 21; nếu dùng JDK mới hơn và biên dịch **không đặt target**, bytecode có thể mang major version mới hơn.

Trên Linux/macOS có thể lọc bằng `grep`, còn trên Windows PowerShell có thể lọc bằng `Select-String`:

~~~powershell
javap -verbose ToolchainSmokeTest | Select-String "major version"
~~~

Khi chạy class Java 21 bằng một JVM 17, thường sẽ gặp `UnsupportedClassVersionError`, với thông điệp cho biết JVM không hỗ trợ class file version 65. **Đây là lỗi runtime**: source đã biên dịch nhưng JVM triển khai không hỗ trợ bytecode.

### `--release` không “hạ cấp” toàn bộ dependency

Ngay cả khi code của bạn biên dịch với `--release 17`, một thư viện bên ngoài được phát hành với bytecode Java 21 có thể **không chạy trên JVM 17**. Khi audit tương thích, cần xem **major version và yêu cầu runtime của dependency**, cũng như version của agent, framework hoặc plugin. `--release` giới hạn API Java Platform của mã đang biên dịch; nó không tự biên dịch lại các thư viện phụ thuộc.

**Đừng sửa sai bằng cách chỉnh tay class file major version.** Hạ con số trong bytecode không chuyển đổi cú pháp, bytecode instructions hoặc những API mới thành dạng mà JVM cũ hiểu.

## 7. Kiểm tra Maven toolchain

Với dự án Maven, bắt đầu bằng:

~~~bash
mvn -version
~~~

Nếu repo có **Maven Wrapper**, nên dùng wrapper:

~~~bash
./mvnw -version
./mvnw clean test
~~~

Trên Windows PowerShell, file wrapper thường là `mvnw.cmd`:

~~~powershell
.\mvnw.cmd -version
.\mvnw.cmd clean test
~~~

`mvn -version` hoặc `mvnw -version` hiển thị Java runtime dùng để **khởi chạy Maven**, không bảo đảm compiler và test JVM đã chọn cùng JDK đó.

### Cấu hình Java release trong `pom.xml`

Một cách thông dụng:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
~~~

Dự án cần phiên bản **Maven Compiler Plugin** hỗ trợ cấu hình release tương ứng và một JDK đủ mới. Cũng có thể cấu hình plugin tường minh:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <release>21</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Khi dùng trong dự án thật, **pin phiên bản plugin tương thích** trong parent POM hoặc plugin management. Bản minh họa tập trung vào `<release>`; phiên bản plugin cụ thể phải được chọn theo vòng đời build của dự án.

### Maven Toolchains: compiler có thể dùng JDK khác launcher

Nếu build cần chọn JDK 21 nhưng Maven chạy dưới một JDK khác, có thể cấu hình **Maven Toolchains Plugin** cùng file `~/.m2/toolchains.xml` mô tả những JDK có sẵn. Ví dụ cấu trúc metadata của một JDK đã cài:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
        </provides>
        <configuration>
            <jdkHome>/absolute/path/to/jdk-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

**Thay `/absolute/path/to/jdk-21` bằng đường dẫn thực**; trên Windows đó là một thư mục JDK của Windows. Chỉ có file này **chưa đủ**: build còn phải cấu hình plugin/toolchain selection phù hợp để các plugin liên quan thực sự dùng JDK đó.

Trong cấu hình Maven thực tế, cần kiểm tra riêng:
- Maven Compiler Plugin lấy compiler từ đâu, `release` hiệu lực là bao nhiêu?
- Maven Surefire/Failsafe chạy test trên JVM nào? Có cấu hình fork/JDK khác không?
- Plugin tạo source, annotation processor hay công cụ code generation có yêu cầu JVM riêng không?
- Parent POM và profile CI có ghi đè `maven.compiler.release` không?

**Checklist Maven ngắn:** xác nhận wrapper → `mvnw -version` → effective POM/active profiles khi cần → chạy `clean test` → xác minh compiler target và test runtime. Lỗi `release version 21 not supported` thường là dấu hiệu compiler đang được dùng **quá cũ** để nhận target 21, dù máy có thể đã cài JDK mới ở một đường dẫn khác.

## 8. Kiểm tra Gradle Java toolchains

Với dự án Gradle, ưu tiên **Gradle Wrapper**:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean test
~~~

Trên Windows PowerShell dùng `.\gradlew.bat`. Lệnh `javaToolchains` (trong dự án có cấu hình Java plugin phù hợp) giúp quan sát các JDK mà Gradle phát hiện. `gradlew --version` cho biết runtime/daemon sử dụng khi chạy Gradle, **không nhất thiết** trùng compiler toolchain.

Trong `build.gradle` (Groovy DSL):

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
~~~

Trong `build.gradle.kts` (Kotlin DSL):

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}
~~~

Tách hai khái niệm:

- `java.toolchain.languageVersion = 21`: yêu cầu Gradle chọn **JDK 21** phù hợp để biên dịch/chạy các tác vụ Java có dùng toolchain.
- `options.release = 21`: đặt mức Java Platform và bytecode target cho tác vụ biên dịch Java.

Toolchain Gradle có thể tự phát hiện JDK cài sẵn; **tự động tải JDK** còn phụ thuộc việc dự án đã cấu hình provisioning resolver phù hợp. Không nên giả định mọi máy/CI luôn tải được JDK chỉ vì khai báo `toolchain`.

**Chú ý compatibility của Gradle:** một phiên bản Gradle quá cũ có thể không hỗ trợ chạy trên một JDK mới hoặc không hỗ trợ đầy đủ Java toolchain target bạn chọn. Vì vậy ngoài phiên bản JDK, phải kiểm tra **phiên bản Gradle Wrapper** thực tế trong repo. Với multi-project build, cấu hình có thể khác giữa các subproject, test tasks và các plugin.

### Những lỗi Gradle hay gặp

- `No matching toolchains found`: Gradle không tìm thấy JDK phù hợp hoặc chưa có resolver để cấp phát JDK.
- Gradle daemon đang chạy bằng JDK cũ dù shell đã đổi `JAVA_HOME`: cần kiểm tra daemon và IDE Gradle JVM.
- `Unsupported class file major version` từ Gradle/plugin: bản Gradle hoặc plugin có thể không hiểu bytecode của một dependency/plugin mới.
- Build script chọn Java 21 nhưng test hoặc deployment dùng Java 17: build thành công, runtime có thể thất bại.

## 9. IDE: đừng để editor “xanh” nhưng CI “đỏ”

Mỗi IDE có thể có **JDK riêng để phân tích source**, **project language level**, **Gradle/Maven JVM** và **Run/Debug JRE**. Khi gặp mâu thuẫn, đừng chỉ sửa một dropdown.

| Môi trường | Nơi cần kiểm tra | Câu hỏi quan trọng |
| --- | --- | --- |
| IntelliJ IDEA | Project SDK; Project language level; Gradle JVM hoặc Maven runner/importer; Run configuration | IDE có dùng cùng JDK/release như build wrapper không? |
| Eclipse | Installed JREs/JDKs; compiler compliance level; Execution Environment; project JRE | Project compliance có là Java 21? Runtime launch có đúng không? |
| VS Code Java | Java runtime settings/extension; Maven/Gradle project import; terminal JDK | Extension dùng JDK nào; terminal và build wrapper có cùng cấu hình không? |
| CI server | Setup JDK step; env `JAVA_HOME`; image/container; build commands | Toolchain của CI có đúng và đủ JDK không? |
| Container production | Base image tag/digest; `java -version` trong container; classfile target | Runtime hỗ trợ bytecode và dependency không? |

**Quy trình thực tế:** chọn SDK/Gradle JVM phù hợp, **re-import project**, chạy build bằng wrapper ngay trong terminal, rồi chạy ứng dụng bằng runtime tương ứng. Không dựa độc nhất vào code highlighting hoặc thông báo “project SDK 21” để cho rằng CI đã dùng JDK 21.

Khi IDE/CI khác nhau, ghi lại những dòng bằng chứng có thể tái lập:
- Lệnh `java -version` và `javac -version` ở môi trường lỗi.
- Lệnh wrapper `-version`.
- Tùy chọn compiler `--release` hoặc cấu hình `maven.compiler.release`/Gradle `options.release`.
- Class file major version (nếu lỗi nạp class).
- Version plugin, runtime container và stack trace đầu tiên có ý nghĩa.

## 10. CI/CD: kiểm thử target trong môi trường thật

Một ví dụ job GitHub Actions minh họa cách chạy Maven Wrapper với JDK 21:

~~~yaml
name: Java 21 verification
on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
      - name: Inspect toolchain
        run: |
          java -version
          javac -version
          ./mvnw -version
      - name: Build and test
        run: ./mvnw -B -ntp clean verify
~~~

Đây là **ví dụ cấu hình**, không phải khẳng định các major version của GitHub Actions trong ví dụ là phiên bản mới nhất. Trong sản phẩm thật, nên chọn phiên bản action theo chính sách bảo mật của tổ chức và cân nhắc **pin theo commit SHA**.

Nếu repo dùng Gradle, thay lệnh Maven bằng `./gradlew --no-daemon clean test` và cấu hình cache tương ứng.

### Vì sao cần test trên JVM đích?

Biên dịch bằng JDK 24 với `--release 21` là một bài kiểm tra compile-time có ích. Nhưng để bảo đảm ứng dụng chạy trên **Java 21**, vẫn cần một lượt chạy test trên **JVM 21**. Các yếu tố ngoài cú pháp có thể phụ thuộc runtime: thư viện JNI, flags JVM, hệ thống module, dependency và cấu hình môi trường.

Trong dự án cần hỗ trợ nhiều Java runtime, xác định một **ma trận tương thích** bằng yêu cầu sản phẩm và chạy test trên từng runtime được cam kết. Đừng vô tình tuyên bố “hỗ trợ Java 17” khi source Java 21 đã dùng record patterns và switch patterns không thể compile với `--release 17`.

## 11. Chế độ preview và tính năng đã ổn định

Một nguồn nhầm lẫn là lấy hướng dẫn preview từ các phiên bản Java cũ rồi áp dụng cho Java 21:

- `record patterns` và `pattern matching for switch` **không cần preview** trong Java 21.
- `--enable-preview` chỉ dành cho những tính năng preview của **release đang sử dụng** và cần cấu hình biên dịch/chạy phù hợp.
- Bật preview trên JDK 17 **không làm cho cú pháp hoàn thiện của Java 21 trở nên khả dụng đầy đủ**. Những bản preview trước có thể có cú pháp/quy tắc khác, đặc biệt với guards.
- Nếu dự án thật dùng một tính năng preview, phải ghi rõ **JDK release**, compiler flags, runtime flags, chính sách nâng cấp và cách CI chạy test.
- Tránh bật preview mặc định trong một codebase không cần, vì nó làm khó việc kiểm soát hợp đồng và vòng đời tính năng.

**Đề xuất cho module Pattern Matching hiện đại:** chọn **Java 21** làm target tối thiểu khi cần record patterns và `switch` patterns chính thức; dùng `--release 21` (hoặc cấu hình tương đương) và không bật preview nếu không có tính năng preview khác.

## 12. Chẩn đoán nhanh các lỗi toolchain thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra và sửa |
| --- | --- | --- |
| `patterns in switch ... not supported in -source 17` hoặc thông điệp tương tự | `source/release` quá thấp cho pattern switch | Dùng release 21+ nếu được phép, hoặc viết code tương thích 17 |
| `release version 21 not supported` | `javac` được chọn quá cũ | Kiểm tra `javac -version` và toolchain của build; chọn JDK đủ mới |
| `UnsupportedClassVersionError` | JVM runtime quá cũ so với class-file major version | Xem `java -version` và `javap -verbose`; chỉnh target/runtime cho phù hợp |
| Build CLI thành công nhưng IDE báo lỗi `case ... when` | IDE SDK/language level/importer chưa đồng bộ | Kiểm tra project SDK, language level, re-import Gradle/Maven |
| IDE chạy được nhưng CI fail | CI JDK hoặc compiler target khác | In version/target trong CI; dùng wrapper và toolchain rõ ràng |
| Gradle không tìm thấy JDK 21 | JDK chưa cài hoặc resolver chưa cấu hình | Chỉ rõ toolchain và cấu hình provisioning khi cần |
| Maven dùng JDK sai dù `JAVA_HOME` đã đổi | Maven runner/toolchains/forked compiler khác môi trường shell | Kiểm tra Maven runtime, compiler plugin, toolchains và test JVM |
| Class được build với Java 21 nhưng dependency yêu cầu Java mới hơn | `--release` không hạ bytecode dependency | Kiểm tra minimum Java version của thư viện và class major |
| Source dùng `String.isBlank()` với `--release 8` | API Java 11 không có ở Java 8 | Chuyển sang API tương thích 8 hoặc nâng target theo yêu cầu |
| Code compile nhầm sau khi test release thấp | Tệp `.class` cũ còn trong build output | Dọn sạch output, build lại trong thư mục riêng |
| Toolchain chạy được trên một máy nhưng không tái lập | Không pin wrapper/JDK/dependencies | Dùng wrapper, toolchain version và CI xác nhận |

Thông báo lỗi cụ thể có thể thay đổi theo JDK và plugin. Hãy ưu tiên **tìm nguyên nhân**, không sửa mù bằng cách bật preview, bỏ `--release` hoặc ép IDE nhận cú pháp mới.

## 13. Quy trình kiểm tra toolchain theo từng bước

Một quy trình có thể dùng trong lúc nhận bàn giao dự án hoặc trước khi merge PR dùng Java Pattern Matching:

**Bước 1 — Ghi yêu cầu Java tối thiểu.** Xác định API phục vụ khách hàng có phải chạy trên JVM 17, JVM 21 hay mới hơn. Nếu code phải chạy trên Java 17, không thể tự ý nhập record patterns Java 21.

**Bước 2 — Kiểm tra JDK shell.** Chạy `java -version`, `javac -version`, `JAVA_HOME` và đường dẫn launcher. Phân biệt terminal Windows/Unix, IDE terminal và shell trong CI.

**Bước 3 — Kiểm tra wrapper và build config.** Với Maven, xem `mvnw`, compiler release, toolchains, test plugins. Với Gradle, xem `gradlew`, `java.toolchain`, `options.release` và môi trường daemon.

**Bước 4 — Kiểm tra có dùng preview không.** Nếu code yêu cầu Java 21 stable, thường không cần `--enable-preview`. Nếu đang bật preview, xác nhận nó phục vụ tính năng nào.

**Bước 5 — Compile từ output sạch.** Chạy build clean và smoke test với target yêu cầu. Tránh kết luận từ tệp `.class` cũ.

**Bước 6 — Chạy trên JVM mục tiêu.** Chạy test bằng **runtime thấp nhất được hỗ trợ**. Nếu target 21, kiểm tra thực sự có chạy trên JVM 21 khi cần cam kết tương thích với JVM 21.

**Bước 7 — Kiểm tra dependency/runtime image.** Xem minimum Java version của framework và thư viện; kiểm tra image Java dùng khi deploy không bị ghim ở phiên bản khác.

**Bước 8 — Đồng bộ IDE và CI.** Re-import project, cập nhật các run configs và in phiên bản JDK trong logs CI.

**Bước 9 — Ghi lại bằng chứng.** Lưu phiên bản JDK, wrapper, release, kết quả smoke test và những hạn chế môi trường vào tài liệu build hoặc log CI.

**Bước 10 — Đưa kiểm tra vào pipeline.** CI nên chạy tự động khi module thêm pattern matching mới hoặc nâng toolchain, thay vì dựa vào việc một lập trình viên chạy thành công trên máy cá nhân.

## 14. Bài tập tự luyện và đáp án

### Bài 1 — JDK mới nhưng `--release` cũ

Máy đã cài JDK 24. Dự án Maven cấu hình `<maven.compiler.release>17</maven.compiler.release>`. Người viết thêm `case Point(var x, var y) -> ...`. Lỗi là gì?

**Đáp án:** Record pattern trong `switch` được hoàn thiện từ Java 21, trong khi project target là Java 17. JDK 24 cài trên máy **không làm mất ràng buộc `--release 17`**. Phải xin phép nâng project target lên 21, hoặc viết cách xử lý tương thích Java 17 theo hợp đồng sản phẩm.

### Bài 2 — Compile được, chạy không được

Một `.class` có `major version 65` được chạy trên JVM 17. Điều gì xảy ra?

**Đáp án:** JVM 17 chỉ hỗ trợ các class file đến mức phù hợp với Java 17 (major 61); nạp class Java 21 (major 65) có thể ném `UnsupportedClassVersionError`. Muốn chạy trên JVM 17, cần build/source/dependencies tương thích Java 17; nếu không, phải nâng runtime lên phiên bản hỗ trợ Java 21.

### Bài 3 — Maven và terminal báo version khác nhau

`java -version` là 21, nhưng `./mvnw -version` báo đang chạy Java 17. Đâu là điều cần kiểm tra đầu tiên?

**Đáp án:** Kiểm tra `JAVA_HOME`, launcher của Maven Wrapper và cấu hình Maven runner/toolchains. Không kết luận compile target đang là 21 chỉ vì một lệnh `java` bên ngoài Maven báo 21. Xem cả compiler plugin và test JVM đang dùng.

### Bài 4 — Gradle Wrapper và `toolchain`

Trong `build.gradle` đã khai báo Java toolchain 21, nhưng `./gradlew -q javaToolchains` không hiển thị JDK 21 và build báo không tìm thấy toolchain. Có nên bỏ toolchain để build chạy tạm bằng JDK mặc định?

**Đáp án:** Không nên. Hãy cài JDK 21 hoặc cấu hình JDK provisioning/resolver phù hợp, kiểm tra version Gradle Wrapper và đường dẫn JDK. Bỏ ràng buộc có thể khiến mỗi máy dùng compiler khác nhau, giảm tính tái lập và khiến build tạo bytecode không đúng target.

### Bài 5 — Có cần `--enable-preview` cho record patterns Java 21?

**Đáp án:** Không. Record patterns (JEP 440) và pattern matching for switch (JEP 441) đã **finalized trong Java 21**. Chọn JDK/release phù hợp; chỉ bật preview nếu ứng dụng sử dụng **một tính năng preview khác** của chính release đó.

### Bài 6 — Kiểm tra source và runtime

Một nhóm chỉ chạy `javac --release 21` trên JDK 24 và thông báo “đã xác nhận hỗ trợ Java 21 trên production”. Điều này đầy đủ chưa?

**Đáp án:** Chưa. Đây là bằng chứng compile-time. Cần chạy test trên JVM 21, kiểm tra dependencies, launcher runtime của CI/deployment, class-file version và môi trường sản phẩm. `--release` không thay thế test thực tế.

## 15. Checklist trước khi merge mã Pattern Matching

- [ ] Biết chính xác feature nào đòi Java 16, 17 hay 21.
- [ ] Xác định minimum Java runtime mà sản phẩm cam kết.
- [ ] `java -version`, `javac -version` và JDK của build wrapper được ghi lại.
- [ ] Maven `maven.compiler.release` hoặc Gradle `options.release` khớp target.
- [ ] Maven Toolchains/Gradle Java Toolchains thực sự tìm được JDK cần thiết.
- [ ] IDE language level và runtime dùng để Run/Debug thống nhất với target.
- [ ] Không bật preview nếu không cần, không dựa vào cú pháp preview cũ.
- [ ] Biên dịch từ output sạch; source smoke test Java 21 chạy đúng.
- [ ] Runtime CI/deploy không thấp hơn classfile/dependency target.
- [ ] Có test trên runtime thấp nhất được hỗ trợ.
- [ ] Đã kiểm tra dependencies và build plugins không yêu cầu JDK khác.
- [ ] Có log/tài liệu ghi lại JDK, wrapper, target và kết quả smoke test.

## 16. Ghi nhớ và tài liệu tham khảo

**Ba câu hỏi cần trả lời trước tiên:**
1. **Ai đang biên dịch?** `javac` nào, do wrapper/toolchain nào chọn?
2. **Đang biên dịch cho Java nào?** `--release`/source/target bao nhiêu, có preview không?
3. **Ai đang chạy?** JVM của test, CI và production có tương thích classfile/dependencies không?

Với module dùng **record patterns + pattern matching for switch**, Java **21+** là mức tối thiểu cho cú pháp đã hoàn thiện. Một toolchain được quản lý tốt không chỉ giúp code biên dịch mà còn giúp **phát hiện lệch cấu hình sớm**, giảm “works on my machine” và làm rõ hợp đồng tương thích khi dự án nâng JDK.

**Nguồn chính thức:**
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394).
- [JEP 395 — Records](https://openjdk.org/jeps/395).
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [javac — Java Development Kit Tool Specifications](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html).
- [Maven Compiler Plugin: compile with a different Java version](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html).
- [Maven Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/).
- [Gradle Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html).
