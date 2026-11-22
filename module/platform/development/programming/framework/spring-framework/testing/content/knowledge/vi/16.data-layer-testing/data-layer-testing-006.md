# Clear persistence context trước khi kiểm tra việc tải lại

Trong JPA, một entity đã được quản lý thường được giữ trong persistence context (ngữ cảnh lưu trữ). Khi test gọi repository để tìm lại entity bằng cùng ID, JPA có thể trả về chính object đang được quản lý thay vì đọc lại dữ liệu từ database. Điều này làm một số test cho kết quả đúng dù chúng chưa thực sự kiểm tra quá trình tải lại.

Để kiểm tra việc tải lại một cách rõ ràng, hãy đồng bộ các thay đổi cần giữ xuống database bằng `flush()`, sau đó gọi `clear()` để detach toàn bộ entity khỏi persistence context. Khi test tìm entity lại, JPA phải đưa một instance vào context từ nguồn lưu trữ theo cơ chế cache và transaction hiện tại. Cách làm này giúp phân biệt trạng thái object trong bộ nhớ với trạng thái đã được đồng bộ xuống database.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích persistence context và first-level cache của JPA.
- Hiểu vì sao tìm entity theo cùng ID có thể trả về chính instance đang được quản lý.
- Phân biệt `flush()`, `clear()`, `detach()` và `refresh()`.
- Dùng `EntityManager.clear()` trước khi kiểm tra việc tải lại entity.
- Viết integration test chứng minh dữ liệu được đọc lại sau khi persistence context được làm sạch.
- Tránh mất thay đổi chưa flush khi gọi `clear()`.
- Hiểu vì sao `clear()` không commit hoặc mở transaction mới.
- Nhận biết ảnh hưởng của second-level cache, transaction isolation và lazy loading.
- Chọn đúng công cụ giữa `EntityManager`, Spring Data repository và Spring Boot `TestEntityManager`.

## 1. Persistence context là gì?

Persistence context là vùng theo dõi các entity đang được quản lý bởi một `EntityManager`. Với mỗi entity có định danh, persistence context duy trì một instance đại diện trong phạm vi context đó. Đây là cơ sở của identity guarantee trong JPA: trong cùng persistence context, việc tìm cùng một entity identity thường trả về cùng một Java object.

Ví dụ:

~~~java
AppUser first = entityManager.find(AppUser.class, 10L);
AppUser second = entityManager.find(AppUser.class, 10L);

assertSame(first, second);
~~~

Nếu entity có ID là `10` đã được quản lý, lần tìm tiếp theo có thể trả ngay object đó từ persistence context. JPA không cần tạo một instance khác chỉ vì test gọi `find()` lần nữa.

Persistence context còn theo dõi thay đổi của entity. Khi code sửa một field của entity đang managed, provider có thể phát hiện thay đổi bằng dirty checking và đồng bộ xuống database khi flush.

Có thể hình dung:

~~~mermaid
flowchart TD
    A["EntityManager.find(AppUser, 10)"] --> B{"Entity 10 đã managed?"}
    B -->|Có| C["Trả instance hiện có từ persistence context"]
    B -->|Không| D["Tải dữ liệu và tạo managed instance"]
    D --> E["Đưa instance vào persistence context"]
    E --> F["Trả entity cho caller"]
~~~

Trong Spring Data JPA, repository thường dùng EntityManager phía sau. Vì vậy, gọi `repository.findById(id)` không đồng nghĩa chắc chắn database sẽ được truy vấn mỗi lần. Nếu entity đã có trong persistence context, JPA có thể trả instance đang quản lý.

## 2. Vì sao test cần clear trước khi kiểm tra reload?

Giả sử test lưu một user, thay đổi tên trong object rồi gọi repository tìm lại theo ID:

~~~java
AppUser user = repository.save(new AppUser("Alice"));
Long id = user.getId();

user.rename("Alicia");

AppUser loaded = repository.findById(id).orElseThrow();
~~~

Nếu `user` vẫn đang managed trong persistence context, `loaded` có thể chính là `user`. Assertion sau có thể pass:

~~~java
assertEquals("Alicia", loaded.getDisplayName());
~~~

Nhưng assertion này chỉ chứng minh object trong bộ nhớ đang có tên Alicia. Nó chưa chứng minh database đã lưu giá trị đó hoặc JPA có thể tải lại giá trị đó sau khi object cũ không còn được quản lý.

