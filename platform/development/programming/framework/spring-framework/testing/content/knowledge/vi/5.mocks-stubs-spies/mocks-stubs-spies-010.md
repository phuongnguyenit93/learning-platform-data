# Tránh xác nhận mọi lời gọi nội bộ làm bài kiểm thử dễ vỡ

Mock, stub và spy giúp kiểm soát các cộng tác viên của một đơn vị khi kiểm thử. Tuy nhiên, việc có thể xác nhận một lời gọi không có nghĩa là nên xác nhận lời gọi đó. Nếu test kiểm tra từng phương thức nội bộ, từng lần gọi helper và toàn bộ thứ tự xử lý, test sẽ phụ thuộc chặt vào cách code được viết ở thời điểm hiện tại.

Khi nhóm phát triển đổi tên phương thức, gộp hai bước tính toán, tách một helper thành bean riêng hoặc thay đổi cách phối hợp các collaborator mà hành vi bên ngoài vẫn giữ nguyên, những test như vậy có thể thất bại dù sản phẩm vẫn hoạt động đúng. Đây là hiện tượng **bài kiểm thử dễ vỡ (brittle test)** do xác nhận quá nhiều chi tiết triển khai.

Mục tiêu của unit test là bảo vệ hành vi và các hợp đồng có ý nghĩa. Hãy xác minh kết quả mà người gọi quan sát được, trạng thái được tạo ra và những tương tác có tác động thực sự ở ranh giới của đơn vị. Chỉ xác nhận lời gọi nội bộ khi chính tương tác đó là một phần của yêu cầu cần bảo vệ.

## 1. Phân biệt hành vi với cách triển khai

Giả sử một service tạo đơn hàng. Người gọi quan tâm đến những điều như:

- Đơn hàng hợp lệ được tạo với tổng tiền chính xác.
- Đơn hàng được lưu với trạng thái phù hợp.
- Thanh toán được yêu cầu đúng số tiền và đúng mã đơn hàng.
- Khi thanh toán bị từ chối, đơn hàng không được đánh dấu đã thanh toán.

Người gọi thường không quan tâm service đã gọi bao nhiêu helper, dùng phương thức nào để tính tổng, hoặc gọi một mapper trước hay sau một hàm tiện ích nếu những khác biệt đó không làm thay đổi hợp đồng.

Ví dụ, service có thể được triển khai theo cách sau:

~~~java
public OrderResult createOrder(CreateOrderCommand command) {
    var cart = cartLoader.load(command.cartId());
    var subtotal = subtotalCalculator.calculate(cart);
    var discount = discountCalculator.calculate(cart, subtotal);
    var total = subtotal.subtract(discount);
    var order = orderMapper.toOrder(command, total);

    orderRepository.save(order);
    eventPublisher.publish(new OrderCreatedEvent(order.getId()));

    return OrderResult.from(order);
}
~~~

Một phiên bản khác có thể gom phần tính giá vào một đối tượng:

~~~java
public OrderResult createOrder(CreateOrderCommand command) {
    var cart = cartLoader.load(command.cartId());
    var quote = pricingService.quote(cart);
    var order = orderFactory.create(command, quote);

    orderRepository.save(order);
    eventPublisher.publish(new OrderCreatedEvent(order.getId()));

    return OrderResult.from(order);
}
~~~

Nếu hai cách triển khai tạo cùng một đơn hàng, lưu cùng trạng thái và phát cùng sự kiện theo hợp đồng, test nghiệp vụ không nên thất bại chỉ vì subtotalCalculator và discountCalculator đã được thay bằng pricingService.

Có thể mô tả sự khác biệt như sau:

~~~text
Kiểm tra hành vi:
Input -> gọi chức năng công khai -> quan sát kết quả/trạng thái/tác động

Kiểm tra chi tiết triển khai:
Input -> xác nhận helper A -> xác nhận helper B -> xác nhận helper C
      -> xác nhận thứ tự từng lời gọi -> kiểm tra kết quả
~~~

Cách thứ hai đôi khi cần thiết, nhưng nếu dùng cho mọi lời gọi thì test trở thành bản sao của cấu trúc code. Khi cấu trúc code thay đổi, test phải sửa theo dù hành vi không đổi.

## 2. Mock, stub và spy có vai trò khác nhau

Các thuật ngữ này thường được dùng cùng nhau nhưng mô tả những mục đích khác nhau.

### Stub: cung cấp câu trả lời đã định trước

Stub giúp test kiểm soát phản hồi của một dependency. Nó trả về dữ liệu hoặc tạo lỗi theo kịch bản để test có thể tập trung vào hành vi của đối tượng đang kiểm tra.

Ví dụ với Mockito:

~~~java
when(inventoryClient.availableQuantity("SKU-1"))
        .thenReturn(10);
~~~

Test đang nói rằng khi service hỏi số lượng tồn của SKU-1, dependency sẽ trả về 10. Việc cấu hình phản hồi không đồng nghĩa phải xác minh lời gọi đó sau khi chạy.

Stub hữu ích khi:

- Cần mô phỏng dữ liệu từ repository hoặc API.
- Cần kiểm tra nhánh thành công và thất bại.
- Cần tạo timeout, exception hoặc kết quả rỗng có thể tái hiện.
- Muốn loại bỏ sự phụ thuộc vào database, mạng hoặc hệ thống bên ngoài.

### Mock: cung cấp câu trả lời và ghi nhận tương tác

Mock thường được cấu hình để trả về giá trị, đồng thời ghi nhận những phương thức được gọi, đối số, số lần gọi và thứ tự tương tác. Test có thể dùng verify để xác nhận một tương tác có xảy ra.

~~~java
when(paymentGateway.charge(any()))
        .thenReturn(PaymentResult.approved("payment-42"));

var result = orderService.createOrder(command);

verify(paymentGateway).charge(any());
~~~

Mock có giá trị khi tương tác là điều cần bảo vệ, chẳng hạn yêu cầu thanh toán phải được gửi đến cổng thanh toán. Nhưng nếu test xác nhận mọi lời gọi mock chỉ vì Mockito cho phép làm vậy, test sẽ bị ràng buộc vào cấu trúc triển khai.

### Spy: bọc một đối tượng thật và theo dõi một phần tương tác

Spy thường bọc một đối tượng thật. Những phương thức không bị stub vẫn thực thi logic thật, còn test có thể theo dõi hoặc thay phản hồi của một số phương thức.

~~~java
var formatter = spy(new InvoiceFormatter());

doReturn("TEST-INVOICE")
        .when(formatter)
        .generateReference(any());
~~~

Spy có thể hữu ích khi cần giữ phần lớn hành vi thật nhưng cô lập một phần khó kiểm soát. Tuy nhiên, spy dễ tạo ra test phụ thuộc vào cách đối tượng tự gọi các phương thức của nó. Nếu một refactor thay đổi lời gọi nội bộ, test spy có thể thất bại dù kết quả công khai vẫn đúng.

### Fake cũng là một lựa chọn

Fake là một implementation đơn giản nhưng hoạt động được, thường dùng trong test thay cho hệ thống thật. Ví dụ, InMemoryOrderRepository có thể lưu object trong một Map để test service mà không cần database.

Fake có thể giữ được hành vi gần với hợp đồng hơn một mock cấu hình quá chi tiết. Nó đặc biệt hữu ích khi nhiều test cần cùng một loại dependency và muốn giảm số lượng kỳ vọng về từng lời gọi.

| Test double | Vai trò chính | Ví dụ |
|---|---|---|
| Stub | Cung cấp phản hồi đã định trước | API tồn kho trả về 10 |
| Mock | Ghi nhận và xác minh tương tác | Cổng thanh toán nhận lệnh charge |
| Spy | Theo dõi đối tượng thật, có thể thay một phần hành vi | Spy formatter và stub phương thức tạo mã |
| Fake | Implementation đơn giản có thể chạy được | Repository lưu dữ liệu trong bộ nhớ |

Trong Mockito, một object mock có thể vừa được stub vừa được verify. Vì vậy, stub và mock cũng có thể chỉ những vai trò của test double trong một test cụ thể, chứ không nhất thiết là các lớp object hoàn toàn khác nhau.

## 3. Vì sao xác nhận mọi lời gọi nội bộ làm test dễ vỡ?

### 3.1. Test phụ thuộc vào cấu trúc hiện tại

Giả sử test xác nhận:

~~~java
verify(cartLoader).load("cart-1");
verify(subtotalCalculator).calculate(cart);
verify(discountCalculator).calculate(cart, subtotal);
verify(orderMapper).toOrder(command, total);
verify(orderRepository).save(any());
verify(eventPublisher).publish(any());
~~~

Test đang bảo vệ sáu lời gọi. Nhưng yêu cầu nghiệp vụ có thể chỉ cần bảo vệ ba điều: đơn hàng có tổng tiền đúng, được lưu và phát sự kiện sau khi tạo thành công.

Nếu nhóm phát triển thay hai calculator bằng PricingService, test sẽ đỏ vì hai tương tác biến mất và một tương tác mới xuất hiện. Kết quả nghiệp vụ vẫn đúng nhưng test buộc phải sửa theo cấu trúc mới.

Một test có giá trị nên cho phép thay đổi cách triển khai miễn là hợp đồng cần bảo vệ vẫn được giữ nguyên.

