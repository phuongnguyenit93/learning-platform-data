# Khai báo @Query bằng SQL của cơ sở dữ liệu

Trong **Spring Data Relational JDBC**, repository có thể suy ra truy vấn từ tên phương thức, nhưng có những trường hợp nghiệp vụ cần SQL cụ thể: join nhiều bảng để tạo dữ liệu đọc, dùng hàm riêng của hệ quản trị cơ sở dữ liệu, kiểm soát điều kiện lọc, sắp xếp, phân trang hoặc thực hiện một lệnh cập nhật có chủ đích. Annotation **`@Query`** cho phép khai báo câu SQL ngay trên repository method.

Khác với JPQL của JPA, SQL trong `@Query` của Spring Data JDBC làm việc với **tên bảng, tên cột và cú pháp SQL của database**. Spring Data JDBC chuẩn bị câu lệnh, bind tham số và ánh xạ kết quả theo kiểu trả về của method. Vì vậy, người viết phải hiểu schema, kiểu dữ liệu, cardinality của kết quả và giới hạn của mapping.

Bài học trình bày cách khai báo `@Query`, bind tham số an toàn, ánh xạ kết quả, dùng `@Modifying` cho câu lệnh thay đổi dữ liệu, phối hợp transaction, xử lý khác biệt giữa các database và kiểm thử SQL tùy chỉnh.

## 1. Khi nào cần @Query?

Spring Data JDBC hỗ trợ các derived query method được tạo từ tên method:

~~~java
Optional<Product> findBySku(String sku);

List<Product> findByStatusOrderByCreatedAtDesc(String status);
~~~

Với truy vấn đơn giản, derived query giúp code ngắn và dễ đọc. Tuy nhiên, tên method không phải lúc nào cũng diễn đạt tốt câu SQL cần chạy.

Các trường hợp thường dùng `@Query`:

- Cần join bảng để tạo một kết quả đọc.
- Cần hàm SQL hoặc toán tử đặc thù của database.
- Cần biểu thức tính toán, aggregate function hoặc subquery.
- Cần kiểm soát chính xác điều kiện `WHERE`, `ORDER BY`, `GROUP BY`.
- Cần dùng CTE hoặc cú pháp SQL nâng cao mà derived query không diễn đạt được.
- Cần một câu lệnh cập nhật/xóa cụ thể thông qua `@Modifying`.

Ví dụ, lấy sản phẩm theo SKU:

~~~java
@Query("""
       SELECT id, sku, name, price_minor_units
       FROM product
       WHERE sku = :sku
       """)
Optional<Product> findBySkuWithSql(@Param("sku") String sku);
~~~

Đây là SQL thật chạy trên database. `product` là tên bảng; `price_minor_units` là tên cột. Spring Data JDBC không chuyển `product` thành tên entity Java như JPQL.

## 2. Đúng annotation và package

Khi dùng Spring Data JDBC, import `@Query` từ package:

~~~java
import org.springframework.data.jdbc.repository.query.Query;
~~~

Với câu lệnh thay đổi dữ liệu, annotation tương ứng là:

~~~java
import org.springframework.data.jdbc.repository.query.Modifying;
~~~

Đừng nhầm với `@Query` của Spring Data JPA:

~~~java
// Spring Data JDBC:
import org.springframework.data.jdbc.repository.query.Query;

// Không dùng annotation JPA cho repository Spring Data JDBC:
// import org.springframework.data.jpa.repository.Query;
~~~

Hai annotation có cùng tên nhưng thuộc hai cơ chế persistence khác nhau. Spring Data JDBC khai báo SQL; Spring Data JPA có thể khai báo JPQL hoặc native SQL tùy thuộc cách dùng. Mang import JPA vào repository JDBC có thể khiến framework không nhận diện annotation như mong đợi.

## 3. Khai báo repository method với @Query

Một repository có thể kế thừa `CrudRepository` và khai báo thêm query method:

~~~java
import java.util.Optional;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface ProductRepository
        extends CrudRepository<Product, Long> {

    @Query("""
           SELECT id, sku, name, price_minor_units
           FROM product
           WHERE sku = :sku
           """)
    Optional<Product> findBySkuWithSql(@Param("sku") String sku);
}
~~~

Các thành phần:

- `@Query` chứa câu SQL cần thực thi.
- `:sku` là named parameter trong SQL.
- `@Param("sku")` liên kết tham số Java với placeholder.
- `Optional<Product>` biểu diễn tối đa một kết quả có thể không tồn tại.

