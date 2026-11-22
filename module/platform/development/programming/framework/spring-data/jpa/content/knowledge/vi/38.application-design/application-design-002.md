# Thiết kế aggregate và ranh giới cập nhật nhất quán

## Mục tiêu

Trong Domain-Driven Design (DDD), aggregate là một nhóm đối tượng miền được quản lý như một đơn vị nhất quán. Một aggregate có một **aggregate root** làm điểm truy cập bên ngoài. Root bảo vệ các quy tắc nghiệp vụ (invariants) phải luôn đúng khi một transaction hoàn tất.

Với Spring Data JPA, cách chia aggregate ảnh hưởng trực tiếp đến entity mapping, cascade, repository, transaction, khóa đồng thời và cách phối hợp nhiều dịch vụ. Nếu aggregate quá lớn, cập nhật trở nên nặng và dễ tranh chấp. Nếu ranh giới quá nhỏ, một quy tắc nghiệp vụ có thể bị chia cắt qua nhiều transaction và khó bảo vệ.

Sau bài này, bạn có thể:

- Phân biệt entity, aggregate và aggregate root.
- Xác định ranh giới aggregate từ quy tắc nhất quán của nghiệp vụ.
- Thiết kế quan hệ JPA để root kiểm soát vòng đời entity con.
- Đặt repository và transaction theo ranh giới aggregate.
- Phân biệt cập nhật nội bộ aggregate với phối hợp nhiều aggregate.
- Dùng optimistic locking và ràng buộc database để bảo vệ cập nhật đồng thời.
- Chọn transaction cục bộ, outbox hoặc Saga cho nghiệp vụ trải qua nhiều ranh giới.
- Kiểm thử invariants, mapping và hành vi đồng thời.

## 1. Aggregate là gì?

Một **entity** có định danh và vòng đời riêng. Một **value object** được xác định bởi giá trị của nó, thường bất biến và không có định danh độc lập trong mô hình miền.

**Aggregate** là ranh giới nhất quán bao quanh một hoặc nhiều entity và value object. Aggregate root là entity duy nhất mà code bên ngoài được phép dùng để yêu cầu thay đổi trạng thái của aggregate.

Ví dụ một đơn hàng có thể gồm:

- PurchaseOrder: root, có mã đơn và trạng thái.
- OrderLine: các dòng hàng, thuộc vòng đời của đơn hàng.
- Money hoặc địa chỉ giao hàng: value object được lưu cùng aggregate.

Các quy tắc như “đơn hàng đã xác nhận không được thêm dòng hàng” hoặc “tổng tiền phải bằng tổng thành tiền của các dòng” thuộc trách nhiệm của PurchaseOrder. Code bên ngoài không nên sửa trực tiếp OrderLine hoặc tự gán tổng tiền để bỏ qua quy tắc của root.

Một aggregate không đơn giản là toàn bộ các bảng có quan hệ khóa ngoại với nhau. Nó là một **ranh giới cập nhật nhất quán**: những dữ liệu nào phải được kiểm tra và thay đổi cùng nhau để bảo vệ một quy tắc nghiệp vụ?

## 2. Xác định ranh giới từ invariants

Hãy bắt đầu bằng cách liệt kê các quy tắc phải đúng ngay khi một transaction commit.

Ví dụ với đơn hàng:

- Đơn hàng phải có ít nhất một dòng trước khi xác nhận.
- Số lượng mỗi dòng phải lớn hơn 0.
- Đơn đã xác nhận không được sửa nội dung.
- Tổng tiền phải khớp với các dòng hàng.
- Một reservation tồn kho không được vượt số lượng còn có thể giữ.

Các quy tắc đầu tiên có thể thuộc cùng một aggregate Order vì chúng cần được kiểm tra đồng thời khi sửa đơn. Quy tắc tồn kho có thể thuộc aggregate InventoryItem riêng vì tồn kho được nhiều đơn hàng cùng cập nhật và có vòng đời riêng.

Một số câu hỏi hữu ích khi thiết kế:

1. Những thuộc tính nào cần thay đổi nguyên tử để một quy tắc luôn đúng?
2. Ai có quyền quyết định thay đổi trạng thái của đối tượng?
3. Đối tượng con có ý nghĩa độc lập ngoài root không?
4. Hai phần dữ liệu có thường xuyên được cập nhật bởi các request khác nhau không?
5. Có thể chấp nhận trạng thái trung gian và nhất quán sau một khoảng thời gian không?
6. Nếu phải khóa hoặc tải toàn bộ nhóm dữ liệu, phạm vi đó có quá lớn không?

