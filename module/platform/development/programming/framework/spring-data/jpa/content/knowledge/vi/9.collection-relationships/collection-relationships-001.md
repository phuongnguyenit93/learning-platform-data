# Ánh xạ một-nhiều bằng @OneToMany

## 1. Quan hệ một-nhiều là gì?

Quan hệ một-nhiều (one-to-many) biểu diễn một Entity cha có thể liên kết với nhiều Entity con. Ví dụ, một `PurchaseOrder` có nhiều `PurchaseOrderItem`; mỗi item thuộc về một đơn hàng. Ở mô hình quan hệ, khóa ngoại thường nằm ở bảng con:

```text
purchase_order
  id
  order_number

purchase_order_item
  id
  purchase_order_id  -> purchase_order.id
  product_code
  quantity
```

Trong Java, phía cha thường khai báo collection bằng `@OneToMany`. Nếu cần điều hướng ngược từ con về cha, Entity con khai báo `@ManyToOne`. `@OneToMany` mô tả collection; nó không tự quyết định cascade, cách xóa con, thứ tự phần tử hoặc cách tải dữ liệu. Những hành vi đó cần được thiết kế riêng.

## 2. Mapping hai hướng phổ biến: ManyToOne sở hữu khóa ngoại

Với schema có `purchase_order_item.purchase_order_id`, mẫu thường dùng là quan hệ hai hướng. Entity con giữ thuộc tính `purchaseOrder` và `@JoinColumn`, do đó phía ManyToOne là owning side. Collection ở Entity cha dùng `mappedBy` để chỉ ra thuộc tính sở hữu:

```java
import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;

    @Column(name = "order_number", nullable = false, unique = true)
    private String orderNumber;

    @OneToMany(
        mappedBy = "purchaseOrder",
        cascade = {CascadeType.PERSIST, CascadeType.MERGE},
        orphanRemoval = true
    )
    private List<PurchaseOrderItem> items = new ArrayList<>();

    public void addItem(PurchaseOrderItem item) {
        items.add(item);
        item.setPurchaseOrder(this);
    }

    public void removeItem(PurchaseOrderItem item) {
        if (items.remove(item)) {
            item.setPurchaseOrder(null);
        }
    }
}
```

```java
@Entity
@Table(name = "purchase_order_item")
public class PurchaseOrderItem {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "purchase_order_id", nullable = false)
    private PurchaseOrder purchaseOrder;

    @Column(name = "product_code", nullable = false)
    private String productCode;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    public void setPurchaseOrder(PurchaseOrder purchaseOrder) {
        this.purchaseOrder = purchaseOrder;
    }
}
```

Đây là các phần mapping cốt lõi; trong ứng dụng thực tế hãy bổ sung constructor, getter và các thao tác nghiệp vụ cần thiết. `mappedBy = "purchaseOrder"` phải trùng chính xác tên thuộc tính Java trong `PurchaseOrderItem`, không phải tên cột `purchase_order_id`. `@JoinColumn` đặt tên cột vật lý chứa khóa ngoại.

## 3. Vì sao ManyToOne là owning side?

Trong quan hệ hai hướng này, bảng `purchase_order_item` lưu `purchase_order_id`. Vì vậy Hibernate cần biết giá trị thuộc tính `PurchaseOrderItem.purchaseOrder` để ghi hoặc thay đổi khóa ngoại. Collection `PurchaseOrder.items` có `mappedBy`, nên là inverse side.

Khi lưu quan hệ, phải gán phía sở hữu:

```java
PurchaseOrder order = entityManager.find(PurchaseOrder.class, orderId);
PurchaseOrderItem item = new PurchaseOrderItem();
item.setProductCode("P-100");
item.setQuantity(2);
order.addItem(item);
```

Helper `addItem` vừa thêm item vào collection trong bộ nhớ, vừa gán `item.purchaseOrder`. Nhờ cascade PERSIST, khi `order` đang managed và transaction commit, item mới có thể được persist cùng cha. Nếu không dùng cascade, cần persist item riêng. Chỉ thêm vào `order.getItems()` mà không gán `item.purchaseOrder` có thể khiến khóa ngoại không được cập nhật như mong muốn.

Đối với quan hệ hai hướng, JPA không tự đồng bộ hai thuộc tính Java. Helper method nên là nơi duy nhất thêm/bỏ liên kết để tránh trạng thái một phía đã đổi còn phía kia chưa đổi.

## 4. Mapping một chiều bằng @OneToMany

