# Fork kiểm thử, bộ nhớ JVM và giới hạn tài nguyên CI với Maven

## 1. Vấn đề: nhiều fork có thể tăng tốc hoặc làm CI hết bộ nhớ

Một dự án Maven chạy trên máy phát triển có thể hoàn tất hàng nghìn tests, nhưng lại thất bại ngẫu nhiên trên CI dù source code không thay đổi. Những thông báo thường gặp:

~~~text
java.lang.OutOfMemoryError: Java heap space
java.lang.OutOfMemoryError: Metaspace
The forked VM terminated without properly saying goodbye
Process exited with code 137
There was a timeout in the fork
~~~

Các thông báo trên **không có cùng nguyên nhân**. Heap Java có thể thiếu; JVM có thể vượt memory limit của container vì bộ nhớ **ngoài heap**; runner có thể thiếu CPU khiến quá trình bị timeout; test có thể gọi `System.exit` hoặc làm process crash; hoặc hệ điều hành có thể gửi SIGKILL.

Đặc biệt, khi bật Surefire `forkCount=2`, Maven có thể chạy **hai JVM kiểm thử** cùng lúc trong **một module**. Khi dùng thêm Maven `-T 2` trên reactor nhiều module, có thể có **hai modules đang ở phase test**, mỗi module có tới **hai test JVM**. Khi ấy số fork có thể lên tới **4**, chưa kể **Maven JVM**, các processes/toolchains và services của integration tests.

Nhân `-Xmx` với số fork là một phần quan trọng của bài toán, nhưng **-Xmx chỉ là giới hạn heap**, không phải giới hạn tổng RAM của process.

**Mục tiêu của bài:** cấu hình số fork, reuse, JVM heap/metaspace, concurrency và timeout để **tăng throughput có kiểm soát** trong phạm vi CPU/RAM/disk thực của CI; giữ unit/integration tests đáng tin và biết cách đo, điều tra lỗi trước khi tăng tài nguyên.

### Kết quả học tập

Sau bài, bạn có thể:

1. Phân biệt Maven JVM, Surefire forked test JVM, Failsafe JVM và JVM do plugin khác tạo.
2. Giải thích `forkCount`, `reuseForks`, `argLine`, `forkedProcessTimeoutInSeconds`.
3. Hiểu `forkCount=0`, `1`, `2`, `1C` khác nhau và khi nào nên dùng.
4. Phân biệt **fork song song**, Maven reactor parallel `-T` và JUnit Jupiter thread parallelism.
5. Phân biệt heap `-Xms/-Xmx` với metaspace, direct buffers, thread stacks, code cache và native memory.
6. Ước lượng ngân sách memory tổng khi nhiều modules và forks cùng chạy.
7. Cấu hình Maven Surefire Plugin **3.5.4**, Java **17**, JUnit Jupiter **5.11.4** trong POM hoàn chỉnh.
8. Tạo chương trình và ba unit tests chạy được, xem PID/CPU/heap của **test JVM**.
9. Thiết lập Maven JVM bằng `MAVEN_OPTS` mà không nhầm với `argLine` của test fork.
10. Tham khảo workflow GitHub Actions/GitLab CI và các giới hạn ngoài JVM.
11. Phân loại JVM OutOfMemoryError, container OOMKilled, timeout, deadlock và test flakiness.
12. Cân bằng tốc độ với tính cô lập, tránh tests tranh file/port/database hoặc chia sẻ static state.
13. Dùng Surefire/Failsafe reports, GC logs và số đo RSS để quyết định tuning.
14. Xây CI gate không bỏ test, không che exit code và giữ reports khi job fail.

Bài dùng **Maven 3.9.x, Java 17+, Maven Compiler Plugin 3.14.1, Surefire Plugin 3.5.4, JAR Plugin 3.4.2 và JUnit Jupiter 5.11.4**. Version được ghim để tái hiện, không phải cam kết đây luôn là những phiên bản mới nhất. Những con số RAM/timeouts là **giá trị demo**, phải hiệu chỉnh theo workload và runner thật.

---

## 2. Bốn mức đồng thời khác nhau

Hãy hình dung một build như sau:

~~~text
CI runner / container / VM (giới hạn CPU, RAM, disk, time)
  |
  +-- Maven launcher JVM  [MAVEN_OPTS]
  |     |
  |     +-- Module A: maven-surefire-plugin
  |     |       |
  |     |       +-- test JVM A1  [argLine, -Xmx]
  |     |       +-- test JVM A2  [argLine, -Xmx]
  |     |
  |     +-- Module B: maven-surefire-plugin (nếu reactor -T cho chạy song song)
  |             |
  |             +-- test JVM B1  [argLine, -Xmx]
  |             +-- test JVM B2  [argLine, -Xmx]
  |
  +-- CI sidecars: database / browser / Docker / report tools (nếu có)
~~~

### 2.1. Maven JVM là một process riêng

Lệnh:

~~~bash
mvn -B -ntp clean verify
~~~

khởi động JVM để chạy Maven core, build lifecycle và plugins. Chính JVM này có heap, metaspace và native memory riêng.

Cấu hình thông dụng trên Bash:

~~~bash
export MAVEN_OPTS="-Xms128m -Xmx512m"
mvn -B -ntp clean verify
~~~

`MAVEN_OPTS` do launcher Maven dùng để truyền JVM options tới **Maven JVM**. Nó **không phải tham số mặc định đặt -Xmx cho mọi JVM do Surefire fork**.

### 2.2. Surefire forked test JVM

Với:

~~~xml
<forkCount>1</forkCount>
<reuseForks>true</reuseForks>
<argLine>-Xms64m -Xmx256m</argLine>
~~~

Surefire thực thi tests trong **một JVM con** với heap tối đa được yêu cầu là 256 MiB. JVM chạy Maven vẫn có ngân sách riêng.

Surefire truyền options qua `argLine` **chỉ khi thực sự fork JVM**.

### 2.3. Maven reactor -T

~~~bash
mvn -T 2 clean verify
~~~

cho Maven core xây dựng **các modules độc lập** song song khi graph cho phép. Nó **không** đồng nghĩa “chạy hai JUnit methods cùng lúc”, cũng không tự tăng `forkCount` trong một module.

### 2.4. Parallel threads bên trong test JVM

JUnit Jupiter có cơ chế parallel execution riêng. Nhiều test methods có thể chạy trong **nhiều threads của cùng một forked JVM**, chia sẻ heap, static fields và resource handles.

Vậy:

- `forkCount`: tối đa **bao nhiêu process JVM** chạy tests đồng thời mỗi module.
- `-T`: tối đa **bao nhiêu Maven reactor module-build tasks** chạy đồng thời.
- JUnit parallelism: **bao nhiêu test tasks/threads** bên trong một JVM.

Không gộp ba trục điều khiển này làm một.

---

## 3. Surefire forkCount và reuseForks

Theo tài liệu Maven Surefire 3.5.4:

| Thiết lập | Hành vi | Khi dùng |
| --- | --- | --- |
| `forkCount=0` | Không fork; tests chạy trong JVM chạy Maven | Chẩn đoán đặc biệt; không mặc định tốt cho CI song song |
| `forkCount=1` | Tối đa một forked JVM tại một thời điểm cho module | Baseline an toàn |
| `forkCount=2` | Tối đa hai JVM kiểm thử đồng thời cho module | Khi test suite đủ lớn và RAM cho phép |
| `forkCount=1C` | Fork count tỷ lệ với số processors JVM nhìn thấy | Cần đo CPU/RAM và giới hạn container |
| `forkCount=0.5C` | Theo hệ số CPU; plugin tính mức fork thực | Có thể hữu ích trên runner nhiều CPU |
| `reuseForks=true` | Tái sử dụng các JVM để chạy nhiều test classes | Mặc định; giảm khởi tạo JVM |
| `reuseForks=false` | Tạo JVM mới cho từng test class (tối đa forkCount đồng thời) | Khi cần cô lập static state/resource leaks |

**Giá trị mặc định**: `forkCount=1` và `reuseForks=true`. Khi số test classes ít hơn số fork mong muốn, plugin không cần tạo đủ JVM đến mức cấu hình tối đa.

### 3.1. forkCount=N là tối đa, không phải số luôn xuất hiện

Nếu module chỉ có hai test classes, đặt `forkCount=8` không có nghĩa Surefire sẽ tạo tám JVM chạy việc có ích. Fork count là **giới hạn concurrency**, còn số test classes, scheduling và plugin behavior quyết định số process thực tế.

