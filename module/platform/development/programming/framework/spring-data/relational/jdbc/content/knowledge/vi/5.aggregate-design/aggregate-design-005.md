# Thiết kế Order và OrderItem như một đơn vị lưu trữ

Trong **Spring Data Relational JDBC (Spring Data JDBC)**, một đơn hàng thường gồm thông tin chung như khách hàng, trạng thái và nhiều dòng hàng. Hai loại đối tượng này có thể lưu ở **hai bảng**, nhưng về mặt nghiệp vụ cần được xem như **một aggregate**: `Order` là **aggregate root**, còn `OrderItem` là thành phần thuộc quyền sở hữu của đơn hàng.

Bài học này xây dựng mô hình `Order`–`OrderItem` từ yêu cầu nghiệp vụ, ánh xạ bằng Spring Data JDBC, lưu xuống cơ sở dữ liệu quan hệ và giải thích điều gì thực sự xảy ra khi gọi `repository.save(order)`. Trọng tâm là thiết kế **một đơn vị lưu trữ nhất quán**, không chỉ nối hai bảng bằng khóa ngoại.

## 1. Tại sao phải thiết kế cùng một aggregate?

Giả sử hệ thống bán hàng cho phép:

- Tạo một đơn hàng ở trạng thái `DRAFT`.
- Thêm hoặc bỏ sản phẩm trước khi xác nhận.
- Mỗi dòng chứa mã sản phẩm (SKU), số lượng và đơn giá được chốt tại thời điểm thêm vào đơn.
- Không cho đơn hàng chuyển sang `CONFIRMED` nếu chưa có dòng hàng.
- Không cho sửa danh sách dòng hàng sau khi xác nhận.

Các quy tắc này liên quan đồng thời đến trạng thái của **Order** và danh sách **OrderItem**. Nếu mỗi nơi tự cập nhật từng dòng hàng rồi cập nhật đơn tùy ý, sẽ có thể xuất hiện đơn `CONFIRMED` nhưng không có dòng hàng, hoặc giá và số lượng bị thay đổi sau khi chốt đơn.

Vì vậy, ta chọn:

**Order là aggregate root.** Mọi thao tác nghiệp vụ làm thay đổi dòng hàng đi qua các phương thức trên `Order`. `OrderItem` sống trong ranh giới của đơn hàng, không được tạo hoặc lưu độc lập bởi các use case thông thường.

### Bản đồ mô hình

~~~mermaid
flowchart TB
    Service["OrderApplicationService<br/>use case tạo / xác nhận đơn"] --> Repository["OrderRepository<br/>CrudRepository<Order, Long>"]
    Repository --> Root

    subgraph Aggregate["AGGREGATE: Order"]
        Root["Order<br/>Aggregate Root<br/>id, version, customerId, status"]
        Root -->|"sở hữu 0..N"| Item["OrderItem<br/>id, sku, quantity, unitPriceCents"]
    end

    Root -. "customerId" .-> Customer["Customer<br/>Aggregate khác"]
    Item -. "sku" .-> Product["Product<br/>Aggregate khác"]
    Root --> Orders[("shop_orders")]
    Item --> Items[("order_items")]
    Items -->|"order_id (FK)"| Orders
~~~

Sơ đồ cho thấy hai khía cạnh riêng:

1. **Mô hình miền:** `Order` sở hữu các `OrderItem`; `Customer` và `Product` có vòng đời độc lập nên đơn hàng chỉ lưu giá trị định danh cần thiết.
2. **Mô hình lưu trữ:** một `Order` và các `OrderItem` của nó được ghi thành các hàng trong hai bảng. Khóa ngoại `order_id` nối bản ghi con tới bản ghi root.

**Một aggregate không đồng nghĩa một bảng.** Ranh giới được quyết định bởi quy tắc nghiệp vụ và quyền sở hữu, còn bảng dữ liệu là cách biểu diễn trạng thái của aggregate.

## 2. Phân chia trách nhiệm cho Order và OrderItem

