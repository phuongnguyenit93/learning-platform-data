# Quan hệ sở hữu, cascade và orphan removal theo vòng đời nghiệp vụ

Trong một mô hình miền, một đối tượng có thể chứa hoặc liên kết với nhiều đối tượng khác. Ví dụ, đơn hàng có các dòng hàng; hồ sơ khách hàng có các địa chỉ; dự án có các công việc; tài khoản có các giao dịch. Khi lưu những quan hệ này bằng ORM, nhóm thường gặp các cấu hình `cascade`, `orphanRemoval` và các tùy chọn xóa liên quan.

Những cấu hình đó có thể làm cho việc lưu và xóa dữ liệu thuận tiện, nhưng cũng có thể xóa nhầm dữ liệu hoặc làm mất lịch sử nếu quan hệ lưu trữ không phản ánh đúng vòng đời nghiệp vụ. Trong Domain-Driven Design (DDD), cần xác định đối tượng nào thực sự sở hữu vòng đời của đối tượng khác, đối tượng nào chỉ tham chiếu, aggregate root nào kiểm soát thay đổi và dữ liệu nào phải được giữ lại sau khi một quy trình kết thúc.

Một điểm cần phân biệt rõ: **ownership trong mô hình nghiệp vụ không đồng nghĩa với owning side trong ánh xạ JPA**. Tương tự, cascade của ORM là cơ chế lan truyền thao tác persistence, không tự quyết định chính sách nghiệp vụ. Bài học này giải thích cách phối hợp các khái niệm đó theo vòng đời của đối tượng, với ví dụ Java/JPA và các tình huống thường gặp.

## 1. Bắt đầu từ vòng đời nghiệp vụ, không bắt đầu từ annotation

Trước khi cấu hình `CascadeType.REMOVE` hoặc `orphanRemoval = true`, hãy hỏi nghiệp vụ điều gì xảy ra khi đối tượng cha được kết thúc hoặc khi một đối tượng con không còn liên kết với cha.

Ví dụ, với đơn hàng:

- Một `OrderLine` trong đơn nháp thường không có ý nghĩa độc lập ngoài đơn hàng.
- Khi người dùng bỏ một dòng hàng khỏi đơn nháp, dòng đó có thể được loại bỏ khỏi aggregate.
- Khi đơn đã xác nhận, việc bỏ một dòng hàng có thể cần quy trình điều chỉnh hoặc hủy một phần thay vì xóa trực tiếp.
- Khi đơn đã phát sinh hóa đơn, thanh toán hoặc vận đơn, việc xóa đơn có thể không được phép vì cần giữ lịch sử giao dịch.

Như vậy, cùng một quan hệ `Order` - `OrderLine` có thể có hành vi khác nhau tùy trạng thái và chính sách. Annotation ORM không thể tự suy ra những quy tắc đó.

Một quy trình phân tích phù hợp thường bắt đầu bằng các câu hỏi:

1. Đối tượng nào sở hữu vòng đời của đối tượng còn lại theo nghiệp vụ?
2. Đối tượng con có thể tồn tại độc lập sau khi tách khỏi cha không?
3. Đối tượng bên ngoài có được phép truy cập và thay đổi con trực tiếp không?
4. Khi cha bị xóa, con cần bị xóa, lưu trữ, chuyển chủ sở hữu hay giữ lại?
5. Có lịch sử, giao dịch hoặc nghĩa vụ nào ngăn việc xóa không?
6. Những thay đổi nào phải được thực hiện cùng nhau để bảo vệ invariant?

Chỉ sau khi trả lời những câu hỏi đó, nhóm mới quyết định cách ánh xạ quan hệ và cấu hình cascade.

## 2. Ownership nghiệp vụ và association là hai quan hệ khác nhau

**Ownership (quan hệ sở hữu)** trong mô hình miền diễn tả việc vòng đời của một đối tượng phụ thuộc vào đối tượng sở hữu. Đối tượng được sở hữu thường chỉ có ý nghĩa trong phạm vi chủ sở hữu và được thay đổi thông qua chủ sở hữu.

**Association/reference (quan hệ liên kết/tham chiếu)** chỉ cho biết hai đối tượng có liên quan hoặc biết đến nhau. Nó không có nghĩa một bên có quyền xóa hoặc điều khiển vòng đời của bên còn lại.

| Quan hệ | Ý nghĩa nghiệp vụ | Hệ quả khi đối tượng cha kết thúc |
| --- | --- | --- |
| Ownership | Đối tượng con phụ thuộc vòng đời và quy tắc của cha | Có thể loại bỏ con cùng cha nếu chính sách cho phép |
| Association/reference | Hai đối tượng có liên hệ nhưng có vòng đời riêng | Thường giữ đối tượng được tham chiếu hoặc xử lý bằng chính sách riêng |

### 2.1. Ví dụ quan hệ sở hữu

Một `Order` có thể sở hữu các `OrderLine`. Dòng hàng chỉ có ý nghĩa như một phần của đơn cụ thể. Bên ngoài không nên tải một dòng hàng rồi thay đổi số lượng mà bỏ qua quy tắc của đơn. `Order` aggregate root kiểm soát thêm, sửa và loại bỏ dòng hàng.

Một `ShoppingCart` có thể sở hữu các `CartItem` nếu cart item chỉ tồn tại trong giỏ hàng. Khi giỏ bị xóa theo chính sách, các item có thể được loại bỏ cùng nó.

### 2.2. Ví dụ quan hệ tham chiếu

Một `Order` tham chiếu `CustomerId`, nhưng khách hàng có vòng đời riêng. Xóa đơn nháp không có nghĩa xóa khách hàng.

Một `Invoice` có thể tham chiếu `OrderId`, nhưng hóa đơn có vòng đời và yêu cầu lưu trữ riêng. Xóa đơn không nên tự động xóa hóa đơn.

