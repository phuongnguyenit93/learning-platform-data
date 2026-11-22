# Chạy Maven song song và đánh giá plugin không an toàn với nhiều luồng

## 1. Vì sao Maven build song song có thể nhanh hơn nhưng cũng nguy hiểm?

Khi dự án Spring Boot được chia thành nhiều Maven module, lệnh `mvn clean verify` mặc định đi qua **reactor build** và tuân thủ thứ tự phụ thuộc giữa các module. Nếu có những module **độc lập**, Maven 3 có thể xây dựng chúng **đồng thời** khi dùng tùy chọn `-T` (*thread count*). Việc này rút ngắn thời gian chờ ở dự án đa mô-đun, nhưng chỉ an toàn nếu **plugin goals, tests, file output và dịch vụ bên ngoài** có thể hoạt động đồng thời.

Điểm cần nắm:

> `mvn -T 2 clean verify` cho phép Maven dùng **hai worker thread để xử lý những module đang sẵn sàng**, không có nghĩa mọi module hay mọi test method chạy đồng thời.

Khác biệt này rất quan trọng. Maven tôn trọng quan hệ dependency ở reactor, nhưng các **side effect ngoài đồ thị** như ghi chung một file, chiếm cùng TCP port hoặc cập nhật chung một database có thể gây race condition dù mỗi module biên dịch đúng.

Bài này hướng dẫn cách chọn `-T`, đọc phản hồi của Maven về plugin goals **không được đánh dấu thread-safe**, rà soát các side effect thường gặp và đo lợi ích thật bằng một dự án Maven/Spring Boot Java 17 có thể chạy được.

### Kết quả mong đợi

Sau khi học, bạn có thể:

- Dùng đúng `mvn -T 2`, `mvn -T 1C` và `mvn -T 1.5C`.
- Giải thích reactor **dependency DAG**, điều kiện để hai module được chạy song song và giới hạn **critical path**.
- Phân biệt **Maven reactor parallelism** với **JUnit 5 test parallelism**, **Surefire forks** và việc CI chạy nhiều job.
- Đọc warning về goals không có marker `threadSafe` và tìm **plugin/version/goal đang thực thi**.
- Xem xét an toàn của plugin theo **mã, descriptor và side effect**, thay vì tin tuyệt đối vào nhãn thread-safe.
- Thử baseline serial, build parallel có kiểm soát, so sánh reports và hiệu năng.
- Thiết kế build output, test port, database và external services **độc lập giữa các module**.

## 2. Maven -T thực sự chạy song song điều gì?

### 2.1. Cú pháp command line

Tại thư mục root của một reactor Maven, trên Linux/macOS:

```bash
# Baseline: không bật reactor parallelism
./mvnw clean verify

# Tối đa 2 worker thread Maven trong reactor:
./mvnw -T 2 clean verify

# Khoảng 1 worker thread trên mỗi CPU core được Maven phát hiện:
./mvnw -T 1C clean verify

# Khoảng 1,5 worker thread trên mỗi CPU core được Maven phát hiện:
./mvnw -T 1.5C clean verify

# 4 worker thread (không phải 4 thread cho từng module):
./mvnw -T 4 clean package
```

Nếu dự án không có Maven Wrapper và máy đã cài Maven, dùng `mvn` thay `./mvnw`. Trên Windows PowerShell dùng `.\mvnw.cmd`, ví dụ:

```powershell
.\mvnw.cmd -T 2 clean verify
.\mvnw.cmd -T 1C clean verify
```

| Tùy chọn | Ý nghĩa | Ghi chú |
|---|---|---|
| Không có `-T` | Maven reactor chạy các project theo chế độ thông thường | Baseline hữu ích khi debug |
| `-T 2` | Số worker thread cố định là 2 | Dễ khống chế tài nguyên trên CI |
| `-T 4` | Số worker thread cố định là 4 | Hợp lý khi có đủ module độc lập và CPU/RAM |
| `-T 1C` | Hệ số 1 thread cho mỗi CPU core | Thread count phụ thuộc core count được Maven phát hiện |
| `-T 1.5C` | Hệ số 1,5 thread cho mỗi CPU core | Có thể oversubscribe CPU, cần đo |
| `-pl :service-app -am` | Chọn module ứng dụng **và dependency project cần thiết** | Kết hợp được với `-T` |
| `-fae` | *Fail at end*: tiếp tục các module có thể build rồi báo lỗi | Không tự làm build thành công |
| `-ff` | *Fail fast*: chính sách dừng nhanh theo reactor | Không bảo đảm các worker đã chạy dừng tức thì |

`C` ở đây là **cores multiplier**, không phải “compiler threads” hay ký hiệu CPU limit do Docker/CI tự cấu hình. Trong môi trường container, thông tin CPU Maven/JVM nhìn thấy có thể khác tài nguyên thực được cấp; hãy đo thực tế.

### 2.2. Maven reactor là một dependency graph

Xét sơ đồ:

```text
                     parent (pom)
                         |
              +----------+----------+
              |                     |
          format-lib             math-lib
              |                     |
              +----------+----------+
                         |
                     service-app
                         |
                 executable Boot JAR
```

- `format-lib` và `math-lib` **không phụ thuộc nhau**, nên đủ điều kiện build song song khi root parent đã được xử lý.
- `service-app` phụ thuộc cả hai, nên Maven **không thể hoàn tất build app trước khi các module thư viện cần thiết hoàn tất**.
- Nếu chỉ có chuỗi A → B → C → D, tăng `-T 8` không tạo ra tám việc chạy song song được vì graph không có đủ nhánh độc lập.
- Nếu có nhiều module cùng chỉ phụ thuộc vào parent, reactor có thể khai thác concurrency tốt hơn.

Các quan hệ có thể ảnh hưởng reactor ordering bao gồm **project dependency**, **plugin nằm trong reactor**, **plugin dependency**, **build extension**, **parent POM** và, khi không có ràng buộc khác, thứ tự `<modules>`. Các mục chỉ nằm trong `dependencyManagement`/`pluginManagement` **không tự tạo edge** trong reactor. Maven ưu tiên tính đúng của dependency graph, không vì `-T` mà bỏ qua phụ thuộc.

