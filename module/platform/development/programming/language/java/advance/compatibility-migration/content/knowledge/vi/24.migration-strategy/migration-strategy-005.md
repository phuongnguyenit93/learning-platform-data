# Dùng adapter hoặc nhánh triển khai riêng khi cần hỗ trợ nhiều JDK

Trong một dự án **Java Advance Compatibility Migration**, khó khăn lớn nhất đôi khi không nằm ở code cần sửa, mà ở việc **không thể nâng tất cả consumer lên cùng một JDK**. Một batch job còn chạy Java 8; service mới đã chuyển sang Java 21; một thư viện nội bộ phục vụ cả hai; ứng dụng partner lại có lịch nâng cấp ngoài quyền kiểm soát của nhóm phát triển. Nếu thay toàn bộ source bằng những API mới, ứng dụng cũ có thể ngừng biên dịch hoặc thất bại khi JVM nạp class.

Giải pháp thường hữu ích là tạo một **hợp đồng chung** rồi tách những phần lệ thuộc JDK thành **adapter** hoặc **implementation riêng**. Một nhánh triển khai sử dụng API tương thích JDK cũ, nhánh khác tận dụng Java hiện đại. Với khác biệt nhỏ, có thể dùng **multi-release JAR**; với sự phân kỳ lớn về framework và dependency, có thể cần nhiều artifact hoặc những release branches độc lập.

Mục tiêu không phải duy trì JDK cũ vô thời hạn. Đây là chiến lược chuyển tiếp có kiểm soát: hỗ trợ consumer đang tồn tại, cho phép ứng dụng mới tiến hóa, giữ tính đúng đắn của dữ liệu và có kế hoạch kết thúc hỗ trợ legacy.

Bài học này giải thích cách chọn mô hình, thiết kế adapter ở mức source/binary/API, ví dụ Java 8 và Java 21, cấu hình Maven/Gradle, ServiceLoader và JPMS, MR-JAR, kiểm soát dependency graph, kiểm thử trên nhiều JVM, rollout, rollback, security backport và sunset.

## 1. Xác định chính xác yêu cầu tương thích

### 1.1. “Hỗ trợ nhiều JDK” bao gồm những tầng nào?

| Tầng | Câu hỏi | Lỗi thường gặp |
|---|---|---|
| Source | Consumer cũ có biên dịch được với API không? | Method bị đổi chữ ký hoặc dùng cú pháp mới |
| Binary | Class đã biên dịch từ trước còn liên kết được không? | `NoSuchMethodError` hoặc `NoClassDefFoundError` |
| Class-file | JVM có đọc được major version của `.class` không? | `UnsupportedClassVersionError` |
| Java platform API | Method của Java SE có tồn tại ở JDK cũ không? | Dùng `java.net.http` trên Java 8 |
| Dependencies | JAR bắc cầu có yêu cầu Java mới hơn không? | Thư viện major 65 trong app Java 8 |
| Behavior | Kết quả, concurrency, timeout có giữ nguyên hợp đồng không? | Adapter mới làm quá tải database |
| Data/protocol | Version cũ đọc được dữ liệu version mới ghi không? | Unknown enum, JSON/schema incompatibility |
| Deployment | Runtime image, native library, agent và flags có phù hợp không? | Sai OS/architecture, agent crash |
| Vendor support | Framework và JDK có trong support matrix không? | Framework line đã EOL |

Một API adapter có thể che thay đổi API Java nhưng không tự giải quyết tất cả những tầng khác. Phải viết rõ mục tiêu trước khi chọn giải pháp.

### 1.2. Build JDK khác runtime JDK

Một module được biên dịch bằng JDK 21 vẫn có thể tạo bytecode Java 8 khi dùng `javac --release 8`. Nhưng nếu dependency đã biên dịch cho Java 21, runtime Java 8 vẫn không nạp được.

Ví dụ cấu hình có chủ đích:

```text
Shared API:
  compiler: JDK 21
  --release: 8
  runtime floor: Java 8

Legacy adapter:
  compiler: JDK 21
  --release: 8
  runtime floor: Java 8

Modern adapter:
  compiler: JDK 21
  --release: 21
  runtime floor: Java 21
```

Java 8 class-file major là **52**, Java 17 là **61**, Java 21 là **65**. Runtime Java 8 không hỗ trợ class major 65. Chạy tests trên Java 21 không thay thế việc chạy legacy variant trên Java 8 thật.

### 1.3. Xác định tập consumer và support window

Ghi nhận:

- Service/ứng dụng nào còn chạy mỗi JDK.
- Framework và build tools tương ứng.
- Hạn chót nâng cấp hoặc điều khoản hỗ trợ.
- Public APIs và protocol mà họ sử dụng.
- Artifact/version đã triển khai.
- Ai chịu trách nhiệm backport và security fixes.

Nếu không còn consumer JDK 8, tạo một implementation JDK 8 mới chỉ khiến sản phẩm phát sinh nghĩa vụ bảo trì không cần thiết.

## 2. Chọn mức tách phù hợp

| Chiến lược | Khi nên dùng | Ưu điểm | Đánh đổi |
|---|---|---|---|
| Một implementation target JDK thấp | Không thật sự cần API mới | Dễ bảo trì | Không khai thác trực tiếp API mới |
| Adapter + implementation JARs | API chung, kỹ thuật runtime khác | Ranh giới rõ và test độc lập | Thêm artifacts/wiring |
| Adapter qua `ServiceLoader` | Muốn pluggable implementation | Consumer không phụ thuộc implementation lúc compile | Dễ đóng gói thiếu hoặc thừa provider |
| Multi-release JAR | Khác biệt nhỏ trong cùng public API | Một JAR, JVM chọn class theo release | Build, inspection và shading phức tạp |
| Hai artifact lines | Dependency/framework khác lớn | Consumers chọn minh bạch | Release matrix lớn hơn |
| Hai Git release branches | Roadmap/support contract phân kỳ nhiều | Backport và lịch phát hành riêng | Divergence và chi phí cao |
| Reflection/MethodHandles ở một boundary | Một API mới nhỏ, không muốn tách JAR | Ít artifacts | Runtime errors, giảm type safety |
| Chỉ phát hành modern variant | Consumer cũ đã sunset | Đơn giản nhất | Không còn tương thích JDK cũ |

Không bắt đầu bằng hai Git branches nếu sự khác nhau chỉ là một class dùng API mới. Ngược lại, không ép một MR-JAR xử lý hai framework lines khác nhau hoàn toàn.

## 3. Kiến trúc adapter cơ bản

### 3.1. Sơ đồ

```text
                         +------------------+
                         |  Business Logic  |
                         |  shared JDK API  |
                         +---------+--------+
                                   |
                                   v
                          +----------------+
                          | TaskExecutor   |
                          | interface      |
                          | target Java 8  |
                          +--------+-------+
                             /           \
                            /             \
             +-------------+--+      +-----+------------+
             | JDK 8 adapter |      | JDK 21 adapter   |
             | platform pool |      | virtual threads  |
             +----------------+      +------------------+
                      |                       |
                      v                       v
                Java 8 app               Java 21 app
```

