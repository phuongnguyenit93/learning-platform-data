# Tránh repository cho mọi entity bên trong aggregate

Trong Domain-Driven Design (DDD), Repository cung cấp cách truy cập các đối tượng miền đã được lưu mà không để application code phụ thuộc trực tiếp vào cơ chế persistence. Tuy nhiên, không nên tạo một Repository riêng cho mọi Entity có bảng hoặc có identity trong cơ sở dữ liệu.

Repository thường được thiết kế theo **Aggregate Root**. Một Aggregate là ranh giới nhất quán gồm một root và các đối tượng bên trong. Các đối tượng con được tải, thay đổi và lưu thông qua root để những invariant thuộc Aggregate được bảo vệ tại một điểm kiểm soát rõ ràng.

Ví dụ, một đơn hàng có thể gồm Order và nhiều OrderLine. Nếu Order là Aggregate Root, application nên tải Order qua OrderRepository rồi gọi hành vi trên Order để thêm, sửa hoặc xóa OrderLine. Tạo OrderLineRepository chỉ để application lấy một dòng hàng, sửa trực tiếp số lượng rồi lưu riêng có thể bỏ qua quy tắc tổng số lượng, trạng thái đơn hoặc cách tính tổng tiền.

Nguyên tắc này không có nghĩa mọi Entity đều phải nằm trong một Aggregate lớn, cũng không có nghĩa không bao giờ được truy vấn dữ liệu của Entity con. Điều cần phân biệt là **Repository dùng để nạp và lưu Aggregate** với **truy vấn phục vụ đọc hoặc báo cáo**. Thiết kế đúng giúp giữ invariant, transaction boundary và quyền sở hữu mô hình của Aggregate.

## 1. Repository trong DDD giải quyết vấn đề gì?

Repository cung cấp một abstraction để application làm việc với Aggregate như thể đang truy cập một collection trong domain. Application yêu cầu tìm Aggregate theo identity hoặc lưu Aggregate sau khi thực hiện hành vi nghiệp vụ. Infrastructure chịu trách nhiệm thực hiện việc đọc và ghi bằng database, ORM hoặc công nghệ lưu trữ cụ thể.

Repository giúp:

- Tách domain/application khỏi chi tiết SQL, ORM và database.
- Cung cấp điểm truy cập rõ ràng cho Aggregate Root.
- Bảo đảm application tải đúng đơn vị cần thiết để thực hiện use case.
- Kết hợp với Unit of Work hoặc transaction để lưu các thay đổi nhất quán.
- Làm rõ đối tượng nào là ranh giới nhất quán mà hệ thống cần bảo vệ.

Repository không đơn giản là một class có các hàm CRUD cho mọi bảng. Nếu cứ mỗi Entity hoặc bảng có một Repository, application có thể thao tác trực tiếp vào các thành phần bên trong Aggregate và làm suy yếu ranh giới mà DDD muốn bảo vệ.

### Repository và DAO không hoàn toàn đồng nghĩa

DAO (Data Access Object) thường tổ chức truy cập dữ liệu theo bảng hoặc nguồn dữ liệu. Repository trong DDD hướng đến một tập hợp Aggregate theo ngôn ngữ miền.

Một hệ thống có thể có nhiều DAO hoặc persistence adapter bên dưới một Repository. Nhưng application không nhất thiết phải biết từng bảng hoặc từng DAO đó.

| Khía cạnh | Repository theo DDD | DAO / Table Gateway |
|---|---|---|
| Trọng tâm | Aggregate Root và mô hình miền | Bảng, bản ghi hoặc nguồn dữ liệu |
| API | Hành vi truy cập Aggregate | Truy vấn và thao tác dữ liệu |
| Invariant | Hỗ trợ giữ invariant qua Aggregate Root | Không tự bảo đảm invariant miền |
| Người sử dụng thường gặp | Application Service / Use Case | Repository implementation hoặc tầng persistence |
| Cách lưu | Thường lưu Aggregate như một đơn vị | Có thể thao tác từng bảng hoặc bản ghi |

