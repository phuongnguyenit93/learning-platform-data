# Phối hợp nhiều repository trong một giao dịch

Bài học này thuộc module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, trong chương **Giao dịch và tính nhất quán**. Module hướng tới cách tổ chức phần mềm theo kiến trúc phân tầng, nơi presentation tiếp nhận yêu cầu, application điều phối ca sử dụng, business/domain bảo vệ quy tắc và data access thực hiện thao tác lưu trữ. Trọng tâm ở đây là phối hợp nhiều repository trong cùng một giao dịch để một ca sử dụng cập nhật nhiều phần dữ liệu mà vẫn giữ được tính nhất quán.

Một ca sử dụng thường không chỉ ghi vào một bảng. Ví dụ đặt hàng có thể cần lưu đơn hàng, cập nhật tồn kho và ghi nhận một sự kiện cần phát đi. Nếu mỗi thao tác tự commit riêng, lỗi xảy ra giữa chừng có thể để lại dữ liệu ở trạng thái chỉ hoàn thành một phần. Ranh giới giao dịch cần bao phủ toàn bộ nhóm thay đổi phải thành công hoặc thất bại cùng nhau.

## 1. Vì sao một ca sử dụng cần nhiều repository?

Repository cung cấp cách đọc và ghi một loại dữ liệu hoặc một tập đối tượng. Một quy trình nghiệp vụ có thể phối hợp nhiều repository vì dữ liệu liên quan được tổ chức theo những trách nhiệm khác nhau.

Ví dụ khi đặt hàng:

- Đọc thông tin sản phẩm hoặc giá bán.
- Đọc và giữ chỗ số lượng tồn kho.
- Tạo đơn hàng và các dòng đơn hàng.
- Ghi nhận sự kiện nghiệp vụ cần được gửi sau khi giao dịch hoàn tất.

Có thể mỗi repository quản lý một aggregate hoặc một nhóm bảng riêng. Điều đó không có nghĩa mỗi repository phải mở một giao dịch độc lập. Nếu các thao tác cùng thuộc một đơn vị công việc và cùng sử dụng một tài nguyên giao dịch, application service có thể gọi tất cả chúng trong một transaction.

Tính nguyên tử (atomicity) có nghĩa là nhóm thay đổi được commit cùng nhau hoặc bị rollback cùng nhau. Ví dụ, nếu không thể giữ đủ hàng thì đơn hàng không được lưu ở trạng thái đã đặt; nếu lưu đơn hàng thất bại sau khi đã cập nhật tồn kho, phần cập nhật tồn kho cũng cần được hoàn tác.

Một giao dịch bao phủ nhiều repository hữu ích khi:

- Các thay đổi cùng tạo nên một kết quả nghiệp vụ không thể tách rời.
- Các thao tác cùng tham gia một transaction manager và một tài nguyên hỗ trợ transaction.
- Hệ thống cần bảo đảm dữ liệu liên quan không bị commit một phần.
- Application service có thể xác định rõ điểm bắt đầu và kết thúc của ca sử dụng.

Không phải mọi thao tác của một quy trình đều cần nằm trong cùng transaction. Gửi email, gọi dịch vụ vận chuyển hoặc phát message ra broker thường có đặc tính và vòng đời riêng; cần thiết kế riêng cho các hiệu ứng bên ngoài.

## 2. Đặt ranh giới giao dịch ở application service

Application service điều phối một ca sử dụng nên thường là nơi phù hợp để xác định ranh giới transaction. Nó biết các bước nào phải thành công cùng nhau, repository nào cần được gọi và khi nào có thể kết thúc công việc.

Ví dụ dưới đây giả định `OrderRepository` và `InventoryRepository` cùng sử dụng một cơ sở dữ liệu và được quản lý bởi cùng transaction manager của Spring:

```java
@Service
public class PlaceOrderService {
    private final InventoryRepository inventoryRepository;
    private final OrderRepository orderRepository;

    public PlaceOrderService(
            InventoryRepository inventoryRepository,
            OrderRepository orderRepository) {
        this.inventoryRepository = inventoryRepository;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public OrderId place(PlaceOrderCommand command) {
        Inventory inventory = inventoryRepository
                .findForUpdate(command.productId())
                .orElseThrow(() -> new ProductNotFoundException(
                        command.productId()));

        inventory.reserve(command.quantity());

        Order order = Order.place(
                command.customerId(),
                command.productId(),
                command.quantity());

        inventoryRepository.save(inventory);
        orderRepository.save(order);

        return order.id();
    }
}
```

Trong ví dụ:

1. Spring bắt đầu transaction khi lời gọi đi qua proxy của `PlaceOrderService`.
2. Application service đọc tồn kho và yêu cầu domain kiểm tra, giữ chỗ số lượng.
3. Application service lưu thay đổi tồn kho và đơn hàng qua hai repository.
4. Khi phương thức kết thúc bình thường, transaction manager thực hiện commit.
5. Nếu một lỗi làm transaction phải rollback, cả hai thay đổi trong cùng transaction được hoàn tác.

Đoạn code minh họa ranh giới và thứ tự điều phối. Kiểu `findForUpdate` biểu thị một chiến lược khóa được trình bày ở phần sau; cách triển khai cụ thể tùy công nghệ lưu trữ.

Các repository không cần tự tạo transaction mới cho từng lời gọi. Với propagation mặc định `REQUIRED` của Spring, thao tác repository tham gia transaction hiện có nếu đã có một transaction phù hợp. Spring Data JPA cũng cung cấp transaction cho một số phương thức repository khi được gọi độc lập; khi được gọi bên trong application transaction, chúng thường tham gia transaction bên ngoài theo cấu hình propagation.

### 2.1. Vì sao không đặt transaction ở từng repository?

Nếu mỗi repository tự mở và commit một transaction riêng, luồng có thể trở thành:

1. Repository tồn kho commit số lượng đã giảm.
2. Repository đơn hàng bắt đầu transaction khác.
3. Lưu đơn hàng thất bại.
4. Tồn kho vẫn bị giảm dù không có đơn hàng tương ứng.

Đây là trạng thái không nhất quán. Application service cần gom các thao tác phải cùng thành công vào một ranh giới transaction chung.

Repository vẫn có thể khai báo `@Transactional` cho các thao tác được gọi độc lập hoặc đặt `readOnly = true` cho một số truy vấn. Tuy nhiên, việc quyết định một ca sử dụng cần bao phủ bao nhiêu repository nên thuộc nơi điều phối ca sử dụng. Tránh dùng `REQUIRES_NEW` một cách tùy tiện trong repository: propagation này có thể tạo transaction độc lập và commit ngay cả khi transaction bên ngoài rollback.

### 2.2. Luồng phụ thuộc và vai trò từng tầng

Một cách tổ chức thường gặp:

```text
HTTP Controller
      |
      v
PlaceOrderService  (@Transactional)
      |
      +------> InventoryRepository
      |
      +------> OrderRepository
      |
      +------> OutboxRepository
                    |
                    v
              Database
```

Controller chuyển request thành command và gọi application service. Application service quyết định phạm vi công việc. Repository che giấu chi tiết truy vấn và lưu trữ. Domain object bảo vệ các quy tắc như số lượng phải dương hoặc không được giữ chỗ vượt quá tồn kho.

Transaction không làm thay trách nhiệm của các tầng. Nó bảo vệ tính nguyên tử của các thao tác lưu trữ; nó không biến một controller phức tạp thành application service tốt, cũng không thay thế các bất biến nghiệp vụ.

## 3. Điều kiện để nhiều repository cùng tham gia một transaction

Có nhiều lời gọi repository trong một phương thức chưa đủ để bảo đảm chúng thuộc cùng transaction. Cần kiểm tra các điều kiện thực tế.

### 3.1. Cùng transaction manager và tài nguyên giao dịch