Nếu chỉ cần truy cập từ cha tới con, có thể khai báo OneToMany đơn hướng mà không có thuộc tính ManyToOne trong Entity con. Cần hiểu cách JPA ánh xạ quan hệ này xuống schema.

**Mặc định dùng join table:**

```java
@OneToMany
@JoinTable(
    name = "purchase_order_item_link",
    joinColumns = @JoinColumn(name = "purchase_order_id"),
    inverseJoinColumns = @JoinColumn(name = "item_id", unique = true)
)
private List<PurchaseOrderItem> items = new ArrayList<>();
```

Join table chứa hai khóa ngoại và biểu diễn liên kết cha-con. Đây là cấu trúc mặc định thường gặp của OneToMany đơn hướng khi không khai báo join column.

**Dùng khóa ngoại ở bảng con:**

```java
@OneToMany
@JoinColumn(name = "purchase_order_id")
private List<PurchaseOrderItem> items = new ArrayList<>();
```

Ở dạng này, collection là phía sở hữu liên kết và cột `purchase_order_id` nằm trên bảng con. Entity con không cần thuộc tính tham chiếu ngược. Cần kiểm tra DDL và SQL do provider sinh ra, vì thao tác thêm con có thể gồm các lệnh insert/update tùy mapping và provider. Nếu nghiệp vụ thường xuyên cần đi từ item về đơn hàng, quan hệ hai hướng với ManyToOne thường diễn đạt mô hình rõ ràng hơn.

## 5. Chọn cascade theo vòng đời Entity con

Không có cascade nào được bật mặc định. Các cascade thường dùng:

| Cascade | Tác dụng với collection OneToMany |
| --- | --- |
| `PERSIST` | Persist các con mới khi persist cha |
| `MERGE` | Merge các con liên quan khi merge cha |
| `REMOVE` | Xóa các con khi xóa cha |
| `REFRESH` | Refresh các con khi refresh cha |
| `DETACH` | Detach các con khi detach cha |
| `ALL` | Bao gồm tất cả các loại trên |

Chỉ bật cascade theo quan hệ vòng đời. Nếu `PurchaseOrderItem` chỉ tồn tại như một phần của đơn hàng, cascade PERSIST/MERGE có thể hợp lý. Nếu con được chia sẻ hoặc có thể tồn tại độc lập, không nên tự động cascade REMOVE chỉ vì nó đang xuất hiện trong collection.

`cascade = ALL` rất tiện cho aggregate nhỏ, nhưng có thể làm một thao tác trên cha lan sang nhiều Entity hơn dự kiến. Hãy chọn từng loại cascade và xem xét tất cả luồng xóa, cập nhật, import và đồng bộ dữ liệu.

## 6. orphanRemoval khác cascade REMOVE

`orphanRemoval = true` yêu cầu provider xóa Entity con khi nó bị loại khỏi quan hệ OneToMany hoặc OneToOne thích hợp. Ví dụ, khi item bị bỏ khỏi `PurchaseOrder.items`, item trở thành orphan và sẽ bị xóa ở lần flush phù hợp.

Điều này khác cascade REMOVE:

- `cascade = REMOVE` lan thao tác xóa từ cha sang con khi cha bị xóa.
- `orphanRemoval = true` xử lý con bị tách khỏi quan hệ, kể cả khi cha vẫn còn.

Với ví dụ trên, `removeItem` bỏ item khỏi collection và đặt tham chiếu cha về null để giữ object graph nhất quán. Vì mapping dùng orphanRemoval, item được đánh dấu xóa khi flush. Mẫu này chỉ phù hợp khi item thực sự thuộc quyền sở hữu vòng đời của đơn hàng. Nếu chỉ muốn bỏ liên kết mà vẫn giữ item, không dùng orphanRemoval và thiết kế khóa ngoại nullable hoặc quy tắc chuyển item sang cha khác.

Không nhầm orphanRemoval với việc database tự xóa theo `ON DELETE CASCADE`. Orphan removal là ngữ nghĩa vòng đời ở ORM; ràng buộc cascade ở database là một cơ chế riêng và cần được cấu hình trong DDL.

## 7. Quy tắc nullable và ràng buộc khóa ngoại

Với quan hệ bắt buộc, có thể khai báo `optional = false` trên ManyToOne và `nullable = false` trên JoinColumn. DDL tương ứng cần có khóa ngoại và NOT NULL:

```sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE purchase_order_item (
    id BIGINT PRIMARY KEY,
    purchase_order_id BIGINT NOT NULL,
    product_code VARCHAR(50) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_item_order
        FOREIGN KEY (purchase_order_id) REFERENCES purchase_order(id)
);
```

