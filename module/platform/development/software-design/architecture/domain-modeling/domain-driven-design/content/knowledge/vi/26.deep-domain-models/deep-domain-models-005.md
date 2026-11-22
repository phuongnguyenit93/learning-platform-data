# Tái cấu trúc tên gọi, quan hệ và ranh giới theo hiểu biết mới

Một mô hình miền tốt phản ánh cách doanh nghiệp thực sự hiểu và vận hành công việc. Khi đội phát triển mới bắt đầu một dự án, hiểu biết thường chưa đầy đủ: một từ có thể được dùng cho nhiều khái niệm, một quy trình có thể bị xem như một trạng thái đơn giản, hoặc nhiều đối tượng có vòng đời khác nhau bị gom vào cùng một Entity. Khi trao đổi với chuyên gia nghiệp vụ và quan sát thêm các trường hợp thực tế, đội ngũ có thể phát hiện mô hình ban đầu không còn diễn đạt đúng miền.

Trong Domain-Driven Design (DDD), việc thay đổi mô hình theo hiểu biết mới là một phần của quá trình xây dựng mô hình sâu (deep domain model). Tái cấu trúc không chỉ là đổi tên class hay sắp xếp lại package. Nó có thể đòi hỏi phân biệt các khái niệm từng bị gọi chung một tên, thay đổi quan hệ giữa Entity và Value Object, tách hoặc gộp Aggregate, điều chỉnh ranh giới Bounded Context và chuyển đổi dữ liệu đang tồn tại.

Bài học này trình bày cách nhận ra mô hình không còn phù hợp, cách dùng ngôn ngữ miền để đặt lại tên, cách thay đổi quan hệ và ranh giới dựa trên invariant, và cách triển khai chuyển đổi an toàn trong code, database và hợp đồng tích hợp. Ví dụ xuyên suốt bắt đầu từ một mô hình Order đơn giản rồi được làm rõ thành các khái niệm Sales Order, Fulfillment Order, Invoice, Buyer và Delivery Recipient.

## 1. Mô hình miền phải tiến hóa cùng hiểu biết

### 1.1. Mô hình ban đầu luôn là giả thuyết

Khi bắt đầu khám phá một miền, đội phát triển thường có một mô hình tạm thời. Mô hình đó giúp trao đổi và thử nghiệm, nhưng chưa chắc đã phản ánh đúng mọi quy tắc.

Ví dụ ban đầu, nhóm bán hàng nói: “Khách đặt đơn, đơn được giao, rồi xuất hóa đơn”. Đội phát triển tạo một Entity Order với các thuộc tính:

- Customer.
- OrderLines.
- Shipment.
- Invoice.
- Status.

Mô hình có thể chạy được, nhưng nó đang giả định rằng người mua, người nhận hàng và người nhận hóa đơn luôn là một người; một đơn chỉ có một shipment; hóa đơn luôn được tạo sau khi giao hàng; và toàn bộ các đối tượng có thể thay đổi cùng một vòng đời.

Sau các buổi trao đổi, nhóm nghiệp vụ giải thích:

- Người mua có thể đặt hàng để gửi cho người khác.
- Một đơn có thể được chia thành nhiều đợt giao từ các kho khác nhau.
- Hóa đơn được phát hành theo quy tắc kế toán riêng.
- Việc giao hàng do bộ phận Fulfillment quản lý, không phải bộ phận Sales.
- Một shipment có thể thất bại hoặc được giao lại mà đơn bán vẫn tồn tại.

Những thông tin mới làm thay đổi ý nghĩa của mô hình. Giữ nguyên Order và chỉ thêm nhiều field sẽ khiến class ngày càng phức tạp mà vẫn không thể hiện rõ quyền sở hữu và vòng đời.

### 1.2. Deep domain model không phải mô hình phức tạp hơn

Mô hình sâu là mô hình thể hiện được những quy tắc và phân biệt quan trọng của miền. Nó có thể làm cho một số khái niệm trở nên rõ ràng hơn và loại bỏ những cấu trúc không cần thiết.

Một mô hình tốt giúp trả lời:

- Đối tượng này đại diện cho điều gì trong nghiệp vụ?
- Ai có quyền thay đổi nó?
- Nó tồn tại qua những trạng thái nào?
- Quy tắc nào phải luôn đúng?
- Nó có cùng vòng đời với đối tượng đang tham chiếu không?
- Từ ngữ nào giúp chuyên gia và lập trình viên hiểu cùng một ý?

Mục tiêu không phải tạo thật nhiều class hoặc abstraction. Mục tiêu là mô hình hóa đúng những khác biệt có ý nghĩa.

### 1.3. Refactoring mô hình là hoạt động học hỏi liên tục

Một lần tái cấu trúc có thể bắt đầu từ một ví dụ nghiệp vụ mới, một ngoại lệ mà mô hình cũ không giải thích được hoặc một cuộc thảo luận cho thấy hai nhóm đang dùng cùng từ với hai ý nghĩa khác nhau.

Chu trình thường là:

1. Thu thập ví dụ và cách chuyên gia mô tả công việc.
2. Nêu giả thuyết về khái niệm và quy tắc.
3. Kiểm tra giả thuyết bằng các tình huống thực tế.
4. Điều chỉnh tên gọi, quan hệ hoặc ranh giới.
5. Cập nhật code, dữ liệu và hợp đồng liên quan.
6. Kiểm chứng rằng mô hình mới diễn đạt đúng các quy tắc đã khám phá.

Mỗi thay đổi nên dựa trên bằng chứng nghiệp vụ, không chỉ dựa trên sở thích thiết kế của lập trình viên.

## 2. Dấu hiệu cho thấy mô hình hiện tại cần được tái cấu trúc

### 2.1. Một tên gọi đang đại diện cho nhiều khái niệm

Nếu cùng một từ được dùng trong nhiều cuộc hội thoại nhưng mỗi nhóm hiểu khác nhau, mô hình có thể đang gộp các khái niệm riêng.

Ví dụ từ Customer có thể chỉ:

- Người mua và chịu trách nhiệm đặt hàng.
- Người nhận kiện hàng.
- Đơn vị nhận hóa đơn.
- Tổ chức ký hợp đồng.
- Người thanh toán.

Trong trường hợp đơn giản, tất cả vai trò có thể là cùng một người. Nhưng khi nghiệp vụ cho phép các vai trò khác nhau, một trường customerId duy nhất không còn đủ nghĩa.

### 2.2. Một trạng thái đang che giấu nhiều vòng đời

