# CI-friendly versions với revision, sha1 và changelist trong Maven

## 1. Mục tiêu: kiểm soát phiên bản build mà không sửa POM mỗi lần chạy CI

Một project Java thường có ít nhất ba loại build: bản đang phát triển (`1.4.0-SNAPSHOT`), bản phát hành (`1.4.0`) và bản CI muốn gắn dấu vết commit (`1.4.0-gabc123-SNAPSHOT`). Nếu một repository có hàng chục module, sửa `<version>` trong từng POM để tạo những bản này dễ dẫn đến lệch phiên bản, tạo commit chỉ để thay số version và làm rối quy trình phát hành.

**CI-friendly versions** là cơ chế Maven cho phép dùng ba placeholder có tên cố định ngay tại project version:

- `${revision}` — phần phiên bản nền, ví dụ `1.4.0`.
- `${sha1}` — phần mở rộng tùy chọn, ví dụ `-gabc123`; **Maven không tự lấy Git SHA**.
- `${changelist}` — phần thay đổi trạng thái, thường `-SNAPSHOT` hoặc rỗng khi release.

Trong một POM Maven 3:

```xml
<version>${revision}${sha1}${changelist}</version>
<properties>
    <revision>1.4.0</revision>
    <sha1></sha1>
    <changelist>-SNAPSHOT</changelist>
</properties>
```

Maven tính được version hiệu lực **`1.4.0-SNAPSHOT`**. CI có thể đổi giá trị bằng `-Drevision`, `-Dsha1`, `-Dchangelist` mà không phải sửa source POM.

Cơ chế này được hướng dẫn chính thức từ **Maven 3.5.0-beta-1**. Trong bài thực hành dùng **Maven 3.9.x** ổn định và **Java 17**, để có đầy đủ chức năng cùng các plugin hiện đại.

### Những giới hạn cần hiểu ngay

1. Đây là **cơ chế tính version string**, không phải công cụ tự tạo Git tag, ký artifact, thay changelog hoặc deploy.
2. **Chỉ ba tên placeholder nói trên** được Maven 3 xử lý đặc biệt ở project version. Không dùng tùy ý `${myVersion}` như một cơ chế tương đương.
3. `sha1` là tên property chứ không phải phép kiểm chứng nguồn; Maven **không tự chạy `git rev-parse`**.
4. `changelist` không tự phát hiện “đang build release”; chính bạn/CI phải gán rỗng nếu muốn không có suffix.
5. **Dependency giữa các module Maven 3 nên dùng `${project.version}`**, không dùng `${revision}` như một phiên bản đầy đủ.
6. Trên **Maven 3**, khi `install` hoặc `deploy` thì thường cần **Flatten Maven Plugin** để POM được công bố có tọa độ concrete, giúp một consumer ngoài reactor resolve đúng.
7. **Maven 4** có cải tiến khác với model `4.1.0`; đừng tự áp dụng quy tắc Maven 4 vào POM Maven 3.

## 2. Ba property hợp thành version như thế nào?

Maven dùng một expression như:

```text
effectiveVersion = revision + sha1 + changelist
```

Đây là **sơ đồ nối chuỗi để hiểu kết quả**, không phải một cú pháp expression khác bạn phải viết vào POM. Maven thay từng placeholder đã hỗ trợ bằng giá trị tương ứng.

| revision | sha1 | changelist | Project version thu được |
| --- | --- | --- | --- |
| `1.4.0` | rỗng | `-SNAPSHOT` | `1.4.0-SNAPSHOT` |
| `1.4.0` | rỗng | rỗng | `1.4.0` |
| `1.5.0` | `-gabc123` | `-SNAPSHOT` | `1.5.0-gabc123-SNAPSHOT` |
| `2.0.0` | `-build42` | rỗng | `2.0.0-build42` |
| `2026.11.0` | rỗng | `-SNAPSHOT` | `2026.11.0-SNAPSHOT` |

Mỗi giá trị là **chuỗi bạn cấp**, không có nghĩa Maven sẽ tự thêm dấu `-` hoặc tự chọn format semantic versioning.

### `revision`: version nền

Khai:

```xml
<revision>1.4.0</revision>
```

và override:

```bash
mvn -Drevision=1.5.0 clean verify
```

Nếu `sha1` rỗng, `changelist=-SNAPSHOT`, version là `1.5.0-SNAPSHOT`.

Đừng khai `revision=1.5.0-SNAPSHOT` rồi vẫn giữ `changelist=-SNAPSHOT`; kết quả thành `1.5.0-SNAPSHOT-SNAPSHOT` và dễ gây nhầm lẫn với repository policy.

### `sha1`: một phần tùy chọn của tên phiên bản

Khai mặc định:

```xml
<sha1></sha1>
```

Gắn một suffix tự định nghĩa:

```bash
mvn -Drevision=1.4.0 -Dsha1=-gabc123 -Dchangelist=-SNAPSHOT clean package
```

Kết quả: `1.4.0-gabc123-SNAPSHOT`.

**Không có auto-Git logic.** Muốn thực sự dùng mã commit, workflow phải lấy mã từ commit đã checkout và truyền vào Maven. Một short hash có thể trùng nếu giới hạn quá ngắn; nó không thay thế full Git SHA, artifact checksum, signature hay provenance.

### `changelist`: SNAPSHOT và release