Một `Student` có thể tham chiếu `Course`; xóa một lượt đăng ký không có nghĩa xóa khóa học hoặc sinh viên. Một `User` có thể được gán vào nhiều `Role`; xóa user không nhất thiết có nghĩa xóa các role dùng chung.

### 2.3. Không suy ra ownership từ quan hệ một-nhiều

Quan hệ một-nhiều trong UML, object graph hoặc database không tự chứng minh rằng cha sở hữu con. Một khách hàng có nhiều đơn hàng, nhưng các đơn hàng có thể là aggregate độc lập. Một phòng ban có nhiều nhân viên, nhưng nhân viên không nhất thiết phải bị xóa khi phòng ban bị giải thể.

Hãy xác định vòng đời và quy tắc trước, sau đó mới quyết định quan hệ trong mô hình và database.

## 3. Aggregate root là ranh giới truy cập và thay đổi

Trong DDD, aggregate là ranh giới nhất quán gồm một aggregate root cùng các đối tượng nội bộ. Aggregate root bảo vệ invariant và là cổng truy cập từ bên ngoài.

Nếu `OrderLine` thuộc aggregate `Order`, application service nên tải `Order` qua repository rồi gọi `order.removeLine(lineId)`. Nó không nên gọi `orderLineRepository.deleteById(lineId)` để xóa dòng hàng độc lập, vì thao tác đó có thể bỏ qua điều kiện trạng thái, số dòng tối thiểu, tổng tiền hoặc các quy tắc khác của đơn.

```text
Application Service
        |
        v
OrderRepository
        |
        v
Order (Aggregate Root)
        |
        +---- OrderLine A
        +---- OrderLine B
        +---- OrderLine C

Yêu cầu bỏ OrderLine B
        |
        v
Order.removeLine(lineId)
        |
        +--> kiểm tra trạng thái đơn
        +--> kiểm tra dòng hàng tồn tại
        +--> kiểm tra invariant
        +--> loại bỏ dòng hàng
        +--> cập nhật dữ liệu dẫn xuất và ghi nhận event nếu cần
```

Aggregate root quyết định việc loại bỏ có hợp lệ hay không. ORM sau đó thực hiện lưu hoặc xóa các bản ghi tương ứng theo mapping. Thứ tự này quan trọng: domain model quyết định hành vi; persistence mapping hỗ trợ lưu trạng thái đã được quyết định.

### 3.1. Tham chiếu aggregate khác bằng ID

Nếu `Order` liên quan đến `Customer`, `Payment` hoặc `Shipment` nhưng các đối tượng đó có vòng đời độc lập, hãy cân nhắc giữ ID thay vì nhúng toàn bộ object graph.

```java
public final class Order {
    private final OrderId id;
    private final CustomerId customerId;
}
```

Điều này giới hạn ranh giới aggregate. Xóa `Order` không lan sang `Customer`, `Payment` hoặc `Shipment` chỉ vì chúng được tham chiếu.

## 4. Ownership nghiệp vụ khác owning side của JPA

Trong JPA, quan hệ hai chiều có một phía được gọi là **owning side**. Đây là phía mà ORM sử dụng để xác định cập nhật quan hệ trong database, thường là phía chứa foreign key. Phía còn lại có thể khai báo `mappedBy` và được gọi là inverse side.

Đây là khái niệm ánh xạ persistence, không phải khẳng định bên nào sở hữu vòng đời theo nghiệp vụ.

Ví dụ:

```java
@Entity
public class OrderEntity {
    @Id
    private UUID id;

    @OneToMany(mappedBy = "order")
    private List<OrderLineEntity> lines = new ArrayList<>();
}

@Entity
public class OrderLineEntity {
    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private OrderEntity order;
}
```

Trong mapping này:

- `OrderLineEntity.order` là owning side của quan hệ JPA vì nó chứa `@JoinColumn` và quản lý foreign key `order_id`.
- `OrderEntity.lines` là inverse side vì khai báo `mappedBy = "order"`.
- Về nghiệp vụ, `Order` vẫn có thể là aggregate root sở hữu vòng đời của `OrderLine`.

Vì vậy, không được kết luận `OrderLine` sở hữu `Order` trong nghiệp vụ chỉ vì `OrderLineEntity` là owning side của mapping JPA.

### 4.1. Cập nhật cả hai phía của quan hệ hai chiều

Khi dùng association hai chiều, helper method trong entity cha nên đồng bộ cả collection và tham chiếu phía con. Nếu chỉ thêm vào collection inverse side mà không cập nhật owning side, ORM có thể không ghi foreign key như mong muốn.

```java
public void addLine(OrderLineEntity line) {
    lines.add(line);
    line.attachTo(this);
}

public void removeLine(OrderLineEntity line) {
    lines.remove(line);
    line.detachFrom(this);
}
```

Đây là chi tiết quan trọng của mapping hai chiều. Nó không thay thế kiểm tra invariant nghiệp vụ trong aggregate root.

## 5. Cascade trong JPA là gì?

**Cascade** là cơ chế lan truyền một số thao tác persistence từ entity này sang entity liên kết. Khi một thao tác được gọi trên entity nguồn, ORM có thể áp dụng thao tác tương ứng cho entity đích nếu quan hệ được cấu hình cascade.

Ví dụ, khi lưu một `OrderEntity` mới cùng các `OrderLineEntity`, nhóm có thể muốn thao tác persist trên đơn hàng được lan truyền đến các dòng hàng. Khi đó, `CascadeType.PERSIST` có thể phù hợp với quan hệ sở hữu.

JPA cung cấp các loại cascade chính:

| Loại | Ý nghĩa khái quát |
| --- | --- |
| `PERSIST` | Lan truyền thao tác persist |
| `MERGE` | Lan truyền thao tác merge |
| `REMOVE` | Lan truyền thao tác remove |
| `REFRESH` | Lan truyền thao tác refresh |
| `DETACH` | Lan truyền thao tác detach |
| `ALL` | Bao gồm tất cả các loại cascade trên |

