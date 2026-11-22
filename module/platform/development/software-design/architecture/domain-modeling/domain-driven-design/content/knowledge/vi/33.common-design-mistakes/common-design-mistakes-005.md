# Cho phép sửa Entity bên trong bằng Repository riêng

Trong Domain-Driven Design (DDD), một Aggregate là ranh giới nhất quán nghiệp vụ. Aggregate Root là điểm vào duy nhất để bên ngoài yêu cầu thay đổi trạng thái của Aggregate. Một lỗi thiết kế thường gặp là tạo Repository riêng cho từng Entity nằm bên trong Aggregate, sau đó cho application service hoặc controller nạp và sửa các Entity con trực tiếp.

Ví dụ, Order là Aggregate Root và OrderLine là Entity bên trong. Nếu ứng dụng có OrderRepository để lưu đơn hàng nhưng đồng thời có OrderLineRepository cho phép cập nhật số lượng từng dòng hàng độc lập, bất kỳ caller nào cũng có thể thay đổi một phần của đơn mà không đi qua quy tắc của Order. Khi đó Aggregate Boundary chỉ còn là cách nhóm class; nó không còn bảo vệ được các bất biến mà nhóm đã đặt vào Aggregate.

Nguyên tắc cần nhớ: **bên ngoài Aggregate chỉ yêu cầu thay đổi thông qua Aggregate Root; Repository của domain thường được định nghĩa cho Aggregate Root, không phải cho mọi Entity con**. Entity con vẫn có identity và hành vi riêng, nhưng quyền thay đổi nó được kiểm soát bởi root.

## 1. Aggregate Root bảo vệ điều gì?

Aggregate là một cụm đối tượng miền được xem như một đơn vị nhất quán. Aggregate Root:

- Là điểm truy cập từ bên ngoài đến Aggregate.
- Bảo vệ các invariant phải đúng sau mỗi transaction được chấp nhận.
- Điều phối thay đổi đối với Entity và Value Object bên trong.
- Kiểm soát việc thêm, xóa hoặc thay đổi đối tượng con.
- Là đối tượng được nạp và lưu thông qua Repository của Aggregate.

Entity bên trong Aggregate có thể có ID, trạng thái và hành vi riêng. Tuy nhiên, việc có identity không tự động khiến nó trở thành Aggregate Root. Câu hỏi quyết định là: **những quy tắc nào phải được bảo vệ cùng nhau, và đối tượng nào có quyền chấp nhận thay đổi?**

Ví dụ, một đơn hàng có thể có các quy tắc:

1. Chỉ đơn ở trạng thái DRAFT mới được sửa dòng hàng.
2. Số lượng của một dòng hàng phải lớn hơn 0.
3. Một đơn phải có ít nhất một dòng hàng khi xác nhận.
4. Tổng tiền đơn hàng phải được tính từ các dòng hàng hợp lệ.
5. Khi đơn đã CONFIRMED, không thể âm thầm sửa số lượng.

Nếu OrderLine được sửa độc lập, các quy tắc liên quan đến toàn bộ Order có thể bị bỏ qua.

## 2. Ví dụ: Order và OrderLine

Giả sử mô hình có cấu trúc:

~~~text
Order (Aggregate Root)
--------------------------------
orderId
customerId
status
version
lines

OrderLine (Entity bên trong)
--------------------------------
lineId
productId
quantity
unitPrice
~~~

OrderLine là Entity vì mỗi dòng có identity trong phạm vi đơn hàng và có thể được thay đổi trong vòng đời của đơn. Nhưng Order chịu trách nhiệm quyết định một dòng có được thêm, sửa hoặc xóa hay không.

Một thiết kế hợp lý thường chỉ công bố:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
~~~

Application service nạp Order, yêu cầu root thực hiện hành vi, rồi lưu Aggregate. Không cần một domain repository công khai cho OrderLine.

