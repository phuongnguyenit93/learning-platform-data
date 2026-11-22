# JPQL UPDATE, DELETE và @Modifying trong Spring Data JPA

## 1. Bulk DML là gì?

Trong JPA, thao tác cập nhật hoặc xóa dữ liệu thường được thực hiện thông qua entity đang được persistence context quản lý. Ứng dụng tải entity, thay đổi thuộc tính hoặc gọi phương thức remove, rồi JPA đồng bộ thay đổi xuống database khi flush hoặc commit transaction.

Với số lượng lớn bản ghi, cách làm đó có thể tốn bộ nhớ và thời gian vì phải tải nhiều entity, quản lý trạng thái của từng object và thực hiện các bước lifecycle tương ứng.

**Bulk DML** (bulk data manipulation) cho phép gửi một câu lệnh UPDATE hoặc DELETE tác động lên một tập entity trực tiếp tại database. JPQL hỗ trợ hai dạng câu lệnh này. Spring Data JPA cho phép khai báo chúng trong repository bằng **@Query** kết hợp **@Modifying**.

Ví dụ, thay vì tải hàng nghìn tài khoản rồi đặt **active = false** từng object, ứng dụng có thể gửi một câu lệnh cập nhật cho tất cả tài khoản thỏa điều kiện.

Bulk DML phù hợp khi:

- Cập nhật một thuộc tính theo cùng một quy tắc cho nhiều bản ghi.
- Xóa dữ liệu hết hạn theo điều kiện.
- Chuyển trạng thái hàng loạt.
- Dọn dữ liệu cũ theo lịch.
- Thực hiện thao tác mà không cần gọi logic domain riêng trên từng entity.

Đổi lại, bulk DML bỏ qua nhiều cơ chế vòng đời entity. Vì vậy, cần hiểu rõ ảnh hưởng tới persistence context, callback, cascade và optimistic locking trước khi sử dụng.

## 2. Cú pháp JPQL UPDATE và DELETE

JPQL sử dụng tên entity và thuộc tính Java được ánh xạ, không sử dụng trực tiếp tên bảng và tên cột SQL.

Cập nhật có dạng:

~~~sql
UPDATE EntityName alias
SET alias.property = :value
WHERE condition
~~~

Xóa có dạng:

~~~sql
DELETE FROM EntityName alias
WHERE condition
~~~

Ví dụ với entity **User**:

~~~java
@Entity
@Table(name = "users")
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String email;
    private boolean active;
    private Instant lastLoginAt;
    private Instant createdAt;

    @Enumerated(EnumType.STRING)
    private UserStatus status;

    protected User() {
    }

    // Constructors, getters and domain methods omitted.
}
~~~

JPQL cập nhật tất cả tài khoản không hoạt động đã đăng nhập lần cuối trước một mốc thời gian:

~~~sql
UPDATE User u
SET u.active = false
WHERE u.active = true
  AND u.lastLoginAt < :cutoff
~~~

JPQL xóa tài khoản ở trạng thái đã khóa và được tạo trước mốc thời gian:

~~~sql
DELETE FROM User u
WHERE u.status = :status
  AND u.createdAt < :cutoff
~~~

Các quy tắc quan trọng:

- **User** là entity name, thường là tên lớp entity hoặc giá trị được khai báo trong **@Entity(name = "...")**.
- **active**, **lastLoginAt**, **status** là thuộc tính entity, không phải tên cột database.
- **WHERE** giới hạn tập entity bị tác động. Nếu bỏ **WHERE**, câu lệnh có thể cập nhật hoặc xóa toàn bộ entity thuộc kiểu được chỉ định.
- Kiểu của giá trị trong **SET** phải tương thích với kiểu thuộc tính.
- Một câu lệnh bulk update/delete chỉ chỉ định một entity type trong mệnh đề UPDATE hoặc FROM; phạm vi còn bao gồm các lớp con theo quy tắc kế thừa JPA.
- DELETE không tự cascade sang các entity liên quan.

JPQL bulk DML không phải một câu SELECT. Nó được thực thi bằng **executeUpdate()** của JPA Query API.

## 3. Vì sao cần @Modifying?

Spring Data JPA thường xem method có **@Query** là truy vấn đọc. Khi method chứa JPQL UPDATE hoặc DELETE, cần đánh dấu bằng **@Modifying** để Spring Data thực thi nó như một modifying query.

