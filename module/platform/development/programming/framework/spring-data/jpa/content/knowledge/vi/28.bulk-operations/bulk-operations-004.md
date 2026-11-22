# flushAutomatically và clearAutomatically trong Spring Data JPA

Khi dùng Spring Data JPA để chạy câu lệnh cập nhật hoặc xóa hàng loạt bằng `@Modifying`, cơ sở dữ liệu có thể đã thay đổi trong khi các entity đang được quản lý trong persistence context vẫn giữ giá trị cũ. Hai thuộc tính `flushAutomatically` và `clearAutomatically` giúp kiểm soát thời điểm đồng bộ các thay đổi đang chờ và làm mới trạng thái quản lý sau câu lệnh bulk.

- `flushAutomatically = true`: yêu cầu Spring Data JPA gọi `EntityManager.flush()` trước khi thực thi câu lệnh modifying query.
- `clearAutomatically = true`: yêu cầu Spring Data JPA gọi `EntityManager.clear()` sau khi thực thi câu lệnh modifying query.

Hai thuộc tính này thuộc annotation `@Modifying`. Chúng có mục đích khác nhau và không thay thế cho `@Transactional`.

## 1. Vì sao bulk update/delete cần flush và clear?

### Persistence context giữ trạng thái entity

Trong một transaction, JPA thường quản lý các entity đã được tải hoặc persist thông qua persistence context. Khi thay đổi một entity đang managed, Hibernate/JPA thường ghi nhận thay đổi trong bộ nhớ và đồng bộ câu lệnh SQL xuống cơ sở dữ liệu tại thời điểm flush.

Ví dụ:

```java
User user = entityManager.find(User.class, 10L);
user.setActive(false);
```

Sau lệnh `setActive(false)`, entity đã thay đổi trong persistence context. SQL `UPDATE` có thể chưa được gửi ngay xuống database. Việc phát hiện thay đổi và ghi SQL này thường được gọi là dirty checking.

Bulk JPQL update/delete hoạt động khác với việc sửa từng entity:

```java
UPDATE User u SET u.active = false WHERE u.lastLoginAt < :cutoff
```

Câu lệnh được database thực hiện trực tiếp trên nhiều hàng. JPA không lần lượt tải từng `User` thành object rồi áp dụng dirty checking. Vì vậy, các object `User` đang managed có thể không tự nhận được giá trị mới sau câu lệnh bulk.

Đây là nguồn gốc của hai vấn đề:

1. Có thay đổi entity đang chờ trong persistence context nhưng bulk query được thực thi trước khi những thay đổi đó được đồng bộ.
2. Bulk query đã cập nhật database, nhưng entity đang managed vẫn chứa giá trị cũ.

`flushAutomatically` xử lý vấn đề thứ nhất bằng cách flush trước query. `clearAutomatically` xử lý vấn đề thứ hai bằng cách clear persistence context sau query.

## 2. flushAutomatically: flush trước khi chạy modifying query

### Ý nghĩa

Khai báo:

```java
@Modifying(flushAutomatically = true)
```

yêu cầu Spring Data JPA gọi:

```java
entityManager.flush();
```

ngay trước khi thực thi câu lệnh update/delete được đánh dấu `@Modifying`.

Flush đồng bộ các thay đổi đang chờ trong persistence context xuống database trong transaction hiện tại. Flush không đồng nghĩa với commit. Transaction vẫn có thể rollback sau đó.

Ví dụ, ứng dụng sửa trạng thái một entity rồi chạy bulk query:

```java
User user = entityManager.find(User.class, 10L);
user.setActive(true);

// Bulk query chạy sau thay đổi trên.
int updated = userRepository.deactivateInactiveUsers(cutoff);
```

Nếu cần bảo đảm các thay đổi đang chờ được gửi xuống database trước câu lệnh bulk, dùng `flushAutomatically = true`. Điều này làm thứ tự thực thi rõ ràng: các thay đổi đã chờ được flush trước, sau đó bulk query mới chạy.

### Ví dụ repository

Giả sử entity `User` có các thuộc tính `active` và `lastLoginAt`:

```java
import java.time.LocalDateTime;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface UserRepository extends JpaRepository<User, Long> {

    @Modifying(flushAutomatically = true)
    @Query("""
        update User u
           set u.active = false
         where u.lastLoginAt < :cutoff
        """)
    int deactivateInactiveUsers(
        @Param("cutoff") LocalDateTime cutoff
    );
}
```

