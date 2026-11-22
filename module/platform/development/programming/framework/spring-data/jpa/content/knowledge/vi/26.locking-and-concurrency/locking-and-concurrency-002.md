# Khóa lạc quan bằng `@Version`

Trong ứng dụng Spring Data JPA, nhiều transaction có thể cùng đọc và sửa một bản ghi. Nếu hai transaction cùng đọc một giá trị cũ rồi lần lượt ghi lại, lần ghi sau có thể ghi đè kết quả của lần ghi trước. Hiện tượng này gọi là *lost update* (mất cập nhật).

Khóa lạc quan (optimistic locking) phát hiện xung đột tại thời điểm cập nhật hoặc xóa dữ liệu. Các transaction vẫn có thể đọc cùng một hàng mà không phải giữ khóa cơ sở dữ liệu trong suốt thời gian xử lý. Khi ghi, JPA kiểm tra phiên bản mà transaction đã đọc. Nếu phiên bản đã thay đổi, thao tác thất bại để ứng dụng xử lý xung đột.

## 1. Khi nào cần khóa lạc quan?

Giả sử kho có 10 sản phẩm và hai yêu cầu cùng đọc bản ghi với `quantity = 10`, `version = 4`:

1. Transaction A đọc số lượng 10, phiên bản 4.
2. Transaction B cũng đọc số lượng 10, phiên bản 4.
3. A đặt số lượng còn 9 và commit. Cơ sở dữ liệu lưu phiên bản 5.
4. B cố ghi số lượng 8 dựa trên phiên bản 4. Điều kiện phiên bản không còn đúng nên B không được phép ghi.

Nếu không kiểm tra phiên bản, B có thể ghi đè kết quả của A. Với khóa lạc quan, hệ thống phát hiện xung đột thay vì âm thầm làm mất cập nhật.

Cách tiếp cận này phù hợp khi xung đột ghi tương đối hiếm, còn thao tác đọc diễn ra thường xuyên. Nếu nhiều transaction liên tục tranh chấp cùng một hàng và cần tuần tự hóa thao tác, có thể cân nhắc khóa bi quan như `PESSIMISTIC_WRITE`. Khóa bi quan thường giữ khóa cơ sở dữ liệu trong transaction và làm tăng thời gian chờ.

## 2. Khai báo trường phiên bản bằng @Version

`@Version` là annotation của Jakarta Persistence, được import từ `jakarta.persistence.Version` trong Spring Boot 3 trở lên. Đặt annotation trên một trường hoặc getter của entity theo kiểu truy cập mà entity đang sử dụng. Mỗi entity có một thuộc tính version được JPA quản lý.

Các kiểu dữ liệu phiên bản chuẩn gồm `int`, `Integer`, `short`, `Short`, `long`, `Long` và `java.sql.Timestamp`. Ví dụ dưới đây dùng `Long`:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "inventory")
public class Inventory {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private int quantity;

    @Version
    @Column(name = "version_no", nullable = false)
    private Long version;

    protected Inventory() {
        // JPA cần constructor không tham số.
    }

    public Inventory(int quantity) {
        this.quantity = quantity;
    }

