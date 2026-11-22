# Timeout, flush và thời điểm phát sinh lỗi ràng buộc

Trong Spring Data JPA, ba khái niệm này liên quan chặt chẽ nhưng giải quyết những vấn đề khác nhau:

- **Timeout** giới hạn thời gian một giao dịch, câu truy vấn hoặc thao tác chờ khóa được phép chạy.
- **Flush** đồng bộ các thay đổi đang được quản lý trong persistence context xuống cơ sở dữ liệu.
- **Lỗi ràng buộc** xuất hiện khi cơ sở dữ liệu hoặc cơ chế kiểm tra dữ liệu phát hiện bản ghi vi phạm quy tắc như NOT NULL, UNIQUE, FOREIGN KEY hoặc CHECK.

Điểm dễ gây nhầm lẫn là lời gọi **save()** có thể hoàn tất trước khi câu SQL INSERT/UPDATE được gửi xuống database. Vì vậy, lỗi ràng buộc đôi khi chỉ xuất hiện tại **flush()** hoặc lúc transaction commit.

## 1. Transaction timeout trong Spring

### 1.1. Đặt timeout cho ranh giới giao dịch

Có thể đặt thời gian tối đa cho transaction bằng thuộc tính **timeout** của **@Transactional**:

~~~java
@Service
public class PaymentService {

    private final PaymentRepository payments;

    public PaymentService(PaymentRepository payments) {
        this.payments = payments;
    }

    @Transactional(timeout = 10)
    public void createPayment(Payment payment) {
        payments.save(payment);
        // Các thao tác thuộc cùng transaction
    }
}
~~~

Trong ví dụ, timeout là **10 giây**. Đây là ngân sách thời gian cho transaction, không phải thời gian tối đa riêng cho từng câu SQL. Nếu không cấu hình, Spring dùng timeout mặc định của transaction manager; thông thường giá trị mặc định là không đặt giới hạn riêng.

Timeout chỉ có ý nghĩa khi transaction manager và tài nguyên bên dưới hỗ trợ thực thi nó. Spring có thể truyền giới hạn xuống JDBC/JPA resource, nhưng cách database, JDBC driver và JPA provider phát hiện hoặc ngắt thao tác quá hạn phụ thuộc cấu hình và triển khai cụ thể. Không nên xem **timeout** như cơ chế chắc chắn ngắt mọi đoạn mã Java đúng tại giây thứ N. Ví dụ, một đoạn tính toán CPU hoặc **Thread.sleep()** không nhất thiết bị dừng ngay khi hết thời gian transaction.

### 1.2. Transaction timeout gắn với transaction thực sự được tạo

Mặc định, **@Transactional** dùng propagation **REQUIRED**:

- Nếu chưa có transaction, Spring tạo transaction mới và áp dụng timeout được khai báo.
- Nếu đã có transaction bên ngoài, lời gọi thường tham gia transaction đó. Timeout và các thuộc tính transaction của transaction bên ngoài tiếp tục chi phối; timeout khai báo ở phương thức tham gia không đặt lại đồng hồ cho transaction đang chạy.

Do đó, hãy đặt timeout tại ranh giới dịch vụ thực sự mở transaction, thường là phương thức service điều phối nhiều thao tác repository.

**@Transactional** thường được thực thi thông qua Spring proxy. Lời gọi một phương thức transactional từ một phương thức khác trong cùng object (self-invocation) có thể bỏ qua proxy, khiến annotation không được áp dụng như mong đợi. Hãy gọi phương thức qua Spring bean phù hợp và kiểm tra ranh giới transaction thực tế khi debug.

Các phương thức CRUD kế thừa từ **SimpleJpaRepository** đã có cấu hình transaction mặc định: thao tác đọc thường là read-only, thao tác ghi có transaction. Các phương thức truy vấn tự khai báo trong repository không tự động nhận cấu hình transaction chỉ vì chúng nằm trong interface repository. Khi một nghiệp vụ gồm nhiều thao tác, nên khai báo transaction ở service để toàn bộ nghiệp vụ có cùng ranh giới commit/rollback.

### 1.3. Phân biệt các loại timeout