Default thường là:

```xml
<changelist>-SNAPSHOT</changelist>
```

Khi release:

```bash
mvn -Drevision=1.4.0 -Dsha1= -Dchangelist= clean package
```

Maven nhận `1.4.0`. Đối số `-Dchangelist=` truyền **chuỗi rỗng**. Nếu quên dấu `-` ở `<changelist>-SNAPSHOT</changelist>`, kết quả có thể thành `1.4.0SNAPSHOT`, không phải suffix chuẩn.

### Ba property không tương đương với ba Maven artifact attributes

Repository vẫn thấy một artifact version đơn lẻ như `1.4.0-gabc123-SNAPSHOT`. Không có ba field riêng tên revision, sha1, changelist trong tọa độ GAV. `sha1` cũng không trở thành `classifier`; classifier là khái niệm khác dùng phân biệt artifact bổ sung cùng GAV.

## 3. Ví dụ sai: property tùy ý hoặc nội suy lồng nhau

**Không dùng một property bất kỳ thay cho bộ ba được hỗ trợ:**

```xml
<!-- Không được hỗ trợ như CI-friendly project version của Maven 3 -->
<version>${buildVersion}</version>
```

**Không kỳ vọng nội suy lồng nhau sẽ hoạt động như mong muốn:**

```xml
<properties>
    <revision>1.4.0-${buildNumber}</revision>
</properties>
<version>${revision}</version>
```

Tài liệu Maven CI-friendly minh họa rằng cách lồng `${buildNumber}` trong `revision` không hoạt động như người dùng mong đợi. Nếu thật sự cần build number, **tạo giá trị version/suffix ở CI rồi truyền property đã được hỗ trợ**:

```bash
mvn -Drevision=1.4.0 -Dsha1=-build42 -Dchangelist=-SNAPSHOT clean verify
```

Không dùng giá trị do người khác cung cấp chưa validate để tạo version/command. Version có thể bị repository/tooling từ chối nếu có ký tự không hợp lệ hoặc không đáp ứng release policy.

## 4. Nơi khai property và cách override

Có ba vị trí hay dùng:

- **POM/parent POM `<properties>`**: default chung cho lập trình viên.
- **`.mvn/maven.config`**: Maven CLI options áp dụng theo repository.
- **Command line `-D...`**: override tường minh của CI hoặc người chạy build.

Với project dùng POM properties mặc định, CLI user properties `-Drevision=...`, `-Dsha1=...`, `-Dchangelist=...` ghi đè các default tương ứng.

File `.mvn/maven.config` mẫu:

```text
-Drevision=1.4.0
-Dsha1=
-Dchangelist=-SNAPSHOT
```

Đây là **nội dung file**, mỗi tùy chọn trên một dòng cho Maven 3.x hiện đại. Không bắt buộc có file này nếu POM đã khai defaults; ví dụ hoàn chỉnh bên dưới chỉ sử dụng POM properties.

### Lệnh CLI dành cho CI

```bash
mvn -B -ntp -Drevision=1.4.0 -Dsha1= -Dchangelist=-SNAPSHOT clean verify
```

`-B` bật batch mode, `-ntp` tắt transfer progress. Các cờ này không liên quan tới version semantics, nhưng hữu ích với CI logs.

Trước khi build, kiểm tra Maven và JDK:

```bash
mvn -version
java -version
javac -version
```

**`mvn -version` không trả version dự án**; nó cho biết Maven distribution và JVM chạy Maven. Muốn xem resolved project version, dùng Maven Help Plugin.

## 5. Maven 3 multi-module: dùng chung version giữa parent và children

Một reactor có parent POM và hai modules:

```text
ci-friendly-demo/
├── pom.xml
├── greeter-core/
│   └── pom.xml
└── greeter-cli/
    └── pom.xml
```

Trong parent:

```xml
<groupId>dev.lesson</groupId>
<artifactId>ci-friendly-demo</artifactId>
<version>${revision}${sha1}${changelist}</version>
<packaging>pom</packaging>
```

Trong children:

```xml
<parent>
    <groupId>dev.lesson</groupId>
    <artifactId>ci-friendly-demo</artifactId>
    <version>${revision}${sha1}${changelist}</version>
</parent>
```

Parent version, groupId và properties có thể được kế thừa. Khi CI đổi revision/changelist, cả reactor cùng có một project version phù hợp.

**Vị trí dependency giữa modules là chuyện khác.** Trong `greeter-cli/pom.xml`, dependency lên `greeter-core` cần:

```xml
<dependency>
    <groupId>dev.lesson</groupId>
    <artifactId>greeter-core</artifactId>
    <version>${project.version}</version>
</dependency>
```

Đừng đổi thành:

```xml
<!-- Không dùng cho inter-module dependency trong ví dụ composite version -->
<version>${revision}</version>
```

Ví dụ CI resolved version `1.4.0-gabc123-SNAPSHOT`:

- `${project.version}` là **`1.4.0-gabc123-SNAPSHOT`**.
- `${revision}` chỉ là **`1.4.0`**.
- Nếu dependency dùng `${revision}`, Maven có thể cố resolve artifact `greeter-core:1.4.0` vốn không được reactor hiện tại tạo ra.

