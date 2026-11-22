# Khi nào cần native SQL thay cho JPQL

Trong Spring Data JPA, JPQL cho phép truy vấn theo Entity và thuộc tính Java, còn native SQL cho phép viết câu lệnh theo cú pháp và cấu trúc thật của database. Native SQL hữu ích khi truy vấn cần tính năng riêng của hệ quản trị, cú pháp JPQL không biểu diễn được, hoặc cần kiểm soát một câu SQL cụ thể để tích hợp với schema hiện có.

Tuy nhiên, native SQL làm ứng dụng phụ thuộc nhiều hơn vào database, tên bảng/cột, kiểu dữ liệu và dialect. Vì vậy, chỉ nên chọn native query khi lợi ích về khả năng biểu đạt, tích hợp hoặc hiệu năng đã được xác định. Với truy vấn CRUD và quan hệ thông thường, JPQL thường dễ bảo trì và di chuyển hơn.

## 1. JPQL và native SQL khác nhau ở đâu?

JPQL (Jakarta Persistence Query Language) truy vấn trên mô hình Entity. Tên trong câu lệnh là tên Entity và thuộc tính Java, không phải tên bảng và cột vật lý.

Ví dụ JPQL:

~~~java
@Query("""
    select p
    from Product p
    where p.category.name = :categoryName
    order by p.name
    """)
List<Product> findByCategoryName(
        @Param("categoryName") String categoryName
);
~~~

Câu truy vấn dùng Entity Product, thuộc tính category và name. Hibernate chuyển JPQL thành SQL phù hợp với database hiện tại.

Native SQL truy vấn trực tiếp bảng và cột:

~~~java
@Query(value = """
    SELECT p.*
    FROM products p
    JOIN categories c ON c.id = p.category_id
    WHERE c.name = ?1
    ORDER BY p.name
    """, nativeQuery = true)
List<Product> findByCategoryNameNative(String categoryName);
~~~

Câu truy vấn dùng tên bảng products, categories và cột category_id. Đây là SQL thực tế dành cho database mục tiêu.

| Tiêu chí | JPQL | Native SQL |
|---|---|---|
| Mô hình truy vấn | Entity và thuộc tính Java | Bảng, cột, view và cú pháp SQL |
| Khả năng di động | Thường cao hơn giữa các database | Phụ thuộc SQL dialect và schema |
| Quan hệ | Điều hướng qua thuộc tính Entity | JOIN bằng khóa ngoại và điều kiện SQL |
| Tính năng riêng database | Bị giới hạn bởi JPQL chuẩn/provider | Có thể dùng trực tiếp |
| Mapping kết quả | Tự nhiên với Entity và projection | Cần bảo đảm cột/alias phù hợp với kiểu trả về |
| Kiểm soát SQL | Provider sinh SQL | Nhà phát triển viết SQL |
| Bảo trì | Ít gắn với schema vật lý | Cần cập nhật khi đổi tên bảng/cột hoặc database |

Native SQL vẫn có thể được thực thi qua EntityManager hoặc Spring Data Repository. Dùng native query không có nghĩa phải bỏ JPA hay chuyển toàn bộ module sang JDBC.

## 2. Khi JPQL là đủ

Với các truy vấn phổ biến, JPQL thường là lựa chọn đầu tiên:

- Tìm Entity theo thuộc tính.
- Lọc theo trạng thái, ngày tháng hoặc khoảng giá trị.
- JOIN các quan hệ đã mapping.
- Sắp xếp và phân trang.
- Dùng EXISTS, subquery và các hàm tổng hợp được JPQL hỗ trợ.
- Cập nhật hoặc xóa theo điều kiện đơn giản bằng JPQL bulk query.

Ví dụ:

~~~java
@Query("""
    select p
    from Product p
    where p.active = true
      and p.price between :minimum and :maximum
    """)
Page<Product> findActiveProductsInPriceRange(
        @Param("minimum") BigDecimal minimum,
        @Param("maximum") BigDecimal maximum,
        Pageable pageable
);
~~~

JPQL cho phép provider xử lý tên Entity, mapping và kiểu dữ liệu. Khi chuyển database, ứng dụng thường ít phải sửa truy vấn hơn, dù vẫn cần kiểm thử sự khác biệt về kiểu dữ liệu, collation, hàm và hiệu năng.

