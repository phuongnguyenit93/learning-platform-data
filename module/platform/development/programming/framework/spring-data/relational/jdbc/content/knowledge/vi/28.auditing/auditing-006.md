# Auditing với entity bất biến, đối tượng mới và nhiều nguồn ghi

Trong **Spring Data Relational JDBC**, auditing giúp lưu lại ai tạo một aggregate, thời điểm tạo và lần sửa gần nhất. Các trường thường dùng là `createdBy`, `createdDate`, `lastModifiedBy` và `lastModifiedDate`. Spring Data JDBC có thể tự điền những trường này khi aggregate được lưu thông qua repository hoặc các API persistence của Spring Data.

Auditing có một số điểm cần chú ý khi domain model bất biến, khi ứng dụng tự cấp ID cho object mới và khi dữ liệu có thể được ghi từ nhiều đường khác nhau. Spring phải nhận diện đúng object mới để chọn thao tác insert và gán metadata tạo mới; với immutable entity, các giá trị audit phải được đưa vào instance mới; còn những câu SQL chạy ngoài lifecycle của Spring Data JDBC sẽ không tự kích hoạt auditing callback.

Bài học này trình bày cách bật auditing, cung cấp auditor và clock, xử lý immutable object bằng wither, nhận diện object mới bằng ID, `@Version` hoặc `Persistable`, và thiết kế auditing khi repository, `JdbcAggregateTemplate`, SQL trực tiếp hoặc hệ thống bên ngoài cùng ghi dữ liệu.

## 1. Các trường auditing trong Spring Data JDBC

Spring Data cung cấp bốn annotation phổ biến:

| Annotation | Ý nghĩa | Thời điểm cập nhật |
|---|---|---|
| `@CreatedBy` | Người hoặc tác nhân tạo aggregate | Khi aggregate được nhận diện là mới |
| `@CreatedDate` | Thời điểm tạo aggregate | Khi aggregate được nhận diện là mới |
| `@LastModifiedBy` | Người hoặc tác nhân sửa gần nhất | Khi tạo mới hoặc sửa, tùy cấu hình |
| `@LastModifiedDate` | Thời điểm sửa gần nhất | Khi tạo mới hoặc sửa, tùy cấu hình |

Các annotation nằm trong package `org.springframework.data.annotation`.

Ví dụ một aggregate mutable:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    private OrderStatus status;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedDate;
}
~~~

Spring Data JDBC dùng auditing infrastructure để điền các property có annotation. Những property này vẫn là dữ liệu được lưu trong database, vì vậy schema cần có các cột tương ứng và kiểu cột phải tương thích với kiểu Java.

## 2. Bật auditing cho Spring Data JDBC

Để kích hoạt auditing, thêm `@EnableJdbcAuditing` vào cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing
public class JdbcAuditingConfiguration {
}
~~~

Annotation nằm trong package `org.springframework.data.jdbc.repository.config`.

Khi bật cấu hình này, Spring Data JDBC đăng ký auditing infrastructure, bao gồm `AuditingEntityCallback`. Callback này tham gia lifecycle ghi của aggregate và điền các trường auditing trước khi dữ liệu được chuyển thành câu lệnh ghi.

### 2.1. Auditing callback chạy trước khi ghi

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Repository.save(aggregate)"] --> B["Spring Data xác định aggregate mới hay cũ"]
    B --> C["AuditingEntityCallback"]
    C --> D["Gán Created* / LastModified*"]
    D --> E["BeforeConvert và mapping"]
    E --> F["Sinh lệnh INSERT hoặc UPDATE"]
    F --> G["Database lưu các cột audit"]
~~~

Điểm quan trọng: auditing không phải một tác vụ chạy sau khi SQL đã ghi xong. Các giá trị audit phải được điền trước khi Spring Data tạo dữ liệu ghi, để chúng có mặt trong câu INSERT hoặc UPDATE.

### 2.2. Đừng nhầm với AfterConvertCallback

`AfterConvertCallback` chạy sau khi dữ liệu relational được chuyển thành object khi đọc. Auditing ghi dữ liệu dùng callback ở lifecycle trước khi convert để lưu. Hai callback phục vụ hai hướng khác nhau:

- `AfterConvertCallback`: bổ sung dữ liệu sau khi tải aggregate.
- `AuditingEntityCallback`: điền metadata audit trước khi aggregate được chuyển thành dữ liệu ghi.

Nếu muốn `createdDate` hoặc `lastModifiedDate` được lưu vào database, không dùng callback sau khi đọc để gán chúng.

## 3. Cung cấp người thực hiện qua AuditorAware

`@CreatedBy` và `@LastModifiedBy` cần biết ai đang thực hiện thao tác. Spring Data lấy thông tin đó từ bean `AuditorAware<T>`.

Ví dụ ứng dụng dùng Spring Security và lưu tên người dùng dưới dạng `String`:

~~~java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
@EnableJdbcAuditing(auditorAwareRef = "auditorAware")
public class JdbcAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.ofNullable(
                SecurityContextHolder.getContext().getAuthentication()
            )
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName);
    }
}
~~~

`AuditorAware<String>` phải tương thích với kiểu property có `@CreatedBy` và `@LastModifiedBy`. Nếu aggregate dùng kiểu `UUID` cho user ID, auditor cũng cần trả về `UUID`.

Khi không có người dùng hiện tại, `AuditorAware` có thể trả `Optional.empty()`. Khi đó các trường auditor không được tự điền một người dùng giả. Date fields vẫn có thể được cập nhật từ `DateTimeProvider`.

Trong ứng dụng có anonymous authentication, cần loại trừ principal anonymous nếu không muốn lưu tên `anonymousUser` như một người dùng thực. Quy tắc lọc cụ thể phụ thuộc cấu hình Spring Security.

### 3.1. Ghi nhận tác nhân cho batch và tác vụ nền

Không phải thao tác ghi nào cũng đến từ HTTP request. Ví dụ:

- Import dữ liệu ban đêm.
- Scheduler đồng bộ đơn hàng.
- Message listener xử lý sự kiện.
- Công việc quản trị hoặc migration.

Những luồng này có thể không có `SecurityContext`. Hãy định nghĩa một tác nhân hệ thống rõ ràng, chẳng hạn `order-import-service` hoặc `scheduler`, nếu nghiệp vụ cần biết nguồn ghi.

Không nên mặc định mọi trường hợp thiếu authentication đều là một người dùng cụ thể. Giá trị auditor phải phản ánh đúng tác nhân thực hiện.

## 4. Cung cấp thời gian bằng DateTimeProvider và Clock

Nếu không cấu hình riêng, Spring Data sử dụng nguồn thời gian mặc định. Ứng dụng có thể cung cấp `DateTimeProvider` để kiểm soát clock và múi giờ.

Ví dụ dùng UTC:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing(dateTimeProviderRef = "auditingDateTimeProvider")
public class JdbcAuditingConfiguration {

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditingDateTimeProvider(Clock auditingClock) {
        return () -> Optional.of(Instant.now(auditingClock));
    }
}
~~~

`@CreatedDate` và `@LastModifiedDate` có thể dùng các kiểu thời gian được Spring Data hỗ trợ như `Instant` hoặc các kiểu `java.time` phù hợp. Chọn một quy ước nhất quán, thường là lưu thời điểm UTC và chuyển sang múi giờ hiển thị ở tầng trình bày.

Clock có thể được thay bằng clock cố định trong test để kiểm tra giá trị audit chính xác mà không phụ thuộc thời điểm chạy test.

## 5. Auditing với entity bất biến

Với entity mutable, auditing có thể gán giá trị qua setter hoặc property accessor. Với entity bất biến, các field thường là `final` và không có setter. Khi đó Spring Data cần cách tạo instance mới có chứa giá trị audit vừa được gán.

Spring Data mapping hỗ trợ immutable object thông qua constructor và property accessor. Một cách phổ biến để cập nhật property sau khi tạo object là cung cấp **wither**: method trả về một instance mới với đúng một property được thay đổi.

### 5.1. Ví dụ immutable aggregate

Ví dụ dùng Lombok `@Value` và `@With` để tạo class bất biến cùng các wither:

~~~java
import java.time.Instant;

