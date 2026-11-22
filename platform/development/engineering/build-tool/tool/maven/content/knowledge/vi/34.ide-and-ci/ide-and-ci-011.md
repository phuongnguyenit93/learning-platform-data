# Kiểm chứng trên nhiều phiên bản JDK bằng cấu hình tường minh trong Maven, IDE và CI

## 1. Mục tiêu: chứng minh tương thích, không chỉ đổi nhãn “Java 17”

Một dự án Java có thể cần **biên dịch cho Java 17**, chạy trên **JDK 17 và JDK 21**, và được kiểm tra nhất quán trên laptop, IDE và CI. Nếu chỉ đặt một dòng `<java.version>17</java.version>` hoặc chọn “Java 17” trong giao diện IDE, chưa đủ để chứng minh điều này.

Các câu hỏi phải trả lời riêng:

1. **JDK nào chạy chính Maven?** Xem `mvn -version`, không chỉ `java -version`.
2. **JDK nào thực thi `javac` cho source/test?** Mặc định thường là JDK của Maven, nhưng Maven Toolchains/Compiler Plugin có thể chọn JDK khác.
3. **Bytecode/API target nào được phép?** Dùng `maven.compiler.release`, không suy ra từ JDK đang chạy.
4. **JVM nào thực sự chạy JUnit tests?** Surefire/Failsafe có thể fork một JVM khác hoặc dùng toolchain riêng.
5. **JRE/JDK nào chạy artifact trong thực tế?** CI build pass trên JDK 21 không đủ chứng minh app vẫn chạy trên JDK 17.
6. **Mỗi bản JDK có thực sự có một lượt verify độc lập?** Dùng CI matrix, log toolchain, test assertion và tình trạng job tách biệt.

Kết quả mong muốn: một **hợp đồng tương thích được viết rõ** và kiểm thử được:

> Mã nguồn và API Java tối thiểu là **17**. Cùng một project được build và chạy JUnit tests riêng trên **JDK 17 và JDK 21**. Đầu ra Java của ứng dụng ổn định. Nếu sai JDK trong bất kỳ matrix job nào, job phải fail thay vì được tính là đã kiểm thử phiên bản đó.

Bài tập dùng **Maven 3.9+, Java 17+, Maven Compiler Plugin 3.15.0, Maven Surefire Plugin 3.5.2 và JUnit Jupiter 5.11.4**. Các phiên bản plugin trong demo được pin cụ thể để tránh thay đổi implicit defaults. Khi đưa vào dự án thật cần đối chiếu các phiên bản được tổ chức chấp thuận.

## 2. Năm lớp phiên bản Java thường bị trộn lẫn

| Lớp | Cấu hình/quan sát | Tác động |
| --- | --- | --- |
| Maven runtime JDK | `JAVA_HOME`, `PATH`, `mvn -version`, IDE Maven runner JRE | Java chạy chính Maven và plugins không dùng toolchain |
| Compiler JDK | Maven Compiler Plugin, Toolchains Plugin, `javac -version` | Trình biên dịch Java thực sự được gọi |
| Source/API/bytecode baseline | `<maven.compiler.release>17</maven.compiler.release>` | Cú pháp Java, Java SE APIs và classfile target được phép |
| Test JVM | Surefire/Failsafe fork, `jdkToolchain`, `jvm` | JVM thực hiện unit/integration tests |
| Production runtime | Image/container/JRE/JDK khi deploy | JVM thực tế tải classes và thực thi ứng dụng |

Đặt `maven.compiler.release=17` trên JDK 21 thường tạo bytecode **major version 61** phù hợp Java 17 và chặn dùng Java SE APIs xuất hiện muộn hơn Java 17. Nhưng nó **không tự chạy các tests trên JDK 17**. Nếu Surefire tests chỉ chạy trên JDK 21, lỗi chỉ xuất hiện trên JVM 17 vẫn có thể lọt qua.

Ngược lại, dùng JDK 17 để biên dịch một project có `<maven.compiler.release>21</maven.compiler.release>` **không hoạt động**: compiler JDK 17 không biết phát hành Java 21. Một compiler mới hơn có thể target một số release cũ; compiler cũ không thể target release tương lai.

## 3. Vì sao nên dùng `--release`, không chỉ `-source` và `-target`?

Xét một project tuyên bố tương thích Java 17 nhưng developer build bằng JDK 21.

Cấu hình yếu:

~~~xml
<properties>
    <maven.compiler.source>17</maven.compiler.source>
    <maven.compiler.target>17</maven.compiler.target>
</properties>
~~~

Cấu hình này chủ yếu đặt source syntax và classfile target. Nó **không đầy đủ như `--release`** để ràng buộc tập API của Java SE version cũ khi compiler chạy trên JDK mới hơn.

Cấu hình khuyến nghị cho ví dụ:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Trên JDK 17 hoặc 21, Maven Compiler Plugin sử dụng cơ chế `javac --release 17`. Compiler kiểm đồng thời:

- Java language features của release 17.
- Public Java SE APIs khả dụng trong release 17.
- Bytecode/classfile version tương ứng release 17.

Ví dụ source sử dụng một JDK 21 API không có ở Java 17 sẽ bị compiler từ chối dù build đang chạy trên JDK 21. Đây là kiểm tra sớm cực kỳ giá trị cho thư viện phát hành tương thích ngược.

**Giới hạn:** `--release 17` chỉ ràng buộc Java platform APIs theo hỗ trợ của `javac`; nó **không đảm bảo** toàn bộ dependencies bên ngoài tương thích Java 17, không kiểm hành vi khác nhau giữa vendors, không thử runtime code paths và không giải quyết native libraries. Vì vậy vẫn cần chạy tests thật trên JDK tối thiểu.

### 3.1. Source, target và release khác version của Maven project

~~~text
project.version       = 1.0.0       -> phiên bản artifact
maven.compiler.release = 17         -> Java baseline
Maven runtime JDK      = 21         -> JVM chạy Maven
Surefire test JVM      = 21         -> JVM chạy tests
production JVM         = 17 hoặc 21 -> mục tiêu kiểm chứng
~~~

Đừng đặt `<version>17</version>` ở root project rồi coi đó là cấu hình Java target. Maven GAV version có ý nghĩa riêng.

## 4. Kiểm tra JDK đang hoạt động trước khi sửa POM

Trên POSIX shell:

~~~bash
java -version
javac -version
mvn -version
echo "$JAVA_HOME"
~~~

Trên PowerShell:

~~~powershell
java -version
javac -version
mvn -version
$env:JAVA_HOME
Get-Command java
Get-Command javac
~~~

**`mvn -version` đặc biệt quan trọng.** Nó báo Java version và Java home mà Maven launcher đang dùng. `java -version` chỉ cho biết executable `java` resolve được từ shell ở thời điểm đó. Hai thông tin có thể khác khi `JAVA_HOME`, `PATH`, Maven launcher hoặc IDE runner configuration không đồng bộ.

Phân biệt:

~~~text
java -version          -> Java executable trên PATH
javac -version         -> Java compiler executable trên PATH
mvn -version           -> Java runtime dùng cho Maven process
Surefire test log/test -> JVM thật sự chạy tests
Toolchains log         -> JDK được Maven plugins chọn
~~~

**`java -version` không chứng minh Compiler Plugin hoặc Surefire đang dùng cùng JDK** nếu Maven Toolchains được cấu hình. Cũng không dùng `System.getProperty("java.version")` trong một app chạy bằng `exec:java` rồi coi nó luôn đại diện cho JVM của Surefire: Exec Plugin có cơ chế thực thi khác, trong khi Surefire có JVM fork riêng.

### 4.1. JDK khác JRE