Cascade chỉ điều khiển việc lan truyền thao tác persistence. Nó không phải cơ chế tự động thực thi mọi quy tắc nghiệp vụ khi một đối tượng thay đổi.

### 5.1. Cascade PERSIST

Khi tạo một đơn mới cùng các dòng hàng mới, `CascadeType.PERSIST` cho phép persist đơn hàng kéo theo persist các dòng hàng được liên kết.

```java
@OneToMany(mappedBy = "order", cascade = CascadeType.PERSIST)
private List<OrderLineEntity> lines = new ArrayList<>();
```

Chỉ nên dùng khi các dòng hàng thực sự thuộc vòng đời của đơn và cần được lưu cùng aggregate. Nếu đối tượng liên kết đã tồn tại độc lập, không nên cascade persist một cách tùy tiện.

### 5.2. Cascade MERGE

`CascadeType.MERGE` lan truyền thao tác merge đến entity liên kết. Nó có thể hữu ích khi ứng dụng merge một đồ thị entity detached.

Tuy nhiên, merge một object graph cũ có thể ghi đè dữ liệu mới hơn nếu ứng dụng không kiểm soát version và trạng thái. Trong thiết kế DDD, một cách thường dùng là tải aggregate đang được quản lý qua repository, gọi hành vi trên root rồi để persistence context ghi thay đổi. Không cần thêm cascade merge chỉ vì muốn mọi quan hệ đều có `ALL`.

### 5.3. Cascade REMOVE

`CascadeType.REMOVE` lan truyền thao tác remove từ entity cha sang entity liên kết. Nó chỉ phù hợp khi đối tượng đích thực sự phụ thuộc vòng đời vào nguồn và được phép xóa cùng nguồn.

Ví dụ, một `OrderLine` riêng tư có thể bị xóa khi `Order` bị xóa trong trường hợp đơn nháp chưa phát sinh nghĩa vụ khác và chính sách cho phép xóa. Nhưng một `Customer`, `Payment`, `Invoice` hoặc `Product` được tham chiếu không nên bị xóa theo đơn hàng.

Theo JPA, cascade remove được thiết kế cho các quan hệ `OneToOne` và `OneToMany`. Ứng dụng portable không nên khai báo `CascadeType.REMOVE` trên `ManyToOne` hoặc `ManyToMany`. Đây cũng là một lý do để tránh cascade remove qua các quan hệ tham chiếu hoặc đối tượng được chia sẻ.

### 5.4. Cascade REFRESH và DETACH

`REFRESH` và `DETACH` thường ít được dùng hơn trong ứng dụng nghiệp vụ thông thường. Chúng ảnh hưởng đến trạng thái entity được quản lý trong persistence context. Chỉ cấu hình khi có nhu cầu rõ ràng và hiểu hệ quả đối với object graph.

### 5.5. Cascade ALL không phải lựa chọn mặc định

`CascadeType.ALL` tương đương việc bật mọi loại cascade. Nó tiện cho quan hệ cha-con có ownership rõ, nhưng có thể gây tác động rộng hơn dự kiến nếu quan hệ chỉ là tham chiếu.

Đừng thêm `cascade = CascadeType.ALL` vào mọi association theo thói quen. Hãy chọn đúng thao tác cần lan truyền, ví dụ chỉ `PERSIST` hoặc `PERSIST, MERGE`, và chỉ thêm `REMOVE` khi vòng đời thực sự phụ thuộc.

## 6. Orphan removal là gì?

**Orphan removal** là cơ chế xóa entity con khi nó bị loại khỏi quan hệ sở hữu được cấu hình `orphanRemoval = true`. Trong JPA, tùy chọn này áp dụng cho quan hệ `@OneToOne` và `@OneToMany`.

Ví dụ, nếu `OrderLine` chỉ có ý nghĩa trong một `Order`, khi dòng hàng bị loại khỏi collection của đơn, ORM có thể xóa entity dòng hàng khỏi database khi flush.

```java
@OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
)
private List<OrderLineEntity> lines = new ArrayList<>();
```

Hai cơ chế trong mapping trên có trách nhiệm liên quan nhưng khác nhau:

- `cascade = CascadeType.ALL` lan truyền các thao tác persistence được liệt kê, bao gồm persist, merge và remove.
- `orphanRemoval = true` yêu cầu loại bỏ entity con khi nó không còn thuộc quan hệ sở hữu, theo semantics của JPA.

Nói ngắn gọn, cascade remove xử lý trường hợp thao tác remove trên cha được lan truyền xuống con; orphan removal xử lý trường hợp con bị tách khỏi quan hệ sở hữu.

### 6.1. Orphan removal không phải xóa mọi đối tượng mất tham chiếu

Orphan removal không có nghĩa ORM tự tìm mọi object không còn được tham chiếu trong toàn hệ thống rồi xóa chúng. Nó gắn với một association cụ thể được cấu hình và semantics của quan hệ đó.

Nếu một `Product` được nhiều đơn hàng tham chiếu, bỏ sản phẩm khỏi một đơn không có nghĩa xóa sản phẩm. Đây là quan hệ tham chiếu, không phải ownership riêng tư của đơn.

### 6.2. Orphan removal gắn với vòng đời riêng tư

JPA định nghĩa orphan removal cho các quan hệ một-một và một-nhiều mà entity đích được xem là sở hữu riêng bởi entity nguồn. Khi entity nguồn bị remove, thao tác remove cũng được áp dụng đến entity đích như thể có cascade remove.

Không nên dùng orphan removal nếu entity con có thể được chuyển sang chủ sở hữu khác hoặc cần tồn tại độc lập. Khi cần chuyển quyền sở hữu, hãy thiết kế hành vi chuyển giao rõ ràng và kiểm tra semantics của provider; không dựa vào việc tách rồi gắn lại object trong cùng một lần xử lý như một kỹ thuật chung.

