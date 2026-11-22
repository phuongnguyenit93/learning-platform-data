# Đánh giá số lớp, mức phụ thuộc và khả năng đọc sau cải tiến

## 1. Vì sao cần đánh giá sau khi cải tiến?

Refactor một ứng dụng Model–View–Controller thường làm thay đổi số lượng lớp, cách các lớp gọi nhau và vị trí của logic. Một Controller lớn có thể được tách thành Controller, Application Service, Form/DTO Mapper và Repository adapter. Số lớp tăng lên, nhưng điều đó chưa tự chứng minh thiết kế tốt hơn.

Mục tiêu của cải tiến thiết kế là làm cho trách nhiệm dễ nhận biết, phụ thuộc dễ lần theo, thay đổi ít lan rộng và hành vi dễ kiểm thử. Vì vậy, cần đánh giá đồng thời ba khía cạnh:

- **Số lớp:** có bao nhiêu thành phần mới, mỗi thành phần có lý do tồn tại rõ ràng không, có tạo thêm lớp trung gian không cần thiết không?
- **Mức phụ thuộc:** lớp nào biết lớp nào, phụ thuộc có đi theo hướng kiến trúc dự kiến không, có vòng phụ thuộc hoặc coupling không cần thiết không?
- **Khả năng đọc:** người mới có hiểu luồng request và tìm được nơi sửa hành vi mà không phải nhảy qua quá nhiều file không?

Không có một con số lớp lý tưởng cho mọi ứng dụng. Một module nhỏ có thể chỉ cần vài lớp; một module lớn cần nhiều thành phần để tách use case, persistence, integration và presentation. Đánh giá phải dựa trên phạm vi thay đổi, trách nhiệm và chi phí bảo trì, không dựa vào việc làm số lớp ít nhất.

## 2. Xác định baseline trước khi refactor

Muốn biết cải tiến có hiệu quả hay không, hãy ghi nhận trạng thái ban đầu trước khi thay đổi. Baseline không cần là một báo cáo phức tạp; chỉ cần đủ dữ liệu để so sánh cùng một use case sau refactor.

Với chức năng tạo sách trong MVC, có thể ghi nhận:

| Khía cạnh | Baseline cần ghi |
|---|---|
| Số lớp | Controller, Service, Repository, DTO và adapter hiện có |
| Trách nhiệm | Logic binding, validation, nghiệp vụ, SQL, mapping nằm ở đâu |
| Phụ thuộc | Controller gọi trực tiếp những thành phần nào; package nào phụ thuộc package nào |
| Độ phức tạp | Số nhánh điều kiện, mức lồng nhau, độ dài các phương thức quan trọng |
| Khả năng kiểm thử | Có thể test Controller không cần database không; use case có test độc lập không |
| Khả năng đọc | Người review cần mở bao nhiêu file để lần theo một request; tên lớp/phương thức có diễn đạt đúng ý định không |
| Hành vi | Test hiện có, response HTTP, validation, lỗi và kết quả nghiệp vụ |

Chọn một vài thay đổi đại diện để đánh giá, chẳng hạn “thêm quy tắc ISBN duy nhất”, “đổi cách lưu sách” hoặc “thêm một trường vào form”. Câu hỏi hữu ích là sau refactor, thay đổi đó cần chạm vào những lớp nào và có phải sửa các phần không liên quan không.

## 3. Đếm lớp có ý nghĩa, không chỉ đếm file

Số lớp là một tín hiệu về cấu trúc, nhưng bản thân nó không phải mục tiêu tối ưu. Tách một Controller 400 dòng thành năm lớp có thể là cải tiến nếu mỗi lớp giữ một trách nhiệm riêng. Tạo thêm mười lớp chỉ để chuyển tiếp một lời gọi lại có thể làm code khó đọc hơn.

Khi đếm, nên phân biệt:

- **Lớp có trách nhiệm:** chứa hành vi hoặc chính sách có ý nghĩa như `BookController`, `CreateBookService`, `BookPolicy`.
- **Kiểu dữ liệu:** command, query, form DTO, View Model, record dùng để truyền dữ liệu.
- **Adapter:** lớp nối ứng dụng với database, HTTP client, message broker hoặc framework.
- **Lớp điều phối thuần túy:** chỉ nhận tham số rồi gọi một phương thức khác mà không thêm quy tắc, chuyển đổi hoặc ranh giới hữu ích.

Không nhất thiết phải tách mọi record thành file riêng nếu ngôn ngữ, quy ước dự án và phạm vi sử dụng cho phép nhóm chúng hợp lý. Ngược lại, không nên nhồi nhiều trách nhiệm vào một lớp chỉ để giảm số file.

### Khi nào một lớp mới đáng được tạo?

Một lớp mới thường có lý do khi nó:

1. Có một trách nhiệm hoặc chính sách có thể mô tả bằng một câu rõ ràng.
2. Có lý do thay đổi khác với lớp đang chứa logic đó.
3. Có thể được kiểm thử hoặc thay thế độc lập.
4. Làm giảm phụ thuộc không phù hợp hoặc giảm độ phức tạp của caller.
5. Được dùng lại bởi nhiều use case mà không làm mất ngữ cảnh.

Ví dụ, `BookFormMapper` đáng tách nếu việc chuyển đổi form phức tạp, có nhiều quy tắc chuẩn hóa hoặc được nhiều Controller dùng. Nếu chỉ chuyển hai trường bằng một constructor, một phương thức riêng trong Controller hoặc một static factory có thể dễ đọc hơn.

### Dấu hiệu tách lớp quá mức

- Lớp có một phương thức duy nhất chỉ gọi tiếp một lớp khác mà không thêm ý nghĩa.
- Tên lớp quá chung như `Helper`, `Manager`, `Processor` nhưng không thể giải thích chính xác trách nhiệm.
- Muốn hiểu một hành động đơn giản phải mở quá nhiều file chỉ để lần theo các lớp chuyển tiếp.
- Nhiều interface có đúng một implementation, không có ranh giới thay thế, kiểm thử hoặc module nào cần đến abstraction đó.
- Dữ liệu chỉ được chuyển qua nhiều DTO giống hệt nhau mà không có chuyển đổi hoặc hợp đồng khác biệt.

Những dấu hiệu này không có nghĩa phải gộp lớp ngay. Hãy xem lớp có tạo ranh giới hữu ích cho kiến trúc hoặc kiểm thử hay không trước khi quyết định.

## 4. Đánh giá mức độ tập trung trách nhiệm (cohesion)

Cohesion mô tả mức độ các thuộc tính và hành vi trong một lớp cùng phục vụ một mục đích. Lớp có cohesion tốt thường có một lý do thay đổi tương đối rõ.

Ví dụ, `BookController` có thể:

- Nhận request và path/query parameter.
- Binding form và phối hợp validation đầu vào.
- Gọi use case.
- Chọn View, redirect hoặc response.

Đây là các trách nhiệm cùng thuộc ranh giới HTTP. Nhưng nếu Controller còn chứa SQL, tính giá, gửi email, kiểm tra quyền theo tenant và dựng file export, nó đang ôm nhiều chính sách có lý do thay đổi khác nhau.

Không nên diễn giải Single Responsibility Principle thành “mỗi lớp chỉ có một phương thức” hoặc “mỗi lớp chỉ làm một dòng việc”. Một lớp có thể có nhiều phương thức nếu chúng cùng phục vụ một trách nhiệm nhất quán.

### Câu hỏi review cohesion

- Có thể mô tả mục đích của lớp bằng một câu cụ thể không?
- Các phương thức có cùng một nhóm lý do thay đổi không?
- Có field nào chỉ được một phần nhỏ phương thức sử dụng và thuộc một trách nhiệm khác không?
- Khi thay đổi database, có phải sửa lớp trình bày không?
- Khi thay đổi quy tắc nghiệp vụ, có phải sửa template hoặc Controller ngoài phần hợp đồng cần thiết không?

