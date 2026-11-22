# @CreatedDate, @LastModifiedDate, @CreatedBy và @LastModifiedBy trong Spring Data JDBC

## 1. Auditing ghi nhận điều gì?

Auditing trong Spring Data JDBC giúp lưu metadata về thời điểm một aggregate được tạo/cập nhật và actor thực hiện thao tác. Bốn annotation thường dùng là:

| Annotation | Thông tin | Thời điểm điển hình |
|---|---|---|
| `@CreatedDate` | Thời điểm tạo | Khi aggregate được insert lần đầu |
| `@LastModifiedDate` | Thời điểm sửa gần nhất | Khi tạo và mỗi lần cập nhật |
| `@CreatedBy` | Actor tạo dữ liệu | Khi aggregate được tạo |
| `@LastModifiedBy` | Actor sửa gần nhất | Khi tạo và mỗi lần cập nhật |

Ví dụ, một đơn hàng có thể lưu `createdAt`, `createdBy`, `lastModifiedAt` và `lastModifiedBy`. Khi người dùng cập nhật trạng thái đơn, thông tin tạo ban đầu vẫn được giữ, còn metadata sửa đổi được cập nhật.

Auditing hữu ích cho truy vết vận hành, hỗ trợ điều tra lỗi, hiển thị “ai đã cập nhật” và kiểm tra thời điểm thay đổi gần nhất. Nó không tự tạo lịch sử đầy đủ của mọi phiên bản dữ liệu. `@LastModifiedDate` và `@LastModifiedBy` chỉ giữ thông tin sửa đổi gần nhất trên hàng hiện tại.

## 2. Bật auditing cho Spring Data JDBC

Khai báo auditing bằng `@EnableJdbcAuditing` trong cấu hình Spring:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing
public class JdbcAuditingConfiguration {
}
~~~

Khi được kích hoạt, Spring Data JDBC đăng ký cơ chế auditing callback. Callback này bổ sung các giá trị auditing vào entity trong quá trình persistence của Spring Data JDBC.

Các annotation `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy` và `@LastModifiedBy` thuộc Spring Data Commons, nằm trong package `org.springframework.data.annotation`. Chúng không phải annotation JPA. Với Spring Data JDBC, dùng `@EnableJdbcAuditing` thay vì bật auditing JPA bằng `@EnableJpaAuditing`.

Nếu ứng dụng dùng Spring Boot, hãy đặt cấu hình auditing trong package được component/configuration scan. Tránh khai báo nhiều cấu hình repository/auditing trùng lặp mà không kiểm tra phạm vi scan.

## 3. Khai báo audit metadata trên entity

Ví dụ aggregate root `PurchaseOrder`:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String status;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @LastModifiedDate
    @Column("last_modified_at")
    private Instant lastModifiedAt;

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @LastModifiedBy
    @Column("last_modified_by")
    private String lastModifiedBy;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String status) {
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public String getLastModifiedBy() {
        return lastModifiedBy;
    }
}
~~~

Các điểm cần chú ý:

- `@Id` đánh dấu identifier của aggregate root.
- `@CreatedDate` và `@LastModifiedDate` đặt trên property thời gian.
- `@CreatedBy` và `@LastModifiedBy` đặt trên property actor.
- `@Column` ánh xạ property Java sang tên cột trong schema.
- Kiểu của property actor phải tương thích với kiểu generic do `AuditorAware<T>` cung cấp.

`Instant` là lựa chọn phù hợp cho timestamp biểu diễn một thời điểm tuyệt đối. Nếu dùng `LocalDateTime` hoặc kiểu khác, hãy thống nhất timezone và cách chuyển đổi giữa ứng dụng, JDBC driver và database.

Ví dụ dùng mutable entity để minh họa. Spring Data JDBC cũng hỗ trợ entity bất biến, nhưng các giá trị auditing phải có thể được áp dụng thông qua constructor, property accessor hoặc wither phù hợp với mapping. Nếu entity dùng record hoặc immutable class, hãy kiểm tra constructor/property mapping của phiên bản Spring Data JDBC đang sử dụng.

## 4. Cung cấp actor hiện tại bằng AuditorAware

Hai annotation `@CreatedBy` và `@LastModifiedBy` cần biết actor hiện tại. Spring Data lấy actor thông qua bean `AuditorAware<T>`.

