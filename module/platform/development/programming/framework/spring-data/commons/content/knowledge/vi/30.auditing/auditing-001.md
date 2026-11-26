# Thông tin ai tạo/sửa và thời điểm tạo/sửa entity

## 1. Auditing trả lời những câu hỏi nào?

Trong một ứng dụng quản lý dữ liệu, ngoài nội dung nghiệp vụ như tiêu đề ghi chú hoặc trạng thái đơn hàng, thường cần biết:

- Ai tạo entity?
- Entity được tạo vào thời điểm nào?
- Ai thực hiện lần sửa gần nhất?
- Lần sửa gần nhất xảy ra khi nào?

Spring Data cung cấp auditing để điền các metadata này trong những đường persistence có tích hợp tương ứng. Domain khai báo những thuộc tính cần theo dõi; ứng dụng cấu hình nguồn người thực hiện, nguồn thời gian và bật hạ tầng của store.

Bài học thuộc chương **Auditing** của module `SPRING_DATA_COMMONS`. Các annotation và SPI dùng chung giúp mô tả nhu cầu, nhưng việc kích hoạt và checkpoint đọc/ghi phụ thuộc module như MongoDB, JPA hoặc Relational. Không thể chỉ thêm annotation rồi giả định mọi đường ghi đều tự cập nhật metadata.

Theo tài liệu Commons, có thể khai báo metadata bằng annotation hoặc interface, và phải bật auditing để đăng ký hạ tầng cần thiết. [Spring Data Commons Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html).

## 2. Bốn thuộc tính thường gặp

| Annotation | Thuộc tính minh họa | Ý nghĩa |
| --- | --- | --- |
| `@CreatedBy` | `createdBy` | Người hoặc tác nhân được ghi nhận khi tạo entity |
| `@CreatedDate` | `createdAt` | Mốc thời gian được ghi nhận khi tạo entity |
| `@LastModifiedBy` | `lastModifiedBy` | Người hoặc tác nhân của lần sửa gần nhất được auditing xử lý |
| `@LastModifiedDate` | `lastModifiedAt` | Mốc thời gian của lần sửa gần nhất được auditing xử lý |

Các annotation nằm trong package:

```java
org.springframework.data.annotation.CreatedBy
org.springframework.data.annotation.CreatedDate
org.springframework.data.annotation.LastModifiedBy
org.springframework.data.annotation.LastModifiedDate
```

Tên field không bắt buộc phải giống tên annotation. Ví dụ, `createdAt` vẫn biểu diễn thời điểm tạo nếu được gắn `@CreatedDate`.

Có thể chọn chỉ theo dõi một phần thông tin. Nếu ứng dụng chỉ cần ngày tạo và ngày sửa, không bắt buộc cung cấp auditor để lấy danh tính. Ngược lại, nếu dùng hai annotation về người thực hiện, cần nguồn cung cấp auditor phù hợp với kiểu dữ liệu đã khai báo.

### 2.1. Diễn biến dữ liệu khi tạo rồi cập nhật

Giả sử hệ thống coi lần tạo cũng là lần sửa đầu tiên:

| Thao tác | `createdBy` | `createdAt` | `lastModifiedBy` | `lastModifiedAt` |
| --- | --- | --- | --- | --- |
| `user-101` tạo ghi chú tại `t0` | `user-101` | `t0` | `user-101` | `t0` |
| `user-202` sửa ghi chú tại `t1` | Giữ `user-101` | Giữ `t0` | `user-202` | `t1` |
| `user-303` sửa tiếp tại `t2` | Giữ `user-101` | Giữ `t0` | `user-303` | `t2` |

Bảng minh họa yêu cầu khi auditor thay đổi theo từng thao tác và entity được nhận diện đúng là mới hoặc đã tồn tại. Nó không có nghĩa Spring Data tự biết các mã người dùng này nếu ứng dụng chưa cung cấp chúng.

Sau lần sửa thứ hai, bốn field không còn chứa riêng thông tin `user-202` tại `t1`. Nếu cần đầy đủ mọi phiên bản, nội dung trước/sau hoặc lý do thay đổi, phải có cơ chế lưu lịch sử bổ sung.

