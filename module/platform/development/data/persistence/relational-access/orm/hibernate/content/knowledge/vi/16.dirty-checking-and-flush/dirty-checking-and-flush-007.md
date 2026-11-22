# Hàng đợi hành động và thứ tự insert, update, delete

Trong Hibernate ORM, khi gọi `persist()`, sửa một entity managed, thay đổi collection hoặc gọi `remove()`, **thứ tự các lời gọi Java không nhất thiết là thứ tự các câu SQL** mà database nhận được. Hibernate quản lý những thay đổi của persistence context bằng cơ chế *transactional write-behind*, phát hiện dữ liệu bẩn (*dirty checking*), lập kế hoạch các hành động cần thực thi và đồng bộ chúng khi **flush**.

Thành phần cốt lõi là **`ActionQueue`**: hàng đợi/lớp lập kế hoạch chứa những thao tác như chèn entity, cập nhật entity, xóa entity, xử lý orphan và đồng bộ collection. Tại thời điểm flush, Hibernate thực hiện các hành động theo **quy tắc thực thi của phiên bản ORM**, không đơn thuần theo thứ tự `persist()`, setter và `remove()` xuất hiện trong mã.

Điều này có hệ quả rất thực tế:

- Gọi `remove(old)` trước rồi `persist(new)` **vẫn có thể dẫn tới SQL `INSERT` trước `DELETE`**.
- Một transaction tưởng là “xóa bản ghi cũ để giải phóng giá trị `UNIQUE`, rồi chèn bản ghi mới” vẫn có thể vi phạm unique constraint.
- Quan hệ khóa ngoại ảnh hưởng thứ tự chèn cha/con và xóa con/cha.
- Các thay đổi ở collection được lập kế hoạch riêng với thao tác update thuộc tính của entity.
- JDBC batching có thể sắp xếp lại các thao tác cùng nhóm để tăng hiệu năng, nhưng không cho phép bỏ qua ràng buộc database.

Bài học trình bày **Dirty Checking và Flush → ActionQueue → thứ tự DML → ràng buộc FK/UNIQUE → cách quan sát và xử lý**. Các ví dụ minh họa dùng Jakarta Persistence và Hibernate hiện đại; những chi tiết về nhóm action và thứ tự cụ thể được đối chiếu theo **Hibernate ORM 7.4 User Guide**. Không nên coi chúng là hợp đồng portable cho mọi JPA provider hoặc bất kỳ phiên bản Hibernate trong tương lai.

## 1. Từ thao tác Java đến SQL: không phải một bước duy nhất

Một ứng dụng Java thường viết:

```java
em.persist(newCustomer);

Customer existing = em.find(Customer.class, customerId);
existing.rename("Tên mới");

em.remove(oldCustomer);
```

Người mới học có thể hình dung ngay ba câu SQL theo đúng thứ tự:

```sql
INSERT ...;
UPDATE ...;
DELETE ...;
```

Nhưng với entity stateful ORM, phải phân biệt các giai đoạn:

```text
Ứng dụng Java
  │
  ├─ persist(entity)            ─→ đăng ký INSERT / cascade
  ├─ sửa thuộc tính managed     ─→ đổi trạng thái Java
  ├─ thay đổi Set/List/Map      ─→ collection bị thay đổi
  └─ remove(entity)             ─→ chuyển entity sang trạng thái removed
                                  │
                                  ▼
                     Persistence Context (L1)
                        managed entities
                        snapshots / dirty state
                        persistent collections
                                  │
                           flush được kích hoạt
                                  │
                                  ▼
                      Dirty checking + cascades
                        phát hiện các thay đổi
                                  │
                                  ▼
                        Hibernate ActionQueue
                     sắp xếp những action cần chạy
                                  │
                                  ▼
                      JDBC INSERT / UPDATE / DELETE
                                  │
                                  ▼
                         Database constraints
                              PK, FK, UNIQUE
                                  │
                                  ▼
                         Commit hoặc rollback
```

**Không phải mọi thao tác đều đợi đến flush.** Ví dụ entity dùng `GenerationType.IDENTITY` thường cần thực thi `INSERT` sớm để nhận ID do database sinh. Nhưng đó là ngoại lệ liên quan chiến lược sinh khóa, không làm mất nguyên tắc chung rằng Hibernate có cơ chế lập kế hoạch và đồng bộ DML.

### 1.1. Các khái niệm không được trộn lẫn

| Khái niệm | Vai trò | Không đồng nghĩa với |
| --- | --- | --- |
| `persist()` | Đưa entity mới vào trạng thái persistent/managed và đăng ký thao tác tương ứng | Mọi trường hợp đã `INSERT` ngay |
| Setter trên managed entity | Đổi state object Java | SQL `UPDATE` đã chạy |
| `remove()` | Đánh dấu entity cần được xóa trong context | SQL `DELETE` đã chạy ngay |
| Dirty checking | Xác định state managed nào khác trạng thái đã tải/đồng bộ | SQL của từng setter |
| `ActionQueue` | Giữ/lập kế hoạch những hành động DML đang chờ | FIFO queue phản ánh thứ tự Java |
| `flush()` | Đồng bộ thay đổi persistence context với database | `commit()` transaction |
| `commit()` | Hoàn tất transaction; thường cần flush trước | Chỉ là lệnh gọi `flush()` |
| JDBC batching | Gom những statement phù hợp để giảm round trip | HQL bulk update/delete |

## 2. Vì sao Hibernate cần hàng đợi hành động?

Nếu ngay khi người lập trình thay field, Hibernate gửi SQL tương ứng, ứng dụng có thể:

- Phát một `UPDATE` cho từng setter dù sửa nhiều field cùng một entity.
- Không có cơ hội nhóm những `INSERT` giống nhau vào batch.
- Khó sắp xếp những thao tác phải tuân thủ quan hệ cha/con và FK.
- Tốn nhiều round trip dù transaction chỉ cần lưu trạng thái cuối cùng.
- Không thể quản lý hiệu quả việc xóa orphan hoặc thay đổi bảng liên kết.

Cơ chế write-behind giúp Hibernate **tổng hợp trạng thái của một đơn vị công việc**:

```java
Customer c = em.find(Customer.class, 10L);

c.rename("Alice A");
c.rename("Alice B");
c.rename("Alice Final");
```

Nếu chưa flush ở giữa, Hibernate thường chỉ cần đồng bộ trạng thái cuối:

```sql
UPDATE customers
SET display_name = 'Alice Final'
WHERE id = 10;
```

Không phải ba UPDATE, một lần cho mỗi setter. **Số câu SQL thực tế** còn phụ thuộc mapping, dirty checking strategy, lifecycle callbacks, version và việc flush có xảy ra giữa các lần sửa hay không.

### 2.1. Các thao tác tạo action ở thời điểm khác nhau

- `persist()` thường đăng ký hành động insert tương ứng ngay trong quá trình xử lý event và cascade.
- `remove()` thường đăng ký hành động xóa tương ứng theo lifecycle.
- Với một entity managed đã tồn tại, chỉ gọi setter **không nhất thiết tạo `EntityUpdateAction` ngay**. Hibernate thường phát hiện thuộc tính dirty trong quá trình flush, rồi lập `EntityUpdateAction` nếu thực sự cần UPDATE.
- Những collection persistent có snapshot/tracking riêng; add/remove phần tử có thể trở thành collection actions khi flush.
- Orphan removal và cascade làm xuất hiện hành động phụ thuộc, dù ứng dụng chỉ gọi một method trên aggregate root.

Do đó, hiểu `ActionQueue` không phải là tưởng tượng “mỗi method Java đẩy một câu SQL ngay lập tức vào FIFO queue”.

## 3. Dirty checking quyết định khi nào cần UPDATE

Giả sử entity:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected Customer() {
    }

    public Customer(Long id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void rename(String name) {
        this.displayName = java.util.Objects.requireNonNull(name);
    }
}
```

Trong một transaction:

```java
Customer customer = em.find(Customer.class, 10L);
customer.rename("Tên mới");

// Chưa gọi em.merge(customer).
// customer đã managed, nên Hibernate theo dõi state của nó.
em.flush();
```

Khi flush, Hibernate có thể so state hiện tại với state đã tải hoặc dùng cơ chế dirty tracking được cấu hình. Nếu phát hiện dirty, ORM lập `EntityUpdateAction` và gửi UPDATE thích hợp.

Trường hợp:

```java
customer.rename(customer.getDisplayName());
```

thường **không cần UPDATE** vì giá trị không đổi. Nhưng kết quả còn tùy kiểu dữ liệu, custom type, converter và việc dirty tracking đã được cấu hình như thế nào.

**Không suy luận mỗi setter tạo một UPDATE.** Cũng không suy luận một lần `flush()` chắc chắn có UPDATE: nếu không có state nào dirty, có thể không có SQL DML.

### 3.1. Managed và detached khác nhau

```java
Customer customer = em.find(Customer.class, 10L);
em.detach(customer);

