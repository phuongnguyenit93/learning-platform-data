# Reset mock và an toàn khi chạy kiểm thử song song

Trong unit test, một mock thường được tạo mới cho từng test method nên trạng thái lời gọi và cấu hình giả lập không bị chia sẻ lâu dài. Với Spring integration test, mock có thể được đăng ký thay cho một bean trong `ApplicationContext`. Vì Spring TestContext cache và tái sử dụng context, mock bean đó có thể tồn tại qua nhiều test method hoặc nhiều test class.

Điều này tạo ra hai vấn đề cần xử lý: **trạng thái mock phải được reset đúng thời điểm** và **nhiều test không được đồng thời sửa hoặc sử dụng cùng một mock theo cách gây xung đột**. Nếu một test để lại stub hoặc invocation, test tiếp theo có thể nhận kết quả cũ. Nếu hai test chạy song song trên cùng mock bean, một test có thể reset mock trong khi test còn lại đang stub, gọi hoặc verify nó.

## 1. Vì sao mock cần được reset?

Một Mockito mock lưu ít nhất hai nhóm trạng thái quan trọng:

- **Stubbing:** các quy tắc được khai báo bằng `when(...).thenReturn(...)`, `doReturn(...).when(...)`, `thenThrow(...)` hoặc các API tương tự.
- **Invocation history:** danh sách lời gọi đã xảy ra, gồm method, đối số và thông tin phục vụ verification.

Ví dụ:

```java
when(orderRepository.findById(42L)).thenReturn(Optional.of(order));

service.findOrder(42L);

verify(orderRepository).findById(42L);
```

Sau khi test hoàn tất, mock vẫn có thể giữ stub trả về `order` và lịch sử lời gọi `findById(42L)`. Nếu mock được dùng lại, test kế tiếp có thể vô tình nhận cùng kết quả hoặc verification có thể nhìn thấy lời gọi từ test trước.

Trong unit test thông thường, Mockito tạo mock mới trong mỗi test instance hoặc `@BeforeEach`, vì vậy trạng thái được cô lập tự nhiên. Trong Spring test, bean mock được quản lý bởi context có thể được chia sẻ do cơ chế cache. Vì vậy cần một chính sách reset rõ ràng.

## 2. Mock bean trong Spring và vòng đời ApplicationContext

Spring hỗ trợ thay thế bean trong test bằng Mockito mock. Tùy phiên bản, dự án có thể dùng `@MockBean` của Spring Boot hoặc `@MockitoBean` của Spring Framework.

### 2.1. @MockitoBean trong Spring Framework 6.2 trở lên

Spring Framework 6.2 cung cấp `@MockitoBean` trong package `org.springframework.test.context.bean.override.mockito`. Annotation này yêu cầu Spring tạo hoặc thay thế bean bằng Mockito mock trong `ApplicationContext`.

```java
@SpringJUnitConfig(OrderServiceTestConfig.class)
class OrderServiceTest {

    @MockitoBean
    private OrderRepository orderRepository;

    @Autowired
    private OrderService orderService;

    @Test
    void returnsOrderWhenRepositoryFindsIt() {
        var order = new Order(42L, "PENDING");
        when(orderRepository.findById(42L)).thenReturn(Optional.of(order));

        Order result = orderService.findOrder(42L);

        assertEquals(order, result);
        verify(orderRepository).findById(42L);
    }
}
```

`@MockitoBean` được xử lý bởi Spring TestContext và mock được đăng ký như một bean trong context. Các bean khác được inject sẽ nhận mock đó thay cho bean thật được chỉ định. Test có thể dùng mock để điều khiển kết quả của dependency mà không cần khởi động dịch vụ bên ngoài.

Nếu muốn chắc chắn một bean thật đã tồn tại và cần được thay thế, có thể dùng `enforceOverride = true`. Khi không có bean phù hợp để thay thế, context sẽ báo lỗi thay vì âm thầm tạo thêm mock bean:

```java
@MockitoBean(enforceOverride = true)
private OrderRepository orderRepository;
```

