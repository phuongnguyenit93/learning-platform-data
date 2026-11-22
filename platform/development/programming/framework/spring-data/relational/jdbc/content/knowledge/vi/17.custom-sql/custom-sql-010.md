# Chọn truy vấn suy diễn, @Query hoặc triển khai tùy chỉnh theo bài toán

Trong **Spring Data Relational JDBC**, một repository có thể lấy dữ liệu bằng tên phương thức suy diễn, khai báo SQL trực tiếp với `@Query` hoặc bổ sung một phần triển khai riêng dùng Spring JDBC. Ba cách này đều có chỗ đứng, nhưng giải quyết những mức độ phức tạp khác nhau.

Lựa chọn phù hợp phụ thuộc vào hình dạng truy vấn, tính động của điều kiện, kiểu kết quả cần trả về, ranh giới aggregate, yêu cầu hiệu năng và mức độ phụ thuộc vào cú pháp của database. Một truy vấn đơn giản có thể được diễn đạt rõ bằng tên method; một câu SQL cố định có thể phù hợp với `@Query`; còn truy vấn động hoặc cần mapping đặc biệt thường dễ kiểm soát hơn trong custom repository fragment.

Bài học này cung cấp cách ra quyết định, ví dụ cùng một bài toán được triển khai theo ba hướng, cách kết hợp chúng trong một repository, và các lưu ý về transaction, bảo mật, tính portable và kiểm thử.

## 1. Ba cách truy vấn trong Spring Data JDBC

Spring Data JDBC hỗ trợ ba hướng chính:

| Cách làm | Cách mô tả truy vấn | Phù hợp khi |
| --- | --- | --- |
| Derived query (truy vấn suy diễn) | Tên phương thức repository mô tả property và predicate | Điều kiện đơn giản, cố định, chủ yếu lọc theo thuộc tính của aggregate root |
| `@Query` | Viết SQL trực tiếp trong annotation trên method | SQL cố định cần join, function, subquery hoặc điều kiện cụ thể |
| Custom repository implementation | Viết code Java dùng `JdbcClient`, `NamedParameterJdbcTemplate` hoặc `JdbcTemplate` | Điều kiện động, nhiều nhánh, SQL phức tạp, mapping đặc biệt hoặc cần phối hợp nhiều thao tác |

Luồng lựa chọn:

~~~text
Nhu cầu truy vấn
      |
      v
Điều kiện đơn giản, cố định, biểu diễn rõ bằng tên method?
      |
      +-- Có --> Derived query
      |
      +-- Không
            |
            v
       SQL cố định, result shape rõ ràng?
            |
            +-- Có --> @Query
            |
            +-- Không
                  |
                  v
           Custom repository fragment
           (SQL động / mapping / điều phối)
~~~

Đây là hướng dẫn ra quyết định, không phải luật cứng. Một truy vấn đơn giản vẫn có thể dùng `@Query` nếu SQL tường minh giúp dễ đọc hơn; một truy vấn phức tạp nhưng hoàn toàn cố định có thể nằm trong annotation nếu nó vẫn dễ bảo trì.

## 2. Khi nào chọn truy vấn suy diễn?

Truy vấn suy diễn phù hợp khi có thể mô tả ý định bằng tên method ngắn, rõ và ổn định. Spring Data phân tích tên method để tạo điều kiện SQL dựa trên thuộc tính entity.

Ví dụ aggregate:

~~~java
import java.time.LocalDateTime;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("products")
public record Product(
        @Id Long id,
        String sku,
        String name,
        String status,
        @Column("price_minor_units") long priceMinorUnits,
        @Column("created_at") LocalDateTime createdAt
) {
}
~~~

Repository:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long> {

    Optional<Product> findBySku(String sku);

    List<Product> findByStatus(String status);

    List<Product> findByStatusAndPriceMinorUnitsGreaterThanEqualOrderByCreatedAtDesc(
            String status,
            long minimumPrice
    );

    List<Product> findTop20ByStatusOrderByCreatedAtDesc(String status);

    boolean existsBySku(String sku);

    long countByStatus(String status);
}
~~~

Các method thể hiện trực tiếp ý định:

- `findBySku`: tìm theo SKU.
- `findByStatus`: tìm tất cả sản phẩm theo trạng thái.
- `findByStatusAndPriceMinorUnitsGreaterThanEqualOrderByCreatedAtDesc`: lọc theo trạng thái và giá tối thiểu, sắp xếp mới nhất trước.
- `findTop20ByStatusOrderByCreatedAtDesc`: giới hạn số kết quả.
- `existsBySku`: kiểm tra sự tồn tại.
- `countByStatus`: đếm số sản phẩm theo trạng thái.

### 2.1. Ưu điểm của derived query

**Ít SQL phải duy trì:** framework tạo câu SQL từ metadata và dialect.

