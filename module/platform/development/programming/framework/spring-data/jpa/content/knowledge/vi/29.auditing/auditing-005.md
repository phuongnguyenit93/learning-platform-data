# Cấu hình AuditingEntityListener và lớp thuộc tính dùng chung

Spring Data JPA Auditing tự động ghi nhận thông tin người tạo và thời điểm tạo, người sửa cuối cùng và thời điểm sửa cuối cùng của Entity. Cơ chế này hữu ích cho các bảng nghiệp vụ cần biết ai đã tạo dữ liệu, dữ liệu được tạo lúc nào và lần cập nhật gần nhất diễn ra khi nào.

Để auditing hoạt động, ứng dụng cần bật cấu hình Spring Data JPA Auditing, đăng ký `AuditingEntityListener` với JPA và đánh dấu các thuộc tính cần theo dõi bằng `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy` hoặc `@LastModifiedBy`. Khi nhiều Entity dùng chung các trường audit, có thể gom chúng vào một lớp `@MappedSuperclass` để tái sử dụng mapping và listener.

## 1. Auditing là gì và dùng để làm gì?

Auditing lưu metadata mô tả vòng đời của dữ liệu. Một bản ghi thường có bốn thông tin:

| Thuộc tính | Annotation | Ý nghĩa |
|---|---|---|
| createdAt | `@CreatedDate` | Thời điểm Entity được tạo |
| createdBy | `@CreatedBy` | Tác nhân tạo Entity |
| lastModifiedAt | `@LastModifiedDate` | Thời điểm Entity được sửa gần nhất |
| lastModifiedBy | `@LastModifiedBy` | Tác nhân sửa Entity gần nhất |

Ví dụ một bản ghi đơn hàng có thể lưu:
- createdAt = thời điểm đơn hàng được tạo.
- createdBy = mã người dùng hoặc tài khoản dịch vụ tạo đơn.
- lastModifiedAt = thời điểm trạng thái hoặc thông tin đơn hàng được cập nhật gần nhất.
- lastModifiedBy = người hoặc tiến trình thực hiện lần cập nhật đó.

Auditing hữu ích cho:
- Truy vết thay đổi trong ứng dụng quản trị.
- Hỗ trợ điều tra lỗi và đối soát dữ liệu.
- Hiển thị thông tin “được tạo bởi” hoặc “cập nhật lúc”.
- Phục vụ quy trình kiểm soát nội bộ.
- Xác định dữ liệu được tạo bởi người dùng hay tác vụ nền.

Auditing metadata không phải lịch sử đầy đủ mọi phiên bản của Entity. Các trường lastModified chỉ giữ thông tin lần cập nhật gần nhất. Nếu cần lưu toàn bộ lịch sử thay đổi, hãy xem xét audit log riêng, event log hoặc Hibernate Envers.

## 2. Các annotation auditing

Spring Data cung cấp bốn annotation chính trong package `org.springframework.data.annotation`:

- `@CreatedDate`: đánh dấu thời điểm tạo.
- `@LastModifiedDate`: đánh dấu thời điểm cập nhật gần nhất.
- `@CreatedBy`: đánh dấu auditor tạo bản ghi.
- `@LastModifiedBy`: đánh dấu auditor cập nhật gần nhất.

Ví dụ:

~~~java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant lastModifiedAt;

@CreatedBy
private String createdBy;

@LastModifiedBy
private String lastModifiedBy;
~~~

Các annotation này chỉ mô tả metadata cần auditing xử lý. Chúng không tự hoạt động nếu ứng dụng chưa bật auditing và Entity chưa được gắn listener phù hợp.

Với ứng dụng mới, các kiểu `java.time` như `Instant` hoặc `LocalDateTime` thường là lựa chọn rõ ràng. `Instant` biểu diễn một thời điểm trên timeline và thường thuận tiện khi lưu thời gian UTC; `LocalDateTime` không chứa timezone/offset nên cần quy ước múi giờ rõ ràng ở tầng ứng dụng và database.