Điều này hữu ích khi mục tiêu test là xác minh đúng bean trong cấu hình ứng dụng đã được thay thế. Nếu test cố ý tạo mock mới cho một interface chưa có bean thật, không cần bật `enforceOverride`.

### 2.2. @MockBean trong các dự án Spring Boot cũ hơn

Các dự án Spring Boot trước đây thường dùng `@MockBean`:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;
}
```

`@MockBean` thuộc Spring Boot Test. Từ Spring Boot 3.4, annotation này đã bị deprecated để chuyển sang cơ chế bean override của Spring Framework, trong đó có `@MockitoBean`. Khi nâng cấp, cần dùng đúng annotation và enum `MockReset` tương ứng với phiên bản dependency của dự án; hai API có package khác nhau.

Không nên trộn `@MockBean` và `@MockitoBean` một cách tùy tiện trong cùng một test suite. Hãy theo phiên bản Spring Boot/Spring Framework mà dự án đang quản lý và giữ cách khai báo nhất quán.

### 2.3. Vì sao mock bean có thể được chia sẻ giữa các test?

Spring TestContext cache `ApplicationContext` để tránh khởi tạo lại các bean tốn thời gian. Các test có cấu hình context tương thích có thể nhận cùng một context được cache. Mock bean là bean trong context đó, nên nhiều test có thể truy cập cùng một instance.

```text
Test A --------+
               |
               v
        Cached ApplicationContext
               |
               v
        OrderRepository mock
               ^
               |
Test B --------+
```

`@TestInstance(PER_METHOD)` của JUnit tạo instance test class mới cho mỗi method theo mặc định, nhưng không tạo mới toàn bộ Spring `ApplicationContext`. Vì vậy, field test được inject có thể trỏ tới cùng một mock bean dù test object khác nhau.

Đây là điểm khác biệt quan trọng giữa `@Mock` cục bộ và `@MockitoBean`:

| Đặc điểm | Mockito `@Mock` cục bộ | Spring `@MockitoBean` |
|---|---|---|
| Nơi quản lý | Test instance hoặc Mockito extension | Spring ApplicationContext |
| Vòng đời thường gặp | Một test instance/method | Theo vòng đời context được cache |
| Chia sẻ giữa test | Không, nếu tạo mới đúng cách | Có thể, khi test dùng chung context |
| Reset | Tạo mock mới hoặc reset thủ công | Có chính sách reset do Spring quản lý |
| Phù hợp | Unit test logic độc lập | Spring integration/slice test cần thay bean trong context |

## 3. Chính sách reset mock của Spring

`@MockitoBean` có thuộc tính `reset` để xác định thời điểm Spring reset mock. Các lựa chọn thuộc `MockReset` là `BEFORE`, `AFTER` và `NONE`.

| Chế độ | Hành vi | Trường hợp sử dụng |
|---|---|---|
| `AFTER` | Reset mock sau mỗi test method | Mặc định; xóa stubbing và invocation sau khi test kết thúc |
| `BEFORE` | Reset mock trước mỗi test method | Muốn bắt đầu method với mock sạch trước khi `@BeforeEach` thiết lập stub |
| `NONE` | Không tự động reset | Chỉ dùng khi test chủ động quản lý toàn bộ trạng thái mock |

Với `@MockitoBean`, chế độ mặc định là `AFTER`. Spring TestContext sử dụng listener tích hợp Mockito để reset mock theo chính sách này. Test method có thể thiết lập stub trong phần chuẩn bị và sử dụng nó trong thân test; sau khi test hoàn tất, Spring reset mock để test tiếp theo không nhận trạng thái còn sót.

Ví dụ khai báo rõ chế độ mặc định:

```java
@MockitoBean(reset = MockReset.AFTER)
private OrderRepository orderRepository;
```

Nếu muốn reset trước method:

```java
@MockitoBean(reset = MockReset.BEFORE)
private OrderRepository orderRepository;
```

`MockReset` ở đây là `org.springframework.test.context.bean.override.mockito.MockReset` của Spring Framework. Với `@MockBean` cũ của Spring Boot, enum tương ứng nằm trong package `org.springframework.boot.test.mock.mockito`. Khi đọc hoặc chuyển đổi code, cần kiểm tra import để không dùng nhầm hai kiểu.

### 3.1. Reset AFTER: lựa chọn mặc định

Với `AFTER`, test được chạy trên mock đã được reset từ lần chạy trước. Sau khi test method kết thúc, Spring reset mock để xóa stubbing và invocation history.

```java
@SpringJUnitConfig(OrderServiceTestConfig.class)
class OrderServiceTest {

