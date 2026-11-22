# Mục đích và ranh giới của thông tin tạo/sửa dữ liệu

Thông tin tạo và sửa dữ liệu (auditing metadata) cho biết **ai tạo một bản ghi, thời điểm bản ghi được tạo, ai sửa gần nhất và thời điểm sửa gần nhất**. Trong Spring Data JDBC, các annotation auditing giúp ứng dụng ghi những thông tin này theo vòng đời lưu entity mà không phải tự gán thủ công ở mọi service.

Bốn thuộc tính thường dùng là `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy` và `@LastModifiedDate`. Chúng tạo ra dấu mốc cơ bản về nguồn gốc và lần cập nhật gần nhất của dữ liệu.

Cần xác định rõ phạm vi của metadata. Nó không tự lưu toàn bộ lịch sử thay đổi, không quyết định người dùng có quyền sửa dữ liệu hay không, và không thay thế optimistic locking. Những trách nhiệm đó cần cơ chế riêng.

Bài học này giải thích mục đích của từng trường, cách bật auditing trong Spring Data JDBC, cách lấy actor và thời gian, nơi nên đặt metadata trong aggregate, và các giới hạn khi dữ liệu được thay đổi bằng SQL trực tiếp.

## 1. Vì sao cần metadata tạo/sửa?

Giả sử bảng đơn hàng có các cột nghiệp vụ:

~~~text
sales_orders
+----+------------+----------+
| id | order_code | status   |
+----+------------+----------+
| 41 | SO-0041    | DRAFT    |
+----+------------+----------+
~~~

Khi điều tra dữ liệu, chỉ các cột nghiệp vụ có thể chưa trả lời được:

- Bản ghi này được tạo bởi người dùng hay tiến trình nào?
- Bản ghi được tạo lúc nào?
- Ai là người sửa gần nhất?
- Lần cập nhật gần nhất diễn ra khi nào?

Có thể bổ sung metadata:

~~~text
sales_orders
+----+------------+----------+------------+---------------------+---------------+---------------------+
| id | order_code | status   | created_by | created_at          | modified_by   | modified_at         |
+----+------------+----------+------------+---------------------+---------------+---------------------+
| 41 | SO-0041    | DRAFT    | user-102   | 2026-10-03 08:15:00 | user-205      | 2026-10-04 10:42:18 |
+----+------------+----------+------------+---------------------+---------------+---------------------+
~~~

Các trường này hữu ích cho:

- Hiển thị thông tin tạo và cập nhật gần nhất trong màn hình quản trị.
- Hỗ trợ điều tra lỗi và truy vết nguồn dữ liệu.
- Xác định bản ghi đã cũ bao lâu.
- Hỗ trợ quy trình vận hành, kiểm tra dữ liệu và báo cáo.
- Cung cấp ngữ cảnh cơ bản khi hỗ trợ người dùng.

Metadata tạo/sửa đặc biệt hữu ích với dữ liệu tồn tại lâu dài và được nhiều người hoặc tiến trình cập nhật.

## 2. Bốn trường auditing cơ bản

Spring Data cung cấp bốn annotation chính cho metadata tạo và sửa.

| Annotation | Ý nghĩa | Thời điểm điển hình |
|---|---|---|
| `@CreatedBy` | Actor tạo bản ghi | Khi entity được nhận diện là mới |
| `@CreatedDate` | Thời điểm tạo bản ghi | Khi entity được nhận diện là mới |
| `@LastModifiedBy` | Actor sửa gần nhất | Khi tạo và khi sửa, tùy cấu hình |
| `@LastModifiedDate` | Thời điểm sửa gần nhất | Khi tạo và khi sửa, tùy cấu hình |

Ví dụ:

~~~java
@Table("sales_orders")
public class SalesOrder {

    @Id
    private Long id;

    private String orderCode;
    private String status;

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @LastModifiedBy
    @Column("modified_by")
    private String modifiedBy;

    @LastModifiedDate
    @Column("modified_at")
    private Instant modifiedAt;
}
~~~

Các annotation này mô tả vai trò của thuộc tính. Spring Data JDBC sử dụng auditing callback trong quá trình persistence để điền giá trị phù hợp trước khi ghi dữ liệu.

Tên cột trong ví dụ được khai báo rõ bằng `@Column` để schema và entity dễ đối chiếu. Có thể dùng naming convention của dự án nếu nó đã được cấu hình nhất quán.

