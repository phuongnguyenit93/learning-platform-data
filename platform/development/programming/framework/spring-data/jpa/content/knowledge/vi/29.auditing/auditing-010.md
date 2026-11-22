# Spring Data Envers, RevisionRepository và yêu cầu Hibernate Envers

Spring Data Envers kết nối khả năng truy vấn lịch sử của Hibernate Envers với mô hình repository của Spring Data JPA. Hibernate Envers ghi lại các phiên bản của entity được đánh dấu audit; Spring Data Envers cung cấp RevisionRepository để đọc các revision đó bằng những method quen thuộc như tìm revision mới nhất, tìm trạng thái tại một revision và phân trang lịch sử.

Ba thành phần có vai trò khác nhau:

- **Hibernate Envers** là engine ghi nhận thay đổi và quản lý bảng lịch sử.
- **Spring Data Envers** tích hợp Envers vào hạ tầng repository của Spring Data JPA.
- **RevisionRepository** là interface Spring Data cung cấp để ứng dụng truy vấn lịch sử entity.

Chỉ thêm RevisionRepository vào interface là chưa đủ. Dự án cần Hibernate Envers trên classpath, repository phải được tạo bằng Envers repository infrastructure, và entity cần được đánh dấu bằng @Audited. Bài học này đi từ dependency, cấu hình, mô hình bảng audit, cách ghi revision, truy vấn bằng RevisionRepository/AuditReader, đến quan hệ, revision metadata, transaction, hiệu năng và kiểm thử.

## 1. Spring Data Auditing khác Hibernate Envers thế nào?

Spring Data JPA có hai khả năng thường bị nhầm lẫn:

**Spring Data Auditing** ghi metadata về lần tạo và lần cập nhật gần nhất trên bản ghi hiện tại. Các annotation phổ biến:

- @CreatedBy: người tạo entity.
- @CreatedDate: thời điểm tạo.
- @LastModifiedBy: người sửa gần nhất.
- @LastModifiedDate: thời điểm sửa gần nhất.

Ví dụ entity chỉ giữ thông tin hiện tại:

~~~java
@Entity
@EntityListeners(AuditingEntityListener.class)
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant lastModifiedAt;
}
~~~

Sau nhiều lần cập nhật, createdAt vẫn là thời điểm tạo và lastModifiedAt là thời điểm cập nhật gần nhất. Cơ chế này không tự giữ lại giá trị name trước đó.

**Hibernate Envers** lưu các phiên bản lịch sử của entity. Nếu name lần lượt đổi từ An sang Binh rồi Chi, Envers có thể lưu các trạng thái theo revision để ứng dụng xem lại dữ liệu tại từng thời điểm.

| Tiêu chí | Spring Data Auditing | Hibernate Envers |
|---|---|---|
| Mục tiêu | Ai tạo/sửa và khi nào | Lịch sử các phiên bản dữ liệu |
| Dữ liệu | Metadata hiện tại trên bảng entity | Bản ghi lịch sử trong audit table |
| Xem giá trị cũ | Không tự cung cấp | Có thể truy vấn theo revision |
| Tích hợp | @EnableJpaAuditing và auditing listener | @Audited, Hibernate Envers |
| Truy vấn lịch sử | Không phải mục đích chính | AuditReader hoặc RevisionRepository |

Hai cơ chế có thể dùng cùng nhau. Ví dụ ứng dụng giữ createdBy/lastModifiedBy trên entity hiện tại và dùng Envers để tra cứu mọi thay đổi trước đó.

## 2. Hibernate Envers là yêu cầu nền tảng

Envers là module thuộc Hibernate ORM. Nó không phải một tính năng độc lập của mọi JPA provider. Spring Data Envers dựa vào Envers để ghi và đọc lịch sử.

Với Maven, thêm dependency Spring Data Envers:

~~~xml
<dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-envers</artifactId>
</dependency>
~~~

Với Gradle:

~~~groovy
implementation("org.springframework.data:spring-data-envers")
~~~

Nếu dự án dùng Spring Boot hoặc Spring Data BOM, để dependency management quản lý version tương thích. Không chọn tùy ý một version Spring Data Envers và một version Hibernate Envers riêng biệt.

Spring Data Envers khai báo Hibernate Envers như dependency bắc cầu. Vì vậy, thêm spring-data-envers thường đã đưa hibernate-envers vào runtime classpath. Có thể kiểm tra dependency tree để xác nhận:

~~~bash
mvn dependency:tree
~~~

Hoặc với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Nếu dự án chủ động exclude dependency bắc cầu hoặc quản lý thư viện theo chính sách riêng, cần bảo đảm artifact hibernate-envers có mặt và version tương thích với hibernate-core đang chạy. Tránh ghép Hibernate Envers khác dòng phiên bản với Hibernate ORM vì có thể gặp lỗi class hoặc API khi khởi động.

Spring Data Envers luôn được sử dụng cùng Spring Data JPA. Chỉ thêm Spring Data Envers vào một ứng dụng không dùng Hibernate ORM sẽ không tạo ra chức năng revision tương đương.

## 3. Cấu hình repository Envers

Trong ứng dụng Spring Boot dùng auto-configuration, khi Spring Data Envers có trên classpath, Spring Boot có thể cấu hình JPA repositories để hỗ trợ truy vấn Envers. Repository vẫn cần kế thừa RevisionRepository.

Nếu tự cấu hình Spring Data repositories, dùng @EnableEnversRepositories:

~~~java
@Configuration
@EnableEnversRepositories(
    basePackages = "com.example.people.repository"
)
@EnableTransactionManagement
public class PersistenceConfiguration {
}
~~~

