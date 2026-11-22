# Phân biệt auditing mặc định với lịch sử thay đổi đầy đủ

Trong Spring Data JDBC, auditing mặc định giúp ghi nhận **ai tạo một aggregate và ai sửa nó lần gần nhất, vào thời điểm nào**. Các trường như `createdBy`, `createdDate`, `lastModifiedBy` và `lastModifiedDate` được cập nhật cùng entity thông qua hạ tầng auditing của Spring Data.

Thông tin đó hữu ích cho màn hình quản trị, truy vết trách nhiệm cơ bản và hỗ trợ vận hành. Tuy nhiên, nó không phải là lịch sử thay đổi đầy đủ. Khi một entity được sửa nhiều lần, `lastModifiedBy` và `lastModifiedDate` chỉ mô tả lần sửa mới nhất; giá trị cũ bị thay thế. Spring Data JDBC không tự tạo một bản ghi cho từng lần sửa, không tự lưu giá trị trước/sau của từng field và không tự ghi lại lý do thay đổi.

Nếu nghiệp vụ cần trả lời các câu hỏi như “ai đã đổi trạng thái từ PENDING sang APPROVED?”, “giá trị trước đó là gì?”, “đã có những lần thay đổi nào trong tháng này?” hoặc “ai đã xóa bản ghi?”, ứng dụng cần thiết kế một cơ chế lưu lịch sử riêng, chẳng hạn append-only audit table, database trigger, change data capture hoặc event sourcing.

Bài học phân biệt hai mục tiêu này, hướng dẫn bật auditing trong Spring Data JDBC và trình bày cách lưu lịch sử thay đổi đầy đủ cùng transaction với dữ liệu nghiệp vụ.

## 1. Auditing mặc định ghi nhận điều gì?

Spring Data cung cấp các annotation để lưu metadata về thời điểm tạo và sửa entity:

| Annotation | Thông tin được ghi nhận |
| --- | --- |
| `@CreatedBy` | Người hoặc principal tạo entity. |
| `@CreatedDate` | Thời điểm entity được tạo. |
| `@LastModifiedBy` | Người hoặc principal sửa entity gần nhất. |
| `@LastModifiedDate` | Thời điểm entity được sửa gần nhất. |

Các annotation có thể được sử dụng chọn lọc. Nếu chỉ cần ngày tạo và ngày sửa, ứng dụng không cần cung cấp `AuditorAware`. Nếu cần ghi người tạo hoặc người sửa, auditing infrastructure phải biết principal hiện tại thông qua `AuditorAware<T>`.

Ví dụ một dòng dữ liệu sau vài lần cập nhật:

~~~text
id   name       created_by   created_at           last_modified_by   last_modified_at
---  ---------  -----------  -------------------  -----------------  -------------------
42   Keyboard   user-101     2026-10-01T08:00Z     user-205           2026-11-13T09:30Z
~~~

Ta biết bản ghi được tạo bởi `user-101` và lần sửa gần nhất do `user-205` thực hiện. Nhưng chỉ từ các cột này, ta không biết:

- Ai đã sửa bản ghi vào ngày 3, ngày 8 và ngày 10.
- Tên sản phẩm trước mỗi lần sửa là gì.
- Trạng thái đã chuyển từ ACTIVE sang DISCONTINUED khi nào.
- Giá trị nào đã thay đổi trong từng lần cập nhật.
- Vì sao người dùng thực hiện thay đổi.
- Một bản ghi đã bị xóa hay chưa, nếu thao tác xóa không được ghi riêng.

Đó là giới hạn cốt lõi: **auditing mặc định giữ metadata hiện tại, không giữ chuỗi các phiên bản dữ liệu**.

## 2. Bật auditing trong Spring Data JDBC

Để kích hoạt auditing, thêm `@EnableJdbcAuditing` vào cấu hình Spring.

Ví dụ:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing
public class DataJdbcConfiguration {
}
~~~

Nếu entity có các field `@CreatedDate` và `@LastModifiedDate`, cấu hình này đủ để bật việc gán thời gian theo date-time provider mặc định.

Nếu cần ghi người tạo/người sửa, đăng ký một bean `AuditorAware`:

~~~java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing(auditorAwareRef = "auditorAware")
public class DataJdbcConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.of("system");
    }
}
~~~

Ví dụ trên dùng principal cố định `system` để minh họa cấu hình. Trong ứng dụng thật, auditor cần phản ánh người dùng hoặc service account thực hiện thao tác. Không nên dùng một giá trị cố định cho mọi request nếu cần truy vết trách nhiệm.

### 2.1. Lấy principal từ Spring Security

Nếu ứng dụng dùng Spring Security, có thể đọc tên principal từ `SecurityContextHolder`:

~~~java
import java.util.Optional;

import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component
public class SpringSecurityAuditorAware
        implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        return Optional.ofNullable(
                    SecurityContextHolder.getContext().getAuthentication()
                )
                .filter(Authentication::isAuthenticated)
                .filter(authentication ->
                        !(authentication instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName);
    }
}
~~~

Khi chỉ có một bean `AuditorAware` trong application context, auditing infrastructure có thể tự nhận diện bean đó. Nếu có nhiều bean, dùng `auditorAwareRef` trên `@EnableJdbcAuditing` để chỉ rõ bean cần sử dụng.

`AuditorAware<T>` phải trả về kiểu tương thích với các property được đánh dấu `@CreatedBy` và `@LastModifiedBy`. Nếu các field đó là `String`, dùng `AuditorAware<String>`; nếu lưu một kiểu user domain, dùng kiểu tương ứng.

### 2.2. Request không có người dùng tương tác

Không phải thao tác nào cũng xuất phát từ một người dùng đăng nhập. Ví dụ:

- Scheduled job cập nhật dữ liệu.
- Worker xử lý message.
- Tiến trình import.
- Tác vụ bảo trì.
- Hệ thống đồng bộ dữ liệu giữa các service.

