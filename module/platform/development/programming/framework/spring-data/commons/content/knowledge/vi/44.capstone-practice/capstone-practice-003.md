# Triển khai CRUD chọn lọc và giao diện cơ sở

## 1. Mục tiêu bài thực hành

Trong ứng dụng quản lý học tập, không phải repository nào cũng nên cung cấp toàn bộ thao tác CRUD. Khóa học có thể được tạo, đọc và chỉnh sửa nhưng không được xóa trực tiếp. Danh mục khóa học có thể chỉ được đọc bởi ứng dụng hiện tại, còn việc cập nhật thuộc một quy trình quản trị riêng.

Bài thực hành sử dụng các abstraction của Spring Data Commons để xây dựng hợp đồng phù hợp với các nhu cầu đó:

- Tạo interface nền chỉ có các thao tác đọc theo ID.
- Mở rộng thêm `save` cho nhóm repository được phép ghi.
- Dùng `@NoRepositoryBean` cho interface generic dùng chung.
- Thêm derived query, phân trang và projection tại repository cụ thể.
- Kiểm chứng cả bề mặt API và hành vi trên store.

Phần thiết kế interface dùng abstraction Commons. Phần model và integration minh họa chọn **Spring Data JPA** để có một đường thực thi cụ thể. Khi áp dụng vào module khác, cần thay mapping, cấu hình và kiểm tra khả năng hỗ trợ tương ứng.

## 2. Chốt yêu cầu trước khi chọn interface cha

### 2.1. Hợp đồng mong muốn

| Repository | Cho phép | Không công khai trong hợp đồng này |
| --- | --- | --- |
| Khóa học | Đọc theo ID, kiểm tra ID, lưu mới/cập nhật, tìm theo mã, liệt kê có giới hạn | Xóa, xóa tất cả, lưu hàng loạt, đọc toàn bộ không giới hạn |
| Danh mục | Đọc theo ID, kiểm tra ID, đọc danh mục đang bật | Lưu và mọi thao tác xóa |

Với khóa học, “CRUD chọn lọc” ở đây là chọn các khả năng tạo/đọc/cập nhật cần thiết, còn xóa được thay bằng hành vi nghiệp vụ lưu trữ khóa học. Không bắt buộc một repository phải công khai đủ bốn nhóm thao tác chỉ vì nó truy cập dữ liệu.

Giới hạn interface giúp người viết code không vô tình gọi thao tác ngoài hợp đồng. Nó không thay thế authorization, quyền truy cập database hoặc ràng buộc dữ liệu. Một thành phần khác có quyền dùng `EntityManager` hay repository khác vẫn có thể ghi/xóa nếu thiết kế hệ thống cho phép.

### 2.2. Vì sao không kế thừa `CrudRepository` rồi bỏ qua method không dùng?

Khi kế thừa `CrudRepository`, các method CRUD đã trở thành một phần của API kế thừa. Không khai báo lại `deleteAll()` trong interface con không làm method đó biến mất.

Override rồi ném `UnsupportedOperationException` cũng vẫn để method hiện diện và dời lỗi tới runtime. Nếu yêu cầu là không cho consumer gọi thao tác đó qua interface, nên thiết kế interface hẹp ngay từ đầu.

## 3. Tạo interface đọc nền

```java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

import java.util.Optional;

@NoRepositoryBean
public interface ReadByIdRepository<T, ID> extends Repository<T, ID> {

    Optional<T> findById(ID id);

    boolean existsById(ID id);
}
```

`Repository<T, ID>` là interface đánh dấu. Nó cho biết domain type cùng ID type mà không mang theo toàn bộ method của `CrudRepository`.

Hai method được sao chép theo hợp đồng CRUD quen thuộc. Với module hỗ trợ các thao tác cơ sở tương ứng, Spring Data có thể nối chúng tới implementation cơ sở của repository. Ứng dụng không cần tự viết một lớp tìm theo ID cho từng entity chỉ vì không kế thừa toàn bộ CRUD interface.