Annotation @EnableEnversRepositories cung cấp repository factory bean phù hợp cho Envers. Với cấu hình thủ công, đây là cách chuyên biệt để tạo repository có hỗ trợ revision.

Không bật hai cấu hình repository chồng lấn cho cùng package nếu không có chủ đích. Trong ứng dụng đã dùng Spring Boot auto-configuration, trước tiên kiểm tra cấu hình hiện có thay vì thêm annotation thủ công một cách máy móc.

Các thành phần JPA cơ bản vẫn cần hoạt động:

- DataSource kết nối database.
- EntityManagerFactory quản lý persistence unit.
- PlatformTransactionManager quản lý transaction.
- Entity được scan và mapping đúng.
- Hibernate Envers có mặt trong runtime classpath.

Trong Spring Boot, phần lớn bean này thường được auto-configure từ starter và datasource properties.

## 4. Đánh dấu entity bằng @Audited

Envers chỉ ghi lịch sử cho entity được bật auditing. Cách phổ biến là đặt @Audited trên class:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import org.hibernate.envers.Audited;

@Entity
@Audited
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    private String email;

    protected Person() {
    }

    public Person(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public void setName(String name) {
        this.name = name;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

@Audited là annotation của Hibernate Envers, package org.hibernate.envers. Nó không phải annotation của Spring Data JPA.

Khi entity được persist, cập nhật hoặc xóa thông qua Hibernate trong transaction, Envers ghi thông tin revision tương ứng. Nếu entity không được đánh dấu audit, RevisionRepository không thể tự tạo lịch sử cho entity đó.

Có thể đặt @Audited ở cấp class để audit các thuộc tính persistent theo mặc định, hoặc đặt ở cấp thuộc tính khi muốn chọn lọc. Với cách cấu hình chọn lọc, hãy kiểm tra chính xác annotation và quy tắc mặc định của phiên bản Envers đang dùng.

## 5. Revision là gì?

Revision là mốc lịch sử do Envers quản lý. Trong cấu hình mặc định, revision number là một số tăng dần dùng chung cho các thay đổi được audit.

Ví dụ:

| Revision | Person ID | name | email | Loại thay đổi |
|---:|---:|---|---|---|
| 1 | 10 | An | an@example.com | Tạo |
| 4 | 10 | Binh | an@example.com | Sửa |
| 7 | 10 | Binh | binh@example.com | Sửa |
| 9 | 10 | — | — | Xóa |

Revision number có thể không liên tiếp đối với một entity vì revision là phạm vi rộng hơn một entity. Những revision khác có thể được tạo bởi thay đổi trên entity khác.

Một transaction có thay đổi nhiều entity được audit có thể gom các thay đổi đó vào cùng một revision. Envers không tạo một revision độc lập cho mỗi câu lệnh save trong cùng transaction.

Revision number không phải ID của entity và cũng không phải trường @Version dùng cho optimistic locking.

## 6. Cấu trúc audit table

Với entity Person có bảng hiện tại PERSON, Envers mặc định tạo bảng audit thường có hậu tố _AUD, ví dụ PERSON_AUD. Bảng revision mặc định thường là REVINFO.

Mô hình đơn giản:

~~~text
PERSON
  id
  name
  email

PERSON_AUD
  id
  REV
  REVTYPE
  name
  email

REVINFO
  REV
  REVTSTMP
~~~

Ý nghĩa:

- PERSON lưu trạng thái hiện tại.
- PERSON_AUD lưu trạng thái lịch sử của các thuộc tính được audit.
- REV là revision number liên kết với bảng revision.
- REVTYPE biểu diễn loại thay đổi.
- REVINFO lưu revision number và timestamp của revision.

Khóa chính audit thường kết hợp ID entity và revision number, vì một entity có thể có nhiều phiên bản nhưng chỉ có một bản ghi của entity đó trong một revision.

Trong cấu hình mặc định, revision type biểu diễn các loại thêm mới, sửa và xóa. Hibernate Envers có enum RevisionType với các giá trị ADD, MOD và DEL. Spring Data ánh xạ thông tin revision sang RevisionMetadata.RevisionType với các giá trị INSERT, UPDATE, DELETE hoặc UNKNOWN.

Với thao tác xóa, Envers mặc định có thể chỉ lưu ID, revision và loại xóa trong audit row; các thuộc tính dữ liệu có thể là null. Nếu cần giữ toàn bộ dữ liệu tại thời điểm xóa, kiểm tra cấu hình store_data_at_delete của Envers và chi phí lưu trữ đi kèm.

## 7. Revision number không phải @Version

Hai cơ chế đều có thể chứa số tăng dần nhưng giải quyết hai bài toán khác nhau.

~~~java
@Entity
@Audited
public class Account {

    @Id
    @GeneratedValue
    private Long id;

    private String owner;

    @Version
    private Long version;
}
~~~

@Version thuộc JPA optimistic locking. Nó giúp phát hiện cập nhật xung đột khi nhiều transaction cùng sửa một entity.

Envers revision number xác định mốc lịch sử. Một revision có thể chứa thay đổi từ nhiều entity trong cùng transaction.

| Thuộc tính | @Version | Envers revision |
|---|---|---|
| Phạm vi | Một entity instance | Revision của transaction có thay đổi audit |
| Mục đích | Phát hiện ghi đè đồng thời | Xem lại lịch sử |
| Tự cung cấp snapshot cũ | Không | Có |
| Được dùng cho | Optimistic locking | Audit/history query |

Có thể dùng cả hai trong cùng entity. Không dùng revision number để thay thế optimistic locking hoặc ngược lại.

## 8. Khai báo RevisionRepository

RevisionRepository thuộc Spring Data Commons và được Spring Data Envers hỗ trợ khi repository infrastructure đã được cấu hình.

Khai báo repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.history.RevisionRepository;

public interface PersonRepository
        extends JpaRepository<Person, Long>,
                RevisionRepository<Person, Long, Integer> {
}
~~~

Ba tham số generic có ý nghĩa:

1. Person: entity cần đọc lịch sử.
2. Long: kiểu ID của entity.
3. Integer: kiểu revision number.

Với Envers cấu hình mặc định, kiểu revision number thường là Integer hoặc Long. N phải là kiểu số có thể so sánh theo hợp đồng RevisionRepository.

RevisionRepository không thay thế JpaRepository. Trong ví dụ, JpaRepository vẫn cung cấp CRUD; RevisionRepository bổ sung API đọc lịch sử.

Entity Person phải được đánh dấu @Audited. Nếu không, các method lịch sử không có audit record phù hợp để trả về.

## 9. Các method chính của RevisionRepository

RevisionRepository cung cấp các thao tác sau:

| Method | Kết quả | Mục đích |
|---|---|---|
| findLastChangeRevision(id) | Optional<Revision<N,T>> | Revision gần nhất của entity |
| findRevision(id, revisionNumber) | Optional<Revision<N,T>> | Entity tại một revision cụ thể |
| findRevisions(id) | Revisions<N,T> | Toàn bộ revision của entity |
| findRevisions(id, pageable) | Page<Revision<N,T>> | Phân trang lịch sử |

Các method này yêu cầu ID không null. Với findRevision, revision number cũng không được null.

Không có lịch sử phù hợp thì các method Optional có thể trả Optional.empty(); Revisions có thể là collection rỗng. Luôn xử lý trường hợp entity chưa có revision hoặc ID không tồn tại.

## 10. Đọc toàn bộ lịch sử bằng findRevisions

Ví dụ service đọc lịch sử của một Person:

~~~java
@Service
public class PersonHistoryService {

    private final PersonRepository repository;

    public PersonHistoryService(PersonRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<PersonRevisionView> history(Long personId) {
        Revisions<Integer, Person> revisions =
            repository.findRevisions(personId);

        return revisions.getContent().stream()
            .map(revision -> {
                RevisionMetadata<Integer> metadata =
                    revision.getMetadata();

                return new PersonRevisionView(
                    metadata.getRevisionNumber().orElseThrow(),
                    metadata.getRevisionInstant().orElseThrow(),
                    metadata.getRevisionType().name(),
                    revision.getEntity().getName(),
                    revision.getEntity().getEmail()
                );
            })
            .toList();
    }
}
~~~

DTO trả về:

~~~java
public record PersonRevisionView(
    Integer revisionNumber,
    Instant changedAt,
    String changeType,
    String name,
    String email
) {
}
~~~

Ví dụ dùng getContent() để lấy danh sách revision. Mỗi Revision chứa entity snapshot và metadata. Metadata cung cấp revision number, thời điểm và loại thay đổi.

Nếu dự án dùng Java thấp hơn 16, thay toList() bằng Collectors.toList(). Các class Person, PersonRepository và DTO cần được đặt trong package tương ứng và có import phù hợp.

## 11. Đọc revision mới nhất

Dùng findLastChangeRevision:

~~~java
Optional<Revision<Integer, Person>> latest =
    personRepository.findLastChangeRevision(personId);

if (latest.isPresent()) {
    Revision<Integer, Person> revision = latest.get();

    Integer number = revision.getMetadata()
        .getRevisionNumber()
        .orElseThrow();

    Person snapshot = revision.getEntity();

    RevisionMetadata.RevisionType type =
        revision.getMetadata().getRevisionType();
}
~~~

Method trả về revision mà entity được thay đổi gần nhất. Revision mới nhất có thể là revision DELETE nếu entity đã bị xóa.

Vì vậy, trước khi hiển thị snapshot như một entity còn tồn tại, hãy kiểm tra revision type. Bản ghi xóa mặc định có thể không giữ đầy đủ các thuộc tính đã audit.

Không dùng findLastChangeRevision để tìm entity hiện tại thay cho findById. Hai method có mục tiêu khác nhau: một method đọc lịch sử, một method đọc bảng hiện tại.

## 12. Tìm trạng thái tại một revision cụ thể

Dùng findRevision:

~~~java
Optional<Revision<Integer, Person>> result =
    personRepository.findRevision(personId, revisionNumber);

if (result.isPresent()) {
    Revision<Integer, Person> revision = result.get();
    Person historicalState = revision.getEntity();

    Integer actualRevision = revision.getMetadata()
        .getRevisionNumber()
        .orElseThrow();
}
~~~

Method này trả về Revision wrapper, không trả trực tiếp Person. Wrapper chứa metadata và entity snapshot tại revision yêu cầu.

Nếu revision number không tồn tại cho entity đó, kết quả có thể rỗng. Revision number có thể tồn tại trong REVINFO do thay đổi của entity khác nhưng không có nghĩa Person có snapshot ở revision đó.

Khi cần trạng thái của entity tại một mốc lịch sử, dùng API này thay vì lấy entity hiện tại rồi cố khôi phục các field thủ công.

## 13. Phân trang lịch sử với Pageable

Một entity có thể được sửa hàng nghìn lần. Không nên luôn tải toàn bộ lịch sử vào bộ nhớ.

RevisionRepository hỗ trợ phân trang:

~~~java
Page<Revision<Integer, Person>> page =
    personRepository.findRevisions(
        personId,
        PageRequest.of(0, 20, RevisionSort.desc())
    );
~~~

RevisionSort là Sort chuyên biệt để sắp xếp theo revision number mà không phụ thuộc tên property của revision entity. RevisionSort.desc() đưa revision mới hơn lên trước; RevisionSort.asc() đưa revision cũ hơn lên trước.

Có thể đọc:

~~~java
for (Revision<Integer, Person> revision : page.getContent()) {
    Integer number = revision.getMetadata()
        .getRevisionNumber()
        .orElseThrow();

    Person snapshot = revision.getEntity();
}
~~~

Tài liệu API lưu ý implementation không bắt buộc hỗ trợ sort theo mọi property khi phân trang revisions. Dùng RevisionSort khi cần sắp xếp theo revision number và kiểm tra khả năng sort khác trên phiên bản cụ thể.

## 14. Revision và RevisionMetadata

Spring Data biểu diễn một phiên bản bằng Revision<N,T>. Revision chứa:

- Entity snapshot.
- RevisionMetadata.
- Revision number.
- Revision timestamp nếu có.
- Revision type.

RevisionMetadata cung cấp các API:

~~~java
RevisionMetadata<Integer> metadata = revision.getMetadata();

Optional<Integer> number = metadata.getRevisionNumber();

Optional<Instant> instant = metadata.getRevisionInstant();

RevisionMetadata.RevisionType type = metadata.getRevisionType();
~~~

RevisionMetadata.RevisionType có các giá trị:

- INSERT: entity được tạo.
- UPDATE: entity được sửa.
- DELETE: entity bị xóa.
- UNKNOWN: không xác định được loại thay đổi.

Không nhầm enum Spring Data này với org.hibernate.envers.RevisionType của Hibernate. Hai enum thuộc hai API khác nhau và dùng tên giá trị khác nhau.

getDelegate() của RevisionMetadata có thể cung cấp revision metadata object gốc do store/provider sử dụng. Khi dùng custom revision entity và cần đọc thêm field như actor hoặc requestId, có thể truy cập delegate theo kiểu revision entity đã cấu hình. Nên đóng gói việc chuyển đổi này trong service/mapper thay vì để controller phụ thuộc trực tiếp Hibernate metadata.

## 15. Truy vấn lịch sử trực tiếp bằng AuditReader

RevisionRepository phù hợp với thao tác phổ biến theo ID entity. Khi cần truy vấn lịch sử phức tạp, Hibernate Envers cung cấp AuditReader.

~~~java
AuditReader reader =
    AuditReaderFactory.get(entityManager);

Person historicalPerson =
    reader.find(Person.class, personId, revisionNumber);
~~~

AuditReaderFactory lấy AuditReader từ EntityManager hiện tại. find trả trạng thái của entity tại revision number được yêu cầu.

AuditReader cũng hỗ trợ truy vấn revision theo tiêu chí. Ví dụ có thể truy vấn các revision của Person, lọc theo ID và sắp xếp theo revision number bằng Envers AuditQuery API.

~~~java
List<Object[]> changes = reader.createQuery()
    .forRevisionsOfEntity(Person.class, false, true)
    .add(AuditEntity.id().eq(personId))
    .addOrder(AuditEntity.revisionNumber().asc())
    .getResultList();
~~~

Khi selectEntitiesOnly là false, mỗi kết quả thường là một Object[] gồm entity snapshot, revision entity và revision type. Cần ép kiểu theo entity và revision mapping thực tế.

Dùng AuditReader khi cần tính năng truy vấn chuyên sâu mà RevisionRepository không cung cấp trực tiếp. Giữ phần truy vấn Hibernate-specific ở service/repository boundary để tránh làm rò rỉ API Envers ra toàn bộ ứng dụng.

## 16. Tùy chỉnh tên audit table

Mặc định Envers thường thêm hậu tố _AUD vào tên bảng entity. Có thể thay đổi tên audit table cho từng entity bằng @AuditTable:

~~~java
@Entity
@Audited
@AuditTable(value = "PERSON_HISTORY")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
}
~~~

Hoặc cấu hình prefix/suffix toàn cục bằng Hibernate properties. Ví dụ Spring Boot:

~~~properties
spring.jpa.properties.org.hibernate.envers.audit_table_suffix=_HISTORY
~~~

Nếu đổi tên table, migration database phải tạo đúng tên và cấu trúc mà Envers mong đợi.

Trong môi trường production, không nên phụ thuộc vào tự động tạo schema của Hibernate để thay thế quản lý migration. Dùng Flyway, Liquibase hoặc quy trình schema migration của dự án để tạo audit tables, revision table, khóa và index tương ứng.

## 17. Chỉ audit một số thuộc tính với @NotAudited

Một số field không cần lưu lịch sử, ví dụ dữ liệu cache hoặc thông tin tạm thời. Dùng @NotAudited:

~~~java
@Entity
@Audited
public class UserProfile {

    @Id
    @GeneratedValue
    private Long id;

    private String displayName;

    @NotAudited
    private String temporaryAccessToken;
}
~~~

Field temporaryAccessToken không được ghi vào audit table. Các field khác vẫn được audit theo mapping.

Đừng loại một field khỏi audit chỉ vì nó nhạy cảm mà chưa xem xét yêu cầu compliance. Cần xác định chính sách dữ liệu: có nên lưu lịch sử, có cần mã hóa, có cần masking hoặc có cần retention giới hạn không.

Ngược lại, không nên audit mọi dữ liệu một cách vô điều kiện. Audit table có thể chứa nhiều bản sao dữ liệu nhạy cảm và làm tăng đáng kể dung lượng database.

## 18. Quan hệ tới entity không được audit

Nếu entity audited tham chiếu entity khác không được đánh dấu @Audited, Envers cần biết cách xử lý quan hệ đó.

Một trường hợp là chỉ muốn lưu liên kết tới trạng thái hiện tại của target entity:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@Audited(targetAuditMode = RelationTargetAuditMode.NOT_AUDITED)
private Department department;
~~~

Với RelationTargetAuditMode.NOT_AUDITED, lịch sử của entity nguồn có thể tham chiếu tới entity đích không được audit theo trạng thái hiện tại của nó.

Điều này có nghĩa khi xem lại lịch sử, Department có thể phản ánh dữ liệu hiện tại, không phải snapshot Department tại revision cũ. Không dùng cách này nếu yêu cầu là khôi phục toàn bộ graph quan hệ như tại thời điểm lịch sử.

Nếu cần lịch sử của cả hai phía quan hệ, hãy đánh dấu target entity audit và cấu hình quan hệ theo mapping được Envers hỗ trợ.

## 19. Đánh dấu thay đổi từng thuộc tính

Envers có thể lưu cờ cho biết thuộc tính nào thay đổi trong revision. Ví dụ:

~~~java
@Entity
@Audited(withModifiedFlag = true)
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    private String email;
}
~~~

Với modified flag, audit table có thể có thêm cột biểu diễn field tương ứng có thay đổi trong revision hay không. Tên cột mặc định thường được tạo theo property name và hậu tố cấu hình.

Thông tin này hữu ích khi màn hình audit cần hiển thị “email đã thay đổi” mà không phải so sánh toàn bộ snapshot trước/sau.

Đổi lại, schema và dữ liệu audit lớn hơn. Hãy kiểm tra cấu hình modified flag và migration database trước khi bật trên entity có nhiều field.

Envers AuditQuery API hỗ trợ điều kiện truy vấn theo thuộc tính đã thay đổi, ví dụ AuditEntity.property("email").hasChanged(). Đây là tính năng Hibernate Envers, không phải method mặc định của RevisionRepository.

## 20. Custom Revision Entity để lưu người thay đổi

Revision mặc định lưu số revision và timestamp. Ứng dụng có thể cần thêm actor, tenant, request ID hoặc nguồn thao tác.

Tạo revision entity:

~~~java
@Entity
@Table(name = "REVINFO")
@RevisionEntity(CurrentUserRevisionListener.class)
public class AuditRevisionEntity {

    @Id
    @GeneratedValue
    @RevisionNumber
    private int id;

    @RevisionTimestamp
    private long timestamp;

    @Column(length = 120)
    private String actor;

    @Column(length = 80)
    private String requestId;

    public int getId() {
        return id;
    }

    public long getTimestamp() {
        return timestamp;
    }

    public String getActor() {
        return actor;
    }

    public void setActor(String actor) {
        this.actor = actor;
    }

    public String getRequestId() {
        return requestId;
    }

    public void setRequestId(String requestId) {
        this.requestId = requestId;
    }
}
~~~

Hai annotation quan trọng:

- @RevisionNumber đánh dấu khóa revision.
- @RevisionTimestamp đánh dấu thời điểm revision.

@RevisionEntity liên kết revision entity với RevisionListener để điền metadata khi Envers tạo revision.

Ví dụ listener dùng Spring Security:

~~~java
public class CurrentUserRevisionListener
        implements RevisionListener {

    @Override
    public void newRevision(Object revisionEntity) {
        AuditRevisionEntity revision =
            (AuditRevisionEntity) revisionEntity;

        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            revision.setActor("system");
        } else {
            revision.setActor(authentication.getName());
        }
    }
}
~~~

