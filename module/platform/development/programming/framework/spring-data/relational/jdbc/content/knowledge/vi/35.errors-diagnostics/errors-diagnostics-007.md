# Vi phạm khóa ngoại, unique constraint và dữ liệu con ngoài dự kiến

Khi lưu một aggregate bằng Spring Data JDBC, database vẫn kiểm tra các ràng buộc toàn vẹn như foreign key, primary key, unique constraint và check constraint. Nếu dữ liệu không thỏa một ràng buộc, câu SQL thất bại và Spring thường chuyển lỗi JDBC thành một exception thuộc hệ thống `DataAccessException`.

Ngoài lỗi do dữ liệu đầu vào, Spring Data JDBC còn có một hành vi quan trọng cần hiểu khi chẩn đoán dữ liệu con: **khi lưu một aggregate root đã tồn tại, framework xóa các entity con đang được tham chiếu, cập nhật root rồi insert lại các entity con theo trạng thái hiện tại của object**. Vì Spring Data JDBC không theo dõi trạng thái trước đó của aggregate, một object root bị thiếu collection con có thể khiến dữ liệu con hiện có bị xóa khi lưu.

Bài học giải thích nguyên nhân thường gặp của lỗi khóa ngoại và unique constraint, cách mapping quan hệ parent-child bằng `@MappedCollection`, vì sao dữ liệu con có thể biến mất hoặc được tạo lại, cách giữ aggregate nhất quán và cách chẩn đoán exception trong transaction.

## 1. Ba nhóm ràng buộc thường gặp

### 1.1. Foreign key constraint

Foreign key bảo đảm một giá trị tham chiếu phải trỏ đến một hàng tồn tại ở bảng được tham chiếu.

Ví dụ, mỗi dòng hàng phải thuộc về một đơn hàng:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_order(id)
);
~~~

Cột `order_line.order_id` phải chứa một giá trị tồn tại trong `purchase_order.id`.

Lỗi foreign key có thể xảy ra khi:

- Insert child với ID parent không tồn tại.
- Update foreign key sang một parent không tồn tại.
- Xóa parent trong khi một hàng ở bảng khác vẫn tham chiếu đến parent đó.
- Mapping tạo tên cột back-reference không khớp với schema.
- Dữ liệu được ghi bằng SQL thủ công bỏ qua thứ tự insert/delete phù hợp.

### 1.2. Unique constraint

Unique constraint bảo đảm một giá trị hoặc một tổ hợp giá trị không bị lặp.

Ví dụ, SKU chỉ được xuất hiện một lần trong cùng một đơn hàng:

~~~sql
ALTER TABLE order_line
ADD CONSTRAINT uq_order_line_sku
UNIQUE (order_id, sku);
~~~

Nếu ứng dụng thêm hai dòng có cùng `order_id` và `sku`, database từ chối dòng trùng.

Unique constraint thường được dùng để bảo vệ các quy tắc như:

- Email khách hàng không trùng.
- Mã đơn hàng duy nhất.
- Một SKU chỉ có một dòng trong một đơn hàng.
- Một người dùng chỉ có một membership trong một tổ chức.
- Một cặp khóa ghép không được xuất hiện hai lần.

Đừng nhầm unique constraint với primary key. Primary key luôn duy nhất và không null; unique constraint có thể được tạo cho các cột nghiệp vụ khác.

### 1.3. Check constraint và NOT NULL

Ngoài foreign key và unique constraint, database còn có thể từ chối dữ liệu vì:

- Một cột bắt buộc nhận null.
- Giá trị không thỏa `CHECK`.
- Giá trị vượt độ dài hoặc precision của cột.
- Kiểu dữ liệu không tương thích.

Ví dụ:

~~~sql
quantity INTEGER NOT NULL CHECK (quantity > 0)
~~~

Dòng hàng có số lượng 0 hoặc âm không thể được lưu.

## 2. Spring chuyển lỗi database thành exception nào?

Spring JDBC sử dụng cơ chế exception translation để chuyển `SQLException` và lỗi từ data access framework thành các exception nhất quán thuộc package `org.springframework.dao`.

Hai loại thường gặp:

| Exception | Ý nghĩa |
| --- | --- |
| `DataIntegrityViolationException` | Một thao tác insert/update/delete vi phạm ràng buộc toàn vẹn hoặc dữ liệu không thể lưu theo schema |
| `DuplicateKeyException` | Một dạng lỗi cụ thể hơn liên quan đến khóa bị trùng; đây là subclass của `DataIntegrityViolationException` |

