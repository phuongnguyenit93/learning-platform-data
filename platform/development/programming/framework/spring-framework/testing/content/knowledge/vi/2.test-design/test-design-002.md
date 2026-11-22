# Cấu trúc chuẩn bị, thực thi và xác nhận

Một bài kiểm thử tốt cần cho người đọc biết ba điều: hệ thống được đặt vào trạng thái nào, hành động nào đang được kiểm tra và bằng chứng nào chứng minh hành vi mong đợi đã xảy ra. Trong Spring Framework Testing, ba phần này thường được tổ chức theo mẫu **Arrange – Act – Assert (AAA)**, tương ứng với **Given – When – Then**:

1. **Chuẩn bị (Arrange/Given):** tạo dữ liệu, cấu hình trạng thái ban đầu và thiết lập các cộng tác viên cần thiết.
2. **Thực thi (Act/When):** gọi hành động thuộc phạm vi kiểm thử.
3. **Xác nhận (Assert/Then):** kiểm tra kết quả quan sát được và những tác động có ý nghĩa đối với hợp đồng của thành phần.

Spring bổ sung một lớp chuẩn bị quan trọng: môi trường kiểm thử có thể cần khởi tạo một phần hoặc toàn bộ `ApplicationContext`, tạo bean, áp dụng cấu hình và kết nối các thành phần. Vì vậy, người viết cần phân biệt **chuẩn bị môi trường Spring** với **chuẩn bị dữ liệu của từng kịch bản**. Khi hai việc này được tổ chức rõ ràng, bài kiểm thử vừa dễ đọc, vừa ít phụ thuộc vào trạng thái ngầm.

## 1. Nhìn toàn bộ cấu trúc của một bài kiểm thử

Một test method thường có hình dạng sau:

~~~java
@Test
void createsOrderWhenRequestIsValid() {
    // Arrange: chuẩn bị trạng thái đầu vào và cộng tác viên.
    CreateOrderCommand command = validCommand();

    // Act: thực hiện đúng hành động đang được kiểm tra.
    Order result = orderService.create(command);

    // Assert: xác nhận kết quả mà người gọi có thể quan sát.
    assertEquals(OrderStatus.CREATED, result.status());
    assertEquals(command.customerId(), result.customerId());
}
~~~

Đây là cấu trúc khái niệm; tên lớp và kiểu dữ liệu trong ví dụ có thể được thay bằng mô hình của ứng dụng. Điều quan trọng là ba phần có ranh giới dễ nhận ra:

- Phần chuẩn bị không gọi hành động chính của kịch bản.
- Phần thực thi không chứa một loạt thao tác kiểm tra hoặc thiết lập dữ liệu.
- Phần xác nhận tập trung vào kết quả và tác động liên quan trực tiếp đến hành vi đang mô tả.

Không phải bài kiểm thử nào cũng chỉ có đúng một câu lệnh ở mỗi phần. Một kịch bản có thể cần nhiều bước chuẩn bị và nhiều assertion. Tuy nhiên, thông thường chỉ nên có **một hành động chính**. Nếu test method thực hiện nhiều hành động độc lập, người đọc khó xác định lỗi thuộc hành vi nào và kết quả nào là trọng tâm.

### AAA và Given – When – Then

Hai cách gọi diễn đạt cùng một cấu trúc:

| AAA | Given – When – Then | Câu hỏi cần trả lời |
|---|---|---|
| Arrange | Given | Điều kiện ban đầu và dữ liệu là gì? |
| Act | When | Người dùng hoặc thành phần đang kiểm thử đã làm gì? |
| Assert | Then | Hành vi quan sát được phải như thế nào? |

AAA thường hữu ích khi tổ chức mã Java. Given – When – Then thường hữu ích khi diễn đạt kịch bản nghiệp vụ hoặc tên test. Có thể kết hợp cả hai: đặt tên test theo kết quả mong đợi, sau đó chia thân hàm thành ba khối AAA.

Ví dụ tên test tốt thường mô tả điều kiện và kết quả:

~~~java
@Test
void rejectsOrderWhenQuantityIsZero() {
    // Arrange
    CreateOrderCommand command = commandWithQuantity(0);

    // Act + Assert
    assertThrows(
        InvalidOrderException.class,
        () -> orderService.create(command)
    );
}
~~~

Trong trường hợp kiểm tra ngoại lệ, hành động và xác nhận thường nằm chung trong biểu thức `assertThrows`, bởi assertion cần thực thi lambda để bắt ngoại lệ. Về mặt ý nghĩa, phần chuẩn bị vẫn tách biệt với phần thực thi và xác nhận.

## 2. Chuẩn bị: tạo đúng điều kiện ban đầu

Phần chuẩn bị quyết định test đang mô tả tình huống nào. Một phần Arrange tốt trả lời được:

- Thành phần nào là đối tượng đang được kiểm thử?
- Nó nhận dữ liệu đầu vào nào?
- Trạng thái ban đầu của hệ thống ra sao?
- Những phụ thuộc nào là thật, giả lập hoặc được thay thế?
- Cấu hình Spring nào cần thiết để chạy kịch bản?

### 2.1. Chuẩn bị dữ liệu rõ ràng và tối thiểu

