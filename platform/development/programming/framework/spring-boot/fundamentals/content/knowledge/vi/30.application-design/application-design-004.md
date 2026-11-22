# Tách interface theo nhu cầu thay thế, tránh tạo lớp trung gian không có vai trò

Trong một ứng dụng Spring Boot, rất dễ tạo một interface cho mỗi class:

```java
public interface OrderService {
    Order findById(String id);
}
```

```java
@Service
public class OrderServiceImpl implements OrderService {

    @Override
    public Order findById(String id) {
        // ...
    }
}
```

Cách làm này không sai về cú pháp và đôi khi phù hợp với kiến trúc. Nhưng nếu interface chỉ lặp lại toàn bộ public methods của một implementation, ứng dụng chỉ có một cách triển khai, không có nhu cầu thay thế và không có ranh giới độc lập cần bảo vệ, abstraction đó có thể chỉ làm tăng số file và số tên cần theo dõi.

Ngược lại, khi một use case cần hỗ trợ nhiều payment providers, khi ứng dụng phải chuyển từ một hệ thống lưu trữ sang hệ thống khác, hoặc khi một thành phần cần được thay bằng fake trong test, interface có thể tạo ra một **hợp đồng thay thế có ý nghĩa**. Khi đó client phụ thuộc vào điều nó cần, còn implementation có thể thay đổi mà không buộc client biết chi tiết bên trong.

Bài học này tập trung vào việc **tách interface theo nhu cầu thay thế thực tế**, xác định ai cần hợp đồng, hợp đồng nên chứa những hành vi nào và khi nào một lớp trung gian chỉ chuyển tiếp lời gọi nên được bỏ đi. Mục tiêu là tạo ranh giới giúp thay đổi dễ hơn, đồng thời giữ thiết kế đủ đơn giản để người đọc hiểu được luồng nghiệp vụ.

> Một interface có giá trị khi nó diễn đạt một hợp đồng mà client cần và cho phép một quyết định triển khai thay đổi độc lập. Một interface chỉ sao chép tên method của một class chưa tự tạo ra giá trị đó.

## 1. Interface là hợp đồng, không phải nghi thức bắt buộc cho mọi class

Interface trong Java mô tả những thao tác mà một kiểu có thể cung cấp:

```java
public interface InventoryReader {
    int availableQuantity(String sku);
}
```

Một implementation cam kết thực hiện hợp đồng:

```java
@Component
public class JpaInventoryReader implements InventoryReader {

    private final InventoryRepository repository;

    public JpaInventoryReader(InventoryRepository repository) {
        this.repository = repository;
    }

    @Override
    public int availableQuantity(String sku) {
        return repository.findBySku(sku)
                .map(InventoryEntity::getAvailableQuantity)
                .orElse(0);
    }
}
```

Client có thể sử dụng hợp đồng:

```java
@Service
public class CheckoutService {

    private final InventoryReader inventory;

    public CheckoutService(InventoryReader inventory) {
        this.inventory = inventory;
    }

    public boolean canCheckout(String sku, int quantity) {
        return inventory.availableQuantity(sku) >= quantity;
    }
}
```

`CheckoutService` chỉ cần biết cách hỏi số lượng còn khả dụng. Nó không cần biết dữ liệu đến từ JPA, REST API, cache hay một nguồn khác.

### 1.1. Interface tạo ra điều gì?

Một interface được thiết kế tốt có thể:

- Đặt tên cho một khả năng nghiệp vụ hoặc một cổng tích hợp.
- Giới hạn những gì client được phép yêu cầu.
- Cho phép nhiều implementation cùng tuân theo một contract.
- Tách chính sách nghiệp vụ khỏi chi tiết hạ tầng.
- Tạo seam để test bằng fake hoặc stub.
- Cho phép thay đổi implementation mà không sửa client.
- Giúp một module công bố API nhỏ, ổn định.

Nhưng interface không tự động:

- Làm code dễ test hơn nếu test vẫn cần nhiều hạ tầng thật.
- Làm ứng dụng linh hoạt nếu chỉ có một implementation và không có lý do thay thế.
- Giảm coupling nếu interface phơi bày mọi chi tiết của implementation.
- Làm hệ thống tuân thủ Dependency Inversion chỉ vì có thêm một file.
- Bảo đảm hai implementation có hành vi tương đương.

### 1.2. Class cũng là một kiểu phụ thuộc hợp lệ

Java cho phép client phụ thuộc trực tiếp vào class:

```java
@Service
public class OrderApplicationService {

    private final OrderCalculator calculator;

    public OrderApplicationService(OrderCalculator calculator) {
        this.calculator = calculator;
    }
}
```

Nếu `OrderCalculator` là logic thuần, ổn định, không có nhu cầu thay thế và không cần tạo ranh giới module, constructor injection trực tiếp vào class có thể là thiết kế đơn giản và rõ ràng.

Không có quy tắc kiến trúc phổ quát yêu cầu mọi `@Service` phải có một interface cùng tên.

## 2. Bắt đầu từ nhu cầu của client

Trước khi tạo interface, hãy hỏi:

1. Client thực sự cần làm những việc nào?
2. Những quyết định triển khai nào có thể thay đổi độc lập?
3. Có nhiều nguồn thực hiện hoặc nhiều môi trường cần hành vi khác nhau không?
4. Việc thay implementation có phải là một khả năng được yêu cầu, hay chỉ là giả định mơ hồ?
5. Nếu thay implementation, client có cần thay đổi không?
6. Interface có thể được đặt theo ngôn ngữ của nghiệp vụ/client không?

Ví dụ, một use case thanh toán có thể cần:

```java
public interface PaymentGateway {
    PaymentResult authorize(PaymentRequest request);
    void capture(String paymentReference);
    void refund(String paymentReference, Money amount);
}
```

Ứng dụng có thể dùng một provider trong môi trường local, provider khác trong production hoặc một fake trong test. Đây là một nhu cầu thay thế có thật.

### 2.1. Thiết kế theo khả năng client sử dụng

Nếu client chỉ cần tra cứu tồn kho, không nhất thiết phải inject một interface cung cấp mọi thao tác quản trị:

```java
public interface InventoryManager {
    int availableQuantity(String sku);
    void reserve(String sku, int quantity);
    void release(String reservationId);
    void importStock(StockImport importData);
    void correctStock(StockCorrection correction);
    void deleteWarehouse(String warehouseId);
}
```

Một `CheckoutService` chỉ cần `availableQuantity` và `reserve`. Một interface quá rộng khiến client phụ thuộc vào nhiều khả năng không liên quan.

Có thể tách hợp đồng theo vai trò:

```java
public interface InventoryAvailability {
    int availableQuantity(String sku);
}
```

```java
public interface StockReservation {
    Reservation reserve(String sku, int quantity);
    void release(String reservationId);
}
```

Một implementation có thể implement cả hai:

```java
@Component
public class WarehouseInventory
        implements InventoryAvailability, StockReservation {
    // ...
}
```

Đây là cách dùng Interface Segregation Principle: client chỉ phụ thuộc vào những method mà nó cần.

### 2.2. Không tách interface chỉ vì muốn có thêm file

Nếu class chỉ có một method `calculate()` và mọi client đều cần đúng class đó, một interface trùng lặp có thể không tạo ra một ranh giới có ý nghĩa:

```java
public interface TaxCalculator {
    BigDecimal calculate(Order order);
}
```

```java
@Component
public class TaxCalculatorImpl implements TaxCalculator {
    // Một triển khai duy nhất, không có contract độc lập
}
```

Nếu không có nhu cầu thay thế, module boundary hoặc lợi ích test cụ thể, có thể dùng trực tiếp:

```java
@Component
public class TaxCalculator {

    public BigDecimal calculate(Order order) {
        // ...
    }
}
```

Khi yêu cầu thay đổi và cần nhiều tax policies, có thể trích interface lúc đó. Việc tạo abstraction sau khi có lý do rõ ràng thường dễ đặt đúng tên và đúng phạm vi hơn tạo trước mọi interface theo mẫu.

## 3. “Nhu cầu thay thế” là gì?

Thay thế không nhất thiết có nghĩa là ngày mai sẽ đổi nhà cung cấp. Nó có thể là yêu cầu hiện tại hoặc một ranh giới độc lập đã tồn tại.

### 3.1. Nhiều provider hoặc chiến lược

Ví dụ:

- Thanh toán bằng thẻ và ví điện tử.
- Gửi thông báo qua email, SMS hoặc push.
- Lưu file vào local disk hoặc object storage.
- Tính giá theo chính sách bán lẻ hoặc bán sỉ.
- Chọn thuật toán định tuyến theo loại đơn.

Các implementation cùng phục vụ một nhu cầu của client, nhưng khác nhau ở cách thực hiện.

### 3.2. Khác biệt giữa môi trường