## 3. Cơ chế gồm những phần nào?

Một đường auditing có thể được hình dung như sau:

```text
Ứng dụng tạo hoặc thay đổi entity
  -> gọi đường persistence có hỗ trợ
  -> hạ tầng xác định tạo mới hay cập nhật
  -> lấy auditor từ nguồn danh tính
  -> lấy thời gian từ nguồn thời gian
  -> điền các thuộc tính auditing phù hợp
  -> mapper/provider thực hiện persistence
```

Đây là sơ đồ trách nhiệm, không mô tả một thứ tự callback cố định cho mọi store.

| Thành phần | Trách nhiệm |
| --- | --- |
| Entity và auditing metadata | Cho biết thuộc tính nào cần được điền |
| `AuditorAware<T>` | Cung cấp người hoặc tác nhân hiện tại cho hạ tầng đồng bộ |
| `ReactiveAuditorAware<T>` | Cung cấp auditor trong reactive flow |
| `DateTimeProvider` | Cung cấp thời gian dùng cho auditing |
| Hạ tầng của module store | Gắn auditing vào vòng đời persistence |
| Cơ chế nhận diện entity mới | Giúp chọn ghi metadata tạo hay sửa trong đường có sử dụng chiến lược này |

Ví dụ MongoDB triển khai auditing bằng `AuditingEntityCallback`, một `BeforeConvertCallback`, để điền metadata vào entity trước bước chuyển đổi. [AuditingEntityCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/AuditingEntityCallback.html).

Vì vậy, tạo một object bằng `new` chưa có nghĩa các field đã được điền. Metadata được xử lý khi object đi qua checkpoint tương ứng của hạ tầng đã cấu hình.

## 4. Chọn kiểu dữ liệu cho người thực hiện và thời gian

### 4.1. Người thực hiện là một khái niệm của ứng dụng

Ví dụ trong bài lưu auditor bằng `String` chứa mã định danh ổn định:

```java
@CreatedBy
private String createdBy;

@LastModifiedBy
private String lastModifiedBy;
```

Khi đó provider cần cung cấp kiểu tương ứng:

```java
AuditorAware<String>
```

`T` trong `AuditorAware<T>` là kiểu của auditor, không phải kiểu ID của entity đang được lưu. Một entity có ID `Long` vẫn có thể lưu `createdBy` dạng String nếu đó là thiết kế danh tính của ứng dụng.

Có thể sử dụng UUID hoặc một kiểu người dùng khác nếu module mapping hỗ trợ. Nếu lưu cả đối tượng người dùng thay vì mã tham chiếu, phải làm rõ quan hệ, cách ánh xạ và việc đọc dữ liệu ở store đó; không giả định mọi module xử lý giống JPA relationship.

Mã định danh ổn định và tên hiển thị cũng có ý nghĩa khác nhau. Nếu lưu một tên có thể đổi, bản ghi cũ có thể không còn cho biết rõ tài khoản nào đã thực hiện thao tác. Nếu cần cả tên tại thời điểm thao tác, thiết kế snapshot riêng thay vì nhầm nó với identity của auditor.

### 4.2. Ví dụ chọn Instant cho mốc thời gian

```java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant lastModifiedAt;
```

`Instant` biểu diễn một mốc trên trục thời gian. Khi hiển thị cho người dùng, có thể chuyển mốc đó sang múi giờ cần thiết, thay vì lưu một chuỗi đã định dạng theo giao diện.

Ví dụ:

```text
Mốc lưu/trao đổi: 2026-11-25T02:00:00Z
Hiển thị tại UTC+07:00: 09:00 ngày 25/11/2026
```

Việc chọn kiểu còn phải phù hợp với converter, provider và độ chính xác store hỗ trợ. Không dùng giả định độ chính xác nanosecond của Java để khẳng định database luôn giữ nguyên mọi chữ số sau giây.

## 5. Ví dụ entity đầy đủ với MongoDB

Ví dụ sau dùng một ghi chú có title là dữ liệu nghiệp vụ. ID/version phục vụ persistence, còn bốn field audit do hạ tầng điền.