Kiểu của `@CreatedBy` và `@LastModifiedBy` phải tương thích với kiểu generic của `AuditorAware<T>`. Nếu auditor là username dạng chuỗi, dùng `AuditorAware<String>` và trường audit kiểu String. Nếu dùng ID người dùng kiểu Long, dùng `AuditorAware<Long>`.

## 3. Vai trò của AuditingEntityListener

`AuditingEntityListener` là JPA entity listener do Spring Data JPA cung cấp:

~~~java
import org.springframework.data.jpa.domain.support.AuditingEntityListener;
~~~

Listener kết nối các callback vòng đời JPA với auditing handler của Spring Data. Về cơ bản:
- Khi Entity được persist lần đầu, callback tạo mới gọi xử lý auditing.
- Khi Entity được cập nhật, callback cập nhật gọi xử lý auditing.
- Handler đọc thông tin auditor hiện tại và thời gian hiện tại rồi gán vào các thuộc tính được đánh dấu.

Đăng ký listener bằng annotation JPA:

~~~java
@EntityListeners(AuditingEntityListener.class)
~~~

Ví dụ đặt trên Entity:

~~~java
@Entity
@EntityListeners(AuditingEntityListener.class)
public class Customer {
    // Các thuộc tính Entity.
}
~~~

Khi Customer được persist/update qua JPA, listener có thể cập nhật các trường auditing trước khi thay đổi được đồng bộ xuống database.

Nếu có nhiều Entity cùng cần auditing, không nên lặp lại cấu hình và bốn trường trên từng lớp. Có thể đặt listener cùng các thuộc tính audit trong một mapped superclass.

## 4. Bật auditing bằng @EnableJpaAuditing

Ứng dụng cần bật auditing trong cấu hình Spring:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing
public class JpaAuditingConfiguration {
}
~~~

`@EnableJpaAuditing` đăng ký hạ tầng cần thiết để Spring Data xử lý các annotation auditing.

Nếu chỉ cần ngày tạo và ngày cập nhật, cấu hình tối thiểu này có thể đủ. Nếu cần trường người tạo/người sửa, hãy cung cấp bean `AuditorAware`. Nếu muốn kiểm soát nguồn thời gian, có thể cung cấp `DateTimeProvider`.

Hai thuộc tính cấu hình đáng chú ý:
- `auditorAwareRef`: tên bean cung cấp auditor hiện tại.
- `dateTimeProviderRef`: tên bean cung cấp thời điểm hiện tại.

`modifyOnCreate` mặc định là true, nghĩa là các trường sửa đổi cũng có thể được điền trong lần tạo đầu tiên. Nếu đặt false, metadata sửa đổi không được thiết lập trong quá trình tạo theo cấu hình này. `setDates` mặc định bật việc gán các trường ngày.

## 5. Cung cấp auditor bằng AuditorAware

Auditor là tác nhân thực hiện thao tác ghi. Trong ứng dụng web có Spring Security, auditor thường được lấy từ Authentication hiện tại.

Ví dụ:

~~~java
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
    AuditorAware<String> auditorAware() {
        return () -> {
            Authentication authentication =
                    SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return Optional.empty();
            }

            return Optional.ofNullable(authentication.getName());
        };
    }
}
~~~

Giải thích:
1. Lấy Authentication từ SecurityContextHolder.
2. Nếu không có authentication, chưa xác thực hoặc là anonymous, trả Optional.empty().
3. Nếu đã xác thực, dùng authentication.getName() làm auditor.
4. Spring Data gán giá trị đó vào các trường CreatedBy/LastModifiedBy.

Cấu hình này yêu cầu ứng dụng có Spring Security. Nếu dự án không dùng Spring Security, hãy triển khai AuditorAware bằng nguồn phù hợp, ví dụ user context của ứng dụng, thông tin tenant hoặc một service xác định tác nhân hiện tại.

Không nên trả username giả định cho mọi request. Nếu auditor không tồn tại, quyết định rõ trường auditor có được phép null hay ứng dụng cần một tài khoản hệ thống. Database constraint và quy tắc nghiệp vụ phải nhất quán với lựa chọn đó.

## 6. Auditor cho tác vụ nền và hệ thống