| Thành phần | Vai trò trong miền | Trách nhiệm | Cách truy cập để ghi |
|---|---|---|---|
| `Order` | Entity và aggregate root | Giữ danh tính đơn, trạng thái, danh sách dòng hàng; bảo vệ bất biến | Thông qua `OrderRepository` |
| `OrderItem` | Entity con trong aggregate | Giữ dữ liệu một dòng hàng và tính thành tiền | Thông qua phương thức của `Order` |
| `Customer` | Aggregate độc lập | Quản lý hồ sơ/vòng đời khách hàng | Repository của Customer |
| `Product` | Aggregate độc lập | Quản lý sản phẩm, trạng thái bán, giá niêm yết | Repository của Product |

Trong bài này, mỗi `OrderItem` có một `id` để định danh bản ghi con khi ánh xạ xuống bảng. Điều đó **không** có nghĩa dòng hàng cần repository riêng. Nó vẫn là entity con, được truy cập và thay đổi trong phạm vi root `Order`.

Tại thời điểm tạo đơn, `OrderItem` ghi lại `sku` và `unitPriceCents`. Sau đó giá niêm yết của `Product` có thể thay đổi mà giá đã chốt trong đơn không tự biến đổi. Đây là ví dụ về **snapshot dữ liệu giao dịch**: chỉ giữ phần thông tin cần thiết của sản phẩm trong Order, không nhúng cả aggregate Product.

### Những bất biến cần bảo vệ

Với thiết kế minh họa, ta quy định:

1. `customerId` phải hợp lệ theo đầu vào (ví dụ lớn hơn 0).
2. Khi thêm dòng hàng, SKU không được trống, số lượng phải dương và đơn giá không âm.
3. Mỗi SKU chỉ xuất hiện một lần trong cùng một đơn. Nếu muốn tăng số lượng cho SKU đã có, cần một thao tác nghiệp vụ tường minh; phiên bản minh họa sẽ từ chối thêm trùng.
4. Chỉ đơn `DRAFT` mới được thêm hoặc xóa dòng hàng.
5. `confirm()` chỉ thành công khi đơn có ít nhất một dòng hàng và đang `DRAFT`.
6. Tổng tiền được tính từ số lượng và đơn giá của các dòng hàng, thay vì cho phép bên ngoài đặt một tổng không khớp.

Cần phân biệt **bất biến trong bộ nhớ** với **ràng buộc database**. Chẳng hạn, `CHECK (quantity > 0)` bảo vệ dữ liệu số lượng trong bảng, nhưng quy tắc “chỉ sửa item khi Order còn DRAFT” phải được thực thi trong thao tác miền và quy trình ghi phù hợp.

## 3. Mô hình Java của aggregate

Ví dụ sau dùng Java và Spring Data JDBC. Các lớp nằm cùng package `com.example.sales.order` để đơn giản hóa minh họa; trong dự án thực tế có thể tách thêm package domain, application và persistence.

### OrderStatus.java

~~~java
package com.example.sales.order;

public enum OrderStatus {
    DRAFT,
    CONFIRMED
}
~~~

### OrderItem.java

~~~java
package com.example.sales.order;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("order_items")
public class OrderItem {

    @Id
    private Long id;

    private String sku;
    private int quantity;
    private long unitPriceCents;

    protected OrderItem() {
        // Spring Data JDBC tạo lại đối tượng khi đọc từ database.
    }

    OrderItem(String sku, int quantity, long unitPriceCents) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (unitPriceCents < 0) {
            throw new IllegalArgumentException("Unit price must be non-negative");
        }
        this.sku = sku;
        this.quantity = quantity;
        this.unitPriceCents = unitPriceCents;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public long getUnitPriceCents() {
        return unitPriceCents;
    }

    public long subtotalCents() {
        return Math.multiplyExact(unitPriceCents, quantity);
    }
}
~~~

Điểm đáng chú ý:

- `@Id` là ID lưu trữ của dòng hàng. ID thường được database sinh khi thêm bản ghi.
- Các thuộc tính của `OrderItem` không có public setter. Use case bên ngoài không thể tự sửa số lượng, giá hay SKU qua đối tượng mà root đã trả về.
- Phương thức `subtotalCents()` tính giá trị từ dữ liệu hiện có; `Math.multiplyExact` phát hiện tràn số nguyên thay vì im lặng tạo ra tổng sai.
- Constructor thêm dòng hàng có phạm vi package (không public), nhằm diễn đạt việc tạo dòng hàng là trách nhiệm của root.

### Order.java

~~~java
package com.example.sales.order;

import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("shop_orders")
public class Order {

    @Id
    private Long id;

    @Version
    private Long version;

    private Long customerId;
    private OrderStatus status;

    @MappedCollection(
        idColumn = "order_id",
        keyColumn = "line_position"
    )
    private List<OrderItem> items = new ArrayList<>();

    protected Order() {
        // Constructor dùng bởi bộ ánh xạ Spring Data JDBC.
    }

    public static Order draftFor(long customerId) {
        if (customerId <= 0) {
            throw new IllegalArgumentException("Invalid customer ID");
        }
        Order order = new Order();
        order.customerId = customerId;
        order.status = OrderStatus.DRAFT;
        return order;
    }

    public void addItem(String sku, int quantity, long unitPriceCents) {
        requireDraft();
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU must not be blank");
        }
        if (items.stream().anyMatch(item -> item.getSku().equals(sku))) {
            throw new IllegalArgumentException("Duplicate SKU in order");
        }
        items.add(new OrderItem(sku, quantity, unitPriceCents));
    }

    public void removeItem(String sku) {
        requireDraft();
        boolean removed = items.removeIf(item -> item.getSku().equals(sku));
        if (!removed) {
            throw new IllegalArgumentException("SKU is not in the order");
        }
    }

    public void confirm() {
        requireDraft();
        if (items.isEmpty()) {
            throw new IllegalStateException("Cannot confirm an empty order");
        }
        status = OrderStatus.CONFIRMED;
    }

    public long totalCents() {
        long total = 0;
        for (OrderItem item : items) {
            total = Math.addExact(total, item.subtotalCents());
        }
        return total;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public Long getCustomerId() {
        return customerId;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public List<OrderItem> getItems() {
        return List.copyOf(items);
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Order is not editable");
        }
    }
}
~~~

Ở đây, **Order bảo vệ quyền thay đổi danh sách**. Phương thức `getItems()` trả về bản sao danh sách không sửa được; kết hợp với việc `OrderItem` không cung cấp setter, caller chỉ có thể thay đổi dòng hàng qua phương thức nghiệp vụ của root.

`@Version` quản lý phiên bản aggregate root để phát hiện cập nhật đồng thời trên cùng một đơn. Phiên bản sẽ do Spring Data JDBC xử lý khi lưu; ứng dụng không tự tăng số này.

### Tại sao không đưa thao tác thêm/xóa vào OrderItemRepository?

Nếu cho phép `orderItemRepository.deleteById(id)`, một đoạn code khác có thể xóa item cuối cùng trong đơn đã `CONFIRMED`. Nó vượt qua `Order.requireDraft()` và quy tắc “đơn đã chốt phải có ít nhất một item”. Với mô hình hiện tại, **chỉ tạo `OrderRepository`**; khi cần thêm/xóa item, tải Order, gọi phương thức của root và lưu Order.

## 4. Ánh xạ một aggregate xuống hai bảng

Spring Data JDBC ánh xạ `Order` vào bảng `shop_orders` và danh sách `OrderItem` vào bảng `order_items`. Trong ví dụ sử dụng PostgreSQL:

~~~sql
CREATE TABLE shop_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED'))
);

CREATE TABLE order_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES shop_orders(id),
    line_position INTEGER NOT NULL,
    sku VARCHAR(60) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents BIGINT NOT NULL
        CHECK (unit_price_cents >= 0),
    CONSTRAINT uq_order_line_position
        UNIQUE (order_id, line_position),
    CONSTRAINT uq_order_sku
        UNIQUE (order_id, sku)
);

