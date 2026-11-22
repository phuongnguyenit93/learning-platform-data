# Kiểm thử service qua hợp đồng công khai

Trong ứng dụng Spring, service thường là nơi thực hiện quy tắc nghiệp vụ và phối hợp với repository, cổng tích hợp hoặc các service khác. Khi kiểm thử đơn vị một service, hãy gọi các phương thức mà thành phần khác được phép sử dụng và xác nhận kết quả mà những thành phần đó có thể quan sát.

Cách tiếp cận này đặt **hợp đồng công khai của service** làm mục tiêu kiểm thử. Hợp đồng mô tả service nhận đầu vào nào, trả về kết quả gì, từ chối tình huống nào và tạo ra những tác động nghiệp vụ nào. Test tập trung vào các cam kết đó, vì vậy có thể tiếp tục có giá trị khi lập trình viên đổi thuật toán hoặc tổ chức lại các phương thức nội bộ.

## 1. Hợp đồng công khai của service là gì?

Hợp đồng công khai là tập hợp những hành vi mà caller có quyền dựa vào khi gọi service. Nó thường bao gồm:

- **Đầu vào và điều kiện:** tham số nào hợp lệ, trạng thái ban đầu nào được yêu cầu.
- **Kết quả trả về:** kiểu dữ liệu, giá trị và trạng thái được trả về khi xử lý thành công.
- **Lỗi được công bố:** exception hoặc kết quả lỗi mà caller có thể nhận khi điều kiện không được đáp ứng.
- **Tác động nghiệp vụ:** dữ liệu được tạo, cập nhật hoặc xóa; thông điệp được phát; thao tác bên ngoài được yêu cầu.
- **Bất biến:** những quy tắc phải luôn đúng, chẳng hạn tổng tiền không âm hoặc đơn hàng đã thanh toán không thể bị hủy.

Một service có thể có nhiều phương thức public, nhưng không phải mọi chi tiết nhìn thấy được trong code đều là một phần của hợp đồng. Một phương thức public được dùng như helper nội bộ có thể không phải API mà caller được phép dựa vào. Ngược lại, một interface hoặc facade có thể là hợp đồng chính dù phần triển khai nằm trong class khác.

Hãy bắt đầu từ câu hỏi: **Thành phần gọi service được phép kỳ vọng điều gì sau khi gọi phương thức này?**

Ví dụ, thay vì mô tả “OrderService gọi repository.save”, hãy mô tả:

> Khi khách hàng đặt một sản phẩm còn đủ hàng với số lượng hợp lệ, service tạo đơn hàng ở trạng thái PENDING, giữ số lượng hàng tương ứng và trả về mã đơn hàng cùng tổng tiền.

Mô tả này nêu các kết quả có ý nghĩa đối với caller và hệ thống. Nó chưa quy định service phải dùng bao nhiêu private method hoặc phải sắp xếp các phép tính theo thứ tự nào.

## 2. Xác định ranh giới public trước khi viết test

Một service thường được gọi từ controller, một service khác, một message listener hoặc một tác vụ định kỳ. Trong unit test, hãy gọi đúng phương thức mà caller sử dụng.

~~~text
REST Controller
      |
      | gọi public method
      v
  OrderService  <---- Unit test gọi qua public method
      |
      +---- ProductCatalog
      |
      +---- Inventory
      |
      +---- OrderRepository
~~~

Test service không cần gửi HTTP request nếu mục tiêu chỉ là quy tắc nghiệp vụ trong service. HTTP status, JSON, header và mapping request thuộc hợp đồng của controller/API. Service test tập trung vào đầu vào nghiệp vụ, kết quả trả về, exception và các tác động qua collaborator.

Ví dụ:

~~~java
public class OrderService {

    public OrderReceipt placeOrder(
            String customerId,
            String productId,
            int quantity) {
        // Quy tắc nghiệp vụ và phối hợp dependency.
    }

    private BigDecimal calculateTotal(
            BigDecimal unitPrice,
            int quantity) {
        // Chi tiết triển khai nội bộ.
    }
}
~~~

Caller sử dụng placeOrder. Vì vậy, test nên gọi placeOrder và xác nhận tổng tiền hoặc trạng thái trong kết quả. Không cần gọi trực tiếp calculateTotal chỉ vì phương thức đó có một phép tính đáng kiểm tra. Nếu phép tính là quy tắc nghiệp vụ, hãy kiểm tra nó qua kết quả của placeOrder hoặc qua một abstraction nghiệp vụ public có ý nghĩa riêng.

