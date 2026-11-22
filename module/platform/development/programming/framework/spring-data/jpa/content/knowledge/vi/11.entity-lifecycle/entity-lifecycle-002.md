# Ánh xạ một-nhiều bằng @OneToMany

## 1. Ý nghĩa của quan hệ một-nhiều

Quan hệ một-nhiều (one-to-many) biểu diễn một Entity cha có thể liên kết với nhiều Entity con. Ví dụ, một đơn hàng `PurchaseOrder` có nhiều dòng hàng `PurchaseOrderItem`, còn mỗi dòng hàng thuộc về một đơn hàng.

Trong mô hình quan hệ, cách biểu diễn phổ biến là đặt khóa ngoại ở bảng con:

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

`@OneToMany` ánh xạ collection ở phía cha. Nó không tự quyết định phía nào ghi khóa ngoại, có xóa con theo cha hay không, thứ tự phần tử hoặc cách tải collection. Các quyết định này cần được cấu hình riêng.

## 2. Mapping hai hướng phổ biến

Với schema có `purchase_order_item.purchase_order_id`, mẫu thường dùng là quan hệ hai hướng: Entity con có `@ManyToOne` và Entity cha có `@OneToMany(mappedBy = ...)`. Khóa ngoại nằm ở bảng con nên ManyToOne là owning side.

```java
import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false, unique = true)
    private String orderNumber;

    @OneToMany(
        mappedBy = "purchaseOrder",
        cascade = {CascadeType.PERSIST, CascadeType.MERGE},
        orphanRemoval = true
    )
    private List<PurchaseOrderItem> items = new ArrayList<>();

    protected PurchaseOrder() {
    }

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
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "purchase_order_id", nullable = false)
    private PurchaseOrder purchaseOrder;

    @Column(name = "product_code", nullable = false)
    private String productCode;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected PurchaseOrderItem() {
    }

    public void setPurchaseOrder(PurchaseOrder purchaseOrder) {
        this.purchaseOrder = purchaseOrder;
    }
}
```

Đây là phần mapping cốt lõi; ứng dụng thực tế cần bổ sung constructor, accessor và các phương thức nghiệp vụ phù hợp. `mappedBy = "purchaseOrder"` phải trùng chính xác tên thuộc tính Java trong `PurchaseOrderItem`, không phải tên cột `purchase_order_id`. `@JoinColumn` khai báo cột vật lý chứa khóa ngoại.

## 3. Owning side và mappedBy

Trong ví dụ trên, `PurchaseOrderItem.purchaseOrder` là owning side vì nó khai báo `@JoinColumn` và tương ứng với khóa ngoại trên bảng con. `PurchaseOrder.items` là inverse side vì nó khai báo `mappedBy`.

JPA dựa vào owning side để ghi thay đổi liên kết xuống database. Do đó, nếu chỉ gọi `order.getItems().add(item)` mà không gán `item.setPurchaseOrder(order)`, collection trong bộ nhớ có thể đã có phần tử nhưng `purchase_order_id` vẫn không được ghi như mong muốn.

Với quan hệ hai hướng, JPA không tự đồng bộ hai thuộc tính Java. Hãy đóng gói thao tác thêm/bỏ trong helper method để cập nhật cả hai phía. Nếu item đã thuộc một đơn hàng khác, nghiệp vụ cần quyết định có cho phép chuyển item hay phải từ chối; không nên âm thầm để item xuất hiện trong collection của hai cha.

## 4. Mapping OneToMany đơn hướng

Nếu chỉ cần đi từ cha tới con, có thể khai báo `@OneToMany` mà không tạo thuộc tính tham chiếu ngược trong Entity con. Có hai cách ánh xạ phổ biến.

**Dùng join table:** Khi OneToMany đơn hướng không khai báo join column, JPA thường dùng một join table để lưu liên kết. Có thể khai báo rõ tên bảng và hai cột:

```java
@OneToMany
@JoinTable(
    name = "purchase_order_item_link",
    joinColumns = @JoinColumn(name = "purchase_order_id"),
    inverseJoinColumns = @JoinColumn(name = "item_id", unique = true)
)
private List<PurchaseOrderItem> items = new ArrayList<>();
```

Join table chứa khóa ngoại tới parent và child. Ràng buộc unique trên `item_id` giúp một item chỉ liên kết với tối đa một đơn hàng trong mô hình này.

**Đặt khóa ngoại trên bảng con:** Có thể khai báo `@JoinColumn` trực tiếp trên collection:

```java
@OneToMany
@JoinColumn(name = "purchase_order_id")
private List<PurchaseOrderItem> items = new ArrayList<>();
```

Ở dạng đơn hướng này, collection là phía khai báo liên kết; Entity con không cần thuộc tính `purchaseOrder`. Cột `purchase_order_id` vẫn nằm trên bảng con. Tùy provider và mapping, thao tác lưu có thể gồm insert child rồi update FK; hãy kiểm tra SQL thực tế nếu hiệu năng ghi quan trọng. Nếu nghiệp vụ thường xuyên cần đi từ con về cha, mapping hai hướng với ManyToOne thường rõ ràng hơn.

