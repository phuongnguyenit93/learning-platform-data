# Kiểm tra khả năng an toàn khi chạy plugin song song trong Maven

## 1. Vì sao tối ưu hiệu năng phải đi cùng tính đúng đắn?

Một dự án Java đa module dùng Maven có thể chạy tuần tự rất lâu. Để tận dụng CPU của máy phát triển hoặc CI runner, nhóm muốn chuyển:

~~~bash
mvn -B -ntp -T 1 clean verify
~~~

sang:

~~~bash
mvn -B -ntp -T 2 clean verify
~~~

Maven 3 có **parallel reactor build**, cho phép các Maven modules không còn phụ thuộc nhau được xử lý trên nhiều worker threads. Nhưng đây không phải “chế độ tự động làm mọi plugin an toàn”. Cùng lúc chạy nhiều goals có thể làm lộ xung đột file, port, database, temporary directories, system properties, caches và shared mutable state.

Một plugin được đánh dấu `threadSafe=true` có thể vẫn được cấu hình **ghi chung một thư mục** ở hai modules, hoặc gọi test code không an toàn. Ngược lại, Maven phát cảnh báo “goal not marked thread-safe” không có nghĩa mọi lần chạy đều thất bại; đó là một tín hiệu cần đánh giá.

**Mục tiêu của bài học thuộc nhóm Hiệu năng:**

1. Phân biệt parallel module builds, test JVM forks và concurrent test methods.
2. Đọc Reactor dependency graph để hiểu module nào được chạy cùng lúc.
3. Hiểu thuộc tính `threadSafe` của **Mojo/goal**, không nhầm với tên plugin.
4. Biết cách tra cứu đúng goal, đúng version, descriptor `META-INF/maven/plugin.xml` và cảnh báo Maven.
5. Phát hiện nguy cơ concurrent access vào files, ports, database, caches, temp và singleton state.
6. Thiết kế mục tiêu kiểm thử: baseline tuần tự, run song song, stress/repeat, so reports và outputs.
7. Tạo project Java 17 đa module `core`, `east`, `west` có JUnit Jupiter test, chạy được với `-T 1` và `-T 2`.
8. Hiểu tác động của Surefire/Failsafe `forkCount`, `reuseForks` và `${surefire.forkNumber}`.
9. Thiết lập CI so sánh hai chế độ và giữ reports khi build fail.
10. Ra quyết định có bằng chứng: nâng plugin, sửa isolation hoặc giữ build tuần tự khi chưa an toàn.

Phần thực hành dùng Maven 3.8+, Java 17, Maven Compiler Plugin 3.13.0, Surefire 3.5.4 và JUnit Jupiter 5.11.4. Đây là phiên bản ví dụ được ghim để dễ tái hiện, không phải lời khẳng định phiên bản mới nhất.

## 2. Bốn loại song song hóa cần phân biệt

| Tầng | Điều khiển | Có thể chạy đồng thời |
| --- | --- | --- |
| Maven reactor | `mvn -T N` | Các Maven modules mà dependency graph cho phép. |
| Maven Surefire/Failsafe | `forkCount`, `reuseForks` | Một hoặc nhiều **JVM processes** chạy tests ở từng module. |
| Test framework | JUnit Jupiter parallel options hoặc TestNG/JUnit provider. | Methods/classes trên threads trong một test JVM. |
| Plugin/external tool | Compiler, code generator, npm, Docker, DB process, shell. | Threads/processes được goal tự tạo. |

Ví dụ có 2 reactor workers và `forkCount=2` trên hai modules cùng bước test, có thể có tối đa **4 test JVM forks** đang thực thi (trong điều kiện đủ test workload); Maven process và threads khác vẫn tồn tại.

Một số người thấy `-T 2` và hiểu là toàn build chỉ có hai threads. Điều đó không đúng: `-T` giới hạn **reactor scheduling concurrency**, không phải tổng số OS threads, JVMs hay network connections.

### Plugin thread-safe chưa đủ bảo đảm tests thread-safe

Surefire goal có thể hỗ trợ parallel module build nhưng hai integration test suites dùng cùng port 8080 sẽ xung đột khi đồng thời khởi động server. Tương tự, Compiler Plugin hỗ trợ parallel builds nhưng cấu hình hai modules cùng ghi vào một output directory có thể làm mất file.

Cần xem **mỗi tầng** và **tài nguyên thực sự bị truy cập**, không chỉ cờ CLI.

## 3. Reactor graph quyết định concurrency thực tế

Project minh họa:

~~~text
          parent (pom)
                │
                ▼
            core (jar)
             /    \
            ▼      ▼
        east       west
         jar        jar
~~~

`east` và `west` phụ thuộc `core`, không phụ thuộc nhau.

Khi chạy:

~~~bash
mvn -B -ntp -T 2 clean verify
~~~

Maven cần xử lý các project predecessors phù hợp dependency graph trước khi dependent module có thể dùng artifact của họ. Sau đó `east` và `west` có thể chạy song song.

**Lưu ý:** không suy luận thời điểm bắt đầu/kết thúc chỉ từ thứ tự các dòng console. Logs của nhiều modules có thể xen kẽ. Reactor Summary và per-module reports đáng tin hơn để xác định modules đã PASS/FAIL.

### Các chế độ `-T`

~~~bash
mvn -T 1 clean verify
mvn -T 2 clean verify
mvn -T 4 clean verify
mvn -T 1C clean verify
mvn -T 1.5C clean verify
~~~

- `-T 1`: baseline tuần tự với một reactor worker.
- `-T 2`: tối đa hai reactor workers.
- `-T 4`: tối đa bốn, không bảo đảm có bốn modules runnable cùng lúc.
- `-T 1C`: số threads theo hệ số CPU cores mà Maven phát hiện.
- `-T 1.5C`: số threads theo 1,5 lần số cores, có thể dùng nhiều memory và I/O hơn.

**Critical path:** nếu graph là chuỗi `A → B → C → D`, thêm threads không tạo ra các modules độc lập. Nếu chỉ có một module, `-T 4` gần như không giúp module ấy tự chạy bốn goals cùng lúc.

