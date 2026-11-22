# Thay lớp lưu trữ mà vẫn giữ hành vi giao diện

Trong bài thực hành này, bạn sẽ thay đổi cách lưu trữ dữ liệu của một ứng dụng danh mục sách mà không làm thay đổi hành vi mà người dùng nhìn thấy. Trang danh sách, trang chi tiết, biểu mẫu thêm sách, thông báo validation và đường dẫn điều hướng phải tiếp tục hoạt động như trước. Phần thay đổi nằm sau ranh giới lưu trữ: ứng dụng có thể dùng bộ nhớ trong tiến trình hoặc cơ sở dữ liệu quan hệ mà Controller và View không cần biết implementation nào đang được chọn.

Bài tập dùng Spring MVC, Thymeleaf và Java. Bạn sẽ tách một hợp đồng lưu trữ, đưa nghiệp vụ vào application service, xây hai adapter `InMemoryBookCatalogStore` và `JpaBookCatalogStore`, sau đó chọn adapter bằng Spring Profile. Cuối cùng, bạn kiểm tra hợp đồng lưu trữ riêng và chạy lại kiểm thử giao diện để xác nhận việc thay persistence không làm đổi route, View Model hoặc phản hồi HTML.

## 1. Mục tiêu thực hành

Sau khi hoàn thành, bạn có thể:

- Nhận diện sự phụ thuộc trực tiếp giữa Controller và công nghệ lưu trữ.
- Tách hợp đồng lưu trữ khỏi implementation cụ thể.
- Đặt use case ở application service và giữ Controller tập trung vào HTTP.
- Viết adapter lưu trữ trong bộ nhớ và adapter JPA cùng triển khai một hợp đồng.
- Chọn implementation bằng cấu hình mà không sửa template hoặc route.
- Kiểm thử hợp đồng lưu trữ và hành vi giao diện ở các tầng riêng.
- Giải thích khác biệt về độ bền dữ liệu, transaction và vận hành giữa các adapter.

## 2. Bối cảnh và yêu cầu của bài toán

Ứng dụng có một khu vực quản lý sách với ba màn hình:

| Màn hình | Route | Hành vi người dùng mong đợi |
|---|---|---|
| Danh sách sách | `GET /books` | Xem các sách đã lưu, hoặc thấy hướng dẫn khi danh sách rỗng |
| Chi tiết sách | `GET /books/{id}` | Xem tiêu đề và tác giả của một sách |
| Thêm sách | `GET /books/new`, `POST /books` | Mở form, kiểm tra dữ liệu và thêm sách mới |

Hành vi cần giữ sau khi thay lớp lưu trữ:

1. `GET /books` vẫn trả trang `books/list` và thuộc tính Model tên `books`.
2. Danh sách vẫn được sắp xếp theo tiêu đề, không phân biệt chữ hoa/chữ thường.
3. Danh sách rỗng vẫn hiển thị empty state.
4. `GET /books/{id}` vẫn trả `books/detail`; ID không tồn tại vẫn cho kết quả 404.
5. Form vẫn dùng `title` và `author`; hai trường đều bắt buộc.
6. Khi validation thất bại, form được render lại với lỗi ở đúng trường và dữ liệu hợp lệ đã nhập được giữ lại.
7. Khi thêm sách thành công, server redirect đến `/books/{id}`.
8. HTML, tên View, route và thông điệp người dùng không thay đổi chỉ vì implementation lưu trữ đã thay đổi.

Điểm khác nhau được phép là cách dữ liệu được lưu. Adapter trong bộ nhớ mất dữ liệu khi tiến trình khởi động lại; adapter JPA lưu dữ liệu bền vững trong database. Đây là khác biệt của persistence, không phải thay đổi trong hợp đồng giao diện.

## 3. Chuẩn bị môi trường

Bài thực hành giả định project đã có:

- Java và Spring Boot.
- `spring-boot-starter-web` cho Spring MVC.
- `spring-boot-starter-thymeleaf` cho HTML template.
- `spring-boot-starter-validation` cho Bean Validation.
- `spring-boot-starter-data-jpa` cho adapter JPA.
- Driver database phù hợp; H2 có thể dùng cho local/test và PostgreSQL hoặc database của dự án dùng cho môi trường triển khai.

Nếu project chưa có các dependency này, bổ sung starter tương ứng theo hệ build hiện tại. Không cần đổi hệ build chỉ để làm bài tập.

### 3.1. Cấu trúc package mục tiêu

Một cấu trúc tham khảo:

```text
src/main/java/com/example/books/
├── domain/
│   ├── Book.java
│   └── BookNotFoundException.java
├── application/
│   └── BookCatalogService.java
├── port/
│   └── BookCatalogStore.java
├── persistence/
│   ├── memory/
│   │   └── InMemoryBookCatalogStore.java
│   └── jpa/
│       ├── BookEntity.java
│       ├── SpringDataBookRepository.java
│       └── JpaBookCatalogStore.java
└── web/
    ├── BookController.java
    ├── CreateBookForm.java
    └── BookPageExceptionHandler.java

src/main/resources/
├── templates/
│   ├── books/
│   │   ├── list.html
│   │   ├── detail.html
│   │   └── new.html
│   └── errors/404.html
├── application.yml
├── application-memory.yml
├── application-jpa.yml
└── db/migration/V1__create_books.sql
```

Bạn có thể điều chỉnh package theo quy ước dự án. Điều cần giữ là Controller không phụ thuộc trực tiếp vào `JpaRepository`, entity JPA hoặc map lưu trữ trong bộ nhớ.

## 4. Bước 1 — Ghi nhận hành vi giao diện hiện tại

Trước khi thay persistence, hãy ghi lại hợp đồng mà trang đang cung cấp. Nếu ứng dụng đã có test, chạy chúng và xác nhận trạng thái ban đầu. Nếu chưa có, hãy thêm một số kiểm thử MVC trước khi thay đổi.

Ví dụ test hợp đồng của Controller:

```java
@WebMvcTest(BookController.class)
class BookControllerContractTest {
    @Autowired
    MockMvc mockMvc;

    @MockBean
    BookCatalogService catalog;

    @Test
    void listUsesTheExistingViewAndModelName() throws Exception {
        given(catalog.list()).willReturn(List.of(
            new Book(1L, "Clean Code", "Robert C. Martin")
        ));

        mockMvc.perform(get("/books"))
            .andExpect(status().isOk())
            .andExpect(view().name("books/list"))
            .andExpect(model().attributeExists("books"));
    }
}
```

Test này cố định ba phần của hợp đồng: route, tên View và tên thuộc tính Model. Nó mock application service nên chưa kiểm tra persistence. Các test form, empty state và 404 sẽ được bổ sung ở những bước sau.

Nếu project dùng Spring Security, request POST trong `MockMvc` cần được cấu hình user và CSRF token theo chính sách hiện tại. Không bỏ CSRF chỉ để test chạy qua.

### Việc cần làm

- Ghi lại các route đang tồn tại.
- Ghi lại tên View và tên Model attribute mà template sử dụng.
- Ghi lại status, redirect và nội dung lỗi quan trọng.
- Chạy test hiện tại và lưu kết quả làm baseline.

**Điều kiện qua bước:** bạn có thể mô tả chính xác những gì người dùng sẽ thấy trước khi thay lớp lưu trữ.

## 5. Bước 2 — Tạo Model nghiệp vụ và hợp đồng lưu trữ

Trước tiên, định nghĩa đối tượng nghiệp vụ `Book`. Đối tượng này không phụ thuộc JPA, Spring MVC hoặc template engine.

```java
package com.example.books.domain;

public record Book(Long id, String title, String author) {
    public Book {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Title is required");
        }
        if (author == null || author.isBlank()) {
            throw new IllegalArgumentException("Author is required");
        }

        title = title.trim();
        author = author.trim();
    }
}
```

`id` có thể là `null` khi tạo sách mới; adapter sẽ gán ID khi lưu. Domain Model kiểm tra invariant tối thiểu, còn thông báo validation thân thiện cho form vẫn được xử lý ở ranh giới web.

Tạo port mô tả những thao tác use case cần từ lớp lưu trữ:

```java
package com.example.books.port;

import com.example.books.domain.Book;
import java.util.List;
import java.util.Optional;

public interface BookCatalogStore {
    List<Book> findAll();

    Optional<Book> findById(long id);

    Book insert(Book book);
}
```

Port này không nhắc đến `JpaRepository`, SQL, file hoặc cấu trúc map. Nó mô tả nhu cầu của ứng dụng: liệt kê, tìm một sách và thêm sách.

### Việc cần làm

- Tạo `Book` trong package domain.
- Tạo `BookCatalogStore` trong package port.
- Không thêm annotation JPA vào `Book`.
- Không thêm kiểu `Pageable`, `EntityManager` hoặc `HttpServletRequest` vào port của bài tập.

**Điều kiện qua bước:** Model và hợp đồng lưu trữ có thể biên dịch mà không cần biết adapter nào sẽ được sử dụng.

## 6. Bước 3 — Đưa thao tác danh mục vào application service

