# Auditing với @CreatedDate, @LastModifiedDate, @CreatedBy và @LastModifiedBy

Spring Data Auditing tự động ghi nhận thời điểm tạo, thời điểm cập nhật và người thực hiện các thao tác lưu entity. Bốn annotation thường dùng là **`@CreatedDate`**, **`@LastModifiedDate`**, **`@CreatedBy`** và **`@LastModifiedBy`**.

Khi Spring Data REST lưu entity thông qua Spring Data JPA, auditing có thể được kích hoạt ở lifecycle của JPA. Để hoạt động, ứng dụng cần bật auditing, đăng ký **`AuditingEntityListener`** trên entity và cung cấp **`AuditorAware`** nếu muốn lưu người tạo hoặc người cập nhật.

Auditing giúp trả lời các câu hỏi như “bản ghi được tạo lúc nào?”, “lần cập nhật gần nhất là khi nào?” và “ai đã thực hiện thao tác?”. Nó ghi các metadata này trên entity; bản thân auditing không lưu lịch sử mọi phiên bản hay bản diff của dữ liệu.

## 1. Vai trò của bốn annotation

Các annotation auditing nằm trong package **`org.springframework.data.annotation`**:

~~~java
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
~~~

| Annotation | Ý nghĩa | Thời điểm cập nhật |
|---|---|---|
| **`@CreatedDate`** | Thời điểm entity được tạo | Khi insert lần đầu |
| **`@LastModifiedDate`** | Thời điểm entity được sửa gần nhất | Khi tạo và khi cập nhật |
| **`@CreatedBy`** | Người tạo entity | Khi insert lần đầu |
| **`@LastModifiedBy`** | Người sửa entity gần nhất | Khi tạo và khi cập nhật |

Mặc định, **`modifyOnCreate`** của Spring Data Auditing là **`true`**, vì vậy metadata “last modified” cũng được thiết lập ở lần tạo đầu tiên. Nếu không muốn hành vi này, có thể cấu hình **`@EnableJpaAuditing(modifyOnCreate = false)`**.

Hai annotation ngày giờ có thể hoạt động mà không cần biết người dùng hiện tại. Hai annotation về actor (**`@CreatedBy`**, **`@LastModifiedBy`**) cần một nguồn cung cấp auditor, thường là bean **`AuditorAware<T>`**.

## 2. Bật JPA Auditing

Với Spring Data JPA, bật auditing bằng **`@EnableJpaAuditing`** trong một class cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing
public class JpaAuditingConfiguration {
}
~~~

Annotation **`@EnableJpaAuditing`** đăng ký hạ tầng auditing của Spring Data JPA. Nếu entity dùng **`@CreatedBy`** hoặc **`@LastModifiedBy`**, chỉ định bean **`AuditorAware`** để Spring biết actor hiện tại:

~~~java
@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorProvider")
public class JpaAuditingConfiguration {

    @Bean
    public AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system");
    }
}
~~~

Ví dụ trên luôn gán actor là **`system`**, phù hợp cho một tác vụ nền đơn giản. Trong ứng dụng thực tế, nên lấy tên người dùng từ security context hoặc một nguồn định danh đáng tin cậy.

Nếu chỉ cần timestamp, có thể bật **`@EnableJpaAuditing`** mà không cần cấu hình **`AuditorAware`**.

## 3. Lấy người dùng hiện tại bằng AuditorAware

**`AuditorAware<T>`** trả về actor được dùng cho các trường **`@CreatedBy`** và **`@LastModifiedBy`**. Kiểu **`T`** phải tương thích với kiểu thuộc tính trên entity.

Ví dụ với Spring Security:

~~~java
import java.util.Optional;

import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Bean
public AuditorAware<String> auditorProvider() {
    return () -> {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return Optional.empty();
        }

        return Optional.of(authentication.getName());
    };
}
~~~

Trong ví dụ:

- Người dùng đã đăng nhập được nhận diện bằng **`authentication.getName()`**.
- Anonymous hoặc không có authentication sẽ trả về **`Optional.empty()`**.
- Spring Data Auditing dùng giá trị trả về để gán các trường actor.

Nếu hệ thống có batch job, scheduler hoặc message consumer, các luồng này có thể không có SecurityContext. Hãy quyết định rõ actor hệ thống cần ghi nhận, chẳng hạn **`system-job`**, hoặc chấp nhận giá trị rỗng nếu nghiệp vụ cho phép. Không nên ghi một actor mặc định làm mất dấu người dùng thật.

Nếu actor là một đối tượng domain, có thể dùng **`AuditorAware<User>`** thay cho **`AuditorAware<String>`**, miễn kiểu đó phù hợp với thuộc tính **`@CreatedBy`** và **`@LastModifiedBy`**.

## 4. Khai báo audit fields trên entity

Ví dụ entity Person:

~~~java
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @CreatedDate
    @Column(updatable = false)
    private Instant createdDate;

    @LastModifiedDate
    private Instant lastModifiedDate;

    @CreatedBy
    @Column(updatable = false)
    private String createdBy;

    @LastModifiedBy
    private String lastModifiedBy;

    // getters and setters
}
~~~

