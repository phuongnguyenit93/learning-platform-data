# Phân biệt kiểm thử repository thật với mock repository

Trong ứng dụng Spring, repository thường là nơi service truy cập dữ liệu. Với Spring Data JPA, ta khai báo một interface như `BookRepository extends JpaRepository<Book, Long>`; Spring tạo implementation tại runtime và kết nối nó với JPA provider cùng datasource.

Khi kiểm thử phần code sử dụng repository, có hai cách thường gặp:

- **Kiểm thử repository thật**: khởi tạo repository do Spring Data tạo ra và cho nó làm việc với database kiểm thử. Cách này kiểm tra đường đi từ repository qua JPA đến database.
- **Kiểm thử với mock repository**: thay repository bằng một đối tượng giả do Mockito tạo ra. Cách này kiểm tra service hoặc component gọi repository xử lý đúng khi nhận các kết quả đã được định trước.

Hai cách trả lời hai câu hỏi khác nhau. Một bài kiểm thử service với mock có thể chạy rất nhanh nhưng không chứng minh câu truy vấn của repository đúng. Ngược lại, một bài kiểm thử repository thật có thể xác nhận câu truy vấn hoạt động nhưng không nhất thiết kiểm tra quy tắc nghiệp vụ trong service.

## 1. Repository thật trong Spring Data JPA là gì?

Giả sử ứng dụng quản lý sách có repository sau:

```java
public interface BookRepository extends JpaRepository<Book, Long> {

    Optional<Book> findByIsbn(String isbn);

    List<Book> findByTitleContainingIgnoreCase(String keyword);
}
```

Đây chỉ là interface. Khi ứng dụng khởi động, Spring Data JPA tạo một implementation cho interface này. Các lời gọi như `findByIsbn` được Spring Data diễn giải theo tên phương thức và chuyển thành truy vấn phù hợp. Nếu repository có `@Query`, JPA provider cũng phải phân tích và thực thi truy vấn đó.

Một bài kiểm thử repository thật sử dụng chính implementation do Spring tạo. Bài kiểm thử khởi tạo persistence context, ánh xạ entity, datasource và database kiểm thử. Khi gọi `repository.findByIsbn(...)`, lời gọi đi qua Spring Data và JPA đến database.

Tùy cấu hình, database kiểm thử có thể là H2 chạy trong bộ nhớ hoặc một instance database thật được khởi chạy cho test, chẳng hạn PostgreSQL qua Testcontainers. Vì vậy, “repository thật” có nghĩa là dùng implementation và luồng persistence thật; điều đó chưa tự động có nghĩa là đang dùng đúng hệ quản trị database production.

### Những gì cách kiểm thử này có thể xác nhận

- Spring Data có tạo và khởi tạo repository đúng hay không.
- Tên phương thức truy vấn có được diễn giải đúng hay không, ví dụ `findByTitleContainingIgnoreCase`.
- JPQL hoặc native SQL trong `@Query` có hợp lệ và trả về kết quả mong đợi hay không.
- Entity có được ánh xạ đúng với bảng, cột, khóa chính, quan hệ và kiểu dữ liệu hay không.
- Các thao tác lưu, cập nhật, xóa, phân trang và sắp xếp có hoạt động đúng hay không.
- Ràng buộc ở database, chẳng hạn `NOT NULL`, `UNIQUE` và khóa ngoại, có được áp dụng như mong đợi hay không.

Đây là những hành vi mà một mock không thể xác nhận, vì mock không chạy câu SQL và không có JPA provider hoặc database thực thi truy vấn.

## 2. Viết kiểm thử repository thật với `@DataJpaTest`

Với Spring Boot, `@DataJpaTest` thường là lựa chọn phù hợp để kiểm thử tầng JPA. Annotation này nạp cấu hình cần thiết cho entity và Spring Data JPA repository, thay vì khởi động toàn bộ ứng dụng như `@SpringBootTest`.

Ví dụ entity:

```java
@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String isbn;

    @Column(nullable = false)
    private String title;

    protected Book() {
    }

    public Book(String isbn, String title) {
        this.isbn = isbn;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getIsbn() {
        return isbn;
    }

    public String getTitle() {
        return title;
    }
}
```

Repository:

```java
public interface BookRepository extends JpaRepository<Book, Long> {

    List<Book> findByTitleContainingIgnoreCase(String keyword);
}
```

Bài kiểm thử:

```java
@DataJpaTest
class BookRepositoryTest {

    @Autowired
    private BookRepository bookRepository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void findsBooksByTitleWithoutConsideringCase() {
        entityManager.persist(new Book("ISBN-001", "Spring Framework Guide"));
        entityManager.persist(new Book("ISBN-002", "Learning Java"));
        entityManager.flush();
        entityManager.clear();

        List<Book> result = bookRepository.findByTitleContainingIgnoreCase("SPRING");

        assertThat(result)
                .extracting(Book::getIsbn)
                .containsExactly("ISBN-001");
    }
}
```

Trong ví dụ này:

1. `@DataJpaTest` yêu cầu Spring khởi tạo phần cấu hình JPA cho test.
2. `@Autowired` lấy repository thật từ Spring context. Đây không phải mock.
3. `TestEntityManager` tạo dữ liệu kiểm thử bằng JPA.
4. `flush()` đẩy các thay đổi đang chờ xuống database để database thực thi chúng.
5. `clear()` xóa các entity đang được giữ trong persistence context hiện tại. Nhờ vậy, test không vô tình chỉ đọc lại đối tượng đang nằm sẵn trong bộ nhớ.
6. Lời gọi repository thực thi truy vấn; AssertJ kiểm tra kết quả trả về.

Mặc định, các test `@DataJpaTest` chạy trong transaction và transaction thường được rollback sau mỗi test. Điều này giúp dữ liệu của test này không tồn tại để ảnh hưởng test tiếp theo. Nếu test cần xác nhận hành vi liên quan đến commit hoặc nhiều transaction độc lập, cần thiết kế transaction của test phù hợp với hành vi đang muốn kiểm tra.

### Cấu hình database cho test

Với dự án Spring Boot dùng Gradle, cấu hình đơn giản có thể gồm:

```groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("com.h2database:h2")
}
```

Khi H2 có trên test classpath, `@DataJpaTest` thường tự cấu hình database nhúng cho test. Đây là cách chạy nhanh và tiện cho các truy vấn, mapping và thao tác JPA phổ biến.

Tuy nhiên, H2 không phải PostgreSQL, MySQL hay Oracle. Cú pháp SQL, kiểu dữ liệu, collation, xử lý JSON, sequence, khóa, hàm database và một số hành vi transaction có thể khác nhau. Một truy vấn chạy trên H2 vẫn có thể thất bại khi chạy trên database production.

Nếu ứng dụng phụ thuộc vào hành vi riêng của database production, hãy chạy repository test với cùng hệ quản trị đó. Testcontainers có thể khởi chạy database dùng trong test. Ví dụ cấu hình PostgreSQL:

```java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class BookRepositoryPostgresTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void configureDatasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    // Các test repository đặt tại đây.
}
```

Test cần các thư viện Testcontainers cho JUnit Jupiter và PostgreSQL, cùng JDBC driver PostgreSQL ở test runtime. `@AutoConfigureTestDatabase(replace = Replace.NONE)` yêu cầu Spring giữ datasource được cấu hình thay vì thay nó bằng database nhúng. `@DynamicPropertySource` cung cấp thông tin kết nối từ container cho Spring.

Không cần dùng Testcontainers cho mọi test. H2 phù hợp với nhiều kiểm thử repository thông thường; database container hữu ích khi cần xác nhận tính tương thích với database production hoặc kiểm tra tính năng đặc thù của nó.

## 3. Mock repository là gì?

Mock repository là một đối tượng giả thay thế `BookRepository` trong bài kiểm thử. Mockito tạo đối tượng này; test quy định lời gọi nào sẽ trả về dữ liệu gì.

Ví dụ service sử dụng repository:

```java
public class BookService {

    private final BookRepository bookRepository;

    public BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    public Book getRequiredBook(Long id) {
        return bookRepository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
```

Ta có thể kiểm tra quy tắc xử lý của service mà không cần khởi động Spring hoặc database:

```java
@ExtendWith(MockitoExtension.class)
class BookServiceTest {

    @Mock
    private BookRepository bookRepository;

    @InjectMocks
    private BookService bookService;

    @Test
    void returnsBookWhenItExists() {
        Book book = new Book("ISBN-001", "Spring Framework Guide");
        when(bookRepository.findById(10L)).thenReturn(Optional.of(book));

        Book result = bookService.getRequiredBook(10L);

        assertThat(result.getIsbn()).isEqualTo("ISBN-001");
        verify(bookRepository).findById(10L);
    }

    @Test
    void throwsExceptionWhenBookDoesNotExist() {
        when(bookRepository.findById(99L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> bookService.getRequiredBook(99L))
                .isInstanceOf(BookNotFoundException.class);
    }
}
```