### Public method không đồng nghĩa với mọi chi tiết là hợp đồng

Không nên suy luận rằng một test phải xác nhận mọi lời gọi method public của dependency theo đúng thứ tự hiện tại. Hãy phân biệt:

- Kết quả mà caller nhận được.
- Tác động bên ngoài mà nghiệp vụ cam kết.
- Cách service đang tổ chức các bước để đạt kết quả.

Ví dụ, việc service gọi inventory.reserve(productId, quantity) có ý nghĩa nếu hợp đồng yêu cầu giữ hàng. Việc service gọi một helper tên normalizeProductCode trước hay sau một helper khác thường là chi tiết triển khai, trừ khi thứ tự đó tạo ra khác biệt nghiệp vụ quan sát được.

## 3. Chuyển hợp đồng thành các tình huống kiểm thử

Một cách rõ ràng để xác định test case là mô tả mỗi tình huống theo ba phần:

1. **Given – Điều kiện:** dữ liệu và trạng thái ban đầu.
2. **When – Hành động:** caller gọi public method với đầu vào cụ thể.
3. **Then – Kết quả:** giá trị trả về, lỗi hoặc tác động mà hợp đồng yêu cầu.

Ví dụ với placeOrder:

| Điều kiện | Hành động | Kết quả theo hợp đồng |
|---|---|---|
| Sản phẩm tồn tại, còn đủ hàng, số lượng hợp lệ | Đặt hàng | Trả về mã đơn hàng, tổng tiền; đơn hàng ở trạng thái PENDING; hàng được giữ |
| Số lượng bằng 0 hoặc âm | Đặt hàng | Từ chối đầu vào; không giữ hàng và không tạo đơn |
| Sản phẩm không tồn tại | Đặt hàng | Trả về lỗi sản phẩm không tồn tại; không giữ hàng và không lưu đơn |
| Sản phẩm tồn tại nhưng không đủ hàng | Đặt hàng | Trả về lỗi hết hàng; không lưu đơn |
| Lưu đơn hàng thất bại sau khi giữ hàng | Đặt hàng | Thực hiện chính sách rollback hoặc giải phóng reservation đã được quy định |

Bảng này là ví dụ về hợp đồng giả định. Trong dự án thực tế, hãy lấy quy tắc từ yêu cầu nghiệp vụ hoặc API service đã được thống nhất. Không tự đưa thêm hành vi như “không gọi catalog khi quantity không hợp lệ” nếu đó không phải điều caller hoặc hệ thống cần dựa vào.

Một test nên kiểm tra một kết quả chính. Nếu các đầu vào khác nhau dẫn đến các kết quả khác nhau, hãy tách thành các test riêng để tên test và dữ liệu chuẩn bị nói rõ tình huống.

## 4. Thiết kế service có thể kiểm thử qua collaborator

Service thường phụ thuộc vào repository hoặc các cổng giao tiếp. Trong unit test, có thể thay các collaborator này bằng mock hoặc fake để kiểm soát đầu vào và quan sát những tác động thuộc hợp đồng.

Ví dụ dưới đây sử dụng constructor injection:

~~~java
public class OrderService {

    private final ProductCatalog productCatalog;
    private final Inventory inventory;
    private final OrderRepository orderRepository;

    public OrderService(
            ProductCatalog productCatalog,
            Inventory inventory,
            OrderRepository orderRepository) {
        this.productCatalog = productCatalog;
        this.inventory = inventory;
        this.orderRepository = orderRepository;
    }

    public OrderReceipt placeOrder(
            String customerId,
            String productId,
            int quantity) {

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive");
        }

        Product product = productCatalog.findById(productId)
                .orElseThrow(() ->
                        new ProductNotFoundException(productId));

        boolean reserved = inventory.reserve(productId, quantity);
        if (!reserved) {
            throw new InsufficientStockException(productId);
        }

        BigDecimal total = product.unitPrice()
                .multiply(BigDecimal.valueOf(quantity));

        Order draft = Order.pending(
                customerId, productId, quantity, total);

        Order saved = orderRepository.save(draft);

        return new OrderReceipt(
                saved.id(), saved.status(), saved.total());
    }
}
~~~

Các collaborator thể hiện những ranh giới mà service cần phối hợp:

~~~java
public interface ProductCatalog {
    Optional<Product> findById(String productId);
}

public interface Inventory {
    boolean reserve(String productId, int quantity);
}