### 2.1. Created và LastModified khác nhau thế nào?

`createdBy` và `createdAt` mô tả nguồn gốc ban đầu của bản ghi. Sau khi bản ghi đã được tạo, các giá trị này thường được giữ nguyên qua các lần cập nhật.

`modifiedBy` và `modifiedAt` mô tả lần cập nhật gần nhất. Chúng được thiết lập khi tạo mới nếu cấu hình cho phép cập nhật metadata sửa ngay lúc tạo, và được làm mới ở những lần sửa tiếp theo.

Ví dụ:

~~~text
Lần 1: user-102 tạo đơn
    created_by  = user-102
    created_at  = 08:15
    modified_by = user-102
    modified_at = 08:15

Lần 2: user-205 sửa trạng thái
    created_by  = user-102
    created_at  = 08:15
    modified_by = user-205
    modified_at = 10:42

Lần 3: job-archive cập nhật nhãn lưu trữ
    created_by  = user-102
    created_at  = 08:15
    modified_by = job-archive
    modified_at = 23:00
~~~

Ở lần thứ ba, người sửa gần nhất là tiến trình nền chứ không phải người dùng cuối. Đây là lý do ứng dụng cần một quy ước actor thống nhất cho cả request người dùng và background job.

## 3. Bật auditing cho Spring Data JDBC

Để Spring Data JDBC tự điền metadata, cần bật auditing trong cấu hình.

~~~java
@Configuration
@EnableJdbcAuditing
public class JdbcAuditingConfiguration {
}
~~~

Sau khi bật, Spring Data đăng ký thành phần auditing cho vòng đời entity. Khi entity được lưu qua cơ chế repository của Spring Data JDBC, callback có thể cập nhật các thuộc tính được đánh dấu.

Nếu ứng dụng cần ghi actor hiện tại, khai báo một bean `AuditorAware<T>`. Kiểu generic của bean cần tương thích với kiểu thuộc tính được đánh dấu `@CreatedBy` và `@LastModifiedBy`.

Ví dụ đơn giản dùng tên principal:

~~~java
@Configuration
@EnableJdbcAuditing(auditorAwareRef = "auditorAware")
public class JdbcAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.of("system");
    }
}
~~~

Ví dụ trên luôn trả về actor `system`, phù hợp để minh họa cấu hình nhưng không phù hợp cho mọi ứng dụng có người dùng đăng nhập. Trong ứng dụng thực tế, `AuditorAware` nên lấy danh tính từ security context hoặc từ ngữ cảnh thực thi đã được xác thực.

Nếu không cấu hình `AuditorAware`, auditing vẫn có thể điền các trường ngày giờ khi được bật, nhưng không có nguồn cung cấp actor để điền các trường `@CreatedBy` và `@LastModifiedBy`.

### 3.1. Lấy actor từ Spring Security

Ví dụ dưới đây lấy tên principal từ Spring Security và bỏ qua anonymous authentication:

~~~java
@Configuration
@EnableJdbcAuditing(auditorAwareRef = "auditorAware")
public class JdbcAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.ofNullable(
                    SecurityContextHolder.getContext().getAuthentication()
                )
                .filter(Authentication::isAuthenticated)
                .filter(authentication ->
                        !(authentication instanceof AnonymousAuthenticationToken)
                )
                .map(Authentication::getName);
    }
}
~~~

Các import tương ứng đến từ Spring Security và Spring Data:

~~~java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
~~~

Trong hệ thống thực tế, nên lưu một định danh actor ổn định như user ID thay vì tên hiển thị có thể thay đổi. Có thể thay kiểu generic `String` bằng `UUID` hoặc kiểu định danh phù hợp với mô hình người dùng của ứng dụng.

### 3.2. Actor có thể vắng mặt

`AuditorAware` trả về `Optional.empty()` khi không xác định được actor. Ứng dụng cần quyết định điều gì xảy ra trong trường hợp này:

- Cho phép trường actor là NULL.
- Dùng một actor hệ thống được quy ước rõ ràng cho job hoặc migration.
- Từ chối thao tác nếu nghiệp vụ yêu cầu mọi thay đổi phải có danh tính.

Không nên tự động gán mọi thao tác không có security context thành một người dùng giả. Điều đó làm giảm giá trị truy vết vì không thể phân biệt người dùng, job, migration và thao tác vận hành.

