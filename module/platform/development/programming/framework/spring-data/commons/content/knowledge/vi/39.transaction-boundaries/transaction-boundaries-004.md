# CRUD, query method và phương thức tùy chỉnh có thể khác cấu hình

## 1. Cùng repository chưa chắc cùng ranh giới giao dịch

Trong chương **Ranh giới giao dịch** của module **SPRING_DATA_COMMONS**, cần phân biệt API repository dùng chung với chính sách giao dịch của module lưu trữ. Một interface có thể ghép CRUD kế thừa, derived query, truy vấn khai báo và fragment tự viết. Những phương thức đó có thể lấy cấu hình giao dịch từ các nơi khác nhau.

Ví dụ, hai lời gọi sau cùng trả về tài khoản nhưng không nhất thiết tự mở transaction theo cùng một cách:

~~~java
repository.findById(id);             // CRUD kế thừa
repository.findByDisplayName(name);   // Query method do ứng dụng khai báo
~~~

Tên bắt đầu bằng `find` mô tả ý định truy vấn; nó không phải quy tắc chung để Spring tự gán `readOnly = true`. Tương tự, tên bắt đầu bằng `save` không chứng minh một implementation tùy chỉnh đã tham gia đúng transaction.

Bài học dùng **Java 17, Spring Data JPA 3.5 và Spring Framework 6.2** để minh họa cụ thể. Những kết luận về implementation JPA được ghi rõ phạm vi; không mặc định áp dụng chúng cho mọi repository của Commons.

Sau bài này, bạn có thể:

- Xác định phương thức được thực thi bởi base implementation, query infrastructure hay fragment.
- Khai báo giao dịch cho query method và phương thức tự viết.
- Phân biệt cấu hình tại repository với giao dịch đang bao quanh lời gọi.
- Chọn ranh giới ở service khi nhiều thao tác phải thành công hoặc thất bại cùng nhau.

## 2. Nhận diện nguồn cấu hình trước khi đọc annotation

