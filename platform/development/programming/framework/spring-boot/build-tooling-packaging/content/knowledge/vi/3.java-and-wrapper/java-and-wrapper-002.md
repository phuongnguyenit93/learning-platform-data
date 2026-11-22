# Phân biệt JDK chạy Maven hoặc Gradle với JDK dùng để biên dịch

## 1. Bài toán và kết quả cần nắm

Trong một dự án Java/Spring Boot, câu “máy đang dùng Java 21” **chưa đủ** để kết luận mã nguồn được biên dịch bằng JDK 21 hoặc ứng dụng chỉ chạy được trên Java 21. Mỗi giai đoạn có thể chọn một Java khác nhau:

1. **Java chạy công cụ build:** JVM khởi động Maven hoặc Gradle; với Gradle hiện đại cần phân biệt thêm **client JVM** và **daemon JVM**.
2. **JDK biên dịch (compiler/toolchain):** bộ JDK cung cấp `javac` và các công cụ cho tác vụ biên dịch.
3. **Java release đích:** mức ngôn ngữ, API và phiên bản bytecode mà compiler sinh ra, ví dụ `--release 17`.
4. **JVM chạy test và ứng dụng:** môi trường thực sự nạp và chạy bytecode đã tạo. Nó có thể khác JDK dùng cho build và compile.
5. **Maven/Gradle Wrapper:** cách dự án gọi **phiên bản Maven/Gradle đã chọn**; wrapper không đồng nghĩa với chọn JDK biên dịch.

**Ví dụ đúng:** máy cài JDK 21 và JDK 17; Maven chạy trên Java 21, Maven Toolchains chọn `javac` của JDK 17 và mã được build với release 17. Hoặc Gradle daemon chạy Java 21 trong khi Gradle Java Toolchains cung cấp JDK 17 cho `compileJava` và `test`. Không có mâu thuẫn: đây là các vai trò khác nhau.

## 2. Bảng phân biệt nhanh

| Thành phần | Câu hỏi nó trả lời | Cách chọn phổ biến | Cách kiểm chứng |
| --- | --- | --- | --- |
| Maven JVM | Maven và plugin đang chạy trên Java nào? | `JAVA_HOME`, script `mvn`/`mvnw`, IDE runner | `mvn -version` hoặc `./mvnw -version` |
| Gradle client JVM | Script `gradlew` khởi động bằng Java nào? | `JAVA_HOME`, `java` trên `PATH`, IDE | `./gradlew --version`, xem `Launcher JVM` ở bản Gradle hỗ trợ |
| Gradle daemon JVM | JVM nào thực hiện build script và điều phối task? | Mặc định theo client; `org.gradle.java.home`, IDE, daemon JVM criteria | `./gradlew --version`, xem `Daemon JVM` hoặc cấu hình/log daemon |
| JDK biên dịch | `javac` thực tế thuộc JDK nào? | Maven Toolchains, Maven Compiler Plugin; Gradle Java Toolchains | Log compiler/toolchain, `javaToolchains`, đường dẫn compiler được resolve |
| Release đích | Bytecode, cú pháp Java và API Java SE ở mức nào? | `maven.compiler.release`, `options.release` | Cấu hình build và `javap -verbose` |
| JVM chạy test | Test được chạy bằng Java nào? | Cấu hình Maven Surefire/Failsafe, Gradle `Test.javaLauncher` hoặc toolchain | Log test/task, cấu hình fork/launcher |
| JVM chạy ứng dụng | Khi deploy/`java -jar`, ứng dụng được chạy bằng Java nào? | JRE/JDK trong môi trường deploy, container base image, service runtime | `java -version` ngay tại môi trường chạy, runtime logs |
| Wrapper | Dự án dùng phiên bản công cụ build nào? | `.mvn/wrapper/maven-wrapper.properties`, `gradle/wrapper/gradle-wrapper.properties` | `./mvnw -version`, `./gradlew --version` |

