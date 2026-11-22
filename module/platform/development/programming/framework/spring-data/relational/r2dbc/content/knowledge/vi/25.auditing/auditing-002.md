# Ánh xạ thời điểm tạo và cập nhật dữ liệu

Trong Spring Data Relational R2DBC, auditing giúp tự động ghi nhận ai tạo bản ghi, ai sửa bản ghi và thời điểm các thao tác đó diễn ra. Thay vì gán createdAt, updatedAt, createdBy hoặc updatedBy ở mọi service, ứng dụng có thể khai báo metadata trên entity và bật auditing của Spring Data.

Các annotation thường dùng:

- @CreatedDate: thời điểm tạo bản ghi.
- @LastModifiedDate: thời điểm sửa gần nhất.
- @CreatedBy: người hoặc tác nhân tạo bản ghi.
- @LastModifiedBy: người hoặc tác nhân sửa gần nhất.

Auditing cần được kích hoạt bằng @EnableR2dbcAuditing. Nếu muốn ghi nhận người thực hiện, cần cung cấp ReactiveAuditorAware để lấy actor hiện tại trong reactive context. Nếu muốn kiểm soát nguồn thời gian, có thể cấu hình DateTimeProvider và Clock.

Auditing của Spring Data được thực hiện trong luồng persistence của entity. Một câu SQL viết trực tiếp bằng DatabaseClient không tự động chạy entity auditing callback. Nếu có nhiều đường ghi, cần thống nhất nơi quản lý timestamp và actor để dữ liệu audit không bị thiếu hoặc mâu thuẫn.

## 1. Auditing giải quyết vấn đề gì?

Một bảng customer thường cần lưu dấu vết tạo và cập nhật:

| Cột | Ý nghĩa |
|---|---|
| created_at | Thời điểm bản ghi được tạo |
| updated_at | Thời điểm sửa gần nhất |
| created_by | Người hoặc tác nhân tạo |
| updated_by | Người hoặc tác nhân sửa |

Nếu mỗi service tự gán các trường này, ứng dụng dễ gặp những vấn đề:

- Một luồng ghi quên cập nhật updated_at.
- Một service dùng giờ local, service khác dùng UTC.
- Một tác vụ nền không có người dùng đăng nhập nên bỏ trống actor.
- Một lần cập nhật ghi đè nhầm created_at.
- Các test phụ thuộc thời gian thực và trở nên khó ổn định.

Auditing tập trung quy tắc này tại persistence infrastructure. Khi entity được lưu qua cơ chế Spring Data có hỗ trợ auditing, các trường được đánh dấu sẽ được thiết lập theo lifecycle của entity.

Auditing không thay thế lịch sử thay đổi đầy đủ. Bốn trường trên chỉ cho biết người tạo, người sửa cuối và thời điểm tương ứng. Nếu cần biết mọi lần thay đổi, giá trị cũ/mới hoặc lý do thay đổi, cần thiết kế audit log, event log hoặc lịch sử phiên bản riêng.

## 2. Khai báo các trường auditing trên entity

Ví dụ entity Customer:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @LastModifiedDate
    @Column("updated_at")
    private Instant updatedAt;

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @LastModifiedBy
    @Column("updated_by")
    private String updatedBy;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public String getUpdatedBy() {
        return updatedBy;
    }
}
~~~

Các annotation auditing thuộc Spring Data, không phải annotation của JPA:

- @CreatedDate đánh dấu thuộc tính chứa thời điểm tạo.
- @LastModifiedDate đánh dấu thuộc tính chứa thời điểm sửa gần nhất.
- @CreatedBy đánh dấu thuộc tính chứa auditor lúc tạo.
- @LastModifiedBy đánh dấu thuộc tính chứa auditor lúc sửa gần nhất.

@Column ánh xạ tên thuộc tính Java sang tên cột database. Có thể dùng naming strategy thay cho khai báo tường minh, nhưng tên cột thực tế phải khớp schema.