**Tên method thể hiện ý định:** với predicate ngắn, người đọc có thể hiểu ngay điều kiện lọc.

**Tích hợp repository tự nhiên:** dùng kiểu trả về như `Optional<T>`, `List<T>`, `boolean` hoặc kiểu phù hợp khác theo hợp đồng query.

**Giảm phụ thuộc cú pháp database:** framework có thể tạo SQL phù hợp dialect thay vì phải tự viết từng biến thể.

### 2.2. Dấu hiệu derived query không còn phù hợp

Một method name trở nên khó đọc khi:

- Có nhiều điều kiện kết hợp AND/OR.
- Có nhiều nhóm ngoặc logic.
- Tên method dài đến mức người đọc phải phân tích từng từ khóa.
- Truy vấn cần join nhiều bảng hoặc dùng biểu thức SQL.
- Điều kiện chỉ xuất hiện khi một tham số được cung cấp.
- Cần projection hoặc phép tổng hợp phức tạp.
- Có nhiều biến thể sắp xếp hoặc phân trang.

Ví dụ một tên method quá dài:

~~~java
List<Product> findByStatusInAndCategoryIdAndPriceMinorUnitsGreaterThanEqualAndNameContainingIgnoreCaseOrderByCreatedAtDesc(
        Collection<String> statuses,
        Long categoryId,
        long minimumPrice,
        String name
);
~~~

Method vẫn có thể hợp lệ nếu các predicate được hỗ trợ, nhưng khi nhiều nhánh logic tiếp tục xuất hiện, tên method không còn giúp người đọc hiểu truy vấn. Hãy cân nhắc `@Query` hoặc custom implementation.

### 2.3. Derived query có giới hạn theo mô hình JDBC

Spring Data JDBC không phải ORM có thể tự suy luận mọi quan hệ object và tạo join tùy ý. Query derivation phù hợp nhất với thuộc tính được ánh xạ của aggregate root và các predicate mà phiên bản Spring Data JDBC hỗ trợ.

Không giả định rằng tên property lồng nhau, collection child hoặc aggregate reference sẽ luôn được chuyển thành join giống JPA. Khi truy vấn cần dữ liệu từ nhiều bảng hoặc cần điều kiện phức tạp, kiểm tra tài liệu đúng phiên bản; nếu derived query không biểu diễn được, dùng SQL tường minh hoặc custom repository.

### 2.4. Đừng chọn derived query chỉ vì câu SQL ngắn

Một method name dài và khó hiểu không trở nên tốt hơn chỉ vì framework có thể sinh SQL. Hãy đánh giá khả năng người bảo trì hiểu điều kiện nghiệp vụ, số lượng method cần tạo và khả năng mở rộng truy vấn.

## 3. Khi nào chọn @Query?

`@Query` phù hợp với một câu SQL **cố định** mà muốn đặt cạnh method repository. Người viết kiểm soát bảng, cột, join, function và thứ tự kết quả.

Trong Spring Data JDBC, import annotation:

~~~java
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;
~~~

Ví dụ tìm sản phẩm có giá từ một ngưỡng và thuộc một trạng thái:

~~~java
@Query("""
       SELECT id, sku, name, status,
              price_minor_units, created_at
       FROM products
       WHERE status = :status
         AND price_minor_units >= :minimumPrice
       ORDER BY created_at DESC, id DESC
       """)
List<Product> searchByStatusAndMinimumPrice(
        @Param("status") String status,
        @Param("minimumPrice") long minimumPrice
);
~~~

SQL ở đây là SQL của database, không phải JPQL. `products` và `price_minor_units` là tên bảng/cột thật trong schema.

### 3.1. Những trường hợp @Query phát huy tác dụng

- Câu truy vấn cần join bảng khác.
- Cần subquery hoặc CTE.
- Cần function của database.
- Cần tính toán hoặc aggregate như `COUNT`, `SUM`, `MIN`.
- Cần một projection đọc được định nghĩa rõ bằng SQL.
- Cần một câu lệnh cập nhật/xóa cố định.
- Tên derived query sẽ quá dài hoặc không diễn đạt được logic.

Ví dụ join đơn hàng với khách hàng cho màn hình danh sách:

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

Đây là query đọc kết hợp hai aggregate. Kết quả phù hợp với DTO/projection phục vụ màn hình, không nhất thiết là một aggregate `PurchaseOrder` đầy đủ.

### 3.2. Ưu điểm của @Query

**SQL minh bạch:** người đọc nhìn thấy câu lệnh thực tế thay vì phải suy luận từ tên method.

**Kiểm soát chính xác:** dễ chỉ định join, alias, function, thứ tự và biểu thức.

**Đặt cạnh hợp đồng repository:** tên method, tham số và SQL ở cùng một nơi.

