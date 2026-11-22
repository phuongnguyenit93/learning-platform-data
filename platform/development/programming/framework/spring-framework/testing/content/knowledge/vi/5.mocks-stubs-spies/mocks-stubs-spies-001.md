# Phân biệt đối tượng thật, fake, stub, mock và spy

Khi kiểm thử một ứng dụng Spring, một lớp thường cộng tác với repository, HTTP client, cổng thanh toán, message publisher, clock hoặc các dịch vụ khác. Nếu mọi test đều kết nối đến phụ thuộc thật, việc chạy test sẽ chậm, khó cô lập và dễ bị ảnh hưởng bởi môi trường. Nếu thay mọi phụ thuộc bằng mock, test có thể chạy nhanh nhưng bỏ qua hành vi thực tế của các thành phần.

Để chọn cách thay thế phù hợp, cần phân biệt năm khái niệm: **đối tượng thật (real object), fake, stub, mock và spy**. Chúng mô tả những cách khác nhau để cung cấp hoặc quan sát hành vi của một phụ thuộc trong test.

Fake, stub, mock và spy thường được gọi chung là *test doubles* (đối tượng thay thế trong kiểm thử). Một đối tượng Mockito có thể đóng vai trò stub trong test này và mock trong test khác, tùy cách test sử dụng nó. Tên API không quyết định vai trò; mục đích của phép kiểm tra mới quyết định.

## 1. Đối tượng thật (real object)

Đối tượng thật là implementation thực tế mà ứng dụng sử dụng. Nó thực hiện hành vi thật của lớp hoặc thành phần đó, chẳng hạn:

- Một service tính phí theo quy tắc nghiệp vụ.
- Một repository JPA truy vấn cơ sở dữ liệu.
- Một HTTP client gửi request đến dịch vụ khác.
- Một adapter ghi message vào broker.
- Một formatter chuyển đổi dữ liệu theo cấu hình ứng dụng.

Ví dụ, một repository Spring Data JPA là thành phần thật khi test gọi repository do Spring tạo và nó truy cập database được cấu hình cho test.

~~~java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void savesAndFindsAnOrder() {
        var order = new OrderEntity("order-18", "customer-7");

        OrderEntity saved = repository.save(order);

        Optional<OrderEntity> loaded =
                repository.findById(saved.getId());

        assertTrue(loaded.isPresent());
        assertEquals("customer-7", loaded.get().getCustomerId());
    }
}
~~~

Ở đây, repository không phải mock. Spring cung cấp repository implementation và nó thực hiện thao tác persistence trong database mà test sử dụng.

**Ưu điểm**

- Kiểm tra được hành vi thực tế của implementation.
- Có thể phát hiện lỗi cấu hình, mapping, transaction, truy vấn hoặc tương tác giữa các thành phần.
- Tăng mức độ đại diện cho môi trường ứng dụng thật khi test dùng đúng loại hạ tầng.

**Chi phí và giới hạn**

- Có thể cần Spring context, database, mạng hoặc dịch vụ phụ trợ.
- Thời gian chạy và thiết lập thường cao hơn test dùng đối tượng thay thế.
- Kết quả có thể phụ thuộc dữ liệu, trạng thái môi trường và tính ổn định của dịch vụ bên ngoài.
- Khó tạo một số tình huống lỗi hiếm gặp, chẳng hạn timeout hoặc phản hồi bất thường từ dịch vụ bên thứ ba.

Đối tượng thật phù hợp khi chính hành vi tích hợp là điều cần xác minh. Nếu đang kiểm tra một quy tắc tính toán thuần Java, việc khởi động database chỉ làm tăng chi phí mà không bổ sung bằng chứng cần thiết.

## 2. Fake: implementation đơn giản nhưng có hành vi thực

**Fake** là một implementation có thể hoạt động được, thường đơn giản hơn implementation production và có thể bỏ qua một số đặc tính của môi trường thật.