### 6.3. Thời điểm xóa

Orphan removal được thực thi theo lifecycle của persistence context, thường tại thời điểm flush. Vì vậy, việc gọi `collection.remove(...)` không nhất thiết phát câu lệnh SQL ngay tại dòng code đó. Nhóm cần kiểm thử trạng thái cuối và SQL được sinh ra bởi ORM đang sử dụng.

## 7. Ví dụ JPA: Order sở hữu OrderLine

Giả sử đơn hàng nháp sở hữu các dòng hàng. Khi bỏ một dòng, đơn cần kiểm tra trạng thái, tìm đúng dòng và cập nhật collection. Khi đơn được xóa theo chính sách, các dòng hàng riêng tư cũng được loại bỏ.

```java
@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private UUID id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @OneToMany(
            mappedBy = "order",
            cascade = CascadeType.ALL,
            orphanRemoval = true
    )
    private List<OrderLineEntity> lines = new ArrayList<>();

    protected OrderEntity() {}

    public void addLine(OrderLineEntity line) {
        ensureDraft();
        lines.add(line);
        line.attachTo(this);
    }

    public void removeLine(UUID lineId) {
        ensureDraft();

        OrderLineEntity line = lines.stream()
                .filter(item -> item.hasId(lineId))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order line not found"));

        if (lines.size() == 1) {
            throw new IllegalStateException(
                    "A draft order must contain at least one line");
        }

        lines.remove(line);
        line.detachFrom(this);
    }

    private void ensureDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                    "Only a draft order can be changed");
        }
    }
}

@Entity
@Table(name = "order_lines")
public class OrderLineEntity {
    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private OrderEntity order;

    private String productId;
    private int quantity;

    protected OrderLineEntity() {}

    void attachTo(OrderEntity order) {
        this.order = Objects.requireNonNull(order);
    }

    void detachFrom(OrderEntity expectedOrder) {
        if (this.order != expectedOrder) {
            throw new IllegalStateException("Unexpected order owner");
        }
        this.order = null;
    }

    boolean hasId(UUID candidate) {
        return id.equals(candidate);
    }
}
```

Đây là ví dụ tập trung vào ownership và mapping; một ứng dụng thực tế cần bổ sung constructor/factory, ID, giá trị tiền, kiểm tra quantity, equality, domain event và cách ánh xạ domain entity sang persistence entity nếu hai mô hình được tách riêng.

Một số điểm cần chú ý:

- `OrderEntity.lines` có `cascade = ALL` vì dòng hàng được xem là entity con riêng tư của đơn trong ví dụ này.
- `orphanRemoval = true` thể hiện việc bỏ dòng khỏi collection sẽ loại bỏ entity con khi flush.
- `OrderLineEntity.order` là owning side của quan hệ JPA vì nó giữ foreign key.
- `OrderEntity` vẫn là aggregate root theo nghiệp vụ và kiểm soát hành vi `removeLine`.
- Việc tách `order` khỏi child cần được đồng bộ với collection. Với mapping và provider cụ thể, cần kiểm tra SQL flush và ràng buộc foreign key để bảo đảm thao tác được thực hiện như mong muốn.
- Không dùng mapping này làm mẫu cho `Customer`, `Product`, `Payment` hoặc các đối tượng có vòng đời độc lập.

### 7.1. Đơn đã xác nhận cần hành vi khác

Nếu đơn đã xác nhận, `removeLine()` có thể từ chối thao tác. Nếu nghiệp vụ cho phép bỏ một mặt hàng sau xác nhận, có thể cần một use case như `RequestOrderAmendment`, `CancelOrderLine` hoặc `ReturnOrderLine`, tùy thời điểm và chính sách. Việc đó có thể phát sinh hoàn tiền, giải phóng tồn kho hoặc điều chỉnh hóa đơn; không nên dùng orphan removal như một cách thay thế quy trình.

## 8. Ví dụ: quan hệ tham chiếu không nên cascade remove

Giả sử nhiều đơn hàng cùng tham chiếu một khách hàng. Mapping có thể là:

```java
@Entity
public class OrderEntity {
    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private CustomerEntity customer;
}
```

Không nên cấu hình:

```java
// Không phù hợp nếu Customer có vòng đời độc lập
@ManyToOne(cascade = CascadeType.REMOVE)
private CustomerEntity customer;
```

Nếu xóa một đơn hàng, cascade remove có thể lan thao tác xóa đến khách hàng được tham chiếu. Điều này có thể làm hỏng các đơn hàng khác hoặc lịch sử khách hàng.

Tương tự, không nên cascade remove từ `Order` sang `Product` trong quan hệ nhiều-nhiều hoặc nhiều đơn hàng cùng tham chiếu sản phẩm. `Product` thường là aggregate độc lập trong context catalog; việc một dòng hàng không còn dùng sản phẩm không có nghĩa sản phẩm bị xóa.

Một quy tắc an toàn là chỉ cascade remove khi đối tượng đích thực sự là đối tượng con có vòng đời phụ thuộc và chính sách nghiệp vụ cho phép xóa cùng nguồn. Với reference đến aggregate khác, thông thường không cascade remove.

## 9. Cascade ORM và ON DELETE CASCADE của database

Hai cơ chế này có tên giống nhau nhưng hoạt động ở các tầng khác nhau.

**ORM cascade** được cấu hình trong mapping entity. ORM lan truyền thao tác persistence như persist, merge hoặc remove qua object graph khi ứng dụng gọi thao tác tương ứng.

**Database `ON DELETE CASCADE`** là hành vi của foreign key constraint. Khi một hàng cha bị xóa trong database, database tự động xóa các hàng con tham chiếu theo constraint.

