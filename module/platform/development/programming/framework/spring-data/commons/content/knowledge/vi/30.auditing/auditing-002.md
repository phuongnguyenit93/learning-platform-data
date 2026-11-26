# @CreatedBy, @LastModifiedBy, @CreatedDate và @LastModifiedDate

## 1. Auditing ghi lại metadata của lần tạo và sửa

Trong chương **Auditing** của **SPRING_DATA_COMMONS**, bốn annotation này mô tả hai nhóm metadata: ai thực hiện thao tác và thời điểm thao tác được hạ tầng auditing xử lý.

Một ghi chú được tạo bởi người dùng A, rồi được người dùng B cập nhật. Ứng dụng thường cần giữ người tạo và thời điểm tạo ban đầu, đồng thời cập nhật người sửa và thời điểm sửa gần nhất.

```text
Tạo:       người A, thời điểm t0
Cập nhật:  người B, thời điểm t1

Metadata sau cập nhật:
  createdBy        = A
  createdDate      = t0
  lastModifiedBy   = B
  lastModifiedDate = t1
```

Đây là hợp đồng cần đạt khi auditing được bật, nguồn dữ liệu phù hợp và thao tác đi qua pipeline mà module hỗ trợ. Chỉ thêm annotation lên field chưa làm mọi đường ghi tự có hành vi đó.

Bài này giúp bạn hiểu ý nghĩa từng annotation, cấu hình nguồn auditor và thời gian, hành vi khi tạo/cập nhật, cùng các điểm dễ nhầm về entity mới, dữ liệu đầu vào, transaction và lịch sử thay đổi.

## 2. Bốn annotation có vai trò gì?

Các annotation nằm trong package dùng chung:

```java
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
```

| Annotation | Câu hỏi được trả lời | Giá trị điển hình |
| --- | --- | --- |
| `@CreatedBy` | Ai được ghi nhận là người tạo entity? | ID người dùng, ID dịch vụ hoặc kiểu auditor của ứng dụng |
| `@LastModifiedBy` | Ai được ghi nhận ở lần sửa gần nhất? | Auditor hiện tại tại điểm auditing |
| `@CreatedDate` | Thời điểm tạo được auditing ghi nhận là khi nào? | Một giá trị thời gian được hỗ trợ, ví dụ `Instant` |
| `@LastModifiedDate` | Thời điểm sửa gần nhất được auditing ghi nhận là khi nào? | Giá trị thời gian của lần auditing tương ứng |

Tên field không bắt buộc giống tên annotation. Ví dụ `createdAt` vẫn có thể được gắn `@CreatedDate`. Điều quan trọng là metadata annotation, kiểu thuộc tính và cách module mapping nó vào store.

Trong ví dụ bài học, dùng tên `createdDate` và `lastModifiedDate` để dễ đối chiếu với annotation.

### 2.1. Hai nguồn dữ liệu độc lập

Các field `...By` lấy dữ liệu từ cơ chế cung cấp auditor. Các field `...Date` lấy dữ liệu từ cơ chế cung cấp thời gian.

```text
AuditorAware<T> hoặc ReactiveAuditorAware<T>
    -> createdBy / lastModifiedBy

DateTimeProvider
    -> createdDate / lastModifiedDate
```

Không có auditor không đồng nghĩa phải không có timestamp. Ngược lại, có một người dùng trong ngữ cảnh bảo mật không tự làm auditing điền timestamp nếu auditing chưa được bật hoặc cấu hình thời gian không cung cấp giá trị.

Nếu entity chỉ cần thời điểm tạo/sửa, không bắt buộc thêm hai field người dùng hoặc một auditor provider không cần thiết.

### 2.2. `By` là định danh actor theo thiết kế ứng dụng

Auditor có thể là một người dùng tương tác, một dịch vụ tích hợp hoặc một job hệ thống. Ví dụ:

```text
user:1042
service:catalog-import
system:nightly-reconciliation
```

Đây là quy ước ví dụ, không phải cú pháp bắt buộc của Spring Data. Nên chọn biểu diễn ổn định, có thể tra cứu và phù hợp với vòng đời tài khoản.

