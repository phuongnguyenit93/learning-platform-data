# Bài chạy riêng đạt nhưng cả bộ thất bại do trạng thái dùng chung

Một test chạy riêng luôn thành công nhưng thất bại khi chạy cùng toàn bộ suite thường đang phụ thuộc vào trạng thái do test khác tạo ra, thay đổi hoặc dọn dẹp. Trạng thái đó có thể nằm trong JVM, Spring `ApplicationContext`, mock bean, database, file, cache, biến môi trường, thread hoặc một tác vụ bất đồng bộ còn chạy sau khi test kết thúc.

Đây là dạng lỗi phụ thuộc thứ tự thực thi (order-dependent test) hoặc cạnh tranh tài nguyên (race condition). Cách xử lý hiệu quả là tìm đúng trạng thái bị chia sẻ, xác định test nào tạo và test nào tiêu thụ trạng thái đó, rồi cô lập hoặc đồng bộ tài nguyên theo đúng phạm vi.

## 1. Vì sao test riêng pass nhưng suite fail?

Khi chạy một test riêng, nó thường bắt đầu với một JVM hoặc test context có trạng thái tương đối sạch. Khi chạy toàn bộ suite, test đó có thể chạy sau một test đã:

- Thay đổi một field static hoặc singleton bean.
- Ghi dữ liệu vào database nhưng không xóa dữ liệu sau test.
- Stub hoặc reset một mock bean được nhiều test dùng chung.
- Đăng ký expectation vào mock HTTP server rồi để test khác tiêu thụ.
- Thay đổi system property, default locale, timezone hoặc working directory.
- Đưa dữ liệu vào cache, message broker hoặc in-memory store.
- Khởi chạy background task nhưng không chờ task kết thúc.
- Đóng Spring `ApplicationContext` trong khi test khác vẫn đang dùng context đó.

Test lỗi có thể không sai khi xét riêng. Nó chỉ đang dựa vào một giả định ngầm, ví dụ bảng dữ liệu rỗng, mock chưa có stubbing, cache chưa được làm nóng hoặc một singleton vẫn ở giá trị mặc định. Giả định đó không còn đúng khi suite đã chạy các test khác.

Ví dụ về phụ thuộc thứ tự:

```text
Test A                                 Test B
------                                 ------
ghi activeTenant = "tenant-a"
                                       đọc activeTenant
                                       mong đợi giá trị mặc định
                                       nhận "tenant-a" và thất bại
```

Nếu chạy B riêng, `activeTenant` có thể vẫn ở giá trị mặc định nên test pass. Chạy cả suite, A để lại trạng thái khiến B fail.

## 2. Phân biệt lỗi do trạng thái chung và lỗi do chạy song song

Hai nhóm lỗi có biểu hiện gần giống nhau nhưng nguyên nhân khác nhau:

| Dạng lỗi | Cơ chế | Dấu hiệu thường gặp |
|---|---|---|
| Phụ thuộc thứ tự | Test trước để lại trạng thái cho test sau | Chạy tuần tự theo một thứ tự thì fail ổn định; đổi thứ tự có thể đổi test lỗi |
| Race condition | Nhiều test cùng đọc/ghi tài nguyên trong cùng thời điểm | Lỗi chập chờn, thay đổi theo timing hoặc biến mất khi tắt parallel |
| Rò rỉ tài nguyên | Test không đóng file, executor, subscription, server hoặc context | Test cuối suite treo, cạn thread/port/file handle hoặc log xuất hiện sau khi test kết thúc |
| Cấu hình môi trường bị thay đổi | Test sửa system property, locale, timezone hoặc biến global | Test liên quan đến định dạng ngày, encoding hoặc đường dẫn chỉ fail trong suite |

Một suite có thể gặp đồng thời nhiều dạng. Tắt chạy song song là phép thử chẩn đoán hữu ích, nhưng nếu test vẫn fail khi chạy tuần tự thì cần tìm trạng thái còn sót hoặc phụ thuộc thứ tự.

