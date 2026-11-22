# Khóa bi quan và các LockModeType phù hợp trong Spring Data JPA

## Mục tiêu

Sau bài này, bạn có thể giải thích khi nào cần khóa bi quan; phân biệt `PESSIMISTIC_READ`, `PESSIMISTIC_WRITE` và `PESSIMISTIC_FORCE_INCREMENT`; áp dụng `@Lock` trên repository method; giữ khóa trong transaction đúng phạm vi; cấu hình timeout và lock scope; xử lý timeout, deadlock; và kiểm thử hành vi đồng thời trên database mục tiêu.

Các ví dụ dùng Java 17+, Spring Boot 3+, Spring Data JPA và Jakarta Persistence (`jakarta.persistence.*`). Khóa bi quan được thực thi bởi database thông qua JPA provider và JDBC driver. SQL cụ thể có thể khác giữa PostgreSQL, MySQL, SQL Server, Oracle và các hệ quản trị khác.

## 1. Vì sao cần khóa bi quan?

Khi nhiều transaction cùng đọc và cập nhật một bản ghi, kết quả có thể phụ thuộc vào thứ tự thực thi. Ví dụ kho còn 5 sản phẩm. Hai request cùng đọc số lượng 5; mỗi request muốn đặt 4 sản phẩm. Nếu cả hai cùng kiểm tra trên giá trị cũ rồi cùng ghi, hệ thống có thể chấp nhận tổng cộng 8 sản phẩm dù kho chỉ có 5. Đây là một dạng race condition và lost update.

Khóa bi quan (pessimistic locking) yêu cầu database khóa bản ghi liên quan để transaction khác phải chờ hoặc không thể thực hiện một thao tác xung đột cho tới khi khóa được giải phóng. Cách này hữu ích khi:

- Xung đột cập nhật có khả năng xảy ra thường xuyên.
- Một thao tác cần đọc trạng thái hiện tại, kiểm tra điều kiện rồi cập nhật trong cùng transaction.
- Không thể chấp nhận hai transaction cùng vượt qua một điều kiện nghiệp vụ dựa trên dữ liệu cũ.
- Cần tuần tự hóa thao tác trên một hoặc một nhóm bản ghi đã xác định.

Khóa bi quan có chi phí: transaction giữ khóa lâu có thể làm request khác chờ, giảm throughput hoặc gây deadlock. Chỉ khóa những hàng cần thiết và giữ transaction ngắn.

## 2. LockModeType trong Jakarta Persistence

`jakarta.persistence.LockModeType` mô tả cách JPA yêu cầu khóa entity. Các mode thường gặp được chia thành nhóm optimistic và pessimistic:

| LockModeType | Nhóm | Ý nghĩa thực tế |
| --- | --- | --- |
| `NONE` | Không yêu cầu khóa | Không yêu cầu kiểm tra hoặc khóa bổ sung ngoài cơ chế mặc định của provider/database |
| `OPTIMISTIC` | Lạc quan | Kiểm tra version khi transaction hoàn tất; phát hiện xung đột thay vì khóa hàng trong lúc đọc |
| `OPTIMISTIC_FORCE_INCREMENT` | Lạc quan | Kiểm tra và tăng version của entity versioned |
| `PESSIMISTIC_READ` | Bi quan | Yêu cầu khóa đọc dùng chung; transaction khác có thể đọc nhưng không được cập nhật/xóa theo cách xung đột |
| `PESSIMISTIC_WRITE` | Bi quan | Yêu cầu khóa ghi độc quyền; transaction khác cần khóa hoặc sửa cùng hàng thường phải chờ |
| `PESSIMISTIC_FORCE_INCREMENT` | Bi quan | Khóa ghi bi quan và buộc tăng version của entity có `@Version` |

Khi mục tiêu là ngăn transaction khác sửa một hàng trong lúc kiểm tra rồi cập nhật, `PESSIMISTIC_WRITE` thường là lựa chọn phù hợp. `PESSIMISTIC_READ` dành cho trường hợp cần bảo vệ dữ liệu khỏi thay đổi trong khi đọc và database/provider hỗ trợ shared lock đúng như mong đợi. `PESSIMISTIC_FORCE_INCREMENT` chỉ nên dùng khi cần cả khóa ghi lẫn thay đổi version token.