Các trường audit thường không nên được nhận trực tiếp từ request của client. Service nên để auditing infrastructure quản lý chúng, tránh việc client tự gửi createdBy hoặc sửa createdAt.

## 3. Bật auditing cho Spring Data R2DBC

Chỉ thêm annotation trên entity chưa đủ. Ứng dụng phải bật R2DBC auditing:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;

@Configuration
@EnableR2dbcAuditing
public class R2dbcAuditingConfiguration {
}
~~~

Khi được bật, Spring Data đăng ký hạ tầng auditing reactive để thiết lập các trường được đánh dấu trong lifecycle persistence của entity.

Nếu chỉ cần timestamp, cấu hình tối thiểu này thường đủ. Nếu cần @CreatedBy hoặc @LastModifiedBy, hãy cung cấp auditor provider. Nếu không có auditor provider hoặc không tìm được actor, các trường actor có thể không được thiết lập; timestamp vẫn có thể hoạt động độc lập.

### Cấu hình modifyOnCreate

@EnableR2dbcAuditing có thuộc tính modifyOnCreate. Theo cấu hình mặc định, các trường last-modified cũng được thiết lập khi entity được tạo. Điều đó có nghĩa updatedAt có thể bằng hoặc gần bằng createdAt sau lần INSERT đầu tiên.

Nếu nghiệp vụ muốn chỉ có created fields ở lần tạo đầu, có thể cấu hình:

~~~java
@Configuration
@EnableR2dbcAuditing(modifyOnCreate = false)
public class R2dbcAuditingConfiguration {
}
~~~

Khi đó, các trường @LastModifiedDate và @LastModifiedBy không được thiết lập chỉ vì entity được tạo mới. Khi entity được sửa về sau, các trường này mới phản ánh lần sửa.

Thuộc tính setDates cũng có thể được dùng để bật hoặc tắt việc thiết lập các trường ngày giờ. Chỉ tắt khi ứng dụng có một nguồn timestamp khác được quản lý rõ ràng.

## 4. Ánh xạ timestamp và actor theo từng thao tác

Với cấu hình mặc định modifyOnCreate = true, hành vi khái quát như sau:

| Trường | Khi INSERT | Khi UPDATE |
|---|---|---|
| @CreatedDate | Được thiết lập | Giữ thời điểm tạo ban đầu |
| @LastModifiedDate | Được thiết lập | Được cập nhật |
| @CreatedBy | Được thiết lập nếu có auditor | Giữ actor tạo ban đầu |
| @LastModifiedBy | Được thiết lập nếu có auditor | Được cập nhật nếu có auditor |

Nếu cấu hình modifyOnCreate = false, các trường last-modified không được thiết lập trong lần tạo đầu chỉ bởi auditing.

Ví dụ:

~~~text
INSERT customer
  created_at = 2026-01-10T09:00:00Z
  updated_at = 2026-01-10T09:00:00Z
  created_by = "alice"
  updated_by = "alice"

UPDATE customer
  created_at = 2026-01-10T09:00:00Z   (giữ nguyên)
  updated_at = 2026-01-12T14:30:00Z   (thay đổi)
  created_by = "alice"                 (giữ nguyên)
  updated_by = "bob"                   (thay đổi)
~~~

Các thời điểm trong ví dụ chỉ minh họa. Giá trị thực tế phụ thuộc DateTimeProvider, độ chính xác cột timestamp và thời điểm callback được thực thi.

@CreatedDate không có nghĩa là ngày giờ được database tự sinh. Với auditing phía ứng dụng, Spring Data thiết lập giá trị trước khi ghi entity. Nếu muốn database là nguồn tạo timestamp, cần thiết kế default hoặc trigger ở database và bảo đảm câu lệnh INSERT không ghi đè giá trị đó.

## 5. Cấu hình ReactiveAuditorAware

