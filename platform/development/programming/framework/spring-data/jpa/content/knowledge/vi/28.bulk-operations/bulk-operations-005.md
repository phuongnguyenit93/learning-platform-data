# PersistenceContext lỗi thời sau bulk update hoặc bulk delete

Spring Data JPA cho phép thực hiện cập nhật hoặc xóa hàng loạt bằng JPQL để xử lý nhiều bản ghi trong một câu lệnh SQL. Cách làm này thường nhanh hơn việc tải từng entity rồi sửa hoặc xóa lần lượt. Tuy nhiên, bulk update và bulk delete tác động trực tiếp lên cơ sở dữ liệu, không đồng bộ các entity đang được quản lý trong persistence context.

Vì vậy, sau khi chạy bulk operation, một entity đã được tải trước đó có thể vẫn giữ giá trị cũ trong bộ nhớ. Nếu tiếp tục đọc hoặc ghi entity đó, ứng dụng có thể trả về dữ liệu lỗi thời hoặc vô tình ghi đè thay đổi vừa thực hiện. Bài học này giải thích nguyên nhân và cách đồng bộ trạng thái an toàn.

## 1. Persistence context là gì?

Persistence context là vùng làm việc của JPA, do `EntityManager` quản lý. Trong một persistence context, mỗi entity có định danh cơ sở dữ liệu thường được đại diện bởi một instance managed duy nhất.

Các trạng thái chính của entity:

- **Transient:** đối tượng Java mới được tạo, chưa được JPA quản lý và chưa gắn với persistence context.
- **Managed:** entity đang được quản lý. JPA theo dõi thay đổi thuộc tính thông qua dirty checking và có thể đồng bộ chúng xuống database khi flush.
- **Detached:** entity từng được quản lý nhưng đã bị tách khỏi persistence context, chẳng hạn sau `clear()`, `detach()` hoặc khi persistence context kết thúc.
- **Removed:** entity được đánh dấu xóa trong persistence context; lệnh xóa sẽ được đồng bộ khi flush.

Persistence context hoạt động như bộ nhớ đệm cấp một (first-level cache). Khi gọi `find()` hoặc repository `findById()`, nếu entity có cùng định danh đã được quản lý trong persistence context hiện tại, JPA có thể trả lại chính instance đó mà không đọc lại trạng thái mới nhất từ database.

Ví dụ:

```java
@Transactional
public void inspectOrder(Long id) {
    PurchaseOrder first = entityManager.find(PurchaseOrder.class, id);
    PurchaseOrder second = entityManager.find(PurchaseOrder.class, id);

    System.out.println(first == second); // true
}
```

Hai biến tham chiếu đến cùng một instance managed trong persistence context. Nếu một thao tác khác cập nhật hàng tương ứng trực tiếp trong database, instance này không tự động thay đổi theo.

## 2. Vì sao bulk update và bulk delete làm persistence context lỗi thời?

Một thao tác entity thông thường đi qua persistence context:

1. JPA tải entity vào persistence context.
2. Ứng dụng thay đổi thuộc tính hoặc đánh dấu entity cần xóa.
3. Dirty checking và cơ chế đồng bộ của JPA phát hiện thay đổi.
4. Khi flush, JPA phát lệnh SQL tương ứng.

Bulk DML có đường thực thi khác. JPQL `UPDATE` hoặc `DELETE` được chuyển thành một câu lệnh tác động trực tiếp lên nhiều hàng trong database. Provider không tải từng entity vào persistence context để áp dụng thay đổi.

Ví dụ, repository chạy:

```sql
UPDATE purchase_orders
SET status = 'ARCHIVED'
WHERE created_at < ?;
```

Nếu `PurchaseOrder` có một instance đang managed, thuộc tính `status` của instance đó vẫn có thể là `OPEN`, dù database đã chuyển thành `ARCHIVED`.