customer.rename("Đã tách khỏi context");

em.flush(); // Không dirty-check object detached này.
```

Object detached không được đồng bộ chỉ vì bạn đã sửa nó. `ActionQueue` không phải “hàng đợi toàn bộ Java objects từng được đọc”; nó gắn với **persistence context và lifecycle**.

Muốn đưa thay đổi detached vào context phải sử dụng `merge()` đúng ngữ nghĩa hoặc tải entity managed mới rồi áp dụng những field cần sửa.

## 4. Flush xảy ra khi nào?

Các điểm phổ biến có thể kích hoạt flush:

1. **Gọi `em.flush()`/`session.flush()` trực tiếp** trong transaction phù hợp.
2. **Trước transaction commit** khi flush mode cho phép tự động đồng bộ.
3. **Trước JPQL/HQL query có ảnh hưởng bởi pending changes** trong `AUTO` flush mode.
4. **Trước native query**, tùy cách bootstrap, registered synchronization spaces và flush mode.
5. Một số thao tác ORM khác cần SQL ngay, đặc biệt việc lấy generated ID.

Ví dụ:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Customer customer = new Customer(100L, "Alice");
    em.persist(customer);

    // INSERT có thể đang chờ trong hàng đợi.
    em.flush(); // Yêu cầu đồng bộ các thay đổi đang chờ.

    tx.commit(); // Kết thúc transaction.
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Ví dụ dùng assigned ID (`100L`) để tập trung vào flush, không phải thời điểm Hibernate lấy generated identifier.

### 4.1. Flush không phải commit

```text
Transaction BEGIN
  ├─ persist()/update()/remove()
  ├─ flush()       → gửi SQL DML
  ├─ thao tác khác
  └─ ROLLBACK      → database hoàn tác DML của transaction
```

Sau `flush()`, dữ liệu có thể đã được ghi vào transaction của database nhưng **chưa được commit**. Transaction khác nhìn thấy gì còn phụ thuộc isolation level.

### 4.2. Flush mode có thể đổi thời điểm đồng bộ

| Mode | Ý nghĩa điển hình |
| --- | --- |
| JPA `AUTO` | Đồng bộ trước commit và trước query khi cần bảo đảm kết quả query |
| JPA `COMMIT` | Thường chờ tới commit; tính hiển thị của pending changes cho query trước commit không được JPA bảo đảm giống `AUTO` |
| Hibernate `ALWAYS` | Yêu cầu flush trước mỗi query |
| Hibernate `MANUAL` | Chủ động `flush()` mới đồng bộ theo chế độ này |

`MANUAL` là extension của Hibernate, không phải tên giá trị trong enum JPA `FlushModeType`. Không chọn `MANUAL` chỉ để tạm che lỗi thứ tự DML; dữ liệu chưa flush có thể không được lưu như kỳ vọng.

## 5. ActionQueue không phải FIFO theo thứ tự lệnh Java

Xét:

```java
Customer old = em.find(Customer.class, 10L);

em.remove(old);                            // Java gọi REMOVE trước.
em.persist(new Customer(20L, "Bob"));      // Java gọi PERSIST sau.

em.flush();
```

Trực giác thường là:

```text
DELETE Customer#10
INSERT Customer#20
```

Nhưng với kế hoạch hành động kiểu Hibernate 7.4 thông thường, kết quả SQL có thể là:

```sql
INSERT INTO customers (id, display_name)
VALUES (20, 'Bob');

DELETE FROM customers
WHERE id = 10;
```

**INSERT chạy trước entity DELETE thông thường**, mặc dù `remove()` được gọi trước `persist()`.

Hibernate ORM User Guide có ví dụ chính thức cùng ý tưởng: xóa một entity `Person`, sau đó persist một `Person` mới, nhưng SQL INSERT xuất hiện trước SQL DELETE.

Lý do không phải Hibernate “quên” lệnh `remove()`, mà là **ActionQueue tổ chức nhóm hành động theo quy tắc flush**, có cân nhắc collection, FK và hiệu năng.

### 5.1. Đừng suy ra thứ tự từ log `persist()` và `remove()`

```java
log.info("remove old");
em.remove(old);

log.info("persist new");
em.persist(newOne);
```

Hai log ứng dụng chỉ chứng minh **thứ tự gọi API**. Để biết thứ tự DML thực tế, phải xem SQL log hoặc statement inspector khi flush; không thể đọc source Java rồi kết luận chắc chắn.

## 6. Thứ tự thực thi ActionQueue theo Hibernate ORM 7.4

Hibernate ORM 7.4 User Guide, mục **Flush operation order**, mô tả thứ tự action như sau:

| Thứ tự | Loại action trong Hibernate | Ý nghĩa chính |
| ---: | --- | --- |
| 1 | `OrphanRemovalAction` | Xóa entity con bị orphan trong trường hợp orphan-removal phù hợp |
| 2 | `EntityInsertAction` hoặc `EntityIdentityInsertAction` | Chèn entity mới |
| 3 | `EntityUpdateAction` | Cập nhật entity managed đã dirty |
| 4 | `QueuedOperationCollectionAction` | Thực thi những operation được ghi nhận ở persistent collection theo semantics phù hợp |
| 5 | `CollectionRemoveAction` | Xóa những hàng dữ liệu của một collection/association cần gỡ |
| 6 | `CollectionUpdateAction` | Đồng bộ thay đổi trong collection |
| 7 | `CollectionRecreateAction` | Tạo lại hoặc ghi những hàng thuộc collection |
| 8 | `EntityDeleteAction` | Xóa entity thông thường |

Một cách ghi nhớ:

```text
FLUSH
  │
  ├─ 1. Orphan-removal actions
  ├─ 2. Entity INSERT actions
  ├─ 3. Entity UPDATE actions
  ├─ 4. Queued collection operations
  ├─ 5. Collection REMOVE
  ├─ 6. Collection UPDATE
  ├─ 7. Collection RECREATE
  └─ 8. Ordinary entity DELETE actions
```

**Lưu ý về phiên bản:** Đây là sơ đồ của hàng đợi thực thi được tài liệu **Hibernate ORM 7.4** mô tả. Hibernate 5.x có khác biệt trong danh sách các action (ví dụ các phiên bản cũ hơn chưa liệt kê `QueuedOperationCollectionAction` giống hiện tại); phiên bản mới hoặc implementation phát triển sau đó có thể thay đổi lập kế hoạch. Không coi danh sách này là thứ tự cố định do chuẩn Jakarta Persistence quy định.

### 6.1. `OrphanRemovalAction` đứng trước không có nghĩa mọi DELETE đều sớm

`OrphanRemovalAction` là một loại action riêng, phát sinh ở trường hợp phù hợp với `orphanRemoval = true`.

Ngược lại:

```java
em.remove(customer);
```

thường tạo **entity deletion action**, thuộc nhóm `EntityDeleteAction` về cuối. Do đó câu “DELETE luôn cuối” cũng **không chính xác tuyệt đối**: orphan removal có thể xảy ra trước insert, và SQL từ collection actions có thể dùng DELETE.

Phải hỏi: **đang xóa entity thông thường, xóa orphan hay xóa một hàng liên kết/collection?**

### 6.2. Thứ tự nhóm không cho biết thứ tự từng row trong nhóm

Ngay cả khi biết nhóm INSERT trước UPDATE, ta vẫn chưa thể dự đoán:

```text
INSERT Parent A?
INSERT Child B?
INSERT Parent C?
```

Thứ tự trong nhóm có thể chịu tác động của FK dependencies, cascade, ID generation, batching và các setting sắp xếp. Với các bảng liên quan, Hibernate phải cố tạo thứ tự phù hợp ràng buộc mà nó quản lý; không có nghĩa toàn bộ SQL sẽ luôn trùng thứ tự các lời gọi `persist`.

### 6.3. Collection actions không phải một câu SQL duy nhất

Một `CollectionUpdateAction` hoặc `CollectionRemoveAction` ở mức ORM có thể dẫn tới nhiều SQL statement, ví dụ xóa các rows của bảng liên kết, chèn lại các rows còn lại hoặc cập nhật order index. Chi tiết tùy `Set`, `List`, bag, `@OrderColumn`, quan hệ hai chiều và mapping sở hữu.

Không đếm mỗi action tương đương đúng một dòng SQL.

## 7. Ba loại entity action quan trọng

### 7.1. `EntityInsertAction`

`persist(newEntity)` có thể tạo entity insertion action:

```java
Customer c = new Customer(101L, "Alice");
em.persist(c);
```

Khi thực thi:

```sql
INSERT INTO customers(id, display_name) VALUES (101, 'Alice');
```

Với ID sinh kiểu `IDENTITY`, Hibernate có thể sử dụng `EntityIdentityInsertAction` và thực hiện INSERT sớm hơn để có ID. Vì vậy, trong ví dụ về thứ tự DML cần tránh nhầm **thời điểm sinh khóa** với **thứ tự flush**.

### 7.2. `EntityUpdateAction`

Entity managed bị sửa:

```java
Customer c = em.find(Customer.class, 101L);
c.rename("Alice Updated");
```

Khi flush, dirty checking có thể tạo update action:

```sql
UPDATE customers
SET display_name = 'Alice Updated'
WHERE id = 101;
```

Nếu entity có `@Version`, SQL còn có thể chứa điều kiện version và cập nhật version. Nếu entity được đánh dấu Hibernate `@Immutable`, thay đổi scalar có thể bị bỏ qua thay vì tạo update action.

### 7.3. `EntityDeleteAction`

```java
Customer c = em.find(Customer.class, 101L);
em.remove(c);
```

Hibernate đánh dấu removed và lập deletion action. Entity deletion thông thường được thực thi **sau các nhóm insert/update/collection** theo sơ đồ Hibernate 7.4, trừ những trường hợp đặc biệt và hành vi đã thực thi SQL sớm.

SQL minh họa:

```sql
DELETE FROM customers WHERE id = 101;
```

Đừng nhầm `EntityDeleteAction` với `OrphanRemovalAction`, vốn đứng đầu trong danh sách thứ tự ở mục 6.

## 8. Bài toán UNIQUE: xóa trước trong Java vẫn có thể lỗi

Đây là một trong những tình huống quan trọng nhất khi hiểu ActionQueue.

Giả sử bảng:

```sql
CREATE TABLE user_aliases (
    id BIGINT PRIMARY KEY,
    alias VARCHAR(100) NOT NULL,
    CONSTRAINT uq_user_alias UNIQUE (alias)
);
```

Dữ liệu ban đầu:

```text
id = 1, alias = "primary"
```

Entity:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "user_aliases")
public class UserAlias {

    @Id
    private Long id; // Assigned ID để ví dụ không phụ thuộc IDENTITY.

    @Column(name = "alias", nullable = false, unique = true, length = 100)
    private String alias;

    protected UserAlias() {
    }

    public UserAlias(Long id, String alias) {
        this.id = id;
        this.alias = alias;
    }

    public Long getId() {
        return id;
    }

    public String getAlias() {
        return alias;
    }

    public void changeAlias(String alias) {
        this.alias = java.util.Objects.requireNonNull(alias);
    }
}
```