public interface OrderRepository {
    Order save(Order order);
}
~~~

Các kiểu Product, Order, OrderReceipt, ProductNotFoundException và InsufficientStockException là kiểu miền nghiệp vụ minh họa. Ví dụ giả định Order.pending(...) tạo một đơn hàng mới ở trạng thái PENDING và Order.withId(...) tạo bản sao có mã định danh do repository trả về.

Constructor injection làm dependency rõ ràng. Unit test có thể tạo OrderService mà không cần khởi động Spring ApplicationContext.

## 5. Viết unit test bằng JUnit Jupiter và Mockito

JUnit Jupiter cung cấp cấu trúc test và assertion. Mockito tạo mock cho collaborator, cấu hình phản hồi và xác nhận những tác động có ý nghĩa.

Với MockitoExtension, test class có thể khai báo mock bằng @Mock và để Mockito tạo service qua @InjectMocks:

~~~java
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private ProductCatalog productCatalog;

    @Mock
    private Inventory inventory;

    @Mock
    private OrderRepository orderRepository;

    @InjectMocks
    private OrderService orderService;

    @Test
    void createsPendingOrderWhenProductHasEnoughStock() {
        Product product = new Product(
                "sku-1", new BigDecimal("12.50"));

        when(productCatalog.findById("sku-1"))
                .thenReturn(Optional.of(product));

        when(inventory.reserve("sku-1", 2))
                .thenReturn(true);

        when(orderRepository.save(any(Order.class)))
                .thenAnswer(invocation -> {
                    Order draft = invocation.getArgument(0);
                    return draft.withId("order-42");
                });

        OrderReceipt receipt = orderService.placeOrder(
                "customer-7", "sku-1", 2);

        assertAll(
                () -> assertEquals("order-42", receipt.orderId()),
                () -> assertEquals(
                        OrderStatus.PENDING, receipt.status()),
                () -> assertEquals(
                        new BigDecimal("25.00"), receipt.total())
        );

        ArgumentCaptor<Order> orderCaptor =
                ArgumentCaptor.forClass(Order.class);

        verify(orderRepository).save(orderCaptor.capture());

        Order savedOrder = orderCaptor.getValue();

        assertAll(
                () -> assertEquals(
                        "customer-7", savedOrder.customerId()),
                () -> assertEquals(
                        "sku-1", savedOrder.productId()),
                () -> assertEquals(2, savedOrder.quantity()),
                () -> assertEquals(
                        new BigDecimal("25.00"), savedOrder.total()),
                () -> assertEquals(
                        OrderStatus.PENDING, savedOrder.status())
        );

        verify(inventory).reserve("sku-1", 2);
    }
}
~~~

Test này xác nhận hai nhóm cam kết:

- Caller nhận được receipt có mã đơn hàng, trạng thái và tổng tiền đúng.
- Service gửi yêu cầu giữ hàng và yêu cầu lưu một đơn hàng mang dữ liệu nghiệp vụ đúng.

ArgumentCaptor giúp kiểm tra đối tượng được truyền qua ranh giới repository. Test không cần biết service dùng private method nào để tính tổng tiền hoặc tạo đối tượng đơn hàng.

thenAnswer mô phỏng repository trả về đối tượng đã có ID. Đây là cách giả lập kết quả của collaborator trong unit test; nó không chứng minh dữ liệu đã được ghi vào database thật.

### Kiểm tra trường hợp đầu vào không hợp lệ

Giả sử hợp đồng quy định số lượng phải là số nguyên dương. Khi đầu vào không hợp lệ, service phải từ chối và không được tạo tác động ghi nhận đơn hàng hoặc giữ hàng.

~~~java
@Test
void rejectsNonPositiveQuantityWithoutReservingOrSaving() {
    assertThrows(
            IllegalArgumentException.class,
            () -> orderService.placeOrder(
                    "customer-7", "sku-1", 0)
    );

    verify(inventory, never())
            .reserve(anyString(), anyInt());

    verify(orderRepository, never())
            .save(any(Order.class));
}
~~~

Các assertion về tác động chỉ nên giữ khi chúng là một phần của hợp đồng. Trong ví dụ, không giữ hàng và không lưu đơn là cam kết có ý nghĩa vì nếu xảy ra, hệ thống có thể tạo ra tác động nghiệp vụ sai dù caller đã nhận lỗi.