**Ít boilerplate:** không cần tạo lớp implementation riêng cho một câu query cố định.

### 3.3. Khi @Query bắt đầu trở nên khó bảo trì

Annotation không phải nơi tốt nhất cho mọi SQL. Cân nhắc chuyển sang custom implementation khi:

- SQL cần được tạo từ nhiều bộ lọc tùy chọn.
- Số nhánh điều kiện tăng theo request.
- Có nhiều whitelist cho sort column hoặc hướng sort.
- Cần mapping kết quả phức tạp qua nhiều loại DTO.
- Cần phối hợp nhiều query hoặc nhiều bước xử lý.
- SQL phải được chọn theo dialect/database.
- Cần tái sử dụng helper tạo predicate hoặc ánh xạ.

Một annotation chứa SQL dài hàng trăm dòng, nhiều điều kiện null và nhiều placeholder tùy chọn có thể khó đọc hơn một implementation Java có cấu trúc.

### 3.4. Named parameter và bảo mật

Luôn bind giá trị qua placeholder:

~~~java
@Query("""
       SELECT id, sku, name, status,
              price_minor_units, created_at
       FROM products
       WHERE sku = :sku
       """)
Optional<Product> findBySku(@Param("sku") String sku);
~~~

Không nối chuỗi đầu vào vào SQL:

~~~java
// Không an toàn:
String sql = "SELECT * FROM products WHERE sku = '" + sku + "'";
~~~

Bind parameter giúp giá trị được xử lý như dữ liệu, giảm nguy cơ SQL injection và tránh lỗi escaping.

Tên bảng, tên cột hoặc từ khóa sort không thể được thay bằng bind parameter theo cách thông thường. Nếu cần lựa chọn động, hãy dùng whitelist các identifier đã biết hoặc tạo câu SQL trong custom implementation từ các hằng số an toàn.

## 4. Khi nào chọn custom repository implementation?

Custom repository implementation phù hợp khi logic truy vấn cần nhiều điều kiện động, nhiều câu SQL, mapping riêng hoặc hành vi không còn gọn trong một annotation.

Spring Data hỗ trợ ghép repository từ các fragment (thành phần mở rộng). Một fragment có interface riêng và implementation tương ứng; repository chính kế thừa fragment đó.

~~~text
ProductRepository
  |
  +-- CrudRepository<Product, Long>
  |
  +-- ProductSearchRepository
          |
          v
    ProductSearchRepositoryImpl
          |
          v
    NamedParameterJdbcTemplate
          |
          v
       Database
~~~

### 4.1. Khai báo fragment interface

~~~java
import java.util.List;

public interface ProductSearchRepository {
    List<ProductSummary> search(ProductSearchCriteria criteria);
}
~~~

Định nghĩa DTO và tiêu chí tìm kiếm:

~~~java
import java.util.List;

public record ProductSummary(
        Long id,
        String sku,
        String name,
        String status,
        long priceMinorUnits
) {
}

public record ProductSearchCriteria(
        List<String> statuses,
        Long categoryId,
        Long minimumPrice,
        String nameContains,
        ProductSort sort,
        int limit
) {
}

public enum ProductSort {
    NEWEST,
    PRICE_ASC,
    PRICE_DESC
}
~~~

`ProductSearchCriteria` gom các điều kiện tùy chọn vào một object, tránh method có quá nhiều tham số. `ProductSort` giới hạn những cách sắp xếp được phép.

### 4.2. Kết hợp fragment vào repository

~~~java
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long>, ProductSearchRepository {

    Optional<Product> findBySku(String sku);
}
~~~

Spring Data repository composition kết hợp CRUD repository và fragment tùy chỉnh. Theo quy ước mặc định, implementation có tên `ProductSearchRepositoryImpl` được ghép với fragment `ProductSearchRepository`. Có thể cấu hình postfix khác, nhưng cần nhất quán với cấu hình repository của dự án.

### 4.3. Cài đặt bằng NamedParameterJdbcTemplate