Ví dụ:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    @Modifying
    @Query("""
        update User u
        set u.active = false
        where u.active = true
          and u.lastLoginAt < :cutoff
    """)
    int deactivateInactiveUsers(
        @Param("cutoff") Instant cutoff
    );
}
~~~

Khi gọi method, Spring Data thực thi câu lệnh update thay vì cố đọc kết quả như một truy vấn select.

**@Modifying** có ý nghĩa khi kết hợp với query method khai báo bằng **@Query**. Nó không cần thiết cho:

- Derived delete query như **deleteByStatus(...)**, vì Spring Data biết method đó là thao tác xóa từ tên method.
- Custom repository implementation, nơi code tự điều khiển **EntityManager** hoặc API truy cập dữ liệu.
- Các method CRUD kế thừa từ repository.

Theo API Spring Data JPA, các loại query cần **@Modifying** bao gồm INSERT, UPDATE, DELETE và một số câu lệnh DDL. Bài này tập trung vào JPQL UPDATE và DELETE.

## 4. Khai báo JPQL UPDATE trong repository

Ví dụ cập nhật trạng thái người dùng theo ID:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    @Modifying
    @Query("""
        update User u
        set u.status = :newStatus
        where u.id = :id
    """)
    int updateStatus(
        @Param("id") Long id,
        @Param("newStatus") UserStatus newStatus
    );
}
~~~

Gọi từ service:

~~~java
@Service
public class UserService {

    private final UserRepository userRepository;

    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @Transactional
    public int changeStatus(Long id, UserStatus status) {
        return userRepository.updateStatus(id, status);
    }
}
~~~

Method trả về **int** là số entity được cập nhật theo kết quả của thao tác bulk. Nếu ID không tồn tại, số lượng thường là **0**. Nếu một bản ghi được cập nhật, số lượng là **1**.

Có thể dùng int để:

- Kiểm tra có bản ghi nào thỏa điều kiện hay không.
- Phát hiện ID không tồn tại hoặc điều kiện không khớp.
- Ghi nhận số lượng bản ghi được xử lý trong tác vụ nền.

Không trả về entity từ một bulk update method. Câu lệnh không tải và đồng bộ lại object entity như một truy vấn đọc.

## 5. Khai báo JPQL DELETE trong repository

Ví dụ xóa các tài khoản đã hết hạn:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    @Modifying
    @Query("""
        delete from User u
        where u.status = :status
          and u.createdAt < :cutoff
    """)
    int deleteExpiredUsers(
        @Param("status") UserStatus status,
        @Param("cutoff") Instant cutoff
    );
}
~~~

Service thực thi:

~~~java
@Service
public class UserCleanupService {

    private final UserRepository userRepository;

    public UserCleanupService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @Transactional
    public int removeExpiredUsers(
            UserStatus status,
            Instant cutoff) {

        return userRepository.deleteExpiredUsers(status, cutoff);
    }
}
~~~

Câu lệnh trên gửi một bulk delete tới database. Nó không tải trước từng User rồi gọi **EntityManager.remove()** cho từng object.

Hãy kiểm tra điều kiện xóa thật kỹ. Trước khi chạy tác vụ xóa dữ liệu quan trọng, nên xác nhận số lượng bản ghi dự kiến bằng một truy vấn đọc tương ứng hoặc một bước dry-run của ứng dụng. Một câu lệnh DELETE không có điều kiện có thể tác động tới toàn bộ tập entity.

## 6. Transaction là yêu cầu bắt buộc

Bulk update/delete cần transaction. JPA yêu cầu thao tác modifying query được thực thi trong transaction; nếu không có transaction phù hợp, provider có thể ném **TransactionRequiredException**.

Một điểm dễ nhầm là method query được khai báo trực tiếp trong repository không tự động nhận cấu hình transaction mặc định chỉ vì repository mở rộng JpaRepository. Các method CRUD kế thừa có transaction configuration riêng, còn declared query methods cần được đặt trong transaction rõ ràng.

Cách thường dùng là khai báo ranh giới transaction ở service:

~~~java
@Service
public class UserMaintenanceService {

    private final UserRepository repository;

    public UserMaintenanceService(UserRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int deactivateBefore(Instant cutoff) {
        return repository.deactivateInactiveUsers(cutoff);
    }
}
~~~

**@Transactional** mặc định dùng transaction ghi thông thường, phù hợp cho bulk update/delete.

Nếu class service có **@Transactional(readOnly = true)** ở cấp lớp, hãy ghi đè cho method ghi:

~~~java
@Service
@Transactional(readOnly = true)
public class UserMaintenanceService {

