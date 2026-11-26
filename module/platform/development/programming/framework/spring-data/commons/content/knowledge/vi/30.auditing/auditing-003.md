# Auditable và lựa chọn annotation hoặc interface

## 1. Hai cách khai báo metadata cho cùng một nhu cầu

Trong chương **Auditing** của module **SPRING_DATA_COMMONS**, ứng dụng cần chỉ ra nơi lưu thông tin ai tạo, ai sửa và thời điểm thực hiện. Có hai cách khai báo chính:

- Dùng annotation như `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, `@LastModifiedDate` trên các thuộc tính cần theo dõi.
- Cho domain class triển khai `Auditable<U, ID, T>` để cung cấp một hợp đồng getter/setter rõ ràng cho metadata audit.

Cả hai cách đều cần hạ tầng auditing được kích hoạt theo module. Thêm annotation hoặc interface vào class chưa tự làm mọi thao tác persistence được audit. [Spring Data Commons: Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html)

Lựa chọn nên dựa trên thiết kế domain: cần theo dõi bao nhiêu thuộc tính, có muốn công khai các setter audit không, có chấp nhận phụ thuộc interface của Spring Data không và entity được nhận biết là mới theo cách nào.

Trong bài, các ví dụ lưu trữ chọn **Spring Data JDBC** để có bối cảnh cụ thể. Hợp đồng Auditable thuộc Commons, còn annotation kích hoạt, mapping và đường gọi auditing thuộc module tương ứng.

## 2. Phân biệt các thành phần thường có tên gần nhau

| Thành phần | Vai trò |
| --- | --- |
| `Auditable<U, ID, T>` | Hợp đồng của entity để đọc và ghi metadata audit. |
| `AuditorAware<U>` | Nguồn cung cấp chủ thể đang thực hiện thao tác trong luồng đồng bộ. |
| `DateTimeProvider` | Nguồn cung cấp thời gian cho auditing. |
| `@CreatedBy`, `@LastModifiedBy` | Đánh dấu thuộc tính lưu chủ thể tạo hoặc sửa. |
| `@CreatedDate`, `@LastModifiedDate` | Đánh dấu thuộc tính lưu thời điểm tạo hoặc sửa. |
| Cấu hình auditing của module | Đăng ký hạ tầng để metadata được điền tại các điểm persistence được hỗ trợ. |

Entity triển khai **Auditable**, còn một thành phần hạ tầng triển khai hoặc cung cấp **AuditorAware**. Không để entity tự đóng vai trò “người dùng hiện tại” chỉ vì hai interface cùng có tiền tố Audit.

Auditing cơ bản giữ metadata tạo và sửa gần nhất trên entity. Nó không tự tạo lịch sử mọi phiên bản dữ liệu, không thay thế kiểm tra quyền và không thay thế optimistic locking.

## 3. Lựa chọn annotation: đánh dấu đúng những gì cần theo dõi

### 3.1. Bốn annotation thường dùng

| Annotation | Ý nghĩa metadata |
| --- | --- |
| `org.springframework.data.annotation.CreatedBy` | Chủ thể tạo entity. |
| `org.springframework.data.annotation.CreatedDate` | Thời điểm tạo entity. |
| `org.springframework.data.annotation.LastModifiedBy` | Chủ thể sửa entity gần nhất. |
| `org.springframework.data.annotation.LastModifiedDate` | Thời điểm sửa entity gần nhất. |

Có thể chọn một phần metadata. Một model chỉ cần ngày tạo và ngày sửa không bắt buộc có hai thuộc tính actor hoặc một nguồn auditor. Cách annotation phù hợp với yêu cầu theo dõi có chọn lọc. [Commons: Annotation-based Auditing Metadata](https://docs.spring.io/spring-data/commons/reference/auditing.html)

### 3.2. Model JDBC dùng annotation

```java
package example.auditing;

import java.time.Instant;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.relational.core.mapping.Table;

@Table("annotation_note")
public class AnnotationNote {

    @Id
    private Long id;

    private String body;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedDate;

    public AnnotationNote() {
    }

    public static AnnotationNote draft(String body) {
        AnnotationNote note = new AnnotationNote();
        note.body = body;
        return note;
    }

    public void reviseBody(String body) {
        this.body = body;
    }

    public Long getId() {
        return id;
    }

