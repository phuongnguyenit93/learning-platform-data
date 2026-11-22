# Bulk DML và giới hạn callback, cascade, version trong Spring Data JPA

Bulk DML (bulk data manipulation) là thao tác `UPDATE` hoặc `DELETE` tác động trực tiếp lên một tập bản ghi trong database bằng một câu lệnh. Trong Spring Data JPA, ta thường dùng `@Modifying` kết hợp `@Query`, hoặc các phương thức như `deleteAllInBatch()`. Cách này giảm việc tải từng entity lên bộ nhớ và phù hợp với cập nhật trạng thái hàng loạt, dọn dữ liệu cũ hoặc tác vụ bảo trì.

Đổi lại, bulk DML đi theo đường thực thi trực tiếp ở mức database. JPA không lần lượt xử lý từng entity như khi gọi `EntityManager.merge()` hoặc `EntityManager.remove()`. Vì vậy, lifecycle callback, cascade của JPA, persistence context và optimistic locking bằng `@Version` có những giới hạn quan trọng.

Bài viết dùng Java 17+, Spring Boot 3.x, Spring Data JPA, JUnit 5, AssertJ và H2 trong ví dụ. Các đoạn mã là thành phần của một dự án Spring Boot có dependency JPA và test phù hợp.

## 1. Bulk DML hoạt động như thế nào?

Một thao tác entity thông thường đi qua persistence context:

1. Entity được tải hoặc được persist và trở thành managed.
2. Ứng dụng thay đổi thuộc tính hoặc gọi `remove()`.
3. Khi flush, JPA provider phát hiện thay đổi và phát lệnh SQL.
4. JPA có thể thực thi callback, cascade, kiểm tra version và đồng bộ trạng thái entity theo quy tắc của persistence context.

Bulk DML có đường đi ngắn hơn: câu lệnh JPQL hoặc SQL tác động trực tiếp lên các hàng phù hợp trong database. JPA không tải tất cả entity bị ảnh hưởng để xử lý từng đối tượng Java.

Ví dụ JPQL:

```java
update InventoryItem i
set i.quantity = 0
where i.expired = true
```

Câu lệnh trên cập nhật mọi hàng phù hợp trong một lần thực thi. Nó không tương đương với vòng lặp tải từng `InventoryItem`, gọi setter rồi flush.

Bulk DML thường hiệu quả khi số lượng bản ghi lớn và quy tắc nghiệp vụ có thể biểu diễn an toàn trong một câu lệnh. Nếu mỗi entity cần callback, cascade, domain event hoặc logic nghiệp vụ riêng, thao tác entity thông thường thường phù hợp hơn.

## 2. Dùng `@Modifying` với `@Query`

Spring Data JPA cần biết một query method thực hiện thay đổi dữ liệu thay vì truy vấn kết quả. Đánh dấu phương thức bằng `@Modifying` khi dùng `@Query` cho JPQL `UPDATE` hoặc `DELETE`.

Ví dụ entity:

**InventoryItem.java**

```java
package com.example.inventory;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private int quantity;

    @Version
    private long version;

    protected InventoryItem() {
    }

    public InventoryItem(int quantity) {
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public int getQuantity() {
        return quantity;
    }

    public long getVersion() {
        return version;
    }
}
```

Repository:

**InventoryItemRepository.java**

```java
package com.example.inventory;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface InventoryItemRepository
        extends JpaRepository<InventoryItem, Long> {

    @Transactional
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update InventoryItem i
           set i.quantity = :newQuantity,
               i.version = i.version + 1
         where i.id = :id
           and i.version = :expectedVersion
        """)
    int updateQuantityIfVersionMatches(
        @Param("id") Long id,
        @Param("newQuantity") int newQuantity,
        @Param("expectedVersion") long expectedVersion
    );

    @Transactional
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        delete from InventoryItem i
         where i.quantity = 0
        """)
    int deleteEmptyItemsInBulk();
}
```

Một số điểm cần nhớ:

- `@Modifying` thay đổi cách Spring Data thực thi query. Nó không tự tạo transaction cho mọi trường hợp.
- Query method khai báo bằng `@Query` không mặc nhiên có transaction giống các phương thức CRUD kế thừa. Hãy đặt `@Transactional` ở phương thức repository hoặc, thường linh hoạt hơn, ở service bao quanh thao tác.
- Phương thức trả về `int` nhận số hàng/entity bị ảnh hưởng. Với câu lệnh update/delete, số lượng này giúp xác định thao tác có khớp bản ghi nào hay không.
- `@Modifying` có thể dùng với JPQL hoặc native SQL. Với native SQL, đặt `nativeQuery = true` trong `@Query`; các giới hạn về callback, cascade và đồng bộ persistence context vẫn tồn tại.

