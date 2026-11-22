# Kích hoạt kiểm toán với @EnableJpaAuditing

## 1. Auditing trong Spring Data JPA là gì?

Auditing (kiểm toán dữ liệu) giúp ứng dụng tự động lưu thông tin về người tạo và thời điểm tạo entity, cũng như người sửa và thời điểm sửa gần nhất. Đây là metadata hữu ích để truy vết trách nhiệm, hiển thị lần cập nhật gần nhất và hỗ trợ vận hành.

Spring Data JPA cung cấp bốn annotation chính:

- **@CreatedBy**: người dùng hoặc tác nhân tạo bản ghi.
- **@CreatedDate**: thời điểm tạo bản ghi.
- **@LastModifiedBy**: người dùng hoặc tác nhân sửa bản ghi gần nhất.
- **@LastModifiedDate**: thời điểm sửa gần nhất.

Để các annotation này hoạt động, cần kích hoạt auditing bằng **@EnableJpaAuditing**, đăng ký **AuditingEntityListener** trên entity (hoặc lớp cha được ánh xạ), và cung cấp **AuditorAware** nếu muốn lưu thông tin người thực hiện.

Auditing của Spring Data JPA tự điền metadata trong vòng đời entity. Nó không tự tạo bản ghi lịch sử cho từng lần thay đổi, không thay thế nhật ký nghiệp vụ và không tự kiểm toán mọi câu lệnh SQL chạy trên database.

## 2. Các thành phần và luồng xử lý

| Thành phần | Vai trò |
|---|---|
| @EnableJpaAuditing | Bật cơ chế auditing trong cấu hình Spring |
| AuditingEntityListener | Nhận callback vòng đời entity từ JPA và gọi bộ xử lý auditing |
| @CreatedBy, @LastModifiedBy | Đánh dấu trường lưu người tạo/người sửa |
| @CreatedDate, @LastModifiedDate | Đánh dấu trường lưu thời điểm tạo/sửa |
| AuditorAware<T> | Cung cấp người dùng hiện tại có kiểu T |
| DateTimeProvider (tùy chọn) | Cung cấp thời gian hiện tại theo quy tắc của ứng dụng |

Luồng tổng quát:

1. Ứng dụng lưu entity thông qua EntityManager hoặc Spring Data repository.
2. JPA gọi callback trước khi insert hoặc update entity.
3. AuditingEntityListener chuyển callback đến bộ xử lý auditing của Spring Data.
4. Các trường được đánh dấu được điền từ AuditorAware và DateTimeProvider.
5. Khi JPA flush thay đổi xuống database, metadata được lưu cùng entity.

Gọi save() không có nghĩa dữ liệu đã commit ngay lập tức. Callback xảy ra trong quá trình persist/update hoặc flush; commit vẫn phụ thuộc transaction đang quản lý thao tác đó.

## 3. Bật auditing bằng @EnableJpaAuditing

Với Spring Boot, ứng dụng thường đã có cấu hình JPA và transaction manager thông qua dependency phù hợp, ví dụ spring-boot-starter-data-jpa. Thêm một lớp cấu hình được Spring component scan hoặc import vào application context:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing
public class JpaAuditingConfig {
}
```

Khi application context khởi tạo, **@EnableJpaAuditing** đăng ký hạ tầng auditing của Spring Data JPA. Chỉ bật annotation này chưa đủ để entity nhận callback: entity hoặc mapped superclass còn phải đăng ký **AuditingEntityListener**.

Nếu ứng dụng chỉ cần trường thời gian như CreatedDate và LastModifiedDate, không nhất thiết phải cung cấp AuditorAware. Nếu muốn tự động điền CreatedBy hoặc LastModifiedBy, cần có bean AuditorAware với kiểu trả về tương thích với trường auditor.

Có thể cấu hình rõ tên bean cung cấp auditor:

```java
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorProvider")
public class JpaAuditingConfig {