`DataIntegrityViolationException` là exception tổng quát cho vi phạm toàn vẹn. Nó có thể bao gồm lỗi foreign key, unique, primary key, check constraint hoặc dữ liệu không phù hợp schema.

Không phải mọi JDBC driver đều phân loại cùng một constraint violation thành cùng một subclass. Vì vậy, khi xử lý nghiệp vụ, thường nên bắt `DataIntegrityViolationException` ở ranh giới phù hợp. Chỉ bắt `DuplicateKeyException` khi translator của database thực sự cung cấp loại cụ thể đó.

Ví dụ xử lý lỗi trùng SKU:

~~~java
try {
    orderRepository.save(order);
} catch (DuplicateKeyException ex) {
    throw new DuplicateOrderLineException(
        "SKU already exists in this order",
        ex
    );
}
~~~

Nếu muốn xử lý nhiều dạng vi phạm khác nhau, có thể bắt exception tổng quát:

~~~java
try {
    orderRepository.save(order);
} catch (DataIntegrityViolationException ex) {
    throw new OrderPersistenceException(
        "Order data violates a database constraint",
        ex
    );
}
~~~

Không nên biến mọi `DataIntegrityViolationException` thành lỗi “duplicate key”. Một foreign key violation và một unique violation có nguyên nhân nghiệp vụ khác nhau.

### 2.1. Tìm nguyên nhân gốc

Spring exception thường giữ exception gốc từ JDBC driver. Có thể lấy cause cụ thể để log hoặc chẩn đoán:

~~~java
catch (DataIntegrityViolationException ex) {
    Throwable rootCause = ex.getMostSpecificCause();

    log.error(
        "Database constraint violation: {}",
        rootCause.getMessage(),
        ex
    );

    throw ex;
}
~~~

Thông tin hữu ích để xác định lỗi gồm:

- Tên constraint bị vi phạm nếu database/driver cung cấp.
- Tên bảng và cột.
- SQLState.
- Vendor error code.
- Câu SQL đang chạy và giá trị bind phù hợp với môi trường debug.

Không nên phụ thuộc vào việc parse chuỗi message để điều khiển nghiệp vụ vì format message thay đổi theo database, driver và phiên bản.

## 3. Mapping parent-child bằng @MappedCollection

Spring Data JDBC coi các entity được tham chiếu từ aggregate root là một phần của aggregate. Ví dụ, `PurchaseOrder` là root và `OrderLine` là entity con. Mỗi thay đổi nhất quán được thực hiện qua root.

Root:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String status;

    @MappedCollection(
        idColumn = "order_id",
        keyColumn = "line_no"
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String status) {
        this.status = status;
    }

    public void addLine(String sku, int quantity) {
        lines.add(new OrderLine(sku, quantity));
    }

    public void removeLine(String sku) {
        lines.removeIf(line -> line.sku().equals(sku));
    }

    public Long getId() {
        return id;
    }

    public List<OrderLine> getLines() {
        return List.copyOf(lines);
    }
}
~~~

Entity con:

~~~java
import org.springframework.data.relational.core.mapping.Table;

@Table("order_line")
public record OrderLine(
    String sku,
    int quantity
) {
}
~~~

`@MappedCollection` cho Spring Data biết cột nào trong bảng con tham chiếu đến primary key của root và cột nào lưu vị trí của List hoặc key của Map.

Trong ví dụ:

- `idColumn = "order_id"` là foreign key trỏ tới `purchase_order.id`.
- `keyColumn = "line_no"` lưu chỉ số của phần tử trong List.
- `OrderLine` không cần một ID độc lập trong ví dụ này; hàng con được nhận diện trong aggregate bằng parent ID và key/index.

### Schema tương ứng

~~~sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE order_line (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),

    CONSTRAINT pk_order_line
        PRIMARY KEY (order_id, line_no),

    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_order(id),

    CONSTRAINT uq_order_line_sku
        UNIQUE (order_id, sku)
);
~~~

Bảng con có ba ràng buộc khác nhau:

- Primary key `(order_id, line_no)` bảo đảm mỗi vị trí trong một đơn hàng chỉ có một dòng.
- Foreign key `order_id` bảo đảm parent tồn tại.
- Unique `(order_id, sku)` bảo đảm cùng SKU không xuất hiện hai lần trong một đơn hàng.