### 3.2. Test lặp lại code thay vì kiểm tra kết quả

Nếu production code thực hiện:

~~~java
var subtotal = subtotalCalculator.calculate(cart);
var discount = discountCalculator.calculate(cart, subtotal);
var total = subtotal.subtract(discount);
~~~

và test chỉ xác minh lần lượt ba lời gọi trên, test gần như mô tả lại cách code đang chạy. Nó chưa chắc chứng minh tổng tiền cuối cùng được sử dụng đúng khi lưu đơn hàng.

Có thể có tình huống cả ba lời gọi đều xảy ra nhưng service truyền nhầm total vào repository. Test xác minh lời gọi vẫn xanh nếu không kiểm tra đối số có ý nghĩa hoặc kết quả cuối.

Hãy ưu tiên assertion trên kết quả hoặc dữ liệu được lưu. Nếu tương tác là một side effect quan trọng, hãy xác minh đối số của side effect đó.

### 3.3. Refactor an toàn cũng làm test thất bại

Các thay đổi sau có thể giữ nguyên hành vi nhưng làm test xác nhận chi tiết nội bộ thất bại:

- Gộp hai phương thức helper thành một phương thức.
- Tách logic thành một collaborator mới.
- Thay vòng lặp bằng Stream API.
- Tính trước một giá trị thay vì tính ngay trước lúc dùng.
- Thay đổi thứ tự các thao tác độc lập.
- Thay một implementation bằng một implementation tương đương.
- Chuyển xử lý từ service sang domain object.

Nếu test đỏ sau một refactor không đổi hành vi, nhóm phải mất thời gian phân biệt lỗi sản phẩm với lỗi kỳ vọng test. Test quá nhạy với implementation làm giảm sự tự tin khi refactor.

### 3.4. Test có thể buộc code giữ nguyên thiết kế chưa tốt

Khi mỗi lời gọi nội bộ đều được xác nhận, việc tái cấu trúc trở nên tốn kém. Người phát triển có thể ngại tách lớp, đổi tên phương thức hoặc gom trách nhiệm vì phải sửa hàng loạt test.

Test nên bảo vệ yêu cầu ổn định. Nó không nên biến mọi quyết định tổ chức code thành một hợp đồng bất biến.

## 4. Ví dụ: từ test xác nhận mọi helper sang test xác nhận hành vi

Giả sử OrderService nhận một yêu cầu tạo đơn, tính giá và gọi cổng thanh toán. Sau khi thanh toán thành công, service lưu đơn và trả kết quả.

~~~java
public class OrderService {

    private final PricingService pricingService;
    private final PaymentGateway paymentGateway;
    private final OrderRepository orderRepository;

    public OrderService(
            PricingService pricingService,
            PaymentGateway paymentGateway,
            OrderRepository orderRepository
    ) {
        this.pricingService = pricingService;
        this.paymentGateway = paymentGateway;
        this.orderRepository = orderRepository;
    }

    public OrderResult createOrder(CreateOrderCommand command) {
        var quote = pricingService.quote(command.items());

        var payment = paymentGateway.charge(
                new PaymentCommand(command.customerId(), quote.total())
        );

        if (!payment.approved()) {
            return OrderResult.paymentRejected();
        }

        var order = Order.create(command, quote, payment.reference());
        var saved = orderRepository.save(order);

        return OrderResult.created(saved.getId(), saved.total());
    }
}
~~~

Các kiểu dữ liệu là mô hình minh họa; tên constructor và phương thức cần điều chỉnh theo ứng dụng.

### Test dễ vỡ: xác minh mọi lời gọi và thứ tự

~~~java
@ExtendWith(MockitoExtension.class)
class OrderServiceBrittleTest {

    @Mock
    PricingService pricingService;

    @Mock
    PaymentGateway paymentGateway;

    @Mock
    OrderRepository orderRepository;

    @InjectMocks
    OrderService orderService;

    @Test
    void shouldCreateOrder() {
        var command = sampleCommand();
        var quote = new PriceQuote(new BigDecimal("250000"));
        var payment = PaymentResult.approved("PAY-1");

        when(pricingService.quote(command.items())).thenReturn(quote);
        when(paymentGateway.charge(any())).thenReturn(payment);
        when(orderRepository.save(any())).thenAnswer(
                invocation -> invocation.getArgument(0)
        );

        orderService.createOrder(command);

        var order = inOrder(
                pricingService,
                paymentGateway,
                orderRepository
        );

        order.verify(pricingService).quote(command.items());
        order.verify(paymentGateway).charge(any());
        order.verify(orderRepository).save(any());

        verifyNoMoreInteractions(
                pricingService,
                paymentGateway,
                orderRepository
        );
    }
}
~~~