## 4. Tách actor khỏi quyền truy cập

Auditing ghi lại danh tính được dùng để thực hiện thao tác. Nó không quyết định danh tính đó có quyền thực hiện thao tác hay không.

Ví dụ:

~~~text
Authentication
      |
      v
Xác định principal hiện tại
      |
      +-----------------------+
      |                       |
      v                       v
Authorization             AuditorAware
Có được sửa đơn?          Ai đang thực hiện?
      |                       |
      v                       v
Cho phép / từ chối        Ghi modified_by
~~~

Hai trách nhiệm có liên quan nhưng khác nhau:

- **Authentication:** xác định principal là ai.
- **Authorization:** kiểm tra principal có quyền làm hành động cụ thể hay không.
- **Auditing:** ghi nhận actor nào đã tạo hoặc sửa bản ghi.

Không dùng giá trị `createdBy` để thay thế kiểm tra quyền. Bản ghi do một người tạo không có nghĩa chỉ người đó được sửa. Quyền có thể phụ thuộc vai trò, tenant, trạng thái nghiệp vụ hoặc chính sách khác.

Tương tự, không cho client gửi tùy ý `createdBy` hoặc `modifiedBy` trong request rồi tin trực tiếp giá trị đó. Actor nên được lấy từ security context hoặc một ngữ cảnh thực thi đáng tin cậy ở server.

## 5. Metadata thời gian và DateTimeProvider

Spring Data auditing có thể lấy thời gian hiện tại qua cơ chế cung cấp thời gian mặc định. Khi cần kiểm soát nguồn thời gian, có thể khai báo `DateTimeProvider`.

Ví dụ dùng `Clock` để thống nhất thời gian UTC:

~~~java
@Configuration
@EnableJdbcAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "dateTimeProvider"
)
public class JdbcAuditingConfiguration {

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider dateTimeProvider(Clock auditingClock) {
        return () -> Optional.of(auditingClock.instant());
    }

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.of("system");
    }
}
~~~

Sử dụng `Clock` có lợi cho kiểm thử vì có thể thay bằng clock cố định. Khi đó test không cần phụ thuộc vào thời điểm thực của máy.

### 5.1. Chọn kiểu thời gian

Một số lựa chọn thường gặp:

| Kiểu Java | Ý nghĩa |
|---|---|
| `Instant` | Một thời điểm tuyệt đối trên timeline |
| `OffsetDateTime` | Thời điểm kèm UTC offset |
| `LocalDateTime` | Ngày giờ địa phương, không mang timezone/offset |
| `LocalDate` | Chỉ ngày, không có giờ |

Đối với thời điểm auditing trong hệ thống phân tán, `Instant` thường là lựa chọn dễ trao đổi nhất vì biểu diễn một thời điểm UTC. Giao diện có thể chuyển sang timezone của người xem khi hiển thị.

Nếu dùng `LocalDateTime`, phải thống nhất timezone ngầm của dữ liệu. Hai server chạy ở timezone khác nhau có thể tạo ra timestamp khó so sánh nếu không có quy ước rõ.

### 5.2. Chọn một nguồn thời gian có thẩm quyền

Có hai cách phổ biến để gán thời gian:

- Ứng dụng dùng `DateTimeProvider` và ghi giá trị vào cột.
- Database dùng default hoặc trigger để gán thời gian.

Không nên để cả ứng dụng và trigger cùng cập nhật một trường mà không xác định rõ nguồn nào có quyền quyết định. Nếu hai nơi ghi đè lẫn nhau, giá trị quan sát được có thể khác với thời gian mà ứng dụng nghĩ đã ghi.

Đối với auditing do Spring Data JDBC quản lý, hãy để callback ứng dụng là nguồn ghi chính và cấu hình schema tương ứng. Nếu tổ chức yêu cầu database là nguồn thời gian tuyệt đối, hãy thiết kế trigger/default có chủ đích và kiểm tra cách nó tương tác với entity mapping.

## 6. Đặt auditing metadata ở đâu trong aggregate?

Trong Spring Data JDBC, aggregate root là ranh giới nhất quán của một aggregate. Nếu mục đích là ghi nhận ai tạo và ai sửa **đơn hàng**, metadata thường được đặt trên aggregate root.

Ví dụ:

~~~text
SalesOrder
    id
    status
    created_by
    created_at
    modified_by
    modified_at
    |
    +-- OrderLine
    +-- OrderLine