Một field status có thể bị dùng để mô tả đồng thời đơn bán, giao hàng và hóa đơn:

~~~java
enum OrderStatus {
    CREATED,
    CONFIRMED,
    SHIPPED,
    DELIVERED,
    INVOICED,
    CANCELLED
}
~~~

Các trạng thái này không nhất thiết thuộc cùng một state machine. Đơn có thể đã xác nhận nhưng chưa được giao; shipment có thể đã giao trong khi hóa đơn chưa phát hành; hóa đơn có thể đã phát hành nhưng sau đó được điều chỉnh.

Nếu mọi tiến trình đều cập nhật cùng một OrderStatus, các chuyển đổi dễ xung đột và không thể diễn đạt các trạng thái song song.

### 2.3. Một Entity có quá nhiều lý do để thay đổi

Nếu Order phải thay đổi khi chính sách bán hàng, quy tắc kho, vận chuyển, kế toán và thanh toán đổi, có thể nó đang ôm trách nhiệm của nhiều mô hình.

Hãy xem xét:

- Quy tắc có cùng một chuyên gia nghiệp vụ sở hữu không?
- Các dữ liệu có thay đổi cùng nhau không?
- Một thay đổi ở bộ phận này có bắt buộc làm thay đổi trạng thái của bộ phận kia không?
- Có thể mô tả các khái niệm như các Aggregate độc lập và phối hợp bằng sự kiện không?

Nhiều lý do thay đổi là tín hiệu cần xem lại ranh giới, nhưng chưa đủ để tự động tách class hoặc Aggregate.

### 2.4. Code thường xuyên phải giải thích bằng comment

Các comment như “customer ở đây thực ra là người nhận hóa đơn”, “shipmentStatus chỉ dùng cho đợt giao cuối” hoặc “nếu đơn có nhiều kho thì field này có ý nghĩa khác” thường cho thấy tên gọi và cấu trúc không còn phản ánh ngôn ngữ miền.

Một mô hình tốt nên làm cho ý nghĩa xuất hiện ngay trong tên kiểu, quan hệ và hành vi.

### 2.5. Quy tắc chỉ có thể kiểm tra ở nhiều nơi

Nếu cùng một điều kiện được kiểm tra ở controller, service, repository và batch job, có thể mô hình chưa xác định rõ ai sở hữu quyết định.

Ví dụ, quy tắc “chỉ đơn đã xác nhận mới được đưa vào xử lý giao hàng” nên có một chủ thể chịu trách nhiệm phát hành hoặc tiếp nhận hành vi phù hợp, thay vì mỗi adapter tự diễn giải trạng thái.

## 3. Khám phá lại ngôn ngữ và đặt tên chính xác

### 3.1. Bắt đầu từ từ ngữ chuyên gia sử dụng

Khi một từ có vẻ mơ hồ, hãy yêu cầu ví dụ cụ thể:

- “Người đặt hàng” có luôn là “người nhận hàng” không?
- “Đơn hàng đã hoàn tất” nghĩa là đã giao, đã thanh toán hay đã xuất hóa đơn?
- “Hủy đơn” có hủy shipment và hóa đơn đã phát hành không?
- “Giao hàng” là một lần giao hay toàn bộ quá trình thực hiện đơn?

Ví dụ thực tế giúp phân biệt ý nghĩa tốt hơn việc hỏi một định nghĩa trừu tượng.

### 3.2. Đặt tên theo vai trò và ngữ cảnh

Thay vì một kiểu Customer dùng ở mọi nơi, có thể cần:

- Buyer: người hoặc tổ chức thực hiện việc mua.
- DeliveryRecipient: người nhận hàng.
- BillToParty: chủ thể nhận hóa đơn.
- AccountHolder: chủ thể sở hữu tài khoản thanh toán.

Các tên này không mặc định là bốn Entity riêng. Một số có thể là vai trò của cùng một Party, một số là snapshot Value Object, hoặc ID tham chiếu đến Aggregate trong context khác. Quyết định phụ thuộc vào danh tính, vòng đời và quy tắc nghiệp vụ.

### 3.3. Dùng động từ để làm rõ hành vi

Tên hành vi cũng cần phản ánh điều xảy ra:

- confirmSalesOrder() thay cho process().
- assignDelivery() thay cho updateStatus().
- issueInvoice() thay cho completeOrder().
- recordDeliveryAttempt() thay cho setDelivered().

Một động từ rõ nghĩa giúp người đọc biết quyết định nào đang được thực hiện và tránh method tổng quát thay đổi nhiều trạng thái không liên quan.

### 3.4. Ubiquitous Language phải nhất quán trong code và trao đổi

Khi nhóm thống nhất dùng SalesOrder, tên đó nên xuất hiện trong:

- Tài liệu nghiệp vụ.
- Entity và Aggregate Root.
- Repository.
- Domain Event.
- API contract khi công bố khái niệm này.
- Test case.
- Log và metric nếu cần truy vết.

Không nhất thiết mọi tên nội bộ phải lộ ra ngoài API. Nhưng các lớp chuyển đổi phải có mapping rõ để không làm mất ý nghĩa.

### 3.5. Không đổi tên chỉ để chạy theo xu hướng

Một tên mới không tự làm mô hình sâu hơn. Nếu Order đã có một định nghĩa rõ ràng, một vòng đời duy nhất và được các bên hiểu thống nhất, đổi thành SalesOrderAggregateRoot có thể chỉ làm code dài hơn.

Hãy đổi tên khi có bằng chứng rằng tên cũ mơ hồ, sai ngữ nghĩa hoặc che giấu một phân biệt nghiệp vụ quan trọng.

## 4. Ví dụ khám phá lại mô hình Order

### 4.1. Mô hình ban đầu

Giả sử ứng dụng đang dùng một Aggregate:

~~~java
public class Order {

    private OrderId id;
    private Customer customer;
    private List<OrderLine> lines;
    private Shipment shipment;
    private Invoice invoice;
    private OrderStatus status;

    public void confirm() {
        // kiểm tra điều kiện bán hàng
        // giữ hàng
        // tạo shipment
        // phát hành invoice
        status = OrderStatus.CONFIRMED;
    }

    public void markDelivered() {
        shipment.markDelivered();
        status = OrderStatus.DELIVERED;
    }
}
~~~

Mô hình này có một số giả định ẩn:

- Customer chỉ có một vai trò.
- Shipment là một đối tượng duy nhất thuộc Order.
- Invoice nằm trong cùng vòng đời của Order.
- Xác nhận đơn đồng thời thực hiện nhiều bước ở các bộ phận.
- OrderStatus mô tả mọi tiến trình.

Khi nghiệp vụ mở rộng, các giả định này không còn đúng.

### 4.2. Thu thập ví dụ phản chứng

Chuyên gia nghiệp vụ đưa ra các tình huống:

| Tình huống | Mô hình cũ gặp khó khăn |
|---|---|
| Người mua đặt quà cho người khác | Không phân biệt Buyer và Delivery Recipient |
| Đơn có hàng ở hai kho | Một Shipment không biểu diễn được nhiều đợt giao |
| Giao hàng thất bại rồi giao lại | Không thể lưu lịch sử nhiều lần giao thử |
| Hóa đơn được phát hành sau khi giao một phần | Invoice không cùng trạng thái với Order |
| Hóa đơn được điều chỉnh | Không nên sửa trực tiếp trạng thái đơn bán |
| Một đơn bị hủy sau khi đã giữ hàng | Cần phối hợp giải phóng hàng và cập nhật đơn |

Những tình huống này chứng minh mô hình cần phân biệt các khái niệm và vòng đời.

### 4.3. Mô hình sau khi hiểu rõ hơn

Có thể mô hình hóa thành:

~~~text
Sales Context
    SalesOrder (Aggregate Root)
        SalesOrderId
        BuyerId
        DeliveryAddressSnapshot
        BillToPartySnapshot
        SalesOrderLine[]
        SalesOrderStatus

Fulfillment Context
    FulfillmentOrder (Aggregate Root)
        FulfillmentOrderId
        SourceSalesOrderId
        FulfillmentLine[]
        DeliveryAssignment[]
        FulfillmentStatus

Billing Context
    Invoice (Aggregate Root)
        InvoiceId
        SourceSalesOrderId
        BillToParty
        InvoiceLine[]
        InvoiceStatus
~~~

SalesOrder sở hữu quyết định thương mại. FulfillmentOrder sở hữu tiến trình thực hiện giao hàng. Invoice sở hữu chứng từ kế toán. Các Aggregate tham chiếu nguồn gốc bằng ID theo hợp đồng, không chia sẻ trực tiếp object graph nội bộ.

### 4.4. Mô hình mới không nhất thiết làm quy trình đồng bộ

Sau khi xác nhận SalesOrder, Sales có thể phát SalesOrderConfirmed. Fulfillment nhận sự kiện và tạo một hoặc nhiều FulfillmentOrder. Billing có thể nhận sự kiện hoặc một tín hiệu nghiệp vụ phù hợp để tạo hóa đơn theo chính sách.

Nếu một bước thất bại, quy trình điều phối xử lý retry, trạng thái chờ hoặc hành động bù trừ. Không nên giữ một transaction database xuyên qua Sales, Fulfillment và Billing chỉ để mô hình trông như một object duy nhất.

## 5. Tái cấu trúc quan hệ giữa Entity và Value Object

### 5.1. Phân biệt danh tính với giá trị

Một Entity được nhận diện bằng ID. Một Value Object được xác định bằng giá trị thuộc tính và thường bất biến.

Ví dụ:

- SalesOrder là Entity/Aggregate Root.
- SalesOrderLine có thể là Entity nội bộ nếu cần danh tính riêng hoặc vòng đời riêng trong Aggregate.
- Money là Value Object.
- DeliveryAddressSnapshot là Value Object nếu chỉ lưu thông tin địa chỉ tại thời điểm đặt.
- BuyerId là Value Object biểu diễn định danh tham chiếu.

Nếu một đối tượng chỉ là tập hợp dữ liệu không có vòng đời độc lập, đừng tạo Entity chỉ vì nó có nhiều field.

### 5.2. Chuyển một thuộc tính thành Value Object khi ý nghĩa trở nên quan trọng

Mô hình ban đầu có thể lưu:

~~~java
private String currency;
private BigDecimal total;
~~~

Khi quy tắc tiền tệ được khám phá rõ hơn, có thể thay bằng:

~~~java
public record Money(
    BigDecimal amount,
    Currency currency
) {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);
    }
}
~~~

Money giúp gom các quy tắc về currency, so sánh, cộng trừ và làm tròn vào một kiểu có ý nghĩa. Việc chuyển đổi phải rà soát các phép tính cũ để tránh thay đổi semantics ngoài dự kiến.

### 5.3. Chuyển Entity thành Value Object hoặc ngược lại

Một khái niệm ban đầu có thể bị mô hình hóa sai cấp độ.

Ví dụ DeliveryAddress ban đầu được tạo thành Entity có AddressId. Sau khi tìm hiểu, nhóm thấy địa chỉ trong đơn chỉ là snapshot tại thời điểm đặt; thay đổi địa chỉ sổ địa chỉ của khách không được làm thay đổi đơn cũ. Trong trường hợp đó, địa chỉ snapshot có thể là Value Object nằm trong SalesOrder.

Ngược lại, nếu doanh nghiệp quản lý một địa điểm giao nhận có danh tính, lịch sử, trạng thái hoạt động và nhiều đơn tham chiếu, Warehouse hoặc DeliveryLocation có thể là Entity hoặc Aggregate riêng.

Câu hỏi quyết định là danh tính và vòng đời nghiệp vụ, không phải số lượng field.

### 5.4. Dùng snapshot khi cần bảo toàn ý nghĩa lịch sử

Một SalesOrderLine có thể lưu:

~~~java
public record ProductSnapshot(
    ProductId productId,
    String productName,
    String sku,
    Money unitPrice
) {
}
~~~

Snapshot giữ tên, mã hàng và đơn giá tại thời điểm đặt. Nó giúp lịch sử đơn không thay đổi khi Catalog cập nhật tên hoặc giá hiện tại.

Snapshot không có nghĩa Order sở hữu Product Catalog. Nó chỉ lưu các dữ liệu cần thiết để bảo toàn giao dịch.

## 6. Tái cấu trúc quan hệ giữa các đối tượng

### 6.1. Quan hệ trong code không đồng nghĩa với quyền sở hữu

Một field object reference có thể khiến người đọc nghĩ đối tượng này sở hữu đối tượng kia:

~~~java
private Customer customer;
~~~

Nhưng quan hệ nghiệp vụ có thể chỉ là tham chiếu. Nếu Customer thuộc Customer Context, SalesOrder không nên sửa trực tiếp trạng thái Customer thông qua reference đó.

Có thể dùng:

~~~java
private BuyerId buyerId;
~~~

Khi cần tên hoặc thông tin hiển thị, query service lấy dữ liệu qua API hoặc read model phù hợp.

### 6.2. Phân biệt association, ownership và lifecycle

Khi xem một quan hệ, hãy hỏi:

- Hai đối tượng chỉ cần biết đến nhau hay một đối tượng sở hữu vòng đời của đối tượng kia?
- Xóa đối tượng cha có làm đối tượng con mất ý nghĩa không?
- Đối tượng con có được truy cập hoặc thay đổi độc lập không?
- Quy tắc nào cần được bảo đảm nguyên tử?
- Quan hệ có thể là một-nhiều hoặc nhiều-nhiều theo nghiệp vụ không?

Ví dụ SalesOrder sở hữu các dòng hàng của chính đơn. Khi đơn bị xóa theo chính sách lưu trữ, các dòng hàng không còn ý nghĩa độc lập. Ngược lại, Product Catalog có vòng đời riêng và không bị xóa khi một đơn hàng bị hủy.

### 6.3. Cardinality phải xuất phát từ nghiệp vụ

Không giả định mọi quan hệ là one-to-one vì mô hình ban đầu chỉ có một field.

Ví dụ:
- Một SalesOrder có thể có nhiều FulfillmentOrder.
- Một FulfillmentOrder có thể có nhiều DeliveryAttempt.
- Một SalesOrder có thể có nhiều Invoice hoặc CreditNote tùy chính sách.
- Một Buyer có thể đặt nhiều SalesOrder.

Cardinality cần được xác nhận qua tình huống thực tế, không chỉ dựa trên dữ liệu mẫu hiện tại.

### 6.4. Dùng ID để tham chiếu giữa Aggregate

Một Aggregate thường tham chiếu Aggregate khác bằng ID. Điều này giúp giữ ranh giới thay đổi và tránh tải toàn bộ object graph.

~~~java
public final class SalesOrder {

    private final SalesOrderId id;
    private final BuyerId buyerId;

    // Các thành phần thuộc SalesOrder Aggregate

    public SalesOrderId id() {
        return id;
    }

    public BuyerId buyerId() {
        return buyerId;
    }
}
~~~

Nếu cần thông tin Buyer để hiển thị, application/query layer lấy thông tin riêng. Hành vi của SalesOrder không nên gọi trực tiếp repository của Buyer để tự điều phối nhiều Aggregate.

## 7. Tái xác định Aggregate boundary theo invariant

### 7.1. Aggregate boundary được quyết định bởi consistency rule

Aggregate là ranh giới nhất quán. Aggregate Root bảo vệ invariant của các thành phần bên trong.

Ví dụ SalesOrder có thể bảo vệ:

- Chỉ đơn ở trạng thái Draft mới được sửa dòng hàng.
- Số lượng mỗi dòng hàng phải dương.
- Tổng tiền được tính từ các dòng và chính sách giá đã chốt.
- Chỉ đơn hợp lệ mới được xác nhận.
- Sau khi xác nhận, các thuộc tính thương mại quan trọng không được sửa tùy tiện.

Các dòng hàng thuộc cùng Aggregate nếu cần thay đổi cùng SalesOrder để giữ những invariant này.

### 7.2. Không gom đối tượng chỉ vì chúng có quan hệ

Shipment, Invoice và Payment có thể tham chiếu SalesOrder nhưng có vòng đời, trạng thái và chuyên gia nghiệp vụ sở hữu riêng. Chúng không nhất thiết phải nằm trong SalesOrder Aggregate.

Một Aggregate lớn có thể buộc hệ thống tải và khóa nhiều dữ liệu cho một thay đổi nhỏ. Nó cũng làm tăng xung đột cập nhật giữa các thao tác độc lập.

### 7.3. Không tách Aggregate chỉ vì class quá dài

Nếu một invariant phải được bảo vệ đồng bộ giữa các đối tượng, tách chúng ra có thể làm quy tắc trở nên khó bảo đảm.

Ví dụ, nếu SalesOrder cần tính tổng tiền từ toàn bộ OrderLine trước khi xác nhận, việc đưa OrderLine sang Aggregate độc lập sẽ tạo bài toán phối hợp mới. Cần có lý do nghiệp vụ rõ và một chiến lược nhất quán phù hợp trước khi tách.

### 7.4. Dấu hiệu cần xem lại boundary

- Aggregate thường xuyên tải collection rất lớn.
- Nhiều use case cập nhật các phần độc lập nhưng liên tục xung đột version.
- Các đối tượng con có vòng đời và quy tắc riêng.
- Một thay đổi nghiệp vụ ở context khác thường xuyên buộc Aggregate này thay đổi.
- Có thể xác định invariant riêng cho từng nhóm dữ liệu.
- Việc phối hợp giữa các nhóm có thể chấp nhận eventual consistency.

Đây là dấu hiệu để điều tra, không phải quy tắc tự động tách.

### 7.5. Khi nào nên gộp lại các Aggregate đã tách?

Việc khám phá thêm cũng có thể cho thấy hai Aggregate trước đây được tách riêng thực ra phải bảo vệ cùng một invariant và luôn thay đổi như một đơn vị nghiệp vụ.

Ví dụ, nhóm từng tách Order và OrderLine thành hai Aggregate để dễ cập nhật từng dòng. Sau khi làm rõ quy tắc, chuyên gia xác nhận tổng tiền và trạng thái xác nhận của đơn phải được tính từ toàn bộ dòng hàng trong cùng một quyết định; một dòng không thể được thêm hoặc xóa độc lập sau khi đơn xác nhận. Nếu mọi thao tác hợp lệ đều cần tải và phối hợp cả hai Aggregate, việc tách có thể tạo ra độ phức tạp không cần thiết.

Có thể cân nhắc gộp khi:

- Invariant bắt buộc phải được bảo đảm nguyên tử giữa hai nhóm dữ liệu.
- Hai nhóm có cùng chủ sở hữu quyết định và vòng đời gắn chặt với nhau.
- Các thao tác gần như luôn phải tải và cập nhật cả hai.
- Chi phí điều phối và xử lý trạng thái trung gian lớn hơn lợi ích của việc tách.

Trước khi gộp, kiểm tra kích thước dữ liệu, tần suất cập nhật và mức độ tranh chấp. Gộp Aggregate không có nghĩa phải gộp mọi bảng hoặc mọi Bounded Context có liên quan.

