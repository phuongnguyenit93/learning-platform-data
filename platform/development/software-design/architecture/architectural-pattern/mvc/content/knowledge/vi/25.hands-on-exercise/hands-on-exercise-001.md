# Xây dựng ứng dụng MVC tối giản không phụ thuộc nền tảng

## 1. Mục tiêu thực hành

Trong bài thực hành này, bạn sẽ xây dựng một ứng dụng quản lý sách nhỏ theo Model–View–Controller (MVC). Ứng dụng hỗ trợ xem danh sách, tìm kiếm và thêm sách. Phần lõi được viết bằng Java thuần, không phụ thuộc Spring MVC, Servlet API, JavaFX hay một framework giao diện cụ thể.

Ta dùng giao diện dòng lệnh làm một View adapter để có thể chạy ứng dụng ngay. Sau đó, bài học chỉ ra cách thay View dòng lệnh bằng View HTML và HTTP adapter mà không phải viết lại quy tắc nghiệp vụ.

Sau khi hoàn thành, bạn sẽ có thể:

- Phân chia Model, View và Controller theo trách nhiệm.
- Tách use case khỏi database và framework.
- Dùng interface để đảo chiều phụ thuộc của persistence.
- Chuyển request hoặc thao tác người dùng thành command.
- Trả dữ liệu trình bày qua View Model.
- Kiểm tra validation đầu vào và invariant nghiệp vụ ở đúng tầng.
- Thay adapter giao diện hoặc lưu trữ mà không thay đổi phần lõi.

**Yêu cầu:** JDK 17 trở lên và một terminal. Không cần Maven, Gradle hoặc thư viện bên ngoài. Bài dùng Java 17 record, switch expression dạng cơ bản và collection API.

## 2. Ứng dụng sẽ được xây dựng

Người dùng có thể chọn một trong các thao tác:

| Lựa chọn | Hành vi |
|---|---|
| 1 | Xem toàn bộ sách |
| 2 | Tìm sách theo tiêu đề, tác giả hoặc ISBN |
| 3 | Thêm sách mới |
| 0 | Thoát ứng dụng |

Mỗi sách có mã định danh, tiêu đề, tác giả và ISBN. Ứng dụng kiểm tra trường bắt buộc và từ chối ISBN trùng. Dữ liệu được lưu trong bộ nhớ để bài tập tập trung vào MVC; khi ứng dụng kết thúc, dữ liệu mẫu sẽ mất.

Luồng xử lý:

~~~mermaid
flowchart TD
    U[Người dùng] --> V[ConsoleBookView]
    V -->|Thao tác và input| C[BookController]
    C -->|Gọi use case| S[BookService]
    S -->|Đọc/ghi qua interface| R[BookRepository]
    I[InMemoryBookRepository] -. implements .-> R
    I --> S
    S --> C
    C -->|View Model / kết quả| V
    V --> U
~~~

Trong bài này, Model gồm Domain Model và application service thực hiện use case. Repository interface là hợp đồng lưu trữ mà application cần; implementation trong bộ nhớ thuộc infrastructure. Controller điều phối thao tác và chuyển kết quả thành dữ liệu dành cho View. View nhận input và trình bày kết quả.

## 3. Tạo cấu trúc dự án

Tạo các thư mục và file sau:

~~~text
mvc-books/
  src/
    main/
      java/
        demo/
          mvc/
            Main.java
            domain/
              Book.java
              DuplicateIsbnException.java
            application/
              BookRepository.java
              BookService.java
            infrastructure/
              InMemoryBookRepository.java
            presentation/
              BookController.java
              BookForm.java
              BookRow.java
              BookListPage.java
              CreateBookResult.java
            view/
              BookView.java
              ConsoleBookView.java
    test/
      java/
        demo/
          mvc/
            BookControllerSmokeTest.java
~~~

Package được chia theo trách nhiệm. Không bắt buộc dự án nào cũng cần nhiều package như vậy; với bài tập này, cách chia giúp nhìn rõ phần miền, use case, adapter lưu trữ và giao diện.

## 4. Xây dựng Model: Domain Entity và lỗi nghiệp vụ

Tạo `domain/Book.java`:

~~~java
package demo.mvc.domain;

import java.util.Locale;
import java.util.Objects;
import java.util.UUID;

