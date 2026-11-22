# Cấu hình chạy song song của công cụ thực thi

Kiểm thử Spring có thể mất nhiều thời gian khi phải khởi tạo application context, truy cập database hoặc gọi các dịch vụ tích hợp. Chạy nhiều test đồng thời giúp tận dụng CPU và giảm tổng thời gian chờ, nhưng chỉ an toàn khi các test không tranh chấp trạng thái dùng chung.

Trong dự án Spring hiện đại, JUnit Jupiter thường là công cụ thực thi test. JUnit có cơ chế chạy song song ở cấp test class và test method, có thể cấu hình bằng file `junit-platform.properties`, annotation hoặc cấu hình riêng. Công cụ build như Gradle và Maven còn có cơ chế chạy nhiều JVM test worker. Hai lớp cấu hình này khác nhau và có thể được dùng đồng thời.

Khi bật chạy song song, cần quyết định ba điều: test nào được chạy đồng thời, số lượng luồng thực thi mục tiêu là bao nhiêu, và cách bảo vệ tài nguyên mà nhiều test cùng sử dụng. Với Spring Test, điều cuối cùng đặc biệt quan trọng vì test có thể chia sẻ application context, singleton bean, database, system properties hoặc tài nguyên bên ngoài.

## 1. Các lớp thực thi test

Một test suite Java có thể được thực thi qua nhiều lớp:

1. **Build tool:** Gradle hoặc Maven tìm test, tạo test task và có thể khởi chạy nhiều JVM worker.
2. **JUnit Platform:** nhận diện engine và điều phối test thông qua launcher.
3. **JUnit Jupiter Engine:** thực thi các test viết bằng JUnit Jupiter, gồm test class, method, lifecycle callback và extension.
4. **Spring TestContext Framework:** tích hợp Spring context, dependency injection, transaction test và các listener vào vòng đời JUnit.

JUnit Jupiter quản lý song song các node trong test tree, ví dụ test class và test method. Build tool có thể đồng thời chạy nhiều tiến trình JVM. Nếu bật cả hai, tổng số test đang chạy có thể lớn hơn số luồng cấu hình trong một JUnit worker.

Sơ đồ khái quát:

```text
Gradle / Maven test task
        |
        +--> JVM worker 1 --> JUnit Platform --> JUnit Jupiter
        |                                      +--> Test class A
        |                                      +--> Test class B
        |
        +--> JVM worker 2 --> JUnit Platform --> JUnit Jupiter
                                               +--> Test class C
                                               +--> Test class D
```

Trong mỗi JVM worker, JUnit Jupiter còn có thể chạy nhiều test node đồng thời nếu parallel execution được bật. Vì vậy, cần hiểu cấu hình ở cả build tool lẫn JUnit trước khi tăng mức song song.

## 2. Bật parallel execution trong JUnit Jupiter

JUnit Jupiter tắt chạy song song theo mặc định. Để bật, thêm file `junit-platform.properties` vào test classpath, thường là:

```text
src/test/resources/junit-platform.properties
```

Nội dung tối thiểu:

```properties
junit.jupiter.execution.parallel.enabled = true
```

Chỉ bật thuộc tính này chưa có nghĩa mọi test class và method sẽ tự động chạy đồng thời. JUnit còn có execution mode mặc định cho node và cấu hình chiến lược thread pool. Nếu không chỉ định mode, các node thường tiếp tục chạy `SAME_THREAD` theo mặc định.