Transaction cố thay bản ghi cũ bằng bản ghi mới có **cùng alias**:

```java
UserAlias old = em.find(UserAlias.class, 1L);

em.remove(old); // Tưởng UNIQUE("primary") đã được giải phóng.

UserAlias replacement = new UserAlias(2L, "primary");
em.persist(replacement);

em.flush();
```

Lập kế hoạch phổ biến trong Hibernate 7.4:

```text
1. EntityInsertAction UserAlias#2
2. EntityDeleteAction UserAlias#1
```

SQL thực tế có thể:

```sql
INSERT INTO user_aliases(id, alias)
VALUES (2, 'primary');           -- Vi phạm UNIQUE(alias)!

DELETE FROM user_aliases WHERE id = 1;
```

Database kiểm tra unique constraint ngay tại INSERT, nên **không chờ DELETE sau đó** để quyết định. Một transaction có ý định hợp lệ về trạng thái cuối vẫn có thể thất bại do **trạng thái trung gian của SQL**.

### 8.1. Đây không phải bug của database

Constraint của database làm đúng nhiệm vụ: tại thời điểm câu INSERT chạy, vẫn tồn tại hàng `(1, 'primary')`. Hibernate không hứa duy trì thứ tự lệnh Java khi execute SQL.

Tương tự có thể gặp với:

- `username`/`email` unique.
- `slug` của bài viết.
- Mã đơn hàng, số chứng từ.
- Khóa duy nhất `(parent_id, position)`.
- Mối quan hệ một-một qua FK có `UNIQUE`.
- Thay một entity có natural key bằng một entity khác.

### 8.2. Cách 1: cập nhật bản ghi hiện có khi business identity không đổi

Nếu chỉ muốn đổi thông tin của một alias mà **không cần đổi persistent identity**, đừng delete+insert:

```java
UserAlias existing = em.find(UserAlias.class, 1L);
existing.changeAlias("secondary");

em.flush();
```

Đây là `UPDATE` trên entity hiện có. Tùy domain, đây có thể là giải pháp đúng nhất vì giữ nguyên FK, audit và ID.

**Không phải mọi nghiệp vụ “thay thế record” đều thật sự cần một entity mới.** Hãy xác định vì sao muốn đổi ID trước.

### 8.3. Cách 2: flush sau DELETE, rồi mới persist

Nếu nghiệp vụ **bắt buộc xóa bản ghi cũ và tạo bản ghi mới với ID khác**, có thể chia thành hai pha flush trong **cùng transaction**:

```java
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    UserAlias old = em.find(UserAlias.class, 1L);
    em.remove(old);

    em.flush(); // Thực thi DELETE trước khi tạo replacement.

    UserAlias replacement = new UserAlias(2L, "primary");
    em.persist(replacement);

    em.flush(); // Thực thi INSERT trong pha thứ hai.

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Tại đây, có một **ranh giới đồng bộ rõ ràng** giữa DELETE và INSERT. Database thường kiểm tra constraint sau DELETE đầu tiên, rồi INSERT mới không còn va chạm alias cũ.

Điều kiện:

- FK từ các bảng khác không được ngăn việc xóa bản ghi cũ.
- ID mới khác ID cũ; không cố xóa và tạo một object mới có **cùng primary key** đang còn nằm trong persistence context.
- Transaction phải được rollback nếu một trong hai flush lỗi.
- Không có trigger/rule DB khác tạo unique conflict.
- Không có transaction khác đồng thời chiếm alias theo cách gây xung đột.

**`flush()` không commit.** Nếu INSERT pha hai thất bại và rollback, DELETE pha đầu cũng được rollback như một transaction thông thường.

### 8.4. Cách 3: thay đổi mô hình hoặc constraint

Nếu nghiệp vụ thực sự là “một alias có hiệu lực tại một thời điểm”, có thể cần:

- Bảng lịch sử và cột `active`/`valid_from`/`valid_to`.
- Unique constraint chỉ áp trên bản ghi active nếu DBMS hỗ trợ filtered/partial index.
- Chuyển giá trị unique hiện có sang trạng thái khác trước khi dùng lại.
- Dùng một bảng canonical alias thay vì tạo nhiều entity thay thế nhau.
- Constraint deferrable nếu database hỗ trợ và yêu cầu transaction phù hợp.

Đây là **quyết định schema và nghiệp vụ**, không chỉ là mẹo đổi thứ tự Java code.

## 9. `flush()` giải quyết được những gì và không giải quyết được những gì?

| Tình huống | `flush()` giữa các thao tác có hữu ích? | Lưu ý |
| --- | --- | --- |
| Xóa record cũ để giải phóng giá trị UNIQUE, rồi chèn record mới | Có thể | DELETE phải thực thi và không bị FK/trigger chặn |
| Xóa entity parent đang còn children có FK bắt buộc | Không tự đủ | Phải xóa/chuyển children và ràng buộc đúng |
| Thay vị trí hai hàng có `UNIQUE(parent_id, position)` | Có thể cần nhiều bước | Hai UPDATE đổi chỗ trực tiếp có thể va chạm |
| Cần chắc SQL pending đã gửi trước native read | Có thể | Flush không thay transaction isolation |
| Muốn commit một nửa công việc rồi tiếp tục | Không | Flush không commit |
| Muốn “xóa” entity khỏi first-level cache | Không | `clear()`/`detach()` mới tác động context; cần giữ pending changes |
| Mọi lỗi thứ tự DML trong tất cả phiên bản | Không | Phụ thuộc ActionQueue, cascade và database constraints |

Nếu `flush()` ném lỗi do constraint, **không tiếp tục dùng cùng transaction/persistence context như thể không có gì xảy ra**. Thông thường transaction cần rollback; exception có thể làm session không còn nhất quán để tiếp tục công việc đó.

## 10. Khóa ngoại: cần chèn parent trước child

Bảng:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(60) NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL,
    CONSTRAINT fk_lines_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);
```

Quan hệ ở Java:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @OneToMany(mappedBy = "order", cascade = CascadeType.PERSIST)
    private List<OrderLine> lines = new ArrayList<>();

    public void addLine(OrderLine line) {
        lines.add(line);
        line.assignOrder(this);
    }

    // constructor và getters...
}

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    public void assignOrder(PurchaseOrder order) {
        this.order = order;
    }

    // sku, constructor và getters...
}
```

Đây là **đoạn mapping cấu trúc rút gọn**; để biên dịch cần các import Jakarta/JDK, constructor không tham số và những field/method còn thiếu.

Mẫu transaction:

```java
PurchaseOrder order = new PurchaseOrder(10L, "PO-10");
OrderLine lineA = new OrderLine(101L, "SKU-A");
OrderLine lineB = new OrderLine(102L, "SKU-B");

