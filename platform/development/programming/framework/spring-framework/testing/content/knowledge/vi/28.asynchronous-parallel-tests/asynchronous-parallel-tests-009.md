# Cô lập database, thư mục, cổng và tài nguyên chia sẻ

Khi test chạy song song hoặc có tác vụ bất đồng bộ, nhiều test có thể cùng truy cập một database, thư mục, cổng mạng, cache, message broker hoặc biến trạng thái trong JVM. Nếu hai test cùng sửa một tài nguyên mà không có ranh giới riêng, kết quả sẽ phụ thuộc vào thời điểm chạy: test có thể đọc dữ liệu của test khác, xóa file đang được sử dụng hoặc chiếm cùng một cổng.

Trong Spring Framework Testing, cô lập tài nguyên là một phần của thiết kế test đáng tin cậy. Mỗi test nên sở hữu dữ liệu và tài nguyên của mình, đặt tên riêng cho những tài nguyên dùng chung, và giải phóng chúng sau khi hoàn tất. Chỉ khóa thực thi khi một tài nguyên toàn cục không thể tách riêng.

## 1. Vì sao test song song dễ bị ảnh hưởng lẫn nhau?

JUnit Jupiter có thể chạy nhiều test method hoặc test class đồng thời. Spring TestContext cũng có thể tái sử dụng application context đã được cache giữa các test. Điều này tiết kiệm thời gian khởi động Spring, nhưng có nghĩa nhiều test có thể cùng dùng một singleton bean và cùng truy cập các dịch vụ bên ngoài.

Các xung đột thường gặp:

- Hai test ghi cùng một hàng dữ liệu hoặc cùng dùng một mã định danh trong database.
- Một test xóa dữ liệu trong khi test khác đang đọc hoặc cập nhật.
- Nhiều test tạo file có cùng tên trong `target/test-output` hoặc thư mục tạm dùng chung.
- Hai server test cùng cố gắng bind vào một cổng cố định.
- Một test thay đổi system property, locale hoặc timezone trong khi test khác đang đọc.
- Nhiều test gửi message vào cùng queue hoặc dùng chung consumer group và nhận message của nhau.
- Một test sửa trạng thái mutable trong singleton bean hoặc static cache mà test khác đang sử dụng.

Một test chạy riêng lẻ thành công chưa chứng minh nó an toàn khi chạy cùng các test khác. Cần thiết kế ranh giới tài nguyên để thứ tự và thời điểm thực thi không làm thay đổi kết quả.

## 2. Nguyên tắc thiết kế ranh giới cô lập

Với mỗi tài nguyên mà test sử dụng, hãy xác định ai sở hữu nó, phạm vi chia sẻ và thời điểm giải phóng:

| Tài nguyên | Cách cô lập nên ưu tiên | Khi nào cần khóa |
|---|---|---|
| Database records | Dữ liệu riêng theo test, khóa ngoại và cleanup theo định danh | Khi thao tác bắt buộc ảnh hưởng toàn database hoặc bảng dùng chung |
| Database/schema | Database hoặc schema riêng theo suite/test | Khi nhiều test cùng reset schema hoặc chạy migration phá hủy |
| Thư mục/file | `@TempDir`, tên file duy nhất | Khi test buộc phải dùng một đường dẫn cố định |
| Cổng mạng | Cổng ngẫu nhiên do OS cấp | Khi giao thức hoặc công cụ bắt buộc dùng một cổng cố định |
| Cache | Key có namespace riêng, xóa đúng key | Khi test phải xóa cache toàn cục |
| Queue/topic/consumer group | Tên riêng theo test hoặc suite | Khi không thể tạo namespace riêng |
| System property/locale/timezone | Khôi phục giá trị cũ trong `finally` | Khi nhiều test truy cập cùng trạng thái JVM |
| Spring singleton bean | Tránh mutable shared state, tạo instance riêng khi cần | Khi state toàn cục không thể loại bỏ |

Ưu tiên cấp phát tài nguyên riêng thay vì dùng chung rồi cố gắng dọn dẹp. Tài nguyên riêng giảm phụ thuộc thứ tự; cleanup vẫn cần thiết để tránh rò rỉ tài nguyên sau khi test kết thúc.

## 3. Cô lập dữ liệu database

### Dùng dữ liệu riêng cho từng test