Không phải mọi thao tác ghi đều xuất phát từ HTTP request. Dữ liệu cũng có thể được tạo bởi:
- Scheduler.
- Batch import.
- Message consumer.
- Tác vụ đồng bộ.
- Công việc bảo trì.
- Quy trình tự động.

Các luồng này có thể không có SecurityContext. Khi đó, `AuditorAware` có thể trả Optional.empty() hoặc dùng một định danh hệ thống theo quy ước ứng dụng, chẳng hạn `system`, `batch-import` hoặc service account ID.

Ví dụ một provider đơn giản có fallback cho tác vụ không có người dùng:

~~~java
@Bean
AuditorAware<String> auditorAware() {
    return () -> {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return Optional.of("system");
        }

        return Optional.ofNullable(authentication.getName());
    };
}
~~~

Fallback `system` chỉ là một chính sách minh họa. Hệ thống thực tế có thể cần phân biệt batch, scheduler và service account để truy vết chính xác hơn.

Với xử lý bất đồng bộ, thread mới không nhất thiết kế thừa SecurityContext của thread gọi. Không dựa vào việc context luôn có mặt trong scheduler hoặc message listener. Hãy truyền danh tính tác nhân qua message/job metadata hoặc cung cấp auditor hệ thống một cách tường minh.

## 7. Dùng DateTimeProvider để kiểm soát thời gian

Mặc định Spring Data sử dụng nguồn thời gian hiện tại. Có thể cung cấp DateTimeProvider nếu muốn chuẩn hóa timezone, dùng Clock để test hoặc kiểm soát nguồn thời gian.

Ví dụ dùng Instant UTC:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;

@Configuration
public class AuditingTimeConfiguration {

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider dateTimeProvider(Clock auditingClock) {
        return () -> Optional.of(Instant.now(auditingClock));
    }
}
~~~

Kết nối bean vào auditing:

~~~java
@Configuration
@EnableJpaAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "dateTimeProvider"
)
public class JpaAuditingConfiguration {
}
~~~

DateTimeProvider trả về Optional của TemporalAccessor. Instant triển khai TemporalAccessor nên có thể dùng trực tiếp với trường audit kiểu Instant.

Dùng Clock thay vì gọi Instant.now() rải rác giúp test có thể kiểm soát thời gian. Trong môi trường production, Clock.systemUTC() là một lựa chọn phổ biến; database column type và JDBC mapping vẫn cần được cấu hình nhất quán.

## 8. Tạo lớp thuộc tính dùng chung bằng @MappedSuperclass

Nếu nhiều Entity có cùng bốn trường audit, có thể khai báo chúng trong một lớp cơ sở:

~~~java
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.MappedSuperclass;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class AuditableEntity {

    @CreatedDate
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @CreatedBy
    @Column(name = "created_by", updatable = false)
    private String createdBy;

    @LastModifiedDate
    @Column(name = "last_modified_at")
    private Instant lastModifiedAt;

    @LastModifiedBy
    @Column(name = "last_modified_by")
    private String lastModifiedBy;

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }

    public String getLastModifiedBy() {
        return lastModifiedBy;
    }
}
~~~

Ý nghĩa:
- `@MappedSuperclass` cho biết lớp này cung cấp mapping cho các Entity con, nhưng bản thân nó không phải Entity độc lập để truy vấn.
- Các trường được kế thừa và ánh xạ vào bảng của từng Entity con.
- `@EntityListeners` đăng ký AuditingEntityListener cho các Entity sử dụng lớp cơ sở.
- `updatable = false` ngăn JPA đưa createdAt/createdBy vào câu UPDATE thông thường sau khi tạo.
- Getter cho phép ứng dụng đọc metadata audit mà không cung cấp setter tùy tiện.

JPA cho phép mapping và entity listener được khai báo trên mapped superclass để áp dụng cho các Entity kế thừa. Khi listener đã được đăng ký ở lớp cơ sở, không cần lặp lại cùng listener ở mọi Entity con trừ khi có lý do mapping rõ ràng.

## 9. Kế thừa lớp audit trong các Entity