~~~java
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductSearchRepositoryImpl
        implements ProductSearchRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public ProductSearchRepositoryImpl(
            NamedParameterJdbcTemplate jdbc
    ) {
        this.jdbc = jdbc;
    }

    @Override
    public List<ProductSummary> search(ProductSearchCriteria criteria) {
        if (criteria.limit() <= 0 || criteria.limit() > 200) {
            throw new IllegalArgumentException("limit phải từ 1 đến 200");
        }

        StringBuilder sql = new StringBuilder("""
                SELECT id, sku, name, status, price_minor_units
                FROM products
                WHERE 1 = 1
                """);

        MapSqlParameterSource params = new MapSqlParameterSource();

        if (criteria.statuses() != null && !criteria.statuses().isEmpty()) {
            if (criteria.statuses().stream().anyMatch(value -> value == null)) {
                throw new IllegalArgumentException("status không được null");
            }
            sql.append(" AND status IN (:statuses)");
            params.addValue("statuses", criteria.statuses());
        }

        if (criteria.categoryId() != null) {
            sql.append(" AND category_id = :categoryId");
            params.addValue("categoryId", criteria.categoryId());
        }

        if (criteria.minimumPrice() != null) {
            sql.append(" AND price_minor_units >= :minimumPrice");
            params.addValue("minimumPrice", criteria.minimumPrice());
        }

        if (criteria.nameContains() != null
                && !criteria.nameContains().isBlank()) {
            sql.append(" AND name LIKE :namePattern");
            params.addValue(
                    "namePattern",
                    "%" + criteria.nameContains().trim() + "%"
            );
        }

        String orderBy = switch (criteria.sort() == null
                ? ProductSort.NEWEST : criteria.sort()) {
            case NEWEST -> "created_at DESC, id DESC";
            case PRICE_ASC -> "price_minor_units ASC, id ASC";
            case PRICE_DESC -> "price_minor_units DESC, id DESC";
        };

        sql.append(" ORDER BY ").append(orderBy);
        sql.append(" LIMIT :limit");
        params.addValue("limit", criteria.limit());

        RowMapper<ProductSummary> mapper = (rs, rowNum) ->
                new ProductSummary(
                        rs.getLong("id"),
                        rs.getString("sku"),
                        rs.getString("name"),
                        rs.getString("status"),
                        rs.getLong("price_minor_units")
                );

        return jdbc.query(sql.toString(), params, mapper);
    }
}
~~~

Đây là ví dụ cho một database có cú pháp `LIMIT`. Nếu database mục tiêu dùng cú pháp giới hạn hàng khác, phần cuối câu SQL phải được điều chỉnh theo dialect. Các tên cột như `category_id` và `created_at` phải tồn tại trong schema thực tế.

Một số quyết định quan trọng trong implementation:

- Điều kiện chỉ được thêm khi tham số tương ứng được cung cấp.
- Giá trị đầu vào được bind bằng `MapSqlParameterSource`.
- Danh sách trạng thái rỗng được định nghĩa là **không áp dụng bộ lọc trạng thái** trong ví dụ này. Nếu hợp đồng cần “không chọn trạng thái nghĩa là không có kết quả”, service phải trả list rỗng trước khi gọi fragment.
- Sort được chọn từ enum và ánh xạ sang chuỗi SQL cố định. Không nối trực tiếp giá trị sort do request gửi lên.
- Result set được ánh xạ tường minh vào `ProductSummary`.
- `limit` được kiểm tra giới hạn trước khi bind.

Nếu `nameContains` cần tìm chuỗi theo nghĩa literal, cần escape ký tự wildcard `%` và `_` theo quy tắc `LIKE` của database. Nếu chủ đích cho phép wildcard, phải ghi rõ hợp đồng đó.

### 4.4. Vì sao dùng repository fragment thay vì một class tiện ích bất kỳ?

Fragment giúp:

- Giữ API tìm kiếm cạnh repository mà caller đang dùng.
- Tách phần CRUD chuẩn khỏi truy vấn đặc thù.
- Dễ thay implementation mà không đổi service contract.
- Tiêm dependency JDBC qua constructor.
- Dùng chung transaction và datasource do Spring quản lý.

Không cần tạo một custom implementation chỉ để bọc lại `findById` hoặc `findAll`. Chỉ thêm fragment khi có hành vi thực sự cần triển khai riêng.

## 5. So sánh ba cách trên cùng một bài toán

Giả sử cần tìm sản phẩm theo trạng thái và giá tối thiểu, sắp xếp theo ngày tạo.

### 5.1. Dùng derived query

~~~java
List<Product> findByStatusAndPriceMinorUnitsGreaterThanEqualOrderByCreatedAtDesc(
        String status,
        long minimumPrice
);
~~~

**Phù hợp khi:** chỉ có một trạng thái, một ngưỡng giá và một thứ tự cố định.

**Giới hạn:** nếu có nhiều trạng thái, category tùy chọn, từ khóa tìm kiếm và nhiều kiểu sort, method name sẽ dài và cứng.

### 5.2. Dùng @Query

~~~java
@Query("""
       SELECT id, sku, name, status,
              price_minor_units, created_at
       FROM products
       WHERE status = :status
         AND price_minor_units >= :minimumPrice
       ORDER BY created_at DESC, id DESC
       """)
List<Product> searchByStatusAndMinimumPrice(
        @Param("status") String status,
        @Param("minimumPrice") long minimumPrice
);
~~~

**Phù hợp khi:** SQL cố định, cần đọc rõ cột và điều kiện, không cần dựng câu query từ nhiều nhánh.