Tài liệu Maven chính thức cũng hướng dẫn dùng `${project.version}` cho **inter-module dependencies**, kể cả khi parent chỉ dùng `${revision}`.

### `<modules>` không tự tạo quan hệ dependency

`<modules>` trong aggregator chỉ chọn modules để Maven reactor quản lý. `greeter-cli` không tự có `greeter-core` trên classpath nếu bạn không khai `<dependency>`. Parent/aggregator và dependency graph là những khái niệm khác nhau.

## 6. Dự án thực hành Java 17: parent, core library và CLI

Ta dựng một project với **ba POMs và ba Java files**, gồm một JUnit test. Không cần database, network service hoặc native tool. Version default là `1.4.0-SNAPSHOT` và có thể thay bằng các lệnh CI.

**Yêu cầu:** Maven 3.9.x (hoặc Maven 3 tương thích), JDK 17+, Maven Central/mirror để tải các plugins và JUnit. `deploy` không bắt buộc và không chạy trong demo.

### Cấu trúc đầy đủ

```text
ci-friendly-demo/
├── pom.xml
├── greeter-core/
│   ├── pom.xml
│   └── src/main/java/dev/lesson/core/Greeter.java
└── greeter-cli/
    ├── pom.xml
    ├── src/main/java/dev/lesson/cli/Main.java
    └── src/test/java/dev/lesson/cli/MainTest.java
```

### 6.1. Root `ci-friendly-demo/pom.xml` — POM đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>ci-friendly-demo</artifactId>
    <version>${revision}${sha1}${changelist}</version>
    <packaging>pom</packaging>

    <modules>
        <module>greeter-core</module>
        <module>greeter-cli</module>
    </modules>

    <properties>
        <revision>1.4.0</revision>
        <sha1></sha1>
        <changelist>-SNAPSHOT</changelist>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
            </plugins>
        </pluginManagement>

        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>flatten-maven-plugin</artifactId>
                <version>1.8.0</version>
                <configuration>
                    <updatePomFile>true</updatePomFile>
                    <flattenMode>resolveCiFriendliesOnly</flattenMode>
                </configuration>
                <executions>
                    <execution>
                        <id>flatten-ci-versions</id>
                        <phase>process-resources</phase>
                        <goals>
                            <goal>flatten</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>flatten-clean</id>
                        <phase>clean</phase>
                        <goals>
                            <goal>clean</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**Giải thích:**

1. `<version>${revision}${sha1}${changelist}</version>` được Maven 3 hiểu theo cơ chế CI-friendly.
2. `<packaging>pom</packaging>` có nghĩa root là parent/aggregator, không đóng JAR chứa code Java.
3. `<modules>` khai rõ hai child directories.
4. Các defaults tạo version `1.4.0-SNAPSHOT`, vẫn có thể override trên command line.
5. `maven.compiler.release=17` chọn Java platform/compiler release. Các phiên bản Compiler, Surefire và JAR plugins được pin trong `pluginManagement` cho các child packaging `jar`.
6. **Flatten Maven Plugin 1.8.0** được khai trong `build/plugins`; plugin executions được kế thừa theo mặc định sang children.
7. `resolveCiFriendliesOnly` tập trung giải quyết các CI-friendly placeholders, không tự thay mọi element metadata như các flatten modes khác.
8. `updatePomFile=true` đảm bảo Maven có thể dùng flattened POM khi `install`/`deploy`, đặc biệt quan trọng với **parent packaging `pom`**.
9. Goal `flatten` chạy ở `process-resources` trước install/deploy; goal `clean` dọn file flattened POM cũ khi chạy Maven clean lifecycle.

### 6.2. `greeter-core/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.lesson</groupId>
        <artifactId>ci-friendly-demo</artifactId>
        <version>${revision}${sha1}${changelist}</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>greeter-core</artifactId>
    <packaging>jar</packaging>
</project>
```

Không cần child `<version>` riêng vì version được kế thừa từ parent. `relativePath` giúp Maven tìm source parent trong reactor; consumer bên ngoài vẫn phải resolve parent artifact trong repository phù hợp.

### 6.3. `greeter-core/src/main/java/dev/lesson/core/Greeter.java`

```java
package dev.lesson.core;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

Không có thư viện Java ngoài, chỉ có một method có kết quả deterministic để kiểm chứng module dependency và runtime.

### 6.4. `greeter-cli/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.lesson</groupId>
        <artifactId>ci-friendly-demo</artifactId>
        <version>${revision}${sha1}${changelist}</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>greeter-cli</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>greeter-core</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`<version>${project.version}</version>` ở dependency `greeter-core` là một dòng then chốt: giữ dependency nội bộ cùng **resolved project version**, kể cả khi CI đổi `revision`, `sha1` hay `changelist`. JUnit Jupiter dùng test scope nên không thuộc runtime classpath của ứng dụng thông thường.

### 6.5. `greeter-cli/src/main/java/dev/lesson/cli/Main.java`

```java
package dev.lesson.cli;

import dev.lesson.core.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("GREETING=" + Greeter.greet("Maven"));
    }
}
```

CLI module có một import từ core module, chứng minh dependency giữa hai modules thật sự cần thiết khi compile.

### 6.6. `greeter-cli/src/test/java/dev/lesson/cli/MainTest.java`