DAO vẫn hữu ích trong Infrastructure. Vấn đề phát sinh khi đưa DAO cho từng Entity con trực tiếp lên application và cho phép use case thay đổi dữ liệu mà không đi qua Aggregate Root.

## 2. Aggregate Root quyết định ranh giới Repository

Aggregate là một nhóm đối tượng miền được xem như một đơn vị nhất quán. Aggregate Root là đối tượng gốc mà bên ngoài được phép dùng để truy cập và yêu cầu thay đổi Aggregate.

Ví dụ:

    Order (Aggregate Root)
      - OrderId
      - CustomerId
      - Status
      - OrderLine
          - OrderLineId
          - ProductId
          - Quantity
          - UnitPrice
      - OrderLine
          - OrderLineId
          - ProductId
          - Quantity
          - UnitPrice

Trong mô hình này, OrderLine là entity con bên trong Aggregate Order. Các dòng hàng có thể có identity riêng để phân biệt từng dòng, nhưng điều đó không tự động khiến chúng cần một Repository riêng.

OrderRepository chịu trách nhiệm nạp và lưu Aggregate Order. Application không cần OrderLineRepository chỉ để sửa một dòng hàng thuộc Order.

### Identity của entity con không quyết định Repository

Một entity con có thể có ID vì:

- Cần phân biệt các đối tượng cùng loại bên trong Aggregate.
- Cần tham chiếu chính xác dòng hàng khi người dùng sửa hoặc xóa.
- Cần theo dõi vòng đời hoặc lịch sử của đối tượng con.
- Cần ánh xạ dữ liệu persistence.

Nhưng identity không đồng nghĩa với quyền truy cập độc lập. Một OrderLine có OrderLineId vẫn có thể chỉ được truy cập thông qua Order.

Câu hỏi quan trọng là: entity này có cần được tải và thay đổi độc lập để bảo vệ một tập invariant riêng không? Nếu câu trả lời là không, và các thay đổi của nó phải được kiểm soát bởi root, Repository riêng thường không cần thiết.

### Một Repository cho mỗi Aggregate Root

Một quy tắc thiết kế thực tế là:

- Mỗi Aggregate Root có một Repository phù hợp.
- Entity và Value Object bên trong Aggregate được nạp cùng Aggregate khi cần.
- Thay đổi các đối tượng con thông qua hành vi của root.
- Lưu thay đổi thông qua Repository của root hoặc Unit of Work.
- Aggregate khác được truy cập bằng identity của Aggregate Root đó, không đi sâu vào object graph của Aggregate khác.

Không phải mọi class có tên Entity đều cần Repository. Repository phục vụ ranh giới nhất quán, không phải danh sách các kiểu dữ liệu.

## 3. Vì sao không nên tạo Repository cho từng Entity con?

### Làm suy yếu invariant của Aggregate

Giả sử Order có quy tắc:

- Chỉ đơn ở trạng thái DRAFT mới được thay đổi dòng hàng.
- Số lượng của mỗi dòng phải lớn hơn 0.
- Tổng số lượng không được vượt giới hạn đơn hàng.
- Không được xóa dòng cuối cùng nếu nghiệp vụ yêu cầu đơn phải còn ít nhất một dòng.
- Tổng tiền phải được tính lại theo chính sách giá và chiết khấu.

Nếu application gọi OrderLineRepository để sửa số lượng trực tiếp, những quy tắc này có thể không được thực thi.

Ví dụ:

    OrderLine line = orderLineRepository.findById(lineId);
    line.setQuantity(100);
    orderLineRepository.save(line);

Đoạn code này không thể hiện rằng Order đang ở trạng thái nào, tổng số lượng có vượt giới hạn không hoặc tổng tiền có cần tính lại không. Nó thay đổi một phần Aggregate mà không qua root.