Trong những trường hợp đó, cần xác định actor có ý nghĩa như `batch-import`, `inventory-sync` hoặc một service account cụ thể. Có thể dùng context do ứng dụng quản lý để cung cấp actor cho `AuditorAware`.

Đừng gán mọi thao tác không có `Authentication` thành một user giả mà không phân biệt nguồn. Nếu audit cần giải thích nguồn thay đổi, hãy ghi thêm `source` hoặc `actorType` trong audit event.

### 2.3. Tùy chỉnh thời gian bằng DateTimeProvider

`@EnableJdbcAuditing` cho phép chỉ định `dateTimeProviderRef` để thay đổi nguồn thời gian. Điều này hữu ích khi muốn dùng UTC thống nhất hoặc inject `Clock` để kiểm thử.

Ví dụ:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing(dateTimeProviderRef = "auditDateTimeProvider")
public class DataJdbcConfiguration {

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditDateTimeProvider(Clock auditClock) {
        return () -> Optional.of(Instant.now(auditClock));
    }
}
~~~

Nếu đồng thời cần `AuditorAware`, hãy khai báo cả `auditorAwareRef` và `dateTimeProviderRef` trong cùng cấu hình auditing.

Trong `@EnableJdbcAuditing` của Spring Data Relational 4.1.2:

- `setDates` mặc định là `true`, tức ngày tạo và ngày sửa được thiết lập.
- `modifyOnCreate` mặc định là `true`, tức entity có thể được đánh dấu modified ngay khi tạo.
- `auditorAwareRef` chọn bean cung cấp principal.
- `dateTimeProviderRef` chọn bean cung cấp thời gian.

Các thuộc tính này điều chỉnh metadata hiện tại của entity; chúng không biến auditing thành cơ chế lưu lịch sử phiên bản.

## 3. Khai báo auditing metadata trên aggregate

Ví dụ aggregate `Customer`:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    private String name;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedAt;

    @Version
    private Long version;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException(
                    "Customer name is required"
            );
        }
        this.name = newName;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

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

    public Long getVersion() {
        return version;
    }
}
~~~

Schema có thể là:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    created_by VARCHAR(150),
    created_at TIMESTAMP WITH TIME ZONE,
    last_modified_by VARCHAR(150),
    last_modified_at TIMESTAMP WITH TIME ZONE,
    version BIGINT NOT NULL
);
~~~

Khi tạo customer và cập nhật qua Spring Data JDBC, auditing infrastructure điền metadata tương ứng. Ví dụ:

| Thời điểm | createdBy | createdAt | lastModifiedBy | lastModifiedAt |
| --- | --- | --- | --- | --- |
| Sau insert | user-101 | 08:00 | user-101 | 08:00 |
| Sau lần sửa 1 | user-101 | 08:00 | user-205 | 09:00 |
| Sau lần sửa 2 | user-101 | 08:00 | user-310 | 10:30 |

`createdBy` và `createdAt` giữ thông tin ban đầu. `lastModifiedBy` và `lastModifiedAt` phản ánh lần sửa gần nhất. Giá trị của `user-205` và thời điểm 09:00 không còn được lưu trong các cột hiện tại sau lần sửa thứ hai.

### 3.1. @Version không phải audit history

Trong ví dụ trên có thêm `@Version`. Hai nhóm field có mục đích khác nhau:

| Field | Mục đích |
| --- | --- |
| `@CreatedBy`, `@CreatedDate` | Metadata tạo entity. |
| `@LastModifiedBy`, `@LastModifiedDate` | Metadata sửa gần nhất. |
| `@Version` | Phát hiện cập nhật cạnh tranh bằng optimistic locking. |

Version có thể tăng sau mỗi lần update, nhưng chỉ có một số version hiện tại trên aggregate. Nó không tự tạo bản ghi cho các version cũ và không lưu snapshot dữ liệu trước đó.

Nếu database chỉ có `version = 7`, ta biết aggregate đã đi qua các lần cập nhật theo cơ chế versioning, nhưng không thể dựng lại nội dung của version 1 đến 6 nếu không lưu chúng ở nơi khác.

### 3.2. Auditing không tự tạo diff

Auditing mặc định không so sánh từng field để tạo một bản ghi dạng:

~~~text
name:   "Keyboard" -> "Mechanical Keyboard"
price:  100.00     -> 120.00
status: "DRAFT"    -> "ACTIVE"
~~~

Nó chỉ cập nhật các field auditing được khai báo. Nếu cần diff, ứng dụng phải tự lấy trạng thái trước/sau, dùng cơ chế database-level history hoặc lưu domain event thể hiện thay đổi.

## 4. So sánh auditing mặc định và lịch sử thay đổi đầy đủ

| Khả năng | Auditing mặc định | Full change history |
| --- | --- | --- |
| Ai tạo bản ghi | Có, qua `@CreatedBy` | Có thể ghi trong event |
| Khi nào tạo | Có, qua `@CreatedDate` | Có thể ghi trong event |
| Ai sửa gần nhất | Có, qua `@LastModifiedBy` | Có |
| Khi nào sửa gần nhất | Có, qua `@LastModifiedDate` | Có |
| Các lần sửa trước | Không | Có |
| Giá trị trước/sau | Không | Có nếu thiết kế lưu |
| Field nào thay đổi | Không tự ghi | Có thể lưu diff |
| Lý do thay đổi | Không tự ghi | Có thể lưu |
| Correlation/request ID | Không tự ghi | Có thể lưu |
| Lịch sử xóa | Không tự tạo | Có thể ghi delete event/tombstone |
| Khôi phục trạng thái cũ | Không | Có thể nếu lưu snapshot hoặc event đủ dữ liệu |

Một hệ thống có thể dùng đồng thời cả hai:

- Auditing metadata để truy vấn nhanh ai tạo và ai sửa gần nhất.
- Audit event table để tra cứu toàn bộ lịch sử thay đổi.