Không nhất thiết phải xác nhận mọi collaborator đều không được gọi. Chẳng hạn, việc catalog có được truy vấn trước hay sau bước kiểm tra đầu vào có thể chỉ là cách tổ chức code. Chỉ kiểm tra điều đó nếu yêu cầu thực sự quy định hoặc nếu nó ngăn một tác động đáng kể.

### Kiểm tra trường hợp không đủ hàng

~~~java
@Test
void rejectsOrderWhenInventoryCannotReserveQuantity() {
    Product product = new Product(
            "sku-1", new BigDecimal("12.50"));

    when(productCatalog.findById("sku-1"))
            .thenReturn(Optional.of(product));

    when(inventory.reserve("sku-1", 2))
            .thenReturn(false);

    assertThrows(
            InsufficientStockException.class,
            () -> orderService.placeOrder(
                    "customer-7", "sku-1", 2)
    );

    verify(orderRepository, never())
            .save(any(Order.class));
}
~~~

Test xác nhận service từ chối đơn hàng khi reservation thất bại và không lưu đơn. Nó không kiểm tra thứ tự gọi tất cả các helper nội bộ; chỉ xác nhận tác động quan trọng theo hợp đồng.

### Kiểm tra trường hợp không tìm thấy sản phẩm

~~~java
@Test
void reportsProductNotFoundWhenCatalogHasNoMatchingProduct() {
    when(productCatalog.findById("missing-sku"))
            .thenReturn(Optional.empty());

    assertThrows(
            ProductNotFoundException.class,
            () -> orderService.placeOrder(
                    "customer-7", "missing-sku", 1)
    );

    verify(inventory, never())
            .reserve(anyString(), anyInt());

    verify(orderRepository, never())
            .save(any(Order.class));
}
~~~

Tình huống này làm rõ lỗi mà caller nhận được và bảo đảm service không tiếp tục tạo tác động giữ hàng hoặc lưu đơn khi sản phẩm không tồn tại.

## 6. Nên xác nhận kết quả hay xác nhận tương tác?

Một unit test service có thể cần cả assertion trên kết quả và xác nhận tương tác. Hãy chọn dựa trên ý nghĩa của từng cam kết.

### Xác nhận giá trị trả về

Dùng khi caller dựa vào kết quả mà service trả về:

~~~java
OrderReceipt receipt = orderService.placeOrder(
        "customer-7", "sku-1", 2);

assertEquals("order-42", receipt.orderId());
assertEquals(OrderStatus.PENDING, receipt.status());
~~~

Đây thường là bằng chứng trực tiếp nhất về hợp đồng của public method.

### Xác nhận dữ liệu gửi đến collaborator

Dùng khi dữ liệu được truyền qua ranh giới là một phần của cam kết:

~~~java
ArgumentCaptor<Order> captor =
        ArgumentCaptor.forClass(Order.class);

verify(orderRepository).save(captor.capture());

assertEquals("customer-7", captor.getValue().customerId());
assertEquals(2, captor.getValue().quantity());
~~~

Nếu service phải lưu đơn hàng với đúng khách hàng, sản phẩm và số lượng, kiểm tra đối tượng gửi tới repository giúp xác nhận dữ liệu nghiệp vụ trước khi persistence adapter xử lý.

### Xác nhận một tác động đã hoặc chưa xảy ra

Dùng verify khi tác động đó có ý nghĩa với hệ thống:

~~~java
verify(inventory).reserve("sku-1", 2);
verify(orderRepository, never()).save(any(Order.class));
~~~

Ví dụ, giữ hàng là một cam kết nghiệp vụ; không lưu đơn khi không đủ hàng cũng là cam kết.

### Tránh xác nhận tương tác không có ý nghĩa với caller

Các assertion sau thường làm test phụ thuộc vào cấu trúc nội bộ:

- Một private helper được gọi đúng hai lần.
- Một mapper cụ thể được gọi thay vì cách ánh xạ khác.
- Repository phải được gọi qua một phương thức helper có tên nhất định.
- Các dependency được gọi theo đúng thứ tự hiện tại dù thứ tự không ảnh hưởng đến kết quả.
- Mọi mock phải được gọi hoặc không được gọi chỉ để đạt coverage.

Khi implementation thay đổi nhưng kết quả nghiệp vụ vẫn đúng, các assertion kiểu này có thể khiến test thất bại giả. Hãy giữ những tương tác thuộc hợp đồng tích hợp hoặc cần thiết để chứng minh một tác động có ý nghĩa.

### Khi nào thứ tự tương tác là hợp đồng?