Một display name có thể thay đổi, còn một object chứa toàn bộ phiên đăng nhập thường mang nhiều dữ liệu hơn nhu cầu metadata. Hãy xác định rõ kiểu auditor muốn lưu trước khi viết provider.

## 3. Ví dụ entity có đủ bốn field

Ví dụ sau dùng mapping của **Spring Data MongoDB** để có một bối cảnh cụ thể. Bốn annotation auditing vẫn thuộc Commons.

```java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("notes")
public class Note {

    @Id
    private String id;

    private String title;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String lastModifiedBy;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedDate
    private Instant lastModifiedDate;

    public Note() {
    }

    public Note(String title) {
        this.title = title;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public String getLastModifiedBy() {
        return lastModifiedBy;
    }

    public Instant getCreatedDate() {
        return createdDate;
    }

    public Instant getLastModifiedDate() {
        return lastModifiedDate;
    }
}
```

Ví dụ dùng field access và không cung cấp public setter cho audit fields. Hạ tầng mapping/auditing phù hợp vẫn có thể ghi các field đó theo cơ chế truy cập của module.

Việc không có setter là một lựa chọn API Java, chưa phải ràng buộc bảo vệ dữ liệu ở mọi lớp. Mapper nhận request, custom code hoặc thao tác trực tiếp với store vẫn cần được thiết kế đúng phạm vi.

Với entity bất biến, phải kiểm tra khả năng tạo instance thay thế và truy cập thuộc tính của module. Không suy ra một ví dụ mutable có thể được chuyển nguyên sang mọi record hoặc constructor model mà không cần điều chỉnh.

## 4. Cấu hình một ví dụ auditing đồng bộ hoàn chỉnh về ý định

### 4.1. Nguồn actor của ứng dụng

Tách việc lấy actor thành một hợp đồng nhỏ:

```java
import java.util.Optional;

public interface CurrentActorProvider {

    Optional<String> currentActorId();
}
```

Implementation có thể lấy actor từ cơ chế xác thực hoặc ngữ cảnh job đã được ứng dụng thiết lập. Nó cần trả định danh đã được ứng dụng tin cậy, không chỉ lấy nguyên một field `createdBy` do client gửi.

### 4.2. Bật auditing trong MongoDB

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

@Configuration
@EnableMongoAuditing(
        auditorAwareRef = "currentAuditor",
        dateTimeProviderRef = "auditingDateTimeProvider",
        modifyOnCreate = true
)
class AuditingConfiguration {

    @Bean
    AuditorAware<String> currentAuditor(CurrentActorProvider actors) {
        return () -> actors.currentActorId()
                .filter(actorId -> !actorId.isBlank());
    }

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditingDateTimeProvider(Clock auditingClock) {
        return () -> Optional.of(Instant.now(auditingClock));
    }
}
```

Ứng dụng cần cung cấp implementation của `CurrentActorProvider`, kết nối MongoDB và cấu hình repository/template tương ứng. Các đoạn code không phải một ứng dụng độc lập đã có đầy đủ dependency và bootstrap.

`auditorAwareRef` và `dateTimeProviderRef` chọn rõ bean được auditing sử dụng. Điều này hữu ích khi container có nhiều nguồn dữ liệu cùng loại hoặc cần thay nguồn trong kiểm thử.

### 4.3. Ba lớp cấu hình phải khớp nhau

| Lớp | Điều cần khớp |
| --- | --- |
| Metadata entity | Annotation đúng và kiểu thuộc tính phù hợp |
| Nguồn dữ liệu | Auditor provider cùng kiểu với field; time provider tạo giá trị chuyển đổi được |
| Tích hợp store | Auditing đã bật và đường thao tác thực sự chạy callback/listener tương ứng |

Một provider đúng không bù được việc auditing chưa bật. Một annotation đúng cũng không bù được việc thao tác dùng driver trực tiếp và bỏ qua hạ tầng auditing.

## 5. Hành vi khi tạo và cập nhật

Giả sử cấu hình trong bài được sử dụng, actor và thời gian đều có giá trị, còn entity được nhận diện đúng theo giai đoạn vòng đời.

| Thao tác | `createdBy` | `createdDate` | `lastModifiedBy` | `lastModifiedDate` |
| --- | --- | --- | --- | --- |
| Tạo ở `t0`, actor A, `modifyOnCreate=true` | A | t0 | A | t0 |
| Sửa ở `t1`, actor B | Giữ A | Giữ t0 | B | t1 |
| Tạo với `modifyOnCreate=false` | Actor tạo | Thời điểm tạo | Không được auditing điền theo nhánh sửa khi tạo | Tương tự |

Dòng cuối nói về việc auditing gán giá trị, không khẳng định field chắc chắn null nếu ứng dụng hoặc database đã có giá trị khác.

### 5.1. Vì sao last-modified có thể được điền ngay lúc tạo?

Một entity mới đã có trạng thái hiện tại tại thời điểm tạo. Cấu hình `modifyOnCreate=true` cho phép auditing đồng thời ghi nhận metadata sửa gần nhất ngay trong lần tạo đó.

Nếu sản phẩm cần phân biệt “chưa bao giờ sửa sau khi tạo”, có thể xem xét `modifyOnCreate=false` ở module hỗ trợ. Khi ấy phải xác định rõ ý nghĩa null và cách API hiển thị nó.

Không dùng việc `lastModifiedDate` khác null như bằng chứng chắc chắn entity đã được sửa sau lần tạo nếu cấu hình đang điền metadata sửa ngay lúc tạo.

### 5.2. Ví dụ một vòng save

Repository minh họa:

```java
import org.springframework.data.repository.CrudRepository;