## 3. Những vùng trạng thái thường bị chia sẻ

### 3.1. Static field và singleton mutable

Static field tồn tại trong phạm vi class loader/JVM. Bean Spring mặc định có scope singleton trong một `ApplicationContext`. Nếu test thay đổi trạng thái của các đối tượng này, test khác có thể quan sát được thay đổi.

```java
@Component
class CurrentTenantHolder {

    private String tenantId = "default";

    void setTenantId(String tenantId) {
        this.tenantId = tenantId;
    }

    String getTenantId() {
        return tenantId;
    }
}
```

Giả sử một test gọi `setTenantId("tenant-a")` nhưng không khôi phục giá trị. Test tiếp theo dùng cùng context sẽ đọc được `tenant-a`.

Ưu tiên thiết kế bean không giữ trạng thái theo request hoặc test. Nếu trạng thái là cần thiết, truyền nó qua tham số, lưu trong scope phù hợp hoặc cung cấp API reset rõ ràng. Trong test, khôi phục trạng thái sau mỗi method nếu không thể tạo instance riêng.

### 3.2. Spring ApplicationContext cache

Spring TestContext Framework cache `ApplicationContext` để nhiều test có cấu hình tương đương có thể dùng lại cùng context. Điều này giúp giảm thời gian khởi tạo nhưng cũng có nghĩa singleton bean, cache và mock bean trong context có thể được dùng chung.

JUnit Jupiter mặc định tạo một test instance mới cho mỗi test method (`PER_METHOD`), nhưng điều đó không tạo mới Spring `ApplicationContext`. Vì vậy, field instance của test class có thể mới trong khi các bean được inject vẫn là cùng singleton.

Đừng coi `@BeforeEach` là bằng chứng rằng toàn bộ trạng thái Spring đã được reset. Nó chỉ chạy trước method; các bean trong context vẫn giữ state trừ khi test hoặc framework chủ động reset chúng.

`@DirtiesContext` đánh dấu context không còn dùng lại được và khiến Spring đóng/loại context khỏi cache theo mode được chọn. Đây là biện pháp dành cho test thực sự làm thay đổi context hoặc singleton không thể khôi phục an toàn. Nó tốn chi phí tạo lại context và có thể gây lỗi nếu test khác đang dùng cùng context đồng thời.

### 3.3. Mockito mock dùng chung

Mock được inject bằng `@MockitoBean` hoặc annotation tương ứng của Spring Boot thường nằm trong `ApplicationContext`. Các test dùng cùng context có thể cùng truy cập một mock instance.

Ví dụ hai test cùng stub một phương thức với các kết quả khác nhau:

```java
@SpringBootTest
class InventoryServiceTests {

    @MockitoBean
    InventoryGateway inventoryGateway;

    @Autowired
    InventoryService inventoryService;

    @Test
    void reportsTenItems() {
        when(inventoryGateway.available("SKU-1")).thenReturn(10);
        assertThat(inventoryService.available("SKU-1")).isEqualTo(10);
    }

    @Test
    void reportsTwentyItems() {
        when(inventoryGateway.available("SKU-1")).thenReturn(20);
        assertThat(inventoryService.available("SKU-1")).isEqualTo(20);
    }
}
```

Khi chạy song song, stubbing của test này có thể ghi đè stubbing của test kia. Việc framework reset mock sau test method giúp giảm rò rỉ khi chạy tuần tự, nhưng reset cũng là một thay đổi trên cùng mock instance. Nếu một method reset trong lúc method khác còn dùng mock, hành vi có thể không ổn định.

Giải pháp ưu tiên là tạo mock riêng cho unit test không cần Spring context, hoặc bảo đảm các test dùng cùng mock mutable không chạy đồng thời. Không dùng một mock bean singleton như fixture độc lập cho nhiều test song song.

### 3.4. Database, file và hệ thống bên ngoài

