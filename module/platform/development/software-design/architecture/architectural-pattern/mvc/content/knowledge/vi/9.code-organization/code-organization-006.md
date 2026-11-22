# Quản lý phụ thuộc bằng giao diện và tiêm phụ thuộc

## 1. Vì sao ứng dụng MVC cần quản lý phụ thuộc?

Trong ứng dụng Model–View–Controller, các thành phần không hoạt động độc lập. Controller cần gọi nghiệp vụ; Service cần truy cập dữ liệu; Repository cần một cơ chế lưu trữ; một số chức năng còn cần gửi email, đọc tệp hoặc gọi dịch vụ bên ngoài. Mỗi quan hệ sử dụng một thành phần khác được gọi là **phụ thuộc (dependency)**.

Nếu mỗi lớp tự tạo các đối tượng mà nó cần bằng `new`, mã nguồn dễ bị gắn chặt với một cách triển khai cụ thể. Ví dụ, `BookService` tự tạo `JpaBookRepository` thì khó chuyển sang kho dữ liệu khác hoặc kiểm thử nghiệp vụ mà không khởi tạo cơ sở dữ liệu.

Quản lý phụ thuộc bằng **giao diện (interface)** và **tiêm phụ thuộc (Dependency Injection — DI)** giúp tách việc sử dụng một khả năng khỏi việc tạo ra khả năng đó. Thành phần nghiệp vụ làm việc với hợp đồng ổn định; thành phần cấu hình hoặc container cung cấp implementation phù hợp.

## 2. Nhận diện phụ thuộc và chiều phụ thuộc

Xét một chức năng hiển thị chi tiết sách:

~~~mermaid
flowchart TD
    U[Browser] --> C[BookController]
    C --> S[BookService]
    S --> I[BookRepository interface]
    R[JpaBookRepository]
    R -. implements .-> I
    R --> DB[(Database)]
~~~

Controller cần Service để xử lý use case. Service cần khả năng đọc và lưu sách. Service không nhất thiết phải biết dữ liệu nằm trong PostgreSQL, tệp hay một dịch vụ từ xa; nó chỉ cần một hợp đồng như `BookRepository`.

Chiều phụ thuộc cần được thiết kế có chủ đích. Lớp trình bày gọi lớp ứng dụng; lớp ứng dụng dựa vào hợp đồng cần thiết cho use case; lớp hạ tầng triển khai hợp đồng đó. Khi lớp nghiệp vụ phụ thuộc trực tiếp vào framework hoặc thư viện persistence, thay đổi ở hạ tầng có thể lan vào phần lõi.

## 3. Giao diện giúp tách hợp đồng khỏi cách triển khai

Interface trong Java định nghĩa những hành vi mà một thành phần cung cấp. Lớp khác có thể lập trình dựa trên interface thay vì phụ thuộc vào một class cụ thể.

Ví dụ, hợp đồng kho sách có thể được khai báo như sau:

~~~java
import java.util.List;
import java.util.Optional;

public interface BookRepository {
    Optional<Book> findById(BookId id);
    List<Book> findAll();
    Book save(Book book);
}
~~~

`BookRepository` mô tả những gì use case cần từ nơi lưu trữ. Nó không nói dữ liệu được lưu bằng JPA, JDBC, file hay API. `JpaBookRepository`, `JdbcBookRepository` hoặc `InMemoryBookRepository` có thể cung cấp các implementation khác nhau miễn là tuân thủ cùng hợp đồng.

Interface có giá trị khi nó biểu diễn một ranh giới có ý nghĩa: một khả năng có thể có nhiều implementation, một phụ thuộc cần thay thế trong kiểm thử, hoặc một ranh giới giữa các lớp kiến trúc. Không cần tạo interface cho mọi class một cách máy móc. Nếu một lớp đơn giản, ổn định và không có nhu cầu thay thế hoặc tách ranh giới, inject trực tiếp class cụ thể vẫn có thể hợp lý.

### Ví dụ implementation

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class JpaBookRepository implements BookRepository {
    private final SpringDataBookJpaRepository jpaRepository;

    public JpaBookRepository(SpringDataBookJpaRepository jpaRepository) {
        this.jpaRepository = jpaRepository;
    }

    @Override
    public Optional<Book> findById(BookId id) {
        return jpaRepository.findById(id.value())
                .map(BookEntityMapper::toDomain);
    }

    @Override
    public List<Book> findAll() {
        return jpaRepository.findAll().stream()
                .map(BookEntityMapper::toDomain)
                .toList();
    }

    @Override
    public Book save(Book book) {
        var entity = BookEntityMapper.toEntity(book);
        return BookEntityMapper.toDomain(jpaRepository.save(entity));
    }
}
~~~