Trong ứng dụng Spring dùng một cơ sở dữ liệu quan hệ với JPA, các repository thường cùng tham gia transaction do một `JpaTransactionManager` quản lý nếu chúng dùng cùng persistence unit/entity manager factory phù hợp.

Với JDBC, các thao tác cần dùng cùng transaction-bound connection do transaction manager quản lý. Nếu mỗi adapter tự tạo connection riêng hoặc tự commit, chúng có thể nằm ngoài transaction của application service.

Một số trường hợp cần xem xét kỹ:

- Hai repository dùng cùng database nhưng được cấu hình qua hai datasource hoặc hai transaction manager khác nhau.
- Một repository dùng JPA, repository khác dùng JDBC.
- Một ứng dụng kết nối nhiều database độc lập.
- Một thao tác ghi qua HTTP tới dịch vụ khác.
- Một repository gọi stored procedure hoặc hệ thống ngoài có cơ chế commit riêng.

JPA và JDBC có thể cùng tham gia một transaction nếu được cấu hình để chia sẻ đúng datasource và transaction manager. Chỉ nhìn thấy cùng tên database trong cấu hình không đủ để kết luận điều đó.

Nếu ứng dụng có nhiều transaction manager, có thể chỉ định manager phù hợp:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void place(PlaceOrderCommand command) {
    // Các thao tác thuộc transaction manager này
}
```

Tên bean ở ví dụ chỉ mang tính minh họa. Cần chọn đúng manager mà các repository liên quan thực sự sử dụng.

### 3.2. Propagation và lời gọi qua proxy

Spring thường áp dụng `@Transactional` bằng proxy. Lời gọi từ bên ngoài đi qua proxy sẽ kích hoạt transaction theo cấu hình. Một lời gọi nội bộ từ phương thức này sang phương thức khác trong cùng object (self-invocation) thường không đi qua proxy, nên annotation trên phương thức được gọi nội bộ có thể không được áp dụng như mong đợi.

Ví dụ:

```java
@Service
class OrderService {
    public void submit(PlaceOrderCommand command) {
        saveAll(command); // Lời gọi nội bộ trên cùng object
    }

