# Ánh xạ khóa Map từ thuộc tính của đối tượng liên quan trong JPA

Trong Java, `Map<K, V>` là cấu trúc dữ liệu cho phép tìm một giá trị `V` bằng khóa `K`. Khi thiết kế entity JPA, một tập hợp các entity liên quan cũng có thể được biểu diễn bằng `Map` thay vì `List` hoặc `Set`. Điều này đặc biệt hữu ích khi nghiệp vụ thường xuyên tra cứu phần tử theo một thuộc tính có ý nghĩa, chẳng hạn mã sản phẩm, mã ngôn ngữ, mã nhân viên hoặc mã dòng công việc.

Ví dụ một kho hàng có nhiều dòng tồn kho. Mỗi dòng `StockItem` có một mã SKU; trong một kho, SKU là duy nhất. Ở Java, ta muốn truy cập:

~~~java
StockItem item = warehouse.getItemsBySku().get("SKU-001");
~~~

Trong cơ sở dữ liệu, có thể chỉ cần hai bảng:

~~~text
warehouse                      stock_item
------------------------       ----------------------------
id (PK)                   <--- warehouse_id (FK)
name                            id (PK)
                                sku (VARCHAR)
                                quantity
~~~

JPA hỗ trợ mô hình này qua **`@MapKey(name = "sku")`**: khóa `Map` được **suy ra từ thuộc tính persistent `sku` của entity giá trị `StockItem`**. Không cần tạo thêm một cột riêng để lưu map key nếu thuộc tính `sku` đã có trong bảng `stock_item`.

Điểm cốt lõi của bài học:

> **`@MapKey(name = "...")` chọn một thuộc tính của entity liên quan làm khóa của `Map`; nó không tạo ra định danh mới và cũng không tự bảo đảm thuộc tính đó là duy nhất hay bất biến.**

Bài này tập trung vào việc chuyển từ yêu cầu nghiệp vụ sang mapping, phân biệt `@MapKey` với `@MapKeyColumn`, xác định phía sở hữu quan hệ, xử lý thao tác thêm/xóa/đổi khóa, truy vấn JPQL, constraint cơ sở dữ liệu và những giới hạn cần lưu ý khi dùng `Map` trong ORM.

## 1. Tại sao dùng `Map` trong quan hệ entity?

Giả sử một `Warehouse` có nhiều dòng `StockItem`. Có ba cách khai báo thông dụng ở Java:

~~~java
private List<StockItem> items;
private Set<StockItem> items;
private Map<String, StockItem> itemsBySku;
~~~

Cùng mô tả quan hệ một-nhiều, nhưng mỗi cấu trúc truyền tải một ý nghĩa khác nhau.

| Kiểu Java | Cách truy cập đặc trưng | Cần chú ý |
|---|---|---|
| `List<StockItem>` | Lặp qua các dòng, có thể quan tâm thứ tự | Tìm theo SKU thường cần duyệt hoặc truy vấn riêng |
| `Set<StockItem>` | Tập các phần tử không trùng theo quy tắc `equals/hashCode` | Không có phép tra cứu trực tiếp bằng SKU |
| `Map<String, StockItem>` | `get("SKU-001")` | Mỗi khóa duy nhất trong Map; cần giữ khóa đồng bộ với dữ liệu của entity |

`Map` đặc biệt phù hợp nếu:

1. Nghiệp vụ sử dụng một khóa tra cứu ổn định và có ý nghĩa.
2. Trong phạm vi entity cha, mỗi khóa tương ứng tối đa một entity con.
3. Code thường xuyên truy cập theo khóa thay vì duyệt toàn bộ tập hợp.
4. Mô hình muốn thể hiện rõ ràng quy tắc “mỗi kho có tối đa một dòng cho cùng SKU”.

Tuy nhiên, `Map` trong Java **không tự tạo UNIQUE constraint ở database**. Và `Map.get(...)` chỉ truy cập dữ liệu trong collection đã nạp vào persistence context; nó không mặc định là một truy vấn SQL tối ưu có điều kiện `WHERE sku = ?`.

### 1.1. Khóa của `Map` không nhất thiết là khóa chính của entity

Ví dụ:

~~~text
StockItem.id    = 5001       -- khóa chính kỹ thuật
StockItem.sku   = "SKU-001"  -- mã nghiệp vụ trong phạm vi Warehouse
Map key         = "SKU-001"
~~~

`StockItem.id` định danh bản ghi ở DB; `StockItem.sku` làm khóa tra cứu trong collection của kho. Hai giá trị độc lập. Không phải vì dùng `Map` mà JPA tự thay thế primary key của `StockItem` bằng `sku`.

### 1.2. Bài toán quan trọng là tính duy nhất trong phạm vi cha

Hai kho khác nhau có thể cùng một SKU:

~~~text
warehouse_id | stock_item_id | sku       | quantity
-------------+---------------+-----------+---------
10           | 501           | SKU-001   | 15
10           | 502           | SKU-002   |  7
20           | 503           | SKU-001   | 30
~~~

Trong mỗi kho, một SKU chỉ được xuất hiện một lần. Nhưng SKU không nhất thiết duy nhất trên **toàn hệ thống**. Do đó, constraint phù hợp thường là **`UNIQUE(warehouse_id, sku)`**, không phải chỉ `UNIQUE(sku)`.

## 2. Cơ chế của `@MapKey(name = "...")`

`@MapKey` là annotation chuẩn của Jakarta Persistence, nằm trong package `jakarta.persistence`. Thuộc tính `name` xác định **tên thuộc tính persistent của entity được dùng làm value trong Map**.

Ví dụ:

~~~java
@OneToMany(mappedBy = "warehouse")
@MapKey(name = "sku")
private Map<String, StockItem> itemsBySku = new HashMap<>();
~~~

Có thể đọc annotation theo cách sau:

- `@OneToMany`: `Warehouse` liên kết đến nhiều `StockItem`.
- `mappedBy = "warehouse"`: phía sở hữu foreign key là thuộc tính `StockItem.warehouse`.
- `@MapKey(name = "sku")`: khi các `StockItem` được biểu diễn bằng `Map`, giá trị khóa lấy từ `StockItem.sku`.
- `Map<String, StockItem>`: khóa Java là `String`, giá trị là `StockItem`.

Với một entity con:

~~~java
StockItem item = ...;
String key = item.getSku();
~~~

về mặt ý nghĩa, phần tử của map là:

~~~java
itemsBySku.put(item.getSku(), item);
~~~

**Chú ý:** Đây là minh họa mô hình dữ liệu, không có nghĩa provider bắt buộc gọi chính phương thức `Map.put` này khi nạp entity. JPA quản lý persistent collection theo cơ chế riêng và có thể thay collection bằng wrapper/proxy do provider cung cấp.

### 2.1. Tên trong `name` là tên thuộc tính Java

Cấu hình đúng:

~~~java
@MapKey(name = "sku")
private Map<String, StockItem> itemsBySku;
~~~

Nếu `StockItem` khai báo:

~~~java
@Column(name = "stock_keeping_unit")
private String sku;
~~~

thì `@MapKey(name = "sku")` vẫn dùng **`sku`**, không dùng `stock_keeping_unit`. Tên sau là tên cột SQL.

Phân biệt ba tầng tên:

| Cấu hình | Tên | Vai trò |
|---|---|---|
| `@MapKey(name = "sku")` | `sku` | Thuộc tính Java của entity giá trị |
| `@Column(name = "stock_keeping_unit")` | `stock_keeping_unit` | Tên cột SQL lưu thuộc tính đó |
| `@JoinColumn(name = "warehouse_id")` | `warehouse_id` | Cột FK trỏ tới entity cha |
| `mappedBy = "warehouse"` | `warehouse` | Thuộc tính Java ở phía owning side |
| `@Id private Long id` | `id` | Định danh kỹ thuật của bản ghi con |

Đặt `@MapKey(name = "stock_keeping_unit")` trong khi entity chỉ có field `sku` thường dẫn tới lỗi metadata hoặc mapping, vì JPA đang tìm một thuộc tính persistent có tên không tồn tại.

### 2.2. Thuộc tính dùng làm khóa phải phù hợp với kiểu `K`

Ví dụ `StockItem.sku` là `String`:

~~~java
private String sku;
~~~

thì khai báo hợp lý:

~~~java
Map<String, StockItem>
~~~

