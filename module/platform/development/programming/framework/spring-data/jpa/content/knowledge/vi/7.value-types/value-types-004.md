# Tập hợp kiểu cơ bản và đối tượng giá trị với @ElementCollection

Trong JPA, không phải mọi dữ liệu gắn với một entity đều cần trở thành một entity riêng. Nếu một thuộc tính là một tập hợp các giá trị đơn giản hoặc các đối tượng giá trị không có định danh độc lập, có thể ánh xạ bằng @ElementCollection. Cách này phù hợp với tag, tên phụ, số điện thoại, địa chỉ lưu nhanh, nhãn, cấu hình hoặc các giá trị thuộc riêng về một entity chủ.

Bài học tập trung vào hai loại phần tử: **kiểu cơ bản** (String, enum, số, ngày giờ và các kiểu được hỗ trợ hoặc chuyển đổi) và **đối tượng giá trị @Embeddable**. Các ví dụ dùng Jakarta Persistence với Spring Boot 3 / Spring Framework 6 trở lên, vì vậy import là jakarta.persistence.*. Dự án Spring Boot 2 cũ thường dùng javax.persistence.*; không trộn hai namespace trong cùng một ứng dụng.

## 1. @ElementCollection giải quyết vấn đề gì?

Giả sử một hồ sơ người dùng có nhiều tag. Một tag chỉ là một chuỗi gắn với hồ sơ đó; nó không có ID, không được chia sẻ như một đối tượng độc lập và không có vòng đời riêng. Nếu tạo một entity Tag chỉ để lưu từng chuỗi, mô hình sẽ có thêm identity, repository và quan hệ không cần thiết.

@ElementCollection cho phép JPA lưu một collection của:

- Kiểu cơ bản được JPA hỗ trợ, ví dụ String, Integer, BigDecimal, LocalDate, Boolean hoặc enum.
- Kiểu đối tượng giá trị được đánh dấu @Embeddable.

Các phần tử được lưu trong **collection table** riêng. Mỗi hàng của bảng này gắn với khóa chính của entity chủ thông qua khóa ngoại. JPA quản lý các hàng collection cùng vòng đời persistence của entity chủ.

Một element collection không có identity riêng. Phần tử là một giá trị thuộc về entity chủ, không phải một entity độc lập. Do đó, không thể khai báo @Id trên phần tử, không có repository riêng cho phần tử và không thể dùng quan hệ entity như @OneToMany để thay thế cho ngữ nghĩa value collection.

Ví dụ mô hình:

~~~text
user_profile
------------
id
display_name

user_profile_tags
-----------------
user_profile_id   -> user_profile.id
tag

user_profile_contacts
---------------------
user_profile_id   -> user_profile.id
position
kind
value
~~~

Bảng user_profile_tags lưu các chuỗi tag. Bảng user_profile_contacts lưu các trường của một đối tượng ContactMethod. Cả hai bảng đều phụ thuộc vào hàng user_profile.

## 2. Phân biệt kiểu cơ bản, đối tượng giá trị và entity

Ba khái niệm này có ranh giới khác nhau:

| Loại | Đặc điểm | Cách ánh xạ thường dùng |
|---|---|---|
| Kiểu cơ bản | Giá trị đơn như String, số, ngày, enum | @ElementCollection |
| Đối tượng giá trị | Gom nhiều thuộc tính thành một khái niệm, không có identity độc lập | @Embeddable kết hợp @ElementCollection |
| Entity | Có định danh ổn định, vòng đời và có thể được tham chiếu độc lập | @Entity cùng @OneToMany, @ManyToOne hoặc quan hệ phù hợp |

Ví dụ:

- Danh sách từ khóa của bài viết: các String, phù hợp với element collection.
- Danh sách địa chỉ giao hàng được lưu riêng trong hồ sơ và không được tham chiếu độc lập: có thể là collection của Address @Embeddable.
- Sản phẩm trong đơn hàng cần ID, trạng thái xử lý, giá tại thời điểm mua và được truy vấn độc lập: thường là OrderLine entity, không phải element collection.
- Danh mục dùng chung bởi nhiều sản phẩm và có vòng đời riêng: nên là Category entity và quan hệ entity.