`findById` làm việc với định danh được mapping của entity. Không suy ra nó luôn là một derived query thông thường dựa trên field có tên Java `id`.

### Vai trò của `@NoRepositoryBean`

Interface nền chưa chốt domain type và ID type. Annotation cho biết Spring Data không nên tạo nó thành một repository cụ thể.

Annotation này không tạo implementation riêng, không chọn store và không áp đặt quyền chỉ đọc tại database. Repository cụ thể vẫn cần được factory của module phát hiện và tạo bean.

## 4. Mở rộng thêm khả năng lưu

```java
@NoRepositoryBean
public interface SaveByIdRepository<T, ID>
        extends ReadByIdRepository<T, ID> {

    <S extends T> S save(S entity);
}
```

Chữ ký generic của `save` giữ hợp đồng nhận một subtype của domain type và trả lại kiểu tương ứng. Đây là cách sao chép có chủ đích một phần API cơ sở.

Không tự thêm `delete`, `saveAll` hoặc `findAll` vào interface nền chỉ vì một repository tương lai có thể cần. Những khả năng dùng chung nên phản ánh nhu cầu đã xác định, tránh khiến mọi consumer nhận quyền thao tác rộng hơn.

Sơ đồ kế thừa:

```text
Repository<T, ID>
    -> ReadByIdRepository<T, ID>
        -> SaveByIdRepository<T, ID>
            -> CourseRepository
        -> CategoryRepository
```

Hai interface nền được đánh dấu `@NoRepositoryBean`. Hai repository cụ thể sẽ chốt kiểu và được tạo bean khi cấu hình store phù hợp.

## 5. Mô hình khóa học minh họa bằng JPA

### 5.1. Trạng thái nghiệp vụ

```java
public enum CourseStatus {
    DRAFT,
    ARCHIVED
}
```

Trong phạm vi bài, khóa học mới ở trạng thái nháp. Khi không tiếp tục sử dụng, ứng dụng chuyển sang `ARCHIVED` thay vì công khai thao tác xóa trực tiếp.

### 5.2. Entity

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import jakarta.persistence.Version;

