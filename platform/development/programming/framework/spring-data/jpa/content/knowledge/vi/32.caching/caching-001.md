# Phạm vi và tính nhất quán của bộ nhớ đệm cấp một

Trong JPA, bộ nhớ đệm cấp một (first-level cache) chính là persistence context gắn với một `EntityManager`. Nó giữ các entity đang được quản lý trong phạm vi của persistence context, giúp một entity có cùng loại và khóa chính chỉ có một instance managed trong context đó. Nhờ vậy, JPA có thể theo dõi thay đổi bằng dirty checking và tránh tải lại cùng một entity nhiều lần trong cùng phạm vi quản lý.

Bộ nhớ đệm cấp một luôn tồn tại trong persistence context; ứng dụng không bật/tắt nó như một cache tùy chọn. Tuy nhiên, phạm vi sống của persistence context, thời điểm đồng bộ dữ liệu và cách làm mới entity quyết định dữ liệu mà code nhìn thấy có còn mới hay không.

## 1. Persistence context là gì?

Persistence context là một tập hợp các entity instance mà một `EntityManager` đang quản lý. Mỗi entity managed được định danh bởi entity type và primary key. Trong cùng một persistence context, JPA duy trì identity guarantee: một định danh entity tương ứng với một instance được quản lý.

Ví dụ:

```java
User first = entityManager.find(User.class, 10L);
User second = entityManager.find(User.class, 10L);

System.out.println(first == second); // true trong cùng persistence context
```

Lần gọi thứ hai có thể trả về chính instance đã được quản lý từ lần gọi trước, thay vì tạo một object managed khác cho cùng định danh. Điều này có nghĩa thay đổi trên `first` cũng được nhìn thấy khi code đọc qua `second`, vì cả hai biến tham chiếu cùng một object.

Persistence context còn có các trách nhiệm:

- Giữ trạng thái hiện tại của entity managed.
- Theo dõi thay đổi của entity để thực hiện dirty checking.
- Duy trì quan hệ giữa các entity và trạng thái của chúng.
- Điều phối các thao tác persist, remove, merge, refresh và flush.
- Bảo đảm identity của entity trong phạm vi quản lý.

First-level cache không phải một map cache do ứng dụng tự tạo và cũng không phải cache dùng chung cho toàn bộ ứng dụng. Nó gắn với một persistence context cụ thể.

## 2. Vòng đời của persistence context trong Spring Data JPA

Trong ứng dụng Spring Data JPA thông thường, `EntityManager` được quản lý thông qua Spring và transaction manager. Khi một service method có `@Transactional` được gọi, Spring mở hoặc tham gia transaction và gắn EntityManager phù hợp với transaction đó vào thread hiện tại. Các repository được gọi trong cùng transaction thường sử dụng cùng persistence context.