### 2.3. Công việc nào không được song song hóa tự động?

`-T` **không** có nghĩa Maven biến mọi công việc bên trong một module thành tác vụ đồng thời. Những việc sau có cơ chế riêng:

- Compiler có thể có chính sách riêng; `-T` không đồng nghĩa `javac` chạy đồng thời trên từng source file.
- Surefire/Failsafe có cấu hình **forked JVMs** hoặc execution của test framework.
- JUnit Jupiter có cấu hình **parallel execution** của chính JUnit.
- Spring Boot Maven Plugin `repackage` tạo executable JAR trong lifecycle của **module app**.
- CI có thể chạy nhiều Maven process ở nhiều job; đó là **job/process parallelism**, khác với một Maven reactor dùng `-T`.

Khi dùng `-T 4` mà có nhiều module test, **các Surefire executions ở nhiều module có thể cùng hoạt động** dù trong mỗi module test methods vẫn chạy tuần tự. Đó là một nguồn tranh chấp cổng HTTP, database, file chung và container runtime.

## 3. "Plugin thread-safe" trong Maven là gì?

Một Maven plugin chứa nhiều **Mojo** (*Maven plain Old Java Object*). Mỗi Mojo là một **goal**, chẳng hạn `compiler:compile`, `surefire:test` hoặc `spring-boot:repackage`. Plugin có thể có goals khác nhau, **không nên chỉ gán nhãn an toàn theo tên plugin** nếu chưa xem goal cụ thể được gọi.

Từ Maven 3, plugin goal có thể khai báo metadata `threadSafe` (ví dụ annotation `@Mojo(..., threadSafe = true)` khi viết plugin). Maven dùng thông tin trong plugin descriptor để nhận diện goal được tác giả **đánh dấu có hỗ trợ parallel build**.

### 3.1. Điều warning thực sự nói

Khi chạy song song, Maven có thể in cảnh báo mang ý nghĩa:

```text
Your build is requesting parallel execution, but this project contains
plugin(s) that have goals not marked as thread-safe...
```

Đây là **trích ý nghĩa thông báo**; câu chữ, danh sách plugin và cách log hiển thị phụ thuộc phiên bản Maven. Warning xuất hiện vì một hoặc nhiều goal trong execution plan **không được đánh dấu `threadSafe`**, chứ không phải Maven đã chứng minh race condition xảy ra.

**Phân biệt ba trạng thái:**

| Trạng thái | Có thể kết luận | Không thể kết luận |
|---|---|---|
| Goal đánh dấu `threadSafe=true` | Tác giả khai báo goal hỗ trợ parallel execution trong Maven reactor | Mọi cấu hình, script tùy biến, database/test cùng dùng đều tự động an toàn |
| Goal thiếu marker hoặc `threadSafe=false` | Maven có lý do cảnh báo và cần đánh giá | Goal chắc chắn gây lỗi trên mọi dự án |
| Chạy `-T` thành công một lần | Không quan sát được lỗi ở lần đó | Build đã hết race, hết flaky tests hoặc artifact hoàn toàn tái lập |

Một plugin có thể được đánh dấu thread-safe nhưng **cấu hình tại dự án** lại khiến mọi module cùng ghi `target/shared-report.json` dưới root. Hoặc code plugin dùng các static mutable fields, singleton components, non-thread-safe libraries. Marker tốt là tín hiệu tích cực, **không thay thế việc kiểm chứng side effects thực tế**.

### 3.2. Đánh giá ở cấp goal và phiên bản

Trước tiên xem **plugin goal thực sự được gọi** ở các phase như `generate-sources`, `compile`, `test`, `package`, `verify`. Thông tin thường nằm tại:

- `pom.xml` hoặc parent POM và active Maven profiles.
- `help:effective-pom` cho cấu hình sau inheritance và profile.
- Log Maven hiển thị plugin goal/version trong từng module.
- Tài liệu goal trên website chính thức của plugin (nhiều goal có phần **Attributes** ghi thread-safe).
- Plugin descriptor `META-INF/maven/plugin.xml` bên trong artifact JAR plugin (nếu cần xác minh kỹ).
- Source code/issue tracker/release notes khi warning hoặc hiện tượng race không rõ.

Ví dụ lệnh:

```bash
# Cấu hình build hiệu lực:
./mvnw help:effective-pom -Doutput=effective-pom.xml

# Mô tả goal, plugin và tham số:
./mvnw help:describe \
  -Dplugin=org.apache.maven.plugins:maven-jar-plugin \
  -Dgoal=jar -Ddetail

# Xem plugin Boot goal cụ thể (không giả định toàn bộ goal chung metadata):
./mvnw help:describe \
  -Dplugin=org.springframework.boot:spring-boot-maven-plugin \
  -Dgoal=repackage -Ddetail
```

Trên Windows, thay `./mvnw` bằng `.\mvnw.cmd`; có thể viết lệnh một dòng. `help:describe` **là goal trợ giúp/aggregator** và bản thân nó có thể không được đánh dấu thread-safe; nên chạy lệnh phân tích này **không kèm `-T`**. Nếu output help plugin không nêu rõ thread-safety, tiếp tục đọc tài liệu goal và plugin descriptor tương ứng phiên bản; không suy từ việc help không in cờ.

Ví dụ kiểm tra descriptor bằng JDK `jar` (phải có JAR plugin tại đường dẫn đã giải quyết):

```bash
# Đây là tên JAR ví dụ sau khi Maven đã tải plugin 3.5.16:
jar tf "$HOME/.m2/repository/org/springframework/boot/spring-boot-maven-plugin/3.5.16/spring-boot-maven-plugin-3.5.16.jar"
```

Trong artifact Maven plugin hợp lệ có `META-INF/maven/plugin.xml`. Có thể trích vào thư mục riêng rồi tìm `<goal>repackage</goal>` và `<threadSafe>...` **trong cùng phần tử `<mojo>`**, thay vì chỉ grep toàn bộ file và gán nhầm flag của goal khác. Đường dẫn `~/.m2` là **mặc định phổ biến**, có thể khác nếu `settings.xml`/`-Dmaven.repo.local` thay local repository.