## 8. Tái cấu trúc Bounded Context và Context Map

### 8.1. Khi nào một khái niệm cần context riêng?

Nếu một nhóm nghiệp vụ có ngôn ngữ, mô hình và quy tắc riêng, nó có thể cần Bounded Context riêng. Ví dụ Order trong Sales và Order trong Fulfillment không nhất thiết là cùng một model.

Sales tập trung vào cam kết thương mại với người mua. Fulfillment tập trung vào việc lấy hàng, đóng gói và giao. Billing tập trung vào chứng từ và nghĩa vụ thanh toán.

Một tên giống nhau bên ngoài không có nghĩa phải dùng chung class bên trong.

### 8.2. Context Map mô tả quan hệ giữa các mô hình

Một Context Map có thể mô tả:

~~~text
Sales Context
    |
    | SalesOrderConfirmed
    v
Fulfillment Context

Sales Context
    |
    | SalesOrderConfirmed / Billing instruction
    v
Billing Context

Fulfillment Context
    |
    | DeliveryCompleted
    v
Sales Context
~~~

Sơ đồ thể hiện hướng trao đổi thông tin, không có nghĩa các context dùng chung Entity hoặc database.

### 8.3. Anti-Corruption Layer bảo vệ ngôn ngữ nội bộ

Khi một context nhận dữ liệu từ context khác hoặc đối tác, ACL chuyển đổi hợp đồng bên ngoài sang mô hình nội bộ.

Ví dụ Fulfillment nhận SalesOrderConfirmed và tạo FulfillmentOrder. Nó có thể chuyển SalesOrderId thành SourceSalesOrderId trong mô hình của mình. Các kiểu dữ liệu và quy tắc của Sales không cần được import trực tiếp vào Domain Model của Fulfillment.

### 8.4. Chọn quan hệ tích hợp theo thực tế

Tùy mức độ phụ thuộc và quyền lực giữa các nhóm, có thể dùng:
- Customer/Supplier.
- Conformist.
- Anti-Corruption Layer.
- Published Language.
- Open Host Service.
- Shared Kernel khi có phần mô hình thực sự cần chia sẻ và được quản lý chung.

Không chọn pattern chỉ vì tên nghe phù hợp. Hãy xác định ai kiểm soát hợp đồng, ai chịu chi phí thay đổi và consumer cần bảo vệ mô hình của mình đến mức nào.

### 8.5. Khi nào nên xem xét gộp Bounded Context?

Một ranh giới context có thể được tạo ra quá sớm hoặc vì lý do tổ chức kỹ thuật. Sau khi hiểu miền sâu hơn, có thể thấy hai context dùng cùng ngôn ngữ, cùng mô hình và cùng nhóm chịu trách nhiệm cho các quyết định; lớp chuyển đổi giữa chúng chỉ làm tăng chi phí mà không bảo vệ một khác biệt nghiệp vụ thực sự.

Khi đó, có thể xem xét hợp nhất mô hình hoặc tổ chức lại context. Tuy nhiên, không nên gộp chỉ vì hai hệ thống dùng chung một Entity hoặc một database. Hãy kiểm tra:

- Các thuật ngữ có cùng ý nghĩa trong mọi use case không?
- Các quy tắc và thay đổi có cùng chủ sở hữu không?
- Có cần giữ hai state machine và chính sách khác nhau không?
- Việc hợp nhất có làm một nhóm phải chịu trách nhiệm cho miền mà họ không kiểm soát không?
- Hợp đồng tích hợp hiện tại có đang bảo vệ một khác biệt cần thiết không?

Nếu hai nhóm thực sự có ngôn ngữ hoặc quyền sở hữu khác nhau, giữ Bounded Context riêng và cải thiện hợp đồng thường phù hợp hơn. Nếu hợp nhất, cần có kế hoạch chuyển dữ liệu, API, event và trách nhiệm vận hành như một thay đổi kiến trúc có kiểm soát.

## 9. Quy trình tái cấu trúc mô hình theo hiểu biết mới

### 9.1. Bước 1 — ghi nhận ví dụ và điểm chưa rõ

Thu thập:
- Từ chuyên gia thường dùng.
- Ví dụ bình thường và ngoại lệ.
- Các quyết định nghiệp vụ.
- Ai chịu trách nhiệm cho từng hành động.
- Những dữ liệu cần giữ lại để giải thích lịch sử.

Ghi lại câu hỏi chưa có lời giải. Không biến giả định của đội phát triển thành quy tắc chính thức khi chưa được xác nhận.

### 9.2. Bước 2 — tạo mô hình hiện tại và mô hình đề xuất

Mô tả rõ:
- Khái niệm hiện tại.
- Vấn đề hoặc mâu thuẫn.
- Hiểu biết mới.
- Khái niệm mới.
- Quan hệ và invariant bị ảnh hưởng.

Có thể dùng bảng:

| Hiện tại | Hiểu biết mới | Thay đổi đề xuất |
|---|---|---|
| Customer | Người mua, người nhận và người nhận hóa đơn có thể khác nhau | Buyer, DeliveryRecipient, BillToParty |
| Order | Bán hàng và giao hàng có vòng đời riêng | SalesOrder và FulfillmentOrder |
| Shipment đơn | Một đơn có thể chia nhiều kho | Một-nhiều FulfillmentOrder |
| OrderStatus chung | Trạng thái giao và hóa đơn độc lập | Các state machine riêng |
| Invoice nằm trong Order | Hóa đơn có quy tắc kế toán riêng | Invoice Aggregate |

### 9.3. Bước 3 — xác định invariant và ownership

Trước khi sửa code, trả lời:
- Aggregate nào sở hữu quyết định?
- Ai có quyền tạo hoặc đổi trạng thái?
- Dữ liệu nào phải commit cùng nhau?
- Dữ liệu nào chỉ cần tham chiếu?
- Có cần Domain Event hoặc Process Manager để phối hợp không?

Đây là bước tránh tách class cơ học mà không cải thiện mô hình.

### 9.4. Bước 4 — thống nhất từ ngữ với chuyên gia

Đưa tên và ví dụ mới trở lại buổi trao đổi. Hỏi chuyên gia xem Buyer, DeliveryRecipient và BillToParty có phản ánh đúng vai trò không; FulfillmentOrder có đúng là đơn vị công việc mà bộ phận kho sở hữu không.

Nếu chuyên gia vẫn dùng cùng một từ cho hai nghĩa, có thể cần giữ từ đó trong ngữ cảnh cụ thể hoặc chọn một thuật ngữ khác. Đừng áp đặt từ kỹ thuật chỉ vì code dễ đặt tên.