Tên cột mặc định của back-reference thường dựa trên tên bảng của aggregate root. `@MappedCollection(idColumn = "order_id")` cho phép chỉ định rõ tên cột để khớp schema. Với List và Map, key column cũng có thể được tùy chỉnh.

## 4. Thứ tự ghi và xóa aggregate

Spring Data JDBC xử lý toàn bộ aggregate theo root. Khi lưu aggregate mới:

1. Insert aggregate root.
2. Insert các entity con được tham chiếu trực tiếp và gián tiếp.

Parent được insert trước để các hàng con có thể tham chiếu đến ID hợp lệ.

Khi lưu một aggregate đã tồn tại, hành vi hiện tại khác với ORM có persistence context:

1. Xóa các entity con được aggregate tham chiếu.
2. Update aggregate root.
3. Insert lại các entity con theo trạng thái hiện tại của object.

Khi xóa aggregate, Spring Data JDBC xóa các entity con thuộc aggregate và sau đó xóa root theo quy trình persist/delete của framework.

### Vì sao Spring Data JDBC ghi lại toàn bộ entity con?

Spring Data JDBC không duy trì persistence context và không theo dõi snapshot trước đó của từng entity con. Nó nhận trạng thái aggregate hiện tại từ object được truyền vào và biến trạng thái đó thành dữ liệu trong database.

Vì vậy, framework cần bảo đảm các hàng hiện có được chuyển thành đúng tập hàng thể hiện trong object mới. Cách thực hiện là xóa các hàng con được tham chiếu rồi insert lại tập hiện tại.

Điều này có thể tạo thêm SQL ngay cả khi chỉ thay đổi một property của root. Với collection lớn, chi phí ghi có thể đáng kể.

## 5. Dữ liệu con bị xóa hoặc thay đổi ngoài dự kiến

Đây là nguyên nhân phổ biến khi một aggregate được dựng lại từ dữ liệu không đầy đủ rồi gọi `save`.

Giả sử database đang có:

| order_id | line_no | sku | quantity |
| ---: | ---: | --- | ---: |
| 10 | 0 | BOOK-01 | 2 |
| 10 | 1 | PEN-02 | 3 |

Ứng dụng tạo một object root chỉ chứa trạng thái đơn hàng và không có dòng hàng:

~~~java
PurchaseOrder partial = new PurchaseOrder("PAID");
// Không có OrderLine trong collection.
~~~

Nếu object này được nhận diện là aggregate đã tồn tại và được lưu, Spring Data JDBC có thể coi collection rỗng là trạng thái cuối cùng mong muốn. Các dòng hàng cũ được xóa, sau đó không có dòng nào được insert lại.

Kết quả là dữ liệu con biến mất dù code chỉ định cập nhật trạng thái root.

### 5.1. Luôn load aggregate đầy đủ trước khi thay đổi

Một cách phù hợp là load aggregate hiện tại, thay đổi nó qua phương thức nghiệp vụ rồi save:

~~~java
@Transactional
public void markPaid(Long orderId) {
    PurchaseOrder order = orderRepository.findById(orderId)
        .orElseThrow(() -> new OrderNotFoundException(orderId));

    order.markPaid();

    orderRepository.save(order);
}
~~~

Với aggregate được load đầy đủ, collection con hiện tại vẫn nằm trong object khi save.

Nếu cần cập nhật một cột đơn lẻ mà không muốn đồng bộ lại toàn bộ collection, cân nhắc custom repository hoặc SQL update tường minh. Khi làm vậy, ứng dụng tự chịu trách nhiệm giữ invariant và quan hệ dữ liệu.

### 5.2. Không dùng child entity như aggregate độc lập

Theo mô hình Spring Data JDBC, entity con thuộc aggregate root có vòng đời do root quản lý. Khi reference bị xóa khỏi root, entity con tương ứng bị xóa khỏi database.

Nếu một entity con cần được tham chiếu độc lập từ nhiều aggregate hoặc có vòng đời riêng, nó có thể không nên là child của aggregate hiện tại. Hãy xem xét tách nó thành aggregate root riêng.

### 5.3. Quan hệ n-1 và n-m là aggregate riêng

Spring Data JDBC giới hạn entity references bên trong aggregate theo quan hệ một-một hoặc một-nhiều. Nếu cần quan hệ nhiều-nhất hoặc nhiều-nhiều giữa các aggregate, hãy dùng ID hoặc `AggregateReference` để lưu tham chiếu.

Ví dụ:

~~~java
import org.springframework.data.jdbc.core.mapping.AggregateReference;

public class PurchaseOrder {