Ví dụ đơn giản, ứng dụng có một abstraction cung cấp người dùng hiện tại:

~~~java
public interface CurrentActor {
    String username();
}
~~~

Cấu hình provider:

~~~java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;

@Configuration
public class AuditorConfiguration {

    @Bean
    AuditorAware<String> auditorAware(CurrentActor currentActor) {
        return () -> Optional.ofNullable(currentActor.username());
    }
}
~~~

Generic type `String` phải tương thích với kiểu của `createdBy` và `lastModifiedBy` trong entity. Nếu ứng dụng lưu ID người dùng dạng UUID, có thể dùng `AuditorAware<UUID>` và khai báo hai property actor bằng UUID.

### 4.1. Kết nối với Spring Security

Nếu ứng dụng dùng Spring Security, provider có thể lấy username từ security context:

~~~java
import java.util.Optional;

import org.springframework.data.domain.AuditorAware;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public class SecurityAuditorAware implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || "anonymousUser".equals(authentication.getPrincipal())) {
            return Optional.empty();
        }

        return Optional.of(authentication.getName());
    }
}
~~~

Đăng ký bean và tham chiếu từ cấu hình auditing:

~~~java
@Configuration
@EnableJdbcAuditing(auditorAwareRef = "auditorAware")
public class JdbcAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return new SecurityAuditorAware();
    }
}
~~~

Tên bean trong `auditorAwareRef` phải khớp với bean thực tế. Nếu ứng dụng không dùng Spring Security, hãy kết nối `AuditorAware` với cơ chế xác thực hoặc context actor của ứng dụng; không cần thêm Spring Security chỉ để dùng auditing.

### 4.2. Khi không có người dùng hiện tại

`AuditorAware` trả về `Optional.empty()` khi không xác định được actor. Trong tình huống đó, trường actor có thể không được điền bởi auditing handler. Hãy quyết định rõ schema và nghiệp vụ cho trường hợp này:

- Cho phép cột actor là NULL nếu một số thao tác không có người dùng.
- Dùng actor kỹ thuật như `system` cho scheduler, batch job hoặc migration.
- Dùng một định danh service account khi thao tác được thực hiện bởi một service cụ thể.

Không nên tự gán tên người dùng giả chỉ để tránh NULL. Giá trị actor phải phản ánh đúng nguồn thực hiện thao tác.

Với tác vụ chạy nền, security context của request thường không có mặt trên thread worker. Hãy cung cấp actor hệ thống rõ ràng trong context xử lý job, hoặc thiết kế provider có thể phân biệt user request với system task.

## 5. Thời gian auditing và DateTimeProvider

Nếu chỉ cần timestamp hiện tại, Spring Data auditing có thể dùng time provider mặc định. Khi cần kiểm soát clock, timezone hoặc kiểm thử thời gian, cấu hình bean `DateTimeProvider`.

Ví dụ dùng `Clock`:

~~~java
import java.time.Clock;
import java.time.temporal.TemporalAccessor;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;

@Configuration
public class AuditTimeConfiguration {

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider dateTimeProvider(Clock auditClock) {
        return () -> Optional.<TemporalAccessor>of(auditClock.instant());
    }
}
~~~

Tham chiếu provider trong cấu hình:

~~~java
@Configuration
@EnableJdbcAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "dateTimeProvider"
)
public class JdbcAuditingConfiguration {
    // Khai báo các bean auditor/time provider ở cấu hình phù hợp.
}
~~~

Dùng một `Clock` được inject giúp ứng dụng có một nguồn thời gian rõ ràng và dễ thay thế trong test. `Clock.systemUTC()` tránh phụ thuộc timezone mặc định của máy chạy ứng dụng.

Nếu hệ thống yêu cầu thời gian do database quyết định, có thể cân nhắc timestamp/default/trigger ở database. Tuy nhiên, đó là một nguồn thời gian khác với auditing callback của ứng dụng. Hãy thống nhất nguồn thời gian để tránh so sánh timestamp không đồng nhất giữa các đường ghi.

## 6. Giá trị được gán vào lúc nào?

