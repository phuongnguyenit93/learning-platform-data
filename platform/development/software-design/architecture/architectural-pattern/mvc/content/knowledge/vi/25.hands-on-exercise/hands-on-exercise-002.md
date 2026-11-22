# Tạo hai View cùng phản ánh một Model

## Mục tiêu thực hành

Trong bài thực hành này, bạn sẽ xây dựng một ứng dụng quản lý danh mục sách bằng Spring MVC và Thymeleaf. Cùng một nguồn dữ liệu danh mục sẽ được trình bày qua hai View khác nhau:

- **View danh sách** hiển thị từng cuốn sách và biểu mẫu cập nhật số bản có sẵn.
- **View tổng quan** hiển thị số đầu sách, tổng số bản có sẵn và danh sách rút gọn.

Khi số bản có sẵn của một cuốn sách được cập nhật, cả hai View phải phản ánh giá trị mới sau khi tải lại. Bài tập giúp bạn quan sát cách Model cung cấp dữ liệu cho nhiều View mà không nhân đôi nguồn dữ liệu hoặc quy tắc nghiệp vụ.

Ứng dụng sử dụng Java 17+, Spring Boot 3.x, Spring MVC và Thymeleaf. Dữ liệu được lưu trong repository giả lập bằng bộ nhớ để bạn tập trung vào luồng MVC; khi hoàn thành, bạn có thể thay repository này bằng database mà không phải viết lại hai template.

Sau khi hoàn thành, bạn có thể:

- Phân biệt domain Model, Spring MVC Model và View Model.
- Tạo một nguồn dữ liệu danh mục dùng chung.
- Dùng Controller đưa cùng một View Model vào hai template.
- Render cùng dữ liệu theo hai cách trình bày khác nhau.
- Cập nhật dữ liệu qua POST và điều hướng theo Post/Redirect/Get.
- Viết kiểm thử xác nhận cả hai View phản ánh cùng trạng thái mới.

## 1. Bài toán

Một thư viện nhỏ cần trang quản lý danh mục sách. Nhân viên có hai cách xem dữ liệu:

1. Trang danh sách để xem từng sách và cập nhật số bản có sẵn.
2. Trang tổng quan để xem số lượng đầu sách và tổng số bản có sẵn.

Dữ liệu mẫu ban đầu:

| ID | Tên sách | Tác giả | Số bản có sẵn |
|---:|---|---|---:|
| 1 | Java căn bản | Nguyễn An | 3 |
| 2 | Thiết kế ứng dụng web | Trần Bình | 5 |

Vì vậy, tổng số đầu sách là 2 và tổng số bản có sẵn là 8.

Nhân viên cập nhật sách có ID 1 từ 3 bản thành 7 bản. Sau khi lưu:

- Trang danh sách phải hiển thị sách Java căn bản có 7 bản.
- Trang tổng quan phải hiển thị tổng số bản có sẵn là 12.
- Cả hai trang phải lấy dữ liệu từ cùng một nguồn trạng thái.

## 2. Phân biệt ba khái niệm Model

Trong bài này, từ Model có thể chỉ ba thứ liên quan nhưng không đồng nhất:

| Khái niệm | Vai trò trong bài |
|---|---|
| Domain Model | Book biểu diễn một cuốn sách và trạng thái nghiệp vụ của nó |
| Spring MVC Model | Đối tượng theo từng request, dùng để chuyển thuộc tính từ Controller sang View |
| View Model | BookCatalogViewModel là dữ liệu đã được chuẩn bị cho nhu cầu trình bày |

Hai request HTTP không chia sẻ cùng một đối tượng org.springframework.ui.Model. Mỗi request có Model container riêng. Điều được chia sẻ là nguồn dữ liệu danh mục và hợp đồng View Model: cả hai Controller method đều lấy trạng thái từ cùng service rồi đưa thuộc tính tên catalog vào Model của request tương ứng.

Phân biệt này giúp tránh một cách hiểu sai: không nên lưu một Spring Model mutable toàn cục để nhiều người dùng cùng truy cập. Trạng thái dùng chung thuộc repository/service; Spring Model chỉ là túi dữ liệu trình bày của một request.

