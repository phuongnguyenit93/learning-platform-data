# Truy vấn theo thành phần của khóa ghép trong JPA

Trong cơ sở dữ liệu quan hệ, **khóa chính ghép (composite primary key)** gồm từ hai cột trở lên. Ví dụ, mỗi dòng đơn hàng được xác định bằng cặp **(mã đơn hàng, số thứ tự dòng)**. Không thể dùng riêng `order_id` hoặc `line_no` để định danh duy nhất mọi dòng, nhưng ứng dụng vẫn thường cần lấy **tất cả các dòng của một đơn hàng**, tức truy vấn chỉ bằng **một thành phần của khóa ghép**.

Trong Jakarta Persistence (JPA), cách viết truy vấn phụ thuộc vào **cách ánh xạ khóa ghép**:

- Với `@EmbeddedId`, các thành phần của khóa nằm trong một object nhúng; truy vấn dùng đường dẫn như `line.id.orderId`.
- Với `@IdClass`, các trường mang `@Id` được khai báo trực tiếp trên entity; truy vấn dùng `line.orderId`.
- `EntityManager.find(...)` tìm **đúng một entity theo toàn bộ khóa**, không phải cơ chế tìm theo một phần khóa.
- JPQL, Criteria API hoặc phương thức truy vấn của Spring Data JPA có thể lọc theo **một hoặc nhiều thành phần** và trả về tập kết quả.

Bài học dùng ví dụ đơn hàng để giải thích cú pháp, cách ánh xạ sang SQL, vấn đề số lượng kết quả, chỉ mục và những lỗi thường gặp.

## 1. Ví dụ dữ liệu có khóa chính ghép

Giả sử hệ thống bán hàng lưu danh sách mặt hàng thuộc đơn hàng trong bảng `order_lines`:

~~~sql
CREATE TABLE order_lines (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_code VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT pk_order_lines PRIMARY KEY (order_id, line_no),
    CONSTRAINT ck_order_lines_quantity CHECK (quantity > 0)
);
~~~

Dữ liệu minh họa:

| `order_id` | `line_no` | `product_code` | `quantity` |
| ---: | ---: | --- | ---: |
| 1001 | 1 | BOOK-01 | 2 |
| 1001 | 2 | PEN-03 | 5 |
| 1001 | 3 | BAG-10 | 1 |
| 1002 | 1 | BOOK-01 | 1 |
| 1002 | 2 | NOTE-02 | 3 |

Cặp `(1001, 1)` chỉ một dòng cụ thể. Nhưng điều kiện `order_id = 1001` trả về **ba dòng**. Điều kiện `line_no = 1` trả về **hai dòng** vì nhiều đơn hàng đều có dòng số 1.

~~~text
Khóa ghép của OrderLine = (orderId, lineNo)
                         /               \
                        /                 \
               orderId = 1001           lineNo = 1
               -> nhiều dòng             -> nhiều dòng
                        \                 /
                         \               /
                     (1001, 1)
                -> một dòng duy nhất
~~~

Tính duy nhất được bảo đảm trên **toàn bộ tổ hợp khóa**, không được suy ra cho từng thành phần riêng lẻ.

### 1.1. Ba yêu cầu truy vấn khác nhau

~~~sql
-- Tìm chính xác một dòng theo toàn bộ khóa:
SELECT * FROM order_lines
WHERE order_id = 1001 AND line_no = 2;

-- Tìm nhiều dòng theo thành phần order_id:
SELECT * FROM order_lines
WHERE order_id = 1001
ORDER BY line_no;

-- Tìm những dòng đầu tiên của các đơn hàng:
SELECT * FROM order_lines
WHERE line_no = 1
ORDER BY order_id;
~~~

JPA cho phép thực hiện cả ba, nhưng đường dẫn thuộc tính Java sẽ khác tên cột SQL và khác nhau giữa `@EmbeddedId` với `@IdClass`.

## 2. Biểu diễn khóa ghép bằng @EmbeddedId

### 2.1. Tạo lớp khóa @Embeddable

Sử dụng Jakarta Persistence 3.x với các import thuộc `jakarta.persistence.*`:

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class OrderLineId implements Serializable {

    private static final long serialVersionUID = 1L;

    @Column(name = "order_id", nullable = false)
    private Long orderId;

    @Column(name = "line_no", nullable = false)
    private Integer lineNo;

    protected OrderLineId() {
        // JPA cần constructor không tham số.
    }

    public OrderLineId(Long orderId, Integer lineNo) {
        this.orderId = Objects.requireNonNull(orderId);
        this.lineNo = Objects.requireNonNull(lineNo);
    }

    public Long getOrderId() {
        return orderId;
    }

    public Integer getLineNo() {
        return lineNo;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof OrderLineId that)) {
            return false;
        }
        return Objects.equals(orderId, that.orderId)
            && Objects.equals(lineNo, that.lineNo);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNo);
    }
}
~~~

`OrderLineId` là **kiểu giá trị chứa cả hai thành phần khóa**. Nó không phải entity độc lập, không cần `@Entity` và không có bảng riêng. Lớp khóa cần đáp ứng yêu cầu khóa chính JPA, trong đó có constructor không tham số phù hợp, `Serializable` và các phương thức `equals/hashCode` nhất quán với ý nghĩa bằng nhau của hai khóa.

Khi entity đang được quản lý, **không thay đổi giá trị khóa chính** của nó. Việc đổi `orderId` hoặc `lineNo` sau khi persist không phải cách cập nhật ID an toàn; nếu cần thay định danh, thường phải thực hiện nghiệp vụ xóa/tạo hoặc thiết kế lại định danh.

