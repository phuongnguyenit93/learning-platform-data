# Khai báo và tạo truy vấn thủ tục

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Nhóm kiến thức:** Thủ tục lưu trữ

Trong ứng dụng Java sử dụng JPA, phần lớn thao tác truy vấn và cập nhật dữ liệu có thể được diễn đạt bằng JPQL, Criteria API hoặc các phương thức repository. Tuy nhiên, hệ thống doanh nghiệp đôi khi đã có **stored procedure (thủ tục lưu trữ)** ở cơ sở dữ liệu: quy trình điều chỉnh tồn kho, chốt sổ, tính phí, tổng hợp báo cáo hoặc tích hợp một hệ thống legacy. Khi đó, JPA cung cấp **StoredProcedureQuery** để gọi thủ tục, đăng ký tham số, thực thi và đọc kết quả.

Ví dụ một thủ tục có tên **adjust_product_stock** nhận ID sản phẩm và số lượng thay đổi:

~~~java
StoredProcedureQuery query =
    entityManager.createStoredProcedureQuery("adjust_product_stock");

query.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN);
query.registerStoredProcedureParameter(
    2, Integer.class, ParameterMode.IN);

query.setParameter(1, 42L);
query.setParameter(2, -3);

query.execute();
~~~

Cùng một thủ tục còn có thể được khai báo trước bằng **@NamedStoredProcedureQuery** rồi tạo truy vấn theo **tên logic**:

~~~java
StoredProcedureQuery query =
    entityManager.createNamedStoredProcedureQuery(
        "Product.adjustStock"
    );

query.setParameter("p_product_id", 42L);
query.setParameter("p_delta", -3);
query.execute();
~~~

Hai ví dụ có cùng ý tưởng nhưng **khác nơi định nghĩa metadata**: ví dụ đầu tạo trực tiếp và đăng ký tham số trong code; ví dụ sau dựa vào metadata khai báo bằng annotation. Bài học giải thích cả hai con đường, những kiểu tham số **IN, OUT, INOUT, REF_CURSOR**, cách lấy nhiều loại kết quả, ánh xạ entity/DTO, transaction, xử lý lỗi, sự khác biệt giữa database và cách kiểm thử.

Điều quan trọng nhất: **JPA chuẩn hóa API gọi thủ tục, không làm cho ngôn ngữ hoặc hành vi thủ tục của PostgreSQL, SQL Server, Oracle và các hệ quản trị khác trở nên giống hệt nhau.** Phần SQL bên dưới ghi rõ hệ quản trị được sử dụng để tránh nhầm cú pháp.

## 1. Stored procedure là gì và khi nào nên dùng?

**Stored procedure** là đơn vị chương trình được định nghĩa và lưu phía cơ sở dữ liệu, có thể được gọi bằng tên, nhận tham số, thực hiện SQL và tùy DB có thể trả tham số OUT, result set, mã trạng thái hoặc nhiều kết quả.

Sơ đồ khái niệm:

~~~text
HTTP request / scheduled job
          |
          v
Service Java (@Transactional)
          |
          v
EntityManager
          |
          v
StoredProcedureQuery
    | register parameters
    | bind values
    | execute
    | read outputs/results
          |
          v
JDBC driver + database dialect
          |
          v
Database procedure
    | validate
    | INSERT / UPDATE / DELETE / SELECT
    | set OUT parameters
          |
          v
Transaction commit / rollback do ứng dụng kiểm soát
~~~

Những use case có thể phù hợp:

- Một nghiệp vụ cần thực hiện nhiều câu SQL có quan hệ chặt chẽ và DB đã cung cấp thủ tục ổn định.
- Hệ thống đang tích hợp một database legacy có interface procedure được các ứng dụng khác cùng dùng.
- Tác vụ tổng hợp hoặc biến đổi dữ liệu lớn tận dụng các khả năng SQL riêng của DBMS.
- Quy trình được quản lý, cấp quyền và triển khai tại database với contract rõ.
- Đội ngũ DBA đã tối ưu và kiểm soát triển khai của procedure.

Không phải mọi cập nhật đều cần procedure. Nếu thao tác đơn giản chỉ sửa thuộc tính một entity, **find + dirty checking** có thể rõ ràng hơn. Nếu chỉ cập nhật nhiều hàng theo điều kiện, **bulk JPQL** hoặc native SQL có thể đủ. Stored procedure không tự nhanh hơn mọi JPQL, và việc lạm dụng có thể làm tăng phụ thuộc database.

### 1.1. Procedure, function, query và transaction là bốn khái niệm khác nhau

| Khái niệm | Đặc điểm |
|---|---|
| JPQL SELECT | Truy vấn theo entity model và thuộc tính Java |
| Criteria API | Xây truy vấn Java có cấu trúc |
| Native SQL | SQL theo bảng/cột/cú pháp database |
| Stored procedure | Chương trình ở DB gọi theo tên và tham số |
| Database function | Hàm DB có thể trả một giá trị/bảng, cú pháp gọi phụ thuộc DB |
| Transaction | Ranh giới commit/rollback nhiều thao tác, có thể bao gồm CALL |

Ví dụ PostgreSQL phân biệt **CALL procedure** và **SELECT function**. Việc database có một routine tên **calculate_total** chưa cho biết chắc nên gọi bằng StoredProcedureQuery: cần biết routine ấy là **procedure hay function**, trả dữ liệu theo cách nào, và driver/provider hỗ trợ mô hình đó ra sao.

### 1.2. Vì sao không dùng createNativeQuery cho mọi CALL?

Một số hệ thống có thể thực thi lệnh CALL qua native SQL. Tuy nhiên **StoredProcedureQuery** được thiết kế riêng để:
- Đăng ký chế độ tham số IN/OUT/INOUT/REF_CURSOR;
- Bind các tham số theo vị trí hoặc tên khi được hỗ trợ;
- Nhận output parameters;
- Đọc result sets, update counts và nhiều kết quả theo API của JPA;
- Gắn metadata gọi thủ tục với **@NamedStoredProcedureQuery**.

Khi thủ tục chỉ có IN và không trả kết quả, native SQL có thể trông đơn giản, nhưng khi có OUT/result sets thì API dành riêng thường giúp contract rõ hơn.

### 1.3. Điều kiện tiên quyết

Để gọi thành công:
1. Database đã có thủ tục đúng tên và schema.
2. Application account có quyền **EXECUTE** hoặc quyền tương đương.
3. JDBC driver và JPA provider hỗ trợ kiểu routine/tham số bạn dùng.
4. Kiểu Java bind tương thích kiểu SQL của tham số.
5. Transaction phù hợp với thủ tục có tác động ghi.
6. Cách xử lý output/result set được xác định trước.
7. Schema migration triển khai thủ tục trước khi code gọi.

Chỉ khai báo annotation trong Java **không tạo ra stored procedure tại database**. Bạn phải triển khai SQL procedure bằng Flyway, Liquibase, script quản trị hoặc một cơ chế triển khai DB được kiểm soát.

## 2. Mô hình dữ liệu ví dụ: điều chỉnh tồn kho

Bài học dùng một quy trình: sản phẩm có số lượng tồn kho và lịch sử điều chỉnh. Một stored procedure thay đổi số lượng và ghi audit trong **cùng transaction**.

### 2.1. SQL cho PostgreSQL

SQL sau dành cho **PostgreSQL**, minh họa DDL tối giản:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL DEFAULT 0,
    sku VARCHAR(48) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    stock_quantity INTEGER NOT NULL
        CHECK (stock_quantity >= 0)
);

CREATE TABLE stock_adjustments (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id),
    delta INTEGER NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO products (sku, name, stock_quantity)
VALUES ('KB-001', 'Mechanical Keyboard', 20);
~~~

**stock_quantity** không được âm. Ràng buộc CHECK ở database bảo vệ dữ liệu kể cả khi ghi bằng SQL trực tiếp hoặc từ ứng dụng khác.

### 2.2. Entity Product

~~~java
package com.example.inventory;

import jakarta.persistence.*;

@Entity
@Table(name = "products")
@NamedStoredProcedureQuery(
    name = "Product.adjustStock",
    procedureName = "adjust_product_stock",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_product_id",
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_delta",
            type = Integer.class
        )
    }
)
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    @Column(name = "sku", nullable = false, unique = true)
    private String sku;

    @Column(name = "name", nullable = false)
    private String name;

    @Column(name = "stock_quantity", nullable = false)
    private Integer stockQuantity;

    protected Product() {}

    public Product(String sku, String name, Integer stockQuantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        if (stockQuantity == null || stockQuantity < 0) {
            throw new IllegalArgumentException("Tồn kho không hợp lệ");
        }
        this.sku = sku;
        this.name = name;
        this.stockQuantity = stockQuantity;
    }

    public Long getId() { return id; }
    public Long getVersion() { return version; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public Integer getStockQuantity() { return stockQuantity; }
}
~~~

Class có **@NamedStoredProcedureQuery** để dùng trong phần 5. Annotation mô tả thủ tục và tham số; bản thân entity **không phải thủ tục** và không chứa logic SQL của thủ tục.

### 2.3. Stored procedure thực hiện cập nhật và ghi lịch sử

PostgreSQL PL/pgSQL:

~~~sql
CREATE OR REPLACE PROCEDURE adjust_product_stock(
    IN p_product_id BIGINT,
    IN p_delta INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_stock INTEGER;
BEGIN
    IF p_delta = 0 THEN
        RAISE EXCEPTION 'delta must be non-zero';
    END IF;

    UPDATE products
       SET stock_quantity = stock_quantity + p_delta,
           version = version + 1
     WHERE id = p_product_id
       AND stock_quantity + p_delta >= 0
    RETURNING stock_quantity INTO v_stock;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Product missing or insufficient stock: %',
            p_product_id;
    END IF;

    INSERT INTO stock_adjustments(product_id, delta)
    VALUES (p_product_id, p_delta);
END;
$$;
~~~

Trong ví dụ này:
- **p_product_id** và **p_delta** là hai tham số IN.
- UPDATE chỉ thành công khi sản phẩm tồn tại và tồn kho không trở thành số âm.
- Sau UPDATE, procedure ghi một dòng lịch sử.
- Nếu điều kiện không thỏa, procedure ném exception; caller phải xử lý transaction.
- Cột **version** được tăng bởi SQL nhằm thể hiện rằng **thay đổi dữ liệu bằng thủ tục nằm ngoài dirty checking thông thường của JPA**.

Đoạn SQL không gọi COMMIT hoặc ROLLBACK bên trong procedure. Một JPA service có transaction bao quanh sẽ kiểm soát ranh giới commit/rollback.

### 2.4. Vì sao cần xét @Version khi procedure cập nhật entity?

JPA dùng @Version để phát hiện xung đột khi update managed entity. Khi stored procedure cập nhật trực tiếp bảng:
- Provider **không tự biết** từng thay đổi do procedure gây ra.
- Managed Product đã được load trước đó có thể giữ **stockQuantity/version cũ** trong RAM.
- Nếu procedure không cập nhật version, một số thay đổi ngoài ORM có thể không được optimistic locking phát hiện như mong muốn.

Ở SQL ví dụ, procedure tăng version bằng tay. Điều này cần được áp dụng nhất quán với tất cả đường ghi ngoài ORM. Nếu version do provider/DB có quy ước phức tạp, phải thiết kế procedure tương thích; không cứ thêm **version + 1** vào mọi schema mà chưa xét kiểu/version strategy.

## 3. API trung tâm: StoredProcedureQuery

Interface **jakarta.persistence.StoredProcedureQuery** là cách JPA biểu diễn một lời gọi stored procedure. Luồng điển hình:

~~~text
EntityManager
    |
    +-- createStoredProcedureQuery("procedure_name")
    |       |
    |       +-- registerStoredProcedureParameter(...)
    |       +-- setParameter(...)
    |       +-- execute()
    |       +-- getOutputParameterValue(...) nếu có OUT
    |       +-- getResultList()/getUpdateCount() nếu có kết quả
    |
    +-- createNamedStoredProcedureQuery("LogicalName")
            |
            +-- dùng metadata từ @NamedStoredProcedureQuery
            +-- setParameter(...)
            +-- execute()
~~~

### 3.1. Tạo query trực tiếp

~~~java
StoredProcedureQuery query =
    em.createStoredProcedureQuery("adjust_product_stock");
~~~

Chuỗi truyền vào là tên procedure mà provider/driver sẽ dùng để gọi trong database. Nếu routine được đặt trong schema riêng, có thể cần tên đủ schema như **inventory.adjust_product_stock**, tùy cấu hình schema resolution.

### 3.2. Tạo query từ khai báo có tên

~~~java
StoredProcedureQuery query =
    em.createNamedStoredProcedureQuery("Product.adjustStock");
~~~

Chuỗi **Product.adjustStock** là tên logic trong metadata JPA, **không phải** tên procedure ở database. Metadata phải được provider nhận diện lúc khởi tạo persistence unit.

### 3.3. Đăng ký tham số

Với query trực tiếp, khi procedure cần tham số, ta đăng ký:

~~~java
query.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN);