Có những trường hợp thứ tự thực sự quan trọng. Ví dụ, hệ thống phải xác thực quyền trước khi thực hiện thao tác ghi, hoặc phải nhận reservation thành công trước khi tạo đơn hàng. Nếu thứ tự là yêu cầu nghiệp vụ hoặc yêu cầu an toàn, có thể dùng InOrder để xác nhận.

~~~java
InOrder inOrder = inOrder(permissionService, orderRepository);

inOrder.verify(permissionService).checkCanCreateOrder("customer-7");
inOrder.verify(orderRepository).save(any(Order.class));
~~~

Chỉ sử dụng cách này khi thứ tự là cam kết cần bảo đảm. Nếu chỉ là thứ tự tình cờ của code hiện tại, đừng khóa test vào nó.

## 7. Kiểm thử exception như một phần của hợp đồng

Exception là một dạng kết quả mà caller có thể quan sát. Test cần xác nhận đúng loại lỗi hoặc thông tin lỗi nếu chúng thuộc API của service.

~~~java
@Test
void throwsProductNotFoundForUnknownProduct() {
    when(productCatalog.findById("missing-sku"))
            .thenReturn(Optional.empty());

    ProductNotFoundException exception = assertThrows(
            ProductNotFoundException.class,
            () -> orderService.placeOrder(
                    "customer-7", "missing-sku", 1)
    );

    assertEquals("missing-sku", exception.productId());
}
~~~

Nếu exception có mã lỗi, loại lỗi miền nghiệp vụ hoặc thông tin định danh mà caller sử dụng, hãy xác nhận các trường đó. Nếu message chỉ là câu chữ nội bộ không phải hợp đồng, tránh phụ thuộc quá chặt vào toàn bộ chuỗi message.

Một số lưu ý:

- Kiểm tra exception cụ thể nếu caller phân biệt các trường hợp lỗi.
- Không bắt Exception.class quá rộng khi hợp đồng quy định một loại lỗi cụ thể.
- Xác nhận trạng thái không bị thay đổi khi thao tác thất bại nếu đó là cam kết.
- Nếu exception được chuyển đổi thành HTTP status ở controller, hãy kiểm tra phần chuyển đổi trong controller test riêng.

## 8. Mock, stub và fake trong service unit test

Các kỹ thuật test double có mục đích khác nhau:

| Loại test double | Mục đích | Ví dụ |
|---|---|---|
| Stub | Cung cấp câu trả lời đã định trước | Catalog trả về một Product |
| Mock | Cho phép cấu hình và xác nhận tương tác | Inventory được yêu cầu giữ đúng số lượng |
| Fake | Cung cấp triển khai đơn giản có hành vi thực | Repository trong bộ nhớ dùng Map |

Mockito có thể được dùng như stub khi cấu hình when(...).thenReturn(...), và như mock khi cần verify(...). Không phải mọi dependency đều cần mock.

Một fake có thể phù hợp khi service cần tương tác với một collaborator có hành vi đơn giản và việc dùng mock khiến test khó đọc. Ví dụ, một repository giả trong bộ nhớ có thể lưu các đối tượng vào Map và cho phép truy vấn lại. Tuy nhiên, fake chỉ mô phỏng hành vi đã được lập trình; nó không thay thế kiểm thử adapter/database thật.

Hãy chọn test double theo câu hỏi cần trả lời:

- Cần kiểm soát kết quả dependency để đi vào một nhánh? Dùng stub.
- Cần xác nhận tác động tích hợp có ý nghĩa? Dùng mock.
- Cần một collaborator nhỏ hoạt động tự nhiên trong nhiều test? Cân nhắc fake.
- Cần xác nhận truy vấn, mapping, transaction hoặc SQL thực tế? Dùng integration test với adapter/database phù hợp.

## 9. Có cần khởi động Spring ApplicationContext không?

Một class được đánh dấu @Service không có nghĩa mọi test của nó phải dùng @SpringBootTest. Annotation @Service chủ yếu giúp Spring phát hiện và quản lý bean. Nếu mục tiêu là quy tắc trong phương thức service và các dependency có thể truyền qua constructor, có thể tạo service trực tiếp trong unit test.

### Unit test thuần với Mockito

~~~java
@ExtendWith(MockitoExtension.class)
class PricingServiceTest {

    @Mock
    private DiscountPolicy discountPolicy;

    @InjectMocks
    private PricingService pricingService;