Ví dụ:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserService {

    private final UserRepository users;

    public UserService(UserRepository users) {
        this.users = users;
    }

    @Transactional
    public void updateAndRead(Long id) {
        User first = users.findById(id).orElseThrow();
        first.setDisplayName("New name");

        User second = users.findById(id).orElseThrow();

        // Hai lần đọc trong cùng persistence context có thể trả về
        // cùng instance managed.
        System.out.println(first == second); // true
        System.out.println(second.getDisplayName()); // New name
    }
}
```

Trong ví dụ này, lần đọc thứ hai nhìn thấy giá trị mới vì entity đang managed đã được sửa trong bộ nhớ. Chưa cần gọi `save()` để JPA nhận biết thay đổi; dirty checking sẽ phát hiện thay đổi khi persistence context flush.

### Phạm vi mặc định và các trường hợp đặc biệt

- **Transaction-scoped persistence context:** mô hình phổ biến với Spring Data JPA. Persistence context gắn với transaction; khi transaction kết thúc, context tương ứng được đóng hoặc kết thúc theo cách quản lý của Spring/provider.
- **Extended persistence context:** có thể tồn tại qua nhiều transaction trong những mô hình JPA đặc biệt. Không nên giả định ứng dụng Spring Boot thông thường đang dùng kiểu này.
- **Open EntityManager in View (OSIV):** nếu được bật, EntityManager có thể được mở trong suốt một HTTP request để hỗ trợ lazy loading ở tầng web. Điều đó kéo dài phạm vi persistence context theo request, nhưng không biến nó thành cache toàn ứng dụng và cũng không có nghĩa toàn bộ request nằm trong một database transaction.

Vì vậy, khi phân tích dữ liệu cũ, cần xác định chính xác EntityManager/persistence context nào đang được dùng và nó sống trong phạm vi nào.

## 3. First-level cache hoạt động ra sao?

### find() và identity trong cùng context

Khi gọi:

```java
User user = entityManager.find(User.class, 10L);
```

JPA kiểm tra persistence context. Nếu entity có định danh đó đã managed, `find()` trả về instance đang được quản lý. Nếu chưa có, provider lấy dữ liệu từ database, tạo entity instance và đưa vào persistence context.

Điều này có nghĩa:

- Một lần `find()` đầu tiên có thể cần truy vấn database.
- Các lần `find()` tiếp theo cho cùng entity trong cùng persistence context có thể được phục vụ từ first-level cache.
- Khi context khác được tạo, entity đó không tự động được chia sẻ sang context mới.

### JPQL query vẫn có thể truy vấn database

Không nên suy luận rằng first-level cache làm mọi query trở thành cache hit. Một JPQL query như:

```java
List<User> users = entityManager.createQuery(
    "select u from User u where u.active = true",
    User.class
).getResultList();
```

vẫn có thể cần thực thi SQL để database đánh giá điều kiện và tìm các hàng phù hợp. Khi kết quả chứa entity đã có trong persistence context, provider dùng lại instance managed tương ứng thay vì tạo một instance managed thứ hai cho cùng định danh.

Do đó, query có thể đọc được tập kết quả mới từ database nhưng object trả về vẫn có trạng thái đang được quản lý trong persistence context. JPA không tự động refresh tất cả field của entity managed chỉ vì query được chạy lại.

### First-level cache lưu entity managed, không phải mọi kết quả truy vấn

First-level cache chủ yếu quản lý entity instance. Không nên xem nó là cache tổng quát cho:

- DTO projection.
- Scalar result như `count(*)`.
- Mọi câu lệnh JPQL/native query.
- Kết quả tìm kiếm bất kỳ.

Query cache của Hibernate, nếu được cấu hình, là một cơ chế khác. Second-level cache cũng là cơ chế riêng, có thể chia sẻ dữ liệu entity giữa nhiều persistence context theo cấu hình provider.

## 4. Dirty checking và thời điểm dữ liệu được ghi xuống database

Khi entity đang managed bị thay đổi, JPA ghi nhận trạng thái trong persistence context. Provider có thể phát hiện khác biệt giữa trạng thái hiện tại và snapshot ban đầu khi flush.

```java
@Transactional
public void renameUser(Long id) {
    User user = entityManager.find(User.class, id);
    user.setDisplayName("Lan");

    // Không nhất thiết có SQL UPDATE ngay tại dòng setter.
    // SQL thường được phát khi flush hoặc commit.
}
```

### flush() đồng bộ thay đổi đang chờ

`EntityManager.flush()` yêu cầu provider đồng bộ thay đổi trong persistence context với database bằng SQL. Flush không kết thúc transaction và không commit dữ liệu.

```java
entityManager.flush();
```

Sau flush:

- Các câu lệnh SQL cần thiết đã được gửi trong transaction hiện tại.
- Entity vẫn managed và vẫn nằm trong first-level cache.
- Các thay đổi tiếp theo vẫn có thể được dirty checking.
- Transaction vẫn có thể rollback.

Vì vậy, flush không phải thao tác xóa cache và cũng không làm dữ liệu trở nên bền vững độc lập với transaction.

### Commit thường kéo theo flush

Khi transaction commit, JPA provider đồng bộ các thay đổi cần thiết trước khi transaction được commit. Tùy flush mode và provider, flush cũng có thể xảy ra trước một query khi cần bảo đảm query nhìn thấy thay đổi trong persistence context.

Nếu cần xác định lỗi SQL tại một vị trí cụ thể, có thể flush tường minh. Điều này hữu ích để phát hiện sớm constraint violation hoặc optimistic locking failure, nhưng không thay đổi phạm vi sống của first-level cache.

## 5. Vì sao entity có thể bị stale?

First-level cache bảo đảm identity trong một persistence context; nó không bảo đảm entity luôn phản ánh thay đổi mới nhất từ database do transaction khác hoặc hệ thống khác thực hiện.

Ví dụ:

1. Transaction A tải `User#10`, nhận `displayName = "An"`.
2. Entity `User#10` được giữ trong persistence context của A.
3. Transaction B cập nhật database thành `displayName = "Binh"` và commit.
4. Transaction A gọi lại `find(User.class, 10L)`.
5. Nếu entity vẫn managed trong persistence context A, JPA có thể trả về instance đang có với giá trị "An".

