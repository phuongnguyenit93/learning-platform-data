# Chạy cả bộ độc lập với thứ tự và tổng hợp bằng chứng

Một bộ kiểm thử Spring đáng tin cậy phải chạy được từ đầu đến cuối mà không cần người phát triển đoán thứ tự test, chạy lại thủ công một vài class hoặc dựa vào dữ liệu còn sót từ lần chạy trước. Mỗi test cần tự chuẩn bị điều kiện của nó, kiểm tra một hành vi có ý nghĩa và dọn tài nguyên mà nó sở hữu. Khi toàn bộ suite chạy trên CI, kết quả cần được tổng hợp thành bằng chứng đủ để biết test nào đã chạy, test nào thất bại, môi trường nào được dùng và lỗi xuất hiện trong bước nào.

Hai mục tiêu gắn với nhau:

- **Độc lập với thứ tự:** kết quả của một test không phụ thuộc vào test khác đã chạy trước hay chưa.
- **Tổng hợp bằng chứng:** một lần chạy toàn bộ suite phải lưu được kết quả, log và thông tin môi trường để nhóm có thể đánh giá chất lượng cũng như điều tra lỗi.

Chạy toàn bộ suite một lần và thấy màu xanh chưa đủ để chứng minh hai mục tiêu này. Cần có cách kiểm tra thứ tự, cô lập dữ liệu, quản lý trạng thái dùng chung và lưu kết quả có thể truy xuất.

## 1. Độc lập với thứ tự nghĩa là gì?

Một test độc lập với thứ tự khi nó cho kết quả đúng dù được chạy trước, sau hoặc xen kẽ với các test khác trong cùng suite. Test phải thiết lập những điều kiện cần thiết của chính nó và không dựa vào side effect do test khác tạo ra.

Ví dụ, một test repository cần kiểm tra tìm khách hàng theo email. Test nên tạo khách hàng cần tìm bằng chính fixture của nó, gọi repository và xác nhận kết quả. Nó không nên giả định một test khác đã chạy trước để thêm khách hàng đó vào database.

Test có phụ thuộc thứ tự thường có các biểu hiện:

- Chạy riêng lẻ thì pass nhưng chạy toàn suite lại fail.
- Chạy class A trước class B thì pass, đổi thứ tự thì fail.
- Chạy lần thứ hai trên cùng workspace thì khác lần đầu vì dữ liệu cũ còn lại.
- Test cần một field static, singleton mutable bean hoặc system property được test khác thiết lập.
- Test có `@Order` hoặc `@TestMethodOrder` chỉ để che việc chia sẻ trạng thái.
- Kết quả phụ thuộc vào ID tự sinh, thời gian hiện tại, thứ tự record hoặc dữ liệu seed không được kiểm soát.

JUnit có thể sắp xếp test theo một thứ tự xác định, nhưng thứ tự đó không nên trở thành một phần ngầm của hợp đồng test. Một bộ test tốt vẫn cho kết quả như nhau khi thứ tự thực thi thay đổi.

### Phân biệt một workflow và sự phụ thuộc thứ tự

Nếu nghiệp vụ thực sự gồm nhiều bước có thứ tự, hãy kiểm tra chúng trong cùng một test scenario hoặc trong một test fixture được điều khiển rõ ràng. Ví dụ, tạo đơn hàng rồi thanh toán đơn hàng là một workflow; test workflow có thể gọi hai thao tác theo thứ tự trong cùng test.

Không nên tạo `createOrderTest()` để test khác dựa vào dữ liệu mà nó tạo, rồi tạo `payOrderTest()` với giả định test trước đã chạy. Test method là đơn vị kiểm tra độc lập, không phải các bước của một kịch bản dùng chung trạng thái ẩn.

## 2. Thiết kế mỗi test tự chuẩn bị dữ liệu

Nguyên tắc cơ bản là Arrange–Act–Assert:

1. **Arrange:** tạo dữ liệu và cấu hình mà test cần.
2. **Act:** thực hiện một hành động của ứng dụng.
3. **Assert:** kiểm tra kết quả quan sát được.

