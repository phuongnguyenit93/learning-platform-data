# ResourceLock hoặc cơ chế khóa theo khả năng của JUnit

## 1. Bối cảnh: cô lập tài nguyên khi Spring Boot tests chạy song song

Trong một dự án Spring Boot, kiểm thử riêng từng class thường xanh, nhưng khi bật JUnit parallel execution, một số phép kiểm lại thất bại không ổn định. Nguyên nhân nhiều khi không nằm ở business code mà nằm ở **test interference**: nhiều phép kiểm chia sẻ mutable state rồi sửa nó gần như đồng thời.

Ví dụ thường gặp:

- Hai tests đều gọi `System.setProperty("app.mode", ...)`.
- Các test thay đổi `Locale.setDefault(...)`, timezone mặc định hoặc `System.out`.
- Hai lớp `@SpringBootTest` có cùng cached `ApplicationContext` và cùng singleton stateful.
- Nhiều tests thao tác cùng file xuất báo cáo hoặc thư mục cố định.
- Một test reset bảng DB trong `@BeforeEach` đúng lúc test khác đọc bản ghi.
- Các lớp test dùng chung Kafka topic/consumer group, RabbitMQ queue hoặc Redis keys.
- `@MockBean` bị reset hoặc restub giữa hai HTTP requests đang chạy.
- Một test trả về trước khi async task hoàn thành, làm background worker ghi vào dữ liệu của phép kiểm tiếp theo.

Mục tiêu **không phải tắt toàn bộ parallelism**. Cần hiểu phần state nào có thể tránh chia sẻ, phần nào phải giữ chung, rồi đồng bộ **chỉ những test đang cạnh tranh trên cùng một tài nguyên**.

JUnit Jupiter có `@ResourceLock`, mô tả tài nguyên bằng **một khóa tên kiểu String**. Khi một phép kiểm yêu cầu READ hay READ_WRITE trên tài nguyên đó, JUnit engine sử dụng metadata này để tránh các test nodes có yêu cầu xung đột chạy đồng thời. Đây là khóa **lịch thực thi kiểm thử**, không phải mutex mà Spring tự đưa vào code production.

**Đề bài chính:** “ResourceLock hoặc cơ chế khóa theo khả năng của JUnit”, ngữ cảnh cha **Cách ly và chạy song song**. Sau bài học, bạn cần:

1. Hiểu `@ResourceLock`, `ResourceAccessMode.READ`, `READ_WRITE` và key identity.
2. Biết `@ResourceLock` bảo vệ luôn `@BeforeEach` và `@AfterEach` của phương thức được đánh dấu.
3. Khóa giữa **nhiều lớp test khác nhau** khi chúng cùng dùng một shared resource key.
4. Phân biệt method-level với class-level lock và biết cách khai báo nhiều locks cho một test.
5. Cấu hình `junit.jupiter.execution.parallel.enabled`, class/method execution mode và fixed parallelism.
6. Hiểu `@Execution(CONCURRENT)` cho phép chạy đồng thời nhưng không cam kết hai test chắc chắn overlap.
7. Biết lúc nào chọn `@Execution(SAME_THREAD)`, `@Isolated`, `@TempDir` hoặc data isolation thay cho ResourceLock.
8. Xử lý JVM globals đúng: system properties, stdout/stderr, default locale/timezone; restore trạng thái ban đầu.
9. Hiểu cùng `@SpringBootTest` configuration có thể chia sẻ Spring singleton qua TestContext cache.
10. Tránh khóa `READ` nếu setup/teardown hoặc operation có implicit write.
11. Tránh nhầm khóa JUnit với database advisory lock, Java lock hoặc distributed lock.
12. Đưa ví dụ hoàn chỉnh **Java 17 + Spring Boot 3.3.5 + Gradle**, gồm **12 phương thức JUnit Jupiter `@Test`**.
13. Biết giới hạn với Gradle forks/multi-module CI, @DirtiesContext, @MockBean, @Async và @Scheduled.
14. Đánh giá hiệu quả của locking bằng tỷ lệ flaky và suite runtime, không bằng `Thread.sleep` hay khẳng định thời gian đo chưa thực thi.

**Stack cố định:** Java 17, Spring Boot **3.3.5**, Spring Framework 6.1, JUnit Jupiter do Boot quản lý. Bài chỉ dùng JUnit `@ResourceLock(value, mode)`, `Resources` và `@Isolated` vốn sẵn có trong nhánh 5.10.x. Những options mới của `@ResourceLock` như `target` và `providers` thuộc **JUnit 5.12+**, **không được sử dụng trong project runnable** để giữ tính tương thích với Boot 3.3.

## 2. Phân biệt bốn loại vấn đề

| Vấn đề | Ví dụ | Công cụ nên cân nhắc |
|---|---|---|
| **Test isolation** | Test A để lại property, B thấy giá trị cũ | Restore state; ResourceLock nếu cả hai chia sẻ |
| **Race trong chính ứng dụng** | Hai request cùng trừ tồn kho bị lost update | Atomic DB update, transaction, optimistic lock và concurrent integration test |
| **Thực thi song song** | Chạy nhiều tests trên JUnit workers | JUnit parallel config, `@Execution` |
| **Cạnh tranh cross-process** | Hai Gradle forks hoặc CI jobs cùng dùng test DB | Unique schema/container/namespace, DB lock hoặc distributed coordination |

ResourceLock dành cho **test interference** giữa những JUnit nodes đã tham gia cùng một thỏa thuận key. Nó **không thể biến một service vốn không thread-safe thành thread-safe ở production**. Nếu bạn bảo vệ tất cả các test gọi một service bằng READ_WRITE rồi kết luận service an toàn dưới nhiều HTTP requests đồng thời, đó là suy luận sai: JUnit đã **tuần tự hóa** chính tình huống cần quan sát.

### 2.1. Phản mẫu không có khóa

~~~java
// Hai JUnit test methods minh họa; chúng cạnh tranh khi chạy concurrent.
@Test
void alpha() {
    System.setProperty("demo.mode", "alpha");
    assertEquals("alpha", System.getProperty("demo.mode"));
}

@Test
void beta() {
    System.setProperty("demo.mode", "beta");
    assertEquals("beta", System.getProperty("demo.mode"));
}
~~~

Một interleaving có thể khiến `alpha` fail:

~~~text
JUnit worker T1                   JUnit worker T2
setProperty("demo.mode","alpha")
                                  setProperty("demo.mode","beta")
getProperty("demo.mode") -> beta
assertEquals(alpha, beta) -> FAIL
                                  assertEquals(beta,beta) -> PASS
~~~

Hai methods còn để lại property `demo.mode` cho test thứ ba. Dù cho concurrency được khóa, bạn vẫn phải restore state. Nếu test B dùng một `synchronized(this)` ở test instance khác, hai locks Java **không giống nhau**, nên không giải quyết cạnh tranh.