### 2.1. Đừng nhầm READ và WRITE với khóa bi quan

Các tên `READ` và `WRITE` trong enum là tên tương thích cũ của nhóm optimistic:

- `READ` tương đương `OPTIMISTIC`.
- `WRITE` tương đương `OPTIMISTIC_FORCE_INCREMENT`.

Vì vậy, `LockModeType.READ` không có nghĩa là database lấy shared pessimistic lock; `LockModeType.WRITE` cũng không có nghĩa là lấy exclusive pessimistic lock. Khi cần khóa bi quan, hãy viết rõ `PESSIMISTIC_READ` hoặc `PESSIMISTIC_WRITE`.

## 3. PESSIMISTIC_READ, PESSIMISTIC_WRITE và PESSIMISTIC_FORCE_INCREMENT

### 3.1. PESSIMISTIC_READ

`PESSIMISTIC_READ` yêu cầu khóa đọc để ngăn transaction khác cập nhật hoặc xóa entity đang được khóa cho tới khi transaction hiện tại kết thúc. Nhiều transaction có thể cùng giữ khóa đọc trên một hàng nếu database hỗ trợ shared lock.

Mode này phù hợp khi cần đọc một trạng thái ổn định trong một transaction và muốn chặn cập nhật đồng thời. Tuy nhiên, database hoặc JPA provider có thể triển khai bằng khóa mạnh hơn, chẳng hạn nâng thành khóa ghi. Không giả định rằng mode này luôn cho phép nhiều reader chạy đồng thời; kiểm tra SQL và hành vi trên database thực tế.

### 3.2. PESSIMISTIC_WRITE

`PESSIMISTIC_WRITE` yêu cầu khóa ghi độc quyền trên entity. Transaction khác muốn lấy khóa xung đột hoặc cập nhật cùng hàng sẽ thường phải chờ tới khi khóa được giải phóng hoặc bị timeout.

Đây là lựa chọn phổ biến cho các thao tác như trừ tồn kho, giữ chỗ, chuyển trạng thái đơn hàng hoặc cập nhật một hạn mức dùng chung. Hãy lấy khóa trước khi đọc giá trị dùng để ra quyết định, kiểm tra điều kiện và ghi thay đổi trong cùng transaction.

### 3.3. PESSIMISTIC_FORCE_INCREMENT

`PESSIMISTIC_FORCE_INCREMENT` lấy khóa ghi bi quan và buộc tăng trường version của entity có `@Version`. Nó hữu ích khi một thao tác cần làm thay đổi version token để các transaction khác nhận biết trạng thái đã được đồng bộ, kể cả khi nghiệp vụ không thay đổi một thuộc tính thông thường.

Chỉ dùng mode này khi entity được version hóa và có lý do nghiệp vụ rõ ràng để tăng version. Nếu chỉ cần ngăn cập nhật đồng thời trong một transaction, `PESSIMISTIC_WRITE` thường đơn giản hơn.

## 4. Ví dụ entity có version và số lượng tồn kho

Entity `Inventory` minh họa một mặt hàng có số lượng khả dụng. `@Version` cho phép JPA thực hiện kiểm tra optimistic version khi ghi; nó có thể cùng tồn tại với pessimistic lock.

```java
package com.example.learning.inventory;

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

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private int available;

    @Version
    private long version;

    protected Inventory() {
    }

    public Inventory(String sku, int available) {
        this.sku = sku;
        this.available = available;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public int getAvailable() { return available; }
    public long getVersion() { return version; }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (available < quantity) {
            throw new IllegalStateException("insufficient inventory");
        }
        available -= quantity;
    }
}
```

`reserve` chứa quy tắc nghiệp vụ của entity. Phương thức không tự ghi SQL; khi entity đang managed và transaction commit, JPA dirty checking sẽ phát hiện `available` thay đổi và đồng bộ xuống database.