Ví dụ với repository:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void findsCustomerByEmail() {
        Customer customer = repository.saveAndFlush(
                new Customer("customer-a@example.test"));

        Optional<Customer> result =
                repository.findByEmail("customer-a@example.test");

        assertThat(result)
                .isPresent()
                .get()
                .extracting(Customer::getId)
                .isEqualTo(customer.getId());
    }
}
```

Test tự tạo record cần thiết. Nó không cần test khác seed dữ liệu. `saveAndFlush` còn buộc SQL được thực thi trước truy vấn trong trường hợp test cần kiểm tra persistence thật.

Với test service hoặc controller, hãy tạo mock/fake riêng cho test method hoặc dùng dependency injection có phạm vi rõ. Không chia sẻ một mock mutable giữa nhiều test concurrent nếu các test cùng thay đổi expectation hoặc verify state.

### Dùng fixture builder thay vì dữ liệu ẩn

Khi entity có nhiều thuộc tính, builder hoặc factory giúp tạo dữ liệu rõ ràng:

```java
final class CustomerFixtures {

    private CustomerFixtures() {
    }

    static Customer customer(String email) {
        return new Customer(email, "Lan", true);
    }
}
```

Test:

```java
@Test
void filtersActiveCustomers() {
    repository.saveAndFlush(
            CustomerFixtures.customer("active@example.test"));

    List<Customer> result = repository.findByActiveTrue();

    assertThat(result)
            .extracting(Customer::getEmail)
            .contains("active@example.test");
}
```

Fixture nên tạo đối tượng với giá trị hợp lệ và mặc định dễ hiểu. Các thuộc tính liên quan trực tiếp đến hành vi cần test nên được truyền tường minh để người đọc biết điều kiện nào đang được kiểm tra.

### Không dùng dữ liệu cố định chung giữa nhiều test

Một email hoặc mã đơn hàng cố định có thể gây xung đột khi hai test chạy song song hoặc khi dữ liệu đã tồn tại từ lần chạy trước. Có thể tạo khóa riêng cho mỗi test:

```java
String email = "customer-" + UUID.randomUUID() + "@example.test";
```

Nếu cần tái hiện lỗi, hãy ghi lại giá trị hoặc seed đã dùng. Dữ liệu ngẫu nhiên chỉ có ích khi test có thể tái tạo cùng đầu vào từ bằng chứng của lần thất bại.

## 3. Quản lý cleanup và tài nguyên do test sở hữu

Test nên dọn đúng tài nguyên mà nó tạo ra. Việc dọn toàn bộ database hoặc xóa file chung có thể làm hỏng test khác đang chạy đồng thời.

Các ví dụ về cleanup:

- Database: xóa record theo ID hoặc business key duy nhất của test.
- File: tạo thư mục tạm riêng và xóa thư mục đó sau test.
- Mock HTTP server: reset stub và request journal sau mỗi test nếu server được chia sẻ.
- Executor: dừng executor do test tạo và chờ worker kết thúc.
- Container: để lifecycle của Testcontainers quản lý đúng phạm vi suite hoặc test.
- System property/locale/timezone: lưu giá trị cũ, khôi phục trong `finally` và khóa tài nguyên khi cần.

Ví dụ dùng thư mục tạm của JUnit:

```java
class FileExportServiceTest {

    @TempDir
    Path temporaryDirectory;