    public void reserve(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount phải lớn hơn 0");
        }
        if (quantity < amount) {
            throw new IllegalStateException("Không đủ hàng trong kho");
        }
        quantity -= amount;
    }

    public Long getId() {
        return id;
    }

    public int getQuantity() {
        return quantity;
    }

    public Long getVersion() {
        return version;
    }
}
```

`@Column(name = "version_no")` đặt tên cột phiên bản trong bảng. Nếu bỏ `@Column`, tên cột được suy ra theo quy tắc đặt tên của provider và cấu hình ứng dụng. Cột phiên bản phải tồn tại trong schema cơ sở dữ liệu. Khi nâng cấp hệ thống đang có dữ liệu, cần migration tạo cột và khởi tạo phiên bản cho các hàng cũ; ví dụ SQL sau cần điều chỉnh theo hệ quản trị cơ sở dữ liệu đang dùng:

```sql
ALTER TABLE inventory
ADD COLUMN version_no BIGINT NOT NULL DEFAULT 0;
```

Provider JPA, chẳng hạn Hibernate, khởi tạo và tăng giá trị version. Không tự gán hoặc tăng trường này trong logic nghiệp vụ. Dùng kiểu wrapper như `Long` cũng giúp phân biệt entity mới có version `null` với entity đã được lưu trong một số cơ chế nhận diện entity mới của Spring Data JPA.

## 3. JPA kiểm tra phiên bản như thế nào?

Với entity được quản lý trong persistence context, khi ứng dụng thay đổi trạng thái và transaction flush, provider thực hiện cập nhật kèm điều kiện phiên bản. SQL minh họa có dạng:

```sql
UPDATE inventory
SET quantity = ?, version_no = ?
WHERE id = ? AND version_no = ?;
```

Giả sử entity đang có version 4. Provider ghi dữ liệu mới với version 5 và chỉ cập nhật hàng có đúng `id` cùng version 4. Nếu một transaction khác đã cập nhật hàng đó lên version 5, câu lệnh không tìm thấy hàng phù hợp và số hàng bị ảnh hưởng bằng 0. Provider nhận biết dữ liệu đã lỗi thời và báo lỗi optimistic locking.

Đây là SQL minh họa cho cơ chế, không phải chuỗi SQL cố định mà mọi provider đều phải phát ra. Provider cũng có thể thực hiện kiểm tra tại thời điểm flush hoặc commit. Vì vậy, lỗi có thể xuất hiện khi gọi `flush()` hoặc khi transaction kết thúc, dù câu lệnh sửa entity đã chạy trước đó.

Vòng đời thường gặp:

- **Tạo mới:** ứng dụng persist entity; provider thiết lập giá trị version ban đầu.
- **Đọc:** entity nhận giá trị version hiện tại từ cơ sở dữ liệu.
- **Sửa:** provider dùng version đã đọc làm điều kiện cập nhật và tăng version nếu cập nhật thành công.
- **Xóa:** provider cũng kiểm tra phiên bản để tránh xóa một trạng thái đã bị transaction khác thay đổi.
- **Xung đột:** thao tác cập nhật hoặc xóa không khớp version sẽ phát sinh lỗi optimistic locking và transaction bị rollback.

Không cần khóa hàng ngay lúc đọc. Việc kiểm tra được thực hiện khi ghi, do đó hai transaction vẫn có thể cùng đọc một phiên bản.

## 4. Sử dụng với Spring Data JPA

Repository có thể khai báo bình thường:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryRepository
        extends JpaRepository<Inventory, Long> {
}
```

Trong service, tải entity trong transaction rồi thay đổi entity đang được quản lý:

```java
import jakarta.persistence.EntityNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void reserve(Long id, int amount) {
        Inventory inventory = repository.findById(id)
                .orElseThrow(() ->
                        new EntityNotFoundException("Không tìm thấy kho: " + id));

        inventory.reserve(amount);
        // Dirty checking ghi thay đổi khi transaction flush/commit.
        // Không cần gọi save() cho entity vẫn đang được quản lý.
    }
}
```

`@Transactional` tạo ranh giới transaction cho thao tác đọc và sửa. Vì entity được tải trong persistence context của transaction, Hibernate có thể phát hiện thay đổi bằng dirty checking và phát lệnh cập nhật khi flush. Gọi `repository.save(inventory)` sau khi sửa entity đang được quản lý thường không cần thiết, dù có thể xuất hiện trong một số quy ước codebase.

Nếu ứng dụng nhận một entity detached từ request hoặc từ transaction trước, thao tác `save()` của Spring Data JPA có thể đi qua `merge()`. Provider vẫn kiểm tra version khi đồng bộ trạng thái đó. Vì vậy, không nên bỏ trường version khỏi quy trình cập nhật nếu client cần phát hiện dữ liệu đã cũ.