Fake không chỉ trả về một giá trị cố định. Nó có thể giữ trạng thái và thực hiện các thao tác cơ bản theo hợp đồng của interface.

Ví dụ, ứng dụng có interface repository:

~~~java
public interface OrderRepository {
    Optional<Order> findById(String id);

    void save(Order order);
}
~~~

Trong production, implementation có thể sử dụng JPA và database. Trong unit test, ta có thể tạo một fake lưu dữ liệu trong bộ nhớ:

~~~java
public class InMemoryOrderRepository implements OrderRepository {

    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public Optional<Order> findById(String id) {
        return Optional.ofNullable(orders.get(id));
    }

    @Override
    public void save(Order order) {
        orders.put(order.id(), order);
    }
}
~~~

Fake này hỗ trợ lưu và tìm đơn hàng. Nó có thể được dùng trong nhiều test như một repository nhỏ, không cần database.

~~~java
@Test
void retrievesAnOrderThatWasPreviouslySaved() {
    OrderRepository repository = new InMemoryOrderRepository();
    var order = new Order("order-18", OrderStatus.PENDING);

    repository.save(order);

    assertEquals(Optional.of(order), repository.findById("order-18"));
}
~~~

Fake thực hiện một phần hợp đồng bằng cách đơn giản hóa cách lưu trữ hoặc xử lý. Nó có thể dùng Map thay cho database, danh sách trong bộ nhớ thay cho message broker, hoặc một bộ định tuyến đơn giản thay cho dịch vụ định tuyến thật.

Vì vậy, fake có thể xác nhận logic của service khi service cộng tác với một interface, nhưng không chứng minh rằng implementation production hoạt động đúng. InMemoryOrderRepository không kiểm tra SQL, transaction, constraint, index, locking hoặc mapping JPA.

**Khi nào nên dùng fake?**

- Khi cần một phụ thuộc có trạng thái để nhiều thao tác trong test phối hợp với nhau.
- Khi nhiều test cần cùng một implementation đơn giản và dễ tái sử dụng.
- Khi muốn kiểm tra service qua interface mà không phải cấu hình mock phức tạp cho từng lời gọi.
- Khi dữ liệu trong bộ nhớ đủ để mô phỏng hành vi mà test quan tâm.

Fake cần được giữ đơn giản. Nếu fake bắt đầu mô phỏng toàn bộ transaction, locking, truy vấn và quy tắc của database, nó sẽ trở thành một implementation thứ hai khó bảo trì và có nguy cơ sai khác production.

## 3. Stub: cung cấp phản hồi đã định trước

**Stub** cung cấp câu trả lời được định trước cho những lời gọi mà đối tượng đang kiểm thử thực hiện. Mục đích chính là kiểm soát đầu vào gián tiếp của test để tập trung vào hành vi của lớp cần kiểm tra.

Ví dụ, OrderService cần hỏi PaymentGateway kết quả thanh toán. Trong test, ta muốn mô phỏng trường hợp cổng thanh toán từ chối giao dịch:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private PaymentGateway paymentGateway;

    @Mock
    private OrderRepository orderRepository;

    @InjectMocks
    private OrderService orderService;

    @Test
    void rejectsOrderWhenPaymentIsDeclined() {
        var order = new Order("order-18", OrderStatus.PENDING);

        when(orderRepository.findById("order-18"))
                .thenReturn(Optional.of(order));

        when(paymentGateway.charge(order))
                .thenReturn(PaymentResult.declined());

        OrderResult result = orderService.pay("order-18");

        assertEquals(OrderStatus.REJECTED, result.status());
    }
}
~~~

Hai cấu hình **when(...).thenReturn(...)** thiết lập phản hồi cho các phụ thuộc: repository trả về đơn hàng đã biết và PaymentGateway trả về kết quả từ chối. Trong test này, mock PaymentGateway đang được sử dụng với vai trò stub vì test cần câu trả lời đã định trước. Mục tiêu của assertion là xác nhận OrderService xử lý kết quả từ chối đúng theo nghiệp vụ.

