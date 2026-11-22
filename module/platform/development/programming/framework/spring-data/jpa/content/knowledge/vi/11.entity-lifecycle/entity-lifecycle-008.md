# Vì sao merge trả về một đối tượng managed khác

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích chính xác `EntityManager.merge()` làm gì với entity new, managed, detached và removed.
- Hiểu vì sao đối tượng truyền vào `merge()` không tự trở thành managed khi nó đang detached.
- Phân biệt `persist()` với `merge()` và biết khi nào dùng từng thao tác.
- Sử dụng đúng giá trị trả về từ `EntityManager.merge()` và `JpaRepository.save()`.
- Nhận diện rủi ro ghi đè dữ liệu bằng trạng thái detached cũ hoặc object được dựng từ DTO thiếu field.
- Dùng `@Version`, transaction và integration test để kiểm soát cập nhật đồng thời.

## 1. Vòng đời Entity trong JPA

JPA quản lý entity theo các trạng thái. Trạng thái cho biết entity có đang được một persistence context theo dõi hay không.

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| New / Transient | Đối tượng Java mới, chưa được persistence context quản lý và chưa có bản ghi được quản lý tương ứng | `new Customer("An")` |
| Managed / Persistent | Entity đang được persistence context quản lý; thay đổi được theo dõi bằng dirty checking | Kết quả của `find()` trong transaction |
| Detached | Entity có identity trong database nhưng không còn được persistence context hiện tại quản lý | Entity sau `detach()`, `clear()` hoặc khi context đóng |
| Removed | Entity đang được đánh dấu xóa trong persistence context | Entity sau `remove()` |

Một persistence context giữ một managed instance cho mỗi persistent identity trong phạm vi context. Ví dụ, nếu bản ghi Customer có ID 10 đã được nạp vào context, các thao tác tiếp theo trong cùng context sẽ làm việc với managed instance đại diện cho Customer 10.

Điều này giúp Hibernate/JPA theo dõi một trạng thái nhất quán: thay đổi nào cần ghi, entity nào cần xóa và quan hệ nào cần đồng bộ khi flush.

## 2. merge() thực sự làm gì?

`EntityManager.merge(entity)` sao chép trạng thái của đối tượng đầu vào sang một đối tượng managed có cùng persistent identity và trả về đối tượng managed đó.

Điểm quan trọng: nếu đầu vào đang detached, JPA không biến chính object detached đó thành managed. Nó đưa trạng thái của object vào persistence context thông qua một managed instance.

Có thể tóm tắt theo trạng thái đầu vào:

| Trạng thái đầu vào | Hành vi merge | Đối tượng trả về |
|---|---|---|
| New / Transient | Tạo một managed instance mới và sao chép trạng thái đầu vào sang đó | Managed instance mới |
| Detached | Tìm managed instance cùng identity trong context hoặc tạo managed instance mới, sau đó sao chép trạng thái | Managed instance đại diện cho identity đó |
| Managed | Bản thân entity đã được quản lý; merge không cần tạo bản sao mới, nhưng thao tác merge vẫn có thể cascade | Chính managed instance đó |
| Removed | Không được merge; thao tác có thể ném IllegalArgumentException hoặc lỗi được phát hiện khi commit | Không có kết quả hợp lệ |

Với entity detached, đối tượng truyền vào và đối tượng trả về có thể là hai Java object khác nhau:

~~~java
Customer detached = ...;

Customer managed = entityManager.merge(detached);

// detached vẫn detached
// managed được persistence context theo dõi
~~~

Cả hai có thể mang cùng ID và cùng dữ liệu sau khi merge, nhưng chỉ `managed` được theo dõi bởi persistence context hiện tại.

### Vì sao cần một managed instance khác?

Một entity detached đã rời persistence context cũ. Nó có thể đã được giữ trong session của người dùng, cache ứng dụng hoặc gửi qua một request. Trong lúc đó, database có thể đã thay đổi và một persistence context mới có thể đang quản lý một instance khác của cùng bản ghi.

JPA cần một instance được persistence context hiện tại quản lý để thực hiện dirty checking, đồng bộ quan hệ và ghi thay đổi khi flush. Vì vậy, merge sao chép trạng thái từ object bên ngoài vào managed instance đại diện cho identity đó.