## 5. Xử lý lỗi xung đột

Ở tầng JPA, lỗi thường là `jakarta.persistence.OptimisticLockException`. Khi đi qua cơ chế exception translation của Spring, ứng dụng thường nhận một ngoại lệ thuộc `OptimisticLockingFailureException`, chẳng hạn `ObjectOptimisticLockingFailureException`.

Lỗi có thể xuất hiện tại flush hoặc commit. Nếu cần phát hiện sớm trong transaction, có thể gọi `repository.flush()` hoặc `EntityManager.flush()`; thao tác này buộc provider đồng bộ các thay đổi đang chờ. Nó không làm transaction commit sớm.

Cách xử lý nên phù hợp với nghiệp vụ:

- Thông báo cho người dùng rằng dữ liệu đã được người khác thay đổi, tải lại dữ liệu mới và yêu cầu xác nhận hoặc áp dụng lại thao tác.
- Với API cập nhật từ client, có thể trả HTTP 409 Conflict để client biết trạng thái gửi lên đã cũ.
- Chỉ tự retry khi thao tác có thể thực hiện lại an toàn. Mỗi lần retry phải dùng transaction mới, đọc lại dữ liệu mới nhất và tính lại thay đổi nghiệp vụ.
- Không bắt lỗi rồi tiếp tục dùng transaction đã thất bại. Transaction có thể đã bị đánh dấu rollback-only; hãy để transaction kết thúc và xử lý ở ranh giới bên ngoài.

Không nên tự động ghi đè bằng dữ liệu cũ. Ví dụ, nếu hai người cùng sửa số lượng hoặc số dư, ứng dụng cần quyết định nghiệp vụ trên giá trị mới nhất thay vì chỉ gửi lại toàn bộ object cũ.

## 6. Những trường hợp cần chú ý

### Cập nhật hàng loạt bằng JPQL

Các câu lệnh bulk update/delete dùng `@Modifying` chạy trực tiếp trên cơ sở dữ liệu và bỏ qua cơ chế dirty checking của entity đang được quản lý. JPA không tự thực hiện optimistic locking check cho các bulk update này và persistence context cũng không tự đồng bộ theo kết quả câu lệnh.

Nếu vẫn cần cập nhật hàng loạt có kiểm tra phiên bản, phải tự đưa version mong đợi vào điều kiện và tự tăng version. Ví dụ:

```java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Query("""
    update Inventory i
       set i.quantity = :quantity,
           i.version = i.version + 1
     where i.id = :id
       and i.version = :expectedVersion
    """)
int updateIfVersionMatches(
        @Param("id") Long id,
        @Param("expectedVersion") Long expectedVersion,
        @Param("quantity") int quantity);
```

Nếu phương thức trả về 0 hàng được cập nhật, bản ghi không tồn tại hoặc version không còn khớp; ứng dụng cần phân biệt hai trường hợp nếu nghiệp vụ yêu cầu. Với native SQL, phải tự thực hiện cùng nguyên tắc. Sau bulk update, cần chú ý persistence context có thể đang giữ entity cũ; có thể clear hoặc refresh phù hợp.

### Không cập nhật version bằng tay trong luồng entity thông thường

Không viết `version++` trong phương thức nghiệp vụ và không gửi một version mới do client tự chọn để ghi vào entity. Provider chịu trách nhiệm tăng version. Client chỉ nên gửi version đã đọc như một giá trị kỳ vọng để server phát hiện xung đột.

### Cập nhật qua nhiều đường ghi

Khóa lạc quan chỉ bảo vệ những đường ghi có thực hiện kiểm tra version. Nếu một tiến trình khác sửa cùng bảng bằng SQL trực tiếp, batch job hoặc bulk update mà không kiểm tra và tăng version, cơ chế có thể không phát hiện được xung đột đó. Mọi đường ghi liên quan cần tuân theo cùng quy ước phiên bản.

### Version không thay thế ràng buộc dữ liệu