Không nên dùng native SQL chỉ vì câu SQL trông quen thuộc hơn. Nếu JPQL diễn đạt rõ yêu cầu và tạo execution plan tốt, đó thường là lựa chọn dễ bảo trì hơn.

## 3. Khi cần tính năng SQL mà JPQL chuẩn không biểu diễn được

Đây là lý do phổ biến nhất để chọn native query. Một số tính năng SQL không có cú pháp tương đương trong JPQL chuẩn hoặc phụ thuộc extension của provider:

- Common Table Expression (CTE) với WITH.
- Recursive CTE để duyệt cây hoặc cấu trúc phân cấp.
- Window functions như ROW_NUMBER(), RANK(), LAG(), LEAD().
- Một số toán tử JSON, JSON path hoặc kiểu JSONB riêng của database.
- Array operators, toán tử full-text search hoặc spatial.
- Database hints, optimizer directives và cú pháp lock đặc thù.
- UPSERT như ON CONFLICT của PostgreSQL hoặc ON DUPLICATE KEY UPDATE của MySQL.
- Truy vấn materialized view hoặc cấu trúc legacy đặc thù.

Ví dụ dùng window function để xếp hạng sản phẩm theo giá trong từng danh mục:

~~~java
@Query(value = """
    SELECT
        p.id AS product_id,
        p.category_id AS category_id,
        p.name AS product_name,
        p.price AS price,
        ROW_NUMBER() OVER (
            PARTITION BY p.category_id
            ORDER BY p.price DESC
        ) AS price_rank
    FROM products p
    """, nativeQuery = true)
List<Object[]> rankProductsByCategory();
~~~

ROW_NUMBER() OVER (PARTITION BY ...) là tính năng SQL. JPQL chuẩn không có cú pháp window function tương đương. Kết quả ví dụ là các dòng dữ liệu gồm ID, danh mục, tên, giá và thứ hạng; kiểu trả về Object[] phù hợp để minh họa nhưng không phải lựa chọn tốt nhất cho API lâu dài.

Có thể dùng projection hoặc DTO để đặt tên và kiểu dữ liệu rõ ràng hơn.

## 4. Khi cần CTE hoặc truy vấn đệ quy

CTE giúp chia truy vấn phức tạp thành các phần có tên. Recursive CTE có thể duyệt cây danh mục, sơ đồ tổ chức hoặc quan hệ cha-con.

Ví dụ PostgreSQL tìm một danh mục cùng tất cả danh mục con:

~~~java
@Query(value = """
    WITH RECURSIVE category_tree AS (
        SELECT id, parent_id, name
        FROM categories
        WHERE id = ?1

        UNION ALL

        SELECT child.id, child.parent_id, child.name
        FROM categories child
        JOIN category_tree parent
          ON child.parent_id = parent.id
    )
    SELECT id, parent_id, name
    FROM category_tree
    """, nativeQuery = true)
List<Object[]> findCategoryTree(Long rootId);
~~~

Đây là cú pháp PostgreSQL. Database khác có thể có khác biệt về cú pháp recursive CTE, cách khai báo cột, giới hạn đệ quy hoặc kiểu dữ liệu. Cần kiểm thử trên đúng hệ quản trị.

JPQL có thể điều hướng quan hệ đã mapping, nhưng không cung cấp cú pháp CTE đệ quy chuẩn để giải quyết mọi cấu trúc cây. Nếu truy vấn cây là nghiệp vụ chính, native SQL hoặc một giải pháp chuyên biệt thường phù hợp hơn.

## 5. Khi cần toán tử hoặc kiểu dữ liệu riêng database

Một số database có tính năng dữ liệu không được JPQL chuẩn biểu diễn đầy đủ.

Ví dụ PostgreSQL JSONB:

~~~java
@Query(value = """
    SELECT e.*
    FROM event_records e
    WHERE e.payload ->> 'eventType' = ?1
    """, nativeQuery = true)
List<EventRecord> findEventsByType(String eventType);
~~~

Toán tử ->> trích xuất giá trị văn bản từ JSONB. Đây là cú pháp PostgreSQL; không thể giả định MySQL, Oracle hoặc H2 dùng cùng toán tử.