### 3.2. Giá trị C phụ thuộc CPU khả dụng/được báo cáo

~~~xml
<forkCount>1C</forkCount>
~~~

được Surefire nhân theo số **available processors/cores** JVM thấy. Trên container/runner, con số hiệu dụng có thể bị ảnh hưởng bởi cgroup/container CPU quota, JVM version và flags như `-XX:ActiveProcessorCount`.

**Công thức nguy hiểm:** 1C không tự tính RAM. Một runner 8 CPUs nhưng chỉ 4 GiB RAM có thể không chịu nổi 8 fork mỗi fork `-Xmx1g`.

### 3.3. Vì sao reuseForks=true thường tốt hơn

Giả sử 200 test classes:

~~~text
forkCount=1, reuseForks=true:
  khởi động 1 test JVM rồi lần lượt chạy classes

forkCount=1, reuseForks=false:
  từng class có JVM mới, khởi động/teardown lặp lại
~~~

Mode thứ hai tốn thời gian JVM startup và classloading hơn, nhưng có thể giúp phát hiện state leakage; nó **không tự chữa** test tranh database, file hay external service, và không làm tests đúng nếu code phụ thuộc thứ tự.

### 3.4. Forked tests khác với threads trong một process

Nhiều threads trong cùng JVM chia sẻ:

- Java heap và static fields.
- System properties.
- Default locale/timezone khi thay global state.
- Connections/clients/resources do code test dùng chung.

Các fork JVM khác nhau tách heap/static fields, nhưng vẫn có thể tranh:

- Một port TCP hardcode.
- File/directory cùng đường dẫn.
- Database schema.
- Docker containers hoặc test server.
- CPU/RAM/disk của CI runner.

**Fork chỉ tách process memory, không tự tạo môi trường tài nguyên độc lập.**

---

## 4. Maven -T nhân mức đồng thời như thế nào?

Một reactor gồm:

~~~text
parent (packaging=pom)
  |
  +-- api-lib
  +-- worker-lib
  +-- gateway-lib
  +-- cli-app (depends on api-lib)
~~~

Nếu build command:

~~~bash
mvn -T 2 clean verify
~~~

Maven có thể build **tối đa hai modules phù hợp graph** cùng lúc. Nếu trong mỗi module Surefire có:

~~~xml
<forkCount>2</forkCount>
~~~

thì ở một số thời điểm có thể có:

~~~text
2 concurrent module builds
    × 2 forked test JVMs per module
    = up to 4 concurrent test JVMs
~~~

Đây là **upper bound minh họa**, không phải phép tính chính xác số fork từng giây. Nếu modules có dependencies buộc chạy nối tiếp, hoặc không có đủ test classes, số fork thực nhỏ hơn.

Nếu thêm JUnit parallelism trong mỗi fork, ví dụ hai worker threads:

~~~text
4 test JVMs × 2 active JUnit test threads ≈ 8 concurrent test tasks
~~~

Đây vẫn **không** là tám CPUs được bảo đảm. CPU cores vật lý/quota có thể chỉ là hai, dẫn đến context switching, GC cạnh tranh và tăng thời gian chạy.

### 4.1. Khi nào -T giúp?

`-T` có ích khi reactor có modules **không phụ thuộc nhau**, build code thực sự parallelizable và CPU/RAM/I/O đáp ứng. Trong reactor tuyến tính toàn dependencies, tăng `-T` có thể không cải thiện throughput.

### 4.2. Khi nào không nên tăng đồng thời?

- Integration tests khởi động nhiều application contexts.
- Spring Boot/Testcontainers với database, browser, Docker daemon hoặc sidecars.
- Large in-memory fixtures, mocks hoặc code generation.
- Runner RAM nhỏ, CPU bị quota.
- Test classes tranh port/file/static state.
- Build không ổn định hoặc có lỗi chưa được hiểu.

**Chiến lược baseline:** trước hết `-T 1` + `forkCount=1` + JUnit chạy tuần tự. Chỉ tăng từng trục sau khi đã đo.

---

## 5. Heap Java không phải tổng bộ nhớ của JVM

Các thành phần RAM có thể gồm:

~~~text
Một JVM process:
  Java heap                  (-Xmx)
  Metaspace/class metadata   (native, -XX:MaxMetaspaceSize)
  Code cache/JIT
  Thread stacks              (-Xss × threads, xấp xỉ)
  Direct/off-heap buffers
  Garbage collector native structures
  JNI/native libraries
  JVM launcher + shared mappings + OS resources
~~~

`-Xmx256m` nghĩa là **giới hạn heap Java**, không phải process luôn dùng đúng 256 MiB và càng không phải total RSS cap 256 MiB.

### 5.1. -Xms

~~~text
-Xms64m
~~~

đặt initial Java heap theo cơ chế JVM. Đặt `-Xms` quá lớn có thể tăng mức cam kết/bộ nhớ thực tế và giảm linh hoạt trên runner nhỏ, tùy JVM/OS. Không tự đặt `-Xms=-Xmx` cho mọi CI suite chỉ vì muốn “ổn định”.

### 5.2. -Xmx

~~~text
-Xmx256m
~~~

đặt maximum heap khoảng 256 MiB cho process đó. Nếu test cần nhiều objects sống hơn heap cho phép, có thể thấy:

~~~text
java.lang.OutOfMemoryError: Java heap space
~~~

Nhưng một test JVM có thể bị container kill vì **tổng RSS** trước khi Java báo Java heap space.

### 5.3. MaxMetaspaceSize

~~~text
-XX:MaxMetaspaceSize=128m
~~~

giới hạn một vùng metadata lớp. Điều này giúp có một mức kiểm soát, nhưng có thể gây `OutOfMemoryError: Metaspace` khi framework load rất nhiều classes. Không coi con số 128 MiB là lựa chọn mặc định cho mọi Spring/test workload.

### 5.4. Direct/off-heap buffers

NIO/Netty/native libraries có thể dùng direct buffers hoặc native allocations ngoài heap. Nếu chỉ tăng `-Xmx` mà job đã thiếu tổng RAM, hệ thống có thể càng dễ kill process. Nên đo **RSS/native usage** chứ không chỉ Java heap usage.

### 5.5. Thread stacks

Một JVM có hàng trăm threads có thể dùng nhiều bộ nhớ cho thread stacks và runtime overhead. Tham số `-Xss` có thể ảnh hưởng stack per thread nhưng giảm quá thấp có thể gây `StackOverflowError`. Đừng dùng `-Xss` như chữa cháy đầu tiên khi có lỗi fork.

### 5.6. Container-awareness của Java 17

JDK hiện đại thường xem giới hạn CPU/RAM của container khi tính ergonomics, nhưng kết quả còn phụ thuộc JVM vendor/version, cgroup và flags cụ thể. Cần xác nhận bằng logs hoặc `Runtime.getRuntime().maxMemory()` trong **forked test JVM**, không đoán từ RAM của host.

Khi dùng:

~~~text
-XX:MaxRAMPercentage=60
~~~

một JVM có thể lấy phần trăm bộ nhớ mà nó nhìn thấy để đặt heap khi **không có -Xmx áp đặt trực tiếp**. Nếu **bốn JVM fork độc lập** đều tính 60% của cùng container RAM, tổng khả năng dùng heap có thể vượt xa container limit. Phần trăm **không** được tự chia cho số fork!

---

## 6. Tính ngân sách bộ nhớ tổng ở CI

Một mô hình ước lượng:

~~~text
M_total_needed ≈
    M_Maven_JVM
  + SUM(each active test JVM heap + native overhead)
  + M_compiler/build/plugin processes
  + M_services/containers
  + M_OS/page cache/buffer
  + safety_margin
~~~

Con số là **ước lượng để ra quyết định**. Không phải công thức đo RSS chính xác. Một số phần có thể overlap, memory mapping dùng chung, heap chưa sử dụng hết; cần đo RSS/peak thực tế của toàn container để hiệu chỉnh.

### 6.1. Ví dụ giả định runner giới hạn 4 GiB

Giả sử:

- Runner/container thực được cấp **4.096 MiB**.
- Maven JVM `-Xmx512m`.
- Build reactor có `-T 2`.
- Mỗi module có `forkCount=2`.
- Mỗi fork có `-Xmx384m`.
- Giả định native overhead mỗi test JVM khoảng **200 MiB** trong workload này.
- Maven JVM/native/compiler overhead khoảng **700 MiB** tính gộp cho phần Maven/build.
- OS/cache/services và khoản dự phòng tối thiểu khoảng **700 MiB**.

