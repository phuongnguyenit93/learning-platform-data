# Kiểm thử nhánh thành công, lỗi và ngoại lệ

Một phương thức nghiệp vụ thường có nhiều đường thực thi: dữ liệu hợp lệ dẫn đến kết quả thành công, dữ liệu không đáp ứng quy tắc dẫn đến lỗi nghiệp vụ, còn dependency có thể phát sinh ngoại lệ khi truy cập cơ sở dữ liệu hoặc gọi dịch vụ khác. Kiểm thử đơn vị cần xác nhận từng đường thực thi quan trọng tạo ra đúng kết quả và chỉ thực hiện những tương tác được phép.

Trong JUnit Jupiter, `@Test` xác định một trường hợp kiểm thử, assertion xác nhận kết quả và `assertThrows` xác nhận ngoại lệ mong đợi. Mockito giúp thay thế dependency bằng mock, thiết lập kết quả trả về hoặc ngoại lệ, rồi xác nhận các lời gọi xảy ra đúng lúc. Kết hợp các công cụ này giúp kiểm thử tập trung vào hợp đồng của lớp đang xét.

## 1. Phân biệt các đường thực thi

Trước khi viết test, hãy đọc quy tắc của phương thức và liệt kê các nhánh có ý nghĩa. Một phương thức xử lý đơn hàng có thể có các đường sau:

| Đường thực thi | Điều kiện | Kết quả mong đợi |
|---|---|---|
| Thành công | Số lượng hợp lệ, sản phẩm tồn tại và đang bán, còn đủ hàng | Lưu đơn hàng và trả về đơn hàng đã lưu |
| Đầu vào không hợp lệ | Số lượng nhỏ hơn hoặc bằng 0 | Ném lỗi tham số trước khi gọi repository |
| Không tìm thấy tài nguyên | Repository không tìm thấy sản phẩm | Ném lỗi nghiệp vụ, không kiểm tra tồn kho hoặc lưu đơn |
| Trạng thái không cho phép | Sản phẩm đã ngừng bán | Ném lỗi nghiệp vụ, không giữ hàng và không lưu đơn |
| Không đủ tồn kho | Dịch vụ tồn kho từ chối giữ số lượng yêu cầu | Ném lỗi nghiệp vụ, không lưu đơn |
| Dependency gặp lỗi | Repository hoặc dịch vụ tồn kho ném ngoại lệ | Ngoại lệ được xử lý theo hợp đồng của service; không tiếp tục các bước phía sau |

Mỗi hàng trong bảng đại diện cho một hành vi cần bảo vệ. Không nên chỉ có một test thành công và một test thất bại chung chung, vì chúng không cho biết nhánh nào đang được kiểm tra.

### 1.1. Nhánh thành công

Nhánh thành công xác nhận dữ liệu hợp lệ đi qua đúng trình tự và tạo ra kết quả mong đợi. Thường cần kiểm tra:

- Giá trị trả về có đúng nội dung hoặc đúng đối tượng theo hợp đồng.
- Dependency nhận đúng tham số.
- Các thao tác cần thiết được gọi đúng số lần.
- Dữ liệu được truyền đi đã được biến đổi đúng, ví dụ mật khẩu đã mã hóa hoặc số tiền đã tính thuế.
- Không có lời gọi thừa hoặc thao tác ngoài luồng nghiệp vụ.

Không phải test nào cũng cần xác nhận mọi lời gọi nội bộ. Chỉ xác minh tương tác có ý nghĩa với hợp đồng của lớp, đặc biệt là tương tác tạo tác dụng phụ như lưu dữ liệu, gửi thông báo hoặc giữ tài nguyên.

### 1.2. Nhánh lỗi nghiệp vụ

Lỗi nghiệp vụ là kết quả có chủ đích khi điều kiện đầu vào hoặc trạng thái miền không cho phép thao tác. Ví dụ: số lượng không hợp lệ, sản phẩm không tồn tại, tài khoản bị khóa hoặc số dư không đủ.

