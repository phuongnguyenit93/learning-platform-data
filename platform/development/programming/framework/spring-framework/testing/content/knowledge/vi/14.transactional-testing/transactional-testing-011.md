# Timeout đổi luồng và dữ liệu không được rollback

Trong Spring Framework Testing, một test method có thể chạy bên trong transaction do Spring Test quản lý. Mặc định, Spring rollback transaction này sau khi test kết thúc để dữ liệu kiểm thử không tồn tại lâu dài.

Cơ chế đó dựa trên một điều kiện quan trọng: **transaction được gắn với thread đang thực thi test**. Spring liên kết transaction với JDBC connection hoặc JPA EntityManager hiện tại bằng tài nguyên quản lý theo thread, thường thông qua ThreadLocal.

Nếu bài test dùng timeout theo kiểu chạy phần code được kiểm tra trên thread khác, phần code đó không tự động tham gia transaction của test. Thao tác ghi có thể chạy trong transaction riêng hoặc ở chế độ auto-commit. Khi test kết thúc, Spring rollback transaction ban đầu nhưng không thể rollback những thay đổi đã được thread khác commit.

Đây là một nguyên nhân khiến test có vẻ đã rollback thành công nhưng dữ liệu vẫn còn trong database.

## 1. Spring Test quản lý transaction như thế nào?

Khi test method được đánh dấu @Transactional, Spring TestContext Framework có thể mở một test-managed transaction trước khi chạy test method và rollback sau khi test hoàn tất.

Ví dụ:

~~~java
@SpringBootTest
@Transactional
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void savesCustomer() {
        customerRepository.save(
                new Customer("Linh", "linh@example.com"));

        assertEquals(1, customerRepository.count());
    }
}
~~~

Với cấu hình mặc định của Spring Test, transaction của test được rollback sau khi phương thức kiểm thử kết thúc. Nhờ đó, bản ghi được tạo trong test không để lại dữ liệu lâu dài.

Trình tự khái quát:

~~~text
Spring TestContext
      |
      | bắt đầu test-managed transaction
      v
Test thread
      |
      | gọi repository / service
      | các thao tác tham gia transaction hiện tại
      v
Database
      |
      | test method kết thúc
      v
Spring TestContext rollback transaction
~~~

Điều này hoạt động vì lời gọi repository và service diễn ra trên cùng thread với transaction của test, đồng thời dùng cùng transaction manager và tài nguyên được Spring quản lý.

### Transaction được gắn với thread

Trong mô hình transaction imperative của Spring, transaction resource thường được liên kết với thread hiện tại. TransactionSynchronizationManager lưu thông tin tài nguyên và synchronization theo thread.

Khi transaction manager mở transaction cho JDBC hoặc JPA, tài nguyên tương ứng được bind vào thread. Các thao tác tiếp theo trên cùng thread có thể lấy lại tài nguyên đó và tham gia transaction hiện tại theo propagation phù hợp.

Một thread mới không tự nhận được transaction resource đã bind ở thread ban đầu.

Điều này khác với việc truyền một object Java thông thường. Gửi reference của service, repository hoặc EntityManagerFactory sang thread khác không làm transaction của thread ban đầu tự động được truyền theo.

## 2. Timeout có thể đổi thread như thế nào?

JUnit Jupiter cung cấp hai assertion timeout thường gặp:

- **assertTimeout:** thực thi executable trên thread gọi assertion; chỉ báo lỗi nếu thời gian thực thi vượt giới hạn sau khi executable hoàn tất.
- **assertTimeoutPreemptively:** thực thi executable trên một thread khác để có thể ngắt khi vượt giới hạn.

Sự khác biệt này rất quan trọng khi test nằm trong transaction do Spring quản lý.

### assertTimeout giữ nguyên thread

~~~java
@Test
@Transactional
void usesNonPreemptiveTimeout() {
    assertTimeout(Duration.ofSeconds(2), () -> {
        customerRepository.save(
                new Customer("Linh", "linh@example.com"));
    });
}
~~~

Executable được chạy trên thread đang thực thi test. Nếu repository tham gia transaction hiện tại, thay đổi dữ liệu vẫn nằm trong test-managed transaction và có thể được rollback khi test kết thúc.

Điểm cần hiểu là assertTimeout không dừng executable ngay tại thời điểm hết thời gian. Nó đợi executable hoàn tất rồi mới so sánh thời lượng thực tế với giới hạn. Nếu code bị treo vô thời hạn, assertion cũng phải chờ nó trả về.

### assertTimeoutPreemptively đổi sang thread khác