    public String getBody() {
        return body;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public Instant getCreatedDate() {
        return createdDate;
    }

    public String getLastModifiedBy() {
        return lastModifiedBy;
    }

    public Instant getLastModifiedDate() {
        return lastModifiedDate;
    }
}
```

Trong ví dụ, tên field do ứng dụng chọn; annotation biểu đạt vai trò audit. Entity không phải cung cấp setter audit công khai chỉ để có được hợp đồng Auditable. Cách hạ tầng ghi vào thuộc tính còn phụ thuộc mapper và mô hình truy cập của module.

Các getter trong model này có thể trả null trước khi auditing điền dữ liệu. Nếu API ứng dụng muốn che việc chưa có giá trị, có thể thiết kế DTO hoặc kiểu trả về phù hợp; annotation không ép tất cả getter phải trả Optional.

### 3.3. Đặc điểm thiết kế

Annotation đặt metadata ngay tại thuộc tính, ít áp đặt lên API công khai của entity. Nó vẫn tạo phụ thuộc vào annotation của Spring Data, nhưng không bắt entity triển khai toàn bộ interface auditing và Persistable.

Cách này cũng cho phép chỉ theo dõi hai mốc thời gian hoặc tổ chức metadata theo cấu trúc phù hợp. Nếu tách thành object metadata nhúng, phải kiểm tra khả năng mapping và auditing của store; không mặc định mọi module đều hỗ trợ giống nhau.

## 4. Lựa chọn interface: hiểu đầy đủ Auditable

Chữ ký rút gọn của interface:

```java
public interface Auditable<U, ID, T extends TemporalAccessor>
        extends Persistable<ID> {

    Optional<U> getCreatedBy();
    void setCreatedBy(U createdBy);

    Optional<T> getCreatedDate();
    void setCreatedDate(T createdDate);

    Optional<U> getLastModifiedBy();
    void setLastModifiedBy(U lastModifiedBy);

    Optional<T> getLastModifiedDate();
    void setLastModifiedDate(T lastModifiedDate);
}
```

Đây là phần trình bày hợp đồng chính, lược bỏ các nullability annotation và tài liệu API. Ngoài các method trên, entity còn có `getId()` và `isNew()` kế thừa từ Persistable. [API Auditable](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Auditable.html)

### 4.1. Ba tham số generic có ý nghĩa khác nhau

Với khai báo:

```java
class InterfaceNote implements Auditable<String, Long, Instant> {
    // ...
}
```

| Tham số | Lựa chọn trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| `U` | `String` | Kiểu chủ thể audit, dùng cho cả createdBy và lastModifiedBy. |
| `ID` | `Long` | Kiểu định danh của entity được audit. |
| `T` | `Instant` | Kiểu thời gian audit, dùng cho cả ngày tạo và ngày sửa. |

Không nhầm `ID` với kiểu định danh của người dùng. Một Note có ID Long vẫn có thể lưu actor bằng chuỗi như `user:42`.

`T` bị ràng buộc bởi `TemporalAccessor`. Vì vậy không thể thay T bằng Long hoặc `java.util.Date` chỉ vì một số thuộc tính auditing dùng annotation có thể hỗ trợ các kiểu thời gian đó. Khi đổi từ annotation sang interface, phải xem lại kiểu thời gian đang dùng.

### 4.2. Optional thuộc hợp đồng getter

`getCreatedBy()` trả `Optional<U>`, nhưng `setCreatedBy()` nhận U. Các getter ngày giờ cũng trả Optional, còn setter nhận T.

Điều này không yêu cầu field persistence phải có kiểu Optional. Trong model mutable, có thể lưu `String` hoặc `Instant` nullable và bọc bằng `Optional.ofNullable()` tại getter. Cần phân biệt hợp đồng Java với biểu diễn được mapper ghi xuống storage.

### 4.3. Interface yêu cầu hành vi, không chỉ nhãn đánh dấu

Implement Auditable đồng nghĩa phải cung cấp các method thực sự đọc và ghi được metadata. Không cài setter rỗng hoặc ném UnsupportedOperationException chỉ để compiler chấp nhận class immutable.

Nếu muốn dùng entity immutable, annotation có thể phù hợp với API domain hơn, nhưng vẫn phải kiểm chứng khả năng cập nhật metadata của mapper và auditing theo module. Chọn annotation không tự bảo đảm mọi dạng immutable đều được hỗ trợ.

## 5. Model JDBC triển khai Auditable

Ví dụ dưới đây là một lựa chọn thay thế model annotation, không cần thêm lại bốn annotation audit trên các field.

```java
package example.auditing;

import java.time.Instant;
import java.util.Optional;
import org.springframework.data.annotation.Id;
import org.springframework.data.domain.Auditable;
import org.springframework.data.relational.core.mapping.Table;

@Table("interface_note")
public class InterfaceNote implements Auditable<String, Long, Instant> {