## 3. Cơ chế `@ResourceLock` trên JUnit Jupiter

`org.junit.jupiter.api.parallel.ResourceLock` là annotation áp dụng cho **test method hoặc test class**. Tài nguyên được nhận diện bằng **exact string key** (`value`), kèm access mode. Giá trị mặc định của `mode` là `ResourceAccessMode.READ_WRITE`.

~~~java
@Test
@ResourceLock("inventory-fixture")
void modifyInventory() {
    // Mặc định là READ_WRITE.
}

@Test
@ResourceLock(
        value = "inventory-fixture",
        mode = ResourceAccessMode.READ)
void inspectInventory() {
    // Chỉ đọc, kể cả setup/teardown.
}
~~~

Đây là snippet chú giải; imports bao gồm JUnit Jupiter `Test`, `ResourceLock`, `ResourceAccessMode`. Một key `"Inventory-Fixture"` khác `"inventory-fixture"`. JUnit **không biết hai tên này đang chỉ cùng DB table**: mọi class/test liên quan phải thống nhất giá trị.

### 3.1. Ma trận READ / READ_WRITE

| Test A giữ tài nguyên X | Test B yêu cầu READ(X) | Test B yêu cầu READ_WRITE(X) |
|---|---|---|
| `READ(X)` | Có thể cùng chạy | B phải chờ A |
| `READ_WRITE(X)` | B phải chờ A | B phải chờ A |
| Không giữ X | Không có xung đột theo X | Không có xung đột theo X |

**Hai READ không bắt buộc chạy đồng thời**, chỉ **được phép** nếu scheduler còn workers và không có resource khác xung đột. **READ_WRITE không cam kết thứ tự chạy**: writer A không nhất thiết chạy trước writer B, và không có guarantee công khai về fairness giữa readers/writers.

**Không chọn READ chỉ vì HTTP method là GET.** Một GET có thể ghi audit log, cập nhật cache, ghi `lastSeenAt` hoặc lazy-load state. Đánh giá side effects thực tế của toàn bộ test, bao gồm `@BeforeEach` và `@AfterEach`.

### 3.2. Lock bao trùm các lifecycle callbacks

Với method-level annotation:

~~~java
@BeforeEach
void prepare() {
    sharedStore.reset();
}

@Test
@ResourceLock("shared:store")
void verifyStore() {
    assertEquals(1, sharedStore.next());
}

@AfterEach
void cleanup() {
    sharedStore.reset();
}
~~~

Đoạn code là snippet trong một class giả định có `sharedStore`; `@ResourceLock` ở **method có `@Test`**, không phải ở callback. JUnit giữ khóa **trước** khi `@BeforeEach` chạy và chỉ giải phóng **sau** khi `@AfterEach` hoàn tất.

~~~text
Acquire READ_WRITE("shared:store")
  |
  +-- @BeforeEach: reset fixture
  +-- @Test: assertions và mutations
  +-- @AfterEach: cleanup/reset
  |
Release READ_WRITE("shared:store")
~~~

Đây là điểm mạnh so với `synchronized` đặt **chỉ trong thân test**: một phép kiểm khác không thể chen vào giữa setup và cleanup nếu nó khai báo cùng resource key. Tuy nhiên, việc gắn lock **không tự reset** tài nguyên; bạn vẫn phải cleanup hoặc rollback.

### 3.3. Class-level, method-level và repeatable

Khi tất cả test methods đều dùng cùng resource, bạn có thể gắn ở class:

~~~java
@Execution(ExecutionMode.CONCURRENT)
@ResourceLock(
        value = "configuration:shared",
        mode = ResourceAccessMode.READ_WRITE)
class ConfigurationChecks {

    @Test
    void scenarioA() { }

    @Test
    void scenarioB() { }
}
~~~

Snippet trên là một class JUnit rút gọn. Class-level locking đơn giản và bao quát lifecycle liên quan, nhưng có thể **giảm khả năng parallelize**, vì toàn bộ class được xem như sử dụng resource. Khi chỉ vài methods thực sự mutate, method-level annotations thường cho granularity tốt hơn.

Một test dùng hai shared resources có thể khai báo hai annotations:

~~~java
@Test
@ResourceLock("database:orders")
@ResourceLock("cache:orders")
void changesDatabaseAndCache() {
    // JUnit biết test này cần cả hai named resources.
}
~~~

Các annotations là repeatable; không cần tự tạo Java `ReentrantLock` cho mỗi annotation. Đừng dùng một khóa chung `"EVERYTHING"` cho cả suite nếu hai resources độc lập: nó sẽ tuần tự hóa những việc không xung đột.

**Chú ý version:** Trong JUnit Jupiter 5.10.x, `@ResourceLock` chỉ có các thuộc tính `value`/`mode` dùng ở bài. Khi đọc tài liệu JUnit latest, có thể thấy `target=CHILDREN` hoặc `providers=...` được bổ sung từ 5.12. **Không copy options này vào code Boot 3.3.5 mà chưa nâng Jupiter**.

## 4. Các predefined keys và quy ước đặt tên

JUnit định nghĩa các `Resources` phổ biến:

| Tên constant | Đối tượng |
|---|---|
| `Resources.SYSTEM_PROPERTIES` | `java.lang.System` properties |
| `Resources.SYSTEM_OUT` | `System.out` |
| `Resources.SYSTEM_ERR` | `System.err` |
| `Resources.LOCALE` | JVM default locale |
| `Resources.TIME_ZONE` | JVM default timezone |

Ví dụ:

~~~java
@Test
@ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE)
void temporarilyChangeProperty() {
    String old = System.getProperty("demo.mode");
    try {
        System.setProperty("demo.mode", "test");
        assertEquals("test", System.getProperty("demo.mode"));
    } finally {
        if (old == null) {
            System.clearProperty("demo.mode");
        } else {
            System.setProperty("demo.mode", old);
        }
    }
}
~~~

Snippet cần imports JUnit và `Resources`; source runnable của phần 8 có ví dụ đầy đủ hơn. **Dùng cùng key** ở mọi tests chạm global state. `Resources.SYSTEM_PROPERTIES` có scope rộng hơn `"demo.mode"`: nếu test nào cũng đang đổi những properties **độc lập**, có thể dùng keys chi tiết để tăng parallelism, nhưng phải đảm bảo code under test không đọc/ghi những properties khác hoặc cả bảng `System.getProperties()` như một đơn vị.

Nếu resource key tự định nghĩa, quy ước nên mô tả **scope va chạm**:
- `"spring:sequence-fixture"` cho bean singleton của các classes.
- `"db:shop-test:orders"` cho bảng chung trong một schema.
- `"file:build/shared/export.csv"` cho file dùng chung.
- `"broker:orders-test:queue"` cho queue.
- `"cache:orders-global"` cho namespace cache.

