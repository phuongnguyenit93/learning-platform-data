# Chọn unit test cho logic ứng dụng và integration test cho hành vi repository

## 1. Chọn loại test từ điều cần chứng minh

Trong chương **Kiểm thử** của module **SPRING_DATA_COMMONS**, câu hỏi đầu tiên là: hành vi cần bảo vệ nằm trong code ứng dụng hay trong sự phối hợp giữa repository, mapping và kho dữ liệu?

Một service có thể cần kiểm tra điều kiện xuất bản khóa học, tìm dữ liệu và lưu trạng thái mới. Trong đó:

- Quy tắc “khóa học phải có bài học trước khi xuất bản” là logic ứng dụng.
- Query “chỉ lấy khóa học đã xuất bản của đúng tenant” cần repository thực sự thực thi.
- Việc ghi rồi đọc lại entity đúng kiểu phụ thuộc mapping và backend.
- Việc nhiều thao tác cùng rollback phụ thuộc ranh giới transaction và hạ tầng được cấu hình.

Không có một loại test duy nhất chứng minh tốt tất cả các điều trên. Unit test cung cấp phản hồi nhanh cho quyết định của ứng dụng. Integration test kiểm tra các thành phần thật phối hợp tại ranh giới đã chọn.

Bài học dùng **Java 17, Spring Boot 3.5, Spring Data JPA 3.5, JUnit Jupiter, Mockito và AssertJ** cho ví dụ cụ thể. Commons cung cấp abstraction chung; JPA và cơ sở dữ liệu trong ví dụ là một lựa chọn triển khai.

## 2. Phân biệt bằng thành phần thật tham gia

| Kiểu kiểm thử | Thành phần thật | Thành phần được thay thế | Kết luận chính |
| --- | --- | --- | --- |
| Unit test service | Service và domain object | Repository bằng mock hoặc stub | Quy tắc và quyết định của service |
| Unit test hàm thuần | Hàm tính toán hoặc chuyển đổi | Không nhất thiết cần mock | Kết quả với các đầu vào |
| Integration test repository | Repository proxy, mapping, truy vấn và backend test | Có thể loại phần web/service không liên quan | Hành vi persistence trong cấu hình test |
| Integration test service với persistence | Service bean, proxy giao dịch, repository và backend | Các tích hợp ngoài phạm vi có thể được thay | Hành vi phối hợp và giao dịch của công việc |
| Test toàn luồng | Các tầng cần thiết cho một luồng sử dụng | Tùy ranh giới được công bố | Kết quả từ đầu vào đến đầu ra của luồng |

`@DataJpaTest` vẫn là integration test dù dùng H2 trong bộ nhớ. Có cơ sở dữ liệu trong bộ nhớ không làm repository trở thành mock.

Ngược lại, dùng `@SpringBootTest` nhưng thay repository bằng mock không chứng minh query hoặc mapping thật đã hoạt động. Kích thước context và khả năng chứng minh hành vi persistence là hai vấn đề khác nhau.

Một repository giả lưu bằng `Map` có thể hữu ích cho test service, nhưng không tự mô phỏng đúng collation, transaction, constraint hoặc query derivation của backend.

## 3. Ma trận chọn phạm vi kiểm thử