~~~java
@Test
@Transactional
void preemptiveTimeoutCanEscapeTestTransaction() {
    assertTimeoutPreemptively(
            Duration.ofSeconds(2),
            () -> customerRepository.save(
                    new Customer("Linh", "linh@example.com"))
    );
}
~~~

Đoạn code trên có rủi ro. JUnit chạy callback trên thread riêng. Thread đó không tham gia transaction được Spring Test bind vào thread thực thi test method.

Nếu lời gọi repository tự mở transaction, transaction đó có thể commit khi phương thức repository hoàn tất. Transaction của test ở thread ban đầu sau đó rollback, nhưng bản ghi đã được commit trong transaction khác vẫn tồn tại.

### So sánh hai cách timeout

| Đặc điểm | assertTimeout | assertTimeoutPreemptively |
|---|---|---|
| Thread thực thi callback | Thread hiện tại | Thread riêng |
| Giữ transaction thread-bound của Spring Test | Có, nếu không tự chuyển thread ở bên trong | Không |
| Có thể báo timeout trước khi callback kết thúc | Không | Có |
| Phù hợp với test ghi database trong test-managed transaction | Thường phù hợp hơn | Có nguy cơ ghi ngoài transaction |
| Có thể dừng code đang treo ngay khi hết hạn | Không | Có thể yêu cầu ngắt thread; không bảo đảm code luôn dừng |

Nếu mục tiêu chỉ là phát hiện một test chạy chậm, ưu tiên cách timeout giữ nguyên thread khi test phụ thuộc vào transaction hoặc ThreadLocal context.

## 3. Vì sao dữ liệu vẫn còn sau khi test rollback?

Xem luồng sau:

~~~text
Thread A: JUnit test thread
    |
    +-- Spring mở transaction T1
    |
    +-- assertTimeoutPreemptively(...)
             |
             +-- Thread B: callback thread
                    |
                    +-- repository.save(...)
                    |
                    +-- transaction T2 hoặc auto-commit
                    |
                    +-- ghi dữ liệu và commit
    |
    +-- callback kết thúc hoặc timeout
    |
    +-- Spring rollback T1
             |
             +-- T2 đã commit nên không bị rollback
~~~

Có hai transaction độc lập:

- **T1:** test-managed transaction được Spring mở trên thread A.
- **T2:** transaction mới do repository hoặc service mở trên thread B, hoặc thao tác ghi được commit theo chế độ auto-commit của kết nối.

Rollback T1 chỉ hoàn tác những thay đổi thuộc T1. Nó không thể đảo ngược một transaction khác đã commit.

### Repository có thể tự mở transaction

Các phương thức ghi của Spring Data JPA repository thường được cấu hình transactional. Khi được gọi mà không có transaction hiện tại trên thread B, repository có thể mở transaction riêng, thực hiện thao tác và commit khi phương thức hoàn tất.

Ví dụ:

~~~java
assertTimeoutPreemptively(
        Duration.ofSeconds(1),
        () -> customerRepository.saveAndFlush(customer)
);
~~~

Nếu saveAndFlush chạy trong transaction riêng trên thread B, transaction đó có thể commit độc lập với transaction của test.

Không nên giả định rằng vì test method có @Transactional nên mọi lời gọi repository phát sinh trong thời gian test đều thuộc transaction đó. Điều này chỉ đúng khi lời gọi thực sự chạy trong cùng transaction context.

### JDBC cũng có thể ghi ngoài transaction của test

Nếu callback thread dùng JdbcTemplate, Spring lấy connection theo thread hiện tại. Thread mới không có connection được bind từ test thread, nên thao tác có thể lấy connection khác.

Tùy cấu hình datasource và transaction manager, thao tác đó có thể:

- Chạy với auto-commit bật.
- Tham gia một transaction riêng do service hoặc repository mở.
- Được bao quanh bởi một transaction khác do code trong thread mới tạo.

Trong các trường hợp đó, rollback transaction của test thread không hoàn tác được thay đổi.

## 4. Ví dụ tái hiện dữ liệu thoát khỏi rollback

Giả sử có repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

Một test có thể tạo dữ liệu bằng timeout preemptive:

~~~java
@SpringBootTest
@Transactional
class PreemptiveTimeoutTransactionTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void writesCustomerOnAnotherThread() {
        assertTimeoutPreemptively(
                Duration.ofSeconds(2),
                () -> customerRepository.saveAndFlush(
                        new Customer(
                                "Linh",
                                "linh-timeout@example.com"))
        );
    }
}
~~~

Sau khi test hoàn tất, Spring rollback transaction gắn với test thread. Tuy nhiên, thao tác saveAndFlush có thể đã chạy và commit trong transaction riêng trên callback thread.