    @Id
    private Long id;

    private String body;
    private String createdBy;
    private Instant createdDate;
    private String lastModifiedBy;
    private Instant lastModifiedDate;

    public InterfaceNote() {
    }

    public static InterfaceNote draft(String body) {
        InterfaceNote note = new InterfaceNote();
        note.body = body;
        return note;
    }

    public void reviseBody(String body) {
        this.body = body;
    }

    public String getBody() {
        return body;
    }

    @Override
    public Long getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return id == null;
    }

    @Override
    public Optional<String> getCreatedBy() {
        return Optional.ofNullable(createdBy);
    }

    @Override
    public void setCreatedBy(String createdBy) {
        this.createdBy = createdBy;
    }

    @Override
    public Optional<Instant> getCreatedDate() {
        return Optional.ofNullable(createdDate);
    }

    @Override
    public void setCreatedDate(Instant createdDate) {
        this.createdDate = createdDate;
    }

    @Override
    public Optional<String> getLastModifiedBy() {
        return Optional.ofNullable(lastModifiedBy);
    }

    @Override
    public void setLastModifiedBy(String lastModifiedBy) {
        this.lastModifiedBy = lastModifiedBy;
    }

    @Override
    public Optional<Instant> getLastModifiedDate() {
        return Optional.ofNullable(lastModifiedDate);
    }

    @Override
    public void setLastModifiedDate(Instant lastModifiedDate) {
        this.lastModifiedDate = lastModifiedDate;
    }
}
```

Model giả định ID Long do database sinh: object mới có ID null, object đã được lưu hoặc được đọc từ storage có ID không null. `isNew()` ở đây được chọn cho đúng giả định đó.

`@Id` và `@Table` vẫn cần theo quy tắc mapping của ví dụ. Chọn interface cho audit không loại bỏ metadata định danh hoặc metadata lưu trữ.

Trong JDBC, mapping field của entity tách khỏi những getter Optional của hợp đồng Auditable; các field audit trong ví dụ vẫn là String và Instant. Không sao chép giả định truy cập field này sang mọi module dùng property access. [Spring Data JDBC: Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html)

## 6. Điểm dễ bỏ sót: Auditable kéo theo Persistable

### 6.1. isNew() ảnh hưởng đến nhiều hơn metadata audit

Persistable yêu cầu entity trả lời nó là mới hay đã được persistence quản lý trước đó. Hợp đồng không chỉ nói “đã có ID chưa”. [API Persistable](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Persistable.html)

Khi entity triển khai Persistable, chiến lược nhận biết entity mới có thể được giao cho `isNew()`. Vì Auditable kế thừa Persistable, việc đổi cách khai báo audit có thể đồng thời đổi trách nhiệm nhận biết trạng thái entity. [Commons: Entity State Detection Strategies](https://docs.spring.io/spring-data/commons/reference/is-new-state-detection.html)

Hai lỗi thường gặp:

| Implementation | Hệ quả có thể xảy ra |
| --- | --- |
| `isNew()` luôn trả true | Mỗi lần lưu có thể bị xử lý như entity mới, kéo theo insert hoặc điền lại metadata tạo theo luồng tương ứng. |
| `isNew()` luôn trả false | Object chưa lưu có thể bị xử lý như entity đã tồn tại, dẫn đến đường update hoặc thiếu metadata tạo. |

Hành vi cuối cùng phải được đối chiếu với module và thao tác đang sử dụng. Không sửa isNew bằng một giá trị hằng để né lỗi insert/update.

### 6.2. ID gán trước cần chiến lược khác

Nếu ứng dụng tạo UUID ngay khi tạo domain object, ID đã khác null dù entity chưa từng được lưu. Khi đó `id == null` không thể biểu diễn đầy đủ trạng thái mới.

Cần thiết kế cơ chế nhận biết mới phù hợp với module, đồng thời xác định cách chuyển trạng thái sau lưu và sau đọc. Không dùng `createdDate == null` làm giải pháp mặc định: bản ghi cũ có thể chưa được bổ sung audit metadata, hoặc dữ liệu được import có thể đã mang thời gian tạo.

### 6.3. Thuộc tính kỹ thuật và property access

Khi dùng property access, `getId()` và `isNew()` là các accessor cần được xét trong mapping. Persistable có lưu ý về việc đánh dấu transient theo cơ chế phù hợp để tránh lưu nhầm thuộc tính kỹ thuật.

Ví dụ JDBC ở trên dùng field mapping và không khai báo một field `new`. Nếu chuyển model sang module hoặc kiểu truy cập khác, kiểm tra lại việc ánh xạ các accessor thay vì mặc định mọi thứ giữ nguyên.

## 7. Cấu hình auditing dùng chung cho hai model

Hai model có thể sử dụng cùng một nguồn auditor và nguồn thời gian. Ví dụ JDBC:

```java
package example.auditing;