```java
package dev.lesson.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;

import dev.lesson.core.Greeter;
import org.junit.jupiter.api.Test;

class MainTest {
    @Test
    void usesCoreDependency() {
        assertEquals("Hello, Maven!", Greeter.greet("Maven"));
    }
}
```

JUnit test không phụ thuộc database/network và không in stdout. Surefire sẽ phát hiện tên `MainTest` theo quy tắc unit test mặc định.

### 6.7. Build toàn bộ reactor

Đứng tại root `ci-friendly-demo/`:

```bash
mvn -version
mvn -B -ntp clean verify
```

Kết quả mong đợi nếu Maven resolve plugin/dependencies thành công:

- Parent, core và CLI có resolved version `1.4.0-SNAPSHOT`.
- Module core được build trước CLI do quan hệ dependency.
- `MainTest` chạy một test và pass.
- JARs được tạo ở `greeter-core/target` và `greeter-cli/target`.
- Flatten Plugin tạo các generated POMs để chuẩn bị consumer metadata.

Các **file paths dự kiến**, không phải toàn bộ Maven output:

```text
greeter-core/target/greeter-core-1.4.0-SNAPSHOT.jar
greeter-cli/target/greeter-cli-1.4.0-SNAPSHOT.jar
greeter-cli/target/surefire-reports/
```

### 6.8. Chạy CLI từ compiled classes

Linux/macOS:

```bash
java -cp "greeter-cli/target/classes:greeter-core/target/classes" dev.lesson.cli.Main
```

Windows PowerShell:

```powershell
java -cp "greeter-cli/target/classes;greeter-core/target/classes" dev.lesson.cli.Main
```

**Stdout chính xác của Java main:**

```text
GREETING=Hello, Maven!
```

Hai thư mục được nêu rõ trong classpath vì CLI cần class từ core. `-cp` trên Linux/macOS dùng dấu `:`, Windows dùng `;`.

### 6.9. Chạy từ hai JARs đã package

Linux/macOS:

```bash
java -cp "greeter-cli/target/greeter-cli-1.4.0-SNAPSHOT.jar:greeter-core/target/greeter-core-1.4.0-SNAPSHOT.jar" dev.lesson.cli.Main
```

Windows PowerShell:

```powershell
java -cp "greeter-cli/target/greeter-cli-1.4.0-SNAPSHOT.jar;greeter-core/target/greeter-core-1.4.0-SNAPSHOT.jar" dev.lesson.cli.Main
```

Stdout vẫn là:

```text
GREETING=Hello, Maven!
```

**Không sử dụng `java -jar` ở đây:** ví dụ dùng Maven Jar Plugin chuẩn, chưa cấu hình `Main-Class` và runtime dependency packaging để tạo executable JAR. Bài này tập trung vào **CI-friendly versions và consumer POM**, không nhầm tính runnable của Java main với executable JAR.

## 7. Đổi version trong toàn reactor mà không sửa source

Tất cả lệnh chạy tại root.

### Thử revision mới

```bash
mvn -B -ntp -Drevision=1.5.0 clean verify
```

Với sha1 rỗng và changelist default, artifacts mang version:

```text
greeter-core-1.5.0-SNAPSHOT.jar
greeter-cli-1.5.0-SNAPSHOT.jar
```

Cả parent và children resolve cùng version, dependency CLI -> core cũng theo `1.5.0-SNAPSHOT` vì dùng `${project.version}`.

### Thử commit suffix

```bash
mvn -B -ntp -Drevision=1.5.0 -Dsha1=-gabc123 -Dchangelist=-SNAPSHOT clean verify
```

Kỳ vọng artifact names:

```text
greeter-core-1.5.0-gabc123-SNAPSHOT.jar
greeter-cli-1.5.0-gabc123-SNAPSHOT.jar
```

### Thử release version

```bash
mvn -B -ntp -Drevision=1.5.0 -Dsha1= -Dchangelist= clean verify
```

Kỳ vọng:

```text
greeter-core-1.5.0.jar
greeter-cli-1.5.0.jar
```

Đây mới chỉ là build với **release-like version string**, không tự tạo tag, signature hay upload artifact vào release repository.

### Chọn module và phụ thuộc với `-pl` và `-am`

```bash
mvn -B -ntp -pl greeter-cli -am clean verify
```

`-pl` chọn module CLI, `-am` giúp reactor build các module liên quan mà CLI cần, cụ thể là `greeter-core` trong ví dụ. Nếu bỏ `-am` và local repository không có core đúng version, Maven có thể không resolve được dependency.

## 8. Kiểm tra version Maven thật sự đã hiểu

### 8.1. Maven version khác project version

```bash
mvn -version
```

chỉ cho biết Maven distribution và Java runtime, không trả lời project sẽ phát hành với version nào.

Để xem project version ở root:

```bash
mvn -q help:evaluate -Dexpression=project.version -DforceStdout
```

Giá trị mong đợi:

```text
1.4.0-SNAPSHOT
```

Với overrides:

```bash
mvn -q -Drevision=1.5.0 -Dsha1=-gabc123 -Dchangelist=-SNAPSHOT help:evaluate -Dexpression=project.version -DforceStdout
```

Giá trị mong đợi:

```text
1.5.0-gabc123-SNAPSHOT
```

Đây là **giá trị expression**; Maven/plugins có thể in thêm log hoặc hints tùy cấu hình, không nên parse full console output bằng string equality một cách thiếu kiểm soát.