| Loại timeout | Đơn vị thường dùng | Phạm vi |
|---|---:|---|
| **@Transactional(timeout = 10)** | Giây | Ngân sách thời gian của transaction |
| JPA query hint **jakarta.persistence.query.timeout** | Mili giây | Một câu truy vấn |
| JPA lock hint **jakarta.persistence.lock.timeout** | Mili giây | Thời gian chờ khóa khi truy vấn cần lock |
| Connection pool timeout | Tùy pool, thường là mili giây | Thời gian chờ lấy connection từ pool |
| Socket/read timeout của JDBC driver | Tùy driver | Thời gian chờ phản hồi mạng/database |

Các timeout này không thay thế cho nhau. Ví dụ, transaction timeout không đồng nghĩa với query timeout; connection pool timeout có thể xảy ra trước khi câu SQL được gửi đi. JPA query hint là gợi ý cho provider và database, nên khả năng hỗ trợ cũng cần được xác nhận theo hệ thống đang dùng.

Có thể đặt query timeout cho một phương thức truy vấn bằng Spring Data JPA:

~~~java
public interface AppUserRepository extends JpaRepository<AppUser, UUID> {

    @QueryHints(
        value = @QueryHint(
            name = "jakarta.persistence.query.timeout",
            value = "2000"
        )
    )
    @Query("select u from AppUser u where u.email = :email")
    Optional<AppUser> findByEmail(@Param("email") String email);
}
~~~

Giá trị **2000** ở đây là 2.000 mili giây theo quy ước của JPA query timeout. Cần import các annotation tương ứng từ **jakarta.persistence** và **org.springframework.data.jpa.repository**. Query hint không tự tạo transaction; nếu phương thức cần transaction, hãy cấu hình transaction riêng. Với dự án dùng JPA cũ, tên hint có thể thuộc namespace **javax.persistence**; hãy dùng namespace khớp với phiên bản ứng dụng.

## 2. Flush và persistence context

### 2.1. JPA trì hoãn ghi dữ liệu

Entity được quản lý trong persistence context. Khi gọi **save()**, Spring Data JPA yêu cầu **EntityManager** lưu entity:

- Với entity mới, repository thường gọi **persist()**.
- Với entity đã tồn tại, repository thường gọi **merge()**.
- Khi dùng **merge()**, đối tượng trả về là instance được quản lý; nên tiếp tục dùng giá trị trả về của **save()**.

JPA thường áp dụng cơ chế **write-behind**: thay đổi được ghi nhận trong persistence context trước, còn SQL có thể được gửi xuống database ở thời điểm flush. Vì vậy, **save()** không có nghĩa là transaction đã commit, và cũng không bảo đảm SQL luôn được thực thi ngay tại dòng lệnh đó. Một số chiến lược sinh khóa, chẳng hạn **IDENTITY**, có thể khiến provider phải INSERT sớm để lấy khóa chính.

### 2.2. Flush làm gì?

**flush()** đồng bộ trạng thái entity đang được quản lý với database bằng cách phát sinh các câu INSERT, UPDATE hoặc DELETE cần thiết trong transaction hiện tại.

Có thể yêu cầu flush thông qua **EntityManager** hoặc repository:

~~~java
@Transactional
public void updateUser(AppUser user) {
    users.save(user);
    users.flush();
}
~~~

**JpaRepository** cung cấp **flush()** và **saveAndFlush()**. Hai cách thường dùng:

~~~
users.save(user);
users.flush();
~~~

hoặc:

~~~
users.saveAndFlush(user);
~~~

Flush có các đặc điểm quan trọng:

1. SQL được thực thi trong transaction hiện tại.
2. Database có cơ hội kiểm tra các ràng buộc áp dụng cho những câu SQL vừa chạy.
3. Transaction vẫn chưa commit. Dữ liệu chưa trở thành một transaction đã commit và có thể còn bị rollback.
4. Các khóa database có thể tiếp tục được giữ đến khi transaction kết thúc.

**Flush không đồng nghĩa với commit.** Flush chỉ đẩy các thay đổi đang chờ xuống database; commit mới hoàn tất transaction.

### 2.3. Khi nào JPA tự động flush?

Với **FlushModeType.AUTO** (chế độ mặc định theo JPA), provider phải bảo đảm kết quả truy vấn nhìn thấy các thay đổi đang chờ có liên quan trong persistence context. Provider thường flush trước một truy vấn có thể bị ảnh hưởng bởi những thay đổi đó. Provider cũng flush trước khi transaction commit.

Với **FlushModeType.COMMIT**, việc đồng bộ được trì hoãn đến thời điểm commit theo cấu hình flush mode; không nên dựa vào một truy vấn trung gian để buộc thay đổi đã được gửi xuống database.