    private AggregateReference<Customer, Long> customer;
}
~~~

`AggregateReference` biểu diễn ID của aggregate khác. Nó không yêu cầu Spring Data lưu hoặc xóa aggregate được tham chiếu như một child của root hiện tại.

Không đặt entity được nhiều aggregate cùng tham chiếu thành child collection của một root. Khi root save, framework có thể xóa và tạo lại child rows, gây lỗi foreign key hoặc làm mất dữ liệu tham chiếu bên ngoài.

## 6. Chẩn đoán foreign key violation

Khi nhận `DataIntegrityViolationException`, trước hết xác định thao tác SQL nào thất bại và constraint nào bị vi phạm.

### 6.1. Child insert không tìm thấy parent

Các nguyên nhân thường gặp:

- Giá trị foreign key không khớp với ID của parent.
- Parent chưa được insert hoặc insert đã thất bại.
- `@MappedCollection(idColumn = "...")` dùng tên cột khác với schema.
- SQL viết tay insert child trước khi insert parent.
- Dữ liệu cũ chứa foreign key không còn hợp lệ.

Với quan hệ parent-child trong cùng aggregate, Spring Data JDBC thường insert root trước rồi insert child. Nếu lỗi xảy ra trong đường lưu repository chuẩn, hãy kiểm tra tên back-reference, mapping, schema và giá trị ID thực tế.

### 6.2. Xóa parent nhưng vẫn còn hàng tham chiếu

Ví dụ, một bảng `payment` tham chiếu trực tiếp đến `purchase_order`. Nếu database dùng `ON DELETE RESTRICT` hoặc hành vi mặc định tương đương, lệnh xóa đơn hàng sẽ thất bại khi payment còn tồn tại.

Có thể xử lý theo một trong các quy tắc nghiệp vụ:

- Xóa các hàng phụ thuộc trước khi xóa parent.
- Dùng `ON DELETE CASCADE` nếu vòng đời dữ liệu thực sự yêu cầu xóa dây chuyền.
- Không cho phép xóa parent và chuyển nghiệp vụ sang trạng thái đã hủy/đóng.
- Dùng soft delete nếu dữ liệu lịch sử cần được giữ lại.

Không thêm cascade chỉ để làm biến mất exception. `ON DELETE CASCADE` có thể xóa dữ liệu của các bảng khác mà ứng dụng không dự định xóa.

### 6.3. Cột back-reference không khớp

Nếu Spring Data dùng tên back-reference khác tên cột trong schema, insert child có thể báo không tìm thấy cột hoặc không thể ghi giá trị khóa ngoại.

Có thể khai báo rõ tên cột:

~~~java
@MappedCollection(
    idColumn = "order_id",
    keyColumn = "line_no"
)
private List<OrderLine> lines;
~~~

Đối chiếu mapping với DDL và naming strategy. Với List/Map, kiểm tra cả key column vì nó lưu index hoặc key của collection.

## 7. Chẩn đoán unique constraint violation

Unique constraint thường biểu thị một invariant nghiệp vụ đã bị vi phạm.

Ví dụ, ứng dụng có quy tắc mỗi đơn hàng chỉ chứa một dòng cho một SKU. Nếu service không kiểm tra danh sách trước khi thêm dòng mới, database sẽ từ chối khi insert một SKU trùng.

Có thể kiểm tra trước trong domain model:

~~~java
public void addLine(String sku, int quantity) {
    boolean alreadyExists = lines.stream()
        .anyMatch(line -> line.sku().equals(sku));

    if (alreadyExists) {
        throw new DuplicateOrderLineException(sku);
    }

    lines.add(new OrderLine(sku, quantity));
}
~~~

Kiểm tra trong Java giúp trả lỗi nghiệp vụ dễ hiểu. Tuy nhiên, nó không thay thế unique constraint ở database.

### Vì sao vẫn cần unique constraint?

Hai request có thể cùng kiểm tra một SKU trước khi một request nào insert. Cả hai đều thấy SKU chưa có và cùng tiếp tục. Chỉ database mới có thể tuần tự hóa việc ghi và bảo đảm uniqueness cuối cùng.

Vì vậy, nên kết hợp:

1. Kiểm tra trong domain/service để thông báo sớm.
2. Unique constraint để bảo vệ dữ liệu trước race condition và các đường ghi khác.
3. Xử lý exception khi database từ chối một request cạnh tranh.

Không nên chỉ chạy SELECT kiểm tra trùng rồi insert. Khoảng thời gian giữa SELECT và INSERT vẫn có thể có transaction khác ghi cùng giá trị.