Khi hai modules test cùng lúc:

~~~text
Số test JVM tối đa:           2 modules × 2 forks = 4
Heap tối đa của test forks:   4 × 384 MiB = 1.536 MiB
Native overhead ước tính:     4 × 200 MiB =   800 MiB
Maven/build ước tính:                              700 MiB
OS/services + dự phòng:                            700 MiB
-----------------------------------------------------------
Tổng ước tính:                                   3.736 MiB
Giới hạn giả định:                               4.096 MiB
Biên còn lại:                                      360 MiB
~~~

Biên còn lại ~360 MiB khá mỏng và 200 MiB/fork chỉ là giả định, **không phải số liệu đo**. Database container, JVM khác hoặc report tool có thể làm vượt giới hạn.

Giảm `forkCount` từ 2 xuống 1 trong hai modules hạ mức heap test tối đa từ 1.536 MiB còn 768 MiB. Như vậy có thể ổn định hơn dù thời gian chạy dài hơn.

### 6.2. Dùng giới hạn thực, không đoán từ tên runner

`ubuntu-latest` là **runner label**, không phải hợp đồng “máy này có 16 GB RAM”. Thông số CPU/RAM GitHub-hosted runners phụ thuộc loại repo, plan, image và runner size; GitLab/Jenkins còn tùy executor/container limit. Hãy xem tài liệu provider cho account/project cụ thể và kiểm tra container cgroup khi cần.

Không đưa một con số RAM chung cố định cho mọi CI provider.

### 6.3. Nếu runner chỉ có 2 CPUs

Dù memory đủ, `forkCount=4` + JUnit parallel có thể làm CPU oversubscription nghiêm trọng. Test throughput đôi khi **giảm** do contention và GC. Tối ưu theo **wall-clock duration và peak RSS**, không chỉ theo số test JVM.

---

## 7. POM runnable: kiểm soát fork và memory cho Java 17

Dự án mẫu có ba file:

~~~text
maven-fork-budget-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/performance/App.java
    └── test/java/vn/example/performance/
        ├── AppTest.java
        └── ForkBudgetTest.java
~~~

Thực tế là **4 file**: một POM, một class main và hai class tests.

### 7.1. pom.xml hoàn chỉnh

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>maven-fork-budget-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>

        <test.forkCount>1</test.forkCount>
        <test.reuseForks>true</test.reuseForks>
        <test.jvm.args>-Xms64m -Xmx256m -XX:MaxMetaspaceSize=128m</test.jvm.args>
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
                <version>3.14.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
                <configuration>
                    <forkCount>${test.forkCount}</forkCount>
                    <reuseForks>${test.reuseForks}</reuseForks>
                    <argLine>${test.jvm.args}</argLine>
                    <forkedProcessTimeoutInSeconds>180</forkedProcessTimeoutInSeconds>
                    <forkedProcessExitTimeoutInSeconds>30</forkedProcessExitTimeoutInSeconds>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.performance.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

#### Vì sao thiết kế như vậy?

- `test.forkCount=1`: một test JVM fork tại một thời điểm là baseline.
- `test.reuseForks=true`: tái sử dụng process giữa test classes, giảm startup overhead.
- `test.jvm.args`: property riêng cho command line của test JVM.
- `-Xms64m -Xmx256m`: heap ban đầu và tối đa, chỉ dành cho các fork Surefire.
- `-XX:MaxMetaspaceSize=128m`: limit metaspace **minh họa**, cần tăng/loại nếu framework nhiều classes.
- `forkedProcessTimeoutInSeconds=180`: giới hạn **vòng đời fork process** theo Surefire, không phải timeout của từng @Test.
- `forkedProcessExitTimeoutInSeconds=30`: khoảng chờ lúc fork thoát **sau khi tests kết thúc**, dùng để xử lý tiến trình còn non-daemon threads.
- `failIfNoTests=true`: tránh báo build xanh nếu suite đáng lẽ có tests nhưng Surefire không tìm thấy test nào.
- POM **không kích hoạt JUnit Jupiter parallel execution**; do đó tests mặc định chạy tuần tự bên trong mỗi process.

Hai properties riêng `test.forkCount` và `test.jvm.args` cho phép thí nghiệm CLI mà không sửa POM. Nếu hardcode `<argLine>-Xmx256m</argLine>` và chỉ đổi `-Dtest.jvm.args` trên CLI, không có bảo đảm plugin nhận giá trị mới — cần interpolation như POM đã thiết kế.

### 7.2. App.java: chương trình chạy độc lập

File `src/main/java/vn/example/performance/App.java`:

~~~java
package vn.example.performance;

public final class App {
    private App() {
    }

    public static int multiply(int a, int b) {
        return Math.multiplyExact(a, b);
    }

    public static void main(String[] args) {
        System.out.println("FORK DEMO: " + multiply(6, 7));
    }
}
~~~

Sử dụng Java standard library, không cần dependency runtime bên ngoài.

### 7.3. AppTest.java: hai unit tests

File `src/test/java/vn/example/performance/AppTest.java`:

~~~java
package vn.example.performance;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void multiplyReturnsFortyTwo() {
        assertEquals(42, App.multiply(6, 7));
    }

    @Test
    void overflowIsReported() {
        assertThrows(
                ArithmeticException.class,
                () -> App.multiply(Integer.MAX_VALUE, 2)
        );
    }
}
~~~

Hai phương thức này deterministic, không giữ static shared state và không chiếm nhiều RAM.

### 7.4. ForkBudgetTest.java: đo JVM đang chạy tests

File `src/test/java/vn/example/performance/ForkBudgetTest.java`:

~~~java
package vn.example.performance;

import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class ForkBudgetTest {
    @Test
    void reportsCurrentTestProcess() {
        long pid = ProcessHandle.current().pid();
        Runtime runtime = Runtime.getRuntime();
        long heapMaxMiB = runtime.maxMemory() / (1024L * 1024L);
        int processors = runtime.availableProcessors();

        assertTrue(pid > 0);
        assertTrue(heapMaxMiB > 0);
        assertTrue(processors >= 1);

        System.out.printf(
                "TEST JVM pid=%d heapMaxMiB=%d processors=%d%n",
                pid,
                heapMaxMiB,
                processors
        );
    }
}
~~~

Lệnh in ra **PID, heapMaxMiB và processors của process thực thi unit test**. Các giá trị **phụ thuộc môi trường**; không được bịa ra một PID hoặc CPU count cố định. Khi `forkCount=0`, test này vẫn chạy được nhưng sẽ đo **Maven JVM** thay vì process fork; điều đó là một thí nghiệm hữu ích.

**Tổng số tests:** 2 trong `AppTest` + 1 trong `ForkBudgetTest` = **3 tests**.

### 7.5. Build và chạy

Từ root:

~~~bash
mvn -version
java -version
mvn -B -ntp clean verify
~~~

Khi JDK17+ và dependency/plugin resolution phù hợp, kỳ vọng:

~~~text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Dòng “Tests run: 3” có thể là **số tổng hợp** theo các test classes/reports; Surefire logs thường hiển thị từng class và summary. Không coi hai dòng này là bản sao đầy đủ log thực.

Trong logs/report của `ForkBudgetTest`, có thể thấy dòng dạng:

~~~text
TEST JVM pid=<PID_THỰC> heapMaxMiB=<GIÁ_TRỊ_THỰC> processors=<GIÁ_TRỊ_THỰC>
~~~

Đây là **mẫu để nhận diện**, không phải stdout literal chứa chuỗi dấu ngoặc nhọn. Giá trị heap max với `-Xmx256m` thường xấp xỉ 256 MiB nhưng có thể có chênh lệch nhỏ do JVM ergonomics và cách quy đổi.

Chạy ứng dụng:

~~~bash
java -jar target/maven-fork-budget-demo-1.0.0.jar
~~~

Stdout **chính xác của App.main**:

~~~text
FORK DEMO: 42
~~~

Đây là chương trình Java chạy sau khi build, không phải output tự sinh từ `mvn verify`.

---

## 8. Thí nghiệm thay đổi forkCount và reuseForks

### 8.1. Baseline: một fork reusable

~~~bash
mvn -B -ntp "-Dtest.forkCount=1" "-Dtest.reuseForks=true" clean verify
~~~

Thực thi 3 unit tests. Với cấu hình mặc định, các test classes có thể được xử lý trong một JVM fork. Trong reports, xem PID do `ForkBudgetTest` in; không giả định một PID cố định.

### 8.2. Tối đa hai forks trong module