Để chạy đồng thời các test class và method, có thể cấu hình:

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
junit.jupiter.execution.parallel.mode.classes.default = concurrent
```

Hai thuộc tính mode có phạm vi khác nhau:

- `junit.jupiter.execution.parallel.mode.default` quy định mode mặc định cho node trong cây test, thường là các method.
- `junit.jupiter.execution.parallel.mode.classes.default` quy định mode mặc định cho test class.

Giá trị mode hợp lệ là `same_thread` và `concurrent`. Tên thuộc tính và giá trị cần được viết đúng trong file properties.

### Vị trí file cấu hình

JUnit Platform tìm `junit-platform.properties` trên classpath của test runtime. Với Gradle hoặc Maven, `src/test/resources` thường được đưa vào test classpath mặc định. Nếu file đặt ở thư mục khác, hãy bảo đảm thư mục đó được cấu hình thành test resource.

Không đặt file này trong `src/main/resources` nếu mục tiêu chỉ là điều khiển test. Cấu hình test nên nằm trong source set hoặc resource set dành cho test để tránh tác động đến runtime production.

## 3. Chọn execution mode cho class và method

JUnit Jupiter cung cấp hai execution mode chính:

| Mode | Ý nghĩa |
| --- | --- |
| `same_thread` | Node con được thực thi tuần tự trên cùng luồng với node cha |
| `concurrent` | Node con có thể được thực thi đồng thời với node khác |

Có thể kết hợp hai thuộc tính mode để chọn phạm vi song song.

### Chạy các method đồng thời trong từng class, còn các class tuần tự

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
junit.jupiter.execution.parallel.mode.classes.default = same_thread
```

Cấu hình này cho phép các method trong một class chạy đồng thời, trong khi các class ở cấp cao hơn được giữ cùng luồng theo mode mặc định của class. Cần đặc biệt chú ý khi các method dùng chung instance hoặc trạng thái mutable.

### Chạy các class đồng thời, method trong mỗi class tuần tự

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = same_thread
junit.jupiter.execution.parallel.mode.classes.default = concurrent
```

Đây là lựa chọn thận trọng hơn cho nhiều dự án Spring: các test class độc lập có thể chạy đồng thời, nhưng các method trong cùng class tiếp tục tuần tự. Dù vậy, hai class vẫn có thể chia sẻ database, static state hoặc cùng một cached Spring context.

### Chạy cả class và method đồng thời

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
junit.jupiter.execution.parallel.mode.classes.default = concurrent
```

Đây là cấu hình có mức song song cao hơn. Chỉ nên dùng khi test method độc lập về trạng thái, không dựa vào thứ tự chạy và có cơ chế đồng bộ tài nguyên dùng chung.

## 4. Chọn số luồng bằng execution strategy

JUnit Jupiter cung cấp các chiến lược cấu hình parallel execution thông qua:

```properties
junit.jupiter.execution.parallel.config.strategy = <strategy>
```

Các chiến lược tiêu chuẩn gồm:

- `dynamic`: tính mức song song dựa trên số bộ xử lý khả dụng và hệ số cấu hình.
- `fixed`: sử dụng mức song song cố định do người dùng chỉ định.
- `custom`: dùng implementation của `ParallelExecutionConfigurationStrategy` do dự án cung cấp.

Nếu không chỉ định strategy, JUnit dùng chiến lược mặc định tương ứng với cấu hình của phiên bản JUnit Jupiter. Khi muốn kiểm soát rõ tải của test suite, nên khai báo strategy tường minh.

### Dynamic strategy

Dynamic strategy tính parallelism dựa trên số bộ xử lý khả dụng. Có thể đặt hệ số:

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
junit.jupiter.execution.parallel.mode.classes.default = concurrent
junit.jupiter.execution.parallel.config.strategy = dynamic
junit.jupiter.execution.parallel.config.dynamic.factor = 1
```

Với `dynamic.factor = 1`, parallelism mục tiêu được tính xấp xỉ theo số CPU khả dụng mà JVM nhìn thấy. Ví dụ, nếu JVM nhìn thấy 8 processor, mức parallelism mục tiêu là khoảng 8.

Có thể điều chỉnh hệ số để tăng hoặc giảm mức song song mục tiêu:

```properties
junit.jupiter.execution.parallel.config.dynamic.factor = 0.5
```

Với hệ số 0.5 và 8 processor, mức song song mục tiêu xấp xỉ 4. Dynamic strategy hữu ích khi cùng một bộ test chạy trên máy developer, CI runner và máy build có số CPU khác nhau.

JUnit còn hỗ trợ giới hạn kích thước tối đa của pool theo hệ số:

```properties
junit.jupiter.execution.parallel.config.dynamic.max-pool-size-factor = 2
```

Thuộc tính này xác định hệ số dùng để tính maximum pool size từ số processor khả dụng. Đây là giới hạn kích thước pool, khác với parallelism mục tiêu.

### Fixed strategy

Fixed strategy cho phép khai báo parallelism cụ thể:

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
junit.jupiter.execution.parallel.mode.classes.default = concurrent
junit.jupiter.execution.parallel.config.strategy = fixed
junit.jupiter.execution.parallel.config.fixed.parallelism = 4
```