Database không tự động sạch chỉ vì test method kết thúc. Transaction rollback chỉ có tác dụng với các thao tác tham gia đúng transaction của test; dữ liệu ghi qua thread khác, transaction độc lập, async worker hoặc hệ thống ngoài có thể vẫn tồn tại.

Các tình huống dễ gây xung đột:

- Hai test cùng insert một email hoặc business key có unique constraint.
- Một test xóa dữ liệu mà test khác đang đọc.
- Test giả định bảng rỗng nhưng dữ liệu từ test trước vẫn còn.
- Nhiều test dùng chung tên file, thư mục tạm, queue hoặc topic.
- Test dùng chung một tài khoản bên ngoài và thay đổi trạng thái tài khoản đó.

Ưu tiên tạo dữ liệu riêng cho từng test bằng ID hoặc namespace duy nhất. Dùng transaction rollback khi phù hợp; nếu dữ liệu được ghi ngoài transaction, cần cleanup tường minh hoặc tạo tài nguyên riêng theo test.

### 3.5. Mock HTTP server, cache và message broker

`MockRestServiceServer`, mock server HTTP, fake repository, cache in-memory và message broker test có thể giữ expectation hoặc dữ liệu mutable. Nếu nhiều test dùng chung một instance, request hoặc message của test này có thể tiêu thụ expectation của test khác.

Với `MockRestServiceServer`, cách đơn giản là tạo `RestTemplate` và server riêng trong mỗi test. Với broker hoặc cache dùng chung, tạo topic/key/namespace riêng và dọn dữ liệu sau test. Không chia sẻ một expectation manager giữa các test độc lập.

## 4. Các nguyên nhân ít hiển nhiên

Ngoài bean và mock, một số trạng thái toàn cục của JVM cũng có thể làm test phụ thuộc nhau:

| Trạng thái | Ví dụ lỗi | Cách kiểm soát |
|---|---|---|
| System properties | Test đổi `user.timezone` hoặc feature flag | Lưu giá trị cũ và khôi phục trong `finally` |
| Default locale/timezone | Format ngày khác nhau giữa test | Dùng `Locale`/`ZoneId` tường minh; khôi phục default nếu buộc phải đổi |
| System clock | Test phụ thuộc giờ hiện tại | Inject `Clock` và dùng `Clock.fixed(...)` |
| Random/UUID | Assertion phụ thuộc giá trị sinh ngẫu nhiên | Inject generator hoặc kiểm tra định dạng/quan hệ thay vì hard-code |
| ThreadLocal/SecurityContext | Dữ liệu request còn trên thread tái sử dụng | Dùng cơ chế cleanup và xác nhận context được xóa |
| Cache static | Test đọc dữ liệu đã cache từ lần trước | Dùng cache riêng hoặc clear theo key/namespace |
| Port/socket | Hai server test cố bind cùng port | Dùng port ngẫu nhiên và đóng server sau test |
| Working directory/file | Test ghi đè cùng file | Dùng thư mục tạm riêng cho từng test |

Không nên sửa global state trong test nếu có thể truyền dependency hoặc cấu hình riêng cho đối tượng cần kiểm thử. Nếu bắt buộc phải đổi, việc khôi phục cần chạy cả khi assertion hoặc code test ném exception.

## 5. Quy trình chẩn đoán có hệ thống

### Bước 1: Xác nhận test thực sự độc lập khi chạy riêng

Chạy đúng test method hoặc class thất bại. Sau đó chạy lại test đó vài lần để xem nó có tự chập chờn hay chỉ fail khi có test khác chạy trước.

Ví dụ Maven:

```bash
./mvnw -Dtest=InventoryServiceTests#reportsTwentyItems test
```

Ví dụ Gradle:

```bash
./gradlew test --tests "com.example.InventoryServiceTests.reportsTwentyItems"
```

### Bước 2: Chạy cả class và cả suite

Nếu method pass riêng nhưng fail trong class, nghi ngờ trạng thái giữa các method hoặc lifecycle của test class. Nếu class pass riêng nhưng fail trong suite, nghi ngờ context cache, static state hoặc tài nguyên chia sẻ giữa class.