Chỉ tạo dữ liệu cần thiết cho hành vi đang kiểm tra. Nếu test xác nhận việc tạo đơn hàng, hãy chuẩn bị khách hàng hợp lệ, sản phẩm và số lượng cần thiết. Không nên tạo thêm nhiều đối tượng không liên quan vì chúng làm tăng chi phí đọc và có thể tạo ra nguyên nhân lỗi phụ.

Có thể dùng các hàm tạo dữ liệu có tên thể hiện ý nghĩa:

~~~java
private CreateOrderCommand validCommand() {
    return new CreateOrderCommand("customer-01", "product-01", 2);
}

private CreateOrderCommand commandWithQuantity(int quantity) {
    return new CreateOrderCommand("customer-01", "product-01", quantity);
}
~~~

Tên hàm nên mô tả dữ liệu được tạo, không nên che giấu quá nhiều hành vi. Khi một kịch bản cần một giá trị đặc biệt, hãy thể hiện điểm khác biệt ngay tại test:

~~~java
@Test
void rejectsOrderWhenQuantityIsZero() {
    // Arrange
    CreateOrderCommand command = commandWithQuantity(0);

    // Act + Assert
    assertThrows(
        InvalidOrderException.class,
        () -> orderService.create(command)
    );
}
~~~

Không nên dùng một fixture quá tổng quát với nhiều tham số boolean như `createOrder(true, false, true)`. Người đọc phải mở phần triển khai mới hiểu được trạng thái. Hãy ưu tiên builder hoặc hàm có tên biểu đạt ý nghĩa, chẳng hạn `anOrder().withCancelledStatus().build()`, nếu mô hình dữ liệu có nhiều thuộc tính.

### 2.2. Giữ dữ liệu kiểm thử xác định

Kết quả test cần lặp lại được. Các nguồn gây không xác định thường gặp gồm:

- Thời gian hiện tại được đọc trực tiếp từ hệ thống.
- Số ngẫu nhiên hoặc mã định danh sinh ngẫu nhiên.
- Dữ liệu dùng chung còn sót lại từ test trước.
- Thứ tự thực thi test hoặc thứ tự bản ghi trong cơ sở dữ liệu.
- Dịch vụ bên ngoài thay đổi trạng thái hoặc trả kết quả theo mạng.

Nếu nghiệp vụ phụ thuộc thời gian, có thể đưa `Clock` vào thành phần cần kiểm thử và cung cấp clock cố định trong test. Nếu cần dữ liệu ngẫu nhiên, hãy đặt seed cố định hoặc tạo dữ liệu cụ thể cho kịch bản. Nếu cần truy vấn nhiều bản ghi, hãy sắp xếp theo tiêu chí rõ ràng thay vì dựa vào thứ tự ngầm của cơ sở dữ liệu.

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-01-15T10:00:00Z"),
    ZoneOffset.UTC
);
~~~

Clock cố định giúp test kiểm tra ngày hết hạn, thời điểm tạo hoặc quy tắc thời gian mà không phụ thuộc đồng hồ của máy chạy test.

### 2.3. Chuẩn bị đối tượng đang kiểm thử và các phụ thuộc

Đối tượng đang kiểm thử thường được gọi là **SUT (System Under Test)**. Cần phân biệt SUT với các thành phần cộng tác:

- **Dependency thật:** phù hợp khi mục tiêu là kiểm tra sự phối hợp thực tế giữa các thành phần.
- **Mock:** phù hợp khi cần điều khiển phản hồi hoặc xác nhận một tương tác thuộc hợp đồng.
- **Stub:** cung cấp dữ liệu trả về cố định, không nhất thiết xác nhận tương tác.
- **Fake:** một triển khai đơn giản có hành vi thật ở mức cần thiết, ví dụ kho lưu trữ trong bộ nhớ.

Không nên mock mọi thứ theo thói quen. Nếu kiểm thử một service cùng repository thật trong cơ sở dữ liệu kiểm thử, việc mock repository có thể khiến test không còn kiểm tra được ánh xạ, truy vấn hoặc ranh giới giao dịch. Ngược lại, khi kiểm thử riêng quy tắc của service, một mock cho cổng thanh toán bên ngoài giúp kịch bản không phụ thuộc mạng hoặc tài khoản thật.

Với Mockito, việc chuẩn bị phản hồi có thể được thể hiện như sau:

~~~java
@SpringBootTest
class CheckoutServiceTest {

    @Autowired
    private CheckoutService checkoutService;

    @MockBean
    private PaymentGateway paymentGateway;

    @Test
    void completesCheckoutWhenPaymentIsAccepted() {
        // Arrange
        CheckoutCommand command = validCheckoutCommand();
        given(paymentGateway.charge(any(PaymentRequest.class)))
            .willReturn(PaymentResult.accepted("payment-01"));

        // Act
        CheckoutResult result = checkoutService.checkout(command);

        // Assert
        assertEquals(CheckoutStatus.COMPLETED, result.status());
        then(paymentGateway).should()
            .charge(any(PaymentRequest.class));
    }
}
~~~

Ví dụ giả định ứng dụng có `CheckoutService`, `PaymentGateway` và các kiểu dữ liệu tương ứng. `@MockBean` thay bean `PaymentGateway` trong context bằng mock để Spring vẫn inject phụ thuộc đó vào service. Cách này thích hợp khi test cần Spring wiring thật nhưng muốn cô lập một cổng bên ngoài.

