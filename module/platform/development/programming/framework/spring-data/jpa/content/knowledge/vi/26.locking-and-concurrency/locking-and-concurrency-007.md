# Khóa quan hệ và giới hạn phạm vi bảo vệ

Trong JPA, khóa một entity không đồng nghĩa với khóa toàn bộ object graph mà entity tham chiếu. Phạm vi bảo vệ phụ thuộc vào **loại khóa**, **bên sở hữu quan hệ**, **vị trí khóa ngoại hoặc bảng nối** và **lock scope** mà persistence provider áp dụng.

Khi dùng Spring Data JPA, ta thường đặt lock mode trên phương thức repository bằng **@Lock**. Với khóa bi quan, Jakarta Persistence còn cho phép chọn phạm vi **NORMAL** hoặc **EXTENDED** qua thuộc tính **jakarta.persistence.lock.scope**.

Cần phân biệt hai câu hỏi:

- **Lock mode**: giao dịch yêu cầu kiểu bảo vệ nào, chẳng hạn đọc có khóa hay ghi độc quyền?
- **Lock scope**: khi khóa một entity bằng khóa bi quan, phạm vi có mở rộng tới bảng nối hoặc bảng collection của các quan hệ mà entity sở hữu hay không?

Hai cấu hình này phối hợp với nhau nhưng không thay thế nhau.

## 1. Các loại khóa trong JPA

JPA hỗ trợ khóa lạc quan và khóa bi quan. Chúng giải quyết xung đột đồng thời theo cách khác nhau.

### 1.1. Khóa lạc quan

Khóa lạc quan thường dùng trường phiên bản được đánh dấu bằng **@Version**:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Inventory {

    @Id
    private Long id;

    private int availableQuantity;

    @Version
    private long version;

    protected Inventory() {
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (availableQuantity < quantity) {
            throw new IllegalStateException("insufficient inventory");
        }
        availableQuantity -= quantity;
    }
}
~~~

Khi cập nhật entity, JPA sử dụng giá trị version hiện tại trong điều kiện UPDATE. Về mặt khái niệm, câu lệnh có dạng:

~~~sql
UPDATE inventory
   SET available_quantity = ?, version = version + 1
 WHERE id = ?
   AND version = ?;
~~~

Nếu một giao dịch khác đã cập nhật bản ghi và tăng version, câu UPDATE của giao dịch hiện tại không còn khớp version cũ. Provider phát hiện xung đột và ném **OptimisticLockException** hoặc exception Spring được dịch tương ứng.

Khóa lạc quan không giữ row lock trong suốt thời gian đọc và xử lý nghiệp vụ. Nó phát hiện xung đột khi kiểm tra version, thường trong flush hoặc commit. Cách này phù hợp khi xung đột không thường xuyên và giao dịch tương đối ngắn.

### 1.2. Khóa bi quan

Khóa bi quan yêu cầu database bảo vệ bản ghi ngay khi giao dịch lấy khóa. JPA định nghĩa các mode thường dùng:

| Lock mode | Ý nghĩa |
|---|---|
| **PESSIMISTIC_READ** | Yêu cầu khóa cho phép đọc đồng thời nhưng ngăn giao dịch khác cập nhật hoặc xóa entity đang bị khóa |
| **PESSIMISTIC_WRITE** | Yêu cầu khóa độc quyền để giao dịch khác không thể cập nhật hoặc xóa entity cho đến khi giao dịch giữ khóa kết thúc |
| **PESSIMISTIC_FORCE_INCREMENT** | Khóa bi quan kiểu ghi và buộc tăng version của entity có trường @Version |
| **OPTIMISTIC** | Yêu cầu kiểm tra version theo cơ chế khóa lạc quan |
| **OPTIMISTIC_FORCE_INCREMENT** | Kiểm tra lạc quan và buộc tăng version |

Với mode bi quan, khóa được giữ đến khi transaction commit hoặc rollback. Một phương thức repository trả về entity không có nghĩa là khóa được giải phóng ngay khi phương thức đó kết thúc nếu nó đang tham gia transaction rộng hơn.

Các tên **READ** và **WRITE** cũ trong LockModeType là bí danh của mode lạc quan. Khi đọc code, nên dùng tên **OPTIMISTIC** và **OPTIMISTIC_FORCE_INCREMENT** để tránh nhầm chúng với **PESSIMISTIC_READ** và **PESSIMISTIC_WRITE**.

