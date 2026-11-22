# Phân phối công việc kiểm thử và kiểm soát cạnh tranh tài nguyên

Khi một dự án Java có nhiều unit test và integration test, chạy tất cả tuần tự có thể làm pipeline kéo dài. Build tool và test framework cho phép phân phối công việc qua nhiều tiến trình, thread hoặc CI agent để tận dụng CPU và rút ngắn thời gian. Tuy nhiên, tăng mức song song cũng làm nhiều bài kiểm thử truy cập cùng lúc vào database, cổng mạng, file, service hoặc trạng thái dùng chung.

Nếu không kiểm soát những tài nguyên đó, test có thể tranh chấp, ghi đè dữ liệu, chiếm cùng một port, vượt giới hạn connection hoặc thất bại ngẫu nhiên. Một cấu hình song song tốt cần giải quyết đồng thời hai việc:

1. **Phân phối công việc hợp lý:** chia test thành các đơn vị có thể chạy đồng thời và cân bằng thời gian giữa worker.
2. **Bảo đảm cô lập tài nguyên:** mỗi test có dữ liệu và tài nguyên riêng, hoặc có cơ chế đồng bộ khi buộc phải chia sẻ.

Không phải cứ tăng số thread hoặc fork là build nhanh hơn. Mục tiêu là tăng throughput trong giới hạn CPU, bộ nhớ, I/O và dịch vụ bên ngoài, đồng thời giữ test độc lập và kết quả ổn định.

## 1. Các cấp độ song song trong quy trình kiểm thử

Một build Java có thể chạy đồng thời ở nhiều cấp độ. Cần phân biệt chúng vì mỗi cấp có phạm vi chia sẻ trạng thái và cách cấu hình khác nhau.

| Cấp độ | Đơn vị được chạy đồng thời | Cơ chế thường gặp | Trạng thái được chia sẻ |
|---|---|---|---|
| Multi-project build | Module/subproject | Gradle parallel project execution, Maven reactor threads | Có thể chia sẻ daemon, filesystem và dịch vụ ngoài |
| Task-level | Task build độc lập | Gradle task graph/worker leases | Có thể dùng chung output hoặc tài nguyên ngoài nếu cấu hình sai |
| Test process/fork | Nhóm test trong các JVM riêng | Gradle maxParallelForks, Maven Surefire forkCount | Không chia sẻ static memory, nhưng vẫn chia sẻ DB/port/file/service |
| Test engine/thread | Class hoặc method test trong cùng JVM | JUnit Jupiter parallel execution, TestNG/JUnit 4 | Chia sẻ static state, singleton và heap của JVM |
| CI sharding | Nhóm test trên nhiều runner/agent | Test matrix, test splitting, shard assignment | Có thể chia sẻ database, account, queue hoặc endpoint bên ngoài |

Các cấp này có thể được kết hợp. Ví dụ, CI chạy hai shard, mỗi shard build nhiều module song song, mỗi module tạo hai test JVM, và mỗi JVM cho JUnit chạy nhiều class đồng thời. Nếu không tính tổng mức đồng thời, số worker thực tế có thể vượt xa dự kiến.

### 1.1. Song song hóa build không đồng nghĩa song song hóa test

Gradle có thể chạy các task hoặc subproject độc lập đồng thời, nhưng điều đó không tự bật parallel execution bên trong JUnit. Ngược lại, JUnit có thể chạy method test song song trong một JVM dù build chỉ có một task test.

Maven có thể chạy nhiều module trong reactor bằng tùy chọn T, còn Surefire/Failsafe có thể tạo fork JVM để chạy test. Hai cơ chế này khác nhau và có thể nhân mức đồng thời lên.

### 1.2. Process isolation và thread concurrency

Nhiều test JVM tạo ra sự cô lập tốt hơn cho static state, system properties và classloader. Mỗi JVM có heap riêng. Tuy vậy, các tiến trình vẫn dùng chung database, filesystem, cổng mạng và quota của dịch vụ.

Nhiều thread trong cùng JVM tiết kiệm chi phí tạo process nhưng test phải an toàn khi chạy đồng thời. Chúng có thể truy cập cùng singleton, static field, cache trong bộ nhớ, system properties và các object mutable.

## 2. Chọn đơn vị phân phối công việc

Không phải mọi test đều phù hợp với cùng một cấp song song.

| Loại kiểm thử | Đặc điểm | Cách phân phối thường phù hợp |
|---|---|---|
| Unit test thuần, không trạng thái dùng chung | Nhanh, ít I/O, độc lập | Chạy nhiều class/method song song |
| Unit test dùng static/global state | Có thể ảnh hưởng test khác | Cô lập JVM hoặc chạy tuần tự/khóa có chọn lọc |
| Test truy cập database | Tốn connection và dùng dữ liệu ngoài JVM | Schema/database riêng hoặc dữ liệu namespace riêng; giới hạn worker |
| Test khởi chạy server | Tốn RAM, port và thời gian khởi động | Fork có giới hạn, port động, môi trường riêng |
| Test gọi API bên ngoài | Có quota, rate limit và độ trễ mạng | Mock/sandbox, giới hạn concurrency |
| Test nặng CPU | Có thể tận dụng nhiều core | Chọn số worker theo CPU và bộ nhớ |
| Test nặng I/O | Có thể bị nghẽn disk/network | Đo throughput, tránh tăng worker quá mức |

Một nhóm test độc lập và nhẹ có thể chạy đồng thời mạnh. Một nhóm test dùng chung database production-like hoặc một service có quota thấp cần giới hạn và cô lập cẩn thận.

## 3. Gradle: phân phối test qua nhiều JVM

Với Java Plugin, task test thuộc loại Test. Gradle thường chạy test trong một JVM worker riêng. Mặc định maxParallelForks là 1, nên các class test của task được phân phối qua một worker process.

### 3.1. Cấu hình maxParallelForks

Trong build.gradle.kts:

~~~kotlin
tasks.test {
    maxParallelForks = 2
}
~~~

Giá trị 2 cho phép task test sử dụng tối đa hai test worker JVM đồng thời. Gradle phân phối các class test qua các worker này. Mỗi worker có heap và trạng thái static riêng.