Ví dụ Customer và PurchaseOrder dùng chung lớp AuditableEntity:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer extends AuditableEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder extends AuditableEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String orderNumber;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }
}
~~~

Hai bảng customers và purchase_orders đều có các cột audit theo mapping kế thừa. Mỗi Entity có thể bổ sung thuộc tính nghiệp vụ riêng mà không phải khai báo lại createdAt, createdBy, lastModifiedAt và lastModifiedBy.

Nếu lớp cơ sở chứa các trường có tên trùng với thuộc tính của Entity con, cần xử lý mapping rõ ràng bằng override phù hợp hoặc đổi tên thuộc tính. Không để hai thuộc tính cùng ánh xạ vào một cột một cách vô ý.

## 10. @MappedSuperclass khác với @Entity inheritance

Không nên nhầm `@MappedSuperclass` với một Entity trong chiến lược kế thừa JPA.

| Đặc điểm | @MappedSuperclass | Entity inheritance |
|---|---|---|
| Có bảng riêng | Không | Tùy inheritance strategy |
| Có thể truy vấn trực tiếp | Không | Có thể truy vấn Entity gốc |
| Mục đích | Chia sẻ mapping/thuộc tính | Mô hình hóa quan hệ kế thừa Entity |
| Trường kế thừa | Được ánh xạ vào bảng Entity con | Ánh xạ theo chiến lược kế thừa |
| Dùng cho audit fields | Rất phù hợp | Có thể dùng nhưng thường phức tạp hơn cần thiết |

Với lớp chỉ chia sẻ metadata audit, `@MappedSuperclass` thường đơn giản hơn vì không tạo một Entity gốc cần quản lý trong persistence context.

Nếu nghiệp vụ thực sự có quan hệ is-a giữa các Entity và cần truy vấn theo kiểu cha, hãy chọn một JPA inheritance strategy như SINGLE_TABLE, JOINED hoặc TABLE_PER_CLASS. Không dùng Entity inheritance chỉ để tái sử dụng bốn trường audit.

## 11. Vị trí đặt @EntityListeners

Có hai cách thường gặp:

**Đăng ký trên từng Entity**

~~~java
@Entity
@EntityListeners(AuditingEntityListener.class)
public class Customer {
}
~~~

Cách này dễ thấy listener ngay trên Entity, nhưng phải lặp lại ở mọi Entity cần auditing.

**Đăng ký trên mapped superclass**

~~~java
@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class AuditableEntity {
}
~~~

Các Entity kế thừa dùng chung mapping và listener. Đây thường là cách gọn hơn khi phần lớn Entity trong module cần auditing.

Chọn một quy ước nhất quán. Tránh đăng ký cùng listener lặp lại ở cả lớp cơ sở và Entity con nếu không hiểu rõ thứ tự callback và hành vi kế thừa của JPA. Nếu có Entity đặc biệt không cần listener của lớp cha, JPA có annotation loại trừ listener superclass; hãy dùng theo đúng quy tắc mapping và kiểm thử trên provider của dự án.

## 12. Access type: field access và property access

JPA xác định access type dựa trên vị trí các annotation mapping như `@Id`, trừ khi được chỉ định rõ bằng `@Access`.

Nếu Entity dùng field access (đặt `@Id` trên field), các annotation mapping trong lớp mapped superclass nên nhất quán với field access. Ví dụ AuditableEntity đặt `@CreatedDate` và `@Column` trực tiếp trên field như phần trước.

Nếu dự án dùng property access (đặt `@Id` trên getter), cần thiết kế lớp audit theo property access tương ứng hoặc khai báo `@Access` rõ ràng. Trộn annotation trên field và getter mà không có chủ đích có thể khiến provider bỏ qua mapping hoặc báo lỗi.

Hãy giữ một access strategy nhất quán cho Entity hierarchy. Nếu lớp cơ sở và lớp con cần access strategy khác nhau, phải cấu hình và kiểm tra rõ ràng theo Jakarta Persistence.

## 13. Tạo bảng và migration cho các cột audit

Lớp mapped superclass không tạo bảng riêng. Mỗi Entity con cần các cột tương ứng trong bảng của nó.