## 5. Dùng @Lock trên repository method

Spring Data JPA cung cấp annotation `org.springframework.data.jpa.repository.Lock`. Annotation này gắn `LockModeType` vào query mà repository thực thi:

```java
package com.example.learning.inventory;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import jakarta.persistence.LockModeType;

public interface InventoryRepository extends JpaRepository<Inventory, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select i from Inventory i where i.id = :id")
    Optional<Inventory> findByIdForUpdate(@Param("id") Long id);

    @Lock(LockModeType.PESSIMISTIC_READ)
    @Query("select i from Inventory i where i.sku = :sku")
    Optional<Inventory> findBySkuForRead(@Param("sku") String sku);
}
```

Method `findByIdForUpdate` trả entity được chọn với lock mode `PESSIMISTIC_WRITE`. Tên method `ForUpdate` giúp caller hiểu ý định, nhưng tên method tự nó không tạo khóa; annotation `@Lock` mới đặt lock mode.

Có thể đặt `@Lock` trên derived query method hoặc redeclare một CRUD method để thêm lock mode:

```java
@Override
@Lock(LockModeType.PESSIMISTIC_WRITE)
Optional<Inventory> findById(Long id);
```

Khi redeclare `findById`, mọi caller của method đó đều dùng lock ghi. Hãy cân nhắc phạm vi ảnh hưởng; một method riêng như `findByIdForUpdate` thường thể hiện rõ use case nào thực sự cần khóa.

`@Lock` chỉ cấu hình lock mode cho query. Nó không tự mở transaction cho toàn bộ logic nghiệp vụ của caller. Hãy đặt transaction ở service để query lấy khóa, kiểm tra dữ liệu và cập nhật nằm trong cùng một ranh giới.

## 6. Giữ khóa trong transaction ở service

Ví dụ service thực hiện đặt trước hàng tồn kho:

```java
package com.example.learning.inventory;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {
    private final InventoryRepository inventoryRepository;

    public InventoryService(InventoryRepository inventoryRepository) {
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void reserve(Long inventoryId, int quantity) {
        Inventory inventory = inventoryRepository.findByIdForUpdate(inventoryId)
            .orElseThrow(() -> new IllegalArgumentException("inventory not found"));

        inventory.reserve(quantity);
    }
}
```

Trình tự:

1. Spring mở transaction khi lời gọi đi qua transactional proxy.
2. Repository thực hiện query và yêu cầu database lấy `PESSIMISTIC_WRITE` lock.
3. Nếu transaction khác đang giữ khóa xung đột, query có thể chờ hoặc timeout.
4. Sau khi lấy được khóa, service kiểm tra và giảm số lượng trên entity managed.
5. Khi transaction commit hoặc rollback, database giải phóng khóa.

Không cần gọi `save(inventory)` trong ví dụ này vì entity đã managed trong persistence context và thay đổi được ghi bằng dirty checking khi flush/commit. Gọi `save` thêm không làm khóa mạnh hơn.

Đối với luồng ghi, dùng transaction thông thường (`readOnly = false`, là mặc định). Không đánh dấu transaction này `readOnly = true` vì mục tiêu của nó là cập nhật tồn kho và database/provider có thể xử lý read-only transaction theo cách không phù hợp với thao tác ghi.

### 6.1. Transaction phải bao trùm toàn bộ thao tác

Không lấy khóa trong một transaction ngắn rồi cập nhật ở transaction khác. Khi transaction đầu kết thúc, khóa được giải phóng; thao tác cập nhật sau đó không còn được bảo vệ.

`@Transactional` của Spring thường hoạt động qua proxy. Một method public được gọi từ bean khác sẽ đi qua proxy. Nếu một method trong cùng object tự gọi method khác có `@Transactional` (self-invocation), lời gọi nội bộ thường không đi qua proxy và có thể không mở transaction như mong đợi. Hãy đặt transaction ở public service method được gọi từ bên ngoài bean hoặc tổ chức lời gọi qua bean phù hợp.