Với nhánh này, test nên xác nhận loại lỗi, thông tin quan trọng của lỗi và việc các bước tiếp theo không được thực hiện. Ví dụ, nếu sản phẩm không tồn tại thì không được gọi dịch vụ giữ hàng hoặc repository lưu đơn hàng.

### 1.3. Ngoại lệ từ dependency

Ngoại lệ từ dependency biểu thị một sự cố ở thành phần mà lớp đang kiểm thử sử dụng, chẳng hạn kết nối database lỗi hoặc dịch vụ ngoài không phản hồi. Cần xác định rõ service có trách nhiệm:

- Để ngoại lệ truyền lên tầng gọi, giữ nguyên nguyên nhân;
- Chuyển ngoại lệ kỹ thuật thành một ngoại lệ ứng dụng có ý nghĩa;
- Hay thử lại, dùng fallback hoặc thực hiện hành động khôi phục theo chính sách.

Test phải phản ánh chính sách đó. Không nên bắt mọi `RuntimeException` rồi chỉ kiểm tra rằng có lỗi xảy ra; cần xác nhận loại lỗi hoặc nguyên nhân cụ thể để phát hiện trường hợp một lỗi khác bị xử lý nhầm.

## 2. Xác định hợp đồng của service trước khi viết test

Xét một service tạo đơn hàng. Service cần kiểm tra số lượng, tìm sản phẩm, xác nhận sản phẩm đang bán, giữ hàng và lưu đơn. Ví dụ này dùng Java record để giữ dữ liệu đơn giản.

Các kiểu dữ liệu và dependency:

```java
import java.util.Optional;

record Product(String id, boolean active) {
}

record Order(String productId, int quantity) {
}

interface ProductRepository {
    Optional<Product> findById(String productId);
}

interface InventoryService {
    boolean reserve(String productId, int quantity);
}

interface OrderRepository {
    Order save(Order order);
}
```

Các ngoại lệ nghiệp vụ:

```java
class ProductNotFoundException extends RuntimeException {
    ProductNotFoundException(String productId) {
        super("Product not found: " + productId);
    }
}

class ProductUnavailableException extends RuntimeException {
    ProductUnavailableException(String productId) {
        super("Product is unavailable: " + productId);
    }
}

class InsufficientStockException extends RuntimeException {
    InsufficientStockException(String productId, int quantity) {
        super("Insufficient stock for product " + productId
                + ", requested quantity: " + quantity);
    }
}
```

Service thực hiện các nhánh:

```java
class OrderService {

    private final ProductRepository productRepository;
    private final InventoryService inventoryService;
    private final OrderRepository orderRepository;

    OrderService(
            ProductRepository productRepository,
            InventoryService inventoryService,
            OrderRepository orderRepository
    ) {
        this.productRepository = productRepository;
        this.inventoryService = inventoryService;
        this.orderRepository = orderRepository;
    }

    Order placeOrder(String productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        Product product = productRepository.findById(productId)
                .orElseThrow(() -> new ProductNotFoundException(productId));

        if (!product.active()) {
            throw new ProductUnavailableException(productId);
        }

        if (!inventoryService.reserve(productId, quantity)) {
            throw new InsufficientStockException(productId, quantity);
        }

        return orderRepository.save(new Order(productId, quantity));
    }
}
```

Hợp đồng của ví dụ là: số lượng phải dương; sản phẩm phải tồn tại và đang hoạt động; tồn kho phải chấp nhận yêu cầu; chỉ khi mọi điều kiện đều đạt thì đơn hàng mới được lưu. Constructor injection giúp dependency được thể hiện rõ và cho phép tạo service với mock trong unit test mà không cần khởi tạo Spring context.

## 3. Thiết lập JUnit Jupiter và Mockito

Với Spring Boot, dependency `spring-boot-starter-test` thường cung cấp JUnit Jupiter, Mockito và Mockito extension. Nếu dự án Java thuần không dùng Spring Boot, có thể khai báo `junit-jupiter` cùng `mockito-junit-jupiter` trong scope test.

JUnit Jupiter test sử dụng `MockitoExtension`:

```java
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private ProductRepository productRepository;

    @Mock
    private InventoryService inventoryService;

    @Mock
    private OrderRepository orderRepository;

    @InjectMocks
    private OrderService orderService;
}
```