Ví dụ cần Spring Security và các import tương ứng. Nếu ứng dụng không dùng Spring Security, thay bằng nguồn identity phù hợp của hệ thống.

RevisionListener được gọi khi Envers tạo revision, không phải một lần cho mỗi entity trong revision. Giữ listener đơn giản, tránh truy vấn database hoặc gọi dịch vụ mạng trong callback. Với tác vụ async, scheduler hoặc message consumer, cần truyền identity theo context phù hợp; SecurityContext của HTTP request không tự xuất hiện trong mọi thread.

## 21. Revision metadata và transaction boundary

Envers ghi lịch sử trong cùng transaction với thay đổi entity. Khi transaction rollback, các audit record trong transaction đó cũng rollback.

Một transaction có thể thay đổi nhiều entity được audit và tất cả cùng tham chiếu đến một revision. Vì vậy:

- Hai lần save trong cùng một transaction không nhất thiết tạo hai revision.
- Hai transaction commit riêng có thể tạo hai revision.
- Một transaction chỉ đọc không tạo revision mới.
- Một transaction không làm thay đổi dữ liệu audited sẽ không tạo revision chỉ vì có gọi save.
- Revision number là mốc lịch sử, không phải log cho từng dòng code hoặc từng lần gọi repository.

Ví dụ:

~~~java
@Transactional
public void renamePerson(Long id) {
    Person person = repository.findById(id)
        .orElseThrow();

    person.setName("Binh");
    repository.save(person);

    person.setEmail("binh@example.com");
    repository.save(person);
}
~~~

Hai lần save diễn ra trong cùng transaction. Envers thường ghi một revision cho transaction đó với trạng thái thay đổi cuối cùng của entity, không tạo hai revision riêng cho hai lần gọi save.

Nếu nghiệp vụ cần hai mốc audit riêng, cần hai transaction độc lập với ranh giới được thiết kế rõ. Không chia transaction chỉ để tăng revision number nếu điều đó làm mất tính atomic của nghiệp vụ.

## 22. Bulk update/delete và SQL trực tiếp

Envers hoạt động dựa trên event/lifecycle của Hibernate khi entity được quản lý và thay đổi qua ORM.

Các thao tác bulk JPQL hoặc native SQL cập nhật trực tiếp nhiều hàng thường bỏ qua entity lifecycle events:

~~~java
@Modifying
@Query("""
    update Person p
    set p.name = :name
    where p.id = :id
    """)
int updateName(
    @Param("id") Long id,
    @Param("name") String name
);
~~~

Bulk update như trên không tự tạo lịch sử Envers cho từng entity như khi tải entity, thay đổi field và flush qua Hibernate.