```java
import java.time.Instant;
import java.util.Objects;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("notes")
public class Note {

    @Id
    private String id;

    @Version
    private Long version;

    private String title;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedAt;

    public Note() {
    }

    public Note(String title) {
        rename(title);
    }

    public void rename(String newTitle) {
        Objects.requireNonNull(newTitle, "Title is required");
        if (newTitle.isBlank()) {
            throw new IllegalArgumentException("Title must not be blank");
        }
        this.title = newTitle;
    }

    public String getId() { return id; }
    public Long getVersion() { return version; }
    public String getTitle() { return title; }
    public String getCreatedBy() { return createdBy; }
    public Instant getCreatedAt() { return createdAt; }
    public String getLastModifiedBy() { return lastModifiedBy; }
    public Instant getLastModifiedAt() { return lastModifiedAt; }
}
```

Lớp không cung cấp thao tác nghiệp vụ để tự đổi người tạo hoặc thời điểm tạo. Tuy nhiên, việc không có setter không phải một cơ chế bảo vệ mọi đường ghi dữ liệu. API cần nhận DTO phù hợp và chỉ áp dụng những thay đổi nghiệp vụ được phép.

Entity dùng kiểu `Long` nullable cho version. Ví dụ không tự khởi tạo version; để hạ tầng của store quản lý. Các thuộc tính auditing cũng không được điền sẵn bằng giá trị tùy ý trong constructor.

Repository:

```java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface NoteRepository extends MongoRepository<Note, String> {
}
```

Các đoạn mã này thuộc một ứng dụng MongoDB đã có kết nối và cấu hình repository phù hợp. Annotation mapping MongoDB không được dùng thay cho `@Entity` của một ứng dụng JPA.

## 6. Bật auditing và cung cấp hai nguồn dữ liệu

### 6.1. Cấu hình chạy thử với auditor cố định

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

@Configuration(proxyBeanMethods = false)
@EnableMongoAuditing(
        auditorAwareRef = "currentAuditor",
        dateTimeProviderRef = "auditTimeProvider",
        modifyOnCreate = true)
public class NoteAuditingConfiguration {