query.registerStoredProcedureParameter(
    2, Integer.class, ParameterMode.IN);
~~~

Mỗi đăng ký mô tả:
- **Vị trí** hoặc **tên** tham số;
- **Kiểu Java**;
- **Chế độ tham số**.

Vị trí thường bắt đầu từ **1** theo API positional registration của stored procedure.

### 3.4. Bind giá trị

~~~java
query.setParameter(1, productId);
query.setParameter(2, quantityDelta);
~~~

Với tham số IN và INOUT, cần cung cấp giá trị khi thủ tục yêu cầu. Đừng bind tham số OUT như tham số IN thông thường chỉ để “có giá trị”.

### 3.5. Thực thi

~~~java
boolean firstResultIsResultSet = query.execute();
~~~

Giá trị boolean là tín hiệu về **loại kết quả đầu tiên** theo API:
- **true**: kết quả đầu tiên là result set;
- **false**: kết quả đầu tiên không phải result set (có thể là update count hoặc không có kết quả).

**false không đồng nghĩa lời gọi thất bại**. Một thủ tục chỉ UPDATE và ghi audit có thể execute thành công nhưng không trả result set.

### 3.6. StoredProcedureQuery không phải TypedQuery<Product> mặc định

Một lời gọi chỉ cập nhật dữ liệu không cần một Product result. Nếu procedure trả result set, ta cần khai báo cách ánh xạ:
- Entity class;
- SQL result set mapping;
- Hoặc xử lý dạng scalar/Object[]/các result shape mà provider cung cấp.

Không ép mọi StoredProcedureQuery thành Product list chỉ vì tên procedure chứa Product.

## 4. Tạo trực tiếp với tham số theo vị trí

Ví dụ service Java cho PostgreSQL procedure ở phần 2:

~~~java
package com.example.inventory;

import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;

public class InventoryProcedureDao {
    private final EntityManager em;

    public InventoryProcedureDao(EntityManager em) {
        this.em = em;
    }

    public void adjustStock(long productId, int delta) {
        StoredProcedureQuery query =
            em.createStoredProcedureQuery("adjust_product_stock");

        query.registerStoredProcedureParameter(
            1, Long.class, ParameterMode.IN);

        query.registerStoredProcedureParameter(
            2, Integer.class, ParameterMode.IN);

        query.setParameter(1, productId);
        query.setParameter(2, delta);
        query.execute();
    }
}
~~~

Cách này thường dễ dùng khi procedure chỉ có vài tham số và bạn không muốn tạo metadata named query. Tuy nhiên nếu procedure được gọi ở nhiều nơi, việc đăng ký lặp lại có thể gây sai lệch khi signature thay đổi.

### 4.1. Vị trí phải khớp signature

Procedure:

~~~sql
adjust_product_stock(
    IN p_product_id BIGINT,
    IN p_delta INTEGER
)
~~~

thì:
- Vị trí 1 → product ID;
- Vị trí 2 → delta.

Nếu vô tình đảo:

~~~java
query.setParameter(1, (long) delta);
query.setParameter(2, productId);
~~~

có thể lỗi type hoặc gọi sai giá trị; nếu DB chấp nhận ép kiểu, bug càng khó phát hiện. Dùng named registration có thể làm call site dễ đọc hơn, nhưng **khả năng bind theo tên phụ thuộc provider, driver và database**.

### 4.2. Đăng ký theo tên

Khi provider hỗ trợ named stored procedure parameters:

~~~java
StoredProcedureQuery query =
    em.createStoredProcedureQuery("adjust_product_stock");

query.registerStoredProcedureParameter(
    "p_product_id", Long.class, ParameterMode.IN);

query.registerStoredProcedureParameter(
    "p_delta", Integer.class, ParameterMode.IN);

query.setParameter("p_product_id", 42L);
query.setParameter("p_delta", -3);
query.execute();
~~~

Tên ở đây phải phù hợp interface procedure và cách provider/driver hỗ trợ tên SQL routine parameters. **Không mặc định mọi JDBC driver hỗ trợ parameter names**, nhất là với các dialect có quy tắc khác về chữ hoa/thường hoặc metadata.

### 4.3. Không trộn hai cách bind tùy tiện

Một query đã đăng ký parameters theo vị trí thì nên bind theo vị trí; một query đăng ký theo tên thì bind theo tên. Việc trộn positional/named registration có thể gây lỗi và làm code khó bảo trì. Chọn một chiến lược cho mỗi procedure call, trừ khi provider có tài liệu rõ ràng hỗ trợ một trường hợp đặc biệt.

### 4.4. Không nối trực tiếp dữ liệu vào tên procedure

Sai về mô hình bảo mật:

~~~java
String procedure = request.getProcedureName();
em.createStoredProcedureQuery(procedure);
~~~

**Tên procedure là một phần cấu trúc lời gọi, không phải dữ liệu bind bằng setParameter.** Không cho client chọn arbitrary procedure name. Dùng whitelist tên procedure do server kiểm soát và kiểm tra quyền thực hiện nghiệp vụ.

### 4.5. Kiểu Java phải tương thích kiểu SQL

| Tham số SQL minh họa | Java thường dùng | Ghi chú |
|---|---|---|
| BIGINT | Long.class | Không tự chọn Integer cho ID lớn |
| INTEGER | Integer.class | Số nguyên phù hợp |
| VARCHAR | String.class | Length/encoding theo DB |
| NUMERIC/DECIMAL | BigDecimal.class | Tiền tệ/giá trị decimal |
| BOOLEAN | Boolean.class | Khả năng DB/JDBC hỗ trợ |
| DATE | LocalDate.class hoặc kiểu phù hợp | Phụ thuộc provider/phiên bản |
| TIMESTAMP | LocalDateTime/Instant hoặc kiểu phù hợp | Timezone/precision quan trọng |
| CURSOR | void.class/REF_CURSOR theo API/provider | Rất phụ thuộc DB |

Không dựa vào auto-conversion kiểu số một cách mù quáng: nếu procedure nhận DECIMAL nhưng code đăng ký Double, có thể mất precision hoặc bị driver từ chối.

## 5. Khai báo @NamedStoredProcedureQuery

Khi thủ tục được dùng thường xuyên và signature tương đối ổn định, **@NamedStoredProcedureQuery** cho phép mô tả tên logic, tên database procedure và danh sách tham số tại metadata JPA.

Ví dụ trên Product đã khai báo:

~~~java
@NamedStoredProcedureQuery(
    name = "Product.adjustStock",
    procedureName = "adjust_product_stock",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_product_id",
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_delta",
            type = Integer.class
        )
    }
)
~~~

### 5.1. Phân biệt name và procedureName

| Thuộc tính annotation | Ý nghĩa |
|---|---|
| name = "Product.adjustStock" | Tên logic tra cứu trong JPA persistence unit |
| procedureName = "adjust_product_stock" | Tên procedure thật ở database |
| parameters | Metadata parameter modes, names và Java types |
| resultClasses | Các lớp dùng để ánh xạ result sets phù hợp |
| resultSetMappings | Tên các @SqlResultSetMapping cho result sets phù hợp |
| hints | Provider/JPA query hints khi được hỗ trợ |

**Tên logic không tự phải trùng tên database routine**. Prefix theo entity/module giúp giảm khả năng trùng tên giữa nhiều stored procedure queries.

### 5.2. Gọi named procedure

~~~java
public void adjustStock(
        EntityManager em,
        Long productId,
        Integer delta) {

    StoredProcedureQuery query =
        em.createNamedStoredProcedureQuery(
            "Product.adjustStock");

    query.setParameter("p_product_id", productId);
    query.setParameter("p_delta", delta);

    query.execute();
}
~~~

Nhờ metadata ở annotation, caller **không phải đăng ký lại** các tham số đã được định nghĩa. Việc đăng ký lại không cần thiết có thể gây xung đột với provider.

### 5.3. Annotation nên đặt ở đâu?

Named stored procedure query là **metadata của persistence unit**, thường được đặt trên một entity class (hoặc vị trí metadata JPA phù hợp). Không nhất thiết thủ tục phải luôn trả chính entity được annotation. Ví dụ metadata đặt trên Product có thể mô tả một routine báo cáo trả DTO/scalar nếu mapping tương ứng được khai báo.

Đừng nhầm “procedure của Product” trong tên logic với việc JPA tạo một method SQL trong Product class.

### 5.4. Khai báo nhiều named procedures

Khi cần nhiều thủ tục trên cùng entity:

~~~java
@NamedStoredProcedureQueries({
    @NamedStoredProcedureQuery(
        name = "Product.adjustStock",
        procedureName = "adjust_product_stock",
        parameters = {
            @StoredProcedureParameter(
                mode = ParameterMode.IN,
                name = "p_product_id",
                type = Long.class
            ),
            @StoredProcedureParameter(
                mode = ParameterMode.IN,
                name = "p_delta",
                type = Integer.class
            )
        }
    ),
    @NamedStoredProcedureQuery(
        name = "Product.archiveOld",
        procedureName = "archive_old_products",
        parameters = {
            @StoredProcedureParameter(
                mode = ParameterMode.IN,
                name = "p_before_id",
                type = Long.class
            )
        }
    )
})
~~~

Đoạn trên minh họa cấu trúc metadata; **archive_old_products** phải tồn tại thật nếu muốn gọi. Với Java/JPA hiện đại, annotation repeatable có thể cho phép viết nhiều @NamedStoredProcedureQuery trực tiếp, tùy API/phiên bản.

### 5.5. Đổi signature procedure cần đồng bộ

Nếu database thêm tham số bắt buộc:
- Cập nhật migration SQL procedure;
- Cập nhật @StoredProcedureParameter;
- Cập nhật những caller setParameter;
- Cập nhật integration tests;
- Xem tương thích ngược với ứng dụng đang triển khai phiên bản cũ.