Ví dụ giả định `SpringDataBookJpaRepository`, `BookEntityMapper`, `Book` và `BookId` đã được định nghĩa. Mapper chuyển đổi giữa mô hình persistence và mô hình miền. Nhờ đó, Service có thể làm việc với `Book` mà không cần biết chi tiết của entity JPA.

## 4. Dependency Inversion Principle, IoC và DI

Ba khái niệm này có liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Câu hỏi được giải quyết |
|---|---|---|
| Dependency Inversion Principle (DIP) | Nguyên tắc thiết kế: chính sách cấp cao không phụ thuộc trực tiếp vào chi tiết cấp thấp; cả hai phụ thuộc vào abstraction phù hợp | Phụ thuộc nên hướng về đâu? |
| Inversion of Control (IoC) | Cách tổ chức trong đó một phần quyền điều khiển, như tạo đối tượng hoặc gọi callback, được chuyển cho framework/container | Ai điều khiển việc tạo và kết nối thành phần? |
| Dependency Injection (DI) | Một kỹ thuật IoC: dependency được cung cấp từ bên ngoài thay vì đối tượng tự tạo | Làm thế nào để cung cấp dependency? |

DIP là nguyên tắc kiến trúc; IoC là cách chuyển quyền điều khiển; DI là một kỹ thuật thực hiện IoC. Có thể dùng DI mà chưa tuân thủ DIP, chẳng hạn inject trực tiếp một class hạ tầng vào Service. Ngược lại, có thể áp dụng DIP bằng cách tự wiring các implementation trong một composition root mà không dùng framework DI.

### DIP trong ví dụ quản lý sách

Thiết kế gắn chặt:

~~~java
public class BookService {
    private final JpaBookRepository repository =
            new JpaBookRepository(/* cấu hình database */);
}
~~~

`BookService` vừa chứa quy tắc ứng dụng vừa quyết định cách tạo repository. Nếu đổi sang implementation khác, phải sửa Service. Khi kiểm thử, cũng khó thay repository thật bằng một phiên bản giả.

Thiết kế dựa trên abstraction:

~~~java
public class BookService {
    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }
}
~~~

Service chỉ biết hợp đồng `BookRepository`. Một thành phần bên ngoài chọn implementation và cung cấp nó. Đây là cách thể hiện DIP ở ranh giới truy cập dữ liệu.

## 5. Tiêm phụ thuộc qua constructor

**Constructor injection** là cách cung cấp dependency thông qua hàm tạo. Đây thường là lựa chọn mặc định tốt trong Java và Spring vì các dependency bắt buộc được thể hiện rõ, có thể lưu trong field `final`, và đối tượng không thể được tạo ở trạng thái thiếu dependency.

### Ví dụ Service

~~~java
import java.util.Objects;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final BookRepository books;

    public BookService(BookRepository books) {
        this.books = Objects.requireNonNull(books);
    }

    public Book getBook(BookId id) {
        return books.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }

    public Book create(Book book) {
        // Model/Service kiểm tra quy tắc nghiệp vụ phù hợp.
        return books.save(book);
    }
}
~~~

Constructor cho thấy `BookService` không thể hoạt động nếu thiếu `BookRepository`. Spring có thể tự tiêm dependency khi tìm thấy một bean phù hợp. Với một constructor duy nhất, Spring không yêu cầu thêm `@Autowired` trên constructor.

### Controller cũng nhận dependency qua constructor

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@Controller
public class BookController {
    private final BookService bookService;
    private final BookViewMapper viewMapper;

    public BookController(
            BookService bookService,
            BookViewMapper viewMapper) {
        this.bookService = bookService;
        this.viewMapper = viewMapper;
    }

    @GetMapping("/books/{id}")
    public String detail(@PathVariable BookId id, Model model) {
        Book book = bookService.getBook(id);
        model.addAttribute("book", viewMapper.toDetailView(book));
        return "books/detail";
    }
}
~~~

Controller không tự tạo Service hoặc Mapper. Spring cung cấp các bean khi khởi tạo Controller. Trong ứng dụng thực tế, cách parse ID từ URL sang `BookId` cần có converter hoặc nhận `UUID`/`String` rồi chuyển đổi rõ ràng; ví dụ trên tập trung minh họa wiring phụ thuộc.