Một ứng dụng có thể dùng:

| Môi trường | Implementation |
| --- | --- |
| Unit test | Fake repository hoặc stub gateway |
| Local development | Adapter giả lập hoặc sandbox |
| Staging | Sandbox provider |
| Production | Provider thật |

Nếu các implementation cần được chọn theo profile, property hoặc composition root, interface là ranh giới hữu ích.

### 3.3. Tách domain khỏi hạ tầng

Domain không nên phụ thuộc vào JPA entity, HTTP client hoặc SDK của một vendor chỉ để diễn đạt một nghiệp vụ cốt lõi.

Ví dụ, domain cần lưu đơn hàng:

```java
public interface OrderStore {
    Optional<Order> find(OrderId id);
    void save(Order order);
}
```

Adapter JPA:

```java
@Repository
public class JpaOrderStore implements OrderStore {

    private final SpringDataOrderRepository repository;
    private final OrderMapper mapper;

    public JpaOrderStore(
            SpringDataOrderRepository repository,
            OrderMapper mapper) {
        this.repository = repository;
        this.mapper = mapper;
    }

    @Override
    public Optional<Order> find(OrderId id) {
        return repository.findById(id.value())
                .map(mapper::toDomain);
    }

    @Override
    public void save(Order order) {
        repository.save(mapper.toEntity(order));
    }
}
```

Domain/application layer phụ thuộc `OrderStore`. Adapter phụ thuộc Spring Data/JPA và thực hiện contract đó.

### 3.4. Test cần thay một collaborator có side effects

Một use case gửi tiền không nên gọi payment provider thật trong unit test. Một interface cho gateway cho phép thay bằng fake ghi nhận request và trả kết quả xác định.

Đây là một nhu cầu test thực tế. Tuy nhiên, không phải mọi class đều cần interface chỉ để Mockito có thể mock; test cũng có thể dùng class, fake object hoặc kiểm thử tích hợp tùy mục tiêu.

### 3.5. Module có API ổn định, implementation thay đổi

Một module có thể muốn công bố một contract nhỏ cho module khác, đồng thời giữ database schema, SDK hoặc framework bên trong implementation.

Interface có ích khi nó là ranh giới được chủ động duy trì. Nếu interface chỉ nằm cạnh class trong cùng package và không bảo vệ một quyết định thay đổi nào, lợi ích có thể thấp.

## 4. Interface nên thuộc về phía nào?

Một câu hỏi quan trọng là **ai định nghĩa hợp đồng**.

Nếu `CheckoutService` cần khả năng đọc tồn kho, hợp đồng có thể được đặt ở module/application layer đang sử dụng khả năng đó:

```text
checkout/
  application/
    CheckoutService.java
    InventoryAvailability.java

inventory/
  adapter/
    JpaInventoryAvailability.java
```

`CheckoutService` phụ thuộc vào `InventoryAvailability`; adapter cung cấp implementation.

Đây là một cách áp dụng Dependency Inversion: chính sách cấp cao định nghĩa abstraction mà nó cần, còn chi tiết cấp thấp implement abstraction đó.

### 4.1. Consumer-owned interface

Giả sử một thư viện cung cấp:

```java
public class VendorCustomerClient {
    public VendorCustomer fetchCustomer(String externalId) {
        // ...
    }
}
```

Ứng dụng chỉ cần:

```java
public interface CustomerDirectory {
    Optional<CustomerProfile> find(CustomerId id);
}
```

Adapter chuyển đổi giữa hai mô hình:

```java
@Component
public class VendorCustomerDirectory implements CustomerDirectory {

    private final VendorCustomerClient client;
    private final CustomerMapper mapper;

    public VendorCustomerDirectory(
            VendorCustomerClient client,
            CustomerMapper mapper) {
        this.client = client;
        this.mapper = mapper;
    }

    @Override
    public Optional<CustomerProfile> find(CustomerId id) {
        VendorCustomer external =
                client.fetchCustomer(id.value());

        return Optional.ofNullable(external)
                .map(mapper::toProfile);
    }
}
```

Client nghiệp vụ không phải biết `VendorCustomer`, SDK hoặc kiểu exception riêng của nhà cung cấp.

### 4.2. Khi nào interface thuộc module cung cấp?

Không phải lúc nào consumer cũng nên sở hữu interface. Nếu một module thật sự cung cấp một API công khai ổn định cho nhiều client, interface có thể thuộc module đó.

Điều quan trọng không phải vị trí tuyệt đối của file mà là:

- Hợp đồng diễn đạt đúng trách nhiệm.
- Phụ thuộc giữa module đi theo hướng mong muốn.
- Contract không rò rỉ chi tiết triển khai không cần thiết.
- Có một owner chịu trách nhiệm thay đổi API.

### 4.3. Đừng đặt mọi interface vào một thư mục `interfaces`

Một package chứa hàng chục interface chung chung có thể làm mất ngữ cảnh:

```text
interfaces/
  ServiceInterface.java
  RepositoryInterface.java
  ClientInterface.java
```

Thay vào đó, đặt tên theo khả năng và nhóm với module sử dụng:

```text
checkout/
  application/
    InventoryAvailability.java

payment/
  application/
    PaymentGateway.java
```

Tên package và interface nên giúp người đọc hiểu nó phục vụ quyết định nào.

## 5. Dependency Inversion Principle và interface

Dependency Inversion Principle (DIP) thường được diễn đạt bằng hai ý:

1. Module cấp cao không nên phụ thuộc trực tiếp vào module cấp thấp; cả hai nên phụ thuộc abstraction.
2. Abstraction không nên phụ thuộc chi tiết; chi tiết nên phụ thuộc abstraction.

### 5.1. Phụ thuộc trực tiếp vào implementation

```java
@Service
public class CheckoutService {

    private final StripePaymentClient stripe;

    public CheckoutService(StripePaymentClient stripe) {
        this.stripe = stripe;
    }
}
```

Use case checkout biết cụ thể một provider. Nếu đổi sang provider khác, code checkout có thể phải thay đổi.

### 5.2. Phụ thuộc vào abstraction

```java
public interface PaymentGateway {
    PaymentResult authorize(PaymentRequest request);
}
```

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

```java
@Component
public class StripePaymentGateway implements PaymentGateway {
    // Tích hợp provider
}
```

```java
@Component
public class SandboxPaymentGateway implements PaymentGateway {
    // Tích hợp sandbox
}
```

`CheckoutService` không biết provider nào được chọn. Spring wiring quyết định implementation.

### 5.3. Có interface chưa chắc đã áp dụng DIP

Ví dụ:

```java
public interface StripePaymentService {
    void charge();
}
```

```java
public class StripePaymentServiceImpl
        implements StripePaymentService {
}
```

Nếu interface vẫn mang tên và khái niệm riêng của vendor, client vẫn phụ thuộc vào quyết định triển khai. Abstraction có thể chỉ đổi kiểu tham chiếu mà không đảo chiều phụ thuộc.

Một contract như `PaymentGateway` hoặc `PaymentAuthorization` thường diễn đạt nhu cầu của ứng dụng tốt hơn nếu đó là điều client thực sự cần.

### 5.4. Không phải interface nào cũng là DIP

Interface có thể chỉ là API nội bộ, không nhất thiết đại diện một boundary kiến trúc. DIP là về **hướng phụ thuộc và quyền sở hữu abstraction**, không phải số lượng interface trong project.

## 6. Interface Segregation Principle: hợp đồng nhỏ theo vai trò

Interface Segregation Principle (ISP) khuyên client không nên bị buộc phụ thuộc vào những method mà nó không dùng.

### 6.1. Interface quá rộng

```java
public interface UserManagement {
    User find(UserId id);
    void create(User user);
    void update(User user);
    void delete(UserId id);
    void exportAll();
    void resetPassword(UserId id);
    void lock(UserId id);
}
```

Một service chỉ cần đọc hồ sơ lại phải phụ thuộc vào một contract có cả thao tác xóa và quản trị.

### 6.2. Tách theo client role

```java
public interface UserReader {
    Optional<UserProfile> find(UserId id);
}
```

```java
public interface UserWriter {
    void save(User user);
}
```

```java
public interface UserAdministration {
    void lock(UserId id);
    void resetPassword(UserId id);
}
```

Một implementation có thể thực hiện nhiều interface, nhưng mỗi client chỉ inject vai trò cần dùng.

### 6.3. Interface nhỏ không đồng nghĩa mỗi method một interface

Tách quá nhỏ cũng có chi phí:

```java
public interface UserFinder {
    User find(UserId id);
}

public interface UserSaver {
    void save(User user);
}

public interface UserDeleter {
    void delete(UserId id);
}
```

Nếu mọi client đều dùng chung một tập thao tác và những thao tác đó thay đổi cùng nhau, chia mỗi method thành một interface có thể làm thiết kế phân mảnh.

