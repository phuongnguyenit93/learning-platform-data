# Cập nhật Entity managed mà không gọi save lặp lại trong Spring Data JPA

Khi một entity đã được tải và đang ở trạng thái managed trong persistence context, JPA tự theo dõi thay đổi của entity. Nếu cập nhật thuộc tính trong một transaction đang hoạt động, Hibernate sẽ phát hiện thay đổi và phát sinh SQL UPDATE khi flush hoặc commit. Vì vậy, trong trường hợp này không cần gọi repository.save() sau mỗi lần sửa entity.

Cơ chế đó gọi là dirty checking. Hiểu rõ persistence context, trạng thái entity và ranh giới transaction giúp code ngắn gọn hơn, tránh thao tác merge không cần thiết và bảo đảm dữ liệu được ghi đúng thời điểm.

## 1. Persistence context là gì?

Persistence context là vùng quản lý các entity mà EntityManager đang theo dõi. Mỗi entity có một identity trong context dựa trên kiểu entity và khóa chính. Khi một entity được quản lý, JPA có thể phát hiện thay đổi thuộc tính và đồng bộ chúng xuống database.

Các thao tác như EntityManager.find(), repository.findById() hoặc truy vấn JPQL có thể đưa entity vào persistence context. Khi transaction kết thúc, persistence context theo transaction thường được đóng hoặc giải phóng; entity trả ra ngoài có thể trở thành detached.

Luồng cập nhật thông thường:

~~~mermaid
flowchart TD
    A[Service method bắt đầu] --> B[@Transactional mở transaction]
    B --> C[Repository findById]
    C --> D[Entity ở trạng thái managed]
    D --> E[Thay đổi thuộc tính]
    E --> F[Dirty checking]
    F --> G[Flush: Hibernate phát sinh UPDATE]
    G --> H[Commit transaction]
    H --> I[Database lưu thay đổi]
~~~

Điểm quan trọng: JPA theo dõi entity trong persistence context. Việc gọi save() không phải điều kiện để dirty checking hoạt động.

## 2. Bốn trạng thái cơ bản của entity

JPA thường mô tả vòng đời entity bằng bốn trạng thái:

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| New / Transient | Đối tượng Java mới, chưa được persistence context quản lý | new Product(...) |
| Managed / Persistent | Entity đang được EntityManager theo dõi | Entity vừa được findById trong transaction |
| Detached | Entity từng được quản lý nhưng hiện không còn nằm trong persistence context | Entity sau khi transaction kết thúc |
| Removed | Entity được đánh dấu xóa trong persistence context | Entity sau entityManager.remove(...) |

Ví dụ chuyển trạng thái:

~~~java
Product product = new Product("Keyboard"); // transient
entityManager.persist(product);            // managed
product.rename("Mechanical Keyboard");     // vẫn managed
entityManager.detach(product);              // detached
Product managedProduct = entityManager.merge(product); // managed copy
entityManager.remove(managedProduct);        // removed
~~~

Ví dụ trên minh họa các thao tác JPA trực tiếp. Trong ứng dụng Spring Data JPA, repository thường che giấu phần lớn thao tác EntityManager.

## 3. Dirty checking hoạt động như thế nào?

Khi entity trở thành managed, Hibernate thường giữ trạng thái ban đầu hoặc snapshot của các thuộc tính cần theo dõi. Trong quá trình flush, Hibernate so sánh trạng thái hiện tại với snapshot. Nếu phát hiện thuộc tính có thay đổi, provider tạo SQL UPDATE tương ứng.

Ví dụ:

~~~java
Product product = entityManager.find(Product.class, 10L);
product.setName("Mechanical Keyboard");
// Không cần entityManager.merge(product).
// Entity đang managed nên thay đổi được dirty checking theo dõi.
~~~

Khi transaction commit, JPA yêu cầu đồng bộ thay đổi tới database. Hibernate thực hiện flush trước khi commit; SQL có thể được gửi trước thời điểm commit, nhưng thay đổi vẫn thuộc transaction và có thể rollback.

Dirty checking có các đặc điểm:

- Chỉ áp dụng cho entity đang managed.
- Không cần gọi save() sau mỗi setter.
- Nếu không có thay đổi, provider thường không phát sinh UPDATE.
- SQL thường được trì hoãn tới flush/commit.
- Có thể cần flush trước khi chạy một truy vấn phụ thuộc vào thay đổi chưa đồng bộ.
- Các callback như @PreUpdate có thể được gọi khi entity thực sự được cập nhật qua cơ chế entity thông thường.

Dirty checking không phải cơ chế đồng bộ liên tục mỗi khi setter được gọi. Nó được kiểm tra trong quá trình flush của persistence context.

## 4. Điều kiện quan trọng: cập nhật trong transaction

Một lỗi phổ biến là gọi repository.findById() trong một phương thức, trả entity ra ngoài, rồi thay đổi entity sau khi transaction của repository đã kết thúc.

Ví dụ không nên dùng:

~~~java
public Product rename(Long id, String newName) {
    Product product = repository.findById(id).orElseThrow();
    product.setName(newName);
    return product;
}
~~~

Nếu không có transaction bao quanh phương thức service, repository.findById() có thể chạy trong transaction riêng của nó. Sau khi phương thức repository kết thúc, entity có thể đã detached. Thay đổi sau đó không còn được persistence context theo dõi và không tự động ghi xuống database.

Cách đúng là đặt transaction ở tầng service để cả thao tác đọc và sửa diễn ra trong cùng một persistence context.

## 5. Ví dụ cập nhật managed entity mà không gọi save()

Entity Product:

~~~java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    @Column(nullable = false)
    private boolean active;

    @Version
    private Long version;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
        this.active = true;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
    }

    public Long getVersion() {
        return version;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Name must not be blank");
        }
        this.name = newName;
    }

    public void deactivate() {
        this.active = false;
    }

    public void activate() {
        this.active = true;
    }
}
~~~

Repository:

~~~java
package com.example.catalog;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Service cập nhật entity:

~~~java
package com.example.catalog;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Product rename(Long id, String newName) {
        Product product = repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Product not found: " + id));

        product.rename(newName);

        // product đang managed; dirty checking sẽ ghi thay đổi khi flush/commit.
        return product;
    }

    @Transactional
    public void deactivate(Long id) {
        Product product = repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Product not found: " + id));

        product.deactivate();
    }
}
~~~

Trong hai phương thức service:

1. @Transactional mở transaction.
2. findById() tải entity và đưa entity vào persistence context.
3. rename() hoặc deactivate() thay đổi trạng thái của entity managed.
4. Khi phương thức kết thúc bình thường, transaction commit và Hibernate flush thay đổi.
5. SQL UPDATE được thực hiện trong transaction.

Không cần gọi repository.save(product) sau khi đổi tên hoặc trạng thái. Việc trả entity ra khỏi service không làm nó tự động trở lại managed sau khi transaction đóng; nếu cần trả dữ liệu cho API, nên chuyển sang DTO trong transaction hoặc tải dữ liệu cần thiết trước khi kết thúc.

## 6. Vì sao save() không cần thiết với entity managed?

Spring Data JPA triển khai save() dựa trên trạng thái mới/cũ của entity. Về khái quát:

- Nếu entity được nhận diện là mới, repository gọi EntityManager.persist().
- Nếu entity được nhận diện là đã tồn tại, repository gọi EntityManager.merge().

merge() sao chép trạng thái từ đối tượng truyền vào sang một instance managed và trả về instance managed đó. Với entity đã managed trong cùng persistence context, gọi save() thường không cần thiết. Nó có thể dẫn tới merge không cần thiết và làm luồng code khó hiểu hơn.

Ví dụ:

~~~java
@Transactional
public Product update(Long id, String name) {
    Product managed = repository.findById(id).orElseThrow();
    managed.rename(name);

    // Không cần:
    // managed = repository.save(managed);

    return managed;
}
~~~

Nếu vẫn gọi save() với entity managed, đừng giả định nó luôn tạo thêm một câu SQL UPDATE ngay lập tức. SQL vẫn phụ thuộc dirty checking, flush và trạng thái dữ liệu. Tuy nhiên, merge không đem lại lợi ích trong tình huống entity đã được quản lý.