    @MockitoBean(reset = MockReset.AFTER)
    private OrderRepository orderRepository;

    @Autowired
    private OrderService orderService;

    @Test
    void findsExistingOrder() {
        when(orderRepository.findById(1L))
                .thenReturn(Optional.of(new Order(1L, "PENDING")));

        assertEquals("PENDING", orderService.findOrder(1L).status());
    }

    @Test
    void returnsEmptyWhenOrderDoesNotExist() {
        when(orderRepository.findById(2L)).thenReturn(Optional.empty());

        assertTrue(orderService.findOrderOptional(2L).isEmpty());
    }
}
```

Hai method có thể dùng cùng mock bean vì Spring reset mock sau mỗi method. Stub của test đầu không được giữ lại để ảnh hưởng test thứ hai.

### 3.2. BEFORE: reset trước khi thiết lập fixture

`BEFORE` xóa trạng thái mock trước khi test method chạy. Cách này hữu ích khi phần `@BeforeEach` của test cần cấu hình stubbing mới và muốn bảo đảm mọi invocation từ lần chạy trước đã bị xóa trước lúc fixture được dựng.

```java
@MockitoBean(reset = MockReset.BEFORE)
private PaymentGateway paymentGateway;

@BeforeEach
void setUp() {
    when(paymentGateway.isAvailable()).thenReturn(true);
}

@Test
void processesPaymentWhenGatewayIsAvailable() {
    // Stub trong setUp đã được cấu hình trên mock sạch.
}
```

Spring thực hiện reset ở callback trước test method; callback chuẩn bị của JUnit như `@BeforeEach` diễn ra trong vòng đời thực thi method. Vì vậy, stub được thiết lập trong `@BeforeEach` vẫn tồn tại khi thân test chạy.

### 3.3. NONE: tự chịu trách nhiệm quản lý trạng thái

`NONE` tắt việc reset tự động. Stub và invocation có thể tồn tại qua nhiều test dùng cùng context:

```java
@MockitoBean(reset = MockReset.NONE)
private OrderRepository orderRepository;
```

Chế độ này thường không cần thiết. Nếu một test chọn `NONE`, test phải bảo đảm stubbing và invocation không gây ảnh hưởng tới test khác. Có thể gọi `Mockito.reset(...)` hoặc `clearInvocations(...)` theo mục tiêu, nhưng việc cleanup thủ công dễ bị bỏ sót khi test thất bại hoặc có nhiều nhánh.

Chỉ chọn `NONE` khi có một lý do rõ ràng, chẳng hạn mock có trạng thái được quản lý bởi một fixture dùng chung có chủ đích. Nếu mỗi test cần kịch bản riêng, `AFTER` hoặc `BEFORE` thường đơn giản và an toàn hơn.

## 4. reset(), clearInvocations() và tạo mock mới

Mockito có các thao tác làm sạch khác nhau. Cần hiểu rõ tác động trước khi dùng.

| API | Xóa stubbing | Xóa invocation history | Dùng khi |
|---|---|---|---|
| `Mockito.reset(mock)` | Có | Có | Cần đưa mock về trạng thái ban đầu hoàn toàn |
| `Mockito.clearInvocations(mock)` | Không | Có | Muốn giữ stub nhưng bắt đầu lại việc verify |
| Tạo mock mới | Có, vì mock mới chưa có trạng thái | Có | Muốn cô lập test bằng instance riêng |

Ví dụ:

```java
when(repository.count()).thenReturn(5L);
service.loadCount();

clearInvocations(repository);

