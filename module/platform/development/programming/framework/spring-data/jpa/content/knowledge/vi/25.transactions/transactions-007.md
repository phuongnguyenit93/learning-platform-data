# Quy tắc rollback, checked exception và rollbackFor

Trong Spring Data JPA, một phương thức có thể đã ghi hoặc thay đổi entity nhưng transaction vẫn được commit khi phương thức kết thúc bằng một checked exception. Nguyên nhân là quy tắc mặc định của Spring: transaction rollback khi có `RuntimeException` hoặc `Error` thoát khỏi ranh giới transaction; checked exception mặc định không kích hoạt rollback. Khi nghiệp vụ yêu cầu hủy toàn bộ thay đổi trong trường hợp checked exception, hãy khai báo `rollbackFor` trên `@Transactional`.

## 1. Transaction quyết định commit hay rollback như thế nào?

Khi một lời gọi đi qua transaction proxy của Spring, transaction interceptor sẽ bắt đầu transaction mới hoặc tham gia transaction đang tồn tại. Sau đó phương thức nghiệp vụ chạy trong transaction đó.

- Phương thức kết thúc bình thường: Spring yêu cầu transaction manager commit.
- Phương thức kết thúc bằng exception: Spring đối chiếu exception với các rollback rule của transaction.
- Rule yêu cầu rollback: transaction được đánh dấu rollback-only hoặc được rollback theo trạng thái propagation.
- Rule không yêu cầu rollback: Spring tiếp tục quy trình commit, dù exception vẫn được truyền về phía caller.

Quy tắc mặc định của `@Transactional` trong Spring là:

| Loại kết thúc | Hành vi mặc định |
|---|---|
| Trả về bình thường | Commit |
| `RuntimeException` thoát khỏi phương thức | Rollback |
| `Error` thoát khỏi phương thức | Rollback |
| Checked exception thoát khỏi phương thức | Commit |

Điểm cần nhớ là Spring xét loại exception thoát khỏi phương thức được quản lý transaction, chứ không chỉ xét việc trong thân hàm có câu lệnh `throw` hay không. Nếu exception bị bắt và phương thức trả về bình thường, interceptor thường xem đó là kết thúc thành công.

## 2. Phân biệt checked exception và unchecked exception

Java chia exception thành hai nhóm chính:

~~~text
Throwable
├── Error
└── Exception
    ├── RuntimeException (unchecked)
    └── Các lớp Exception còn lại (checked)
~~~

**Unchecked exception** là `RuntimeException` và các lớp con của nó. Trình biên dịch không bắt buộc khai báo hoặc bắt nhóm exception này. Ví dụ: `IllegalArgumentException`, `NullPointerException` và nhiều exception thuộc Spring `DataAccessException`.

**Checked exception** là các lớp con của `Exception` nhưng không kế thừa `RuntimeException`. Trình biên dịch yêu cầu phương thức bắt exception hoặc khai báo bằng `throws`. Ví dụ: `IOException` hoặc một exception nghiệp vụ tự định nghĩa kế thừa trực tiếp `Exception`.

`Error` là một nhánh riêng dưới `Throwable`, không phải checked exception. Spring mặc định rollback khi `Error` thoát khỏi transaction.

Trong ứng dụng Spring Data JPA, nhiều lỗi truy cập dữ liệu được chuyển thành unchecked exception. Tuy nhiên, exception nghiệp vụ do ứng dụng định nghĩa có thể là checked exception. Vì vậy không nên suy luận rằng mọi exception phát sinh trong một service đều tự động làm transaction rollback.

## 3. Vì sao checked exception có thể làm dữ liệu được commit?

Xét phương thức minh họa sau. Giả sử `OrderRepository` lưu đơn hàng và `InventoryUnavailableException` là checked exception.

~~~java
@Transactional
public void createOrder(Order order) throws InventoryUnavailableException {
    orderRepository.save(order);

    if (!inventoryService.hasEnoughStock(order)) {
        throw new InventoryUnavailableException("Không đủ hàng");
    }
}
~~~

Nếu `InventoryUnavailableException` kế thừa `Exception` và không có rollback rule bổ sung, Spring mặc định không rollback chỉ vì exception này. Khi exception thoát khỏi phương thức, transaction có thể được commit; đơn hàng đã lưu có thể vẫn tồn tại dù caller nhận được lỗi.

Đây là khác biệt quan trọng giữa hai việc:

- Caller nhận được exception: luồng gọi biết thao tác nghiệp vụ gặp lỗi.
- Transaction rollback: các thay đổi cơ sở dữ liệu thuộc transaction bị hủy.

Hai việc này không đồng nghĩa. Một phương thức có thể ném exception nhưng transaction vẫn commit nếu rollback rule không khớp.

## 4. Dùng rollbackFor để rollback khi có checked exception

Thuộc tính `rollbackFor` khai báo loại exception phải làm transaction rollback. Nên truyền trực tiếp class của exception để rule có kiểu rõ ràng.

~~~java
public class InventoryUnavailableException extends Exception {
    public InventoryUnavailableException(String message) {
        super(message);
    }
}
~~~

~~~java
@Service
@RequiredArgsConstructor
public class OrderService {
    private final OrderRepository orderRepository;
    private final InventoryService inventoryService;

    @Transactional(rollbackFor = InventoryUnavailableException.class)
    public void createOrder(Order order)
            throws InventoryUnavailableException {
        orderRepository.save(order);

        if (!inventoryService.hasEnoughStock(order)) {
            throw new InventoryUnavailableException("Không đủ hàng");
        }
    }
}
~~~

Khi `InventoryUnavailableException` thoát khỏi `createOrder`, rollback rule khớp và Spring rollback transaction. Các thay đổi cơ sở dữ liệu thực hiện trong transaction đó sẽ bị hủy.

Có thể khai báo nhiều loại exception:

~~~java
@Transactional(
    rollbackFor = {
        InventoryUnavailableException.class,
        IOException.class
    }
)
public void processOrder(Order order)
        throws InventoryUnavailableException, IOException {
    // Các thao tác thuộc cùng transaction
}
~~~

Nếu muốn mọi exception thuộc nhánh `Exception` đều làm rollback, có thể dùng:

~~~java
@Transactional(rollbackFor = Exception.class)
public void executeBusinessOperation() throws Exception {
    // Bao gồm checked exception và RuntimeException
}
~~~

`Exception.class` bao gồm cả `RuntimeException` vì `RuntimeException` kế thừa `Exception`. Hành vi rollback mặc định cho `Error` vẫn được áp dụng. Chỉ dùng rule rộng khi đó thực sự là chính sách của nghiệp vụ; nếu không, khai báo đúng exception cần xử lý sẽ dễ đọc và ít gây tác dụng phụ hơn.

Ngoài `rollbackFor`, annotation còn có `rollbackForClassName` để khai báo rule theo tên lớp exception. Đây là dạng so khớp chuỗi tên lớp và có thể vô tình khớp các tên lớp tương tự. Ưu tiên `rollbackFor = SomeException.class` khi có thể.

## 5. Dùng noRollbackFor khi muốn commit dù có exception

`noRollbackFor` khai báo exception mà Spring không nên dùng làm lý do rollback. Ví dụ, nghiệp vụ có thể coi một cảnh báo sau khi lưu dữ liệu là kết quả chấp nhận được:

~~~java
@Transactional(noRollbackFor = DuplicateNoticeException.class)
public void registerCustomer(Customer customer)
        throws DuplicateNoticeException {
    customerRepository.save(customer);

    if (customer.hasDuplicateContact()) {
        throw new DuplicateNoticeException("Thông tin liên hệ đã tồn tại");
    }
}
~~~

Nếu `DuplicateNoticeException` thoát khỏi phương thức và không có rollback rule mạnh hơn yêu cầu rollback, transaction có thể commit. Caller vẫn nhận được exception.

Chỉ dùng `noRollbackFor` khi việc giữ lại thay đổi là chủ đích nghiệp vụ. Nếu dữ liệu đã ghi cần bị hủy khi exception xảy ra, không khai báo exception đó trong `noRollbackFor`.

Spring có thể áp dụng nhiều rollback rule cùng lúc. Rule khớp cụ thể nhất với exception thực tế sẽ quyết định hành vi. Vì vậy, khi kết hợp `rollbackFor` và `noRollbackFor`, hãy kiểm tra quan hệ kế thừa của các exception để tránh cấu hình mâu thuẫn hoặc khó hiểu.

## 6. Những điều kiện ảnh hưởng đến rollback

### Exception phải đi qua ranh giới transaction

Ví dụ dưới đây bắt exception và không ném lại:

~~~java
@Transactional
public void createOrder(Order order) {
    try {
        orderRepository.save(order);
        inventoryService.reserve(order);
    } catch (InventoryUnavailableException ex) {
        log.warn("Không thể giữ hàng: {}", ex.getMessage());
    }
}
~~~

Sau khối `catch`, phương thức kết thúc bình thường. Transaction interceptor không nhìn thấy exception thoát ra, nên transaction có thể commit. Việc ghi log không tự động đánh dấu rollback.

Nếu nghiệp vụ bắt buộc phải rollback nhưng vẫn cần xử lý exception tại chỗ, có thể đánh dấu transaction rollback-only:

~~~java
@Transactional
public void createOrder(Order order) {
    try {
        orderRepository.save(order);
        inventoryService.reserve(order);
    } catch (InventoryUnavailableException ex) {
        TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
        log.warn("Đơn hàng sẽ rollback: {}", ex.getMessage());
    }
}
~~~

Cách này cần có transaction đang hoạt động. Thông thường, ném exception phù hợp ra khỏi service boundary và cấu hình `rollbackFor` sẽ dễ hiểu hơn việc bắt exception rồi đánh dấu thủ công.

### Phải đi qua Spring proxy

Trong chế độ proxy mặc định, `@Transactional` được áp dụng khi lời gọi đi qua proxy Spring. Một phương thức trong cùng object gọi trực tiếp phương thức khác có `@Transactional` (self-invocation) sẽ không đi qua proxy; annotation ở phương thức được gọi có thể không được áp dụng như mong đợi.

Ví dụ, nếu `methodA()` gọi trực tiếp `this.methodB()`, không nên mặc định rằng transaction rule của `methodB()` sẽ được kích hoạt độc lập. Hãy đặt ranh giới transaction ở service method được gọi từ bean khác hoặc tổ chức bean sao cho lời gọi đi qua proxy.

### Phương thức tham gia transaction hiện có

Với propagation mặc định `REQUIRED`, phương thức được gọi thường tham gia transaction hiện có. Nếu một lời gọi transactional bên trong đánh dấu transaction chung là rollback-only, việc phương thức bên ngoài bắt exception rồi tiếp tục không làm transaction trở lại trạng thái có thể commit. Khi bên ngoài kết thúc và cố commit, caller có thể nhận `UnexpectedRollbackException`.

Điều này giúp tránh tình huống caller tưởng rằng transaction đã commit trong khi một phần bên trong đã yêu cầu rollback. Khi thiết kế nhiều service cùng tham gia một transaction, cần hiểu exception nào thoát khỏi từng proxy và rollback rule nào được áp dụng.

## 7. Đặt transaction boundary ở đâu trong Spring Data JPA?

Thông thường, đặt `@Transactional` ở service method đại diện cho một nghiệp vụ hoàn chỉnh. Ví dụ, tạo đơn hàng có thể cần lưu đơn, cập nhật tồn kho và ghi chi tiết liên quan. Các thao tác cơ sở dữ liệu này nên nằm trong cùng transaction nếu nghiệp vụ yêu cầu tất cả cùng thành công hoặc cùng rollback.

~~~java
@Service
@RequiredArgsConstructor
public class CheckoutService {
    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    @Transactional(rollbackFor = CheckoutException.class)
    public void checkout(Order order) throws CheckoutException {
        orderRepository.save(order);
        inventoryRepository.reserve(order.getItems());

        if (inventoryRepository.hasReservationFailure(order)) {
            throw new CheckoutException("Không thể giữ đủ hàng");
        }
    }
}
~~~

Spring Data JPA repository có transaction configuration cho các phương thức CRUD được kế thừa. Tuy vậy, transaction ở service giúp gom nhiều lời gọi repository vào cùng một ranh giới nghiệp vụ và cho phép khai báo rollback rule ở nơi hiểu đầy đủ mục đích của thao tác.

Không nên dựa vào transaction riêng lẻ của từng repository để thay thế transaction cho toàn bộ use case. Nếu mỗi lời gọi repository chạy trong transaction độc lập, một thao tác có thể đã commit trước khi thao tác tiếp theo thất bại.

## 8. Kiểm thử hành vi rollback

Nên kiểm thử bằng integration test với cơ sở dữ liệu kiểm thử và gọi service qua Spring context. Test cần xác nhận đồng thời hai điều: caller nhận đúng checked exception và dữ liệu được ghi trước exception không còn trong database.

~~~java
@SpringBootTest
class OrderServiceRollbackTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void rollsBackWhenCheckedExceptionIsThrown() {
        UUID orderId = UUID.randomUUID();
        Order order = new Order(orderId);

