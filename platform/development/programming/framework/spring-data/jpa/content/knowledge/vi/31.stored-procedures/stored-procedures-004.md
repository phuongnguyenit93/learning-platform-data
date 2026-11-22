# Phân biệt IN, OUT, INOUT và REF_CURSOR theo khả năng hỗ trợ

Stored procedure có thể nhận dữ liệu đầu vào, trả giá trị đầu ra hoặc trả về một tập dòng. Khi gọi stored procedure từ JPA, bốn chế độ tham số thường gặp là **IN**, **OUT**, **INOUT** và **REF_CURSOR**.

- **IN** truyền giá trị từ ứng dụng vào procedure.
- **OUT** nhận một giá trị do procedure tính và trả về.
- **INOUT** vừa nhận giá trị ban đầu, vừa trả lại giá trị sau khi procedure xử lý.
- **REF_CURSOR** nhận một cursor do database mở để đọc một tập dòng kết quả.

Jakarta Persistence định nghĩa các chế độ này qua **ParameterMode**, nhưng không có nghĩa mọi database, JDBC driver và JPA provider đều hỗ trợ chúng giống nhau. Đặc biệt, REF_CURSOR phụ thuộc mạnh vào database và provider. Khi thiết kế, cần phân biệt API chuẩn của JPA với khả năng thực thi thực tế của tổ hợp database, dialect, driver và Hibernate đang dùng.

Bài này trình bày ý nghĩa từng mode, cách khai báo bằng EntityManager và Spring Data JPA, cách đọc output, mapping REF_CURSOR, khác biệt giữa các database phổ biến, transaction, persistence context và cách kiểm thử.

**Điều kiện của ví dụ:** các đoạn mã dùng Java 17 trở lên, Spring Boot 3.x, Jakarta Persistence và Spring Data JPA. Ứng dụng cần **spring-boot-starter-data-jpa**, JDBC driver, DataSource và stored procedure đã được tạo trong database. Ví dụ SQL MySQL và Oracle được đánh dấu riêng theo dialect; không thể chạy nguyên văn trên database khác.

## 1. Bốn chế độ tham số có ý nghĩa gì?

| Mode | Hướng dữ liệu | Ứng dụng làm gì? | Procedure làm gì? |
|---|---|---|---|
| **IN** | Ứng dụng → procedure | Gán giá trị trước khi execute | Đọc giá trị đầu vào |
| **OUT** | Procedure → ứng dụng | Đăng ký kiểu và đọc sau execute | Gán giá trị đầu ra |
| **INOUT** | Hai chiều | Gán giá trị ban đầu, sau đó đọc lại | Đọc và cập nhật giá trị |
| **REF_CURSOR** | Database → ứng dụng, qua cursor | Đăng ký cursor và đọc result set | Mở cursor chứa nhiều dòng |

Có thể hình dung:

~~~text
IN          Java value -----------------> Procedure
OUT         Java reads <----------------- Procedure value
INOUT       Java value -----------------> Procedure
            Java reads <----------------- Updated value
REF_CURSOR  Java reads rows <------------ Open database cursor
~~~

Ba mode IN, OUT và INOUT thường dùng cho scalar như số, chuỗi, ngày giờ hoặc decimal. REF_CURSOR dùng để trả về một tập kết quả dạng bảng, thường có nhiều dòng và nhiều cột.

## 2. ParameterMode trong Jakarta Persistence

Jakarta Persistence cung cấp enum **jakarta.persistence.ParameterMode**:

~~~java
public enum ParameterMode {
    IN,
    INOUT,
    OUT,
    REF_CURSOR
}
~~~

Khi làm việc với **StoredProcedureQuery**, phải đăng ký tham số trước khi gán giá trị hoặc thực thi:

~~~java
StoredProcedureQuery query =
    entityManager.createStoredProcedureQuery("procedure_name");

query.registerStoredProcedureParameter(
    1,
    Integer.class,
    ParameterMode.IN
);
~~~

Có thể đăng ký tham số theo vị trí hoặc theo tên:

~~~java
query.registerStoredProcedureParameter(
    "p_amount",
    BigDecimal.class,
    ParameterMode.IN
);
~~~

Tên hoặc vị trí phải khớp với chữ ký procedure theo cách database/provider nhận diện tham số. Với positional parameter, thứ tự phải đúng với khai báo procedure. Với named parameter, cần chú ý quy tắc tên và chữ hoa/thường của database.