    @Transactional
    public void saveAll(PlaceOrderCommand command) {
        // ...
    }
}
```

Trong cấu hình proxy mặc định, gọi `saveAll` theo cách này không kích hoạt transaction mới chỉ nhờ annotation của nó. Cách rõ ràng hơn là đặt ranh giới transaction trên phương thức application service được gọi từ bean khác, hoặc tách một trách nhiệm cần transaction thành bean riêng khi thực sự cần.

Một số propagation thường gặp:

| Propagation | Hành vi | Cách dùng cần cân nhắc |
|---|---|---|
| `REQUIRED` | Tham gia transaction hiện có; nếu chưa có thì tạo mới | Mặc định phù hợp cho nhiều repository trong một ca sử dụng |
| `REQUIRES_NEW` | Tạm dừng transaction hiện tại và tạo transaction độc lập | Chỉ dùng khi dữ liệu con phải commit độc lập theo yêu cầu rõ ràng |
| `MANDATORY` | Yêu cầu phải có transaction hiện tại | Hữu ích khi một thao tác không được gọi ngoài transaction |
| `SUPPORTS` | Tham gia nếu có; nếu không thì chạy không transaction | Phù hợp với một số thao tác đọc tùy ngữ cảnh |

Đừng chọn propagation chỉ để tránh lỗi kỹ thuật trước mắt. Hãy xác định dữ liệu nào phải commit cùng nhau. Nếu một repository dùng `REQUIRES_NEW`, rollback của transaction bên ngoài không thể hoàn tác phần đã commit độc lập.

## 4. Rollback khi một repository thất bại

Giả sử application service đã cập nhật tồn kho, sau đó lưu đơn hàng gặp lỗi ràng buộc duy nhất. Nếu cả hai thao tác nằm trong cùng transaction, rollback sẽ hoàn tác thay đổi tồn kho khi lỗi làm transaction bị rollback.

Spring mặc định đánh dấu rollback với `RuntimeException` và `Error`. Checked exception không tự động gây rollback theo mặc định phổ biến của `@Transactional`; nếu checked exception biểu thị lỗi khiến toàn bộ ca sử dụng phải thất bại, hãy khai báo rõ:

```java
@Transactional(rollbackFor = Exception.class)
public void place(PlaceOrderCommand command) throws Exception {
    // Đọc và cập nhật qua nhiều repository
}
```

Có thể chỉ định một loại checked exception cụ thể thay vì rollback với mọi `Exception`, tùy chính sách lỗi của ứng dụng.

### 4.1. Không nuốt lỗi khi cần rollback

Một lỗi thường gặp là bắt ngoại lệ, ghi log rồi tiếp tục hoặc trả kết quả bình thường:

```java
@Transactional
public void place(PlaceOrderCommand command) {
    inventoryRepository.reserve(command.productId(), command.quantity());

    try {
        orderRepository.save(buildOrder(command));
    } catch (DataAccessException exception) {
        log.error("Không thể lưu đơn hàng", exception);
        // Trả về bình thường có thể khiến transaction không rollback
    }
}
```

Nếu ngoại lệ bị giữ lại và phương thức kết thúc bình thường, transaction có thể được commit nếu chưa bị đánh dấu rollback-only. Hãy để lỗi được truyền ra ngoài khi toàn bộ ca sử dụng phải thất bại, hoặc chủ động đánh dấu rollback-only theo API transaction phù hợp nếu có lý do cần xử lý lỗi tại chỗ.

Không nên bắt mọi ngoại lệ rồi chuyển thành một phản hồi thành công. Nếu cần chuyển lỗi thành kết quả nghiệp vụ, phải xác định rõ transaction có tiếp tục được hay không và trạng thái dữ liệu còn hợp lệ không.

### 4.2. Lỗi có thể xuất hiện khi flush hoặc commit

Với JPA, một số thay đổi được theo dõi trong persistence context và SQL có thể chỉ được thực thi khi flush hoặc commit. Vì vậy, `repository.save(entity)` trả về không đồng nghĩa dữ liệu đã được commit thành công. Vi phạm unique constraint, foreign key hoặc lỗi ghi dữ liệu có thể chỉ xuất hiện ở bước flush/commit.

Transaction interceptor của Spring xử lý commit sau khi phương thức được gọi kết thúc. Caller chỉ nhận được kết quả thành công sau khi quá trình commit hoàn tất. Nếu cần phát hiện lỗi ràng buộc ngay trong thân phương thức, có thể gọi `flush()` tại thời điểm có chủ đích, nhưng không nên flush sau mọi thao tác chỉ để tạo cảm giác an toàn.

### 4.3. Rollback không đảo ngược mọi side effect

Rollback cơ sở dữ liệu không thể tự thu hồi email đã gửi, HTTP request đã tới hệ thống khác hoặc message đã được publish ra broker. Những hành động bên ngoài transaction cần được trì hoãn hoặc có cơ chế bù trừ.

Ví dụ, nếu đơn hàng được lưu nhưng gửi email thất bại, dữ liệu đơn hàng vẫn có thể đã commit. Nếu email được gửi trước commit rồi transaction rollback, khách hàng có thể nhận thông báo về một đơn hàng không tồn tại. Vì thế, không nên coi mọi lời gọi trong một phương thức `@Transactional` đều được database rollback.

## 5. Giữ tính đúng đắn khi nhiều request cập nhật cùng dữ liệu

Một transaction nguyên tử không tự giải quyết mọi vấn đề cạnh tranh. Hai request có thể cùng đọc tồn kho là 5, mỗi request đặt 4 sản phẩm, rồi cả hai cùng ghi kết quả nếu không có kiểm soát đồng thời phù hợp.

Cần phân biệt:

- **Atomicity:** các thao tác trong một transaction commit hoặc rollback cùng nhau.
- **Isolation:** mức độ transaction nhìn thấy thay đổi của transaction khác.
- **Concurrency control:** cách ngăn hai luồng đồng thời vi phạm quy tắc nghiệp vụ.

Với tồn kho, có thể dùng optimistic locking bằng cột version hoặc pessimistic locking để khóa bản ghi trong thời gian ngắn.

### 5.1. Optimistic locking

Với JPA, thêm trường `@Version` vào entity giúp phát hiện cập nhật xung đột:

```java
@Entity
class InventoryEntity {
    @Id
    private UUID productId;