    @Test
    void writesExportFile() throws IOException {
        Path output = temporaryDirectory.resolve("orders.csv");

        new FileExportService().export(output);

        assertThat(output).exists();
        assertThat(Files.readString(output)).contains("orderId");
    }
}
```

`@TempDir` cấp thư mục riêng cho test và quản lý cleanup. Test không cần dùng một đường dẫn cố định chung trong workspace.

Với database, rollback của test-managed transaction hữu ích nhưng không bao quát transaction độc lập, thread khác hoặc request đến embedded server. Nếu test commit dữ liệu hoặc tạo side effect ngoài transaction, phải cleanup rõ ràng sau khi thao tác hoàn tất.

## 4. Tránh trạng thái dùng chung và phụ thuộc thứ tự

Các nguồn trạng thái dùng chung thường gây lỗi khó tái hiện:

| Nguồn trạng thái | Rủi ro | Cách cô lập |
| --- | --- | --- |
| `static` mutable field | Test trước thay đổi giá trị của test sau | Tránh mutable static; reset có kiểm soát |
| Singleton Spring bean có field mutable | Nhiều test/request cùng sửa một object | Thiết kế stateless hoặc dùng scope/context phù hợp |
| System properties | Ảnh hưởng toàn JVM | Lưu và khôi phục; dùng `@ResourceLock` |
| Locale/timezone mặc định | Parse/format khác giữa môi trường | Cấu hình tường minh hoặc lock khi thay đổi global default |
| Database record dùng chung | Test đọc/xóa/cập nhật dữ liệu của test khác | Dữ liệu riêng, ID duy nhất, cleanup theo ownership |
| File hoặc cổng cố định | Xung đột khi chạy song song | Temp directory và cổng động |
| Mock server hoặc broker | Stub/request/event rò giữa test | Reset hoặc instance riêng |
| Spring context cache | Singleton hoặc context bị thay đổi | Không sửa state dùng chung; dùng `@DirtiesContext` chỉ khi thật sự cần |

### JUnit method order không phải giải pháp cho test phụ thuộc

JUnit Jupiter hỗ trợ `@TestMethodOrder` và `@Order` để sắp xếp method khi có nhu cầu rõ ràng. Ví dụ, một nhóm test có thể cần thứ tự cho mục đích trình diễn hoặc một extension đặc biệt. Tuy nhiên, dùng thứ tự để test method này tạo dữ liệu cho method khác khiến test khó chạy riêng, khó song song và dễ hỏng khi suite thay đổi.

Nếu một scenario cần nhiều bước, hãy đặt các bước trong cùng test:

```java
@Test
void createsAndPaysOrder() {
    Order order = orderService.createOrder(command);
    Payment payment = paymentService.pay(order.getId());

    assertThat(payment.getOrderId()).isEqualTo(order.getId());
    assertThat(payment.getStatus()).isEqualTo(PaymentStatus.APPROVED);
}
```

Test vẫn có thể gọi nhiều component, nhưng dữ liệu và trình tự thuộc về một kịch bản duy nhất, không phụ thuộc method khác.

## 5. Kiểm tra tính độc lập bằng thứ tự ngẫu nhiên

Chạy suite theo thứ tự ngẫu nhiên là một cách chủ động tìm phụ thuộc thứ tự. Nếu test chỉ pass khi chạy theo thứ tự quen thuộc, thay đổi thứ tự có thể làm lộ trạng thái bị rò.

JUnit Jupiter hỗ trợ random orderer cho test method và test class. Có thể cấu hình trong `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.testmethod.order.default = org.junit.jupiter.api.MethodOrderer$Random
junit.jupiter.testclass.order.default = org.junit.jupiter.api.ClassOrderer$Random
junit.jupiter.execution.order.random.seed = 20261113
```

Các thuộc tính này yêu cầu JUnit Jupiter hỗ trợ random orderer. Seed cố định giúp tái hiện cùng thứ tự trong các lần chạy tiếp theo. Khi muốn thử thứ tự khác, đổi seed và ghi lại seed đã dùng.

Có thể đặt orderer trực tiếp trên class:

```java
@TestMethodOrder(MethodOrderer.Random.class)
class CustomerServiceTest {

    @Test
    void createsCustomer() {
        // Test độc lập.
    }