Ở đây JUnit đặt mức parallelism mục tiêu là 4. Có thể cấu hình thêm maximum pool size:

```properties
junit.jupiter.execution.parallel.config.fixed.max-pool-size = 8
```

`parallelism` là mức song song mục tiêu; `max-pool-size` giới hạn số thread tối đa trong pool. Không nên coi `parallelism = 4` là cam kết rằng toàn bộ quá trình test sẽ luôn có đúng bốn thread hoạt động. JUnit sử dụng ForkJoinPool và có thể cần thêm thread trong một số tình huống blocking để duy trì tiến độ, trong giới hạn cấu hình pool.

### Custom strategy

Khi cần tính toán parallelism theo logic riêng, có thể triển khai `ParallelExecutionConfigurationStrategy` và đăng ký class:

```properties
junit.jupiter.execution.parallel.config.strategy = custom
junit.jupiter.execution.parallel.config.custom.class = com.example.test.CustomParallelStrategy
```

Custom strategy phù hợp khi CI có nhiều loại runner hoặc khi nhóm muốn điều khiển thread pool theo môi trường. Đây là extension point cấp thấp; với phần lớn dự án, dynamic hoặc fixed strategy đã đủ.

## 5. Chọn chiến lược nào cho dự án Spring?

Không có một giá trị song song tối ưu cho mọi test suite. Cần xét đặc tính công việc:

| Đặc tính test | Gợi ý |
| --- | --- |
| Nhiều unit test thuần Java, độc lập và CPU-bound | Dynamic hoặc fixed với parallelism gần số CPU khả dụng |
| Test chờ database hoặc HTTP service | Có thể cần nhiều thread hơn số CPU, nhưng phải giới hạn connection pool và tài nguyên bên ngoài |
| Nhiều Spring context nặng, ít test độc lập | Bắt đầu bằng chạy class song song, method trong class tuần tự |
| Test chia sẻ static state hoặc system properties | Tuần tự hóa hoặc dùng resource lock |
| Test thay đổi application context bằng `@DirtiesContext` | Không chạy đồng thời với test khác dùng cùng context |
| Test dùng `@TestInstance(PER_CLASS)` và mutable fields | Giữ method tuần tự hoặc tự bảo vệ state |

Một cấu hình khởi đầu tương đối thận trọng cho Spring integration tests có thể là:

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = same_thread
junit.jupiter.execution.parallel.mode.classes.default = concurrent
junit.jupiter.execution.parallel.config.strategy = dynamic
junit.jupiter.execution.parallel.config.dynamic.factor = 1
```

Điều này cho phép test class độc lập chạy đồng thời, nhưng method trong mỗi class vẫn chạy tuần tự. Sau khi xác định các test an toàn với chia sẻ trạng thái, có thể mở rộng song song ở cấp method.

## 6. Điều khiển song song bằng annotation

Có thể cấu hình mode cho một class hoặc method bằng `@Execution`:

```java
@Execution(ExecutionMode.CONCURRENT)
class IndependentControllerTests {

    @Test
    void readsPublicEndpoint() {
        // Test độc lập.
    }

    @Test
    void readsHealthEndpoint() {
        // Test độc lập.
    }
}
```

`@Execution(CONCURRENT)` yêu cầu node được đánh dấu có thể chạy đồng thời theo cơ chế JUnit. Cấu hình global vẫn phải bật parallel execution.

Nếu một class cần tuần tự:

```java
@Execution(ExecutionMode.SAME_THREAD)
class SharedStateTests {

    @Test
    void updatesSharedConfiguration() {
        // Dùng trạng thái mutable chung.
    }