interface NoteRepository extends CrudRepository<Note, String> {
}
```

Lời gọi ở tầng ứng dụng:

```java
Note created = repository.save(new Note("Ghi chú ban đầu"));

created.setTitle("Ghi chú đã cập nhật");
Note updated = repository.save(created);
```

Giả sử ngữ cảnh actor được thiết lập là A ở lời gọi thứ nhất và B ở lời gọi thứ hai. Với thời gian lần lượt là `t0`, `t1`, kết quả mong đợi khớp bảng trên.

Nên sử dụng entity do save trả về khi cần ID hoặc metadata sau persistence. Module có thể tạo hoặc trả một instance khác, đặc biệt với mô hình bất biến.

### 5.3. Last-modified không đo mức thay đổi nghiệp vụ

Auditing điền metadata khi điểm vòng đời liên quan được thực thi. Nó không tự so sánh mọi field để quyết định nội dung có thay đổi “đáng kể” theo nghiệp vụ hay không.

Một số module/provider chỉ phát sinh update trong những điều kiện nhất định; một đường save khác có thể gọi auditing dù giá trị nghiệp vụ không đổi. Không suy ra hành vi của mọi store chỉ từ tên phương thức `save`.

Nếu cần thời điểm thay đổi trạng thái cụ thể, chẳng hạn `approvedAt`, hãy mô hình hóa sự kiện/trạng thái đó riêng thay vì dùng `lastModifiedDate` để thay thế.

## 6. `AuditorAware<T>` và kiểu dữ liệu của hai field `By`

`AuditorAware<T>` cung cấp auditor hiện tại bằng:

```java
Optional<T> getCurrentAuditor();
```

Trong ví dụ, `T` là `String`, phù hợp với `createdBy` và `lastModifiedBy`.

Nếu ứng dụng chọn một kiểu khác như ID có kiểu riêng hoặc một đối tượng người dùng, field và mapping của module phải hỗ trợ cách biểu diễn đó. Không mặc định một object principal của framework bảo mật có thể được lưu trực tiếp vào mọi store.

### 6.1. Khi provider trả `Optional.empty()`

Một auditor rỗng có nghĩa nguồn không cung cấp actor để auditing gán ở lần xử lý đó. Điều này không tự có nghĩa:

- Thao tác bị từ chối.
- Actor mặc định là `anonymous` hoặc `system`.
- Những field `By` đang có sẽ bị xóa.
- Hai field thời gian cũng không được xử lý.

Trong hạ tầng auditing, không có auditor thường dẫn đến không thực hiện phép gán auditor tương ứng. Nếu cần bắt buộc actor cho mọi thao tác ghi, ứng dụng phải quy định và kiểm tra điều kiện đó rõ ràng.

### 6.2. Tác vụ hệ thống cần một chính sách actor

Có thể chọn một actor hệ thống ổn định cho job được xác định, hoặc từ chối thao tác khi job chưa thiết lập actor. Quyết định đó thuộc hợp đồng của ứng dụng.

Không nên tự gán actor hệ thống cho mọi trường hợp không có người dùng nếu điều đó che mất lỗi truyền ngữ cảnh. Một job hợp lệ và một request bị mất authentication là hai tình huống khác nhau cần được xử lý có chủ đích.

### 6.3. Auditing không thay thế kiểm tra quyền

Ghi nhận `lastModifiedBy = user:1042` mô tả actor được hạ tầng cung cấp. Nó không tự kiểm tra người đó có quyền sửa ghi chú hay không.

Phân quyền cần được thực hiện tại lớp phù hợp. Đồng thời, actor đưa vào provider phải có nguồn đáng tin cậy để metadata có ý nghĩa.

## 7. Nguồn thời gian và lựa chọn kiểu timestamp

`DateTimeProvider` cung cấp thời gian hiện tại theo hợp đồng:

```java
Optional<TemporalAccessor> getNow();
```

Ví dụ trong bài trả `Instant` lấy từ `Clock`. Cách này làm nguồn thời gian tường minh và dễ cố định trong kiểm thử.

### 7.1. Vì sao chọn `Instant` trong ví dụ?

`Instant` biểu diễn một thời điểm trên dòng thời gian. Nó phù hợp khi cần so sánh các thao tác diễn ra ở nhiều máy hoặc hiển thị thời gian theo múi giờ của người đọc sau này.

`LocalDateTime` không tự chứa offset hoặc múi giờ. Nếu dùng kiểu đó, ứng dụng cần một quy ước rõ về cách diễn giải và chuyển đổi, nhất là khi dữ liệu được chia sẻ giữa nhiều vùng triển khai.

Spring Data auditing có hỗ trợ nhiều kiểu thời gian theo hạ tầng chuyển đổi, nhưng tập kiểu lưu được và độ chính xác cuối cùng còn phụ thuộc module, driver và schema. Không suy ra mọi `TemporalAccessor` đều có thể gắn vào field rồi lưu trực tiếp ở mọi store.

### 7.2. Độ chính xác có thể thay đổi khi lưu

Ví dụ MongoDB sử dụng BSON date với độ chính xác mili giây. Một `Instant` có phần nano giây có thể không được đọc lại nguyên vẹn ở độ chính xác đó qua mapping thời gian thông thường.

Vì vậy, khi kiểm tra, phải tính đến độ chính xác của biểu diễn store. Không kết luận auditing sai chỉ vì timestamp đọc lại khác phần nhỏ hơn độ chính xác mà store lưu.

Với cơ sở dữ liệu quan hệ, kiểu cột và precision cũng cần được kiểm tra tương ứng.

### 7.3. Thời gian auditing không tự là thời điểm commit

Timestamp được lấy khi auditing chạy trong pipeline. Transaction có thể commit sau đó hoặc rollback.

Nó cũng không tự là thời gian của database server. Nếu ứng dụng muốn database cấp timestamp bằng default/trigger, cần xác định bên nào sở hữu giá trị và cách đọc lại kết quả.

Không cấu hình hai nguồn cùng ghi một field rồi dựa vào thứ tự tình cờ giữa application auditing và database trigger.

### 7.4. Khi time provider không trả giá trị

Nếu `DateTimeProvider` không cung cấp thời gian, không thể mặc định các field ngày sẽ được điền bằng một fallback khác. Cần kiểm tra cấu hình và hợp đồng của provider.

Một cấu hình cũng có thể tắt việc gán ngày thông qua tùy chọn mà module hỗ trợ. Khi xử lý sự cố, kiểm tra cả bật auditing lẫn cấu hình nguồn thời gian và tùy chọn liên quan.

## 8. Entity mới được xác định như thế nào?

Hai nhóm metadata tạo/sửa cần một quyết định vòng đời phù hợp. Cách hạ tầng quyết định phụ thuộc module: có module dùng metadata nhận diện entity mới, có module dựa vào listener/giai đoạn persistence của provider.

Các yếu tố có thể liên quan gồm ID, version, `Persistable.isNew()` khi được hỗ trợ và cơ chế persistence cụ thể.

### 8.1. ID do ứng dụng gán trước có thể làm thay đổi nhận diện

Giả sử ứng dụng tạo object mới và gán ID ngay từ constructor. Không được mặc định mọi module vẫn coi nó là mới chỉ vì object vừa được `new` trong Java.

Nếu metadata nhận diện nó là entity đã tồn tại, auditing có thể đi vào nhánh sửa. Khi đó created metadata không được điền như bạn kỳ vọng.

Cần kiểm tra chiến lược entity mới của module và thiết kế ID/version/`Persistable` theo đúng hợp đồng. Không sửa bằng cách tự gán lại `createdDate` trong mọi save, vì việc đó có thể phá thời điểm tạo thật của entity cũ.

### 8.2. `@CreatedDate` không phải cơ chế hỏi database có bản ghi hay chưa

Annotation đánh dấu metadata, không tự thực hiện một truy vấn tồn tại cho mỗi entity. Đừng coi nó là giải pháp chung cho upsert, import dữ liệu hoặc merge object tách rời.

Với luồng nhập dữ liệu có cả insert và update, cần định nghĩa rõ cách phân biệt và cách giữ metadata tạo ban đầu.

### 8.3. Version phục vụ concurrency là một hợp đồng riêng

Một field version có thể tham gia nhận diện entity mới hoặc optimistic locking tùy module. Nhưng `lastModifiedDate` không tự thay thế version.

Hai thao tác có thể có timestamp trùng độ chính xác lưu trữ, hoặc đồng hồ ứng dụng không có thứ tự tuyệt đối. Nếu cần phát hiện ghi đè đồng thời, sử dụng cơ chế concurrency được store/module hỗ trợ.

## 9. Giữ metadata tạo khi cập nhật từ request

Auditing không tự làm các field trở thành bất biến trước mọi kiểu ghi dữ liệu.

Một lỗi phổ biến:

```text
Bản ghi cũ có createdBy và createdDate
    -> client gửi request chỉ có title
    -> ứng dụng tạo một object thay thế với ID cũ
    -> created metadata trên object thay thế là null
    -> nhánh sửa không tự khôi phục created metadata
    -> thao tác ghi có thể làm mất dữ liệu tạo ban đầu