### Dependency graph không hiểu shared external resources

Maven thấy POM dependency `east → core`, nhưng không thấy cả `east` và `west` cùng dùng database schema `test`, port 5432, hoặc `../shared-output`. Đây là **hidden dependencies**. Chính chúng thường làm build song song flaky.

Một graph Maven đúng là điều kiện cần, nhưng chưa đủ để khẳng định run song song an toàn.

## 4. `@Mojo(threadSafe = true)` nghĩa chính xác là gì?

Maven Plugin Tools có annotation:

~~~java
@Mojo(name = "audit", threadSafe = true)
public class AuditMojo extends AbstractMojo {
    // An example of a Maven plugin goal declaration.
}
~~~

Đây là **mảnh Java minh họa**, không phải custom plugin có thể biên dịch độc lập: còn cần imports, các dependencies của Maven Plugin API, method `execute()`, project packaging và descriptor generation.

Một plugin descriptor có thể có đoạn:

~~~xml
<mojo>
    <goal>audit</goal>
    <threadSafe>true</threadSafe>
</mojo>
~~~

Đây là fragment `META-INF/maven/plugin.xml`, không phải toàn bộ XML descriptor.

Theo Maven Mojo API specification:

- `threadSafe` là metadata thuộc **từng Mojo goal**.
- Default khi không đánh dấu là `false`.
- Nó thể hiện tuyên bố của tác giả goal về khả năng hỗ trợ concurrent module execution trong Maven 3.
- Maven có thể **cảnh báo** khi parallel session chứa goals không được đánh dấu thread-safe.
- Cảnh báo **không mặc định chặn** goal hoặc chuyển build thành failure.

### Plugin-level với goal-level khác nhau

Một plugin có thể có nhiều goals: `plugin:check`, `plugin:report`, `plugin:generate`. Chỉ vì `report` thread-safe không có nghĩa `generate` cũng như vậy.

Vì vậy khi audit, cần ghi **full GAV + goal + version**, ví dụ:

~~~text
groupId: org.apache.maven.plugins
artifactId: maven-compiler-plugin
version: 3.13.0
goal: compile
phase: compile
Mojo thread-safety: kiểm đúng descriptor/docs của version
configuration: outputDirectory, compiler args, fork/toolchain...
modules: core, east, west
external resources: project build directories
~~~

Chữ “thread-safe” ở trang docs mới hơn không tự chứng minh plugin version cũ cũng đã implement/đánh dấu thuộc tính đó.

### Metadata không thay thế kiểm tra configuration

`threadSafe=true` **không** kiểm rằng:

- Hai modules có output directories khác nhau.
- Tests dùng ports/schemas khác nhau.
- External scripts có locking hoặc file writes atomic.
- Plugin dependency overrides không thay behavior.
- Remote services cho phép concurrency ở mức đó.
- Developer không vô tình dùng singleton không an toàn trong test runtime.

Do đó một build có tất cả goals marked threadSafe vẫn có thể FAIL do shared state **ngoài plugin implementation**.

## 5. Tra cứu an toàn song song của plugin/goal

**Quy trình xác minh đề xuất:**

1. Xác định plugin full GAV và goals thực sự được gọi.
2. Tra trang goal documentation của **đúng version**.
3. Tìm thông tin “The goal is thread-safe and supports parallel builds.”
4. Nếu cần bằng chứng kỹ thuật, kiểm tra JAR descriptor `META-INF/maven/plugin.xml` của version đó.
5. Đọc release notes/issues và plugin dependencies.
6. Xem effective POM để xác nhận inherited configuration, executions/phases và active profiles **sau khi project đã được review và môi trường đủ an toàn**.
7. Đánh giá output dirs, environment, files, ports và databases.
8. Chạy baseline tuần tự, song song và stress run trên runner không secrets.

Ví dụ URL chính thức:

- `compiler:compile`: https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html
- `surefire:test`: https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html
- Maven Plugin API — Mojo Descriptor: https://maven.apache.org/ref/3.9.9/maven-plugin-api/plugin.html

Đọc **đúng tài liệu version** hoặc archived goal docs; trang “latest” có thể đã chuyển plugin version kể từ lúc bạn ghim POM.

### Đọc binary descriptor

Với Maven Compiler Plugin JAR đã được tải từ repository được phép, trên Linux/macOS có thể dùng:

~~~bash
unzip -p "$HOME/.m2/repository/org/apache/maven/plugins/maven-compiler-plugin/3.13.0/maven-compiler-plugin-3.13.0.jar" META-INF/maven/plugin.xml
~~~

Tìm phần tử `<mojo>` chứa `<goal>compile</goal>` rồi xem `<threadSafe>` **trong cùng phần tử đó**. Không lấy flag của goal khác. Lệnh chỉ đọc dữ liệu ZIP; nếu trên Windows không có unzip, dùng ZIP viewer/IDE tương đương.

### Vì sao không chỉ chạy `help:effective-pom`?

Lệnh:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

giúp xem parent inheritance, plugin/execution configuration và active model, nhưng **không tự hiển thị toàn bộ Mojo descriptor metadata**. Ngoài ra Maven có thể nạp core extensions hoặc resolve/execute Help Plugin khi chạy. Với repository chưa tin cậy, hãy static-review POM, `.mvn/extensions.xml`, wrapper và script trước khi gọi Maven.

### Warning của Maven

Trong parallel build, Maven có thể báo ý nghĩa tương đương:

~~~text
Your build is requesting parallel execution, but this project contains
plugins that have goals not marked as thread-safe.
~~~

Thông điệp trên **rút gọn để minh họa**; nội dung thực có thể liệt kê plugin versions hoặc goals.

- **Có warning**: chưa có guarantee thread-safety từ metadata, phải đánh giá/khắc phục.
- **Không warning**: không chứng minh mọi cấu hình/test fixture an toàn.
- **Build SUCCESS một lần**: không chứng minh không tồn tại race hiếm.
- **Build FAILURE**: cần xác định goal/module/root cause, không đổ ngay cho Maven scheduler.

Không được tự sửa `plugin.xml` để thay `threadSafe=false` thành true hoặc lọc warning khỏi logs: đó không thay đổi implementation.