Transaction A không tự động biết rằng transaction B đã thay đổi hàng đó. Đây là trạng thái stale của entity trong context A.

Tính nhất quán còn phụ thuộc isolation level của database, transaction snapshot, cache provider và cách query được thực thi. First-level cache chỉ quản lý trạng thái trong context; nó không thay thế cơ chế concurrency control hoặc isolation của database.

### Cách xử lý khi cần dữ liệu mới

Có một số lựa chọn tùy yêu cầu:

- Gọi `refresh(entity)` để nạp lại trạng thái entity managed từ database.
- Gọi `detach(entity)` nếu chỉ muốn một entity ngừng được quản lý, sau đó tải lại.
- Gọi `clear()` để detach toàn bộ entity trong persistence context, rồi truy vấn lại.
- Kết thúc transaction/persistence context hiện tại và đọc trong một transaction mới khi cần một context mới.

Không có lựa chọn nào phù hợp cho mọi trường hợp. Hãy cân nhắc các thay đổi chưa flush trước khi refresh hoặc clear.

## 6. Phân biệt refresh, detach, clear và merge

| Thao tác | Tác động | Phạm vi |
|---|---|---|
| `refresh(entity)` | Nạp lại trạng thái từ database, ghi đè thay đổi chưa flush của entity đó | Một entity managed |
| `detach(entity)` | Loại entity khỏi persistence context; entity trở thành detached | Một entity |
| `clear()` | Detach tất cả entity đang managed | Toàn persistence context |
| `merge(entity)` | Sao chép trạng thái từ entity new/detached vào một instance managed và trả về instance managed đó | Entity được merge |

### refresh(): đọc lại dữ liệu database

```java
@Transactional
public void reloadUser(Long id) {
    User user = entityManager.find(User.class, id);

    entityManager.refresh(user);

    // Các field của user được nạp lại từ database.
}
```

`refresh()` cần entity managed. Thao tác này có thể ghi đè thay đổi chưa flush trên entity. Nếu hàng đã bị xóa hoặc không còn tồn tại, refresh có thể thất bại. Có thể dùng cascade refresh nếu mapping và nghiệp vụ yêu cầu.

### detach(): ngừng quản lý một entity

```java
entityManager.detach(user);
```

Sau detach, thay đổi trên object Java không còn được persistence context theo dõi. Muốn lưu trạng thái đã sửa, phải merge hoặc thực hiện một luồng cập nhật khác phù hợp.

### clear(): làm rỗng persistence context

```java
entityManager.clear();
```

Clear không xóa dữ liệu database. Nó chỉ detach mọi entity đang managed trong context. Nếu có thay đổi chưa flush, chúng có thể không được ghi và sẽ mất khỏi phạm vi dirty checking.

Khi cần flush thay đổi rồi mới clear, thứ tự phải là:

```java
entityManager.flush();
entityManager.clear();
```

### merge(): không biến object cũ thành managed

```java
User detached = obtainDetachedUser();

User managed = entityManager.merge(detached);

// detached vẫn là object detached.
// managed là instance được quản lý.
managed.setDisplayName("Updated");
```