### Stub viết tay

Stub không bắt buộc phải được tạo bằng Mockito. Có thể viết một implementation nhỏ chỉ trả về phản hồi đã cấu hình:

~~~java
class DecliningPaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(Order order) {
        return PaymentResult.declined();
    }
}
~~~

Implementation này là một stub nếu mục tiêu của nó là cung cấp phản hồi cố định cho kịch bản test.

Một stub có thể có một hoặc vài nhánh được thiết lập trước. Ví dụ, stub có thể trả về thành công với một mã đơn hàng và từ chối với mã khác. Khi số lượng kịch bản tăng lên, hãy cân nhắc dùng fake hoặc cấu hình mock rõ ràng để tránh tạo một stub viết tay có quá nhiều điều kiện.

**Ưu điểm**

- Kiểm soát được phản hồi của phụ thuộc.
- Dễ mô phỏng lỗi, timeout, dữ liệu rỗng hoặc trạng thái đặc biệt.
- Giúp test tập trung vào kết quả của lớp đang kiểm tra.
- Không cần gọi dịch vụ bên ngoài.

**Giới hạn**

- Stub không chứng minh phụ thuộc thật sẽ trả về dữ liệu như vậy trong môi trường thực.
- Stub thường không xác minh rằng lời gọi có xảy ra hay xảy ra đúng số lần.
- Nếu phản hồi stub không còn khớp hợp đồng của phụ thuộc, test có thể tạo ra một tình huống không thực tế.

Stub phù hợp khi điều quan trọng là kiểm tra lớp đang xét phản ứng thế nào với một phản hồi đã biết.

## 4. Mock: xác minh tương tác với phụ thuộc

**Mock** là đối tượng thay thế được cấu hình để ghi nhận lời gọi và cho phép test xác minh các tương tác có ý nghĩa. Test có thể kiểm tra một phương thức đã được gọi, tham số được truyền vào hoặc số lần gọi.

Ví dụ, khi thanh toán thành công, OrderService phải lưu đơn hàng với trạng thái PAID:

~~~java
@Test
void savesOrderAfterSuccessfulPayment() {
    var order = new Order("order-18", OrderStatus.PENDING);

    when(orderRepository.findById("order-18"))
            .thenReturn(Optional.of(order));

    when(paymentGateway.charge(order))
            .thenReturn(PaymentResult.approved());

    orderService.pay("order-18");

    verify(orderRepository).save(
            argThat(saved -> saved.status() == OrderStatus.PAID)
    );
}
~~~

Ở đây, test dùng các mock để cung cấp dữ liệu và kiểm tra rằng OrderRepository nhận một đơn hàng đã chuyển sang trạng thái PAID.

Một số assertion tương tác thường dùng trong Mockito:

~~~java
verify(repository).save(order);

verify(repository, times(2)).save(any());

verify(repository, never()).delete(any());

verify(repository, atLeastOnce()).save(any());
~~~

Các phương thức trên xác minh lời gọi và số lần gọi. Hãy chọn mức xác minh phản ánh hợp đồng cần bảo vệ.

### Stub và mock khác nhau như thế nào?

Hai khái niệm này thường bị nhầm vì Mockito dùng cùng một đối tượng mock để thiết lập phản hồi và xác minh lời gọi.

| Khía cạnh | Stub | Mock |
|---|---|---|
| Mục đích chính | Cung cấp phản hồi đã định trước | Kiểm tra tương tác |
| Câu hỏi của test | Phụ thuộc trả về gì? | Lớp đang kiểm tra đã gọi phụ thuộc đúng chưa? |
| Cách dùng thường gặp | when(...).thenReturn(...) | verify(...) |
| Trọng tâm assertion | Kết quả hoặc trạng thái của lớp đang kiểm tra | Lời gọi, tham số, số lần gọi hoặc thứ tự có ý nghĩa |