Trong môi trường có rolling deployment, đổi procedure contract có thể gây downtime nếu phiên bản Java cũ và mới cùng chạy. Có thể cần procedure mới có tên versioned hoặc cơ chế backward-compatible.

## 6. Các kiểu ParameterMode

JPA định nghĩa những chế độ chính trong **jakarta.persistence.ParameterMode**:

| Chế độ | Ý nghĩa | Ứng dụng cung cấp input? | Có đọc output? |
|---|---|---|---|
| IN | Tham số đầu vào | Có | Không |
| OUT | Tham số đầu ra | Không theo ý nghĩa thông thường | Có |
| INOUT | Vừa vào vừa ra | Có | Có |
| REF_CURSOR | Cursor trả tập kết quả | Theo contract DB | Đọc result set/cursor theo provider |

Không nhầm OUT với việc result set trả nhiều rows. **Một OUT parameter** có thể chỉ là số, chuỗi hay trạng thái; **một result set** là bảng kết quả nhiều dòng/cột.

### 6.1. IN

~~~java
query.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN);

query.setParameter(1, productId);
~~~

Một parameter IN chỉ cung cấp dữ liệu cho procedure; nó không có output mới sau execute theo contract.

### 6.2. OUT

~~~java
query.registerStoredProcedureParameter(
    2, Long.class, ParameterMode.OUT);
~~~

Sau execute, có thể dùng:

~~~java
Object value = query.getOutputParameterValue(2);
~~~

Kết quả phải được ép kiểu hoặc yêu cầu kiểu phù hợp với registration và provider. Ví dụ chi tiết ở phần 7.

### 6.3. INOUT

~~~java
query.registerStoredProcedureParameter(
    2, Integer.class, ParameterMode.INOUT);

query.setParameter(2, 100);

query.execute();

Integer updatedValue =
    (Integer) query.getOutputParameterValue(2);
~~~

INOUT nhận giá trị ban đầu từ Java và có thể trả giá trị mới sau khi procedure hoàn thành. Không có nghĩa Java Integer object sẽ được thay đổi tại chỗ: Integer immutable, giá trị mới phải được **đọc lại từ output**.

### 6.4. REF_CURSOR

REF_CURSOR dành cho routine có kết quả kiểu cursor theo database/JDBC contract. Không phải mọi DB đều dùng REF_CURSOR giống nhau; một procedure trả SELECT result set trực tiếp có thể không cần REF_CURSOR.

~~~java
StoredProcedureQuery query =
    em.createStoredProcedureQuery("cursor_report");

query.registerStoredProcedureParameter(
    1, void.class, ParameterMode.REF_CURSOR);
~~~

Đây chỉ là **hình dạng API minh họa**. Việc đăng ký vị trí nào, kiểu Java nào, execute, lấy cursor bằng getResultList hay getOutputParameterValue, cũng như requirement transaction có thể khác giữa Oracle/PostgreSQL và provider. Không copy đoạn đăng ký cursor này vào production mà chưa đối chiếu routine signature, JDBC driver và tài liệu provider.

### 6.5. NULL ở tham số IN

Tham số nullable không phải lúc nào cũng được truyền đồng nhất. Một số database procedure có default parameters; JPA/provider có thể có quy tắc riêng về **không bind tham số** so với **bind explicit NULL**.

Hai hành vi có thể khác:
1. Bỏ tham số để DB dùng default.
2. Gửi tham số NULL thực sự.

Với procedure có default argument và caller tùy chọn, cần định nghĩa contract rõ và thử trên DB/provider; đừng mặc định **setParameter(name, null)** luôn tương đương “không gửi tham số”.

## 7. Ví dụ OUT parameter với SQL Server

Để tránh nhầm cú pháp giữa các database, phần này dùng **Microsoft SQL Server**, không dùng SQL PostgreSQL ở phần 2.

Giả sử cần đếm Product có tồn kho ít nhất một ngưỡng. SQL Server procedure:

~~~sql
CREATE OR ALTER PROCEDURE dbo.count_products_above_stock
    @minimum_stock INT,
    @product_count BIGINT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT @product_count = COUNT_BIG(*)
    FROM dbo.products
    WHERE stock_quantity >= @minimum_stock;
END;
~~~

SQL Server **@product_count BIGINT OUTPUT** là tham số OUT; nó **không phải result set** vì giá trị được gán cho output variable.

### 7.1. Đăng ký và gọi

~~~java
StoredProcedureQuery query =
    em.createStoredProcedureQuery(
        "dbo.count_products_above_stock");

query.registerStoredProcedureParameter(
    1, Integer.class, ParameterMode.IN);

query.registerStoredProcedureParameter(
    2, Long.class, ParameterMode.OUT);

query.setParameter(1, 10);

query.execute();

Long count =
    (Long) query.getOutputParameterValue(2);
~~~

Ví dụ giả định driver/provider hỗ trợ procedure OUT theo vị trí và trả Long tương ứng BIGINT. Đừng ép count thành Integer chỉ vì dataset hiện có ít Product.

### 7.2. Đọc OUT sau execute

Không gọi:

~~~java
query.getOutputParameterValue(2);
~~~

trước khi thực thi procedure rồi mong dữ liệu đã có. Cần execute hoặc một thao tác lấy kết quả khiến provider thực thi call trước.

Nếu procedure đồng thời trả nhiều result sets/update counts, các yêu cầu đọc OUT có thể cần **tiêu thụ các kết quả trước** theo provider/JPA semantics. Để portable hơn, quy trình thường là:
1. Thực thi;
2. Tiêu thụ các result sets/update counts cần thiết;
3. Đọc OUT;
4. Kết thúc transaction/context theo yêu cầu.

### 7.3. OUT NULL khác OUT = 0

Nếu routine thống kê có thể trả NULL, kết quả Java là null. Không tự unbox:

~~~java
long count = (Long) query.getOutputParameterValue(2);
~~~

nếu output có thể null; unboxing sẽ ném NullPointerException. Với COUNT_BIG trong ví dụ, procedure đã gán số đếm và thường trả 0 khi không có Product, nhưng các procedure nghiệp vụ khác có thể chủ động trả NULL để biểu diễn trạng thái không xác định.

### 7.4. OUT nhiều tham số

Một procedure có thể trả:
- numberOfRows;
- totalAmount;
- statusCode;
- statusMessage.

Mỗi output cần đăng ký đúng type/mode và đọc theo index/name được hỗ trợ. Tuy nhiên đừng biến output statusCode thành cơ chế thay thế transaction rollback nếu procedure đã làm các thay đổi không nhất quán. Phải xác định trường hợp nào báo lỗi bằng OUT và trường hợp nào thực sự ném SQL exception.

## 8. INOUT parameter: giá trị vào và giá trị mới

Ví dụ logic một procedure điều chỉnh hệ số:

~~~text
Procedure apply_bonus(
    IN customer_id,
    INOUT bonus_points
)

Input bonus_points = 100
Database áp logic và trả bonus_points = 125
~~~

Client Java:

~~~java
StoredProcedureQuery query =
    em.createStoredProcedureQuery("apply_bonus");

query.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN);

query.registerStoredProcedureParameter(
    2, Integer.class, ParameterMode.INOUT);

query.setParameter(1, 42L);
query.setParameter(2, 100);

query.execute();

Integer finalPoints =
    (Integer) query.getOutputParameterValue(2);
~~~

Đây là minh họa **signature giả định**, không phải DDL triển khai cụ thể cho PostgreSQL/SQL Server. Khi dùng thật, bạn phải khai báo routine ở DB tương ứng và chọn cú pháp tham số INOUT của DB đó.

### 8.1. Tránh nhầm INOUT với state của object Java

Gọi setParameter(2, initial) không làm biến **initial** trong Java trở thành tham chiếu mutable tới DB. Output là một giá trị mới phải nhận qua getOutputParameterValue.

### 8.2. Khi nào INOUT hợp lý?

Phù hợp khi database routine contract đã có biến vào-ra như:
- Balance trước/sau;
- Sequence/counter theo domain;
- State tính lại dựa trên input;
- Dữ liệu tích lũy.

Nếu chỉ cần đọc một tập kết quả nhiều row, output scalar không phải giải pháp thay result set. Dùng đúng kiểu return theo contract.

## 9. Trả result set và ánh xạ entity

Một procedure có thể thực thi SELECT và trả rows. Với SQL Server, ví dụ procedure sau trả toàn bộ cột cần để ánh xạ Product entity:

~~~sql
CREATE OR ALTER PROCEDURE dbo.list_products_by_stock
    @minimum_stock INT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        id,
        version,
        sku,
        name,
        stock_quantity
    FROM dbo.products
    WHERE stock_quantity >= @minimum_stock
    ORDER BY id;
END;
~~~

**Lưu ý:** đoạn này dành cho schema SQL Server có các cột tương đương, không phải DDL PostgreSQL bắt buộc. Product entity minh họa ở phần 2 có các field đó.

### 9.1. Tạo query với result class

~~~java
StoredProcedureQuery query =
    em.createStoredProcedureQuery(
        "dbo.list_products_by_stock",
        Product.class
    );

query.registerStoredProcedureParameter(
    1, Integer.class, ParameterMode.IN);

query.setParameter(1, 5);

@SuppressWarnings("unchecked")
List<Product> products =
    query.getResultList();
~~~

Trong một số provider, **getResultList()** sẽ thực thi stored procedure nếu chưa execute; để điều khiển nhiều kết quả rõ ràng, có thể gọi execute và xử lý result set đầu tiên theo API.

Result class Product yêu cầu result set có các cột cần cho mapping entity, bao gồm ID và những state được provider cần. Một SELECT chỉ trả **sku, name** không đủ để map thành Product entity đầy đủ.

### 9.2. Entity nhận từ result set có thể managed

Khi provider ánh xạ result set thành Product entities theo JPA, chúng có thể trở thành managed trong persistence context và dùng identity map. Điều này khác **DTO projection** chỉ tạo Java objects thường.

Tuy nhiên không vì procedure có kết quả Product mà kết luận:
- Mọi association đã được eager-fetch;
- Object luôn managed sau khi EntityManager đã đóng;
- Stored procedure chỉ đọc, không có side effects.

Cần xét transaction, mapping và vòng đời context.

### 9.3. Đừng dùng SELECT * với entity result mapping một cách tùy tiện

Provider có thể cần các alias/column names tương thích entity mapping. Nếu procedure trả cột tên khác, thiếu khóa chính, join ra nhiều cột cùng tên hoặc type khác, ánh xạ có thể lỗi.

Chọn cột tường minh và aliases phù hợp là cách làm dễ bảo trì hơn:

~~~sql
SELECT
    p.id,
    p.version,
    p.sku,
    p.name,
    p.stock_quantity
FROM dbo.products p
...
~~~

Khi entity thêm thuộc tính persistent mới, procedure result set dùng để map Product cũng có thể cần thay đổi. Đây là một lý do read-only report nên dùng DTO mapping nếu không cần managed entity.

### 9.4. Không nên sửa entity từ result set nếu procedure đang kiểm soát cùng dữ liệu theo cách riêng

Nếu procedure vừa update Product vừa trả Product rows, còn EntityManager đã có Product managed từ trước, identity map và state in-memory có thể dẫn đến dữ liệu chưa được refresh như caller mong đợi. Cần xác định rõ:
- Procedure chỉ đọc hay có ghi?
- Có Product instance đang managed trước CALL không?
- Có cần flush trước CALL và refresh/clear sau CALL không?