verifyNoInteractions(repository); // Invocation cũ đã bị xóa
assertEquals(5L, repository.count()); // Stub vẫn còn
```

Ví dụ trên chỉ minh họa khác biệt giữa hai loại trạng thái; trong một test thực tế, cần lưu ý chính lời gọi `repository.count()` cuối cùng cũng tạo invocation mới sau khi `clearInvocations`.

`reset(mock)` xóa cả stub lẫn lịch sử gọi. Sau reset, lời gọi chưa được stub sẽ trả về giá trị mặc định theo kiểu trả về, chẳng hạn `null`, `0`, `false` hoặc collection rỗng tùy cấu hình Mockito. Đây là lý do reset quá sớm có thể làm test thất bại với lỗi khó hiểu.

Tạo mock mới thường là lựa chọn tốt nhất trong unit test thuần. Reset mock bean trong Spring có mục đích khác: mock thuộc context được cache và được inject vào nhiều bean, nên Spring cần một cơ chế dọn trạng thái để giữ context dùng lại được.

## 5. Reset mock không đồng nghĩa với tạo mới bean

Khi Spring reset một `@MockitoBean`, Spring làm sạch trạng thái Mockito trên cùng instance mock. Spring không nhất thiết loại bean khỏi ApplicationContext rồi tạo một mock object mới.

Điều này có ý nghĩa khi một bean khác đã được inject mock vào constructor hoặc field. Bean đó vẫn giữ tham chiếu tới cùng instance; reset giúp instance trở về trạng thái mock sạch mà không phải dựng lại toàn bộ context.

```text
ApplicationContext được cache
       |
       +---- OrderService
       |         |
       |         +---- tham chiếu OrderRepository mock
       |
       +---- OrderRepository mock
                  |
                  +---- stubbing + invocation

Sau reset:
       |
       +---- OrderService vẫn giữ cùng tham chiếu
       |
       +---- OrderRepository mock vẫn cùng instance,
             nhưng stubbing và invocation đã được xóa
```

Nếu test thay thế một bean bằng instance khác ngoài cơ chế bean override, các bean đã inject tham chiếu cũ có thể không tự động nhận instance mới. Vì vậy, hãy dùng cơ chế `@MockitoBean`/`@MockBean` của Spring khi cần thay bean trong context, thay vì tự sửa bean factory sau khi các bean khác đã được tạo.

## 6. Vì sao reset mock có thể không an toàn khi chạy song song?

JUnit Jupiter mặc định chạy test tuần tự. Khi bật parallel execution, nhiều test method hoặc test class có thể chạy đồng thời. Nếu chúng dùng chung một Spring context và cùng truy cập một mock bean, các thao tác trên mock có thể xen kẽ.

Ví dụ hai test cùng sử dụng `orderRepository`:

```text
Test A                         Test B
------                         ------
stub findById(1)               stub findById(2)
call service(1)                call service(2)
verify findById(1)             verify findById(2)
reset mock AFTER               reset mock AFTER
```

Nếu hai test chạy đồng thời:

- Stub của A và B có thể cùng tồn tại trên một mock, khiến kết quả phụ thuộc đối số và cách cấu hình.
- Invocation history chứa lời gọi của cả hai test, nên verification có thể nhìn thấy tương tác của test còn lại.
- Một test có thể reset mock trong lúc test kia đang thực thi hoặc verify.
- Stub vừa được tạo có thể bị reset trước khi test kia gọi dependency.
- Thứ tự chạy không ổn định có thể làm lỗi chỉ xuất hiện thỉnh thoảng trên CI.

Reset `AFTER` chỉ bảo đảm mock được làm sạch sau một test method theo vòng đời listener. Nó không biến mock bean dùng chung thành mock riêng cho từng thread. `BEFORE` cũng không giải quyết được xung đột nếu hai test bắt đầu đồng thời: một test có thể reset mock sau khi test còn lại đã stub.

Mockito hỗ trợ sử dụng mock trong các tình huống đa luồng nhất định, nhưng điều đó không làm cho một kịch bản có nhiều test cùng thay đổi stubbing, invocation history và reset trở nên độc lập. Vấn đề ở đây là các test đang chia sẻ trạng thái có thể thay đổi, không chỉ là thread safety nội bộ của thư viện.

## 7. JUnit Jupiter parallel execution

Mặc định, JUnit Jupiter không bật chạy song song. Có thể bật qua file `junit-platform.properties` trên test classpath:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
```

