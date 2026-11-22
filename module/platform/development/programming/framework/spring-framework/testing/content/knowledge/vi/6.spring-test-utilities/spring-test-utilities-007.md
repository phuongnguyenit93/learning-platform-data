# ModelAndViewAssert cho controller trả về view

Trong Spring MVC, một controller có thể trả về ModelAndView để chỉ định tên view và các dữ liệu cần đưa vào model. Khi kiểm thử loại controller này, cần xác nhận controller chọn đúng view và cung cấp đúng model attributes cho view đó.

Spring Test cung cấp tiện ích ModelAndViewAssert trong package org.springframework.test.web. Các phương thức của lớp này kiểm tra tên view, sự tồn tại và giá trị của model attributes, cũng như nội dung danh sách trong model. Tiện ích đặc biệt hữu ích khi test đã có một đối tượng ModelAndView và muốn diễn đạt các assertion tập trung vào view và model.

## 1. Hiểu đối tượng ModelAndView

ModelAndView kết hợp hai phần:

- **Model:** tập hợp các thuộc tính dữ liệu mà view có thể sử dụng để hiển thị.
- **View:** tên view logic hoặc một đối tượng View mà Spring sẽ dùng để render phản hồi.

Ví dụ:

~~~java
@GetMapping("/books")
public ModelAndView listBooks() {
    ModelAndView mav = new ModelAndView("books/list");
    mav.addObject("pageTitle", "Books");
    mav.addObject("books", bookService.findAll());
    return mav;
}
~~~

Trong ví dụ này:

- books/list là tên view logic.
- pageTitle là model attribute có giá trị Books.
- books là danh sách dữ liệu được đưa vào model.
- View resolver của Spring sẽ tìm view tương ứng với tên books/list theo cấu hình ứng dụng.

Tên view logic thường không phải đường dẫn file template. Với Thymeleaf, chẳng hạn, books/list có thể được ánh xạ tới một template như templates/books/list.html. Với JSP, view resolver có thể thêm prefix và suffix để tạo đường dẫn JSP. Việc ánh xạ này phụ thuộc cấu hình view resolver.

Một controller cũng có thể trả về ModelAndView bằng cách truyền view name và model vào constructor, hoặc trả về một đối tượng View trực tiếp. Khi controller trả về view object thay vì view name, getViewName() có thể trả về null; khi đó assertion về tên view không phải cách kiểm tra phù hợp.

## 2. ModelAndViewAssert dùng để làm gì?

ModelAndViewAssert là một lớp tiện ích kiểm thử với các phương thức static. Lớp này nhận một đối tượng ModelAndView và xác nhận các thuộc tính cần thiết.

Các assertion thường dùng:

| Phương thức | Mục đích |
|---|---|
| assertViewName(mav, expectedName) | Xác nhận tên view logic |
| assertModelAttributeAvailable(mav, modelName) | Xác nhận model có thuộc tính được yêu cầu |
| assertModelAttributeValue(mav, modelName, expectedValue) | So sánh giá trị của một model attribute |
| assertModelAttributeValues(mav, expectedModel) | Xác nhận các cặp tên/giá trị trong map mong đợi đều có trong model và bằng nhau |
| assertCompareListModelAttribute(mav, modelName, expectedList) | So sánh từng phần tử của một list trong model theo thứ tự |
| assertSortAndCompareListModelAttribute(mav, modelName, expectedList, comparator) | Sắp xếp hai danh sách theo comparator rồi so sánh |
| assertAndReturnModelAttributeOfType(mav, modelName, expectedType) | Xác nhận attribute tồn tại, đúng kiểu và trả về giá trị đã ép kiểu |

Các phương thức nhận ModelAndView làm tham số đầu tiên. Ví dụ:

~~~java
ModelAndViewAssert.assertViewName(mav, "books/list");
ModelAndViewAssert.assertModelAttributeAvailable(mav, "books");
ModelAndViewAssert.assertModelAttributeValue(
        mav, "pageTitle", "Books");
~~~

Khi assertion không đạt, các phương thức assert* ném AssertionError, khiến test thất bại trong test framework nhận diện lỗi assertion.

## 3. Thêm dependency Spring Test

ModelAndViewAssert nằm trong module spring-test. Với dự án Spring Boot, dependency thường đã được cung cấp qua starter kiểm thử:

~~~groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Với dự án Spring Framework không dùng Spring Boot, có thể khai báo spring-test trong test scope và thêm JUnit hoặc test framework mà dự án sử dụng:

~~~groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.junit.jupiter:junit-jupiter")
}
~~~

Cần dùng phiên bản spring-test tương thích với phiên bản Spring Framework của ứng dụng. Dự án dùng Spring Boot nên ưu tiên dependency management của Spring Boot để các module Spring có phiên bản đồng bộ.

Import lớp assertion:

~~~java
import org.springframework.test.web.ModelAndViewAssert;
~~~

## 4. Ví dụ controller trả về ModelAndView

Giả sử ứng dụng có trang danh sách sách. Controller lấy danh sách từ service, đặt dữ liệu vào model và chọn view books/list.

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @GetMapping("/books")
    public ModelAndView listBooks() {
        ModelAndView mav = new ModelAndView("books/list");
        mav.addObject("pageTitle", "Books");
        mav.addObject("books", bookService.findAll());
        return mav;
    }
}
~~~

Service có thể trả về danh sách DTO:

~~~java
public interface BookService {
    List<BookSummary> findAll();
}

public record BookSummary(
        Long id,
        String title,
        String author) {
}
~~~

Hợp đồng của controller trong ví dụ gồm:

- Khi client gửi GET /books, controller chọn view logic books/list.
- Model có thuộc tính pageTitle với giá trị Books.
- Model có thuộc tính books chứa danh sách sách do service cung cấp.

Đây là những kết quả có thể kiểm tra từ ModelAndView mà controller trả về.

## 5. Kiểm thử trực tiếp phương thức controller

Nếu mục tiêu là kiểm tra logic tạo ModelAndView, có thể gọi trực tiếp phương thức controller trong unit test. Service được thay bằng mock để kiểm soát dữ liệu đầu vào của controller.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.BDDMockito.given;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.ModelAndViewAssert;
import org.springframework.web.servlet.ModelAndView;

class BookControllerUnitTest {

    private final BookService bookService =
            org.mockito.Mockito.mock(BookService.class);

    private final BookController controller =
            new BookController(bookService);

    @Test
    void returnsBookListViewWithPageTitleAndBooks() {
        List<BookSummary> books = List.of(
                new BookSummary(1L, "Spring in Action", "Craig Walls"),
                new BookSummary(2L, "Effective Java", "Joshua Bloch")
        );

        given(bookService.findAll()).willReturn(books);

        ModelAndView mav = controller.listBooks();

        assertNotNull(mav);

        ModelAndViewAssert.assertViewName(mav, "books/list");
        ModelAndViewAssert.assertModelAttributeValue(
                mav, "pageTitle", "Books");
        ModelAndViewAssert.assertModelAttributeAvailable(
                mav, "books");

        assertEquals(books, mav.getModel().get("books"));
    }
}
~~~

Test này gọi public method listBooks() và kiểm tra kết quả ModelAndView. Nó xác nhận controller tạo đúng tên view và đưa dữ liệu cần thiết vào model.

Phạm vi của test có giới hạn rõ ràng: nó không chạy Spring MVC dispatcher, không kiểm tra URL mapping, request binding, interceptor, filter hoặc view resolver. Nếu các hành vi đó cũng thuộc mục tiêu, hãy dùng MockMvc.

Có thể dùng MockitoExtension và @Mock để quản lý mock nếu dự án đã sử dụng extension này. Ví dụ trên tạo mock trực tiếp để làm nổi bật việc controller được gọi như một object Java thông thường.

## 6. Dùng ModelAndViewAssert với MockMvc

MockMvc gửi request qua Spring MVC test infrastructure. Sau khi request được xử lý, MvcResult cung cấp ModelAndView nếu request đi theo luồng trả về view.

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.ModelAndViewAssert;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.servlet.ModelAndView;

@WebMvcTest(BookController.class)
class BookControllerMvcTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private BookService bookService;

    @Test
    void returnsBookListViewAndModel() throws Exception {
        List<BookSummary> books = List.of(
                new BookSummary(1L, "Spring in Action", "Craig Walls")
        );

        given(bookService.findAll()).willReturn(books);

        MvcResult result = mockMvc.perform(get("/books"))
                .andExpect(status().isOk())
                .andReturn();

        ModelAndView mav = result.getModelAndView();
        assertNotNull(mav);

        ModelAndViewAssert.assertViewName(mav, "books/list");
        ModelAndViewAssert.assertModelAttributeValue(
                mav, "pageTitle", "Books");
        ModelAndViewAssert.assertModelAttributeAvailable(
                mav, "books");
        ModelAndViewAssert.assertCompareListModelAttribute(
                mav, "books", books);
    }
}
~~~