@CreatedBy và @LastModifiedBy cần biết actor hiện tại. Trong ứng dụng reactive, dùng ReactiveAuditorAware<T> thay vì đọc thông tin từ ThreadLocal theo cách imperative.

Ví dụ lấy username từ Spring Security Reactor Context:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;

@Configuration
@EnableR2dbcAuditing(auditorAwareRef = "auditorAware")
public class R2dbcAuditingConfiguration {

    @Bean
    public ReactiveAuditorAware<String> auditorAware() {
        return () -> ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName)
            .filter(name -> !"anonymousUser".equals(name));
    }
}
~~~

Auditor provider trả về Mono<String>:

1. ReactiveSecurityContextHolder đọc security context từ Reactor Context.
2. Lấy Authentication hiện tại.
3. Chỉ giữ authentication hợp lệ.
4. Chuyển thành tên actor.
5. Trả Mono rỗng nếu không có actor phù hợp.

Tên bean trong auditorAwareRef phải khớp tên bean auditorAware. Kiểu generic String phải tương thích với kiểu thuộc tính createdBy và updatedBy.

### Không dùng SecurityContextHolder theo kiểu imperative trong reactive flow

Trong ứng dụng reactive, không nên dựa vào SecurityContextHolder.getContext() như thể mọi thao tác luôn chạy trên cùng thread. Reactor có thể chuyển thread trong quá trình xử lý. ReactiveSecurityContextHolder lấy context theo reactive context, phù hợp với reactive security.

Nếu ứng dụng không dùng Spring Security, ReactiveAuditorAware có thể lấy actor từ một reactive context provider, message metadata hoặc application service thích hợp. Điều quan trọng là nguồn actor phải theo subscription/context của request hiện tại.

## 6. Xử lý tác vụ nền không có người dùng đăng nhập

Không phải mọi thao tác ghi đều bắt đầu từ HTTP request. Các ví dụ:

- Scheduled job đồng bộ dữ liệu.
- Consumer xử lý message.
- Batch import.
- Tác vụ quản trị.
- Migration hoặc tiến trình hệ thống.

Trong các trường hợp này, ReactiveAuditorAware có thể trả Mono.empty(). Khi cần mọi bản ghi đều có actor, nên xác định một danh tính hệ thống rõ ràng:

~~~java
@Bean
public ReactiveAuditorAware<String> auditorAware() {
    return () -> ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getName)
        .filter(name -> !"anonymousUser".equals(name))
        .switchIfEmpty(Mono.just("system"));
}
~~~

Ở đây, actor "system" là quy ước của ứng dụng. Có thể dùng các giá trị cụ thể hơn như batch-import, scheduler hoặc tên service để truy vết nguồn thay đổi.

Không nên dùng một actor mặc định nếu điều đó làm mất thông tin quan trọng về người thực hiện. Nếu nghiệp vụ cần phân biệt người dùng thật, service account và job, hãy thiết kế miền giá trị actor rõ ràng.

Với message consumer, có thể lấy actor từ metadata của message nếu nguồn phát được xác thực. Không tin một chuỗi username tùy ý từ payload chưa được xác thực.

## 7. Cấu hình DateTimeProvider và Clock

Mặc định, auditing sử dụng nguồn thời gian của Spring Data. Có thể cung cấp DateTimeProvider riêng để kiểm soát nguồn timestamp, đặc biệt hữu ích khi:

- Muốn thống nhất UTC.
- Muốn dùng một Clock có thể thay thế trong test.
- Muốn kiểm soát thời gian trong ứng dụng nhiều service.
- Muốn tạo timestamp theo một chính sách chung.

Ví dụ cấu hình:

~~~java
import java.time.Clock;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;

@Configuration
@EnableR2dbcAuditing(dateTimeProviderRef = "dateTimeProvider")
public class R2dbcAuditingConfiguration {