Với cấu hình này, Jupiter có thể chạy đồng thời các test method và class theo execution mode. Nếu dự án chưa bật parallel execution, các test trong cùng một lần chạy JUnit thường được thực thi tuần tự theo scheduler của engine.

Không nên bật parallel execution chỉ để giảm thời gian chạy mà chưa xác định các tài nguyên dùng chung. Ngoài mock bean, các tài nguyên có thể gây xung đột gồm:

- Singleton bean mutable trong ApplicationContext.
- Database record hoặc schema dùng chung.
- File, thư mục tạm hoặc port cố định.
- System property, default locale, timezone và system clock.
- Static field, singleton cache hoặc trạng thái dùng chung của thư viện.
- Container hoặc dịch vụ ngoài được nhiều test cùng thay đổi.

## 8. Cách bảo vệ test khi cần chạy song song

### 8.1. Ưu tiên mock cục bộ cho unit test

Nếu chỉ kiểm tra logic của một service và không cần Spring context, hãy tạo mock mới cho mỗi test bằng Mockito extension:

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceUnitTest {

    @Mock
    private OrderRepository orderRepository;

    @InjectMocks
    private OrderService orderService;

    @Test
    void findsOrder() {
        when(orderRepository.findById(1L))
                .thenReturn(Optional.of(new Order(1L, "PENDING")));

        assertEquals("PENDING", orderService.findOrder(1L).status());
    }
}
```

Với JUnit mặc định `PER_METHOD`, mỗi test method nhận một test instance mới; Mockito extension khởi tạo mock mới cho instance đó. Đây là cách cô lập đơn giản khi không cần kiểm tra bean wiring hoặc cấu hình Spring.

### 8.2. Không chạy đồng thời test chia sẻ cùng mock bean

Nếu các test cần `@MockitoBean` trong cùng context, có thể giữ nhóm test đó ở chế độ tuần tự. Cách đơn giản nhất là không bật parallel execution cho nhóm này hoặc cấu hình execution mode phù hợp.

JUnit Jupiter cung cấp `@ResourceLock` để đồng bộ các test cùng sử dụng một tài nguyên logic:

```java
@SpringJUnitConfig(OrderServiceTestConfig.class)
@ResourceLock("shared-order-repository-mock")
class OrderServiceIntegrationTests {

    @MockitoBean
    private OrderRepository orderRepository;

    @Test
    void findsPendingOrder() {
        when(orderRepository.findById(1L))
                .thenReturn(Optional.of(new Order(1L, "PENDING")));
        // ...
    }

    @Test
    void returnsEmptyForMissingOrder() {
        when(orderRepository.findById(2L)).thenReturn(Optional.empty());
        // ...
    }
}
```

`@ResourceLock` khiến test có cùng resource name phải tuân theo cơ chế khóa của JUnit Platform trong cùng test execution. Có thể đặt annotation trên class để bảo vệ toàn bộ test trong class hoặc trên method để bảo vệ một số method cụ thể.

Nếu nhiều class khác nhau dùng chung mock bean và cần khóa qua các class đó, hãy khai báo cùng một resource name trên các class/method liên quan. Tên tài nguyên phải thống nhất; hai tên khác nhau không tạo cùng một khóa.

`@ResourceLock` chỉ điều phối trong phạm vi một JUnit execution/JVM. Nó không tạo khóa phân tán giữa nhiều tiến trình Gradle fork, Maven fork hoặc nhiều worker CI. Nếu tài nguyên được chia sẻ giữa các JVM, cần cô lập tài nguyên hoặc dùng cơ chế khóa bên ngoài phù hợp.

### 8.3. Dùng @Isolated cho test cần độc quyền toàn cục trong JUnit run

JUnit Jupiter có `@Isolated` để đánh dấu test class cần chạy độc lập với các test khác trong cùng test plan. Nó hữu ích khi test tác động đến trạng thái toàn cục khó mô hình hóa bằng một resource lock cụ thể.

```java
@Isolated
class GlobalConfigurationTests {