Chỉ xác nhận tương tác khi tương tác đó có ý nghĩa nghiệp vụ hoặc là một phần hợp đồng cần bảo vệ. Nếu kết quả trả về đã đủ chứng minh hành vi, kiểm tra quá nhiều lời gọi nội bộ có thể làm test dễ vỡ khi triển khai được tái cấu trúc.

### 2.4. Chuẩn bị Spring ApplicationContext phù hợp

Spring Test có thể tạo context và inject bean vào test. Chọn phạm vi context theo câu hỏi cần kiểm tra:

| Cách cấu hình | Phạm vi thường dùng | Khi nên chọn |
|---|---|---|
| Không khởi tạo Spring context, tạo đối tượng trực tiếp | Một lớp hoặc một quy tắc độc lập | Logic thuần Java, không cần kiểm tra DI hay cấu hình Spring |
| `@SpringJUnitConfig` | Một context Spring được khai báo có chủ đích | Kiểm tra wiring hoặc cấu hình của một nhóm bean nhỏ |
| `@SpringBootTest` | Context ứng dụng Spring Boot | Kiểm tra phối hợp nhiều bean hoặc hành vi gần với ứng dụng thực |
| `@WebMvcTest` | Phần MVC được chọn | Kiểm tra controller, binding, validation, exception handler và phản hồi HTTP |
| `@DataJpaTest` | Các thành phần JPA/repository | Kiểm tra mapping, truy vấn và hành vi persistence |

Ví dụ context nhỏ:

~~~java
@SpringJUnitConfig(TestConfig.class)
class PricingServiceTest {

    @Autowired
    private PricingService pricingService;

    @Test
    void calculatesPriceUsingConfiguredPolicy() {
        // Arrange, Act, Assert
    }
}
~~~

Ví dụ kiểm thử với toàn bộ ứng dụng:

~~~java
@SpringBootTest
class OrderWorkflowTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrderAndPersistsIt() {
        // Arrange, Act, Assert
    }
}
~~~

`@SpringBootTest` không mặc nhiên là lựa chọn tốt nhất cho mọi test. Khởi tạo context lớn thường chậm hơn, kéo thêm nhiều cấu hình và khiến lỗi có thể xuất phát từ thành phần ngoài phạm vi đang kiểm tra. Dùng context nhỏ giúp test nhanh và làm rõ ranh giới. Dùng context đầy đủ khi chính sự phối hợp của các bean trong ứng dụng là điều cần xác nhận.

Spring TestContext có cơ chế cache `ApplicationContext` giữa các test có cấu hình tương đương. Cache giúp giảm thời gian khởi tạo, nhưng bean singleton trong context có thể giữ trạng thái nếu test tự thay đổi chúng. Vì vậy:

- Tránh lưu trạng thái kịch bản vào bean singleton dùng chung.
- Khôi phục các thay đổi cấu hình hoặc trạng thái mutable nếu test có tạo ra chúng.
- Không giả định mỗi test method luôn nhận một context hoàn toàn mới.
- Chỉ dùng `@DirtiesContext` khi test thực sự làm context không còn dùng an toàn được; annotation này làm mất cache và có thể khiến các test sau phải khởi tạo lại context.

### 2.5. Chọn test slice khi chỉ cần một lớp hạ tầng

Test slice giúp Spring chỉ cấu hình một phần ứng dụng. Ví dụ, `@WebMvcTest` tập trung vào lớp web:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @Test
    void returnsCreatedWhenOrderIsAccepted() throws Exception {
        // Arrange
        given(orderService.create(any(CreateOrderRequest.class)))
            .willReturn(new OrderResponse("order-01"));

        // Act + Assert
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"productId":"product-01","quantity":2}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value("order-01"));
    }
}
~~~

Ví dụ giả định controller nhận JSON và trả một response có trường `id`. `MockMvc` gửi request qua chuỗi xử lý MVC trong môi trường test, vì vậy có thể kiểm tra routing, chuyển đổi JSON, validation, status và response mà không cần mở cổng HTTP thật.

Với repository, `@DataJpaTest` tập trung vào persistence:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void findsCustomerByEmail() {
        // Arrange
        Customer customer = customerRepository.save(
            new Customer("customer@example.test")
        );
        customerRepository.flush();

        // Act
        Optional<Customer> result =
            customerRepository.findByEmail("customer@example.test");

        // Assert
        assertTrue(result.isPresent());
        assertEquals(customer.getId(), result.orElseThrow().getId());
    }
}
~~~

`flush()` đẩy thay đổi xuống database trong phạm vi transaction hiện tại. Điều này hữu ích khi muốn lỗi constraint hoặc câu lệnh SQL xuất hiện ngay tại vị trí có thể xác định, thay vì chỉ xuất hiện muộn khi transaction kết thúc.

### 2.6. Tổ chức setup dùng chung đúng mức

JUnit Jupiter cung cấp `@BeforeEach`, `@AfterEach`, `@BeforeAll` và `@AfterAll`:

- `@BeforeEach`: chuẩn bị phần thực sự giống nhau cho từng test method.
- `@AfterEach`: giải phóng tài nguyên được tạo riêng cho test method.
- `@BeforeAll`: chuẩn bị tài nguyên dùng chung cho cả test class; mặc định method phải là `static`, trừ khi dùng lifecycle `PER_CLASS`.
- `@AfterAll`: giải phóng tài nguyên dùng chung sau test class.