| Tiêu chí | ORM cascade | Database `ON DELETE CASCADE` |
| --- | --- | --- |
| Nơi cấu hình | Mapping ORM | Foreign key constraint trong database |
| Thời điểm | Khi ORM thực hiện thao tác lifecycle | Khi database thực thi lệnh xóa hàng cha |
| Phạm vi | Object graph và các thao tác cascade được cấu hình | Các hàng có foreign key phụ thuộc |
| Callback/entity lifecycle | ORM có thể quản lý lifecycle của entity liên quan | Database xóa hàng mà không gọi lifecycle callback của ORM cho từng entity |
| Cache persistence context | ORM có thể cập nhật trạng thái object được quản lý | Database không tự đồng bộ object đang nằm trong bộ nhớ ORM |
| Tính phụ thuộc công nghệ | Theo JPA/provider | Theo database và schema |

Không nên bật cả hai cơ chế mà không hiểu thứ tự và hệ quả. Nếu database tự xóa hàng con, ORM có thể vẫn còn object hoặc cache cũ trong persistence context. Ngược lại, nếu ORM xóa từng entity trước, database cascade có thể không còn nhiều việc phải làm.

`ON DELETE CASCADE` hữu ích trong một số schema khi quan hệ phụ thuộc rõ và cần bảo vệ referential integrity ngay cả khi có thao tác SQL ngoài ORM. Tuy nhiên, nó không tự phát domain event, không gọi hành vi của aggregate root và không thực hiện quy trình nghiệp vụ như hoàn tiền hay thu hồi quyền.

## 10. Orphan removal và cascade remove: so sánh trực tiếp

| Tình huống | `CascadeType.REMOVE` | `orphanRemoval = true` |
| --- | --- | --- |
| Gọi remove trên entity cha | Lan remove sang entity con được cascade | Entity con trong quan hệ orphan-removal cũng bị remove khi cha bị remove theo semantics JPA |
| Loại entity con khỏi collection | Không tự động có nghĩa remove chỉ vì cascade remove | Entity con bị remove khi trở thành orphan và flush |
| Phạm vi quan hệ | Theo mapping cascade | Quan hệ `OneToOne`/`OneToMany` riêng tư |
| Ý nghĩa chính | Lan truyền thao tác remove | Xóa entity con khi bị tách khỏi quan hệ sở hữu |
| Phù hợp | Con cần bị xóa khi cha bị xóa | Con không có vòng đời độc lập ngoài cha |

Nếu cần cả việc lưu con cùng cha và xóa orphan khi tách con, mapping có thể dùng `cascade = PERSIST` hoặc `ALL` cùng `orphanRemoval = true`, tùy các thao tác thực sự cần lan truyền.

### 10.1. Không dùng orphan removal để chuyển con giữa cha

Orphan removal được thiết kế cho đối tượng con riêng tư. Nếu một entity cần chuyển từ aggregate cha A sang aggregate cha B, việc tách khỏi A có thể khiến ORM đánh dấu nó để xóa. Không nên dựa vào việc remove khỏi collection rồi add sang collection khác trong cùng transaction như một cách chuyển giao portable.

Nếu nghiệp vụ cho phép chuyển quyền sở hữu, hãy mô hình hóa thao tác đó rõ ràng, kiểm tra ràng buộc và chọn mapping/persistence flow phù hợp. Có thể đối tượng không thực sự là orphan-owned child và cần được mô hình hóa như entity độc lập.

## 11. Cascade trong các loại quan hệ JPA

### 11.1. One-to-One

Một `UserProfile` có thể là phần mở rộng riêng tư của `UserAccount`. Nếu profile không có ý nghĩa độc lập và phải kết thúc cùng tài khoản, cascade và orphan removal có thể phù hợp.

Nhưng nếu hồ sơ có lịch sử, được tham chiếu bởi quy trình khác hoặc cần lưu lại sau khi tài khoản đóng, không nên xóa nó tự động. Cần xác định hành vi close, archive hoặc retention trước.

### 11.2. One-to-Many

Đây là quan hệ thường gặp giữa aggregate root và entity nội bộ, ví dụ `Order` - `OrderLine`, `Cart` - `CartItem`. `CascadeType.PERSIST` và `orphanRemoval = true` thường phù hợp nếu child thực sự phụ thuộc vòng đời vào parent.

Tuy nhiên, `Department` - `Employee` có thể là quan hệ một-nhiều nhưng không nên cascade remove nếu nhân viên vẫn tồn tại khi phòng ban giải thể. Cần phân biệt quan hệ sở hữu với quan hệ tổ chức.

### 11.3. Many-to-One

Đây thường là phía con tham chiếu đến cha hoặc một aggregate khác. Ví dụ `OrderLine` tham chiếu `Order`, hoặc `Order` tham chiếu `Customer`. Thông thường không cascade remove từ phía many-to-one đến đối tượng được tham chiếu vì nó có thể được chia sẻ.

Trong mapping hai chiều, `ManyToOne` thường là owning side của foreign key. Điều này không có nghĩa nó sở hữu vòng đời của đối tượng phía kia.

### 11.4. Many-to-Many

Quan hệ nhiều-nhiều thường biểu diễn hai tập đối tượng có vòng đời riêng, ví dụ `Student` - `Course`, `User` - `Role`, `Product` - `Category`. Xóa một liên kết thường chỉ nên xóa hàng trong join table, không xóa các entity ở hai đầu.

Vì vậy, tránh cascade remove qua `ManyToMany` nếu các đối tượng đích được chia sẻ. Nếu bản thân mối quan hệ có thuộc tính và vòng đời riêng, cân nhắc mô hình hóa join entity như `Enrollment`, `UserRoleAssignment` hoặc `ProductCategoryAssignment`.

### 11.5. Bảng gợi ý