~~~bash
mvn -B -ntp "-Dtest.forkCount=2" "-Dtest.reuseForks=true" clean verify
~~~

Plugin được phép có tối đa hai JVM đồng thời, nhưng demo chỉ có **hai test classes**, rất nhỏ. Đừng lấy chênh lệch thời gian của demo làm bằng chứng rằng 2 forks chắc chắn nhanh hơn trên ứng dụng lớn. Phải đo với test suite thực.

### 8.3. Tạo JVM mới theo test class

~~~bash
mvn -B -ntp "-Dtest.forkCount=1" "-Dtest.reuseForks=false" clean verify
~~~

Chế độ này tạo process mới cho từng test class, giúp giảm rò rỉ static state giữa classes nhưng tốn startup. Nó không tách từng **test method** thành JVM riêng; hai methods trong `AppTest` vẫn thuộc một class.

### 8.4. Không fork: chỉ để chẩn đoán

~~~bash
mvn -B -ntp "-Dtest.forkCount=0" clean test
~~~

Khi `forkCount=0`, Surefire chạy trong Maven JVM; `argLine` **không có tác dụng** với JVM test riêng vì không có fork. Vì vậy số `heapMaxMiB` có thể khác với `-Xmx256m` cấu hình trong POM.

**Không dùng forkCount=0 như cách mặc định tránh lỗi OutOfMemoryError.** Bạn chỉ chuyển workload vào Maven JVM và có thêm rủi ro chia sẻ system properties/classloaders với Maven. Surefire docs lưu ý kết hợp no-fork với parallel Maven reactor `-T` có nguy cơ race conditions trên global system properties.

### 8.5. forkCount theo CPU: 1C

~~~bash
mvn -B -ntp "-Dtest.forkCount=1C" clean verify
~~~

Trên runner có `availableProcessors()=4` theo JVM, giới hạn có thể tương ứng bốn forks cho **module**. Demo chỉ có hai classes nên không cần bốn JVM. Trong CI memory-constrained, không dùng `1C` mà chưa kiểm tổng heap/native overhead của các fork.

---

## 9. Đổi heap test JVM từ command line

Vì POM dùng `${test.jvm.args}`:

~~~bash
mvn -B -ntp \
  "-Dtest.forkCount=1" \
  "-Dtest.jvm.args=-Xms64m -Xmx384m -XX:MaxMetaspaceSize=192m" \
  clean verify
~~~