public record Book(UUID id, String title, String author, String isbn) {
    public Book {
        Objects.requireNonNull(id, "id không được null");
        title = required(title, "title");
        author = required(author, "author");
        isbn = required(isbn, "isbn")
                .replaceAll("[\\s-]", "")
                .toUpperCase(Locale.ROOT);
        if (isbn.isBlank()) {
            throw new IllegalArgumentException("isbn không hợp lệ");
        }
    }

    private static String required(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " không được để trống");
        }
        return value.trim();
    }
}
~~~

`Book` là Domain Model. Constructor bảo vệ invariant tối thiểu: ID, tiêu đề, tác giả và ISBN phải có giá trị. ISBN được chuẩn hóa bằng cách bỏ khoảng trắng, dấu gạch nối và chuyển thành chữ hoa. Vì chuẩn hóa nằm trong Model, mọi nguồn tạo sách đều có cùng quy tắc, dù dữ liệu đến từ console, HTTP hay import.

Tạo `domain/DuplicateIsbnException.java`:

~~~java
package demo.mvc.domain;

public final class DuplicateIsbnException extends RuntimeException {
    public DuplicateIsbnException(String isbn) {
        super("ISBN đã tồn tại: " + isbn);
    }
}
~~~

Đây là lỗi nghiệp vụ có ý nghĩa cụ thể. Controller có thể chuyển lỗi này thành thông báo phù hợp với form; View không cần biết cách database phát hiện trùng.

## 5. Khai báo hợp đồng lưu trữ

Tạo `application/BookRepository.java`:

~~~java
package demo.mvc.application;

import demo.mvc.domain.Book;
import java.util.List;
import java.util.Optional;

public interface BookRepository {
    List<Book> findAll();
    Optional<Book> findByIsbn(String normalizedIsbn);
    Book save(Book book);
}
~~~

`BookService` cần đọc và lưu sách, nhưng không cần biết dữ liệu nằm trong `Map`, file, PostgreSQL hay một dịch vụ từ xa. Interface này là port của application layer. Adapter lưu trữ sẽ triển khai hợp đồng đó.

## 6. Viết application service

Tạo `application/BookService.java`:

~~~java
package demo.mvc.application;

import demo.mvc.domain.Book;
import demo.mvc.domain.DuplicateIsbnException;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

public final class BookService {
    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    public List<Book> list() {
        return repository.findAll();
    }

    public List<Book> search(String query) {
        String term = query == null
                ? ""
                : query.trim().toLowerCase(Locale.ROOT);

        if (term.isEmpty()) {
            return list();
        }

        return repository.findAll().stream()
                .filter(book -> contains(book.title(), term)
                        || contains(book.author(), term)
                        || contains(book.isbn(), term))
                .toList();
    }

    public Book create(String title, String author, String isbn) {
        Book book = new Book(UUID.randomUUID(), title, author, isbn);

        if (repository.findByIsbn(book.isbn()).isPresent()) {
            throw new DuplicateIsbnException(book.isbn());
        }

        return repository.save(book);
    }

    private boolean contains(String value, String term) {
        return value.toLowerCase(Locale.ROOT).contains(term);
    }
}
~~~

Service thực hiện các use case của ứng dụng:

- `list()` lấy danh sách sách.
- `search()` lọc theo tiêu đề, tác giả hoặc ISBN.
- `create()` tạo Domain Entity, kiểm tra ISBN đã tồn tại và lưu sách.

Service không import `javafx`, `jakarta.servlet`, Spring MVC hoặc kiểu dữ liệu của console. Nó nhận dữ liệu qua tham số và giữ biến tạm trong phạm vi phương thức. Vì vậy, cùng use case có thể được gọi từ nhiều adapter.

Kiểm tra trùng trước khi lưu giúp phản hồi sớm. Khi dùng database thật, hai request đồng thời vẫn có thể cùng vượt qua bước kiểm tra; cần unique constraint trên cột ISBN và chuyển lỗi constraint thành `DuplicateIsbnException` hoặc lỗi nghiệp vụ tương ứng.

## 7. Tạo adapter lưu trữ trong bộ nhớ

Tạo `infrastructure/InMemoryBookRepository.java`:

~~~java
package demo.mvc.infrastructure;

