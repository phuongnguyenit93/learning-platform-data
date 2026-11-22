# Xóa mềm, lọc dữ liệu và tính duy nhất sau khi xóa trong Hibernate

Xóa mềm (soft delete) đánh dấu một bản ghi là đã bị xóa thay vì xóa vật lý khỏi database. Bản ghi vẫn tồn tại để phục vụ khôi phục, kiểm toán hoặc đối chiếu lịch sử, nhưng các truy vấn nghiệp vụ thông thường phải ẩn nó khỏi kết quả.

Khi triển khai xóa mềm, có ba vấn đề cần giải quyết đồng thời:

1. **Xóa:** thao tác delete của ứng dụng phải cập nhật trạng thái xóa thay vì phát lệnh DELETE vật lý.
2. **Lọc:** truy vấn thông thường phải loại bản ghi đã xóa; màn hình quản trị có thể cần xem hoặc khôi phục chúng.
3. **Tính duy nhất:** sau khi một bản ghi bị xóa mềm, khóa nghiệp vụ như SKU, email hoặc username có được phép dùng lại hay không?

Chỉ thêm cột deleted rồi lọc ở một vài repository method là chưa đủ. Một truy vấn bị quên điều kiện có thể làm dữ liệu đã xóa xuất hiện trở lại. Một unique constraint thông thường có thể ngăn tạo bản ghi mới dù bản ghi cũ đã bị xóa mềm. Ngược lại, bỏ unique constraint để cho phép dùng lại khóa có thể tạo ra hai bản ghi đang hoạt động trùng nhau nếu không có ràng buộc phù hợp ở database.

Bài học này trình bày các lựa chọn Hibernate, cách lọc dữ liệu, quy tắc khôi phục, unique index theo từng hệ quản trị, tác động tới quan hệ và bulk query, cùng cách kiểm thử trên database thật.

## 1. Xóa vật lý và xóa mềm

Xóa vật lý dùng SQL DELETE để loại bỏ hàng khỏi bảng:

~~~sql
DELETE FROM products WHERE id = 42;
~~~

Sau khi transaction commit, hàng không còn trong bảng. Nếu không có bản sao lưu hoặc audit riêng, việc khôi phục có thể khó khăn.

Xóa mềm dùng UPDATE để đánh dấu:

~~~sql
UPDATE products
SET deleted = true,
    deleted_at = CURRENT_TIMESTAMP
WHERE id = 42;
~~~

Hàng vẫn tồn tại nhưng được coi là không còn hoạt động. Truy vấn thông thường phải lọc:

~~~sql
SELECT *
FROM products
WHERE deleted = false;
~~~

Một thiết kế khác dùng deleted_at:

- deleted_at IS NULL: bản ghi đang hoạt động.
- deleted_at IS NOT NULL: bản ghi đã bị xóa mềm.

Cột timestamp lưu được thời điểm xóa và thường hữu ích cho audit. Cột boolean đơn giản hơn nếu chỉ cần trạng thái. Có thể dùng cả hai để truy vấn trạng thái nhanh và lưu thời điểm.

Xóa mềm không thay thế backup, audit log hoặc chính sách lưu trữ. Nó chỉ giữ hàng trong bảng nghiệp vụ và thay đổi cách ứng dụng nhìn nhận hàng đó.

## 2. Xác định chính sách nghiệp vụ trước khi chọn mapping

Trước khi viết annotation, hãy xác định:

- Ai được xóa mềm?
- Có được khôi phục không?
- Người dùng thông thường có được xem bản ghi đã xóa không?
- Khóa nghiệp vụ có được dùng lại sau khi xóa không?
- Nếu khôi phục nhưng khóa đã được bản ghi khác sử dụng thì xử lý thế nào?
- Có cần lưu người xóa, lý do xóa và thời điểm xóa không?
- Xóa cha có xóa mềm các con không?
- Có cần xóa vật lý sau thời hạn lưu trữ không?
- Các writer ngoài ứng dụng có cập nhật trực tiếp bảng không?

Không có một chính sách đúng cho mọi domain. Ví dụ username có thể được giữ lại vĩnh viễn để tránh chiếm đoạt danh tính; SKU của một mặt hàng đã ngừng kinh doanh có thể được tái sử dụng theo quy định; mã hóa đơn thường không nên tái sử dụng vì cần giữ tính duy nhất lịch sử.

Chính sách về uniqueness phải được quyết định trước khi tạo index. Nếu không, hệ thống có thể triển khai soft delete thành công nhưng không thể tạo lại bản ghi có cùng khóa nghiệp vụ.

## 3. Mô hình dữ liệu ví dụ

Ví dụ dùng Product với SKU là khóa nghiệp vụ. Bản ghi đã xóa mềm không xuất hiện trong danh sách sản phẩm đang bán. Ta dùng boolean deleted và timestamp deleted_at cho biến thể mapping thủ công.

~~~java
package com.example.product;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 80)
    private String sku;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(nullable = false)
    private boolean deleted;

    private Instant deletedAt;

    protected Product() {
    }

    public Product(String sku, String name) {
        this.sku = sku;
        this.name = name;
        this.deleted = false;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public boolean isDeleted() {
        return deleted;
    }

    public Instant getDeletedAt() {
        return deletedAt;
    }
}
~~~

Không khai báo unique = true trên SKU trong ví dụ này vì chính sách mong muốn là SKU được dùng lại sau khi bản ghi cũ bị xóa mềm. Unique index phù hợp sẽ được tạo riêng ở database để chỉ áp dụng cho các hàng đang hoạt động.