    @Test
    void changesGlobalConfigurationTemporarily() {
        // Test thay đổi trạng thái toàn cục và khôi phục sau đó.
    }
}
```

`@Isolated` ảnh hưởng tới scheduling của JUnit Platform trong một lần chạy; nó không thay thế cleanup và cũng không đồng bộ các JVM khác nhau. Chỉ dùng khi test thực sự cần độc quyền trên toàn bộ test plan vì annotation có thể làm giảm mức song song.

### 8.4. Dùng context riêng khi cần trạng thái mock độc lập

Nếu hai nhóm test cần cấu hình mock khác nhau và phải chạy song song, có thể thiết kế context riêng cho mỗi nhóm. Context cache nhận diện cấu hình và bean override; các cấu hình khác nhau có thể tạo các context khác nhau, do đó mỗi nhóm nhận mock bean riêng.

Tuy nhiên, không nên cố ý tạo nhiều context chỉ để né một vấn đề reset nếu một `@ResourceLock` hoặc chạy tuần tự đã đáp ứng yêu cầu. Nhiều context làm tăng thời gian khởi động, số connection pool và lượng tài nguyên cần quản lý.

### 8.5. Tránh chia sẻ stub thay đổi giữa test

Ngay cả khi test chạy tuần tự, nên thiết lập stub trong phạm vi từng test hoặc `@BeforeEach`, không dựa vào stub từ test trước. Không dùng thứ tự test làm một phần của hợp đồng.

Một số nguyên tắc hữu ích:

- Mỗi test tự cấu hình phản hồi của mock mà nó cần.
- Không để một test phụ thuộc vào invocation history do test khác tạo ra.
- Không lưu mock hoặc kết quả stub vào static field dùng chung.
- Không dùng `@TestInstance(PER_CLASS)` để chia sẻ mock mutable trừ khi có lý do rõ ràng và đồng bộ phù hợp.
- Tránh gọi `reset()` từ một thread hoặc callback tùy ý trong khi test khác có thể đang dùng mock.

## 9. @DirtiesContext không phải cơ chế khóa song song

`@DirtiesContext` loại context khỏi cache và đóng nó theo phạm vi được chỉ định. Annotation này hữu ích khi test làm thay đổi trạng thái context khiến nó không thể tái sử dụng an toàn.

Tuy nhiên, `@DirtiesContext` không đồng bộ hai test đang chạy. Nếu test A đóng context trong khi test B vẫn đang sử dụng bean từ context đó, test B có thể gặp lỗi hoặc hành vi không xác định. Vì vậy:

- Không dùng `@DirtiesContext` như một cách thay thế `@ResourceLock`.
- Không giả định `@DirtiesContext` sẽ chờ tất cả test khác dùng context kết thúc.
- Tránh để test chạy song song nếu chúng cùng context và một test có thể đánh dấu context dirty.
- Nếu cần reset cấu hình context, hãy điều phối thứ tự test hoặc tách context phù hợp.

Việc reset mock và việc loại context khỏi cache giải quyết hai vấn đề khác nhau. Reset giữ nguyên bean mock nhưng xóa trạng thái Mockito; `@DirtiesContext` đóng và loại context theo phạm vi đã chọn.

## 10. Thứ tự reset và vòng đời JUnit/Spring

Spring TestContext tích hợp với JUnit thông qua `SpringExtension`. Các listener của TestContext được gọi ở các điểm trong vòng đời test để chuẩn bị context, inject dependency, thực hiện transaction và reset bean override.

Ở mức khái quát, với một test method:

```text
Spring chuẩn bị test context và inject field
                  |
                  v
Reset mock nếu cấu hình BEFORE
                  |
                  v
JUnit @BeforeEach
                  |
                  v
Test method
                  |
                  v
JUnit @AfterEach
                  |
                  v
Reset mock nếu cấu hình AFTER
                  |
                  v