## 2. Dùng @Lock trong Spring Data JPA

Spring Data JPA cho phép gắn lock mode trực tiếp lên query method bằng **@Lock**:

~~~java
import jakarta.persistence.LockModeType;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends JpaRepository<Inventory, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select i from Inventory i where i.id = :id")
    Optional<Inventory> findForUpdate(@Param("id") Long id);
}
~~~

Khi gọi **findForUpdate**, Spring Data JPA yêu cầu provider thực thi truy vấn với mode **PESSIMISTIC_WRITE**. Provider chuyển yêu cầu đó thành cơ chế khóa phù hợp với database đang dùng.

### 2.1. Khóa phải nằm trong transaction

Các lock mode khác **NONE** cần một transaction đang hoạt động và EntityManager phải tham gia transaction đó. Nếu yêu cầu khóa khi không có transaction, JPA có thể ném **TransactionRequiredException**.

Nên đặt ranh giới transaction tại service điều phối việc đọc, kiểm tra và cập nhật:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final InventoryRepository inventories;

    public InventoryService(InventoryRepository inventories) {
        this.inventories = inventories;
    }

    @Transactional
    public void reserve(Long id, int quantity) {
        Inventory inventory = inventories.findForUpdate(id)
            .orElseThrow(() -> new IllegalArgumentException("inventory not found"));

        inventory.reserve(quantity);
    }
}
~~~

Trong ví dụ, truy vấn lấy khóa, kiểm tra số lượng và thay đổi entity cùng nằm trong một transaction. Khóa được giữ cho đến khi transaction hoàn tất. Nếu chỉ đánh dấu một phương thức repository có lock nhưng gọi nó ngoài transaction, thao tác có thể thất bại.

Không nên giữ khóa trong lúc gọi HTTP, chờ người dùng hoặc thực hiện tác vụ chậm không cần thiết. Transaction càng dài thì các giao dịch khác càng phải chờ và nguy cơ deadlock càng tăng.

## 3. Quan hệ entity và bên sở hữu quan hệ

Muốn hiểu một khóa có bảo vệ quan hệ đến đâu, trước hết phải xác định **owning side**. Trong JPA, bên sở hữu quan hệ là bên điều khiển mapping của khóa ngoại hoặc bảng nối. Bên có **mappedBy** là inverse side.

Ví dụ một đơn hàng có khách hàng, các nhãn và các dòng hàng:

~~~java
@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    // FK customer_id nằm trong bảng purchase_order.
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    // PurchaseOrder sở hữu bảng nối purchase_order_tag.
    @ManyToMany
    @JoinTable(
        name = "purchase_order_tag",
        joinColumns = @JoinColumn(name = "order_id"),
        inverseJoinColumns = @JoinColumn(name = "tag_id")
    )
    private Set<OrderTag> tags = new HashSet<>();

    // FK order_id nằm trong bảng order_line.
    // OrderLine là owning side vì PurchaseOrder dùng mappedBy.
    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

Trong mapping trên:

- **ManyToOne customer**: bảng purchase_order chứa cột customer_id. PurchaseOrder là owning side của quan hệ này.
- **ManyToMany tags**: PurchaseOrder khai báo @JoinTable nên là owning side của bảng purchase_order_tag.
- **OneToMany lines**: PurchaseOrder khai báo mappedBy = "order". Khóa ngoại order_id nằm trong bảng order_line và do OrderLine quản lý.

Việc một entity có getter trả về collection không có nghĩa là nó sở hữu các hàng trong bảng quan hệ. Hãy xem mapping và vị trí khóa ngoại thực tế để xác định lock scope.

## 4. Pessimistic lock scope: NORMAL và EXTENDED

Jakarta Persistence định nghĩa thuộc tính **jakarta.persistence.lock.scope** cho khóa bi quan. Giá trị enum mặc định là **PessimisticLockScope.NORMAL**; **PessimisticLockScope.EXTENDED** mở rộng phạm vi khóa tới một số bảng quan hệ thuộc entity.

### 4.1. NORMAL — phạm vi mặc định