order.addLine(lineA);
order.addLine(lineB);

em.persist(order); // Cascade persist các lines.
em.flush();
```

Database yêu cầu parent `purchase_orders(id=10)` tồn tại trước khi ghi child với `order_id=10`, trừ trường hợp FK deferrable phù hợp. Hibernate có thể sắp xếp/cascade các insert action để đáp ứng dependency.

SQL logic:

```sql
INSERT INTO purchase_orders(id, order_number)
VALUES (10, 'PO-10');

INSERT INTO order_lines(id, order_id, sku)
VALUES (101, 10, 'SKU-A');

INSERT INTO order_lines(id, order_id, sku)
VALUES (102, 10, 'SKU-B');
```

Không nên suy rằng “mọi INSERT có trước mọi DELETE” sẽ tự động giải quyết **mọi dependency**. FK giữa các bảng, quan hệ vòng và constraint khác có thể khiến mô hình khó hơn.

### 10.1. Owning side phải có giá trị đúng

Với quan hệ hai chiều, `OrderLine.order` là **owning side** của FK. Chỉ gọi:

```java
order.getLines().add(line);
```

mà không gán:

```java
line.assignOrder(order);
```

có thể khiến FK không được Hibernate đồng bộ đúng dự kiến. `ActionQueue` không thể sửa một mô hình Java có hai phía quan hệ mâu thuẫn.

Do đó helper `addLine()` nên đồng bộ cả collection và owning side.

### 10.2. Thứ tự insert cha/con không được suy từ iterator

`HashSet` không có thứ tự nghiệp vụ; `List` có thứ tự Java nhưng không bắt buộc Hibernate phải gửi SQL theo thứ tự `list.add()`. Các setting batching có thể gom insert cùng entity type. Muốn thứ tự hiển thị bền vững, dùng `@OrderColumn` hoặc field sort-order được quản lý riêng, không dùng thứ tự câu INSERT như dữ liệu nghiệp vụ.

## 11. Xóa parent: collection và child delete phải được xử lý phù hợp

Vẫn với hai bảng:

```text
purchase_orders(id=10)
order_lines(id=101, order_id=10)
order_lines(id=102, order_id=10)
```

Nếu chạy:

```sql
DELETE FROM purchase_orders WHERE id = 10;
```

trước khi xóa hoặc chuyển hai lines, database thường từ chối vì FK.

Trong ORM, có thể cấu hình cascade removal ở aggregate root:

```java
@OneToMany(
    mappedBy = "order",
    cascade = {CascadeType.PERSIST, CascadeType.REMOVE},
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
```

Sau đó:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 10L);
em.remove(order);
```

Hibernate phải xử lý việc xóa các dependent rows, quan hệ collection và parent theo mapping và constraint. Nhiều action tương ứng có thể được lập; entity delete của parent được thực thi sau các action cần thiết để tránh FK violation.

SQL có thể tương đương về mặt logic:

```sql
DELETE FROM order_lines WHERE id = 101;
DELETE FROM order_lines WHERE id = 102;
DELETE FROM purchase_orders WHERE id = 10;
```

Không khẳng định **chính xác ba câu** sẽ xuất hiện: batch, `@OnDelete`, cascade database và collection semantics có thể thay đổi SQL.

### 11.1. Đừng trộn cascade ORM với `ON DELETE CASCADE`

- `CascadeType.REMOVE`: Hibernate lan truyền thao tác remove tới các entity liên quan theo mapping.
- `orphanRemoval = true`: xóa con bị tách khỏi quan hệ sở hữu.
- `@OnDelete(action = OnDeleteAction.CASCADE)`: Hibernate-specific mapping yêu cầu/khai thác cascade ở database theo điều kiện phù hợp.
- SQL `ON DELETE CASCADE`: database tự xử lý child rows khi parent bị xóa.

Chúng có thể tương tác nhưng **không tương đương**. Nếu xóa parent bằng native SQL hoặc bulk JPQL, hành vi cascade ORM có thể không chạy như `em.remove(parent)`; DB FK vẫn được kiểm tra.

## 12. Orphan removal: DELETE có thể xuất hiện trước INSERT

Xét mô hình một-một hoặc một-nhiều có:

```java
@OneToMany(
    mappedBy = "invoice",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<InvoiceLine> lines = new ArrayList<>();
```

Khi gỡ một line khỏi collection:

```java
invoice.removeLine(oldLine);
```

Hibernate có thể tạo một `OrphanRemovalAction`. Theo thứ tự action Hibernate 7.4, nhóm này **đứng trước** nhóm insert entity.

Vì vậy cần phân biệt:

```java
em.remove(someEntity);      // EntityDeleteAction thông thường
invoice.removeLine(line);   // Có thể dẫn tới OrphanRemovalAction
```

Hai cách “xóa” nhìn tương tự trong domain nhưng có đường lập kế hoạch khác nhau. Chúng **không phải mẹo có thể thay thế tùy ý** để điều khiển SQL order: `orphanRemoval` chỉ hợp lý khi entity con **thực sự phụ thuộc lifecycle vào owner**.

### 12.1. Không bật orphanRemoval để “ép DELETE đi trước” bừa bãi

Nếu một entity cần tồn tại độc lập hoặc được chuyển từ cha A sang cha B, `orphanRemoval = true` có thể khiến việc gỡ khỏi A bị diễn giải thành xóa hẳn entity.

Nếu nghiệp vụ là **chuyển** con, thiết kế owning-side FK và transaction đúng, thay vì bật orphan removal chỉ để xử lý unique conflict.

## 13. Các hành động collection có thể phát nhiều SQL hơn tưởng tượng

Thao tác đơn giản:

```java
project.getTags().remove("legacy");
```

nếu `tags` là `@ElementCollection`, có thể dẫn tới SQL DELETE trong **collection table**, không phải `EntityDeleteAction`.

Tương tự:

```java
project.getMembers().add(user);
```

nếu `members` là `@ManyToMany`, có thể tạo INSERT trong **join table** nhưng không tạo `EntityInsertAction` cho `User` đã tồn tại.

| Java mapping | Thay đổi | SQL thường liên quan |
| --- | --- | --- |
| `@ElementCollection Set<String>` | Thêm/gỡ giá trị | INSERT/DELETE trong collection table |
| `@ManyToMany` | Thêm/gỡ association | INSERT/DELETE trong join table |
| `@OneToMany` bidirectional | Thêm con mới | Entity INSERT con + FK theo owning side |
| `@OneToMany` unidirectional link table | Gỡ phần tử | Có thể DELETE và INSERT lại nhiều link rows |
| `List` với `@OrderColumn` | Đổi vị trí | UPDATE order index của nhiều rows |
| `@OneToMany(orphanRemoval=true)` | Gỡ entity con | Có thể DELETE entity con + collection action |

Vì thế câu “DELETE entity chạy cuối, nên không có DELETE nào trước INSERT” là sai. **SQL DELETE ở collection table** và orphan actions có thể nằm ở những nhóm khác.

### 13.1. Vì sao `List` có thể gây UPDATE khi chỉ đổi thứ tự?

```java
List<Chapter> chapters = book.getChapters();
Collections.swap(chapters, 0, 1);
```

Nếu dùng `@OrderColumn`, Hibernate cần đồng bộ cột vị trí. Database có constraint `UNIQUE(book_id, position)` thì việc hoán đổi vị trí có thể gặp **unique conflict tạm thời** tùy SQL UPDATE order và khả năng deferral của DBMS.

`ActionQueue` xử lý collection update nhưng **không hứa mọi hoán đổi sẽ tránh được constraint violation** khi từng statement phải hợp lệ tức thì.

## 14. Hoán đổi hai giá trị UNIQUE: vấn đề không chỉ là INSERT/DELETE

Giả sử bảng:

```sql
CREATE TABLE seats (
    id BIGINT PRIMARY KEY,
    seat_code VARCHAR(10) NOT NULL UNIQUE
);
```

Có:

```text
Seat#1 = "A1"
Seat#2 = "A2"
```

Muốn đổi chỗ:

```java
seat1.setSeatCode("A2");
seat2.setSeatCode("A1");
em.flush();
```

SQL có thể:

```sql
UPDATE seats SET seat_code = 'A2' WHERE id = 1;
UPDATE seats SET seat_code = 'A1' WHERE id = 2;
```

Câu đầu tiên đã trùng `A2`. Đảo thứ tự hai UPDATE cũng không giải quyết xung đột ngay lập tức: câu nào chạy trước cũng có thể vi phạm.

Các chiến lược tùy domain và DBMS:

- Có **giá trị trung gian tạm** hợp lệ và chưa ai dùng: cập nhật một seat sang temporary code, flush, rồi cập nhật hai seat về giá trị cuối theo một trình tự đã tính.
- Database hỗ trợ **DEFERRABLE UNIQUE constraint**: có thể trì hoãn kiểm tra tới transaction commit nếu constraint được khai báo và kích hoạt đúng; không phải DBMS nào cũng hỗ trợ.
- Thiết kế quan hệ/slot assignment thay vì đổi trực tiếp natural key.
- Dùng một câu SQL chuyên biệt với behavior được database xác nhận.
- Đồng bộ bằng lock/optimistic concurrency để tránh request khác dùng cùng code.

Không dùng `hibernate.order_updates=true` như một bảo đảm rằng **mọi phép đổi giá trị UNIQUE** sẽ tự trở nên hợp lệ.

## 15. `hibernate.order_inserts` và `hibernate.order_updates`

Hibernate có các setting để **sắp xếp thao tác trong nhóm** nhằm tăng cơ hội JDBC batching:

```properties
hibernate.jdbc.batch_size=30
hibernate.order_inserts=true
hibernate.order_updates=true
```

Ý nghĩa:

| Setting | Tác dụng chính | Điều cần biết |
| --- | --- | --- |
| `hibernate.jdbc.batch_size` | Giới hạn số statement tương thích trong một JDBC batch | `0`/giá trị không dương thường tắt batching |
| `hibernate.order_inserts=true` | Nhóm/sắp xếp INSERT theo entity type và identifier nhằm tăng batching | Có chi phí sort; vẫn phải tôn trọng FK |
| `hibernate.order_updates=true` | Sắp xếp UPDATE theo entity type và identifier; có thể sắp xếp collection-related statements | Có thể giảm deadlock ở một số workload, nhưng cần benchmark |
| Per-session batch size | Override cho `Session` cụ thể | Là tối ưu JDBC, không đổi domain state |

Các setting này **không đảo ngược quy luật nhóm action** để DELETE thông thường chạy trước INSERT. Chúng chủ yếu thay cách sắp xếp **trong những nhóm thao tác thích hợp**.

### 15.1. Vì sao sort có thể tăng batch?

Không sắp xếp:

```text
INSERT Author
INSERT Book
INSERT Author
INSERT Book
INSERT Author
```

Có thể buộc Hibernate/JDBC luân phiên nhiều prepared statement khác SQL.

Sau khi nhóm theo entity type, trong phạm vi không vi phạm FK:

```text
INSERT Author
INSERT Author
INSERT Author
INSERT Book
INSERT Book
```

nhiều statement giống nhau được batch hiệu quả hơn. Tuy nhiên FK từ `Book` tới `Author` yêu cầu chèn author phù hợp trước book; Hibernate phải cân nhắc dependency, không thể sort tùy ý mọi INSERT.

### 15.2. `IDENTITY` là ngoại lệ quan trọng của insert batching

Với:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Hibernate thường phải INSERT sớm để đọc ID do database cấp. Tài liệu Hibernate mô tả JDBC insert batching thường bị **vô hiệu hóa đối với identity identifier generator** theo cơ chế truyền thống.

Nếu công việc cần batch insert số lượng lớn và DBMS hỗ trợ sequence, cân nhắc `SEQUENCE` + allocation size phù hợp. Nhưng đổi chiến lược sinh ID tác động schema/migration; đừng thay chỉ để đẹp log.

### 15.3. Batching không phải bulk JPQL DML

- **JDBC batching:** gửi nhiều statement tương thích phát sinh từ lifecycle của từng entity, giữ phần lớn ORM semantics.
- **Bulk JPQL/HQL `update/delete`:** một query cập nhật/xóa nhiều hàng trực tiếp, không duyệt dirty checking của từng managed entity như cách gọi setter.
- **Native bulk SQL:** database xử lý trực tiếp; Hibernate không tự gắn mọi kết quả vào L1 context.

Đừng gọi cả ba là “batch update” mà không phân biệt.

## 16. `ActionQueue` và bulk JPQL/HQL mutation

Ví dụ:

```java
int changed = em.createQuery(
    "update Customer c " +
    "set c.displayName = :name " +
    "where c.id >= :fromId"
)
.setParameter("name", "Standardized")
.setParameter("fromId", 100L)
.executeUpdate();
```

Đây là **bulk mutation**. SQL tương ứng được thực thi qua con đường query mutation, không phải một loạt `EntityUpdateAction` do Hibernate dirty-check từng object trong persistence context.

Hậu quả:

- Entity managed đã load trước bulk update có thể **giữ state cũ** trong L1 cache.
- Lifecycle callbacks và entity cascades không nhất thiết được gọi như khi update/remove từng entity.
- Với joined/subclass inheritance, một bulk HQL statement có thể tạo nhiều SQL statements theo chiến lược mutation.
- Những SQL này vẫn phải tuân thủ database constraints/transaction.
- Chúng không thể được dùng như bằng chứng rằng thứ tự `ActionQueue` của ordinary entity operations đã thay đổi.

Nếu bulk mutation và entity state changes được trộn trong một transaction, cần thiết kế **flush trước bulk khi cần**, rồi refresh/clear hoặc tránh dùng managed instances cũ sau bulk. Không gọi `clear()` khi còn pending changes chưa xử lý.

## 17. Generated ID khiến SQL xuất hiện trước flush

Nhiều ví dụ “Hibernate dồn hết DML tới cuối transaction” trở nên sai nếu quên IDENTITY.

Ví dụ:

```java
@Entity
class Invoice {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
}
```

Trong nhiều cấu hình stateful ORM, Hibernate cần câu INSERT để lấy generated ID:

```java
Invoice invoice = new Invoice();
em.persist(invoice);

Long id = invoice.getId(); // ID có thể đã được cấp vì INSERT sớm.
```

Ngay cả khi chưa gọi `flush()`, INSERT **có thể đã được gửi** để phục vụ ID generation. Việc `EntityIdentityInsertAction` xuất hiện trong sơ đồ không đồng nghĩa nó luôn phải chờ tới bước entity INSERT của một flush duy nhất.

Bởi vậy, khi xây thí nghiệm kiểm tra **INSERT trước DELETE**, tốt nhất dùng **assigned ID hoặc generator có thể trì hoãn INSERT** để loại bỏ ảnh hưởng của IDENTITY, sau đó kiểm thử riêng behavior của generator production.

## 18. AUTO flush có thể thay đổi ranh giới ActionQueue

Ví dụ:

```java
tx.begin();

UserAlias old = em.find(UserAlias.class, 1L);
em.remove(old);

// Một JPQL query có query space liên quan đến user_aliases:
long count = em.createQuery(
    "select count(a) from UserAlias a",
    Long.class
).getSingleResult();

em.persist(new UserAlias(2L, "primary"));

tx.commit();
```

Với `FlushMode.AUTO`, Hibernate có thể **flush trước câu query** để trả kết quả phù hợp với pending changes. Điều này tạo ra hai pha khác với việc không có query ở giữa:

```text
Pha 1: remove old
    ↓
AUTO flush trước JPQL query liên quan
    ↓
DELETE old

Pha 2: persist new
    ↓
Flush khi commit
    ↓
INSERT new
```

Do đó hành vi SQL có thể thay đổi chỉ vì một query xuất hiện giữa hai thao tác. Tuy nhiên:

- Không coi đây là cách chữa lỗi thứ tự DML: phụ thuộc flush mode, query overlap và provider.
- Nếu query không overlap pending changes, Hibernate có thể **không flush**.
- Với `COMMIT`/`MANUAL`, query có thể không kích hoạt flush như mong đợi.
- Native SQL có quy tắc auto flush khác tùy JPA/native bootstrap và synchronized spaces.

Muốn phân chia hai pha rõ ràng, sử dụng **explicit `flush()`**, không trông chờ một câu `SELECT COUNT(*)` để điều khiển thứ tự.

## 19. Vì sao thứ tự ActionQueue ảnh hưởng tính nhất quán constraint?

Database thường kiểm tra những ràng buộc như:

| Constraint | Điều có thể xảy ra khi thứ tự SQL không như mong muốn |
| --- | --- |
| Primary key | Chèn ID đã tồn tại trước khi xóa hàng cũ → lỗi duplicate PK |
| Unique key | INSERT record mới dùng slug/email cũ trước DELETE → lỗi UNIQUE |
| Foreign key | Xóa parent trước child → lỗi FK |
| NOT NULL | INSERT child không có FK, chờ UPDATE sau → lỗi NOT NULL |
| Check constraint | State trung gian của một UPDATE không hợp lệ → lỗi CHECK |
| Composite unique | Hoán đổi position/number trong collection → va chạm unique |
| Trigger/business constraint | Trigger chạy trên từng statement, có thể thấy trạng thái trung gian |

Hibernate cố gắng lên kế hoạch DML nhất quán với nhiều dependency mapping, nhưng **không bảo đảm mọi ràng buộc nghiệp vụ/custom constraint đều được giải quyết tự động**.

Đặc biệt, UNIQUE constraints thường phụ thuộc **giá trị cột nghiệp vụ**, không chỉ FK/PK. Một trạng thái cuối hợp lệ không đồng nghĩa từng statement trung gian đều hợp lệ.

### 19.1. Constraint deferral phụ thuộc DBMS

Một số DBMS cho khai báo constraint `DEFERRABLE`, cho phép kiểm tra một số ràng buộc ở cuối transaction thay vì ngay từng statement. Đây là đặc điểm **database/schema**, không phải một annotation Hibernate chung đảm bảo hoạt động ở mọi DB.

Nếu dùng PostgreSQL, các lựa chọn `DEFERRABLE INITIALLY DEFERRED` cho constraint hỗ trợ deferral cần được đánh giá với thiết kế schema thực tế. MySQL và nhiều hệ quản trị khác có tập tính năng khác; không đưa một DDL dành cho một DBMS vào hệ thống khác mà chưa kiểm tra.

## 20. Ví dụ nhiều action trong cùng một flush

Giả sử transaction thực hiện:

```java
tx.begin();

UserAlias toDelete = em.find(UserAlias.class, 1L);
UserAlias toUpdate = em.find(UserAlias.class, 3L);

em.remove(toDelete);
toUpdate.changeAlias("updated");
em.persist(new UserAlias(2L, "new"));

em.flush();

tx.commit();
```

Sơ đồ khái niệm:

```text
Java method order
  1. remove UserAlias#1
  2. update field UserAlias#3
  3. persist UserAlias#2
                    │
                    ▼
Flush / dirty checking
  - EntityDeleteAction(#1)
  - EntityUpdateAction(#3)
  - EntityInsertAction(#2)
                    │
                    ▼
ActionQueue order (7.4, thông thường)
  1. INSERT #2
  2. UPDATE #3
  3. DELETE #1
```

SQL minh họa:

```sql
INSERT INTO user_aliases (id, alias) VALUES (2, 'new');

UPDATE user_aliases SET alias = 'updated' WHERE id = 3;

DELETE FROM user_aliases WHERE id = 1;
```

Nếu `toUpdate` không thực sự dirty, bước UPDATE có thể bị bỏ qua. Nếu entity có `@Version`, câu UPDATE có thể kèm điều kiện version. Nếu câu insert vi phạm unique, flush thất bại ngay ở đầu, nên hai statement sau có thể **không được thực thi**.

### 20.1. Một flush không đồng nghĩa một lần JDBC call

Một flush có thể phát nhiều SQL; JDBC batching có thể gom nhiều thao tác dùng cùng prepared statement. Số câu DML và số lần đi qua mạng database không giống nhau. Mặc dù application log hiển thị SQL từng statement, driver có thể gửi batch theo cách khác.

## 21. Entity version và optimistic locking trong ActionQueue

Ví dụ:

```java
@Entity
@Table(name = "customers")
public class VersionedCustomer {

    @Id
    private Long id;

    @Version
    private long version;

    private String displayName;
}
```

Khi Hibernate phát `EntityUpdateAction`, SQL thường bảo vệ bằng version:

```sql
UPDATE customers
SET display_name = ?, version = ?
WHERE id = ? AND version = ?;
```

Nếu một transaction khác đã thay version, số rows cập nhật có thể là `0`, khiến Hibernate ném optimistic locking exception thích hợp.

Tuy nhiên:

- ActionQueue ordering **không thay thế** optimistic locking.
- Một UPDATE nằm trước DELETE trong flush không có nghĩa luôn thành công; version/FK/UNIQUE vẫn có thể thất bại.
- Bulk JPQL/HQL update thông thường có semantics version khác với entity dirty checking; cần đọc tài liệu mutation/versioned query tương ứng.
- Nếu flush thất bại, rollback transaction và không tiếp tục dùng context lỗi.

## 22. `@DynamicUpdate` không làm thay đổi vị trí UPDATE trong hàng đợi

Hibernate có:

```java
@org.hibernate.annotations.DynamicUpdate
@Entity
public class Customer {
    // ...
}
```

`@DynamicUpdate` có thể khiến Hibernate sinh SQL chỉ cập nhật những cột được đánh dấu dirty, thay vì tất cả cột updateable theo chiến lược mặc định.

Nhưng điều đó **không** biến `EntityUpdateAction` thành thao tác được thực thi trước entity INSERT. Nó thay **hình dạng UPDATE SQL**, không thay quy luật nhóm action.

Ngoài ra, việc SQL UPDATE có nhiều hình dạng khác nhau có thể làm giảm cơ hội dùng cùng prepared statement để batch. Nếu dự án cần tối ưu, phải cân bằng số cột cập nhật và batching thực tế.

## 23. Quan sát thứ tự SQL bằng log

Để kiểm chứng một tình huống ActionQueue, có thể bật logging trong môi trường test:

```properties
hibernate.show_sql=true
hibernate.format_sql=true
```

Với Spring Boot logging:

```properties
logging.level.org.hibernate.SQL=DEBUG
```

Nếu muốn biết bound parameter, có logger riêng theo Hibernate version, nhưng **không bật log giá trị tham số ở production** nếu có mật khẩu, token, dữ liệu cá nhân hoặc số tiền nhạy cảm.

### 23.1. Nhìn log nào?

Để kết luận thứ tự DML, ghi lại:

1. Thời điểm bắt đầu transaction.
2. Những lời gọi `persist`, thay field, `remove`, `flush`.
3. SQL Hibernate gửi tới JDBC.
4. Những lệnh SQL do trigger/database tự thực hiện nếu có.
5. Exception/cause và transaction rollback.
6. Cấu hình batch và ID strategy.

Ví dụ log mô tả:

```text
BEGIN
APP: remove old UserAlias#1
APP: persist replacement UserAlias#2
APP: flush
SQL: insert into user_aliases ...       ← có thể lỗi UNIQUE
SQL: delete from user_aliases ...       ← không tới được
ROLLBACK
```

Không nên chỉ dựa vào `show_sql` nếu có batching mà yêu cầu chính xác số lần JDBC execute. Muốn quan sát sâu hơn, có thể dùng datasource proxy/JDBC tracing hoặc công cụ database monitoring trong môi trường thử nghiệm.

### 23.2. Hibernate Statistics

Có thể bật:

```properties
hibernate.generate_statistics=true
```

và đọc thống kê từ:

```java
org.hibernate.SessionFactory sf =
    emf.unwrap(org.hibernate.SessionFactory.class);

org.hibernate.stat.Statistics stats = sf.getStatistics();

System.out.println(stats.getEntityInsertCount());
System.out.println(stats.getEntityUpdateCount());
System.out.println(stats.getEntityDeleteCount());
System.out.println(stats.getFlushCount());
System.out.println(stats.getPrepareStatementCount());
```

Các counter hữu ích để **định lượng**, nhưng chúng **không tự cho biết thứ tự thực thi từng statement**. Cần log/tracing nếu mục tiêu là chứng minh `INSERT` trước `DELETE`.

Thống kê thường áp dụng ở `SessionFactory` scope; test chạy song song có thể làm counter bị ảnh hưởng. Nếu dùng `stats.clear()` để đo một test, chỉ thực hiện trong môi trường test cô lập.

## 24. Tự thử nghiệm với constraint và transaction

Một integration test cần database thật hoặc database test có behavior constraint tương tự production. Ví dụ JUnit 5 minh họa hiện tượng UNIQUE khi Hibernate sắp thứ tự INSERT trước DELETE.

### 24.1. Giả định fixture

- Đã có `EntityManagerFactory emf` từ JPA/Hibernate.
- Bảng `user_aliases` có `PRIMARY KEY(id)` và `UNIQUE(alias)` thực sự.
- Test chạy trên database **kiểm tra UNIQUE ngay mỗi INSERT**.
- Mỗi test có dữ liệu seed độc lập và cleanup phù hợp.
- `UserAlias` dùng **assigned `Long id`**, tránh IDENTITY làm lệch thời điểm INSERT.
- Không dùng `orphanRemoval` trong test này.

### 24.2. Reproduce vi phạm UNIQUE

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityTransaction;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ActionQueueOrderingTest {

    // emf được test fixture/bootstrap tạo và đóng.
    private final jakarta.persistence.EntityManagerFactory emf;

    ActionQueueOrderingTest(
            jakarta.persistence.EntityManagerFactory emf) {
        this.emf = emf;
    }

    @Test
    void removeThenPersistMayStillHitUniqueConstraint() {
        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            // Giả sử UserAlias#1 với alias="primary" đã được seed.
            UserAlias old = em.find(UserAlias.class, 1L);
            assertNotNull(old);

            em.remove(old);
            em.persist(new UserAlias(2L, "primary"));

            assertThrows(RuntimeException.class, em::flush);

            // Sau lỗi flush, không cố tiếp tục transaction.
            if (tx.isActive()) {
                tx.rollback();
            }
        } finally {
            if (tx.isActive()) {
                tx.rollback();
            }
            em.close();
        }
    }
}
```

**Đây là mã minh họa cho test body**, không phải một lớp JUnit tự chạy nếu chưa cung cấp fixture. JUnit 5 không tự inject `EntityManagerFactory` vào constructor ở mọi cấu hình; cần JUnit extension, Spring test hoặc `@BeforeAll` bootstrap. Test cũng cần seed/cleanup và database constraints có hiệu lực.

Exception từ `flush()` có thể là Hibernate `ConstraintViolationException` được bao bọc, hoặc JPA `PersistenceException`/một runtime exception khác. Nếu cần assert loại lỗi chính xác, kiểm tra **root cause và SQLState theo DBMS/driver**, không giả định một wrapper cố định.

### 24.3. Test hai flush riêng biệt

```java
@Test
void explicitFlushCanSeparateDeleteAndInsert() {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        UserAlias old = em.find(UserAlias.class, 1L);
        assertNotNull(old);

        em.remove(old);
        em.flush(); // DELETE old trước.

        em.persist(new UserAlias(2L, "primary"));
        em.flush(); // INSERT replacement sau.

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    } finally {
        em.close();
    }
}
```

Chỉ dùng mô hình này khi business rule thực sự cần **identity mới**. Nếu có FK tham chiếu `UserAlias#1`, DELETE có thể vẫn lỗi vì còn hàng phụ thuộc. Khi đó phải giải quyết schema/quan hệ, không thêm nhiều `flush()` ngẫu nhiên.