Không gom mọi entity có quan hệ JPA vào một aggregate duy nhất. Một aggregate quá lớn làm tăng số hàng phải tải, thời gian giữ khóa và nguy cơ hai người dùng xung đột khi sửa những phần không liên quan.

Ngược lại, không tách một quy tắc cần atomicity thành nhiều aggregate chỉ vì chúng nằm ở hai bảng khác nhau. Ranh giới nên theo nghiệp vụ và yêu cầu nhất quán, không theo số lượng bảng.

## 3. Aggregate root bảo vệ trạng thái

Một ví dụ đơn hàng đơn giản:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private long version;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status = OrderStatus.DRAFT;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal totalAmount = BigDecimal.ZERO;

    protected PurchaseOrder() {
    }

    public void addLine(
            Long productId,
            String productName,
            BigDecimal unitPrice,
            int quantity) {

        ensureDraft();

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive");
        }
        if (unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Unit price must be non-negative");
        }

        OrderLine line = new OrderLine(
            this, productId, productName, unitPrice, quantity);

        lines.add(line);
        recalculateTotal();
    }

    public void removeLine(Long lineId) {
        ensureDraft();

        boolean removed = lines.removeIf(
            line -> line.hasId(lineId));

        if (!removed) {
            throw new IllegalArgumentException("Order line not found");
        }

        recalculateTotal();
    }

    public void confirm() {
        ensureDraft();

        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "An order must contain at least one line");
        }

        status = OrderStatus.CONFIRMED;
    }

    private void ensureDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Only a draft order can be changed");
        }
    }

    private void recalculateTotal() {
        totalAmount = lines.stream()
            .map(OrderLine::subtotal)
            .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public List<OrderLine> getLines() {
        return List.copyOf(lines);
    }
}
~~~

Enum trạng thái:

~~~java
public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
~~~

Entity con:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_id", nullable = false)
    private Long productId;

    @Column(name = "product_name", nullable = false)
    private String productName;

    @Column(name = "unit_price", nullable = false,
            precision = 19, scale = 2)
    private BigDecimal unitPrice;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {
    }

    OrderLine(
            PurchaseOrder order,
            Long productId,
            String productName,
            BigDecimal unitPrice,
            int quantity) {
        this.order = order;
        this.productId = productId;
        this.productName = productName;
        this.unitPrice = unitPrice;
        this.quantity = quantity;
    }

    BigDecimal subtotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }

    boolean hasId(Long lineId) {
        return id != null && id.equals(lineId);
    }
}
~~~

Ví dụ minh họa các điểm quan trọng:

- PurchaseOrder là root; code nghiệp vụ gọi addLine, removeLine và confirm.
- OrderLine có constructor không public để hạn chế việc tạo entity con tùy tiện từ bên ngoài package.
- OrderLine giữ tham chiếu đến root và có foreign key order_id.
- Root tính lại totalAmount khi danh sách dòng thay đổi. Trường tổng tiền cũng làm trạng thái root thay đổi, giúp version của root tham gia kiểm soát cập nhật trong ví dụ này.
- getLines() trả bản sao không thể dùng để sửa trực tiếp collection nội bộ.

Đây là mô hình minh họa; dự án thực tế cần bổ sung equals/hashCode phù hợp, cách xử lý dòng mới chưa có ID, quy tắc tiền tệ, scale/rounding và các trạng thái nghiệp vụ của riêng mình. Không dùng BigDecimal với toán tử double để tính tiền.

## 4. Quan hệ JPA phải phản ánh quyền sở hữu

Trong mapping trên, OrderLine.order là phía sở hữu quan hệ vì nó chứa khóa ngoại order_id. PurchaseOrder.lines khai báo mappedBy = "order", nên đây là phía nghịch đảo.

Khi thêm dòng, root tạo OrderLine với tham chiếu this và thêm vào collection. Như vậy cả hai phía của quan hệ được đồng bộ trong bộ nhớ.

Nếu chỉ thêm dòng vào collection nghịch đảo mà không đặt OrderLine.order, Hibernate có thể không ghi foreign key như mong muốn hoặc database từ chối vì order_id null. Một helper method ở root giúp tránh lỗi quên cập nhật owning side.

