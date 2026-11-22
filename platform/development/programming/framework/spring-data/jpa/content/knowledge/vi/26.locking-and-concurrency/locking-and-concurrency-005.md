# Áp dụng @Lock lên truy vấn và phương thức CRUD khai báo lại

Spring Data JPA cho phép đặt chế độ khóa JPA trực tiếp lên phương thức repository bằng annotation `@Lock`. Annotation này có thể dùng với truy vấn dẫn xuất từ tên phương thức, truy vấn khai báo bằng `@Query`, và cả phương thức CRUD kế thừa được khai báo lại trong repository interface. Nhờ đó, ứng dụng có thể yêu cầu khóa bi quan hoặc kiểm tra khóa lạc quan khi đọc dữ liệu trong một giao dịch.

`@Lock` xác định chế độ khóa cho thao tác truy vấn. Nó không tự mở giao dịch và cũng không thay thế `@Transactional`. Muốn khóa có hiệu lực đúng trong suốt nghiệp vụ, cần đặt ranh giới giao dịch phù hợp, chọn đúng loại khóa và giữ giao dịch đủ ngắn.

## 1. @Lock là gì?

Spring Data JPA cung cấp annotation:

```java
import org.springframework.data.jpa.repository.Lock;
import jakarta.persistence.LockModeType;
```

Annotation `@Lock` nhận một giá trị thuộc enum `jakarta.persistence.LockModeType`:

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
Optional<Product> findBySku(String sku);
```

Khi Spring Data thực thi phương thức repository, lock mode được áp dụng cho truy vấn JPA tương ứng. JPA provider sẽ yêu cầu cơ sở dữ liệu hoặc cơ chế quản lý persistence thực hiện chế độ khóa đó.

Các vị trí thường dùng:

- Derived query: phương thức như `findByStatus()`, `findBySku()`.
- JPQL query khai báo bằng `@Query`.
- Phương thức CRUD được khai báo lại trong repository interface, chẳng hạn `findAll()`, để gắn thêm metadata khóa.

`@Lock` không khóa toàn bộ repository hay toàn bộ bảng. Nó áp dụng cho thao tác truy vấn được gắn annotation và các entity nằm trong phạm vi khóa mà JPA provider hỗ trợ.

## 2. Áp dụng @Lock lên derived query

Với derived query, chỉ cần đặt `@Lock` ngay trên phương thức:

```java
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;