    @Test
    void readsSharedConfiguration() {
        // Phụ thuộc vào trạng thái dùng chung.
    }
}
```

`@Execution` giúp diễn đạt ý định ngay tại test class, nhưng không tự khóa mọi tài nguyên bên ngoài. Nếu nhiều class cùng truy cập một tài nguyên, cần cơ chế đồng bộ ở phạm vi chia sẻ đó.

## 7. Bảo vệ tài nguyên dùng chung bằng ResourceLock

Khi test cần truy cập tài nguyên dùng chung như system properties, locale mặc định hoặc một file chung, JUnit cung cấp `@ResourceLock`.

Ví dụ:

```java
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;

@ResourceLock(value = "shared-system-property", mode = ResourceAccessMode.READ_WRITE)
class SystemPropertyTests {

    @Test
    void changesPropertyTemporarily() {
        System.setProperty("app.mode", "test");
        try {
            assertThat(System.getProperty("app.mode")).isEqualTo("test");
        }
        finally {
            System.clearProperty("app.mode");
        }
    }
}
```

JUnit sẽ điều phối các test khai báo cùng resource key để tránh thực thi đồng thời khi một test yêu cầu quyền truy cập xung đột. `READ_WRITE` yêu cầu quyền đọc/ghi độc quyền; chế độ `READ` có thể cho phép nhiều test đọc cùng lúc nếu không có test ghi cùng resource.

Có thể dùng hằng `Resources.SYSTEM_PROPERTIES`, `Resources.LOCALE` hoặc resource key tự định nghĩa khi phù hợp. Điều quan trọng là các test cùng truy cập một tài nguyên phải dùng cùng tên resource lock. Nếu một test thay đổi system property nhưng test khác không khai báo lock, JUnit không thể tự suy ra xung đột.

`@ResourceLock` bảo vệ các test trong cùng JUnit execution context. Nó không khóa một database, file hoặc service cho tiến trình JVM khác hay build khác. Với tài nguyên bên ngoài, cần cơ chế đồng bộ phù hợp ở tầng đó.

## 8. Quan hệ với lifecycle của JUnit

Mặc định, JUnit Jupiter tạo một test instance mới cho mỗi test method (`PER_METHOD`). Điều này giúp giảm chia sẻ field giữa các method. Nếu dùng:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class SharedTestInstance {
    // Một instance dùng cho nhiều test method.
}
```

thì các method trong cùng class chia sẻ một object. Nếu chúng chạy concurrent, các field mutable, mock, collection hoặc state được cập nhật trong `@BeforeEach`/`@AfterEach` có thể bị truy cập đồng thời.

Với `PER_CLASS`, cần lựa chọn một trong các hướng:

- Giữ các method tuần tự bằng `@Execution(SAME_THREAD)`.
- Thiết kế test instance và collaborator thread-safe.
- Tách dữ liệu và state riêng cho từng method.
- Dùng resource lock nếu các method truy cập cùng tài nguyên được xác định.

`@BeforeAll` và `@AfterAll` cũng cần được thiết kế để không tranh chấp với các test node chạy đồng thời. Không nên dùng lifecycle callback để thay đổi cấu hình toàn cục trong lúc test khác đang đọc cấu hình đó.

## 9. Những lưu ý riêng với Spring TestContext Framework

Spring TestContext Framework có thể cache `ApplicationContext` giữa các test class có cấu hình tương đương. Cơ chế cache giúp giảm thời gian khởi tạo Spring, nhưng đồng thời có nghĩa nhiều test có thể dùng cùng một context và cùng singleton bean.

### Singleton bean và trạng thái mutable

Bean Spring mặc định có scope singleton. Nếu test gọi bean có field mutable hoặc thay đổi trạng thái dùng chung, hai test chạy đồng thời có thể ảnh hưởng lẫn nhau. Hãy giữ service/controller stateless khi có thể, tạo dữ liệu test riêng và tránh dùng singleton làm nơi lưu trạng thái tạm của test.

### @DirtiesContext

`@DirtiesContext` đánh dấu context không còn dùng được và yêu cầu Spring loại context khỏi cache hoặc đóng context theo phạm vi khai báo. Nếu một test đánh dấu context dirty trong khi test khác đang sử dụng cùng context, test song song có thể gặp lỗi khó dự đoán. Không chạy đồng thời các test có `@DirtiesContext` với test khác dùng chung context; cân nhắc tuần tự hóa nhóm test đó.

### Mock bean và thay đổi cấu hình context