### 8.2. Xem module cụ thể

```bash
mvn -q -pl greeter-cli help:evaluate -Dexpression=project.version -DforceStdout
```

Với defaults, module version cũng là `1.4.0-SNAPSHOT`. Nếu hệ thống thực có profiles hoặc modules dùng versions riêng, phải kiểm tra đúng project.

### 8.3. Effective POM

```bash
mvn help:effective-pom
mvn help:active-profiles
```

Các lệnh giúp kiểm tra parent inheritance, properties, plugin management và dependency versions. **Effective POM không nhất thiết chính là POM sẽ được install/deploy**, vì Flatten Plugin có thể thay project POM file sau khi goal chạy.

## 9. Vì sao phải Flatten khi Maven 3 install/deploy?

Trong reactor, Maven biết `revision`, `sha1` và `changelist`. Nhưng consumer đứng ngoài reactor không phải lúc nào cũng có cùng properties và context build. Nếu Maven 3 publish POM nguyên văn còn:

```xml
<version>${revision}${sha1}${changelist}</version>
```

thì một consumer có thể gặp lỗi resolve parent/dependency metadata, dù tên file JAR artifact đúng.

Một lỗi **minh họa**, không phải toàn bộ output:

```text
Could not find artifact dev.lesson:ci-friendly-demo:pom:${revision}${sha1}${changelist}
```

Tài liệu Maven chính thức khuyến nghị **Flatten Maven Plugin** cho Maven 3 CI-friendly versions khi muốn `install` hoặc `deploy` POMs dùng được bởi consumer.

### 9.1. `flattenMode=resolveCiFriendliesOnly`

```xml
<configuration>
    <updatePomFile>true</updatePomFile>
    <flattenMode>resolveCiFriendliesOnly</flattenMode>
</configuration>
```

Với mode này, Flatten Maven Plugin thay **CI-friendly placeholders** bằng giá trị resolved nhưng giữ các phần còn lại theo policy của mode. Nó khác các flatten modes có thể loại bỏ parent, build/plugins, metadata hoặc dependencies mạnh hơn.

### 9.2. `updatePomFile=true` trong parent packaging `pom`

Theo docs Flatten Plugin, mặc định generated flattened POM được trỏ làm project POM file cho dự án có packaging **khác `pom`**. Với parent POM có packaging `pom`, cần đặt `updatePomFile=true` nếu muốn parent dùng flattened POM để install/deploy.

Nếu chỉ có file `.flattened-pom.xml` nhưng `install` vẫn dùng original POM, consumer có thể tiếp tục gặp unresolved placeholder problem.

### 9.3. Bind flatten trước khi install/deploy

Execution `flatten:flatten` ở `process-resources` giúp tạo POM đã resolve trước giai đoạn `package/install/deploy`:

```xml
<execution>
    <id>flatten-ci-versions</id>
    <phase>process-resources</phase>
    <goals>
        <goal>flatten</goal>
    </goals>
</execution>
```

Execution `flatten:clean` ở clean lifecycle dọn file generated. POM hoàn chỉnh ở mục 6 đã khai cả hai goals. Chạy `mvn clean install` từ root giúp build và cài đặt các modules cùng parent đúng phiên bản.

### 9.4. Generated `.flattened-pom.xml`

Sau build, có thể có:

```text
ci-friendly-demo/.flattened-pom.xml
ci-friendly-demo/greeter-core/.flattened-pom.xml
ci-friendly-demo/greeter-cli/.flattened-pom.xml
```

Kiểm tra **file thực tế**, không tự sửa:

- `<version>` của project là concrete version?
- `<parent><version>` trong child có concrete value?
- Các placeholder `${revision}`, `${sha1}`, `${changelist}` được thay ở những fields cần?
- Các dependency, dependencyManagement và plugin metadata quan trọng còn được giữ theo policy?
- File nào sẽ được Maven Install/Deploy Plugin dùng thật?

Trong nhiều repositories, `.flattened-pom.xml` được `.gitignore` vì là generated output, nhưng cần tuân chính sách source-control của project.

## 10. Build, install và thử consumer độc lập

### 10.1. Install reactor

```bash
mvn -B -ntp clean install
```

Với defaults, artifact coordinates là:

```text
dev.lesson:ci-friendly-demo:pom:1.4.0-SNAPSHOT
dev.lesson:greeter-core:jar:1.4.0-SNAPSHOT
dev.lesson:greeter-cli:jar:1.4.0-SNAPSHOT
```

Các paths mặc định trong Maven local repository có dạng:

```text
~/.m2/repository/dev/lesson/ci-friendly-demo/1.4.0-SNAPSHOT/
~/.m2/repository/dev/lesson/greeter-core/1.4.0-SNAPSHOT/
~/.m2/repository/dev/lesson/greeter-cli/1.4.0-SNAPSHOT/
```

Nếu `settings.xml` chỉ định `localRepository` khác, paths thực tế sẽ khác. Đây chỉ là sơ đồ để biết cần kiểm tra ở đâu.

### 10.2. Kiểm tra installed POM thay vì chỉ tên JAR

Trong POM đã install, version cụ thể cần xuất hiện, ví dụ:

```xml
<version>1.4.0-SNAPSHOT</version>
```