CREATE INDEX idx_order_items_order_id
    ON order_items(order_id);
~~~

**Lưu ý:** đây là DDL PostgreSQL mẫu cho bài thực hành. Khi dùng MySQL, cần thay cú pháp ID tự sinh bằng `AUTO_INCREMENT` và chọn engine hỗ trợ FK, ví dụ InnoDB. Không chạy `CREATE TABLE` trên bảng đã tồn tại nếu chưa có kế hoạch migration.

| Trong Java | Trong database | Ý nghĩa |
|---|---|---|
| `Order.id` | `shop_orders.id` | Khóa chính của aggregate root |
| `Order.version` | `shop_orders.version` | Phiên bản phục vụ optimistic locking |
| `Order.customerId` | `shop_orders.customer_id` | Tham chiếu đến khách hàng bằng ID |
| `Order.status` | `shop_orders.status` | Trạng thái của đơn |
| `Order.items` | Tập hàng trong `order_items` | Các thành phần được root sở hữu |
| `@MappedCollection(idColumn = "order_id")` | `order_items.order_id` | Cột liên kết mỗi item đến Order |
| `@MappedCollection(keyColumn = "line_position")` | `order_items.line_position` | Vị trí phần tử trong `List` |
| `OrderItem.id` | `order_items.id` | Khóa chính hàng dòng hàng |

`idColumn` trong `@MappedCollection` chỉ định **cột thuộc bảng con** chứa ID của root; không phải một thuộc tính bắt buộc phải khai báo ngược trên `OrderItem`. Spring Data JDBC quản lý cột FK đó khi ghi aggregate.

Với kiểu `List`, `keyColumn` dùng lưu thứ tự phần tử, bắt đầu từ vị trí **0** trong ví dụ. Nếu nghiệp vụ không quan tâm thứ tự, có thể xem xét collection khác và điều chỉnh mapping tương ứng; đừng nhầm vị trí danh sách với danh tính bền vững của một dòng hàng.

### Cơ sở dữ liệu không quyết định quyền sở hữu

Hai bảng có FK vẫn có thể thuộc **hai aggregate độc lập** nếu mỗi bên có vòng đời riêng. Ngược lại, `Order` và `OrderItem` ở đây thuộc một aggregate vì:

- Item chỉ có ý nghĩa khi gắn với một Order.
- Thêm, xóa, hoặc điều chỉnh item chịu điều kiện trạng thái Order.
- Khi xóa toàn bộ Order theo nghiệp vụ, các item thuộc Order cũng phải được xử lý theo.
- Các thao tác thay đổi phải duy trì bất biến xuyên suốt root và các dòng hàng.

Khóa ngoại là một công cụ giữ toàn vẹn quan hệ, còn **quyết định aggregate** xuất phát từ miền nghiệp vụ.

## 5. Tạo repository cho aggregate root

Ghi `OrderRepository.java`:

~~~java
package com.example.sales.order;

import org.springframework.data.repository.CrudRepository;

public interface OrderRepository extends CrudRepository<Order, Long> {
}
~~~

Repository nhận kiểu root `Order`, ID kiểu `Long`. Với Spring Data JDBC, các thao tác cơ bản bao gồm:

- `save(order)`: ghi trạng thái aggregate bắt đầu từ root và các phần con được ánh xạ.
- `findById(id)`: tải root cùng các phần con thuộc aggregate theo mapping.
- `delete(order)` hoặc `deleteById(id)`: xóa aggregate thông qua repository.

Không cần định nghĩa `OrderItemRepository` để thao tác với bảng `order_items`. Khi cần truy vấn phục vụ báo cáo hoặc tìm kiếm số liệu xuyên nhiều bảng, có thể xây dựng read model/truy vấn riêng; điều đó không làm thay đổi nguyên tắc **thay đổi nghiệp vụ đi qua Order**.

## 6. Thực hiện use case qua application service