```

Hệ quả cụ thể phụ thuộc cách module ghi/merge dữ liệu. Điều cần tránh là giả định `@CreatedBy` hoặc `@CreatedDate` tự truy vấn và bảo vệ giá trị cũ trong mọi tình huống.

### Cách tổ chức update rõ ràng

1. Request DTO chỉ nhận những field nghiệp vụ được phép sửa.
2. Tải entity hiện có khi luồng cập nhật cần bảo toàn trạng thái của nó.
3. Thay đổi những field nghiệp vụ theo hợp đồng.
4. Lưu entity qua đường auditing đã cấu hình.
5. Kiểm tra metadata tạo vẫn giữ nguyên và metadata sửa được cập nhật.

Nếu dùng update trực tiếp hoặc patch theo query, thiết kế riêng cách giữ/gán audit metadata vì đường đó có thể không chạy cùng pipeline entity.

Field auditing cũng không tự là field chỉ đọc ở tầng HTTP/JSON. DTO, mapper và API contract phải thể hiện quyền sở hữu metadata phù hợp.

## 10. Khác biệt giữa các module store

Các annotation thuộc Commons, còn bật auditing và thời điểm thực hiện là tích hợp của module.

| Bối cảnh | Điểm cần kiểm tra |
| --- | --- |
| MongoDB đồng bộ | `@EnableMongoAuditing`, auditor provider và callback mapping tương ứng |
| MongoDB reactive | Cơ chế reactive auditing và `ReactiveAuditorAware` phù hợp |
| JPA | `@EnableJpaAuditing`, auditing entity listener và cấu hình/dependency của JPA provider |
| JDBC/R2DBC | Cơ chế bật auditing và callback phù hợp của module; phân biệt đồng bộ/reactive |
| Store khác | Tài liệu và API auditing cụ thể của module/phiên bản |

Riêng JPA, có các entity listener như `AuditingEntityListener` tham gia vòng đời entity. Không lấy một cấu hình MongoDB rồi kỳ vọng annotation bật auditing đó điều khiển các entity JPA.

### 10.1. Đường ghi ảnh hưởng việc auditing có chạy không

| Đường thao tác | Câu hỏi cần xác nhận |
| --- | --- |
| Repository/template save entity | Có đi qua callback/listener auditing không? |
| Dirty checking và flush của JPA | Provider có kích hoạt giai đoạn listener phù hợp không? |
| Update theo query hoặc bulk update | Có bỏ qua vòng đời entity thông thường không? |
| Driver trực tiếp | Có dùng hạ tầng auditing của Spring Data không? |
| Import/migration | Metadata được bảo toàn hay tạo mới theo chính sách nào? |

Không giả định mọi update được tự điền audit fields chỉ vì entity có annotation. Query update và bulk operation thường cần đánh giá riêng theo module.

### 10.2. Một quy tắc dùng chung không đồng nghĩa cùng một hook

Về nghiệp vụ, các module có thể cùng cần giữ người tạo và cập nhật người sửa. Về kỹ thuật, chúng có thể dùng listener, callback và metadata khác nhau.

Khi chuyển store hoặc đổi API đồng bộ sang reactive, kiểm tra lại cấu hình, nguồn actor, thời gian và đường thao tác thực tế thay vì chỉ giữ nguyên bốn field.

## 11. Auditing reactive và nguồn actor

Trong stack reactive, nguồn actor có thể cần được lấy khi chuỗi được subscribe và theo context của chuỗi. Abstraction dùng chung là:

```java
import org.springframework.data.domain.ReactiveAuditorAware;
```

Ví dụ một bean cung cấp auditor từ Reactor Context:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.data.domain.ReactiveAuditorAware;

import reactor.core.publisher.Mono;

@Bean
ReactiveAuditorAware<String> reactiveAuditorAware() {
    return () -> Mono.deferContextual(contextView ->
            Mono.justOrEmpty(contextView.<String>getOrEmpty("actorId"))
                    .filter(actorId -> !actorId.isBlank()));
}
```