Trong production, nên quản lý schema bằng migration như Flyway hoặc Liquibase. Không dựa vào hibernate.ddl-auto=update để tạo filtered/partial index vì cú pháp và khả năng hỗ trợ phụ thuộc database.

## 4. Hibernate @SoftDelete

Từ Hibernate ORM 6.4, có thể dùng annotation @SoftDelete để khai báo soft delete ở cấp entity. Hibernate tự chuyển thao tác remove thành cập nhật cột chỉ thị xóa và tự áp dụng điều kiện loại bản ghi đã xóa khi tải entity qua ORM.

Ví dụ:

~~~java
package com.example.product;

import java.math.BigDecimal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import org.hibernate.annotations.SoftDelete;
import org.hibernate.annotations.SoftDeleteType;

@Entity
@Table(name = "catalog_products")
@SoftDelete(
    strategy = SoftDeleteType.DELETED,
    columnName = "deleted"
)
public class CatalogProduct {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 80)
    private String sku;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal price;

    protected CatalogProduct() {
    }

    public CatalogProduct(String sku, String name, BigDecimal price) {
        this.sku = sku;
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

Với strategy DELETED, giá trị chỉ thị biểu diễn bản ghi đã bị xóa; mặc định tên cột chỉ thị của Hibernate là deleted nếu không cấu hình tên khác. Ví dụ trên đặt rõ columnName để schema dễ đọc.

Hibernate @SoftDelete là tính năng riêng của Hibernate, không phải annotation chuẩn Jakarta Persistence. Dự án phải dùng Hibernate ORM 6.4 trở lên và import org.hibernate.annotations.SoftDelete cùng SoftDeleteType. Kiểm tra đúng phiên bản dependency trước khi sao chép ví dụ.

Với mapping này, gọi EntityManager.remove(entity) hoặc repository.delete(entity) sẽ đi qua cơ chế soft delete của Hibernate thay vì xóa hàng vật lý theo hành vi mặc định. Các truy vấn entity thông thường của Hibernate tự loại hàng đã bị đánh dấu xóa theo mapping.

Không thêm một thuộc tính boolean deleted độc lập rồi kỳ vọng nó tự đồng bộ với @SoftDelete nếu chưa cấu hình mapping phù hợp. Annotation quản lý indicator column; hãy chọn rõ cách truy cập trạng thái và cách đọc bản ghi đã xóa.

## 5. SoftDeleteType.DELETED và ACTIVE

Hibernate cung cấp hai cách diễn giải indicator:

- DELETED: giá trị true biểu thị bản ghi đã xóa.
- ACTIVE: giá trị true biểu thị bản ghi đang hoạt động.

Ví dụ ACTIVE:

~~~java
@SoftDelete(
    strategy = SoftDeleteType.ACTIVE,
    columnName = "active"
)
@Entity
@Table(name = "catalog_products")
public class CatalogProduct {
    // Các thuộc tính entity.
}
~~~

Với ACTIVE, Hibernate ghi trạng thái chỉ thị theo nghĩa active. Đọc schema và migration phải thống nhất cách diễn giải; không đặt tên cột active nhưng lại viết index predicate theo nghĩa deleted.

Nên chọn một quy ước duy nhất trong toàn bộ ứng dụng. Với cột deleted, strategy DELETED thường dễ đọc hơn: false là còn hoạt động, true là đã xóa.

## 6. Mapping thủ công với @SQLDelete và @SQLRestriction

Trước Hibernate 6.4 hoặc khi cần kiểm soát SQL cụ thể, có thể dùng @SQLDelete để thay câu DELETE bằng UPDATE, và @SQLRestriction để thêm điều kiện lọc tĩnh.

~~~java
package com.example.product;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import org.hibernate.annotations.SQLDelete;
import org.hibernate.annotations.SQLRestriction;

@Entity
@Table(name = "products")
@SQLDelete(
    sql = """
          UPDATE products
          SET deleted = true,
              deleted_at = CURRENT_TIMESTAMP
          WHERE id = ?
          """
)
@SQLRestriction("deleted = false")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 80)
    private String sku;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(nullable = false)
    private boolean deleted;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    protected Product() {
    }

    public Product(String sku, String name) {
        this.sku = sku;
        this.name = name;
        this.deleted = false;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public boolean isDeleted() {
        return deleted;
    }

    public Instant getDeletedAt() {
        return deletedAt;
    }
}
~~~

Hai annotation có vai trò khác nhau:

- @SQLDelete thay SQL mà Hibernate phát ra khi xóa entity.
- @SQLRestriction thêm điều kiện SQL cố định vào truy vấn tải entity/collection tương ứng.

@SQLRestriction dùng SQL fragment theo tên cột vật lý, ở ví dụ là deleted. Nó không phải JPQL và không dùng tên property Java nếu tên cột khác nhau.

Ví dụ trên không có @Version. Nếu entity dùng optimistic locking với version column, SQL tùy chỉnh phải nhận đúng các bind parameter mà Hibernate truyền theo mapping, bao gồm version theo thứ tự được provider yêu cầu. Cần kiểm tra SQL của đúng phiên bản Hibernate và kiểm thử row-count/optimistic-lock behavior; không sao chép nguyên câu SQL không có version vào entity có @Version.

Trong Hibernate mới, @Where cũ đã được thay thế/đánh dấu deprecated trong các phiên bản gần đây; ưu tiên @SQLRestriction khi phiên bản hỗ trợ. Với Hibernate cũ, kiểm tra API tương ứng của version dự án.

