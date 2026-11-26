# Chọn ranh giới giao dịch theo ca sử dụng và yêu cầu nhất quán

Trong kiến trúc phân tầng, ranh giới giao dịch nên được chọn theo **đơn vị công việc nghiệp vụ cần bảo đảm nhất quán**, thường tương ứng với một ca sử dụng hoặc một phần rõ ràng của ca sử dụng. Khi một thao tác phải cập nhật nhiều dữ liệu cùng nhau, hệ thống cần xác định những thay đổi nào phải thành công hoặc thất bại như một đơn vị. Nếu ranh giới quá nhỏ, dữ liệu có thể chỉ được cập nhật một phần; nếu quá rộng, giao dịch giữ khóa lâu, làm giảm khả năng xử lý đồng thời và dễ bao trùm cả những thao tác bên ngoài cơ sở dữ liệu.

Trong module SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED — học tổ chức phần mềm theo kiến trúc phân tầng — bài học này tập trung vào cách tầng ứng dụng điều phối giao dịch theo ca sử dụng, cách domain bảo vệ bất biến, và cách tầng dữ liệu thực thi tính nguyên tử, cô lập và lưu bền. Không có một kích thước giao dịch cố định cho mọi ứng dụng. Ranh giới phù hợp phụ thuộc vào quy tắc nghiệp vụ, nơi lưu dữ liệu, yêu cầu nhất quán, mức độ đồng thời và những hệ thống bên ngoài tham gia vào quy trình.

## 1. Giao dịch bảo vệ điều gì?

Một giao dịch cơ sở dữ liệu gom một nhóm thao tác đọc/ghi thành một đơn vị có kết quả được quản lý chung. Với cơ sở dữ liệu quan hệ, các thuộc tính ACID thường được dùng để mô tả hành vi mong muốn:

- **Atomicity — tính nguyên tử:** hoặc tất cả thay đổi thuộc giao dịch được commit, hoặc chúng bị rollback. Không để một nửa thao tác được lưu lại khi phần còn lại thất bại.
- **Consistency — tính nhất quán:** giao dịch phải đưa dữ liệu từ một trạng thái hợp lệ sang trạng thái hợp lệ theo các ràng buộc được hệ thống bảo vệ. Cơ sở dữ liệu bảo vệ constraint; ứng dụng/domain bảo vệ các quy tắc nghiệp vụ.
- **Isolation — tính cô lập:** các giao dịch đồng thời không được quan sát hoặc gây ra những trạng thái trung gian trái với mức cô lập đã chọn. Mức cô lập cụ thể quyết định những hiện tượng đọc nào có thể xảy ra.
- **Durability — tính bền vững:** sau khi commit thành công, thay đổi được lưu bền theo cam kết của hệ quản trị cơ sở dữ liệu.

Giao dịch không tự động làm cho mọi quy tắc nghiệp vụ đúng. Ví dụ, một transaction có thể lưu thành công một đơn hàng rỗng nếu ứng dụng không kiểm tra bất biến và cơ sở dữ liệu không có constraint phù hợp. Transaction bảo đảm tính nguyên tử của các thao tác được đưa vào nó; domain vẫn cần xác định trạng thái nào là hợp lệ.

Hãy xét thao tác đặt hàng cần:

1. Kiểm tra sản phẩm và giá hiện tại.
2. Giảm số lượng tồn kho.
3. Tạo đơn hàng và các dòng hàng.
4. Ghi nhận trạng thái ban đầu của đơn.

Nếu giảm tồn kho thành công nhưng lưu đơn thất bại, hệ thống có thể mất hàng tồn mà không có đơn tương ứng. Nếu tạo đơn thành công nhưng giảm tồn kho thất bại, đơn có thể được xác nhận dù không còn hàng. Khi các thao tác này cùng nằm trong một transaction trên cùng cơ sở dữ liệu, chúng có thể được commit hoặc rollback như một đơn vị.

## 2. Chọn ranh giới theo ca sử dụng

Ca sử dụng mô tả một mục tiêu nghiệp vụ như đặt hàng, chuyển tiền, hủy đặt chỗ hoặc hoàn tiền. Tầng ứng dụng thường là nơi phù hợp để mở và kết thúc transaction vì nó biết các bước cần phối hợp để hoàn thành mục tiêu đó.

Một ranh giới giao dịch hợp lý thường bao gồm:

- Những lần đọc cần thiết để quyết định và thực hiện thay đổi.
- Các hành vi domain làm thay đổi trạng thái nghiệp vụ.
- Những thao tác ghi phải cùng thành công hoặc cùng thất bại.
- Việc ghi nhận các sự kiện nội bộ cần được lưu cùng trạng thái nếu tính nhất quán yêu cầu.

Ranh giới thường kết thúc khi ca sử dụng đã hoàn tất phần công việc nguyên tử trên một resource manager, chẳng hạn một cơ sở dữ liệu quan hệ. Không nên kéo transaction qua toàn bộ phiên làm việc của người dùng hoặc giữ nó mở trong lúc chờ người dùng nhập thêm dữ liệu.

### Ví dụ: đặt hàng và trừ tồn kho

Giả sử đơn hàng và tồn kho được lưu trong cùng một cơ sở dữ liệu. Việc tạo đơn và giữ/trừ tồn kho phải nhất quán: không tạo đơn được xác nhận nếu cập nhật tồn kho thất bại. Tầng ứng dụng điều phối toàn bộ thao tác:

~~~java
@Service
class PlaceOrderService implements PlaceOrderUseCase {
    private final ProductRepository products;
    private final OrderRepository orders;
    private final InventoryRepository inventory;

    PlaceOrderService(
            ProductRepository products,
            OrderRepository orders,
            InventoryRepository inventory) {
        this.products = products;
        this.orders = orders;
        this.inventory = inventory;
    }

    @Override
    @Transactional
    public OrderId handle(PlaceOrderCommand command) {
        List<OrderLine> lines = command.items().stream()
            .map(item -> {
                Product product = products.findById(item.productId())
                    .orElseThrow(ProductNotFoundException::new);

                inventory.reserve(product.id(), item.quantity());

                return OrderLine.of(
                    product.id(), item.quantity(), product.price());
            })
            .toList();

        Order order = Order.place(command.customerId(), lines);
        orders.save(order);

        return order.id();
    }
}
~~~

Ví dụ rút gọn giả định ProductRepository, InventoryRepository và OrderRepository cùng tham gia một transaction manager và cùng cơ sở dữ liệu. Nếu một lần reserve hoặc lưu đơn ném ngoại lệ làm transaction rollback, những thay đổi đã thực hiện trong transaction đó cũng được rollback. Việc reserve phải thực sự kiểm tra và cập nhật tồn kho một cách an toàn khi có nhiều yêu cầu đồng thời; chỉ đọc số lượng trước rồi ghi lại sau có thể gây bán vượt tồn.

Không phải mọi lần đọc đều cần khóa hoặc phải nằm trong transaction dài. Hãy xác định dữ liệu nào cần được đọc nhất quán với các thay đổi và chọn cơ chế đồng thời phù hợp. Những dữ liệu chỉ dùng để hiển thị hoặc không ảnh hưởng quyết định ghi có thể được đọc ngoài transaction hoặc theo chính sách cache riêng nếu nghiệp vụ cho phép.

### Vì sao không đặt transaction ở controller hoặc repository?

Controller thuộc tầng trình bày và chỉ biết một request HTTP. Một ca sử dụng có thể được gọi từ REST, CLI, message consumer hoặc tác vụ nền; đặt transaction ở controller sẽ làm cho các kênh khác không được bảo vệ như nhau.

Repository thường biểu diễn thao tác truy cập dữ liệu. Nếu mỗi phương thức repository tự mở transaction riêng, một ca sử dụng gọi nhiều repository có thể bị chia thành nhiều đơn vị commit độc lập. Khi repository thứ hai thất bại, thay đổi đã commit bởi repository thứ nhất có thể không được rollback.

Có thể dùng transaction ở một phương thức repository trong những trường hợp kỹ thuật cụ thể, nhưng transaction bao quanh đơn vị công việc nghiệp vụ thường nên được điều phối ở tầng ứng dụng. Domain tập trung vào quy tắc và trạng thái; nó không cần điều khiển Spring transaction hoặc gọi commit/rollback trực tiếp.

## 3. Ranh giới giao dịch không nhất thiết bằng một phương thức hoặc một bảng

Một ca sử dụng có thể chạm tới nhiều bảng và nhiều repository. Nếu các thay đổi phải cùng tồn tại để bảo đảm một bất biến, chúng nên nằm trong cùng transaction khi cùng một cơ sở dữ liệu có thể bảo đảm tính nguyên tử.