Không đăng ký cùng một tham số hai lần. Tất cả tham số phải được đăng ký trước khi gọi **execute()**.

## 3. IN: truyền dữ liệu vào procedure

IN là mode đơn giản nhất. Ứng dụng truyền một giá trị để procedure dùng trong xử lý.

Ví dụ stored procedure theo cú pháp MySQL:

~~~sql
CREATE PROCEDURE find_products_by_status(
    IN p_status VARCHAR(30)
)
BEGIN
    SELECT id, name, status, price
    FROM products
    WHERE status = p_status;
END;
~~~

Gọi bằng EntityManager:

~~~java
StoredProcedureQuery query =
    entityManager.createStoredProcedureQuery(
        "find_products_by_status",
        Product.class
    );

query.registerStoredProcedureParameter(
    "p_status",
    String.class,
    ParameterMode.IN
);

query.setParameter("p_status", "ACTIVE");

List<Product> products = query.getResultList();
~~~

Trong ví dụ:

- p_status được đăng ký là IN.
- setParameter gán giá trị trước khi thực thi.
- procedure sử dụng giá trị đó trong điều kiện WHERE.
- result set được ánh xạ thành Product.

Khi ánh xạ về entity, SELECT phải trả về đủ cột cần thiết theo mapping Product. Nếu procedure chỉ trả về một phần dữ liệu, hãy dùng DTO/scalar mapping thay vì giả định có thể dựng entity đầy đủ.

## 4. OUT: nhận một giá trị từ procedure

OUT là tham số chỉ trả dữ liệu từ procedure về ứng dụng. Ứng dụng đăng ký kiểu tham số, không gán giá trị đầu vào cho nó, sau đó đọc bằng **getOutputParameterValue()** sau khi procedure thực thi.

Ví dụ MySQL:

~~~sql
CREATE PROCEDURE calculate_discount(
    IN p_amount DECIMAL(12,2),
    OUT p_discount DECIMAL(12,2)
)
BEGIN
    SET p_discount = ROUND(p_amount * 0.10, 2);
END;
~~~

Gọi bằng EntityManager:

~~~java
StoredProcedureQuery query =
    entityManager.createStoredProcedureQuery("calculate_discount");

query.registerStoredProcedureParameter(
    "p_amount",
    BigDecimal.class,
    ParameterMode.IN
);

query.registerStoredProcedureParameter(
    "p_discount",
    BigDecimal.class,
    ParameterMode.OUT
);

query.setParameter("p_amount", new BigDecimal("500000.00"));

query.execute();

BigDecimal discount = (BigDecimal)
    query.getOutputParameterValue("p_discount");
~~~

Nếu đầu vào là 500000.00 và procedure tính 10%, giá trị output theo ví dụ là 50000.00. Kết quả thực tế phụ thuộc precision, scale và quy tắc làm tròn của database.

Không gọi getOutputParameterValue trước khi execute. Giá trị OUT chỉ có ý nghĩa sau khi procedure đã thực thi thành công và driver/provider đã lấy được output.

## 5. INOUT: vừa truyền vào vừa nhận giá trị cập nhật

INOUT kết hợp hai chiều:

1. Ứng dụng gán giá trị ban đầu.
2. Procedure đọc giá trị đó.
3. Procedure thay đổi giá trị.
4. Ứng dụng đọc lại giá trị sau khi execute.

Ví dụ MySQL:

~~~sql
CREATE PROCEDURE add_tax(
    IN p_amount DECIMAL(12,2),
    INOUT p_tax DECIMAL(12,2)
)
BEGIN
    SET p_tax = p_tax + ROUND(p_amount * 0.05, 2);
END;
~~~

Gọi bằng EntityManager:

~~~java
StoredProcedureQuery query =
    entityManager.createStoredProcedureQuery("add_tax");

query.registerStoredProcedureParameter(
    "p_amount",
    BigDecimal.class,
    ParameterMode.IN
);

query.registerStoredProcedureParameter(
    "p_tax",
    BigDecimal.class,
    ParameterMode.INOUT
);

query.setParameter("p_amount", new BigDecimal("100000.00"));
query.setParameter("p_tax", new BigDecimal("2000.00"));

query.execute();

BigDecimal updatedTax = (BigDecimal)
    query.getOutputParameterValue("p_tax");
~~~