Luồng kiểm thử gồm:

1. MockMvc gửi GET /books.
2. Spring MVC tìm handler cho request và gọi controller.
3. Controller gọi BookService đã được thay bằng mock.
4. Controller trả về ModelAndView.
5. MvcResult.getModelAndView() lấy đối tượng kết quả.
6. ModelAndViewAssert xác nhận tên view và các model attributes.

@webMvcTest giới hạn ApplicationContext vào các thành phần MVC cần thiết cho controller test. @MockitoBean đăng ký mock thay cho bean BookService trong context. @MockitoBean có trong Spring Framework 6.2 trở lên; với các phiên bản Spring Boot cũ hơn, dự án có thể đang dùng @MockBean của Spring Boot.

Nếu controller trả về @ResponseBody hoặc ResponseEntity, getModelAndView() thường trả về null vì request không tạo view. Trong trường hợp đó, hãy kiểm tra response body bằng các result matcher tương ứng.

## 7. Các assertion quan trọng

### Xác nhận tên view bằng assertViewName

~~~java
ModelAndViewAssert.assertViewName(mav, "books/list");
~~~

Phương thức này so sánh tên view trong ModelAndView với tên mong đợi. Nó hữu ích khi controller có nhiều nhánh trả về view khác nhau.

Ví dụ, nếu người dùng chưa đăng nhập thì controller có thể trả về redirect:/login; test cho nhánh đó có thể xác nhận tên view redirect theo hợp đồng.

Tên view được so sánh là tên logic trong ModelAndView, không phải đường dẫn file template sau khi view resolver xử lý.

### Xác nhận model attribute tồn tại

~~~java
ModelAndViewAssert.assertModelAttributeAvailable(mav, "books");
~~~

Assertion này xác nhận model có key books. Nó phù hợp khi chỉ cần bảo đảm dữ liệu được đưa vào model, còn nội dung chi tiết sẽ được kiểm tra ở assertion khác.

Một attribute tồn tại nhưng có giá trị null vẫn có thể khác với attribute hoàn toàn không tồn tại. Nếu cần kiểm tra cả giá trị, hãy dùng assertModelAttributeValue hoặc lấy attribute theo kiểu mong đợi.

### Xác nhận giá trị model attribute

~~~java
ModelAndViewAssert.assertModelAttributeValue(
        mav, "pageTitle", "Books");
~~~

Phương thức này so sánh giá trị mong đợi với giá trị trong model theo quy tắc equality của object. Vì vậy, với DTO hoặc entity, kết quả phụ thuộc vào cách kiểu dữ liệu triển khai equals().

Dùng assertion này phù hợp cho chuỗi, số, enum, object value hoặc những kiểu có equality rõ ràng.

### Xác nhận nhiều thuộc tính bằng Map

Khi cần kiểm tra một số thuộc tính cùng lúc, có thể tạo map mong đợi:

~~~java
Map<String, Object> expectedModel = Map.of(
        "pageTitle", "Books",
        "pageSize", 20
);

ModelAndViewAssert.assertModelAttributeValues(
        mav, expectedModel);
~~~

Assertion xác nhận tất cả các cặp tên và giá trị trong expectedModel xuất hiện và bằng nhau trong model. Nó không yêu cầu model chỉ chứa đúng những key đó; model có thể có thêm các thuộc tính khác.

Nếu cần kiểm tra một thuộc tính vắng mặt, hãy kiểm tra riêng bằng mav.getModel().containsKey("attributeName") hoặc một assertion phù hợp.

### So sánh danh sách theo thứ tự

Nếu thứ tự các phần tử là một phần của hợp đồng hiển thị, dùng:

~~~java
ModelAndViewAssert.assertCompareListModelAttribute(
        mav, "books", expectedBooks);
~~~

Phương thức này so sánh từng phần tử của danh sách trong model mà không sắp xếp hai danh sách trước. Thứ tự vì thế có ý nghĩa.

Ví dụ, trang danh sách có yêu cầu hiển thị sách mới nhất trước. Test có thể xác nhận danh sách trong model có đúng thứ tự mong đợi.

Các phần tử nên có equality phù hợp. Với Java record, equality được tạo tự động dựa trên các thành phần của record. Với class thông thường, có thể cần triển khai equals() và hashCode().