Giữ transaction ngắn: không gọi HTTP service, gửi email, chờ người dùng hoặc thực hiện tác vụ chậm trong khi giữ khóa. Những thao tác đó làm connection và row lock bị giữ lâu, khiến request khác phải chờ.

## 7. Lock timeout và QueryHints

Khi một hàng đang bị transaction khác khóa, query lấy khóa có thể chờ. Có thể yêu cầu timeout qua hint chuẩn của Jakarta Persistence:

```java
import jakarta.persistence.LockModeType;
import jakarta.persistence.QueryHint;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.QueryHints;

@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(value = {
    @QueryHint(name = "jakarta.persistence.lock.timeout", value = "3000")
})
@Query("select i from Inventory i where i.id = :id")
Optional<Inventory> findByIdForUpdateWithTimeout(@Param("id") Long id);
```

`jakarta.persistence.lock.timeout` nhận giá trị timeout tính bằng mili giây theo quy ước của hint. Đây là hint mà provider chuyển xuống database/driver; mức hỗ trợ và cách thực thi có thể khác nhau. Một số hệ quản trị không hỗ trợ timeout theo từng câu query hoặc provider có thể bỏ qua hint. Hãy xác minh trên database mục tiêu, không xem giá trị `3000` là cam kết mọi request sẽ chờ đúng ba giây.

Không nhầm lock timeout với transaction timeout của Spring. Lock timeout giới hạn thời gian chờ lấy khóa; transaction timeout giới hạn thời gian thực thi transaction theo cấu hình transaction manager/provider. Hai giới hạn giải quyết hai vấn đề khác nhau.

## 8. Lock scope: NORMAL và EXTENDED

Jakarta Persistence định nghĩa `PessimisticLockScope` để mô tả phạm vi hàng được khóa:

| Scope | Phạm vi |
| --- | --- |
| `NORMAL` | Các hàng thuộc entity đang khóa, bao gồm các bảng phụ dùng để lưu trạng thái của entity |
| `EXTENDED` | Phạm vi NORMAL và thêm hàng trong join table của các quan hệ mà entity sở hữu |

`EXTENDED` không có nghĩa là khóa toàn bộ entity được tham chiếu bởi quan hệ. Ví dụ, khóa một customer có collection many-to-many có thể mở rộng tới hàng join table thuộc quan hệ đó, nhưng không tự động khóa trạng thái của mọi entity ở đầu bên kia.

Có thể yêu cầu scope bằng hint:

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(value = {
    @QueryHint(name = "jakarta.persistence.lock.scope", value = "EXTENDED")
})
@Query("select i from Inventory i where i.id = :id")
Optional<Inventory> findWithExtendedLockScope(@Param("id") Long id);
```

Chỉ tăng scope khi nghiệp vụ cần bảo vệ các hàng liên quan. Phạm vi khóa rộng làm tăng khả năng contention và deadlock. Provider/database có thể có giới hạn về cách triển khai; hãy kiểm tra hành vi thực tế.

## 9. Dùng EntityManager khi cần khóa theo chương trình

Ngoài repository `@Lock`, có thể yêu cầu khóa qua `EntityManager`. Cách này hữu ích trong custom repository hoặc khi cần chọn lock mode theo nhánh nghiệp vụ:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.LockModeType;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class InventoryLockRepository {
    private final EntityManager entityManager;

    public InventoryLockRepository(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional
    public Inventory findForUpdate(Long id) {
        Inventory inventory = entityManager.find(Inventory.class, id);
        if (inventory == null) {
            return null;
        }
        entityManager.lock(inventory, LockModeType.PESSIMISTIC_WRITE);
        return inventory;
    }
}
```

Các API liên quan:

- `entityManager.find(Entity.class, id, lockMode)` tải entity với lock mode được chỉ định.
- `entityManager.lock(managedEntity, lockMode)` yêu cầu khóa cho entity đang managed.
- `entityManager.refresh(entity, lockMode)` tải lại trạng thái database và có thể yêu cầu khóa cùng lúc.