Service ứng dụng điều phối việc tải, thay đổi và lưu aggregate. Mọi thao tác phải dùng phương thức nghiệp vụ của `Order` thay vì xây dựng SQL cập nhật từng dòng từ bên ngoài.

~~~java
package com.example.sales.order;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;

    public OrderApplicationService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public Long createDraft(
            long customerId,
            String firstSku,
            int quantity,
            long unitPriceCents) {
        Order order = Order.draftFor(customerId);
        order.addItem(firstSku, quantity, unitPriceCents);

        Order saved = orders.save(order);
        return saved.getId();
    }

    @Transactional
    public void addItem(
            Long orderId,
            String sku,
            int quantity,
            long unitPriceCents) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException(
                "Order not found: " + orderId
            ));

        order.addItem(sku, quantity, unitPriceCents);
        orders.save(order);
    }

    @Transactional
    public void confirm(Long orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException(
                "Order not found: " + orderId
            ));

        order.confirm();
        orders.save(order);
    }
}
~~~

Đối với use case xác nhận:

1. `OrderRepository.findById(orderId)` tải root và danh sách item.
2. `order.confirm()` xác nhận bất biến “đơn ở DRAFT và có ít nhất một dòng”.
3. `OrderRepository.save(order)` ghi aggregate về database.

`@Transactional` đặt ranh giới transaction ở application service, có ích khi một use case thực hiện nhiều lời gọi repository hoặc thao tác SQL liên quan. Việc tải rồi lưu trong cùng một transaction **không tự thay thế** cơ chế kiểm soát cập nhật đồng thời; ví dụ sử dụng thêm `@Version` ở root.

### Minh họa vòng đời một đơn hàng

~~~java
Long orderId = service.createDraft(
    101L,
    "JAVA-BOOK",
    2,
    150_000L
);

service.addItem(orderId, "NOTEBOOK", 1, 40_000L);
service.confirm(orderId);

Order saved = orders.findById(orderId).orElseThrow();

System.out.println(saved.getStatus()); // CONFIRMED
System.out.println(saved.getItems().size()); // 2
System.out.println(saved.totalCents()); // 340000
~~~

Đoạn mã cuối giả định `service` và `orders` đã được Spring cung cấp qua dependency injection. Nó chỉ minh họa luồng sử dụng, không phải một ứng dụng có sẵn tất cả biến và bean.

Giá trị `340000` được tính bằng `2 × 150000 + 1 × 40000`. Sau khi xác nhận, `service.addItem(...)` trên cùng đơn sẽ bị `Order.requireDraft()` từ chối.

## 7. “Một đơn vị lưu trữ” nghĩa là gì khi save?

Hãy tưởng tượng một Order mới có hai item:

~~~text
Order (id chưa có)
  status = DRAFT
  customerId = 101
  items
    - JAVA-BOOK, quantity=2, unitPriceCents=150000
    - NOTEBOOK, quantity=1, unitPriceCents=40000
~~~

Khi gọi `orders.save(order)`, về mặt khái niệm Spring Data JDBC thực hiện các thao tác cần thiết để lưu:

~~~mermaid
sequenceDiagram
    participant App as Application Service
    participant Repo as OrderRepository
    participant DB as Relational Database
    App->>Repo: save(order)
    Repo->>DB: INSERT shop_orders (...)
    DB-->>Repo: generated order id
    Repo->>DB: INSERT order_items (..., order_id, line_position=0)
    Repo->>DB: INSERT order_items (..., order_id, line_position=1)
    Repo-->>App: saved Order
~~~

Đây là sơ đồ **ngữ nghĩa**, không phải bản cam kết chính xác về số câu SQL hay thứ tự nội bộ cho mọi phiên bản, cấu hình và kiểu aggregate. Điểm cần ghi nhớ là repository biết các item **thuộc về** root vì chúng được khai báo trong mapping của `Order`.

Nếu giao dịch thất bại trước khi commit, các thao tác ghi trong cùng transaction được rollback theo cơ chế của database. Mục tiêu là giữ các bảng của **một aggregate** ở trạng thái nhất quán sau mỗi lần lưu thành công.