Một cách đơn giản là tạo định danh duy nhất cho dữ liệu test. Không dùng các mã cố định như `TEST-1` nếu nhiều test có thể cùng insert vào bảng có unique constraint.

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class CustomerServiceTests {

    @Test
    void createsCustomerWithUniqueTestData() {
        String email = "test-" + UUID.randomUUID() + "@example.test";

        Customer customer = customerService.create("Mai", email);

        assertThat(customer.email()).isEqualTo(email);
    }
}
```

Mã định danh duy nhất giúp các test đồng thời không ghi đè dữ liệu của nhau. Nếu test tạo nhiều bản ghi liên quan, hãy dùng cùng một test identifier làm tiền tố hoặc trường liên kết để có thể truy vấn và cleanup đúng nhóm dữ liệu.

### Cleanup theo định danh của test

Nếu test cần commit dữ liệu hoặc gọi qua server thật, transaction rollback của test có thể không dọn được dữ liệu. Khi đó, cleanup theo định danh riêng là một lựa chọn rõ ràng:

```java
import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CustomerApiIntegrationTests {

    private String testRunId;

    @BeforeEach
    void createTestNamespace() {
        testRunId = "it-" + UUID.randomUUID();
    }

    @Test
    void createsCustomer() {
        String email = testRunId + "@example.test";
        // Gửi request tạo customer bằng email thuộc namespace của test.
    }

    @AfterEach
    void removeTestData() {
        customerRepository.deleteByEmailStartingWith(testRunId);
    }
}
```

Cleanup phải giới hạn trong namespace của test. Tránh `DELETE FROM customers` hoặc `TRUNCATE` một bảng dùng chung khi các test khác có thể đang chạy. Nếu cleanup thất bại, cần để test hoặc suite báo lỗi rõ ràng thay vì âm thầm để lại dữ liệu ảnh hưởng lượt chạy sau.

### Hiểu đúng transaction rollback trong Spring Test

Spring TestContext hỗ trợ `@Transactional` trên test method. Theo mặc định, transaction test được rollback sau test, hữu ích khi test gọi trực tiếp service đồng bộ trong cùng thread:

```java
import org.junit.jupiter.api.Test;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
class CustomerServiceTransactionalTests {

    @Test
    @Transactional
    void createsCustomerInsideTestTransaction() {
        customerService.create("Mai", "mai@example.test");
        // Transaction của test được rollback sau method.
    }
}
```

Tuy nhiên, rollback này không phải cơ chế cô lập chung cho mọi tác vụ:

- Transaction Spring thường gắn với thread hiện tại. Tác vụ chạy bằng `@Async`, executor hoặc scheduler sử dụng thread khác sẽ không tự tham gia transaction của test.
- Với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, request HTTP được xử lý trên thread của server. Transaction của test method không bao bọc transaction do request đó thực hiện.
- Một service dùng `REQUIRES_NEW` có thể commit transaction độc lập; rollback transaction bên ngoài không hoàn tác phần đã commit.
- Message được gửi ra broker, file được ghi hoặc lời gọi HTTP ra hệ thống khác không tự được rollback cùng database transaction.

Vì vậy, nếu test gọi API qua server hoặc khởi chạy tác vụ bất đồng bộ, hãy dùng dữ liệu riêng theo test và cleanup tường minh. Không giả định rằng thêm `@Transactional` trên test sẽ dọn mọi side effect.

### Database/schema riêng cho suite hoặc test

Khi test cần reset dữ liệu, chạy migration hoặc xác minh ràng buộc trên nhiều bảng, một database hoặc schema riêng cho mỗi test suite có thể an toàn hơn database dùng chung. Với Testcontainers, có thể khởi chạy database container dùng chung cho suite nhưng tạo schema hoặc namespace dữ liệu riêng theo test.

Container dùng chung giúp giảm chi phí khởi động; nó không tự cô lập các bản ghi bên trong database. Nếu nhiều test cùng gọi migration, truncate hoặc thay đổi cấu trúc schema, cần tách schema/database hoặc tuần tự hóa đúng phần thao tác đó.

Không chạy lệnh reset toàn database trong `@BeforeEach` khi các test khác đang dùng chung database. Việc reset có thể xóa dữ liệu của test khác dù mỗi test đã có transaction riêng.

## 4. Cô lập thư mục và file bằng @TempDir

JUnit Jupiter cung cấp `@TempDir` để cấp phát thư mục tạm riêng cho test. Có thể nhận `Path` qua tham số test method hoặc field được annotation. JUnit quản lý vòng đời và mặc định xóa thư mục sau khi phạm vi sử dụng kết thúc.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.assertj.core.api.Assertions.assertThat;

class ReportWriterTests {

    @Test
    void writesReportToItsOwnDirectory(@TempDir Path tempDir)
            throws IOException {
        Path report = tempDir.resolve("report.txt");

        Files.writeString(report, "report for this test");

        assertThat(Files.readString(report))
            .isEqualTo("report for this test");
    }
}
```