Đây là phương thức bean đặt trong một lớp cấu hình phù hợp. Key `actorId` là quy ước của ví dụ; phía ứng dụng phải cung cấp giá trị đã xác thực vào context. Spring Data không tự tạo key này.

Trong MongoDB reactive, dùng cấu hình bật reactive auditing phù hợp, chẳng hạn `@EnableReactiveMongoAuditing`, và chọn bean auditor tương ứng. Đây là phương án cho pipeline reactive, không phải lý do để áp dụng cả hai cấu hình mà không xác định đường sử dụng.

Một publisher auditor rỗng không tự tạo actor hệ thống. Nếu yêu cầu actor bắt buộc, cần chính sách lỗi rõ ràng.

Không gọi `block()` chỉ để lấy actor reactive rồi đưa vào `AuditorAware` đồng bộ. Cách đó có thể chặn luồng và làm mất ý nghĩa phạm vi context. Đồng thời, không mặc định một `ThreadLocal` từ request còn mang đúng actor sau mọi điểm chuyển thread.

## 12. Auditing hiện tại khác lịch sử thay đổi

Bốn field thường nằm trên bản ghi hiện tại. Mỗi lần sửa có thể ghi đè giá trị last-modified của lần trước.

```text
A tạo
B sửa
C sửa

Bản ghi hiện tại thường chỉ còn:
  createdBy = A
  lastModifiedBy = C
```