## 3. Anti-pattern: Repository riêng cho Entity con

Một thiết kế dễ gặp:

~~~java
public interface OrderLineRepository {
    Optional<OrderLine> findById(OrderLineId id);
    void save(OrderLine line);
}
~~~

Application service có thể sử dụng nó như sau:

~~~java
@Transactional
public void changeLineQuantity(
    OrderLineId lineId,
    int newQuantity
) {
    OrderLine line = orderLines.findById(lineId)
        .orElseThrow(OrderLineNotFound::new);

    line.changeQuantity(newQuantity);
    orderLines.save(line);
}
~~~

Đoạn code này cho phép thay đổi dòng hàng mà không nạp Order. Nó không kiểm tra trạng thái đơn, không yêu cầu root chấp thuận và không có cơ hội thực thi invariant cấp Aggregate.

Ví dụ, đơn đã xác nhận nhưng OrderLineRepository vẫn cho phép đổi số lượng. Dòng hàng có thể trở nên không khớp với tổng tiền, tồn kho đã giữ, hóa đơn hoặc các sự kiện đã phát ra cho đơn hàng.

Vấn đề không nằm ở tên interface. Dù gọi là DAO, service hay gateway, nếu tầng application có thể nạp và ghi Entity con độc lập để thay đổi trạng thái nghiệp vụ, Aggregate Root đã bị vượt qua.

## 4. Vì sao sửa Entity con trực tiếp làm suy yếu Aggregate?

**Bỏ qua invariant của root**

Root có thể chứa quy tắc liên quan đến toàn bộ Aggregate. Sửa child trực tiếp chỉ kiểm tra được quy tắc cục bộ của child, nếu có.

**Tạo nhiều điểm ghi**

Mọi caller có thể tự tìm repository con và thay đổi dữ liệu. Quy tắc nghiệp vụ bị phân tán giữa controller, application service, domain service và persistence adapter.

**Làm sai transaction boundary**

Một thao tác tưởng như chỉ sửa một dòng hàng có thể cần cập nhật tổng tiền, trạng thái đơn hoặc reservation liên quan. Nếu chỉ lưu child, các thay đổi cần thiết khác có thể không xảy ra.

**Làm khó concurrency control**

Optimistic locking hoặc version thường được đặt tại Aggregate Root để tuần tự hóa các thay đổi có thể ảnh hưởng invariant. Cập nhật child độc lập có thể không kiểm tra version của root, khiến hai transaction cùng phá vỡ quy tắc.

**Làm sai ý nghĩa của domain event**

Sự kiện như OrderLineQuantityChanged có thể cần được phát cùng quyết định nghiệp vụ của Order. Nếu child bị sửa ngoài root, event có thể thiếu hoặc không phản ánh đúng trạng thái tổng thể.

**Tạo coupling vào cấu trúc persistence**

Consumer bắt đầu phụ thuộc vào bảng hoặc ORM mapping của child. Khi Aggregate thay đổi cấu trúc, các caller đó phải sửa theo.

## 5. Thiết kế đúng: yêu cầu Aggregate Root thực hiện hành vi

Thay vì cho caller cập nhật OrderLine, hãy cung cấp một hành vi trên Order:

~~~java
public final class Order {
    private final OrderId id;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status;

    public void changeLineQuantity(
        OrderLineId lineId,
        int newQuantity
    ) {
        requireDraft();

        OrderLine line = lines.stream()
            .filter(candidate -> candidate.hasId(lineId))
            .findFirst()
            .orElseThrow(OrderLineNotFound::new);

        line.changeQuantity(newQuantity);
        recalculateTotals();
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new OrderCannotBeChanged(status);
        }
    }

    private void recalculateTotals() {
        // Tính lại tổng tiền theo chính sách của Order.
    }
}
~~~

OrderLine vẫn có hành vi thay đổi số lượng, nhưng hành vi đó không được công khai cho application layer:

~~~java
public final class OrderLine {
    private final OrderLineId id;
    private final ProductId productId;
    private int quantity;
    private final Money unitPrice;

    void changeQuantity(int newQuantity) {
        if (newQuantity <= 0) {
            throw new InvalidOrderLineQuantity();
        }
        this.quantity = newQuantity;
    }

    boolean hasId(OrderLineId candidate) {
        return id.equals(candidate);
    }
}
~~~

Trong ví dụ, changeQuantity() có package visibility để chỉ các class trong package domain có thể gọi. Tùy cách chia module, có thể dùng encapsulation khác để bảo đảm application không nhận được tham chiếu mutable đến child.

Root kiểm tra trạng thái đơn, tìm đúng dòng hàng, yêu cầu child thay đổi và cập nhật những dữ liệu tổng hợp cần thiết. Các quy tắc cục bộ vẫn nằm trong OrderLine; quy tắc liên quan toàn Aggregate nằm ở Order.

## 6. Application Service chỉ làm việc với Repository của Root

Use case trở nên rõ ràng:

~~~java
@Service
public class ChangeOrderLineQuantityHandler {
    private final OrderRepository orders;

    public ChangeOrderLineQuantityHandler(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void handle(ChangeOrderLineQuantity command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(OrderNotFound::new);

        order.changeLineQuantity(
            command.lineId(),
            command.newQuantity()
        );

        orders.save(order);
    }
}
~~~

Application service chịu trách nhiệm điều phối use case và transaction. Nó không tự tìm OrderLine, không tự sửa field và không tự tính lại invariant của đơn. Nó yêu cầu Aggregate Root thực hiện hành vi.

Điều này cũng giúp application layer diễn đạt ngôn ngữ nghiệp vụ: “đổi số lượng dòng hàng của đơn” thay vì “load row rồi update cột quantity”.

## 7. Không công khai collection mutable của Entity con

Ngay cả khi chỉ có OrderRepository, Aggregate vẫn có thể bị vượt qua nếu root trả ra collection mutable hoặc tham chiếu child cho caller sửa trực tiếp.

Không nên:

~~~java
public List<OrderLine> lines() {
    return lines;
}
~~~

Caller có thể xóa hoặc thêm phần tử trực tiếp:

~~~java
order.lines().clear();
~~~

Hãy trả về view không thể sửa:

~~~java
public List<OrderLineView> lineItems() {
    return lines.stream()
        .map(line -> new OrderLineView(
            line.id(),
            line.productId(),
            line.quantity(),
            line.unitPrice()
        ))
        .toList();
}
~~~

Nếu chỉ trả List.copyOf(lines), caller không thể thêm/xóa phần tử trong list, nhưng vẫn có thể gọi phương thức mutable trên từng child nếu phương thức đó public. Vì vậy, cần bảo vệ cả collection lẫn API thay đổi của child.

Đối với truy vấn, có thể trả DTO hoặc projection bất biến. Đối với command, hãy yêu cầu root thực hiện hành vi.

## 8. Repository của Aggregate Root lưu cả Aggregate như một đơn vị

Repository của Order chịu trách nhiệm nạp và lưu trạng thái cần thiết của toàn Aggregate:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
~~~

Với ORM như JPA, implementation có thể dùng cascade để lưu Entity con khi lưu root:

~~~java
@Entity
class OrderRecord {
    @Id
    private UUID id;