Cách này cũng tránh việc có hai object Java cùng đại diện cho một persistent identity nhưng chỉ một object được context theo dõi. Managed instance là đối tượng mà ứng dụng cần tiếp tục sử dụng trong transaction.

## 3. Ví dụ minh họa: object đầu vào và object trả về

Giả sử có entity Customer:

~~~java
package com.example.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false, length = 120)
    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getName() {
        return name;
    }

    public void rename(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        this.name = name;
    }
}
~~~

Trong transaction, có thể tạo và persist entity:

~~~java
Customer original = new Customer("Lan");
entityManager.persist(original);
entityManager.flush();

Long id = original.getId();
~~~

Sau đó tách entity khỏi persistence context:

~~~java
entityManager.detach(original);

boolean detachedIsManaged = entityManager.contains(original);
// false
~~~

Gọi merge:

~~~java
Customer managed = entityManager.merge(original);

boolean originalIsManaged = entityManager.contains(original);
// false

boolean returnedIsManaged = entityManager.contains(managed);
// true

boolean sameReference = original == managed;
// false khi đầu vào detached được sao chép sang managed instance
~~~

Hai object có cùng identity:

~~~java
System.out.println(original.getId().equals(managed.getId()));
// true
~~~

Nhưng chỉ object trả về được quản lý:

- Thay đổi `managed.rename("Lan Nguyen")` sẽ được dirty checking theo dõi.
- Thay đổi `original.rename("Lan Tran")` sau merge không tự động được ghi xuống database.
- Gọi `entityManager.contains(original)` vẫn trả về false.
- Gọi `entityManager.contains(managed)` trả về true.

Đây là lý do phải luôn sử dụng giá trị trả về của merge.

## 4. persist() và merge() khác nhau thế nào?

Hai thao tác này có mục đích khác nhau.

| Tiêu chí | persist(entity) | merge(entity) |
|---|---|---|
| Mục đích | Đưa entity mới vào trạng thái managed | Sao chép trạng thái của entity vào managed instance |
| Đối tượng đầu vào | Thường là new/transient | Có thể là new hoặc detached; managed cũng được chấp nhận |
| Giá trị trả về | void | Managed instance |
| Object đầu vào | Chính object đó trở thành managed | Nếu đầu vào detached/new, object đầu vào không trở thành managed |
| ID đã tồn tại | Có thể dẫn đến lỗi identity/duplicate tùy trạng thái và thời điểm | Dùng identity để tìm hoặc tạo managed instance tương ứng |
| Ghi SQL | Thường khi flush, tùy generator và provider | Merge không đồng nghĩa SQL UPDATE ngay lập tức; flush mới đồng bộ thay đổi |

Ví dụ với entity mới:

~~~java
Customer customer = new Customer("Mai");

entityManager.persist(customer);

// customer chính là managed instance
assert entityManager.contains(customer);
~~~

Ví dụ với entity detached:

~~~java
Customer detached = loadInPreviousTransaction();

Customer managed = entityManager.merge(detached);

// Phải tiếp tục làm việc với managed
managed.rename("Mai Nguyen");
~~~

Không dùng `persist()` như cách cập nhật entity detached. Theo JPA, persist dành cho entity mới; truyền detached entity vào persist có thể dẫn đến EntityExistsException hoặc lỗi được phát hiện khi flush/commit.

Ngược lại, không cần gọi merge cho entity đang managed. Mọi thay đổi trên managed entity trong transaction đã được dirty checking theo dõi.

## 5. merge không phải là UPDATE ngay lập tức

Một hiểu lầm thường gặp là gọi merge thì Hibernate lập tức chạy câu SQL UPDATE.

Thực tế:

1. Merge xác định managed instance tương ứng.
2. Trạng thái đầu vào được sao chép vào managed instance.
3. Persistence context ghi nhận trạng thái cần đồng bộ.
4. Khi flush, provider so sánh trạng thái và phát sinh SQL cần thiết.
5. Transaction commit mới làm thay đổi trở nên bền vững trong database.

Flush có thể xảy ra trước commit, ví dụ khi gọi `flush()` hoặc trước một query theo FlushMode phù hợp. SQL đã gửi trong transaction vẫn có thể bị rollback nếu transaction thất bại.

Vì vậy, nếu muốn kiểm tra dữ liệu sau merge, cần xét cả persistence context và database transaction. Một query trong cùng context có thể trả kết quả từ managed instance hoặc được đồng bộ trước query tùy flush mode.