## 7. Chọn @SoftDelete hay mapping thủ công?

| Tiêu chí | @SoftDelete | @SQLDelete + @SQLRestriction |
|---|---|---|
| Phiên bản | Hibernate ORM 6.4+ | Có từ các phiên bản Hibernate trước |
| Cấu hình | Gọn, theo indicator column | Phải tự viết SQL xóa và restriction |
| SQL xóa | Hibernate quản lý | Ứng dụng khai báo SQL cụ thể |
| Lọc bản ghi đã xóa | Hibernate tích hợp với soft-delete mapping | Restriction tĩnh được thêm vào truy vấn |
| Thời điểm xóa | Indicator do Hibernate quản lý | Có thể tự cập nhật timestamp/audit column |
| Kiểm soát SQL | Ít chi tiết hơn | Kiểm soát câu UPDATE cụ thể |
| Rủi ro | Phụ thuộc phiên bản Hibernate | Sai placeholder, version hoặc row-count trong SQL tùy chỉnh |

Nếu dự án dùng Hibernate 6.4+, @SoftDelete thường là lựa chọn đơn giản để bắt đầu. Nếu cần SQL tùy chỉnh, timestamp hoặc đang dùng phiên bản cũ, có thể chọn @SQLDelete và restriction.

Không gắn cả hai chiến lược lên cùng một entity nếu chưa hiểu rõ tương tác. Chọn một cơ chế soft delete làm nguồn sự thật cho indicator column.

## 8. @SQLRestriction là bộ lọc tĩnh

@SQLRestriction luôn thêm điều kiện vào truy vấn ORM tương ứng. Với:

~~~java
@SQLRestriction("deleted = false")
~~~

truy vấn đọc Product thông thường sẽ loại hàng có deleted = true.

Đặc điểm quan trọng:

- Restriction không có tham số bật/tắt.
- Không thể tạm thời disable restriction như một Hibernate filter.
- Nó không tự thêm điều kiện vào mọi SQL do ứng dụng tự viết.
- Native SQL, JDBC, stored procedure và truy vấn từ ứng dụng khác phải tự tuân thủ chính sách.
- Một truy vấn quản trị cần xem cả bản ghi đã xóa phải dùng đường truy cập riêng được kiểm soát.

Đây là lựa chọn tốt khi hầu hết mọi thao tác ORM đều phải ẩn bản ghi đã xóa và không cần bật/tắt bộ lọc trong cùng persistence context.

Nếu có use case khôi phục hoặc audit cần đọc bản ghi đã xóa, hãy thiết kế đường truy cập quản trị rõ ràng. Đừng cố bỏ restriction bằng cách sửa SQL tùy tiện ở một endpoint thông thường.

## 9. Dùng @Filter khi cần bật/tắt lọc động

Hibernate @Filter cho phép áp dụng điều kiện có tham số và bật/tắt theo Session. Nó phù hợp khi cùng một ứng dụng có luồng người dùng thông thường chỉ xem bản ghi hoạt động và luồng quản trị được phép xem cả bản ghi đã xóa.

Ví dụ:

~~~java
package com.example.product;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import org.hibernate.annotations.Filter;
import org.hibernate.annotations.FilterDef;
import org.hibernate.annotations.ParamDef;

@Entity
@Table(name = "products")
@FilterDef(
    name = "productVisibility",
    parameters = @ParamDef(name = "includeDeleted", type = Boolean.class),
    applyToLoadByKey = true
)
@Filter(
    name = "productVisibility",
    condition = "deleted = false or :includeDeleted = true"
)
public class FilteredProduct {
    @Id
    private Long id;

    // Các thuộc tính còn lại.
}
~~~

Bật filter trong transaction:

~~~java
import org.hibernate.Session;

Session session = entityManager.unwrap(Session.class);

session.enableFilter("productVisibility")
        .setParameter("includeDeleted", false);
~~~

Luồng quản trị có thể bật includeDeleted = true trong một Session riêng được giới hạn quyền. Filter là tính năng Hibernate; applyToLoadByKey có ở các phiên bản Hibernate hỗ trợ thuộc tính này. Nếu phiên bản dự án không có thuộc tính đó, bỏ thuộc tính và kiểm tra riêng hành vi load theo identifier.

Không dựa vào filter làm ranh giới bảo mật duy nhất. Hãy kiểm tra cả findById, getReference, association loading, query JPQL, native SQL và các đường truy cập quản trị. Nếu filter không được bật trong Session mới, truy vấn có thể không có điều kiện như dự kiến.

Không dùng đồng thời @SQLRestriction deleted=false và @Filter có includeDeleted=true trên cùng entity với kỳ vọng filter có thể mở lại bản ghi; restriction tĩnh vẫn luôn áp dụng. Chọn restriction tĩnh hoặc filter động theo nhu cầu.

## 10. Lọc thủ công ở tầng repository

Một cách đơn giản là ánh xạ deleted thành property và thêm điều kiện vào từng method:

~~~java
public interface ProductRepository extends JpaRepository<Product, Long> {

    Optional<Product> findBySkuAndDeletedFalse(String sku);

    List<Product> findAllByDeletedFalse();

    boolean existsBySkuAndDeletedFalse(String sku);
}
~~~

Cách này dễ hiểu nhưng dễ bị bỏ sót khi repository có nhiều method. Một method findById kế thừa từ JpaRepository không tự động thêm DeletedFalse nếu không có Hibernate restriction/filter.