Ở đây, `@Mock` tạo repository giả và `@InjectMocks` đưa mock đó vào service. `when(...).thenReturn(...)` thiết lập kết quả giả lập. Khi service gọi `findById`, Mockito trả về đúng kết quả đã khai báo; không có câu truy vấn nào được gửi đến database.

Bài kiểm thử này có thể xác nhận:

- Service trả về đúng dữ liệu khi repository tìm thấy bản ghi.
- Service xử lý đúng trường hợp repository trả về `Optional.empty()`.
- Service chuyển đổi dữ liệu, áp dụng quy tắc nghiệp vụ hoặc ném exception đúng theo kết quả nhận được.
- Service gọi repository với tham số cần thiết, nếu lời gọi đó là một phần hành vi quan trọng cần xác nhận.

Bài kiểm thử này không xác nhận `findById` hoặc một phương thức truy vấn tùy chỉnh có chạy đúng trên database. Nó chỉ xác nhận service phản ứng đúng với kết quả mà mock cung cấp.

## 4. So sánh hai cách kiểm thử

| Tiêu chí | Repository thật | Mock repository |
| --- | --- | --- |
| Đối tượng đang kiểm tra | Spring Data repository và luồng persistence | Service hoặc component phụ thuộc repository |
| Repository được dùng | Implementation do Spring tạo | Đối tượng giả do Mockito tạo |
| Database | Có database kiểm thử, có thể là H2 hoặc database container | Không cần database |
| Câu SQL/JPQL | Được thực thi và có thể được kiểm tra qua kết quả | Không được thực thi |
| Mapping entity | Có thể kiểm tra | Không kiểm tra |
| Quy tắc nghiệp vụ trong service | Chỉ được kiểm tra nếu test thêm service vào phạm vi | Có thể kiểm tra trực tiếp |
| Tốc độ và phạm vi khởi tạo | Thường chậm hơn unit test, cần cấu hình JPA | Thường nhanh, ít phụ thuộc môi trường |
| Lỗi có thể phát hiện | Sai truy vấn, mapping, cấu hình persistence, ràng buộc database | Sai nhánh xử lý, chuyển đổi hoặc quyết định của service |

Ví dụ, nếu `findByTitleContainingIgnoreCase` viết sai tên thuộc tính hoặc `@Query` có JPQL không hợp lệ, repository test có thể phát hiện vấn đề khi khởi tạo hoặc thực thi truy vấn. Một service test dùng mock vẫn có thể thành công, bởi Mockito chỉ trả về danh sách mà test đã định nghĩa.

Ngược lại, nếu service phải ném `BookNotFoundException` khi repository không tìm thấy sách nhưng service lại trả về `null`, service test với mock có thể phát hiện lỗi này mà không cần database.

## 5. Những nhầm lẫn thường gặp

### Mock repository không phải là kiểm thử repository

Nếu test tạo `@Mock BookRepository` rồi gọi `bookRepository.findByTitleContainingIgnoreCase(...)`, kết quả chỉ đến từ cấu hình `when(...).thenReturn(...)`. Test đó không chạy implementation của Spring Data. Vì vậy, nó không thể chứng minh tên phương thức, JPQL, native SQL hoặc mapping đúng.

Hãy đặt mock ở ranh giới giữa service và repository khi mục tiêu là kiểm tra service. Khi mục tiêu là kiểm tra câu truy vấn hoặc persistence, hãy inject repository thật trong một bài kiểm thử JPA.

### H2 không tương đương database production

Một test dùng repository thật với H2 vẫn là repository integration test: Spring Data, JPA provider và database đều tham gia. Nhưng kết quả đó chỉ chứng minh hành vi trên H2. Với truy vấn dùng hàm riêng của PostgreSQL, kiểu dữ liệu đặc thù hoặc hành vi khóa phụ thuộc database, hãy chạy test trên PostgreSQL.

### `@DataJpaTest` và `@SpringBootTest` có phạm vi khác nhau

`@DataJpaTest` tập trung vào tầng persistence và thường khởi động nhanh hơn. `@SpringBootTest` khởi tạo application context rộng hơn, phù hợp khi cần kiểm tra cách nhiều thành phần của ứng dụng kết hợp với nhau. Không nên dùng `@SpringBootTest` cho mọi truy vấn repository nếu một JPA slice đã đủ để xác nhận hành vi.