### Khi Order đã tồn tại và item thay đổi

Spring Data JDBC **không sử dụng persistence context và dirty checking như JPA**. Với aggregate đã tồn tại, cách lưu mặc định có thể **xóa các bản ghi con đang được tham chiếu rồi chèn lại những bản ghi con theo trạng thái hiện tại**. Vì vậy:

- `save(order)` không có nghĩa “chỉ UPDATE đúng một dòng item vừa thay đổi”.
- Một thay đổi nhỏ với collection con có thể tạo nhiều thao tác ghi.
- ID do database cấp cho `OrderItem` có thể thay đổi nếu các hàng con bị xóa và chèn lại.
- Không nên dùng `order_items.id` như danh tính được các aggregate khác tham chiếu bền vững khi thiết kế dựa trên kiểu ghi này.

Nếu mỗi item có vòng đời dài, được nhiều bên tham chiếu và cần cập nhật độc lập với Order, đó là tín hiệu phải **xem xét lại ranh giới aggregate**, thay vì mặc định duy trì quan hệ sở hữu lớn.

Việc xóa/ghi lại item cũng ảnh hưởng đến trigger, audit log và hiệu năng. Với hệ thống có số item lớn hoặc lưu rất thường xuyên, cần đo lượng SQL thực tế và cân nhắc mô hình lưu trữ phù hợp. Trong bài này, một đơn hàng có số dòng vừa phải là mô hình phù hợp để minh họa.

## 8. Đảm bảo tính nhất quán và xử lý cập nhật đồng thời

### Bất biến ở root

Gọi `order.confirm()` trên một đơn không có item sẽ phát sinh `IllegalStateException`. Vì chưa gọi `save`, database không bị ghi sai trạng thái. Quy tắc này nằm ở root, vì chỉ root biết đồng thời **trạng thái đơn** và **danh sách dòng hàng**.

### Ràng buộc database

Các điều kiện trong DDL bổ sung một tầng bảo vệ:

- `NOT NULL` ngăn trường bắt buộc bị bỏ trống.
- `CHECK (quantity > 0)` và `CHECK (unit_price_cents >= 0)` ngăn số liệu không hợp lệ.
- `UNIQUE (order_id, sku)` ngăn SKU lặp lại trong cùng đơn.
- `FOREIGN KEY (order_id)` ngăn item tham chiếu đến Order không tồn tại.

Một số quy tắc như “đơn CONFIRMED không được sửa item” hoặc “đơn CONFIRMED phải có ít nhất một item” cần logic nghiệp vụ và chính sách ghi, vì ràng buộc cột đơn lẻ không biểu đạt đầy đủ ngữ nghĩa đó.

### Cập nhật đồng thời và @Version

Giả sử có hai request cùng tải `Order(id=15, version=4)`:

~~~text
Request A                       Request B
load Order version=4            load Order version=4
addItem("PEN", ...)             confirm()
save Order                      save Order
version chuyển sang 5          phát hiện version cũ -> xung đột
~~~

Với `@Version` trên root, Spring Data JDBC sử dụng optimistic locking khi cập nhật. Request lưu sau mà dùng phiên bản cũ sẽ nhận ngoại lệ thuộc nhóm `OptimisticLockingFailureException`. Ứng dụng nên trả thông báo xung đột, tải dữ liệu mới và yêu cầu thực hiện lại hành động theo quy tắc nghiệp vụ; không tự động ghi đè kết quả request đã thành công.

**Không nên chỉ tin vào @Transactional để tránh lost update.** Transaction bao bọc thao tác, còn version giúp phát hiện việc hai bên đã dựa trên hai bản đọc cũ của cùng aggregate.

### Ranh giới với Product, Customer và tồn kho

`Order` có thể tham chiếu `Customer` bằng `customerId` và `Product` bằng `sku`/`productId`, nhưng **không nhúng hai aggregate độc lập này thành danh sách object trong Order**. Khi xác nhận đơn cần giảm tồn kho, một application service phải phối hợp với aggregate tồn kho và chính sách giao dịch/sự kiện phù hợp.

