# Gộp quá nhiều đối tượng vào một aggregate

Trong Domain-Driven Design, aggregate là ranh giới nhất quán của một nhóm đối tượng domain. Aggregate có một aggregate root để bên ngoài tương tác với trạng thái và hành vi bên trong theo một quy tắc rõ ràng. Vì vậy, việc gom nhiều entity và value object vào cùng một aggregate có thể làm cho mô hình ban đầu trông thuận tiện, nhưng nếu ranh giới đó lớn hơn phạm vi invariant thực sự cần bảo vệ, hệ thống sẽ phải trả giá bằng giao dịch nặng, cạnh tranh đồng thời, truy vấn lớn và khó thay đổi.

Chủ đề này thuộc phần tactical design của Domain-Driven Design. Mục tiêu của DDD là biến hiểu biết nghiệp vụ thành mô hình và ngôn ngữ chung giữa chuyên gia với đội phát triển. Trong bối cảnh đó, aggregate không phải là một cấu trúc để phản ánh toàn bộ cây đối tượng của một khái niệm nghiệp vụ. Aggregate là một quyết định về ranh giới nhất quán và quyền thay đổi trạng thái. Một aggregate tốt giúp đội ngũ biết điều gì phải được bảo vệ trong cùng một giao dịch, điều gì có thể thay đổi độc lập và thông tin nào nên được trao đổi qua sự kiện hoặc một cơ chế tích hợp khác.

## 1. Aggregate tồn tại để bảo vệ invariant

Invariant là quy tắc phải đúng tại thời điểm domain chấp nhận một thay đổi. Ví dụ, một đơn hàng đã bị hủy không được chuyển sang trạng thái đã giao; tổng tiền của đơn phải phù hợp với các dòng hàng và chính sách giá áp dụng; một hạn mức tín dụng không được bị vượt qua nếu nghiệp vụ yêu cầu kiểm tra ngay khi chấp nhận giao dịch.

Aggregate gom những dữ liệu và hành vi cần thiết để kiểm tra các invariant có cùng ranh giới nhất quán. Aggregate root là điểm vào của ranh giới đó. Client không nên tùy ý thay đổi entity con bằng cách lấy trực tiếp entity con từ repository.

Có thể hình dung:

```text
                    Aggregate
        +--------------------------------+
        | Aggregate Root                 |
        |                                |
        |  Entity / Value Object         |
        |  Entity / Value Object         |
        |  Entity / Value Object         |
        |                                |
        |  Invariant phải đúng            |
        +--------------------------------+
```

Một câu hỏi thiết kế quan trọng là:

> Những đối tượng nào thực sự phải được thay đổi và kiểm tra cùng nhau để một hành động nghiệp vụ được chấp nhận?

Nếu câu trả lời chỉ liên quan đến một phần nhỏ của object graph, việc đưa toàn bộ graph vào một aggregate thường tạo ra một boundary quá lớn.

## 2. Aggregate lớn xuất hiện như thế nào?

Lỗi này thường bắt đầu từ một mô hình đối tượng tự nhiên trong đầu người phát triển. Ví dụ một `Order` có `Customer`, `Address`, `Product`, `Warehouse`, `Payment`, `Shipment`, `Discount` và `OrderLine`. Khi sử dụng ORM, việc tạo quan hệ giữa các lớp rất dễ dàng. Từ đó, đội phát triển có thể xây dựng một aggregate chứa toàn bộ các quan hệ:

```text
Order
 ├── Customer
 ├── ShippingAddress
 ├── BillingAddress
 ├── OrderLine[*]
 │    └── Product
 ├── Payment[*]
 ├── Shipment[*]
 │    └── ShipmentItem[*]
 ├── Discount[*]
 └── Invoice
```

Object graph này có thể đúng về mặt liên kết dữ liệu, nhưng nó chưa chứng minh rằng tất cả các đối tượng phải thuộc cùng một consistency boundary.

`Product` có thể được nhiều đơn hàng tham chiếu và được quản lý bởi catalog. `Payment` có vòng đời riêng. `Shipment` có thể được xử lý bởi fulfillment. `Invoice` có thể thuộc accounting. Những đối tượng này có thể liên quan về nghiệp vụ với `Order`, nhưng quan hệ nghiệp vụ không tự động biến chúng thành thành viên của cùng một aggregate.