Ngược lại, một phương thức có thể chỉ đọc dữ liệu và không cần transaction ghi. Một thao tác ghi đơn giản có thể chỉ cập nhật một bảng. Kích thước transaction không được quyết định bởi số lượng lớp hoặc số lượng câu SQL, mà bởi điều kiện nhất quán mà nghiệp vụ cần.

| Tình huống | Ranh giới thường phù hợp | Lý do |
|---|---|---|
| Tạo đơn và trừ tồn kho trong cùng database | Một transaction cho ca sử dụng đặt hàng | Hai thay đổi phải cùng thành công để không tạo đơn thiếu hàng hoặc làm mất tồn kho. |
| Chuyển tiền giữa hai tài khoản cùng database | Một transaction bao trọn ghi nợ, ghi có và bút toán | Không thể để chỉ một tài khoản bị thay đổi. |
| Cập nhật hồ sơ đơn giản ở một bảng | Transaction ngắn bao quanh lần ghi | Đơn vị thay đổi nhỏ và rõ ràng. |
| Truy vấn danh sách để hiển thị | Có thể dùng read-only transaction hoặc không cần transaction tường minh tùy công nghệ và yêu cầu | Không có thay đổi ghi cần commit; cần cân nhắc nhất quán của nhiều truy vấn. |
| Gửi email sau khi tạo đơn | Không giữ transaction database mở trong lúc chờ SMTP | Email là tác động bên ngoài và không thể rollback bằng rollback database. |
| Gọi dịch vụ thanh toán từ xa | Thường tách thành workflow nhiều bước có trạng thái và xử lý lỗi | Transaction cục bộ không thể tự hoàn tác giao dịch đã được dịch vụ khác commit. |

Đừng mở transaction ngay khi người dùng bắt đầu nhập biểu mẫu rồi giữ nó cho tới khi họ bấm xác nhận. Hãy nhận và kiểm tra dữ liệu ở tầng trình bày trước; khi người dùng gửi yêu cầu hoàn chỉnh, ứng dụng mới mở transaction cho phần xử lý cần tính nguyên tử.

## 4. Nhất quán và xử lý truy cập đồng thời

Một ranh giới transaction đúng vẫn cần chiến lược xử lý khi nhiều yêu cầu chạy cùng lúc. Ví dụ, kho có một sản phẩm còn một đơn vị. Hai khách hàng cùng đặt sản phẩm đó. Nếu cả hai transaction đều đọc số lượng là một trước khi transaction nào cập nhật, cả hai có thể cùng tạo đơn và làm tồn kho âm nếu thao tác không được bảo vệ.

Có nhiều cách xử lý; chọn theo mức tranh chấp, chi phí khóa và yêu cầu nghiệp vụ.

### Cập nhật có điều kiện

Một câu lệnh cập nhật nguyên tử có thể giảm tồn kho chỉ khi số lượng còn đủ:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - :quantity
WHERE product_id = :productId
  AND available_quantity >= :quantity;
~~~

Ứng dụng kiểm tra số dòng bị ảnh hưởng. Nếu không có dòng nào được cập nhật, sản phẩm không tồn tại hoặc lượng hàng không đủ theo điều kiện của câu lệnh. Cách này hữu ích vì kiểm tra và cập nhật được thực hiện trong một thao tác cơ sở dữ liệu. Cần phân biệt trường hợp không tồn tại với hết hàng nếu nghiệp vụ cần thông báo khác nhau.

### Optimistic locking

Khi xung đột không thường xuyên, optimistic locking cho phép nhiều transaction đọc trước, nhưng phát hiện xung đột lúc cập nhật bằng một version. Với JPA có thể dùng:

~~~java
@Entity
class InventoryJpaEntity {
    @Id
    private UUID productId;

    private int availableQuantity;

    @Version
    private long version;
}
~~~

Nếu một transaction cập nhật bản ghi dựa trên version cũ sau khi transaction khác đã cập nhật, ORM hoặc cơ sở dữ liệu phát hiện số dòng cập nhật không khớp và báo lỗi optimistic lock. Ứng dụng có thể retry có giới hạn hoặc trả lỗi xung đột để người gọi thử lại. Retry phải được cân nhắc cẩn thận nếu ca sử dụng có tác động bên ngoài hoặc không idempotent.