Các tình huống tương tự gồm:

- Tìm kiếm full-text theo cơ chế của database.
- Lọc dữ liệu địa lý bằng PostGIS.
- So sánh array bằng toán tử riêng.
- Dùng hàm xử lý JSON hoặc chuỗi đặc thù.
- Truy vấn dữ liệu trong materialized view.

Nếu ứng dụng chỉ cần lưu JSON và truy xuất toàn bộ payload, có thể mapping kiểu dữ liệu bằng Hibernate hoặc converter mà không cần native query cho mọi thao tác. Chỉ dùng native SQL ở phần thật sự cần toán tử đặc thù.

## 6. Khi cần tích hợp schema legacy hoặc view

Trong hệ thống cũ, database có thể có:

- Tên bảng/cột không theo quy ước Entity.
- View hoặc materialized view đã được DBA xây dựng.
- Bảng báo cáo hoặc bảng tổng hợp.
- Cấu trúc dữ liệu không thuận tiện để biểu diễn bằng Entity.
- Stored procedure hoặc function đã được dùng chung bởi nhiều ứng dụng.

Native SQL cho phép truy vấn trực tiếp cấu trúc đó mà không cần ép toàn bộ schema vào mô hình Entity.

Ví dụ đọc từ view báo cáo:

~~~java
public interface SalesSummary {
    Long getCustomerId();
    BigDecimal getTotalSales();
}
~~~

~~~java
@Query(value = """
    SELECT
        s.customer_id AS customerId,
        s.total_sales AS totalSales
    FROM customer_sales_summary s
    WHERE s.total_sales >= ?1
    """, nativeQuery = true)
List<SalesSummary> findCustomersBySalesThreshold(
        BigDecimal minimumSales
);
~~~

Alias customerId và totalSales cần tương ứng với các accessor của projection. Tên alias và cách provider trả column label có thể ảnh hưởng đến việc ánh xạ, nên hãy kiểm tra bằng integration test trên database thật.

## 7. Khai báo native query trong Spring Data JPA

Cách phổ biến và tương thích rộng là dùng @Query với nativeQuery = true:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query(value = """
        SELECT p.*
        FROM products p
        WHERE p.active = true
        ORDER BY p.name
        """, nativeQuery = true)
    List<Product> findAllActiveNative();
}
~~~

Khi native query trả về Product, câu SQL cần chọn đủ các cột cần thiết để JPA provider hydrate Entity theo mapping. Các cột khóa chính, trường bắt buộc, trường kế thừa hoặc mapping liên quan phải có mặt và có tên/kiểu phù hợp.

Không nên SELECT một vài cột rồi khai báo kiểu trả về là Entity đầy đủ. Nếu chỉ cần một phần dữ liệu, hãy dùng projection hoặc DTO.

### Dùng EntityManager khi cần kiểm soát trực tiếp

Có thể tạo native query qua EntityManager:

~~~java
@Repository
public class ProductNativeRepository {

    @PersistenceContext
    private EntityManager entityManager;

    public List<Product> findActiveProducts() {
        return entityManager
                .createNativeQuery(
                    "SELECT * FROM products WHERE active = ?",
                    Product.class
                )
                .setParameter(1, true)
                .getResultList();
    }
}
~~~

Product.class yêu cầu JPA map các dòng kết quả thành Entity Product. Placeholder ? là tham số vị trí của native SQL theo API JPA; setParameter(1, ...) gán giá trị cho tham số thứ nhất.

EntityManager phù hợp khi cần API native query, cấu hình hint, timeout, lock mode hoặc result mapping phức tạp hơn. Với truy vấn đơn giản, @Query thường gọn hơn.

## 8. Bind tham số an toàn

Luôn dùng tham số bind thay vì nối chuỗi đầu vào vào SQL.

An toàn:

~~~java
@Query(value = """
    SELECT p.*
    FROM products p
    WHERE p.name = ?1
    """, nativeQuery = true)
List<Product> findByNameNative(String name);
~~~

Không an toàn:

~~~java
String sql =
        "SELECT * FROM products WHERE name = '" + name + "'";
~~~