Ví dụ DDL minh họa:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by VARCHAR(100),
    last_modified_at TIMESTAMP WITH TIME ZONE,
    last_modified_by VARCHAR(100)
);
~~~

Kiểu SQL cụ thể phụ thuộc database. `Instant` có thể được ánh xạ sang kiểu timestamp phù hợp với dialect/JDBC driver; hãy kiểm tra schema thực tế thay vì giả định mọi database đều dùng cùng kiểu.

Trong production, nên quản lý schema bằng Flyway hoặc Liquibase. Annotation `@Column(nullable = false)` và `updatable = false` mô tả mapping cho JPA/schema generation; chúng không tự sửa một bảng đã tồn tại nếu ứng dụng không chạy cơ chế cập nhật schema.

Nếu createdAt là NOT NULL, auditing phải được bật và listener phải chạy trước khi INSERT. Khi import dữ liệu cũ hoặc ghi bằng SQL trực tiếp, cần cung cấp giá trị created_at tương ứng hoặc thiết kế default/nullable/migration phù hợp.

## 14. Khi nào các trường audit được cập nhật?

Auditing được gắn với lifecycle callback của JPA:

- Khi Entity được persist lần đầu, trường tạo được thiết lập.
- Khi Entity được cập nhật và callback update chạy, trường sửa đổi được cập nhật.
- Với cấu hình `modifyOnCreate = true`, trường sửa đổi cũng có thể được thiết lập ở lần tạo đầu tiên.
- Với `modifyOnCreate = false`, trường sửa đổi không được thiết lập trong quá trình tạo theo cấu hình auditing.

Việc cập nhật phụ thuộc Entity thực sự đi qua lifecycle của JPA. Một Entity được load rồi thay đổi thuộc tính và flush/commit sẽ được provider xử lý update khi có thay đổi cần ghi.

Không phải mọi thao tác database đều kích hoạt entity listener:
- JPQL bulk UPDATE/DELETE chạy trực tiếp trên tập dữ liệu và bỏ qua lifecycle callback của từng Entity.
- Native SQL cũng không gọi AuditingEntityListener.
- JDBC trực tiếp không kích hoạt callback JPA.
- Thay đổi một Entity con không nhất thiết làm Entity cha trở thành dirty và cập nhật lastModifiedAt của cha.

Nếu dùng bulk update, hãy cập nhật trường audit tường minh trong câu query hoặc chọn cách cập nhật từng Entity qua persistence context nếu cần listener. Sau bulk operation, cân nhắc clear/refresh persistence context để tránh Entity đang managed giữ dữ liệu cũ.

## 15. Phân biệt auditing với @PrePersist và @PreUpdate tự viết

JPA cho phép tự khai báo lifecycle callback:

~~~java
@PrePersist
void onCreate() {
    createdAt = Instant.now();
}

@PreUpdate
void onUpdate() {
    lastModifiedAt = Instant.now();
}
~~~

Cách tự viết có thể đủ cho ứng dụng nhỏ, nhưng thường dẫn đến:
- Lặp code giữa nhiều Entity.
- Không có cơ chế chuẩn để lấy auditor hiện tại.
- Khó thay nguồn thời gian trong test.
- Mỗi Entity có thể triển khai quy tắc khác nhau.
- Khó kết hợp với Spring Security hoặc tác vụ nền.

Spring Data Auditing cung cấp listener, handler, AuditorAware và DateTimeProvider để thống nhất logic. Không nên đồng thời tự gán cùng trường audit trong callback riêng và để AuditingEntityListener cũng gán, vì hai cơ chế có thể ghi đè nhau tùy thứ tự callback.

Nếu có quy tắc đặc thù, hãy mở rộng thiết kế có chủ đích và chỉ để một cơ chế chịu trách nhiệm cho mỗi trường.

## 16. Cấu hình hoàn chỉnh cho Spring Boot 3