**Quy tắc suy luận:** `mvn -version` và `./gradlew --version` cho biết Java **chạy công cụ build**; chúng không tự chứng minh phiên bản `javac` cuối cùng khi đã cấu hình toolchain. Ngược lại, class file phiên bản 61 chỉ chứng minh **bytecode đích Java 17**, không chứng minh `javac` là JDK 17.

## 3. Vì sao JDK chạy build và JDK biên dịch có thể khác nhau?

```text
Shell / IDE / CI
    |
    +--> JAVA_HOME / PATH / IDE JVM
    |         |
    |         +--> Maven JVM (vd. JDK 21)
    |         |         |
    |         |         +--> Maven Toolchains --> javac của JDK 17
    |         |
    |         +--> Gradle client JVM (vd. JDK 21)
    |                   |
    |                   +--> Gradle daemon JVM (vd. JDK 21)
    |                               |
    |                               +--> Java Toolchains --> javac của JDK 17
    |
    +--> Compiler: --release 17 --> .class major version 61
    |
    +--> JVM tại nơi deploy (vd. JRE 17 hoặc 21) --> chạy ứng dụng
```

Maven là ứng dụng Java. Nếu không cấu hình cơ chế chọn JDK riêng, Maven Compiler Plugin thường dùng compiler gắn với JDK Maven đang chạy. Khi cấu hình **Maven Toolchains**, các plugin *toolchain-aware* có thể lấy công cụ từ một JDK khác. Maven vẫn chạy bằng JVM ban đầu. Maven Toolchains không làm tất cả plugin tự động chạy trên JDK được chọn: plugin cần hỗ trợ toolchain hoặc có cấu hình riêng.

Gradle cũng chạy trên JVM, nhưng Gradle hiện đại dùng **client** để nhận lệnh và **daemon** dài hạn để chạy build. Chúng có thể chạy trên hai Java khác nhau. Các tác vụ Java như `JavaCompile`, `Test`, `Javadoc` có thuộc tính toolchain riêng; khi dùng `java.toolchain` trong Java plugin, chúng thường được cấu hình theo toolchain đó. Các plugin/tác vụ tùy chỉnh chỉ dùng JDK tương ứng nếu chúng hỗ trợ hoặc được nối rõ vào toolchain.

**Tách hai trục cấu hình:**

- `JDK 17 dùng để compile` nói về **bộ công cụ được gọi**.
- `--release 17` nói về **mức tương thích của mã được sinh ra**.

Ví dụ JDK 21 vẫn có thể dùng `javac --release 17` để tạo bytecode Java 17 và kiểm tra việc gọi API Java SE 17. Như vậy “target Java 17” **không suy ra** “compile bằng JDK 17”. Ngược lại, chọn `javac` JDK 17 không tự nói JVM ở production là JDK 17.

## 4. `JAVA_HOME`, `PATH` và phiên bản Java trong IDE

### Terminal

- `JAVA_HOME` thường trỏ tới **thư mục gốc của JDK**, ví dụ một thư mục cài JDK 21; giá trị không phải đường dẫn tới `bin/java`.
- `PATH` quyết định bản `java`/`javac` mà shell tìm được khi gọi trực tiếp. Nếu `JAVA_HOME` và `PATH` trỏ tới hai JDK khác nhau, `java -version` có thể khác `mvn -version`.
- Script Maven/Gradle Wrapper thường ưu tiên `JAVA_HOME` hợp lệ, nếu không thì tìm Java khả dụng theo cơ chế script/hệ điều hành. Cài đặt của IDE có thể ghi đè cách chọn này.
- Nếu dự án dùng toolchain, compiler có thể đến từ một JDK **không xuất hiện đầu tiên trên `PATH`**.

Các lệnh kiểm tra hữu ích:

```bash
java -version
javac -version
mvn -version
./mvnw -version
./gradlew --version
```

Chỉ dùng `./mvnw` khi dự án có Maven Wrapper và `./gradlew` khi dự án có Gradle Wrapper. Trên Windows lần lượt dùng `mvnw.cmd` và `gradlew.bat`. `java -version` có thể in thông tin ra stderr; đó là hành vi bình thường.