Trong ví dụ, `flushAutomatically = true` yêu cầu flush persistence context trước khi chạy query. `clearAutomatically = true` yêu cầu clear persistence context sau khi query chạy. Hai thuộc tính này mặc định đều là `false`.

## 3. Bulk DML bỏ qua lifecycle callback

Các callback như `@PreUpdate`, `@PostUpdate`, `@PreRemove` và `@PostRemove` gắn với vòng đời của từng entity. Bulk DML không tải từng entity và không gọi các callback đó.

Ví dụ:

```java
@Entity
public class Document {

    @Id
    @GeneratedValue
    private Long id;

    private String status;

    private Instant updatedAt;

    @PreUpdate
    void beforeUpdate() {
        updatedAt = Instant.now();
    }

    @PreRemove
    void beforeRemove() {
        // Ghi nhận xử lý trước khi một entity bị xóa.
    }
}
```

Nếu ứng dụng chạy:

```java
documentRepository.markAllArchived();
```

với repository method thực thi JPQL bulk update, callback `beforeUpdate()` không được gọi cho từng `Document`. Tương tự, bulk delete không gọi `@PreRemove` hoặc `@PostRemove`.

Hệ quả thực tế:

- Trường `updatedAt` được cập nhật trong `@PreUpdate` sẽ không tự đổi.
- Logic kiểm tra, ghi log hoặc tạo audit record trong entity listener không chạy.
- Spring Data auditing dựa trên entity listener như `@LastModifiedDate` không tự áp dụng cho các hàng được bulk update.
- Xử lý phụ thuộc callback xóa entity không được thực hiện.

Nếu cần cập nhật cột thời gian trong bulk query, hãy đặt giá trị đó tường minh trong câu lệnh, chẳng hạn `set d.updatedAt = :now`. Nếu cần audit record hoặc domain event cho từng entity, hãy dùng quy trình xử lý entity riêng hoặc thiết kế một cơ chế audit/event ở mức database hay ứng dụng phù hợp với yêu cầu.

Database trigger vẫn có thể chạy theo quy tắc của database. Trigger là cơ chế ở database, khác với JPA lifecycle callback trong ứng dụng Java.

## 4. Bulk DELETE không thực hiện JPA cascade

Giả sử một đơn hàng có nhiều dòng hàng:

```java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();
}
```

Khi gọi `entityManager.remove(order)`, JPA áp dụng các quy tắc cascade tương ứng. Với `CascadeType.REMOVE` hoặc `CascadeType.ALL`, các entity con có thể được đánh dấu xóa cùng entity cha; `orphanRemoval` xử lý entity con bị loại khỏi quan hệ managed theo quy tắc của JPA.

Nhưng một JPQL bulk delete như:

```java
delete from PurchaseOrder o
where o.createdAt < :cutoff
```

chỉ xóa các hàng của entity đích trong database. Nó không gọi `remove()` cho từng `PurchaseOrder`, không duyệt collection `lines`, không thực hiện JPA cascade và không áp dụng `orphanRemoval` như khi thay đổi quan hệ của entity managed.

Nếu bảng `order_lines` có foreign key tham chiếu `purchase_orders` và không có hành vi cascade ở database, câu lệnh có thể thất bại vì vi phạm ràng buộc khóa ngoại. Có thể xử lý bằng cách xóa bản ghi con trước, dùng thao tác entity khi cần JPA cascade, hoặc thiết kế foreign key với `ON DELETE CASCADE` nếu đó là quy tắc dữ liệu mong muốn.

`ON DELETE CASCADE` là cascade của database. Nó có thể xóa hàng con khi hàng cha bị xóa, nhưng vẫn không gọi callback Java cho các entity con.

Spring Data cũng có hai kiểu delete cần phân biệt:

| Cách xóa | Cách thực hiện | Callback và JPA cascade |
|---|---|---|
| Derived delete như `deleteByStatus(...)` | Spring Data tìm các entity phù hợp rồi xóa từng entity | Có thể áp dụng lifecycle callback và cascade của JPA |
| `@Modifying @Query("delete ...")` | Một bulk delete trực tiếp trong database | Không áp dụng callback hoặc JPA cascade |
| `deleteAllInBatch()` / `deleteAllInBatch(entities)` | Bulk delete qua một thao tác truy vấn | Không áp dụng callback hoặc JPA cascade |

Derived delete có thể tốn bộ nhớ và nhiều thao tác hơn vì phải tải các entity phù hợp. Bulk delete nhanh hơn với tập dữ liệu lớn, nhưng người viết phải tự bảo đảm ràng buộc dữ liệu và các tác dụng phụ cần thiết.

## 5. Bulk DML và optimistic locking với `@Version`

Trong thao tác entity thông thường, JPA provider dùng thuộc tính `@Version` để kiểm tra optimistic locking. Khi cập nhật một entity managed, provider đưa version hiện tại vào điều kiện cập nhật và tăng version khi thành công. Nếu một transaction khác đã cập nhật entity, thao tác có thể thất bại với optimistic locking exception.