import lombok.Value;
import lombok.With;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Value
@With
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    Long id;

    String orderNumber;

    OrderStatus status;

    @CreatedBy
    String createdBy;

    @CreatedDate
    Instant createdDate;

    @LastModifiedBy
    String lastModifiedBy;

    @LastModifiedDate
    Instant lastModifiedDate;

    @Version
    Long version;
}
~~~

`@Value` tạo các field final, constructor và getter; `@With` tạo các method dạng `withCreatedBy(...)`, `withCreatedDate(...)`, `withLastModifiedBy(...)`, `withLastModifiedDate(...)` và `withVersion(...)`.

Spring Data có thể dùng property accessor để áp dụng các giá trị audit và nhận lại instance mới. Với class tự viết thay vì Lombok, hãy cung cấp wither tương ứng hoặc một chiến lược tạo object bất biến tương thích với mapping của phiên bản Spring Data đang dùng.

### 5.2. Vì sao wither quan trọng?

Giả sử auditing cần cập nhật hai property:

1. `createdBy = "alice"`.
2. `createdDate = 2026-11-13T08:00:00Z`.

Với object bất biến, không thể gán trực tiếp vào field. Property accessor có thể gọi các wither để tạo object kế tiếp:

~~~text
PurchaseOrder ban đầu
        |
        +-- withCreatedBy("alice")
        v
PurchaseOrder có createdBy
        |
        +-- withCreatedDate(timestamp)
        v
PurchaseOrder hoàn chỉnh
~~~

Callback phải tiếp tục làm việc với instance mới sau mỗi lần thay đổi. Spring Data property accessor xử lý việc thay thế instance này trong quá trình mapping; code ứng dụng không cần tự gọi từng wither trước khi `save()`.

Nếu một immutable class không có setter, wither hoặc constructor/property mapping phù hợp để cập nhật property audit, giá trị có thể không được áp dụng như mong muốn. Hãy xác nhận bằng integration test qua repository, không chỉ kiểm tra constructor của object.

### 5.3. Constructor của immutable entity

Spring Data cần biết cách tạo aggregate từ dữ liệu đọc. Với immutable class, constructor hoặc persistence creator phải nhận được các property persistent cần thiết. Những property `@Transient` không phải cột database và không nên bị coi là trường lưu trữ.

Không tự thêm một constructor tùy ý rồi giả định mapping luôn chọn đúng constructor. Nếu có nhiều constructor, hãy khai báo persistence creator theo cơ chế mà phiên bản Spring Data hỗ trợ, hoặc giữ một constructor rõ ràng.

## 6. Object mới được nhận diện như thế nào?

Auditing cần biết aggregate là mới hay đã tồn tại để chọn `markCreated` hay `markModified`. Spring Data JDBC dùng chiến lược nhận diện trạng thái mới (newness) của entity. Quyết định này cũng ảnh hưởng việc repository `save()` chọn INSERT hay UPDATE.

Các quy tắc thường gặp:

1. Nếu entity có property `@Version`, giá trị version `null` thường cho biết entity mới.
2. Nếu không có version property, ID `null` thường cho biết entity mới.
3. Nếu entity triển khai `Persistable`, method `isNew()` do entity cung cấp được dùng để xác định trạng thái mới.

Quy tắc chính xác còn phụ thuộc mapping và phiên bản Spring Data, nhưng cần đặc biệt chú ý khi ứng dụng tự cấp ID.

### 6.1. ID do database sinh

Với ID tự sinh, object mới thường có ID `null`:

~~~java
PurchaseOrder order = new PurchaseOrder(
    null,
    "SO-100",
    OrderStatus.DRAFT,
    null,
    null,
    null,
    null,
    null
);
~~~

Nếu không có chiến lược newness khác, Spring Data nhận diện object là mới, chọn INSERT và auditing điền các trường `@Created*`.

### 6.2. ID được ứng dụng cấp trước

Nếu ứng dụng gán UUID hoặc ID số trước khi lưu:

~~~java
UUID id = UUID.randomUUID();
~~~

thì ID đã khác `null` dù hàng chưa tồn tại. Nếu không có `@Version` hoặc `Persistable`, Spring Data có thể xem object là đã tồn tại và chọn UPDATE.