Với Linux/macOS có thể xem `echo "$JAVA_HOME"`, `command -v java` và `command -v javac`. Trên PowerShell, dùng `$env:JAVA_HOME`, `Get-Command java` và `Get-Command javac`. Đừng kết luận compiler của **build** chỉ từ các lệnh này nếu dự án có toolchain.

### IDE

Trong IDE thường có ít nhất ba mục độc lập: Project SDK/JDK (phục vụ editor), **Maven Runner JRE/Gradle JVM** (dùng để chạy build) và toolchain được mô tả trong `pom.xml`/`build.gradle`. Biên dịch bằng nút Build của IDE có thể đi qua compiler riêng hoặc được ủy quyền cho Maven/Gradle tùy cấu hình.

Vì vậy khi **terminal build được nhưng IDE fail**, hãy so sánh runner JVM, wrapper đang dùng, cách IDE import cấu hình toolchain và log compile thực tế. Việc editor hiển thị “Project SDK 17” chưa chứng minh Gradle daemon đang chạy Java 17.

## 5. Maven: chạy bằng JDK 21 nhưng compile bằng JDK 17

### 5.1. Nếu không dùng Maven Toolchains

Trong dự án Maven tiêu chuẩn, cấu hình:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

yêu cầu Compiler Plugin tạo bytecode và kiểm tra ngôn ngữ/API tương thích Java 17. Nó **không bắt Maven phải khởi động bằng JDK 17** và **không ép compiler phải là JDK 17**. Nếu Maven chạy bằng JDK 21 và không có compiler/toolchain đặc biệt, compilation có thể dùng `javac` JDK 21 với `--release 17`.

Có thể bật `fork` cùng `executable` để Compiler Plugin dùng một lệnh `javac` riêng. Tuy nhiên cách này chỉ tác động đến plugin đã cấu hình; nếu muốn nhiều plugin (compiler, surefire, javadoc...) chia sẻ lựa chọn JDK, dùng **Maven Toolchains** khi các plugin đó hỗ trợ.

### 5.2. Maven Toolchains hoạt động thế nào?

1. Maven được khởi chạy bằng JDK phù hợp để chạy **Maven và các build plugin**.
2. Maven Toolchains Plugin tìm một JDK đúng yêu cầu, từ JDK đã cài đặt và được phát hiện hoặc qua `~/.m2/toolchains.xml` ở cách cấu hình truyền thống.
3. Plugin compiler có hỗ trợ toolchain lấy compiler từ JDK đã chọn. Các plugin khác có hỗ trợ cũng có thể sử dụng JDK đó.
4. Compiler áp dụng `--release` để giới hạn ngôn ngữ, API và bytecode đích.

Từ Maven Toolchains Plugin 3.2.0 có goal `select-jdk-toolchain` tự phát hiện JDK. Cách bên dưới dùng bản 3.3.0 và yêu cầu phiên bản JDK thuộc khoảng `[17,18)` để chọn Java 17.x, không chọn JDK 18 hay 21.

### 5.3. Ví dụ Maven độc lập

Tạo cấu trúc:

```text
jdk-separation-demo/
├── pom.xml
└── src/main/java/dev/demo/Hello.java
```

**`pom.xml`** — dự án Maven đơn giản, không cần Spring Boot dependency để minh họa việc chọn JDK:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.demo</groupId>
    <artifactId>jdk-separation-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <toolchain.jdk.version>[17,18)</toolchain.jdk.version>
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
                            <goal>select-jdk-toolchain</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/dev/demo/Hello.java`**

```java
package dev.demo;