    @Bean
    public AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system");
    }
}
```

Ví dụ trên luôn gán người thực hiện là system, phù hợp cho demo hoặc tác vụ nền đơn giản. Trong ứng dụng thực tế, giá trị này nên lấy từ người dùng đã đăng nhập hoặc ngữ cảnh thực thi của tác vụ. Không dùng một chuỗi cố định nếu cần truy vết chính xác từng người dùng.

Khi có nhiều bean AuditorAware, thuộc tính **auditorAwareRef** giúp Spring chọn đúng bean. Tên truyền vào phải khớp tên bean trong application context.

## 4. Đăng ký AuditingEntityListener trên entity

JPA cần biết listener nào sẽ nhận callback vòng đời entity. Cách thông dụng là dùng **@EntityListeners**:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    // Constructor, getter và setter được lược bỏ.
}
```

Khi nhiều entity cần auditing, có thể gom các trường metadata vào lớp cha dùng **@MappedSuperclass** để tái sử dụng:

```java
import jakarta.persistence.Column;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.MappedSuperclass;
import java.time.Instant;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class AuditableEntity {

    @CreatedBy
    @Column(updatable = false)
    private String createdBy;

    @CreatedDate
    @Column(updatable = false)
    private Instant createdAt;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedAt;

    public String getCreatedBy() {
        return createdBy;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getLastModifiedBy() {
        return lastModifiedBy;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }
}
```

