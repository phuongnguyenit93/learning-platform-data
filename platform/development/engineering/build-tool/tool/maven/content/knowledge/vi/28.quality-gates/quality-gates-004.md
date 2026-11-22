# Tích hợp kiểm tra định dạng và quy tắc mã nguồn bằng plugin trong Maven

## 1. Vì sao cần cổng chất lượng mã nguồn ngay trong build?

Một ứng dụng Java có thể **biên dịch được, unit tests đều xanh**, nhưng mã nguồn vẫn chứa nhiều vấn đề làm chi phí bảo trì tăng: định dạng khác nhau giữa thành viên, import dạng wildcard, tên phương thức khó hiểu, thiếu dấu ngoặc ở nhánh điều kiện hoặc những mẫu code dễ gây bug.

Trong Maven, một **cổng chất lượng (quality gate)** là bước kiểm tra được cấu hình để **trả mã thoát khác 0 và làm build thất bại khi vi phạm một chính sách đã công bố**. Khi gắn goal kiểm tra vào Maven lifecycle, cùng một quy tắc có thể chạy ở máy lập trình viên lẫn CI thay vì phụ thuộc vào thiết lập riêng của từng IDE.

Ba loại kiểm tra dễ bị nhầm:

1. **Formatting**: đặt dấu cách, xuống dòng, thụt lề, cách sắp xếp import... theo một chuẩn thống nhất. Phần lớn có thể **tự sửa**.
2. **Code style / conventions**: đặt tên, dấu ngoặc, cách import và những quy tắc cấu trúc. Nhiều vi phạm cần người viết **chủ động sửa code**, không phải đổi whitespace.
3. **Static code analysis**: tìm những mẫu code có nguy cơ bug, độ phức tạp, duplication hoặc vấn đề thiết kế. Không thay thế compiler, tests, review hay security audit.

Bài học này sử dụng **Spotless Maven Plugin** để chuẩn hóa định dạng Java và **Maven Checkstyle Plugin** để kiểm tra quy tắc mã nguồn, đồng thời giới thiệu **Maven PMD Plugin** như một tầng kiểm tra bổ sung. Ví dụ chính dùng **Java 17 + JUnit 5**, với POM và file cấu hình đầy đủ, sau đó thực hành sửa lỗi và tích hợp CI.

## 2. Phân vai plugin và hành vi build

| Công cụ | Trọng tâm | Goal điển hình | Có tự sửa source? | Có thể chặn build? |
| --- | --- | --- | --- | --- |
| Spotless Maven Plugin | Formatting Java, POM, văn bản và file khác được chọn | `spotless:check`, `spotless:apply` | **Có**, khi gọi `apply` | Có, qua `check` |
| Maven Checkstyle Plugin | Quy tắc Java source/style theo XML ruleset | `checkstyle:check` | **Không** tự rewrite Java trong goal `check` | Có |
| Maven PMD Plugin | Static analysis dựa trên ruleset | `pmd:check`, `pmd:cpd-check` | Không phải trình format tự động | Có |
| Maven Compiler Plugin | Java syntax/type correctness và bytecode | `compiler:compile` | Không | Có khi compile lỗi |
| Maven Surefire Plugin | Chạy unit tests | `surefire:test` | Không | Có nếu test fail theo config |

**Spotless `apply` và Spotless `check` không tương đương:**
- `mvn spotless:apply`: **có thể sửa trực tiếp file mã nguồn** để khớp formatter.
- `mvn spotless:check`: **kiểm tra**, báo lỗi nếu các file cần đổi; không chủ động chuẩn hóa file thay người viết.
- `mvn checkstyle:check`: đọc mã, áp ruleset và có thể fail build. Nó **không tự thêm ngoặc hay đổi tên phương thức**.
- `mvn pmd:check`: kiểm tra các vi phạm PMD theo reports/ruleset; không thay nhiệm vụ formatter.

**Khuyến nghị workflow:** developer có thể chạy `spotless:apply` trước khi commit, nhưng **CI nên chạy `spotless:check` + `checkstyle:check` ở chế độ không tự sửa**. CI cần phát hiện sự khác biệt, không âm thầm thay mã nguồn rồi báo xanh.

## 3. Maven lifecycle: gắn quy tắc vào phase nào?

Các phase thường gặp:

```text
validate
   |
compile
   |
test                  -> Surefire chạy unit tests
   |
package               -> tạo JAR
   |
verify                -> Spotless check + Checkstyle check (nếu đã bind)
   |
install
   |
deploy
```

Đây là **sơ đồ rút gọn**, không phải toàn bộ default lifecycle. Trong ví dụ chính, chúng ta bind cả hai quality-check goals vào **`verify`**. Vì vậy:

| Lệnh | Kết quả đối với ví dụ |
| --- | --- |
| `mvn spotless:apply` | Format lại những Java source được chọn; không cần đi qua toàn lifecycle |
| `mvn spotless:check` | Chạy trực tiếp kiểm tra formatting |
| `mvn checkstyle:check` | Chạy trực tiếp kiểm tra Checkstyle |
| `mvn test` | Chạy đến `test`; **chưa** kích hoạt hai execution gắn `verify` |
| `mvn package` | Đóng gói nhưng **chưa** chạy hai execution ở `verify` |
| `mvn verify` | Đi qua compile, unit tests, package rồi chạy quality checks |
| `mvn clean verify` | Xóa output cũ theo clean lifecycle rồi xây và kiểm tra đầy đủ |

Một số team gắn Checkstyle ở `validate` để **fail fast** trước khi compile. Điều này hợp lệ nhưng code bị lỗi cú pháp có thể tạo thông báo parsing khác compiler. Gắn ở `verify` giúp compiler/tests chạy trước, đổi lại developer phải gọi `verify` thay vì chỉ `test` để thấy lỗi style.

**Một plugin có tên trong `<build><plugins>` không tự bảo đảm mọi goal của nó chạy khi gõ `mvn verify`.** Phải có **execution** bind goal phù hợp, trừ những goal đã được packaging/lifecycle bind theo mặc định. Bài này viết `<phase>verify</phase>` tường minh, giúp người mới dễ kiểm tra.

## 4. Quy tắc minh họa của bài thực hành

Chúng ta chọn bộ quy tắc nhỏ, đủ phân biệt formatter và linter:

**Spotless / google-java-format**
- Áp dụng cho `src/main/java` và `src/test/java`;
- Chuẩn hóa format Java theo Google Java Format;
- Chốt phiên bản formatter để máy developer và CI dùng cùng hành vi;
- Không kiểm tra chất lượng business logic.

**Checkstyle**
- `AvoidStarImport`: không dùng import wildcard như `import java.util.*;`;
- `TypeName`: tên kiểu/lớp tuân thủ quy tắc đặt tên kiểu Java;
- `MethodName`: tên phương thức tuân thủ quy tắc;
- `NeedBraces`: yêu cầu dấu ngoặc nhọn cho những câu lệnh điều khiển được rule kiểm tra.

Checkstyle không có nhiệm vụ bảo đảm tất cả code đều “đẹp” hoặc không có bug. Một class có tên đúng vẫn có thể chứa thuật toán sai; một class đã format theo Google Java Format vẫn có thể có một method quá phức tạp.

Chọn ruleset có chủ đích giúp demo **tránh mâu thuẫn không cần thiết** giữa formatter và rule về vị trí khoảng trắng. Trong dự án thật, hãy review Checkstyle rules song song với formatter. Khi hai công cụ cùng kiểm soát indentation/line wraps nhưng có chuẩn khác nhau, chúng có thể khiến developer sửa qua lại vô tận.

## 5. Bài thực hành hoàn chỉnh Java 17

### 5.1. Cấu trúc file

```text
style-gates-demo/
├── pom.xml
├── config/
│   └── checkstyle/
│       └── checkstyle.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/quality/
    │           └── GreetingApp.java
    └── test/
        └── java/
            └── com/example/quality/
                └── GreetingAppTest.java
```

Có ba điểm cần lưu ý:
1. `pom.xml` ở root khai báo plugin và versions.
2. `config/checkstyle/checkstyle.xml` là **file quy tắc do chính project quản lý**, không phải một file được Maven tự tạo.
3. Hai file Java có `package com.example.quality;` phù hợp đường dẫn `com/example/quality/` trong các source roots mặc định.

Yêu cầu:
- **JDK 17+** cho ví dụ;
- bản Maven tương thích với các plugin đã chọn (Maven 3.9.x là lựa chọn tham khảo phù hợp);
- repository/mirror có thể cung cấp Maven plugins, JUnit và google-java-format nếu chưa cache.

### 5.2. File pom.xml đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>style-gates-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
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
                <version>3.14.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>

            <plugin>
                <groupId>com.diffplug.spotless</groupId>
                <artifactId>spotless-maven-plugin</artifactId>
                <version>2.46.1</version>
                <configuration>
                    <java>
                        <includes>
                            <include>src/main/java/**/*.java</include>
                            <include>src/test/java/**/*.java</include>
                        </includes>
                        <googleJavaFormat>
                            <version>1.24.0</version>
                            <style>GOOGLE</style>
                        </googleJavaFormat>
                    </java>
                </configuration>
                <executions>
                    <execution>
                        <id>check-java-format</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>check</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-checkstyle-plugin</artifactId>
                <version>3.6.0</version>
                <configuration>
                    <configLocation>config/checkstyle/checkstyle.xml</configLocation>
                    <encoding>UTF-8</encoding>
                    <consoleOutput>true</consoleOutput>
                    <failOnViolation>true</failOnViolation>
                    <includeTestSourceDirectory>true</includeTestSourceDirectory>
                    <includeResources>false</includeResources>
                    <includeTestResources>false</includeTestResources>
                </configuration>
                <executions>
                    <execution>
                        <id>check-java-rules</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>check</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là **một POM độc lập và hoàn chỉnh**; không thêm các fragments khác của bài vào nó nếu chỉ muốn chạy ví dụ cơ bản.

**Phân tích theo từng khối:**

- `project.build.sourceEncoding=UTF-8`: chốt charset chung cho build.
- `maven.compiler.release=17`: biên dịch Java theo release 17 khi Maven dùng toolchain/JDK hỗ trợ.
- JUnit Jupiter dependency có `scope=test`: cho test compilation/execution, không vào classpath runtime của chương trình.
- Surefire Plugin 3.5.4 hỗ trợ chạy JUnit Jupiter tests có tên phù hợp.
- Spotless Plugin 2.46.1 chỉ target hai source trees Java trong cấu hình đã chọn. Goal `check` bind ở phase `verify`.
- `googleJavaFormat` dùng phiên bản `1.24.0` và style `GOOGLE`; **chính version formatter cũng cần được ghim**, không chỉ version Maven plugin.
- Checkstyle Plugin 3.6.0 đọc file `config/checkstyle/checkstyle.xml`, bật kiểm tra test source và đặt `failOnViolation=true`.
- `includeResources=false` và `includeTestResources=false` giúp ví dụ tập trung vào Java code; không quét tài nguyên text ngoài mục đích.
- Cả hai plugin khai báo `<executions>` thật trong `<build><plugins>`, vì vậy `mvn verify` có thể trở thành quality gate.

**Không có bước tự format khi CI chạy `verify`.** Chỉ Spotless `check` được bind vào lifecycle, không phải `apply`. Điều này bảo toàn nguyên trạng checkout của CI và khiến vi phạm có thể được sửa/chốt ở commit tiếp theo.

### 5.3. File config/checkstyle/checkstyle.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE module PUBLIC
    "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
    "https://checkstyle.org/dtds/configuration_1_3.dtd">
<module name="Checker">
    <property name="charset" value="UTF-8"/>

    <module name="TreeWalker">
        <module name="AvoidStarImport"/>
        <module name="TypeName"/>
        <module name="MethodName"/>
        <module name="NeedBraces"/>
    </module>