### 3.3. Checklist đánh giá plugin có thực sự an toàn

Cần kiểm tra cả **metadata, implementation và môi trường**:

1. **Mutable static state**: plugin có static map/list/cache không đồng bộ không?
2. **Singleton/service components**: các object được chia sẻ giữa worker threads có mutable state không?
3. **Thread-unsafe library**: plugin gọi formatter/archiver/helper có dùng state không bảo vệ không?
4. **Output path**: mỗi module ghi vào `${project.build.directory}` riêng hay mọi module cùng ghi vào một file ở root?
5. **Temp files**: tên có duy nhất trên từng module/goal invocation không?
6. **Global resources**: TCP port, H2 file database, Docker container name, Git index, lockfile, local repository metadata hay cache riêng?
7. **Forked process**: goal có spawn subprocess, script hoặc external tool đồng thời được không?
8. **Lifecycle side effect**: goal tạo/sửa parent POM, generated sources của module khác, version file hoặc tài nguyên dùng chung không?
9. **Reproducibility**: đầu ra có phụ thuộc vào thứ tự scheduling, system clock, random seed hoặc thứ tự duyệt file không?
10. **Error handling**: khi nhiều module cùng fail, plugin có để lại file output tạm hoặc lock gây hỏng build sau không?

**Điểm phân biệt:** Maven core có cơ chế quản lý reactor concurrency, nhưng **không thể bảo vệ hoàn toàn các file/socket/database ngoài mô hình dependency graph**.

## 4. Tình huống rủi ro: cùng file, cùng port và shared resources

### 4.1. Hai module cùng ghi một file bên ngoài thư mục build riêng

Giả sử plugin tùy biến `generate-report` của cả `format-lib` và `math-lib` được cấu hình xuất ra:

```text
multi-module/
├── format-lib/target/       (đầu ra riêng)
├── math-lib/target/         (đầu ra riêng)
└── target/
    └── all-reports.json     (cả hai module cùng ghi)
```

Nếu mỗi execution ghi đè `root/target/all-reports.json`, dưới `-T 2` hai module có thể:

- Mất dữ liệu của nhau do cùng ghi file.
- Gặp `FileSystemException`/lock trên Windows.
- Đọc file khi module khác mới ghi một phần.
- Để output không tái lập; lần nào build trước thì kết quả khác.

**Cách thiết kế tốt hơn:**

- Mỗi module xuất file vào `${project.build.directory}/reports/report.json`.
- Tạo một **bước aggregation riêng** sau khi các module đã hoàn thành, không để các module cùng cập nhật file tổng hợp.
- Nếu plugin buộc dùng đường dẫn chung, tách phase/job chạy **tuần tự** hoặc thiết kế cơ chế lock nhất quán và kiểm thử thật.
- Không dùng tên file cố định ở `/tmp` chung giữa các project/job; cần không gian tên riêng theo module/CI run.

Ví dụ cấu hình plugin **minh họa**, không phải một plugin có thật để copy chạy trực tiếp:

```xml
<configuration>
    <!-- Chọn một output riêng của mỗi Maven project -->
    <outputFile>${project.build.directory}/reports/report.json</outputFile>
</configuration>
```

Vì property `project.build.directory` mặc định là `target` **theo module**, cách này an toàn hơn việc dùng `${maven.multiModuleProjectDirectory}/target/report.json` để tất cả module ghi chung. Dù vậy, nếu module bị cấu hình `build.directory` giống nhau hoặc plugin bỏ qua `outputFile`, vẫn phải kiểm tra hành vi thật.

### 4.2. Hai bộ integration tests cùng mở một TCP port

Ví dụ hai module đều chạy ứng dụng kiểm thử trên port `18080`. Khi `-T 2` khiến test của hai module chồng thời gian, một trong hai có thể gặp:

```text
java.net.BindException: Address already in use
```