Một Mockito mock được cấu hình bằng **when(...).thenReturn(...)** nhưng không có assertion **verify(...)** có thể đang đóng vai trò stub. Nếu test dùng **verify(...)** để kiểm tra lời gọi, nó đang đóng vai trò mock theo nghĩa kiểm thử tương tác.

Do đó, không nên hiểu rằng stub và mock nhất thiết là hai loại class riêng biệt. Đây là hai vai trò thường dùng của test double.

### Khi nào nên xác minh tương tác?

Xác minh tương tác có ý nghĩa khi lời gọi đó là một phần của hành vi cần bảo vệ, ví dụ:

- Service phải gửi một message sau khi giao dịch được xác nhận.
- Repository phải lưu thay đổi khi nghiệp vụ hoàn tất.
- Dịch vụ thanh toán không được gọi khi dữ liệu đầu vào không hợp lệ.
- Một thao tác gửi email chỉ được thực hiện một lần trong một kịch bản cụ thể.

Không nên xác minh mọi lời gọi nội bộ chỉ vì Mockito cho phép làm điều đó. Nếu test kiểm tra rằng service gọi ba helper theo đúng thứ tự nội bộ, việc tái cấu trúc có thể làm test hỏng dù hành vi bên ngoài vẫn đúng.

Ưu tiên kiểm tra kết quả quan sát được. Chỉ kiểm tra tương tác khi bản thân tương tác đó có ý nghĩa nghiệp vụ hoặc là hợp đồng giữa các thành phần.

## 5. Spy: giữ hành vi thật và quan sát lời gọi

**Spy** là đối tượng theo dõi một instance có hành vi thật. Các phương thức thường chạy implementation thật theo mặc định, đồng thời Mockito cho phép xác minh lời gọi hoặc thay thế hành vi của một số phương thức.

Ví dụ đơn giản với một danh sách:

~~~java
@Test
void spyKeepsRealListBehaviorAndRecordsInteraction() {
    List<String> events = spy(new ArrayList<>());

    events.add("order-created");

    assertEquals(List.of("order-created"), events);
    verify(events).add("order-created");
}
~~~

Danh sách vẫn thực hiện hành vi thật của ArrayList: phần tử được thêm và có thể đọc lại. Đồng thời, test có thể xác minh phương thức add đã được gọi.

### Spy có thể thay thế một phần hành vi

Spy cũng cho phép stub một phương thức cụ thể trong khi các phương thức khác vẫn chạy thật. Ví dụ, một dịch vụ đọc thời gian hệ thống có thể được spy để cố định thời gian trong test:

~~~java
class SystemTimeProvider {
    Instant now() {
        return Instant.now();
    }
}
~~~

~~~java
@Test
void usesFixedTimeFromSpy() {
    SystemTimeProvider timeProvider = spy(new SystemTimeProvider());
    Instant fixedTime = Instant.parse("2026-04-12T10:00:00Z");

    doReturn(fixedTime).when(timeProvider).now();

    assertEquals(fixedTime, timeProvider.now());
    verify(timeProvider).now();
}
~~~

Trong ví dụ này, spy được tạo từ một đối tượng thật, nhưng phương thức now() được thay bằng kết quả cố định. Những phương thức khác chưa bị stub vẫn có thể chạy implementation thật.

Khi dùng spy, có một điểm cần chú ý: cú pháp **when(spy.method()).thenReturn(value)** có thể gọi phương thức thật ngay trong lúc thiết lập stub. Nếu phương thức thật có side effect, thực hiện I/O hoặc ném exception, việc thiết lập test có thể gây tác động ngoài ý muốn.

Với spy, thường nên dùng dạng **doReturn(...).when(spy).method(...)** khi cần stub phương thức mà không muốn gọi implementation thật trong lúc thiết lập.

**Rủi ro khi dùng spy**