import java.util.List;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Lock(LockModeType.PESSIMISTIC_READ)
    List<Product> findByCategoryId(Long categoryId);
}
```

Spring Data JPA vẫn phân tích tên `findByCategoryId` để tạo truy vấn. Annotation `@Lock` bổ sung lock mode cho truy vấn được tạo ra.

Ví dụ này yêu cầu khóa đọc bi quan trên các sản phẩm phù hợp. Cách cơ sở dữ liệu thực thi khóa phụ thuộc vào JPA provider và hệ quản trị cơ sở dữ liệu. Một số hệ quản trị có thể dùng row-level lock; một số trường hợp có thể nâng cấp hoặc chuyển đổi chế độ khóa.

Nếu phương thức query được gọi trong một nghiệp vụ cần nhiều thao tác nhất quán, hãy gọi nó từ service có `@Transactional`. Query method tự khai báo không mặc nhiên có cấu hình giao dịch chỉ vì nó nằm trong repository.

## 3. Áp dụng @Lock lên truy vấn @Query

Với JPQL được khai báo bằng `@Query`, đặt `@Lock` cùng phương thức:

```java
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select p
        from Product p
        where p.id = :id
        """)
    Optional<Product> findForUpdate(@Param("id") Long id);
}
```

Khi gọi `findForUpdate(id)`, Spring Data JPA thực thi truy vấn và yêu cầu chế độ `PESSIMISTIC_WRITE`. Mục đích thường gặp là đọc một bản ghi rồi cập nhật nó trong cùng giao dịch, ví dụ trừ tồn kho, giữ chỗ hoặc chuyển trạng thái một đơn hàng.

Một service sử dụng phương thức này:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final ProductRepository products;

    public InventoryService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public void decreaseStock(Long productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive");
        }

        Product product = products.findForUpdate(productId)
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Product not found: " + productId));

        if (product.getStock() < quantity) {
            throw new IllegalStateException("Insufficient stock");
        }

        product.setStock(product.getStock() - quantity);
        // product đang được quản lý trong persistence context.
        // Dirty checking sẽ ghi thay đổi khi flush/commit.
    }
}
```

Giao dịch service bao quanh cả thao tác đọc có khóa và cập nhật tồn kho. Khi một transaction khác cùng yêu cầu khóa ghi trên bản ghi đó, transaction sau phải chờ, hoặc nhận lỗi timeout tùy cấu hình. Sau khi transaction đầu commit hoặc rollback, transaction đang chờ mới có thể tiếp tục theo trạng thái dữ liệu mới.

Không nên tách lời gọi `findForUpdate()` và thao tác cập nhật thành hai giao dịch độc lập. Khi transaction chứa khóa kết thúc, khóa được giải phóng; phần xử lý sau đó sẽ không còn được bảo vệ bởi khóa vừa lấy.

## 4. Khai báo lại phương thức CRUD để thêm @Lock

Có thể khai báo lại một phương thức CRUD đã được kế thừa từ `JpaRepository` hoặc `CrudRepository`, rồi gắn `@Lock` lên khai báo mới. Spring Data JPA dùng metadata này khi thực thi phương thức repository.

Ví dụ khóa đọc bi quan cho `findAll()`:

```java
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;

import java.util.List;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Override
    @Lock(LockModeType.PESSIMISTIC_READ)
    List<Product> findAll();
}
```

Lời gọi `findAll()` trên repository này sẽ áp dụng lock mode đã khai báo. Đây là cách hữu ích khi ứng dụng muốn thay đổi hành vi khóa của một CRUD method có sẵn mà không cần tạo một truy vấn mới.

Có thể khai báo lại các phương thức đọc khác khi phù hợp với API và cách Spring Data JPA triển khai chúng. Hãy chọn đúng phương thức có thao tác truy vấn hoặc tải entity. Gắn `@Lock` lên một phương thức ghi như `save()` không biến thao tác ghi đó thành một truy vấn đọc có khóa; hãy dùng lock trên phương thức tải entity rồi thực hiện cập nhật trong cùng transaction.

Với thao tác khóa ghi, nên đặt giao dịch nghiệp vụ ở service:

```java
@Transactional
public void updateProduct(Long id, String newName) {
    Product product = products.findForUpdate(id)
            .orElseThrow();
    product.setName(newName);
}
```

Phương thức CRUD kế thừa có cấu hình giao dịch mặc định từ triển khai repository. Query method tự khai báo thì không có cấu hình giao dịch mặc định tương tự. Trong cả hai trường hợp, service transaction giúp giữ khóa xuyên suốt nghiệp vụ và kết hợp nhiều thao tác trong một đơn vị commit/rollback.

## 5. Các chế độ LockModeType

JPA định nghĩa các lock mode chính sau:

| Lock mode | Ý nghĩa và trường hợp sử dụng |
|---|---|
| `NONE` | Không yêu cầu khóa bổ sung. |
| `OPTIMISTIC` | Yêu cầu kiểm tra tính hợp lệ của khóa lạc quan trong giao dịch. Thích hợp khi xung đột ít và không muốn giữ khóa cơ sở dữ liệu trong lúc đọc. |
| `OPTIMISTIC_FORCE_INCREMENT` | Kiểm tra khóa lạc quan và buộc tăng version của entity. Hữu ích khi cần ghi nhận một thay đổi về mặt đồng bộ dù các thuộc tính nghiệp vụ không đổi. |
| `PESSIMISTIC_READ` | Yêu cầu khóa đọc bi quan để hạn chế transaction khác cập nhật dữ liệu đang được khóa. |
| `PESSIMISTIC_WRITE` | Yêu cầu khóa ghi bi quan, thường dùng khi cần đọc rồi cập nhật một bản ghi và muốn tuần tự hóa các thao tác cạnh tranh. |
| `PESSIMISTIC_FORCE_INCREMENT` | Lấy khóa ghi bi quan và buộc tăng version của entity nếu entity có version. |

Hai tên `READ` và `WRITE` cũng tồn tại trong enum để tương thích: `READ` tương đương `OPTIMISTIC`, còn `WRITE` tương đương `OPTIMISTIC_FORCE_INCREMENT`. Trong code mới, nên dùng tên tường minh `OPTIMISTIC` và `OPTIMISTIC_FORCE_INCREMENT` để tránh nhầm giữa khóa lạc quan và khóa đọc/ghi bi quan.

### Khóa lạc quan (optimistic locking)

Khóa lạc quan giả định xung đột ghi không thường xuyên. Nhiều transaction có thể đọc cùng một entity mà không phải giữ row lock trong suốt thời gian xử lý. Khi cập nhật, JPA kiểm tra version để phát hiện transaction khác đã thay đổi dữ liệu.

Entity thường khai báo trường `@Version`:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    private int stock;

    @Version
    private Long version;

    // constructors, getters and setters
}
```

Khi hai transaction cùng đọc một phiên bản rồi cùng cập nhật, transaction commit thay đổi sau có thể thất bại vì version trong cơ sở dữ liệu đã thay đổi. JPA thường phát hiện xung đột tại lúc flush hoặc commit, nên lỗi có thể xuất hiện ở cuối phương thức service chứ không nhất thiết ngay tại lệnh setter.

Có thể yêu cầu kiểm tra optimistic lock rõ ràng trên một query:

```java
@Lock(LockModeType.OPTIMISTIC)
Optional<Product> findBySku(String sku);
```

Với entity có `@Version`, thao tác cập nhật thông thường đã được JPA kiểm tra version tự động. `OPTIMISTIC` hữu ích khi muốn bảo đảm dữ liệu được đọc vẫn không bị thay đổi bởi transaction khác trong thời gian giao dịch, kể cả khi nghiệp vụ chỉ đọc entity đó. `OPTIMISTIC_FORCE_INCREMENT` dùng khi muốn tăng version ngay cả khi không có thay đổi thuộc tính thông thường.

Khi optimistic lock thất bại, JPA có thể ném `OptimisticLockException`; qua lớp dịch exception của Spring, lỗi thường được biểu diễn bằng nhóm `OptimisticLockingFailureException`. Ứng dụng có thể thông báo xung đột, tải lại dữ liệu và yêu cầu người dùng thử lại. Chỉ retry tự động khi nghiệp vụ có thể chạy lại an toàn.

### Khóa bi quan (pessimistic locking)

Khóa bi quan yêu cầu cơ sở dữ liệu giữ khóa trong thời gian transaction. Nó phù hợp với các thao tác có tranh chấp cao hoặc khi nghiệp vụ cần tuần tự hóa việc đọc và cập nhật một bản ghi.

- `PESSIMISTIC_READ`: yêu cầu khóa đọc; các transaction khác thường vẫn có thể đọc nhưng bị hạn chế khi muốn cập nhật cùng dữ liệu.
- `PESSIMISTIC_WRITE`: yêu cầu khóa ghi; transaction cạnh tranh muốn lấy khóa xung đột phải chờ hoặc thất bại.
- `PESSIMISTIC_FORCE_INCREMENT`: khóa ghi và tăng version nếu entity có version.

Cơ sở dữ liệu và provider quyết định cách ánh xạ lock mode sang câu lệnh hoặc cơ chế khóa cụ thể. Ví dụ phổ biến là câu lệnh tương đương `SELECT ... FOR UPDATE` cho khóa ghi, nhưng cú pháp và hành vi chính xác phụ thuộc hệ quản trị cơ sở dữ liệu.

Khóa bi quan thường cần transaction đang hoạt động. Hãy giữ transaction ngắn, tránh gọi API bên ngoài, chờ người dùng hoặc thực hiện tác vụ lâu trong lúc đang giữ khóa. Nếu transaction giữ khóa quá lâu, các yêu cầu khác có thể bị chặn, timeout hoặc làm giảm thông lượng hệ thống.

## 6. Kết hợp @Lock với @Transactional

`@Lock` và `@Transactional` giải quyết hai việc khác nhau:

- `@Lock` chọn chế độ khóa JPA cho truy vấn.
- `@Transactional` xác định ranh giới và vòng đời transaction.

Query method tự khai báo như `findForUpdate()` không tự mở transaction chỉ vì có `@Lock`. Một phương thức dùng khóa bi quan phải được gọi trong transaction đang hoạt động. Cách rõ ràng nhất thường là đặt `@Transactional` trên service method bao quanh việc đọc và xử lý entity.

Ví dụ:

```java
@Transactional
public void reserve(Long productId, int amount) {
    Product product = products.findForUpdate(productId)
            .orElseThrow();

    if (product.getStock() < amount) {
        throw new IllegalStateException("Insufficient stock");
    }

    product.setStock(product.getStock() - amount);
}
```

Propagation mặc định của `@Transactional` là `REQUIRED`. Vì vậy, repository method được gọi bên trong service thường tham gia transaction hiện có. Nếu repository method được gọi độc lập, hãy kiểm tra cấu hình giao dịch của chính phương thức đó; không dựa vào `@Lock` để tạo transaction.

Đối với khóa ghi bi quan, tránh đặt service transaction là `readOnly = true`. Giao dịch chỉ đọc không phù hợp với nghiệp vụ vừa khóa ghi vừa cập nhật dữ liệu, và cách provider xử lý có thể khác nhau.

## 7. Cấu hình thời gian chờ khóa

Có thể truyền JPA query hint để yêu cầu giới hạn thời gian chờ khóa. Spring Data JPA hỗ trợ `@QueryHints` trên phương thức repository:

```java
import jakarta.persistence.LockModeType;
import jakarta.persistence.QueryHint;
import org.springframework.data.jpa.repository.QueryHints;

@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(
    value = @QueryHint(
        name = "jakarta.persistence.lock.timeout",
        value = "3000"
    )
)
@Query("""
    select p
    from Product p
    where p.id = :id
    """)
Optional<Product> findForUpdate(@Param("id") Long id);
```

Ví dụ yêu cầu thời gian chờ 3.000 mili giây. Tên hint theo Jakarta Persistence là `jakarta.persistence.lock.timeout`; dự án dùng JPA cũ có thể dùng namespace `javax.persistence.lock.timeout`.

Đây là hint cho provider. Khả năng hỗ trợ và mức độ tuân thủ phụ thuộc JPA provider, driver và cơ sở dữ liệu. Không nên giả định mọi môi trường đều áp dụng timeout chính xác như giá trị đã khai báo. Hãy kiểm tra hành vi thực tế trên hệ quản trị cơ sở dữ liệu mà ứng dụng sử dụng và xử lý trường hợp không lấy được khóa.

## 8. Phạm vi và giới hạn cần hiểu

**Khóa gắn với transaction.** Khóa bi quan được giữ đến khi transaction kết thúc theo quy tắc của cơ sở dữ liệu. Khi transaction commit hoặc rollback, khóa được giải phóng. Không thể lấy khóa trong một transaction rồi mong khóa tiếp tục bảo vệ phần code chạy sau transaction đó.

**Khóa áp dụng cho truy vấn được gắn annotation.** Nếu một service tải entity bằng một phương thức khác không có lock mode, không thể giả định entity đó tự động được khóa chỉ vì một phương thức repository khác có `@Lock`.

**Lock mode không thay thế @Version.** Khóa lạc quan dựa trên version cần trường `@Version` để phát hiện xung đột theo cơ chế version. Khóa bi quan dựa vào khóa của cơ sở dữ liệu và có thể phối hợp với version khi entity có trường này.

**Bulk update không đồng bộ persistence context.** Truy vấn `UPDATE` hoặc `DELETE` hàng loạt tác động trực tiếp lên cơ sở dữ liệu, không đi qua quá trình cập nhật từng entity đang được quản lý. Nếu dùng bulk query trong cùng transaction với entity đã tải, hãy cân nhắc flush và clear persistence context để tránh dữ liệu cũ.

**Không có bảo đảm giống nhau giữa mọi cơ sở dữ liệu.** Loại khóa, phạm vi khóa, khả năng nâng cấp khóa, timeout và mức độ chặn phụ thuộc provider và hệ quản trị. Kiểm thử tích hợp trên đúng loại cơ sở dữ liệu triển khai là cần thiết cho nghiệp vụ có tranh chấp.

## 9. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Lỗi yêu cầu transaction khi dùng khóa bi quan | Query method có `@Lock` nhưng không chạy trong transaction | Bao lời gọi trong service có `@Transactional` |
| Hai request vẫn cập nhật đè dữ liệu | Chưa dùng lock phù hợp, hoặc thao tác đọc và ghi nằm ở các transaction khác nhau | Dùng `@Version` hoặc khóa bi quan trong cùng transaction |
| Optimistic lock thất bại khi commit | Transaction khác đã cập nhật cùng entity | Thông báo xung đột, tải lại và xử lý retry an toàn |
| Request chờ lâu khi cập nhật | Transaction khác đang giữ khóa bi quan | Rút ngắn transaction, đặt timeout phù hợp, xem xét giảm tranh chấp |
| Deadlock | Các transaction lấy nhiều khóa theo thứ tự khác nhau | Chuẩn hóa thứ tự truy cập bản ghi và giữ transaction ngắn |
| Entity trong persistence context có dữ liệu cũ sau bulk update | Bulk query không đồng bộ entity đã quản lý | Flush trước và clear sau khi cần, hoặc tải lại entity |
| @Lock có vẻ không tác dụng | Gắn annotation vào phương thức không thực thi query phù hợp, hoặc provider/database có hành vi khác | Xác minh phương thức repository thực tế và kiểm tra SQL/lock trên database |

Một deadlock có thể xảy ra khi transaction A khóa bản ghi 1 rồi chờ bản ghi 2, trong khi transaction B khóa bản ghi 2 rồi chờ bản ghi 1. Nếu nghiệp vụ cần khóa nhiều entity, nên thống nhất thứ tự lấy khóa ở mọi luồng xử lý.

## 10. Chọn loại khóa theo nghiệp vụ

| Nhu cầu | Lựa chọn thường phù hợp |
|---|---|
| Dữ liệu ít xung đột, chấp nhận phát hiện lỗi khi commit | `@Version` và optimistic locking |
| Cần xác nhận entity không đổi trong thời gian đọc | `@Lock(OPTIMISTIC)` |
| Cần tăng version dù không sửa thuộc tính | `@Lock(OPTIMISTIC_FORCE_INCREMENT)` |
| Cần nhiều transaction đọc nhưng hạn chế cập nhật đồng thời | `@Lock(PESSIMISTIC_READ)` |
| Cần tuần tự hóa thao tác đọc rồi cập nhật bản ghi | `@Lock(PESSIMISTIC_WRITE)` |
| Cần khóa ghi và tăng version | `@Lock(PESSIMISTIC_FORCE_INCREMENT)` |

Không nên mặc định chọn khóa bi quan cho mọi truy vấn. Khóa bi quan có thể làm giảm khả năng xử lý đồng thời và tăng nguy cơ chờ khóa. Với phần lớn nghiệp vụ CRUD, optimistic locking bằng `@Version` thường là điểm khởi đầu phù hợp; chỉ chuyển sang pessimistic locking khi mô hình tranh chấp và yêu cầu nghiệp vụ chứng minh cần thiết.

## 11. Quy trình triển khai và kiểm tra

1. Xác định entity và bản ghi cần bảo vệ khi có nhiều transaction cùng thao tác.
2. Chọn optimistic hay pessimistic locking dựa trên tần suất xung đột và cách nghiệp vụ xử lý khi có xung đột.
3. Với optimistic locking, khai báo `@Version` trên entity và kiểm tra cách ứng dụng xử lý lỗi version.
4. Với pessimistic locking, đặt `@Lock` lên derived query, `@Query` hoặc phương thức CRUD đọc được khai báo lại.
5. Bao thao tác lấy khóa và cập nhật trong cùng một `@Transactional` service method.
6. Nếu cần, cấu hình query hint cho lock timeout và xác minh provider/database có hỗ trợ.
7. Kiểm thử hai transaction đồng thời trên cùng bản ghi: một transaction giữ khóa hoặc cập nhật trước, transaction còn lại phải chờ hoặc phát hiện xung đột theo chế độ đã chọn.
8. Kiểm tra log SQL, thời gian chờ, lỗi deadlock và dữ liệu sau commit/rollback trên cơ sở dữ liệu mục tiêu.

## Kết luận

`@Lock` là cách Spring Data JPA gắn lock mode của JPA lên truy vấn repository. Có thể áp dụng nó cho derived query, phương thức `@Query` và CRUD method được khai báo lại như `findAll()`. Chế độ optimistic phù hợp khi muốn phát hiện xung đột, còn pessimistic phù hợp khi cần giữ khóa trong transaction để tuần tự hóa thao tác. Để khóa bảo vệ đúng nghiệp vụ, hãy đặt `@Transactional` bao quanh cả quá trình đọc và xử lý, chọn lock mode có chủ đích và kiểm thử trên hệ quản trị cơ sở dữ liệu thực tế.