Không nên chuyển toàn bộ Arrange vào `@BeforeEach`. Nếu mỗi test có dữ liệu hoặc trạng thái khác nhau, đặt chúng ngay trong test method để kịch bản tự giải thích được. Setup dùng chung chỉ nên giữ những phần lặp lại thật sự và không làm ẩn điều kiện quan trọng.

~~~java
class DiscountPolicyTest {

    private DiscountPolicy policy;

    @BeforeEach
    void setUp() {
        policy = new DiscountPolicy();
    }

    @Test
    void appliesDiscountForEligibleCustomer() {
        // Dữ liệu riêng của kịch bản được đặt ngay tại đây.
    }

    @Test
    void doesNotApplyDiscountForIneligibleCustomer() {
        // Kịch bản này tự khai báo điều kiện khác biệt.
    }
}
~~~

Với test dùng Spring, không cần tự tạo lại mọi bean trong `@BeforeEach` nếu chúng đã được Spring quản lý. Hãy để dependency injection chịu trách nhiệm wiring, còn test method chịu trách nhiệm chuẩn bị dữ liệu kịch bản.

## 3. Thực thi: gọi đúng hành động đang kiểm tra

Phần Act là điểm chuyển từ trạng thái chuẩn bị sang hành vi cần kiểm tra. Nó nên làm rõ một hành động chính, ví dụ:

- Gọi một method của service.
- Gửi một HTTP request qua `MockMvc`.
- Gọi repository để thực hiện truy vấn.
- Phát một sự kiện hoặc kích hoạt một thao tác có chủ đích.

Ví dụ:

~~~java
// Arrange
CreateOrderCommand command = validCommand();

// Act
Order result = orderService.create(command);

// Assert
assertEquals(OrderStatus.CREATED, result.status());
~~~

Tránh trộn việc tạo dữ liệu, cấu hình mock, gọi nhiều service và xác nhận kết quả vào cùng một khối không có ranh giới. Khi phần Act ngắn và rõ, người đọc có thể nhanh chóng xác định chính xác hành động đã kích hoạt lỗi.

### 3.1. Gọi qua đúng ranh giới cần kiểm thử

Hãy chọn điểm vào tương ứng với mục tiêu:

- Kiểm thử service: gọi public method của service.
- Kiểm thử controller: gửi request qua `MockMvc` hoặc môi trường HTTP phù hợp.
- Kiểm thử repository: gọi method repository thực tế.
- Kiểm thử cấu hình: lấy bean từ context và xác nhận bean hoặc hành vi cấu hình.

Không nên gọi trực tiếp một private method chỉ để kiểm thử một nhánh nội bộ. Hãy kiểm tra hành vi qua API công khai của lớp. Nếu một private method chứa logic phức tạp đến mức cần test độc lập, có thể đó là dấu hiệu logic nên được tách thành một thành phần có trách nhiệm rõ ràng.

### 3.2. Giữ một hành động chính trong mỗi test

Một test có thể thực hiện nhiều bước kỹ thuật để kích hoạt cùng một hành vi, nhưng không nên ghép nhiều tình huống độc lập vào một test method.

Ví dụ khó đọc:

~~~java
@Test
void handlesSeveralOrderScenarios() {
    Order first = orderService.create(validCommand());
    orderService.cancel(first.getId());
    Order second = orderService.create(anotherValidCommand());
    orderService.confirm(second.getId());

    // Nhiều assertion cho các trạng thái khác nhau.
}
~~~

Test này có nhiều hành động và nhiều kết quả. Khi thất bại, khó biết hành vi nào sai. Nên tách thành các test mô tả riêng việc tạo, hủy và xác nhận đơn hàng. Nếu cần kiểm tra toàn bộ luồng nghiệp vụ, hãy đặt tên test theo luồng đó và xác định rõ các bước là một kịch bản tích hợp có chủ đích.

### 3.3. Xử lý hành động bất đồng bộ

Với xử lý bất đồng bộ, phần Act có thể chỉ kích hoạt công việc; kết quả xuất hiện sau đó. Không nên dùng `Thread.sleep()` với một khoảng thời gian tùy ý để chờ, vì test sẽ vừa chậm vừa không ổn định giữa các máy.

Nên đồng bộ theo một tín hiệu có ý nghĩa:

- Chờ `Future` hoặc `CompletableFuture` hoàn tất.
- Dùng latch hoặc cơ chế đồng bộ được thiết kế cho test.
- Dùng thư viện chờ điều kiện như Awaitility nếu dự án đã có.
- Kiểm tra trạng thái cuối qua API quan sát được, với timeout có giới hạn.

Ví dụ ý tưởng với `CompletableFuture`:

~~~java
// Arrange
JobCommand command = validJobCommand();

// Act
CompletableFuture<JobResult> future = jobService.submit(command);

// Assert
JobResult result = future.get(2, TimeUnit.SECONDS);
assertEquals(JobStatus.COMPLETED, result.status());
~~~

Timeout hữu hạn giúp test kết thúc có kiểm soát nếu tác vụ không hoàn thành. Giá trị timeout nên đủ cho môi trường CI dự kiến và không được dùng để che giấu race condition.

## 4. Xác nhận: kiểm tra bằng chứng của hành vi

Assertion là phần trả lời câu hỏi: điều gì chứng minh hành vi đã đúng? Một test có thể chạy hết mà không có assertion vẫn không bảo vệ được hành vi mong đợi. Mỗi test nên có ít nhất một xác nhận có ý nghĩa, ngoại trừ một số test đặc biệt kiểm tra rằng một thao tác không ném ngoại lệ; khi đó cần cân nhắc dùng assertion tường minh để ý định dễ hiểu.

