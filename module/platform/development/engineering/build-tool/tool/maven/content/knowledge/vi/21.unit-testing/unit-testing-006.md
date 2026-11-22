# Truyền system properties, biến môi trường và tham số JVM kiểm thử trong Maven

## 1. Vì sao cần phân biệt ba kênh cấu hình?

Trong unit testing Java, test có thể cần biết chế độ chạy, địa chỉ mock service, tên môi trường, cấu hình encoding hoặc giới hạn heap. Các giá trị này không đi qua một kênh duy nhất. Ba câu hỏi dưới đây có ba cách giải quyết khác nhau:

- Test gọi `System.getProperty("lab.mode")`: truyền **Java system property**.
- Test gọi `System.getenv("LAB_STAGE")`: truyền **OS environment variable**.
- Test cần `-Xmx256m`, `--add-opens` hay `-javaagent`: truyền **JVM startup arguments**.

Với **Maven Surefire Plugin**, ba tham số thường dùng lần lượt là `systemPropertyVariables`, `environmentVariables` và `argLine`. Với **Maven Failsafe Plugin**, cũng có các tham số tương tự cho integration tests, nhưng cấu hình chỉ đặt ở Surefire không tự áp dụng cho Failsafe.

Điểm dễ nhầm nhất: Maven có thể chạy trong **một JVM riêng**, còn Surefire có thể **fork một JVM mới để chạy tests**. Giá trị được gán vào Maven process không nhất thiết trở thành environment hoặc startup argument của JVM đang chạy JUnit.

Bài này hướng dẫn:

1. Phân biệt Maven properties, system properties, environment variables và VM options.
2. Hiểu Maven CLI `-D` khi Surefire chuyển user properties sang test process.
3. Dùng `systemPropertyVariables` và `systemPropertiesFile`, hiểu thứ tự ưu tiên.
4. Dùng environment từ terminal/CI hoặc khai `environmentVariables` cho fork.
5. Dùng `argLine` cho heap, module flags, agent và startup properties.
6. Hiểu `forkCount`, `reuseForks`, `MAVEN_OPTS` và late evaluation của JaCoCo.
7. Chạy project **Java 17 + JUnit 5** có POM hoàn chỉnh, test assertions và stdout kiểm chứng.
8. Chẩn đoán lỗi môi trường CI/IDE, test fork crash, trùng key hoặc secrets bị đưa vào log.

## 2. Sơ đồ luồng cấu hình

~~~text
Shell / CI environment
   |
   +-- LAB_STAGE=from-shell                       [OS env]
   |
   v
Maven process (JVM A)
   +-- pom.xml properties                        [Maven model]
   +-- CLI: mvn -Dlab.mode=ci test                [Maven user property]
   +-- MAVEN_OPTS                                 [Maven JVM options]
   |
   +-- Maven Surefire Plugin
          +-- systemPropertyVariables            [Java system props]
          +-- systemPropertiesFile                 [Java system props]
          +-- environmentVariables                [OS env của fork]
          +-- argLine                             [Startup args]
          |
          v
      Forked test JVM (JVM B), forkCount > 0
          +-- System.getProperty("lab.mode")
          +-- System.getenv("LAB_STAGE")
          +-- -Xmx, --add-opens, -javaagent
          +-- JUnit tests
~~~

Cấu hình build/test có thể bao gồm nhiều lớp:

| Nguồn | Ví dụ | Đến đâu? |
| --- | --- | --- |
| Maven project property | `<properties><lab.mode>local</lab.mode>` | Maven model và interpolation; không tự thành Java property |
| Maven session user property | `mvn -Dlab.mode=ci test` | Maven và có thể được Surefire promoted sang test provider/JVM |
| Surefire `systemPropertyVariables` | `<lab.mode>local</lab.mode>` | `System.getProperty("lab.mode")` |
| OS environment | `LAB_STAGE=ci` | `System.getenv("LAB_STAGE")` nếu process nhận được |
| Surefire `environmentVariables` | `<LAB_STAGE>injected</LAB_STAGE>` | Forked test process environment |
| Surefire `argLine` | `-Xmx256m -Dlab.jvm.marker=fork` | JVM command line của fork |

**Không có chuyển đổi mặc định từ system property sang environment variable.** Hai đoạn sau có thể trả về hai giá trị khác nhau:

~~~java
String p = System.getProperty("LAB_STAGE");
String e = System.getenv("LAB_STAGE");
~~~

Lời gọi `System.setProperty("LAB_STAGE", "x")` cũng không sửa `System.getenv("LAB_STAGE")`. Test cần gọi đúng API tương ứng với kênh được truyền.

## 3. Surefire chạy ở đâu trong Maven lifecycle?

Đối với project `jar` thông thường:

~~~text
validate
  |
process-resources
  |
compile                  compiler:compile
  |
process-test-resources
  |
test-compile             compiler:testCompile
  |
test                     surefire:test
  |                       |
  |                       +-- tìm các lớp JUnit
  |                       +-- dựng test classpath
  |                       +-- khởi động fork JVM nếu cấu hình
  |                       +-- chạy test và sinh reports
package
  |
verify
~~~

`mvn test` chạy default lifecycle đến phase `test`, trong đó thường có `surefire:test`. `mvn clean verify` còn đóng gói và chạy tới `verify`. Trong khi đó, gọi trực tiếp goal:

~~~bash
mvn org.apache.maven.plugins:maven-surefire-plugin:3.5.4:test
~~~

không bắt buộc Maven phải đi qua toàn bộ các phase compile/resource từ đầu. Với project chưa compile, nên ưu tiên `mvn test` hoặc `mvn clean verify`.

Các class tên `TestConfig.java`, `ConfigTest.java`, `ConfigTests.java` thường được Surefire phát hiện theo convention; `PaymentIT.java` thường dành cho Failsafe nếu được cấu hình. Bài lab dùng tên `ConfigPrinterTest.java` để tránh nhầm với integration test.

## 4. Java system properties bằng systemPropertyVariables

Đây là một POM fragment:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.4</version>
            <configuration>
                <systemPropertyVariables>
                    <lab.mode>local</lab.mode>
                    <feature.demo.enabled>true</feature.demo.enabled>
                    <service.mock.url>http://127.0.0.1:18080</service.mock.url>
                </systemPropertyVariables>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Khi Surefire chạy tests với cấu hình này, Java có thể đọc:

~~~java
String mode = System.getProperty("lab.mode");
boolean enabled = Boolean.parseBoolean(
        System.getProperty("feature.demo.enabled", "false"));
String url = System.getProperty("service.mock.url");
~~~

Key và value của `systemPropertyVariables` là map mà Surefire truyền cho test provider/JVM. Đừng nhầm nó với:

~~~xml
<properties>
    <lab.mode>local</lab.mode>
</properties>
~~~

Phần `<properties>` phía trên cung cấp **Maven model property** để plugin nội suy. Nó **không tự cam kết** `System.getProperty("lab.mode")` của một Java process bất kỳ sẽ bằng `local`.

Nếu muốn dùng Maven property làm nguồn giá trị, hãy nối tường minh:

~~~xml
<properties>
    <lab.default.mode>local</lab.default.mode>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.4</version>
            <configuration>
                <systemPropertyVariables>
                    <lab.mode>${lab.default.mode}</lab.mode>
                </systemPropertyVariables>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Trong ví dụ này, Maven nội suy `${lab.default.mode}` thành giá trị cho plugin. Tài liệu Surefire cũng lưu ý biểu thức có kết quả kiểu đối tượng không phải `String` (ví dụ một số expression kiểu `File`) có thể bị truyền nguyên văn thay vì chuyển thành string path như bạn tưởng. Với path quan trọng, hãy xác minh giá trị thật trong test.

### 4.1. systemPropertiesFile

Khi nhiều keys cần được nạp từ tệp, Surefire hỗ trợ `systemPropertiesFile`:

~~~xml
<configuration>
    <systemPropertiesFile>
        ${project.basedir}/src/test/config/test-system.properties
    </systemPropertiesFile>
</configuration>
~~~

File được tham chiếu cần tồn tại, ví dụ:

~~~properties
lab.mode=from-file
feature.demo.enabled=true
service.mock.url=http://127.0.0.1:18080
~~~

Đây là **fragment tùy chọn**, không nằm trong POM lab chính phía dưới. File này dùng để cung cấp Java system properties, **không tự tạo environment variables**. Không cất secrets thật vào file properties được commit lên Git hay được đưa vào build artifacts.

### 4.2. systemProperties cũ đã deprecated

Cách cũ:

~~~xml
<systemProperties>
    <property>
        <name>lab.mode</name>
        <value>local</value>
    </property>
</systemProperties>
~~~

đã bị Surefire đánh dấu **deprecated**. Với POM mới, dùng `systemPropertyVariables` hoặc `systemPropertiesFile` khi thích hợp.

## 5. Maven CLI -D và thứ tự ưu tiên

Lệnh:

~~~bash
mvn -B -ntp test -Dlab.mode=ci
~~~

đặt **Maven session user property** `lab.mode=ci`. Trong Surefire **3.5.4**, `promoteUserPropertiesToSystemProperties` mặc định **true**; nó chuyển các user properties, thường do Maven CLI `-D` cung cấp, thành effective system properties cho test provider. Nếu cùng key đã tồn tại trong `systemPropertyVariables`, giá trị từ CLI có ưu tiên cao hơn.

Ví dụ Surefire 3.5.4 có nhiều nguồn trùng `lab.mode`:

| Nguồn | Giá trị |
| --- | --- |
| `argLine` chứa `-Dlab.mode=from-argline` | `from-argline` |
| `systemPropertiesFile` | `from-file` |
| `systemPropertyVariables` | `local` |
| Maven CLI `-Dlab.mode=ci` | `ci` |

Với promotion bật, **giá trị effective thông thường là `ci`**.

Thứ tự ghép effective system properties được tài liệu Surefire 3.5.4 mô tả từ thấp đến cao:

1. `-D` trong `argLine` của forked JVM.
2. `systemProperties` cũ.
3. `systemPropertiesFile`.
4. `systemPropertyVariables`.
5. Maven session user properties nếu `promoteUserPropertiesToSystemProperties=true`.

Nguồn sau có thể ghi đè key cùng tên của nguồn trước. Tuy nhiên, **những thuộc tính được JVM chốt từ lúc startup** (ví dụ `file.encoding`, `java.library.path` và một số biến nội bộ) cần xem riêng; thay chúng ở provider sau startup có thể không đổi được hành vi runtime tương ứng.

### 5.1. Tắt promotion

Bạn có thể cấu hình:

~~~xml
<promoteUserPropertiesToSystemProperties>false</promoteUserPropertiesToSystemProperties>
~~~

Đây là thiết lập có từ Surefire 3.4.0. Khi tắt, Maven CLI `-Dlab.mode=ci` không tự được promoted theo cơ chế trên; giá trị `lab.mode` khai rõ trong `systemPropertyVariables` vẫn có thể là `local`. Nhưng điều này **không có nghĩa mọi user property đều biến mất khỏi mọi cơ chế cấu hình Maven**: plugin parameters, interpolation và các mục khác có thể vẫn đọc CLI properties.

**Không khái quát hành vi Surefire 3.5.4 cho mọi plugin version cũ.** Hãy pin phiên bản, đọc plugin goal documentation tương ứng và kiểm tra test runtime.

### 5.2. Maven -D khác Java -D

So sánh:

~~~bash
mvn -Dlab.mode=ci test
java -Dlab.mode=ci -cp target/classes dev.example.config.ConfigPrinter
~~~

Lệnh thứ nhất cấp Maven user property, Surefire có thể promoted nó sang test JVM. Lệnh thứ hai cấp một **Java system property ngay tại startup của ứng dụng Java**. Cú pháp cùng dạng `-Dname=value` nhưng **tiến trình nhận khác nhau**.

Không dùng Maven `-Dfile.encoding=UTF-8` để bảo đảm hành vi giống `java -Dfile.encoding=UTF-8` trong một test fork. Một số startup properties phải được đặt ở JVM command line qua `argLine`.

## 6. Environment variables từ shell và CI

Một OS environment variable được tiến trình con kế thừa từ môi trường cha, trừ khi bị loại/ghi đè. Java đọc bằng:

~~~java
String stage = System.getenv("LAB_STAGE");
~~~

Trên Linux/macOS:

~~~bash
LAB_STAGE=from-shell mvn -B -ntp test
~~~

Hoặc dùng environment tồn tại cho cả shell session:

~~~bash
export LAB_STAGE=from-shell
mvn -B -ntp test
~~~

