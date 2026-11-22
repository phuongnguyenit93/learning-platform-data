# Thread safety và những lưu ý khi Maven goal chạy trong Reactor song song

## 1. Vấn đề: `mvn verify` thành công, nhưng `mvn -T 2 verify` thất bại không ổn định

Một dự án Maven có ba mô-đun: `common`, `alpha` và `beta`. Hai mô-đun `alpha` và `beta` đều dùng `common`, nhưng không phụ thuộc vào nhau. Lệnh tuần tự:

~~~bash
mvn -B -ntp clean verify
~~~

thành công. Khi tăng tốc bằng:

~~~bash
mvn -B -ntp -T 2 clean verify
~~~

build đôi khi lỗi `AccessDeniedException`, báo cáo bị ghi đè, file bị hỏng, test không bind được cổng hoặc artifact của mô-đun này chứa nội dung của mô-đun kia.

Kết luận nhanh “Maven parallel bị lỗi” thường chưa đủ. Cần phân biệt **Reactor scheduling** với **thread safety của các Maven goals (Mojos)**, các dependencies thư viện mà goal sử dụng, trạng thái toàn cục được chia sẻ và tài nguyên bên ngoài quy trình Maven.

Mục tiêu của bài học:

1. Hiểu `-T`, Reactor dependency graph và điều kiện để hai module được chạy đồng thời.
2. Hiểu ý nghĩa thực sự của `@Mojo(threadSafe = true)` và cảnh báo “not marked as thread-safe”.
3. Phân biệt thread-safe *Mojo implementation* với việc **toàn bộ build pipeline** an toàn khi chạy song song.
4. Thiết kế goal tạo output theo **module-specific build directory**, tránh mutable static/singleton/file/cổng dùng chung.
5. Chạy một lab Maven 3.9+/Java 17/JUnit 5 có các mô-đun thực sự độc lập và một custom Maven Mojo tùy chọn.
6. Chẩn đoán lỗi chỉ xuất hiện với `-T`, chọn cách serialize, giới hạn concurrency, test căng tải và xác minh kết quả.

**Nguyên tắc:** `threadSafe=true` là một tuyên bố về khả năng chạy goal đồng thời; **nó không cấp khóa, không tự cô lập files, không biến thư viện không an toàn thành an toàn và không bảo đảm deterministic build**.

## 2. Maven Reactor song song hoạt động ở mức nào?

Reactor thu thập các Maven projects trong một multi-module build, xác định dependency graph rồi sắp xếp build. Maven 3 có cơ chế chạy các modules độc lập song song nếu sử dụng `-T`.

Ví dụ:

~~~text
                 reactor-root (packaging=pom)
                            |
                      common (jar)
                       /       \
                      v         v
                alpha (jar)   beta (jar)
~~~

`alpha` và `beta` phụ thuộc vào `common`. Do đó Maven phải làm xong những điều kiện cần thiết từ `common` trước khi cho consumers chạy; sau đó `alpha` và `beta` có thể chạy đồng thời khi đủ workers.

Điều đó **không** có nghĩa Maven tự chạy **hai goals trong cùng một module** song song theo bất kỳ thứ tự nào. Lifecycle phases/goals cho một project vẫn tuân thứ tự cần thiết, nhưng **goal của hai projects khác nhau** có thể được gọi trùng thời điểm.

### 2.1. `-T` là số worker cho Reactor, không phải một Java compiler flag

~~~bash
mvn -T 2 clean verify
mvn -T 4 clean verify
mvn -T 1C clean verify
mvn -T 1.5C clean verify
~~~

- `-T 2`: tối đa hai build threads theo thiết lập CLI.
- `-T 4`: bốn threads cho parallel Reactor.
- `-T 1C`: xấp xỉ một build thread trên mỗi CPU core mà Maven nhận biết.
- `-T 1.5C`: nhân số core với 1,5, có thể tạo nhiều workers hơn cores.

Trong tình huống nhiều threads nhưng chỉ có một module hoặc dependency graph tạo một chuỗi tuyến tính, mức concurrency thực tế vẫn thấp. `-T 8` không tạo ra tám modules có thể chạy độc lập từ một graph vốn chỉ có một nhánh.

Chạy tuần tự để có baseline:

~~~bash
mvn -B -ntp clean verify
~~~

Có thể dùng `-T 1` cho một build chỉ có một worker, nhưng **loại bỏ `-T` hoàn toàn** là cách đối chiếu rõ ràng nhất với chế độ sequential thông thường.

### 2.2. `<modules>` không thay thế `<dependencies>`

~~~xml
<modules>
    <module>common</module>
    <module>alpha</module>
    <module>beta</module>
</modules>
~~~

Danh sách này cho Maven biết những projects sẽ được aggregate. Để `alpha` hoặc `beta` dùng class từ `common`, consumer POM phải có dependency thật tới `common` với GAV đúng.

Nếu khai báo thiếu dependency edge, Reactor có thể chạy module trước khi các class cần thiết sẵn sàng; thêm threads làm lộ cấu hình thiếu vốn đã tiềm ẩn ngay cả khi build tuần tự từng “tình cờ” pass vì local cache.

## 3. Ba mức độ độc lập cần tách rõ

| Mức độ | Đơn vị xét | Ví dụ |
| --- | --- | --- |
| Reactor parallelism | Mô-đun Maven | `alpha` và `beta` build đồng thời |
| Plugin/Mojo thread safety | Các invocation của goal trong cùng Maven process | `audit:report` ở `alpha` và `beta` không tranh chấp state |
| Test parallelism | JUnit tests/forks/threads | Surefire chạy tests song song theo cấu hình riêng |

Một `mvn -T 2 verify` **không tự bật JUnit parallel execution trong một module**. Tuy nhiên nếu hai modules đều có Surefire executions, hai test suites có thể được thực thi cùng lúc dưới hai module build threads, thường bằng hai forked JVMs.

Đây là lý do một unit test “chạy tuần tự thì pass” có thể fail dưới `-T` dù bản thân Maven goal `surefire:test` đã được đánh dấu thread-safe: **tests của bạn** có thể tranh cùng TCP port, cùng database schema hoặc cùng file tạm.

Ngược lại, bật parallel JUnit bên trong một module cũng không tự mở Reactor multi-module parallelism. Hai knobs cần thiết kế/test độc lập.

## 4. Mojo là gì và `@Mojo(threadSafe=true)` có ý nghĩa gì?

Một Maven plugin có thể có nhiều **goals**. Mỗi goal thường được triển khai bằng một **Mojo class**, kế thừa `org.apache.maven.plugin.AbstractMojo` và có method `execute()`.

Với Maven Plugin Tools Java Annotations:

~~~java
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.LifecyclePhase;

@Mojo(
    name = "module-report",
    defaultPhase = LifecyclePhase.PROCESS_CLASSES,
    threadSafe = true
)
public final class ModuleReportMojo extends AbstractMojo {
    // Chi tiết runnable đầy đủ ở phần 12.
}
~~~

Đây là **fragment minh họa**, chưa phải file Java độc lập. Khi Maven Plugin Plugin tạo plugin descriptor, `threadSafe` xuất hiện trong metadata của **goal**, chẳng hạn `<threadSafe>true</threadSafe>` trong `META-INF/maven/plugin.xml`.

Ý nghĩa của annotation theo API: tác giả plugin khẳng định goal **hỗ trợ gọi đồng thời một cách an toàn trong parallel builds**. Nó không phải chỉ thị “hãy chạy goal này song song”, không phải Java `synchronized`, không phải cơ chế khóa file và không phải một phép kiểm tự động chứng minh implement đúng.

### 4.1. `@Mojo(threadSafe=false)` không đồng nghĩa Maven chắc chắn chặn goal

Giá trị mặc định của annotation là `false`. Với Maven 3 parallel builds, nếu execution plan chứa goals chưa được đánh dấu an toàn, Maven thường **in cảnh báo nhưng vẫn tiếp tục build**. Bởi vậy không được kỳ vọng Maven 3 tự serialize mọi unsafe goal.