Auditing trong Spring Data JDBC được thực hiện qua entity callback của Spring Data. Khi aggregate được lưu bằng repository hoặc aggregate operations, auditing callback cập nhật metadata trước khi entity được chuyển đổi và ghi xuống database.

| Thao tác | Created fields | Last-modified fields |
|---|---|---|
| Insert aggregate mới | Được điền | Thông thường cũng được điền khi tạo |
| Update aggregate hiện có | Giữ giá trị tạo ban đầu | Cập nhật theo lần sửa |
| Đọc aggregate | Không thay đổi | Không thay đổi |
| SQL UPDATE tự viết | Không tự động chạy callback | Không tự động chạy callback |

Trong cấu hình auditing thông thường, modified metadata được thiết lập ngay cả lúc tạo mới; thuộc tính `modifyOnCreate` của cấu hình auditing có thể điều chỉnh hành vi này ở phiên bản hỗ trợ thuộc tính đó.

Created metadata biểu thị lần tạo đầu tiên. Không ghi đè `createdAt` hoặc `createdBy` trong các thao tác cập nhật thông thường. Modified metadata phản ánh lần sửa gần nhất mà đường persistence có chạy auditing callback.

### 6.1. Ví dụ sử dụng repository

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Tạo mới:

~~~java
PurchaseOrder order = new PurchaseOrder("PENDING");
PurchaseOrder saved = orders.save(order);

System.out.println(saved.getCreatedAt());
System.out.println(saved.getCreatedBy());
System.out.println(saved.getLastModifiedAt());
System.out.println(saved.getLastModifiedBy());
~~~

Sau đó cập nhật trạng thái:

~~~java
PurchaseOrder loaded = orders.findById(saved.getId())
        .orElseThrow();

loaded.setStatus("CONFIRMED");

PurchaseOrder updated = orders.save(loaded);
~~~

Khi auditing được bật và thao tác đi qua Spring Data JDBC persistence callback:

- `createdAt` vẫn biểu thị thời điểm tạo.
- `createdBy` vẫn biểu thị actor tạo.
- `lastModifiedAt` được cập nhật.
- `lastModifiedBy` phản ánh actor thực hiện lần sửa.

Không nên tự đặt các field auditing trong service trước khi gọi `save` nếu auditing handler là nguồn dữ liệu chuẩn. Việc gán thủ công có thể khiến metadata không nhất quán hoặc che khuất actor/time provider.

## 7. Cấu trúc bảng và kiểu dữ liệu

Schema cần có cột tương ứng với metadata entity:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_modified_at TIMESTAMP WITH TIME ZONE,
    created_by VARCHAR(120),
    last_modified_by VARCHAR(120)
);
~~~

Đây là ví dụ PostgreSQL. Kiểu timestamp và cú pháp identity thay đổi theo hệ quản trị. Với database hỗ trợ kiểu tương đương timestamp có timezone, kiểu đó thường phù hợp khi ứng dụng lưu `Instant`.

Một số quyết định schema cần thống nhất:

- Có bắt buộc actor hay không? Nếu batch/system task có thể không có actor, cột actor có thể cần nullable hoặc provider phải trả actor hệ thống.
- Có bắt buộc modified timestamp hay không? Nếu auditing cấu hình ghi modified time khi tạo, có thể đặt NOT NULL; nếu tắt hành vi đó, cần điều chỉnh schema.
- Precision timestamp có đủ cho workload không? Database có thể làm tròn hoặc cắt phần fractional seconds.
- Tên cột có khớp mapping không? Dùng `@Column` khi cần chỉ rõ.
- Các đường ghi ngoài Spring Data JDBC có điền đủ cột không? Nếu không, cần default hoặc cơ chế DB có chủ đích.

Đừng đặt NOT NULL cho actor trước khi bảo đảm mọi đường ghi đều có actor hợp lệ. Một tác vụ migration hoặc SQL thủ công có thể không có security context như request thông thường.

## 8. SQL tùy chỉnh không tự chạy auditing callback

Một điểm quan trọng là auditing callback được gắn với đường persistence của Spring Data JDBC. Câu UPDATE viết tay bằng `@Modifying @Query` hoặc `JdbcTemplate` không tự tạo entity rồi chạy callback auditing.

Ví dụ query:

~~~java
@Modifying
@Query("""
    UPDATE purchase_orders
    SET status = :status
    WHERE id = :id
    """)