    @Bean
    AuditorAware<String> currentAuditor() {
        return () -> Optional.of("demo-user");
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

`demo-user` chỉ phục vụ quan sát cơ chế: mọi thao tác trong cấu hình này đều nhận cùng một auditor. Cấu hình đó không nhận diện người đăng nhập. Khi tích hợp nguồn danh tính thật, thay implementation provider bằng nguồn được ứng dụng quản lý.

Hai tham chiếu bean được khai báo tường minh để biết provider nào được dùng. Với nhiều bean auditor, không để việc lựa chọn trở nên mơ hồ. Cấu hình MongoDB hỗ trợ `@EnableMongoAuditing` và lựa chọn provider bằng `auditorAwareRef`. [MongoDB Auditing](https://docs.spring.io/spring-data/mongodb/reference/mongodb/auditing.html).

### 6.2. Vai trò của AuditorAware

Hợp đồng cốt lõi:

```java
Optional<T> getCurrentAuditor();
```

Auditor có thể là một người dùng, tài khoản dịch vụ hoặc tác nhân chạy job. Spring Data gọi provider để lấy giá trị; nó không tự suy ra actor từ tên thread, địa chỉ IP hoặc một field trong request. [AuditorAware](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AuditorAware.html).

Một cách tách nguồn danh tính của ứng dụng:

```java
import java.util.Optional;

public interface ActorSource {
    Optional<String> currentActorId();
}
```

Sau đó thay bean `currentAuditor` của ví dụ bằng:

```java
@Bean
AuditorAware<String> currentAuditor(ActorSource actorSource) {
    return actorSource::currentActorId;
}
```

`ActorSource` ở đây do ứng dụng định nghĩa, không phải interface của Spring Data. Implementation có thể đọc danh tính đã xác thực hoặc context được thiết lập cho một job. Ứng dụng phải đăng ký implementation tương ứng trước khi dùng cấu hình này.

Không trả null thay cho `Optional`. Nếu không biết auditor, `Optional.empty()` diễn đạt việc không có giá trị auditor mới được cung cấp. Nó không tự gán `system`, không tự từ chối thao tác lưu và không phải lệnh xóa một người sửa cũ.

Nếu nghiệp vụ bắt buộc xác định người thực hiện, hãy kiểm tra điều kiện đó trong hợp đồng xử lý của ứng dụng thay vì coi việc thiếu auditor là một cơ chế kiểm soát truy cập.

### 6.3. Vai trò của DateTimeProvider

`DateTimeProvider` trả `Optional<TemporalAccessor>` để cung cấp mốc dùng cho ngày tạo/sửa. Trong ví dụ, nguồn là `Instant.now(auditClock)`. [DateTimeProvider](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/auditing/DateTimeProvider.html).

Tách `Clock` thành dependency cho phép kiểm soát thời gian khi thực hành hoặc kiểm thử. Ví dụ tạo một clock cố định:

```java
Clock fixed = Clock.fixed(
        Instant.parse("2026-11-25T02:00:00Z"),
        java.time.ZoneOffset.UTC);
```

Để dùng clock đó trong kiểm chứng tích hợp, phải nối nó vào `DateTimeProvider` đang được auditing sử dụng. Tạo một biến local `fixed` không tự thay đổi clock của application context.

## 7. Quan sát lần tạo và lần sửa

### 7.1. Tạo mới

```java
Note draft = new Note("Tìm hiểu Spring Data auditing");
Note saved = repository.save(draft);
```

Khi cấu hình demo ở mục 6 được sử dụng và entity đi qua đường lưu có auditing, các field về người thực hiện nhận `demo-user`; các field thời gian được điền từ provider.

`modifyOnCreate = true` diễn đạt việc tạo mới cũng được đánh dấu là lần sửa đầu tiên. Trong `@EnableMongoAuditing`, `modifyOnCreate` và `setDates` đều có mặc định true. [EnableMongoAuditing](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/config/EnableMongoAuditing.html).

Nếu chọn `modifyOnCreate = false`, không kỳ vọng các field sửa được điền ngay ở lần tạo chỉ vì chúng có annotation. Chính sách này cần được thống nhất với giao diện: entity mới có thể chưa có thông tin “lần sửa” riêng.

### 7.2. Cập nhật entity đã tải

```java
Note existing = repository.findById(saved.getId()).orElseThrow();
existing.rename("Auditing: người tạo, người sửa và thời gian");
Note updated = repository.save(existing);
```

Trong đường cập nhật thông thường, metadata tạo được giữ lại; metadata sửa được cập nhật theo actor và thời gian đang được provider cung cấp. Nếu vẫn dùng provider demo, người sửa vẫn là `demo-user` dù lần gọi diễn ra muộn hơn.

Khi muốn quan sát hai actor khác nhau, cấu hình nguồn actor có khả năng cung cấp `user-101` cho lần tạo và `user-202` cho lần cập nhật. Không thay người sửa bằng cách tự gán trực tiếp field trong entity rồi kết luận provider đã hoạt động.

Luôn tiếp tục từ instance persistence trả về. Với model bất biến hoặc một số đường mapping, instance kết quả có thể khác instance đầu vào. Khi dùng entity immutable, các phương thức sao chép cần bảo toàn ID, version và metadata tạo không thuộc trách nhiệm thay đổi.

### 7.3. Metadata thời gian không phải thời điểm commit

Auditing ghi nhận thời gian ở checkpoint được cấu hình. Mốc này không tự trở thành thời điểm bắt đầu HTTP request, thời điểm người dùng nhấn nút hoặc thời điểm transaction commit.

Một audit field trong object ở bộ nhớ cũng không chứng minh dữ liệu đã được commit vào store. Khi cần biết trạng thái bền vững, phải xét kết quả thao tác và hợp đồng transaction của ứng dụng.

## 8. Entity mới hay entity đã tồn tại ảnh hưởng metadata

Metadata tạo và sửa phụ thuộc việc hạ tầng nhận diện đúng trạng thái entity. Spring Data có các chiến lược dựa trên ID, version hoặc `Persistable.isNew()`, tùy model và module. Khi có version được hỗ trợ, giá trị version có thể được dùng để nhận diện trạng thái trước khi dựa vào ID. [Entity State Detection Strategies](https://docs.spring.io/spring-data/commons/reference/is-new-state-detection.html).

Ở lớp hạ tầng, `IsNewAwareAuditingHandler` dùng chiến lược `isNew` để chọn xử lý created hoặc modified. [IsNewAwareAuditingHandler](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/auditing/IsNewAwareAuditingHandler.html).

Những tình huống cần chú ý:

| Tình huống | Ảnh hưởng có thể gặp |
| --- | --- |
| Tự gán ID trước lần lưu đầu | Không thể chỉ nhìn ID để kết luận hạ tầng sẽ coi entity là mới |
| Dựng lại entity cập nhật từ request, bỏ metadata cũ | Có thể làm mất người/ngày tạo hoặc version |
| `Persistable.isNew()` luôn trả true | Entity có thể luôn đi vào nhánh tạo theo hợp đồng module |
| Sao chép entity rồi đặt version về null | Có thể thay đổi nhận diện trạng thái và hành vi persistence |
| Dữ liệu cũ thiếu trường created | Một lần cập nhật không phải cơ chế tự động khôi phục lịch sử tạo |

Với thao tác sửa title, cách dễ theo dõi là tải entity hiện có, thay đổi dữ liệu nghiệp vụ rồi lưu lại, thay vì tạo một object mới chỉ có ID và title nhưng bỏ các field còn lại.

Không dùng `createdAt == null` như một quy tắc nhận diện mới tự phát nếu thiết kế persistence đã sử dụng chiến lược khác. Việc sửa chiến lược phải phù hợp với module và vòng đời thực tế.

## 9. Chọn cơ chế đúng với store và kiểu thực thi

| Môi trường | Phần cấu hình cần chú ý |
| --- | --- |
| MongoDB đồng bộ | `@EnableMongoAuditing`, `AuditorAware` và callback của module |
| MongoDB reactive | `@EnableReactiveMongoAuditing`, `ReactiveAuditorAware` và hạ tầng reactive |
| JPA | `@EnableJpaAuditing`, đăng ký `AuditingEntityListener` và các điều kiện tích hợp của JPA |
| JDBC/R2DBC hoặc module khác | Dùng cơ chế bật auditing và checkpoint do đúng module hỗ trợ |

JPA dùng entity listener để kích hoạt auditing. Có thể đăng ký listener theo entity bằng `@EntityListeners(AuditingEntityListener.class)` hoặc qua cấu hình persistence; cần tuân thủ cả các yêu cầu tích hợp của phiên bản JPA đang dùng. Cấu hình MongoDB không thay thế phần này. [JPA Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html).

### 9.1. Đồng bộ và reactive có hợp đồng provider khác nhau

```java
AuditorAware<String>              // getCurrentAuditor() -> Optional<String>
ReactiveAuditorAware<String>      // getCurrentAuditor() -> Mono<String>
```

Provider reactive phát auditor hoặc một publisher rỗng khi không biết auditor. [ReactiveAuditorAware](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/ReactiveAuditorAware.html).

Ví dụ bean demo cho một cấu hình reactive riêng:

```java
@Bean
ReactiveAuditorAware<String> currentReactiveAuditor() {
    return () -> reactor.core.publisher.Mono.just("demo-user");
}
```

Khi đó sử dụng annotation bật auditing reactive và tham chiếu đúng bean của nó. Đoạn bean này không tự chuyển cấu hình đồng bộ trước đó thành ứng dụng reactive.

Trong ứng dụng thực tế, lấy danh tính theo reactive context phù hợp. Không gọi `.block()` để ép việc tìm actor về đồng bộ, cũng không giả định `ThreadLocal` của lúc tạo pipeline còn đại diện đúng người dùng lúc pipeline thực thi.

### 9.2. Actor của job không nhất thiết là người đang mở giao diện

Job nhập dữ liệu, xử lý hàng đợi hoặc tác vụ lịch có thể chạy không có phiên đăng nhập. Ứng dụng cần quy định đó là actor hệ thống nào, hoặc thông tin người khởi tạo có được truyền tiếp theo một hợp đồng riêng không.

Không dùng người đăng nhập gần nhất trong một biến singleton để điền auditing cho công việc nền. Metadata cần phản ánh đúng nguồn actor của thao tác hiện tại.

## 10. Auditing hoạt động trong phạm vi đường persistence được hỗ trợ

Bốn annotation không phải database trigger. Một lệnh ghi bỏ qua callback/listener có thể bỏ qua cả việc điền auditing.

| Đường thao tác | Điều cần xác minh |
| --- | --- |
| Lưu entity qua repository/template | Có đi qua hạ tầng auditing của module không? |
| Query cập nhật trực tiếp hoặc bulk update | Có gọi entity lifecycle hay phải cập nhật audit fields tường minh? |
| Native query hoặc driver trực tiếp | Có bỏ qua phần mapping/callback không? |
| Script import/migration | Dữ liệu ai/thời gian có được cung cấp theo cùng hợp đồng không? |
| Database trigger tự cập nhật timestamp | Ai là nguồn có thẩm quyền cuối cùng cho giá trị thời gian? |
| Custom converter hoặc callback tạo bản sao | Có giữ lại metadata audit đã được điền không? |

Ví dụ tài liệu R2DBC nêu rõ modifying query chạy trực tiếp không gọi events/callbacks; field auditing không tự được cập nhật nếu query không cập nhật chúng. Đây là giới hạn của đường thực thi cụ thể, không phải lỗi annotation. [R2DBC Query Methods](https://docs.spring.io/spring-data/relational/reference/r2dbc/query-methods.html).

Nếu ứng dụng chọn để database quản lý thời gian, cần cấu hình phần gán thời gian của auditing nhất quán thay vì để hai nguồn cùng ghi đè. Hạ tầng auditing có tùy chọn điều khiển việc điền ngày và đánh dấu modified khi tạo. [AuditingHandlerSupport](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/auditing/AuditingHandlerSupport.html).

Không trộn lẫn thời gian do ứng dụng và database cung cấp mà không biết giá trị nào được đọc lại cho caller. Với cơ sở dữ liệu có độ chính xác khác Java, các phép so sánh kiểm chứng cũng cần tính đến độ chính xác được giữ lại.

## 11. Bốn field không thay thế những cơ chế khác

### 11.1. Lịch sử thay đổi

`lastModifiedBy` và `lastModifiedAt` giữ lần sửa gần nhất. Chúng không lưu:

- Danh sách tất cả lần sửa.
- Field nào đã đổi và giá trị trước/sau.
- Lý do thay đổi.
- Metadata của một entity đã bị xóa nếu bản ghi không còn tồn tại.

Nếu sản phẩm cần các thông tin này, thiết kế lịch sử phiên bản, event hoặc audit log riêng theo yêu cầu. Không suy rằng bốn annotation đã tạo sẵn kho lịch sử đó.

### 11.2. Phân quyền

Biết `createdBy` không đồng nghĩa người tạo mặc nhiên được sửa hoặc xóa entity. Việc cho phép thao tác phải do quy tắc phân quyền của ứng dụng quyết định.

Tương tự, một field `createdBy` do client gửi lên không phải danh tính đã xác thực. Chỉ ánh xạ các trường nghiệp vụ được phép từ request; để nguồn actor do server quản lý cung cấp metadata tương ứng.

### 11.3. Kiểm soát cập nhật đồng thời

`lastModifiedAt` không tự cung cấp optimistic locking. Hai thao tác có thể có cùng timestamp do độ chính xác store, hoặc đồng hồ giữa các node có độ lệch.

Trong ví dụ, `@Version` có vai trò riêng đối với optimistic locking theo khả năng module. Không dùng “timestamp lớn hơn” như một cơ chế thay thế nếu chưa thiết kế hợp đồng cập nhật đồng thời.

### 11.4. Truy vấn và dữ liệu trình bày

Có field auditing không có nghĩa chúng tự xuất hiện trong mọi projection hoặc kết quả query khai báo. Nếu query chọn một phần cột/field, DTO và mapping phải có dữ liệu tương ứng khi giao diện cần hiển thị.

Nếu dùng `lastModifiedAt` để sắp xếp/phân trang, hãy chọn thứ tự ổn định phù hợp với store, chẳng hạn có thêm khóa phân biệt khi nhiều entity cùng thời điểm. Auditing cung cấp dữ liệu; nó không tự cấu hình sort hoặc index cho mọi truy vấn.

## 12. Bài thực hành và cách quan sát kết quả

### 12.1. Một kịch bản có thể kiểm chứng

Thiết lập actor và clock có thể điều khiển trong môi trường thực hành, rồi thực hiện:

1. Actor `user-101` tạo một ghi chú tại `2026-11-25T02:00:00Z`.
2. Đọc lại ghi chú, lưu thông tin người/ngày tạo làm giá trị đối chiếu.
3. Actor `user-202` đổi title tại `2026-11-25T02:10:00Z`.
4. Đọc lại từ store để so sánh metadata thực sự được lưu.

Khi bật `modifyOnCreate = true`, kỳ vọng:

| Thuộc tính | Sau lần tạo | Sau lần sửa |
| --- | --- | --- |
| `createdBy` | `user-101` | `user-101` |
| `createdAt` | `02:00:00Z` | `02:00:00Z` |
| `lastModifiedBy` | `user-101` | `user-202` |
| `lastModifiedAt` | `02:00:00Z` | `02:10:00Z` |

Bảng rút gọn ngày vì cả hai mốc thuộc cùng ngày UTC. Không dùng một lần sleep rồi so sánh timestamp để thay cho việc kiểm soát nguồn thời gian khi bài thử cần kết quả xác định.

### 12.2. Kiểm tra riêng những đường quan trọng

| Tình huống | Câu hỏi kiểm chứng |
| --- | --- |
| Chỉ theo dõi thời gian | Có điền dates mà không cần nguồn auditor không? |
| Auditor không có giá trị | Metadata nào được giữ hoặc điền theo chính sách ứng dụng? |
| Có nhiều bean auditor | Đúng provider được chọn bằng cấu hình chưa? |
| Cập nhật entity cũ | Người/ngày tạo có được bảo toàn không? |
| ID được gán trước | Hạ tầng có nhận diện đúng trạng thái mới không? |
| Cập nhật trực tiếp | Audit fields có được xử lý theo hợp đồng riêng của đường đó không? |
| Entity immutable | Kết quả trả về có metadata đã điền và các phép sao chép có giữ chúng không? |
| Reactive hoặc job nền | Actor có thuộc đúng lần thực thi không? |

Các tình huống này xác nhận cả cấu hình và ý nghĩa dữ liệu. Gọi trực tiếp một provider chỉ chứng minh provider trả giá trị; nó chưa chứng minh repository đã kích hoạt auditing.

### 12.3. Chẩn đoán lỗi thường gặp

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| Cả bốn field đều null | Đã bật auditing đúng module và entity có đi qua lifecycle tương ứng chưa? |
| Dates có nhưng người thực hiện không có | Kiểm tra kiểu auditor, provider và nguồn actor hiện tại |
| Người thực hiện có nhưng dates không có | Kiểm tra `setDates`, `DateTimeProvider` và mapping kiểu thời gian |
| Mọi bản ghi đều có cùng người sửa | Có còn dùng provider demo hoặc một giá trị đã bị giữ trong trạng thái dùng chung không? |
| Metadata tạo bị mất sau cập nhật | Có dựng lại entity thiếu field, nhận diện sai trạng thái hoặc ghi đè từ request không? |
| Bulk update không đổi audit fields | Đường thực thi có bỏ qua callback/listener không? |
| Thời gian khác kỳ vọng vài chữ số | Đối chiếu timezone hiển thị và độ chính xác store lưu được |

Auditing có ý nghĩa khi cả bốn yếu tố khớp nhau: metadata entity, nguồn actor, nguồn thời gian và đường persistence được module hỗ trợ. Khi giữ rõ các yếu tố đó, ứng dụng có thể trả lời chính xác ai tạo/sửa và khi nào, đồng thời biết những câu hỏi cần một cơ chế lịch sử hoặc kiểm soát dữ liệu khác.
