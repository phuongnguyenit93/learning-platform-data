# Phân biệt orphanRemoval, CascadeType.REMOVE và ON DELETE của cơ sở dữ liệu

## 1. Ba cơ chế xóa liên quan đến quan hệ entity

Khi một entity cha có quan hệ với các entity con, ứng dụng cần xác định điều gì sẽ xảy ra với dữ liệu con trong những tình huống khác nhau: xóa một phần tử khỏi collection, xóa entity cha bằng JPA, hoặc xóa trực tiếp hàng cha trong database.

JPA và cơ sở dữ liệu cung cấp ba cơ chế thường bị nhầm lẫn:

- **`orphanRemoval = true`**: xóa entity con khi nó bị tách khỏi quan hệ một-một hoặc một-nhiều được cấu hình orphan removal.
- **`CascadeType.REMOVE`**: truyền thao tác `remove` từ entity nguồn sang các entity đích khi entity nguồn bị xóa bằng JPA.
- **`ON DELETE CASCADE`**: quy tắc của khóa ngoại trong database, tự xóa các hàng tham chiếu khi hàng được tham chiếu bị xóa.

Chúng có thể cùng dẫn đến việc dữ liệu con bị xóa, nhưng điều kiện kích hoạt, tầng thực thi và ảnh hưởng đến persistence context khác nhau. Chọn đúng cơ chế phụ thuộc vào ý nghĩa sở hữu dữ liệu và cách ứng dụng thực hiện thao tác xóa.

## 2. orphanRemoval: xóa entity con khi bị tách khỏi quan hệ

`orphanRemoval` là thuộc tính của các annotation quan hệ `@OneToOne` và `@OneToMany`. Khi đặt `orphanRemoval = true`, entity đích sẽ được áp dụng thao tác xóa nếu nó bị loại khỏi quan hệ được quản lý. Việc xóa được thực hiện khi persistence context đồng bộ với database (thường tại thời điểm flush hoặc commit).

Ví dụ: một đơn hàng sở hữu các dòng chi tiết. Một dòng chi tiết không có ý nghĩa nghiệp vụ độc lập khi bị loại khỏi đơn hàng, nên có thể xem nó là đối tượng phụ thuộc vòng đời vào đơn hàng.

~~~java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = {CascadeType.PERSIST, CascadeType.MERGE},
        orphanRemoval = true
    )
    private List<OrderItem> items = new ArrayList<>();

    protected PurchaseOrder() {}

    public void addItem(OrderItem item) {
        items.add(item);
        item.setOrder(this);
    }

    public void removeItem(OrderItem item) {
        items.remove(item);
        item.setOrder(null);
    }

    public List<OrderItem> getItems() {
        return items;
    }
}
~~~

Entity con giữ phía sở hữu khóa ngoại:

~~~java
@Entity
@Table(name = "order_item")
public class OrderItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    private String productName;

    protected OrderItem() {}

    public OrderItem(String productName) {
        this.productName = productName;
    }

    void setOrder(PurchaseOrder order) {
        this.order = order;
    }
}
~~~

Trong quan hệ hai chiều này:

- `PurchaseOrder.items` là phía inverse vì có `mappedBy = "order"`.
- `OrderItem.order` là phía owning side, chứa khóa ngoại `order_id`.
- Phương thức `addItem` và `removeItem` cập nhật cả hai phía để trạng thái trong bộ nhớ nhất quán.
- Khi gọi `removeItem`, dòng chi tiết trở thành orphan; JPA sẽ áp dụng remove cho entity đó khi flush.

Ví dụ sử dụng:

~~~java
@Transactional
public void removeProductFromOrder(Long orderId, Long itemId) {
    PurchaseOrder order = orderRepository.findById(orderId)
        .orElseThrow();

    OrderItem item = order.getItems().stream()
        .filter(candidate -> candidate.getId().equals(itemId))
        .findFirst()
        .orElseThrow();

    order.removeItem(item);
}
~~~

Trong transaction này, không cần gọi riêng `orderItemRepository.delete(item)` để biểu đạt ý nghĩa xóa phần tử khỏi đơn hàng. Khi quan hệ được đồng bộ, orphan removal yêu cầu xóa entity con.

### Khi nào nên dùng orphanRemoval?

Dùng khi entity con thực sự thuộc sở hữu vòng đời của entity cha, ví dụ:

- Dòng chi tiết của đơn hàng.
- Các dòng cấu hình riêng của một hồ sơ.
- Các địa chỉ phụ thuộc vào một tài khoản nếu nghiệp vụ không cho phép chúng tồn tại độc lập.
- Thành phần của một aggregate mà khi bị gỡ khỏi aggregate thì phải bị xóa.

Không nên dùng nếu entity con có thể được chuyển sang một entity cha khác hoặc tồn tại độc lập sau khi bị gỡ khỏi quan hệ. Theo quy tắc portable của JPA, không nên dựa vào việc tái gắn một entity đã trở thành orphan vào quan hệ khác; hãy thiết kế lại thao tác chuyển chủ sở hữu hoặc không dùng orphan removal cho trường hợp đó.

`orphanRemoval` không áp dụng cho `@ManyToMany`. Quan hệ nhiều-nhiều thường nối các entity có vòng đời độc lập; xóa một liên kết không có nghĩa là xóa entity ở đầu bên kia.

## 3. CascadeType.REMOVE: xóa con khi xóa entity cha bằng JPA

`CascadeType.REMOVE` truyền thao tác `EntityManager.remove(parent)` từ entity cha sang các entity đích của quan hệ. Điểm kích hoạt là **xóa entity cha**, không phải chỉ xóa một phần tử khỏi collection trong khi cha vẫn tồn tại.

Ví dụ:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REMOVE
)
private List<OrderItem> items = new ArrayList<>();
~~~

Khi ứng dụng xóa đơn hàng bằng JPA:

~~~java
@Transactional
public void deleteOrder(Long id) {
    PurchaseOrder order = orderRepository.findById(id)
        .orElseThrow();

    entityManager.remove(order);
}
~~~

JPA truyền thao tác remove tới các entity con thuộc quan hệ có `CascadeType.REMOVE`. Provider sẽ phát các câu lệnh SQL cần thiết trong transaction, theo thứ tự phù hợp với ràng buộc khóa ngoại.

Nếu chỉ gọi `order.getItems().remove(item)` mà không xóa entity cha, `CascadeType.REMOVE` không yêu cầu xóa `item`. Nếu muốn xóa entity con khi nó bị gỡ khỏi collection, đó là trường hợp của `orphanRemoval`.

### CascadeType.ALL có bao gồm REMOVE không?

Có. `CascadeType.ALL` bao gồm các thao tác `PERSIST`, `MERGE`, `REMOVE`, `REFRESH` và `DETACH`. Vì vậy:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderItem> items = new ArrayList<>();
~~~

Cấu hình trên truyền nhiều thao tác vòng đời từ cha sang con và đồng thời xóa con khi bị tách khỏi quan hệ.

Tuy nhiên, không nên dùng `CascadeType.ALL` theo thói quen cho mọi quan hệ. Chỉ cascade những thao tác phù hợp với quyền sở hữu và vòng đời dữ liệu. Đặc biệt, cascade REMOVE tới entity dùng chung có thể gây xóa dữ liệu ngoài ý muốn.

## 4. ON DELETE CASCADE: xóa hàng con do database thực hiện

`ON DELETE CASCADE` là hành động được khai báo trên **foreign key** trong database. Khi một hàng ở bảng được tham chiếu bị xóa, database tự xóa các hàng ở bảng tham chiếu có khóa ngoại trỏ tới hàng đó.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY
);

CREATE TABLE order_item (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_name VARCHAR(255),
    CONSTRAINT fk_order_item_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_order(id)
        ON DELETE CASCADE
);
~~~

Khi xóa hàng trong `purchase_order`, database tự xóa các hàng `order_item` có `order_id` tương ứng. Quy tắc này được thực thi ở tầng database, kể cả khi câu lệnh DELETE đến từ JDBC, SQL trực tiếp hoặc một thao tác JPA khiến provider phát lệnh xóa hàng cha.

Trong mapping JPA, `ON DELETE CASCADE` không phải là một giá trị của `CascadeType`. JPA chuẩn không có thuộc tính annotation portable tương đương để khai báo hành động `ON DELETE CASCADE` của foreign key. Vì thế, thông thường hãy tạo quy tắc này bằng migration/schema DDL.