Quyết định quan trọng không phải số lượng trường, mà là **giá trị đó có identity và vòng đời nghiệp vụ độc lập hay không**. Một đối tượng gồm nhiều trường vẫn có thể là value object; ngược lại, một đối tượng chỉ có hai trường vẫn có thể cần trở thành entity nếu được quản lý độc lập.

## 3. Ánh xạ collection của kiểu cơ bản

### 3.1. Collection của String

Ví dụ một hồ sơ lưu nhiều tag:

~~~java
import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import java.util.LinkedHashSet;
import java.util.Set;

@Entity
@Table(name = "user_profile")
public class UserProfile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "user_profile_tags",
        joinColumns = @JoinColumn(name = "user_profile_id"),
        uniqueConstraints = @UniqueConstraint(
            name = "uk_user_profile_tag",
            columnNames = {"user_profile_id", "tag"}
        )
    )
    @Column(name = "tag", nullable = false, length = 60)
    private Set<String> tags = new LinkedHashSet<>();

    protected UserProfile() {
    }

    public UserProfile(String displayName) {
        this.displayName = displayName;
    }

    public void addTag(String tag) {
        if (tag == null || tag.isBlank()) {
            throw new IllegalArgumentException("Tag must not be blank");
        }
        tags.add(tag.trim());
    }

    public void removeTag(String tag) {
        tags.remove(tag);
    }

    public Set<String> getTags() {
        return Set.copyOf(tags);
    }

    public Long getId() {
        return id;
    }
}
~~~

Ý nghĩa các annotation:

- @ElementCollection đánh dấu thuộc tính là collection của value, không phải quan hệ tới entity.
- fetch = FetchType.LAZY yêu cầu provider trì hoãn tải collection cho tới khi cần. LAZY là mặc định của ElementCollection; đây là fetch hint trong JPA, nên vẫn cần quan sát SQL thực tế của provider.
- @CollectionTable chỉ định bảng lưu collection và các cột nối về entity chủ.
- joinColumns khai báo khóa ngoại user_profile_id trỏ tới khóa chính của user_profile.
- @Column mô tả cột chứa từng giá trị phần tử.
- Set phù hợp khi giá trị không cần thứ tự và không được trùng trong mô hình Java. LinkedHashSet giữ thứ tự chèn trong bộ nhớ Java, nhưng nếu cần thứ tự bền vững qua lần đọc database thì phải ánh xạ thứ tự rõ ràng.
- uniqueConstraints tạo ràng buộc duy nhất trên cặp owner và tag ở database. Điều này bảo vệ tính duy nhất khi có nhiều luồng hoặc nhiều ứng dụng ghi dữ liệu.

JPA provider tạo SQL schema theo cấu hình và dialect. Khi dùng migration như Flyway hoặc Liquibase, hãy tạo bảng và constraint bằng migration thay vì dựa vào tự động tạo schema ở production.

### 3.2. Collection của enum

Enum cũng có thể là phần tử của element collection. Nên dùng EnumType.STRING để lưu tên enum dễ đọc và tránh lỗi thay đổi thứ tự phần tử enum:

~~~java
public enum Permission {
    READ,
    WRITE,
    APPROVE
}
~~~

~~~java
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "user_profile_permissions",
    joinColumns = @JoinColumn(name = "user_profile_id")
)
@Enumerated(EnumType.STRING)
@Column(name = "permission", nullable = false, length = 30)
private Set<Permission> permissions = new HashSet<>();
~~~

EnumType.ORDINAL lưu số thứ tự của hằng enum. Nếu thêm, xóa hoặc sắp xếp lại hằng enum, dữ liệu cũ có thể bị diễn giải sai. Chỉ dùng ordinal khi có lý do rõ ràng và kiểm soát chặt chẽ thứ tự enum.

### 3.3. Collection của số, ngày và kiểu cơ bản khác

Các kiểu cơ bản được hỗ trợ có thể dùng tương tự:

~~~java
@ElementCollection
@CollectionTable(
    name = "product_price_points",
    joinColumns = @JoinColumn(name = "product_id")
)
@Column(name = "price", precision = 12, scale = 2, nullable = false)
private List<BigDecimal> historicalPrices = new ArrayList<>();
~~~

~~~java
@ElementCollection
@CollectionTable(
    name = "user_profile_reminder_dates",
    joinColumns = @JoinColumn(name = "user_profile_id")
)
@Column(name = "reminder_date", nullable = false)
private Set<LocalDate> reminderDates = new HashSet<>();
~~~