### 24.4. Đếm và so sánh log

Một bài test có giá trị cần ghi nhận:

```text
Case A: remove(); persist(); flush()
    → thường INSERT, rồi DELETE
    → có thể UNIQUE violation

Case B: remove(); flush(); persist(); flush()
    → DELETE trước, sau đó INSERT
    → có thể thành công nếu các constraint khác cho phép
```

Nếu chạy với Hibernate version/DBMS khác và quan sát kết quả khác, **giữ lại log cùng phiên bản/configuration** thay vì sửa kỳ vọng theo cảm tính. Thứ tự là chi tiết implementation của provider, không phải hứa hẹn JPA portable.

## 25. Các lỗi và triệu chứng thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Gọi `remove` rồi `persist` cùng giá trị UNIQUE nhưng INSERT lỗi | Entity insert được thực thi trước entity delete trong cùng flush | Cân nhắc UPDATE entity hiện có, hoặc tách hai flush có chủ đích |
| `ConstraintViolationException` dù trạng thái cuối nhìn hợp lệ | Constraint kiểm tra từng SQL trung gian | Xem thứ tự SQL, unique/FK/trigger/deferral |
| FK lỗi khi xóa parent | Child rows vẫn tham chiếu parent | Cascade/remove child, chuyển owner hoặc DB cascade đúng nghiệp vụ |
| FK lỗi khi insert child | Parent chưa tồn tại hoặc owning-side FK chưa được gán | Persist parent, đồng bộ mapping/cascade, kiểm tra insert ordering |
| `NOT NULL` lỗi khi insert child rồi update FK | Unidirectional OneToMany FK mapping có thể cần UPDATE sau INSERT | Cân nhắc `@ManyToOne` sở hữu FK, kiểm tra SQL thật |
| Thấy INSERT ngay sau `persist()` | `IDENTITY` cần ID được DB cấp | Kiểm tra generator; không mặc định mọi INSERT đợi flush |
| Không có UPDATE dù gọi setter | Entity không dirty, detached hoặc mapping immutable/updatable=false | Kiểm tra state, flush, access type và annotation |
| Một thao tác `Set.remove()` gây nhiều SQL | Collection action tái tạo link rows | Kiểm tra collection semantics, cân nhắc mapping khác |
| Bật batching nhưng ít batch | SQL xen kẽ, identity generator, batch size/cấu hình không phù hợp | Đo, thử `order_inserts/updates`, xem ID strategy |
| `flush()` không cho transaction khác thấy dữ liệu | Chưa commit, isolation đang che uncommitted data | Phân biệt flush với commit/isolation |
| Query giữa transaction làm SQL chạy sớm | AUTO flush trước query có query spaces liên quan | Phân tích flush mode và SQL timeline |
| Bulk update xong entity managed vẫn cũ | Bulk DML không đồng bộ L1 state như dirty checking | Refresh/clear hợp lý, tránh merge stale state |
| Exception ở flush nhưng code vẫn tiếp tục dùng EM | Persistence context/transaction có thể không còn hợp lệ sau lỗi SQL | Rollback và đóng/recreate context |
| `order_updates=true` không sửa được swap UNIQUE | Sắp xếp để batch không giải quyết được constraint cycle | Dùng nghiệp vụ nhiều bước/deferrable constraint hoặc schema khác |