`@Mock` tạo mock cho từng dependency. `@InjectMocks` yêu cầu Mockito tạo `OrderService` và đưa các mock phù hợp vào constructor. `MockitoExtension` khởi tạo và quản lý các annotation Mockito theo vòng đời JUnit Jupiter.

Có thể khởi tạo mock bằng `Mockito.mock(...)` trong `@BeforeEach`, nhưng không nên trộn nhiều cách khởi tạo trong cùng lớp test nếu không có lý do. Chọn một cách rõ ràng để tránh mock bị tạo hai lần hoặc test dùng nhầm instance.

## 4. Kiểm thử nhánh thành công

Khi tất cả điều kiện hợp lệ, service phải trả về kết quả lưu từ repository và gửi đúng dữ liệu đến dependency. Dùng `when(...).thenReturn(...)` để thiết lập phản hồi của mock.

```java
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@Test
void placesOrderWhenProductIsActiveAndStockIsAvailable() {
    Product product = new Product("p-100", true);
    Order savedOrder = new Order("p-100", 3);

    when(productRepository.findById("p-100"))
            .thenReturn(Optional.of(product));
    when(inventoryService.reserve("p-100", 3))
            .thenReturn(true);
    when(orderRepository.save(org.mockito.ArgumentMatchers.any(Order.class)))
            .thenReturn(savedOrder);

    Order result = orderService.placeOrder("p-100", 3);

    assertThat(result).isSameAs(savedOrder);

    ArgumentCaptor<Order> orderCaptor = ArgumentCaptor.forClass(Order.class);
    verify(orderRepository).save(orderCaptor.capture());
    assertThat(orderCaptor.getValue())
            .isEqualTo(new Order("p-100", 3));

    verify(productRepository).findById("p-100");
    verify(inventoryService).reserve("p-100", 3);
}
```

`ArgumentCaptor` giúp kiểm tra đối tượng được gửi vào repository. Chỉ kiểm tra `save()` đã được gọi chưa sẽ không phát hiện trường hợp service lưu sai `productId` hoặc `quantity`.

`assertThat(result).isSameAs(savedOrder)` phù hợp với ví dụ vì service trả về trực tiếp đối tượng mà repository trả về. Nếu hợp đồng chỉ yêu cầu giá trị tương đương, nên dùng `isEqualTo(...)` và kiểm tra các trường quan trọng. Chọn assertion theo ý nghĩa của API, không theo cách triển khai tình cờ.

Một số dự án có thể dùng `@Captor` thay vì tạo captor ngay trong test. Điều quan trọng là captor chỉ được dùng khi cần kiểm tra đối số; nếu đã có thể xác nhận kết quả bằng assertion trực tiếp, không cần thêm captor cho mọi lời gọi.

## 5. Kiểm thử nhánh đầu vào không hợp lệ

Với `quantity <= 0`, service phải ném `IllegalArgumentException` ngay lập tức. Vì điều kiện này được kiểm tra trước khi truy cập repository, test nên xác nhận không dependency nào được gọi.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void rejectsZeroQuantityBeforeCallingDependencies() {
    IllegalArgumentException exception = assertThrows(
            IllegalArgumentException.class,
            () -> orderService.placeOrder("p-100", 0)
    );

    assertThat(exception).hasMessage("quantity must be positive");
    verifyNoInteractions(productRepository, inventoryService, orderRepository);
}
```

`assertThrows` trả về ngoại lệ thực tế để có thể kiểm tra message hoặc thuộc tính bổ sung. Nó cũng chấp nhận ngoại lệ thuộc lớp con của kiểu được chỉ định. Nếu hợp đồng yêu cầu chính xác một lớp ngoại lệ, JUnit Jupiter có `assertThrowsExactly` ở các phiên bản hỗ trợ API đó.

Nên kiểm tra thêm trường hợp số lượng âm nếu đó là một giá trị đại diện có ý nghĩa riêng. Nếu cả 0 và số âm đều phải đi qua cùng một điều kiện và cùng loại lỗi, có thể dùng parameterized test để tránh lặp lại mã.

```java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