Các annotation thay thế bean hoặc cấu hình mock trong Spring test có thể làm thay đổi context được cache. Nếu test cần cấu hình bean khác nhau, hãy để Spring tạo context phù hợp hoặc phân tách test scope rõ ràng. Không tự sửa singleton bean dùng chung giữa các test concurrent.

### Transaction trong test

Spring quản lý transaction test theo thread hiện tại. Mỗi test method chạy trên thread riêng khi được thực thi song song và transaction test thường gắn với thread thực thi đó. Dữ liệu của test này không tự động nằm trong transaction của test khác.

Tuy vậy, các test vẫn có thể xung đột khi cùng ghi vào một bảng, dùng cùng khóa duy nhất, cùng record hoặc cùng dữ liệu seed. Dùng ID riêng cho từng test, dọn dữ liệu có kiểm soát và tránh giả định transaction rollback của test này sẽ cô lập dữ liệu khỏi mọi thread khác.

### Async code trong ứng dụng

JUnit chạy test method trên thread của JUnit, còn `@Async`, `CompletableFuture` hoặc executor của ứng dụng có thể dùng thread khác. Transaction gắn với thread của test không tự truyền sang worker thread. Khi test async, phải đợi tác vụ hoàn tất và xác nhận trạng thái cuối một cách tường minh; không dựa vào rollback của thread test để kiểm soát mọi thao tác được thực hiện trên worker thread.

## 10. Cấu hình song song ở Gradle và Maven

JUnit điều khiển song song bên trong một JVM test process. Build tool có thể khởi chạy nhiều JVM process độc lập, mỗi process có JUnit engine và thread pool riêng.

### Gradle

Để Gradle dùng JUnit Platform:

```groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Gradle có thuộc tính `maxParallelForks` để quyết định số test JVM worker được chạy đồng thời:

```groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()
    maxParallelForks = 2
}
```

`maxParallelForks = 2` cho phép tối đa hai JVM test worker cho task đó. Mỗi worker lại có thể chạy nhiều JUnit test node đồng thời nếu `junit-platform.properties` bật parallel execution. Tổng tải có thể tăng nhanh nếu cả hai mức đều cao.

Ví dụ, hai worker JVM với JUnit parallelism mục tiêu 4 có thể tạo mức song song danh nghĩa xấp xỉ tám test node, tùy cách phân phối test và tài nguyên. Hãy điều chỉnh cả hai lớp cấu hình theo năng lực CPU, RAM, connection pool và dịch vụ ngoài.

### Maven Surefire

Với Maven Surefire, `forkCount` quyết định số JVM test process có thể chạy đồng thời:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <forkCount>2</forkCount>
        <reuseForks>true</reuseForks>
    </configuration>
</plugin>
```

JUnit Jupiter parallel execution vẫn được cấu hình riêng qua `junit-platform.properties`. `forkCount` không thay thế `junit.jupiter.execution.parallel.*`; nó điều khiển số JVM process, còn JUnit điều khiển các node trong mỗi process.

Không bật đồng thời mức fork lớn và JUnit thread pool lớn nếu chưa đánh giá tải. Ví dụ bốn JVM, mỗi JVM chạy tám test đồng thời, có thể tạo đến khoảng 32 test node cùng hoạt động, chưa tính thread nội bộ của ứng dụng.

## 11. Từng bước bật chạy song song an toàn

Một cách triển khai thực tế:

1. Đo thời gian chạy test suite hiện tại và xác định nhóm test tốn nhiều thời gian.
2. Phân loại test độc lập, test dùng database, test thay đổi global state và test cần context riêng.
3. Bật parallel execution trong JUnit nhưng bắt đầu với class concurrent và method same-thread.
4. Chọn dynamic hoặc fixed strategy với parallelism vừa phải.
5. Thêm `@ResourceLock` hoặc `@Execution(SAME_THREAD)` cho test chia sẻ tài nguyên không thể tách.
6. Giữ `maxParallelForks`/`forkCount` ở mức phù hợp, không nhân đồng thời nhiều lớp thread mà chưa đo tải.
7. Chạy test suite lặp lại trên CI để phát hiện lỗi không ổn định do race condition.
8. Mở rộng concurrency ở cấp method khi đã xác định test an toàn.
9. Theo dõi RAM, CPU, database connections, thời gian khởi tạo context và log lỗi trong quá trình tăng tải.