Test này không hoàn toàn vô ích: nó xác nhận một chuỗi tương tác cụ thể. Nhưng nó có những vấn đề:

- Không kiểm tra OrderResult trả về có đúng mã đơn và tổng tiền không.
- Không kiểm tra đối số gửi cho cổng thanh toán có đúng số tiền không.
- Không kiểm tra đơn hàng lưu có trạng thái và dữ liệu đúng không.
- Khẳng định thứ tự mọi collaborator dù một số thứ tự có thể không thuộc yêu cầu.
- verifyNoMoreInteractions khiến việc thêm một lời gọi nội bộ vô hại cũng làm test thất bại.

Nếu sau này service dùng OrderFactory hoặc chuyển một phần logic vào domain object, test phải sửa dù người dùng vẫn nhận được kết quả tương tự.

### Test bền vững hơn: kiểm tra kết quả và hợp đồng side effect

~~~java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    PricingService pricingService;

    @Mock
    PaymentGateway paymentGateway;

    @Mock
    OrderRepository orderRepository;

    @InjectMocks
    OrderService orderService;

    @Test
    void shouldCreateAndPersistOrderAfterApprovedPayment() {
        var command = sampleCommand();
        var quote = new PriceQuote(new BigDecimal("250000"));

        when(pricingService.quote(command.items())).thenReturn(quote);
        when(paymentGateway.charge(any())).thenReturn(
                PaymentResult.approved("PAY-1")
        );
        when(orderRepository.save(any())).thenAnswer(
                invocation -> invocation.getArgument(0)
        );

        var result = orderService.createOrder(command);

        assertEquals(OrderStatus.CREATED, result.status());
        assertEquals(new BigDecimal("250000"), result.total());

        var paymentCaptor = ArgumentCaptor.forClass(PaymentCommand.class);
        verify(paymentGateway).charge(paymentCaptor.capture());
        assertEquals(command.customerId(), paymentCaptor.getValue().customerId());
        assertEquals(
                new BigDecimal("250000"),
                paymentCaptor.getValue().amount()
        );

        var orderCaptor = ArgumentCaptor.forClass(Order.class);
        verify(orderRepository).save(orderCaptor.capture());
        assertEquals(OrderStatus.PAID, orderCaptor.getValue().status());
        assertEquals(
                new BigDecimal("250000"),
                orderCaptor.getValue().total()
        );
    }
}
~~~

Test mới tập trung vào:

- Kết quả service trả về.
- Số tiền và khách hàng được gửi tới cổng thanh toán.
- Đơn hàng được lưu với trạng thái và tổng tiền phù hợp.

Test vẫn xác minh hai tương tác quan trọng: thanh toán và lưu đơn. Những tương tác này nằm ở ranh giới có tác động bên ngoài và thuộc hợp đồng của chức năng. Test không bắt buộc service phải gọi chính xác từng helper nội bộ theo một trình tự cố định.

Trong ví dụ, PricingService được stub để cung cấp báo giá. Test không cần xác minh PricingService được gọi đúng một lần nếu điều đó không phải yêu cầu. Nếu việc không tính giá lại nhiều lần có ý nghĩa về chi phí hoặc tính nhất quán, hãy viết một test riêng cho hợp đồng đó với lý do rõ ràng.

## 5. Khi nào verify một tương tác là hợp lý?

Không phải mọi verify đều xấu. Tương tác cần được xác nhận khi nó có ý nghĩa đối với hành vi quan sát được hoặc hợp đồng của collaborator.

### 5.1. Side effect cần xảy ra

Một số hành vi không thể suy ra chỉ từ giá trị trả về:

- Gửi email hoặc SMS.
- Gọi cổng thanh toán.
- Phát sự kiện sang message broker.
- Gửi lệnh đến hệ thống vận chuyển.
- Ghi audit log bắt buộc.
- Xóa cache sau khi cập nhật dữ liệu.
- Gọi một API bên ngoài để thực hiện nghiệp vụ.

Ví dụ, nếu yêu cầu là sau khi tạo đơn thành công phải phát sự kiện OrderCreated, test có thể xác minh eventPublisher nhận đúng sự kiện:

~~~java
verify(eventPublisher).publishEvent(
        argThat(event ->
                event instanceof OrderCreatedEvent created
                && created.orderId().equals(orderId)
        )
);
~~~

Điều cần bảo vệ là sự kiện đúng được phát ra ở ranh giới công khai của hệ thống. Test không cần xác minh mọi helper đã được gọi để tạo ra event đó.

### 5.2. Số lần gọi là một phần của yêu cầu

Có trường hợp số lần gọi thực sự quan trọng:

- Không được thu tiền hai lần cho cùng một yêu cầu.
- Không gửi email trùng lặp khi retry.
- Chỉ phát một event khi trạng thái chuyển từ PENDING sang PAID.
- Không gọi dịch vụ tính phí nếu đơn hàng không hợp lệ.

Khi đó, xác minh số lần gọi có giá trị:

~~~java
verify(paymentGateway, times(1)).charge(any());
~~~

Tuy nhiên, Mockito mặc định verify một phương thức không tham số times cũng có nghĩa là đúng một lần:

~~~java
verify(paymentGateway).charge(any());
~~~

Hãy dùng times(2), never() hoặc atLeastOnce() khi số lần cụ thể là điều cần thể hiện. Không thêm times(1) chỉ để làm câu lệnh dài hơn.

### 5.3. Thứ tự tương tác có ý nghĩa nghiệp vụ

Một số thứ tự là hợp đồng thật:

- Kiểm tra quyền trước khi đọc dữ liệu nhạy cảm.
- Giữ chỗ hàng tồn trước khi xác nhận đơn.
- Xác nhận thanh toán trước khi đánh dấu đơn đã trả tiền.
- Ghi nhận trạng thái thành công sau khi thao tác bên ngoài hoàn tất.

Nếu thay đổi thứ tự có thể làm nghiệp vụ sai, test có thể dùng InOrder để xác minh đúng phần trình tự đó.

~~~java
InOrder order = inOrder(inventoryService, paymentGateway);

order.verify(inventoryService).reserve(orderId);
order.verify(paymentGateway).charge(any());
~~~

Chỉ xác minh thứ tự giữa những tương tác có quan hệ nhân quả hoặc yêu cầu nghiệp vụ. Đừng dùng InOrder để cố định mọi lời gọi trong phương thức, đặc biệt là những bước độc lập có thể thực hiện theo thứ tự khác.

### 5.4. Không thực hiện tương tác khi điều kiện không thỏa mãn

Ví dụ, đơn hàng không hợp lệ phải bị từ chối trước khi gửi thanh toán:

~~~java
@Test
void shouldNotChargeWhenOrderIsInvalid() {
    when(orderValidator.isValid(any())).thenReturn(false);

    var result = orderService.createOrder(invalidCommand());

    assertEquals(OrderStatus.REJECTED, result.status());
    verifyNoInteractions(paymentGateway);
}
~~~

Ở đây, không gọi cổng thanh toán là một phần quan trọng của yêu cầu. Assertion trên kết quả cùng verifyNoInteractions ở ranh giới thanh toán giúp bảo vệ điều đó.

Hãy giới hạn phạm vi verifyNoInteractions vào collaborator có tác động mà ta cần ngăn chặn. Không nhất thiết yêu cầu mọi mock trong test đều không được gọi.

## 6. Khi nào không nên xác minh lời gọi?

Nên tránh verify khi tương tác chỉ là chi tiết giúp code được tổ chức theo một cách nhất định.

Ví dụ, nếu một service gọi một helper thuần để chuẩn hóa chuỗi, test nghiệp vụ thường chỉ cần kiểm tra chuỗi đầu ra. Việc helper được gọi một hay hai lần không quan trọng nếu không ảnh hưởng đến hành vi.

Các trường hợp thường không cần verify:

- Phương thức private hoặc helper nội bộ của đối tượng đang kiểm tra.
- Getter chỉ đọc giá trị từ object.
- Hàm chuyển đổi thuần không tạo side effect.
- Một collaborator nội bộ chỉ tồn tại để chia nhỏ code.
- Thứ tự các bước độc lập không được quy định bởi nghiệp vụ.
- Một lời gọi mà kết quả đã được kiểm tra đầy đủ qua output hoặc state.
- Tương tác chỉ được xác nhận vì mock đã được tạo sẵn.

Nếu test cần xác minh một phương thức private, thường có thể kiểm tra hành vi thông qua phương thức public gọi nó. Nếu phần logic private quá phức tạp và cần test độc lập, có thể xem xét tách trách nhiệm thành một collaborator có hợp đồng rõ ràng. Việc tách lớp cần phản ánh trách nhiệm thực sự, không nên chỉ để có thể mock từng helper.

## 7. Dùng ArgumentCaptor để kiểm tra dữ liệu có ý nghĩa

Đôi khi điều quan trọng không phải là lời gọi có xảy ra, mà là dữ liệu được truyền qua ranh giới có đúng không.

Ví dụ, một service gửi lệnh thanh toán. Thay vì chỉ viết:

~~~java
verify(paymentGateway).charge(any());
~~~

hãy capture đối số để kiểm tra các trường quan trọng:

~~~java
var captor = ArgumentCaptor.forClass(PaymentCommand.class);

verify(paymentGateway).charge(captor.capture());

var paymentCommand = captor.getValue();

assertEquals("customer-1", paymentCommand.customerId());
assertEquals(new BigDecimal("250000"), paymentCommand.amount());
~~~

Cách này xác minh hợp đồng dữ liệu mà collaborator nhận được.

Không cần capture mọi đối số hoặc kiểm tra mọi trường nếu chúng không liên quan đến hành vi đang bảo vệ. Hãy tập trung vào các giá trị có ý nghĩa nghiệp vụ: customer id, amount, currency, idempotency key, order id hoặc trạng thái.

Nếu đối tượng có equals được định nghĩa theo hợp đồng phù hợp, có thể xác minh trực tiếp:

~~~java
verify(paymentGateway).charge(
        new PaymentCommand(
                "customer-1",
                new BigDecimal("250000")
        )
);
~~~

Nếu object chứa timestamp, random id hoặc trường được sinh tự động, ArgumentCaptor kết hợp assertion có chọn lọc thường dễ đọc hơn.

## 8. Cẩn trọng với verifyNoMoreInteractions

Mockito cung cấp verifyNoMoreInteractions để xác nhận không còn tương tác nào khác chưa được xác minh trên mock.

~~~java
verify(paymentGateway).charge(any());
verifyNoMoreInteractions(paymentGateway);
~~~

Lệnh này có thể hữu ích khi hợp đồng yêu cầu mock chỉ được tương tác theo một tập giới hạn. Nhưng nếu đặt verifyNoMoreInteractions trên mọi mock trong mọi test, test sẽ trở nên rất nhạy với thay đổi implementation.

Ví dụ, service được bổ sung một lời gọi metrics counter hoặc tracing collaborator. Nếu test đang kiểm tra tổng tiền và trạng thái đơn hàng, metrics không phải hành vi mà test cần bảo vệ. verifyNoMoreInteractions có thể làm test đỏ vì một chi tiết phụ được thêm vào.

Một số nguyên tắc:

- Chỉ dùng verifyNoMoreInteractions khi việc không có tương tác bổ sung là một phần của hợp đồng.
- Không dùng nó như một bước mặc định sau mỗi verify.
- Không xác minh mọi mock trong test chỉ để đạt trạng thái "không còn tương tác chưa xác nhận".
- Ưu tiên xác minh các side effect quan trọng và kết quả đầu ra.
- Nếu một collaborator được kỳ vọng không bị gọi, dùng verifyNoInteractions trên đúng collaborator đó.

## 9. Spy có thể làm test phụ thuộc vào lời gọi nội bộ như thế nào?

Spy thường hữu ích để quan sát một object thật, nhưng cũng có nguy cơ tạo ra test dễ vỡ hơn mock ở ranh giới.

Ví dụ:

~~~java
class InvoiceService {

    public Invoice create(Order order) {
        var reference = generateReference(order);
        return new Invoice(reference, order.total());
    }

    String generateReference(Order order) {
        return "INV-" + order.id();
    }
}
~~~

Test dùng spy:

~~~java
@Test
void shouldUseGeneratedReference() {
    var service = spy(new InvoiceService());
    doReturn("INV-TEST").when(service).generateReference(any());

    var invoice = service.create(sampleOrder());

    assertEquals("INV-TEST", invoice.reference());
    verify(service).generateReference(any());
}
~~~

Test này cố định rằng create phải gọi chính phương thức generateReference trên cùng object. Nếu sau này code chuyển sang ReferenceGenerator collaborator hoặc tính reference bằng một cách khác, test có thể thất bại dù invoice vẫn có mã đúng theo hợp đồng.

Một số điểm cần nhớ khi dùng spy:

- Spy thường chạy phương thức thật nếu phương thức chưa được stub.
- Cách viết when(spy.method()).thenReturn(value) có thể gọi phương thức thật ngay trong lúc stubbing.
- Có thể dùng doReturn(value).when(spy).method() để tránh gọi phương thức thật khi thiết lập stub.
- Spy lên đối tượng có side effect có thể vô tình truy cập file, mạng, database hoặc trạng thái thật.
- Verify lời gọi nội bộ trên spy làm test phụ thuộc vào cách object tự triển khai.

Nên ưu tiên mock collaborator ở ranh giới bên ngoài và kiểm tra kết quả public của object đang test. Chỉ dùng spy khi có lý do cụ thể, chẳng hạn cần giữ phần lớn hành vi thật nhưng thay một thao tác khó tái hiện.