### Constraint có thể quá chặt hoặc đặt sai phạm vi

Nếu nghiệp vụ cho phép cùng SKU xuất hiện nhiều lần trong một đơn hàng, unique constraint `UNIQUE(order_id, sku)` là sai. Có thể cần một khóa khác, ví dụ `line_no`, hoặc thêm thuộc tính phân biệt vào unique key.

Ngược lại, nếu quy tắc duy nhất áp dụng toàn hệ thống, constraint phải được đặt trên cột nghiệp vụ toàn cục, không chỉ trên cặp parent-child.

Hãy thiết kế unique key theo đúng phạm vi nghiệp vụ: toàn hệ thống, theo tenant, theo parent hay theo một khoảng thời gian.

## 8. Xử lý exception ở ranh giới nghiệp vụ

Spring exception translation giúp code không phụ thuộc trực tiếp vào class exception của từng JDBC driver. Có thể bắt `DataIntegrityViolationException` hoặc subclass cụ thể khi translator cung cấp.

Ví dụ, service chuyển lỗi trùng SKU thành exception nghiệp vụ:

~~~java
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final PurchaseOrderRepository orders;

    public OrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public PurchaseOrder save(PurchaseOrder order) {
        try {
            return orders.save(order);
        } catch (DuplicateKeyException ex) {
            throw new DuplicateOrderLineException(
                "The order already contains this SKU",
                ex
            );
        } catch (DataIntegrityViolationException ex) {
            throw new OrderDataIntegrityException(
                "The order violates a database constraint",
                ex
            );
        }
    }
}
~~~

Ví dụ bắt `DuplicateKeyException` trước vì nó là subclass của `DataIntegrityViolationException`. Một driver có thể chỉ trả exception tổng quát cho một số constraint, do đó không nên giả định mọi lỗi unique đều luôn có cùng subclass.

Không nên bắt exception rồi bỏ qua:

~~~java
try {
    orders.save(order);
} catch (DataIntegrityViolationException ex) {
    log.warn("Could not save order", ex);
    // Tiếp tục xử lý như thể lưu thành công là sai.
}
~~~

Nếu exception bị nuốt bên trong service, transaction interceptor có thể không nhận được exception để áp dụng quy tắc rollback mặc định. Một số database cũng đánh dấu transaction là failed sau constraint violation và không cho thực hiện thêm SQL cho đến khi rollback.

Hãy chuyển lỗi thành exception nghiệp vụ rồi ném ra ngoài transaction boundary, hoặc chủ động rollback theo chiến lược transaction đã chọn. Không tiếp tục nghiệp vụ như thể aggregate đã được lưu thành công.

### Không parse message để phân loại constraint

Tên constraint, SQLState và vendor error code có thể nằm trong cause chain. Khi cần phân loại chính xác, hãy kiểm tra root cause phù hợp với driver/database đang dùng hoặc viết một exception translator riêng.

Tránh logic kiểu:

~~~java
if (ex.getMessage().contains("uq_order_line_sku")) {
    // ...
}
~~~

Message có thể thay đổi theo driver hoặc phiên bản database. Dùng tên constraint trong migration và kiểm tra cause/SQLState có kiểm soát sẽ bền vững hơn.

## 9. Dữ liệu con bị tạo lại có thể gây lỗi khóa ngoại như thế nào?

Giả sử bảng `order_line` là child của `purchase_order`. Một bảng khác `shipment_line` lại có foreign key trỏ đến `order_line.id`.

Nếu ứng dụng lưu aggregate và Spring Data JDBC xóa các child row cũ rồi insert lại, foreign key từ `shipment_line` có thể ngăn xóa child row. Nếu database cho cascade, việc xóa child có thể kéo theo shipment line ngoài dự kiến.

Đây là dấu hiệu thiết kế aggregate chưa phù hợp: một entity được mô hình hóa là child nhưng lại được tham chiếu độc lập từ một aggregate khác.

Cách giải quyết thường là:

- Đưa entity có vòng đời độc lập thành aggregate root riêng.
- Tham chiếu từ aggregate khác bằng ID hoặc `AggregateReference`.
- Không để bảng ngoài aggregate tham chiếu trực tiếp vào child row nếu Spring Data JDBC sẽ quản lý child như dữ liệu phụ thuộc root.
- Nếu schema hiện tại bắt buộc phải có quan hệ đó, cân nhắc custom repository/SQL để quản lý cập nhật child theo cách phù hợp với database.