    private final UserRepository repository;

    public UserMaintenanceService(UserRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int deactivateBefore(Instant cutoff) {
        return repository.deactivateInactiveUsers(cutoff);
    }
}
~~~

**readOnly = true** là một transaction hint cho provider/driver và có thể kích hoạt tối ưu hóa. Nó không phải cơ chế kiểm tra tuyệt đối để ngăn mọi câu lệnh ghi. Vì vậy, method thực hiện bulk DML cần được chạy trong transaction ghi phù hợp.

Có thể đặt **@Transactional** trực tiếp trên repository method, nhưng khai báo transaction ở service thường giúp quản lý một use case gồm nhiều thao tác repository trong cùng một ranh giới nhất quán.

## 7. Persistence context không tự đồng bộ sau bulk DML

Đây là điểm quan trọng nhất khi dùng JPQL UPDATE/DELETE.

Persistence context lưu các entity đang được quản lý trong **EntityManager**. Khi thực hiện bulk DML, database thay đổi trực tiếp nhưng JPA không tự cập nhật các object đang nằm trong persistence context.

Ví dụ:

~~~java
User user = entityManager.find(User.class, 10L);

repository.updateStatus(10L, UserStatus.BLOCKED);

// Object user đang được quản lý có thể vẫn giữ trạng thái cũ.
System.out.println(user.getStatus());
~~~

Câu lệnh bulk update đã thay đổi dữ liệu trong database, nhưng object **user** đã tải trước đó có thể vẫn chứa trạng thái cũ trong bộ nhớ.

Điều tương tự xảy ra với DELETE: một entity đã được tải có thể vẫn tồn tại trong persistence context dù hàng tương ứng đã bị xóa trực tiếp ở database.

Hậu quả có thể gồm:

- Service đọc lại giá trị cũ từ entity đã managed.
- Logic nghiệp vụ tiếp tục dùng trạng thái không còn đúng.
- Một lần flush sau đó có thể ghi các thay đổi đang chờ của entity managed.
- Entity đã bị xóa ở database nhưng vẫn được tham chiếu trong bộ nhớ.

Jakarta Persistence quy định persistence context không được đồng bộ tự động với kết quả của bulk update/delete. Vì vậy, hãy thực hiện bulk DML trong transaction và quản lý các entity bị ảnh hưởng cẩn thận.

## 8. clearAutomatically và flushAutomatically

Spring Data JPA cung cấp hai thuộc tính của **@Modifying** để kiểm soát persistence context:

| Thuộc tính | Tác dụng | Mặc định |
|---|---|---|
| **flushAutomatically** | Flush persistence context trước khi chạy modifying query | **false** |
| **clearAutomatically** | Clear persistence context sau khi chạy modifying query | **false** |

Ví dụ:

~~~java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    update User u
    set u.active = false
    where u.lastLoginAt < :cutoff
""")
int deactivateBefore(@Param("cutoff") Instant cutoff);
~~~

### flushAutomatically = true

**flushAutomatically** yêu cầu Spring Data gọi **EntityManager.flush()** trước khi thực thi câu lệnh modifying query.

Flush đồng bộ các thay đổi đang chờ trong persistence context xuống database. Điều này hữu ích khi bulk query cần nhìn thấy các thay đổi trước đó hoặc khi sắp clear persistence context.

Flush không đồng nghĩa với commit. Transaction vẫn có thể rollback sau đó.

### clearAutomatically = true

**clearAutomatically** yêu cầu Spring Data gọi **EntityManager.clear()** sau khi thực thi modifying query.

Clear làm tất cả entity đang managed trong persistence context trở thành detached. Lần truy vấn tiếp theo sẽ phải tải trạng thái từ database thay vì dùng các object managed cũ.

Lưu ý: clear() tác động tới toàn bộ persistence context, không chỉ entity bị bulk DML thay đổi. Các entity khác đang được service sử dụng cũng bị detach.

### Vì sao đôi khi cần bật cả hai?

Nếu clear persistence context trong khi còn thay đổi chưa flush, những thay đổi đó có thể bị loại bỏ khỏi persistence context. Vì vậy, khi use case cần giữ lại các thay đổi đang chờ trước bulk query, có thể bật cả **flushAutomatically = true** và **clearAutomatically = true**.

Tuy nhiên, flush toàn bộ persistence context có thể ghi thêm nhiều thay đổi không liên quan và làm phát sinh constraint hoặc lỗi validation trước câu lệnh bulk. Chỉ bật các thuộc tính này khi hiểu rõ trạng thái persistence context của use case.

Một cách khác là tự gọi **EntityManager.flush()** trước bulk DML và **EntityManager.clear()** sau đó trong service, nếu cần kiểm soát thứ tự cụ thể.

## 9. Ví dụ quản lý trạng thái persistence context

Repository:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    @Modifying(
        flushAutomatically = true,
        clearAutomatically = true
    )
    @Query("""
        update User u
        set u.status = :status
        where u.id = :id
    """)
    int updateStatusAndClear(
        @Param("id") Long id,
        @Param("status") UserStatus status
    );
}
~~~

Service:

~~~java
@Service
public class UserService {

    private final UserRepository repository;
    private final EntityManager entityManager;

    public UserService(
            UserRepository repository,
            EntityManager entityManager) {
        this.repository = repository;
        this.entityManager = entityManager;
    }

    @Transactional
    public UserStatus changeStatus(Long id, UserStatus status) {
        int updated = repository.updateStatusAndClear(id, status);

        if (updated == 0) {
            throw new EntityNotFoundException("User not found");
        }

        User reloaded = entityManager.find(User.class, id);
        return reloaded.getStatus();
    }
}
~~~

Sau khi repository method chạy, persistence context được clear. Lệnh find() tiếp theo tải entity mới từ database trong cùng transaction.

Nếu không dùng **clearAutomatically**, có thể gọi **entityManager.clear()** sau bulk query hoặc **entityManager.refresh(user)** cho một entity managed cụ thể. Chọn cách phù hợp với số lượng entity và các object service còn cần sử dụng.

Không gọi clear() một cách máy móc nếu service còn cần các entity managed hoặc thay đổi chưa được flush.

## 10. Bulk DELETE khác derived delete như thế nào?

Spring Data JPA hỗ trợ cả derived delete query và bulk delete bằng **@Modifying**.

Ví dụ derived delete:

~~~java
void deleteByRoleId(Long roleId);
~~~

Ví dụ bulk JPQL delete:

~~~java
@Modifying
@Query("delete from User u where u.role.id = :roleId")
int deleteInBulkByRoleId(@Param("roleId") Long roleId);
~~~

Hai method có thể xóa cùng tập dữ liệu nhưng cách thực thi khác nhau:

| Tiêu chí | Derived delete | Bulk JPQL DELETE |
|---|---|---|
| Cách thực thi | Truy vấn entity phù hợp rồi xóa từng entity | Một câu lệnh DELETE tác động trực tiếp tại database |
| Tải entity vào bộ nhớ | Có | Không cần tải từng entity |
| Entity lifecycle callbacks | Được gọi theo quy trình remove từng entity | Không được gọi cho từng entity |
| Cascade remove của JPA | Được áp dụng theo mapping remove | Không tự cascade sang entity liên quan |
| Bộ nhớ với số lượng lớn | Có thể cao vì entity được tải và giữ trong session | Thường thấp hơn |
| Số lượng bản ghi | Có thể trả về theo chữ ký method | Có thể nhận số entity bị tác động qua int |

Derived delete có thể gọi **@PreRemove** và các lifecycle callback liên quan vì Spring Data tải entity rồi xóa từng object. Nó phù hợp khi cần logic xóa ở cấp entity, callback hoặc cascade.

Bulk delete phù hợp khi cần hiệu năng và không cần xử lý từng entity. Khi xóa số lượng lớn, derived delete có thể tiêu tốn nhiều bộ nhớ vì các entity được tải vào persistence context trước khi xóa.

Không chọn bulk delete nếu nghiệp vụ phụ thuộc vào **@PreRemove**, entity listener, cascade remove hoặc logic domain trên từng object.

## 11. Bulk DML bỏ qua lifecycle callbacks và cascade

Bulk update/delete tác động trực tiếp lên database, không thực hiện chu trình lifecycle của từng entity.

Ví dụ các callback sau không được gọi cho từng entity bị bulk DML tác động:

- **@PreUpdate**
- **@PostUpdate**
- **@PreRemove**
- **@PostRemove**

Các entity listener và Spring Data auditing dựa trên lifecycle callback cũng không tự chạy cho từng bản ghi được cập nhật hoặc xóa bằng bulk DML. Bean Validation tự động gắn với lifecycle event cũng không được thực hiện theo cách cập nhật entity thông thường.

Nếu cần cập nhật trường audit như **updatedAt**, **updatedBy**, hãy đưa giá trị đó trực tiếp vào câu lệnh JPQL hoặc xử lý riêng theo nghiệp vụ.

Ví dụ:

~~~java
@Modifying
@Query("""
    update User u
    set u.status = :status,
        u.updatedAt = :updatedAt
    where u.status = :oldStatus
""")
int changeStatusAndAudit(
    @Param("oldStatus") UserStatus oldStatus,
    @Param("status") UserStatus status,
    @Param("updatedAt") Instant updatedAt
);
~~~

Bulk DELETE cũng không tự áp dụng **CascadeType.REMOVE** hoặc **orphanRemoval** như khi xóa entity managed. Nếu bảng con còn tham chiếu tới bản ghi cha, foreign key có thể khiến DELETE thất bại.

Có thể xử lý quan hệ bằng cách:

1. Xóa bản ghi con bằng một câu lệnh bulk phù hợp trước.
2. Xóa bản ghi cha sau khi các ràng buộc đã được thỏa mãn.
3. Dùng cơ chế cascade ở database nếu kiến trúc và chính sách dữ liệu cho phép.
4. Dùng entity removal thông thường khi cần JPA cascade và lifecycle callback.

Database trigger vẫn được database thực thi theo quy tắc của hệ quản trị, dù JPA entity callback không chạy.

## 12. Bulk UPDATE và optimistic locking với @Version

Optimistic locking thông thường sử dụng thuộc tính **@Version**. Khi cập nhật một entity managed, JPA kiểm tra version để phát hiện thay đổi đồng thời.

Bulk update bỏ qua cơ chế optimistic locking tự động. Nếu câu lệnh không kiểm tra version, nó có thể ghi đè thay đổi của transaction khác mà không phát hiện xung đột theo cách thông thường.

Ví dụ entity:

~~~java
@Entity
public class Inventory {

    @Id
    private Long id;

    private int quantity;

    @Version
    private long version;

    protected Inventory() {
    }
}
~~~

Nếu cần kiểm tra version trong bulk update, hãy thêm điều kiện version và tăng version một cách tường minh:

~~~java
@Modifying
@Query("""
    update Inventory i
    set i.quantity = :quantity,
        i.version = i.version + 1
    where i.id = :id
      and i.version = :expectedVersion
""")
int updateQuantity(
    @Param("id") Long id,
    @Param("quantity") int quantity,
    @Param("expectedVersion") long expectedVersion
);
~~~

Service kiểm tra số lượng bản ghi được cập nhật:

~~~java
@Transactional
public void changeQuantity(
        Long id,
        int quantity,
        long expectedVersion) {

    int updated = repository.updateQuantity(
        id,
        quantity,
        expectedVersion
    );

    if (updated == 0) {
        throw new OptimisticLockingFailureException(
            "Inventory does not exist or its version has changed"
        );
    }
}
~~~

Khi **updated == 0**, ID có thể không tồn tại hoặc version không còn khớp. Nếu cần phân biệt hai trường hợp, hãy truy vấn thêm theo chính sách nghiệp vụ.

Việc tăng version thủ công phải được kiểm thử với provider và database thực tế. Nếu không cần optimistic concurrency cho thao tác hàng loạt, hãy ghi rõ chính sách chấp nhận cập nhật đè và giới hạn phạm vi tác động.

## 13. Kết hợp nhiều điều kiện trong UPDATE

JPQL cho phép cập nhật nhiều thuộc tính trong cùng câu lệnh, miễn giá trị tương thích kiểu:

~~~java
@Modifying
@Query("""
    update Product p
    set p.price = :price,
        p.active = :active,
        p.updatedAt = :updatedAt
    where p.category.id = :categoryId
""")
int updateProductsInCategory(
    @Param("categoryId") Long categoryId,
    @Param("price") BigDecimal price,
    @Param("active") boolean active,
    @Param("updatedAt") Instant updatedAt
);
~~~

Câu lệnh này cập nhật các thuộc tính của tất cả Product có category ID tương ứng.

Có thể dùng biểu thức số học:

~~~sql
UPDATE Product p
SET p.stock = p.stock - :amount
WHERE p.id = :id
  AND p.stock >= :amount
~~~

Điều kiện **p.stock >= :amount** giúp tránh giảm số lượng xuống dưới 0 trong câu lệnh cập nhật này. Tuy nhiên, nếu nhiều transaction đồng thời thao tác trên cùng bản ghi, cần đánh giá transaction isolation, khóa và chính sách retry phù hợp.

Không đưa chuỗi JPQL được ghép từ input người dùng vào **@Query**. Hãy dùng named parameter để bind giá trị. Tên entity, property và cấu trúc câu lệnh nên được cố định trong mã nguồn.

## 14. Bulk DML với native SQL

**@Modifying** cũng có thể được dùng với **@Query(nativeQuery = true)** khi cần SQL riêng cho database:

~~~java
@Modifying
@Query(
    value = """
        update users
        set active = false
        where last_login_at < :cutoff
    """,
    nativeQuery = true
)
int deactivateWithNativeSql(
    @Param("cutoff") Instant cutoff
);
~~~

Native SQL dùng tên bảng, tên cột và cú pháp của hệ quản trị database. Nó có thể tận dụng tính năng đặc thù nhưng làm giảm tính portable của repository.

Với native query, cần kiểm tra:

- Kiểu tham số và cách bind của JDBC driver.
- Tên bảng/cột thực tế và schema.
- Cú pháp database-specific.
- Kiểu giá trị trả về và số lượng bản ghi.
- Tác động của câu lệnh tới persistence context và cache.

Native DML cũng không đồng bộ các entity managed trong persistence context. Hãy xử lý flush/clear hoặc refresh tương tự như bulk JPQL khi các entity đang được quản lý có thể bị ảnh hưởng.

## 15. Khi nào nên dùng CriteriaUpdate và CriteriaDelete?

Nếu điều kiện update/delete được tạo động bằng Criteria API, JPA cung cấp **CriteriaUpdate** và **CriteriaDelete**.

Ví dụ CriteriaUpdate:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();

CriteriaUpdate<User> update =
    cb.createCriteriaUpdate(User.class);

Root<User> user = update.from(User.class);

update.set(user.get("active"), false);
update.where(
    cb.lessThan(user.get("lastLoginAt"), cutoff)
);

int affected = entityManager
    .createQuery(update)
    .executeUpdate();
~~~

Ví dụ CriteriaDelete:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();

CriteriaDelete<User> delete =
    cb.createCriteriaDelete(User.class);

Root<User> user = delete.from(User.class);

delete.where(
    cb.equal(user.get("status"), UserStatus.EXPIRED)
);

int affected = entityManager
    .createQuery(delete)
    .executeUpdate();
~~~

Criteria bulk DML có cùng đặc tính quan trọng với JPQL bulk DML: thực thi trực tiếp trên database, không tự đồng bộ persistence context và bỏ qua optimistic locking tự động.

Dùng **@Modifying** khi câu lệnh tĩnh, dễ khai báo trong repository bằng **@Query**. Dùng CriteriaUpdate/CriteriaDelete khi cần xây dựng điều kiện động theo cấu trúc chương trình hoặc cần Criteria API.

Các ví dụ Criteria trên là đoạn mã trong service/repository có EntityManager và transaction phù hợp; cần import **jakarta.persistence.criteria.CriteriaBuilder**, **CriteriaUpdate**, **CriteriaDelete** và các kiểu liên quan.

## 16. Hiệu năng và giới hạn của bulk DML

Bulk DML thường hiệu quả hơn việc tải hàng nghìn entity rồi cập nhật hoặc xóa từng object vì database nhận một câu lệnh cho cả tập dữ liệu.

Lợi ích:

- Không cần materialize toàn bộ entity vào persistence context.
- Giảm số lần round-trip giữa ứng dụng và database.
- Không cần gọi save() cho từng entity sau khi cập nhật thuộc tính.
- Có thể để database tối ưu câu lệnh theo index và execution plan.

Tuy nhiên, bulk DML không tự động nhanh trong mọi tình huống. Hiệu năng còn phụ thuộc:

- Số lượng bản ghi bị tác động.
- Index trên các cột trong điều kiện WHERE.
- Chi phí ghi transaction log và cập nhật index.
- Foreign key, trigger và constraint ở database.
- Lock contention và thời gian giữ transaction.
- Kích thước transaction và khả năng rollback.

Một câu lệnh cập nhật hàng triệu bản ghi có thể giữ lock lâu và tạo transaction log lớn. Với tác vụ rất lớn, cân nhắc chia thành nhiều batch theo ID hoặc mốc thời gian, commit từng batch và theo dõi tiến độ. JPQL bulk DML chuẩn không cung cấp cú pháp LIMIT trực tiếp cho UPDATE/DELETE; chiến lược chia batch cần được thiết kế bằng điều kiện hoặc truy vấn lấy ID phù hợp.

Bulk DML cũng khác JDBC batch. JDBC batch thường gửi nhiều câu lệnh cập nhật riêng cho các entity; bulk DML gửi một câu lệnh tác động lên một tập bản ghi thỏa điều kiện.

## 17. Lỗi thường gặp

### 17.1. Quên @Modifying

Method có **@Query** chứa UPDATE/DELETE nhưng thiếu **@Modifying** có thể bị Spring Data xử lý như truy vấn đọc và thất bại khi thực thi. Thêm **@Modifying** cho modifying query method.

### 17.2. Không có transaction

JPA yêu cầu transaction cho bulk DML. Đặt **@Transactional** ở service hoặc repository boundary phù hợp. Không dựa vào **@Modifying** để tự tạo transaction.

### 17.3. Dùng tên bảng thay cho entity name

JPQL dùng entity name và thuộc tính Java. Ví dụ **update User u set u.active = false**, không dùng tên bảng **users** hoặc cột **is_active**. Tên bảng/cột chỉ dùng trong native SQL.

### 17.4. Entity managed vẫn giữ dữ liệu cũ

Bulk DML không đồng bộ persistence context. Clear persistence context, refresh entity cụ thể hoặc dùng một persistence context mới trước khi đọc lại dữ liệu.

### 17.5. clearAutomatically làm mất thay đổi chưa flush

**clearAutomatically = true** detach toàn bộ entity. Nếu có thay đổi đang chờ và cần lưu, cân nhắc **flushAutomatically = true** hoặc flush tường minh trước khi clear.

### 17.6. Mong đợi callback và cascade được gọi

Bulk DML bỏ qua lifecycle callback và JPA cascade của từng entity. Nếu cần **@PreRemove**, auditing listener hoặc cascade remove, dùng derived delete hoặc xóa entity thông thường.

### 17.7. Không kiểm tra version

Bulk update bỏ qua optimistic locking tự động. Nếu cần phát hiện xung đột, đưa version vào điều kiện WHERE, tăng version thủ công khi thích hợp và kiểm tra số bản ghi được cập nhật.

### 17.8. Xóa entity cha khi còn entity con

Bulk DELETE không cascade. Foreign key có thể từ chối câu lệnh. Xử lý dữ liệu con trước hoặc chọn quy trình xóa entity có cascade phù hợp.

### 17.9. Dùng transaction read-only cho câu lệnh ghi

Không chạy bulk DML trong transaction được thiết kế là read-only. Dùng transaction ghi cho service method thực hiện update/delete.

### 17.10. Xóa hoặc cập nhật quá nhiều bản ghi trong một transaction

Một transaction lớn có thể giữ lock lâu và làm tăng log. Chia batch khi cần, giới hạn điều kiện và theo dõi số lượng affected.

## 18. Kiểm thử bulk UPDATE và DELETE

Nên dùng integration test với **@DataJpaTest** hoặc test context đầy đủ để kiểm tra query thực tế trên JPA provider và database mục tiêu.

Ví dụ kiểm thử update và clear persistence context:

~~~java
@DataJpaTest
class UserBulkDmlRepositoryTest {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void bulkUpdateChangesDatabaseAndClearsManagedEntities() {
        User user = userRepository.saveAndFlush(
            new User("user@example.com", true)
        );

        Long id = user.getId();
        User managed = entityManager.find(User.class, id);

        int updated = userRepository.deactivateById(id);

        assertThat(updated).isEqualTo(1);
        assertThat(entityManager.contains(managed)).isFalse();

        User reloaded = entityManager.find(User.class, id);
        assertThat(reloaded.isActive()).isFalse();
    }
}
~~~

Ví dụ giả định repository method **deactivateById** có **@Modifying(clearAutomatically = true)** và entity có constructor/getter tương ứng. **@DataJpaTest** thường chạy trong transaction kiểm thử và rollback sau test.

Các trường hợp nên kiểm tra:

1. UPDATE tác động đúng số lượng bản ghi.
2. DELETE chỉ xóa các entity thỏa điều kiện.
3. Điều kiện không khớp trả về số lượng **0**.
4. Không có WHERE chỉ được dùng khi thực sự muốn tác động toàn bộ tập entity.
5. Persistence context được clear hoặc refresh đúng cách.
6. Thay đổi đang chờ trước bulk query được flush khi cấu hình yêu cầu.
7. Callback và cascade không được giả định chạy trong bulk DML.
8. Version check phát hiện trường hợp version không khớp.
9. Foreign key và database constraint hoạt động như mong đợi.
10. Query chạy trong transaction ghi.
11. Native query, nếu có, chạy trên đúng database production.
12. Số lượng bản ghi lớn không gây lock hoặc thời gian transaction vượt giới hạn vận hành.

Với native query hoặc hành vi phụ thuộc dialect, nên kiểm thử bằng Testcontainers hoặc database tương đương môi trường production thay vì chỉ dựa vào H2.

## 19. Quy trình lựa chọn cách cập nhật/xóa

Khi cần thay đổi nhiều bản ghi:

1. Xác định thao tác có cần chạy domain logic, lifecycle callback, cascade hoặc auditing cho từng entity hay không.
2. Nếu cần xử lý từng entity, tải entity và dùng phương thức domain/remove hoặc derived delete phù hợp.
3. Nếu cùng một thay đổi áp dụng cho tập lớn, cân nhắc JPQL bulk UPDATE/DELETE.
4. Khai báo câu lệnh trong **@Query** và thêm **@Modifying**.
5. Đặt transaction ghi ở service boundary.
6. Xác định persistence context có entity bị ảnh hưởng hay không; chọn flush, clear hoặc refresh phù hợp.
7. Nếu có **@Version**, quyết định cách kiểm tra và tăng version thủ công.
8. Kiểm tra quan hệ, foreign key, callback, auditing và cache.
9. Trả về và ghi nhận số lượng bản ghi được tác động.
10. Kiểm thử với database mục tiêu, cả trường hợp không có bản ghi, dữ liệu lớn và lỗi transaction.

## 20. Ghi nhớ

- JPQL UPDATE/DELETE thực hiện bulk DML trực tiếp trên một tập entity.
- JPQL dùng entity name và property name, không dùng tên bảng/cột SQL.
- **@Modifying** cần cho modifying query được khai báo bằng **@Query**; derived delete và custom implementation không cần annotation này.
- Bulk DML cần transaction; khai báo transaction ghi ở service boundary là cách thường dùng.
- Method có thể trả về **int** để nhận số entity được cập nhật hoặc xóa.
- **flushAutomatically** flush persistence context trước câu lệnh; **clearAutomatically** clear persistence context sau câu lệnh. Cả hai mặc định là false.
- Persistence context không tự đồng bộ với bulk DML; entity đã managed có thể giữ trạng thái cũ.
- Bulk DELETE không cascade sang entity liên quan và không gọi lifecycle callback của từng entity.
- Bulk UPDATE/DELETE bỏ qua optimistic locking tự động; cần quản lý version tường minh nếu nghiệp vụ yêu cầu.
- Derived delete xóa từng entity và có thể gọi lifecycle callback; bulk delete gửi một câu lệnh trực tiếp tới database.
- Bulk DML thường giảm chi phí tải entity, nhưng cần xem index, transaction log, lock và số lượng bản ghi.
- Kiểm thử persistence context, transaction, số lượng affected và constraint trên database mục tiêu.

JPQL bulk UPDATE, DELETE và **@Modifying** là công cụ hiệu quả cho thao tác hàng loạt khi cùng một quy tắc áp dụng cho nhiều bản ghi. Hãy quản lý transaction rõ ràng, xử lý persistence context sau câu lệnh, và chỉ dùng bulk DML khi không cần hành vi lifecycle của từng entity.

## Tài liệu tham khảo

- [Spring Data JPA — JPA Query Methods: Modifying Queries and Derived Deletes](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA — Transactionality and Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Spring Data JPA — @Modifying API](https://docs.spring.io/spring-data/jpa/reference/4.0/api/java/org/springframework/data/jpa/repository/Modifying.html)
- [Jakarta Persistence 3.2 — Section 4.11: Bulk Update and Delete Operations](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html)