Phần transaction và stale state phía sau sẽ xử lý cụ thể.

## 10. Ánh xạ result set thành DTO bằng @SqlResultSetMapping

Trong một report, procedure có thể trả chỉ vài cột. Thay vì cố map thành Product entity, ta có thể khai báo **@SqlResultSetMapping** với **@ConstructorResult**.

Ví dụ DTO class:

~~~java
package com.example.inventory.dto;

public class ProductStockRow {
    private final String sku;
    private final String name;
    private final Integer stockQuantity;

    public ProductStockRow(
            String sku,
            String name,
            Integer stockQuantity) {
        this.sku = sku;
        this.name = name;
        this.stockQuantity = stockQuantity;
    }

    public String getSku() { return sku; }
    public String getName() { return name; }
    public Integer getStockQuantity() { return stockQuantity; }
}
~~~

Định nghĩa mapping trên một entity metadata class:

~~~java
@SqlResultSetMapping(
    name = "ProductStockRowMapping",
    classes = @ConstructorResult(
        targetClass = ProductStockRow.class,
        columns = {
            @ColumnResult(name = "sku", type = String.class),
            @ColumnResult(name = "name", type = String.class),
            @ColumnResult(
                name = "stock_quantity",
                type = Integer.class
            )
        }
    )
)
~~~

Các ColumnResult tương ứng tên/alias mà SQL procedure SELECT trả về. Constructor có **đúng ba tham số theo thứ tự** String, String, Integer.

### 10.1. SQL Server procedure trả cột cho DTO

~~~sql
CREATE OR ALTER PROCEDURE dbo.list_product_stock_rows
    @minimum_stock INT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        sku,
        name,
        stock_quantity
    FROM dbo.products
    WHERE stock_quantity >= @minimum_stock
    ORDER BY sku;
END;
~~~

### 10.2. Tạo query sử dụng mapping name

~~~java
StoredProcedureQuery query =
    em.createStoredProcedureQuery(
        "dbo.list_product_stock_rows",
        "ProductStockRowMapping"
    );

query.registerStoredProcedureParameter(
    1, Integer.class, ParameterMode.IN);

query.setParameter(1, 5);

@SuppressWarnings("unchecked")
List<ProductStockRow> rows = query.getResultList();
~~~

Lưu ý overload:
- **createStoredProcedureQuery(String procedureName, Class<?>... resultClasses)** nhận các class kết quả;
- **createStoredProcedureQuery(String procedureName, String... resultSetMappings)** nhận **tên mapping**, không phải tên DTO class.

Mapping phải được provider nhận diện trong persistence unit. Không dùng một tên tự nghĩ rồi mong provider tự tìm thấy DTO.

### 10.3. Khai báo named procedure với resultSetMappings

~~~java
@NamedStoredProcedureQuery(
    name = "Product.listStockRows",
    procedureName = "dbo.list_product_stock_rows",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "minimum_stock",
            type = Integer.class
        )
    },
    resultSetMappings = {
        "ProductStockRowMapping"
    }
)
~~~

Gọi:

~~~java
StoredProcedureQuery query =
    em.createNamedStoredProcedureQuery(
        "Product.listStockRows");

query.setParameter("minimum_stock", 5);

@SuppressWarnings("unchecked")
List<ProductStockRow> rows =
    query.getResultList();
~~~

Như với các ví dụ trước, khả năng bind **named SQL Server parameters** phụ thuộc provider/driver; nếu không hỗ trợ, dùng registration positional trong trực tiếp call hoặc cấu hình theo provider.

### 10.4. DTO khác entity mapping

**ProductStockRow** là đối tượng dữ liệu, không có persistence identity/dirty checking. Thay stockQuantity trong DTO (nếu mutable) **không cập nhật bảng products**.

DTO mapping phù hợp cho:
- Báo cáo;
- API read model;
- Procedure trả vài trường không đủ ánh xạ entity;
- Dashboard;
- Tích hợp với schema legacy.

### 10.5. ConstructorResult và phiên bản Java

Một Java record cũng có canonical constructor, và nhiều provider hiện đại có thể hỗ trợ constructor projection cho record. Nhưng khi ưu tiên khả năng tương thích rộng, một **public class với public constructor** như ví dụ là lựa chọn dễ hiểu. Bất kể class hay record, types của result columns và constructor phải khớp.

### 10.6. Multiple result mappings

Một stored procedure có thể trả nhiều result sets. JPA cho phép khai báo nhiều resultClasses/resultSetMappings theo khả năng API, nhưng **thứ tự result sets và cách provider áp mapping cần tuân theo contract cụ thể**. Nếu procedure trả shape thay đổi theo điều kiện, việc map có thể trở nên rất khó bảo trì; đôi khi nên tách thành hai thủ tục với các result set shapes ổn định.

## 11. Một procedure có nhiều result sets và update counts

Không phải thủ tục nào cũng chỉ có một SELECT. Một routine có thể:
1. UPDATE bảng;
2. INSERT bản ghi audit;
3. SELECT danh sách bị ảnh hưởng;
4. SELECT tổng hợp trạng thái.

Tùy DB/driver, caller có thể nhận:
- Một hoặc nhiều result sets;
- Update counts;
- Output parameters;
- Hoặc kết hợp các loại.

### 11.1. execute() trả boolean để nhận diện kết quả đầu tiên

~~~java
boolean isResultSet = query.execute();
~~~

Nếu true, kết quả đầu tiên được trình bày như một result set và có thể đọc:

~~~java
List<?> firstRows = query.getResultList();
~~~

Nếu false, có thể xem update count:

~~~java
int updated = query.getUpdateCount();
~~~

**getUpdateCount()** có thể trả -1 khi kết quả hiện tại không phải update count hoặc không còn update count theo API. Một số JDBC drivers có cơ chế ẩn update counts (ví dụ SQL Server SET NOCOUNT ON), nên không được dùng một update count chung như số bản ghi nghiệp vụ chắc chắn đã được cập nhật nếu procedure không cam kết điều ấy.

### 11.2. hasMoreResults() chuyển sang kết quả tiếp theo

Sơ đồ khái niệm:

~~~text
execute()
    |
    +-- result set? ------> getResultList()
    |                           |
    |                           v
    +-- update count? ----> getUpdateCount()
                                |
                                v
                         hasMoreResults()
                                |
                                +-- next result set?
                                +-- next update count?
                                +-- no more results
~~~

Trong thực tế, **hasMoreResults() trả true nếu kết quả tiếp theo là result set**, không đơn giản có nghĩa "còn bất kỳ loại kết quả nào". Vì vậy khi false, cần kiểm tra getUpdateCount() để phân biệt một update count tiếp theo với hết kết quả.

### 11.3. Mẫu vòng lặp xử lý các kết quả

~~~java
boolean resultSet = query.execute();

while (true) {
    if (resultSet) {
        List<?> rows = query.getResultList();
        handleRows(rows);
    } else {
        int count = query.getUpdateCount();

        if (count == -1) {
            break;
        }

        handleUpdateCount(count);
    }

    resultSet = query.hasMoreResults();
}
~~~

Đây là một khung minh họa. **handleRows** và **handleUpdateCount** là các phương thức của ứng dụng cần định nghĩa, không phải API JPA. Với một số driver/provider, stored procedure và result set lifecycle cần xử lý riêng; nên kiểm thử theo DB mục tiêu, nhất là nếu OUT/ref cursor cùng xuất hiện.

### 11.4. Không dùng getSingleResult tùy tiện

Nếu procedure có thể trả nhiều hàng hoặc không có hàng:
- **getResultList()** phù hợp cho danh sách;
- **getSingleResult()** chỉ phù hợp khi thực sự kỳ vọng đúng một hàng.

Không mặc định “procedure trả output scalar” sẽ khiến getSingleResult trả scalar ấy. **OUT parameter phải được đọc bằng getOutputParameterValue**, không phải đọc result set trừ khi procedure thực sự SELECT ra giá trị đó.

### 11.5. Hạn chế phụ thuộc nhiều loại kết quả

Routine trả nhiều result sets/update counts/OUT có thể khó dùng portable hơn procedure:
- Một loại OUT scalar;
- Hoặc một result set có schema cố định;
- Hoặc không có result và chỉ thực hiện side effect.

Khi có quyền thiết kế interface mới, hãy ưu tiên contract đơn giản, versioned và có tài liệu rõ. Nếu tích hợp legacy nhiều results, xây adapter riêng tại DAO/repository layer và integration test đầy đủ.

## 12. REF_CURSOR và sự khác biệt giữa các database

Một số database hỗ trợ thủ tục hoặc function trả cursor. Cursor có thể được biểu diễn bằng parameter mode **REF_CURSOR** trong JPA, nhưng support cụ thể không đồng nhất.

### 12.1. Không đánh đồng cursor với SELECT result set

- Với SQL Server, procedure có thể trả một result set trực tiếp qua SELECT.
- Với Oracle, stored procedure có thể trả một SYS_REFCURSOR qua OUT parameter.
- Với PostgreSQL, procedure/function/cursor có quy tắc riêng, và JDBC driver có thể yêu cầu transaction hoặc những điều kiện đặc biệt khi fetch.

Không dùng REF_CURSOR chỉ vì procedure trả nhiều hàng: hãy xác định **interface database routine**.

### 12.2. Hình dạng JPA cơ bản

~~~java
StoredProcedureQuery query =
    em.createStoredProcedureQuery("find_products_cursor");

query.registerStoredProcedureParameter(
    1, void.class, ParameterMode.REF_CURSOR
);

// Tiếp tục theo contract provider:
// execute, getResultList hoặc getOutputParameterValue.
~~~

Ví dụ là **mẫu API**, không phải lời gọi có thể chạy trên mọi DB. Một Oracle routine có cursor OUT parameter, một PostgreSQL function returning refcursor và một SQL Server SELECT result set cần các cách gọi khác nhau.

### 12.3. Kiểm tra transaction và việc đóng cursor

Cursor có thể yêu cầu transaction còn mở để fetch dữ liệu. Nếu trả iterator/cursor ra ngoài transaction Spring rồi mới duyệt, có thể gặp lỗi tài nguyên đã đóng hoặc lazy retrieval không còn hợp lệ.

Tổ chức service:
- Mở transaction/EntityManager phù hợp;
- Thực thi procedure;
- Đọc toàn bộ những row cần dùng hoặc stream theo lifecycle provider có kiểm soát;
- Đóng tài nguyên đúng cách;
- Trả DTO đã hoàn thành thay vì expose cursor thô ra controller.

### 12.4. Vì sao REF_CURSOR kém portable?

Các DB khác nhau về:
- Cách khai báo cursor parameter;
- Vị trí parameter và kiểu return;
- Cú pháp SQL procedure vs function;
- Yêu cầu transaction;
- JDBC metadata;
- Cách provider chuyển cursor thành List/ResultSet;
- Fetch size và lifetime.

Với một ứng dụng muốn hỗ trợ nhiều RDBMS, cần một abstraction riêng cho report và các implementation phù hợp với từng DB, thay vì kỳ vọng một registration REF_CURSOR chạy y hệt mọi nơi.

## 13. Transaction: stored procedure là một phần của đơn vị công việc

Một procedure UPDATE thường phải được gọi trong transaction phù hợp. Ví dụ Spring:

~~~java
@Service
public class InventoryService {
    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void adjustStock(long productId, int delta) {
        if (delta == 0) {
            throw new IllegalArgumentException(
                "delta không được bằng 0");
        }

        StoredProcedureQuery query =
            em.createNamedStoredProcedureQuery(
                "Product.adjustStock");

        query.setParameter("p_product_id", productId);
        query.setParameter("p_delta", delta);
        query.execute();
    }
}
~~~

Cần import:
- **org.springframework.stereotype.Service**;
- **org.springframework.transaction.annotation.Transactional**;
- **jakarta.persistence.PersistenceContext** và EntityManager.

Với transaction được Spring quản lý, method không tự gọi **em.getTransaction().begin()** hoặc commit nếu EntityManager gắn với transaction hiện tại. Spring xử lý boundary khi advice thực sự được áp dụng.

### 13.1. Procedure thành công chưa có nghĩa transaction commit

~~~text
@Transactional service
    |
    |-- CALL adjust_product_stock(...)
    |        UPDATE products
    |        INSERT stock_adjustments
    |
    |-- Java xử lý thêm nghiệp vụ
    |
    +-- commit thành công → dữ liệu được xác nhận
         hoặc
        rollback → các thay đổi trong transaction bị hủy
~~~

Nếu CALL chạy SQL thành công nhưng sau đó một validation khác làm transaction rollback, database không giữ các thay đổi chưa commit của transaction ấy.

### 13.2. Không tự COMMIT trong procedure khi muốn JPA quản lý transaction

Một số hệ quản trị cho phép transaction control bên trong một số loại procedure trong điều kiện cụ thể, nhưng việc này **không tương thích tùy ý với mọi JDBC/JPA transaction**. Với PostgreSQL chẳng hạn, transaction control bên trong procedure chịu những ràng buộc khi CALL nằm trong transaction block.

Nếu ứng dụng mong muốn một @Transactional service atomic, procedure nên tôn trọng transaction hiện tại và không tự kết thúc nó. Điều kiện này phải được thỏa thuận giữa người viết DB procedure và service Java.

### 13.3. Lỗi procedure và rollback

Ví dụ procedure điều chỉnh tồn kho ném exception nếu stock không đủ. Java thường nhận lỗi đã được JDBC/provider bọc lại, có thể là:
- **PersistenceException**;
- **RollbackException** tại commit;
- Spring **DataAccessException** hoặc wrapper khác;
- SQL exception vendor-specific được bọc bên trong.

Không bắt mọi lỗi rồi tiếp tục dùng transaction đã thất bại. Sau SQL error, transaction có thể bị đánh dấu rollback-only hoặc ở trạng thái không thể tiếp tục theo DB. Xử lý ở service boundary, rollback và trả lỗi nghiệp vụ thích hợp.

### 13.4. Ràng buộc database vẫn rất quan trọng

Ngay cả khi service validate delta, database vẫn cần:
- CHECK stock_quantity >= 0;
- FK của stock_adjustments.product_id;
- UNIQUE cho SKU;
- Quyền EXECUTE procedure;
- Transaction và locking thích hợp.

Các constraint bảo vệ khi nhiều app cùng gọi procedure hoặc có native SQL trực tiếp. Không dựa duy nhất vào Java validation để giữ toàn vẹn dữ liệu.

### 13.5. @Transactional self-invocation

Trong mô hình Spring proxy thông dụng, method @Transactional có thể không được advice nếu được gọi từ một method khác trên **chính cùng instance**. Vì vậy:

~~~java
public void runJob() {
    adjustStock(42L, -3); // Có thể là self-invocation.
}
~~~

không phải bằng chứng transaction annotation của adjustStock đã được áp dụng. Đảm bảo lời gọi đi qua Spring proxy, dùng bean riêng hoặc TransactionTemplate khi phù hợp.

## 14. Đồng bộ persistence context khi procedure thay đổi dữ liệu

Một điểm rất quan trọng của stored procedure: SQL bên trong procedure có thể **bỏ qua cơ chế dirty checking** của JPA đối với các managed entities đã tồn tại.

### 14.1. Object managed có thể stale

~~~java
Product product = em.find(Product.class, productId);
Integer before = product.getStockQuantity(); // 20

StoredProcedureQuery query =
    em.createNamedStoredProcedureQuery(
        "Product.adjustStock");

query.setParameter("p_product_id", productId);
query.setParameter("p_delta", -3);
query.execute();

// Procedure có thể đã ghi stock_quantity = 17 vào DB.
// product.getStockQuantity() không tự chắc chắn thành 17.
~~~

JPA không tự đọc lại mọi entity bị procedure tác động. Nếu vẫn dùng Product managed đã load trước CALL, object trong RAM có thể giữ 20 và version cũ.

### 14.2. Flush trước procedure nếu có pending changes liên quan

Giả sử code đã sửa Product managed nhưng chưa flush, sau đó procedure cũng UPDATE chính Product:

~~~java
Product managed = em.find(Product.class, id);
// managed đã được sửa qua domain method nào đó.

em.flush(); // Ghi các pending changes của context trước CALL.

callProcedure(id, -3);
~~~

**em.flush() tác động cả persistence context**, không chỉ Product hiện tại. Nó giúp DB nhìn thấy những thay đổi pending trong cùng transaction trước khi procedure chạy, nhưng cũng có thể phát SQL/constraint của entities khác.

Nếu không flush, một lần flush muộn của JPA có thể ghi trạng thái cũ đè lên thay đổi của procedure, hoặc gây optimistic lock conflict. Tùy provider/flush mode, một query có thể gây auto-flush, nhưng không nên dựa vào thứ tự tự động khi correctness phụ thuộc thứ tự rõ.

### 14.3. Refresh sau procedure nếu cần cùng managed instance

~~~java
Product product = em.find(Product.class, id);

// Chỉ minh họa thứ tự API trong transaction phù hợp.
em.flush();
callProcedure(id, -3);

em.refresh(product);

Integer updated = product.getStockQuantity();
Long updatedVersion = product.getVersion();
~~~

**em.refresh(product)** yêu cầu nạp lại state từ DB vào managed instance, phù hợp khi cần tiếp tục sử dụng đúng reference Product trong context hiện tại. Trước refresh phải cân nhắc pending modifications: refresh có thể thay thế state chưa flush của entity. Vì vậy sắp xếp thứ tự quan trọng.

### 14.4. Clear rồi find nếu muốn context mới

~~~java
em.flush();
callProcedure(id, -3);

em.clear();

Product reloaded = em.find(Product.class, id);
~~~

Sau clear:
- Mọi entity managed trong context đều detached;
- Reference Product cũ không còn được dirty checking;
- find nạp managed instance cho context sau clear.

Đừng đặt clear trong helper dùng chung mà không hiểu tác động tới những entities khác đang managed trong cùng transaction.

### 14.5. Procedure cập nhật nhiều bảng

Một routine chốt sổ có thể thay đổi Order, OrderLine, Account và LedgerEntry. Không thể chỉ refresh một Product rồi coi toàn context đã nhất quán. Chọn:
- Refresh có chủ đích các managed entities cần dùng;
- Clear context trước khi đọc lại;
- Hoặc tổ chức procedure call ở một boundary riêng với data flow DTO/IDs rõ ràng.

Không sử dụng đối tượng Java cũ sau CALL như nguồn sự thật tuyệt đối về dữ liệu vừa thay đổi.

### 14.6. Optimistic locking khi ghi trực tiếp từ procedure

Trong ví dụ SQL, procedure tăng **version** thủ công. Nếu JPA còn Product managed với version trước CALL và sau đó cố UPDATE, optimistic locking có thể phát hiện version mismatch.

Nhưng nếu procedure khác không cập nhật version, application có thể mất cơ chế phát hiện xung đột expected. Cần xác định contract rõ cho các đường ghi:
- ORM update;
- Bulk JPQL;
- Native SQL;
- Stored procedure;
- Trigger;
- Các ứng dụng khác dùng cùng DB.

Không có một annotation Java nào tự làm cho mọi external SQL update tuân theo version policy.

## 15. Spring Data JPA @Procedure

Spring Data JPA có annotation **@Procedure** để gọi stored procedure thông qua repository method. Đây là tính năng Spring Data, không phải phương thức của EntityManager JPA chuẩn.

Ví dụ:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Procedure(procedureName = "adjust_product_stock")
    void adjustStock(
        @Param("p_product_id") Long productId,
        @Param("p_delta") Integer delta
    );
}
~~~

Các import minh họa:
- **org.springframework.data.jpa.repository.JpaRepository**;
- **org.springframework.data.jpa.repository.query.Procedure**;
- **org.springframework.data.repository.query.Param**.

### 15.1. Gọi repository trong service transaction

~~~java
@Service
public class InventoryService {
    private final ProductRepository repository;

    public InventoryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void adjustStock(long id, int delta) {
        repository.adjustStock(id, delta);
    }
}
~~~

Lời gọi procedure vẫn chạy trong transaction phù hợp. Cần xử lý stale managed entities nếu service trước đó đã load Product rồi tiếp tục dùng sau CALL.

### 15.2. procedureName và name của @Procedure

Trong Spring Data JPA, các cách khai báo có ý nghĩa khác nhau:

~~~java
@Procedure(procedureName = "adjust_product_stock")
~~~

thường chỉ **tên procedure database**, còn:

~~~java
@Procedure(name = "Product.adjustStock")
~~~

thường tham chiếu **tên logical NamedStoredProcedureQuery** đã khai báo trong metadata JPA.

Cần kiểm tra phiên bản Spring Data JPA đang dùng và tên attribute annotation tương ứng, không đánh đồng cả hai với tên method Java.

### 15.3. OUT parameter qua repository

Với procedure có một OUT parameter, Spring Data JPA có thể ánh xạ nó thành return value của repository method theo configuration phù hợp. Với nhiều OUT parameters, một số mẫu hỗ trợ trả Map theo named stored procedure metadata; chi tiết phụ thuộc API/version.

Ví dụ ý tưởng:

~~~java
@Procedure(procedureName = "count_products_above_stock")
Long countProductsAboveStock(
    @Param("minimum_stock") Integer minimumStock
);
~~~

Ví dụ này **chỉ minh họa contract một OUT**; để chạy được, database signature và Spring Data mapping của OUT phải được khai báo phù hợp. Không suy từ signature Java rằng một procedure không có OUT nhưng SELECT result set sẽ tự trả Long.

### 15.4. Khi nào dùng repository, khi nào dùng EntityManager?

| Trường hợp | Lựa chọn thường hợp lý |
|---|---|
| Procedure đơn giản, vài tham số, 1 OUT | Spring Data @Procedure có thể ngắn gọn |
| Cần dùng JPA chuẩn không phụ thuộc Spring | EntityManager StoredProcedureQuery |
| Cần resultSets và mappings phức tạp | EntityManager/custom repository |
| Cần nhiều kết quả/update counts | Adapter StoredProcedureQuery chuyên biệt |
| Tích hợp legacy nhiều database dialect | Interface + implementation theo DB |
| Cần query/hợp đồng kiểm thử rõ | Dedicated DAO/service thay vì controller gọi thẳng |

**@Procedure không làm những khác biệt của database biến mất.** SQL Server/Oracle/PostgreSQL vẫn có quy tắc riêng về procedure outputs và cursor.

## 16. Database portability và procedure/function