Tách khi các nhóm client có quyền hạn, nhu cầu thay thế hoặc nhịp thay đổi khác nhau. Giữ cùng nhau khi chúng tạo thành một contract có ý nghĩa.

## 7. Lớp trung gian không có vai trò là gì?

Một lớp trung gian thường được gọi là pass-through wrapper khi nó chỉ chuyển lời gọi tới một object khác mà không thêm hành vi, không bảo vệ abstraction và không quản lý một ranh giới riêng.

Ví dụ:

```java
@Service
public class OrderService {

    private final OrderServiceImpl delegate;

    public OrderService(OrderServiceImpl delegate) {
        this.delegate = delegate;
    }

    public Order findById(String id) {
        return delegate.findById(id);
    }

    public void save(Order order) {
        delegate.save(order);
    }
}
```

Nếu `OrderService` chỉ chuyển tiếp mọi method sang `OrderServiceImpl`, lớp ngoài không thêm:

- Quy tắc nghiệp vụ.
- Transaction boundary.
- Authorization.
- Mapping hoặc validation.
- Caching.
- Retry policy.
- Điều phối nhiều collaborator.
- Một contract độc lập có ý nghĩa.

Nó chỉ làm người đọc phải đi qua thêm một file để tìm logic thực tế.

### 7.1. Vì sao pass-through wrapper gây chi phí?

- Thêm một tầng điều hướng khi đọc stack trace.
- Thêm constructor và dependency wiring.
- Tạo thêm nơi cần đổi tên method.
- Có thể tạo vòng lặp gọi qua lại.
- Làm người đọc tưởng có một abstraction quan trọng trong khi không có.
- Khó biết class nào thực sự sở hữu nghiệp vụ.

### 7.2. Không phải mọi delegate đều vô nghĩa

Một lớp trung gian có thể có vai trò thật nếu nó:

- Chuyển đổi domain model sang external model.
- Áp dụng authorization hoặc validation.
- Chọn implementation theo policy.
- Điều phối nhiều collaborator.
- Tạo transaction boundary.
- Quản lý retry, timeout, fallback.
- Chuyển đổi exception.
- Giữ ổn định contract trước một SDK thay đổi.

Tên `Adapter`, `Facade`, `Decorator` hoặc `Service` không tự chứng minh lớp đó có giá trị. Hãy xem nó thực sự làm gì.

## 8. Ví dụ: loại bỏ lớp trung gian chỉ chuyển tiếp

### 8.1. Thiết kế có hai tầng trùng lặp

```text
OrderController
      |
      v
OrderService
      |
      v
OrderServiceImpl
      |
      v
OrderRepository
```

Code:

```java
public interface OrderService {
    Order findById(String id);
}
```

```java
@Service
public class OrderServiceImpl implements OrderService {

    private final OrderRepository repository;

    public OrderServiceImpl(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public Order findById(String id) {
        return repository.findById(id).orElseThrow();
    }
}
```

Nếu một class khác cũng tên `OrderService` chỉ delegate tới implementation, hãy xác định tầng nào thật sự có trách nhiệm. Không cần giữ hai lớp chỉ vì muốn có interface và implementation cùng tên.

### 8.2. Một service class trực tiếp

```java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Order findById(String id) {
        return repository.findById(id).orElseThrow();
    }
}
```

Nếu không có contract thay thế độc lập cho `OrderService`, đây có thể là thiết kế rõ ràng hơn.

### 8.3. Interface ở boundary dữ liệu vẫn có thể hợp lý

Không cần loại bỏ mọi interface. `OrderRepository` có thể là abstraction hữu ích nếu nó đại diện persistence port do application/domain cần, còn implementation JPA là adapter.

Một thiết kế có thể là:

```text
OrderController
      |
      v
OrderService
      |
      v
OrderStore (port)
      ^
      |
JpaOrderStore (adapter)
      |
      v
Spring Data Repository
```

Điểm khác biệt: `OrderStore` thể hiện ranh giới persistence mà service cần. Nó không chỉ lặp lại class `OrderService`.

## 9. Phân biệt interface có ý nghĩa với interface trùng lặp

| Tiêu chí | Interface có ý nghĩa | Interface trùng lặp |
| --- | --- | --- |
| Tên | Diễn đạt capability/contract | Thường chỉ thêm hậu tố `Service`, `Impl` |
| Owner | Có client/module cần contract | Không rõ ai cần nó |
| Methods | Chỉ những thao tác client cần | Sao chép toàn bộ class API |
| Implementations | Có thể có nhiều cách thực hiện hợp lý | Một implementation duy nhất, không có seam độc lập |
| Thay thế | Có kịch bản thay thế cụ thể | Chỉ giả định “sau này có thể đổi” |
| Dependencies | Giảm coupling tới chi tiết | Client vẫn phụ thuộc khái niệm implementation |
| Test | Tạo seam có giá trị cho test | Chỉ thêm mock type mà không cải thiện test boundary |
| Evolution | Contract thay đổi theo nhu cầu client | Interface và class luôn đổi cùng nhau |

Đây không phải checklist cứng. Một interface một implementation vẫn có thể rất hữu ích nếu nó là ranh giới ổn định giữa module hoặc giữa domain và infrastructure.

## 10. Ví dụ đầy đủ: PaymentGateway với nhiều implementation

Một ứng dụng cần thanh toán qua provider khác nhau theo môi trường.

### 10.1. Domain types

```java
package com.example.payment.domain;

import java.math.BigDecimal;

public record Money(BigDecimal amount, String currency) {
}
```

```java
package com.example.payment.domain;

public record PaymentRequest(
        String orderReference,
        Money amount
) {
}
```

```java
package com.example.payment.domain;

public record PaymentResult(
        String providerReference,
        PaymentStatus status
) {
}
```

```java
package com.example.payment.domain;

public enum PaymentStatus {
    AUTHORIZED,
    DECLINED,
    PENDING
}
```

### 10.2. Contract mà use case cần

```java
package com.example.payment.application;

import com.example.payment.domain.PaymentRequest;
import com.example.payment.domain.PaymentResult;

public interface PaymentGateway {
    PaymentResult authorize(PaymentRequest request);
}
```

Contract này thuộc ngôn ngữ của ứng dụng. Nó không chứa `StripeChargeRequest`, `VendorTransactionResponse` hoặc exception riêng của SDK.

### 10.3. Use case phụ thuộc abstraction

```java
package com.example.payment.application;

import com.example.payment.domain.PaymentRequest;
import com.example.payment.domain.PaymentResult;
import org.springframework.stereotype.Service;

@Service
public class AuthorizePayment {

    private final PaymentGateway gateway;

    public AuthorizePayment(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public PaymentResult execute(PaymentRequest request) {
        if (request.amount().amount().signum() <= 0) {
            throw new IllegalArgumentException(
                    "Payment amount must be positive"
            );
        }

        return gateway.authorize(request);
    }
}
```

### 10.4. Provider adapter

```java
package com.example.payment.adapter.partner;

import com.example.payment.application.PaymentGateway;
import com.example.payment.domain.PaymentRequest;
import com.example.payment.domain.PaymentResult;
import com.example.payment.domain.PaymentStatus;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("production")
public class PartnerPaymentGateway implements PaymentGateway {

    private final PartnerClient client;

    public PartnerPaymentGateway(PartnerClient client) {
        this.client = client;
    }

    @Override
    public PaymentResult authorize(PaymentRequest request) {
        PartnerResponse response = client.authorize(
                new PartnerRequest(
                        request.orderReference(),
                        request.amount().amount(),
                        request.amount().currency()
                )
        );

        PaymentStatus status = switch (response.status()) {
            case "APPROVED" -> PaymentStatus.AUTHORIZED;
            case "PENDING" -> PaymentStatus.PENDING;
            default -> PaymentStatus.DECLINED;
        };

        return new PaymentResult(response.reference(), status);
    }
}
```

`PartnerClient`, `PartnerRequest` và `PartnerResponse` là kiểu giả định của integration SDK. Adapter chuyển đổi giữa contract của ứng dụng và API của provider.

### 10.5. Sandbox adapter

```java
@Component
@Profile("local")
public class SandboxPaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult authorize(PaymentRequest request) {
        return new PaymentResult(
                "sandbox-" + request.orderReference(),
                PaymentStatus.AUTHORIZED
        );
    }
}
```

### 10.6. Spring chọn implementation

Với profile `local`:

```bash
java -jar app.jar --spring.profiles.active=local
```

Với profile `production`:

```bash
java -jar app.jar --spring.profiles.active=production
```

Ứng dụng cần bảo đảm chỉ có một `PaymentGateway` phù hợp trong mỗi môi trường. Nếu không profile nào được kích hoạt hoặc có hai implementation cùng được đăng ký, constructor injection có thể thất bại vì thiếu hoặc ambiguous bean.