Nếu dùng lọc thủ công, hãy tạo convention rõ ràng, review mọi method mới và tránh để controller gọi JpaRepository trực tiếp. Đặt truy vấn qua service/repository chuyên biệt để một nơi chịu trách nhiệm áp dụng điều kiện active.

Không nên cho rằng chỉ cần đổi tên method thành findActive... là mọi truy vấn đã an toàn. Kiểm tra SQL và test từng đường đọc.

## 11. Repository method xóa mềm và khôi phục

Với mapping thủ công có property deleted, có thể tạo method explicit update:

~~~java
package com.example.product;

import java.time.Instant;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Optional<Product> findBySkuAndDeletedFalse(String sku);

    boolean existsBySkuAndDeletedFalse(String sku);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Transactional
    @Query("""
           update Product p
           set p.deleted = true,
               p.deletedAt = :deletedAt
           where p.id = :id
             and p.deleted = false
           """)
    int markDeleted(
            @Param("id") Long id,
            @Param("deletedAt") Instant deletedAt);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Transactional
    @Query("""
           update Product p
           set p.deleted = false,
               p.deletedAt = null
           where p.id = :id
             and p.deleted = true
           """)
    int restore(
            @Param("id") Long id);
}
~~~

Đây là cách update trực tiếp property deleted, không phụ thuộc @SQLDelete. Chỉ dùng method markDeleted/restore nếu entity được ánh xạ với deleted và deletedAt như ví dụ thủ công.

Nếu entity dùng @SQLRestriction deleted=false, truy vấn JPQL update có thể chịu ảnh hưởng của restriction tùy Hibernate/provider và query type. Hãy kiểm tra SQL sinh ra. Một đường restore ổn định có thể dùng native UPDATE theo ID hoặc một repository quản trị riêng không bị restriction, sau khi xác minh unique constraint.

Bulk update không đồng bộ trạng thái các entity đang managed trong persistence context. clearAutomatically=true giúp xóa persistence context sau update; flushAutomatically=true đồng bộ thay đổi đang chờ trước khi chạy bulk query. Dùng chúng có chủ đích vì clear có thể detach các entity khác trong cùng context.

## 12. Không phải mọi DELETE đều đi qua cùng một cơ chế

Cần phân biệt:

- EntityManager.remove(entity): thao tác remove một entity managed.
- JpaRepository.delete(entity): thường chuyển sang thao tác remove qua EntityManager.
- JpaRepository.deleteById(id): triển khai Spring Data thường tìm entity rồi xóa entity đó.
- Bulk JPQL DELETE với @Modifying: chạy bulk statement trực tiếp, không tải và remove từng entity.
- Native SQL DELETE/JDBC/stored procedure: đi thẳng xuống database.

@SoftDelete và @SQLDelete được thiết kế quanh cơ chế xóa entity của Hibernate. Không giả định bulk JPQL DELETE, native DELETE hoặc SQL từ bên ngoài tự động chuyển thành soft delete giống entity.remove().

Nếu cần xóa hàng loạt bằng soft delete, hãy viết UPDATE tường minh:

~~~java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Transactional
@Query("""
       update Product p
       set p.deleted = true,
           p.deletedAt = :now
       where p.deleted = false
         and p.id in :ids
       """)
int softDeleteAllByIds(
        @Param("ids") Collection<Long> ids,
        @Param("now") Instant now);
~~~

Đoạn này yêu cầu mapping thủ công có deleted/deletedAt. Nếu dùng @SoftDelete với indicator do Hibernate quản lý, không giả định property deleted tồn tại trong JPQL; dùng API/SQL được hỗ trợ và kiểm thử theo phiên bản Hibernate.

Không gọi deleteAllInBatch hoặc viết DELETE native nếu yêu cầu nghiệp vụ là giữ lại hàng đã xóa. Test SQL thực tế để xác nhận database nhận UPDATE hay DELETE.

## 13. Unique constraint thông thường vẫn giữ khóa sau khi xóa mềm

Giả sử database có:

~~~sql
ALTER TABLE products
ADD CONSTRAINT uk_products_sku UNIQUE (sku);
~~~

Sau khi Product SKU-100 bị soft delete, hàng vẫn còn trong bảng. Khi tạo Product mới cùng SKU-100, unique constraint vẫn nhìn thấy hàng cũ và từ chối INSERT.

Điều này đúng theo semantics của unique constraint. Database không biết rằng ứng dụng coi hàng đó là đã xóa, trừ khi điều kiện uniqueness được thiết kế để chỉ áp dụng cho hàng hoạt động.

Không bỏ unique constraint rồi chỉ kiểm tra bằng code:

~~~java
if (!repository.existsBySkuAndDeletedFalse(sku)) {
    repository.save(new Product(sku, name));
}
~~~

Hai transaction đồng thời có thể cùng kiểm tra không tồn tại rồi cùng INSERT. Kiểm tra trước chỉ cải thiện thông báo; database constraint mới là hàng rào cuối cùng bảo vệ tính duy nhất.

## 14. Unique index chỉ áp dụng cho bản ghi đang hoạt động

Nếu SKU được phép dùng lại sau khi xóa, cần unique index có điều kiện:

- Các hàng deleted = false phải có SKU duy nhất.
- Các hàng deleted = true không tham gia unique constraint đó.

Cách triển khai phụ thuộc database. Không có một câu DDL portable cho mọi hệ quản trị.

### PostgreSQL: partial unique index

~~~sql
CREATE UNIQUE INDEX uq_products_active_sku
ON products (sku)
WHERE deleted = false;
~~~

