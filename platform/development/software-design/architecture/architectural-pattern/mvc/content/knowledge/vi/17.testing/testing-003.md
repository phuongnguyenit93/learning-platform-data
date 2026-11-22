# Kiểm thử Controller với các phụ thuộc thay thế

## 1. Vì sao cần thay thế phụ thuộc khi kiểm thử Controller?

Trong kiến trúc Model–View–Controller, Controller tiếp nhận HTTP request, chuyển dữ liệu đầu vào, gọi use case và chọn response hoặc View. Controller thường phụ thuộc vào Service, Mapper, Facade hoặc một thành phần điều phối khác. Nếu kiểm thử Controller bằng toàn bộ hệ thống thật, test có thể phải khởi động database, kết nối dịch vụ bên ngoài hoặc chuẩn bị nhiều dữ liệu không liên quan đến hành vi HTTP đang kiểm tra.

Thay thế phụ thuộc (test doubles) giúp kiểm thử Controller trong phạm vi hẹp và có kiểm soát. Test có thể cung cấp một Service giả để trả về kết quả xác định, sau đó kiểm tra Controller:

- Nhận đúng HTTP method, URL, path variable, query parameter và request body.
- Chuyển dữ liệu đầu vào sang đối tượng mà use case cần.
- Gọi đúng use case trong nhánh hợp lệ.
- Không gọi nghiệp vụ khi binding hoặc validation thất bại.
- Đưa dữ liệu đúng vào Model hoặc response body.
- Chọn đúng View, redirect, status code và header.
- Ánh xạ lỗi theo hợp đồng mà client cần nhận.

Mục tiêu là kiểm tra hợp đồng HTTP và trách nhiệm điều phối của Controller. Quy tắc nghiệp vụ, câu SQL và hành vi của dịch vụ bên ngoài cần có các bài kiểm thử riêng ở tầng tương ứng.

## 2. Ranh giới cần kiểm thử

Với một request xem chi tiết sách, luồng có thể được chia như sau:

~~~mermaid
sequenceDiagram
    participant T as Controller Test
    participant M as MockMvc
    participant C as BookController
    participant S as BookService (mock)
    participant V as View Mapper (mock)
    T->>M: GET /books/{id}
    M->>C: Binding path variable và gọi handler
    C->>S: getById(id)
    S-->>C: Book giả lập
    C->>V: toDetail(book)
    V-->>C: BookDetailView
    C-->>M: Tên View và Model
    M-->>T: HTTP status, view, model
~~~

Trong test, `BookService` và `BookViewMapper` được thay bằng mock hoặc fake. MockMvc tạo request mô phỏng và chạy qua hạ tầng Spring MVC được cấu hình trong test. Không cần database thật để xác minh Controller có đưa đúng dữ liệu vào View hay không.

Controller không nên tự tạo các dependency bằng `new` bên trong handler. Constructor injection giúp khai báo rõ dependency bắt buộc và cho phép test cung cấp implementation thay thế:

~~~java
@Controller
@RequestMapping("/books")
public class BookController {
    private final BookService bookService;
    private final BookViewMapper viewMapper;

    public BookController(
            BookService bookService,
            BookViewMapper viewMapper) {
        this.bookService = bookService;
        this.viewMapper = viewMapper;
    }
}
~~~

Với constructor này, ứng dụng có thể tiêm Service thật trong runtime và test có thể tiêm mock hoặc fake. Nếu Controller dùng `new BookService(...)` bên trong, test khó thay thế Service và dễ bị kéo vào chi tiết hạ tầng.

## 3. Các loại test double

Test double là đối tượng thay thế một dependency thật trong kiểm thử. Những loại thường gặp có mục đích khác nhau:

| Loại | Mục đích | Ví dụ |
|---|---|---|
| Dummy | Được truyền vào để lấp tham số nhưng test không sử dụng | Một collaborator rỗng cho nhánh không gọi đến nó |
| Stub | Trả về dữ liệu cố định để điều khiển tình huống kiểm thử | `getById(id)` luôn trả về một `Book` đã chuẩn bị |
| Mock | Cho phép cấu hình hành vi và xác minh tương tác | Kiểm tra Service không được gọi khi form lỗi |
| Fake | Implementation đơn giản nhưng có hành vi thực tế ở mức giới hạn | Repository lưu dữ liệu trong `Map` |
| Spy | Bọc một đối tượng thật để quan sát một số lời gọi | Theo dõi một mapper thật trong trường hợp đặc biệt |