    private int availableQuantity;

    @Version
    private long version;
}
```

Nếu hai transaction cùng đọc một version và cùng cập nhật, một transaction có thể thành công; transaction còn lại nhận lỗi optimistic locking khi cập nhật version không còn khớp. Application có thể yêu cầu thử lại toàn bộ ca sử dụng theo chính sách phù hợp hoặc trả lỗi xung đột cho client.

Không nên tự động retry mọi lỗi. Retry chỉ phù hợp khi thao tác có thể thực hiện lại an toàn, giới hạn số lần thử và không lặp side effect ngoài transaction.

### 5.2. Pessimistic locking

Với thao tác giữ chỗ tồn kho cần tuần tự hóa, repository có thể khóa bản ghi khi đọc:

```java
public interface SpringDataInventoryRepository
        extends JpaRepository<InventoryEntity, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select i
        from InventoryEntity i
        where i.productId = :productId
        """)
    Optional<InventoryEntity> findForUpdate(UUID productId);
}
```

Transaction giữ khóa cho đến khi commit hoặc rollback. Cách này có thể phù hợp khi tranh chấp cao và đoạn cập nhật ngắn, nhưng làm giảm mức song song và có thể gây chờ hoặc deadlock. Cần giữ transaction ngắn, khóa theo thứ tự nhất quán khi cập nhật nhiều bản ghi và xử lý timeout/lock exception.

Lựa chọn optimistic hay pessimistic phụ thuộc tần suất xung đột, chi phí thử lại và khả năng của cơ sở dữ liệu. Không có một chiến lược duy nhất đúng cho mọi nghiệp vụ.

## 6. Khi nào nhiều repository không thể dùng một transaction cục bộ?

Transaction cục bộ thường bảo vệ một tài nguyên giao dịch, chẳng hạn một database thông qua một transaction manager. Nếu hai repository cùng truy cập các bảng trong cùng database và cùng transaction resource, một transaction có thể bao phủ cả hai.

Nhưng nếu repository thứ nhất ghi vào database A còn repository thứ hai ghi vào database B, một transaction manager cục bộ thông thường không thể tự bảo đảm cả hai commit hoặc rollback cùng nhau. Tương tự, gọi dịch vụ kho hàng qua HTTP không trở thành một phần của transaction JPA chỉ vì lời gọi đó nằm bên trong phương thức có `@Transactional`.

Một số hệ thống có thể dùng distributed transaction/XA với JTA và các tài nguyên hỗ trợ chuẩn tương ứng. Cách này có chi phí cấu hình, vận hành và ảnh hưởng tính sẵn sàng; không nên giả định Spring `@Transactional` mặc định đã cung cấp transaction phân tán.

Với kiến trúc nhiều dịch vụ hoặc nhiều database độc lập, thường cân nhắc các mẫu sau:

### 6.1. Transactional outbox

Nếu một transaction cần vừa lưu dữ liệu vừa yêu cầu phát sự kiện, có thể ghi sự kiện vào bảng outbox trong cùng database và cùng transaction với dữ liệu nghiệp vụ:

```java
@Transactional
public OrderId place(PlaceOrderCommand command) {
    Order order = createAndSaveOrder(command);

    outboxRepository.save(
            OutboxMessage.orderPlaced(order.id()));

    return order.id();
}
```

Một tiến trình riêng đọc các bản ghi outbox và publish lên message broker. Nếu transaction rollback, cả đơn hàng và outbox record đều không được commit. Nếu transaction commit, thông tin cần phát đi được lưu bền vững cùng dữ liệu.

Dispatcher có thể publish lại khi gặp lỗi, vì vậy consumer thường cần xử lý idempotent hoặc loại trùng. Outbox không làm database và broker commit trong cùng một transaction; nó giúp không mất ý định phát sự kiện khi dữ liệu nghiệp vụ đã commit.

### 6.2. Saga và hành động bù trừ

Khi một quy trình đi qua nhiều dịch vụ có database riêng, mỗi dịch vụ thường commit transaction cục bộ của mình. Saga tổ chức chuỗi bước đó và định nghĩa hành động bù trừ khi bước sau thất bại.

Ví dụ, đặt hàng có thể tạo đơn ở dịch vụ Order, giữ hàng ở Inventory, rồi yêu cầu thanh toán ở Payment. Nếu thanh toán thất bại sau khi đã giữ hàng, hệ thống phát lệnh hủy giữ hàng và chuyển đơn sang trạng thái phù hợp. Hành động bù trừ là một nghiệp vụ mới, không phải rollback vật lý của transaction trước.

Không nên dùng saga chỉ vì ứng dụng có nhiều repository. Nếu tất cả repository cùng một database và cùng transaction manager, transaction cục bộ thường đơn giản và mạnh hơn. Saga phù hợp khi ranh giới dịch vụ hoặc tài nguyên khiến không thể có một transaction nguyên tử chung.

## 7. Thiết kế transaction ngắn và có phạm vi rõ

Transaction dài làm giữ connection và lock lâu hơn, tăng nguy cơ timeout, deadlock và giảm thông lượng. Application service nên giới hạn transaction vào phần cần đọc/ghi nhất quán.

Một số nguyên tắc thực tế:

- Không gọi API bên ngoài, gửi email hoặc chờ người dùng phản hồi khi đang giữ transaction.
- Không thực hiện tính toán nặng hoặc xử lý tệp lớn trong transaction nếu có thể tách ra.
- Đọc dữ liệu cần thiết và thực hiện các thay đổi liên quan trong một khoảng thời gian ngắn.
- Chỉ dùng lock khi cần và giữ lock trong thời gian tối thiểu.
- Không mở transaction mới ở từng repository nếu chúng cần commit cùng nhau.
- Đặt `readOnly = true` cho luồng chỉ đọc khi phù hợp với công nghệ và transaction manager; đây là gợi ý tối ưu, không phải cơ chế bảo đảm mọi thao tác ghi đều bị chặn ở mọi cấu hình.

Với ca sử dụng có nhiều bước, hãy xác định phần nào là thay đổi dữ liệu nguyên tử và phần nào là công việc có thể thực hiện sau commit. Ranh giới rõ ràng giúp tránh giữ transaction trong lúc thực hiện tác vụ chậm.

## 8. Kiểm thử việc phối hợp nhiều repository

Unit test với mock có thể xác minh application service gọi đúng repository và xử lý kết quả, nhưng nó không chứng minh các repository thật sự tham gia cùng transaction. Cần integration test với cấu hình transaction thực tế để kiểm tra rollback và mapping.

Một kịch bản kiểm thử quan trọng:

1. Tạo dữ liệu tồn kho ban đầu.
2. Gọi ca sử dụng cập nhật tồn kho và lưu đơn hàng.
3. Làm cho thao tác lưu đơn hàng thất bại sau khi tồn kho đã được thay đổi trong transaction.
4. Đọc lại dữ liệu trong transaction mới.
5. Xác minh tồn kho vẫn giữ giá trị ban đầu và không có đơn hàng được lưu.

Ví dụ phác thảo:

```java
@SpringBootTest
class PlaceOrderTransactionTest {
    @Autowired
    PlaceOrderService placeOrder;

    @Autowired
    InventoryRepository inventoryRepository;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void rollsBackInventoryWhenOrderCannotBeSaved() {
        // Chuẩn bị tồn kho và điều kiện khiến lưu đơn hàng thất bại.

        assertThrows(DataIntegrityViolationException.class,
                () -> placeOrder.place(invalidCommand()));

        // Đọc lại bằng transaction mới hoặc sau khi transaction đã kết thúc.
        assertEquals(10,
                inventoryRepository.findAvailableQuantity(productId()));
        assertFalse(orderRepository.existsById(expectedOrderId()));
    }
}
```

Đây là khung minh họa; cách tạo lỗi và quản lý transaction trong test phụ thuộc schema, repository và cấu hình ứng dụng. Nếu test tự chạy bên trong một transaction do framework test mở, cần chú ý rằng transaction của test có thể che khuất thời điểm commit/rollback của service. Có thể dùng transaction mới để xác minh trạng thái sau khi lời gọi kết thúc.

Ngoài rollback, nên kiểm thử:

- Hai repository có thực sự dùng chung transaction manager/resource.
- Checked exception có được cấu hình rollback như mong muốn.
- Repository nào đó có vô tình dùng `REQUIRES_NEW` hay tự commit không.
- Lỗi optimistic/pessimistic locking được chuyển thành kết quả phù hợp.
- Outbox record được ghi cùng dữ liệu nghiệp vụ và consumer có thể xử lý message lặp.

## 9. Checklist khi phối hợp nhiều repository

Trước khi thêm hoặc sửa một transaction, hãy trả lời các câu hỏi:

1. Những thay đổi dữ liệu nào bắt buộc phải thành công hoặc thất bại cùng nhau?
2. Các repository có dùng chung transaction manager và tài nguyên giao dịch không?
3. Ranh giới transaction nằm ở application service nào?
4. Các lời gọi repository có tham gia transaction hiện tại hay tạo transaction riêng?
5. Những ngoại lệ nào phải làm rollback? Có checked exception hoặc lỗi bị bắt rồi nuốt không?
6. Có nguy cơ cập nhật đồng thời gây mất dữ liệu hoặc vi phạm bất biến không?
7. Có gọi mạng, gửi email hoặc publish message trong transaction không?
8. Nếu có nhiều database hoặc dịch vụ độc lập, cần outbox, saga hay một cơ chế phân tán khác?
9. Integration test đã xác minh rollback trên trạng thái lưu trữ thực tế chưa?

Nếu chưa thể trả lời các câu hỏi về transaction manager, resource và propagation, không nên suy luận rằng nhiều lời gọi repository tự động tạo thành một transaction nguyên tử.

## 10. Ghi nhớ

- Application service thường là nơi phù hợp để xác định ranh giới transaction cho một ca sử dụng gọi nhiều repository.
- Nhiều repository chỉ cùng commit/rollback khi chúng thực sự tham gia cùng transaction manager và tài nguyên giao dịch.
- Propagation mặc định `REQUIRED` thường cho phép repository tham gia transaction hiện tại; `REQUIRES_NEW` có thể commit độc lập và làm thay đổi ngữ nghĩa rollback.
- Spring mặc định rollback với unchecked exception và `Error`; checked exception cần cấu hình nếu cũng phải rollback.
- JPA có thể chỉ thực thi SQL khi flush hoặc commit, nên `save()` trả về chưa chứng minh transaction đã commit.
- Atomicity không tự giải quyết xung đột đồng thời; cân nhắc optimistic locking, pessimistic locking và mức isolation phù hợp.
- Transaction cục bộ không tự bao phủ database khác, HTTP service, email hay message broker. Với hệ phân tán, cân nhắc outbox, saga hoặc distributed transaction khi có lý do rõ ràng.
- Giữ transaction ngắn, tránh side effect bên ngoài trong transaction và dùng integration test để xác minh rollback thực tế.