Một aggregate nên được xác định bởi hành vi và invariant, sau đó mới quyết định quan hệ tham chiếu. Nếu bắt đầu từ quan hệ database hoặc object graph rồi biến toàn bộ graph thành aggregate, boundary rất dễ phình to.

## 3. Dấu hiệu aggregate đang quá lớn

Không có một con số tuyệt đối về số entity hay số thuộc tính để kết luận aggregate lớn. Một aggregate có vài entity vẫn có thể quá rộng, trong khi một aggregate có nhiều value object vẫn hoàn toàn hợp lý. Các dấu hiệu dưới đây hữu ích hơn việc đếm object.

| Dấu hiệu | Điều cần điều tra |
|---|---|
| Mỗi thay đổi nhỏ phải load cả graph | Có thật sự cần toàn bộ graph cho invariant không? |
| Transaction thường xuyên cập nhật nhiều phần không liên quan | Các phần đó có vòng đời và invariant riêng không? |
| Nhiều request cùng sửa một root | Root có đang trở thành điểm tranh chấp không? |
| Concurrency conflict xuất hiện thường xuyên | Boundary có đang quá rộng không? |
| Repository trả về object graph rất lớn | Query có đang phản ánh boundary sai không? |
| Lazy loading kéo theo nhiều truy vấn | Aggregate có chứa quá nhiều quan hệ không? |
| Một entity con có nhiều use case độc lập | Entity đó có thể có aggregate riêng không? |
| Một thay đổi nghiệp vụ cần khóa nhiều bản ghi | Có đang dùng transaction để bù cho boundary quá rộng không? |
| Test aggregate phải dựng rất nhiều fixture | Có quá nhiều invariant hoặc trách nhiệm trong một root không? |
| Các team khác nhau cần cập nhật các phần khác nhau | Boundary có phản ánh ownership nghiệp vụ không? |
| Một aggregate phải biết quá nhiều policy | Chính sách có thuộc context hoặc aggregate khác không? |

Những dấu hiệu này không phải bằng chứng độc lập. Chúng là tín hiệu để quay lại câu hỏi về invariant và transaction.

## 4. Quan hệ không đồng nghĩa với cùng aggregate

Một trong những nhầm lẫn phổ biến nhất là:

```text
A có quan hệ với B
        ↓
A chứa B
        ↓
A và B cùng aggregate
```

Chuỗi suy luận này không đúng trong mọi trường hợp.

Ví dụ `OrderLine` cần biết `ProductId`, nhưng điều đó không có nghĩa `Product` phải nằm bên trong `Order`:

```java
public final class OrderLine {
    private final ProductId productId;
    private Quantity quantity;
    private Money unitPrice;

    public void changeQuantity(Quantity newQuantity) {
        this.quantity = newQuantity;
    }
}
```

`Order` có thể bảo vệ invariant của các dòng hàng:

```java
public final class Order {
    private final OrderId id;
    private final List<OrderLine> lines = new ArrayList<>();

    public void addLine(ProductId productId, Quantity quantity, Money unitPrice) {
        // kiểm tra invariant của chính Order
        lines.add(new OrderLine(productId, quantity, unitPrice));
    }
}
```

Thông tin chi tiết của `Product` có thể được truy cập thông qua application service hoặc một domain service phù hợp khi nghiệp vụ cần. Việc tham chiếu bằng identity giúp tránh biến toàn bộ catalog thành một phần của transaction boundary của `Order`.

## 5. Boundary nên theo invariant, không theo cấu trúc dữ liệu

Hãy bắt đầu bằng các hành vi nghiệp vụ thay vì các bảng.

Ví dụ, nghiệp vụ có thể nói:

1. Khi đặt hàng, hệ thống phải đảm bảo đơn có ít nhất một dòng hàng.
2. Số lượng của mỗi dòng phải lớn hơn 0.
3. Tổng giá trị đơn phải được tính theo các dòng hàng đã chấp nhận.
4. Khi đơn đã giao, không được thêm dòng hàng.

Các invariant này có thể được bảo vệ bên trong `Order` aggregate:

```text
Order
 ├── OrderLine*
 ├── Money / Quantity / Address
 └── trạng thái đơn

Invariant:
 - có ít nhất một line khi submit
 - quantity hợp lệ
 - trạng thái cho phép thêm/sửa line
 - tổng tiền phù hợp với line
```