Tương tự, SQL chạy trực tiếp từ JDBC, script ngoài ứng dụng hoặc hệ thống khác cập nhật bảng không tự kích hoạt Envers.

Nếu nghiệp vụ bắt buộc audit các thay đổi bulk, hãy thiết kế chiến lược riêng:

- Tải và cập nhật entity qua ORM nếu số lượng phù hợp.
- Tạo audit event riêng cho thao tác bulk.
- Dùng cơ chế database auditing/CDC khi cần theo dõi mọi thay đổi bất kể nguồn.
- Ghi rõ phạm vi nào do Envers theo dõi và phạm vi nào do hệ thống khác đảm nhiệm.

Không tuyên bố Envers là bản ghi đầy đủ mọi thay đổi database nếu ứng dụng còn có đường ghi ngoài Hibernate.

## 23. Xóa entity và dữ liệu lịch sử

Khi entity bị xóa qua Hibernate, Envers ghi revision mang loại DELETE. Bảng hiện tại không còn entity nhưng audit table vẫn có thể giữ marker lịch sử.

Có thể truy vấn revision xóa bằng RevisionRepository và kiểm tra RevisionMetadata.RevisionType.DELETE.

Với cấu hình mặc định, snapshot của revision xóa có thể chỉ chứa định danh thay vì toàn bộ field. Nếu cần lưu dữ liệu cuối cùng trước khi xóa, xem xét cấu hình Envers store_data_at_delete và kiểm tra audit schema.