## 6. Các nguồn xung đột trong parallel Maven builds

| Thành phần | Anti-pattern | Hậu quả có thể xảy ra |
| --- | --- | --- |
| Build output | Cả hai modules cùng `../shared-target`. | Ghi đè/xóa file nhau. |
| Code generation | Generator dùng một root `generated-sources` chung. | Race khi xóa/tạo Java files. |
| Report output | XML coverage/test reports ghi chung đường dẫn. | File hỏng/được overwrite. |
| Temp files | Tên file cố định trong OS temp. | Đọc dữ liệu lẫn lộn. |
| Port | Hai test servers cùng bind 8080. | `BindException`, test FAIL. |
| Database | Hai modules reset cùng schema. | Migration/data race. |
| System properties | Goal/test dùng `System.setProperty` toàn JVM. | Cấu hình thay đổi bất định. |
| Static fields | Plugin giữ mutable static counters/maps. | Lost updates, cross-module state. |
| Singleton components | Plexus/Sisu object chia sẻ mutable state. | Data corruption hoặc nondeterminism. |
| Unsafe libraries | Shared `SimpleDateFormat` static. | Parse/format lỗi dưới contention. |
| Docker/npm | Các scripts cùng build chung folder/image tag. | Race giữa subprocesses. |
| Cache | Custom script chỉnh cùng file cache mà không lock. | Cache corruption. |
| HTTP service | Nhiều module gọi endpoint bị rate limit. | 429, timeouts, tăng latency. |
| Publishing | Hai jobs/deploy goals xuất cùng GAV/version. | Conflict/partial publication. |

Các resources có thể được **đọc đồng thời** nếu dữ liệu immutable và implementation cho phép; rủi ro nằm ở shared mutable state, không phải mọi hành vi chia sẻ tài nguyên.

### Nguyên tắc dùng output riêng cho từng module

Maven mặc định có các thư mục:

~~~text
core/target/
east/target/
west/target/
~~~

Với plugin nhận output directory, ưu tiên cấu hình theo:

~~~xml
<outputDirectory>${project.build.directory}/generated-safe</outputDirectory>
~~~

Đây là **mảnh plugin parameter**; phải dùng tại plugin thật sự có `outputDirectory`, không copy bừa vào root POM. `${project.build.directory}` mặc định là `target` của module hiện tại.

**Anti-pattern — KHÔNG áp dụng vào bài lab:**

~~~xml
<build>
    <directory>../shared-target</directory>
</build>
~~~

Nếu cả `east` và `west` dùng đường dẫn tương đối này, chúng có thể tranh cùng thư mục. `mvn clean` còn có thể xóa output do module khác cần.

### Đừng quên cấu hình phụ

Dù `build.directory` là riêng, plugin có thể có parameters khác: `workingDirectory`, `reportOutputDirectory`, `tempDirectory`, `cacheDirectory`, `outputFile` hoặc user properties. Review **tất cả đường dẫn và side effects thực tế**.

## 7. Project Java 17 đa module để kiểm chứng

Ta tạo một project hoàn chỉnh:

~~~text
maven-parallel-safety-lab/
├── pom.xml
├── core/
│   ├── pom.xml
│   ├── src/main/java/demo/parallel/core/CoreText.java
│   └── src/test/java/demo/parallel/core/CoreTextTest.java
├── east/
│   ├── pom.xml
│   ├── src/main/java/demo/parallel/east/EastService.java
│   └── src/test/java/demo/parallel/east/EastServiceTest.java
└── west/
    ├── pom.xml
    ├── src/main/java/demo/parallel/west/WestService.java
    └── src/test/java/demo/parallel/west/WestServiceTest.java
~~~

**Quan hệ:** `core` cung cấp class `CoreText`; `east` và `west` cùng phụ thuộc `core` nhưng không phụ thuộc nhau. Trong Java code không có file/network/port/global mutable state, nhằm làm rõ Maven scheduling và báo cáo test, không tạo lỗi concurrency cố ý.

### 7.1. Parent `pom.xml` hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.parallel</groupId>
    <artifactId>parallel-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>east</module>
        <module>west</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.11.4</junit.version>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-clean-plugin</artifactId>
                    <version>3.4.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-resources-plugin</artifactId>
                    <version>3.3.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.4</version>
                    <configuration>
                        <forkCount>1</forkCount>
                        <reuseForks>true</reuseForks>
                        <failIfNoTests>true</failIfNoTests>
                    </configuration>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

**Giải thích cấu hình parent:**

- `packaging=pom`: root là parent/aggregator, không phải Java JAR module có Surefire tests.
- `<modules>` cho Reactor biết ba subprojects.
- `pluginManagement` ghim lifecycle plugin versions/config khi plugins được dùng; không tự kích hoạt mọi custom goal.
- `maven.compiler.release=17` đặt Java bytecode/API target; Maven vẫn cần runtime JDK phù hợp.
- `forkCount=1` làm mỗi module có tối đa một forked test JVM tại một thời điểm.
- `reuseForks=true` có thể dùng lại fork giữa test classes **trong cùng module**.
- `failIfNoTests=true` phù hợp các JAR modules của demo đều có tests; với POM-only module không bị Surefire default JAR lifecycle binding kích hoạt.
- Demo **không bật parallel methods của JUnit**: đang kiểm Maven module parallelism.

### 7.2. `core/pom.xml` hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>demo.parallel</groupId>
        <artifactId>parallel-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

### 7.3. `east/pom.xml` hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>demo.parallel</groupId>
        <artifactId>parallel-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>east</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>demo.parallel</groupId>
            <artifactId>core</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

### 7.4. `west/pom.xml` hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>demo.parallel</groupId>
        <artifactId>parallel-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>west</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>demo.parallel</groupId>
            <artifactId>core</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

**Quan trọng:** root `<modules>` giúp Maven tìm modules; **`<dependency>core</dependency>`** trong east/west mới tạo edge để Maven biết module phụ thuộc core. Nếu code dùng `CoreText` nhưng POM thiếu dependency, compile có thể fail; không nên dựa vào thứ tự thư mục.