- Phương thức thật có thể thực hiện side effect như ghi file, gọi mạng hoặc cập nhật trạng thái.
- Test có thể phụ thuộc vào nhiều chi tiết nội bộ của đối tượng.
- Việc stub một phần hành vi có thể làm đối tượng hoạt động theo trạng thái không giống production.
- Spy phức tạp thường là dấu hiệu lớp đang làm quá nhiều việc hoặc có phụ thuộc khó thay thế.

Spy hữu ích khi cần giữ phần lớn hành vi thật và chỉ quan sát hoặc thay thế một phần nhỏ. Nếu phải stub nhiều phương thức trên spy, hãy xem xét tách interface hoặc cộng tác viên để test có ranh giới rõ ràng hơn.

## 6. So sánh nhanh năm khái niệm

| Loại đối tượng | Hành vi chính | Có thực hiện logic thật? | Thường dùng để |
|---|---|---|---|
| Real object | Implementation production | Có | Kiểm tra hành vi thực và tích hợp |
| Fake | Implementation đơn giản thay thế | Có, nhưng đơn giản hóa | Mô phỏng phụ thuộc có trạng thái |
| Stub | Trả phản hồi đã định trước | Thường không thực hiện logic phụ thuộc thật | Điều khiển kịch bản đầu vào |
| Mock | Ghi nhận và xác minh tương tác | Thường không | Kiểm tra lời gọi và side effect |
| Spy | Theo dõi instance có hành vi thật | Có theo mặc định | Quan sát hoặc thay thế một phần hành vi |

Có thể nhớ bằng năm câu hỏi:

- **Real object**: implementation thật hoạt động thế nào?
- **Fake**: một implementation đơn giản có thể đáp ứng hợp đồng cần thiết không?
- **Stub**: nếu phụ thuộc trả về dữ liệu này thì lớp đang kiểm tra phản ứng ra sao?
- **Mock**: lớp đang kiểm tra có thực hiện tương tác cần thiết không?
- **Spy**: có thể giữ hành vi thật nhưng vẫn quan sát hoặc thay một phần lời gọi không?

## 7. Một ví dụ xuyên suốt: OrderService và các loại test double

Giả sử OrderService phụ thuộc vào OrderRepository và PaymentGateway:

~~~java
public class OrderService {

    private final OrderRepository repository;
    private final PaymentGateway paymentGateway;

    public OrderService(
            OrderRepository repository,
            PaymentGateway paymentGateway) {
        this.repository = repository;
        this.paymentGateway = paymentGateway;
    }

    public OrderResult pay(String orderId) {
        Order order = repository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        PaymentResult payment = paymentGateway.charge(order);

        if (payment.approved()) {
            order.markPaid();
        } else {
            order.reject();
        }

        repository.save(order);

        return new OrderResult(order.id(), order.status());
    }
}
~~~

Cùng một hành vi có thể được kiểm tra theo nhiều cách.

### Dùng real object

Khởi động Spring context, dùng repository thật và một PaymentGateway có thể kết nối đến sandbox hoặc dịch vụ kiểm thử. Test xác minh các thành phần thực sự phối hợp. Cách này phù hợp cho integration test, nhưng cần quản lý dữ liệu và môi trường.

### Dùng fake repository

Tạo InMemoryOrderRepository để lưu đơn hàng trong Map. Service có thể tìm, cập nhật và lưu đơn hàng qua các thao tác thật trong bộ nhớ. Cách này phù hợp để kiểm tra logic service mà không cần database.

### Dùng stub payment gateway

Cấu hình PaymentGateway trả về approved hoặc declined. Test kiểm tra OrderService chuyển trạng thái tương ứng. Đây là cách dễ kiểm soát các nhánh nghiệp vụ.

### Dùng mock repository

Dùng **verify(repository).save(...)** để xác minh service lưu đơn hàng sau khi xử lý thanh toán. Có thể xác minh repository không được gọi nếu đơn hàng không tồn tại hoặc đầu vào bị từ chối trước khi thao tác lưu.