Child POM cũng cần parent version cụ thể. Nếu vẫn có `${revision}${sha1}${changelist}` tại vị trí version quan trọng, điều tra execution `flatten`/`updatePomFile`, inherited plugin và Maven Install Plugin POM source.

**Tên JAR đúng không chứng minh POM publish đúng.** Điều đó đặc biệt nguy hiểm nếu project build được trong reactor nhưng consumer bên ngoài không resolve parent/dependencies.

### 10.3. Consumer POM độc lập

Một project khác, **không khai ba CI-friendly properties**, có thể dùng POM:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.consumer</groupId>
    <artifactId>greeter-consumer</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>greeter-core</artifactId>
            <version>1.4.0-SNAPSHOT</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là POM của một **consumer khác**, không thêm nó vào reactor. Nếu source `src/main/java/dev/consumer/App.java` là:

```java
package dev.consumer;

import dev.lesson.core.Greeter;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.greet("consumer"));
    }
}
```

thì sau khi `greeter-core` được install đúng, chạy:

```bash
mvn -B -ntp clean compile
```

có thể resolve dependency và compile class. **Stdout khi chạy App.main với runtime classpath có chứa core JAR**, không phải stdout của `mvn compile`:

```text
Hello, consumer!
```

Consumer example chứng minh việc POM concrete version có ích. Còn chạy Java cần cấp runtime classpath hoặc app packaging tương ứng; `mvn compile` không tự start chương trình.

## 11. CI snapshots và release: ví dụ các command thực tế

### CI kiểm thử bình thường

```bash
mvn -B -ntp -Drevision=1.4.0 -Dsha1= -Dchangelist=-SNAPSHOT clean verify
```

Tất cả modules dùng `1.4.0-SNAPSHOT`. Chưa upload artifacts lên repository.

### CI gắn commit suffix

Linux Bash với repo đã checkout đúng commit:

```bash
COMMIT_SHORT="$(git rev-parse --short=7 HEAD)"
mvn -B -ntp -Drevision=1.4.0 "-Dsha1=-g${COMMIT_SHORT}" -Dchangelist=-SNAPSHOT clean verify
```

Nếu `COMMIT_SHORT=abc1234` thì resolved version là:

```text
1.4.0-gabc1234-SNAPSHOT
```

Đây là **script Bash minh họa**. Trên PowerShell cần cú pháp biến/command substitution tương ứng. Đừng xây command từ raw branch name hoặc string không tin cậy; CI phải validate input.

Commit short hash không bảo đảm uniqueness tuyệt đối và không thay cho full Git SHA/provenance; cần lưu các thông tin đó trong build record/SBOM/artifact metadata phù hợp.

### CI build release version

```bash
mvn -B -ntp -Drevision=1.4.0 -Dsha1= -Dchangelist= clean verify
```

Nếu release QA thành công và project có repository policy/credentials:

```bash
mvn -B -ntp -Drevision=1.4.0 -Dsha1= -Dchangelist= deploy
```

**Không chạy lệnh `deploy` lên repository thật khi chưa có quyền và quy trình phát hành.** Nó upload Maven artifact/POM, không tạo Git tag, không push Docker image và không deploy service.

Hai invocations `verify` và `deploy` có thể tái thực hiện một phần build. Với hệ thống yêu cầu artifact bất biến, cần đảm bảo artifact được kiểm thử và artifact phát hành thực sự là **cùng nội dung đã QA** hoặc chứng minh rebuild reproducible. Không nên test version SNAPSHOT rồi âm thầm phát hành version release khác mà không kiểm tra artifact cuối.

## 12. Parent POM, BOM, dependencyManagement và metadata consumer

Một root parent có thể chứa `dependencyManagement`, `pluginManagement` và `properties` quan trọng cho children và consumer. Khi Flatten POM:

- `resolveCiFriendliesOnly` được chọn để giải quyết các CI-friendly variables nhưng giữ phần lớn mô hình POM, tránh làm mất cấu hình cần thiết.
- Nếu POM là **BOM** chuyên để import, Flatten Plugin còn có `flattenMode=bom`, nhưng đó là chính sách nội dung POM khác; không tự thay `resolveCiFriendliesOnly` bằng `bom` nếu không kiểm tra mục đích/metadata.
- `groupId/artifactId/version` của parent cần concrete nếu consumer resolve theo repository GAV.
- Dependency version của internal modules nên phản ánh **resolved project version**, không phải một property chưa được khai ở consumer.
- `pluginManagement` quản lý plugin versions, không tự bind Failsafe hay một goal tùy ý vào lifecycle.
- CI-friendly properties không phải Maven BOM: chúng không tự quản lý hàng loạt versions của external dependencies.

Nếu project dựa vào external parent hoặc BOM, hãy kiểm tra **POM thực tế được publish** có đủ metadata theo đúng policy. Không mặc định “một file `.flattened-pom.xml` tồn tại” là đủ.

## 13. Maven 3 và Maven 4: phạm vi áp dụng khác nhau

Maven 4 có tài liệu riêng cho **multi-subproject builds với model 4.1.0**. Nó cải tiến automatic version resolution của parent/subproject và dependencies.