Mockito có thể tạo mock và spy; một mock được cấu hình trả dữ liệu cũng đóng vai trò stub trong test. Fake thường là class do nhóm phát triển tự viết.

Không cần dùng mock cho mọi dependency. Nếu một mapper thuần Java đơn giản và ổn định, có thể dùng implementation thật. Nếu cần kiểm tra hợp đồng Controller–Service, mock Service thường đủ. Fake phù hợp khi cần hành vi lưu trữ có thể dùng lại mà không phụ thuộc database.

### Khi nào dùng mock và khi nào dùng fake?

Dùng mock khi test cần kiểm soát kết quả của một lời gọi hoặc xác minh một tương tác quan trọng. Ví dụ, khi form không hợp lệ, `BookService.create` tuyệt đối không được gọi.

Dùng fake khi test cần một implementation có trạng thái và hành vi đơn giản. Ví dụ, một `InMemoryBookRepository` cho phép Service đọc/ghi dữ liệu trong bộ nhớ. Fake có thể giúp test nhiều use case mà không cần cấu hình nhiều câu `when`.

Tránh mock quá sâu toàn bộ object graph. Test có thể trở nên giòn vì phụ thuộc vào thứ tự lời gọi hoặc cấu trúc nội bộ, trong khi hợp đồng HTTP vẫn không được kiểm tra.

## 4. Chuẩn bị Controller và DTO cho ví dụ

Ví dụ dưới đây dùng một Controller render HTML. Controller có hai hành vi: hiển thị chi tiết sách và tiếp nhận biểu mẫu tạo sách.

Form DTO:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class CreateBookForm {
    @NotBlank(message = "Tiêu đề không được để trống")
    @Size(max = 200, message = "Tiêu đề tối đa 200 ký tự")
    private String title;

    @NotBlank(message = "ISBN không được để trống")
    private String isbn;

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getIsbn() { return isbn; }
    public void setIsbn(String isbn) { this.isbn = isbn; }
}
~~~

View Model và command:

~~~java
import java.util.UUID;

public record BookDetailView(
        UUID id,
        String title,
        String isbn
) {}

public record CreateBookCommand(String title, String isbn) {}
~~~

Service và mapper là các hợp đồng mà Controller sử dụng:

~~~java
import java.util.UUID;

public interface BookService {
    Book getById(UUID id);
    Book create(CreateBookCommand command);
}

public interface BookViewMapper {
    BookDetailView toDetail(Book book);
}
~~~

`Book` đại diện cho kiểu miền đã được định nghĩa trong ứng dụng. Test Controller không cần biết cách Entity được lưu trữ; test chỉ cần một đối tượng `Book` mẫu để cấu hình mock.

Controller:

~~~java
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/books")
public class BookController {
    private final BookService bookService;
    private final BookViewMapper viewMapper;

    public BookController(
            BookService bookService,
            BookViewMapper viewMapper) {
        this.bookService = bookService;
        this.viewMapper = viewMapper;
    }

    @GetMapping("/{id}")
    public String detail(@PathVariable UUID id, Model model) {
        Book book = bookService.getById(id);
        model.addAttribute("book", viewMapper.toDetail(book));
        return "books/detail";
    }

    @GetMapping("/new")
    public String newForm(Model model) {
        model.addAttribute("form", new CreateBookForm());
        return "books/form";
    }

    @PostMapping
    public String create(
            @Valid @ModelAttribute("form") CreateBookForm form,
            BindingResult errors) {
        if (errors.hasErrors()) {
            return "books/form";
        }

        bookService.create(
                new CreateBookCommand(form.getTitle(), form.getIsbn()));
        return "redirect:/books";
    }
}
~~~

Controller chỉ chuyển request thành command, gọi Service và chuẩn bị View. Nó không chứa truy vấn SQL hoặc tự quyết định các quy tắc như ISBN có duy nhất hay không.

## 5. Kiểm thử handler trực tiếp

Cách đơn giản nhất là khởi tạo Controller bằng constructor và gọi phương thức Java trực tiếp. Cách này phù hợp để kiểm tra logic điều phối thuần túy, chẳng hạn mapper được gọi và model có thuộc tính mong đợi.