Ghi lại test nào chạy ngay trước test lỗi. Đừng chỉ nhìn stack trace; tìm test đầu tiên đã thay đổi trạng thái liên quan.

### Bước 3: Tắt parallel để phân loại lỗi

Tạm tắt JUnit parallel execution và chạy lại suite. Nếu lỗi biến mất, có khả năng có race condition hoặc tài nguyên dùng chung không an toàn khi truy cập đồng thời. Nếu lỗi vẫn còn nhưng phụ thuộc thứ tự, tập trung vào cleanup và test order.

Với JUnit Platform có thể dùng cấu hình:

```properties
junit.jupiter.execution.parallel.enabled = false
```

Đây là bước khoanh vùng. Nếu suite cần chạy song song, cần xử lý tài nguyên cụ thể thay vì mặc định giữ parallel disabled mãi mãi.

### Bước 4: Thử đảo thứ tự và lặp suite

Chạy test với thứ tự ngẫu nhiên hoặc lặp nhiều lần để tìm cặp test tạo ra lỗi. Nếu lỗi xuất hiện sau một test cụ thể, xem xét các tài nguyên mà test đó thay đổi và test lỗi đọc.

Khi dùng JUnit orderer hoặc random seed, ghi lại seed để có thể tái hiện. Không thêm `@Order` chỉ để ép test lỗi chạy sau một test khác; điều đó thường che giấu phụ thuộc thay vì sửa nó.

### Bước 5: Kiểm tra state trước và sau test

Với từng tài nguyên nghi ngờ, xác định:

1. Ai tạo hoặc thay đổi nó?
2. Ai đọc hoặc phụ thuộc vào nó?
3. Phạm vi sống của nó là method, test instance, class, Spring context, JVM hay hệ thống ngoài?
4. Nó được reset ở đâu và reset có chạy khi test thất bại không?
5. Có hai test cùng truy cập trong một thời điểm không?

Có thể log ID của context, tên thread, khóa dữ liệu hoặc mock invocation để xác định phạm vi chia sẻ. Chỉ thêm log có mục tiêu; tránh biến log thành thay đổi timing lớn làm race condition biến mất.

### Bước 6: Tạo test tái hiện nhỏ nhất

Khi nghi ngờ hai test tương tác, chạy chúng cùng nhau trong một class hoặc một suite nhỏ. Nếu cặp test tái hiện được lỗi, đã thu hẹp được nguồn trạng thái. Sau đó tạo fixture riêng hoặc cleanup và chạy lại cả suite.

## 6. Cách khắc phục theo loại trạng thái

### 6.1. Tạo fixture mới cho từng test

Với unit test, tạo mock và đối tượng cần kiểm thử trong từng method:

```java
@Test
void reportsTenItems() {
    InventoryGateway gateway = mock(InventoryGateway.class);
    when(gateway.available("SKU-1")).thenReturn(10);

    InventoryService service = new InventoryService(gateway);

    assertThat(service.available("SKU-1")).isEqualTo(10);
}
```

Mỗi method sở hữu mock và service riêng. Không có stubbing hoặc invocation history dùng chung với test khác.

### 6.2. Reset state có kiểm soát

Khi phải dùng singleton hoặc static fixture, có thể cung cấp API reset và gọi trong lifecycle hook:

```java
@BeforeEach
void setUp() {
    tenantHolder.reset();
    cache.clear();
}

@AfterEach
void tearDown() {
    tenantHolder.reset();
    cache.clear();
}
```

Cleanup ở `@AfterEach` bảo vệ test tiếp theo; reset ở `@BeforeEach` bảo vệ test hiện tại khỏi trạng thái cũ. Chỉ dùng nếu reset an toàn và test không chạy đồng thời trên cùng tài nguyên. Nếu nhiều test song song cùng thay đổi một singleton, cleanup vẫn có thể xóa state mà test khác đang dùng.

Với system property, khôi phục giá trị cũ thay vì luôn xóa:

```java
String previous = System.getProperty("feature.mode");
try {
    System.setProperty("feature.mode", "test");
    // Thực hiện assertion.
} finally {
    if (previous == null) {
        System.clearProperty("feature.mode");
    } else {
        System.setProperty("feature.mode", previous);
    }
}
```

### 6.3. Dùng dữ liệu database riêng

Có thể tạo ID riêng cho mỗi test, ví dụ dùng UUID hoặc một namespace dựa trên test method. Mọi truy vấn và cleanup chỉ thao tác trên dữ liệu thuộc test đó.

```java
String email = "user-" + UUID.randomUUID() + "@example.test";
User saved = repository.save(new User(email));

assertThat(repository.findByEmail(email)).isPresent();

repository.deleteById(saved.getId());
```

Ví dụ này minh họa dữ liệu riêng theo test; trong dự án thực tế, nên đặt cleanup trong fixture hoặc lifecycle hook để vẫn chạy khi assertion thất bại.

### 6.4. Cô lập file và thư mục tạm

JUnit Jupiter hỗ trợ `@TempDir` để mỗi test nhận một thư mục tạm riêng:

```java
@Test
void writesReport(@TempDir Path tempDir) throws IOException {
    Path report = tempDir.resolve("report.txt");
    Files.writeString(report, "test report");

    assertThat(Files.readString(report)).isEqualTo("test report");
}
```

Không ghi file test vào một đường dẫn cố định trong thư mục làm việc nếu nhiều test có thể chạy cùng lúc.

### 6.5. Inject Clock thay vì phụ thuộc giờ hệ thống

Code dùng `Instant.now()` trực tiếp khiến test phụ thuộc thời điểm chạy. Có thể inject `Clock` để cố định thời gian:

```java
Instant fixedInstant = Instant.parse("2026-01-15T10:00:00Z");
Clock clock = Clock.fixed(fixedInstant, ZoneOffset.UTC);
OrderService service = new OrderService(repository, clock);
```

Test không còn phụ thuộc timezone mặc định hoặc thời điểm thực thi của suite.

## 7. Xử lý riêng với Spring ApplicationContext và @DirtiesContext

Spring context cache là tối ưu hiệu năng, không phải cơ chế cô lập dữ liệu cho từng test. Nếu test chỉ thay đổi dữ liệu nghiệp vụ trong repository, hãy cleanup dữ liệu. Nếu test thay đổi singleton bean, có thể reset bean. Chỉ dùng `@DirtiesContext` khi context thật sự bị thay đổi đến mức không thể tái sử dụng.

Ví dụ đánh dấu context dirty sau class:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextMutationTests {
    // Test thay đổi cấu hình hoặc singleton không thể khôi phục.
}
```

Các mode method/class của `@DirtiesContext` xác định thời điểm context bị đánh dấu dirty và đóng. Dùng sai phạm vi có thể làm suite chậm hoặc ảnh hưởng test khác dùng cùng context.

Khi JUnit chạy song song, class A có thể đóng context trong khi class B vẫn đang dùng context đó. Nếu không thể tránh thao tác này, hãy cô lập class hoặc khóa tài nguyên dùng chung bằng cơ chế JUnit phù hợp. `@DirtiesContext` không tự động chờ mọi test khác kết thúc trước khi đóng context.

## 8. Kiểm soát chạy song song khi tài nguyên không thể cô lập

Ưu tiên cô lập tài nguyên trước. Nếu một nhóm test buộc phải dùng chung state mutable, JUnit Jupiter có các cơ chế tuần tự hóa:

### @Execution(SAME_THREAD)

Yêu cầu các node trong execution tree của class chạy trên cùng thread:

```java
@SpringBootTest
@Execution(ExecutionMode.SAME_THREAD)
class SharedSingletonTests {
    // Các method trong class không chạy đồng thời với nhau.
}
```

Annotation này không tự khóa các class khác cùng dùng singleton. Chỉ dùng nó khi phạm vi chia sẻ nằm trong class đó.

### @ResourceLock

Khai báo một tên tài nguyên chung cho mọi test có thể truy cập state đó:

```java
@ResourceLock(value = "shared-inventory-cache",
        mode = ResourceAccessMode.READ_WRITE)