Một test khác chạy sau đó có thể tìm thấy email linh-timeout@example.com dù test tạo dữ liệu đã kết thúc.

Đây là ví dụ về rủi ro, không phải cách viết test được khuyến nghị. Nếu cần kiểm tra timeout và persistence, hãy thiết kế transaction boundary và cleanup rõ ràng.

## 5. @Timeout cũng cần chú ý đến thread mode

JUnit Jupiter có annotation @Timeout. Annotation này hỗ trợ cấu hình thread mode:

- **SAME_THREAD:** chạy test trên thread hiện tại và áp dụng timeout theo chế độ này.
- **SEPARATE_THREAD:** chạy test trong thread riêng.
- **INFERRED:** lấy chế độ từ cấu hình mặc định của JUnit.

Ví dụ chọn rõ SAME_THREAD:

~~~java
@Test
@Timeout(
        value = 2,
        unit = TimeUnit.SECONDS,
        threadMode = Timeout.ThreadMode.SAME_THREAD)
@Transactional
void checksOperationWithinTimeoutOnSameThread() {
    customerRepository.save(
            new Customer("Linh", "linh@example.com"));
}
~~~

JUnit Jupiter mặc định suy ra thread mode từ cấu hình toàn cục; cấu hình mặc định thông thường là SAME_THREAD. Tuy nhiên, dự án có thể thay đổi chế độ bằng junit-platform.properties hoặc cấu hình hệ thống.

Ví dụ cấu hình mặc định:

~~~properties
junit.jupiter.execution.timeout.thread.mode.default = SAME_THREAD
~~~

Nếu dự án đặt giá trị SEPARATE_THREAD hoặc annotation chỉ định rõ SEPARATE_THREAD, test có thể đổi thread và mất transaction context của Spring Test.

Khi đọc một test có @Timeout, hãy kiểm tra cả:

1. threadMode được khai báo trực tiếp trên annotation;
2. cấu hình timeout mặc định của JUnit;
3. các lời gọi bên trong test có tự chuyển sang executor hoặc thread khác hay không.

@Timeout với SAME_THREAD không làm cho một tác vụ bất đồng bộ tự động chạy trong transaction của test. Nó chỉ quy định thread thực thi test method theo chế độ timeout đó.

## 6. Timeout cùng thread vẫn có giới hạn

assertTimeout và @Timeout với SAME_THREAD tránh việc JUnit chủ động chuyển callback sang thread khác. Điều này giúp giữ ThreadLocal context trong quá trình thực thi bình thường.

Tuy nhiên, chúng không giải quyết mọi vấn đề:

- assertTimeout chỉ báo vượt thời gian sau khi callback hoàn tất.
- Timeout cùng thread có thể ngắt test thread khi hết hạn, nhưng code không phản ứng với interruption vẫn có thể tiếp tục.
- Một lời gọi tự tạo thread hoặc gửi task vào executor vẫn chạy ở thread khác.
- Timeout không rollback các transaction độc lập đã commit.
- Timeout không tự dừng một request hoặc tác vụ ở hệ thống ngoài.

Nếu test thực hiện thao tác không thể hoàn tác, chẳng hạn gửi thanh toán, ghi file hoặc phát message, hãy xác định cách cleanup và idempotency riêng. Đừng xem timeout là cơ chế rollback.

## 7. Phân biệt timeout của test với xử lý bất đồng bộ thật

Một bài test có thể đổi thread vì timeout preemptive. Một ứng dụng cũng có thể đổi thread do sử dụng:

- @Async.
- Executor hoặc thread pool.
- CompletableFuture.
- TaskExecutor.
- Message listener container.
- Scheduler.
- Reactive pipeline có chuyển scheduler.

Các trường hợp này đều có thể khiến code chạy ngoài thread đang giữ transaction của test.

Ví dụ:

~~~java
@Service
public class CustomerImportService {

    @Async
    public CompletableFuture<Void> importCustomer(CustomerData data) {
        // Ghi dữ liệu trên worker thread.
        return CompletableFuture.completedFuture(null);
    }
}
~~~

Nếu test gọi importCustomer trong khi test thread đang có transaction, worker thread không tự tham gia transaction đó.

Nếu method được đánh dấu @Transactional và được gọi qua Spring proxy trên worker thread, transaction có thể được mở riêng trên worker thread. Khi method hoàn tất, transaction riêng đó có thể commit. Rollback của test thread không thể hoàn tác transaction độc lập đã commit.

### Chờ Future không làm transaction được truyền sang worker thread