## 6. Spring Data JPA save() cũng có thể trả về object khác

Trong Spring Data JPA, `JpaRepository.save(entity)` quyết định dùng persist hay merge dựa trên việc entity có được nhận diện là mới hay không.

Về hành vi phổ biến của `SimpleJpaRepository`:

- Nếu entity được xem là new, repository gọi `EntityManager.persist(entity)` và trả về chính entity đầu vào.
- Nếu entity không được xem là new, repository gọi `EntityManager.merge(entity)` và trả về managed instance từ merge.

Do đó, code nên capture kết quả:

~~~java
Customer saved = customerRepository.save(customer);
~~~

Không nên bỏ qua giá trị trả về:

~~~java
customerRepository.save(customer);

// Không nên tiếp tục giả định customer đã trở thành managed
// nếu save đã đi theo nhánh merge.
~~~

Nếu cần flush ngay:

~~~java
Customer saved = customerRepository.saveAndFlush(customer);
~~~

`saveAndFlush()` vẫn không thay đổi semantics của merge: nếu entity đi theo nhánh merge, hãy dùng object được trả về. Flush chỉ yêu cầu đồng bộ thay đổi pending xuống database trong transaction hiện tại.

### Spring Data xác định entity mới thế nào?

Cơ chế mặc định thường kiểm tra:

1. Nếu có thuộc tính `@Version` không phải primitive, version null thường được xem là entity mới.
2. Nếu không có version phù hợp, ID null thường được xem là entity mới.
3. Nếu ID đã được gán trước và không có version để nhận diện newness, Spring Data có thể xem entity là existing và gọi merge.

Điều này đặc biệt quan trọng với UUID được ứng dụng tự gán trước khi save. Nếu ID đã khác null, không mặc định cho rằng Spring Data sẽ gọi persist.

Có thể giải quyết bằng nullable `@Version` hoặc implement `Persistable<ID>` với `isNew()` phù hợp. Khi dùng `Persistable`, cần kiểm thử state detection qua persist, load, detach và callback để tránh báo entity mới sai.

## 7. Merge và trạng thái cũ (stale state)

Merge sao chép trạng thái của entity detached vào managed instance. Nếu object detached được tạo từ dữ liệu cũ, nó có thể ghi đè những thay đổi mới hơn trong database.

Ví dụ:

1. Transaction A đọc Customer có tên “Lan”, version 4.
2. Transaction B đọc cùng Customer và đổi tên thành “Lan Nguyen”, commit version 5.
3. Transaction A vẫn giữ object detached cũ với tên “Lan”.
4. Transaction A merge object cũ.

Nếu không có cơ chế concurrency phù hợp, trạng thái cũ có thể ghi đè giá trị mới. Đây là lost update.

### Dùng @Version để phát hiện cập nhật đồng thời

Entity Customer ở ví dụ trên có:

~~~java
@Version
private Long version;
~~~

JPA provider sử dụng version để phát hiện xung đột cập nhật. Nếu object detached có version cũ, thao tác merge/flush/commit có thể phát sinh OptimisticLockException hoặc lỗi optimistic locking tương ứng.

Ứng dụng nên bắt lỗi ở ranh giới transaction và yêu cầu người dùng tải lại hoặc hợp nhất thay đổi theo quy tắc nghiệp vụ. Không tự động retry mù quáng nếu thao tác không idempotent hoặc có side effect.

`@Version` không phải khóa bi quan. Nó phát hiện xung đột khi ghi; không giữ row lock liên tục trong suốt thời gian người dùng chỉnh sửa.

## 8. Rủi ro khi merge entity dựng từ DTO

Một anti-pattern là nhận DTO từ API, tạo một entity mới chỉ với ID và một vài field được gửi lên, rồi merge:

~~~java
Customer partial = new Customer("New name");
partial.setId(id); // giả sử có setter hoặc mapper
entityManager.merge(partial);
~~~

Entity detached/partial có thể chứa giá trị null hoặc mặc định cho các field mà request không gửi. Merge có thể sao chép những giá trị đó lên managed instance và làm mất dữ liệu đang có.

Ví dụ database có:

~~~text
id = 10
name = "Lan"
email = "lan@example.com"
status = "ACTIVE"
~~~