Shared API chỉ phụ thuộc các types có mặt trong runtime thấp nhất. Các adapters chứa code JDK-specific và không làm lộ implementation types vào public interface.

### 3.2. Interface chung dùng được trên Java 8

```java
package com.example.tasks.api;

import java.util.concurrent.Callable;
import java.util.concurrent.Future;

public interface TaskExecutor extends AutoCloseable {
    <T> Future<T> submit(Callable<T> task);

    @Override
    void close();
}
```

`Callable`, `Future` và `AutoCloseable` đều có trong Java 8. Interface này không nhắc `Thread.Builder` hoặc `Executors.newVirtualThreadPerTaskExecutor()`.

Một mẫu **không phù hợp** khi vẫn cần Java 8:

```java
// Sai: public contract tham chiếu API chỉ có ở Java mới.
public interface TaskExecutor {
    Thread.Builder.OfVirtual newVirtualTask();
}
```

Không thể bảo toàn compatibility chỉ bằng cách “không gọi method đó” ở Java 8. Type trong chữ ký API đã vi phạm baseline.

### 3.3. Hợp đồng cần mô tả cả behavior

Ngoài chữ ký, phải quyết định:

```text
submit(task):
  - task khác null
  - Future trả về kết quả/exception của task
  - caller có thể cancel hoặc chờ timeout
  - không hứa thứ tự scheduling cụ thể

close():
  - bắt đầu shutdown
  - không nhận thêm task mới
  - không tự hứa chờ mọi task hoàn thành

operational:
  - giới hạn downstream resources độc lập thread model
  - không để task bị mất trong lúc shutdown
```

Nếu adapter legacy dùng 8 threads và adapter modern tạo nhiều virtual threads, behavior và áp lực lên hệ thống bên ngoài có thể khác dù interface giống nhau.

## 4. Implementation Java 8

### 4.1. Dùng ExecutorService truyền thống

```java
package com.example.tasks.jdk8;

import com.example.tasks.api.TaskExecutor;

import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class Jdk8TaskExecutor implements TaskExecutor {
    private final ExecutorService delegate;

    public Jdk8TaskExecutor(int threads) {
        if (threads <= 0) {
            throw new IllegalArgumentException(
                "threads must be positive");
        }
        this.delegate = Executors.newFixedThreadPool(threads);
    }

    @Override
    public <T> Future<T> submit(Callable<T> task) {
        Objects.requireNonNull(task, "task");
        return delegate.submit(task);
    }

    @Override
    public void close() {
        delegate.shutdown();
    }
}
```

Code này sử dụng những tính năng đã có trên Java 8. Nó không cần biết modern adapter hoạt động thế nào.

### 4.2. Hạn chế của fixed thread pool

`Executors.newFixedThreadPool` giới hạn số worker threads nhưng có thể có queue chờ lớn. Trong hệ thống production, nên cân nhắc:

- Queue capacity và rejection policy.
- Backpressure khi producer nhanh hơn consumer.
- Task timeout và cancellation.
- Metrics về active threads, queue size và thời gian chờ.
- Graceful shutdown và xử lý unfinished tasks.

Nếu business contract yêu cầu backpressure, phải thiết kế abstraction hoặc policy đủ rõ thay vì coi thread pool mặc định là hoàn hảo.

### 4.3. Test trên runtime Java 8 thật

Compile target Java 8 không chứng minh runtime behavior. Cần một job:

```text
Build shared API with --release 8
Build legacy adapter with --release 8
Assemble full legacy dependency graph
Run contract + integration tests on Java 8 JVM
```

Test phải sử dụng artifact cuối và runtime dependency versions thực tế, không chỉ compile test sources trên JDK mới.

## 5. Implementation Java 21

### 5.1. Dùng virtual threads

Java 21 có API `Executors.newVirtualThreadPerTaskExecutor()`:

```java
package com.example.tasks.jdk21;

import com.example.tasks.api.TaskExecutor;

import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class Jdk21TaskExecutor implements TaskExecutor {
    private final ExecutorService delegate =
        Executors.newVirtualThreadPerTaskExecutor();

    @Override
    public <T> Future<T> submit(Callable<T> task) {
        Objects.requireNonNull(task, "task");
        return delegate.submit(task);
    }

    @Override
    public void close() {
        delegate.shutdown();
    }
}
```

Implementation được compile target Java 21. Interface chung vẫn là Java 8, giúp application code phụ thuộc abstraction, không phụ thuộc vào cách tạo threads.

### 5.2. Virtual threads không đồng nghĩa tài nguyên vô hạn

Virtual threads thuận lợi cho workload có nhiều I/O blocking tasks, nhưng không tạo thêm CPU cores, database connections hoặc hạn ngạch API.

Ví dụ có thể cần một semaphore/bulkhead ở ngoài adapter:

```text
Incoming jobs: 10,000
Virtual threads: many
Database pool: 20 connections
=> giới hạn đồng thời gọi DB vẫn phải được quản lý
```

Nếu bản Java 8 trước đó vô tình giới hạn concurrency bằng 8 threads, thay bằng virtual-thread-per-task có thể làm downstream quá tải. Cần định nghĩa capacity, timeout và rate limits như một phần hợp đồng hoặc vận hành.

### 5.3. Khi Java 17 cũng là target

Nếu consumer Java 17 phải chạy modern API nhưng không có virtual threads final, có thể:

- Dùng legacy implementation trên Java 17.
- Tạo implementation Java 17 riêng khi có lợi ích cụ thể.
- Giữ Java 21 adapter cho Java 21 trở lên.
- Nâng toàn bộ support floor khi consumer đã sẵn sàng.

Không cần một adapter cho **mỗi** JDK release. Chỉ tạo variant khi có capability và nhu cầu thực tế.

## 6. Chọn implementation khi build hoặc khi deploy

### 6.1. Explicit dependency injection

Ứng dụng legacy có thể khởi tạo:

```java
TaskExecutor executor = new Jdk8TaskExecutor(8);
```

Ứng dụng Java 21:

```java
TaskExecutor executor = new Jdk21TaskExecutor();
```

Hai đoạn code thuộc hai application configurations hoặc bootstrap modules **khác nhau**; không đặt code hiện đại vào một source unit mà bắt buộc biên dịch với `--release 8`.

Ưu điểm: không có runtime guessing hoặc reflection, dễ thấy artifact nào được sử dụng. Nhược điểm: cần cấu hình wiring riêng.

### 6.2. Framework DI

Nếu dùng Spring, CDI hoặc DI container khác, một số cách là:

- Mỗi application profile chỉ thêm một provider artifact.
- Bean configuration gắn với runtime/deployment được công bố.
- Application module quyết định binding của interface.
- Feature flag chỉ chọn feature khi cả hai implementation đều được build phù hợp.
- Bổ sung test “exactly one bean/provider” ở startup.