Hãy chọn kiểu Java và kiểu cột phù hợp với ý nghĩa dữ liệu. Với tiền tệ, ưu tiên BigDecimal thay vì float/double. Với ngày giờ, chọn LocalDate, LocalDateTime, Instant hoặc OffsetDateTime theo quy tắc múi giờ của nghiệp vụ và khả năng của database.

Nếu một kiểu tùy chỉnh không được provider ánh xạ trực tiếp, có thể dùng AttributeConverter phù hợp. Converter cần chuyển đổi ổn định giữa kiểu Java và kiểu database; không nên lưu một object phức tạp thành chuỗi JSON nếu ứng dụng cần truy vấn từng trường bằng SQL mà không có chiến lược rõ ràng.

## 4. Ánh xạ Map của kiểu cơ bản

Element collection cũng có thể là Map. Ví dụ hồ sơ lưu các thiết lập dạng khóa và giá trị:

~~~java
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "user_profile_settings",
    joinColumns = @JoinColumn(name = "user_profile_id")
)
@MapKeyColumn(name = "setting_key", length = 80)
@Column(name = "setting_value", length = 300)
private Map<String, String> settings = new HashMap<>();
~~~

Trong ví dụ:

- @MapKeyColumn chỉ định cột lưu key của Map.
- @Column trên thuộc tính collection chỉ định cột lưu value.
- Mỗi hàng collection table chứa owner ID, setting key và setting value.
- Key phải duy nhất trong Map của một owner. Nếu cần bảo vệ ở database, hãy tạo unique constraint trên cặp user_profile_id và setting_key.

Map phù hợp với dữ liệu dạng dictionary nhỏ, ví dụ cặp tên cấu hình và giá trị. Nếu key hoặc value cần identity, quan hệ, validation phức tạp hay truy vấn nghiệp vụ độc lập, hãy xem xét entity riêng.

## 5. Đối tượng giá trị với @Embeddable

Khi một phần tử có nhiều thuộc tính, thay vì lưu từng thuộc tính trong các collection riêng biệt, hãy gom chúng vào một class @Embeddable. Ví dụ một hồ sơ có nhiều phương thức liên hệ:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class ContactMethod {

    @Column(name = "kind", nullable = false, length = 20)
    private String kind;

    @Column(name = "contact_value", nullable = false, length = 160)
    private String value;

    protected ContactMethod() {
    }

    public ContactMethod(String kind, String value) {
        if (kind == null || kind.isBlank()) {
            throw new IllegalArgumentException("Kind is required");
        }
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Value is required");
        }
        this.kind = kind;
        this.value = value;
    }

    public String getKind() {
        return kind;
    }

    public String getValue() {
        return value;
    }
}
~~~

@Embeddable đánh dấu class có thể được nhúng vào entity hoặc được dùng làm phần tử trong element collection. Class không khai báo @Id vì nó không có identity độc lập. Constructor không tham số với visibility protected là mẫu tương thích phổ biến với JPA; các field được ánh xạ theo access strategy của entity/embeddable.

Ánh xạ collection:

~~~java
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "user_profile_contacts",
    joinColumns = @JoinColumn(name = "user_profile_id")
)
@OrderColumn(name = "position")
private List<ContactMethod> contacts = new ArrayList<>();
~~~

Các field của ContactMethod trở thành các cột trong user_profile_contacts. Không cần tạo bảng contact_method riêng chỉ để lưu một value object thuộc hồ sơ.

Nếu muốn đặt tên cột khác với tên field trong embeddable, dùng @AttributeOverride hoặc @AttributeOverrides:

~~~java
@ElementCollection
@CollectionTable(
    name = "user_profile_saved_locations",
    joinColumns = @JoinColumn(name = "user_profile_id")
)
@AttributeOverrides({
    @AttributeOverride(
        name = "label",
        column = @Column(name = "location_label", nullable = false)
    ),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "city_name", nullable = false)
    )
})
private List<SavedLocation> savedLocations = new ArrayList<>();
~~~

Tên trong thuộc tính name của @AttributeOverride là thuộc tính Java bên trong embeddable. Tên column là tên cột cần dùng trong collection table. Nếu embeddable có thuộc tính lồng nhau, đường dẫn thuộc tính có thể được dùng để override theo quy tắc mapping của JPA.