    @Test
    void appliesDiscountReturnedByPolicy() {
        when(discountPolicy.discountRateFor("VIP"))
                .thenReturn(new BigDecimal("0.10"));

        BigDecimal total = pricingService.calculate(
                new BigDecimal("100.00"), "VIP");

        assertEquals(new BigDecimal("90.00"), total);
    }
}
~~~

Cách này phù hợp khi cần kiểm tra logic service và phản ứng với collaborator. Nó chạy nhanh, không cần cấu hình database hoặc nạp toàn bộ Spring context.

### Khi nào cần test có Spring context?

Một unit test tạo service bằng constructor không chạy qua Spring container và không tạo proxy. Vì vậy, nó không xác nhận các hành vi do Spring quản lý như:

- Dependency injection và cấu hình bean có thực sự đúng.
- @Transactional được áp dụng qua transaction proxy.
- @Cacheable, @Retryable hoặc các interceptor AOP hoạt động đúng.
- Method validation được kích hoạt thông qua Spring proxy khi dùng @Validated.
- Cấu hình security, event listener hoặc các bean tích hợp được wiring đúng.

Nếu mục tiêu là xác nhận một trong các hành vi đó, hãy viết một bài kiểm thử tích hợp phù hợp với phạm vi cần kiểm tra. Có thể dùng @SpringBootTest cho luồng rộng hoặc cấu hình Spring nhỏ hơn nếu chỉ cần một nhóm bean.

Ví dụ kiểm tra hành vi transaction thường cần database thật hoặc test database phù hợp và transaction manager được cấu hình trong context. Gọi trực tiếp một object new OrderService(...) không thể chứng minh annotation @Transactional đã tạo transaction.

### Phân biệt các phạm vi

| Câu hỏi cần trả lời | Phạm vi kiểm thử phù hợp |
|---|---|
| Quy tắc service trả về kết quả đúng với đầu vào không? | Unit test service |
| Service xử lý đúng khi dependency trả về lỗi không? | Unit test với stub/mock |
| Repository thực sự lưu và truy vấn entity đúng không? | Repository integration test |
| Spring có inject đúng bean và tạo proxy cần thiết không? | Spring context test |
| Transaction, cache hoặc retry có hoạt động qua proxy không? | Spring integration test |
| API ánh xạ kết quả service thành HTTP response đúng không? | MVC/controller test |

Không dùng một bài test duy nhất để tuyên bố đã xác nhận tất cả các tầng. Hãy gắn kết luận với đúng ranh giới mà test quan sát.

## 10. Kiểm thử trạng thái dữ liệu và tác động bên ngoài

Service có thể thay đổi trạng thái thông qua repository, phát domain event, gửi thông điệp hoặc gọi dịch vụ bên ngoài. Những tác động này cần được kiểm tra theo hợp đồng.

### Trạng thái dữ liệu

Nếu unit test mock repository, test có thể kiểm tra đối tượng được gửi tới save, nhưng không thể xác nhận database thực sự ghi đúng. Hãy tách hai câu hỏi:

- Service có tạo yêu cầu lưu đúng dữ liệu không? Unit test với mock hoặc captor phù hợp.
- Persistence adapter có lưu và truy vấn dữ liệu đúng không? Repository integration test phù hợp.

### Domain event và message

Nếu hợp đồng quy định service phát OrderCreated, có thể mock event publisher và xác nhận event chứa mã đơn hàng, khách hàng và trạng thái đúng. Nếu cần xác nhận event thực sự được broker nhận hoặc listener xử lý, cần test tích hợp message infrastructure.

### Dịch vụ bên ngoài

Đối với cổng thanh toán, gửi email hoặc dịch vụ vận chuyển, unit test thường thay adapter bằng mock để kiểm soát kết quả. Test có thể xác nhận service gửi đúng yêu cầu hoặc không gửi khi điều kiện không hợp lệ.

Không gọi dịch vụ production thật trong unit test. Giao tiếp thật nên được kiểm tra trong một bài test tích hợp có môi trường kiểm thử được kiểm soát.

### Xử lý thất bại giữa chừng

Một tình huống đáng quan tâm là service đã thực hiện một tác động rồi bước sau thất bại. Ví dụ, đã giữ hàng nhưng lưu đơn hàng không thành công. Hợp đồng phải quy định cách hệ thống phục hồi:

- Nếu reservation thuộc cùng một transaction có thể rollback, test tích hợp cần xác nhận transaction behavior.
- Nếu reservation là tác động bên ngoài, có thể cần thao tác release/compensation.
- Nếu thao tác được xử lý bất đồng bộ, cần xác định trạng thái trung gian và chính sách retry.