Java text block `""" ... """` giúp viết SQL nhiều dòng dễ đọc hơn (Java 15 trở lên là tính năng chính thức). Nếu dùng Java cũ hơn, có thể dùng chuỗi thông thường và nối dòng phù hợp.

### 3.1. Chọn kiểu trả về theo số lượng hàng

| Kiểu trả về | Ý nghĩa |
| --- | --- |
| `Product` | Kỳ vọng đúng một kết quả; nếu không có hoặc có nhiều hơn một kết quả, framework xử lý theo hợp đồng truy vấn đơn và có thể ném exception |
| `Optional<Product>` | Có tối đa một kết quả; không có hàng thì Optional rỗng |
| `List<Product>` | Nhiều kết quả; không có hàng thì list rỗng |
| `Collection<Product>` / `Iterable<Product>` | Tập kết quả tổng quát |
| Kiểu scalar như `Long`, `Integer`, `String` | Một giá trị được chọn từ kết quả SQL, khi kiểu trả về và cột tương thích |
| Projection/DTO | Một tập cột được ánh xạ theo projection và quy tắc hỗ trợ của phiên bản Spring Data JDBC |

Kiểu trả về là một phần hợp đồng của query method. Nếu SQL có thể trả nhiều hàng thì không khai báo `Optional<Product>` chỉ vì dữ liệu hiện tại tình cờ không trùng.

### 3.2. Kết quả không có hàng

Với method trả Optional:

~~~java
Optional<Product> findBySkuWithSql("UNKNOWN-SKU");
~~~

Nếu truy vấn chạy thành công nhưng không có hàng phù hợp, kết quả là `Optional.empty()`. Nếu method trả List, kết quả là list rỗng.

Không bắt lỗi kết nối hoặc lỗi SQL rồi chuyển thành Optional rỗng. “Không có dữ liệu” khác với “không thể truy vấn dữ liệu”.

## 4. Bind tham số bằng named parameter

SQL tùy chỉnh phải truyền dữ liệu đầu vào qua bind parameter, không ghép trực tiếp giá trị vào chuỗi SQL.

~~~java
@Query("""
       SELECT id, sku, name, price_minor_units
       FROM product
       WHERE status = :status
         AND price_minor_units >= :minimumPrice
       ORDER BY price_minor_units DESC
       """)
List<Product> findAvailableProducts(
        @Param("status") String status,
        @Param("minimumPrice") long minimumPrice
);
~~~

Placeholder `:status` được liên kết với tham số `status`; `:minimumPrice` được liên kết với tham số `minimumPrice`.

Ưu điểm của named parameter:

- SQL dễ đọc khi có nhiều tham số.
- Không phụ thuộc thứ tự dấu hỏi trong câu lệnh.
- Khi thêm tham số mới, ít nguy cơ đảo thứ tự bind.
- Giá trị được truyền như dữ liệu, không trở thành một phần cú pháp SQL.

### 4.1. Dùng @Param rõ ràng

Nên dùng `@Param` khi muốn hợp đồng tham số rõ ràng:

~~~java
@Query("SELECT * FROM product WHERE sku = :sku")
Optional<Product> findProduct(@Param("sku") String sku);
~~~

Một số cấu hình Spring Data có thể lấy tên tham số từ metadata biên dịch Java khi bật `-parameters`. Tuy nhiên, `@Param` giúp tránh phụ thuộc cấu hình đó và thể hiện trực tiếp mối liên hệ giữa placeholder SQL và tham số method.

### 4.2. Không nối chuỗi SQL từ input

Không viết:

~~~java
String sql = "SELECT * FROM product WHERE sku = '" + sku + "'";
~~~

Nếu `sku` chứa dấu nháy hoặc dữ liệu có chủ đích phá cú pháp, câu SQL có thể bị thay đổi. Đây là một nguồn SQL injection.

Hãy viết:

~~~java
@Query("SELECT * FROM product WHERE sku = :sku")
Optional<Product> findBySku(@Param("sku") String sku);
~~~

Bind parameter bảo vệ giá trị đầu vào khỏi bị diễn giải như SQL syntax. Nó không thay thế việc kiểm tra quyền truy cập, validation nghiệp vụ hay kiểm soát tên cột/bảng động.

### 4.3. Parameter không thay thế được tên bảng/cột

Bind parameter dành cho **giá trị**, không phải identifier SQL:

~~~sql
SELECT * FROM :tableName
~~~

Thông thường database không cho dùng parameter như tên bảng hoặc tên cột. Nếu cần chọn sort column động, hãy ánh xạ input vào danh sách identifier được phép rồi tạo câu SQL có kiểm soát hoặc chọn query method riêng. Không nối trực tiếp tên cột từ request.