## 5. Cascade: thao tác nào lan sang Entity con?

Không có cascade nào được bật mặc định. Các loại thường gặp:

| Cascade | Hành vi |
| --- | --- |
| `PERSIST` | Persist các con liên quan khi persist cha |
| `MERGE` | Merge các con liên quan khi merge cha |
| `REMOVE` | Xóa các con khi xóa cha |
| `REFRESH` | Refresh các con khi refresh cha |
| `DETACH` | Detach các con khi detach cha |
| `ALL` | Bao gồm tất cả các loại trên |

Chọn cascade theo vòng đời dữ liệu. Nếu `PurchaseOrderItem` chỉ tồn tại như một phần của đơn hàng, PERSIST/MERGE có thể hợp lý. Nếu child có thể được chia sẻ hoặc tồn tại độc lập, không nên cascade REMOVE một cách tùy tiện.

Cascade không thay đổi owning side và không tự đồng bộ hai thuộc tính Java. `cascade = ALL` cũng không có nghĩa là mọi thao tác collection đều an toàn; hãy xem xét tác động của persist, merge, remove và các luồng import.

## 6. orphanRemoval và xóa phần tử khỏi collection

`orphanRemoval = true` yêu cầu provider xóa Entity con khi nó bị tách khỏi quan hệ OneToMany hoặc OneToOne thích hợp. Trong ví dụ hai hướng, `removeItem` bỏ item khỏi collection và đặt tham chiếu cha về null; khi flush, item bị xem là orphan và được xóa.

Khác biệt với cascade REMOVE:

- `cascade = REMOVE`: thao tác xóa cha được lan sang các con.
- `orphanRemoval = true`: xóa con khi con bị gỡ khỏi quan hệ, kể cả khi cha vẫn tồn tại.

Chỉ dùng orphanRemoval khi child thực sự thuộc quyền sở hữu vòng đời của parent. Nếu chỉ muốn bỏ liên kết nhưng giữ child, không bật orphanRemoval và thiết kế khóa ngoại nullable hoặc quy tắc chuyển child sang parent khác. Với FK `NOT NULL`, không thể giữ child tồn tại mà không có parent.

Orphan removal là ngữ nghĩa của ORM. Nó khác với `ON DELETE CASCADE` do database thực hiện; hai cơ chế cần được hiểu và cấu hình riêng.

## 7. Nullability và migration

Với quan hệ bắt buộc, `optional = false` trên ManyToOne và `nullable = false` trên JoinColumn mô tả mapping. Schema cũng cần có FK và NOT NULL tương ứng:

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

DDL chỉ mang tính minh họa; kiểu ID và cú pháp có thể thay đổi theo database. Annotation không tự cập nhật schema đang được quản lý bằng Flyway hoặc Liquibase. Migration phải tạo đúng tên cột, foreign key, unique constraint và nullability. Khi đổi mapping, cần migration tương ứng và kiểm tra dữ liệu hiện có.

## 8. List, Set và thứ tự phần tử

`List` giữ thứ tự trong bộ nhớ, nhưng không tự bảo đảm thứ tự khi tải từ database. `Set` biểu diễn tập phần tử không trùng theo quy tắc `equals()`/`hashCode()`, vì vậy equality của Entity cần được thiết kế cẩn thận.

**Sắp xếp theo thuộc tính:**

```java
@OneToMany(mappedBy = "purchaseOrder")
@OrderBy("lineNumber ASC")
private List<PurchaseOrderItem> items = new ArrayList<>();
```

`@OrderBy` sắp xếp khi tải collection theo thuộc tính Java `lineNumber`, không phải tên cột vật lý.

**Lưu vị trí của từng phần tử:**

```java
@OneToMany(mappedBy = "purchaseOrder")
@OrderColumn(name = "item_position")
private List<PurchaseOrderItem> items = new ArrayList<>();
```

`@OrderColumn` dùng cột riêng để lưu vị trí; provider có thể phải cập nhật nhiều vị trí khi danh sách thay đổi. Chọn cách này khi thứ tự do người dùng sắp xếp cần được lưu bền vững. Nếu không khai báo thứ tự, không dựa vào thứ tự kết quả từ database.

## 9. Lazy loading và N+1

`@OneToMany` mặc định là LAZY theo Jakarta Persistence. Khi tải parent, collection chưa nhất thiết được tải. Truy cập collection trong persistence context có thể kích hoạt truy vấn bổ sung.

N+1 xảy ra khi lấy N parent rồi truy cập collection của từng parent, khiến Hibernate phát sinh thêm khoảng N truy vấn. Ví dụ một trang hiển thị 20 đơn hàng và mỗi đơn hàng cần danh sách item có thể tạo một truy vấn lấy đơn hàng cùng nhiều truy vấn lấy item.