## 26. Quy trình chẩn đoán lỗi ActionQueue

Khi gặp lỗi mà **thứ tự Java có vẻ đúng nhưng database báo sai**, hãy làm theo trình tự:

**Bước 1 — Xác định hành vi nghiệp vụ muốn có.**

Ví dụ: “Xóa `UserAlias#1` rồi tạo `UserAlias#2` với cùng alias” khác với “chuyển alias từ user A sang user B” hoặc “sửa record hiện có”.

**Bước 2 — Kiểm tra database constraints.**

Xem PK/FK/UNIQUE/CHECK, `NOT NULL`, triggers, deferrability và các bảng liên quan. Đừng chỉ đọc annotation; schema production có thể khác.

**Bước 3 — Kiểm tra entity lifecycle và owning side.**

Entity nào là `managed`, `new`, `removed`, `detached`? Có cascade/orphanRemoval không? FK được quản lý ở bên nào? Có `@OnDelete` database cascade không?

**Bước 4 — Kiểm tra flush boundaries.**

Có explicit `flush()`, commit, JPQL/HQL query hoặc native query nào chạy trước dự kiến không? Flush mode là `AUTO`, `COMMIT`, `ALWAYS` hay `MANUAL`?

**Bước 5 — Kiểm tra ID strategy.**