</module>
```

Đây là **file Checkstyle XML đầy đủ**, riêng biệt với POM. Nó có:
- Root `Checker`: module cấu hình chính.
- `TreeWalker`: duyệt cú pháp Java và áp những quy tắc tương ứng.
- `AvoidStarImport`: không chấp nhận `java.util.*` theo cách dùng import wildcard.
- `TypeName`, `MethodName`: quy tắc đặt tên.
- `NeedBraces`: yêu cầu braces đối với các control statements mà rule hỗ trợ.

**Đừng chép Checkstyle XML vào POM** như một `<plugin>` mới. Trước tiên tạo đúng đường dẫn `config/checkstyle/checkstyle.xml`, sau đó `configLocation` ở POM trỏ tới file này.

Nếu team muốn dùng ruleset chuẩn có sẵn, Maven Checkstyle Plugin cũng cung cấp `sun_checks.xml` và `google_checks.xml`. Đó là các **bộ quy tắc nhiều hơn và chặt hơn**, có thể khiến ví dụ nhỏ không đáp ứng ngay nếu copy nguyên xi. Bài này chủ động chọn custom ruleset tối thiểu để thể hiện cơ chế.

### 5.4. File src/main/java/com/example/quality/GreetingApp.java

```java
package com.example.quality;

public final class GreetingApp {
  private GreetingApp() {}

  public static String greeting(String name) {
    if (name == null || name.isBlank()) {
      return "Hello, friend!";
    }
    return "Hello, " + name.strip() + "!";
  }

  public static void main(String[] args) {
    System.out.println(greeting(" Maven "));
    System.out.println(greeting(" "));
  }
}
```

Đây là Java 17 hoàn chỉnh. `String.isBlank()` và `String.strip()` có từ Java 11, nên hoạt động với release 17. Các method tuân thủ cách đặt tên lower camel case và mọi `if` đều có braces.

Kết quả:
- `greeting(" Maven ")` trả `Hello, Maven!`;
- `greeting(" ")` trả `Hello, friend!`;
- `greeting(null)` cũng trả `Hello, friend!`.

**Google Java Format** có thể điều chỉnh whitespace/import layout mà không đổi behavior Java. Vì cùng một formatter version được ghim, developer và CI có cùng chuẩn để đối chiếu.

### 5.5. File src/test/java/com/example/quality/GreetingAppTest.java

```java
package com.example.quality;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class GreetingAppTest {
  @Test
  void trimsInput() {
    assertEquals("Hello, Maven!", GreetingApp.greeting(" Maven "));
  }

  @Test
  void returnsFallbackForBlank() {
    assertEquals("Hello, friend!", GreetingApp.greeting(" "));
  }

  @Test
  void returnsFallbackForNull() {
    assertEquals("Hello, friend!", GreetingApp.greeting(null));
  }
}
```

Đây là JUnit Jupiter test compilable với **3 test methods**. File có hậu tố `Test.java` nên được Surefire nhận diện theo mặc định. `assertEquals` là static import cụ thể, **không dùng wildcard**.

Test methods có tên lower camel case, phù hợp `MethodName`. Test source cũng được Spotless quét vì cấu hình `<includes>` chứa `src/test/java/...`, và được Checkstyle quét vì `includeTestSourceDirectory=true`.

### 5.6. Chạy từ thư mục root

Trước hết dùng bản Maven/JDK phù hợp:

```bash
mvn -version
```

Nếu tự gõ source hoặc IDE tạo format khác, developer có thể chuẩn hóa **chỉ một lần trước khi commit**:

```bash
mvn -B -ntp spotless:apply
```

Lệnh này **có thể thay đổi file Java trên đĩa**, vì vậy nên kiểm tra `git diff` trước khi commit. Nếu file đã đúng định dạng thì formatter không cần thay đổi gì.

Kiểm tra formatting riêng:

```bash
mvn -B -ntp spotless:check
```

Kiểm tra Checkstyle riêng:

```bash
mvn -B -ntp checkstyle:check
```

Chạy toàn bộ cổng chất lượng và tests:

```bash
mvn -B -ntp clean verify
```

Lượt build thành công sẽ:
1. Biên dịch `GreetingApp.java`;
2. Biên dịch và chạy **3 JUnit Jupiter tests**;
3. Tạo JAR ở phase `package`;
4. Kiểm tra Spotless formatting và Checkstyle rules tại `verify`;
5. Trả exit code thành công khi không có lỗi compiler/test/quality gate.

**Không khẳng định Maven log có chính xác số dòng nào**, vì output còn tùy plugin versions, local repository và môi trường. Số lượng test methods theo mã trên là **3**, còn đường dẫn report tiêu biểu là:

```text
target/surefire-reports/TEST-com.example.quality.GreetingAppTest.xml
```

### 5.7. Chạy Java class và stdout chính xác

Sau `mvn clean verify`, dùng:

```bash
java -cp target/classes com.example.quality.GreetingApp
```

**Stdout chính xác của chương trình Java**, không tính Maven logs:

```text
Hello, Maven!
Hello, friend!
```

POM ví dụ không ghi `Main-Class` vào manifest. Vì vậy **không** giả định lệnh `java -jar target/style-gates-demo-1.0.0.jar` chạy được. Đó là vấn đề packaging executable JAR khác với quality gates.

## 6. Thử cố tình tạo lỗi định dạng

Giả sử một developer viết một đoạn Java thiếu khoảng trắng và xuống dòng:

```java
package com.example.quality;
public final class Demo{public static void run(){System.out.println("ok");}}
```

Đây là **đoạn minh họa chưa đúng chuẩn**, không phải file để thêm vào project demo mà không chỉnh sửa. Java compiler vẫn có thể chấp nhận cú pháp này, nhưng formatter Google Java Format sẽ muốn thay đổi trình bày.

Nếu đoạn này nằm trong file Java được Spotless target, lệnh:

```bash
mvn spotless:check
```

có thể trả lỗi định dạng, nêu file và gợi ý `spotless:apply`. Điều này cho thấy **compiler success không đồng nghĩa format success**.

Sửa qua:

```bash
mvn spotless:apply
mvn spotless:check
```

Sau apply, format tương đương:

```java
package com.example.quality;