    @Test
    void rejectsInvalidEmail() {
        // Test độc lập.
    }
}
```

Random order không đồng nghĩa với parallel execution. JUnit có thể chạy test theo thứ tự ngẫu nhiên nhưng vẫn tuần tự. Đây là cách tách riêng hai biến điều tra:

- Random order kiểm tra phụ thuộc thứ tự.
- Parallel execution kiểm tra tranh chấp khi nhiều test cùng chạy.

Nên thử từng chế độ riêng trước, sau đó kết hợp nếu cần.

### Lưu seed và thứ tự khi có lỗi

Khi random order làm test thất bại, lưu seed, test class/method và log thực thi. Chạy lại với cùng seed để tái hiện; sau đó chạy một nhóm test nhỏ hơn để tìm test gây ảnh hưởng.

Không nên đổi seed liên tục cho đến khi suite pass rồi kết luận lỗi đã hết. Điều cần tìm là trạng thái nào được tạo hoặc thay đổi bởi test trước, và vì sao test sau lại phụ thuộc vào trạng thái đó.

## 6. Chạy tuần tự và song song như hai phép thử riêng

Độc lập với thứ tự và an toàn khi chạy song song là hai thuộc tính liên quan nhưng khác nhau.

| Cách chạy | Phát hiện tốt |
| --- | --- |
| Thứ tự ngẫu nhiên, tuần tự | Test phụ thuộc vào trạng thái do test trước để lại |
| Thứ tự cố định, song song | Race condition và tranh chấp tài nguyên |
| Thứ tự ngẫu nhiên, song song | Kết hợp phụ thuộc thứ tự và tranh chấp đồng thời |
| Chạy từng test riêng | Lỗi nằm trong test hoặc dependency trực tiếp |

JUnit Jupiter có thể bật parallel execution bằng:

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = same_thread
junit.jupiter.execution.parallel.mode.classes.default = concurrent
junit.jupiter.execution.parallel.config.strategy = fixed
junit.jupiter.execution.parallel.config.fixed.parallelism = 4
```

Cấu hình này cho phép test class chạy đồng thời, còn method trong mỗi class giữ tuần tự theo mode mặc định. Đây có thể là điểm bắt đầu thận trọng cho integration test Spring. Cần bảo đảm database, connection pool, container và các tài nguyên dùng chung đủ khả năng chịu tải.

Nếu test thay đổi system property hoặc một tài nguyên global, dùng `@ResourceLock` với cùng resource key ở mọi test truy cập xung đột. Nếu test không an toàn với parallel, đánh dấu `@Execution(SAME_THREAD)` hoặc tách nó vào nhóm tuần tự trong khi xử lý nguyên nhân.

## 7. Cô lập Spring ApplicationContext

Spring TestContext Framework cache `ApplicationContext` giữa các test có cấu hình tương đương để giảm thời gian khởi động. Context được cache có thể chứa singleton bean, datasource, executor, cache hoặc mock server. Vì vậy, test không nên thay đổi trạng thái mutable của bean dùng chung rồi kỳ vọng context mới sẽ được tạo cho test tiếp theo.

Một số nguyên tắc:

- Giữ service và controller stateless khi có thể.
- Không lưu dữ liệu riêng của test trong field singleton.
- Reset cache hoặc collaborator có trạng thái nếu đó là trách nhiệm của test.
- Dùng cấu hình/profile rõ ràng để tránh phụ thuộc môi trường developer.
- Dùng `@DirtiesContext` khi test thực sự làm context không còn dùng được, không dùng nó như cleanup chung cho mọi lỗi dữ liệu.
- Không đóng tài nguyên do context sở hữu trong một test nếu test khác còn dùng context đó.

`@DirtiesContext` đánh dấu context cần bị loại khỏi cache và đóng theo phạm vi. Nó không xóa dữ liệu đã commit trong database, không reset service ngoài và không sửa race condition ở static state.

### Test slice và full context

Test slice như `@WebMvcTest` hoặc `@DataJpaTest` giúp giảm số bean và tài nguyên cần khởi tạo. `@SpringBootTest` kiểm tra cấu hình rộng hơn nhưng thường nặng hơn. Dù dùng loại nào, test vẫn cần độc lập về dữ liệu và side effect.

Không nên dùng full context chỉ để chia sẻ một bộ dữ liệu chung giữa nhiều test. Hãy để mỗi test tạo dữ liệu cần thiết hoặc dùng fixture có vòng đời được quản lý rõ ràng.

## 8. Tổ chức dữ liệu database để toàn suite chạy lặp lại được

Một bộ integration test database nên có thể chạy nhiều lần trên database mới hoặc database đã được cleanup mà không phụ thuộc vào ID hay thứ tự test.

Các thực hành hữu ích:

- Tạo dữ liệu trong test bằng repository, `TestEntityManager`, SQL script hoặc fixture có chủ đích.
- Dùng business key duy nhất cho từng test khi database được chia sẻ.
- Không giả định ID tự sinh bắt đầu từ một giá trị cụ thể hoặc liên tục sau rollback.
- Không dựa vào thứ tự truy vấn nếu query không có `ORDER BY`.
- Flush khi cần xác nhận SQL và constraint.
- Xác định rõ transaction của test, transaction độc lập và thao tác chạy trên thread khác.
- Cleanup theo khóa do test sở hữu, không xóa toàn bảng dùng chung.
- Nếu test cần trạng thái database đặc biệt, dùng schema/database riêng hoặc container riêng theo suite.

Ví dụ dùng `@Sql` để chuẩn bị dữ liệu cho một test:

```java
@Test
@Sql(scripts = "/sql/customer-test-data.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
@Sql(scripts = "/sql/cleanup-customer-test-data.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD)
void findsSeededCustomer() {
    assertThat(repository.findByEmail("seeded@example.test")).isPresent();
}
```

Script cần giới hạn dữ liệu bằng key riêng của test và có thể chạy nhiều lần an toàn nếu suite được chạy lại. Nếu nhiều test cùng dùng script với cùng dữ liệu và chạy song song, chúng vẫn có thể xung đột; khi đó cần dữ liệu riêng hoặc schema riêng.

## 9. Kiểm soát thời gian, random và tài nguyên hệ điều hành

Để test chạy nhất quán trên developer machine và CI:

- Tiêm `Clock` thay vì gọi trực tiếp `Instant.now()` hoặc `LocalDate.now()` trong logic cần kiểm tra.
- Dùng timezone và locale tường minh.
- Cố định random seed hoặc ghi seed khi lỗi xảy ra.
- Dùng `@TempDir` thay cho đường dẫn file cố định.
- Dùng cổng động cho embedded server/mock server.
- Dùng readiness check hoặc điều kiện hoàn tất thay cho `Thread.sleep`.
- Đặt timeout đủ rộng cho CI nhưng vẫn có giới hạn để test không treo vô hạn.
- Dọn executor, socket, file handle và container mà test tạo ra.

Ví dụ với `Clock`:

```java
@Test
void expiresAtExpectedInstant() {
    Clock clock = Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"), ZoneOffset.UTC);
    ExpirationService service = new ExpirationService(clock);

    assertThat(service.isExpired(
            Instant.parse("2025-12-31T23:59:59Z"))).isTrue();
}
```

Test không phụ thuộc thời điểm thực tế chạy. Điều này giúp kết quả ổn định khi CI chạy vào ngày khác hoặc ở timezone khác.

## 10. Chạy toàn bộ test suite bằng build tool

Sau khi test có tính độc lập, cần chạy cả bộ trong đúng lifecycle mà dự án dùng.

### Gradle

Chạy task test:

```bash
./gradlew test
```

Chạy các verification task chuẩn:

```bash
./gradlew check
```

`check` thường phụ thuộc vào `test` và các verification task khác được dự án gắn vào lifecycle. Nếu dự án có integration test task riêng, hãy xác nhận task đó được nối vào `check` hoặc gọi tường minh.

Ví dụ một task integration test riêng:

```groovy
tasks.register('integrationTest', Test) {
    description = 'Runs integration tests.'
    group = 'verification'
    useJUnitPlatform()
    shouldRunAfter(tasks.test)
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    filter {
        includeTestsMatching '*IntegrationTest'
    }
}

tasks.named('check') {
    dependsOn tasks.named('integrationTest')
}
```

Đây là cấu hình minh họa; dự án nên dùng source set riêng cho integration test nếu cần tách dependency, resource và báo cáo. Không nên vô tình chạy cùng một test hai lần trong `test` và `integrationTest` chỉ vì filter hoặc source set chưa rõ.

Gradle lưu kết quả XML thường tại `build/test-results/test` và báo cáo HTML tại `build/reports/tests/test`. Với task riêng, thư mục báo cáo thường có tên task tương ứng. Có thể cấu hình test logging để in failure và summary ra console, nhưng XML report nên được giữ làm artifact máy đọc được.

### Maven

Chạy pha test:

```bash
./mvnw test
```

Chạy đến pha verify:

```bash
./mvnw verify
```

Surefire thường chạy unit test ở pha `test`. Failsafe thường chạy integration test qua các pha `integration-test` và `verify` khi plugin được cấu hình. Pha `verify` cho phép plugin thực hiện kiểm tra kết quả integration test sau khi các test đã chạy.