`IDENTITY` có khiến INSERT chạy sớm không? Có sequence/assigned ID không? ID có được cấp trước khi insert không?

**Bước 6 — Quan sát SQL thật.**

Bật SQL logging/tracing an toàn trong môi trường test; ghi lại thứ tự các statement và giá trị constraint liên quan.

**Bước 7 — So sánh với ActionQueue của đúng Hibernate version.**

Với Hibernate ORM 7.4, xem danh sách nhóm action ở mục 6. Không dùng một bảng thứ tự trích từ Hibernate 5 cho tất cả các phiên bản.

**Bước 8 — Chọn giải pháp đúng domain.**

Có thể dùng UPDATE thay delete+insert, explicit flush có chủ đích, sắp xếp relation lifecycle, thay schema, dùng constraint deferral hoặc chuyển thiết kế entity liên kết.

**Bước 9 — Kiểm tra hồi quy trong integration test.**

Test với DBMS tương tự production, constraint thực, nhiều transaction nếu có race condition; bảo đảm rollback/cleanup đúng.

## 27. Những hiểu nhầm cần tránh

**“`remove()` đứng trước `persist()` nên SQL DELETE chắc chắn đứng trước INSERT.”** Không. ActionQueue có thể thực thi entity INSERT trước ordinary entity DELETE trong cùng flush.

**“Hàng đợi hành động chỉ là danh sách SQL FIFO.”** Không. Hibernate lập action từ lifecycle, dirty checking, cascade và collection changes; sau đó áp dụng thứ tự execution của provider.

**“Chỉ có insert/update/delete cho entity, không có collection action.”** Không. Collection table, join table, order index và orphan removal có action riêng.

**“Mọi DELETE đều cuối cùng.”** Không. `OrphanRemovalAction` và những SQL DELETE phát sinh từ collection actions có thể nằm trước entity deletion thông thường.

**“`flush()` là commit.”** Không. Flush đồng bộ DML nhưng transaction vẫn có thể rollback.

**“Bật `order_inserts` bảo đảm mọi INSERT được sắp theo thứ tự Java.”** Không. Nó là tối ưu batching, có cân nhắc FK, không phải bảo đảm sequence theo nguồn code.

**“Dùng IDENTITY thì INSERT vẫn luôn đợi flush.”** Không. Hibernate thường phải INSERT sớm để lấy ID từ database.