### Vì sao thường tránh field injection?

Spring hỗ trợ field injection:

~~~java
@Autowired
private BookRepository books;
~~~

Nhưng cách này có một số nhược điểm: dependency bị ẩn khỏi constructor, field không thể là `final`, đối tượng khó được khởi tạo trực tiếp trong unit test và cần cơ chế reflection để gán dependency. Setter injection phù hợp hơn với dependency thật sự tùy chọn hoặc có thể thay đổi sau khi tạo đối tượng; dependency bắt buộc nên đi qua constructor.

## 6. Ai tạo và kết nối các đối tượng?

Trong ứng dụng không dùng DI container, có thể tạo các đối tượng tại một điểm lắp ráp (composition root):

~~~java
BookRepository repository = new InMemoryBookRepository();
BookService service = new BookService(repository);
BookViewMapper mapper = new BookViewMapper();
BookController controller = new BookController(service, mapper);
~~~

Composition root là nơi biết các implementation cụ thể và kết nối chúng thành object graph. Các lớp nghiệp vụ không cần tự tìm hoặc tạo những dependency của mình.

Với Spring, IoC container đảm nhận việc tạo bean, giải quyết dependency và quản lý vòng đời theo cấu hình. Các lớp có thể được phát hiện bằng component scanning (`@Component`, `@Service`, `@Repository`, `@Controller`) hoặc được khai báo tường minh bằng `@Bean` trong một lớp `@Configuration`.

### Khai báo bean bằng cấu hình

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BookConfiguration {
    @Bean
    BookRepository bookRepository(
            SpringDataBookJpaRepository jpaRepository) {
        return new JpaBookRepository(jpaRepository);
    }
}
~~~

Đây là một cách cấu hình thay thế cho việc đánh dấu `JpaBookRepository` bằng `@Repository` để component scanning tự đăng ký. Không nên đăng ký cả hai cách cho cùng một implementation nếu chúng tạo ra hai bean không mong muốn.

Spring sẽ tìm một bean có kiểu tương thích với `BookRepository` để cung cấp cho `BookService`. Nếu có nhiều implementation, ứng dụng phải chỉ rõ lựa chọn.

### Khi có nhiều implementation

Có thể dùng `@Primary` để chỉ định bean mặc định hoặc `@Qualifier` để chọn bean theo tên/qualifier:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final BookRepository books;

    public BookService(
            @Qualifier("jpaBookRepository") BookRepository books) {
        this.books = books;
    }
}
~~~

Qualifier cần khớp với bean đã được đăng ký. Ví dụ trên giả định component scanning tạo bean tên `jpaBookRepository` từ lớp `JpaBookRepository`; nếu dùng phương thức `@Bean` ở ví dụ trước, tên mặc định là `bookRepository` và qualifier cần được điều chỉnh tương ứng. Không nên dùng tên bean như một cách thay thế cho thiết kế hợp đồng; hãy chọn implementation dựa trên cấu hình môi trường hoặc vai trò nghiệp vụ có ý nghĩa.

## 7. DI trong các lớp của kiến trúc MVC

Mỗi tầng nên nhận đúng những dependency cần cho trách nhiệm của nó:

| Thành phần | Dependency thường gặp | Trách nhiệm |
|---|---|---|
| Controller | Application Service, View Mapper | Nhận request, chuyển input, gọi use case, chọn response/View |
| Application Service | Repository interface, gateway, clock hoặc policy | Điều phối use case và giao dịch nghiệp vụ |
| Domain Model | Value Object, domain service hoặc abstraction miền cần thiết | Bảo vệ trạng thái và quy tắc miền |
| Repository implementation | JPA repository, EntityManager, JDBC client | Chuyển hợp đồng lưu trữ thành thao tác hạ tầng |
| View | View Model và template engine | Trình bày dữ liệu |

View template thường không cần được Controller tiêm như một object. Framework chọn và render template dựa trên tên View logic. Cũng không nên để Controller trực tiếp nhận `DataSource`, `EntityManager` hoặc client HTTP nếu thao tác đó thuộc trách nhiệm của Service/Repository.

~~~mermaid
flowchart TB
    subgraph Presentation
      C[Controller]
      V[View / Template]
    end
    subgraph Application
      S[BookService]
      P[BookRepository port]
    end
    subgraph Infrastructure
      A[JpaBookRepository adapter]
      D[(Database)]
    end
    C --> S
    C --> V
    S --> P
    A -. implements .-> P
    A --> D