~~~java
@Test
@Transactional
void waitsForAsyncImport() throws Exception {
    CompletableFuture<Void> future =
            customerImportService.importCustomer(data);

    future.get(2, TimeUnit.SECONDS);
}
~~~

future.get() chạy trên test thread và chờ kết quả. Nhưng việc chờ không chuyển transaction của test sang worker thread. Worker vẫn có transaction context riêng.

Điểm cần phân biệt:

- **Thread đang chờ:** test thread, có thể đang giữ test-managed transaction.
- **Thread thực hiện import:** worker thread, không tự nhận transaction của test.
- **Kết quả:** dữ liệu do worker ghi có thể đã commit độc lập trước khi future hoàn tất.

Nếu test kiểm tra một luồng bất đồng bộ ghi database, cần xác nhận dữ liệu qua ranh giới persistence và có cleanup cho dữ liệu đã commit.

## 8. Transaction propagation không vượt qua thread boundary

Spring transaction propagation xác định cách một lời gọi tham gia hoặc tạo transaction trong execution context hiện tại.

Một số propagation thường gặp:

| Propagation | Ý nghĩa trong cùng thread |
|---|---|
| REQUIRED | Tham gia transaction hiện tại nếu có; nếu không thì tạo transaction mới |
| REQUIRES_NEW | Tạo transaction mới và tạm suspend transaction hiện tại |
| SUPPORTS | Tham gia transaction nếu có; nếu không thì chạy không có transaction |
| NOT_SUPPORTED | Suspend transaction hiện tại và chạy không có transaction |
| MANDATORY | Yêu cầu phải có transaction hiện tại |
| NEVER | Yêu cầu không có transaction hiện tại |
| NESTED | Dùng nested transaction nếu transaction manager hỗ trợ |

Các propagation này không tự truyền transaction qua thread.

### REQUIRED trên thread mới

Nếu service method có:

~~~java
@Transactional(propagation = Propagation.REQUIRED)
public void process() {
    // ...
}
~~~

Khi được gọi trên thread A đã có transaction, method có thể tham gia transaction A.

Khi được gọi trên thread B không có transaction, REQUIRED tạo một transaction mới trên B. Transaction mới đó độc lập với transaction của test thread.

### REQUIRES_NEW ngay cả trên cùng thread

REQUIRES_NEW cũng có một tình huống đáng chú ý: nó tạo transaction độc lập ngay cả khi cùng thread đã có transaction bên ngoài.