    @Bean
    public Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean
    public DateTimeProvider dateTimeProvider(Clock auditClock) {
        return () -> Optional.of(auditClock.instant());
    }
}
~~~

DateTimeProvider trả về Optional<TemporalAccessor>. Instant là một TemporalAccessor, nên có thể dùng làm giá trị thời gian cho entity có kiểu tương thích.

Nếu cấu hình đồng thời auditor và date provider, khai báo cả hai reference:

~~~java
@EnableR2dbcAuditing(
    auditorAwareRef = "auditorAware",
    dateTimeProviderRef = "dateTimeProvider",
    modifyOnCreate = true
)
~~~

Chỉ tạo một bean có tên khớp từng reference. Nếu tên bean không khớp hoặc có nhiều provider cùng loại không rõ ràng, cấu hình auditing có thể không khởi động như mong đợi.

### Clock có thể thay thế trong kiểm thử

Trong test, dùng Clock cố định:

~~~java
@Bean
public Clock auditClock() {
    return Clock.fixed(
        Instant.parse("2026-01-10T09:00:00Z"),
        ZoneOffset.UTC
    );
}
~~~

Khi đó, các trường ngày giờ được auditing thiết lập theo một thời điểm xác định. Test không cần chờ đồng hồ thực hoặc so sánh timestamp với sai số không cần thiết.

## 8. Chọn kiểu Java cho thời điểm audit

Kiểu Java cần phù hợp ý nghĩa thời gian và kiểu cột database.

| Kiểu Java | Ý nghĩa | Khi phù hợp |
|---|---|---|
| Instant | Một thời điểm tuyệt đối trên timeline UTC | Thời điểm tạo/sửa dùng chung giữa các hệ thống |
| OffsetDateTime | Ngày giờ kèm UTC offset | Khi cần giữ offset trong giá trị trao đổi |
| ZonedDateTime | Ngày giờ cùng zone ID | Khi nghiệp vụ cần zone như Europe/Paris |
| LocalDateTime | Ngày giờ địa phương không kèm zone/offset | Lịch hoặc thời gian tường tại một địa điểm đã được xác định |
| LocalDate | Chỉ ngày, không có giờ | Ngày nghiệp vụ, không phải timestamp tạo/sửa |

Với createdAt và updatedAt mang ý nghĩa thời điểm thực tế, Instant thường là lựa chọn dễ trao đổi giữa các service. Khi hiển thị, chuyển Instant sang múi giờ của người dùng ở tầng trình bày.

Không nên lưu thời điểm audit dưới dạng chuỗi tùy ý. Dùng kiểu temporal và mapping được R2DBC driver hỗ trợ để database có thể so sánh, sắp xếp và lập chỉ mục.

## 9. Chọn kiểu cột database và múi giờ

Schema phải tương thích với kiểu Java và R2DBC driver.

Ví dụ một schema có các cột audit:

~~~sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by VARCHAR(150),
    updated_by VARCHAR(150)
);
~~~

Đây là cú pháp minh họa theo PostgreSQL. Kiểu timestamp và cú pháp tạo ID khác nhau giữa database.

Một số lưu ý:

- PostgreSQL TIMESTAMP WITH TIME ZONE (timestamptz) biểu diễn một instant; database không giữ nguyên tên múi giờ ban đầu của người gửi.
- PostgreSQL TIMESTAMP WITHOUT TIME ZONE lưu ngày giờ không kèm múi giờ.
- MySQL TIMESTAMP có quy tắc chuyển đổi theo session time zone; DATETIME không mang cùng semantics chuyển đổi đó.
- Kiểu Java và codec cần phù hợp với cột cụ thể và R2DBC driver.
- Database có thể lưu timestamp với độ chính xác thấp hơn nanosecond; giá trị đọc lại có thể bị làm tròn hoặc cắt bớt phần lẻ.

Không có một kiểu cột SQL duy nhất phù hợp cho mọi database. Hãy chọn semantics trước, sau đó xác nhận mapping với driver thực tế.

