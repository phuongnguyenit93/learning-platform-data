# Điều tra kiểm thử chập chờn thay vì lặp lại để che lỗi

Một test chập chờn (flaky test) là test có lúc thành công, lúc thất bại dù code và đầu vào được cho là không đổi. Ví dụ, cùng một bài kiểm thử Spring MVC có thể xanh khi chạy riêng nhưng đỏ khi chạy toàn bộ suite; test repository có thể lúc tìm thấy bản ghi, lúc không; hoặc test async có thể thất bại ngẫu nhiên trên CI nhưng hiếm khi xảy ra ở máy developer.

Lặp lại test có thể giúp phát hiện hiện tượng này, nhưng nếu chỉ tăng số lần retry để build cuối cùng chuyển xanh thì nguyên nhân vẫn tồn tại. Một lần retry thành công không chứng minh test ổn định. Nó có thể đang che race condition, dữ liệu dùng chung, phụ thuộc thứ tự, timeout quá ngắn hoặc lỗi môi trường.

Mục tiêu điều tra là thu thập bằng chứng đủ để tái hiện lỗi, xác định nguồn không ổn định, sửa nguyên nhân và chứng minh test ổn định sau khi sửa. Retry chỉ nên là biện pháp tạm thời có theo dõi trong CI, không phải cách chữa test.

## 1. Nhận diện flaky test

Một test được xem là chập chờn khi cùng một tình huống kiểm thử có kết quả không nhất quán mà không có thay đổi có chủ đích ở code, dữ liệu hoặc môi trường. Các dấu hiệu thường gặp:

- Test chạy riêng lẻ thì xanh, chạy cùng suite thì đỏ.
- Test thất bại chỉ khi bật parallel execution.
- Test lỗi trên CI nhưng không lỗi trên máy cá nhân.
- Assertion về thời gian, thứ tự phần tử hoặc trạng thái async thất bại không theo quy luật rõ ràng.
- Lần chạy đầu thất bại, lần chạy lại ngay sau đó thành công.
- Một test thất bại kéo theo nhiều test khác do để lại trạng thái hoặc làm hỏng tài nguyên dùng chung.

Không phải mọi test đỏ một lần đều là flaky test. Nếu lỗi luôn tái hiện với cùng đầu vào, đó có thể là bug ổn định trong ứng dụng hoặc assertion sai. Nếu nhiều test cùng thất bại khi database không truy cập được, nguyên nhân có thể là hạ tầng CI. Cần phân loại trước khi kết luận.

### Phân biệt các nhóm lỗi

| Nhóm | Dấu hiệu | Ví dụ |
| --- | --- | --- |
| Bug sản phẩm có thể tái hiện | Cùng điều kiện luôn tạo cùng lỗi | Controller luôn trả 500 cho một request hợp lệ |
| Assertion hoặc dữ liệu test không ổn định | Kết quả phụ thuộc thứ tự, thời gian hoặc dữ liệu ngẫu nhiên | Test giả định phần tử đầu tiên trong collection có thứ tự cố định |
| Race condition | Nhiều thread truy cập trạng thái chung và kết quả phụ thuộc thời điểm | Hai test cùng cập nhật một record hoặc static field |
| Timing/async | Test kiểm tra trước khi tác vụ hoàn tất | Assertion chạy trước khi `CompletableFuture` hoàn thành |
| Phụ thuộc môi trường | Kết quả khác theo máy, timezone, locale hoặc tài nguyên | Test parse ngày theo timezone mặc định của runner |
| Lỗi hạ tầng bên ngoài | Database, broker, container hoặc HTTP service không ổn định | Testcontainers không khởi động được Docker daemon |
| Rò rỉ trạng thái giữa test | Test trước để lại dữ liệu hoặc thay đổi cấu hình | System property, file tạm hoặc mock server chưa được reset |

Phân loại đúng giúp chọn thí nghiệm tiếp theo. Chẳng hạn, nếu chỉ thất bại khi chạy song song, việc retry tuần tự có thể che race condition mà không giải quyết nó.