Một framework mà bản mới yêu cầu Java 17 không thể được làm cho chạy trên Java 8 chỉ bằng cách đặt bean trong adapter. Framework và thư viện bắc cầu vẫn quyết định JDK floor.

### 6.3. Không lựa chọn ngầm bằng JDK của build tool

Nếu CI chạy Maven hoặc Gradle bằng JDK 21 để build artifact Java 8, rule kiểu “JDK build >= 21 thì chọn adapter hiện đại” sẽ chọn **sai** variant.

Quyết định cần dựa vào release target/consumer contract, không phải JDK tình cờ có trong PATH của developer.

## 7. ServiceLoader và SPI

### 7.1. Khi nào dùng ServiceLoader?

`java.util.ServiceLoader` có từ Java cũ và phù hợp khi application chỉ phụ thuộc shared interface nhưng implementation được cung cấp lúc runtime.

Đối với provider class trên classpath, một Java 8-compatible JAR thường khai báo resource:

```text
META-INF/services/com.example.tasks.api.TaskExecutor
```

Nội dung resource trỏ tới tên class của provider có public no-arg constructor.

### 7.2. Provider legacy phù hợp SPI

Ví dụ `Jdk8TaskExecutor` bên trên chỉ có constructor nhận `threads`. Vì vậy tạo wrapper:

```java
package com.example.tasks.jdk8;

import com.example.tasks.api.TaskExecutor;
import java.util.concurrent.Callable;
import java.util.concurrent.Future;

public final class Jdk8TaskExecutorProvider
        implements TaskExecutor {

    private final Jdk8TaskExecutor delegate =
        new Jdk8TaskExecutor(8);

    public Jdk8TaskExecutorProvider() {
    }

    @Override
    public <T> Future<T> submit(Callable<T> task) {
        return delegate.submit(task);
    }

    @Override
    public void close() {
        delegate.close();
    }
}
```

Service descriptor của legacy JAR:

```text
com.example.tasks.jdk8.Jdk8TaskExecutorProvider
```

Modern JAR có thể khai báo provider hiện đại theo cùng interface.

### 7.3. Loader chạy trên Java 8

```java
package com.example.tasks.api;

import java.util.Iterator;
import java.util.ServiceLoader;

public final class TaskExecutors {
    private TaskExecutors() {
    }

    public static TaskExecutor loadExactlyOne() {
        Iterator<TaskExecutor> providers =
            ServiceLoader.load(TaskExecutor.class).iterator();

        if (!providers.hasNext()) {
            throw new IllegalStateException(
                "No TaskExecutor provider available");
        }

        TaskExecutor executor = providers.next();

        if (providers.hasNext()) {
            throw new IllegalStateException(
                "Multiple TaskExecutor providers found");
        }

        return executor;
    }
}
```

Ở runtime, phát hành **chỉ một provider phù hợp**:

```text
Java 8 distribution:
  task-api.jar
  task-adapter-jdk8.jar

Java 21 distribution:
  task-api.jar
  task-adapter-jdk21.jar
```

`ServiceLoader` không phải công cụ tự chọn JDK-compatible implementation theo class-file version. Đóng cả hai JAR có thể làm loader thấy hai providers, hoặc cố nạp provider quá mới trên JDK cũ.

### 7.4. Cẩn thận khi tạo fat JAR

Shading có thể:

- Làm mất `META-INF/services`.
- Merge cả hai provider descriptors vào cùng file.
- Relocate implementation class mà không sửa descriptor.
- Đóng JAR hiện đại vào gói legacy.

Do đó phải chạy SPI tests trên **artifact cuối cùng**, không chỉ classpath của IDE.

## 8. Thiết kế Maven multi-module

### 8.1. Cấu trúc

```text
multi-jdk-library/
  pom.xml
  task-api/
    pom.xml
  task-adapter-jdk8/
    pom.xml
  task-adapter-jdk21/
    pom.xml
  app-legacy/
    pom.xml
  app-modern/
    pom.xml
```

Quan hệ dependency:

```text
task-api
  |
  +-- task-adapter-jdk8 ----> app-legacy
  |
  +-- task-adapter-jdk21 ---> app-modern
```

Parent POM quản lý plugin versions, dependency versions và baseline; child modules có compile release riêng.

### 8.2. Shared API và legacy adapter

Ví dụ trong hai POM tương ứng:

```xml
<properties>
    <maven.compiler.release>8</maven.compiler.release>
</properties>
```

`maven-compiler-plugin` phải được pin và chạy bằng toolchain/compiler hỗ trợ `--release`. Java 8 compiler không có `--release`; một cách phổ biến là dùng compiler JDK 21 với release 8 rồi test runtime thật trên Java 8.

### 8.3. Modern adapter

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Implementation khai báo dependency vào `task-api` và những dependency chỉ dùng được trên Java 21. Không khai báo modern adapter trong dependency graph của app legacy.

### 8.4. Ví dụ dependency của ứng dụng legacy

```xml
<dependencies>
    <dependency>
        <groupId>com.example.tasks</groupId>
        <artifactId>task-api</artifactId>
        <version>1.0.0</version>
    </dependency>
    <dependency>
        <groupId>com.example.tasks</groupId>
        <artifactId>task-adapter-jdk8</artifactId>
        <version>1.0.0</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Ví dụ giả định ứng dụng dùng SPI và chỉ cần API ở compile-time. Nếu bootstrap code trực tiếp khởi tạo `Jdk8TaskExecutor`, dependency implementation phải hiện diện ở compile scope.

### 8.5. Không nhầm Maven reactor với compatibility

Một reactor build thành công chỉ chứng minh từng module được build dưới cấu hình hiện tại. Nó không chứng minh:

- Legacy graph không có Java 21 JAR.
- Application runtime dùng đúng provider.
- App chạy được trên Java 8.
- Framework, JDBC driver và agent không đòi JDK cao hơn.

Nên dùng `dependency:tree`, effective POM và runtime tests cho từng distribution.

### 8.6. Profile rõ ràng hơn activation theo Java build version

Nếu dùng Maven profiles, nên có profiles được chọn có chủ đích:

```text
-Plegacy-distribution
-Pmodern-distribution
```

Đừng để profile tự chọn modern adapter chỉ vì Maven đang chạy bằng JDK 21, trong khi artifact được xây cho người dùng Java 8.

## 9. Thiết kế Gradle multi-project

### 9.1. Khai báo projects

```groovy
rootProject.name = 'multi-jdk-library'

include 'task-api'
include 'task-adapter-jdk8'
include 'task-adapter-jdk21'
include 'app-legacy'
include 'app-modern'
```

### 9.2. Shared API target Java 8

`task-api/build.gradle`:

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 8
}
```

Compiler JDK 21 được dùng để tạo class-file version Java 8 và kiểm soát Java SE API trong source tương ứng.

### 9.3. Modern adapter target Java 21

`task-adapter-jdk21/build.gradle`:

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}

