# Yêu cầu giao dịch cho truy vấn thay đổi dữ liệu trong Spring Data JPA

Khi dùng Spring Data JPA để thực hiện truy vấn `UPDATE` hoặc `DELETE` trực tiếp bằng JPQL hay SQL, ứng dụng phải chạy truy vấn trong một transaction đang hoạt động. Annotation `@Modifying` cho Spring Data biết một phương thức `@Query` là truy vấn thay đổi dữ liệu; annotation này **không tự mở transaction**. Trách nhiệm tạo ranh giới transaction thuộc về `@Transactional` hoặc một transaction đang bao quanh lời gọi.

Bài này tập trung vào các truy vấn bulk DML được khai báo trong repository, cách đặt transaction ở tầng service, ảnh hưởng của flush/clear đến persistence context và những lỗi thường gặp khi chạy truy vấn thay đổi dữ liệu.

> Các đoạn Java dưới đây là snippet dành cho một dự án Java 17+ dùng Spring Boot 3+ và `spring-boot-starter-data-jpa`. Chúng minh họa các lớp và phương thức cần tích hợp vào ứng dụng, không phải các chương trình độc lập có thể chạy trực tiếp bằng `javac`/`java`.

## 1. Vì sao truy vấn thay đổi dữ liệu cần transaction?

Transaction gom một hoặc nhiều thao tác cơ sở dữ liệu thành một đơn vị công việc. Với một transaction, ứng dụng có thể đảm bảo các thay đổi liên quan được commit cùng nhau hoặc rollback khi công việc thất bại.

Một truy vấn `UPDATE` hoặc `DELETE` thay đổi trạng thái dữ liệu. JPA yêu cầu các thao tác ghi này được thực hiện trong transaction. Nếu gọi truy vấn DML khi không có transaction phù hợp, provider có thể ném `jakarta.persistence.TransactionRequiredException` hoặc lỗi tương ứng được Spring dịch sang exception khác.

Transaction còn giúp kết hợp truy vấn bulk với các bước nghiệp vụ khác. Ví dụ, khi vô hiệu hóa tài khoản và ghi lịch sử thay đổi, cả hai thao tác nên nằm trong cùng một transaction nếu nghiệp vụ yêu cầu chúng cùng thành công hoặc cùng thất bại.

Một phương thức service có `@Transactional` thường là nơi phù hợp để xác định ranh giới đó. Transaction bắt đầu khi lời gọi đi qua Spring proxy, các thao tác bên trong tham gia transaction, và transaction được commit khi phương thức kết thúc thành công. Nếu phát sinh exception thuộc quy tắc rollback, transaction sẽ rollback.

## 2. Phân biệt @Modifying và @Transactional

Hai annotation có vai trò khác nhau:

| Annotation | Vai trò |
|---|---|
| `@Modifying` | Đánh dấu phương thức `@Query` là truy vấn thay đổi dữ liệu để Spring Data JPA thực thi theo chế độ modifying. |
| `@Transactional` | Xác định transaction bao quanh thao tác, bao gồm thời điểm bắt đầu, propagation, read-only và quy tắc rollback. |

Một phương thức repository khai báo JPQL `UPDATE` hoặc `DELETE` cần `@Modifying`. Nhưng `@Modifying` không thay thế `@Transactional`.

Ví dụ repository:

```java
import java.time.Instant;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AccountRepository
        extends JpaRepository<Account, Long> {

    @Modifying
    @Query("""
        update Account a
           set a.enabled = false
         where a.lastLoginAt < :cutoff
           and a.enabled = true
        """)
    int disableInactiveAccounts(@Param("cutoff") Instant cutoff);
}
```

Đây là một phương thức truy vấn được khai báo tường minh. Các query method tự khai báo như phương thức trên không mặc nhiên có cấu hình transaction giống các phương thức CRUD kế thừa từ `JpaRepository`. Vì vậy, hãy đặt `@Transactional` ở service gọi phương thức hoặc trực tiếp trên phương thức repository.

## 3. Đặt transaction ở tầng service

Đặt transaction ở service giúp một use case có thể bao gồm nhiều thao tác repository trong cùng một đơn vị công việc. Ví dụ:

```java
import java.time.Instant;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountMaintenanceService {

    private final AccountRepository accountRepository;
    private final AuditRepository auditRepository;

    public AccountMaintenanceService(
            AccountRepository accountRepository,
            AuditRepository auditRepository) {
        this.accountRepository = accountRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public int disableInactiveAccounts(Instant cutoff) {
        int affected = accountRepository.disableInactiveAccounts(cutoff);

        if (affected > 0) {
            auditRepository.save(
                    new AuditEntry("DISABLE_INACTIVE_ACCOUNTS", affected));
        }

        return affected;
    }
}
```

Khi phương thức service được gọi qua Spring bean proxy:

1. Spring bắt đầu transaction theo cấu hình `@Transactional`.
2. Repository thực thi câu lệnh bulk update trong transaction hiện tại.
3. Nếu có bản ghi bị ảnh hưởng, service ghi thêm audit entry trong cùng transaction.
4. Khi phương thức kết thúc bình thường, Spring commit transaction.
5. Nếu một thao tác phát sinh lỗi khiến transaction rollback, thay đổi từ truy vấn update và audit entry cùng bị rollback.

Mặc định, `@Transactional` dùng propagation `REQUIRED`. Nếu đã có transaction, lời gọi tham gia transaction đó; nếu chưa có, Spring tạo transaction mới. Đây thường là lựa chọn phù hợp cho một use case nghiệp vụ.

Nếu muốn transaction bắt đầu ngay ở repository, có thể khai báo:

```java
@Modifying
@Transactional
@Query("""
    update Account a
       set a.enabled = false
     where a.id = :id
    """)
int disableAccount(@Param("id") Long id);
```

Cách này hợp lệ cho một thao tác đơn giản. Tuy nhiên, nếu use case gồm nhiều repository hoặc cần phối hợp với kiểm tra nghiệp vụ, transaction ở service giúp thể hiện rõ phạm vi nguyên tử của toàn bộ công việc. Tránh tạo các transaction riêng lẻ ngoài ý muốn khiến một phần nghiệp vụ đã commit trong khi phần còn lại thất bại.

## 4. Gọi truy vấn thay đổi trong transaction chỉ đọc

Không nên gọi modifying query bên trong một transaction được đánh dấu `@Transactional(readOnly = true)`.

```java
@Transactional(readOnly = true)
public void maintenance() {
    // Không gọi bulk UPDATE/DELETE trong transaction này.
}
```

Thuộc tính `readOnly` là gợi ý tối ưu cho transaction chỉ đọc. Tùy transaction manager, JPA provider và hệ quản trị cơ sở dữ liệu, nó có thể ảnh hưởng flush mode hoặc thiết lập chế độ chỉ đọc ở kết nối. Nó không phải cơ chế bảo vệ giống nhau ở mọi môi trường, nhưng không được dùng làm transaction ghi.

Hãy khai báo transaction ghi ở ranh giới service:

```java
@Transactional
public int updateAccountStatus(Long id) {
    return accountRepository.disableAccount(id);
}
```

Lưu ý: propagation mặc định `REQUIRED` sẽ tham gia transaction bên ngoài nếu đã tồn tại. Nếu service bên ngoài đang chạy trong transaction `readOnly = true`, một lời gọi bên trong không tự động biến transaction hiện tại thành transaction ghi chỉ bằng cách đặt `readOnly = false` ở phương thức được gọi. Hãy thiết kế ranh giới transaction của use case ở tầng ngoài cho đúng mục đích ghi dữ liệu.

## 5. Bulk DML và persistence context

Truy vấn bulk JPQL được thực thi trực tiếp trên cơ sở dữ liệu. Nó không tải từng entity rồi gọi setter, vì vậy không đi qua quy trình dirty checking thông thường của các entity đang được quản lý.

Điều này có một hệ quả quan trọng: nếu persistence context đang giữ một entity `Account` với `enabled = true`, sau khi bulk query cập nhật cột thành `false`, object trong bộ nhớ có thể vẫn giữ giá trị `true`. Persistence context đã trở nên cũ so với cơ sở dữ liệu.

Ví dụ:

1. Service tải `Account` số 10 vào persistence context.
2. Một modifying query đặt `enabled = false` cho tài khoản đó.
3. Entity đã tải trước đó vẫn có thể hiển thị `enabled = true` trong bộ nhớ.
4. Nếu tiếp tục dùng entity cũ, logic nghiệp vụ có thể đọc trạng thái không còn đúng.

`@Modifying` cung cấp hai tùy chọn:

- `flushAutomatically = true`: yêu cầu flush persistence context trước khi chạy truy vấn modifying.
- `clearAutomatically = true`: yêu cầu clear persistence context sau khi truy vấn thực thi.

Ví dụ:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    update Account a
       set a.enabled = false
     where a.lastLoginAt < :cutoff
    """)
int disableInactiveAccounts(@Param("cutoff") Instant cutoff);
```

Hai thuộc tính này mặc định là `false`. Chỉ bật khi phù hợp với cách service sử dụng persistence context:

- Flush trước truy vấn giúp đồng bộ các thay đổi entity đang chờ xuống database trước khi bulk DML chạy.
- Clear sau truy vấn loại bỏ các entity đang được quản lý khỏi persistence context để tránh tiếp tục dùng trạng thái cũ.
- `clear()` ảnh hưởng toàn bộ persistence context hiện tại, không chỉ entity bị truy vấn cập nhật. Các entity đã tải trước đó sẽ trở thành detached.
- Nếu clear khi còn thay đổi chưa flush, các thay đổi đang chờ có thể bị mất khỏi persistence context. Vì vậy, cần cân nhắc `flushAutomatically = true` khi bật clear và có pending changes.
- Sau khi clear, nếu cần dữ liệu mới, hãy truy vấn lại entity hoặc dùng `EntityManager.refresh()` cho entity phù hợp.

Không cần bật cả hai thuộc tính cho mọi modifying query. Nếu service không giữ entity liên quan trong persistence context hoặc không cần dùng lại chúng sau truy vấn, cấu hình mặc định có thể đủ.

## 6. Transaction, rollback và exception

Mặc định, Spring rollback transaction khi phương thức transactional ném `RuntimeException` hoặc `Error`. Checked exception không tự động kích hoạt rollback theo quy tắc mặc định.

Nếu nghiệp vụ cần rollback khi một checked exception được ném ra, khai báo rõ:

```java
@Transactional(rollbackFor = Exception.class)
public void updateAndRecord() throws Exception {
    accountRepository.disableInactiveAccounts(Instant.now());
    auditRepository.save(new AuditEntry("MAINTENANCE", 1));
    // Một checked exception tại đây sẽ kích hoạt rollback theo cấu hình.
}
```

Không nên bắt exception của truy vấn rồi bỏ qua và tiếp tục coi transaction là thành công. Một số lỗi persistence khiến transaction bị đánh dấu rollback-only. Khi đó, dù phương thức không ném lỗi ra ngoài, Spring vẫn có thể rollback lúc commit và báo `UnexpectedRollbackException`.

Nếu cần chuyển exception thành phản hồi nghiệp vụ, hãy để transaction kết thúc theo đúng trạng thái trước rồi xử lý ở tầng gọi bên ngoài, hoặc chủ động đánh dấu rollback khi bắt buộc phải bắt exception bên trong.

`@Transactional` hoạt động thông qua proxy trong cấu hình mặc định của Spring. Gọi một phương thức transactional khác bằng `this.someMethod()` trong cùng object (self-invocation) thường không đi qua proxy, do đó annotation ở phương thức được gọi có thể không được áp dụng như mong đợi. Hãy gọi qua Spring bean phù hợp hoặc tổ chức lại ranh giới service. Transaction gắn với luồng thực thi hiện tại; không giả định nó tự truyền sang một thread mới được tạo bởi `@Async` hoặc executor.

## 7. Truy vấn DELETE, native query và số hàng bị ảnh hưởng

Nguyên tắc transaction tương tự áp dụng cho bulk delete:

```java
@Modifying
@Query("""
    delete from Account a
     where a.enabled = false
       and a.lastLoginAt < :cutoff
    """)
int deleteDisabledAccounts(@Param("cutoff") Instant cutoff);
```

JPQL bulk delete xóa trực tiếp các hàng thỏa điều kiện. Nó không tương đương với việc tải từng entity rồi gọi `repository.delete(entity)`. Các callback vòng đời entity, cascade ở cấp ORM và `orphanRemoval` không được thực thi theo cùng cách như thao tác xóa từng entity. Nếu nghiệp vụ phụ thuộc vào các hành vi đó, hãy cân nhắc xóa entity theo quy trình phù hợp hoặc thiết kế cascade/ràng buộc ở cơ sở dữ liệu.

Với native query, cũng dùng `@Modifying` cho phương thức `@Query(nativeQuery = true)` thực hiện DML, đồng thời bảo đảm có transaction ghi đang hoạt động. Cần kiểm tra cú pháp, tên bảng/cột và hành vi theo hệ quản trị cơ sở dữ liệu.

Giá trị trả về kiểu `int` cho biết số hàng được truy vấn cập nhật hoặc xóa. Có thể dùng kết quả này để kiểm tra điều kiện nghiệp vụ, ví dụ không tìm thấy bản ghi cần cập nhật:

```java
@Transactional
public void disableAccount(Long id) {
    int affected = accountRepository.disableAccount(id);

    if (affected == 0) {
        throw new IllegalArgumentException(
                "Không tìm thấy tài khoản hoặc trạng thái không phù hợp");
    }
}
```

Cần diễn giải số hàng bị ảnh hưởng theo điều kiện truy vấn. Kết quả 0 có thể do bản ghi không tồn tại hoặc không thỏa điều kiện `WHERE`; không phải lúc nào cũng chỉ có một nguyên nhân.

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `TransactionRequiredException` khi chạy update/delete | Không có transaction ghi đang hoạt động | Bao quanh lời gọi bằng `@Transactional` |
| Truy vấn `@Query` update bị xử lý như truy vấn đọc | Thiếu `@Modifying` | Thêm `@Modifying` vào phương thức repository |
| Có `@Modifying` nhưng vẫn lỗi transaction | Nhầm rằng `@Modifying` tự mở transaction | Thêm transaction ở service hoặc repository |
| Entity trong bộ nhớ vẫn mang giá trị cũ | Bulk DML không đồng bộ persistence context | Refresh entity hoặc cân nhắc `clearAutomatically` |
| Thay đổi đang chờ biến mất sau clear | Persistence context bị clear trước khi pending changes được flush | Cân nhắc `flushAutomatically = true` trước clear |
| Một phần use case đã commit dù bước sau thất bại | Các thao tác nằm trong transaction khác nhau | Đặt transaction ở service bao trọn use case |
| Transaction không rollback như mong đợi | Checked exception không nằm trong quy tắc rollback mặc định hoặc exception đã bị nuốt | Dùng `rollbackFor` phù hợp và không bỏ qua lỗi persistence |
| `@Transactional` dường như không có tác dụng | Lời gọi self-invocation không đi qua proxy hoặc gọi object ngoài Spring container | Kiểm tra cách tạo bean và đường gọi qua proxy |

## 9. Checklist triển khai

- Phương thức repository dùng `@Query` để update/delete đã được đánh dấu `@Modifying`.
- Lời gọi modifying query chạy trong transaction ghi đang hoạt động.
- Transaction được đặt ở service khi một use case cần phối hợp nhiều thao tác repository.
- Không gọi modifying query bên trong transaction chỉ đọc.
- Hiểu rõ `flushAutomatically` và `clearAutomatically` trước khi bật chúng.
- Không tiếp tục dùng entity có thể đã stale sau bulk DML; refresh hoặc tải lại khi cần.
- Đã xác định quy tắc rollback cho exception của nghiệp vụ.
- Đã kiểm thử cả trường hợp cập nhật thành công, không có hàng phù hợp và lỗi giữa các bước trong transaction.
- Với bulk delete/native query, đã đánh giá callback, cascade, persistence context và sự khác biệt theo database.

Khi sử dụng truy vấn thay đổi dữ liệu trong Spring Data JPA, hãy xem `@Modifying` là chỉ dẫn về loại truy vấn và `@Transactional` là ranh giới bảo đảm tính nguyên tử. Kết hợp đúng hai cơ chế, đồng thời quản lý persistence context sau bulk DML, giúp dữ liệu và trạng thái entity trong ứng dụng nhất quán hơn.