Nếu khóa lấy từ một thuộc tính `Long`:

~~~java
@MapKey(name = "externalId")
private Map<Long, StockItem> itemsByExternalId;
~~~

Nếu khóa lấy từ thuộc tính enum:

~~~java
@MapKey(name = "state")
private Map<StockState, StockItem> itemsByState;
~~~

thì phải xem xét liệu mỗi trạng thái có thật sự tương ứng tối đa một StockItem trong một Warehouse hay không. Nếu nhiều dòng đều có `state = AVAILABLE`, `Map<StockState, StockItem>` không đại diện đầy đủ được tập dữ liệu đó.

**Không chọn khóa chỉ vì thuộc tính tồn tại; phải chọn thuộc tính mà nghiệp vụ bảo đảm tính duy nhất phù hợp với cấu trúc `Map`.**

## 3. Ví dụ hoàn chỉnh: Warehouse ánh xạ các StockItem theo SKU

### 3.1. Thiết kế database

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE warehouse (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(150) NOT NULL
);

CREATE TABLE stock_item (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    warehouse_id BIGINT NOT NULL,
    sku VARCHAR(40) NOT NULL,
    quantity INTEGER NOT NULL,

    CONSTRAINT fk_stock_item_warehouse
        FOREIGN KEY (warehouse_id)
        REFERENCES warehouse(id),

    CONSTRAINT uk_stock_item_warehouse_sku
        UNIQUE (warehouse_id, sku),

    CONSTRAINT ck_stock_item_quantity
        CHECK (quantity >= 0)
);
~~~

Ý nghĩa:

- `stock_item.id` là khóa chính riêng của StockItem.
- `warehouse_id` là FK tới `Warehouse.id`.
- `sku` là mã nghiệp vụ được dùng làm khóa Map.
- `UNIQUE(warehouse_id, sku)` bảo đảm không tồn tại hai dòng cùng SKU trong một kho.
- `quantity >= 0` là một quy tắc lưu trữ; ứng dụng cũng nên kiểm tra trước khi ghi.

Sơ đồ:

~~~text
Warehouse(id = 10)
  |
  +-- itemsBySku["SKU-001"] --> StockItem(id=501, sku="SKU-001")
  |
  +-- itemsBySku["SKU-002"] --> StockItem(id=502, sku="SKU-002")
  |
  +-- itemsBySku["SKU-003"] --> StockItem(id=503, sku="SKU-003")

Bảng stock_item chỉ có một cột sku, không có cột map_key bổ sung.
~~~

### 3.2. Entity `Warehouse`

~~~java
package com.example.inventory.domain;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.MapKey;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;

import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

@Entity
@Table(name = "warehouse")
public class Warehouse {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "name", nullable = false, length = 150)
    private String name;

    @OneToMany(
        mappedBy = "warehouse",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    @MapKey(name = "sku")
    private Map<String, StockItem> itemsBySku = new HashMap<>();

    protected Warehouse() {
        // Constructor cho JPA.
    }

    public Warehouse(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Warehouse name is required");
        }
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Map<String, StockItem> getItemsBySku() {
        return Collections.unmodifiableMap(itemsBySku);
    }

    public StockItem getItem(String sku) {
        return itemsBySku.get(sku);
    }

    public void addItem(String sku, int quantity) {
        if (itemsBySku.containsKey(sku)) {
            throw new IllegalArgumentException(
                "SKU already exists in this warehouse: " + sku
            );
        }

        StockItem item = new StockItem(this, sku, quantity);
        itemsBySku.put(item.getSku(), item);
    }

    public void removeItem(String sku) {
        StockItem removed = itemsBySku.remove(sku);
        if (removed != null) {
            removed.detachFromWarehouse();
        }
    }
}
~~~

Các điểm quan trọng:

1. `@OneToMany(mappedBy = "warehouse")` xác định chiều ngược của quan hệ; phía StockItem sẽ quản lý FK.
2. `@MapKey(name = "sku")` dùng thuộc tính `StockItem.sku` làm khóa Map.
3. `cascade = ALL` và `orphanRemoval = true` là lựa chọn **vòng đời**, phù hợp với ví dụ một dòng tồn kho phụ thuộc Warehouse. Nếu hệ thống cần lưu lịch sử hoặc không cho xóa dòng, chính sách sẽ khác.
4. `addItem` khởi tạo StockItem đã liên kết tới Warehouse và chèn bằng đúng `item.getSku()`.
5. `getItemsBySku()` trả về view chỉ đọc để caller không tùy tiện phá vỡ invariant. Trong một entity managed, không nên thay hẳn collection do provider quản lý bằng Map khác.
6. `removeItem` gỡ phần tử khỏi Map và cập nhật mối quan hệ trong bộ nhớ; `orphanRemoval` cho phép JPA xóa entity phụ thuộc theo vòng đời ở thời điểm thích hợp.

Ở ví dụ, SKU đã được kiểm tra theo một định dạng nghiệp vụ trong StockItem. Với hệ thống thực tế, có thể chuẩn hóa đầu vào tại boundary/service trước khi gọi `getItem` hoặc `removeItem`, để tránh khác biệt viết hoa/thường và khoảng trắng.

### 3.3. Entity `StockItem`

~~~java
package com.example.inventory.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import java.util.Locale;

@Entity
@Table(
    name = "stock_item",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_stock_item_warehouse_sku",
        columnNames = {"warehouse_id", "sku"}
    )
)
public class StockItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "warehouse_id", nullable = false)
    private Warehouse warehouse;

    @Column(name = "sku", nullable = false, length = 40)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected StockItem() {
        // Constructor cho JPA.
    }

    StockItem(Warehouse warehouse, String sku, int quantity) {
        if (warehouse == null) {
            throw new IllegalArgumentException("Warehouse is required");
        }
        if (sku == null) {
            throw new IllegalArgumentException("SKU is required");
        }

        String normalized = sku.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("[A-Z0-9-]{1,40}")) {
            throw new IllegalArgumentException("Invalid SKU: " + sku);
        }
        if (quantity < 0) {
            throw new IllegalArgumentException(
                "Quantity must not be negative"
            );
        }

        this.warehouse = warehouse;
        this.sku = normalized;
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public Warehouse getWarehouse() {
        return warehouse;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public void adjustQuantity(int delta) {
        int next = Math.addExact(quantity, delta);
        if (next < 0) {
            throw new IllegalArgumentException(
                "Insufficient stock"
            );
        }
        this.quantity = next;
    }

    void detachFromWarehouse() {
        this.warehouse = null;
    }
}
~~~

`StockItem` có PK riêng nhưng vẫn có thuộc tính nghiệp vụ `sku`, và **chính `sku` làm khóa Map**. Người đọc không nên lẫn:

~~~text
Warehouse.itemsBySku key       -> StockItem.sku
StockItem primary key          -> StockItem.id
StockItem foreign key          -> stock_item.warehouse_id
~~~

Trong ví dụ, constructor cho phép gán `sku` đúng một lần và không công khai setter sửa SKU. Cách này có chủ đích: **khóa Map nên ổn định sau khi entity được đưa vào collection**.

Lưu ý về `detachFromWarehouse`: helper chỉ dùng khi entity đang được tách khỏi collection có `orphanRemoval = true`. Entity bị orphan được dự kiến xóa khi flush, không phải trở thành dòng tồn kho hợp lệ với FK null. Nếu không dùng orphanRemoval hoặc cần chuyển StockItem sang kho khác, phải thiết kế thao tác và constraint riêng.

### 3.4. Lưu một kho cùng các dòng tồn

Sử dụng Spring:

~~~java
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WarehouseService {

    private final EntityManager entityManager;

    public WarehouseService(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional
    public Long createWarehouse() {
        Warehouse warehouse = new Warehouse("Kho phía Nam");

        warehouse.addItem("SKU-001", 15);
        warehouse.addItem("SKU-002", 7);

        entityManager.persist(warehouse);

        // Cascade PERSIST lưu các StockItem mới.
        // Không phải gọi persist từng phần tử nếu mapping cascade đúng.
        return warehouse.getId();
    }
}
~~~

`@Transactional` là annotation của Spring, không phải JPA thuần. Nếu method mở transaction ngoài cùng và gọi qua Spring proxy, transaction manager sẽ commit khi luồng xử lý hoàn tất bình thường; nếu tham gia transaction bao ngoài thì ID trả về **không chứng minh transaction ngoài đã commit**.

Trong JPA `RESOURCE_LOCAL` thuần, cần điều khiển transaction bằng `EntityTransaction` tương ứng. Việc `persist`/`flush` và cấp ID có thời điểm riêng, không nên đồng nhất với commit.

### 3.5. Đọc từ database

~~~java
Warehouse warehouse =
    entityManager.find(Warehouse.class, warehouseId);

StockItem first = warehouse.getItemsBySku().get("SKU-001");
~~~

Nếu `Warehouse` đã được tải và Map được khởi tạo, JPA provider sẽ vật chất hóa các mục Map với khóa lấy từ `StockItem.sku`.

Tuy nhiên, `@OneToMany` mặc định LAZY, và `getItemsBySku().get(...)` **có thể khiến ORM tải cả collection**, tùy provider và loại persistent Map. Đừng mặc định phép `Map.get` này luôn được dịch thành SQL có `WHERE sku = ?` mà không nạp các phần tử khác.

Khi chỉ cần một StockItem theo SKU ở kho lớn, một truy vấn có điều kiện rõ ràng có thể hiệu quả và dễ kiểm soát hơn.

## 4. Map key là thuộc tính của *value entity*, không phải cột thứ hai

Cách đọc chuẩn của ánh xạ:

~~~java
@OneToMany(mappedBy = "warehouse")
@MapKey(name = "sku")
private Map<String, StockItem> itemsBySku;
~~~

giống việc định nghĩa:

~~~text
Key       = stockItem.sku
Value     = stockItem
Parent    = stockItem.warehouse
~~~

Do đó:

- Khóa Map được lấy từ thuộc tính `sku` **đã được ánh xạ** của StockItem.
- Cột `stock_item.sku` vừa lưu dữ liệu nghiệp vụ vừa là nguồn khóa Map.
- Không cần tạo cột `stock_item.map_key` thứ hai chỉ để JPA biết dùng khóa nào.
- Không cần `@Id` trên `sku`; PK của StockItem vẫn là `id`.
- Nếu muốn bảo đảm khóa duy nhất **trong mỗi Warehouse**, cần constraint tương ứng ở schema.

Một cấu hình không phù hợp:

~~~java
@OneToMany(mappedBy = "warehouse")
@MapKey(name = "sku")
@MapKeyColumn(name = "another_sku")
private Map<String, StockItem> itemsBySku;
~~~

`@MapKey` đã yêu cầu lấy khóa từ property của StockItem, còn `@MapKeyColumn` phục vụ một kiểu lưu khóa Map khác. Không nên phối hợp hai annotation với hai nguồn khóa mâu thuẫn cho cùng collection. Hãy xác định rõ **khóa được suy ra từ value entity hay được lưu độc lập ở cấu trúc collection**.

## 5. `@MapKey` không tham số: Khóa lấy từ primary key của entity giá trị

`@MapKey` có thuộc tính `name` mặc định là chuỗi rỗng. Khi dùng:

~~~java
@OneToMany(mappedBy = "warehouse")
@MapKey
private Map<Long, StockItem> itemsById;
~~~

trong bối cảnh value là entity `StockItem` có `@Id Long id`, JPA có thể dùng **khóa chính của StockItem** làm khóa Map.

So sánh:

~~~java
@MapKey(name = "sku")
private Map<String, StockItem> itemsBySku;
~~~

và:

~~~java
@MapKey
private Map<Long, StockItem> itemsById;
~~~

| Cấu hình | Nguồn Map key | Kiểu khóa | Đặc điểm |
|---|---|---|---|
| `@MapKey(name = "sku")` | `StockItem.sku` | `String` | Mã nghiệp vụ có ý nghĩa với người dùng |
| `@MapKey` hoặc `@MapKey(name = "")` | `StockItem.id` | `Long` | Dựa trên PK kỹ thuật của entity con |

**Cẩn thận với generated ID:** trước khi JPA cấp `id`, một `new StockItem(...)` có thể có `id == null`. Nếu application tự chèn item vào Map keyed by ID trước persist, nó có thể đưa vào dưới khóa null hoặc khóa chưa ổn định. Khi ID sinh ra sau đó, Map Java không tự đổi khóa theo giá trị mới.

Vì vậy, dùng mã nghiệp vụ được gán từ lúc tạo và không thay đổi như `sku` thường thuận tiện hơn khi cần xây dựng một Map các entity mới trước persist. Với khóa chính sinh tự động, cần thiết kế thời điểm materialize collection hoặc chọn cấu trúc `List/Set` rồi truy vấn theo ID.

## 6. Phân biệt `@MapKey` và `@MapKeyColumn`

Hai annotation có mục đích khác nhau.

### 6.1. `@MapKey(name = "...")`: Khóa **đã là một thuộc tính** của entity value

~~~java
@OneToMany(mappedBy = "warehouse")
@MapKey(name = "sku")
private Map<String, StockItem> itemsBySku;
~~~

Nguồn khóa:

~~~text
stock_item.sku
  |
  +-- property StockItem.sku
  |
  +-- key của Warehouse.itemsBySku
~~~

Cột `sku` đã có vì đó là một thuộc tính persistent trên StockItem.

### 6.2. `@MapKeyColumn`: Khóa có cột riêng trong cấu trúc lưu collection

Ví dụ các ghi chú của Warehouse theo mã ngôn ngữ. Mỗi mục là một chuỗi, **không có entity value riêng**:

~~~java
@ElementCollection
@CollectionTable(
    name = "warehouse_note",
    joinColumns = @JoinColumn(name = "warehouse_id")
)
@MapKeyColumn(name = "locale_code", length = 10)
@Column(name = "note_text", length = 500)
private Map<String, String> notesByLocale = new HashMap<>();
~~~

Schema minh họa:

~~~sql
CREATE TABLE warehouse_note (
    warehouse_id BIGINT NOT NULL
        REFERENCES warehouse(id),
    locale_code VARCHAR(10) NOT NULL,
    note_text VARCHAR(500),
    PRIMARY KEY (warehouse_id, locale_code)
);
~~~

Ở đây:

- `Map key` là `locale_code`, nằm trong bảng collection `warehouse_note`.
- `Map value` là chuỗi `note_text`, không phải một entity có field `localeCode` riêng.
- `@MapKeyColumn` ánh xạ khóa Map sang một cột cơ bản riêng.

### 6.3. Bảng so sánh

| Tiêu chí | `@MapKey(name = "...")` | `@MapKeyColumn(name = "...")` |
|---|---|---|
| Nguồn khóa | Thuộc tính persistent của entity value | Cột dùng để lưu khóa của Map |
| Ví dụ | `StockItem.sku` | `warehouse_note.locale_code` |
| Thường dùng với | Map chứa entity value trong association | Map có khóa basic trong element collection hoặc mapping collection phù hợp |
| Có cột khóa Map tách riêng khỏi thuộc tính value? | Không, dùng cột của thuộc tính value | Có một cột lưu map key |
| `name` chỉ cái gì? | Tên property Java | Tên cột database |
| Sai lầm điển hình | Truyền tên cột SQL vào `name` | Dùng để chọn field của entity value |

Không dùng `@MapKeyColumn` chỉ vì thấy chữ “Map” nếu nhu cầu thật là “lấy `sku` của StockItem làm khóa”.

## 7. Phân biệt `@MapKey(name)` và `@MapKeyJoinColumn`

Có những Map mà **khóa là một entity**, chẳng hạn `Map<Product, StockItem>`. Nếu giá trị `StockItem` đã có thuộc tính liên kết `product`, có thể muốn khóa Map lấy trực tiếp từ chính liên kết đó:

~~~java
// Trong StockItem:
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "product_id", nullable = false)
private Product product;

// Trong Warehouse:
@OneToMany(mappedBy = "warehouse")
@MapKey(name = "product")
private Map<Product, StockItem> itemsByProduct;
~~~

Ở đây `@MapKey(name = "product")` chọn **thuộc tính `StockItem.product`**. Khóa Map là entity Product; kiểu `K` trong Map phải khớp.

Cách này khác `@MapKeyJoinColumn`, dùng để cấu hình **khóa Map là entity reference với join column riêng** trong mapping nơi khóa không được dẫn xuất từ property của value entity theo cách trên.

Ví dụ so sánh về mặt thiết kế:

| Yêu cầu | Cách suy nghĩ |
|---|---|
| Khóa Map là `StockItem.sku` | `@MapKey(name = "sku")` |
| Khóa Map là `StockItem.product` | `@MapKey(name = "product")` |
| Map có khóa tham chiếu entity riêng cần ánh xạ bằng join column của map | Cân nhắc `@MapKeyJoinColumn` trong cấu trúc association/collection phù hợp |
| Map có khóa basic độc lập với value | Cân nhắc `@MapKeyColumn` |

**Không nhầm `@MapKeyJoinColumn` với `@JoinColumn`** trên `@ManyToOne` ở StockItem. `@JoinColumn(name = "warehouse_id")` trên `StockItem.warehouse` quyết định FK từ StockItem tới cha; nó không nói Map nên được index bằng SKU hay Product.

Khi dùng entity làm Map key, cần đặc biệt chú ý `equals/hashCode` và identity của entity key. Khóa không ổn định có thể khiến `Map.get(...)` không hoạt động như kỳ vọng.

## 8. Vị trí annotation và owning side của quan hệ

Với ánh xạ:

~~~java
// Warehouse
@OneToMany(mappedBy = "warehouse")
@MapKey(name = "sku")
private Map<String, StockItem> itemsBySku;

// StockItem
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "warehouse_id", nullable = false)
private Warehouse warehouse;
~~~

phía sở hữu liên kết tới warehouse là `StockItem.warehouse`. `Warehouse.itemsBySku` là phía nghịch (`inverse side`) vì có `mappedBy`.

### 8.1. `mappedBy` và `@MapKey(name)` trỏ tới hai thuộc tính khác nhau

- `mappedBy = "warehouse"`: field **quan hệ cha** trên StockItem. Nó quyết định FK.
- `@MapKey(name = "sku")`: field **giá trị khóa Map** trên StockItem. Nó quyết định cách tổ chức collection ở Java.

Cả hai đều dùng tên property Java nhưng có ý nghĩa khác nhau. Có thể hình dung:

~~~text
Warehouse.itemsBySku
    |-- mappedBy="warehouse"
    |      |
    |      +---- StockItem.warehouse --> stock_item.warehouse_id (FK)
    |
    +-- @MapKey(name="sku")
           |
           +---- StockItem.sku -------> stock_item.sku (map key)
~~~

### 8.2. Cập nhật owning side là điều cần thiết

Nếu chỉ làm:

~~~java
warehouse.getItemsBySku().put("SKU-001", item);
~~~

trong khi `item.warehouse` vẫn là `null`, phía sở hữu FK chưa được thiết lập. Hơn nữa, việc cho caller truy cập trực tiếp Map mutable có thể phá vỡ invariant và làm orphan removal xảy ra ngoài ý muốn.

Nên dùng helper để:

1. Đảm bảo SKU hợp lệ, đúng định dạng.
2. Từ chối khóa trùng.
3. Gán `item.warehouse`.
4. Chèn `item` dưới đúng `item.getSku()`.
5. Cập nhật hai phía khi loại bỏ quan hệ.
6. Thực hiện trong transaction thích hợp khi entity đang managed.

**`@MapKey` không thay thế `mappedBy` hoặc việc duy trì owning side.**

### 8.3. Field access và property access

JPA có thể dùng field access (ví dụ `@Id` trên field) hoặc property access (ví dụ `@Id` trên getter). Đặt `@MapKey` cạnh annotation ánh xạ quan hệ đúng theo access strategy đang sử dụng:

~~~java
// Field access:
@OneToMany(mappedBy = "warehouse")
@MapKey(name = "sku")
private Map<String, StockItem> itemsBySku;
~~~

Hoặc:

~~~java
// Property access:
@OneToMany(mappedBy = "warehouse")
@MapKey(name = "sku")
public Map<String, StockItem> getItemsBySku() {
    return itemsBySku;
}
~~~

Không rải annotation lên field và getter một cách không nhất quán. Nếu cần thay đổi access strategy ở một vị trí đặc biệt, dùng `@Access` theo quy tắc của JPA.

## 9. Tại sao khóa Map nên bất biến hoặc ít thay đổi?

Đây là một trong những điểm dễ sai nhất của `@MapKey(name)`.

Giả sử Map đã chứa:

~~~java
StockItem item = warehouse.getItemsBySku().get("SKU-001");
// Map hiện có: "SKU-001" -> item
~~~

Nếu code sau đó đổi `item.sku` thành `"SKU-999"`:

~~~java
item.setSku("SKU-999");
~~~

thì Java Map đang tồn tại trong bộ nhớ **không tự cập nhật khóa** thành `"SKU-999"`. Nó có thể vẫn giữ entry `"SKU-001" -> item` đến khi collection được tải lại hoặc được ứng dụng điều chỉnh.

Kết quả gây bất ngờ:

~~~text
StockItem.sku               = "SKU-999"
itemsBySku.containsKey("SKU-001") = true  (có thể trong Map đã load)
itemsBySku.containsKey("SKU-999") = false
~~~

JPA xử lý thuộc tính entity và trạng thái Map như những phần của persistence context, nhưng **không bảo đảm tự động re-key Map ngay lúc property được sửa**. Theo ngữ nghĩa `@MapKey`, sau khi tải collection, sự thay đổi thuộc tính được dùng làm khóa không tự phản ánh ngay trong các khóa của Map đang nằm trong bộ nhớ.

### 9.1. Giải pháp đơn giản: Chọn thuộc tính ổn định

Trong ví dụ kho hàng:

- Xem SKU như mã nghiệp vụ định danh một StockItem trong Warehouse.
- Không công khai setter `setSku` trên StockItem đang persistent.
- Nếu cần sửa mã SKU do lỗi nhập liệu, thiết kế operation riêng có kiểm soát.
- Khi thay đổi thật sự diễn ra, bảo đảm transaction, constraint DB và Map trong bộ nhớ nhất quán.
- Nếu SKU thay đổi có thể xảy ra thường xuyên, cân nhắc dùng khóa Map khác ổn định hơn hoặc dùng `List/Set` và query theo SKU.

### 9.2. Có nên remove key cũ rồi put key mới?

Một số mã Java viết:

~~~java
StockItem item = itemsBySku.remove(oldSku);
item.changeSku(newSku);
itemsBySku.put(newSku, item);
~~~

Về mặt Java, thao tác này có thể tạo đúng Map, nhưng **không nên áp dụng máy móc trên persistent Map có `orphanRemoval = true`**. Khi phần tử bị remove khỏi association, provider có thể đánh dấu entity là orphan để xóa; việc thêm lại cùng object dưới khóa mới trong một flush cycle có thể gặp hành vi không mong muốn, phụ thuộc timing và provider.

Nếu nghiệp vụ cho phép đổi mã:

1. Ưu tiên một API domain rõ ràng, không mở setter tự do.
2. Hiểu giới hạn `orphanRemoval` và vòng đời của StockItem.
3. Thực hiện thao tác trong transaction, tránh các trạng thái trung gian bị flush sai.
4. Kiểm tra unique constraint với SKU mới.
5. Nếu cần, thiết kế cơ chế thay thế/xóa-tạo có chủ đích hoặc chọn mô hình khác.
6. Quan sát hành vi của provider thực tế đối với persistent collection.

Với khóa biến động nhiều lần, dùng Map derived key có thể không phải lựa chọn thuận tiện nhất.

### 9.3. Map key từ thuộc tính liên quan cũng có thể bị thay đổi gián tiếp

Nếu sử dụng `@MapKey(name = "product")` và khóa là entity `Product`, việc sửa `StockItem.product` sang Product khác cũng là thay đổi nguồn key. Map đã load có thể không tự re-key.

Ngoài ra, nếu entity key dùng `equals/hashCode` dựa trên ID chưa được cấp, việc khóa thay đổi hash sau persist có thể làm Map dựa trên hash bị lỗi lookup. Cần thiết kế equality ổn định và không thay đổi khóa sau khi đã đưa vào Map.

## 10. Ràng buộc duy nhất ở tầng database là cần thiết

Java Map chỉ có một value cho mỗi key, nhưng nhiều luồng, nhiều instance và các đường ghi dữ liệu ngoài JPA vẫn có thể tạo bản ghi trùng SKU.

Một ví dụ nguy hiểm:

~~~text
Kho 10:
stock_item(id=1, warehouse_id=10, sku="SKU-001")
stock_item(id=2, warehouse_id=10, sku="SKU-001")
~~~

Cả hai bản ghi đều thuộc cùng Warehouse và có cùng map key. Khi nạp vào `Map<String, StockItem>`, cấu trúc Map không thể biểu diễn cả hai dưới một khóa duy nhất. Hành vi nạp/ghi đè entry cụ thể tùy provider, và dữ liệu có thể bị nhìn thiếu ở tầng Java.

Do đó, schema nên có:

~~~sql
CONSTRAINT uk_stock_item_warehouse_sku
    UNIQUE (warehouse_id, sku)
~~~

Bên cạnh đó:

~~~sql
warehouse_id BIGINT NOT NULL,
sku VARCHAR(40) NOT NULL
~~~

để tránh khóa Map null và quan hệ thiếu cha.

### 10.1. UNIQUE theo toàn cục hay theo cha?

Chọn theo quy tắc nghiệp vụ:

- Nếu SKU chỉ được duy nhất trong từng kho: `UNIQUE(warehouse_id, sku)`.
- Nếu SKU là mã toàn hệ thống độc lập mọi kho: có thể cần `UNIQUE(sku)` trên bảng danh mục Product; StockItem khi đó tham chiếu Product bằng FK.
- Nếu có phiên bản hay thời điểm hiệu lực: có thể phải mở rộng unique key, chẳng hạn `(warehouse_id, sku, effective_date)`, và lúc đó Map key cũng cần đại diện đủ thông tin.

Không có một UNIQUE constraint mặc định nào do riêng `@MapKey(name="sku")` bảo đảm cho mọi schema. JPA metadata và migration phải được thiết kế đồng bộ.

### 10.2. Collation ảnh hưởng đến tính duy nhất của khóa chuỗi

Nếu DB dùng collation không phân biệt hoa/thường, `"sku-001"` và `"SKU-001"` có thể bị xem là trùng trong UNIQUE constraint, trong khi một `HashMap<String, StockItem>` thông thường dùng `String.equals` và xem chúng là khác nhau.

Vì vậy cần một quy ước canonicalization rõ ràng, ví dụ:

~~~java
String normalized =
    rawSku.trim().toUpperCase(Locale.ROOT);
~~~

Trong ví dụ entity, chuẩn hóa này diễn ra ở constructor. Ứng dụng phải dùng cùng quy tắc khi thêm, tìm và xóa; DB collation/index cũng cần phù hợp với chính sách. Không nên giả định Java và database dùng cùng một quy tắc so sánh văn bản.

## 11. Truy vấn JPQL qua Map: `KEY`, `VALUE` và join

JPA hỗ trợ các biểu thức dành cho Map trong JPQL, tiêu biểu là `KEY(...)` và `VALUE(...)` đối với biến join của map-valued association.

Giả sử `Warehouse.itemsBySku` được ánh xạ như trước.

### 11.1. Tra cứu dòng tồn theo SKU bằng JPQL

~~~java
List<StockItem> items = entityManager.createQuery(
        "SELECT item " +
        "FROM Warehouse w JOIN w.itemsBySku item " +
        "WHERE w.id = :warehouseId AND KEY(item) = :sku",
        StockItem.class
    )
    .setParameter("warehouseId", warehouseId)
    .setParameter("sku", "SKU-001")
    .getResultList();
~~~

Giải thích:

- `JOIN w.itemsBySku item` điều hướng từ entity Warehouse sang các phần tử value trong Map.
- `KEY(item)` truy cập khóa Map của entry đang join.
- Với `@MapKey(name = "sku")`, khóa đó được dẫn xuất từ `StockItem.sku`.
- `item` biểu diễn entity value `StockItem` trong JPQL.

Truy vấn mang ý nghĩa tương tự:

~~~java
List<StockItem> items = entityManager.createQuery(
        "SELECT item FROM StockItem item " +
        "WHERE item.warehouse.id = :warehouseId " +
        "AND item.sku = :sku",
        StockItem.class
    )
    .setParameter("warehouseId", warehouseId)
    .setParameter("sku", "SKU-001")
    .getResultList();
~~~

Cách thứ hai không phụ thuộc đường dẫn map-valued association trong truy vấn; đôi khi nó đơn giản hơn nếu chỉ cần tra một dòng theo mã.

### 11.2. Lấy cả khóa và entity value

~~~java
List<Object[]> rows = entityManager.createQuery(
        "SELECT KEY(item), VALUE(item) " +
        "FROM Warehouse w JOIN w.itemsBySku item " +
        "WHERE w.id = :warehouseId",
        Object[].class
    )
    .setParameter("warehouseId", warehouseId)
    .getResultList();

for (Object[] row : rows) {
    String sku = (String) row[0];
    StockItem item = (StockItem) row[1];

    System.out.println(sku + " -> " + item.getQuantity());
}
~~~

`KEY(item)` là map key, `VALUE(item)` là map value. Với ví dụ này `VALUE(item)` là entity StockItem.

Các provider có thể có cách tối ưu SQL khác nhau, nhưng ngữ nghĩa JPQL vẫn làm việc với tên entity/thuộc tính JPA thay vì tên bảng SQL.

### 11.3. Truy vấn theo thuộc tính value thay cho KEY

Vì Map key lấy từ một thuộc tính của StockItem, ta cũng có thể viết:

~~~jpql
SELECT item
FROM Warehouse w JOIN w.itemsBySku item
WHERE w.id = :warehouseId
  AND item.sku = :sku
~~~

Điều này phù hợp khi `sku` là thuộc tính basic và được ánh xạ bình thường. Việc dùng `KEY(item)` nhấn mạnh ngữ nghĩa map-valued association; dùng `item.sku` nhấn mạnh thuộc tính entity giá trị. Cả hai có thể cho phép provider tạo điều kiện SQL trên cùng dữ liệu nguồn.

### 11.4. Khi chỉ cần một bản ghi, đừng tải cả Map lớn

Giả sử một Warehouse có 200.000 StockItem. Gọi:

~~~java
warehouse.getItemsBySku().get("SKU-001");
~~~

có thể khiến ORM nạp một lượng dữ liệu không cần thiết nếu collection chưa được khởi tạo và provider không hỗ trợ truy cập entry một cách tối ưu.

Với use case lấy một SKU, truy vấn repository trực tiếp thường dễ kiểm soát hơn:

~~~java
public StockItem findByWarehouseAndSku(
        Long warehouseId, String sku) {

    return entityManager.createQuery(
            "SELECT s FROM StockItem s " +
            "WHERE s.warehouse.id = :warehouseId AND s.sku = :sku",
            StockItem.class
        )
        .setParameter("warehouseId", warehouseId)
        .setParameter("sku", sku)
        .getResultStream()
        .findFirst()
        .orElse(null);
}
~~~

Đây là ví dụ API JPA có `getResultStream()`; có thể dùng `getResultList()` nếu dự án theo quy ước khác. `UNIQUE(warehouse_id, sku)` ở DB giúp bảo đảm kỳ vọng tối đa một kết quả.

## 12. Fetching và persistent Map

### 12.1. Mặc định LAZY với One-to-Many

`@OneToMany` có default fetch là `LAZY`, nên collection thường được tải khi truy cập. Tuy nhiên, provider có thể hiện thực bằng proxy/wrapper khác `HashMap`, và một số thao tác có thể kích hoạt SQL.

Ví dụ:

~~~java
Warehouse warehouse =
    entityManager.find(Warehouse.class, warehouseId);

Map<String, StockItem> items = warehouse.getItemsBySku();
int count = items.size();
~~~

`size()` có thể kích hoạt việc khởi tạo collection hoặc truy vấn đếm riêng tùy tính năng provider. Không suy ra chính xác SQL chỉ từ việc `items` là Map.

### 12.2. Vấn đề N+1

Nếu tải danh sách 100 Warehouse rồi lặp qua `itemsBySku` của từng Warehouse, có thể xuất hiện một truy vấn lấy danh sách kho cộng thêm nhiều truy vấn nạp collection.

Có thể cân nhắc:

- Chỉ tải danh sách kho với DTO không kèm Map nếu màn hình không cần chi tiết.
- Tải chi tiết cho một kho khi người dùng mở trang kho.
- Sử dụng JPQL fetch join/EntityGraph theo use case.
- Với nhiều kho cùng cần chi tiết, dùng query riêng, batching hoặc strategy do provider hỗ trợ.
- Kiểm tra SQL và kích thước dữ liệu thực tế.