Bulk DML bỏ qua cơ chế tự động đó:

- JPA không tự kiểm tra version của từng entity bị tác động.
- JPA không tự tăng thuộc tính `@Version` cho các hàng được bulk update.
- Một bulk update có thể ghi đè dữ liệu do transaction khác thay đổi nếu câu lệnh không có điều kiện bảo vệ thích hợp.

Nếu cần bảo vệ một cập nhật theo version, phải đưa version mong đợi vào `WHERE` và tự tăng version trong `SET`. Phương thức `updateQuantityIfVersionMatches` ở phần trước làm việc này:

```sql
UPDATE inventory_items
SET quantity = ?, version = version + 1
WHERE id = ? AND version = ?
```

Đây là SQL minh họa cho ý nghĩa của JPQL. Khi một bản ghi có đúng `id` và `version`, câu lệnh cập nhật hàng đó và tăng version. Nếu version đã đổi, điều kiện không khớp nên không có hàng nào được cập nhật.

Với một bản ghi đã biết:

- Số hàng bị ảnh hưởng bằng `1`: cập nhật thành công theo version mong đợi.
- Số hàng bằng `0`: không cập nhật được; có thể bản ghi không tồn tại, version đã cũ hoặc một điều kiện nghiệp vụ khác không còn đúng. Không nên kết luận chắc chắn chỉ riêng nguyên nhân version nếu câu lệnh có nhiều điều kiện.

Đối với thao tác cập nhật hàng loạt nhiều entity, chỉ tăng version bằng `version = version + 1` không tự tạo ra kiểm tra optimistic locking tương đương từng entity. Nếu nghiệp vụ cần phát hiện xung đột cho từng bản ghi, hãy thiết kế điều kiện version phù hợp hoặc xử lý từng entity bằng cơ chế JPA thông thường.

Sau bulk update, các entity đang managed có thể vẫn giữ version và dữ liệu cũ. Hãy clear hoặc refresh trước khi tiếp tục dùng chúng, nếu không ứng dụng có thể đọc trạng thái cũ từ persistence context.

## 6. Persistence context có thể bị stale

Persistence context là bộ nhớ cấp một của EntityManager. Trong một persistence context, mỗi entity identity thường được quản lý bằng một đối tượng Java tương ứng.

Ví dụ, ứng dụng đã tải một `InventoryItem`:

```java
InventoryItem item = entityManager.find(InventoryItem.class, id);
int oldQuantity = item.getQuantity();

repository.updateQuantityIfVersionMatches(
    id, oldQuantity - 1, item.getVersion()
);
```

Bulk query cập nhật database trực tiếp, nhưng đối tượng `item` đang managed có thể vẫn giữ `quantity` và `version` cũ. Một lần `find()` tiếp theo trong cùng persistence context có thể trả lại chính đối tượng đang được quản lý thay vì đọc lại database.

Có hai lựa chọn thường dùng:

- Flush trước query để đẩy các thay đổi đang chờ trong persistence context xuống database.
- Clear sau query để detach toàn bộ entity managed; khi cần dữ liệu, tải lại từ database.

`flushAutomatically = true` và `clearAutomatically = true` của `@Modifying` hỗ trợ hai bước này. Có thể gọi `entityManager.flush()` và `entityManager.clear()` tường minh nếu cần điều khiển ở service.

Cần hiểu phạm vi tác động:

- Flush có thể ghi tất cả thay đổi đang chờ trong persistence context, không chỉ entity thuộc query.
- Clear detach tất cả entity managed trong persistence context hiện tại, không chỉ các entity bị bulk DML tác động.
- Clear mà không flush trước có thể làm mất các thay đổi chưa flush đang nằm trong bộ nhớ.
- Sau clear, các tham chiếu Java cũ vẫn tồn tại nhưng đã detached. Không tiếp tục giả định chúng tự phản ánh trạng thái database.

Nếu chỉ cần làm mới một entity, có thể cân nhắc `entityManager.refresh(entity)` sau khi bảo đảm entity vẫn managed. `refresh` tải lại trạng thái từ database và ghi đè thay đổi chưa flush của entity đó, nên cần dùng có chủ đích.

## 7. Kiểm thử cập nhật theo version

Một integration test có thể xác nhận số hàng cập nhật, version tăng và lần cập nhật với version cũ không thành công.

**InventoryItemRepositoryTest.java**