Trong khi đó, việc vận chuyển có thể có invariant riêng:

```text
Shipment
 ├── ShipmentItem*
 └── trạng thái vận chuyển

Invariant:
 - chỉ đóng shipment khi đủ điều kiện
 - không sửa shipment đã hoàn tất
 - trạng thái vận chuyển chuyển theo quy trình
```

Nếu `Order` và `Shipment` có thể thay đổi độc lập, việc đưa `Shipment` vào `Order` chỉ để tiện truy cập sẽ làm boundary rộng hơn nhu cầu nhất quán.

## 6. Aggregate lớn làm tăng chi phí transaction

Khi một aggregate chứa nhiều đối tượng, một command đơn giản có thể phải đọc và ghi nhiều dữ liệu.

Ví dụ:

```text
UpdateOrderAddress
        |
        v
Load Order
        |
        +--> Customer
        +--> OrderLine x 80
        +--> Product x 80
        +--> Shipment
        +--> Payment
        +--> Invoice
        |
        v
Validate
        |
        v
Save entire aggregate
```

Nếu chỉ địa chỉ giao hàng thay đổi, việc tải và đồng bộ toàn bộ graph có thể không mang lại thêm giá trị nghiệp vụ. Nó làm tăng I/O, thời gian giữ transaction và số lượng dữ liệu cần kiểm tra.

Chi phí có thể nhìn theo mô hình đơn giản:

```text
Transaction cost
    ≈ load cost
    + validation cost
    + persistence cost
    + lock duration
    + serialization cost
```

Đây không phải công thức định lượng tuyệt đối. Nó là cách tư duy để thấy rằng boundary lớn tác động đồng thời đến nhiều thành phần của hệ thống.

## 7. Aggregate lớn làm tăng contention

Concurrency là một lý do quan trọng để giới hạn aggregate.

Giả sử nhiều request cùng cập nhật các phần khác nhau:

```text
Request A: cập nhật địa chỉ giao hàng
Request B: xác nhận thanh toán
Request C: thêm dòng hàng
Request D: cập nhật shipment
             |
             v
         Order aggregate
```

Nếu mọi thao tác đều phải sửa cùng một aggregate root, chúng có thể tranh chấp cùng một version:

```text
Order version = 41

        A reads 41
        B reads 41
        C reads 41

        A writes 42
        B -> conflict
        C -> conflict
```

Optimistic locking giúp phát hiện xung đột, nhưng không loại bỏ nguyên nhân. Khi boundary quá rộng, những thao tác vốn có thể độc lập trở thành đối thủ cạnh tranh trên cùng một transaction boundary.

Một aggregate nhỏ hơn cho phép các thay đổi độc lập có version và transaction riêng:

```text
Order aggregate       Shipment aggregate       Payment aggregate
version 41            version 17               version 8
     |                      |                       |
  order change          shipment change        payment change
```

Điều này chỉ phù hợp khi domain cho phép các trạng thái đó thay đổi độc lập. Nếu một invariant thực sự yêu cầu atomicity giữa chúng, việc tách aggregate phải được đánh giá lại.

## 8. Aggregate lớn làm mờ ownership

DDD dùng model để diễn đạt trách nhiệm nghiệp vụ. Nếu một aggregate chứa `Order`, `Payment`, `Shipment` và `Invoice`, rất khó trả lời:

- Ai sở hữu quy tắc thanh toán?
- Ai quyết định shipment có được tạo không?
- Ai quyết định invoice được phát hành?
- Ai được phép thay đổi trạng thái payment?
- Quy tắc nào thuộc Order và quy tắc nào thuộc Billing?

Khi ownership bị mờ, domain model dễ biến thành một object manager lớn. Root trở thành nơi nhận mọi command và biết mọi policy.

Một boundary rõ hơn có thể tạo ra các model có trách nhiệm riêng:

```text
Ordering
  └── Order aggregate

Billing
  └── Payment aggregate

Fulfillment
  └── Shipment aggregate

Accounting
  └── Invoice aggregate
```

Các aggregate vẫn có thể liên quan qua domain event hoặc application orchestration:

```text
OrderSubmitted
      |
      +----> Payment workflow
      |
      +----> Fulfillment workflow
      |
      +----> Notification
```