Đây là điểm dễ nhầm: `merge()` sao chép trạng thái vào một instance managed; nó không gắn lại chính object detached ban đầu.

## 7. Quan hệ với Spring Data repository và save()

Spring Data JPA repository thường dùng EntityManager được quản lý bởi Spring. Trong một service transaction, các repository cùng tham gia transaction thường thao tác trên cùng persistence context.

Ví dụ:

```java
@Transactional
public void updateTwice(Long id) {
    User first = userRepository.findById(id).orElseThrow();
    first.setDisplayName("First change");

    User second = userRepository.findById(id).orElseThrow();

    // Cùng persistence context: second nhìn thấy First change.
    System.out.println(second.getDisplayName());

    second.setActive(false);
}
```

Đối với entity đang managed, dirty checking đủ để ghi thay đổi khi flush/commit. Không cần gọi `save()` chỉ để báo JPA rằng entity đã thay đổi.

Tuy nhiên, Spring Data JPA `save()` thường chọn `persist()` cho entity được nhận diện là mới và `merge()` cho entity đã tồn tại. Nếu `merge()` được dùng, hãy tiếp tục làm việc với instance mà `save()` trả về khi cần trạng thái managed:

```java
User managed = userRepository.save(detached);
managed.setDisplayName("New value");
```

`save()` không có nghĩa luôn phát SQL ngay; SQL có thể chỉ được gửi ở flush hoặc commit. Ngoài ra, không nên dùng việc gọi `save()` lặp lại như một cách làm mới entity stale. Hãy dùng `refresh()`, context mới hoặc query phù hợp.

## 8. Bộ nhớ đệm cấp một và các cache khác

| Cơ chế | Phạm vi | Bật/tắt | Vai trò |
|---|---|---|---|
| First-level cache | Một persistence context/EntityManager | Luôn gắn với persistence context | Quản lý identity, trạng thái managed và dirty checking |
| Second-level cache | Chia sẻ giữa các persistence context trong cùng cấu hình provider | Tùy chọn, phụ thuộc provider | Tái sử dụng trạng thái entity giữa các EntityManager |
| Query cache | Cache kết quả truy vấn theo cơ chế provider | Tùy chọn | Tái sử dụng một số kết quả query; không thay thế entity state |
| Cache ứng dụng | Phạm vi do ứng dụng định nghĩa, ví dụ Caffeine/Redis | Tùy thiết kế | Cache dữ liệu nghiệp vụ hoặc response theo key riêng |

Không nên gọi first-level cache là cache toàn cục. Hai EntityManager khác nhau có thể cùng quản lý một hàng database nhưng giữ hai instance và hai snapshot khác nhau.

## 9. Optimistic locking và tính nhất quán khi nhiều transaction cùng cập nhật