## 5. Đánh giá coupling và hướng phụ thuộc

Coupling là mức độ một thành phần biết hoặc phụ thuộc vào thành phần khác. Phụ thuộc không thể bị loại bỏ hoàn toàn; ứng dụng cần kết nối các thành phần để thực hiện công việc. Mục tiêu là làm cho phụ thuộc rõ ràng, ổn định và hướng về đúng ranh giới.

Trong một cấu trúc MVC có application layer, hướng phụ thuộc thường được tổ chức như sau:

~~~mermaid
flowchart TD
    B[Browser request] --> C[Controller]
    C --> A[Application Service]
    A --> D[Domain Model]
    A --> P[Repository Port]
    I[Persistence Adapter] -. implements .-> P
    I --> DB[(Database)]
    C -->|View name and View Model| R[View Resolver]
    R --> T[Template]
~~~

Browser gửi request đến Controller; Controller gọi hợp đồng use case và trả tên View cùng dữ liệu trình bày để View Resolver render template. Service phối hợp Domain Model và port cần thiết; adapter persistence triển khai port và giao tiếp với database. Template dùng View Model để trình bày, còn Domain Model không cần biết Spring MVC, template engine hoặc chi tiết SQL.

Đây là hướng phụ thuộc tham khảo, không phải yêu cầu phải có đủ mọi lớp trong mọi ứng dụng. Với một ứng dụng CRUD nhỏ, Service có thể phụ thuộc trực tiếp Spring Data Repository nếu đó là lựa chọn kiến trúc có chủ đích. Điều quan trọng là không để chi tiết hạ tầng rò vào nơi chứa quy tắc miền khi điều đó làm thay đổi nghiệp vụ trở nên khó kiểm soát.

### Những dạng coupling cần nhận diện

| Dạng phụ thuộc | Ví dụ | Điều cần đánh giá |
|---|---|---|
| Compile-time | Controller import class Service | Có phụ thuộc đúng abstraction và đúng package không? |
| Data coupling | Phương thức nhận `CreateBookCommand` | Có truyền đúng dữ liệu cần thiết, tránh object quá rộng không? |
| Framework coupling | Domain Model import `HttpServletRequest` | Framework có lan vào nơi cần độc lập không? |
| Persistence coupling | Controller dùng `JdbcTemplate` | Thay đổi SQL hoặc database có làm sửa giao diện không? |
| Temporal coupling | Phải gọi `init()` trước `save()` | Thứ tự gọi có được thể hiện rõ hoặc đóng gói không? |
| Shared-state coupling | Nhiều lớp sửa cùng một mutable object | Ai sở hữu state và có nguy cơ race condition không? |
| Package coupling | Package A và B tham chiếu vòng nhau | Có thể tách interface hoặc đảo hướng phụ thuộc không? |

## 6. Dùng fan-in, fan-out và dependency graph

Để đánh giá coupling, có thể quan sát số lượng phụ thuộc vào và phụ thuộc ra của một lớp hoặc package.

- **Fan-in:** số thành phần phụ thuộc vào một thành phần. Fan-in cao thường cho thấy thành phần được dùng rộng; thay đổi nó cần xem xét nhiều caller.
- **Fan-out:** số thành phần mà một thành phần phụ thuộc trực tiếp. Fan-out cao có thể làm lớp khó hiểu, khó test và dễ bị ảnh hưởng bởi thay đổi ở nhiều nơi.
- **Dependency cycle:** hai hoặc nhiều package phụ thuộc vòng nhau, khiến khó xác định ranh giới và thứ tự thay đổi.

Ví dụ, nếu `BookController` phụ thuộc `BookService`, `BookRepository`, `JdbcTemplate`, `MailClient`, `Clock` và `PdfRenderer`, fan-out của Controller đã cao và các trách nhiệm có thể bị trộn. Nếu Controller chỉ phụ thuộc `BookApplicationService` và một mapper cần thiết, cấu trúc thường dễ theo dõi hơn.