### 10.7. Interface giúp gì ở đây?

- `AuthorizePayment` không cần sửa khi provider thay đổi.
- Provider-specific types được giữ trong adapter.
- Sandbox và production thực hiện cùng contract.
- Unit test có thể cung cấp fake gateway.
- Việc lựa chọn implementation được thể hiện tại configuration boundary.

Đây là một nhu cầu thay thế cụ thể, vì vậy interface tạo ra giá trị thực.

## 11. Interface không đảm bảo các implementation có hành vi tương đương

Hai class cùng implement một interface có thể vẫn khác nhau về:

- Quy tắc retry.
- Timeout.
- Idempotency.
- Error mapping.
- Tính nhất quán dữ liệu.
- Side effects.
- Điều kiện trả `null` hoặc empty.
- Độ chính xác của kết quả.

Ví dụ:

```java
public interface PaymentGateway {
    PaymentResult authorize(PaymentRequest request);
}
```

Nếu implementation A ném `PaymentDeclinedException` khi bị từ chối nhưng implementation B trả `null`, client phải biết từng implementation và contract mất giá trị.

### 11.1. Contract cần mô tả cả semantics

Một contract nên làm rõ:

- `PaymentResult` biểu diễn trạng thái nào?
- Declined là kết quả bình thường hay exception?
- Timeout có thể xảy ra không?
- Một request có thể được gửi lại an toàn không?
- Provider reference có duy nhất không?
- Currency và amount được xác thực ở đâu?

Không cần ghi mọi chi tiết vào JavaDoc, nhưng behavior quan trọng phải được thống nhất và kiểm thử.

### 11.2. Contract test cho nhiều implementation

Có thể tạo một bộ test dùng chung:

```java
abstract class PaymentGatewayContractTest {

    protected abstract PaymentGateway gateway();

    @Test
    void returnsAResultForAnApprovedRequest() {
        PaymentResult result = gateway().authorize(
                new PaymentRequest(
                        "order-100",
                        new Money(new BigDecimal("100.00"), "USD")
                )
        );

        assertThat(result).isNotNull();
        assertThat(result.status())
                .isIn(PaymentStatus.AUTHORIZED,
                      PaymentStatus.PENDING,
                      PaymentStatus.DECLINED);
    }
}
```

Đây chỉ là skeleton; một contract test có giá trị cần fixture hoặc provider sandbox với kết quả xác định. Test không nên cho phép mọi status rồi xem như đã xác nhận business semantics. Hãy viết các test cụ thể theo expected outcome và cách mỗi adapter mô phỏng chúng.

## 12. Test seam không nhất thiết phải là interface cho mọi class

Một lý do thường được dùng để tạo interface là “để mock dễ hơn”. Đây có thể là lý do hợp lệ khi thay thế collaborator là một phần quan trọng của test, nhưng không phải quy tắc tuyệt đối.

### 12.1. Fake qua interface

```java
class FakePaymentGateway implements PaymentGateway {

    private PaymentResult nextResult;
    private PaymentRequest lastRequest;

    void returnNext(PaymentResult result) {
        this.nextResult = result;
    }

    PaymentRequest lastRequest() {
        return lastRequest;
    }

    @Override
    public PaymentResult authorize(PaymentRequest request) {
        lastRequest = request;
        return nextResult;
    }
}
```

Fake này có behavior rõ và có thể kiểm tra use case mà không gọi provider thật.

### 12.2. Dùng Mockito

```java
@ExtendWith(MockitoExtension.class)
class AuthorizePaymentTest {

    @Mock
    PaymentGateway gateway;

    @InjectMocks
    AuthorizePayment authorizePayment;

    @Test
    void delegatesAuthorizationToGateway() {
        PaymentRequest request = new PaymentRequest(
                "order-1",
                new Money(new BigDecimal("50.00"), "USD")
        );

        PaymentResult expected = new PaymentResult(
                "pay-1",
                PaymentStatus.AUTHORIZED
        );

        when(gateway.authorize(request)).thenReturn(expected);

        PaymentResult actual = authorizePayment.execute(request);

        assertThat(actual).isEqualTo(expected);
        verify(gateway).authorize(request);
    }
}
```

### 12.3. Test class trực tiếp cũng được

Nếu một `OrderCalculator` là logic thuần, test có thể khởi tạo trực tiếp:

```java
class OrderCalculatorTest {

    private final OrderCalculator calculator =
            new OrderCalculator();

    @Test
    void calculatesDiscount() {
        // Assert kết quả tính toán
    }
}
```

Không cần `OrderCalculatorInterface` chỉ để test một class thuần không có side effects.

### 12.4. Ưu tiên test behavior thay vì cấu trúc mock

Một test chỉ verify rằng method A gọi method B có thể khóa chặt implementation. Khi code refactor nhưng behavior không đổi, test vẫn fail.

Hãy xác định test cần chứng minh:

- Kết quả nghiệp vụ?
- Một side effect quan trọng?
- Một contract với provider?
- Một tương tác bắt buộc?

Chọn fake, mock, integration test hoặc direct construction theo câu hỏi đó.

## 13. Spring dependency injection với interface

Spring có thể inject implementation theo interface nếu có đúng một bean phù hợp.

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

### 13.1. Một implementation

```java
@Component
public class DefaultPaymentGateway implements PaymentGateway {
}
```

Spring có thể inject `DefaultPaymentGateway` vào constructor yêu cầu `PaymentGateway`.

### 13.2. Nhiều implementation

Nếu có:

```java
@Component
class CardGateway implements PaymentGateway {
}

@Component
class WalletGateway implements PaymentGateway {
}
```

constructor cần một bean duy nhất có thể gặp `NoUniqueBeanDefinitionException`.

Dùng `@Qualifier`:

```java
public CheckoutService(
        @Qualifier("cardGateway") PaymentGateway gateway) {
    this.gateway = gateway;
}
```

Hoặc `@Primary` nếu một implementation là lựa chọn mặc định phù hợp.

### 13.3. Profile

```java
@Component
@Profile("local")
class FakePaymentGateway implements PaymentGateway {
}
```

```java
@Component
@Profile("production")
class RealPaymentGateway implements PaymentGateway {
}
```

Phải xác nhận profile nào được active ở từng môi trường. Interface không tự chọn implementation.

### 13.4. Conditional bean

```java
@Bean
@ConditionalOnProperty(
        name = "payment.provider",
        havingValue = "partner"
)
PaymentGateway partnerGateway(PartnerClient client) {
    return new PartnerPaymentGateway(client);
}
```

Nếu condition không match và không có bean thay thế, client inject bắt buộc sẽ thất bại. Đây là behavior cần được thiết kế và test, không phải điều interface tự giải quyết.

## 14. Adapter có vai trò khác pass-through wrapper

Một adapter bảo vệ client khỏi contract của hệ thống bên ngoài bằng chuyển đổi thực sự.

### 14.1. Pass-through

```java
public class CustomerService {

    private final VendorCustomerService vendor;

    public Customer get(String id) {
        return vendor.get(id);
    }
}
```

Nếu method chỉ đổi tên `get()` thành `get()` và trả nguyên object, lớp này có thể không tạo abstraction.

### 14.2. Adapter có mapping

```java
public class CustomerDirectoryAdapter
        implements CustomerDirectory {

    private final VendorCustomerService vendor;
    private final CustomerMapper mapper;

    @Override
    public Optional<CustomerProfile> find(CustomerId id) {
        VendorCustomer response = vendor.get(id.value());

        return Optional.ofNullable(response)
                .map(mapper::toDomainProfile);
    }
}
```

Adapter này:

- Dịch ID của ứng dụng sang ID provider.
- Dịch model vendor sang model domain.
- Cô lập kiểu dữ liệu bên ngoài.
- Có thể chuẩn hóa lỗi hoặc retry ở đúng boundary.

Đây là lớp trung gian có trách nhiệm rõ ràng.

### 14.3. Adapter không cần có thêm interface riêng

Nếu `CustomerDirectoryAdapter` đã implement `CustomerDirectory`, không nhất thiết tạo thêm:

```java
public interface CustomerDirectoryAdapter {
    Optional<CustomerProfile> find(CustomerId id);
}
```

Một interface trùng với adapter class thường không thêm contract mới. Client nên phụ thuộc `CustomerDirectory`.

## 15. Decorator: lớp trung gian có thêm behavior

Decorator bọc một implementation cùng contract để thêm hành vi mà không sửa implementation gốc.

Ví dụ cache:

```java
public class CachingCustomerDirectory
        implements CustomerDirectory {

    private final CustomerDirectory delegate;
    private final CustomerCache cache;

    public CachingCustomerDirectory(
            CustomerDirectory delegate,
            CustomerCache cache) {
        this.delegate = delegate;
        this.cache = cache;
    }

    @Override
    public Optional<CustomerProfile> find(CustomerId id) {
        return cache.get(id)
                .or(() -> {
                    Optional<CustomerProfile> result =
                            delegate.find(id);
                    result.ifPresent(profile -> cache.put(id, profile));
                    return result;
                });
    }
}
```

Lớp này không chỉ chuyển tiếp: nó thêm cache policy. Tuy nhiên, cần xem xét cache invalidation, freshness và concurrency; không thêm decorator nếu không có yêu cầu.

### 15.1. Logging decorator

Một decorator có thể đo thời gian hoặc ghi metrics mà không thay đổi contract:

```java
public class ObservedPaymentGateway implements PaymentGateway {

    private final PaymentGateway delegate;
    private final MeterRegistry meterRegistry;

    @Override
    public PaymentResult authorize(PaymentRequest request) {
        Timer.Sample sample = Timer.start(meterRegistry);
        try {
            return delegate.authorize(request);
        } finally {
            sample.stop(
                    meterRegistry.timer("payment.authorize.duration")
            );
        }
    }
}
```

Ví dụ minh họa ý tưởng; trong Spring, AOP hoặc instrumentation của client có thể đã cung cấp metrics. Không nên tạo decorator chỉ để lặp lại một cơ chế quan sát đã có.

## 16. Facade và orchestration cũng có vai trò

Một facade có thể cung cấp API đơn giản cho một nhóm subsystem phức tạp.

Ví dụ checkout cần:

- Đọc giỏ hàng.
- Kiểm tra tồn kho.
- Tính tổng tiền.
- Authorize thanh toán.
- Tạo đơn hàng.

Một `CheckoutService` điều phối các collaborator có trách nhiệm thật:

```java
@Service
public class CheckoutService {

    private final CartReader carts;
    private final InventoryAvailability inventory;
    private final PriceCalculator pricing;
    private final PaymentGateway payments;
    private final OrderStore orders;

    public CheckoutService(
            CartReader carts,
            InventoryAvailability inventory,
            PriceCalculator pricing,
            PaymentGateway payments,
            OrderStore orders) {
        this.carts = carts;
        this.inventory = inventory;
        this.pricing = pricing;
        this.payments = payments;
        this.orders = orders;
    }

    public OrderResult checkout(CustomerId customerId) {
        Cart cart = carts.load(customerId);
        inventory.requireAvailable(cart.items());
        Money total = pricing.calculate(cart);
        PaymentResult payment =
                payments.authorize(
                        new PaymentRequest(cart.reference(), total)
                );

        return orders.create(cart, total, payment);
    }
}
```

`CheckoutService` không phải pass-through wrapper vì nó chứa use-case orchestration. Nhưng không cần tự động tạo một interface `CheckoutService` nếu không có một client boundary hoặc nhu cầu thay thế tương ứng.

## 17. Khi interface trở thành abstraction quá rộng

Một interface có thể ban đầu hợp lý nhưng dần phình to:

```java
public interface FileStorage {
    void upload(...);
    byte[] download(...);
    void delete(...);
    void archive(...);
    void restore(...);
    void generatePublicUrl(...);
    void scanForMalware(...);
    void changeRetention(...);
    void listAllBuckets(...);
}
```

Một client chỉ cần upload file lại phụ thuộc vào cả chức năng restore, retention và quản trị bucket.

### 17.1. Tách theo khả năng client dùng

```java
public interface FileUploader {
    StoredFile upload(FileContent content);
}
```

```java
public interface FileReader {
    InputStream open(StoredFileId id);
}
```

```java
public interface FileRetentionManager {
    void archive(StoredFileId id);
    void restore(StoredFileId id);
}
```

### 17.2. Nhưng tránh một interface cho mỗi method

Nếu mọi thao tác cùng thuộc một contract mà cùng client sử dụng, tách quá nhỏ sẽ làm DI phức tạp và khiến client cần inject nhiều dependency.

Đặt câu hỏi:

- Nhóm method có cùng lý do thay đổi không?
- Cùng một client có cần chúng không?
- Có quyền hạn hoặc lifecycle khác nhau không?
- Có implementation nào chỉ thực hiện một phần hợp đồng không?

Tách theo vai trò và lý do thay đổi, không theo số lượng method.

## 18. Interface và abstract class: chọn theo bản chất

Interface thường phù hợp khi muốn định nghĩa capability mà các class không cùng cây kế thừa có thể thực hiện.

Abstract class phù hợp khi muốn chia sẻ:

- State chung.
- Constructor có logic.
- Protected helper methods.
- Một phần implementation.
- Template method có thứ tự xử lý cố định.

Ví dụ:

```java
public abstract class AbstractFileImporter {

    public final ImportResult importFile(Path path) {
        validate(path);
        List<Row> rows = readRows(path);
        return persist(rows);
    }

    protected abstract List<Row> readRows(Path path);

    protected abstract ImportResult persist(List<Row> rows);

    private void validate(Path path) {
        if (!Files.isReadable(path)) {
            throw new IllegalArgumentException(
                    "Input file is not readable"
            );
        }
    }
}
```

Các importer chia sẻ một algorithm, nhưng khác cách đọc và lưu. Đây có thể là một lý do dùng abstract class.

### 18.1. Có thể kết hợp interface và abstract class

```java
public interface FileImporter {
    ImportResult importFile(Path path);
}
```

```java
public abstract class AbstractFileImporter
        implements FileImporter {
    // Template implementation
}
```

Interface là contract cho client; abstract class là một cách reuse implementation. Không bắt buộc phải có cả hai nếu chỉ có một class đơn giản.

### 18.2. Java chỉ có một superclass

Nếu một class cần thực hiện nhiều capability độc lập, interface cho phép:

```java
class CloudFileAdapter
        implements FileReader, FileUploader, FileArchiver {
}
```

Điều này không có nghĩa nên gom mọi capability vào một class lớn. Hãy cân nhắc cohesion và ownership.

## 19. Default methods và sự tiến hóa của contract

Java interface có thể chứa `default` methods:

```java
public interface NotificationSender {

    void send(Notification notification);

    default void sendAll(List<Notification> notifications) {
        for (Notification notification : notifications) {
            send(notification);
        }
    }
}
```

Default method có thể bổ sung một behavior dùng chung mà không buộc mọi implementation viết lại.

### 19.1. Không dùng default method để giấu behavior không tương thích

Nếu một method mới yêu cầu semantics mà implementation cũ không thể thực hiện đúng, default implementation giả hoặc no-op có thể làm contract mất ý nghĩa.

Ví dụ:

```java
default void refund(String paymentReference) {
    // Không làm gì
}
```

Một payment gateway không hỗ trợ refund nhưng im lặng bỏ qua lệnh có thể gây sai nghiệp vụ nghiêm trọng.

Hãy:

- Tách capability riêng nếu không phải provider nào cũng hỗ trợ.
- Dùng một kết quả/exception biểu diễn unsupported behavior.
- Hoặc xác định refund là một phần bắt buộc của contract và yêu cầu mọi implementation tuân thủ.

### 19.2. Interface public là API cần quản lý

Thay đổi method signature của interface có thể ảnh hưởng tất cả implementation và client. Đừng coi interface là file không có chi phí bảo trì.

Nếu contract được nhiều module sử dụng, hãy xem xét backward compatibility, versioning và cách rollout.

## 20. Interface cho repository trong Spring Data

Spring Data JPA tự cung cấp nhiều repository abstractions:

```java
public interface SpringDataOrderRepository
        extends JpaRepository<OrderEntity, Long> {
}
```

Bạn không cần tạo thêm một interface trùng lặp chỉ để đổi tên:

```java
public interface OrderRepository
        extends SpringDataOrderRepository {
}
```

trừ khi `OrderRepository` có vai trò domain/application contract độc lập hoặc bổ sung hành vi có ý nghĩa.

### 20.1. Tách persistence port khỏi Spring Data

Nếu application/domain không muốn phụ thuộc Spring Data:

```java
public interface OrderStore {
    Optional<Order> find(OrderId id);
    void save(Order order);
}
```

Adapter:

```java
@Repository
public class JpaOrderStore implements OrderStore {

    private final SpringDataOrderRepository repository;
    private final OrderMapper mapper;

    public JpaOrderStore(
            SpringDataOrderRepository repository,
            OrderMapper mapper) {
        this.repository = repository;
        this.mapper = mapper;
    }

    @Override
    public Optional<Order> find(OrderId id) {
        return repository.findById(id.value())
                .map(mapper::toDomain);
    }

    @Override
    public void save(Order order) {
        repository.save(mapper.toEntity(order));
    }
}
```

Đây là abstraction có lý do: domain model và persistence model được tách ra, Spring Data không bị lộ vào application contract.