Có thể dùng giới hạn worker của máy làm tham chiếu:

~~~kotlin
tasks.test {
    maxParallelForks = Runtime.getRuntime()
        .availableProcessors()
        .coerceAtLeast(1)
}
~~~

Đây chỉ là điểm bắt đầu. Số processor nhìn thấy không cho biết đầy đủ bộ nhớ, quota container, database connection limit hoặc mức tiêu thụ của từng test. Không nên đặt worker bằng toàn bộ số core nếu mỗi test JVM cần nhiều RAM hoặc gọi service có giới hạn thấp.

### 3.2. Giới hạn tài nguyên của test JVM

Có thể giới hạn heap cho mỗi worker:

~~~kotlin
tasks.test {
    maxParallelForks = 2
    maxHeapSize = "1g"
    minHeapSize = "256m"
}
~~~

Nếu mỗi worker được phép dùng tối đa 1 GB heap và có hai worker, riêng test JVM có thể cần khoảng 2 GB heap, chưa tính Gradle daemon, metaspace, thread stack, native memory và hệ điều hành.

Nếu đặt heap quá thấp, test có thể gặp OutOfMemoryError hoặc GC liên tục. Nếu đặt quá cao và tăng nhiều worker, runner có thể hết RAM hoặc bị hệ điều hành/container kill.

### 3.3. forkEvery: tái tạo worker sau một số class

Gradle có thuộc tính forkEvery, xác định số test class được chạy trong một test process trước khi process đó bị thay thế. Giá trị mặc định 0 nghĩa là không tự động fork lại theo số class trong suốt task.

~~~kotlin
tasks.test {
    maxParallelForks = 2
    forkEvery = 100
}
~~~

Ví dụ trên yêu cầu mỗi worker được tái tạo sau khoảng 100 test class. Điều này có thể giúp hạn chế ảnh hưởng của memory leak hoặc trạng thái tích lũy trong test process. Đổi lại, tạo JVM mới tốn thời gian khởi động và làm giảm lợi ích tái sử dụng process.

Không dùng forkEvery bằng 1 như cách sửa mặc định cho test không cô lập. Nó chỉ che một số vấn đề về trạng thái trong process; database, port và file dùng chung vẫn có thể xung đột.

### 3.4. Giới hạn worker toàn build

Gradle có thể giới hạn số worker lease được dùng đồng thời:

~~~bash
./gradlew test --max-workers=4
~~~

Hoặc cấu hình trong gradle.properties:

~~~properties
org.gradle.workers.max=4
~~~

Giới hạn này áp dụng ở phạm vi build và ảnh hưởng đến việc lập lịch task/worker. Nó giúp tránh một build chiếm toàn bộ tài nguyên máy. Các task test còn có maxParallelForks; cần cân nhắc cả hai thay vì chỉ nhìn một giá trị.

### 3.5. Song song hóa nhiều subproject

Với multi-project build, Gradle có thể thực thi các project/task độc lập song song:

~~~properties
org.gradle.parallel=true
org.gradle.workers.max=4
~~~

Hoặc bật bằng tham số:

~~~bash
./gradlew build --parallel --max-workers=4
~~~

--parallel cho phép Gradle chạy task của các project độc lập đồng thời. Nó không tự động bật JUnit parallel execution. Nếu nhiều subproject đều có task test và mỗi task lại mở nhiều fork, tổng tải có thể tăng nhanh; hãy giới hạn worker toàn build và đo tài nguyên.

## 4. Gradle: song song hóa test bên trong một JVM

maxParallelForks tạo nhiều JVM. Nếu muốn JUnit Jupiter chạy class hoặc method song song bên trong mỗi JVM, cần bật parallel execution của JUnit Platform.

Một cách rõ ràng là tạo file src/test/resources/junit-platform.properties:

~~~properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = same_thread
junit.jupiter.execution.parallel.mode.classes.default = concurrent
junit.jupiter.execution.parallel.config.strategy = fixed
junit.jupiter.execution.parallel.config.fixed.parallelism = 4
~~~

Với cấu hình này:

- JUnit bật khả năng thực thi song song;
- các method trong một class mặc định chạy cùng thread;
- các class test có thể chạy đồng thời;
- parallelism mong muốn được đặt là 4 cho engine.

Đây là điểm khởi đầu thận trọng: class độc lập được phân phối song song, còn các method trong cùng class giữ thứ tự tuần tự theo luồng thực thi thông thường. Chỉ chuyển method sang concurrent khi fixture và trạng thái của chúng an toàn khi chạy đồng thời.

Có thể cấu hình qua Gradle:

~~~kotlin
tasks.test {
    useJUnitPlatform()
    systemProperty(
        "junit.jupiter.execution.parallel.enabled",
        "true"
    )
    systemProperty(
        "junit.jupiter.execution.parallel.mode.default",
        "same_thread"
    )
    systemProperty(
        "junit.jupiter.execution.parallel.mode.classes.default",
        "concurrent"
    )
    systemProperty(
        "junit.jupiter.execution.parallel.config.strategy",
        "fixed"
    )
    systemProperty(
        "junit.jupiter.execution.parallel.config.fixed.parallelism",
        "4"
    )
}
~~~

Chọn một nơi quản lý cấu hình để tránh cùng một property bị đặt khác nhau giữa file junit-platform.properties, Gradle task và CI.

### 4.1. Chọn chiến lược parallelism

JUnit Jupiter hỗ trợ các chiến lược cấu hình như:

| Strategy | Ý nghĩa |
|---|---|
| dynamic | Tính parallelism dựa trên số processor và dynamic factor |
| fixed | Dùng một con số parallelism được chỉ định |
| custom | Dùng implementation cấu hình riêng |

Với môi trường CI có quota CPU/RAM rõ ràng, fixed parallelism thường dễ dự đoán. Dynamic strategy tiện khi môi trường thay đổi, nhưng cần hiểu cách JUnit xác định số processor mà JVM nhìn thấy.

### 4.2. Cho phép method chạy song song

Nếu các method trong cùng class thực sự độc lập, có thể đặt:

~~~properties
junit.jupiter.execution.parallel.mode.default = concurrent
junit.jupiter.execution.parallel.mode.classes.default = concurrent
~~~