Tương tự, bulk delete có thể xóa hàng trong database nhưng instance tương ứng vẫn còn trong persistence context. Entity đó không tự chuyển sang trạng thái `Removed`; ứng dụng vẫn có thể giữ tham chiếu đến một đối tượng Java đại diện cho hàng đã bị xóa.

Điểm cần nhớ: **bulk DML không đồng bộ các entity đang managed với kết quả của câu lệnh.** JPA không tự động cập nhật hoặc loại bỏ từng instance trong persistence context sau bulk operation.

## 3. Ví dụ tái hiện dữ liệu cũ

Giả sử có entity `PurchaseOrder` với các thuộc tính `id`, `status` và `createdAt`. Một phương thức đọc entity trước, sau đó gọi bulk update:

```java
@Transactional
public void demonstrateStaleState(Long id) {
    PurchaseOrder order = entityManager.find(PurchaseOrder.class, id);

    // Cập nhật trực tiếp database qua một JPQL bulk update.
    entityManager.createQuery("""
        update PurchaseOrder p
        set p.status = :status
        where p.id = :id
        """)
        .setParameter("status", OrderStatus.ARCHIVED)
        .setParameter("id", id)
        .executeUpdate();

    // Instance managed có thể vẫn chứa giá trị status cũ.
    System.out.println(order.getStatus());
}
```

Câu lệnh `executeUpdate()` trả về số hàng bị tác động. Nó không cập nhật thuộc tính của biến `order`. Nếu `order.getStatus()` được gọi sau bulk update, kết quả có thể vẫn là giá trị cũ đã tải trước đó.

Một truy vấn repository tiếp theo trong cùng persistence context cũng có thể trả về instance managed cũ. Chỉ gọi lại `findById(id)` không đảm bảo làm mới entity nếu JPA tìm thấy instance đó trong first-level cache.

## 4. Bulk update/delete bằng Spring Data JPA

Trong Spring Data JPA, dùng `@Modifying` cùng `@Query` để khai báo một truy vấn cập nhật hoặc xóa:

```java
import java.time.LocalDateTime;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Modifying
    @Query("""
        update PurchaseOrder p
        set p.status = :status
        where p.createdAt < :cutoff
        """)
    int updateStatusBefore(
            @Param("status") OrderStatus status,
            @Param("cutoff") LocalDateTime cutoff);

    @Modifying
    @Query("""
        delete from PurchaseOrder p
        where p.status = :status
        """)
    int deleteAllWithStatus(@Param("status") OrderStatus status);
}
```

`@Modifying` báo cho Spring Data biết truy vấn khai báo bằng `@Query` là thao tác thay đổi dữ liệu và cần thực thi bằng `executeUpdate()`, thay vì xử lý như truy vấn đọc.

Phương thức bulk update/delete cần chạy trong giao dịch. Có thể đặt `@Transactional` ở service để gom các thao tác liên quan vào cùng một ranh giới giao dịch:

```java
import java.time.LocalDateTime;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderMaintenanceService {

    private final PurchaseOrderRepository repository;

    public OrderMaintenanceService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int archiveOldOrders(LocalDateTime cutoff) {
        return repository.updateStatusBefore(
                OrderStatus.ARCHIVED, cutoff);
    }
}
```

`@Modifying` chỉ thay đổi cách Spring Data thực thi truy vấn; nó không tự tạo ranh giới giao dịch. Hãy bảo đảm phương thức được gọi trong một transaction đang hoạt động, thường bằng `@Transactional` ở service hoặc trên phương thức repository phù hợp.

Các phương thức query được khai báo trực tiếp trong repository không nên được giả định là tự có cấu hình transaction giống các phương thức CRUD kế thừa. Đặt transaction boundary rõ ràng ở tầng service giúp dễ kiểm soát nhiều thao tác trong cùng nghiệp vụ.

## 5. Dùng flushAutomatically và clearAutomatically