Fan-in cao không tự động xấu. Một interface ổn định hoặc một thành phần dùng chung có thể có nhiều caller. Tuy nhiên, thay đổi hợp đồng của nó cần được kiểm tra kỹ vì phạm vi ảnh hưởng lớn.

### Chỉ số Instability ở mức package

Một chỉ số kiến trúc thường dùng là Instability:

\[ I = \frac{C_e}{C_a + C_e} \]

Trong đó:

- `C_e` là số phụ thuộc đi ra khỏi package (efferent coupling).
- `C_a` là số phụ thuộc đi vào package từ package khác (afferent coupling).

Giá trị gần 0 biểu thị package được nhiều thành phần khác phụ thuộc và có ít phụ thuộc đi ra; package tương đối ổn định. Giá trị gần 1 biểu thị package phụ thuộc nhiều thành phần khác và ít package phụ thuộc vào nó; package tương đối dễ thay đổi từ bên ngoài.

Chỉ số này giúp mở đầu cuộc trao đổi, không phải điểm chất lượng. Package ở tầng UI có thể có instability cao vì nó phụ thuộc application layer; đó có thể là hướng phụ thuộc hợp lý. Nếu `C_a + C_e = 0`, chỉ số không xác định và không nên tự gán một giá trị có ý nghĩa.

## 7. Nhận diện vòng phụ thuộc giữa package

Vòng phụ thuộc làm cho việc thay đổi một package có thể kéo theo package khác theo chuỗi khó đoán.

~~~mermaid
flowchart LR
    UI[ui] --> APP[application]
    APP --> DOMAIN[domain]
    DOMAIN --> INFRA[infrastructure]
    INFRA --> APP
~~~

Ví dụ trên có vòng `application → domain → infrastructure → application`. Một cách xử lý là xác định hợp đồng cần thiết ở phía application/domain, để infrastructure triển khai hợp đồng đó; domain không import implementation cụ thể.

Không phải mọi vòng phụ thuộc class-level đều có cùng mức rủi ro, nhưng package cycle thường là tín hiệu cần xem lại module boundary. Có thể dùng công cụ phân tích dependency hoặc rule test để phát hiện package không được phép phụ thuộc vào nhau.

## 8. Ví dụ trước cải tiến: Controller ôm nhiều trách nhiệm

Ví dụ rút gọn dưới đây cho thấy một Controller vừa xử lý HTTP, validation, SQL và thông báo:

~~~java
@Controller
@RequestMapping("/books")
public class BookController {
    private final JdbcTemplate jdbc;
    private final MailClient mailClient;

    public BookController(JdbcTemplate jdbc, MailClient mailClient) {
        this.jdbc = jdbc;
        this.mailClient = mailClient;
    }

    @PostMapping
    public String create(
            @ModelAttribute BookForm form,
            BindingResult errors) {
        if (form.getTitle() == null || form.getTitle().isBlank()) {
            errors.rejectValue("title", "required");
            return "books/form";
        }

        Integer count = jdbc.queryForObject(
                "select count(*) from books where isbn = ?",
                Integer.class, form.getIsbn());
        if (count != null && count > 0) {
            errors.rejectValue("isbn", "duplicate");
            return "books/form";
        }

        jdbc.update(
                "insert into books(title, isbn) values (?, ?)",
                form.getTitle(), form.getIsbn());
        mailClient.sendBookCreated(form.getTitle());
        return "redirect:/books";
    }
}
~~~

Controller này có nhiều lý do thay đổi: URL và response, quy tắc đầu vào, schema SQL, chính sách ISBN duy nhất và tích hợp email. Nó cũng khó kiểm thử độc lập vì cần mock nhiều chi tiết hạ tầng hoặc khởi động database.

## 9. Ví dụ sau cải tiến: lớp tăng nhưng trách nhiệm rõ hơn

Một cách tách có thể là:

- `BookController`: binding request, gọi use case và chọn response.
- `CreateBookService`: điều phối use case và transaction.
- `BookRepository`: hợp đồng lưu trữ mà use case cần.
- `JdbcBookRepository`: triển khai truy vấn SQL.
- `BookForm`: dữ liệu đầu vào cho giao diện.