Mỗi bước có thể có transaction boundary phù hợp với invariant của nó.

## 9. Không nên tách aggregate chỉ vì muốn nhỏ

Ngược lại, chia aggregate một cách máy móc cũng tạo ra vấn đề. Nếu hai đối tượng luôn phải thay đổi cùng nhau để bảo vệ một invariant mạnh, tách chúng có thể khiến invariant không còn được bảo vệ trong một transaction.

Ví dụ, nghiệp vụ yêu cầu:

> Khi xác nhận chuyển tiền, số dư tài khoản và trạng thái giao dịch phải thay đổi atomically trong cùng một consistency boundary.

Nếu mô hình tách `AccountBalance` và `Transfer` thành hai aggregate chỉ vì mỗi object có vẻ độc lập, hệ thống sẽ phải giải quyết trạng thái trung gian:

```text
Transfer = COMPLETED
Balance  = OLD
```

Nếu trạng thái này vi phạm invariant nghiệp vụ, boundary đã bị tách quá mức.

Vì vậy, mục tiêu là tìm boundary vừa đủ để bảo vệ invariant. Không có quy tắc rằng aggregate càng nhỏ càng tốt.

## 10. Một aggregate nên có một root rõ ràng

Aggregate root là identity và entry point của aggregate. Các đối tượng bên trong không nên được thay đổi tùy ý từ bên ngoài.

Ví dụ:

```java
public final class Order {
    private final OrderId id;
    private final List<OrderLine> lines = new ArrayList<>();

    public void removeLine(ProductId productId) {
        ensureEditable();
        lines.removeIf(line -> line.productId().equals(productId));
        ensureOrderRules();
    }

    public List<OrderLine> lines() {
        return List.copyOf(lines);
    }

    private void ensureEditable() {
        // invariant
    }

    private void ensureOrderRules() {
        // invariant
    }
}
```

Client gọi hành vi của root:

```java
order.removeLine(productId);
```

thay vì:

```java
order.getLines().get(0).setQuantity(...);
```

Điểm quan trọng là root kiểm soát các thay đổi cần thiết để invariant không bị phá vỡ.

## 11. Repository không nên biến thành loader của toàn bộ graph

Một repository cho aggregate có trách nhiệm lấy và lưu aggregate theo boundary đã chọn.

```java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
```

Nếu `findById()` luôn phải join hàng chục bảng vì aggregate chứa toàn bộ graph, repository đang phản ánh một boundary có thể quá lớn.

Repository không nên được thiết kế chỉ để làm cho ORM dễ mapping. Domain model quyết định boundary; persistence mapping phải phục vụ boundary đó.

Trong hệ thống thực tế, một aggregate có thể được lưu bằng nhiều bảng. Điều đó vẫn ổn nếu các bảng cùng phục vụ một consistency boundary. Vấn đề xuất hiện khi persistence model ép những đối tượng có vòng đời độc lập vào cùng transaction.

## 12. ORM có thể che giấu kích thước thật của aggregate

Các tính năng như lazy loading, cascade và dirty checking làm cho aggregate lớn trông dễ sử dụng:

```java
order.getShipment().getItems().add(item);
repository.save(order);
```

Mã nguồn có thể rất ngắn, nhưng chi phí runtime có thể lớn:

```text
save(order)
   |
   +--> dirty checking
   +--> load lazy collection
   +--> cascade
   +--> update nhiều row
   +--> flush
```

Vì vậy, khi đánh giá aggregate, cần xem cả hành vi runtime: SQL phát sinh, số row đọc/ghi, thời gian transaction, lock và tỷ lệ conflict. Một object graph nhỏ trong code chưa chắc là một aggregate nhỏ trong database.

## 13. Ví dụ: Order aggregate quá lớn

Giả sử hệ thống bán hàng có mô hình ban đầu:

```text
Order
 ├── Customer
 ├── Address
 ├── OrderLine[*]
 │    └── Product
 ├── Payment
 ├── Shipment
 │    └── Warehouse
 └── Invoice
```

Use case `ChangeShippingAddress` chỉ cần:

```text
Order
 └── ShippingAddress
```

Nhưng nếu toàn bộ object graph là một aggregate, repository có thể phải tải rất nhiều dữ liệu.