Application service điều phối use case và phụ thuộc vào port. Nó không biết dữ liệu nằm trong bộ nhớ hay database.

```java
package com.example.books.application;

import com.example.books.domain.Book;
import com.example.books.domain.BookNotFoundException;
import com.example.books.port.BookCatalogStore;
import org.springframework.stereotype.Service;

import java.util.Comparator;
import java.util.List;

@Service
public class BookCatalogService {
    private static final Comparator<Book> TITLE_ORDER =
        Comparator.comparing(Book::title, String.CASE_INSENSITIVE_ORDER);

    private final BookCatalogStore store;

    public BookCatalogService(BookCatalogStore store) {
        this.store = store;
    }

    public List<Book> list() {
        return store.findAll().stream()
            .sorted(TITLE_ORDER)
            .toList();
    }

    public Book get(long id) {
        return store.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
    }

    public Book create(String title, String author) {
        Book newBook = new Book(null, title, author);
        return store.insert(newBook);
    }
}
```

Exception miền:

```java
package com.example.books.domain;

public class BookNotFoundException extends RuntimeException {
    public BookNotFoundException(long id) {
        super("Book not found: " + id);
    }
}
```

Trong ví dụ, thứ tự tiêu đề được áp dụng ở service để cả hai adapter có cùng hành vi. Với dữ liệu lớn, có thể chuyển yêu cầu sắp xếp thành một phần của port/query contract để database thực hiện hiệu quả hơn; khi đó phải định nghĩa cùng semantics cho mọi adapter.

Bài tập chỉ có một thao tác insert. Với use case ghi nhiều bản ghi hoặc phải giữ invariant xuyên nhiều thao tác, đặt transaction boundary ở application service để các lần ghi cần thiết cùng commit hoặc rollback. Không giả định transaction database tự hoàn tác được side effect bên ngoài như email.

### Việc cần làm

- Tạo `BookCatalogService` phụ thuộc `BookCatalogStore`.
- Chuyển logic tìm sách không tồn tại thành `BookNotFoundException`.
- Giữ Controller không truy cập trực tiếp adapter.
- Không đặt logic render HTML vào service.

**Điều kiện qua bước:** service có thể được kiểm thử bằng một implementation giả của `BookCatalogStore`.

## 7. Bước 4 — Tạo adapter lưu trữ trong bộ nhớ

Adapter đầu tiên lưu dữ liệu trong tiến trình. Nó hữu ích cho demo, test hoặc môi trường không cần độ bền dữ liệu qua lần khởi động lại.

```java
package com.example.books.persistence.memory;

import com.example.books.domain.Book;
import com.example.books.port.BookCatalogStore;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

@Repository
@Profile("memory")
public class InMemoryBookCatalogStore implements BookCatalogStore {
    private final ConcurrentMap<Long, Book> books = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong(0);

    @Override
    public List<Book> findAll() {
        return List.copyOf(books.values());
    }

    @Override
    public Optional<Book> findById(long id) {
        return Optional.ofNullable(books.get(id));
    }

    @Override
    public Book insert(Book book) {
        if (book.id() != null) {
            throw new IllegalArgumentException("Insert expects a new book");
        }

        long id = nextId.incrementAndGet();
        Book saved = new Book(id, book.title(), book.author());
        books.put(id, saved);
        return saved;
    }
}
```

`ConcurrentHashMap` và `AtomicLong` giúp ví dụ an toàn hơn khi nhiều request đồng thời truy cập cùng một instance. Adapter này vẫn chỉ tồn tại trong bộ nhớ tiến trình: restart ứng dụng sẽ làm mất dữ liệu. Nó cũng không cung cấp transaction rollback như database.

### Việc cần làm

- Tạo class triển khai `BookCatalogStore`.
- Đánh dấu adapter bằng `@Profile("memory")`.
- Đảm bảo `insert()` trả về `Book` có ID.
- Đảm bảo `findById()` trả `Optional.empty()` khi không tồn tại.
- Không đưa `@Profile` hoặc `ConcurrentMap` vào Controller.

**Điều kiện qua bước:** có thể tạo adapter bằng `new InMemoryBookCatalogStore()` và gọi đủ ba phương thức của port.

## 8. Bước 5 — Tạo adapter JPA

Adapter JPA chuyển giữa Domain Model `Book` và persistence entity `BookEntity`. Hai lớp có mục đích khác nhau nên không cần dùng chung một class.

### 8.1. Tạo entity