dependencies {
    implementation project(':task-api')
}
```

Legacy adapter dùng `options.release = 8` và dependency vào `:task-api`.

### 9.4. App chọn runtime dependency

`app-legacy/build.gradle`:

```groovy
dependencies {
    implementation project(':task-api')
    runtimeOnly project(':task-adapter-jdk8')
}
```

`app-modern/build.gradle`:

```groovy
dependencies {
    implementation project(':task-api')
    runtimeOnly project(':task-adapter-jdk21')
}
```

Ví dụ này phù hợp khi app sử dụng `ServiceLoader`. Nếu gọi implementation trực tiếp, cần thêm nó vào compile classpath như một dependency thích hợp.

### 9.5. Convention plugins và nguồn cấu hình thống nhất

Trong monorepo lớn, thay vì rải `options.release` ở nhiều nơi, dùng convention plugin để đặt policy:

```text
shared API modules  -> release 8
legacy adapters     -> release 8
modern adapters     -> release 21
legacy apps         -> release 8
modern apps         -> release 21
```

Tuy nhiên, phải cho phép override có chủ đích và lưu lý do. Một module được build bằng JDK 21 không nhất thiết được phép phát hành Java 21 bytecode.

### 9.6. Variant metadata

Gradle Module Metadata có thể thể hiện target JVM và hỗ trợ lựa chọn variants theo attributes. Nhưng các Maven consumers không nhất thiết hiểu metadata đó; vì vậy với thư viện phục vụ nhiều build systems, artifacts có coordinates riêng và support matrix rõ ràng thường dễ bảo trì.

Không tin rằng variant resolution tự bảo đảm mọi JAR bên trong fat distribution có major version tương thích.

## 10. Multi-release JAR: một artifact chứa implementation theo JDK

### 10.1. Bố cục

Multi-release JAR được Java hỗ trợ từ Java 9. Một JAR có base classes và lớp thay thế theo runtime release:

```text
task-library.jar
  META-INF/MANIFEST.MF
  com/example/tasks/TaskEngine.class
  com/example/tasks/EngineImpl.class
  META-INF/versions/21/com/example/tasks/EngineImpl.class
```

Manifest cần khai báo:

```text
Multi-Release: true
```

Trên Java 8, JVM sử dụng base implementation. Trên Java 21, classloading có hỗ trợ MR-JAR có thể chọn versioned class ở `META-INF/versions/21`.

### 10.2. Ưu điểm

- Chỉ một coordinates/artifact để phân phối.
- Base API giữ runtime floor cũ.
- JDK mới có thể chọn implementation tối ưu mà consumer không cần đổi dependency.
- Hữu ích khi sự khác biệt ở một số internal classes, không phải ở toàn bộ framework.

### 10.3. Giới hạn

MR-JAR **không**:

- Tự chọn những Maven/Gradle dependencies khác nhau theo runtime một cách tổng quát.
- Biến JAR Java 21 thành chạy được trên Java 8.
- Giải quyết native ABI, OS/architecture hoặc application-server differences.
- Đảm bảo public API khác nhau giữa variants được hỗ trợ.
- Đảm bảo mọi plugin shading, bytecode scan, obfuscation hoặc classpath tool hiểu versioned entries.

Nếu modern adapter cần cả một bộ thư viện mới không còn hỗ trợ Java 8, hai artifacts riêng thường đơn giản hơn.

### 10.4. Quy tắc xây dựng

- Base classes được biên dịch target runtime thấp nhất.
- Versioned classes được biên dịch target tương ứng với folder `versions/N`.
- Giữ public API compatibility phù hợp giữa base và versioned classes.
- Manifest đúng và JAR layout đúng.
- Runtime Java 8 nạp được base classes.
- Runtime Java 21 thực sự chọn variant mới.
- Dependency closure vẫn hợp lệ cho từng runtime.
- CI xử lý đúng MR-JAR khi scan class major.

Scanner chỉ kiểm tra “mọi .class trong ZIP <= major 52” sẽ từ chối MR-JAR có variant Java 21 hợp lệ. Ngược lại, chỉ kiểm tra root classes có thể bỏ sót class versioned bị build sai.

### 10.5. Kiểm thử MR-JAR

```text
Java 8:
  uses base implementation
  no reference to Java 21 API
  behavior contract passes

Java 17:
  uses base or highest eligible <= 17 variant
  behavior contract passes

Java 21:
  uses Java 21 versioned implementation
  behavior contract passes
```

Dùng `jar --list`, `javap` và `jdeps --multi-release` khi phù hợp, nhưng kết luận dựa trên **JAR đã phát hành chạy trên JVM thực tế**.

## 11. Khi nên duy trì hai artifact lines

### 11.1. Mức độ phân kỳ dependency lớn

Giả sử:

```text
shared-api:
  Java 8 baseline

legacy-adapter:
  Java 8
  HTTP library cũ
  framework line A

modern-adapter:
  Java 21
  java.net.http
  framework line B
```

Nếu framework line B đòi Java 17/21, không thể đưa nó vào classpath của legacy app rồi hy vọng adapter che được. Mỗi distribution cần dependency closure riêng.

### 11.2. Release coordinates rõ ràng

Ví dụ:

```text
com.example:task-api:1.4.0
com.example:task-adapter-jdk8:1.4.0
com.example:task-adapter-jdk21:1.4.0
```

Cùng version family giúp quản lý, nhưng không tự chứng minh compatibility. Nếu phát hành versions độc lập, cần lập bảng cặp API/adapter được hỗ trợ.

### 11.3. ArtifactId riêng hay classifier?

| Cách | Lợi thế | Rủi ro |
|---|---|---|
| ArtifactId riêng | Graph rõ, phụ thuộc riêng | Tăng số coordinates |
| Classifier riêng | Cùng artifact family | Dependency metadata của classifier có thể khó quản lý |
| Gradle variants | Tự chọn theo attributes trong một số trường hợp | Maven/older consumers có thể không hiểu |
| MR-JAR | Một file | Build/runtime testing phức tạp |

Nếu hai implementations có transitive dependencies riêng biệt, artifactId riêng thường dễ audit hơn.

### 11.4. Khai báo minimum JDK trong tài liệu

Ví dụ mẫu:

```text
task-adapter-jdk8:
  minimum Java: 8
  tested Java: 8, 17, 21 (chỉ ghi sau khi kiểm thử)

task-adapter-jdk21:
  minimum Java: 21
  tested Java: 21, 25 (chỉ ghi sau khi kiểm thử)
```

Tên artifact không thay thế việc công bố runtime support. Đối với các JDK sau bản phát hành hiện tại, đừng tự gắn nhãn “supported” khi chưa có bằng chứng.

## 12. Khi nào cần hai Git branches?

### 12.1. Tách implementation không bắt buộc tách repository

Nếu hai adapters chỉ khác một vài classes, giữ cùng một repository/main branch giúp code review, API contract và security fixes nhất quán hơn.

Nhánh phát hành riêng phù hợp khi:

- Framework major lines khác sâu.
- Public API hoặc build tooling phân kỳ lớn.
- Consumer legacy cần bảo trì nhiều năm nhưng không nhận tính năng mới.
- Đội vận hành/release có owner và support contracts khác nhau.
- Các thay đổi không thể được chia sẻ dễ qua modules/source sets.

### 12.2. Mô hình branches

```text
main
  -> Java 21 modern development