~~~

Cách đặt này cho biết lần gần nhất aggregate được cập nhật qua đường persistence có auditing.

Nếu từng child có vòng đời độc lập và cần theo dõi riêng, có thể đặt metadata trên entity con tương ứng. Nhưng cần hiểu chính xác cách Spring Data JDBC lưu collection entity.

### 6.1. Metadata root và metadata child trả lời câu hỏi khác nhau

| Vị trí | Câu hỏi được trả lời |
|---|---|
| Aggregate root | Ai tạo/sửa aggregate gần nhất? |
| Entity con | Ai tạo/sửa hàng con này gần nhất theo lifecycle persistence của nó? |
| Audit table riêng | Những hành động nào đã xảy ra và theo thứ tự nào? |

Không nên đặt cùng một trường ở mọi entity chỉ vì có thể làm vậy. Mỗi trường cần có ý nghĩa rõ ràng và được cập nhật theo đúng vòng đời của dữ liệu đó.

### 6.2. Lưu ý khi Spring Data JDBC ghi lại collection

Spring Data JDBC không hoạt động giống ORM có dirty tracking cho từng child. Khi lưu aggregate, các referenced entities trong collection có thể được ghi lại theo chiến lược persistence của aggregate, bao gồm việc xóa và chèn lại các hàng con.

Vì vậy, không nên mặc định rằng `created_at` trên child luôn có nghĩa “thời điểm nghiệp vụ đầu tiên tạo ra child” nếu child row có thể bị thay thế trong một lần save aggregate. Metadata có thể phản ánh lần insert row gần nhất theo cơ chế persistence.

Nếu cần giữ nguyên thời điểm tạo ban đầu của child qua mọi lần lưu root, hãy thiết kế và kiểm tra cách lưu child phù hợp, hoặc lưu lịch sử nghiệp vụ trong bảng riêng. Không dùng auditing metadata của persistence như một lịch sử bất biến nếu mô hình lưu trữ có thể tái tạo hàng con.

## 7. Metadata tạo/sửa không phải lịch sử kiểm toán đầy đủ

Bốn trường auditing chỉ lưu thông tin tạo ban đầu và thông tin sửa gần nhất. Chúng không cho biết mọi lần sửa đã xảy ra.

Ví dụ sau ba lần cập nhật, một bản ghi có thể chỉ giữ:

~~~text
created_by  = user-102
created_at  = 2026-10-03T08:15:00Z
modified_by = user-205
modified_at = 2026-10-04T10:42:18Z
~~~

Thông tin này không cho biết:

- Trước đó ai đã sửa?
- Trạng thái cũ là gì?
- Giá trị nào đã thay đổi?
- Thay đổi nào xảy ra trước hay sau?
- Vì sao người dùng thực hiện thay đổi?

Nếu cần các câu trả lời này, cần một audit trail riêng.

### 7.1. Audit metadata và audit history

| Đặc điểm | Auditing metadata | Audit history |
|---|---|---|
| Số lần ghi | Một lần tạo và lần sửa gần nhất | Nhiều bản ghi theo từng sự kiện |
| Lưu actor | Actor tạo và actor sửa gần nhất | Actor cho từng hành động |
| Lưu thời gian | Thời điểm tạo và sửa gần nhất | Thời điểm từng hành động |
| Giá trị cũ/mới | Không | Có thể lưu |
| Mục đích | Metadata vận hành của bản ghi | Truy vết lịch sử và điều tra |
| Chi phí lưu trữ | Thấp | Cao hơn, tăng theo số sự kiện |

Ví dụ audit history:

~~~sql
CREATE TABLE sales_order_audit (
    audit_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    actor_id VARCHAR(100) NOT NULL,
    action VARCHAR(40) NOT NULL,
    old_status VARCHAR(20),
    new_status VARCHAR(20),
    occurred_at TIMESTAMP NOT NULL,
    correlation_id VARCHAR(100)
);
~~~

Mỗi hành động quan trọng có thể ghi thêm một hàng audit. Thiết kế thực tế cần xác định dữ liệu nào được phép lưu, thời hạn lưu, ai được xem và cách bảo vệ dữ liệu nhạy cảm.

### 7.2. Audit history có thể dùng outbox hoặc event log