```java
package com.example.books.persistence.jpa;

import jakarta.persistence.*;

@Entity
@Table(name = "books")
public class BookEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 160)
    private String title;

    @Column(nullable = false, length = 120)
    private String author;

    protected BookEntity() {
    }

    public BookEntity(String title, String author) {
        this.title = title;
        this.author = author;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getAuthor() {
        return author;
    }
}
```

Constructor không tham số có phạm vi `protected` để JPA có thể khởi tạo entity. Entity chỉ chứa mapping persistence; quy tắc nghiệp vụ vẫn nằm trong Domain Model và application layer.

### 8.2. Tạo Spring Data repository

```java
package com.example.books.persistence.jpa;

import org.springframework.data.jpa.repository.JpaRepository;

public interface SpringDataBookRepository
        extends JpaRepository<BookEntity, Long> {
}
```

Spring Data cung cấp implementation cho interface repository. Interface này thuộc adapter JPA, không được inject trực tiếp vào Controller hoặc application service.

### 8.3. Tạo adapter triển khai port

```java
package com.example.books.persistence.jpa;

import com.example.books.domain.Book;
import com.example.books.port.BookCatalogStore;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
@Profile("jpa")
public class JpaBookCatalogStore implements BookCatalogStore {
    private final SpringDataBookRepository repository;

    public JpaBookCatalogStore(SpringDataBookRepository repository) {
        this.repository = repository;
    }

    @Override
    public List<Book> findAll() {
        return repository.findAll().stream()
            .map(this::toDomain)
            .toList();
    }

    @Override
    public Optional<Book> findById(long id) {
        return repository.findById(id).map(this::toDomain);
    }

    @Override
    public Book insert(Book book) {
        if (book.id() != null) {
            throw new IllegalArgumentException("Insert expects a new book");
        }

        BookEntity entity = new BookEntity(book.title(), book.author());
        return toDomain(repository.save(entity));
    }

    private Book toDomain(BookEntity entity) {
        return new Book(
            entity.getId(),
            entity.getTitle(),
            entity.getAuthor()
        );
    }
}
```

Adapter này chỉ hoạt động khi profile `jpa` được bật. `JpaBookCatalogStore` chuyển đổi entity sang domain object trước khi trả kết quả cho application service. Controller và template không biết `BookEntity` tồn tại.

### Việc cần làm

- Tạo `BookEntity` và Spring Data repository.
- Tạo `JpaBookCatalogStore implements BookCatalogStore`.
- Ánh xạ entity/domain ở trong adapter.
- Đánh dấu adapter bằng `@Profile("jpa")`.
- Không trả entity JPA trực tiếp từ Controller.

**Điều kiện qua bước:** cả hai adapter cùng biên dịch và cùng triển khai đúng ba phương thức của `BookCatalogStore`.

## 9. Bước 6 — Chọn adapter bằng Spring Profile

Hai adapter đều triển khai `BookCatalogStore`, vì vậy ứng dụng cần chọn đúng một bean cho mỗi lần chạy.

Trong `application-memory.yml`, cấu hình profile dùng bộ nhớ trong. Nếu project có JPA starter, có thể giữ H2 làm datasource phục vụ việc khởi tạo hạ tầng JPA ở môi trường local; adapter đang được chọn vẫn là `InMemoryBookCatalogStore`.

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:bookdb;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  jpa:
    hibernate:
      ddl-auto: none
```

Trong `application-jpa.yml`, cấu hình database thật qua biến môi trường:

```yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
  jpa:
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
```

Chọn profile khi chạy ứng dụng, ví dụ qua biến môi trường `SPRING_PROFILES_ACTIVE=memory` hoặc `SPRING_PROFILES_ACTIVE=jpa`. Có thể cấu hình profile trong môi trường chạy local theo quy ước của project.

Không bật đồng thời cả hai profile nếu cả hai adapter cùng tạo bean `BookCatalogStore`. Nếu không có profile hoặc có nhiều bean cùng kiểu, Spring có thể báo thiếu bean hoặc xung đột khi inject. Hãy để cấu hình xác định rõ một adapter.

### 9.1. Tạo migration database

Với Flyway, tạo `src/main/resources/db/migration/V1__create_books.sql`:

```sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(160) NOT NULL,
    author VARCHAR(120) NOT NULL
);
```

Kiểu identity và cú pháp migration cần phù hợp database thực tế. Trong môi trường dùng Flyway, `ddl-auto: validate` giúp Hibernate kiểm tra mapping so với schema thay vì tự ý thay đổi schema khi ứng dụng khởi động.

### 9.2. Kiểm tra cấu hình

- Profile `memory` phải chọn đúng một `InMemoryBookCatalogStore`.
- Profile `jpa` phải chọn đúng một `JpaBookCatalogStore`.
- Không inject `SpringDataBookRepository` vào service hoặc Controller.
- Database credentials lấy từ secret/environment, không commit vào source.
- Migration phải chạy trước khi adapter JPA truy cập bảng.

## 10. Bước 7 — Giữ Controller và View ổn định

Controller chỉ phụ thuộc `BookCatalogService`. Việc thay adapter không yêu cầu sửa route hoặc template.

### 10.1. Form object

```java
package com.example.books.web;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class CreateBookForm {
    @NotBlank
    @Size(max = 160)
    private String title;

    @NotBlank
    @Size(max = 120)
    private String author;

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getAuthor() { return author; }
    public void setAuthor(String author) { this.author = author; }
}
```

### 10.2. Controller

```java
package com.example.books.web;