Khi update không tìm thấy hàng, thao tác không tương đương với việc tự động insert. Auditing cũng có thể đi vào nhánh sửa thay vì nhánh tạo mới.

Với entity dùng ID được cấp trước, hãy khai báo cách nhận diện object mới rõ ràng.

## 7. Dùng @Version để nhận diện object mới có ID được cấp trước

Một lựa chọn là thêm property `@Version` dùng kiểu wrapper, ví dụ `Long`:

~~~java
@Id
Long id;

@Version
Long version;
~~~

Khi tạo object mới, để `version == null`:

~~~java
PurchaseOrder newOrder = new PurchaseOrder(
    UUID.randomUUID(),
    "SO-101",
    OrderStatus.DRAFT,
    null,
    null,
    null,
    null,
    null
);
~~~

Với version null, Spring Data có thể nhận diện entity là mới dù ID đã có giá trị. Sau khi insert, framework gán version ban đầu. Các lần update tiếp theo dùng version để kiểm soát optimistic locking.

`@Version` có hai vai trò liên quan nhưng khác nhau:

- Hỗ trợ nhận diện trạng thái mới/cũ.
- Phát hiện cập nhật cạnh tranh bằng optimistic locking.

Không dùng primitive `long` nếu cần biểu diễn trạng thái version chưa được gán bằng `null`. Kiểu wrapper giúp phân biệt version chưa tồn tại với giá trị version hợp lệ.

Với immutable entity, cần có cách để Spring Data cập nhật cả version, chẳng hạn wither `withVersion(...)` được tạo bởi `@With`.

## 8. Dùng Persistable khi cần kiểm soát isNew()

Nếu không muốn dùng `@Version` hoặc có quy tắc newness riêng, entity có thể triển khai `Persistable<ID>`:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.domain.Persistable;

public class ImportedOrder implements Persistable<UUID> {

    @Id
    private final UUID id;

    @Transient
    private boolean newEntity;

    public ImportedOrder(UUID id) {
        this(id, true);
    }