Khi đó cả class và method có thể được thực thi đồng thời theo mô hình của JUnit. Trước khi bật, kiểm tra:

- mỗi test có fixture riêng không;
- test có thay đổi static field hoặc system property không;
- các method có dùng chung instance/resource không;
- dữ liệu database có tách biệt không;
- test có phụ thuộc thứ tự hoặc trạng thái của method trước không.

Nếu chưa chắc, hãy bắt đầu bằng song song hóa class, sau đó bật method-level concurrency cho những nhóm đã được thiết kế để độc lập.

### 4.3. Dùng @Execution để chọn phạm vi

Có thể đánh dấu class hoặc method bằng @Execution:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

@Execution(ExecutionMode.CONCURRENT)
class IndependentCalculationTest {
    @Test
    void calculatesFirstCase() {
        // Test không dùng trạng thái mutable chung.
    }

    @Test
    void calculatesSecondCase() {
        // Test độc lập với test còn lại.
    }
}
~~~

Annotation này hữu ích khi chỉ một số nhóm test được phép chạy đồng thời. Tuy nhiên, annotation không tự làm cho code thread-safe. Test vẫn phải được thiết kế để không tranh chấp dữ liệu.

## 5. Maven: phân phối test bằng Surefire và Failsafe

Maven thường dùng:

- **Maven Surefire Plugin** để chạy unit test trong phase test;
- **Maven Failsafe Plugin** để chạy integration test qua các phase integration-test và verify.

Hai plugin có cấu hình fork/process riêng. Nếu dùng JUnit Jupiter, cấu hình song song bên trong engine nên được quản lý qua JUnit Platform properties; không nhầm forkCount với số thread trong JUnit.

### 5.1. Dùng forkCount

Ví dụ Maven Surefire:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <forkCount>2</forkCount>
        <reuseForks>true</reuseForks>
        <argLine>-Xms256m -Xmx1g</argLine>
    </configuration>
</plugin>
~~~

forkCount xác định số JVM test có thể chạy đồng thời cho module. reuseForks=true cho phép tái sử dụng forked JVM để chạy nhiều test class, giảm chi phí khởi động. argLine truyền JVM options cho process test.

Nếu dùng forkCount là 1C, Surefire có thể tính số fork dựa trên số CPU core mà JVM nhìn thấy. Cách này không tự tính RAM, database connection hoặc quota service; nên đo trong CI trước khi dùng.

### 5.2. reuseForks và isolation

Với reuseForks=true, nhiều class test chạy trong cùng một JVM fork. Static state hoặc system properties do test để lại có thể ảnh hưởng class chạy sau nếu không được reset.

Với reuseForks=false, Surefire tạo process mới theo cách thực thi test class, tăng isolation process nhưng tốn thời gian khởi động và bộ nhớ. Cấu hình này không giải quyết xung đột database hoặc port vì các process vẫn chia sẻ hệ thống bên ngoài.

Đừng dùng reuseForks=false để che test phụ thuộc thứ tự. Hãy sửa test để thiết lập và dọn trạng thái đúng cách; chỉ chọn process isolation khi nó có lợi ích được xác định rõ.

### 5.3. JUnit Jupiter parallel execution trong Maven

Đặt file src/test/resources/junit-platform.properties:

~~~properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = same_thread
junit.jupiter.execution.parallel.mode.classes.default = concurrent
junit.jupiter.execution.parallel.config.strategy = fixed
junit.jupiter.execution.parallel.config.fixed.parallelism = 4
~~~

Surefire cần phiên bản hỗ trợ JUnit Platform và dependency test phù hợp. File properties được đưa vào test runtime classpath, nên JUnit Jupiter đọc cấu hình khi khởi chạy engine.

Nếu Surefire tạo hai fork JVM và mỗi JVM có JUnit parallelism là bốn, tổng số luồng thực thi test có thể cao hơn bốn. Cần tính cả fork và engine concurrency.

### 5.4. Parallel modes cho JUnit 4 hoặc TestNG

Surefire có các cấu hình parallel, threadCount và các tùy chọn liên quan cho những provider/framework hỗ trợ mô hình này. Ví dụ khái niệm:

~~~xml
<configuration>
    <parallel>classes</parallel>
    <threadCount>4</threadCount>
</configuration>
~~~

Ý nghĩa cụ thể phụ thuộc test provider và framework. Không áp dụng cấu hình này như thể nó điều khiển JUnit Jupiter giống cách JUnit Platform properties làm. Với JUnit 5, hãy cấu hình parallel execution trong JUnit Jupiter engine.

### 5.5. Parallel integration test với Failsafe

Failsafe có cấu hình fork tương tự Surefire:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <forkCount>2</forkCount>
        <reuseForks>true</reuseForks>
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

Integration test thường sử dụng nhiều tài nguyên ngoài JVM hơn unit test. Trước khi tăng fork, hãy xác định số database instance/schema, port, container và external service có thể hỗ trợ.

## 6. Maven: song song hóa nhiều module

Maven reactor có thể build các module độc lập song song bằng tùy chọn T:

~~~bash
./mvnw -T 4 verify
~~~

Hoặc dùng số core:

~~~bash
./mvnw -T 1C verify
~~~

Maven vẫn phải tôn trọng quan hệ dependency giữa các module. Module phụ thuộc module khác cần chờ module dependency hoàn tất theo reactor graph.

### 6.1. Kết hợp reactor parallelism và Surefire forks

Giả sử Maven chạy bốn module đồng thời và mỗi module có forkCount bằng 2. Về lý thuyết, có thể có tới khoảng tám test JVM cùng lúc, chưa tính thread parallelism bên trong mỗi JVM.

Nếu mỗi JVM có JUnit parallelism bốn, số test thread tiềm năng có thể tăng hơn nữa. Đây là lý do không nên đặt mọi cấp độ bằng số CPU core một cách độc lập.

### 6.2. Xác định giới hạn toàn pipeline

Khi cần giữ tổng tải thấp, có thể:

- giảm T để ít module build đồng thời;
- giảm forkCount cho integration test nặng;
- giới hạn JUnit parallelism;
- tách unit test nhanh và integration test cần service;
- chia job CI theo nhóm test thay vì tăng mọi loại concurrency.