Theo logic procedure, p_tax ban đầu là 2000.00, phần tăng thêm là 5000.00, nên output là 7000.00.

Khác biệt giữa OUT và INOUT:

| OUT | INOUT |
|---|---|
| Không cần giá trị đầu vào | Phải có giá trị ban đầu |
| Procedure tạo giá trị đầu ra | Procedure xử lý giá trị được truyền vào |
| Ứng dụng chỉ đọc sau execute | Ứng dụng gán trước và đọc lại sau execute |

## 6. Kết hợp IN, OUT và INOUT trong một procedure

Một procedure có thể khai báo nhiều mode cùng lúc. Ví dụ calculate_price nhận giá tiền, trả discount và cập nhật tax:

~~~sql
CREATE PROCEDURE calculate_price(
    IN p_amount DECIMAL(12,2),
    OUT p_discount DECIMAL(12,2),
    INOUT p_tax DECIMAL(12,2)
)
BEGIN
    SET p_discount = ROUND(p_amount * 0.10, 2);
    SET p_tax = p_tax + ROUND(p_amount * 0.05, 2);
END;
~~~

Gọi:

~~~java
StoredProcedureQuery query =
    entityManager.createStoredProcedureQuery("calculate_price");

query.registerStoredProcedureParameter(
    "p_amount", BigDecimal.class, ParameterMode.IN);
query.registerStoredProcedureParameter(
    "p_discount", BigDecimal.class, ParameterMode.OUT);
query.registerStoredProcedureParameter(
    "p_tax", BigDecimal.class, ParameterMode.INOUT);

query.setParameter("p_amount", new BigDecimal("500000.00"));
query.setParameter("p_tax", new BigDecimal("10000.00"));

query.execute();

BigDecimal discount = (BigDecimal)
    query.getOutputParameterValue("p_discount");

BigDecimal tax = (BigDecimal)
    query.getOutputParameterValue("p_tax");
~~~

Với dữ liệu trên, discount là 50000.00 và tax mới là 35000.00. Đây là kết quả theo công thức của procedure minh họa.

Trong ứng dụng thực tế, có thể gom logic gọi procedure vào service để controller không phải biết chi tiết thứ tự tham số hoặc kiểu JDBC.

## 7. Gọi procedure qua Spring Data JPA @Procedure

Spring Data JPA cung cấp annotation **@Procedure** trên repository method.

Ví dụ procedure chỉ có một output scalar:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Procedure(
        procedureName = "calculate_discount",
        outputParameterName = "p_discount"
    )
    BigDecimal calculateDiscount(
        @Param("p_amount") BigDecimal amount
    );
}
~~~

**procedureName** là tên procedure trong database. **outputParameterName** xác định tham số OUT được dùng làm giá trị trả về của method.

Có thể khai báo metadata bằng **@NamedStoredProcedureQuery** trên entity rồi tham chiếu bằng tên JPA:

~~~java
@Entity
@Table(name = "products")
@NamedStoredProcedureQuery(
    name = "Product.calculateDiscount",
    procedureName = "calculate_discount",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_amount",
            type = BigDecimal.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_discount",
            type = BigDecimal.class
        )
    }
)
public class Product {
    // Entity mapping
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Procedure(name = "Product.calculateDiscount")
    BigDecimal calculateDiscount(
        @Param("p_amount") BigDecimal amount
    );
}
~~~

Cần phân biệt:

- **procedureName**: tên procedure vật lý trong database.
- **name**: tên named stored procedure query được khai báo trong JPA metadata.
- **value**: alias của thuộc tính procedureName trong annotation @Procedure.

Nếu method có một output scalar, có thể dùng kiểu trả về tương ứng. Với nhiều output parameters, Spring Data JPA hỗ trợ trả về **Map<String, Object>** trong các trường hợp khai báo phù hợp bằng named stored procedure metadata. Key của map gắn với tên output parameter theo mapping của framework/provider.

Đối với INOUT, REF_CURSOR hoặc procedure trả đồng thời nhiều result set và output parameters, nên kiểm tra cách Spring Data JPA và provider của phiên bản đang dùng xử lý kết quả. Nếu cần điều khiển chi tiết, EntityManager StoredProcedureQuery thường rõ ràng hơn.

## 8. Đọc nhiều output parameters bằng Map

Giả sử entity khai báo metadata cho calculate_price:

~~~java
@NamedStoredProcedureQuery(
    name = "Product.calculatePrice",
    procedureName = "calculate_price",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_amount",
            type = BigDecimal.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_discount",
            type = BigDecimal.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.INOUT,
            name = "p_tax",
            type = BigDecimal.class
        )
    }
)
~~~

Repository có thể khai báo method trả Map:

~~~java
@Procedure(name = "Product.calculatePrice")
Map<String, Object> calculatePrice(
    @Param("p_amount") BigDecimal amount,
    @Param("p_tax") BigDecimal initialTax
);
~~~

Gọi:

~~~java
Map<String, Object> outputs =
    productRepository.calculatePrice(
        new BigDecimal("500000.00"),
        new BigDecimal("10000.00")
    );

BigDecimal discount =
    (BigDecimal) outputs.get("p_discount");

BigDecimal updatedTax =
    (BigDecimal) outputs.get("p_tax");
~~~

Map giúp nhận nhiều output trong một lần gọi. Tên key phụ thuộc metadata parameter name và cách provider/framework trả kết quả; hãy xác nhận bằng integration test trên database thực tế. Không giả định Map chứa tất cả result set hoặc mọi loại output nếu procedure có cấu trúc phức tạp.

## 9. REF_CURSOR là gì?

REF_CURSOR là tham số đại diện cho một cursor do database mở. Cursor trỏ tới một tập dòng kết quả mà ứng dụng có thể đọc sau khi procedure thực thi.

Khác với OUT scalar:

- OUT thường trả về một giá trị như BigDecimal hoặc String.
- REF_CURSOR trả về nhiều hàng và nhiều cột.
- Ứng dụng cần đọc result set và ánh xạ từng hàng thành entity, DTO hoặc scalar.

Một số hệ quản trị dùng cursor output riêng, ví dụ **SYS_REFCURSOR** của Oracle. PostgreSQL có kiểu refcursor với vòng đời cursor gắn với transaction. Các database khác có thể trả result set trực tiếp từ procedure mà không dùng REF_CURSOR theo cùng semantics.

REF_CURSOR có trong **ParameterMode** của Jakarta Persistence, nhưng khả năng thực thi vẫn phụ thuộc provider, dialect, JDBC driver và database. Không thể suy ra rằng một procedure dùng REF_CURSOR trên Oracle sẽ chạy nguyên trạng trên MySQL hoặc SQL Server.

## 10. Ví dụ Oracle REF_CURSOR với EntityManager

Ví dụ procedure Oracle mở SYS_REFCURSOR:

~~~sql
CREATE OR REPLACE PROCEDURE find_products (
    p_status IN VARCHAR2,
    p_result OUT SYS_REFCURSOR
)
AS
BEGIN
    OPEN p_result FOR
        SELECT id, name, status, price
        FROM products
        WHERE status = p_status;
END;
/
~~~

Gọi bằng Jakarta Persistence và Hibernate:

~~~java
@Transactional(readOnly = true)
public List<Product> findProductsByStatus(String status) {
    StoredProcedureQuery query =
        entityManager.createStoredProcedureQuery(
            "find_products",
            Product.class
        );

    query.registerStoredProcedureParameter(
        1,
        String.class,
        ParameterMode.IN
    );

    query.registerStoredProcedureParameter(
        2,
        Class.class,
        ParameterMode.REF_CURSOR
    );

    query.setParameter(1, status);
    query.execute();

    @SuppressWarnings("unchecked")
    List<Product> products = query.getResultList();

    return products;
}
~~~

Trong ví dụ:

- Tham số 1 là p_status, mode IN.
- Tham số 2 là cursor output, mode REF_CURSOR.
- Product.class yêu cầu provider ánh xạ các dòng cursor thành entity Product.
- SQL trong procedure phải trả đủ cột theo mapping Product.

Đây là ví dụ theo khả năng hỗ trợ REF_CURSOR của Hibernate và Oracle JDBC. Kiểu tham số cursor, thứ tự đăng ký và cách lấy result set cần được kiểm tra theo phiên bản Hibernate, dialect và driver. Một số tổ hợp có khác biệt trong cách đăng ký hoặc lấy cursor; không coi đoạn mã là bảo đảm portable cho mọi JPA provider.

## 11. REF_CURSOR và transaction

Một cursor có thể phụ thuộc transaction để giữ tài nguyên database mở trong khi ứng dụng đọc kết quả.