Một JRE/runtime chỉ có thành phần chạy Java; để compile Java source thường cần một **JDK** với `javac` và công cụ phát triển. Trong CI matrix ta cài JDK rõ ràng, không chỉ JRE. `mvn -version` có thể hoạt động trên một runtime nhưng Maven Compiler Plugin lại không tìm được compiler nếu thiếu JDK/toolchain.

## 5. Một cấu hình tường minh cần ghi ở đâu?

| Nhu cầu | Nơi cấu hình | Không nên hiểu sai |
| --- | --- | --- |
| Java baseline/API | `pom.xml`, `maven.compiler.release` | Không chọn JVM test |
| Plugin versions | `pom.xml`, `<build><plugins>`/`pluginManagement` | Không tự cài JDK |
| Maven runtime JDK trên CI | `actions/setup-java` hoặc CI image/environment | Không ép compiler/test dùng cùng JDK nếu toolchains override |
| Compiler/test JDK khác Maven JVM | Toolchains Plugin và `toolchains.xml`/toolchain-aware plugins | Không phải mọi plugin đều toolchain-aware |
| JDK của IDE | Project SDK, Maven runner JDK, test runner config | IDE editor không phải Maven CLI |
| JDK thực tế trong test | JUnit assertion/log `Runtime.version().feature()` | `mvn -version` chỉ là một phần của bằng chứng |
| Production JDK | Docker base image/runtime configuration | Build matrix không tự triển khai production |

Cấu hình có thể tái hiện không phải là việc chọn một version ở **một** màn hình. Nó là chuỗi **hợp đồng POM + toolchain/environment + test evidence + CI status**.

## 6. Bài lab Java 17: project có thể chạy trên hai JDK

Ta xây một thư viện/ứng dụng nhỏ dùng **Java record**, được hỗ trợ từ Java 16 và nằm trong baseline Java 17. Application trả chuỗi ổn định `"Compatible: MAVEN=42"`. Test suite kiểm logic và **xác nhận JVM thực tế** qua `Runtime.version().feature()`.

### 6.1. Cấu trúc project

~~~text
jdk-matrix-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/jdkmatrix/
    │       └── CompatibilityService.java
    └── test/
        └── java/com/example/jdkmatrix/
            └── CompatibilityServiceTest.java
~~~

Không có cơ sở dữ liệu, network calls hoặc secret. Khi build, Maven có thể cần Internet hoặc internal repository mirror đã cấu hình để resolve JUnit/plugins.

### 6.2. `pom.xml` hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>jdk-matrix-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.jupiter.version>5.11.4</junit.jupiter.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.jupiter.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.15.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <forkCount>1</forkCount>
                    <reuseForks>true</reuseForks>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Mấu chốt:** Cùng một `pom.xml` được dùng trong cả hai jobs **Java 17 và Java 21**, với `maven.compiler.release=17` **không thay đổi** giữa các jobs. Nhờ vậy test matrix kiểm tương thích cho một baseline cố định, không tạo hai sản phẩm có target khác nhau rồi gộp kết quả.

Surefire `forkCount=1` khởi chạy JVM riêng cho tests. Khi **không** cấu hình Maven Toolchains hoặc Surefire `jdkToolchain` riêng, JVM tests thông thường dùng Java từ môi trường Maven job đang chạy; assertion ở phần sau xác minh thực tế để tránh dựa vào giả định.

`junit-jupiter` có `test` scope, không đưa vào runtime dependencies của JAR ứng dụng. `maven-compiler-plugin` có version pin rõ; `maven-jar-plugin` tạo JAR thường, nhưng chưa cấu hình runnable JAR manifest.

### 6.3. `CompatibilityService.java`

Tạo `src/main/java/com/example/jdkmatrix/CompatibilityService.java`:

~~~java
package com.example.jdkmatrix;

import java.util.Locale;

public final class CompatibilityService {

    private CompatibilityService() {
    }

    public record Result(String name, int value) {
    }

    public static Result compute(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }

        String normalized = raw.strip()
                .toUpperCase(Locale.ROOT);

        return new Result(normalized, 21 * 2);
    }

    public static String message(String raw) {
        Result result = compute(raw);
        return "Compatible: "
                + result.name()
                + "="
                + result.value();
    }

    public static void main(String[] args) {
        System.out.println(message(" maven "));
    }
}
~~~

Các API được dùng (`record`, `String.isBlank`, `String.strip`, `Locale.ROOT`) đều phù hợp Java 17. Việc không dùng `var` hay API riêng JDK 21 giúp ví dụ dễ đọc, nhưng **giới hạn thật vẫn do `--release 17` và runtime tests chứng minh**.

Lệnh chạy chương trình sau khi compile:

~~~bash
java -cp target/classes com.example.jdkmatrix.CompatibilityService
~~~

**Stdout chính xác của application main** trên cả JDK 17 và JDK 21:

~~~text
Compatible: MAVEN=42
~~~

Đây là stdout của ứng dụng, không bao gồm Maven logs. Không chạy `java -jar target/jdk-matrix-demo-1.0.0.jar` và kỳ vọng chạy được, bởi POM chưa thêm `Main-Class` manifest.

### 6.4. `CompatibilityServiceTest.java`

Tạo `src/test/java/com/example/jdkmatrix/CompatibilityServiceTest.java`:

~~~java
package com.example.jdkmatrix;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CompatibilityServiceTest {

    @Test
    void computesUsingJava17Record() {
        CompatibilityService.Result actual =
                CompatibilityService.compute(" maven ");

        assertEquals(
                new CompatibilityService.Result("MAVEN", 42),
                actual);
        assertEquals("Compatible: MAVEN=42",
                CompatibilityService.message(" maven "));
    }

    @Test
    void rejectsBlankInput() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> CompatibilityService.compute("   "));

        assertEquals("name must not be blank",
                error.getMessage());
    }

    @Test
    void testJvmMatchesDeclaredMatrixCell() {
        int actual = Runtime.version().feature();

        assertTrue(actual >= 17,
                "Test JVM must support Java 17+");

        String expected =
                System.getenv("EXPECTED_JDK_FEATURE");

        if (expected != null && !expected.isBlank()) {
            assertEquals(Integer.parseInt(expected), actual,
                    "Surefire JVM differs from CI matrix JDK");
        }

        System.out.println("TEST_JDK_FEATURE=" + actual);
    }
}
~~~

Có **ba test methods**. Test cuối là phần đặc biệt của bài:

- `Runtime.version().feature()` đọc **JVM đang thực thi JUnit test**, không đọc Maven POM.
- Khi chạy local không có `EXPECTED_JDK_FEATURE`, test vẫn đòi JVM >=17 và in giá trị thực.
- Khi CI đặt `EXPECTED_JDK_FEATURE=17`, nếu Surefire JVM thực là 21, assertion fail.
- Khi CI đặt `EXPECTED_JDK_FEATURE=21`, nếu Surefire JVM thực là 17, assertion fail.
- `System.getenv` cần tên environment variable chính xác; đây không phải Maven property tự động.
- Một `EXPECTED_JDK_FEATURE` sai định dạng (ví dụ `"21.x"`) sẽ khiến `parseInt` ném exception, đó cũng là CI config failure cần sửa thay vì silently bỏ qua.

**Không viết assertion cố định `assertEquals(17, Runtime.version().feature())` cho tất cả jobs**, bởi như vậy sẽ chặn chính việc thử JDK 21. Expected value phải gắn với từng matrix cell được xác định trước.

### 6.5. Chạy tại local

Trong folder chứa `pom.xml`:

~~~bash
mvn -version
java -version
javac -version
mvn -B -ntp clean verify
java -cp target/classes com.example.jdkmatrix.CompatibilityService
~~~