Nối chuỗi có thể mở đường cho SQL injection nếu giá trị đến từ người dùng. Bind parameter giúp driver truyền dữ liệu như một giá trị, không diễn giải nó thành cú pháp SQL.

Lưu ý:

- Parameter bind dùng cho giá trị như ID, tên, trạng thái hoặc ngày.
- Không thể dùng parameter bind để thay tên bảng, tên cột, từ khóa ORDER BY hoặc hướng ASC/DESC.
- Nếu cần lựa chọn cột sắp xếp động, hãy ánh xạ lựa chọn của người dùng vào danh sách identifier được cho phép rồi tạo query theo whitelist.
- Không nối trực tiếp nội dung người dùng vào điều kiện SQL.
- Cú pháp tham số native có thể khác theo API/provider. Dùng placeholder vị trí ?1 trong Spring Data là cách phổ biến; named parameter trong native query không được Jakarta Persistence bảo đảm tính di động giữa mọi provider.

Ví dụ whitelist sort:

~~~java
String sortColumn = switch (requestedSort) {
    case "name" -> "p.name";
    case "price" -> "p.price";
    case "createdAt" -> "p.created_at";
    default -> "p.id";
};
~~~

Chỉ các identifier do ứng dụng định nghĩa mới được đưa vào SQL. Không sử dụng nguyên văn chuỗi sort do client gửi lên.

## 9. Mapping kết quả native query

Kết quả native query có thể được ánh xạ theo nhiều cách. Chọn kiểu trả về phù hợp với lượng dữ liệu và mục đích sử dụng.

### Trả về Entity

~~~java
@Query(value = """
    SELECT p.*
    FROM products p
    WHERE p.id = ?1
    """, nativeQuery = true)
Optional<Product> findEntityByIdNative(Long id);
~~~

Dùng khi cần một Entity được quản lý bởi persistence context. Câu SELECT phải trả đủ các cột theo mapping của Entity.

### Trả về interface projection

~~~java
public interface ProductSummary {
    Long getId();
    String getName();
    BigDecimal getPrice();
}
~~~

~~~java
@Query(value = """
    SELECT
        p.id AS id,
        p.name AS name,
        p.price AS price
    FROM products p
    WHERE p.active = true
    """, nativeQuery = true)
List<ProductSummary> findActiveProductSummaries();
~~~

Projection chỉ lấy các cột cần thiết và không yêu cầu hydrate toàn bộ Entity. Alias nên khớp tên property của projection; kiểm tra cách ánh xạ với provider và phiên bản Spring Data đang dùng.

### Trả DTO class

Với native query, việc ánh xạ trực tiếp vào DTO class không phải lúc nào cũng tự động như projection interface. Nếu kết quả cần constructor mapping cụ thể, có thể dùng @SqlResultSetMapping cùng @ConstructorResult, hoặc lấy scalar result rồi chuyển sang DTO trong repository/service.

Không nên phụ thuộc vào thứ tự cột của Object[] ở nhiều nơi trong ứng dụng. Nếu buộc phải dùng Object[], hãy đóng gói và chuyển đổi tại một điểm, kiểm tra kiểu dữ liệu và alias rõ ràng.

## 10. Phân trang với native query

Native query có thể kết hợp Pageable, nhưng Spring Data cần biết cách đếm tổng số kết quả. Với truy vấn đơn giản, framework có thể suy ra count query; với truy vấn phức tạp, hãy khai báo countQuery rõ ràng.

~~~java
@Query(
    value = """
        SELECT p.id AS id, p.name AS name, p.price AS price
        FROM products p
        WHERE p.active = true
        ORDER BY p.name
        """,
    countQuery = """
        SELECT COUNT(*)
        FROM products p
        WHERE p.active = true
        """,
    nativeQuery = true
)
Page<ProductSummary> findActiveSummaries(Pageable pageable);
~~~

countQuery phải đếm đúng số bản ghi logic mà truy vấn nội dung trả về. Nếu truy vấn có JOIN làm nhân bản dòng, DISTINCT hoặc GROUP BY, countQuery cần phản ánh đúng ngữ nghĩa đó.

Dynamic sorting với native query phụ thuộc phiên bản Spring Data và khả năng phân tích SQL. Không nên giả định mọi native query đều có thể được framework tự động nối ORDER BY an toàn. Với truy vấn phức tạp, có thể định nghĩa các phương thức sort cố định hoặc xây dựng lựa chọn sort bằng whitelist.