### 4.1. Xác nhận kết quả trả về

Với service hoặc component trả dữ liệu, kiểm tra những thuộc tính liên quan trực tiếp đến yêu cầu:

~~~java
Order result = orderService.create(command);

assertEquals(OrderStatus.CREATED, result.status());
assertEquals(command.customerId(), result.customerId());
assertEquals(command.quantity(), result.quantity());
~~~

Không cần xác nhận mọi field nếu chúng không liên quan đến kịch bản. Quá nhiều assertion không có mục đích rõ ràng làm test khó bảo trì và có thể khiến thay đổi không liên quan làm test thất bại.

### 4.2. Xác nhận trạng thái sau hành động

Với thao tác ghi dữ liệu, chỉ kiểm tra object trả về đôi khi chưa đủ. Nếu mục tiêu là xác nhận dữ liệu được lưu, hãy đọc lại qua ranh giới persistence:

~~~java
// Arrange
CreateOrderCommand command = validCommand();

// Act
Order created = orderService.create(command);

// Assert
Order stored = orderRepository.findById(created.getId())
    .orElseThrow();
assertEquals(OrderStatus.CREATED, stored.getStatus());
~~~

Đây là một kiểm tra phối hợp service và repository. Nếu chỉ muốn kiểm tra quy tắc của service, có thể thay repository bằng mock và xác nhận lời gọi lưu khi lời gọi đó là hợp đồng cần bảo vệ. Hãy chọn cách xác nhận phù hợp với phạm vi test đã chọn.

### 4.3. Xác nhận ngoại lệ và trường hợp lỗi

JUnit Jupiter cung cấp `assertThrows` để kiểm tra ngoại lệ:

~~~java
@Test
void rejectsOrderWhenQuantityIsZero() {
    // Arrange
    CreateOrderCommand command = commandWithQuantity(0);

    // Act
    InvalidOrderException exception = assertThrows(
        InvalidOrderException.class,
        () -> orderService.create(command)
    );

    // Assert
    assertEquals("Quantity must be positive", exception.getMessage());
}
~~~

Chỉ kiểm tra loại ngoại lệ khi đó là hợp đồng cần thiết. Kiểm tra message phù hợp nếu message là nội dung được cam kết cho người gọi; nếu message chỉ là chi tiết nội bộ, ưu tiên mã lỗi hoặc thuộc tính ổn định hơn. Có thể xác nhận thêm rằng thao tác ghi dữ liệu không diễn ra nếu đây là một phần của quy tắc:

~~~java
assertThrows(
    InvalidOrderException.class,
    () -> orderService.create(command)
);

then(orderRepository).shouldHaveNoInteractions();
~~~

Assertion về không có tương tác chỉ nên dùng khi việc không gọi repository là yêu cầu quan trọng. Không nên kiểm tra mọi lời gọi không xảy ra vì điều đó ràng buộc test với cách triển khai.

### 4.4. Xác nhận tương tác với mock

Mockito cho phép xác nhận một dependency đã được gọi:

~~~java
then(paymentGateway).should()
    .charge(argThat(request ->
        request.orderId().equals("order-01")
    ));
~~~

Xác nhận tương tác hữu ích khi:

- Một lệnh gửi ra hệ thống bên ngoài là kết quả quan trọng.
- Cần bảo đảm một thao tác chỉ được gọi khi điều kiện thỏa mãn.
- Cần kiểm tra dữ liệu gửi qua một cổng tích hợp.

Không nên xác nhận tương tác chỉ vì biết implementation hiện tại gọi một method cụ thể. Ví dụ, nếu hợp đồng chỉ yêu cầu trả về tổng tiền chính xác, test nên xác nhận tổng tiền; không cần xác nhận nội bộ service gọi một helper bao nhiêu lần.

### 4.5. Xác nhận HTTP response với MockMvc

Với controller, response HTTP là bằng chứng tự nhiên. Có thể kiểm tra status, header, nội dung JSON và tương tác với service khi cần:

~~~java
mockMvc.perform(post("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"productId":"product-01","quantity":2}
            """))
    .andExpect(status().isCreated())
    .andExpect(header().exists("Location"))
    .andExpect(jsonPath("$.id").isNotEmpty());
~~~

Các assertion nên phản ánh hợp đồng HTTP:

- Status code có đúng với kết quả nghiệp vụ không?
- Header quan trọng, chẳng hạn `Location`, có được thiết lập không?
- JSON có cấu trúc và giá trị cần thiết không?
- Dữ liệu không hợp lệ có được chuyển thành phản hồi lỗi đúng không?

Nếu controller nhận JSON, hãy kiểm tra cả content type và body. Nếu test chỉ gọi method controller trực tiếp, nó bỏ qua nhiều phần của MVC như argument resolver, message converter, validation và exception handler; vì vậy cách đó không thay thế được test MVC khi các phần này nằm trong phạm vi cần kiểm tra.

### 4.6. Dùng assertAll khi có nhiều thuộc tính cùng ý nghĩa

JUnit Jupiter hỗ trợ `assertAll` để chạy một nhóm assertion độc lập và báo tất cả lỗi:

~~~java
assertAll(
    () -> assertEquals(OrderStatus.CREATED, result.status()),
    () -> assertEquals("customer-01", result.customerId()),
    () -> assertEquals(2, result.quantity())
);
~~~

Nên nhóm các assertion cùng mô tả một kết quả. Không nên dùng `assertAll` để gom những hành vi độc lập vốn nên tách thành test riêng.

## 5. Dọn dẹp và cô lập giữa các test

Dọn dẹp thường không phải một phần của AAA, nhưng là điều kiện để các lần chạy không ảnh hưởng lẫn nhau. Trước khi thêm cleanup thủ công, hãy xác định tài nguyên được quản lý bởi ai:

- Spring quản lý vòng đời bean và context.
- Spring Test quản lý transaction test khi test được cấu hình transactional.
- JUnit quản lý vòng đời test instance và callback lifecycle.
- Test chịu trách nhiệm giải phóng tài nguyên tự tạo như file tạm, socket, server hoặc container.

### 5.1. Transaction rollback trong Spring Test

Các test dùng `@Transactional` với Spring Test thường chạy trong transaction do framework quản lý và rollback sau test theo mặc định. `@DataJpaTest` cũng thường có transaction test và rollback mặc định. Điều này giúp dữ liệu của test không tồn tại sang test tiếp theo.

~~~java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository productRepository;

    @Test
    void savesProduct() {
        Product product = productRepository.save(new Product("Keyboard"));
        productRepository.flush();

        assertTrue(productRepository.findById(product.getId()).isPresent());
    }
}
~~~

Không nên hiểu rollback là cơ chế dọn dẹp cho mọi tác động. Các trường hợp sau có thể nằm ngoài transaction test hoặc không được rollback như mong đợi:

- Công việc chạy trên thread khác.
- Tác vụ bất đồng bộ đã được xử lý sau khi transaction test kết thúc.
- Giao dịch được tạo riêng, ví dụ propagation `REQUIRES_NEW`.
- Dữ liệu được ghi sang hệ thống bên ngoài.
- Test dùng `@Commit` hoặc `@Rollback(false)`.

Khi test liên quan đến các trường hợp này, cần có chiến lược cô lập riêng, chẳng hạn dữ liệu có mã định danh duy nhất và thao tác cleanup rõ ràng.

### 5.2. Không phụ thuộc thứ tự chạy

Mỗi test cần tự tạo trạng thái mà nó cần. Không để test B chỉ chạy đúng sau test A vì test A đã tạo dữ liệu hoặc thay đổi bean. Khi chạy riêng từng test, chạy cả class, chạy song song hoặc chạy lại sau một test thất bại, kết quả phải nhất quán.

Một số cách giữ tính độc lập:

- Dùng dữ liệu riêng cho từng test.
- Tránh biến static mutable dùng chung giữa test method.
- Không dựa vào thứ tự bản ghi trả về từ database nếu không có `ORDER BY`.
- Reset mock và trạng thái mutable đúng vòng đời.
- Dùng transaction rollback khi phù hợp.
- Dọn tài nguyên ngoài transaction trong `@AfterEach` hoặc cơ chế quản lý tương ứng.

## 6. Ghép ba phần trong các kiểu test Spring phổ biến

Ba giai đoạn Arrange – Act – Assert không thay đổi giữa các loại test. Điều thay đổi là cách chuẩn bị môi trường và điểm thực thi.

### 6.1. Unit test cho logic độc lập

Khi lớp không cần Spring container, có thể tạo SUT trực tiếp. Test thường nhanh, dễ kiểm soát và không cần annotation Spring:

~~~java
class TaxCalculatorTest {

    private TaxCalculator calculator;

    @BeforeEach
    void setUp() {
        calculator = new TaxCalculator();
    }

    @Test
    void calculatesTaxFromNetAmount() {
        // Arrange
        BigDecimal netAmount = new BigDecimal("100.00");

        // Act
        BigDecimal tax = calculator.calculate(netAmount);

        // Assert
        assertEquals(new BigDecimal("10.00"), tax);
    }
}
~~~

Unit test phù hợp để kiểm tra phép tính, quy tắc xác thực, chuyển đổi dữ liệu hoặc quyết định nghiệp vụ thuần. Không cần dùng `@SpringBootTest` nếu test không kiểm tra Spring.

### 6.2. Integration test cho service và các bean

Khi cần xác nhận Spring inject đúng bean và các thành phần phối hợp, dùng context phù hợp. Có thể thay một phụ thuộc ngoài bằng mock để test không gọi dịch vụ thật:

~~~java
@SpringBootTest
class RegistrationServiceIntegrationTest {

    @Autowired
    private RegistrationService registrationService;

    @MockBean
    private EmailSender emailSender;

    @Test
    void registersUserAndRequestsWelcomeEmail() {
        // Arrange
        RegistrationCommand command = validRegistrationCommand();
        given(emailSender.send(any(EmailMessage.class)))
            .willReturn(SendResult.accepted());

        // Act
        RegistrationResult result = registrationService.register(command);

        // Assert
        assertEquals(RegistrationStatus.REGISTERED, result.status());
        then(emailSender).should()
            .send(any(EmailMessage.class));
    }
}
~~~

Test này kiểm tra service trong Spring context và tương tác với một bean giả lập. Nếu mục tiêu còn bao gồm việc gửi email qua hạ tầng thật, cần một integration test riêng với môi trường email thử nghiệm; mock không chứng minh được cấu hình SMTP hoặc dịch vụ bên ngoài hoạt động.

### 6.3. MVC test cho request và response

`@WebMvcTest` chuẩn bị lớp web và các thành phần MVC liên quan. Service thường được mock để test tập trung vào HTTP contract. Phần Act là request gửi qua `MockMvc`; phần Assert là response.

~~~java
@WebMvcTest(CustomerController.class)
class CustomerControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private CustomerService customerService;

    @Test
    void returnsBadRequestWhenEmailIsInvalid() throws Exception {
        // Arrange: không cần cấu hình service nếu validation chặn request.

        // Act + Assert
        mockMvc.perform(post("/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"email":"invalid"}
                    """))
            .andExpect(status().isBadRequest());
    }
}
~~~