Khi Maven/JDK được cấu hình đúng:

- `compile` và `testCompile` dùng Java release 17.
- Surefire phát hiện class `CompatibilityServiceTest`.
- Có ba JUnit 5 tests, tất cả pass.
- Test runtime in `TEST_JDK_FEATURE=17` nếu JVM test thật là JDK 17, hoặc `TEST_JDK_FEATURE=21` nếu thật là JDK 21.
- `target/jdk-matrix-demo-1.0.0.jar` được tạo.
- `main` in `Compatible: MAVEN=42` như trên.

`-B` là batch mode, `-ntp` tắt progress của các lần transfer. Đây không phải cờ chọn Java version. **Lệnh Maven vẫn cần đúng `JAVA_HOME`/toolchain ở môi trường trước khi chạy**.

### 6.6. Kiểm classfile target sau compile

JDK hỗ trợ `javap -verbose` để xem bytecode metadata:

~~~bash
javap -verbose target/classes/com/example/jdkmatrix/CompatibilityService.class
~~~

Trong output dài, tìm:

~~~text
major version: 61
~~~

**Major version 61 là Java 17 classfile**. Đây là expected result của `--release 17` cho class demo. JDK 21 tương ứng major version 65, nhưng không vì dùng JDK 21 để build mà class của project nhất thiết thành major 65.

Trên POSIX, có thể lọc:

~~~bash
javap -verbose target/classes/com/example/jdkmatrix/CompatibilityService.class | grep "major version"
~~~

Trên PowerShell:

~~~powershell
javap -verbose target/classes/com/example/jdkmatrix/CompatibilityService.class | Select-String "major version"
~~~

**Classfile major 61 không tự chứng minh runtime JDK 17 test pass**. Nó cho biết bytecode target; cần thực thi tests bằng JVM 17 riêng.

## 7. CI matrix: hai JDK, hai lần kiểm chứng độc lập

GitHub Actions có thể tạo một job cho mỗi phiên bản JDK. Với môi trường hiện hành, `actions/setup-java@v6` hỗ trợ `distribution: temurin` và `java-version` rõ ràng. Ví dụ ở `.github/workflows/jdk-matrix.yml`:

~~~yaml
name: Maven JDK matrix

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    name: Verify Temurin JDK ${{ matrix.java }}
    runs-on: ubuntu-latest

    strategy:
      fail-fast: false
      matrix:
        java: ['17', '21']

    steps:
      - name: Checkout source
        uses: actions/checkout@v7

      - name: Select requested JDK
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: maven

      - name: Show actual toolchain
        run: |
          echo "JAVA_HOME=$JAVA_HOME"
          java -version
          javac -version
          mvn -version

      - name: Verify Maven project on this JVM
        env:
          EXPECTED_JDK_FEATURE: ${{ matrix.java }}
        run: mvn -B -ntp clean verify
~~~

**Đây là workflow hoàn chỉnh cho demo** trong một repo GitHub Actions thông thường, giả sử repository có POM và source ở root, runner dùng được actions versions và Maven cài sẵn, artifact repositories truy cập được.

### 7.1. Tại sao cấu hình tường minh hơn một job chung?

- `matrix.java` có chính xác `'17'` và `'21'`.
- `setup-java` cài/chọn đúng **Temurin JDK** trong từng job.
- `JAVA_HOME`/`PATH` của job được thiết lập cho Maven launcher.
- `java -version`, `javac -version`, `mvn -version` cung cấp evidence độc lập.
- Test nhận `EXPECTED_JDK_FEATURE` theo matrix cell và assert đúng JVM thực tế.
- Mỗi cell chạy `mvn clean verify` riêng; không tái sử dụng output `target` của cell khác.
- `fail-fast: false` cho phép thu kết quả cả hai JDK ngay cả khi một job fail.
- Branch protection có thể yêu cầu mọi matrix job cần thiết đều pass.

Một matrix chỉ có job name “Java 21” mà không thiết lập Java trong job hoặc không assert JVM **không phải bằng chứng đủ mạnh**.

### 7.2. Cập nhật action versions và pin SHA

`setup-java@v6` và `checkout@v7` là các major action tags dùng trong ví dụ theo tài liệu hiện hành. Tổ chức có supply-chain controls nghiêm ngặt nên **pin immutable commit SHA** của actions đã được approve và cập nhật qua automated dependency review, thay vì tin một tag động.

Self-hosted runner phải hỗ trợ Node runtime mà phiên bản action yêu cầu; `setup-java@v6` dùng runtime action mới. Nếu runner cũ không tương thích, cập nhật runner/pin strategy theo policy, **không thay bằng action cũ thiếu support một cách mù quáng**.

### 7.3. Vì sao không dùng `java-version: latest`?

`latest` không tạo một matrix có mục tiêu kiểm chứng rõ ràng: nó thay đổi theo thời gian. Một job “latest” có thể hữu ích để **phát hiện tương thích tương lai**, nhưng không thay các jobs bắt buộc cho **minimum supported JDK 17** và JDK 21 đã công bố.

Khi cần thêm JDK 25:

~~~yaml
strategy:
  fail-fast: false
  matrix:
    java: ['17', '21', '25']
~~~

Đây là fragment thay cho phần `strategy` hiện tại, **không phải workflow thứ hai hoàn chỉnh**. Phải xác nhận dependencies/test tooling hỗ trợ JDK 25 và thời gian CI đủ. Có thể chạy JDK 25 ở lane advisory trước khi thành merge gate, rồi nâng policy sau khi ổn định.

### 7.4. Cache không phải bằng chứng đã test đủ

`cache: maven` làm Maven dependency cache nhanh hơn, không tự cache kết quả unit tests hay xác nhận runtime. Mỗi job vẫn phải chạy `verify`. Nếu nhìn thấy cache hit rồi skip tests, đó là vi phạm mục tiêu kiểm chứng.

Nếu dùng Maven Wrapper đã commit, thay dòng:

~~~yaml
run: mvn -B -ntp clean verify
~~~

bằng (trên Linux runner):

~~~yaml
run: ./mvnw -B -ntp clean verify
~~~

**Chỉ dùng `./mvnw` nếu repository thật có Maven Wrapper files và quyền thực thi phù hợp.** Bài lab này không cung cấp wrapper sẵn; lệnh chạy chuẩn là `mvn`.

## 8. Local JDK matrix không có CI: dùng từng môi trường riêng

Nếu cài cả JDK 17 và JDK 21 trên máy, có thể chạy lần lượt trong **hai terminal environments**. Cách đơn giản nhất là đặt `JAVA_HOME`, đặt đúng `bin` đầu `PATH`, kiểm `mvn -version`, rồi chạy `clean verify`.

POSIX shell minh họa (đường dẫn phải thay bằng JDK cài thật):

~~~bash
export JAVA_HOME="/opt/jdks/temurin-17"
export PATH="$JAVA_HOME/bin:$PATH"
export EXPECTED_JDK_FEATURE=17

java -version
javac -version
mvn -version
mvn -B -ntp clean verify
~~~

Để thử JDK 21, mở **terminal mới** hoặc thiết lập lại cả `JAVA_HOME` lẫn `PATH` một cách chắc chắn:

~~~bash
export JAVA_HOME="/opt/jdks/temurin-21"
export PATH="$JAVA_HOME/bin:$PATH"
export EXPECTED_JDK_FEATURE=21

java -version
javac -version
mvn -version
mvn -B -ntp clean verify
~~~

Những đường dẫn `/opt/jdks/...` chỉ là **ví dụ**, không phải path JDK mặc định trên mọi máy. Đừng copy nguyên nếu chưa cài JDK tại đó.