### Tránh trộn giờ local và UTC

Nếu một service lưu giờ local, service khác lưu UTC nhưng cả hai ghi vào cùng cột không có timezone, việc so sánh và sắp xếp có thể sai.

Với timestamp audit, một quy ước phổ biến là:

1. Sinh thời điểm dưới dạng Instant/UTC.
2. Lưu bằng kiểu cột có semantics phù hợp.
3. Đọc lại thành kiểu temporal tương ứng.
4. Chuyển sang zone người dùng khi hiển thị.

Nếu nghiệp vụ cần ghi nhận múi giờ nơi sự kiện xảy ra, lưu thêm zone ID hoặc offset riêng; đừng kỳ vọng mọi kiểu timestamp đều giữ thông tin zone gốc.

## 10. Thiết kế schema cho auditing

Ví dụ schema tổng quát:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP,
    created_by VARCHAR(150),
    updated_by VARCHAR(150)
);
~~~

Các quyết định schema cần làm rõ:

- created_at có bắt buộc không?
- updated_at có được NULL cho đến lần cập nhật đầu không?
- created_by và updated_by có thể vắng mặt trong tác vụ hệ thống không?
- Actor là username, user ID, service ID hay một mã định danh khác?
- Có cần index trên created_at hoặc updated_at cho truy vấn quản trị không?
- Có cần lưu timestamp theo độ chính xác mili giây hay micro/nanosecond?

Nếu ứng dụng dùng auditing để luôn gán created_at trước khi INSERT, cột có thể đặt NOT NULL. Nhưng mọi đường ghi phải đi qua auditing hoặc tự cung cấp giá trị hợp lệ.

Nếu có dữ liệu cũ, migration cần backfill các cột mới trước khi đặt NOT NULL. Không nên thêm cột NOT NULL vào bảng đang có dữ liệu mà không có default hoặc bước backfill phù hợp.

### Database default và auditing phía ứng dụng

Một default như:

~~~sql
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
~~~

chỉ được dùng khi câu INSERT để database áp dụng default, ví dụ không đưa cột vào danh sách INSERT hoặc dùng từ khóa DEFAULT. Nếu Spring Data gửi một giá trị NULL tường minh, default thông thường không tự thay NULL bằng thời điểm hiện tại.

Vì vậy, hãy chọn một nguồn sở hữu timestamp:

- Ứng dụng dùng Spring Data auditing và bind giá trị.
- Database dùng default/trigger và câu lệnh ghi để database sinh giá trị.
- Một quy trình thống nhất khác có hợp đồng rõ ràng.

Tránh để ứng dụng và database cùng ghi đè timestamp mà không có quy tắc ưu tiên.

## 11. Auditing khi gọi repository.save()

Khi lưu entity qua Spring Data repository, auditing callback có thể thiết lập các trường trước khi dữ liệu được ghi:

~~~java
public Mono<Customer> createCustomer(String name) {
    Customer customer = new Customer(name);
    return customerRepository.save(customer);
}
~~~

Nếu auditing đã bật:

- createdAt được thiết lập khi tạo.
- updatedAt được thiết lập khi tạo nếu modifyOnCreate bật.
- createdBy được thiết lập nếu auditor provider phát actor.
- updatedBy được thiết lập khi tạo nếu modifyOnCreate bật và có auditor.

Khi cập nhật:

~~~java
public Mono<Customer> rename(Long id, String newName) {
    return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(
            new CustomerNotFoundException(id)
        ))
        .flatMap(customer -> {
            customer.rename(newName);
            return customerRepository.save(customer);
        });
}
~~~

createdAt và createdBy giữ thông tin lần tạo. updatedAt và updatedBy được cập nhật theo auditing.

Hãy tiếp tục pipeline bằng entity trả về từ save(), vì entity kết quả có thể chứa ID, version và các trường auditing mới.