## 3. Chuẩn bị dự án

Tạo một dự án Spring Boot với Java 17 trở lên và Maven. Thêm các dependency sau vào pom.xml:

    <project xmlns="http://maven.apache.org/POM/4.0.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
        <modelVersion>4.0.0</modelVersion>

        <parent>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-parent</artifactId>
            <version>3.4.2</version>
            <relativePath/>
        </parent>

        <groupId>com.example</groupId>
        <artifactId>mvc-two-views</artifactId>
        <version>0.0.1-SNAPSHOT</version>

        <properties>
            <java.version>17</java.version>
        </properties>

        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-web</artifactId>
            </dependency>

            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-thymeleaf</artifactId>
            </dependency>

            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-test</artifactId>
                <scope>test</scope>
            </dependency>
        </dependencies>

        <build>
            <plugins>
                <plugin>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-maven-plugin</artifactId>
                </plugin>
            </plugins>
        </build>
    </project>

Cấu trúc thư mục:

    src/
      main/
        java/com/example/mvctwoviews/
          MvcTwoViewsApplication.java
          model/
            Book.java
          repository/
            InMemoryBookRepository.java
          viewmodel/
            BookItemView.java
            BookCatalogViewModel.java
          service/
            BookCatalogService.java
          web/
            BookController.java
        resources/
          templates/
            books/
              list.html
              summary.html
      test/
        java/com/example/mvctwoviews/
          BookViewsIntegrationTest.java

Nếu dùng Spring Initializr, chọn Spring Web, Thymeleaf và Spring Boot Starter Test. Giữ các package con bên dưới package chứa class ứng dụng để component scanning tìm thấy Controller, Service và Repository.

## 4. Tạo class khởi động ứng dụng

Tạo file MvcTwoViewsApplication.java:

    package com.example.mvctwoviews;

    import org.springframework.boot.SpringApplication;
    import org.springframework.boot.autoconfigure.SpringBootApplication;

    @SpringBootApplication
    public class MvcTwoViewsApplication {

        public static void main(String[] args) {
            SpringApplication.run(MvcTwoViewsApplication.class, args);
        }
    }

@SpringBootApplication bật auto-configuration và component scanning cho package ứng dụng cùng các package con.

## 5. Tạo Domain Model Book

Tạo file model/Book.java:

    package com.example.mvctwoviews.model;

    public record Book(
            long id,
            String title,
            String author,
            int availableCopies) {

        public Book {
            if (availableCopies < 0) {
                throw new IllegalArgumentException(
                        "Số bản có sẵn không được âm");
            }
        }
    }

Book biểu diễn dữ liệu nghiệp vụ của một cuốn sách. Record giúp tạo object bất biến: khi số bản thay đổi, repository sẽ lưu một Book mới thay cho việc sửa trực tiếp object hiện có.

Quy tắc số bản không âm được bảo vệ ngay trong constructor. Như vậy, mọi nơi tạo Book đều phải tuân theo bất biến này, không chỉ form trên giao diện.

## 6. Tạo repository dùng chung

Tạo file repository/InMemoryBookRepository.java:

    package com.example.mvctwoviews.repository;

    import com.example.mvctwoviews.model.Book;
    import org.springframework.stereotype.Repository;

    import java.util.Comparator;
    import java.util.List;
    import java.util.Map;
    import java.util.Optional;
    import java.util.concurrent.ConcurrentHashMap;

    @Repository
    public class InMemoryBookRepository {

        private final Map<Long, Book> books =
                new ConcurrentHashMap<>();

        public InMemoryBookRepository() {
            books.put(1L, new Book(
                    1L, "Java căn bản", "Nguyễn An", 3));

            books.put(2L, new Book(
                    2L, "Thiết kế ứng dụng web", "Trần Bình", 5));
        }

        public List<Book> findAll() {
            return books.values()
                    .stream()
                    .sorted(Comparator.comparingLong(Book::id))
                    .toList();
        }

        public Optional<Book> updateAvailableCopies(
                long id,
                int availableCopies) {

            Book updated = books.computeIfPresent(
                    id,
                    (key, current) -> new Book(
                            current.id(),
                            current.title(),
                            current.author(),
                            availableCopies));

            return Optional.ofNullable(updated);
        }
    }