Với entity detached, save() có thể cần thiết vì repository phải merge trạng thái vào persistence context. Khi đó hãy dùng instance được trả về từ save(), vì merge không làm cho object detached ban đầu trở thành managed.

## 7. Phân biệt persist(), merge() và save()

| Thao tác | Mục đích | Đối tượng sau thao tác |
|---|---|---|
| EntityManager.persist(newEntity) | Đưa entity mới vào persistence context | Đối tượng truyền vào trở thành managed |
| EntityManager.merge(detachedEntity) | Sao chép trạng thái entity detached vào context | Giá trị trả về là instance managed |
| repository.save(entity) | API Spring Data để lưu entity mới hoặc entity hiện có | Trả về entity được persist/merge |
| Thay đổi entity managed | Cập nhật entity đã được quản lý | Vẫn managed, dirty checking theo dõi |

Ví dụ merge:

~~~java
Product detached = obtainDetachedProduct();

Product managed = entityManager.merge(detached);

// detached vẫn là instance detached.
// managed là instance đang được persistence context quản lý.
managed.rename("Updated name");
~~~

Không nên bỏ qua giá trị trả về của merge() hoặc repository.save() khi đang xử lý entity detached. Thay đổi tiếp trên object cũ có thể không được theo dõi.

## 8. Cập nhật nhiều thuộc tính trong một transaction

Dirty checking đặc biệt hữu ích khi một nghiệp vụ thay đổi nhiều thuộc tính của cùng entity:

~~~java
@Transactional
public void updateProduct(
        Long id,
        String name,
        boolean active) {
    Product product = repository.findById(id)
            .orElseThrow();

    product.rename(name);

    if (active) {
        product.activate();
    } else {
        product.deactivate();
    }

    // Không cần gọi save() sau từng thay đổi.
}
~~~

Có thể cập nhật nhiều entity trong cùng một transaction:

~~~java
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

public interface ProductRepository extends JpaRepository<Product, Long> {
    List<Product> findByActiveTrue();
}

@Service
public class ProductBatchService {
    private final ProductRepository repository;

    public ProductBatchService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void deactivateActiveProducts() {
        List<Product> products = repository.findByActiveTrue();
        for (Product product : products) {
            product.deactivate();
        }
        // Hibernate phát hiện các thay đổi khi flush.
    }
}
~~~

Trong thực tế, cần chú ý kích thước persistence context. Nếu xử lý hàng chục nghìn entity, giữ tất cả managed cùng lúc có thể tốn bộ nhớ. Có thể xử lý theo từng batch, flush và clear có kiểm soát, hoặc dùng bulk update nếu nghiệp vụ phù hợp.

Không nên gọi save() lặp lại cho từng entity chỉ để kích hoạt dirty checking. Khi các entity đã managed, thay đổi thuộc tính là đủ.

## 9. Flush và commit khác nhau thế nào?

Flush đồng bộ các thay đổi đang chờ trong persistence context xuống database bằng SQL. Commit xác nhận transaction để thay đổi trở thành dữ liệu đã commit.

| Thao tác | Ý nghĩa |
|---|---|
| Thay đổi thuộc tính managed | Cập nhật trạng thái trong bộ nhớ |
| flush() | Gửi SQL cần thiết xuống database trong transaction hiện tại |
| commit | Xác nhận transaction |
| rollback | Hủy các thay đổi của transaction chưa commit |

Có thể yêu cầu flush tường minh:

~~~java
@Transactional
public void renameAndCheck(Long id, String newName) {
    Product product = repository.findById(id).orElseThrow();
    product.rename(newName);

    repository.flush();

    // SQL UPDATE đã được gửi trong transaction.
    // Transaction vẫn chưa commit tại dòng này.
}
~~~

Thông thường không cần gọi flush() thủ công. Hibernate tự flush trước commit và có thể flush trước một số truy vấn khi flush mode là AUTO. Chỉ gọi flush khi cần bảo đảm SQL đã được gửi, ví dụ muốn phát hiện sớm constraint violation hoặc cần đọc kết quả SQL trong cùng transaction.