public record Hello(String text) {
    public static void main(String[] args) {
        System.out.println(new Hello("Hello from Java 17").text());
    }
}
```

`record` là cú pháp Java hiện đại được JDK 17 hỗ trợ. Điều kiện để làm theo ví dụ: máy có Maven tương thích, JDK 21 dùng để chạy Maven, và JDK 17 đã cài và được Maven Toolchains phát hiện. Thiết lập `JAVA_HOME` cho **Maven runner** về JDK 21 theo hệ điều hành trước khi chạy; đường dẫn cài đặt khác nhau trên từng máy.

Chạy:

```bash
mvn -version
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains
mvn clean compile
java -cp target/classes dev.demo.Hello
javap -verbose target/classes/dev/demo/Hello.class
```

Trong cấu hình mong muốn, `mvn -version` cho thấy Maven chạy Java **21**, lệnh discovery liệt kê JDK **17** và log build cho thấy toolchain Java 17 được chọn. Lệnh chạy `Hello` có stdout chính xác:

```text
Hello from Java 17
```

Trong kết quả `javap -verbose`, class `Hello.class` có **`major version: 61`** (Java 17). Đây là bằng chứng của *bytecode đích*, không phải bằng chứng độc lập về JDK đã compile; bằng chứng compiler nằm ở đường dẫn JDK được Maven Toolchains chọn và log của compiler.

Nếu JDK 17 không được auto-discover, cần cài JDK hoặc khai báo vị trí bằng cách Maven Toolchains hỗ trợ. **Không sửa `<toolchain.jdk.version>` thành 21 chỉ để build xanh** nếu yêu cầu bài toán là compile bằng JDK 17; làm vậy sẽ thay đổi điều đang kiểm chứng.

### 5.4. Maven dùng `toolchains.xml` trong dự án cũ

Một số dự án dùng goal `toolchains:toolchain` và tệp người dùng `~/.m2/toolchains.xml`, chứa loại toolchain (`jdk`), thuộc tính phiên bản/vendor và `jdkHome` trỏ tới JDK thực tế. `pom.xml` khai báo yêu cầu, còn mỗi máy map yêu cầu tới đường dẫn JDK của chính mình. Tệp này nằm trong cấu hình Maven của **máy build**, không phải thứ Maven Wrapper mặc nhiên tạo ra. Không cần kết hợp cả cơ chế legacy và auto-discovery mới nếu một cơ chế đã đáp ứng nhu cầu.

Để debug một build cũ, kiểm tra goal toolchains nào đang chạy, tệp `toolchains.xml` nào được dùng, và plugin compiler/test có thật sự hỗ trợ toolchain tương ứng hay không.

## 6. Gradle: daemon JDK và Java Toolchain là hai lớp

### 6.1. Có thể có ba JVM/JDK liên quan

**Gradle client JVM:** tiến trình bắt đầu khi gọi `gradle` hoặc `./gradlew`; lấy Java theo script, môi trường hoặc IDE.

**Gradle daemon JVM:** tiến trình thực thi build. Nếu không cấu hình khác, thường dùng JDK tương ứng với client. Có thể khác qua `org.gradle.java.home`, IDE/Tooling API hoặc **Daemon JVM criteria** (tệp `gradle/gradle-daemon-jvm.properties` ở các phiên bản Gradle hỗ trợ). Khi có Daemon JVM criteria, tiêu chí này có ưu tiên cao hơn `JAVA_HOME` và `org.gradle.java.home`.

**Java compilation toolchain:** JDK mà task `compileJava` dùng. Cấu hình trong `java { toolchain { ... } }` và không nhằm thay đổi Gradle daemon JVM. Đây là điểm phân biệt quan trọng nhất.

Ví dụ:

```text
Gradle client:   Java 21  <- JAVA_HOME
Gradle daemon:   Java 21  <- default hoặc cấu hình daemon
compileJava:     JDK 17   <- java.toolchain
Test:            JDK 17   <- launcher mặc định từ Java toolchain
Artifact:        class file 61 (Java 17)
Production:      Java 17 hoặc Java 21 tương thích
```

Khi Gradle không được chạy bằng một JVM mà **bản Gradle đó hỗ trợ**, build có thể fail trước cả lúc task `compileJava` được tạo. Java Toolchains của dự án **không chữa được lỗi không chạy nổi Gradle**. Tra [bảng tương thích Gradle–Java](https://docs.gradle.org/current/userguide/compatibility.html) theo đúng bản wrapper, vì JDK được hỗ trợ để **chạy Gradle** và để **compile** có thể có mốc khác nhau.

### 6.2. Ví dụ Gradle Groovy DSL độc lập

Tái sử dụng `src/main/java/dev/demo/Hello.java` ở mục 5; thay `pom.xml` bằng hai tệp:

**`settings.gradle`**

```groovy
rootProject.name = 'jdk-separation-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
}