### 4.4. Tham số null

Khi tham số có thể null, cần xác định ý nghĩa SQL mong muốn. Điều kiện:

~~~sql
WHERE category = :category
~~~

không tự có nghĩa “nếu category null thì bỏ qua bộ lọc”. So sánh SQL với NULL cho kết quả UNKNOWN, không phải TRUE.

Nếu muốn một bộ lọc tùy chọn:

~~~sql
WHERE (:category IS NULL OR category = :category)
~~~

Kiểu placeholder và cách bind null phải tương thích driver/database. Với query phức tạp, có thể tạo các method riêng hoặc dùng JdbcClient để dựng query theo điều kiện đã được kiểm soát.

## 5. Dùng @Query với điều kiện, sắp xếp và giới hạn kết quả

SQL tùy chỉnh cho phép kiểm soát trực tiếp điều kiện:

~~~java
@Query("""
       SELECT id, sku, name, price_minor_units
       FROM product
       WHERE status = :status
         AND price_minor_units BETWEEN :minimum AND :maximum
       ORDER BY name ASC, id ASC
       """)
List<Product> findByPriceRange(
        @Param("status") String status,
        @Param("minimum") long minimum,
        @Param("maximum") long maximum
);
~~~

`ORDER BY name, id` tạo thứ tự xác định hơn so với chỉ sắp xếp theo tên, vì nhiều sản phẩm có thể cùng tên. Thứ tự ổn định đặc biệt hữu ích khi chia trang hoặc xử lý theo lô.

### 5.1. LIMIT và OFFSET phụ thuộc database

Một số database hỗ trợ:

~~~sql
SELECT id, sku, name
FROM product
ORDER BY id
LIMIT :pageSize OFFSET :offset;
~~~

Database khác có thể dùng cú pháp `FETCH FIRST ... ROWS ONLY`, `OFFSET ... FETCH` hoặc cú pháp riêng. Vì `@Query` chứa SQL trực tiếp, không nên giả định một câu query giới hạn hàng chạy giống nhau trên mọi hệ quản trị.

### 5.2. Phân trang và tổng số bản ghi

Khi một API cần trang dữ liệu cùng tổng số phần tử, thường cần hai truy vấn:

~~~sql
SELECT id, sku, name
FROM product
WHERE status = :status
ORDER BY id
LIMIT :limit OFFSET :offset;
~~~

~~~sql
SELECT COUNT(*)
FROM product
WHERE status = :status;
~~~

Một query lấy dữ liệu trang và một query đếm tổng có thể được khai báo thành hai method. Cách tích hợp trực tiếp với `Page<T>` hoặc `Slice<T>` phụ thuộc API query và phiên bản Spring Data JDBC đang dùng; nếu không có hợp đồng paging phù hợp, có thể trả DTO chứa content và total được ghép ở service.

Với bảng lớn, `OFFSET` cao có thể tốn kém vì database phải bỏ qua nhiều hàng. Keyset pagination dựa trên khóa sắp xếp cuối cùng có thể hiệu quả hơn:

~~~sql
SELECT id, sku, name
FROM product
WHERE id > :lastSeenId
ORDER BY id
FETCH FIRST :pageSize ROWS ONLY;
~~~

Cú pháp giới hạn hàng cần điều chỉnh theo database. Điều kiện `id > :lastSeenId` chỉ phù hợp nếu thứ tự trang dựa trên ID tăng dần và ID là khóa ổn định.

## 6. Ánh xạ kết quả SQL vào entity

Khi method trả về một entity, các cột trong result set phải cung cấp dữ liệu cần thiết để Spring Data JDBC dựng entity theo mapping metadata.

Ví dụ entity:

~~~java
@Table("product")
public class Product {
    @Id
    private Long id;

    private String sku;
    private String name;

    @Column("price_minor_units")
    private long priceMinorUnits;

    // constructor và accessors...
}
~~~

Query:

~~~java
@Query("""
       SELECT id, sku, name, price_minor_units
       FROM product
       WHERE id = :id
       """)
Optional<Product> findProductRow(@Param("id") Long id);
~~~

Các tên cột và kiểu dữ liệu phải tương thích với mapping. Nếu entity có thuộc tính nhúng, version hoặc field bắt buộc khác, query cần trả đủ dữ liệu mà mapping cần.

### 6.1. Alias cột cho property

Khi SQL dùng biểu thức hoặc tên cột khác, alias giúp làm rõ tên kết quả:

~~~sql
SELECT
    p.id,
    p.sku,
    p.price_minor_units AS price_minor_units
FROM product p
WHERE p.id = :id;
~~~

Nếu kết quả là DTO/projection có tên component khác tên cột, cần alias theo quy tắc mapping được hỗ trợ. Không giả định mọi naming strategy đều tự đoán đúng alias từ biểu thức phức tạp.

### 6.2. Tránh SELECT * trong query lâu dài

`SELECT *` tiện khi thử nghiệm, nhưng query production nên liệt kê cột:

- Dễ nhận biết dữ liệu method cần.
- Tránh vô tình kéo thêm cột lớn hoặc nhạy cảm.
- Giảm rủi ro khi schema thêm cột có kiểu không mong muốn.
- Làm rõ contract giữa SQL và entity/DTO.
- Dễ xem xét khi mapping thay đổi.

Với entity cần nhiều cột, có thể liệt kê toàn bộ cột persistent. Với projection, chỉ chọn các cột thực sự cần.

### 6.3. Query trả về aggregate root có child collection

Một câu `@Query` đọc bảng root không nên được hiểu mặc nhiên là sẽ tự tải toàn bộ collection child như đường đọc aggregate chuẩn. Query SQL tùy chỉnh cần được thiết kế và kiểm chứng theo mapping contract của Spring Data JDBC phiên bản đang dùng. Đặc biệt với join hoặc nhiều row cho cùng root, việc dựng aggregate có thể không giống một query trả về một row root.

Nếu use case cần đầy đủ aggregate để thực hiện hành vi miền, cân nhắc:

- Dùng repository method chuẩn để tải aggregate.
- Dùng `@Query` để tìm ID root, rồi tải aggregate qua repository theo ID.
- Dùng custom query/result mapping phù hợp khi cần kiểm soát toàn bộ dữ liệu.

Nếu use case chỉ cần dữ liệu báo cáo hoặc màn hình, trả projection/DTO thay vì giả vờ một result set phẳng là aggregate đầy đủ.

## 7. Query join và projection

Một màn hình danh sách đơn hàng có thể cần tên khách hàng, trong khi customer là aggregate độc lập. SQL join phù hợp cho read model:

~~~sql
SELECT
    po.id AS order_id,
    po.order_number,
    po.status,
    c.name AS customer_name
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id
WHERE po.status = :status
ORDER BY po.id DESC;
~~~

Kết quả không nhất thiết là một `PurchaseOrder` đầy đủ. Nó là một cấu trúc đọc gồm dữ liệu từ hai aggregate.

Một DTO record có thể diễn đạt cấu trúc đó:

~~~java
public record OrderListItem(
        Long orderId,
        String orderNumber,
        String status,
        String customerName
) {
}
~~~

Khi phiên bản Spring Data JDBC và kiểu projection hỗ trợ mapping DTO tương ứng, có thể khai báo query method trả projection. Nếu result shape phức tạp hoặc cần kiểm soát row mapping chính xác, dùng `JdbcClient` hoặc `JdbcTemplate` với `RowMapper` tường minh:

~~~java
public List<OrderListItem> findOrderList(String status) {
    return jdbcClient.sql("""
            SELECT
                po.id AS order_id,
                po.order_number,
                po.status,
                c.name AS customer_name
            FROM purchase_order po
            JOIN customer c ON c.id = po.customer_id
            WHERE po.status = :status
            ORDER BY po.id DESC
            """)
        .param("status", status)
        .query((rs, rowNum) -> new OrderListItem(
                rs.getLong("order_id"),
                rs.getString("order_number"),
                rs.getString("status"),
                rs.getString("customer_name")
        ))
        .list();
}
~~~

Ví dụ dùng `JdbcClient` của Spring Framework 6.1 trở lên. Với phiên bản cũ hơn, `NamedParameterJdbcTemplate` hoặc `JdbcTemplate` có thể là lựa chọn phù hợp.

Projection giúp tránh tải toàn bộ aggregate khi màn hình chỉ cần một vài trường. Nó không thay thế aggregate root trong luồng cập nhật nghiệp vụ.

## 8. Truy vấn giá trị scalar và hàm aggregate

`@Query` cũng có thể dùng cho kết quả không phải entity, nếu kiểu trả về và mapping của phiên bản framework hỗ trợ.

Ví dụ đếm sản phẩm:

~~~java
@Query("""
       SELECT COUNT(*)
       FROM product
       WHERE status = :status
       """)
long countByStatus(@Param("status") String status);
~~~

Khi không có sản phẩm phù hợp, `COUNT(*)` thường trả một hàng với giá trị 0.

