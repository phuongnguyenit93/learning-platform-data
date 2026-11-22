# Đo thời gian từng mô-đun và từng bước trước khi tối ưu Maven

## 1. Vì sao phải đo trước khi tối ưu?

Một dự án Maven có thể mất nhiều thời gian vì download dependencies, startup JVM, compile, annotation processing, test execution, database/container integration tests, quality gates hoặc đóng gói JAR/WAR. Nhìn thấy dòng `Total time: 2 min` không cho biết bước nào gây chậm. Nếu ngay lập tức bật `-T 1C`, tăng heap hoặc bỏ tests, bạn có thể làm build kém ổn định mà chỉ cải thiện rất ít.

**Profiling build** là đo thời gian ở những mức phù hợp, tìm bottleneck có số liệu và thử thay đổi trong điều kiện có thể so sánh. Ba câu hỏi cơ bản:

1. **Cả lệnh Maven mất bao lâu?** Wall-clock elapsed time từ lúc chạy đến lúc trả exit status.
2. **Mô-đun nào chậm?** Maven Reactor Summary cung cấp thời gian từng project trong multi-module build.
3. **Bước nào trong mô-đun đó chậm?** Đo từng plugin goal execution (mojo), ví dụ `compiler:compile`, `surefire:test`, `shade:shade` hoặc `jar:jar`.

Bài này hướng dẫn **Maven Reactor Summary**, **Maven Profiler core extension 3.3**, kỹ thuật đo lặp lại cold/warm/incremental, phân tích critical path và kiểm chứng lợi ích trước/sau tối ưu. Có dự án **Java 17 multi-module hoàn chỉnh** với ba POM, mã chạy được, ba JUnit 5 tests và output chính xác.

**Thông điệp cốt lõi:** không tối ưu theo cảm giác; hãy xác định module, goal, dạng chi phí, điều kiện cache và mức cải thiện thực sự.

## 2. Các mức đo cần phân biệt

| Mức | Dữ liệu | Công cụ | Điều chưa biết |
| --- | --- | --- | --- |
| Toàn invocation | Wall time, exit code | Shell `time`, PowerShell Stopwatch, Maven Total time | Module/goal nào chiếm thời gian |
| Module | Duration mỗi Maven project | Reactor Summary | Bên trong module goal nào chậm |
| Plugin goal (mojo) | Duration mỗi execution | Maven Profiler extension | CPU vs I/O/network/fork chi tiết |
| Tests | Từng test suite, số tests | Surefire/Failsafe reports | Phần plugin startup và test discovery |
| Process/JVM | CPU, GC, allocation, threads | JFR, OS metrics, profiler JVM | Thời gian các module chồng lấp |
| CI job | Checkout, cache, setup, Maven, upload | CI platform timers | Maven plugin bottleneck nếu không đo riêng |

**Wall time** là thời gian người dùng chờ. **CPU time** là thời gian CPU tiêu thụ; có thể thấp hơn wall time khi chờ network hoặc lớn hơn wall time nếu nhiều core được dùng. **Mojo duration** là thời gian một plugin goal hoạt động; nó có thể bao gồm thời gian chờ fork/test process, không tự là CPU time.

### Phase khác goal

Trong Maven, `validate`, `compile`, `test`, `package`, `verify` là **lifecycle phases**. `maven-compiler-plugin:compile`, `maven-surefire-plugin:test` là **plugin goals**. Một phase có thể chạy nhiều goals, và gọi phase sau cũng thực thi các phase trước đó.

Ví dụ `mvn verify` có thể đi qua resources, compile, test-compile, test, package và quality checks trước khi kết thúc. Không được gọi `surefire:test` là “toàn bộ thời gian phase test” khi còn setup/fork hoặc plugin execution khác.

### Reactor Summary khác tổng wall time

Với sequential reactor (không có `-T`), Maven hiển thị thời gian theo project và tổng build, nhưng tổng project durations có thể nhỏ hơn wall time do startup/model/dependency-resolution/overhead.

Với parallel reactor (`-T 1C`), những modules độc lập chạy **chồng lấp**. Tổng durations của các modules có thể **lớn hơn wall time**. Khi đó nên phân tích **critical path**, chứ không cộng thời gian module như thời gian tuần tự.

## 3. Bắt đầu bằng Reactor Summary

Một lượt Maven multi-module build có thể kết thúc bằng log **minh họa**:

```text
[INFO] Reactor Summary for Performance Lab 1.0.0:
[INFO]
[INFO] Performance Lab ................................. SUCCESS [  0.310 s]
[INFO] Performance Core ................................ SUCCESS [ 10.900 s]
[INFO] Performance CLI ................................. SUCCESS [  2.520 s]
[INFO] ------------------------------------------------------------------------
[INFO] BUILD SUCCESS
[INFO] ------------------------------------------------------------------------
[INFO] Total time:  14.770 s
```

**Đây chỉ là dữ liệu ví dụ**, không phải thời gian đã đo trên một máy cụ thể. Những điều có thể suy ra:
- Module `Performance Core` có thời gian cao nhất trong lần đo.
- Cần vào Core để xem `compiler:compile`, `surefire:test`, test fixtures hay processors chiếm phần lớn.
- Chưa có đủ bằng chứng để tăng parallel threads hoặc bỏ tests.