### 9.5. Bước 5 — thay đổi mô hình nhỏ và có kiểm chứng

Có thể chia thành các thay đổi:
1. Thêm kiểu và tên mới.
2. Chuyển một use case sang mô hình mới.
3. Thêm adapter hoặc mapping.
4. Chuyển dữ liệu.
5. Chuyển event/API consumer.
6. Loại bỏ cấu trúc cũ khi không còn người dùng.

Không nhất thiết phải đổi toàn bộ hệ thống trong một commit hoặc một lần triển khai.

## 10. Tái cấu trúc code mà vẫn giữ hành vi đúng

### 10.1. Đổi tên theo ngữ nghĩa

IDE refactoring hỗ trợ rename class, field, method và package. Tuy nhiên, cần kiểm tra các điểm không được IDE nhận diện đầy đủ:

- Tên bảng và cột.
- JSON property.
- Tên field trong event.
- Query JPQL/SQL dạng chuỗi.
- Reflection và framework mapping.
- Log, metric và dashboard.
- Script batch hoặc dữ liệu cấu hình.

Đổi tên trong code không tự động đổi hợp đồng hoặc schema an toàn.

### 10.2. Tách trách nhiệm trước khi di chuyển logic

Nếu Order.confirm() đang giữ hàng, tạo shipment và phát hành invoice, hãy xác định từng quyết định thuộc context nào. Có thể thay bằng hành vi xác nhận thương mại và phát Domain Event sau khi transaction SalesOrder commit.

Ví dụ:

~~~java
public final class SalesOrder {

    private final SalesOrderId id;
    private SalesOrderStatus status;
    private final List<SalesOrderLine> lines;

    public void confirm() {
        if (status != SalesOrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Only a draft sales order can be confirmed"
            );
        }

        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "A sales order must contain at least one line"
            );
        }

        status = SalesOrderStatus.CONFIRMED;
        // Ghi nhận SalesOrderConfirmed để phát sau commit.
    }
}
~~~

Ví dụ chỉ minh họa hành vi Sales. Cơ chế lưu event an toàn có thể dùng Transactional Outbox để tránh phát event trước khi transaction commit.

### 10.3. Dùng application service để điều phối

Application Service có thể tải Aggregate, gọi hành vi và lưu nó. Việc điều phối các context khác thường diễn ra qua message hoặc Process Manager.

~~~java
public final class ConfirmSalesOrderHandler {

    private final SalesOrderRepository orders;
    private final UnitOfWork unitOfWork;

    public void handle(ConfirmSalesOrder command) {
        SalesOrder order = orders.get(command.orderId());

        order.confirm();

        orders.save(order);
        unitOfWork.commit();
    }
}
~~~

Không nên để SalesOrder gọi trực tiếp FulfillmentRepository hoặc InvoiceRepository để thay đổi Aggregate của context khác.

### 10.4. Giữ tương thích trong giai đoạn chuyển tiếp

Nếu các module khác vẫn gọi OrderService, có thể giữ một facade hoặc adapter tạm thời chuyển lời gọi cũ sang use case mới.

Facade cần có kế hoạch loại bỏ. Nếu giữ mã tương thích vô thời hạn, mô hình cũ có thể tiếp tục lan rộng.

## 11. Chuyển đổi dữ liệu và schema an toàn

### 11.1. Đổi mô hình trong code chưa đủ

Khi một bảng orders trước đây chứa customer_id, shipment_id và invoice_id, việc tách Aggregate có thể cần schema mới:

- sales_orders.
- fulfillment_orders.
- invoices.
- external_order_references.

Cần xác định cách chuyển dữ liệu cũ sang các bảng mới mà không mất lịch sử hoặc tạo liên kết sai.

### 11.2. Dùng chiến lược Expand–Migrate–Contract

Một cách triển khai an toàn gồm ba giai đoạn:

**Expand**
- Thêm bảng, cột, index và constraint mới.
- Triển khai code có thể đọc cấu trúc mới.
- Nếu cần, ghi dữ liệu mới vào cả cấu trúc cũ và mới trong thời gian chuyển tiếp.

**Migrate**
- Backfill dữ liệu lịch sử.
- Tạo mapping giữa ID cũ và ID mới.
- Đối chiếu số lượng và quan hệ.
- Chuyển dần read path sang mô hình mới.
- Theo dõi các bản ghi chưa thể chuyển đổi.

**Contract**
- Xác nhận không còn consumer đọc cấu trúc cũ.
- Dừng dual-write.
- Xóa cột hoặc bảng cũ trong một lần phát hành riêng.
- Loại bỏ adapter tương thích sau khi hết thời hạn hỗ trợ.

Không xóa schema cũ ngay khi code mới vừa được triển khai.

### 11.3. Backfill phải có thể chạy lại an toàn

Một migration có thể bị gián đoạn. Hãy thiết kế để:
- Mỗi bản ghi có khóa nguồn ổn định.
- Mapping được bảo vệ bằng unique constraint.
- Backfill có thể tiếp tục từ checkpoint.
- Bản ghi đã chuyển không bị tạo trùng.
- Lỗi dữ liệu được ghi nhận và có quy trình xử lý.

Không giả định script migration chỉ chạy một lần hoàn hảo trong mọi môi trường.

### 11.4. Đối chiếu dữ liệu sau migration

Các kiểm tra có thể gồm:
- Số lượng SalesOrder trước và sau.
- Số lượng dòng hàng theo từng đơn.
- Tổng tiền và currency.
- Buyer, Delivery Recipient và BillToParty được ánh xạ đúng.
- Quan hệ một-nhiều giữa SalesOrder và FulfillmentOrder.
- Invoice và trạng thái của nó được bảo toàn.
- Các ID nguồn và ID nội bộ có mapping duy nhất theo phạm vi.

Nếu có sai lệch, không nên tiếp tục contract cho đến khi biết nguyên nhân và có quyết định nghiệp vụ.

## 12. Tương thích API, Domain Event và dữ liệu tích hợp

### 12.1. Đổi tên nội bộ không bắt buộc đổi API ngay

Một API cũ có thể trả customerId trong khi mô hình nội bộ mới phân biệt buyerId và deliveryRecipientId. Có thể giữ API cũ trong giai đoạn chuyển tiếp bằng adapter, miễn là semantics cũ được hiểu và ánh xạ chính xác.