## 11. Native UPDATE/DELETE và tác động đến persistence context

Native SQL có thể thực hiện cập nhật hoặc xóa trực tiếp:

~~~java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query(value = """
    UPDATE products
    SET active = false
    WHERE created_at < ?1
    """, nativeQuery = true)
int deactivateOlderThan(Instant cutoff);
~~~

Phương thức cần được gọi trong transaction, thường do service quản lý:

~~~java
@Service
public class ProductMaintenanceService {

    private final ProductRepository repository;

    public ProductMaintenanceService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int deactivateOldProducts(Instant cutoff) {
        return repository.deactivateOlderThan(cutoff);
    }
}
~~~

Bulk native DML tác động trực tiếp database, không cập nhật từng Entity trong persistence context. Vì vậy:

- Entity đã được load trước đó có thể còn dữ liệu cũ trong bộ nhớ.
- Callback @PreUpdate/@PreRemove không tự chạy cho từng Entity.
- Cơ chế dirty checking không theo dõi từng dòng đã bị sửa bởi SQL.
- Optimistic locking không tự động được áp dụng như khi cập nhật Entity qua JPA.
- Cache cấp hai hoặc cache query có thể cần được xử lý theo cấu hình/provider.

flushAutomatically yêu cầu flush thay đổi JPA đang chờ trước khi chạy query; clearAutomatically xóa persistence context sau khi chạy để tránh tiếp tục dùng Entity stale. Việc clear ảnh hưởng mọi Entity đang managed trong persistence context đó, vì vậy chỉ dùng khi hiểu rõ tác động.

Nếu cập nhật bằng native SQL và vẫn cần optimistic locking, hãy tự đưa điều kiện version vào WHERE và tăng version trong câu UPDATE, sau đó kiểm tra số dòng được cập nhật. Không giả định @Version tự bảo vệ một câu SQL native tùy ý.

## 12. Native query có nhanh hơn JPQL không?

Không. Native SQL không tự động nhanh hơn JPQL. JPQL thường được provider dịch thành SQL tương đương. Nếu hai câu lệnh tạo ra cùng execution plan, hiệu năng có thể gần như nhau.

Native SQL có thể hữu ích khi:

- Cần kiểm soát chính xác JOIN, CTE, window function hoặc hint.
- Muốn dùng index/operator riêng của database.
- Cần viết truy vấn mà JPQL/provider không diễn đạt được.
- Đã đo và chứng minh câu SQL do provider sinh ra chưa phù hợp.
- DBA đã tối ưu một câu SQL cụ thể cho workload thực tế.

Để đánh giá, hãy so sánh:
1. SQL thực tế được thực thi.
2. Execution plan của database.
3. Số dòng đọc và trả về.
4. Index được sử dụng.
5. Thời gian chạy với dữ liệu gần production.
6. Chi phí ghi và lock khi có nhiều transaction đồng thời.

Không nên chuyển sang native chỉ vì câu query dài hoặc vì nghĩ rằng SQL viết tay luôn tối ưu hơn.

## 13. Native SQL và tính di động giữa các database

Một native query thường phụ thuộc vào:

- Tên bảng, cột, schema và quoting.
- Kiểu dữ liệu vật lý.
- Hàm, toán tử và cú pháp riêng database.
- Cách phân trang và giới hạn dòng.
- Kiểu dữ liệu trả về từ JDBC driver.
- Cách database xử lý NULL, collation và timestamp.
- Hỗ trợ CTE, JSON, window function, lock và hint.

Ví dụ PostgreSQL dùng LIMIT/OFFSET:

~~~sql
SELECT *
FROM products
ORDER BY id
LIMIT 20 OFFSET 40;
~~~

Một số database dùng cú pháp phân trang khác. Spring Data có thể tạo phần phân trang theo dialect cho các query phù hợp, nhưng câu SQL viết tay chứa cú pháp riêng vẫn cần điều chỉnh khi chuyển engine.

Nếu ứng dụng hỗ trợ nhiều database, hãy cô lập native query trong repository riêng, đặt tên rõ ràng theo database nếu cần, và duy trì integration test cho từng engine. Không nên để cú pháp PostgreSQL rải rác trong nhiều service.