Đây là nguồn gây false positive trong test persistence. Test vô tình xác nhận trạng thái của first-level cache thay vì xác nhận dữ liệu đã được đồng bộ và có thể được nạp lại.

Sau khi gọi `flush()` và `clear()`, persistence context không còn giữ entity cũ. Khi tìm lại, JPA phải nạp một managed instance vào context. Test có thể kiểm tra cả identity và dữ liệu:

~~~java
entityManager.flush();
entityManager.clear();

AppUser reloaded = repository.findById(id).orElseThrow();

assertNotSame(user, reloaded);
assertEquals("Alice", reloaded.getDisplayName());
~~~

Giá trị được đọc lại phụ thuộc vào những gì đã được flush trước khi clear. Nếu chỉ flush lần insert đầu tiên rồi sửa object nhưng không flush lần sửa đó, database vẫn lưu tên Alice. Sau clear, lần tìm lại sẽ cho thấy Alice, không phải thay đổi chưa được đồng bộ trong bộ nhớ.

## 3. Phân biệt flush, clear, detach và refresh

Bốn thao tác này có mục đích khác nhau:

| Thao tác | Tác dụng | Có kết thúc transaction không? |
|---|---|---|
| `flush()` | Đồng bộ thay đổi pending trong persistence context xuống database | Không |
| `clear()` | Detach tất cả entity đang managed khỏi persistence context | Không |
| `detach(entity)` | Detach một entity cụ thể | Không |
| `refresh(entity)` | Đọc lại trạng thái database vào một entity đang managed | Không |

### flush(): đồng bộ thay đổi

~~~java
entityManager.flush();
~~~

`flush()` yêu cầu JPA provider đồng bộ các thay đổi đang chờ trong persistence context với database. Nó có thể phát sinh câu lệnh INSERT, UPDATE hoặc DELETE.

Flush không commit transaction. Transaction vẫn đang hoạt động, và những thay đổi đã gửi xuống database vẫn có thể bị rollback khi transaction kết thúc.

### clear(): làm sạch toàn bộ persistence context

~~~java
entityManager.clear();
~~~

`clear()` detach tất cả entity đang managed. Sau lời gọi này, các object Java mà test đang giữ vẫn tồn tại, nhưng chúng không còn được EntityManager theo dõi.

Các thay đổi chưa flush có thể bị bỏ lại cùng persistence context. Vì vậy, khi muốn giữ dữ liệu trước khi làm sạch context, hãy flush trước.

### detach(): detach một entity

~~~java
entityManager.detach(user);
~~~

`detach(user)` chỉ loại một entity khỏi persistence context. Các entity khác và relationship của chúng vẫn có thể được quản lý. Dùng thao tác này khi test chỉ cần tách một object cụ thể.

### refresh(): nạp lại trạng thái của một entity đang managed

~~~java
entityManager.refresh(user);
~~~

`refresh(user)` ghi đè trạng thái trong bộ nhớ của entity đang managed bằng trạng thái đọc từ database. Entity vẫn được quản lý sau refresh.

Khác với clear, refresh cần một entity đang managed và chỉ làm mới entity được chỉ định. Không thể dùng refresh trên entity đã detached; trước hết cần tìm hoặc merge entity vào context phù hợp.

## 4. Trình tự đúng: flush rồi clear rồi find

Khi mục tiêu là kiểm tra tải lại entity sau khi persistence context không còn giữ instance cũ, trình tự thông thường là:

1. Tạo hoặc cập nhật entity.
2. Gọi `flush()` để đồng bộ thay đổi cần kiểm tra xuống database.
3. Lưu lại ID cần dùng để truy vấn.
4. Gọi `clear()` để detach toàn bộ entity.
5. Dùng repository hoặc EntityManager tìm entity theo ID.
6. Kiểm tra instance mới và các giá trị được tải lại.

~~~mermaid
flowchart TD
    A["Tạo hoặc cập nhật entity"] --> B["EntityManager.flush()"]
    B --> C["SQL được đồng bộ trong transaction"]
    C --> D["EntityManager.clear()"]
    D --> E["Entity cũ trở thành detached"]
    E --> F["findById(id)"]
    F --> G["JPA nạp managed instance vào context"]
    G --> H["Assert identity và dữ liệu"]
~~~