Thông tin “B từng sửa field nào” không còn đầy đủ trong bốn field này.

| Nhu cầu | Bốn annotation có tự cung cấp đầy đủ không? |
| --- | --- |
| Người tạo và thời điểm tạo | Có thể cung cấp qua auditing đã cấu hình |
| Người sửa và thời điểm sửa gần nhất | Có thể cung cấp qua auditing đã cấu hình |
| Mọi phiên bản cũ của entity | Không |
| Giá trị trước/sau của từng field | Không |
| Lý do nghiệp vụ của thay đổi | Không |
| Người xóa và thời điểm xóa | Không được diễn đạt chỉ bằng bốn annotation này |
| Bảo đảm chống sửa metadata ngoài ứng dụng | Không |

Nếu cần lịch sử, xem xét cơ chế revision, audit event hoặc change log theo yêu cầu và khả năng store. Nếu cần soft delete, mô hình `deletedBy`/`deletedDate` và đường xử lý phải được thiết kế riêng.

Metadata auditing cũng không tự chứng minh transaction đã commit. Trong một thao tác rollback, object trong bộ nhớ có thể đã được điền metadata, trong khi dữ liệu cuối cùng của database không có thay đổi đó.

## 13. Kiểm chứng bằng nguồn actor và clock kiểm soát được