Các cách xử lý theo use case:

- `JOIN FETCH` khi cần lấy parent cùng collection trong một truy vấn:

```java
@Query("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.items
    where o.id = :id
    """)
Optional<PurchaseOrder> findWithItemsById(
    @org.springframework.data.repository.query.Param("id") Long id
);
```

- `@EntityGraph(attributePaths = "items")` khi muốn khai báo fetch plan trên repository method.
- `@BatchSize` hoặc `hibernate.default_batch_fetch_size` để tải collection theo nhóm trong các trường hợp phù hợp.
- DTO/projection khi chỉ cần một phần dữ liệu để hiển thị hoặc trả API.

Không áp dụng collection fetch join một cách máy móc cho truy vấn phân trang parent. Join collection nhân số dòng kết quả và có thể làm phân trang sai kỳ vọng hoặc buộc Hibernate phân trang trong bộ nhớ. Một cách thường dùng là lấy trang ID parent trước, sau đó truy vấn fetch collection cho nhóm ID đó.

## 10. Quản lý collection lớn

Không nên tải hàng chục nghìn child vào một collection chỉ để thêm một bản ghi. Với collection lớn, có thể truy vấn parent managed rồi tạo child, gán ManyToOne trực tiếp và persist child. Cách này tránh khởi tạo toàn bộ collection khi use case chỉ cần ghi thêm một child.

Khi phải xử lý hàng loạt, chia thành chunk và quản lý transaction, flush, clear phù hợp. `flush()` đồng bộ thay đổi đang chờ với database; `clear()` detach các Entity khỏi persistence context để giới hạn bộ nhớ. Sau `clear()`, không tiếp tục coi các đối tượng cũ là managed.

Với bulk JPQL delete/update, persistence context không tự đồng bộ các Entity đang managed. Sau bulk operation, cần clear hoặc refresh phù hợp để tránh đọc trạng thái cũ.

## 11. Xóa parent và child

Khi xóa parent, kết quả phụ thuộc cascade, orphanRemoval và FK. Nếu không cascade remove và vẫn còn child tham chiếu, database có thể từ chối xóa parent do ràng buộc khóa ngoại. Nếu cascade remove được bật, Hibernate có thể phát sinh lệnh xóa child trước parent.

Không bật cascade REMOVE chỉ để né lỗi FK. Trước tiên xác định child có được dùng chung hoặc cần lưu lịch sử hay không. Với dữ liệu nghiệp vụ cần bảo toàn, cân nhắc trạng thái ngừng hoạt động hoặc soft delete thay vì xóa vật lý.

## 12. Lỗi thường gặp và cách chẩn đoán

**Thêm vào collection nhưng FK không thay đổi.** Trong mapping hai hướng, cập nhật owning side ManyToOne; dùng helper method để đồng bộ cả hai phía.

**`mappedBy` báo lỗi.** Kiểm tra tên thuộc tính Java ở Entity con, không dùng tên cột database.

**Có join table ngoài dự kiến.** Kiểm tra OneToMany đơn hướng không khai báo `@JoinColumn`; mặc định thường dùng join table.

**Không thể gỡ child.** Xem FK có NOT NULL không, orphanRemoval có bật không và nghiệp vụ muốn xóa, chuyển hay bỏ liên kết.

**Phát sinh nhiều truy vấn.** Kiểm tra N+1, fetch plan, serialization và số lượng collection được khởi tạo.

**JSON bị lặp vô hạn.** Không serialize trực tiếp Entity hai hướng; tạo DTO với chiều dữ liệu có chủ đích.

**Set mất phần tử hoặc không loại trùng đúng.** Kiểm tra equals/hashCode, tránh dùng thuộc tính mutable làm định danh khi Entity đang nằm trong Set.

## 13. Checklist thiết kế @OneToMany

- Chọn quan hệ đơn hướng hay hai hướng theo nhu cầu điều hướng.
- Xác định FK nằm ở bảng nào và owning side là thuộc tính nào.
- Với mapping hai hướng, đặt `mappedBy` trỏ đúng thuộc tính ManyToOne.
- Tạo helper method cập nhật cả collection và tham chiếu owning side.
- Chọn cascade và orphanRemoval theo vòng đời child.
- Đồng bộ nullability, FK, index và migration với mapping.
- Chọn List/Set, `@OrderBy` hoặc `@OrderColumn` theo yêu cầu thứ tự.
- Kiểm tra LAZY, N+1, phân trang và DTO.
- Quan sát SQL khi thêm, sửa, bỏ child và xóa parent.

`@OneToMany` là cách biểu diễn collection ở phía cha. Một mapping tốt cần nhất quán giữa object graph, owning side, vòng đời child và cấu trúc khóa ngoại trong database. Thiết kế theo use case thực tế giúp tránh lỗi liên kết và giữ hiệu năng khi collection phát triển.