Một module có thể build song song với module khác nhưng vẫn chạy test tuần tự nếu test dùng chung môi trường.

## 7. Phân phối test trên nhiều CI agent (sharding)

Khi một test suite quá lớn cho một runner, CI có thể chia danh sách test thành nhiều shard. Mỗi shard chạy trên một agent hoặc job độc lập.

Ví dụ:

~~~text
All tests
├── Shard 1: unit tests A-F
├── Shard 2: unit tests G-M
├── Shard 3: unit tests N-S
└── Shard 4: unit tests T-Z
~~~

Sharding có thể giảm wall-clock time vì nhiều máy làm việc đồng thời. Nhưng các shard phải dùng phân hoạch ổn định và không bỏ sót hoặc chạy trùng test ngoài chủ đích.

### 7.1. Chia theo package hoặc class

Cách đơn giản là chia danh sách class theo package, tên hoặc nhóm test. Cách này dễ cấu hình nhưng có thể mất cân bằng nếu một package chứa vài integration test rất lâu.

Gradle có thể chọn test bằng filter:

~~~bash
./gradlew test --tests "com.example.unit.*"
~~~

Maven Surefire có thể chọn class cụ thể:

~~~bash
./mvnw test -Dtest=PriceCalculatorTest,OrderMapperTest
~~~

Trong CI, mỗi shard nhận tập filter khác nhau. Cần xác nhận filter của framework/build plugin hoạt động theo đúng pattern đã chọn.

### 7.2. Chia theo thời lượng lịch sử

Nếu CI lưu thời gian chạy của từng test class, có thể chia nhóm sao cho tổng thời lượng các shard gần bằng nhau. Đây thường là cách cân bằng tốt hơn chia đều số class vì test có thời lượng rất khác nhau.

Một thuật toán đơn giản:

1. sắp xếp test class theo thời lượng giảm dần;
2. lần lượt đưa class tiếp theo vào shard đang có tổng thời gian thấp nhất;
3. ghi danh sách test của mỗi shard thành artifact/configuration;
4. chạy từng shard và hợp nhất báo cáo.

Thời lượng lịch sử cần được cập nhật định kỳ vì test thay đổi theo thời gian.

### 7.3. Không dùng thứ tự test để phân shard

Không nên chia test bằng cách dựa vào thứ tự phát hiện không ổn định của filesystem hoặc thứ tự ngẫu nhiên. Hãy tạo danh sách test có thứ tự xác định và lưu lại shard assignment trong log để tái hiện lỗi.

### 7.4. Báo cáo và test failure

Mỗi shard cần xuất report riêng, tránh ghi đè vào cùng một thư mục output. CI có thể thu thập và hợp nhất JUnit XML reports sau khi tất cả shard hoàn thành.

Khi một shard thất bại, log cần nêu:

- shard ID và tổng số shard;
- danh sách test class đã chạy;
- commit và build parameters;
- thời gian từng test;
- environment/worker identity;
- test bị fail, skipped hoặc retry.

## 8. Cạnh tranh tài nguyên là gì?

Cạnh tranh tài nguyên xảy ra khi nhiều test hoặc worker cùng sử dụng một tài nguyên có giới hạn hoặc có trạng thái mutable.

Các nhóm thường gặp:

| Tài nguyên | Biểu hiện cạnh tranh | Hậu quả |
|---|---|---|
| CPU | Nhiều test nặng CPU chạy cùng lúc | Context switching, thời gian chạy tăng |
| RAM/heap | Nhiều JVM hoặc container lớn cùng chạy | GC nhiều, OOM, process bị kill |
| Database connections | Nhiều test mở connection cùng lúc | Pool cạn, timeout, server quá tải |
| Database data | Test cùng sửa một row/table/schema | Kết quả phụ thuộc thứ tự, dữ liệu bị ghi đè |
| Network ports | Nhiều test bind cùng port cố định | BindException, test fail ngẫu nhiên |
| Filesystem | Nhiều test ghi cùng file/thư mục | File bị ghi đè hoặc đọc dữ liệu dở dang |
| Queue/topic | Test consume cùng message stream | Test khác mất message hoặc nhận nhầm message |
| External API | Nhiều request đồng thời | Rate limit, quota hoặc chi phí tăng |
| Shared account | Test cùng đổi mật khẩu/trạng thái account | Test ảnh hưởng lẫn nhau |
| Locks | Nhiều worker chờ cùng lock | Bottleneck, deadlock hoặc timeout |

Tăng concurrency có thể làm thời gian chờ tài nguyên lớn hơn thời gian xử lý hữu ích. Vì vậy, hiệu năng phải được đo ở mức toàn hệ thống, không chỉ số worker.

## 9. Cô lập tài nguyên trước khi dùng lock

Chiến lược tốt nhất thường là tạo tài nguyên riêng cho từng test hoặc từng worker. Khi không thể cô lập, mới dùng lock để tuần tự hóa phần cần thiết.

### 9.1. Database: schema hoặc namespace riêng

Nếu mọi test cùng dùng bảng orders và xóa dữ liệu trước khi chạy, hai test song song có thể xóa dữ liệu của nhau.

Các cách cô lập:

- tạo database riêng cho từng CI shard;
- tạo schema riêng cho từng test class hoặc worker;
- dùng tenant/test ID riêng cho mỗi test;
- thêm khóa namespace vào dữ liệu;
- dùng transaction rollback khi mọi thao tác nằm trong cùng transaction và không có side effect ngoài transaction;
- reset database bằng fixture được kiểm soát.

Ví dụ namespace:

~~~java
String testNamespace = "test-" + UUID.randomUUID();
~~~

Mỗi test chỉ đọc/ghi dữ liệu có namespace của nó và cleanup đúng namespace đó. UUID ngẫu nhiên ở đây dùng để cô lập dữ liệu test; nếu giá trị được ghi vào artifact build thì lại là một nguồn không deterministic.

### 9.2. Connection pool

Nếu mỗi test mở một connection và có 20 test chạy cùng lúc, database cần chịu được ít nhất số connection tương ứng cộng các connection của ứng dụng và công cụ khác. Nếu pool chỉ cho 10 connection, test có thể chờ hoặc timeout.