Controller:

~~~java
@Controller
@RequestMapping("/books")
public class BookController {
    private final CreateBookService createBook;

    public BookController(CreateBookService createBook) {
        this.createBook = createBook;
    }

    @PostMapping
    public String create(
            @Valid @ModelAttribute("form") BookForm form,
            BindingResult errors) {
        if (errors.hasErrors()) {
            return "books/form";
        }

        try {
            createBook.execute(
                    new CreateBookCommand(form.getTitle(), form.getIsbn()));
            return "redirect:/books";
        } catch (DuplicateIsbnException exception) {
            errors.rejectValue("isbn", "duplicate");
            return "books/form";
        }
    }
}
~~~

Service:

~~~java
@Service
public class CreateBookService {
    private final BookRepository books;

    public CreateBookService(BookRepository books) {
        this.books = books;
    }

    @Transactional
    public void execute(CreateBookCommand command) {
        Isbn isbn = new Isbn(command.isbn());
        if (books.existsByIsbn(isbn)) {
            throw new DuplicateIsbnException();
        }

        Book book = Book.create(command.title(), isbn);
        books.save(book);
    }
}
~~~

Repository port và adapter:

~~~java
public interface BookRepository {
    boolean existsByIsbn(Isbn isbn);
    void save(Book book);
}

@Repository
public class JdbcBookRepository implements BookRepository {
    private final JdbcTemplate jdbc;

    public JdbcBookRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public boolean existsByIsbn(Isbn isbn) {
        Integer count = jdbc.queryForObject(
                "select count(*) from books where isbn = ?",
                Integer.class, isbn.value());
        return count != null && count > 0;
    }

    @Override
    public void save(Book book) {
        jdbc.update(
                "insert into books(title, isbn) values (?, ?)",
                book.title(), book.isbn().value());
    }
}
~~~

Ví dụ giả định `BookForm`, `CreateBookCommand`, `Isbn`, `Book`, `DuplicateIsbnException` và các import cần thiết đã được định nghĩa. Trong triển khai thực tế, constraint unique ở database vẫn cần thiết vì hai request đồng thời có thể cùng vượt qua bước `existsByIsbn`; adapter cần chuyển lỗi unique constraint thành lỗi nghiệp vụ phù hợp.

Service này chưa thể hiện tích hợp email. Nếu gửi email là một phần của use case, hãy xác định chính sách nhất quán và có thể dùng event/outbox; đừng giữ `MailClient` trong Controller chỉ để giảm số lớp. Cũng không cần tạo riêng `BookFormMapper` nếu chuyển đổi command chỉ gồm hai trường và không có logic đáng kể.

### So sánh trước và sau

| Tiêu chí | Trước | Sau |
|---|---|---|
| Số lớp chính | 1 Controller | Controller, Service, Repository port, JDBC adapter (và các kiểu dữ liệu) |
| Trách nhiệm Controller | HTTP, validation, SQL, email, nghiệp vụ | HTTP binding, gọi use case, chọn View/redirect |
| Phụ thuộc Controller | JDBC và Mail client | Application Service |
| Phụ thuộc nghiệp vụ vào SQL | Trực tiếp trong Controller | Qua Repository port/adapter |
| Kiểm thử Controller | Dễ kéo theo hạ tầng | Có thể mock Service và dùng MockMvc |
| Kiểm thử use case | Trộn với HTTP và JDBC | Có thể test Service với fake Repository |
| Chi phí lần theo luồng | Ít file nhưng một lớp nhiều nhánh | Nhiều file hơn nhưng mỗi ranh giới rõ hơn |

Số lớp tăng là chấp nhận được vì mỗi lớp có một trách nhiệm và một ranh giới kiểm thử. Nếu dự án rất nhỏ, có thể chưa cần port riêng cho Repository; lựa chọn đó nên dựa vào mức cần tách persistence khỏi use case.