## 6. Thứ tự phần tử: @OrderColumn và @OrderBy

Collection có thể là Set, List hoặc Map, nhưng cần phân biệt thứ tự trong Java với thứ tự được lưu trong database.

### 6.1. @OrderColumn lưu vị trí

Nếu nghiệp vụ cần giữ chính xác thứ tự người dùng sắp xếp, dùng @OrderColumn:

~~~java
@ElementCollection
@CollectionTable(
    name = "user_profile_contacts",
    joinColumns = @JoinColumn(name = "user_profile_id")
)
@OrderColumn(name = "position")
private List<ContactMethod> contacts = new ArrayList<>();
~~~

Database lưu thêm cột position. JPA sử dụng cột này để tái tạo thứ tự List khi tải collection. Khi chèn hoặc xóa một phần tử ở giữa, provider có thể phải cập nhật vị trí của nhiều hàng phía sau.

Dùng @OrderColumn cho thứ tự có ý nghĩa nghiệp vụ như thứ tự ưu tiên, thứ tự hiển thị hoặc thứ tự bước. Đừng dùng nó chỉ vì Java field đang khai báo List.

### 6.2. @OrderBy sắp xếp theo thuộc tính

@OrderBy yêu cầu sắp xếp collection theo một hoặc nhiều thuộc tính của phần tử:

~~~java
@ElementCollection
@CollectionTable(
    name = "user_profile_contacts",
    joinColumns = @JoinColumn(name = "user_profile_id")
)
@OrderBy("kind ASC")
private List<ContactMethod> contacts = new ArrayList<>();
~~~

Với @OrderBy, thứ tự được tính theo thuộc tính khi tải collection. Nó không lưu chỉ số vị trí do người dùng kéo thả.

Phân biệt:

| Annotation | Cách hoạt động | Trường hợp dùng |
|---|---|---|
| @OrderColumn | Lưu vị trí trong một cột thứ tự | Giữ thứ tự do người dùng sắp xếp |
| @OrderBy | Sắp xếp theo giá trị thuộc tính | Luôn hiển thị theo tên, ngày hoặc mức ưu tiên |

Không nên đặt cả hai annotation để giải quyết cùng một yêu cầu thứ tự. Chọn một mô hình phù hợp và kiểm tra SQL do provider tạo ra.

## 7. Collection table và khóa ngoại

@CollectionTable ánh xạ collection vào một bảng quan hệ. Các thuộc tính thường dùng:

- name: tên bảng collection.
- schema và catalog: schema/catalog nếu cần.
- joinColumns: một hoặc nhiều cột khóa ngoại về entity chủ.
- foreignKey: cấu hình tên và đặc tính khóa ngoại.
- uniqueConstraints: constraint duy nhất trên các cột.
- indexes: index phục vụ truy vấn.

Ví dụ:

~~~java
@ElementCollection
@CollectionTable(
    name = "article_labels",
    joinColumns = @JoinColumn(
        name = "article_id",
        nullable = false,
        foreignKey = @ForeignKey(name = "fk_article_labels_article")
    ),
    indexes = {
        @Index(
            name = "ix_article_labels_article",
            columnList = "article_id"
        ),
        @Index(
            name = "ix_article_labels_label",
            columnList = "label"
        )
    }
)
@Column(name = "label", nullable = false, length = 80)
private Set<String> labels = new HashSet<>();
~~~

Về mặt khái niệm, schema có dạng:

~~~sql
create table article_labels (
    article_id bigint not null,
    label varchar(80) not null,
    constraint fk_article_labels_article
        foreign key (article_id) references article(id)
);

create index ix_article_labels_article
    on article_labels(article_id);

create index ix_article_labels_label
    on article_labels(label);
~~~

Đây là DDL minh họa. Kiểu cột, tên constraint và cú pháp thực tế phụ thuộc database, dialect và migration. Với dữ liệu cần chống trùng, hãy bổ sung unique constraint phù hợp, ví dụ unique(article_id, label). Với truy vấn thường lọc theo owner ID và value, chọn index theo workload thực tế.

Entity chủ có khóa chính ghép thì joinColumns có thể gồm nhiều JoinColumn, tương ứng với các thành phần khóa. Tên và kiểu cột phải khớp với khóa được tham chiếu.