**Quá hẹp**: Writer A dùng `"db:orders:table"` và Writer B dùng `"db:orders"` nhưng cùng mutate bảng `orders` → JUnit coi khác. **Quá rộng**: mọi test dùng `"GLOBAL"` → gần như tắt parallelism. Nên centralize resource keys bằng compile-time constants ở dự án lớn để tránh typo. Một test có thể dùng lock trên DB và cache cùng lúc khi cả hai có thể bị tác động.

## 5. Cấu hình chạy song song: JUnit khác Gradle forks

Jupiter không mặc định bật toàn bộ test parallelism. Ví dụ file `src/test/resources/junit-platform.properties`:

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=4
~~~

- `enabled=true`: JUnit parallel scheduler được bật.
- `mode.default=concurrent`: các methods có thể concurrent nếu phù hợp.
- `mode.classes.default=concurrent`: classes cũng có thể concurrent.
- `fixed.parallelism=4`: giới hạn mức parallelism mục tiêu trong Jupiter engine.
- `@Execution(CONCURRENT)` khai báo cho phép chạy song song trong class hoặc method.
- `@Execution(SAME_THREAD)` buộc test node chạy trên thread của parent theo Jupiter semantics. **Không** dùng nó như một global mutex giữa classes.

`@TestInstance(PER_METHOD)` là default của JUnit Jupiter, giúp mỗi test method có một **test class instance riêng**, nhưng không tách static fields, Spring singleton hoặc DB. Với `@TestInstance(PER_CLASS)` hoặc `@TestMethodOrder`, JUnit có các ngoại lệ về parallel execution mode; cần cân nhắc `@Execution(CONCURRENT)` và mức thread safety thật của instance fields.

### 5.1. Đừng dùng test order để chữa race

Một `@ResourceLock(READ_WRITE)` đảm bảo hai tests có cùng key **không overlap**, nhưng không đảm bảo A chạy trước B. Nếu A tạo dữ liệu mà B dựa vào, tests đã bị **phụ thuộc thứ tự**. Hãy chuyển setup dữ liệu vào `@BeforeEach` hoặc fixture riêng, hoặc gộp các bước của một workflow vào một integration test duy nhất.

`@TestMethodOrder` chỉ điều khiển ordering theo policy JUnit, không tự ngăn class khác thay shared state. Với Spring parallel tests, ordered tests còn là nhóm cần thận trọng về test independence.

### 5.2. Một JVM JUnit khác nhiều JVM Gradle

`@ResourceLock` được quản lý bên trong JUnit execution plan trong một process/test JVM. Gradle có thể chạy nhiều JVM workers nếu `maxParallelForks` lớn hơn 1 hoặc `forkEvery` khiến worker được khởi tạo lại.

~~~text
JVM #1                                   JVM #2
@ResourceLock("db:test:orders")           @ResourceLock("db:test:orders")
      |                                          |
  Khóa nội bộ JUnit #1                      Khóa nội bộ JUnit #2
      |                                          |
  Truy vấn PostgreSQL chung <----> Truy vấn PostgreSQL chung

Không có mutual exclusion xuyên hai JVM dù key string giống nhau.
~~~

Đối với external DB/broker cùng được nhiều forks/CI jobs dùng, cần unique schema/tenant/test IDs/container hoặc cross-process coordination. Không thể chỉ đặt cùng tên `@ResourceLock` rồi kỳ vọng một khóa distributed xuất hiện.

### 5.3. Parallelism không phải một assertion thời gian

Không đoán rằng hai READ tests sẽ chạy *thực sự overlap* chỉ vì chúng có cùng READ key. Scheduler, CI load và CPU quotas có thể khiến chúng chạy nối tiếp. Tránh `Thread.sleep(50)` như một bằng chứng concurrency. Nếu cần test **thuật toán concurrent**, dùng executor nhiều worker, `CountDownLatch`/`CyclicBarrier`, timeout hữu hạn và business invariants — đó là một bài test khác với locking test fixtures.

## 6. Chọn khóa, cách ly dữ liệu, hay chạy class độc lập?

| Cơ chế | Khi nên chọn | Giới hạn |
|---|---|---|
| **`@ResourceLock(K, READ_WRITE)`** | Một shared resource thực sự phải có người viết độc quyền | Chỉ giữa những Jupiter test nodes khai báo K trong cùng process/plan |
| **`@ResourceLock(K, READ)`** | Những readers thực sự không mutate kể cả setup/teardown | Có thể cùng chạy, không đi cùng writer trên K |
| **`@Isolated`** | Một class phải loại trừ **các class khác** trong Jupiter plan | Khóa rộng, giảm throughput; không chặn external threads/processes |
| `@Execution(SAME_THREAD)` | Cần chạy node trên thread của parent, hoặc per-class test state không parallel-safe | Không serialize mọi classes khác |
| **`@TempDir`** | Mỗi test tự quản file riêng | Không bảo vệ file/path bên ngoài temp dir |
| DB schema/container/unique IDs riêng | Multi-process/multi-JVM integration tests | Tốn setup, vẫn cần cleanup |
| `@Transactional` + rollback hoặc `@Sql` | Dữ liệu DB test được quản lý đúng transaction | HTTP/async/server writes có thể khác transaction |
| Mutex/JVM `synchronized` | Threads cùng JVM và cùng lock object | Không tự bao JUnit lifecycle nếu chỉ dùng trong thân test |
| DB advisory lock/distributed lease | Cross-process external resource thật sự chia sẻ | Timeout, crash recovery, consistency cần thiết kế |

**Định hướng:** Nếu có thể tránh chia sẻ file, records hoặc queues bằng fixture riêng thì **không cần khóa** và thường nhanh hơn. Nếu nhiều tests phải dùng một Spring singleton hoặc một global property, dùng `@ResourceLock` mức nhỏ nhất bao hết phần mutate. Dùng `@Isolated` cho những thay đổi global khó inventory hết readers.

## 7. Project Java 17 + Spring Boot 3.3.5: đầy đủ và có thể chạy

Project gồm một Spring singleton mutable **chỉ để minh họa test interference**, hai lớp writer, một lớp reader, test system properties, test temp directories và một class `@Isolated` cho default locale.

**Chính sách của ví dụ:**
- Writers phải có `READ_WRITE("demo:sequence")`.
- Readers chỉ dùng `READ("demo:sequence")`, **không reset state**.
- Mọi writer method đặt `@BeforeEach`/`@AfterEach` reset dữ liệu và được JUnit bảo vệ xuyên suốt.
- `SystemPropertiesLockTest` khai báo lock ở **class level** vì cả class thay system properties.
- `IndependentTempDirectoryTest` **không dùng lock**, vì hai files là hai paths tách biệt.
- `GlobalLocaleIsolatedTest` dùng `@Isolated` và luôn restore default locale.
- Không dựa vào thứ tự phương thức hoặc các lớp test.
- **12 JUnit Jupiter tests** trong 6 classes, không có intentionally failing tests.

### 7.1. Cây thư mục