@Entity
@Table(
    name = "course",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_course_code",
        columnNames = "course_code"
    )
)
public class Course {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "course_code", nullable = false, updatable = false)
    private String code;

    @Column(nullable = false)
    private String title;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private CourseStatus status;

    @Version
    private Long version;

    protected Course() {
    }

    public Course(String code, String title) {
        this.code = required(code, "Mã khóa học");
        this.title = required(title, "Tên khóa học");
        this.status = CourseStatus.DRAFT;
    }

    public void rename(String title) {
        if (status == CourseStatus.ARCHIVED) {
            throw new IllegalStateException("Khóa học đã được lưu trữ");
        }
        this.title = required(title, "Tên khóa học");
    }

    public void archive() {
        this.status = CourseStatus.ARCHIVED;
    }

    private static String required(String value, String label) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(label + " không được rỗng");
        }
        return value.strip();
    }

    public Long getId() {
        return id;
    }

    public String getCode() {
        return code;
    }

    public String getTitle() {
        return title;
    }

    public CourseStatus getStatus() {
        return status;
    }

    public Long getVersion() {
        return version;
    }
}
```

Ví dụ dùng Jakarta Persistence và Java có các API chuỗi tương ứng. Chiến lược sinh ID phải được cơ sở dữ liệu/provider hỗ trợ trong môi trường thực hành.

`@Version` trong ví dụ là annotation của JPA. Không thay nó bằng một annotation có cùng tên đơn giản từ module khác rồi mặc định semantics giữ nguyên.

Unique constraint mô tả yêu cầu mã không trùng. Khi dùng migration quản lý schema, cần tạo ràng buộc tương ứng trong schema thực tế; không mặc định annotation luôn tự thay đổi database đang chạy.

Quy tắc mã ở đây giữ nguyên hoa thường sau khi bỏ khoảng trắng hai đầu. Nếu nghiệp vụ muốn không phân biệt hoa thường, cần định nghĩa chuẩn hóa và ràng buộc datastore phù hợp, thay vì chỉ thay một query thành `IgnoreCase`.

## 6. Repository cụ thể và projection danh sách

### 6.1. Projection cho màn hình danh sách

```java
public interface CourseSummary {
    Long getId();
    String getCode();
    String getTitle();
    CourseStatus getStatus();
}
```

### 6.2. Repository khóa học

```java
public interface CourseRepository
        extends SaveByIdRepository<Course, Long> {

    Optional<Course> findByCode(String code);

    boolean existsByCode(String code);

    Slice<CourseSummary> findByStatus(
        CourseStatus status,
        Pageable pageable
    );
}
```

Các import thông dụng được lược bỏ. Trong ví dụ JPA này, `findByCode`, `existsByCode` và `findByStatus` là các query method theo thuộc tính Java của `Course`.

Tên field Java là `code` dù cột lưu trữ được đặt tên `course_code`. Derived query không được viết theo tên cột SQL.

`Slice` phù hợp với yêu cầu danh sách chỉ cần biết còn phần tiếp hay không. Nếu sản phẩm cần tổng chính xác, có thể chọn `Page` cùng chi phí và cách kiểm chứng tương ứng. Không đổi kiểu chỉ để tránh một query đếm khi tổng vẫn thuộc hợp đồng.

Không có `findAll()` không giới hạn trong interface. Consumer muốn liệt kê khóa học phải đi qua query đã được thiết kế cho nhu cầu danh sách.

Projection cũng cần được kiểm chứng trên query và module thực tế. Việc khai báo một interface projection không tự cam kết mọi store sẽ đọc đúng số field hoặc tạo cùng hình dạng query.

## 7. Repository chỉ đọc cho danh mục

Một model JPA đơn giản:

```java
@Entity
public class Category {

    @Id
    private Long id;

    @Column(nullable = false)
    private String name;

    private boolean enabled;

    protected Category() {
    }

    public Category(Long id, String name, boolean enabled) {
        this.id = id;
        this.name = name;
        this.enabled = enabled;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public boolean isEnabled() {
        return enabled;
    }
}
```

```java
public interface CategoryRepository
        extends ReadByIdRepository<Category, Long> {

    List<Category> findByEnabledTrueOrderByNameAsc();
}
```

Repository danh mục không nhận `save` vì không kế thừa interface nền có ghi. Việc khởi tạo dữ liệu danh mục có thể thuộc migration, quy trình quản trị hoặc fixture test riêng.

Danh sách trong ví dụ giả định tập danh mục nhỏ và có giới hạn nghiệp vụ hợp lý. Nếu tập đó tăng lớn, cần đổi hợp đồng truy vấn để có giới hạn/phân trang thay vì coi mọi method trả `List` là phù hợp vô thời hạn.

“Chỉ đọc” ở đây là bề mặt repository. Trong JPA, đối tượng được quản lý có thể tham gia cơ chế dirty checking nếu bị thay đổi trong một phạm vi ghi phù hợp. Không dùng việc thiếu method `save` làm ranh giới bảo mật duy nhất.

## 8. Service công khai lệnh nghiệp vụ thay vì thao tác tùy ý

### 8.1. DTO tại biên ứng dụng

```java
public record CourseDetail(
    Long id,
    String code,
    String title,
    CourseStatus status
) {
    static CourseDetail from(Course course) {
        return new CourseDetail(
            course.getId(),
            course.getCode(),
            course.getTitle(),
            course.getStatus()
        );
    }
}
```

```java
public record CourseListItem(
    Long id,
    String code,
    String title,
    CourseStatus status
) {
}
```

Các DTO chỉ giữ giá trị cần trả, tránh buộc tầng bên ngoài phụ thuộc trực tiếp vào entity và tài nguyên persistence. Ví dụ không đưa version vào response được chụp trước flush; nếu API cần version để phát hiện chỉnh sửa từ client cũ, phải thiết kế riêng mốc lấy version và hợp đồng cập nhật.

### 8.2. Tạo, đổi tên và lưu trữ

```java
@Service
@Transactional(readOnly = true)
public class CourseService {