| Quan hệ | Ví dụ | Cascade remove/orphan removal thường có phù hợp? |
| --- | --- | --- |
| One-to-Many sở hữu riêng tư | Order - OrderLine | Có thể phù hợp nếu child chỉ thuộc parent và chính sách cho phép |
| One-to-One sở hữu riêng tư | User - UserPreferences | Có thể phù hợp nếu preferences không có vòng đời riêng |
| Many-to-One tham chiếu | Order - Customer | Thường không cascade remove |
| Many-to-Many chia sẻ | User - Role | Thường chỉ xóa liên kết, không xóa entity ở hai đầu |
| One-to-Many nhưng child độc lập | Department - Employee | Không cascade remove chỉ vì quan hệ một-nhiều |

Đây là gợi ý, không phải quy tắc thay thế phân tích nghiệp vụ. Một số miền có semantics đặc biệt và cần quyết định khác.

## 12. Tách aggregate domain khỏi persistence entity

Không phải dự án DDD nào cũng ánh xạ trực tiếp domain entity bằng JPA annotation. Một số dự án dùng persistence entity riêng và mapper chuyển đổi giữa domain model với schema.

Khi tách hai mô hình:

- Domain aggregate kiểm soát hành vi và invariant.
- Persistence entity biểu diễn cấu trúc lưu trữ và quan hệ ORM.
- Repository adapter tải persistence graph, chuyển thành aggregate rồi lưu thay đổi.
- Cascade và orphan removal được cấu hình trong persistence mapping dựa trên ownership đã xác nhận ở domain model.

Tách mô hình có thể giúp domain không phụ thuộc ORM, nhưng tăng công việc mapping và nguy cơ sai lệch. Chỉ nên áp dụng khi lợi ích về ranh giới, kiểm soát schema hoặc độ độc lập đáng với chi phí.

Nếu domain model và persistence model dùng chung class, vẫn cần giữ các quy tắc: không để ORM mapping quyết định hành vi nghiệp vụ, không công khai thao tác phá vỡ aggregate root và không dùng cascade quá rộng.

## 13. Xóa, hủy và lưu trữ: không phải cùng một lifecycle

Một aggregate có thể có nhiều trạng thái kết thúc khác nhau. Việc một object không còn được dùng không tự động có nghĩa bản ghi phải bị xóa.

| Hành vi | Ví dụ | Xử lý persistence thường gặp |
| --- | --- | --- |
| Remove child khỏi aggregate | Bỏ dòng hàng trong đơn nháp | Cập nhật aggregate; orphan removal có thể xóa child row |
| Delete aggregate | Xóa bản nháp tạo nhầm, chưa có tham chiếu cần giữ | Remove root; cascade remove cho child riêng tư nếu phù hợp |
| Cancel | Hủy đơn đã được xác nhận | Giữ aggregate và chuyển trạng thái; thực hiện quy trình bù nếu cần |
| Close | Đóng tài khoản | Giữ dữ liệu và ghi nhận thời điểm/trạng thái đóng |
| Archive | Lưu trữ hợp đồng kết thúc | Đánh dấu hoặc chuyển dữ liệu sang vùng lưu trữ |
| Erase data | Xóa dữ liệu theo chính sách đã xác nhận | Xóa/ẩn danh phạm vi cụ thể, xử lý bản sao và tham chiếu |

### 13.1. Không xóa lịch sử giao dịch chỉ để làm sạch object graph

Một đơn đã giao có thể được tham chiếu bởi hóa đơn, thanh toán, hoàn tiền, vận đơn và yêu cầu hỗ trợ. Những dữ liệu này có ý nghĩa độc lập. Nếu cần xóa thông tin nhận diện, có thể phải ẩn danh một số trường trong khi vẫn giữ số liệu giao dịch cần thiết theo chính sách.

### 13.2. Snapshot giúp giữ ý nghĩa lịch sử

Một hóa đơn có thể lưu tên và địa chỉ xuất hóa đơn tại thời điểm phát hành. Nếu chỉ tham chiếu hồ sơ khách hàng hiện tại, thay đổi địa chỉ sau này có thể làm báo cáo lịch sử hiển thị sai. Snapshot là quyết định mô hình hóa để giữ thông tin cần thiết tại thời điểm sự kiện xảy ra.

## 14. Cascade và domain event

Cascade ORM chỉ thực hiện thao tác persistence trong object graph. Nó không tự động phát domain event có ý nghĩa nghiệp vụ.

Ví dụ, khi một `Order` bị hủy, việc xóa `OrderLine` khỏi database không tự động:

- Giải phóng tồn kho đã giữ.
- Hủy hoặc hoàn giao dịch thanh toán.
- Thông báo cho đơn vị vận chuyển.
- Ghi nhận lý do hủy.
- Cập nhật projection hoặc hệ thống chăm sóc khách hàng.

Những việc này cần được mô hình hóa bằng hành vi nghiệp vụ và quy trình điều phối. Aggregate có thể ghi nhận `OrderCancelled`; application layer công bố sự kiện sau khi thay đổi được commit hoặc dùng Transactional Outbox. Các context liên quan tiếp tục xử lý theo hợp đồng của chúng.

```text
CancelOrder command
       |
       v
Order aggregate checks policy
       |
       v
OrderCancelled domain event
       |
       v
Commit / Outbox
       |
       +------> Inventory releases reservation
       +------> Payment starts refund/void flow
       +------> Delivery receives cancellation request
       +------> Support/read model updates
```

Nếu quy trình có nhiều bước và có thể thất bại giữa chừng, cần trạng thái trung gian, retry, idempotency và có thể saga/process manager. Không dùng cascade delete như một cách thay thế cho workflow liên context.

## 15. Giao dịch, thứ tự flush và lỗi khi xóa

Khi ORM xóa entity cha hoặc orphan, câu lệnh SQL có thể được phát tại flush hoặc commit. Các ràng buộc foreign key, thứ tự xóa và trạng thái persistence context có thể ảnh hưởng kết quả.

Nhóm cần chú ý:

- Xóa child trước hay parent trước để không vi phạm foreign key.
- Có entity đang được quản lý trong persistence context nhưng bị xóa bởi database cascade không.
- Collection đã bị thay đổi có đồng bộ với owning side không.
- Có entity detached hoặc proxy nào đang được tham chiếu không.
- Có optimistic version hoặc audit listener nào cần được thực thi không.
- Khi constraint từ chối xóa, transaction và trạng thái ứng dụng được xử lý ra sao.

### 15.1. Không dựa vào thứ tự SQL ngầm

Không nên giả định ORM luôn phát câu lệnh theo đúng thứ tự mà code gọi. ORM có thể gom thao tác và sắp xếp SQL theo dependency hoặc chiến lược riêng. Khi mapping có orphan removal, foreign key không nullable hoặc nhiều cascade, cần kiểm thử với provider thực tế.

### 15.2. Kiểm tra trạng thái sau flush

Một kiểm thử chỉ xác nhận collection trong bộ nhớ đã bỏ child chưa đủ chứng minh bản ghi đã bị xóa. Có thể cần flush, clear persistence context và truy vấn lại database để kiểm tra trạng thái đã lưu.

### 15.3. Xử lý lỗi ràng buộc

Nếu database từ chối xóa vì còn tham chiếu, đó có thể là dấu hiệu chính sách chưa được xử lý đầy đủ. Application layer nên chuyển lỗi persistence thành kết quả phù hợp hoặc lỗi nghiệp vụ có thể hiểu, thay vì để client nhận thông báo SQL thô.

## 16. Kiểm thử ownership, cascade và orphan removal

Các kiểm thử nên chứng minh mapping thực hiện đúng vòng đời đã quyết định, đồng thời xác nhận không xóa nhầm đối tượng được tham chiếu.

### 16.1. Kiểm thử persist cascade

Tạo một aggregate mới cùng các child, lưu root và xác nhận các child được lưu đúng. Sau khi clear persistence context, tải lại root và kiểm tra collection.

### 16.2. Kiểm thử orphan removal

1. Tạo và lưu một đơn có hai dòng hàng.
2. Tải đơn trong một transaction mới.
3. Gọi hành vi `removeLine()` trên root.
4. Flush và commit.
5. Clear persistence context.
6. Xác nhận dòng hàng đã bị loại bỏ khỏi database và dòng còn lại vẫn tồn tại.

Kiểm tra cả collection và hàng trong database. Nếu có mapping hai chiều, xác nhận owning side được đồng bộ.

### 16.3. Kiểm thử cascade remove

Tạo đơn cùng các dòng hàng riêng tư, xóa đơn theo chính sách và xác nhận các dòng hàng bị xóa. Đồng thời tạo khách hàng hoặc sản phẩm được tham chiếu và xác nhận chúng vẫn tồn tại.

### 16.4. Kiểm thử không xóa đối tượng được chia sẻ

Tạo hai đơn cùng tham chiếu một khách hàng hoặc sản phẩm. Xóa một đơn nháp theo chính sách. Xác nhận đơn còn lại và đối tượng được tham chiếu vẫn tồn tại.

### 16.5. Kiểm thử trạng thái không cho phép xóa

Thử loại bỏ dòng hàng khi đơn đã xác nhận hoặc đã giao. Xác nhận domain model từ chối hoặc yêu cầu use case điều chỉnh phù hợp; database không bị thay đổi một phần.

### 16.6. Dùng đúng ORM provider và database

Hành vi flush, orphan removal, cascade và SQL sinh ra có thể phụ thuộc provider. Nên dùng integration test với phiên bản ORM và database mục tiêu, đặc biệt khi mapping có foreign key không nullable, database cascade hoặc callback.

## 17. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Coi owning side JPA là ownership nghiệp vụ | Chọn sai đối tượng có quyền xóa và quản lý vòng đời | Phân tích ownership trong domain trước khi mapping |
| Thêm `CascadeType.ALL` cho mọi quan hệ | Xóa hoặc thay đổi lan sang entity độc lập | Chọn cascade theo từng thao tác và vòng đời |
| Dùng cascade remove từ `Order` sang `Customer` hoặc `Product` | Xóa đối tượng được nhiều aggregate tham chiếu | Tham chiếu bằng ID hoặc mapping không cascade remove |
| Bật orphan removal cho entity có vòng đời độc lập | Tách liên kết có thể xóa nhầm entity cần giữ | Chỉ dùng cho child riêng tư của parent |
| Xóa child qua repository riêng | Bỏ qua invariant của aggregate root | Thay đổi collection qua hành vi của root |
| Chỉ cập nhật inverse collection | Foreign key có thể không được cập nhật như mong muốn | Đồng bộ owning side và inverse side |
| Nhầm ORM cascade với database ON DELETE CASCADE | Không hiểu callback, cache và SQL thực tế | Phân biệt cơ chế ở hai tầng và kiểm thử |
| Dùng orphan removal để chuyển child sang parent khác | Entity có thể bị đánh dấu xóa theo semantics orphan | Mô hình hóa chuyển giao hoặc thiết kế lại ownership |
| Dùng xóa vật lý thay cho cancel/close/archive | Mất lịch sử và các nghĩa vụ liên quan | Dùng hành vi kết thúc vòng đời đúng ngữ nghĩa |
| Giả định cascade tự phát domain event | Các context khác không được thông báo | Tạo event và workflow riêng |
| Chỉ kiểm tra object trong bộ nhớ | Không phát hiện SQL hoặc foreign key lỗi khi flush | Flush, clear và truy vấn lại database trong integration test |

## 18. Quy trình thiết kế quan hệ sở hữu và cascade

Khi ánh xạ một quan hệ bằng ORM, nhóm có thể đi theo các bước sau.

### Bước 1: Xác định ý nghĩa nghiệp vụ của hai đối tượng

Mô tả mỗi đối tượng, danh tính, vòng đời và các hành vi quan trọng. Tránh bắt đầu bằng cardinality trong database.

### Bước 2: Xác định ownership hay reference