Thiết kế an toàn hơn:

    Order order = orderRepository.findById(orderId)
            .orElseThrow(OrderNotFoundException::new);

    order.changeLineQuantity(lineId, 100);

    orderRepository.save(order);

Order kiểm tra trạng thái, tìm dòng hàng bên trong Aggregate, xác thực số lượng và cập nhật các giá trị liên quan. Application không cần biết cách OrderLine được lưu ở bảng nào.

### Phá vỡ transaction boundary

Invariant của Aggregate thường cần được bảo vệ trong một transaction. Nếu application lưu OrderLine riêng rồi lưu Order bằng một thao tác khác, hệ thống có thể rơi vào trạng thái dở dang khi một trong hai thao tác thất bại.

Ví dụ:

1. OrderLineRepository cập nhật số lượng thành công.
2. Cập nhật tổng tiền của Order thất bại.
3. Database chứa dòng hàng mới nhưng tổng tiền vẫn cũ.

Nếu cả hai thay đổi thuộc cùng Aggregate và cần nhất quán cùng nhau, chúng nên nằm trong cùng một transaction và được điều phối qua root.

### Tạo nhiều điểm ghi cho cùng một trạng thái

Khi có OrderRepository và OrderLineRepository cùng được application sử dụng để sửa dữ liệu, có nhiều đường ghi vào một Aggregate. Mỗi đường có thể áp dụng quy tắc khác nhau hoặc bỏ qua một số bước.

Nhiều điểm ghi làm khó việc xác định:

- Quy tắc nào đã được kiểm tra?
- Khi nào tổng tiền được tính lại?
- Domain Event nào được tạo?
- Version nào cần tăng?
- Ai chịu trách nhiệm xử lý optimistic concurrency?
- Có cần ghi audit hay không?

Một Repository cho Aggregate Root giúp thu hẹp các đường ghi và làm rõ nơi kiểm soát hành vi.

### Làm lộ cấu trúc persistence vào application

Nếu application phải gọi nhiều Repository tương ứng với từng bảng để dựng lại một đơn hàng, nó đang biết quá nhiều về cách Aggregate được lưu.

Ví dụ:

    Order order = orderRepository.findHeader(orderId);
    List<OrderLine> lines = orderLineRepository.findAllByOrder(orderId);
    List<Discount> discounts = discountRepository.findByOrder(orderId);

    order.attachLines(lines);
    order.attachDiscounts(discounts);

Cách làm này khiến application phải tự lắp ráp object graph. Nó có thể quên một thành phần cần thiết hoặc ghép dữ liệu không nhất quán. Repository của Aggregate nên che giấu việc Aggregate được lưu ở một hay nhiều bảng.

## 4. Truy cập Entity con thông qua Aggregate Root

Aggregate Root cung cấp các hành vi có ý nghĩa nghiệp vụ để thay đổi đối tượng con. Application truyền identity của entity con vào root, sau đó root tìm đối tượng nội bộ và áp dụng quy tắc.

Ví dụ:

    public final class Order {
        private final OrderId id;
        private final List<OrderLine> lines;
        private OrderStatus status;

        public void addLine(
                ProductId productId,
                Quantity quantity,
                Money unitPrice
        ) {
            requireDraft();

            OrderLine line = OrderLine.create(
                    OrderLineId.newId(),
                    productId,
                    quantity,
                    unitPrice
            );

            lines.add(line);
        }

        public void changeLineQuantity(
                OrderLineId lineId,
                Quantity newQuantity
        ) {
            requireDraft();

            OrderLine line = findLine(lineId);
            line.changeQuantity(newQuantity);

            ensureOrderLimits();
        }

        public void removeLine(OrderLineId lineId) {
            requireDraft();

            if (lines.size() == 1) {
                throw new OrderMustContainALine();
            }

            lines.remove(findLine(lineId));
        }

        private OrderLine findLine(OrderLineId lineId) {
            return lines.stream()
                    .filter(line -> line.id().equals(lineId))
                    .findFirst()
                    .orElseThrow(OrderLineNotFoundException::new);
        }

        private void requireDraft() {
            if (status != OrderStatus.DRAFT) {
                throw new OrderCannotBeChanged();
            }
        }

        private void ensureOrderLimits() {
            // Kiểm tra các invariant của toàn Order.
        }
    }