Entity nghiệp vụ kế thừa lớp cha sẽ thừa hưởng các trường auditing:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Customer extends AuditableEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public void rename(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Đây là các đoạn mã minh họa theo Jakarta Persistence (Spring Boot 3 trở lên). Các entity/repository khác và cấu hình datasource được lược bỏ. Trong Spring Boot 2 sử dụng JPA cũ, package persistence thường là javax.persistence thay vì jakarta.persistence; không trộn hai hệ package trong cùng ứng dụng.

Có thể đặt **@EntityListeners(AuditingEntityListener.class)** trực tiếp trên từng entity hoặc trên mapped superclass chung. Nếu listener không được đăng ký ở vị trí phù hợp, các trường auditing sẽ không tự động cập nhật.

Các annotation auditing như CreatedDate và LastModifiedDate thuộc package **org.springframework.data.annotation**, còn AuditingEntityListener thuộc package **org.springframework.data.jpa.domain.support**. Đây là hai nhóm package khác nhau; import nhầm annotation từ thư viện khác có thể khiến metadata không được nhận diện.

## 5. Cung cấp người thực hiện bằng AuditorAware

**AuditorAware<T>** là interface cho phép Spring Data hỏi ai đang thực hiện thao tác. Kiểu T phải tương thích với kiểu của trường được đánh dấu CreatedBy và LastModifiedBy.

Ví dụ đơn giản với kiểu String:

```java
import java.util.Optional;
import org.springframework.data.domain.AuditorAware;

public class SystemAuditorAware implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        return Optional.of("system");
    }
}
```

Trong ứng dụng có Spring Security, có thể lấy tên principal từ SecurityContext:

```java
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
public class AuditorConfiguration {

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
}
```

Cấu hình auditing cần tham chiếu đúng bean:

```java
@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorProvider")
public class JpaAuditingConfig {
}
```

Trong ứng dụng thật, chỉ khai báo một bean có tên auditorProvider cho mục đích này. Nếu gộp các ví dụ cấu hình thành một lớp, tránh khai báo trùng bean.

Một số lưu ý:

- **Không có Authentication**: trả về Optional.empty() nếu không có người dùng hiện tại. Các trường ngày vẫn có thể được điền; trường auditor sẽ không có giá trị mới từ AuditorAware.
- **Anonymous user**: không nên ghi tên anonymous như một người dùng thật. Ví dụ trên loại bỏ AnonymousAuthenticationToken.
- **Tác vụ nền**: scheduled job, message consumer hoặc batch process có thể không có SecurityContext. Có thể dùng auditor riêng như system hoặc batch-worker nếu quy ước nghiệp vụ yêu cầu.
- **Kiểu auditor**: nếu trường CreatedBy là Long, bean cần là AuditorAware<Long> và trả mã người dùng kiểu Long. Không trả tên String vào trường Long.
- **Ngữ cảnh bất đồng bộ**: SecurityContext không tự động có mặt trong mọi thread hoặc executor. Cần truyền/cấu hình security context phù hợp hoặc dùng auditor riêng cho tác vụ nền.

AuditorAware chỉ cung cấp giá trị được dùng khi callback auditing chạy. Nó không tự xác thực người dùng và không thay thế kiểm soát truy cập.

## 6. Tùy chỉnh thời gian bằng DateTimeProvider

Mặc định, auditing dùng thời gian hiện tại do provider mặc định cung cấp. Khi muốn thống nhất múi giờ, kiểm thử với đồng hồ cố định hoặc áp dụng nguồn thời gian riêng, có thể cấu hình **DateTimeProvider**.

Ví dụ dùng Clock của Java:

```java
import java.time.Clock;
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing(
        auditorAwareRef = "auditorProvider",
        dateTimeProviderRef = "auditingDateTimeProvider"
)
public class JpaAuditingConfig {

    @Bean
    public Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    public DateTimeProvider auditingDateTimeProvider(Clock auditingClock) {
        return () -> Optional.of(auditingClock.instant());
    }
}
```

DateTimeProvider trả về Optional chứa giá trị thời gian kiểu TemporalAccessor. Instant phù hợp với trường Instant trong entity và biểu diễn thời điểm tuyệt đối theo UTC. Khi hiển thị cho người dùng, ứng dụng có thể chuyển đổi sang múi giờ phù hợp.

Có thể dùng Clock cố định trong kiểm thử để kết quả thời gian ổn định. Tránh tạo nhiều nguồn thời gian khác nhau cho các trường auditing nếu cần so sánh thứ tự cập nhật nhất quán.

## 7. Thuộc tính quan trọng của @EnableJpaAuditing

| Thuộc tính | Ý nghĩa | Mặc định |
|---|---|---|
| auditorAwareRef | Tên bean AuditorAware được sử dụng | Để trống; auditor là tùy chọn nếu chỉ audit ngày |
| dateTimeProviderRef | Tên bean DateTimeProvider | Provider mặc định |
| setDates | Có tự điền các trường ngày tạo/sửa hay không | true |
| modifyOnCreate | Có điền các trường LastModified khi tạo mới hay không | true |
| auditingHandlerRef | Tên bean AuditingHandler tùy chỉnh | Để trống |

Hai thuộc tính dễ bị hiểu nhầm:

- **setDates = false** tắt việc tự điền các trường ngày, nhưng không đồng nghĩa với việc tắt auditing cho trường người tạo/người sửa.
- **modifyOnCreate = false** khiến các trường LastModifiedBy và LastModifiedDate không được thiết lập trong lần tạo mới. Khi entity được sửa sau đó, chúng mới được cập nhật theo quy tắc auditing.

Nếu cần cấu hình mặc định, chỉ dùng **@EnableJpaAuditing** là đủ. Chỉ thêm thuộc tính khi ứng dụng thực sự cần tùy chỉnh.

## 8. Kiểu dữ liệu và cách tổ chức metadata

Spring Data hỗ trợ các kiểu thời gian phổ biến như Instant, LocalDateTime, OffsetDateTime, Date và Calendar tùy cấu hình mapping/provider. Với hệ thống phân tán, lưu **Instant** thường thuận tiện vì biểu diễn một thời điểm tuyệt đối; chuyển đổi múi giờ ở tầng hiển thị.

Các trường auditor có thể là String, Long hoặc kiểu định danh người dùng của ứng dụng. Kiểu generic của AuditorAware phải khớp với kiểu dữ liệu tương ứng.

Có hai cách tổ chức metadata:

**Dùng mapped superclass**

- Các trường auditing nằm trực tiếp trong lớp cha.
- Entity con kế thừa thuộc tính và listener.
- Dễ truy vấn các trường auditing như thuộc tính bình thường của entity.
- Phù hợp khi nhiều entity có cùng cấu trúc audit.

**Dùng embedded object**

- Gom các trường audit vào một lớp @Embeddable.
- Entity chứa một thuộc tính @Embedded.
- Giúp nhóm metadata về mặt mô hình domain.
- Cần đảm bảo listener auditing được đăng ký cho entity và mapping embedded hoạt động đúng.

Ví dụ cấu trúc embedded (lược bỏ getter/setter):

```java
@Embeddable
public class AuditMetadata {

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedAt;
}

@Entity
@EntityListeners(AuditingEntityListener.class)
public class Invoice {

    @Id
    @GeneratedValue
    private Long id;

    @Embedded
    private AuditMetadata audit = new AuditMetadata();
}
```

Cách embedded hữu ích khi muốn tách nhóm metadata, nhưng hãy kiểm thử mapping và callback trên phiên bản Spring Data JPA/JPA provider đang dùng. Với người mới học hoặc mô hình đơn giản, mapped superclass thường dễ hiểu và dễ kiểm tra hơn.

## 9. Kiểm thử auditing

Nên kiểm thử bằng repository và database test thực tế (ví dụ H2 trong test slice) thay vì chỉ mock AuditorAware hoặc repository. Bài test cần xác nhận callback JPA đã điền dữ liệu và giá trị được lưu sau flush.

Ví dụ với Spring Boot test:

```java
@DataJpaTest
@Import(TestAuditingConfig.class)
class CustomerAuditingTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void shouldPopulateCreatedAndModifiedMetadata() {
        Customer customer = new Customer("Lan");

        Customer saved = customerRepository.saveAndFlush(customer);

        assertEquals("test-user", saved.getCreatedBy());
        assertNotNull(saved.getCreatedAt());
        assertEquals("test-user", saved.getLastModifiedBy());
        assertNotNull(saved.getLastModifiedAt());

        saved.rename("Lan Nguyen");
        Customer updated = customerRepository.saveAndFlush(saved);

        assertNotNull(updated.getLastModifiedAt());
        assertEquals("test-user", updated.getLastModifiedBy());
    }
}

@Configuration
@EnableJpaAuditing(auditorAwareRef = "testAuditor")
class TestAuditingConfig {

    @Bean
    AuditorAware<String> testAuditor() {
        return () -> Optional.of("test-user");
    }
}
```

Đây là ví dụ kiểm thử minh họa; cần có CustomerRepository extends JpaRepository<Customer, Long>, các import JUnit/Spring Boot Test, entity Customer kế thừa AuditableEntity và cấu hình test được nạp vào context. Các import bổ sung gồm DataJpaTest, Import, Autowired, Test, Configuration, Bean, Optional và AuditorAware. Trong dự án thực tế, có thể dùng @Import để nạp cấu hình auditing hiện có thay vì khai báo cấu hình test riêng.

Các assertion quan trọng:

- Sau insert, CreatedBy và CreatedDate phải có giá trị.
- Theo mặc định, LastModifiedBy và LastModifiedDate cũng được điền khi insert vì modifyOnCreate là true.
- Sau update thực sự và flush, các trường LastModified phản ánh auditor và thời điểm cập nhật.
- Các trường Created nên giữ nguyên trong lần update; có thể dùng @Column(updatable = false) để ngăn JPA đưa chúng vào câu lệnh update.

Nếu kiểm thử thời gian chính xác, cung cấp Clock cố định và DateTimeProvider sử dụng Clock đó. Nếu kiểm tra giá trị thay đổi giữa hai lần update, dùng clock có thể tiến về phía trước thay vì clock cố định.

## 10. Giới hạn: Auditing không phải lịch sử thay đổi đầy đủ

Spring Data JPA auditing chủ yếu ghi nhận người tạo, thời điểm tạo, người sửa gần nhất và thời điểm sửa gần nhất trên chính entity. Nó không tự lưu snapshot của từng phiên bản dữ liệu.

Một số thao tác có thể bỏ qua callback entity:

- Bulk JPQL update/delete thông qua @Modifying.
- Native SQL trực tiếp.
- JdbcTemplate hoặc thao tác SQL ngoài EntityManager.
- Thay đổi trực tiếp từ công cụ quản trị database hoặc ứng dụng khác.

Ví dụ, một bulk update có thể thay đổi hàng trăm bản ghi trong database mà không gọi AuditingEntityListener cho từng entity. Nếu cần cập nhật trường LastModified trong thao tác bulk, phải đưa logic đó vào câu lệnh update hoặc xử lý theo cơ chế riêng.

Nếu yêu cầu lưu mọi phiên bản của entity, người dùng thay đổi, thời điểm, giá trị cũ và giá trị mới, hãy cân nhắc giải pháp lưu lịch sử chuyên biệt như Hibernate Envers, bảng audit do ứng dụng quản lý, hoặc event sourcing. Không nhầm bốn trường metadata của Spring Data với một hệ thống audit trail đầy đủ.

## 11. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| CreatedDate/LastModifiedDate luôn null | Chưa bật @EnableJpaAuditing hoặc listener chưa đăng ký | Kiểm tra config được Spring scan và @EntityListeners |
| CreatedBy/LastModifiedBy null | Chưa có AuditorAware hoặc auditor trả Optional.empty() | Đăng ký đúng bean, kiểm tra SecurityContext và tên bean tham chiếu |
| Không tìm thấy AuditorAware bean | auditorAwareRef sai tên hoặc bean chưa được scan | Khớp tên bean và package cấu hình |
| Trường auditor sai kiểu | AuditorAware<T> không khớp kiểu trường entity | Dùng cùng kiểu T hoặc chuyển đổi định danh rõ ràng |
| Người tạo bị thay đổi khi update | Mapping cho phép ghi lại trường created | Kiểm tra annotation và đặt @Column(updatable = false) khi phù hợp |
| LastModified không được điền khi insert | modifyOnCreate đã được đặt false | Đặt true nếu muốn điền trường LastModified ngay khi tạo |
| Bulk update không cập nhật audit | Bulk/native SQL bỏ qua entity lifecycle callback | Cập nhật audit field trong câu lệnh hoặc đổi chiến lược ghi |
| Test chạy qua nhưng dữ liệu chưa có | Chưa flush hoặc test không nạp auditing config | Dùng saveAndFlush và kiểm tra application context |

Khi debug, kiểm tra theo thứ tự:

1. Lớp có @EnableJpaAuditing có thực sự được nạp vào application context không?
2. Entity hoặc mapped superclass có đăng ký AuditingEntityListener không?
3. AuditorAware có được tìm thấy và trả về đúng kiểu dữ liệu không?
4. Entity có đi qua vòng đời persist/update của JPA không?
5. Thao tác có phải bulk/native SQL bỏ qua callback không?
6. Cấu hình setDates và modifyOnCreate có đúng kỳ vọng không?

## 12. Ghi nhớ

- **@EnableJpaAuditing** kích hoạt hạ tầng auditing của Spring Data JPA.
- **@EntityListeners(AuditingEntityListener.class)** đăng ký listener để nhận callback vòng đời entity.
- **@CreatedBy** và **@LastModifiedBy** lấy người thực hiện từ **AuditorAware<T>**.
- **@CreatedDate** và **@LastModifiedDate** lấy thời gian từ **DateTimeProvider**; mặc định dùng provider thời gian hiện tại.
- Mặc định **modifyOnCreate = true**, vì vậy các trường LastModified cũng được điền lúc tạo entity.
- Listener chỉ hoạt động khi entity đi qua lifecycle của JPA; bulk update, native SQL và JDBC trực tiếp không tự kích hoạt auditing callback.
- Auditing lưu metadata tạo/sửa gần nhất, không phải lịch sử đầy đủ của mọi lần thay đổi.

## 13. Tài liệu tham khảo

- [Spring Data JPA — Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html)
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Spring Framework — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