Đây là **ví dụ lỗi có thể xảy ra**, không phải output tất yếu của mọi lần Maven chạy. Nếu một test dùng Spring Boot embedded web server, có thể cấu hình:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ExampleIntegrationTest {
    // Kiểm thử theo port động được cấp thực tế.
}
```

Đoạn trên là **một class minh họa**, chưa có test method và không phải file runnable độc lập. Khi cần gọi HTTP, inject địa chỉ/port thực của test thay vì hardcode 18080. Với hệ thống bên ngoài test framework, có thể yêu cầu OS cấp **port 0** rồi đọc port thực tế.

Các trường hợp tương tự: Kafka broker/test container cố định port, database schema dùng chung, file SQLite/H2, Redis key không có namespace theo module. Đừng chỉ tăng timeout để che race.

### 4.3. Shared database hoặc test data

Hai module có thể cùng:

- Xóa bảng hoặc chạy migration trên một database integration dùng chung.
- Reset dữ liệu `users`, trong khi module kia đang assert.
- Tạo Kafka topic hoặc Docker container cùng tên.
- Dùng credentials và external API có giới hạn rate/concurrency.

Giải pháp: test database/schema/container **riêng theo module/run**, dữ liệu có namespace, transaction rollback phù hợp, tài nguyên tạm có tên duy nhất. Nếu hạ tầng test không cô lập được, chạy phần kiểm thử đó **tuần tự**.

### 4.4. Nhiều tiến trình Maven trong cùng workspace

Khác với một lệnh `mvn -T 2`, CI có thể chạy **hai lệnh Maven độc lập** trên cùng checkout. Hai process sẽ có các biến số riêng:

- Có thể cùng chạy `clean` và xóa `target` của nhau.
- Có thể cùng deploy/install artifact có cùng GAV nhưng khác bytes.
- Cùng dùng temp files, generated sources hoặc repository file trong quá trình publishing.
- Có thể tranh cổng, database và Docker.

`@threadSafe` cho Maven Mojo **không phải** cam kết mọi plugin an toàn với **nhiều Maven process** dùng cùng workspace. Dùng workspace tách biệt cho các CI jobs; nếu dùng local Maven repository dùng chung, đánh giá cache behavior và tránh đồng thời ghi artifact mutable/SNAPSHOT sai quy trình.

## 5. Maven song song khác Surefire/JUnit chạy test song song

Đây là một nguồn nhầm lẫn rất phổ biến.

| Cơ chế | Điều khiển bằng | Đơn vị chạy song song | Nguy cơ tiêu biểu |
|---|---|---|---|
| **Maven reactor parallelism** | `mvn -T 2 ...` | Các **module độc lập** | Plugin concurrent executions, port/file/db giữa module |
| **Surefire forked JVMs** | `forkCount`, `reuseForks` | Test JVM process trong module | RAM cao, tài nguyên chung giữa forks |
| **JUnit Jupiter parallel execution** | `junit.jupiter.execution.parallel.enabled=true` và execution modes | Test class/method theo engine JUnit | Shared test fixtures, static state, ordering |
| **TestNG/JUnit4 provider parallel** | Provider/config của Surefire phù hợp | Test classes/methods theo framework | State/thread safety trong test |
| **CI pipeline parallel jobs** | Cấu hình GitHub Actions/Jenkins/GitLab/... | Các job/process độc lập | Workspace, port, artifact repository, rate limits |

Nếu dùng `-T 4` và trong các module đồng thời cấu hình nhiều Surefire forks, số JVM chạy cùng lúc có thể tăng mạnh; **không giả định CPU/RAM chỉ tương ứng bốn luồng**. Giới hạn concurrency tổng thể của pipeline bằng test matrix thực tế.

### 5.1. Surefire/JUnit Jupiter không tự bật song song test

Với phiên bản Surefire/JUnit 5 phù hợp, test methods **không tự chạy song song** chỉ vì Maven dùng `-T`. Nếu cần song song **bên trong** JUnit Jupiter, có thể đặt cấu hình JUnit Platform tại `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
```

Đây là **một lựa chọn riêng**, không phải thiết lập nên bật mặc định. Khi bật, test classes/methods cần thread-safe, không dùng trạng thái mutable chung chưa bảo vệ. Cấu hình JUnit 5 được xử lý ở test engine; Surefire docs về tùy chọn `parallel` có **ngữ nghĩa theo provider/framework**. Không sao chép cấu hình dành cho JUnit 4.7 provider sang JUnit Jupiter mà cho rằng tương đương.

### 5.2. Khi nào chỉ nên chạy parallel reactor, không parallel tests?

Dự án có nhiều thư viện độc lập nhưng trong từng module có integration tests dùng shared fixtures: có thể hưởng lợi từ `-T 2` nhưng **phải cô lập test resources giữa các module**. Nếu test resources chưa cô lập, hãy giữ serial khi chạy `verify` cho tới khi test infrastructure được sửa. Không dùng `-DskipTests` để báo “parallel build xanh” rồi suy chất lượng đã được xác minh.

## 6. Dự án thực hành Maven reactor + Spring Boot Java 17

Ta xây dựng **bốn Maven projects**: root parent, hai JAR library độc lập và một Spring Boot app phụ thuộc cả hai. Bài này có mã chạy được và unit tests để so kết quả **serial/parallel**.

Dùng Java **17+**, Maven 3.9.x phù hợp hoặc Maven Wrapper đã được dự án cấu hình, Spring Boot **3.5.16** làm bản pin ví dụ. Không dùng bản ví dụ để khẳng định đây là Spring Boot mới nhất. Trong lần build đầu có thể cần tải plugin/dependencies; hãy làm nóng cache trước khi đo thời gian.

### 6.1. Cây thư mục

```text
parallel-build-lab/
├── pom.xml
├── mvnw                          (nếu đã có Maven Wrapper)
├── mvnw.cmd                      (nếu đã có Maven Wrapper)
├── .mvn/wrapper/...              (nếu đã có Maven Wrapper)
├── format-lib/
│   ├── pom.xml
│   ├── src/main/java/com/example/format/GreetingFormatter.java
│   └── src/test/java/com/example/format/GreetingFormatterTest.java
├── math-lib/
│   ├── pom.xml
│   ├── src/main/java/com/example/math/SumCalculator.java
│   └── src/test/java/com/example/math/SumCalculatorTest.java
└── service-app/
    ├── pom.xml
    └── src/main/java/com/example/app/ParallelLabApplication.java
```

Wrapper không tự xuất hiện chỉ vì tạo POM. Nếu chưa có wrapper, dùng `mvn` đã cài. File project gồm đúng ba modules được khai báo dưới root POM; không yêu cầu thay đổi build tool Gradle hay dùng thêm script tự động.

### 6.2. POM root: aggregator + parent

Tạo `pom.xml` ở root:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>parallel-build-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>format-lib</module>
        <module>math-lib</module>
        <module>service-app</module>
    </modules>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
</project>
```

Root có `<packaging>pom</packaging>` nên đóng vai trò aggregator/parent, không tạo executable JAR. Kế thừa Spring Boot Starter Parent để lấy dependency/plugin management; root **không tự khai báo Spring Boot Maven Plugin trong `<build><plugins>`**. Nếu đặt plugin Boot vào root rồi để plugin declaration được các con kế thừa, có thể dẫn đến goal `repackage` được áp dụng cả cho thư viện không có `main`. Chỉ app mới khai báo plugin đó ở mục 6.5.

### 6.3. format-lib: POM + Java class + unit test

Tạo `format-lib/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>parallel-build-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>format-lib</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`format-lib/src/main/java/com/example/format/GreetingFormatter.java`:

```java
package com.example.format;