### 2.2. Nhúng khóa vào entity

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @EmbeddedId
    private OrderLineId id;

    @Column(name = "product_code", nullable = false, length = 64)
    private String productCode;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected OrderLine() {
    }

    public OrderLine(
            OrderLineId id,
            String productCode,
            int quantity) {
        this.id = id;
        this.productCode = productCode;
        this.quantity = quantity;
    }

    public OrderLineId getId() {
        return id;
    }

    public String getProductCode() {
        return productCode;
    }

    public int getQuantity() {
        return quantity;
    }

    public void changeQuantity(int newQuantity) {
        if (newQuantity <= 0) {
            throw new IllegalArgumentException(
                "Số lượng phải lớn hơn 0");
        }
        this.quantity = newQuantity;
    }
}
~~~

Ánh xạ tương ứng:

| Đường dẫn Java | Cột SQL | Có thuộc khóa chính? |
| --- | --- | --- |
| `line.id.orderId` | `order_id` | Có |
| `line.id.lineNo` | `line_no` | Có |
| `line.productCode` | `product_code` | Không |
| `line.quantity` | `quantity` | Không |

Entity `OrderLine` có **một thuộc tính `id`** ở tầng Java, bên trong nó chứa **hai trường khóa**. Vì thế truy vấn JPQL đi qua `id` để truy cập từng thành phần.

## 3. Truy vấn @EmbeddedId bằng JPQL

JPQL làm việc với **entity và thuộc tính Java**, không sử dụng trực tiếp tên bảng/cột SQL. Nếu truy vấn muốn lọc theo mã đơn hàng `1001`:

~~~java
List<OrderLine> lines = em.createQuery(
    """
    SELECT l
    FROM OrderLine l
    WHERE l.id.orderId = :orderId
    ORDER BY l.id.lineNo
    """,
    OrderLine.class
)
.setParameter("orderId", 1001L)
.getResultList();
~~~

Đọc từng đoạn:

- `FROM OrderLine l`: dùng tên entity `OrderLine`, không phải tên bảng `order_lines`.
- `l.id`: truy cập trường `@EmbeddedId` trong entity.
- `l.id.orderId`: truy cập **thành phần `orderId` của khóa ghép**.
- `:orderId`: tham số được bind bằng `setParameter`, tránh ghép chuỗi trực tiếp vào query.
- `ORDER BY l.id.lineNo`: sắp theo phần khóa `lineNo`, làm thứ tự danh sách ổn định trong một đơn hàng.
- `getResultList()`: trả về **danh sách** vì một `orderId` có thể tương ứng nhiều `OrderLine`.

Provider có thể phát sinh SQL tương đương:

~~~sql
SELECT order_id, line_no, product_code, quantity
FROM order_lines
WHERE order_id = ?
ORDER BY line_no;
~~~

Cú pháp `l.id.orderId` là **đường dẫn thuộc tính**, còn `order_id` là **tên cột vật lý** do `@Column(name = "order_id")` quyết định.

### 3.1. Truy vấn theo thành phần thứ hai

~~~java
List<OrderLine> firstLines = em.createQuery(
    """
    SELECT l
    FROM OrderLine l
    WHERE l.id.lineNo = :lineNo
    ORDER BY l.id.orderId
    """,
    OrderLine.class
)
.setParameter("lineNo", 1)
.getResultList();
~~~

Kết quả có thể bao gồm dòng đầu tiên của nhiều đơn hàng. Không nên gọi `getSingleResult()` với giả định `lineNo = 1` là duy nhất.

### 3.2. Kết hợp hai thành phần khóa trong điều kiện WHERE

~~~java
List<OrderLine> result = em.createQuery(
    """
    SELECT l
    FROM OrderLine l
    WHERE l.id.orderId = :orderId
      AND l.id.lineNo = :lineNo
    """,
    OrderLine.class
)
.setParameter("orderId", 1001L)
.setParameter("lineNo", 2)
.getResultList();
~~~

Với tổ hợp đầy đủ, ràng buộc primary key bảo đảm kết quả có **tối đa một dòng**. Tuy vậy, khi đã có cả hai giá trị khóa và chỉ cần lấy entity, `EntityManager.find` thường rõ ý định hơn (xem mục 4).

### 3.3. Kết hợp một thành phần khóa với thuộc tính thông thường

Ví dụ tìm mặt hàng `BOOK-01` trong một đơn hàng:

~~~java
List<OrderLine> books = em.createQuery(
    """
    SELECT l
    FROM OrderLine l
    WHERE l.id.orderId = :orderId
      AND l.productCode = :productCode
    ORDER BY l.id.lineNo
    """,
    OrderLine.class
)
.setParameter("orderId", 1001L)
.setParameter("productCode", "BOOK-01")
.getResultList();
~~~

Thành phần khóa được truy cập bằng `l.id.orderId`, còn trường thường chỉ cần `l.productCode`. Không cần và không nên tạo một `OrderLineId` giả có `lineNo = null` để lọc theo đơn hàng.

### 3.4. Truy vấn khoảng của một thành phần khóa

~~~java
List<OrderLine> range = em.createQuery(
    """
    SELECT l
    FROM OrderLine l
    WHERE l.id.orderId = :orderId
      AND l.id.lineNo BETWEEN :fromLine AND :toLine
    ORDER BY l.id.lineNo
    """,
    OrderLine.class
)
.setParameter("orderId", 1001L)
.setParameter("fromLine", 2)
.setParameter("toLine", 10)
.getResultList();
~~~