## 2. Giữ lại bằng chứng ngay khi test thất bại

Trước khi chạy lại, hãy ghi nhận đủ thông tin để lần lỗi có thể được so sánh với lần thành công. Nếu chỉ lưu một dòng `Tests failed` thì rất khó tìm ra nguyên nhân.

Thông tin nên lưu:

- Tên đầy đủ của test class và method.
- Commit SHA, phiên bản JDK, Spring Boot/Spring Framework, JUnit và build tool.
- Hệ điều hành, số CPU khả dụng, bộ nhớ, timezone và locale.
- Test chạy trong JVM worker nào, thread nào và có bật parallel execution hay không.
- Thứ tự test, random seed nếu có, profile và system properties.
- Log đầy đủ trước và sau thời điểm lỗi, stack trace và suppressed exception.
- Trạng thái database, container, mock server và các dịch vụ phụ thuộc khi lỗi xảy ra.
- Số lần chạy, lần nào thất bại, lần nào thành công và test nào chạy ngay trước đó.

Trong Spring integration test, có thể bật log chi tiết có chọn lọc cho Spring TestContext, transaction hoặc HTTP request để xem context nào được tái sử dụng và test đã thực hiện thao tác gì. Không nên bật log debug cho toàn bộ framework trên mọi job nếu log quá lớn; ưu tiên tái hiện trong một job điều tra riêng.

Một mẫu ghi nhận đơn giản:

| Trường | Giá trị cần lưu |
| --- | --- |
| Test | `OrderRepositoryTest.findsReadyOrders` |
| Commit/JDK | SHA của commit và phiên bản JDK |
| Runner | OS, CPU, RAM, timezone |
| Execution | Parallel on/off, worker, thread, thứ tự test |
| Dependency | Database/container và phiên bản |
| Kết quả | Số lần pass/fail, stack trace và log liên quan |
| Tái hiện | Lệnh chạy, profile, seed và cấu hình |

## 3. Tái hiện có kiểm soát

Không bắt đầu bằng cách chạy toàn bộ suite hàng trăm lần. Hãy tăng phạm vi từng bước để biết điều kiện nào làm lỗi xuất hiện.

### Bước 1: chạy đúng test đang lỗi

Với Gradle:

```bash
./gradlew test --tests "com.example.orders.OrderRepositoryTest.findsReadyOrders" --no-daemon
```

Với Maven Surefire:

```bash
./mvnw -Dtest=OrderRepositoryTest#findsReadyOrders test
```

Chạy một test method giúp loại bớt ảnh hưởng từ các test khác. Nếu lỗi luôn xuất hiện, điều tra code, dữ liệu hoặc dependency trực tiếp của test. Nếu không xuất hiện, chuyển sang phạm vi rộng hơn.

### Bước 2: chạy toàn bộ class

Chạy cả test class để kiểm tra phụ thuộc giữa các method trong cùng class. Nếu test chỉ lỗi ở đây, hãy xem:

- Test method trước đó có thay đổi trạng thái dùng chung không?
- `@BeforeEach` và `@AfterEach` có reset đầy đủ dữ liệu không?
- Test có giả định thứ tự method không?
- Test instance có dùng `@TestInstance(PER_CLASS)` và field mutable không?
- Một method có đánh dấu `@DirtiesContext` hoặc đóng tài nguyên mà method khác đang sử dụng không?

### Bước 3: chạy cùng nhóm test liên quan

Nếu class chạy riêng ổn nhưng toàn suite thất bại, thêm các class có chung database, context, file, system property, mock server hoặc container. Mở rộng nhóm theo từng bước để tìm test gây nhiễu.

### Bước 4: so sánh chạy tuần tự và song song

Tạm thời tắt parallel execution trong một lần chạy chẩn đoán hoặc đặt các test nghi vấn về `SAME_THREAD`. Nếu lỗi biến mất khi chạy tuần tự, đó là bằng chứng mạnh về race condition hoặc tranh chấp tài nguyên; chưa phải bằng chứng nguyên nhân đã được sửa.