Mỗi lần thực thi test có thư mục tạm riêng, vì vậy hai test cùng tạo `report.txt` vẫn không đụng nhau. Ưu tiên truyền `Path` vào component cần kiểm thử để component ghi đúng thư mục mà test đã cấp phát.

Nếu component nhận thư mục qua constructor hoặc cấu hình, có thể truyền `tempDir` trực tiếp:

```java
@Test
void exportsIntoTemporaryFolder(@TempDir Path tempDir) {
    ReportExporter exporter = new ReportExporter(tempDir);

    Path generated = exporter.export("monthly");

    assertThat(generated).exists();
    assertThat(generated.getParent()).isEqualTo(tempDir);
}
```

Tránh ghi file test vào một đường dẫn cố định như `build/reports/test-output/report.txt` nếu test có thể chạy đồng thời. Nếu cần kiểm tra một file có tên cố định, đặt tên đó bên trong `@TempDir`.

`@TempDir` có thể được đặt ở cấp method hoặc class. Phạm vi method tạo thư mục riêng cho mỗi test method và thường là lựa chọn tốt nhất khi test ghi/xóa file. Phạm vi class chia sẻ thư mục giữa các method trong class; chỉ dùng khi các method thật sự cần chia sẻ fixture và không chạy đồng thời hoặc mỗi method có subdirectory riêng.

## 5. Cấp phát cổng mạng động

Test server không nên bind vào một cổng cố định như `8080` hoặc `8081`. Cổng đó có thể đã được ứng dụng khác hoặc một test chạy song song sử dụng. Hãy để hệ điều hành cấp cổng còn trống.

Với Spring Boot, `RANDOM_PORT` khởi động server trên cổng ngẫu nhiên và `@LocalServerPort` cung cấp cổng thực tế:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApiIntegrationTests {

    @LocalServerPort
    private int port;

    @Test
    void respondsOnTheAssignedPort() {
        String baseUrl = "http://localhost:" + port;
        // Gửi HTTP request đến baseUrl.
    }
}
```

Nếu test tự khởi động một server mock, hãy dùng API hỗ trợ cổng `0` hoặc cơ chế chọn cổng ngẫu nhiên của thư viện. Ví dụ, `MockWebServer.start()` tự chọn một cổng khả dụng; lấy URL từ `server.url("/")` thay vì giả định cổng cụ thể.

Không nên tự kiểm tra một cổng có vẻ đang trống rồi đóng socket trước khi server thật bind vào cổng đó. Giữa bước kiểm tra và bước bind, process khác có thể chiếm cổng (race condition). Hãy để chính server bind vào cổng `0`, sau đó đọc cổng được cấp.

Với container, lấy host và mapped port do Testcontainers cung cấp, chẳng hạn `getHost()` và `getMappedPort(...)`. Không hard-code port bên trong container thành port trên host; Docker có thể ánh xạ sang cổng khác.

## 6. Cô lập Spring application context và singleton bean

Spring TestContext cache application context để tránh khởi động lại context giống nhau cho từng test. Những test dùng cùng cấu hình có thể nhận cùng singleton bean instance. Đây là hành vi có lợi cho tốc độ nhưng cần chú ý khi bean chứa mutable state.

Ví dụ một bean giữ danh sách dùng chung:

```java
@Component
class RequestHistory {

    private final List<String> requests = new ArrayList<>();

    void add(String request) {
        requests.add(request);
    }

    List<String> all() {
        return List.copyOf(requests);
    }
}
```

Nếu hai test cùng dùng context và gọi `add(...)`, mỗi test có thể đọc thêm dữ liệu do test kia tạo. Cách tốt hơn là thiết kế bean không giữ trạng thái test-specific, truyền state qua request hoặc tạo collaborator riêng theo scope phù hợp. Nếu bean cần state, cung cấp cơ chế reset có kiểm soát và bảo đảm không reset trong khi test khác đang sử dụng.

`@DirtiesContext` đánh dấu context cần loại khỏi cache và đóng context theo thời điểm được chọn. Nó hữu ích khi một test làm hỏng cấu hình hoặc trạng thái context đến mức không thể tái sử dụng. Tuy nhiên, nó không phải khóa đồng bộ và không dọn dữ liệu ở database, queue, file system hoặc dịch vụ bên ngoài. Dùng annotation này cho mọi test có thể làm suite chậm mà vẫn không giải quyết xung đột tài nguyên bên ngoài.

## 7. Dùng JUnit ResourceLock cho trạng thái toàn cục

Có một số trạng thái không thể dễ dàng cấp riêng cho từng test, chẳng hạn system properties, default locale, timezone hoặc singleton static. JUnit Jupiter hỗ trợ `@ResourceLock` để tuần tự hóa các test cùng khai báo sử dụng một tài nguyên.

Ví dụ test thay đổi system property:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

import static org.assertj.core.api.Assertions.assertThat;

@ResourceLock(value = Resources.SYSTEM_PROPERTIES,
              mode = ResourceAccessMode.READ_WRITE)
class SystemPropertyTests {

    @Test
    void readsFeatureFlag() {
        String previous = System.getProperty("feature.mode");
        try {
            System.setProperty("feature.mode", "test");

            assertThat(System.getProperty("feature.mode"))
                .isEqualTo("test");
        }
        finally {
            if (previous == null) {
                System.clearProperty("feature.mode");
            }
            else {
                System.setProperty("feature.mode", previous);
            }
        }
    }
}
```