import java.time.Clock;
import java.time.Instant;
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing(
        auditorAwareRef = "currentAuditor",
        dateTimeProviderRef = "auditTimeProvider",
        modifyOnCreate = true
)
public class AuditingConfiguration {

    @Bean
    AuditorAware<String> currentAuditor() {
        return () -> Optional.of("system:lesson");
    }

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditTimeProvider(Clock auditClock) {
        return () -> Optional.of(Instant.now(auditClock));
    }
}
```

`system:lesson` là actor cố định phục vụ minh họa. Trong ứng dụng thật, nguồn auditor phải phản ánh người dùng hoặc tiến trình đang thực hiện thao tác theo chính sách của hệ thống.

Spring Data JDBC dùng `@EnableJdbcAuditing` để kích hoạt auditing; `auditorAwareRef` giúp chọn rõ bean khi có nhiều nguồn auditor. [Spring Data JDBC: Auditing](https://docs.spring.io/spring-data/relational/reference/jdbc/auditing.html)

Các thuộc tính `dateTimeProviderRef`, `setDates` và `modifyOnCreate` điều khiển nguồn thời gian và việc điền metadata. API EnableJdbcAuditing có mặc định setDates và modifyOnCreate là true; ví dụ ghi rõ modifyOnCreate để người đọc thấy kỳ vọng. [API EnableJdbcAuditing](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/jdbc/repository/config/EnableJdbcAuditing.html)

Hai bảng cần được chuẩn bị bằng cơ chế schema của dự án. Chọn kiểu cột tương thích với String, ID Long được sinh và Instant qua driver/converter của môi trường; lưu ý độ chính xác thời gian và quy tắc đặt tên cột. Auditing không tự tạo schema phù hợp.

### 7.1. Kiểu auditor phải tương thích

Trong hai model, actor là String nên nguồn tương ứng là `AuditorAware<String>`. Nếu dùng một kiểu User domain thay cho String, cần đồng bộ kiểu trả về, cách mapping và quan hệ lưu trữ của module.

AuditorAware cung cấp `Optional<U> getCurrentAuditor()`. Optional.empty biểu đạt không có auditor tại thời điểm gọi, không đồng nghĩa cơ chế auditing sẽ tự tạo một actor hệ thống. Chính sách có cho phép thiếu actor hay không cần được xác định riêng. [API AuditorAware](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AuditorAware.html)

Không lấy createdBy hoặc lastModifiedBy trực tiếp từ request chỉ để điền cho đủ. Metadata này cần được suy ra từ ngữ cảnh đáng tin cậy của ứng dụng; entity có setter công khai không có nghĩa mọi caller đều được quyền quyết định auditor.

### 7.2. Thời gian là một nguồn có thể thay thế

DateTimeProvider trả `Optional<TemporalAccessor>`. Việc tách nguồn này giúp kiểm thử với thời gian cố định và thể hiện rõ thời gian do ứng dụng cung cấp. [API DateTimeProvider](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/auditing/DateTimeProvider.html)

Nếu hệ thống quyết định để database sinh thời gian, cần thiết kế phối hợp với auditing và refresh dữ liệu một cách rõ ràng. Không để hai nguồn cùng ghi một field rồi mặc định kết quả cuối luôn đúng ý định.

## 8. Luồng CRUD minh họa

Repository cho model interface:

```java
package example.auditing;

import org.springframework.data.repository.CrudRepository;