import com.example.books.application.BookCatalogService;
import com.example.books.domain.Book;
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
@RequestMapping("/books")
public class BookController {
    private final BookCatalogService catalog;

    public BookController(BookCatalogService catalog) {
        this.catalog = catalog;
    }

    @GetMapping
    public String list(Model model) {
        model.addAttribute("books", catalog.list());
        return "books/list";
    }

    @GetMapping("/new")
    public String newBook(Model model) {
        model.addAttribute("form", new CreateBookForm());
        return "books/new";
    }

    @GetMapping("/{id}")
    public String detail(@PathVariable long id, Model model) {
        model.addAttribute("book", catalog.get(id));
        return "books/detail";
    }

    @PostMapping
    public String create(
            @Valid @ModelAttribute("form") CreateBookForm form,
            BindingResult errors,
            RedirectAttributes redirect) {

        if (errors.hasErrors()) {
            return "books/new";
        }

        Book created = catalog.create(form.getTitle(), form.getAuthor());
        redirect.addFlashAttribute("notice", "Đã thêm sách.");
        return "redirect:/books/" + created.id();
    }
}
```

`BindingResult` đặt ngay sau đối tượng được validate để Spring gắn lỗi đúng form. Nếu project bật Spring Security, request POST cần CSRF token theo cấu hình. Không bỏ xác thực hoặc CSRF để làm cho ví dụ đơn giản hơn.

### 10.3. Ánh xạ lỗi không tìm thấy

```java
import com.example.books.domain.BookNotFoundException;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;

@ControllerAdvice
public class BookPageExceptionHandler {
    @ExceptionHandler(BookNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public String notFound() {
        return "errors/404";
    }
}
```

Import `BookNotFoundException` và `HttpStatus` theo package tương ứng. Exception handler trả View lỗi cho request HTML. Nếu ứng dụng cũng có API, nên có error mapping phù hợp với JSON thay vì trả template HTML cho client API.

### 10.4. Template danh sách

`templates/books/list.html` có thể chứa:

```html
<main>
  <h1>Danh mục sách</h1>
  <a th:href="@{/books/new}">Thêm sách</a>

  <p th:if="${#lists.isEmpty(books)}" id="empty-state">
    Chưa có sách nào. Hãy thêm cuốn sách đầu tiên.
  </p>

  <table th:unless="${#lists.isEmpty(books)}" id="book-table">
    <thead>
      <tr><th>Tên sách</th><th>Tác giả</th></tr>
    </thead>
    <tbody>
      <tr th:each="book : ${books}">
        <td>
          <a th:href="@{/books/{id}(id=${book.id})}"
             th:text="${book.title}">Tên sách</a>
        </td>
        <td th:text="${book.author}">Tác giả</td>
      </tr>
    </tbody>
  </table>
</main>
```

### 10.5. Template form

`templates/books/new.html`:

```html
<main>
  <h1>Thêm sách</h1>
  <form th:action="@{/books}" th:object="${form}" method="post">
    <label for="title">Tên sách</label>
    <input id="title" type="text" th:field="*{title}">
    <p th:if="${#fields.hasErrors('title')}"
       th:errors="*{title}" class="field-error"></p>

    <label for="author">Tác giả</label>
    <input id="author" type="text" th:field="*{author}">
    <p th:if="${#fields.hasErrors('author')}"
       th:errors="*{author}" class="field-error"></p>