## 8. Quản lý collection qua entity chủ trong Spring Data JPA

Repository vẫn dành cho entity chủ. Không tạo repository cho String, ContactMethod hoặc value object trong collection.

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserProfileRepository
        extends JpaRepository<UserProfile, Long> {
}
~~~

Một service thay đổi collection:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserProfileService {

    private final UserProfileRepository repository;

    public UserProfileService(UserProfileRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void addTag(Long id, String tag) {
        UserProfile profile = repository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException(
                "User profile not found"
            ));

        profile.addTag(tag);
        // profile đang managed; dirty checking ghi thay đổi khi flush/commit.
    }

    @Transactional
    public void addContact(Long id, ContactMethod contact) {
        UserProfile profile = repository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException(
                "User profile not found"
            ));

        profile.addContact(contact);
    }
}
~~~

Khi entity chủ đang managed trong transaction, thay đổi collection được phát hiện bởi persistence context và đồng bộ khi flush/commit. Không cần gọi repository.save(profile) sau mọi lần thay đổi một entity đã managed. Tuy vậy, save có thể được dùng ở ranh giới tạo mới hoặc khi làm việc với object detached theo thiết kế repository; hiểu rõ persist/merge và trạng thái entity trước khi gọi.

Nếu collection được khởi tạo lazy, việc thêm/xóa phần tử có thể khiến provider cần tải trạng thái collection hiện tại để tính toán thay đổi. Không nên giả định thao tác add luôn chỉ sinh một INSERT đơn giản.

## 9. Truy vấn element collection

JPQL có thể join qua collection của entity chủ:

~~~java
@Query("""
    select distinct p
    from UserProfile p
    left join fetch p.tags
    where p.id = :id
    """)
Optional<UserProfile> findByIdWithTags(@Param("id") Long id);
~~~

Fetch join tải collection cùng entity trong một truy vấn. Từ đó service có thể chuyển dữ liệu sang DTO trước khi transaction kết thúc.

Có thể dùng EntityGraph:

~~~java
@EntityGraph(attributePaths = "tags")
@Query("select p from UserProfile p where p.id = :id")
Optional<UserProfile> findProfileWithTags(@Param("id") Long id);
~~~

Với collection embeddable, có thể fetch collection tương tự:

~~~java
@Query("""
    select distinct p
    from UserProfile p
    left join fetch p.contacts
    where p.id = :id
    """)
Optional<UserProfile> findByIdWithContacts(@Param("id") Long id);
~~~

Collection join làm số hàng kết quả tăng lên: một entity chủ có nhiều phần tử sẽ xuất hiện trên nhiều hàng SQL. Vì vậy dùng distinct để tránh entity trùng trong kết quả JPQL khi cần.

### 9.1. Tìm owner theo một giá trị collection

Có thể join để tìm các hồ sơ có một tag:

~~~java
@Query("""
    select distinct p
    from UserProfile p
    join p.tags tag
    where tag = :tag
    """)
List<UserProfile> findProfilesWithTag(@Param("tag") String tag);
~~~

Có thể truy vấn trực tiếp phần tử qua join trong JPQL, nhưng phần tử vẫn không phải entity root có identity độc lập. Truy vấn và vòng đời của nó vẫn thuộc ngữ cảnh entity chủ.

### 9.2. Fetch collection và phân trang

Cần thận trọng khi kết hợp fetch join một collection với Pageable. Một entity chủ có nhiều phần tử tạo ra nhiều hàng SQL, khiến database pagination không còn tương ứng đơn giản với số entity. Một số provider có thể cảnh báo hoặc phải xử lý phân trang trong bộ nhớ.

Các cách an toàn hơn:

1. Phân trang danh sách ID hoặc entity chủ trước.
2. Truy vấn collection cho tập ID đã lấy.
3. Dùng DTO/projection nếu màn hình chỉ cần một phần dữ liệu.
4. Dùng batch fetching theo khả năng provider nếu phù hợp.

Không fetch join nhiều collection lớn cùng lúc nếu chưa hiểu số hàng kết quả và giới hạn của provider.

## 10. Vòng đời và cập nhật phần tử

Element collection thuộc entity chủ:

- Khi thêm phần tử vào collection managed, JPA đồng bộ hàng collection tương ứng khi flush.
- Khi xóa phần tử, JPA đồng bộ việc loại bỏ giá trị khỏi collection table.
- Khi thay đổi thuộc tính của một embeddable managed trong collection, provider phải đồng bộ trạng thái collection theo mapping.
- Khi xóa entity chủ bằng thao tác entity thông thường, các hàng collection thuộc nó được xử lý theo quan hệ sở hữu và mapping của JPA/provider.
- Không có cascade attribute như quan hệ entity, vì phần tử không phải entity độc lập.
- Không dùng orphanRemoval cho ElementCollection; khái niệm orphan removal thuộc quan hệ entity như OneToMany/OneToOne.

Chi tiết SQL để cập nhật collection phụ thuộc provider và cách collection được thay đổi. Provider có thể thực hiện các thao tác DELETE/INSERT theo collection hoặc tối ưu theo phần tử. Nếu collection lớn, thường xuyên cập nhật một phần nhỏ hoặc cần audit từng phần tử, mô hình entity con có thể phù hợp hơn.

Một bulk JPQL update/delete tác động trực tiếp lên database và bỏ qua lifecycle/dirty checking của các entity đang managed. Sau bulk operation, persistence context có thể chứa trạng thái cũ; cân nhắc clear/refresh và xử lý collection table/foreign key theo schema thực tế.

## 11. Validation và tính toàn vẹn dữ liệu

Collection table cần được thiết kế như mọi bảng quan hệ khác:

- Độ dài cột phù hợp với dữ liệu.
- NOT NULL cho giá trị bắt buộc.
- UNIQUE khi một owner không được lặp giá trị.
- Foreign key về owner.
- Index cho truy vấn theo owner hoặc theo value.
- Quy tắc chuẩn hóa chuỗi nếu so sánh không phân biệt hoa thường.
- Kiểu số/ngày phù hợp với miền giá trị.

Validation ở Java giúp báo lỗi sớm và thân thiện, nhưng không thay thế constraint database. Khi có nhiều instance ứng dụng hoặc concurrent request, database constraint mới là hàng rào cuối cùng bảo vệ tính toàn vẹn.

Với collection embeddable, validation có thể đặt trên field bên trong embeddable và kích hoạt cascade validation từ entity chủ theo Bean Validation. Ví dụ:

~~~java
@Embeddable
public class ContactMethod {

    @NotBlank
    @Column(name = "kind", nullable = false, length = 20)
    private String kind;

    @NotBlank
    @Column(name = "contact_value", nullable = false, length = 160)
    private String value;

    protected ContactMethod() {
    }
}
~~~

~~~java
@ElementCollection
@Valid
@CollectionTable(
    name = "user_profile_contacts",
    joinColumns = @JoinColumn(name = "user_profile_id")
)
private List<ContactMethod> contacts = new ArrayList<>();
~~~

Cần có dependency Bean Validation phù hợp, ví dụ starter validation của Spring Boot. @Valid yêu cầu validation đi sâu vào từng phần tử. Constraint database vẫn cần được khai báo bằng migration hoặc mapping.

## 12. Hiệu năng và giới hạn thiết kế

### 12.1. Collection nhỏ và ít thay đổi

ElementCollection rất phù hợp khi collection nhỏ, thuộc riêng một owner và thường được đọc cùng entity đó. Ví dụ danh sách tag, ngôn ngữ ưa thích, cặp cấu hình hoặc các value object nhỏ.

### 12.2. Collection lớn hoặc được truy vấn thường xuyên

Nếu một entity có hàng chục nghìn phần tử, việc tải cả collection có thể tốn bộ nhớ và thời gian. ElementCollection thường được xử lý như một đơn vị thuộc owner; API repository không cung cấp repository riêng cho phần tử.

Nếu cần tìm kiếm, phân trang, cập nhật, khóa hoặc audit từng phần tử độc lập, hãy cân nhắc chuyển thành entity.

### 12.3. N+1 query

Nếu tải một danh sách owner rồi truy cập collection lazy của từng owner, có thể phát sinh một truy vấn cho mỗi owner. Đây là một dạng N+1.

Cách xử lý:
- Dùng fetch join khi lấy một owner hoặc một tập nhỏ phù hợp.
- Dùng EntityGraph cho use case cần collection.
- Dùng projection/DTO khi chỉ cần dữ liệu cụ thể.
- Dùng batch fetching của provider nếu được hỗ trợ và đã kiểm tra.
- Đo SQL thật thay vì chỉ nhìn số lần gọi repository.