Nếu thay đổi cần phát sự kiện cho hệ thống khác, có thể ghi outbox record trong cùng transaction với thay đổi aggregate. Worker gửi event sau khi transaction commit.

Không gửi message trước khi database commit rồi giả định hai thao tác luôn thành công cùng nhau. Database transaction thông thường không tự bao trùm broker bên ngoài.

Audit history cũng không nhất thiết phải chứa toàn bộ object trước và sau. Hãy lưu các trường cần thiết cho mục đích điều tra, tuân thủ hoặc vận hành và tránh sao chép dữ liệu nhạy cảm không cần thiết.

## 8. Auditing không thay thế optimistic locking

`modifiedAt` có thể thay đổi sau mỗi lần save, nhưng không nên dùng nó làm cơ chế phát hiện lost update.

Hai request có thể cùng đọc một giá trị timestamp. Độ chính xác timestamp còn phụ thuộc kiểu cột, database và driver. So sánh timestamp không có semantics rõ bằng version số.

Spring Data JDBC hỗ trợ optimistic locking bằng `@Version`:

~~~java
@Table("sales_orders")
public class SalesOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    @LastModifiedDate
    private Instant modifiedAt;
}
~~~

Hai trường phục vụ hai mục đích:

| Trường | Câu hỏi |
|---|---|
| `modifiedAt` | Lần cập nhật gần nhất diễn ra khi nào? |
| `modifiedBy` | Ai thực hiện lần cập nhật gần nhất? |
| `version` | Aggregate đã thay đổi bao nhiêu phiên bản theo cơ chế optimistic locking? |

Nếu hai người dùng cùng sửa aggregate, `@Version` giúp phát hiện một lần save dựa trên version cũ. `@LastModifiedDate` chỉ ghi thời gian cập nhật gần nhất và không tự từ chối lần save xung đột.

## 9. Auditing callback và các đường ghi trực tiếp

Spring Data JDBC auditing gắn với lifecycle persistence của Spring Data. Khi lưu entity qua repository, auditing callback có thể điền metadata trước khi dữ liệu được ghi.

Nhưng một câu SQL trực tiếp như:

~~~java
jdbcClient.sql("""
        UPDATE sales_orders
        SET status = :status
        WHERE id = :id
        """)
    .param("status", status)
    .param("id", orderId)
    .update();
~~~

không đi qua entity callback của Spring Data JDBC. Do đó, không nên kỳ vọng `modifiedBy` và `modifiedAt` tự được cập nhật.

Nếu một đường SQL trực tiếp là chủ ý, cần chọn một trong các cách sau:

1. Cập nhật metadata ngay trong câu SQL.
2. Dùng database trigger làm nguồn ghi metadata theo quy ước thống nhất.
3. Chuyển thao tác về repository/domain flow nếu cần đầy đủ lifecycle behavior.

Ví dụ cập nhật metadata bằng SQL:

~~~java
jdbcClient.sql("""
        UPDATE sales_orders
        SET status = :status,
            modified_by = :actor,
            modified_at = :modifiedAt,
            version = version + 1
        WHERE id = :id
          AND version = :expectedVersion
        """)
    .param("status", status)
    .param("actor", actorId)
    .param("modifiedAt", clock.instant())
    .param("id", orderId)
    .param("expectedVersion", expectedVersion)
    .update();
~~~

Ví dụ này cũng kiểm tra version để bảo vệ direct write. Trong ứng dụng thực tế, phải kiểm tra số hàng bị ảnh hưởng và thực hiện các bước liên quan trong transaction phù hợp.

### 9.1. Đừng để mỗi đường ghi có một quy tắc actor khác nhau

Nếu repository ghi `modifiedBy` bằng user ID nhưng batch job trực tiếp SQL lại ghi tên máy, metadata sẽ không nhất quán.

Hãy chuẩn hóa:

- Định dạng actor ID.
- Cách biểu diễn người dùng hệ thống.
- Nguồn thời gian.
- Quy tắc cập nhật modified fields.
- Cách cập nhật version khi thay đổi aggregate.
- Audit/outbox cần ghi cho từng loại command.

Có thể dùng cùng một actor abstraction ở application layer để cả repository flow và SQL adapter nhận cùng một danh tính đã xác thực.

## 10. Background job, scheduler và service account

Auditing không chỉ phục vụ HTTP request. Dữ liệu có thể được tạo hoặc sửa bởi:

- Scheduled job.
- Batch import.
- Message consumer.
- Data migration.
- Quy trình đồng bộ.
- Tài khoản vận hành hoặc service account.

Các luồng này thường không có SecurityContext của người dùng cuối. Nếu `AuditorAware` chỉ đọc SecurityContext, nó có thể trả `Optional.empty()`.

Cần xác định actor cho từng loại tiến trình. Ví dụ:

| Luồng thực thi | Actor có thể dùng |
|---|---|
| Người dùng đăng nhập | User ID ổn định |
| Scheduled archive job | `system:archive-job` |
| Import từ đối tác | `integration:partner-a` |
| Data migration | `migration:release-2026-11` |
| Message consumer | Service identity hoặc producer identity theo chính sách |
| Thao tác quản trị | Admin user ID |

Nếu cần biết cả người khởi tạo và service thực thi, hai thông tin này có thể được lưu riêng trong audit event. Trường `modifiedBy` thường chỉ nên chứa một actor theo quy ước đã chọn, không nhồi nhiều nguồn danh tính vào cùng một chuỗi.

Với async execution, không giả định security context tự động có mặt trên mọi thread. Hãy truyền actor context một cách tường minh hoặc dùng cơ chế context propagation đã cấu hình.

## 11. Thiết kế schema cho auditing metadata

Một bảng đơn hàng có thể khai báo:

~~~sql
CREATE TABLE sales_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_code VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL,

    created_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE,
    modified_by VARCHAR(100),
    modified_at TIMESTAMP WITH TIME ZONE,

    version BIGINT NOT NULL
);
~~~

Các điểm cần quyết định:

- Actor column dùng user ID, UUID hay service identity.
- Timestamp lưu UTC hay quy ước timezone khác.
- Có cho phép NULL khi actor không xác định không.
- Có index trên `created_at` hoặc `modified_at` phục vụ truy vấn vận hành không.
- Có lưu version riêng cho optimistic locking không.
- Có bảng audit history riêng không.

Không phải mọi bảng đều cần đủ bốn trường. Bảng lookup bất biến hoặc bảng kỹ thuật có thể không cần metadata sửa. Hãy dựa trên nhu cầu truy vết và vòng đời dữ liệu.

### 11.1. Có nên dùng foreign key từ created_by đến bảng user?

Có thể tạo FK nếu user record luôn tồn tại và vòng đời của user được quản lý phù hợp. Nhưng nếu user có thể bị xóa hoặc chuyển sang hệ thống danh tính khác, FK cứng có thể làm khó việc lưu lịch sử.

Một lựa chọn là lưu stable actor ID như một giá trị tham chiếu, đồng thời giữ audit identity trong hệ thống quản lý danh tính. Hãy cân nhắc khả năng tra cứu actor sau khi tài khoản bị vô hiệu hóa hoặc xóa.

### 11.2. Index cho timestamp

Index trên `modified_at` có thể hữu ích cho job tìm bản ghi lâu chưa cập nhật hoặc dashboard vận hành. Tuy nhiên, trường này thay đổi thường xuyên nên index cũng làm tăng chi phí ghi.

Chỉ tạo index khi có truy vấn thực tế cần nó. Đừng tạo index cho mọi metadata column theo mặc định.

## 12. Kiểm thử auditing

Kiểm thử cần xác nhận metadata được ghi đúng qua đường repository, actor và clock có thể điều khiển được.

Một cấu hình test có thể dùng `AuditorAware` cố định và `DateTimeProvider` trả về thời điểm đã biết. Khi đó, test không phụ thuộc vào đồng hồ hệ thống.

Các kịch bản quan trọng:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Tạo entity mới | createdBy và createdDate được điền nếu có provider |
| Tạo entity mới với modify-on-create bật | lastModifiedBy/Date được điền theo cấu hình |
| Sửa entity đã tồn tại | created metadata giữ nguyên; modified metadata được cập nhật |
| Không có actor | Auditor fields theo chính sách Optional/NULL/system actor |
| Chạy scheduled job | modifiedBy phản ánh service actor đã quy định |
| Ghi qua repository | Auditing callback được thực thi |
| Ghi bằng JdbcClient trực tiếp | Metadata không tự đổi nếu SQL/trigger không cập nhật |
| Thay clock trong test | Timestamp có giá trị xác định |
| Entity con được lưu lại cùng aggregate | Xác nhận semantics metadata theo cách Spring Data JDBC ghi collection |