Không xóa audit row chỉ vì entity hiện tại đã bị xóa. Việc giữ lịch sử thường là mục đích chính của Envers. Nếu cần xóa dữ liệu theo chính sách retention hoặc quyền riêng tư, phải có quy trình xóa audit phù hợp và xem xét ảnh hưởng tới yêu cầu pháp lý/nghiệp vụ.

## 24. Envers không phải event sourcing

Envers ghi lại trạng thái entity theo revision để truy vấn lịch sử. Nó không tự biến các thay đổi thành domain event có ý nghĩa nghiệp vụ.

Ví dụ Envers có thể cho thấy Account balance đổi từ 100 sang 80. Nhưng nó không tự giải thích hành động đó là thanh toán hóa đơn, hoàn tiền hay điều chỉnh thủ công.

| Envers | Event sourcing |
|---|---|
| Lưu snapshot/phiên bản entity | Lưu event nghiệp vụ |
| Tập trung vào lịch sử trạng thái dữ liệu | Tập trung vào chuỗi sự kiện làm phát sinh trạng thái |
| Có thể truy vấn entity tại revision | Replay event để dựng trạng thái |
| Không tự diễn giải lý do nghiệp vụ | Event thường mang tên và dữ liệu nghiệp vụ |
| Phù hợp audit lịch sử ORM | Phù hợp hệ thống lấy event làm nguồn dữ liệu chính |

Nếu yêu cầu là xem ai sửa field nào và dữ liệu trước/sau ra sao, Envers có thể phù hợp. Nếu cần biết chính xác nghiệp vụ nào xảy ra và phát lại chuỗi sự kiện, cần thiết kế domain event/event sourcing riêng.

## 25. Hiệu năng và dung lượng audit

Mỗi revision làm phát sinh ghi dữ liệu bổ sung. Entity có nhiều field hoặc cập nhật thường xuyên có thể tạo audit table lớn.

Cần xem xét:

- Số entity được @Audited.
- Số field được audit.
- Tần suất update.
- Collection/association có nhiều thay đổi.
- Modified flags.
- Index trên ID và revision number.
- Truy vấn lịch sử có phân trang hay tải toàn bộ.
- Chính sách retention và backup.

Các bảng audit thường cần index phục vụ truy vấn theo entity ID và revision. Schema mặc định có khóa kết hợp nhưng truy vấn thực tế có thể cần index bổ sung theo workload.

Không thêm index tùy tiện. Dùng execution plan và đo các query lịch sử thường gặp.

RevisionRepository.findRevisions(id) có thể trả toàn bộ lịch sử. Với entity thay đổi nhiều, ưu tiên findRevisions(id, pageable).

## 26. Bảo mật và dữ liệu nhạy cảm

Audit table là dữ liệu lưu lâu dài. Khi một field nhạy cảm được audit, các giá trị cũ của nó cũng có thể còn trong audit table sau khi giá trị hiện tại đã thay đổi hoặc bị xóa.

Các việc cần làm:

- Xác định field nào cần audit.
- Dùng @NotAudited cho field không cần lịch sử.
- Không audit password plaintext, token truy cập hoặc secret.
- Giới hạn quyền đọc audit history.
- Ghi nhận actor và request context nếu yêu cầu truy vết.
- Bảo vệ backup và replica chứa audit data.
- Định nghĩa retention, masking hoặc quy trình xóa theo chính sách dữ liệu.
- Không trả toàn bộ revision entity trực tiếp ra API nếu có metadata nội bộ.

Audit history thường có mức độ nhạy cảm cao hơn dữ liệu hiện tại vì nó chứa nhiều phiên bản trước đó.

## 27. Kiểm thử Envers và revision commit

Một test cần xác nhận ít nhất hai transaction đã tạo hai revision. Lưu ý @DataJpaTest thường chạy test trong transaction và rollback khi kết thúc. Nếu chỉ save rồi update trong cùng transaction, test không chứng minh hai revision độc lập.