### Pessimistic locking

Khi tranh chấp cao và nghiệp vụ cần tuần tự hóa cập nhật trên một bản ghi, có thể khóa bản ghi trong transaction. Ví dụ với Spring Data JPA:

~~~java
public interface InventoryJpaRepository
        extends JpaRepository<InventoryJpaEntity, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select i from InventoryJpaEntity i where i.productId = :id")
    Optional<InventoryJpaEntity> findForUpdate(UUID id);
}
~~~

Khóa ghi giúp transaction khác phải chờ hoặc thất bại tùy cơ sở dữ liệu và cấu hình. Khóa phải được giữ trong thời gian ngắn; nếu transaction làm nhiều việc chậm hoặc gọi mạng trong lúc giữ khóa, thông lượng có thể giảm và nguy cơ deadlock tăng.

### Constraint và mức cô lập

Constraint như UNIQUE, CHECK và khóa ngoại giúp cơ sở dữ liệu từ chối trạng thái không hợp lệ kể cả khi có nhiều đường ghi. Ví dụ, ràng buộc UNIQUE trên mã giao dịch có thể ngăn hai transaction tạo cùng một định danh nghiệp vụ.

Mức cô lập transaction xác định các hiện tượng đọc/ghi có thể xảy ra. Read committed, repeatable read và serializable có hành vi, chi phí khác nhau tùy hệ quản trị. Không nên chọn mức cao nhất cho mọi thao tác theo thói quen; hãy xác định bất biến cần bảo vệ, kiểm thử dưới tải đồng thời và xem tài liệu của hệ quản trị đang dùng. Với một số quy tắc, cập nhật có điều kiện hoặc optimistic locking có thể là lựa chọn rõ ràng hơn việc nâng mức cô lập toàn cục.

## 5. Spring quản lý transaction như thế nào?

Trong Spring, annotation @Transactional thường được đặt trên phương thức dịch vụ ứng dụng để Spring mở transaction trước khi gọi phương thức và commit khi phương thức kết thúc bình thường. Nếu có lỗi phù hợp với chính sách rollback, transaction được rollback.

~~~java
@Service
class ConfirmOrderService {
    private final OrderRepository orders;

    ConfirmOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void confirm(OrderId id) {
        Order order = orders.findById(id)
            .orElseThrow(OrderNotFoundException::new);

        order.confirm();
        orders.save(order);
    }
}
~~~

Một số điểm cần nhớ khi dùng Spring transaction:

- Cơ chế mặc định dựa trên proxy trong cách cấu hình phổ biến. Lời gọi nội bộ từ một phương thức trong cùng đối tượng sang phương thức khác có @Transactional (self-invocation) thường không đi qua proxy nên không kích hoạt transaction mới theo annotation đó.
- Theo mặc định, Spring rollback với RuntimeException và Error; checked exception không tự động rollback trong cấu hình mặc định. Có thể cấu hình rollbackFor khi ca sử dụng cần rollback với checked exception cụ thể.
- Propagation quyết định cách một phương thức tham gia hoặc tạo transaction so với transaction hiện tại. REQUIRED thường phù hợp cho các bước cùng thuộc một ca sử dụng; REQUIRES_NEW tạo transaction độc lập và cần được dùng khi có chủ đích.
- Isolation và timeout có thể được cấu hình theo yêu cầu, nhưng cần hiểu hành vi của transaction manager và cơ sở dữ liệu thực tế.
- @Transactional trên phương thức đọc có thể dùng readOnly = true như một gợi ý tối ưu cho một số nền tảng; nó không phải lúc nào cũng là cơ chế cấm ghi tuyệt đối.
- Transaction gắn với resource và transaction manager cụ thể. Không mặc định rằng một transaction Spring cục bộ sẽ bao trùm mọi cơ sở dữ liệu, message broker hoặc HTTP service mà phương thức gọi tới.

Tránh dựa vào một annotation mà không hiểu cách lời gọi thực sự đi qua Spring proxy. Nếu cần transaction boundary rõ ràng, hãy đặt phương thức public của ca sử dụng trên bean Spring được gọi từ bean khác và kiểm tra hành vi qua integration test.

## 6. Khi ca sử dụng cần nhiều hệ thống bên ngoài