Sau khi phân tích invariant, đội có thể xác định:

```text
Order
 ├── OrderLine*
 └── ShippingAddress

Payment
 └── PaymentTransaction*

Shipment
 └── ShipmentItem*

Invoice
 └── InvoiceLine*
```

`OrderLine` tham chiếu `ProductId` thay vì giữ cả `Product` aggregate. `Shipment` nhận thông tin cần thiết thông qua command hoặc event. `Invoice` được tạo theo quy trình accounting.

Ví dụ event:

```text
OrderSubmitted
      |
      +--> Payment process
      |
      +--> Shipment process
      |
      +--> Invoice process
```

Mỗi consumer có thể lưu trạng thái riêng và bảo vệ invariant riêng.

## 14. Khi nào nên tham chiếu bằng identity?

Tham chiếu aggregate khác bằng identity là một kỹ thuật phổ biến để giữ boundary rõ:

```java
public record ProductId(UUID value) {}

public final class OrderLine {
    private final ProductId productId;
    private Money price;
    private Quantity quantity;
}
```

Thay vì:

```java
public final class OrderLine {
    private Product product;
    private Quantity quantity;
}
```

Việc chọn identity đặc biệt hữu ích khi `Product` có lifecycle riêng hoặc nằm trong context khác.

Tuy nhiên, identity reference không phải một quy tắc tuyệt đối. Nếu một value object hoặc entity thực sự thuộc cùng boundary và invariant của root cần dữ liệu đó, nó vẫn có thể nằm trong aggregate.

## 15. Khi nào có thể dùng domain service?

Một số nghiệp vụ liên quan đến nhiều aggregate nhưng không nên đặt toàn bộ các aggregate vào một aggregate lớn. Ví dụ quyết định cấp hạn mức có thể cần dữ liệu từ `Customer`, `Account` và `RiskProfile`.

Có thể tổ chức:

```text
Application Service
       |
       +--> CustomerRepository
       +--> AccountRepository
       +--> RiskPolicy
       |
       v
   CreditDecision
```

Domain service phù hợp khi logic là nghiệp vụ quan trọng nhưng không tự nhiên thuộc về một entity hoặc aggregate duy nhất.

Điều này cho phép các aggregate giữ boundary riêng mà business rule vẫn được biểu diễn rõ ràng.

## 16. Domain event giúp tách những thay đổi không cần atomicity

Giả sử sau khi `Order` được submit, hệ thống cần:

- tạo shipment;
- khởi tạo payment;
- gửi email;
- cập nhật read model.

Không phải tất cả thao tác này đều cần nằm trong cùng transaction với `Order`.

Có thể phát sinh:

```text
Order.submit()
    |
    +--> OrderSubmitted
              |
              +--> Payment
              +--> Shipment
              +--> Notification
              +--> Read model
```

Điều kiện quan trọng là domain phải chấp nhận tính nhất quán cuối cùng cho các bước đó. Nếu một invariant yêu cầu kết quả ngay trong cùng transaction, event-driven coordination không thể được dùng chỉ để làm aggregate nhỏ hơn.

## 17. Một aggregate lớn thường là dấu hiệu của transaction-centric design

Nếu đội phát triển bắt đầu từ câu hỏi:

> Làm sao để mọi thay đổi liên quan được commit trong một transaction?

thì dễ dẫn đến việc gom mọi thứ vào một aggregate.

DDD yêu cầu hỏi thêm:

> Quy tắc nào thực sự cần atomicity?

Hai câu hỏi này cho kết quả khác nhau.

Ví dụ:

```text
Business relationship:
Order -> Payment -> Shipment -> Invoice

Không tự động suy ra:
One aggregate
```

Thay vào đó:

```text
Business relationship
        |
        v
Phân tích invariant
        |
        v
Xác định atomicity
        |
        v
Xác định aggregate boundary
```

## 18. Đo kích thước aggregate bằng hành vi

Thay vì đặt quy tắc như “aggregate không quá N entity”, có thể theo dõi các chỉ số:

| Chỉ số | Ý nghĩa |
|---|---|
| Số entity/value object được load trung bình | Chi phí đọc của command |
| Số row được cập nhật | Phạm vi ghi |
| Transaction duration | Thời gian giữ consistency/lock |
| Optimistic lock conflict | Mức contention |
| Số aggregate khác cần đọc | Độ phức tạp của use case |
| Số invariant kiểm tra | Mật độ trách nhiệm của root |
| Số use case chạm vào root | Mức tập trung thay đổi |
| Tần suất lazy loading | Khả năng graph bị mở rộng ngoài dự kiến |
| Tỷ lệ retry do conflict | Chi phí concurrency |

Các số liệu này giúp đội đưa ra quyết định dựa trên hành vi thật của hệ thống.

## 19. Một use case là phép thử tốt cho boundary

Hãy lấy một command cụ thể:

```text
ChangeOrderShippingAddress
```

Hỏi lần lượt:

1. Đối tượng nào phải thay đổi?
2. Invariant nào phải được kiểm tra?
3. Dữ liệu nào cần để kiểm tra invariant?
4. Những dữ liệu nào chỉ được đọc để hiển thị?
5. Những thay đổi nào phải atomic?
6. Những thay đổi nào có thể xảy ra sau đó?

Nếu câu trả lời là:

```text
Thay đổi Address
Kiểm tra Order status
Commit Order
```

thì việc load `Payment`, `Shipment`, `Invoice` và toàn bộ `Product` graph cần được xem xét lại.

## 20. Quy trình refactor aggregate quá lớn

Khi nghi ngờ aggregate quá lớn, không nên tách class ngay. Có thể đi theo các bước:

### Bước 1: Liệt kê use case

Ghi các command thực tế:

```text
SubmitOrder
ChangeOrderAddress
AddOrderLine
CapturePayment
CreateShipment
IssueInvoice
```

### Bước 2: Liệt kê invariant

Ví dụ:

```text
Order:
 - không thêm line sau khi shipped
 - quantity > 0

Payment:
 - không capture quá số tiền được phép

Shipment:
 - không ship trước trạng thái hợp lệ
```

### Bước 3: Gán invariant cho owner

Mỗi invariant nên có nơi bảo vệ rõ ràng.

### Bước 4: Xác định atomicity

Đánh dấu:

```text
[SAME TX] phải thay đổi cùng nhau
[SEPARATE] có thể xử lý độc lập
[EVENTUAL] chấp nhận nhất quán cuối cùng
```

### Bước 5: Tìm identity boundary

Đối tượng có lifecycle riêng, identity riêng và invariant riêng thường là ứng viên cho aggregate riêng.

### Bước 6: Thay object reference bằng identity khi phù hợp

```java
ProductId
CustomerId
ShipmentId
PaymentId
```

### Bước 7: Đưa orchestration ra application layer

Nếu một use case cần nhiều aggregate:

```text
Application Service
   |
   +--> OrderRepository
   +--> PaymentRepository
   +--> ShipmentRepository
```

Application service điều phối use case; từng aggregate vẫn tự bảo vệ invariant của mình.

### Bước 8: Chạy lại các use case quan trọng

Kiểm tra cả behavior và chi phí runtime. Refactor chỉ thành công khi boundary mới vẫn bảo vệ được nghiệp vụ và giảm được vấn đề mà boundary cũ gây ra.

## 21. Ví dụ Java trước và sau

Một thiết kế quá rộng có thể bắt đầu như:

```java
public final class Order {
    private Customer customer;
    private List<OrderLine> lines;
    private Payment payment;
    private Shipment shipment;
    private Invoice invoice;

    public void changeShippingAddress(Address address) {
        shipment.changeAddress(address);
    }
}
```

`Order` lúc này đang điều khiển trạng thái của nhiều lifecycle khác nhau.

Một thiết kế có boundary rõ hơn:

```java
public final class Order {
    private final OrderId id;
    private Address shippingAddress;
    private final List<OrderLine> lines;
    private OrderStatus status;

    public void changeShippingAddress(Address address) {
        if (!status.allowsAddressChange()) {
            throw new DomainException("Order không cho phép đổi địa chỉ");
        }
        this.shippingAddress = address;
    }
}
```

Payment:

```java
public final class Payment {
    private final PaymentId id;
    private final OrderId orderId;
    private PaymentStatus status;

    public void capture() {
        if (!status.canCapture()) {
            throw new DomainException("Payment không thể capture");
        }
        status = PaymentStatus.CAPTURED;
    }
}
```

Shipment:

```java
public final class Shipment {
    private final ShipmentId id;
    private final OrderId orderId;
    private ShipmentStatus status;

    public void dispatch() {
        if (!status.canDispatch()) {
            throw new DomainException("Shipment không thể dispatch");
        }
        status = ShipmentStatus.DISPATCHED;
    }
}
```

Ba aggregate có thể cùng dùng `OrderId` để liên kết nghiệp vụ mà không cần một object graph khổng lồ.

## 22. Tách aggregate có thể làm thay đổi cách xử lý transaction

Sau refactor, một use case có thể trở thành:

```text
Command
  |
  v
Application Service
  |
  +--> Order.submit()
  |       |
  |       +--> transaction 1
  |
  +--> publish OrderSubmitted
          |
          +--> Payment workflow
          |
          +--> Shipment workflow
```

Đây là thay đổi kiến trúc quan trọng. Đội phát triển phải xác định rõ:

- trạng thái nào là nguồn sự thật;
- event nào được phát hành;
- consumer có thể xử lý lại không;
- cần idempotency ở đâu;
- lỗi giữa các bước được xử lý thế nào;
- nghiệp vụ có chấp nhận eventual consistency không.

Aggregate nhỏ hơn không tự động giải quyết những câu hỏi này. Nó chỉ tạo ra boundary để các câu hỏi được trả lời rõ ràng hơn.

## 23. Các lỗi refactor thường gặp

### Tách theo bảng database

Mỗi bảng được biến thành một aggregate chỉ vì bảng có primary key. Cách này bỏ qua invariant nghiệp vụ.

### Tách theo class

Mỗi entity thành một aggregate để làm object nhỏ. Kết quả là nhiều invariant phải đi qua service bên ngoài.

### Tách để giảm query

Một aggregate được tách chỉ vì query chậm, trong khi invariant thực sự yêu cầu atomicity. Khi đó performance có thể tốt hơn nhưng correctness giảm.

### Gom theo transaction tiện nhất

Mọi object được gom để có một `save()` duy nhất. Đây là cách dùng persistence transaction để quyết định domain boundary.

### Dùng event cho mọi quan hệ

Một số invariant mạnh bị chuyển thành eventual consistency chỉ để tránh aggregate lớn. Đây là thay đổi nghiệp vụ cần được chấp nhận rõ ràng.

## 24. Aggregate boundary và bounded context

Aggregate là tactical boundary bên trong một domain model. Bounded context là boundary của một model và ngôn ngữ cụ thể. Hai khái niệm liên quan nhưng khác nhau.

Ví dụ:

```text
Ordering Context
  └── Order aggregate

Billing Context
  └── Invoice aggregate
  └── Payment aggregate

Fulfillment Context
  └── Shipment aggregate
```

Cùng từ “Order” hoặc “Customer” có thể mang ý nghĩa khác nhau trong các context. Vì vậy, việc cố tạo một aggregate khổng lồ dùng chung cho toàn hệ thống thường là dấu hiệu model đang vượt qua boundary của một bounded context.

## 25. Aggregate boundary và ubiquitous language

Khi xác định aggregate, hãy dùng ngôn ngữ của domain expert.

Nếu chuyên gia nói:

> “Đơn hàng được xác nhận trước, sau đó bộ phận thanh toán xử lý giao dịch.”

thì câu nói này gợi ý hai trách nhiệm có thể có lifecycle khác nhau.

Nếu chuyên gia nói:

> “Trong lúc xác nhận, tổng tiền và các dòng hàng phải được kiểm tra cùng nhau.”

thì đó là tín hiệu mạnh cho một invariant trong cùng boundary.

Aggregate boundary vì vậy nên xuất phát từ hành vi và quy tắc mà domain expert hiểu, sau đó được kiểm chứng bằng transaction và concurrency.

## 26. Một heuristic thực dụng

Có thể dùng chuỗi câu hỏi sau trong design session:

```text
1. Root này bảo vệ invariant nào?
             |
             v
2. Invariant cần dữ liệu nào?
             |
             v
3. Dữ liệu nào phải thay đổi atomically?
             |
             v
4. Những phần nào có lifecycle riêng?
             |
             v
5. Những phần nào có concurrency riêng?
             |
             v
6. Boundary hiện tại có quá rộng không?
```