Nếu API cũ thực sự không thể diễn đạt mô hình mới, cần thiết kế version hoặc field mới và có thời gian chuyển đổi consumer.

### 12.2. Event là hợp đồng, không phải object nội bộ

Không serialize trực tiếp Entity hoặc Aggregate vào message. Hãy dùng integration event có schema rõ ràng.

Ví dụ:

~~~java
public record SalesOrderConfirmedV2(
    String salesOrderId,
    String buyerId,
    String deliveryRecipientId,
    String orderNumber,
    Instant occurredAt,
    int schemaVersion
) {
}
~~~

Event V2 bổ sung vai trò mới. Consumer cũ có thể tiếp tục dùng event V1 trong giai đoạn tương thích, hoặc một adapter chuyển đổi giữa schema. Không đổi ý nghĩa của field cũ mà không version hóa hợp đồng.

### 12.3. Phân biệt event nội bộ và integration event

Domain Event mô tả điều xảy ra trong mô hình nội bộ. Integration Event là thông điệp công bố cho context hoặc hệ thống khác.

Không phải mọi Domain Event đều cần phát ra ngoài. Khi công bố, hãy chọn dữ liệu cần thiết và chuyển đổi sang ngôn ngữ của hợp đồng tích hợp.

### 12.4. Xử lý message lặp và đến muộn

Trong giai đoạn chuyển đổi, một event có thể được phát từ luồng cũ và mới. Consumer cần:
- Deduplicate theo Event ID hoặc khóa nghiệp vụ phù hợp.
- Kiểm tra source version hoặc schema version.
- Không áp dụng cùng một hành vi hai lần.
- Ghi nhận correlation để truy vết.
- Xử lý event đến muộn theo quy tắc trạng thái.

Không dùng Aggregate ID làm khóa deduplication cho mọi event vì một Aggregate có thể phát nhiều sự kiện hợp lệ.

## 13. Kiểm thử mô hình sau khi tái cấu trúc

### 13.1. Characterization test cho hành vi cũ

Trước khi thay đổi một hệ thống đang chạy, có thể viết characterization test để ghi lại hành vi hiện tại của các use case quan trọng.

Những test này không khẳng định mọi hành vi cũ đều đúng. Chúng giúp nhận biết thay đổi nào là chủ đích và thay đổi nào là hồi quy ngoài dự kiến.

### 13.2. Domain test cho quy tắc mới

Sau khi mô hình hóa, viết test thể hiện các phân biệt mới:

Ví dụ dưới đây minh họa ý tưởng kiểm thử; các factory và kiểu snapshot được giả định là đã được định nghĩa trong mô hình mới, còn import và phần dựng fixture được lược bỏ.

~~~java
@Test
void buyerCanBeDifferentFromDeliveryRecipient() {
    SalesOrder order = SalesOrder.draft(
        new SalesOrderId(UUID.randomUUID()),
        new BuyerId("BUYER-1"),
        new DeliveryRecipientSnapshot(
            "Nguyen An",
            "0900000000"
        )
    );

    assertEquals("BUYER-1", order.buyerId().value());
    assertEquals(
        "Nguyen An",
        order.deliveryRecipient().name()
    );
}
~~~

Test cho thấy Buyer và Delivery Recipient là hai vai trò riêng. Trong triển khai thật, dữ liệu cá nhân trong test nên là dữ liệu giả.

### 13.3. Test invariant của từng Aggregate

Kiểm tra SalesOrder không thể xác nhận khi chưa có dòng hàng; FulfillmentOrder không thể đánh dấu hoàn tất khi còn DeliveryTask chưa xử lý; Invoice không thể phát hành khi thiếu dữ liệu bắt buộc theo chính sách kế toán.

Các test này xác nhận ranh giới mới có trách nhiệm bảo vệ đúng invariant.

### 13.4. Integration test cho mapping và migration

Kiểm tra:
- Bản ghi cũ được chuyển sang đúng Aggregate mới.
- Quan hệ one-to-many được bảo toàn.
- External reference tra được nguồn.
- Mapping không tạo trùng.
- Read path mới trả cùng kết quả nghiệp vụ cần thiết.
- Consumer event cũ và mới xử lý đúng trong thời gian chuyển tiếp.

### 13.5. Contract test cho consumer

Nếu event hoặc API đổi schema, test hợp đồng xác nhận producer vẫn phát đúng schema và consumer có thể xử lý phiên bản được hỗ trợ.

Một thay đổi tên field tưởng nhỏ có thể phá consumer nếu JSON property được dùng trực tiếp. Cần kiểm tra ở ranh giới giao tiếp.

### 13.6. Kiểm thử song song trong giai đoạn chuyển đổi

Nếu hệ thống tạm thời dual-write, có thể chạy shadow read hoặc so sánh kết quả giữa mô hình cũ và mới. Chỉ dùng kết quả mới để phục vụ người dùng sau khi đã có độ tin cậy phù hợp.

Không nên dual-write vô thời hạn vì hai nguồn dữ liệu có thể lệch nhau. Cần metric, cảnh báo, thời hạn và điều kiện kết thúc rõ ràng.

## 14. Những sai lầm thường gặp khi tái cấu trúc mô hình

### Đổi tên class nhưng giữ nguyên ý nghĩa mơ hồ

Order đổi thành SalesOrder nhưng vẫn chứa shipment, invoice và trạng thái thanh toán không làm mô hình sâu hơn. Cần thay đổi trách nhiệm và quan hệ theo hiểu biết mới.

### Tách class theo sơ đồ kỹ thuật

Tách một class thành nhiều class chỉ vì file quá dài có thể không thay đổi mô hình miền. Hãy dựa trên khái niệm, vòng đời và invariant.

### Gộp mọi vai trò vào một Customer

Buyer, người nhận hàng và chủ thể nhận hóa đơn có thể là các vai trò khác nhau. Dùng một ID duy nhất chỉ khi nghiệp vụ bảo đảm các vai trò luôn cùng một chủ thể.

### Tạo quá nhiều Aggregate nhỏ

Tách mỗi bảng thành một Aggregate riêng có thể khiến một hành vi đơn giản phải điều phối quá nhiều transaction. Hãy giữ các thành phần cần nhất quán cùng nhau.

### Giữ Aggregate khổng lồ để tránh message

Aggregate quá lớn có thể làm tăng tải dữ liệu, lock contention và xung đột cập nhật. Nếu các vòng đời độc lập, hãy cân nhắc sự kiện và quy trình điều phối.

### Dùng quan hệ ORM quyết định ranh giới miền