Transaction ACID của một cơ sở dữ liệu không thể rollback một email đã gửi, một khoản thanh toán đã được cổng thanh toán chấp nhận hoặc một message đã được hệ thống khác xử lý. Nếu giữ transaction database mở trong lúc gọi dịch vụ bên ngoài, thời gian giữ kết nối và khóa tăng lên, nhưng lỗi mạng vẫn có thể khiến kết quả bên ngoài không rõ ràng.

Ví dụ đặt hàng và thanh toán:

1. Tạo đơn ở trạng thái PENDING_PAYMENT và ghi một yêu cầu thanh toán cần xử lý.
2. Commit trạng thái đơn và thông tin yêu cầu trong transaction database ngắn.
3. Một worker gửi yêu cầu tới cổng thanh toán.
4. Khi nhận kết quả, ứng dụng cập nhật đơn thành PAID hoặc PAYMENT_FAILED trong transaction khác.
5. Nếu thanh toán thành công nhưng việc cập nhật trạng thái bị lỗi, hệ thống cần có cơ chế đối soát hoặc xử lý lại dựa trên định danh giao dịch.

Đây là workflow nhiều bước, thường được mô hình hóa như saga hoặc quy trình điều phối có trạng thái. Mỗi bước có transaction cục bộ của nó. Khi một bước sau thất bại, hệ thống có thể thực hiện hành động bù (compensation) nếu nghiệp vụ cho phép, chẳng hạn hủy giữ chỗ hoặc hoàn tiền. Hành động bù là một hành động nghiệp vụ mới, không phải rollback vật lý của transaction trước đó.

### Transactional outbox

Một lỗi phổ biến là cập nhật đơn trong database rồi gửi message ngay sau đó. Nếu database commit thành công nhưng gửi message thất bại, hệ thống có đơn mới nhưng không có sự kiện thông báo. Nếu gửi message trước rồi database rollback, consumer có thể xử lý một sự kiện cho thay đổi chưa được lưu.

Transactional outbox giải quyết khoảng trống này bằng cách ghi trạng thái nghiệp vụ và một bản ghi outbox trong cùng transaction:

~~~java
@Transactional
public OrderId placeOrder(PlaceOrderCommand command) {
    Order order = Order.place(command.customerId(), command.lines());
    orders.save(order);

    outbox.save(OutboxMessage.pending(
        "OrderPlaced",
        order.id().value(),
        orderPlacedPayload(order)
    ));

    return order.id();
}
~~~

Một tiến trình riêng đọc các bản ghi outbox chưa gửi và phát message tới broker. Sau khi gửi thành công, nó đánh dấu bản ghi đã xử lý. Vì publish có thể bị lặp nếu worker gặp sự cố sau khi gửi nhưng trước khi đánh dấu, consumer cần xử lý message theo cách idempotent. Outbox bảo đảm trạng thái nghiệp vụ và ý định phát sự kiện được lưu cùng nhau; nó không biến database và broker thành một transaction phân tán duy nhất.

## 7. Chọn chiến lược theo yêu cầu nhất quán

Trước khi đặt @Transactional hoặc chọn mức khóa, hãy xác định điều gì phải đúng và trong khoảng thời gian nào.

| Yêu cầu nghiệp vụ | Câu hỏi thiết kế | Hướng xử lý có thể cân nhắc |
|---|---|---|
| Tất cả thay đổi cùng thành công | Những bản ghi nào phải được commit như một đơn vị? | Một transaction cục bộ bao trọn ca sử dụng trên cùng resource manager. |
| Không bán vượt tồn kho | Hai yêu cầu đồng thời có thể cùng tiêu thụ một đơn vị hàng không? | Cập nhật có điều kiện, optimistic/pessimistic locking hoặc constraint phù hợp. |
| Chuyển tiền không mất hoặc nhân đôi | Ghi nợ, ghi có và bút toán có cùng nguyên tử không? | Một transaction trên cùng database; định danh duy nhất và kiểm soát đồng thời. |
| Dữ liệu đọc có thể chậm cập nhật | Người dùng có chấp nhận thấy trạng thái cũ trong một khoảng ngắn không? | Read model/cache hoặc xử lý bất đồng bộ với eventual consistency có chủ đích. |
| Gửi sự kiện sau khi lưu | Làm sao tránh commit dữ liệu nhưng mất sự kiện? | Transactional outbox và consumer idempotent. |
| Quy trình qua nhiều dịch vụ | Một dịch vụ thất bại sau khi dịch vụ khác đã commit thì xử lý ra sao? | Saga, trạng thái tiến trình, retry, timeout và hành động bù phù hợp. |