public final class Demo {
  public static void run() {
    System.out.println("ok");
  }
}
```

**Lưu ý kỹ thuật:** Ví dụ `Demo` không có private constructor, nhưng ruleset Checkstyle của bài không bật `HideUtilityClassConstructor`, nên Checkstyle sẽ không tự áp một chính sách chưa được cấu hình. Bản demo chính `GreetingApp` đã có private constructor.

Khi dùng Spotless `check`, phần lớn vi phạm đến từ khác biệt giữa nội dung file hiện tại và nội dung mà **formatter có thể tạo ra**. Không nên tự suy ra một file “trông đẹp” nghĩa là đạt format; hãy chạy chính goal `check`.

## 7. Thử tạo lỗi Checkstyle mà formatter không giải quyết

### 7.1. Wildcard imports

Ví dụ:

```java
import java.util.*;
```

Cú pháp Java trên hợp lệ, nhưng `AvoidStarImport` có thể báo vi phạm. Import cụ thể là:

```java
import java.util.List;
import java.util.Map;
```

Hai snippets trên chỉ minh họa import declarations, **không phải file Java hoàn chỉnh**. Khi dùng vào class thật, chỉ import type thực sự cần.

Formatter đôi khi có thể sắp xếp/import-cleanup nếu được cấu hình thêm bước, nhưng **đừng giả định Spotless sẽ sửa mọi vi phạm Checkstyle**. Trong POM bài này, Spotless chủ yếu dùng Google Java Format; quy tắc `AvoidStarImport` là một policy độc lập của Checkstyle.

### 7.2. Tên method sai convention

Ví dụ `public void DO_WORK() {}` có thể vi phạm `MethodName`. Việc đổi tên method không phải chỉ là format whitespace: cần đổi declaration lẫn call sites và kiểm tra public API compatibility.

### 7.3. Thiếu ngoặc nhọn

Ví dụ control statement:

```java
if (enabled)
  start();
```

Đây là **snippet minh họa**, không phải Java class độc lập. `NeedBraces` sẽ yêu cầu dùng dấu ngoặc theo policy:

```java
if (enabled) {
  start();
}
```

**Formatter không đồng nghĩa refactoring semantics.** Dù Google Java Format có thể căn lề câu lệnh đúng, nó không nên được coi là công cụ tự sửa mọi rule cấu trúc như Checkstyle.

### 7.4. Quy trình đọc lỗi

Nếu `mvn checkstyle:check` fail:
1. Tìm tên Checkstyle rule, ví dụ `AvoidStarImport` hoặc `NeedBraces`.
2. Xem file path, vị trí line/column nếu log có.
3. Đọc rule trong `config/checkstyle/checkstyle.xml`.
4. Sửa nguyên nhân source code, không chỉ xóa rule.
5. Chạy lại direct goal, sau đó `mvn clean verify`.
6. Với rule gây false positive, thảo luận policy của team, cân nhắc suppression hẹp có lý do.

Dòng Maven `BUILD FAILURE` chỉ báo build fail; **log vi phạm ngay trước đó** mới giúp tìm lỗi cụ thể.

## 8. Checkstyle: `check` và `checkstyle` khác gì?

Maven Checkstyle Plugin có nhiều goal. Hai goal cần phân biệt:

- **`checkstyle:check`**: thực thi kiểm tra và **có thể fail build** khi có violations. Đây là goal phù hợp cho quality gate.
- **`checkstyle:checkstyle`**: dành cho **báo cáo Checkstyle**, có thể tạo report phục vụ Maven Site hoặc gọi trực tiếp, **không thay thế goal `check` trong build gate**.

Ví dụ lệnh:

```bash
mvn checkstyle:check
mvn checkstyle:checkstyle
```

Tương tự, cấu hình plugin trong `<reporting>` phục vụ Maven Site **không tự khiến build tại phase verify fail**. Muốn cổng chất lượng chạy khi `mvn verify`, phải cấu hình goal execution trong `<build><plugins>` hoặc cơ chế áp dụng tương đương.

### `failOnViolation` so với `failsOnError`

Maven Checkstyle Plugin có các tùy chọn:
- `failOnViolation`: khi được bật, plugin có thể **fail build theo mức độ vi phạm và các tham số liên quan**; mặc định của goal `check` là `true`.
- `failsOnError`: lựa chọn chặt hơn có thể làm build fail sớm khi Checkstyle report bất kỳ violation/error, trước bước xử lý/logging như `failOnViolation`.

Bài này đặt **`failOnViolation=true` tường minh** vì cần cổng kiểm tra rõ ràng. Không cần bật tất cả các cờ cùng lúc mà không hiểu tác động lên log và chính sách. Khi có nhu cầu phân mức warning/error, tham khảo các tham số Checkstyle như `violationSeverity`, `maxAllowedViolations` nếu version/plugin hỗ trợ.

**Không đánh đồng Checkstyle warning với Java compiler warning.** Code có thể có các mức cảnh báo khác nhau, và threshold/policy do ruleset cộng cấu hình goal quyết định.

## 9. Quy tắc Checkstyle nên bắt đầu từ đâu?

Một team chưa có coding conventions thường mắc hai cực đoan:
- **Không có rule nào:** mọi style được review thủ công.
- **Bật bộ ruleset khổng lồ ngay:** hàng nghìn vi phạm legacy và mâu thuẫn với formatter, khiến mọi PR fail không liên quan thay đổi.

Cách khởi đầu hợp lý:
1. Chốt formatter version trước.
2. Chọn một số Checkstyle rules ít tranh cãi về **cấu trúc** (imports, braces, naming).
3. Chạy trên dự án nhỏ, đánh giá false positives.
4. Tăng rules theo từng nhóm có owner giải thích.
5. Không disable hàng loạt violations chỉ để giữ build xanh.

Những nhóm rule thường được cân nhắc:

| Nhóm | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| Naming | Class/method/variable naming | Public API changes có thể ảnh hưởng consumer |
| Imports | Wildcard, unused imports | Formatter cũng có thể xử lý một phần nếu thêm step |
| Braces | Điều kiện/vòng lặp có dấu ngoặc | Tránh bug khi thêm lệnh vào nhánh |
| Whitespace | Vị trí dấu cách, line width | Dễ xung đột với formatter khác |
| Javadoc | Yêu cầu documentation | Nên phân biệt public API và internal code |
| File/headers | License/copyright header | Phải khớp chính sách license của dự án |
| Complexity | Giới hạn mức lồng nhau/độ phức tạp | Có thể dùng thêm PMD nếu hợp lý |

Không có nghĩa tất cả rule đều nên bật trong ví dụ. **Giữ một nguồn chuẩn duy nhất cho format** rồi bổ sung Checkstyle những quy tắc mà formatter không đại diện.

## 10. Thêm PMD như một lớp static analysis tùy chọn

Spotless và Checkstyle xử lý nhiều phần về format/conventions, trong khi **PMD** tập trung rộng hơn vào quy tắc code quality: code smells, những mẫu dễ lỗi, complex methods và các rulesets khác.

Apache Maven PMD Plugin có goal:
- `pmd:pmd`: phân tích và tạo report;
- `pmd:check`: có thể **fail build khi report chứa các vi phạm vượt chính sách**;
- `pmd:cpd-check`: kiểm tra code duplication qua CPD theo policy.

Nếu muốn bổ sung PMD sau khi ví dụ cơ bản đã ổn định, có thể **thêm** plugin này trong `<build><plugins>` của POM:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-pmd-plugin</artifactId>
    <version>3.28.0</version>
    <configuration>
        <failOnViolation>true</failOnViolation>
        <verbose>true</verbose>
    </configuration>
    <executions>
        <execution>
            <id>check-static-analysis</id>
            <phase>verify</phase>
            <goals>
                <goal>check</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

**Đây là một biến thể tùy chọn**, không nằm trong POM hoàn chỉnh ở mục 5. `pmd:check` có thể gọi analysis goal cần thiết trước khi đánh giá report theo tài liệu plugin. Khi thêm vào một dự án thật:
- Quyết định rõ **ruleset** và mức ưu tiên những violations cần làm build fail;
- Kiểm tra PMD version hỗ trợ cú pháp Java của project;
- Đừng nhầm PMD với Spotless formatter;
- Không bật CPD cho project quá nhỏ chỉ vì muốn thêm chỉ số: nên chọn threshold và ignore files có chủ đích.

Có thể chạy độc lập:

```bash
mvn org.apache.maven.plugins:maven-pmd-plugin:3.28.0:check
```

Lệnh trực tiếp dùng tọa độ goal đầy đủ để tránh phụ thuộc prefix resolution khi plugin chưa được thêm vào POM. Phần ví dụ chính chỉ bắt buộc Spotless + Checkstyle; PMD là bước mở rộng theo maturity của team.

## 11. Chỉ kiểm tra file nào? Includes, excludes và generated source

Spotless Java target trong POM:

```xml
<java>
    <includes>
        <include>src/main/java/**/*.java</include>
        <include>src/test/java/**/*.java</include>
    </includes>
    <googleJavaFormat>
        <version>1.24.0</version>
    </googleJavaFormat>