~~~java
@Transactional
public void processOrder() {
    orderRepository.save(order);
    auditService.recordEvent();
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordEvent() {
    auditRepository.save(event);
}
~~~

Nếu recordEvent commit thành công, transaction bên ngoài sau đó rollback vẫn không hoàn tác được bản ghi audit đã commit trong transaction REQUIRES_NEW.

Do đó, test-managed transaction rollback cũng không tự dọn những tác động được commit trong transaction REQUIRES_NEW. Đây là một nguyên nhân khác của dữ liệu còn lại sau test, dù không có thread switch.

Khi test một luồng có REQUIRES_NEW, cần xác định rõ transaction nào có thể commit độc lập và cách dọn dữ liệu đó.

## 9. Cách chọn timeout an toàn cho test có transaction

### Ưu tiên assertTimeout khi cần giữ thread

Nếu test ghi dữ liệu trong test-managed transaction và chỉ cần xác nhận thời gian thực thi không vượt giới hạn, dùng assertTimeout:

~~~java
@Test
@Transactional
void savesCustomerWithinExpectedDuration() {
    assertTimeout(Duration.ofSeconds(2), () -> {
        customerRepository.saveAndFlush(
                new Customer("Linh", "linh@example.com"));
    });
}
~~~

Cách này giữ callback trên test thread. Khi callback hoàn tất, Spring vẫn có thể rollback transaction của test.

Hạn chế là assertion không preemptively dừng callback tại thời điểm timeout.

### Dùng @Timeout với SAME_THREAD khi cần timeout ở cấp test

~~~java
@Test
@Transactional
@Timeout(
        value = 3,
        unit = TimeUnit.SECONDS,
        threadMode = Timeout.ThreadMode.SAME_THREAD)
void updatesCustomerWithinTimeout() {
    customerService.updateCustomer(customerId);
}
~~~

Cách này giữ test method trên thread hiện tại trong quá trình thực thi. Cần nhớ interruption không bảo đảm dừng được mọi hoạt động và các tác vụ do test khởi chạy ở thread khác vẫn có transaction độc lập.

### Tránh assertTimeoutPreemptively quanh thao tác ghi

Nếu callback có thể ghi dữ liệu qua repository, JdbcTemplate hoặc service transactional, không bọc nó bằng assertTimeoutPreemptively trong test dựa vào rollback mặc định.

Nếu thật sự cần timeout preemptive, hãy thiết kế test như một bài kiểm thử có side effect độc lập: dùng dữ liệu định danh riêng, chờ worker kết thúc và thực hiện cleanup có commit riêng.

## 10. Khi bắt buộc phải chạy trên thread khác

Có những bài kiểm thử phải dùng thread khác để xác nhận hành vi bất đồng bộ hoặc timeout preemptive. Khi đó, không nên dựa vào test-managed transaction để dọn tất cả thay đổi.

Có thể áp dụng các nguyên tắc sau:

1. **Dùng dữ liệu riêng cho mỗi test:** tạo một testRunId hoặc mã định danh duy nhất.
2. **Giới hạn phạm vi dữ liệu:** mọi bản ghi được worker tạo đều gắn với testRunId.
3. **Chờ worker kết thúc:** không bắt đầu cleanup trong khi worker vẫn có thể tiếp tục ghi.
4. **Cleanup trong transaction độc lập:** thao tác xóa phải commit thật, không bị rollback cùng test transaction.
5. **Kiểm tra kết quả đã commit:** truy vấn lại từ transaction hoặc persistence context mới.
6. **Dọn cả dữ liệu phụ thuộc:** bản ghi con, event outbox hoặc audit record nếu được tạo trong cùng luồng.

### Ví dụ dùng testRunId

~~~java
@SpringBootTest
class AsyncCustomerImportTest {

    @Autowired
    private CustomerImportService importService;

    @Autowired
    private CustomerRepository customerRepository;

    @Autowired
    private TransactionTemplate cleanupTransaction;

    private final String testRunId = UUID.randomUUID().toString();

    @Test
    void importsCustomerOnWorkerThread() throws Exception {
        CustomerData data = new CustomerData(
                testRunId,
                "Linh",
                "linh@example.com");

        CompletableFuture<Void> future =
                importService.importCustomer(data);

        future.get(5, TimeUnit.SECONDS);

        assertTrue(customerRepository
                .existsByImportRunId(testRunId));
    }

    @AfterEach
    void removeImportedData() {
        cleanupTransaction.executeWithoutResult(status ->
                customerRepository.deleteByImportRunId(testRunId));
    }
}
~~~

Ví dụ này giả định TransactionTemplate được cấu hình với propagation phù hợp để cleanup được commit độc lập nếu test có transaction bên ngoài. Nếu test class không có test-managed transaction, transaction mặc định của TransactionTemplate thường là REQUIRED và có thể tự mở transaction mới.

Nếu test method có @Transactional và cleanup chạy trong khi transaction đó vẫn hoạt động, TransactionTemplate mặc định REQUIRED có thể tham gia transaction của test. Trong trường hợp đó, hãy cấu hình cleanup transaction với REQUIRES_NEW hoặc đặt cleanup ngoài transaction của test.

## 11. Cleanup bằng REQUIRES_NEW khi test thread đang có transaction

Một cách thể hiện rõ ràng là cấu hình TransactionTemplate riêng cho cleanup:

~~~java
@SpringBootTest
@Transactional
class AsyncCustomerImportTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Autowired
    private PlatformTransactionManager transactionManager;

    private String testRunId;

    @BeforeEach
    void createRunId() {
        testRunId = UUID.randomUUID().toString();
    }

    @AfterEach
    void cleanupCommittedWorkerData() {
        TransactionTemplate cleanup = new TransactionTemplate(
                transactionManager);

        cleanup.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);

        cleanup.executeWithoutResult(status ->
                customerRepository.deleteByImportRunId(testRunId));
    }
}
~~~

REQUIRES_NEW tạm suspend transaction test hiện tại, mở transaction cleanup riêng và commit khi cleanup hoàn tất. Sau đó Spring có thể rollback transaction test như bình thường.

Cách này hữu ích khi worker đã commit dữ liệu bên ngoài test transaction. Tuy nhiên, chỉ thực hiện cleanup sau khi worker đã kết thúc hoặc chắc chắn không còn ghi thêm dữ liệu. Nếu worker vẫn chạy, nó có thể tạo lại bản ghi sau khi cleanup hoàn tất.

Nếu transaction manager không hỗ trợ propagation hoặc resource không tham gia cùng transaction manager, cần chọn cách cleanup tương ứng với hạ tầng đang dùng.

## 12. Quản lý executor và worker khi test timeout

Khi test tự tạo ExecutorService hoặc gửi task bất đồng bộ, hãy quản lý vòng đời executor rõ ràng.

Ví dụ:

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();