## 14. Native query và stored procedure

Native query là câu SQL được gửi trực tiếp qua JPA. Stored procedure là thủ tục đã được định nghĩa trong database và được gọi bằng API phù hợp, chẳng hạn @NamedStoredProcedureQuery hoặc StoredProcedureQuery.

Stored procedure có thể phù hợp khi:

- Logic xử lý dữ liệu lớn cần chạy gần database.
- Nhiều ứng dụng dùng chung một quy trình database.
- DBA quản lý quy trình và quyền thực thi tập trung.
- Cần dùng khả năng thủ tục riêng của database.

Đổi lại, logic nghiệp vụ bị phân tán giữa Java và database, khó test độc lập hơn và có thể phụ thuộc mạnh vào hệ quản trị. Không dùng stored procedure chỉ để thay một truy vấn đơn giản mà JPQL hoặc native query đã xử lý tốt.

## 15. Những lỗi thường gặp

**Dùng tên Entity trong native SQL**

Native SQL cần tên bảng và cột thật. JPQL mới dùng tên Entity và thuộc tính Java.

**Dùng tên bảng/cột SQL trong JPQL**

JPQL không mặc định hiểu tên vật lý. Hãy dùng tên Entity và thuộc tính được mapping.

**Trả Entity nhưng chỉ SELECT một phần cột**

Provider có thể không hydrate được Entity đầy đủ hoặc trả dữ liệu không đúng. Dùng projection/DTO nếu chỉ cần một phần dữ liệu.

**Nối chuỗi tham số vào SQL**

Có nguy cơ SQL injection. Dùng bind parameter cho mọi giá trị đầu vào.

**Dùng bind parameter cho tên cột hoặc ORDER BY**

SQL parameter không thay thế identifier. Dùng whitelist các lựa chọn được phép.

**Quên countQuery cho native pagination phức tạp**

Spring Data có thể không suy ra đúng số dòng. Khai báo countQuery phù hợp với logic truy vấn.

**Dùng native DML rồi đọc lại Entity cũ trong cùng persistence context**

Entity managed có thể stale. Cân nhắc flush/clear và kiểm tra transaction.

**Cho rằng native SQL luôn nhanh hơn**

Cần đo execution plan và workload. Native chỉ tăng quyền kiểm soát, không tự tạo hiệu năng.

**Chỉ test trên H2 trong khi production dùng database khác**

Kiểu dữ liệu, cú pháp, collation và hàm có thể khác. Chạy integration test trên đúng database mục tiêu.

## 16. Quy trình quyết định và kiểm thử

Trước khi viết native query, hãy trả lời:

1. JPQL chuẩn có biểu diễn được yêu cầu không?
2. Có cần CTE, window function, JSON operator, full-text, spatial, hint hoặc cú pháp đặc thù không?
3. Native query có thật sự cải thiện khả năng kiểm soát hoặc hiệu năng đã đo được không?
4. Kết quả nên là Entity, projection hay DTO?
5. Có cần phân trang và countQuery riêng không?
6. Tham số đã được bind an toàn chưa?
7. Native DML có ảnh hưởng persistence context, lifecycle callback hoặc version không?
8. Query phụ thuộc database nào và được cô lập ở đâu?
9. Integration test có chạy trên đúng engine, schema và phiên bản không?

Sau khi triển khai, kiểm tra SQL thực tế, kiểu dữ liệu trả về, alias projection, transaction, execution plan và các trường hợp NULL. Nếu query có nhiều JOIN, hãy kiểm tra duplicate row và cách countQuery đếm kết quả.

## 17. Kết luận

Native SQL nên được dùng khi JPQL chuẩn không đủ khả năng biểu đạt truy vấn, khi cần tính năng đặc thù database, tích hợp schema/view legacy hoặc kiểm soát một câu SQL đã được đo và tối ưu. Với CRUD, quan hệ và điều kiện thông thường, JPQL thường dễ đọc, dễ bảo trì và di động hơn. Khi dùng native query, cần bind tham số an toàn, mapping kết quả rõ ràng, xử lý phân trang và persistence context cẩn thận, đồng thời kiểm thử trên database mục tiêu.