Các mẫu SQL ở những phần trên dùng hai DB để minh họa rằng **không thể dùng chung một DDL procedure cho mọi hệ quản trị**.

### 16.1. PostgreSQL

- Hỗ trợ **CREATE PROCEDURE** và **CALL**.
- **CREATE FUNCTION** có mô hình return khác; function thường được gọi qua SELECT hoặc cơ chế JDBC/provider tương ứng.
- REF_CURSOR và transaction có quy tắc riêng.
- Thủ tục có transaction-control statements chịu ràng buộc về cách CALL và transaction context.
- Tên schema, identifier casing và OUT/INOUT semantics có thể khác các DB khác.

### 16.2. SQL Server

- Thường dùng **CREATE OR ALTER PROCEDURE**, các tham số **@name**;
- OUT tham số được khai báo với **OUTPUT**;
- SELECT trong procedure có thể trả result set;
- **SET NOCOUNT ON** ảnh hưởng cách update count messages được trình bày;
- JDBC driver có quy tắc riêng về stored procedure call và output retrieval.

### 16.3. Oracle

- Thường có stored procedures trong schema/packages;
- Có tham số IN, OUT, IN OUT;
- Có thể sử dụng SYS_REFCURSOR;
- Tên package.procedure và cách gọi có thể cần driver/provider configuration riêng;
- NUMBER/DATE/TIMESTAMP và JDBC Java types cần xác định rõ.

### 16.4. MySQL/MariaDB và các hệ khác

- Có syntax **CREATE PROCEDURE** và **CALL** riêng;
- Hỗ trợ OUT/INOUT tùy sản phẩm và phiên bản;
- Một số đặc điểm cursor/returned result sets khác PostgreSQL/Oracle;
- Driver có thể yêu cầu quyền metadata hoặc cấu hình đặc biệt để nhận diện tham số.

Bảng định hướng:

| Khía cạnh | Có thể dùng API JPA chung? | Vẫn cần kiểm tra DB/provider? |
|---|---|---|
| createStoredProcedureQuery | Có | Tên, khả năng routine |
| IN parameter registration | Có | Type và position/name |
| OUT/INOUT | Có | JDBC support, retrieval |
| REF_CURSOR | Có trong API | Rất cần |
| @NamedStoredProcedureQuery | Có | Procedure thực tồn tại |
| Result mapping entity | Có | Columns/types/alias |
| SQL procedure DDL | Không portable | Bắt buộc |
| Internal transaction control | Không portable | Bắt buộc |
| Error codes/SQLState | Không đồng nhất | Bắt buộc |
| Multiple result sets | API có hỗ trợ | Cần kiểm thử |

### 16.5. Stored procedure khác database function

Ví dụ PostgreSQL:

~~~sql
CREATE OR REPLACE FUNCTION multiply_two(
    a INTEGER,
    b INTEGER
)
RETURNS INTEGER
LANGUAGE sql
AS $$
    SELECT a * b;
$$;
~~~

Gọi bằng SQL:

~~~sql
SELECT multiply_two(3, 4);
~~~

Đây là **function trả scalar**, không phải procedure được tạo bằng CREATE PROCEDURE. Nếu dùng Java, có thể xét native query:

~~~java
Number result = (Number) em.createNativeQuery(
    "select multiply_two(?1, ?2)"
)
.setParameter(1, 3)
.setParameter(2, 4)
.getSingleResult();
~~~

Cách gọi function thông qua StoredProcedureQuery hoặc JDBC CallableStatement có thể có các extension/provider-specific patterns, nên không xem một function PostgreSQL là procedure tương đương để gọi bằng CALL.

## 17. Migration, versioning và kiểm soát contract

Vì procedure sống ở database, một dự án cần quản lý nó như source code được version.

### 17.1. Dùng migration

Ví dụ layout:

~~~text
src/main/resources/db/migration/
    V1__create_products.sql
    V2__create_stock_adjustments.sql
    V3__create_adjust_product_stock_procedure.sql
~~~

Tên file minh họa convention của Flyway. Nếu dùng Liquibase, tổ chức changesets phù hợp. Không trông chờ **hibernate.hbm2ddl.auto=update** tự cài đặt hoặc cập nhật PL/pgSQL/Transact-SQL cho procedure.

### 17.2. Kiểm soát tên schema

Nếu procedure nằm trong schema inventory:

~~~java
em.createStoredProcedureQuery(
    "inventory.adjust_product_stock"
);
~~~

Tên đầy đủ giúp tránh việc session default schema thay đổi làm gọi nhầm object cùng tên trong schema khác. Nhưng cách quote/case-sensitive identifiers và schema name cần khớp dialect.

### 17.3. Quyền EXECUTE tối thiểu

Database account của ứng dụng có thể được cấp quyền EXECUTE procedure thay vì quyền trực tiếp sửa mọi bảng, tùy security model. Song **procedure có thể chạy dưới quyền owner/definer** ở một số DB, nên phải rà soát quyền thực sự và tránh dynamic SQL injection trong code phía database.

JPA parameter binding giúp an toàn giá trị input ở client, **không bảo đảm stored procedure body không chứa dynamic SQL không an toàn**.

### 17.4. Thay đổi contract trong rolling deployment

Giả sử app phiên bản A gọi procedure hai tham số; app phiên bản B cần ba tham số. Nếu migration thay procedure mà không tương thích ngược, A có thể lỗi khi vẫn đang chạy.

Các chiến lược:
- Tạo procedure mới **adjust_product_stock_v2**;
- Giữ old wrapper trong giai đoạn chuyển đổi;
- Thêm default parameter nếu DB cho phép và đã kiểm thử;
- Triển khai migration theo thứ tự tương thích;
- Kiểm thử cả old/new app với DB rollout plan.

### 17.5. Không dùng procedure name làm dữ liệu từ request

Nên có các service methods mang tên nghiệp vụ như **adjustStock**, **closePeriod**, **buildReport**. Không tạo một endpoint cho người dùng tùy ý chọn tên procedure và JSON parameters để gọi vào DB; điều này làm mất boundary về quyền và input validation.

## 18. Xử lý lỗi và resilience

Stored procedure có thể thất bại vì nhiều nguyên nhân:
- Tham số sai kiểu hoặc thiếu;
- Procedure không tồn tại hoặc sai schema;
- Thiếu quyền EXECUTE;
- Dữ liệu vi phạm FK, UNIQUE, CHECK;
- Deadlock hoặc lock timeout;
- Optimistic locking/version conflict;
- Lỗi nghiệp vụ được procedure chủ động raise;
- Driver/provider không hỗ trợ OUT/cursor;
- Procedure tự thực thi logic lâu gây timeout.

### 18.1. Không swallow exception rồi báo thành công

Sai:

~~~java
try {
    query.execute();
} catch (RuntimeException ignored) {
    // Trả HTTP 200?
}
~~~

Bỏ qua lỗi có thể che transaction đã rollback-only hoặc dữ liệu không được ghi. Với ghi dữ liệu, nên để transaction rollback và dịch lỗi ở boundary phù hợp:

~~~java
@Transactional
public void adjustStock(long productId, int delta) {
    try {
        callAdjustStock(productId, delta);
    } catch (PersistenceException ex) {
        // Có thể log mã lỗi/trace ID không nhạy cảm,
        // sau đó ném tiếp để transaction bị rollback.
        throw ex;
    }
}
~~~

Khi biết chính xác database error code biểu thị “không đủ tồn kho”, có thể dịch thành lỗi nghiệp vụ rõ ràng. Không dựa vào chuỗi error message tùy DB/language như một interface lâu dài nếu có thể dùng SQLSTATE/vendor code hoặc OUT status contract.

### 18.2. Timeout

Một stored procedure có thể chạy hàng phút. JPA query hints và JDBC statement timeout có hỗ trợ tùy provider/driver:

~~~java
query.setHint(
    "jakarta.persistence.query.timeout",
    5000
);
~~~

Giá trị timeout của JPA hint thường tính bằng millisecond. Tuy vậy, database/driver/provider có thể xử lý timeout khác nhau; kiểm tra hành vi thật, rollback và cleanup. Không mặc định một timeout sẽ hủy triệt để mọi công việc server-side ngay lập tức.

### 18.3. Idempotency và retry

Nếu procedure thực hiện điều chỉnh tồn kho **delta -3**, gọi lại hai lần sẽ trừ 6. Khi gặp timeout sau CALL nhưng trước response, client có thể không biết transaction đã commit hay chưa.

Để retry an toàn cần thiết kế nghiệp vụ:
- Request ID hoặc idempotency key;
- Unique constraint trên key trong DB;
- Procedure kiểm tra key và chỉ áp adjustment một lần;
- Lưu kết quả xử lý để trả lại khi request trùng;
- Transaction đảm bảo cùng lúc kiểm tra/ghi lịch sử/cập nhật stock.

Không tự retry mọi procedure chỉ vì lỗi là timeout hoặc deadlock, nhất là với thao tác có side effects không idempotent.

### 18.4. Giao dịch dài và lock contention

Một procedure update nhiều hàng có thể giữ locks đến commit. Đừng gọi nó trong một transaction còn chờ HTTP request tới hệ thống khác hoặc xử lý CPU không liên quan. Với batch jobs, xem xét chunking và checkpoint, nhưng nếu nghiệp vụ cần atomicity toàn phần thì không được chia transaction tùy tiện.

## 19. Hiệu năng: procedure không tự thay thế thiết kế truy vấn

### 19.1. Một CALL cho mỗi entity có thể tạo N round trips

Ví dụ:

~~~java
for (Long productId : ids) {
    callAdjustStock(productId, -1);
}
~~~

Một procedure call có thể nhanh hơn nhiều statement client-side cho **một product**, nhưng nếu gọi N lần cho N rows, vẫn có N round trips và overhead. Với batch rất lớn, cân nhắc procedure nhận tập IDs qua staging table/TVP/array tùy DB, hoặc xử lý set-based SQL trong một routine.

### 19.2. DB set-based SQL thường đáng ưu tiên

Thay vì lặp 10.000 UPDATE trong procedure, SQL có thể cập nhật nhiều rows theo điều kiện với một statement, nếu business rules cho phép. Dùng EXPLAIN/plan/statistics để quan sát:
- Index scans;
- Lock waits;
- Rows affected;
- Trigger cost;
- Transaction log I/O;
- Network round trips;
- Procedure plan cache/parameter sensitivity.

**Stored procedure không phải bảo đảm tự động nhanh hơn JPQL hoặc JDBC batch**; kết quả phải đo trong workload thật.

### 19.3. Tránh trả quá nhiều result rows

Một procedure SELECT trả một triệu Product entities có thể làm persistence context và heap tăng mạnh. Khi cần export lớn, cân nhắc paging/cursor/stream đúng lifecycle, DTO mapping, hoặc workflow DB riêng. Không đọc tất cả vào List nếu mục tiêu chỉ là streaming response.

### 19.4. Procedure trả entity có thể gây N+1

Nếu result set được map Product và code đọc **p.getCategory()** trên mỗi Product mà association LAZY, có thể phát N+1. Điều này không tự biến mất chỉ vì source là stored procedure. Nếu report cần categoryName, procedure có thể trả DTO có cột categoryName phù hợp.

### 19.5. Monitoring và tracing

Khi vận hành, nên theo dõi:
- Tên procedure (không log secrets);
- Thời gian gọi;
- Transaction ID/correlation ID nếu có;
- Số rows/result count phù hợp;
- Error code/SQLSTATE;
- DB load và lock waits;
- Retry count;
- Thống kê call thành công/không thành công.