Luồng thường gặp:

~~~text
Gọi repository.save(...)
        |
        v
Entity được quản lý trong persistence context
        |
        v
Flush thủ công, flush tự động trước truy vấn liên quan,
hoặc flush khi commit
        |
        v
INSERT / UPDATE / DELETE được gửi xuống database
        |
        v
Database kiểm tra các ràng buộc
        |
        v
Commit thành công hoặc transaction rollback
~~~

## 3. Vì sao lỗi ràng buộc có thể xuất hiện muộn?

### 3.1. Thời điểm kiểm tra phụ thuộc thời điểm SQL chạy

Giả sử bảng **app_user** có ràng buộc UNIQUE trên cột **email**. Một transaction thêm email đã tồn tại có thể diễn ra như sau:

1. **save()** đưa entity vào persistence context.
2. Phương thức service tiếp tục chạy và có thể trả về kết quả từ phần thân phương thức.
3. Khi flush, JPA gửi INSERT xuống database.
4. Database phát hiện email trùng và từ chối câu INSERT.
5. Transaction không thể commit thành công và phải rollback.

Nếu không gọi flush thủ công, bước 3 có thể diễn ra trong quá trình commit sau khi phần thân phương thức service đã chạy xong. Khi đó, lỗi vẫn được ném ra cho bên gọi phương thức transactional, vì Spring cần hoàn tất commit trước khi trả kết quả cho caller.

| Thời điểm | Điều có thể xảy ra |
|---|---|
| **save() / persist()** | Entity được đưa vào persistence context; một số kiểm tra hoặc SQL có thể xảy ra sớm tùy provider và chiến lược sinh ID |
| **flush() / saveAndFlush()** | SQL được gửi xuống database; lỗi ràng buộc thường xuất hiện tại đây |
| **commit()** | JPA flush các thay đổi còn lại; lỗi có thể xuất hiện tại đây nếu chưa flush trước đó |
| Commit với ràng buộc trì hoãn của database | Một số ràng buộc được cấu hình deferred chỉ được xác nhận ở cuối transaction |

Vì vậy, vị trí dòng **save()** không nhất thiết là nơi phát sinh lỗi. Muốn chủ động phát hiện lỗi SQL sớm hơn trong phương thức, có thể gọi **flush()** hoặc **saveAndFlush()**. Tuy nhiên, ngay cả flush cũng không bảo đảm phát hiện mọi ràng buộc được database cấu hình kiểm tra trì hoãn đến commit.

### 3.2. Phân biệt kiểm tra Bean Validation và ràng buộc database

Có hai lớp kiểm tra thường gặp:

- **Bean Validation**: ví dụ **@NotNull**, **@NotBlank**, **@Email**. Khi tích hợp validation với JPA, provider có thể kiểm tra entity trước khi ghi SQL, thường tại các thời điểm lifecycle như persist hoặc update.
- **Database constraint**: ví dụ NOT NULL, UNIQUE, FOREIGN KEY, CHECK. Database kiểm tra khi câu SQL tương ứng được thực thi, hoặc tại commit nếu constraint được cấu hình deferred.

**@Column(nullable = false)** mô tả mapping/schema và có thể được dùng khi sinh DDL; nó không thay thế cho kiểm tra dữ liệu trong Java. Nếu cần xác thực đầu vào trước khi chạm database, hãy dùng Bean Validation phù hợp. Nếu cần bảo vệ tính toàn vẹn trước các request đồng thời, database vẫn cần constraint thật được tạo bằng migration hoặc DDL.

### 3.3. Exception có thể được bọc qua nhiều lớp

Khi database từ chối INSERT/UPDATE, exception đi qua JPA provider và Spring. Tùy provider, dialect và thời điểm lỗi, lớp exception bên ngoài có thể khác nhau. Spring Data JPA thường dịch lỗi toàn vẹn dữ liệu thành **DataIntegrityViolationException**; trong cause chain có thể có exception đặc thù của Hibernate, JDBC hoặc JPA.

Không nên chỉ dựa vào tên exception ngoài cùng để kết luận. Hãy xem cause chain, SQLSTATE/vendor code, câu SQL và constraint được database báo lỗi. Đồng thời phân biệt lỗi database constraint với **jakarta.validation.ConstraintViolationException** của Bean Validation; chúng có cùng cụm từ nhưng thuộc hai cơ chế và package khác nhau.