~~~text
settings.gradle
build.gradle
src/main/java/demo/locks/LockingDemoApplication.java
src/main/java/demo/locks/SharedSequence.java
src/test/resources/junit-platform.properties
src/test/java/demo/locks/SpringCounterATest.java
src/test/java/demo/locks/SpringCounterBTest.java
src/test/java/demo/locks/CounterReadersTest.java
src/test/java/demo/locks/SystemPropertiesLockTest.java
src/test/java/demo/locks/IndependentTempDirectoryTest.java
src/test/java/demo/locks/GlobalLocaleIsolatedTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'spring-junit-resource-lock'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    // Một worker JVM, nhưng nhiều JUnit Jupiter workers bên trong.
    maxParallelForks = 1
    forkEvery = 0

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**src/test/resources/junit-platform.properties**

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=4
~~~

`maxParallelForks=1` giữ **một JVM** để các classes cùng thấy JUnit resource keys; `fixed.parallelism=4` vẫn cho Jupiter điều phối một số nodes chạy concurrently **trong JVM đó**. Dù `maxParallelForks=1`, tổng số threads của Spring/GC vẫn có thể nhiều; không phải “JVM chỉ có một thread”.

`spring-boot-starter` đủ để tạo Spring ApplicationContext không cần HTTP server. `spring-boot-starter-test` chứa JUnit Jupiter và Spring TestContext; không cần khai báo trực tiếp JUnit engine version.

### 7.2. Spring Boot main class

**src/main/java/demo/locks/LockingDemoApplication.java**

~~~java
package demo.locks;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LockingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LockingDemoApplication.class, args);
    }
}
~~~

### 7.3. Singleton dùng chung để minh họa

**src/main/java/demo/locks/SharedSequence.java**

~~~java
package demo.locks;

import org.springframework.stereotype.Service;

@Service
public class SharedSequence {

    // Cố ý mutable và không synchronized để tạo fixture
    // mà các JUnit tests cần sử dụng dưới cùng một resource key.
    private int value;

    public void reset() {
        value = 0;
    }

    public int next() {
        return ++value;
    }

    public int current() {
        return value;
    }
}
~~~

**Cảnh báo production:** `++value` không phải atomic read-modify-write khi nhiều threads thật sự cùng gọi; đây là **demo fixture**, không phải một singleton nên chép vào backend production. Nếu ứng dụng cần concurrency thật, dùng stateless service, transaction, database atomic update hoặc primitive đồng bộ phù hợp. JUnit `@ResourceLock` chỉ bảo vệ những test nodes hợp tác khai báo cùng key.

Hai Spring test classes với **cùng `@SpringBootTest(webEnvironment=NONE)`** thường reuse Spring TestContext cached ApplicationContext và do đó chia sẻ singleton `SharedSequence`. Nhưng nếu profiles/test properties/customizers khác, cache key cũng có thể khác. **Khóa JUnit không phải bằng chứng hai classes đã share context**; nếu cần chứng minh reuse, kiểm bean reference hoặc Spring context cache stats riêng.

## 8. Hai writer test classes: READ_WRITE xuyên qua setup và teardown

### 8.1. SpringCounterATest: 3 tests

**src/test/java/demo/locks/SpringCounterATest.java**

~~~java
package demo.locks;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Execution(ExecutionMode.CONCURRENT)
class SpringCounterATest {

    @Autowired
    SharedSequence sequence;

    // Các methods @Test bên dưới đều có lock "demo:sequence".
    @BeforeEach
    void prepare() {
        sequence.reset();
        assertEquals(0, sequence.current());
    }

    @AfterEach
    void cleanup() {
        sequence.reset();
    }

    @Test
    @ResourceLock(
            value = "demo:sequence",
            mode = ResourceAccessMode.READ_WRITE)
    void initialIncrementIsOne() {
        assertEquals(1, sequence.next());
        assertEquals(1, sequence.current());
    }

    @Test
    @ResourceLock(
            value = "demo:sequence",
            mode = ResourceAccessMode.READ_WRITE)
    void threeCallsProduceConsecutiveNumbers() {
        assertEquals(1, sequence.next());
        assertEquals(2, sequence.next());
        assertEquals(3, sequence.next());
        assertEquals(3, sequence.current());
    }

    @Test
    @ResourceLock("demo:sequence")
    void resettingWithinProtectedMethodIsValid() {
        assertEquals(1, sequence.next());
        sequence.reset();
        assertEquals(0, sequence.current());
        assertEquals(1, sequence.next());
    }
}
~~~

**Đúng 3 `@Test`.** Hai methods đầu khai rõ READ_WRITE, method cuối sử dụng dạng rút gọn vì READ_WRITE là **default mode**. Mỗi method có lock được cấp trước `@BeforeEach` và giải phóng sau `@AfterEach`; vì thế việc reset của class A không chen vào thân test của class B nếu B khai báo cùng key.

**Vì sao class vẫn có `@Execution(CONCURRENT)`?** Để cho phép JUnit parallel scheduler xử lý nhiều tests khi có tài nguyên độc lập; **những method cùng WRITE key vẫn phải chờ nhau**. Không nên assert chúng bắt đầu cùng lúc. Dù 3 methods dùng cùng resource, JUnit không hứa một thứ tự chạy cụ thể.

### 8.2. SpringCounterBTest: 2 tests

**src/test/java/demo/locks/SpringCounterBTest.java**

~~~java
package demo.locks;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Execution(ExecutionMode.CONCURRENT)
class SpringCounterBTest {

    @Autowired
    SharedSequence sequence;

    @BeforeEach
    void prepare() {
        sequence.reset();
    }

    @AfterEach
    void cleanup() {
        sequence.reset();
    }

    @Test
    @ResourceLock(
            value = "demo:sequence",
            mode = ResourceAccessMode.READ_WRITE)
    void otherClassAlsoStartsFromOne() {
        assertEquals(1, sequence.next());
        assertEquals(1, sequence.current());
    }

    @Test
    @ResourceLock(
            value = "demo:sequence",
            mode = ResourceAccessMode.READ_WRITE)
    void otherClassCanAdvanceAndReset() {
        assertEquals(1, sequence.next());
        assertEquals(2, sequence.next());
        assertEquals(2, sequence.current());
    }
}
~~~

**Đúng 2 `@Test`.** B và A không chia sẻ Java test object instance, nhưng có thể chia sẻ **Spring singleton bean** từ cached context. Resource key `"demo:sequence"` là tên chung cho cả hai; không cần tạo một `ReentrantLock` trong mỗi test class.

Một typo như `"demo:sequences"` ở B tạo **một resource khác**; JUnit sẽ không biết hai keys tương ứng với cùng bean. Trong production test suite lớn, định nghĩa một compile-time constant `public static final String SEQUENCE = "demo:sequence";` trong test utilities class rồi dùng thống nhất.

## 9. Reader test class: READ nhưng không thay đổi shared fixture