Trong ví dụ, OrderLine có thể có hành vi riêng như changeQuantity(), nhưng application không gọi trực tiếp entity con. Root quyết định khi nào hành vi đó được phép và kiểm tra invariant liên quan đến toàn đơn.

Điều này không làm OrderLine trở thành một cấu trúc dữ liệu thụ động. Entity con vẫn có thể bảo vệ các quy tắc nội tại của nó. Root bảo vệ các invariant cần nhìn trên toàn Aggregate.

### Root không cần phơi bày collection có thể sửa

Không nên trả về collection mutable để application thêm hoặc xóa phần tử tùy ý:

    public List<OrderLine> lines() {
        return lines;
    }

Caller có thể gọi lines().clear() và phá invariant mà không thông qua Order.

Thay vào đó, trả về view không thể sửa hoặc bản sao:

    public List<OrderLine> lines() {
        return List.copyOf(lines);
    }

Nếu OrderLine mutable, cần cân nhắc việc trả trực tiếp reference của entity con. Có thể cung cấp các phương thức truy vấn chỉ đọc, DTO hoặc Value Object snapshot để bên ngoài không sửa state nội bộ.

## 5. Repository của Aggregate Root trông như thế nào?

Repository nên dùng kiểu identity của root và cung cấp những thao tác cần thiết để nạp/lưu Aggregate.

    public interface OrderRepository {
        Optional<Order> findById(OrderId id);

        void save(Order order);
    }

Nếu use case cần tìm theo một tiêu chí nghiệp vụ, có thể bổ sung phương thức phù hợp:

    public interface OrderRepository {
        Optional<Order> findById(OrderId id);

        Optional<Order> findOpenOrderFor(CustomerId customerId);

        void save(Order order);
    }

Không nên biến Repository thành một API truy vấn tùy ý chứa hàng chục phương thức tìm kiếm mọi kiểu dữ liệu. Những truy vấn đọc phức tạp có thể thuộc query service riêng.

### Repository implementation có thể dùng nhiều bảng

OrderRepository có thể đọc:

- Bản ghi Order.
- Các OrderLine.
- Các adjustment hoặc dữ liệu nội bộ khác thuộc Aggregate.
- Version để kiểm soát concurrency.

Khi lưu, implementation có thể cập nhật nhiều bảng trong cùng transaction. Application vẫn chỉ làm việc với Order.

    public Optional<Order> findById(OrderId id) {
        return orderJpaRepository.findById(id.value())
                .map(orderRow -> {
                    List<OrderLineRow> lineRows =
                            lineJpaRepository.findByOrderId(id.value());

                    return mapper.toDomain(orderRow, lineRows);
                });
    }

    public void save(Order order) {
        transactionTemplate.executeWithoutResult(status -> {
            orderJpaRepository.save(mapper.toRow(order));

            lineJpaRepository.replaceLines(
                    order.id().value(),
                    mapper.toLineRows(order.lines())
            );
        });
    }

Đây là phác thảo để minh họa. Implementation thật cần xử lý version, locking, mapping, cascade, xóa phần tử, domain event và lỗi transaction phù hợp. Điểm quan trọng là nhiều thao tác persistence có thể nằm sau một Repository của root.

## 6. Khi nào một Entity con thực sự cần Repository riêng?

Nếu một đối tượng có identity, điều đó chưa đủ. Nhưng cũng không nên áp dụng máy móc quy tắc "không bao giờ có Repository cho entity con" nếu mô hình nghiệp vụ thực tế cho thấy nó là Aggregate Root độc lập.

Hãy xem xét các dấu hiệu:

- Đối tượng có vòng đời nghiệp vụ độc lập.
- Nó có thể được tạo, thay đổi và kết thúc mà không cần tải Aggregate cha.
- Nó có invariant riêng cần được bảo vệ trong một transaction độc lập.
- Các use case thường xuyên truy cập nó độc lập.
- Nó có thể được tham chiếu từ các Aggregate khác bằng identity.
- Việc đưa nó vào Aggregate cha làm tăng contention hoặc khiến ranh giới nhất quán quá rộng.
- Chuyên gia nghiệp vụ xem nó là một khái niệm có trách nhiệm riêng.

Nếu các dấu hiệu này đúng, có thể đối tượng đó nên trở thành Aggregate Root riêng, thay vì entity con. Khi đó Repository riêng là hợp lý vì nó phục vụ một Aggregate mới.

### Ví dụ: OrderLine có thể vẫn là entity con

Một dòng hàng chỉ tồn tại trong phạm vi đơn hàng:

- Không thể được tạo nếu chưa có Order.
- Không thể chuyển sang đơn khác tùy ý.
- Thay đổi số lượng phải tuân theo trạng thái và chính sách của Order.
- Khi đơn bị hủy, dòng hàng không còn được xử lý như một giao dịch độc lập.

Trong trường hợp này, OrderLine là entity con và không cần OrderLineRepository.

### Ví dụ: Shipment có thể là Aggregate Root riêng

Sau khi đơn được xác nhận, hệ thống có thể tạo một Shipment có vòng đời riêng:

- Được phân công cho đơn vị vận chuyển.
- Có tracking number.
- Có trạng thái lấy hàng, đang vận chuyển, giao thành công hoặc thất bại.
- Có thể phát sinh nhiều lần cập nhật từ đối tác logistics.
- Có thể được truy vấn và cập nhật độc lập với Order.

Shipment có thể là Aggregate Root riêng và có ShipmentRepository. Order có thể lưu ShipmentId hoặc nhận sự kiện từ Shipping context để cập nhật phần thông tin cần thiết.

Việc tách này phải dựa trên invariant và vòng đời nghiệp vụ, không chỉ vì bảng shipment có nhiều cột.

## 7. Tránh nhầm Repository với truy vấn đọc Entity con

Một use case có thể cần hiển thị một dòng hàng hoặc thống kê các dòng hàng mà không cần tải toàn bộ Aggregate Order. Điều đó không nhất thiết đòi hỏi OrderLineRepository.

Có thể sử dụng query service hoặc read model:

    public interface OrderLineQueryService {
        Optional<OrderLineView> findLine(
                OrderId orderId,
                OrderLineId lineId
        );
    }

    public record OrderLineView(
            OrderId orderId,
            OrderLineId lineId,
            ProductId productId,
            int quantity,
            Money unitPrice
    ) {
    }

Query service trả về dữ liệu đọc, không trả entity mutable để application sửa rồi lưu độc lập. Nó có thể truy vấn trực tiếp bảng hoặc read model được tối ưu cho màn hình.

Phân biệt rõ:

| Nhu cầu | Cách tiếp cận phù hợp |
|---|---|
| Đổi số lượng một dòng hàng và bảo vệ invariant của Order | Tải Order qua OrderRepository, gọi hành vi root |
| Hiển thị thông tin một dòng hàng | Query service / read model |
| Báo cáo tổng hợp nhiều OrderLine | Query/reporting model |
| Cập nhật trạng thái Shipment có vòng đời riêng | ShipmentRepository nếu Shipment là Aggregate Root |
| Lưu một OrderLine bên trong Order | OrderRepository / Unit of Work |

Read model có thể có cấu trúc phẳng, denormalized hoặc tách theo màn hình. Nó không phải là một cách khác để ghi trực tiếp vào entity con.

## 8. Aggregate Root và transaction boundary

Một trong những lý do chính để dùng Repository theo Aggregate Root là bảo vệ các invariant cần nhất quán cùng nhau.