public interface InterfaceNoteRepository
        extends CrudRepository<InterfaceNote, Long> {
}
```

Trong một phương thức ứng dụng đã được cung cấp repository:

```java
InterfaceNote saved = repository.save(
        InterfaceNote.draft("Bản nháp đầu tiên")
);

Long id = saved.getId();

InterfaceNote loaded = repository.findById(id).orElseThrow();
loaded.reviseBody("Nội dung đã cập nhật");
InterfaceNote updated = repository.save(loaded);
```

Với cấu hình minh họa, actor ở cả hai lần lưu là `system:lesson`. Nếu muốn kiểm tra hai người dùng khác nhau, thay nguồn auditor trong môi trường kiểm thử bằng một nguồn có thể điều khiển theo từng bước.

Giả sử entity ban đầu chưa có audit metadata, auditing được kích hoạt, có auditor và thời gian hợp lệ, cùng `modifyOnCreate=true`, kỳ vọng nghiệp vụ có thể được diễn đạt như sau:

| Thao tác | createdBy | createdDate | lastModifiedBy | lastModifiedDate |
| --- | --- | --- | --- | --- |
| Tạo tại T0 bởi A | A | T0 | A | T0 |
| Sửa tại T1 bởi B | Giữ A | Giữ T0 | B | T1 |

Bảng không yêu cầu T1 luôn lớn hơn T0 trong mọi môi trường đồng hồ; điều cần kiểm tra là nguồn thời gian đã chọn được áp dụng đúng. Nếu cần kiểm soát cập nhật cạnh tranh, dùng cơ chế version hoặc điều kiện ghi phù hợp, không dùng timestamp audit thay thế theo mặc định.

`@CreatedBy` và `@CreatedDate` cũng không tạo ràng buộc database bất biến. Nếu application code tự ghi đè giá trị tạo rồi lưu lại, không được giả định annotation sẽ luôn bảo vệ hoặc khôi phục lịch sử đúng. Hãy kiểm soát những field được lấy từ request và cách entity được cập nhật.

## 9. So sánh để lựa chọn

| Tiêu chí | Annotation | Auditable |
| --- | --- | --- |
| Theo dõi một phần metadata | Thuận tiện, chỉ đánh dấu những thuộc tính cần dùng. | Phải đáp ứng toàn bộ hợp đồng method của interface. |
| API công khai của entity | Không bắt buộc cung cấp bộ setter theo interface. | Công khai các setter và getter audit theo chữ ký đã định nghĩa. |
| Kiểu thời gian | Chọn theo annotation, mapper và conversion được hỗ trợ. | Một T chung cho hai mốc thời gian, phải là TemporalAccessor. |
| Kiểu chủ thể | Metadata được đánh dấu tại thuộc tính và phải tương thích với nguồn auditor. | Một U chung cho chủ thể tạo và sửa. |
| Phụ thuộc Spring Data | Phụ thuộc các annotation được dùng. | Phụ thuộc interface domain cùng Persistable. |
| Nhận biết entity mới | Có thể dùng chiến lược thông thường của module nếu không triển khai Persistable. | Phải có implementation isNew đúng với lifecycle. |
| Model immutable | Ít áp đặt setter ở API; vẫn cần kiểm tra module hỗ trợ cập nhật metadata. | Hợp đồng setter tự nhiên hơn với model mutable. |
| Code dùng chung cần một kiểu audit | Có thể xây abstraction riêng nếu cần. | Có sẵn kiểu Auditable để viết code generic. |
| Đặt tên field | Vai trò đến từ annotation. | Vai trò đến từ implementation getter/setter; storage vẫn cần mapping đúng. |

### 9.1. Khi annotation là lựa chọn thuận tiện

Dùng annotation khi entity chỉ cần một vài field audit, khi muốn giữ API domain gọn hoặc khi không muốn việc thêm auditing kéo theo trách nhiệm triển khai Persistable.

Ví dụ, một bảng danh mục chỉ cần `createdDate` và `lastModifiedDate` có thể khai báo hai annotation ngày giờ. Không cần tạo setter actor rỗng chỉ để đáp ứng một interface có nhiều khả năng hơn yêu cầu hiện tại.

### 9.2. Khi interface có ích

Dùng Auditable khi ứng dụng chủ động chọn hợp đồng mutable đầy đủ, muốn các entity có cùng API audit và đã có chiến lược isNew được thiết kế rõ.

Chẳng hạn một tiện ích nội bộ có thể nhận `Auditable<?, ?, ?>` để đọc trạng thái audit mà không phải biết tên field từng entity. Tuy nhiên, nếu chỉ cần một view chỉ đọc cho ứng dụng, cũng có thể định nghĩa interface domain riêng thay vì kéo cả bộ setter và Persistable vào mọi model.

### 9.3. Không cần chồng hai cách để “chắc chắn hơn”

Hai cách mô tả cùng một vai trò metadata không cần được gắn đồng thời vào một model như điều kiện kích hoạt auditing. Việc vừa implement interface vừa đặt annotation trên các field khác nhau có thể làm thiết kế khó theo dõi và tạo giả định sai rằng mọi nguồn metadata sẽ tự được hợp nhất.

Chọn một cách biểu đạt chính cho từng model, giữ implementation nhất quán và kiểm chứng hành vi qua infrastructure thực tế.

## 10. AbstractAuditable không phải lớp nền dùng chung cho mọi store

Spring Data JPA có lớp tiện ích `org.springframework.data.jpa.domain.AbstractAuditable`, giúp tránh tự viết một phần implementation. Đây là lớp thuộc module JPA, có metadata mapping và lớp cha theo mô hình JPA. [JPA API AbstractAuditable](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/domain/AbstractAuditable.html)

Không nhầm sự tồn tại của interface Commons với một cam kết rằng mọi lớp nền tiện ích mang tên tương tự đều phù hợp cho JDBC, MongoDB hoặc store khác.

Kế thừa một lớp nền còn sử dụng vị trí kế thừa duy nhất của class và đưa thêm quyết định về ID, thời gian hoặc mapping vào domain. Nếu không cần toàn bộ quyết định đó, annotation hoặc một implementation interface riêng có thể dễ kiểm soát hơn.

Tài liệu JPA cũng lưu ý lớp nền auditing làm tăng sự gắn kết với Spring Data và thường ưu tiên cách annotation vì ít can thiệp hơn. Khi dùng JPA, vẫn phải thiết lập auditing listener và cấu hình theo module, không sao chép nguyên cấu hình JDBC của bài. [Spring Data JPA: Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html)

## 11. Đổi từ annotation sang interface là thay đổi thiết kế

Có thể giữ nguyên các cột audit khi chuyển cách khai báo, nhưng không nên coi đây chỉ là thao tác thay cú pháp. Cần kiểm tra:

1. U và T của interface có biểu diễn đúng kiểu dữ liệu hiện tại không?
2. Các getter audit đã đổi từ giá trị trực tiếp sang Optional có ảnh hưởng caller không?
3. Các setter interface có thực sự cập nhật đúng field persistent không?
4. isNew có giữ đúng quyết định mới/cũ đối với ID hiện tại không?
5. Mapper còn dùng đúng field hoặc accessor sau khi thay hợp đồng không?
6. Cấu hình auditor và thời gian có tiếp tục được sử dụng không?
7. Dữ liệu cũ có field audit null có đọc và cập nhật đúng không?

Đổi ngược từ interface sang annotation cũng cần đánh giá lại chiến lược nhận biết entity mới vì entity có thể không còn triển khai Persistable. Đừng chỉ xóa các method rồi để repository tự đổi hành vi mà không kiểm tra.

Với API bên ngoài, nên dùng request/response DTO phù hợp để việc đổi Optional hoặc setter audit trong domain không vô tình trở thành thay đổi hợp đồng HTTP.

## 12. Kiểm chứng theo hành vi, không chỉ theo cách khai báo

Đối với hai model có cùng yêu cầu audit, nên có những kỳ vọng tương đương:

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Lưu entity mới | Metadata tạo được điền; metadata sửa theo cấu hình modifyOnCreate. |
| Đọc lại entity | Actor và thời gian được khôi phục đúng từ storage. |
| Sửa entity đã tồn tại | Metadata tạo giữ đúng; metadata sửa phản ánh nguồn hiện tại. |
| Lưu lần hai cùng entity | Không bị xử lý như insert chỉ vì isNew sai. |
| Không có auditor | Hành vi phù hợp chính sách nullable, actor hệ thống hoặc yêu cầu của ứng dụng. |
| Dữ liệu cũ thiếu audit | Không nhầm thiếu metadata với entity chưa từng tồn tại. |
| SQL hoặc thao tác ghi tùy biến | Xác nhận có đi qua auditing hay cần xử lý ở đường ghi riêng. |
| Nhiều nguồn auditor trong context | Chọn đúng bean đã cấu hình. |

Để kiểm thử thời gian ổn định, có thể cung cấp một Clock cố định cho DateTimeProvider trong môi trường test:

```java
Instant expectedTime = Instant.parse("2026-11-25T02:00:00Z");
Clock fixedClock = Clock.fixed(expectedTime, java.time.ZoneOffset.UTC);
DateTimeProvider fixedTimeProvider =
        () -> Optional.of(Instant.now(fixedClock));