Không log toàn bộ tham số nếu chúng có dữ liệu cá nhân, token hoặc thông tin tài chính nhạy cảm.

## 20. Kiểm thử tích hợp thủ tục

**Unit test** mock EntityManager có thể xác minh code gọi register/setParameter, nhưng **không chứng minh procedure thực sự tồn tại hoặc trả kết quả đúng**. Kiểm thử tích hợp phải chạy với database thật hoặc môi trường có khả năng tương thích đủ cao.

### 20.1. Chuẩn bị test database

Ví dụ PostgreSQL:
1. Chạy migration tạo products/stock_adjustments.
2. Chạy migration tạo procedure adjust_product_stock.
3. Thêm Product có stockQuantity=20.
4. Gọi qua EntityManager trong transaction.
5. Kiểm tra products và stock_adjustments.
6. Rollback/cleanup cho mỗi test theo isolation phù hợp.

Nếu production dùng SQL Server cho OUT/results, test những phần đó trên SQL Server tương ứng; không dùng H2 thay thế rồi coi là đã xác minh cú pháp SQL Server.

### 20.2. Test thành công với IN parameters

Ví dụ pseudocode JUnit với resource-local EntityManager:

~~~java
@Test
void adjustmentUpdatesStockAndAudit() {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        Long productId = findTestProductId(em, "KB-001");

        StoredProcedureQuery query =
            em.createStoredProcedureQuery(
                "adjust_product_stock");

        query.registerStoredProcedureParameter(
            1, Long.class, ParameterMode.IN);

        query.registerStoredProcedureParameter(
            2, Integer.class, ParameterMode.IN);

        query.setParameter(1, productId);
        query.setParameter(2, -3);
        query.execute();

        em.clear();

        Product reloaded =
            em.find(Product.class, productId);

        assertEquals(
            Integer.valueOf(17),
            reloaded.getStockQuantity()
        );

        Long adjustments = em.createQuery(
            """
            select count(a)
            from StockAdjustment a
            where a.product.id = :productId
            """,
            Long.class
        )
        .setParameter("productId", productId)
        .getSingleResult();

        assertEquals(1L, adjustments);

        tx.commit();
    } finally {
        if (tx.isActive()) {
            tx.rollback();
        }
        em.close();
    }
}
~~~

Ví dụ giả định có entity **StockAdjustment** mapping bảng stock_adjustments và helper **findTestProductId** cùng fixture sạch. Nếu chưa có entity StockAdjustment, dùng native SQL count phù hợp hoặc định nghĩa class đó trong project. Đây là test structure minh họa, không phải một class độc lập có thể compile khi thiếu helpers/imports.

### 20.3. Test lỗi không đủ tồn kho

Nếu tồn kho hiện là 2, gọi delta=-3 phải bị procedure từ chối:
- Transaction không được commit thành công;
- Product stock vẫn 2 sau rollback;
- Không có stock_adjustments mới từ call thất bại.

Dùng transaction mới để verify DB state. Không assert message lỗi cụ thể nếu message có thể thay đổi theo database/localization; ưu tiên error classification có chủ đích.

### 20.4. Test rollback sau CALL

Quy trình:
1. Begin transaction.
2. Gọi adjust_product_stock với delta hợp lệ.
3. Xác minh bên trong transaction nếu cần.
4. Rollback.
5. Mở EntityManager mới.
6. Verify Product stock và lịch sử không giữ thay đổi chưa commit.

Test này phân biệt **execute thành công** với **transaction commit thành công**.

### 20.5. Test stale managed Product

~~~java
Product before = em.find(Product.class, id);
Integer oldStock = before.getStockQuantity();

callAdjustStock(em, id, -1);

// Không giả định before đã tự đổi ngay trong Java.
em.refresh(before);

assertEquals(
    Integer.valueOf(oldStock - 1),
    before.getStockQuantity()
);
~~~

Ví dụ minh họa need for refresh. Khi test trên DB có @Version, kiểm tra version tăng phù hợp với procedure contract.

### 20.6. Test OUT parameter

Với SQL Server test container/database:
- Cài procedure count_products_above_stock;
- Đăng ký IN/OUT;
- Execute;
- Lấy output Long;
- So sánh số lượng DB theo dataset cố định;
- Test ngưỡng không khớp trả 0.

### 20.7. Test result set mapping

Cài procedure list_product_stock_rows:
- SELECT aliases sku, name, stock_quantity;
- Khai báo ProductStockRowMapping;
- Gọi procedure với minimum_stock;
- Assert DTO fields và loại Java;
- Test zero rows;
- Test thay đổi alias trong procedure được phát hiện bằng test thay vì fail ở production.

### 20.8. Test database-specific behavior

Nếu hệ thống dùng:
- Named parameter;
- OUT/INOUT;
- REF_CURSOR;
- Multiple result sets;
- Default NULL arguments;
- Schema-qualified routines;
- Statement timeout;
- Procedure trong transaction đang rollback;

thì mỗi khả năng phải được kiểm thử với **chính driver/provider/DB version mục tiêu**. Không mô phỏng qua unit test rồi suy ra tất cả hoạt động portable.

## 21. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Procedure not found | Sai procedureName/schema hoặc chưa migration | Kiểm tra DB catalog/schema và migration |
| Named procedure not found | Sai logical name của annotation | Dùng createNamedStoredProcedureQuery với đúng name |
| Gọi tên logic như tên DB | Nhầm name và procedureName | Phân biệt hai namespace |
| Sai vị trí parameter | Signature và register index không khớp | Đối chiếu DDL, thống nhất vị trí |
| Sai kiểu parameter | BIGINT/DECIMAL/JDBC type không tương thích | Chọn Long/BigDecimal/kiểu đúng |
| Driver không bind named parameter | Provider/DB không hỗ trợ tên | Thử positional registration theo contract |
| OUT luôn null | Chưa execute, sai mode/index, chưa consume results | Kiểm tra lifecycle và signature |
| getResultList không có dữ liệu | Routine chỉ có OUT hoặc UPDATE | Dùng getOutputParameterValue/getUpdateCount |
| execute trả false | First result không phải result set | Không coi false là lỗi |
| getSingleResult ném exception | Procedure trả 0 hoặc nhiều rows | Dùng getResultList hoặc sửa contract |
| Map Product báo thiếu column | Result set không đủ mapped entity fields | SELECT đủ columns hoặc dùng DTO |
| DTO constructor mismatch | Sai order/type @ColumnResult | Đồng bộ SQL aliases và constructor |
| REF_CURSOR không hoạt động | Driver/provider/DB routine khác contract | Theo docs dialect và integration test |
| Function bị gọi như procedure | CREATE FUNCTION khác CREATE PROCEDURE | Chọn native SELECT hoặc API phù hợp |
| Query báo permission denied | Thiếu EXECUTE | Cấp quyền tối thiểu đúng schema |
| SQL update xong Product vẫn cũ | Entity managed stale | flush trước, refresh/clear sau |
| Optimistic lock conflict | Procedure tăng version, managed instance cũ | Refresh hoặc transaction flow mới |
| Không phát hiện concurrent update | Procedure không tôn trọng version | Thiết kế external-write version policy |
| CALL chạy nhưng transaction rollback | execute không phải commit | Xử lý tại transaction boundary |
| Bắt exception rồi tiếp tục | Transaction đã rollback-only | Rollback và dùng transaction mới |
| Timeout lặp khiến trừ tồn kho nhiều lần | Retry không idempotent | Request ID/idempotency key |
| Procedure SQL chạy trên DB khác lỗi | DDL/call syntax khác hệ quản trị | Dùng migrations/implementations theo DB |
| Result set nhiều lần đọc sai | Multiple results/update counts | Xử lý execute/hasMoreResults/getUpdateCount |
| Test chạy H2 nhưng production lỗi | Dialect/driver khác | Integration test DB cùng loại |
| Procedure thay đổi không đồng bộ app | Signature migration không tương thích | Versioning và rollout plan |
| Lộ quyền gọi procedure bất kỳ | Client chọn tên procedure | Chỉ expose business methods whitelist |
| Performance không cải thiện | N calls/N round trips, locks, query plan | Tối ưu set-based SQL và đo thực tế |

## 22. Bài tập thực hành

Các bài tập tập trung vào **khai báo và tạo StoredProcedureQuery**, cách đăng ký tham số, ánh xạ output và transaction. Nếu đề dùng SQL Server, không chạy nguyên SQL đó trên PostgreSQL.

### Bài 1. Tạo procedure query trực tiếp

Với PostgreSQL procedure:

~~~sql
adjust_product_stock(IN p_product_id BIGINT, IN p_delta INTEGER)
~~~

Viết method Java:
- createStoredProcedureQuery;
- register hai IN parameters theo vị trí;
- setParameter với productId=42, delta=-3;
- execute.

Giải thích vì sao **execute() == false** vẫn có thể là thành công.

### Bài 2. Đăng ký theo tên

Viết lại bài 1 bằng registration theo tên **p_product_id** và **p_delta**. Khi chuyển driver/database, cần kiểm tra điều kiện hỗ trợ nào?

### Bài 3. Đặt annotation named query

Khai báo @NamedStoredProcedureQuery có:
- name = Product.adjustStock;
- procedureName = adjust_product_stock;
- hai StoredProcedureParameter IN.

Sau đó dùng EntityManager.createNamedStoredProcedureQuery. Tại sao không tạo bằng **createStoredProcedureQuery("Product.adjustStock")**?

### Bài 4. Đặt tên sai

Một developer viết:

~~~java
em.createNamedStoredProcedureQuery(
    "adjust_product_stock"
);
~~~

trong khi annotation có **name="Product.adjustStock"**. Hãy phân tích lỗi và sửa call. Nếu không có annotation nào, dùng API nào để gọi procedure theo DB name?

### Bài 5. Chế độ OUT

SQL Server procedure:

~~~sql
dbo.count_products_above_stock(
    @minimum_stock INT,
    @product_count BIGINT OUTPUT
)
~~~

Viết Java register IN ở vị trí 1, OUT ở vị trí 2, execute rồi lấy Long output. Không dùng getSingleResult để đọc một OUT parameter.

### Bài 6. INOUT

Một procedure nhận tham số INOUT là bonus_points. Viết Java đăng ký ParameterMode.INOUT, setParameter giá trị ban đầu, execute và đọc giá trị cuối. Giải thích tại sao biến Integer ban đầu không tự được thay đổi.

### Bài 7. REF_CURSOR

Hãy mô tả:
- REF_CURSOR khác SELECT result set trực tiếp như thế nào?
- Vì sao không thể dùng cùng một ví dụ PostgreSQL cursor cho SQL Server mà không sửa?
- Transaction/cursor lifetime ảnh hưởng thế nào tới service?
- Những tài liệu provider/driver nào cần kiểm tra?

### Bài 8. Result class Product

Một procedure chỉ SELECT sku và name. Một developer gọi:

~~~java
em.createStoredProcedureQuery(
    "list_products",
    Product.class
);
~~~

Vì sao mapping thành Product có thể thất bại? Viết hai phương án: trả đủ mapped columns, hoặc dùng DTO resultSetMapping.

### Bài 9. @SqlResultSetMapping DTO