### 12.3. Fetch join Map

Một ví dụ:

~~~java
List<Warehouse> warehouses = entityManager.createQuery(
        "SELECT DISTINCT w " +
        "FROM Warehouse w LEFT JOIN FETCH w.itemsBySku " +
        "WHERE w.id = :id",
        Warehouse.class
    )
    .setParameter("id", warehouseId)
    .getResultList();
~~~

Fetch join có thể nạp những StockItem của Warehouse trong cùng truy vấn. Tuy nhiên, join collection có thể nhân số hàng SQL và không phù hợp với phân trang trực tiếp trên danh sách nhiều Warehouse. Hãy thiết kế truy vấn theo nhu cầu thực tế.

### 12.4. Tránh trả trực tiếp entity Map qua JSON

Một đồ thị hai chiều:

~~~text
Warehouse.itemsBySku
       |
       v
StockItem.warehouse
       |
       v
Warehouse.itemsBySku
       | ...
~~~

có thể làm serializer đi theo vòng lặp, nạp collection ngoài transaction hoặc tạo payload quá lớn. Thường nên chuyển sang DTO:

~~~java
public record StockItemDto(
    String sku,
    int quantity
) {}

public record WarehouseDto(
    Long id,
    String name,
    List<StockItemDto> items
) {}
~~~

DTO cho phép kiểm soát dữ liệu công khai, số phần tử, thứ tự và chính sách phân trang thay vì phơi toàn bộ persistent Map.

## 13. Quan hệ và collection có vòng đời như thế nào?

Đối với `Warehouse.itemsBySku`:

~~~java
@OneToMany(
    mappedBy = "warehouse",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
@MapKey(name = "sku")
private Map<String, StockItem> itemsBySku;
~~~

`CascadeType.ALL` bao gồm `PERSIST`, `MERGE`, `REMOVE` và các thao tác khác theo JPA. Điều này thể hiện quyết định rằng StockItem được quản lý theo vòng đời Warehouse.

**Nhưng Map không mặc định đồng nghĩa quyền sở hữu vòng đời.** Nếu value là một entity dùng chung, ví dụ `Map<String, Product>` biểu diễn danh mục Product đã tồn tại, cascade REMOVE thường không thích hợp. Lựa chọn cascade dựa trên domain, không chỉ dựa trên kiểu dữ liệu `Map`.

### 13.1. `orphanRemoval` khi xóa entry

Nếu một StockItem không còn ý nghĩa khi bị gỡ khỏi kho:

~~~java
warehouse.removeItem("SKU-001");
~~~

và mapping có `orphanRemoval = true`, provider có thể xóa bản ghi StockItem khi flush theo quy tắc JPA.

Không nên nghĩ đơn giản rằng:

~~~java
itemsBySku.remove("SKU-001");
~~~

luôn tương đương:

~~~sql
DELETE FROM stock_item WHERE sku = 'SKU-001';
~~~

Provider phải xác định entity bị gỡ trong ngữ cảnh relationship, transaction và mapping. SQL thực tế có thể khác, bao gồm điều kiện theo PK, FK hoặc thêm những thao tác nội bộ.

### 13.2. Không dùng `CascadeType.REMOVE` trên value entity độc lập

Một Map biểu diễn “phòng ban phân công nhân viên theo mã nhân viên” có thể chứa các Employee tồn tại độc lập. Xóa phòng ban không nhất thiết có nghĩa xóa toàn bộ tài khoản nhân viên. Trường hợp đó có thể yêu cầu null FK, chuyển nhân viên sang đơn vị khác hoặc giữ lịch sử; cascade REMOVE phải được quyết định riêng.

### 13.3. Thay Map instance khi entity managed

Không nên tạo:

~~~java
warehouse.itemsBySku = new HashMap<>();
~~~

để “xóa tất cả dòng” trên entity managed có persistent collection. Điều này có thể khiến ORM mất wrapper theo dõi collection hoặc không áp dụng orphanRemoval theo cách mong muốn.

Thay vào đó, sử dụng helper thao tác từng entry hoặc một operation `clearInventory` được thiết kế cho vòng đời entity, kiểm tra tác động xóa và xử lý transaction rõ ràng.

## 14. Các kiểu khóa Map khác có thể suy ra từ value entity

Không phải lúc nào khóa cũng là `String`. JPA có thể dùng thuộc tính persistent phù hợp của value entity.

### 14.1. Khóa là mã số nguyên

~~~java
// StockItem:
@Column(name = "position_no", nullable = false)
private Integer positionNo;

// Warehouse:
@OneToMany(mappedBy = "warehouse")
@MapKey(name = "positionNo")
private Map<Integer, StockItem> itemsByPosition;
~~~

Nghiệp vụ cần bảo đảm `positionNo` không trùng trong cùng Warehouse. Nếu số vị trí được đổi thường xuyên, rủi ro mất đồng bộ Map cũng phải được xử lý.

### 14.2. Khóa là enum trạng thái

~~~java
public enum SlotType {
    PRIMARY,
    RESERVE,
    RETURNED
}
~~~

Nếu mỗi Warehouse được phép có **tối đa một StockItem cho mỗi SlotType**, có thể:

~~~java
// StockItem:
@Enumerated(EnumType.STRING)
@Column(name = "slot_type", length = 20, nullable = false)
private SlotType slotType;

// Warehouse:
@OneToMany(mappedBy = "warehouse")
@MapKey(name = "slotType")
private Map<SlotType, StockItem> itemsBySlotType;
~~~

`@Enumerated(EnumType.STRING)` ở **thuộc tính StockItem.slotType** quyết định cách lưu enum trong cột. `@MapKey(name="slotType")` lấy chính thuộc tính đó làm khóa.

Nếu một kho có nhiều StockItem cùng `slotType = PRIMARY` thì Map này **không phù hợp**; cần chọn khóa duy nhất khác hoặc dùng `Map<SlotType, List<StockItem>>` ở DTO/service (không nhất thiết ánh xạ trực tiếp như collection JPA tương tự).

### 14.3. Khóa là một entity liên quan

~~~java
// Trong StockItem:
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "product_id", nullable = false)
private Product product;

// Trong Warehouse:
@OneToMany(mappedBy = "warehouse")
@MapKey(name = "product")
private Map<Product, StockItem> itemsByProduct;
~~~

Thiết kế này nói mỗi Product có tối đa một dòng StockItem trong mỗi Warehouse. Database nên bảo vệ bằng `UNIQUE(warehouse_id, product_id)` nếu đó là invariant thực.

Khi khóa là entity, chú ý identity và `equals/hashCode`. Nếu Product mới chưa được persist và ID là generated, dùng nó làm key của `HashMap` có thể gặp vấn đề khi hash thay đổi. Trong nhiều hệ thống, khóa đơn giản/ổn định như SKU hoặc Product ID được xử lý có kiểm soát sẽ dễ sử dụng hơn.

### 14.4. Khóa bằng primary key

~~~java
@OneToMany(mappedBy = "warehouse")
@MapKey
private Map<Long, StockItem> itemsById;
~~~

Đây là lựa chọn khi object đã persisted và luôn có ID. Nếu cần thêm StockItem mới vào Map trước khi ID được sinh, thiết kế này kém thuận tiện hơn khóa nghiệp vụ đã biết từ đầu.

## 15. Cần làm gì nếu một khóa có nhiều giá trị?

Giả sử nghiệp vụ nói “Một Warehouse có nhiều StockItem thuộc cùng nhóm hàng `ELECTRONICS`”.

Đây **không phải** quan hệ có thể ánh xạ đầy đủ bằng:

~~~java
@MapKey(name = "category")
private Map<String, StockItem> itemsByCategory;
~~~

vì nhiều StockItem có thể cùng category. `Map<String, StockItem>` chỉ chứa một value trên mỗi khóa.

Các hướng thiết kế khác:

1. Lưu collection dưới dạng `List<StockItem>` hoặc `Set<StockItem>` và truy vấn nhóm theo category.
2. Xây dựng `Map<String, List<StockItem>>` ở tầng service/DTO bằng cách group dữ liệu đã truy vấn, không mặc định nó là một association JPA trực tiếp.
3. Nếu “nhóm hàng” là entity có identity riêng, ánh xạ `@ManyToOne` tới Category rồi truy vấn theo Category.
4. Nếu mỗi category có một bản ghi tổng hợp đại diện và các item bên trong, mô hình lại entity tổng hợp và collection của nó.