### 8.1. Trên Windows PowerShell

Với một JDK17 đã cài ở đường dẫn thực tế:

~~~powershell
$env:JAVA_HOME = "C:\jdks\temurin-17"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
$env:EXPECTED_JDK_FEATURE = "17"

java -version
javac -version
mvn -version
mvn -B -ntp clean verify
~~~

Để chạy JDK21, dùng **terminal mới**, thay `C:\jdks\temurin-21` và `EXPECTED_JDK_FEATURE="21"`; xác nhận `mvn -version` ngay trước build.

Không sửa cấu hình Java hệ thống của mọi ứng dụng chỉ để thử một Maven build. Dùng terminal riêng, IDE runner configuration, CI matrix hoặc Maven Toolchains tùy nhu cầu.

### 8.2. `JAVA_HOME` và PATH có thể lệch nhau

Nếu `JAVA_HOME` trỏ JDK17 nhưng `PATH` ưu tiên một JDK21 `java.exe`, `java -version` và Maven launcher có thể phản ánh JDK khác nhau. Trong Linux/macOS, shell có thể cache command path; trên Windows, thứ tự PATH/system launchers có thể gây bất ngờ.

Bằng chứng tối thiểu là cả `java -version`, `javac -version`, `mvn -version` và output test `TEST_JDK_FEATURE=...`.

## 9. Maven Toolchains: JDK dùng để compile có thể khác JDK chạy Maven

Maven Toolchains cho phép Maven chạy trên một JVM và những toolchain-aware plugins dùng **JDK được chỉ định riêng**.

Ví dụ:

~~~text
Maven process: JDK 21
  |
  +-- maven-toolchains-plugin selects JDK 17
  |
  +-- maven-compiler-plugin (aware): javac JDK 17
  |
  +-- maven-surefire-plugin (aware): test JVM JDK 17
  |
  +-- plugins không hỗ trợ toolchain: có thể tiếp tục trên Maven JVM 21
~~~

Điểm quan trọng: toolchain **không đổi JVM đang chạy Maven**; nó là lựa chọn cho các tools/plugins có hỗ trợ. `mvn -version` vẫn có thể báo Java 21 dù Compiler/Surefire dùng JDK17.

Maven Toolchains Plugin 3.3.0 có hai hướng:
- `toolchains:toolchain` chọn từ `toolchains.xml` theo requirements.
- `toolchains:select-jdk-toolchain` tự discovery JDKs theo cơ chế plugin và áp ràng buộc (có từ 3.2.0).

Không mọi plugin đều dùng toolchain. Với plugin chạy Java trong Maven JVM hoặc fork process khác, phải kiểm tài liệu plugin đó.

## 10. `toolchains.xml` tường minh theo từng máy

Ví dụ `${user.home}/.m2/toolchains.xml` (Linux; **sửa `jdkHome` thành thư mục có thật**):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-17</jdkHome>
        </configuration>
    </toolchain>

    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

`<provides>` là **metadata matching**, còn `<configuration><jdkHome>` là đường dẫn vật lý. Nếu `jdkHome` sai hoặc `bin/javac` không có, entry không tạo ra một JDK thật.

**Không commit `toolchains.xml` chứa absolute paths riêng của một developer** như một file bắt buộc cho tất cả máy. Trong repository có thể ghi yêu cầu version/vendor; mỗi môi trường cung cấp path bằng settings/toolchain provisioning.

### 10.1. Dùng version range để không nhầm 17 với 17.0.x

Trong `toolchains.xml`, metadata version có thể là `17`, `17.0.20` hoặc một dạng phiên bản đầy đủ. Khi toolchain requirement đặt một giá trị cụ thể `<version>17</version>`, matching có thể đòi **đúng chuỗi version** đã khai báo.

Để nhận cả Java 17.0.x, dùng range như:

~~~xml
<version>[17,18)</version>
~~~

Đối với Java 21:

~~~xml
<version>[21,22)</version>
~~~

Đây là **mảnh yêu cầu selection**, không phải toàn bộ `toolchains.xml`. Theo tài liệu Maven, `actions/setup-java` có thể ghi metadata toolchain version bằng chính chuỗi input `17` hoặc `21`, còn discovery tool đôi khi dùng đầy đủ patch version. Range giúp tương thích hai kiểu khai báo này.

**Vendor matching** là một ràng buộc khác và thường dùng exact string (không phải range); ví dụ `temurin` vs tên `java.vendor` do tool khác ghi có thể khác nhau. Nếu yêu cầu vendor mà không tìm thấy toolchain, kiểm metadata thực tế và policy trước khi nới rule.

## 11. Chọn JDK17 bằng Maven Toolchains Plugin 3.3.0

Nếu một build đang chạy Maven trên JDK21 nhưng muốn compiler và Surefire dùng JDK17, có thể thêm **fragment** sau vào `<build><plugins>` của POM:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.3.0</version>
    <executions>
        <execution>
            <id>select-java17</id>
            <phase>validate</phase>
            <goals>
                <goal>select-jdk-toolchain</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <version>[17,18)</version>
        <useJdk>Never</useJdk>
    </configuration>
</plugin>
~~~

**Đây là POM fragment tùy chọn, không nằm trong POM demo phần 6.** `select-jdk-toolchain` chọn JDK đúng version constraint từ các JDK được discovery; `useJdk=Never` yêu cầu chọn toolchain thay vì chỉ dùng JVM hiện tại khi phù hợp. Nếu không phát hiện JDK17, build phải báo lỗi thay vì âm thầm chọn JDK21.

Với cấu hình toolchain này, tests có thể **chạy trên JDK17 dù Maven process đang chạy trên JDK21**. Vì thế không dùng nó như giải pháp kiểm JDK21 runtime trong matrix JDK17/21 ở phần 7. Nếu muốn test JDK21 thực sự, phải bỏ/đổi toolchain hoặc cấu hình Surefire riêng.

### 11.1. Toolchain policy và CI matrix là hai mục tiêu khác nhau

- **Toolchain pin compile JDK17**: phục vụ reproducible compiler/tooling, không tự nói app chạy được trên JDK21.
- **CI matrix test JDK17 và 21**: phục vụ compatibility, cần đảm bảo mỗi test JVM đúng matrix cell.
- **`--release 17`**: phục vụ bytecode + Java API baseline.

Ba cơ chế có thể dùng cùng nhau, nhưng phải xác định rõ **JDK compile và JDK tests**. Nếu vô tình “pin JDK17 cho toàn build” trong một matrix mà đặt tên JDK21, người đọc tưởng đã chạy tests trên JDK21 trong khi tất cả jobs đều thử JDK17.

## 12. Compiler JDK17 nhưng Surefire test JVM21 trong một job

Một số trường hợp muốn **Maven chạy JDK21**, compiler dùng JDK17, còn tests dùng JDK21. Các plugin hỗ trợ JDK toolchains riêng:

~~~xml
<!-- Fragment đặt trong maven-compiler-plugin -->
<configuration>
    <release>17</release>
    <jdkToolchain>
        <version>[17,18)</version>
    </jdkToolchain>
</configuration>
~~~

~~~xml
<!-- Fragment đặt trong maven-surefire-plugin -->
<configuration>
    <forkCount>1</forkCount>
    <jdkToolchain>
        <version>[21,22)</version>
    </jdkToolchain>
</configuration>
~~~

**Đây là hai fragments riêng cho hai plugins**, không phải một POM XML hoàn chỉnh. Khi dùng cần JDK17/JDK21 thực sự có trên máy và được Maven toolchains resolve. `jdkToolchain` của một plugin có thể override toolchain chung do Toolchains Plugin chọn.