| Hành vi cần bảo vệ | Lựa chọn khởi đầu | Vì sao |
| --- | --- | --- |
| Từ chối xuất bản khóa học chưa có bài | Unit test | Quyết định nằm trong code ứng dụng |
| Xử lý trường hợp không tìm thấy khóa học | Unit test | Có thể điều khiển kết quả lookup một cách rõ ràng |
| Chuyển input thành `PageRequest` theo quy tắc ứng dụng | Unit test | Không cần backend để kiểm tra tham số được tạo |
| Derived query lọc đúng tenant | Integration test repository | Cần query thực sự được tạo và chạy |
| Sắp xếp và phân trang đúng tập kết quả | Integration test repository | Kết quả phụ thuộc query và dữ liệu |
| Projection nhận đúng các field | Integration test repository | Cần kiểm tra ánh xạ kết quả thực |
| Custom converter tính toán đúng | Unit test cho converter | Tách kiểm tra thuật toán khỏi persistence |
| Converter được đăng ký và lưu/đọc đúng | Integration test | Cần kiểm tra wiring cùng mapping |
| Fragment ghép chuỗi hoặc tính quy tắc thuần | Unit test cho phần thuần | Có thể kiểm tra riêng logic |
| Fragment thực thi SQL hoặc API của store | Integration test | Cần tài nguyên cùng cơ chế thực thi thật |
| Auditing tự điền người và thời gian | Integration test có nguồn auditor/thời gian kiểm soát | Cần callback và cấu hình auditing |
| Rollback toàn bộ công việc service | Integration test qua bean phù hợp | Mock không thực hiện giao dịch backend |

Một chức năng thường cần cả hai loại test. Không cần chọn một loại rồi loại bỏ loại còn lại.

Ví dụ, unit test bảo vệ điều kiện xuất bản; integration test bảo vệ query danh sách đã xuất bản. Hai test có mục tiêu khác nhau dù cùng dùng domain `Course`.

## 4. Mô hình xuyên suốt: xuất bản khóa học

Các public type sau được đặt trong các file Java riêng cùng package `example.courses`. Ví dụ giả định ứng dụng đã có cấu hình Boot ở package phù hợp để phát hiện entity và repository.

### 4.1. Entity minh họa

~~~java
package example.courses;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "learning_courses")
public class Course {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private String tenantKey;

    @Column(nullable = false)
    private String title;

    private int lessonCount;

    private boolean published;

    protected Course() {
    }

    public Course(
            String tenantKey,
            String title,
            int lessonCount,
            boolean published) {

        this.tenantKey = tenantKey;
        this.title = title;
        this.lessonCount = lessonCount;
        this.published = published;
    }

    public Long getId() {
        return id;
    }

    public String getTenantKey() {
        return tenantKey;
    }

    public String getTitle() {
        return title;
    }

    public int getLessonCount() {
        return lessonCount;
    }

    public boolean isPublished() {
        return published;
    }

    public void publish() {
        this.published = true;
    }
}
~~~

Đây là mô hình tối thiểu để tập trung vào ranh giới kiểm thử. Một khóa học nháp có thể chưa có bài, nên trạng thái `lessonCount = 0` là đầu vào hợp lệ để kiểm tra chính sách xuất bản.

### 4.2. Repository có query riêng của ứng dụng

~~~java
package example.courses;

import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CourseRepository
        extends JpaRepository<Course, Long> {

    List<Course>
    findByTenantKeyAndPublishedTrueOrderByTitleAscIdAsc(
            String tenantKey);

    Page<Course> findByTenantKeyAndPublishedTrue(
            String tenantKey,
            Pageable pageable);
}
~~~