Đây là cú pháp **Bash/Linux/macOS** với dấu `\` nối dòng. Trên PowerShell/CMD, viết thành một dòng:

~~~text
mvn -B -ntp "-Dtest.forkCount=1" "-Dtest.jvm.args=-Xms64m -Xmx384m -XX:MaxMetaspaceSize=192m" clean verify
~~~

Truyền cả chuỗi Java options trong một đối số `-Dtest.jvm.args=...` cho Maven; Surefire tách JVM options khi tạo command fork.

### 9.1. Đổi Maven heap là câu chuyện khác

Bash:

~~~bash
export MAVEN_OPTS="-Xms128m -Xmx512m"
mvn -B -ntp clean verify
~~~

PowerShell:

~~~powershell
$env:MAVEN_OPTS = "-Xms128m -Xmx512m"
mvn -B -ntp clean verify
$code = $LASTEXITCODE
Write-Output "maven_exit=$code"
~~~

MAVEN_OPTS tác động tới JVM chạy Maven. Surefire fork vẫn dùng `test.jvm.args` theo POM, trừ khi những JVM options khác được thừa kế từ environment theo cơ chế riêng.

### 9.2. JAVA_TOOL_OPTIONS khác MAVEN_OPTS

Biến `JAVA_TOOL_OPTIONS` được Java toolchain/JVM startup hỗ trợ trong nhiều môi trường, có thể được áp dụng cho **cả Maven JVM lẫn các JVM con** nếu environment được kế thừa.

Ví dụ:

~~~bash
export JAVA_TOOL_OPTIONS="-XX:ActiveProcessorCount=2"
mvn -B -ntp clean verify
~~~

Điều này có thể làm `availableProcessors()` mà Java báo bị giới hạn tới 2 trong các processes chịu ảnh hưởng. Nhưng nó **không** tạo giới hạn CPU cgroup thực, và không làm CI runner được cấp thêm/giảm CPU tài nguyên ở hạ tầng. Với kiểm soát fork rõ ràng, ưu tiên cấu hình explicit Surefire `argLine`, Maven launcher và runner limits thay vì dựa ngầm vào biến áp dụng cho tất cả processes.

### 9.3. Khi có JaCoCo hoặc Java agents

Một plugin như JaCoCo `prepare-agent` có thể thiết lập Maven property `argLine` để thêm `-javaagent`. Nếu bạn ghi cứng một `<argLine>` mới, có nguy cơ **đè mất Java agent**, khiến báo cáo coverage rỗng.

Surefire hỗ trợ cú pháp **late property evaluation**:

~~~xml
<argLine>@{argLine} ${test.jvm.args}</argLine>
~~~

Đây là **snippet tích hợp với JaCoCo**, chưa có trong POM runnable. Khi sử dụng, phải bảo đảm property `argLine` được khởi tạo hợp lệ (ví dụ khai property rỗng trong POM) hoặc được plugin khác thiết lập trước khi Surefire chạy, nếu không literal `@{argLine}` có thể lọt vào Java command.

**Đừng thêm snippet này vào POM demo nguyên trạng rồi mong JaCoCo tự xuất hiện.** Bài không cấu hình JaCoCo, nên POM runnable dùng chỉ `${test.jvm.args}` là đủ.

---

## 10. Thực sự có những mức parallelism nào trong JUnit 5?

JUnit Jupiter mặc định **không bật** parallel execution cho mọi test methods. Tăng Surefire `forkCount` cho nhiều process là một chuyện; bật parallel execution trong test engine là chuyện khác.

Khi thật sự muốn JUnit 5 chạy methods đồng thời, có thể tạo file **bổ sung**:

~~~text
src/test/resources/junit-platform.properties
~~~

với nội dung:

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=2
~~~

**File này KHÔNG thuộc bốn file bắt buộc của demo.** Đây là thí nghiệm mở rộng, chỉ nên bật nếu test fixtures/các resource đã thread-safe.

### 10.1. Forks vs threads

| Kiểu | Cô lập heap/static | Khởi động JVM mới? | Rủi ro shared resource |
| --- | --- | --- | --- |
| Surefire fork mới | Cách ly process memory | Có | Vẫn tranh port/file/DB |
| Reused Surefire fork | Giữa classes có thể chia state trong process | Không mỗi class | Static state/leaks |
| JUnit parallel methods | Chia sẻ JVM/heap/static | Không | Race conditions trong code |
| Maven -T | Chạy modules trong reactor song song | Không nhất thiết | Build/test output và external resources |

### 10.2. Không bật ba trục cùng lúc

Một cấu hình:

~~~text
Maven -T 4
Surefire forkCount=2
JUnit fixed parallelism=4
~~~

có thể cho nhiều test tasks đồng thời hơn CPU/RAM thực sự. Giảm rủi ro bằng cách baseline từng trục, đo thời gian và peak resources, sau đó tăng **một biến mỗi lượt**.

### 10.3. Tests dùng static state

Các tests có thể sửa:

~~~java
System.setProperty("app.mode", "test");
java.util.Locale.setDefault(java.util.Locale.US);
~~~

trong cùng JVM. Nếu chạy song song, test khác có thể đọc global state không mong muốn. Dùng per-test dependency injection, resource locking, JUnit isolation annotations hoặc sequential execution theo nhu cầu. ForkCount không chữa được việc hai forks cùng tranh một service bên ngoài.

---

## 11. Quản lý tài nguyên shared giữa các forks

Có các tài nguyên **không tự cách ly** khi tách process:

- TCP port cố định như `localhost:8080`.
- File `target/test-output/result.txt` do nhiều forks cùng ghi.
- Database schema như `test_schema`.
- Redis queue/key prefix.
- Selenium/browser process và file download directory.
- Mock server static endpoints.
- Docker daemon/Testcontainers; nhiều tests có thể tạo nhiều containers cùng lúc.

### 11.1. Dùng placeholder surefire.forkNumber

Surefire hỗ trợ `${surefire.forkNumber}` trong một số cấu hình như `argLine` và `systemPropertyVariables`. Ví dụ:

~~~xml
<systemPropertyVariables>
    <test.schema>test_schema_${surefire.forkNumber}</test.schema>
</systemPropertyVariables>
~~~

Đây là **snippet minh họa**, không nằm trong POM runnable; nó truyền một schema name riêng cho fork nếu các tests/DB setup thực sự đọc property này.

Khi kết hợp Maven `-T` và forkCount, Surefire chọn numbering đủ để tránh nhiều forks dùng cùng number trong **phạm vi Maven session** theo tài liệu plugin. Không dùng numbering này làm **định danh toàn cục** qua các CI jobs độc lập: ở mỗi invocation khác nhau nó có thể bắt đầu lại.

### 11.2. Port theo fork number

Có thể sử dụng số fork để xây port hoặc directory, nhưng phải kiểm tra port chưa bị chiếm và xử lý tranh chấp với các processes khác trên cùng runner. Chỉ cộng port base với fork number mà không có reservation không phải bảo đảm tránh mọi collision.

### 11.3. Database/service isolation

Mỗi fork hoặc test suite có thể dùng một namespace/schema riêng, fixture cleanup riêng và giới hạn số connection. Nếu test gắn với external service đắt/khó nhân bản, chạy tuần tự hoặc giới hạn pool có thể cho throughput tốt hơn việc mở thật nhiều JVMs.

---

## 12. Timeout của fork, timeout của test và timeout của CI khác nhau

### 12.1. Surefire forkedProcessTimeoutInSeconds

~~~xml
<forkedProcessTimeoutInSeconds>180</forkedProcessTimeoutInSeconds>
~~~

Tham số Surefire này dùng để **kill forked test process sau thời gian giới hạn** khi quá trình chạy lâu. Giá trị `0` nghĩa là chờ không giới hạn (mặc định thường là 0), không phù hợp nếu bạn muốn mọi CI test hang đều được phát hiện sớm.

Đây **không phải** timeout riêng cho mỗi method: một class/test dài hoặc nhiều tests tuần tự trong fork có thể tiêu tốn phần đáng kể của giới hạn.

### 12.2. forkedProcessExitTimeoutInSeconds

~~~xml
<forkedProcessExitTimeoutInSeconds>30</forkedProcessExitTimeoutInSeconds>
~~~

Đây là thời gian chờ JVM con **thoát sau khi tests hoàn tất**. Nếu tests tạo non-daemon threads mà không shutdown, process có thể treo lúc exit; tham số này giúp giải phóng thay vì chờ vô hạn. Nó không thay timeout ở lúc test logic đang chạy.

### 12.3. JUnit @Timeout

Ví dụ method timeout (snippet):

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class NetworkTimeoutTest {
    @Test
    @Timeout(5)
    void boundedOperation() {
        // Phép thử phải có logic phù hợp và cleanup resources.
    }
}
~~~

Đây là đoạn minh họa, **không phải test bổ sung bắt buộc của demo**. JUnit `@Timeout(5)` mặc định là giây; nó giúp giới hạn một test. Với thao tác không interruptible/native blocking, timeout vẫn cần design cleanup kỹ.

### 12.4. CI job timeout

GitHub Actions:

~~~yaml
jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 20
~~~

Đây là **snippet job header**. Job timeout là một lớp bảo vệ bao ngoài toàn bộ checkout, setup, dependency downloads, compile và tests, chứ không chỉ forked test JVM.

### 12.5. Đừng dùng timeout để “chữa” thiếu CPU

CPU throttling hoặc quá nhiều forks có thể khiến test bình thường chạy chậm. Chỉ tăng timeout không giải quyết memory pressure hoặc oversubscription. Hãy đo CPU utilization, throttling, GC pauses và queue time; nếu cần, giảm concurrency.

---

## 13. GitHub Actions: ví dụ CI Java 17 có giới hạn rõ

File `.github/workflows/maven-test.yml`:

~~~yaml
name: Maven tests with bounded Surefire forks

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    env:
      MAVEN_OPTS: "-Xms128m -Xmx512m"

    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Set up Java 17
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Inspect toolchain
        run: |
          mvn -version
          java -version

      - name: Run Maven tests
        run: >
          mvn -B -ntp -T 1
          "-Dtest.forkCount=1"
          "-Dtest.reuseForks=true"
          clean verify

      - name: Upload Surefire reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: surefire-reports
          path: target/surefire-reports/
          if-no-files-found: warn
~~~

Cấu hình này cố ý chọn:

- **Một** Maven reactor worker (`-T 1`).
- **Một** Surefire test fork/module (`forkCount=1`).
- Reuse forks bật.
- Maven JVM có `-Xmx512m` thông qua `MAVEN_OPTS`.
- Test JVM có `-Xmx256m` thông qua POM `argLine`.
- Job timeout 20 phút như lớp bảo vệ ngoài.
- Report upload bằng `if: always()` để chẩn đoán cả khi tests fail.

**Lưu ý:** tên `ubuntu-latest` không khẳng định dung lượng RAM cụ thể cho mọi repository/account. RAM/CPU thực do GitHub-hosted runner type quyết định; tài liệu GitHub có bảng phân biệt public/private/plan. Trước khi áp dụng một ngân sách heap lớn hơn, tra đúng runner của tổ chức.

### 13.1. cache=maven không kiểm soát test RAM

`actions/setup-java@v6` với `cache: maven` giúp phục hồi dependencies Maven, giảm tải mạng. **Nó không giới hạn -Xmx**, không kiểm tra memory pressure và không làm tests chạy với ít forks hơn.

### 13.2. Self-hosted runner

Nếu dùng self-hosted runner, chạy nhiều CI jobs trên cùng host có thể khiến **tổng memory của nhiều jobs** vượt host RAM, kể cả mỗi job riêng trông có vẻ an toàn. Cần quản lý đồng thời ở runner scheduler hoặc container limits.

### 13.3. Job timeout không thay OOM diagnosis

Nếu job bị killed vì memory, tăng `timeout-minutes` không sửa nguyên nhân. Kiểm runner logs, OOM events và process peak memory.

---

## 14. GitLab CI: giới hạn cùng Maven, khác hạ tầng

File `.gitlab-ci.yml` minh họa:

~~~yaml
image: maven:3.9-eclipse-temurin-17

stages:
  - test

variables:
  MAVEN_OPTS: "-Xms128m -Xmx512m"

verify:
  stage: test
  script:
    - mvn -version
    - mvn -B -ntp -T 1 "-Dtest.forkCount=1" clean verify
  artifacts:
    when: always
    reports:
      junit: target/surefire-reports/TEST-*.xml
    paths:
      - target/surefire-reports/
~~~

Image tag là ví dụ phổ biến; với yêu cầu reproducibility/security cao, pin image digest được phê duyệt. GitLab runner có thể dùng Docker/Kubernetes/shell executor, nên **memory/cpu limits** có thể đến từ cấu hình runner/namespace/pod/container, **không** được tự suy ra bằng việc chỉ ghi `MAVEN_OPTS` trong YAML.

### 14.1. GitLab resource limits

GitLab job timeout và container memory limit là hai thứ khác nhau. Job timeout giới hạn thời lượng; container limit giới hạn memory khả dụng, thường do executor/Kubernetes resource settings quyết định.

### 14.2. Không dùng artifacts để che test failure

`when: always` cho reports giúp giữ evidence khi fail. Nó **không biến** một job Maven exit nonzero thành job pass. Đừng thêm `allow_failure: true` hoặc `|| true` chỉ để upload reports.

### 14.3. Jenkins và các CI khác

Jenkins pipelines phụ thuộc agent labels, container plugins, Docker/Kubernetes pod templates và resource quotas. Quy tắc giống nhau: **giới hạn JVM trong process** cùng **giới hạn RAM/CPU toàn job ở hạ tầng** và quan sát peak usage.

---

## 15. Giới hạn CI cần đo những gì?

| Tài nguyên | Các chỉ báo quan trọng | Rủi ro |
| --- | --- | --- |
| CPU cores/quota | Active processors, CPU usage/throttling | Forks nhiều nhưng chậm hơn |
| RAM container | Memory limit, RSS/working set, OOM events | SIGKILL/OOMKilled |
| Java heap | Usage, maxMemory, GC pause | Java heap space |
| Metaspace | Class metadata, Metaspace usage | Metaspace OOM |
| Native/direct memory | Buffer allocations, RSS | Container kill dù heap còn |
| Thread count | Threads, stacks, native limits | Unable to create native thread |
| Disk space | `target`, temp, browser logs, dependency cache | No space left on device |
| File descriptors | Open files/sockets | Too many open files |
| CI time | Job deadline, test duration | Deadline exceeded |
| Network/DB | Connection pools, service latency | Timeouts/flaky tests |
| Test isolation | Ports, paths, schemas | Race conditions |

### 15.1. Java Runtime measurements

Trong `ForkBudgetTest` của demo:

~~~java
Runtime.getRuntime().maxMemory()
Runtime.getRuntime().availableProcessors()
ProcessHandle.current().pid()
~~~

giúp biết JVM test thực đang nhìn thấy heap limit/CPU count nào. Nhưng `maxMemory` **không đo peak RSS** hoặc dung lượng còn trống của toàn container.

### 15.2. Kiểm cgroup trên Linux

Trên runner/container Linux dùng **cgroup v2** có thể có:

~~~bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
~~~

`memory.max` có thể là số bytes hoặc `max` khi không giới hạn ở cgroup ấy. Những path này **không có trên mọi Linux runner**, đặc biệt hệ thống dùng cgroup v1/namespaces khác. Không coi lỗi “No such file” là lỗi Maven.

### 15.3. Quan sát process khi tests đang chạy

JDK có thể cung cấp:

~~~bash
jcmd <PID_THỰC> VM.flags
jcmd <PID_THỰC> GC.heap_info
~~~

Trong đó `<PID_THỰC>` phải được thay bằng số PID thật do test log hoặc process listing cung cấp. Đây là **template lệnh**, không copy nguyên dấu ngoặc vào terminal. `jcmd` cần JDK/tool và quyền attach phù hợp; sandbox/container security có thể hạn chế.

Trên Linux:

~~~bash
ps -o pid,rss,cmd -p <PID_THỰC>
~~~

`RSS` là bộ nhớ cư trú của process, không bằng heap usage và có thể có shared memory mappings. Dùng đo theo thời gian/peak toàn job để ra quyết định.

### 15.4. GC logs

Khi điều tra GC pressure, có thể thêm vào **test.jvm.args** (snippet minh họa):

~~~text
-Xlog:gc*:file=target/gc-%p.log:time,level,tags
~~~

`%p` là PID placeholder được JVM unified logging hỗ trợ trong filename. Điều này tránh nhiều forks ghi đè cùng một file; cần bảo đảm `target` tồn tại, runner cho phép ghi và policy bảo vệ logs. GC log giúp thấy pause/collection pressure, nhưng không thay đo native/container memory.

---

## 16. Phân biệt các kiểu OutOfMemoryError và process failure

### 16.1. Java heap space

~~~text
java.lang.OutOfMemoryError: Java heap space
~~~

Thường cho biết Java heap không đáp ứng allocation trong JVM đó. Cần tìm:

- Heap limit `-Xmx` của **đúng test fork**.
- Tests giữ references dài hạn, cache/static state.
- Fixtures tạo dữ liệu lớn hoặc load toàn bộ file vào RAM.
- Leak chỉ xuất hiện khi `reuseForks=true` và nhiều classes cùng process.
- GC behavior và peak live set.

Không tự tăng `-Xmx` quá nhiều khi runner RAM cố định; có thể chuyển thành container OOMKill.

### 16.2. Metaspace

~~~text
java.lang.OutOfMemoryError: Metaspace
~~~

Có thể do load quá nhiều classes/classloaders hoặc metaspace cap quá thấp. Kiểm `-XX:MaxMetaspaceSize`, frameworks/proxies/bytecode generation và classloader retention. Nếu demo cap 128 MiB không đủ cho project thật, phải đo rồi điều chỉnh.

### 16.3. Unable to create native thread

~~~text
java.lang.OutOfMemoryError: unable to create native thread
~~~

Có thể do process/thread limit, native memory, `ulimit`/pid cgroup hoặc quá nhiều threads. Tăng Java heap thường **không giải quyết** và có thể giảm native RAM còn lại.

### 16.4. Process exit 137 / SIGKILL

Trên Linux, exit code **137** thường tương ứng SIGKILL (128+9). Một nguyên nhân phổ biến là kernel/cgroup OOM killer; nhưng người/quản lý job cũng có thể gửi SIGKILL vì timeout hoặc policy. **Không được khẳng định 137 luôn là OOM**. Đọc CI logs, dmesg/memory.events nếu có quyền và xác định ai kill process.

### 16.5. Forked VM terminated without properly saying goodbye

Surefire có thể báo lỗi forked VM mất kết nối:

~~~text
The forked VM terminated without properly saying goodbye
~~~

Các khả năng:

- Fork bị kill vì memory/time/resource.
- Test hoặc thư viện gọi `System.exit`.
- Native crash/JVM fatal error.
- Fork startup không thành công do sai JVM flags, command line hoặc classpath.
- OS/container gửi signal, hết disk/file descriptors.

Đây là **triệu chứng**, không phải chẩn đoán nguyên nhân. Cần xem process exit, dump files, CI logs, Surefire reports, JVM error logs và fork command line.

### 16.6. Timeout không đồng nghĩa OOM

Nếu thấy `forkedProcessTimeoutInSeconds` đạt giới hạn, xem deadlock, network timeout, CPU throttling, GC pauses, resource contention và test setup/teardown. Nếu tăng timeout mà không giải quyết nguyên nhân, flakiness vẫn còn.

---

## 17. Surefire reports và evidence kiểm thử

Sau `mvn clean verify`, xem:

~~~text
target/surefire-reports/
    TEST-vn.example.performance.AppTest.xml
    TEST-vn.example.performance.ForkBudgetTest.xml
    vn.example.performance.AppTest.txt
    vn.example.performance.ForkBudgetTest.txt
~~~

Names của reports có thể khác khi bạn cấu hình reportNameSuffix/provider; danh sách trên là dự kiến của POM mẫu.

Với ví dụ chạy đúng, tổng số tests:

~~~text
AppTest:        2 tests
ForkBudgetTest: 1 test
Total:          3 tests, 0 failures, 0 errors, 0 skipped
~~~

Phân biệt:

- **Surefire XML reports:** số test, duration, failures/errors, system-out khi được ghi.
- **JVM GC logs:** heap pressure/tần suất thu gom rác.
- **CI container metrics:** peak RSS/memory usage, throttling, OOM events.
- **Maven logs:** phase/plugin, test JVM fork startup/errors.
- **Application logs:** resource setup/teardown, external services.

Một dòng `BUILD SUCCESS` vẫn cần đọc **test count** nếu CI có khả năng skip tests hoặc report cũ.

### 17.1. Chạy một class để chẩn đoán

~~~bash
mvn -B -ntp -Dtest=ForkBudgetTest test
~~~

Chỉ chạy class đó, thường là một test. **Không đánh dấu toàn bộ suite pass** từ command này. Nó hữu ích để xem heapMaxMiB, processors và PID với flags đang thử.

### 17.2. Cấm ẩn test failures

Không dùng các cờ sau như quality gate release:

~~~bash
mvn -DskipTests package
mvn -Dmaven.test.failure.ignore=true verify
mvn -fn clean verify
~~~

Các lệnh có thể có mục đích chẩn đoán riêng, nhưng **không chứng minh** required tests đều pass. `-fn` của Maven reactor có thể trả exit code thành công dù có module failures.

### 17.3. Đừng nuốt exit code khi tee logs

Bash:

~~~bash
set -o pipefail
mvn -B -ntp clean verify | tee build.log
status=$?
exit "$status"
~~~

`pipefail` giúp pipeline giữ failure của Maven nếu `tee` chạy được. Trên PowerShell, dùng `$LASTEXITCODE` sau Maven CLI, không chỉ dựa vào dòng text cuối.

---

## 18. Failsafe: integration tests cũng có fork và budget riêng

Maven thường sử dụng:

- **Surefire** để chạy unit tests ở `test` phase.
- **Failsafe** để chạy integration tests ở `integration-test` và kiểm outcome ở `verify`.

Failsafe không phải “bản Surefire tự xử lý memory miễn phí”: nó cũng có tùy chọn `forkCount`, `reuseForks`, `argLine`, timeout tương ứng. Nếu trong CI chạy cả unit và integration tests, cần tính ngân sách các phases/profiles thực sự được chạy.

### 18.1. Snippet tích hợp Failsafe

Nếu project có test class như `DatabaseIT.java` và môi trường integration test được thiết lập đúng, thêm plugin sau vào `build/plugins`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.4</version>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <forkCount>1</forkCount>
        <reuseForks>true</reuseForks>
        <argLine>-Xms128m -Xmx512m</argLine>
        <forkedProcessTimeoutInSeconds>600</forkedProcessTimeoutInSeconds>
    </configuration>
</plugin>
~~~

Đây là **plugin snippet minh họa**, không có trong POM runnable cơ bản. Không tự chèn và chạy khi bạn chưa viết integration tests hoặc chưa có DB/service. Goals `integration-test` và `verify` được bind vào phases tương ứng theo Failsafe.

### 18.2. Vì sao Failsafe dùng verify?

Failsafe cho phép Maven đi qua `post-integration-test` cleanup trước khi đánh dấu build thất bại ở `verify`. Nếu gọi riêng `mvn integration-test`, bạn có thể bỏ qua bước kiểm tra failure/cleanup; với pipeline integration tests, dùng `mvn verify` theo lifecycle.

### 18.3. Dự trù external service/container

Testcontainers hoặc Dockerized DB không chỉ chiếm bộ nhớ trong Java heap. Chúng có **process/container memory và disk riêng**, thuộc tài nguyên của CI runner. Khi Failsafe/Surefire tăng forks mà mỗi fork khởi động DB riêng, chi phí này phải được cộng vào memory và CPU budget.

### 18.4. Unit tests và IT có chạy đồng thời?

Trong một **default lifecycle của cùng Maven module**, phase `test` xảy ra trước `integration-test`, nên không tự giả định Surefire và Failsafe của module đó đồng thời dùng peak RAM. Tuy nhiên trong reactor `-T`, các modules khác nhau có thể ở **phases khác nhau cùng lúc**, hoặc CI mở **nhiều jobs/containers**, vì vậy toàn runner vẫn có thể đồng thời chạy nhiều loại process.

---

## 19. Chiến lược tuning theo từng bước

### Bước 1 — Tạo baseline đáng tin

~~~bash
mvn -B -ntp -T 1 "-Dtest.forkCount=1" clean verify
~~~

Ghi:

- Tổng test count, failures/errors/skips.
- Wall-clock duration.
- Runner memory/cpu limit.
- Peak RSS/working set và CPU utilization.
- Surefire fork PID/heap max.
- Test classes chậm, GC metrics nếu có.

### Bước 2 — Giữ nguyên mọi thứ, tăng một biến

Thử:

~~~bash
mvn -B -ntp -T 1 "-Dtest.forkCount=2" clean verify
~~~

Nếu nhanh hơn và peak memory vẫn còn margin, có thể giữ. Nếu OOM hoặc flaky, quay lại 1 rồi điều tra.

### Bước 3 — Thử reactor parallel

Với multi-module project có graph cho phép:

~~~bash
mvn -B -ntp -T 2 "-Dtest.forkCount=1" clean verify
~~~

Tổng forks tối đa có thể bằng hai tại thời điểm các modules độc lập test cùng nhau. Không kết luận quá mức từ single-module demo: `-T 2` ở project chỉ một module không mang lại lợi ích reactor parallel.

### Bước 4 — Tối ưu bộ nhớ

Nếu Java heap OOM và runner còn RAM:

- Đo live set/GC/logs.
- Tìm test giữ object không cần thiết.
- Tăng test heap có kiểm soát, ví dụ 256 lên 384 MiB.
- Kiểm tra lại budget tổng cùng số forks.

Nếu container OOMKill:

- Giảm forkCount và `-T` trước.
- Giảm services/containers không cần.
- Tránh `MaxRAMPercentage` quá cao trên mỗi fork.
- Tăng runner memory chỉ khi đã có số đo và được phép.

### Bước 5 — Rà soát isolation/flakiness

Nếu parallel làm tests fail ngẫu nhiên:

- Kiểm port/schema/files shared.
- Loại dependence vào test order/static global state.
- Gắn resource locks nếu framework hỗ trợ.
- Chạy tuần tự tests vốn không concurrency-safe.
- Cân nhắc `reuseForks=false` cho nhóm tests gây state leakage, đồng thời đo startup overhead.

### Bước 6 — Chốt CI guardrails

- Job timeout và fork timeouts phù hợp với suite.
- Không skip required tests.
- Có lưu Surefire reports khi fail.
- Có memory headroom; không ở sát 100% limit.
- Có thể tái chạy baseline để phân tích regression.
- Ghim Maven/JDK/plugins và input dependency.
- Tránh thay đồng thời `-T`, forkCount, heap và JUnit parallelism trong một phép thử: bạn sẽ khó biết yếu tố nào tạo thay đổi.

---

## 20. Bảng chẩn đoán nhanh

| Hiện tượng | Khả năng chính | Bước kế tiếp |
| --- | --- | --- |
| Maven process OOM trước test | Heap Maven/plugins quá nhỏ | Đo Maven JVM và MAVEN_OPTS |
| Test process báo Java heap space | Heap fork/test data leak | Xem argLine, maxMemory, heap usage |
| Test process báo Metaspace | Metaspace cap/classloader leak | Đo classloading, chỉnh cap có kiểm chứng |
| Exit 137, không có Java OOM | Có thể SIGKILL/OOMKill | Kiểm runner/cgroup logs và timeouts |
| Forked VM terminated unexpectedly | OOM/crash/System.exit/flags sai | Xem dump, logs, process status |
| forkCount=0 “hết lỗi” | Đã chuyển tests sang Maven JVM | Không kết luận code hết memory leak |
| forkCount=1C làm CI chậm hơn | CPU/RAM bị oversubscribe | Giảm count, đo throughput |
| -T 4 nhưng chỉ một module | Không có parallel modules | Giữ -T 1 hoặc thay graph |
| reuseForks=true gây flakiness | Static state/resource leak giữa classes | Cô lập fixtures hoặc thử false |
| reuseForks=false quá chậm | JVM startup lặp lại | Dùng reuse=true nếu tests isolation-safe |
| Tests tranh port 8080 | Các forks cùng hardcode port | Allocate ports/namespace riêng |
| Test OOM dù Xmx nhỏ hơn runner RAM | Non-heap/native/sidecars | Đo RSS/limit toàn container |
| Active processors báo lớn hơn quota | CPU visibility/config khác | Xem cgroup/JDK, ActiveProcessorCount |
| JVM percentages gây OOM khi nhiều forks | Mỗi JVM tính % toàn container | Tính lại số forks × heap và overhead |
| Surefire timeout khi network chậm | Test/service hang hoặc throttling | Kiểm network, teardown, CPU load |
| exit timeout sau khi tests pass | Non-daemon threads còn sống | Cleanup executor/services |
| JUnit tests chạy ít hơn dự kiến | Test discovery/skip flags | Xem Surefire reports, failIfNoTests |
| PID trong test log khác PID Maven | Đúng vì đã fork | So argLine và process flags |
| PID trong test giống Maven PID | forkCount=0 hoặc process observation | Kiểm effective Surefire config |
| CI killed khi dùng Testcontainers | DB/browser containers dùng RAM ngoài heap | Tính service memory, giảm forks |
| GC log bị ghi đè | Nhiều forks chung filename | Dùng %p hoặc forkNumber |
| Maven và IDE chạy khác JDK | Toolchain/run config khác | So mvn -version và IDE runner |
| Một module pass, reactor fail | Module khác lỗi | Đọc Reactor Summary và scope -pl/-am |

---

## 21. Bài tập thực hành

### Bài A — Nhận diện các JVM

Vẽ sơ đồ Maven JVM + hai Surefire forked JVMs + một DB container. Nếu mỗi fork có `-Xmx512m`, tại sao tổng RAM job có thể lớn hơn 1.024 MiB?

### Bài B — Build runnable

Tạo bốn file mục 7, chạy `mvn -B -ntp clean verify`. Kiểm **3 tests PASS**, rồi `java -jar target/maven-fork-budget-demo-1.0.0.jar`. Stdout chính xác là gì?

### Bài C — In heap và PID

Mở `ForkBudgetTest` reports. Ghi `pid`, `heapMaxMiB`, `processors` thực. Có thể suy ra peak container RSS từ ba giá trị này không?

### Bài D — Fork reuse

Chạy `-Dtest.reuseForks=true` rồi `false`. Với 2 test classes, mỗi chế độ tạo bao nhiêu JVM theo lý thuyết? Vì sao kết quả timing không nói lên suite hàng nghìn classes?

### Bài E — Không fork

Chạy `-Dtest.forkCount=0`. Vì sao `argLine=-Xmx256m` không đặt heap của Maven JVM? Khi nào no-fork còn có rủi ro về system properties?

### Bài F — 1C

Một CI container có Java `availableProcessors=6` nhưng chỉ 4 GiB RAM. `forkCount=1C` và mỗi fork `-Xmx768m` có thể dẫn đến vấn đề gì trước khi cộng native overhead?

### Bài G — -T nhân fork

Reactor có tối đa 3 modules test đồng thời, `forkCount=2`. Tổng số test JVM tối đa theo lý thuyết là bao nhiêu? Nếu JUnit fixed parallelism=2 trong mỗi fork, có bao nhiêu test tasks có thể active? CPU có được bảo đảm đủ không?

### Bài H — Ngân sách

Lấy ví dụ 4 GiB ở mục 6. Thay `forkCount=2` bằng 1; tính lại tổng heap test tối đa. Vì sao chênh lệch đó **không** bằng mức giảm RSS được bảo đảm?

### Bài I — Maven vs test JVM

Đặt `MAVEN_OPTS="-Xmx512m"` và `test.jvm.args="-Xmx256m"`. Process nào nhận cấu hình nào? Làm thế nào xác nhận bằng PID/Runtime?

### Bài J — Java_tool_options

Thêm `JAVA_TOOL_OPTIONS="-XX:ActiveProcessorCount=2"` trong terminal sandbox, chạy bài mẫu. Vì sao điều này ảnh hưởng JVM nhìn thấy CPUs nhưng không cấp/giới hạn CPU ở mức runner?

### Bài K — Heap OOM và container kill

Phân biệt `OutOfMemoryError: Java heap space` với exit137. Cần evidence nào trước khi kết luận exit137 là kernel OOM killer?

### Bài L — Metaspace

Nếu test Spring/Mockito load quá nhiều classes và gặp `Metaspace` với cap 128 MiB, liệu tăng `-Xmx` có sửa không? Cần đo gì?

### Bài M — Thread leaks

Một test mở non-daemon executor và không đóng. `forkedProcessTimeoutInSeconds` khác `forkedProcessExitTimeoutInSeconds` ở điểm nào? Cách cleanup đúng là gì?

### Bài N — Shared resources

Hai fork cùng ghi `target/test-output.json` và bind `localhost:8080`. Thiết kế paths/ports/DB schemas riêng, thử dùng `surefire.forkNumber` và giải thích vì sao vẫn cần inter-job isolation.

### Bài O — JUnit parallelism

Bật `junit-platform.properties` với fixed parallelism=2. Nếu tests dùng chung mutable static collection, điều gì có thể xảy ra? Khi nào chọn sequential method execution?

### Bài P — Failsafe

Một integration test chạy Dockerized database. Vì sao Docker memory không nằm trong `-Xmx` của Failsafe test JVM? Hãy thiết kế budget cho test JVM và DB container.

### Bài Q — CI reports

Trong GitHub Actions/GitLab CI, vì sao cần lưu Surefire reports khi job fail? `if: always()` hay `when: always` có làm Maven failure thành success không?

### Bài R — Tuning experiment

Chọn test suite thực, giữ cùng source và runner, thử lần lượt baseline, fork2, -T2/fork1, heap384. Lưu runtime/peak memory/test failures. Đưa ra lựa chọn dựa trên số đo, không dựa trực giác.

### Bài S — Không che lỗi

Vì sao `mvn -fn verify`, `-DskipTests` hoặc Bash `|| true` không phù hợp release quality gate? Viết script trả đúng exit code Maven.

### Bài T — Hạn mức

Một workflow có `timeout-minutes=20`, `forkedProcessTimeoutInSeconds=180` và `@Timeout(5)`. Mỗi giới hạn áp dụng ở cấp nào? Vì sao timeout job không chữa được memory exhaustion?

---

## 22. Checklist đưa vào CI thực tế

- [ ] Đã ghi đúng Maven/JDK/Surefire/Failsafe versions.
- [ ] Biết Maven JVM và test fork JVM có heap riêng.
- [ ] Đặt `forkCount` theo **RAM và CPU thực**, không chỉ theo số cores.
- [ ] Hiểu `reuseForks` và rủi ro static state leak.
- [ ] Tính upper bound khi `-T` nhân số concurrent modules.
- [ ] Nếu bật JUnit parallelism, đo thêm threads/active test tasks.
- [ ] Không xem `-Xmx` là tổng giới hạn RSS của JVM.
- [ ] Dự trù metaspace, direct/native buffers, thread stacks và JVM overhead.
- [ ] Dự trù Maven JVM, compiler/plugin processes và sidecars/DB/containers.
- [ ] Có memory headroom, không chạy sát cgroup limit.
- [ ] Phân biệt `MAVEN_OPTS`, Surefire `argLine` và `JAVA_TOOL_OPTIONS`.
- [ ] Nếu có JaCoCo/agents, bảo toàn agent arguments đúng cấu hình.
- [ ] Không dùng forkCount=0 + -T song song khi chưa hiểu rủi ro.
- [ ] Không bật JVM/threads/modules concurrency tăng cùng lúc mà không đo.
- [ ] Files, ports, DB schemas và test fixtures được cô lập giữa forks.
- [ ] Surefire fork timeout, exit timeout và CI job timeout có lý do cụ thể.
- [ ] Failsafe IT services được tính trong resource budget riêng.
- [ ] Đã kiểm test count và Surefire XML reports, không skip tests.
- [ ] Khi exit137/VM terminated, kiểm logs/cgroup trước khi kết luận OOM.
- [ ] Logs và GC diagnostics lưu với PID hoặc fork identifier khi cần.
- [ ] Có số đo wall-clock duration, peak memory/RSS và CPU contention.
- [ ] CI scripts giữ đúng exit code, không dùng -fn/ignore flags để che lỗi.
- [ ] Profile/runner type/limit được đối chiếu thực, không dựa tên label.
- [ ] Thay đổi cấu hình được kiểm trên suite thật và nhiều runs đủ đại diện.

**Kết luận:** Surefire `forkCount` và `reuseForks` điều khiển số/lifecycle các **test JVM**, `argLine` điều khiển JVM options của chúng; Maven `-T` điều khiển độ song song **giữa modules**, còn JUnit Jupiter có thread parallelism riêng. Trong CI, **-Xmx chỉ giới hạn heap một process** — muốn build nhanh và ổn định phải cộng cả memory ngoài heap, Maven JVM, các forks, services và headroom theo hạn mức runner thật. Hãy bắt đầu với cấu hình đơn giản, tăng một trục concurrency mỗi lần, kiểm bằng test reports/CPU/RSS/GC metrics và không che failures bằng timeout hay skip flags.

## 23. Nguồn tham khảo chính thức

- [Apache Maven Surefire 3.5.4 — surefire:test](https://maven.apache.org/surefire-archives/surefire-3.5.4/maven-surefire-plugin/test-mojo.html): `forkCount`, `reuseForks`, `argLine`, process timeouts, failIfNoTests.
- [Apache Maven Surefire — Fork Options and Parallel Test Execution](https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options-and-parallel-execution.html): `1C`, fork number, reuse behavior, interaction with Maven `-T`.
- [Apache Maven Surefire — Debugging Tests](https://maven.apache.org/surefire-archives/surefire-3.5.4/maven-surefire-plugin/examples/debugging.html): fork vs non-fork diagnostics.
- [Apache Maven Failsafe Plugin — Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/): unit tests vs integration tests, `integration-test`, `post-integration-test`, `verify`.
- [Apache Maven Surefire — Using JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html): JUnit5/Surefire tests.
- [JUnit 5 User Guide — Parallel Execution](https://docs.junit.org/5.11.4/user-guide/#writing-tests-parallel-execution): JUnit Jupiter default and opt-in parallel settings.
- [Oracle JDK 17 — java Command Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xms`, `-Xmx`, `-XX:ActiveProcessorCount` và JVM options.
- [OpenJDK — Container Awareness](https://openjdk.org/jeps/8182070): container CPU/memory ergonomics.
- [GitHub Docs — Choosing the Runner for a Job](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job): runner CPU/RAM tùy repo/plan/label.
- [GitHub Docs — Workflow Syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax): `timeout-minutes`, jobs, permissions.
- [actions/setup-java v6](https://github.com/actions/setup-java): JDK setup/cache và runtime requirements.
- [actions/checkout](https://github.com/actions/checkout): checkout action.
- [GitLab CI/CD YAML Reference](https://docs.gitlab.com/ci/yaml/): `artifacts:reports:junit`, `when: always`, job timeout.
- [GitLab Runner — Docker Executor](https://docs.gitlab.com/runner/executors/docker.html): container resource config.
- [GitLab Runner — Kubernetes Executor](https://docs.gitlab.com/runner/executors/kubernetes/): resource limits/requests.