## 10. Đánh giá khả năng đọc sau refactor

Khả năng đọc không chỉ là số dòng hoặc độ dài file. Một lớp 40 dòng vẫn khó đọc nếu tên không rõ, trạng thái ẩn hoặc phụ thuộc bị truyền vòng qua nhiều tầng.

Các dấu hiệu tích cực:

- Tên class, method và biến diễn đạt mục đích nghiệp vụ hoặc vai trò kỹ thuật cụ thể.
- Một phương thức có luồng chính dễ nhận ra; nhánh lỗi và điều kiện biên được đặt ở vị trí hợp lý.
- Constructor thể hiện dependency cần thiết, không có service locator hoặc `new` hạ tầng ẩn bên trong.
- DTO/command có hợp đồng rõ, không truyền cả `HttpServletRequest` vào Service.
- Logic nghiệp vụ không bị giấu trong template hoặc callback.
- Có thể đọc từ Controller đến use case rồi đến port mà không cần hiểu toàn bộ ứng dụng.
- Comment giải thích lý do hoặc ràng buộc khó thấy, không lặp lại câu lệnh.

### Đọc theo một thay đổi cụ thể

Hãy yêu cầu reviewer thực hiện một nhiệm vụ nhỏ mà không sửa code, ví dụ “tìm nơi quy định ISBN trùng được xử lý như thế nào”. Quan sát:

1. Reviewer bắt đầu từ endpoint hay từ tên use case?
2. Có thể tìm nơi chứa quy tắc mà không đọc toàn bộ Controller không?
3. Có phải lần theo nhiều lớp chỉ chuyển tiếp dữ liệu không?
4. Có phân biệt được validation giao diện với invariant nghiệp vụ không?
5. Có biết test nào chứng minh hành vi đó không?

Đây là cách đánh giá đọc hiểu thực tế tốt hơn việc chỉ đếm số file hoặc dùng một giới hạn LOC cố định.

## 11. Các chỉ số định lượng nên theo dõi

Không có chỉ số đơn lẻ nào đo được chất lượng thiết kế. Có thể kết hợp các số liệu sau để nhận diện khu vực cần review:

| Chỉ số | Điều nó gợi ý | Giới hạn |
|---|---|---|
| Số lớp và số package | Quy mô cấu trúc | Không nói lớp có trách nhiệm rõ hay không |
| LOC theo lớp/phương thức | Nơi có thể quá lớn | Code ngắn vẫn có thể coupling cao hoặc khó hiểu |
| Cyclomatic complexity | Số đường đi điều khiển độc lập tương đối | Không đo được chất lượng tên, abstraction hoặc domain model |
| Fan-in/fan-out | Mức sử dụng và số phụ thuộc | Không phản ánh đầy đủ chất lượng hợp đồng |
| Package cycles | Ranh giới module có thể bị rối | Cần xem cycle có ảnh hưởng thực tế nào |
| Số dependency framework ở domain | Mức rò rỉ framework | Một số tích hợp có chủ đích vẫn hợp lý |
| Thời gian chạy test và phạm vi test | Khả năng kiểm thử, chi phí feedback | Coverage cao không đồng nghĩa test có assertion hữu ích |
| Số file phải sửa cho một thay đổi | Mức lan truyền thay đổi | Thay đổi lớn tự nhiên có thể cần nhiều file |

Chỉ số nên được dùng để đặt câu hỏi, không làm ngưỡng tự động buộc refactor. Ví dụ, một lớp 250 dòng có thể vẫn dễ đọc nếu nó là một bộ quy tắc cohesive; một lớp 30 dòng có thể khó bảo trì nếu phụ thuộc mười service và có state ẩn.

## 12. Đánh giá dependency direction bằng package rule

Trong MVC, có thể đặt quy ước rõ về package:

| Package | Có thể phụ thuộc | Nên tránh phụ thuộc |
|---|---|---|
| `web` / `controller` | Application API, presentation DTO, validation framework | JDBC, SQL, implementation persistence |
| `application` | Domain, application ports, transaction boundary | Servlet API, template engine, chi tiết database |
| `domain` | Các kiểu miền và thư viện nền tảng tối thiểu | Spring MVC, JPA nếu muốn domain độc lập, HTTP client |
| `infrastructure` | Application/domain ports, driver và framework tích hợp | Controller và View implementation |
| `templates` | View Model và message keys được cung cấp | Truy cập trực tiếp Repository hoặc thực thi nghiệp vụ |

Đây là một quy ước tham khảo. Một dự án dùng JPA annotation trong Entity có thể chấp nhận mức phụ thuộc framework persistence ở domain model; điều quan trọng là quyết định đó có chủ đích và được áp dụng nhất quán.

Có thể kiểm tra dependency rule bằng ArchUnit hoặc công cụ phân tích bytecode. Ví dụ rule khái niệm: package `domain` không được phụ thuộc `web` hoặc `infrastructure`; package `web` không được import package implementation persistence. Rule tự động giúp refactor không vô tình đảo hướng phụ thuộc về sau.

## 13. Đánh giá thay đổi bằng test và phạm vi ảnh hưởng

Refactor chỉ có ích nếu hành vi bên ngoài được giữ nguyên hoặc thay đổi đúng theo yêu cầu. Trước khi đánh giá cấu trúc, cần xác minh test bảo vệ các hành vi quan trọng:

- Request hợp lệ tạo dữ liệu và redirect/response đúng.
- Binding và validation lỗi không gọi use case.
- Lỗi nghiệp vụ được ánh xạ thành thông báo hoặc status phù hợp.
- Quyền truy cập vẫn được kiểm tra ở mọi đường gọi.
- Transaction và constraint dữ liệu vẫn giữ tính nhất quán.
- Controller test không cần database nếu chỉ kiểm tra HTTP contract.
- Service test có thể chạy với fake/mock port mà không khởi động web layer.

Đánh giá số file phải sửa cho một thay đổi đại diện. Nếu thêm một trường hiển thị buộc phải sửa Domain Entity, SQL, Controller, template, email client và nhiều test không liên quan, hãy xem lại ranh giới dữ liệu. Nếu thêm một quy tắc nghiệp vụ chỉ cần sửa use case/domain policy và test tương ứng, phạm vi thay đổi đã tập trung hơn.

## 14. Quy trình review before/after

Một quy trình review ngắn có thể thực hiện theo thứ tự:

1. **Chọn use case:** xác định endpoint và thay đổi đại diện.
2. **Ghi baseline:** số lớp, trách nhiệm, phụ thuộc, độ phức tạp và test hiện có.
3. **Vẽ luồng phụ thuộc:** từ View/Controller đến Service, Model và adapter.
4. **Review cohesion:** mỗi lớp mới có trách nhiệm và lý do thay đổi rõ không?
5. **Review coupling:** fan-out có giảm ở lớp điều phối không; dependency direction có đúng không; có package cycle mới không?
6. **Đọc lại luồng:** người khác có thể tìm logic và hiểu request mà không cần quá nhiều context không?
7. **Chạy test phù hợp:** unit, MVC slice và integration test cho các ranh giới bị ảnh hưởng.
8. **So sánh phạm vi thay đổi:** một yêu cầu tiếp theo có ít lan rộng hơn không?

Không cần thu thập mọi metric cho mọi pull request. Chọn chỉ số tương xứng với kích thước refactor và rủi ro của module.

## 15. Phiếu đánh giá thiết kế

Có thể dùng bảng sau trong review. Điểm 0–2 chỉ là cách tổ chức thảo luận, không phải điểm chuẩn chất lượng tuyệt đối.