### 20.2. Không cần port riêng cho mọi repository trong mọi ứng dụng

Nếu dự án là CRUD service đơn giản, team chấp nhận Spring Data là một phần của application architecture và không có yêu cầu thay persistence boundary, dùng trực tiếp Spring Data repository có thể đủ.

Việc thêm port/adaptor cho từng repository đều có chi phí mapping và boilerplate. Hãy quyết định theo mục tiêu kiến trúc và nhu cầu thay thế thực tế.

## 21. Interface và external SDK

Một SDK của vendor thường có nhiều class, exception và model riêng. Không nên để các kiểu đó lan khắp business layer nếu muốn thay provider.

### 21.1. Coupling trực tiếp

```java
@Service
public class ShipmentService {

    private final VendorShippingClient client;

    public ShipmentService(VendorShippingClient client) {
        this.client = client;
    }

    public VendorShipmentResponse createShipment(
            VendorShipmentRequest request) {
        return client.createShipment(request);
    }
}
```

Application service đang phụ thuộc trực tiếp vendor request/response.

### 21.2. Contract của ứng dụng

```java
public interface ShipmentProvider {
    ShipmentResult create(ShipmentRequest request);
}
```

Adapter dịch kiểu:

```java
@Component
public class VendorShipmentProvider implements ShipmentProvider {

    private final VendorShippingClient client;

    @Override
    public ShipmentResult create(ShipmentRequest request) {
        VendorShipmentResponse response =
                client.createShipment(
                        new VendorShipmentRequest(
                                request.destination(),
                                request.packageWeight()
                        )
                );

        return new ShipmentResult(
                response.trackingCode(),
                response.estimatedDelivery()
        );
    }
}
```

Nếu ngày mai đổi SDK, phần lớn thay đổi nằm trong adapter. Đây là một boundary có giá trị.

### 21.3. Đừng bọc SDK chỉ để đổi tên

Nếu adapter chỉ gọi:

```java
return client.createShipment(request);
```

và mọi kiểu dữ liệu vẫn là vendor types, nó chưa bảo vệ application khỏi SDK. Cần xem có lý do nào để giữ lớp đó hay không.

## 22. Đặt tên interface theo capability và ngôn ngữ nghiệp vụ

Tên tốt cho biết client có thể làm gì:

```text
PaymentGateway
CustomerDirectory
InventoryAvailability
OrderStore
NotificationSender
ExchangeRateProvider
FileUploader
Clock
```

Tên kém rõ:

```text
IPaymentService
PaymentServiceInterface
PaymentServiceContractV2
BasePaymentService
CommonService
GenericRepository
```

Không phải mọi tên có chữ `Service` đều sai. Vấn đề là tên có diễn đạt capability và trách nhiệm hay chỉ mô tả rằng đây là interface.

### 22.1. Tránh hậu tố `I` nếu convention không yêu cầu

Java thường dùng:

```java
PaymentGateway
PartnerPaymentGateway
```

thay vì:

```java
IPaymentGateway
PaymentGatewayImpl
```

Implementation name có thể phản ánh provider hoặc cách triển khai. Nếu chỉ có một implementation và không cần phân biệt, class có thể mang tên capability mà không cần hậu tố `Impl`.

### 22.2. Tên method theo ngôn ngữ client

Nếu client cần tìm hồ sơ khách hàng, `find(CustomerId)` hoặc `lookup(CustomerId)` có thể phù hợp hơn một method vendor-specific như `fetchCustomerByExternalSystemCode()`.

Contract nên phản ánh ngôn ngữ của module sở hữu nó.

## 23. Tách interface theo lý do thay đổi

Một cách quyết định phạm vi contract là xem những method nào có cùng lý do thay đổi.

Ví dụ:

```java
public interface PaymentGateway {
    PaymentResult authorize(PaymentRequest request);
    PaymentResult capture(CaptureRequest request);
    RefundResult refund(RefundRequest request);
}
```

Nếu một client chỉ authorize, một client khác quản trị refund và một provider không hỗ trợ refund, có thể cần phân tách:

```java
public interface PaymentAuthorizer {
    PaymentResult authorize(PaymentRequest request);
}
```

```java
public interface PaymentCapturer {
    PaymentResult capture(CaptureRequest request);
}
```

```java
public interface PaymentRefunder {
    RefundResult refund(RefundRequest request);
}
```

Nhưng nếu mọi client đều thực hiện cùng lifecycle payment và tất cả providers đều phải hỗ trợ đủ ba bước, một `PaymentGateway` thống nhất có thể rõ hơn.

**Số interface nên phản ánh các vai trò và lý do thay đổi độc lập**, không phản ánh số method hoặc số class một cách máy móc.

## 24. Interface và transaction boundary

Một interface không tự tạo transaction. `@Transactional` và transaction manager mới điều khiển transaction behavior theo cấu hình.

Ví dụ:

```java
public interface OrderStore {
    void save(Order order);
}
```

```java
@Service
public class PlaceOrder {

    private final OrderStore orders;

    public PlaceOrder(OrderStore orders) {
        this.orders = orders;
    }

    @Transactional
    public void execute(Order order) {
        orders.save(order);
    }
}
```

`PlaceOrder` là application service sở hữu transaction boundary. `OrderStore` là contract persistence.

Không cần tạo một lớp `TransactionalOrderService` chỉ chuyển lời gọi tới `PlaceOrder` nếu nó không thêm policy hoặc ranh giới nào.

### 24.1. Tránh để adapter quyết định transaction của toàn use case

Nếu một use case cần ghi nhiều aggregate/repository trong cùng transaction, đặt transaction boundary ở nơi điều phối use case thường dễ hiểu hơn đặt `@Transactional` rải rác ở mọi adapter.

Tuy nhiên, transaction boundary cuối cùng phụ thuộc kiến trúc, framework và consistency requirements. Interface chỉ giúp định nghĩa điểm phụ thuộc, không quyết định transaction semantics.

## 25. Interface và Spring AOP proxy

Spring AOP có thể sử dụng JDK dynamic proxy hoặc class-based proxy tùy cấu hình và trường hợp.

### 25.1. JDK proxy

JDK dynamic proxy dựa trên interface. Client inject theo interface có thể nhận proxy phù hợp:

```java
public CheckoutService(PaymentGateway gateway) {
    this.gateway = gateway;
}
```

Nếu bean được expose bằng JDK proxy, inject concrete implementation class có thể không tương thích kiểu.

### 25.2. CGLIB/class-based proxy

Class-based proxy được tạo bằng subclass trong các trường hợp phù hợp, vì vậy có thể assignable với concrete class. Nhưng final class hoặc method có giới hạn với subclass proxy.

### 25.3. Interface không phải chỉ để tránh lỗi proxy

Interface nên được thiết kế theo contract nghiệp vụ hoặc boundary. Việc inject theo interface thường giúp tương thích với JDK proxy, nhưng không nên tạo một interface vô nghĩa chỉ để tránh một lỗi cast.

## 26. Cấu hình implementation trong Spring

### 26.1. Một implementation mặc định

```java
@Component
public class JpaOrderStore implements OrderStore {
}
```

Client:

```java
public OrderService(OrderStore orderStore) {
    this.orderStore = orderStore;
}
```

### 26.2. Chọn bằng qualifier

```java
@Component("primaryOrderStore")
public class JpaOrderStore implements OrderStore {
}
```

```java
@Component("archiveOrderStore")
public class ArchiveOrderStore implements OrderStore {
}
```

Client:

```java
public OrderQueryService(
        @Qualifier("archiveOrderStore") OrderStore store) {
    this.store = store;
}
```

### 26.3. Chọn bằng profile

```java
@Component
@Profile("test")
public class InMemoryOrderStore implements OrderStore {
}
```

```java
@Component
@Profile("production")
public class JpaOrderStore implements OrderStore {
}
```

### 26.4. Chọn bằng configuration

Với logic chọn phức tạp, có thể định nghĩa bean tại configuration class:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    @ConditionalOnProperty(
            name = "payment.provider",
            havingValue = "sandbox"
    )
    PaymentGateway sandboxGateway() {
        return new SandboxPaymentGateway();
    }
}
```

Đảm bảo chỉ có một implementation phù hợp hoặc lựa chọn rõ ràng khi có nhiều bean.

## 27. Khi nào nên bắt đầu bằng class rồi trích interface sau?

Một lựa chọn thực tế là không tạo abstraction trước khi biết ranh giới cần bảo vệ.

### 27.1. Bắt đầu đơn giản

```java
@Service
public class DiscountCalculator {