Không đảo thứ tự thành clear rồi mới flush. Sau khi clear, entity cũ đã detached; những thay đổi chưa được flush của nó không còn được persistence context theo dõi để đồng bộ như trước.

Một ví dụ ngắn:

~~~java
AppUser user = repository.save(new AppUser("Alice"));

entityManager.flush();
Long id = user.getId();

entityManager.clear();

AppUser reloaded = repository.findById(id).orElseThrow();

assertNotSame(user, reloaded);
assertEquals("Alice", reloaded.getDisplayName());
~~~

Trong ví dụ này, insert được flush trước khi clear. Lần tìm sau đó không thể lấy lại instance cũ từ first-level cache vì context đã được làm sạch.

## 5. Ví dụ integration test với Spring Data JPA

Giả sử entity:

~~~java
@Entity
@Table(name = "app_user")
public class AppUser {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String displayName;

    protected AppUser() {
    }

    public AppUser(String displayName) {
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void rename(String displayName) {
        this.displayName = displayName;
    }
}
~~~

Repository:

~~~java
public interface AppUserRepository
        extends JpaRepository<AppUser, Long> {
}
~~~

Test dùng `@DataJpaTest`:

~~~java
@DataJpaTest
class AppUserRepositoryReloadTest {

    @Autowired
    AppUserRepository repository;

    @PersistenceContext
    EntityManager entityManager;

    @Test
    void reloadsEntityAfterClearingPersistenceContext() {
        AppUser user = repository.save(new AppUser("Alice"));

        entityManager.flush();
        Long id = user.getId();

        // Thay đổi object trong bộ nhớ nhưng chưa flush.
        user.rename("Alicia");

        AppUser foundBeforeClear =
            repository.findById(id).orElseThrow();

        // Cùng persistence context nên JPA trả instance đang managed.
        assertSame(user, foundBeforeClear);
        assertEquals("Alicia", foundBeforeClear.getDisplayName());

        // Loại entity cũ khỏi first-level cache.
        entityManager.clear();

        assertFalse(entityManager.contains(user));

        AppUser reloaded = repository.findById(id).orElseThrow();

        assertNotSame(user, reloaded);
        assertTrue(entityManager.contains(reloaded));
        assertEquals("Alice", reloaded.getDisplayName());
    }
}
~~~

Test này thể hiện rõ hai trạng thái:

- Trước clear, `findById` trả lại cùng object đang managed, nên thấy thay đổi chưa flush là Alicia.
- Sau clear, entity cũ detached. Lần tìm tiếp theo nạp trạng thái đã flush trong database, tức Alice.

`@DataJpaTest` thường chạy trong test-managed transaction và rollback sau mỗi method. Việc clear persistence context không kết thúc transaction này. Vì vậy, dữ liệu insert trong test vẫn nằm trong transaction hiện tại và được rollback khi test hoàn tất theo cấu hình mặc định.

Nếu dùng `@SpringBootTest` thay vì `@DataJpaTest`, có thể inject repository và EntityManager tương tự, đồng thời cấu hình `@Transactional` nếu muốn Spring TestContext quản lý transaction quanh method.

## 6. Dùng EntityManager.find trực tiếp để kiểm tra

Repository không bắt buộc trong bước tải lại. Có thể dùng EntityManager:

~~~java
entityManager.flush();

Long id = user.getId();

entityManager.clear();

AppUser reloaded = entityManager.find(AppUser.class, id);

assertNotNull(reloaded);
assertNotSame(user, reloaded);
assertEquals("Alice", reloaded.getDisplayName());
~~~

Cách này làm rõ rằng thao tác tìm được thực hiện bởi JPA EntityManager. Dùng repository khi muốn kiểm tra cả đường truy cập qua Spring Data; dùng EntityManager trực tiếp khi mục tiêu chỉ là persistence context và JPA identity behavior.

Cần lưu ý rằng EntityManager được inject trong Spring thường là proxy gắn với transaction. Nó đại diện cho EntityManager phù hợp với transaction hiện tại. Gọi `clear()` trên đó làm sạch persistence context đang được sử dụng trong transaction đó.

## 7. Dùng TestEntityManager trong @DataJpaTest

Spring Boot cung cấp `TestEntityManager` để hỗ trợ kiểm thử JPA. Nó cung cấp các thao tác tiện lợi như persist, flush, clear, find và detach.

Ví dụ:

~~~java
@DataJpaTest
class AppUserPersistenceTest {

    @Autowired
    TestEntityManager testEntityManager;