Nếu một phương thức nội bộ cần được kiểm tra độc lập, hãy xem xét liệu nó có thực sự là một trách nhiệm riêng. Một collaborator có hợp đồng rõ ràng có thể được kiểm tra riêng bằng unit test mà không cần theo dõi lời gọi private hoặc self-invocation.

## 10. Tránh mock quá sâu trong chuỗi phụ thuộc

Một test có thể mock tất cả các thành phần:

~~~text
OrderService
    |
    +-- Mock CartLoader
    +-- Mock PricingService
    +-- Mock TaxService
    +-- Mock DiscountService
    +-- Mock OrderMapper
    +-- Mock OrderRepository
    +-- Mock EventPublisher
    +-- Mock Clock
~~~

Nếu test chỉ thiết lập và xác minh mọi lời gọi, nó trở thành một mô phỏng lại implementation. Sự thay đổi ở bất kỳ mắt xích nào cũng có thể làm test cần chỉnh sửa.

Hãy xác định ranh giới của unit đang kiểm tra:

- Đối tượng chính là code thật.
- Dependency bên ngoài có thể được thay bằng stub hoặc mock để kiểm soát tác động.
- Logic thuần và collaborator nội bộ đơn giản có thể giữ thật.
- Các side effect ở ranh giới như thanh toán, gửi event hoặc persistence cần được xác minh theo hợp đồng.
- Nếu một dependency phức tạp có thể thay bằng fake có hành vi đơn giản, fake có thể giúp test dễ đọc hơn.

Mock quá sâu còn có thể làm mất giá trị của test: nếu tất cả collaborator đều được cấu hình trả về đúng kết quả mong đợi, test có thể xanh dù sự phối hợp thực tế giữa chúng sai. Những ranh giới quan trọng cần thêm integration test để xác minh thành phần thật phối hợp với nhau.

## 11. Một số ví dụ chọn assertion phù hợp

| Tình huống | Assertion nên ưu tiên | Có cần verify không? |
|---|---|---|
| Hàm tính tổng đơn hàng | So sánh tổng tiền trả về | Không cần verify helper tính từng dòng |
| Service chuyển trạng thái đơn | Kiểm tra trạng thái cuối | Chỉ verify side effect có ý nghĩa |
| Service gọi cổng thanh toán | Kiểm tra kết quả và PaymentCommand | Có, vì đây là side effect |
| Service lưu đơn hàng | Kiểm tra dữ liệu được lưu hoặc đối số save | Có thể verify repository boundary |
| Hàm chuẩn hóa tên | So sánh chuỗi đầu ra | Không cần verify lời gọi nội bộ |
| Gửi event sau khi hoàn tất đơn | Kiểm tra trạng thái và event được phát | Có, vì event là hợp đồng tích hợp |
| Không thu tiền khi đơn không hợp lệ | Kiểm tra trạng thái từ chối | Có thể verifyNoInteractions(paymentGateway) |
| Hai thao tác phải theo thứ tự nghiệp vụ | Kiểm tra kết quả và thứ tự cần thiết | Dùng InOrder cho đúng hai tương tác liên quan |
| Một helper private được gọi | Kiểm tra kết quả public | Không mock/verify private method |

Bảng này là hướng dẫn lựa chọn, không phải luật cứng. Hãy xét điều test cần chứng minh và ranh giới của chức năng.

## 12. Thiết kế test theo Given - When - Then

Cấu trúc Given - When - Then giúp test tập trung vào điều kiện, hành động và kết quả:

~~~java
@Test
void shouldRejectOrderWhenPaymentIsDeclined() {
    // Given
    var command = sampleCommand();
    when(paymentGateway.charge(any()))
            .thenReturn(PaymentResult.declined());

    // When
    var result = orderService.createOrder(command);

    // Then
    assertEquals(OrderStatus.PAYMENT_REJECTED, result.status());
    verify(orderRepository, never()).save(any());
}
~~~

Trong ví dụ này:

- Given thiết lập dữ liệu và phản hồi của dependency.
- When gọi một hành vi công khai của service.
- Then kiểm tra kết quả nghiệp vụ và xác nhận không có side effect lưu đơn.

Không cần thêm verify cho mọi collaborator đã xuất hiện trong Given. Một test nên đọc được như một kịch bản nghiệp vụ ngắn, không phải danh sách kiểm kê lời gọi.

Nên đặt tên test mô tả kết quả hoặc quy tắc:

- shouldRejectOrderWhenPaymentIsDeclined
- shouldNotChargeWhenCartIsEmpty
- shouldPublishOrderCreatedEventAfterSuccessfulPayment
- shouldPreserveOrderTotalWhenDiscountIsZero

Tránh tên chỉ mô tả implementation như shouldCallCalculatorThenMapperThenRepository. Tên test tốt giúp người đọc hiểu hành vi được bảo vệ ngay cả khi code bên trong được tái cấu trúc.