**Khóa Map phải là ánh xạ một-một từ khóa sang phần tử value trong phạm vi collection**, dù quan hệ entity cha–con vẫn là một-nhiều.

### 15.1. Khóa thực tế là khóa tổng hợp

Nếu định danh logic của dòng tồn phụ thuộc cả `sku` và `batchNo`, chỉ dùng SKU là thiếu:

~~~text
SKU-001, batch-A
SKU-001, batch-B
~~~

Hai dòng cùng SKU có thể cùng tồn tại, nên `Map<String, StockItem>` keyed by SKU không phù hợp. Có thể tạo một value type khóa tổng hợp ở tầng domain, dùng cấu trúc query phù hợp, hoặc ánh xạ một khóa embedded/natural key theo tính năng JPA và yêu cầu thực tế. Không ép hai bản ghi vào cùng một key rồi mong ORM giữ đủ dữ liệu.

## 16. Annotation khác liên quan đến Map, nhưng không giải quyết cùng bài toán

| Annotation | Tác dụng | Có phải lựa chọn chính khi khóa lấy từ property của entity value? |
|---|---|---|
| `@MapKey(name = "sku")` | Lấy thuộc tính `sku` của value entity làm Map key | **Có** |
| `@MapKey` | Lấy primary key của value entity làm Map key | Khi khóa cần là PK |
| `@MapKeyColumn` | Ánh xạ cột lưu khóa basic riêng | Không, nếu khóa đã là `StockItem.sku` |
| `@MapKeyJoinColumn` | Cấu hình khóa Map là entity reference qua join column | Không, nếu chỉ lấy field basic `sku` |
| `@MapKeyEnumerated` | Cấu hình cách lưu enum dùng làm map key trong mapping có key enum riêng | Không cần chỉ để đọc `StockItem.slotType` đã được ánh xạ |
| `@MapKeyTemporal` | Cấu hình temporal map key theo kiểu legacy liên quan | Không cần chỉ để đọc thuộc tính đã ánh xạ |
| `@ElementCollection` | Collection của basic/embeddable values | Không dùng cho collection entity StockItem |
| `@OneToMany` | Quan hệ một-nhiều với entity value | Có trong ví dụ chính |
| `@ManyToMany` | Quan hệ nhiều-nhiều tới entity value | Có thể kết hợp với Map tùy mô hình |
| `@JoinColumn` | Xác định FK của liên kết | Cần cho owning side tương ứng |
| `mappedBy` | Xác định phía ngược của quan hệ hai chiều | Cần nếu dùng inverse association |
| `@OrderBy` | Cấu hình thứ tự lấy phần tử collection theo thuộc tính | Không quyết định Map key |
| `@OrderColumn` | Cột lưu vị trí thứ tự List | Không tương đương Map key |

Đặc biệt, **Map không đồng nghĩa dữ liệu có thứ tự**. `HashMap` và nhiều persistent Map không bảo đảm thứ tự lặp. Nếu giao diện cần sắp xếp các dòng theo SKU, cần truy vấn `ORDER BY` hoặc sử dụng cấu trúc kết quả có thứ tự ở tầng DTO. Đừng dùng Map key như một giải pháp thay thế cho yêu cầu ordering.

## 17. Lỗi thường gặp và cách xử lý

### 17.1. Dùng tên cột thay vì tên property

~~~java
@MapKey(name = "stock_keeping_unit")
private Map<String, StockItem> itemsBySku;
~~~

Nhưng entity có:

~~~java
@Column(name = "stock_keeping_unit")
private String sku;
~~~

**Vấn đề:** `@MapKey.name` phải trỏ tới thuộc tính persistent Java `sku`. Sửa thành:

~~~java
@MapKey(name = "sku")
~~~

### 17.2. Khai báo kiểu khóa Map không khớp

~~~java
@MapKey(name = "sku")
private Map<Long, StockItem> itemsBySku;
~~~

Trong khi `sku` là String. Mapping có thể thất bại khi bootstrap hoặc tải dữ liệu. Sửa kiểu `K` khớp nguồn khóa:

~~~java
private Map<String, StockItem> itemsBySku;
~~~

### 17.3. Chỉ thêm phần tử vào Map, không gán quan hệ cha

~~~java
warehouse.getMutableMap().put(item.getSku(), item);
~~~

Nhưng `item.warehouse` chưa được đặt. Trong mapping `@OneToMany(mappedBy="warehouse")`, owning side là child. Dùng helper gán cả owning side và collection entry.

### 17.4. Hai entity con trùng khóa Map

Nếu database cho phép hai StockItem cùng warehouse và SKU, collection Map không thể đại diện đầy đủ cả hai. Thiết kế `UNIQUE(warehouse_id, sku)` theo nghiệp vụ và từ chối trùng ngay ở helper. Constraint DB vẫn là lớp bảo vệ khi có concurrency.

### 17.5. Đổi SKU sau khi Map đã load

~~~java
item.setSku("SKU-999");
~~~

Entity value đổi field, nhưng Map Java vẫn có thể giữ key cũ. Cân nhắc khóa bất biến, re-key có kiểm soát và chú ý `orphanRemoval`; nếu đổi khóa thường xuyên, cần thay đổi cấu trúc mapping.

### 17.6. Lạm dụng `@MapKeyColumn`

Nếu `StockItem` đã có field `sku`, không cần tạo thêm cột key độc lập cho Map. Dùng `@MapKey(name="sku")` thay vì cấu hình `@MapKeyColumn` như thể khóa Map chưa được lưu ở đâu.

### 17.7. Chọn khóa không duy nhất như trạng thái

`Map<OrderStatus, OrderLine>` không thể chứa nhiều OrderLine cùng trạng thái `NEW`. Cần chọn một key khác hoặc giữ List/Set. Không dựa vào “Map sẽ tự chọn một bản ghi” vì đó là mất thông tin.

### 17.8. Đặt cascade REMOVE cho entity dùng chung

Nếu Map value là Product dùng chung toàn hệ thống, xóa Warehouse không nên xóa Product. Cascade và orphanRemoval phải phản ánh vòng đời, không phải “collection nào cũng cascade ALL”.

### 17.9. Truy cập Map ngoài persistence context

Nếu One-to-Many LAZY chưa được tải, gọi `getItemsBySku()` sau khi đóng EntityManager/session có thể gây lỗi lazy loading ở một số provider. Dùng DTO/projection hoặc fetch cần thiết trong transaction.

### 17.10. Dùng Map key làm thứ tự hiển thị

Map key không bảo đảm Map được sắp xếp. Nếu cần thứ tự tăng theo SKU, hãy truy vấn `ORDER BY` hoặc sắp xếp ở tầng hiển thị; không suy ra từ `@MapKey`.

## 18. Quy trình thiết kế quan hệ Map cho một mô hình nghiệp vụ

Có thể áp dụng quy trình sau với bất kỳ quan hệ một-nhiều nào.

### Bước 1. Xác định nhu cầu tra cứu theo khóa

Nghiệp vụ có thường hỏi “lấy phần tử theo mã X” không? Nếu chỉ hiển thị tất cả phần tử theo thứ tự, List hoặc query riêng có thể đơn giản hơn.

### Bước 2. Xác định khóa nằm ở đâu

- Khóa là thuộc tính đã có của entity value → cân nhắc `@MapKey(name="...")`.
- Khóa là primary key của entity value → cân nhắc `@MapKey` không tham số.
- Khóa là thuộc tính độc lập của entry Map, cần cột riêng → cân nhắc `@MapKeyColumn`.
- Khóa là entity reference độc lập cần join column riêng → cân nhắc `@MapKeyJoinColumn`.

### Bước 3. Chứng minh tính duy nhất

Kiểm tra có thể có hai value cùng khóa trong một cha hay không. Nếu có, `Map<K,V>` không phù hợp để đại diện đầy đủ. Nếu không, thiết kế UNIQUE constraint theo khóa và phạm vi cha.

### Bước 4. Chọn phía sở hữu quan hệ

Nếu FK nằm trong bảng con, có thể đặt `@ManyToOne` và `@JoinColumn` trên con, `@OneToMany(mappedBy="...")` trên cha. Đảm bảo `mappedBy` trỏ đúng tên field Java.