Query derivation chuyển khai báo method thành truy vấn theo khả năng của store. Mock interface sẽ không chạy bước đó. Xem [Defining Query Methods của Spring Data JPA 3.5](https://docs.spring.io/spring-data/jpa/reference/3.5/repositories/query-methods-details.html).

### 4.3. Service chứa chính sách ứng dụng

~~~java
package example.courses;

import java.util.NoSuchElementException;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CourseService {

    private final CourseRepository repository;

    public CourseService(CourseRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void publish(Long courseId) {
        Course course = repository.findById(courseId)
                .orElseThrow(() -> new NoSuchElementException(
                        "Không tìm thấy khóa học"));

        if (course.getLessonCount() <= 0) {
            throw new IllegalStateException(
                    "Khóa học chưa có bài học");
        }

        course.publish();
        repository.save(course);
    }
}
~~~

Service nhận dependency qua constructor, vì vậy có thể tạo bằng `new` trong unit test. Đây là cách kiểm tra service độc lập với container mà [tài liệu Unit Testing của Spring Framework](https://docs.spring.io/spring-framework/reference/6.2/testing/unit.html) mô tả.

Nếu sau này chính sách chuyển vào domain, hãy đặt unit test tại nơi thực sự giữ quy tắc. Không bắt buộc mọi điều kiện nghiệp vụ phải luôn nằm trong service.

## 5. Unit test: điều khiển repository, kiểm tra quyết định của service

### 5.1. Ví dụ hoàn chỉnh

~~~java
package example.courses;

import java.util.NoSuchElementException;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CourseServiceTest {

    @Mock
    private CourseRepository repository;

    private CourseService service;

    @BeforeEach
    void setUp() {
        service = new CourseService(repository);
    }

    @Test
    void publishesCourseThatHasLessons() {
        Course course = new Course(
                "team-a", "Spring Data", 3, false);

        when(repository.findById(7L))
                .thenReturn(Optional.of(course));

        service.publish(7L);

        assertThat(course.isPublished()).isTrue();
        verify(repository).save(course);
    }

    @Test
    void rejectsCourseWithoutLessonsAndDoesNotSave() {
        Course course = new Course(
                "team-a", "Spring Data", 0, false);

        when(repository.findById(7L))
                .thenReturn(Optional.of(course));

        assertThatThrownBy(() -> service.publish(7L))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("Khóa học chưa có bài học");

        assertThat(course.isPublished()).isFalse();
        verify(repository, never()).save(any(Course.class));
    }

    @Test
    void reportsMissingCourseAndDoesNotSave() {
        when(repository.findById(99L))
                .thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.publish(99L))
                .isInstanceOf(NoSuchElementException.class);

        verify(repository, never()).save(any(Course.class));
    }
}
~~~

`MockitoExtension` khởi tạo các mock của test. Cách dùng với JUnit Jupiter được minh họa trong [mã nguồn chính thức của MockitoExtension](https://raw.githubusercontent.com/mockito/mockito/v5.18.0/mockito-extensions/mockito-junit-jupiter/src/main/java/org/mockito/junit/jupiter/MockitoExtension.java).

Domain object là đối tượng thật. Test điều khiển kết quả lookup, gọi service thật rồi kiểm tra trạng thái và yêu cầu lưu có ý nghĩa với chính sách.

Không cần stub `save` trả về một entity nếu service không sử dụng giá trị trả về. Chỉ chuẩn bị hành vi mà kịch bản đang cần.

### 5.2. Những điều test này chứng minh

Test bảo vệ ba quyết định:

1. Có bài học thì chuyển sang trạng thái đã xuất bản và yêu cầu lưu.
2. Chưa có bài thì từ chối trước khi lưu.
3. Không tìm thấy thì báo lỗi phù hợp và không lưu.

Việc xác minh không gọi `save` ở nhánh bị từ chối có ý nghĩa vì đây là hành vi cần bảo vệ. Không cần xác minh mọi lời gọi nội bộ chỉ để tăng số assertion.

### 5.3. Những điều cần test khác để chứng minh

Test chưa gửi query đến database. Nó chưa kiểm tra mapping, SQL, constraint hay query derivation.

Service được tạo bằng `new`, nên annotation `@Transactional` không tự có hiệu lực qua proxy Spring trong test này. Kết quả unit test không phải bằng chứng rằng transaction thật đã commit hoặc rollback.

Một lỗi chính tả trong derived query vẫn có thể tồn tại dù toàn bộ unit test service đều xanh. Mock chỉ nhận lời gọi theo khai báo interface.

## 6. Integration test repository: dùng repository thật

### 6.1. Chọn context vừa đủ

Với lựa chọn JPA và Boot của bài, `@DataJpaTest` tập trung vào thành phần persistence. Nó hỗ trợ entity, repository, `TestEntityManager` và cấu hình database cho test; các service ứng dụng thông thường không tự trở thành toàn bộ đối tượng cần kiểm thử trong slice này.

Theo mặc định, test có transaction và rollback sau mỗi method. Xem [API DataJpaTest của Boot 3.5](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html).

Để chạy bản ví dụ dùng database nhúng, ứng dụng cần các dependency phù hợp:

- `spring-boot-starter-data-jpa`.
- `spring-boot-starter-test` trong phạm vi test.
- Một database nhúng như `com.h2database:h2` trong phạm vi test.

Giữ phiên bản theo dependency management của ứng dụng. Ví dụ giả định database test riêng, không có seed tự động làm thay đổi fixture.

### 6.2. Dữ liệu phải phân biệt được các lỗi lọc

Một bộ dữ liệu nhỏ:

| Tenant | Tiêu đề | Published | Vai trò |
| --- | --- | --- | --- |
| team-a | Alpha | true | Kết quả hợp lệ |
| team-a | Charlie | true | Kết quả hợp lệ |
| team-a | Zulu | true | Kết quả hợp lệ |
| team-a | Draft | false | Bắt lỗi thiếu điều kiện published |
| team-b | Bravo | true | Bắt lỗi thiếu điều kiện tenant |

Nếu chỉ tạo một khóa học đã xuất bản của team-a, query quên tenant hoặc quên published vẫn có thể trả về đúng một kết quả. Dữ liệu đối chứng khiến assertion có khả năng phát hiện những sai sót đó.

### 6.3. Kiểm tra lọc, thứ tự và phân trang

~~~java
package example.courses;

import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(
        properties = "spring.jpa.hibernate.ddl-auto=create-drop")
class CourseRepositoryTest {

    @Autowired
    private CourseRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void selectsOnlyPublishedCoursesOfRequestedTenant() {
        seedCourses();

        List<Course> result = repository
                .findByTenantKeyAndPublishedTrueOrderByTitleAscIdAsc(
                        "team-a");

        assertThat(result)
                .extracting(Course::getTitle)
                .containsExactly("Alpha", "Charlie", "Zulu");

        assertThat(result).allSatisfy(course -> {
            assertThat(course.getTenantKey()).isEqualTo("team-a");
            assertThat(course.isPublished()).isTrue();
        });
    }

    @Test
    void returnsSecondPageWithCorrectTotal() {
        seedCourses();

        Sort sort = Sort.by("title").ascending()
                .and(Sort.by("id").ascending());

        Page<Course> page =
                repository.findByTenantKeyAndPublishedTrue(
                        "team-a",
                        PageRequest.of(1, 2, sort));

        assertThat(page.getContent())
                .extracting(Course::getTitle)
                .containsExactly("Zulu");

        assertThat(page.getNumber()).isEqualTo(1);
        assertThat(page.getSize()).isEqualTo(2);
        assertThat(page.getTotalElements()).isEqualTo(3);
        assertThat(page.getTotalPages()).isEqualTo(2);
        assertThat(page.hasNext()).isFalse();
    }

    private void seedCourses() {
        repository.saveAll(List.of(
                new Course("team-a", "Zulu", 2, true),
                new Course("team-a", "Alpha", 3, true),
                new Course("team-a", "Charlie", 4, true),
                new Course("team-a", "Draft", 1, false),
                new Course("team-b", "Bravo", 2, true)));

        entityManager.flush();
        entityManager.clear();
    }
}
~~~

`create-drop` ở đây chỉ phục vụ schema tối thiểu của database test riêng. Khi cần kiểm chứng schema do migration quản lý, phải dùng migration cùng cấu hình phù hợp thay vì coi schema tự sinh là bằng chứng tương đương.

Test thứ nhất bảo vệ điều kiện và thứ tự kết quả. Test thứ hai bảo vệ nội dung cùng metadata của `Page`; chỉ assert `getContent().size()` sẽ bỏ sót những lỗi về tổng số phần tử hoặc trang.

Thứ tự có thêm ID làm khóa phụ. Nếu hành vi khi trùng tiêu đề là yêu cầu quan trọng, bổ sung fixture trùng tiêu đề và kiểm tra thứ tự ID tương ứng. Không suy rằng bộ dữ liệu hiện tại đã bao phủ tình huống chưa được tạo.

Các assertion kiểm tra hợp đồng kết quả, không buộc implementation luôn chạy một số lượng câu SQL cố định.

## 7. Flush, clear và rollback có ý nghĩa khác nhau

Trong ví dụ JPA:

- `flush()` đồng bộ các thay đổi đang chờ của persistence context với database.
- `clear()` loại các entity đang được quản lý khỏi persistence context.
- Rollback kết thúc giao dịch bằng cách hủy các thay đổi thuộc phạm vi giao dịch đó.

Flush trước clear giúp không bỏ các thay đổi đang chờ. Đọc sau clear giúp tránh việc kiểm tra chỉ quan sát lại một entity đang được giữ trong persistence context. Các thao tác hỗ trợ được mô tả trong [API TestEntityManager](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/TestEntityManager.html).

Flush chưa phải commit. Các test trên vẫn có thể rollback sau khi assertion kết thúc.

Khi kiểm tra lỗi constraint hoặc callback ORM, cần bảo đảm thao tác liên quan thật sự được flush. Spring mô tả khả năng test xanh giả do trì hoãn đồng bộ trong [Transaction Management của TestContext](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html).

Transaction bao quanh test cũng có thể che việc service thiếu ranh giới riêng. Nếu mục tiêu là kiểm tra commit/rollback của công việc service, hãy gọi service bean qua đường được quản lý và thiết kế bước đọc kiểm chứng ở transaction độc lập phù hợp.

Không lấy việc “cuối test dữ liệu bị rollback” làm bằng chứng rằng service đã tự mở transaction đúng. Đó có thể là transaction do test framework cung cấp.

## 8. Chọn backend đủ đại diện cho điều cần kiểm tra

Database nhúng giúp giảm chi phí khởi tạo và có thể kiểm tra nhiều lỗi mapping hoặc query. Tuy nhiên, kết quả trên H2 không tự chứng minh hành vi tương đương với PostgreSQL hay một store khác.

Khi chức năng phụ thuộc native SQL, kiểu dữ liệu riêng, collation, constraint hoặc ngữ nghĩa transaction cụ thể, ưu tiên kiểm tra với backend đại diện cho môi trường triển khai.

Testcontainers cung cấp cách đưa backend thật vào integration test. Với Boot 3.5, có thể quản lý container như Spring bean và cung cấp connection details qua `@ServiceConnection`. Xem [Testcontainers trong Spring Boot](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html).

### 8.1. Cấu hình PostgreSQL minh họa

Ngoài dependency test của ví dụ trước, cần module `spring-boot-testcontainers`, module PostgreSQL tương ứng của Testcontainers và JDBC driver PostgreSQL. Môi trường chạy test cần container runtime tương thích.

~~~java
package example.courses;

import org.testcontainers.containers.PostgreSQLContainer;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
public class PostgresTestConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgres() {
        return new PostgreSQLContainer<>("postgres:17-alpine");
    }
}
~~~

Image trong ví dụ là một phiên bản minh họa; lựa chọn cho dự án phải phù hợp backend mà dự án cần hỗ trợ.

### 8.2. Test sử dụng backend đó

~~~java
package example.courses;

import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(
        properties = "spring.jpa.hibernate.ddl-auto=create-drop")
@Import(PostgresTestConfiguration.class)
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class CourseRepositoryPostgresTest {

    @Autowired
    private CourseRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void filtersTenantAgainstPostgres() {
        repository.saveAll(List.of(
                new Course("team-a", "Commons", 2, true),
                new Course("team-b", "JPA", 2, true),
                new Course("team-a", "Draft", 0, false)));

        entityManager.flush();
        entityManager.clear();

        assertThat(repository
                .findByTenantKeyAndPublishedTrueOrderByTitleAscIdAsc(
                        "team-a"))
                .extracting(Course::getTitle)
                .containsExactly("Commons");
    }
}
~~~

`Replace.NONE` thể hiện yêu cầu giữ database đã cấu hình thay vì thay bằng database nhúng. Xem [API AutoConfigureTestDatabase.Replace](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html).

Test này kiểm tra repository trong cấu hình PostgreSQL test. Nó chưa tự bao phủ mọi khác biệt về extension, cấu hình server, tải thực tế hoặc schema triển khai.

Nếu backend đã là một phần quan trọng của hợp đồng, có thể dùng backend đó cho tập integration test repository chính. Không bắt buộc nhân đôi mọi kịch bản trên cả H2 và PostgreSQL khi việc nhân đôi không tăng khả năng phát hiện lỗi có ý nghĩa.

## 9. Thiết kế assertion theo hành vi cần bảo vệ

### 9.1. Unit test nên quan sát kết quả và quyết định quan trọng

Với `publish`, trạng thái published và việc có yêu cầu lưu hay không là những điều hữu ích. Xác minh chính xác mọi getter được gọi bao nhiêu lần thường làm test phụ thuộc chi tiết cài đặt.

Khi service biến đổi dữ liệu trước khi lưu, có thể dùng argument capture để kiểm tra giá trị được gửi. Đừng chỉ kiểm tra “save đã được gọi” nếu lỗi có thể nằm trong dữ liệu truyền vào.

Nếu code chỉ chuyển tiếp một lời gọi không có quyết định hay biến đổi, cân nhắc giá trị của test trước khi thêm một test chỉ lặp lại implementation.

### 9.2. Integration test cần dữ liệu phản ví dụ

Với query theo tenant và trạng thái, cần cả bản ghi khớp và không khớp. Với sắp xếp, dữ liệu đầu vào cần có thứ tự khác thứ tự kỳ vọng. Với phân trang, số bản ghi cần vượt kích thước một trang.

Một số tình huống nên chọn theo yêu cầu thực tế:

| Hành vi | Dữ liệu hoặc assertion có sức phân biệt |
| --- | --- |
| Kết quả rỗng | Có dữ liệu trong store nhưng không có bản ghi phù hợp |
| Phân trang | Có nhiều hơn một trang và kiểm tra tổng số phù hợp |
| Thứ tự khi bằng nhau | Có giá trị trùng ở khóa sort chính |
| Projection | Kiểm tra giá trị field được ánh xạ |
| Query by Example | Có dữ liệu phân biệt matcher, null và điều kiện được chọn |
| Auditing | Auditor và thời gian có thể kiểm soát, sau đó kiểm tra field thật |
| Optimistic locking | Các phiên bản cập nhật cạnh tranh được thiết lập ở ranh giới phù hợp |
| Constraint | Thao tác vi phạm thực sự được gửi đến backend tại thời điểm cần kiểm tra |

Không cần đưa mọi dòng vào mọi repository. Chọn các rủi ro tồn tại trong hành vi ứng dụng đang sử dụng.

### 9.3. Không mock đối tượng đang được kiểm tra persistence

Nếu mock `CourseRepository`, stub query trả về danh sách mong muốn rồi assert chính danh sách đó, test mới kiểm tra thiết lập mock. Query thật có thể bị xóa hoặc đổi điều kiện mà test vẫn không phát hiện.

Trong integration test repository, inject repository thật. Có thể thay những dependency ngoài mục tiêu kiểm tra, nhưng không thay chính đường persistence cần chứng minh.

## 10. Dữ liệu độc lập và vòng đời kiểm thử

Mỗi test cần tự tạo dữ liệu đủ cho kịch bản của mình. Không dựa vào thứ tự chạy hoặc một test trước đó đã tạo bản ghi.

Không mặc định ID đầu tiên luôn bằng 1. Dùng ID được trả về khi lưu hoặc khóa nghiệp vụ do fixture kiểm soát. Sequence và chính sách sinh ID có thể không trở lại trạng thái cũ chỉ vì dữ liệu bị rollback.

Context được cache giúp giảm chi phí khởi tạo, nhưng cache context không đồng nghĩa tự dọn mọi dữ liệu ngoài transaction. Cơ chế cache được mô tả trong [Context Caching của Spring Framework](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html).

Các thao tác chạy ở transaction khác, thread khác hoặc tài nguyên không được transaction test quản lý cần chiến lược dọn dữ liệu riêng. Khi chạy song song, các test còn cần tránh dùng chung dữ liệu có thể gây tranh chấp ngoài ý định.

Một container dùng chung không tự cô lập từng test. Cần phối hợp vòng đời backend với schema, database, namespace hoặc transaction theo khả năng của store.

Đối với dữ liệu thời gian hoặc auditing, tránh assertion phụ thuộc giờ máy thay đổi giữa hai câu lệnh. Đưa nguồn thời gian/người dùng vào phạm vi có thể điều khiển khi thiết kế test.

## 11. Áp dụng đúng module của Spring Data

| Module | Hướng integration test phù hợp |
| --- | --- |
| JPA | Repository thật, entity mapping và database; dùng JPA slice khi phù hợp |
| JDBC | Repository JDBC, mapping aggregate và database; chọn cấu hình hoặc slice tương ứng |
| MongoDB | Repository/template thật với MongoDB có cấu hình phù hợp |
| R2DBC | Repository/template reactive và database; bảo đảm pipeline được thực thi và quan sát kết quả |
| Module khác | Test query, mapping và khả năng backend của chính module đó |

`@DataJpaTest` phục vụ JPA; nó không phải annotation kiểm thử chung cho mọi abstraction của Commons.

Boot có các slice riêng như `@DataJdbcTest`, `@DataMongoTest` và `@DataR2dbcTest`. Không giả định chúng có cùng mặc định rollback; chẳng hạn Boot 3.5 mô tả Data R2DBC test mặc định không transactional. Xem [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).

Unit test logic ứng dụng có thể giữ cách tiếp cận tương tự khi thay store. Integration test phải thay theo mapping, query và semantics mà store thực sự hỗ trợ.

Đối với fragment tùy chỉnh, tách thuật toán thuần để unit test nếu có ích, đồng thời kiểm tra phần tương tác backend bằng integration test. Test một nửa không tự chứng minh nửa còn lại.

## 12. Quy trình chọn test khi thêm hành vi mới

1. Viết rõ điều cần bảo vệ, chẳng hạn “không xuất bản khi chưa có bài” hoặc “không trả dữ liệu của tenant khác”.
2. Xác định thành phần nào quyết định điều đó: code ứng dụng, repository infrastructure, mapping hay backend.
3. Dùng phạm vi nhỏ nhất vẫn thực thi được thành phần quyết định; thêm integration test khi kết luận phụ thuộc sự phối hợp thật.
4. Tạo dữ liệu và assertion có thể phân biệt hành vi đúng với lỗi cụ thể đang cần ngăn.
5. Ghi nhận giới hạn của môi trường test để không suy rộng kết quả vượt phạm vi đã kiểm chứng.

Với ví dụ khóa học, bộ test có mục đích rõ ràng gồm unit test cho ba nhánh của service và integration test cho điều kiện truy vấn cùng phân trang. Khi thêm projection, auditing, fragment hoặc yêu cầu giao dịch, bổ sung test tại đúng ranh giới phát sinh hành vi đó.

Một bộ test hữu ích cho Spring Data bảo vệ cả quyết định của ứng dụng và cách dữ liệu thực sự được lưu, chọn và ánh xạ. Số lượng mock, annotation hay context được khởi tạo không thay thế việc xác định điều mỗi test có thể chứng minh.