Trên Windows PowerShell:

~~~powershell
$env:LAB_STAGE = 'from-shell'
mvn -B -ntp test
Remove-Item Env:LAB_STAGE
~~~

Trên Windows Command Prompt:

~~~bat
set LAB_STAGE=from-shell
mvn -B -ntp test
~~~

Đây là thao tác trên **OS environment**, không tạo Java system property. `System.getProperty("LAB_STAGE")` vẫn có thể trả `null`.

### 6.1. environmentVariables của Surefire

Surefire có thể bổ sung hoặc ghi đè các biến trên **forked test JVM**:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.4</version>
    <configuration>
        <environmentVariables>
            <LAB_STAGE>injected-stage</LAB_STAGE>
            <LAB_FEATURE_FLAG>enabled</LAB_FEATURE_FLAG>
        </environmentVariables>
    </configuration>
</plugin>
~~~

Nếu Maven process kế thừa `LAB_STAGE=from-shell` nhưng POM này định nghĩa `LAB_STAGE=injected-stage`, forked test JVM thường thấy **`injected-stage`** ở `System.getenv` do entry của plugin ghi đè key tương ứng.

Điều đó **không thay đổi** environment variable ở terminal, Maven parent process hoặc một Java application process khác. Đây chỉ là environment cấp cho child fork khi Surefire khởi chạy nó.

### 6.2. excludedEnvironmentVariables

Có thể loại chọn lọc một số biến khỏi fork:

~~~xml
<configuration>
    <excludedEnvironmentVariables>
        UNWANTED_VARIABLE,UNSAFE_SAMPLE_FLAG
    </excludedEnvironmentVariables>
</configuration>
~~~

Hoặc dùng Maven user property:

~~~bash
mvn -B -ntp test -Dsurefire.excludedEnvironmentVariables=UNWANTED_VARIABLE,UNSAFE_SAMPLE_FLAG
~~~

Tên key được Surefire so khớp đúng literal, có chú ý tới **chữ hoa/chữ thường**. Không loại những biến cần thiết như `PATH` hoặc `JAVA_HOME` nếu chưa hiểu tác động tới test/child processes.

`excludedEnvironmentVariables` chỉ là biện pháp giới hạn môi trường cho process kiểm thử, **không xóa secrets khỏi CI logs, Maven process hay server**.

### 6.3. env.* trong Maven POM

Maven có cú pháp nội suy từ environment, chẳng hạn `${env.HOME}` hoặc `${env.CI}`, ở nơi POM hỗ trợ interpolation. Ví dụ:

~~~xml
<systemPropertyVariables>
    <lab.ci.flag>${env.CI}</lab.ci.flag>
</systemPropertyVariables>
~~~

Nếu `CI` được định nghĩa thì giá trị có thể được lấy từ OS environment rồi truyền như Java system property `lab.ci.flag` cho test. **Nội suy không phải thao tác sửa môi trường.** Với biến không tồn tại, kiểm tra giá trị thực thay vì giả định sẽ có default theo ý muốn.

## 7. argLine: JVM startup arguments của fork

`argLine` truyền cờ **khi Surefire khởi động test JVM mới**:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.4</version>
    <configuration>
        <forkCount>1</forkCount>
        <argLine>-Xms64m -Xmx256m -Dlab.jvm.marker=fork-start</argLine>
    </configuration>
</plugin>
~~~

Các mục đích hay gặp:

| Cờ | Ý nghĩa |
| --- | --- |
| `-Xms64m` | Initial heap size |
| `-Xmx256m` | Maximum heap size |
| `-Dlab.jvm.marker=fork-start` | System property khởi tạo khi test JVM start |
| `-Dfile.encoding=UTF-8` | Thuộc tính startup ảnh hưởng encoding theo JDK/platform |
| `--add-opens java.base/java.lang=ALL-UNNAMED` | Mở package cho reflection nếu thật sự cần |
| `-javaagent:/path/to/agent.jar` | Nạp instrumentation/coverage agent |
| `-XX:+HeapDumpOnOutOfMemoryError` | Thu thập dữ liệu khi JVM OOM |

`argLine` **không phải** `program arguments` đưa vào `main(String[] args)` của ứng dụng. JUnit được chạy bởi test provider, không mặc định nhận `String[] args` như một Java main thông thường.

### 7.1. forkCount=0 thay đổi tất cả

Surefire có:

~~~xml
<forkCount>1</forkCount>
<reuseForks>true</reuseForks>
~~~

`forkCount=1` cho phép một test JVM process được fork tại một thời điểm; `reuseForks=true` có thể tái dùng fork cho nhiều test classes. Nếu `forkCount=0`, tests chạy trong JVM của Maven (không fork JVM mới bằng Surefire theo chế độ đó). Khi đó `argLine` **không thể sửa startup flags của JVM Maven đã khởi động**, và cấu hình `environmentVariables` không còn child environment mới để áp theo nghĩa thông thường.

Vì thế nếu lab cần test JVM có `-Xmx256m` hoặc `LAB_STAGE` do Surefire cấp, **dùng forkCount > 0**.

### 7.2. reuseForks và state leak

Nếu test A gọi:

~~~java
System.setProperty("lab.mode", "changed-by-test");
~~~

mà không restore giá trị, test B trong cùng fork có thể đọc giá trị đó khi `reuseForks=true`, làm test phụ thuộc thứ tự. Hãy tránh global mutable state, hoặc restore bằng `try/finally`/test extension. `System.setProperty` **không sửa** `System.getenv`.

Nếu có nhiều forks song song, `${surefire.forkNumber}` có thể được Surefire thay ở một số tham số như `argLine`, `environmentVariables` hoặc system properties, theo phiên bản hỗ trợ. Fork number **không phải ID duy nhất của từng test method**, vì nhiều tests có thể dùng cùng fork.

## 8. MAVEN_OPTS không phải Surefire argLine

Nếu terminal có:

~~~bash
export MAVEN_OPTS="-Xmx1g"
mvn -B -ntp test
~~~

biến `MAVEN_OPTS` thường cấu hình **JVM chạy Maven**, không đảm bảo test fork có `-Xmx1g`. Muốn đảm bảo heap test fork, cấu hình `-Xmx...` trong Surefire `argLine` và kiểm chứng input arguments của test JVM.