    @Test
    void reloadsEntityAfterClear() {
        AppUser user = new AppUser("Alice");

        testEntityManager.persistAndFlush(user);
        Long id = user.getId();

        testEntityManager.clear();

        AppUser reloaded =
            testEntityManager.find(AppUser.class, id);

        assertNotSame(user, reloaded);
        assertEquals("Alice", reloaded.getDisplayName());
    }
}
~~~

`persistAndFlush` lưu entity và flush thay đổi xuống database. `clear` làm sạch persistence context, còn `find` tải entity lại.

`TestEntityManager` là tiện ích của Spring Boot Test, không phải API JPA chuẩn. Nếu dự án không dùng Spring Boot hoặc test cần kiểm tra cách repository được gọi, hãy dùng EntityManager và repository thông thường.

## 8. Vì sao phải flush trước clear?

Đây là điểm dễ gây lỗi nhất khi kiểm tra reload.

Giả sử test làm như sau:

~~~java
AppUser user = new AppUser("Alice");
entityManager.persist(user);

entityManager.clear();

AppUser reloaded = entityManager.find(AppUser.class, user.getId());
~~~

Nếu chưa flush, lệnh insert có thể vẫn đang được giữ trong persistence context. Gọi clear detach entity và bỏ trạng thái pending mà context đang theo dõi. Lần tìm sau đó có thể không thấy bản ghi vì insert chưa được gửi xuống database.

Cách đúng:

~~~java
entityManager.persist(user);
entityManager.flush();

Long id = user.getId();

entityManager.clear();

AppUser reloaded = entityManager.find(AppUser.class, id);
~~~

Hãy lưu ID trước khi clear. Sau clear, object cũ đã detached; việc tiếp tục dùng nó như entity managed có thể dẫn đến kết quả khó hiểu hoặc lỗi khi thao tác relationship.

Flush cũng hữu ích sau khi cập nhật:

~~~java
user.rename("Alicia");

entityManager.flush();
entityManager.clear();

AppUser reloaded = entityManager.find(AppUser.class, id);

assertEquals("Alicia", reloaded.getDisplayName());
~~~

Trong trường hợp này, assertion xác nhận giá trị mới đã được đồng bộ xuống database và có thể được tải lại sau khi clear.

## 9. Clear không phải commit và không tạo transaction mới

`EntityManager.clear()` chỉ làm sạch persistence context. Nó không:

- Commit transaction hiện tại.
- Rollback transaction hiện tại.
- Mở một transaction mới.
- Đóng EntityManager hoặc ApplicationContext.
- Xóa bản ghi trong database.
- Xóa second-level cache của JPA provider.

Sau khi clear, test vẫn ở trong transaction cũ nếu transaction đó chưa được kết thúc. Nếu test flush insert rồi clear, sau đó find lại, nó có thể đọc dữ liệu do chính transaction hiện tại ghi ra. Đây là read-after-flush trong cùng transaction, không phải bằng chứng rằng một transaction khác đã nhìn thấy dữ liệu sau commit.

Nếu mục tiêu là xác nhận dữ liệu đã commit và có thể được đọc trong transaction mới, cần kết thúc transaction hiện tại bằng cơ chế phù hợp, chẳng hạn Spring TestContext `TestTransaction.flagForCommit()` rồi `TestTransaction.end()`, sau đó bắt đầu transaction mới bằng `TestTransaction.start()` khi test được cấu hình hỗ trợ.

| Mục tiêu kiểm tra | Cách phù hợp |
|---|---|
| Tránh first-level cache trả object cũ | `flush()` rồi `clear()` |
| Làm mới một entity đang managed | `refresh(entity)` |
| Tách một entity khỏi context | `detach(entity)` |
| Kiểm tra dữ liệu sau commit trong transaction mới | Commit transaction rồi bắt đầu transaction mới |
| Kiểm tra rollback của test | Để test-managed transaction rollback hoặc đánh dấu rollback |

## 10. Clear và second-level cache

JPA persistence context là first-level cache, gắn với một EntityManager. `clear()` làm sạch cache này.

Một số ứng dụng còn bật second-level cache ở cấp persistence unit hoặc provider. Cache đó có thể sống lâu hơn một EntityManager và được chia sẻ giữa nhiều persistence context. Vì vậy, sau khi clear first-level cache, lần tìm entity có thể vẫn được phục vụ từ second-level cache thay vì truy vấn database.

Nếu mục tiêu của test chỉ là chứng minh entity không còn được giữ trong persistence context hiện tại, `clear()` là thao tác phù hợp.

Nếu mục tiêu là xác nhận dữ liệu thực sự được đọc từ database và không lấy từ second-level cache, cần kiểm soát cache riêng. JPA cung cấp `CacheRetrieveMode.BYPASS` cho thao tác tìm, hoặc có thể evict entity khỏi shared cache khi test phù hợp. Cách cấu hình cụ thể phụ thuộc phiên bản Jakarta Persistence và provider.

Ví dụ dùng cache retrieve mode:

~~~java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);