Chế độ này hữu ích cho:
- Kiểm compiler reproducibility trên JDK17.
- Test runtime behavior trên JVM21.
- Dự án cần chứng minh **bytecode 17 được JVM21 chạy**.

Nhưng **vẫn phải có một job test trên JVM17** nếu Java17 là minimum supported runtime. Test chỉ trên JVM21 chưa đủ.

### 12.1. Surefire `jvm` vs `jdkToolchain`

Surefire có option `jvm` để trỏ trực tiếp tới một Java executable. Cách đó dùng path máy cụ thể, khó tái hiện. `jdkToolchain` sử dụng matching metadata có thể tách khỏi absolute path, phù hợp môi trường nhiều JDK.

Nếu cấu hình cả `jvm` và `jdkToolchain`, phải đọc precedence theo Surefire version; theo tài liệu hiện hành, `jvm` có thể thắng. Tránh cấu hình hai phương pháp tranh nhau khi không cần.

## 13. JDK discovery và kiểm toolchains

Maven Toolchains Plugin có goals:

~~~bash
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains
~~~

Lệnh giúp xem các JDK plugin phát hiện theo cơ chế discovery. Nếu JDK bạn cài không hiện ra, kiểm JDK home, OS installation path, environment và cấu hình plugin.

Có thể tạo gợi ý toolchains XML từ JDK discovery:

~~~bash
mvn org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:generate-jdk-toolchains-xml
~~~

**Không tự copy output không kiểm tra** vào `~/.m2/toolchains.xml`: xem lại các JDK paths, versions và vendor tokens được phát hiện. Với CI, `actions/setup-java@v6` có thể tạo Maven toolchains entries cho JDK đã cài, nên nhiều dự án không cần viết file từ đầu bằng tay.

Dù plugin có cơ chế discovery, môi trường build phải **thực sự cài JDK** trước. Toolchains không tải JDK theo ý nghĩa một package manager tự động; các `javaHome`/metadata chỉ trỏ vào installed toolchains.

## 14. IDE: cửa sổ editor xanh không chứng minh CLI/CI xanh

Một IDE có thể cùng lúc dùng:
- JDK cho chính IDE runtime.
- Project SDK/JRE cho code model.
- Java language level cho editor/inspections.
- Maven importer JDK để tải model.
- Maven runner JDK để chạy Maven goals.
- JUnit run configuration JDK cho các tests chạy trực tiếp từ IDE.
- Compiler JDK/toolchain do Maven POM quy định.

Nếu editor báo Java 17 nhưng Maven runner dùng Java 21, CI vẫn có thể fail trên Java17. Nếu IDE test launcher dùng Java17 nhưng Maven Surefire được cấu hình chạy bằng toolchain21, hai lần thử không tương đương.

### 14.1. IntelliJ IDEA

Trong IntelliJ:
1. Kiểm **Project SDK** và language level.
2. Kiểm Maven **runner JRE/JDK** và Maven import/build settings.
3. Kiểm project đang delegate build/test cho Maven hay dùng IntelliJ compiler/test runner.
4. Kiểm **JUnit run configuration** dùng SDK nào.
5. Chạy Maven goals `clean verify` từ Maven tool window hoặc terminal với đúng Maven runner.
6. So log `mvn -version` và `TEST_JDK_FEATURE` trong Surefire reports.

Tên menu có thể thay đổi giữa các phiên bản IntelliJ; mục tiêu là đối chiếu **runtime cho từng thao tác**, không nhớ một đường dẫn menu cố định.

**Không sửa `maven.compiler.release` trong POM chỉ để làm editor hết gạch đỏ** nếu JDK SDK của IDE đang chọn sai. Sửa JDK installation/configuration tại IDE/máy, giữ baseline Java17 nếu đó là contract của project.

### 14.2. Eclipse / m2e

Trong Eclipse, kiểm:
- Installed JREs/JDKs và default JRE.
- Project Java Build Path và compiler compliance level.
- Maven run configuration JRE.
- m2e project configuration từ `pom.xml`.
- JUnit launch configuration khi dùng IDE runner.

m2e và Maven CLI có thể dùng Java environments khác. Khi kết quả khác nhau, chạy `mvn -version` trong terminal có cùng environment và đọc plugin logs để xác định JVM nào thật sự được dùng.

### 14.3. Visual Studio Code Java

VS Code Java extension có thể cấu hình installed JDK runtimes, ví dụ fragment `settings.json`:

~~~json
{
  "java.configuration.runtimes": [
    {
      "name": "JavaSE-17",
      "path": "/opt/jdks/temurin-17",
      "default": true
    },
    {
      "name": "JavaSE-21",
      "path": "/opt/jdks/temurin-21"
    }
  ]
}
~~~

Đây là **mảnh cấu hình editor**, các paths phải tồn tại. Nó không tự bảo đảm integrated terminal gọi Maven với cùng `JAVA_HOME`; terminal environment và Maven launcher cần được kiểm riêng. Nếu đã có Maven Toolchains/CI, giữ cấu hình POM là nguồn quy định target release, không để editor override policy.

## 15. Tại sao Enforcer vẫn hữu ích?

Một POM có `<maven.compiler.release>17</maven.compiler.release>` không ngăn Maven launcher chạy trên JDK rất cũ trước khi Compiler Plugin báo lỗi. Dự án có thể thêm **Maven Enforcer Plugin** để fail sớm khi Maven/JDK baseline không đạt.

Fragment đặt trong `<build><plugins>`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>enforce-build-environment</id>
            <phase>validate</phase>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <requireJavaVersion>
                        <version>[17,)</version>
                    </requireJavaVersion>
                    <requireMavenVersion>
                        <version>[3.9,)</version>
                    </requireMavenVersion>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

**Đây là tùy chọn bổ sung, không nằm trong POM lab**. Rule `requireJavaVersion` ở đây kiểm **JDK của Maven process**. Nó không tự chứng minh Surefire đang dùng JDK17/21, nhất là khi toolchain chọn JVM khác. Test assertion `Runtime.version().feature()` vẫn cần cho matrix.

`requireMavenVersion` giúp hạn chế Maven version quá cũ. Khi dự án dùng Maven Wrapper, nên pin Maven distribution và kiểm version trên CI. Rule Enforcer làm **fail fast** nhưng không tải JDK hoặc sửa PATH hộ developer.

## 16. Không đổi `maven.compiler.release` theo từng matrix cell nếu đang test compatibility

Một workflow dễ gây hiểu nhầm:

~~~yaml
# PHẢN VÍ DỤ cho việc kiểm tương thích cùng một artifact baseline:
matrix:
  java: ['17', '21']
~~~

và trong mỗi job lại chạy:

~~~bash
mvn -Dmaven.compiler.release=$JAVA_VERSION clean verify
~~~

Khi đó job17 tạo Java17 bytecode, job21 tạo Java21 bytecode. Bạn đã thử **hai compiler targets khác nhau**; điều này không trả lời câu hỏi “một artifact baseline Java17 có chạy trên Java21 không?” theo cách kiểm soát chặt.

Cách đúng cho demo:

~~~text
Maven POM baseline: release 17
JDK17 job: compile release17; tests JDK17
JDK21 job: compile release17; tests JDK21
~~~

Nếu muốn kiểm compiler output giống nhau tới từng byte, cần thêm reproducible-build comparison vì JDK compiler patch/vendor khác nhau có thể làm artifact bytes khác dù classfile target giống. **Matrix verify không tự chứng minh binary reproducibility tuyệt đối**.

Nếu dự án cố ý phát hành **multi-release JAR** hoặc các artifacts riêng theo JDK, đó là thiết kế khác: phải có packaging, classifiers, test matrix và versioning rõ ràng, không chỉ override `release` tùy hứng.