Với **NORMAL**, provider phải khóa các hàng thuộc bảng chính và bảng phụ ánh xạ trạng thái không phải collection của entity. Nếu dùng joined inheritance, các hàng tương ứng trong bảng của lớp cha cũng thuộc phạm vi.

Các quan hệ mà entity đang khóa chứa khóa ngoại cũng được bảo vệ cùng trạng thái của entity. Tuy nhiên, điều đó **không khóa trạng thái của entity được tham chiếu**.

Ví dụ, khóa PurchaseOrder:

- Hàng của purchase_order được khóa, bao gồm cột customer_id nằm trên hàng đó.
- Hàng của Customer được tham chiếu không tự động bị khóa.
- Các quan hệ dùng join table và element collection không được mở rộng khóa theo mặc định.
- Với OneToMany mappedBy, khóa ngoại nằm trong bảng OrderLine; khóa PurchaseOrder không tự động khóa các hàng OrderLine.

NORMAL phù hợp khi invariant nghiệp vụ chỉ cần bảo vệ trạng thái của entity gốc và các cột quan hệ được lưu ngay trên hàng của entity đó.

### 4.2. EXTENDED — mở rộng tới bảng quan hệ thuộc entity

Với **PessimisticLockScope.EXTENDED**, provider giữ toàn bộ phạm vi NORMAL và mở rộng thêm tới:

- Các hàng trong join table của quan hệ do entity sở hữu.
- Các hàng trong collection table của các element collection thuộc entity.

Đối với PurchaseOrder ở ví dụ trên:

- Hàng purchase_order vẫn được khóa.
- Các hàng quan hệ hiện có trong purchase_order_tag được đưa vào phạm vi khóa vì PurchaseOrder sở hữu join table.
- Các hàng Customer và OrderTag không tự động bị khóa.
- Các hàng OrderLine không tự động được khóa chỉ vì PurchaseOrder có collection lines với mappedBy; khóa ngoại nằm ở bảng OrderLine và quan hệ không do PurchaseOrder sở hữu.

**EXTENDED không có nghĩa là khóa tất cả entity trong object graph.** Nó mở rộng phạm vi tới các hàng bảng nối và bảng collection phù hợp; trạng thái của entity được tham chiếu vẫn cần được khóa riêng nếu nghiệp vụ yêu cầu.

### 4.3. Bảng so sánh phạm vi

| Thành phần dữ liệu của PurchaseOrder | NORMAL | EXTENDED |
|---|---|---|
| Hàng purchase_order | Có | Có |
| Bảng phụ của PurchaseOrder | Có | Có |
| Cột customer_id nằm trên purchase_order | Thuộc hàng được khóa | Thuộc hàng được khóa |
| Hàng của Customer được tham chiếu | Không tự động | Không tự động |
| Hàng purchase_order_tag do PurchaseOrder sở hữu | Không mở rộng tới join table | Có |
| Hàng của OrderTag được tham chiếu | Không tự động | Không tự động |
| Hàng collection table của @ElementCollection | Không | Có |
| Hàng order_line với quan hệ mappedBy ở PurchaseOrder | Không tự động | Không tự động |

### 4.4. EXTENDED vẫn có thể xuất hiện phantom

Khi khóa một quan hệ hoặc element collection bằng EXTENDED, provider thường chỉ khóa các hàng hiện có trong join table hoặc collection table. Những hàng mới có thể được thêm vào phạm vi truy vấn trong thời gian giao dịch đang chạy. Hiện tượng này được gọi là **phantom**.

Vì vậy, EXTENDED không tương đương với việc khóa tuyệt đối toàn bộ collection hoặc bảo đảm không ai có thể thêm thành viên mới. Nếu invariant yêu cầu bảo vệ cả việc thêm/xóa quan hệ, cần thiết kế thêm cơ chế phù hợp, chẳng hạn khóa rõ ràng các entity con, cập nhật version của aggregate root theo một quy ước thống nhất, constraint database hoặc isolation level phù hợp.

## 5. Đặt lock scope bằng query hint

Spring Data JPA cho phép gắn JPA query hint lên repository method bằng **@QueryHints**. Để yêu cầu EXTENDED, dùng đúng tên property Jakarta Persistence:

~~~java
import jakarta.persistence.LockModeType;
import jakarta.persistence.QueryHint;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.QueryHints;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @QueryHints(
        @QueryHint(
            name = "jakarta.persistence.lock.scope",
            value = "EXTENDED"
        )
    )
    @Query("select o from PurchaseOrder o where o.id = :id")
    Optional<PurchaseOrder> findForUpdateWithExtendedScope(
        @Param("id") Long id
    );
}
~~~

Ở đây có hai cấu hình độc lập:

- **@Lock(PESSIMISTIC_WRITE)** yêu cầu khóa ghi bi quan trên entity được truy vấn.
- **jakarta.persistence.lock.scope = EXTENDED** mở rộng phạm vi khóa tới join table và collection table thuộc entity theo quy tắc JPA.

Nếu bỏ query hint, provider dùng phạm vi mặc định NORMAL. Nếu chỉ đặt EXTENDED mà không yêu cầu khóa bi quan, scope này không tạo ra khóa; nó chỉ điều chỉnh phạm vi của một pessimistic lock.

Có thể khai báo thêm lock timeout bằng query hint:

~~~java
@QueryHints({
    @QueryHint(
        name = "jakarta.persistence.lock.scope",
        value = "EXTENDED"
    ),
    @QueryHint(
        name = "jakarta.persistence.lock.timeout",
        value = "3000"
    )
})
~~~

Giá trị **3000** là 3.000 mili giây theo quy ước của lock timeout hint. Khả năng thực thi và cách diễn giải vẫn phụ thuộc JPA provider, JDBC driver và database. Hãy kiểm thử trên database triển khai; query hint không bảo đảm mọi hệ thống sẽ ngắt chờ khóa chính xác tại thời điểm đó.

Với ứng dụng dùng JPA cũ thuộc namespace **javax.persistence**, tên property tương ứng là **javax.persistence.lock.scope** và import phải theo namespace của phiên bản đang dùng. Không trộn javax và jakarta trong cùng một ứng dụng.

## 6. Phạm vi khóa không phải phạm vi tải dữ liệu

Lock scope và fetch plan giải quyết hai vấn đề khác nhau:

- **FetchType.LAZY/EAGER**, JOIN FETCH và EntityGraph quyết định dữ liệu quan hệ nào được tải.
- **LockModeType** và lock scope quyết định những hàng nào cần được bảo vệ bởi khóa.

Một association được fetch không mặc nhiên đồng nghĩa là toàn bộ entity liên quan đã được khóa theo cách ứng dụng mong muốn. Tương tự, đặt EXTENDED không yêu cầu provider tải mọi association vào bộ nhớ.

Nếu nghiệp vụ cần khóa cả PurchaseOrder và Customer, hãy yêu cầu khóa Customer một cách rõ ràng trong cùng transaction, hoặc thiết kế truy vấn có lock mode áp dụng tới entity cần bảo vệ. Đừng suy luận rằng khóa root tự lan truyền tới mọi entity được tham chiếu.

## 7. Chọn chiến lược bảo vệ theo invariant nghiệp vụ

Hãy xác định điều gì cần đúng trong suốt transaction trước khi chọn lock mode và scope.

| Invariant | Chiến lược thường phù hợp |
|---|---|
| Không cho hai giao dịch cùng cập nhật một hàng tồn kho | PESSIMISTIC_WRITE trên Inventory hoặc @Version với xử lý retry |
| Không cho sửa trạng thái của một đơn hàng đang được xử lý | PESSIMISTIC_WRITE trên PurchaseOrder |
| Cần bảo vệ các hàng join table hiện có của quan hệ sở hữu | PESSIMISTIC lock với scope EXTENDED |
| Cần bảo vệ trạng thái của Customer được tham chiếu | Khóa Customer riêng trong cùng transaction |
| Cần bảo vệ các dòng OrderLine có FK ở bảng con | Khóa các OrderLine cần thiết hoặc thiết kế quy tắc aggregate/constraint |
| Cần ngăn hai bản ghi có cùng mã nghiệp vụ | UNIQUE constraint ở database; lock không thay thế constraint |
| Xung đột hiếm và muốn phát hiện khi ghi | @Version và optimistic locking |