**Giới hạn:** SQL không thay đổi theo tham số ngoài các giá trị bind; nếu có nhiều filter tùy chọn, annotation có thể trở nên khó đọc.

### 5.3. Dùng custom fragment

~~~java
List<ProductSummary> search(ProductSearchCriteria criteria);
~~~

**Phù hợp khi:** filter tùy chọn, sort động theo whitelist, projection riêng và giới hạn kết quả được kiểm soát trong code.

**Đánh đổi:** nhiều code hơn, người triển khai chịu trách nhiệm tạo SQL, bind tham số và mapping kết quả.

| Tiêu chí | Derived query | `@Query` | Custom implementation |
| --- | --- | --- | --- |
| Độ phức tạp ban đầu | Thấp | Trung bình | Cao hơn |
| SQL nhìn thấy trực tiếp | Không | Có | Có |
| Điều kiện động | Hạn chế | Thường không thuận tiện | Linh hoạt |
| Join và function đặc thù | Không phải thế mạnh | Phù hợp | Phù hợp |
| Mapping DTO phức tạp | Hạn chế theo contract hỗ trợ | Tùy projection được hỗ trợ | Chủ động với RowMapper |
| Tái sử dụng helper tạo query | Không linh hoạt | Hạn chế | Tốt |
| Phụ thuộc dialect | Thấp hơn | Có thể cao | Có thể cao |
| Boilerplate | Ít | Ít đến vừa | Nhiều hơn |
| Kiểm soát SQL động an toàn | Không cần dựng SQL | Hạn chế | Cần whitelist và bind đúng |

## 6. Chọn theo hình dạng bài toán

| Bài toán | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Tìm một sản phẩm theo SKU duy nhất | Derived query | Tên method ngắn và rõ |
| Lọc theo trạng thái và giá tối thiểu | Derived query | Predicate đơn giản, cố định |
| Lọc theo một điều kiện SQL cố định có function | `@Query` | Câu SQL rõ ràng hơn method name |
| Join order với customer cho DTO | `@Query` hoặc custom fragment | SQL join và result shape được kiểm soát |
| Nhiều filter tùy chọn từ màn hình tìm kiếm | Custom fragment | Thêm/bỏ predicate theo tham số |
| Nhiều lựa chọn sort từ whitelist | Custom fragment | Chọn identifier SQL an toàn bằng enum |
| Truy vấn có CTE/subquery cố định | `@Query` | SQL nằm cạnh repository method |
| Query cần mapping nhiều loại result hoặc xử lý từng row đặc biệt | Custom fragment | Dùng RowMapper tường minh |
| Bulk update cố định theo điều kiện đơn giản | `@Modifying` + `@Query` | SQL ngắn, mục đích rõ |
| Bulk update có nhiều nhánh động | Custom fragment | Dễ kiểm soát điều kiện và affected rows |
| Tải đầy đủ aggregate để thực hiện hành vi miền | Repository method chuẩn | Giữ đúng aggregate mapping và ownership |
| Báo cáo chỉ cần vài cột | Projection/query riêng | Tránh tải toàn bộ aggregate |

### 6.1. Bắt đầu từ hợp đồng dữ liệu

Trước khi chọn công cụ, hãy xác định:

- Kết quả là aggregate root, projection, scalar hay collection?
- Query có thể trả không hàng, một hàng hay nhiều hàng?
- Điều kiện có cố định hay phụ thuộc input tùy chọn?
- Có cần join qua aggregate khác không?
- Có cần giữ invariant của aggregate hay chỉ đọc báo cáo?
- Database nào phải được hỗ trợ?

Một truy vấn có thể rất phức tạp về SQL nhưng kết quả chỉ là một DTO nhỏ. Ngược lại, một truy vấn lọc đơn giản có thể phải trả aggregate lớn và cần đúng cơ chế mapping của repository.

## 7. Tách query đọc khỏi luồng cập nhật aggregate

Không phải mọi truy vấn nên trả về entity để rồi lưu lại. Hãy phân biệt:

**Command/update path:** cần aggregate đầy đủ để kiểm tra invariant và thực hiện hành vi miền. Dùng repository root, gọi domain method và `save`.

**Read/query path:** cần dữ liệu hiển thị hoặc báo cáo. Dùng projection, SQL join hoặc custom query phù hợp.

Ví dụ màn hình danh sách đơn hàng chỉ cần:

- Mã đơn.
- Trạng thái.
- Tên khách hàng.
- Tổng tiền.

Không cần tải toàn bộ `PurchaseOrder` cùng mọi `OrderLine` nếu màn hình không sử dụng chúng. Một DTO query có thể giảm lượng dữ liệu và số lần truy cập.

Ngược lại, use case xác nhận đơn hàng cần kiểm tra tất cả dòng hàng và trạng thái. Không nên dùng một projection mỏng để thay thế aggregate trong thao tác cập nhật.