## 17. Tác động của dependencies: baseline Java17 chưa đủ

Một POM có Java release17 vẫn có thể kéo dependency mà class files được compile cho Java21. Lỗi có thể chỉ xảy ra khi class loader tải dependency:

~~~text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version
  of the Java Runtime
~~~

Vì vậy:
1. Kiểm `mvn dependency:tree`.
2. Xem Java compatibility notes của các third-party dependencies.
3. **Chạy JVM17** trong CI matrix, không chỉ compile trên JDK21 với `--release 17`.
4. Kiểm integration paths có tải các optional/transitive classes tương ứng.
5. Với SDK khách hàng, smoke test public APIs thật.
6. Theo dõi vendor/OS/architecture nếu thư viện dùng native components.

Một library chỉ được load ở production code path ít gặp có thể chưa bị unit tests chạm tới. Khi đó matrix đơn thuần vẫn thiếu coverage; bổ sung integration/smoke tests theo risk.

### 17.1. Test APIs cũ và mới

`--release` ngăn dùng JDK API vượt baseline, nhưng nó **không mô phỏng mọi behavior của JDK cũ**. Ví dụ TLS defaults, timezone data, locale, garbage collector behavior, security providers, module encapsulation, reflection và network stack có thể khác giữa versions. Vì vậy tests chạy trên JDK17/21 cần bao gồm các areas rủi ro, không chỉ unit test tính toán.

## 18. Plugin compatibility cũng phải được kiểm

Không phải plugin Maven nào cũng hỗ trợ mọi JDK/Maven version. Ví dụ:
- Surefire/JUnit provider phải hỗ trợ JDK và test engine tương ứng.
- JaCoCo instrumentation cần hỗ trợ classfile version mới.
- Compiler Plugin cần version hỗ trợ `maven.compiler.release`.
- Bytecode enhancement/proxy/serialization libraries có thể cần nâng version.
- Maven plugin chạy trong Maven JVM có thể yêu cầu Java tối thiểu riêng.

**Nếu job JDK21 fail vì Maven Plugin quá cũ**, đó vẫn là một kết quả CI quan trọng nhưng chưa chứng minh code application không tương thích. Phân loại lỗi toolchain/plugin trước khi sửa source.

Ở chiều ngược lại, **nâng plugin để JDK21 pass có thể phá Maven/JDK17 build** nếu plugin mới có runtime requirement cao. Pin versions và chạy lại toàn matrix khi thay đổi build tooling.

## 19. `mvn test`, `mvn verify` và unit/integration tests

Trong POM lab, Surefire chạy JUnit unit tests tại phase `test`. `mvn verify` bao gồm các phase trước đó nên có unit tests; dự án thực còn có thể cấu hình Failsafe integration tests ở `integration-test`/`verify`.

Cần ghi rõ matrix đang kiểm gì:

| Job | Unit tests | Integration tests | Cần bổ sung |
| --- | --- | --- | --- |
| JDK17 | Có theo POM demo | Không, chưa cấu hình | API/DB/framework smoke tests |
| JDK21 | Có theo POM demo | Không, chưa cấu hình | API/DB/framework smoke tests |
| JDK25 (tùy chọn) | Có sau mở matrix | Không mặc định | Review tools hỗ trợ JDK25 |

`mvn verify` **không tự tạo integration tests**. Nếu dự án cần kiểm database, HTTP server hay native lib trên nhiều JDK, phải thêm Failsafe/IT config và hạ tầng tương ứng.

Trong CI release, không dùng `-DskipTests` hoặc `-Dmaven.test.skip=true` rồi kết luận “đã kiểm trên JDK17 và 21”.

## 20. Matrix theo Java distribution và OS

Khi thư viện hỗ trợ nhiều vendor/OS, mở rộng matrix theo risk, ví dụ:

~~~yaml
strategy:
  fail-fast: false
  matrix:
    os: [ubuntu-latest, windows-latest]
    java: ['17', '21']
runs-on: ${{ matrix.os }}
~~~

**Đây là fragment cho một GitHub Actions job**, không thể chèn rời ngoài `jobs.<job>` mà chạy. Matrix trên tạo bốn tổ hợp khi cấu hình đúng trong job: 2 OS × 2 JDKs.

Bạn cũng có thể mở thêm `distribution: ['temurin','zulu']` khi có lý do; phải kiểm hỗ trợ JDK/version/architecture và giới hạn CI cost. Không bắt mọi dự án nhỏ chạy mọi JDK × OS × vendor × architecture vô hạn. Bắt đầu với minimum supported JDK và runtime mục tiêu production, rồi mở rộng theo failure modes đã biết.

## 21. Kiểm báo cáo JUnit theo từng matrix cell

Surefire sinh báo cáo ở:

~~~text
target/surefire-reports/
    com.example.jdkmatrix.CompatibilityServiceTest.txt
    TEST-com.example.jdkmatrix.CompatibilityServiceTest.xml
~~~

Với demo kỳ vọng 3 test methods. Dấu hiệu tốt:
- Job17: `mvn -version` báo JVM17 và JUnit in `TEST_JDK_FEATURE=17`.
- Job21: `mvn -version` báo JVM21 và JUnit in `TEST_JDK_FEATURE=21`.
- Mỗi job trả `BUILD SUCCESS`.
- Không có tests skipped, fails hoặc errors ngoài policy.
- `maven.compiler.release=17` ở cả hai jobs.

Không lấy một file JUnit XML từ job17 rồi upload chung với job21 mà không gắn nhãn JDK. Nếu lưu CI artifacts/report, đặt tên theo matrix cell để không ghi đè hoặc gộp sai nguồn.

### 21.1. Test output trong JUnit XML

Surefire có thể thu `System.out` từ tests vào `.txt` hoặc XML reports theo cấu hình. `TEST_JDK_FEATURE` là log phụ trợ; bằng chứng mạnh nhất là **assertion** trong `testJvmMatchesDeclaredMatrixCell()` kết hợp job status và CI configuration.

Một job name `JDK21` không đủ nếu biến `EXPECTED_JDK_FEATURE` chưa được truyền đúng; test được thiết kế fail khi giá trị được truyền mà JVM thực khác.

## 22. Mismatch thường gặp trong IDE

| Hiện tượng | Nguyên nhân có thể | Cách xác minh/sửa |
| --- | --- | --- |
| IDE editor báo Java17 nhưng Maven compile báo API unavailable | `release=17`, code dùng API21 | Giữ contract hoặc nâng baseline có review |
| IDE run pass, terminal Maven fail | IDE JDK hoặc Maven runner JDK khác terminal | `mvn -version`, run config, JAVA_HOME |
| Maven compile pass, JUnit test JVM fail `UnsupportedClassVersionError` | Test JVM thấp hơn classfile target | Xem Surefire JVM/toolchain, javap |
| Chọn Project SDK21 nhưng production yêu cầu17 | IDE SDK không là runtime compatibility proof | CI chạy tests JDK17 |
| VS Code Java extension báo21, terminal báo17 | Editor runtimes khác terminal PATH | Kiểm VS Code config và shell env |
| Eclipse compliance17 nhưng Maven plugin target21 | IDE/m2e và POM khác cấu hình | Xem effective POM và Maven goals |
| `JAVA_HOME` đúng nhưng `java -version` sai | PATH ưu tiên JDK khác | Sửa PATH và kiểm binaries |
| `mvn -version` báo21 nhưng Surefire test báo17 | Toolchains hoặc Surefire jdkToolchain | Xem plugin configs, test log |
| `mvn -version` báo17 nhưng javac dùng21 | Compiler toolchain/fork config | Xem Compiler Plugin logs |
| Chạy debug IDE pass nhưng Surefire fail | IDE JUnit runner khác Surefire provider/flags | So JUnit version, JVM args, profiles |
| Maven toolchains không thấy JDK | Sai `jdkHome`/version metadata/vendor | Display discovered JDKs, kiểm installed paths |
| Local pass, GitHub Actions fail | CI pin tool versions/OS khác hoặc env thiếu | Xem per-job Java/JDK/Maven logs |