import demo.mvc.application.BookRepository;
import demo.mvc.domain.Book;
import demo.mvc.domain.DuplicateIsbnException;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public final class InMemoryBookRepository implements BookRepository {
    private final ConcurrentMap<String, Book> books =
            new ConcurrentHashMap<>();

    @Override
    public List<Book> findAll() {
        return books.values().stream()
                .sorted(Comparator.comparing(
                        Book::title, String.CASE_INSENSITIVE_ORDER))
                .toList();
    }

    @Override
    public Optional<Book> findByIsbn(String normalizedIsbn) {
        return Optional.ofNullable(books.get(normalizedIsbn));
    }

    @Override
    public Book save(Book book) {
        Book existing = books.putIfAbsent(book.isbn(), book);
        if (existing != null) {
            throw new DuplicateIsbnException(book.isbn());
        }
        return book;
    }
}
~~~

Adapter này dùng `ConcurrentHashMap` để bảo vệ thao tác thêm theo ISBN trong trường hợp có nhiều thread. `putIfAbsent` bảo đảm chỉ một sách có thể được thêm cho cùng key trong adapter này. Danh sách được sắp xếp theo tiêu đề để kết quả hiển thị ổn định.

Đây là implementation dành cho bài thực hành, không phải database bền vững. Khi thay bằng JDBC hoặc JPA, chỉ cần tạo implementation khác của `BookRepository` và cấu hình composition root để dùng implementation mới.

## 8. Tạo hợp đồng dữ liệu cho View

Không đưa Domain Entity trực tiếp vào View nếu giao diện chỉ cần một phần dữ liệu. Tạo một View Model riêng.

`presentation/BookForm.java`:

~~~java
package demo.mvc.presentation;

public record BookForm(String title, String author, String isbn) {}
~~~

`presentation/BookRow.java`:

~~~java
package demo.mvc.presentation;

import java.util.UUID;

public record BookRow(UUID id, String title, String author, String isbn) {}
~~~

`presentation/BookListPage.java`:

~~~java
package demo.mvc.presentation;

import java.util.List;

public record BookListPage(String query, List<BookRow> rows) {
    public BookListPage {
        query = query == null ? "" : query;
        rows = List.copyOf(rows);
    }

    public boolean isEmpty() {
        return rows.isEmpty();
    }
}
~~~

`presentation/CreateBookResult.java`:

~~~java
package demo.mvc.presentation;

import java.util.Map;
import java.util.UUID;

public record CreateBookResult(
        boolean success,
        UUID createdBookId,
        String message,
        Map<String, String> fieldErrors
) {
    public CreateBookResult {
        fieldErrors = Map.copyOf(fieldErrors);
    }

    public static CreateBookResult success(UUID id) {
        return new CreateBookResult(
                true, id, "Đã tạo sách thành công.", Map.of());
    }

    public static CreateBookResult failure(
            String message, Map<String, String> errors) {
        return new CreateBookResult(false, null, message, errors);
    }
}
~~~

`BookRow` và `BookListPage` là dữ liệu trình bày. `CreateBookResult` mô tả kết quả thao tác và lỗi gắn với trường. Những kiểu này không phụ thuộc HTTP status, template engine hoặc control cụ thể.

## 9. Viết Controller

Tạo `presentation/BookController.java`:

~~~java
package demo.mvc.presentation;

import demo.mvc.application.BookService;
import demo.mvc.domain.Book;
import demo.mvc.domain.DuplicateIsbnException;
import java.util.LinkedHashMap;
import java.util.Map;

public final class BookController {
    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    public BookListPage list() {
        return toPage("", bookService.list());
    }

    public BookListPage search(String query) {
        String safeQuery = query == null ? "" : query.trim();
        return toPage(safeQuery, bookService.search(safeQuery));
    }

    public CreateBookResult create(BookForm form) {
        if (form == null) {
            return CreateBookResult.failure(
                    "Dữ liệu biểu mẫu không hợp lệ.",
                    Map.of("form", "Vui lòng nhập lại dữ liệu."));
        }

        Map<String, String> errors = new LinkedHashMap<>();
        requireText(form.title(), "title", "Tiêu đề", errors);
        requireText(form.author(), "author", "Tác giả", errors);
        requireText(form.isbn(), "isbn", "ISBN", errors);

        if (!errors.isEmpty()) {
            return CreateBookResult.failure(
                    "Vui lòng kiểm tra các trường được đánh dấu.", errors);
        }

        try {
            Book created = bookService.create(
                    form.title().trim(),
                    form.author().trim(),
                    form.isbn().trim());
            return CreateBookResult.success(created.id());
        } catch (DuplicateIsbnException exception) {
            return CreateBookResult.failure(
                    "Không thể tạo sách.",
                    Map.of("isbn", "ISBN này đã được sử dụng."));
        }
    }