Ví dụ, khi thay đổi một dòng hàng, hệ thống có thể cần:

1. Xác nhận Order còn ở trạng thái cho phép chỉnh sửa.
2. Kiểm tra Product có thể được đặt.
3. Kiểm tra số lượng mới.
4. Cập nhật OrderLine.
5. Tính lại tổng tiền.
6. Áp dụng giới hạn đơn hàng.
7. Tạo Domain Event nếu nghiệp vụ yêu cầu.
8. Lưu toàn bộ thay đổi.

Nếu các bước thuộc cùng một Aggregate boundary, chúng cần được thực hiện trong một transaction phù hợp.

Repository của root cung cấp điểm truy cập để load và save Aggregate. Unit of Work hoặc transaction manager đảm bảo các thao tác persistence liên quan được commit hoặc rollback cùng nhau.

### Không có nghĩa một Aggregate phải nằm trong một bảng

Một Aggregate có thể được lưu qua nhiều bảng hoặc document. Ranh giới Aggregate là ranh giới mô hình và consistency, không phải sơ đồ bảng.

Ngược lại, nhiều bảng không tự động có nghĩa là nhiều Aggregate. Thiết kế persistence cần phục vụ Aggregate boundary thay vì quyết định Aggregate boundary dựa trên số lượng bảng.

## 9. Entity con và Aggregate khác nhau cần được tham chiếu ra sao?

Khi một Aggregate cần liên kết tới Aggregate khác, thường nên tham chiếu bằng identity của root thay vì giữ toàn bộ object graph mutable.

Ví dụ, Order có thể giữ CustomerId thay vì giữ một Customer entity đầy đủ:

    public final class Order {
        private final OrderId id;
        private final CustomerId customerId;
    }

Order không cần CustomerRepository để tải toàn bộ Customer chỉ vì cần biết khách hàng nào sở hữu đơn. Nếu một use case cần thông tin khách hàng, application có thể phối hợp các Repository hoặc query service theo nhu cầu.

Tương tự, Order có thể giữ ShipmentId sau khi Shipment được tạo. Order không nên tự sửa trực tiếp các trạng thái nội bộ của Shipment.

Điều này giúp các Aggregate giữ quyền sở hữu invariant của riêng mình và tránh một transaction vô tình mở rộng qua nhiều ranh giới.

## 10. Điều gì xảy ra nếu Aggregate quá lớn?

Không tạo Repository cho từng entity con không có nghĩa phải giữ một Aggregate khổng lồ. Nếu root có quá nhiều child entity hoặc mọi thay đổi nhỏ đều gây contention, cần xem lại Aggregate boundary.

Một Aggregate quá lớn có thể dẫn đến:

- Tải nhiều dữ liệu không cần thiết.
- Transaction kéo dài.
- Xung đột optimistic locking thường xuyên.
- Nhiều use case không liên quan phải chờ nhau.
- Khó kiểm thử và khó hiểu các invariant.
- Tăng chi phí lưu và cập nhật toàn bộ object graph.

Giải pháp là xem lại những invariant nào thực sự phải được bảo vệ đồng thời. Nếu một phần có vòng đời và consistency riêng, có thể tách thành Aggregate Root khác. Nếu chỉ cần đọc, có thể dùng projection/read model. Nếu cần phối hợp bất đồng bộ, có thể dùng Domain Event hoặc process manager.

Không nên tách Aggregate chỉ vì muốn tạo thêm Repository. Mục tiêu là xác định đúng ranh giới consistency.

## 11. Ví dụ: thiết kế Order và Shipment

Giả sử hệ thống thương mại điện tử có hai khái niệm:

- Order quản lý cam kết mua bán giữa khách hàng và doanh nghiệp.
- Shipment quản lý quá trình giao một lô hàng.