@ParameterizedTest
@ValueSource(ints = {0, -1, -100})
void rejectsNonPositiveQuantity(int quantity) {
    assertThrows(
            IllegalArgumentException.class,
            () -> orderService.placeOrder("p-100", quantity)
    );

    verifyNoInteractions(productRepository, inventoryService, orderRepository);
}
```

Parameterized test phù hợp khi nhiều dữ liệu kiểm tra cùng một quy tắc và có cùng kết quả mong đợi. Nếu mỗi giá trị cần một thông điệp, trạng thái hoặc hành vi khác nhau, các test riêng thường dễ đọc hơn.

## 6. Kiểm thử từng nhánh lỗi nghiệp vụ

### 6.1. Sản phẩm không tồn tại

Repository trả về `Optional.empty()`, service phải ném `ProductNotFoundException`. Các bước giữ hàng và lưu đơn không được chạy.

```java
@Test
void throwsWhenProductDoesNotExist() {
    when(productRepository.findById("missing"))
            .thenReturn(Optional.empty());

    ProductNotFoundException exception = assertThrows(
            ProductNotFoundException.class,
            () -> orderService.placeOrder("missing", 2)
    );

    assertThat(exception).hasMessage("Product not found: missing");
    verify(productRepository).findById("missing");
    verifyNoInteractions(inventoryService, orderRepository);
}
```

Test này xác nhận cả kết quả lỗi và thứ tự nghiệp vụ quan trọng: không thể giữ hàng cho sản phẩm không tồn tại.

### 6.2. Sản phẩm đã ngừng bán

Sản phẩm có tồn tại nhưng `active` bằng `false`. Đây là nhánh khác với không tìm thấy sản phẩm và cần có test riêng.

```java
@Test
void throwsWhenProductIsInactive() {
    when(productRepository.findById("p-100"))
            .thenReturn(Optional.of(new Product("p-100", false)));

    ProductUnavailableException exception = assertThrows(
            ProductUnavailableException.class,
            () -> orderService.placeOrder("p-100", 2)
    );

    assertThat(exception).hasMessage("Product is unavailable: p-100");
    verify(productRepository).findById("p-100");
    verifyNoInteractions(inventoryService, orderRepository);
}
```

Nếu chỉ kiểm tra trường hợp `Optional.empty()`, nhánh `!product.active()` vẫn chưa được xác nhận. Mỗi điều kiện rẽ nhánh có ý nghĩa cần có dữ liệu khiến điều kiện đó đúng và sai, hoặc được bao phủ bởi một bộ test tương đương có thể giải thích được.

### 6.3. Không đủ tồn kho

Khi sản phẩm hợp lệ nhưng `reserve(...)` trả về `false`, service phải ném `InsufficientStockException` và không lưu đơn hàng.

```java
@Test
void throwsWhenInventoryCannotReserveRequestedQuantity() {
    when(productRepository.findById("p-100"))
            .thenReturn(Optional.of(new Product("p-100", true)));
    when(inventoryService.reserve("p-100", 5))
            .thenReturn(false);

    InsufficientStockException exception = assertThrows(
            InsufficientStockException.class,
            () -> orderService.placeOrder("p-100", 5)
    );

    assertThat(exception)
            .hasMessage("Insufficient stock for product p-100, requested quantity: 5");
    verify(inventoryService).reserve("p-100", 5);
    verifyNoInteractions(orderRepository);
}
```

Đây là ví dụ về việc xác nhận tác dụng phụ bị chặn: repository lưu đơn không được gọi khi tồn kho từ chối yêu cầu. Nếu hệ thống có cơ chế giữ hàng hoặc hoàn tác phức tạp hơn, test cần xác nhận đúng hợp đồng giữ/nhả hàng tương ứng.

## 7. Kiểm thử ngoại lệ phát sinh từ dependency

Lỗi nghiệp vụ do service chủ động ném ra khác với ngoại lệ kỹ thuật từ dependency. Trong ví dụ này, nếu repository không thể truy vấn dữ liệu, service không có chính sách chuyển đổi lỗi nên ngoại lệ cần truyền lên tầng gọi.

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void propagatesRepositoryFailureAndStopsProcessing() {
    IllegalStateException databaseFailure =
            new IllegalStateException("database unavailable");

    when(productRepository.findById("p-100"))
            .thenThrow(databaseFailure);

    assertThatThrownBy(() -> orderService.placeOrder("p-100", 2))
            .isSameAs(databaseFailure);

    verifyNoInteractions(inventoryService, orderRepository);
}
```