    private void requireText(
            String value,
            String field,
            String label,
            Map<String, String> errors) {
        if (value == null || value.isBlank()) {
            errors.put(field, label + " không được để trống.");
        }
    }

    private BookListPage toPage(String query, java.util.List<Book> books) {
        var rows = books.stream()
                .map(book -> new BookRow(
                        book.id(),
                        book.title(),
                        book.author(),
                        book.isbn()))
                .toList();
        return new BookListPage(query, rows);
    }
}
~~~

Controller tiếp nhận thao tác từ View, gọi Service và chuẩn bị dữ liệu trình bày. Validation trong Controller giúp phản hồi lỗi nhập liệu ngay trên form. `Book` vẫn tự bảo vệ invariant và Service vẫn kiểm tra ISBN duy nhất; không được chỉ dựa vào Controller vì Service có thể được gọi từ một adapter khác.

Controller trả `BookListPage` thay vì trả `Book` trực tiếp. Nhờ vậy, View chỉ phụ thuộc vào dữ liệu nó cần hiển thị. Phương thức `toPage` chuyển Domain Entity thành View Model tại ranh giới presentation.

## 10. Định nghĩa View và triển khai giao diện dòng lệnh

Tạo `view/BookView.java`:

~~~java
package demo.mvc.view;

import demo.mvc.presentation.BookListPage;
import demo.mvc.presentation.CreateBookResult;

public interface BookView {
    void showBookList(BookListPage page);
    void showCreateResult(CreateBookResult result);
}
~~~

Interface này mô tả khả năng trình bày kết quả. Controller không cần biết View dùng terminal, HTML, JavaFX hay một UI toolkit khác.

Tạo `view/ConsoleBookView.java`:

~~~java
package demo.mvc.view;

import demo.mvc.presentation.BookController;
import demo.mvc.presentation.BookForm;
import demo.mvc.presentation.BookListPage;
import demo.mvc.presentation.BookRow;
import demo.mvc.presentation.CreateBookResult;
import java.io.PrintStream;
import java.util.Scanner;

public final class ConsoleBookView implements BookView {
    private final BookController controller;
    private final Scanner input;
    private final PrintStream output;

    public ConsoleBookView(
            BookController controller,
            Scanner input,
            PrintStream output) {
        this.controller = controller;
        this.input = input;
        this.output = output;
    }

    public void run() {
        boolean running = true;
        while (running) {
            output.println();
            output.println("=== QUẢN LÝ SÁCH ===");
            output.println("1. Xem danh sách");
            output.println("2. Tìm kiếm");
            output.println("3. Thêm sách");
            output.println("0. Thoát");
            output.print("Chọn: ");

            String choice = input.nextLine().trim();
            switch (choice) {
                case "1" -> showBookList(controller.list());
                case "2" -> searchBooks();
                case "3" -> createBook();
                case "0" -> running = false;
                default -> output.println("Lựa chọn không hợp lệ.");
            }
        }
        output.println("Đã thoát ứng dụng.");
    }

    private void searchBooks() {
        output.print("Nhập từ khóa: ");
        String query = input.nextLine();
        showBookList(controller.search(query));
    }

    private void createBook() {
        output.print("Tiêu đề: ");
        String title = input.nextLine();
        output.print("Tác giả: ");
        String author = input.nextLine();
        output.print("ISBN: ");
        String isbn = input.nextLine();

        CreateBookResult result = controller.create(
                new BookForm(title, author, isbn));
        showCreateResult(result);

        if (result.success()) {
            showBookList(controller.list());
        }
    }

    @Override
    public void showBookList(BookListPage page) {
        output.println();
        output.println("--- DANH SÁCH SÁCH ---");
        if (page.isEmpty()) {
            output.println("Không tìm thấy sách phù hợp.");
            return;
        }

        for (BookRow row : page.rows()) {
            output.printf("%s | %s | %s | %s%n",
                    row.id(), row.title(), row.author(), row.isbn());
        }
    }