### 12.4. Nhiều collection và Cartesian multiplication

Fetch join nhiều collection trong một truy vấn có thể nhân số hàng kết quả. Ví dụ một owner có 5 tag và 4 contact có thể tạo 20 hàng SQL cho cùng owner. Với Hibernate, fetch đồng thời nhiều bag collection còn có thể gây MultipleBagFetchException tùy mapping. Đây là hành vi riêng của provider, không phải quy tắc chung của JPA.

Tách truy vấn, dùng DTO hoặc batch fetch thường dễ kiểm soát hơn.

### 12.5. Transaction và lazy loading

Nếu truy cập collection lazy sau khi persistence context đóng, có thể gặp LazyInitializationException trong Hibernate. Tải dữ liệu cần thiết bên trong service transaction rồi trả DTO là cách thiết kế rõ ràng.

Không bật Open EntityManager in View chỉ để che lỗi lazy loading mà chưa hiểu query phát sinh ở tầng web. OSIV có thể khiến truy vấn chạy trong quá trình serialize response và làm N+1 khó phát hiện.

## 13. So sánh @ElementCollection với @OneToMany

| Tiêu chí | @ElementCollection | @OneToMany |
|---|---|---|
| Phần tử | Basic hoặc @Embeddable | Entity |
| Identity riêng | Không | Có |
| @Id trên phần tử | Không | Có trên entity con |
| Repository riêng | Không | Có thể có |
| Vòng đời | Gắn với owner | Có thể được quản lý độc lập tùy quan hệ/cascade |
| Cascade | Không khai báo cascade entity | Có thể cấu hình cascade |
| orphanRemoval | Không áp dụng | Có thể áp dụng trong quan hệ phù hợp |
| Truy vấn độc lập | Thường join từ owner | Có thể truy vấn entity con trực tiếp |
| Mô hình phù hợp | Giá trị thuộc riêng owner | Đối tượng con có identity/hành vi/vòng đời riêng |

Ví dụ một danh sách số điện thoại đơn giản chỉ là giá trị thuộc hồ sơ có thể dùng ElementCollection. Nếu mỗi số điện thoại có trạng thái xác minh, thời điểm xác minh, lịch sử thay đổi, quyền sở hữu hoặc được các phần khác tham chiếu trực tiếp, hãy cân nhắc PhoneNumber entity và @OneToMany.

## 14. Kiểm thử với Spring Data JPA

Một test repository có thể kiểm tra việc lưu và tải collection:

~~~java
@DataJpaTest
class UserProfileRepositoryTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private UserProfileRepository repository;

    @Test
    void persistsBasicAndEmbeddableCollections() {
        UserProfile profile = new UserProfile("Ada");
        profile.addTag("java");
        profile.addContact(new ContactMethod("EMAIL", "ada@example.test"));

        entityManager.persist(profile);
        entityManager.flush();
        entityManager.clear();

        UserProfile loaded = repository.findByIdWithTags(profile.getId())
            .orElseThrow();

        assertThat(loaded.getTags()).contains("java");
    }
}
~~~

Đây là đoạn test minh họa cần các import và dependency test của Spring Boot. Nếu muốn kiểm tra collection embeddable, truy vấn cần fetch contacts hoặc thực hiện trong transaction còn mở trước khi assert. Test nên flush và clear để bảo đảm dữ liệu thực sự được ghi và đọc lại từ database, thay vì chỉ kiểm tra object còn trong persistence context.