Đây là DDL minh họa; cú pháp tạo ID, kiểu dữ liệu và naming có thể cần điều chỉnh theo database. `nullable = false` trong annotation không thay thế migration tạo constraint trên schema đang chạy. Nếu dùng Flyway/Liquibase, migration phải tạo đúng tên cột và ràng buộc.

Nếu muốn xóa item khỏi collection mà không xóa bản ghi, khóa ngoại phải cho phép null hoặc phải chuyển item sang một parent khác trước khi commit. Nếu FK NOT NULL, không thể chỉ gỡ liên kết và để item tồn tại không có cha.

## 8. Collection List, Set và thứ tự phần tử

`List` phù hợp khi ứng dụng cần giữ một danh sách có thứ tự hiển thị; `Set` phù hợp khi quan hệ cần ngữ nghĩa không trùng lặp. Tuy nhiên, collection Java không tự tạo ra thứ tự ổn định trong database.

- `@OrderBy("productCode ASC")` sắp xếp kết quả theo thuộc tính của Entity con khi collection được tải. Tên trong `@OrderBy` là tên thuộc tính Java, không phải tên cột vật lý.
- `@OrderColumn(name = "item_position")` lưu vị trí phần tử bằng một cột thứ tự trong schema; provider cập nhật các giá trị vị trí khi danh sách thay đổi.
- Nếu không khai báo thứ tự, không nên dựa vào thứ tự phần tử trả về từ database.
- Với `Set`, `equals()` và `hashCode()` phải ổn định khi Entity còn nằm trong collection. Không nên dùng các thuộc tính mutable như quantity hoặc status làm khóa equality.

Ví dụ sắp xếp theo số dòng nghiệp vụ:

```java
@OneToMany(mappedBy = "purchaseOrder")
@OrderBy("lineNumber ASC")
private List<PurchaseOrderItem> items = new ArrayList<>();
```

Ví dụ lưu vị trí do người dùng sắp xếp:

```java
@OneToMany(mappedBy = "purchaseOrder")
@OrderColumn(name = "item_position")
private List<PurchaseOrderItem> items = new ArrayList<>();
```

Chỉ chọn một chiến lược phù hợp với yêu cầu thứ tự. `@OrderBy` đọc theo giá trị thuộc tính có sẵn; `@OrderColumn` quản lý một cột vị trí riêng và có thể gây thêm update khi sắp xếp lại danh sách.

## 9. Lazy loading và vấn đề N+1

`@OneToMany` mặc định là LAZY theo Jakarta Persistence. Khi tải parent, provider không bắt buộc tải toàn bộ collection ngay. Collection có thể được tải khi ứng dụng truy cập nó trong persistence context còn hoạt động.

Vấn đề N+1 xảy ra khi truy vấn danh sách N parent, rồi truy cập collection của từng parent và khiến Hibernate phát thêm một truy vấn cho mỗi collection. Ví dụ một trang hiển thị 30 đơn hàng cùng item có thể phát sinh 1 truy vấn lấy đơn hàng và thêm 30 truy vấn lấy item.

Các cách xử lý thường dùng:

- Dùng `JOIN FETCH` cho use case cần lấy parent và child cùng lúc:

```java
@Query("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.items
    where o.id = :id
    """)
Optional<PurchaseOrder> findWithItemsById(@org.springframework.data.repository.query.Param("id") Long id);
```

- Dùng `@EntityGraph(attributePaths = "items")` trên repository method khi muốn khai báo fetch plan ở mức method.
- Cân nhắc `@BatchSize` hoặc `hibernate.default_batch_fetch_size` để Hibernate tải collection theo nhóm, giảm số round-trip trong các trường hợp phù hợp.
- Dùng DTO/projection khi chỉ cần một phần dữ liệu để trả API hoặc báo cáo.

Không áp dụng collection fetch join một cách máy móc cho truy vấn phân trang parent. Join nhiều child làm nhân số dòng kết quả, có thể khiến database pagination và số parent thực tế không khớp kỳ vọng hoặc buộc Hibernate phân trang trong bộ nhớ. Với màn hình phân trang, có thể lấy trang ID parent trước, sau đó truy vấn fetch collection cho nhóm ID đó hoặc dùng DTO query phù hợp.

## 10. Lưu và cập nhật collection trong transaction

Ví dụ một service thêm nhiều item vào đơn hàng:

```java
@Transactional
public void addItems(Long orderId, List<NewItemRequest> requests) {
    PurchaseOrder order = repository.findById(orderId)
        .orElseThrow(() -> new EntityNotFoundException("Order not found"));

    for (NewItemRequest request : requests) {
        PurchaseOrderItem item = new PurchaseOrderItem();
        item.setProductCode(request.productCode());
        item.setQuantity(request.quantity());
        order.addItem(item);
    }
}
```

Do `order` đang managed, thay đổi owning side và cascade PERSIST cho item mới sẽ được đồng bộ khi flush/commit. Service cần kiểm tra request, quyền truy cập, giới hạn số lượng và các quy tắc nghiệp vụ trước khi thêm item. Nếu không dùng cascade PERSIST, hãy persist từng item hoặc dùng repository phù hợp.

Đối với collection lớn, tránh tải toàn bộ con chỉ để thêm một bản ghi nếu use case không cần collection. Có thể tạo child và gán parent managed trực tiếp qua ManyToOne, sau đó persist child. Điều này giảm chi phí tải collection.

## 11. Xóa parent và child

Khi xóa parent, kết quả phụ thuộc vào cascade, orphan removal và ràng buộc FK. Nếu collection dùng `cascade = REMOVE` hoặc orphanRemoval, Hibernate có thể xóa các child liên quan trước khi xóa parent. Nếu không, FK có thể chặn lệnh DELETE parent. Với dữ liệu lớn, xóa hàng nghìn child qua ORM có thể tốn bộ nhớ và nhiều câu lệnh; cần thiết kế batch/delete query có kiểm soát và lưu ý bulk JPQL delete không đồng bộ persistence context.

Không bật cascade REMOVE chỉ để tránh lỗi FK. Trước tiên xác định ai sở hữu vòng đời child và liệu child có được tham chiếu ở nơi khác không. Nếu dữ liệu cần lưu lịch sử, cân nhắc soft delete hoặc trạng thái nghiệp vụ thay vì xóa vật lý.

## 12. Lỗi thường gặp và cách chẩn đoán

**Collection có phần tử nhưng FK không được ghi.** Với quan hệ hai hướng, kiểm tra đã gán ManyToOne owning side chưa; helper method phải cập nhật cả collection và child.parent.

**`mappedBy` không hợp lệ.** Giá trị `mappedBy` phải là tên thuộc tính Java ở Entity con. Không dùng tên cột `purchase_order_id`.

**Tạo ra join table ngoài dự kiến.** Kiểm tra OneToMany đơn hướng có thiếu `@JoinColumn` hay không. JPA thường dùng join table cho mapping đơn hướng mặc định.

**Xóa child nhưng bản ghi vẫn còn.** Kiểm tra `orphanRemoval`, cascade và phía owning; gỡ child khỏi collection chỉ có ý nghĩa xóa orphan khi mapping được cấu hình như vậy.

**Không thể gỡ child vì FK NOT NULL.** Xác định nghiệp vụ là xóa child, chuyển child sang parent khác hay cho phép quan hệ rỗng. Điều chỉnh mapping và migration nhất quán.

**API trả dữ liệu chậm hoặc phát sinh nhiều SQL.** Kiểm tra N+1, fetch plan và serialization. Dùng DTO/entity graph/join fetch theo use case.

**Vòng lặp khi serialize.** Tránh trả Entity hai hướng trực tiếp; tạo DTO có cấu trúc rõ ràng để không serialize qua lại parent-child.

## 13. Checklist thiết kế @OneToMany

- Xác định quan hệ có thực sự là một parent nhiều child và child có thể tồn tại độc lập hay không.
- Chọn đơn hướng hoặc hai hướng theo nhu cầu điều hướng.
- Nếu hai hướng, đặt `@JoinColumn` trên ManyToOne và `mappedBy` đúng tên thuộc tính ở OneToMany.
- Tạo helper method để cập nhật hai phía trong bộ nhớ.
- Chọn cascade và orphanRemoval theo vòng đời dữ liệu.
- Khớp nullable, FK, unique constraint và tên cột với migration.
- Chọn List/Set và quy tắc thứ tự phù hợp.
- Kiểm tra LAZY, N+1, phân trang và DTO.
- Xem SQL thực tế khi thêm, cập nhật và xóa child.

`@OneToMany` mô tả collection ở phía cha; thiết kế đúng còn cần quyết định nơi lưu khóa ngoại, phía sở hữu, vòng đời child và cách tải collection. Khi các quy tắc này thống nhất với schema và use case, quan hệ một-nhiều sẽ dễ duy trì và tránh được nhiều lỗi ORM phổ biến.