Một số biến toàn cục như `JAVA_TOOL_OPTIONS` hoặc `JDK_JAVA_OPTIONS` có thể được Java launcher/JVM xử lý cho **nhiều Java processes** trong environment, gồm cả Maven và fork, tùy Java version và cách khởi động. Chúng không thích hợp nếu bạn chỉ muốn thay tham số của **một** test suite. Tác động chéo khó debug, nhất là khi agent hoặc debugger được bật ngoài ý muốn.

Nếu Maven dùng Toolchains hoặc Surefire cấu hình Java executable riêng, JDK thực tế của test fork cũng có thể khác với `java` trong terminal. Kiểm tra `mvn -version` và cấu hình fork/toolchain trước khi kết luận một `--add-opens`, `-XX` hay module option có tương thích hay không.

## 9. Lab thực hành Java 17 + JUnit 5 đầy đủ

Lab có ba nguồn giá trị **khác nhau** trong cùng một test:

- Java system property `lab.mode=local` từ `systemPropertyVariables`.
- OS environment variable `LAB_STAGE=injected-stage` từ `environmentVariables`.
- JVM marker `lab.jvm.marker=fork-start` và `-Xmx256m` từ `argLine`.

Sau đó ta chạy Maven CLI `-Dlab.mode=ci` để chứng minh cơ chế promotion/precedence, và chạy Java main trực tiếp để thấy Surefire config không tự áp cho process ngoài Maven.

### 9.1. Điều kiện và cấu trúc

Yêu cầu: **JDK 17+**, **Maven 3.9.x**, kết nối Maven Central hoặc mirror phù hợp ở lần tải plugin/dependency đầu. Không cần database, Docker, Spring Boot hay dịch vụ bên ngoài.

~~~text
test-jvm-config-lab/
├── pom.xml
└── src/
    ├── main/
    │   └── java/dev/example/config/ConfigPrinter.java
    └── test/
        └── java/dev/example/config/ConfigPrinterTest.java
~~~

### 9.2. POM đầy đủ