Ví dụ dùng TestTransaction để commit giữa các giai đoạn:

~~~java
@DataJpaTest
class PersonRevisionRepositoryTest {

    @Autowired
    private PersonRepository repository;

    @Test
    void storesSeparateRevisionsForSeparateTransactions() {
        Person person = repository.saveAndFlush(
            new Person("An", "an@example.com")
        );

        Long id = person.getId();

        TestTransaction.flagForCommit();
        TestTransaction.end();

        TestTransaction.start();

        Person current = repository.findById(id).orElseThrow();
        current.setName("Binh");
        repository.saveAndFlush(current);

        TestTransaction.flagForCommit();
        TestTransaction.end();

        TestTransaction.start();

        Revisions<Integer, Person> revisions =
            repository.findRevisions(id);

        assertEquals(2, revisions.getContent().size());

        Person latest = repository.findLastChangeRevision(id)
            .orElseThrow()
            .getEntity();

        assertEquals("Binh", latest.getName());
    }
}
~~~

Ví dụ cần import TestTransaction, DataJpaTest và assertion từ test framework đang dùng. Test giả định repository được cấu hình Envers, entity Person có constructor và setter như ví dụ trước, và schema audit đã được tạo.

Transaction đầu tạo Person và commit. Transaction thứ hai đổi tên và commit. Transaction thứ ba đọc revision history. Test transaction cuối có thể rollback khi test kết thúc.

Các test quan trọng khác:

1. Persist entity audited tạo revision INSERT.
2. Update entity tạo revision UPDATE.
3. Delete entity tạo revision DELETE.
4. Rollback không để lại audit row đã commit.
5. Hai entity thay đổi trong cùng transaction có cùng revision number.
6. @NotAudited không tạo dữ liệu lịch sử cho field bị loại.
7. Quan hệ tới entity không audit hoạt động theo targetAuditMode đã chọn.
8. RevisionRepository phân trang và sắp xếp đúng.
9. Custom RevisionListener lưu actor phù hợp.
10. Bulk update không bị nhầm là đã được Envers audit.

## 28. Lỗi thường gặp và cách khắc phục

**1. Repository không có method lịch sử hoặc startup báo lỗi factory**

Kiểm tra spring-data-envers có trên classpath không, repository có kế thừa RevisionRepository không và repository infrastructure có dùng Envers factory không. Với Spring Boot, kiểm tra auto-configuration; với cấu hình thủ công, dùng @EnableEnversRepositories.

**2. Entity không có revision**

Kiểm tra entity có @Audited không, thay đổi có thực sự được flush/commit không và thao tác có đi qua Hibernate ORM không.

**3. Không tìm thấy class Hibernate Envers**

Kiểm tra dependency tree và đảm bảo hibernate-envers có mặt, version tương thích với hibernate-core.

**4. Sai kiểu generic revision number**

Kiểm tra tham số thứ ba của RevisionRepository. Với Envers mặc định thường dùng Integer hoặc Long.

**5. Lịch sử không tăng sau nhiều lần save**

Kiểm tra các lần save có nằm trong cùng transaction hay không. Một transaction có thể chỉ tạo một revision cho các thay đổi được audit.

**6. Bulk update không tạo audit row**

Bulk JPQL/native SQL bỏ qua entity lifecycle events. Dùng ORM update hoặc cơ chế audit riêng.

**7. Quan hệ tới entity không audit gây lỗi mapping**

Đánh dấu target entity @Audited nếu cần lịch sử quan hệ, hoặc cấu hình RelationTargetAuditMode.NOT_AUDITED nếu chấp nhận tham chiếu trạng thái hiện tại của target.

**8. Revision xóa không có đủ field**

Kiểm tra store_data_at_delete. Mặc định revision DELETE có thể chỉ lưu ID và metadata.

**9. Test thấy không có revision**

Kiểm tra transaction test có rollback hay không và thay đổi có commit chưa. Dùng TestTransaction hoặc thiết kế transaction test riêng.

**10. Audit table không được tạo trong production**

Kiểm tra schema migration. Không giả định Hibernate tự tạo audit table khi production dùng ddl-auto=validate hoặc none.

**11. Audit table tăng quá nhanh**

Xem lại phạm vi @Audited, field @NotAudited, tần suất ghi, modified flags, retention và index.

**12. Nhầm Envers với @Version hoặc Spring Data Auditing**

@Version xử lý optimistic locking; Spring Data Auditing ghi metadata tạo/sửa; Envers lưu lịch sử entity. Chọn đúng cơ chế theo yêu cầu.

## 29. Quy trình triển khai Spring Data Envers

1. Xác nhận ứng dụng dùng Spring Data JPA và Hibernate ORM.
2. Thêm spring-data-envers với version do BOM quản lý.
3. Kiểm tra hibernate-envers được đưa vào runtime classpath.
4. Đánh dấu entity cần lịch sử bằng @Audited.
5. Xác định field/association cần loại khỏi audit.
6. Cấu hình @EnableEnversRepositories nếu không dùng auto-configuration phù hợp.
7. Kế thừa RevisionRepository cùng JpaRepository.
8. Chọn kiểu revision number Integer hoặc Long phù hợp.
9. Tạo schema audit tables và revision table bằng migration.
10. Xác định metadata bổ sung như actor hoặc request ID nếu cần.
11. Giữ transaction boundary đúng với nghiệp vụ.
12. Xác định bulk/native SQL có cần cơ chế audit riêng không.
13. Tạo service đọc lịch sử bằng RevisionRepository.
14. Dùng AuditReader khi cần truy vấn Envers chuyên sâu.
15. Phân trang lịch sử và giới hạn quyền truy cập.
16. Kiểm thử INSERT, UPDATE, DELETE, rollback, relation và custom revision metadata.
17. Theo dõi dung lượng, query plan và chính sách retention.