### Fake, stub và mock không hoàn toàn giống nhau

Trong hội thoại, các thuật ngữ này đôi khi bị gọi chung là “repository giả”, nhưng chúng có ý nghĩa khác nhau:

- **Stub** cung cấp câu trả lời cố định cho lời gọi, ví dụ `findById(10L)` trả về một `Book`.
- **Mock** cũng có thể cung cấp câu trả lời, đồng thời ghi nhận lời gọi để test xác minh tương tác, chẳng hạn repository được gọi đúng một lần với ID cần thiết.
- **Fake** là một implementation đơn giản nhưng có hành vi thực, ví dụ repository lưu dữ liệu trong một `Map` ở bộ nhớ.

Fake có thể hữu ích trong một số unit test, nhưng nó vẫn không kiểm tra Spring Data JPA hoặc database. Dữ liệu và quy tắc của fake có thể khác với implementation thật.

## 6. Chọn cách kiểm thử theo câu hỏi cần trả lời

Hãy bắt đầu bằng cách xác định thành phần và hành vi cần được xác nhận:

| Câu hỏi | Cách kiểm thử phù hợp |
| --- | --- |
| Phương thức `findByEmail` có tìm đúng bản ghi trong database không? | Repository thật |
| JPQL trong `@Query` có hợp lệ và trả đúng kết quả không? | Repository thật |
| Quan hệ `@OneToMany` có lưu và tải đúng không? | Repository thật |
| Ràng buộc unique có ngăn dữ liệu trùng không? | Repository thật |
| Service có ném exception khi repository không tìm thấy bản ghi không? | Mock repository trong service test |
| Service có tính phí hoặc chuyển trạng thái đúng từ dữ liệu repository trả về không? | Mock repository trong service test |
| Luồng service, transaction và database có phối hợp đúng trong ứng dụng không? | Integration test phạm vi rộng hơn, có thể dùng `@SpringBootTest` và database phù hợp |

Một dự án thường cần cả hai nhóm test. Repository test tập trung vào truy vấn, mapping và hành vi persistence. Service unit test dùng mock để kiểm tra các nhánh nghiệp vụ độc lập với database. Khi có rủi ro ở ranh giới giữa nhiều thành phần, bổ sung integration test cho đúng luồng đó.

### Quy trình gợi ý cho repository test

1. Xác định truy vấn hoặc hành vi persistence cần kiểm tra, chẳng hạn lọc theo trạng thái, phân trang hoặc kiểm tra tính duy nhất.
2. Tạo dữ liệu đầu vào có cả trường hợp khớp và không khớp.
3. Dùng repository thật được Spring inject vào test.
4. Flush dữ liệu trước khi truy vấn; cân nhắc clear persistence context khi cần bảo đảm test đọc lại từ database.
5. Gọi phương thức repository và kiểm tra nội dung, số lượng, thứ tự hoặc trường hợp rỗng của kết quả.
6. Nếu ứng dụng dùng tính năng riêng của database production, chạy test với chính hệ quản trị đó.

### Quy trình gợi ý cho service test với mock

1. Xác định các kết quả repository có thể trả về và các nhánh nghiệp vụ tương ứng.
2. Tạo mock cho repository và cấu hình kết quả bằng `when(...).thenReturn(...)` hoặc `thenThrow(...)` khi cần mô phỏng lỗi.
3. Gọi phương thức service.
4. Kiểm tra kết quả, exception hoặc thay đổi nghiệp vụ.
5. Chỉ dùng `verify(...)` khi tương tác với repository có ý nghĩa đối với hành vi đang kiểm tra; tránh xác minh mọi lời gọi nội bộ không cần thiết.

## 7. Kết luận

Kiểm thử repository thật trả lời câu hỏi: **repository và tầng persistence có làm việc đúng với database không?** Mock repository trong service test trả lời câu hỏi: **service có xử lý đúng các kết quả và tình huống mà repository cung cấp không?**

Hãy dùng `@DataJpaTest` cùng repository thật để kiểm tra truy vấn, mapping và hành vi database. Hãy dùng Mockito để thay repository khi kiểm tra logic của service. Kết hợp hai loại test theo ranh giới trách nhiệm sẽ giúp phát hiện cả lỗi truy vấn lẫn lỗi nghiệp vụ, đồng thời giữ cho phần lớn unit test chạy nhanh và dễ kiểm soát.