Tạo ProductStockRow(String sku, String name, Integer stockQuantity) và @SqlResultSetMapping bằng ConstructorResult/ColumnResult. Viết createStoredProcedureQuery nhận mapping name.

### Bài 10. Lỗi constructor order

Procedure trả cột sku, stock_quantity, name. Mapping lại ghi cột sku, name, stock_quantity trong constructor có thứ tự khác. Hãy giải thích khi nào mismatch có thể gây lỗi runtime hoặc dữ liệu sai kiểu.

### Bài 11. Multiple results

Một procedure thực hiện UPDATE rồi SELECT các rows. Hãy giải thích ý nghĩa boolean của execute, getUpdateCount, getResultList và hasMoreResults. Vì sao hasMoreResults=false chưa chắc có nghĩa không có update count tiếp theo?

### Bài 12. Cập nhật bên ngoài persistence context

Trong một transaction:

~~~java
Product p = em.find(Product.class, id);
callAdjustStock(em, id, -2);
System.out.println(p.getStockQuantity());
~~~

Tại sao giá trị in ra có thể cũ? Viết lại bằng refresh hoặc clear + find và giải thích khác biệt phạm vi ảnh hưởng.

### Bài 13. Flush trước CALL

Service đã sửa nhiều managed entities nhưng chưa flush, sau đó procedure tính tổng hoặc update dựa trên dữ liệu ấy. Tại sao explicit flush trước CALL có thể quan trọng? Flush tác động riêng entity vừa sửa hay toàn persistence context?

### Bài 14. Optimistic locking

Product có @Version. Procedure update stockQuantity trực tiếp nhưng không thay version. Hãy phân tích nguy cơ lost update và đề xuất contract cập nhật version để tương thích với đường ghi JPA.

### Bài 15. Giao dịch atomic

Procedure điều chỉnh stock và thêm stock_adjustments trong cùng transaction. Sau CALL, service ném RuntimeException làm rollback. Kỳ vọng hai bảng có thay đổi nào được commit không? Tại sao execute thành công chưa đủ để xác nhận lưu dữ liệu?

### Bài 16. Retry idempotency

Client gửi yêu cầu delta=-3, gặp timeout rồi gửi lại. Nếu procedure được gọi hai lần, điều gì có thể xảy ra? Thiết kế idempotency key và UNIQUE constraint cho request ID để tránh điều chỉnh trùng.

### Bài 17. @Procedure trong Spring Data JPA

Khai báo repository method dùng @Procedure(procedureName="adjust_product_stock") và một phiên bản dùng @Procedure(name="Product.adjustStock"). Phân biệt trường hợp dùng DB name với logical JPA name.

### Bài 18. Procedure và function

Một PostgreSQL routine được định nghĩa bằng **CREATE FUNCTION calculate_discount** và trả numeric. Có nên mặc định gọi bằng CALL như stored procedure không? Viết native SQL SELECT function qua EntityManager.

### Bài 19. Test OUT parameter

Dùng SQL Server test database, tạo procedure đếm Product và kiểm tra output Long bằng giá trị mong đợi. Vì sao không thể chỉ mock query.getOutputParameterValue rồi kết luận DB signature đúng?

### Bài 20. Mapping result set

Lập integration test cho procedure trả ProductStockRow. Test danh sách rỗng, một row, nhiều rows, NULL nếu schema cho phép, aliases đúng và constructor mapping đúng.

### Bài 21. Phân biệt nhiều kiểu kết quả

Một procedure trả:
1. UPDATE count;
2. ResultSet danh sách Product;
3. OUT status_code.

Hãy thiết kế adapter DAO xử lý cả ba, xác định thứ tự đọc results và OUT theo provider, không expose StoredProcedureQuery trực tiếp lên controller.

### Bài 22. Quyền EXECUTE

Ứng dụng có database account chỉ được EXECUTE procedure, không có quyền UPDATE table trực tiếp. Hãy nêu lợi ích/hạn chế và rủi ro nếu procedure body dùng dynamic SQL từ input không escape đúng.

### Bài 23. Migration tương thích ngược

Phiên bản A của app gọi procedure hai tham số; phiên bản B cần tham số thứ ba. Hãy thiết kế rollout không làm phiên bản A đang chạy lỗi khi DB migration được triển khai trước.

### Bài 24. Tối ưu batch

Một job gọi stored procedure 20.000 lần để cộng một số vào từng Product. Đề xuất giải pháp set-based hoặc staging table tùy database, và cách đo round trips, SQL execution time, lock contention.

### Bài 25. Chẩn đoán một lỗi thực tế

Log:

~~~text
CALL inventory.adjust_stock product=42 delta=-3
execute(): false
service returned 500 "Procedure failed"
DB row was successfully updated in transaction
~~~

Giải thích tại sao code có thể hiểu sai boolean của execute. Trình bày cách phân biệt result type và exception thực sự, đồng thời nói rõ commit vẫn có thể rollback sau đó.

### Bài 26. Xây quy trình kiểm thử an toàn

Viết kế hoạch integration test gồm:
- Migration procedure;
- Product fixture;
- IN/OUT/result mapping;
- Vi phạm tồn kho;
- Rollback;
- Stale managed entity;
- Version tăng;
- Transaction timeout;
- Quyền EXECUTE;
- Retry idempotency;
- Driver/provider target.

Giải thích vì sao database in-memory không cùng dialect chưa đủ cho các phần REF_CURSOR và SQL Server OUT.

## 23. Bảng tra cứu nhanh

| Nhu cầu | JPA API / cấu hình |
|---|---|
| Tạo procedure call trực tiếp | em.createStoredProcedureQuery("db_procedure") |
| Tạo từ metadata logical name | em.createNamedStoredProcedureQuery("Product.adjustStock") |
| Khai báo tên logic và DB procedure | @NamedStoredProcedureQuery(name, procedureName, ...) |
| Khai báo tham số | @StoredProcedureParameter(mode, name, type) |
| Đăng ký IN theo vị trí | registerStoredProcedureParameter(1, Long.class, IN) |
| Đăng ký OUT theo vị trí | registerStoredProcedureParameter(2, Long.class, OUT) |
| Bind IN/INOUT | setParameter(index/name, value) |
| Thực thi | execute() |
| Đọc OUT | getOutputParameterValue(index/name) |
| Đọc result set | getResultList() |
| Đọc một result row | getSingleResult() khi contract đảm bảo |
| Đọc update count | getUpdateCount() |
| Sang kết quả tiếp theo | hasMoreResults() |
| Ánh xạ entity result | createStoredProcedureQuery(name, Product.class) |
| Ánh xạ DTO result | @SqlResultSetMapping + @ConstructorResult |
| Dùng tên mapping | createStoredProcedureQuery(name, "MappingName") |
| Named query result mapping | @NamedStoredProcedureQuery(resultSetMappings=...) |
| Cursor parameter | ParameterMode.REF_CURSOR (theo DB/provider) |
| Spring Data repository method | @Procedure(procedureName=...) hoặc @Procedure(name=...) |
| Đồng bộ state trước CALL | em.flush() nếu pending changes cần thấy ở DB |
| Đọc state mới sau CALL | em.refresh(managed) hoặc em.clear()+find |
| Commit/rollback | Transaction service/JPA boundary |
| Triển khai procedure SQL | Migration Flyway/Liquibase/script DB |

## 24. Checklist khi đưa StoredProcedureQuery vào dự án

1. **Routine là procedure hay function?** Chọn CALL/SELECT/API đúng loại.
2. **Procedure đã tồn tại trong database chưa?** Có migration, quyền EXECUTE?
3. **Tên schema/procedure có đúng không?** Có cần schema-qualified name?
4. **Có dùng tên logical của JPA hay tên DB?** Phân biệt createNamedStoredProcedureQuery và createStoredProcedureQuery.
5. **Signature được tài liệu hóa chưa?** Thứ tự/tên/kiểu/mode tham số.
6. **Có chọn registration theo tên hay vị trí nhất quán chưa?** Driver có hỗ trợ named binding không?
7. **IN có được setParameter đầy đủ không?** Có tham số nullable/default cần quy định rõ?
8. **OUT/INOUT được đăng ký đúng kiểu không?** Đọc sau execute/tiêu thụ results phù hợp?
9. **REF_CURSOR có đúng với routine và provider không?** Transaction/cursor lifecycle đã kiểm thử?
10. **Result set cần map entity hay DTO?** Entity mapping cần đủ columns/identity.
11. **@SqlResultSetMapping có đúng aliases/types/constructor order không?**
12. **Procedure có nhiều result sets/update counts không?** Có adapter xử lý đúng không?
13. **Có hiểu execute() trả boolean gì không?** false không phải lỗi.
14. **Transaction boundary có rõ không?** Procedure không tự COMMIT trái với nghiệp vụ.
15. **Có flush trước CALL khi cần không?** Pending changes trong persistence context có thể ảnh hưởng kết quả.
16. **Sau CALL, entity managed có stale không?** Refresh/clear/readback được bố trí hợp lý.
17. **@Version có được bảo toàn với external SQL update không?**
18. **Có đảm bảo atomicity của các bảng procedure cập nhật không?** Constraint và transaction?
19. **Exception có làm rollback đúng không?** Không nuốt lỗi rồi tiếp tục transaction hỏng.
20. **Timeout/retry có thể gọi hai lần không?** Có idempotency key nếu cần?
21. **Đã hạn chế người gọi chọn procedure name chưa?** Chỉ expose business operations được cho phép.
22. **Đã kiểm tra quyền database tối thiểu và dynamic SQL trong procedure chưa?**
23. **Có kế hoạch migration/rollback versioned contract không?** Tránh phá app đang chạy.
24. **Đã đo hiệu năng với số lượng calls/rows thực không?** CALL không tự tối ưu.
25. **Có integration tests trên DB/driver/provider tương ứng production không?**
26. **Có giám sát và correlation IDs không?** Không ghi lộ dữ liệu nhạy cảm.

## 25. Tóm tắt

**Khai báo và tạo truy vấn thủ tục trong JPA** có hai con đường chính:

~~~text
1. Tạo trực tiếp:
   em.createStoredProcedureQuery("db_procedure")
     → registerStoredProcedureParameter(...)
     → setParameter(...)
     → execute()
     → đọc output/result nếu có

2. Khai báo metadata:
   @NamedStoredProcedureQuery(
       name = "LogicalName",
       procedureName = "db_procedure",
       parameters = ...
   )

   em.createNamedStoredProcedureQuery("LogicalName")
     → setParameter(...)
     → execute()
     → đọc output/result nếu có
~~~

Nhớ phân biệt **IN / OUT / INOUT / REF_CURSOR**, **OUT parameter với result set**, **tên logic JPA với tên procedure ở database** và **execute thành công với transaction commit thành công**. Với procedure trả dữ liệu, chọn result mapping phù hợp: **entity class** khi cần JPA-managed entity và đủ mapped columns, hoặc **DTO qua @SqlResultSetMapping** khi chỉ cần read model.

Cuối cùng, stored procedure thường tác động trực tiếp tới database, nên **managed entity có thể stale sau CALL**. Hãy sắp xếp **flush trước, refresh hoặc clear sau** khi cần, bảo toàn transaction và optimistic locking, triển khai procedure qua migration, và kiểm thử đúng trên database/provider mục tiêu. Những nguyên tắc này giúp biến stored procedure từ một lời gọi SQL khó kiểm soát thành **một interface nghiệp vụ rõ ràng, có thể kiểm thử và vận hành tin cậy**.