AppUser reloaded =
    entityManager.find(AppUser.class, id, hints);
~~~

Đoạn ví dụ dùng namespace Jakarta Persistence hiện đại. Với ứng dụng JPA cũ dùng package `javax.persistence`, cần dùng API và hint tương ứng với phiên bản đó.

Không cần bypass second-level cache trong mọi test. Chỉ làm vậy khi chính hành vi cache cấp hai nằm ngoài phạm vi cần kiểm tra.

## 11. Clear và refresh: chọn thao tác theo mục tiêu

Hai thao tác thường bị nhầm:

~~~java
entityManager.refresh(user);
~~~

và:

~~~java
entityManager.clear();
AppUser reloaded = entityManager.find(AppUser.class, id);
~~~

`refresh` giữ nguyên entity managed và nạp lại trạng thái database vào chính object đó. Sau refresh, biến `user` vẫn trỏ tới cùng instance, nhưng field được cập nhật từ dữ liệu được đọc.

`clear` detach tất cả entity. Khi tìm lại, JPA tạo hoặc lấy một managed instance mới cho identity đó trong persistence context đã được làm sạch.

| Tiêu chí | refresh | clear rồi find |
|---|---|---|
| Phạm vi | Một entity | Tất cả entity đang managed |
| Object cũ | Vẫn managed | Detached |
| Identity Java sau thao tác | Giữ cùng instance | Lần tìm có instance mới |
| Mục tiêu điển hình | Bỏ thay đổi trong bộ nhớ và nạp lại một entity | Kiểm tra tải lại sau khi bỏ first-level cache |
| Điều kiện | Entity phải đang managed | Entity có thể được tìm lại theo ID |

Dùng refresh nếu muốn cập nhật một entity đang managed từ database. Dùng clear khi muốn bảo đảm lần tìm sau không lấy lại object cũ từ persistence context.

## 12. Entity detached sau clear và ảnh hưởng tới lazy loading

Sau khi clear, mọi entity trước đó được quản lý trong context trở thành detached. Các object Java vẫn tồn tại, nhưng EntityManager không còn theo dõi thay đổi của chúng.

Ví dụ:

~~~java
entityManager.clear();

user.rename("Changed after clear");

entityManager.flush();
~~~

Lời gọi `flush()` không tự lưu thay đổi vừa thực hiện trên `user`, vì object này đã detached. Nếu muốn cập nhật lại entity, hãy tìm entity managed theo ID hoặc dùng `merge()` đúng cách.

Các association lazy cũng cần được chú ý. Nếu test clear context rồi truy cập một collection lazy trên object cũ, provider có thể không tải được dữ liệu vì entity không còn managed. Điều này có thể dẫn tới `LazyInitializationException` trong Hibernate hoặc lỗi truy cập association ngoài persistence context theo provider.

Cách phù hợp là tải lại root entity sau clear rồi truy cập association trong khi entity mới còn managed và context đang hoạt động:

~~~java
entityManager.clear();

Order reloaded = entityManager.find(Order.class, orderId);

assertEquals(2, reloaded.getItems().size());
~~~

Nếu association cần được tải cùng root, cân nhắc entity graph, fetch join hoặc query phù hợp với mục tiêu test. Không giữ tham chiếu collection lazy của entity cũ rồi kỳ vọng nó tiếp tục hoạt động sau clear.

## 13. Clear trong transaction isolation và kiểm tra thay đổi bên ngoài

Clear buộc JPA bỏ first-level cache, nhưng không thay đổi isolation level của database và không kết thúc transaction.