class InventoryCacheTests {
    // Mọi test khác dùng cache này cũng phải khai báo cùng lock name.
}
```

Các test cùng khai báo resource name sẽ được JUnit điều phối để tránh xung đột theo access mode. Nếu một test không khai báo lock, JUnit không tự biết nó cũng truy cập tài nguyên đó. Lock chỉ điều phối trong cùng JUnit execution, không đồng bộ giữa JVM hoặc build fork độc lập.

### @Isolated

Khi một class cần chạy độc quyền so với các test Jupiter khác, có thể dùng `@Isolated`:

```java
@SpringBootTest
@Isolated
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class GlobalContextMutationTests {
    // Class này chạy riêng trong JUnit execution.
}
```

`@Isolated` hữu ích cho test thay đổi tài nguyên toàn cục hoặc đóng context mà không thể mô tả bằng một lock nhỏ. Đây là biện pháp phạm vi rộng; nên giới hạn vào class thật sự cần thiết.

### Tắt parallel execution

Nếu suite chưa được thiết kế an toàn cho chạy đồng thời, tạm tắt parallel trong `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled = false
```

Đây là biện pháp ổn định suite trong ngắn hạn và giúp xác nhận race condition. Khi có thể, hãy quay lại cô lập state hoặc khóa nhóm test cụ thể để không làm chậm toàn bộ suite.

## 9. Chờ và dọn dẹp công việc bất đồng bộ

Test method có thể kết thúc trước khi task do nó khởi chạy hoàn tất. Background task vẫn có thể ghi database, thay đổi mock hoặc gọi bean trong Spring context sau khi test tiếp theo đã bắt đầu.

Với `CompletableFuture`, chờ kết quả trong giới hạn thời gian:

```java
CompletableFuture<Result> future = service.startAsyncWork();
Result result = future.get(5, TimeUnit.SECONDS);

assertThat(result.status()).isEqualTo("DONE");
```

Với Reactor, xác nhận publisher hoàn tất hoặc hủy subscription:

```java
StepVerifier.create(service.process())
        .expectNextMatches(Result::isSuccessful)
        .verifyComplete();