Không phải mọi ứng dụng cần eventual consistency hoặc saga. Nếu tất cả dữ liệu thuộc một cơ sở dữ liệu và cần nguyên tử, một transaction cục bộ có thể là giải pháp đơn giản nhất. Nếu quy trình trải qua nhiều dịch vụ độc lập, cố ép một transaction kéo dài qua mạng thường làm tăng phụ thuộc và khó phục hồi khi lỗi.

## 8. Những sai lầm thường gặp khi đặt ranh giới transaction

- **Transaction quá nhỏ:** mỗi repository method tự commit, khiến một ca sử dụng có nhiều thay đổi nhưng không thể rollback cùng nhau.
- **Transaction quá rộng:** giữ transaction qua thao tác chờ người dùng, gọi HTTP, gửi email hoặc xử lý tệp lớn; khóa và kết nối bị giữ lâu.
- **Dựa vào kiểm tra trước khi ghi:** đọc số dư hoặc tồn kho rồi mới cập nhật mà không có khóa, version hoặc câu lệnh điều kiện; hai transaction có thể cùng vượt qua kiểm tra.
- **Cho rằng rollback database hoàn tác mọi thứ:** email, HTTP request hoặc message đã gửi không tự biến mất khi database rollback.
- **Nuốt ngoại lệ:** catch exception rồi trả kết quả bình thường có thể khiến transaction commit dù thao tác nghiệp vụ đã thất bại. Nếu lỗi cần rollback, hãy để nó truyền ra hoặc đánh dấu rollback-only theo cách rõ ràng.
- **Dùng REQUIRES_NEW tùy tiện:** transaction con có thể commit độc lập dù transaction ngoài rollback, làm dữ liệu không còn phản ánh một đơn vị công việc như mong muốn.
- **Nhầm readOnly với bảo đảm nhất quán:** readOnly thường là gợi ý cho nền tảng; nó không thay thế thiết kế truy vấn và isolation phù hợp.

## 9. Quy trình chọn ranh giới giao dịch cho một ca sử dụng

Khi thiết kế một chức năng mới, hãy thực hiện lần lượt:

1. **Mô tả kết quả nghiệp vụ cần đạt.** Xác định trạng thái nào phải được tạo ra hoặc thay đổi khi hành động thành công.
2. **Liệt kê các thay đổi phải cùng thành công.** Bao gồm bản ghi chính, bản ghi con, số dư, tồn kho, lịch sử hoặc outbox nếu chúng thuộc cùng một đơn vị nguyên tử.
3. **Xác định resource manager.** Các thay đổi có nằm trong cùng một cơ sở dữ liệu/transaction manager không? Nếu có nhiều hệ thống, xác định rõ transaction cục bộ của từng bước.
4. **Xác định điều kiện đồng thời.** Có hai yêu cầu nào có thể cập nhật cùng một dữ liệu không? Cần constraint, optimistic locking, pessimistic locking hay cập nhật có điều kiện?
5. **Đặt transaction ở tầng điều phối ca sử dụng.** Giữ phần đọc/ghi cần nhất quán trong phạm vi ngắn, tránh chờ người dùng và tránh gọi mạng chậm khi đang giữ khóa.
6. **Thiết kế phục hồi lỗi.** Xác định lỗi nào rollback, bước nào có thể retry, tác động bên ngoài nào cần idempotency hoặc hành động bù.
7. **Kiểm thử dưới tình huống lỗi và đồng thời.** Xác minh không có cập nhật một phần, không vượt invariant và hệ thống có thể phục hồi khi message hoặc dịch vụ ngoài thất bại.

Ranh giới giao dịch tốt bảo vệ đúng đơn vị nghiệp vụ cần nhất quán, đồng thời giữ thời gian khóa và phạm vi phụ thuộc ở mức có thể kiểm soát. Tầng ứng dụng xác định các bước thuộc ca sử dụng; domain bảo vệ bất biến; adapter dữ liệu thực thi thao tác lưu trữ; còn các quy trình qua nhiều dịch vụ cần trạng thái, retry và hành động bù rõ ràng. Khi chọn ranh giới theo yêu cầu nhất quán thực tế, hệ thống dễ hiểu hơn và có khả năng xử lý lỗi tốt hơn.

