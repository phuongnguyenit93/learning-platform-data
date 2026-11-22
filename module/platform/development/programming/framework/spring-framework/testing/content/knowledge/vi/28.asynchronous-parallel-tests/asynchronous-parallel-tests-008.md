# Tránh chạy song song khi dùng @DirtiesContext hoặc mock dùng chung không an toàn

JUnit Jupiter có thể chạy nhiều test method hoặc test class đồng thời. Chạy song song giúp giảm thời gian suite, nhưng một số Spring integration test dùng chung tài nguyên có trạng thái: `ApplicationContext` được cache, singleton bean, mock bean, mock HTTP server hoặc tác vụ bất đồng bộ. Nếu một test thay đổi hoặc đóng tài nguyên trong khi test khác vẫn đang sử dụng, kết quả có thể phụ thuộc vào thời điểm chạy.

Đặc biệt cần thận trọng với `@DirtiesContext` và các mock được đăng ký trong Spring `ApplicationContext`. Cả hai đều có thể ảnh hưởng đến test khác đang dùng cùng context. Bài này giải thích nguồn gốc của race condition và cách giới hạn song song bằng JUnit Jupiter.

## 1. Vì sao test Spring có thể chia sẻ trạng thái?

Spring TestContext Framework cache `ApplicationContext` để tránh khởi tạo lại context cho từng test class. Các test có cùng cấu hình context có thể nhận cùng một context instance. Vì bean mặc định là singleton, những test đó cũng có thể cùng truy cập một bean instance.

Ví dụ hai test class dùng chung cấu hình:

```java
@SpringBootTest
class OrderControllerTests {
    // Dùng ApplicationContext có cấu hình này.
}

@SpringBootTest
class InventoryControllerTests {
    // Nếu cấu hình context tương đương, có thể dùng lại cùng context đã cache.
}
```

Việc dùng chung context thường an toàn khi test chỉ đọc cấu hình và mỗi request có dữ liệu riêng. Rủi ro xuất hiện khi test thay đổi singleton bean, reset mock, sửa cấu hình mutable hoặc đóng context trong lúc test khác còn hoạt động.

JUnit Jupiter mặc định không chạy song song nếu chưa bật cấu hình parallel execution. Tuy nhiên, dự án có thể bật chế độ này trong `junit-platform.properties`, Maven/Gradle hoặc cấu hình test runtime. Hãy xác định rõ test suite có thực sự chạy song song trước khi chẩn đoán race condition.

## 2. @DirtiesContext làm gì?

`@DirtiesContext` đánh dấu một `ApplicationContext` là không còn phù hợp để tái sử dụng. Spring TestContext sẽ đóng context và loại nó khỏi context cache ở thời điểm được chỉ định. Lần test tiếp theo cần context có cùng cấu hình sẽ phải tạo context mới.

Có thể dùng annotation ở cấp method:

```java
@Test
@DirtiesContext
void changesSingletonConfiguration() {
    // Thay đổi trạng thái context mà test khác không nên kế thừa.
}
```

Hoặc ở cấp class:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextMutationTests {
    // Sau khi toàn bộ test trong class chạy xong, context bị đóng và loại khỏi cache.
}
```

Các mode phụ thuộc vào vị trí đặt annotation:

| Thuộc tính | Mode | Thời điểm đánh dấu context dirty |
|---|---|---|
| `methodMode` (annotation trên method) | `BEFORE_METHOD` | Trước test method đó |
| `methodMode` (annotation trên method) | `AFTER_METHOD` | Sau test method đó; đây là mặc định ở cấp method |
| `classMode` (annotation trên class) | `BEFORE_CLASS` | Trước các test method trong class |
| `classMode` (annotation trên class) | `AFTER_CLASS` | Sau khi các test method trong class hoàn tất; đây là mặc định ở cấp class |
| `classMode` (annotation trên class) | `BEFORE_EACH_TEST_METHOD` | Trước từng test method trong class |
| `classMode` (annotation trên class) | `AFTER_EACH_TEST_METHOD` | Sau từng test method trong class |

Chọn mode theo thời điểm trạng thái context bị thay đổi và khi nào cần loại bỏ context. Việc đánh dấu dirty ở trước method/class có thể làm Spring tạo context mới cho lần chạy tương ứng; mode sau method/class đóng context hiện tại sau khi phần test được chỉ định hoàn tất.

### Race condition khi context bị đóng

Giả sử hai test class cùng dùng một context đã cache:

```text
Test A                              Test B
------                              ------
đang dùng ApplicationContext       đang dùng cùng context
@DirtiesContext chạy sau test A
Spring đóng context
                                    tiếp tục gọi bean
                                    bean/context đã bị đóng
                                    test có thể thất bại