Unit test có thể xác nhận service yêu cầu giải phóng reservation khi repository thất bại nếu đó là logic của service. Tuy nhiên, chỉ test với mock không chứng minh transaction hoặc compensation thực sự thành công ở hệ thống ngoài.

## 11. Tổ chức test để dễ đọc và dễ bảo trì

Một test tốt cho biết rõ điều kiện, hành động và kết quả. Có thể dùng cấu trúc Arrange–Act–Assert hoặc Given–When–Then:

~~~java
@Test
void returnsDiscountedTotalForVipCustomer() {
    // Arrange
    when(discountPolicy.discountRateFor("VIP"))
            .thenReturn(new BigDecimal("0.10"));

    // Act
    BigDecimal total = pricingService.calculate(
            new BigDecimal("100.00"), "VIP");

    // Assert
    assertEquals(new BigDecimal("90.00"), total);
}
~~~

### Đặt tên test theo hành vi

Tên test nên mô tả điều kiện và kết quả:

- createsPendingOrderWhenStockIsAvailable
- rejectsOrderWhenQuantityIsNotPositive
- throwsProductNotFoundWhenCatalogHasNoMatch
- doesNotSaveOrderWhenReservationFails

Tránh tên chung như testPlaceOrder, testSuccess hoặc testError. Tên rõ ràng giúp đọc kết quả test report mà không cần mở code ngay.

### Chuẩn bị dữ liệu gần với test

Nếu mỗi test cần một sản phẩm khác nhau, tạo dữ liệu đó trong test hoặc dùng builder/test data factory có ý nghĩa. Tránh một @BeforeEach chứa nhiều dữ liệu cho tất cả tình huống nhưng mỗi test chỉ dùng một phần nhỏ.

Một helper như aProductWithPrice(...) có thể làm test dễ đọc, miễn là tên helper diễn đạt dữ liệu được tạo và không che giấu hành vi quan trọng.

### Không dùng chung state có thể thay đổi

Mỗi test nên độc lập. Dùng mock do MockitoExtension quản lý hoặc tạo fake mới cho mỗi test. Tránh static mutable field, cache dùng chung hoặc thứ tự test phụ thuộc nhau.

### Giữ assertion có mục đích

Một test có thể có nhiều assertion nếu chúng cùng mô tả một kết quả, ví dụ receipt có ID, trạng thái và tổng tiền. Không cần kiểm tra mọi field nội bộ của object nếu caller không dựa vào chúng.

## 12. Những lỗi thiết kế test thường gặp

### Gọi private method trực tiếp

Private method không phải ranh giới caller sử dụng. Test trực tiếp private method thường buộc phải dùng reflection hoặc thay đổi visibility chỉ để phục vụ test. Hãy gọi public method và xác nhận kết quả nghiệp vụ.

Nếu một private method chứa quy tắc nghiệp vụ lớn đến mức cần test độc lập, có thể đó là dấu hiệu quy tắc ấy nên được tách thành một collaborator/domain object có trách nhiệm rõ ràng. Khi đó, test object mới qua public API của nó.

### Xác nhận quá nhiều lời gọi Mockito

verifyNoMoreInteractions trên mọi mock có thể khiến test thất bại khi implementation thêm một truy vấn hoặc logging collaborator không ảnh hưởng hợp đồng. Chỉ xác nhận các tương tác quan trọng.

### Mock toàn bộ hệ thống

Nếu mock cả dependency có hành vi quan trọng mà không có test khác xác nhận chúng, test service có thể chỉ chứng minh các mock phản hồi theo đúng cách test đã cấu hình. Giữ mock ở ranh giới cần cô lập và có integration test riêng cho adapter thật.

### Dùng @SpringBootTest cho mọi unit test

Khởi động toàn bộ context khiến test chậm và có thể làm lỗi wiring che khuất lỗi logic. Dùng unit test thuần khi chỉ cần kiểm tra service logic. Dùng Spring context khi chính hành vi của container, proxy hoặc cấu hình là điều cần kiểm tra.

### Chỉ kiểm tra exception mà quên tác động phụ

Một test xác nhận service ném exception nhưng không kiểm tra việc giữ hàng, ghi dữ liệu hoặc phát event có thể bỏ sót tác động sai. Nếu hợp đồng quy định thất bại phải không tạo tác động, hãy xác nhận điều đó.