Không cần chọn một trong hai nếu ứng dụng có cả nhu cầu hiển thị metadata hiện tại và nhu cầu kiểm toán chi tiết.

## 5. Thiết kế audit history bằng append-only table

Một cách phổ biến để lưu lịch sử đầy đủ là tạo bảng audit riêng. Mỗi lần thay đổi nghiệp vụ, ứng dụng thêm một hàng mới thay vì ghi đè hàng lịch sử cũ.

Ví dụ:

~~~text
customers
---------
id = 42
name = "Mechanical Keyboard"
status = "ACTIVE"

customer_audit_events
---------------------
event 1: CUSTOMER_CREATED
event 2: CUSTOMER_NAME_CHANGED
event 3: CUSTOMER_STATUS_CHANGED
event 4: CUSTOMER_PRICE_CHANGED
~~~

Một audit event có thể chứa:

- Aggregate type và ID.
- Loại hành động hoặc event.
- Actor thực hiện.
- Thời điểm xảy ra.
- Version sau thay đổi.
- Giá trị cũ và mới hoặc một payload diff.
- Lý do thay đổi.
- Correlation ID/request ID.
- Nguồn thực hiện thay đổi.
- Phiên bản schema của payload.

### 5.1. Schema audit table

Ví dụ dùng cột `TEXT` để lưu JSON payload theo cách tương đối đơn giản, không phụ thuộc trực tiếp vào kiểu JSON native của một database cụ thể:

~~~sql
CREATE TABLE customer_audit_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    actor_id VARCHAR(150) NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    aggregate_version BIGINT,
    reason VARCHAR(1000),
    correlation_id VARCHAR(150),
    changes_json TEXT NOT NULL,
    schema_version INTEGER NOT NULL
);

CREATE INDEX idx_customer_audit_aggregate_time
    ON customer_audit_events(
        aggregate_type,
        aggregate_id,
        occurred_at,
        id
    );

CREATE INDEX idx_customer_audit_correlation
    ON customer_audit_events(correlation_id);
~~~

Không nhất thiết phải tạo một bảng riêng cho mỗi loại aggregate. Có thể dùng một bảng chung với `aggregate_type` và `aggregate_id`, hoặc tách bảng theo domain khi yêu cầu truy vấn, retention và quyền truy cập khác nhau.

Nếu cần foreign key từ audit row về aggregate, hãy cân nhắc rằng lịch sử thường cần tồn tại sau khi aggregate bị xóa. Một foreign key cascade delete có thể xóa luôn lịch sử và làm mất mục đích audit. Nhiều hệ thống giữ `aggregate_id` như giá trị tham chiếu logic, không cascade theo vòng đời aggregate.

### 5.2. Audit event là bản ghi bất biến

Một audit table nên được thiết kế theo hướng append-only:

- Mỗi thay đổi tạo một event mới.
- Không sửa event cũ để phản ánh trạng thái mới.
- Không xóa lịch sử chỉ vì aggregate đã bị xóa.
- Hạn chế quyền UPDATE/DELETE trên bảng audit.
- Có chính sách retention, backup và kiểm soát truy cập.
- Có thể bổ sung checksum hoặc cơ chế tamper-evident nếu yêu cầu kiểm toán cần chứng minh tính toàn vẹn.

`CrudRepository` cung cấp cả thao tác update và delete, vì vậy chỉ dùng tên bảng `audit_events` không tự bảo đảm tính append-only. Có thể giới hạn repository interface chỉ công khai insert/read, đồng thời dùng database permission để ngăn tài khoản ứng dụng sửa hoặc xóa lịch sử.

## 6. Lưu audit event cùng transaction với thay đổi nghiệp vụ

Nếu audit history là một phần bắt buộc của dữ liệu nghiệp vụ, thao tác cập nhật aggregate và thêm audit event nên nằm trong cùng transaction database.

Ví dụ event model:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer_audit_events")
public record CustomerAuditEvent(
        @Id Long id,
        String aggregateType,
        Long aggregateId,
        String eventType,
        String actorId,
        Instant occurredAt,
        Long aggregateVersion,
        String reason,
        String correlationId,
        String changesJson,
        Integer schemaVersion
) {
}
~~~

Repository chỉ công khai các thao tác cần thiết:

~~~java
import java.util.List;

import org.springframework.data.repository.Repository;

public interface CustomerAuditEventRepository
        extends Repository<CustomerAuditEvent, Long> {

    <S extends CustomerAuditEvent> S save(S event);

    List<CustomerAuditEvent>
    findByAggregateTypeAndAggregateIdOrderByOccurredAtAscIdAsc(
            String aggregateType,
            Long aggregateId
    );
}
~~~

Service cập nhật customer và ghi event:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Map;
import java.util.Objects;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.data.domain.AuditorAware;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerCommandService {

    private final CustomerRepository customerRepository;
    private final CustomerAuditEventRepository auditRepository;
    private final AuditorAware<String> auditorAware;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    public CustomerCommandService(
            CustomerRepository customerRepository,
            CustomerAuditEventRepository auditRepository,
            AuditorAware<String> auditorAware,
            ObjectMapper objectMapper,
            Clock clock
    ) {
        this.customerRepository = customerRepository;
        this.auditRepository = auditRepository;
        this.auditorAware = auditorAware;
        this.objectMapper = objectMapper;
        this.clock = clock;
    }

    @Transactional
    public Customer rename(
            Long customerId,
            String newName,
            String reason,
            String correlationId
    ) {
        Customer customer = customerRepository.findById(customerId)
                .orElseThrow();

        String oldName = customer.getName();

        customer.rename(newName);

        Customer saved = customerRepository.save(customer);

        if (!Objects.equals(oldName, saved.getName())) {
            String actor = auditorAware.getCurrentAuditor()
                    .orElseThrow(() ->
                            new IllegalStateException(
                                    "An audit actor is required"
                            )
                    );

            String changes = toJson(Map.of(
                    "name", Map.of(
                            "old", oldName,
                            "new", saved.getName()
                    )
            ));

            auditRepository.save(new CustomerAuditEvent(
                    null,
                    "Customer",
                    saved.getId(),
                    "CUSTOMER_NAME_CHANGED",
                    actor,
                    Instant.now(clock),
                    saved.getVersion(),
                    reason,
                    correlationId,
                    changes,
                    1
            ));
        }

        return saved;
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(
                    "Cannot serialize audit changes",
                    exception
            );
        }
    }
}
~~~