Chỉ hàng có deleted=false tham gia index. Nhiều hàng đã xóa có thể giữ cùng SKU, trong khi các hàng đang hoạt động vẫn duy nhất.

Nếu SKU duy nhất theo tenant:

~~~sql
CREATE UNIQUE INDEX uq_products_active_tenant_sku
ON products (tenant_id, sku)
WHERE deleted = false;
~~~

### SQL Server: filtered unique index

~~~sql
CREATE UNIQUE INDEX uq_products_active_sku
ON dbo.products (sku)
WHERE deleted = 0;
~~~

Điều kiện lọc chỉ bao gồm hàng đang hoạt động. Cú pháp boolean/bit và schema phụ thuộc thiết kế SQL Server.

### MySQL: generated column và unique index

MySQL không cung cấp partial index với cú pháp WHERE giống PostgreSQL. Có thể tạo generated column trả SKU khi hàng đang hoạt động và NULL khi đã xóa:

~~~sql
ALTER TABLE products
ADD COLUMN active_sku VARCHAR(80)
GENERATED ALWAYS AS (
    CASE WHEN deleted = 0 THEN sku ELSE NULL END
) STORED;

CREATE UNIQUE INDEX uq_products_active_sku
ON products (active_sku);
~~~

Unique index cho phép nhiều giá trị NULL trong MySQL, do đó các hàng đã xóa không xung đột qua active_sku. Kiểm tra phiên bản MySQL, collation, kiểu cột và quy tắc NULL của hệ quản trị đang dùng trước khi áp dụng.

Không dùng cùng một DDL cho mọi database. Chạy migration trên đúng hệ quản trị production và kiểm tra execution plan/index metadata sau khi triển khai.

## 15. Vì sao unique(deleted, sku) thường không phải giải pháp đúng?

Một cách dễ nghĩ tới là:

~~~sql
ALTER TABLE products
ADD CONSTRAINT uq_products_deleted_sku
UNIQUE (deleted, sku);
~~~

Cách này cho phép một hàng deleted=false và một hàng deleted=true có cùng SKU. Nhưng nó chỉ cho phép một hàng deleted=true cho mỗi SKU. Nếu SKU được tái sử dụng rồi lại xóa nhiều lần, lần xóa mềm thứ hai có thể xung đột với hàng deleted=true trước đó.

Ví dụ:

| id | sku | deleted |
|---:|---|---|
| 1 | SKU-100 | true |
| 2 | SKU-100 | false |

Khi xóa hàng id=2, hàng thứ hai chuyển thành deleted=true và tạo cặp (true, SKU-100) trùng hàng id=1.

Vì vậy, unique(deleted, sku) không diễn đạt đúng chính sách "chỉ duy nhất trong tập bản ghi đang hoạt động" khi có thể lưu nhiều phiên bản đã xóa. Partial/filtered unique index hoặc generated active key phù hợp hơn.

## 16. Khóa nghiệp vụ có phạm vi tenant

Nếu mỗi tenant được phép dùng cùng SKU, uniqueness phải gồm tenant_id:

~~~sql
CREATE UNIQUE INDEX uq_products_active_tenant_sku
ON products (tenant_id, sku)
WHERE deleted = false;
~~~

Với MySQL, có thể tạo generated active_sku như phần trước rồi tạo unique index trên (tenant_id, active_sku).

Tầng ứng dụng cũng phải dùng cùng phạm vi:

~~~java
boolean existsByTenantIdAndSkuAndDeletedFalse(
        Long tenantId,
        String sku);
~~~

Không kiểm tra SKU toàn cục nếu database cho phép SKU trùng giữa các tenant. Ngược lại, không để cache key hoặc API lookup chỉ dùng SKU khi dữ liệu được phân vùng theo tenant.

Mọi truy vấn, unique index, cache key và thao tác restore phải thống nhất cùng một định nghĩa business key.

## 17. Tạo lại bản ghi sau khi xóa mềm

Một luồng tạo mới có thể kiểm tra trước để trả lỗi thân thiện:

~~~java
@Transactional
public Product create(String sku, String name) {
    if (repository.existsBySkuAndDeletedFalse(sku)) {
        throw new DuplicateActiveSkuException(sku);
    }

    return repository.save(new Product(sku, name));
}
~~~

Tuy nhiên, existsBySkuAndDeletedFalse không thay thế unique index. Nếu hai request cùng tạo SKU, một transaction có thể thắng và transaction còn lại nhận lỗi constraint.

Hãy bắt DataIntegrityViolationException ở tầng service boundary phù hợp, phân biệt lỗi unique SKU với lỗi constraint khác nếu cần, rồi chuyển thành response nghiệp vụ thích hợp. Không nuốt mọi DataIntegrityViolationException và trả lỗi trùng SKU nếu lỗi thật là foreign key hoặc NOT NULL.

## 18. Khôi phục bản ghi đã xóa có thể bị xung đột uniqueness

Giả sử:

1. Product id=1, SKU-100 bị xóa mềm.
2. Một Product mới id=2 được tạo với SKU-100.
3. Người quản trị muốn khôi phục id=1.

Nếu unique index chỉ áp dụng cho bản ghi hoạt động, restore id=1 sẽ xung đột với id=2. Đây là kết quả đúng: không thể có hai sản phẩm hoạt động cùng SKU.

Chính sách restore cần được định nghĩa:

- Từ chối khôi phục và yêu cầu chọn SKU khác.
- Khôi phục sau khi đổi SKU của bản ghi cũ.
- Hợp nhất dữ liệu lịch sử vào bản ghi đang hoạt động.
- Khôi phục bằng một workflow quản trị có kiểm tra và audit.