JUnit Jupiter có thể ghi đè cấu hình parallel trong một lần chạy bằng system property:

```bash
./gradlew test -Djunit.jupiter.execution.parallel.enabled=false
```

Nếu build tool không truyền system property này vào test JVM theo cấu hình hiện tại, hãy truyền qua `systemProperty` của task `Test` hoặc dùng một file `junit-platform.properties` dành cho lần chạy điều tra. Kiểm tra log để chắc chắn test thực sự chạy tuần tự.

### Bước 5: lặp lại có mục đích và ghi kết quả

Lặp lại một test có thể giúp ước lượng tần suất lỗi hoặc xác nhận một thay đổi có tác dụng. Hãy giữ nguyên điều kiện và ghi lại số lần pass/fail. Nếu thay đổi một biến như parallelism, timezone hoặc dữ liệu đầu vào, hãy ghi rõ biến đó để kết quả có thể so sánh.

Không chỉ ghi “chạy lại đã xanh”. Hãy ghi “chạy 30 lần với cùng cấu hình, 0 lần thất bại” hoặc “chạy 20 lần, lỗi xuất hiện 3 lần khi bật parallel, 0 lần khi tắt parallel”. Những con số này vẫn không chứng minh tuyệt đối test không thể chập chờn, nhưng cung cấp bằng chứng tốt hơn.

## 4. Tìm phụ thuộc thứ tự và trạng thái dùng chung

Một test nên thiết lập dữ liệu mà nó cần và dọn trạng thái do nó tạo ra. Test không nên phụ thuộc vào việc một test khác đã chạy trước.

### Static field và singleton mutable bean

Ví dụ dễ gây lỗi:

```java
@Component
public class CurrentTenant {

    private String tenantId;

    public void setTenantId(String tenantId) {
        this.tenantId = tenantId;
    }

    public String getTenantId() {
        return tenantId;
    }
}
```

Bean Spring mặc định là singleton. Nếu nhiều request hoặc test đồng thời gọi `setTenantId`, một test có thể đọc tenant của test khác. Đây là lỗi thiết kế trạng thái dùng chung, không thể sửa bền vững bằng retry.

Nếu tenant là thông tin theo request, hãy truyền nó qua tham số, request-scoped context hoặc cơ chế context an toàn theo luồng phù hợp. Không lưu trạng thái riêng của request trong field mutable của singleton.

### System properties, locale và timezone

Các giá trị như `System.setProperty`, `Locale.setDefault` và `TimeZone.setDefault` có phạm vi toàn JVM. Nếu test thay đổi chúng, cần lưu giá trị cũ và khôi phục trong `finally`, đồng thời khóa truy cập khi test khác cũng dùng cùng tài nguyên.

JUnit cung cấp `@ResourceLock` để điều phối các test khai báo cùng resource key:

```java
@ResourceLock(value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE)
class SystemPropertyTest {

    @Test
    void changesApplicationMode() {
        String previous = System.getProperty("app.mode");
        try {
            System.setProperty("app.mode", "test");
            assertThat(System.getProperty("app.mode")).isEqualTo("test");
        }
        finally {
            if (previous == null) {
                System.clearProperty("app.mode");
            }
            else {
                System.setProperty("app.mode", previous);
            }
        }
    }
}
```

Tất cả test có truy cập xung đột phải khai báo cùng resource key. `@ResourceLock` chỉ điều phối test trong cùng JUnit execution; nó không khóa tài nguyên cho một JVM hoặc build khác.

### Dữ liệu database trùng nhau

Hai test có thể cùng insert một email duy nhất hoặc cập nhật cùng một record. Dù mỗi test có transaction rollback, việc chạy đồng thời vẫn có thể gây vi phạm unique constraint hoặc đọc dữ liệu của nhau trước khi rollback.

Giải pháp thường dùng:

- Tạo dữ liệu riêng cho từng test, dùng ID hoặc key duy nhất.
- Không dựa vào dữ liệu do test khác tạo.
- Dọn dữ liệu đúng phạm vi và bảo đảm thao tác dọn không xóa dữ liệu của test khác.
- Tránh chia sẻ một tài khoản, một record hoặc một hàng đợi nếu test cùng thay đổi nó.
- Nếu test cần một tài nguyên độc quyền, tuần tự hóa bằng lock phù hợp hoặc dùng database/schema riêng.

## 5. Kiểm tra timing và xử lý bất đồng bộ

Test async chập chờn thường xảy ra khi assertion chạy trước khi công việc hoàn tất hoặc timeout được đặt quá ngắn so với môi trường CI.

### Tránh dùng Thread.sleep để đoán thời điểm hoàn tất

Ví dụ không ổn định:

```java
service.startAsyncJob();
Thread.sleep(200);
assertThat(repository.findById(42L)).isPresent();
```

Tác vụ có thể hoàn tất trong 50 ms trên máy developer nhưng cần 500 ms trên CI. Tăng `sleep` lên vài giây chỉ kéo dài test và vẫn không bảo đảm điều kiện đã hoàn tất.

Hãy chờ điều kiện cần thiết với một timeout có giới hạn:

```java
service.startAsyncJob();

await()
        .atMost(Duration.ofSeconds(5))
        .untilAsserted(() ->
                assertThat(repository.findById(42L)).isPresent());
```

Ví dụ dùng Awaitility. Cần khai báo dependency Awaitility trong test scope. `untilAsserted` thử lại assertion cho đến khi thành công hoặc hết timeout; đây là chờ một điều kiện bất đồng bộ có chủ đích, khác với việc retry toàn bộ test để che lỗi. Timeout phải phản ánh giới hạn hợp lý của hệ thống và thông báo thất bại cần giúp xác định điều kiện nào chưa hoàn tất.

### Dùng latch hoặc future khi test điều khiển được tác vụ

Nếu code trả về `CompletableFuture`, chờ future hoàn tất thay vì đoán thời gian:

```java
CompletableFuture<Order> result = service.createOrderAsync(command);

Order order = result.get(5, TimeUnit.SECONDS);

assertThat(order.getStatus()).isEqualTo("CREATED");
```

`get(timeout, unit)` giới hạn thời gian chờ và trả lỗi nếu future không hoàn tất đúng hạn. Nếu dùng callback hoặc listener, `CountDownLatch` có thể giúp test chờ đến khi callback được gọi.

### MockMvc async test cần dispatch kết quả cuối

Với controller trả `Callable`, `DeferredResult` hoặc `CompletableFuture`, lần request đầu có thể chỉ xác nhận async đã bắt đầu. Test cần gọi `asyncDispatch(...)` sau khi kết quả sẵn sàng để kiểm tra response cuối cùng.

```java
MvcResult initial = mockMvc.perform(get("/async-orders/42"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(initial))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42));
```

Nếu tác vụ cần callback từ test, hãy kích hoạt callback trước khi dispatch. Không gọi `asyncDispatch` khi request chưa bắt đầu async hoặc khi kết quả vẫn chưa hoàn tất.

## 6. Kiểm soát thời gian, random và dữ liệu môi trường

Test phụ thuộc vào thời gian hiện tại, random, timezone hoặc locale mặc định thường dễ chạy khác nhau giữa máy và giữa thời điểm.

### Tiêm Clock thay vì gọi trực tiếp thời gian hệ thống

Code production:

```java
@Service
public class ExpirationService {

    private final Clock clock;

    public ExpirationService(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant expiresAt) {
        return !expiresAt.isAfter(Instant.now(clock));
    }
}
```

Test cung cấp clock cố định:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"), ZoneOffset.UTC);

ExpirationService service = new ExpirationService(fixedClock);

assertThat(service.isExpired(Instant.parse("2025-12-31T23:59:59Z")))
        .isTrue();