Ví dụ lấy giá thấp nhất:

~~~java
@Query("""
       SELECT MIN(price_minor_units)
       FROM product
       WHERE status = :status
       """)
Long findMinimumPrice(@Param("status") String status);
~~~

`MIN` có thể trả SQL NULL khi không có hàng phù hợp. Dùng kiểu wrapper có thể nullable nếu mapping cho phép; nếu nghiệp vụ muốn giá trị mặc định, cân nhắc `COALESCE`:

~~~sql
SELECT COALESCE(MIN(price_minor_units), 0)
FROM product
WHERE status = :status;
~~~

Đừng nhầm:

- Không có row result.
- Có một row với cột SQL NULL.
- Có một row với số 0.

Các trường hợp này có hợp đồng khác nhau.

## 9. Câu lệnh thay đổi dữ liệu với @Modifying

`@Query` chủ yếu khai báo SQL. Khi query method thực hiện `UPDATE` hoặc `DELETE`, dùng `@Modifying` để thông báo rằng đây là câu lệnh thay đổi dữ liệu:

~~~java
@Modifying
@Query("""
       UPDATE product
       SET name = :name
       WHERE id = :id
       """)
int updateName(
        @Param("id") Long id,
        @Param("name") String name
);
~~~

Kiểu trả về số nguyên thường được dùng để nhận số hàng bị ảnh hưởng. Có thể dùng `void` nếu caller không cần con số, theo hợp đồng được hỗ trợ của phiên bản đang dùng.

### 9.1. Cập nhật hàng loạt

~~~java
@Modifying
@Query("""
       UPDATE product
       SET status = :newStatus
       WHERE status = :oldStatus
       """)
int changeStatusForAll(
        @Param("oldStatus") String oldStatus,
        @Param("newStatus") String newStatus
);
~~~

Phương thức có thể cập nhật nhiều hàng. Giá trị trả về cho biết số hàng được database báo là đã ảnh hưởng (chi tiết phụ thuộc driver/database). Hãy đặt tên method thể hiện rõ phạm vi thay đổi; một câu lệnh bulk có thể tác động đến nhiều aggregate cùng lúc.

### 9.2. Xóa dữ liệu

~~~java
@Modifying
@Query("""
       DELETE FROM product
       WHERE status = :status
       """)
int deleteByStatus(@Param("status") String status);
~~~

Trước khi chạy lệnh xóa hàng loạt, cần xác định điều kiện, foreign key và chính sách lịch sử. Không dùng một câu DELETE rộng nếu dữ liệu cần được lưu để kiểm toán hoặc các aggregate khác còn tham chiếu.

### 9.3. @Modifying không phải repository.save

Bulk SQL trực tiếp không đi qua toàn bộ quy trình lưu aggregate theo cùng cách với `repository.save(entity)`:

- Không tự dựng object aggregate đã cập nhật để trả về.
- Không tự tải và kiểm tra invariant trong domain model.
- Không tự quản lý collection child theo vòng đời aggregate.
- Không nên giả định các callback/auditing hoặc quy tắc version của aggregate được áp dụng như thao tác lưu chuẩn.

Hãy dùng `@Modifying` cho thao tác SQL có chủ đích, nơi câu lệnh và ảnh hưởng dữ liệu được kiểm soát. Nếu cần thực thi hành vi nghiệp vụ trên một aggregate, thường nên đọc root, gọi hành vi miền rồi lưu qua repository.

### 9.4. Optimistic locking và @Version

Nếu entity dùng `@Version`, câu `UPDATE` tùy chỉnh không tự động nhận được điều kiện optimistic locking giống thao tác repository save. Muốn phát hiện xung đột, phải tự đưa version vào điều kiện và cập nhật version:

~~~sql
UPDATE product
SET name = :name,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

Nếu số hàng bị ảnh hưởng bằng 0, có thể do ID không tồn tại hoặc version đã thay đổi. Service cần xác định cách phân biệt và xử lý phù hợp, chẳng hạn đọc lại để phân loại lỗi. Không tự tăng version ở Java rồi giả định database đã khóa được cạnh tranh.

### 9.5. Insert và generated ID

Một câu INSERT tùy chỉnh có thể được thực thi qua API JDBC, nhưng việc lấy generated key, tạo lại entity immutable, áp dụng aggregate callbacks và xử lý quan hệ child là những phần mà `repository.save` thường quản lý tốt hơn.

Nếu chỉ cần tạo aggregate theo mô hình Spring Data JDBC, ưu tiên `save`. Chỉ dùng INSERT tùy chỉnh khi có yêu cầu rõ ràng và đã tự thiết kế cách lấy key, kiểm soát transaction và duy trì invariant.