Repository là một Spring singleton bean, nên các request trong cùng một instance ứng dụng truy cập cùng map books. ConcurrentHashMap hỗ trợ thao tác cập nhật an toàn hơn khi có nhiều request đồng thời; computeIfPresent thay giá trị cho một ID theo một thao tác nguyên tử trên key đó.

Đây chỉ là repository minh họa. Dữ liệu trong bộ nhớ sẽ mất khi ứng dụng khởi động lại và không được chia sẻ giữa nhiều instance chạy độc lập. Khi triển khai thực tế, thay bằng database hoặc một kho lưu trữ dùng chung.

## 7. Tạo View Model dùng cho cả hai View

Tạo file viewmodel/BookItemView.java:

    package com.example.mvctwoviews.viewmodel;

    public record BookItemView(
            long id,
            String title,
            String author,
            int availableCopies) {
    }

Tạo file viewmodel/BookCatalogViewModel.java:

    package com.example.mvctwoviews.viewmodel;

    import java.util.List;

    public record BookCatalogViewModel(
            List<BookItemView> books,
            int totalBooks,
            int totalAvailableCopies) {

        public BookCatalogViewModel {
            books = List.copyOf(books);
        }
    }

BookItemView chỉ chứa những trường cần hiển thị. BookCatalogViewModel gom danh sách và các số liệu tổng hợp để View không phải tự tính toán.

Cả trang danh sách và trang tổng quan sẽ dùng cùng kiểu BookCatalogViewModel, cùng tên thuộc tính catalog và cùng các trường. Nhờ đó, hai template có thể chọn cách trình bày khác nhau mà không tự truy cập repository.

## 8. Tạo service cung cấp Model cho View

Tạo file service/BookCatalogService.java:

    package com.example.mvctwoviews.service;

    import com.example.mvctwoviews.model.Book;
    import com.example.mvctwoviews.repository.InMemoryBookRepository;
    import com.example.mvctwoviews.viewmodel.BookCatalogViewModel;
    import com.example.mvctwoviews.viewmodel.BookItemView;
    import org.springframework.stereotype.Service;

    import java.util.List;

    @Service
    public class BookCatalogService {

        private final InMemoryBookRepository repository;

        public BookCatalogService(
                InMemoryBookRepository repository) {
            this.repository = repository;
        }

        public BookCatalogViewModel getCatalog() {
            List<BookItemView> items = repository.findAll()
                    .stream()
                    .map(this::toItemView)
                    .toList();

            int totalAvailableCopies = items.stream()
                    .mapToInt(BookItemView::availableCopies)
                    .sum();

            return new BookCatalogViewModel(
                    items,
                    items.size(),
                    totalAvailableCopies);
        }

        public boolean updateAvailableCopies(
                long bookId,
                int availableCopies) {

            if (availableCopies < 0) {
                throw new IllegalArgumentException(
                        "Số bản có sẵn không được âm");
            }

            return repository.updateAvailableCopies(
                    bookId,
                    availableCopies).isPresent();
        }

        private BookItemView toItemView(Book book) {
            return new BookItemView(
                    book.id(),
                    book.title(),
                    book.author(),
                    book.availableCopies());
        }
    }

getCatalog() luôn đọc trạng thái hiện tại từ repository và tạo một View Model mới. Hai request gọi method này sẽ nhận hai object View Model riêng, nhưng chúng được tạo từ cùng nguồn dữ liệu.

updateAvailableCopies() thay đổi nguồn dữ liệu. Request kế tiếp gọi getCatalog() sẽ nhận trạng thái mới. Service là nơi điều phối thao tác cập nhật; Controller không cần biết map được lưu như thế nào.

## 9. Tạo Controller với hai endpoint View