    @Override
    public void showCreateResult(CreateBookResult result) {
        output.println(result.message());
        result.fieldErrors().forEach((field, message) ->
                output.println("- " + field + ": " + message));
    }
}
~~~

`ConsoleBookView` phụ thuộc vào `BookController` để phát thao tác và nhận kết quả. Nó chỉ xử lý nhập/xuất terminal. Nếu đổi sang giao diện web, phần nhập liệu và render sẽ thay đổi; `BookService`, `Book`, repository port và phần lớn Controller/View Model vẫn có thể được giữ lại.

## 11. Composition Root: lắp ghép các thành phần

Tạo `Main.java`:

~~~java
package demo.mvc;

import demo.mvc.application.BookService;
import demo.mvc.infrastructure.InMemoryBookRepository;
import demo.mvc.presentation.BookController;
import demo.mvc.view.ConsoleBookView;
import java.util.Scanner;

public final class Main {
    private Main() {}

    public static void main(String[] args) {
        var repository = new InMemoryBookRepository();
        var service = new BookService(repository);
        var controller = new BookController(service);

        var view = new ConsoleBookView(
                controller, new Scanner(System.in), System.out);
        view.run();
    }
}
~~~

`Main` là composition root: nơi tạo implementation cụ thể và nối các dependency. Các lớp nghiệp vụ không tự tìm hoặc tự tạo dependency của mình. Khi thay `InMemoryBookRepository` bằng `JdbcBookRepository`, thay đổi chủ yếu nằm ở chỗ lắp ghép này.

## 12. Biên dịch và chạy ứng dụng

Mở terminal tại thư mục `mvc-books`.

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
$files = Get-ChildItem -Path src/main/java -Recurse -Filter *.java | ForEach-Object FullName
javac -d out $files
java -cp out demo.mvc.Main
~~~

Trên macOS/Linux hoặc shell có `find`:

~~~bash
mkdir -p out
javac -d out $(find src/main/java -name '*.java')
java -cp out demo.mvc.Main
~~~

Nếu biên dịch thành công, menu quản lý sách xuất hiện. Thử thêm một sách, liệt kê, tìm theo một phần tiêu đề rồi thêm lại cùng ISBN để quan sát lỗi trùng.

Ví dụ phiên chạy:

~~~text
=== QUẢN LÝ SÁCH ===
1. Xem danh sách
2. Tìm kiếm
3. Thêm sách
0. Thoát
Chọn: 3
Tiêu đề: Clean Architecture
Tác giả: Robert C. Martin
ISBN: 978-0132350884
Đã tạo sách thành công.

--- DANH SÁCH SÁCH ---
6c2d... | Clean Architecture | Robert C. Martin | 9780132350884
~~~

ID thực tế được sinh ngẫu nhiên nên mỗi lần chạy sẽ khác.

## 13. Kiểm tra hành vi Controller không cần framework

Vì `BookController` không phụ thuộc Spring hoặc Servlet API, có thể kiểm tra nó bằng một chương trình Java nhỏ. Tạo `src/test/java/demo/mvc/BookControllerSmokeTest.java`:

~~~java
package demo.mvc;

import demo.mvc.application.BookService;
import demo.mvc.infrastructure.InMemoryBookRepository;
import demo.mvc.presentation.BookController;
import demo.mvc.presentation.BookForm;

public final class BookControllerSmokeTest {
    private BookControllerSmokeTest() {}