Không dùng khóa bi quan để thay thế constraint. Ví dụ, kiểm tra “mã đơn hàng chưa tồn tại” rồi insert vẫn có thể gặp race condition nếu hai transaction chạy đồng thời. UNIQUE constraint mới là bảo vệ cuối cùng ở database.

## 8. Timeout, lỗi khóa và deadlock

Khóa bi quan có thể khiến transaction phải chờ một transaction khác giải phóng khóa. Các lỗi thường gặp:

- **PessimisticLockException**: lỗi lấy khóa làm transaction bị rollback.
- **LockTimeoutException**: thao tác lấy khóa hết thời gian chờ và chỉ statement bị rollback theo phân loại của JPA provider.
- **TransactionRequiredException**: yêu cầu lock mode khác NONE khi không có transaction đang hoạt động.
- **Deadlock**: hai hoặc nhiều transaction giữ các khóa khác nhau rồi chờ lẫn nhau.

Cách giảm rủi ro:

1. Giữ transaction ngắn và không gọi dịch vụ bên ngoài khi đang giữ khóa.
2. Khóa nhiều entity theo một thứ tự nhất quán giữa các luồng xử lý.
3. Chỉ khóa những entity và quan hệ cần cho invariant.
4. Đặt lock timeout phù hợp với SLA và kiểm tra hỗ trợ của database.
5. Với lỗi deadlock hoặc timeout có thể thử lại, hãy retry trong transaction mới; không tiếp tục sử dụng transaction đã rollback.
6. Theo dõi thời gian chờ khóa, số lần deadlock và các truy vấn giữ khóa lâu.

JPA không quy định chính xác provider phải dùng câu SQL hay cơ chế database nào để lấy khóa. Provider hoặc database có thể khóa nhiều hàng hơn phạm vi mà ứng dụng yêu cầu. Vì vậy, cần kiểm tra SQL và hành vi thực tế của database đang triển khai.

## 9. Ví dụ hoàn chỉnh: khóa đơn hàng cùng phạm vi quan hệ

Giả sử một nghiệp vụ duyệt đơn hàng cần bảo đảm không có transaction khác đồng thời thay đổi đơn hàng và các liên kết tag hiện có trong bảng nối. Repository có thể khai báo:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @QueryHints(
        @QueryHint(
            name = "jakarta.persistence.lock.scope",
            value = "EXTENDED"
        )
    )
    @Query("select o from PurchaseOrder o where o.id = :id")
    Optional<PurchaseOrder> findForApproval(@Param("id") Long id);
}
~~~

Service điều phối toàn bộ nghiệp vụ trong transaction:

~~~java
@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository orders;

    public PurchaseOrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void approve(Long orderId) {
        PurchaseOrder order = orders.findForApproval(orderId)
            .orElseThrow(() ->
                new IllegalArgumentException("order not found")
            );

        if (order.isApproved()) {
            return;
        }

        order.approve();
    }
}
~~~

Trong trường hợp này, transaction yêu cầu khóa ghi trên PurchaseOrder và EXTENDED scope cho các join table/collection table thuộc đơn hàng. Các entity Customer, OrderTag và OrderLine không tự động được khóa chỉ vì chúng được tham chiếu hoặc xuất hiện trong object graph. Nếu quy trình duyệt cần bảo vệ trạng thái của một trong các entity đó, hãy bổ sung thao tác khóa tương ứng.

Mã trên là ví dụ tích hợp trong ứng dụng Spring Boot đã cấu hình JPA, datasource, entity mapping và transaction manager; các import, enum trạng thái và phương thức nghiệp vụ phụ thuộc domain thực tế.

## 10. Kiểm thử phạm vi khóa

Nên kiểm thử bằng hai transaction độc lập và database tương ứng production. Một test chỉ gọi một repository method trong một transaction đơn lẻ không chứng minh được giao dịch thứ hai thực sự bị chặn.

Kịch bản kiểm thử:

1. Transaction A gọi phương thức repository có PESSIMISTIC_WRITE và giữ transaction mở.
2. Transaction B thử cập nhật hoặc xóa cùng entity; xác nhận thao tác phải chờ hoặc thất bại theo lock timeout.
3. Transaction A commit hoặc rollback.
4. Xác nhận Transaction B có thể tiếp tục sau khi khóa được giải phóng.
5. Lặp lại với association dùng join table và EXTENDED để kiểm tra các hàng liên kết.
6. Thử thay đổi hàng Customer hoặc OrderTag được tham chiếu để xác nhận entity đó không tự động nằm trong phạm vi khóa.
7. Thử thêm một liên kết mới trong lúc transaction A đang giữ khóa để kiểm tra khả năng xuất hiện phantom.
8. Kiểm tra trường hợp OneToMany mappedBy, trong đó FK nằm ở bảng con.

Khi viết test đồng thời, dùng latch/barrier hoặc cơ chế đồng bộ rõ ràng để kiểm soát thời điểm transaction A và B chạy. Tránh dùng sleep tùy ý vì test có thể chập chờn trên CI. Có thể đặt lock timeout ngắn trong test để xác nhận hành vi chờ khóa, nhưng cần biết database và driver có hỗ trợ hint đó.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| Khóa PurchaseOrder là khóa luôn Customer | NORMAL khóa hàng của PurchaseOrder; trạng thái Customer không tự động được khóa |
| EXTENDED khóa tất cả entity trong object graph | EXTENDED mở rộng tới join table và collection table thuộc entity, không tự khóa các entity được tham chiếu |
| EXTENDED ngăn mọi thay đổi thành viên collection | Các hàng join/collection table được khóa nhưng phantom vẫn có thể xảy ra |
| OneToMany mappedBy luôn được khóa khi khóa parent | FK nằm ở bảng con; cần khóa các entity con nếu nghiệp vụ yêu cầu |
| @Lock tự tạo transaction | Lock mode khác NONE cần transaction đang hoạt động |
| Lock scope quyết định association nào được fetch | Fetch plan và lock scope là hai cơ chế riêng |
| PESSIMISTIC_WRITE bảo vệ mọi quy tắc nghiệp vụ | Nó bảo vệ các hàng được khóa; UNIQUE, FK, CHECK vẫn cần constraint database |
| Provider luôn khóa đúng duy nhất hàng được chọn | Database/provider có thể khóa thêm hàng tùy cách triển khai |
| Có thể tiếp tục dùng transaction sau deadlock/lock failure | Transaction có thể đã rollback; retry cần transaction mới |

## 12. Checklist triển khai

- [ ] Đã xác định invariant nghiệp vụ và entity cần khóa.
- [ ] Đã xác định owning side, mappedBy, vị trí foreign key và join table.
- [ ] Đã chọn lock mode: optimistic hoặc một trong các PESSIMISTIC_* phù hợp.
- [ ] Nếu dùng khóa bi quan, repository method được gọi trong transaction đang hoạt động.
- [ ] Chỉ dùng EXTENDED khi cần khóa join table/collection table thuộc entity.
- [ ] Đã khóa riêng entity được tham chiếu nếu nghiệp vụ cần bảo vệ trạng thái của entity đó.
- [ ] Đã đánh giá phantom và constraint database cho quy tắc toàn vẹn.
- [ ] Đã kiểm tra timeout, deadlock và khả năng retry trong transaction mới.
- [ ] Integration test có hai transaction độc lập trên database phù hợp.
- [ ] Đã kiểm tra SQL và phạm vi khóa thực tế của JPA provider/database.

## 13. Ghi nhớ

**@Lock** xác định lock mode của query; **jakarta.persistence.lock.scope** xác định phạm vi của pessimistic lock. **NORMAL** bảo vệ hàng của entity và các bảng trạng thái liên quan theo quy tắc JPA. **EXTENDED** bổ sung hàng join table của association do entity sở hữu và hàng collection table, nhưng không tự khóa các entity được tham chiếu và không loại bỏ khả năng phantom.

Muốn bảo vệ đúng nghiệp vụ, hãy bắt đầu từ vị trí khóa ngoại và owning side, xác định các hàng thực sự tham gia invariant, sau đó khóa trong transaction ngắn. Dùng version hoặc constraint database cho những quy tắc mà row lock và lock scope không thể bảo đảm.

## Tài liệu tham khảo

- [Jakarta Persistence 3.2 — Locking and concurrency](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html)
- [Jakarta Persistence API — PessimisticLockScope](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/pessimisticlockscope)
- [Spring Data JPA — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html)
- [Spring Data JPA — Query methods and query hints](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)