### Dùng spy

Nếu có một thành phần thật có hành vi phù hợp nhưng cần quan sát một số lời gọi, có thể tạo spy cho thành phần đó. Chẳng hạn, spy một bộ ghi nhận sự kiện trong bộ nhớ để kiểm tra phương thức publish được gọi, trong khi vẫn giữ hành vi lưu sự kiện thật.

Không cần dùng tất cả năm loại trong cùng một test. Mỗi loại trả lời một câu hỏi khác nhau. Một unit test có thể dùng fake repository và stub payment gateway; một integration test có thể dùng repository thật và stub dịch vụ thanh toán; một test riêng khác có thể kiểm tra tương tác publish bằng mock.

## 8. Dùng Mockito trong unit test

Mockito cung cấp các annotation và API thường gặp:

| API | Ý nghĩa |
|---|---|
| @Mock | Tạo mock |
| @Spy | Tạo spy từ instance hoặc đối tượng được khởi tạo |
| @InjectMocks | Tạo đối tượng cần kiểm tra và cố gắng inject mock/spy phù hợp |
| when(...).thenReturn(...) | Thiết lập phản hồi cho mock |
| doReturn(...).when(...) | Thiết lập phản hồi theo cú pháp phù hợp với spy |
| verify(...) | Xác minh tương tác |
| ArgumentCaptor | Thu thập đối số được truyền vào lời gọi |
| reset(...) | Xóa trạng thái mock; thường nên tránh nếu có thể tạo mock mới cho từng test |

JUnit Jupiter có thể tích hợp Mockito thông qua MockitoExtension:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private OrderRepository repository;

    @Mock
    private PaymentGateway paymentGateway;

    @InjectMocks
    private OrderService service;

    @Test
    void returnsPaidWhenPaymentIsApproved() {
        var order = new Order("order-18", OrderStatus.PENDING);

        when(repository.findById("order-18"))
                .thenReturn(Optional.of(order));

        when(paymentGateway.charge(order))
                .thenReturn(PaymentResult.approved());

        OrderResult result = service.pay("order-18");

        assertEquals(OrderStatus.PAID, result.status());
        verify(repository).save(order);
    }
}
~~~

**@InjectMocks** giúp Mockito tạo OrderService với các phụ thuộc mock phù hợp. Nó không phải dependency injection của Spring và không khởi động ApplicationContext.

Nếu đối tượng cần kiểm tra có constructor rõ ràng và chỉ có một vài phụ thuộc, khởi tạo trực tiếp trong test cũng là lựa chọn tốt. Điều đó làm các phụ thuộc hiện rõ và tránh nhầm lẫn giữa cơ chế inject của Mockito với Spring.

## 9. Dùng mock và spy trong Spring TestContext

Trong unit test thuần, **@Mock** tạo một đối tượng Mockito nhưng không tự đăng ký nó thành bean của Spring. Nếu test khởi động Spring context và cần thay một bean trong context, hãy dùng cơ chế bean override phù hợp.

Với Spring Framework 6.2 trở lên, có thể dùng các annotation trong package **org.springframework.test.context.bean.override.mockito**:

- **@MockitoBean**: tạo mock và đưa mock vào Spring ApplicationContext để thay thế bean phù hợp.
- **@MockitoSpyBean**: tạo spy từ bean hiện có trong ApplicationContext, giữ hành vi thật theo mặc định và cho phép quan sát hoặc stub một phần.

Ví dụ với web slice:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @Test
    void returnsExpectedOrder() throws Exception {
        when(orderService.findById("order-18"))
                .thenReturn(new OrderView("order-18", "PAID"));

        mockMvc.perform(get("/orders/order-18"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("order-18"))
                .andExpect(jsonPath("$.status").value("PAID"));
    }
}
~~~

Controller được Spring tạo trong context, còn OrderService được thay bằng mock. Test có thể kiểm tra hợp đồng HTTP mà không cần chạy logic service và database.