### 3.4. Transaction sau khi flush thất bại

Khi flush gặp lỗi, transaction thường không còn an toàn để tiếp tục. JPA provider hoặc transaction manager có thể đánh dấu transaction rollback-only. Nếu bắt exception rồi tiếp tục ghi dữ liệu trong cùng transaction, thao tác commit cuối cùng có thể thất bại, chẳng hạn bằng **UnexpectedRollbackException**.

Cách xử lý an toàn thường là để exception thoát khỏi ranh giới transaction để transaction rollback, sau đó chuyển lỗi thành phản hồi nghiệp vụ ở tầng phù hợp. Nếu cần thử lại hoặc xử lý tiếp, hãy thực hiện trong một transaction mới sau khi transaction lỗi đã kết thúc. Không nuốt exception rồi coi transaction vẫn hợp lệ.

## 4. Ví dụ: phát hiện email trùng tại flush

Ví dụ sau minh họa một entity có UUID được tạo ở phía ứng dụng và ràng buộc UNIQUE trên email. Mã dùng Java 17, Jakarta Persistence và Spring Data JPA; đây là các lớp trong một ứng dụng Spring Boot đã cấu hình datasource, JPA và schema, không phải chương trình Java độc lập.

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.util.UUID;

@Entity
@Table(
    name = "app_user",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_app_user_email",
        columnNames = "email"
    )
)
public class AppUser {

    @Id
    private UUID id;

    @Column(nullable = false)
    private String email;

    protected AppUser() {
    }

    public AppUser(String email) {
        this.id = UUID.randomUUID();
        this.email = email;
    }