Kết thúc test method
```

Sơ đồ biểu diễn thứ tự khái quát để giải thích chính sách reset. Chi tiết callback có thể phụ thuộc extension và listener khác được đăng ký trong test. Nếu một extension khác cũng thay đổi mock hoặc trạng thái context, cần xem thứ tự thực thi của extension đó.

Với `BEFORE`, stubbing trong `@BeforeEach` được thiết lập sau khi reset. Với `AFTER`, stubbing và invocation của test được dọn sau khi method kết thúc. Nếu dùng `NONE`, Spring không thực hiện bước reset tự động.

## 11. Những tình huống dễ gây lỗi

### 11.1. Stub còn sót từ test trước

Triệu chứng: test không khai báo stub cho một lời gọi nhưng service vẫn nhận được một đối tượng cụ thể. Nguyên nhân có thể là mock bean được tái sử dụng và không được reset.

Cách xử lý:

- Kiểm tra `@MockitoBean` có dùng reset mặc định hoặc cấu hình `AFTER`/`BEFORE` không.
- Nếu dùng `NONE`, kiểm tra cleanup thủ công.
- Đảm bảo test không phụ thuộc vào thứ tự chạy.

### 11.2. Verification nhìn thấy invocation từ test khác

Triệu chứng: `verify(mock).someMethod()` thất bại vì có nhiều lời gọi hơn dự kiến. Nếu mock được chia sẻ, invocation history có thể chứa tương tác của test khác hoặc test trước.

Cách xử lý là reset/clear invocation đúng thời điểm hoặc bảo đảm test không chạy đồng thời trên cùng mock. `clearInvocations` chỉ xóa lịch sử lời gọi, còn stub vẫn được giữ; `reset` xóa cả hai.

### 11.3. Test thất bại ngẫu nhiên khi CI bật parallel

Triệu chứng: chạy riêng từng test thì thành công, chạy cả suite hoặc trên CI lại thất bại không ổn định.

Hãy kiểm tra:

- Nhiều test có dùng chung `@MockitoBean` trong cùng context không?
- Có test nào dùng `reset = NONE` hoặc gọi `Mockito.reset()` thủ công không?
- Có test nào đánh dấu `@DirtiesContext` khi test khác vẫn dùng context không?
- JUnit parallel execution hoặc build tool parallel fork có đang bật không?
- Có system property, static state, file, port hoặc dữ liệu database dùng chung không?

Sau đó chọn `@ResourceLock`, `@Isolated`, chạy tuần tự hoặc tách tài nguyên/context theo phạm vi thực sự bị chia sẻ.

### 11.4. Reset mock nhưng stub trong @BeforeEach không còn

Nếu dùng `BEFORE`, Spring reset trước khi JUnit chạy `@BeforeEach`; stub được cấu hình trong callback đó sẽ còn hiệu lực khi test method bắt đầu. Nếu test tự gọi `Mockito.reset()` sau `@BeforeEach`, stub vừa thiết lập sẽ bị xóa. Hãy tránh reset thủ công không cần thiết trong thân test.

### 11.5. Một test cần giữ invocation để assertion ở @AfterEach

Nếu cần kiểm tra invocation trong `@AfterEach`, chế độ `AFTER` thường reset sau callback cleanup của test method. Tuy nhiên, không nên dựa vào chi tiết listener nếu một extension khác cũng thao tác mock. Có thể đặt assertion trực tiếp trong test method sau hành động cần kiểm tra để vòng đời rõ ràng hơn.

## 12. Ví dụ tổ chức test Spring an toàn

Giả sử `OrderService` phụ thuộc `OrderRepository`. Một integration test cần thay repository bằng mock trong Spring context:

```java
@SpringJUnitConfig(OrderServiceTestConfig.class)
@ResourceLock("order-service-repository-mock")
class OrderServiceSpringTest {

    @MockitoBean(reset = MockReset.AFTER)
    private OrderRepository orderRepository;

    @Autowired
    private OrderService orderService;

    @Test
    void returnsExistingOrder() {
        var order = new Order(42L, "PENDING");
        when(orderRepository.findById(42L))
                .thenReturn(Optional.of(order));

        Order result = orderService.findOrder(42L);

        assertEquals(42L, result.id());
        verify(orderRepository).findById(42L);
    }