group = 'dev.demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

tasks.register('runHello', JavaExec) {
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'dev.demo.Hello'
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Giải thích:

- `id 'java'`: tạo các task biên dịch, test, JAR cơ bản.
- `java.toolchain.languageVersion = 17`: chọn JDK 17 cho các task Java plugin có hỗ trợ toolchain.
- `options.release = 17`: kiểm soát mức cú pháp/API/bytecode đích; thêm vào để ý định tương thích Java 17 được tường minh.
- `runHello`: tự tạo `JavaExec` dùng launcher JDK 17, vì JVM chạy app có thể được chọn độc lập với JVM build.

Với dự án đã có **Gradle Wrapper** hỗ trợ chạy bằng JDK 21, và JDK 17 khả dụng:

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean compileJava runHello
javap -verbose build/classes/java/main/dev/demo/Hello.class
```

Dòng ứng dụng in ra khi task `runHello` thực thi là:

```text
Hello from Java 17
```

Output đầy đủ của Gradle còn chứa thông tin task/build và phụ thuộc phiên bản. `javap` phải thấy `major version: 61`. Lệnh `./gradlew -q javaToolchains` liệt kê JDK Gradle phát hiện và chi tiết phiên bản/vị trí; trong Gradle mới, `--version` còn cho biết launcher/daemon JVM. Kiểm tra task `compileJava` với `--info` khi cần xác nhận compiler đang được dùng.

Nếu máy không có JDK 17 và không cấu hình kho cấp phát toolchain, Gradle có thể báo “No matching toolchains found”. Toolchain **không mặc nhiên tải JDK trong mọi project**; tự tải cần repository resolver được cấu hình phù hợp. Không hạ hoặc nâng `languageVersion` tùy tiện để che lỗi thiếu JDK.

### 6.3. Lựa chọn Java cho task riêng

Java Toolchain cấp project giúp các task `JavaCompile`, `Test`, `Javadoc` tiêu chuẩn dùng cùng phiên bản theo quy ước Gradle. Tuy nhiên có thể cố ý chạy test trên JDK 21 trong khi compile bằng JDK 17 bằng cách chỉnh `Test.javaLauncher`:

```groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Đây là **đoạn bổ sung**, không phải build script độc lập. Kết quả là `compileJava` dùng JDK 17, trong khi task test được cấu hình dùng JDK 21. Tình huống này hữu ích khi kiểm tra khả năng chạy ứng dụng biên dịch Java 17 trên môi trường runtime cao hơn. Đừng coi **JDK chạy test** là **JDK compile**.

## 7. Maven/Gradle Wrapper làm gì và không làm gì?

`mvnw`/`mvnw.cmd` cùng thư mục `.mvn/wrapper/` giúp sử dụng bản **Maven** mà dự án quy định, kể cả tải phân phối Maven nếu cần. `gradlew`/`gradlew.bat` cùng `gradle/wrapper/gradle-wrapper.properties` giúp sử dụng bản **Gradle** quy định. Vì thế dùng wrapper giúp giảm tình trạng máy A chạy Maven/Gradle phiên bản khác máy B.

Nhưng bản Maven/Gradle và bản JDK là **hai quyết định khác nhau**. Wrapper thông thường không tự đặt `java.toolchain` hoặc tự chọn `maven.compiler.release`. Muốn build nhất quán cần cả ba: **phiên bản công cụ build**, **JDK chạy công cụ build** đáp ứng tương thích và **JDK/release biên dịch** được khai báo rõ. Gradle Daemon JVM criteria là cơ chế bổ sung để chuẩn hóa JVM chạy daemon, khác với Gradle Wrapper và khác với Java compilation toolchain.

Ví dụ trên CI:

```text
CI cung cấp JDK 21  -->  chạy ./mvnw hoặc ./gradlew
Project pin Maven/Gradle version bằng Wrapper
Project chọn JDK 17 cho compiler bằng Toolchains
Compiler tạo class file major 61 cho Java 17
CI chạy test bằng JDK đã cấu hình
Release chạy trên Java 17+ nếu mọi dependency/API tương thích
```

Không dùng kết quả `java -version` tại máy developer để thay bằng chứng tương tự ở **CI hoặc container**. `JAVA_HOME`, đường dẫn JDK, daemon và các môi trường có thể khác.

## 8. Trong Spring Boot cần xem thêm điều gì?

Với Spring Boot, phải tính cả **yêu cầu Java để chạy build tool và plugin**. Ví dụ một phiên bản Spring Boot plugin có thể yêu cầu Java 17 trở lên để chính plugin hoạt động. Khi Maven/Gradle đang chạy trên Java thấp hơn mức plugin cần, cấu hình compiler toolchain lên Java 17 **không giải quyết được lỗi nạp plugin ngay từ đầu**.

Ngược lại, nếu Spring Boot plugin chạy được trên Java 21, vẫn có thể chọn toolchain JDK 17 để biên dịch ứng dụng nhắm tới Java 17, với điều kiện phiên bản Spring Boot/dependency cũng hỗ trợ Java 17. Đừng suy ra mọi dòng Spring Boot có cùng Java minimum; kiểm tra [Spring Boot System Requirements](https://docs.spring.io/spring-boot/system-requirements.html) ứng với **phiên bản đang dùng**.

Đóng gói Spring Boot qua `spring-boot-maven-plugin:repackage` hoặc Gradle `bootJar` chủ yếu tạo executable archive. Việc file JAR có Boot loader và dependency runtime **không làm thay đổi** yêu cầu Java của class đã biên dịch hay runtime Spring Boot. `java -jar` thực tế dùng JVM của nơi triển khai, không phải “JDK compile” được nhúng trong JAR.

Chú ý thêm các plugin khác như Kotlin, annotation processor, bytecode enhancement, code generation và plugin kiểm thử: có plugin chạy trong JVM build, plugin spawn tiến trình riêng và plugin dùng toolchain. Nếu build lệch JDK, phải xem **từng plugin/task**, không áp đặt cơ chế JavaCompile cho mọi tác vụ.

## 9. Phân biệt `source`, `target`, `release` và toolchain

| Tùy chọn | Thực chất kiểm soát | Điều nó không bảo đảm |
| --- | --- | --- |
| `maven.compiler.source` hoặc `-source` | Cú pháp Java được phép | Không chỉ ra JDK nào chạy compiler; không đảm bảo API Java cũ |
| `maven.compiler.target` hoặc `-target` | Phiên bản bytecode đích | Không chặn tự động việc gọi API mới nếu vẫn compile trên JDK mới |
| `maven.compiler.release` hoặc `javac --release` | Cú pháp, bytecode và public API của Java SE release đích | Không ép trình biên dịch phải đến từ cùng major JDK |
| Gradle `options.release` | Tham số `--release` cho `JavaCompile` | Không thay đổi JVM chạy Gradle daemon |
| Gradle `sourceCompatibility`/`targetCompatibility` | Mức source/bytecode theo cơ chế cũ | Không đảm bảo giới hạn public API giống `--release` |
| Maven Toolchains / Gradle Java Toolchains | Chọn **JDK thực tế** cung cấp công cụ Java | Không tự chọn môi trường JVM của server production |

**Ví dụ bẫy API:** code gọi API chỉ có từ Java 21 nhưng cấu hình `source=17`, `target=17` và chạy `javac` JDK 21 có thể compile thành class Java 17 rồi lỗi khi chạy trên Java 17. Cấu hình `--release 17` kiểm tra API Java SE mục tiêu và thường phát hiện ngay ở lúc compile. Dù vậy, `--release` không thay thế việc kiểm tra tương thích các thư viện bên thứ ba, cấu hình JNI, native image và những phụ thuộc runtime khác.

Cách đọc class file: `javap -verbose ...` in `major version`. Một số mốc phổ biến: **Java 8 = 52**, **Java 11 = 55**, **Java 17 = 61**, **Java 21 = 65**. Nếu chạy class major 65 bằng Java 17 (chỉ hiểu đến major 61), có thể gặp `UnsupportedClassVersionError`. Nếu class major 61 chạy trên Java 21 nhưng vẫn lỗi, nguyên nhân có thể nằm ở API, dependency, plugin/runtime chứ không nhất thiết ở class version.

## 10. Chẩn đoán có thứ tự

Khi gặp lỗi “Java version” trong dự án, làm theo chuỗi sau để tránh thay nhầm cấu hình:

1. **Tìm lớp lỗi:** lỗi xuất hiện trước build script, trong plugin, tại `compileJava`/`maven-compiler-plugin`, lúc test, hay khi `java -jar`?
2. **Kiểm tra wrapper:** chạy `./mvnw -version` hoặc `./gradlew --version`; ghi bản Maven/Gradle và Java đang chạy công cụ. Nếu không có wrapper, kiểm tra bản cài toàn cục.
3. **Kiểm tra JVM điều phối Gradle:** xem Launcher JVM và Daemon JVM, `org.gradle.java.home` hoặc daemon JVM criteria; IDE có thể dùng JVM khác terminal.
4. **Kiểm tra compiler JDK:** Maven xem `mvn ...:display-discovered-jdk-toolchains`, log `mvn -X compile` và plugin toolchain; Gradle xem `./gradlew -q javaToolchains` và `./gradlew compileJava --info`.
5. **Kiểm tra release đích:** tìm `maven.compiler.release`, `options.release` và config source/target; dùng `javap -verbose` để xác nhận bytecode sau build.
6. **Kiểm tra JVM test và production:** xem `Test.javaLauncher`, Surefire/Failsafe, Dockerfile/base image, môi trường deploy thực sự. Không xem kết quả `java -version` trên laptop như bằng chứng JVM của container.
7. **Sửa đúng lớp cấu hình:** lỗi chạy plugin thì đổi JDK chạy build hoặc phiên bản plugin; lỗi không tìm thấy JDK 17 thì cài/cấu hình toolchain; lỗi API Java 21 khi target 17 thì sửa mã/đổi release theo yêu cầu sản phẩm; lỗi runtime thì xác minh JRE/JDK deploy và dependency.

### Triệu chứng nhanh

| Triệu chứng | Nguyên nhân đáng kiểm tra | Hành động phù hợp |
| --- | --- | --- |
| `mvn -version` hiển thị Java 21 nhưng cần artifact Java 17 | Chưa chắc có lỗi; Maven JVM khác compiler/release | Kiểm tra toolchain và `maven.compiler.release=17` |
| `./gradlew --version` hiển thị daemon Java 21 nhưng `compileJava` cần JDK 17 | Daemon JVM và compilation toolchain khác nhau | Đặt `java.toolchain=17`, kiểm tra `javaToolchains` |
| `No matching toolchains found` | Không có JDK phù hợp hoặc provisioning chưa cấu hình | Cài JDK, cấu hình đường dẫn/auto-provisioning |
| `invalid target release: 21` hoặc `release version 21 not supported` | Compiler thực tế quá cũ so với release yêu cầu | Chọn JDK compiler đủ mới, kiểm tra plugin/toolchain |
| `UnsupportedClassVersionError` khi chạy app | Runtime JVM thấp hơn phiên bản class file được sinh ra | Dùng runtime đủ mới hoặc build lại với release tương thích |
| IDE lỗi nhưng terminal build tốt | IDE runner JDK, Gradle daemon hoặc wrapper khác | Đồng bộ đường dẫn JDK và phiên bản công cụ; kiểm tra task thực |
| Đã đặt `source=17,target=17` nhưng lỗi `NoSuchMethodError` trên Java 17 | Có thể dùng API Java mới từ lúc compile hoặc dependency runtime không khớp | Dùng `--release 17`, kiểm tra resolved dependencies và runtime |
| Plugin Boot fail trước bước compile | JVM chạy build không thỏa yêu cầu plugin | Đổi JVM chạy Maven/Gradle phù hợp, không chỉ sửa toolchain |

## 11. Bài tập tự kiểm tra

**Bài 1.** `mvn -version` báo Java 21; POM có `maven.compiler.release=17`. Chắc chắn `javac` là JDK 17 không? **Không.** Nếu không có toolchain riêng, compiler có thể từ JDK 21 với `--release 17`.

**Bài 2.** Gradle daemon chạy Java 21, nhưng `java.toolchain.languageVersion=17`. `compileJava` sẽ dùng JDK nào? **JDK 17**, nếu toolchain được tìm thấy, và task đang dùng toolchain tiêu chuẩn.

**Bài 3.** `javap` báo `major version: 61`. Có chứng minh Maven/Gradle chạy trên Java 17 không? **Không.** Nó chỉ chứng minh class file nhắm tới Java 17.

**Bài 4.** Chuyển `JAVA_HOME` từ 17 sang 21 có tự động chuyển compiler Java project đã cấu hình toolchain17 sang JDK21 không? **Không.** Compiler vẫn tuân theo toolchain nếu cấu hình hoạt động; JVM chạy build có thể đổi.

**Bài 5.** Maven Wrapper dùng bản Maven đúng chuẩn nhưng plugin chạy Java báo `UnsupportedClassVersionError` ngay lúc Maven load plugin. Sửa `maven.compiler.release` có giúp không? **Không.** Cần kiểm tra JVM chạy Maven và yêu cầu Java của plugin.

**Bài 6.** Spring Boot JAR được đóng gói bằng Gradle daemon JDK 21 nhưng class major 61. Production phải chạy JDK21 vì daemon dùng 21? **Không.** Runtime cần đáp ứng mức Java của ứng dụng, Spring Boot và dependency; bản daemon không quyết định trực tiếp mức runtime.

## 12. Checklist áp dụng cho dự án thực tế

- [ ] Project dùng wrapper để chuẩn hóa bản Maven/Gradle.
- [ ] JDK chạy Maven/Gradle đáp ứng yêu cầu chính xác của build tool và build plugin.
- [ ] Compiler JDK được chọn có chủ đích bằng toolchain, nhất là khi có nhiều JDK trên máy/CI.
- [ ] Release đích được khai báo bằng `--release` khi yêu cầu tương thích Java.
- [ ] IDE, terminal, CI và container có cách xác minh phiên bản thực sự.
- [ ] Test JVM được định rõ nếu có ma trận phiên bản runtime.
- [ ] Artifact được kiểm tra class major và chạy thử trên môi trường runtime đích.
- [ ] Không gộp `JAVA_HOME`, phiên bản wrapper, compiler JDK và runtime JDK thành một khái niệm.

**Ghi nhớ:** **JDK chạy build ≠ JDK compiler ≠ Java release đích ≠ JVM chạy ứng dụng.** Maven Toolchains và Gradle Java Toolchains giúp chọn JDK compile độc lập; `--release` kiểm soát tương thích mã; wrapper kiểm soát phiên bản build tool.

## 13. Tài liệu chính thức

- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains)
- [Maven Toolchains Plugin — JDK Discovery](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk-discovery.html)
- [Maven Compiler Plugin — Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html)
- [Apache Maven Wrapper](https://maven.apache.org/tools/mavenwrapper.html)
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle — Daemon JVM](https://docs.gradle.org/current/userguide/gradle_daemon.html)
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html)
- [Gradle — Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