int updateStatus(
        @Param("id") Long id,
        @Param("status") String status
);
~~~

Query này không tự động cập nhật `last_modified_at` hoặc `last_modified_by`. Nếu cần auditing cho direct SQL, hãy cập nhật metadata ngay trong câu SQL:

~~~java
@Modifying
@Query("""
    UPDATE purchase_orders
    SET status = :status,
        last_modified_at = :modifiedAt,
        last_modified_by = :actor
    WHERE id = :id
    """)
int updateStatusWithAudit(
        @Param("id") Long id,
        @Param("status") String status,
        @Param("modifiedAt") Instant modifiedAt,
        @Param("actor") String actor
);
~~~

Service có thể lấy actor và thời gian từ các abstraction tương ứng rồi truyền thành parameter. Với SQL trực tiếp, ứng dụng chịu trách nhiệm giữ quy tắc:

- Không thay đổi `created_at` và `created_by` trong UPDATE thông thường.
- Cập nhật cả modified timestamp và actor theo chính sách.
- Bind mọi giá trị bằng parameter.
- Nếu entity có `@Version`, cân nhắc thêm version predicate và tăng version trong cùng statement.
- Xử lý update count để biết predicate có khớp hay không.

Một phương án khác là dùng trigger hoặc default ở database. Nếu chọn cách này, hãy xác định nguồn actor/time của database và tránh để callback ứng dụng cùng trigger ghi đè lẫn nhau.

## 9. Auditing metadata không phải audit trail

Bốn annotation chỉ giữ một bộ metadata hiện tại trên entity. Ví dụ sau ba lần cập nhật, hàng vẫn chỉ có:

~~~text
created_by       = alice
created_at       = thời điểm tạo
last_modified_by = bob
last_modified_at = thời điểm sửa gần nhất
~~~

Thông tin ai đã sửa ở lần thứ nhất và lần thứ hai không còn được biểu diễn trong các field này.

Nếu yêu cầu cần lưu toàn bộ lịch sử:

- Tạo bảng history/audit riêng với một hàng cho mỗi thay đổi.
- Lưu actor, thời điểm, entity ID, loại hành động và dữ liệu trước/sau phù hợp chính sách.
- Ghi audit trong cùng transaction với thay đổi nghiệp vụ nếu hai thao tác phải atomic.
- Cân nhắc transactional outbox nếu cần phát sự kiện tới hệ thống khác sau commit.
- Với yêu cầu pháp lý hoặc bảo mật cao, xác định quyền sửa/xóa log và thời gian lưu trữ.

Auditing metadata hữu ích cho trạng thái hiện tại; audit trail là một mô hình dữ liệu khác.

## 10. Clock, timezone và actor trong môi trường nhiều instance

Khi ứng dụng chạy trên nhiều máy hoặc container, đồng hồ hệ thống có thể lệch nhau. Nếu mỗi instance tự lấy thời gian, hai thao tác gần nhau có thể ghi timestamp không hoàn toàn theo thứ tự thực tế.

Một số thực hành:

- Dùng UTC và lưu thời điểm dưới dạng instant.
- Đồng bộ clock của các node bằng hạ tầng thời gian đáng tin cậy.
- Dùng một DateTimeProvider chung để dễ kiểm soát và test.
- Không dùng timestamp làm thứ tự tuyệt đối duy nhất nếu hai sự kiện có thể cùng thời điểm; thêm ID hoặc sequence khi cần thứ tự.
- Nếu cần thời gian chuẩn do database cấp, dùng database expression/default/trigger nhất quán trên mọi đường ghi.

Actor cũng cần quy ước thống nhất. Một user có thể có username thay đổi; trong hệ thống dài hạn, lưu ID ổn định (UUID/long) thường tốt hơn lưu display name. Có thể lưu thêm tên hiển thị ở bảng identity nếu cần.

## 11. Auditing và aggregate

Spring Data JDBC quản lý aggregate root cùng các thành phần thuộc aggregate. Audit metadata thường đặt trên aggregate root để thể hiện thời điểm và actor của thao tác lưu aggregate.