Với PostgreSQL, refcursor thường là tên cursor được mở trong transaction; cursor không còn dùng được sau khi transaction kết thúc. Vì vậy, cần đọc result set trong transaction phù hợp và không trả cursor/handle ra ngoài service để controller dùng sau đó.

Một nguyên tắc an toàn:

1. Bắt đầu transaction.
2. Gọi procedure và nhận cursor.
3. Đọc hết dữ liệu cần thiết.
4. Chuyển kết quả thành DTO nếu cần.
5. Kết thúc transaction sau khi đã đọc xong.

Không mở cursor trong một transaction rồi đóng transaction ngay trước khi serializer hoặc client đọc cursor. Nếu cần phân trang qua một tập dữ liệu lớn, hãy xem xét thiết kế query/pagination riêng thay vì giữ cursor lâu qua nhiều request HTTP.

## 12. Ánh xạ REF_CURSOR thành DTO hoặc scalar

Nếu cursor trả về các cột không tương ứng đầy đủ với entity, dùng result-set mapping hoặc DTO.

Ví dụ DTO:

~~~java
public record ProductRow(
    Long id,
    String name,
    BigDecimal price
) {
}
~~~

Có thể khai báo **@SqlResultSetMapping** với **@ConstructorResult** rồi tạo StoredProcedureQuery sử dụng tên mapping:

~~~java
StoredProcedureQuery query =
    entityManager.createStoredProcedureQuery(
        "find_product_rows",
        "ProductRowMapping"
    );
~~~

Sau đó đăng ký tham số IN và REF_CURSOR theo chữ ký procedure, set input, execute và lấy result list. Kiểu dữ liệu các cột và thứ tự constructor phải khớp mapping.

Nếu dùng entity result mapping, cursor phải trả về đầy đủ cột cần thiết theo entity mapping. Không ánh xạ một tập cột rút gọn thành entity đầy đủ chỉ vì result set có cùng ID.

## 13. Khả năng hỗ trợ theo database

Bảng dưới đây là định hướng thực tế, không phải ma trận bảo đảm cho mọi phiên bản:

| Database | IN | OUT | INOUT | REF_CURSOR |
|---|---|---|---|---|
| Oracle | Hỗ trợ phổ biến | Hỗ trợ phổ biến | Hỗ trợ | SYS_REFCURSOR được dùng rộng rãi; cần driver/provider tương thích |
| PostgreSQL | Hỗ trợ theo chữ ký procedure/function | Có hỗ trợ theo loại routine và phiên bản | Có hỗ trợ theo chữ ký | refcursor có transaction semantics riêng; kiểm tra Hibernate/driver |
| MySQL | Hỗ trợ | Hỗ trợ | Hỗ trợ | Thường trả result set bằng SELECT từ procedure; không đồng nhất với Oracle SYS_REFCURSOR |
| SQL Server | Hỗ trợ | Hỗ trợ qua OUTPUT parameter | Có thể dùng theo cú pháp routine | Thường trả result set qua SELECT; cursor parameter có semantics riêng của SQL Server |

Các điểm cần kiểm tra:

- Phiên bản database có hỗ trợ procedure và mode đang dùng không.
- JDBC driver có hỗ trợ CallableStatement và output parameter tương ứng không.
- Hibernate dialect có xử lý đúng parameter mode và cursor không.
- Provider có yêu cầu đăng ký REF_CURSOR bằng kiểu cụ thể không.
- Procedure trả result set, update count và OUT parameter theo thứ tự nào.
- Có cần transaction mở trong toàn bộ thời gian đọc cursor không.

Đối với database không có REF_CURSOR theo semantics mong muốn, có thể dùng result set trả trực tiếp, query riêng, temporary table hoặc một cơ chế database-specific khác. Chọn giải pháp theo khả năng thực tế thay vì cố ép mọi database vào cùng một procedure signature.

## 14. Xử lý nhiều result set và update count

Một stored procedure có thể trả nhiều result set hoặc update count trước khi trả output parameters. Khi đó, việc chỉ gọi **getResultList()** một lần có thể chưa đủ.

Jakarta Persistence cung cấp các API như:

- **execute()** để bắt đầu thực thi.
- **getResultList()** để đọc result set hiện tại.
- **hasMoreResults()** để kiểm tra result set tiếp theo.
- **getUpdateCount()** để lấy update count hiện tại.
- **getOutputParameterValue()** để đọc OUT/INOUT parameter.