Hibernate có annotation riêng `@OnDelete(action = OnDeleteAction.CASCADE)` để mô tả hành vi xóa ở khóa ngoại trong schema do Hibernate quản lý. Đây là extension của Hibernate, không phải annotation chuẩn JPA. Nếu dùng extension này, cần kiểm tra DDL thực tế và hành vi của đúng phiên bản provider; migration vẫn là cách rõ ràng để quản lý schema production.

### Vì sao ON DELETE CASCADE hữu ích?

- Database tự bảo đảm quy tắc xóa ở mọi đường truy cập, kể cả khi có ứng dụng khác ghi dữ liệu.
- Có thể xóa nhiều hàng con mà không cần ORM tải từng entity con lên bộ nhớ.
- Quy tắc được bảo vệ bởi foreign key và thực thi trong transaction database.
- Hữu ích với các thao tác SQL trực tiếp hoặc bulk delete vốn không kích hoạt cascade remove của JPA.

Nhưng database không cập nhật trạng thái các object Java đang được quản lý trong persistence context. Nếu `OrderItem` đã được tải vào bộ nhớ, database có thể xóa hàng tương ứng trong khi object vẫn còn tồn tại trong persistence context. Sau thao tác database cascade, cần cân nhắc `clear()`, `refresh()` hoặc tải lại dữ liệu ở một persistence context phù hợp. Với second-level cache, việc đồng bộ/invalidate phụ thuộc provider và cấu hình.

## 5. So sánh trực tiếp ba cơ chế

| Tiêu chí | `orphanRemoval = true` | `CascadeType.REMOVE` | `ON DELETE CASCADE` |
|---|---|---|---|
| Được cấu hình ở đâu? | Annotation quan hệ JPA `@OneToOne` / `@OneToMany` | Thuộc tính `cascade` của quan hệ JPA | Foreign key trong database |
| Kích hoạt khi nào? | Entity con bị tách khỏi quan hệ được quản lý | Entity cha bị xóa bằng JPA | Hàng cha bị xóa trong database |
| Ai thực hiện xóa? | JPA provider qua thao tác remove khi flush | JPA provider truyền remove tới entity con | Database engine |
| Xóa phần tử khỏi collection khi cha còn tồn tại? | Có, nếu entity là orphan theo quan hệ | Không tự động | Không, chỉ phản ứng khi hàng được tham chiếu bị xóa |
| Xóa cha bằng JPA? | Có, remove cũng được áp dụng cho các entity đích theo semantics orphan removal | Có, nếu quan hệ có cascade REMOVE | Có, nếu foreign key được tạo với ON DELETE CASCADE |
| Có phụ thuộc persistence context? | Có | Có | Database không phụ thuộc persistence context; trạng thái object/cache của ORM có thể bị cũ |
| Quan hệ áp dụng | One-to-one, one-to-many | Các quan hệ JPA có khai báo cascade phù hợp | Foreign key của database |

Cách nhớ nhanh:

- **Gỡ con khỏi quan hệ** → `orphanRemoval`.
- **Xóa cha bằng JPA và muốn xóa con theo** → `CascadeType.REMOVE`.
- **Xóa hàng cha ở database và muốn database tự xóa hàng con** → `ON DELETE CASCADE`.

Ba cơ chế có thể được kết hợp nếu mô hình dữ liệu cần cả hành vi ORM và ràng buộc ở database. Nhưng phải hiểu rõ provider sẽ phát SQL gì và persistence context được đồng bộ ra sao.

## 6. Kết hợp các cơ chế trong cùng một quan hệ

Với quan hệ cha-con có sở hữu vòng đời, một mapping thường dùng là:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = {CascadeType.PERSIST, CascadeType.MERGE},
    orphanRemoval = true
)
private List<OrderItem> items = new ArrayList<>();
~~~

Cấu hình này cho phép lưu/merge các con theo cha và xóa con khi chúng bị gỡ khỏi collection. Khi xóa cha, orphan-removal semantics cũng áp dụng remove tới các entity đích. Không nhất thiết phải thêm `CascadeType.REMOVE` chỉ để lặp lại hành vi xóa con khi cha bị xóa trong trường hợp `orphanRemoval = true`.

Nếu nghiệp vụ chỉ muốn xóa con khi xóa cha, nhưng vẫn cho phép gỡ hoặc chuyển con sang cha khác, có thể dùng `CascadeType.REMOVE` mà không bật orphan removal:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = {CascadeType.PERSIST, CascadeType.MERGE, CascadeType.REMOVE}
)
private List<OrderItem> items = new ArrayList<>();
~~~