### 7.5. `core/src/main/java/demo/parallel/core/CoreText.java`

~~~java
package demo.parallel.core;

import java.util.Objects;

public final class CoreText {
    private CoreText() {
    }

    public static String greet(String region) {
        Objects.requireNonNull(region, "region");
        return "Hello " + region + " from core";
    }
}
~~~

### 7.6. `core/src/test/java/demo/parallel/core/CoreTextTest.java`

~~~java
package demo.parallel.core;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CoreTextTest {
    @Test
    void greetsEast() {
        assertEquals("Hello east from core", CoreText.greet("east"));
    }

    @Test
    void rejectsNull() {
        assertThrows(
                NullPointerException.class,
                () -> CoreText.greet(null));
    }
}
~~~

`core` có **2 JUnit tests**, không dùng shared files hoặc network.

### 7.7. `east/src/main/java/demo/parallel/east/EastService.java`

~~~java
package demo.parallel.east;

import demo.parallel.core.CoreText;

public final class EastService {
    private EastService() {
    }

    public static String render() {
        return CoreText.greet("east") + " | east module";
    }

    public static void main(String[] args) {
        System.out.println(render());
    }
}
~~~

### 7.8. `east/src/test/java/demo/parallel/east/EastServiceTest.java`

~~~java
package demo.parallel.east;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class EastServiceTest {
    @Test
    void assemblesMessage() {
        assertEquals(
                "Hello east from core | east module",
                EastService.render());
    }
}
~~~

`east` có **1 JUnit test**.

### 7.9. `west/src/main/java/demo/parallel/west/WestService.java`

~~~java
package demo.parallel.west;

import demo.parallel.core.CoreText;

public final class WestService {
    private WestService() {
    }

    public static String render() {
        return CoreText.greet("west") + " | west module";
    }

    public static void main(String[] args) {
        System.out.println(render());
    }
}
~~~

### 7.10. `west/src/test/java/demo/parallel/west/WestServiceTest.java`

~~~java
package demo.parallel.west;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class WestServiceTest {
    @Test
    void assemblesMessage() {
        assertEquals(
                "Hello west from core | west module",
                WestService.render());
    }
}
~~~

`west` có **1 JUnit test**. Tổng **4 JUnit tests** trên ba JAR modules.

## 8. Chạy tuần tự và song song; kiểm đầu ra

Từ thư mục `maven-parallel-safety-lab` trên JDK 17+ và Maven 3.8+:

~~~bash
java -version
mvn --version
mvn -B -ntp -T 1 clean verify
~~~

**Kỳ vọng với môi trường đầy đủ:** Maven build root/core/east/west theo graph; core 2 tests, east 1, west 1; tất cả PASS; không có lỗi dependency; kết thúc `BUILD SUCCESS`.

Tiếp theo:

~~~bash
mvn -B -ntp -T 2 clean verify
~~~

**Kỳ vọng:** core sẵn sàng trước dependents; east và west có thể được build song song; các bài test vẫn PASS; output và reports giữ nguyên phạm vi module.

Đây là **kỳ vọng dựa trên project mẫu**, không phải trích log thực tế đã chạy. Không đoán thứ tự các dòng ở console vì đa luồng có thể xen kẽ.

### Kiểm report XML sau từng run

~~~text
core/target/surefire-reports/TEST-demo.parallel.core.CoreTextTest.xml
east/target/surefire-reports/TEST-demo.parallel.east.EastServiceTest.xml
west/target/surefire-reports/TEST-demo.parallel.west.WestServiceTest.xml
~~~

| Module | Tests | Failures | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: |
| `core` | 2 | 0 | 0 | 0 |
| `east` | 1 | 0 | 0 | 0 |
| `west` | 1 | 0 | 0 | 0 |

Bảng là **tiêu chí mong đợi của demo**. Nếu xuất hiện 0 tests, mất XML, lỗi compilation hay warning, phải điều tra trước khi coi song song an toàn.

### Chạy Java và stdout chính xác

Trên Linux/macOS, sau `clean verify` thành công:

~~~bash
java -cp "core/target/classes:east/target/classes" demo.parallel.east.EastService
java -cp "core/target/classes:west/target/classes" demo.parallel.west.WestService
~~~

**Stdout ứng dụng east:**

~~~text
Hello east from core | east module
~~~

**Stdout ứng dụng west:**

~~~text
Hello west from core | west module
~~~

Trên Windows PowerShell, classpath separator là `;`:

~~~powershell
java -cp "core\target\classes;east\target\classes" demo.parallel.east.EastService
java -cp "core\target\classes;west\target\classes" demo.parallel.west.WestService
~~~

Không dùng `java -jar east/target/east-1.0.0-SNAPSHOT.jar` cho demo này: JAR manifest chưa cấu hình `Main-Class`, và main cũng cần class của `core` trên classpath.

## 9. Đối chứng lặp và phát hiện race hiếm

Một build PASS **không phải chứng minh** không bao giờ race. Với test/CI được phép, dùng cùng commit/JDK/Maven/plugin versions và thử nhiều lần.

### Baseline

~~~bash
mvn -B -ntp -T 1 clean verify
~~~

Nếu baseline còn flaky thì **chưa** nên đổ lỗi do song song. Sửa test nondeterministic, dependency resolution hoặc môi trường trước.

### Parallel nhỏ và lớn

~~~bash
mvn -B -ntp -T 2 clean verify
mvn -B -ntp -T 4 clean verify
~~~

`-T 4` chỉ nên thử khi máy/CI đủ memory; với project demo có hai branches sau core nên mức tăng chưa chắc cải thiện tốc độ.

### Stress loop trong lab (Linux/macOS)

~~~bash
for i in 1 2 3 4 5; do
  echo "Parallel trial $i"
  mvn -B -ntp -T 2 clean verify || exit 1
done
~~~

### Stress loop PowerShell

~~~powershell
1..5 | ForEach-Object {
    Write-Host "Parallel trial $_"
    mvn -B -ntp -T 2 clean verify
    if ($LASTEXITCODE -ne 0) {
        throw "Parallel trial failed with exit code $LASTEXITCODE"
    }
}
~~~