Không tạm thời bỏ unique index để khôi phục. Hãy để database bảo vệ invariant và xử lý lỗi constraint thành kết quả nghiệp vụ rõ ràng.

## 19. Race condition giữa delete, create và restore

Các thao tác sau có thể chạy đồng thời:

- Request A kiểm tra SKU chưa tồn tại rồi tạo.
- Request B restore một hàng cũ cùng SKU.
- Request C xóa mềm một hàng đang hoạt động.
- Job D import hàng loạt.

Nếu chỉ dùng kiểm tra ở tầng Java, hai transaction có thể cùng vượt qua bước kiểm tra. Unique index có điều kiện giải quyết tính duy nhất nguyên tử tại database.

Các nguyên tắc:

- Unique index là nguồn sự thật cho uniqueness.
- exists query chỉ dùng để cải thiện thông báo hoặc tránh thao tác chắc chắn thất bại.
- Bắt lỗi constraint trong transaction và chuyển thành lỗi domain.
- Không retry vô hạn khi conflict là lỗi nghiệp vụ.
- Với import hàng loạt, xác định chính sách bỏ qua, cập nhật hay từ chối từng bản ghi.
- Kiểm thử bằng nhiều transaction đồng thời nếu workload có tranh chấp cao.

Nếu cần một workflow gồm nhiều bước restore/rename, dùng transaction và xử lý unique conflict rõ ràng. Không dựa vào thứ tự request ở tầng web để bảo đảm uniqueness.

## 20. Khôi phục với @SQLRestriction và @Filter

Nếu entity dùng @SQLRestriction("deleted = false"), truy vấn ORM thông thường không nhìn thấy hàng đã xóa. Vì restriction tĩnh không thể tắt, một method repository thông thường có thể không tìm được entity để gọi restore.

Các lựa chọn:

- Native UPDATE theo ID để đặt deleted=false và deleted_at=NULL; unique index sẽ kiểm tra xung đột.
- Một entity/repository quản trị riêng có mapping phù hợp để đọc cả hàng đã xóa.
- Dùng Hibernate @Filter có thể bật includeDeleted trong một Session được kiểm soát.
- Dùng JDBC hoặc một service quản trị chuyên biệt cho workflow restore.

Ví dụ native restore cho mapping thủ công:

~~~java
@Modifying
@Transactional
@Query(
    value = """
            UPDATE products
            SET deleted = false,
                deleted_at = NULL
            WHERE id = :id
              AND deleted = true
            """,
    nativeQuery = true
)
int restoreById(@Param("id") Long id);
~~~

Đây là native SQL nên không dùng JPQL entity/property name. Method trả số hàng được cập nhật: 1 nghĩa là có hàng đã xóa được khôi phục; 0 nghĩa là ID không tồn tại hoặc không ở trạng thái đã xóa. Nếu unique index phát hiện SKU đang được sử dụng, database từ chối UPDATE và transaction phải được xử lý như một conflict.

Với @SoftDelete, indicator có thể do Hibernate quản lý mà không có property deleted trong entity. Đừng dùng JPQL update p.deleted nếu property đó không được ánh xạ. Hãy dùng cách quản trị phù hợp với version/provider và kiểm thử việc khôi phục trên database mục tiêu.

## 21. Quan hệ cha-con và cascade

Soft delete một entity cha không tự động định nghĩa chính sách cho các entity con. Cần quyết định rõ:

- Con vẫn hoạt động nhưng không còn cha hiển thị?
- Con cũng bị soft delete?
- Con được chuyển sang trạng thái archived?
- Chỉ xóa liên kết ở join table?
- Có cần giữ lịch sử con để audit?

CascadeType.REMOVE có thể gọi remove trên entity con theo mapping/provider. Nếu con cũng có soft-delete mapping, thao tác remove có thể được chuyển thành soft delete của con. Tuy nhiên, không suy luận chính sách domain chỉ từ cascade annotation.

orphanRemoval=true có thể kích hoạt remove khi phần tử bị loại khỏi collection. Nếu child entity có soft-delete mapping, cần xác minh provider phát UPDATE hay DELETE và collection sau đó được đồng bộ thế nào.

Với ManyToMany, xóa phần tử khỏi collection thường tác động join table; nó không đồng nghĩa với soft delete entity đích. Nếu cần lịch sử membership, cân nhắc chuyển join table thành entity association riêng có deleted/deletedAt.

Kiểm thử các thao tác remove, clear collection, delete parent và restore parent trên mapping thật. Không để cascade vô tình xóa vật lý dữ liệu cần lưu.

## 22. Unique constraint trên association và các trường khác

Một entity có thể có nhiều quy tắc uniqueness:

- SKU duy nhất trong các sản phẩm hoạt động.
- Email duy nhất trong các tài khoản hoạt động.
- Mã external reference duy nhất theo tenant.
- Một bản ghi chính đang hoạt động cho mỗi customer.
- Một loại membership hoạt động cho mỗi user/team.

Mỗi invariant cần được biểu diễn bằng index/constraint phù hợp. Ví dụ một customer chỉ có một địa chỉ mặc định đang hoạt động:

~~~sql
CREATE UNIQUE INDEX uq_customer_default_address
ON customer_addresses (customer_id)
WHERE is_default = true
  AND deleted = false;
~~~

Đây là partial index kiểu PostgreSQL. Với database khác, cần cú pháp tương đương như filtered index hoặc generated columns.