    private final CourseRepository courses;

    public CourseService(CourseRepository courses) {
        this.courses = courses;
    }

    @Transactional
    public CourseDetail create(String code, String title) {
        Course saved = courses.save(new Course(code, title));
        return CourseDetail.from(saved);
    }

    public CourseDetail get(Long id) {
        return CourseDetail.from(requiredCourse(id));
    }

    @Transactional
    public CourseDetail rename(Long id, String newTitle) {
        Course course = requiredCourse(id);
        course.rename(newTitle);

        Course saved = courses.save(course);
        return CourseDetail.from(saved);
    }

    @Transactional
    public void archive(Long id) {
        Course course = requiredCourse(id);
        course.archive();
        courses.save(course);
    }

    public Slice<CourseListItem> list(
            CourseStatus status, int page, int size) {
        if (status == null || page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException("Bộ lọc hoặc phân trang sai");
        }

        Pageable pageable = PageRequest.of(
            page,
            size,
            Sort.by(
                Sort.Order.asc("title"),
                Sort.Order.asc("id")
            )
        );

        return courses.findByStatus(status, pageable)
            .map(summary -> new CourseListItem(
                summary.getId(),
                summary.getCode(),
                summary.getTitle(),
                summary.getStatus()
            ));
    }

    private Course requiredCourse(Long id) {
        return courses.findById(id)
            .orElseThrow(() ->
                new IllegalArgumentException("Không tìm thấy khóa học"));
    }
}
```

Ví dụ dùng transaction của Spring Framework, giả định service được gọi qua proxy và transaction manager JPA phù hợp. Các import được lược bỏ.

Với JPA, thay đổi entity đã được quản lý có thể được ghi qua dirty checking. Ví dụ vẫn gọi `save` để thể hiện hợp đồng ghi mà bài đang thực hành, đồng thời sử dụng đối tượng trả về thay vì mặc định mọi implementation đều trả chính tham chiếu đầu vào.

Transaction ghi có thể chỉ bộc lộ một số lỗi ở flush hoặc commit. Caller cần xử lý kết quả của cả ranh giới giao dịch, không coi việc chạy qua dòng `save()` là bằng chứng commit thành công.

Service không có method xóa. Lệnh `archive` mô tả ý định nghiệp vụ và thay đổi trạng thái có kiểm soát. Authorization cần được áp dụng tại biên phù hợp trong ứng dụng thực tế.

## 9. Ràng buộc và kiểm tra tồn tại có vai trò khác nhau

`existsByCode` có thể dùng để phản hồi sớm theo trải nghiệm sản phẩm. Tuy nhiên, chuỗi kiểm tra rồi lưu vẫn có khoảng cạnh tranh:

```text
A kiểm tra mã -> chưa có
B kiểm tra mã -> chưa có
A tạo khóa học
B cũng tạo khóa học
```

Ràng buộc duy nhất tại datastore vẫn cần bảo vệ yêu cầu không trùng mã. Nếu ánh xạ lỗi thành thông báo nghiệp vụ, cần phân biệt đúng ràng buộc gây lỗi, không biến mọi lỗi ghi thành “mã đã tồn tại”.

Tương tự, `existsById` rồi `findById` không bảo đảm dữ liệu giữ nguyên giữa hai thao tác và có thể tạo thêm truy cập. Khi cần đối tượng để sửa, đọc một lần bằng `findById` rồi xử lý trường hợp không có thường rõ hơn.

Version hỗ trợ phát hiện cập nhật cạnh tranh theo cơ chế JPA. Nó không tự giải quyết request lặp hoặc mọi bất biến trên nhiều bản ghi. Không thêm retry vô điều kiện cho mọi lỗi chỉ vì entity có version.

## 10. Cấu hình repository và model cho store đã chọn

Một cấu hình minh họa trong Spring Boot dùng JPA:

```java
@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
    basePackageClasses = {
        CourseRepository.class,
        CategoryRepository.class
    }
)
@EntityScan(basePackageClasses = {Course.class, Category.class})
class LearningRepositoryConfiguration {
}
```

Class cấu hình phải được nạp bằng scan hoặc import. `@EntityScan` là hỗ trợ của Spring Boot; package import cần phù hợp với phiên bản ứng dụng. Datasource, provider và các bean hạ tầng cũng phải được cấu hình.

Các repository cụ thể không được gắn trực tiếp `@NoRepositoryBean`. Hai interface nền có annotation đó để tránh tạo bean generic không hoàn chỉnh.

Không cần thêm `@Repository` vào từng interface chỉ để Spring Data có thể tạo implementation khi repository scanning đã được cấu hình đúng.

### Khi ứng dụng có nhiều store

Các interface nền chỉ kế thừa `Repository` chung, nên không tự chọn JPA, MongoDB hay một module khác. Nếu nhiều repository factory cùng xuất hiện, cần giới hạn package, mapping và cấu hình để mỗi repository thuộc đúng store.

Trong ví dụ JPA, annotation `@Entity` và phạm vi `@EnableJpaRepositories` là các tín hiệu có liên quan. Nếu chuyển sang document store, cần thiết kế mapping cùng factory tương ứng, không giữ nguyên annotation JPA rồi kỳ vọng chỉ đổi dependency là đủ.

Hợp đồng chọn lọc có thể dùng lại về mặt ý định, nhưng hỗ trợ derived query, projection, transaction, auditing và version phải được xác nhận theo module thực tế.

## 11. Kiểm chứng bề mặt API

Những lời gọi sau không thuộc hợp đồng vừa thiết kế:

```java
// Các dòng minh họa lỗi biên dịch; không đưa vào source test cần compile.
courseRepository.deleteAll();
courseRepository.saveAll(courses);
courseRepository.findAll();
categoryRepository.save(category);
```

Mục tiêu là lỗi được phát hiện khi consumer cố gọi qua interface đó, thay vì chỉ thất bại lúc chạy.

Có thể bổ sung một test hợp đồng API để giữ danh sách method cấm:

```java
@Test
void doesNotExposeUnboundedOrDestructiveMethods() {
    Set<String> methods = Arrays.stream(CourseRepository.class.getMethods())
        .map(Method::getName)
        .collect(Collectors.toSet());

    assertThat(methods).doesNotContain(
        "delete",
        "deleteById",
        "deleteAll",
        "saveAll",
        "findAll"
    );
}
```

Ví dụ dùng JUnit Jupiter và AssertJ, lược bỏ import. Test này bảo vệ yêu cầu cụ thể về bề mặt API. Nó không chứng minh quyền datastore, query hay transaction, nên cần các test hành vi bổ sung.

Nếu sau này có nhu cầu batch có kiểm soát, không nên sửa test cho qua rồi thêm mọi method vào base interface. Hãy xác định repository hoặc capability nào thực sự cần mở rộng và giới hạn của nó.

## 12. Integration test các method được sao chép và query bổ sung

### 12.1. Lưu rồi đọc lại bằng interface chọn lọc

Trong một test JPA có repository thật, `EntityManager` và transaction test phù hợp:

```java
@Test
void savesAndReadsCourseThroughSelectiveContract() {
    Course saved = courses.save(
        new Course("JAVA-101", "Java nền tảng")
    );
    Long id = saved.getId();

    entityManager.flush();
    entityManager.clear();

    assertThat(courses.findById(id))
        .get()
        .extracting(Course::getCode)
        .isEqualTo("JAVA-101");
}
```

Ví dụ dùng assertion của AssertJ, giả định test harness đã cấu hình bean và schema. Flush/clear giúp không chỉ quan sát đối tượng vẫn còn trong persistence context. Kỹ thuật này thuộc JPA, không áp nguyên xi cho mọi store.

Test cần xác nhận thêm `existsById` với ID có và không có dữ liệu. Với `findById`, kiểm tra trường hợp rỗng theo hợp đồng thay vì tự chuyển nó thành một entity mặc định.

### 12.2. Fixture danh mục không cần thêm `save` vào repository

Dữ liệu test có thể được chuẩn bị bằng hạ tầng fixture riêng:

```java
@Test
void readsOnlyEnabledCategories() {
    entityManager.persist(new Category(10L, "Backend", true));
    entityManager.persist(new Category(20L, "Legacy", false));
    entityManager.flush();
    entityManager.clear();

    assertThat(categories.findByEnabledTrueOrderByNameAsc())
        .extracting(Category::getName)
        .containsExactly("Backend");
}
```

Việc test dùng `EntityManager` để chuẩn bị dữ liệu không buộc ứng dụng mở method `save` cho `CategoryRepository`. Cần phân biệt quyền của test fixture với hợp đồng repository dành cho consumer.

### 12.3. Phân trang và projection cần dữ liệu đối chứng

Chuẩn bị nhiều khóa học hơn kích thước một slice, có cả trạng thái nháp và lưu trữ. Thêm ít nhất hai khóa học trùng tiêu đề nhưng khác ID để kiểm tra tiêu chí phá hòa.

Kiểm tra chính xác:

- Chỉ có trạng thái được yêu cầu.
- Các field projection đúng giá trị.
- Thứ tự theo `title`, rồi `id`.
- Slice có đúng giới hạn và `hasNext` đúng khi còn dữ liệu.
- Duyệt phần tiếp không bỏ sót hoặc lặp do thiếu thứ tự ổn định trong tập dữ liệu kiểm thử.

Thứ tự ổn định không tự tạo snapshot khi dữ liệu được ghi đồng thời. Nếu bài toán cần bảo đảm mạnh hơn khi duyệt nhiều trang, phải xác định thêm semantics đọc và chiến lược phân trang phù hợp.

## 13. Test service và các tình huống lỗi

| Tình huống | Kết quả mong muốn |
| --- | --- |
| Tạo khóa học hợp lệ | Có ID và đọc lại được qua repository |
| Tạo mã trùng | Store bảo vệ uniqueness; lỗi được xử lý đúng tại ranh giới phù hợp |
| Đổi tên khóa học nháp | Lưu tên mới theo quy tắc |
| Đổi tên khóa học đã lưu trữ | Từ chối theo nghiệp vụ |
| Tìm ID không tồn tại | Repository trả rỗng; service áp dụng chính sách lỗi đã chọn |
| Page âm hoặc size ngoài giới hạn | Service từ chối trước truy vấn |
| Hai cập nhật cạnh tranh | Version được kiểm chứng theo provider và transaction thực tế |
| Interface nền trong scan | Không tạo bean generic độc lập |

Unit test service với mock có thể xác nhận logic điều phối, nhưng không chứng minh `save` sao chép được nối đúng base implementation. Integration test mới kiểm tra factory, mapping và query của module.

Khi kiểm tra lỗi uniqueness hoặc version trong JPA, đưa flush/commit vào phạm vi quan sát. Không cố định một loại exception của mọi đường thao tác nếu chúng đi qua cơ chế dịch lỗi khác nhau.

Nếu thêm auditing trong phần mở rộng, cần bật auditing và nguồn actor/time phù hợp. Không mặc định chỉ thêm annotation vào entity là metadata sẽ xuất hiện ở mọi đường ghi.

## 14. Tổ chức giao diện theo capability khi dự án phát triển

Thiết kế ban đầu có hai capability rõ: đọc theo ID và lưu. Khi nhu cầu tăng, có thể thêm interface riêng cho một nhóm hợp đồng có ý nghĩa, thay vì tạo một base repository chứa mọi thao tác từng được yêu cầu.

Ví dụ một capability liệt kê có bộ lọc hoặc một fragment cho nghiệp vụ truy vấn phức tạp cần được đặt tên theo trách nhiệm cụ thể. Không dùng một method tùy chỉnh cùng tên CRUD rồi mặc định framework sẽ nối nó tới implementation cơ sở.

Nếu cần custom fragment, kiểm tra interface được kế thừa, implementation được phát hiện và thứ tự ưu tiên khi có chữ ký trùng. Nếu chỉ cần method CRUD tiêu chuẩn đã được module hỗ trợ, sao chép đúng chữ ký vào interface chọn lọc thường đơn giản hơn tự viết implementation.

Không để interface ghi rộng trở thành dependency của một thành phần chỉ cần đọc. Consumer có thể được thiết kế quanh một application port hẹp hơn khi cần giới hạn trách nhiệm ở tầng nghiệp vụ. Repository abstraction và application port có vai trò khác nhau, dù đều là interface Java.

## 15. Điều kiện hoàn thành bài thực hành

Bài thực hành đạt mục tiêu khi có thể chứng minh:

1. Hai interface nền chỉ công khai đúng các method đã chọn và được đánh dấu `@NoRepositoryBean`.
2. `CourseRepository` có đọc/lưu cùng các query bổ sung, không kế thừa API xóa hoặc đọc toàn bộ ngoài ý định.
3. `CategoryRepository` không công khai method ghi.
4. Repository proxy thật thực hiện được các thao tác cơ sở đã sao chép.
5. Projection và slice trả đúng dữ liệu, thứ tự và giới hạn.
6. Service thể hiện hành vi tạo, đổi tên và lưu trữ bằng các lệnh rõ ràng.
7. Uniqueness, version và lỗi tại transaction được kiểm chứng theo store.
8. Cấu hình scan không tạo interface nền thành bean và không gắn repository vào nhầm store.

Các điều kiện này là tiêu chí thực hành cho người triển khai. Chúng tách bằng chứng về API khỏi bằng chứng về dữ liệu và cấu hình, giúp đánh giá kết quả cụ thể thay vì chỉ nhìn số interface đã tạo.

## 16. Bài tập mở rộng

Một nhóm mới cần tra cứu khóa học theo ví dụ và một tác vụ quản trị cần lưu theo lô. Không phải mọi service đều được dùng hai khả năng đó.

Hãy đề xuất:

- Khả năng nào thuộc repository cụ thể, khả năng nào nên thành capability riêng.
- Có cần công khai `QueryByExampleExecutor` hay một API nghiệp vụ hẹp hơn không.
- Store mục tiêu hỗ trợ matcher, projection và kiểu kết quả nào.
- Batch operation cần giữ những quy tắc validation, version, callback và auditing nào.
- Consumer nào được nhận interface mới và test nào bảo vệ bề mặt API.

Không thêm cả query by example và `saveAll` vào interface nền chung chỉ vì có một consumer cần. Quyết định mở rộng phải đi từ hợp đồng sử dụng và khả năng của store.

## 17. Điểm cần nhớ

CRUD chọn lọc bắt đầu từ `Repository` đánh dấu, rồi sao chép đúng những chữ ký cơ sở ứng dụng cần. Interface nền dùng `@NoRepositoryBean`; repository cụ thể chốt domain/ID và bổ sung query phù hợp.

Bề mặt API hẹp giúp biểu đạt trách nhiệm, còn tính đúng của mapping, transaction, version, projection và ràng buộc vẫn cần được kiểm chứng theo module cùng datastore. Một repository không công khai method xóa là một quyết định thiết kế API; các bảo đảm về quyền và dữ liệu vẫn cần cơ chế tương ứng ở những tầng liên quan.