Nếu transaction đang dùng isolation như REPEATABLE READ hoặc SNAPSHOT, database có thể tiếp tục cung cấp cùng snapshot cho những lần đọc tiếp theo trong transaction đó. Vì thế, clear không bảo đảm test nhìn thấy dữ liệu vừa được một transaction khác commit sau khi transaction hiện tại bắt đầu.

Để kiểm tra một transaction mới nhìn thấy commit của transaction trước, hãy:

1. Commit transaction ghi dữ liệu.
2. Kết thúc transaction đó.
3. Bắt đầu transaction mới.
4. Đọc lại dữ liệu trong transaction mới.

Nếu chỉ cần xác nhận object đã được đồng bộ và có thể nạp lại trong cùng transaction, flush rồi clear là đủ. Nếu cần xác nhận tính nhìn thấy giữa các transaction, hãy thiết kế test với transaction boundary riêng.

## 14. Các lỗi thường gặp

- **Gọi clear trước flush:** thay đổi pending có thể chưa được gửi xuống database; flush trước nếu cần giữ chúng.
- **Cho rằng clear commit dữ liệu:** clear chỉ detach entity, transaction vẫn tiếp tục.
- **Cho rằng find luôn phát sinh SQL:** JPA có thể trả entity từ first-level cache nếu entity vẫn managed.
- **Chỉ assert field sau save:** assertion có thể đang đọc object trong bộ nhớ, không chứng minh dữ liệu được tải lại.
- **Dùng refresh sau khi entity đã detached:** refresh yêu cầu entity managed; hãy tìm lại entity hoặc dùng thao tác phù hợp.
- **Tiếp tục sửa object cũ sau clear rồi mong flush lưu thay đổi:** object đó đã detached và không còn được dirty checking theo dõi.
- **Quên lưu ID trước clear:** test có thể phụ thuộc vào trạng thái object cũ hoặc generated identifier.
- **Coi clear là transaction mới:** transaction và isolation level vẫn như trước.
- **Bỏ qua second-level cache:** clear chỉ tác động first-level cache; cache cấp hai có thể vẫn cung cấp entity.
- **Truy cập lazy association trên entity detached:** tải lại root entity trong context đang hoạt động hoặc dùng fetch plan phù hợp.
- **Dùng clear khi chỉ cần refresh một entity:** clear detach tất cả entity, có thể làm hỏng các tham chiếu managed khác mà test đang cần.
- **Kết luận dữ liệu đã commit chỉ từ flush rồi clear:** flush không commit; test vẫn có thể đang ở trong cùng transaction.

## 15. Quy trình kiểm tra việc tải lại entity

Khi cần chứng minh một entity có thể được tải lại sau khi persistence context không còn giữ instance cũ, hãy thực hiện:

1. Tạo entity hoặc cập nhật trạng thái cần kiểm tra.
2. Persist hoặc save entity qua repository.
3. Gọi `EntityManager.flush()` hoặc `saveAndFlush()` để đồng bộ dữ liệu.
4. Lưu ID của entity vào biến độc lập.
5. Gọi `EntityManager.clear()` để detach toàn bộ entity.
6. Xác nhận object cũ không còn managed bằng `EntityManager.contains()` nếu cần.
7. Tìm entity lại bằng repository hoặc `EntityManager.find()`.
8. Kiểm tra instance mới bằng `assertNotSame()`.
9. Kiểm tra các field hoặc association đã được tải lại.
10. Nếu mục tiêu là kiểm tra commit visibility, kết thúc transaction và bắt đầu transaction mới; clear đơn thuần chưa đủ.
11. Nếu second-level cache đang bật và test cần xác nhận truy vấn database, kiểm soát cache cấp hai riêng.

## Kết luận

Persistence context giữ các entity đang managed và hoạt động như first-level cache của JPA. Vì vậy, tìm lại entity theo cùng ID có thể trả về đúng object cũ mà không kiểm tra việc nạp dữ liệu từ database. Trong test cần xác nhận reload, hãy flush những thay đổi cần giữ, clear persistence context rồi tìm entity lại theo ID.

`flush()` đồng bộ thay đổi nhưng không commit; `clear()` detach toàn bộ entity nhưng không kết thúc transaction; `refresh()` nạp lại một entity vẫn đang managed; còn `detach()` chỉ tách một entity. Phân biệt các thao tác này giúp test kiểm tra đúng điều cần kiểm tra: trạng thái object trong bộ nhớ, dữ liệu đã đồng bộ xuống database hay dữ liệu đã commit và nhìn thấy từ transaction mới.