Thông điệp thường có nội dung gần nghĩa:

~~~text
Your build is requesting parallel execution,
but this project contains plugin goals
not marked as thread-safe to support parallel execution.
~~~

**Đây là cảnh báo, không nhất thiết là lỗi build.** Một goal không có annotation có thể chạy đúng trong tình huống hiện tại; nhưng chưa có sự bảo đảm từ tác giả plugin. Ngược lại, một goal có annotation nhưng implementation sai vẫn có thể gây race.

Không nên tự xóa cảnh báo bằng cách thêm `threadSafe=true` mà chưa audit thư viện, static state, shared resources và thực hiện concurrency tests.

### 4.2. `aggregator=true` là điều khác

~~~java
@Mojo(
    name = "aggregate-report",
    aggregator = true,
    threadSafe = false
)
~~~

`aggregator` nói về **mục tiêu làm việc với toàn bộ project set/aggregation**, còn `threadSafe` nói về an toàn đồng thời. Một aggregator goal không tự trở thành global mutex, cũng không tự đồng nghĩa “chỉ chạy một lần dù bind ở mọi child”.

Khi authoring aggregator goal, phải nghiên cứu rõ **cách goal được invoke, bound phase, root project selection, execution strategy** và Maven major version. Nếu goal tổng hợp đọc reports từ mọi module, cần chắc rằng producer modules đã hoàn thành trước lúc aggregation, hoặc đặt một bước tổng hợp tách biệt sau Reactor.

## 5. Một Mojo an toàn cần xem xét những state nào?

Để đánh giá thread safety, không chỉ xem class Mojo. Xem mọi trạng thái mà `execute()` và các dependencies chạm tới:

1. Field `static` mutable trong class Mojo hoặc helper.
2. Singleton do Plexus/JSR-330 dependency injection cung cấp.
3. Collections, caches, builders, formatters không được đồng bộ.
4. `System.setProperty`, default locale/timezone, JVM-wide state.
5. Shared working directory, shared output file path hoặc `target/` của root.
6. Các file được ghi bằng `FileWriter`, `Files.writeString`, stream không atomic.
7. Temporary directories dùng tên cố định (`/tmp/report`, `build/output.json`).
8. Logs và global counters.
9. Maven session/repository metadata hoặc project model bị mutate.
10. External systems: TCP ports, database schemas, Docker containers, remote endpoints, credentials, test fixtures.
11. Child processes tạo bởi `ProcessBuilder`, shell scripts và công cụ không thread-safe.
12. Plugin libraries có classloader/caches riêng, đặc biệt shared mutable singletons.
13. Build outputs và attached artifacts trỏ cùng đường dẫn giữa nhiều modules.
14. Thứ tự đọc/ghi files của các goals ở phase khác nhau.

**Biên giới thực:** Một goal được coi an toàn không phải vì nó “chỉ chạy nhanh” hoặc “không có static trong class Mojo”; third-party helper hoặc external state vẫn có thể gây race.

## 6. Sai lầm phổ biến: ghi mọi module vào cùng một file

Một implementation có vấn đề:

~~~java
// PHẢN VÍ DỤ: không dùng khi chạy reactor song song.
Path report = Path.of("reports", "report.txt");
Files.writeString(report, content);
~~~

Nếu mỗi `execute()` được gọi với different working directory thì có thể tình cờ tạo file riêng; nhưng khi plugin tự cố định `rootDirectory/reports/report.txt`, hoặc Maven launcher/CI chọn một working directory chung, `alpha` và `beta` sẽ ghi đè cùng đường dẫn.

Lỗi có thể là:
- `FileAlreadyExistsException`.
- `AccessDeniedException` trên Windows.
- Truncated/partial report.
- Nội dung report của alpha bị beta thay thế.
- “Last writer wins” nhưng CI vẫn `BUILD SUCCESS`.
- Tình trạng rất khó tái hiện do thread scheduling.

**Giải pháp:** sử dụng `${project.build.directory}` được Maven inject cho **module hiện tại**, rồi tạo file dưới đó.

~~~java
// FRAGMENT: buildDirectory được inject theo module POM.
Path report = buildDirectory.toPath()
        .resolve("thread-audit")
        .resolve("report.txt");
~~~

Một module `alpha` dùng `alpha/target/thread-audit/report.txt`, còn `beta` dùng `beta/target/thread-audit/report.txt`. Việc module-specific output **loại bỏ một dạng tranh chấp file**, không tự chứng minh mọi dependency khác thread-safe.

## 7. Lab Maven 3.9+/Java 17: dự án thực sự có hai modules song song

Tạo project minh họa:

~~~text
parallel-reactor-lab/
├── pom.xml
├── common/
│   ├── pom.xml
│   └── src/
│       ├── main/java/com/example/parallel/common/MathTwice.java
│       └── test/java/com/example/parallel/common/MathTwiceTest.java
├── alpha/
│   ├── pom.xml
│   └── src/
│       ├── main/java/com/example/parallel/alpha/AlphaApp.java
│       └── test/java/com/example/parallel/alpha/AlphaAppTest.java
└── beta/
    ├── pom.xml
    └── src/
        ├── main/java/com/example/parallel/beta/BetaApp.java
        └── test/java/com/example/parallel/beta/BetaAppTest.java
~~~

`common` là upstream của `alpha` và `beta`. Hai consumers độc lập nên Maven Reactor có thể build đồng thời. Source Java không ghi file/port chung; bài lab đầu tiên nhằm chứng minh parallel build đúng trước khi thử custom Mojo.

**Điều kiện:** Maven 3.9+, JDK 17+ và quyền tải Maven plugins/JUnit từ artifact repositories. POM pin versions tương thích Java17.

## 8. Root `pom.xml` hoàn chỉnh

Tạo `parallel-reactor-lab/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.parallel</groupId>
    <artifactId>parallel-lab-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>common</module>
        <module>alpha</module>
        <module>beta</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.version>5.11.4</junit.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example.parallel</groupId>
                <artifactId>common</artifactId>
                <version>1.0.0</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <pluginManagement>
            <plugins>
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
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.5.1</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

**Chú ý:**
- Root `packaging=pom` là parent và aggregator, không tạo application JAR.
- `common` được khai báo trước, nhưng Reactor ordering còn do real dependencies quyết định.
- `dependencyManagement` quản lý version `common`; nó **không tự thêm dependency** cho alpha/beta.
- JUnit Jupiter scope `test` được children thừa hưởng qua parent.
- Plugin versions được pin rõ. Maven Compiler Plugin 3.16.0, Surefire 3.6.1 và JAR Plugin 3.5.1 là các bản phát hành hiện hành ở thời điểm viết; doanh nghiệp nên dùng versions đã phê duyệt sau khi test matrix.
- `maven.compiler.release=17` giữ Java language/API/classfile baseline; nó không điều khiển số threads.
- Không có plugin tự viết ở POM này; các goals của custom plugin chỉ được thêm trong phần mở rộng sau.

## 9. `common/pom.xml` và Java source

POM thư viện `common`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.parallel</groupId>
        <artifactId>parallel-lab-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>common</artifactId>
    <packaging>jar</packaging>
</project>
~~~

Tạo `common/src/main/java/com/example/parallel/common/MathTwice.java`:

~~~java
package com.example.parallel.common;

public final class MathTwice {

    private MathTwice() {
    }

    public static int twice(int value) {
        return Math.multiplyExact(value, 2);
    }
}
~~~

`Math.multiplyExact` phát hiện integer overflow, phù hợp với mục đích unit test. Class **không có static mutable state**; `MathTwice.twice` tính toán thuần và không ghi file/port chung.

Tạo `common/src/test/java/com/example/parallel/common/MathTwiceTest.java`:

~~~java
package com.example.parallel.common;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class MathTwiceTest {

    @Test
    void doubles() {
        assertEquals(6, MathTwice.twice(3));
    }

    @Test
    void detectsOverflow() {
        assertThrows(ArithmeticException.class,
                () -> MathTwice.twice(Integer.MAX_VALUE));
    }
}
~~~

Có **2 test methods** trong `common`. Phương thức `detectsOverflow` cần số nhân làm tràn `int`; `Integer.MAX_VALUE * 2` được `Math.multiplyExact` kiểm an toàn.

## 10. `alpha/pom.xml` và Java source

Tạo `alpha/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.parallel</groupId>
        <artifactId>parallel-lab-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>alpha</artifactId>

    <dependencies>
        <dependency>
            <groupId>com.example.parallel</groupId>
            <artifactId>common</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Child không cần ghi version của `common`, vì parent `dependencyManagement` đã xác định `1.0.0`. Đây vẫn là **actual dependency**. Nếu xóa nó, import class sẽ không có compile classpath.