## 12. Auditing khi dùng R2dbcEntityTemplate

R2dbcEntityTemplate dùng mapping infrastructure của Spring Data Relational và tham gia lifecycle entity của framework.

Ví dụ insert:

~~~java
Mono<Customer> saved =
    r2dbcEntityTemplate.insert(Customer.class)
        .using(new Customer("An"));
~~~

Ví dụ update một entity:

~~~java
Mono<Customer> saved =
    r2dbcEntityTemplate.update(customer);
~~~

API cụ thể có thể khác theo phiên bản Spring Data. Khi dùng các thao tác entity của template, auditing được áp dụng theo lifecycle được hỗ trợ bởi Spring Data. Vẫn nên dùng entity được trả về để lấy timestamp và version mới nhất.

Nếu dùng template cho update theo kiểu bulk hoặc câu lệnh không ánh xạ entity, không nên mặc định auditing tự chạy cho từng row. Kiểm tra loại operation cụ thể.

## 13. Auditing khi dùng DatabaseClient hoặc SQL thuần

DatabaseClient cho phép viết SQL tùy chỉnh:

~~~java
return databaseClient.sql(
        "UPDATE customer " +
        "SET name = :name, updated_at = :updatedAt, updated_by = :updatedBy " +
        "WHERE id = :id"
    )
    .bind("name", newName)
    .bind("updatedAt", clock.instant())
    .bind("updatedBy", actor)
    .bind("id", id)
    .fetch()
    .rowsUpdated();
~~~

Ở đây, ứng dụng tự quản lý updated_at và updated_by. Không nên giả định @LastModifiedDate hoặc @LastModifiedBy sẽ tự được áp dụng cho câu SQL DatabaseClient viết thủ công.

Nếu hệ thống có nhiều đường ghi:

- Repository save().
- R2dbcEntityTemplate.
- DatabaseClient.
- Stored procedure hoặc trigger.

hãy xác định một quy ước audit thống nhất. Có thể để database trigger quản lý timestamp, hoặc yêu cầu mọi câu SQL thuần tự cập nhật cột audit. Nếu một đường ghi quên cập nhật, dữ liệu audit sẽ không còn nhất quán.

### Bulk update

Một câu UPDATE ảnh hưởng nhiều row thường không tạo một entity cho mỗi row. Do đó không có callback auditing entity tự động cho từng bản ghi như luồng save entity thông thường.

Ví dụ:

~~~sql
UPDATE customer
SET status = :status
WHERE last_login_at < :cutoff;
~~~

Nếu cần cập nhật updated_at và updated_by cho tất cả dòng, hãy thêm chúng vào câu SQL hoặc dùng trigger:

~~~sql
UPDATE customer
SET status = :status,
    updated_at = :updatedAt,
    updated_by = :updatedBy
WHERE last_login_at < :cutoff;
~~~

## 14. Auditing và @Version là hai trách nhiệm khác nhau

@CreatedDate và @LastModifiedDate ghi nhận thời điểm. @CreatedBy và @LastModifiedBy ghi nhận actor. @Version phục vụ optimistic locking.

| Thuộc tính | Mục đích |
|---|---|
| @CreatedDate | Thời điểm tạo |
| @LastModifiedDate | Thời điểm sửa gần nhất |
| @CreatedBy | Actor tạo |
| @LastModifiedBy | Actor sửa gần nhất |
| @Version | Phát hiện cập nhật cạnh tranh |

Không dùng updatedAt thay cho version. Hai transaction có thể cùng đọc một timestamp hoặc độ chính xác timestamp không đủ để phân biệt hai lần ghi rất gần nhau. Version là token concurrency được Spring Data quản lý theo semantics riêng.

Nếu entity có cả @Version và auditing, hai cơ chế có thể cùng hoạt động trong một lần save. Auditing cập nhật metadata; version kiểm tra trạng thái ghi và tăng version theo quy tắc optimistic locking.