## 10. Quy trình chẩn đoán từ exception đến dữ liệu

Khi một thao tác save/delete thất bại, hãy điều tra theo thứ tự:

1. **Xác định thao tác:** repository method nào chạy, save root, insert child, update hay delete?
2. **Đọc constraint:** tên constraint, bảng và cột nào xuất hiện trong exception hoặc log database?
3. **Kiểm tra trạng thái dữ liệu:** parent có tồn tại không, giá trị unique có bị trùng không, collection con hiện tại có đầy đủ không?
4. **Kiểm tra mapping:** `@Table`, `@Column`, `@MappedCollection`, `idColumn` và `keyColumn` có khớp schema không?
5. **Kiểm tra câu SQL:** bật logging JDBC trong môi trường phù hợp để xem câu lệnh thực tế và thứ tự thực thi.
6. **Kiểm tra transaction:** lỗi có làm rollback toàn bộ use case không, hay exception đã bị bắt và bỏ qua?
7. **Kiểm tra đường ghi khác:** có SQL thủ công, batch job hoặc service khác đang ghi cùng bảng không?

### Bật log SQL

Có thể bật log Spring JDBC trong cấu hình môi trường test:

~~~properties
logging.level.org.springframework.jdbc=DEBUG
~~~

Tùy phiên bản và cấu hình logging, có thể cần bật logger cụ thể hơn để xem SQL và bind parameter. Không nên ghi giá trị nhạy cảm của người dùng vào log production.

### Đọc thông tin constraint từ database

Tên constraint trong DDL nên có ý nghĩa, ví dụ:

- `fk_order_line_order` cho foreign key.
- `uq_order_line_sku` cho unique constraint.
- `pk_order_line` cho primary key.
- `ck_order_line_quantity` cho check constraint.

Tên rõ ràng giúp xác định lỗi nhanh hơn so với constraint name do database tự sinh. Nếu database không trả tên constraint trong exception, kiểm tra cause chain, SQLState, vendor code và log server.

## 11. Transaction và rollback khi vi phạm constraint

Một constraint violation là runtime data access exception trong Spring. Nếu exception đi ra khỏi method được quản lý bởi `@Transactional`, Spring mặc định rollback transaction.

Ví dụ:

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;

    public OrderApplicationService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void addLine(Long orderId, String sku, int quantity) {
        PurchaseOrder order = orders.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.addLine(sku, quantity);

        orders.save(order);
    }
}
~~~

Nếu unique hoặc foreign key constraint bị vi phạm trong quá trình save, exception được ném ra và transaction được rollback theo quy tắc mặc định.

Nếu cần chuyển exception thành lỗi nghiệp vụ, hãy ném exception mới ra khỏi transaction boundary và giữ exception gốc làm cause. Nếu bắt lỗi và tiếp tục chạy trong cùng method, hãy xác định rõ transaction có còn hợp lệ hay không và có cần đánh dấu rollback.

Không nên chia một use case gồm load root, sửa child và save root thành nhiều transaction riêng nếu tính nhất quán yêu cầu tất cả cùng thành công hoặc cùng thất bại.

## 12. Thiết kế aggregate để tránh dữ liệu con ngoài dự kiến

Spring Data JDBC dựa trên ranh giới aggregate để quyết định dữ liệu nào được ghi và xóa cùng nhau.

### 12.1. Chỉ để root quản lý child có cùng vòng đời

Một Order và các OrderLine thường có quan hệ một-nhiều: dòng hàng thuộc về đơn hàng, không có vòng đời độc lập và không được nhiều aggregate khác tham chiếu trực tiếp.

Trong trường hợp này, `@MappedCollection` là cách ánh xạ phù hợp.

Nếu một entity có thể được chia sẻ giữa nhiều parent, hoặc cần được cập nhật/xóa độc lập, hãy mô hình hóa nó thành aggregate root riêng và lưu ID/reference trong aggregate khác.

### 12.2. Không lưu aggregate một phần

Nếu một service chỉ muốn cập nhật status, hãy load đầy đủ aggregate rồi thay đổi status. Đừng tạo một object mới với cùng ID nhưng thiếu collection con rồi gọi `save`.

Nếu cần cập nhật trực tiếp một số cột mà không đọc toàn aggregate, dùng custom repository hoặc JDBC SQL tường minh. Khi đó cần tự xác định tác động tới child rows, version, constraint và transaction.

### 12.3. Không để aggregate khác tham chiếu vào child row