</java>
```

Đây là **một đoạn `configuration` đã được POM chứa**, không phải POM thứ hai. Pattern kiểu Ant `src/main/java/**/*.java` hướng tới source files trong package subdirectories.

Trong những dự án có generated Java sources dưới `target/generated-sources`, đừng tự format mã generator sinh ra rồi commit, trừ khi đó là một quy trình có chủ đích. Spotless ở ví dụ chỉ nhắm `src/main/java` và `src/test/java`, không target `target`.

Checkstyle mặc định dựa vào source roots của project và có các tham số exclude generated sources ở phiên bản hỗ trợ. Nếu generator thêm thư mục mới vào compile source roots, cần **kiểm tra thực tế** Checkstyle có quét generated files không và cấu hình `excludes`/`excludeGeneratedSources` phù hợp.

Ví dụ tham số của Maven Checkstyle Plugin 3.6.0:

```xml
<excludeGeneratedSources>true</excludeGeneratedSources>
```

Đây là đoạn **tùy chọn thêm vào `<configuration>` của Checkstyle Plugin**, không phải tag hợp lệ ở mọi plugin. Dùng khi generated code không được phép chỉnh tay.

### Đừng loại bỏ mọi legacy file một cách mù quáng

Có trường hợp cần suppress rule cho generated code hoặc thư viện kế thừa. Tuy nhiên nên dùng:
- Exclusion hẹp với lý do;
- Suppressions filter có owner và thời hạn xem lại;
- Ngưỡng violation có kế hoạch giảm dần nếu tool hỗ trợ;
- Báo cáo quan sát được thay vì `skip=true` vĩnh viễn.

**Một file nằm ngoài include không được kiểm tra**, vì vậy “CI xanh” không tự bảo đảm **toàn repo** tuân thủ format. Cần khớp scope các source trees thật trong dự án.

## 12. Cấu hình nhiều module: tránh chỉ chạy ở aggregator

Một project multi-module có parent `packaging=pom` và nhiều Java module:
- `core`;
- `adapter`;
- `app`.

Nếu muốn các module cùng tuân thủ Spotless/Checkstyle, hãy **quản lý version và executions ở vị trí mà children thực sự nhận**.

### `pluginManagement` khác `plugins`

Trong parent:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>com.diffplug.spotless</groupId>
                <artifactId>spotless-maven-plugin</artifactId>
                <version>2.46.1</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Đây chỉ là **mẫu quản lý version**, chưa bind `spotless:check` cho tất cả modules. Để chạy quality gate trong children, cần plugin được khai báo tại `<build><plugins>` của children hoặc được inherit qua parent `<build><plugins>` với `<executions>` thích hợp.

**Không khai báo plugin ở `<reporting>` rồi nghĩ `mvn verify` sẽ tự fail**. Report và build execution là hai cơ chế khác nhau.

### Dùng một Checkstyle XML dùng chung

Với root layout:

```text
workspace/
├── pom.xml
├── config/checkstyle/checkstyle.xml
├── core/pom.xml
└── app/pom.xml
```

Khi Checkstyle chạy **trong core/app**, đường dẫn tương đối `config/checkstyle/checkstyle.xml` có thể được hiểu theo **project basedir của từng module** và không tồn tại. Hãy giải quyết rõ:
1. Với module con cấp một, đặt `configLocation` phù hợp, ví dụ `../config/checkstyle/checkstyle.xml` nếu module layout thực sự như trên;
2. Đóng gói rule file thành **một artifact JAR cấu hình Checkstyle** và khai báo nó như plugin dependency khi muốn chia sẻ nhiều repositories;
3. Dùng đường dẫn/properties đã được kiểm chứng với Maven version và root discovery thực tế.

Không giả định `configLocation` của root tự áp dụng đúng path ở mọi module khi modules nằm sâu khác nhau.

### Cần quality gate ở module nào?

- Java library/CLI: thường kiểm tra cả main/test Java sources.
- Parent `pom` aggregator: thường không có Java sources; plugin có thể không có gì để check.
- Code generator: nên kiểm tra **generator source** nhưng xử lý generated source theo policy riêng.
- Module chỉ chứa POM/config: có thể thêm formatter cho XML/POM nếu muốn, nhưng không ép Java Checkstyle có source để quét.

## 13. Đưa cổng chất lượng vào CI và pull request

Mục tiêu CI là kiểm tra những file developer định commit, với cùng build config.

Một job có thể chạy:

```bash
mvn -B -ntp clean verify
```

Với POM ở mục 5:
- Compiler/tests hoạt động trước;
- Spotless `check` và Checkstyle `check` chạy ở `verify`;
- Nếu source format/rules vi phạm, Maven trả **nonzero exit code** và CI phải đánh dấu job thất bại;
- CI **không** tự chạy `spotless:apply`.

Một GitHub Actions workflow minh họa:

```yaml
name: Maven quality
on:
  pull_request:
  push:

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Verify build and source quality
        run: mvn -B -ntp clean verify