    @Version
    private long version;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLineRecord> lines = new ArrayList<>();
}
~~~

OrderLineRecord có thể là entity persistence riêng để ORM ánh xạ bảng. Điều đó không đồng nghĩa nó cần một domain Repository riêng. OrderRepository adapter quản lý việc chuyển đổi và lưu toàn bộ Aggregate theo mapping.

Cascade là cơ chế persistence; nó không tự bảo vệ invariant. Root vẫn phải kiểm soát thay đổi trong domain model, và transaction vẫn cần bảo đảm các cập nhật được commit nhất quán.

## 9. Phân biệt Repository với DAO hoặc truy vấn đọc

Không phải mọi truy vấn tới bảng order_lines đều vi phạm Aggregate Boundary.

Có thể có:

- Repository của Order dùng để nạp và lưu Aggregate.
- Query service đọc OrderLineView cho màn hình hoặc báo cáo.
- Read model/projection tối ưu cho tìm kiếm.
- Persistence DAO nội bộ được OrderRepository adapter sử dụng.

Điểm phân biệt là quyền thay đổi nghiệp vụ. Query có thể đọc dữ liệu child mà không nạp toàn bộ Aggregate nếu use case chỉ cần hiển thị hoặc phân tích. Nhưng một đường ghi nghiệp vụ không nên cập nhật child độc lập rồi bỏ qua root.

Ví dụ query:

~~~java
public interface OrderLineQueries {
    List<OrderLineView> findViewsByOrderId(OrderId id);
}
~~~

Interface này chỉ trả dữ liệu đọc. Nó không cung cấp save(OrderLine) hoặc changeQuantity() để sửa trạng thái nghiệp vụ.

CQRS cho phép read model có cấu trúc khác Aggregate. Read model có thể được cập nhật bằng projection hoặc event handler, nhưng nguồn ghi chính vẫn phải đi qua Aggregate Root.

## 10. Transaction và tính nhất quán

Giả sử thay đổi số lượng dòng hàng cần:

1. Kiểm tra đơn còn ở trạng thái DRAFT.
2. Kiểm tra số lượng hợp lệ.
3. Cập nhật dòng hàng.
4. Tính lại tổng tiền.
5. Cập nhật version của đơn.
6. Phát domain event nếu nghiệp vụ yêu cầu.

Các bước thuộc cùng một Aggregate cần được xử lý trong một transaction phù hợp. Repository riêng cho child có thể chỉ commit bước 3, để lại trạng thái tổng thể không hợp lệ.

Một transaction database bao quanh cả hai repository không tự làm thiết kế đúng. Nếu application service gọi OrderLineRepository.save() rồi tự cập nhật các trường của Order, invariant vẫn nằm ngoài Aggregate Root và mọi caller khác có thể lặp lại sai sót.

Transaction boundary cần bao quanh use case, còn quyền quyết định thay đổi vẫn thuộc Aggregate Root.

## 11. Concurrency: version của Root bảo vệ thay đổi

Giả sử hai request cùng sửa hai dòng khác nhau của một đơn hàng. Nếu quy tắc của đơn liên quan đến tổng tiền, số dòng hoặc trạng thái chung, hai thao tác vẫn có thể xung đột dù chúng sửa hai child khác nhau.

Optimistic locking trên Aggregate Root giúp phát hiện một transaction đã thay đổi Aggregate kể từ lúc transaction khác đọc nó:

~~~java
@Entity
class OrderRecord {
    @Id
    private UUID id;