Hãy tính tổng connection từ:

- số test JVM;
- số thread test trong mỗi JVM;
- số connection tối đa mỗi test có thể giữ;
- connection của app/server fixture;
- connection của migration hoặc setup task.

Không nhất thiết mỗi test thread cần connection riêng nếu test dùng chung pool có giới hạn, nhưng cần tránh giữ connection lâu trong lúc chờ network hoặc assertion.

### 9.3. Port mạng động

Không hardcode một port như 8080 cho mọi test server. Hai test chạy đồng thời có thể cùng bind port và một test thất bại.

Ưu tiên cho server bind port 0 để hệ điều hành cấp port khả dụng, sau đó đọc port thực tế từ server đã khởi động. Nếu framework test có cơ chế random port, dùng cơ chế đó.

Tránh mô hình tìm port trống bằng cách mở socket tạm, đóng nó rồi mới khởi động server ở port đó; một process khác có thể chiếm port trong khoảng thời gian giữa hai thao tác.

### 9.4. Thư mục tạm riêng

Mỗi test nên dùng thư mục tạm riêng. Với JUnit Jupiter:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;

class FileExportTest {
    @Test
    void writesExportIntoItsOwnDirectory(@TempDir Path tempDir) {
        Path output = tempDir.resolve("export.csv");
        // Test chỉ ghi file trong tempDir được cấp riêng.
    }
}
~~~

Không dùng một đường dẫn cố định như build/test-output/result.csv cho nhiều test chạy đồng thời. Nếu phải dùng thư mục chung, cần tên file duy nhất và cleanup có kiểm soát.

### 9.5. Queue, topic và external API

Tạo queue/topic riêng hoặc gắn correlation ID/namespace cho message test. Test chỉ consume message thuộc lượt của mình.

Với external API, ưu tiên mock hoặc sandbox. Nếu cần gọi endpoint thật, giới hạn concurrency theo quota, dùng account/test data riêng và có cơ chế retry có kiểm soát. Không để nhiều test cùng thay đổi trạng thái một account dùng chung.

## 10. Chia sẻ trạng thái trong cùng JVM

Test chạy bằng nhiều thread trong cùng process có thể truy cập chung:

- static fields;
- singleton;
- cache trong bộ nhớ;
- system properties;
- default locale/timezone;
- default security context;
- shared mock hoặc fixture;
- mutable object được tạo trong BeforeAll.

Ví dụ không an toàn:

~~~java
class CounterTest {
    private static int counter = 0;

    @Test
    void incrementsCounter() {
        counter++;
        // Assertion phụ thuộc test khác có chạy trước hay không.
    }
}
~~~

Kết quả phụ thuộc lịch thực thi thread. Cách tốt hơn là tạo trạng thái riêng trong từng test hoặc dùng object thread-safe nếu chia sẻ là yêu cầu thực sự.

### 10.1. Không phụ thuộc thứ tự test

Mỗi test phải tự chuẩn bị dữ liệu và không dựa vào test trước đó. Thứ tự test có thể thay đổi khi parallel execution, test filtering hoặc CI sharding được bật.

Nếu test B chỉ thành công sau test A, hai test đang có dependency ẩn. Hãy chuyển setup chung thành fixture rõ ràng hoặc hợp nhất thành một scenario có chủ đích.

### 10.2. Reset trạng thái toàn cục

Nếu test thay đổi system properties, default locale, timezone hoặc singleton state, cần khôi phục giá trị trong finally/teardown ngay cả khi assertion thất bại.

Ví dụ:

~~~java
String previous = System.getProperty("app.mode");
try {
    System.setProperty("app.mode", "test");
    // Thực hiện hành vi cần kiểm tra.
} finally {
    if (previous == null) {
        System.clearProperty("app.mode");
    } else {
        System.setProperty("app.mode", previous);
    }
}
~~~

Nếu nhiều test cùng thay system property, việc lưu/khôi phục riêng từng test vẫn có thể race. Khi đó, dùng resource lock hoặc tránh thay global property trong test chạy đồng thời.

## 11. JUnit Jupiter: khóa tài nguyên dùng chung

JUnit Jupiter có @ResourceLock để mô tả test sử dụng tài nguyên được đặt tên. Test khác khai báo cùng resource lock sẽ được điều phối theo chế độ truy cập.

Ví dụ khóa system properties:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

@ResourceLock(
    value = Resources.SYSTEM_PROPERTIES,
    mode = ResourceAccessMode.READ_WRITE
)
class SystemPropertyTest {
    @Test
    void changesOneSystemProperty() {
        // Thay đổi property và khôi phục sau test.
    }
}
~~~

Các test dùng cùng resource lock được JUnit điều phối để tránh chạy đồng thời theo cách xung đột. Có thể dùng tên resource tùy chỉnh cho tài nguyên ứng dụng.

### 11.1. Lock có phạm vi trong test engine

@ResourceLock chỉ điều phối các test mà cùng JUnit engine quản lý trong phạm vi execution tương ứng. Nó không phải distributed lock và không tự đồng bộ:

- hai JVM Surefire/Gradle fork khác nhau;
- hai Gradle task test riêng biệt;
- hai Maven module chạy song song;
- hai CI agent;
- một test và một ứng dụng bên ngoài.

Với database hoặc port dùng chung qua nhiều process, cần cô lập bằng namespace/port riêng hoặc dùng lock bên ngoài có phạm vi phù hợp.

### 11.2. @Isolated

Nếu một class cần chạy riêng so với các test Jupiter khác trong cùng execution, có thể dùng @Isolated:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Isolated;

@Isolated
class ChangesGlobalRuntimeStateTest {
    @Test
    void changesGlobalState() {
        // Test cần chạy cô lập với các test Jupiter khác.
    }
}
~~~

Đây là biện pháp dành cho class có trạng thái toàn cục khó cô lập. Không nên đánh dấu nhiều test class Isolated nếu có thể sửa fixture hoặc resource sharing để chạy song song an toàn.

### 11.3. @Execution(SAME_THREAD)

Có thể giữ một class hoặc method tuần tự:

~~~java
@Execution(ExecutionMode.SAME_THREAD)
class UsesSharedFixtureTest {
    // Các test trong nhóm được thực thi cùng thread.
}
~~~

Tuần tự trong cùng class không bảo vệ tài nguyên trước test ở JVM khác hoặc CI agent. Hãy kết hợp với isolation hoặc lock phù hợp.

## 12. Lock, semaphore và giới hạn tài nguyên ở cấp ứng dụng

Đôi khi test cần dùng một tài nguyên có số lượng giới hạn, ví dụ chỉ có hai license test hoặc một endpoint chỉ cho phép ba request đồng thời. Có thể dùng semaphore hoặc cơ chế giới hạn concurrency ở fixture.

Ví dụ Java:

~~~java
private static final Semaphore LICENSE_SLOTS = new Semaphore(2);

void runLicensedScenario() throws InterruptedException {
    LICENSE_SLOTS.acquire();
    try {
        // Sử dụng tài nguyên có giới hạn.
    } finally {
        LICENSE_SLOTS.release();
    }
}
~~~

Semaphore trong ví dụ chỉ đồng bộ các thread trong cùng JVM. Nó không giới hạn được nhiều fork hoặc CI agent. Nếu giới hạn nằm ở dịch vụ ngoài, cần cơ chế phân phối slot/lease có phạm vi toàn hệ thống hoặc giới hạn số job ở CI.

### 12.1. Lock càng rộng, throughput càng thấp

Nếu khóa toàn bộ test suite để bảo vệ một file cấu hình, tất cả test sẽ chạy tuần tự dù chỉ một nhóm nhỏ cần file đó. Hãy khóa tài nguyên cụ thể và chỉ trong khoảng thời gian cần thiết.

### 12.2. Tránh deadlock

Nếu test cần nhiều lock, tất cả phải lấy theo thứ tự nhất quán. Giữ lock trong khi chờ network, sleep hoặc chờ một task khác có thể làm các worker khác bị chặn. Thiết kế tốt hơn là giữ lock trong thời gian ngắn và giải phóng chắc chắn trong mọi nhánh.

## 13. Tính toán mức song song theo ngân sách tài nguyên

Số worker nên bị giới hạn bởi tài nguyên khan hiếm nhất, không chỉ số CPU core.

Một cách ước lượng:

~~~text
workers_cpu = số CPU có thể sử dụng
workers_memory = RAM còn dành cho test / RAM trung bình mỗi test worker
workers_database = connection budget dành cho test / connection tối đa mỗi worker

workers_target <= min(
    workers_cpu,
    workers_memory,
    workers_database,
    giới hạn external service
)
~~~

Đây là mô hình ước lượng, không phải công thức bảo đảm. Cần chừa bộ nhớ cho hệ điều hành, Gradle/Maven process, metaspace, thread stack, native memory và các service chạy cùng runner.

### 13.1. Ví dụ tính bộ nhớ

Giả sử CI runner có 12 GB RAM khả dụng. Gradle daemon và các service cần khoảng 2 GB; cần chừa thêm 2 GB headroom. Mỗi test JVM có thể dùng tối đa khoảng 1.5 GB.

Ngân sách còn cho test JVM:

~~~text
12 GB - 2 GB - 2 GB = 8 GB
8 GB / 1.5 GB ≈ 5 workers
~~~

Nếu máy có 8 CPU, giới hạn theo RAM ước lượng là 5 worker, nên bắt đầu thử ở 4 hoặc 5 thay vì 8. Sau đó đo heap thực tế, GC, CPU và thời gian test để điều chỉnh.

### 13.2. Database và external quota

Giả sử test database có pool tối đa 30 connection, nhưng 5 connection cần dành cho ứng dụng và migration. Nếu mỗi worker có thể mở tối đa 4 connection, giới hạn lý thuyết là:

~~~text
(30 - 5) / 4 = 6 workers
~~~

Thực tế nên để headroom vì connection có thể tồn tại ngoài dự tính và các job khác có thể dùng chung database.

### 13.3. Oversubscription

Nếu tổng thread/process lớn hơn tài nguyên máy có thể phục vụ, hệ thống phải chuyển đổi context liên tục, GC tăng, I/O queue dài và các test chờ nhau. Khi đó, tăng worker có thể làm tổng thời gian hoàn thành dài hơn.

## 14. Đo hiệu quả trước và sau khi bật parallel execution

Đừng đánh giá hiệu quả chỉ bằng việc số worker tăng. Hãy đo:

- tổng wall-clock time;
- thời gian CPU và CPU utilization;
- peak memory và GC pause;
- số database connection và thời gian chờ pool;
- network latency và rate limit;
- thời gian setup/teardown fixture;
- số test flaky hoặc retry;
- thời gian dài nhất của từng shard;
- mức độ phân bố thời gian giữa các worker.

Ví dụ bảng đo:

| Cấu hình | Wall time | Peak RAM | CPU trung bình | Test flaky |
|---|---:|---:|---:|---:|
| 1 worker | 18 phút | 3 GB | 35% | 0 |
| 2 workers | 11 phút | 5 GB | 60% | 0 |
| 4 workers | 8 phút | 9 GB | 85% | 2 |
| 8 workers | 12 phút | OOM | 95% | 7 |

Số liệu trên chỉ là ví dụ minh họa. Nó cho thấy cấu hình nhanh nhất có thể nằm giữa mức tuần tự và mức song song tối đa. Nếu flaky test tăng, đó là tín hiệu cần kiểm tra isolation trước khi tăng tiếp.

### 14.1. Tách nhóm test theo đặc tính

Có thể chia pipeline thành:

- unit test nhanh, thuần bộ nhớ;
- unit test dùng filesystem hoặc global state;
- integration test cần database;
- test khởi chạy container/service;
- test end-to-end gọi nhiều hệ thống.

Mỗi nhóm có mức song song khác nhau. Ví dụ, unit test thuần có thể chạy nhiều worker, trong khi test end-to-end có thể chạy ít worker vì mỗi test tạo nhiều service.

## 15. Test flaky khi chạy song song

Flaky test là test có lúc pass, lúc fail trong cùng điều kiện dự kiến. Parallel execution có thể làm lộ race condition vốn bị che khi chạy tuần tự.