```

Đây là **workflow minh họa** cho GitHub Actions. Nếu tổ chức dùng GitLab CI, Jenkins hoặc CI riêng, nguyên tắc giữ nguyên: checkout commit cần kiểm tra, chuẩn bị Java/Maven đúng version, chạy Maven `verify`, dựa vào exit code để chặn merge/deploy.

**Chỉ có workflow file không tự chặn merge.** Trên nền tảng hosting cần cấu hình branch protection / required checks phù hợp, nếu muốn bắt buộc job xanh trước khi merge.

### Vì sao không chạy apply trong CI?

Nếu CI chạy `spotless:apply`, nó có thể format file trong workspace tạm. Job sau đó build thành công với **source đã bị CI thay đổi**, trong khi commit của người viết **vẫn không chuẩn**. Vì vậy quality gate phải dùng `check`; sửa mã nguồn là trách nhiệm của developer hoặc một quy trình tạo commit tự động riêng được quản lý minh bạch.

### Có nên gắn check ở validate để fail sớm?

Tùy team:
- `validate`: nhanh, gặp vi phạm sớm; Checkstyle có thể phân tích code chưa compile.
- `verify`: compiler/tests chạy trước, phù hợp kiểm tra tổng thể; chậm hơn khi format vi phạm.
- Chạy trực tiếp `mvn spotless:check checkstyle:check`: phù hợp bước kiểm tra nhanh trước commit, nhưng phải biết cú pháp plugin prefix và cấu hình.

**Quan trọng:** Đừng dựa vào `mvn test` để kết luận format/rules đã đạt nếu executions gắn ở `verify`.

## 14. Phân biệt lỗi build và lỗi môi trường plugin

Một quality gate fail không phải lúc nào cũng vì source code:

| Dấu hiệu | Khả năng nguyên nhân | Hành động |
| --- | --- | --- |
| `spotless:check` nêu file cần format | Source khác output formatter | Chạy `spotless:apply`, review diff, commit |
| `checkstyle:check` nêu `AvoidStarImport` | Import wildcard | Thay bằng imports cụ thể |
| `NeedBraces` | Thiếu braces ở control statement | Thêm ngoặc và chạy test lại |
| `TypeName` hoặc `MethodName` | Naming vi phạm convention | Đổi tên và cập nhật call sites |
| Checkstyle không tìm thấy `checkstyle.xml` | Sai `configLocation`/basedir | Tạo file, sửa path |
| Maven `No plugin found for prefix` | Prefix không resolve hoặc plugin chưa khai báo | Kiểm tra `<build><plugins>`, dùng full goal coordinates |
| Plugin/dependency download lỗi | Maven Central/mirror/proxy/network/offline | Kiểm tra `settings.xml`, repository availability |
| Formatter không chạy với JDK đang dùng | Plugin/formatter có runtime JDK minimum khác | Kiểm tra `mvn -version`, plugin release requirements |
| `mvn test` xanh nhưng `mvn verify` fail style | Checks gắn phase `verify` | Chạy đúng lifecycle và sửa source |
| Checkstyle report có nhưng build vẫn xanh | Chạy goal report thay vì `check`, hoặc fail threshold/skip | Kiểm tra binding `check`, `failOnViolation` |
| Một module bị bỏ qua | `-pl`, `-N`, execution inheritance hoặc includes sai | Xem Reactor Build Order/effective POM |
| Generated Java bị báo hàng nghìn violations | Tool đang quét generated source | Thêm excludes hẹp phù hợp |
| CI xanh dù code chưa format | Job chạy `apply` hoặc goal không bind vào lifecycle | Chỉ dùng `check`, kiểm tra POM execution |
| Các dev format code ra khác nhau | Không ghim formatter/plugin versions hoặc IDE config khác | Chốt phiên bản và chạy Maven gate |
| Một rule báo quá nhiều false positives | Rule không phù hợp codebase | Review rule/suppression có lý do |
| PMD báo bug pattern không phải format | Trộn hai trách nhiệm | Phân tích nội dung code, không chỉ format |
| `BUILD FAILURE` không có location | Log bị cắt hoặc goal không console output | Xem báo cáo/log đầy đủ, bật console output hợp lý |

Đừng đặt mọi lỗi vào cùng một nhóm “quality fail”. **Lỗi tải plugin** không chứng minh source code sai; **vi phạm rule** không được “sửa” bằng tắt kiểm tra.

### Debug thực tế

1. Xác nhận `mvn -version`: Maven, Java runtime.
2. Kiểm tra POM có Spotless/Checkstyle **plugin versions và executions**.
3. Kiểm tra file `config/checkstyle/checkstyle.xml` thật sự tồn tại.
4. Chạy `mvn spotless:check` rồi `mvn checkstyle:check` riêng để phân loại lỗi.
5. Nếu format fail, chạy `spotless:apply` **trên bản làm việc developer** và xem `git diff`.
6. Nếu Checkstyle fail, xem `rule`, `file`, `line`, sau đó sửa code hoặc policy có review.
7. Chạy `mvn clean verify` để xác nhận **tests + cả hai gates**.
8. Trên CI, kiểm tra job thật chạy `verify` và exit status được pipeline dùng.
9. Với reactor, kiểm tra tất cả module có execution và scope file đúng.
10. Không tắt checks vĩnh viễn chỉ để đạt `BUILD SUCCESS`.

## 15. Baseline, suppression và áp dụng dần trong codebase cũ

Một codebase đã tồn tại lâu có thể có hàng nghìn file chưa tuân thủ format. Chạy `spotless:apply` cho **toàn bộ repo** có thể tạo một PR rất lớn, khó review và tăng nguy cơ merge conflict.

Một cách triển khai an toàn:
- Chốt rules và plugin versions trong một PR cấu hình riêng.
- Chạy formatter thử trên một thư mục/nhóm files có phạm vi kiểm soát.
- Tạo PR chỉ chứa formatting khi cần, không trộn refactor logic với hàng nghìn whitespace changes.
- Giới hạn rule/loại file có chủ đích và lên kế hoạch mở rộng.
- Dùng Spotless **ratchet** nếu phù hợp với chính sách version control và hiểu commit baseline; nó giúp enforce theo nhánh thay đổi ở một số tình huống thay vì nợ format toàn repo.
- Dùng Checkstyle suppression hẹp cho trường hợp thật sự không sửa ngay được; giữ ghi chú lý do và thời điểm xem lại.

**Không dùng suppression làm nơi cất tất cả vi phạm vĩnh viễn.** Mỗi suppression nên có phạm vi cụ thể (rule, file, dòng nếu hợp lý), lý do và người chịu trách nhiệm.

### Suppressions của Checkstyle

Maven Checkstyle Plugin hỗ trợ `suppressionsLocation`, nhưng cách wiring suppression còn phụ thuộc Checkstyle XML `SuppressionFilter` và expression được cấu hình. Nếu chỉ viết:

```xml
<suppressionsLocation>config/checkstyle/suppressions.xml</suppressionsLocation>
```

mà không thêm `SuppressionFilter` phù hợp trong Checkstyle XML, không nên giả định mọi suppression đã hoạt động. Cần đọc tài liệu plugin và kiểm thử một violation có/không bị suppressed như mong đợi.

Demo **không dùng suppressions**, để kết quả dễ hiểu và mọi vi phạm Checkstyle theo bốn rule đều có thể làm build fail.

## 16. Quy tắc formatter và Checkstyle có thể mâu thuẫn như thế nào?

Ví dụ Spotless áp Google Java Format, còn Checkstyle ruleset khác yêu cầu tab indentation hoặc 4-space indentation trái với formatter. Developer có thể:
1. Chạy `spotless:apply` -> format bằng 2-space;
2. Chạy `checkstyle:check` -> bị báo indentation;
3. Sửa tay sang 4-space;
4. Chạy `spotless:check` -> lại fail.

Đây là **xung đột policy**, không phải developer thiếu kỹ năng. Cách sửa là **chọn một formatter chuẩn duy nhất** rồi cấu hình/simplify Checkstyle không bắt các quy tắc layout mâu thuẫn, hoặc lựa chọn formatter khác có cùng style với ruleset.

Tương tự, nếu Spotless được cấu hình sắp xếp imports theo cách khác Checkstyle ImportOrder, cần thống nhất order cho hai tool.

**Checklist xung đột:**
- Formatter nào quyết định indentation?
- Formatter nào quyết định line wrapping?
- Ai quản lý import order và wildcard imports?
- Có rule yêu cầu Javadocs không? Formatter có làm gì với Javadocs?
- Có file generated source hoặc vendored code bị quét không?
- Đã ghim formatter version khi update Checkstyle ruleset chưa?

Đừng gỡ toàn bộ Checkstyle chỉ vì một rule không tương thích; thường chỉ cần điều chỉnh nhóm rules overlap.

## 17. `spotless:apply` không nên được coi là “đã sửa mọi lỗi”

Formatters chủ yếu biến đổi **biểu diễn văn bản**. Ngay sau khi `spotless:apply` thành công, vẫn có thể tồn tại:
- Tên kiểu không đáp ứng `TypeName`;
- Tên method không đáp ứng `MethodName`;
- Thiếu braces mà formatter không tự thêm;
- Dữ liệu đầu vào không được validate;
- NPE, resource leak hoặc lỗi transaction;
- SQL injection hay lỗ hổng bảo mật khác.

Muốn quality gate đầy đủ cần compiler/tests, static analysis phù hợp, security checks và review theo mức rủi ro của sản phẩm.

**Vì vậy lệnh kiểm cuối phải là `mvn clean verify`, không chỉ `mvn spotless:apply`.**

## 18. Kiểm soát phiên bản và khả năng tái lập

Vì formatter có thể thay đổi output giữa các versions:
- Ghim `spotless-maven-plugin` và `google-java-format` version.
- Ghim `maven-checkstyle-plugin` version và lưu ruleset XML trong version control.
- Cập nhật plugin/formatter theo PR riêng, review phạm vi format diff.
- Chốt JDK dùng để chạy Maven (không chỉ `maven.compiler.release`) vì một số plugin formatter có JRE minimum riêng.
- Tránh cho CI tự download tool từ nguồn không được kiểm soát; dùng repository/mirror được tổ chức phê duyệt khi cần.
- Với multi-module, ưu tiên quản lý versions tại parent để không có module dùng plugin version khác do vô tình.

`project.build.sourceEncoding=UTF-8` hỗ trợ xử lý source text nhất quán, nhưng **không tự đồng bộ line endings của tất cả file hoặc cấu hình editor**. Có thể dùng `.gitattributes`, EditorConfig và Spotless format steps khi thật sự cần chính sách thống nhất.

Một team chạy formatter giống nhau trong Maven/CI thường giảm tranh luận vô ích về whitespace trong code review.

## 19. Bài tập tự kiểm tra

1. **Mục tiêu:** Vì sao unit tests xanh chưa chứng minh source format đúng?
2. **Phân biệt:** `spotless:check` và `spotless:apply` khác nhau ở tác động trên file?
3. **Thiết kế CI:** Tại sao CI nên chạy `check` thay vì `apply`?
4. **Lifecycle:** Khi check goals bind ở `verify`, `mvn test` đã thực thi quality gate chưa?
5. **Phạm vi:** Pattern `src/main/java/**/*.java` chọn những file nào? Có tự quét `target/generated-sources` không?
6. **Checkstyle:** Rule nào trong XML ví dụ phát hiện `import java.util.*;`?
7. **Naming:** `MethodName` có sửa tên method giúp bạn không?
8. **Test source:** Điều gì làm Checkstyle và Spotless đều kiểm tra file trong `src/test/java`?
9. **Cấu hình:** Vì sao plugin trong `<reporting>` không đủ để chặn `mvn verify`?
10. **PMD:** Khi nào nên bổ sung PMD bên cạnh Spotless và Checkstyle?
11. **Multi-module:** Vì sao một `configLocation` tương đối có thể sai khi child modules nằm ở folder khác root?
12. **Generated code:** Tại sao không nên tự format code generator sinh ra mà không có chủ đích?
13. **Scope:** Một quality gate báo xanh có nghĩa toàn repo tuân thủ nếu nhiều folder bị excludes không?
14. **Policy conflict:** Vì sao không nên bật Checkstyle indentation mâu thuẫn Google Java Format?
15. **Kết quả:** Lệnh Java nào chạy `GreetingApp` sau build và in chính xác hai dòng gì?

### Đáp án ngắn

- **1:** Tests kiểm tra behavior theo assertions, không kiểm soát formatting toàn bộ source.
- **2–3:** `check` chỉ kiểm tra/không sửa; `apply` có thể rewrite source, phù hợp developer hơn CI.
- **4:** Chưa; lệnh phải tới phase `verify` hoặc gọi goal trực tiếp.
- **5:** Chọn Java files trong source trees đã khai báo; không tự quét thư mục `target`.
- **6:** `AvoidStarImport`.
- **7:** Không; goal Checkstyle `check` báo vi phạm, developer/refactor xử lý.
- **8:** Spotless includes test tree và Checkstyle `includeTestSourceDirectory=true`.
- **9:** `<reporting>` dành cho reports, không tự bind build failure goal.
- **10:** Khi cần thêm static analysis về bugs/code smells/duplication theo policy.
- **11:** Config paths thường được resolve theo project basedir.
- **12:** Generated code thay đổi khi generator chạy, sửa tay không bền vững.
- **13:** Không; chỉ những file trong scope được gate kiểm tra.
- **14:** Developer sẽ mắc vòng format/sửa rule; phải thống nhất style.
- **15:** `java -cp target/classes com.example.quality.GreetingApp` in `Hello, Maven!` và `Hello, friend!`.

## 20. Checklist trước khi dùng làm required quality gate

- [ ] POM ghim Spotless Plugin và formatter engine version.
- [ ] POM ghim Checkstyle Plugin version; ruleset XML nằm trong version control.
- [ ] Spotless target bao gồm Java main/test trees cần kiểm tra.
- [ ] Checkstyle có `configLocation` đúng trên từng module.
- [ ] `check` goals được bind vào phase phù hợp, ví dụ `verify`.
- [ ] CI chạy `mvn -B -ntp clean verify`, không tự chạy `spotless:apply`.
- [ ] CI tôn trọng nonzero exit code và cấu hình required check khi cần chặn merge.
- [ ] Developer biết chạy `spotless:apply` rồi review `git diff`.
- [ ] Unit tests vẫn chạy; quality gate không thay thế tests.
- [ ] Không có rule layout Checkstyle mâu thuẫn formatter.
- [ ] Không vô tình check generated/vendor code hoặc bỏ qua source quan trọng.
- [ ] Mọi suppressions/exclusions đều hẹp và có lý do.
- [ ] Vi phạm rule thực sự làm build fail; có thử tạo một lỗi để xác nhận.
- [ ] `mvn test` và `mvn verify` khác nhau được giải thích cho team.
- [ ] JDK của Maven đủ mới cho plugin/formatter, release Java được kiểm soát.
- [ ] Với reactor, các module Java thực sự inherit/áp plugin executions.
- [ ] Có phương án áp dụng dần để tránh PR reformat khổng lồ.
- [ ] Khi thêm PMD, chọn ruleset và ngưỡng fail riêng, không coi nó là formatter.
- [ ] Sau khi sửa vi phạm, build `clean verify` và test Java thực tế đều thành công.

**Kết luận:** Trong Maven, tích hợp cổng chất lượng mã nguồn hiệu quả nghĩa là **tự động kiểm tra những quy tắc đã thống nhất ngay trong lifecycle**. Spotless `check` giữ formatting nhất quán, Spotless `apply` phục vụ developer sửa source, Checkstyle `check` kiểm soát coding conventions, còn PMD có thể mở rộng static analysis. Khi chúng được cấu hình đúng `<build><plugins><executions>`, gắn phase `verify`, có source scope/ruleset rõ và được chạy bằng CI, một pull request vi phạm sẽ bị chặn thay vì chỉ để lại góp ý thủ công.

## Tài liệu tham khảo

- [Spotless — Maven Plugin README, quickstart, Java, check/apply, lifecycle](https://github.com/diffplug/spotless/blob/main/plugin-maven/README.md)
- [Spotless — Maven Plugin Change Log](https://github.com/diffplug/spotless/blob/main/plugin-maven/CHANGES.md)
- [Apache Maven Checkstyle Plugin — Usage](https://maven.apache.org/plugins/maven-checkstyle-plugin/usage.html)
- [Apache Maven Checkstyle Plugin — checkstyle:check](https://maven.apache.org/plugins/maven-checkstyle-plugin/check-mojo.html)
- [Apache Maven Checkstyle Plugin — Custom Checker Configuration](https://maven.apache.org/plugins/maven-checkstyle-plugin/examples/custom-checker-config.html)
- [Apache Maven Checkstyle Plugin — Suppressions Filter](https://maven.apache.org/plugins/maven-checkstyle-plugin/examples/suppressions-filter.html)
- [Checkstyle — Getting Started and Rule Configuration](https://checkstyle.org/getting-started.html)
- [Apache Maven PMD Plugin — Violation Checking](https://maven.apache.org/plugins/maven-pmd-plugin/examples/violationChecking.html)
- [Apache Maven PMD Plugin — pmd:check](https://maven.apache.org/plugins/maven-pmd-plugin/check-mojo.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)