```

Đây là mã minh họa nguồn thời gian. Test tích hợp còn phải nối đúng provider này với hạ tầng auditing, dùng schema phù hợp và so sánh theo độ chính xác timestamp thực tế của database.

Gọi trực tiếp `setCreatedDate()` rồi kiểm tra getter chỉ chứng minh setter lưu được giá trị. Nó chưa chứng minh repository gọi auditing hoặc mapper ghi metadata xuống storage. Đọc lại qua đường persistence là một bước kiểm chứng quan trọng.

## 13. Giữ đúng phạm vi abstraction của Commons

| Abstraction liên quan | Điểm cần chú ý |
| --- | --- |
| CRUD repository | Trạng thái mới/cũ và đường lưu quyết định auditing có được áp dụng đúng. |
| Derived query | Đọc dữ liệu hoặc trả projection không tự đồng nghĩa với cập nhật metadata sửa. |
| Phân trang và sắp xếp | Muốn sort theo lastModifiedDate thì field phải được lưu và module hỗ trợ truy vấn đó. |
| Projection | Chỉ công khai những metadata phù hợp với response; không biến projection thành nguồn quyết định auditor. |
| Query by Example | Chọn rõ audit field nào tham gia probe nếu store hỗ trợ; tránh vô tình lọc theo metadata không cần thiết. |
| Repository fragment | Đường ghi trực tiếp cần kiểm tra riêng conversion, lifecycle và audit metadata. |
| Reactive repository | Chọn hạ tầng auditor reactive và cấu hình tương ứng của module, không mặc định ThreadLocal đồng bộ luôn phù hợp. |

Việc model implement Auditable không mở rộng khả năng của store. Nó cung cấp hợp đồng metadata cho infrastructure có hỗ trợ; vẫn phải kiểm tra từng đường truy cập và cấu hình cụ thể.

## 14. Các lỗi dễ gặp và cách định vị

| Hiện tượng | Điểm cần xem lại |
| --- | --- |
| Có annotation nhưng mọi field vẫn null | Auditing đã được bật đúng module và đường lưu có đi qua infrastructure chưa? |
| Implement Auditable nhưng metadata không được giữ | Setter có cập nhật đúng field persistent không? |
| Có ngày giờ nhưng thiếu actor | Kiểu auditor, nguồn getCurrentAuditor và chính sách khi Optional.empty. |
| Lần sửa bị ghi như tạo mới | Implementation isNew và chiến lược ID. |
| Entity có UUID mới bị coi là đã tồn tại | Không dùng id-null như quy tắc mặc định cho ID gán trước. |
| Generic T không biên dịch với Date hoặc Long | Auditable yêu cầu T extends TemporalAccessor. |
| Field lưu kiểu Optional gây mapping khó hiểu | Phân biệt getter Optional với kiểu field persistence. |
| Metadata tạo bị request sửa được | Kiểm soát DTO và những field được cập nhật từ đầu vào. |
| Dùng AbstractAuditable ở module khác bị lệch mapping | Kiểm tra package và giả định JPA của lớp nền. |
| Đổi cách khai báo làm caller hoặc repository đổi hành vi | Kiểm tra Optional, setter, Persistable và isNew như một thay đổi hợp đồng. |

Chọn annotation khi cần khai báo metadata linh hoạt với ít yêu cầu lên API entity. Chọn Auditable khi muốn một hợp đồng mutable đầy đủ và chủ động quản lý những trách nhiệm đi kèm, đặc biệt là Persistable. Dù chọn cách nào, nguồn actor, nguồn thời gian và luồng persistence được module hỗ trợ mới làm metadata audit có ý nghĩa trong dữ liệu thực tế.