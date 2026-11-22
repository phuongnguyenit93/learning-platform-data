# Tên phương thức dành riêng và xung đột với thuộc tính tên id

Spring Data JPA cho phép tạo truy vấn từ tên phương thức repository. Tuy nhiên, một số tên phương thức đã được dành riêng cho các thao tác CRUD kế thừa từ Repository, CrudRepository hoặc JpaRepository. Những phương thức này luôn làm việc với khóa chính của entity, kể cả khi entity có một thuộc tính khác tên là id.

Điểm dễ nhầm xuất hiện khi entity dùng một thuộc tính như pk làm @Id, đồng thời có một thuộc tính persistent khác tên id, chẳng hạn mã người dùng từ hệ thống bên ngoài. Trong trường hợp đó, findById(...) vẫn tìm theo khóa chính. Muốn truy vấn thuộc tính id thông thường, hãy thêm một descriptive token trước By, ví dụ findAccountById(...), hoặc khai báo JPQL tường minh bằng @Query.

Bài học này giải thích cách Spring Data phân biệt phương thức CRUD dành riêng với derived query, cách đặt tên để tránh xung đột, cách dùng @Query, và cách kiểm thử để bảo đảm truy vấn đi đúng thuộc tính.

## 1. Derived query được tạo từ tên phương thức như thế nào?

Spring Data phân tích tên method của repository để suy ra điều kiện truy vấn. Ví dụ:

~~~java
List<Account> findByEmail(String email);
~~~

Spring hiểu method này là truy vấn entity Account có thuộc tính email bằng giá trị truyền vào.

Một tên derived query thường gồm:

- **Subject**: phần chỉ loại thao tác như find, read, get, query, search, stream, count, exists hoặc delete.
- **Descriptive token**: phần mô tả tùy chọn nằm sau subject và trước By; phần này giúp đặt tên dễ đọc nhưng không trở thành điều kiện lọc.
- **Predicate**: phần bắt đầu sau By, mô tả thuộc tính và điều kiện truy vấn.
- **Modifier**: các phần bổ sung như Distinct, Top, First hoặc OrderBy tùy cú pháp method.

Ví dụ:

~~~java
Optional<Account> findAccountByEmail(String email);
~~~

Có thể đọc thành:

- find: tìm entity.
- Account: descriptive token, chỉ giúp tên method dễ hiểu.
- ByEmail: điều kiện lọc theo thuộc tính email.

Descriptive token không yêu cầu entity phải có thuộc tính account. Điều kiện truy vấn bắt đầu sau By.

## 2. Phương thức CRUD dành riêng là gì?

Các repository của Spring Data kế thừa những method chuẩn. Một số method quan trọng gồm:

| Phương thức | Ý nghĩa |
|---|---|
| findById(ID id) | Tìm entity theo thuộc tính được ánh xạ bằng @Id |
| existsById(ID id) | Kiểm tra entity có khóa chính tương ứng hay không |
| deleteById(ID id) | Xóa entity theo khóa chính |
| findAllById(Iterable<ID> ids) | Tìm các entity theo danh sách khóa chính |
| deleteAllById(Iterable<? extends ID> ids) | Xóa các entity theo danh sách khóa chính |

Đây là các thao tác CRUD đã được định nghĩa trong repository base interface. Chúng không được diễn giải như một derived query thông thường chỉ vì tên có phần ById.

Đặc biệt, findById luôn nhận kiểu ID của repository và tìm theo thuộc tính @Id. Nếu primary key trong entity có tên pk, findById vẫn tìm pk. Tên của field khóa chính không làm thay đổi ý nghĩa method này.

Ví dụ repository:

~~~java
public interface AccountRepository
        extends JpaRepository<Account, Long> {
}
~~~

Kiểu ID của AccountRepository là Long. Vì vậy:

~~~java
repository.findById(42L);
~~~

có nghĩa là tìm Account có primary key bằng 42.

## 3. Tình huống gây xung đột: entity có cả pk và id

Giả sử hệ thống cần hai định danh:

- pk là khóa chính nội bộ do database cấp.
- id là mã tài khoản từ hệ thống bên ngoài, ví dụ EXT-1001.

Entity:

~~~java
package example.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "accounts")
public class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long pk;

    @Column(name = "external_id", nullable = false, unique = true)
    private String id;

    @Column(nullable = false)
    private String email;

    protected Account() {
    }

    public Account(String id, String email) {
        this.id = id;
        this.email = email;
    }

    public Long getPk() {
        return pk;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Trong entity này:

| Thuộc tính Java | Mapping | Vai trò |
|---|---|---|
| pk | @Id | Khóa chính của entity |
| id | @Column(name = "external_id") | Mã tài khoản bên ngoài |
| email | @Column | Email đăng nhập |

Tên cột database là external_id, nhưng tên thuộc tính Java vẫn là id. Derived query dùng tên thuộc tính Java trong entity, không dùng tên cột SQL.

Nếu repository kế thừa JpaRepository<Account, Long>, Spring Data đã cung cấp sẵn findById(Long id). Method này tìm theo pk vì pk là thuộc tính @Id.

## 4. Vì sao findById không truy vấn field id thông thường?

Giả sử bạn viết:

~~~java
Optional<Account> account = repository.findById(42L);
~~~

Spring Data xử lý đây là method CRUD dành riêng. Nó tìm Account có primary key pk = 42.

Nó không tự suy luận rằng bạn muốn tìm field String id chỉ vì entity có thuộc tính mang tên id. Method đã được dành riêng trong repository base API và ý nghĩa của nó được xác định bởi kiểu khóa chính của repository.

Nếu cố dùng findById với một tham số String để truy vấn thuộc tính id trong ví dụ trên, bạn sẽ gặp xung đột với chữ ký CRUD đã kế thừa và kiểu ID của repository. Không nên tạo một method cùng tên để thay đổi ý nghĩa của API chuẩn.

Đây là quy tắc quan trọng: **tên method CRUD dành riêng được ưu tiên theo hợp đồng của repository base interface và luôn trỏ đến khóa chính**.

## 5. Cách đúng: thêm descriptive token trước By

Để truy vấn thuộc tính id thông thường, đặt một descriptive token giữa subject và By.

Repository:

~~~java
package example.repository;

import example.domain.Account;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface AccountRepository
        extends JpaRepository<Account, Long> {

    Optional<Account> findAccountById(String id);
}
~~~

Method findAccountById được phân tích như sau:

- find: subject, yêu cầu tìm entity.
- Account: descriptive token, không phải điều kiện.
- By: bắt đầu phần predicate.
- Id: thuộc tính Java cần so sánh.

Vì vậy:

~~~java
repository.findById(42L);
~~~

tìm theo khóa chính pk.

Còn:

~~~java
repository.findAccountById("EXT-1001");
~~~

tìm theo thuộc tính id có giá trị EXT-1001.

Hai method có ý nghĩa khác nhau dù cả hai đều chứa chữ Id.

Tên descriptive token nên giúp người đọc hiểu domain, ví dụ Account, User, Customer hoặc Order. Token này không phải tên property bắt buộc phải tồn tại trong entity.

## 6. So sánh các cách đặt tên

Với entity Account ở trên:

| Method | Cách Spring Data hiểu | Thuộc tính được truy vấn |
|---|---|---|
| findById(Long id) | Method CRUD dành riêng | pk, tức @Id |
| existsById(Long id) | Method CRUD dành riêng | pk, tức @Id |
| deleteById(Long id) | Method CRUD dành riêng | pk, tức @Id |
| findAccountById(String id) | Derived query | id |
| findByEmail(String email) | Derived query | email |
| findAccountByEmail(String email) | Derived query | email |

Cách đọc tên method:

~~~text
findById
  |
  +-- Tên CRUD dành riêng
  +-- Tìm theo @Id

findAccountById
  |
  +-- find: subject
  +-- Account: descriptive token
  +-- ById: predicate
          |
          +-- Tìm theo thuộc tính id
~~~

Nếu thuộc tính id chính là khóa chính được đánh dấu @Id, findById vẫn đúng và không có xung đột về ý nghĩa. Vấn đề chỉ phát sinh khi id là thuộc tính persistent khác với thuộc tính khóa chính.

## 7. Dùng @Query khi muốn diễn đạt rõ ràng

Nếu tên method có thể gây nhầm lẫn hoặc truy vấn có điều kiện phức tạp, hãy dùng @Query để chỉ rõ thuộc tính cần truy vấn.

Ví dụ JPQL:

~~~java
package example.repository;

import example.domain.Account;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface AccountRepository
        extends JpaRepository<Account, Long> {

    Optional<Account> findAccountById(String id);

    @Query("""
        select a
        from Account a
        where a.id = :externalId
        """)
    Optional<Account> findByExternalId(
        @Param("externalId") String externalId
    );
}
~~~

JPQL dùng tên entity và thuộc tính Java:

- Account là entity.
- a.id là thuộc tính id trong Java.
- externalId là tên tham số truy vấn.
- :externalId liên kết tham số với giá trị truyền vào.

JPQL không dùng tên cột external_id trong biểu thức a.id. JPA provider tự ánh xạ thuộc tính id sang cột external_id theo @Column.

Với native SQL, bạn làm việc trực tiếp với bảng và cột database:

~~~java
@Query(
    value = """
        select *
        from accounts
        where external_id = :externalId
        """,
    nativeQuery = true
)
Optional<Account> findNativeByExternalId(
    @Param("externalId") String externalId
);
~~~

Dùng native query khi cần cú pháp hoặc tính năng riêng của database. Với truy vấn đơn giản theo một thuộc tính entity, derived query hoặc JPQL thường dễ bảo trì hơn.

## 8. Phân biệt tên thuộc tính Java và tên cột database

Một nguyên nhân gây lỗi khác là nhầm property name với column name.

~~~java
@Column(name = "external_id")
private String id;
~~~

Trong Java, thuộc tính tên id. Trong database, cột tên external_id.

Derived query phải dùng property name:

~~~java
Optional<Account> findAccountById(String id);
~~~

Không dùng tên cột SQL trong tên method:

~~~java
// Không phải derived query hợp lệ nếu entity không có property externalId:
Optional<Account> findByExternalId(String externalId);
~~~

Method findByExternalId chỉ hợp lệ theo cơ chế derived query nếu entity thực sự có thuộc tính externalId. Nếu muốn query cột external_id trong khi field Java tên id, hãy dùng findAccountById hoặc khai báo @Query.

Quy tắc này áp dụng cho mọi thuộc tính, không chỉ id. Ví dụ:

~~~java
@Column(name = "created_at")
private Instant createdAt;
~~~

Derived query dùng findByCreatedAt(...), không dùng findByCreated_at(...).

## 9. Khi nào descriptive token hữu ích?

Descriptive token hữu ích khi:

- Tên method xung đột với CRUD method dành riêng.
- Muốn method rõ nghĩa hơn trong repository có nhiều định danh.
- Có một thuộc tính tên id không phải primary key.
- Cần phân biệt truy vấn theo ID nội bộ với mã bên ngoài.

Ví dụ:

~~~java
Optional<Account> findAccountById(String externalId);

Optional<Account> findAccountByEmail(String email);

List<Account> findAccountByStatus(AccountStatus status);
~~~

Các token Account làm tên method dễ đọc hơn. Predicate vẫn bắt đầu sau By và phải khớp với persistent property của entity.

Không cần thêm descriptive token vào mọi method. findByEmail vẫn hoàn toàn hợp lệ nếu không có xung đột.

## 10. Các method CRUD khác cũng cần chú ý

Ngoài findById, repository base API còn có các method dùng khóa chính như existsById, deleteById và findAllById.

Ví dụ:

~~~java
repository.existsById(42L);
repository.deleteById(42L);
repository.findAllById(List.of(10L, 20L, 30L));
~~~

Các lệnh này thao tác theo khóa chính của Account, tức pk trong ví dụ.

Nếu nghiệp vụ cần kiểm tra hoặc xóa theo mã bên ngoài, hãy đặt tên riêng để thể hiện rõ thuộc tính:

~~~java
boolean existsAccountById(String externalId);

void deleteAccountById(String externalId);
~~~

Các method derived query dạng exists hoặc delete cần được kiểm tra theo phiên bản Spring Data JPA đang sử dụng và kiểu trả về được hỗ trợ. Với thao tác xóa có yêu cầu nghiệp vụ hoặc cần kiểm soát transaction, một service method tường minh thường dễ đọc hơn.

Ví dụ xóa theo mã ngoài bằng @Query:

~~~java
@Modifying
@Query("delete from Account a where a.id = :externalId")
int deleteByExternalId(
    @Param("externalId") String externalId
);
~~~

Phương thức này cần được gọi trong transaction phù hợp. Bulk delete tác động trực tiếp lên database và không đồng bộ từng entity đang được quản lý trong persistence context. Nếu cần tiếp tục dùng các entity liên quan trong cùng transaction, hãy cân nhắc clear persistence context hoặc dùng thao tác xóa entity thông thường.

## 11. Đường dẫn thuộc tính lồng nhau và dấu gạch dưới

Spring Data còn hỗ trợ truy vấn qua property path. Ví dụ entity có:

~~~java
class Account {
    private AccountProfile profile;
}

class AccountProfile {
    private String id;
}
~~~

Method:

~~~java
Optional<Account> findAccountByProfileId(String id);
~~~

có thể được phân tích thành đường dẫn profile.id. Nếu tên thuộc tính gây mơ hồ giữa một property trực tiếp và một đường dẫn lồng nhau, dấu gạch dưới có thể chỉ rõ ranh giới:

~~~java
Optional<Account> findAccountByProfile_Id(String id);
~~~

Dấu gạch dưới trong tên method là ký hiệu phân tách property path của Spring Data. Nó không có nghĩa là tên cột database chứa dấu gạch dưới.

Với entity phức tạp, dùng @Query có thể rõ ràng hơn nếu derived method trở nên quá dài hoặc khó đọc.

## 12. Kiểu tham số phải khớp với thuộc tính được truy vấn

Với AccountRepository extends JpaRepository<Account, Long>:

- findById nhận Long vì đây là kiểu khóa chính.
- findAccountById nhận String vì thuộc tính id trong entity là String.
- findByEmail nhận String nếu email là String.

Không chọn kiểu tham số theo tên method đơn thuần. Hãy xác định method là CRUD dành riêng hay derived query, sau đó kiểm tra kiểu của đúng thuộc tính.

Nếu kiểu tham số không tương thích, lỗi có thể xuất hiện khi biên dịch, khi Spring tạo repository query hoặc khi provider thực thi truy vấn, tùy chữ ký và cách cấu hình.

## 13. Kiểm thử để xác nhận hai loại ID không bị nhầm

Một repository test nên tạo một bản ghi có primary key do database cấp và external id do ứng dụng cung cấp, sau đó truy vấn bằng cả hai method.

Ví dụ với Spring Boot test slice:

~~~java
package example.repository;

import example.domain.Account;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@DataJpaTest
class AccountRepositoryTest {

    @Autowired
    private AccountRepository repository;

    @Test
    void distinguishesPrimaryKeyFromPropertyNamedId() {
        Account saved = repository.saveAndFlush(
            new Account("EXT-1001", "an@example.com")
        );

        Account byPrimaryKey = repository
            .findById(saved.getPk())
            .orElseThrow();

        Account byExternalId = repository
            .findAccountById("EXT-1001")
            .orElseThrow();

        assertEquals(saved.getPk(), byPrimaryKey.getPk());
        assertEquals(saved.getPk(), byExternalId.getPk());
    }
}
~~~

Đây là test tích hợp minh họa cho dự án dùng Spring Boot test. Nếu ứng dụng không dùng Boot, có thể khởi tạo Spring test context và JPA provider theo cấu hình hiện tại; logic cần kiểm tra vẫn giống nhau.

Test chứng minh:

- findById dùng khóa chính.
- findAccountById dùng thuộc tính id.
- Cả hai truy vấn có thể trả về cùng một hàng bằng hai định danh khác nhau.

Nên bổ sung test cho trường hợp không tìm thấy ID, external id trùng và unique constraint của cột external_id.

## 14. Lỗi thường gặp và cách khắc phục

**1. findById truy vấn sai cột**

Kiểm tra thuộc tính nào mang @Id. Method CRUD findById luôn tìm theo thuộc tính đó. Nếu cần field id khác, dùng findAccountById hoặc @Query.

**2. Không tạo được derived query**

Kiểm tra tên property sau By có tồn tại trong entity và đúng chữ hoa/thường không. Derived query dùng tên thuộc tính Java, không dùng tên cột SQL.

**3. Dùng sai kiểu tham số**

Kiểm tra kiểu ID của JpaRepository và kiểu của property cần truy vấn. Trong ví dụ, findById nhận Long còn findAccountById nhận String.

**4. Cố overload findById để thay đổi ý nghĩa**

Không nên dùng cùng tên CRUD dành riêng với kiểu tham số khác để biểu đạt property thường. Chọn descriptive token để tên method không đụng chữ ký CRUD.

**5. Nhầm descriptive token là property**

Trong findAccountById, Account là phần mô tả subject. Spring không yêu cầu entity có property account. Điều kiện lọc là property id sau By.

**6. Dùng tên cột thay cho tên field**

Nếu field Java là id và @Column đặt tên external_id, derived query vẫn phải dùng ById. Chỉ native SQL dùng external_id.

**7. Dùng native SQL nhưng viết tên property Java**

Native SQL phải dùng tên bảng và cột thật trong database. JPQL mới dùng tên entity và thuộc tính Java.

**8. Không kiểm thử khi entity có nhiều định danh**

Hãy tạo dữ liệu có primary key khác external id và kiểm tra từng repository method. Một test chỉ kiểm tra findById với giá trị trùng nhau có thể không phát hiện nhầm lẫn.

## 15. Quy trình đặt tên method an toàn

Khi thêm repository method liên quan đến ID:

1. Xác định field hoặc property được đánh dấu @Id.
2. Xác định kiểu ID thứ hai nếu entity có mã nghiệp vụ hoặc mã từ hệ thống ngoài.
3. Kiểm tra method có trùng tên CRUD dành riêng được kế thừa hay không.
4. Nếu cần truy vấn property tên id không phải khóa chính, thêm descriptive token trước By, ví dụ findAccountById.
5. Dùng đúng kiểu tham số theo property được truy vấn.
6. Dùng tên property Java, không dùng tên cột SQL, với derived query và JPQL.
7. Dùng @Query nếu muốn chỉ rõ điều kiện hoặc tránh một tên method khó hiểu.
8. Viết repository test phân biệt truy vấn theo primary key và truy vấn theo mã nghiệp vụ.

## 16. Checklist tự đánh giá

- [ ] Tôi giải thích được derived query được phân tích từ tên method.
- [ ] Tôi biết descriptive token nằm giữa subject và By.
- [ ] Tôi hiểu findById là method CRUD dành riêng và luôn truy vấn theo @Id.
- [ ] Tôi biết existsById, deleteById và findAllById cũng thao tác theo khóa chính.
- [ ] Tôi nhận ra xung đột khi entity có @Id pk và property thường tên id.
- [ ] Tôi biết dùng findAccountById để truy vấn property id thông thường.
- [ ] Tôi phân biệt tên property Java với tên cột database.
- [ ] Tôi biết dùng JPQL @Query khi cần chỉ rõ property.
- [ ] Tôi phân biệt JPQL với native SQL.
- [ ] Tôi chọn kiểu tham số theo đúng thuộc tính được truy vấn.
- [ ] Tôi có test phân biệt primary key và mã định danh bên ngoài.

## 17. Câu hỏi ôn tập

**1. findById trong JpaRepository tìm theo field nào?**

Nó tìm theo thuộc tính được ánh xạ bằng @Id, bất kể thuộc tính đó tên là id, pk hay userKey.

**2. Entity có @Id pk và một field String id. Muốn tìm theo String id thì viết gì?**

Dùng một derived method có descriptive token, ví dụ findAccountById(String id), hoặc một method @Query rõ điều kiện a.id = :id.

**3. Từ Account trong findAccountById có phải là property của entity không?**

Không. Account là descriptive token của phần subject. Predicate bắt đầu sau By và truy vấn property id.

**4. @Column(name = "external_id") có làm method phải viết findByExternalId không?**

Không. Derived query dùng tên property Java. Nếu field tên id, method truy vấn field đó có thể là findAccountById.

**5. Vì sao không nên overload findById để tìm mã bên ngoài?**

Vì findById là method CRUD dành riêng, gắn với kiểu ID của repository. Dùng descriptive token giúp tránh nhầm lẫn về hợp đồng và kiểu tham số.

**6. Khi nào nên dùng @Query thay vì derived query?**

Khi điều kiện phức tạp, tên method dài hoặc cần thể hiện rõ thuộc tính được truy vấn. JPQL dùng entity/property; native SQL dùng bảng/cột database.

Khi phân biệt rõ method CRUD dành riêng với derived query, bạn có thể dùng entity có cả khóa chính nội bộ và thuộc tính id nghiệp vụ mà không nhầm lẫn truy vấn.