```java
package com.example.inventory;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class InventoryItemRepositoryTest {

    @Autowired
    private InventoryItemRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void bulkUpdateChecksAndIncrementsVersion() {
        InventoryItem item = new InventoryItem(10);
        entityManager.persistAndFlush(item);

        Long id = item.getId();
        long originalVersion = item.getVersion();

        int updated = repository.updateQuantityIfVersionMatches(
            id, 7, originalVersion
        );

        assertThat(updated).isEqualTo(1);

        // Repository query đã clear persistence context.
        InventoryItem reloaded =
            entityManager.find(InventoryItem.class, id);

        assertThat(reloaded.getQuantity()).isEqualTo(7);
        assertThat(reloaded.getVersion()).isEqualTo(originalVersion + 1);

        // Version cũ không còn khớp nên câu lệnh không cập nhật hàng nào.
        int staleUpdate = repository.updateQuantityIfVersionMatches(
            id, 5, originalVersion
        );

        assertThat(staleUpdate).isZero();
    }
}
```

`@DataJpaTest` cung cấp transaction cho test và thường dùng database nhúng nếu có dependency phù hợp. Ví dụ này kiểm tra kết quả trong database bằng cách tải lại entity sau bulk query. Đây là integration test; không mock repository vì mục tiêu là kiểm tra query JPA và tác động của nó.

Test không cần in stdout. Bằng chứng là các assertion: lần đầu ảnh hưởng một hàng, quantity được cập nhật, version tăng một đơn vị và lần gọi với version cũ ảnh hưởng không hàng nào.

## 8. Chọn bulk DML hay thao tác entity?

| Yêu cầu | Hướng phù hợp |
|---|---|
| Cập nhật hàng nghìn bản ghi với cùng một quy tắc đơn giản | Bulk JPQL hoặc native DML |
| Cần `@PreUpdate`, `@PostUpdate`, entity listener hoặc Spring Data auditing | Tải và cập nhật entity managed |
| Cần `CascadeType.REMOVE` hoặc `orphanRemoval` của JPA | Gọi thao tác xóa trên entity managed |
| Cần optimistic locking tự động theo từng entity | Cập nhật entity managed có `@Version` |
| Cần bulk update nhưng vẫn bảo vệ một hàng theo version | Đưa version vào `WHERE`, tăng version tường minh và kiểm tra số hàng bị ảnh hưởng |
| Cần xóa nhanh và đã có quy tắc khóa ngoại/database cascade phù hợp | Bulk delete, đồng thời xử lý persistence context |
| Cần gom nhiều câu INSERT/UPDATE của entity thành batch JDBC | Cân nhắc JDBC batching của Hibernate |

Bulk DML và JDBC batching là hai khái niệm khác nhau. Bulk DML là một câu lệnh set-based tác động lên nhiều hàng, ví dụ `UPDATE ... WHERE ...`. JDBC batching gom nhiều câu lệnh INSERT/UPDATE riêng lẻ để gửi theo nhóm. Với JDBC batching, ứng dụng vẫn có thể persist hoặc cập nhật từng entity qua JPA; lifecycle, cascade và version tiếp tục được xử lý theo đường entity của provider.

Ví dụ, `saveAll(entities)` không có nghĩa Spring Data luôn tạo một câu SQL bulk duy nhất. Phương thức thường gọi quy trình save cho từng entity; Hibernate có thể gom các câu SQL tương ứng bằng cấu hình như `hibernate.jdbc.batch_size`. Hãy phân biệt mục tiêu giảm round trip của JDBC batch với mục tiêu cập nhật theo tập của bulk DML.

## 9. Checklist trước khi đưa bulk DML vào production

1. **Transaction:** câu lệnh chạy trong transaction phù hợp; xác định rõ transaction boundary ở service hoặc repository.
2. **Callback:** kiểm tra xem có logic nào đang nằm trong `@PreUpdate`, `@PostUpdate`, `@PreRemove`, `@PostRemove` hoặc entity listener cần được thay thế hay không.
3. **Cascade và khóa ngoại:** xác nhận cách xử lý bản ghi con, orphan và foreign key. Đừng dựa vào `CascadeType.REMOVE` cho bulk delete.
4. **Version:** nếu cần optimistic locking, đưa version mong đợi vào điều kiện và tăng version tường minh; kiểm tra số hàng bị ảnh hưởng.
5. **Persistence context:** quyết định flush và clear/refresh khi nào. Lưu ý `clearAutomatically` làm detach tất cả entity managed trong context.
6. **Audit và event:** cập nhật audit column trong query hoặc thiết kế cơ chế audit/event khác nếu callback không chạy.
7. **Kiểm thử:** kiểm tra cả dữ liệu database, số hàng bị ảnh hưởng, version, quan hệ con và trạng thái entity sau query.

Bulk DML là công cụ hiệu quả cho thao tác hàng loạt khi tác động trực tiếp lên database phù hợp với nghiệp vụ. Trước khi dùng, cần chủ động xử lý những việc mà JPA thường làm cho từng entity: callback, cascade, version, audit và đồng bộ persistence context.