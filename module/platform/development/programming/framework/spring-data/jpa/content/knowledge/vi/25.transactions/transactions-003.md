# Đặt @Transactional ở dịch vụ và phối hợp nhiều Repository

**Module:** Spring Data JPA  
**Nhóm kiến thức:** Giao dịch

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao ranh giới giao dịch thường được đặt ở tầng Service.
- Dùng một phương thức dịch vụ để phối hợp nhiều Spring Data Repository trong cùng giao dịch.
- Hiểu cách Spring bắt đầu, tham gia, commit và rollback giao dịch.
- Chọn các thuộc tính cơ bản của @Transactional và nhận biết những lỗi thường gặp.
- Kiểm tra tính nguyên tử của một nghiệp vụ có nhiều thao tác đọc và ghi dữ liệu.

## 2. Vì sao đặt ranh giới giao dịch ở tầng Service?

Một nghiệp vụ thường gồm nhiều thao tác dữ liệu. Ví dụ, khi đặt hàng, hệ thống cần kiểm tra tồn kho, trừ số lượng hàng, tạo đơn hàng và lưu các dòng chi tiết. Những thao tác này có quan hệ nghiệp vụ với nhau: nếu một bước thất bại, các bước ghi trước đó cũng phải được hủy.

Tầng Service thường là nơi thể hiện một ca sử dụng hoàn chỉnh. Vì vậy, đây là vị trí phù hợp để định nghĩa ranh giới giao dịch. Service gọi nhiều Repository nhưng vẫn giữ chúng trong một giao dịch duy nhất.

Nếu chỉ dựa vào giao dịch riêng của từng Repository, một thao tác lưu có thể đã commit trước khi thao tác kế tiếp thất bại. Khi đó dữ liệu có thể ở trạng thái dở dang. Ví dụ: đơn hàng đã được lưu nhưng việc ghi chi tiết đơn hàng hoặc cập nhật tồn kho thất bại.

Đặt @Transactional trên phương thức Service giúp các thao tác tham gia cùng một giao dịch:

- Tất cả thao tác ghi thành công: giao dịch được commit.
- Một lỗi làm giao dịch phải rollback: các thay đổi thuộc giao dịch đó được hoàn tác cùng nhau.
- Repository không cần tự mở một giao dịch độc lập cho từng bước khi đã có giao dịch bên ngoài.

Ranh giới nên bao phủ một nghiệp vụ có ý nghĩa, chẳng hạn tạo đơn hàng, chuyển tiền hoặc cập nhật hồ sơ cùng các bản ghi liên quan. Không nên kéo dài giao dịch qua những công việc không cần thiết như chờ người dùng, gọi dịch vụ từ xa lâu hoặc xử lý tệp lớn.

## 3. Spring xử lý @Transactional như thế nào?

Trong cấu hình Spring thông thường, @Transactional được thực thi thông qua proxy AOP:

1. Một bean khác gọi phương thức public trên bean Service do Spring quản lý.
2. Proxy chặn lời gọi và yêu cầu transaction manager bắt đầu giao dịch mới hoặc tham gia giao dịch đang tồn tại.
3. Transaction manager quản lý EntityManager và kết nối cơ sở dữ liệu trong phạm vi giao dịch.
4. Các Repository được gọi bên trong phương thức sử dụng cùng giao dịch nếu chúng được cấu hình với cùng transaction manager và persistence unit.
5. Khi phương thức kết thúc bình thường, Spring flush các thay đổi cần thiết và commit. Nếu có lỗi thuộc quy tắc rollback, Spring rollback giao dịch.

Spring Boot với Spring Data JPA thường tự cấu hình JpaTransactionManager cho một persistence unit. Trong ứng dụng có cấu hình giao dịch riêng hoặc nhiều datasource, cần chọn đúng transaction manager cho Service.

Ví dụ khi có nhiều transaction manager:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public void processOrder() {
    // Các Repository thuộc transaction manager này
}
~~~

Tên transaction manager trong ví dụ chỉ là minh họa; phải dùng đúng bean đã khai báo trong ứng dụng.