~~~

Trong cách nhìn ports and adapters, `BookRepository` là port mà ứng dụng cần; `JpaBookRepository` là adapter ở hạ tầng thực hiện port đó. Đây là một cách tổ chức giúp thể hiện DIP rõ hơn, nhưng không bắt buộc mọi dự án MVC phải dùng đầy đủ thuật ngữ hoặc cấu trúc Hexagonal Architecture.

## 8. Kiểm thử nhờ dependency có thể thay thế

DI làm cho dependency có thể được thay bằng implementation khác trong kiểm thử. Với `BookService`, có thể dùng repository giả trong bộ nhớ để kiểm tra quy tắc mà không cần khởi động Spring hoặc cơ sở dữ liệu.

### Ví dụ Fake Repository

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public class InMemoryBookRepository implements BookRepository {
    private final Map<BookId, Book> data = new HashMap<>();

    @Override
    public Optional<Book> findById(BookId id) {
        return Optional.ofNullable(data.get(id));
    }

    @Override
    public List<Book> findAll() {
        return List.copyOf(data.values());
    }

    @Override
    public Book save(Book book) {
        data.put(book.id(), book);
        return book;
    }
}
~~~

Đây là fake đơn giản, giả định `Book` có `id()` và `BookId` có cách so sánh/hash phù hợp. Nó mô phỏng hợp đồng lưu trữ trong bộ nhớ, không thay thế kiểm thử tích hợp cho truy vấn, transaction hoặc ràng buộc của cơ sở dữ liệu thật.

### Unit test Service

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class BookServiceTest {
    @Test
    void createsBookThroughRepositoryContract() {
        BookRepository repository = new InMemoryBookRepository();
        BookService service = new BookService(repository);
        Book book = TestData.validBook();

        Book saved = service.create(book);

        assertEquals(book.id(), saved.id());
        assertEquals(book.id(),
                repository.findById(book.id()).orElseThrow().id());
    }
}
~~~

`TestData.validBook()` là factory của bộ test, trả về một `Book` hợp lệ theo constructor/factory của miền. Ý chính là test tạo Service trực tiếp với một implementation của interface. Không cần khởi động ApplicationContext cho unit test thuần.

Mock cũng là một lựa chọn khi muốn xác minh tương tác cụ thể, ví dụ Service gọi `save` đúng một lần. Fake hữu ích khi cần hành vi lưu trữ có thể sử dụng trong nhiều ca kiểm thử. Hãy chọn test double phù hợp; không nên mock mọi dependency nếu một fake đơn giản đã đủ.

## 9. Vòng đời bean và an toàn luồng

DI container thường quản lý vòng đời của dependency. Trong Spring, scope mặc định của bean là `singleton`: một instance được chia sẻ trong ApplicationContext. Vì vậy, Service và Repository singleton thường nên giữ dependency bất biến và tránh lưu trạng thái riêng của một request trong field mutable.

Ví dụ, không nên làm như sau:

~~~java
@Service
public class BookService {
    private String currentUser;
    private Book currentBook;
}
~~~

Nhiều request đồng thời có thể ghi đè các field này và làm dữ liệu của người dùng này ảnh hưởng người dùng khác. Dữ liệu request nên được truyền qua tham số phương thức hoặc lưu trong context có scope phù hợp.

Spring còn có các scope như `prototype`, `request` và `session`. Khi bean scope ngắn hơn được inject vào singleton, cần xem xét proxy hoặc provider để lấy instance đúng vòng đời; không giữ một đối tượng request/session trong singleton theo cách làm nó tồn tại quá lâu.

DI không tự làm cho một bean thread-safe. Nếu bean giữ trạng thái dùng chung, vẫn cần thiết kế đồng bộ, bất biến hoặc cô lập trạng thái phù hợp.

## 10. Những vấn đề thường gặp khi wiring dependency

### Không tìm thấy bean

Nếu Spring không tìm thấy implementation phù hợp cho một constructor parameter, ApplicationContext không thể khởi động. Kiểm tra component scanning, package chứa implementation, điều kiện profile và cấu hình `@Bean`. Không giải quyết bằng cách tự gọi `new` bên trong Service vì điều đó quay lại coupling ban đầu.

### Có nhiều bean cùng kiểu

Nếu có nhiều `BookRepository` bean mà không có lựa chọn rõ ràng, Spring có thể báo lỗi không xác định được bean. Dùng `@Primary`, `@Qualifier` hoặc cấu hình có điều kiện theo môi trường với ý nghĩa rõ ràng.