Nếu muốn database là nơi bảo đảm xóa hàng con cho mọi lệnh DELETE, thêm `ON DELETE CASCADE` vào foreign key bằng DDL migration. Khi kết hợp với JPA cascade, hãy kiểm tra SQL do provider phát ra để tránh các thao tác dư thừa và xử lý trạng thái persistence context.

## 7. Lưu ý quan trọng với quan hệ hai chiều

Trong quan hệ `@OneToMany` hai chiều, phía `@ManyToOne` thường là owning side vì nó chứa khóa ngoại. `mappedBy` ở collection phía cha chỉ ra thuộc tính sở hữu quan hệ ở entity con.

Ví dụ:

~~~java
@OneToMany(mappedBy = "order", orphanRemoval = true)
private List<OrderItem> items = new ArrayList<>();
~~~

và:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "order_id")
private PurchaseOrder order;
~~~

Nếu chỉ xóa phần tử khỏi `items` nhưng không cập nhật `OrderItem.order`, hai phía object có thể không nhất quán. Nên đóng gói thao tác thêm/xóa vào helper method để cập nhật cả collection và owning side.

Không nên thao tác trực tiếp với collection ở nhiều nơi trong ứng dụng. Khi logic quan hệ bị phân tán, rất dễ bỏ sót việc cập nhật owning side, gây lỗi khóa ngoại hoặc dữ liệu không đúng như mong muốn.

## 8. Bulk delete và native SQL khác với xóa entity thông thường

Một điểm rất quan trọng: các thao tác xóa hàng loạt thường không đi qua từng entity managed.

Ví dụ, Spring Data JPA có các phương thức như `deleteAllInBatch()` hoặc `deleteAllByIdInBatch()`, và ứng dụng cũng có thể viết JPQL bulk delete với `@Modifying`. Các lệnh bulk này thực hiện DELETE ở mức truy vấn; chúng không gọi `EntityManager.remove()` cho từng entity.

Hệ quả:

- JPA cascade remove không được áp dụng theo cách của thao tác xóa từng entity.
- Orphan removal không được kích hoạt bởi việc bulk delete từng hàng.
- Entity callbacks như `@PreRemove` không được gọi cho từng entity bị xóa bởi bulk query.
- Persistence context có thể chứa object cũ sau khi database đã xóa hàng.
- Foreign key `ON DELETE CASCADE` vẫn được database thực thi nếu lệnh DELETE làm xóa hàng cha và constraint được cấu hình như vậy.

Ví dụ JPQL bulk delete:

~~~java
@Modifying
@Query("delete from PurchaseOrder o where o.id = :id")
int deleteOrderDirectly(@Param("id") Long id);
~~~

Lệnh trên không tương đương với việc tải `PurchaseOrder` rồi gọi `entityManager.remove(order)`. Nếu cần JPA cascade và lifecycle callbacks, hãy dùng thao tác xóa entity thông thường. Nếu chủ đích dùng bulk delete, hãy thiết kế rõ hành vi xóa con bằng database constraint hoặc các lệnh xóa tường minh, đồng thời đồng bộ persistence context sau đó.

## 9. Cascade REMOVE có nguy hiểm với ManyToMany không?

Có thể rất nguy hiểm nếu entity ở phía bên kia được chia sẻ.

Ví dụ một `Student` có nhiều `Course`, và một `Course` có nhiều `Student`. Khi xóa một sinh viên, thông thường chỉ cần xóa các hàng liên kết trong bảng nối, không xóa khóa học vì các sinh viên khác vẫn có thể đăng ký khóa học đó.

Vì vậy:

- Không dùng `orphanRemoval` cho `@ManyToMany`.
- Tránh cascade `REMOVE` từ một entity chia sẻ sang entity còn lại.
- Có thể để database cascade trên các foreign key của **bảng nối** để xóa các hàng liên kết khi một đầu mối bị xóa; điều đó không đồng nghĩa xóa entity dùng chung ở đầu còn lại.

Quy tắc tổng quát là chỉ cascade REMOVE khi entity đích thực sự thuộc quyền sở hữu vòng đời của entity nguồn.

## 10. Chọn cơ chế nào cho từng tình huống?