```

Nếu test tạo executor riêng, hãy shutdown nó trong `@AfterEach` hoặc `try/finally`, rồi chờ task kết thúc. Không để thread nền giữ tham chiếu tới mock hoặc context của test sau khi method đã kết thúc.

## 10. Tránh sửa test để phụ thuộc thứ tự

Khi phát hiện A phải chạy trước B mới pass, không nên mặc định thêm `@Order` để giữ thứ tự đó. Thứ tự chỉ che giấu state leakage và có thể bị thay đổi bởi cấu hình suite, engine hoặc build tool.

Test độc lập nên có thể chạy theo bất kỳ thứ tự nào. Nếu test cần dữ liệu do một bước trước tạo ra, hãy gộp các bước thành một test workflow có ý nghĩa hoặc tạo fixture dữ liệu ngay trong test đó.

`@TestMethodOrder` phù hợp khi thứ tự là một phần có chủ đích của kịch bản (ví dụ kiểm thử một state machine qua các bước không thể tách rời), nhưng không nên dùng để chữa một test suite có trạng thái dùng chung không được cleanup.

## 11. Checklist điều tra nhanh

Khi test chỉ fail trong suite, lần lượt xác định:

1. Test fail khi chạy riêng, trong class hay chỉ khi chạy toàn suite?
2. Tắt parallel có làm lỗi biến mất không?
3. Test chạy ngay trước đó đã ghi hoặc thay đổi tài nguyên nào?
4. Hai test có dùng cùng `ApplicationContext`, singleton bean hoặc mock bean không?
5. Database, file, cache, queue hoặc mock server có dữ liệu/expectation tồn đọng không?
6. Test có sửa system property, locale, timezone, static field hoặc ThreadLocal không?
7. Background task hoặc reactive subscription có còn hoạt động sau khi method kết thúc không?
8. Cleanup có chạy trong mọi trường hợp, kể cả khi assertion thất bại không?
9. Có thể tạo fixture riêng hoặc namespace dữ liệu riêng cho mỗi test không?
10. Nếu không thể cô lập, mọi test liên quan đã dùng cùng `@ResourceLock` hoặc cơ chế tuần tự hóa chưa?

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Test pass riêng nhưng fail sau test khác | Test trước để lại state trong static field, singleton hoặc cache | Tìm writer và reader của state; reset hoặc tạo fixture riêng |
| Mock trả kết quả khác khi chạy suite | Nhiều test cùng stub/reset một mock bean trong context cache | Tạo mock riêng hoặc tuần tự hóa tất cả test dùng mock đó |
| Test fail chập chờn chỉ khi bật parallel | Nhiều thread cùng ghi tài nguyên mutable | Cô lập tài nguyên hoặc dùng `@ResourceLock` đúng phạm vi |
| Test database báo duplicate key | Dữ liệu từ test khác còn tồn tại hoặc test dùng business key cố định | Tạo dữ liệu duy nhất và cleanup rõ ràng |
| Test file đọc nhầm dữ liệu | Nhiều test ghi cùng đường dẫn | Dùng `@TempDir` hoặc file riêng theo test |
| Test sau nhận timezone/locale khác | Test trước sửa global default và không khôi phục | Dùng cấu hình tường minh hoặc khôi phục trong `finally` |
| Context bị đóng giữa request | Test khác dùng `@DirtiesContext` trong lúc context còn được chia sẻ | Tránh dirty context không cần thiết; cô lập/khóa class liên quan |
| Log hoặc database thay đổi sau khi test đã xong | Background task chưa hoàn tất | Chờ future, verify/cancel publisher và shutdown executor |
| Thêm `@Order` thì suite pass nhưng đổi thứ tự lại fail | Test phụ thuộc thứ tự thay vì độc lập | Sửa fixture và cleanup; không dựa vào thứ tự toàn suite |

## 13. Nguyên tắc thiết kế suite ổn định

- Mỗi test tự tạo dữ liệu đầu vào và không dựa vào dữ liệu của test khác.
- Hạn chế mutable static field và mutable singleton bean trong test context.
- Tạo mock, mock server và fixture riêng khi có thể.
- Cleanup database, file, cache, message và system property ở đúng phạm vi.
- Dùng `Clock`, ID generator và dependency injection để kiểm soát giá trị thay đổi theo thời gian hoặc môi trường.
- Chờ hoặc hủy mọi tác vụ bất đồng bộ trước khi test method kết thúc.
- Chỉ dùng `@DirtiesContext` khi context thực sự không thể tái sử dụng.
- Nếu cần chạy song song trên state chung, khóa đúng tài nguyên và bảo đảm mọi test tham gia đều khai báo lock.
- Không dùng `@Order` để che giấu phụ thuộc giữa các test độc lập.

## 14. Ghi nhớ

Test pass riêng nhưng fail trong suite thường là dấu hiệu trạng thái bị chia sẻ hoặc cleanup chưa đầy đủ. Hãy xác định trạng thái nằm ở đâu, test nào ghi và test nào đọc, rồi phân loại đó là phụ thuộc thứ tự, race condition hay rò rỉ tài nguyên. Ưu tiên fixture và dữ liệu riêng cho từng test; reset global state an toàn; chờ công việc bất đồng bộ; chỉ dùng `@DirtiesContext` khi cần. Khi tài nguyên không thể cô lập, dùng `@ResourceLock`, `@Execution(SAME_THREAD)`, `@Isolated` hoặc tắt parallel trong phạm vi phù hợp. Một suite ổn định phải cho kết quả như nhau khi test chạy riêng, theo thứ tự khác nhau hoặc cùng các test độc lập khác.