release/java8
  -> critical fixes + security backports

release/java17 (nếu cần)
  -> maintenance của consumers Java 17
```

Không nên tạo một branch cho mọi JDK major khi không có consumer hoặc business requirement.

### 12.3. Backport logic thay vì cherry-pick máy móc

Ví dụ bản modern dùng Java 21 HTTP Client, còn legacy dùng `HttpURLConnection`. Một bug fix về retry policy phải được backport về **nghĩa nghiệp vụ** nhưng implementation có thể khác.

```text
Modern fix:
  use HTTP client timeout API

Legacy fix:
  configure connect/read timeouts on HttpURLConnection

Shared contract:
  request fails after documented deadline
```

Không cố giữ source giống hệt khi hai runtime APIs khác nhau.

### 12.4. Mỗi branch cần điều kiện kết thúc

Một policy có thể ghi:

- Branch owner.
- Minimum JDK và framework line.
- Consumer list.
- Security fixes được phép.
- Critical bug-fix criteria.
- Ngày dừng bảo trì.
- CI matrix và artifact release process.
- Cách chuyển consumer sang modern line.
- Exit criteria và archival policy.

Thiếu những mục này, một “nhánh chuyển tiếp” có nguy cơ tồn tại vô thời hạn mà không đủ nguồn lực cập nhật.

## 13. Phát hiện capability thay vì đoán version

### 13.1. Vì sao check version dễ tạo lỗi?

Một source Java 8 viết:

```java
if (javaVersion >= 21) {
    // call Java 21 API directly
}
```

không làm source tự trở thành Java 8-compatible: compiler vẫn nhìn thấy code gọi API chưa có trên Java 8, và JVM class loading có thể phải resolve types mới.

Việc chạy trên một JDK version cụ thể cũng không tự bảo đảm framework/plugin hoặc runtime image có capability được trông đợi.

### 13.2. Reflection chỉ phù hợp cho boundary nhỏ

Có thể kiểm tra một method qua reflection bằng cú pháp Java 8:

```java
import java.lang.reflect.Method;
import java.util.concurrent.Executors;

public final class RuntimeCapabilities {
    private RuntimeCapabilities() {
    }

    public static boolean hasVirtualThreadExecutor() {
        try {
            Method method = Executors.class.getMethod(
                "newVirtualThreadPerTaskExecutor");
            return method != null;
        } catch (NoSuchMethodException ex) {
            return false;
        }
    }
}
```

Đây chỉ là capability detection; không chứng minh method phù hợp workload hoặc policy. Nếu dùng reflection để gọi API mới, phải xử lý invocation errors, resource cleanup và giữ public interface không rò rỉ Java 21 types.

### 13.3. Không catch mọi Throwable rồi fallback

Nếu code dùng `Class.forName` để tìm provider hiện đại, lỗi có thể là:

- Implementation JAR không tồn tại.
- JVM quá cũ để nạp bytecode.
- Dependency bị thiếu.
- Module access bị chặn.
- Static initializer hoặc constructor bị lỗi.
- Bản provider sai cấu hình.

Nếu bắt tất cả `Throwable` rồi fallback im lặng, có thể che một lỗi production nghiêm trọng. Hãy phân biệt “feature absent” khỏi “deployment broken” và log đủ thông tin đã che secrets.

### 13.4. Runtime.version không tồn tại trên Java 8

`Runtime.version()` có từ Java 9. Shared Java 8 source không nên gọi trực tiếp API này. Nếu cần version detection thật sự, chọn cơ chế tương thích và kiểm thử format; tuy nhiên, artifact selection ở build/deploy time thường rõ hơn.

## 14. JPMS, module descriptors và classloading

### 14.1. JPMS API khi runtime mới

Một named module có thể khai báo:

```java
module com.example.tasks.api {
    exports com.example.tasks.api;
    uses com.example.tasks.api.TaskExecutor;
}
```

Provider module:

```java
module com.example.tasks.jdk21 {
    requires com.example.tasks.api;

    provides com.example.tasks.api.TaskExecutor
        with com.example.tasks.jdk21.Jdk21TaskExecutor;
}
```

Ví dụ mô tả cách JPMS công bố service provider. Nhưng một source `module-info.java` không thể được biên dịch bằng Java 8; nếu shared API cần Java 8, cần dùng classpath-based SPI, MR-JAR descriptor versioned hoặc artifact module-specific có chiến lược rõ.

### 14.2. Classpath SPI khác module path SPI

Trên classpath, provider có thể được công bố qua `META-INF/services/...`. Trên module path, `module-info.java` dùng `provides`/`uses`. Đừng giả định chuyển packaging từ classpath sang module path không thay đổi discovery behavior.

### 14.3. Split packages và duplicate classes

Nếu legacy và modern providers dùng cùng packages/class names và được đưa lên module path cùng lúc, có thể gặp conflict module/package. Nếu plugin tự đóng shared API khác classloader, một instance provider có thể không cast được sang interface của host dù class names giống nhau.

Nên tách:

```text
com.example.tasks.api
com.example.tasks.jdk8
com.example.tasks.jdk21
```

Chỉ định rõ API được chia sẻ ở classloader/module layer thích hợp và không bundle duplicate API vào plugins không cần thiết.

## 15. Dependency closure quyết định JDK tối thiểu

### 15.1. Một implementation major 52 vẫn có thể phụ thuộc major 61

```text
legacy-adapter.jar  major 52
        |
        +--> metrics-library.jar major 61
```

Java 8 sẽ thất bại khi nạp class Java 17 từ dependency, dù adapter chính được compile target 8.

Kiểm tra:

- Direct dependencies.
- Transitive dependencies.
- Fat/nested JARs.
- Java agents.
- Annotation processors và test dependencies riêng.
- Native library requirements.
- Framework/ORM/HTTP/serialization baseline.

### 15.2. BOM và dependency locking không sửa bytecode

Gradle version catalog, BOM/platform, dependency locking và Maven dependencyManagement giúp quản lý version graph. Chúng không làm một Java 21 JAR tương thích Java 8.

Nếu modern adapter có dependency chỉ chạy Java 21, dependency đó phải được loại khỏi legacy deployment graph. Khi đổi BOM, review cả nhánh legacy, không chỉ modern path.

### 15.3. Kiểm tra artifact thực tế

```shell
javap -verbose -classpath task-api.jar \
    com.example.tasks.api.TaskExecutor