try {
    Future<?> future = executor.submit(() -> {
        customerRepository.saveAndFlush(customer);
    });

    future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    // Yêu cầu hủy task.
    // Việc hủy phụ thuộc task có phản ứng với interruption hay không.
} finally {
    executor.shutdownNow();
    executor.awaitTermination(2, TimeUnit.SECONDS);
}
~~~

shutdownNow() gửi yêu cầu interrupt đến các task đang chạy; nó không bảo đảm mọi task dừng ngay. Một task đang ở native call, bỏ qua interruption hoặc xử lý cleanup không đúng có thể tiếp tục chạy.

Khi dữ liệu database có thể được ghi từ worker:

- Không coi Future bị cancel là bằng chứng task đã dừng.
- Chờ executor kết thúc trong giới hạn phù hợp.
- Nếu worker không dừng, phải coi dữ liệu test có thể tiếp tục thay đổi.
- Dùng namespace riêng hoặc database/schema riêng để hạn chế ảnh hưởng.
- Chỉ cleanup khi biết worker không còn ghi dữ liệu.

Với code bất đồng bộ do ứng dụng quản lý, tốt hơn nên inject một executor có thể điều khiển trong test và có cơ chế chờ hoàn tất rõ ràng.

## 13. Không dựa vào rollback cho side effect ngoài database

Ngay cả khi transaction của Spring được giữ đúng trên cùng thread, rollback database không thể hoàn tác mọi side effect.

Ví dụ:

- Email đã gửi.
- HTTP request đã gửi sang payment provider.
- Message đã được broker nhận.
- File đã ghi vào filesystem.
- Một tác vụ đã được gửi tới executor.
- Cache ngoài database đã được cập nhật.
- Một transaction REQUIRES_NEW đã commit.

Các side effect này cần chiến lược test riêng:

- Dùng mock/fake cho cổng gửi email hoặc payment trong unit test.
- Dùng broker hoặc server test riêng cho integration test.
- Dùng file tạm và xóa rõ ràng.
- Dùng test namespace để phân biệt message và dữ liệu.
- Dùng outbox hoặc cơ chế compensation nếu ứng dụng cần đảm bảo nhất quán trong production.

Một test có @Transactional không có nghĩa toàn bộ hệ thống được rollback. Annotation đó chỉ quản lý transaction được cấu hình cho resource tham gia transaction manager tương ứng.

## 14. ThreadLocal context khác cũng có thể bị mất

Transaction không phải context duy nhất gắn với thread. Khi chuyển thread, những dữ liệu dựa trên ThreadLocal có thể không xuất hiện ở thread mới:

- TransactionSynchronizationManager: transaction resources và synchronization.
- SecurityContextHolder: security context trong chế độ lưu trữ theo thread.
- RequestContextHolder: request attributes gắn với request thread.
- LocaleContextHolder: locale context gắn với thread.

Một số framework có cơ chế truyền context hoặc wrapper cho executor, nhưng không nên giả định tất cả context được truyền tự động.

Ví dụ, test chạy callback trên thread khác có thể không thấy authentication được thiết lập bằng @WithMockUser nếu security context strategy không truyền sang thread đó. Tương tự, transaction test không tự xuất hiện trong callback thread.

Hãy kiểm tra cơ chế context propagation riêng cho từng loại context. Việc truyền security context không đồng nghĩa transaction context cũng được truyền.

## 15. Trường hợp dùng JUnit 4 timeout

Nếu dự án còn dùng JUnit 4, thuộc tính timeout của @Test có cách thực thi riêng:

~~~java
@Test(timeout = 1000)
public void writesCustomer() {
    customerRepository.save(customer);
}
~~~

JUnit 4 chạy phương thức test trong một thread riêng để thực thi timeout. Vì vậy, test dựa trên transaction được Spring bind vào thread chạy lifecycle có thể gặp vấn đề tương tự: phương thức test không chạy trong thread đang giữ test-managed transaction.

Khi duy trì test cũ, không nên giả định @Test(timeout=...) tương đương với một timeout cùng thread. Hãy kiểm tra phiên bản JUnit và cách tích hợp Spring Test đang dùng.

Với JUnit Jupiter, có thể chọn rõ thread mode của @Timeout hoặc dùng assertTimeout không preemptive khi cần giữ thread.

## 16. Cách chẩn đoán dữ liệu bị sót sau test

Khi một test được đánh dấu @Transactional nhưng dữ liệu vẫn còn, hãy lần lượt xác định transaction boundary thay vì chỉ thêm lệnh xóa tùy tiện.

### Xác định thread thực thi thao tác ghi

Ghi nhận tên thread ở test method và ở callback:

~~~java
System.out.println(
        "test thread = " + Thread.currentThread().getName());

assertTimeoutPreemptively(Duration.ofSeconds(1), () -> {
    System.out.println(
            "callback thread = " + Thread.currentThread().getName());

    customerRepository.save(customer);
});
~~~

Nếu tên thread khác nhau, callback đã đổi thread.

### Kiểm tra transaction hiện tại

Có thể quan sát trạng thái transaction trên từng thread:

~~~java
boolean active =
        TransactionSynchronizationManager
                .isActualTransactionActive();

boolean synchronizationActive =
        TransactionSynchronizationManager
                .isSynchronizationActive();
~~~

Trong test thread có test-managed transaction, trạng thái thường là active. Trong callback thread chạy preemptive timeout, trạng thái có thể là false trước khi repository hoặc service tự mở transaction.

Nếu repository tự mở transaction bên trong callback, kiểm tra trước lời gọi repository sẽ cho thấy thread chưa có transaction. Sau khi phương thức repository kết thúc, transaction riêng đó có thể đã commit.

### Truy vấn lại bằng một transaction mới

Không nên chỉ đọc lại trong cùng persistence context đang giữ entity cũ. Hãy truy vấn từ transaction hoặc EntityManager mới để xác nhận dữ liệu đã được commit ở database.

Ví dụ, dùng một transaction độc lập và truy vấn theo testRunId. Nếu dữ liệu còn tồn tại sau khi transaction của test kết thúc, đó là dấu hiệu có tác động được commit ngoài transaction rollback.

### Tìm các nguồn transaction độc lập

Kiểm tra:

- assertTimeoutPreemptively hoặc JUnit timeout chạy trên thread riêng.
- @Async, executor, CompletableFuture hoặc message listener.
- Service method có @Transactional chạy qua proxy trên worker thread.
- Repository tự mở transaction khi không có transaction hiện tại.
- Propagation REQUIRES_NEW.
- JDBC connection chạy với auto-commit.
- Test có @Commit hoặc @Rollback(false).
- Tác động ngoài database không thuộc transaction manager.

Không phải mọi dữ liệu còn lại đều do timeout. Xác định đúng nguyên nhân trước khi chọn cleanup.

## 17. Các cách viết test theo từng mục tiêu

| Mục tiêu | Cách tiếp cận | Lý do |
|---|---|---|
| Kiểm tra logic service có ghi database trong test transaction | assertTimeout hoặc @Timeout SAME_THREAD | Giữ lời gọi trên test thread |
| Chỉ đo thời gian của một phép tính thuần Java | assertTimeout hoặc benchmark phù hợp | Không có transaction resource cần truyền |
| Kiểm tra service chạy bất đồng bộ | Gọi qua executor, chờ Future và cleanup dữ liệu độc lập | Worker có transaction boundary riêng |
| Kiểm tra timeout preemptive với thao tác ghi | Dữ liệu định danh riêng, chờ worker dừng, cleanup REQUIRES_NEW | Không dựa vào rollback của test thread |
| Kiểm tra transaction REQUIRES_NEW | Integration test với database và xác nhận commit độc lập | Transaction con có thể tồn tại sau rollback ngoài |
| Kiểm tra HTTP request chạy trong server thread | Gửi request qua MockMvc hoặc HTTP client và kiểm tra kết quả thực | Request server có execution/transaction context riêng |
| Kiểm tra side effect ngoài database | Mock/fake hoặc test infrastructure riêng | Database rollback không hoàn tác side effect |

## 18. Những lỗi thường gặp

### Dùng assertTimeoutPreemptively trong test có @Transactional

Callback chạy trên thread khác, không tham gia transaction của test. Repository có thể mở transaction riêng và commit.

**Cách xử lý:** dùng assertTimeout hoặc timeout cùng thread nếu phù hợp; nếu bắt buộc preemptive, tạo dữ liệu riêng và cleanup độc lập.

### Cho rằng @Transactional áp dụng cho mọi thread

Annotation không tự truyền transaction context sang executor hoặc worker thread.

**Cách xử lý:** thiết kế transaction cho worker một cách rõ ràng và kiểm tra dữ liệu sau khi worker hoàn tất.

### Cho rằng Future.get() làm worker tham gia transaction của test

Future.get chỉ chờ kết quả. Nó không chuyển transaction từ thread gọi sang thread thực thi task.

**Cách xử lý:** quản lý transaction của worker và cleanup theo transaction boundary riêng.

### Dùng REQUIRES_NEW rồi kỳ vọng rollback ngoài xóa dữ liệu