Trình tự result set và update count phụ thuộc procedure, JDBC driver và provider. Với procedure có nhiều kết quả, hãy kiểm thử thứ tự thực tế. Không giả định mọi OUT parameter luôn đọc được trước khi tiêu thụ hết các result set nếu driver yêu cầu xử lý kết quả theo thứ tự.

## 15. Bulk procedure và persistence context

Stored procedure có thể cập nhật hoặc xóa dữ liệu trực tiếp trong database. Nếu procedure thay đổi hàng mà JPA đang quản lý, persistence context có thể giữ giá trị cũ.

Ví dụ:

1. Ứng dụng tải Product id 10 thành managed entity.
2. Stored procedure cập nhật price trong database.
3. Object Product trong persistence context vẫn giữ price cũ.
4. Code tiếp tục đọc object và thấy dữ liệu stale.

Trước khi gọi procedure, cân nhắc flush nếu procedure cần nhìn thấy các thay đổi JPA đang chờ. Sau procedure có ghi dữ liệu, cân nhắc refresh entity liên quan hoặc clear persistence context.

~~~java
@Transactional
public void recalculatePrice(Long productId) {
    entityManager.flush();

    StoredProcedureQuery query =
        entityManager.createStoredProcedureQuery("recalculate_price");

    query.registerStoredProcedureParameter(
        1, Long.class, ParameterMode.IN);
    query.setParameter(1, productId);
    query.execute();

    entityManager.clear();
}
~~~

**clear()** detach tất cả entity đang managed trong persistence context hiện tại. Chỉ dùng khi đã xử lý các thay đổi cần giữ và hiểu rằng các object đang được tham chiếu sẽ trở thành detached.

Procedure thực hiện DML trực tiếp không đi qua entity lifecycle thông thường. Vì vậy, không tự động gọi Spring Data JPA Auditing listener hoặc tạo revision Envers như khi thay đổi entity qua Hibernate. Nếu cần audit, hãy ghi audit metadata/history tường minh trong cùng transaction hoặc thiết kế cơ chế database-level phù hợp.

## 16. Transaction, lỗi và bảo mật

Gọi stored procedure thường nên nằm trong service method có transaction rõ ràng:

~~~java
@Service
public class ProductProcedureService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public BigDecimal calculateDiscount(BigDecimal amount) {
        StoredProcedureQuery query =
            entityManager.createStoredProcedureQuery("calculate_discount");

        query.registerStoredProcedureParameter(
            "p_amount", BigDecimal.class, ParameterMode.IN);
        query.registerStoredProcedureParameter(
            "p_discount", BigDecimal.class, ParameterMode.OUT);

        query.setParameter("p_amount", amount);
        query.execute();

        return (BigDecimal)
            query.getOutputParameterValue("p_discount");
    }
}
~~~

Cần chú ý:

- Quy tắc commit/rollback và khả năng procedure tự điều khiển transaction phụ thuộc database. Tránh để procedure tự commit nếu nó phải tham gia transaction do Spring quản lý.
- Bắt và chuyển đổi lỗi database ở service boundary; không trả raw SQL error cho client.
- Dùng parameter binding, không nối input vào tên hoặc nội dung SQL.
- Kiểm soát quyền EXECUTE trên procedure theo database user.
- Quản lý procedure bằng migration có version, ví dụ Flyway hoặc Liquibase.
- Kiểm tra timeout, lock, deadlock và execution plan như với truy vấn SQL khác.

Tên procedure, schema và identifier không thể bind như một giá trị parameter thông thường. Nếu cần chọn procedure theo input, dùng allowlist các tên hợp lệ thay vì ghép chuỗi tùy ý.

## 17. Kiểm thử từng mode trên database thật

Test với H2 có thể hữu ích cho các luồng JPA cơ bản, nhưng không chứng minh procedure hoặc REF_CURSOR tương thích với Oracle/PostgreSQL/MySQL/SQL Server. Cú pháp procedure, output binding, cursor và driver behavior cần được kiểm tra trên database đích.

Một bộ integration test nên bao gồm:

- IN nhận đúng giá trị và lọc đúng dữ liệu.
- OUT trả đúng kiểu, precision và scale.
- INOUT nhận giá trị ban đầu và trả giá trị đã cập nhật.
- REF_CURSOR trả đúng số dòng, cột và kiểu mapping.
- Procedure trả result set rỗng.
- Procedure báo lỗi hoặc vi phạm constraint.
- Transaction rollback không để lại thay đổi ngoài dự kiến.
- Procedure cập nhật dữ liệu mà entity managed không bị dùng với trạng thái stale.
- Nhiều output parameters hoặc nhiều result sets được đọc đúng thứ tự.

Có thể dùng Testcontainers với image database phù hợp để chạy integration test gần với production. Nếu môi trường CI không thể chạy database production, vẫn cần một test suite định kỳ trên đúng engine và driver được triển khai.

## 18. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Parameter index sai | Thứ tự đăng ký khác chữ ký procedure | Đối chiếu thứ tự tham số database |
| Không đọc được OUT | Chưa execute hoặc sai tên/position | Execute thành công rồi gọi getOutputParameterValue |
| INOUT trả giá trị cũ | Gán sai tham số hoặc procedure không cập nhật | Kiểm tra mode, input và logic procedure |
| REF_CURSOR không được hỗ trợ | Driver/provider/dialect không hỗ trợ tổ hợp đang dùng | Kiểm tra ma trận version và dùng API phù hợp |
| Cursor hết hiệu lực | Transaction kết thúc trước khi đọc xong | Đọc cursor trong transaction |
| Entity trả về thiếu field | Cursor result set không đủ cột entity | Dùng đầy đủ entity mapping hoặc DTO |
| Spring Data method không map nhiều output | Chữ ký return type/metadata không phù hợp | Dùng named stored procedure và Map hoặc EntityManager |
| Procedure chạy nhưng entity trong bộ nhớ cũ | DML trực tiếp bỏ qua đồng bộ persistence context | Flush trước, refresh/clear sau |
| Auditing/Envers không ghi lịch sử | Procedure sửa dữ liệu ngoài entity lifecycle | Ghi audit tường minh hoặc dùng DB audit |
| Chạy được trên dev nhưng lỗi production | Khác database, driver, dialect hoặc schema | Integration test trên engine production |
| Gọi nhầm function/procedure | Database phân biệt cách gọi routine | Kiểm tra routine type và cách gọi của dialect |

## 19. Checklist chọn và sử dụng ParameterMode

- [ ] Dùng **IN** khi chỉ truyền dữ liệu vào procedure.
- [ ] Dùng **OUT** khi procedure trả một scalar value.
- [ ] Dùng **INOUT** khi procedure cần giá trị ban đầu và trả lại giá trị đã xử lý.
- [ ] Dùng **REF_CURSOR** khi database/provider hỗ trợ cursor output và cần đọc nhiều dòng.
- [ ] Đăng ký mọi tham số trước execute.
- [ ] Khớp chính xác tên hoặc vị trí, kiểu dữ liệu và mode với procedure signature.
- [ ] Đọc OUT/INOUT sau khi execute thành công.
- [ ] Dùng EntityManager StoredProcedureQuery khi cần điều khiển chi tiết.
- [ ] Dùng Spring Data @Procedure cho các chữ ký đơn giản và đã được kiểm thử.
- [ ] Kiểm tra REF_CURSOR theo database, dialect, JDBC driver và transaction.
- [ ] Mapping cursor thành entity chỉ khi result set đủ cột; nếu không, dùng DTO.
- [ ] Flush/refresh/clear persistence context khi procedure thay đổi dữ liệu đang managed.
- [ ] Không giả định procedure DML tự kích hoạt Spring Data Auditing hoặc Envers.
- [ ] Viết integration test trên đúng database engine của production.

## 20. Kết luận

**IN** truyền dữ liệu vào; **OUT** trả dữ liệu ra; **INOUT** nhận giá trị ban đầu rồi trả lại giá trị đã xử lý; **REF_CURSOR** cung cấp tập dòng kết quả qua cursor. Jakarta Persistence định nghĩa các mode này bằng ParameterMode và cho phép đăng ký qua StoredProcedureQuery.

Khả năng hỗ trợ thực tế khác nhau giữa database, JDBC driver, Hibernate dialect và Spring Data JPA version. Đặc biệt, REF_CURSOR không phải một hợp đồng portable có thể chạy nguyên trạng trên mọi database. Hãy dùng @Procedure cho trường hợp đơn giản, EntityManager khi cần kiểm soát nhiều output/cursor, đọc cursor trong transaction, và kiểm thử trên đúng database sẽ triển khai.