`@Modifying` có hai thuộc tính quan trọng:

| Thuộc tính | Mặc định | Tác dụng |
|---|---:|---|
| `flushAutomatically` | `false` | Flush persistence context trước khi thực thi câu lệnh modifying query. |
| `clearAutomatically` | `false` | Clear persistence context sau khi modifying query thực thi thành công. |

Có thể bật cả hai:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    update PurchaseOrder p
    set p.status = :status
    where p.createdAt < :cutoff
    """)
int updateStatusBefore(
        @Param("status") OrderStatus status,
        @Param("cutoff") LocalDateTime cutoff);
```

### flushAutomatically

`flushAutomatically = true` yêu cầu Spring Data gọi `EntityManager.flush()` trước khi chạy bulk query.

Flush đồng bộ những thay đổi đang chờ của các entity managed xuống database. Điều này quan trọng nếu persistence context có thay đổi chưa được ghi mà câu lệnh bulk sắp chạy có thể tác động đến cùng dữ liệu.

Nếu bỏ qua flush, thứ tự giữa thay đổi đang chờ trong bộ nhớ và bulk DML có thể gây kết quả khó đoán theo kỳ vọng của ứng dụng. Flush trước giúp các thay đổi đang chờ được gửi xuống database trước khi câu lệnh bulk chạy.

Flush không phải commit. Transaction vẫn tiếp tục và có thể rollback toàn bộ các thay đổi khi có lỗi.

### clearAutomatically

`clearAutomatically = true` yêu cầu Spring Data gọi `EntityManager.clear()` sau khi bulk query thực thi thành công.

`clear()` tách **tất cả** entity đang managed khỏi persistence context hiện tại, không chỉ những entity bị ảnh hưởng bởi câu lệnh bulk. Lần truy vấn tiếp theo sẽ tải entity từ database vào persistence context mới hoặc tạo instance managed mới.

Khi bật clear, các biến Java đang giữ tham chiếu đến entity cũ vẫn tồn tại, nhưng entity đó đã detached. Giá trị thuộc tính trong biến không tự thay đổi. Hãy truy vấn lại để lấy instance mới.

Nên cân nhắc bật đồng thời `flushAutomatically = true` và `clearAutomatically = true` khi phương thức bulk có thể chạy trong persistence context chứa thay đổi chưa flush. Nếu chỉ clear mà chưa flush, các thay đổi đang chờ của entity bị detach có thể không được đồng bộ xuống database.

Ví dụ:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    delete from PurchaseOrder p
    where p.status = :status
    """)