Việc một use case sử dụng cả Order và Inventory **không tự động biến chúng thành một aggregate**. Khi xác định ranh giới, hãy hỏi: bất biến nào nhất thiết phải được duy trì cùng nhau, và đối tượng nào thực sự có vòng đời độc lập?

## 9. Một số lựa chọn thiết kế cần cân nhắc

### OrderItem là entity hay value object?

Ở bài này, `OrderItem` có ID và được mô hình hóa như **entity con**. Điều này hữu ích nếu nghiệp vụ phân biệt từng dòng hàng và muốn có trạng thái hay thao tác trên một dòng cụ thể.

Với mô hình đơn giản hơn, một dòng hàng chỉ là tổ hợp `(sku, quantity, price)` không cần nhận diện riêng. Khi ấy có thể thiết kế dòng hàng theo hướng **value object** bất biến. Dù vậy, cách nó được ánh xạ vào collection và khóa trong bảng vẫn cần phù hợp với Spring Data JDBC. **Không đánh đồng value object trong miền với bắt buộc lưu chung một hàng.**

### Có nên chứa toàn bộ Customer/Product object trong Order?

Thông thường **không** nếu Customer/Product là aggregate độc lập. Giữ tham chiếu bằng ID và snapshot dữ liệu giao dịch cần thiết giúp Order có phạm vi ghi rõ ràng, giảm vòng đời phụ thuộc và tránh truy cập object graph ngoài ranh giới.

### Có nên cho mọi entity một repository riêng?

Không. Repository ở mô hình hiện tại thuộc về **Order**. Nếu giao diện cần tìm các item theo SKU, có thể viết truy vấn đọc trên các bảng hoặc projection phục vụ báo cáo. Truy vấn đọc không nhất thiết phải đi qua các phương thức ghi của aggregate, nhưng các **thao tác thay đổi nghiệp vụ** phải duy trì bất biến của root.

### Có nên giữ totalCents ở bảng Order?

Ví dụ này **tính tổng từ các item** để tránh cập nhật thiếu đồng bộ. Nếu yêu cầu truy vấn hiệu năng hoặc báo cáo khiến tổng được lưu sẵn, cần có cơ chế bảo đảm tổng luôn được tính/cập nhật trong cùng luồng nghiệp vụ. Không đưa public setter cho phép client ghi tổng bất kỳ.

### Khi nào aggregate này quá lớn?

Nếu một Order chứa hàng nghìn item và thường xuyên cập nhật, chi phí lưu cả aggregate có thể tăng. Khi đó cần đánh giá số lượng item thực tế, cách thức ghi của Spring Data JDBC, các bất biến cần bảo vệ và khả năng chia trách nhiệm. Không nên chia aggregate chỉ vì có hai bảng; cũng không nên giữ mọi đối tượng liên quan trong Order chỉ vì muốn tải chúng bằng một repository.

## 10. Các lỗi phổ biến khi triển khai

| Cách làm | Hậu quả | Cách thiết kế trong bài |
|---|---|---|
| Tạo `OrderItemRepository` rồi sửa item trực tiếp | Bỏ qua trạng thái và bất biến của Order | Thay đổi item qua `Order.addItem/removeItem` |
| Coi một bảng là một aggregate | Chia đôi thao tác nghiệp vụ có quan hệ chặt | Một `Order` sở hữu nhiều item dù có hai bảng |
| Dùng `@OneToMany`/`@ManyToOne` theo cách JPA | Hiểu nhầm cơ chế mapping của Spring Data JDBC | Dùng `@MappedCollection` và tham chiếu ID đúng ranh giới |
| Đưa `Customer`/`Product` trực tiếp vào object graph được sở hữu | Mở rộng aggregate ngoài ý muốn | Giữ customerId/SKU hoặc productId |
| Cho client sửa `List<OrderItem>` trả về | Có thể thay đổi state ngoài quy tắc của root | Trả bản sao không sửa được, chỉ root có mutation |
| Cho rằng `save(order)` cập nhật tối thiểu mỗi item | Bất ngờ về lượng SQL và ID con | Hiểu cơ chế ghi aggregate của Spring Data JDBC |
| Không có kiểm soát concurrency | Hai request có thể ghi đè dữ liệu cũ | `@Version` trên Order, xử lý lỗi optimistic lock |
| Chỉ đặt ràng buộc trong code hoặc chỉ đặt trong DB | Thiếu lớp bảo vệ ở miền hoặc ở dữ liệu | Kết hợp bất biến trên root và FK/CHECK/UNIQUE |
| Luôn nhúng giá hiện tại của Product vào Order | Tổng giá cũ thay đổi khi catalog cập nhật | Lưu đơn giá snapshot trong `OrderItem` |