### So sánh danh sách sau khi sắp xếp

Nếu hợp đồng chỉ yêu cầu tập hợp phần tử mà không quy định thứ tự, có thể dùng:

~~~java
ModelAndViewAssert.assertSortAndCompareListModelAttribute(
        mav, "books", expectedBooks, comparator);
~~~

Phương thức này sắp xếp cả danh sách trong model và danh sách mong đợi bằng comparator rồi so sánh từng phần tử. Nếu truyền comparator là null, API sẽ sử dụng thứ tự tự nhiên của phần tử; kiểu phần tử phải hỗ trợ Comparable.

Ví dụ comparator theo ID:

~~~java
Comparator<BookSummary> byId =
        Comparator.comparing(BookSummary::id);

ModelAndViewAssert.assertSortAndCompareListModelAttribute(
        mav, "books", expectedBooks, byId);
~~~

Chỉ bỏ qua thứ tự khi thứ tự thực sự không thuộc hợp đồng. Nếu người dùng kỳ vọng kết quả đã được sắp xếp theo tên hoặc thời gian, hãy kiểm tra đúng thứ tự đó thay vì sắp xếp lại trước khi so sánh.

### Lấy model attribute và xác nhận kiểu

Khi cần tiếp tục kiểm tra một object trong model, dùng:

~~~java
List<?> books =
        ModelAndViewAssert.assertAndReturnModelAttributeOfType(
                mav, "books", List.class);
~~~

Phương thức này xác nhận attribute tồn tại và kiểu runtime tương thích với kiểu mong đợi, sau đó trả về giá trị đã ép kiểu. Java generic bị type erasure nên việc truyền List.class chỉ xác nhận object là một List; nó không xác nhận kiểu phần tử bên trong.

Ví dụ có thể kết hợp với AssertJ để kiểm tra dữ liệu cụ thể:

~~~java
List<?> books =
        ModelAndViewAssert.assertAndReturnModelAttributeOfType(
                mav, "books", List.class);

assertThat(books)
        .hasSize(2)
        .extracting("title")
        .containsExactly("Spring in Action", "Effective Java");
~~~

## 8. Phân biệt kiểm tra ModelAndView và kiểm tra HTML được render

ModelAndViewAssert kiểm tra dữ liệu điều khiển view: tên view và model. Nó không chứng minh nội dung HTML cuối cùng đã được render đúng.

Có ba câu hỏi khác nhau:

| Câu hỏi | Cách kiểm tra phù hợp |
|---|---|
| Controller chọn view logic nào? | ModelAndViewAssert.assertViewName hoặc view().name(...) |
| Controller đưa dữ liệu nào vào model? | ModelAndViewAssert hoặc model().attribute(...) |
| View resolver và template tạo HTML nào? | Kiểm tra response content trong MVC test hoặc integration test có view engine |

Ví dụ, controller có thể trả về đúng books/list và model có đúng danh sách, nhưng template vẫn có thể tham chiếu sai tên thuộc tính hoặc không hiển thị dữ liệu. Model assertion không phát hiện lỗi HTML đó.

Nếu cần xác nhận nội dung response:

~~~java
mockMvc.perform(get("/books"))
        .andExpect(status().isOk())
        .andExpect(content().string(containsString("Spring in Action")));
~~~

Để kiểm tra template một cách có ý nghĩa, test cần có view engine và template tương ứng trong test/application classpath. Khi mục tiêu chỉ là controller chọn view và chuẩn bị model, không cần biến bài test thành kiểm thử toàn bộ giao diện.

## 9. So sánh với MockMvc result matchers

Trong các test dùng MockMvc, Spring cung cấp result matcher để kiểm tra trực tiếp view và model:

~~~java
mockMvc.perform(get("/books"))
        .andExpect(status().isOk())
        .andExpect(view().name("books/list"))
        .andExpect(model().attributeExists("books"))
        .andExpect(model().attribute("pageTitle", "Books"));
~~~

Các matcher thường dùng:

- view().name(...) kiểm tra view name.
- model().attributeExists(...) kiểm tra model attribute tồn tại.
- model().attribute(...) kiểm tra giá trị attribute.
- model().attributeDoesNotExist(...) kiểm tra attribute không tồn tại.
- model().attributeHasErrors(...) và các matcher liên quan kiểm tra binding/validation errors.