**src/test/java/demo/locks/CounterReadersTest.java**

~~~java
package demo.locks;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Execution(ExecutionMode.CONCURRENT)
class CounterReadersTest {

    @Autowired
    SharedSequence sequence;

    @Test
    @ResourceLock(
            value = "demo:sequence",
            mode = ResourceAccessMode.READ)
    void readerObservesCleanBaseline() {
        assertEquals(0, sequence.current());
    }

    @Test
    @ResourceLock(
            value = "demo:sequence",
            mode = ResourceAccessMode.READ)
    void multipleReadsDoNotAlterState() {
        int a = sequence.current();
        int b = sequence.current();

        assertEquals(0, a);
        assertEquals(a, b);
    }
}
~~~

**Đúng 2 `@Test`.** Hai readers dùng cùng READ key, được phép chạy đồng thời với nhau nhưng **không overlap với các writer** có READ_WRITE key `"demo:sequence"`. Chúng không dùng `@BeforeEach` để reset, vì một reset là write — khi đó mode READ là sai.

Khi reader nhận lock sau một writer, `@AfterEach` của writer đã chạy dưới READ_WRITE lock và đặt counter về 0. Vì vậy assertions về giá trị 0 là hợp lý trong **bộ fixtures cụ thể này**. Nếu code khác tự tạo background thread sửa `SharedSequence`, hoặc một test khác không khai báo lock, đảm bảo này sẽ không còn. `@ResourceLock` không tự cấp khóa cho application threads.

**READ không phải cam kết hai tests đã overlap.** Để test điều đó, cần một phép kiểm scheduler/concurrency riêng bằng latch và bounded waits, không được suy từ annotation.

## 10. Class-level lock với JVM system properties

**src/test/java/demo/locks/SystemPropertiesLockTest.java**

~~~java
package demo.locks;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

import static org.junit.jupiter.api.Assertions.*;

@Execution(ExecutionMode.CONCURRENT)
@ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE)
class SystemPropertiesLockTest {

    private static final String KEY =
            "demo.resource-lock.sample-mode";

    private String previous;

    @BeforeEach
    void saveOldValue() {
        previous = System.getProperty(KEY);
    }

    @AfterEach
    void restoreOldValue() {
        if (previous == null) {
            System.clearProperty(KEY);
        } else {
            System.setProperty(KEY, previous);
        }
    }

    @Test
    void canSetAlphaForOneMethod() {
        System.setProperty(KEY, "alpha");
        assertEquals("alpha", System.getProperty(KEY));
    }

    @Test
    void canSetBetaForAnotherMethod() {
        System.setProperty(KEY, "beta");
        assertEquals("beta", System.getProperty(KEY));
    }
}
~~~

**Đúng 2 `@Test`.** Ở đây cả class sử dụng system properties, nên class-level lock đơn giản và rõ. `@BeforeEach` lưu value cũ, `@AfterEach` restore; JUnit sẽ phối hợp với các tests khác khai báo cùng predefined `Resources.SYSTEM_PROPERTIES`.

**Giới hạn:**
- Chỉ những JUnit tests tham gia cùng resource key mới được scheduler đồng bộ.
- Background thread của Spring hoặc third-party code không tự chờ JUnit lock.
- Sửa một `System` property sau khi Spring đã tạo bean `@Value`/`@ConfigurationProperties` **không tự refresh bean đó**. Các properties ảnh hưởng wiring nên được cấu hình qua test profiles, `@TestPropertySource`, `@SpringBootTest(properties=...)` hoặc isolated context.
- Nên chọn property name không trùng các system settings của JVM/Java security trong ví dụ.
- Nếu một test thật sự thay nhiều global properties, có thể cần predefined key cho **cả bảng** hơn là một custom key quá hẹp.

## 11. `@TempDir`: tốt hơn là không chia sẻ file

**src/test/java/demo/locks/IndependentTempDirectoryTest.java**

~~~java
package demo.locks;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import static org.junit.jupiter.api.Assertions.*;

@Execution(ExecutionMode.CONCURRENT)
class IndependentTempDirectoryTest {

    @Test
    void firstTestHasOwnReport(@TempDir Path dir)
            throws Exception {

        Path file = dir.resolve("report.txt");

        Files.writeString(
                file, "first", StandardCharsets.UTF_8);

        assertEquals(
                "first",
                Files.readString(file, StandardCharsets.UTF_8));
    }

    @Test
    void secondTestHasOwnReport(@TempDir Path dir)
            throws Exception {

        Path file = dir.resolve("report.txt");

        Files.writeString(
                file, "second", StandardCharsets.UTF_8);

        assertEquals(
                "second",
                Files.readString(file, StandardCharsets.UTF_8));
    }
}
~~~

**Đúng 2 `@Test`.** Mặc dù cùng dùng filename `report.txt`, Jupiter cấp cho mỗi `@TempDir` method parameter một **temporary directory riêng**. Paths thực khác nhau; tests không xung đột nên **không cần lock**. Đây là một cách tăng khả năng parallelize tốt hơn việc serialize hai file writes vào một path chung.

Nếu app production code luôn ghi vào `build/reports/report.txt` bất chấp `@TempDir`, hai tests vẫn đụng nhau. Trong integration tests cần inject base output directory để code under test thật sự sử dụng path riêng. Với DB, tương đương là unique schema/test tenant/record IDs; với broker là unique topic/queue/group identifiers.

## 12. `@Isolated`: khi phải loại trừ toàn bộ các lớp khác

**src/test/java/demo/locks/GlobalLocaleIsolatedTest.java**

~~~java
package demo.locks;

import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Isolated;

import static org.junit.jupiter.api.Assertions.*;

@Isolated("Temporarily mutates JVM-wide default Locale")
class GlobalLocaleIsolatedTest {

    @Test
    void canChangeDefaultLocaleAndRestoreIt() {
        Locale original = Locale.getDefault();

        try {
            Locale vietnamese =
                    Locale.forLanguageTag("vi-VN");

            Locale.setDefault(vietnamese);

            assertEquals(vietnamese, Locale.getDefault());
            assertEquals("vi", Locale.getDefault().getLanguage());
        } finally {
            Locale.setDefault(original);
        }
    }
}
~~~

**Đúng 1 `@Test`.** `@Isolated` áp dụng **ở class**. Trong Jupiter test plan, class này không overlap với các test classes khác, ngay cả khi classes ấy không biết resource key. Điều đó phù hợp với một mutation JVM-global khó kiểm kê hết nơi đọc.

**Khác biệt quan trọng:** `@Isolated` vẫn không loại trừ một **background application thread**, một Gradle test worker JVM khác hoặc một CI pipeline job. Nó cũng không tự restore Locale: `finally` vẫn cần thiết. Nếu tất cả tests dùng Locale đều có thể khai báo `Resources.LOCALE`, một method-level `@ResourceLock` trên key ấy sẽ hẹp hơn và thường giữ được parallelism tốt hơn.