Nếu một child object thay đổi và ứng dụng lưu aggregate root, auditing callback có thể cập nhật metadata của root theo lần persistence đó. Điều này không tự tạo một bộ metadata độc lập cho từng hàng con. Nếu mỗi child cần actor/time riêng, hãy thiết kế entity/mapping và lifecycle phù hợp, hoặc lưu sự kiện lịch sử riêng.

Không nên biến auditing thành một lý do để phá vỡ aggregate boundary. Hãy xác định metadata cần phản ánh thay đổi của root, của child hay của từng record độc lập.

## 12. Kiểm thử auditing

Nên kiểm thử qua repository thật trong Spring context để xác nhận auditing được kích hoạt và callback thực sự chạy.

Ví dụ cấu hình test:

~~~java
@DataJdbcTest
@Import(JdbcAuditingConfiguration.class)
class PurchaseOrderAuditingTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Test
    void populatesAuditFieldsOnInsert() {
        PurchaseOrder saved = orders.save(
                new PurchaseOrder("PENDING")
        );

        assertThat(saved.getCreatedAt()).isNotNull();
        assertThat(saved.getLastModifiedAt()).isNotNull();
        assertThat(saved.getCreatedBy()).isEqualTo("test-user");
        assertThat(saved.getLastModifiedBy()).isEqualTo("test-user");
    }
}
~~~

Đây là ví dụ minh họa; test cần cung cấp bean `AuditorAware` trả về `test-user` và import cấu hình auditing. Nếu dùng custom DateTimeProvider, test có thể điều khiển clock để kiểm tra timestamp chính xác mà không phụ thuộc thời gian thực.

Các tình huống nên kiểm tra:

| Tình huống | Điều cần xác nhận |
|---|---|
| Insert mới | Created và modified metadata được điền theo cấu hình |
| Update entity | Created fields không đổi |
| Update entity | Last-modified fields phản ánh actor/time mới |
| Không có actor | Hành vi Optional.empty và nullable constraint đúng chính sách |
| System job | Actor kỹ thuật được ghi theo quy ước |
| Direct UPDATE | Modified metadata chỉ đổi nếu SQL/trigger chủ động cập nhật |
| Immutable entity | Mapping trả entity với metadata được áp dụng |
| Nhiều repository | Các aggregate dùng chung provider như mong đợi |
| Test với clock cố định | Timestamp có giá trị xác định, dễ assert |

Một test có transaction rollback tự động vẫn có thể kiểm tra entity trả về từ `save` trong cùng test. Nếu cần xác minh dữ liệu sau commit hoặc trigger/database behavior, hãy tạo integration test với transaction boundary phù hợp.

## 13. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Field auditing luôn NULL | Chưa bật `@EnableJdbcAuditing` hoặc entity chưa được callback xử lý | Bật auditing trong Spring context |
| Created/modified date có giá trị nhưng actor NULL | Chưa đăng ký `AuditorAware` hoặc provider trả Optional.empty | Cấu hình provider và kiểm tra actor context |
| Không nhận đúng user hiện tại | Security context không có trên thread hoặc provider đọc sai principal | Kiểm tra authentication và tác vụ async |
| Không cập nhật last-modified khi dùng custom SQL | Direct SQL không chạy entity callback | Cập nhật cột trong SQL hoặc dùng cơ chế DB |
| Created fields bị ghi đè khi update | Service tự gán metadata hoặc mapping không giữ giá trị cũ | Để auditing quản lý created fields |
| Insert thất bại vì NOT NULL actor | Job/migration không có actor | Dùng system actor hoặc schema nullable theo chính sách |
| Timestamp lệch giữa instance | Clock/timezone không thống nhất | Dùng UTC, đồng bộ clock hoặc database time |
| Entity immutable không nhận audit fields | Constructor/wither/property mapping chưa phù hợp | Khai báo property/constructor tương thích |
| Modified timestamp không đổi trong test | Clock cố định hoặc độ chính xác timestamp thấp | Điều khiển clock và kiểm tra precision |
| Nghĩ bốn annotation lưu mọi lịch sử | Nhầm metadata hiện tại với audit trail | Tạo history table hoặc event log |
| Trigger và callback ghi đè nhau | Có hai nguồn auditing độc lập | Chọn nguồn chuẩn hoặc phân chia trách nhiệm rõ |
| Tên cột không khớp | Thiếu mapping hoặc schema khác tên property | Dùng `@Column` và kiểm tra DDL |