```

Test không còn phụ thuộc ngày giờ thực tế. Với code cần kiểm tra thời gian trôi, có thể dùng clock test có thể điều khiển.

### Đặt timezone và locale tường minh

Khi parse/format ngày giờ, dùng `Instant`, `OffsetDateTime`, `ZoneId` hoặc `DateTimeFormatter` có cấu hình rõ. Không dựa vào timezone mặc định của máy. Nếu test thực sự cần thay đổi default timezone, bảo vệ thay đổi bằng resource lock và khôi phục trong `finally`.

### Cố định random seed hoặc kiểm soát generator

Nếu test dùng random để tạo dữ liệu, hãy truyền `Random`/generator có seed cố định để có thể tái hiện. Nếu mục tiêu là kiểm tra nhiều trường hợp ngẫu nhiên, ghi seed khi lỗi xảy ra để có thể chạy lại chính xác trường hợp đó.

### Không dựa vào thứ tự không được đảm bảo

Nếu kết quả là `Set`, query không có `ORDER BY`, hoặc API không cam kết thứ tự, đừng assert phần tử đầu tiên. So sánh tập hợp không thứ tự hoặc yêu cầu thứ tự rõ ràng trong truy vấn khi thứ tự là một phần của hợp đồng.

## 7. Điều tra Spring ApplicationContext và @DirtiesContext

Spring TestContext Framework cache `ApplicationContext` để tránh khởi tạo lại cùng một context cho nhiều test. Điều này cải thiện tốc độ, nhưng có thể làm trạng thái mutable hoặc tài nguyên bị rò rỉ giữa các test.

Hãy kiểm tra:

- Test có sửa singleton bean hoặc cấu hình sau khi context đã khởi tạo không?
- Test có đóng datasource, executor, mock server hoặc client dùng chung không?
- Test có dùng `@DirtiesContext` trong khi class khác vẫn dùng context đó không?
- Context có được tạo với profile/property khác nhau giữa local và CI không?
- Một bean giữ cache, counter hoặc collection mutable mà test không reset không?

`@DirtiesContext` đánh dấu context cần được loại khỏi cache và đóng theo phạm vi áp dụng. Nó hữu ích khi test thực sự làm thay đổi context theo cách không thể khôi phục. Không nên thêm annotation này cho mọi test để che trạng thái bị rò rỉ: việc đóng và tạo lại context có thể làm suite chậm hơn, đồng thời không sửa race condition ở tài nguyên bên ngoài.

Nếu test chỉ thay đổi dữ liệu database, hãy dọn dữ liệu đúng cách thay vì làm dirty toàn bộ application context. Nếu một singleton bean có trạng thái thay đổi, cân nhắc thiết kế bean stateless hoặc cung cấp API reset có chủ đích cho test.

## 8. Điều tra transaction và database trong Spring test

Spring test thường chạy test method trong transaction và rollback sau khi test kết thúc. Điều đó tiện cho việc cô lập dữ liệu, nhưng không đảm bảo mọi thao tác của test đều nằm trong transaction đó.

Các tình huống cần chú ý:

- Tác vụ `@Async` chạy trên thread khác không tự tham gia transaction của test.
- `REQUIRES_NEW` tạo transaction riêng và có thể commit dữ liệu dù transaction test bên ngoài rollback.
- Một request đến embedded server xử lý trên server thread khác với thread test; transaction của test không bao bọc transaction server.
- Hai test concurrent cùng ghi dữ liệu có thể tranh chấp khóa hoặc unique key.
- Test dùng cùng sequence, ID cố định hoặc dữ liệu seed chung có thể ảnh hưởng lẫn nhau.

Khi test liên quan async hoặc server thật, cần xác định transaction nào đã commit và ai chịu trách nhiệm cleanup. Không giả định rollback ở cuối test sẽ xóa dữ liệu được ghi bởi thread hoặc transaction độc lập.

Với lỗi database chập chờn, lưu SQL log và thời điểm thao tác, transaction boundary, isolation level, lock wait timeout và trạng thái container. Nếu có thể, tạo dữ liệu test bằng ID duy nhất và tránh phụ thuộc thứ tự insert giữa các test.

## 9. Kiểm tra Testcontainers và dịch vụ ngoài

Testcontainers, WireMock, embedded broker và dịch vụ ngoài giúp integration test gần môi trường thật hơn, nhưng cũng tạo thêm nguồn không ổn định.

Các câu hỏi cần kiểm tra:

- Container có khởi động thành công và readiness check đã hoàn tất chưa?
- Test có dùng cổng cố định dẫn đến xung đột khi chạy song song không?
- Container có bị đóng trong khi test khác còn sử dụng không?
- Database có đủ connection cho mức concurrency hiện tại không?
- Mock server có reset stub và request journal sau mỗi test không?
- Test có phụ thuộc Internet, DNS hoặc một dịch vụ bên ngoài không được kiểm soát không?
- Timeout của client có phù hợp với tải CI không?

Ưu tiên cổng động do thư viện cấp phát, readiness check thay vì `sleep`, container lifecycle rõ ràng và dữ liệu riêng cho từng test. Nếu một dịch vụ ngoài không thể kiểm soát, cân nhắc thay bằng fake/mock server cho unit hoặc slice test, đồng thời giữ một số integration test chuyên biệt để xác nhận tích hợp thật.

## 10. Cách sử dụng retry đúng mục đích

Retry có thể có ích trong hai trường hợp:

1. **Điều tra:** chạy lại có kiểm soát để đo tần suất lỗi, kiểm tra điều kiện tái hiện hoặc xác nhận hiệu quả của một bản sửa.
2. **Giảm tác động tạm thời trong CI:** một test phụ thuộc hạ tầng không ổn định có thể được retry trong thời gian ngắn, với cảnh báo, người phụ trách và hạn xử lý rõ ràng.

Retry không nên được coi là kết quả pass bình thường. Nếu lần đầu fail nhưng lần hai pass, CI cần ghi nhận test đó đã flaky. Nếu chỉ báo build xanh và bỏ qua lần fail đầu, nhóm mất tín hiệu quan trọng về chất lượng.

### Chính sách retry tạm thời

Nếu bắt buộc dùng retry trong CI, nên:

- Giới hạn số lần retry nhỏ.
- Lưu cả log và stack trace của lần thất bại ban đầu.
- Báo cáo riêng test đã pass sau retry.
- Gắn issue, owner và thời hạn loại bỏ retry.
- Không dùng retry cho test có thể gây side effect nguy hiểm khi thực thi nhiều lần.
- Không retry lỗi deterministic như assertion sai ổn định, compilation error hoặc cấu hình thiếu.
- Theo dõi tỷ lệ flaky theo test và theo thời gian.

Plugin retry của Gradle và cấu hình rerun của Maven Surefire có thể giúp tự động thực hiện chính sách này. Cú pháp và cách báo cáo phụ thuộc phiên bản plugin. Hãy kiểm tra tài liệu build tool đang dùng và cấu hình để lần pass sau retry vẫn được ghi nhận là flaky, thay vì âm thầm biến thành pass sạch.

### Quarantine test

Nếu một test gây nhiễu nghiêm trọng cho pipeline, có thể tạm thời tách nó khỏi job blocking trong khi điều tra. Việc quarantine cần có:

- Tên test và lý do cụ thể.
- Issue theo dõi nguyên nhân.
- Người phụ trách và ngày hết hạn.
- Job riêng tiếp tục chạy test để không mất tín hiệu.
- Điều kiện đưa test trở lại pipeline chính.

Quarantine không có nghĩa xóa test hoặc bỏ quên. Một test bị tách khỏi pipeline mà không có owner và deadline thường sẽ bị quên và trở thành lỗ hổng chất lượng lâu dài.

## 11. Ví dụ quy trình điều tra một test Spring bị lỗi ngẫu nhiên

Giả sử `OrderIntegrationTest.createsOrder` thỉnh thoảng không tìm thấy đơn hàng vừa tạo.

**Quan sát ban đầu:**

- Chạy riêng method: 20/20 lần pass.
- Chạy toàn class: 18/20 lần pass.
- Chạy toàn suite song song: 14/20 lần pass.
- Chạy toàn suite tuần tự: 20/20 lần pass.

Những kết quả này gợi ý có tranh chấp hoặc phụ thuộc trạng thái giữa test. Chúng chưa xác định test nào gây lỗi.

**Điều tra tiếp:**

1. Ghi lại test class chạy cùng thời điểm và thread ID.
2. Tìm các test cùng dùng bảng `orders`, cùng email hoặc cùng khóa nghiệp vụ.
3. Kiểm tra dữ liệu seed và cleanup có dùng ID cố định không.
4. Tạm tách các class dùng cùng database để xác định nhóm gây xung đột.
5. Thêm dữ liệu riêng cho từng test hoặc bảo vệ tài nguyên độc quyền.
6. Chạy lại ở cùng mức song song và ghi kết quả.

Ví dụ, hai test cùng dùng `customer@example.test` với unique constraint. Một test cleanup bằng cách xóa customer theo email, trong khi test khác vừa tạo order liên quan. Tùy thời điểm, cleanup có thể xóa dữ liệu test kia hoặc insert có thể gặp conflict. Tạo email riêng cho từng test và cleanup theo ID do chính test sở hữu sẽ loại bỏ nguồn xung đột.

Sau khi sửa, chạy test riêng, cả class, nhóm liên quan và toàn suite với cấu hình parallel CI. Nếu lỗi không còn tái hiện qua nhiều lần chạy, lưu bằng chứng và bỏ retry tạm thời nếu không còn lý do hạ tầng độc lập.

## 12. Checklist điều tra có thể áp dụng

| Câu hỏi | Bằng chứng cần tìm |
| --- | --- |
| Lỗi có tái hiện khi chạy riêng không? | Lệnh chạy chính xác và kết quả nhiều lần |
| Lỗi chỉ xuất hiện khi chạy cả class/suite? | Test chạy trước đó và trạng thái dùng chung |
| Lỗi chỉ xuất hiện khi parallel? | Thread, worker, resource contention và shared state |
| Test phụ thuộc thời gian? | Clock, timezone, timeout, sleep và async completion |
| Test phụ thuộc thứ tự? | Collection/query order, seed data và lifecycle callback |
| Test chia sẻ database? | ID/key, transaction boundary, lock và cleanup |
| Test chia sẻ context? | Context cache, singleton mutable bean, `@DirtiesContext` |
| Test phụ thuộc service ngoài? | Container readiness, port, connection pool, DNS và timeout |
| Lần retry có che lần fail đầu? | Báo cáo flaky riêng, log lần đầu và issue theo dõi |
| Bản sửa đã ổn định chưa? | Chạy lại cùng điều kiện, suite đầy đủ và CI tương đương |

## 13. Kết luận

Test chập chờn là tín hiệu cho thấy test hoặc môi trường thực thi đang phụ thuộc vào một yếu tố không được kiểm soát. Hãy tái hiện theo phạm vi tăng dần, lưu bằng chứng, so sánh chạy riêng/toàn suite và tuần tự/song song, rồi điều tra state dùng chung, async timing, thời gian, dữ liệu, transaction, context cache và dịch vụ ngoài.

Retry có thể hỗ trợ điều tra hoặc giảm tác động tạm thời của một hạ tầng chưa ổn định, nhưng lần pass sau retry vẫn phải được ghi nhận là flaky và có người chịu trách nhiệm xử lý. Một test chỉ đáng tin khi nó ổn định nhờ dữ liệu xác định, đồng bộ đúng, tài nguyên được cô lập và điều kiện môi trường được kiểm soát — không phải vì CI đã thử đủ lần để có một lần xanh.