Spring Data JDBC giả định chỉ aggregate chứa child mới có foreign key tới bảng child. Nếu bảng của một aggregate khác tham chiếu trực tiếp đến child row, việc delete/reinsert child khi save root có thể bị chặn hoặc gây cascade ngoài dự kiến.

Hãy tham chiếu aggregate root bằng ID hoặc `AggregateReference`. Nếu dữ liệu lịch sử yêu cầu tham chiếu trực tiếp child, cần thiết kế cách persist riêng để giữ ổn định identity của child.

### 12.4. Chọn constraint theo invariant nghiệp vụ

Database constraint nên phản ánh quy tắc cần bảo vệ:

| Quy tắc | Constraint phù hợp |
| --- | --- |
| Child phải có parent | Foreign key |
| Một SKU chỉ xuất hiện một lần trong một order | Unique `(order_id, sku)` |
| Mỗi vị trí List chỉ có một child | Primary key `(order_id, line_no)` |
| Số lượng phải dương | Check `quantity > 0` |
| Trạng thái không được null | `NOT NULL` |

Constraint bảo vệ dữ liệu ngay cả khi có nhiều instance ứng dụng, nhiều transaction hoặc một công cụ khác ghi trực tiếp vào database.

## 13. Kiểm thử constraint và vòng đời child

Nên có integration test trên database mục tiêu để xác nhận cả mapping và hành vi constraint.

### 13.1. Test unique constraint

~~~java
@Test
void rejectsDuplicateSkuWithinOrder() {
    PurchaseOrder order = new PurchaseOrder("NEW");
    order.addLine("BOOK-01", 1);
    order.addLine("BOOK-01", 2);

    assertThatThrownBy(() -> orders.save(order))
        .isInstanceOf(DataIntegrityViolationException.class);
}
~~~

Test này giả định schema có unique constraint `UNIQUE(order_id, sku)`. Nếu domain model kiểm tra trùng trước khi persist, test repository-level có thể dùng JDBC trực tiếp để kiểm tra database constraint độc lập.

### 13.2. Test foreign key

Có thể dùng `JdbcTemplate` để thử insert child với parent ID không tồn tại và xác nhận database từ chối. Đây là test schema constraint, không phải test repository mapping.

### 13.3. Test save aggregate đã tồn tại

Một test hữu ích là:

1. Lưu order có hai dòng hàng.
2. Load lại aggregate qua repository.
3. Thay đổi status và save.
4. Load lại và xác nhận hai dòng hàng vẫn tồn tại.
5. Xóa một dòng bằng phương thức domain rồi save.
6. Xác nhận chỉ dòng đã bỏ khỏi aggregate bị xóa khỏi trạng thái cuối cùng.

Test này giúp phát hiện trường hợp service tạo aggregate một phần và vô tình xóa collection con.

### 13.4. Test transaction rollback

Tạo một thao tác save có unique violation sau khi đã thực hiện một thay đổi khác trong cùng transaction. Xác nhận transaction rollback và không để lại trạng thái một phần.

Đối với deadlock, race condition hoặc constraint dưới tải đồng thời, hãy chạy integration test trên database thật hoặc Testcontainers. Embedded database có thể có transaction và locking semantics khác production.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Insert child báo foreign key violation | Parent chưa tồn tại hoặc back-reference sai | Kiểm tra parent ID, `idColumn` và thứ tự SQL |
| Delete root bị database từ chối | Bảng khác còn tham chiếu root | Xóa dependency, dùng soft delete hoặc thiết kế cascade phù hợp |
| Save root làm mất tất cả child | Object truyền vào thiếu collection hoặc collection rỗng | Load aggregate đầy đủ trước khi sửa và save |
| Save root làm child được insert lại | Đây là cách Spring Data JDBC đồng bộ aggregate hiện tại | Thiết kế child cùng vòng đời root; tránh external FK tới child |
| Thêm child báo duplicate key | Trùng primary key, list index hoặc unique business key | Kiểm tra key column và unique constraint |
| Dòng hàng trùng SKU bị từ chối | Unique constraint `(order_id, sku)` được áp dụng | Kiểm tra domain trước, hoặc điều chỉnh constraint nếu nghiệp vụ cho phép |
| Không ghi được cột foreign key | `@MappedCollection` không khớp tên cột schema | Khai báo `idColumn` và `keyColumn` rõ ràng |
| Dữ liệu con bị xóa khi update status | Lưu object detached/partial aggregate | Load root đầy đủ rồi sửa; hoặc dùng SQL update riêng |
| Bắt exception nhưng transaction không rollback như mong đợi | Exception bị nuốt trong transactional method | Ném lại exception hoặc đánh dấu rollback |
| Không phân biệt được unique và FK error | Chỉ log message chung | Kiểm tra root cause, SQLState, vendor code và constraint name |