## 13. Tổng cộng 12 JUnit tests và lệnh chạy

| Lớp | `@Test` | Điều được kiểm |
|---|---:|---|
| `SpringCounterATest` | 3 | Mutate/reset singleton dưới method-level READ_WRITE |
| `SpringCounterBTest` | 2 | Khóa cùng key xuyên classes |
| `CounterReadersTest` | 2 | Chỉ READ, không mutate |
| `SystemPropertiesLockTest` | 2 | Class-level `Resources.SYSTEM_PROPERTIES`, cleanup |
| `IndependentTempDirectoryTest` | 2 | `@TempDir` không cần shared lock |
| `GlobalLocaleIsolatedTest` | 1 | `@Isolated` và restore JVM default Locale |
| **Tổng** | **12** | Không có `@Disabled`, không phụ thuộc thứ tự |

Chạy project nếu đã có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu bạn chỉ sao chép source files, `settings.gradle`, `build.gradle` nhưng **chưa tạo Wrapper scripts/JAR**, lệnh `./gradlew` chưa tồn tại. Có thể chạy `gradle test` với Gradle tương thích hoặc tạo Gradle Wrapper trước.

Chạy các lớp riêng:

~~~bash
./gradlew test --tests demo.locks.SpringCounterATest
./gradlew test --tests demo.locks.SpringCounterBTest
./gradlew test --tests demo.locks.CounterReadersTest
./gradlew test --tests demo.locks.SystemPropertiesLockTest
./gradlew test --tests demo.locks.IndependentTempDirectoryTest
./gradlew test --tests demo.locks.GlobalLocaleIsolatedTest
~~~

Báo cáo HTML thường nằm tại `build/reports/tests/test/index.html`. **Kết quả thiết kế mong đợi**: 12 test methods được JUnit Jupiter phát hiện và PASS, không có assertions phụ thuộc timing/order. Đây là kết quả **dự kiến từ source và API**, không phải tuyên bố đã thực thi Gradle.

**Chú ý:** Khi chạy từng class bằng các lệnh Gradle khác nhau, resource locks không chứng minh được phối hợp **xuyên classes**, vì mỗi lệnh có thể khởi tạo một test JVM mới. Muốn kiểm lock giữa writer classes A/B và readers C, chạy **toàn suite** với `maxParallelForks=1` như cấu hình đã nêu. Không test “cùng JVM” bằng cách chạy từng test riêng và ghép kết quả đo thời gian.

Không có stdout với thứ tự cố định khi JUnit parallel scheduler chạy. Tên threads và thứ tự hoàn thành tests có thể thay đổi; assert **behavior/invariant** chứ không chụp snapshot dòng log theo thứ tự.

## 14. Vì sao một test lock được thiết kế đúng vẫn có thể flaky?

### 14.1. Một test không tham gia key contract

Nếu classes A và B khai báo `"demo:sequence"` nhưng C dùng `"demo:sequences"`, JUnit có thể schedule C cùng A/B. Nếu C `@BeforeEach` reset singleton, assertion của A/B có thể thất bại. Lập danh sách **tất cả** tests chạm shared fixture, đưa key vào constants chung và review khi thêm test mới.

### 14.2. Khai báo READ nhưng có write gián tiếp

Test read response có thể gọi service GET làm update `lastAccessedAt`, audit log hoặc cache. `@BeforeEach` có thể truncate DB. JUnit chỉ thấy annotation READ, không tự inspect implementation. Nếu operation thực sự mutate, phải chọn READ_WRITE hoặc loại/tách write. READ mode không biến shared state thành immutable.

### 14.3. Worker hoạt động sau `@AfterEach`

Một `@Test` gọi `@Async void` và kết thúc trước khi task gửi message hoặc cập nhật DB. Sau `@AfterEach`, JUnit giải phóng resource lock, nhưng background task còn chạy; test tiếp theo có thể thay shared fixture trong khi worker cũ tiếp tục ghi.

Cách khắc phục:
- Ưu tiên `CompletableFuture`/`Future` có thể **chờ completion với timeout hữu hạn**.
- Khi có message listener, chờ điều kiện nghiệp vụ cụ thể hoặc dùng Awaitility/CountDownLatch có deadline.
- Stop/cancel workers và release resources trong lifecycle phù hợp.
- Không dùng `Thread.sleep(500)` cố định để giả vờ worker đã hoàn thành.
- Tách schemas/queues/records để concurrent consumers không đụng nhau.

**`@ResourceLock` không được truyền vào background thread**: đây là khóa scheduler test, không phải distributed mutex của hệ thống.

### 14.4. Nhiều JVM hoặc CI pipelines

JUnit resource locks trong JVM A không thấy locks của JVM B. Một hệ có Gradle `maxParallelForks=4`, multi-module builds và CI shards có thể chạy bốn–mười JVMs cùng lúc. Nếu tất cả cùng dùng test DB schema `"public"`, chỉ dựa ResourceLock là không đủ. Giải pháp ưu tiên:
- Schema/database/container riêng cho mỗi fork/job.
- Unique fixture prefixes/tenant IDs.
- Cleanup/transaction boundaries độc lập.
- Với tài nguyên bắt buộc global, lock ở **DB/file/distributed coordination** có timeout và crash handling.

`@DirtiesContext` chỉ loại Spring ApplicationContext; nó không tự xóa external DB hoặc broker. Đừng dùng nó để “tăng an toàn” cho shared external state khi gốc vấn đề nằm ngoài JVM.

### 14.5. Mock reset và Spring TestContext caching

Spring Boot 3.3 có `@MockBean`/`@SpyBean` để override hoặc spy beans trong test context. Hai tests cùng cached context mà cùng stub/reset một mock có thể interfere. Spring TestContext documentation khuyến cáo **không chạy song song một cách tùy tiện** các tests dùng `@DirtiesContext`, `@MockBean`/`@SpyBean`, ordering hoặc shared DB/broker/filesystem.

ResourceLock có thể giảm xung đột **nếu toàn bộ participants khai báo đúng key**, nhưng không đảm bảo một test thứ ba không biết key sẽ không đóng Spring context hoặc reset bean. Trong các nhóm test context-lifecycle nhạy cảm, cân nhắc chạy tuần tự/tách test task thay vì cố dùng một khóa chung.

### 14.6. Các test cần chứng minh race production

Nếu business service có lost update khi hai HTTP requests đồng thời, đừng gắn cùng READ_WRITE ResourceLock cho hai test methods đang gửi hai requests rồi suy rằng race đã được giải quyết. Khóa ấy sẽ **ngăn hai JUnit methods overlap**, có thể che bug.

Để kiểm thuật toán concurrent:
1. Tạo ít nhất hai tasks/HTTP requests thực sự độc lập.
2. Dùng executor có đủ workers.
3. Dùng `CountDownLatch`/barrier để ép đúng interleaving có rủi ro.
4. Chờ cả hai hoàn thành bằng bounded `Future.get`.
5. Kiểm DB state, số thành công/thất bại, unique constraints và side effects.
6. Chạy với transaction policy/DB vendor phù hợp.