    public Money calculate(Cart cart) {
        // Quy tắc giảm giá
    }
}
```

Ở thời điểm này:

- Có một chính sách giảm giá.
- Không có provider bên ngoài.
- Logic thuần, dễ test trực tiếp.
- Không có client cần thay implementation.

Class trực tiếp có thể là đủ.

### 27.2. Khi yêu cầu mở rộng xuất hiện

Sau này có:

- Chính sách theo tenant.
- Chính sách theo chương trình loyalty.
- Chính sách theo thị trường.

Có thể trích:

```java
public interface DiscountPolicy {
    Money calculate(Cart cart);
}
```

Các implementation:

```java
@Component
public class RetailDiscountPolicy implements DiscountPolicy {
}
```

```java
@Component
public class LoyaltyDiscountPolicy implements DiscountPolicy {
}
```

Lúc này interface được thiết kế dựa trên các behavior và điểm thay thế đã hiểu rõ.

### 27.3. Không phải lúc nào cũng cần interface

Nếu chỉ thêm một nhánh `if` nhỏ trong calculator và không có nhu cầu chọn strategy độc lập, một interface strategy có thể quá mức.

Đánh giá mức độ thay đổi và complexity thực tế trước khi tạo thêm abstraction.

## 28. Câu hỏi quyết định trước khi tách interface

Hãy dùng các câu hỏi sau trong design review:

### Câu hỏi 1 — Có client cụ thể nào cần abstraction?

Nếu không có client nào sử dụng interface ngoài implementation của chính nó, hãy xem lại lý do tồn tại.

### Câu hỏi 2 — Có một quyết định triển khai cần được cô lập không?

Ví dụ vendor, storage engine, transport, algorithm hoặc policy có thể thay đổi độc lập.

### Câu hỏi 3 — Contract có thuộc về ngôn ngữ của client không?

Một interface mang tên `StripeClientFacade` vẫn có thể làm business layer phụ thuộc Stripe.

### Câu hỏi 4 — Các method có cùng vai trò không?

Nếu client chỉ dùng một phần interface lớn, cân nhắc tách theo ISP.

### Câu hỏi 5 — Implementation có thể tuân thủ cùng semantics không?

Nếu hai implementation trả kết quả khác ý nghĩa hoặc có side effects khác nhau, contract cần được làm rõ.

### Câu hỏi 6 — Lớp trung gian có thêm behavior không?

Nếu nó chỉ chuyển tiếp từng method, cân nhắc bỏ đi.

### Câu hỏi 7 — Chi phí abstraction có xứng đáng?

Interface, adapter, mapper, configuration và test contract đều có chi phí. Chúng có thể đáng giá ở boundary quan trọng, nhưng không cần áp dụng cho mọi class.

## 29. Các anti-pattern cần nhận diện

### 29.1. Interface cho mọi service theo template

```text
CustomerService
CustomerServiceImpl
OrderService
OrderServiceImpl
ProductService
ProductServiceImpl
```

Nếu các interface chỉ mirror implementation, có thể xóa tầng không cần thiết và giữ service class trực tiếp.

### 29.2. Interface tên chung chung

```java
public interface BaseService<T> {
    T process(T value);
}
```

Một abstraction generic không có semantics cụ thể có thể khiến client khó hiểu hành vi thực tế.

Generic interface hữu ích khi có một contract chung thực sự, không phải để gom những method chỉ tình cờ có cùng chữ ký.

### 29.3. Adapter không chuyển đổi gì

```java
public Order find(String id) {
    return delegate.find(id);
}
```

Nếu không thêm behavior hoặc boundary, lớp này có thể là pass-through.

### 29.4. Interface phơi bày framework

```java
public interface OrderService {
    ResponseEntity<OrderEntity> process(
            HttpServletRequest request
    );
}
```

Contract application/domain bị gắn với Spring MVC, Servlet và persistence entity. Client không thể dùng nó độc lập.

Tách HTTP concerns ở controller và giữ contract nghiệp vụ bằng kiểu dữ liệu phù hợp.

### 29.5. Interface chứa mọi method vì “implementation nào cũng có”

Hai class cùng có method `save()` không có nghĩa chúng thực hiện cùng contract. Một class lưu file, class khác lưu đơn hàng; đặt chúng vào một `SaveService` chung có thể làm abstraction mất ý nghĩa.

### 29.6. Thêm interface nhưng vẫn expose implementation type

```java
private final StripePaymentGateway gateway;
```

Nếu client vẫn inject concrete class, interface mới có thể không đem lại lợi ích cho client đó.

### 29.7. Tạo interface rồi vẫn kiểm tra implementation bằng `instanceof`

```java
if (gateway instanceof StripePaymentGateway) {
    // ...
}
```

Client vẫn biết chi tiết provider. Nếu hành vi cần khác nhau, hãy đưa khả năng đó vào contract hoặc dùng strategy phù hợp thay vì kiểm tra class cụ thể.

### 29.8. Interface chỉ tồn tại để mock mọi thứ

Mocking mọi class làm test phụ thuộc vào cấu trúc nội bộ và có thể tạo nhiều test tương tác mong manh. Dùng interface khi nó là seam có ý nghĩa, không phải mục tiêu tự thân.

## 30. Refactor an toàn từ pass-through wrapper

Giả sử hiện tại:

```text
Controller
   |
   v
OrderFacade
   |
   v
OrderService
   |
   v
Repository
```

`OrderFacade` chỉ gọi `OrderService` với cùng đối số và trả cùng kết quả.

### Bước 1 — Xác nhận không có behavior ẩn

Kiểm tra:

- Transaction annotation.
- Security annotation.
- Cache.
- Validation.
- Metrics/logging có ý nghĩa.
- Mapping.
- Retry/timeout.
- Event publication.
- Contract được module khác sử dụng.

Một lớp nhìn như pass-through có thể vẫn mang behavior từ annotation hoặc proxy.

### Bước 2 — Xác định owner của use case

Nếu `OrderService` là nơi thực hiện nghiệp vụ, controller có thể inject trực tiếp service.

### Bước 3 — Chuyển client

```java
@RestController
public class OrderController {

    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }
}
```

### Bước 4 — Xóa wrapper nếu không còn client

Chỉ sau khi xác nhận không có bean, module hoặc API khác phụ thuộc nó.

### Bước 5 — Giữ boundary thật

Không xóa `OrderStore` hoặc `PaymentGateway` nếu chúng vẫn bảo vệ một quyết định hạ tầng có thể thay thế.

### Bước 6 — Test behavior quan trọng

Chạy test cho controller/service contract liên quan. Không refactor hàng loạt interface chỉ vì một lớp wrapper được xác định là dư thừa.

## 31. Module boundaries và package design

Một cách tổ chức đơn giản:

```text
com.example.shop
├── checkout
│   ├── application
│   │   ├── CheckoutService.java
│   │   └── InventoryAvailability.java
│   └── web
│       └── CheckoutController.java
├── inventory
│   └── adapter
│       └── JpaInventoryAvailability.java
└── payment
    ├── application
    │   └── PaymentGateway.java
    └── adapter
        ├── PartnerPaymentGateway.java
        └── SandboxPaymentGateway.java
```

Trong ví dụ, `checkout.application` định nghĩa nhu cầu `InventoryAvailability`; adapter inventory thực hiện contract. `payment.application` định nghĩa `PaymentGateway`; provider adapters implement contract.

### 31.1. Không bắt buộc mọi project phải dùng package `port` và `adapter`

Có thể đặt:

```text
checkout/
  port/
  service/
```

hoặc:

```text
checkout/
  application/
  infrastructure/
```

Điều quan trọng là hướng phụ thuộc có thể nhìn thấy và tên package giúp người đọc hiểu boundary.

### 31.2. Tránh package cycle

Nếu:

```text
application -> adapter
adapter -> application
```

và application import trực tiếp vendor/JPA classes, ranh giới đã bị rò rỉ.

Trong ports-and-adapters, adapter phụ thuộc contract của application; application không cần import adapter implementation.

### 31.3. Interface không thay thế module architecture

Một interface trong cùng package không tự tạo module boundary. Nếu muốn enforce dependency direction, có thể dùng module structure, build modules hoặc architecture tests phù hợp.

## 32. Thiết kế contract để dễ thay implementation

Một contract có thể thay thế tốt cần quan tâm:

### 32.1. Kiểu dữ liệu ổn định

Ưu tiên domain/application types:

```java
PaymentRequest
PaymentResult
Money
PaymentReference
```

Hạn chế expose:

```java
StripeRequest
JpaOrderEntity
HttpServletRequest
ResponseEntity
```

nếu client không cần phụ thuộc các kiểu đó.

### 32.2. Exception semantics nhất quán

Một adapter có thể chuyển vendor exception thành application exception:

```java
public class PaymentUnavailableException
        extends RuntimeException {

    public PaymentUnavailableException(String message) {
        super(message);
    }
}
```

Adapter:

```java
try {
    return client.authorize(request);
} catch (PartnerTimeoutException ex) {
    throw new PaymentUnavailableException(
            "Payment provider is unavailable"
    );
}
```

Không đưa token, raw request hoặc credential vào exception message.

### 32.3. Timeout và retry semantics

Nếu một implementation tự retry 5 lần còn implementation khác không retry, client có thể có latency và side effects khác nhau.

Quyết định retry nên được đặt ở một nơi có trách nhiệm rõ ràng và được phản ánh trong contract/operation policy.

### 32.4. Idempotency

Một payment authorization có thể bị retry do timeout. Contract cần xác định cách dùng idempotency key hoặc reference để tránh charge trùng.

Interface chỉ định method signature không đủ để bảo đảm idempotency. Behavior cần được mô tả và test.

### 32.5. Null và Optional

Tránh để implementation tùy ý trả `null` hoặc empty theo những ý nghĩa khác nhau.

Chọn contract rõ:

```java
Optional<CustomerProfile> find(CustomerId id);
```

hoặc:

```java
CustomerProfile get(CustomerId id);
```

và định nghĩa rõ trường hợp không tìm thấy.

## 33. Đánh giá một ví dụ thiết kế

Giả sử code:

```java
public interface EmailService {
    void send(String to, String subject, String body);
}
```

```java
@Service
public class EmailServiceImpl implements EmailService {