Ví dụ cấu hình tổng hợp dùng Jakarta Persistence, auditor từ Spring Security và thời gian UTC:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
@EnableJpaAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "dateTimeProvider",
        modifyOnCreate = true
)
public class JpaAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> {
            Authentication authentication =
                    SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return Optional.empty();
            }

            return Optional.ofNullable(authentication.getName());
        };
    }

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider dateTimeProvider(Clock auditingClock) {
        return () -> Optional.of(Instant.now(auditingClock));
    }
}
~~~

Nếu không dùng Spring Security, thay bean auditorAware bằng implementation lấy tác nhân từ context/service riêng. Nếu không cần lưu người tạo/người sửa, có thể bỏ auditorAware và chỉ dùng các annotation ngày.

Đặt cấu hình trong package được component scan hoặc import rõ ràng. Với nhiều persistence unit, hãy xác định auditing configuration áp dụng cho đúng EntityManagerFactory và mapping context; không giả định một cấu hình tự động áp dụng đồng nhất cho mọi datasource.

## 17. Kiểm thử auditing khi tạo Entity

Một test repository có thể xác nhận trường ngày và auditor được gán khi persist.

Ví dụ:

~~~java
@DataJpaTest
@Import(JpaAuditingConfiguration.class)
class CustomerAuditingTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void setsAuditFieldsWhenCustomerIsCreated() {
        Customer customer = customerRepository.save(
                new Customer("An")
        );

        assertNotNull(customer.getCreatedAt());
        assertNotNull(customer.getLastModifiedAt());
    }
}
~~~

Đây là cấu trúc minh họa. Nếu cấu hình auditor lấy từ Spring Security, test cần thiết lập Authentication hoặc dùng một AuditorAware test cố định. Nếu dự án dùng Spring Boot 3, các annotation persistence phải thuộc package `jakarta.persistence`.

Để kiểm tra dữ liệu đã được ghi xuống database, gọi flush và đọc lại Entity sau khi clear persistence context:

~~~java
customerRepository.save(customer);
entityManager.flush();
entityManager.clear();

Customer reloaded = customerRepository.findById(customer.getId())
        .orElseThrow();

assertNotNull(reloaded.getCreatedAt());
~~~

Flush đồng bộ các thay đổi đang chờ xuống database nhưng không đồng nghĩa commit. Trong test có transaction bao ngoài, dữ liệu có thể vẫn rollback khi test kết thúc.

## 18. Kiểm thử auditor và cập nhật Entity

Để xác nhận CreatedBy và LastModifiedBy, thiết lập auditor test có giá trị xác định. Có thể dùng một AuditorAware test trả về `Optional.of("test-user")`, hoặc thiết lập Spring Security Authentication.

Các trường hợp nên kiểm tra:
1. Tạo Entity: createdAt và createdBy được gán.
2. Tạo Entity với modifyOnCreate mặc định: lastModifiedAt và lastModifiedBy được gán nếu auditor có mặt.
3. Cập nhật Entity: lastModifiedAt và lastModifiedBy thay đổi theo tác nhân hiện tại.
4. Không có auditor: xác nhận hành vi Optional.empty() và khả năng null của schema.
5. Tác vụ nền: auditor là system/service account theo chính sách.
6. Bulk JPQL update: listener không tự chạy; câu update phải quản lý audit field riêng.
7. Nhiều Entity kế thừa mapped superclass: tất cả dùng cùng mapping và listener.
8. Entity đặc biệt loại trừ listener superclass: xác nhận không nhận audit callback ngoài ý muốn.

Khi test thời gian cập nhật, tránh giả định hai lần gọi clock luôn khác nhau nếu database chỉ lưu timestamp với độ chính xác giới hạn. Có thể inject Clock có thể điều khiển trong test hoặc chỉ kiểm tra timestamp hợp lệ theo precision của database.

## 19. Những lỗi thường gặp

**Chỉ thêm @CreatedDate nhưng quên bật @EnableJpaAuditing**

Annotation không tự hoạt động. Bật auditing trong cấu hình Spring.

**Quên đăng ký AuditingEntityListener**

Nếu listener không được gọi, các trường audit có thể vẫn null. Đăng ký listener trên Entity hoặc mapped superclass.

**Dùng @MappedSuperclass nhưng mong có bảng riêng**