```

Một class major 52 là tín hiệu tốt nhưng chưa đủ. Cần scan mọi class trong JAR và nested runtime dependencies; với MR-JAR phải dùng logic hiểu `META-INF/versions/N`.

Sau đó chạy tests trên JVM tối thiểu để phát hiện Java API, module, reflection và behavior không tương thích.

## 16. Ví dụ thứ hai: HTTP adapter

### 16.1. Chia API của HTTP client

Java 8 không có `java.net.http.HttpClient` nhưng Java 11+ có. Một common interface chỉ dùng types có từ Java 8:

```java
package com.example.http.api;

import java.io.IOException;

public interface TextFetcher {
    String fetch(String url) throws IOException;
}
```

Một implementation có thể dùng `HttpURLConnection`; bản mới dùng `java.net.http.HttpClient`.

### 16.2. Legacy implementation

```java
package com.example.http.jdk8;

import com.example.http.api.TextFetcher;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public final class Jdk8Fetcher implements TextFetcher {
    @Override
    public String fetch(String address) throws IOException {
        HttpURLConnection c =
            (HttpURLConnection) new URL(address).openConnection();

        c.setConnectTimeout(5000);
        c.setReadTimeout(5000);

        try {
            if (c.getResponseCode() != 200) {
                throw new IOException(
                    "Unexpected HTTP response: " +
                    c.getResponseCode());
            }

            StringBuilder result = new StringBuilder();

            try (BufferedReader reader =
                     new BufferedReader(
                         new InputStreamReader(
                             c.getInputStream(),
                             StandardCharsets.UTF_8))) {

                String line;
                while ((line = reader.readLine()) != null) {
                    result.append(line).append('\n');
                }
            }

            return result.toString();
        } finally {
            c.disconnect();
        }
    }
}
```

Ví dụ chỉ minh họa ranh giới JDK, không phải HTTP client production-ready: cần xử lý redirect, response size, charset, proxy, TLS, SSRF và status policies. Đầu vào URL từ người dùng cần allowlist và giới hạn network riêng.

### 16.3. Modern implementation

```java
package com.example.http.jdk21;

import com.example.http.api.TextFetcher;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class Jdk21Fetcher implements TextFetcher {
    private final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build();

    @Override
    public String fetch(String address) throws IOException {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create(address))
            .timeout(Duration.ofSeconds(5))
            .GET()
            .build();

        try {
            HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8));

            if (response.statusCode() != 200) {
                throw new IOException(
                    "Unexpected HTTP response: " +
                    response.statusCode());
            }

            return response.body();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IOException(
                "Interrupted during HTTP request", ex);
        }
    }
}
```

API `java.net.http` có từ Java 11; đặt implementation tại module Java 21 ở đây là lựa chọn release cụ thể, không phải vì chính API cần Java 21.

### 16.4. Contract tests cho hai HTTP adapters

Cần so sánh:

- HTTP status handling (200, 201, 204, 4xx/5xx).
- Redirect behavior.
- Timeout và retry.
- Charset và newline.
- Proxy.
- TLS truststore và hostname verification.
- Error messages và exception contract.
- Resource cleanup.
- Response-size limits.
- Cancellation và thread interruption.

Nếu chỉ test “fetch một trang thành công”, behavior khác nhau có thể lộ sau deployment.

## 17. Kiểm thử API, binary và behavior

### 17.1. Contract tests chung

Một helper có thể được dùng bởi cả hai test modules:

```java
import com.example.tasks.api.TaskExecutor;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class TaskExecutorContract {
    public static void verify(TaskExecutor executor)
            throws Exception {

        try {
            Future<Integer> result =
                executor.submit(() -> 6 * 7);

            int actual = result.get(5, TimeUnit.SECONDS);

            if (actual != 42) {
                throw new AssertionError(
                    "Expected 42 but got " + actual);
            }
        } finally {
            executor.close();
        }
    }
}
```

Test thực tế cần bổ sung exception propagation, cancellation, timeout, shutdown và concurrency semantics.

### 17.2. Source compatibility không đồng nghĩa binary compatibility

Một thay đổi public method:

```java
// V1
byte[] encode(String text);

// V2
java.nio.ByteBuffer encode(CharSequence text);
```

không chỉ ảnh hưởng JDK target; nó thay đổi method descriptor. Consumer đã biên dịch với V1 có thể gặp `NoSuchMethodError` khi runtime chọn V2, dù cả hai cùng dùng bytecode Java 8.

Nếu hứa binary compatibility, giữ method cũ hoặc phát hành breaking API version có migration path rõ. Adapter JDK không tự chữa một public API bị xóa.

### 17.3. Không để tests chỉ chạy trên JVM mới

Một ví dụ test coverage sai:

```text
shared API target 8
legacy adapter target 8
all tests executed on Java 21
=> Java 8 compatibility not proven
```

Để xác nhận legacy support, phải chạy ứng dụng hoặc contract suite với Java 8 runtime thật và dependency closure thực tế.

### 17.4. Binary comparison tools

Có thể dùng tools như `japicmp`, `Revapi` hoặc một API compatibility checker được tổ chức lựa chọn. Chúng giúp phát hiện các thay đổi public API/binary, nhưng vẫn phải kết hợp runtime integration tests và data protocol tests.

## 18. Ma trận CI và release

### 18.1. Ma trận đề xuất

| Thành phần | Compiler JDK | Target release | Test JVM |
|---|---:|---:|---|
| Shared API | 21 | 8 | 8, 21 |
| Legacy adapter | 21 | 8 | 8 |
| Modern adapter | 21 | 21 | 21 |
| Legacy app | Theo cấu hình | 8 | 8 |
| Modern app | Theo cấu hình | 21 | 21 |
| Legacy release bundle | Theo target | 8 closure | Java 8 production-like |
| Modern release bundle | Theo target | 21 closure | Java 21 production-like |

Chỉ dùng JDK releases và OS/architecture mà sản phẩm thực sự cam kết. Nếu ứng dụng còn hỗ trợ Java 11 hoặc 17, thêm những cột cần thiết với owners và test workloads cụ thể.

### 18.2. Pipeline mẫu

```text
Checkout immutable commit
        |
        v
Pin Maven/Gradle + compiler JDK
        |
        v
Build shared API
        |
        +--> Build legacy adapter
        |         |
        |         v
        |    Resolve legacy dependencies
        |         |
        |         v
        |    Package legacy application
        |         |
        |         v
        |    Bytecode scan + Java 8 tests
        |
        +--> Build modern adapter
                  |
                  v
             Resolve modern dependencies
                  |
                  v
             Package modern application
                  |
                  v
             Bytecode scan + Java 21 tests
        |
        v
Review API/binary compatibility
        |
        v
Integration / protocol / security tests
        |
        v