REQUIRES_NEW có thể commit độc lập. Rollback transaction bên ngoài không đảo ngược transaction đã commit.

**Cách xử lý:** kiểm tra tác động độc lập và xóa bằng transaction cleanup riêng.

### Cleanup trước khi worker thực sự dừng

Timeout hoặc cancel không đảm bảo worker đã kết thúc. Worker có thể ghi dữ liệu sau khi cleanup chạy.

**Cách xử lý:** chờ termination hoặc dùng tài nguyên test biệt lập và xác nhận không còn worker hoạt động trước cleanup.

### Cleanup tham gia transaction test rồi bị rollback

Nếu @AfterEach dùng TransactionTemplate với REQUIRED trong khi test transaction vẫn đang hoạt động, thao tác xóa có thể tham gia transaction đó. Spring rollback test transaction sẽ rollback luôn cleanup.

**Cách xử lý:** dùng transaction cleanup độc lập với REQUIRES_NEW hoặc thiết kế test không dùng test-managed transaction cho dữ liệu worker.

### Dùng @DirtiesContext để sửa dữ liệu sót

@DirtiesContext loại ApplicationContext khỏi cache; nó không xóa bản ghi đã commit trong database.

**Cách xử lý:** cleanup database hoặc dùng database/schema riêng. Chỉ dùng @DirtiesContext khi cần reset trạng thái context.

### Nghĩ rằng interrupt luôn dừng task

Task có thể bỏ qua interruption hoặc đang ở thao tác không phản ứng với interrupt.

**Cách xử lý:** thiết kế task có khả năng hủy, kiểm soát executor và không cleanup khi worker còn có thể ghi.

## 19. Quy trình chọn timeout và transaction cho một test mới

1. **Xác định test có ghi dữ liệu không:** nếu không có persistence hoặc side effect, rủi ro transaction có thể không liên quan.
2. **Xác định transaction owner:** test method, service proxy, repository, worker thread hay message listener?
3. **Xác định thread thực thi:** callback chạy cùng thread hay được chuyển sang thread khác?
4. **Kiểm tra timeout mode:** assertTimeout, assertTimeoutPreemptively, @Timeout SAME_THREAD/SEPARATE_THREAD hoặc timeout cấu hình toàn cục.
5. **Xác định propagation:** REQUIRED, REQUIRES_NEW hoặc transaction boundary riêng nào được sử dụng?
6. **Chọn timeout phù hợp:** ưu tiên cách giữ thread nếu cần rollback test-managed transaction.
7. **Nếu chạy bất đồng bộ:** dùng test data riêng, chờ worker hoàn tất và có cleanup độc lập.
8. **Xác nhận trạng thái database:** truy vấn sau transaction bằng một persistence context/transaction mới khi cần chứng minh commit hoặc rollback.
9. **Kiểm tra side effect khác:** message, file, HTTP request và cache cần cleanup hoặc test double riêng.

### Mẫu ghi nhận trước khi viết test

~~~text
Test-managed transaction:
[có / không]

Thread thực thi callback:
[test thread / worker thread]

Timeout:
[assertTimeout / assertTimeoutPreemptively / @Timeout mode]

Transaction của thao tác ghi:
[tham gia test transaction / transaction độc lập / auto-commit]

Dữ liệu có thể commit ngoài test transaction:
[loại dữ liệu và định danh test]

Cleanup:
[cách cleanup và transaction sẽ commit]

Điều kiện kết thúc worker:
[cách xác nhận task không còn ghi dữ liệu]
~~~

Mẫu này giúp người viết test không mặc định rằng annotation @Transactional sẽ dọn mọi thay đổi được tạo trong quá trình test.

## 20. Tài liệu tham khảo

- [Spring Framework Reference: TestContext Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Framework Reference: Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework API: TransactionSynchronizationManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)
- [JUnit 5 User Guide: Assertions — Timeout Assertions](https://junit.org/junit5/docs/current/user-guide/#writing-tests-assertions)
- [JUnit 5 User Guide: Timeout](https://junit.org/junit5/docs/current/user-guide/#writing-tests-declarative-timeouts)

## Kết luận

Spring Test gắn test-managed transaction với thread thực thi test. Khi timeout preemptive hoặc tác vụ bất đồng bộ chuyển thao tác ghi sang thread khác, thao tác đó không tự tham gia transaction của test và có thể commit độc lập. Rollback của test thread không thể hoàn tác transaction khác đã commit. Với test cần rollback tự động, ưu tiên timeout giữ nguyên thread; với test thật sự cần worker thread, hãy dùng dữ liệu riêng, quản lý việc dừng worker và cleanup trong transaction độc lập.