## 15. Quy trình xử lý sự cố

Khi gặp foreign key, unique constraint hoặc child data ngoài dự kiến, hãy làm theo quy trình:

1. Xác định aggregate root và toàn bộ entity con thuộc aggregate.
2. Đọc DDL để liệt kê primary key, foreign key, unique, check và not-null constraints.
3. Đối chiếu `@MappedCollection`, naming strategy, `idColumn` và `keyColumn` với schema.
4. Kiểm tra object aggregate truyền vào `save` có chứa đúng trạng thái cuối cùng của collection con không.
5. Xác nhận entity bị tham chiếu có thật sự thuộc aggregate hay cần tách thành aggregate riêng.
6. Kiểm tra SQL và thứ tự insert/delete trong log.
7. Xử lý exception ở service boundary và bảo đảm transaction rollback khi use case thất bại.
8. Viết integration test tái hiện constraint trên database mục tiêu.

## 16. Bài tập tự thực hành

### Bài 1 — Foreign key

Tạo Order và OrderLine với `@MappedCollection`. Thử insert một child qua SQL thủ công với order ID không tồn tại và quan sát exception.

### Bài 2 — Unique constraint

Thêm unique constraint `(order_id, sku)`. Tạo hai OrderLine có cùng SKU trong một order và xác nhận database từ chối.

### Bài 3 — Dữ liệu con bị mất

Lưu order có hai dòng hàng, sau đó tạo object mới chỉ có ID và status rồi gọi save. Quan sát dữ liệu con. Giải thích vì sao load aggregate đầy đủ trước khi thay đổi giúp tránh lỗi này.

### Bài 4 — Thứ tự persist

Bật JDBC logging khi insert và delete aggregate. Xác định thứ tự SQL giữa root và child.

### Bài 5 — AggregateReference

Tách Customer thành aggregate root độc lập. Tham chiếu Customer từ Order bằng ID hoặc `AggregateReference` và giải thích vì sao Customer không nên là child của Order.

### Bài 6 — External foreign key tới child

Tạo bảng khác tham chiếu đến OrderLine. Thử save order và quan sát tác động của chiến lược delete/reinsert child. Sau đó thiết kế lại aggregate boundary.

### Bài 7 — Exception translation

Bắt `DataIntegrityViolationException` và `DuplicateKeyException`. So sánh cause chain trên database đang dùng và chuyển lỗi thành exception nghiệp vụ phù hợp.

### Bài 8 — Transaction rollback

Trong một service `@Transactional`, cập nhật root rồi tạo một child vi phạm unique constraint. Xác nhận toàn bộ thay đổi của use case được rollback.

## 17. Tài liệu tham khảo chính thức

- [Spring Data Relational — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): `@MappedCollection`, foreign key back-reference, giới hạn quan hệ aggregate và cách ánh xạ child.
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): thứ tự insert/update và hành vi delete/reinsert entity con khi save aggregate đã tồn tại.
- [Spring Data Relational — Domain Driven Design and Relational Databases](https://docs.spring.io/spring-data/relational/reference/jdbc/domain-driven-design.html): aggregate root, ranh giới aggregate và giới hạn tham chiếu giữa aggregate.
- [Spring Framework — DataAccessException](https://docs.spring.io/spring-framework/reference/data-access/dao.html): hệ thống exception thống nhất và exception translation trong tầng data access.
- [Spring Framework — DataIntegrityViolationException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataIntegrityViolationException.html): exception tổng quát cho lỗi vi phạm ràng buộc toàn vẹn, bao gồm các trường hợp duplicate key.

Foreign key và unique constraint bảo vệ tính toàn vẹn của dữ liệu ở database. Spring Data JDBC bổ sung quy tắc persist theo aggregate: root quản lý vòng đời của entity con, và khi save một root đã tồn tại, các entity con được xóa rồi tạo lại theo trạng thái hiện tại. Hiểu rõ hai lớp này giúp phân biệt lỗi do dữ liệu không hợp lệ với lỗi do mapping hoặc thiết kế aggregate, đồng thời tránh việc cập nhật một phần root làm mất dữ liệu con ngoài dự kiến.