`@Version` giải quyết xung đột giữa các lần cập nhật entity. Nó không thay thế khóa ngoại, unique constraint, check constraint hay quy tắc nghiệp vụ. Ví dụ, nếu yêu cầu không cho phép số lượng âm, vẫn cần kiểm tra trong nghiệp vụ và cân nhắc ràng buộc ở cơ sở dữ liệu để bảo vệ dữ liệu trước mọi đường ghi.

## 7. Kiểm thử tình huống cập nhật đồng thời

Một kiểm thử tích hợp cần dùng hai transaction độc lập:

1. Tạo một hàng inventory và commit.
2. Transaction A đọc hàng đó; transaction B cũng đọc cùng hàng trước khi A cập nhật.
3. A thay đổi số lượng và commit. Version trong cơ sở dữ liệu được tăng.
4. B sửa object đã đọc từ trước và cố flush hoặc commit.
5. Xác nhận B nhận lỗi optimistic locking, transaction B rollback, còn dữ liệu đã commit từ A được giữ nguyên.

Điểm quan trọng là hai lần đọc phải giữ cùng version ban đầu, còn lần ghi thứ hai phải chạy trong transaction khác. Nếu kiểm thử tất cả trong một persistence context, nó không tái hiện được xung đột giữa hai bản đọc độc lập.

Ví dụ kiểm thử có thể dùng `TransactionTemplate` để tạo các ranh giới transaction rõ ràng, hoặc `@Transactional` kết hợp hai thread và hai transaction manager context riêng. Khi kiểm tra lỗi, hãy flush trong transaction ghi thứ hai để lỗi xuất hiện ngay tại vị trí assertion thay vì chỉ xuất hiện khi framework commit transaction.

## 8. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc xử lý |
|---|---|---|
| Không phát hiện xung đột | Entity thiếu `@Version` hoặc một đường ghi bỏ qua version | Kiểm tra mapping và tất cả luồng ghi vào bảng |
| Lỗi chỉ xuất hiện lúc commit | Provider trì hoãn SQL đến flush/commit | Flush trong phạm vi cần kiểm tra hoặc xử lý exception bên ngoài transaction |
| Cập nhật hàng loạt không tăng version | Bulk JPQL/native SQL không tự áp dụng optimistic locking | Thêm điều kiện version và tăng version tường minh |
| Entity mới có version không hợp lệ | Ứng dụng tự gán version hoặc schema chưa được migration đúng | Để provider quản lý version và kiểm tra cột trong database |
| Retry vẫn liên tục thất bại | Retry dùng lại entity hoặc version cũ | Mở transaction mới, đọc lại trạng thái mới và tính lại nghiệp vụ |
| Transaction tiếp tục sau khi bắt lỗi | Transaction đã bị đánh dấu rollback-only | Để transaction rollback và xử lý ở tầng gọi bên ngoài |

## 9. Checklist khi triển khai

- Entity có đúng một thuộc tính được đánh dấu `@Version` và dùng kiểu được JPA hỗ trợ.
- Cột version tồn tại, có giá trị hợp lệ cho dữ liệu cũ và được ánh xạ đúng tên.
- Không có code nghiệp vụ tự tăng hoặc ghi đè version.
- Các thao tác sửa entity chạy trong transaction phù hợp.
- Bulk update, native SQL và batch job có quy tắc kiểm tra/tăng version riêng.
- Ứng dụng xử lý lỗi xung đột theo nghiệp vụ, không âm thầm ghi đè dữ liệu mới.
- Kiểm thử tích hợp mô phỏng hai transaction đọc cùng version và xác nhận lần ghi sau bị từ chối.

Khóa lạc quan bằng `@Version` là lựa chọn gọn cho các entity thường được đọc nhiều và ít khi bị cập nhật đồng thời. Cơ chế chỉ phát huy đầy đủ khi mọi đường ghi vào dữ liệu đều tôn trọng version và ứng dụng có cách xử lý xung đột rõ ràng.