## 8. Dùng @Modifying cho SQL thay đổi cố định

Nếu câu lệnh update/delete đơn giản và cố định, có thể dùng `@Query` kết hợp `@Modifying`:

~~~java
import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Modifying
@Query("""
       UPDATE products
       SET status = :newStatus
       WHERE id = :id
       """)
int updateStatus(
        @Param("id") Long id,
        @Param("newStatus") String newStatus
);
~~~

Phương thức trả số hàng bị ảnh hưởng để caller có thể xác định ID có khớp hay không. Nếu có version, bulk SQL không tự động thực hiện optimistic locking như thao tác save aggregate. Cần đưa version vào điều kiện và cập nhật có chủ đích nếu muốn phát hiện xung đột.

Nếu câu update có nhiều nhánh điều kiện động, cần phối hợp nhiều câu lệnh hoặc custom mapping, hãy chuyển sang fragment. Không dùng bulk update để bỏ qua invariant của domain model.

## 9. Transaction và datasource trong custom implementation

Một custom repository fragment dùng `NamedParameterJdbcTemplate` hoặc `JdbcClient` có thể tham gia transaction Spring khi sử dụng cùng `DataSource` và transaction manager mà ứng dụng cấu hình.

Ví dụ:

~~~java
@Service
public class ProductSearchService {
    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<ProductSummary> search(ProductSearchCriteria criteria) {
        return repository.search(criteria);
    }
}
~~~

`@Transactional(readOnly = true)` thể hiện use case chỉ đọc. Với use case cập nhật nhiều thao tác, đặt transaction ở service boundary để các thao tác cùng tham gia transaction theo cấu hình.

Trong custom implementation:

- Tiêm template do Spring cấu hình qua constructor.
- Dùng cùng datasource với repository.
- Không tự tạo connection bằng `DriverManager.getConnection`.
- Không tự tạo `DataSource` mới chỉ cho một query.
- Đóng tài nguyên đúng cách nếu sử dụng JDBC cấp thấp trực tiếp.

Các template Spring JDBC quản lý việc lấy/trả connection theo cơ chế transaction-aware của Spring. Nếu tự tạo connection ngoài cơ chế đó, thao tác có thể không tham gia transaction đang mở.

### 9.1. Transaction không biến nhiều database thành một

Nếu custom fragment gọi một database khác hoặc một service HTTP, `@Transactional` cục bộ không tự tạo distributed transaction. Khi phải phối hợp nhiều hệ thống, cần thiết kế outbox, saga hoặc cơ chế đồng bộ phù hợp.

## 10. Tính portable giữa các database

Derived query thường giúp giảm việc tự viết SQL theo dialect. Với `@Query` và custom fragment, người viết chịu trách nhiệm về cú pháp database.

Các khác biệt thường gặp:

| Nhu cầu | Điểm có thể khác nhau |
| --- | --- |
| Giới hạn số hàng | `LIMIT/OFFSET`, `FETCH FIRST`, `OFFSET ... FETCH` |
| Upsert | `ON CONFLICT`, `MERGE` hoặc cú pháp riêng |
| Sinh ID | Identity, sequence hoặc cơ chế riêng |
| JSON | Kiểu dữ liệu, operator và function |
| Ghép chuỗi | `||` hoặc `CONCAT` |
| Ngày giờ | Function, timezone và kiểu timestamp |
| Cập nhật có khóa | Cú pháp locking và isolation behavior |

Nếu chỉ hỗ trợ một database, dùng cú pháp đặc thù có thể là lựa chọn hợp lý. Nếu phải hỗ trợ nhiều database:

- Ưu tiên derived query khi biểu đạt đủ ý định.
- Dùng phần SQL chung khi có thể.
- Tách custom implementation theo dialect khi khác biệt thực sự cần thiết.
- Chạy integration test trên từng database mục tiêu.

Không khẳng định query portable chỉ vì nó chạy trên H2. Test nên dùng database production hoặc Testcontainers với đúng image/phiên bản.

## 11. Bảo mật khi xây dựng truy vấn

Dù chọn phương án nào, dữ liệu từ request phải được xử lý như input không đáng tin cậy.

### 11.1. Bind giá trị

Với derived query, framework xử lý tham số theo cơ chế bind.

Với `@Query`:

~~~java
@Query("SELECT * FROM products WHERE sku = :sku")
Optional<Product> findBySku(@Param("sku") String sku);
~~~

Với custom fragment:

~~~java
jdbc.query(
        "SELECT * FROM products WHERE sku = :sku",
        new MapSqlParameterSource("sku", sku),
        rowMapper
);
~~~

Không nối trực tiếp giá trị vào SQL.

### 11.2. Whitelist identifier động

Sort column và tên bảng không thể bind như một giá trị. Dùng enum hoặc switch:

~~~java
String orderBy = switch (sort) {
    case NEWEST -> "created_at DESC";
    case PRICE_ASC -> "price_minor_units ASC";
    case PRICE_DESC -> "price_minor_units DESC";
};
~~~

Chỉ nối chuỗi lấy từ tập hằng số đã kiểm soát. Không viết:

~~~java
sql.append(" ORDER BY ").append(request.sortBy());
~~~

nếu `request.sortBy()` đến trực tiếp từ input bên ngoài.

### 11.3. Kiểm soát tập tham số

Với điều kiện `IN`/`NOT IN`:

- Kiểm tra collection null.
- Quy định collection rỗng có nghĩa gì.
- Kiểm tra phần tử null.
- Giới hạn số lượng phần tử.
- Dùng bind parameters thay vì ghép giá trị.

Không để một collection rỗng tạo SQL không hợp lệ hoặc làm thay đổi semantics ngoài ý muốn.

## 12. Hiệu năng: lựa chọn API không thay thế việc đo SQL

Derived query, `@Query` hay custom fragment không tự quyết định truy vấn nào nhanh hơn. Hiệu năng phụ thuộc:

- SQL được tạo.
- Index và execution plan.
- Số hàng phải đọc.
- Kích thước dữ liệu trả về.
- Số lần round-trip.
- Mapping và allocation trong JVM.
- Thời gian chờ connection pool.
- Transaction/isolation và lock contention.

### 12.1. Khi derived query đủ tốt

Một query theo ID hoặc trạng thái đơn giản có thể tạo SQL hiệu quả và dùng index phù hợp. Không cần chuyển sang custom SQL chỉ để “tối ưu” khi chưa có bằng chứng.

### 12.2. Khi @Query giúp kiểm soát hiệu năng

SQL tường minh cho phép chỉ lấy cột cần thiết, dùng join/subquery và biểu thức phù hợp. Projection giúp tránh materialize aggregate lớn nếu use case chỉ cần vài cột.

### 12.3. Khi custom implementation cần thiết

Custom fragment cho phép dựng điều kiện động để database chỉ nhận những predicate cần thiết, thay vì một câu SQL khổng lồ với nhiều nhánh tùy chọn. Tuy nhiên, query builder tự viết cũng có thể tạo SQL kém hiệu quả; hãy đo execution plan và số row.

## 13. Các dấu hiệu nên chuyển từ cách này sang cách khác

| Dấu hiệu hiện tại | Nên cân nhắc |
| --- | --- |
| Derived method dài, có nhiều nhóm AND/OR khó hiểu | `@Query` hoặc custom fragment |
| Derived method chỉ lọc property đơn giản, tên ngắn | Giữ derived query |
| SQL cố định, đọc rõ và ít thay đổi | `@Query` |
| @Query có nhiều predicate tùy chọn và placeholder phức tạp | Custom fragment |
| @Query dài, nhiều phép tính và mapping DTO riêng | Custom fragment |
| Custom implementation chỉ chứa một SELECT đơn giản | Có thể quay lại `@Query` hoặc derived query |
| Nhiều method custom lặp lại cùng logic tạo predicate | Tách helper/query component trong custom layer |
| Custom code tự tạo connection và quản lý transaction thủ công | Chuyển sang template Spring được quản lý |
| Query cần full aggregate nhưng đang map thủ công từng child | Cân nhắc repository root chuẩn |
| Màn hình chỉ cần một vài cột nhưng đang tải full aggregate | Projection hoặc read query riêng |

Không nên chuyển đổi chỉ vì sở thích cá nhân. Hãy chuyển khi cách hiện tại làm ý định khó hiểu, logic khó mở rộng, SQL khó kiểm soát hoặc mapping không còn phù hợp.

## 14. Kiểm thử theo lựa chọn truy vấn

Mỗi kiểu truy vấn cần kiểm thử những điều riêng.

### 14.1. Derived query

Kiểm tra:

- Property path đúng với tên field.
- Predicate đúng với dữ liệu biên.
- Kết quả rỗng và cardinality.
- Sort/limit nếu có.
- Nullability của thuộc tính.

### 14.2. @Query

Kiểm tra:

- Tên bảng/cột đúng schema.
- Bind parameter đúng tên và kiểu.
- Alias ánh xạ đúng property/DTO.
- SQL chạy trên dialect production.
- Không hàng, một hàng, nhiều hàng.
- Projection chỉ nhận các cột đã chọn.
- Câu lệnh update/delete trả số hàng bị ảnh hưởng đúng.

### 14.3. Custom repository

Kiểm tra:

- Mỗi filter tùy chọn được thêm/bỏ đúng.
- Input null và collection rỗng theo đúng contract.
- Sort chỉ nhận giá trị whitelist.
- Limit/page size bị giới hạn.
- Mapping ResultSet đúng kiểu và nullability.
- Template dùng đúng datasource/transaction.
- SQL không bị injection khi input chứa ký tự đặc biệt.