Các tình huống sau là hướng dẫn triển khai; bài học không báo cáo kết quả đã chạy trên một database cụ thể.

### 13.1. Cố định thời gian để có kỳ vọng rõ ràng

Trong kiểm thử, có thể dùng:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-10T03:00:00Z"),
        java.time.ZoneOffset.UTC
);
```

Đưa clock này vào `DateTimeProvider` mà auditing thực sự sử dụng. Chỉ tạo một clock trong test nhưng provider vẫn gọi nguồn thời gian khác thì không kiểm soát được timestamp.

Khi kiểm tra lần sửa, dùng một thời điểm khác thay vì chờ bằng sleep. Đồng thời kiểm tra theo precision mà store lưu được.

### 13.2. Ma trận hành vi cốt lõi

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Tạo với actor A tại t0, modify-on-create bật | Bốn field được điền đúng |
| Sửa với actor B tại t1 | Created metadata giữ nguyên; modified metadata đổi |
| Tạo với modify-on-create tắt | Nhánh metadata sửa khi tạo không tự gán |
| Chỉ dùng annotation thời gian | Timestamp hoạt động mà không cần auditor field |
| Provider không có auditor | Hành vi đúng chính sách; không tự phát sinh actor khác |
| Entity gán ID trước | Nhận diện mới/cũ đúng với thiết kế |
| Update từ DTO | Created metadata không bị mất hoặc bị client thay thế |
| Đọc lại sau save | Metadata đã được lưu thật, không chỉ có trong object |
| Update/bulk được ứng dụng sử dụng | Đã biết có auditing hay cần gán riêng |
| Reactive đổi ngữ cảnh actor | Không lẫn actor giữa các subscription |

### 13.3. Kiểm tra tích hợp quan trọng hơn chỉ kiểm tra provider

Một test `AuditorAware` trả đúng chuỗi chưa xác nhận:

- Auditing đã được bật.
- Provider đó được chọn trong container.
- Entity được nhận diện đúng theo vòng đời.
- Callback/listener được thực thi.
- Field được mapping và lưu vào store.

Cần ít nhất một kịch bản đi qua đúng repository/template/provider mà ứng dụng sử dụng, rồi đọc lại dữ liệu để xác nhận.

Với JPA, cần xét thời điểm flush và vòng đời persistence context. Với reactive, phải subscribe và chờ tín hiệu kết thúc để kiểm tra thao tác thật. Các chi tiết này phải theo module đang triển khai.

## 14. Lỗi thường gặp và cách khoanh vùng

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Cả bốn field không được điền | Chưa bật auditing hoặc đường ghi bỏ qua hạ tầng | Xác định cấu hình và pipeline persistence |
| Date có giá trị nhưng By rỗng | Auditor không có giá trị, sai bean hoặc sai kiểu | Kiểm tra provider và generic field |
| By đúng nhưng Date không được điền | Cấu hình thời gian/tùy chọn gán ngày không phù hợp | Kiểm tra time provider và kiểu thời gian |
| Last-modified có ngay lúc tạo | `modifyOnCreate` đang bật | Đối chiếu ý nghĩa sản phẩm mong muốn |
| Created metadata rỗng với ID tự gán | Nhận diện entity mới khác kỳ vọng | Kiểm tra chiến lược ID/version/isNew của module |
| Created metadata mất sau update | Object thay thế không giữ dữ liệu tạo | Điều chỉnh DTO/mapping và cách update |
| Actor sai khi chạy reactive | Nguồn context không phù hợp hoặc bị dùng lại sai phạm vi | Kiểm tra subscription và propagation |
| Bulk update không đổi timestamp | Không chạy vòng đời entity như save | Thiết kế metadata cho đường bulk đó |
| Timestamp lệch phần nano giây | Store/driver giảm precision | Kiểm tra biểu diễn lưu trữ và kỳ vọng test |
| Auditing xung đột custom callback | Hai cơ chế cùng sửa field, thứ tự chưa rõ | Xác định bên sở hữu và thứ tự hợp lệ |
| Cần lịch sử nhưng chỉ thấy người sửa cuối | Bốn field chỉ giữ trạng thái metadata hiện tại | Thiết kế revision/change log riêng |

Khi xử lý lỗi, tách các bước: tìm metadata annotation, xác định nhánh tạo/sửa, lấy actor/thời gian, thực thi vòng đời và lưu dữ liệu. Không mặc định mọi trường rỗng đều do annotation sai.

## 15. Tự kiểm tra mức hiểu

**`@CreatedBy` có bắt buộc lưu một object người dùng không?**

Không. Kiểu auditor do ứng dụng chọn; ví dụ dùng `String`. Provider, field và mapping phải tương thích.

**Nếu chỉ cần `@CreatedDate` và `@LastModifiedDate`, có bắt buộc dùng `AuditorAware` không?**

Không. Nguồn auditor dành cho các field người tạo/sửa; các field thời gian dùng nguồn thời gian riêng.

**`Optional.empty()` từ auditor provider có tự từ chối save không?**

Không phải hành vi mặc định có thể suy ra. Nếu actor là bắt buộc, ứng dụng cần quy định rõ việc từ chối.

**Last-modified có giá trị ngay lúc tạo có phải lỗi không?**

Không. Điều đó phù hợp với cấu hình điền metadata sửa khi tạo. Cần xem `modifyOnCreate` và hợp đồng mong muốn.

**Vì sao `@CreatedDate` không bảo vệ được dữ liệu cũ khi ứng dụng tạo object thay thế bị thiếu field?**

Vì annotation đánh dấu việc auditing, không tự khôi phục mọi field từ database hay áp đặt bất biến cho tất cả kiểu update.

**Có thể dùng `lastModifiedDate` làm thay optimistic locking không?**

Không nên đồng nhất hai cơ chế. Timestamp có precision và nguồn thời gian riêng; concurrency cần hợp đồng version/điều kiện cập nhật phù hợp.

**Bốn annotation có lưu được toàn bộ lịch sử ai sửa gì không?**

Không. Chúng thường lưu metadata tạo và sửa gần nhất trên bản ghi hiện tại; lịch sử cần cơ chế khác.

## 16. Nguyên tắc áp dụng

Bắt đầu bằng ý nghĩa của bốn field và nguồn dữ liệu mà ứng dụng tin cậy. Chọn kiểu auditor ổn định, nguồn thời gian tường minh và cấu hình bật auditing của đúng module.

Sau đó xác nhận nhánh tạo/sửa, hành vi modify-on-create, khả năng bảo toàn created metadata và những đường update có thể bỏ qua vòng đời entity. Với reactive hoặc transaction, kiểm tra thêm phạm vi context và thời điểm dữ liệu thực sự được commit.

Một tích hợp đúng cần thống nhất **annotation, nguồn auditor/thời gian, điểm vòng đời và biểu diễn dữ liệu trong store**. Khi các phần đó được kiểm chứng cùng nhau, metadata auditing mới phản ánh đúng hợp đồng ứng dụng đã chọn.