int deleteAllWithStatus(@Param("status") OrderStatus status);
```

Sau phương thức này, persistence context hiện tại đã được clear. Những entity trước đó được tải qua repository cần được truy vấn lại trước khi sử dụng như entity managed.

## 6. Ba cách xử lý trạng thái lỗi thời

Không có một cách duy nhất phù hợp cho mọi tình huống. Hãy chọn thao tác theo số lượng entity bị ảnh hưởng và phạm vi persistence context cần đồng bộ.

### Cách 1: clear rồi truy vấn lại

Dùng khi bulk operation tác động đến nhiều entity và có thể làm nhiều đối tượng trong persistence context lỗi thời:

```java
@Transactional
public PurchaseOrder updateAndReload(Long id) {
    entityManager.createQuery("""
        update PurchaseOrder p
        set p.status = :status
        where p.id = :id
        """)
        .setParameter("status", OrderStatus.ARCHIVED)
        .setParameter("id", id)
        .executeUpdate();

    entityManager.clear();

    return entityManager.find(PurchaseOrder.class, id);
}
```

Sau `clear()`, các entity cũ đều detached. Lệnh `find()` tiếp theo tải lại dữ liệu và trả về instance managed mới.

Lưu ý: `clear()` tác động đến toàn bộ persistence context. Nếu có thay đổi cần giữ, hãy flush trước khi clear. Những tham chiếu cũ không tự biến thành tham chiếu đến instance mới.

### Cách 2: refresh một entity cụ thể

Dùng `refresh(entity)` khi chỉ cần đồng bộ một entity đang managed:

```java
@Transactional
public PurchaseOrder updateAndRefresh(Long id) {
    PurchaseOrder order =
            entityManager.find(PurchaseOrder.class, id);

    entityManager.createQuery("""
        update PurchaseOrder p
        set p.status = :status
        where p.id = :id
        """)
        .setParameter("status", OrderStatus.ARCHIVED)
        .setParameter("id", id)
        .executeUpdate();

    entityManager.refresh(order);

    return order;
}
```

`refresh()` đọc lại trạng thái từ database và ghi đè trạng thái hiện tại của entity managed. Nó không dùng được cho entity đã detached hoặc removed.

Cần thận trọng: nếu entity có thay đổi chưa flush, `refresh()` có thể làm mất các thay đổi đó vì trạng thái trong bộ nhớ bị thay bằng trạng thái database. Nếu có thay đổi cần bảo toàn, hãy flush trước khi refresh.

Nếu bulk method dùng `clearAutomatically = true`, entity đã bị detach sau câu lệnh. Không thể gọi `refresh()` trên instance detached đó; hãy truy vấn lại thay vì refresh.

### Cách 3: detach một entity cụ thể

`entityManager.detach(entity)` tách một entity khỏi persistence context:

```java
entityManager.detach(order);
```

Cách này hữu ích khi chỉ muốn ngừng theo dõi một entity. Tuy nhiên, `detach()` không tải dữ liệu mới và không cập nhật thuộc tính của đối tượng. Instance Java vẫn giữ giá trị cũ. Muốn đọc trạng thái mới, cần truy vấn lại entity bằng định danh.

So sánh nhanh:

| Thao tác | Phạm vi | Có tải trạng thái mới không? |
|---|---|---|
| `clear()` | Tất cả entity managed trong persistence context | Không; cần truy vấn lại. |
| `refresh(entity)` | Một entity managed | Có; ghi đè trạng thái trong bộ nhớ bằng trạng thái DB. |
| `detach(entity)` | Một entity | Không; chỉ tách khỏi persistence context. |
| `find()` sau clear | Entity được tìm theo định danh | Có; tải vào persistence context sau khi clear. |

## 7. Ví dụ quy trình an toàn với Spring Data JPA

Một phương thức service có thể thực hiện bulk update, sau đó đọc lại dữ liệu:

```java
@Service
public class OrderMaintenanceService {

    private final PurchaseOrderRepository repository;

    public OrderMaintenanceService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public PurchaseOrder archiveAndReload(Long id) {
        repository.updateStatusById(
                id, OrderStatus.ARCHIVED);

        // Phương thức repository được cấu hình clearAutomatically=true.
        // Truy vấn lại để lấy entity managed mới.
        return repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Không tìm thấy đơn hàng"));
    }
}
```

Repository có thể khai báo:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    update PurchaseOrder p
    set p.status = :status
    where p.id = :id
    """)
int updateStatusById(
        @Param("id") Long id,
        @Param("status") OrderStatus status);
```

Sau khi modifying query chạy, Spring Data clear persistence context. `findById()` tiếp theo tải lại entity. Kết quả trả về là instance managed trong persistence context hiện tại, nếu transaction vẫn còn hoạt động.

Nếu cần tiếp tục thao tác với nhiều entity khác đã tải trước đó, hãy nhớ rằng chúng cũng bị detach khi clear. Các thao tác tiếp theo cần tải lại hoặc merge theo đúng mục đích; không nên tiếp tục giả định các instance cũ vẫn managed.

## 8. Bulk operation có bỏ qua lifecycle và cascade không?

Có. JPQL bulk update/delete tác động trực tiếp lên database và không xử lý từng entity qua vòng đời thông thường của JPA.