Như vậy `@ResourceLock` bảo vệ **test fixture**, còn concurrency tests bảo vệ **business correctness**. Hai mục tiêu khác nhau, không dùng một để thay cái kia.

## 15. @Execution(SAME_THREAD) khác @Isolated thế nào?

**`@Execution(SAME_THREAD)`** điều khiển execution mode của một JUnit node, thường dùng để giữ các methods trong class không chạy song song với nhau hoặc giữ method trên cùng thread parent. Nhưng một **lớp khác** có thể đang chạy đồng thời và đụng đúng resource. Vì thế SAME_THREAD không đủ để cô lập một global property hoặc shared DB giữa nhiều classes.

**`@Isolated`** là lớp test không overlap với các lớp khác do Jupiter điều phối trong cùng plan. Đây là bảo vệ **rộng hơn** một named lock và có thể tạo bottleneck nếu nhiều classes đều isolated.

**`@ResourceLock`** điều phối theo tên tài nguyên. Nếu test A và B chạm một file, còn C chỉ tính toán thuần Java, A/B sẽ chờ nhau nhưng C có thể chạy cùng một trong hai. Đây là lợi thế chính khi tối ưu parallel suite.

| Nhu cầu | Chọn |
|---|---|
| Một class muốn methods tuần tự vì shared instance field | `@Execution(SAME_THREAD)` hoặc bỏ shared state |
| Một nhóm tests khác classes cùng sửa bảng test | `@ResourceLock` nếu trong một JVM; tốt hơn là tách schema |
| Toàn JVM locale/default encoding bị thay và chưa inventory readers | `@Isolated` + restore |
| Các tests tạo báo cáo cùng tên nhưng có thể đổi base directory | `@TempDir`, không cần lock |
| Cross-JVM CI jobs cùng DB | Isolation DB/schema hoặc cross-process lock |
| Business service cần chống race | Production synchronization/DB transaction, concurrency tests độc lập |

## 16. Đo hiệu quả và giữ test suite khỏe

Khi đưa `@ResourceLock` vào một suite:
1. Đo baseline: total test runtime, Gradle forks, Jupiter parallelism, failures có tính lặp lại.
2. Inventory shared resources. Đặt key đúng **resource**, không dùng tên test.
3. Ưu tiên fixtures riêng trước khi chọn READ_WRITE.
4. Chọn READ thật sự chỉ khi không có mutation trong setup/test/teardown.
5. Chạy nhiều lần toàn suite trong cùng JVM để quan sát sự ổn định.
6. Thử cấu hình CI thực với nhiều forks/jobs; nếu vẫn có race, chuyển sang cross-process isolation.
7. Sau locking, đo runtime lần nữa. Một key quá rộng có thể serialize nhiều tests và triệt tiêu lợi ích concurrent.
8. Không đặt timing assertions kiểu `assertTrue(testFinishedUnder200ms)` trong functional tests. CI có thể biến động CPU/GC/network.
9. Không diễn giải số lần chạy xanh là bằng chứng **không còn bất kỳ race nào**.
10. Ghi rõ giới hạn: các participating Jupiter tests trong một execution plan/JVM, không bao gồm background threads hoặc processes.

**Ví dụ đánh giá đúng:** Trước: 10 trên 100 CI runs fail vì tests sửa cùng JVM property. Sau: cùng 100 runs không fail, property được restore; thời gian suite tăng ít hoặc giảm nhờ parallel có chọn lọc. Đó là bằng chứng thực nghiệm về cải thiện. Không bịa ra các con số này nếu chưa thực đo.

**Ví dụ đánh giá sai:** “Thêm một `@ResourceLock` vào class A, chạy riêng class A một lần xanh nên toàn hệ thống đã thread-safe.” Khi chạy riêng, class B chưa tham gia cạnh tranh và `@ResourceLock` chưa được kiểm ở tình huống quan trọng nhất.

## 17. Troubleshooting

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| Test A/B có khóa nhưng vẫn race | Khác resource keys hoặc class thứ ba không khai báo | Chuẩn hóa names, inventory toàn bộ participants |
| READ test làm bẩn dữ liệu | Setup/teardown có write | Dùng READ_WRITE hoặc tách/reset fixture |
| Thêm lock khiến suite chậm | Khóa class-level/`GLOBAL` quá rộng | Method-level và keys cụ thể |
| @ResourceLock không tìm thấy | Sai import hoặc thiếu JUnit Jupiter | `org.junit.jupiter.api.parallel.ResourceLock` |
| `target=CHILDREN` không compile | Sử dụng API JUnit 5.12 trong Jupiter 5.10 | Bỏ thuộc tính mới hoặc nâng stack chính xác |
| @Execution(CONCURRENT) nhưng không overlap | Các locks xung đột hoặc scheduler không có worker | Không dùng overlap làm điều kiện PASS |
| @Execution(SAME_THREAD) nhưng class B vẫn chạy | SAME_THREAD không phải global mutex | ResourceLock hoặc Isolated |
| Hệ có 4 Gradle forks, DB vẫn race | Lock không cross-process | Unique schema/container/DB advisory locks |
| System property restore không đúng | Không snapshot trước mutation, thiếu finally/AfterEach | Lưu null vs value; clear/set đúng |
| Spring @Value không đổi khi System property mới | Bean được tạo trước khi property đổi | Test properties tại context bootstrap |
| JUnit test xanh nhưng async task phá test sau | Test kết thúc trước worker | Await completion/cancel/cleanup |
| @DirtiesContext đóng context đang dùng | Context cache bị evict trong parallel suite | Không parallel nhóm context lifecycle đó |
| @MockBean stubbing của test bị reset | Shared mock/context | Reset policy, tách tests, serialize nhóm phù hợp |
| @TestMethodOrder không chữa interference | Ordering không là mutual exclusion xuyên classes | Data independence + locks |
| File `build/report.txt` bị ghi đè | Shared path | `@TempDir` hoặc shared file lock |
| `@Isolated` vẫn thấy external worker đổi state | Isolation chỉ Jupiter plan | Cross-process synchronization |
| Singleton test bean bị chia sẻ ngẫu nhiên | Spring Context cache reuse | Reset fixture và thống nhất resource key |
| READ/READ cùng chạy nhưng kết quả sai | Tài nguyên không thật sự read-only | Review implicit writes/caches |
| Jupiter dùng PER_CLASS và methods bị race | Mutable instance fields được chia sẻ | PER_METHOD, SAME_THREAD hoặc locks phù hợp |
| Test chạy từng lớp đều xanh | Không có concurrent classes trong mỗi invocation | Chạy full suite, kiểm CI parallel config |
| Logs xáo thứ tự | Concurrent execution không cam kết thứ tự | Assert state, không snapshot order log |