**“Cứ thêm `flush()` sau mỗi lời gọi để chắc đúng.”** Không nên. Điều đó có thể giảm batching, tăng round trips và che lỗi domain; chỉ đặt flush boundary khi thực sự cần đồng bộ.

**“Bulk JPQL update dùng cùng ActionQueue như sửa field managed.”** Không. Bulk query có execution path khác và có thể khiến L1 state cũ.

**“ActionQueue bảo đảm mọi constraint cuối transaction đều hợp lệ.”** Không. Database kiểm tra constraints theo thời điểm/deferral của nó; unique swap, FK cycles và custom triggers vẫn cần giải pháp riêng.

**“Một câu `INSERT` ở log là một JDBC round trip.”** Không nhất thiết khi JDBC batching bật; cần công cụ đo phù hợp.

## 28. Bài tập tình huống

### Bài 1 — Xóa trước, chèn sau

```java
em.remove(oldUser);
em.persist(newUser);
em.flush();
```

`oldUser` và `newUser` có ID khác nhau nhưng cùng email UNIQUE. Vì sao vẫn có thể lỗi?

**Giải thích:** Với thứ tự action thông thường ở Hibernate 7.4, insert action có thể chạy trước ordinary entity delete. Database thấy email cũ còn tồn tại nên từ chối INSERT.

### Bài 2 — Ranh giới flush

```java
em.remove(oldUser);
em.flush();
em.persist(newUser);
em.flush();
```

Có phải sau lần flush đầu tiên DELETE đã commit?

**Giải thích:** Không. Nó đã được đồng bộ tới database trong transaction hiện tại nhưng chưa commit. Rollback vẫn có thể hoàn tác cả DELETE và INSERT.

### Bài 3 — Setter nhưng không UPDATE

```java
Customer c = em.find(Customer.class, 10L);
c.rename(c.getDisplayName());
em.flush();
```

Có phải Hibernate luôn thực thi `EntityUpdateAction`?

**Giải thích:** Không. Dirty checking có thể phát hiện trạng thái không đổi, nên không cần UPDATE.

### Bài 4 — Ba lần sửa một field

```java
c.rename("A");
c.rename("B");
c.rename("C");
em.flush();
```

Có bắt buộc ba UPDATE?

**Giải thích:** Không. Nếu không flush ở giữa và c là managed, ORM thường chỉ cần đồng bộ giá trị cuối `"C"`.

### Bài 5 — FK cha con

`OrderLine` có FK `order_id NOT NULL`, nhưng app chỉ thêm line vào inverse collection của `PurchaseOrder`, không set `line.order`. Nguy cơ gì?

**Giải thích:** Owning side không được cập nhật; FK có thể thiếu, khiến flush báo lỗi. Dùng helper đồng bộ hai phía và cascade phù hợp.

### Bài 6 — OrphanRemovalAction

Gỡ một `InvoiceLine` trong `@OneToMany(orphanRemoval=true)` có giống `em.remove(someUnrelatedEntity)` về vị trí action không?

**Giải thích:** Không nhất thiết. Orphan removal có action riêng, đứng trước entity inserts trong sơ đồ Hibernate 7.4; ordinary entity deletion thường cuối.

### Bài 7 — Swap UNIQUE

Hai seat có mã `"A1"` và `"A2"`. Đổi trực tiếp hai field rồi flush lỗi UNIQUE. Bật `order_updates=true` có chắc sửa được không?

**Giải thích:** Không. Đảo thứ tự UPDATE cũng có thể vi phạm unique ngay ở statement đầu. Cần xử lý bằng giá trị trung gian, constraint deferral hợp lệ hoặc mô hình khác.

### Bài 8 — Collection table

Gỡ một phần tử `@ElementCollection Set<String>` thấy DELETE trong log trước DELETE entity parent. Có mâu thuẫn với việc entity DELETE chạy cuối không?

**Giải thích:** Không. DELETE đó thuộc **collection action**, không phải `EntityDeleteAction` của parent.

### Bài 9 — IDENTITY

Tại sao thấy INSERT ngay sau `em.persist()` dù chưa `em.flush()`?

**Giải thích:** `GenerationType.IDENTITY` thường cần thực thi INSERT để database trả generated ID. Kiểm tra strategy trước khi suy luận ActionQueue order.

### Bài 10 — Query chen giữa

Tại sao thêm một JPQL query giữa `remove()` và `persist()` khiến log DML khác trước?

**Giải thích:** `AUTO` flush có thể đồng bộ pending changes trước query khi query spaces liên quan; do đó các action được chia qua hai lần flush. Không nên dùng query làm công cụ điều khiển flush không tường minh.

### Bài 11 — Bulk update

Bulk JPQL đổi trạng thái nhiều orders, nhưng object `Order` đã managed vẫn có giá trị cũ. Tại sao?

**Giải thích:** Bulk mutation không cập nhật từng managed entity theo dirty checking thông thường. Cần kế hoạch refresh/clear và kiểm soát pending changes.

### Bài 12 — JDBC batching

`hibernate.jdbc.batch_size=50`, nhưng mỗi INSERT xảy ra riêng vì IDENTITY. Có phải cài đặt sai?

**Giải thích:** Không nhất thiết. Identity generator thường hạn chế insert batching. Đọc tài liệu Hibernate/DBMS và đánh giá ID strategy, số statement đồng dạng trước khi kết luận.

## 29. Tài liệu tham khảo chính thức

- [Hibernate ORM 7.4 User Guide — Flushing, Flush operation order](https://docs.hibernate.org/stable/core/userguide/html_single/#flushing-flush-order): thứ tự các nhóm action, ví dụ INSERT trước DELETE và mối quan hệ với dirty checking.
- [Hibernate ORM 7.4 User Guide — Flushing](https://docs.hibernate.org/stable/core/userguide/html_single/#flushing): transaction write-behind, `AUTO`, `COMMIT`, `ALWAYS`, `MANUAL` và thời điểm đồng bộ.
- [Hibernate ORM 7.4 User Guide — Batching](https://docs.hibernate.org/stable/core/userguide/html_single/#batch): JDBC batching, `hibernate.jdbc.batch_size`, `hibernate.order_inserts`, `hibernate.order_updates`, giới hạn của IDENTITY.
- [Hibernate ORM Javadoc — `ActionQueue`](https://docs.hibernate.org/stable/orm/javadocs/org/hibernate/engine/spi/ActionQueue.html): vai trò hàng đợi DML trong session và các phương thức liên quan.
- [Hibernate ORM Javadoc — `BatchSettings`](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/cfg/BatchSettings.html): ý nghĩa các cấu hình batch và sắp xếp INSERT/UPDATE.
- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): `EntityManager.persist`, `remove`, `flush`, flush modes và semantics của persistence context.
- [PostgreSQL Documentation — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): PK, FK, UNIQUE và tác động của constraint tại database.
- [PostgreSQL Documentation — SET CONSTRAINTS](https://www.postgresql.org/docs/current/sql-set-constraints.html): thời điểm kiểm tra deferred constraints khi có cấu hình hỗ trợ.

**Phạm vi phiên bản:** Danh sách tám nhóm action trong bài căn cứ Hibernate ORM 7.4. Các bản 5.x, 6.x hoặc nhánh phát triển mới có thể khác chi tiết; trước khi dựa vào thứ tự execution để thiết kế một nghiệp vụ nhạy cảm, cần kiểm tra **đúng phiên bản Hibernate, database, kiểu ID, cascade, flush mode và SQL thật**.

## Kết luận

Hibernate **không phải** công cụ thực thi từng lệnh `persist()`, setter và `remove()` thành SQL ngay lập tức theo đúng thứ tự Java. Persistence context giữ state; dirty checking xác định những thay đổi cần ghi; `ActionQueue` lập kế hoạch các action; và `flush()` đồng bộ chúng qua JDBC theo quy tắc của Hibernate.

Theo Hibernate ORM 7.4, orphan-removal actions, entity inserts, entity updates, các nhóm collection actions và ordinary entity deletes có **thứ tự thực thi riêng**. Do đó gọi `remove()` trước `persist()` có thể vẫn dẫn tới `INSERT` trước `DELETE`, gây lỗi `UNIQUE` dù trạng thái cuối người lập trình mong muốn là hợp lệ. Khóa ngoại, generated ID, cascade, JDBC batching và AUTO flush trước query cũng làm SQL timeline phức tạp hơn.

Cách xử lý bền vững là **thiết kế đúng lifecycle và constraint**, quan sát SQL trong transaction thực, sử dụng `flush()` giữa các pha **khi thật sự cần**, và kiểm thử trên DBMS cùng phiên bản Hibernate triển khai. Đừng lấy thứ tự lời gọi Java làm bằng chứng về **thứ tự insert, update, delete ở database**.
