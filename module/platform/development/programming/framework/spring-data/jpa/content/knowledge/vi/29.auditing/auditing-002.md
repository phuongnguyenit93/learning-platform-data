# @CreatedDate, @LastModifiedDate và kiểu thời gian phù hợp

Spring Data JPA Auditing giúp tự động ghi nhận thời điểm một entity được tạo và lần cuối được sửa. Thay vì gán ngày giờ thủ công ở mọi service, ta khai báo các annotation trên entity và bật auditing trong cấu hình Spring.

Hai annotation thời gian thường dùng là:

- **@CreatedDate**: ghi thời điểm entity được tạo.
- **@LastModifiedDate**: ghi thời điểm entity được sửa gần nhất. Với cấu hình mặc định, trường này cũng được thiết lập khi entity được tạo.

Đối với dữ liệu audit cần biểu diễn một thời điểm thống nhất trên toàn hệ thống, **java.time.Instant** thường là lựa chọn phù hợp. Tuy nhiên, kiểu thời gian phải phản ánh đúng ý nghĩa nghiệp vụ và cách database lưu timestamp.

## 1. Spring Data JPA Auditing hoạt động như thế nào?

Auditing là cơ chế của Spring Data để tự động điền các trường metadata trong vòng đời entity. Với JPA, Spring cung cấp **AuditingEntityListener** để tham gia các lifecycle callback của entity.

Luồng cơ bản:

~~~text
Ứng dụng gọi repository.save(entity)
              |
              v
JPA quản lý entity trong persistence context
              |
              v
Entity được persist hoặc update
              |
              v
AuditingEntityListener nhận lifecycle callback
              |
              v
AuditingHandler điền createdDate / lastModifiedDate
              |
              v
JPA flush INSERT hoặc UPDATE xuống database
              |
              v
Transaction commit
~~~

Auditing không tự bật chỉ vì dự án có dependency Spring Data JPA. Cần bật tính năng bằng **@EnableJpaAuditing** và đăng ký listener cho entity hoặc mapped superclass cần theo dõi.

Hai annotation **@CreatedDate** và **@LastModifiedDate** thuộc package **org.springframework.data.annotation**. Listener JPA thuộc package **org.springframework.data.jpa.domain.support**.

## 2. Bật auditing trong ứng dụng

Tạo một lớp cấu hình Spring:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing
public class JpaAuditingConfiguration {
}
~~~

**@EnableJpaAuditing** đăng ký hạ tầng auditing cho Spring Data JPA. Cấu hình này nên nằm trong package được Spring component scan, hoặc được import rõ ràng vào application context.

Nếu dự án đã có lớp cấu hình phù hợp, có thể đặt annotation trên lớp đó. Không cần khai báo nhiều lần ở nhiều configuration class.

### 2.1. Đăng ký AuditingEntityListener

JPA cần biết listener nào sẽ xử lý các lifecycle callback. Khai báo trên entity:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class Article {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
}
~~~

Trong ví dụ thực tế, các trường audit sẽ được khai báo trong entity. Với nhiều entity cùng cần audit, nên gom các trường chung vào một lớp **@MappedSuperclass** để tránh lặp code.

## 3. Khai báo @CreatedDate và @LastModifiedDate

Ví dụ dưới đây dùng **Instant** cho cả thời điểm tạo và cập nhật:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.MappedSuperclass;
import java.time.Instant;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class AuditedEntity {

    @CreatedDate
    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    @LastModifiedDate
    @Column(nullable = false)
    private Instant lastModifiedAt;

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }
}
~~~

Entity nghiệp vụ kế thừa lớp audit:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Article extends AuditedEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    protected Article() {
    }

    public Article(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void rename(String title) {
        this.title = title;
    }
}
~~~

Khi entity được tạo và lưu, listener điền **createdAt** và **lastModifiedAt**. Khi entity đã tồn tại được sửa và JPA thực sự phát sinh UPDATE, listener cập nhật **lastModifiedAt**. Trường **createdAt** được bảo vệ ở cả hai lớp:

- **@CreatedDate** có nhiệm vụ ghi nhận thời điểm tạo.
- **updatable = false** yêu cầu JPA không đưa cột này vào câu UPDATE do entity manager tạo.

**updatable = false** là thuộc tính mapping của JPA; nó không phải cơ chế bảo vệ tuyệt đối ở database trước SQL native hoặc câu lệnh bên ngoài ứng dụng. Nếu cần bất biến ở cấp database, có thể bổ sung quyền, trigger hoặc quy tắc schema phù hợp.

### 3.1. Thời điểm nào được ghi?

Với cấu hình mặc định **modifyOnCreate = true**:

| Trạng thái entity | @CreatedDate | @LastModifiedDate |
|---|---|---|
| Persist lần đầu | Được thiết lập | Được thiết lập |
| Update entity đã tồn tại | Giữ nguyên | Được cập nhật |
| Không có thay đổi được JPA ghi xuống | Giữ nguyên | Thường không đổi |
| Bulk JPQL/native UPDATE | Listener không tự chạy | Listener không tự chạy |

Nếu nghiệp vụ không muốn đặt trường modified date lúc tạo mới, có thể cấu hình:

~~~java
@Configuration
@EnableJpaAuditing(modifyOnCreate = false)
public class JpaAuditingConfiguration {
}
~~~

Khi đó, auditing không đánh dấu entity là đã sửa trong lần tạo đầu tiên. Hãy chọn cấu hình phù hợp với ý nghĩa của trường dữ liệu và quy ước của hệ thống.

## 4. Chọn kiểu thời gian phù hợp

Kiểu Java quyết định ý nghĩa của dữ liệu thời gian trước khi xét đến cách Hibernate/JDBC ánh xạ xuống database.

| Kiểu Java | Ý nghĩa | Khi nào nên dùng |
|---|---|---|
| **Instant** | Một thời điểm trên dòng thời gian toàn cầu, biểu diễn theo UTC | Audit log, thời điểm tạo/cập nhật, sự kiện hệ thống |
| **OffsetDateTime** | Ngày giờ kèm độ lệch UTC, ví dụ +07:00 | Khi cần giữ offset đã biết cùng thời điểm |
| **LocalDateTime** | Ngày và giờ địa phương, không có múi giờ hoặc offset | Lịch hẹn hoặc thời gian nghiệp vụ theo quy ước địa phương khi zone được quản lý riêng |
| **LocalDate** | Chỉ có ngày, không có giờ | Ngày sinh, ngày hiệu lực, ngày kế toán |
| **ZonedDateTime** | Ngày giờ gắn với ZoneId như Asia/Ho_Chi_Minh | Logic lịch theo vùng địa lý; cần kiểm tra hỗ trợ ánh xạ và lưu trữ của provider/database |

### 4.1. Vì sao Instant thường phù hợp cho audit?

Giả sử một hệ thống có người dùng ở Việt Nam, Nhật Bản và Mỹ. Nếu lưu thời điểm một bản ghi được tạo, ta thường muốn mọi dịch vụ hiểu đó là cùng một khoảnh khắc, bất kể máy chủ hoặc người dùng ở múi giờ nào.

**Instant** biểu diễn thời điểm trên UTC timeline. Ví dụ:

~~~java
Instant createdAt = Instant.parse("2026-11-09T13:00:00Z");
~~~

Đây là thời điểm 13:00 UTC. Khi hiển thị cho người dùng ở múi giờ Việt Nam (UTC+07:00), ứng dụng có thể chuyển đổi thành 20:00 cùng ngày:

~~~java
ZonedDateTime vietnamTime = createdAt.atZone(
    ZoneId.of("Asia/Ho_Chi_Minh")
);
~~~

Việc lưu một thời điểm chuẩn và chuyển đổi ở tầng hiển thị giúp tránh nhầm lẫn khi hệ thống có nhiều múi giờ hoặc chuyển vùng máy chủ.

### 4.2. Khi nào không nên dùng LocalDateTime?