Tạo file web/BookController.java:

    package com.example.mvctwoviews.web;

    import com.example.mvctwoviews.service.BookCatalogService;
    import org.springframework.http.HttpStatus;
    import org.springframework.stereotype.Controller;
    import org.springframework.ui.Model;
    import org.springframework.web.bind.annotation.GetMapping;
    import org.springframework.web.bind.annotation.PathVariable;
    import org.springframework.web.bind.annotation.PostMapping;
    import org.springframework.web.bind.annotation.RequestMapping;
    import org.springframework.web.bind.annotation.RequestParam;
    import org.springframework.web.servlet.mvc.support.RedirectAttributes;
    import org.springframework.web.server.ResponseStatusException;

    @Controller
    @RequestMapping("/books")
    public class BookController {

        private final BookCatalogService catalogService;

        public BookController(BookCatalogService catalogService) {
            this.catalogService = catalogService;
        }

        @GetMapping
        public String list(Model model) {
            model.addAttribute(
                    "catalog",
                    catalogService.getCatalog());

            return "books/list";
        }

        @GetMapping("/summary")
        public String summary(Model model) {
            model.addAttribute(
                    "catalog",
                    catalogService.getCatalog());

            return "books/summary";
        }

        @PostMapping("/{id}/copies")
        public String updateCopies(
                @PathVariable long id,
                @RequestParam int availableCopies,
                RedirectAttributes redirectAttributes) {

            if (availableCopies < 0) {
                redirectAttributes.addFlashAttribute(
                        "errorMessage",
                        "Số bản có sẵn phải lớn hơn hoặc bằng 0.");

                return "redirect:/books";
            }

            boolean updated = catalogService.updateAvailableCopies(
                    id,
                    availableCopies);

            if (!updated) {
                throw new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Không tìm thấy sách");
            }

            redirectAttributes.addFlashAttribute(
                    "successMessage",
                    "Đã cập nhật số bản có sẵn.");

            return "redirect:/books";
        }
    }

Hai method GET khác nhau về View được trả về, nhưng cùng gọi catalogService.getCatalog() và cùng thêm thuộc tính catalog vào Spring Model. Hai template sẽ nhận cùng cấu trúc dữ liệu.

POST cập nhật dữ liệu rồi redirect về /books. Đây là mẫu Post/Redirect/Get: sau khi POST thành công, browser nhận redirect và tải lại trang bằng GET. Người dùng refresh trang sẽ không vô tình gửi lại POST vừa thực hiện.

Nếu ID không tồn tại, Controller trả 404. Giá trị âm bị từ chối và hiển thị thông báo. Giá trị không chuyển đổi được thành số nguyên sẽ gặp lỗi binding/conversion của Spring MVC.

## 10. Tạo View thứ nhất: trang danh sách

Tạo file resources/templates/books/list.html:

    <!DOCTYPE html>
    <html lang="vi" xmlns:th="http://www.thymeleaf.org">
    <head>
        <meta charset="UTF-8">
        <title>Danh sách sách</title>
    </head>
    <body>
        <header>
            <h1>Danh sách sách</h1>
            <nav>
                <a th:href="@{/books/summary}">Xem tổng quan</a>
            </nav>
        </header>

        <p>
            Tổng số đầu sách:
            <strong th:text="${catalog.totalBooks}">0</strong>
        </p>

        <p>
            Tổng số bản có sẵn:
            <strong th:text="${catalog.totalAvailableCopies}">0</strong>
        </p>

        <p th:if="${successMessage}"
           role="status"
           th:text="${successMessage}"></p>

        <p th:if="${errorMessage}"
           role="alert"
           th:text="${errorMessage}"></p>

        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Tên sách</th>
                    <th>Tác giả</th>
                    <th>Số bản có sẵn</th>
                    <th>Cập nhật</th>
                </tr>
            </thead>
            <tbody>
                <tr th:each="book : ${catalog.books}">
                    <td th:text="${book.id}">1</td>
                    <td th:text="${book.title}">Java căn bản</td>
                    <td th:text="${book.author}">Nguyễn An</td>
                    <td th:text="${book.availableCopies}">3</td>
                    <td>
                        <form
                            th:action="@{/books/{id}/copies(id=${book.id})}"
                            method="post">
                            <label>
                                Số bản mới
                                <input
                                    type="number"
                                    name="availableCopies"
                                    min="0"
                                    required
                                    th:value="${book.availableCopies}">
                            </label>
                            <button type="submit">Lưu</button>
                        </form>
                    </td>
                </tr>
            </tbody>
        </table>
    </body>
    </html>