**CascadeType.ALL** ở đây phù hợp vì OrderLine thuộc vòng đời của PurchaseOrder. Persist root có thể persist các dòng mới; remove root có thể remove các dòng phụ thuộc. **orphanRemoval = true** nghĩa là khi một dòng bị loại khỏi collection được quản lý, dòng đó có thể bị xóa khi flush.

Không áp dụng cascade remove từ Order sang Product chỉ vì OrderLine lưu productId. Product là đối tượng thuộc aggregate khác và có vòng đời độc lập. Tương tự, không dùng orphanRemoval cho quan hệ mà entity con cần tồn tại độc lập hoặc được chia sẻ.

## 5. Tham chiếu aggregate khác bằng ID

Thông thường, một aggregate nên tham chiếu aggregate khác bằng định danh thay vì giữ cả object graph JPA.

Ví dụ OrderLine lưu productId và một bản sao productName/unitPrice tại thời điểm đặt hàng. Order không cần tải toàn bộ Product aggregate mỗi khi đọc đơn. Giá sản phẩm có thể thay đổi sau đó nhưng đơn hàng vẫn cần giữ giá đã chốt.

Một số lợi ích:

- Giảm kích thước object graph và số join không cần thiết.
- Tránh vô tình sửa aggregate khác qua một quan hệ cascade.
- Giảm phụ thuộc giữa các module và service.
- Làm rõ aggregate nào sở hữu quy tắc cập nhật.

Khi cần thông tin hiện tại của Product, ứng dụng có thể truy vấn Product repository hoặc một read model riêng. Nếu nghiệp vụ cần kiểm tra giá hoặc tồn kho tại thời điểm đặt hàng, hãy xác định rõ bước kiểm tra và cách xử lý khi dữ liệu thay đổi giữa lúc đọc và lúc ghi.

Không phải mọi quan hệ JPA ManyToOne đều phải là tham chiếu giữa aggregate. Trong một aggregate, các entity con có thể dùng quan hệ object trực tiếp. Giữa hai aggregate, tham chiếu ID thường giúp ranh giới nhất quán rõ hơn.

## 6. Repository thường đặt ở aggregate root

Repository cung cấp cách tải và lưu aggregate. Thông thường, tạo repository cho root:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
~~~

Application service tải root rồi gọi hành vi miền:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.math.BigDecimal;

@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orderRepository;

    public OrderApplicationService(
            PurchaseOrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void addLine(
            Long orderId,
            Long productId,
            String productName,
            BigDecimal unitPrice,
            int quantity) {

        PurchaseOrder order = orderRepository.findById(orderId)
            .orElseThrow(() ->
                new IllegalArgumentException("Order not found"));

        order.addLine(productId, productName, unitPrice, quantity);
    }

    @Transactional
    public void confirm(Long orderId) {
        PurchaseOrder order = orderRepository.findById(orderId)
            .orElseThrow(() ->
                new IllegalArgumentException("Order not found"));

        order.confirm();
    }
}
~~~

Entity được tải trong transaction đang được quản lý. Khi root thay đổi, JPA dirty checking ghi nhận thay đổi và flush khi cần; không nhất thiết gọi save() lại chỉ để cập nhật entity managed.

Không cần tạo OrderLineRepository cho các thao tác thêm, sửa hoặc xóa dòng hàng thông thường nếu OrderLine chỉ được quản lý qua PurchaseOrder. Nếu cần truy vấn báo cáo hoặc tìm dòng hàng độc lập, có thể tạo query/projection riêng, nhưng đường ghi vẫn nên đi qua root để bảo vệ invariants.

Repository không nên trở thành nơi chứa toàn bộ quy tắc nghiệp vụ. Nó tải và lưu aggregate; root thực thi hành vi miền; application service điều phối use case và transaction.

## 7. Transaction boundary và một aggregate

Transaction thường bao quanh một use case ở application service:

1. Mở transaction.
2. Tải aggregate root.
3. Gọi hành vi miền để kiểm tra và thay đổi trạng thái.
4. Flush/commit.
5. Nếu có lỗi, transaction rollback.

Các quy tắc phải đúng ngay khi transaction kết thúc nên được bảo vệ trong root và/hoặc constraint ở database. Không trả root ra ngoài transaction để một controller hoặc background thread sửa trực tiếp.

Một transaction cục bộ có thể cập nhật nhiều aggregate root trong cùng database về mặt kỹ thuật. Tuy nhiên, nếu use case thường xuyên cần tải và sửa nhiều root cùng lúc, hãy xem lại ranh giới: có thể một quy tắc đang bị đặt sai aggregate, hoặc quy trình nên trở thành nhiều bước với eventual consistency.