Điều này có một số hệ quả:

- Các callback như `@PreUpdate`, `@PostUpdate`, `@PreRemove` và `@PostRemove` không được gọi cho từng entity bị tác động bởi bulk DML.
- Cơ chế cascade của JPA như `CascadeType.REMOVE` không được thực hiện như khi xóa entity từng đối tượng.
- Các entity liên quan không tự được tải lên rồi cập nhật hoặc xóa theo quan hệ.
- Ràng buộc khóa ngoại ở database vẫn có hiệu lực. Câu lệnh bulk delete có thể thất bại nếu còn bản ghi con tham chiếu và schema không cho phép xóa.
- Những quy tắc nghiệp vụ được đặt trong phương thức entity hoặc callback lifecycle không tự chạy.

Nếu nghiệp vụ yêu cầu cascade, kiểm tra dữ liệu hoặc callback cho từng entity, hãy cân nhắc xóa/cập nhật entity qua repository hoặc xử lý riêng các bước liên quan. Bulk DML phù hợp khi bạn chủ động chấp nhận các khác biệt về vòng đời để đạt hiệu năng.

Cũng cần phân biệt derived delete query như `deleteByStatus(...)` với một JPQL bulk delete được khai báo bằng `@Modifying @Query`. Derived delete của Spring Data có thể tải các entity phù hợp rồi xóa từng entity để cho phép lifecycle callback chạy; JPQL bulk delete là một lệnh DML trực tiếp và có ngữ nghĩa khác. Hãy kiểm tra loại phương thức repository đang dùng trước khi dựa vào callback hoặc cascade.

## 9. Ảnh hưởng đến @Version và optimistic locking

Bulk update/delete bỏ qua kiểm tra optimistic locking thông thường. Nếu entity dùng `@Version`, câu lệnh bulk không tự động tăng version như một lần cập nhật entity managed thông thường.

Ví dụ entity:

```java
@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private long version;

    // Các thuộc tính khác...
}
```

Một bulk update chỉ đổi `status` có thể để nguyên cột `version`. Một transaction khác đang giữ entity cũ có thể không nhận ra rằng bulk operation đã thay đổi dữ liệu, tùy vào cách câu lệnh và lần ghi tiếp theo được thực hiện.