| Tình huống nghiệp vụ | Cơ chế phù hợp |
|---|---|
| Xóa một dòng chi tiết khỏi đơn hàng và dòng đó không còn tồn tại độc lập | `orphanRemoval = true` |
| Xóa đơn hàng bằng JPA và muốn provider xóa các dòng chi tiết | `CascadeType.REMOVE` hoặc `orphanRemoval = true` theo mô hình sở hữu |
| Cần database tự xóa các hàng con kể cả khi lệnh đến từ SQL trực tiếp hoặc bulk delete | Foreign key `ON DELETE CASCADE` |
| Xóa liên kết giữa hai entity dùng chung trong quan hệ nhiều-nhiều | Xóa hàng ở bảng nối; giữ entity ở hai đầu |
| Có thể chuyển entity con sang cha khác | Tránh orphan removal; dùng quy trình chuyển quan hệ rõ ràng |
| Cần chạy callback JPA cho từng entity bị xóa | Xóa entity qua JPA thay vì bulk delete |

Trước khi bật cascade, hãy trả lời câu hỏi: entity con có thể tồn tại độc lập không? Nếu có, xóa cha không nên tự động xóa con trừ khi nghiệp vụ quy định rõ điều đó. Nếu không, orphan removal hoặc cascade remove có thể phản ánh đúng vòng đời.

## 11. Kiểm thử hành vi xóa

Nên kiểm thử từng hành vi trong transaction riêng với database thực tế hoặc Testcontainers, vì hành vi foreign key cascade và cú pháp DDL phụ thuộc hệ quản trị.

Một số tình huống cần xác nhận:

1. Tạo một đơn hàng có hai dòng chi tiết, flush và kiểm tra cả ba entity được lưu.
2. Gỡ một dòng khỏi collection khi `orphanRemoval = true`, flush, clear persistence context rồi xác nhận dòng đó không còn trong database.
3. Với mapping chỉ có `CascadeType.REMOVE`, gỡ một dòng khỏi collection nhưng giữ cha, xác nhận dòng con vẫn tồn tại nếu không có hành vi xóa khác.
4. Xóa entity cha qua `EntityManager.remove` và xác nhận hành vi cascade đúng như mapping.
5. Xóa hàng cha bằng native SQL hoặc bulk delete để kiểm tra `ON DELETE CASCADE` ở database.
6. Sau thao tác bulk/database cascade, clear persistence context trước khi truy vấn lại để tránh đọc trạng thái object cũ.
7. Kiểm tra trường hợp rollback: transaction rollback không có nghĩa sequence hoặc mọi tác động ngoài transaction đều được hoàn nguyên; với DELETE thông thường trong cùng transaction database, các thay đổi dữ liệu được rollback theo transaction nếu hệ quản trị hỗ trợ transactional DML.

Luôn gọi `flush()` trong test khi cần buộc provider gửi SQL xuống database tại một thời điểm xác định. Sau đó gọi `clear()` hoặc mở persistence context mới trước khi xác minh dữ liệu, đặc biệt khi kiểm tra database cascade.

## 12. Ghi nhớ

- `orphanRemoval = true` diễn tả vòng đời phụ thuộc: entity con bị xóa khi bị tách khỏi quan hệ một-một hoặc một-nhiều.
- `CascadeType.REMOVE` truyền thao tác xóa từ entity cha sang entity con khi cha bị xóa bằng JPA.
- `ON DELETE CASCADE` là quy tắc của foreign key và do database thực thi khi hàng được tham chiếu bị xóa.
- Orphan removal và cascade remove là semantics JPA; database cascade là semantics của database.
- Bulk delete và native SQL không chạy JPA cascade/orphan removal như xóa từng entity, nhưng database foreign key cascade vẫn có thể chạy.
- Giữ owning side và inverse side của quan hệ hai chiều đồng bộ.
- Không cascade REMOVE bừa bãi tới entity dùng chung, nhất là trong `@ManyToMany`.
- Database cascade có thể làm persistence context và cache ORM cũ; hãy đồng bộ hoặc clear khi cần.

Hãy chọn cơ chế theo ý nghĩa nghiệp vụ của quan hệ và đường đi của thao tác xóa. Khi entity con phụ thuộc vòng đời vào cha, orphan removal thường diễn tả đúng việc gỡ con; khi xóa cha qua JPA, cascade remove truyền thao tác tới con; còn ON DELETE CASCADE bảo đảm quy tắc ở tầng database cho mọi lệnh xóa hàng cha đi qua database.