    @Test
    void reportsMissingOrder() {
        when(orderRepository.findById(99L))
                .thenReturn(Optional.empty());

        assertThrows(OrderNotFoundException.class,
                () -> orderService.findOrder(99L));

        verify(orderRepository).findById(99L);
    }
}
```

Trong ví dụ, mỗi method tự thiết lập stub và kiểm tra tương tác của chính nó. `AFTER` dọn mock sau method; `@ResourceLock` điều phối các test khác cũng khai báo cùng resource name trong cùng JUnit execution. Nếu không bật parallel execution, lock có thể không cần thiết, nhưng nó thể hiện rõ tài nguyên được bảo vệ khi suite thay đổi cấu hình chạy.

Nếu hai test không cần Spring wiring, nên chuyển chúng thành unit test với `@Mock` và `@InjectMocks`. Khi đó mỗi test instance có mock riêng và không cần khóa dùng chung.

## 13. Checklist trước khi bật parallel execution

Trước khi cho phép test Spring chạy đồng thời, hãy xác định:

- Test nào sử dụng `@MockitoBean` hoặc `@MockBean`?
- Các test đó có dùng chung ApplicationContext và cùng mock bean không?
- Mock có được reset tự động không, và reset diễn ra trước hay sau test?
- Có test nào dùng `MockReset.NONE` hoặc reset thủ công không?
- Các test có cùng thay đổi stubbing hoặc verify invocation trên một mock không?
- Có test nào dùng `@DirtiesContext` trên context mà test khác đang sử dụng không?
- Có thể thay mock Spring bean bằng mock cục bộ trong unit test không?
- Có thể dùng `@ResourceLock` hoặc `@Isolated` để bảo vệ phần tài nguyên chia sẻ không?
- Build tool có chạy nhiều JVM/fork hoặc nhiều worker CI cùng lúc không?
- Database, file, port, system property và static state đã được cô lập chưa?

Không cần khóa mọi test chỉ vì chúng đều dùng Spring. Chỉ các test có khả năng truy cập và thay đổi cùng tài nguyên cần được điều phối. Khóa quá rộng làm giảm mức song song và có thể che khuất thiết kế chia sẻ trạng thái không cần thiết.

## 14. Nguyên tắc thực hành

- Dùng mock cục bộ và tạo mới theo từng test cho unit test thuần.
- Dùng `@MockitoBean` khi cần thay một bean trong Spring context; dùng `@MockBean` theo codebase cũ tương thích với phiên bản Spring Boot.
- Giữ reset tự động ở `AFTER` hoặc `BEFORE` trừ khi có lý do rõ ràng để chọn `NONE`.
- Hiểu rằng reset làm sạch cùng instance mock, không tạo instance mới và không làm mới ApplicationContext.
- Không để test phụ thuộc stub hoặc invocation từ test khác.
- Nếu nhiều test chia sẻ mock bean, không cho chúng đồng thời stub, gọi, verify hoặc reset cùng mock; dùng `@ResourceLock`, `@Isolated` hoặc chạy tuần tự.
- Nhớ rằng khóa JUnit không điều phối nhiều JVM hoặc nhiều CI worker.
- Không dùng `@DirtiesContext` như một cơ chế khóa; annotation này chỉ loại context khỏi cache và đóng context.
- Tách test cần context độc lập khi yêu cầu song song thực sự cần thiết, đồng thời cân nhắc chi phí tạo context.
- Chạy test riêng và chạy cả suite trong cấu hình CI để phát hiện lỗi phụ thuộc thứ tự hoặc trạng thái chia sẻ.

Reset mock và điều phối chạy song song là hai phần của cùng một vấn đề quản lý trạng thái test. Spring có thể tái sử dụng `ApplicationContext`, do đó mock bean cũng có thể được dùng lại. Chính sách reset giúp mỗi test bắt đầu hoặc kết thúc với mock ở trạng thái xác định; cơ chế khóa hoặc cô lập bảo đảm hai test không đồng thời thay đổi cùng một mock. Khi chọn đúng phạm vi unit test, Spring integration test và parallel execution, bộ kiểm thử vừa tận dụng được context cache vừa giữ kết quả ổn định giữa local và CI.