Khi cần bảo toàn kiểm soát optimistic locking, hãy chủ động thiết kế điều kiện version và tăng version trong bulk query, ví dụ:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    update PurchaseOrder p
    set p.status = :status,
        p.version = p.version + 1
    where p.id = :id
      and p.version = :expectedVersion
    """)
int updateStatusWithVersion(
        @Param("id") Long id,
        @Param("status") OrderStatus status,
        @Param("expectedVersion") long expectedVersion);
```

Số hàng cập nhật trả về có thể dùng để xác định kết quả:

- `1`: tìm thấy hàng đúng định danh và version, cập nhật thành công.
- `0`: không có hàng phù hợp; có thể do bản ghi không tồn tại hoặc version đã thay đổi.

Ứng dụng cần quyết định cách phân biệt hai trường hợp nếu nghiệp vụ yêu cầu, chẳng hạn kiểm tra tồn tại riêng hoặc trả lỗi xung đột phù hợp.

Việc tăng version trong bulk query giúp các transaction khác đang giữ version cũ phát hiện xung đột khi flush. Tuy nhiên, persistence context hiện tại vẫn cần được clear hoặc refresh để không tiếp tục giữ version và thuộc tính cũ.

## 10. Những lỗi thường gặp

| Lỗi | Vì sao xảy ra | Cách khắc phục |
|---|---|---|
| Đọc entity ngay sau bulk update và nhận giá trị cũ | Entity managed chưa được đồng bộ với bulk DML. | Clear rồi truy vấn lại, hoặc refresh entity còn managed. |
| Gọi `findById()` lần nữa nhưng vẫn nhận dữ liệu cũ | First-level cache trả về instance đã managed. | Clear persistence context trước khi truy vấn lại. |
| Gọi `refresh()` sau khi đã clear | Entity cũ đã detached, không còn thuộc persistence context. | Dùng `find()` hoặc repository để tải instance mới. |
| Clear mà không flush thay đổi đang chờ | Các thay đổi chưa đồng bộ có thể mất khi entity bị detach. | Flush trước clear; cân nhắc `flushAutomatically=true`. |
| Cho rằng clear chỉ tách entity bị cập nhật | `EntityManager.clear()` tách tất cả entity managed. | Đánh giá phạm vi persistence context hoặc dùng refresh cho một entity. |
| Mong callback hoặc cascade chạy khi bulk delete | Bulk DML bỏ qua vòng đời entity thông thường. | Xử lý quan hệ và nghiệp vụ riêng hoặc xóa từng entity. |
| Cho rằng `@Version` tự tăng khi bulk update | Bulk DML bỏ qua cơ chế optimistic locking tự động. | Tự kiểm tra và tăng version trong câu lệnh nếu cần. |
| Dùng `@Modifying` mà thiếu transaction | Truy vấn thay đổi cần một giao dịch đang hoạt động. | Đặt `@Transactional` tại service hoặc phương thức thích hợp. |

## 11. Khi nào nên dùng bulk DML?

Bulk DML phù hợp khi:

- Cần cập nhật hoặc xóa nhiều hàng theo cùng một điều kiện.
- Không cần chạy callback lifecycle trên từng entity.
- Không cần cascade JPA tự động cho từng entity bị xóa.
- Có thể chủ động xử lý persistence context sau thao tác.
- Có chiến lược rõ ràng cho version, khóa ngoại và các quy tắc nghiệp vụ liên quan.

Nên cân nhắc thao tác từng entity khi:

- Mỗi entity cần logic nghiệp vụ khác nhau.
- Cần gọi phương thức domain trên từng đối tượng.
- Cần lifecycle callback hoặc cascade JPA.
- Cần kiểm tra optimistic locking theo cơ chế entity thông thường.
- Số lượng bản ghi đủ nhỏ để chi phí tải và xử lý từng entity chấp nhận được.

Không nên chọn bulk DML chỉ vì nó ít dòng mã hơn. Hãy cân đối hiệu năng với những hành vi JPA bị bỏ qua.

## 12. Checklist trước và sau bulk update/delete

Trước khi chạy:

- Xác định entity nào có thể đang managed trong persistence context.
- Kiểm tra có thay đổi nào đang chờ flush hay không.
- Bảo đảm thao tác nằm trong transaction phù hợp.
- Xác định lifecycle callback, cascade và `@Version` có ý nghĩa với nghiệp vụ không.
- Chọn rõ chiến lược flush và clear.

Sau khi chạy:

- Nếu bật `clearAutomatically`, truy vấn lại entity cần sử dụng.
- Nếu không clear, refresh các entity managed cụ thể có trạng thái đã bị bulk operation thay đổi.
- Không gọi `refresh()` trên entity detached.
- Không dùng lại các instance cũ như thể chúng đã được cập nhật.
- Kiểm tra số hàng bị tác động và xử lý trường hợp không có hàng phù hợp.
- Kiểm thử cả dữ liệu trong database và trạng thái entity được đọc lại trong cùng transaction.

Bulk update và bulk delete giúp Spring Data JPA xử lý số lượng lớn dữ liệu hiệu quả bằng câu lệnh trực tiếp. Đổi lại, persistence context không được tự đồng bộ với kết quả câu lệnh. Hiểu rõ khác biệt giữa flush, clear, refresh và detach sẽ giúp tránh đọc dữ liệu cũ, mất thay đổi chưa flush và ghi đè dữ liệu ngoài ý muốn.