flush() không đồng nghĩa commit. Nếu có lỗi sau flush và transaction rollback, database vẫn hủy các thay đổi thuộc transaction đó.

## 10. Transaction boundary và các lưu ý với Spring

@Transactional thường đặt trên public service method. Spring tạo proxy để bắt đầu, commit hoặc rollback transaction quanh lời gọi từ bên ngoài bean.

~~~java
@Service
public class ProductService {

    @Transactional
    public void rename(Long id, String name) {
        // Đọc và cập nhật entity trong cùng transaction.
    }
}
~~~

Các lưu ý:

- Transaction phải bao trùm cả thao tác tải entity và sửa entity.
- Gọi một method @Transactional từ method khác trong cùng instance (self-invocation) thường không đi qua proxy, vì vậy annotation bên trong có thể không được áp dụng như mong đợi.
- Một repository method có transaction riêng không tự động giữ entity managed sau khi method kết thúc.
- Không đánh dấu phương thức cập nhật là @Transactional(readOnly = true).
- Mặc định Spring rollback với unchecked exception và Error; checked exception không tự động rollback nếu không cấu hình rollbackFor.
- Giữ transaction ngắn, tránh gọi API bên ngoài hoặc chờ người dùng trong lúc transaction đang mở.
- Nếu một transaction ngoài đã tồn tại, repository thường tham gia transaction đó theo propagation mặc định REQUIRED.

Ví dụ cấu trúc phù hợp: Controller gọi Service; Service có @Transactional; Service gọi repository để tải và sửa entity. Controller không nên tự mở transaction rồi thao tác persistence.

## 11. Khi nào vẫn cần gọi save()?

Không phải mọi thao tác đều bỏ save().

| Tình huống | Có cần save()? | Lý do |
|---|---|---|
| Tạo entity mới | Có, thường dùng repository.save() | Entity cần được persist |
| Tải entity trong transaction rồi thay đổi | Không | Dirty checking tự ghi thay đổi |
| Tải entity rồi chỉ đọc | Không | Không có thay đổi cần lưu |
| Cập nhật entity detached | Có thể cần | save() thực hiện merge; phải dùng instance trả về |
| Tạo entity có ID được gán thủ công | Phụ thuộc cơ chế nhận diện mới/cũ | Spring Data cần xác định persist hay merge |
| Bulk JPQL UPDATE | Không gọi save cho từng entity | Query cập nhật trực tiếp database qua @Modifying |
| Thay đổi entity sau khi transaction đã kết thúc | Không thể dựa vào dirty checking | Entity đã detached; cần tải lại trong transaction hoặc merge |

Đối với entity mới:

~~~java
@Transactional
public Product create(String name) {
    Product product = new Product(name);
    return repository.save(product);
}
~~~

Đối với entity managed:

~~~java
@Transactional
public void rename(Long id, String name) {
    Product product = repository.findById(id).orElseThrow();
    product.rename(name);
}
~~~

Hai trường hợp có mục đích khác nhau: entity mới cần persist; entity managed đã nằm trong persistence context và được theo dõi.

## 12. Tránh cập nhật entity bằng dữ liệu request một cách mù quáng

Một anti-pattern phổ biến là nhận nguyên entity từ JSON, trong đó client gửi cả ID, rồi gọi save() để ghi đè dữ liệu:

~~~java
// Không nên dùng như cách cập nhật tổng quát.
public Product update(Product requestEntity) {
    return repository.save(requestEntity);
}
~~~

Cách này có thể ghi đè trường mà client không được phép sửa, gây lỗi với quan hệ lazy, trường audit hoặc optimistic locking.

Nên nhận DTO, tải entity managed và chỉ cập nhật các trường được phép:

~~~java
public record RenameProductRequest(String name) {
}

@Transactional
public Product rename(Long id, RenameProductRequest request) {
    Product product = repository.findById(id).orElseThrow();
    product.rename(request.name());
    return product;
}
~~~