Có thể dùng result matcher trực tiếp khi test chỉ cần xác nhận view và model. ModelAndViewAssert phù hợp khi đã lấy được một ModelAndView, chẳng hạn từ MvcResult, hoặc khi gọi trực tiếp phương thức controller trong unit test.

Tài liệu API hiện hành của Spring mô tả ModelAndViewAssert là tiện ích assertion hướng tới các kịch bản JUnit 4 và TestNG. Các phương thức của nó ném AssertionError, nên có thể được gọi trong test JUnit Jupiter và lỗi vẫn làm test thất bại; tuy vậy, với test MVC mới viết bằng Jupiter, result matcher thường hòa nhập tự nhiên hơn vào chuỗi MockMvc.perform(...).andExpect(...).

## 10. Xử lý redirect và forward

Controller trả về ModelAndView có thể chọn view name đặc biệt:

~~~java
return new ModelAndView("redirect:/books");
~~~

Hoặc:

~~~java
return new ModelAndView("forward:/login");
~~~

Nếu test kiểm tra trực tiếp ModelAndView, có thể xác nhận tên view:

~~~java
ModelAndViewAssert.assertViewName(mav, "redirect:/books");
~~~

Khi dùng MockMvc, redirect thường nên được xác nhận bằng result matcher dành cho redirect:

~~~java
mockMvc.perform(post("/books")
                .param("title", "Spring in Action"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/books"));
~~~

Nếu controller thêm flash attribute qua RedirectAttributes, hãy kiểm tra flash map bằng matcher phù hợp, chẳng hạn flash().attribute("message", "Book created"). Flash attribute có vòng đời riêng qua redirect; không nên mặc định xem nó như model của trang đích.

## 11. Trường hợp ModelAndView dùng View object

ModelAndView có thể được tạo bằng một tên view:

~~~java
ModelAndView mav = new ModelAndView("books/list");
~~~

Hoặc bằng một đối tượng View:

~~~java
ModelAndView mav = new ModelAndView(customView);
~~~

Trong trường hợp thứ hai, mav.getView() trả về đối tượng view và mav.getViewName() có thể là null. assertViewName chỉ phù hợp khi controller cung cấp view name.

Nếu hợp đồng yêu cầu dùng một loại view cụ thể, có thể kiểm tra đối tượng view hoặc kiểm tra kết quả render qua MVC test. Không cố ép một view object thành tên logic không tồn tại.

## 12. Những lỗi thường gặp khi dùng ModelAndViewAssert

### Truyền tham số sai thứ tự

Các phương thức assertion nhận ModelAndView trước, rồi đến tên model attribute và giá trị mong đợi:

~~~java
ModelAndViewAssert.assertModelAttributeValue(
        mav, "pageTitle", "Books");
~~~

Đừng đảo thứ tự thành tên attribute trước mav.

### Gọi assertViewName với controller trả về response body

Nếu controller dùng @ResponseBody hoặc trả ResponseEntity, request không tạo view. MvcResult.getModelAndView() có thể là null. Hãy kiểm tra status, header và body thay vì gọi ModelAndViewAssert.

### Nhầm tên view với đường dẫn template

books/list thường là logical view name. Tên file template có thể là templates/books/list.html. Hãy xác nhận đúng giá trị controller trả về, trừ khi mục tiêu là kiểm tra view resolver.

### Chỉ kiểm tra attribute tồn tại

assertModelAttributeAvailable không xác nhận nội dung của attribute. Nếu dữ liệu phải đúng, hãy dùng assertModelAttributeValue, assertion danh sách hoặc lấy object theo kiểu rồi kiểm tra các trường.

### So sánh object không có equality phù hợp

assertModelAttributeValue và các assertion so sánh phần tử dựa trên equality. Nếu DTO không triển khai equals() đúng như mong muốn, hai object có cùng dữ liệu vẫn có thể không bằng nhau. Hãy dùng record, triển khai equality phù hợp hoặc kiểm tra các trường cần thiết.

### Cho rằng model phải có đúng số lượng key

assertModelAttributeValues xác nhận các thuộc tính mong đợi có mặt và bằng giá trị tương ứng. Nó không phải assertion kiểm tra model chỉ có đúng các key trong map. Nếu muốn kiểm tra key dư, hãy xác nhận riêng kích thước hoặc tập key của model.

### Cho rằng model assertion kiểm tra template

Model đúng chỉ chứng minh controller cung cấp dữ liệu đúng. Template vẫn có thể sai. Khi cần, hãy kiểm tra response content hoặc tích hợp view engine.

### Dùng ModelAndViewAssert cho mọi kiểu controller

Controller trả JSON, file download hoặc ResponseEntity có hợp đồng khác với controller trả view. Chọn assertion phù hợp với kiểu phản hồi của endpoint.

## 13. Quy trình viết test cho controller trả về view

Có thể thực hiện theo trình tự sau:

1. **Xác định view logic:** đọc nhánh controller và xác định tên view mà request hợp lệ phải trả về.
2. **Liệt kê model attributes:** xác định key và dữ liệu mà template cần.
3. **Chuẩn bị collaborator:** mock service để trả về dữ liệu kiểm soát được.
4. **Chọn phạm vi test:** gọi trực tiếp controller nếu chỉ kiểm tra việc tạo ModelAndView; dùng MockMvc nếu cần kiểm tra URL mapping, request handling và Spring MVC dispatch.
5. **Kiểm tra view:** dùng assertViewName hoặc view().name(...).
6. **Kiểm tra model:** xác nhận key tồn tại, giá trị đúng hoặc danh sách đúng thứ tự.
7. **Kiểm tra render khi cần:** xác nhận response content hoặc dùng test có view engine.
8. **Kiểm tra các nhánh khác:** view lỗi, redirect, model validation errors hoặc dữ liệu rỗng nếu chúng thuộc yêu cầu.

Một test có tên rõ ràng như returnsBookListViewWithPageTitleAndBooks cho biết cả điều kiện lẫn kết quả. Khi test thất bại, assertion chỉ ra tên view hay model attribute nào không đạt.

## 14. Ví dụ kiểm tra model validation errors

Một controller trả view có thể nhận form object và quay lại trang nhập khi dữ liệu không hợp lệ:

~~~java
@PostMapping("/books")
public ModelAndView createBook(
        @Valid @ModelAttribute("bookForm") BookForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        ModelAndView mav = new ModelAndView("books/new");
        mav.addObject("pageTitle", "Create book");
        return mav;
    }

    bookService.create(form);
    return new ModelAndView("redirect:/books");
}
~~~

Với nhánh validation lỗi, có thể kiểm tra view và các model attributes cần có:

~~~java
ModelAndView mav = controller.createBook(invalidForm, bindingResult);

ModelAndViewAssert.assertViewName(mav, "books/new");
ModelAndViewAssert.assertModelAttributeAvailable(mav, "bookForm");
ModelAndViewAssert.assertModelAttributeValue(
        mav, "pageTitle", "Create book");
~~~

Nếu muốn xác nhận chi tiết lỗi binding, có thể lấy BindingResult từ model bằng key tương ứng hoặc dùng MockMvc với model().attributeHasErrors("bookForm"). Khi kiểm tra qua MVC, cần gửi dữ liệu request thực tế để Spring thực hiện binding và validation.

## 15. Checklist khi đọc một test dùng ModelAndViewAssert

- Đối tượng ModelAndView được tạo từ đúng controller hoặc request cần kiểm tra.
- View name là tên logic đúng theo hợp đồng.
- Các model attributes bắt buộc có mặt.
- Giá trị model được so sánh theo equality phù hợp.
- Danh sách được kiểm tra đúng thứ tự nếu thứ tự có ý nghĩa.
- Không giả định ModelAndViewAssert đã kiểm tra HTML render.
- Controller trả JSON hoặc response body được kiểm tra bằng assertion dành cho HTTP response.
- Test dùng MockMvc khi cần xác nhận Spring MVC dispatch và request mapping.
- Test kiểm tra view resolver/template khi đó là mục tiêu thực sự.

## Tài liệu tham khảo

- [Spring Framework API: ModelAndViewAssert](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/ModelAndViewAssert.html)
- [Spring Framework API: ModelAndView](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/ModelAndView.html)
- [Spring Framework Reference: Testing Spring MVC Controllers](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)

## Kết luận

ModelAndViewAssert giúp kiểm tra những gì controller trả về cho tầng view: tên view logic và các model attributes. Có thể dùng nó với ModelAndView lấy trực tiếp từ controller hoặc từ MvcResult của MockMvc. Khi cần kiểm tra request mapping và MVC dispatch, MockMvc là ranh giới phù hợp; khi cần kiểm tra HTML cuối cùng, phải kiểm tra response đã render hoặc cấu hình view engine. Chọn assertion theo đúng hợp đồng của controller giúp test rõ ràng và dễ bảo trì.