        assertThatThrownBy(() -> orderService.createOrder(order))
                .isInstanceOf(InventoryUnavailableException.class);

        assertThat(orderRepository.existsById(orderId)).isFalse();
    }
}
~~~

Ví dụ giả định constructor `Order(UUID)` và service đã lưu entity trước khi ném `InventoryUnavailableException`. Test method không được bao trong một transaction test khiến kết quả đọc bị che khuất bởi transaction bên ngoài. Hãy bảo đảm dữ liệu kiểm thử được cô lập và cơ sở dữ liệu thực sự thực hiện transaction.

Một số lưu ý khi kiểm thử:

- Gọi bean service được inject để lời gọi đi qua proxy.
- Kiểm tra database sau khi service đã kết thúc và transaction đã rollback.
- Dùng một ID duy nhất cho mỗi test để tránh dữ liệu cũ làm sai kết quả.
- Không chỉ kiểm tra exception; cần xác nhận trạng thái dữ liệu.
- Nếu muốn kiểm tra SQL hoặc constraint, lưu ý JPA có thể trì hoãn câu lệnh cho tới lúc flush hoặc commit.

## 9. Rollback database không hoàn tác mọi side effect

Transaction JPA chỉ quản lý tài nguyên tham gia transaction, thường là database. Nếu service gửi email, gọi HTTP API, ghi file hoặc phát thông điệp ra hệ thống bên ngoài rồi sau đó rollback, những side effect đó không tự động được hoàn tác.

Ví dụ: đơn hàng được lưu, email xác nhận đã gửi, sau đó một checked exception làm transaction rollback. Database không còn đơn hàng nhưng email đã được gửi. Với nghiệp vụ cần đồng bộ các hành động này, hãy cân nhắc transactional outbox, phát sự kiện sau commit hoặc một quy trình bù trừ phù hợp. Không nên giả định `rollbackFor` có thể hoàn tác lời gọi tới hệ thống bên ngoài.

## 10. Lỗi thường gặp và cách xử lý

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Checked exception không được khai báo trong `rollbackFor` | Transaction có thể commit dù caller nhận exception | Khai báo đúng exception class |
| Bắt exception rồi trả về bình thường | Transaction có thể commit | Ném lại exception hoặc đánh dấu rollback-only |
| Dùng `noRollbackFor` cho exception cần hủy dữ liệu | Thay đổi có thể được commit | Bỏ rule đó hoặc điều chỉnh chính sách |
| Gọi transactional method qua self-invocation | Proxy có thể không áp dụng transaction rule | Đặt ranh giới ở bean/service được gọi qua proxy |
| Chỉ kiểm tra exception trong test | Không chứng minh database đã rollback | Đọc lại trạng thái dữ liệu sau lời gọi |
| Cho rằng rollback hoàn tác email hoặc HTTP | Side effect ngoài database vẫn tồn tại | Dùng outbox, after-commit hoặc cơ chế bù trừ |

## 11. Checklist khi chọn rollback rule

Trước khi hoàn thiện một service method, hãy tự kiểm tra:

1. Phương thức đang chạy trong transaction nào và transaction boundary nằm ở đâu?
2. Exception nghiệp vụ là checked hay unchecked?
3. Exception có thoát khỏi phương thức được Spring proxy quản lý không?
4. Nếu là checked exception, đã khai báo `rollbackFor` đúng class chưa?
5. Có `noRollbackFor` hoặc rule khác làm thay đổi kết quả không?
6. Có đoạn `catch` nào nuốt exception hoặc khiến phương thức kết thúc bình thường không?
7. Những thao tác cần rollback có thật sự tham gia cùng transaction không?
8. Integration test đã xác nhận dữ liệu được giữ hoặc bị hủy theo đúng nghiệp vụ chưa?
9. Có side effect ngoài database cần xử lý riêng sau commit hoặc bằng cơ chế bù trừ không?

## Kết luận

Spring mặc định rollback với `RuntimeException` và `Error`, còn checked exception thường không làm rollback. Dùng `@Transactional(rollbackFor = YourCheckedException.class)` khi nghiệp vụ yêu cầu hủy thay đổi database trong trường hợp checked exception đó xảy ra. Đồng thời bảo đảm exception đi qua transaction proxy, không bị bắt rồi nuốt, và kiểm thử trạng thái database sau khi transaction kết thúc.