Các điểm cần chú ý:

- **`@EntityListeners(AuditingEntityListener.class)`** đăng ký JPA listener để nhận callback persistence.
- **`@CreatedDate`** và **`@LastModifiedDate`** được điền tự động từ thời gian hiện tại do auditing cung cấp.
- **`@CreatedBy`** và **`@LastModifiedBy`** lấy giá trị từ **`AuditorAware`**.
- **`@Column(updatable = false)`** trên trường tạo giúp JPA không đưa các cột đó vào câu UPDATE sau khi insert.

Có thể dùng **`Instant`** để lưu thời điểm theo UTC. Spring Data cũng hỗ trợ các kiểu thời gian phổ biến khác như **`LocalDateTime`**, **`OffsetDateTime`**, **`Date`** hoặc **`Calendar`**, tùy phiên bản và mapping được sử dụng. Chọn một kiểu nhất quán trong toàn hệ thống.

Nếu dùng XML để đăng ký JPA entity listener toàn cục, có thể cấu hình **`AuditingEntityListener`** trong **`orm.xml`** thay vì lặp lại **`@EntityListeners`** trên từng entity.

## 5. Spring Data REST kích hoạt auditing khi nào?

Spring Data REST lưu entity qua repository. Khi repository dùng JPA, thao tác persist/update sẽ đi qua JPA lifecycle và listener auditing có thể cập nhật các trường audit.

Luồng điển hình:

| Request Spring Data REST | Thao tác persistence | Kết quả auditing |
|---|---|---|
| **`POST /people`** | Insert entity mới | Thiết lập created và last-modified metadata |
| **`PUT /people/{id}`** | Cập nhật entity hiện có | Giữ created metadata; cập nhật last-modified metadata |
| **`PATCH /people/{id}`** | Cập nhật một phần entity | Giữ created metadata; cập nhật last-modified metadata |
| Gọi repository **`save`** từ service | Insert hoặc update tùy trạng thái entity | Listener JPA chạy theo lifecycle tương ứng |

Auditing không phụ thuộc riêng vào HTTP request. Một lần lưu qua service hoặc batch cũng có thể được ghi nhận nếu nó đi qua persistence lifecycle được cấu hình.

Nếu ứng dụng dùng Spring Data REST với một persistence store không phải JPA, hãy dùng auditing support của store đó; **`AuditingEntityListener`** là listener dành cho JPA.

## 6. Phân biệt auditing với transaction và event listener

Auditing và transaction có liên quan trong cùng luồng lưu dữ liệu nhưng giải quyết các mục đích khác nhau:

- **Transaction** xác định ranh giới commit/rollback của thao tác dữ liệu.
- **Auditing** cập nhật metadata tạo/sửa trên entity trong lifecycle persistence.
- **Spring Data REST repository events** cho phép xử lý logic trước hoặc sau các thao tác repository, chẳng hạn **`beforeCreate`** hoặc **`afterSave`**.
- **Audit log/history** lưu lại nhiều sự kiện hoặc phiên bản để truy vết lâu dài; bốn annotation auditing không tự cung cấp chức năng này.

Nếu transaction rollback, thay đổi metadata trên entity cũng không được commit vào database. Tuy nhiên, một object đang nằm trong bộ nhớ có thể đã được listener gán giá trị trước khi rollback; không dùng object đó làm bằng chứng rằng transaction đã commit.

## 7. Giữ audit fields do server quản lý

Các trường audit thường do server kiểm soát. Client không nên tự gửi **`createdBy`**, **`createdDate`**, **`lastModifiedBy`** hoặc **`lastModifiedDate`** để giả mạo lịch sử.

Có thể đánh dấu thuộc tính bằng **`@ReadOnlyProperty`** để Spring Data xem đó là thuộc tính chỉ đọc trong quá trình ghi:

~~~java
import org.springframework.data.annotation.ReadOnlyProperty;

@CreatedDate
@ReadOnlyProperty
@Column(updatable = false)
private Instant createdDate;

@LastModifiedDate
@ReadOnlyProperty
private Instant lastModifiedDate;
~~~

Áp dụng tương tự cho hai trường actor nếu chúng được công bố trong representation. Kiểm tra response và hành vi ghi thực tế của phiên bản Spring Data REST đang dùng.

Nếu không muốn client nhìn thấy metadata, có thể loại chúng khỏi representation bằng projection hoặc cấu hình API phù hợp. Việc ẩn khỏi response và việc ngăn client ghi là hai yêu cầu riêng; hãy kiểm soát cả hai theo contract.

## 8. Tùy chỉnh thời gian auditing

Mặc định, auditing lấy thời gian hiện tại từ **`DateTimeProvider`**. Có thể cung cấp một bean riêng để kiểm soát nguồn thời gian, ví dụ khi cần test hoặc chuẩn hóa clock:

~~~java
import java.time.Clock;
import java.time.temporal.TemporalAccessor;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.data.auditing.DateTimeProvider;