**Không khắc phục mọi mismatch bằng cách thay `maven.compiler.release` thành 21**. Đó là thay đổi public compatibility contract; cần decision và tests riêng.

## 23. Những lỗi kỹ thuật theo phiên bản JDK

### 23.1. `invalid target release: 21`

Nguyên nhân phổ biến: JDK đang compile là 17, nhưng POM đặt `release=21`. Giải pháp: dùng compiler JDK21 nếu project **thật sự** cần Java21, hoặc hạ target về17 nếu contract cần Java17 (đồng thời sửa code dùng API21).

Không thể buộc `javac` của JDK17 biên dịch Java21 code bằng một Maven property kỳ diệu.

### 23.2. `release version 17 not supported`

Compiler JDK quá cũ, toolchain không đúng hoặc compiler backend không hỗ trợ release17. Kiểm `mvn -version`, toolchain log, `javac -version`, Compiler Plugin config.

### 23.3. `UnsupportedClassVersionError`

Runtime JVM đang cố load bytecode có classfile version cao hơn nó hỗ trợ. Ví dụ Java17 (major61) không load được Java21 class (major65). Kiểm **class gây lỗi** có phải app code hay transitive dependency; `javap -verbose` trên class/JAR liên quan.

### 23.4. `No compiler is provided in this environment`

Maven đang dùng JRE hoặc toolchain không có javac. Chọn JDK, thiết lập JAVA_HOME/CI image, không chỉ Java runtime.

### 23.5. `No toolchain matched`

POM yêu cầu version/vendor không có trong installed/discovered JDKs hoặc `toolchains.xml` metadata không khớp. Kiểm range `[17,18)`, JDKHome, vendor string, quyền truy cập JDK. Không silently bỏ ràng buộc chỉ để pipeline xanh.

### 23.6. JDK21 job pass nhưng Java17 production fail

Nguyên nhân có thể: tests chỉ thực thi trên21, external dependency compiled cho21, plugin packaging tạo wrong bytecode hoặc Java17-specific runtime path chưa được test. Cần job Java17 bắt buộc với integration/smoke tests trên actual artifact.

### 23.7. `JAVA_HOME` sai trên Windows

Nếu `JAVA_HOME` có path tới `bin` thay vì JDK root, Maven launcher có thể tìm sai Java. `JAVA_HOME` phải là **thư mục gốc JDK** (nơi có `bin/java`, `bin/javac`), và PATH cần ưu tiên `JAVA_HOME\bin`.

### 23.8. CI reports ghi sai Java version

Kiểm `setup-java` step version/distribution, PATH, Maven runner, Surefire toolchain. Không dựa vào matrix job name; dùng runtime assertion để fail tự động.

## 24. Trường hợp chủ động nâng Java baseline từ 17 lên 21

Đổi baseline là **quyết định sản phẩm**, không chỉ cập nhật compiler plugin.

Một quy trình có trách nhiệm:

1. Xác định consumers/production đang ở JDK nào.
2. Kiểm thư viện/dependencies/frameworks có chính thức hỗ trợ Java21.
3. Thảo luận tác động SDK/public APIs và runtime requirement.
4. Cập nhật POM `maven.compiler.release` từ17 lên21.
5. Cập nhật toolchain/compiler JDK, IDE setup và CI image.
6. Thay matrix mandatory: bỏ JDK17 **chỉ sau khi** minimum supported runtime được nâng chính thức.
7. Chạy unit/integration/security/smoke tests trên21 và phiên bản mới hơn dự định hỗ trợ.
8. Cập nhật tài liệu release, container base images, deployment charts và compatibility statements.
9. Kiểm compiler/annotation processors/bytecode agents/Surefire/JaCoCo tương thích.
10. Publish release có thông báo breaking compatibility rõ khi cần.

Không hạ ngầm minimum JDK support chỉ vì developer đã chuyển IDE sang JDK21.

### 24.1. Nếu chỉ muốn thử JDK mới hơn

Giữ `release=17`, thêm JDK21 hoặc25 vào matrix. Điều này kiểm JVM runtime compatibility mà **không** nâng Java language/API baseline của artifact. Đây thường là bước đầu an toàn.

## 25. Dự án nhiều module: matrix ở Reactor level

Với multi-module project:

~~~text
root/pom.xml  (packaging=pom)
├── api/
├── core/
├── adapter/
└── application/
~~~

CI matrix nên chạy **root `mvn clean verify`** để Maven Reactor build các modules đúng thứ tự và thực hiện tests trong từng module.

Cần lưu ý:
- Parent POM có thể quản lý `maven.compiler.release` và plugin versions cho child.
- Child override compiler release/toolchain có thể làm một module sinh bytecode cao hơn baseline.
- Một root build thành công không đảm bảo mọi module có tests; kiểm per-module Surefire reports.
- Reactor aggregation không đồng nghĩa tất cả modules có cùng Java runtime requirement; policy phải định nghĩa ngoại lệ.
- Nếu Java17 là minimum supported cho toàn thư viện public, phải kiểm riêng những module được xuất bản cho clients.
- Các plugin chỉ có execution trong `pluginManagement` không tự chạy nếu không có actual plugin/lifecycle binding tương ứng.

Nếu muốn một module cần Java21 trong cùng monorepo, không ép toàn Reactor chạy một matrix chung như thể tất cả artifacts hỗ trợ17; ghi contract theo module và chọn matrix/subprojects phù hợp.

## 26. Không nhầm runtime compatibility với reproducible bytes

Có ba yêu cầu khác nhau:

1. **Source portability:** code compile cho release17.
2. **Runtime compatibility:** compiled code/dependencies chạy đúng trên JVM17/21.
3. **Reproducible build:** cùng inputs và toolchains cho binary bytes/metadata giống nhau.

CI matrix chứng minh từng job **đã được build/test theo phiên bản đã đặt**, không tự chứng minh artifact JAR byte-for-byte identical giữa JDK17 và21.

JDK compiler, file ordering, timestamps, generated sources, annotation processors hoặc plugin versions có thể tác động bytes. Nếu tổ chức cần reproducible builds, cần pin thêm:
- Maven/JDK vendor/patch version hoặc validated toolchain.
- Plugin/dependency versions và repository state.
- Archive timestamps (`project.build.outputTimestamp`) khi thích hợp.
- Environment variables, locale, timezone.
- Generated code/toolchain versions.
- Checksum comparison cho cùng artifact input.

**Reproducibility và compatibility bổ trợ nhau**, không thể thay thế.

## 27. Checklist kiểm chứng cho một pull request