    @Version
    private long version;
}
~~~

Nếu transaction thứ hai ghi với version cũ, persistence layer báo conflict. Application có thể nạp lại Aggregate, đánh giá lại command và trả kết quả phù hợp.

Lưu ý với ORM: không nên mặc định mọi thay đổi field của child Entity đều tự động tăng version của root. Với JPA, thay đổi một thuộc tính của OrderLineRecord có thể chỉ update row của dòng hàng; version ở OrderRecord không nhất thiết tăng nếu root không được dirty hoặc collection mapping không phát sinh thay đổi. Cần cấu hình và kiểm thử rõ cơ chế version ở cấp Aggregate, chẳng hạn force increment lock trên root, cập nhật version root một cách có chủ đích hoặc dùng cơ chế locking phù hợp. Annotation @Version trên root, đứng một mình, chưa đủ chứng minh mọi child update đều được bảo vệ.

Nếu child được cập nhật qua repository riêng mà không kiểm tra version của root, hai transaction có thể cùng ghi thành công trong khi invariant cấp đơn hàng đã bị phá vỡ. Cơ chế version cần đặt tại ranh giới bảo vệ quy tắc, không chỉ tại từng bảng.

Không phải mọi Aggregate đều bắt buộc dùng optimistic locking; lựa chọn phụ thuộc persistence và concurrency model. Nhưng nếu nhiều thay đổi có thể ảnh hưởng cùng invariant, cần một cơ chế đồng bộ hóa tại đúng ranh giới.

## 12. Domain Event nên phát từ quyết định của Root

Khi số lượng dòng hàng thay đổi, có thể cần phát OrderLineQuantityChanged. Root là nơi biết thay đổi có hợp lệ trong trạng thái đơn hiện tại hay không và có cập nhật các dữ liệu liên quan không.

~~~java
public void changeLineQuantity(
    OrderLineId lineId,
    int newQuantity
) {
    requireDraft();
    OrderLine line = findLine(lineId);
    int previousQuantity = line.quantity();
    line.changeQuantity(newQuantity);
    recalculateTotals();
    registerEvent(new OrderLineQuantityChanged(
        id,
        lineId,
        previousQuantity,
        newQuantity
    ));
}
~~~

Domain Event phản ánh sự thật đã được Aggregate chấp nhận. Application/infrastructure layer chịu trách nhiệm lưu hoặc publish event theo cơ chế phù hợp, ví dụ transactional outbox. Child không nên tự phát thông báo ra message broker để bỏ qua quyết định của root.

Nếu thay đổi child có ý nghĩa nghiệp vụ độc lập, không cần ảnh hưởng invariant của root và có thể tồn tại độc lập, đó có thể là dấu hiệu child thực ra nên là Aggregate Root riêng. Cần quyết định từ mô hình, không chỉ từ mong muốn phát event.

## 13. Khi nào Entity con thực sự nên trở thành Aggregate Root?

Không phải mọi đối tượng từng được gọi là child đều phải nằm trong Aggregate lớn mãi mãi. Có thể tách nó thành Aggregate Root riêng nếu:

- Nó có vòng đời độc lập với Aggregate hiện tại.
- Nó cần được truy cập và thay đổi độc lập trong nhiều use case.
- Các invariant của nó có thể được bảo vệ riêng.
- Thay đổi của nó không cần transaction nguyên tử với root cũ.
- Nhiều Aggregate khác tham chiếu nó bằng ID thay vì giữ object mutable.
- Ranh giới mới giúp giảm kích thước, contention hoặc coupling.

Ví dụ, Product thường không nên là Entity con của mọi Order. Sản phẩm có vòng đời, giá và quy tắc tồn tại độc lập; Order chỉ lưu ProductId và snapshot tên/giá tại thời điểm đặt.

Nếu OrderLine cần vòng đời độc lập, được nhiều quy trình quản lý riêng và không còn cần invariant nguyên tử với Order, nhóm có thể xem xét mô hình hóa nó thành Aggregate Root mới. Nhưng khi đó cần làm rõ cách đồng bộ giữa Order và đối tượng mới; không thể chỉ thêm một repository rồi giữ nguyên giả định cũ.

## 14. Tách Aggregate có thể tạo consistency eventual

Khi tách một Entity con thành Aggregate Root, một số quy tắc trước đây được bảo vệ trong cùng transaction có thể chuyển thành quy trình nhiều bước.

Ví dụ:

- Order phát OrderLineChangeRequested.
- OrderLine hoặc một context khác xử lý yêu cầu.
- Kết quả được phản hồi bằng event.
- Order cập nhật trạng thái theo kết quả.

Hoặc root mới có thể nhận command trực tiếp và phát event để các consumer cập nhật projection.

Những cách này đòi hỏi:

- Trạng thái trung gian được mô hình hóa rõ.
- Message idempotency và xử lý trùng.
- Retry, timeout và dead-letter handling.
- Compensation nếu quy trình không thể hoàn tất.
- Người dùng hiểu được eventual consistency khi cần.

Đừng tách Aggregate chỉ để giảm số lượng object được load nếu nghiệp vụ vẫn yêu cầu invariant được bảo vệ nguyên tử trên toàn bộ dữ liệu.

## 15. Dấu hiệu Aggregate Boundary đang quá lớn

Nếu Order chứa hàng chục nghìn dòng và mỗi thay đổi đều phải load toàn bộ dữ liệu, có thể Aggregate đang quá lớn hoặc ranh giới nhất quán chưa đúng.

Hãy xem xét:

- Các Entity con có thực sự cần thay đổi nguyên tử cùng root không?
- Một số đối tượng có vòng đời và invariant độc lập không?
- Có thể tham chiếu Aggregate khác bằng ID thay vì nhúng toàn bộ object không?
- Có hành vi nào chỉ là truy vấn và có thể dùng read model không?
- Có thể chia nhỏ quy trình thành nhiều bước với eventual consistency không?

Giải pháp không phải tạo Repository cho từng child trong khi vẫn tuyên bố chúng thuộc cùng Aggregate. Hãy thiết kế lại Aggregate Boundary nếu các child cần quyền thay đổi độc lập.

## 16. Những lỗi thường gặp khi thiết kế Repository cho Aggregate

**Tạo Repository cho mọi Entity.** Điều này biến Aggregate thành nhóm class không có điểm kiểm soát. Hãy định nghĩa Repository theo Aggregate Root.

**Cho application service sửa child trực tiếp.** Invariant cấp root bị bỏ qua. Hãy đưa hành vi thay đổi qua root.

**Trả collection mutable.** Caller có thể thêm/xóa child mà không qua quy tắc. Trả view bất biến và giữ API thay đổi bên trong.

**Cho rằng cascade đồng nghĩa với bảo vệ Aggregate.** Cascade chỉ quyết định ORM lưu/xóa quan hệ; nó không kiểm tra quy tắc nghiệp vụ.

**Dùng transaction chung để hợp thức hóa repository con.** Transaction có thể atomic ở database nhưng domain vẫn có nhiều điểm ghi bỏ qua root.

**Đọc child bằng query rồi dùng object đó để ghi.** Query model có thể cũ hoặc thiếu trạng thái Aggregate. Command nên nạp root hoặc gọi owner.

**Tách child thành root chỉ để tránh load dữ liệu.** Nếu invariant vẫn cần transaction nguyên tử, tách như vậy làm yếu consistency.

**Không kiểm soát concurrency ở root.** Hai thao tác trên child khác nhau vẫn có thể xung đột qua invariant chung. Dùng version/locking phù hợp tại ranh giới.

**Để child tự publish integration event.** Event có thể được phát trước khi Aggregate chấp nhận hoặc commit. Root ghi nhận sự kiện; adapter phát sau commit hoặc qua outbox.

## 17. Quy trình rà soát một Repository con hiện có

Nếu codebase đang có OrderLineRepository, hãy đánh giá theo các bước:

1. **Tìm tất cả caller:** controller, application service, batch job và message handler có đang dùng nó không?
2. **Xác định loại thao tác:** repository chỉ đọc projection hay có thể thay đổi trạng thái nghiệp vụ?
3. **Liệt kê invariant:** những quy tắc nào liên quan cả Order và OrderLine?
4. **Kiểm tra quyền sở hữu:** ai có quyền chấp nhận thay đổi quantity, price hoặc lifecycle?
5. **Kiểm tra transaction:** các thay đổi liên quan có được commit cùng nhau không?
6. **Kiểm tra concurrency:** version của Aggregate Root có được kiểm tra không?
7. **Chuyển write path:** đưa thao tác sửa vào hành vi của Order và chỉ lưu qua OrderRepository.
8. **Giữ read path nếu cần:** thay repository ghi bằng query projection chỉ đọc.
9. **Xóa đường ghi cũ:** sau khi mọi caller đã chuyển, loại bỏ save(OrderLine) khỏi API công khai.
10. **Bổ sung test:** kiểm tra không thể sửa child khi root ở trạng thái không cho phép và invariant luôn đúng.

Không nên xóa một repository trước khi xác định caller và vai trò thực tế của nó. Nếu nó chỉ là DAO nội bộ trong implementation của OrderRepository, có thể giữ lại ở infrastructure nhưng không công khai như domain Repository cho application layer.

## 18. Ví dụ test bảo vệ Aggregate Boundary

Test nên xác minh hành vi nghiệp vụ thông qua root:

~~~java
class OrderTest {
    @Test
    void cannotChangeLineQuantityAfterConfirmation() {
        Order order = anOrderWithOneLine();
        OrderLineId lineId = order.firstLineId();
        order.confirm();

        assertThrows(
            OrderCannotBeChanged.class,
            () -> order.changeLineQuantity(lineId, 3)
        );
    }