| Tính năng | Maven 3 + model 4.0.0 | Maven 4 + model 4.1.0 |
| --- | --- | --- |
| CI-friendly version placeholders | `revision`/`sha1`/`changelist` được hỗ trợ | Có cơ chế tiếp tục/cải tiến trong Maven 4 |
| Child parent version | Phải khai theo cú pháp tương thích Maven 3, có thể dùng CI-friendly placeholder | Có khả năng auto-detect parent/version theo mô hình mới |
| Dependency giữa modules | Dùng `${project.version}` cho same-version modules | Có thể bỏ version trong trường hợp subproject auto-versioning phù hợp |
| Install/deploy POM CI-friendly | Thường cần Flatten Plugin | Theo docs Maven 4 model 4.1.0 với automatic versioning, không còn cần Flatten như trong Maven 3 |
| POM và plugin compatibility | Maven 3 conventions | Có các thay đổi model/plugins, cần migration riêng |

**Bài thực hành này cố ý dùng Maven 3 + model 4.0.0**. Không xóa parent version hoặc inter-module dependency version khỏi các POM ví dụ chỉ vì thấy tài liệu Maven 4. Hãy đọc migration guide đúng Maven version trước khi đổi chiến lược.

## 14. Phân biệt CI-friendly với Versions và Release Plugins

- **Versions Maven Plugin** có thể chỉnh các version hiện có trong POM, phù hợp khi dự án muốn version changes được ghi nhận bằng Git commit.
- **Maven Release Plugin** hỗ trợ quy trình prepare/tag/perform theo cấu hình SCM và repository, không phải chỉ một expression trong `<version>`.
- **CI-friendly placeholders** cho phép một source tree được build với nhiều resolved versions từ CI mà không sửa POM trong mỗi invocation.

Không có lựa chọn “tốt nhất” cho mọi team. Nếu release governance yêu cầu một commit riêng cập nhật version và tag, cách version literal có thể đơn giản hơn. Nếu CI gán version từ Git tag/build context, CI-friendly có thể giảm thay đổi POM và hỗ trợ reactor đồng nhất.

**CI-friendly không tự bảo đảm semantic versioning.** CI phải validate version format, không reuse release version bất hợp pháp và duy trì phát hành bất biến theo repository policy.

## 15. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Project version chứa literal `${buildVersion}` | Dùng property ngoài ba CI-friendly names ở version Maven 3 | Dùng `revision`/`sha1`/`changelist` hoặc cơ chế versioning khác |
| Version thành `1.4.0-SNAPSHOT-SNAPSHOT` | Suffix SNAPSHOT bị thêm hai lần | Revision không chứa suffix nếu changelist đã `-SNAPSHOT` |
| Version thành `1.4.0SNAPSHOT` | Changelist thiếu dấu gạch ngang | Dùng `-SNAPSHOT` |
| `sha1` rỗng dù có Git repo | Maven không tự đọc commit ID | CI phải truyền `-Dsha1=...` |
| CLI module không tìm core module | Inter-module dependency dùng `${revision}` thay `${project.version}` | Sửa dependency version |
| Root build pass, consumer thất bại | Published POM còn unresolved CI-friendly placeholders | Flatten Plugin và consumer test |
| Parent POM install còn placeholder | Parent packaging `pom` chưa dùng flattened POM | Kiểm tra `updatePomFile=true` và execution |
| `.flattened-pom.xml` không được sinh | Flatten goal chưa được bind/phase không chạy | Xem effective POM và Maven log |
| Version Help Plugin khác POM default | CLI `-D`, `maven.config`, profile khác | Xem project version effective |
| `-pl greeter-cli` fail, root build pass | Core version chưa có trong local repo và không được build | Thêm `-am` |
| `mvn deploy` sang sai repository | `distributionManagement`/settings/credentials sai | Kiểm tra repository config và policy |
| Release artifact bị overwrite | Tái dùng version release cũ | Bật immutable release policy, kiểm tra tags/digests |
| Maven 3 POM thiếu parent version vì áp dụng Maven 4 guide | Trộn model 4.1.0 với 4.0.0 | Giữ Maven 3-compatible declarations |
| Artifact JAR đúng tên nhưng metadata bị lỗi | Chỉ xem filename, không xem POM publish | Kiểm tra installed/deployed POM |
| Version dùng raw Git branch không hợp lệ | Input chưa được normalize/validate | Dùng sanitized version string từ CI |

### Lệnh kiểm tra

```bash
mvn -version
mvn help:active-profiles
mvn help:effective-pom
mvn -q help:evaluate -Dexpression=project.version -DforceStdout
mvn -B -ntp clean verify
```

Nếu cần thêm thông tin:

```bash
mvn -B -ntp -e clean install
mvn -B -ntp -X clean install
```

`-X` có thể in local paths, repository URLs, system properties, một phần cấu hình nhạy cảm. Không đăng debug logs chưa lọc lên nơi công khai; không dùng production deploy để “thử cờ version”.

## 16. Bài tập tự kiểm tra

**Câu 1.** POM có `<version>${revision}${sha1}${changelist}</version>`, mặc định revision=1.4.0, sha1 rỗng, changelist=-SNAPSHOT. Version là gì?

**Đáp án:** `1.4.0-SNAPSHOT`.

**Câu 2.** Chạy `-Drevision=2.0.0 -Dsha1= -Dchangelist=`. Version là gì?

**Đáp án:** `2.0.0`.