`lock` yêu cầu entity thuộc persistence context hiện tại. `refresh` ghi đè trạng thái trong bộ nhớ bằng trạng thái database; không gọi nó sau khi đã có thay đổi chưa flush mà bạn muốn giữ lại. Các thao tác lấy khóa cần transaction đang hoạt động.

## 10. Database thực thi khóa như thế nào?

JPA mô tả ý định khóa ở mức API. Provider tạo SQL phù hợp với dialect và database. Nhiều hệ quản trị dùng câu lệnh tương tự `SELECT ... FOR UPDATE` cho khóa ghi; một số dùng cú pháp khác hoặc cơ chế riêng.

Không giả định:

- `PESSIMISTIC_READ` luôn được triển khai bằng một shared row lock riêng biệt.
- Một câu query luôn chỉ khóa đúng một hàng nếu query có join hoặc database dùng lock escalation.
- Lock mode bảo vệ các hàng chưa tồn tại hoặc mọi bản ghi thỏa điều kiện trong tương lai.
- Các database khác nhau có cùng hành vi với một isolation level hoặc một lock hint.

Index trên điều kiện tìm hàng được khóa giúp database định vị bản ghi nhanh hơn và có thể giảm thời gian giữ khóa. Tuy nhiên, loại khóa thực tế, khóa phạm vi/range và khả năng lock escalation phụ thuộc database, isolation level, execution plan và câu SQL do provider tạo ra.

Khi dùng `PESSIMISTIC_WRITE`, hãy bật log SQL hoặc quan sát database để hiểu câu lệnh và lock wait. Kiểm tra trên đúng phiên bản database chạy production.

## 11. Locking query, join và bản ghi không tồn tại

Lock mode được áp dụng cho entity mà query trả về theo quy tắc JPA/provider. Nếu query trả projection hoặc scalar thay vì entity, đừng mặc định rằng entity gốc đã được khóa như mong muốn. Với thao tác cần khóa, ưu tiên query trả entity và kiểm tra SQL thực tế.

Khi query join nhiều bảng, database có thể khóa thêm hàng hoặc khóa theo cách khác dự kiến. Tránh join không cần thiết trong query lấy khóa. Nếu cần bảo vệ nhiều entity, xác định rõ thứ tự lấy khóa và phạm vi từng query.

Một hàng không tồn tại không thể được khóa như một entity hiện có bằng `findByIdForUpdate`. Nếu hai transaction cùng kiểm tra một mã chưa tồn tại rồi cùng insert, row lock trên kết quả rỗng không bảo vệ được khoảng trống đó ở mọi database. Dùng unique constraint để bảo đảm tính duy nhất, xử lý xung đột insert, hoặc chọn isolation/advisory lock phù hợp với database nếu nghiệp vụ cần khóa một key chưa có hàng.

## 12. Timeout, deadlock và exception

Khóa bi quan có thể dẫn tới các lỗi vận hành cần xử lý rõ:

- **Lock timeout:** transaction chờ quá thời gian cho phép để lấy khóa.
- **Deadlock:** transaction A giữ khóa mà B cần, trong khi B giữ khóa mà A cần; database chọn một transaction làm nạn nhân và rollback.
- **Database lock error:** lỗi riêng của driver/database khi không thể lấy hoặc duy trì khóa.

Jakarta Persistence có hai exception đáng chú ý:

| Exception | Ý nghĩa theo JPA |
| --- | --- |
| `LockTimeoutException` | Hết thời gian chờ khóa và chỉ statement bị rollback theo hợp đồng JPA; transaction có thể vẫn còn hoạt động |
| `PessimisticLockException` | Không lấy được khóa và transaction bị rollback ở cấp transaction |

Spring có thể dịch exception từ provider/JDBC thành các exception thuộc hệ thống `DataAccessException`, ví dụ nhóm lỗi không lấy được khóa. Loại exception quan sát được phụ thuộc provider, driver và transaction manager; không bắt duy nhất một lớp JPA rồi giả định mọi lỗi đều có cùng dạng.