Mục đích là đo độ ổn định và giữ log ở lần FAIL. Không gọi lặp `deploy` hoặc các goals có side effects trên release repository. Không chạy stress trên database production hoặc service chung nếu chưa được phép.

### Các tiêu chí so sánh

- Maven exit status và first failing goal/module.
- Số tests, failures, errors, skipped ở từng Surefire XML.
- Artifact list và đường dẫn output.
- Maven non-thread-safe warnings.
- Shared file/port/db schema sử dụng.
- Wall-clock time và peak memory.
- Tần suất lỗi, ví dụ 1/20 trials (nếu có), thay vì nói “thỉnh thoảng” không có dữ liệu.

Nếu parallel-only failure lặp lại, đó là bằng chứng mạnh cần điều tra concurrency. **Nó chưa tự chứng minh lỗi nằm ở plugin implementation**; test fixture hoặc config dùng chung có thể là nguồn chính.

## 10. Surefire/Failsafe: tổng concurrency có thể lớn hơn `-T`

Maven Surefire Plugin hỗ trợ:

- `forkCount`: số forked JVMs cho một test execution.
- `reuseForks`: tái sử dụng test JVMs.
- Framework options cho parallel tests, tùy JUnit/TestNG/provider.
- `${surefire.forkNumber}`: placeholder giúp phân biệt forks trong một Maven session/build.

### Trong demo

~~~xml
<forkCount>1</forkCount>
<reuseForks>true</reuseForks>
~~~

Khi Maven chạy hai modules song song, có thể có hai test forks cùng lúc — mỗi module một JVM. Nếu tăng `forkCount=2` và có đủ test classes, hai modules cùng ở test phase có thể tạo tới 4 forks.

### Tránh `forkCount=0` với Maven parallel builds

Khi vô hiệu hóa forking, tests/plugin goals có thể chia sẻ JVM/process-wide properties. Tài liệu Surefire nhấn mạnh việc kết hợp Maven parallel module builds và `forkCount=0` không phải lựa chọn an toàn; system properties có thể bị các test executions thay đổi gây race.

Trước khi tăng parallel tests trong một module, nên làm ổn định **module-level parallelism với forked test JVMs**.

### `${surefire.forkNumber}`

Có thể tạo tên schema/working directory riêng cho fork bằng placeholder, ví dụ mảnh config:

~~~xml
<systemPropertyVariables>
    <test.schema>schema_${surefire.forkNumber}</test.schema>
</systemPropertyVariables>
~~~

Đây không phải POM runnable đầy đủ: test code phải đọc `test.schema` và thật sự dùng DB/schema riêng. ForkNumber chỉ phân biệt trong phạm vi Maven session, không bảo đảm globally unique giữa hai CI jobs cùng chạy. Khi cần cô lập cross-job, đưa build/run identifier vào namespace.

### JUnit 5 thread parallelism

Nếu bật Jupiter parallel execution bằng `junit.jupiter.execution.parallel.enabled=true` và cấu hình modes, tests trong **một forked JVM** cũng có thể chạy đồng thời. Một test dùng static mutable state hoặc chung fixture có thể lỗi dù Maven chỉ chạy `-T 1`.

Hãy xác định rõ bạn đang thử **Maven module concurrency**, **Surefire forks** hay **JUnit method concurrency**. Không thay nhiều tầng cùng lúc rồi không biết yếu tố nào gây lỗi.

## 11. Plugin tự phát triển: checklist trước khi đánh dấu threadSafe

Một custom Mojo được annotate `threadSafe=true` cần kiểm:

**State:**

- Mutable static fields hoặc maps không synchronization?
- Singleton Plexus/Sisu components dùng chung?
- `MavenSession`/`MavenProject` có bị sửa vượt phạm vi module?
- System properties/env mutable được thay trên Maven process?
- Third-party libraries có thread safety contract không?

**Filesystem:**

- Mọi output file có đường dẫn unique theo project?
- Temp files có bị dùng chung tên?
- Code generator có dọn thư mục của module khác?
- Concurrent writes có atomic rename/locking khi cần?
- Có xử lý cleanup và interrupted operation không?

**External tools:**

- npm, Docker, database, shell command có chung workspace?
- Cùng port hoặc database schema?
- Remote service có quota/rate limit?
- Tool có thực sự thread-safe và process-safe?
- Các retries có idempotent không?

**Evidence:**

- Có unit tests cho concurrency-sensitive logic?
- Có multi-module integration test chạy tuần tự và parallel?
- Có stress runs trên Linux/Windows hoặc OS mục tiêu?
- Có xác định giới hạn resource và document chúng?
- Có rollback khi parallel CI không ổn định?

### Java `synchronized` không giải quyết mọi loại xung đột

`synchronized` đồng bộ những threads dùng **cùng lock object trong một JVM**. Hai Maven CLI processes riêng biệt không chia sẻ Java lock. DB/files/network cần locking/transaction/isolation ở tầng tài nguyên đó.

### Static counter anti-pattern

~~~java
private static int processedModules = 0;

// In a Mojo execute() method:
processedModules++;
~~~

Đây là **mảnh code lỗi**, không phải plugin hoàn chỉnh; `++` không phải atomic operation giữa threads, nên số đếm có thể sai. Thường tốt hơn là tránh state dùng chung, xử lý module-local data hoặc dùng concurrency primitives sau khi xác định lifecycle.

## 12. Lỗi cấu hình: plugin có metadata tốt nhưng output vẫn bị trộn

Giả sử hai module build cùng:

~~~xml
<build>
    <directory>../shared-target</directory>
</build>
~~~

Đây là **anti-pattern để phân tích**, không thêm vào lab. `mvn clean` hoặc các plugin goals có thể xóa/ghi output lẫn nhau. Dù Compiler/JAR/Surefire goals hỗ trợ thread-safe, project-level path sai gây collision.

Cách sửa: để mỗi module giữ default `target`, hoặc dùng module-local expression:

~~~xml
<build>
    <directory>${project.basedir}/target</directory>
</build>
~~~

Đoạn này minh họa cách quy về từng module; trong thực tế giữ default Maven `target` là đơn giản nhất. Với plugin có `outputDirectory` riêng, dùng `${project.build.directory}` thay vì một absolute/shared path.