@Bean
public Clock auditingClock() {
    return Clock.systemUTC();
}

@Bean
public DateTimeProvider dateTimeProvider(Clock auditingClock) {
    return () -> Optional.of(Instant.now(auditingClock));
}
~~~

Sau đó tham chiếu bean trong cấu hình:

~~~java
@EnableJpaAuditing(
    auditorAwareRef = "auditorProvider",
    dateTimeProviderRef = "dateTimeProvider"
)
~~~

Dùng clock có thể kiểm soát giúp test timestamp ổn định và tránh phụ thuộc trực tiếp vào đồng hồ hệ thống. Trong production, nên lưu thời điểm nhất quán, thường theo UTC, rồi chuyển sang múi giờ hiển thị ở tầng giao diện.

Nếu chỉ cần hành vi mặc định, không cần khai báo **`DateTimeProvider`** riêng.

## 9. Kiểm tra auditing bằng integration test

Nên kiểm tra cả trường hợp tạo mới và cập nhật bằng cách lưu entity rồi ép flush để JPA thực hiện lifecycle callback.

Ví dụ:

~~~java
@Test
void auditingFieldsAreSetOnCreateAndUpdate() {
    Person person = new Person();
    person.setName("An");

    Person created = personRepository.saveAndFlush(person);

    assertNotNull(created.getCreatedDate());
    assertNotNull(created.getLastModifiedDate());
    assertNotNull(created.getCreatedBy());
    assertNotNull(created.getLastModifiedBy());

    Instant originalCreatedDate = created.getCreatedDate();
    String originalCreatedBy = created.getCreatedBy();

    created.setName("An Nguyen");
    Person updated = personRepository.saveAndFlush(created);

    assertEquals(originalCreatedDate, updated.getCreatedDate());
    assertEquals(originalCreatedBy, updated.getCreatedBy());
    assertNotNull(updated.getLastModifiedDate());
    assertNotNull(updated.getLastModifiedBy());
}
~~~

Để test actor có kết quả xác định, cấu hình **`AuditorAware`** trong test trả về một actor cố định như **`test-user`**. Với test dựa trên Spring Security, thiết lập authentication trước khi gọi repository.

Có thể thêm HTTP integration test cho Spring Data REST:

1. Gửi POST tạo Person qua **`/people`**.
2. Đọc response hoặc GET lại item và xác nhận các trường created/modified đã được điền.
3. Gửi PATCH hoặc PUT thay đổi tên.
4. GET lại item để xác nhận created metadata giữ nguyên và modified metadata được cập nhật.
5. Kiểm tra actor phản ánh đúng người dùng của request.

Không nên chỉ kiểm tra HTTP status. Hãy đọc lại entity hoặc database sau khi transaction hoàn tất để xác minh dữ liệu thực sự đã được lưu.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Các trường ngày vẫn null | Chưa bật **`@EnableJpaAuditing`** hoặc listener chưa được đăng ký | Kiểm tra cấu hình và **`@EntityListeners`** |
| CreatedDate có giá trị nhưng CreatedBy null | Chưa có **`AuditorAware`** hoặc nguồn actor trả về empty | Đăng ký auditor provider và kiểm tra security context |
| LastModifiedDate không đổi khi cập nhật | Entity không đi qua JPA update lifecycle hoặc không phát sinh thay đổi cần lưu | Ép flush trong test và kiểm tra SQL/persistence state |
| Actor luôn là system | Auditor provider đang trả về giá trị cố định | Lấy actor từ authentication hoặc nguồn định danh phù hợp |
| CreatedDate bị thay đổi sau update | Trường created chưa được bảo vệ hoặc logic ứng dụng ghi đè | Dùng **`updatable = false`**, read-only mapping và không cho client ghi |
| Timestamp lệch múi giờ | Trộn kiểu thời gian hoặc chuyển đổi timezone không nhất quán | Ưu tiên Instant/UTC và chuyển timezone khi hiển thị |
| Audit fields không được lưu qua REST | JPA listener chưa được cấu hình cho entity hoặc repository không dùng JPA | Kiểm tra persistence module và listener thực tế |

## 11. Checklist cấu hình

- Có Spring Data JPA và persistence provider phù hợp.
- Có **`@EnableJpaAuditing`** trong Spring configuration.
- Entity có **`@EntityListeners(AuditingEntityListener.class)`** hoặc listener được đăng ký toàn cục qua XML.
- Các trường audit dùng đúng annotation từ **`org.springframework.data.annotation`**.
- Có **`AuditorAware<T>`** nếu cần ghi người tạo/người sửa.
- Kiểu trả về của **`AuditorAware`** tương thích với kiểu trường actor.
- Security context hoặc nguồn actor nền được xử lý rõ ràng.
- Các trường audit do server quản lý được bảo vệ khỏi client ghi giả mạo.
- Integration test xác nhận cả insert và update sau khi flush/commit.
- Nếu cần lịch sử đầy đủ, thiết kế audit log hoặc version history riêng.

Tài liệu tham khảo chính thức:

- [Spring Data JPA — Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html)
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