**Lưu ý về thời điểm ghi SQL:** JPA có persistence context. Khi một entity đang được quản lý bị thay đổi, Hibernate thường theo dõi thay đổi đó và ghi xuống cơ sở dữ liệu khi flush. Vì vậy, việc một phương thức Repository trả về không có nghĩa giao dịch đã commit. Commit xảy ra khi ranh giới giao dịch bên ngoài kết thúc thành công.

## 4. Ví dụ: đặt hàng qua nhiều Repository

Giả sử ứng dụng có ba thành phần dữ liệu:

- Inventory: số lượng tồn kho của sản phẩm.
- PurchaseOrder: đơn hàng của khách.
- OrderLine: các dòng chi tiết của đơn hàng.

Yêu cầu nghiệp vụ: kiểm tra tồn kho, giảm số lượng, tạo đơn hàng và lưu chi tiết. Tất cả phải thành công hoặc cùng thất bại.

### 4.1. Repository

Có thể dùng khóa ghi bi quan để khóa bản ghi tồn kho trong lúc kiểm tra và cập nhật, tránh hai giao dịch đồng thời cùng đọc một số lượng rồi cùng bán vượt tồn.

~~~java
import java.util.Optional;

import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends JpaRepository<Inventory, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select i
        from Inventory i
        where i.productId = :productId
        """)
    Optional<Inventory> findForUpdateByProductId(
            @Param("productId") Long productId);
}
~~~

Hai Repository còn lại có thể dùng các phương thức CRUD kế thừa:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}

public interface OrderLineRepository
        extends JpaRepository<OrderLine, Long> {
}
~~~

Ví dụ giả định các entity đã có ánh xạ JPA phù hợp, Inventory có trường productId và available, còn OrderLine tham chiếu đến PurchaseOrder.

### 4.2. Đặt @Transactional ở Service

~~~java
import jakarta.persistence.EntityNotFoundException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class OrderService {

    private final InventoryRepository inventoryRepository;
    private final PurchaseOrderRepository orderRepository;
    private final OrderLineRepository orderLineRepository;

    @Transactional
    public Long placeOrder(PlaceOrderCommand command) {
        Inventory inventory = inventoryRepository
                .findForUpdateByProductId(command.productId())
                .orElseThrow(() ->
                        new EntityNotFoundException("Không tìm thấy tồn kho"));

        inventory.reserve(command.quantity());

        PurchaseOrder order = orderRepository.save(
                PurchaseOrder.create(command.customerId()));

        OrderLine line = OrderLine.create(
                order,
                command.productId(),
                command.quantity());

        orderLineRepository.save(line);

        return order.getId();
    }
}
~~~

PlaceOrderCommand có thể là một Java record:

~~~java
public record PlaceOrderCommand(
        Long customerId,
        Long productId,
        int quantity
) {
}
~~~

Phương thức reserve của Inventory nên kiểm tra số lượng hợp lệ và tồn kho trước khi trừ:

~~~java
public void reserve(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException(
                "Số lượng phải lớn hơn 0");
    }

    if (available < quantity) {
        throw new InsufficientStockException(
                "Không đủ hàng trong kho");
    }

    available -= quantity;
}
~~~

InsufficientStockException nên kế thừa RuntimeException nếu muốn Spring rollback theo mặc định.

Trong ví dụ:

- @Transactional tạo ranh giới giao dịch cho toàn bộ nghiệp vụ placeOrder.
- findForUpdateByProductId đọc và khóa bản ghi tồn kho trong giao dịch.
- inventory là entity đang được persistence context quản lý. Thay đổi available được JPA phát hiện bằng dirty checking; không bắt buộc gọi inventoryRepository.save(inventory) lần nữa.
- orderRepository.save lưu đơn hàng và trả về entity được lưu. Nên sử dụng entity trả về của save, đặc biệt khi thao tác với entity mới hoặc detached.
- orderLineRepository.save lưu chi tiết đơn hàng.
- Nếu một bước phát sinh lỗi khiến giao dịch rollback, thay đổi tồn kho, đơn hàng và chi tiết đơn hàng cùng được hoàn tác, với điều kiện chúng dùng chung transaction manager và giao dịch cơ sở dữ liệu.

Đây là các đoạn mã trong một ứng dụng Spring Boot có các entity, ánh xạ quan hệ, constructor/factory và repository tương ứng; chúng không phải chương trình Java độc lập để chạy chỉ bằng javac.

## 5. Quy tắc commit và rollback

Theo mặc định, Spring rollback khi phương thức giao dịch kết thúc bằng:

- RuntimeException hoặc một lớp con của RuntimeException.
- Error hoặc một lớp con của Error.

Với checked exception, Spring mặc định không rollback. Nếu nghiệp vụ cần rollback khi một checked exception xảy ra, khai báo rõ:

~~~java
@Transactional(rollbackFor = PaymentRejectedException.class)
public void confirmPayment() throws PaymentRejectedException {
    // Cập nhật nhiều bản ghi
}
~~~

Có thể khai báo nhiều loại exception trong rollbackFor. Chỉ dùng noRollbackFor khi thật sự muốn một loại lỗi cụ thể không làm rollback.

Không nên bắt lỗi rồi bỏ qua trong phương thức giao dịch:

~~~java
@Transactional
public void createOrder() {
    try {
        orderRepository.save(...);
        orderLineRepository.save(...);
    } catch (RuntimeException ex) {
        // Chỉ ghi log rồi tiếp tục có thể khiến giao dịch không rollback
        log.error("Không thể tạo đơn hàng", ex);
    }
}
~~~

Nếu lỗi bị nuốt và giao dịch chưa được đánh dấu rollback-only, Spring có thể commit các thay đổi đã thực hiện. Cách thường dùng là để exception phù hợp truyền ra ngoài. Nếu cần chuyển đổi lỗi, hãy ném lại một exception có ngữ nghĩa rõ ràng và thuộc quy tắc rollback.

Một trường hợp khác: một phương thức transactional bên trong tham gia giao dịch ngoài bằng REQUIRED, phát sinh RuntimeException khiến giao dịch bị đánh dấu rollback-only, sau đó phương thức ngoài bắt lỗi và tiếp tục. Khi giao dịch ngoài kết thúc, Spring vẫn rollback và có thể ném UnexpectedRollbackException. Việc bắt exception không tự khôi phục một giao dịch đã bị đánh dấu rollback-only.

**Flush không phải commit.** saveAndFlush hoặc EntityManager.flush buộc JPA đồng bộ thay đổi xuống cơ sở dữ liệu sớm hơn để phát hiện lỗi ràng buộc. Tuy nhiên, giao dịch vẫn có thể rollback sau flush; chỉ khi transaction manager commit thành công thì giao dịch mới hoàn tất.

## 6. Các thuộc tính thường dùng của @Transactional

| Thuộc tính | Mặc định | Ý nghĩa |
|---|---|---|
| propagation | REQUIRED | Tham gia giao dịch hiện tại; nếu chưa có thì tạo giao dịch mới |
| isolation | DEFAULT | Dùng mức cô lập mặc định của transaction manager/cơ sở dữ liệu |
| readOnly | false | Giao dịch cho phép đọc và ghi |
| timeout | Theo transaction manager | Giới hạn thời gian giao dịch nếu được cấu hình |
| rollbackFor | RuntimeException và Error | Chỉ định thêm loại exception phải rollback |

### 6.1. Propagation REQUIRED

REQUIRED là mặc định và thường phù hợp với nghiệp vụ phối hợp nhiều Repository:

~~~java
@Transactional
public void placeOrder() {
    inventoryService.reserve();
    paymentRecordService.createRecord();
}
~~~

Nếu các lời gọi bên trong tham gia cùng transaction manager, chúng dùng giao dịch đang có. Khi không có giao dịch bên ngoài, lời gọi Service mở giao dịch mới.

### 6.2. Propagation REQUIRES_NEW

REQUIRES_NEW tạm dừng giao dịch ngoài và mở giao dịch độc lập. Giao dịch trong có thể commit dù giao dịch ngoài rollback. Vì thế, không dùng tùy tiện cho các thao tác cần nguyên tử cùng nghiệp vụ. Chỉ chọn khi thật sự muốn kết quả độc lập, ví dụ một số loại nhật ký nghiệp vụ được phép tồn tại dù thao tác chính thất bại.

### 6.3. readOnly

Với phương thức chỉ truy vấn:

~~~java
@Transactional(readOnly = true)
public Optional<PurchaseOrder> findOrder(Long id) {
    return orderRepository.findById(id);
}
~~~

readOnly là một gợi ý cho transaction manager và JPA provider để tối ưu thao tác đọc. Đây không phải cơ chế bảo mật hay bảo đảm tuyệt đối rằng không thể ghi dữ liệu. Không dùng readOnly = true cho phương thức cần cập nhật entity.

Có thể đặt @Transactional(readOnly = true) ở cấp lớp rồi khai báo @Transactional trên các phương thức ghi để ghi đè cấu hình mặc định của lớp.

## 7. Những lỗi thường gặp

### 7.1. Tự gọi phương thức trong cùng bean

Trong chế độ proxy mặc định, lời gọi nội bộ qua this không đi qua proxy:

~~~java
@Service
public class OrderService {

    public void process() {
        saveDetails(); // Tự gọi trong cùng bean
    }

    @Transactional
    public void saveDetails() {
        // Không nên dựa vào annotation này khi chỉ được gọi nội bộ
    }
}
~~~

Nếu process gọi saveDetails bằng this, proxy không chặn lời gọi đó, nên cấu hình @Transactional trên saveDetails có thể không được áp dụng như mong đợi. Hãy đặt ranh giới giao dịch ở phương thức được gọi từ bean khác hoặc tách phần xử lý thành một Spring bean riêng.

### 7.2. Tạo Service bằng new

Một đối tượng được tạo bằng new thay vì được Spring quản lý sẽ không có proxy giao dịch. Hãy inject Service qua constructor hoặc cơ chế dependency injection của Spring.

### 7.3. Chỉ đặt giao dịch ở từng Repository

Mỗi Repository có thể có cấu hình giao dịch riêng cho các phương thức CRUD kế thừa. Tuy nhiên, điều đó không tự tạo ra một ranh giới nguyên tử cho toàn bộ nghiệp vụ gọi nhiều Repository. Các query method tự khai báo cũng không mặc nhiên nhận cấu hình giao dịch nếu không có cấu hình ở nơi gọi. Đặt giao dịch ở Service giúp toàn bộ luồng nghiệp vụ dùng chung ranh giới rõ ràng.

### 7.4. Nghĩ rằng mọi lỗi đều tự rollback

Checked exception không rollback theo mặc định. Lỗi bị bắt và không truyền ra ngoài cũng có thể khiến giao dịch tiếp tục. Hãy xác định rõ loại exception và chính sách rollback của nghiệp vụ.

### 7.5. Gọi API bên ngoài trong một giao dịch dài

Rollback cơ sở dữ liệu không thể tự hoàn tác email đã gửi, lời gọi HTTP đã thành công hoặc thao tác trên một hệ thống độc lập. Tránh giữ transaction mở trong lúc chờ mạng. Với sự kiện cần phát sau khi commit, có thể dùng @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT). Nếu cần độ tin cậy cao giữa dữ liệu và sự kiện, cân nhắc Transactional Outbox.

### 7.6. Cho rằng @Transactional tự giải quyết mọi vấn đề đồng thời

Giao dịch bảo đảm các thao tác thuộc giao dịch được commit/rollback cùng nhau, nhưng không tự ngăn mọi tranh chấp dữ liệu. Với tồn kho hoặc số dư, hãy cân nhắc:

- Pessimistic lock khi cần khóa bản ghi trong lúc xử lý.
- Optimistic locking bằng trường @Version khi xung đột ít và có thể phát hiện lúc cập nhật.
- Cập nhật có điều kiện ở mức SQL và kiểm tra số dòng bị ảnh hưởng.
- Ràng buộc duy nhất và ràng buộc toàn vẹn ở cơ sở dữ liệu.

Mức isolation mặc định phụ thuộc cấu hình transaction manager và cơ sở dữ liệu. Chỉ nâng isolation khi đã xác định được loại bất thường cần ngăn chặn và hiểu tác động đến khóa, thông lượng.

### 7.7. Dùng nhiều cơ sở dữ liệu nhưng nghĩ rằng vẫn có một giao dịch cục bộ

Một JpaTransactionManager thông thường quản lý một persistence unit. Nếu các Repository dùng các datasource hoặc transaction manager khác nhau, @Transactional đơn giản không tự biến chúng thành một giao dịch phân tán nguyên tử. Cần giải pháp giao dịch phân tán phù hợp như JTA/XA nếu hệ thống hỗ trợ, hoặc thiết kế quy trình bù trừ/outbox/saga khi chấp nhận nhất quán cuối cùng.

## 8. Kiểm thử giao dịch phối hợp nhiều Repository

Nên có kiểm thử tích hợp với transaction manager và cơ sở dữ liệu thử nghiệm tương ứng. Một kịch bản quan trọng:

1. Chuẩn bị tồn kho và dữ liệu đầu vào hợp lệ.
2. Gọi phương thức Service có thao tác ghi qua ít nhất hai Repository.
3. Làm cho một bước sau khi đã có thay đổi ghi phát sinh RuntimeException hoặc lỗi ràng buộc cơ sở dữ liệu.
4. Sau khi lời gọi Service kết thúc bằng lỗi, truy vấn lại dữ liệu trong một giao dịch kiểm tra độc lập.
5. Xác nhận không còn đơn hàng/chi tiết dở dang và số lượng tồn kho vẫn như trước.

Khi kiểm tra ranh giới giao dịch của Service, tránh để chính phương thức test mặc định chạy trong một giao dịch bao ngoài nếu điều đó làm thay đổi cách quan sát commit/rollback. Ví dụ, @DataJpaTest thường chạy test trong giao dịch và rollback khi kết thúc; điều này hữu ích cho kiểm thử repository nhưng cần cân nhắc khi kiểm tra hành vi commit của Service. Có thể dùng kiểm thử Spring Boot không đánh dấu @Transactional ở phương thức test và xác minh trạng thái sau lời gọi.

Ngoài rollback, nên kiểm tra:

- Hai Repository thực sự dùng cùng transaction manager trong nghiệp vụ cần nguyên tử.
- Lỗi checked exception có đúng chính sách rollbackFor hay không.
- Lỗi bị bắt có khiến giao dịch bị đánh dấu rollback-only hay không.
- Hai yêu cầu đồng thời cập nhật cùng tồn kho có vượt số lượng cho phép hay không.
- Giao dịch có bị giữ quá lâu do gọi dịch vụ ngoài hoặc xử lý không liên quan hay không.

## 9. Checklist khi triển khai

- [ ] Đặt @Transactional ở phương thức Service đại diện cho một nghiệp vụ hoàn chỉnh.
- [ ] Các Repository cần nguyên tử dùng cùng transaction manager và persistence unit.
- [ ] Chọn propagation phù hợp; ưu tiên REQUIRED cho luồng phối hợp thông thường.
- [ ] Xác định exception nào phải rollback, đặc biệt với checked exception.
- [ ] Không nuốt exception khi vẫn cần rollback.
- [ ] Không dựa vào self-invocation để kích hoạt proxy giao dịch.
- [ ] Dùng readOnly = true cho luồng chỉ đọc và không dùng nó như cơ chế chặn ghi.
- [ ] Có chiến lược khóa hoặc kiểm soát đồng thời cho dữ liệu dễ tranh chấp.
- [ ] Không giữ giao dịch mở trong thời gian gọi mạng hoặc xử lý lâu.
- [ ] Có kiểm thử tích hợp chứng minh các thay đổi ở nhiều Repository cùng commit hoặc cùng rollback.

## 10. Kết luận

@Transactional ở tầng Service xác định ranh giới của một nghiệp vụ. Khi các Repository tham gia cùng giao dịch và cùng transaction manager, ứng dụng có thể phối hợp nhiều thao tác đọc/ghi mà vẫn giữ tính nguyên tử: hoặc toàn bộ thay đổi được commit, hoặc toàn bộ thay đổi trong giao dịch được rollback. Để hành vi đúng trong thực tế, cần hiểu proxy của Spring, quy tắc rollback, propagation, cấu hình transaction manager và các vấn đề đồng thời của cơ sở dữ liệu.