Nguyên nhân thường gặp:

- hai test cùng sửa dữ liệu;
- test dùng port cố định;
- shared file bị ghi đồng thời;
- static state không được reset;
- test phụ thuộc thứ tự;
- assertion dựa trên sleep hoặc timing;
- external API rate limit;
- cleanup chạy quá muộn hoặc không chạy khi fail;
- test dùng clock thực hoặc random data không được kiểm soát.

### 15.1. Không chữa flaky test bằng retry vô hạn

Retry có thể giúp phân biệt lỗi môi trường tạm thời với lỗi ổn định, nhưng không sửa race condition. Nếu bật retry, cần ghi nhận lần chạy đầu và số lần retry, theo dõi tỷ lệ flaky và có kế hoạch loại bỏ nguyên nhân.

Một test pass sau retry vẫn có thể đang tranh chấp tài nguyên và che giấu lỗi thực tế.

### 15.2. Tái hiện bằng thay đổi concurrency

Để chẩn đoán:

1. chạy test class riêng lẻ;
2. chạy nhóm test liên quan cùng nhau;
3. chạy với một worker;
4. tăng dần lên hai, bốn worker;
5. ghi lại seed, shard và worker ID nếu có randomization;
6. kiểm tra resource dùng chung và thời điểm cleanup.

Nếu lỗi chỉ xuất hiện khi chạy đồng thời, hãy tìm shared state hoặc tài nguyên bên ngoài. Không mặc định test runner bị lỗi.

## 16. Thiết kế test an toàn khi chạy đồng thời

Một test tốt có setup, hành động, assertion và cleanup rõ ràng. Để chạy song song an toàn:

1. Tạo fixture riêng cho mỗi test.
2. Tránh mutable static state.
3. Dùng @TempDir hoặc thư mục có namespace.
4. Dùng port động thay cho port cố định.
5. Tạo database/schema/tenant riêng hoặc dữ liệu có khóa test.
6. Không phụ thuộc thứ tự test.
7. Khôi phục system property, locale, timezone và global state.
8. Cleanup trong teardown/finally ngay cả khi assertion fail.
9. Mock external service hoặc giới hạn request theo quota.
10. Chỉ dùng lock cho tài nguyên không thể cô lập.
11. Ghi log worker/shard/test ID để truy vết.
12. Kiểm tra test suite ở concurrency thực tế của CI, không chỉ trên máy cá nhân.

## 17. Chẩn đoán sự cố cạnh tranh tài nguyên

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| BindException: Address already in use | Nhiều test dùng cùng port | Dùng port động và server lifecycle riêng |
| Database pool timeout | Quá nhiều test giữ connection | Giảm worker, rút ngắn thời gian giữ connection, tăng pool có kiểm soát |
| Unique constraint violation ngẫu nhiên | Test dùng chung dữ liệu hoặc ID cố định | Tạo dữ liệu riêng/namespace riêng |
| File bị ghi đè hoặc thiếu nội dung | Nhiều test ghi cùng path | Dùng temp directory hoặc file name riêng |
| Test pass riêng nhưng fail trong suite | Shared state, order dependency hoặc race | Kiểm tra static/global state, fixture và lock |
| OOM khi tăng fork | Tổng heap/native memory vượt RAM | Giảm fork/heap, chia job hoặc tăng runner capacity |
| CPU gần 100% nhưng build chậm hơn | Oversubscription hoặc contention | Giảm concurrency, đo từng nhóm test |
| HTTP 429 hoặc quota exceeded | Quá nhiều request ngoài | Mock/sandbox, rate limit hoặc giảm worker |
| Queue test nhận nhầm message | Consumer dùng chung topic/queue | Tách topic/group hoặc correlation ID |
| Chỉ CI shard lỗi | Tài nguyên giữa shard dùng chung | Namespace theo shard, tách database/account/port |
| Test treo hoặc timeout khi chạy song song | Deadlock, lock rộng hoặc resource starvation | Thu thập thread dump, xem lock order và giới hạn worker |

### 17.1. Thu thập thread dump khi test bị treo

Nếu test JVM bị treo, thread dump có thể cho thấy thread đang chờ lock, connection hoặc I/O. Cách lấy dump phụ thuộc cách build tool khởi chạy JVM và môi trường CI. Có thể dùng công cụ JDK như jcmd hoặc jstack với PID của test process khi có quyền truy cập.

Không nên kết luận deadlock chỉ từ việc một test chạy lâu. Xem thread state, stack trace và tài nguyên đang chờ.

### 17.2. Kiểm tra connection và port

Log fixture nên ghi rõ:

- test ID;
- worker/process ID;
- database/schema/tenant;
- port được cấp;
- thời điểm setup và teardown;
- số connection mở/đóng.

Thông tin này giúp xác định hai test có đang sử dụng cùng tài nguyên ngoài dự kiến không.

## 18. Chiến lược triển khai theo từng bước

Không nên bật toàn bộ concurrency cùng lúc. Một lộ trình an toàn:

**Bước 1 — Thiết lập baseline.** Chạy suite tuần tự, ghi wall time, flaky rate, memory và nhóm test chậm.

**Bước 2 — Cô lập test.** Sửa dữ liệu dùng chung, port, file, static state và cleanup trước khi tăng worker.

**Bước 3 — Song song hóa class độc lập.** Bắt đầu với hai Gradle fork hoặc hai Surefire fork; nếu dùng JUnit Jupiter, cho class chạy concurrent nhưng giữ method cùng class tuần tự.

**Bước 4 — Đo tài nguyên.** Kiểm tra RAM, CPU, DB connections, external quota và test flakiness.

**Bước 5 — Tăng có kiểm soát.** Tăng từng mức và so sánh wall time; dừng khi throughput không tăng hoặc contention tăng.

**Bước 6 — Shard test suite nếu cần.** Chia nhóm test trên nhiều CI agent bằng phân hoạch ổn định và cân bằng theo thời lượng.

**Bước 7 — Theo dõi liên tục.** Ghi nhận test flaky, thời lượng và tài nguyên sau mỗi thay đổi lớn.

## 19. Ví dụ cấu hình tổng hợp