## 15. Thời điểm audit được thiết lập trước commit

Auditing timestamp thường được thiết lập trong lifecycle trước khi câu lệnh ghi hoàn tất. Vì vậy, có thể có tình huống:

1. Entity được gán updatedAt.
2. UPDATE được gửi.
3. Một thao tác sau đó trong transaction thất bại.
4. Transaction rollback.

Database giữ timestamp cũ vì UPDATE chưa được commit. Nhưng object Java đang nằm trong bộ nhớ có thể vẫn chứa timestamp mới đã được gán trước đó.

Không nên xem giá trị audit trên object là bằng chứng transaction đã commit. Nếu transaction thất bại, hãy tải lại entity từ database trước khi sử dụng trạng thái persisted làm nguồn sự thật.

Điều này đặc biệt quan trọng với entity mutable được giữ lại trong cache hoặc tiếp tục dùng sau khi một reactive transaction lỗi.

## 16. Kiểm thử auditing

Nên kiểm thử trên database R2DBC thực tế hoặc Testcontainers để xác nhận mapping timestamp và auditor.

### Kiểm thử thời điểm tạo

Với Clock cố định:

~~~java
Instant fixedInstant =
    Instant.parse("2026-01-10T09:00:00Z");
~~~

Sau khi lưu entity mới, xác nhận:

- createdAt có giá trị.
- updatedAt có giá trị nếu modifyOnCreate = true.
- createdBy và updatedBy bằng actor hiện tại nếu auditor được cung cấp.

### Kiểm thử cập nhật

1. Tạo entity với actor alice.
2. Thay đổi Clock sang thời điểm khác hoặc dùng DateTimeProvider test có thể điều khiển.
3. Chuyển auditor sang bob.
4. Lưu entity đã thay đổi.
5. Đọc lại từ database.
6. Xác nhận createdAt và createdBy không đổi.
7. Xác nhận updatedAt và updatedBy phản ánh lần sửa.

### Kiểm thử tác vụ không có actor

Xác nhận chính sách khi ReactiveAuditorAware trả Mono.empty():

- Trường actor có thể không được thiết lập.
- Cột database có cho phép NULL hay không.
- Có cần actor mặc định như system hay không.

### Kiểm thử precision và timezone

Đừng luôn so sánh timestamp bằng equals với Instant nanosecond nếu database chỉ lưu microsecond hoặc millisecond. So sánh theo độ chính xác cột hoặc kiểm tra giá trị đã được chuẩn hóa theo quy ước của hệ thống.

Kiểm tra round-trip:

1. Ghi một Instant có phần lẻ giây.
2. Đọc lại qua cùng R2DBC driver.
3. Xác nhận thời điểm tương ứng sau khi xét precision của database.
4. Chạy test với session timezone được kiểm soát nếu database có chuyển đổi timezone theo session.

### Kiểm thử đường ghi SQL thuần

Nếu hệ thống dùng DatabaseClient, thêm test chứng minh các trường audit được cập nhật theo quy ước của câu SQL hoặc trigger. Không suy luận từ test repository save() rằng bulk update cũng tự auditing.