**Cảnh báo:** Một số tools như JaCoCo `report-aggregate` hoặc aggregator plugins có mục đích tạo output chung. Chúng cần cơ chế tổng hợp/phase phù hợp, không thể chỉ áp quy tắc "tất cả output phải riêng" mà không xem behavior. Điều quan trọng là **không có hai writers chưa phối hợp ghi cùng target**.

## 13. Nhiều module, aggregator goals và lifecycle order

Một plugin goal có thể được đánh dấu `aggregator=true`, vì nó xử lý phạm vi project group. Những goal tổng hợp báo cáo/đóng gói có thể cần kết quả của tất cả modules.

Trước khi bật parallel:

1. Kiểm tra plugin goal có aggregator behavior không.
2. Xem goal thực thi ở root, một module hoặc nhiều module.
3. Kiểm những files nó đọc được tạo vào phase nào.
4. Đảm bảo không có hai goals cùng xóa/ghi aggregated output.
5. Kiểm parent inheritance và activation profile.
6. Với các reports, xem target path có đúng build scope không.

Đừng nghĩ thứ tự `<module>east</module>`, `<module>west</module>` trong POM là cơ chế serialization. Dependency graph và plugin lifecycle mới là cơ sở lập lịch; hidden dependencies cần mô tả bằng POM/config hoặc phối hợp tài nguyên đúng cách.

### `pluginManagement` có làm plugin tự chạy không?

Không tự tạo một custom execution chỉ vì khai báo plugin version trong `pluginManagement`. Với lifecycle-bound plugins như Compiler/Surefire, version/configuration managed vẫn có tác dụng khi JAR packaging gọi goals mặc định. Với một quality plugin riêng, còn cần declaration/execution thích hợp.

Khi audit, xem cả parent POM, inherited `build/plugins`, active profiles và goals được gọi trực tiếp trong CI. Cảnh báo thread-safety có thể đến từ goal nằm trong parent, không nằm ngay trong POM con.

## 14. Benchmark: tốc độ phải đi kèm reliability

Khi đo hiệu năng, so cùng source SHA, JDK/Maven versions, plugin versions, runner core/memory, cache state và external service load.

### Ví dụ bảng ghi nhận (số giả định)

| Cấu hình | Wall time giả định | Tests | Failure rate giả định | Đánh giá |
| --- | ---: | ---: | ---: | --- |
| `-T 1` | 120 giây | 200 | 0/10 | Baseline. |
| `-T 2` | 84 giây | 200 | 0/10 | Có thể phù hợp. |
| `-T 4` | 72 giây | 200 | 2/10 | Chưa chấp nhận được. |
| `-T 1C` | 88 giây | 200 | 0/10 | Phụ thuộc core count runner. |

Đây là **số minh họa, không phải benchmark đo được**. `-T 4` nhanh hơn khi PASS nhưng có intermittent failures thì không đủ điều kiện cho required CI gate.

### Đo trong lab

Linux/macOS (nếu có `/usr/bin/time`):

~~~bash
/usr/bin/time -p mvn -B -ntp -T 1 clean verify
/usr/bin/time -p mvn -B -ntp -T 2 clean verify
~~~

Windows PowerShell:

~~~powershell
Measure-Command { mvn -B -ntp -T 1 clean verify }
Measure-Command { mvn -B -ntp -T 2 clean verify }
~~~

Ngoài số thời gian, kiểm Maven exit status và test report counts. Run đầu có thể tải dependencies/plugins, run sau dùng warm cache; không so khập khiễng rồi kết luận speedup do threads.

### Artifact checksum và reproducibility

Nếu JAR hashes khác nhau giữa tuần tự và song song, phải điều tra nhưng không tự kết luận race: ZIP timestamps, build metadata hoặc nondeterministic plugin inputs có thể khiến files khác nhau. Muốn kiểm exact binary equality cần chuẩn hóa reproducible-build configuration và inputs. Test count/report integrity và class/API behavior là các bằng chứng bổ sung.

## 15. Mẫu GitHub Actions kiểm song song trước khi rollout

Một CI job kiểm tra cả baseline và parallel theo matrix:

~~~yaml
name: Maven Parallel Safety

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    strategy:
      fail-fast: false
      matrix:
        threads: ['1', '2']

    steps:
      - name: Checkout
        uses: actions/checkout@v7
        with:
          persist-credentials: false

      - name: Set up Java 17
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
          cache-read-only: ${{ github.event_name == 'pull_request' }}

      - name: Record build environment
        run: |
          java -version
          mvn --version
          git rev-parse HEAD

      - name: Verify with selected thread count
        run: mvn -B -ntp -T ${{ matrix.threads }} clean verify

      - name: Keep reports after failure
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: maven-parallel-T${{ matrix.threads }}-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            **/target/surefire-reports/**
            **/target/failsafe-reports/**
          if-no-files-found: warn
          retention-days: 7
~~~

**Đây là workflow mẫu cho GitHub-hosted Ubuntu với action majors được tài liệu upstream công bố tại thời điểm soạn.** Nếu dùng self-hosted runner cũ hoặc GitHub Enterprise Server, kiểm yêu cầu Node/runner runtime và versions. Tổ chức muốn security hardening nên pin full trusted commit SHA của actions, không tự bịa SHA.

### Giải thích

- Hai legs `-T 1` và `-T 2` có workspace riêng trên hosted runners.
- `fail-fast: false` giữ leg còn lại khi một leg fail.
- Branch protection nên coi cả hai legs là required checks nếu muốn cho phép parallel CI.
- `upload-artifact` với `always()` cố lưu XML khi Maven fail; nếu fail trước khi test chạy, có thể không có files và action chỉ warning.
- Tên report unique theo thread mode/run attempt.
- Không dùng `continue-on-error: true` hoặc `|| true` cho verify.
- PR job không có publish token/signing key; `contents: read` tuân thủ least privilege.
- Artifact upload **không tự parse tests**; muốn PR annotations cần reporter đã review.

### Vì sao không chạy `deploy` để kiểm plugin thread-safety?

`deploy` có side effects thật (ghi artifact repository) và không cần thiết cho test song song thông thường. Stress loops nên chạy `verify` trong môi trường cô lập; publishing/release stage có QA riêng sau khi tất cả checks PASS.

## 16. Cách xử lý khi một goal chưa an toàn

Có những lựa chọn:

| Vấn đề | Hướng sửa phù hợp |
| --- | --- |
| Version cũ chưa hỗ trợ threadSafe. | Upgrade theo changelog rồi kiểm lại behavior. |
| Plugin chưa marked threadSafe. | Không chỉ xóa warning; giữ serial hoặc nhận risk có review. |
| Hai modules ghi chung temp/output. | Tách theo `project.build.directory`, module ID/build ID. |
| Shared DB schema/port. | Cấp schema/port riêng hoặc serialize IT stage. |
| Plugin custom dùng unsafe singleton. | Refactor state, locking/atomic operations và stress tests. |
| External tool bị rate-limit. | Giảm concurrency và dùng retry/backoff có kiểm soát. |
| CI memory không đủ. | Giảm `-T` hoặc forkCount, đo peak JVM memory. |
| Aggregator goal cần báo cáo từ tất cả modules. | Đặt phase/execution phù hợp và tránh writers chạy trùng. |
| Publication tạo partial releases. | Tách verify, dùng staging/release governance; không tăng concurrency mù. |
| Không có evidence của safety. | Giữ `-T 1` đến khi đủ điều kiện. |

**Không phải mọi module đều cần bật song song.** Có thể thiết kế pipeline với pure Java compile/test song song, nhưng serial hóa một số stage integration/release nếu tài nguyên chúng cần không hỗ trợ concurrency.

## 17. Những câu hỏi chẩn đoán khi `-T 2` bị lỗi

1. Lỗi có lặp lại ở `-T 1` không?
2. Maven báo plugin goal nào not marked thread-safe?
3. Đúng plugin **version**/Mojo **goal** nào đang chạy?
4. Goal nằm ở parent, module, profile hay direct CLI?
5. Hai modules có ghi chung output/cache/report directory không?
6. Tests có dùng chung port, schema, Docker resource, global system property không?
7. Surefire `forkCount` và JUnit parallel options là gì?
8. Maven runner có đủ memory khi nhiều test JVMs chạy không?
9. Có giữ reports/XML và log module gây lỗi không?
10. Plugin/tool có side effects ngoài workspace không?
11. Sau khi giảm concurrency, lỗi có biến mất ổn định qua nhiều trials không?
12. Có thay đổi cache state hoặc version giữa hai runs không?

### Một số triệu chứng điển hình

| Hiện tượng | Hướng xem |
| --- | --- |
| `Address already in use` | Port cố định, test server lifecycle. |
| `NoClassDefFoundError` trong service demo | Thiếu `core` trên classpath khi chạy Java thủ công, không vội quy cho -T. |
| `No tests were executed` | Surefire naming, test dependencies, profiles, skip flags. |
| XML report bị cắt giữa chừng | Cùng report directory hoặc job bị kill. |
| Java OutOfMemoryError | `-T` × `forkCount` × heap/resource limits. |
| Missing generated source | Plugin codegen output path hoặc dependency edge sai. |
| Cache corruption | Shared write access hoặc incomplete download, cần kiểm nguồn và lock. |
| Build song song chậm hơn | Critical path, I/O contention, cache warm/cold, test fork overhead. |
| `-fae` tiếp tục modules nhưng một vài modules SKIPPED | Maven dependency constraints; không phải mọi module đều được test. |
| `-fn` che failure exit code | Không dùng ở required CI checks. |
| `BUILD SUCCESS` nhưng warning không thread-safe | Metadata risk chưa được giải quyết, cần review. |

**Phân biệt fail-fast, fail-at-end, fail-never:** `-fae` có thể tiếp tục các modules không phụ thuộc vào module lỗi để thu thêm thông tin, vẫn báo failure cuối. `-fn` có thể che failure và không thích hợp làm required gate. Mặc định fail-fast có thể dừng sớm khi gặp lỗi, nên các modules chưa chạy không thể được tính PASS.

## 18. Bài tập thực hành

### Bài A — Reactor graph

Cho `parent → core → {east, west}`:

1. Module nào phải sẵn sàng trước `east`?
2. `east` và `west` có thể chạy đồng thời không?
3. `-T 8` có tự tạo tám modules runnable không?
4. Nếu `east` và `west` cùng dùng `shared-target`, Maven graph có bảo vệ không?
5. Vì sao tăng `-T` có lúc làm build chậm?

**Đáp án:** core là prerequisite; east/west có thể overlap; `-T` không thay graph; shared output là hidden dependency; overhead, I/O, memory và contention có thể lấn át lợi ích.

### Bài B — chạy project Java 17

1. Tạo bốn POM và sáu Java files từ mục 7.
2. Chạy `mvn --version` và `java -version`.
3. Chạy `mvn -B -ntp -T 1 clean verify`.
4. Chạy `mvn -B -ntp -T 2 clean verify`.
5. Đọc Surefire reports: core 2 tests, east 1, west 1.
6. Chạy `EastService` và `WestService` qua `java -cp`, xác minh stdout.
7. Lặp song song năm lần trong lab, lưu số lần failure.
8. So versions, timings và output files.
9. Kết luận mức tin cậy, không tuyên bố an toàn tuyệt đối.
10. Viết điều kiện cần để chuyển `-T 2` thành required CI.

### Bài C — metadata tốt, configuration sai

Một plugin goal có `threadSafe=true`, nhưng POM hai modules cùng dùng `../shared-target/report.json`.

Hỏi:

- ThreadSafe metadata có đủ bảo đảm không?
- Nếu một goal truncate file trong lúc goal khác đang ghi, hậu quả gì?
- Làm sao tách path?
- Làm stress test để chứng minh fix?
- Nếu các modules được build bởi **hai Maven processes khác nhau**, Java synchronized có đủ bảo vệ không?

**Đáp án:** Không; có race/overwrite; tách output theo module; so tuần tự/song song và reports/bytes; Java lock không giải quyết xung đột giữa processes độc lập.