    public static void main(String[] args) {
        var repository = new InMemoryBookRepository();
        var controller = new BookController(new BookService(repository));

        var invalid = controller.create(
                new BookForm(" ", "Tác giả", "9780000000001"));
        check(!invalid.success(), "Form rỗng phải bị từ chối");
        check(invalid.fieldErrors().containsKey("title"),
                "Phải có lỗi ở trường title");

        var created = controller.create(new BookForm(
                "Clean Architecture",
                "Robert C. Martin",
                "978-0132350884"));
        check(created.success(), "Sách hợp lệ phải được tạo");

        var duplicate = controller.create(new BookForm(
                "Bản sao", "Tác giả khác", "9780132350884"));
        check(!duplicate.success(), "ISBN trùng phải bị từ chối");
        check(duplicate.fieldErrors().containsKey("isbn"),
                "Lỗi trùng phải gắn với trường isbn");

        var results = controller.search("clean");
        check(results.rows().size() == 1,
                "Tìm kiếm phải trả về đúng một sách");

        System.out.println("PASS: BookController smoke test");
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
~~~

Biên dịch cả source chính và test rồi chạy:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
$files = Get-ChildItem -Path src/main/java,src/test/java -Recurse -Filter *.java | ForEach-Object FullName
javac -d out $files
java -cp out demo.mvc.BookControllerSmokeTest
~~~

Kết quả mong đợi:

~~~text
PASS: BookController smoke test
~~~

Đây là smoke test không dùng test framework để giữ bài tập không phụ thuộc thư viện. Trong dự án thực tế, có thể chuyển các tình huống này thành JUnit test, thêm fake/mock cho các dependency và kiểm tra cả lỗi persistence.

## 14. Thay adapter console bằng adapter web

Phần lõi không biết request HTTP, status code hoặc template engine. Một ứng dụng Spring MVC có thể tạo adapter web nhận request, gọi Controller lõi và chuyển kết quả thành Model/View/redirect.

Ví dụ minh họa:

~~~java
@Controller
@RequestMapping("/books")
public class BookHttpAdapter {
    private final BookController bookController;

    public BookHttpAdapter(BookController bookController) {
        this.bookController = bookController;
    }

    @GetMapping
    public String list(
            @RequestParam(defaultValue = "") String q,
            Model model) {
        model.addAttribute("page", bookController.search(q));
        return "books/list";
    }

    @PostMapping
    public String create(
            @ModelAttribute("form") BookForm form,
            Model model,
            RedirectAttributes redirect) {
        CreateBookResult result = bookController.create(form);
        if (!result.success()) {
            model.addAttribute("result", result);
            return "books/form";
        }

        redirect.addFlashAttribute("message", result.message());
        return "redirect:/books";
    }
}
~~~

Đây là adapter minh họa; cần các import Spring MVC và đăng ký `BookController` lõi cùng dependency của nó thành bean. Trong ứng dụng thực tế, có thể đặt tên lớp là `BookWebController` để phân biệt rõ HTTP adapter với Controller độc lập nền tảng. Có thể dùng Bean Validation trên Form DTO và `BindingResult` ở adapter web; phần kiểm tra invariant và quy tắc nghiệp vụ vẫn phải được giữ trong core.

Template `books/list.html` có thể lặp qua `page.rows()` để hiển thị danh sách; `books/form.html` hiển thị `result.fieldErrors`. Nếu thay console bằng web, chỉ adapter và View thay đổi. Domain Model, Service và repository contract vẫn không cần import Spring MVC.

Với một dự án web thuần, cũng có thể bỏ Controller lõi và để `BookWebController` gọi trực tiếp `BookService`. Bài tập giữ Controller độc lập để thể hiện rõ cách tách điều phối và dữ liệu trình bày khỏi nền tảng giao diện.

## 15. Kiểm tra ranh giới kiến trúc

Sau khi chạy ứng dụng, xem lại các import và dependency:

| Thành phần | Được biết | Không nên biết |
|---|---|---|
| `Book` | Java cơ bản và quy tắc miền | Spring, Servlet, console, database driver |
| `BookService` | Domain Model và `BookRepository` interface | HTTP request, template, `System.in`, JDBC cụ thể |
| `BookRepository` | Hợp đồng đọc/ghi sách | Cách View hiển thị dữ liệu |
| `InMemoryBookRepository` | Repository interface và collection Java | Controller, FXML, HTML template |
| `BookController` | Service, Form và View Model | Terminal, Servlet API, Spring annotation |
| `ConsoleBookView` | Controller và I/O terminal | SQL hoặc quy tắc ISBN duy nhất |
| `Main` | Các implementation cụ thể để lắp ghép | Quy tắc nghiệp vụ chi tiết |

Dependency direction quan trọng hơn số lượng package. Application phụ thuộc vào repository abstraction; implementation lưu trữ phụ thuộc vào abstraction để triển khai nó. Domain không cần biết adapter nào đang được sử dụng.

## 16. Bài tập mở rộng

Hoàn thành các thay đổi sau để củng cố ranh giới MVC:

1. **Thêm cập nhật sách:** tạo use case `rename` và kiểm tra ID sách tồn tại trước khi cập nhật.
2. **Thêm xóa sách:** xác định kết quả khi ID không tồn tại và không để View truy cập Repository trực tiếp.
3. **Thêm sắp xếp:** cho phép sắp xếp theo tiêu đề hoặc tác giả; giữ quy tắc sắp xếp ở application/query layer.
4. **Thêm phân trang:** đưa page number và page size vào query model; giới hạn page size ở server.
5. **Thêm repository lưu file:** tạo adapter khác của `BookRepository`, giữ nguyên `BookService` nếu hợp đồng không đổi.
6. **Thêm database:** triển khai JDBC/JPA adapter và unique constraint cho ISBN.
7. **Thêm web View:** tạo Spring MVC adapter và template; không đưa `HttpServletRequest` vào `BookService`.
8. **Thêm quyền:** truyền Actor đã xác thực vào use case và kiểm tra quyền trên từng sách.

Với mỗi thay đổi, hãy xác định lớp nào phải sửa và lý do. Nếu một thay đổi về giao diện buộc phải sửa Domain Model hoặc SQL, xem lại hướng phụ thuộc.

## 17. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể xác nhận:

- [ ] Ứng dụng biên dịch và chạy bằng JDK 17 trở lên.
- [ ] Có thể liệt kê, tìm kiếm và thêm sách.
- [ ] Form thiếu tiêu đề, tác giả hoặc ISBN bị từ chối với lỗi theo trường.
- [ ] ISBN được chuẩn hóa và không thể thêm trùng.
- [ ] Controller không truy cập trực tiếp repository hoặc database.
- [ ] View không chứa quy tắc nghiệp vụ hoặc truy vấn dữ liệu.
- [ ] Service không phụ thuộc HTTP, console hoặc framework UI.
- [ ] Có thể thay repository implementation qua composition root.
- [ ] Smoke test chạy và in `PASS: BookController smoke test`.

## 18. Lỗi thường gặp khi thực hành

- **Đặt SQL trong Controller:** làm Controller phụ thuộc persistence và khó kiểm thử.
- **Để View tự kiểm tra ISBN trùng:** quy tắc bị gắn với một giao diện và có thể bị bỏ qua bởi adapter khác.
- **Trả Domain Entity trực tiếp cho View:** giao diện bị phụ thuộc cấu trúc miền; dùng View Model khi cần hợp đồng trình bày riêng.
- **Để Service đọc `System.in` hoặc ghi `System.out`:** application layer bị gắn với console.
- **Tạo Repository bằng `new` trong Service:** khó thay adapter và khó kiểm thử; tiêm qua constructor.
- **Chỉ kiểm tra ISBN ở Controller:** Service có thể được gọi từ đường khác; invariant cần được bảo vệ ở Model/application và storage.
- **Cho rằng kiểm tra trùng trước khi insert đủ an toàn:** database thực tế cần unique constraint để xử lý request đồng thời.
- **Dùng một singleton mutable để giữ sách đang chọn:** request hoặc màn hình khác có thể ghi đè state; dùng biến cục bộ hoặc state có scope rõ.
- **Tạo quá nhiều lớp chuyển tiếp:** mỗi abstraction nên tạo ranh giới hoặc trách nhiệm có ý nghĩa.

## 19. Kết luận

Ứng dụng nhỏ này thể hiện MVC bằng một phần lõi Java độc lập nền tảng: Domain Model bảo vệ dữ liệu, application service thực hiện use case, Controller điều phối thao tác và tạo View Model, còn View nhận input và trình bày kết quả. Repository interface tách use case khỏi cách lưu trữ; composition root nối các implementation cụ thể.

Console chỉ là một adapter để chạy bài tập. Khi chuyển sang Spring MVC, JavaFX hoặc một giao diện khác, adapter đầu vào/đầu ra có thể thay đổi trong khi Model và use case vẫn giữ nguyên. Giá trị của thiết kế nằm ở ranh giới trách nhiệm và hướng phụ thuộc rõ ràng, giúp ứng dụng dễ kiểm thử, dễ thay đổi và không bị khóa vào một nền tảng.