`isSameAs(databaseFailure)` xác nhận service truyền lại đúng ngoại lệ đã nhận. Nếu service được thiết kế để bọc lỗi thành `OrderProcessingException`, assertion phải kiểm tra lớp ngoại lệ mới và nguyên nhân gốc bằng `hasCause(...)` hoặc `getCause()`.

Có thể kiểm tra lỗi từ dịch vụ tồn kho tương tự:

```java
@Test
void propagatesInventoryFailureWithoutSavingOrder() {
    when(productRepository.findById("p-100"))
            .thenReturn(Optional.of(new Product("p-100", true)));

    IllegalStateException inventoryFailure =
            new IllegalStateException("inventory service unavailable");
    when(inventoryService.reserve("p-100", 2))
            .thenThrow(inventoryFailure);

    assertThatThrownBy(() -> orderService.placeOrder("p-100", 2))
            .isSameAs(inventoryFailure);

    verifyNoInteractions(orderRepository);
}
```

Không nên dùng `thenThrow(new RuntimeException())` cho mọi dependency lỗi nếu ứng dụng phân biệt timeout, lỗi kết nối, lỗi xác thực hoặc lỗi nghiệp vụ. Hãy dùng kiểu ngoại lệ mà dependency thực tế phát ra hoặc một ngoại lệ đại diện trong test, để chính sách xử lý có thể được kiểm tra rõ ràng.

### 7.1. Ngoại lệ của phương thức `void`

Mockito dùng `doThrow(...)` để thiết lập ngoại lệ cho phương thức `void`:

```java
doThrow(new IllegalStateException("notification unavailable"))
        .when(notificationService)
        .sendOrderCreated("order-1");
```

Sau đó gọi phương thức đang kiểm thử và xác nhận kết quả theo hợp đồng. Với phương thức trả về giá trị, có thể dùng `when(...).thenThrow(...)` như các ví dụ trước.

### 7.2. Checked exception và unchecked exception

Nếu dependency khai báo checked exception, test cần xử lý nó đúng chữ ký phương thức. Ví dụ, phương thức có thể khai báo `throws IOException`, và lambda truyền vào `assertThrows(IOException.class, ...)` có thể thực thi lời gọi đó trong test method thích hợp.

Không nên chuyển checked exception thành `RuntimeException` trong test chỉ để bỏ qua chữ ký. Hãy kiểm tra đúng loại ngoại lệ mà hợp đồng công khai yêu cầu. Nếu lớp đang kiểm thử chuyển đổi ngoại lệ, xác nhận cả ngoại lệ đích lẫn cause để không làm mất thông tin chẩn đoán.

## 8. Xác nhận tương tác và tác dụng phụ

Assertion về giá trị trả về cho biết phương thức đã tạo ra kết quả gì. Mockito verification cho biết phương thức đã tương tác với dependency ra sao. Hai loại kiểm tra bổ sung cho nhau.

| Mockito API | Mục đích | Ví dụ |
|---|---|---|
| `verify(mock).method(...)` | Xác nhận lời gọi xảy ra một lần | `verify(orderRepository).save(any())` |
| `verify(mock, times(2))` | Xác nhận số lần gọi cụ thể | Một thao tác được gọi hai lần theo hợp đồng |
| `verify(mock, never())` | Xác nhận phương thức không được gọi | Không lưu đơn khi hết hàng |
| `verifyNoInteractions(mock)` | Xác nhận mock hoàn toàn không được tương tác | Không gọi dependency khi đầu vào sai ngay từ đầu |
| `verifyNoMoreInteractions(mock)` | Xác nhận không còn tương tác ngoài các lời gọi đã verify | Chỉ dùng khi các tương tác còn lại thực sự thuộc hợp đồng cần khóa |
| `ArgumentCaptor<T>` | Bắt đối số đã truyền để kiểm tra nội dung | Kiểm tra đơn hàng gửi vào repository |