**Câu 3.** Có thể dùng `${ciVersion}` thay `${revision}` trong vị trí project version với Maven 3 không?

**Đáp án:** Không theo cơ chế CI-friendly đặc biệt. Dùng đúng ba tên property hỗ trợ.

**Câu 4.** Maven có tự tính `sha1` từ Git HEAD không?

**Đáp án:** Không. CI phải truyền property nếu muốn commit suffix.

**Câu 5.** Composite version resolved là `1.4.0-gabc123-SNAPSHOT`. Dependency trong cùng reactor dùng `${revision}` hay `${project.version}`?

**Đáp án:** Dùng `${project.version}` để tham chiếu đủ version.

**Câu 6.** `mvn clean package` pass trong reactor có đủ chứng minh consumer Maven cài được dependency ngoài reactor?

**Đáp án:** Không. Cần kiểm tra POM được install/deploy, flatten đúng và thử consumer độc lập.

**Câu 7.** Vì sao `<updatePomFile>true</updatePomFile>` cần lưu ý trên parent packaging `pom`?

**Đáp án:** Nếu chỉ tạo flattened POM nhưng Maven install parent POM gốc thì consumer vẫn có thể gặp placeholder chưa resolve. Cấu hình này cho phép plugin chỉ định flattened POM được dùng.

**Câu 8.** `flattenMode=resolveCiFriendliesOnly` có mục đích xóa toàn bộ dependencies không?

**Đáp án:** Không. Nó giải quyết CI-friendly placeholders và giữ phần lớn mô hình POM khác.

**Câu 9.** Maven 4 model 4.1.0 có auto-versioning cho subprojects, vậy Maven 3 có thể bỏ child parent version giống vậy không?

**Đáp án:** Không. Hai model có quy tắc khác nhau; demo dùng Maven 3 model 4.0.0.

**Câu 10.** `-Dchangelist=` có tự push artifact hoặc tạo Git tag không?

**Đáp án:** Không. Nó chỉ ảnh hưởng resolved project version của invocation.

## 17. Checklist áp dụng trong CI thật

- [ ] Biết Maven distribution và POM model version của repository.
- [ ] Chỉ dùng `revision`, `sha1`, `changelist` làm project version placeholders trên Maven 3.
- [ ] POM có defaults giúp developer build không cần CI.
- [ ] Không để revision và changelist thêm `-SNAPSHOT` hai lần.
- [ ] CI truyền version overrides tường minh và nhất quán giữa jobs/modules.
- [ ] Không giả định Maven tự lấy Git hash cho `sha1`.
- [ ] CI xác minh Git commit thực tế và lưu full SHA/provenance riêng.
- [ ] Parent và child POMs dùng cùng composite version policy.
- [ ] Inter-module dependencies dùng `${project.version}`.
- [ ] `mvn help:evaluate` cho thấy version dự kiến.
- [ ] Không nhầm Maven distribution version với project artifact version.
- [ ] Flatten Maven Plugin chạy trước install/deploy.
- [ ] `flattenMode=resolveCiFriendliesOnly` đúng mục đích consumer metadata.
- [ ] Parent packaging `pom` sử dụng flattened POM khi cần, với `updatePomFile=true`.
- [ ] Đã kiểm tra generated flattened POM và **installed POM**.
- [ ] Có consumer test không khai CI-friendly properties.
- [ ] Không chỉ nhìn tên JAR mà tuyên bố Maven repository metadata đúng.
- [ ] Release repository không cho overwrite version đã phát hành theo policy.
- [ ] Không đẩy secrets/token vào POM/CLI logs.
- [ ] Đã chạy unit tests và kiểm tra reports trước khi release.
- [ ] Phân biệt Maven 3 rules với Maven 4 model 4.1.0.
- [ ] CI-friendly version được xem là cơ chế đặt tên, không thay release/QA/security workflow.

**Kết luận:** Trong Maven 3, CI-friendly versions dùng **`${revision}`, `${sha1}` và `${changelist}`** để tính project version mà không cần sửa POM mỗi lần CI chạy. Với reactor nhiều module, khai dependency nội bộ bằng **`${project.version}`**. Khi install/deploy, dùng **Flatten Maven Plugin** hoặc một cơ chế xuất POM tương đương đã được xác minh để consumer không phải giải unresolved placeholders. Đừng nhầm việc tạo version string với việc ký, phát hành hoặc deploy artifacts.

## Nguồn chính thức

- [Apache Maven — Maven CI Friendly Versions](https://maven.apache.org/guides/mini/guide-maven-ci-friendly.html)
- [MojoHaus — Flatten Maven Plugin Usage](https://www.mojohaus.org/flatten-maven-plugin/usage.html)
- [MojoHaus — flatten:flatten Goal Parameters](https://www.mojohaus.org/flatten-maven-plugin/flatten-mojo.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Guide to Configuring Maven](https://maven.apache.org/configure.html)
- [Apache Maven — Maven 4 Migration Guide](https://maven.apache.org/guides/mini/guide-migration-to-mvn4.html)

*Dự án minh họa dựa trên Maven 3, POM model 4.0.0, Java 17, Flatten Maven Plugin 1.8.0, JUnit Jupiter 5.11.4 và Maven plugins đã pin. Các lệnh phát hành thật cần kiểm tra repository/credentials, consumer POM và quy trình kiểm soát chất lượng.*