Mapped superclass chỉ chia sẻ mapping; bảng được tạo cho các Entity con.

**AuditorAware có generic type không khớp trường @CreatedBy**

Ví dụ AuditorAware<Long> nhưng createdBy là String có thể gây lỗi chuyển đổi hoặc mapping. Dùng cùng kiểu dữ liệu.

**SecurityContext không tồn tại trong batch hoặc async**

Luồng nền có thể không có Authentication. Trả Optional.empty() hoặc cung cấp auditor hệ thống theo chính sách.

**Đăng ký listener lặp lại**

Đặt listener ở superclass và lại đăng ký ở từng Entity con có thể làm callback chạy theo cấu hình kế thừa nhiều lần. Chọn một vị trí đăng ký rõ ràng và kiểm thử.

**Bulk update không cập nhật audit field**

JPQL bulk DML và native SQL bỏ qua entity lifecycle callback. Cập nhật audit field trong query hoặc dùng cách cập nhật qua Entity.

**Cho rằng sửa Entity con luôn cập nhật thời gian Entity cha**

JPA chỉ gọi callback update cho Entity thực sự được cập nhật. Nếu cần timestamp cha thay đổi khi collection con đổi, hãy thiết kế hành vi đó tường minh.

**Lưu LocalDateTime mà không có quy ước timezone**

LocalDateTime không chứa timezone. Dùng Instant hoặc xác định rõ quy tắc chuyển đổi thời gian.

**Dùng @Column(nullable = false) nhưng schema cũ chưa có cột**

Cần migration database trước khi ứng dụng ghi Entity. Annotation không thay thế migration production.

**Vừa dùng AuditingEntityListener vừa tự gán cùng trường trong @PrePersist/@PreUpdate**

Hai cơ chế có thể ghi đè nhau. Chỉ định một nguồn chịu trách nhiệm cho từng trường.

## 20. Quy trình triển khai auditing dùng chung

Khi thêm auditing vào một module:

1. Xác định cần lưu thời điểm, auditor hay cả hai.
2. Chọn kiểu dữ liệu nhất quán: thường là Instant cho timestamp và String/Long cho auditor.
3. Tạo lớp abstract `@MappedSuperclass` chứa các trường audit.
4. Đặt `@EntityListeners(AuditingEntityListener.class)` trên lớp cơ sở hoặc từng Entity theo một quy ước thống nhất.
5. Bật `@EnableJpaAuditing` trong cấu hình Spring.
6. Cung cấp `AuditorAware<T>` nếu dùng CreatedBy/LastModifiedBy.
7. Cung cấp `DateTimeProvider` nếu cần nguồn thời gian có thể kiểm soát.
8. Cho các Entity nghiệp vụ kế thừa lớp audit.
9. Tạo migration cho các cột audit trên từng bảng Entity.
10. Kiểm tra access type và tránh trùng mapping.
11. Kiểm thử create, update, auditor rỗng, tác vụ nền và nhiều Entity con.
12. Kiểm tra bulk JPQL/native SQL vì các thao tác đó không gọi listener.
13. Xác nhận dữ liệu audit thực tế trên database mục tiêu.

## 21. Kết luận

Spring Data JPA Auditing dùng `AuditingEntityListener` để kết nối lifecycle callback của JPA với các annotation `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy` và `@LastModifiedBy`. Ứng dụng cần bật `@EnableJpaAuditing`; nếu lưu người thực hiện, cung cấp `AuditorAware<T>`, và nếu cần kiểm soát thời gian, cung cấp `DateTimeProvider`. Đặt các trường cùng listener trong một `@MappedSuperclass` giúp nhiều Entity kế thừa cùng mapping mà không tạo bảng cơ sở riêng. Hãy thống nhất kiểu dữ liệu, access strategy, schema migration và chính sách auditor cho tác vụ nền. Bulk JPQL/native SQL không kích hoạt entity listener, nên cần cập nhật audit field tường minh. Kiểm thử cả tạo, sửa và các đường ghi đặc biệt để bảo đảm metadata phản ánh đúng vòng đời dữ liệu.