`flushAutomatically = true` hữu ích khi persistence context có thể chứa các thay đổi cần được ghi trước câu lệnh bulk, hoặc khi muốn kiểm soát rõ thứ tự đồng bộ.

### Flush có thể làm lộ lỗi sớm hơn

Vì flush gửi các thay đổi đang chờ xuống database, lỗi có thể xuất hiện ngay tại bước flush, ví dụ:

- Vi phạm unique constraint hoặc foreign key.
- Giá trị không đáp ứng ràng buộc NOT NULL.
- Lỗi optimistic locking khi cập nhật entity.
- Lỗi chuyển đổi kiểu dữ liệu hoặc lỗi SQL.

Đó không phải là lỗi do thuộc tính tự tạo ra; flush làm cho các thao tác đang chờ được thực thi sớm hơn nên lỗi được phát hiện tại thời điểm dễ xác định hơn.

### Khi nào không cần bật?

Nếu không có thay đổi đang chờ cần đồng bộ trước bulk query, hoặc cơ chế flush mặc định của JPA/provider đã đáp ứng yêu cầu, có thể giữ giá trị mặc định `false`.

Lưu ý rằng `flushAutomatically = false` có nghĩa Spring Data JPA không chủ động gọi `flush()` theo thuộc tính này. Provider vẫn có thể tự flush theo `FlushModeType.AUTO` và quy tắc đồng bộ của JPA. Khi cần bảo đảm rõ ràng rằng toàn bộ thay đổi đang chờ được flush trước modifying query, hãy bật thuộc tính này.

## 3. clearAutomatically: clear persistence context sau modifying query

### Ý nghĩa

Khai báo:

```java
@Modifying(clearAutomatically = true)
```

yêu cầu Spring Data JPA gọi:

```java
entityManager.clear();
```

sau khi câu lệnh modifying query thực thi.

`EntityManager.clear()` loại bỏ toàn bộ entity đang được quản lý khỏi persistence context hiện tại. Những object Java mà code đang giữ vẫn tồn tại, nhưng chuyển sang trạng thái detached. JPA không tiếp tục dirty checking các object đó trong persistence context vừa clear.

Điều này quan trọng vì bulk query thay đổi dữ liệu trực tiếp trong database, còn các entity đã được tải trước đó có thể vẫn chứa dữ liệu cũ.

### Ví dụ trạng thái stale

Giả sử một service tải user trước khi gọi bulk update:

```java
User user = userRepository.findById(10L).orElseThrow();

userRepository.deactivateInactiveUsers(cutoff);

// Biến user vẫn có thể chứa active=true,
// dù database đã được bulk update thành active=false.
System.out.println(user.isActive());
```

Bulk query không tự đồng bộ giá trị mới vào object `user` đang managed. Nếu sau query ứng dụng tiếp tục đọc entity này, nó có thể quan sát trạng thái cũ.

Bật `clearAutomatically = true` sẽ clear persistence context sau query. Khi cần đọc lại entity, tải lại từ repository hoặc EntityManager:

```java
@Modifying(clearAutomatically = true)
@Query("update User u set u.active = false where u.lastLoginAt < :cutoff")
int deactivateInactiveUsers(
    @Param("cutoff") LocalDateTime cutoff
);
```

Sau khi persistence context được clear, có thể gọi `findById()` để lấy một instance managed mới với dữ liệu hiện tại trong transaction:

```java
userRepository.deactivateInactiveUsers(cutoff);

User refreshed = userRepository.findById(10L).orElseThrow();
System.out.println(refreshed.isActive()); // false nếu user thỏa điều kiện bulk update
```

Ví dụ trên giả định user có `lastLoginAt` nhỏ hơn `cutoff` và câu lệnh đã thực thi thành công.

### Clear ảnh hưởng đến toàn bộ persistence context

`clearAutomatically = true` không chỉ clear những entity bị câu lệnh update/delete tác động. Nó clear tất cả entity đang managed trong persistence context hiện tại.

Hệ quả:

- Các entity đã tải trước đó đều trở thành detached.
- Thay đổi tiếp theo trên các object detached không còn được dirty checking tự động.
- Quan hệ lazy của object detached có thể không tải được nếu chưa được khởi tạo và không còn persistence context phù hợp.
- Nếu cần tiếp tục cập nhật một entity, hãy tải lại entity hoặc quản lý lại nó theo một transaction/persistence context thích hợp.

Vì phạm vi ảnh hưởng rộng, không nên bật clear tự động một cách máy móc trong những phương thức đang quản lý nhiều entity và còn cần tiếp tục thao tác trên chúng.

## 4. Dùng kết hợp flushAutomatically và clearAutomatically

Khi một persistence context có thể chứa thay đổi chưa flush và bulk query cũng có thể làm stale các entity đang managed, có thể bật cả hai:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
```

Thứ tự xử lý của Spring Data JPA là:

1. Gọi `EntityManager.flush()` trước câu lệnh modifying query nếu `flushAutomatically = true`.
2. Thực thi câu lệnh update/delete bằng `executeUpdate()`.
3. Gọi `EntityManager.clear()` sau câu lệnh nếu `clearAutomatically = true`.

Như vậy, thay đổi đang chờ được flush trước query; sau khi query cập nhật database, persistence context được clear để tránh tiếp tục dùng các entity stale.

Ví dụ đầy đủ ở tầng repository:

```java
import java.time.LocalDateTime;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface UserRepository extends JpaRepository<User, Long> {

    @Modifying(
        flushAutomatically = true,
        clearAutomatically = true
    )
    @Query("""
        update User u
           set u.active = false
         where u.lastLoginAt < :cutoff
        """)
    int deactivateInactiveUsers(
        @Param("cutoff") LocalDateTime cutoff
    );
}
```

Ở đây, `int` là số hàng được câu lệnh update tác động theo kết quả `executeUpdate()`. Entity `User` và các thuộc tính được dùng trong JPQL phải tồn tại đúng với mô hình entity của dự án.

## 5. Hai thuộc tính này không thay thế transaction

`@Modifying` cho Spring Data JPA biết rằng query khai báo bằng `@Query` là câu lệnh thay đổi dữ liệu, cần thực thi theo cơ chế modifying query. Hai thuộc tính flush/clear điều khiển persistence context quanh câu lệnh đó.

Chúng không tự mở transaction và không commit transaction.

Câu lệnh bulk update/delete cần được thực thi trong transaction. Có thể đặt `@Transactional` tại service để toàn bộ thao tác nghiệp vụ có một ranh giới transaction rõ ràng:

```java
import java.time.LocalDateTime;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserMaintenanceService {

    private final UserRepository userRepository;

    public UserMaintenanceService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @Transactional
    public int deactivateInactiveUsers(LocalDateTime cutoff) {
        return userRepository.deactivateInactiveUsers(cutoff);
    }
}
```

Khi service kết thúc thành công, transaction interceptor mới thực hiện commit theo transaction manager. Nếu có lỗi và rollback rule áp dụng, transaction có thể rollback. Flush chỉ đồng bộ SQL trong transaction; nó không làm dữ liệu trở nên bền vững độc lập với transaction.

Có thể đặt `@Transactional` trực tiếp trên repository query method nếu thiết kế ứng dụng yêu cầu. Tuy nhiên, đặt transaction ở service thường thuận tiện hơn khi một nghiệp vụ gồm nhiều thao tác repository cần được commit hoặc rollback cùng nhau.

## 6. So sánh giá trị mặc định và các cấu hình

Cả hai thuộc tính của `@Modifying` mặc định đều là `false`.

| Cấu hình | Trước khi chạy query | Sau khi chạy query | Tác động chính |
|---|---|---|---|
| Mặc định | Không yêu cầu Spring Data JPA flush tường minh | Không tự clear | Ít tác động lên persistence context; cần tự xử lý trạng thái stale nếu có |
| `flushAutomatically = true` | Flush các thay đổi đang chờ | Không tự clear | Bảo đảm thay đổi đang chờ được đồng bộ trước query |
| `clearAutomatically = true` | Không yêu cầu flush tường minh | Clear toàn bộ persistence context | Tránh tiếp tục dùng entity stale, nhưng có thể detach nhiều entity |
| Cả hai là `true` | Flush trước query | Clear sau query | Đồng bộ thay đổi đang chờ rồi loại entity managed khỏi context sau bulk operation |

Không có một cấu hình đúng cho mọi repository. Chọn theo trạng thái persistence context và các thao tác sẽ diễn ra sau bulk query.

## 7. Những lưu ý quan trọng khi dùng bulk update/delete

### Clear có thể làm mất thay đổi chưa flush

Đây là lỗi dễ gặp nhất khi bật `clearAutomatically` một mình.

Giả sử code đã thay đổi một entity managed nhưng thay đổi đó vẫn chưa được flush. Nếu bulk query chạy và sau đó `EntityManager.clear()` được gọi, các thay đổi chưa đồng bộ có thể bị bỏ khỏi persistence context.

Nếu các thay đổi đó phải được lưu trước bulk query, bật đồng thời `flushAutomatically = true`:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
```