Kết quả Surefire thường nằm trong `target/surefire-reports`; kết quả Failsafe thường nằm trong `target/failsafe-reports`. Giữ cả XML report và log console để CI có thể tổng hợp số test, failure, error và skipped.

### Chạy lại một test để điều tra không thay thế chạy full suite

Lệnh chạy riêng hữu ích để khoanh vùng:

```bash
./gradlew test --tests "com.example.orders.OrderIntegrationTest"
```

```bash
./mvnw -Dtest=OrderIntegrationTest test
```

Sau khi sửa, vẫn cần chạy lại full suite và lifecycle CI. Một test xanh riêng lẻ không chứng minh nó độc lập với các test khác.

## 11. Tổng hợp bằng chứng từ JUnit và build tool

Một lần chạy toàn suite nên tạo ra ít nhất hai loại đầu ra:

1. **Báo cáo máy đọc được:** JUnit XML hoặc báo cáo tương đương để CI tổng hợp test count, pass/fail/error/skipped và liên kết đến test thất bại.
2. **Báo cáo cho người đọc:** HTML report, console log, stack trace và artifact chẩn đoán để developer hiểu ngữ cảnh lỗi.

Thông tin nên tổng hợp:

| Nhóm bằng chứng | Nội dung |
| --- | --- |
| Nhận dạng build | Commit SHA, branch, build number, thời điểm chạy |
| Môi trường | JDK, OS, CPU/RAM, timezone, locale |
| Phiên bản | Spring Boot, Spring Framework, JUnit, Gradle/Maven, database/container image |
| Cấu hình test | Active profiles, properties quan trọng, parallel mode, random seed |
| Kết quả | Tổng test, pass, failure, error, skipped, duration |
| Failure | Test class/method, assertion, stack trace, suppressed exceptions |
| Dependency ngoài | Database/container/service version, readiness và log liên quan |
| Retry/flaky | Lần đầu fail hay pass, số lần retry, trạng thái cuối |

Không phải mọi giá trị đều cần ghi vào log của mỗi test. Có thể ghi một file metadata ở cấp build và liên kết nó với XML/HTML report để tránh lặp thông tin.

### JUnit XML và HTML report

JUnit XML giúp CI nhận diện test case, duration và failure message. HTML report thuận tiện cho việc duyệt test class và stack trace. Console log có ích để xem thứ tự thực thi, startup log của Spring, container readiness và thông tin không nằm trong XML.

Không nên chỉ lưu summary như “1 test failed”. Hãy giữ report chi tiết của lần chạy thất bại và log đầy đủ liên quan. Khi CI job thất bại, artifact vẫn cần được upload để developer tải về.

## 12. Ghi lại metadata của lần chạy

Có thể tạo một file metadata trước khi chạy test để gắn thông tin môi trường với report:

```json
{
  "commit": "<git-sha>",
  "javaVersion": "<java-version>",
  "os": "<operating-system>",
  "timezone": "UTC",
  "springProfile": "test",
  "parallelExecution": false,
  "randomOrderSeed": 20261113,
  "databaseImage": "postgres:<pinned-version>"
}
```

Các giá trị trong ví dụ là placeholder hoặc cấu hình minh họa. CI nên ghi giá trị thực của build, không sao chép chuỗi placeholder. Nếu không dùng random ordering hoặc database container, ghi rõ cấu hình tương ứng thay vì bỏ qua một cách mơ hồ.

Có thể lấy thông tin môi trường từ build script hoặc pipeline và lưu cạnh test report. Tránh ghi password, token, connection string chứa secret hoặc dữ liệu cá nhân vào artifact. Chỉ lưu những thông tin cần để tái hiện lỗi.

### Gắn định danh vào log

Khi nhiều test chạy đồng thời, log của các request có thể xen kẽ. Dùng correlation ID hoặc test-specific identifier trong dữ liệu request và log giúp liên kết một test với thao tác server. Không nên dựa vào thứ tự dòng log để suy ra thứ tự test khi parallel execution đang bật.