Trong giai đoạn đầu, hệ thống có thể lưu Order và OrderLine trong một Aggregate:

    OrderRepository
        |
        v
    Order
      +-- OrderLine
      +-- OrderLine
      +-- OrderLine

Sau khi Order được xác nhận, hệ thống tạo Shipment riêng:

    OrderRepository                 ShipmentRepository
        |                                    |
        v                                    v
      Order                              Shipment
        |                                    |
        +-- OrderLine                        +-- ShipmentItem
        +-- OrderLine                        +-- TrackingEvent

Order và Shipment có thể liên hệ bằng OrderId, ShipmentId và Domain Event. Các hành vi thay đổi OrderLine vẫn đi qua Order. Các cập nhật tracking đi qua Shipment.

Một luồng có thể là:

1. Order được xác nhận.
2. Order phát OrderConfirmed.
3. Fulfillment process nhận event và tạo Shipment.
4. ShipmentRepository lưu Shipment mới.
5. Đối tác vận chuyển gửi tracking update.
6. Shipping context nạp Shipment qua ShipmentRepository và gọi hành vi cập nhật trạng thái.
7. Shipping phát ShipmentDelivered khi giao thành công.
8. Order context nhận event và cập nhật phần trạng thái thực hiện đơn theo quy tắc của mình.

Không có ShipmentItemRepository chỉ vì ShipmentItem là entity con có ID. Nếu ShipmentItem phải được thay đổi để bảo vệ invariant của Shipment, thay đổi đi qua Shipment Root.

## 12. Các anti-pattern cần tránh

### Repository cho mỗi Entity

Tạo OrderRepository, OrderLineRepository, DiscountRepository và TaxLineRepository rồi cho application tự ghép chúng lại. Cách này khiến Aggregate boundary không còn là điểm kiểm soát.

### Generic repository cho mọi kiểu

Một GenericRepository<T> với save, delete, findById cho mọi entity có thể khuyến khích application lưu bất kỳ entity con nào độc lập. Generic repository không tự động sai trong mọi kiến trúc, nhưng nếu nó làm mất ngữ nghĩa Aggregate Root thì không phù hợp với mục tiêu DDD.

### Repository trả entity con để sửa trực tiếp

Query một child entity bằng ID rồi thay đổi và save riêng có thể bỏ qua root. Nếu cần chỉnh sửa, hãy nạp root và gọi hành vi.

### Root chỉ là lớp bao quanh collection

Nếu mọi quy tắc vẫn nằm ở application service và root chỉ cung cấp getLines(), addLine() không kiểm tra gì, Aggregate Root chưa thực sự bảo vệ invariant.

### Dùng Repository để truy vấn mọi báo cáo

Repository của Aggregate không nên trở thành công cụ báo cáo tùy ý. Các truy vấn đọc phức tạp có thể dùng query service hoặc read model.

### Tách Aggregate chỉ theo bảng

Một bảng riêng không tự động có nghĩa một Aggregate riêng. Hãy dựa trên invariant, vòng đời và consistency requirement.

### Lưu entity con bằng transaction riêng

Nếu child entity thuộc cùng Aggregate và thay đổi cần nhất quán với root, commit riêng có thể tạo trạng thái dở dang.

## 13. Cách tổ chức code gợi ý

Một cấu trúc package đơn giản có thể là:

    orders/
      domain/
        Order.java
        OrderLine.java
        OrderId.java
        OrderLineId.java
        OrderRepository.java

      application/
        ChangeOrderLineQuantityHandler.java
        AddOrderLineHandler.java
        GetOrderLineViewHandler.java

      infrastructure/
        JpaOrderRepository.java
        OrderJpaEntity.java
        OrderLineJpaEntity.java
        OrderMapper.java
        OrderLineQueryServiceSql.java

Trong cấu trúc này:

- OrderRepository là abstraction để truy cập Aggregate Order.
- OrderLine không có Repository riêng cho các hành vi ghi thuộc Order.
- OrderLineQueryService phục vụ nhu cầu đọc riêng nếu cần.
- JpaOrderRepository có thể sử dụng nhiều DAO hoặc Spring Data repository nội bộ.
- Application handler gọi root để thực hiện thay đổi.
- Infrastructure quyết định cách lưu Order và OrderLine trong database.

Một dự án có thể đặt Repository interface trong Domain hoặc Application tùy ý nghĩa abstraction. Điều quan trọng là interface phục vụ Aggregate Root và implementation không làm lộ chi tiết persistence ra domain.

## 14. Kiểm thử ranh giới Repository và Aggregate

Kiểm thử nên xác nhận application không thể thay đổi child entity bằng cách bỏ qua root.

Một số kịch bản hữu ích:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Tải Order bằng OrderRepository | Aggregate root cùng các child cần thiết được khôi phục |
| Thay đổi OrderLine qua Order | Root kiểm tra trạng thái và invariant |
| Thay đổi OrderLine khi Order đã xác nhận | Bị từ chối theo chính sách |
| Gọi use case với OrderLineId không thuộc Order | Không tìm thấy child trong root và trả lỗi phù hợp |
| Lưu Order sau khi thay đổi child | Root và child được lưu trong cùng unit of work |
| Đọc một dòng hàng để hiển thị | Query service trả read model, không tạo đường ghi độc lập |
| Shipment thay đổi trạng thái | ShipmentRepository nạp Shipment root, hành vi root kiểm tra chuyển trạng thái |

Ngoài unit test cho Aggregate, nên có repository integration test để kiểm tra mapping nhiều bảng, transaction rollback và optimistic concurrency. Không cần mock mọi chi tiết ORM trong domain test; domain test nên tập trung vào invariant và hành vi.

## 15. Checklist quyết định có cần Repository riêng không?

Trước khi tạo Repository cho một Entity, hãy hỏi:

- Đối tượng này có phải Aggregate Root không?
- Nó có vòng đời nghiệp vụ độc lập không?
- Nó có invariant cần bảo vệ trong một transaction riêng không?
- Các use case có cần nạp và thay đổi nó độc lập không?
- Nếu nó thuộc Aggregate khác, hành vi có cần đi qua root hiện tại không?
- ID riêng chỉ phục vụ nhận diện nội bộ hay thực sự cần quyền truy cập độc lập?
- Nhu cầu hiện tại là ghi nghiệp vụ hay chỉ đọc dữ liệu?
- Có thể dùng query service/read model cho nhu cầu đọc không?
- Repository riêng có làm application biết thêm về cấu trúc bảng không?
- Tách Aggregate có giảm đúng consistency boundary hay chỉ tăng số abstraction?

Nếu đối tượng là entity con và mọi thay đổi của nó phải tuân theo invariant của root, không tạo Repository riêng. Hãy dùng Repository của root để nạp Aggregate và gọi hành vi thông qua root.

Nếu đối tượng thực sự có vòng đời và invariant độc lập, hãy xem xét mô hình hóa nó thành Aggregate Root riêng. Khi đó Repository riêng có cơ sở từ domain model.

## 16. Kết luận

Repository trong DDD phục vụ Aggregate Root, không phải một bản sao CRUD cho mọi Entity hoặc mọi bảng. Entity con có thể có identity riêng và hành vi riêng, nhưng nếu nó nằm trong Aggregate thì quyền truy cập và thay đổi vẫn cần đi qua root để bảo vệ invariant và transaction boundary.

Khi cần đọc dữ liệu con cho màn hình hoặc báo cáo, query service/read model có thể đáp ứng mà không tạo một Repository ghi độc lập. Khi một đối tượng có vòng đời và consistency riêng, hãy xem xét tách nó thành Aggregate Root và cấp Repository tương ứng.

Thiết kế này giúp application làm việc theo ngôn ngữ nghiệp vụ, giữ các đường ghi tập trung ở Aggregate Root và tránh biến persistence schema thành cấu trúc điều khiển domain model.