Nếu không muốn flush toàn bộ persistence context, cân nhắc thiết kế transaction boundary khác hoặc chủ động flush/clear tại vị trí nghiệp vụ kiểm soát được.

### Bulk query bỏ qua dirty checking và vòng đời entity thông thường

JPQL bulk update/delete tác động trực tiếp lên database. Nó không lần lượt tải entity rồi gọi setter. Vì vậy, không nên kỳ vọng bulk query tự động:

- Gọi các entity lifecycle callback như `@PreUpdate`, `@PostUpdate`, `@PreRemove` hoặc `@PostRemove` cho từng entity.
- Thực hiện cascade remove/update như khi thao tác qua entity graph.
- Đồng bộ trạng thái vào các entity đang managed.
- Tự động áp dụng optimistic locking theo từng entity như thao tác cập nhật entity thông thường.

Nếu nghiệp vụ phụ thuộc lifecycle callback, cascade hoặc optimistic locking, hãy đánh giá việc tải và cập nhật entity theo từng đối tượng, hoặc tự triển khai đầy đủ các quy tắc tương ứng trong bulk query và transaction.

Đặc biệt, bulk update trên entity có trường `@Version` không nên được giả định là tự tăng version và kiểm tra version như dirty checking thông thường. Nếu cần bảo vệ cạnh tranh dữ liệu, phải thiết kế điều kiện version và cập nhật version một cách tường minh, hoặc dùng cơ chế cập nhật entity phù hợp.

### Flush không có nghĩa là commit

Sau `EntityManager.flush()`, SQL đã được gửi trong transaction hiện tại. Một lỗi xảy ra sau đó vẫn có thể làm toàn bộ transaction rollback. Không dùng flush như cách xác nhận dữ liệu đã commit.

### Clear không cập nhật object Java đang được giữ trong biến

Sau `clear()`, biến Java vẫn tham chiếu object cũ nhưng object đó detached. Clear không sửa các field của object thành giá trị database mới. Hãy tải lại entity nếu cần đọc trạng thái mới.

### Không nên dùng clear tự động nếu còn nhiều entity cần tiếp tục thao tác

Nếu service đang xử lý nhiều entity và sau bulk query vẫn cần cập nhật chúng, clear toàn bộ persistence context có thể làm các thao tác tiếp theo không còn được dirty checking. Khi chỉ một vài entity bị ảnh hưởng, cân nhắc dùng `EntityManager.refresh(entity)` cho entity vẫn managed, hoặc clear/tải lại tại một ranh giới phù hợp.

## 8. Ví dụ chọn cấu hình theo tình huống

| Tình huống | Cấu hình gợi ý | Lý do |
|---|---|---|
| Chỉ chạy bulk update, không có thay đổi đang chờ và không dùng lại entity managed | Có thể giữ mặc định | Không cần flush/clear bổ sung nếu không có rủi ro đồng bộ |
| Có thay đổi entity đang chờ và cần chúng được ghi trước bulk query | `flushAutomatically = true` | Flush trước khi chạy query |
| Sau bulk query cần đọc lại entity có thể đang managed | `clearAutomatically = true` hoặc tự refresh/clear có kiểm soát | Tránh đọc giá trị cũ từ persistence context |
| Có thay đổi đang chờ và sau bulk query cần loại bỏ entity stale | Cân nhắc bật cả hai | Flush trước, clear sau |
| Sau query vẫn cần tiếp tục dirty checking trên nhiều entity managed | Không bật clear tự động một cách tùy tiện | Clear làm tất cả entity managed thành detached |