Nếu uniqueness phụ thuộc nhiều điều kiện, viết predicate index rõ ràng và test các trường hợp biên. Không dựa vào một unique constraint toàn cục nếu nghiệp vụ chỉ yêu cầu uniqueness trong tập bản ghi chưa bị xóa.

## 23. Soft delete, cache và dữ liệu tìm kiếm

Khi một Product bị soft delete, cache và search index cũng phải phản ánh trạng thái mới.

Các điểm cần xử lý:

- Evict cache chi tiết theo SKU/ID sau commit.
- Evict hoặc cập nhật cache danh sách/search result có chứa sản phẩm.
- Xóa document khỏi search index hoặc đánh dấu inactive.
- Đảm bảo cache key và query chỉ trả sản phẩm đang hoạt động.
- Nếu SKU được dùng lại, không để cache cũ của bản ghi đã xóa trả nhầm nội dung.
- Khi restore, cập nhật lại cache/index sau commit.

Không xóa cache trước khi transaction commit nếu request khác có thể đọc database cũ rồi nạp lại cache. Có thể phát domain event và xử lý invalidation sau commit; với yêu cầu giao nhận đáng tin cậy, dùng outbox/retry.

## 24. Audit và retention

Soft delete chỉ lưu trạng thái xóa. Nhiều hệ thống còn cần biết ai xóa, vì sao và có khôi phục khi nào.

Có thể thêm:

~~~java
@Column(name = "deleted_by")
private String deletedBy;

@Column(name = "deletion_reason", length = 500)
private String deletionReason;

@Column(name = "deleted_at")
private Instant deletedAt;
~~~

Không nhất thiết đưa toàn bộ audit metadata vào entity nếu hệ thống đã có audit log riêng. Hãy xác định dữ liệu nào là trạng thái hiện tại và dữ liệu nào là lịch sử sự kiện.

Retention policy có thể quy định:
- Bản ghi soft delete được giữ 90 ngày.
- Sau thời hạn, job chuyển sang archive hoặc xóa vật lý.
- Một số loại dữ liệu phải giữ lâu hơn vì quy định/đối soát.
- Backup và audit log có chu kỳ riêng.

Job purge phải kiểm tra quan hệ phụ thuộc, foreign key, audit và chính sách pháp lý trước khi xóa vật lý. Không dùng job purge để lách uniqueness hoặc thay thế workflow restore.

## 25. Kiểm thử soft delete cơ bản

Với mapping thủ công @SQLDelete + @SQLRestriction, test cần xác nhận delete không làm mất hàng vật lý nhưng query ORM thường không còn thấy hàng.

Ví dụ repository test:

~~~java
package com.example.product;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class ProductSoftDeleteTest {

    @Autowired
    private ProductRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void deleteMarksRowAndHidesItFromNormalQueries() {
        Product product = new Product("SKU-100", "Keyboard");
        entityManager.persist(product);
        entityManager.flush();

        Long id = product.getId();

        repository.delete(product);
        entityManager.flush();
        entityManager.clear();

        assertThat(repository.findById(id)).isEmpty();

        Number deletedRows = (Number) entityManager.getEntityManager()
                .createNativeQuery("""
                    select count(*)
                    from products
                    where id = :id
                      and deleted = true
                    """)
                .setParameter("id", id)
                .getSingleResult();

        assertThat(deletedRows.longValue()).isEqualTo(1);
    }
}
~~~

Test dùng native query để kiểm tra hàng vẫn tồn tại với deleted=true. Truy vấn native không bị hiểu như JPQL và dùng tên bảng/cột vật lý. Test giả định database có boolean column deleted và @SQLDelete đúng như mapping thủ công.

Với Hibernate @SoftDelete, hãy viết test tương đương trên bảng catalog_products và indicator column được cấu hình. Kiểm tra repository delete, EntityManager.remove, findById và native SQL riêng biệt.

## 26. Kiểm thử uniqueness sau khi xóa

Test uniqueness phải chạy trên đúng database vì partial/filtered index và generated column khác nhau giữa hệ quản trị.

Các trường hợp nên có:

1. Tạo Product SKU-100 đang hoạt động thành công.
2. Tạo thêm Product SKU-100 khi bản ghi đầu còn hoạt động bị từ chối.
3. Soft delete bản ghi đầu.
4. Tạo Product mới SKU-100 thành công nếu chính sách cho phép tái sử dụng.
5. Xóa mềm bản ghi thứ hai.
6. Tạo bản ghi thứ ba cùng SKU thành công.
7. Khôi phục bản ghi đầu khi SKU đang được bản ghi thứ ba sử dụng phải bị từ chối.
8. Khôi phục sau khi SKU được giải phóng có thể thành công.
9. Kiểm thử hai transaction đồng thời cùng tạo SKU để xác nhận unique index bảo vệ dữ liệu.

H2 có thể không hỗ trợ cú pháp partial index giống production database. Dùng Testcontainers với PostgreSQL, SQL Server hoặc MySQL tương ứng để kiểm tra migration và hành vi constraint thật.

Không chỉ test existsBySkuAndDeletedFalse. Cần test unique index trực tiếp vì race condition không thể được chứng minh bằng test tuần tự đơn giản.