### 17.1. Quy trình debug nhanh

1. Ghi lại test class/method nào fail và nó sử dụng state gì.
2. Phân biệt resource được lưu ở **JVM static**, Spring singleton, file, DB hay broker.
3. Xác định có bao nhiêu JUnit workers/Gradle forks/CI jobs.
4. Kiểm mọi tests có thể sửa state đó, kể cả trong `@BeforeEach` và `@AfterEach`.
5. Nếu shared within one JVM và không tách được, thống nhất `@ResourceLock` key.
6. Chọn READ hay READ_WRITE theo **side effects toàn lifecycle**, không theo tên method.
7. Restore global state ngay cả khi assertion thất bại.
8. Nếu có `@Async`/listener, chờ side effect hoàn thành trước khi test kết thúc.
9. Nếu external resource có multi-process users, dùng isolation ở chính external resource.
10. Nếu lỗi là business concurrency, viết concurrency test riêng thay vì serialize các requests.
11. Kiểm `@DirtiesContext`/mock reset/test context cache trước khi bật parallel Spring tests hàng loạt.
12. Chạy lại toàn suite nhiều lần, đo độ ổn định và thời gian.

## 18. Bài tập thực hành

**Bài 1 — Sai key:** Class A dùng `@ResourceLock("db:orders")`, B dùng `"DB:orders"`. Có mutual exclusion không? Vì sao Java String key cần thống nhất chính xác?

**Bài 2 — Matrix:** A READ, B READ, C READ_WRITE cùng key. Những cặp nào có thể overlap? Có nên khẳng định A và B chắc chắn overlap không?

**Bài 3 — BeforeEach:** Đưa một `reset()` vào `@BeforeEach` của reader READ. Vì sao là sai? Sửa thành READ_WRITE hay bỏ mutation?

**Bài 4 — Class-level:** Đưa `@ResourceLock("demo:sequence")` lên class A thay vì từng method. Khi nào cách đó gọn hơn, khi nào giảm parallelism quá mức?

**Bài 5 — System Properties:** Gỡ `@AfterEach` restore. Vì sao dù annotation có khóa, test khác sau đó vẫn có thể thấy giá trị bị để lại?

**Bài 6 — Isolated:** So sánh `@Isolated` với `@ResourceLock(Resources.LOCALE)`. Trường hợp nào phải loại trừ toàn bộ Jupiter test classes?

**Bài 7 — TempDir:** Hai test cùng ghi `report.txt`. Đổi sang `@TempDir` và xác minh paths độc lập; tại sao không còn cần READ_WRITE?

**Bài 8 — Spring context:** Dùng hai classes cùng `@SpringBootTest` và singleton mutable, giữ hoặc gỡ khóa. Tại sao việc test pass riêng không chứng minh isolated state?

**Bài 9 — Gradle forks:** Tăng `maxParallelForks` từ 1 lên 4, cho nhiều classes cùng thao tác test DB. Vì sao cùng resource key chưa đủ?

**Bài 10 — Async:** Một test có `@ResourceLock("queue")` nhưng worker ghi vào queue sau khi test return. Thiết kế Future/latch cleanup phù hợp.

**Bài 11 — Retry test:** Dùng cùng static fake server để kích hoạt retry. Khi nào cần ResourceLock, khi nào tạo server riêng port random tốt hơn?

**Bài 12 — Mongo/PostgreSQL:** Tạo schema/collection riêng cho mỗi test run; so sánh hiệu năng với lock toàn bộ một DB.

**Bài 13 — Consumer groups:** Dùng Kafka topic cùng group ID trong hai tests. Tách group/topic names, hoặc chọn shared resource lock trong cùng JVM.

**Bài 14 — Business race:** Hai concurrent transfers từ cùng account. Vì sao gắn READ_WRITE giữa hai test methods có thể giấu lỗi lost update? Dùng gate và DB invariant thay thế.

**Bài 15 — Tối ưu:** Chạy suite với một key `GLOBAL`, sau đó chia key theo DB/file/cache và đo concurrency/CI time. Không bịa số giây; ghi kết quả thực tế.

**Bài 16 — Code review:** Xây bảng resource ownership của suite; đặt tên keys, nơi reset fixtures, loại mode, process scope và người bảo trì.

## 19. Tài liệu tham khảo chính thức

- [JUnit Jupiter 5.10.5 User Guide — Parallel Execution](https://docs.junit.org/5.10.5/user-guide/junit-user-guide-5.10.5.pdf): cấu hình execution modes, resource locks và isolation.
- [JUnit Jupiter 5.11.3 — ResourceLock API](https://docs.junit.org/5.11.3/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/ResourceLock.html): `value`, `mode`, default READ_WRITE và lifecycle scope.
- [JUnit Jupiter 5.10 — ResourceAccessMode](https://docs.junit.org/5.10.0/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/ResourceAccessMode.html): READ/READ_WRITE semantics.
- [JUnit Jupiter 5.10 — Resources](https://docs.junit.org/5.10.0/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/Resources.html): SYSTEM_PROPERTIES, SYSTEM_OUT, SYSTEM_ERR, LOCALE, TIME_ZONE.
- [JUnit Jupiter 5.10 — Isolated](https://docs.junit.org/5.10.0/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/Isolated.html): class-wide isolation.
- [JUnit Jupiter 5.10 — Execution](https://docs.junit.org/5.10.0/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/Execution.html): SAME_THREAD và CONCURRENT.
- [JUnit Jupiter 5.10 — TempDir](https://docs.junit.org/5.10.0/api/org.junit.jupiter.api/org/junit/jupiter/api/io/TempDir.html): unique temporary directory per test.
- [Spring Framework — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/parallel-test-execution.html): giới hạn với DirtiesContext, mocks, ordered tests, external shared state.
- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): reuse ApplicationContext trong một JVM.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): SpringBootTest, TestContext và integration testing.
- [Gradle — Testing in JVM projects](https://docs.gradle.org/current/userguide/java_testing.html): useJUnitPlatform, maxParallelForks, forkEvery.
- [Java 17 — ReentrantReadWriteLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html): phân biệt Java runtime lock với JUnit scheduling lock.

**Tóm tắt:** Khi bật JUnit song song, hãy **cách ly dữ liệu trước khi khóa**. Nếu một resource vẫn phải chia sẻ, khai báo **cùng `@ResourceLock` key**, chọn **READ** cho readers thực sự không mutate và **READ_WRITE** cho writers, gồm cả `@BeforeEach`/`@AfterEach`. `@Isolated` dành cho class thay đổi JVM global state khó định danh; `@TempDir` giải quyết file conflict bằng đường dẫn riêng. Không dùng ResourceLock để che business race, không mong nó đồng bộ khác Gradle JVM hoặc các CI jobs. Các phép kiểm nên độc lập thứ tự, có cleanup và đưa ra assertions ổn định thay vì phụ thuộc thời gian scheduling.