### Một quy trình quyết định nhanh

Trước khi thêm hai thuộc tính, hãy trả lời ba câu hỏi:

1. Persistence context có thể có thay đổi chưa flush cần được ghi trước câu lệnh bulk không? Nếu có, cân nhắc `flushAutomatically = true`.
2. Sau câu lệnh bulk, code có thể tiếp tục đọc các entity đã được tải trước đó không? Nếu có, cần clear hoặc refresh để tránh stale state.
3. Sau query, code còn cần các entity đó ở trạng thái managed không? Nếu có, cân nhắc refresh từng entity hoặc tải lại có kiểm soát thay vì clear toàn bộ context.

## 9. Kiểm thử hành vi flush và clear

Nên kiểm thử bằng integration test có Spring Data JPA và database phù hợp, vì mục tiêu là xác minh sự phối hợp giữa repository proxy, EntityManager, transaction manager và provider JPA.

Một bài kiểm thử hữu ích có thể xác minh:

- Persist hoặc sửa một entity trong transaction nhưng chưa gọi flush thủ công.
- Gọi repository method có `flushAutomatically = true`, rồi xác nhận bulk query nhìn thấy dữ liệu cần thiết.
- Gọi method có `clearAutomatically = true`, rồi kiểm tra `EntityManager.contains(entity)` trả về `false` với entity trước đó đang managed.
- Tải lại entity qua repository và xác nhận giá trị đọc được phản ánh kết quả bulk update.
- Kiểm tra số hàng được cập nhật mà phương thức repository trả về.
- Kiểm tra rollback: nếu một lỗi xảy ra sau flush nhưng trước commit, các thay đổi vẫn phải rollback theo transaction.

Với `@DataJpaTest`, cần lưu ý test thường chạy trong transaction do framework quản lý. Nếu kiểm tra thời điểm commit hoặc hành vi transaction ở service, hãy thiết kế test để ranh giới transaction được thực thi đúng như production. Không chỉ kiểm tra object Java cũ vì sau clear object đó đã detached; hãy truy vấn lại dữ liệu.

## 10. Lỗi thường gặp

- **Quên `@Modifying`:** Spring Data JPA có thể xử lý query theo đường truy vấn đọc thay vì `executeUpdate()`; câu lệnh DML sẽ không được thực thi đúng cách. Thêm `@Modifying` cho phương thức `@Query` update/delete.
- **Nghĩ rằng `@Modifying` tự tạo transaction:** annotation này chọn cách thực thi query, không mở transaction. Đặt `@Transactional` ở service hoặc repository theo thiết kế.
- **Bật `clearAutomatically` mà không xem xét thay đổi đang chờ:** clear có thể loại bỏ thay đổi chưa flush. Nếu phải giữ các thay đổi đó, cân nhắc bật `flushAutomatically` cùng lúc.
- **Cho rằng clear chỉ ảnh hưởng hàng vừa update:** `EntityManager.clear()` detach toàn bộ entity đang managed trong persistence context hiện tại.
- **Tiếp tục dùng object sau clear như entity managed:** object vẫn tồn tại nhưng đã detached; hãy tải lại hoặc quản lý lại theo cách phù hợp.
- **Cho rằng flush là commit:** flush chỉ đồng bộ SQL trong transaction. Commit/rollback vẫn do transaction manager điều khiển.
- **Mong bulk query gọi callback hoặc cascade:** bulk DML bỏ qua quy trình cập nhật entity thông thường. Hãy tự xử lý nghiệp vụ cần thiết hoặc dùng thao tác entity theo từng đối tượng.

## Kết luận

`flushAutomatically` điều khiển việc đồng bộ thay đổi đang chờ trước modifying query; `clearAutomatically` điều khiển việc loại bỏ toàn bộ entity managed khỏi persistence context sau query. Dùng flush khi cần bảo đảm thứ tự ghi xuống database, dùng clear khi cần tránh stale entity sau bulk update/delete, và kết hợp cả hai khi nghiệp vụ cần cả hai hành vi.

Luôn đặt modifying query trong transaction phù hợp và nhớ rằng flush không commit, clear không cập nhật object Java cũ, còn bulk update/delete không đi qua dirty checking và lifecycle của từng entity.