Nên kiểm thử thêm:
- Owner không có phần tử.
- Thêm, xóa và thay đổi phần tử.
- Unique constraint khi thêm giá trị trùng.
- Xóa owner và xác nhận hàng collection được xử lý.
- Tải lazy và fetch plan của từng use case.
- Concurrent update nếu collection có yêu cầu nhất quán đặc biệt.
- Migration trên database gần production, không chỉ H2.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tạo được mapping | Dùng @ElementCollection cho một entity | Chuyển sang @OneToMany/@ManyToMany hoặc mapping entity phù hợp |
| Lỗi entity không được quản lý | Dùng @Entity thay vì @Embeddable cho value object trong collection | Dùng @Embeddable cho phần tử không có identity |
| Sai tên bảng/cột | Dựa vào default naming không đúng với schema | Khai báo rõ @CollectionTable, @JoinColumn và @Column |
| Duplicate key khi insert | Thiết kế unique constraint không phù hợp hoặc dữ liệu trùng | Xác định quy tắc trùng, chuẩn hóa dữ liệu và xử lý constraint |
| Thứ tự List thay đổi sau khi tải | Không lưu thứ tự nhưng nghiệp vụ lại yêu cầu thứ tự cố định | Dùng @OrderColumn hoặc @OrderBy đúng mục đích |
| LazyInitializationException | Đọc collection ngoài persistence context | Fetch trong transaction và chuyển sang DTO |
| N+1 query | Truy cập collection lazy trong vòng lặp | Fetch join, EntityGraph, batch fetch hoặc projection |
| Query phân trang chậm/sai | Fetch join collection cùng Pageable | Phân trang owner trước, rồi tải collection theo ID |
| Bảng collection quá lớn | Dùng value collection cho dữ liệu có lifecycle độc lập | Chuyển phần tử thành entity và thiết kế truy vấn riêng |
| Nhiều SQL khi sửa một phần tử | Provider đồng bộ collection theo chiến lược riêng | Đo SQL; dùng entity con nếu cập nhật từng dòng thường xuyên |

## 16. Quy tắc lựa chọn và checklist

Chọn @ElementCollection khi tất cả hoặc phần lớn điều kiện sau đúng:

- Phần tử là basic type hoặc embeddable.
- Phần tử không cần primary key và identity riêng.
- Phần tử không được tham chiếu độc lập từ các entity khác.
- Vòng đời của phần tử gắn với owner.
- Collection có kích thước hợp lý và thường được thao tác cùng owner.
- Truy vấn, phân trang hoặc cập nhật độc lập từng phần tử không phải nhu cầu chính.

Chọn entity con khi có một hoặc nhiều nhu cầu:

- Phần tử cần ID riêng.
- Phần tử được nhiều entity tham chiếu.
- Phần tử có trạng thái, lifecycle hoặc hành vi nghiệp vụ riêng.
- Cần repository, phân trang, khóa hoặc audit từng phần tử.
- Collection rất lớn hoặc cập nhật thường xuyên từng dòng.

Checklist trước khi đưa mapping vào ứng dụng:

- [ ] Xác định phần tử là basic, embeddable hay entity.
- [ ] Xác định rõ owner và collection table.
- [ ] Khai báo tên bảng, join column và tên cột rõ ràng.
- [ ] Chọn Set/List/Map theo ngữ nghĩa nghiệp vụ.
- [ ] Dùng @OrderColumn nếu cần lưu thứ tự người dùng sắp xếp.
- [ ] Dùng @OrderBy nếu chỉ cần sắp xếp theo thuộc tính.
- [ ] Bổ sung unique constraint, foreign key và index phù hợp.
- [ ] Kiểm tra LAZY và fetch plan trong transaction.
- [ ] Tránh fetch join collection khi phân trang mà chưa đánh giá.
- [ ] Dùng DTO cho response thay vì để tầng web tùy ý tải lazy collection.
- [ ] Đánh giá kích thước collection và tần suất cập nhật.
- [ ] Viết test flush/clear để xác nhận dữ liệu được lưu thực sự.
- [ ] Dùng migration để quản lý schema production.

## 17. Kết luận

@ElementCollection là lựa chọn phù hợp để ánh xạ tập hợp các giá trị thuộc về một entity chủ. Với kiểu cơ bản, JPA lưu trực tiếp giá trị trong collection table. Với đối tượng giá trị, @Embeddable gom nhiều thuộc tính thành một phần tử có ý nghĩa trong domain. Cả hai loại đều không có identity riêng và vòng đời gắn với owner.

Hãy dùng @ElementCollection cho dữ liệu nhỏ, phụ thuộc owner và không cần thao tác độc lập. Khi phần tử cần identity, lifecycle, repository, truy vấn hoặc cập nhật riêng, hãy mô hình hóa nó thành entity và dùng quan hệ entity. Thiết kế đúng ranh giới này giúp mapping đơn giản, truy vấn dễ dự đoán và tránh biến một value collection thành một mô hình entity phức tạp không cần thiết.