## 10. Transaction cho query method

Một câu SQL đọc đơn giản có thể chạy trong transaction do framework hoặc tầng gọi quản lý. Với nhiều thao tác cần cùng ranh giới commit/rollback, đặt transaction ở service boundary:

~~~java
@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void rename(Long id, String newName) {
        int updated = repository.updateName(id, newName);
        if (updated != 1) {
            throw new IllegalStateException(
                    "Không tìm thấy sản phẩm hoặc dữ liệu đã thay đổi"
            );
        }
    }
}
~~~

Ví dụ giả định repository có method `updateName` tương ứng ở trên. `@Transactional` bảo đảm các thao tác JDBC trong phạm vi được quản lý có thể commit hoặc rollback theo transaction manager.

### 10.1. Đặt transaction ở đâu?

Các query method khai báo trực tiếp không nên được mặc định là có cùng transaction semantics với mọi method CRUD kế thừa. Cách rõ ràng là đặt `@Transactional` ở service cho use case cần transaction; hoặc cấu hình transaction trên method/repository khi thật sự cần.

Đặt transaction ở service giúp gom các bước nghiệp vụ:

~~~text
Service method @Transactional
   |
   +-- đọc dữ liệu cần thiết
   +-- kiểm tra quy tắc
   +-- gọi modifying query hoặc repository save
   +-- commit / rollback
~~~

### 10.2. Read-only transaction

Với query chỉ đọc:

~~~java
@Transactional(readOnly = true)
public List<Product> search(String status) {
    return repository.findByStatus(status);
}
~~~

`readOnly = true` diễn đạt ý định và có thể cung cấp hint cho transaction manager/database. Không xem nó là cơ chế phân quyền hoặc bảo đảm mọi database đều từ chối lệnh ghi.

### 10.3. Không giữ transaction trong lúc gọi dịch vụ ngoài

Nếu query method được gọi trong transaction, tránh giữ transaction mở trong lúc chờ HTTP API, gửi email hoặc xử lý file lớn. Kết nối database và snapshot/lock có thể bị giữ lâu, làm tăng contention và thời gian chờ connection pool.

## 11. SQL phụ thuộc hệ quản trị cơ sở dữ liệu

`@Query` chứa SQL trực tiếp nên cú pháp và function có thể phụ thuộc database.

| Nhu cầu | PostgreSQL | Một số hệ quản trị khác |
| --- | --- | --- |
| Giới hạn số hàng | `LIMIT ... OFFSET ...` | Có thể dùng `FETCH FIRST` hoặc `OFFSET ... FETCH` |
| Nối chuỗi | `\|\|` | Có thể dùng `CONCAT` hoặc toán tử khác |
| JSON | Toán tử và function JSON/JSONB riêng | Function và kiểu JSON khác nhau |
| Upsert | `INSERT ... ON CONFLICT ...` | Có thể dùng `MERGE` hoặc cú pháp riêng |
| Sinh khóa | `GENERATED ... AS IDENTITY` hoặc sequence | Identity/sequence syntax khác nhau |
| Hàm ngày giờ | Function/cast theo PostgreSQL | Tên hàm, timezone và kiểu dữ liệu khác nhau |

Nếu ứng dụng chỉ chạy một database, SQL đặc thù có thể là lựa chọn hợp lý. Nếu cần hỗ trợ nhiều database, phải:

- Giữ query ở phần giao nhau của SQL mà các database hỗ trợ.
- Tách implementation theo dialect/database khi cú pháp khác biệt đáng kể.
- Dùng API Spring JDBC cho phần có thể parameterize và mapping rõ.
- Viết integration test trên từng database mục tiêu.

Không có annotation nào tự động biến mọi SQL vendor-specific thành SQL portable.

## 12. CTE, subquery và hàm database

Một lợi ích của SQL tùy chỉnh là có thể dùng cú pháp mà derived query không biểu diễn được.

Ví dụ subquery:

~~~sql
SELECT p.id, p.sku, p.name, p.price_minor_units
FROM product p
WHERE p.price_minor_units > (
    SELECT AVG(p2.price_minor_units)
    FROM product p2
    WHERE p2.category_id = :categoryId
)
AND p.category_id = :categoryId;
~~~

Ví dụ CTE (cú pháp hỗ trợ tùy database):

~~~sql
WITH product_totals AS (
    SELECT category_id, COUNT(*) AS product_count
    FROM product
    GROUP BY category_id
)
SELECT category_id, product_count
FROM product_totals
WHERE product_count >= :minimumCount;
~~~