**Reactor Summary cung cấp mức module, không tự cung cấp một bảng chi tiết từng mojo duration**. Khi log bị rút gọn bởi `-q` hoặc CI chỉ hiển thị phần cuối, giữ lại full INFO log cho lượt profiling.

## 4. Phân biệt cold, warm clean và incremental build

| Chế độ đo | Mô tả | Câu hỏi |
| --- | --- | --- |
| Cold repository | Maven local repo gần như trống, cần tải plugins/dependencies | Thời gian tải, repository/mirror và network |
| Warm clean | Repo đã có dependencies, mỗi lượt chạy `clean verify` | Clean compile/test/package đầy đủ mất bao lâu |
| Warm incremental | Giữ `target`, chạy lại `verify` | No-change/incremental build có nhanh không |
| Một file thay đổi | Chỉnh một Java source rồi build | Sửa nhỏ kích hoạt những module/goal nào |
| CI cache hit vs miss | Giữ nguyên source và runner class, đổi cache state | Cache thực tế giúp được gì |
| Multi-threaded | So cùng warm clean với `-T 1` và `-T 1C` | Parallel scheduling có giảm wall time không |

**Cold và warm là workload khác nhau.** Một lần đầu mất 2 phút vì tải dependency không có nghĩa Compiler Plugin chậm 2 phút. Với benchmark, cần ghi cache mode và không lẫn các mode trong cùng một median.

### Vì sao lần chạy đầu hay chậm?

- Maven JVM/bootstrap có chi phí cố định.
- Maven plugins và transitive dependencies có thể chưa được tải.
- OS page cache, filesystem caches chưa nóng.
- JVM fork cho tests, JIT/classloading, container/test fixture initialization.
- CI runner có thể bị contention bởi jobs khác.

**Một lượt đo là chưa đủ.** Trong bài thực hành, thực hiện một lượt warm-up rồi ít nhất **năm lượt** cho cùng scenario, dùng median/range để tránh tin vào một outlier.

## 5. Đo wall time với lệnh ngoài Maven

### 5.1. Linux với GNU time

Trong project thực hành:

```bash
mkdir -p perf-results

/usr/bin/time -p -o perf-results/clean-01.time \
  mvn -B -ntp clean verify > perf-results/clean-01.log 2>&1
```

File time có thể có dạng:

```text
real 15.42
user 13.08
sys 1.42
```

Các con số là **ví dụ minh họa**. `real` đo elapsed wall seconds, `user` và `sys` đo CPU time theo công cụ GNU time. Trong parallel/forked processes, CPU time không nhất thiết cộng bằng `real`.

Lưu ý:
- `-B`: batch mode, phù hợp CI.
- `-ntp`: tắt transfer progress output, **không tắt download**.
- `clean verify`: đo trọn clean build, không phải incremental.
- `-p -o` dùng cú pháp GNU `/usr/bin/time`; trên macOS/BSD có thể dùng `time mvn ...` và cơ chế redirect phù hợp.
- Giữ exit code và log: lượt build lỗi không dùng làm baseline thành công.

### 5.2. Windows PowerShell 5.1+

```powershell
New-Item -ItemType Directory -Force -Path "perf-results" | Out-Null

$watch = [System.Diagnostics.Stopwatch]::StartNew()
& mvn -B -ntp clean verify *> "perf-results/clean-01.log"
$exitCode = $LASTEXITCODE
$watch.Stop()

"WallSeconds={0:N3}; ExitCode={1}" -f $watch.Elapsed.TotalSeconds, $exitCode

if ($exitCode -ne 0) {
    throw "Maven failed with exit code $exitCode"
}
```

`Stopwatch` đo một invocation đầy đủ. Giữ cùng cách redirect logs giữa các lượt: log khổng lồ có thể tạo I/O overhead. Không mặc định gọi `Measure-Command` rồi quên kiểm Maven exit status.

### 5.3. Tại sao không chỉ dùng `Total time` của Maven?

Dòng Maven Total time rất tiện, nhưng shell stopwatch còn giúp đo chi phí khởi chạy process và so các giai đoạn CI khác nhau. Hai số có thể lệch chút ít do điểm bắt đầu/kết thúc đo. Nên chọn **một định nghĩa thống nhất** cho dashboard baseline.

## 6. Đo từng plugin goal bằng Maven Profiler 3.3