Cách này giữ các quy tắc miền trong entity và kiểm soát rõ trường nào được phép thay đổi. Với API, thường trả DTO thay vì trả entity trực tiếp để tránh vấn đề lazy loading và vô tình công khai quan hệ nội bộ.

## 13. Optimistic locking với @Version

Khi nhiều người dùng cùng cập nhật một bản ghi, dirty checking không tự giải quyết xung đột nghiệp vụ. Có thể dùng @Version để phát hiện cập nhật đồng thời.

~~~java
@Entity
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @Version
    private Long version;

    protected Product() {
    }

    public void rename(String name) {
        this.name = name;
    }

    public Long getVersion() {
        return version;
    }
}
~~~

Hibernate đưa version hiện tại vào điều kiện UPDATE và tăng version khi cập nhật thành công. Nếu một transaction khác đã cập nhật cùng bản ghi, số dòng được cập nhật không như mong đợi và JPA báo optimistic locking failure, thường được Spring chuyển thành ObjectOptimisticLockingFailureException.

Ví dụ tình huống:

1. Transaction A đọc Product version 3.
2. Transaction B cũng đọc version 3.
3. B cập nhật và commit; version thành 4.
4. A cập nhật với điều kiện version = 3.
5. UPDATE của A không còn khớp; A nhận lỗi optimistic locking.

Cần xử lý xung đột theo nghiệp vụ: thông báo người dùng tải lại dữ liệu, thử lại có giới hạn hoặc yêu cầu hợp nhất thay đổi. Không nên tự động retry vô hạn.

## 14. Bulk update khác dirty checking

JPQL bulk update cập nhật trực tiếp nhiều dòng trong database:

~~~java
public interface ProductRepository extends JpaRepository<Product, Long> {

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("update Product p set p.active = false where p.active = true")
    int deactivateAll();
}
~~~

Gọi trong transaction:

~~~java
@Transactional
public int deactivateAllProducts() {
    return repository.deactivateAll();
}
~~~

Bulk update hữu ích khi cần thay đổi nhiều dòng mà không tải từng entity. Tuy nhiên, nó bỏ qua dirty checking từng entity, thường không kích hoạt entity lifecycle callback và có thể khiến các entity đang managed trong persistence context giữ giá trị cũ. clearAutomatically giúp xóa context sau query; flushAutomatically đồng bộ thay đổi đang chờ trước khi chạy bulk query.

Nếu entity dùng @Version, bulk update cần được thiết kế riêng để cập nhật version nếu nghiệp vụ cần bảo vệ optimistic locking. Bulk query không tự động tương đương với việc thay đổi từng entity managed.

## 15. Kiểm thử dirty checking

Có thể dùng @DataJpaTest để xác nhận entity được cập nhật khi thay đổi trong transaction mà không gọi save() lần hai.

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.transaction.annotation.Transactional;

@DataJpaTest
class ProductDirtyCheckingTest {

    @Autowired
    private ProductRepository repository;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    @Transactional
    void updatesManagedEntityWithoutCallingSaveAgain() {
        Product product = repository.save(new Product("Keyboard"));
        Long id = product.getId();

        Product managed = repository.findById(id).orElseThrow();
        managed.rename("Mechanical Keyboard");

        // Flush SQL rồi xóa persistence context để lần đọc sau lấy lại từ database.
        entityManager.flush();
        entityManager.clear();

        Product reloaded = repository.findById(id).orElseThrow();

        assertThat(reloaded.getName()).isEqualTo("Mechanical Keyboard");
    }
}
~~~

Trong test này, repository.save() đầu tiên dùng để tạo entity mới. Sau đó entity được tải và cập nhật khi đang managed. flush() đồng bộ thay đổi để kiểm tra; test transaction thường được rollback khi kết thúc theo cấu hình @DataJpaTest.