    public UUID getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Repository:

~~~java
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AppUserRepository
        extends JpaRepository<AppUser, UUID> {
}
~~~

Service:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RegistrationService {

    private final AppUserRepository users;

    public RegistrationService(AppUserRepository users) {
        this.users = users;
    }

    @Transactional(timeout = 5)
    public UUID register(String email) {
        AppUser saved = users.save(new AppUser(email));

        // Buộc đồng bộ SQL ngay tại đây để lỗi constraint
        // thường xuất hiện trong lời gọi flush.
        users.flush();

        return saved.getId();
    }
}
~~~

Nếu gọi **register()** lần thứ hai với email đã tồn tại và database có constraint UNIQUE tương ứng, **users.flush()** sẽ làm database kiểm tra INSERT và thường ném lỗi toàn vẹn dữ liệu ngay tại lời gọi đó. Transaction hiện tại sẽ rollback. Nếu bỏ dòng **users.flush()**, SQL có thể chỉ được gửi khi transaction commit; khi ấy caller vẫn nhận exception trong lúc lời gọi service hoàn tất transaction.

Lưu ý: khai báo **uniqueConstraints** trong entity chỉ có tác dụng tạo schema khi cơ chế sinh DDL được bật. Với database đã quản lý bằng migration, phải bảo đảm migration thực sự tạo constraint **uk_app_user_email**; annotation không tự sửa schema đang tồn tại.

## 5. Timeout tương tác với flush như thế nào?

Transaction timeout bao phủ cả thời gian xử lý nghiệp vụ và các thao tác tài nguyên nằm trong transaction. Ví dụ, một transaction có timeout 5 giây có thể dành thời gian cho kiểm tra nghiệp vụ, chờ khóa và thực thi SQL. Nếu transaction vượt giới hạn, thao tác truy cập tài nguyên hoặc commit có thể bị từ chối tùy transaction manager, provider và driver.

Một số tình huống:

- Phương thức chạy nhiều xử lý trước khi flush: timeout có thể đã hết khi đến lúc gửi SQL.
- Flush chạy câu INSERT/UPDATE chậm: giới hạn transaction hoặc timeout ở câu lệnh có thể khiến thao tác thất bại.
- Transaction chờ khóa: lock timeout và transaction timeout có thể cùng liên quan; loại nào được áp dụng phụ thuộc cấu hình.
- Phương thức tham gia transaction bên ngoài: timeout của transaction bên ngoài vẫn là giới hạn cần quan tâm.
- Transaction timeout không phải cách thay thế cho query timeout, connection timeout hoặc socket timeout.

Không nên kéo dài transaction trong khi gọi HTTP, chờ người dùng, xử lý tệp lớn hoặc thực hiện công việc không cần giữ transaction. Hãy giữ ranh giới transaction ngắn, đặt timeout theo SLA thực tế, tối ưu truy vấn và index, đồng thời cấu hình timeout ở tầng database/driver khi cần kiểm soát thời gian thực thi câu SQL.

## 6. Quy trình chẩn đoán lỗi timeout hoặc constraint

Khi lỗi chỉ xuất hiện ở **flush()** hoặc commit, có thể kiểm tra theo thứ tự:

1. **Xác nhận transaction có hoạt động**: kiểm tra phương thức được gọi qua Spring bean/proxy, không phải self-invocation; xác định transaction manager đang dùng.
2. **Xác định transaction bắt đầu ở đâu**: kiểm tra propagation và transaction bên ngoài. Timeout ở một phương thức tham gia không nhất thiết thay đổi timeout của transaction đã tồn tại.
3. **Kiểm tra đơn vị và phạm vi timeout**: **@Transactional** dùng giây; JPA query/lock hint thường dùng mili giây. Xem thêm timeout của pool và JDBC driver.
4. **Xác định thời điểm SQL thực sự chạy**: bật SQL logging trong môi trường phát triển hoặc kiểm thử; thử **flush()** có chủ đích để xác định lỗi xảy ra khi đồng bộ dữ liệu.
5. **Đối chiếu schema database**: kiểm tra constraint thật, tên constraint, kiểu dữ liệu, dữ liệu trùng và quan hệ khóa ngoại. Không chỉ dựa vào annotation trong entity.
6. **Đọc cause chain**: lấy SQLSTATE/vendor code và thông tin constraint từ exception gốc; phân biệt Bean Validation với database constraint.
7. **Kiểm tra trạng thái transaction sau lỗi**: nếu đã rollback-only, kết thúc transaction và thực hiện thao tác tiếp theo trong transaction mới khi phù hợp.
8. **Tạo integration test với database tương ứng**: kiểm tra email trùng, giá trị null, khóa ngoại sai, lock contention và câu truy vấn chậm. Hành vi có thể khác giữa H2 và database production.

## 7. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| **save()** thành công nghĩa là database đã commit | **save()** có thể chỉ cập nhật persistence context; commit diễn ra ở ranh giới transaction |
| **saveAndFlush()** tương đương commit | Nó flush SQL trong transaction hiện tại, nhưng transaction vẫn có thể rollback |
| Gọi **flush()** là dữ liệu đã bền vững | Flush không commit; transaction vẫn chưa hoàn tất |
| **@Transactional(timeout = 5)** là timeout 5 mili giây | Đơn vị của thuộc tính này là giây |
| Query timeout và transaction timeout giống nhau | Một cái giới hạn câu truy vấn, một cái giới hạn transaction |
| Bắt lỗi tại **save()** là đủ | Lỗi có thể chỉ xuất hiện ở flush hoặc commit |
| Bắt exception rồi tiếp tục trong cùng transaction luôn an toàn | Transaction có thể đã rollback-only; commit sau đó vẫn thất bại |
| **@Column(nullable = false)** bảo đảm dữ liệu đầu vào đã hợp lệ trong Java | Cần Bean Validation cho kiểm tra đầu vào và constraint thật trong database cho toàn vẹn dữ liệu |
| Thêm annotation **@Transactional** ở bất kỳ vị trí nào cũng có hiệu lực | Proxy, self-invocation và transaction đang tồn tại có thể làm thay đổi hành vi |

## 8. Ghi nhớ

- Dùng **@Transactional(timeout = ...)** để đặt ngân sách thời gian cho transaction ở đúng service boundary.
- Dùng JPA query/lock timeout khi cần giới hạn riêng truy vấn hoặc thời gian chờ khóa; xác nhận provider và database có hỗ trợ.
- Xem **save()** là thao tác yêu cầu JPA lưu entity, không phải cam kết rằng SQL đã chạy hoặc transaction đã commit.
- Dùng **flush()** hoặc **saveAndFlush()** khi cần buộc SQL chạy sớm và phát hiện lỗi database constraint trước phần còn lại của nghiệp vụ.
- Khi flush thất bại, để transaction rollback và xử lý exception ở ranh giới phù hợp; không tiếp tục dùng một transaction có thể đã rollback-only.
- Luôn xác minh constraint trong schema thật và kiểm thử trên loại database gần với môi trường triển khai.