First-level cache không ngăn hai transaction khác nhau cùng đọc và cập nhật một hàng. Nếu nghiệp vụ cần phát hiện cập nhật cạnh tranh, có thể dùng optimistic locking với `@Version`.

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Product {

    @Id
    private Long id;

    private String name;

    @Version
    private Long version;

    protected Product() {
    }

    public void rename(String name) {
        this.name = name;
    }
}
```

Khi provider cập nhật entity có version, câu lệnh SQL thường kiểm tra version hiện tại và tăng version. Nếu transaction khác đã cập nhật trước, lần cập nhật có thể thất bại bằng optimistic locking exception.

`@Version` bảo vệ cạnh tranh dữ liệu giữa transaction; first-level cache chủ yếu bảo đảm identity và quản lý trạng thái bên trong một persistence context. Hai cơ chế giải quyết hai vấn đề khác nhau.

Nếu dùng bulk JPQL/native update, cần đặc biệt chú ý vì bulk operation không đi qua dirty checking của từng entity và không mặc nhiên thực hiện optimistic locking như cập nhật entity thông thường.

## 10. Những lưu ý về phạm vi và an toàn luồng

- **EntityManager không thread-safe:** không chia sẻ một EntityManager hoặc managed entity tùy tiện giữa nhiều thread. Spring thường cung cấp proxy để chọn EntityManager gắn với thread/transaction hiện tại; không tự giữ và chia sẻ đối tượng thật giữa các luồng.
- **Không dùng managed entity như DTO lâu dài:** sau khi transaction/context kết thúc, entity có thể detached. Hãy chuyển dữ liệu cần thiết sang DTO hoặc value object.
- **Lazy loading phụ thuộc context:** truy cập quan hệ lazy sau khi EntityManager đã đóng có thể gây lỗi lazy initialization. OSIV có thể che một số lỗi này nhưng không thay thế thiết kế fetch rõ ràng.
- **Read-only transaction không làm entity bất biến:** `@Transactional(readOnly = true)` có thể cho provider tối ưu flush behavior, nhưng không phải cơ chế bảo vệ dữ liệu hoặc biến object thành immutable.
- **Không giữ context quá lâu:** persistence context lớn có thể tốn bộ nhớ và dirty checking nhiều entity. Với batch processing, cân nhắc flush/clear theo lô và quản lý transaction boundary hợp lý.

## 11. Kiểm thử phạm vi và tính nhất quán

Nên dùng integration test với database và transaction manager phù hợp để kiểm tra hành vi thực tế. Các ca quan trọng:

1. Gọi `find()` hai lần cùng ID trong một EntityManager và xác nhận hai biến tham chiếu cùng managed instance.
2. Sửa entity rồi đọc lại trong cùng persistence context; xác nhận thay đổi trong bộ nhớ được nhìn thấy ngay.
3. Flush, clear rồi tải lại entity; xác nhận dữ liệu được đọc từ trạng thái database đã đồng bộ.
4. Dùng hai transaction riêng: transaction thứ nhất giữ entity managed, transaction thứ hai cập nhật và commit; kiểm tra cách transaction thứ nhất nhìn thấy entity cũ, rồi thử refresh.
5. Kiểm tra `detach()` và `merge()`: object detached không còn được dirty checking, còn instance trả về từ merge là managed.
6. Kiểm tra optimistic locking bằng hai transaction cập nhật cùng entity version.
7. Kiểm tra bulk update: sau query, entity đã managed có thể stale; clear/refresh và tải lại để xác nhận dữ liệu.

Ví dụ unit/integration test cần lưu ý: không đặt `@Transactional` lên test nếu mục tiêu là quan sát thời điểm commit thực sự ở service. Transaction do test framework quản lý có thể khiến transaction service tham gia vào transaction của test, làm thay đổi thời điểm flush/commit.

## 12. Quy trình chẩn đoán entity stale

Khi ứng dụng đọc thấy dữ liệu cũ, kiểm tra theo thứ tự:

1. Xác định EntityManager/persistence context đang quản lý entity.
2. Kiểm tra entity đã được load trước đó trong context chưa.
3. Kiểm tra có transaction khác, bulk query hoặc native SQL cập nhật cùng hàng không.
4. Xác định thay đổi trong context đã flush hay chưa.
5. Nếu cần dữ liệu mới, chọn `refresh(entity)`, detach/clear rồi load lại, hoặc kết thúc context và đọc trong transaction mới.
6. Nếu có nhiều transaction cùng ghi, bổ sung optimistic locking hoặc thiết kế isolation/concurrency control phù hợp.
7. Kiểm tra OSIV hoặc extended persistence context nếu context sống lâu hơn dự kiến.

## Kết luận

First-level cache là persistence context của EntityManager, không phải cache dùng chung toàn ứng dụng. Nó giữ identity và trạng thái entity managed trong phạm vi context, hỗ trợ dirty checking và giảm việc tải lại cùng entity. Tuy nhiên, entity managed có thể stale khi database thay đổi từ transaction khác hoặc bulk operation.

Hiểu rõ vòng đời EntityManager và phân biệt `flush()`, `refresh()`, `detach()`, `clear()`, `merge()` là điều kiện để giữ dữ liệu nhất quán. Khi cần phát hiện cập nhật cạnh tranh giữa các transaction, dùng optimistic locking hoặc cơ chế phù hợp ở database; không trông chờ first-level cache giải quyết thay.