~~~java
@Test
void detailAddsMappedViewModel() {
    BookService service = mock(BookService.class);
    BookViewMapper mapper = mock(BookViewMapper.class);
    Book book = testBook();
    BookDetailView detail = new BookDetailView(
            UUID.fromString("11111111-1111-1111-1111-111111111111"),
            "Java cơ bản",
            "9780132350884");
    UUID id = detail.id();

    when(service.getById(id)).thenReturn(book);
    when(mapper.toDetail(book)).thenReturn(detail);

    BookController controller = new BookController(service, mapper);
    ExtendedModelMap model = new ExtendedModelMap();

    String viewName = controller.detail(id, model);

    assertEquals("books/detail", viewName);
    assertEquals(detail, model.getAttribute("book"));
    verify(service).getById(id);
    verify(mapper).toDetail(book);
}
~~~

Ví dụ cần các import JUnit, Mockito và Spring `ExtendedModelMap`. `testBook()` là factory trong test tạo một `Book` hợp lệ. Handler được gọi trực tiếp nên test không kiểm tra routing, chuyển đổi path variable, binding, validation, filter, HTTP status hoặc serialization. Đây là unit test cho phương thức Controller, không phải kiểm thử đầy đủ endpoint.

## 6. Dùng MockMvc với standaloneSetup

`MockMvc` gửi request mô phỏng qua Spring MVC mà không cần khởi động toàn bộ ApplicationContext. `standaloneSetup` đăng ký trực tiếp Controller và cho phép thêm validator, controller advice, converter hoặc interceptor cần thiết.

Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.ui.ExtendedModelMap;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@ExtendWith(MockitoExtension.class)
class BookControllerStandaloneTest {
    @Mock
    BookService bookService;

    @Mock
    BookViewMapper viewMapper;

    MockMvc mvc;
    LocalValidatorFactoryBean validator;

    @BeforeEach
    void setUp() throws Exception {
        BookController controller =
                new BookController(bookService, viewMapper);
        validator = new LocalValidatorFactoryBean();
        validator.afterPropertiesSet();

        mvc = MockMvcBuilders.standaloneSetup(controller)
                .setValidator(validator)
                .build();
    }

    @AfterEach
    void tearDown() throws Exception {
        validator.destroy();
    }

    @Test
    void getDetailReturnsViewAndModel() throws Exception {
        UUID id = UUID.fromString(
                "11111111-1111-1111-1111-111111111111");
        Book book = testBook();
        BookDetailView detail = new BookDetailView(
                id, "Java cơ bản", "9780132350884");

        given(bookService.getById(id)).willReturn(book);
        given(viewMapper.toDetail(book)).willReturn(detail);

        mvc.perform(get("/books/{id}", id))
                .andExpect(status().isOk())
                .andExpect(view().name("books/detail"))
                .andExpect(model().attribute("book", detail));
    }
}
~~~

Ví dụ dùng Mockito extension, Spring Test và `LocalValidatorFactoryBean`; cần các import tĩnh `get`, `status`, `view`, `model`, cùng các import JUnit/Mockito/Spring tương ứng. Nếu test không cần validation thì có thể bỏ validator. Với `standaloneSetup`, các thành phần MVC không tự động được lấy từ cấu hình ứng dụng; phải đăng ký rõ những phần test cần, chẳng hạn `@ControllerAdvice`, formatter, converter, validator hoặc interceptor.

### Kiểm tra path variable và lỗi chuyển đổi

Vì MockMvc gửi request qua Spring MVC, test có thể xác minh việc chuyển UUID từ URL. Ví dụ:

~~~java
mvc.perform(get("/books/{id}", id))
        .andExpect(status().isOk())
        .andExpect(view().name("books/detail"));

mvc.perform(get("/books/not-a-uuid"))
        .andExpect(status().isBadRequest());
~~~

Response cho UUID sai định dạng phụ thuộc exception resolver và cấu hình ứng dụng; nếu dự án tùy biến lỗi, hãy kiểm tra status/body hoặc trang lỗi theo hợp đồng thực tế. Đừng giả định `standaloneSetup` có cùng toàn bộ cấu hình với ứng dụng đang chạy.

## 7. Dùng @WebMvcTest để kiểm tra MVC slice

Trong Spring Boot, `@WebMvcTest(BookController.class)` tạo một ApplicationContext giới hạn cho thành phần MVC được chọn. Controller, MVC infrastructure và các thành phần liên quan được cấu hình; Service và Mapper thường được thay bằng mock.

Với Spring Framework 6.2+ và Spring Boot 3.4+, có thể dùng `@MockitoBean` để đăng ký mock bean trong context:

~~~java
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(BookController.class)
class BookControllerWebTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    BookService bookService;

    @MockitoBean
    BookViewMapper viewMapper;

    @Test
    void detailReturnsMappedView() throws Exception {
        UUID id = UUID.fromString(
                "11111111-1111-1111-1111-111111111111");
        Book book = testBook();
        BookDetailView detail = new BookDetailView(
                id, "Java cơ bản", "9780132350884");

        given(bookService.getById(id)).willReturn(book);
        given(viewMapper.toDetail(book)).willReturn(detail);

        mvc.perform(get("/books/{id}", id)
                        .with(user("librarian").authorities(
                                new SimpleGrantedAuthority("BOOK_VIEW"))))
                .andExpect(status().isOk())
                .andExpect(view().name("books/detail"))
                .andExpect(model().attribute("book", detail));

        verify(bookService).getById(id);
        verify(viewMapper).toDetail(book);
    }
}
~~~

Ví dụ giả định ứng dụng có Spring Security và endpoint yêu cầu authority `BOOK_VIEW`; cần import `SimpleGrantedAuthority` và static `user`. Nếu dự án không bật security filter trong test slice, có thể bỏ request post-processor. Nếu security được bật, test cần cung cấp principal và authority phù hợp; không nên tắt toàn bộ filter rồi kết luận endpoint đã được bảo vệ.

Ở các phiên bản Spring Boot cũ hơn chưa có `@MockitoBean`, có thể dùng `@MockBean` theo phiên bản tương ứng. `@MockBean` đã bị đánh dấu deprecated trong Spring Boot 3.4 để chuyển sang cơ chế bean override của Spring Framework.

### Khi nào chọn standaloneSetup và khi nào chọn @WebMvcTest?

| Tiêu chí | `standaloneSetup` | `@WebMvcTest` |
|---|---|---|
| Khởi tạo | Tự đăng ký Controller | Spring tạo MVC slice trong context |
| Dependency | Tự truyền mock/fake vào constructor | Đăng ký mock bean trong context |
| Cấu hình MVC | Phải thêm validator, advice, converter cần thiết | Dùng cấu hình slice và cấu hình được import |
| Security/filter | Không tự động giống filter chain production; phải cấu hình rõ | Có thể tải cấu hình security trong slice |
| Tốc độ | Thường nhẹ và nhanh | Nặng hơn nhưng gần cấu hình Spring MVC thực tế hơn |
| Phù hợp | Test tập trung một Controller với cấu hình tối thiểu | Kiểm tra mapping, binding, validation, advice và MVC configuration |

Chọn cách phù hợp với điều muốn chứng minh. Không có lý do phải dùng `@SpringBootTest` cho mọi Controller test.

## 8. Kiểm thử GET: dữ liệu được đưa vào Model

Với trang chi tiết, test cần xác minh:

- HTTP method và URL được ánh xạ đến handler đúng.
- Path variable được chuyển thành kiểu dữ liệu mong đợi.
- Service được gọi với ID tương ứng.
- Mapper tạo View Model phù hợp.
- Controller đưa View Model vào Model bằng đúng tên thuộc tính.
- Controller trả đúng tên View.

Ví dụ:

~~~java
mvc.perform(get("/books/{id}", id)
                .with(user("librarian").authorities(
                        new SimpleGrantedAuthority("BOOK_VIEW"))))
        .andExpect(status().isOk())
        .andExpect(view().name("books/detail"))
        .andExpect(model().attributeExists("book"))
        .andExpect(model().attribute("book", detail));
~~~

Không cần kiểm tra từng lời gọi nội bộ nếu kết quả HTTP và Model đã chứng minh hợp đồng. Tuy nhiên, xác minh Service được gọi đúng ID có ích khi Controller có trách nhiệm chuyển đổi path variable hoặc query parameter.

## 9. Kiểm thử POST: validation và không gọi Service

Controller phải dừng trước khi gọi nghiệp vụ nếu dữ liệu đầu vào không hợp lệ. Đây là nơi mock rất hữu ích: test xác minh Service không bị gọi.

~~~java
@Test
void invalidFormReturnsFormAndDoesNotCallService() throws Exception {
    mvc.perform(post("/books")
                    .with(user("librarian").authorities(
                            new SimpleGrantedAuthority("BOOK_CREATE")))
                    .with(csrf())
                    .param("title", "   ")
                    .param("isbn", "9780132350884"))
            .andExpect(status().isOk())
            .andExpect(view().name("books/form"))
            .andExpect(model().attributeHasFieldErrors(
                    "form", "title"));

    verifyNoInteractions(bookService);
}
~~~