Tạo `alpha/src/main/java/com/example/parallel/alpha/AlphaApp.java`:

~~~java
package com.example.parallel.alpha;

import com.example.parallel.common.MathTwice;

public final class AlphaApp {

    private AlphaApp() {
    }

    public static String message() {
        return "ALPHA=" + MathTwice.twice(3);
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Tạo `alpha/src/test/java/com/example/parallel/alpha/AlphaAppTest.java`:

~~~java
package com.example.parallel.alpha;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AlphaAppTest {

    @Test
    void usesSharedLibrary() {
        assertEquals("ALPHA=6", AlphaApp.message());
    }
}
~~~

Trong `alpha` có **1 JUnit test method**, không ghi bất kỳ file hay port chung nào.

## 11. `beta/pom.xml` và Java source

Tạo `beta/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.parallel</groupId>
        <artifactId>parallel-lab-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>beta</artifactId>

    <dependencies>
        <dependency>
            <groupId>com.example.parallel</groupId>
            <artifactId>common</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Tạo `beta/src/main/java/com/example/parallel/beta/BetaApp.java`:

~~~java
package com.example.parallel.beta;

import com.example.parallel.common.MathTwice;

public final class BetaApp {

    private BetaApp() {
    }

    public static String message() {
        return "BETA=" + MathTwice.twice(4);
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Tạo `beta/src/test/java/com/example/parallel/beta/BetaAppTest.java`:

~~~java
package com.example.parallel.beta;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BetaAppTest {

    @Test
    void usesSharedLibrary() {
        assertEquals("BETA=8", BetaApp.message());
    }
}
~~~

Trong `beta` có **1 test method**. Tổng cả Reactor: `common` 2, `alpha` 1, `beta` 1, tức **4 JUnit test methods**. Root `pom` không có source/test.

## 12. Build lab tuần tự và song song, xác minh kết quả

Trong `parallel-reactor-lab/`:

~~~bash
mvn -version
java -version
mvn -B -ntp clean verify
mvn -B -ntp -T 2 clean verify
~~~

Khi mọi dependencies/plugins resolve được và tests pass, cả hai lệnh có `BUILD SUCCESS`. Với `-T 2`, Maven có thể xử lý `alpha` và `beta` đồng thời sau `common`; **không cam kết thứ tự log/hoàn thành alpha trước beta**.

Có thể chạy app từ `target/classes`, đưa `common` vào runtime classpath.

POSIX/Linux/macOS:

~~~bash
java -cp "alpha/target/classes:common/target/classes" com.example.parallel.alpha.AlphaApp
java -cp "beta/target/classes:common/target/classes" com.example.parallel.beta.BetaApp
~~~

Windows PowerShell:

~~~powershell
java -cp "alpha/target/classes;common/target/classes" com.example.parallel.alpha.AlphaApp
java -cp "beta/target/classes;common/target/classes" com.example.parallel.beta.BetaApp
~~~

**Stdout chính xác**, theo thứ tự hai lệnh chạy tuần tự phía trên:

~~~text
ALPHA=6
BETA=8
~~~

Đây là stdout của **hai Java main programs**, không phải Maven log. JAR modules chưa được cấu hình `Main-Class` hoặc fat JAR; không dùng `java -jar alpha/target/alpha-1.0.0.jar` và kỳ vọng tự chạy.

### 12.1. Quan sát Reactor summary và warnings

Dưới parallel mode, log có thể interleave:

~~~text
... common ...
... alpha ...
... beta ...
BUILD SUCCESS
~~~

Đây là minh họa ý nghĩa, không phải stdout cố định. Maven có thể hiển thị Reactor Summary ở cuối nhưng **thứ tự các dòng do modules log ra trong lúc chạy không phải contract**.

Đừng test string equality của **toàn bộ Maven console log** khi bật `-T`. Hãy test kết quả artifacts, JUnit XML, file output theo từng module và exit code.

## 13. Authoring custom Maven plugin: một goal thread-safe hoàn chỉnh

Lab trên sử dụng Maven core plugins để kiểm Reactor parallelism. Bây giờ tạo **một project plugin riêng** để thấy `@Mojo(threadSafe=true)` được dùng đúng.

Tại một folder ngang hàng với `parallel-reactor-lab`:

~~~text
workspace/
├── parallel-reactor-lab/        (POM + common/alpha/beta phần trên)
└── parallel-audit-maven-plugin/
    ├── pom.xml
    └── src/main/java/com/example/tools/ModuleReportMojo.java
~~~

Plugin project tách khỏi Reactor lab để khi thêm goal vào root POM, plugin đã được cài vào Maven local repository và không gặp vấn đề plugin artifact chưa resolve.

### 13.1. `parallel-audit-maven-plugin/pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.tools</groupId>
    <artifactId>parallel-audit-maven-plugin</artifactId>
    <version>1.0.0</version>
    <packaging>maven-plugin</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.maven</groupId>
            <artifactId>maven-plugin-api</artifactId>
            <version>3.9.9</version>
            <scope>provided</scope>
        </dependency>
        <dependency>
            <groupId>org.apache.maven.plugin-tools</groupId>
            <artifactId>maven-plugin-annotations</artifactId>
            <version>3.16.0</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-plugin-plugin</artifactId>
                <version>3.16.0</version>
                <configuration>
                    <goalPrefix>parallel-audit</goalPrefix>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`maven-plugin` packaging cùng Maven Plugin Plugin tạo `META-INF/maven/plugin.xml` để Maven biết goals và metadata. `maven-plugin-api` và `maven-plugin-annotations` dùng `provided` vì plugin runtime/Maven tooling quản lý các API tương ứng, không bundle chúng như app dependencies.

Maven Plugin Plugin 3.16.0 và annotations 3.16.0 được pin cùng version. Maven Plugin API 3.9.9 hợp với dải Maven 3.9.x của ví dụ. Khi dùng Maven 4, cần kiểm plugin API/tooling requirement riêng; **đừng giả định plugin 3.x đã phù hợp mọi Maven 4-specific API**.

### 13.2. `ModuleReportMojo.java` đầy đủ

Tạo `parallel-audit-maven-plugin/src/main/java/com/example/tools/ModuleReportMojo.java`:

~~~java
package com.example.tools;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugins.annotations.LifecyclePhase;
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.Parameter;

@Mojo(
        name = "module-report",
        defaultPhase = LifecyclePhase.PROCESS_CLASSES,
        threadSafe = true
)
public final class ModuleReportMojo extends AbstractMojo {

    @Parameter(
            defaultValue = "${project.build.directory}",
            readonly = true,
            required = true
    )
    private File buildDirectory;

    @Parameter(
            defaultValue = "${project.groupId}",
            readonly = true,
            required = true
    )
    private String groupId;

    @Parameter(
            defaultValue = "${project.artifactId}",
            readonly = true,
            required = true
    )
    private String artifactId;

    @Override
    public void execute() throws MojoExecutionException {
        Path directory = buildDirectory.toPath()
                .resolve("thread-audit");
        Path output = directory.resolve("module.txt");

        String content = "module="
                + groupId
                + ":"
                + artifactId
                + "\n";

        try {
            Files.createDirectories(directory);
            Files.writeString(
                    output,
                    content,
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.TRUNCATE_EXISTING,
                    StandardOpenOption.WRITE
            );
        } catch (IOException error) {
            throw new MojoExecutionException(
                    "Cannot write module-specific report: "
                            + output,
                    error
            );
        }

        getLog().info("Module report: " + output);
    }
}
~~~

**Tại sao đây là một thiết kế thread-safe hợp lý cho lab?**
- `buildDirectory` được inject theo **project/Mojo execution**, không dùng static mutable state.
- Mỗi module tạo file dưới **`${project.build.directory}` riêng**, thường là `<module>/target/thread-audit/module.txt`.
- `content` là biến local trong `execute()`, không chia sẻ giữa invocations.
- Không mutate POM/project model hoặc `System` global state.
- Không truy cập TCP port/database/server chia sẻ.
- Không dùng một singleton mutable.
- Log có thể xen kẽ, nhưng bản thân thông điệp không được dùng làm shared result.
- `Files.writeString` **không tự atomic cho concurrent writers**. Nó hợp lý ở đây vì ta thiết kế để những invocations hợp lệ **không bao giờ cùng ghi một path**.

Nếu hai executions khác nhau trong **cùng module** bị cấu hình trỏ vào cùng một output, hoặc hai Maven processes đồng thời build chính **một checkout chung**, giả định “mỗi module một path” không còn đủ. `threadSafe=true` không phải bảo đảm cho mọi cách cấu hình bất thường.

### 13.3. Compile và cài plugin trước

Tại `workspace/`:

~~~bash
mvn -B -ntp -f parallel-audit-maven-plugin/pom.xml clean install
~~~

Lệnh này build plugin và cài artifact của nó vào **Maven local repository**. Không chạy một `mvn -f parallel-reactor-lab/pom.xml` có binding plugin trước khi plugin thực sự resolve được.

### 13.4. Bind custom goal vào Reactor lab

Trong root `parallel-reactor-lab/pom.xml`, bên trong `<build>` **thêm sibling element `<plugins>` cạnh `<pluginManagement>`** như fragment sau:

~~~xml
<plugins>
    <plugin>
        <groupId>com.example.tools</groupId>
        <artifactId>parallel-audit-maven-plugin</artifactId>
        <version>1.0.0</version>
        <executions>
            <execution>
                <id>make-module-report</id>
                <phase>process-classes</phase>
                <goals>
                    <goal>module-report</goal>
                </goals>
            </execution>
        </executions>
    </plugin>
</plugins>
~~~

**Đừng tạo một `<build>` thứ hai trong cùng `pom.xml`.** Plugin execution này được children thừa hưởng theo Maven model inheritance. Root `pom` project cũng có thể thực thi goal được bind vào phase đó; plugin dùng root project `target` riêng nên vẫn không đụng child outputs.

`<defaultPhase>` trong annotation cho Maven biết default lifecycle phase của goal; **execution fragment cũng bind rõ phase** để dễ audit.

### 13.5. Chạy cùng một goal ở các modules song song

Từ `parallel-reactor-lab/`:

~~~bash
mvn -B -ntp -T 2 clean verify
~~~

Các output kỳ vọng (có thể có thêm report của root POM):

~~~text
parallel-reactor-lab/target/thread-audit/module.txt
parallel-reactor-lab/common/target/thread-audit/module.txt
parallel-reactor-lab/alpha/target/thread-audit/module.txt
parallel-reactor-lab/beta/target/thread-audit/module.txt
~~~

**Nội dung chính xác** của `alpha/target/thread-audit/module.txt`:

~~~text
module=com.example.parallel:alpha
~~~

**Nội dung chính xác** của `beta/target/thread-audit/module.txt`:

~~~text
module=com.example.parallel:beta
~~~

Hai files có nội dung riêng và vị trí không trùng nhau. Đây là **kiểm chứng theo output**, không suy từ thứ tự Maven log.

### 13.6. Vì sao không dùng `Thread.sleep` để chứng minh an toàn?

Thêm một `Thread.sleep(1000)` vào goal có thể làm hai log entries trông như “chạy cùng lúc”, nhưng điều đó **không chứng minh dữ liệu an toàn hoặc không race**. Test chính xác phải kiểm output, failure modes, module order, concurrency stress và có khả năng lặp lại. Timing không phải bằng chứng thread safety.

## 14. Plugin descriptor mới là nơi Maven đọc cờ `threadSafe`

Source annotation được Maven Plugin Tools dịch vào plugin descriptor. Sau `mvn ... install` của plugin, có thể kiểm JAR:

~~~bash
jar tf parallel-audit-maven-plugin/target/parallel-audit-maven-plugin-1.0.0.jar
~~~

Trong danh sách entries phải có:

~~~text
META-INF/maven/plugin.xml
~~~

Trên POSIX có `unzip`:

~~~bash
unzip -p parallel-audit-maven-plugin/target/parallel-audit-maven-plugin-1.0.0.jar META-INF/maven/plugin.xml
~~~

Trong XML của `module-report`, tìm field:

~~~xml
<threadSafe>true</threadSafe>
~~~

`@Mojo(threadSafe=true)` trong source **không đủ** nếu Maven Plugin Plugin chưa generate/đóng gói descriptor mới hoặc consumer đang resolve một version artifact cũ từ repository. Đừng chỉ xem source; kiểm **JAR plugin thực tế Maven đang chạy**, goal descriptor và Maven log.

Nếu Maven vẫn warning sau khi bạn sửa annotation:
1. Kiểm Maven đang dùng đúng plugin GAV/version.
2. Build/install lại plugin theo workflow hợp lệ.
3. Kiểm `plugin.xml` bên trong JAR đã publish.
4. Kiểm warnings có nhắc một **goal khác** trong cùng plugin không.
5. Kiểm plugin dependencies có lỗi chưa được audit không.
6. Tránh ghi đè immutable release artifact cùng version; publish version mới khi đưa vào repo team.

## 15. Tại sao static mutable fields nguy hiểm?

Một mẫu code không an toàn:

~~~java
// PHẢN VÍ DỤ: fragment không phải Mojo đầy đủ.
private static final StringBuilder EVENTS =
        new StringBuilder();

public void execute() {
    EVENTS.append(artifactId).append('\n');
}
~~~

Dù field là `final`, **đối tượng `StringBuilder` vẫn mutable và không thread-safe**. Nếu các Mojo executions dùng chung classloader/object, hai invocations có thể append interleaved làm sai dữ liệu.

Một anti-pattern khác:

~~~java
// PHẢN VÍ DỤ: ++ không atomic.
private static int goalCount = 0;

public void execute() {
    goalCount++;
}
~~~

Với concurrent threads, giá trị cuối có thể thấp hơn số executions. Dùng `AtomicInteger` giải quyết vấn đề increment in-memory cụ thể, nhưng **không tự giải quyết** việc mỗi module ghi chung một file và không có ý nghĩa cho global coordination giữa hai Maven processes độc lập.

### 15.1. Không mọi `static final` đều nguy hiểm

~~~java
private static final String FILE_NAME = "module.txt";
~~~

`String` immutable constant là an toàn để chia sẻ. Vấn đề là **mutability và invariants**, không phải chỉ vì thấy từ khóa `static`.

Tránh đưa `SimpleDateFormat`, `NumberFormat`, `DateFormat` mutable vào static global dùng chung. Nếu cần format dữ liệu, chọn immutable `java.time.format.DateTimeFormatter` hoặc tạo instance local phù hợp.

## 16. Singleton và dependency injection: state được chia sẻ ngoài Mojo

Ngay cả khi Mojo fields đều local theo execution, plugin có thể inject một service:

~~~java
// Fragment: service có thể là singleton.
@Component
private ReportRepository reportRepository;
~~~

Nếu `ReportRepository` có `HashMap` nội bộ, cached writer hoặc global active-project field, các calls từ alpha/beta có thể race.

Cần audit:
- Plexus `components.xml` với role/scope như singleton.
- `@Named`, `@Singleton`, injected services theo framework thực tế.
- Libraries dùng static caches hoặc thread-local state không được clear.
- Shared Maven session/project model mutation.
- Services dùng `System.setProperty` làm configuration global.
- External CLI tools invoked song song nhưng dùng cùng output directory.

`ConcurrentHashMap` làm container thread-safe cho một số operations, nhưng **không tự làm chuỗi thao tác `get` rồi `put` có invariants atomic**. Có thể cần `compute`, lock hoặc tách per-module state.

Thực tiễn tốt nhất là **stateless services hoặc immutable data**, và truyền rõ module context vào mỗi operation.

## 17. Output path và filesystem isolation là lớp bảo vệ đầu tiên

Trong một custom goal, thường chọn:

~~~text
${project.build.directory}/generated-sources/...
${project.build.directory}/reports/...
${project.build.directory}/thread-audit/module.txt
~~~

Thay vì:

~~~text
${session.executionRootDirectory}/output.txt
${user.home}/.cache/my-plugin/last-result.json
/tmp/shared-report.txt
target/report.txt dưới workspace root cố định
~~~

Đường dẫn dùng chung **không luôn sai**, nhưng phải có synchronization/transaction/versioning phù hợp và phải biết chính xác writers/readers nào có thể chạy đồng thời.

### 17.1. Ghi file theo chiến lược an toàn

Khi output là module-specific, `Files.createDirectories` + `Files.writeString` đủ cho lab. Với hệ thống production và quan hệ reader/writer phức tạp:
1. Ghi vào file tạm **cùng filesystem** với destination.
2. Flush/close trước khi công bố.
3. Atomic move/replace khi filesystem hỗ trợ `ATOMIC_MOVE`, có fallback có kiểm soát.
4. Khi nhiều writers được phép vào cùng destination, dùng file lock/coordination hoặc single-writer design.
5. Ghi log stage + checksum/provenance để phát hiện output hỏng.
6. Không nuốt `IOException` và tiếp tục `BUILD SUCCESS`.

`StandardCopyOption.ATOMIC_MOVE` có thể **không được hỗ trợ** trên mọi filesystem/remote mount. Nó không phải phép màu sửa hai invocations tranh nhau dùng cùng tên temp file.

### 17.2. Không sửa outputs của module khác

Một goal ở `alpha` ghi vào `../beta/target/generated-sources` phá ranh giới project. Với `-T`, beta có thể đang compile hoặc clean chính thư mục đó. Thiết kế đúng: nếu alpha cần publish artifacts cho beta, khai báo dependency/module relationship và phân phối artifact thông qua Reactor/repository, không ghi lén vào build dir của nhau.

## 18. File locks trong một JVM khác locks giữa nhiều Maven processes

`synchronized` hoặc `ReentrantLock` chỉ phối hợp các threads **cùng chia sẻ lock object trong một JVM**.

Nếu CI đồng thời chạy:

~~~bash
mvn -T 2 verify
~~~

ở **hai processes** trỏ vào **cùng workspace**, một `static synchronized` trong Mojo **không ngăn được process khác** dùng cùng path. Khi build ở hai containers/hosts còn phức tạp hơn.

Các giải pháp tùy trường hợp:
- Một workspace/build directory riêng cho mỗi CI job.
- Không chạy hai builds đồng thời trên cùng output tree.
- File lock cross-process khi cần và filesystem hỗ trợ.
- Transactional database/remote coordination cho shared services.
- Chuyển shared output sang single-writer aggregation step.
- Không dùng plugin-local Java mutex như một distributed lock giả.

Ngay cả khi plugin của bạn thread-safe trong một process, user hoặc CI vẫn có thể làm hỏng output bằng cách mở hai Maven invocations vào cùng checkout.

## 19. Unit tests và integration tests khi bật `-T`

Surefire Plugin có fork behavior và các cấu hình chạy tests riêng. Với Reactor parallelism:
- `alpha` có Surefire execution của nó.
- `beta` có Surefire execution riêng.
- Hai suites có thể chạy đồng thời dù JUnit trong từng suite vẫn sequential.

Một test dùng:

~~~java
// PHẢN VÍ DỤ cho parallel module tests:
ServerSocket server = new ServerSocket(8080);
~~~

có thể fail `BindException: Address already in use` khi suites ở hai modules cùng chiếm port 8080.

Khi muốn test HTTP service:
1. Dùng **port 0** để OS chọn available port trong những tests hỗ trợ.
2. Lấy port thực từ server instance để client kết nối.
3. Đóng server trong `try/finally` hoặc lifecycle hook.
4. Không dùng shared temp filenames.
5. Không reuse database schema/table state giữa concurrently running modules.
6. Dùng Testcontainers/service names/network isolation theo khả năng.
7. Nếu external environment không thể isolation, serialize những tests đó thay vì bỏ kiểm.

### 19.1. `@TempDir` của JUnit giúp tách file temp trong một suite

JUnit Jupiter có `@TempDir` để cung cấp thư mục tạm riêng theo scope phù hợp:

~~~java
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class TempReportTest {
    @TempDir
    Path tempDir;

    @Test
    void writesOnlyWithinOwnTempDir() throws Exception {
        java.nio.file.Path result =
                tempDir.resolve("report.txt");

        java.nio.file.Files.writeString(
                result, "ok\n");

        org.junit.jupiter.api.Assertions.assertEquals(
                "ok\n",
                java.nio.file.Files.readString(result));
    }
}
~~~

**Đây là một test class minh họa độc lập**, không thuộc các 4 methods của lab phần 7–12; nếu muốn chạy nó, thêm vào module test sources với Java17/JUnit5 có sẵn. Test trên không ghi root/shared temp file và không cần cổng cố định.

Nếu test cần Maven plugin context/real reactor, JUnit test Java đơn thuần chưa đủ; phải có plugin integration tests/Invoker integration với `mvn -T`.

## 20. Thread-safe Mojo không đồng nghĩa thread-safe library hoặc native tool

Một Mojo có thể gọi code generator chạy bên ngoài:

~~~text
Mojo.execute()
  -> ProcessBuilder("generator", "--out", "/tmp/result")
  -> generator writes shared config/cache
~~~

Dù Mojo tạo thread-safe Java objects, **generator** có thể dùng global mutable files hoặc process-wide config. Chạy hai invocations có thể tạo file sai hoặc conflict.

Audit:
- Tool command line có trỏ đến module-specific input/output không.
- Tool dùng shared cache có file locks không.
- Native binary có giữ static/global state giữa threads/processes không.
- Maven plugin dependency có version được chứng minh thread-safe không.
- Code generation có deterministic, reproducible outputs không.
- Runner filesystem/OS có hành vi lock phù hợp không.

Nếu tool không có chế độ concurrent an toàn, tách goal ra sequential phase/job hoặc cấp working directory riêng cho từng invocation.

## 21. Annotation processors: một nguồn xung đột khó thấy

Nếu hai modules dùng cùng annotation processor, dù mỗi `javac` là process/tool invocation riêng, processor có thể:
- Viết file dưới một shared `generated/` path.
- Dùng static counters/caches và classloader chung.
- Tạo cùng class/resource tên không phù hợp.
- Ghi chung `META-INF/services` output ngoài module.
- Đọc/ghi file cấu hình global.

Trong compiler context, `Filer` thường quản lý generated sources/resources của compilation hiện tại. Processor **không nên tùy tiện ghi outside configured output**. Nếu cần resource chung, thiết kế aggregation rõ ở module riêng.

Không nên “chữa” bằng cách cấm `-T` vĩnh viễn nếu có thể tách generator per module và kiểm behavior. Nhưng nếu processor/library không bảo đảm concurrent execution, quay về sequential build cho đến khi cập nhật đủ an toàn.

## 22. Aggregator goals, reports và thời điểm chạy

Một goal tổng hợp test coverage/checkstyle/reports từ các modules cần dữ liệu đầy đủ. Trong parallel Reactor, các modules có thể hoàn thành ở thời điểm khác nhau.

Sai lầm:

~~~text
alpha: generate partial report ----+
                                    +--> aggregator reads shared file too early
beta:  generate partial report -----+
~~~

Nếu aggregator goal đọc `target/site/aggregate.xml` khi beta chưa tạo report, kết quả thiếu module nhưng có thể vẫn được ghi thành công.

Các lựa chọn:
- Chạy per-module checks trong Reactor song song.
- Sau khi build tất cả modules pass, chạy **một aggregation command/job** từ root ở phase phù hợp.
- Thiết kế aggregator goal thực sự dùng đúng Maven project set/dependency graph và không dựa vào thứ tự log.
- Không để một goal vừa tổng hợp báo cáo vừa xóa/ghi outputs per-module của goal khác.
- Dùng module-specific report paths rồi merge với xác minh đầy đủ.

**`aggregator=true` không tự bảo đảm barrier sau tất cả module outputs.** Phải xác minh semantics/version của plugin và binding thực tế.

## 23. Cảnh báo `not marked as thread-safe` nên được xử lý thế nào?

Nếu Maven log chỉ rõ một plugin goal không có metadata `threadSafe=true`:

1. Ghi lại plugin GAV **và goal thực tế**.
2. Kiểm version plugin/goal documentations và changelog.
3. Kiểm trong plugin JAR `META-INF/maven/plugin.xml`.
4. Xem plugin có dùng static mutable state, singleton, shared paths hoặc unsafe libraries không.
5. Chạy **serial baseline** để xem lỗi có chỉ do parallelism không.
6. Nếu có version mới đã audit, upgrade và chạy lại tests.
7. Nếu plugin in-house, sửa implementation và test concurrency rồi mới đánh dấu true.
8. Nếu không thể sửa, chạy goal đó trong **một sequential stage** hoặc giảm concurrency cho build cần nó.
9. Không coi thiếu cảnh báo là bằng chứng tuyệt đối; một plugin khai báo sai vẫn có thể race.
10. Không coi warning là hard failure nếu Maven tiếp tục và outputs vẫn có, nhưng với release/CI policy có thể chọn fail qua kiểm soát riêng.

Maven 3 parallel build docs ghi rõ những warnings dạng này có tính **cảnh báo**. Tài liệu lịch sử liệt kê nhiều plugin versions cũ từng không an toàn, nhưng **không được áp một bảng plugin cũ cho release mới**: kiểm đúng version bạn thực sự dùng.

## 24. Các cách tạo tuần tự cục bộ mà không tắt toàn bộ CI pipeline

| Điều kiện | Cách tiếp cận |
| --- | --- |
| Một plugin goal không thread-safe và không thể thay | Tách thành một sequential Maven invocation/stage |
| Test cần một DB schema/port chung | Cấp môi trường riêng, hoặc serialize integration tests |
| Aggregation cần toàn bộ reports | Chạy sau phase per-module từ một single-writer job |
| Các modules đã có dependency edge | Để Reactor tự tôn trọng graph, không tự fake order |
| Không chắc plugin có an toàn không | Dùng `mvn clean verify` tuần tự như baseline |
| CI cần tăng tốc nhưng có module nặng | Tối ưu module graph, caching hoặc giảm `-T` sau đo |
| Plugin tự viết dùng global cache | Refactor stateless/per-module cache hoặc synchronization đúng |
| CI nhiều processes share workspace | Dùng workspace isolation hoặc distributed coordination |
| Goal non-cacheable có side effects | Tách khỏi cacheable/parallel pure build nếu cần |

**Không thể chọn một lệnh Maven universal “hãy serialize đúng một arbitrary Mojo trong khi mọi goal khác tự do song song” trên mọi Maven 3 version và plugin.** Khi nghi ngờ, tách stages là biện pháp dễ kiểm chứng nhất. Nếu làm kỹ thuật locking, cần hiểu scope lock và rủi ro deadlock.

### 24.1. Cẩn trọng với `-pl` và `-am`

~~~bash
mvn -B -ntp -pl :alpha -am verify
~~~

`-pl` chọn module, `-am` gồm upstream reactor dependencies như `common`. Đây là cách giảm graph cho một mục tiêu build, **không phải đảm bảo plugin thread-safe**. Nếu chạy thêm `-T 2`, những modules độc lập còn trong selected reactor vẫn có thể chạy đồng thời.

`-amd` chọn dependents, không giống `-am`; dùng sai flags có thể làm thay đổi module set và che race tình cờ.

## 25. CI ví dụ: giữ safety gate trước khi bật `-T`

Ví dụ GitHub Actions cho project `parallel-reactor-lab` ở repo root:

~~~yaml
name: Maven parallel reactor safety

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  serial-baseline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Verify serial build
        run: mvn -B -ntp clean verify

  parallel-verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Verify parallel build
        run: mvn -B -ntp -T 2 clean verify
~~~

Hai jobs có workspaces riêng theo hosted runner model, nên không ghi đè cùng `target` directory. `cache: maven` chủ yếu giảm thời gian download dependencies, **không tạo race-prevention** hay tự bật Maven build-output cache.

Đây là **workflow minh họa** cho Maven 3.9+/JDK17 project. Trong production:
- Pin actions bằng immutable SHAs đã phê duyệt khi supply-chain policy yêu cầu.
- Pin Maven Wrapper/distribution và plugin versions.
- Nếu dùng self-hosted runners, không cho hai jobs share cùng workspace.
- Lưu JUnit reports và checksums theo job, tránh artifact-name collision.
- Không inject release secrets vào untrusted PR jobs.
- Khi mới mở `-T`, giữ serial lane để đối chiếu.
- Nếu project có test suites dùng shared DB/port, isolation/serialized integration stage là bắt buộc.

### 25.1. Không nhầm GitHub job parallelism với Maven `-T`

Trong workflow trên, **hai CI jobs chạy trên runners khác nhau**, còn trong job `parallel-verify`, Maven `-T 2` chạy parallel Reactor threads. Chúng là **hai tầng concurrency**.

Nếu chạy thêm JUnit parallel execution và forkCount lớn, mức concurrency tổng thể còn tăng. Điều này ảnh hưởng CPU/RAM/ports, cần capacity planning.

## 26. Quy trình chẩn đoán lỗi chỉ xảy ra với `-T`

Khi xảy ra lỗi không ổn định:

**Bước 1 — giữ nguyên commit/JDK/Maven/dependency versions.**

~~~bash
mvn -version
java -version
~~~

**Bước 2 — thử serial baseline.**

~~~bash
mvn -B -ntp clean verify
~~~

**Bước 3 — thử parallel có threads cố định nhỏ.**

~~~bash
mvn -B -ntp -T 2 clean verify
~~~

**Bước 4 — phân loại thông báo lỗi:**
- `not marked as thread-safe`: metadata/cảnh báo plugin.
- `FileAlreadyExistsException`, `AccessDeniedException`: path collision/file locking.
- `BindException: Address already in use`: cổng dùng chung.
- `NoSuchFileException`: file bị xóa/di chuyển trong lúc goal khác chạy.
- `ClassNotFoundException`: chưa khai báo reactor dependency hoặc classpath sai.
- `NoClassDefFoundError`: runtime/plugin dependency/classloader hoặc build output cũ.
- Báo cáo sai nội dung nhưng không exception: last-writer-wins/data race.
- Test assertion fail ngẫu nhiên: shared test state, race, flaky timing.
- Timeout/deadlock: locks, DB pool, CPU starvation, external service.

**Bước 5 — tìm project/goal cụ thể.** Đọc Maven log có GAV/module, executionId, plugin goal, phase và các lines liên quan. Logs parallel có thể xen kẽ, nên không giả định các dòng lân cận đến cùng module.

**Bước 6 — kiểm output directory thực tế** và shared resources. `target` của module có khác hay plugin trỏ root/tmp?

**Bước 7 — đối chiếu plugin descriptor và versions.** Không dùng annotations trong source cũ làm bằng chứng.

**Bước 8 — sửa isolation hoặc serialize goal rủi ro**. Không dùng sleep/retry ngẫu nhiên để che race.

**Bước 9 — chạy lại nhiều lần và kiểm artifact contents**. Một lần pass không chứng minh safety.

**Bước 10 — giữ kết quả/limits trong CI** và theo dõi regression khi nâng plugins/JDK.

## 27. Stress test và khả năng tái hiện

Race thường phụ thuộc timing. Một lần `-T 2` pass chưa đủ:

~~~bash
mvn -B -ntp -T 2 clean verify
mvn -B -ntp -T 4 clean verify
mvn -B -ntp -T 1C clean verify
~~~

Lệnh trên là **ba trials riêng**; không nói chúng đảm bảo phát hiện mọi race. Muốn stress lặp lại nhiều lần, dùng script CI đã kiểm error handling, mỗi trial ghi log và exit code, không xóa ngẫu nhiên global cache.

Nếu muốn dùng PowerShell để kiểm 5 lần:

~~~powershell
1..5 | ForEach-Object {
    Write-Output "parallel trial $_"
    mvn -B -ntp -T 2 clean verify
    if ($LASTEXITCODE -ne 0) {
        throw "Parallel trial failed at iteration $_"
    }
}
~~~

Script **chỉ nên chạy trong lab/workspace có quyền**, không trên CI production đang phát hành artifacts. Nó dừng ở lần fail đầu tiên và không coi logs lẫn lộn là kết quả.

Cần so:
- Các JUnit XML tests counts/failures.
- Exact content của per-module report files.
- GAV/project names trong report.
- JAR checksums khi build có reproducible config.
- Không có files ở shared output path không được phép.
- Resource/port cleanup sau mỗi trial.

### 27.1. Dùng `-X` khi nào?

`mvn -X` có thể thêm thông tin execution/goal/plugin, nhưng log rất dài và có thể lộ thông tin nội bộ/credentials. Không tự in secrets hoặc upload full debug log công khai. Bắt đầu với log thông thường và output assertions; chỉ debug chi tiết khi cần và có kênh bảo vệ.

## 28. Thread safety và performance: nhiều threads không luôn nhanh hơn

Một parallel build có thể **chậm hơn** sequential nếu:
- Project graph có quá ít independent modules.
- Test suites sử dụng quá nhiều CPU/RAM/GC cùng lúc.
- Download và filesystem I/O là bottleneck.
- Các tools dùng global locks khiến mọi job xếp hàng.
- Container CI có 2 CPUs nhưng `-T 1C` báo core count cao hơn quota thực tế.
- Database/ports/service capacity không đủ.
- Test JVM forks và Maven Reactor workers nhân mức concurrency quá lớn.
- Một aggregator stage phải chờ tất cả modules, chiếm thời gian cố định.
- Disk antivirus/file-lock behavior trên Windows tăng contention.

Không đưa ra con số speedup mặc định. Đo trên cùng commit và môi trường đã warm dependencies:

~~~bash
mvn -B -ntp clean verify
mvn -B -ntp -T 2 clean verify
~~~

Chạy nhiều trials, lấy median và xem time per module. Không so một lần build tải dependencies lần đầu với một lần warmed build rồi quy toàn bộ khác biệt cho `-T`.

**Số threads tối ưu** phụ thuộc graph, CPU quotas, RAM, tests, I/O và plugin safety. Tăng threads bằng mọi giá không phải mục tiêu của engineering.

## 29. Những điều riêng với Maven 4 và các phiên bản tương lai

Bài tập trọng tâm là Maven 3.9+ và **cơ chế `-T` của Reactor Maven 3**. Maven 4 có thay đổi về project model/root discovery, build engine và plugin APIs; phải kiểm đúng Maven version, Plugin Tools version, descriptor semantics và build plan được dùng.

Không mặc định rằng một pull request/sáng kiến để Maven tự serialize non-thread-safe mojos **đã được phát hành và bật** trong mọi Maven 3/4 version. Các phiên bản Maven 3 thực tế thường warning rồi tiếp tục.

Khi upgrade Maven major:
1. Kiểm `mvn -version`.
2. Kiểm `plugin.xml` và plugin metadata.
3. Chạy serial và `-T` tests với đúng release.
4. Kiểm plugin dependencies/API classloader, forked builds.
5. So output checksums/report contents.
6. Cập nhật CI policy dựa trên **behavior đã verify**, không dựa vào thông tin từ pull request chưa phát hành.

## 30. Bảng lỗi và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý đúng |
| --- | --- | --- |
| `not marked as thread-safe` | Goal chưa có cờ descriptor hoặc version cũ | Kiểm goal metadata/upgrade/audit |
| Không có warning nhưng output vẫn sai | Goal đánh dấu true nhưng implementation race | Audit shared resources và stress tests |
| Report alpha mang nội dung beta | Cùng path hoặc mutable global buffer | Module-specific directory và stateless Mojo |
| `FileAlreadyExistsException` dưới `target` root | Nhiều modules cùng tạo file | Per-module output; atomic write nếu cần |
| `AccessDeniedException` trên Windows | Shared file open/delete giữa goals | Isolate path, close streams, locks đúng |
| `BindException: Address already in use` | Hai test suites cùng port cố định | Port0, dynamic allocation hoặc serialize |
| Maven log xen kẽ khó đọc | Threads chạy song song | Gắn module/goal context vào logs |
| Surefire test fail ngẫu nhiên | Test shared state/DB/schema | @TempDir, isolated fixtures, per-job services |
| `ConcurrentModificationException` | Shared mutable collection không bảo vệ | Immutable data/concurrent collection/lock đúng |
| `NoSuchMethodError` sau build nhanh | Stale classes/plugin libs/dependency mismatch | Clean baseline, dependency tree, versions |
| Plugin version mới vẫn warning | Descriptor goal khác hoặc artifact cũ | Inspect actual plugin JAR |
| Root build pass, `-T` fail module ordering | Thiếu dependency edge hoặc shared generated files | Khai báo dependencies, tách output |
| `-T 1C` làm máy hết RAM | Too many Maven workers/test forks | Hạ `-T`, forkCount, limit CI CPU |
| Maven sequential pass, parallel pass đôi khi | Race không deterministic | Repeat stress test, output checksums |
| Release upload bị trùng | Nhiều module goals gửi cùng artifact/GAV | Single publisher/aggregation, release policy |
| Java `synchronized` không giúp hai CI jobs | Hai Maven processes không share lock object | Workspace isolation, external coordination |
| `-pl` thay modules khiến race biến mất | Thay graph chỉ che xung đột | Xác minh missing upstream/sharing, không kết luận fixed |
| Aggregated report thiếu beta | Đọc trước khi beta hoàn tất | Separate post-Reactor aggregation stage |
| Plugin marked thread-safe nhưng native tool fail | Helper external không reentrant | Per-module process dirs, serialize tool |
| IDE builds khác CLI | IDE compiler/test runner không giống Maven | Test bằng Maven CLI và cùng JDK/POM |
| `mvn -fn` báo success dù có lỗi | Fail-never không đáng tin làm gate | Không dùng `-fn` trong CI required checks |

## 31. Câu hỏi tự kiểm tra

**Câu 1.** `mvn -T 2 clean verify` cho phép gì?

**Đáp:** Maven Reactor có thể thực thi các module độc lập theo dependency graph với tối đa số build threads được chỉ định; không tự chạy cùng một module goals đảo lộn lifecycle.

**Câu 2.** `@Mojo(threadSafe=true)` có cấp Java lock không?

**Đáp:** Không. Nó công bố một claim về an toàn đồng thời cho goal; tác giả phải thực sự thiết kế và test implementation.

**Câu 3.** Goal không có `threadSafe=true` trên Maven 3 có luôn bị chặn không?

**Đáp:** Không. Maven thường đưa ra warning rồi tiếp tục song song; không tự đảm bảo serialization.

**Câu 4.** `aggregator=true` có phải mutex cho toàn Reactor không?

**Đáp:** Không. Nó là metadata về aggregation semantics, không phải khóa toàn cục hoặc barrier sau mọi module outputs.

**Câu 5.** `static final StringBuilder` có thread-safe không?

**Đáp:** Không, vì `final` chỉ giữ reference không đổi; StringBuilder vẫn mutable.

**Câu 6.** Tại sao per-module `project.build.directory` quan trọng?

**Đáp:** Nó tách đường dẫn output của từng Maven project, tránh hai goals cùng ghi một file.

**Câu 7.** Dùng `Files.writeString` có tự atomic không?

**Đáp:** Không. Cần single-writer/path isolation và chiến lược công bố file phù hợp.

**Câu 8.** Maven `-T` có tự bật JUnit parallel mode trong một Surefire execution không?

**Đáp:** Không. Tuy nhiên hai Surefire goals của hai modules có thể chạy cùng lúc.

**Câu 9.** Vì sao test port 8080 có thể fail ở parallel Reactor?

**Đáp:** Hai tests hoặc services ở modules khác nhau có thể tranh cùng một TCP port.

**Câu 10.** `@TempDir` giải quyết vấn đề nào?

**Đáp:** Cung cấp thư mục tạm riêng theo JUnit scope phù hợp, tránh các tests cùng ghi tên file cố định.

**Câu 11.** Java `synchronized` có bảo vệ hai Maven processes chạy trên cùng workspace không?

**Đáp:** Không. Locks trong JVM không đồng bộ được processes khác.

**Câu 12.** Một Mojo không có `static` đã chắc chắn thread-safe chưa?

**Đáp:** Chưa. Nó có thể dùng singleton, shared file, database hoặc native tools không an toàn.

**Câu 13.** Nếu Maven warning trên Plugin A, có thể chỉ sửa version của Plugin B không?

**Đáp:** Không. Cần kiểm đúng plugin/goal descriptor và dependencies thực tế.

**Câu 14.** `-pl :alpha -am` có phải thread-safety flag không?

**Đáp:** Không. Nó chọn reactor projects cần thiết, không bảo vệ shared state.

**Câu 15.** Module alpha và beta cùng dùng common có thể chạy song song khi nào?

**Đáp:** Sau khi upstream common đáp ứng dependency requirements và cả hai independent modules được Reactor scheduler cho chạy, nếu threads còn trống.

**Câu 16.** Tại sao logging output xen kẽ không phải build failure?

**Đáp:** Console logs từ các threads có thể xen kẽ; phải kiểm exceptions, outputs, test results và Maven exit code.

**Câu 17.** Nếu tăng `-T` làm test suite chậm đi thì sao?

**Đáp:** Đo CPU/RAM/I/O, forkCount, external service capacity và giảm threads/giới hạn concurrency phù hợp.

**Câu 18.** Vì sao plugin descriptor quan trọng?

**Đáp:** Maven đọc goal metadata trong `META-INF/maven/plugin.xml` của JAR được sử dụng, không đọc Java source annotation trực tiếp từ repository của developer.

**Câu 19.** Có nên đánh dấu `threadSafe=true` chỉ để xóa warning không?

**Đáp:** Không. Phải audit, thiết kế isolation và test song song trước.

**Câu 20.** Nếu aggregator report đọc thiếu một module, cách sửa có thể là gì?

**Đáp:** Dùng lifecycle/ordering phù hợp hoặc tách aggregation thành bước chạy sau khi tất cả per-module reports hoàn tất.

## 32. Checklist review plugin trước khi bật Reactor parallel builds

1. Xác định version Maven, JDK và plugins chính xác.
2. Vẽ dependency graph và số modules có thể chạy đồng thời.
3. Kiểm `-T` CLI value thực tế trên CI.
4. Không nhầm Reactor parallelism với JUnit parallelism.
5. Ghi plugin GAV, goal name, executionId và lifecycle phase.
6. Kiểm `@Mojo(threadSafe=...)` và plugin.xml trong artifact thật.
7. Không coi threadSafe=true như một mutex.
8. Kiểm tất cả static mutable fields, kể cả library classes.
9. Kiểm injected components/singletons và thread-safety contracts.
10. Tránh global `System.setProperty`, locale/timezone mutations.
11. Mọi output paths mặc định thuộc `${project.build.directory}`.
12. Không dùng một fixed temp file chung cho mọi module.
13. Không ghi/xóa output directory của module khác.
14. Không lạm dụng shared `target/` root.
15. Ghi file với một writer/path, close streams và xử lý IO exceptions.
16. Dùng atomic move khi phù hợp, không giả định mọi filesystem hỗ trợ.
17. Có strategy file lock/transaction nếu shared write thực sự cần.
18. Biết Java mutex không bảo vệ hai Maven processes khác nhau.
19. Dùng workspace riêng cho mỗi CI job.
20. Không cho tests dùng cố định một port/database schema nếu chạy đồng thời.
21. Dùng `@TempDir` và isolated test fixtures.
22. Kiểm native tools/annotation processors có shared global state không.
23. Kiểm plugin thread-safety warning từ Maven, không bỏ qua mù quáng.
24. Không chỉ nâng annotation để xóa warning.
25. Nếu goal rủi ro, đặt trong sequential stage có kiểm soát.
26. Với aggregator, xác nhận toàn bộ reports có sẵn trước khi merge.
27. Không dùng `-fn` hoặc `-DskipTests` để tạo CI xanh giả.
28. So serial baseline với parallel build cùng inputs.
29. Kiểm test counts, failures và per-module outputs.
30. Stress `-T 2`/`-T 4` nhiều trials có fail-fast.
31. Kiểm toolchain/dependency version khi nâng Maven.
32. Pin plugin versions và update có kiểm thử.
33. Đo speedup bằng dữ liệu, tránh khẳng định tất cả dự án nhanh hơn.
34. Cân nhắc RAM/CPU quota/test forks cùng với Maven threads.
35. Release/publish/side-effect goals cần policy serialization/approval riêng.
36. Giữ logs an toàn, không in credentials khi `-X`.
37. Có thể rollback bằng sequential `mvn clean verify`.
38. Không bao giờ coi missing race trong 1 trial là bằng chứng an toàn tuyệt đối.
39. Dùng custom Mojo module-specific output và stateless design khi có thể.
40. Kiểm lại toàn bộ reactor trên CI sạch sau khi thay plugin.

## 33. Tài liệu chính thức và tham khảo chuyên sâu

- [Apache Maven — Parallel Builds in Maven 3](https://cwiki.apache.org/confluence/display/MAVEN/Parallel+builds+in+Maven+3)
- [Apache Maven — Working with Multiple Modules (Reactor)](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Maven CLI `-T`, `-pl`, `-am`](https://maven.apache.org/ref/3-LATEST/maven-embedder/cli.html)
- [Apache Maven — Mojo API Specification: threadSafe](https://maven.apache.org/developers/mojo-api-specification.html)
- [Apache Maven Plugin Tools — `@Mojo` Java Annotation API](https://maven.apache.org/plugin-tools/maven-plugin-annotations/apidocs/org/apache/maven/plugins/annotations/Mojo.html)
- [Apache Maven Plugin Plugin — Using Java Annotations](https://maven.apache.org/plugin-tools/maven-plugin-plugin/examples/using-annotations.html)
- [Apache Maven Plugin Tools — Plugin Descriptors](https://maven.apache.org/plugin-tools/)
- [Apache Maven — Guide to Maven Classloading](https://maven.apache.org/guides/mini/guide-maven-classloading.html)
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven Compiler Plugin 3.16.0](https://maven.apache.org/plugins/maven-compiler-plugin/)
- [Apache Maven Surefire Plugin 3.6.1](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [JUnit 5 User Guide](https://docs.junit.org/5.11.4/user-guide/)
- [GitHub Actions — setup-java](https://github.com/actions/setup-java)