**LocalDateTime** không chứa múi giờ hoặc offset. Hai giá trị 20:00 cùng ngày ở Việt Nam và một vùng khác có thể là hai thời điểm khác nhau, nhưng bản thân LocalDateTime không thể phân biệt.

Nếu dùng LocalDateTime cho audit timestamp, đội phát triển phải thống nhất múi giờ quy ước ở nơi tạo, lưu và đọc dữ liệu. Với sự kiện cần so sánh, sắp xếp hoặc đồng bộ giữa nhiều vùng, Instant thường an toàn hơn.

### 4.3. Database và độ chính xác timestamp

Dù Java dùng Instant, kiểu cột và hành vi lưu trữ vẫn phụ thuộc database, JDBC driver, Hibernate dialect và cấu hình timezone. Một số database chuẩn hóa timestamp theo UTC; một số kiểu cột có hoặc không lưu offset/zone.

Cần thống nhất:

- Lưu thời điểm audit theo UTC hoặc một quy ước được tài liệu hóa rõ ràng.
- Dùng kiểu cột database phù hợp với dialect đang triển khai.
- Cấu hình timezone nhất quán giữa ứng dụng, JDBC và database.
- Kiểm tra độ chính xác phần giây của cột. Database có thể chỉ lưu microsecond hoặc millisecond, nên giá trị đọc lại có thể không còn đủ nanosecond như Instant ban đầu.
- Chuyển sang múi giờ người dùng ở tầng trình bày, không tự ý cộng/trừ giờ trước khi lưu.

Không dùng **@Temporal** cho các kiểu java.time như Instant hoặc LocalDateTime. **@Temporal** dành cho các kiểu ngày giờ legacy như **java.util.Date** và **java.util.Calendar**.

## 5. Tự kiểm soát nguồn thời gian bằng Clock

Mặc định, Spring Data Auditing lấy thời gian hiện tại từ provider mặc định. Trong hệ thống cần kiểm thử xác định hoặc muốn thống nhất nguồn thời gian, có thể cung cấp **DateTimeProvider**.

~~~java
import java.time.Clock;
import java.time.temporal.TemporalAccessor;
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing(dateTimeProviderRef = "auditingDateTimeProvider")
public class JpaAuditingConfiguration {

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditingDateTimeProvider(Clock auditingClock) {
        return () -> Optional.<TemporalAccessor>of(
            auditingClock.instant()
        );
    }
}
~~~

**Clock.systemUTC()** tạo nguồn thời gian theo UTC. DateTimeProvider trả về thời điểm hiện tại để AuditingHandler gán vào các trường có annotation.

Lợi ích của cách này:

- Có một nguồn thời gian thống nhất trong ứng dụng.
- Có thể thay Clock bằng **Clock.fixed(...)** trong integration test.
- Kiểm thử không phụ thuộc vào thời gian thực của máy chạy test.
- Có thể điều khiển thời gian trong kịch bản kiểm thử tạo mới và cập nhật.

Ví dụ tạo Clock cố định trong test:

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-11-09T13:00:00Z"),
    ZoneOffset.UTC
);
~~~

Để kiểm tra **@LastModifiedDate**, test cần thay đổi thời điểm do Clock cung cấp giữa lần persist và lần update. Có thể dùng một Clock có thể điều khiển hoặc thay DateTimeProvider bằng implementation dành riêng cho test. Sau khi ghi dữ liệu, nên flush, clear persistence context và đọc lại entity để xác nhận giá trị từ database thay vì chỉ đọc object đang nằm trong bộ nhớ.

## 6. Kết hợp auditing với createdBy và lastModifiedBy

Ngoài thời gian, Spring Data Auditing còn hỗ trợ lưu người tạo và người sửa:

- **@CreatedBy**: người tạo entity.
- **@LastModifiedBy**: người sửa entity gần nhất.

Để điền các trường này, cần cung cấp **AuditorAware<T>**. Ví dụ, ứng dụng có thể lấy username từ Spring Security:

~~~java
@Bean
AuditorAware<String> auditorAware() {
    return () -> Optional.ofNullable(
        SecurityContextHolder.getContext().getAuthentication()
    )
    .filter(Authentication::isAuthenticated)
    .map(Authentication::getName);
}
~~~

Cấu hình đầy đủ cần import các kiểu từ Spring Security và khai báo bean trong application context. **@EnableJpaAuditing** sẽ sử dụng AuditorAware phù hợp; nếu có nhiều bean, có thể chỉ rõ tên bằng thuộc tính **auditorAwareRef**.

Ví dụ trường audit:

~~~java
@CreatedBy
@Column(updatable = false)
private String createdBy;

@LastModifiedBy
private String lastModifiedBy;
~~~

Nếu ứng dụng có tác vụ chạy nền không gắn với người dùng đăng nhập, AuditorAware cần định nghĩa cách biểu diễn actor hệ thống, ví dụ tài khoản service hoặc giá trị định danh đã thống nhất. Không nên để logic audit phụ thuộc vào một Authentication luôn tồn tại nếu các batch job cũng ghi entity.

## 7. Các thao tác có thể bỏ qua auditing

AuditingEntityListener hoạt động theo vòng đời entity do JPA quản lý. Một số thao tác cập nhật dữ liệu không đi qua lifecycle callback của từng entity.

### 7.1. Bulk JPQL UPDATE

Ví dụ:

~~~java
@Modifying
@Query("update Article a set a.title = :title where a.id = :id")
int renameDirectly(
    @Param("id") Long id,
    @Param("title") String title
);
~~~

Đây là bulk update. JPA gửi một câu UPDATE trực tiếp xuống database thay vì tải từng entity, thay đổi object và chạy callback cho từng bản ghi. Vì vậy, **@LastModifiedDate** không tự động được listener cập nhật.

Nếu vẫn cần cập nhật thời gian trong bulk query, phải đặt trường đó trực tiếp trong câu lệnh:

~~~java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Query("""
    update Article a
       set a.title = :title,
           a.lastModifiedAt = :modifiedAt
     where a.id = :id
    """)
int renameDirectly(
    @Param("id") Long id,
    @Param("title") String title,
    @Param("modifiedAt") Instant modifiedAt
);
~~~

Trong ví dụ này, phương thức gọi phải truyền thời điểm từ nguồn Clock thống nhất của ứng dụng. Việc clear persistence context giúp tránh tiếp tục dùng các entity đang được quản lý nhưng đã cũ sau bulk update. Cần cân nhắc transaction và flush trước khi chạy bulk query.

### 7.2. Native SQL và thao tác ngoài JPA

Các câu lệnh native SQL, stored procedure, ETL job hoặc ứng dụng khác ghi trực tiếp database cũng không gọi AuditingEntityListener. Nếu nhiều hệ thống cùng ghi một bảng, hãy thống nhất nơi chịu trách nhiệm cập nhật audit timestamp. Có thể dùng trigger database, hoặc yêu cầu mọi writer chủ động cập nhật trường audit theo một quy ước chung.

Không nên vừa dùng Spring auditing vừa dùng database trigger để ghi đè cùng một trường mà không xác định rõ nguồn dữ liệu chuẩn. Nếu hai nơi dùng timezone hoặc độ chính xác khác nhau, kết quả có thể khó dự đoán.

## 8. Kiểm thử auditing

Một integration test nên xác minh cả hai trường ở các thời điểm khác nhau:

1. Tạo entity mới và gọi repository.save(...).
2. Gọi repository.flush() để buộc đồng bộ.
3. Xóa persistence context bằng EntityManager.clear().
4. Đọc lại entity và xác nhận createdAt, lastModifiedAt đã được thiết lập.
5. Thay đổi Clock hoặc DateTimeProvider sang một thời điểm sau đó.
6. Tải entity, sửa một thuộc tính, flush và clear.
7. Đọc lại và xác nhận createdAt không đổi, lastModifiedAt được cập nhật.

Một số lưu ý khi viết test:

- Dùng database gần với production để kiểm tra ánh xạ timestamp và độ chính xác cột.
- Không so sánh nanosecond nếu database chỉ lưu precision thấp hơn.
- Không chỉ assert trên instance vừa save vì instance đó có thể vẫn nằm trong persistence context.
- Kiểm tra cả trường hợp entity không dirty để hiểu khi nào provider phát sinh UPDATE.
- Có test riêng cho bulk JPQL/native query vì listener không tự cập nhật audit fields trong các thao tác này.

## 9. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| createdAt hoặc lastModifiedAt vẫn null | Chưa bật @EnableJpaAuditing | Thêm cấu hình auditing vào application context |
| Listener không được gọi | Entity chưa đăng ký AuditingEntityListener | Thêm @EntityListeners hoặc đặt listener ở mapped superclass |
| Entity con không có trường audit | Lớp cha không phải @MappedSuperclass hoặc mapping không đúng | Kiểm tra kế thừa và mapping JPA |
| lastModifiedAt không đổi | Entity không dirty hoặc không phát sinh UPDATE | Kiểm tra dirty checking và SQL thực tế |
| Bulk update không đổi audit timestamp | Bulk JPQL/native SQL bỏ qua entity callback | Gán timestamp trực tiếp trong query hoặc cập nhật entity qua JPA |
| createdAt bị thay đổi ngoài ý muốn | Có setter hoặc logic ghi đè trường tạo | Hạn chế setter, dùng updatable=false và kiểm soát writer |
| Thời gian lệch giữa môi trường | Cấu hình timezone hoặc nguồn Clock không thống nhất | Chuẩn hóa UTC và kiểm tra JDBC/database |
| Test thời gian chập chờn | Test phụ thuộc đồng hồ thực hoặc độ chính xác database | Dùng Clock cố định/điều khiển và so sánh theo precision của cột |

Một số lỗi còn đến từ việc cấu hình auditing không nằm trong application context đang chạy test, hoặc entity listener được đặt trên một lớp không tham gia mapping. Khi debug, kiểm tra cấu hình Spring, mapping entity và lifecycle SQL trước khi thêm setter thủ công.

## 10. Checklist triển khai

- [ ] Đã bật **@EnableJpaAuditing** trong application context.
- [ ] Entity hoặc **@MappedSuperclass** đã khai báo **@EntityListeners(AuditingEntityListener.class)**.
- [ ] Đã import đúng **org.springframework.data.annotation.CreatedDate** và **LastModifiedDate**.
- [ ] Đã chọn kiểu thời gian theo ý nghĩa nghiệp vụ; ưu tiên **Instant** cho audit event toàn hệ thống.
- [ ] Trường tạo mới được bảo vệ khỏi cập nhật ngoài ý muốn.
- [ ] Đã thống nhất timezone và precision giữa Java, JDBC và database.
- [ ] Đã kiểm tra bulk JPQL, native SQL và các writer bên ngoài JPA.
- [ ] Integration test đã flush, clear và đọc lại dữ liệu từ database.
- [ ] Nếu cần createdBy/lastModifiedBy, đã cấu hình **AuditorAware** và actor cho tác vụ nền.

## 11. Ghi nhớ

**@CreatedDate** lưu thời điểm entity được tạo; **@LastModifiedDate** lưu thời điểm entity được sửa gần nhất. Cả hai cần auditing được bật và JPA entity listener được đăng ký. Với dữ liệu audit cần so sánh giữa nhiều máy chủ hoặc múi giờ, **Instant** thường là lựa chọn rõ ràng nhất vì nó biểu diễn một thời điểm trên UTC timeline.

Auditing chạy theo lifecycle của entity JPA. Những thay đổi được thực hiện bằng bulk query, native SQL hoặc công cụ bên ngoài sẽ bỏ qua listener, vì vậy cần cập nhật timestamp bằng một cơ chế có chủ đích. Hãy kiểm thử trên database thật hoặc tương đương production để xác nhận timezone, precision và hành vi callback.