### Bài D — Surefire forks và ports

Dự án dùng `-T 3`, mỗi module `forkCount=2` và tests bind 8080.

1. Có thể có bao nhiêu forked JVMs cùng lúc nếu ba modules đều chạy test?
2. Port cố định có tạo conflict không?
3. `forkCount=0` giúp an toàn hơn không?
4. Có thể dùng placeholder `surefire.forkNumber` để tạo schema suffix không?
5. Vì sao phải có build ID thêm vào schema cho nhiều CI jobs?
6. Mục tiêu verify có cần kiểm test counts/Failsafe reports không?

**Định hướng:** tối đa lý thuyết 6 forks; shared port có conflict; forkCount 0 có nguy cơ shared properties; forkNumber hỗ trợ tên riêng trong session nhưng chưa globally unique.

### Bài E — review plugin upgrade

Một PR:

- Thay plugin version.
- Thêm execution ở `generate-sources`.
- Đổi output từ `${project.build.directory}/generated` sang `../shared-generated`.
- Thêm `-T 4` vào CI.

Hãy:

1. Tra plugin GAV/goal/descriptor và changelog.
2. So parent inheritance/active profiles.
3. Kiểm shared path/cleanup.
4. Chạy no-secret CI serial vs parallel và stress test.
5. Kiểm số tests và artifact consistency.
6. Đề xuất phương án rollback nếu warning/lỗi.
7. Ghi điều kiện phê duyệt rõ ràng.

## 19. Checklist bật song song có kiểm soát

**Maven và plugins**

- [ ] Xác định module graph, critical path và modules chạy đồng thời.
- [ ] Ghim Maven/JDK/plugin versions và ghi trong CI logs.
- [ ] Tra goal-level threadSafe metadata đúng plugin version.
- [ ] Không còn non-thread-safe warning chưa được review.
- [ ] Kiểm parent/profile/inherited executions và aggregator goals.
- [ ] Không bỏ sót plugin dependencies hoặc extensions ảnh hưởng build.

**Tài nguyên**

- [ ] Output/generated/report/temp directories riêng từng module.
- [ ] Test ports, database schemas và shared caches có isolation.
- [ ] Plugin custom không dùng unsafe static/singleton state.
- [ ] External tools/processes phù hợp concurrency.
- [ ] Tổng forks/memory/CPU nằm trong giới hạn runner.
- [ ] Không lặp side effects deploy/signing/release trong stress jobs.

**Kiểm chứng**

- [ ] `-T 1 clean verify` PASS làm baseline.
- [ ] `-T 2 clean verify` PASS với cùng input/toolchain.
- [ ] Đã chạy lặp hoặc test load phù hợp để tìm flaky race.
- [ ] Surefire/Failsafe reports và test counts không mất.
- [ ] Không dùng `-fn`, `|| true` hoặc skip flags để che lỗi.
- [ ] Có measurement wall time, memory và failure rate.
- [ ] Có lựa chọn rollback về serial khi cần.

**CI governance**

- [ ] PR runner không có publish/signing/cloud production secrets.
- [ ] Cache/action versions được kiểm soát.
- [ ] Reports được lưu khi fail và tên artifact không collision.
- [ ] Branch protection/required checks phù hợp matrix modes.
- [ ] Release pipeline có kiểm chứng riêng với publish side effects.
- [ ] Có owner xử lý plugin non-thread-safe hoặc flaky tests.

## 20. Kết luận

**Plugin “thread-safe” và build “an toàn khi chạy song song” là hai câu hỏi liên quan nhưng khác nhau.** Maven `-T` lập lịch modules theo dependency graph; metadata `threadSafe` của từng Mojo cho biết tác giả plugin tuyên bố goal hỗ trợ concurrent execution. Nhưng output path, port, DB, test forks và external side effects có thể tạo race ngay cả khi goal được đánh dấu an toàn.

~~~text
Module dependency graph rõ
              │
              ▼
Kiểm goal-level threadSafe + plugin version
              │
              ▼
Review output dirs / external resources
              │
              ▼
Baseline -T 1 clean verify
              │
              ▼
Parallel -T 2 clean verify + repeat/stress
              │
              ▼
Đối chiếu XML reports, side effects, time/failures
              │
              ▼
Rollout CI có monitoring và rollback
~~~

Ghi nhớ:

- `-T 2` là mức reactor concurrency, không phải giới hạn tổng JVM threads.
- `threadSafe=true` là metadata cho **goal**, không tự làm shared paths và test fixtures an toàn.
- Maven warning non-thread-safe **không tự fail build**, nhưng cần có người xử lý.
- `forkCount` và JUnit parallel settings là các tầng concurrency riêng.
- Dùng Java 17 reactor độc lập với tests/module outputs tách biệt để học cơ chế.
- **Một lần BUILD SUCCESS không loại bỏ race condition**: cần review, đối chứng, test lặp và đo reliability.
- Khi chưa có bảo đảm phù hợp, giữ build tuần tự là lựa chọn kỹ thuật đúng.

## Tài liệu chính thức

- Apache Maven — Parallel Builds in Maven 3: https://cwiki.apache.org/confluence/display/MAVEN/Parallel+builds+in+Maven+3
- Apache Maven — Working with Multiple Modules: https://maven.apache.org/guides/mini/guide-multiple-modules.html
- Apache Maven — Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — POM Reference: https://maven.apache.org/pom.html
- Maven Plugin API — Mojo Descriptor and threadSafe: https://maven.apache.org/ref/3.9.9/maven-plugin-api/plugin.html
- Maven Plugin Tools — `@Mojo` Annotation: https://maven.apache.org/plugin-tools/maven-plugin-annotations/apidocs/org/apache/maven/plugins/annotations/Mojo.html
- Maven Compiler Plugin — compile goal: https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html
- Maven Surefire Plugin — test goal: https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html
- Maven Surefire — Fork Options and Parallel Test Execution: https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options-and-parallel-execution.html
- Maven Help Plugin — Effective POM: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- JUnit 5 User Guide — Parallel Execution: https://docs.junit.org/current/user-guide/#writing-tests-parallel-execution