1. POM khai báo baseline Java rõ, ví dụ `<maven.compiler.release>17</maven.compiler.release>`.
2. Compiler/Surefire/JUnit/packaging plugin versions được pin.
3. `mvn -version` cho biết JVM Maven process.
4. `java -version` và `javac -version` được ghi từ cùng CI job.
5. Maven JVM và compiler JDK không bị giả định là một khi dùng Toolchains.
6. Surefire JVM được kiểm bằng một assertion chạy trong forked test process.
7. Job JDK17 thực sự có JDK17 và đủ test methods chạy.
8. Job JDK21 thực sự có JDK21 và đủ test methods chạy.
9. `EXPECTED_JDK_FEATURE` được truyền theo matrix cell, không hardcode 17 cho mọi job.
10. CI dùng `fail-fast:false` nếu cần thấy đầy đủ kết quả cả matrix.
11. Không thay `maven.compiler.release` giữa các jobs khi mục tiêu là compatibility một baseline.
12. Không skip tests trong required matrix checks.
13. Kiểm bytecode major version nếu phát hiện classfile mismatch.
14. Kiểm `dependency:tree` và Java compatibility của external libs.
15. IDE Project SDK, Maven runner, test runner được đối chiếu với CLI.
16. Không commit `toolchains.xml` có absolute paths cá nhân làm quy định chung.
17. Toolchain version range được chọn đúng metadata, ví dụ `[17,18)`.
18. Không để plugin JDK requirement phá minimum supported build.
19. Chạy root Reactor verify nếu project có nhiều modules.
20. Kiểm các modules có test reports thay vì chỉ nhìn root `BUILD SUCCESS`.
21. Có integration/smoke tests cho code paths quan trọng trên JVM tối thiểu.
22. Pin CI actions theo chính sách supply-chain, cân nhắc immutable SHAs.
23. Không dùng `latest` thay cho phiên bản JDK chính thức được hỗ trợ.
24. Khi thêm JDK25, xác minh dependencies/plugins/frameworks trước khi bật required gate.
25. Tách runtime compatibility khỏi production deployment và reproducibility claims.
26. Lưu test reports theo từng job Java version, không ghi đè.
27. Không sửa POM để “làm IDE xanh” nếu contract đang đúng mà IDE sai JDK.
28. Có hướng dẫn developers chọn JAVA_HOME, PATH và Maven runner.
29. Khi nâng minimum JDK, cập nhật API support policy và release notes.
30. Chỉ kết luận “đã xác minh JDK17 và21” khi hai jobs đều chạy tests thật và pass.

## 28. Bài tập tự kiểm tra

**Câu 1.** POM `maven.compiler.release=17` có chắc chắn Surefire chạy trên JDK17 không?

**Đáp:** Không. Nó cấu hình compiler target; Surefire JVM phụ thuộc environment/toolchain/`jdkToolchain`.

**Câu 2.** `mvn -version` cho biết gì?

**Đáp:** Maven version và JVM hiện đang chạy Maven process. Nó không nhất thiết cho biết compiler/test JVM khi dùng toolchains.

**Câu 3.** Tại sao phải có job JDK17 nếu artifact nhắm Java17?

**Đáp:** Để thực thi tests trên minimum supported runtime, kiểm external dependencies và runtime behavior trên JVM17 thật.

**Câu 4.** JDK21 compile với `--release 17` tạo class major nào?

**Đáp:** Major61 cho Java17, nếu compiler/toolchain hỗ trợ cấu hình đúng.

**Câu 5.** JDK17 có compile được Java21 code bằng `--release 21` không?

**Đáp:** Không. Compiler JDK17 không hỗ trợ target release21.

**Câu 6.** Vì sao `--release` tốt hơn `-source`/`-target` khi build trên JDK mới cho Java cũ?

**Đáp:** Nó ràng buộc cả Java SE public APIs của target release, không chỉ cú pháp/bytecode.

**Câu 7.** `EXPECTED_JDK_FEATURE` trong demo do Maven tự sinh không?

**Đáp:** Không. CI hoặc developer environment cấp nó; test đọc `System.getenv`.

**Câu 8.** Job matrix tên Java21 nhưng test log `TEST_JDK_FEATURE=17` có pass đúng không?

**Đáp:** Không nếu expected env được truyền: assertion sẽ fail vì JDK test thực khác matrix cell.

**Câu 9.** `toolchains.xml` có tự cài JDK không?

**Đáp:** Không. Nó mô tả installed JDKs và paths; JDK phải tồn tại.

**Câu 10.** `select-jdk-toolchain` chọn JDK17 trong một job Maven JDK21 có làm job đó thành runtime test JDK21 không?

**Đáp:** Không; nếu Surefire dùng toolchain chung, nó có thể chạy JVM17. Kiểm bằng test JVM assertion.

**Câu 11.** Vì sao `[17,18)` thường tốt hơn yêu cầu `17` trong toolchain selection?

**Đáp:** Nó có thể match cả metadata `17` và full patch `17.0.x` thay vì đòi chuỗi bằng chính xác.

**Câu 12.** IDE language level17 có chứng minh `mvn verify` dùng JDK17 không?

**Đáp:** Không. Maven runner và test launcher của IDE có cấu hình riêng.

**Câu 13.** Nếu build JDK21 và test JVM21 pass, có thể khẳng định Java17 runtime tương thích chưa?

**Đáp:** Chưa. Cần run tests trên JVM17 và kiểm dependencies/runtime paths.

**Câu 14.** Hai jobs trả JAR khác checksum có nghĩa code không tương thích?

**Đáp:** Không tự động. Binary reproducibility khác runtime behavior; cần điều tra compiler timestamps và các inputs.

**Câu 15.** `mvn verify` có tự tạo integration tests không?

**Đáp:** Không. Phải cấu hình Failsafe/IT suite nếu dự án cần.

**Câu 16.** `UnsupportedClassVersionError` có thể do dependency chứ không chỉ code của mình không?

**Đáp:** Có. Phải xác định class gây lỗi và bytecode major target của nó.

**Câu 17.** Khi thêm JDK25 vào matrix, có nên bỏ JDK17 vì 25 mới hơn không?

**Đáp:** Không khi Java17 vẫn là minimum supported runtime.

**Câu 18.** `forkCount=1` có nghĩa hai matrix jobs cùng một JVM không?

**Đáp:** Không. Mỗi job độc lập, Surefire trong từng job dùng fork JVM được môi trường/toolchain chọn.

**Câu 19.** Enforcer `requireJavaVersion` kiểm JVM nào?

**Đáp:** JVM đang chạy Maven, không thay cho kiểm Surefire JVM trong toolchains setup.

**Câu 20.** Cấu hình tốt nhất để chứng minh JDK17/21 là gì?

**Đáp:** Baseline `release=17`, matrix JDK17/21 rõ ràng, log Maven/Java/javac versions, Surefire test assertion đối chiếu expected JVM và verify thành công trong từng cell.

## 29. Tài liệu tham khảo chính thức

- [Apache Maven — Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Apache Maven Toolchains Plugin — Introduction](https://maven.apache.org/plugins/maven-toolchains-plugin/)
- [Apache Maven Toolchains Plugin — select-jdk-toolchain](https://maven.apache.org/plugins/maven-toolchains-plugin/select-jdk-toolchain-mojo.html)
- [Apache Maven Toolchains Plugin — JDK Discovery](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk-discovery.html)
- [Apache Maven Toolchains Plugin — JDK Toolchain XML](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk.html)
- [Apache Maven Compiler Plugin — Setting --release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Apache Maven Compiler Plugin — Compiling with a Different JDK](https://maven.apache.org/plugins/maven-compiler-plugin/examples/compile-using-different-jdk.html)
- [Apache Maven Surefire Plugin — Toolchains](https://maven.apache.org/surefire/maven-surefire-plugin/examples/toolchains.html)
- [Apache Maven Surefire Plugin — test Goal Parameters](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Apache Maven Enforcer — Java Version Range](https://maven.apache.org/enforcer/enforcer-rules/versionRanges.html)
- [GitHub Actions — actions/setup-java](https://github.com/actions/setup-java)
- [GitHub Actions — Multiple Java Versions and Matrix](https://github.com/actions/setup-java#testing-with-a-java-matrix)
- [GitHub Actions — actions/checkout](https://github.com/actions/checkout)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [JUnit 5 — User Guide](https://docs.junit.org/5.11.4/user-guide/)