Hỏi đối tượng con có thể tồn tại độc lập không, ai có quyền thay đổi nó và điều gì xảy ra khi liên kết bị loại bỏ. Ghi rõ các trường hợp ngoại lệ theo trạng thái.

### Bước 3: Xác định aggregate boundary

Nếu hai đối tượng cần cùng bảo vệ invariant, xem xét đưa chúng vào cùng aggregate. Chọn root và giới hạn truy cập bên ngoài qua root.

### Bước 4: Xác định hành vi khi kết thúc vòng đời

Phân biệt remove, cancel, close, deactivate, archive và erase. Xác định điều kiện, quyền, lịch sử và tác động đến các quan hệ khác.

### Bước 5: Chọn cascade tối thiểu cần thiết

Quyết định có cần `PERSIST`, `MERGE`, `REMOVE`, `REFRESH`, `DETACH` hay `ALL` không. Không chọn `ALL` chỉ vì tiện.

### Bước 6: Quyết định orphan removal

Chỉ bật `orphanRemoval = true` khi child là đối tượng riêng tư và việc tách khỏi parent đồng nghĩa nó không còn tồn tại trong mô hình.

### Bước 7: Thiết kế mapping JPA

Chọn owning side, `mappedBy`, foreign key, nullability và helper method đồng bộ hai phía. Phân biệt rõ owning side persistence với ownership nghiệp vụ.

### Bước 8: Xác định database constraint

Chọn `ON DELETE CASCADE`, `RESTRICT`, `SET NULL` hoặc hành vi khác dựa trên chính sách và cách ORM thực thi. Tránh để constraint tự quyết định quy trình nghiệp vụ.

### Bước 9: Kiểm thử lifecycle và tác động phụ

Kiểm thử persist, merge, remove, orphan, reference còn tồn tại, trạng thái không cho phép và flush/commit. Kiểm tra cả event, audit và workflow liên context nếu có.

## 19. Nguyên tắc thực hành

Khi sử dụng cascade và orphan removal trong DDD/JPA, nhóm nên nhớ:

- **Ownership là quyết định nghiệp vụ.** Xác định vòng đời trước khi cấu hình annotation.
- **Owning side JPA là quyết định ánh xạ.** Nó cho biết phía nào quản lý foreign key, không nói ai sở hữu vòng đời.
- **Aggregate root kiểm soát thay đổi.** Entity nội bộ được thêm, sửa và loại bỏ qua hành vi của root.
- **Cascade chỉ lan truyền thao tác persistence.** Nó không thay thế domain policy hoặc application workflow.
- **Chọn cascade tối thiểu.** Chỉ lan truyền những thao tác thực sự cần thiết.
- **Chỉ dùng orphan removal cho child riêng tư.** Không dùng cho đối tượng có vòng đời độc lập hoặc được chia sẻ.
- **Không cascade remove qua reference tùy tiện.** Customer, Product, Invoice, Payment và các aggregate khác thường không bị xóa cùng đối tượng tham chiếu.
- **Phân biệt ORM cascade với database cascade.** Hai cơ chế có lifecycle, cache và callback khác nhau.
- **Không nhầm xóa với hủy hoặc lưu trữ.** Dùng trạng thái và hành vi miền khi lịch sử cần được giữ.
- **Đồng bộ hai phía của quan hệ JPA.** Đặc biệt khi dùng `mappedBy` và association hai chiều.
- **Kiểm thử đến database thật.** Flush, clear và xác nhận hàng cùng quan hệ sau commit.
- **Phối hợp liên context bằng event/workflow.** Cascade ORM không thực hiện thay các quy trình phân tán.

Quan hệ sở hữu, cascade và orphan removal chỉ an toàn khi phản ánh đúng vòng đời nghiệp vụ. Ownership quyết định đối tượng nào phụ thuộc vào đối tượng nào; aggregate root bảo vệ invariant và kiểm soát thay đổi; cascade lan truyền thao tác persistence; orphan removal xóa child riêng tư khi nó bị tách khỏi quan hệ; còn database constraint bảo vệ tính toàn vẹn tham chiếu ở tầng lưu trữ. Phân biệt rõ các trách nhiệm này giúp nhóm tránh xóa nhầm dữ liệu, giữ được lịch sử và xây dựng mapping ORM phù hợp với domain model.

## 20. Câu hỏi tự kiểm tra

1. Phân biệt ownership nghiệp vụ với association/reference bằng ví dụ `Order` - `OrderLine` và `Order` - `Customer`.
2. Vì sao owning side của quan hệ JPA không đồng nghĩa với đối tượng sở hữu vòng đời theo DDD?
3. Aggregate root cần kiểm soát thao tác xóa entity nội bộ như thế nào?
4. `CascadeType.PERSIST`, `MERGE` và `REMOVE` có ý nghĩa gì?
5. Vì sao `CascadeType.ALL` không nên được cấu hình mặc định cho mọi association?
6. Orphan removal là gì và khác cascade remove ở điểm nào?
7. Vì sao `orphanRemoval = true` phù hợp với `OrderLine` riêng tư nhưng thường không phù hợp với `Product` được nhiều đơn hàng tham chiếu?
8. Trong mapping hai chiều `Order` - `OrderLine`, owning side và inverse side nằm ở đâu? Vì sao cần đồng bộ cả hai phía?
9. Phân biệt ORM cascade với database `ON DELETE CASCADE` về lifecycle, callback và cache.
10. Vì sao hủy một đơn đã xác nhận thường cần domain event và workflow thay vì xóa dây chuyền các bản ghi?
11. Những trường hợp nào cần kiểm thử flush, clear persistence context và truy vấn lại database?
12. Hãy chọn một quan hệ trong hệ thống của bạn, xác định ownership/reference, aggregate root, cascade cần dùng, orphan removal có phù hợp không và cách kiểm thử để chứng minh không xóa nhầm dữ liệu.