Nếu test validation, cần chắc chắn request đi qua validation thực tế của MVC và DTO có constraint phù hợp. Nếu test service, nên gọi service trực tiếp hoặc qua context service thay vì để test controller gánh cả logic nghiệp vụ.

### 6.4. Repository test cho persistence

`@DataJpaTest` phù hợp khi muốn kiểm tra repository, entity mapping, query và ràng buộc database. Hãy xác nhận kết quả qua repository hoặc database sau khi thực thi, thay vì chỉ kiểm tra object trong bộ nhớ:

~~~java
@DataJpaTest
class AccountRepositoryTest {

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void findsAccountByAccountNumber() {
        // Arrange
        Account account = accountRepository.save(
            new Account("ACC-100")
        );
        accountRepository.flush();

        // Act
        Optional<Account> found =
            accountRepository.findByAccountNumber("ACC-100");

        // Assert
        assertTrue(found.isPresent());
        assertEquals(account.getId(), found.orElseThrow().getId());
    }
}
~~~

Nếu truy vấn phụ thuộc đặc tính của database cụ thể, ví dụ dialect, collation, function hoặc constraint đặc thù, hãy bảo đảm test chạy với loại database tương ứng. Một embedded database có thể không tái hiện đầy đủ hành vi của production database.

## 7. Tổ chức test class để người đọc tìm được kịch bản

Một test class nên có tên thể hiện thành phần hoặc hành vi đang được kiểm tra. Tên test method nên mô tả điều kiện và kết quả. Ví dụ:

~~~java
class OrderServiceTest {

    @Test
    void createsOrderWhenCustomerIsActive() {
        // ...
    }

    @Test
    void rejectsOrderWhenCustomerIsSuspended() {
        // ...
    }

    @Test
    void rejectsOrderWhenQuantityIsNotPositive() {
        // ...
    }
}
~~~

Khi có nhiều kịch bản cùng nhóm, JUnit Jupiter `@Nested` có thể gom chúng theo ngữ cảnh:

~~~java
class OrderServiceTest {

    @Nested
    class WhenCustomerIsActive {

        @Test
        void createsOrderForValidCommand() {
            // ...
        }
    }

    @Nested
    class WhenCustomerIsSuspended {

        @Test
        void rejectsNewOrder() {
            // ...
        }
    }
}
~~~

`@Nested` có thể giúp cấu trúc test dễ đọc hơn, nhưng không cần áp dụng cho mọi class. Nếu chỉ có vài test đơn giản, các method phẳng thường dễ tìm hơn.

Với các trường hợp dữ liệu cùng kiểm tra một quy tắc, `@ParameterizedTest` giúp tránh lặp:

~~~java
@ParameterizedTest
@ValueSource(ints = {0, -1, -10})
void rejectsNonPositiveQuantity(int quantity) {
    // Arrange
    CreateOrderCommand command = commandWithQuantity(quantity);

    // Act + Assert
    assertThrows(
        InvalidOrderException.class,
        () -> orderService.create(command)
    );
}
~~~

Parameterized test phù hợp khi các đầu vào khác nhau cùng kiểm tra một hành vi và có cùng cách xác nhận. Nếu từng trường hợp có ý nghĩa nghiệp vụ hoặc kết quả khác nhau, các test riêng với tên rõ ràng có thể dễ hiểu hơn.

## 8. Những cách tổ chức dễ làm test khó tin cậy

### 8.1. Chuẩn bị quá nhiều dữ liệu

Một test chỉ kiểm tra một quy tắc nhưng tạo nhiều đối tượng không liên quan. Khi dữ liệu fixture phức tạp, người đọc khó biết điều kiện nào thực sự quyết định kết quả. Hãy giữ fixture tối thiểu và nêu rõ điểm khác biệt của kịch bản.

### 8.2. Ẩn điều kiện quan trọng trong setup dùng chung

Nếu `@BeforeEach` âm thầm tạo khách hàng đã xác minh, bật feature flag và cấu hình quyền quản trị, tên test không cho biết điều kiện nào dẫn đến kết quả. Đưa dữ liệu đặc thù về test method hoặc dùng helper có tên diễn đạt chính xác.

### 8.3. Một test thực hiện nhiều hành vi độc lập

Khi một test vừa tạo, sửa, hủy và truy vấn nhiều đối tượng, lỗi đầu tiên có thể che khuất các hành vi còn lại. Tách theo hành vi, trừ khi mục tiêu của test là xác nhận một workflow tích hợp hoàn chỉnh.

### 8.4. Không có assertion có ý nghĩa

Test chỉ gọi method rồi kết thúc không chứng minh được kết quả. Hãy xác nhận giá trị trả về, trạng thái được lưu, phản hồi HTTP, ngoại lệ hoặc tương tác quan trọng.