Điều kiện `BETWEEN` áp dụng cho trường `lineNo` có kiểu số. Đây là ví dụ về việc sử dụng **một hoặc nhiều thành phần khóa ghép như thuộc tính truy vấn bình thường**, miễn giữ đúng tên đường dẫn và kiểu dữ liệu.

## 4. Phân biệt EntityManager.find với truy vấn theo một phần khóa

`EntityManager.find(Class<T>, Object primaryKey)` tìm entity bằng **toàn bộ định danh**. Với `@EmbeddedId`:

~~~java
OrderLineId key = new OrderLineId(1001L, 2);
OrderLine line = em.find(OrderLine.class, key);

if (line == null) {
    System.out.println("Không tìm thấy dòng (1001, 2)");
}
~~~

JPA có thể lấy entity từ persistence context hiện hành hoặc thực hiện SQL nếu cần. Điều cần phân biệt là `find` trả về **một entity hoặc null**, vì key được cung cấp là khóa đầy đủ.

Trường hợp **sai tư duy**:

~~~java
// Không dùng null để biểu thị "không lọc theo lineNo":
OrderLineId partialKey = new OrderLineId(1001L, null);
OrderLine line = em.find(OrderLine.class, partialKey);
~~~

Ngoài việc constructor ví dụ chủ động không chấp nhận null, về mô hình dữ liệu, `(1001, null)` không phải primary key hoàn chỉnh. JPA không diễn giải trường null thành wildcard.

Dùng JPQL/Criteria khi muốn lọc từng phần, dùng `find` khi đã có **đúng toàn bộ khóa**:

| Nhu cầu | Công cụ phù hợp | Kết quả dự kiến |
| --- | --- | --- |
| Tìm `(1001, 2)` | `em.find(OrderLine.class, new OrderLineId(1001L, 2))` | Một entity hoặc null |
| Tìm mọi dòng của đơn 1001 | JPQL/Criteria `l.id.orderId = :orderId` | Danh sách, có thể rỗng |
| Tìm mọi dòng số 1 | JPQL/Criteria `l.id.lineNo = :lineNo` | Danh sách ở nhiều đơn hàng |
| Đếm số dòng của đơn | JPQL `COUNT(l)` với `l.id.orderId` | Một số lượng |
| Trả màn hình chỉ vài trường | JPQL projection | Danh sách DTO, không nhất thiết tạo managed entity |

## 5. Chỉ lấy các cột cần thiết từ khóa ghép

Không phải lúc nào màn hình cũng cần entity đầy đủ. Có thể chọn từng thuộc tính bằng JPQL:

~~~java
List<Integer> lineNumbers = em.createQuery(
    """
    SELECT l.id.lineNo
    FROM OrderLine l
    WHERE l.id.orderId = :orderId
    ORDER BY l.id.lineNo
    """,
    Integer.class
)
.setParameter("orderId", 1001L)
.getResultList();
~~~

Nếu muốn kết quả có cấu trúc rõ ràng, dùng DTO record:

~~~java
package com.example.shop.dto;

public record OrderLineRow(
    Long orderId,
    Integer lineNo,
    String productCode,
    int quantity
) {
}
~~~

JPQL constructor expression tạo record bằng đúng các giá trị chọn:

~~~java
List<OrderLineRow> rows = em.createQuery(
    """
    SELECT new com.example.shop.dto.OrderLineRow(
        l.id.orderId,
        l.id.lineNo,
        l.productCode,
        l.quantity
    )
    FROM OrderLine l
    WHERE l.id.orderId = :orderId
    ORDER BY l.id.lineNo
    """,
    OrderLineRow.class
)
.setParameter("orderId", 1001L)
.getResultList();
~~~

`OrderLineRow` không phải entity JPA. Bản thân record không được quản lý bởi persistence context và không tự động cập nhật cơ sở dữ liệu khi thay đổi dữ liệu nguồn. Đường dẫn tới các thành phần khóa vẫn là `l.id.orderId` và `l.id.lineNo` dù kết quả không phải entity.

### 5.1. Đếm hoặc tổng hợp theo thành phần khóa

~~~java
Long count = em.createQuery(
    """
    SELECT COUNT(l)
    FROM OrderLine l
    WHERE l.id.orderId = :orderId
    """,
    Long.class
)
.setParameter("orderId", 1001L)
.getSingleResult();
~~~

Hoặc đếm số dòng theo từng đơn hàng:

~~~java
List<Object[]> counts = em.createQuery(
    """
    SELECT l.id.orderId, COUNT(l)
    FROM OrderLine l
    GROUP BY l.id.orderId
    ORDER BY l.id.orderId
    """,
    Object[].class
).getResultList();
~~~

`COUNT` trả về `Long`. Với truy vấn nhóm, mỗi phần tử `Object[]` có giá trị đầu là `orderId` và giá trị thứ hai là số dòng. Trong ứng dụng lớn, có thể thay `Object[]` bằng DTO constructor projection để tránh ép kiểu thủ công.

## 6. Truy vấn theo thành phần khóa bằng Criteria API

Criteria API hữu ích khi bộ lọc được dựng động từ đầu vào người dùng hoặc khi muốn viết một query builder tái sử dụng.

Với `@EmbeddedId`, đường dẫn Criteria phải đi qua `id`:

~~~java
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Path;
import jakarta.persistence.criteria.Root;

CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<OrderLine> query =
    cb.createQuery(OrderLine.class);