Không nên lạm dụng `verifyNoMoreInteractions` trong mọi test. Nó khóa chặt thứ tự và số lượng tương tác nội bộ, khiến một thay đổi triển khai không ảnh hưởng hành vi cũng làm test thất bại. Hãy xác minh các tương tác có ý nghĩa như lưu dữ liệu, phát sự kiện hoặc gọi dependency bắt buộc.

Với nhánh thất bại, xác nhận các bước sau điểm lỗi không được thực hiện. Ví dụ, nếu repository không tìm thấy sản phẩm, `inventoryService.reserve(...)` và `orderRepository.save(...)` không được gọi. Với nhánh thành công, xác nhận đủ các tương tác cần thiết và đối số quan trọng.

Nếu một dependency có tác dụng phụ thực sự, chẳng hạn trừ tồn kho hoặc gửi email, mock chỉ chứng minh service đã gọi nó với tham số nào. Mock không chứng minh cơ sở dữ liệu hoặc hệ thống bên ngoài đã thay đổi đúng. Hành vi đó cần test tích hợp với thành phần thực hoặc môi trường kiểm thử phù hợp.

## 9. Phân biệt ngoại lệ mong đợi và lỗi bất ngờ

Không phải mọi ngoại lệ đều biểu thị cùng một loại thất bại.

| Loại | Ví dụ | Cách kiểm thử |
|---|---|---|
| Vi phạm tham số | `IllegalArgumentException` khi quantity không dương | Gọi với đầu vào sai và xác nhận lỗi xảy ra trước dependency |
| Lỗi nghiệp vụ | `ProductNotFoundException`, `InsufficientStockException` | Thiết lập trạng thái miền khiến quy tắc thất bại và kiểm tra loại lỗi |
| Lỗi hạ tầng | Timeout, lỗi kết nối hoặc lỗi repository | Thiết lập mock ném lỗi kỹ thuật và xác nhận truyền lên hoặc chuyển đổi theo hợp đồng |
| Lỗi lập trình ngoài dự kiến | `NullPointerException` do code truy cập null sai | Không nên biến nó thành kết quả mong đợi của test nghiệp vụ; cần sửa nguyên nhân trong mã |

Một test như sau quá rộng:

```java
assertThrows(RuntimeException.class,
        () -> orderService.placeOrder("p-100", 2));
```

Nếu phương thức vô tình ném `NullPointerException`, test vẫn có thể xanh dù hành vi mong đợi là `InsufficientStockException`. Nên chỉ định loại ngoại lệ cụ thể:

```java
assertThrows(InsufficientStockException.class,
        () -> orderService.placeOrder("p-100", 5));
```

Khi loại ngoại lệ là một phần của hợp đồng, kiểm tra thêm message, error code hoặc cause nếu chúng ổn định và có ý nghĩa đối với caller. Tránh khóa cứng toàn bộ câu chữ không phải hợp đồng vì việc diễn đạt hoặc bản địa hóa có thể thay đổi.

## 10. Kiểm thử nhiều nhánh với `@ParameterizedTest`

Parameterized test hữu ích khi một quy tắc có nhiều giá trị đầu vào cùng hành vi. Ví dụ, số lượng bằng 0 và số âm đều phải bị từ chối. `@ValueSource` phù hợp với một tham số đơn giản; `@CsvSource` có thể biểu diễn nhiều cột dữ liệu.

```java
@ParameterizedTest
@ValueSource(ints = {0, -1, -20})
void rejectsQuantityThatIsNotPositive(int quantity) {
    assertThrows(
            IllegalArgumentException.class,
            () -> orderService.placeOrder("p-100", quantity)
    );

    verifyNoInteractions(productRepository, inventoryService, orderRepository);
}
```