### 8.5. Mock quá sâu

Nếu mọi dependency đều bị mock, test có thể chỉ xác nhận các mock được gọi theo đúng kịch bản đã tự dựng. Hãy giữ những thành phần thuộc phạm vi cần kiểm tra ở dạng thật và chỉ thay thế ranh giới cần cô lập.

### 8.6. Dùng `@SpringBootTest` cho mọi test

Context lớn khiến vòng phản hồi chậm và lỗi cấu hình khó khoanh vùng. Chỉ dùng full context khi cần xác nhận sự phối hợp ở cấp ứng dụng. Với logic thuần, tạo đối tượng trực tiếp; với MVC hoặc JPA, cân nhắc test slice.

### 8.7. Dựa vào thứ tự hoặc thời gian tùy ý

Test phụ thuộc test khác, dùng `Thread.sleep()` hoặc đọc giờ hệ thống trực tiếp thường dễ thất bại ngẫu nhiên. Hãy tạo trạng thái riêng, dùng clock có thể điều khiển và chờ theo điều kiện có timeout.

### 8.8. Cleanup làm thay đổi kết quả cần xác nhận

Không xóa dữ liệu trước khi assertion đọc lại trạng thái cần kiểm tra. Hãy xác nhận hành vi trước, sau đó mới giải phóng tài nguyên. Với transaction rollback, hiểu rõ phạm vi rollback trước khi bỏ qua cleanup thủ công.

## 9. Cách đọc một test khi có lỗi

Khi test thất bại, đọc theo thứ tự ba phần:

1. **Arrange:** dữ liệu và cấu hình có thật sự tạo ra điều kiện mà tên test mô tả không?
2. **Act:** test có gọi đúng điểm vào và chỉ kích hoạt hành vi dự định không?
3. **Assert:** bằng chứng được kiểm tra có khớp với hợp đồng cần bảo vệ không?

Sau đó xác định loại lỗi:

- **Lỗi chuẩn bị:** context không khởi tạo được, thiếu bean, cấu hình test sai hoặc dữ liệu đầu vào không hợp lệ ngoài dự kiến.
- **Lỗi thực thi:** hành động ném exception không mong muốn, gọi sai dependency hoặc không hoàn thành.
- **Lỗi xác nhận:** hành vi chạy được nhưng kết quả khác mong đợi.
- **Lỗi cô lập:** test chỉ thất bại khi chạy cùng class hoặc toàn bộ suite, thường liên quan trạng thái dùng chung, transaction, thứ tự hoặc tài nguyên ngoài.

Với lỗi khởi tạo context, xem nguyên nhân gốc trong chuỗi exception thay vì chỉ đọc thông báo tổng quát của Spring. Với lỗi persistence, xác định thao tác đã flush chưa và transaction nào đang bao quanh test. Với test bất đồng bộ, kiểm tra tín hiệu hoàn thành và timeout. Với lỗi chỉ xuất hiện khi chạy toàn suite, chạy lại test riêng và kiểm tra dữ liệu hoặc bean state bị chia sẻ.

## 10. Mẫu cấu trúc có thể áp dụng

Với một test method thông thường, có thể bắt đầu từ khung sau:

~~~java
@Test
void describesExpectedBehaviorUnderCondition() {
    // Arrange
    // 1. Tạo dữ liệu đầu vào tối thiểu.
    // 2. Thiết lập trạng thái ban đầu.
    // 3. Cấu hình mock/fake nếu cần.

    // Act
    // Gọi một hành động chính qua API cần kiểm tra.

    // Assert
    // Xác nhận kết quả hoặc tác động quan sát được.
}
~~~

Khi dùng Spring context, phần cấu hình môi trường nằm ở cấp class:

~~~java
@SpringBootTest
class SomeServiceIntegrationTest {

    @Autowired
    private SomeService someService;

    @MockBean
    private ExternalGateway externalGateway;

    @Test
    void performsExpectedBehavior() {
        // Arrange: dữ liệu riêng của kịch bản.
        // Act: gọi someService.
        // Assert: kiểm tra kết quả và tương tác cần thiết.
    }
}
~~~

Trước khi hoàn thiện một test, hãy tự trả lời các câu hỏi thiết kế sau:

- Tên test có mô tả được điều kiện và kết quả mong đợi không?
- Dữ liệu chuẩn bị có tối thiểu, rõ nghĩa và lặp lại được không?
- Phạm vi Spring context có vừa với mục tiêu kiểm tra không?
- Test đang gọi đúng public boundary cần bảo vệ không?
- Assertion có chứng minh hành vi quan sát được không?
- Mock chỉ thay thế những dependency cần cô lập không?
- Test có thể chạy độc lập và không phụ thuộc thứ tự không?
- Transaction hoặc cleanup có xử lý đúng tài nguyên mà test tạo ra không?

## Kết luận

Một test Spring dễ bảo trì bắt đầu bằng điều kiện ban đầu rõ ràng, thực hiện một hành động có chủ đích và kết thúc bằng bằng chứng cụ thể. Spring Test cung cấp nhiều cách chuẩn bị môi trường, từ tạo đối tượng trực tiếp, context nhỏ đến full application context và test slice. Chọn đúng phạm vi giúp test phản hồi nhanh, cô lập đúng ranh giới và kiểm tra được chính xác hành vi mà nó tuyên bố bảo vệ.