Nếu một object chỉ được giữ trong aggregate vì “có quan hệ” hoặc “ORM map như vậy”, đó là lý do yếu. Nếu object cần thiết để bảo vệ invariant và phải thay đổi atomically, đó là lý do mạnh hơn.

## 27. Checklist review aggregate

Trước khi chấp nhận một aggregate, đội phát triển có thể hỏi:

- Root có invariant rõ ràng không?
- Mọi entity bên trong có tham gia bảo vệ invariant của root không?
- Có entity nào có lifecycle độc lập không?
- Có entity nào thường xuyên được cập nhật bởi use case khác không?
- Một command nhỏ có phải load phần lớn aggregate không?
- Transaction có giữ lock quá lâu không?
- Optimistic locking conflict có cao không?
- Aggregate có tham chiếu aggregate khác bằng identity khi phù hợp không?
- Repository có phải tải graph lớn chỉ để xử lý command nhỏ không?
- Có logic thuộc bounded context khác đang bị kéo vào không?
- Những thay đổi liên quan có thực sự cần atomicity không?
- Nếu tách aggregate, domain có chấp nhận eventual consistency không?
- Event hoặc application service có thể điều phối phần còn lại không?

Nếu nhiều câu trả lời cho thấy các phần có lifecycle và invariant riêng, boundary nên được xem xét lại.

## 28. Ví dụ decision table

| Tình huống | Cùng aggregate? | Lý do |
|---|---:|---|
| Hai entity phải thay đổi cùng transaction để giữ invariant | Có thể | Atomicity là yêu cầu domain |
| Entity chỉ được đọc để hiển thị | Thường không | Không cần đưa vào consistency boundary |
| Entity có lifecycle riêng | Thường không | Có boundary thay đổi riêng |
| Entity thuộc bounded context khác | Thường không | Model boundary khác |
| Hai entity chỉ liên kết bằng identity | Có thể tách | Quan hệ không bắt buộc cùng aggregate |
| Cùng được lưu trong một bảng | Chưa đủ kết luận | Persistence model không quyết định domain boundary |
| Cùng thay đổi trong một use case | Chưa đủ kết luận | Use case có thể điều phối nhiều aggregate |
| Cần cùng version để bảo vệ invariant | Có thể | Cần phân tích atomicity |

Từ “có thể” trong bảng là có chủ ý. Aggregate boundary là quyết định domain, không phải quy tắc cơ học.

## 29. Cách đánh giá sau khi refactor

Sau khi tách aggregate, cần đánh giá ít nhất bốn nhóm kết quả:

```text
Correctness
  ├── invariant vẫn được bảo vệ
  └── trạng thái lỗi được xử lý đúng

Performance
  ├── dữ liệu load giảm
  ├── transaction ngắn hơn
  └── query/lock hợp lý hơn

Concurrency
  ├── conflict giảm
  └── retry giảm

Maintainability
  ├── ownership rõ hơn
  ├── use case dễ hiểu hơn
  └── model dùng đúng ubiquitous language
```

Một refactor thành công phải cải thiện boundary mà không làm mất rule nghiệp vụ.

## 30. Kết luận

Lỗi gộp quá nhiều đối tượng vào một aggregate thường xuất phát từ việc đồng nhất object graph, quan hệ dữ liệu hoặc transaction tiện lợi với consistency boundary. Trong DDD, aggregate được xác định bởi invariant, atomicity và quyền kiểm soát thay đổi của domain.

Khi aggregate quá lớn, transaction có thể trở nên nặng, concurrency conflict tăng, repository phải tải graph lớn và ownership nghiệp vụ bị mờ. Cách xử lý là quay lại use case, xác định invariant, xác định dữ liệu cần để bảo vệ invariant, phân tích atomicity và tìm các lifecycle độc lập. Những phần có thể thay đổi độc lập có thể trở thành aggregate riêng và được liên kết bằng identity, application orchestration hoặc domain event tùy yêu cầu nhất quán.

Một aggregate tốt không phải aggregate có ít class nhất. Đó là aggregate có boundary đủ rõ để bảo vệ invariant cần thiết, đủ nhỏ để tránh tranh chấp không cần thiết và đủ sát với ngôn ngữ nghiệp vụ để đội phát triển có thể cùng hiểu và thay đổi model một cách an toàn.