### Bước 5. Chọn độ ổn định của khóa

Khóa nên ổn định sau khi entry được đưa vào Map. Nếu có khả năng đổi, thiết kế operation re-key tường minh; đừng trông đợi JPA cập nhật Map key đang load.

### Bước 6. Chọn cascade/orphanRemoval theo vòng đời

Phân biệt value entity phụ thuộc hoàn toàn vào cha với entity dùng chung. Quyết định xóa, chuyển cha, lưu lịch sử trước khi bật cascade.

### Bước 7. Chọn truy vấn và fetching

Map phù hợp cho điều hướng dữ liệu đã tải. Đối với collection lớn hoặc tra một entry, query có điều kiện theo FK và key có thể hiệu quả hơn. Kiểm tra SQL thực tế.

### Bước 8. Thiết kế transaction và constraint database

Kiểm tra input, chuẩn hóa mã, xử lý trùng khóa trong Java, rồi bảo vệ bằng UNIQUE/FK/NOT NULL ở DB. Không coi `persist` hoặc ID đã cấp là commit thành công.

## 19. Bài tập thực hành

### Bài 1. Đọc mapping

Cho:

~~~java
@Entity
class Department {

    @Id
    Long id;

    @OneToMany(mappedBy = "department")
    @MapKey(name = "employeeCode")
    Map<String, Employee> employeesByCode;
}

@Entity
class Employee {

    @Id
    Long id;

    @ManyToOne
    @JoinColumn(name = "department_id")
    Department department;

    @Column(name = "employee_code")
    String employeeCode;
}
~~~

**Câu hỏi:** Map key lấy từ đâu? FK nằm ở bảng nào? `mappedBy = "department"` có phải tên cột không?

**Đáp án:** Map key lấy từ `Employee.employeeCode`; FK là `employee.department_id`; `mappedBy` là tên field Java `Employee.department`, không phải tên cột. Nếu employeeCode chỉ duy nhất trong mỗi Department, nên có constraint phù hợp `UNIQUE(department_id, employee_code)`.

### Bài 2. So sánh `@MapKey` và `@MapKeyColumn`

Hệ thống có:

~~~java
@ElementCollection
@CollectionTable(name = "product_translation")
@MapKeyColumn(name = "language_code")
@Column(name = "translated_name")
Map<String, String> namesByLanguage;
~~~

**Câu hỏi:** Có nên thay `@MapKeyColumn(name="language_code")` bằng `@MapKey(name="languageCode")` không?

**Đáp án:** Không trong thiết kế này. Map value là String, không phải entity value có property persistent `languageCode`. Khóa được lưu riêng trong bảng collection, nên `@MapKeyColumn` phù hợp.

### Bài 3. Khóa không duy nhất

Warehouse có 20 dòng tồn cùng `status = AVAILABLE`. Một lập trình viên đề xuất:

~~~java
@MapKey(name = "status")
Map<StockStatus, StockItem> itemsByStatus;
~~~

**Câu hỏi:** Sai ở đâu?

**Đáp án:** Một Map chỉ lưu tối đa một StockItem cho key AVAILABLE. Nếu nghiệp vụ cho phép nhiều dòng cùng status, cấu trúc Map này không biểu diễn đầy đủ quan hệ. Chọn SKU duy nhất hoặc List/Set rồi group ở tầng query/DTO.

### Bài 4. Đổi thuộc tính khóa

Map được nạp với entry `"SKU-001" -> item`. Sau đó code đổi `item.sku` thành `"SKU-002"`.

**Câu hỏi:** Có chắc `map.get("SKU-002")` trả item ngay không?

**Đáp án:** Không. Map đã nạp không nhất thiết được tự re-key khi thuộc tính value thay đổi. Nên chọn khóa ổn định hoặc thực hiện thay đổi có kiểm soát; đặc biệt cẩn trọng nếu collection có orphanRemoval.

### Bài 5. Thiết kế UNIQUE

StockItem có các cột `id`, `warehouse_id`, `sku`. SKU chỉ cần duy nhất trong một kho.

**Câu hỏi:** Dùng `UNIQUE(sku)` hay `UNIQUE(warehouse_id, sku)`?

**Đáp án:** `UNIQUE(warehouse_id, sku)`. Điều này bảo đảm mỗi Warehouse chỉ có một StockItem cho mỗi SKU nhưng cho phép cùng SKU có mặt tại nhiều kho.

### Bài 6. Truy vấn một entry

Kho có 300.000 dòng tồn kho. API nhận `warehouseId` và `sku`, chỉ cần trả số lượng.

**Câu hỏi:** Có nên luôn `find(Warehouse.class, id)` rồi `itemsBySku.get(sku)` không?

**Đáp án:** Không nhất thiết. Nếu collection LAZY, Map access có thể kích hoạt tải nhiều phần tử. Truy vấn trực tiếp `StockItem` theo `warehouse.id` và `sku`, hoặc projection chỉ lấy `quantity`, thường giúp tối ưu lượng dữ liệu tải.

### Bài 7. Khóa Map là entity

`StockItem` có `@ManyToOne Product product`. Trong Warehouse:

~~~java
@MapKey(name = "product")
private Map<Product, StockItem> itemsByProduct;
~~~

**Câu hỏi:** Map key có phải `product_id` dưới dạng `Long` không?

**Đáp án:** Không. Theo cấu hình, Map key là **entity `Product`** (thuộc tính Java `StockItem.product`). Nếu muốn `Map<Long, StockItem>` keyed by Product ID, phải chọn mapping/kiến trúc phù hợp khác; `@MapKey(name="product")` không tự chuyển kiểu key thành Long.

## 20. Tóm tắt nguyên tắc cốt lõi

~~~text
Warehouse.itemsBySku : Map<String, StockItem>
          |
          | @OneToMany(mappedBy = "warehouse")
          v
      StockItem.warehouse  ----------> stock_item.warehouse_id (FK)
          |
          | @MapKey(name = "sku")
          v
      StockItem.sku        ----------> stock_item.sku (map key)
          |
          | @Id
          v
      StockItem.id         ----------> stock_item.id (PK)
~~~

Các nguyên tắc quan trọng:

1. **`@MapKey(name = "...")` lấy khóa Map từ thuộc tính persistent của entity value**; `name` là tên property Java, không phải tên cột SQL.
2. **Map key không nhất thiết là primary key.** Ví dụ `StockItem.sku` làm Map key còn `StockItem.id` vẫn là PK kỹ thuật.
3. **Khi khóa đã có trên entity value, không cần cột map key riêng.** Đây là điểm phân biệt quan trọng với `@MapKeyColumn`.
4. **Khóa phải duy nhất trong phạm vi Map.** Hãy bảo vệ invariant bằng constraint như `UNIQUE(warehouse_id, sku)`.
5. **`mappedBy` và `@MapKey.name` giải quyết hai việc khác nhau:** một cái xác định owning side của liên kết, cái kia chọn thuộc tính dùng làm Map key.
6. **JPA không tự động sửa khóa trong Map đã nạp khi thuộc tính key của value thay đổi.** Ưu tiên khóa ổn định hoặc thiết kế operation re-key có kiểm soát.
7. **Không trông đợi `Map.get` trên persistent collection là một truy vấn SQL theo key tối ưu.** Với collection lớn, dùng JPQL/repository query trực tiếp.
8. **Cascade và orphanRemoval phải theo vòng đời nghiệp vụ**, không phải cứ dùng Map thì bật `ALL`.
9. **`KEY(...)` và `VALUE(...)` cho phép truy vấn map-valued association trong JPQL**, còn SQL thực tế được provider tạo từ mapping.
10. **Nếu mỗi key có nhiều value, `Map<K,V>` không phù hợp để chứa đầy đủ dữ liệu**; hãy xem xét List/Set, grouping DTO hoặc mô hình entity khác.

Ánh xạ khóa Map từ thuộc tính của đối tượng liên quan là cách diễn đạt tự nhiên khi nghiệp vụ cần **tra cứu các entity con theo mã ổn định của chính chúng**. Dùng đúng `@MapKey(name)`, foreign key, constraint và lifecycle giúp Map trong Java phản ánh trung thực dữ liệu quan hệ, thay vì trở thành một lớp chỉ mục dễ mất đồng bộ với database.