@ManyToOne hoặc @OneToMany mô tả quan hệ lưu trữ. Nó không tự chứng minh hai đối tượng thuộc cùng Aggregate.

### Thay đổi schema và code cùng một bước không có kế hoạch

Một deployment có thể làm phiên bản ứng dụng cũ không đọc được schema mới hoặc consumer cũ không xử lý được event mới. Dùng expand–migrate–contract và kế hoạch tương thích.

### Chuyển dữ liệu mà không đối chiếu

Migration chạy xong không đồng nghĩa dữ liệu đúng. Cần kiểm tra cardinality, tổng tiền, mapping và các ngoại lệ.

### Coi mọi hiểu biết mới là lý do phải sửa ngay

Một nhận định chưa được kiểm chứng không nên lập tức làm thay đổi mô hình production. Hãy xác nhận bằng ví dụ, chính sách và người có thẩm quyền nghiệp vụ.

### Duy trì hai mô hình quá lâu

Adapter tương thích và dual-write có ích trong chuyển tiếp, nhưng nếu không có tiêu chí kết thúc, mô hình cũ sẽ tiếp tục tồn tại và làm tăng chi phí bảo trì.

## 15. Bài tập thực hành: tái cấu trúc mô hình xử lý đơn hàng

Một hệ thống thương mại điện tử đang dùng một Order Aggregate chứa Customer, OrderLine, Shipment, Invoice và Payment. Một số quy tắc hiện tại:

- Một đơn có thể giao từ nhiều kho.
- Người đặt hàng có thể khác người nhận.
- Hóa đơn có thể phát hành theo từng đợt giao.
- Thanh toán có thể được ủy quyền trước và capture sau.
- Một đợt giao có thể thất bại rồi được giao lại.
- Bộ phận Sales, Fulfillment, Billing và Payment do các nhóm nghiệp vụ khác nhau quản lý.

Hãy thực hiện:

1. Liệt kê những giả định của mô hình cũ.
2. Tạo các ví dụ phản chứng cho từng giả định.
3. Đề xuất Ubiquitous Language mới cho các vai trò và quy trình.
4. Phân biệt Entity, Value Object và snapshot.
5. Xác định Aggregate Root và invariant của Sales, Fulfillment, Billing và Payment.
6. Vẽ Context Map thể hiện các sự kiện trao đổi.
7. Xác định các ID tham chiếu giữa context.
8. Thiết kế schema mới và chiến lược expand–migrate–contract.
9. Xác định API/Event contract cần giữ tương thích.
10. Viết characterization test, domain test và integration test cho quá trình chuyển đổi.

### 15.1. Gợi ý mô hình mới

| Context | Aggregate | Trách nhiệm chính |
|---|---|---|
| Sales | SalesOrder | Cam kết thương mại, người mua, dòng hàng và tổng tiền |
| Fulfillment | FulfillmentOrder | Phân bổ kho, picking, packing và giao hàng |
| Billing | Invoice | Phát hành, điều chỉnh và trạng thái hóa đơn |
| Payment | Payment | Authorization, capture, refund và đối soát |

Các Aggregate có thể tham chiếu SalesOrderId hoặc ID nguồn theo hợp đồng. Không chia sẻ trực tiếp object graph giữa context.

### 15.2. Câu hỏi thảo luận với chuyên gia nghiệp vụ

- “Đơn hoàn tất” nghĩa là Sales đã hoàn tất, hàng đã giao hay hóa đơn đã phát hành?
- Khi giao một phần, SalesOrder có được xem là hoàn tất không?
- Người nhận hàng có cần danh tính độc lập hay chỉ là snapshot?
- Hóa đơn có thể tồn tại khi đơn bị hủy một phần không?
- Payment authorization hết hạn có làm SalesOrder bị hủy tự động không?
- Ai có quyền quyết định giao lại một shipment thất bại?

Câu trả lời giúp xác định state machine, ownership và các invariant của mô hình mới.

## 16. Checklist tái cấu trúc mô hình theo hiểu biết mới

Trước khi hoàn thành một lần thay đổi mô hình, hãy kiểm tra:

- Hiểu biết mới được chứng minh bằng ví dụ nghiệp vụ cụ thể.
- Các từ mơ hồ đã được làm rõ và thống nhất với chuyên gia.
- Tên Entity, Value Object và hành vi phản ánh đúng ngôn ngữ miền.
- Vai trò khác nhau không bị gộp vào một khái niệm chung.
- Danh tính, snapshot và thuộc tính đã được phân biệt.
- Cardinality và lifecycle của quan hệ đã được xác nhận.
- Ownership của từng thay đổi đã rõ.
- Aggregate boundary dựa trên invariant và consistency requirement.
- Bounded Context phản ánh mô hình và ngôn ngữ riêng.
- Context Map và integration contract được cập nhật.
- Tham chiếu giữa Aggregate dùng ID phù hợp.
- Domain Event không làm lộ object graph nội bộ.
- Migration có chiến lược expand–migrate–contract.
- Backfill có thể chạy lại và có đối chiếu dữ liệu.
- API và event có kế hoạch tương thích/versioning.
- Có characterization test, domain test và integration test.
- Dual-write hoặc adapter tương thích có thời hạn kết thúc.
- Chuyên gia nghiệp vụ xác nhận mô hình mới diễn đạt đúng quy tắc.

## Kết luận

Tái cấu trúc tên gọi, quan hệ và ranh giới theo hiểu biết mới là một phần thiết yếu của quá trình phát triển mô hình sâu. Khi một từ che giấu nhiều vai trò, một trạng thái đại diện cho nhiều vòng đời hoặc một Aggregate ôm nhiều quy tắc độc lập, đội ngũ cần quay lại ví dụ nghiệp vụ, làm rõ ngôn ngữ và điều chỉnh mô hình.

Tên mới phải phản ánh khái niệm thật; quan hệ phải thể hiện đúng danh tính, ownership và lifecycle; Aggregate phải bảo vệ invariant; Bounded Context phải giữ được mô hình và ngôn ngữ riêng. Khi mô hình thay đổi, code, database, API và event cũng cần được chuyển đổi có kế hoạch để bảo toàn dữ liệu và tương thích hệ thống.

Một mô hình sâu không phải là mô hình được thiết kế hoàn hảo ngay từ đầu. Đó là mô hình ngày càng diễn đạt đúng hơn những gì tổ chức hiểu về miền, và có thể tiếp tục thay đổi khi hiểu biết ấy phát triển.