    @Test
    void rejectsNonPositiveLineQuantity() {
        Order order = anOrderWithOneLine();
        OrderLineId lineId = order.firstLineId();

        assertThrows(
            InvalidOrderLineQuantity.class,
            () -> order.changeLineQuantity(lineId, 0)
        );
    }
}
~~~

Tên factory và helper trong ví dụ (anOrderWithOneLine, firstLineId) là helper test minh họa. Test thực tế cần khởi tạo Aggregate qua API hợp lệ và kiểm tra trạng thái sau hành vi.

Có thể thêm integration test để xác minh repository nạp đủ child, lưu thay đổi cùng root và optimistic locking phát hiện xung đột. Unit test domain vẫn nên chạy độc lập với Spring và database.

## 19. Checklist thiết kế

- Repository công khai có được định nghĩa cho Aggregate Root không?
- Application service có nạp root trước khi thay đổi Entity con không?
- Mọi command thay đổi child có đi qua hành vi của root không?
- Root có kiểm tra invariant liên quan toàn Aggregate không?
- Entity con có tránh để lộ API mutable cho caller bên ngoài không?
- Collection child có được bảo vệ khỏi sửa trực tiếp không?
- Repository adapter có lưu toàn bộ Aggregate theo mapping phù hợp không?
- Có phân biệt domain Repository với DAO nội bộ và query projection không?
- Transaction boundary có bao quanh use case không?
- Concurrency control có bảo vệ đúng invariant cấp Aggregate không?
- Domain Event có phản ánh thay đổi được root chấp nhận không?
- Nếu child cần thay đổi độc lập, đã xem xét lại Aggregate Boundary chưa?
- Nếu tách Aggregate, consistency và quy trình phối hợp mới đã rõ chưa?

## 20. Nguyên tắc cần ghi nhớ

Repository không nên được tạo cho mọi Entity chỉ vì mỗi Entity có một bảng hoặc một class riêng. Trong DDD, Repository thường đại diện cho cách nạp và lưu Aggregate Root. Entity bên trong có thể có identity và hành vi riêng, nhưng các thay đổi nghiệp vụ phải đi qua root để bảo vệ invariant, transaction boundary và concurrency.

Nếu một child thực sự cần được truy cập và thay đổi độc lập, hãy xem lại Aggregate Boundary và xác định nó có nên trở thành Aggregate Root riêng hay không. Khi đó cần thiết kế lại consistency và cách các Aggregate phối hợp. Đừng giữ child bên trong một Aggregate nhưng đồng thời mở Repository riêng cho bên ngoài sửa trực tiếp; điều đó làm mất chính ranh giới mà Aggregate được tạo ra để bảo vệ.