Không nên biến nguyên tắc “mỗi transaction một aggregate” thành luật cứng cho mọi hệ thống. Hãy dùng nó như mặc định thiết kế để giảm coupling và contention; nếu nghiệp vụ thực sự yêu cầu atomic update nhiều root trong cùng database, ghi rõ lý do và kiểm thử xung đột.

## 8. Nhiều aggregate và nhất quán cuối cùng

Giả sử đặt hàng phải giữ tồn kho. Order và InventoryItem có thể là hai aggregate riêng:

- Order quản lý dòng hàng, tổng tiền và trạng thái đơn.
- InventoryItem quản lý số lượng có thể bán và reservation.
- Order không tự sửa quantity trong InventoryItem thông qua object graph.

Có hai lựa chọn tùy yêu cầu:

**Cập nhật nguyên tử trong một database:** nếu cả hai aggregate nằm trong cùng database và nghiệp vụ yêu cầu phải cùng thành công hoặc thất bại, một transaction cục bộ có thể tải và cập nhật cả hai root. Cách này tạo coupling và contention giữa hai aggregate, nên cần đánh giá tần suất cập nhật và phạm vi khóa.

**Quy trình nhiều bước:** tạo Order ở trạng thái PENDING, gửi yêu cầu giữ hàng, sau khi Inventory xác nhận thì chuyển Order sang CONFIRMED. Nếu giữ hàng thất bại, chuyển Order sang REJECTED hoặc CANCELLED. Trạng thái trung gian được biểu diễn rõ và quy trình đạt eventual consistency.

Nếu hai aggregate nằm ở hai service/database khác nhau, @Transactional của một service không thể commit nguyên tử cả hai local transaction. Hãy dùng outbox để phát sự kiện đáng tin cậy và Saga để điều phối các bước thuận/bù nếu nghiệp vụ cần.

## 9. Invariants và ràng buộc database

Root nên kiểm tra các quy tắc nghiệp vụ trước khi thay đổi trạng thái. Database constraint cung cấp lớp bảo vệ cuối cùng khi có nhiều request hoặc đường ghi khác nhau.

Ví dụ:

- NOT NULL bảo vệ trường bắt buộc.
- UNIQUE bảo vệ mã tham chiếu duy nhất.
- FOREIGN KEY bảo vệ quan hệ tham chiếu.
- CHECK có thể bảo vệ quantity lớn hơn 0 hoặc giá trị trong miền hợp lệ, tùy database.

Không phải mọi invariant đều biểu diễn được bằng một CHECK constraint. Quy tắc như “đơn đã xác nhận không được sửa dòng” cần logic trạng thái và quyền cập nhật phù hợp. Quy tắc trải qua nhiều hàng có thể cần transaction, khóa hoặc mô hình dữ liệu khác.

Nếu chỉ kiểm tra tồn kho bằng cách đọc quantity trong Java rồi ghi giá trị mới, hai transaction có thể cùng đọc một số lượng cũ. Hãy dùng optimistic/pessimistic locking hoặc UPDATE có điều kiện để thao tác kiểm tra và thay đổi được bảo vệ ở database.

## 10. Optimistic locking cho aggregate root

Có thể dùng @Version trên root để phát hiện hai transaction cùng sửa một aggregate từ cùng phiên bản:

~~~java
@Version
private long version;
~~~

Khi root được cập nhật, JPA provider thường phát UPDATE kèm điều kiện version cũ và tăng version. Nếu một transaction khác đã commit trước, cập nhật còn lại không khớp phiên bản và phát sinh lỗi optimistic locking.

Trong ví dụ PurchaseOrder, các phương thức thêm/xóa dòng đều tính lại totalAmount, vì vậy trạng thái root cũng thay đổi. Với mô hình mà chỉ entity con thay đổi và root không dirty, hãy xác minh hành vi version của provider và mapping. Nếu invariant của aggregate phụ thuộc mọi thay đổi ở entity con, cần bảo đảm thay đổi đó cũng làm tăng version root hoặc dùng cơ chế khóa phù hợp, chẳng hạn optimistic force increment.

Xử lý lỗi ở application boundary:

- Thông báo xung đột cho người gọi hoặc trả HTTP 409.
- Nếu có thể retry, mở transaction mới, tải lại root và tính lại hành vi từ trạng thái mới.
- Không tiếp tục dùng entity stale trong transaction đã rollback hoặc bị đánh dấu rollback-only.
- Không retry side effect bên ngoài nếu chưa có idempotency.

Optimistic locking phù hợp khi xung đột ghi tương đối ít. Nếu contention cao, cân nhắc pessimistic locking trên root, nhưng transaction phải ngắn và có xử lý timeout/deadlock.

## 11. Bulk update có thể phá vỡ aggregate boundary

JPQL bulk update và native SQL cập nhật trực tiếp database, bỏ qua việc gọi hành vi miền trên root. Chúng cũng có thể bỏ qua dirty checking, callback entity và đồng bộ persistence context.

Ví dụ cập nhật trực tiếp trạng thái nhiều đơn có thể bỏ qua quy tắc chỉ cho phép chuyển trạng thái từ DRAFT sang CANCELLED. Nếu dùng bulk update, cần tự thiết kế điều kiện trạng thái, version, audit, event và đồng bộ cache; không giả định các invariant của root tự được chạy.

Bulk update phù hợp cho tác vụ bảo trì hoặc thao tác hàng loạt có quy tắc rõ ràng, khi người thiết kế chủ động tái hiện các bảo đảm cần thiết. Với luồng nghiệp vụ thông thường, tải root và gọi hành vi miền là cách an toàn hơn.

## 12. Tách command model và read model

Aggregate được thiết kế để bảo vệ cập nhật, không nhất thiết là cấu trúc tối ưu cho mọi truy vấn đọc.

Một màn hình danh sách đơn hàng có thể cần customerName, totalAmount, status và số dòng. Tải toàn bộ aggregate cùng mọi quan hệ cho từng hàng có thể gây N+1 query và tải quá nhiều dữ liệu.

Có thể dùng projection:

~~~java
public interface OrderListView {
    Long getId();
    OrderStatus getStatus();
    BigDecimal getTotalAmount();
}
~~~

Hoặc DTO query riêng với JPQL/native SQL phù hợp. Read model có thể tổng hợp từ nhiều aggregate, nhưng không nên dùng read model đó để cập nhật trực tiếp trạng thái domain. Command đi qua aggregate root; query có thể tối ưu theo nhu cầu đọc.

Nếu dùng cache cho read model, cần invalidation sau commit hoặc phát event/outbox để cập nhật dữ liệu đọc. Việc thay đổi một aggregate có thể ảnh hưởng nhiều projection hoặc cache key khác nhau.

## 13. Domain event và outbox ở ranh giới aggregate

Sau một thay đổi nghiệp vụ, root hoặc application service có thể phát domain event, ví dụ OrderConfirmed. Event mô tả điều đã xảy ra; service khác có thể phản ứng để giữ tồn kho, tạo vận đơn hoặc gửi thông báo.

Nếu chỉ publish event trực tiếp sau khi gọi repository, tiến trình có thể dừng giữa database commit và publish. Để tránh mất event, ghi outbox record trong cùng transaction với thay đổi aggregate:

1. Tải Order root và gọi confirm().
2. Lưu thay đổi Order và outbox event trong cùng local transaction.
3. Commit.
4. Worker publish event từ outbox.
5. Consumer xử lý idempotent và ghi nhận event đã xử lý.

Nếu worker publish thành công nhưng dừng trước khi đánh dấu event, message có thể được gửi lại. Consumer nên dùng eventId với unique constraint/inbox để tránh áp dụng cùng hiệu ứng nghiệp vụ nhiều lần.

Outbox không làm nhiều aggregate hoặc nhiều service commit nguyên tử. Nó bảo đảm yêu cầu phát event được lưu bền vững cùng thay đổi nguồn, sau đó truyền event theo mô hình có thể lặp.

## 14. Kiểm thử aggregate và ranh giới cập nhật

Nên kiểm thử cả hành vi miền lẫn persistence mapping.

**Unit test cho root** không cần database:

- Không cho thêm dòng khi đơn đã xác nhận.
- Từ chối quantity bằng 0 hoặc âm.
- Từ chối xác nhận đơn rỗng.
- Tổng tiền thay đổi đúng khi thêm hoặc xóa dòng.
- Không cho xóa dòng không thuộc đơn.