## 27. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| delete vẫn xóa vật lý | Entity không có soft-delete mapping hoặc dùng đường DELETE khác | Kiểm tra SQL và cơ chế remove |
| findById vẫn thấy bản ghi đã xóa | Không có filter/restriction hoặc filter chưa bật | Kiểm tra @SoftDelete, @SQLRestriction, @Filter và load-by-key |
| Native query trả bản ghi đã xóa | Native SQL không tự dùng predicate ORM | Thêm deleted=false trong SQL |
| SKU không dùng lại được | Full unique constraint vẫn tính hàng đã xóa | Dùng partial/filtered index hoặc generated active key |
| Lần xóa thứ hai bị unique conflict | UNIQUE(deleted, sku) chỉ cho một hàng deleted=true | Dùng index có điều kiện đúng |
| Restore thất bại | SKU đã được bản ghi đang hoạt động sử dụng | Xử lý conflict nghiệp vụ |
| Hai request tạo trùng | Chỉ kiểm tra exists ở Java, không có unique index | Đặt invariant tại database |
| Bulk DELETE xóa vật lý | Bulk/native delete không đi qua entity remove mapping | Dùng UPDATE soft delete tường minh |
| Restore không tìm thấy entity | @SQLRestriction luôn ẩn hàng đã xóa | Dùng native/admin path hoặc filter động |
| Child bị xóa ngoài ý muốn | Cascade/orphanRemoval không phù hợp | Xác định policy và test association |
| Cache vẫn trả sản phẩm đã xóa | Thiếu invalidation sau commit | Evict/update cache và search index |
| Hibernate báo stale state khi xóa | SQL tùy chỉnh có placeholder/row count/version sai | Kiểm tra @SQLDelete và optimistic locking |
| DDL chạy trên dev nhưng lỗi production | Partial index syntax khác database | Migration theo dialect và test bằng container thật |

## 28. Quy trình triển khai an toàn

Một trình tự triển khai thực tế:

1. Xác định chính sách xóa, khôi phục, quyền xem và uniqueness.
2. Thêm indicator column và audit metadata cần thiết.
3. Chọn @SoftDelete hoặc mapping thủ công phù hợp Hibernate version.
4. Chọn restriction tĩnh hay filter động cho truy vấn ORM.
5. Liệt kê mọi đường đọc: repository, findById, association, native SQL, batch job và API khác.
6. Tạo partial/filtered unique index hoặc generated active key theo database.
7. Viết service cho delete/restore và xử lý unique conflict.
8. Cập nhật cache/search index sau commit.
9. Kiểm thử entity remove, bulk operation, native query và association cascade.
10. Chạy migration và test uniqueness trên đúng database production.
11. Theo dõi lỗi constraint, query có lọt dữ liệu deleted và thời gian lưu trữ.
12. Triển khai purge job riêng nếu retention policy yêu cầu xóa vật lý sau thời hạn.

Khi migration trên bảng lớn, tạo index có thể khóa bảng hoặc tiêu tốn tài nguyên. Dùng chiến lược online/concurrent index phù hợp database và quy trình deploy của hệ thống.

## 29. Checklist tự đánh giá

- [ ] Phân biệt DELETE vật lý và UPDATE xóa mềm.
- [ ] Xác định chính sách restore và reuse business key.
- [ ] Biết Hibernate @SoftDelete cần Hibernate ORM 6.4+.
- [ ] Phân biệt SoftDeleteType.DELETED và ACTIVE.
- [ ] Hiểu @SQLDelete thay SQL remove và @SQLRestriction lọc tĩnh.
- [ ] Biết @SQLRestriction không thể tắt theo request.
- [ ] Hiểu @Filter cần bật trong Session và kiểm tra load theo ID.
- [ ] Phân biệt Spring Data delete entity với bulk JPQL/native DELETE.
- [ ] Không giả định bulk DELETE tự chuyển thành soft delete.
- [ ] Biết native SQL phải tự áp dụng điều kiện deleted.
- [ ] Hiểu full unique constraint vẫn giữ khóa của hàng đã xóa.
- [ ] Biết vì sao UNIQUE(deleted, sku) không phù hợp khi có nhiều lần tái sử dụng.
- [ ] Tạo partial/filtered unique index theo database.
- [ ] Dùng generated active key khi database không hỗ trợ partial index.
- [ ] Đưa tenant vào uniqueness nếu business key có phạm vi tenant.
- [ ] Dùng database constraint làm nguồn sự thật khi có concurrent writes.
- [ ] Xử lý conflict khi restore.
- [ ] Kiểm tra cascade, orphanRemoval và join table.
- [ ] Invalidate cache/search index sau commit.
- [ ] Kiểm thử trên database cùng loại production.

## 30. Kết luận

Soft delete thay đổi trạng thái bản ghi chứ không loại hàng khỏi database. Một triển khai đúng cần có cơ chế chuyển remove thành update, quy tắc lọc nhất quán cho mọi đường đọc và unique index phù hợp với chính sách dùng lại khóa nghiệp vụ.

Hibernate @SoftDelete là lựa chọn tích hợp từ Hibernate 6.4; @SQLDelete kết hợp @SQLRestriction phù hợp khi cần SQL tùy chỉnh hoặc dùng phiên bản cũ. @Filter hỗ trợ visibility động nhưng phải quản lý theo Session và kiểm tra cả load-by-key. Với uniqueness, hãy dùng partial/filtered index hoặc generated active key để chỉ bảo vệ các hàng đang hoạt động; kiểm tra trước ở Java không thay thế được constraint của database.

Cuối cùng, định nghĩa rõ restore, cascade, cache invalidation và retention. Kiểm thử cả đường ORM, bulk/native SQL, cạnh tranh đồng thời và migration trên đúng hệ quản trị sẽ giúp dữ liệu đã xóa không xuất hiện sai chỗ và khóa nghiệp vụ vẫn duy nhất theo đúng quy tắc.