### 19.1. Gradle: giới hạn worker và chạy class song song

build.gradle.kts:

~~~kotlin
plugins {
    java
}

tasks.test {
    useJUnitPlatform()

    // Tối đa hai test JVM cho task này.
    maxParallelForks = 2

    // Giới hạn heap cho từng test JVM.
    maxHeapSize = "1g"
}
~~~

gradle.properties:

~~~properties
org.gradle.parallel=true
org.gradle.workers.max=4
~~~

src/test/resources/junit-platform.properties:

~~~properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = same_thread
junit.jupiter.execution.parallel.mode.classes.default = concurrent
junit.jupiter.execution.parallel.config.strategy = fixed
junit.jupiter.execution.parallel.config.fixed.parallelism = 2
~~~

Cấu hình này minh họa ba lớp khác nhau: project/task scheduling, test JVM forks và JUnit class concurrency. Tổng tải thực tế còn phụ thuộc số module/task test chạy cùng lúc và cách Gradle lập lịch worker lease. Hãy đo trong CI trước khi tăng các giá trị.

### 19.2. Maven: reactor và Surefire

Lệnh build:

~~~bash
./mvnw -T 2 verify
~~~

Surefire:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <forkCount>2</forkCount>
        <reuseForks>true</reuseForks>
        <argLine>-Xms256m -Xmx1g</argLine>
    </configuration>
</plugin>
~~~

JUnit Platform properties trong src/test/resources/junit-platform.properties:

~~~properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = same_thread
junit.jupiter.execution.parallel.mode.classes.default = concurrent
junit.jupiter.execution.parallel.config.strategy = fixed
junit.jupiter.execution.parallel.config.fixed.parallelism = 2
~~~

Nếu hai module chạy đồng thời, mỗi module có thể tạo hai fork, và mỗi fork có JUnit parallelism hai. Tổng số test execution thread tiềm năng có thể cao hơn nhiều so với hai. Điều chỉnh một lớp tại một thời điểm và cân nhắc giảm fork hoặc bỏ JUnit-level concurrency cho integration test.

## 20. Bài tập thực hành

### Bài 1 — Đo Gradle test worker

Tạo project Gradle Java có một nhóm unit test. Chạy mặc định, ghi wall time. Đặt maxParallelForks bằng 2, chạy lại và so sánh thời gian, CPU, RAM. Tiếp tục với bốn worker nếu runner đủ tài nguyên.

### Bài 2 — Bật JUnit class concurrency

Thêm junit-platform.properties với parallel enabled, default same-thread và classes default concurrent. Tạo hai class test độc lập có thời gian chạy đủ dài để quan sát chúng chồng lấp. Ghi nhận thời gian hoàn thành.

### Bài 3 — Phát hiện shared static state

Tạo hai test method cùng thay đổi một static counter. Chạy tuần tự rồi chạy concurrent. Quan sát kết quả không ổn định. Sửa bằng fixture riêng hoặc thiết kế thread-safe phù hợp.

### Bài 4 — Xung đột port

Tạo hai integration test cùng khởi động server trên một port cố định. Chạy đồng thời và quan sát BindException. Chuyển sang port động được cấp bởi server rồi chạy lại.

### Bài 5 — Cô lập database

Tạo hai test cùng thao tác một bảng và cùng xóa dữ liệu. Chạy song song để quan sát lỗi. Sau đó dùng schema hoặc namespace riêng cho mỗi test/worker và so sánh.

### Bài 6 — Maven fork và reactor parallelism

Tạo Maven multi-module project. So sánh mvn verify, mvn -T 2 verify, và cấu hình Surefire forkCount lớn hơn một. Ghi lại số test JVM và tổng mức đồng thời.

### Bài 7 — CI sharding

Chia danh sách test class thành ba shard. Đảm bảo mỗi test chỉ thuộc một shard, output report không ghi đè nhau và mỗi shard có namespace dữ liệu riêng. Hợp nhất report sau khi các shard kết thúc.

### Bài 8 — Tìm điểm tối ưu

Chạy suite với 1, 2, 4 và 8 worker (trong giới hạn runner). Ghi wall time, peak RAM, CPU, DB connection và flaky rate. Chọn cấu hình có throughput tốt và kết quả ổn định.

## 21. Câu hỏi tự kiểm tra

1. Build parallelism khác test parallelism ở điểm nào?
2. Gradle maxParallelForks điều khiển đơn vị công việc nào?
3. forkEvery có tác dụng gì và chi phí của nó là gì?
4. JUnit Jupiter parallel execution được cấu hình ở đâu?
5. Vì sao nên bắt đầu bằng class concurrency trước khi bật method concurrency?
6. Maven -T khác Surefire forkCount như thế nào?
7. reuseForks=true và false ảnh hưởng isolation/process startup ra sao?
8. Vì sao số fork và số thread trong JUnit có thể nhân mức đồng thời lên?
9. CI sharding cần bảo đảm điều gì để không bỏ sót hoặc chạy trùng test?
10. Những tài nguyên ngoài JVM nào thường bị tranh chấp?
11. Vì sao port động an toàn hơn port cố định?
12. @ResourceLock bảo vệ được phạm vi nào và không bảo vệ được phạm vi nào?
13. Khi nào nên dùng @Isolated hoặc @Execution(SAME_THREAD)?
14. Làm thế nào ước lượng số worker theo CPU, RAM và database connection?
15. Vì sao tăng worker có thể làm build chậm hơn?
16. Dấu hiệu nào cho thấy test flaky do race condition?
17. Vì sao retry không thay thế việc cô lập tài nguyên?
18. Cần ghi nhận dữ liệu gì để chẩn đoán test fail chỉ trên một CI shard?

Phân phối công việc kiểm thử hiệu quả cần kết hợp mức song song phù hợp với khả năng cô lập tài nguyên. Hãy bắt đầu từ các test độc lập, giới hạn process/thread theo ngân sách CPU và RAM, tách dữ liệu cùng dịch vụ ngoài theo test hoặc shard, rồi đo hiệu quả trước khi tăng concurrency. Khi đó, pipeline có thể hoàn thành nhanh hơn mà vẫn giữ kết quả kiểm thử ổn định và có thể tái hiện.