Ví dụ kiểm thử ý tưởng:

~~~java
@DataJdbcTest
@Import(TestJdbcAuditingConfiguration.class)
class SalesOrderAuditingTest {

    @Autowired
    SalesOrderRepository repository;

    @Test
    void storesCreationAndModificationMetadata() {
        SalesOrder order = SalesOrder.draft();

        SalesOrder created = repository.save(order);

        assertThat(created.getCreatedBy()).isEqualTo("user-42");
        assertThat(created.getCreatedAt())
                .isEqualTo(Instant.parse("2026-11-13T08:00:00Z"));

        // Thay đổi entity và lưu lại trong một bước riêng.
        SalesOrder loaded = repository.findById(created.getId())
                .orElseThrow();

        loaded.changeStatus("CONFIRMED");

        SalesOrder updated = repository.save(loaded);

        assertThat(updated.getCreatedBy()).isEqualTo("user-42");
        assertThat(updated.getModifiedBy()).isEqualTo("user-42");
    }
}
~~~

Đây là ví dụ minh họa; entity cần cung cấp factory, getter và domain method tương ứng. Test thực tế nên xác nhận `modifiedAt` đổi theo clock mới và `createdAt` không bị thay đổi sau lần cập nhật.

### 12.1. Test direct SQL riêng

Một integration test khác nên chạy UPDATE qua JdbcClient và xác nhận metadata không đổi nếu câu SQL không cập nhật metadata và database không có trigger.

Test này giúp đội ngũ nhìn thấy rõ ranh giới giữa repository lifecycle và SQL trực tiếp.

## 13. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Xem `createdBy` là quyền sở hữu | Người tạo bị hiểu nhầm là người duy nhất có quyền sửa | Dùng authorization riêng |
| Dùng `modifiedAt` thay `@Version` | Không phát hiện lost update đáng tin cậy | Dùng version số cho optimistic locking |
| Mong JdbcClient tự gọi auditing callback | Metadata không được cập nhật | Ghi metadata trong SQL hoặc dùng repository |
| Không cấu hình actor cho job | createdBy/modifiedBy có thể NULL hoặc thiếu | Quy định service actor |
| Dùng tên hiển thị làm actor ID | Đổi tên làm khó truy vết | Lưu stable user/service identifier |
| Ghi metadata tạo lại mỗi lần save | Mất thông tin thời điểm tạo ban đầu | Phân biệt created và modified fields |
| Xem bốn trường là lịch sử đầy đủ | Không biết các thay đổi trung gian | Dùng audit history/event log riêng |
| Gán metadata từ request body | Client có thể giả mạo actor | Lấy actor từ server security context |
| Để ứng dụng và trigger cùng ghi timestamp | Nguồn thời gian không nhất quán | Chọn một nguồn có thẩm quyền |
| Đặt auditing trên mọi child mà không hiểu persistence | Metadata có thể phản ánh lần ghi lại row | Xác định đúng aggregate/entity lifecycle |

## 14. Quy trình đưa auditing vào một aggregate

Khi thêm metadata tạo/sửa cho một entity:

**Bước 1 — Xác định mục đích.** Cần biết actor/thời gian tạo và sửa gần nhất hay cần lịch sử đầy đủ?

**Bước 2 — Chọn vị trí.** Metadata thuộc aggregate root, child entity hay bảng audit riêng?

**Bước 3 — Chọn kiểu dữ liệu.** Dùng actor ID ổn định và kiểu thời gian có timezone semantics rõ.

**Bước 4 — Bật auditing.** Cấu hình `@EnableJdbcAuditing`.

**Bước 5 — Cung cấp actor.** Cài `AuditorAware` lấy principal đã xác thực hoặc service identity.

**Bước 6 — Cung cấp thời gian nếu cần.** Dùng `DateTimeProvider` để kiểm soát clock và kiểm thử.

**Bước 7 — Ánh xạ schema.** Tạo cột tương ứng và quyết định nullability, index, retention.

**Bước 8 — Kiểm tra các đường ghi.** Repository lifecycle có auditing; direct SQL cần tự cập nhật metadata hoặc dùng trigger theo quy ước.

**Bước 9 — Tách các trách nhiệm khác.** Authorization, optimistic locking, audit history và domain events cần cơ chế riêng.