Nếu mỗi trường hợp cần một kết quả khác nhau, hãy tách test hoặc dùng `@MethodSource` để dữ liệu kiểm thử có tên và cấu trúc rõ ràng. Không nên gom các trường hợp chỉ vì chúng đều có thể ném ngoại lệ; nguyên nhân và hành vi mong đợi vẫn cần được thể hiện riêng.

## 11. Kiểm tra nhánh và độ bao phủ

Line coverage cho biết dòng lệnh nào đã được chạy; branch coverage cho biết các hướng rẽ nhánh đã được thực thi. Với phương thức `placeOrder`, một bộ test có thể chạy dòng kiểm tra `if` nhưng chỉ đi theo một phía của điều kiện. Khi đó, line coverage có thể cao nhưng branch coverage vẫn thiếu.

Ví dụ, điều kiện `if (!product.active())` có hai kết quả:

- `active == true`: tiếp tục kiểm tra tồn kho.
- `active == false`: ném `ProductUnavailableException`.

Muốn bao phủ cả hai nhánh, cần ít nhất một test cho sản phẩm hoạt động và một test cho sản phẩm ngừng bán. Tương tự, `inventoryService.reserve(...)` cần có trường hợp trả về `true` và `false`.

Độ bao phủ là chỉ báo hỗ trợ tìm vùng chưa được thực thi, không phải bằng chứng rằng test đã kiểm tra đúng kết quả. Một test có thể chạy qua nhánh nhưng không assertion gì có ý nghĩa. Hãy ưu tiên xác nhận hành vi, kết quả và tác dụng phụ; dùng branch coverage để phát hiện những hướng xử lý còn thiếu.

Khi dự án dùng JaCoCo, có thể cấu hình báo cáo line/branch coverage cho test task và xem các nhánh còn thiếu trong báo cáo HTML. Không nên viết test chỉ để đạt một con số phần trăm nếu các test đó không bảo vệ quy tắc có ý nghĩa. Một nhánh phòng vệ không thể xảy ra theo hợp đồng cũng cần được đánh giá dựa trên thiết kế, không nên tạo dữ liệu giả chỉ để tăng coverage.

## 12. Chọn unit test hay Spring integration test?

Unit test cho service thường chỉ cần JUnit Jupiter và mock các dependency. Không cần `@SpringBootTest` nếu mục tiêu là kiểm tra quy tắc thuần của một lớp.

| Mục tiêu | Cách kiểm thử phù hợp |
|---|---|
| Kiểm tra nhánh nghiệp vụ trong service | JUnit Jupiter + Mockito, tạo service trực tiếp |
| Kiểm tra dependency injection và cấu hình bean | Spring Test hoặc `@SpringBootTest` |
| Kiểm tra transaction, rollback và tương tác database thực | Integration test với Spring context và database kiểm thử |
| Kiểm tra HTTP status và exception handler | `@WebMvcTest` với `MockMvc` hoặc kiểm thử tích hợp phù hợp |
| Kiểm tra lỗi thực từ database hoặc message broker | Integration test với thành phần thật hoặc container kiểm thử |

Unit test có thể xác nhận service ném `InsufficientStockException`, nhưng không chứng minh controller chuyển ngoại lệ đó thành HTTP 409 hay response JSON đúng. Đó là hợp đồng web và nên được kiểm tra ở tầng controller.

Tương tự, mock repository ném `DataAccessException` giúp kiểm tra cách service phản ứng với dependency lỗi; nó không chứng minh transaction database rollback đúng. Rollback cần được kiểm tra bằng integration test chạy trong transaction và đọc lại trạng thái dữ liệu theo cách phù hợp.

## 13. Những sai lầm thường gặp

**Chỉ kiểm tra kết quả thành công.** Các nhánh từ chối, tài nguyên không tồn tại và dependency lỗi có thể chứa lỗi điều khiển luồng. Hãy liệt kê nhánh trước khi viết test.

**Dùng một test bao phủ nhiều nguyên nhân thất bại.** Nếu một test vừa tạo sản phẩm không tồn tại, vừa thiết lập tồn kho không đủ, service sẽ dừng ở nhánh đầu tiên. Nhánh tồn kho không được thực thi. Mỗi test nên cô lập điều kiện khiến nhánh mục tiêu xảy ra.