Nếu muốn theo dõi một bean thật trong context, có thể dùng **@MockitoSpyBean** thay vì mock toàn bộ bean. Hãy nhớ rằng phương thức thật vẫn có thể chạy và gây side effect. Chỉ dùng spy khi test thực sự cần giữ hành vi của bean đó.

Ở các phiên bản Spring Boot cũ, dự án có thể đang dùng **@MockBean** hoặc **@SpyBean** của Spring Boot. Những API này đã được đánh dấu deprecated trong các phiên bản Spring Boot mới khi cơ chế bean override của Spring Framework được đưa vào. Hãy dùng annotation tương thích với phiên bản Spring Framework và Spring Boot của dự án.

## 10. Chọn loại đối tượng theo mục tiêu test

Không có một lựa chọn đúng cho mọi tình huống. Hãy bắt đầu từ điều test cần chứng minh:

| Mục tiêu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Kiểm tra logic của lớp thuần Java | Real object cho lớp đang kiểm tra; stub/mock/fake cho phụ thuộc | Giữ trọng tâm ở hành vi cần kiểm tra |
| Kiểm tra nhiều thao tác trên một repository giả lập | Fake | Có trạng thái và hành vi nhất quán |
| Mô phỏng dịch vụ trả lỗi hoặc kết quả đặc biệt | Stub | Dễ thiết lập phản hồi |
| Xác minh message được gửi hoặc repository được gọi lưu | Mock | Kiểm tra tương tác có ý nghĩa |
| Giữ phần lớn hành vi thật nhưng quan sát một số lời gọi | Spy | Cho phép theo dõi implementation thật |
| Kiểm tra SQL, mapping hoặc transaction | Real repository và database kiểm thử | Cần xác minh hạ tầng thật |
| Kiểm tra controller với service được cô lập | @WebMvcTest và @MockitoBean | Nạp lát cắt MVC, thay service bằng mock |

Một số quy tắc thực hành:

- Ưu tiên real object cho lớp đang được kiểm tra.
- Dùng fake khi cần phụ thuộc có trạng thái và hành vi đơn giản.
- Dùng stub khi cần kiểm soát phản hồi của phụ thuộc.
- Dùng mock khi lời gọi hoặc side effect là điều cần xác minh.
- Dùng spy có chọn lọc vì phương thức thật vẫn có thể chạy.
- Dùng integration test với hạ tầng thật khi cần chứng minh tương tác với hạ tầng đó.

## 11. Những lỗi thường gặp khi sử dụng test doubles

### Mock tất cả mọi thứ

Nếu test mock cả lớp đang kiểm tra hoặc mock quá nhiều phụ thuộc, test có thể chỉ xác nhận các mock đã được cấu hình theo đúng kịch bản. Hãy giữ implementation thật của đối tượng đang kiểm tra và thay thế đúng các ranh giới cần cô lập.

### Dùng mock thay cho fake dù cần trạng thái

Một mock repository có thể được cấu hình để trả về từng kết quả, nhưng khi test cần nhiều thao tác lưu rồi tìm, fake trong bộ nhớ thường dễ hiểu hơn. Fake giúp mô phỏng trạng thái một cách nhất quán.

### Xác minh quá nhiều tương tác

Test xác minh từng lời gọi nội bộ có thể bị phá vỡ khi refactor. Hãy chỉ xác minh tương tác thuộc hợp đồng cần bảo vệ, chẳng hạn message phải được gửi sau khi thanh toán thành công.

### Dùng spy để che thiết kế khó kiểm thử

Nếu phải spy một service lớn và stub nhiều phương thức, có thể lớp đó đang có quá nhiều trách nhiệm. Tách các collaborator hoặc interface nhỏ hơn thường giúp test rõ ràng hơn.

### Cho rằng fake chứng minh implementation thật

Fake repository không kiểm tra SQL, database constraint hoặc transaction. Khi các yếu tố đó quan trọng, hãy bổ sung test với repository thật và database phù hợp.