    <button type="submit">Lưu sách</button>
  </form>
</main>
```

Các template chỉ đọc `books`, `book` và `form`. Không template nào cần biết `BookCatalogStore`, JPA entity hoặc profile đang bật.

### Điều kiện qua bước

Khi chuyển giữa profile `memory` và `jpa`, Controller vẫn có cùng constructor, các route không đổi và template vẫn dùng cùng Model attribute.

## 11. Bước 8 — Kiểm thử hợp đồng của từng adapter

Mỗi adapter cần tuân thủ cùng semantics của port. Hãy kiểm tra ít nhất:

1. `insert()` trả về sách có ID.
2. `findById(id)` tìm được sách vừa thêm.
3. ID không tồn tại trả `Optional.empty()`.
4. `findAll()` trả tất cả sách đã thêm.
5. Nội dung tiêu đề và tác giả không bị thay đổi ngoài quy tắc trim của domain.

Ví dụ test trực tiếp cho adapter trong bộ nhớ:

```java
class InMemoryBookCatalogStoreTest {
    private final InMemoryBookCatalogStore store =
        new InMemoryBookCatalogStore();

    @Test
    void insertedBookCanBeFoundById() {
        Book saved = store.insert(
            new Book(null, "Clean Code", "Robert C. Martin")
        );

        assertNotNull(saved.id());
        assertEquals(saved, store.findById(saved.id()).orElseThrow());
    }

    @Test
    void missingBookReturnsEmpty() {
        assertTrue(store.findById(999L).isEmpty());
    }
}
```

Với JPA adapter, dùng `@DataJpaTest`, database kiểm thử và import `JpaBookCatalogStore`. Ví dụ khung test:

```java
import com.example.books.domain.Book;
import com.example.books.port.BookCatalogStore;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

@DataJpaTest
@ActiveProfiles("jpa")
@TestPropertySource(properties = {
    "spring.datasource.url=jdbc:h2:mem:books-test;DB_CLOSE_DELAY=-1",
    "spring.datasource.driver-class-name=org.h2.Driver",
    "spring.datasource.username=sa",
    "spring.datasource.password="
})
@Import(JpaBookCatalogStore.class)
class JpaBookCatalogStoreTest {
    @Autowired
    BookCatalogStore store;