## 11. Bài thực hành và câu hỏi tự kiểm tra

Từ mẫu trên, hãy thực hiện lần lượt:

1. Tạo đơn `DRAFT` cho khách `101` và thêm `SKU-A` số lượng `2`, giá `120000`; thêm `SKU-B` số lượng `1`, giá `50000`. Kiểm tra tổng tiền là `290000`.
2. Lưu đơn qua `OrderRepository`, sau đó dùng `findById` để kiểm tra đã đọc được root và đúng hai item từ bảng con.
3. Truy vấn SQL `shop_orders` và `order_items`; xác nhận cả hai dòng hàng có cùng `order_id`, và `line_position` là `0` rồi `1`.
4. Thử thêm `SKU-A` lần hai. Xác định bất biến nào ngăn thao tác, trước khi SQL được phát sinh.
5. Xác nhận đơn, rồi thử xóa `SKU-B`. Dự đoán ngoại lệ sẽ xuất hiện ở phương thức nào.
6. Mở hai phiên xử lý cùng một Order; ở phiên đầu thêm item và lưu; ở phiên sau lưu từ bản cũ. Quan sát cách `@Version` phát hiện xung đột.
7. Thảo luận: nếu một `OrderItem` cần tự giao hàng, hoàn tiền và được tra cứu độc lập trong nhiều năm thì ranh giới aggregate hiện tại có còn thích hợp không?

Một truy vấn SQL giúp quan sát dữ liệu từ hai bảng:

~~~sql
SELECT
    o.id AS order_id,
    o.status,
    o.version,
    i.line_position,
    i.sku,
    i.quantity,
    i.unit_price_cents
FROM shop_orders o
JOIN order_items i ON i.order_id = o.id
WHERE o.id = :order_id
ORDER BY i.line_position;
~~~

Trong truy vấn trên, `:order_id` là **named parameter minh họa**; khi chạy trực tiếp bằng SQL client, hãy thay bằng một ID thực tế hoặc bind parameter bằng công cụ tương ứng. Đối chiếu dữ liệu trả về với danh sách `saved.getItems()` để thấy sự khác biệt giữa **object graph của aggregate** và **các hàng dữ liệu của bảng quan hệ**.

## 12. Ghi nhớ mô hình

Mối quan hệ cốt lõi của bài có thể đọc như sau:

~~~text
Use case
   -> OrderRepository.findById(...)
   -> Order.addItem(...) / Order.removeItem(...) / Order.confirm()
   -> OrderRepository.save(order)
       -> shop_orders       (root)
       -> order_items       (thành phần được root sở hữu)
~~~

Thiết kế `Order` và `OrderItem` như **một đơn vị lưu trữ** nghĩa là chọn **Order làm cửa vào duy nhất cho các thay đổi nghiệp vụ của đơn**, giữ invariant xuyên suốt root và danh sách item, đồng thời để Spring Data JDBC quản lý ánh xạ chúng xuống nhiều bảng. Một repository, một aggregate và một ranh giới nhất quán có thể đi cùng nhiều entity, nhiều hàng dữ liệu và nhiều câu SQL.