Root<OrderLine> line = query.from(OrderLine.class);
Path<Long> orderIdPath = line.get("id").get("orderId");
Path<Integer> lineNoPath = line.get("id").get("lineNo");

query.select(line)
     .where(cb.equal(orderIdPath, 1001L))
     .orderBy(cb.asc(lineNoPath));

List<OrderLine> result =
    em.createQuery(query).getResultList();
~~~

Ở đây, `line.get("id").get("orderId")` tương ứng JPQL `l.id.orderId`. Các chuỗi `"id"`, `"orderId"` và `"lineNo"` là **tên thuộc tính Java**, không phải `"order_id"` hoặc `"line_no"` ở database.

### 6.1. Bộ lọc động nhiều điều kiện

Ví dụ tùy chọn lọc theo `orderId`, dải `lineNo` hoặc `productCode`:

~~~java
import jakarta.persistence.criteria.Predicate;
import java.util.ArrayList;
import java.util.List;

public List<OrderLine> searchLines(
        EntityManager em,
        Long orderId,
        Integer minLine,
        String productCode) {

    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<OrderLine> query =
        cb.createQuery(OrderLine.class);

    Root<OrderLine> root = query.from(OrderLine.class);
    List<Predicate> filters = new ArrayList<>();

    if (orderId != null) {
        filters.add(cb.equal(
            root.get("id").get("orderId"), orderId));
    }

    if (minLine != null) {
        filters.add(cb.ge(
            root.<OrderLineId>get("id")
                .<Integer>get("lineNo"), minLine));
    }

    if (productCode != null && !productCode.isBlank()) {
        filters.add(cb.equal(
            root.get("productCode"), productCode));
    }

    query.select(root)
         .where(filters.toArray(new Predicate[0]))
         .orderBy(
             cb.asc(root.get("id").get("orderId")),
             cb.asc(root.get("id").get("lineNo"))
         );

    return em.createQuery(query).getResultList();
}
~~~

Nếu không có điều kiện lọc, ví dụ trên sẽ trả toàn bộ dòng có trong bảng. Ở API thực tế cần **quy tắc kiểm soát quyền, giới hạn số kết quả và phân trang**; đặc biệt không nên vô tình cho phép người dùng truy vấn dữ liệu của các đơn hàng không thuộc phạm vi họ được truy cập.

### 6.2. Sử dụng static metamodel nếu có

Nếu dự án tạo JPA static metamodel, ví dụ `OrderLine_` và `OrderLineId_`, việc truy cập có thể trở thành:

~~~java
root.get(OrderLine_.id).get(OrderLineId_.orderId)
~~~

Lợi ích là giảm lỗi đánh sai tên thuộc tính, đồng thời IDE/compiler kiểm tra kiểu tốt hơn. Việc sinh metamodel cần annotation processor/build configuration phù hợp, và đây là lựa chọn thêm; query dùng tên chuỗi vẫn hợp lệ.

## 7. Khi dùng @IdClass: đường dẫn truy vấn khác gì?

`@IdClass` là cách ánh xạ khóa ghép khác trong JPA. Thay vì một field `@EmbeddedId`, entity khai báo **nhiều thuộc tính `@Id` trực tiếp**.

Giả sử tồn kho được xác định bởi hai trường `warehouseCode` và `sku`.

### 7.1. Lớp khóa cho @IdClass

~~~java
package com.example.shop.domain;

import java.io.Serializable;
import java.util.Objects;

public class InventoryStockId implements Serializable {

    private static final long serialVersionUID = 1L;

    public String warehouseCode;
    public String sku;

    public InventoryStockId() {
    }

    public InventoryStockId(String warehouseCode, String sku) {
        this.warehouseCode = warehouseCode;
        this.sku = sku;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof InventoryStockId that)) {
            return false;
        }
        return Objects.equals(warehouseCode, that.warehouseCode)
            && Objects.equals(sku, that.sku);
    }

    @Override
    public int hashCode() {
        return Objects.hash(warehouseCode, sku);
    }
}
~~~

Tên và kiểu các trường khóa trong `InventoryStockId` phải tương ứng với thuộc tính `@Id` của entity. Ở ví dụ này, cả hai là `String`.

### 7.2. Entity dùng @IdClass

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;

@Entity
@Table(name = "inventory_stock")
@IdClass(InventoryStockId.class)
public class InventoryStock {

    @Id
    @Column(name = "warehouse_code")
    private String warehouseCode;

    @Id
    @Column(name = "sku")
    private String sku;

    @Column(name = "available")
    private int available;

    protected InventoryStock() {
    }

    public String getWarehouseCode() {
        return warehouseCode;
    }

    public String getSku() {
        return sku;
    }

    public int getAvailable() {
        return available;
    }
}
~~~

SQL schema tương ứng:

~~~sql
CREATE TABLE inventory_stock (
    warehouse_code VARCHAR(40) NOT NULL,
    sku VARCHAR(80) NOT NULL,
    available INTEGER NOT NULL,
    PRIMARY KEY (warehouse_code, sku)
);
~~~

### 7.3. JPQL theo từng trường của @IdClass

Do các trường khóa nằm **trực tiếp trên entity**, JPQL không đi qua `id`:

~~~java
List<InventoryStock> stocks = em.createQuery(
    """
    SELECT s
    FROM InventoryStock s
    WHERE s.warehouseCode = :warehouseCode
    ORDER BY s.sku
    """,
    InventoryStock.class
)
.setParameter("warehouseCode", "HCM-01")
.getResultList();
~~~

Để tìm theo `sku` trên mọi kho:

~~~java
List<InventoryStock> inWarehouses = em.createQuery(
    """
    SELECT s
    FROM InventoryStock s
    WHERE s.sku = :sku
    ORDER BY s.warehouseCode
    """,
    InventoryStock.class
)
.setParameter("sku", "BOOK-01")
.getResultList();
~~~

Với Criteria API:

~~~java
Root<InventoryStock> root = query.from(InventoryStock.class);
query.where(cb.equal(root.get("warehouseCode"), "HCM-01"));
~~~

Với khóa đầy đủ, `find` vẫn nhận một **instance của lớp ID**:

~~~java
InventoryStockId key =
    new InventoryStockId("HCM-01", "BOOK-01");

InventoryStock stock =
    em.find(InventoryStock.class, key);
~~~

### 7.4. Bảng đối chiếu cú pháp

| Nhu cầu | `@EmbeddedId`: OrderLine | `@IdClass`: InventoryStock |
| --- | --- | --- |
| Khai báo khóa trên entity | `@EmbeddedId private OrderLineId id` | `@Id` đặt ở từng trường |
| Đường dẫn thành phần thứ nhất | `l.id.orderId` | `s.warehouseCode` |
| Đường dẫn thành phần thứ hai | `l.id.lineNo` | `s.sku` |
| Criteria thành phần | `root.get("id").get("orderId")` | `root.get("warehouseCode")` |
| Truy vấn theo toàn bộ khóa | `find(OrderLine.class, new OrderLineId(...))` | `find(InventoryStock.class, new InventoryStockId(...))` |
| Lọc theo một phần khóa | JPQL/Criteria trả tập entity | JPQL/Criteria trả tập entity |

Điểm cần nhớ là **tên thuộc tính trong mô hình Java quyết định đường dẫn truy vấn**, không phải việc hai cách này đều ánh xạ tới khóa chính SQL có nhiều cột.

## 8. Spring Data JPA: truy vấn theo thành phần khóa từ repository

**Spring Data JPA** là thư viện xây dựng trên JPA, bổ sung repository abstraction và phương thức truy vấn theo tên. Những phương thức `findBy...` sau đây **không phải API của JPA tiêu chuẩn**.

### 8.1. Repository cho @EmbeddedId

~~~java
package com.example.shop.repository;

import com.example.shop.domain.OrderLine;
import com.example.shop.domain.OrderLineId;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface OrderLineRepository
        extends JpaRepository<OrderLine, OrderLineId> {

    // "id.orderId" là đường dẫn tới thành phần của EmbeddedId.
    List<OrderLine> findById_OrderId(Long orderId);

    // Truy vấn tường minh khi cần thứ tự rõ ràng.
    @Query("""
           SELECT l
           FROM OrderLine l
           WHERE l.id.orderId = :orderId
           ORDER BY l.id.lineNo
           """)
    List<OrderLine> listByOrderId(
        @Param("orderId") Long orderId);
}
~~~

Trong `findById_OrderId`, dấu gạch dưới giúp Spring Data phân tách đường dẫn nested property: `id` → `orderId`. Điều này giảm nhầm lẫn khi tên thuộc tính có thể được diễn giải theo nhiều cách.

Sử dụng:

~~~java
List<OrderLine> lines =
    orderLineRepository.findById_OrderId(1001L);

// Khi có toàn bộ khóa, dùng chức năng repository theo ID:
Optional<OrderLine> one = orderLineRepository.findById(
    new OrderLineId(1001L, 2)
);
~~~

Tham số generic thứ hai của `JpaRepository<OrderLine, OrderLineId>` là **kiểu khóa đầy đủ** `OrderLineId`. Không đổi nó thành `Long` chỉ vì thường xuyên lọc theo `orderId`.

### 8.2. Repository cho @IdClass

~~~java
package com.example.shop.repository;

import com.example.shop.domain.InventoryStock;
import com.example.shop.domain.InventoryStockId;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryStockRepository
        extends JpaRepository<InventoryStock, InventoryStockId> {

    List<InventoryStock> findByWarehouseCode(String warehouseCode);

    List<InventoryStock> findBySku(String sku);
}
~~~

Do hai thành phần khóa là các field trực tiếp trên entity, tên phương thức cũng tham chiếu trực tiếp `WarehouseCode` và `Sku`.

### 8.3. Phân trang theo một thành phần khóa

Với danh sách rất dài, dùng truy vấn có phân trang:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PagedOrderLineRepository
        extends JpaRepository<OrderLine, OrderLineId> {

    Page<OrderLine> findById_OrderId(Long orderId, Pageable pageable);
}
~~~

Ví dụ:

~~~java
Pageable firstPage = PageRequest.of(
    0,
    20,
    Sort.by("id.lineNo").ascending()
);

Page<OrderLine> page =
    repository.findById_OrderId(1001L, firstPage);
~~~

Ví dụ này giả định các import Spring Data cho `PageRequest` và `Sort` đã có. Khi lọc chỉ theo một `orderId`, `lineNo` là duy nhất trong phạm vi đơn hàng nên dùng nó để sắp thứ tự ổn định.

Nếu phân trang qua **nhiều orderId**, nên thêm `orderId` rồi `lineNo` vào thứ tự sắp xếp để không có nhiều hàng có khóa sort bằng nhau. Phân trang offset có thể thay đổi kết quả khi dữ liệu được thêm/xóa giữa các trang; yêu cầu nhất quán cao có thể cần keyset pagination hoặc cơ chế snapshot phù hợp.

## 9. Truy vấn khi một thành phần khóa cũng là khóa ngoại: @MapsId