Khi gặp deadlock hoặc timeout, hãy để transaction kết thúc theo trạng thái rollback của nó. Nếu retry, retry toàn bộ use case trong transaction mới, có giới hạn số lần và backoff; chỉ retry khi thao tác có thể thực hiện an toàn nhiều lần. Không tiếp tục cập nhật trong một transaction đã bị đánh dấu rollback-only.

## 13. Giảm deadlock và contention

Các thực hành giúp giảm thời gian chờ và deadlock:

1. Giữ transaction ngắn và chỉ khóa những hàng cần thiết.
2. Lấy khóa theo một thứ tự nhất quán, chẳng hạn tăng dần theo ID, trong mọi luồng nghiệp vụ.
3. Không gọi dịch vụ bên ngoài hoặc chờ thao tác I/O khi đang giữ khóa.
4. Tạo index phù hợp cho điều kiện tìm hàng được khóa.
5. Tránh khóa collection/quan hệ rộng nếu không cần.
6. Chọn `PESSIMISTIC_READ` khi chỉ cần bảo vệ đọc và database thực sự hỗ trợ hành vi đó; dùng `PESSIMISTIC_WRITE` khi cần loại trừ cập nhật đồng thời.
7. Theo dõi thời gian lock wait, số deadlock, số timeout và connection pool.

Nếu một thao tác cần khóa nhiều hàng, hãy xác định thứ tự khóa trước khi triển khai. Hai code path lấy cùng hai hàng theo thứ tự ngược nhau là nguyên nhân deadlock phổ biến.

## 14. So sánh khóa bi quan với khóa lạc quan

| Tiêu chí | Pessimistic locking | Optimistic locking |
| --- | --- | --- |
| Cách bảo vệ | Database khóa hàng trong transaction | Dùng version để phát hiện xung đột khi ghi/commit |
| Khi xung đột xảy ra | Transaction khác có thể chờ hoặc timeout | Một transaction có thể thất bại với optimistic lock exception |
| Phù hợp | Xung đột thường xuyên, cần tuần tự hóa thao tác | Xung đột ít, đọc nhiều, muốn tránh giữ khóa lâu |
| Chi phí chính | Lock wait, contention, deadlock và connection bị giữ | Retry hoặc xử lý conflict khi version thay đổi |
| Annotation/API | `@Lock(PESSIMISTIC_WRITE)` | `@Version`, `OPTIMISTIC` hoặc `OPTIMISTIC_FORCE_INCREMENT` |

Không có lựa chọn tốt nhất cho mọi use case. Nếu xung đột hiếm, `@Version` thường đơn giản và mở rộng tốt. Nếu thao tác phải kiểm tra rồi cập nhật một trạng thái dùng chung và xung đột thường xuyên, pessimistic write lock có thể phù hợp hơn. Đo dưới tải thực tế trước khi quyết định.

## 15. Kiểm thử repository lock

Có thể bắt đầu bằng integration test để xác nhận repository method có thể thực thi truy vấn khóa:

```java
package com.example.learning.inventory;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class InventoryLockRepositoryTest {
    @Autowired
    private InventoryRepository inventoryRepository;

    @Test
    void loadsInventoryUsingPessimisticWriteQuery() {
        Inventory saved = inventoryRepository.saveAndFlush(
            new Inventory("SKU-1", 5)
        );

        Inventory locked = inventoryRepository.findByIdForUpdate(saved.getId())
            .orElseThrow();

        assertThat(locked.getAvailable()).isEqualTo(5);
    }
}
```

`@DataJpaTest` thường chạy test trong transaction và rollback khi test kết thúc. Test này xác nhận mapping, query và lock request hoạt động trong môi trường test; nó chưa chứng minh transaction thứ hai thật sự bị block.

Để kiểm tra contention, cần integration test có hai transaction độc lập trên hai thread hoặc hai connection:

1. Transaction A lấy `PESSIMISTIC_WRITE` trên một inventory row rồi giữ transaction mở có kiểm soát.
2. Transaction B thử lấy cùng khóa.
3. Xác nhận B chờ hoặc timeout theo cấu hình database/driver.
4. Cho A commit/rollback và xác nhận B tiếp tục hoặc nhận lỗi phù hợp.