Với query dạng tổng hợp, kiểu trả về nên là projection/DTO thay vì entity đầy đủ nếu kết quả không đại diện cho một aggregate. Nếu mapping của `@Query` không phù hợp với result shape, dùng `JdbcClient`/`JdbcTemplate` và row mapper tường minh.

## 13. Giữ SQL dễ bảo trì

SQL trong annotation nằm cạnh repository method, thuận tiện cho query ngắn. Khi query dài hoặc có nhiều biến thể, cần giữ cấu trúc dễ đọc:

- Dùng text block và xuống dòng theo mệnh đề.
- Chọn cột rõ ràng, alias nhất quán.
- Dùng named parameter và `@Param`.
- Đặt tên method phản ánh mục đích nghiệp vụ.
- Tránh một query duy nhất với quá nhiều điều kiện tùy chọn nếu khó đọc và khó tối ưu.
- Đưa truy vấn phức tạp sang custom repository/JDBC client khi annotation không còn phù hợp.

Ví dụ query ngắn:

~~~java
@Query("""
       SELECT id, sku, name, price_minor_units
       FROM product
       WHERE status = :status
       ORDER BY id
       """)
List<Product> findAllByStatus(@Param("status") String status);
~~~

Với query nhiều CTE, dynamic filter hoặc result mapping phức tạp, một custom repository implementation có thể tách SQL khỏi interface và cho phép dùng mapper/logic rõ ràng hơn.

### 13.1. Không tạo một method cho mọi chuỗi SQL động

Tránh API nhận cả câu SQL từ caller:

~~~java
List<Product> executeSql(String sql);
~~~

Đây là một ranh giới bảo mật và bảo trì nguy hiểm. Caller có thể thực thi SQL ngoài ý định. Repository method nên định nghĩa truy vấn có mục đích và bind giá trị đầu vào. Nếu cần query động, xây query từ các thành phần được whitelist ở tầng persistence, không nhận raw SQL tùy ý từ request.

## 14. Kiểm thử @Query

SQL tùy chỉnh cần được kiểm thử trên database phù hợp vì câu lệnh có thể hợp lệ về cú pháp Java nhưng sai tên cột, kiểu dữ liệu, dialect hoặc mapping.

### 14.1. Kiểm thử kết quả đơn

~~~java
@DataJdbcTest
class ProductRepositoryTest {

    @Autowired
    ProductRepository repository;

    @Test
    void findsProductBySku() {
        // Chuẩn bị dữ liệu bằng schema/test fixture phù hợp.
        Optional<Product> result =
                repository.findBySkuWithSql("BOOK-021");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getSku())
                .isEqualTo("BOOK-021");
    }
}
~~~

Đây là khung minh họa; test thực tế cần import/assertion phù hợp và chuẩn bị dữ liệu theo schema của dự án. `@DataJdbcTest` thường cấu hình slice test cho JDBC repositories; database dùng trong test cần tương thích với cú pháp SQL.

### 14.2. Kiểm thử kết quả rỗng

~~~java
assertThat(repository.findBySkuWithSql("MISSING"))
        .isEmpty();
~~~

Kiểm tra hợp đồng absence giúp phát hiện trường hợp query method vô tình trả sai kiểu hoặc SQL filter không đúng.

### 14.3. Kiểm thử modifying query

~~~java
int updated = repository.updateName(id, "Tên mới");

assertThat(updated).isEqualTo(1);
assertThat(repository.findById(id))
        .get()
        .extracting(Product::getName)
        .isEqualTo("Tên mới");
~~~

Kiểm tra cả số hàng bị ảnh hưởng và trạng thái đọc lại. Nếu dùng version, cần kiểm tra version được cập nhật đúng theo logic mà query tự triển khai.

### 14.4. Dùng database thật hoặc Testcontainers khi cần

H2 có thể hữu ích cho test nhanh, nhưng không phải lúc nào cũng tương thích hoàn toàn với SQL PostgreSQL/MySQL/SQL Server. Nếu query dùng function, JSON, CTE, locking, generated column hoặc cú pháp vendor-specific, nên chạy integration test với đúng database mục tiêu, ví dụ qua Testcontainers.

### 14.5. Quan sát SQL và execution plan

Khi query chậm:

- Xem câu SQL thực tế và tham số bind.
- Kiểm tra index có hỗ trợ điều kiện lọc/join không.
- Dùng execution plan của database.
- Đo số row đọc và số row trả về.
- Tránh chỉ nhìn thời gian Java method mà kết luận database là nguyên nhân duy nhất.