### Circular dependency

Nếu `BookService` cần `LoanService` và `LoanService` lại cần `BookService`, object graph có chu trình. Đây thường là dấu hiệu trách nhiệm hoặc ranh giới use case chưa hợp lý. Hãy xem có thể tách một service điều phối, đưa quy tắc chung vào domain service hoặc phát sự kiện miền ở ranh giới phù hợp hay không. Dùng `@Lazy` chỉ để che chu trình thường khiến thiết kế khó hiểu hơn.

### Service Locator

Service Locator là cách một lớp tự hỏi container hoặc registry để lấy dependency khi cần, ví dụ inject `ApplicationContext` rồi gọi `getBean(BookRepository.class)`. Cách này che giấu dependency thật khỏi constructor và khiến lớp phụ thuộc vào container. Constructor injection thường rõ ràng và dễ kiểm thử hơn.

### Tạo interface không có mục đích

Không phải mọi class đều cần interface và một implementation duy nhất chỉ để tuân theo hình thức. Tạo abstraction khi nó đặt tên cho một hợp đồng có ý nghĩa, bảo vệ chiều phụ thuộc hoặc cho phép thay thế thực sự. Interface quá rộng hoặc chứa chi tiết của framework vẫn có thể tạo coupling.

## 11. Kiểm thử wiring và cấu hình

Ngoài unit test cho Service, cần kiểm tra wiring khi ứng dụng có cấu hình DI:

- **Unit test:** khởi tạo lớp bằng constructor với fake/mock, kiểm tra logic mà không cần container.
- **Context test:** khởi động một ApplicationContext nhỏ để xác minh bean được đăng ký và dependency được giải quyết.
- **Integration test:** kiểm tra implementation thật với cơ sở dữ liệu hoặc hệ thống phụ thuộc, bao gồm mapping, transaction và cấu hình môi trường.
- **MVC test:** kiểm tra Controller nhận đúng Service, chuyển dữ liệu thành View Model và trả status/View mong đợi.

Không nên dùng `@SpringBootTest` cho mọi unit test vì việc khởi động toàn bộ context làm test chậm và có thể che khuất ranh giới giữa logic đơn vị với cấu hình tích hợp. Dùng test nhẹ cho logic và test context ở nơi wiring thực sự cần được xác minh.

## 12. Những sai lầm thường gặp

- **Tự tạo dependency bên trong Service/Controller:** làm lớp bị gắn với implementation cụ thể và khó thay thế khi kiểm thử.
- **Nhầm DI với DIP:** inject một class cụ thể vẫn là DI, nhưng chưa chắc đã đảo chiều phụ thuộc.
- **Dùng field injection cho mọi dependency:** làm dependency bị ẩn và đối tượng khó được khởi tạo độc lập.
- **Tạo interface cho mọi class:** tăng số lượng kiểu mà không tạo ranh giới kiến trúc có ý nghĩa.
- **Để Controller truy cập trực tiếp hạ tầng:** khiến tầng trình bày biết quá nhiều về persistence hoặc dịch vụ ngoài.
- **Dùng Service Locator:** che giấu dependency và làm lớp phụ thuộc container.
- **Bỏ qua circular dependency:** chu trình thường cho thấy trách nhiệm hoặc ranh giới cần xem lại.
- **Lưu trạng thái request trong singleton bean:** có thể gây race condition và rò rỉ dữ liệu giữa người dùng.
- **Cho rằng DI bảo đảm thread safety:** vòng đời bean và tính an toàn luồng là hai vấn đề cần thiết kế riêng.

## 13. Kết luận

Giao diện xác định hợp đồng mà một thành phần cần; DI cung cấp implementation từ bên ngoài; IoC container có thể tự động tạo và kết nối các đối tượng. Khi kết hợp với DIP, cách tổ chức này giúp Controller và Service phụ thuộc vào những abstraction phù hợp, còn chi tiết hạ tầng triển khai các hợp đồng đó.

Khi thiết kế MVC, hãy liệt kê dependency thực sự của từng lớp, xác định ranh giới nào cần interface, cung cấp dependency bắt buộc qua constructor và đặt việc wiring tại composition root hoặc DI container. Kiểm thử bằng fake/mock giúp xác minh logic độc lập; context và integration test xác minh cấu hình cùng implementation thật. Mục tiêu là làm cho quan hệ giữa các thành phần rõ ràng, có thể thay thế và dễ kiểm soát.