    private ImportedOrder(UUID id, boolean newEntity) {
        this.id = id;
        this.newEntity = newEntity;
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public ImportedOrder withNewEntity(boolean value) {
        return new ImportedOrder(id, value);
    }
}
~~~

Property `newEntity` được đánh dấu `@Transient` để không tạo cột database. `isNew()` trả về trạng thái do ứng dụng quản lý.

Sau khi insert thành công, trạng thái phải chuyển sang false để lần `save()` tiếp theo được nhận diện là update. Với object mutable, ứng dụng có thể cập nhật cờ sau khi lưu; với object immutable, có thể dùng wither trong một callback sau save hoặc tạo instance persisted trong application layer.

Ví dụ callback sau save cho kiểu immutable:

~~~java
@Component
public class ImportedOrderAfterSaveCallback
        implements AfterSaveCallback<ImportedOrder> {

    @Override
    public ImportedOrder onAfterSave(ImportedOrder aggregate) {
        return aggregate.withNewEntity(false);
    }
}
~~~

Đảm bảo property `newEntity` được mapping nhận diện đúng là transient và callback trả về instance mới. Nếu chọn cách quản lý trạng thái ở service, hãy thay thế object bằng kết quả sau khi lưu thay vì tiếp tục dùng instance còn báo `isNew() == true`.

`Persistable` là công cụ hữu ích nhưng tăng trách nhiệm quản lý lifecycle cho ứng dụng. Nếu `@Version` giải quyết được nhu cầu nhận diện newness, thường nên cân nhắc cách đó trước.

## 9. Auditing được áp dụng thế nào khi tạo mới và cập nhật?

Khi auditing đã bật, Spring Data dùng trạng thái newness để quyết định cách điền các trường:

| Trường | Khi tạo mới | Khi cập nhật |
|---|---|---|
| `@CreatedBy` | Gán auditor hiện tại | Giữ giá trị đã tạo |
| `@CreatedDate` | Gán thời điểm tạo | Giữ giá trị đã tạo |
| `@LastModifiedBy` | Mặc định được gán khi tạo nếu `modifyOnCreate = true` | Gán auditor hiện tại |
| `@LastModifiedDate` | Mặc định được gán khi tạo nếu `modifyOnCreate = true` | Gán thời điểm hiện tại |

`modifyOnCreate` mặc định là `true`. Nếu nghiệp vụ muốn các trường `lastModified*` chỉ có giá trị sau lần sửa đầu tiên, có thể cấu hình:

~~~java
@Configuration
@EnableJdbcAuditing(
    auditorAwareRef = "auditorAware",
    modifyOnCreate = false
)
public class JdbcAuditingConfiguration {
}
~~~

Khi đó, các trường `@LastModifiedBy` và `@LastModifiedDate` không được điền ở lần tạo mới theo cấu hình này. Hãy chọn semantics nhất quán với báo cáo và API của ứng dụng.

Nếu `AuditorAware` trả `Optional.empty()`, các trường auditor không có người dùng để gán. Điều này không đồng nghĩa các trường date cũng bị bỏ qua.

## 10. Nhiều nguồn ghi: callback nào được chạy?

Auditing của Spring Data JDBC gắn với lifecycle persistence của Spring Data. Không phải mọi câu SQL thay đổi database đều đi qua lifecycle đó.

| Nguồn ghi | Auditing callback Spring Data JDBC |
|---|---|
| Repository `save()` | Có |
| `JdbcAggregateTemplate.insert()` / `update()` / `save()` | Có, khi dùng Spring Data aggregate infrastructure |
| Repository query dẫn xuất dùng để đọc | Không ghi audit chỉ vì đọc |
| `@Modifying @Query` thực thi SQL trực tiếp | Không nên giả định callback aggregate được chạy |
| `JdbcTemplate` / `NamedParameterJdbcTemplate` | Không tự chạy auditing entity callback |
| Stored procedure hoặc SQL script | Không tự chạy callback |
| Import tool hoặc ứng dụng khác ghi database | Không chạy callback của ứng dụng Spring này |
| Database trigger | Do database thực thi, độc lập với Spring callback |

Điều này đặc biệt quan trọng nếu cùng bảng được ghi bởi nhiều nguồn. Nếu một ứng dụng dùng repository còn một batch job dùng `JdbcTemplate`, các cột audit có thể được cập nhật theo hai cách khác nhau hoặc không được cập nhật ở một đường ghi.

### 10.1. Repository và JdbcAggregateTemplate

Hai API này cùng sử dụng aggregate mapping infrastructure của Spring Data JDBC. Khi thao tác lưu aggregate qua repository hoặc `JdbcAggregateTemplate`, lifecycle callback của Spring Data được áp dụng, vì vậy auditing có thể điền các trường tương ứng.

Ví dụ:

~~~java
repository.save(order);
~~~

hoặc:

~~~java
jdbcAggregateTemplate.insert(order);
jdbcAggregateTemplate.update(order);
~~~

Các thao tác này vẫn cần cấu hình `@EnableJdbcAuditing`, `AuditorAware` và các property audit phù hợp.

### 10.2. SQL trực tiếp không tự chạy auditing callback

Ví dụ:

~~~java
namedParameterJdbcTemplate.update("""
    UPDATE purchase_orders
    SET status = :status
    WHERE id = :id
    """, params);
~~~

Câu lệnh trên thay đổi database trực tiếp. Nó không tạo aggregate qua repository save và không tự gọi `AuditingEntityCallback`. Nếu cần cập nhật audit fields, phải thực hiện rõ trong SQL:

~~~sql
UPDATE purchase_orders
SET status = :status,
    last_modified_by = :actor,
    last_modified_date = :modifiedAt
WHERE id = :id;
~~~

Hoặc giao việc đó cho database trigger. Hãy chọn một nguồn chịu trách nhiệm chính để tránh hai cơ chế ghi đè giá trị của nhau.

## 11. Chọn chiến lược auditing khi có nhiều ứng dụng cùng ghi

Nếu nhiều ứng dụng, batch job hoặc công cụ quản trị cùng ghi một bảng, có hai hướng chính.

### 11.1. Auditing ở application layer

Mỗi writer phải tuân thủ một hợp đồng ghi:

- Tất cả luồng Spring Data JDBC dùng auditing callback.
- Mọi luồng SQL trực tiếp tự truyền actor và thời điểm.
- Import/batch cung cấp system actor rõ ràng.
- Các ứng dụng khác tuân theo cùng quy ước cột và kiểu dữ liệu.

Ưu điểm là logic actor có thể tích hợp với security context và domain/application layer. Nhược điểm là mọi writer phải tuân thủ quy tắc; một script hoặc ứng dụng ngoài có thể bỏ sót.

### 11.2. Auditing ở database layer

Database trigger có thể cập nhật `created_date` hoặc `last_modified_date` cho mọi nguồn ghi, bất kể thao tác đến từ Spring Data hay ứng dụng khác.

Ví dụ khái niệm:

~~~sql
-- Cú pháp trigger phụ thuộc hệ quản trị database.
-- Trigger BEFORE UPDATE có thể gán:
-- NEW.last_modified_date = CURRENT_TIMESTAMP
~~~

Ưu điểm:

- Mọi nguồn ghi vào bảng đều đi qua cùng quy tắc database.
- Không phụ thuộc một ứng dụng cụ thể có chạy Spring callback hay không.
- Hữu ích khi có nhiều service hoặc công cụ quản trị cùng ghi.

Giới hạn:

- Cú pháp trigger khác nhau giữa các database.
- Database cần biết actor là ai; `CURRENT_USER` có thể chỉ là tài khoản kết nối dùng chung.
- Cần cơ chế truyền actor vào session/database context nếu muốn lưu người dùng ứng dụng.
- Giá trị trigger có thể xung đột với giá trị do application auditing gửi xuống.
- Logic auditing nằm trong database và cần được quản lý cùng migration/schema.

### 11.3. Không để hai nguồn cùng sở hữu một trường

Nếu Spring Data callback gán `last_modified_date` bằng application clock và trigger lại ghi đè bằng database clock, kết quả cuối cùng phụ thuộc thứ tự thực thi. Điều đó có thể chấp nhận được nếu database là nguồn thời gian chuẩn, nhưng cần được thiết kế rõ.

Hãy quyết định:

- Ai sở hữu `created_date`?
- Ai sở hữu `last_modified_date`?
- Ai cung cấp `created_by` và `last_modified_by`?
- Nếu thiếu actor thì lưu NULL, actor hệ thống hay từ chối thao tác?
- Clock chuẩn là application UTC clock hay database clock?

Không triển khai hai cơ chế độc lập mà không xác định thứ tự và nguồn dữ liệu có thẩm quyền.

## 12. Nhiều writer trong cùng một ứng dụng

Ngay trong một ứng dụng, có thể tồn tại nhiều đường ghi:

~~~text
HTTP controller
    |
    v
Application service
    |
    +--> Repository.save()
    |
    +--> JdbcAggregateTemplate.update()
    |
    +--> NamedParameterJdbcTemplate.update()
    |
    +--> Batch import
~~~

Nếu các đường đầu dùng aggregate lifecycle còn các đường sau chạy SQL trực tiếp, auditing không đồng nhất trừ khi SQL trực tiếp tự gán trường audit hoặc có trigger.

Nên gom quy tắc ghi vào một application service hoặc persistence adapter khi có thể. Với bulk update cần SQL trực tiếp vì hiệu năng, hãy cập nhật audit columns trong cùng câu lệnh hoặc dùng trigger theo chiến lược đã chọn.

Đặc biệt, bulk update thường không tải từng aggregate lên, nên không có một object để `AuditingEntityCallback` xử lý. Đừng kỳ vọng callback được gọi một lần cho mỗi hàng bị thay đổi.

## 13. Auditor và thời gian trong hệ thống nhiều instance

Khi ứng dụng chạy nhiều instance:

- Mỗi instance có thể có security context riêng cho request đang xử lý.
- Tác vụ nền cần actor hệ thống nhất quán.
- Clock của các máy có thể lệch nhau.
- Một số writer ngoài Spring có thể dùng clock database.

Để dữ liệu dễ so sánh:

1. Chuẩn hóa timestamp theo UTC.
2. Đồng bộ clock của các node bằng cơ chế vận hành phù hợp.
3. Cung cấp `DateTimeProvider` thống nhất.
4. Dùng cùng quy ước actor ID giữa các service.
5. Tránh lưu tên hiển thị có thể thay đổi nếu cần lịch sử ổn định; ưu tiên ID người dùng hoặc mã service.

Nếu cần một timestamp duy nhất có thẩm quyền cho mọi writer, database timestamp/trigger có thể phù hợp hơn. Nếu chọn application clock, tất cả writer phải tuân thủ cùng quy ước.

## 14. Kiểm tra auditing với entity bất biến và object mới

Một unit test cho `AuditorAware` hoặc wither chưa đủ để chứng minh auditing hoạt động trong persistence. Cần integration test đi qua repository để Spring Data chạy lifecycle callback.

Các tình huống nên kiểm tra:

| Tình huống | Điều cần xác nhận |
|---|---|
| Insert entity có ID null | `createdBy` và `createdDate` được điền |
| Insert entity có ID cấp trước và `@Version == null` | Vẫn được nhận diện là mới |
| Update entity đã lưu | `created*` giữ nguyên, `lastModified*` thay đổi |
| Immutable entity | Repository trả object có các trường audit được cập nhật |
| `AuditorAware` trả empty | Các trường auditor tuân theo quy ước null/fallback |
| `modifyOnCreate = false` | `lastModified*` không được gán lúc insert |
| Ghi bằng `JdbcTemplate` | Callback không tự chạy; SQL hoặc trigger phải xử lý audit |

### 14.1. Test với Clock cố định

Có thể cung cấp `Clock.fixed(...)` trong test:

~~~java
@TestConfiguration
static class FixedClockConfiguration {