Nếu test suite bắt đầu thất bại ngẫu nhiên sau khi bật parallel, hãy xem đó là dấu hiệu có state hoặc tài nguyên dùng chung chưa được cô lập. Tìm nguồn chia sẻ như static field, singleton mutable bean, file chung, system properties, record database, mock server hoặc context bị đóng trong lúc test khác đang dùng.

## 12. Ví dụ cấu hình khởi đầu

Với một dự án Spring Boot dùng JUnit Jupiter, có thể bắt đầu bằng file:

```properties
# src/test/resources/junit-platform.properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = same_thread
junit.jupiter.execution.parallel.mode.classes.default = concurrent
junit.jupiter.execution.parallel.config.strategy = fixed
junit.jupiter.execution.parallel.config.fixed.parallelism = 4
junit.jupiter.execution.parallel.config.fixed.max-pool-size = 8
```

Gradle:

```groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()
    maxParallelForks = 1
}
```

Cấu hình này cho phép tối đa một Gradle test JVM, trong đó JUnit có parallelism mục tiêu là bốn và cho phép pool mở rộng đến tám thread theo cơ chế của ForkJoinPool. Các test class có thể chạy đồng thời; method trong cùng class vẫn theo `same_thread` mặc định.

Đây chỉ là điểm bắt đầu. Nếu integration test cùng dùng một database nhỏ hoặc một dịch vụ container giới hạn connection, giảm parallelism. Nếu test chủ yếu chờ I/O và tài nguyên đủ, có thể thử tăng mức song song có kiểm soát.

## 13. Các vấn đề thường gặp

### Đã bật parallel.enabled nhưng test vẫn chạy tuần tự

Kiểm tra `mode.default` và `mode.classes.default`. Chỉ bật tính năng không tự động đổi execution mode. Ngoài ra, annotation `@Execution(SAME_THREAD)` hoặc resource lock có thể buộc một số node chạy tuần tự.

### Test chạy được riêng lẻ nhưng thất bại khi chạy toàn suite

Thường do state dùng chung, dữ liệu database trùng, file chung, system properties hoặc context bị thay đổi. Tách dữ liệu, bảo vệ resource hoặc chạy tuần tự nhóm test có phụ thuộc.

### Tăng parallelism nhưng test chậm hơn

Có thể do CPU/RAM bị quá tải, context được tạo đồng thời làm tăng áp lực bộ nhớ, database connection pool bị cạn hoặc dịch vụ ngoài bị nghẽn. Parallelism cao hơn không luôn làm tổng thời gian giảm.

### Gradle/Maven đã chạy nhiều worker, nhưng JUnit cũng tạo nhiều thread

Đây là hai tầng song song độc lập. Hãy tính tải tổng thể từ số JVM worker nhân với mức concurrency mục tiêu trong mỗi worker, sau đó đo trên môi trường CI thực tế.

### Transaction test không cô lập được thao tác async

Transaction test gắn với thread thực thi test. Công việc chạy trong executor riêng có thể không tham gia transaction đó. Hãy đợi tác vụ hoàn tất và kiểm soát dữ liệu do worker thread tạo ra.

## 14. Kết luận

JUnit Jupiter điều khiển chạy song song của test class và test method qua các thuộc tính `junit.jupiter.execution.parallel.*`, execution mode và strategy. `dynamic` thích nghi theo số CPU, `fixed` cho phép đặt parallelism cụ thể, còn `custom` dành cho nhu cầu điều khiển riêng. Gradle `maxParallelForks` và Maven Surefire `forkCount` điều khiển số JVM worker, là một lớp cấu hình khác với thread pool của JUnit.

Với Spring Test, hãy bắt đầu bằng việc chạy các test class độc lập đồng thời trong khi giữ method cùng class tuần tự. Bảo vệ global state bằng resource lock, tránh chia sẻ mutable singleton, chú ý `@DirtiesContext`, transaction và tác vụ async. Tăng mức song song từng bước và đo trên CI để đạt tốc độ tốt mà vẫn giữ test ổn định.