Tạo `test-jvm-config-lab/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>test-jvm-config-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
                <configuration>
                    <forkCount>1</forkCount>
                    <reuseForks>true</reuseForks>
                    <promoteUserPropertiesToSystemProperties>true</promoteUserPropertiesToSystemProperties>

                    <systemPropertyVariables>
                        <lab.mode>local</lab.mode>
                    </systemPropertyVariables>

                    <environmentVariables>
                        <LAB_STAGE>injected-stage</LAB_STAGE>
                    </environmentVariables>

                    <argLine>-Xmx256m -Dlab.jvm.marker=fork-start</argLine>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Vì sao cấu hình này đáng tin:

- `forkCount=1` bảo đảm có fork JVM mới cho test.
- `promoteUserPropertiesToSystemProperties=true` được khai rõ theo Surefire 3.5.4, tránh phụ thuộc vào cấu hình mặc định của project khác.
- `lab.mode` nằm dưới `systemPropertyVariables`, còn `lab.jvm.marker` ở `argLine`; chúng có nguồn khác nhau một cách có chủ đích.
- `LAB_STAGE` ở `environmentVariables` chỉ điều khiển fork environment, **không thay đổi terminal environment**.
- POM không có JaCoCo hoặc systemPropertiesFile gây override bất ngờ.
- Surefire 3.5.4 và JUnit Jupiter 5.11.4 phù hợp với JDK 17 của lab.
- Compiler và JAR plugin versions được pin để giảm khác biệt giữa máy phát triển và CI.

### 9.3. Java main class

Tạo `src/main/java/dev/example/config/ConfigPrinter.java`:

~~~java
package dev.example.config;

public final class ConfigPrinter {
    private ConfigPrinter() {
    }

    public static String snapshot() {
        String mode = System.getProperty("lab.mode", "<unset>");
        String stage = System.getenv()
                .getOrDefault("LAB_STAGE", "<unset>");
        String marker = System.getProperty(
                "lab.jvm.marker", "<unset>");

        return "mode=" + mode
                + "|env=" + stage
                + "|jvm=" + marker;
    }

    public static void main(String[] args) {
        System.out.println("CONFIG: " + snapshot());
    }
}
~~~

Đoạn Java 17 này không có dependency ngoài JDK. `System.getProperty` đọc Java system properties, `System.getenv` đọc OS environment; chúng không đọc trực tiếp `pom.xml`.

### 9.4. Unit test dùng JUnit 5

Tạo `src/test/java/dev/example/config/ConfigPrinterTest.java`:

~~~java
package dev.example.config;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.management.ManagementFactory;
import org.junit.jupiter.api.Test;

class ConfigPrinterTest {

    @Test
    void receivesAllThreeConfigurationChannels() {
        String expectedMode = System.getProperty(
                "lab.expected.mode", "local");
        String expectedStage = System.getProperty(
                "lab.expected.stage", "injected-stage");

        assertEquals(expectedMode,
                System.getProperty("lab.mode"));
        assertEquals(expectedStage,
                System.getenv("LAB_STAGE"));
        assertEquals("fork-start",
                System.getProperty("lab.jvm.marker"));

        assertTrue(
                ManagementFactory.getRuntimeMXBean()
                        .getInputArguments()
                        .contains("-Xmx256m"),
                "Forked JVM should have -Xmx256m");

        System.out.println(
                "TEST CONFIG OK: " + ConfigPrinter.snapshot());
    }
}
~~~

Test này kiểm tra ba APIs/nguồn giá trị và dùng `ManagementFactory` để xác nhận JVM **chạy test** thật sự nhận `-Xmx256m`. Hai properties `lab.expected.mode`, `lab.expected.stage` chỉ phục vụ việc thay expected value trong thí nghiệm, không phải giá trị source của POM mặc định.

### 9.5. Chạy mặc định và kết quả

Từ thư mục `test-jvm-config-lab`:

~~~bash
java -version
mvn -version
mvn -B -ntp clean test
~~~

Nếu chạy thành công, Maven/Surefire báo tương đương:

~~~text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là các dấu hiệu trong log, không phải toàn bộ stdout. **Chuỗi do JUnit test tự in** là:

~~~text
TEST CONFIG OK: mode=local|env=injected-stage|jvm=fork-start
~~~

Surefire có thể hiển thị dòng test output trong console với tiền tố log hoặc trong `target/surefire-reports` tùy cấu hình redirect/capture. Test assertions mới là bằng chứng quan trọng rằng system property, environment và JVM args đã tới fork.

### 9.6. Override bằng CLI -D

Chạy:

~~~bash
mvn -B -ntp test -Dlab.mode=ci -Dlab.expected.mode=ci
~~~

`lab.mode=ci` từ Maven CLI được promoted sang test effective system properties vì cấu hình Surefire đã bật `promoteUserPropertiesToSystemProperties`. Property này ưu tiên hơn `lab.mode=local` từ `systemPropertyVariables`. Test vẫn PASS vì expected mode cũng được chỉnh thành `ci`.

**Chuỗi được test in:**

~~~text
TEST CONFIG OK: mode=ci|env=injected-stage|jvm=fork-start
~~~

Nếu chỉ dùng `-Dlab.mode=ci` mà không truyền `-Dlab.expected.mode=ci`, JUnit assertion mong chờ `local` sẽ cố ý fail. Đó là minh họa về giá trị đã được override, **không phải bằng chứng Maven/Surefire cấu hình sai**.

### 9.7. Tắt promotion để so sánh

Thử đổi POM:

~~~xml
<promoteUserPropertiesToSystemProperties>false</promoteUserPropertiesToSystemProperties>
~~~

Sau đó chạy `mvn test -Dlab.mode=ci`. Vì không tự promote key này, `lab.mode` mà test nhìn thấy có thể trở lại giá trị `local` từ `systemPropertyVariables`, nếu không có nguồn override khác. Chỉ thay đổi `lab.mode` không đủ để kết luận mọi Maven properties bị tắt, vì Maven có các nguồn nội suy/plugin config khác. Hoàn nguyên `true` khi xong.

### 9.8. Chạy Java main độc lập để so sánh

Sau khi Maven compile xong, chạy Java CLI trực tiếp. Linux/macOS:

~~~bash
LAB_STAGE=manual-stage java -Dlab.mode=manual \
  -Dlab.jvm.marker=manual-jvm \
  -cp target/classes dev.example.config.ConfigPrinter
~~~

PowerShell:

~~~powershell
$env:LAB_STAGE = 'manual-stage'
java -Dlab.mode=manual -Dlab.jvm.marker=manual-jvm -cp target/classes dev.example.config.ConfigPrinter
Remove-Item Env:LAB_STAGE
~~~

**Stdout chính xác từ Main.java:**

~~~text
CONFIG: mode=manual|env=manual-stage|jvm=manual-jvm
~~~

Những giá trị này đến từ Java CLI và shell, **không phải do Surefire POM áp cho process Java độc lập**. Nếu chạy main không set env/JVM properties, stdout còn phụ thuộc environment thật của máy, nên không có một chuỗi mặc định chắc chắn cho mọi máy.

### 9.9. Xác nhận environment inheritance

Trong lab, POM Surefire luôn đặt `LAB_STAGE=injected-stage` cho test fork. Nếu muốn thử **kế thừa giá trị từ shell**, tạm xóa entry `<LAB_STAGE>injected-stage</LAB_STAGE>` khỏi Surefire `environmentVariables`, rồi chạy:

Bash:

~~~bash
LAB_STAGE=from-shell mvn -B -ntp test \
  -Dlab.expected.stage=from-shell
~~~

PowerShell:

~~~powershell
$env:LAB_STAGE = 'from-shell'
mvn -B -ntp test -Dlab.expected.stage=from-shell
Remove-Item Env:LAB_STAGE
~~~

`lab.expected.stage` là expected value mà test dùng. Nếu fork kế thừa biến shell bình thường, test PASS; sau thí nghiệm hoàn nguyên POM. Không thực hiện thí nghiệm này bằng một biến chứa credential thực.

## 10. JaCoCo: đừng đánh rơi Java agent khi sửa argLine

Một dự án chạy coverage thường dùng `jacoco:prepare-agent` để chuẩn bị option `-javaagent:...` trong Maven property, tên mặc định thường là `argLine` đối với project Java thông thường. Nếu Surefire khai:

~~~xml
<argLine>-Xmx256m</argLine>
~~~

mà không giữ option agent, test vẫn PASS nhưng JaCoCo có thể không thu được coverage. Surefire hỗ trợ **late property evaluation**:

~~~text
@{argLine}
~~~

Ví dụ fragment POM cho dự án **có JaCoCo**:

~~~xml
<properties>
    <argLine></argLine>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.jacoco</groupId>
            <artifactId>jacoco-maven-plugin</artifactId>
            <version>0.8.13</version>
            <executions>
                <execution>
                    <goals>
                        <goal>prepare-agent</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.4</version>
            <configuration>
                <argLine>
                    @{argLine} -Xmx256m -Dlab.jvm.marker=fork-start
                </argLine>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

`@{argLine}` được Surefire thay **khi goal chạy**, giúp nó nhận giá trị `argLine` đã được plugin như JaCoCo chỉnh trước đó. Trong khi `${argLine}` là interpolation thông thường của Maven, có thể được xử lý trước khi JaCoCo cập nhật property. Đây là một lý do quan trọng để phân biệt hai cú pháp.

Property `<argLine></argLine>` rỗng giúp tránh giá trị placeholder chưa tồn tại trong cấu hình ở một số tình huống/version. Nhưng nó **không tự bật JaCoCo**. Muốn báo cáo coverage, cần kiểm tra agent được nạp và cấu hình `jacoco:report`, `jacoco:check` theo nhu cầu. Đừng thêm agent trùng hoặc ghi đè `argLine` từ parent/config khác mà không kiểm thử.

Fragment này minh họa JaCoCo integration, **không được thêm vào lab cơ bản nếu chưa có mục tiêu coverage**.

## 11. Failsafe cho integration tests: tương tự nhưng plugin độc lập

Surefire thường chạy unit tests ở `test`. Failsafe thường được cấu hình với `failsafe:integration-test` và `failsafe:verify` ở các phase tương ứng. Failsafe có tham số cùng nhóm:

- `systemPropertyVariables`, `systemPropertiesFile`
- `environmentVariables`, `excludedEnvironmentVariables`
- `argLine`
- `forkCount` và `reuseForks`
- `promoteUserPropertiesToSystemProperties` trong các phiên bản hỗ trợ

**Không mặc định** phần `<configuration>` của Surefire tự truyền sang Failsafe. Nếu integration tests có nhu cầu riêng, cấu hình plugin Failsafe:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.4</version>
    <configuration>
        <forkCount>1</forkCount>
        <systemPropertyVariables>
            <lab.mode>integration</lab.mode>
        </systemPropertyVariables>
        <environmentVariables>
            <LAB_STAGE>integration-stage</LAB_STAGE>
        </environmentVariables>
        <argLine>-Xmx256m -Dlab.jvm.marker=integration-fork</argLine>
    </configuration>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Đây là **POM fragment bổ sung**, không nằm trong ví dụ 1-unit-test ở mục 9. Với integration test class theo pattern `*IT.java`, cấu hình lifecycle đúng và các tài nguyên test phù hợp, dùng:

~~~bash
mvn -B -ntp verify
~~~

Không chỉ gọi `mvn integration-test` rồi kết luận build đã thực hiện toàn bộ verification/cleanup. `verify` là phase quan trọng để Failsafe đánh giá kết quả và tiến qua các phase cần thiết sau integration-test.

Với JaCoCo và Failsafe, nhớ kiểm tra fork JVM của integration tests cũng giữ được agent options. Một config JaCoCo/Surefire dùng đúng chưa chắc đã phủ hết Failsafe.

## 12. CI/CD: truyền biến đúng nơi và bảo vệ thông tin nhạy cảm

Một CI job có thể cấp config qua job environment, secret manager, CLI arguments hoặc POM. Ví dụ đoạn steps của GitHub Actions:

~~~yaml
steps:
  - uses: actions/checkout@v4

  - uses: actions/setup-java@v4
    with:
      distribution: temurin
      java-version: '17'

  - name: Run unit tests
    run: ./mvnw -B -ntp test -Dlab.mode=ci -Dlab.expected.mode=ci
~~~

Đây là **steps fragment**, không phải workflow hoàn chỉnh. Nó giả định repository có Maven Wrapper. Để dùng độc lập cần `on`, `jobs`, `runs-on` và permissions phù hợp; nếu không có wrapper thì thay bằng `mvn` đã được chuẩn hóa trên runner.

Một job có thể khai:

~~~yaml
env:
  LAB_STAGE: ci-stage
~~~

Nhưng trong **POM lab**, Surefire định nghĩa `<LAB_STAGE>injected-stage</LAB_STAGE>`, nên test fork nhìn thấy `injected-stage` dù environment của job là `ci-stage`. Muốn test nhận giá trị job, phải bỏ override key hoặc cấu hình cách truyền rõ ràng.

### 12.1. Secrets: không in tất cả properties/environment

Truyền password theo CLI:

~~~bash
mvn test -Dservice.password=EXAMPLE_ONLY
~~~

có thể lộ giá trị qua shell history, process command line, Maven `-X` log, báo cáo test, cache hoặc CI artifacts. Dòng này chỉ là **minh họa rủi ro**, không được đưa secret thật theo cách tùy tiện.

Với test thực sự cần credential:

- Dùng secret manager của CI, scope quyền tối thiểu và biến được cấp chỉ cho step/job cần thiết.
- Tránh commit secret thật vào POM, `systemPropertiesFile` hoặc source fixture.
- Không log toàn bộ `System.getProperties()` hoặc `System.getenv()`.
- Không chụp và phát hành unredacted Maven debug output.
- Không in giá trị nhạy cảm trong JUnit assertion failure message.
- Nếu credential đã lọt vào log/artifact, xử lý như một sự cố secrets theo quy trình và rotate khi cần.

### 12.2. Giữ test có thể chạy lại

Nếu cùng một test dựa vào shell environment ở laptop nhưng CI thiếu biến, build có thể chỉ fail trên CI. Thiết kế:

- **Một default an toàn và không nhạy cảm** cho unit tests.
- **Fail fast có thông báo rõ** nếu giá trị bắt buộc thiếu, không tự nối tới production.
- Đặt integration tests dùng dịch vụ thật vào Failsafe với profile và credentials riêng.
- Ghi version Maven/JDK/plugins, active profiles, fork options và những keys không nhạy cảm cần thiết để tái lập.

## 13. Gặp lỗi: điều tra theo đúng lớp

### 13.1. System.getProperty trả null

Kiểm tra:
1. Key có được khai trong `systemPropertyVariables` của plugin **thực sự chạy test** chưa?
2. Có nhầm `<properties>` của Maven với Java system property không?
3. Test đang chạy bằng Maven Surefire hay IDE?
4. Tên key có viết đúng hoa/thường không?
5. Có property khác từ CLI, file hoặc parent override không?
6. `promoteUserPropertiesToSystemProperties` có bật với Surefire version hiện tại không?
7. Maven có nội suy POM expression ra một String mong đợi không?

Dùng:

~~~bash
mvn -version
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-pom.xml
mvn -B -ntp test
~~~

Tìm đúng `maven-surefire-plugin` và execution/config trong effective POM. **Effective POM cho thấy model**, không phải bằng chứng cuối cùng về giá trị mà forked JVM đã nhận; cần test assertion.

### 13.2. System.getenv trả null

Kiểm tra:

- Biến được đặt **trước khi process Maven khởi động** chưa?
- Có đúng environment của shell/CI step/container không?
- Surefire `environmentVariables` có override hay `excludedEnvironmentVariables` loại nó không?
- `forkCount` có bằng 0 khiến bạn hiểu sai ngữ cảnh không?
- IDE có dùng process environment khác không?
- Tên key/case khác nhau giữa Windows và Linux không?

Bash kiểm tra một biến mẫu không nhạy cảm:

~~~bash
printf 'LAB_STAGE=%s\n' "$LAB_STAGE"
~~~

PowerShell:

~~~powershell
Write-Output "LAB_STAGE=$env:LAB_STAGE"
~~~

Không dùng lệnh `env` để in toàn bộ thông tin trong CI logs có secrets.

### 13.3. JVM option không hiệu lực

Khả năng:

- Test chạy bằng Failsafe, nhưng `argLine` chỉ cấu hình Surefire.
- `forkCount=0` nên không có fork mới.
- Một plugin JaCoCo hoặc parent config đã thay `argLine`.
- JDK được fork khác JDK bạn kiểm tra.
- Option cũ không còn hợp lệ trên Java 17.
- Value có dấu cách/quotes gây lỗi command line.
- Bộ nhớ container không đủ cho `-Xmx` mong muốn.

Đọc log `argLine`/fork command ở mức phù hợp; với key an toàn, dùng `ManagementFactory.getRuntimeMXBean().getInputArguments()` trong test. Maven `-X` giúp debug nhưng phải lọc thông tin nhạy cảm trước khi chia sẻ.

### 13.4. IDE chạy fail nhưng mvn test PASS

IDE có thể dùng JUnit runner riêng, **không đi qua Surefire**. Run Configuration của IDE thường có ô **VM options**, **Environment variables** và **Program arguments** riêng. Vì thế POM Surefire configuration không nhất thiết được IDE tự chuyển vào test process.

Hãy xác nhận `mvn test` PASS rồi cấu hình IDE tương đương hoặc chạy tests bằng Maven trong IDE. Không sửa production POM chỉ để chữa một IDE launch setup nếu pipeline Maven vốn đúng.

### 13.5. Fork chết trước khi JUnit chạy

Thông điệp kiểu `The forked VM terminated without properly saying goodbye` có thể xuất phát từ JVM option không hợp lệ, out-of-memory, system exit, thiếu fork permissions, agent không tương thích hoặc lỗi native process. Nó **không chứng minh** rằng `systemPropertyVariables` sai.

Kiểm tra Java version, `argLine`, fork process exit code, report directory và debug log. Không thêm `--add-opens` hay đổi `-Xmx` ngẫu nhiên nếu chưa biết lỗi.

### 13.6. Test flaky khi chạy nhiều class song song

Nếu các tests cùng sửa `System.setProperty` hoặc dùng static mutable state trong một fork, thứ tự chạy có thể làm kết quả khác nhau. `reuseForks=true` không reset JVM state sau mỗi class. Dùng cleanup/isolated processes hoặc refactor code nhận cấu hình bằng dependency injection. Không dựa vào thứ tự test mặc định.

## 14. Các tình huống thường gặp và lựa chọn đúng

| Nhu cầu | Chọn cách nào? |
| --- | --- |
| Unit test cần `lab.mode` dạng chuỗi | `systemPropertyVariables` hoặc Maven `-D` khi promotion được kiểm soát |
| Test cần `LAB_STAGE` | Shell/CI environment hoặc `environmentVariables` |
| Test cần `-Xmx512m` | `argLine` ở Surefire/Failsafe fork |
| Test cần `-Dfile.encoding=UTF-8` từ lúc JVM start | `argLine` và xác minh trên JDK thực tế |
| Test cần nhiều properties từ file | `systemPropertiesFile` |
| Muốn tránh fork đọc một env key | `excludedEnvironmentVariables` |
| Muốn JaCoCo agent tồn tại khi đã có custom argLine | `@{argLine}`, đúng `prepare-agent` và kiểm tra output |
| Muốn đổi heap Maven process | `MAVEN_OPTS`, không đồng nghĩa heap test fork |
| Test chạy trực tiếp từ IDE | IDE Run Configuration hoặc Maven test runner |
| Integration tests cần một environment khác | Failsafe config và `mvn verify` |

### 14.1. Value có dấu cách

Shell quoting khác nhau. Các ví dụ truyền một argument duy nhất:

Bash:

~~~bash
mvn -B -ntp test '-Dlab.label=hello world'
~~~

PowerShell:

~~~powershell
mvn -B -ntp test '-Dlab.label=hello world'
~~~

Với value chứa ký tự `$`, nháy kép, dấu `!`, xuống dòng hoặc path Windows, kiểm tra shell-specific escaping. Giá trị phức tạp nên truyền qua file/properties/CI mechanism thay vì nhồi vào một `-D` dài.

### 14.2. JUnit Platform configuration khác system properties

JUnit 5 có các configuration parameters riêng, ví dụ cấu hình test parallelism. Surefire còn hỗ trợ:

~~~xml
<configuration>
    <properties>
        <configurationParameters>
            junit.jupiter.execution.parallel.enabled = false
        </configurationParameters>
    </properties>
</configuration>
~~~

Đây là cấu hình **JUnit provider**, không phải bất kỳ `<properties>` nào trong Surefire cũng tự trở thành `System.getProperty`. Chọn cơ chế theo tài liệu JUnit Platform và Surefire phiên bản đang dùng.

## 15. Quy trình debug 8 bước

1. Xác định test thật chạy bằng **Surefire**, **Failsafe** hay **IDE**.
2. Xác nhận Maven/JDK/plugin versions bằng `mvn -version` và log goal.
3. Xem effective POM của **đúng module**, gồm `systemPropertyVariables`, `environmentVariables`, `argLine`, `forkCount` và parent/pluginManagement.
4. Kiểm tra active profiles và Maven CLI `-D` được truyền đúng shell quoting.
5. Phân loại key: Java system property, OS environment variable hay startup option.
6. Tạo assertion đơn giản trong **forked test** dùng `System.getProperty`, `System.getenv` hoặc `ManagementFactory`.
7. Xem `target/surefire-reports` và fork log, chỉ bật `-X` khi thật sự cần và đảm bảo không leak secrets.
8. Sửa một nguồn cấu hình rồi chạy `mvn clean test` hoặc `mvn clean verify`, so output trước/sau.

Không tự đặt `CONTENT_QA=FAIL` hoặc kết luận plugin hỏng chỉ vì test bị thiếu environment trong IDE; cần xác định đúng kênh cấu hình.

## 16. Bài tập kèm đáp án

**Bài 1:** `System.getenv("LAB_STAGE")` trả null nhưng `System.getProperty("LAB_STAGE")` là `integration`. Vì sao?

**Đáp án:** Bạn đã đặt Java system property, không đặt OS environment variable. Hai namespaces tách biệt.

**Bài 2:** Surefire 3.5.4 có `<systemPropertyVariables><lab.mode>local</lab.mode>` và gọi `mvn test -Dlab.mode=ci`. Với promotion bật, test thấy gì?

**Đáp án:** `ci`, vì Maven session user property được promoted và ưu tiên hơn value trong `systemPropertyVariables`.

**Bài 3:** CI đặt `LAB_STAGE=ci-stage` nhưng test thấy `injected-stage`. POM có `<environmentVariables><LAB_STAGE>injected-stage</LAB_STAGE>`. Có mâu thuẫn không?

**Đáp án:** Không. Surefire ghi đè key tương ứng trong fork environment.

**Bài 4:** Chỉ dùng `MAVEN_OPTS=-Xmx1g` thì test JVM chắc chắn có heap 1 GiB không?

**Đáp án:** Không. MAVEN_OPTS thường áp cho Maven JVM; test fork cần `argLine` riêng.

**Bài 5:** `forkCount=0` nhưng `argLine=-Xmx512m`. Cờ này có tạo một JVM test mới với heap 512 MiB không?

**Đáp án:** Không có fork JVM mới theo chế độ đó, nên `argLine` không thay startup của JVM Maven đã chạy.

**Bài 6:** Một key nằm ở `systemPropertiesFile`, `systemPropertyVariables` và CLI `-D`. Trong Surefire 3.5.4 mặc định, nguồn nào ưu tiên?

**Đáp án:** CLI user property khi promotion bật; kế đó `systemPropertyVariables`; kế tiếp file, theo tài liệu về effective properties.

**Bài 7:** `System.setProperty("X", "a")` có sửa `System.getenv("X")` không?

**Đáp án:** Không. Thao tác thứ nhất chỉ sửa Java system property của process.

**Bài 8:** Cần thiết lập `file.encoding` khi JVM startup. Đặt trong `systemPropertyVariables` hay `argLine`?

**Đáp án:** `argLine` của fork JVM và kiểm chứng trên Java version thực tế, vì JVM có thể cache property sớm.

**Bài 9:** Thêm JaCoCo rồi tests PASS nhưng không có coverage. Nên kiểm tra gì?

**Đáp án:** Agent argument đã được `jacoco:prepare-agent` tạo có được chuyển vào Surefire `argLine` không; có thể cần `@{argLine}` late replacement.

**Bài 10:** Chỉ khai `systemPropertyVariables` trong Surefire thì Failsafe `PaymentIT` tự nhận các key không?

**Đáp án:** Không đảm bảo. Failsafe là plugin độc lập, cần cấu hình tương ứng hoặc cơ chế chia sẻ rõ ràng.

**Bài 11:** Maven test PASS nhưng IntelliJ Run Test fail vì thiếu env. Nguyên nhân khả dĩ?

**Đáp án:** IDE runner không tự áp Surefire POM config; cấu hình IDE environment/VM options hoặc chạy tests qua Maven.

**Bài 12:** Nếu test A sửa global system property mà không khôi phục, test B trong fork được tái sử dụng có thể bị ảnh hưởng không?

**Đáp án:** Có. Tránh state leak hoặc restore sau test.

**Bài 13:** Có nên log toàn bộ `System.getProperties()` và `System.getenv()` vào CI để điều tra?

**Đáp án:** Không. Có thể lộ secrets hoặc metadata. Chỉ kiểm tra keys không nhạy cảm, có lọc/redact.

**Bài 14:** Tại sao `mvn test -Dlab.mode=ci` làm một assertion cố định kỳ vọng `local` fail lại có thể là dấu hiệu plugin đang hoạt động đúng?

**Đáp án:** Vì CLI user property đã override `lab.mode` thành `ci`. Cần đồng bộ expected value với chế độ test đã chọn hoặc vô hiệu override theo mục đích.

## 17. Checklist trước khi sử dụng trong CI

- [ ] Xác định mỗi key là system property, environment variable hay JVM startup flag.
- [ ] Pin Surefire/Failsafe versions và kiểm tra tương thích Maven/JDK.
- [ ] Dùng `systemPropertyVariables` cho Java system properties mới; không ưu tiên `systemProperties` deprecated.
- [ ] Nếu dùng `systemPropertiesFile`, có file tồn tại và biết thứ tự ưu tiên.
- [ ] Kiểm tra `promoteUserPropertiesToSystemProperties` khi muốn CLI `-D` override.
- [ ] Biến môi trường được đặt ở đúng shell/job trước khi Maven chạy.
- [ ] `environmentVariables` không vô tình override environment của CI.
- [ ] `excludedEnvironmentVariables` không loại biến cần thiết.
- [ ] `argLine` áp cho đúng JVM fork; `forkCount` phù hợp.
- [ ] Không nhầm `MAVEN_OPTS` với `argLine`.
- [ ] Nếu có JaCoCo, giữ agent argument trong Surefire/Failsafe.
- [ ] Không đưa secrets thật vào POM, CLI command line, report hoặc logs.
- [ ] Unit tests không làm rò state qua `System.setProperty` thiếu cleanup.
- [ ] Chạy `mvn clean test` hoặc `mvn clean verify` và xem test reports.
- [ ] Với CI khác local, so Maven Wrapper, profiles, plugin versions và shell quoting.
- [ ] Với Failsafe, chạy `verify` sau integration-test theo lifecycle.
- [ ] Có assertion kiểm chứng các kênh cấu hình tại JVM thực tế chạy test.

## 18. Tài liệu chính thức và tham khảo kỹ thuật

1. [Maven Surefire Plugin 3.5.4 — surefire:test](https://maven.apache.org/surefire-archives/surefire-3.5.4/maven-surefire-plugin/test-mojo.html): định nghĩa tham số, effective system property precedence, fork và environment.
2. [Maven Surefire — Using System Properties](https://maven.apache.org/components/surefire-archives/surefire-3.5.4/maven-surefire-plugin/examples/system-properties.html): `systemPropertyVariables`, `systemPropertiesFile` và deprecated `systemProperties`.
3. [Maven Surefire — Fork Options and Parallel Test Execution](https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options-and-parallel-execution.html): `argLine`, `forkCount`, `reuseForks`, forkNumber.
4. [Maven Surefire — FAQ](https://maven.apache.org/surefire/maven-surefire-plugin/faq.html): `@{argLine}`, forked JVM troubleshooting.
5. [Maven Failsafe Plugin — failsafe:integration-test](https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html): các tham số tương tự của integration testing.
6. [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): `test`, `integration-test`, `verify`.
7. [Maven POM Reference](https://maven.apache.org/pom.html): `properties`, `build/plugins` và `pluginManagement`.
8. [Maven Help Plugin — help:effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): xem cấu hình sau inheritance/profile.
9. [JaCoCo Maven Plugin — prepare-agent](https://www.jacoco.org/jacoco/trunk/doc/prepare-agent-mojo.html): agent configuration và late replacement.
10. [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): JUnit Jupiter assertions và test lifecycle.