Trong mô hình thực tế, `order_id` thường là khóa ngoại từ `order_lines` sang bảng `purchase_orders`. Khi muốn `OrderLine` có quan hệ JPA tới `PurchaseOrder` mà vẫn dùng khóa ghép, có thể kết hợp `@EmbeddedId` và `@MapsId`.

Giả sử `PurchaseOrder` đã được ánh xạ thành entity có `Long id`. Đây là **biến thể thay thế** cho mapping `OrderLine` ở mục 2, không thêm nguyên đoạn này vào class cũ nếu chưa điều chỉnh các khai báo:

~~~java
@Entity
@Table(name = "order_lines")
public class OrderLineWithOrder {

    @EmbeddedId
    private OrderLineId id;

    @MapsId("orderId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_code", nullable = false)
    private String productCode;

    protected OrderLineWithOrder() {
    }

    // Constructor/getters/thuộc tính khác khi cần.
}
~~~

`@MapsId("orderId")` cho biết quan hệ `order` dùng thành phần `orderId` trong `OrderLineId` làm khóa ngoại/khóa chính. Dữ liệu cùng cột `order_id` không cần được ánh xạ thành một field số độc lập có khả năng ghi trùng nhau.

Có hai đường truy vấn hữu ích:

~~~jpql
-- Truy cập thành phần của khóa ghép:
SELECT l
FROM OrderLineWithOrder l
WHERE l.id.orderId = :orderId

-- Truy cập quan hệ tới entity cha:
SELECT l
FROM OrderLineWithOrder l
WHERE l.order.id = :orderId
~~~

Cả hai có thể diễn đạt điều kiện lọc cùng một mã đơn hàng trong mô hình này. Tuy nhiên, chúng là **đường dẫn khác nhau**; cách provider phát sinh SQL hoặc join còn tùy truy vấn và mapping.

Dùng đường dẫn `l.id.orderId` phù hợp khi quan tâm tới thành phần khóa. Dùng `l.order` thích hợp khi muốn truy cập thuộc tính khác của entity cha hoặc join theo quan hệ.

Không cần thiết phải khai báo `@MapsId` chỉ để truy vấn theo một thành phần khóa. Nếu entity chỉ cần `orderId` dưới dạng giá trị, mô hình `@EmbeddedId` thuần ở mục 2 vẫn hoạt động.

## 10. Hiệu năng: chỉ mục trên khóa ghép và thứ tự các cột

Khóa chính SQL `PRIMARY KEY (order_id, line_no)` thường tạo hoặc sử dụng cấu trúc chỉ mục hỗ trợ ràng buộc duy nhất. Đối với chỉ mục B-tree nhiều cột, **thứ tự cột** ảnh hưởng đến những điều kiện lọc có thể tận dụng hiệu quả phần đầu của index.

Với chỉ mục khóa ghép theo thứ tự:

~~~sql
PRIMARY KEY (order_id, line_no)
~~~

Một số truy vấn tiêu biểu:

| Điều kiện | Khả năng tận dụng chỉ mục có thứ tự `(order_id, line_no)` |
| --- | --- |
| `order_id = 1001` | Thường thuận lợi vì lọc theo cột đứng đầu |
| `order_id = 1001 AND line_no = 2` | Thường thuận lợi vì biết cả hai thành phần |
| `order_id = 1001 ORDER BY line_no` | Thường thuận lợi cho cả lọc và thứ tự |
| `line_no = 1` | Không có lợi thế tiền tố `order_id`; có thể cần scan hoặc chỉ mục bổ sung |
| `line_no BETWEEN 1 AND 5` | Phụ thuộc dữ liệu/optimizer; không nên mặc định tận dụng hiệu quả chỉ mục trên `(order_id, line_no)` |

Tùy cơ sở dữ liệu và kế hoạch thực thi, optimizer vẫn có thể chọn những cách dùng index khác nhau. Đây là **nguyên tắc thiết kế phổ biến**, không phải bảo đảm hiệu năng cho mọi DB.

Nếu nghiệp vụ hay truy vấn theo `line_no` độc lập, có thể cân nhắc:

~~~sql
CREATE INDEX idx_order_lines_line_no
    ON order_lines (line_no);
~~~

Trước khi thêm index, nên kiểm tra số lượng bản ghi, phân bố dữ liệu và kế hoạch truy vấn. Với PostgreSQL:

~~~sql
EXPLAIN ANALYZE
SELECT *
FROM order_lines
WHERE order_id = 1001
ORDER BY line_no;
~~~

`EXPLAIN ANALYZE` chạy câu truy vấn để đo kế hoạch, nên thận trọng với dữ liệu hoặc truy vấn nặng trên production. Truy vấn theo một thành phần khóa có thể làm lượng dữ liệu trả về lớn; luôn cân nhắc giới hạn số dòng và phân trang.

## 11. Số lượng kết quả, thứ tự và trường hợp không có dữ liệu

### 11.1. Vì sao nên dùng getResultList?

~~~java
List<OrderLine> result = em.createQuery(
    """
    SELECT l
    FROM OrderLine l
    WHERE l.id.orderId = :id
    """,
    OrderLine.class
).setParameter("id", 1001L)
 .getResultList();
~~~

Truy vấn theo `orderId` có thể có 0, 1 hoặc nhiều dòng. `getResultList()` trả về danh sách (có thể rỗng). `getSingleResult()` dành cho truy vấn được kỳ vọng đúng một kết quả; nó có thể ném exception nếu không có hoặc có nhiều kết quả.