    @Bean
    Clock auditingClock() {
        return Clock.fixed(
            Instant.parse("2026-11-13T08:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
~~~

Khi `DateTimeProvider` dùng clock này, test có thể so sánh chính xác `createdDate` và `lastModifiedDate` mà không phụ thuộc thời gian thực.

### 14.2. Test update không ghi đè created fields

Quy trình:

1. Lưu aggregate với auditor `alice`.
2. Ghi nhận `createdBy` và `createdDate`.
3. Đổi auditor thành `bob`.
4. Tải aggregate, thay đổi trạng thái và lưu lại.
5. Xác nhận `createdBy` vẫn là `alice`.
6. Xác nhận `lastModifiedBy` là `bob` và `lastModifiedDate` được cập nhật.

Với immutable entity, luôn dùng instance được trả về từ repository sau mỗi lần lưu vì các wither và version update có thể tạo object mới.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `createdBy` luôn NULL | Chưa bật auditing hoặc `AuditorAware` trả empty | Kiểm tra `@EnableJdbcAuditing` và auditor bean |
| Ngày tạo không được gán | Callback auditing chưa được đăng ký hoặc property không được mapping | Kiểm tra cấu hình và annotation |
| Entity bất biến không có giá trị audit | Thiếu wither hoặc cách cập nhật property phù hợp | Cung cấp wither/constructor mapping và test qua repository |
| Entity có ID cấp trước bị UPDATE thay vì INSERT | Newness mặc định suy ra entity đã tồn tại | Dùng `@Version` wrapper hoặc `Persistable.isNew()` |
| `createdDate` bị đổi khi update | Logic ứng dụng tự ghi đè hoặc nhận diện newness sai | Kiểm tra chiến lược newness và không tự set created fields |
| `lastModifiedDate` trống khi insert | `modifyOnCreate` được đặt false | Xác nhận đây là semantics mong muốn |
| `isNew()` luôn true | Không chuyển trạng thái sau insert | Dùng version hoặc cập nhật cờ transient sau save |
| SQL trực tiếp không cập nhật audit | Bỏ qua Spring Data lifecycle callback | Gán audit columns trong SQL hoặc dùng trigger |
| Audit khác nhau giữa các ứng dụng | Mỗi writer dùng actor/clock/format khác nhau | Chuẩn hóa hợp đồng auditing hoặc chuyển nguồn sở hữu xuống database |
| `createdBy` lưu `anonymousUser` | Không loại trừ anonymous principal | Lọc principal phù hợp trong `AuditorAware` |
| Batch job không có auditor | Không có security context | Cung cấp system actor rõ ràng |
| Thời gian giữa các instance lệch | Clock không đồng bộ | Chuẩn hóa UTC và nguồn thời gian |

## 16. Quy trình triển khai auditing đáng tin cậy

Khi thêm auditing vào aggregate, có thể đi theo trình tự:

1. **Thiết kế cột:** xác định actor ID, timestamp, nullability và kiểu dữ liệu.
2. **Bật auditing:** dùng `@EnableJdbcAuditing`.
3. **Cung cấp actor:** khai báo `AuditorAware<T>` và quy tắc cho request, batch, scheduler.
4. **Cung cấp clock:** dùng `DateTimeProvider` nếu cần kiểm soát thời gian.
5. **Đánh dấu property:** dùng `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, `@LastModifiedDate`.
6. **Thiết kế immutable mapping:** cung cấp wither hoặc property creation strategy phù hợp.
7. **Xác định newness:** dùng ID null, `@Version` hoặc `Persistable` theo cách ID được cấp.
8. **Liệt kê mọi nguồn ghi:** repository, `JdbcAggregateTemplate`, SQL trực tiếp, batch và ứng dụng ngoài.
9. **Chọn nguồn audit có thẩm quyền:** application callback, SQL do writer quản lý hoặc database trigger.
10. **Integration test:** kiểm tra insert, update, immutable instance, assigned ID và từng đường ghi.

## 17. Bài tập thực hành

### Bài 1 — Auditing cơ bản

1. Bật `@EnableJdbcAuditing`.
2. Tạo `AuditorAware<String>` lấy tên principal.
3. Thêm bốn property audit vào `PurchaseOrder`.
4. Lưu một đơn và kiểm tra các cột trong database.

### Bài 2 — Entity bất biến

1. Chuyển `PurchaseOrder` thành class bất biến.
2. Dùng Lombok `@Value` và `@With`, hoặc tự viết wither.
3. Giữ các property audit trong constructor.
4. Lưu và tải aggregate qua repository.
5. Xác nhận instance trả về chứa giá trị audit.

### Bài 3 — Assigned ID và newness

1. Tạo aggregate có UUID cấp trước.
2. Thử lưu khi không có `@Version`.
3. Thêm `@Version Long version` và để null khi tạo mới.
4. Kiểm tra thao tác đầu là INSERT và lần tiếp theo là UPDATE.
5. Thử `Persistable.isNew()` nếu cần chiến lược riêng.

### Bài 4 — Nhiều nguồn ghi

1. Lưu một aggregate qua repository.
2. Cập nhật aggregate khác qua `JdbcAggregateTemplate`.
3. Cập nhật một hàng bằng `JdbcTemplate`.
4. Quan sát đường nào kích hoạt auditing callback.
5. Thêm actor/time parameter hoặc database trigger cho đường SQL trực tiếp.

### Bài 5 — Nhiều actor và clock

1. Cố định clock trong test.
2. Lưu aggregate với actor `alice`.
3. Update với actor `bob`.
4. Kiểm tra `createdBy` giữ nguyên và `lastModifiedBy` thay đổi.
5. Thử batch job không có security context và cung cấp system actor.

## 18. Kết luận

Spring Data JDBC auditing điền metadata trước khi aggregate được chuyển thành dữ liệu ghi. `@CreatedBy` và `@CreatedDate` được áp dụng khi entity được nhận diện là mới; `@LastModifiedBy` và `@LastModifiedDate` được cập nhật khi sửa, và mặc định cũng có thể được điền lúc tạo mới thông qua `modifyOnCreate`.

Với immutable entity, cung cấp wither hoặc cơ chế tạo instance mới tương thích với mapping để các giá trị audit và version được giữ trong object trả về. Khi ứng dụng tự cấp ID, đừng để Spring suy ra newness chỉ từ ID khác null; dùng `@Version` kiểu wrapper hoặc `Persistable.isNew()` theo yêu cầu.

Cuối cùng, auditing callback chỉ bao phủ các đường ghi đi qua Spring Data JDBC aggregate infrastructure. SQL trực tiếp, bulk update và writer bên ngoài cần tự tuân thủ hợp đồng audit hoặc dùng database trigger. Khi có nhiều nguồn ghi, hãy xác định một nguồn có thẩm quyền cho actor và timestamp, rồi kiểm tra tất cả đường ghi bằng integration test.