**Bước 10 — Kiểm thử actor và thời gian.** Bao gồm request người dùng, job nền, async flow và direct SQL.

~~~text
Entity được tạo hoặc sửa
          |
          v
Đường ghi nào?
     /         \
 Repository    SQL trực tiếp
     |              |
     v              v
Auditing callback  SQL/trigger tự ghi
     |              |
     +-------+------+
             |
             v
created/modified metadata
             |
             +---- Không thay thế authorization
             |
             +---- Không thay thế @Version
             |
             +---- Không thay thế audit history
~~~

## 15. Bài tập tự suy luận

**Tình huống A — Người tạo và người sửa**

User A tạo đơn, user B sửa đơn. `createdBy` và `modifiedBy` nên có giá trị gì?

**Gợi ý:** `createdBy` giữ A; `modifiedBy` phản ánh B sau lần cập nhật gần nhất.

**Tình huống B — Scheduled job**

Một job cập nhật trạng thái archive nhưng không có người dùng đăng nhập. `AuditorAware` chỉ đọc SecurityContext sẽ trả gì?

**Gợi ý:** Có thể trả `Optional.empty()`. Hãy quy định actor hệ thống riêng cho job.

**Tình huống C — Direct SQL**

Một câu UPDATE qua JdbcClient đổi status. `@LastModifiedDate` có tự chạy không?

**Gợi ý:** Không. SQL trực tiếp không đi qua auditing callback của Spring Data JDBC; phải cập nhật metadata trong SQL hoặc dùng trigger.

**Tình huống D — Hai người cùng sửa**

Hai người cùng đọc một đơn. `modifiedAt` có đủ để ngăn lần lưu cũ không?

**Gợi ý:** Không. Dùng `@Version` để phát hiện optimistic locking conflict.

**Tình huống E — Cần biết tất cả lần sửa**

Bảng chỉ có createdBy, createdAt, modifiedBy và modifiedAt. Có thể xem ai đã sửa ở lần thứ hai không?

**Gợi ý:** Không. Bốn trường chỉ giữ lần tạo và lần sửa gần nhất; cần audit history hoặc event log.

**Tình huống F — Metadata trên child**

Một child được ghi lại khi aggregate root được save. `createdAt` trên child có chắc phản ánh lần đầu child được tạo về mặt nghiệp vụ không?

**Gợi ý:** Không nên mặc định như vậy. Kiểm tra chiến lược lưu collection của Spring Data JDBC; nếu cần lịch sử ổn định, dùng thiết kế lưu trữ phù hợp.

## 16. Ghi nhớ

| Thành phần | Trách nhiệm |
|---|---|
| `@CreatedBy` | Actor tạo entity |
| `@CreatedDate` | Thời điểm tạo entity |
| `@LastModifiedBy` | Actor sửa gần nhất |
| `@LastModifiedDate` | Thời điểm sửa gần nhất |
| `@EnableJdbcAuditing` | Bật auditing cho Spring Data JDBC |
| `AuditorAware<T>` | Cung cấp actor hiện tại |
| `DateTimeProvider` | Cung cấp thời gian cho auditing |
| Aggregate root | Thường là nơi đặt metadata của aggregate |
| Direct SQL | Phải tự ghi metadata hoặc dùng trigger |
| `@Version` | Phát hiện optimistic locking conflict |
| Authorization | Quyết định ai được phép thực hiện hành động |
| Audit history | Lưu nhiều sự kiện và thay đổi theo thời gian |

**Auditing metadata ghi nhận nguồn gốc và lần cập nhật gần nhất của dữ liệu.** Trong Spring Data JDBC, `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy` và `@LastModifiedDate` được điền qua auditing lifecycle khi lưu entity bằng repository. Hãy cung cấp actor và thời gian có quy ước rõ, đặt metadata ở đúng ranh giới aggregate, và nhớ rằng direct SQL cần xử lý riêng. Nếu cần phân quyền, chống lost update hoặc lịch sử đầy đủ, hãy dùng authorization, `@Version` và audit history tương ứng.

## Tài liệu tham khảo

- [Spring Data Relational — Auditing](https://docs.spring.io/spring-data/relational/reference/jdbc/auditing.html): bật JDBC auditing, auditor provider và các annotation tạo/sửa.
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html): `AuditorAware`, `DateTimeProvider` và metadata auditing.
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): aggregate persistence, lifecycle callbacks và optimistic locking.
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): principal và security context.