### 11.2. Không có ORDER BY thì thứ tự không được bảo đảm

Khóa chính ghép không tự làm cho kết quả JPQL được trả theo thứ tự tăng dần. Dù SQL planner có thể dùng chỉ mục theo cặp `(order_id, line_no)`, ứng dụng chỉ nên dựa vào thứ tự khi truy vấn có `ORDER BY` rõ ràng.

Ví dụ danh sách dòng trong một đơn hàng:

~~~jpql
SELECT l
FROM OrderLine l
WHERE l.id.orderId = :orderId
ORDER BY l.id.lineNo ASC
~~~

Nếu lọc theo `lineNo` xuyên nhiều đơn hàng:

~~~jpql
SELECT l
FROM OrderLine l
WHERE l.id.lineNo = :lineNo
ORDER BY l.id.orderId ASC
~~~

### 11.3. Tham số phải có đúng kiểu

`OrderLineId.orderId` là `Long` và `lineNo` là `Integer`. Khi binding:

~~~java
.setParameter("orderId", 1001L) // Long
.setParameter("lineNo", 2)      // Integer
~~~

Việc đưa `"1001"` dạng `String` thay cho giá trị số có thể gây lỗi bind hoặc chuyển đổi tùy provider; không nên dựa vào ép kiểu ngầm. Với HTTP API, nên parse/validate input thành kiểu Java dự kiến **trước khi** gọi truy vấn.

## 12. Quy tắc phân quyền khi lọc theo một phần khóa

Lọc theo một thành phần của khóa chỉ là **điều kiện dữ liệu**, không phải điều kiện phân quyền. Trong hệ thống nhiều tenant, việc truy vấn theo khóa chưa đầy đủ có thể vô tình trả dữ liệu ngoài phạm vi người dùng.

Ví dụ bảng hóa đơn có khóa ghép:

~~~sql
CREATE TABLE tenant_invoices (
    tenant_id VARCHAR(40) NOT NULL,
    invoice_no VARCHAR(40) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    PRIMARY KEY (tenant_id, invoice_no)
);
~~~

Nếu chỉ truy vấn `invoice_no` mà không lọc `tenant_id`, có thể có các hóa đơn trùng số giữa nhiều tenant:

~~~sql
-- Có thể trả dữ liệu từ nhiều tenant:
SELECT * FROM tenant_invoices
WHERE invoice_no = 'INV-001';

-- Phạm vi tenant được xác định rõ:
SELECT * FROM tenant_invoices
WHERE tenant_id = :tenantId AND invoice_no = :invoiceNo;
~~~

Ở tầng JPA, với entity dùng `@EmbeddedId InvoiceId(tenantId, invoiceNo)`, điều kiện tương ứng sẽ là:

~~~jpql
SELECT i
FROM TenantInvoice i
WHERE i.id.tenantId = :tenantId
  AND i.id.invoiceNo = :invoiceNo
~~~

Tên entity/ID ở đoạn này minh họa cách đặt đường dẫn; ứng dụng cần định nghĩa chúng theo schema. `tenantId` phải được lấy từ **ngữ cảnh người dùng đã xác thực và được cấp quyền**, không tin hoàn toàn một tham số người dùng tự gửi. Định danh composite không tự thay thế row-level security hoặc authorization ở service/database.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| JPQL báo “could not resolve property: orderId” | Entity dùng `@EmbeddedId` nhưng viết `l.orderId` | Dùng `l.id.orderId` |
| JPQL báo không tìm thấy thuộc tính `id` | Entity dùng `@IdClass`, không có field `id` | Dùng field `@Id` trực tiếp, ví dụ `s.warehouseCode` |
| `find(...)` không trả các dòng cùng `orderId` | `find` luôn làm việc với toàn bộ primary key | Dùng JPQL/Criteria `WHERE l.id.orderId = ...` |
| `getSingleResult()` báo nhiều kết quả | Một phần khóa không duy nhất | Dùng `getResultList()` hoặc bổ sung điều kiện |
| JPQL dùng `order_id` | Nhầm tên cột SQL với tên thuộc tính Java | Dùng `orderId` trong đường dẫn `l.id.orderId` |
| Spring Data báo không tìm thấy property | Method name không biểu diễn đúng nested path | Dùng `findById_OrderId` hoặc `@Query` tường minh |
| JPA không nhận diện khóa ghép | Class ID thiếu `Serializable`/`equals/hashCode` hoặc mapping không đúng | Khai báo key class đúng quy tắc JPA |
| Kết quả phân trang bị đảo thứ tự | Thiếu `ORDER BY` đủ ổn định | Sắp theo các thành phần khóa hoặc bộ khóa duy nhất |
| Truy vấn theo `lineNo` chậm | Chỉ mục `(order_id, line_no)` không thuận lợi cho lọc chỉ bằng cột thứ hai | Xem plan, cân nhắc index riêng theo workload |
| Kết quả chứa đơn hàng/tenant khác | Điều kiện lọc chưa giới hạn quyền truy cập | Áp dụng tenant/owner scope ở tầng truy vấn và service |
| Sửa một phần khóa trên managed entity rồi gặp lỗi | Thay đổi primary key của entity sau khi persist | Giữ ID ổn định; dùng quy trình dữ liệu phù hợp nếu cần đổi định danh |
| Query trả rỗng nhưng SQL thủ công có dữ liệu | Sai kiểu tham số, mapping cột/schema hoặc ID bị viết nhầm | Kiểm tra đường dẫn Java, parameter và schema tương ứng |

## 14. Bài tập thực hành