Ví dụ kiểm thử integration:

~~~java
@DataJdbcTest
class ProductRepositoryTest {

    @Autowired
    ProductRepository repository;

    @Test
    void searchesUsingOptionalCriteria() {
        ProductSearchCriteria criteria = new ProductSearchCriteria(
                List.of("ACTIVE", "PENDING"),
                10L,
                100_000L,
                "book",
                ProductSort.NEWEST,
                20
        );

        List<ProductSummary> results = repository.search(criteria);

        assertThat(results).allSatisfy(product -> {
            assertThat(product.priceMinorUnits())
                    .isGreaterThanOrEqualTo(100_000L);
        });
    }
}
~~~

Đây là khung minh họa; cần chuẩn bị schema và dữ liệu test theo dự án, đồng thời kiểm tra cấu hình test có scan fragment implementation. Nếu SQL dùng cú pháp vendor-specific, chạy test trên database tương ứng thay vì chỉ dựa vào H2.

## 15. Những lỗi thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Dùng derived query cho logic quá phức tạp | Tên method dài và khó hiểu | Chuyển sang `@Query` hoặc custom fragment |
| Dùng @Query cho mọi truy vấn nhỏ | SQL lặp lại và tăng chi phí bảo trì | Ưu tiên derived query khi tên method rõ |
| Đưa SQL động dài vào annotation | Khó kiểm soát nhánh điều kiện | Dùng custom implementation |
| Nghĩ @Query là JPQL | Viết sai tên bảng/cột | Dùng SQL theo schema database |
| Nối input vào SQL | SQL injection | Bind parameter |
| Bind tên cột/sort bằng placeholder | Database không hiểu identifier như giá trị | Whitelist identifier |
| Custom fragment tự mở connection | Có thể không tham gia transaction Spring | Tiêm JdbcClient/JdbcTemplate dùng chung DataSource |
| Dùng projection cho thao tác cần invariant | Thiếu trạng thái aggregate | Tải aggregate root đầy đủ |
| Tải full aggregate cho báo cáo nhỏ | Đọc thừa dữ liệu | Projection/read query |
| Bulk update bỏ qua @Version | Có thể ghi đè cập nhật đồng thời | Tự quản lý optimistic locking hoặc dùng repository save |
| Chỉ test bằng H2 | Không phát hiện khác biệt dialect | Test với database mục tiêu |
| Tạo custom implementation chỉ để bọc CRUD | Thêm lớp không mang giá trị | Dùng repository method có sẵn |

## 16. Quy trình chọn cách triển khai

Khi bắt đầu một truy vấn mới, thực hiện theo thứ tự:

1. **Xác định mục đích:** đọc aggregate, đọc projection, đếm, kiểm tra tồn tại hay thay đổi dữ liệu?
2. **Xác định kết quả:** một hàng, nhiều hàng, scalar hay DTO?
3. **Đánh giá predicate:** đơn giản và cố định hay có nhiều điều kiện tùy chọn?
4. **Kiểm tra aggregate boundary:** query có cần dữ liệu thuộc root hay join qua aggregate độc lập?
5. **Chọn cách ít phức tạp nhất vẫn rõ ràng:** derived query cho predicate đơn giản; `@Query` cho SQL cố định; custom fragment cho logic động hoặc mapping đặc biệt.
6. **Thiết kế parameter binding:** không nối input vào SQL; whitelist identifier động.
7. **Đặt transaction:** xác định service boundary và datasource dùng chung.
8. **Kiểm thử dialect:** kiểm tra SQL, mapping, cardinality và trường hợp rỗng.
9. **Đo hiệu năng:** xem execution plan, index, số row và thời gian thực tế.
10. **Chuyển cách triển khai khi có lý do:** không giữ một query method phức tạp chỉ vì nó đã tồn tại.

## Ghi nhớ

Hãy chọn truy vấn theo độ phức tạp thực tế của bài toán. **Derived query** phù hợp với điều kiện đơn giản, cố định và dễ diễn đạt bằng tên method. **`@Query`** phù hợp với SQL cố định cần kiểm soát bảng, cột, join hoặc function. **Custom repository implementation** phù hợp với điều kiện động, query phức tạp, mapping đặc biệt hoặc nhiều bước xử lý.

Ba cách có thể cùng tồn tại trong một repository. Giữ CRUD và hành vi aggregate qua repository root; dùng SQL/projection riêng cho nhu cầu đọc; dùng custom fragment khi annotation không còn diễn đạt rõ. Dù chọn cách nào, luôn bind giá trị an toàn, kiểm soát identifier động, dùng datasource do Spring quản lý, đặt transaction đúng ranh giới và kiểm thử trên database mục tiêu.