Trang này dùng catalog.books để lặp qua danh sách. Mỗi dòng hiển thị thông tin sách và có form gửi số bản mới đến endpoint POST.

Các số liệu tổng hợp cũng được lấy từ catalog; template chỉ hiển thị dữ liệu, không tự truy vấn repository hoặc tính tổng từ database.

## 11. Tạo View thứ hai: trang tổng quan

Tạo file resources/templates/books/summary.html:

    <!DOCTYPE html>
    <html lang="vi" xmlns:th="http://www.thymeleaf.org">
    <head>
        <meta charset="UTF-8">
        <title>Tổng quan danh mục</title>
    </head>
    <body>
        <header>
            <h1>Tổng quan danh mục sách</h1>
            <nav>
                <a th:href="@{/books}">Quay lại danh sách</a>
            </nav>
        </header>

        <section>
            <h2>Chỉ số danh mục</h2>

            <p>
                Số đầu sách:
                <strong th:text="${catalog.totalBooks}">0</strong>
            </p>

            <p>
                Tổng số bản có sẵn:
                <strong th:text="${catalog.totalAvailableCopies}">0</strong>
            </p>
        </section>

        <section>
            <h2>Sách trong danh mục</h2>
            <ul>
                <li th:each="book : ${catalog.books}">
                    <strong th:text="${book.title}">Java căn bản</strong>
                    <span> — </span>
                    <span th:text="${book.availableCopies}">3</span>
                    <span> bản có sẵn</span>
                </li>
            </ul>
        </section>
    </body>
    </html>

Trang tổng quan dùng cùng catalog nhưng trình bày dữ liệu theo dạng chỉ số và danh sách rút gọn. Template không cần biết dữ liệu được lưu trong ConcurrentHashMap, database hay một dịch vụ bên ngoài.

## 12. Chạy ứng dụng và kiểm tra bằng trình duyệt

Tại thư mục dự án, chạy:

    mvnw.cmd spring-boot:run

Nếu đã cài Maven, có thể dùng:

    mvn spring-boot:run

Mở hai URL:

- http://localhost:8080/books — trang danh sách.
- http://localhost:8080/books/summary — trang tổng quan.

### Kết quả ban đầu mong đợi

| Chỉ số | Giá trị |
|---|---:|
| Số đầu sách | 2 |
| Tổng số bản có sẵn | 8 |

| Sách | Số bản |
|---|---:|
| Java căn bản | 3 |
| Thiết kế ứng dụng web | 5 |

Thử cập nhật Java căn bản từ 3 lên 7 tại trang danh sách. Sau khi nhấn Lưu, ứng dụng redirect về /books. Mở trang tổng quan hoặc tải lại trang đó.

### Kết quả sau khi cập nhật

| Chỉ số | Giá trị |
|---|---:|
| Số đầu sách | 2 |
| Tổng số bản có sẵn | 12 |

| Sách | Số bản |
|---|---:|
| Java căn bản | 7 |
| Thiết kế ứng dụng web | 5 |

Nếu trang danh sách hiển thị 7 nhưng trang tổng quan vẫn hiển thị 8, hãy kiểm tra xem hai Controller method có gọi cùng BookCatalogService và service có đọc cùng repository bean hay không.

## 13. Kiểm thử hai View cùng phản ánh dữ liệu