Trong ví dụ này:

1. Service tải trạng thái customer trước khi thay đổi.
2. Ghi nhớ giá trị cũ của `name`.
3. Thực hiện hành vi domain và lưu aggregate.
4. So sánh giá trị trước/sau.
5. Tạo audit event nếu có thay đổi thực tế.
6. Ghi event vào audit table trong cùng transaction.

Cả hai repository phải dùng cùng DataSource và transaction manager để tham gia cùng transaction. Nếu insert audit event thất bại, transaction có thể rollback cả cập nhật customer. Điều này phù hợp khi không được phép có thay đổi nghiệp vụ mà thiếu audit record tương ứng.

Trong ứng dụng thực tế, actor nên lấy từ context tin cậy của server. Không dùng `actorId` do client tùy ý gửi lên làm danh tính kiểm toán. `reason` và `correlationId` có thể đến từ request sau khi được validate, nhưng danh tính actor cần được xác thực.

### 6.1. Vì sao cần transaction chung?

Nếu cập nhật customer commit trước rồi mới ghi audit event trong transaction riêng, lỗi ở lần ghi audit có thể tạo ra:

~~~text
customers:
  name = "New name"       COMMITTED

customer_audit_events:
  không có event tương ứng
~~~

Dữ liệu nghiệp vụ đã thay đổi nhưng lịch sử bị thiếu.

Khi cả hai thao tác nằm trong một transaction:

~~~text
BEGIN
  UPDATE customers
  INSERT customer_audit_events
COMMIT
~~~

Nếu một trong hai thao tác thất bại, database rollback cả hai. Đây là cách giữ tính nhất quán giữa trạng thái hiện tại và lịch sử bắt buộc.

### 6.2. Audit event và transactional outbox khác nhau

Audit event ghi lại điều đã xảy ra trong nghiệp vụ để truy vấn và kiểm toán. Outbox ghi thông điệp cần được chuyển đến hệ thống khác một cách bền vững sau commit.

Hai loại dữ liệu có thể cùng được tạo trong một transaction, nhưng không đồng nghĩa:

- Audit history phục vụ truy vấn lịch sử và giải thích thay đổi.
- Outbox phục vụ chuyển giao sự kiện đến broker hoặc hệ thống bên ngoài.
- Một audit event không tự động được publish đáng tin cậy ra message broker.
- Một outbox message không nhất thiết chứa đầy đủ dữ liệu kiểm toán cần lưu lâu dài.

Nếu cần cả hai, có thể ghi audit row và outbox row cùng transaction với aggregate update, sau đó worker publish outbox.

## 7. Lưu diff hay lưu snapshot?

Có hai chiến lược phổ biến cho payload lịch sử.

### 7.1. Field-level diff

Chỉ lưu các field thay đổi:

~~~json
{
  "name": {
    "old": "Keyboard",
    "new": "Mechanical Keyboard"
  },
  "status": {
    "old": "DRAFT",
    "new": "ACTIVE"
  }
}
~~~

Ưu điểm:

- Dễ đọc và dễ hiển thị thay đổi.
- Dữ liệu mỗi event thường nhỏ.
- Có thể tìm kiếm những thay đổi theo field nếu cấu trúc được chuẩn hóa.

Hạn chế:

- Phải tự phát hiện và serialize các field thay đổi.
- Khó dựng lại trạng thái đầy đủ nếu thiếu một event.
- Cần xử lý rename field, thay đổi schema và migration payload.
- Với object phức tạp, diff có thể khó diễn giải.

### 7.2. Snapshot trước/sau

Lưu toàn bộ trạng thái trước và sau:

~~~json
{
  "before": {
    "name": "Keyboard",
    "status": "DRAFT",
    "price": 100.00
  },
  "after": {
    "name": "Mechanical Keyboard",
    "status": "ACTIVE",
    "price": 120.00
  }
}
~~~

Ưu điểm:

- Dễ xem trạng thái ở một thời điểm.
- Có thể dựng lại một phiên bản cụ thể từ snapshot.
- Không cần ghép nhiều diff để hiểu toàn bộ entity.

Hạn chế:

- Tốn dung lượng hơn.
- Có thể lưu lại dữ liệu nhạy cảm không cần thiết.
- Cần version hóa schema snapshot.
- Cần chính sách retention và masking.

### 7.3. Kết hợp snapshot định kỳ và diff

Với lịch sử rất dài, có thể lưu snapshot định kỳ và các event/diff giữa hai snapshot. Khi cần dựng lại trạng thái tại một thời điểm, hệ thống lấy snapshot gần nhất rồi áp dụng các thay đổi tiếp theo.

Cách này giảm số event phải replay, nhưng tăng độ phức tạp. Chỉ nên dùng khi nhu cầu truy vấn lịch sử hoặc khôi phục trạng thái thực sự cần thiết.

## 8. Ghi nhận thao tác xóa

Các field `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy` và `@LastModifiedBy` không tự tạo một lịch sử xóa hoàn chỉnh. Khi một aggregate bị xóa, hàng chứa metadata đó cũng có thể bị xóa.

Nếu cần lưu lịch sử xóa, phải ghi nhận rõ hành động trước hoặc cùng thao tác xóa.

Ví dụ service:

~~~java
@Transactional
public void deleteCustomer(
        Long customerId,
        String reason,
        String correlationId
) {
    Customer customer = customerRepository.findById(customerId)
            .orElseThrow();

    String actor = auditorAware.getCurrentAuditor()
            .orElseThrow();

    auditRepository.save(new CustomerAuditEvent(
            null,
            "Customer",
            customer.getId(),
            "CUSTOMER_DELETED",
            actor,
            Instant.now(clock),
            customer.getVersion(),
            reason,
            correlationId,
            toJson(Map.of(
                    "name", customer.getName()
            )),
            1
    ));

    customerRepository.delete(customer);
}
~~~

Audit event và thao tác xóa cần cùng transaction. Nếu xóa thất bại, event ghi nhận việc xóa cũng rollback; nếu event không ghi được, thao tác xóa không commit.

Nếu ứng dụng cần giữ dữ liệu hiện tại sau khi người dùng “xóa”, có thể dùng soft delete bằng `deletedAt`, `deletedBy` và trạng thái tương ứng. Tuy nhiên, soft delete vẫn chỉ là metadata trạng thái hiện tại; nếu cần lịch sử của nhiều lần xóa/khôi phục, vẫn cần audit events.

## 9. Các phương án lưu lịch sử khác

Audit table trong application service không phải phương án duy nhất. Lựa chọn phụ thuộc phạm vi dữ liệu cần theo dõi và những writer nào phải được kiểm soát.

### 9.1. Application-level audit table

Service hoặc domain handler tạo audit event khi thực hiện use case.

Phù hợp khi:

- Cần actor, reason, command ID hoặc correlation ID.
- Muốn ghi nhận ngữ nghĩa nghiệp vụ như `ORDER_APPROVED`, không chỉ SQL UPDATE.
- Cần transaction chung với aggregate.
- Có thể kiểm soát mọi đường ghi qua ứng dụng.

Hạn chế: nếu có một chương trình khác ghi thẳng vào database và bỏ qua service, nó có thể không tạo audit event.

### 9.2. Database trigger

Trigger chạy khi database nhận INSERT, UPDATE hoặc DELETE trên bảng được theo dõi.

Phù hợp khi:

- Cần bắt thay đổi từ nhiều ứng dụng hoặc nhiều writer.
- Muốn database tự ghi lại old/new row.
- Cần bảo vệ audit history ngay cả khi có thao tác SQL trực tiếp.

Hạn chế:

- Cú pháp và hành vi phụ thuộc database.
- Trigger có thể khó kiểm thử và triển khai migration.
- Database biết session/database user, nhưng không tự biết principal nghiệp vụ của ứng dụng nếu ứng dụng không truyền context.
- Trigger ghi row-level change có thể không hiểu ý nghĩa domain hoặc lý do thay đổi.

### 9.3. Change Data Capture (CDC)

CDC đọc transaction log hoặc cơ chế change stream của database để phát hiện các thay đổi đã commit.

Phù hợp khi:

- Cần theo dõi thay đổi từ nhiều writer.
- Muốn chuyển dữ liệu thay đổi đến data warehouse, search index hoặc hệ thống downstream.
- Muốn xử lý bất đồng bộ mà không thêm logic audit vào từng service.

Hạn chế:

- CDC thường ghi nhận thay đổi dữ liệu ở mức bảng/row, không tự hiểu command nghiệp vụ.
- Actor, reason và correlation ID không tự xuất hiện nếu không được lưu kèm dữ liệu hoặc context.
- Cần vận hành connector, offset, retry, schema evolution và retention transaction log.
- CDC là luồng bất đồng bộ; không thay thế ranh giới transaction của use case.

### 9.4. Event sourcing

Trong event sourcing, event là nguồn dữ liệu chính để xác định trạng thái aggregate. Trạng thái hiện tại được dựng bằng cách áp dụng chuỗi event.

Ví dụ:

~~~text
CustomerRegistered
CustomerNameChanged
CustomerEmailChanged
CustomerDeactivated
~~~

Phù hợp khi:

- Lịch sử thay đổi là một phần cốt lõi của domain.
- Cần dựng lại trạng thái tại các thời điểm trước.
- Cần hiểu vì sao trạng thái hiện tại hình thành.
- Domain có event model rõ ràng.

Event sourcing là một lựa chọn kiến trúc lớn, không phải chỉ thêm một bảng audit vào Spring Data JDBC. Ứng dụng phải xử lý event versioning, replay, snapshot, idempotency, eventual consistency và quy trình migration event.

### 9.5. Không nhầm Spring Data JDBC auditing với Hibernate Envers

Hibernate Envers là giải pháp auditing dành cho Hibernate/JPA. Spring Data JDBC không dùng Hibernate persistence context và không tự cung cấp Envers như một tính năng auditing mặc định.

Nếu dự án dùng Spring Data JDBC, hãy thiết kế audit table, trigger, CDC hoặc event model phù hợp với hạ tầng JDBC của dự án. Không sao chép cấu hình Envers của JPA rồi kỳ vọng nó hoạt động với Spring Data JDBC.

## 10. Khi nào chỉ cần auditing mặc định?

Auditing mặc định thường đủ nếu yêu cầu chỉ là:

- Hiển thị ngày tạo và ngày cập nhật gần nhất.
- Biết người tạo và người sửa gần nhất.
- Hỗ trợ điều tra vận hành cơ bản.
- Sắp xếp dữ liệu theo lần sửa gần nhất.
- Theo dõi metadata cho các bảng nghiệp vụ thông thường.

Ví dụ màn hình danh sách khách hàng:

~~~text
Customer            Created             Last modified by   Last modified
------------------  ------------------  -----------------  ------------------
Nguyễn An           2026-10-01 08:00    user-205           2026-11-13 09:30
Trần Bình           2026-10-04 10:15    user-101           2026-11-12 16:20
Lê Chi              2026-10-08 14:00    system             2026-11-10 02:00
~~~

Màn hình này chỉ cần trạng thái hiện tại và metadata của lần sửa gần nhất. Không cần một bảng lưu mọi revision.