**Repository/integration test** dùng @DataJpaTest:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class PurchaseOrderRepositoryTest {

    @Autowired
    private PurchaseOrderRepository orderRepository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void rootPersistsAndRemovesItsLines() {
        PurchaseOrder order = new PurchaseOrder();
        order.addLine(
            10L, "Keyboard", new BigDecimal("25.00"), 2);

        PurchaseOrder saved = orderRepository.save(order);
        entityManager.flush();
        Long orderId = saved.getId();

        entityManager.clear();

        PurchaseOrder loaded =
            orderRepository.findById(orderId).orElseThrow();

        assertThat(loaded.getLines()).hasSize(1);
        assertThat(loaded.getTotalAmount())
            .isEqualByComparingTo("50.00");
    }
}
~~~

Ví dụ tập trung vào cascade persist, owning side, reload sau clear và tổng tiền. Nếu muốn kiểm thử orphanRemoval, tải root, xóa một dòng qua root method, flush/clear rồi xác nhận dòng đó không còn trong database.

Các bài test quan trọng khác:

- Constraint database từ chối dữ liệu không hợp lệ.
- Hai transaction cùng cập nhật một root; một transaction nhận optimistic locking conflict.
- Sửa entity con qua root làm thay đổi version root theo thiết kế.
- Query projection không tải toàn bộ aggregate.
- Bulk update có điều kiện không phá invariant.
- Outbox event chỉ tồn tại khi transaction nghiệp vụ commit.
- Consumer xử lý event trùng an toàn.

Dùng Testcontainers hoặc database cùng loại production cho test locking, isolation, constraint và native query có phụ thuộc dialect. H2 có thể phù hợp cho test nhanh nhưng không thay thế được mọi hành vi của database triển khai.

## 15. Lỗi thiết kế thường gặp

1. **Aggregate quá lớn:** tải nhiều entity, khóa lâu và tạo xung đột giữa các thay đổi không liên quan.
2. **Cho phép sửa entity con trực tiếp:** bỏ qua invariant mà root phải bảo vệ.
3. **Đặt repository cho mọi entity con:** khiến code bên ngoài dễ cập nhật child mà không qua root.
4. **Cascade ALL sang aggregate khác:** vô tình kéo dài hoặc xóa vòng đời của đối tượng độc lập.
5. **Dùng quan hệ JPA cho mọi tham chiếu:** tạo object graph lớn và coupling không cần thiết; cân nhắc tham chiếu bằng ID giữa các aggregate.
6. **Coi @Transactional là bảo đảm nhất quán nhiều service:** transaction cục bộ chỉ bảo vệ resource được transaction manager quản lý.
7. **Chỉ kiểm tra version ở child:** có thể không bảo vệ invariant đặt ở root nếu root không được đánh dấu dirty hoặc khóa phù hợp.
8. **Dùng bulk update cho command nghiệp vụ:** bỏ qua hành vi miền, callback và một số cơ chế concurrency.
9. **Dùng aggregate làm read model cho mọi màn hình:** dễ gây N+1 và tải dữ liệu dư thừa.
10. **Phát event không bền vững:** database commit nhưng message bị mất nếu tiến trình dừng trước khi publish.

## 16. Quy trình thiết kế thực tế

Khi thêm một use case mới, có thể đi theo thứ tự:

1. Viết rõ các invariants phải đúng khi transaction kết thúc.
2. Xác định entity nào sở hữu và bảo vệ từng invariant.
3. Chọn root và giới hạn entity/value object nằm trong aggregate.
4. Thiết kế phương thức miền để mọi thay đổi đi qua root.
5. Mapping JPA theo vòng đời thật: owning side, cascade và orphanRemoval chỉ khi phù hợp.
6. Tạo repository cho root và đặt transaction ở application service.
7. Xác định quy tắc concurrency: @Version, lock hoặc UPDATE có điều kiện.
8. Với nghiệp vụ qua nhiều aggregate/service, chọn local transaction, outbox hoặc Saga và mô tả trạng thái trung gian.
9. Tách read model khỏi command model khi nhu cầu truy vấn khác với cấu trúc aggregate.
10. Viết unit test cho invariants và integration test cho mapping, transaction, concurrency.

Một aggregate tốt giữ những quy tắc cần nhất quán cùng nhau trong một ranh giới cập nhật có thể quản lý. Spring Data JPA cung cấp entity lifecycle, transaction và locking để triển khai ranh giới đó; DDD giúp quyết định dữ liệu nào nên thuộc cùng root và khi nào cần phối hợp bằng event hoặc compensation.