`ResourceAccessMode.READ_WRITE` khai báo test vừa đọc vừa thay đổi tài nguyên. Các test khác khai báo cùng resource lock sẽ được JUnit điều phối để không chạy đồng thời với test đang giữ quyền ghi. Với một tài nguyên do ứng dụng định nghĩa, có thể dùng tên khóa tùy chỉnh:

```java
@ResourceLock(value = "shared-test-cache",
              mode = ResourceAccessMode.READ_WRITE)
class CacheResetTests {
    // Test thao tác trên cache toàn cục.
}
```

Resource lock chỉ điều phối các test trong cùng JUnit Jupiter execution tương ứng. Nó không khóa test chạy trong một JVM fork khác, một Gradle worker khác hoặc một CI job khác. Đối với database, queue hoặc file system dùng chung giữa nhiều process, hãy dùng namespace riêng, lock ở tầng tài nguyên hoặc tách môi trường.

Nếu một class phải chạy độc quyền so với các test khác trong cùng JUnit engine, `@Isolated` có thể được dùng ở cấp class. Đây là biện pháp mạnh hơn; chỉ dùng khi test thật sự tác động trạng thái toàn cục và không thể cô lập theo resource cụ thể.

## 8. Cấu hình chạy song song trong JUnit Jupiter

JUnit Jupiter cho phép bật parallel execution trong `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
junit.jupiter.execution.parallel.mode.classes.default = concurrent
```

Có thể điều khiển phạm vi chạy đồng thời bằng `@Execution`:

```java
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

@Execution(ExecutionMode.CONCURRENT)
class IndependentServiceTests {
    // Các test method có thể chạy đồng thời.
}
```

Chỉ bật chạy song song sau khi test có thể chạy độc lập. Nếu test còn phụ thuộc thứ tự, cùng sửa một file hoặc cùng reset database, việc bật concurrency chỉ làm lỗi xuất hiện thường xuyên hơn. `@ResourceLock` và `@Isolated` là công cụ điều phối cho những phần chưa thể tách riêng; chúng không thay thế thiết kế dữ liệu riêng.

Lưu ý rằng build tool có thể chạy nhiều JVM fork hoặc nhiều task test đồng thời. Cấu hình JUnit lock trong một engine không tự phối hợp giữa các JVM đó. Nếu tài nguyên dùng chung vượt ra ngoài một process, cần đặt tên duy nhất theo build/test run hoặc dùng cơ chế khóa mà tất cả process cùng tuân thủ.

## 9. Cô lập cache, message broker và dịch vụ ngoài

### Cache

Nếu nhiều test dùng chung Redis hoặc cache service, hãy tạo key có namespace riêng, ví dụ `testRunId + ":customer:" + customerId`. Cleanup chỉ xóa các key thuộc namespace đó. Tránh flush toàn bộ cache dùng chung vì có thể xóa dữ liệu của test khác hoặc dịch vụ khác.

### Message broker

Với Kafka, RabbitMQ hoặc broker tương tự, hãy dùng topic, queue, routing key hoặc consumer group riêng theo test/suite khi có thể. Nếu broker không hỗ trợ tạo tài nguyên cho từng test, hãy dùng correlation ID riêng trong message và chỉ đọc message thuộc test hiện tại. Không dùng một queue dùng chung rồi giả định test nào cũng nhận đúng message mình vừa gửi.

### Mock server và service test

Mỗi test nên sở hữu mock server riêng hoặc dùng một server suite-level với expectation được reset và đồng bộ. Đặt cổng động, dọn response queue sau test và tránh cho nhiều test đồng thời dùng một mock server mutable mà không có namespace.

### Tài nguyên file hoặc object storage