public final class GreetingFormatter {
    private GreetingFormatter() {
    }

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

`format-lib/src/test/java/com/example/format/GreetingFormatterTest.java`:

```java
package com.example.format;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingFormatterTest {
    @Test
    void formatsGreeting() {
        assertEquals("Hello, Java!", GreetingFormatter.greet("Java"));
    }
}
```

Đây là module Java thông thường, có **một unit test JUnit Jupiter** và không có `main`, không có Boot packaging plugin. `junit-jupiter` nhận phiên bản được quản lý bởi Spring Boot Parent; test dependency có scope `test` nên không nằm trong JAR thư viện cuối.

### 6.4. math-lib: độc lập với format-lib

Tạo `math-lib/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>parallel-build-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>math-lib</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`math-lib/src/main/java/com/example/math/SumCalculator.java`:

```java
package com.example.math;

public final class SumCalculator {
    private SumCalculator() {
    }

    public static int add(int left, int right) {
        return Math.addExact(left, right);
    }
}
```

`math-lib/src/test/java/com/example/math/SumCalculatorTest.java`:

```java
package com.example.math;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SumCalculatorTest {
    @Test
    void addsTwoIntegers() {
        assertEquals(42, SumCalculator.add(20, 22));
    }
}
```

Module này **không import từ format-lib**, nên Maven có thể xử lý hai library projects đồng thời khi có `-T` và còn worker rảnh. `Math.addExact` có mặt trong Java 17; với đầu vào 20 và 22, kết quả chính xác là 42.

### 6.5. service-app: có dependency vào cả hai module

Tạo `service-app/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>parallel-build-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>service-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>format-lib</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>math-lib</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`${project.version}` ở đây được Maven nội suy thành `1.0.0` trong POM module. `spring-boot-starter` cung cấp runtime Spring Boot; không dùng `spring-boot-starter-web` nên app minh họa là chương trình console.

Với parent `spring-boot-starter-parent`, việc khai báo `spring-boot-maven-plugin` trong app đủ để kích hoạt cấu hình execution `repackage` do parent quản lý. Không khai báo plugin này ở library. `spring-boot:run` là lệnh phục vụ phát triển, không phải goal tự được gọi trong `mvn verify`.

`service-app/src/main/java/com/example/app/ParallelLabApplication.java`:

```java
package com.example.app;

import com.example.format.GreetingFormatter;
import com.example.math.SumCalculator;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ParallelLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(ParallelLabApplication.class, args);
    }

    @Bean
    CommandLineRunner showResult() {
        return args -> {
            System.out.println(GreetingFormatter.greet("Java"));
            System.out.println("answer=" + SumCalculator.add(20, 22));
        };
    }
}
```

Ứng dụng gọi hai JAR thư viện độc lập. Chỉ **service-app** có `main` và Boot plugin, do đó `repackage` được thiết kế cho đúng module.

### 6.6. Chạy baseline và song song

Từ root `parallel-build-lab`:

```bash
# Baseline serial, build cả các module và test:
./mvnw clean verify

# Tái chạy cùng reactor với 2 worker:
./mvnw -T 2 clean verify

# Kiểm tra app và các project nó cần:
./mvnw -T 2 -pl :service-app -am clean verify

# Chạy ứng dụng được đóng gói:
java -jar service-app/target/service-app-1.0.0.jar
```

Thay `./mvnw` bằng `mvn` nếu dự án không có Maven Wrapper; PowerShell dùng `.\mvnw.cmd`. Chọn lệnh phù hợp cho từng lần chạy chứ không cần lặp cả ba build để tạo artifact. Khi thực thi thành công, **hai dòng do ứng dụng in** chính xác là:

```text
Hello, Java!
answer=42
```

Console còn có thể có Spring Boot banner/startup logs tùy môi trường. Không khẳng định **toàn bộ stdout** chỉ gồm hai dòng trên.

### 6.7. Diễn giải output Maven

Với reactor cấu hình đúng, Maven có thể in danh sách project và `Reactor Summary` như:

```text
parallel-build-lab ................. SUCCESS
format-lib ......................... SUCCESS
math-lib ........................... SUCCESS
service-app ........................ SUCCESS
BUILD SUCCESS
```

Đây là **phần minh họa trạng thái cần tìm**, không phải nguyên văn output (thời gian, thứ tự/độ rộng tên và log Maven thay đổi). Khi bật `-T 2`, log của `format-lib` và `math-lib` có thể **xen kẽ**, vì cả hai project được build ở các worker khác nhau. `Reactor Summary` có thể vẫn in theo thứ tự reactor ổn định; không dùng thứ tự log như bằng chứng về dependency scheduling.

**Quan sát quan trọng:** nếu `format-lib` và `math-lib` đều xử lý đồng thời mà plugin/test không có shared side effect, `service-app` chỉ chạy khi các library dependencies đã sẵn sàng. Đây là concurrency ở **module level**; không bảo đảm tốc độ gấp hai.

### 6.8. Kiểm tra artifact thật sau build

```bash
# JAR library thường:
jar tf format-lib/target/format-lib-1.0.0.jar
jar tf math-lib/target/math-lib-1.0.0.jar

# Spring Boot executable JAR:
jar tf service-app/target/service-app-1.0.0.jar
```

Trong Boot executable archive, cần tìm các entry:

```text
BOOT-INF/classes/com/example/app/ParallelLabApplication.class
BOOT-INF/lib/format-lib-1.0.0.jar
BOOT-INF/lib/math-lib-1.0.0.jar
```

Ở library JARs, class nằm tại root package như `com/example/format/GreetingFormatter.class` hoặc `com/example/math/SumCalculator.class`. Sự khác biệt cho thấy reactor thực hiện packaging theo từng module; `-T` không thay đổi ngữ nghĩa của một module thư viện thành Boot JAR.

## 7. Khi Maven cảnh báo một goal không thread-safe

Giả sử project thực tế có plugin cũ hoặc custom plugin gắn vào `generate-resources`. Khi chạy:

```bash
./mvnw -T 2 clean verify
```

và thấy warning plugin không được đánh dấu thread-safe, hãy áp dụng **quy trình có bằng chứng**:

1. **Ghi đúng plugin coordinates**: `groupId:artifactId:version` của plugin được cảnh báo, và goal trong execution plan.
2. **Xác định module và phase** nơi goal chạy (log hoặc effective POM).
3. **Đọc tài liệu goal/plugin descriptor** đúng version, không tra nhầm version khác.
4. **Tìm side effects** như file root, shared database, port cố định, Docker image tag, temp dir.
5. **Kiểm tra release notes**: phiên bản mới đã sửa thread-safety hay bug archive/cache chưa?
6. **So với serial build** bằng cùng JDK, dependency versions, Maven settings, active profiles.
7. **Thử parallel giới hạn** như `-T 2` trước, chưa bật ngay `-T 2C` trong CI.
8. **Kiểm tra artifacts/reports**, không chỉ dòng `BUILD SUCCESS`.
9. **Giữ serial cho giai đoạn rủi ro** nếu chưa chứng minh được an toàn.
10. **Mở issue cho plugin** hoặc sửa custom Mojo nếu lỗi có thể tái hiện; không mặc định đây là bug của Maven core.

### Chọn giải pháp phù hợp

| Phát hiện | Cách xử lý ưu tiên |
|---|---|
| Goal cũ đã có phiên bản mới hỗ trợ thread-safe | Nâng plugin có kiểm thử; pin version trong `pluginManagement` |
| Goal thiếu `threadSafe` nhưng logic đọc-only, không side effect chung | Kiểm tra implementation, test parallel lặp lại, yêu cầu tác giả bổ sung marker nếu hợp lệ |
| Goal ghi cùng file cho mọi module | Chuyển output vào `${project.build.directory}` của mỗi module hoặc aggregation step sau reactor |
| Goal gọi API/service không hỗ trợ concurrency | Chạy phần đó tuần tự, giới hạn request, hoặc dùng tài nguyên riêng |
| Goal tạo test database dùng chung | Tách schema/container/data, hoặc serial integration tests |
| Goal đóng gói/sửa archive của module khác | Sửa ranh giới module; mỗi goal chỉ thao tác artifact của module mình |
| Plugin custom không rõ thread safety | Kiểm tra static/singleton state, lock strategy và dependencies rồi đánh giá |
| Không thể chứng minh an toàn kịp release | Dùng **serial `mvn clean verify`** cho đường release |

**Quan trọng:** đừng dùng `-Dmaven.test.skip=true` hoặc `-DskipTests` chỉ để tránh warning test rồi kết luận an toàn. Những cờ đó thay đổi nội dung công việc được kiểm chứng, có thể che một lỗi nghiêm trọng.

### Có nên "tắt parallel riêng goal X" bằng một dòng cấu hình Maven?

Không có một cờ command line Maven 3 phổ quát kiểu `-T 4 --sequential-plugin=X` để mọi goal được tự phân đoạn tuần tự trong cùng reactor. Nếu goal không an toàn:

- Sửa plugin/configuration hoặc nâng phiên bản.
- Chuyển công việc thành **bước riêng** có điều phối, ví dụ aggregation sau khi các modules đã xuất output độc lập.
- Sử dụng profile phù hợp để build nhanh các phase an toàn, sau đó gọi goal/phase rủi ro **theo một quy trình serial được thiết kế rõ**.
- Nếu chưa thể tách thực sự, giữ toàn bộ build serial cho đến khi sửa.

Không tự nghĩ rằng Maven sẽ tự khóa mọi goal không được đánh dấu thread-safe. Warning là tín hiệu cần đánh giá, không phải bảo đảm Maven sẽ serialize những goal đó.

## 8. Đo hiệu năng đúng cách, không chỉ nhìn cảm giác "nhanh"

Không phải build nào cũng nhanh hơn khi thêm threads. Tốc độ phụ thuộc:

- Số module độc lập và tỷ lệ công việc nằm trên **critical path**.
- CPU/RAM/IO, disk throughput, network artifact repository, container quotas.
- Compiler/test JVM startup và memory footprint.
- Maven daemon/JDK warmup, cache dependency và plugin resolution.
- Plugin serialization hay tài nguyên shared; lock contention.
- Build có chạy test/failsafe, quality checks, code generation, image build như nhau không.

### 8.1. Benchmark cơ bản

Trên Linux/macOS, làm nóng dependency cache (lần đầu tải dependencies không phải benchmark công bằng), rồi chạy nhiều lần với **cùng command goals**:

```bash
# Warm-up build, không dùng làm số liệu chính:
./mvnw clean verify

# Benchmark serial:
time ./mvnw clean verify

# Benchmark 2 workers:
time ./mvnw -T 2 clean verify

# Benchmark theo CPU:
time ./mvnw -T 1C clean verify
```

PowerShell:

```powershell
Measure-Command { .\mvnw.cmd clean verify }
Measure-Command { .\mvnw.cmd -T 2 clean verify }
Measure-Command { .\mvnw.cmd -T 1C clean verify }
```

Lệnh `Measure-Command` đo thời gian thực thi, nhưng **đừng chỉ nhìn Duration**: vẫn phải kiểm tra logs, exit status, test counts và các artifact được tạo. Các runs khác nhau nên dùng cùng JDK/Maven version, flags, profiles, mạng/cache, mục tiêu `clean verify` và CPU allocation. Làm ít nhất vài lần mỗi cấu hình, đổi thứ tự chạy hoặc lấy median để giảm ảnh hưởng warmup và noise.

**Công thức đánh giá:**

```text
speedup = thời gian serial / thời gian parallel

speedup > 1: lần chạy parallel nhanh hơn
speedup = 1: tốc độ tương đương
speedup < 1: parallel chậm hơn
```

Ví dụ minh họa: serial `120 s`, parallel `90 s` ⇒ speedup `120/90 ≈ 1,33`; đó chỉ là số giả định để hiểu phép tính, **không phải cam kết Maven có hiệu năng đó**.

### 8.2. Vì sao -T 1C đôi khi tệ hơn -T 2?

- CI cấp nhiều logical cores nhưng RAM ít; mỗi module chạy tests/fork JVM riêng.
- Parallel builds tăng pressure lên CPU, garbage collection và filesystem.
- Thư viện trong reactor có graph phụ thuộc dài; nhiều workers ngồi chờ.
- Plugin hoặc service bên ngoài tạo bottleneck; tăng thread gây lock/connection contention.
- Nhiều test containers cùng startup khiến Docker daemon/registry quá tải.

**Chọn concurrency bằng số đo và độ ổn định**, không theo giá trị lớn nhất mà phần cứng chấp nhận. Trong nhiều pipeline, `-T 2` hoặc `-T 1C` đủ để thử; với build nhỏ, serial có thể tốt hơn.

## 9. Kiểm tra kết quả ngoài BUILD SUCCESS

Một build song song thành công phải vượt cả **functional correctness** và **artifact correctness**:

| Đối tượng | Cách kiểm tra |
|---|---|
| Reactor modules | `Reactor Summary` có đúng mọi module cần build, không có `SKIPPED` ngoài ý muốn |
| Unit tests | Số test pass/fail/skipped từ `target/surefire-reports` của **mỗi module** |
| Integration tests | Failsafe `verify` và `target/failsafe-reports` nếu dự án đã cấu hình IT |
| Generated sources | File nằm trong module tương ứng, không bị xóa/ghi đè từ module khác |
| Executable JAR | `jar tf` cho `BOOT-INF/classes`, `BOOT-INF/lib` và manifest phù hợp |
| Runtime smoke test | `java -jar service-app/target/service-app-1.0.0.jar` chạy đúng |
| Reproducibility | Checksum/so sánh archive theo chính sách reproducible-build của dự án |
| Shared resources | Không còn port collision, database cross-test pollution, file race |
| Warning log | Không bỏ qua warning plugin hoặc các test failures xuất hiện ngẫu nhiên |

### Thử một pipeline đối chiếu

Giả sử mục tiêu CI là build toàn bộ reactor:

```bash
# 1. Xác nhận baseline serial:
./mvnw clean verify

# 2. Chạy parallel có kiểm soát:
./mvnw -T 2 clean verify

# 3. Kiểm tra artifact ứng dụng:
java -jar service-app/target/service-app-1.0.0.jar
```

Sau đó so reports. Với dự án thực, có thể chạy build song song lặp lại để phát hiện flaky behavior; nếu xuất hiện lỗi không ổn định, thu thập logs và report **trước khi xóa target/**. Không chốt release dựa trên một lần parallel pass khi baseline/parallel cho ra dependency hoặc artifact khác nhau.

### Log khó đọc khi xen kẽ

Trong reactor parallel build, log module A và B có thể chen nhau. Để chẩn đoán:

- Tìm prefix plugin goal/module, `Reactor Summary` và lỗi đầu tiên liên quan mã dự án.
- Giữ log theo job/module nếu CI hỗ trợ; có thể chạy lại **module lỗi ở serial mode** để giảm noise.
- Dùng `-pl :module-name -am` nếu module cần reactor dependencies.
- Sử dụng `-X` khi cần chi tiết Maven internals, nhưng log debug có thể chứa path, settings, URL nội bộ; không chia sẻ công khai nếu chưa rà soát.
- Không đọc thứ tự từng dòng console như timeline chính xác của các worker.

## 10. Nối với Spring Boot Maven Plugin

Trong Spring Boot multi-module, nên để **module library** chỉ dùng JAR packaging bình thường, còn **module app** khai báo Spring Boot Maven Plugin để `repackage` executable JAR.

Điều đó giảm rủi ro:

- Library không bị ép tìm `main()` hoặc ghi cùng kiểu executable artifact.
- App có một đường packaging rõ ràng sau khi Maven đã xử lý các dependent modules.
- Không nhiều app/library cùng sửa một artifact ở `target` root.
- Các profile/chính sách build ảnh hưởng phần nào được xác định theo module.

**Không khẳng định mọi goal của Spring Boot Maven Plugin đều có thread-safety giống nhau.** `repackage`, `run`, `build-image` hoặc `process-aot` có vòng đời, I/O và side effect khác nhau; phải xem đúng **phiên bản/goal** và cách dùng của project.

### spring-boot:run không phải benchmark của -T build

`spring-boot:run` khởi động ứng dụng để phát triển và có thể giữ process hoạt động cho tới khi được dừng. Nó **không phải** một goal nên gắn vào `mvn -T ... verify` để đo build throughput. Với mục tiêu đo build, dùng `clean test`, `clean package` hoặc `clean verify` cùng policy ở cả serial và parallel.

`spring-boot:repackage` tạo executable JAR/WAR từ archive đã do lifecycle `package` sinh ra. Nếu một custom plugin khác sửa cùng file `target/app.jar` trong cùng phase mà không có thứ tự rõ, đó là lỗi phối hợp plugin dù có hay không có `-T`. Định nghĩa execution rõ ràng và để mỗi module sở hữu output của chính nó.

### Docker/build-image và tài nguyên ngoài

Nếu CI chạy `spring-boot:build-image` cho nhiều ứng dụng, chúng có thể:

- Truy cập chung Docker/Podman daemon và buildpack cache.
- Tạo images cùng tag khi group/artifact/version đặt sai.
- Cạnh tranh disk/network/cache layer.
- Dùng credentials, environment hoặc repository rate limits.

Các side effect này cần chính sách CI riêng. Không suy chỉ từ `@threadSafe` của một goal rằng Docker daemon hoặc registry có đủ isolation.

## 11. Quy tắc đưa -T vào dự án thật

Có thể chọn lộ trình **tăng dần**:

### Giai đoạn 1 — Lập baseline đúng

Chạy serial `mvn clean verify` với cùng Java/Maven/settings. Bảo đảm không có test fail, dependency resolution không có lỗi và executable artifact chạy được. Ghi lại thời gian build sau warmup.

### Giai đoạn 2 — Thử mức song song nhỏ

Chạy `mvn -T 2 clean verify`. Đọc các warning plugin, báo cáo Surefire/Failsafe và kiểm tra artifact thực tế. Nếu báo lỗi plugin không thread-safe, không nâng thread count trước khi xử lý.

### Giai đoạn 3 — Phân loại các điểm không an toàn

Tìm plugin goals không đánh dấu `threadSafe`; kiểm tra static/singleton state, output files, temp directory, test ports và external dependencies. Phân loại rủi ro có thể khắc phục bằng **module-specific output**, **resource isolation**, **plugin update** hay phải **serialize**.

### Giai đoạn 4 — Benchmark và chọn cấu hình CI

So thời gian serial với `-T 2`, `-T 1C` trên phần cứng CI thật. Ưu tiên cấu hình **ổn định**, không flake và có tốc độ tốt; đừng dùng mức luồng tối đa chỉ vì một lần build nhanh.

### Giai đoạn 5 — Bảo vệ đường release

Đảm bảo job release chạy toàn bộ tests/quality gates bắt buộc, không dùng skip flags để che lỗi. Với plugin chưa được chứng minh an toàn hoặc test environment không cô lập, **giữ build release serial** hoặc tách stages an toàn/rủi ro có xác minh.

## 12. Các lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
|---|---|---|
| Maven in warning not marked thread-safe | Goal thiếu `threadSafe` metadata | Xác định plugin/version/goal, xem descriptor/docs, kiểm tra side effects |
| `-T 8` không nhanh hơn `-T 2` | Module graph ít nhánh hoặc tài nguyên bão hòa | Phân tích critical path, CPU/RAM/IO, benchmark |
| Build parallel fail nhưng serial pass | Race trong plugin, test port, file/database chung hoặc thứ tự không được mô hình hóa | Thu log/reports, cô lập resource, chạy lại có kiểm soát |
| `Address already in use` | Test modules cùng dùng một port | Dùng dynamic port hoặc serial test stage |
| Generated file bị mất/ghi thiếu | Multiple modules ghi cùng output root | Dùng `${project.build.directory}` của từng module, aggregate sau |
| `FileSystemException`/file lock ở Windows | Đồng thời cập nhật file/shared cache | Đổi output path, giảm concurrency, tách workspace |
| `OutOfMemoryError` khi `-T 1C` | Nhiều Maven workers và forked test JVMs | Hạ `-T`/`forkCount`, tăng RAM theo đo đạc |
| App Boot JAR thiếu module library | POM không khai báo project dependency hoặc packaging sai | So reactor deps, `dependency:tree`, `BOOT-INF/lib` |
| `NoClassDefFoundError` chỉ ở artifact parallel | Có thể artifact stale/hỏng hoặc dependency/packaging issue | Rebuild sạch serial và parallel, so archive, xác định root cause |
| Test counts khác nhau giữa hai cách build | Test discovery/filter/skip/cache hoặc race | So surefire-reports từng module; không chỉ xem BUILD SUCCESS |
| Nhiều version plugin khác nhau giữa module | Parent/pluginManagement/profile thiếu thống nhất | Pin versions, đọc effective POM đúng module |
| Maven log lộn xộn | Workers xen kẽ stdout | Xem Reactor Summary, module/report, log CI đã group |
| `spring-boot:run` không kết thúc | App development đang chạy như server | Không benchmark với goal long-lived; dùng package/verify |
| Image build gây timeout/đụng tag | Docker/buildpack cache và tags shared | Isolation theo app/run, serial hóa cần thiết |
| CI chạy nhiều Maven jobs cùng thư mục | Hai process xóa/ghi `target` nhau | Tách checkout/workspace cho từng job |
| Plugin đánh dấu threadSafe nhưng vẫn race | Marker không chứng minh cấu hình test/external service an toàn | Audit side effects và mở issue có testcase tái hiện |

## 13. Checklist cuối bài

- [ ] Đã xác định dự án là **multi-module reactor** và các module độc lập.
- [ ] Hiểu `-T 2` và `-T 1C` giới hạn **worker threads**, không ép mọi test method chạy song song.
- [ ] Hiểu module có dependency phải đợi project được yêu cầu trong graph.
- [ ] Biết tra `help:effective-pom` và `help:describe` **không kèm -T** khi phân tích plugin.
- [ ] Đã xác định đúng goal/version và metadata `threadSafe`; không đánh giá theo tên plugin chung.
- [ ] Đã kiểm tra file/temp/port/database/Docker/cache có được chia sẻ giữa modules không.
- [ ] Đã tách đầu ra về `${project.build.directory}` từng module hoặc aggregation stage.
- [ ] Không nhầm Maven `-T` với Surefire `forkCount` hoặc JUnit 5 parallel execution.
- [ ] Đã test baseline serial trước khi tăng worker threads.
- [ ] Đã đọc mọi warnings và test reports, không dựa vào một lần `BUILD SUCCESS`.
- [ ] Đã xem Boot executable JAR và các JAR library trong `BOOT-INF/lib`.
- [ ] Đã benchmark nhiều lần với cùng phase/test policy và phần cứng.
- [ ] Nếu plugin/test chưa chứng minh an toàn, vẫn dùng serial cho bản release.
- [ ] Không dùng skip flags/ignore failures để đổi sự ổn định lấy vẻ ngoài build xanh.

**Kết luận:** Maven `-T` là công cụ tăng tốc build ở **cấp Maven reactor module**. Maven giữ dependency ordering nhưng không thể tự sửa plugin goal không thread-safe, file output dùng chung hoặc test tranh tài nguyên. Quy trình đúng là **xác nhận graph → xem plugin goal metadata → audit side effects → thử `-T 2` → so reports/artifacts → benchmark → chọn chính sách CI an toàn**.

### Tài liệu tham khảo chính thức

- [Apache Maven — Parallel Builds in Maven 3](https://cwiki.apache.org/confluence/display/MAVEN/Parallel+builds+in+Maven+3)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven Plugin API — plugin descriptor và threadSafe](https://maven.apache.org/ref/3.9.16/maven-plugin-api/plugin.html)
- [Apache Maven Help Plugin — help:describe](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html)
- [Apache Maven Surefire — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Apache Maven Surefire — surefire:test parameters](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Spring Boot 3.5 — Running Your Application with Maven](https://docs.spring.io/spring-boot/3.5/maven-plugin/run.html)
- [Spring Boot 3.5 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)