Không nên thêm full history chỉ vì hệ thống có field `createdAt` hoặc `updatedAt`. Hãy xác định câu hỏi nghiệp vụ cần trả lời và mức độ truy vết cần thiết.

## 11. Khi nào cần full change history?

Nên thiết kế lịch sử đầy đủ khi cần một hoặc nhiều yêu cầu:

- Phải biết tất cả lần thay đổi của một hồ sơ.
- Cần xem giá trị trước và sau của field.
- Cần xác định actor, thời điểm, lý do và nguồn thay đổi.
- Cần chứng minh ai đã phê duyệt hoặc hủy một giao dịch.
- Cần điều tra thay đổi bất thường.
- Cần khôi phục trạng thái cũ hoặc tái dựng dữ liệu.
- Có yêu cầu kiểm toán, quản trị hoặc tuân thủ.
- Cần đồng bộ thay đổi đến hệ thống downstream với khả năng truy vết.

Ví dụ lịch sử trạng thái đơn hàng:

| Thời điểm | Actor | Trạng thái cũ | Trạng thái mới | Lý do |
| --- | --- | --- | --- | --- |
| 08:00 | customer-12 | — | DRAFT | Tạo đơn |
| 08:05 | user-45 | DRAFT | CONFIRMED | Xác nhận đơn |
| 08:20 | warehouse-2 | CONFIRMED | PICKING | Bắt đầu lấy hàng |
| 09:10 | user-45 | PICKING | CANCELLED | Khách yêu cầu hủy |

Các field `lastModifiedBy` và `lastModifiedAt` trên order chỉ phản ánh dòng cuối cùng. Bảng lịch sử mới trả lời được toàn bộ chuỗi chuyển trạng thái.

## 12. Những vấn đề cần thiết kế cho audit history

Một bảng audit chỉ có `id`, `actor` và `timestamp` thường chưa đủ nếu cần điều tra thay đổi.

Hãy quyết định các trường sau:

| Trường | Câu hỏi được trả lời |
| --- | --- |
| `aggregateType` | Loại đối tượng nào đã thay đổi? |
| `aggregateId` | Đối tượng cụ thể nào? |
| `eventType` | Hành động gì đã xảy ra? |
| `actorId` | Ai hoặc service nào thực hiện? |
| `occurredAt` | Khi nào? |
| `aggregateVersion` | Thay đổi thuộc version nào? |
| `changesJson` | Field nào đổi, từ giá trị nào sang giá trị nào? |
| `reason` | Vì sao thực hiện thay đổi? |
| `correlationId` | Request hoặc workflow nào tạo thay đổi? |
| `source` | UI, API, batch, worker hay hệ thống tích hợp? |
| `schemaVersion` | Payload được serialize theo schema nào? |

### 12.1. Thời gian và thứ tự event

Timestamp có thể trùng nhau, đặc biệt khi nhiều event được tạo trong cùng một khoảng thời gian ngắn. Vì vậy, nên có một ID tăng dần hoặc sequence để tạo thứ tự xác định trong cùng aggregate.

`occurredAt` là thời điểm ứng dụng ghi nhận event. Nếu cần thứ tự commit chính xác trên nhiều node hoặc cần thời gian do database xác nhận, hãy thiết kế thêm metadata phù hợp; không nên coi đồng hồ ứng dụng phân tán là nguồn thứ tự tuyệt đối.

### 12.2. Dữ liệu nhạy cảm và quyền truy cập

Audit history có thể chứa giá trị cũ/mới của dữ liệu cá nhân hoặc bí mật. Không nên serialize toàn bộ entity một cách máy móc.

Cần:

- Chỉ lưu field cần cho mục đích kiểm toán.
- Loại bỏ password, token, secret và dữ liệu xác thực.
- Mask hoặc hash dữ liệu khi phù hợp.
- Hạn chế ai được đọc audit history.
- Quy định retention và xóa theo chính sách pháp lý.
- Bảo vệ audit table khỏi update/delete ngoài quy trình quản trị.
- Không ghi thông tin nhạy cảm vào log ứng dụng chỉ để thay thế audit table.

Tính đầy đủ của audit không có nghĩa là lưu mọi byte của dữ liệu. Chỉ ghi dữ liệu cần thiết cho mục đích đã xác định.

## 13. Tác động của các đường ghi khác nhau

Auditing mặc định của Spring Data JDBC hoạt động trong luồng persistence của Spring Data. Nếu ứng dụng ghi dữ liệu bằng một đường khác, không nên mặc định các callback auditing vẫn được gọi.

| Cách ghi | Auditing metadata mặc định |
| --- | --- |
| `repository.save(aggregate)` | Được áp dụng theo auditing configuration. |
| `JdbcAggregateTemplate` qua Spring Data JDBC | Đi qua hạ tầng Spring Data JDBC. |
| `JdbcTemplate.update(...)` trực tiếp | Không nên giả định auditing callback được gọi. |
| SQL chạy từ script ngoài ứng dụng | Không gọi auditing callback của Spring. |
| Một service khác ghi trực tiếp database | Không tự động cập nhật auditing metadata nếu không có cơ chế riêng. |
| Database trigger | Có thể tự ghi lịch sử ở database level nếu đã cấu hình. |

Nếu có nhiều ứng dụng hoặc batch job cùng ghi một bảng, chỉ dựa vào `@LastModifiedBy` trong một service có thể không đủ. Hãy cân nhắc trigger hoặc CDC để bắt mọi thay đổi ở database, hoặc quy định tất cả writer phải đi qua một API ghi thống nhất.

## 14. Kiểm thử auditing mặc định

Một integration test có thể xác nhận metadata được điền sau insert và update.

Ví dụ khung test với `AuditorAware` test cố định:

~~~java
@TestConfiguration
@EnableJdbcAuditing(auditorAwareRef = "testAuditor")
class TestAuditingConfiguration {

    @Bean
    AuditorAware<String> testAuditor() {
        return () -> Optional.of("test-user");
    }
}
~~~

Test:

~~~java
@SpringBootTest
class CustomerAuditingTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void recordsCreationAndLastModificationMetadata() {
        Customer created = repository.save(
                new Customer("Nguyễn An")
        );

        assertEquals("test-user", created.getCreatedBy());
        assertEquals("test-user", created.getLastModifiedBy());
        assertNotNull(created.getCreatedAt());
        assertNotNull(created.getLastModifiedAt());

        Customer loaded = repository.findById(created.getId())
                .orElseThrow();

        loaded.rename("Nguyễn An Updated");

        Customer updated = repository.save(loaded);

        assertEquals("test-user", updated.getCreatedBy());
        assertEquals("test-user", updated.getLastModifiedBy());
        assertNotNull(updated.getLastModifiedAt());
    }
}
~~~

Trong test thực tế, có thể dùng auditor thay đổi theo từng bước để xác nhận `createdBy` giữ actor ban đầu và `lastModifiedBy` chuyển sang actor mới.

### 14.1. Kiểm thử full history

Với audit event table, kiểm tra thêm:

1. Insert aggregate tạo đúng event `CREATED`.
2. Update field tạo event `UPDATED` với old/new value.
3. Không có thay đổi thực tế thì có hoặc không tạo event theo chính sách đã chọn.
4. Nếu insert audit event thất bại, update aggregate cũng rollback.
5. Delete tạo event `DELETED` và lịch sử vẫn còn.
6. Nhiều thay đổi liên tiếp giữ đúng thứ tự.
7. Actor, reason và correlation ID được gán từ context đúng.
8. Payload không chứa dữ liệu nhạy cảm.

Test transaction rollback cần dùng database integration test; mock repository không chứng minh được hai thao tác thực sự cùng commit hoặc rollback.

## 15. Những lỗi thường gặp

**“@LastModifiedDate lưu tất cả các lần sửa.”** Không. Nó chỉ giữ thời điểm sửa gần nhất trong hàng hiện tại.

**“@CreatedBy và @LastModifiedBy tạo bảng history.”** Không. Chúng ghi metadata vào entity được mapping.

**“@Version là version history.”** Không. Version dùng để phát hiện cập nhật cạnh tranh; nó không lưu snapshot các version trước.

**“Auditing mặc định ghi field nào đã thay đổi.”** Không. Nó không tự tạo diff từng field hoặc lưu old/new values.

**“Chỉ cần bật @EnableJdbcAuditing là biết user hiện tại.”** Không. Nếu cần `@CreatedBy` hoặc `@LastModifiedBy`, phải cung cấp `AuditorAware` phù hợp.

**“Không có AuditorAware thì không thể dùng auditing.”** Không đúng. Nếu chỉ ghi ngày tạo/ngày sửa, có thể dùng auditing date mà không cần auditor provider.

**“Delete cũng tự giữ lại created/modified metadata.”** Không. Khi hàng bị xóa, metadata trên hàng cũng mất; cần delete event, soft delete, trigger hoặc cơ chế lịch sử riêng.

**“JdbcTemplate.update cũng tự chạy auditing callback.”** Không nên giả định. SQL trực tiếp không đi qua luồng auditing entity của Spring Data JDBC.

**“Ghi audit event sau khi commit là luôn an toàn.”** Không nếu event là dữ liệu bắt buộc. Process có thể dừng sau khi aggregate commit nhưng trước khi ghi event. Hãy ghi audit row trong cùng transaction hoặc dùng outbox nếu cần chuyển sự kiện ra ngoài.

**“Audit event và outbox là một.”** Không. Audit phục vụ lịch sử/kiểm toán; outbox phục vụ chuyển giao thông điệp bền vững.

**“Lưu toàn bộ object JSON vào audit table luôn tốt.”** Không. Có thể lưu thừa dữ liệu nhạy cảm, payload lớn và khó tương thích schema. Hãy chọn diff hoặc snapshot theo nhu cầu.

**“Chỉ cần lưu actor và timestamp là đủ.”** Không nếu cần biết field nào đổi, giá trị cũ/mới, lý do và nguồn thay đổi.

**“Có thể sửa audit row cũ để phản ánh dữ liệu mới.”** Điều đó phá vỡ ý nghĩa append-only. Mỗi lần thay đổi nên tạo event mới; việc sửa sai lịch sử cần có event điều chỉnh và quy trình quản trị được kiểm soát.

**“Hibernate Envers dùng trực tiếp cho Spring Data JDBC.”** Không. Envers là giải pháp gắn với Hibernate/JPA; Spring Data JDBC cần cơ chế audit phù hợp với JDBC.

## 16. Quy trình quyết định

Khi thiết kế auditing cho một aggregate, hãy xác định câu hỏi cần trả lời:

1. **Chỉ cần biết ai tạo và ai sửa gần nhất?** Dùng `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, `@LastModifiedDate`.
2. **Cần biết người thực hiện?** Cấu hình `AuditorAware<T>` và principal đáng tin cậy.
3. **Cần thời gian nhất quán?** Dùng `DateTimeProvider` và `Clock` phù hợp, thường thống nhất UTC.
4. **Cần lịch sử từng lần thay đổi?** Thiết kế append-only audit event hoặc version table.
5. **Cần old/new values?** Lưu field-level diff hoặc snapshot trước/sau.
6. **Cần ghi nhận xóa?** Tạo delete event, soft-delete hoặc database-level history.
7. **Có nhiều writer ngoài Spring Data JDBC?** Cân nhắc database trigger hoặc CDC.
8. **Cần đồng bộ event ra hệ thống ngoài?** Dùng transactional outbox hoặc cơ chế publish đáng tin cậy.
9. **Cần dựng lại trạng thái từ event?** Đánh giá event sourcing như một quyết định kiến trúc riêng.
10. **Audit có bắt buộc cùng dữ liệu nghiệp vụ?** Ghi audit row trong cùng transaction và cùng resource.
11. **Có dữ liệu nhạy cảm?** Giới hạn payload, quyền đọc và retention.
12. **Đã kiểm thử rollback và delete history chưa?** Xác nhận audit không bị thiếu khi một bước persistence thất bại.

~~~mermaid
flowchart TD
    A["Cần theo dõi dữ liệu"] --> B{"Chỉ cần ai tạo/sửa gần nhất và thời gian?"}
    B -->|Có| C["Spring Data JDBC Auditing"]
    C --> D["@CreatedBy / @CreatedDate<br/>@LastModifiedBy / @LastModifiedDate"]
    B -->|Không, cần các lần thay đổi| E{"Cần old/new values và actor nghiệp vụ?"}
    E -->|Có| F["Append-only audit event table"]
    E -->|Không, cần bắt mọi SQL writer| G["Database trigger hoặc CDC"]
    F --> H{"Cần publish sang hệ thống ngoài?"}
    H -->|Có| I["Ghi outbox cùng transaction"]
    H -->|Không| J["Truy vấn audit history"]
    G --> J
    D --> K["Lưu metadata hiện tại"]
    I --> L["Worker publish sau commit"]
~~~

## 17. Bài tập thực hành

Tạo aggregate `Customer` với các field `id`, `name`, `createdBy`, `createdAt`, `lastModifiedBy`, `lastModifiedAt` và `version`.

### Bài 1: Bật auditing mặc định

1. Thêm `@EnableJdbcAuditing`.
2. Đăng ký `AuditorAware<String>`.
3. Đánh dấu bốn field auditing bằng annotation tương ứng.
4. Lưu customer mới.
5. Kiểm tra metadata tạo và sửa được điền.

### Bài 2: Quan sát lần sửa gần nhất

1. Tạo customer bằng actor `user-101`.
2. Sửa tên bằng actor `user-205`.
3. Sửa trạng thái bằng actor `user-310`.
4. Đọc lại customer.
5. Xác nhận `createdBy` vẫn là `user-101`, `lastModifiedBy` là `user-310`.
6. Giải thích vì sao không thể biết `user-205` đã sửa field nào chỉ từ các cột auditing.

### Bài 3: Tạo audit event table

1. Tạo bảng `customer_audit_events`.
2. Tạo aggregate audit event có actor, action, timestamp, version và changes payload.
3. Tạo repository chỉ cung cấp insert/read cần thiết.
4. Cập nhật customer và thêm event trong cùng `@Transactional`.
5. Truy vấn lịch sử theo aggregate ID.

### Bài 4: Kiểm tra rollback

1. Tạo một thao tác cập nhật customer.
2. Làm cho insert audit event thất bại bằng một constraint có thể tái lập.
3. Xác nhận thay đổi customer cũng rollback.
4. Thử bỏ transaction chung và quan sát nguy cơ dữ liệu nghiệp vụ thay đổi nhưng audit event không tồn tại.

### Bài 5: Ghi nhận delete

1. Tạo delete event trước khi xóa aggregate.
2. Xóa customer trong cùng transaction.
3. Xác nhận hàng customer biến mất nhưng audit event vẫn tồn tại.
4. Thử thiết kế soft delete và so sánh với delete event.

### Bài 6: So sánh các phương án

1. Tạo một database trigger ghi old/new values khi update.
2. So sánh trigger với audit event do service ghi.
3. Xác định actor nào trigger có thể biết và actor nào cần truyền qua session context.
4. Đánh giá CDC nếu có nhiều writer.
5. Xác định trường hợp event sourcing có phù hợp với domain hay không.

## 18. Ghi nhớ

- Auditing mặc định của Spring Data JDBC ghi metadata tạo và sửa trên trạng thái entity hiện tại.
- `@CreatedBy` và `@CreatedDate` ghi nhận người/thời điểm tạo.
- `@LastModifiedBy` và `@LastModifiedDate` chỉ ghi nhận người/thời điểm sửa gần nhất.
- `@EnableJdbcAuditing` kích hoạt auditing; `AuditorAware<T>` cung cấp principal khi cần ghi actor.
- `DateTimeProvider` cho phép kiểm soát nguồn thời gian; nên thống nhất cách lưu thời gian, thường dùng UTC.
- `@Version` phục vụ optimistic locking, không phải bảng lịch sử.
- Auditing mặc định không tạo diff, không lưu old/new values, không ghi lý do và không tự giữ lịch sử xóa.
- Full history cần append-only audit table, version table, database trigger, CDC hoặc event sourcing tùy yêu cầu.
- Nếu audit row bắt buộc đi cùng thay đổi aggregate, ghi cả hai trong cùng transaction và cùng DataSource/transaction manager.
- Audit event và outbox phục vụ hai mục tiêu khác nhau; có thể dùng chung transaction nhưng không thay thế nhau.
- Thiết kế payload cần cân bằng khả năng truy vết, dung lượng, schema evolution, quyền truy cập và bảo vệ dữ liệu nhạy cảm.
- Nếu có nhiều writer, hãy bảo đảm mọi đường ghi được theo dõi hoặc dùng cơ chế ở database level.

**Auditing mặc định trả lời “ai tạo và ai sửa lần gần nhất, vào lúc nào”; lịch sử thay đổi đầy đủ trả lời “đã thay đổi những gì qua từng lần, bởi ai và vì sao”.** Hãy chọn cơ chế theo câu hỏi nghiệp vụ cần trả lời. Khi cần cả metadata hiện tại lẫn lịch sử kiểm toán, kết hợp auditing annotations với một audit event store append-only.

## Tài liệu tham khảo

- [Spring Data Relational 4.1.2 — Auditing](https://www.springframework.org/spring-data/relational/reference/jdbc/auditing.html)
- [Spring Data Relational 4.1.2 — EnableJdbcAuditing API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/config/EnableJdbcAuditing.html)
- [Spring Data Commons 4.1.2 — Auditing Infrastructure](https://docs.spring.io/spring-data/commons/reference/auditing.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)