## 13. Thực hành với Spring và Mockito

Trong ứng dụng Spring, unit test thuần có thể dùng MockitoExtension và tạo service trực tiếp:

~~~java
@ExtendWith(MockitoExtension.class)
class NotificationServiceTest {

    @Mock
    private MailGateway mailGateway;

    @Mock
    private WelcomeMessageFactory messageFactory;

    @InjectMocks
    private NotificationService notificationService;

    @Test
    void shouldSendWelcomeMessageToCustomer() {
        var customer = new Customer("c-1", "user@example.test");
        var message = new MailMessage(
                "Welcome",
                "Hello",
                customer.email()
        );

        when(messageFactory.create(customer)).thenReturn(message);

        notificationService.sendWelcome(customer);

        verify(mailGateway).send(message);
    }
}
~~~

Test này stub messageFactory để tạo message xác định, sau đó xác minh side effect gửi email. Nếu service thay đổi cách tạo subject hoặc body nhưng vẫn gửi đúng MailMessage, test không cần biết helper nào đã được gọi.

Khi test Spring MVC slice hoặc context, có thể thay bean ở ranh giới ngoài bằng mock. Trong Spring Boot 3.3, @MockBean là lựa chọn thường dùng:

~~~java
@WebMvcTest(NotificationController.class)
class NotificationControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private NotificationService notificationService;

    @Test
    void shouldReturnAcceptedWhenNotificationIsRequested() throws Exception {
        mockMvc.perform(post("/api/notifications/welcome/c-1"))
                .andExpect(status().isAccepted());

        verify(notificationService).sendWelcome(
                argThat(customer -> customer.id().equals("c-1"))
        );
    }
}
~~~

Ở đây test controller xác minh hợp đồng giữa HTTP endpoint và service. Việc service được gọi là một phần của trách nhiệm controller chuyển yêu cầu sang use case. Test không cần xác minh mọi lời gọi nội bộ bên trong NotificationService; phần đó thuộc test riêng của service.

Hãy tránh dùng mock bean để thay toàn bộ service, repository và mọi thành phần của ứng dụng trong một test rồi gọi test đó là integration test. Khi tất cả thành phần quan trọng đã bị mock, bài test chỉ chứng minh cách một lớp điều phối các mock.

## 14. Checklist ra quyết định trước khi thêm verify

Trước khi thêm một câu verify, hãy tự hỏi:

1. Tương tác này có phải một side effect hoặc hợp đồng mà người gọi quan tâm không?
2. Nếu thay implementation nhưng giữ nguyên kết quả, test có nên tiếp tục xanh không?
3. Tương tác có thể được kiểm tra rõ hơn qua kết quả trả về hoặc trạng thái được lưu không?
4. Đối số hoặc số lần gọi có ý nghĩa nghiệp vụ hay chỉ phản ánh cách code đang được tổ chức?
5. Thứ tự này có bắt buộc bởi nghiệp vụ hay chỉ là thứ tự hiện tại trong phương thức?
6. Nếu xóa verify này, test có còn bảo vệ được yêu cầu quan trọng không?
7. Nếu test thất bại, thông báo lỗi có chỉ ra hành vi sai hay chỉ nói một helper không được gọi?

Nếu tương tác không có ý nghĩa với hợp đồng và kết quả đã được kiểm tra đủ, thường không cần verify. Nếu đó là side effect quan trọng, hãy xác minh đúng loại tương tác, đúng dữ liệu và đúng số lần khi cần.

## 15. Kết luận

Mock, stub và spy là công cụ để kiểm soát dependency và quan sát tương tác. Chúng giúp test đáng tin cậy khi được dùng đúng ranh giới, nhưng có thể làm test dễ vỡ nếu mọi lời gọi nội bộ đều trở thành kỳ vọng.

Hãy bắt đầu từ hành vi công khai và câu hỏi nghiệp vụ. Dùng stub để cung cấp phản hồi có kiểm soát, dùng mock để xác minh side effect hoặc hợp đồng tương tác, và dùng spy một cách thận trọng khi thật sự cần giữ phần lớn hành vi thật. Ưu tiên assertion trên kết quả, trạng thái và dữ liệu đi qua ranh giới. Chỉ kiểm tra số lần hoặc thứ tự khi chúng có ý nghĩa.

Một test tốt cho phép nhóm thay đổi cách triển khai mà vẫn giữ được các yêu cầu cần bảo vệ. Khi test tập trung vào hành vi thay vì từng bước nội bộ, nó trở thành lưới an toàn cho refactor thay vì một rào cản mỗi lần code được cải thiện.