```

Khi test A hoàn tất và đánh dấu context dirty, Spring có thể đóng context mà test B vẫn đang sử dụng. Test B có thể gặp lỗi do bean đã bị hủy, connection pool đã đóng hoặc context không còn active. Đây là lý do `@DirtiesContext` cần được xem là thao tác ảnh hưởng tới các test dùng chung context.

`@DirtiesContext` không phải cách reset thông thường cho mọi test. Mỗi lần đóng context có thể khiến suite phải khởi tạo lại nhiều bean và hạ tầng, làm test chậm hơn. Chỉ dùng khi test thực sự làm thay đổi trạng thái cấu hình hoặc singleton không thể khôi phục an toàn bằng cách khác.

## 3. Vì sao mock dùng chung có thể gây race condition?

Mock thường có trạng thái: stubbing, invocation history, verification và reset. Nếu nhiều test dùng cùng một mock instance, các thao tác đó có thể xen kẽ.

Ví dụ Spring context chứa một mock bean:

```java
@SpringBootTest
class OrderServiceTests {

    @MockitoBean
    private InventoryGateway inventoryGateway;

    @Autowired
    private OrderService orderService;

    @Test
    void returnsAvailableInventory() {
        when(inventoryGateway.available("SKU-1")).thenReturn(10);
        assertThat(orderService.available("SKU-1")).isEqualTo(10);
    }
}
```

`@MockitoBean` đăng ký mock trong `ApplicationContext`. Nếu hai test class dùng chung context và cùng mock bean, chúng có thể cùng truy cập một mock instance. Giả sử test A cấu hình kết quả cho `SKU-1`, còn test B cấu hình một kết quả khác hoặc reset mock trong lúc test A đang chạy. Kết quả phụ thuộc vào thứ tự xen kẽ của các thao tác.

Với `@MockitoBean`, mock mặc định được reset sau mỗi test method. Việc reset giúp các test tuần tự không kế thừa invocation hoặc stubbing của nhau, nhưng nếu test method chạy đồng thời trên cùng mock, một test có thể reset trạng thái mà test kia đang cần.

Các annotation mock trong Spring Boot như `@MockBean` cũng có cùng vấn đề khi mock được đặt trong context dùng chung. Trong Spring Framework 6.2 có thể dùng `@MockitoBean`; các dự án Spring Boot cũ hơn có thể đang dùng `@MockBean`.

### Những tài nguyên mock cần chú ý

| Tài nguyên | Trạng thái dùng chung có thể xung đột |
|---|---|
| `@MockitoBean` / `@MockBean` | Test thay stubbing, verify hoặc reset trên cùng mock |
| `MockRestServiceServer` | Các request đồng thời cạnh tranh expectation và response đã khai báo |
| Fake repository hoặc in-memory store | Test ghi/xóa dữ liệu trong cùng collection |
| Mutable singleton bean | Test thay đổi field hoặc cấu hình dùng chung |
| Static test fixture | Test thay đổi biến static hoặc cache toàn cục |

Không phải mọi mock đều không an toàn khi có nhiều thread gọi vào. Rủi ro chính là nhiều test cùng thay đổi cấu hình và trạng thái quan sát của cùng một mock hoặc fixture mà không có cơ chế đồng bộ. Hãy phân biệt việc ứng dụng gọi mock đồng thời theo hành vi cần kiểm thử với việc nhiều test cùng sửa stubbing/reset của mock.

## 4. Ví dụ hai test cùng thay đổi một mock bean

Giả sử hai test cùng dùng một context và cùng mock `InventoryGateway`:

```java
@SpringBootTest
class InventoryTests {

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

Khi chạy tuần tự, mỗi test có thể thiết lập stubbing rồi hoàn tất trước khi test tiếp theo bắt đầu. Khi chạy đồng thời trên cùng mock, trình tự có thể thành:

```text
Test A: stub SKU-1 -> 10
Test B: stub SKU-1 -> 20
Test A: gọi service -> có thể nhận 20
Test B: gọi service -> nhận kết quả hiện tại
```

Ngay cả khi từng lời gọi Mockito riêng lẻ được xử lý an toàn ở mức thread, hai test vẫn đang tranh chấp cùng một trạng thái logic. Việc reset mock sau một method còn có thể xóa stubbing hoặc invocation history mà method kia đang sử dụng.

## 5. Cách an toàn nhất: cô lập trạng thái theo test

Ưu tiên để mỗi test sở hữu dữ liệu và mock riêng. Với unit test không cần Spring context, có thể tạo service và mock trong từng method:

```java
@Test
void returnsTenItems() {
    InventoryGateway gateway = mock(InventoryGateway.class);
    when(gateway.available("SKU-1")).thenReturn(10);

    InventoryService service = new InventoryService(gateway);

    assertThat(service.available("SKU-1")).isEqualTo(10);
}
```

Mỗi test có một mock mới nên stubbing, verification và reset không thể tác động tới test khác. Nếu cần kiểm thử wiring của Spring, dùng context test nhưng tránh thay đổi mock singleton từ nhiều test chạy song song.

Với `MockRestServiceServer`, tạo một `RestTemplate` và mock server riêng cho từng test thay vì dùng chung expectation manager giữa các test:

```java
@Test
void readsOrder() {
    RestTemplate restTemplate = new RestTemplate();
    MockRestServiceServer server = MockRestServiceServer
            .bindTo(restTemplate)
            .build();

    InventoryClient client = new InventoryClient(restTemplate);
    server.expect(requestTo("https://inventory.example.test/orders/42"))
            .andRespond(withSuccess(
                    "{\"id\":\"42\"}", MediaType.APPLICATION_JSON));

    assertThat(client.findOrder("42").id()).isEqualTo("42");
    server.verify();
}
```

Ở đây mỗi test tự tạo request factory và expectation manager. Test khác không thể tiêu thụ expectation của test này.

## 6. Giới hạn song song bằng JUnit Jupiter

JUnit Jupiter cung cấp một số cơ chế để điều khiển việc thực thi đồng thời. Chọn cơ chế theo phạm vi tài nguyên cần bảo vệ.

### 6.1. Tắt parallel execution trên toàn bộ suite

Nếu suite có nhiều test dùng chung context hoặc mock và chưa thể cô lập chúng, có thể tắt chạy song song trong file `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled = false
```

Đây là lựa chọn đơn giản và dễ dự đoán cho suite có nhiều test integration phụ thuộc trạng thái dùng chung. Đổi lại, thời gian chạy suite có thể dài hơn. Chỉ bật parallel lại khi các test đã được thiết kế để độc lập hoặc đã có cơ chế khóa phù hợp.

### 6.2. Chạy các test trong cùng class tuần tự

Dùng `@Execution(ExecutionMode.SAME_THREAD)` để yêu cầu các test node trong class chạy trên cùng thread theo thứ tự của execution tree:

```java
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

@SpringBootTest
@Execution(ExecutionMode.SAME_THREAD)
class SharedMockTests {
    // Các test trong class này không chạy đồng thời với nhau.
}
```

Lưu ý: `SAME_THREAD` trên một class không tự khóa các test thuộc class khác. Nếu class khác cũng dùng cùng mock bean hoặc context, hai class vẫn có thể chạy đồng thời theo cấu hình class-level. Khi tài nguyên được chia sẻ giữa nhiều class, hãy dùng cùng một `@ResourceLock` hoặc cơ chế cô lập ở phạm vi rộng hơn.

### 6.3. Dùng @ResourceLock cho tài nguyên cụ thể

`@ResourceLock` cho phép các test khai báo một tài nguyên logic có tên. Những test dùng cùng tên lock sẽ không thực thi đồng thời trong phạm vi một JUnit Jupiter execution:

```java
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;

@SpringBootTest
@ResourceLock(value = "shared-inventory-mock",
        mode = ResourceAccessMode.READ_WRITE)
class InventoryMockTests {

    @MockitoBean
    InventoryGateway inventoryGateway;

    // Các test truy cập mock dùng chung nằm ở đây.
}
```

Mọi test method hoặc class khác cùng truy cập mock đó cũng phải khai báo đúng resource name và mode tương thích. Nếu một test quên khai báo lock, JUnit không thể tự biết test đó đang dùng cùng tài nguyên.

Dùng `READ_WRITE` khi test có thể thay đổi stubbing, reset hoặc invocation state. `READ` chỉ phù hợp khi tất cả test liên quan thực sự chỉ đọc một tài nguyên ổn định và không có test nào ghi trong cùng khoảng thời gian.

`@ResourceLock` phù hợp khi chỉ một nhóm test cần tuần tự hóa, còn phần còn lại của suite vẫn có thể chạy song song. Lock của JUnit không phối hợp giữa các JVM process hoặc các build fork độc lập.

### 6.4. Dùng @Isolated cho test class cần độc quyền

Khi một class thực hiện thao tác ảnh hưởng rộng tới context hoặc tài nguyên khó liệt kê, `@Isolated` yêu cầu class đó chạy độc lập với các test khác trong cùng JUnit Jupiter execution:

```java
import org.junit.jupiter.api.parallel.Isolated;

@SpringBootTest
@Isolated
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class LegacyContextMutationTests {
    // Test thay đổi cấu hình singleton và cần đóng context sau class.
}
```

`@Isolated` hữu ích cho test class dùng `@DirtiesContext` khi cần bảo đảm không có test Jupiter khác chạy đồng thời với class đó. Nó làm giảm mức song song trong khoảng thời gian class chạy. Annotation này có từ JUnit Jupiter 5.7; hãy kiểm tra version JUnit của dự án trước khi dùng.

## 7. Chọn chiến lược theo phạm vi chia sẻ

| Tình huống | Cách xử lý phù hợp |
|---|---|
| Hai method trong cùng class thay đổi cùng mock | Tạo mock riêng hoặc dùng `@Execution(SAME_THREAD)` |
| Nhiều class dùng chung một mock bean trong context cache | Dùng `@ResourceLock` cùng tên ở tất cả class liên quan hoặc cô lập context |
| Class dùng `@DirtiesContext` có thể đóng context mà class khác đang dùng | Dùng `@Isolated` hoặc khóa chung cho toàn bộ test dùng context đó |
| Nhiều test dùng chung `MockRestServiceServer` | Tạo server/RestTemplate riêng hoặc khóa chung expectation manager |
| Nhiều test có thể làm việc độc lập | Cho phép chạy song song |
| Chưa xác định được tài nguyên chia sẻ và suite thường xuyên flaky | Tạm tắt parallel execution để ổn định, sau đó cô lập từng nhóm |

Không nên thêm `@DirtiesContext` chỉ để chữa một test flaky do mock bị ghi đè. Điều đó có thể làm context bị đóng trong khi test khác đang chạy và khiến vấn đề nghiêm trọng hơn. Hãy xác định tài nguyên thực sự được chia sẻ trước khi chọn cách khóa hoặc cô lập.

## 8. Bất đồng bộ cũng cần được kết thúc trước khi test hoàn tất

Một test có thể kết thúc method trong khi công việc bất đồng bộ mà nó khởi chạy vẫn còn chạy. Ví dụ `@Async`, executor, scheduler hoặc reactive subscription có thể tiếp tục truy cập bean sau khi test đã hoàn tất. Nếu test tiếp theo reset mock hoặc `@DirtiesContext` đóng context, tác vụ cũ có thể dùng trạng thái mới hoặc bean đã bị hủy.

Với `CompletableFuture`, hãy chờ kết quả trong test:

```java
CompletableFuture<Result> future = service.startAsyncWork();
Result result = future.get(5, TimeUnit.SECONDS);

assertThat(result.status()).isEqualTo("DONE");
```

Với Reactor, dùng `StepVerifier` để xác nhận publisher hoàn tất hoặc chủ động cancel stream:

```java
StepVerifier.create(service.process())
        .expectNextMatches(result -> result.isSuccessful())
        .verifyComplete();
```

Không để background task giữ tham chiếu tới singleton bean hoặc mock của test sau khi method kết thúc. Nếu test tạo executor riêng, hãy shutdown nó trong `@AfterEach` hoặc `try/finally` và chờ các task kết thúc trong giới hạn thời gian.

## 9. @DirtiesContext không thay thế việc dọn dẹp dữ liệu

`@DirtiesContext` đóng và loại context khỏi cache; nó không phải cơ chế rollback cho mọi dữ liệu bên ngoài context. Database, file, message broker, static state hoặc server dùng chung có thể vẫn giữ dữ liệu sau khi context bị đóng.

Với các tài nguyên đó, cần dọn dẹp theo đúng phạm vi:

- Dùng transaction rollback cho dữ liệu database khi test chạy trong transaction phù hợp.
- Xóa record hoặc namespace riêng của test khi thao tác không nằm trong transaction được rollback.
- Tạo topic, queue, bucket hoặc thư mục riêng theo test nếu có thể.
- Đóng client, executor và subscription do test tạo ra.
- Không dùng một static mutable fixture chung cho các test chạy song song nếu không có đồng bộ.

Context mới không đồng nghĩa với hệ thống bên ngoài đã trở về trạng thái ban đầu.

## 10. Ví dụ cấu hình parallel có kiểm soát

Có thể bật parallel cho suite và chỉ khóa nhóm test dùng chung tài nguyên. Ví dụ file `junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
junit.jupiter.execution.parallel.mode.classes.default = concurrent
junit.jupiter.execution.parallel.config.strategy = dynamic
```

Các class test dùng mock bean chung cùng khai báo lock:

```java
@SpringBootTest
@ResourceLock(value = "shared-payment-gateway",
        mode = ResourceAccessMode.READ_WRITE)
class PaymentGatewayIntegrationTests {
    // Cùng resource lock với mọi class khác truy cập mock này.
}
```

Class làm thay đổi context và cần đóng context sau cùng:

```java
@SpringBootTest
@Isolated
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class PaymentConfigurationMutationTests {
    // Không chạy đồng thời với test Jupiter khác.
}
```

Không cần khóa các test không chia sẻ tài nguyên. Mục tiêu là giữ song song ở những nơi độc lập và tuần tự hóa đúng vùng có trạng thái chung.

## 11. Dấu hiệu nhận biết race condition

Các dấu hiệu thường gặp:

- Test chạy riêng thì luôn pass nhưng chạy cả suite thì thỉnh thoảng fail.
- Giá trị mock trả về không đúng với stubbing trong test hiện tại.
- Invocation count thay đổi giữa các lần chạy.
- Test báo context đã đóng hoặc bean đã bị destroy trong khi request còn đang xử lý.
- Một expectation của `MockRestServiceServer` bị test khác tiêu thụ trước.
- Lỗi biến mất khi tắt parallel execution hoặc chạy lại riêng test thất bại.

Để điều tra, ghi nhận tên test class/method, thời điểm test bắt đầu/kết thúc, context identity nếu cần, và tài nguyên mock được dùng chung. Chạy lại với parallel disabled giúp xác định lỗi có liên quan đến cạnh tranh hay không, nhưng không phải là cách sửa cuối cùng nếu suite vẫn cần chạy song song.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Test khác lỗi sau khi một test dùng `@DirtiesContext` | Context cache entry đã bị đóng trong lúc test khác còn dùng | Tuần tự hóa test liên quan bằng `@Isolated` hoặc `@ResourceLock` chung |
| Mock trả sai dữ liệu ngẫu nhiên | Nhiều test cùng stub một mock bean singleton | Tạo mock riêng hoặc khóa tất cả test dùng mock đó |
| Stubbing biến mất giữa test | Mock bị reset sau một test method đang chạy song song | Tránh dùng chung mock mutable; tuần tự hóa các test liên quan |
| `MockRestServiceServer` báo request không khớp | Request từ test khác dùng cùng expectation manager | Tạo server riêng theo test hoặc dùng resource lock |
| `@Execution(SAME_THREAD)` vẫn không ngăn race giữa class | Annotation chỉ kiểm soát execution tree của class đó | Dùng lock chung hoặc `@Isolated` khi cần loại trừ class khác |
| Context mới nhưng dữ liệu test vẫn còn | Dữ liệu nằm trong database, file hoặc hệ thống ngoài context | Dọn dẹp tài nguyên ngoài context riêng |
| Test hoàn tất nhưng async task vẫn chạy | Không chờ hoặc cancel background work | Chờ future, verify/cancel publisher và shutdown executor |

## 13. Ghi nhớ

Spring TestContext có thể cache và chia sẻ `ApplicationContext` giữa các test. `@DirtiesContext` đóng context ở thời điểm được cấu hình, nên có thể làm test khác đang dùng cùng context thất bại nếu chúng chạy đồng thời. Mock bean và mock server cũng có trạng thái dùng chung; việc stubbing, reset hoặc tiêu thụ expectation từ nhiều test có thể gây kết quả không xác định. Ưu tiên cô lập mock và dữ liệu theo test. Khi cần chia sẻ, dùng `@ResourceLock` cho nhóm test liên quan, `@Execution(SAME_THREAD)` cho các node trong cùng class, hoặc `@Isolated` cho class cần độc quyền. Tắt parallel execution trên toàn suite khi chưa thể kiểm soát các tài nguyên dùng chung, và luôn kết thúc tác vụ bất đồng bộ trước khi test kết thúc.