Nếu muốn xác nhận dữ liệu sau commit thật sự, cần một integration test quản lý transaction riêng, thực hiện commit rồi đọc lại trong transaction khác. Không nên nhầm việc đọc lại cùng persistence context với việc kiểm tra dữ liệu đã commit.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Thay đổi entity nhưng database không đổi | Entity đã detached hoặc không có transaction bao quanh | Tải và sửa entity trong cùng @Transactional service method |
| Gọi save() nhiều lần nhưng không cải thiện | Entity vốn đã managed | Dùng dirty checking, chỉ save entity mới hoặc detached khi cần |
| Cập nhật sau khi repository method kết thúc không có tác dụng | Transaction của repository đã đóng | Đặt transaction ở service bao trùm đọc và sửa |
| merge() trả về object khác | merge sao chép trạng thái sang instance managed | Tiếp tục dùng object trả về từ merge/save |
| Không thấy SQL UPDATE ngay sau setter | SQL được trì hoãn đến flush/commit | Kiểm tra sau flush hoặc commit |
| flush rồi rollback vẫn mất thay đổi | flush chỉ gửi SQL trong transaction | Commit mới xác nhận transaction |
| Entity bị ghi đè bởi request | Gán trực tiếp dữ liệu client lên entity | Dùng DTO và cập nhật trường được phép |
| Optimistic locking failure | Transaction khác cập nhật trước | Tải lại, xử lý xung đột theo nghiệp vụ |
| Entity trong context cũ sau bulk update | Bulk query không đồng bộ object đang managed | Flush/clear hoặc tải lại entity |
| @Transactional không hoạt động | Self-invocation hoặc gọi ngoài Spring proxy | Tách method sang bean/service được Spring quản lý |

## 17. Nguyên tắc sử dụng trong ứng dụng thực tế

- Đặt transaction boundary ở service method đại diện cho một nghiệp vụ.
- Tải entity bằng repository trong transaction rồi thay đổi qua method có ý nghĩa miền.
- Dùng dirty checking cho entity managed; không gọi save() lặp lại sau mỗi setter.
- Gọi save() cho entity mới và dùng merge/save có chủ đích cho entity detached.
- Dùng @Version khi cần phát hiện cập nhật đồng thời.
- Dùng bulk update khi cần xử lý nhiều dòng và đã hiểu tác động tới persistence context, callback và version.
- Giữ transaction ngắn và tránh gọi dịch vụ ngoài trong transaction.
- Dùng DTO để nhận dữ liệu API và kiểm soát trường được phép cập nhật.
- Dùng flush() chỉ khi cần đồng bộ SQL sớm; nhớ rằng flush không phải commit.
- Kiểm thử với database mục tiêu nếu logic phụ thuộc hành vi Hibernate hoặc SQL cụ thể.

## 18. Checklist tự đánh giá

- [ ] Giải thích được persistence context và trạng thái managed.
- [ ] Phân biệt transient, managed, detached và removed.
- [ ] Mô tả được dirty checking và thời điểm flush.
- [ ] Cập nhật entity trong @Transactional service method mà không gọi save() lần hai.
- [ ] Giải thích vì sao repository.findById() riêng lẻ có thể trả entity detached sau khi method kết thúc.
- [ ] Phân biệt persist(), merge() và repository.save().
- [ ] Dùng đúng instance trả về từ merge/save khi xử lý entity detached.
- [ ] Phân biệt flush với commit.
- [ ] Biết cách dùng @Version để phát hiện cập nhật đồng thời.
- [ ] Phân biệt dirty checking với JPQL bulk update.
- [ ] Tránh ghi đè entity bằng request body trực tiếp.
- [ ] Viết được test xác nhận thay đổi managed entity được lưu khi flush/commit.

## 19. Kết luận

Entity đang managed trong persistence context được JPA theo dõi. Khi sửa thuộc tính trong transaction, dirty checking phát hiện thay đổi và Hibernate ghi SQL khi flush hoặc commit. Vì vậy, một service method có @Transactional thường chỉ cần tải entity, gọi method cập nhật và kết thúc transaction.

save() vẫn hữu ích khi tạo entity mới hoặc khi cần merge entity detached. Hiểu đúng trạng thái entity, transaction và flush giúp tránh gọi save() không cần thiết, giảm thao tác persistence dư thừa và bảo vệ dữ liệu khi có nhiều transaction đồng thời.