Immutable artifacts + SBOM + provenance
```

### 18.3. Kiểm tra compiled artifact

Đọc class-file major của **mọi class cần JVM nạp**, không chỉ class chính. Với JAR có `META-INF/versions`, scanner phải hiểu MR-JAR. Với executable fat JAR chứa nested dependencies, phải kiểm tra JARs bên trong.

Không chỉ kiểm tra compile/test classpath nếu deployment dùng classpath khác.

### 18.4. Test packaging và providers

Thực hiện:

- Legacy distribution chỉ chứa legacy provider.
- Modern distribution chỉ chứa modern provider.
- `ServiceLoader` tìm đúng một provider.
- JPMS services được resolve khi dùng module path.
- Không có duplicate common API class qua classloaders.
- Runtime startup và các code paths hiếm đều chạy.

## 19. Rolling deployment và data compatibility

### 19.1. JDK adapter không đảm bảo protocol compatibility

Hai services có thể chạy JDK khác nhau nhưng giao tiếp qua JSON, Avro, Protobuf hoặc database. Một producer mới phát enum value mà consumer cũ không biết vẫn có thể gây lỗi dù cả hai dùng adapters tương thích JVM.

Phải quản lý dữ liệu riêng với bytecode compatibility.

### 19.2. Expand then contract

Một kế hoạch:

```text
1. Consumer cũ được cập nhật để chấp nhận schema mới hoặc unknown values.
2. Producer mới được triển khai nhưng chưa phát dữ liệu chỉ bản mới hiểu.
3. Feature flag được bật có kiểm soát.
4. Theo dõi schema errors, unknown enum values, retry/dead-letter.
5. Sau khi không còn consumer cũ, loại bỏ fallback legacy.
```

Nếu consumer không thể được cập nhật, producer có thể phải tiếp tục phát legacy-compatible data trong thời gian hỗ trợ.

### 19.3. Rollback phải bao gồm trạng thái dữ liệu

Rollback Java 21 application về Java 8 không tự đảo database migrations hoặc messages đã phát. Cần biết:

- Bản cũ có đọc được dữ liệu mới không?
- Có thể giữ dual-reader hoặc versioned DTO không?
- Trạng thái có thể downgrade mà không mất dữ liệu không?
- Message backlog/replay còn bao nhiêu?
- Khi nào có thể bỏ writer legacy?

Không hứa rollback “chỉ cần redeploy JAR” nếu migration đã đổi dữ liệu hoặc external contract.

## 20. Observability và hiệu năng theo variant

### 20.1. Metrics tương đương về nghĩa

Legacy adapter có thể đo active threads/queue depth; modern adapter có thể cần đo concurrent tasks, virtual-thread behavior và downstream pool saturation. Không so sánh thô chỉ số “thread count” như thể hai runtime dùng cùng mô hình.

Contract-level metrics nên gồm:

- Throughput và latency percentiles.
- Task queue/wait time hoặc active task count.
- Success/error/cancellation rates.
- Timeout rate.
- Downstream calls và pool utilization.
- Memory/CPU và GC behavior.
- Graceful shutdown duration.

### 20.2. APM agents cũng cần support matrix

Một agent dùng bytecode instrumentation có thể chỉ hỗ trợ một số JDK/class-file versions. Nếu modern adapter chạy Java 21 nhưng APM agent quá cũ, service có thể lỗi ở startup hoặc không thu thập được tracing.

Kiểm tra trên deployment artifact có agent/flags giống production. Không xem “app chạy tốt khi tắt agent” là toàn bộ compatibility evidence.

### 20.3. Canary và feature rollout

Nếu modern adapter thay threading hoặc HTTP behavior, triển khai tới một tỷ lệ traffic nhỏ trước; quan sát latency, downstream errors và resource consumption. Nếu cần rollback, phải có artifact/lockfile và schema compatibility tương ứng.

## 21. Bảo mật và supply chain cho nhiều variants

### 21.1. Hai graphs, hai tập rủi ro

Legacy variant có thể phải dùng thư viện cũ hơn modern variant. Mỗi graph cần:

- Dependency inventory/SBOM.
- Security vulnerability scanning.
- License review.
- Artifact integrity checks.
- Runtime JDK security update policy.
- Owner chịu trách nhiệm remediation.
- Quyết định exception có hạn nếu chưa nâng được.

Không được cho rằng lockfile bất biến đồng nghĩa an toàn. Lock chỉ giúp thay đổi có kiểm soát.

### 21.2. Immutable artifacts

Phát hành artifacts có version riêng và checksum. Không ghi đè cùng coordinates bằng byte mới; build cache và repository proxy có thể khiến các consumers nhận nội dung khác nhau dưới cùng version.

### 21.3. Đánh giá thời hạn hỗ trợ legacy

Nếu Java 8/framework cũ đã hết support phù hợp hoặc dependency có CVE không thể sửa, duy trì adapter có thể không còn chấp nhận được. Khi đó cần kế hoạch di chuyển consumer, cách ly/risk mitigation có hạn và quyết định sunset rõ.

## 22. Troubleshooting

### 22.1. `UnsupportedClassVersionError` trên Java 8

**Nguyên nhân:** hiện đại adapter hoặc transitive JAR major 65 lọt vào legacy graph.

**Xử lý:** xác định JAR chứa class, xem class major, dependency tree, runtime classpath và packaging. Chọn legacy artifact; không chỉ đổi `--release 8` của app.

### 22.2. `NoSuchMethodError` dù đều target Java 8

**Nguyên nhân:** binary API của shared library hoặc dependency thay đổi.

**Xử lý:** so sánh API versions thực tế được compile và chạy; dùng binary compatibility checker, giữ method cũ hoặc phát hành breaking version rõ.

### 22.3. `ServiceConfigurationError`

**Nguyên nhân:** provider class không tìm thấy, constructor không phù hợp, SPI descriptor sai hoặc module path/service declaration thiếu.

**Xử lý:** mở artifact cuối, đọc `META-INF/services`, kiểm tra tên class/module và runtime dependencies.

### 22.4. Có hai providers

**Nguyên nhân:** cả legacy và modern JAR cùng được bundle.

**Xử lý:** chỉ đưa một provider vào mỗi distribution, hoặc có selection policy tường minh được test.

### 22.5. MR-JAR không chọn class mới

**Nguyên nhân:** thiếu `Multi-Release: true`, đặt sai `META-INF/versions/21`, class loader/tooling không hỗ trợ đúng MR behavior.

**Xử lý:** xác minh manifest, layout và chạy thử bằng JVM đích trên JAR cuối.

### 22.6. MR-JAR bị scanner từ chối

**Nguyên nhân:** scanner chỉ kiểm tra maximum class major mà không hiểu versioned entries.

**Xử lý:** dùng kiểm tra MR-aware cho base và từng directory versioned.

### 22.7. Adapter mới làm lỗi HTTP/DB

**Nguyên nhân:** behavioral contract khác như redirects, timeout, TLS, concurrency hoặc connection pool.

**Xử lý:** contract/integration tests, giới hạn resource và rollout có quan sát; không xem interface compile thành công là đã tương thích.

### 22.8. App Java 8 chạy tốt ở IDE nhưng production lỗi

**Nguyên nhân:** IDE chạy JDK mới; production dùng Java 8 và dependency graph/agent khác.

**Xử lý:** CI chạy JDK thấp nhất, container hoặc VM sát production, kiểm tra Java launcher và binary thực tế.

### 22.9. Maven profile chọn sai adapter

**Nguyên nhân:** kích hoạt theo JDK chạy Maven, không theo deployment target.

**Xử lý:** explicit release profile/coordinates và verify distribution composition.

### 22.10. Legacy branch lâu ngày không nhận bản vá

**Nguyên nhân:** không có owner, quy trình backport và sunset.

**Xử lý:** khôi phục policy bảo trì hoặc chấm dứt hỗ trợ theo kế hoạch có thông báo; không mặc định branch cũ tự an toàn.

## 23. Quy trình migration từng bước

### Bước 1: Lập inventory

Xác định current JDK, target JDK, consumer/version, framework, API, protocol, native dependencies và support deadlines.

### Bước 2: Chọn ranh giới adapter

Chỉ đưa JDK-specific API vào implementation module. Shared API phải được biên dịch và thực thi trên mức JDK thấp nhất được hỗ trợ.

### Bước 3: Viết contract tests trước

Đóng băng behavior về input/output, exceptions, timeout, cancellation, data và resource lifecycle.

### Bước 4: Tách implementation hiện hành

Chuyển code cũ sang legacy adapter mà không đổi semantics; test trên JVM cũ trước.

### Bước 5: Thêm modern implementation

Dùng tính năng JDK mới khi có lợi ích cụ thể. Đừng nhân bản business logic không phụ thuộc JDK.

### Bước 6: Quy định cách chọn provider

Chọn DI, SPI, artifact coordinates hoặc MR-JAR. Đảm bảo mỗi distribution có kết quả selection dự đoán được.

### Bước 7: Chặn dependency quá mới trong legacy graph

Kiểm tra class-file major và JDK support của toàn bộ transitive dependencies, plugins và agents.

### Bước 8: Tạo CI matrix

Build, test và package cả hai variants. Chạy legacy trên Java 8, modern trên Java 21; thêm OS/architecture cần thiết.

### Bước 9: Canary và rollback

Theo dõi hiệu năng/behavior, giữ artifact cũ nguyên vẹn và xác nhận data/protocol compatibility hai chiều nếu bắt buộc rolling deployment.

### Bước 10: Sunset

Xác nhận đã nâng toàn bộ consumer, chấm dứt backport theo policy và loại bỏ những adapters/branches hết vòng đời.

## 24. Bài tập thực hành

### Bài tập 1: Định nghĩa ranh giới

Một thư viện Java 8 có public API trả về `java.net.http.HttpResponse` sau khi nhóm nâng sang JDK 21. Hãy giải thích vì sao thay implementation nhưng giữ chữ ký đó vẫn phá Java 8, rồi thiết kế DTO hoặc interface chung dùng types Java 8.

### Bài tập 2: Hai implementations cho task execution

Tạo `task-api`, `task-adapter-jdk8` và `task-adapter-jdk21` theo ví dụ. Build bằng JDK 21, dùng `--release 8`/`--release 21` tương ứng. Chạy contract tests trên Java 8 và 21 thật.

### Bài tập 3: ServiceLoader

Đóng gói legacy provider, rồi thử thêm modern provider vào cùng distribution. Quan sát kết quả của `loadExactlyOne()`, đề xuất rule kiểm tra artifacts trong CI để ngăn multiple providers.

### Bài tập 4: Multi-release JAR

Thiết kế MR-JAR với base Java 8 và class thay thế Java 21. Xác định compiler targets, manifest, layout, API contract, các test ở Java 8/17/21 và trường hợp cần chọn hai artifacts thay thế.

### Bài tập 5: Release branches

Một partner chỉ nâng được Java 8 sau 12 tháng, còn ứng dụng nội bộ đã cần Java 21. Hãy đề xuất support horizon, backport policy, dependency security process, release metadata và tiêu chí sunset.

### Bài tập 6: Binary mismatch

Một consumer biên dịch với `MessageCodec.encode(String): byte[]` nhưng library mới đổi method thành `encode(CharSequence): ByteBuffer`. Xác định source/binary break, giải thích vì sao một JDK adapter không tự sửa và đưa ra kế hoạch API migration.

## 25. Checklist trước khi phát hành

### Kiến trúc

- [ ] Có danh sách consumer và minimum JDK được cam kết.
- [ ] Shared API không có types/cú pháp chỉ tồn tại trên JDK mới.
- [ ] Contract tests dùng chung cho mọi adapters.
- [ ] Implementation modules chỉ chứa khác biệt cần thiết.
- [ ] Có quyết định rõ giữa adapters, MR-JAR, artifact lines và branches.
- [ ] Có owner và lịch sunset của legacy support.

### Build

- [ ] Maven/Gradle và JDK toolchains được pin.
- [ ] `--release` đúng cho API và từng implementation.
- [ ] Dependency closure legacy không chứa bytecode hoặc API quá mới.
- [ ] BOM, version catalogs, locks được quản lý theo variant.
- [ ] Service descriptors/JPMS declarations hợp lệ.
- [ ] Không vô tình bundle cả hai providers.
- [ ] Fat/nested JAR và MR-JAR được kiểm tra theo layout thực tế.

### Runtime và protocol

- [ ] Legacy artifact chạy tests trên minimum JDK thật.
- [ ] Modern artifact chạy tests trên target JDK thật.
- [ ] Có test binary compatibility khi cần hỗ trợ consumers chưa biên dịch lại.
- [ ] Concurrency, errors, timeouts và shutdown giữ contract.
- [ ] Java agents/native libraries/framework integrations được kiểm tra.
- [ ] Dữ liệu và protocol được thử với producer/consumer lệch phiên bản.
- [ ] Rollback không phụ thuộc giả định sai về database/schema.

### Phát hành

- [ ] Artifacts có version và checksums không bị ghi đè.
- [ ] Có SBOM/security review riêng cho legacy/modern variants.
- [ ] Release notes công bố minimum và tested JDK rõ ràng.
- [ ] Có canary, monitoring, rollback và runbook.
- [ ] Có quy trình backport và dừng legacy maintenance.

## Kết luận

Khi hỗ trợ nhiều JDK, giải pháp bền vững thường không phải viết `if (javaVersion >= ...)` ở mọi nơi. Hãy giữ một **hợp đồng chung tương thích JDK thấp nhất**, cô lập những API/runtime khác biệt phía sau adapter, rồi cung cấp implementation phù hợp cho từng consumer. Với chênh lệch nhỏ và public API giống nhau, multi-release JAR có thể hợp lý; khi framework, dependencies hoặc release lifecycle phân kỳ lớn, nên chọn artifact lines hoặc release branches riêng.

Chất lượng migration được quyết định bởi toàn bộ **dependency closure**, **runtime tests thực tế**, **source/binary/data compatibility** và **kế hoạch sunset**, không chỉ bởi việc biên dịch thành công. Một lộ trình có adapter, release rõ ràng, CI matrix và rollback giúp ứng dụng Java cũ và mới cùng tồn tại trong thời gian chuyển đổi mà không buộc mọi hệ thống nâng cấp cùng lúc.