Dùng latch/barrier để điều phối test thay vì `sleep` tùy ý. Chạy test này trên cùng loại database và driver với production; H2 có thể khác PostgreSQL, MySQL, SQL Server hoặc Oracle về lock semantics và timeout.

## 16. Các lỗi thường gặp

- **Dùng `READ` khi muốn khóa đọc bi quan.** `READ` là alias của `OPTIMISTIC`; dùng `PESSIMISTIC_READ`.
- **Dùng `WRITE` khi muốn khóa ghi bi quan.** `WRITE` là alias của `OPTIMISTIC_FORCE_INCREMENT`; dùng `PESSIMISTIC_WRITE`.
- **Cho rằng `@Lock` tự mở transaction.** Đặt `@Transactional` ở service bao quanh query, kiểm tra và cập nhật.
- **Lấy khóa rồi kết thúc transaction trước khi cập nhật.** Khóa được giải phóng khi transaction kết thúc; giữ cả thao tác trong một transaction.
- **Dùng `PESSIMISTIC_WRITE` cho mọi truy vấn.** Chỉ khóa nơi có yêu cầu đồng thời thực sự; khóa quá rộng làm giảm throughput.
- **Cho rằng `PESSIMISTIC_READ` luôn là shared lock.** Provider/database có thể dùng khóa mạnh hơn.
- **Gọi dịch vụ ngoài khi đang giữ khóa.** Transaction kéo dài và làm tăng lock wait.
- **Không đặt thứ tự khóa nhất quán.** Nhiều luồng lấy khóa theo thứ tự khác nhau có thể deadlock.
- **Cố khóa một hàng chưa tồn tại.** Dùng unique constraint hoặc cơ chế khóa key phù hợp; query trả rỗng không khóa được entity không có.
- **Dựa vào timeout hint mà không kiểm tra driver.** Hint có thể bị bỏ qua hoặc hỗ trợ khác nhau.
- **Chỉ test bằng H2 rồi suy ra production.** Kiểm thử contention trên đúng database mục tiêu.
- **Retry tiếp trong transaction đã rollback-only.** Kết thúc transaction lỗi và retry toàn bộ thao tác trong transaction mới nếu an toàn.

## 17. Checklist trước khi triển khai

- [ ] Có lý do nghiệp vụ rõ ràng để dùng pessimistic thay vì optimistic locking.
- [ ] Chọn đúng `PESSIMISTIC_READ`, `PESSIMISTIC_WRITE` hoặc `PESSIMISTIC_FORCE_INCREMENT`.
- [ ] Không nhầm `READ`/`WRITE` với các mode bi quan.
- [ ] Repository method có `@Lock` trên query trả entity phù hợp.
- [ ] Service transaction bao trùm lấy khóa, kiểm tra và cập nhật.
- [ ] Transaction không thực hiện I/O bên ngoài hoặc công việc kéo dài khi đang giữ khóa.
- [ ] Timeout và lock scope được kiểm thử trên provider/database thực tế.
- [ ] Điều kiện query có index phù hợp và phạm vi khóa đủ hẹp.
- [ ] Thứ tự lấy nhiều khóa nhất quán giữa các luồng nghiệp vụ.
- [ ] Có xử lý timeout, deadlock và retry trong transaction mới khi phù hợp.
- [ ] Integration test có hai transaction độc lập để xác nhận hành vi contention.

## Kết luận

Trong Spring Data JPA, `@Lock` gắn một `LockModeType` vào query repository. `PESSIMISTIC_READ` yêu cầu khóa đọc, `PESSIMISTIC_WRITE` yêu cầu khóa ghi độc quyền và `PESSIMISTIC_FORCE_INCREMENT` còn buộc tăng version của entity versioned. `READ` và `WRITE` là tên tương thích của các mode optimistic, vì vậy không dùng chúng thay cho khóa bi quan. Hãy giữ khóa trong transaction service ngắn, cấu hình timeout/scope có kiểm chứng, lấy khóa theo thứ tự nhất quán và kiểm thử contention trên đúng database mục tiêu.