**Chỉ kiểm tra rằng có ngoại lệ.** Dùng `RuntimeException.class` có thể khiến lỗi lập trình bất ngờ làm test xanh. Hãy kiểm tra loại ngoại lệ cụ thể và thông tin quan trọng.

**Quên xác nhận các bước sau điểm lỗi không chạy.** Một test có thể nhận đúng ngoại lệ nhưng service vẫn gọi repository hoặc gửi sự kiện sau khi bắt lỗi sai cách. Dùng `verifyNoInteractions`, `never()` hoặc xác nhận trạng thái tùy hợp đồng.

**Mock mọi đối tượng, kể cả đối tượng giá trị đơn giản.** DTO, record và value object thường nên được tạo thật. Mock chúng làm test khó hiểu và không đem lại lợi ích nếu chúng không có hành vi cần thay thế.

**Dùng `@SpringBootTest` cho mọi unit test.** Khởi tạo toàn bộ context làm test chậm và khiến lỗi cấu hình có thể che khuất lỗi nghiệp vụ. Với service có dependency rõ ràng, tạo service trực tiếp cùng Mockito mock thường đủ.

**Xác minh quá nhiều chi tiết nội bộ.** Khóa chặt mọi lời gọi khiến test khó bảo trì khi triển khai được tái cấu trúc. Chỉ kiểm tra các tương tác thuộc hợp đồng hoặc bảo vệ tác dụng phụ quan trọng.

**Cho rằng mock đã kiểm tra hệ thống bên ngoài.** Mockito chỉ mô phỏng phản hồi và ghi nhận tương tác. Nó không chứng minh database, broker hay API ngoài hoạt động đúng; cần integration test cho những hành vi đó.

## 14. Quy trình xây dựng bộ test cho một service

Với một service có nhiều nhánh, có thể làm theo trình tự:

1. Đọc phương thức và ghi lại từng điều kiện `if`, `switch`, `Optional`, vòng lặp hoặc điểm ném ngoại lệ có ý nghĩa.
2. Xác định kết quả mong đợi cho mỗi nhánh: giá trị trả về, ngoại lệ, trạng thái hoặc tác dụng phụ.
3. Viết test thành công trước để xác nhận luồng thông thường và các dependency cần thiết.
4. Viết một test riêng cho mỗi lỗi nghiệp vụ quan trọng, thiết lập đúng điều kiện để chỉ nhánh đó xảy ra.
5. Thiết lập dependency ném ngoại lệ để kiểm tra chính sách truyền lên, chuyển đổi, retry hoặc fallback.
6. Xác nhận các lời gọi tiếp theo bị dừng ở đúng điểm lỗi và không tạo tác dụng phụ ngoài hợp đồng.
7. Chạy test và xem branch coverage để phát hiện hướng xử lý chưa được thực thi; bổ sung test theo hành vi còn thiếu.
8. Nếu cần xác nhận transaction, HTTP mapping hoặc hành vi thật của dependency, bổ sung integration test ở tầng tương ứng.

Với ví dụ `OrderService`, bộ test trọng tâm gồm: một test thành công; một test số lượng không hợp lệ; một test sản phẩm không tồn tại; một test sản phẩm ngừng bán; một test không đủ tồn kho; và các test dependency phát sinh ngoại lệ. Mỗi test tập trung vào một điều kiện khiến luồng xử lý rẽ sang nhánh cần xác nhận.

Khi kiểm thử nhánh thành công, lỗi và ngoại lệ, điều quan trọng là xác định rõ điều kiện kích hoạt, kết quả được công bố và các tác dụng phụ được phép. JUnit Jupiter cung cấp assertion và cơ chế kiểm thử tham số; Mockito điều khiển dependency và xác minh tương tác; Spring Test hoặc integration test được dùng khi cần kiểm tra sự phối hợp với Spring context, transaction, HTTP hoặc hạ tầng thực. Bộ test tốt giúp người đọc hiểu service phải làm gì trong cả trường hợp bình thường lẫn khi một điều kiện không được đáp ứng.