Tạo file src/test/java/com/example/mvctwoviews/BookViewsIntegrationTest.java:

    package com.example.mvctwoviews;

    import com.example.mvctwoviews.repository.InMemoryBookRepository;
    import com.example.mvctwoviews.viewmodel.BookCatalogViewModel;
    import org.junit.jupiter.api.BeforeEach;
    import org.junit.jupiter.api.Test;
    import org.springframework.beans.factory.annotation.Autowired;
    import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
    import org.springframework.boot.test.context.SpringBootTest;
    import org.springframework.test.web.servlet.MockMvc;
    import org.springframework.test.web.servlet.MvcResult;

    import static org.junit.jupiter.api.Assertions.assertEquals;
    import static org.hamcrest.Matchers.containsString;
    import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
    import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
    import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
    import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
    import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
    import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
    import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

    @SpringBootTest
    @AutoConfigureMockMvc
    class BookViewsIntegrationTest {

        @Autowired
        MockMvc mockMvc;

        @Autowired
        InMemoryBookRepository repository;

        @BeforeEach
        void resetData() {
            repository.updateAvailableCopies(1L, 3);
            repository.updateAvailableCopies(2L, 5);
        }

        @Test
        void bothViewsReflectTheSameUpdatedCatalog() throws Exception {

            MvcResult listBefore = mockMvc.perform(get("/books"))
                    .andExpect(status().isOk())
                    .andExpect(view().name("books/list"))
                    .andExpect(model().attributeExists("catalog"))
                    .andReturn();

            MvcResult summaryBefore =
                    mockMvc.perform(get("/books/summary"))
                            .andExpect(status().isOk())
                            .andExpect(view().name("books/summary"))
                            .andExpect(model().attributeExists("catalog"))
                            .andReturn();

            BookCatalogViewModel listCatalog =
                    (BookCatalogViewModel) listBefore
                            .getModelAndView()
                            .getModel()
                            .get("catalog");

            BookCatalogViewModel summaryCatalog =
                    (BookCatalogViewModel) summaryBefore
                            .getModelAndView()
                            .getModel()
                            .get("catalog");

            assertEquals(listCatalog, summaryCatalog);
            assertEquals(8, listCatalog.totalAvailableCopies());

            mockMvc.perform(post("/books/1/copies")
                            .param("availableCopies", "7"))
                    .andExpect(status().is3xxRedirection())
                    .andExpect(redirectedUrl("/books"));

            mockMvc.perform(get("/books"))
                    .andExpect(status().isOk())
                    .andExpect(content().string(containsString("7")));

            mockMvc.perform(get("/books/summary"))
                    .andExpect(status().isOk())
                    .andExpect(content().string(containsString("12")));
        }
    }

Test này xác nhận:

1. GET /books chọn View books/list và cung cấp thuộc tính catalog.
2. GET /books/summary chọn View books/summary và cũng cung cấp catalog.
3. Hai View Model có cùng giá trị ban đầu.
4. POST cập nhật số bản sách thành công và redirect.
5. HTML danh sách phản ánh số bản mới là 7.
6. HTML tổng quan phản ánh tổng số mới là 12.

assertEquals so sánh giá trị của hai record View Model, không yêu cầu hai request dùng cùng một object Spring Model. Đây là điều mong muốn: request có container riêng nhưng đọc cùng trạng thái nghiệp vụ.

Chạy kiểm thử:

    mvnw.cmd test

Nếu dùng Maven đã cài:

    mvn test

## 14. Kiểm tra các trường hợp biên

Sau khi luồng chính hoạt động, bổ sung kiểm thử cho các trường hợp:

| Tình huống | Kết quả mong đợi |
|---|---|
| Cập nhật số bản thành 0 | Chấp nhận; cả hai View hiển thị 0 và tổng mới |
| Cập nhật số bản âm | Redirect về danh sách với thông báo lỗi; dữ liệu không đổi |
| ID sách không tồn tại | Trả 404 |
| Giá trị không phải số nguyên | Spring MVC trả lỗi binding/conversion phù hợp |
| Tải lại trang tổng quan sau cập nhật | Hiển thị dữ liệu mới từ repository |
| Mở danh sách và tổng quan trên hai tab | Mỗi request mới đọc trạng thái hiện tại |

Trong ví dụ, form HTML có min="0" để hỗ trợ người dùng, nhưng kiểm tra ở Controller và bất biến trong Book mới bảo vệ phía server. Client có thể bỏ qua thuộc tính HTML và gửi request trực tiếp.

Ứng dụng hiện chưa bật Spring Security. Nếu bổ sung session authentication, hãy bật CSRF protection và bảo đảm form POST có CSRF token theo cấu hình Spring Security. Không tắt CSRF chỉ để làm cho form hoạt động.