    private final SmtpClient smtpClient;

    public EmailServiceImpl(SmtpClient smtpClient) {
        this.smtpClient = smtpClient;
    }

    @Override
    public void send(String to, String subject, String body) {
        smtpClient.send(to, subject, body);
    }
}
```

Có nên giữ interface?

**Giữ** nếu:

- Ứng dụng có SMTP, provider API và fake sender khác nhau.
- Nhiều module cần contract gửi thông báo.
- Muốn cô lập vendor/transport khỏi application.
- Có test seam cần thiết cho một side effect.

**Cân nhắc bỏ** nếu:

- Chỉ có một class gửi email.
- Interface và implementation luôn thay đổi cùng nhau.
- Không có module boundary cần bảo vệ.
- Interface không định nghĩa semantics ngoài việc đổi tên method.
- Không có kế hoạch hoặc nhu cầu thực tế về implementation khác.

Một phương án tốt hơn cho nhiều ứng dụng là đổi contract thành capability:

```java
public interface NotificationSender {
    void send(Notification notification);
}
```

Tên này diễn đạt nhu cầu rộng hơn SMTP. Nhưng chỉ nên làm vậy nếu application thực sự coi email là một dạng notification và contract có semantics chung.

## 34. Bài tập thực hành

### Bài 1 — Phân loại abstraction

Với mỗi cặp `X` và `XImpl`, hãy xác định:

- Interface có client cụ thể nào sử dụng không?
- Có implementation thay thế nào được yêu cầu không?
- Interface có thêm semantics ngoài method signature không?
- Có nên giữ interface hay dùng class trực tiếp?

Viết lý do cho từng quyết định.

### Bài 2 — Thiết kế PaymentGateway

Một ứng dụng thanh toán hỗ trợ provider production và sandbox.

Thiết kế:

- `PaymentRequest`.
- `PaymentResult`.
- `PaymentGateway`.
- Hai adapter.
- Cấu hình Spring chọn theo profile.

Giải thích vì sao application service không nên phụ thuộc SDK của provider.

### Bài 3 — Tách interface theo ISP

Một interface `UserManagement` có tám method cho đọc, ghi, xóa và quản trị tài khoản.

Tạo các contract nhỏ theo vai trò client. Tránh tạo một interface riêng cho từng method nếu những method có cùng client và cùng lý do thay đổi.

### Bài 4 — Nhận diện pass-through wrapper

Cho một lớp `OrderFacade` chỉ chuyển mọi method sang `OrderService`.

Xác định annotation, transaction, security, mapping hoặc metrics có thể tạo behavior ẩn. Nếu không có, đề xuất loại bỏ wrapper.

### Bài 5 — Adapter thực sự

Tạo `CustomerDirectory` và một adapter cho SDK giả lập trả `VendorCustomer`.

Map sang `CustomerProfile`, chuyển exception vendor sang exception application và không expose vendor types cho client.

### Bài 6 — Fake implementation

Viết `FakePaymentGateway` cho unit test của `AuthorizePayment`.

Cho fake ghi nhận request và trả kết quả xác định. Viết test xác nhận behavior của use case, không gọi provider thật.

### Bài 7 — Contract test

Viết một bộ contract tests chạy trên sandbox adapter và fake adapter để kiểm tra semantics chung:

- Kết quả authorization thành công.
- Kết quả bị từ chối.
- Timeout/unavailable.
- Idempotency behavior nếu contract yêu cầu.

Không cho phép mọi kết quả đều pass mà không assert expected outcome.

### Bài 8 — Interface hay abstract class?

Có ba importer CSV, JSON và XML. Chúng chia sẻ validation, error handling và quy trình persist, nhưng khác cách đọc file.

Đề xuất contract interface, abstract base class hoặc kết hợp. Giải thích trách nhiệm của từng abstraction.

### Bài 9 — Interface cho repository

Một dự án CRUD chỉ dùng Spring Data JPA. Hãy đưa ra hai phương án:

1. Inject trực tiếp Spring Data repository.
2. Tạo domain `OrderStore` và JPA adapter.

Nêu trade-off về coupling, mapping, test và khả năng thay persistence.

### Bài 10 — Conditional implementations

Tạo hai implementation cùng interface và chọn bằng `@ConditionalOnProperty`.

Kiểm tra trường hợp thiếu property, giá trị không hợp lệ và hai bean cùng được đăng ký.

### Bài 11 — Loại interface trùng lặp

Refactor một cặp `TaxCalculator` và `TaxCalculatorImpl` chỉ có một implementation và không có client boundary độc lập.

Giữ behavior, chuyển client sang class trực tiếp và xóa abstraction thừa nếu không có consumer khác.

### Bài 12 — Decorator có giá trị

Tạo `CachingCustomerDirectory` bọc `CustomerDirectory`.

Xác định behavior mới, invalidation strategy và test cache hit/miss. Giải thích vì sao decorator này khác pass-through wrapper.

### Bài 13 — Contract semantics

Hai implementation `FileStorage` có một implementation trả `null` khi không tìm thấy, implementation còn lại ném exception.

Thiết kế lại contract để hành vi nhất quán và viết tests dùng chung.

### Bài 14 — Dependency direction

Vẽ dependency graph của một ứng dụng có `CheckoutService`, `PaymentGateway` và `PartnerPaymentAdapter`.

Đảm bảo application layer không import SDK hoặc adapter implementation. Giải thích hướng dependency của DIP.

### Bài 15 — Quyết định theo yêu cầu thay đổi

Một class `ExchangeRateCalculator` hiện chỉ có một thuật toán. Sau này sản phẩm có thể cần lấy tỷ giá từ nhiều nguồn.

Đưa ra quyết định có tạo interface ngay không. Nếu có, nêu client và contract. Nếu chưa, giải thích thời điểm thích hợp để trích abstraction.

### Bài 16 — Design review

Review một module có:

```text
OrderController
OrderFacade
OrderFacadeImpl
OrderService
OrderServiceImpl
OrderManager
OrderManagerImpl
OrderRepository
OrderRepositoryImpl
```

Không xóa mọi interface theo cảm tính. Xác định class nào có behavior, interface nào bảo vệ boundary, adapter nào thực sự chuyển đổi và lớp nào chỉ chuyển tiếp.

## 35. Ghi nhớ

Tách interface khi có **một client cần một contract ổn định** và một quyết định triển khai cần được thay đổi độc lập: nhiều provider, nhiều strategy, ranh giới persistence/network, module API hoặc một test seam có ý nghĩa. Hãy đặt contract theo capability mà client cần, giữ method vừa đủ và định nghĩa semantics nhất quán giữa các implementation.

Interface không phải yêu cầu bắt buộc cho mọi service. Nếu một class đơn giản có một implementation, không có boundary cần bảo vệ và không có nhu cầu thay thế cụ thể, dùng class trực tiếp thường rõ ràng hơn. Đừng tạo `XService`/`XServiceImpl` theo thói quen nếu interface chỉ sao chép toàn bộ method.

Một lớp trung gian chỉ chuyển lời gọi sang delegate mà không thêm behavior, mapping, policy, lifecycle hoặc abstraction độc lập thường là pass-through wrapper và có thể được loại bỏ. Ngược lại, adapter, decorator, facade hoặc application service có trách nhiệm điều phối thực sự vẫn có giá trị dù chúng gọi collaborator khác.

**Thiết kế tốt không đo bằng số interface.** Nó đo bằng việc client phụ thuộc đúng điều nó cần, chi tiết có thể thay đổi ở ranh giới phù hợp và mỗi lớp đều có một vai trò dễ giải thích.