### Kiểm tra chi tiết triển khai thay cho hợp đồng

Nếu test thất bại chỉ vì private helper được đổi tên hoặc service dùng một mapper khác trong khi kết quả vẫn đúng, test đang phụ thuộc quá sâu vào implementation. Chuyển assertion về kết quả hoặc ranh giới collaborator có ý nghĩa.

### Dùng mock để giả lập điều cần kiểm chứng

Nếu mục tiêu là chứng minh JPA mapping, SQL, transaction hoặc Spring proxy hoạt động, mock repository hay mock transaction manager sẽ bỏ qua chính điều cần kiểm tra. Chọn integration test cho phần đó.

## 13. Quy trình thực hành: từ hợp đồng đến test

Có thể thực hiện theo các bước sau:

1. **Đọc yêu cầu nghiệp vụ:** xác định điều caller được phép kỳ vọng từ service.
2. **Chọn public entry point:** xác định method hoặc interface mà caller thực sự sử dụng.
3. **Liệt kê kết quả quan sát:** giá trị trả về, exception, thay đổi trạng thái và tác động qua collaborator.
4. **Chia tình huống:** thành công, đầu vào không hợp lệ, thiếu dữ liệu, từ chối nghiệp vụ và lỗi dependency.
5. **Chọn test double:** stub để điều khiển phản hồi, mock để quan sát tác động thuộc hợp đồng, fake khi cần collaborator đơn giản có hành vi.
6. **Viết test qua public API:** không gọi private helper hoặc truy cập field nội bộ.
7. **Chọn đúng phạm vi:** unit test cho logic service; integration test cho Spring proxy, persistence hoặc giao tiếp thật.
8. **Đọc test như hợp đồng:** người khác có thể hiểu service phải làm gì chỉ từ tên test, dữ liệu chuẩn bị và assertion hay không?

### Ví dụ mô tả hợp đồng trước khi viết test

~~~text
Public method: OrderService.placeOrder(customerId, productId, quantity)

Điều kiện thành công:
- customerId hợp lệ
- product tồn tại
- quantity > 0
- inventory có thể giữ đủ quantity

Kết quả thành công:
- trả về receipt có orderId
- trạng thái đơn hàng là PENDING
- tổng tiền bằng unitPrice * quantity
- yêu cầu inventory giữ đúng số lượng
- gửi đơn hàng cần lưu đến repository

Kết quả thất bại:
- quantity không hợp lệ: IllegalArgumentException
- product không tồn tại: ProductNotFoundException
- không đủ hàng: InsufficientStockException
- không tạo đơn hàng khi reservation thất bại
~~~

Từ mô tả này, test có thể được chia thành các phương thức riêng cho từng kết quả. Khi yêu cầu thay đổi, cập nhật hợp đồng và các tình huống liên quan thay vì sửa assertion theo cấu trúc implementation mới.

## 14. Checklist ngắn khi đọc một service unit test

- Test gọi public method hoặc interface mà caller thực sự sử dụng.
- Tên test nêu điều kiện và kết quả mong đợi.
- Dữ liệu ban đầu thể hiện rõ tình huống nghiệp vụ.
- Assertion xác nhận kết quả caller nhận được.
- Tương tác với collaborator chỉ được kiểm tra khi nó thuộc cam kết hoặc tác động cần bảo vệ.
- Test lỗi xác nhận các tác động không được phép đã không xảy ra.
- Không truy cập private method, private field hoặc phụ thuộc vào thứ tự helper nội bộ.
- Không nhầm mock repository với bằng chứng database đã lưu dữ liệu.
- Dùng Spring context khi cần kiểm tra container, proxy, transaction hoặc cấu hình tích hợp.
- Mỗi test có thể chạy độc lập và không dựa vào thứ tự test khác.

## Kết luận

Kiểm thử service qua hợp đồng công khai nghĩa là gọi service như một caller thực sự và xác nhận những gì caller có quyền kỳ vọng: kết quả trả về, lỗi được công bố, trạng thái nghiệp vụ và tác động tích hợp có ý nghĩa. JUnit Jupiter cùng Mockito giúp kiểm tra các hành vi đó nhanh chóng mà không cần khởi động toàn bộ Spring context. Khi cần xác nhận transaction, proxy, persistence hoặc cấu hình Spring thật, hãy bổ sung integration test ở đúng ranh giới. Cách tổ chức này giữ unit test tập trung vào nghiệp vụ và ít phụ thuộc vào cách triển khai nội bộ.