### Stub không khớp hợp đồng thực tế

Một mock có thể trả về dữ liệu mà dịch vụ thật không bao giờ trả về. Điều đó làm test xanh nhưng không phản ánh kịch bản có thể xảy ra. Hãy dùng response đúng kiểu, đúng trạng thái và đúng quy tắc của hợp đồng phụ thuộc.

### Để side effect thật chạy trong spy

Một spy có thể gọi mạng hoặc ghi dữ liệu nếu phương thức thật được thực thi. Hãy kiểm soát các phương thức có side effect, dùng stub có chủ đích hoặc chọn fake/mock phù hợp hơn.

## 12. Cách thiết kế ranh giới để test dễ dàng

Việc chọn đúng test double sẽ dễ hơn khi ứng dụng có các ranh giới phụ thuộc rõ ràng.

Một service nghiệp vụ có thể phụ thuộc vào interface:

~~~java
public interface PaymentGateway {
    PaymentResult charge(Order order);
}

public interface OrderRepository {
    Optional<Order> findById(String id);

    void save(Order order);
}
~~~

Production cung cấp implementation sử dụng HTTP và JPA. Unit test có thể cung cấp stub hoặc fake. Test tương tác có thể dùng mock. Integration test nạp implementation thật trong Spring context và cấu hình hạ tầng kiểm thử.

Cách thiết kế này có một số lợi ích:

- Service không cần biết chi tiết HTTP client hoặc JPA.
- Test có thể thay phụ thuộc mà không sửa logic nghiệp vụ.
- Mỗi test chọn được mức đại diện phù hợp với rủi ro.
- Các hợp đồng giữa thành phần được thể hiện qua interface và dữ liệu đầu vào/đầu ra.

Không nên tạo interface cho mọi class chỉ để dùng mock. Interface có giá trị khi nó biểu diễn một ranh giới có ý nghĩa, chẳng hạn một dịch vụ bên ngoài, kho dữ liệu hoặc một khả năng có thể thay thế. Với một lớp thuần Java nhỏ, khởi tạo đối tượng thật thường đơn giản hơn.

## 13. Checklist trước khi chọn đối tượng thay thế

Trước khi viết test, hãy xác định:

1. Đối tượng nào là đối tượng đang được kiểm tra và nên giữ implementation thật?
2. Phụ thuộc nào cần có trạng thái? Nếu có, fake có giúp test dễ hiểu hơn không?
3. Test cần một phản hồi cố định hay cần xác minh một tương tác?
4. Có cần giữ hành vi thật của một phần phụ thuộc không? Nếu có, spy có thực sự cần thiết?
5. Hành vi nào chỉ có thể được xác nhận bằng implementation và hạ tầng thật?
6. Test có đang xác minh chi tiết nội bộ không thuộc hợp đồng của lớp?
7. Dữ liệu mà fake, stub hoặc mock cung cấp có phù hợp với hợp đồng thực tế không?

Một bộ kiểm thử Spring thường phối hợp nhiều loại đối tượng. Unit test giữ service thật và dùng stub hoặc fake cho phụ thuộc; test tương tác dùng mock khi cần xác nhận side effect; test MVC thay service bean bằng **@MockitoBean**; integration test dùng repository và hạ tầng thật; spy chỉ xuất hiện khi cần quan sát một implementation thật trong phạm vi có kiểm soát.

Việc phân biệt rõ real object, fake, stub, mock và spy giúp mỗi bài test có một mục tiêu cụ thể. Test chạy nhanh hơn khi có thể cô lập phụ thuộc, nhưng vẫn giữ được độ tin cậy khi những ranh giới quan trọng được kiểm tra bằng implementation thật. Hãy chọn đối tượng thay thế theo bằng chứng mà test cần cung cấp, rồi kiểm tra kết quả hoặc tương tác có ý nghĩa đối với hành vi của ứng dụng.