Ví dụ cần static import `post`, `status`, `view`, `model`, `csrf`, `user` và Mockito `verifyNoInteractions`. `@WebMvcTest` cần có Bean Validation provider trên classpath, thường được đưa vào qua dependency validation của ứng dụng. `BindingResult` trong Controller giữ lỗi gắn với `form`; template có thể dùng Thymeleaf `th:errors` để hiển thị.

Test này không kiểm tra Service có từ chối dữ liệu sai hay không. Nó xác minh Controller không gọi Service khi validation đầu vào đã thất bại. Service/Model cần unit test riêng cho invariant và quy tắc nghiệp vụ.

### Kiểm thử binding sai kiểu

Nếu form có trường ngày `LocalDate`, gửi chuỗi không hợp lệ để xác minh lỗi conversion được xử lý theo hợp đồng:

~~~java
mvc.perform(post("/books")
                .with(user("librarian").authorities(
                        new SimpleGrantedAuthority("BOOK_CREATE")))
                .with(csrf())
                .param("publishedDate", "not-a-date"))
        .andExpect(status().isOk())
        .andExpect(view().name("books/form"));

verifyNoInteractions(bookService);
~~~

Ví dụ này giả định Form DTO có thuộc tính `publishedDate` kiểu `LocalDate` và handler trả lại form khi có binding errors. Khi thiết kế test, gửi đủ trường khác nếu template hoặc mapper yêu cầu; tập trung xác minh trường đang kiểm tra.

## 10. Kiểm thử POST hợp lệ và redirect

Khi dữ liệu hợp lệ, Controller chuyển Form DTO thành command, gọi Service và trả redirect theo Post/Redirect/Get:

~~~java
@Test
void validFormCallsServiceAndRedirects() throws Exception {
    mvc.perform(post("/books")
                    .with(user("librarian").authorities(
                            new SimpleGrantedAuthority("BOOK_CREATE")))
                    .with(csrf())
                    .param("title", "Java cơ bản")
                    .param("isbn", "9780132350884"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/books"));

    ArgumentCaptor<CreateBookCommand> commandCaptor =
            ArgumentCaptor.forClass(CreateBookCommand.class);
    verify(bookService).create(commandCaptor.capture());
    assertEquals("Java cơ bản", commandCaptor.getValue().title());
    assertEquals("9780132350884", commandCaptor.getValue().isbn());
}
~~~

Ví dụ cần import `ArgumentCaptor` và `assertEquals`. Mockito xác minh command được tạo đúng từ các trường form. Không cần xác minh thứ tự mọi lời gọi nếu thứ tự đó không phải một phần hợp đồng; ưu tiên kiểm tra dữ liệu và kết quả response.

Với handler dùng `RedirectAttributes`, có thể kiểm tra redirect URL và flash attributes trong MockMvc bằng `flash().attribute(...)` khi test trực tiếp request POST. Nếu redirect dẫn đến một request GET tiếp theo, test có thể thực hiện GET riêng và kiểm tra nội dung được hiển thị.

## 11. Kiểm thử lỗi và exception handler

Controller thường dựa vào `@ControllerAdvice` để chuyển lỗi nghiệp vụ thành trang lỗi hoặc API response. Trong test slice, cần chắc chắn advice liên quan được nạp. Nếu không được component scan tự động, có thể import advice hoặc đăng ký vào `standaloneSetup`.

Với một API, có thể kiểm tra:

- Exception nghiệp vụ được ánh xạ sang status đúng, chẳng hạn `409 Conflict`.
- Response body có mã lỗi ổn định và thông điệp an toàn.
- Không trả stack trace, câu SQL hoặc tên class nội bộ.
- Header và content type đúng hợp đồng.

Với HTML, kiểm tra tên View lỗi, status HTTP và Model attribute thông báo. Đừng chỉ kiểm tra Controller có ném exception; cần xác minh response mà client thực sự nhận.

Ví dụ cấu hình `standaloneSetup` với advice:

~~~java
mvc = MockMvcBuilders.standaloneSetup(controller)
        .setControllerAdvice(new PageExceptionHandler())
        .setValidator(validator)
        .build();
~~~

Advice cần được khởi tạo với các dependency của nó nếu có. Khi dùng `@WebMvcTest`, có thể dùng `@Import(PageExceptionHandler.class)` để đưa advice vào slice.

## 12. Kiểm thử phân quyền và CSRF

Trong ứng dụng có Spring Security, Controller test nên xác minh các request được phép và bị từ chối theo cấu hình bảo mật.

- Request không có danh tính có thể bị chuyển đến trang đăng nhập hoặc trả `401`, tùy loại ứng dụng.
- Người dùng đã xác thực nhưng thiếu authority cần bị từ chối, thường là `403`.
- Request POST thiếu CSRF token cần bị từ chối nếu CSRF protection được bật.
- Người có quyền cần đi qua Controller và nhận response phù hợp.

Spring Security Test cung cấp request post-processors như `user(...)`, `jwt()` hoặc `authentication(...)` tùy cơ chế xác thực, cùng `csrf()` cho request thay đổi trạng thái. Test cần phản ánh cấu hình thật; không dùng `addFilters = false` rồi xem đó là bằng chứng security hoạt động.

Phân quyền theo đối tượng, chẳng hạn người dùng chỉ được sửa sách thuộc tenant của mình, thường cần test ở Service/policy và thêm integration test qua endpoint. Controller test với mock Service chỉ có thể xác minh request được chuyển tiếp; nó không chứng minh policy trên đối tượng đã được thực thi nếu Service đã bị thay thế.

## 13. @WebMvcTest, @SpringBootTest và các lớp kiểm thử

Các annotation Spring Boot có phạm vi khác nhau:

| Cách kiểm thử | Phạm vi | Dùng để chứng minh |
|---|---|---|
| Gọi handler trực tiếp | Một phương thức Java | Logic điều phối đơn giản, dữ liệu Model |
| `MockMvcBuilders.standaloneSetup` | Controller và MVC components được đăng ký thủ công | Mapping/binding cơ bản và response với cấu hình test đã chọn |
| `@WebMvcTest` | MVC slice trong Spring context | Request mapping, conversion, validation, advice, security trong slice |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | ApplicationContext rộng hơn, có thể dùng bean thật | Tích hợp Controller với Service, persistence và cấu hình ứng dụng |

Test càng rộng thì càng kiểm tra được nhiều cấu hình thật, nhưng thường chạy chậm hơn và cần nhiều hạ tầng hơn. Nên có nhiều test nhỏ cho logic và MVC slice, cùng một số integration test cho luồng quan trọng.

Không dùng `@SpringBootTest` chỉ để kiểm tra tên View hoặc một status code nếu `@WebMvcTest` đã đủ. Cũng không kết luận cấu hình production đúng chỉ dựa trên standalone test, vì standalone không tự nạp mọi filter, converter, advice và interceptor của ứng dụng.

## 14. Những điều không nên mock trong Controller test

Không nên thay thế chính Controller bằng mock rồi gửi request qua MockMvc. Khi đó test không chạy logic Controller và không chứng minh endpoint hoạt động.

Không nên mock `Model`, `BindingResult` hoặc các đối tượng framework trong MockMvc test. Để Spring tạo chúng giúp test kiểm tra cách framework binding và lưu lỗi.

Không cần mock các kiểu dữ liệu thuần như UUID, record DTO hoặc enum. Tạo giá trị thật giúp test dễ đọc và gần với request thực.

Không nên mock database trong integration test nếu mục tiêu là xác minh query, mapping hoặc transaction. Khi cần kiểm tra hạ tầng persistence, dùng database test phù hợp hoặc môi trường tích hợp được kiểm soát.

Không nên xác minh quá nhiều chi tiết triển khai như một phương thức helper riêng được gọi đúng một lần nếu hành vi bên ngoài không phụ thuộc điều đó. Test nên tập trung vào HTTP contract và những tương tác có ý nghĩa tại ranh giới.

## 15. Tổ chức test và dữ liệu mẫu

Để test dễ bảo trì, hãy tạo helper cho các giá trị dùng lặp lại:

~~~java
final class BookTestData {
    private BookTestData() {}

    static Book book() {
        return Book.create(
                BookId.from(UUID.fromString(
                        "11111111-1111-1111-1111-111111111111")),
                new Isbn("9780132350884"),
                "Java cơ bản");
    }

    static CreateBookForm validForm() {
        CreateBookForm form = new CreateBookForm();
        form.setTitle("Java cơ bản");
        form.setIsbn("9780132350884");
        return form;
    }
}
~~~

Đây là factory minh họa; điều chỉnh theo constructor/factory thật của Domain Model. Dữ liệu mẫu nên hợp lệ theo invariant hiện tại. Tránh dùng một fixture quá lớn cho mọi test vì thay đổi một trường không liên quan có thể làm nhiều test hỏng.

Tên test nên mô tả điều kiện và kết quả, ví dụ `invalidFormReturnsFormWithoutCallingService` hoặc `detailUsesIdFromPathVariable`. Mỗi test nên kiểm tra một hành vi chính và có assertion đủ để phát hiện lỗi thật.

## 16. Ma trận kiểm thử Controller

Một bộ test Controller cho chức năng quản lý sách có thể bao gồm:

| Request | Kết quả cần xác minh | Phụ thuộc thay thế |
|---|---|---|
| `GET /books/{id}` hợp lệ | `200`, View `books/detail`, Model có `book` đúng | Stub Service và Mapper |
| `GET /books/not-a-uuid` | Lỗi binding/status theo hợp đồng | Không cần gọi Service |
| `GET /books/{id}` không tìm thấy | View hoặc response 404 | Stub Service ném lỗi |
| `GET /books/new` | View form và Form DTO rỗng | Không cần Service hoặc chỉ mock nếu có dữ liệu phụ |
| `POST /books` form không hợp lệ | Trả form, lỗi đúng trường, không gọi Service | Mock Service và verify không tương tác |
| `POST /books` form hợp lệ | Gọi Service với command đúng và redirect | Mock Service |
| `POST /books` thiếu CSRF | Bị security filter từ chối khi CSRF bật | Security test setup |
| `POST /books` thiếu authority | Bị từ chối trước hoặc tại method security | Security test setup |
| API request lỗi nghiệp vụ | Status và error body đúng | Stub Service ném exception |

Ma trận là điểm xuất phát. Bổ sung trường hợp query parameter, content type, pagination, multipart hoặc conditional request khi endpoint thực sự hỗ trợ các chức năng đó.

## 17. Những sai lầm thường gặp

- **Kiểm thử Controller bằng database thật cho mọi trường hợp:** làm test chậm và trộn trách nhiệm của nhiều tầng.
- **Tự tạo Service bằng `new` trong Controller:** khiến dependency khó thay thế.
- **Chỉ gọi handler trực tiếp rồi kết luận endpoint đúng:** bỏ qua routing, binding, validation và HTTP response.
- **Dùng mock Controller:** test không còn chạy hành vi cần kiểm tra.
- **Mock mọi thứ:** test gắn chặt vào cấu trúc nội bộ và khó phản ánh hành vi thật.
- **Không kiểm tra Service không được gọi khi form lỗi:** có thể vô tình tạo dữ liệu với request không hợp lệ.
- **Chỉ kiểm tra status:** có thể bỏ sót sai View, sai Model attribute hoặc redirect.
- **Tắt security filter trong mọi test:** làm mất khả năng phát hiện lỗi xác thực, phân quyền và CSRF.
- **Dùng standaloneSetup nhưng quên advice/validator/converter:** test khác hành vi runtime.
- **Dùng @SpringBootTest cho test đơn giản:** tăng thời gian chạy và làm test khó cô lập.
- **Xác minh quá nhiều lời gọi nội bộ:** test dễ hỏng khi refactor dù hợp đồng HTTP không đổi.

## 18. Kết luận

Kiểm thử Controller với phụ thuộc thay thế giúp xác minh ranh giới HTTP và trách nhiệm điều phối mà không cần khởi động toàn bộ hệ thống. Constructor injection cho phép truyền mock, stub hoặc fake; MockMvc kiểm tra routing, binding, validation, Model, View, redirect và response; `standaloneSetup` phù hợp với cấu hình tối thiểu, còn `@WebMvcTest` phù hợp với MVC slice trong Spring context.

Khi thiết kế test, hãy xác định hành vi HTTP cần chứng minh, thay thế đúng những dependency nằm ngoài ranh giới, kiểm tra cả kết quả response lẫn việc gọi use case, và giữ riêng unit test nghiệp vụ cùng integration test hạ tầng. Bộ test rõ ràng giúp thay đổi Controller an toàn mà không làm test phụ thuộc vào database hoặc chi tiết triển khai không liên quan.