Request chỉ muốn đổi name, nhưng mapper tạo object:

~~~text
id = 10
name = "Lan Nguyen"
email = null
status = null
~~~

Nếu merge object này, email và status có nguy cơ bị ghi đè thành null hoặc giá trị mặc định. Các thuộc tính lazy chưa được fetch có quy tắc riêng trong JPA, nhưng không nên dựa vào đó để biến partial entity thành một patch API an toàn.

### Cách cập nhật an toàn

Thay vì merge một entity dựng từ DTO, hãy tải managed entity trong transaction và áp dụng đúng field được phép thay đổi:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Customer rename(Long id, String newName) {
        Customer managed = repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException(
                    "Customer not found: " + id
                ));

        managed.rename(newName);

        // Dirty checking sẽ lưu thay đổi khi transaction commit.
        return managed;
    }
}
~~~

Cách này có các lợi ích:

- Chỉ field được nghiệp vụ cho phép mới bị thay đổi.
- Những field không có trong request được giữ nguyên.
- Có thể kiểm tra trạng thái và quyền trước khi thay đổi.
- Quan hệ và collection được sửa trên managed aggregate.
- `@Version` vẫn tham gia phát hiện xung đột.

Nếu thật sự cần merge một object detached đầy đủ, hãy xác định rõ ai tạo object, mọi field có đầy đủ không, version có còn mới không và cascade được cấu hình ra sao.

## 9. CascadeType.MERGE và quan hệ entity

Merge có thể cascade sang các entity liên quan khi mapping khai báo `CascadeType.MERGE` hoặc `CascadeType.ALL`.

Ví dụ:

~~~java
@OneToMany(
    mappedBy = "customer",
    cascade = {CascadeType.PERSIST, CascadeType.MERGE}
)
private List<Address> addresses = new ArrayList<>();
~~~

Khi merge Customer, trạng thái của các Address liên quan có thể được merge theo cascade. Nếu không có cascade MERGE, không nên giả định toàn bộ trạng thái object con detached sẽ được sao chép.

Hãy chọn cascade theo vòng đời aggregate:

- PERSIST khi tạo parent cần tạo child cùng lúc.
- MERGE khi thao tác merge parent cần lan truyền trạng thái sang child.
- REMOVE khi xóa parent thực sự phải xóa child.
- orphanRemoval khi child không còn thuộc parent thì phải bị xóa.

Không dùng `CascadeType.ALL` chỉ để tránh phải hiểu từng thao tác. Nếu entity con được chia sẻ hoặc có vòng đời độc lập, cascade REMOVE/orphanRemoval có thể xóa dữ liệu ngoài ý muốn.

Khi merge một graph có quan hệ hai chiều, bảo đảm owning side và inverse side được đồng bộ trong bộ nhớ. Merge không thay thế helper method bảo vệ invariant của domain.

## 10. Lazy loading và thuộc tính chưa được tải

Entity detached có thể chứa association hoặc field lazy chưa được tải. JPA có quy tắc bảo vệ trạng thái lazy chưa fetch: provider không được xem một thuộc tính lazy chưa được fetch là giá trị null cần sao chép như field bình thường.

Tuy nhiên, ứng dụng không nên dùng detached entity như một bản vá dữ liệu. Cần phân biệt:

- Field đã được fetch và có giá trị null: null có thể là trạng thái thực cần merge.
- Field lazy chưa được fetch: provider có thể biết đây là thuộc tính chưa tải và không merge nó.
- Field bị mapper gán null vì DTO thiếu dữ liệu: provider không biết null đó là “không gửi” hay “xóa giá trị”.

Do đó, DTO patch nên có semantics riêng (ví dụ field presence hoặc JSON Merge Patch) và service phải áp dụng thay đổi có chủ đích lên managed entity.

## 11. Ví dụ kiểm thử merge trả về managed instance

Ví dụ test dưới đây giả định entity Customer có `@Id`, `@Version`, constructor và phương thức `rename()` như phần trước.