Không bật log tham số nhạy cảm trên production nếu chưa có chính sách bảo vệ dữ liệu phù hợp.

## 15. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Import nhầm `org.springframework.data.jpa.repository.Query` | Dùng annotation của JPA trong repository JDBC | Import `org.springframework.data.jdbc.repository.query.Query` |
| Viết JPQL thay vì SQL | `@Query` của Spring Data JDBC làm việc với schema SQL | Dùng tên bảng, cột và cú pháp database |
| Ghép input vào chuỗi SQL | SQL injection và lỗi escaping | Dùng named parameter và `@Param` |
| Dùng parameter cho tên bảng/cột | Bind parameter chỉ dành cho giá trị | Whitelist identifier hoặc chọn query riêng |
| Method trả Optional nhưng query có thể trả nhiều hàng | Hợp đồng cardinality không đúng | Dùng collection hoặc bảo vệ unique constraint |
| Query thiếu cột cần thiết cho entity | Framework không thể dựng object đầy đủ | Chọn đủ cột và alias đúng |
| Dùng SELECT * trong query lâu dài | Mapping phụ thuộc schema rộng và khó kiểm soát | Liệt kê cột cần thiết |
| Nghĩ @Query root tự tải child collections | Nhầm custom SQL với luồng aggregate loading chuẩn | Kiểm chứng mapping; dùng repository root hoặc query result mapping riêng |
| Dùng @Modifying nhưng quên transaction | Câu lệnh thay đổi không có ranh giới transaction mong muốn | Đặt transaction ở service/method |
| Nghĩ @Modifying tự xử lý @Version | Bulk SQL không tự áp dụng optimistic locking như save | Tự thêm điều kiện version và kiểm tra affected rows |
| Dùng bulk update để thay đổi aggregate mà bỏ qua invariant | SQL bypass hành vi miền | Dùng repository save hoặc kiểm tra đầy đủ quy tắc trong custom operation |
| Dùng SQL vendor-specific mà chỉ test H2 | Test không phản ánh production dialect | Test trên database mục tiêu |
| Bắt mọi exception và trả collection rỗng | Che lỗi SQL/kết nối | Chỉ biểu diễn absence khi query thực sự thành công |

## 16. Quy trình thiết kế một @Query method

Khi cần SQL tùy chỉnh, hãy đi theo trình tự:

1. **Xác định mục tiêu truy vấn.** Đây là đọc entity, projection, scalar hay cập nhật/xóa?
2. **Xác định cardinality.** Không hàng, tối đa một hay nhiều hàng? Chọn Optional, entity hoặc collection đúng hợp đồng.
3. **Viết SQL theo schema thật.** Dùng tên bảng/cột, join và function đúng database mục tiêu.
4. **Bind tham số.** Dùng named parameter và `@Param`; không ghép giá trị vào SQL.
5. **Thiết kế result mapping.** Đảm bảo các cột cần thiết có tên và kiểu phù hợp; dùng DTO/RowMapper khi result shape không phải aggregate.
6. **Chọn annotation.** Dùng `@Query` cho câu SQL và `@Modifying` khi method thay đổi dữ liệu.
7. **Đặt transaction.** Xác định ranh giới transaction ở service/method cho use case cần thiết.
8. **Kiểm tra concurrency.** Nếu cập nhật có version, tự duy trì điều kiện version và xử lý số hàng bị ảnh hưởng.
9. **Kiểm thử đúng dialect.** Bao phủ có dữ liệu, không có dữ liệu, nhiều kết quả, constraint và lỗi.
10. **Đo hiệu năng.** Xem execution plan, index, số row và thời gian truy vấn.

## Ghi nhớ

`@Query` trong Spring Data JDBC cho phép khai báo SQL trực tiếp theo cú pháp của database. Dùng named parameter để bind giá trị an toàn, chọn kiểu trả về đúng cardinality và bảo đảm result set phù hợp với entity hoặc projection. Với câu lệnh thay đổi dữ liệu, dùng `@Modifying` và quản lý transaction rõ ràng; nếu có `@Version`, tự xử lý điều kiện optimistic locking trong SQL tùy chỉnh.

Custom SQL đem lại khả năng kiểm soát truy vấn, nhưng cũng chuyển trách nhiệm về schema, dialect, result mapping và concurrency đến gần người viết hơn. Hãy giữ query có mục đích, kiểm thử trên database mục tiêu và dùng repository aggregate chuẩn khi use case cần tải hoặc thay đổi đầy đủ trạng thái miền.