## 17. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ thêm @CreatedDate nhưng không bật auditing | Trường ngày không được tự thiết lập | Dùng @EnableR2dbcAuditing |
| Dùng @CreatedBy nhưng không có auditor provider | Không có actor để ghi | Cấu hình ReactiveAuditorAware |
| Dùng AuditorAware imperative trong reactive flow | Có thể không lấy được security context đúng | Dùng ReactiveAuditorAware |
| Đọc SecurityContextHolder từ thread hiện tại | Actor có thể sai hoặc vắng mặt khi đổi thread | Dùng ReactiveSecurityContextHolder |
| Quên modifyOnCreate | Hiểu nhầm vì updatedAt có giá trị ngay khi INSERT | Xác định chính sách create/update |
| Client gửi createdAt/createdBy | Có thể giả mạo audit metadata | Không nhận trường audit từ request |
| Trộn LocalDateTime và Instant | Sai lệch timezone hoặc semantics | Thống nhất kiểu thời gian |
| Dùng DB default nhưng INSERT gửi NULL | Default có thể không được áp dụng | Chọn một nguồn sở hữu timestamp và kiểm soát cột trong INSERT |
| Ghi bằng DatabaseClient rồi mong callback tự chạy | Trường audit không được cập nhật | Bind audit fields hoặc dùng trigger |
| Bulk update quên updated_at | Dữ liệu audit không nhất quán | Cập nhật trong SQL hoặc trigger |
| Dùng updatedAt thay @Version | Không phát hiện concurrency đáng tin cậy | Dùng @Version riêng |
| Không backfill cột mới | Migration lỗi hoặc dữ liệu cũ thiếu audit | Backfill trước khi đặt NOT NULL |
| Giả định timestamp luôn chính xác nanosecond | Test thất bại do precision database | So sánh theo precision thực tế |
| Giữ entity sau transaction rollback | Object có thể chứa timestamp chưa commit | Đọc lại trạng thái persisted |

## 18. Quy trình triển khai auditing

Có thể triển khai theo trình tự:

1. Xác định các trường cần ghi: created date, modified date, created actor, modified actor.
2. Chọn kiểu Java và kiểu cột database phù hợp.
3. Thêm các annotation auditing vào entity.
4. Tạo migration cho các cột audit và backfill dữ liệu hiện có.
5. Bật @EnableR2dbcAuditing.
6. Cấu hình ReactiveAuditorAware nếu cần actor.
7. Cấu hình DateTimeProvider/Clock nếu cần nguồn thời gian kiểm soát được.
8. Xác định modifyOnCreate và chính sách actor khi chạy background job.
9. Xác nhận mọi đường ghi có áp dụng cùng quy tắc audit.
10. Viết integration test cho INSERT, UPDATE, tác vụ nền, SQL thuần, timezone và precision.

Đừng để auditing phụ thuộc vào một quy ước ngầm. Hãy định nghĩa rõ ai là actor, thời gian được sinh ở đâu, khi tạo có cập nhật last-modified không và các bulk operation xử lý thế nào.

## 19. Ghi nhớ

- @CreatedDate và @LastModifiedDate ánh xạ thời điểm tạo và sửa; @CreatedBy và @LastModifiedBy ánh xạ actor.
- Phải bật auditing bằng @EnableR2dbcAuditing.
- Reactive application nên cung cấp ReactiveAuditorAware<T> để đọc actor theo Reactor Context.
- Không có auditor có thể khiến trường actor không được thiết lập; xác định chính sách cho background job.
- modifyOnCreate mặc định cho phép last-modified fields được thiết lập ngay khi tạo; có thể tắt nếu nghiệp vụ cần.
- Dùng DateTimeProvider và Clock để kiểm soát nguồn thời gian và giúp test xác định.
- Instant thường phù hợp với thời điểm tuyệt đối; kiểu Java, cột SQL và R2DBC codec phải tương thích.
- Chọn rõ UTC/timezone và precision; không trộn thời gian local với UTC trong cùng quy ước.
- Repository và thao tác entity của R2dbcEntityTemplate có lifecycle auditing; SQL DatabaseClient viết tay không tự chạy entity auditing callback.
- Bulk update cần tự cập nhật audit fields hoặc dựa trên trigger được thiết kế rõ.
- Auditing không thay thế @Version, audit log đầy đủ hoặc authorization.
- Timestamp được gán trong bộ nhớ trước commit không chứng minh transaction đã commit.
- Không nhận audit metadata từ client và không để một đường ghi bỏ qua quy tắc audit.
- Kiểm thử với đúng R2DBC driver/database, gồm actor, timezone, precision và đường ghi SQL thuần.