### Bài 1. Viết JPQL cho @EmbeddedId

Cho entity có `@EmbeddedId private OrderLineId id`, với `OrderLineId` gồm `Long orderId` và `Integer lineNo`. Hãy lấy tất cả dòng của đơn hàng `500L`.

**Đáp án:**

~~~java
List<OrderLine> lines = em.createQuery(
    """
    SELECT l FROM OrderLine l
    WHERE l.id.orderId = :id
    ORDER BY l.id.lineNo
    """,
    OrderLine.class
).setParameter("id", 500L)
 .getResultList();
~~~

### Bài 2. Chọn đúng cú pháp cho @IdClass

`InventoryStock` được khai báo với hai field `@Id`: `warehouseCode` và `sku`. Câu JPQL nào đúng?

~~~jpql
-- A
SELECT s FROM InventoryStock s WHERE s.id.warehouseCode = :warehouse

-- B
SELECT s FROM InventoryStock s WHERE s.warehouseCode = :warehouse
~~~

**Đáp án:** B. Với `@IdClass` của ví dụ, entity không có thuộc tính nhúng `id`. Trường `warehouseCode` nằm trực tiếp trên entity.

### Bài 3. Dùng find khi chỉ biết orderId?

Bạn chỉ biết `orderId = 1001L` và không biết `lineNo`. Có nên gọi `em.find(OrderLine.class, new OrderLineId(1001L, null))` không?

**Đáp án:** Không. Đây không phải khóa đầy đủ; `find` không truy vấn theo wildcard. Dùng JPQL hoặc Criteria lọc `l.id.orderId` và nhận danh sách.

### Bài 4. Tiêu chí sắp xếp cho phân trang

API cần hiển thị dòng sản phẩm của **mọi đơn hàng**, phân trang 20 dòng, không có điều kiện lọc. Nếu chỉ sắp theo `lineNo`, kết quả có ổn định không?

**Đáp án:** Chưa đủ vì nhiều đơn hàng cùng có `lineNo = 1`. Nên sắp theo cả `orderId` và `lineNo` (hoặc một bộ thuộc tính tạo thứ tự duy nhất) để hạn chế thứ tự không xác định giữa những dòng có giá trị sort giống nhau.

### Bài 5. Khóa ghép có cột tenant

Khóa hóa đơn là `(tenantId, invoiceNo)`. Người dùng gõ số hóa đơn `INV-001`. Truy vấn chỉ theo `invoiceNo` có an toàn không?

**Đáp án:** Chưa đủ nếu dữ liệu chứa nhiều tenant. Cần thêm điều kiện tenant được xác định từ phiên đã xác thực và áp dụng kiểm tra quyền phù hợp. Tính duy nhất của cặp khóa không giúp `invoiceNo` đơn lẻ xác định một bản ghi trên toàn hệ thống.

### Bài 6. Viết Criteria cho thành phần thứ hai

Với `@EmbeddedId OrderLineId`, viết điều kiện lấy những dòng có `lineNo >= 5`.

**Đáp án:**

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<OrderLine> cq = cb.createQuery(OrderLine.class);
Root<OrderLine> root = cq.from(OrderLine.class);

cq.select(root)
  .where(cb.ge(
      root.<OrderLineId>get("id").<Integer>get("lineNo"),
      5
  ));

List<OrderLine> result = em.createQuery(cq).getResultList();
~~~

### Bài 7. Đếm số dòng của một đơn hàng

Viết câu JPQL trả về số dòng của `orderId = 700L`.

**Đáp án:**

~~~java
Long count = em.createQuery(
    "SELECT COUNT(l) FROM OrderLine l WHERE l.id.orderId = :orderId",
    Long.class
).setParameter("orderId", 700L)
 .getSingleResult();
~~~

`getSingleResult()` phù hợp ở đây vì `COUNT` không có `GROUP BY` trả về một giá trị tổng hợp, kể cả khi không có bản ghi khớp (giá trị bằng 0).

## 15. Ghi nhớ

- **Khóa ghép** định danh một entity bằng **tổ hợp nhiều thành phần**; từng thành phần riêng lẻ thường không duy nhất.
- Với **`@EmbeddedId`**, truy vấn theo một phần khóa bằng **đường dẫn lồng** như `l.id.orderId` và `l.id.lineNo`.
- Với **`@IdClass`**, các thành phần khóa là **thuộc tính trực tiếp** của entity như `s.warehouseCode` và `s.sku`.
- **`EntityManager.find` yêu cầu toàn bộ khóa**. Muốn lọc theo một phần khóa, dùng JPQL, Criteria API hoặc repository query.
- **JPQL dùng tên thuộc tính Java**; `@Column(name = "...")` quyết định tên cột SQL mà provider sẽ sử dụng.
- **Truy vấn theo một phần khóa có thể trả nhiều bản ghi**; cần lựa chọn API kết quả, thứ tự sắp xếp và phân trang phù hợp.
- **Thứ tự các cột trong chỉ mục composite có ảnh hưởng hiệu năng**, đặc biệt với truy vấn chỉ theo thành phần ở phía sau.
- **Không coi một phần khóa là điều kiện cấp quyền**. Với ứng dụng nhiều tenant, phải ràng buộc truy vấn vào tenant/owner được xác thực.

Một cách nhớ ngắn gọn: **khóa ghép là một định danh gồm nhiều trường; JPA cho phép lọc theo từng trường như các thuộc tính bình thường, nhưng cú pháp phụ thuộc cấu trúc ánh xạ `@EmbeddedId` hay `@IdClass`**.