~~~java
package com.example.customer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class MergeLifecycleTest {

    @Autowired
    EntityManager entityManager;

    @Test
    void mergeDetachedReturnsManagedCopy() {
        Customer original = new Customer("Lan");
        entityManager.persist(original);
        entityManager.flush();

        Long id = original.getId();

        entityManager.detach(original);

        assertFalse(entityManager.contains(original));

        original.rename("Lan Nguyen");

        Customer merged = entityManager.merge(original);

        assertNotSame(original, merged);
        assertEquals(id, merged.getId());
        assertTrue(entityManager.contains(merged));
        assertFalse(entityManager.contains(original));

        merged.rename("Lan Tran");

        entityManager.flush();
        entityManager.clear();

        Customer reloaded = entityManager.find(Customer.class, id);
        assertEquals("Lan Tran", reloaded.getName());
    }

    @Test
    void mergeManagedReturnsSameInstance() {
        Customer managed = new Customer("Mai");
        entityManager.persist(managed);
        entityManager.flush();

        Customer result = entityManager.merge(managed);

        assertSame(managed, result);
        assertTrue(entityManager.contains(result));
    }
}
~~~

Test đầu tiên chứng minh:

1. Entity được persist và có ID.
2. detach() đưa object ra khỏi persistence context.
3. merge() trả về một managed instance khác.
4. Chỉ object trả về được context theo dõi.
5. Thay đổi object trả về được flush.
6. Sau clear(), nạp lại từ database nhận được giá trị đã commit trong transaction test.

Test thứ hai chứng minh nếu đầu vào vốn đã managed thì merge trả về chính instance đó.

`@DataJpaTest` thường chạy trong transaction test và rollback sau test. Ví dụ không phải ứng dụng độc lập; nó cần Spring Boot test, JPA provider, entity và cấu hình database phù hợp.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Gọi merge nhưng object đầu vào không được cập nhật | Đầu vào detached; merge trả về managed copy | Gán và sử dụng object trả về |
| Gọi save nhưng tiếp tục dùng entity cũ | save đã đi theo nhánh merge | Luôn capture kết quả của save/saveAndFlush |
| Field bị xóa sau merge | Detached entity hoặc DTO có null/default state | Load managed entity rồi áp dụng field có chủ đích |
| Lost update | Merge trạng thái cũ mà không kiểm soát concurrency | Dùng @Version và xử lý OptimisticLockException |
| Entity mới có UUID bị merge thay vì persist | Spring Data nhận diện ID khác null là existing | Dùng nullable @Version hoặc Persistable.isNew() |
| Cascade merge không cập nhật child như mong đợi | Quan hệ thiếu CascadeType.MERGE hoặc graph không đồng bộ | Xác định cascade và owning side rõ ràng |
| Merge entity removed gây lỗi | Entity đã bị đánh dấu xóa | Không tái sử dụng entity removed; tạo entity mới nếu nghiệp vụ yêu cầu |
| Thay đổi detached entity nhưng database không đổi | Detached object không được dirty checking theo dõi | Merge và dùng managed copy, hoặc load entity trong transaction |
| Gọi merge cho entity managed mà mong có bản sao | Entity đã nằm trong context | Dùng trực tiếp managed instance; không cần merge |

## Checklist trước khi merge

- [ ] Đã xác định trạng thái entity đầu vào.
- [ ] Nếu đầu vào detached/new, code sử dụng object trả về từ merge.
- [ ] Không giả định merge phát SQL UPDATE ngay lập tức.
- [ ] Không merge partial entity được dựng từ DTO thiếu field.
- [ ] Có @Version khi cần phát hiện cập nhật đồng thời.
- [ ] Cascade MERGE chỉ được bật theo vòng đời aggregate.
- [ ] Owning side và inverse side của quan hệ được đồng bộ.
- [ ] Spring Data save() luôn được capture kết quả.
- [ ] Integration test xác nhận contains(), object identity và dữ liệu sau flush/clear.
- [ ] Các thao tác update diễn ra trong transaction có ranh giới rõ ràng.

## Kết luận

`merge()` không “gắn lại” object detached vào persistence context. Nó sao chép trạng thái của object đầu vào sang managed instance có cùng identity và trả về instance đó. Vì vậy, với detached entity, hãy tiếp tục làm việc với giá trị trả về; object đầu vào vẫn detached. Spring Data `save()` cũng có thể trả về managed copy khi đi theo nhánh merge. Tránh merge object dựng từ DTO thiếu field, dùng `@Version` để phát hiện lost update và ưu tiên nạp managed entity trong transaction rồi áp dụng thay đổi nghiệp vụ có chủ đích.