    @Test
    void insertedBookCanBeFoundById() {
        Book saved = store.insert(
            new Book(null, "Clean Code", "Robert C. Martin")
        );

        assertNotNull(saved.id());
        assertEquals(saved, store.findById(saved.id()).orElseThrow());
    }
}
```

Đảm bảo test runtime có H2 hoặc database test phù hợp và migration/schema đã được thiết lập cho cấu hình test. Nếu Flyway tạo schema, tránh để Hibernate tự tạo một schema khác với production. `@DataJpaTest` thường chạy test trong transaction và rollback sau test; điều này hữu ích cho việc cô lập dữ liệu.

### 11.1. Tạo contract test dùng chung

Khi có nhiều adapter, nên gom các trường hợp chung thành một bộ contract test để cả hai implementation phải thỏa cùng yêu cầu. Có thể tạo abstract test class chứa các assertion và cung cấp fixture/store cho từng implementation. Với JPA, fixture cần được tạo trong Spring test context; với in-memory, có thể tạo instance mới cho mỗi test.

Không đưa phương thức `clearAll()` chỉ dành cho test vào port nghiệp vụ nếu ứng dụng không có nhu cầu xóa toàn bộ danh mục. Hãy dùng fixture hoặc cơ chế reset ở test adapter.

## 12. Bước 9 — Kiểm thử hành vi giao diện sau khi đổi adapter

Các test MVC nên tiếp tục kiểm tra cùng một hợp đồng, độc lập với storage adapter:

| Kịch bản | Assertion |
|---|---|
| GET `/books` | 200, View `books/list`, Model có `books` |
| Danh sách rỗng | HTML có `empty-state`, không có `book-table` |
| Danh sách có dữ liệu | HTML hiển thị title/author đúng và link đến detail |
| GET `/books/{id}` tồn tại | 200, View `books/detail`, Model có `book` |
| GET ID không tồn tại | 404 và View lỗi theo hợp đồng |
| POST form thiếu title | Render lại `books/new`, có field error, không insert |
| POST form hợp lệ | Redirect đến `/books/{id}` và sách có thể được xem |

Controller slice test dùng mock service giúp cố định route và mapping. Template integration test dùng template engine thật để xác minh HTML. Adapter test kiểm tra persistence. Ba loại test này bổ sung cho nhau và không cần gộp mọi thứ vào một test lớn.

### 12.1. Kiểm thử validation

```java
@Test
void invalidTitleReturnsTheSameForm() throws Exception {
    mockMvc.perform(post("/books")
            .param("title", " ")
            .param("author", "Robert C. Martin"))
        .andExpect(status().isOk())
        .andExpect(view().name("books/new"))
        .andExpect(model().attributeHasFieldErrors("form", "title"));

    then(catalog).shouldHaveNoInteractions();
}
```

Test này xác minh validation ở web boundary diễn ra trước khi gọi use case. Nếu Spring Security được bật, bổ sung principal và CSRF token theo cấu hình.

### 12.2. Kiểm thử HTML thực tế

Với template integration test, gửi request qua ứng dụng đã cấu hình Thymeleaf và kiểm tra HTML được render. Ví dụ dùng Jsoup:

```java
MvcResult result = mockMvc.perform(get("/books"))
    .andExpect(status().isOk())
    .andReturn();

Document html = Jsoup.parse(result.getResponse().getContentAsString());
assertEquals("Danh mục sách", html.selectFirst("h1").text());
assertNotNull(html.selectFirst("#empty-state"));
```

Đây là ví dụ cho trạng thái rỗng. Với danh sách có dữ liệu, xác minh bảng, số dòng, nội dung và link chi tiết. Không cần so sánh toàn bộ HTML nếu khoảng trắng hoặc class trang trí không thuộc hợp đồng.

### 12.3. Chạy cùng bộ UI test trên cả hai profile

Tạo hai cấu hình integration test hoặc hai lần chạy cùng test suite:

- Profile `memory` để kiểm tra trang với `InMemoryBookCatalogStore`.
- Profile `jpa` với database kiểm thử để kiểm tra cùng route và template qua `JpaBookCatalogStore`.

Không thay assertion của UI test chỉ vì adapter thay đổi. Nếu phải đổi View name, Model attribute hoặc thông báo do đổi persistence, hãy xem lại thiết kế: giao diện đang phụ thuộc vào implementation lưu trữ ở đâu đó.

## 13. Bước 10 — Chạy và quan sát ứng dụng

Chạy ứng dụng với profile `memory`, thêm vài sách và thử restart. Bạn sẽ thấy dữ liệu trong bộ nhớ biến mất sau khi tiến trình dừng. Đây là hành vi dự kiến.

Sau đó chạy với profile `jpa`, cấu hình database và migration. Thêm sách, restart ứng dụng rồi mở lại danh sách. Dữ liệu phải còn tồn tại.

Khi kiểm tra, ghi nhận:

- Profile đang hoạt động.
- Adapter bean nào được Spring inject vào `BookCatalogService`.
- Database migration có chạy thành công không.
- Request GET/POST có cùng status, route và View như trước không.
- Lỗi database được xử lý an toàn và không lộ SQL/credentials ra HTML.
- Thời gian truy vấn và số lượng query có hợp lý không.

Không log password database hoặc nội dung nhạy cảm. Nếu có lỗi, dùng log ứng dụng và exception type để chẩn đoán; không đưa thông tin kết nối vào response cho người dùng.

## 14. Tiêu chí hoàn thành

Đánh dấu bài tập hoàn thành khi tất cả điều kiện sau được đáp ứng:

- [ ] Có `Book` độc lập với JPA và Spring MVC.
- [ ] Có port `BookCatalogStore` mô tả thao tác lưu trữ cần thiết.
- [ ] `BookCatalogService` phụ thuộc port, không phụ thuộc adapter cụ thể.
- [ ] Có `InMemoryBookCatalogStore` và `JpaBookCatalogStore` cùng triển khai port.
- [ ] Profile chỉ chọn một adapter trong mỗi lần chạy.
- [ ] Controller không inject Spring Data repository hoặc entity JPA.
- [ ] Route, tên View và Model attribute giữ nguyên.
- [ ] Validation, empty state, detail 404 và redirect vẫn đúng.
- [ ] Adapter tests xác minh cùng contract.
- [ ] UI tests chạy được trên cả hai profile hoặc có bằng chứng integration tương đương.
- [ ] Dữ liệu JPA tồn tại sau restart; dữ liệu in-memory mất sau restart như dự kiến.
- [ ] Migration schema được quản lý và không phụ thuộc `ddl-auto: update` trong production.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Spring báo không tìm thấy `BookCatalogStore` | Chưa bật profile hoặc adapter không được scan | Kiểm tra profile và package component scan |
| Có hai bean `BookCatalogStore` | Bật đồng thời `memory` và `jpa` | Chỉ chọn một profile hoặc dùng cấu hình chọn adapter rõ ràng |
| Controller không render template | Dùng nhầm `@RestController` hoặc trả body thay vì View name | Kiểm tra annotation và kiểu trả về |
| Trang danh sách không có dữ liệu | Adapter đang dùng profile khác hoặc database rỗng | Xác nhận bean thực tế và dữ liệu seed/test |
| Dữ liệu biến mất sau restart | Đang dùng adapter in-memory | Chuyển sang profile JPA và database bền vững |
| JPA báo thiếu bảng | Migration chưa chạy hoặc tên bảng/cột không khớp | Kiểm tra Flyway history và schema |
| JPA không validate schema | Cấu hình `ddl-auto` không phù hợp | Dùng migration và `validate` trong môi trường JPA |
| Validation không hiển thị | Thiếu `@Valid`, BindingResult sai vị trí hoặc template dùng sai tên form | Kiểm tra Controller và `th:object` |
| Test UI thay đổi khi đổi adapter | Test phụ thuộc dữ liệu khởi tạo hoặc semantics adapter không đồng nhất | Dùng fixture ổn định và contract test cho port |

### 15.1. Vì sao không inject `JpaRepository` vào Controller?

Nếu Controller trực tiếp gọi Spring Data repository, lớp web biết công nghệ lưu trữ và có thể phụ thuộc vào entity. Khi thay database hoặc thêm cache, Controller phải thay đổi. Tách port và adapter giúp Controller chỉ phụ thuộc use case, còn adapter chịu trách nhiệm chuyển đổi giữa domain và persistence.

### 15.2. Vì sao không đặt `@Profile` trong Controller?

Controller không nên quyết định implementation lưu trữ. Profile là cấu hình composition root của ứng dụng, nơi Spring chọn bean phù hợp. Đặt điều kiện profile trong Controller làm luồng HTTP phụ thuộc môi trường và nhân đôi hành vi giao diện.

### 15.3. Vì sao in-memory adapter không thay thế database trong production?

Adapter trong bộ nhớ không có độ bền dữ liệu qua restart, không chia sẻ trạng thái giữa nhiều instance và không cung cấp transaction/locking như database. Nó phù hợp cho demo hoặc một số test, không phải lựa chọn production chỉ vì cùng triển khai interface.

## 16. Thử thách mở rộng

Sau khi hoàn thành hai adapter, chọn một thử thách:

**Thử thách A — Thêm JDBC adapter:** tạo `JdbcBookCatalogStore` dùng `JdbcTemplate`, vẫn triển khai `BookCatalogStore`. Chạy lại contract tests và UI tests mà không sửa Controller hoặc template.

**Thử thách B — Thêm phân trang:** mở rộng port bằng một query có `page`, `size` và sort rõ ràng. Đảm bảo in-memory và JPA adapter có cùng semantics, giới hạn page size và thứ tự ổn định.

**Thử thách C — Thêm cập nhật sách:** bổ sung use case update. Xác định rõ semantics `save`/`update`, xử lý ID không tồn tại và kiểm thử cùng hợp đồng trên cả hai adapter.

**Thử thách D — Thêm kiểm thử migration:** tạo database test sạch, chạy Flyway từ đầu và xác minh JPA adapter hoạt động với schema mới. Không dựa vào schema còn sót từ lần chạy trước.

## 17. Câu hỏi tự đánh giá

1. Vì sao Controller nên phụ thuộc `BookCatalogService` thay vì `JpaRepository`?
2. `BookCatalogStore` là port hay adapter? `JpaBookCatalogStore` là port hay adapter?
3. Vì sao `Book` và `BookEntity` nên tách biệt trong bài này?
4. Nếu đổi từ in-memory sang JPA, phần nào của MVC cần thay đổi và phần nào phải giữ nguyên?
5. Vì sao cùng một UI test có thể chạy với hai profile?
6. Vì sao adapter trong bộ nhớ không thể chứng minh transaction rollback của database?
7. Khi một use case cần ghi nhiều bảng, transaction boundary nên nằm ở đâu?
8. Vì sao migration schema cần được quản lý độc lập với việc chọn adapter?
9. Nếu thêm API JSON, DTO API có nên được dùng trực tiếp làm View Model HTML không? Vì sao?
10. Những điều kiện nào cần được xác minh trước khi dùng một adapter mới trong production?

## Kết luận

Bạn đã thay đổi lớp lưu trữ bằng cách đặt một port giữa application service và persistence, sau đó cung cấp hai adapter có cùng hợp đồng. Controller và View tiếp tục dùng cùng route, Model attribute, template và validation; Spring Profile quyết định adapter được inject. Adapter test xác minh semantics lưu trữ, còn MVC/template test bảo vệ hành vi người dùng nhìn thấy. Khi thêm một công nghệ lưu trữ mới, hãy kiểm tra contract, migration, transaction, concurrency và độ bền dữ liệu trước khi triển khai. Mục tiêu của việc tách lớp không chỉ là đổi database dễ hơn, mà còn là giữ cho giao diện và nghiệp vụ không bị ràng buộc vào chi tiết lưu trữ.