Với S3-compatible storage hoặc dịch vụ lưu trữ khác, dùng bucket/prefix riêng theo test run nếu môi trường cho phép. Dọn đúng prefix đó sau test. Tránh xóa bucket hoặc folder dùng chung.

## 10. Đồng bộ tác vụ bất đồng bộ mà không dùng sleep cố định

Cô lập tài nguyên giải quyết xung đột giữa test; đồng bộ giải quyết việc test quan sát kết quả trước khi tác vụ bất đồng bộ hoàn thành. Không dùng `Thread.sleep(...)` cố định để đoán khi nào worker đã ghi dữ liệu. Hãy đợi một điều kiện có timeout hoặc dùng công cụ kiểm thử reactive phù hợp.

Ví dụ dùng Awaitility để đợi một bản ghi xuất hiện:

```java
import static org.awaitility.Awaitility.await;

import java.time.Duration;

await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertThat(repository.existsById(orderId)).isTrue()
    );
```

Điều kiện chờ cần gắn với dữ liệu riêng của test. Nếu test chờ một bản ghi chung như `latestOrder`, nó vẫn có thể đọc kết quả của test khác. Timeout giới hạn thời gian chờ; nó không làm cho tài nguyên trở nên cô lập.

Với publisher Reactor, dùng `StepVerifier` để xác nhận phần tử và terminal signal. Nếu test đang kiểm tra side effect do scheduler hoặc `@Async` tạo ra, cần đợi side effect cụ thể với timeout và dọn dữ liệu sau khi hoàn tất.

## 11. Một mẫu test kết hợp nhiều ranh giới cô lập

Ví dụ sau minh họa một integration test có server chạy cổng ngẫu nhiên, dữ liệu riêng và thư mục tạm riêng:

```java
import java.nio.file.Path;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ExportIntegrationTests {

    @LocalServerPort
    private int port;

    @Autowired
    private ExportRepository repository;

    @Test
    void exportsOwnCustomerData(@TempDir Path tempDir) {
        String testId = "it-" + UUID.randomUUID();
        Path output = tempDir.resolve("export.csv");

        try {
            repository.save(new ExportRecord(testId, "Mai"));

            String baseUrl = "http://localhost:" + port;
            // Gọi endpoint export với testId và ghi kết quả vào tempDir.

            assertThat(output).exists();
            assertThat(repository.existsById(testId)).isTrue();
        }
        finally {
            repository.deleteById(testId);
        }
    }
}
```

Trong test thực tế, phần HTTP client và việc ghi file sẽ được triển khai theo endpoint của ứng dụng. Ba ranh giới độc lập đã được thiết lập: `RANDOM_PORT` tránh xung đột cổng, `testId` tránh đụng dữ liệu và `@TempDir` tránh đụng file. Vì request chạy trên thread server riêng, cleanup database được thực hiện tường minh thay vì dựa vào transaction rollback của test method.

## 12. Danh sách kiểm tra trước khi bật chạy song song

Với từng test hoặc test class, hãy xác nhận:

1. Dữ liệu database có định danh riêng và cleanup không xóa dữ liệu test khác.
2. Không reset toàn bảng hoặc schema đang được test khác sử dụng.
3. File được ghi trong `@TempDir` hoặc thư mục có namespace riêng.
4. Server bind cổng ngẫu nhiên và test đọc cổng được cấp thay vì dùng cổng cố định.
5. Cache, queue, topic và consumer group có namespace riêng hoặc cơ chế đồng bộ rõ ràng.
6. Không có mutable state trong singleton bean hoặc static field bị nhiều test sửa đồng thời.
7. System property, locale, timezone và trạng thái JVM toàn cục được khôi phục; dùng `@ResourceLock` khi cần.
8. Tác vụ bất đồng bộ được chờ bằng điều kiện có timeout, không dựa vào `sleep` cố định.
9. Mọi server, container, subscription và tài nguyên tạm đều được đóng hoặc dọn trong lifecycle của test.
10. Nếu build chạy nhiều JVM hoặc CI job, cơ chế cô lập có hiệu lực giữa các process, không chỉ trong một JUnit engine.

Test song song ổn định khi mỗi test có dữ liệu và tài nguyên thuộc quyền sở hữu rõ ràng. Dùng transaction rollback cho phần đồng bộ nằm trong transaction test, `@TempDir` cho file, cổng động cho server, namespace riêng cho dịch vụ ngoài và resource lock cho trạng thái toàn cục không thể tách. Khi các ranh giới đó được thiết lập, test có thể chạy đồng thời mà không phụ thuộc thứ tự hoặc thời điểm của test khác.