Apache Maven liệt kê **Maven profiler** của Jean-Christophe Gay trong [Available Extensions](https://maven.apache.org/extensions/index.html). Project upstream [jcgay/maven-profiler](https://github.com/jcgay/maven-profiler) mô tả extension dùng Maven events để ghi thời gian từng mojo và tạo báo cáo **HTML, JSON hoặc CONSOLE**.

### 6.1. Cài core extension đúng vị trí

Ở root multi-module project, tạo file **`.mvn/extensions.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<extensions>
    <extension>
        <groupId>fr.jcgay.maven</groupId>
        <artifactId>maven-profiler</artifactId>
        <version>3.3</version>
    </extension>
</extensions>
```

Đây là **Maven core extension** được nạp trước project build, **không phải Maven build plugin** đặt trong `<build><plugins>`. Maven phải có thể resolve artifact này từ repository.

Ưu điểm:
- Đo duration từng plugin goal trong từng Maven project.
- Có reports cho con người và machine-readable.
- Theo README upstream, hỗ trợ Maven 3.3+ và tùy chọn nhiều threads (`-T`); cần kiểm tương thích thật nếu dùng Maven 4 hoặc JDK/plugin mới.

Chi phí:
- Extension được Maven nạp kể cả khi không bật ghi profile.
- Lượt đầu có thể tải extension và làm cold build khác.
- Instrumentation/report output có thể thêm overhead, nhất là khi in console/log rất nhiều.
- Dùng **profiling để tìm bottleneck**, rồi đo wall time lần cuối trong điều kiện bạn muốn tối ưu (có hoặc không extension nhưng phải nhất quán).

### 6.2. Kích hoạt report

```bash
mvn -B -ntp -Dprofile clean verify
```

`-Dprofile` là **Maven user property** mà extension đọc để kích hoạt. Nó **không giống** `-Pprofile` kích hoạt build profile.

Maven Profiler upstream mặc định tạo HTML report trong thư mục `.profiler` dưới project. Để tạo JSON và bảng console:

```bash
mvn -B -ntp -Dprofile -DprofileFormat=JSON,CONSOLE clean verify
```

Các tùy chọn từ README upstream:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `-Dprofile` | Kích hoạt profiler |
| `-DprofileFormat=HTML` | HTML report (default) |
| `-DprofileFormat=JSON` | JSON report |
| `-DprofileFormat=CONSOLE` | In bảng timing |
| `-DprofileFormat=JSON,HTML,CONSOLE` | Xuất nhiều định dạng |
| `-DdisableTimeSorting` | Giữ thứ tự thực thi, thay vì sort theo duration |
| `-DhideParameters=true` | Tránh đưa Maven user parameters có thể nhạy cảm vào report |
| `-Dmaven-profiler-report-directory=...` | Đổi thư mục output |

Đối với CI và báo cáo có thể chia sẻ, ưu tiên:

```bash
mvn -B -ntp -Dprofile -DprofileFormat=JSON,CONSOLE -DhideParameters=true clean verify
```

**Vẫn phải kiểm tra logs/report trước khi chia sẻ.** Maven user properties có thể chứa token/URL nội bộ; `hideParameters` giảm một nguồn rò rỉ, không bảo đảm log không chứa secret khác.

### 6.3. Mẫu JSON profiler (dữ liệu giả định)

```json
{
  "name": "maven-profiler",
  "goals": "clean verify",
  "time": "14800 ms",
  "projects": [
    {
      "project": "perf-core",
      "time": "10900 ms",
      "mojos": [
        {
          "mojo": "org.apache.maven.plugins:maven-surefire-plugin:3.5.4:test {execution: default-test}",
          "time": "6900 ms"
        },
        {
          "mojo": "org.apache.maven.plugins:maven-compiler-plugin:3.14.1:compile {execution: default-compile}",
          "time": "1900 ms"
        }
      ]
    }
  ]
}
```

Đây là **một JSON report mẫu đã rút gọn**, không phải kết quả đo trong ví dụ. Report thật có thể chứa nhiều projects, mojos, timestamps và parameters.

Đọc đúng:
- Core mất khoảng 10.9 s **theo ví dụ**.
- `surefire:test` mất 6.9 s, nên ưu tiên tìm chi phí test/fork/fixtures.
- `compiler:compile` mất 1.9 s, không phải bottleneck số một.
- Goal time bao gồm chờ khi goal gọi external process; không tự là CPU time.
- JSON `time` thường là chuỗi có đơn vị, không phải luôn số nanoseconds.

### 6.4. Đọc JSON trên PowerShell

Nếu đã tạo JSON report trong `.profiler`:

```powershell
$file = Get-ChildItem ".profiler" -Filter "*.json" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if ($null -eq $file) {
    throw "Profiler JSON report not found"
}

$report = Get-Content -LiteralPath $file.FullName -Raw |
    ConvertFrom-Json

foreach ($p in $report.projects) {
    "{0}: {1}" -f $p.project, $p.time
    $p.mojos | Select-Object -First 5 -Property mojo, time |
        Format-Table -AutoSize
}
```

Script lấy **một report JSON mới nhất**, in module times và năm mojos đầu của mỗi module. Khi report mặc định sort duration, chúng thường là những mojos chậm nhất. Nếu đã bật `disableTimeSorting`, hãy tự sort theo duration sau khi parse đơn vị.

### 6.5. Khi nào cần timeline/tracing thay vì bảng?

Trong Maven parallel builds (`-T`), hai modules có thể overlap và đôi khi phải chờ dependency output. Bảng goal durations không tự thể hiện **critical path**.

Trang Apache Maven extensions còn liệt kê **maven-timeline**, **Takari Profiler**, **OpenTelemetry Maven Extension** và **JFR Maven Extension**. Chúng có chức năng timeline/trace/profiling khác nhau:
- Profiler dạng bảng: xếp hạng goal bottlenecks.
- Timeline/tracing: thấy parallel overlap, idle gaps, critical path.
- JFR/OS tools: phân biệt CPU, GC, memory, disk/network waits.

**Không cài tất cả cùng lúc khi benchmark**. Mỗi instrumentation có overhead; chọn công cụ theo câu hỏi cần trả lời.

## 7. Ví dụ Maven reactor Java 17 runnable

Project minh họa gồm một **parent/aggregator** và hai modules:
- `perf-parent` có packaging `pom`;
- `perf-core` là library với class `Greeting` và 3 JUnit Jupiter tests;
- `perf-cli` là ứng dụng có `Main`, dùng dependency `perf-core`.

Cấu trúc:

```text
perf-lab/
├── pom.xml
├── .mvn/
│   └── extensions.xml
├── core/
│   ├── pom.xml
│   └── src/
│       ├── main/java/com/example/perf/core/Greeting.java
│       └── test/java/com/example/perf/core/GreetingTest.java
└── cli/
    ├── pom.xml
    └── src/main/java/com/example/perf/cli/Main.java
```

**File `.mvn/extensions.xml` là tùy chọn khi profiling**, không bắt buộc để build source Java. Ba POM và ba Java sources dưới đây là bộ chạy được.

### 7.1. `perf-lab/pom.xml` — POM root hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.perf</groupId>
    <artifactId>perf-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <name>Performance Lab</name>

    <modules>
        <module>core</module>
        <module>cli</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.jupiter.version>5.11.4</junit.jupiter.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>${junit.jupiter.version}</version>
                <scope>test</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-resources-plugin</artifactId>
                    <version>3.3.1</version>
                </plugin>
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
        </pluginManagement>
    </build>
</project>
```

Điểm quan trọng:
1. Root vừa **aggregator** (`modules`) vừa **parent** (children dùng `<parent>`).
2. Java compiler release 17 và UTF-8 được inherited.
3. JUnit Jupiter 5.11.4 có dependencyManagement; chỉ module khai báo JUnit dependency mới dùng nó.
4. PluginManagement ghim version cho những plugins lifecycle sẽ dùng; không tự tạo goal execution tùy biến.
5. `perf-cli` phụ thuộc `perf-core`, nên reactor phải xử lý Core trước CLI dù `<modules>` có thể được liệt kê theo cách khác.

### 7.2. `perf-lab/core/pom.xml` — POM Core hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.perf</groupId>
        <artifactId>perf-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>perf-core</artifactId>
    <packaging>jar</packaging>
    <name>Performance Core</name>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
        </dependency>
    </dependencies>
</project>
```

Vì parent dependencyManagement có version/scope, JUnit được dùng chỉ trong Core test classpath; những modules khác không tự nhận JUnit dependency.

### 7.3. `perf-lab/cli/pom.xml` — POM CLI hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.perf</groupId>
        <artifactId>perf-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>perf-cli</artifactId>
    <packaging>jar</packaging>
    <name>Performance CLI</name>

    <dependencies>
        <dependency>
            <groupId>com.example.perf</groupId>
            <artifactId>perf-core</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
```

Dependency tới Core tạo quan hệ **Core → CLI** trong thứ tự build. CLI không dùng JUnit nên không cần khai báo JUnit test dependency.

### 7.4. `core/src/main/java/com/example/perf/core/Greeting.java`

```java
package com.example.perf.core;

public final class Greeting {

    private Greeting() {
    }

    public static String message(String name) {
        if (name == null || name.isBlank()) {
            return "Hello, friend!";
        }
        return "Hello, " + name.strip() + "!";
    }
}
```

Java 17 hoàn chỉnh. `isBlank` và `strip` có từ Java 11. Class không sử dụng network, database, clock hoặc random data.

### 7.5. `core/src/test/java/com/example/perf/core/GreetingTest.java`

```java
package com.example.perf.core;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingTest {

    @Test
    void stripsName() {
        assertEquals("Hello, Maven!", Greeting.message(" Maven "));
    }

    @Test
    void handlesWhitespace() {
        assertEquals("Hello, friend!", Greeting.message("   "));
    }

    @Test
    void handlesNull() {
        assertEquals("Hello, friend!", Greeting.message(null));
    }
}
```

Đây là **ba JUnit 5 test methods**. File hậu tố `Test.java` được Surefire nhận theo naming conventions. Nếu cấu hình/source đúng, kỳ vọng **3 tests, 0 failures, 0 errors**.

**Không cố tình thêm `Thread.sleep` để làm benchmark chậm.** Tạo artificial bottleneck chỉ cho thấy timer hoạt động chứ không phản ánh tối ưu thực của project.

### 7.6. `cli/src/main/java/com/example/perf/cli/Main.java`

```java
package com.example.perf.cli;

import com.example.perf.core.Greeting;

public final class Main {

    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.message(" Maven "));
        System.out.println(Greeting.message(" "));
    }
}
```

Chạy từ root reactor:

```bash
mvn -B -ntp clean verify
```

Linux/macOS, dùng đường dẫn classes của hai modules:

```bash
java -cp "cli/target/classes:core/target/classes" com.example.perf.cli.Main
```

Windows, dấu phân tách classpath là `;`:

```powershell
java -cp "cli/target/classes;core/target/classes" com.example.perf.cli.Main
```

**Stdout chính xác của ứng dụng Java, không tính Maven logs:**

```text
Hello, Maven!
Hello, friend!
```

Binary JARs thường nằm tại `core/target/perf-core-1.0.0.jar` và `cli/target/perf-cli-1.0.0.jar`. POM không thêm `Main-Class` vào manifest và không tạo uber-JAR, vì vậy **không mặc định dùng `java -jar`** để chạy ví dụ.

## 8. Quy trình benchmark trước khi tối ưu

### 8.1. Ghi lại điều kiện đo

Trước khi làm A/B:

```bash
mvn -version
java -version
git rev-parse HEAD
git status --short
```

Ghi Maven distribution, JDK vendor/update, OS, CPU/RAM, repo mirror, local repository cache, active Maven profiles, flags, thread count và số test thực chạy.

Nếu project không dùng Git, ghi source revision theo version control được sử dụng. **Không thay source commit/test set cùng lúc với một optimization flag** rồi gán toàn bộ cải thiện cho flag.

### 8.2. Warm-up

```bash
mvn -B -ntp clean verify
```

Không dùng lượt đầu làm warm baseline nếu nó vừa tải dependencies/plugins, extension mới hoặc container images. Warm-up giúp tách một phần chi phí không đại diện cho build hàng ngày.

### 8.3. Warm clean baseline, nhiều lượt

Linux với GNU time:

```bash
mkdir -p perf-results