## 14. Quy trình triển khai

1. Xác định metadata cần lưu và kiểu actor ổn định.
2. Thêm bốn field auditing vào aggregate root và ánh xạ cột.
3. Bật `@EnableJdbcAuditing` trong cấu hình Spring Data JDBC.
4. Đăng ký `AuditorAware<T>` để cung cấp actor hiện tại.
5. Nếu cần kiểm soát thời gian, đăng ký `DateTimeProvider` dựa trên `Clock`.
6. Tạo hoặc migration các cột audit với kiểu dữ liệu/nullability phù hợp.
7. Dùng repository/aggregate operations để auditing callback được thực thi.
8. Với direct SQL, cập nhật modified metadata một cách tường minh hoặc dùng database trigger có chủ đích.
9. Kiểm thử insert, update, actor vắng mặt, job nền và các đường ghi khác.
10. Nếu cần lịch sử đầy đủ, thiết kế audit trail riêng thay vì chỉ dựa vào last-modified fields.

## 15. Bài tập thực hành

### Bài 1 — Bật auditing

Tạo cấu hình `@EnableJdbcAuditing` và thêm `@CreatedDate`, `@LastModifiedDate` vào một aggregate. Lưu entity mới và xác nhận hai timestamp có giá trị.

### Bài 2 — Actor provider

Tạo `AuditorAware<String>` đọc actor từ một abstraction hiện tại. Thử user request, anonymous request và system job. Xác nhận quy tắc cho `Optional.empty`.

### Bài 3 — Created và modified

Insert một đơn hàng dưới actor A, sau đó update dưới actor B. Xác nhận created metadata vẫn là A và modified metadata chuyển sang B.

### Bài 4 — Custom DateTimeProvider

Inject `Clock` vào `DateTimeProvider`. Trong test, dùng clock có thể điều khiển để kiểm tra timestamp insert và update.

### Bài 5 — Direct SQL

Tạo một method `@Modifying @Query` cập nhật trạng thái. Quan sát last-modified fields khi chưa đưa chúng vào SQL, sau đó cập nhật timestamp/actor rõ ràng và so sánh.

### Bài 6 — Immutable aggregate

Chuyển entity sang record hoặc immutable class. Cấu hình constructor/property mapping để auditing fields được áp dụng và kiểm tra entity trả về từ save.

### Bài 7 — Audit trail

Tạo bảng history lưu mỗi lần đổi trạng thái đơn hàng. Ghi history trong cùng transaction với cập nhật aggregate và so sánh thông tin đó với last-modified metadata.

### Bài 8 — Nhiều nguồn ghi

Thực hiện một lần insert bằng repository, một lần bằng SQL trực tiếp và một lần từ batch job. Xác định nguồn actor/time cho từng đường ghi và bảo đảm dữ liệu auditing không bị bỏ trống ngoài ý muốn.

## 16. Ghi nhớ

- `@CreatedDate` và `@CreatedBy` ghi nhận thời điểm và actor tạo aggregate.
- `@LastModifiedDate` và `@LastModifiedBy` ghi nhận lần sửa gần nhất; modified metadata thường cũng được điền lúc tạo theo cấu hình mặc định.
- Bật auditing cho Spring Data JDBC bằng `@EnableJdbcAuditing`.
- `AuditorAware<T>` cung cấp actor; kiểu generic phải tương thích với property `@CreatedBy` và `@LastModifiedBy`.
- `DateTimeProvider` cung cấp thời gian; inject `Clock` giúp thống nhất UTC và kiểm thử dễ hơn.
- Auditing callback chạy trên đường persistence của Spring Data JDBC; custom SQL/`JdbcTemplate` không tự chạy callback.
- Created fields giữ giá trị ban đầu; modified fields được cập nhật theo lần persistence tiếp theo.
- Actor vắng mặt cần một chính sách rõ ràng: nullable, system actor hoặc service account.
- Các field last-modified chỉ lưu trạng thái hiện tại, không thay thế audit trail lưu mọi thay đổi.
- Kiểm thử trên repository trong Spring context và xác nhận schema, actor provider, clock, immutable mapping cùng các đường ghi trực tiếp.