Với JPA mặc định, `SimpleJpaRepository` cung cấp implementation cho các thao tác CRUD. Lớp này có cấu hình đọc; các phương thức ghi có cấu hình riêng. Đây là hành vi của implementation JPA, không phải hợp đồng rằng mọi implementation của `CrudRepository` đều giống nhau. Xem [API SimpleJpaRepository 3.5](https://docs.spring.io/spring-data/jpa/docs/3.5.x/api/org/springframework/data/jpa/repository/support/SimpleJpaRepository.html).

| Loại phương thức | Ví dụ | Điểm cần xem |
| --- | --- | --- |
| CRUD kế thừa | `findById`, `save`, `deleteById` | Mặc định của base implementation trong module đang dùng |
| CRUD được khai báo lại | `findAll` có `@Override` | Annotation ở khai báo mới và cấu hình mặc định còn hiệu lực |
| Derived query | `findByActiveFalse` | Cấu hình do ứng dụng khai báo hoặc transaction bên ngoài |
| Query khai báo | Method có `@Query` | Cách thực thi query và cấu hình giao dịch là hai vấn đề riêng |
| Default method | Method có thân trong interface | Cấu hình cho toàn bộ method, ngoài cấu hình của các lời gọi bên trong |
| Fragment tùy chỉnh | `renameInactive` | Implementation thực tế, annotation và tài nguyên mà fragment sử dụng |

Luồng suy luận hữu ích:

~~~text
Lời gọi từ ứng dụng
        |
        v
Có đi qua proxy phù hợp không?
        |
        v
Phương thức được route tới implementation nào?
        |
        v
Có metadata giao dịch áp dụng cho lời gọi không?
        |
        v
Transaction manager nào được chọn?
        |
        v
Tạo giao dịch mới hay tham gia giao dịch đã có?
        |
        v
Thực thi -> hoàn tất / đánh dấu rollback / rollback
~~~

Không có metadata tự mở transaction trên một query method không đồng nghĩa truy vấn chắc chắn nằm ngoài mọi transaction. Khi service đã mở giao dịch phù hợp, truy vấn vẫn có thể sử dụng tài nguyên được liên kết với giao dịch đó.

## 3. Phân biệt CRUD kế thừa và query method do ứng dụng khai báo

### 3.1. Mặc định của JPA

Trong cấu hình JPA thông thường:

- CRUD đọc kế thừa có cấu hình `readOnly = true`.
- CRUD ghi kế thừa dùng `@Transactional` với mặc định thông thường.
- Query method do ứng dụng khai báo, kể cả default method, không tự nhận cấu hình giao dịch chỉ vì nằm trong interface repository.

Các quy tắc này được mô tả trong [Transactionality của Spring Data JPA 3.5](https://docs.spring.io/spring-data/jpa/reference/3.5/jpa/transactions.html).

Ví dụ cần phân biệt:

~~~java
public interface AccountLookup
        extends CrudRepository<Account, Long> {

    List<Account> findByDisplayName(String displayName);
}
~~~

Ở đây, `findById` kế thừa đi theo đường CRUD. `findByDisplayName` là query method mới. Việc query trả về `List<Account>` không tự cung cấp một ranh giới giao dịch bao quanh các bước xử lý tiếp theo.

Nếu caller đọc danh sách rồi cập nhật từng tài khoản, cần quyết định giao dịch cho cả công việc. Cấu hình của lần đọc đầu tiên không tự bao phủ vòng lặp chạy sau khi method đó đã trả về.

### 3.2. Khai báo rõ cho query đọc

Có thể đặt cấu hình tại từng phương thức:

~~~java
import java.util.List;
import org.springframework.data.repository.CrudRepository;
import org.springframework.transaction.annotation.Transactional;

public interface AccountLookup
        extends CrudRepository<Account, Long> {

    @Transactional(readOnly = true)
    List<Account> findByDisplayName(String displayName);
}
~~~

Hai đoạn `AccountLookup` là phiên bản trước và sau của cùng ví dụ, không phải hai interface cần đăng ký đồng thời.

Nếu dùng mặc định ở cấp interface, cần rà các phương thức ghi để chúng có chính sách phù hợp. Bài này chọn annotation ở từng query method nhằm làm rõ ý định tại nơi khai báo.

Phân trang, sắp xếp, projection hay Query by Example mô tả cách chọn và biểu diễn dữ liệu. Chúng không thay thế quyết định về ranh giới giao dịch của công việc sử dụng dữ liệu đó.

## 4. Mô hình dùng cho ví dụ thực hành

Các public type dưới đây được đặt trong các file Java riêng, cùng package `example.accounts`. Chúng là ví dụ cho một ứng dụng JPA đã cấu hình quét entity, repository, kết nối backend và transaction manager phù hợp.

~~~java
package example.accounts;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "account_records")
public class Account {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private String displayName;

    private boolean active;

    @Version
    private Long version;

    protected Account() {
    }

    public Account(String displayName, boolean active) {
        rename(displayName);
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public boolean isActive() {
        return active;
    }

    public void rename(String displayName) {
        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException(
                    "Tên hiển thị không được rỗng");
        }
        this.displayName = displayName;
    }

    public void activate() {
        this.active = true;
    }
}
~~~

`@Version` phục vụ kiểm soát cập nhật đồng thời của ví dụ JPA. Nó không tự tạo một transaction cho chuỗi lời gọi repository.

Không cần thêm auditing chỉ để quan sát transaction. Nếu ứng dụng đã có auditing, thời điểm callback và thông tin auditor vẫn là phần phải cấu hình riêng.

## 5. Một repository có nhiều cấu hình hợp lệ

### 5.1. Repository hoàn chỉnh

`AccountMaintenance` trong ví dụ được định nghĩa ở mục 7.

~~~java
package example.accounts;

import java.util.List;

import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface AccountRepository
        extends CrudRepository<Account, Long>, AccountMaintenance {

    @Override
    @Transactional(readOnly = true, timeout = 5)
    Iterable<Account> findAll();

    @Transactional(readOnly = true)
    List<Account> findByActiveFalse();

    @Transactional(readOnly = true)
    long countByActiveFalse();

    @Modifying(
            flushAutomatically = true,
            clearAutomatically = true)
    @Transactional
    @Query("""
            update Account a
               set a.active = false
             where a.id = :id
            """)
    int deactivateById(@Param("id") Long id);

    @Transactional
    default boolean activateIfPresent(Long id) {
        var result = findById(id);

        if (result.isEmpty()) {
            return false;
        }

        Account account = result.get();
        account.activate();
        save(account);
        return true;
    }
}
~~~

Các method thể hiện những lựa chọn khác nhau:

| Method | Ý định của cấu hình đã khai báo |
| --- | --- |
| `findAll` | Đọc, có timeout 5 giây khi thiết lập giao dịch mới theo chính sách hỗ trợ |
| `findByActiveFalse` | Query đọc có ranh giới giao dịch tường minh |
| `countByActiveFalse` | Query đọc trả số lượng |
| `deactivateById` | Query cập nhật, dùng transaction ghi |
| `activateIfPresent` | Bao quanh cả bước tìm và lưu trong default method |
| `renameInactive` | Thực thi bằng fragment có chính sách riêng ở mục 7 |

`timeout` là cấu hình giao dịch, không phải bảo đảm một đồng hồ sẽ cắt mọi đoạn Java đúng giây thứ năm. Hiệu lực cụ thể còn phụ thuộc transaction manager và tài nguyên. Xem [API @Transactional 6.2](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html).

### 5.2. Khai báo lại CRUD phải nêu đủ ý định

Một biến thể dễ gây hiểu nhầm là:

~~~java
@Override
@Transactional(timeout = 5)
Iterable<Account> findAll();
~~~

Không nên hiểu annotation này là “giữ mọi thuộc tính cũ rồi thêm timeout”. `readOnly` của annotation mới có mặc định là `false`.

Nếu mục tiêu vẫn là giao dịch đọc có timeout, khai báo rõ:

~~~java
@Override
@Transactional(readOnly = true, timeout = 5)
Iterable<Account> findAll();
~~~

Giữ đúng chữ ký CRUD cũng quan trọng. Một overload mới như `findAll(String category)` không tự trở thành phương thức CRUD chỉ vì trùng tên.

## 6. Query cập nhật và default method cần ranh giới riêng

### 6.1. @Modifying không thay cho @Transactional

Trong `deactivateById`, mỗi annotation có một trách nhiệm:

- `@Query`: biểu thức JPQL cần chạy.
- `@Modifying`: yêu cầu JPA query infrastructure thực thi query như thao tác thay đổi dữ liệu.
- `@Transactional`: metadata để hạ tầng giao dịch áp dụng chính sách transaction.

Chỉ có `@Modifying` không tự tạo một transaction ghi. Nếu không có giao dịch thích hợp từ method hoặc caller, thao tác có thể thất bại lúc thực thi.

Các cờ flush/clear trong ví dụ xử lý quan hệ với persistence context: flush trước query và clear sau query. Clear làm các entity đang được quản lý trở thành detached; không tiếp tục giả định chúng phản ánh trạng thái mới.

Bulk JPQL cũng khác vòng lặp gọi thao tác trên từng entity. Không mặc định nó thực hiện callback hoặc cập nhật version như đường lưu entity thông thường. Xem [Modifying Queries của Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/3.5/jpa/query-methods.html#jpa.modifying-queries).

### 6.2. Tên delete không làm mọi cơ chế giống nhau

Một derived delete như:

~~~java
@Transactional
long deleteByActiveFalse();
~~~

khác method có `@Modifying` và JPQL bulk delete. Cần xem cả metadata transaction lẫn cách module thực hiện xóa. Không thêm `@Modifying` theo thói quen vào mọi method có tên `delete...`.

Trong ví dụ thực hành chính, thao tác deactivate chỉ đổi cờ active, không xóa tài khoản.

### 6.3. Transaction của method con không tự ghép thành một công việc

Default method `activateIfPresent` gồm:

~~~text
findById -> kiểm tra tồn tại -> sửa trạng thái -> save
~~~

Nếu chỉ dựa vào giao dịch riêng của từng CRUD method, không thể suy rằng toàn bộ đoạn trên đã có một giao dịch chung. Annotation trên default method biểu đạt ranh giới cho cả thao tác khi được gọi qua repository proxy.

Đây chỉ là thao tác nhỏ minh họa. Khi logic gồm nhiều repository, kiểm tra quyền hoặc quy tắc nghiệp vụ, đặt ranh giới ở service giúp caller thấy rõ công việc cần được bảo vệ.

## 7. Fragment tùy chỉnh có thể cung cấp cấu hình khác

### 7.1. Khai báo fragment

~~~java
package example.accounts;

public interface AccountMaintenance {

    int renameInactive(String suffix);
}
~~~

Implementation theo quy ước postfix `Impl`:

~~~java
package example.accounts;

import java.util.List;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

import org.springframework.transaction.annotation.Transactional;

public class AccountMaintenanceImpl
        implements AccountMaintenance {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    @Transactional(timeout = 15)
    public int renameInactive(String suffix) {
        if (suffix == null || suffix.isBlank()) {
            throw new IllegalArgumentException(
                    "Hậu tố không được rỗng");
        }

        List<Account> accounts = entityManager.createQuery(
                "select a from Account a where a.active = false",
                Account.class)
                .getResultList();

        for (Account account : accounts) {
            account.rename(account.getDisplayName() + suffix);
        }

        entityManager.flush();
        return accounts.size();
    }
}
~~~

Fragment được phát hiện theo cấu hình repository và ghép vào `AccountRepository`. Quy ước mặc định cùng cơ chế kết hợp fragment được mô tả trong [Custom Repository Implementations của Commons](https://docs.spring.io/spring-data/commons/reference/3.5/repositories/custom-implementations.html).

Ví dụ dùng entity do `EntityManager` truy vấn trong giao dịch JPA, rồi cập nhật qua dirty checking. Đây là lựa chọn JPA cho implementation này. Khi viết fragment cho store khác, cần dùng API lưu và mô hình cập nhật tương ứng.

`flush()` yêu cầu đồng bộ các thay đổi đang chờ với backend trong transaction; nó không kết thúc hay commit giao dịch.

### 7.2. Gọi đúng đường được quản lý

Caller sử dụng:

~~~java
int changed = accountRepository.renameInactive(" - reviewed");
~~~

Không tự `new AccountMaintenanceImpl()` rồi kỳ vọng field `EntityManager` được inject và annotation transaction có hiệu lực.

Cũng không suy từ việc fragment nằm trong repository rằng mọi tài nguyên nó sử dụng tự tham gia cùng transaction. Nếu implementation gọi thêm một HTTP API, lời gọi HTTP không tự rollback cùng thay đổi JPA.

### 7.3. Thay implementation cũng có thể thay chính sách

Fragment có thể đóng góp chữ ký trùng với method của base repository. Khi tùy chỉnh như vậy, phải xem lại cả hành vi lưu lẫn metadata giao dịch; không chỉ giữ tên `save` rồi coi chính sách cũ vẫn được bảo toàn.

Không nên cấu hình mâu thuẫn ở nhiều nơi để dựa vào phỏng đoán thứ tự ưu tiên. Hãy chọn nơi thể hiện chính sách rõ ràng và quan sát lời gọi thực tế qua repository.

## 8. Transaction ở service quyết định công việc bao quanh

### 8.1. Bao quanh cả bước đọc và nhiều lần lưu

~~~java
package example.accounts;

import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountService {

    private final AccountRepository repository;

    public AccountService(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int activateAllInactive() {
        List<Account> accounts = repository.findByActiveFalse();

        for (Account account : accounts) {
            account.activate();
            repository.save(account);
        }

        return accounts.size();
    }

    @Transactional(readOnly = true)
    public long countInactive() {
        return repository.countByActiveFalse();
    }
}
~~~

Với cùng transaction manager và tài nguyên JPA, các lời gọi trong `activateAllInactive` tham gia công việc được mở ở service. Nếu một lỗi thỏa quy tắc rollback thoát khỏi ranh giới này, mục tiêu là rollback các thay đổi thuộc giao dịch đó.

Nếu bỏ transaction ở service, không được suy rằng các lần `save` độc lập vẫn tạo một thao tác nguyên tử cho cả danh sách. Lần lưu trước có thể hoàn tất trước khi lần lưu sau gặp lỗi.

Ví dụ chọn tập dữ liệu nhỏ. Với khối lượng lớn, cần thiết kế chunk, thời gian giữ transaction và chiến lược cập nhật phù hợp thay vì kéo dài vòng lặp không giới hạn.

### 8.2. REQUIRED thường tham gia giao dịch đã có

`@Transactional` dùng propagation `REQUIRED` nếu không cấu hình khác. Khi đã có giao dịch tương thích, lời gọi bên trong thường tham gia giao dịch đó; nó không tự mở một giao dịch vật lý mới chỉ vì có thêm annotation.

| Caller bên ngoài | Method bên trong | Cách hiểu trong ví dụ cùng manager |
| --- | --- | --- |
| Chưa có transaction | Query được gắn `readOnly = true` | Có thể tạo giao dịch đọc mới |
| Service đang có transaction ghi | Query đọc dùng `REQUIRED` | Tham gia giao dịch ghi đang có |
| Service đang có transaction đọc | Method ghi dùng `REQUIRED` | Không tự nâng giao dịch ngoài thành giao dịch ghi |
| Service đang có transaction | Fragment có timeout riêng, dùng `REQUIRED` | Không tự thay timeout của giao dịch vật lý đã bắt đầu |

Chi tiết tham gia, kiểm tra tương thích và các propagation khác được mô tả trong [Transaction Propagation của Spring Framework 6.2](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html).

Ví dụ dễ sai:

~~~java
@Transactional(readOnly = true)
public void deactivateFromReadFlow(Long id) {
    repository.deactivateById(id);
}
~~~

Annotation ghi tại `deactivateById` không phải công tắc đổi chế độ của transaction bên ngoài. Cần đặt ranh giới ghi phù hợp cho công việc, thay vì trông chờ method bên trong sửa lại giao dịch đã mở.

`REQUIRES_NEW` có ngữ nghĩa độc lập khác và cần được chọn theo yêu cầu nghiệp vụ. Không thêm nó chỉ để làm biến mất xung đột cấu hình.

### 8.3. readOnly không phải hàng rào cấm ghi chung

Cờ `readOnly` có thể được truyền xuống hạ tầng như gợi ý và ảnh hưởng cơ chế tối ưu. Tùy backend, cấu hình hoặc provider, ghi trong giao dịch đọc có thể bị từ chối hoặc có kết quả không như dự kiến.

Ứng dụng cần phân loại luồng đọc/ghi ở thiết kế. Không dùng cờ này làm cơ chế phân quyền hay thay cho validation nghiệp vụ.

## 9. Những điều kiện khiến annotation có hoặc không có hiệu lực

### 9.1. Phải có hạ tầng transaction

Các ví dụ giả định ứng dụng có transaction manager đúng tài nguyên và đã bật xử lý annotation cho service, bằng cấu hình phù hợp của nền tảng hoặc `@EnableTransactionManagement`.

Một annotation nằm trong source chưa đủ chứng minh lời gọi thực tế đã được intercept. Với proxy mode thông thường, lời gọi từ bên ngoài qua proxy là điểm quan trọng. Ví dụ một service gọi `this.activateAllInactive()` không tự tạo interception mới cho method đích.

Quy tắc này cần phân biệt với cách repository proxy route default method và fragment; không áp một kết luận về self-invocation của service cho mọi đường gọi nội bộ của repository. Xem [Using @Transactional của Framework 6.2](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html).

### 9.2. Kiểm tra cấu hình repository mặc định có bị tắt không

JPA có tùy chọn `enableDefaultTransactions` trong `@EnableJpaRepositories`. Nếu ứng dụng đã tắt nó, không tiếp tục dựa vào các mặc định CRUD được mô tả cho cấu hình thông thường.

Ví dụ cấu hình cần nhận diện khi đọc một dự án:

~~~java
@EnableJpaRepositories(
        basePackageClasses = AccountRepository.class,
        enableDefaultTransactions = false)
~~~

Đây là minh họa một tùy chọn, không phải đề nghị tắt mặc định cho ví dụ thực hành. Khi tắt, ứng dụng cần cung cấp ranh giới phù hợp ở nơi khác hoặc khai báo transaction rõ ràng. Xem [API EnableJpaRepositories](https://docs.spring.io/spring-data/jpa/docs/3.5.x/api/org/springframework/data/jpa/repository/config/EnableJpaRepositories.html).

### 9.3. Chọn đúng manager khi có nhiều nguồn dữ liệu

Một hệ thống có thể có manager cho hai persistence unit hoặc cho JPA và MongoDB. Cần đối chiếu manager mà repository dùng với manager ở service.

Khai báo như `@Transactional("accountsTransactionManager")` chọn manager theo tên/qualifier. Nó không tự biến hai backend thành một giao dịch phân tán.

Nếu hai repository thuộc các tài nguyên khác nhau, phải xác định rõ phạm vi nguyên tử mà hạ tầng thực sự hỗ trợ.

### 9.4. Quy tắc rollback cũng là một phần của cấu hình

Khi không có tùy chỉnh rollback, mặc định thông thường là rollback với `RuntimeException` hoặc `Error`, còn checked exception không tự có cùng quy tắc.

Khi nghiệp vụ yêu cầu checked exception cũng rollback, có thể khai báo `rollbackFor` bằng kiểu exception phù hợp. Phải xét cả cấu hình toàn cục của ứng dụng, không chỉ annotation ở một method.

Một lỗi đã bị bắt và bỏ qua trước khi thoát khỏi ranh giới cũng cần được phân tích riêng. Không dùng câu “method có transaction” để suy ra mọi nhánh lỗi đều rollback theo cùng một cách.

## 10. Giới hạn khi chuyển sang module lưu trữ khác

| Module hoặc mô hình | Điều cần đối chiếu |
| --- | --- |
| Spring Data JPA | Base repository, persistence context, transaction manager và cấu hình query |
| Spring Data JDBC | Mặc định CRUD và query method của JDBC; không dùng giả định dirty checking của JPA |
| Spring Data MongoDB | Khả năng transaction của triển khai MongoDB, session và manager tương ứng |
| Repository reactive | Reactive transaction manager và phạm vi thực thi trong pipeline reactive |
| Fragment gọi tài nguyên bên ngoài | Tài nguyên đó có tham gia transaction được chọn hay không |

Spring Data JDBC cũng có tài liệu riêng về mặc định CRUD và cách cấu hình query transaction. Sự tương đồng với JPA không làm hai mô hình persistence trở thành một. Xem [Transactionality của Spring Data JDBC 3.5](https://docs.spring.io/spring-data/relational/reference/3.5/jdbc/transactions.html).

Với MongoDB, cần cấu hình transaction/session phù hợp; một session cũng không đồng nghĩa mọi thao tác đã nằm trong transaction nhiều document. Xem [Sessions & Transactions của Spring Data MongoDB 4.5](https://docs.spring.io/spring-data/mongodb/reference/4.5/mongodb/client-session-transactions.html).

Trong mô hình reactive, không mang nguyên giả định transaction gắn với thread của luồng JPA sang pipeline. Phải xác định manager và phạm vi thực thi tương ứng với backend đang dùng.

Đối với auditing hoặc domain callback, hãy kiểm tra đường thực thi thực tế. Một cập nhật bulk trong fragment, một lần `save` và một truy vấn đọc có thể đi qua các callback khác nhau dù được gọi từ cùng repository.

## 11. Thực hành quan sát cấu hình thật

Dùng bộ dữ liệu nhỏ gồm vài tài khoản active và inactive. Gọi qua bean Spring từ một caller bên ngoài; tránh tạo repository hoặc service bằng `new`.

| Tình huống | Điều cần quan sát |
| --- | --- |
| Gọi trực tiếp `findById` | Đường CRUD và giao dịch mặc định trong JPA |
| Gọi query đọc có annotation | Giao dịch đọc được thiết lập khi chưa có giao dịch ngoài |
| Gọi `activateIfPresent` | Ranh giới bao quanh cả tìm và lưu |
| Gọi `renameInactive` | Fragment được ghép đúng và dùng tài nguyên JPA đã quản lý |
| Gọi `activateAllInactive` | Các lần đọc/lưu cùng tham gia công việc của service |
| Gây lỗi runtime trong công việc ghi | Trạng thái dữ liệu sau khi ranh giới service kết thúc |
| Gọi ghi từ service read-only | Không giả định method repository tự đổi chế độ ngoài |
| Dùng `deactivateById` sau khi đã tải entity | Ảnh hưởng của flush/clear đến persistence context |
| Tắt default transactions trong cấu hình thử nghiệm | Phân biệt mặc định của base repository và khai báo tường minh |

Có thể bật log giao dịch và SQL trong môi trường học, rồi đối chiếu thời điểm begin/commit/rollback với dữ liệu sau cùng. Việc thấy một câu SQL UPDATE chưa chứng minh transaction đã commit.

Nếu quan sát bằng test tích hợp có transaction bao quanh cả test, transaction đó có thể che khuất việc repository tự mở giao dịch. Khi cần đánh giá ranh giới riêng, thiết kế caller và bước đọc kiểm chứng sao cho không vô tình dùng chung giao dịch ngoài.

Ngoài ra, rollback thành công không chứng minh đã xử lý mọi cập nhật đồng thời. Bài toán tranh chấp vẫn cần constraint, version, locking hoặc isolation theo yêu cầu thực tế.

## 12. Lỗi thường gặp và cách sửa hướng suy luận

| Nhận định hoặc biểu hiện | Điểm cần kiểm tra |
| --- | --- |
| “Mọi method trong CrudRepository đều có cùng transaction” | Phân biệt API Commons và implementation của module |
| “Method tên find tự là read-only” | Xem đó là CRUD kế thừa hay query method mới |
| “Có @Query nên đã có transaction” | Tách định nghĩa truy vấn khỏi metadata giao dịch |
| “@Modifying đủ để UPDATE” | Kiểm tra transaction ghi ở method hoặc caller |
| “Thêm timeout vẫn giữ readOnly cũ” | Khai báo rõ các thuộc tính cần giữ |
| “Mỗi save có transaction nên cả vòng lặp nguyên tử” | Xác định ranh giới bao quanh toàn bộ công việc |
| “readOnly bảo đảm không thể ghi” | Kiểm tra cách manager, provider và backend xử lý |
| “Fragment mang tên save nên giống implementation chuẩn” | Kiểm tra implementation đã được route tới và cấu hình của nó |
| “Có annotation ở service là chắc chắn có hiệu lực” | Kiểm tra bean, proxy, đường gọi và manager |
| “Flush xong là đã commit” | Phân biệt đồng bộ persistence context với hoàn tất giao dịch |
| “Một @Transactional bao phủ mọi backend” | Xác định tài nguyên và khả năng phối hợp của manager |

Khi đọc một repository, hãy xác định implementation của từng phương thức, metadata áp dụng và giao dịch đang bao quanh lời gọi. Khi thiết kế một công việc gồm nhiều thao tác, đặt ranh giới đủ rộng để bảo vệ chính công việc đó, rồi đối chiếu với khả năng của module lưu trữ đang sử dụng.