## 30. Checklist tự đánh giá

- [ ] Tôi phân biệt được Spring Data Auditing và Hibernate Envers.
- [ ] Tôi hiểu Envers là module của Hibernate ORM.
- [ ] Tôi biết thêm dependency spring-data-envers.
- [ ] Tôi biết hibernate-envers được đưa vào runtime và phải tương thích với Hibernate ORM.
- [ ] Tôi biết khi nào dùng @EnableEnversRepositories.
- [ ] Tôi biết đánh dấu entity bằng org.hibernate.envers.Audited.
- [ ] Tôi hiểu cấu trúc audit table và revision table.
- [ ] Tôi phân biệt revision number với entity ID và @Version.
- [ ] Tôi biết khai báo RevisionRepository<T, ID, N>.
- [ ] Tôi biết dùng findLastChangeRevision, findRevision và findRevisions.
- [ ] Tôi biết phân trang lịch sử bằng Pageable và RevisionSort.
- [ ] Tôi biết đọc RevisionMetadata và RevisionType.
- [ ] Tôi biết dùng AuditReader khi cần query nâng cao.
- [ ] Tôi biết cấu hình @AuditTable và @NotAudited.
- [ ] Tôi hiểu targetAuditMode cho quan hệ tới entity không audit.
- [ ] Tôi biết tạo custom revision entity và RevisionListener.
- [ ] Tôi hiểu một transaction có thể gom nhiều thay đổi vào cùng revision.
- [ ] Tôi biết bulk JPQL/native SQL không tự được Envers audit.
- [ ] Tôi biết kiểm thử commit/rollback và lịch sử revision.
- [ ] Tôi có chính sách bảo mật, retention và dung lượng audit.

## 31. Câu hỏi ôn tập

**1. Spring Data Envers có phải engine audit không?**

Không. Hibernate Envers là engine ghi nhận lịch sử; Spring Data Envers tích hợp các truy vấn revision vào repository của Spring Data JPA.

**2. Vì sao cần dependency hibernate-envers?**

Vì Spring Data Envers dựa vào Hibernate Envers để tạo audit record và truy vấn lịch sử. Dependency spring-data-envers thường đưa hibernate-envers vào runtime theo dependency bắc cầu.

**3. @Audited có tác dụng gì?**

Đánh dấu entity hoặc thuộc tính cần được Hibernate Envers theo dõi và lưu lịch sử.

**4. RevisionRepository có thay JpaRepository không?**

Không. RevisionRepository cung cấp API lịch sử; nếu cần CRUD, repository thường kế thừa cả JpaRepository và RevisionRepository.

**5. Ba tham số generic của RevisionRepository có ý nghĩa gì?**

Entity type, ID type và revision number type.

**6. findRevision trả về entity trực tiếp không?**

Không. Nó trả Optional<Revision<N,T>>, trong đó Revision chứa entity snapshot và metadata.

**7. Một transaction thay đổi ba entity audited tạo bao nhiêu revision?**

Thông thường một revision cho transaction đó, dùng chung cho các thay đổi audited trong transaction.

**8. @Version có thay thế revision number không?**

Không. @Version hỗ trợ optimistic locking cho một entity; revision number định danh mốc lịch sử của Envers.

**9. Vì sao bulk update không tạo lịch sử Envers?**

Bulk JPQL/native SQL cập nhật trực tiếp dữ liệu và bỏ qua entity lifecycle events mà Envers dùng để ghi audit.

**10. Khi nào dùng AuditReader thay vì RevisionRepository?**

Khi cần query lịch sử nâng cao theo nhiều tiêu chí, revision date, property changed hoặc các khả năng Hibernate Envers-specific mà repository API không cung cấp trực tiếp.

**11. Revision DELETE mặc định có giữ toàn bộ field không?**

Không nhất thiết. Mặc định có thể chỉ giữ ID và metadata; cấu hình store_data_at_delete điều khiển việc lưu dữ liệu tại thời điểm xóa.

**12. Vì sao cần TestTransaction trong một số test Envers?**

@DataJpaTest thường rollback transaction test. Muốn xác minh revision giữa các transaction độc lập, cần commit transaction trước rồi đọc lịch sử ở transaction khác.

Spring Data Envers giúp ứng dụng truy vấn lịch sử entity bằng repository API, nhưng khả năng ghi revision đến từ Hibernate Envers. Khi dependency, @Audited, repository factory và transaction boundary được cấu hình đúng, ứng dụng có thể xem lại trạng thái entity theo revision, theo dõi loại thay đổi và mở rộng metadata để lưu người thực hiện. Hãy xác định rõ phạm vi audit, đường ghi dữ liệu và chính sách bảo mật trước khi coi audit history là nguồn truy vết đầy đủ.

## Tài liệu tham khảo

- [Spring Data JPA — Spring Data Envers Introduction](https://docs.spring.io/spring-data/jpa/reference/envers/introduction.html)
- [Spring Data JPA — Envers Configuration](https://docs.spring.io/spring-data/jpa/reference/envers/configuration.html)
- [Spring Data Commons — RevisionRepository API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/repository/history/RevisionRepository.html)
- [Spring Data Commons — RevisionMetadata API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/history/RevisionMetadata.html)
- [Spring Data Commons — RevisionSort API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/history/RevisionSort.html)
- [Spring Data JPA — Auditing](https://docs.spring.io/spring-data/jpa/reference/data-commons/auditing.html)
- [Hibernate ORM — Envers documentation](https://hibernate.org/orm/envers/)