for run in 1 2 3 4 5; do
  /usr/bin/time -p -o "perf-results/clean-${run}.time" \
    mvn -B -ntp clean verify \
    > "perf-results/clean-${run}.log" 2>&1 || exit 1
done
```

Mỗi lượt `clean` xóa output cũ, buộc compile/test/package lại. Giữ Maven repository warm, source unchanged, JDK/flags/mirror ổn định. Nếu chạy trên macOS với BSD time, dùng cách đo được shell hỗ trợ thay GNU `-o`.

### 8.4. Warm incremental baseline

Không xóa `target` sau một build thành công:

```bash
for run in 1 2 3 4 5; do
  /usr/bin/time -p -o "perf-results/incremental-${run}.time" \
    mvn -B -ntp verify \
    > "perf-results/incremental-${run}.log" 2>&1 || exit 1
done
```

**Không giả định `mvn verify` khi no-change sẽ làm bằng 0**: Surefire tests hoặc packaging plugin có thể vẫn chạy. Cũng không so kết quả incremental với warm-clean rồi gọi chênh lệch là tối ưu plugin; bản chất workload khác.

### 8.5. Cold-cache benchmark

Nếu câu hỏi là “CI lần đầu chậm vì đâu?”, có thể đo build với **Maven local repo riêng còn trống**:

```bash
mvn -B -ntp -Dmaven.repo.local=/tmp/perf-cold-m2 clean verify
```

Tuy nhiên:
- Đường dẫn `/tmp/perf-cold-m2` chỉ là ví dụ Linux/macOS, có thể chứa dữ liệu từ lượt trước; muốn cold thật phải dùng folder mới được quản lý.
- Maven sẽ cần download plugins/dependencies từ network; một network spike không chứng minh code compiler chậm.
- Không xóa toàn bộ `~/.m2` cá nhân hoặc shared CI cache chỉ để thử.
- Đừng trộn cold result với warm-clean result trong một median.

## 9. Sau Reactor Summary: tìm top plugin goals

Với profiler extension đã cài:

```bash
mvn -B -ntp -Dprofile -DprofileFormat=JSON,CONSOLE -DhideParameters=true clean verify
```

Thực hành:
1. Ghi module chậm nhất từ Reactor Summary.
2. Trong profiler JSON, tìm project tương ứng.
3. Xem top 3–5 mojo executions theo duration.
4. Đối chiếu chúng với source/test/packaging thực tế.
5. Nếu cần, đo sâu bằng Surefire reports/JFR/OS metrics.
6. Chọn **một giả thuyết tối ưu** để kiểm chứng.

**Bảng minh họa cho một dự án lớn khác ví dụ Java 17 ở mục 7:**

| Module | Duration | Goal chậm nhất | Goal duration | Hành động điều tra |
| --- | ---: | --- | ---: | --- |
| `api` | 3.0 s | `compiler:compile` | 1.9 s | JDK/annotation processors |
| `service` | 19.0 s | `surefire:test` | 13.8 s | Slow tests, fork, network |
| `distribution` | 8.0 s | `shade:shade` | 5.1 s | Transformers, artifact count |
| Toàn lệnh | **32.7 s wall** | — | — | Startup/resolution/overhead |

Số liệu hoàn toàn giả định. Không dùng chúng như kết quả đo thật của ứng dụng `perf-lab`. Nếu reactor parallel, cần timeline để xác định goal nào nằm trên critical path.

## 10. Khi Surefire chậm: đừng tự động bỏ tests

Nếu `surefire:test` là top goal:
- Đọc `target/surefire-reports` của đúng module, xem test class durations.
- So test body duration với goal duration (fork startup, JVM classloading, test discovery, setup/teardown).
- Kiểm external HTTP calls, DB containers, filesystem and lock waits trong fixtures.
- Xem `forkCount`, `reuseForks` và JUnit 5 concurrency khi tests thật sự thread-safe.
- Đo cùng test suite trong warm clean builds trước/sau thay đổi.
- Không đánh đổi test correctness hoặc isolation để có số đẹp.

Có thể chạy test class của Core riêng:

```bash
mvn -B -ntp -pl :perf-core -Dtest=GreetingTest test
```

`-pl :perf-core` chọn module Core theo artifactId; nếu module có dependency upstream trong reactor chưa install, cần cân nhắc `-am` để build required projects. Với ví dụ này Core không phụ thuộc module con khác, nên lệnh trên phù hợp.

**Cẩn thận khi dùng `-Dtest=GreetingTest` toàn reactor**: module không có class matching có thể khiến Surefire fail tùy config. Đừng lấy lỗi “No tests matching pattern” làm thời gian benchmark của successful build.

### `-DskipTests` khác `-Dmaven.test.skip=true`

- `-DskipTests` thường bỏ chạy tests nhưng vẫn compile test code.
- `-Dmaven.test.skip=true` có thể bỏ cả test compilation và execution trong các plugins hỗ trợ.
- Hai cách chỉ nên dùng **để bóc tách chi phí tương đối có ghi chú**. Chúng **không giữ nguyên phạm vi kiểm tra chất lượng**, không nên xem như optimization mặc định của CI release.

## 11. Khi compile/codegen chậm: đo đúng chi phí

Nếu Core chậm ở `compiler:compile`:
- Kiểm JDK/compiler plugin version và annotation processors;
- Xem generated sources, số files/classes và compiler warnings;
- Đảm bảo module không đưa các generated resources quá lớn vào compile source roots;
- Kiểm thay đổi một file có kích hoạt recompile bất thường không;
- Nếu compile fork external tool, đo thời gian fork/startup và JVM memory riêng;
- Không tối ưu bằng cách bỏ type checking hoặc dùng source classes cũ sai.

**`maven.compiler.release=17` chỉ là Java compatibility**, không phải một performance flag chắc chắn tăng tốc. Cần đo khi đổi compiler flags/JDK; nhớ kiểm output/test correctness.

## 12. Khi packaging chậm: JAR/WAR/Shade/Assembly

Một module có thể compile nhanh nhưng `shade:shade` hoặc `assembly:single` mất nhiều giây do:
- Đọc nhiều dependency JARs và giải nén;
- Merge service descriptors/resources;
- Manifest generation/relocation;
- ZIP compression, disk throughput;
- Large resources, duplicated archives.

Đo:
1. Module duration;
2. Thời gian `jar:jar`/`shade:shade` hoặc `assembly:single`;
3. Kích thước, số entries và disk I/O;
4. So outputs trước/sau nếu giảm input/artifact scope.

**Không tắt bước packaging cần cho release để báo build nhanh hơn.** Nếu thay Shade transformers hoặc excludes, kiểm ứng dụng vẫn chạy, không mất resources/service provider files.

## 13. Parallel reactor: tại sao `-T 1C` không phải lúc nào cũng nhanh?

Maven có thể chạy song song những modules **đủ điều kiện theo dependency graph**:

```bash
mvn -B -ntp -T 1C clean verify
```

`-T 1C` chọn thread count theo available CPU cores; `-T 4` chọn bốn threads. Không phải mọi module trong reactor đều có thể chạy song song.

Trong ví dụ:
- `perf-cli` có Maven dependency tới `perf-core`;
- CLI phải chờ Core artifact theo reactor order;
- Tăng thread count không thể làm hai modules này hoàn toàn độc lập.

Trong reactor gồm nhiều unrelated modules, parallelism có thể giúp hơn. Nhưng nếu CPU/RAM/disk đã bão hòa, tăng threads có thể khiến tổng wall time xấu đi hoặc làm tests flaky.

**Phép thử A/B:**
- Baseline warm clean với `-T 1`, 5–10 lượt.
- Candidate warm clean với `-T 1C`, 5–10 lượt.
- Giữ JDK, source, test scope, cache, runner class.
- So median và p90 (nếu đủ samples), CPU/memory, failure rate.
- Dùng timeline/tracing để thấy critical path và overlap.

Không cộng các module durations trong parallel build để suy ra wall time. Những duration chồng lấp không đại diện cho đường găng.

## 14. Chi phí CI không nhất thiết nằm trong Maven

CI job thường có:
1. Checkout source;
2. Setup JDK và Maven;
3. Restore dependency cache;
4. Run Maven;
5. Upload test reports/artifacts;
6. Cleanup.

Nếu Maven process mất 25 giây nhưng CI job 3 phút vì setup/restore cache/upload, việc tối ưu plugin goals chỉ có thể giảm **một phần nhỏ** của tổng pipeline time.

Nên ghi song song:
- **Job elapsed time** từ CI platform;
- **Maven invocation wall time**;
- **Per-module reactor times**;
- **Per-goal profiler times**;
- **Cache hit/miss và download durations**;
- **Runner CPU/RAM/concurrency**.

Nếu logs hoặc profiler JSON có secrets, cần redact trước khi đưa lên artifact storage/share. Upstream profiler có `-DhideParameters=true` để giảm user-property exposure.

## 15. Cách so số liệu trước và sau tối ưu

### 15.1. Lấy median trước khi tính phần trăm

Một bộ số **hoàn toàn minh họa** (đơn vị giây):

```text
Run 1: 15.2
Run 2: 14.9
Run 3: 15.7
Run 4: 15.0
Run 5: 16.1
```

Sau khi sort: `14.9, 15.0, 15.2, 15.7, 16.1`.

- **Median** = 15.2 s.
- Min = 14.9 s, Max = 16.1 s.
- **Range** = 1.2 s.
- Với chỉ 5 samples, không đưa ra tuyên bố p90 chắc chắn; nếu cần percentile, đo nhiều lượt và ghi rõ cách tính.

Giả sử sau thay đổi median = 12.4 s:

```text
Time saved = 15.2 - 12.4 = 2.8 s
Relative time reduction = 2.8 / 15.2 * 100 = 18.42%
Speedup factor = 15.2 / 12.4 = 1.23x
```

**Đây là phép tính ví dụ, không phải benchmark thực tế.** Phải ghi rõ test flags/conditions trước khi quyết định chấp nhận thay đổi.

### 15.2. Mẫu báo cáo ngắn nhưng đủ chứng cứ

| Trường | Ví dụ cần điền |
| --- | --- |
| Source revision | Commit SHA |
| Maven/JDK | Output đầy đủ của `mvn -version` |
| OS/runner | CPU, RAM, disk class, CI runner type |
| Cache mode | Cold / warm clean / incremental |
| Goals/profiles | `clean verify`, `-Prelease` nếu có |
| Threads | `-T 1` hoặc `-T 1C` |
| Samples | 5–10+ lượt với warm-up |
| Wall time | Median, min/max, p90 nếu đủ data |
| Slowest module | Maven GAV/module và duration |
| Slowest goal | Plugin goal/execution và duration |
| Change | Một thay đổi độc lập được thử |
| Correctness | Build/tests/artifact checks |
| Result | Time saved, percentage, uncertainty/trade-offs |
| Decision | Giữ, rollback hoặc thu thêm dữ liệu |

**Không dùng một lượt “nhanh nhất” làm headline mà bỏ median/variance.** Một CI runner chia sẻ CPU có thể tạo outlier lớn.

## 16. Những lỗi thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Chỉ nhìn `BUILD SUCCESS` | Không thấy bottleneck | Đo wall, module, goal |
| Chỉ xem `Total time` | Không phân biệt compiler/test/network | Reactor + profiler |
| Coi duration module là duration plugin | Nhầm hạt đo | Tìm mojo trong project report |
| Cộng module times khi dùng `-T` | Tổng lớn hơn wall vì overlap | Xem critical path |
| So `clean verify` với `verify` | Workload khác | Tách warm clean/incremental |
| So cold và warm mà không ghi cache | Gán tác động network cho code | Đo cache mode riêng |
| Một run duy nhất | Noise/outlier | Warm-up, đo nhiều lượt |
| Bật `-X` khi benchmark | Huge logs/I/O overhead | INFO + profiler có kiểm soát |
| Bật `-q` rồi tìm Reactor Summary | Log bị ẩn | Lưu INFO log |
| Dùng `-Pprofile` cho Maven Profiler | Kích hoạt nhầm POM profile | Dùng `-Dprofile` |
| Chưa cài `.mvn/extensions.xml` | Không có per-goal profiler | Tạo đúng core extension file |
| Chia sẻ profiler JSON chứa secrets | Rò rỉ parameters | `-DhideParameters=true`, review logs |
| Bỏ tests để giảm 40% | Thay đổi kiểm chứng chất lượng | Báo scope, không so cùng workload |
| Dùng `-T 1C` mà module graph tuần tự | Ít lợi ích | Xem reactor dependencies |
| Parallel plugins không thread-safe | Flaky build/race | Chọn thread count hợp lý |
| Cho rằng Surefire goal time = test body time | Bỏ qua fork/fixtures | Đọc Surefire report |
| Profiling extension làm wall time cao | Instrumentation overhead | A/B đo wall nhất quán |
| CPU chậm nhưng tối ưu network | Chọn sai nguyên nhân | Phân biệt CPU vs wait |
| CI job chậm nhưng chỉ nhìn Maven | Bỏ checkout/setup/upload | Đo từng giai đoạn CI |
| Thay 5 flags một lúc | Không xác định hiệu quả mỗi flag | Thử từng thay đổi |
| Không ghi baseline/source commit | Không tái lập benchmark | Lưu conditions/logs |
| Bỏ correctness checks | Build nhanh nhưng sai | Chạy tests và xác minh artifacts |

### Debug workflow thực tế

1. Ghi source commit và `mvn -version`.
2. Phân loại cold/warm/incremental.
3. Đo invocation wall time và exit code.
4. Đọc Reactor Summary để xác định module chậm.
5. Bật Maven Profiler 3.3 và đọc top mojos.
6. Xem Surefire/JFR/OS metrics khi cần.
7. Xác định critical path nếu có parallel build.
8. Nêu một giả thuyết bottleneck cụ thể.
9. Chạy A/B nhiều lượt cùng điều kiện, so median/range.
10. Kiểm toàn bộ tests/artifacts và giữ logs.
11. Ghi lợi ích bằng giây/phần trăm, trade-offs.
12. Nếu không có cải thiện rõ, rollback/đo lại.

## 17. Bài tập vận dụng

1. Vì sao Maven `BUILD SUCCESS` không cho biết goal nào chậm?
2. Reactor Summary và Maven Profiler khác nhau ở mức hạt đo nào?
3. Wall time và CPU time khác nhau ra sao?
4. Vì sao duration các modules có thể cộng lớn hơn total wall time ở `-T` build?
5. `-Dprofile` và `-Pprofile` khác nhau thế nào?
6. Profiler 3.3 nên được khai báo trong `pom.xml` `<plugins>` hay `.mvn/extensions.xml`?
7. Có cần xem JSON report trước khi đưa lên CI artifact storage không? Vì sao?
8. Tại sao lần đầu tải dependencies không đại diện cho warm clean?
9. `-ntp` có tắt download dependencies hay chỉ tắt transfer progress?
10. Vì sao `mvn verify` có thể vẫn chạy tests dù source không đổi?
11. `perf-cli` và `perf-core` có thể build hoàn toàn độc lập không? Vì sao?
12. Nếu `surefire:test` duration 8 giây nhưng tests chỉ mất 1 giây, nên kiểm gì?
13. Vì sao không nên dùng `-DskipTests` làm cùng một baseline với full tests?
14. Tại sao `-T 1C` có thể làm build chậm hơn?
15. Nếu một CI job 3 phút nhưng Maven chỉ 20 giây, cần đo thêm những gì?
16. Tại sao 5 mẫu có median tốt hơn chỉ chọn fastest run?
17. Baseline 15.2 s, candidate 12.4 s: reduction và speedup là bao nhiêu?
18. Java `Main` trong ví dụ in chính xác hai dòng nào?

### Đáp án định hướng

- **1:** Success chỉ xác nhận kết quả, không phân rã performance.
- **2:** Reactor theo module, Profiler theo mojo/goal execution.
- **3:** Wall là thời gian chờ, CPU là thời gian CPU xử lý.
- **4:** Các modules độc lập chạy đồng thời, durations overlap.
- **5:** `-D` kích hoạt property của profiler, `-P` kích hoạt Maven build profile.
- **6:** `.mvn/extensions.xml` ở root.
- **7:** Report/log có thể chứa user parameters/secrets.
- **8:** Nó gồm download/cache warmup/network.
- **9:** Chỉ tắt progress display.
- **10:** Plugin có thể vẫn thực thi theo lifecycle.
- **11:** Không, CLI phụ thuộc Core.
- **12:** JVM fork, discovery, fixtures, network/IO wait.
- **13:** Scope tests đã thay đổi.
- **14:** Contention, memory pressure, graph ít parallel, thread safety.
- **15:** Checkout, setup JDK, cache, artifact upload.
- **16:** Giảm tác động outlier khi số lượt vừa phải.
- **17:** Giảm khoảng 18.4%, nhanh hơn khoảng 1.23 lần.
- **18:** `Hello, Maven!` và `Hello, friend!`.

## 18. Checklist trước khi quyết định tối ưu Maven

- [ ] Chốt source commit, Maven/JDK versions, flags và active profiles.
- [ ] Phân biệt cold, warm clean và incremental scenarios.
- [ ] Đo wall time kèm exit status.
- [ ] Lấy Reactor Summary của từng module.
- [ ] Lấy per-goal report bằng Maven Profiler hoặc công cụ tương đương.
- [ ] Xác định goal chậm nhất trong module chậm nhất.
- [ ] Không nhầm mojo duration với CPU time.
- [ ] Khi `-T`, xem dependencies/critical path và timeline.
- [ ] Kiểm test reports nếu Surefire/Failsafe chậm.
- [ ] Kiểm network/download/CI caches nếu cold build chậm.
- [ ] Có một lượt warm-up và ít nhất 5 lượt baseline.
- [ ] So median và dao động thay vì fastest run.
- [ ] Giữ instrumentation/cách log nhất quán khi A/B.
- [ ] Tập trung sửa một bottleneck đã được đo.
- [ ] Không bỏ tests/quality gates để báo tăng tốc giả.
- [ ] Kiểm lại build correctness và artifacts sau thay đổi.
- [ ] Đo riêng Maven invocation và toàn CI job.
- [ ] Không để lộ secrets qua profiler/logs.
- [ ] Lưu report để người khác kiểm lại được.
- [ ] Kết luận chỉ trong phạm vi kịch bản đã đo.

**Kết luận:** Đo thời gian **từng mô-đun** bằng Reactor Summary giúp tìm nơi tốn công. Đo **từng bước/plugin goal** bằng Maven Profiler giúp biết compiler, test, codegen hay packaging mới là bottleneck. Nhưng chỉ khi kịch bản cold/warm/incremental được phân loại, có nhiều lượt đo và điều kiện A/B thống nhất, số liệu mới đủ tin cậy để ra quyết định tối ưu. Hãy tối ưu một vấn đề đã có bằng chứng, rồi xác nhận cả **thời gian** lẫn **độ đúng của build**.

## Tài liệu tham khảo

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Available Extensions](https://maven.apache.org/extensions/index.html)
- [Maven Profiler 3.3 — Upstream README](https://github.com/jcgay/maven-profiler)
- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Apache Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Apache Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/)
- [Apache Maven — Parallel Builds](https://cwiki.apache.org/confluence/display/MAVEN/Parallel+builds+in+Maven+3)
- [Oracle JDK 17 Flight Recorder](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html)