| Tiêu chí | 0 – Cần cải thiện | 1 – Chấp nhận được | 2 – Rõ ràng |
|---|---|---|---|
| Trách nhiệm lớp | Nhiều lý do thay đổi trộn lẫn | Có tách nhưng một số lớp còn ôm nhiều việc | Mỗi lớp có mục đích và ranh giới rõ |
| Số lớp mới | Nhiều lớp chuyển tiếp không có giá trị | Một vài lớp có ích, vài lớp còn dư | Mỗi lớp mới hỗ trợ trách nhiệm hoặc ranh giới cụ thể |
| Phụ thuộc | Fan-out cao, phụ thuộc ngược hoặc vòng | Phần lớn đúng hướng, còn ngoại lệ | Hợp đồng rõ, hướng phụ thuộc nhất quán |
| Cohesion | Field/method không liên quan cùng lớp | Có nhóm trách nhiệm nhưng còn trộn | Dữ liệu và hành vi cùng phục vụ một mục đích |
| Khả năng đọc | Khó lần theo luồng và tên mơ hồ | Luồng chính hiểu được nhưng cần nhiều context | Luồng use case rõ, tên và cấu trúc dễ tìm |
| Khả năng kiểm thử | Cần khởi động nhiều hạ tầng cho logic nhỏ | Một số ranh giới đã test độc lập | Controller, use case và adapter có test đúng phạm vi |
| Khả năng thay đổi | Thay đổi nhỏ lan ra nhiều lớp không liên quan | Phạm vi thay đổi đã giảm một phần | Thay đổi tập trung vào nơi sở hữu chính sách |

Không cộng điểm rồi dùng một ngưỡng cứng để kết luận. Nếu tiêu chí “phụ thuộc” được đánh giá 0 vì domain import Controller, đó là vấn đề cần xử lý ngay cả khi tổng điểm cao. Ghi rõ bằng chứng và tác động thay vì chỉ ghi điểm.

## 16. Những sai lầm thường gặp khi đánh giá

- **Coi ít lớp là tốt hơn:** có thể che giấu Controller hoặc Service ôm quá nhiều trách nhiệm.
- **Coi nhiều lớp là kiến trúc tốt:** lớp chuyển tiếp và abstraction không có mục đích làm tăng chi phí đọc.
- **Đặt ngưỡng LOC cứng cho mọi lớp:** kích thước không phản ánh đầy đủ cohesion hoặc độ phức tạp.
- **Đếm dependency nhưng bỏ qua hướng phụ thuộc:** số lượng ít vẫn có thể phụ thuộc sai tầng.
- **Tạo interface cho mọi class:** abstraction không có ranh giới thay thế hoặc giá trị kiểm thử sẽ làm cấu trúc nặng hơn.
- **Tách Mapper quá sớm:** chuyển đổi vài trường đơn giản có thể không cần thêm lớp.
- **Đo coverage thay cho khả năng kiểm thử:** test có thể chạy nhiều dòng nhưng không kiểm tra hợp đồng quan trọng.
- **Đánh giá chỉ bằng cảm giác:** không có use case, baseline hoặc ví dụ thay đổi để đối chiếu.
- **Refactor nhiều thứ cùng lúc:** khó xác định thay đổi nào làm thiết kế tốt hơn hoặc gây regression.
- **Chỉ xem sơ đồ package:** dependency graph không cho biết tên phương thức, hợp đồng và luồng nghiệp vụ có dễ hiểu không.

## 17. Kết luận

Đánh giá sau cải tiến MVC cần xem đồng thời số lớp, cohesion, coupling, hướng phụ thuộc, khả năng đọc và khả năng kiểm thử. Số lớp có thể tăng khi Controller được tách khỏi nghiệp vụ và persistence; điều đó là hợp lý nếu mỗi lớp tạo ra một ranh giới có ý nghĩa và giúp thay đổi tập trung hơn.

Hãy bắt đầu bằng baseline và một use case cụ thể, lần theo dependency graph, xem lớp nào có nhiều lý do thay đổi, rồi đọc lại luồng request như một reviewer mới. Kết hợp số liệu như fan-in/fan-out, package cycle, complexity và phạm vi file phải sửa với đánh giá định tính. Một refactor tốt giúp người đọc hiểu nhanh hơn, test đúng tầng hơn và thay đổi một chính sách mà ít làm ảnh hưởng các phần không liên quan.