Với Spring Boot, có thể cấu hình logging pattern để in thread name và correlation ID nếu ứng dụng đã có cơ chế MDC. Hãy dọn MDC sau request/test để giá trị không rò sang thread được tái sử dụng.

## 13. Tự động thu thập bằng chứng khi test thất bại

JUnit Jupiter cung cấp extension callback như `TestWatcher` để ghi nhận trạng thái test. Ví dụ đơn giản:

```java
class FailureRecordingExtension implements TestWatcher {

    @Override
    public void testFailed(ExtensionContext context, Throwable cause) {
        String testName = context.getDisplayName();
        System.err.println("FAILED TEST: " + testName);
        cause.printStackTrace(System.err);
    }
}
```

Đăng ký extension:

```java
@ExtendWith(FailureRecordingExtension.class)
class CustomerServiceTest {
    // Tests.
}
```

Đây chỉ là ví dụ ghi thông tin tối thiểu. Trong hệ thống CI, thường nên để JUnit XML và test runner quản lý kết quả chính thức, còn extension chỉ bổ sung metadata hoặc thu thập trạng thái đặc thù. Nếu extension ghi file, phải tạo tên file an toàn và duy nhất cho mỗi test khi chạy song song; không để nhiều thread ghi đè cùng một file.

`TestWatcher` không thay thế báo cáo JUnit và không nên nuốt exception của test. Một test thất bại vẫn phải được test engine báo thất bại.

### Thu thập log và trạng thái dịch vụ

Với integration test dùng Testcontainers hoặc mock server, có thể lưu log container và trạng thái readiness khi suite thất bại. Nên gắn artifact với tên container/service và test class liên quan. Thu thập log trước khi container bị dừng hoặc xóa; nếu lifecycle đóng container quá sớm, log có thể không còn.

Với Spring application context, log startup có thể chỉ ra bean nào không khởi tạo được. Với database, log server và SQL có thể chỉ ra deadlock, timeout, constraint violation hoặc connection exhaustion. Thu thập đúng nguồn giúp giảm thời gian phỏng đoán.

## 14. Cấu hình CI để không mất báo cáo khi test fail

CI nên chạy full suite và luôn upload report, kể cả khi bước test trả exit code khác 0. Ví dụ pipeline tổng quát:

```text
Checkout source
      |
      v
Record commit and environment metadata
      |
      v
Compile and run unit tests
      |
      v
Run integration tests
      |
      v
Collect JUnit XML, HTML and service logs
      |
      v
Publish test report artifacts (also when tests fail)
      |
      v
Fail build if required tests failed
```

Upload report cần được cấu hình theo cơ chế `always` hoặc `if: always()` tương ứng với CI provider. Không nên dùng điều kiện chỉ upload khi job thành công, vì artifact có giá trị nhất thường là từ lần chạy thất bại.

Ví dụ YAML mang tính minh họa:

```yaml
- name: Run tests
  run: ./gradlew check

- name: Upload test reports
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: spring-test-reports
    path: |
      **/build/test-results/**
      **/build/reports/tests/**
```

Đường dẫn và cú pháp cần điều chỉnh theo cấu trúc Gradle project và CI provider thực tế. Với Maven, thêm `target/surefire-reports/**` và `target/failsafe-reports/**`. Nếu dùng nhiều module, cần thu thập report từ tất cả module.

### Không biến retry thành kết quả xanh giả

Nếu CI có retry, phải lưu kết quả lần đầu và đánh dấu test đã pass sau retry là flaky. Báo cáo tổng hợp nên phân biệt:

- Pass ngay lần đầu.
- Fail nhưng pass sau retry.
- Fail sau khi hết số lần retry.
- Skipped hoặc quarantined.

Một suite chỉ đáng tin khi tỷ lệ flaky được theo dõi và có owner xử lý. Không nên xóa stack trace ban đầu hoặc chỉ công bố trạng thái cuối cùng là pass.

## 15. Tạo ma trận bằng chứng cho toàn bộ suite

Một cách trình bày giúp review nhanh là ma trận theo nhóm test:

| Nhóm | Phạm vi | Report cần có | Bằng chứng bổ sung |
| --- | --- | --- | --- |
| Unit | Logic thuần Java | JUnit XML, duration | Seed nếu random, log failure |
| MVC slice | Controller và Spring MVC | JUnit XML, HTML | Request/response, active profile |
| JPA slice | Repository và persistence | JUnit XML, SQL/failure log khi cần | Database version, transaction/cleanup |
| Integration | Nhiều tầng ứng dụng | JUnit XML, HTML | Spring context log, dependency versions |
| HTTP server | Embedded server và network path | JUnit XML | Port, server log, request correlation ID |
| Native/AOT | Generated context hoặc native executable | Build/test report | GraalVM version, AOT artifacts, runtime hints |

Ma trận giúp nhóm biết bằng chứng nào cần có cho từng loại test. Không cần bật SQL trace hoặc debug log cho mọi test; chỉ thu thập sâu hơn khi loại test hoặc lỗi cần thông tin đó.

## 16. Quy trình chạy toàn bộ suite độc lập và có thể truy vết

Một quy trình thực hành có thể áp dụng cho dự án Spring:

1. **Chuẩn bị môi trường:** checkout commit sạch, dùng JDK và dependency version được pin, cấu hình profile test, database/container và timezone rõ ràng.
2. **Chạy test riêng khi điều tra:** xác nhận test không có lỗi deterministic trong phạm vi trực tiếp.
3. **Chạy toàn class và nhóm liên quan:** tìm state rò giữa các method hoặc class.
4. **Thử random order:** ghi seed để tìm phụ thuộc thứ tự và tái hiện được lỗi.
5. **Thử parallel:** tách riêng khỏi random order để tìm race condition và tranh chấp tài nguyên.
6. **Chạy full lifecycle:** dùng `./gradlew check` hoặc `./mvnw verify` theo build của dự án, bao gồm integration test được cấu hình.
7. **Thu thập báo cáo:** lưu JUnit XML, HTML, console log, metadata môi trường và log dịch vụ liên quan.
8. **Tổng hợp kết quả:** phân biệt pass, fail, error, skipped, flaky sau retry và test quarantined.
9. **Lưu bằng chứng khi fail:** CI vẫn upload report dù test task thất bại.
10. **Sửa nguyên nhân:** cô lập dữ liệu, đồng bộ async, loại bỏ shared state hoặc sửa cấu hình môi trường; sau đó chạy lại full suite với cùng điều kiện.

## 17. Tiêu chí hoàn tất cho một bộ test

Một suite có thể xem là sẵn sàng cho CI khi:

- Có thể chạy từ checkout sạch bằng lệnh build đã ghi trong dự án.
- Không yêu cầu một test khác chạy trước để tạo dữ liệu hoặc cấu hình.
- Có thể chạy từng test hoặc từng class riêng để điều tra.
- Random order không làm thay đổi kết quả chức năng.
- Parallel execution được bật ở phạm vi đã xác định mà không gây race condition chưa kiểm soát.
- Dữ liệu và tài nguyên được tạo, quản lý và cleanup theo ownership.
- Test không phụ thuộc thời gian, timezone, locale hoặc thứ tự collection ngoài hợp đồng.
- Transaction, async task và request server có ranh giới rõ.
- CI lưu report máy đọc được và log đủ để truy vết failure.
- Retry hoặc quarantine, nếu có, được ghi nhận và có người chịu trách nhiệm.

## 18. Kết luận

Chạy cả bộ độc lập với thứ tự bắt đầu từ việc mỗi test tự chuẩn bị dữ liệu, không chia sẻ trạng thái mutable và dọn tài nguyên do chính nó tạo ra. Dùng random order để tìm phụ thuộc thứ tự, dùng parallel execution để tìm tranh chấp đồng thời, và kiểm tra full lifecycle sau khi sửa.

Tổng hợp bằng chứng nghĩa là lưu JUnit XML/HTML, stack trace, log dịch vụ và metadata môi trường ngay cả khi CI thất bại. Khi kết hợp tính độc lập của test với báo cáo có thể truy vết, bộ kiểm thử Spring trở thành một tín hiệu đáng tin cho thay đổi phần mềm: lỗi có thể tái hiện, phạm vi ảnh hưởng có thể khoanh vùng và kết quả của toàn suite có thể được review từ cùng một lần chạy.