## 15. Bài tập mở rộng

### Mở rộng 1: Thêm View thứ ba

Tạo trang /books/available chỉ liệt kê sách có ít nhất một bản có sẵn. View mới vẫn phải lấy dữ liệu từ BookCatalogService, không tạo repository hoặc danh sách riêng.

### Mở rộng 2: Thêm tìm kiếm

Thêm query parameter q cho trang danh sách. Kết quả tìm kiếm phải được tạo từ cùng nguồn dữ liệu. Xác định rõ tổng số sách trong toàn danh mục và số kết quả sau lọc là hai chỉ số khác nhau.

### Mở rộng 3: Thêm validation bằng Bean Validation

Tạo request/form DTO với @Min(0) và dùng @Valid cùng BindingResult. Khi validation thất bại, render lại form với lỗi phù hợp. Bảo đảm không cập nhật repository khi dữ liệu không hợp lệ.

### Mở rộng 4: Thay repository bằng database

Thay InMemoryBookRepository bằng Spring Data JPA repository. Giữ nguyên BookCatalogService, BookCatalogViewModel và hai template nếu hợp đồng dữ liệu không đổi. Đây là cách kiểm tra mức độ tách biệt giữa persistence và presentation.

### Mở rộng 5: Dùng fragment chung

Tạo Thymeleaf fragment cho thanh điều hướng hoặc phần chỉ số danh mục. Cả hai View có thể include fragment nhưng vẫn giữ bố cục riêng. Không chuyển truy vấn dữ liệu vào fragment.

## 16. Câu hỏi tự đánh giá

1. Hai endpoint GET dùng cùng dữ liệu nhưng trả hai tên View khác nhau ở đâu trong Controller?
2. Vì sao không nên lưu một đối tượng Spring Model toàn cục cho hai request?
3. BookCatalogViewModel khác Book ở điểm nào?
4. Nếu hai template cùng tự truy vấn repository, vấn đề thiết kế nào có thể xuất hiện?
5. Vì sao POST cập nhật xong nên redirect thay vì render trực tiếp trang danh sách?
6. Nếu thay repository bằng database, những thành phần nào có thể giữ nguyên?
7. Làm thế nào kiểm tra rằng cả hai View thật sự phản ánh cùng trạng thái sau cập nhật?
8. Nếu ứng dụng chạy nhiều instance, repository in-memory hiện tại có còn bảo đảm hai instance nhìn thấy cùng dữ liệu không? Vì sao?

## 17. Tiêu chí hoàn thành

Bài thực hành được xem là hoàn thành khi:

- Ứng dụng khởi động được.
- /books render đúng View danh sách.
- /books/summary render đúng View tổng quan.
- Cả hai endpoint dùng cùng BookCatalogService.
- Cả hai đưa thuộc tính catalog vào Spring Model.
- Cả hai template dùng cùng hợp đồng BookCatalogViewModel.
- Cập nhật số bản qua POST làm thay đổi nguồn dữ liệu dùng chung.
- Sau redirect và tải lại, cả hai View hiển thị giá trị mới.
- Giá trị âm bị từ chối và ID không tồn tại được xử lý phù hợp.
- Integration test xác nhận hai View phản ánh cùng dữ liệu.

## Kết luận

Hai View có thể trình bày cùng một Model theo những cách khác nhau mà không cần nhân đôi dữ liệu hoặc logic truy cập. Trong bài thực hành, BookCatalogService đọc một nguồn danh mục và tạo BookCatalogViewModel; Controller đưa thuộc tính catalog vào request Model rồi chọn template danh sách hoặc tổng quan. Khi thao tác POST cập nhật repository, request tiếp theo của cả hai View đều đọc trạng thái mới.

Điểm cốt lõi là phân biệt nguồn trạng thái nghiệp vụ với Spring MVC Model dùng để chuyển dữ liệu cho một request. Mỗi request có Model container riêng, nhưng các View có thể cùng phản ánh một nguồn dữ liệu và một hợp đồng View Model. Cách tổ chức này giữ Controller mỏng, View tập trung trình bày và dữ liệu nhất quán giữa nhiều cách nhìn.
