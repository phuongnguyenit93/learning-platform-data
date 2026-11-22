# Tránh gắn nhãn MVC chỉ dựa trên tên thư mục hoặc lớp

Trong module **MODEL_VIEW_CONTROLLER**, việc nhận diện một ứng dụng có thực sự dùng Model–View–Controller (MVC) cần dựa trên cách các thành phần phối hợp khi xử lý tương tác. Một thư mục tên là controllers, một lớp có hậu tố Controller hoặc một package có tên model chưa đủ chứng minh kiến trúc đang áp dụng MVC. Tên gọi có thể gợi ý nơi bắt đầu tìm hiểu, nhưng bằng chứng phải đến từ trách nhiệm thực tế, luồng điều khiển, cách dữ liệu được truyền và quan hệ giữa phần tiếp nhận tương tác với phần trình bày.

Bài học thuộc chương **Mẫu giao diện liên quan**. Trọng tâm là tránh phân loại kiến trúc dựa trên tên thư mục hoặc tên lớp. Ta sẽ học cách truy vết một luồng chức năng, xác định vai trò Model, View và Controller theo hành vi, phân biệt MVC với MVP, MVVM, Page Controller và Front Controller, đồng thời phân biệt mẫu giao diện với layered architecture và Hexagonal Architecture. Các ví dụ dùng ứng dụng web Java/Spring để cho thấy một hệ thống có thể mang tên Spring MVC nhưng cấu trúc bên trong vẫn cần được đánh giá theo hành vi.

## 1. Tên gọi không phải bằng chứng kiến trúc

Tên lớp và tên package là tín hiệu hữu ích để định hướng việc đọc mã nguồn. Chúng không phải bằng chứng đầy đủ về cách hệ thống được tổ chức.

Ví dụ:

- Package tên controllers có thể chứa các lớp chỉ ánh xạ URL sang service, trong khi phần giao diện và trạng thái được tổ chức theo cách khác.
- Lớp UserController có thể là REST endpoint trả JSON, một adapter HTTP mỏng hoặc một lớp chứa cả truy vấn, quy tắc nghiệp vụ và định dạng dữ liệu.
- Package model có thể chỉ chứa JPA entity, request DTO hoặc các lớp dữ liệu thụ động.
- Thư mục views có thể chứa template, nhưng template có thể tự gọi service hoặc truy cập dữ liệu trực tiếp.
- Dự án dùng framework có chữ MVC trong tên vẫn có thể tổ chức phần nghiệp vụ theo layered architecture, Hexagonal Architecture hoặc một cấu trúc pha trộn.

Một hệ thống chỉ nên được gọi là MVC khi có thể chỉ ra các trách nhiệm tương ứng và cách chúng phối hợp trong một luồng tương tác. Không cần mỗi vai trò phải nằm trong đúng một lớp hoặc một thư mục có tên cố định. Một vai trò có thể được chia thành nhiều lớp, và một framework có thể cung cấp sẵn một phần cơ chế.

### 1.1. Phân biệt ba loại thông tin

Khi đọc dự án, hãy tách biệt:

| Loại thông tin | Ví dụ | Giá trị khi đánh giá |
|---|---|---|
| Tên gọi | UserController, model/, views/ | Gợi ý vị trí cần xem |
| Cơ chế framework | Annotation @Controller, router, template engine | Cho biết framework cung cấp khả năng gì |
| Hành vi thực tế | Nhận request, điều phối use case, truy cập model, tạo response | Bằng chứng để xác định trách nhiệm và mẫu kiến trúc |

Annotation có thể xác nhận một lớp được framework đăng ký làm controller, nhưng không cho biết lớp đó có giữ đúng trách nhiệm hay không. Một lớp có tên Controller nhưng tự thực hiện truy vấn, tính toán nghiệp vụ và tạo HTML có thể đã trở thành một khối xử lý quá nhiều trách nhiệm.

## 2. Nhận diện MVC bằng trách nhiệm và quan hệ

MVC thường được mô tả bằng ba vai trò:

- **Model:** quản lý hoặc biểu diễn trạng thái và quy tắc của miền ứng dụng mà giao diện cần làm việc.
- **View:** trình bày thông tin cho người dùng và cung cấp các điểm tương tác.
- **Controller:** tiếp nhận hành động, diễn giải input và điều phối việc thay đổi trạng thái hoặc chọn phản hồi.

Cách triển khai cụ thể thay đổi theo framework và biến thể MVC. Trong web MVC kiểu server-side, Controller thường nhận HTTP request, gọi application/service layer, chuẩn bị dữ liệu và chọn View hoặc response. Trong các biến thể MVC khác, Model có thể phát thông báo thay đổi và View đăng ký quan sát. Vì vậy, không nên áp đặt một sơ đồ gọi hàm duy nhất cho mọi hệ thống.

Điều cần tìm là các trách nhiệm có thể nhận diện được và quan hệ giữa chúng:

1. Có một thành phần nhận hành động hoặc input từ bên ngoài.
2. Có phần dữ liệu/trạng thái và quy tắc mà hành động tác động đến hoặc đọc từ đó.
3. Có phần trình bày dữ liệu hoặc kết quả cho người dùng.
4. Luồng tương tác có ranh giới đủ rõ để phân biệt tiếp nhận hành động, xử lý dữ liệu và hiển thị.

~~~mermaid
flowchart LR
    User["Người dùng"] --> View["View"]
    View -->|"Hành động / input"| Controller["Controller"]
    Controller -->|"Đọc hoặc yêu cầu thay đổi"| Model["Model"]
    Model -->|"Dữ liệu / trạng thái"| Controller
    Controller -->|"Chọn dữ liệu và phản hồi"| View
    View -->|"Hiển thị kết quả"| User
~~~

Đây là sơ đồ khái quát để nhận diện trách nhiệm, không phải hợp đồng gọi hàm bắt buộc. Một số triển khai cho phép View quan sát Model trực tiếp; một số triển khai server-side để Controller chuẩn bị Model rồi render View.

### 2.1. Model không đồng nghĩa với database hoặc JPA entity

Model không chỉ là một thư mục chứa lớp có annotation persistence. Nó có thể gồm:

- Trạng thái nghiệp vụ như đơn hàng, tài khoản, giỏ hàng.
- Quy tắc và hành vi liên quan đến trạng thái đó.
- Dịch vụ hoặc thành phần truy vấn/cập nhật dữ liệu theo cách triển khai của hệ thống.
- Các kiểu dữ liệu được dùng để trao đổi với phần trình bày.

Trong ứng dụng web nhiều tầng, nên phân biệt domain model, persistence entity, request DTO và ViewModel. Một JPA entity có thể là một phần của mô hình dữ liệu, nhưng chỉ nhìn annotation @Entity không đủ để kết luận đó là toàn bộ Model của MVC.

Model cũng không nhất thiết phải tự lưu dữ liệu. Nó có thể dựa vào repository hoặc service để lấy trạng thái từ database, cache hay hệ thống khác. Vai trò Model được xác định bởi ý nghĩa dữ liệu và quy tắc mà nó đại diện, không phải nơi lưu trữ vật lý.

### 2.2. View không đồng nghĩa với mọi file HTML

View là phần chịu trách nhiệm trình bày dữ liệu và kết quả tương tác. Nó có thể được tạo bởi:

- Template server-side như Thymeleaf, JSP hoặc FreeMarker.
- Component phía trình duyệt.
- Một lớp renderer hoặc presenter.
- JSON representation cho client, trong một kiến trúc web rộng hơn.

Tuy vậy, một file HTML tĩnh không tự động chứng minh ứng dụng dùng MVC. Cần xác định ai chuẩn bị dữ liệu cho nó, ai quyết định nội dung được hiển thị và cách hành động từ giao diện quay lại luồng xử lý.

Trong MVC server-side, template thường nhận Model/ViewModel từ Controller. Nếu template tự truy vấn database hoặc tự thực hiện quy tắc nghiệp vụ, ranh giới trình bày đã bị trộn với xử lý dữ liệu.

### 2.3. Controller không chỉ là lớp có hậu tố Controller

Controller có trách nhiệm tiếp nhận và điều phối tương tác. Nó có thể:

- Nhận HTTP request hoặc event.
- Binding và kiểm tra dữ liệu đầu vào ở mức giao thức.
- Gọi use case hoặc service phù hợp.
- Chọn View, redirect hoặc response.
- Chuyển lỗi thành phản hồi phù hợp với giao thức.

Controller không nên tự gánh toàn bộ nghiệp vụ, truy vấn phức tạp, quản lý transaction tùy tiện hoặc định dạng mọi thành phần HTML. Nếu lớp có tên Controller nhưng chứa phần lớn quy tắc nghiệp vụ và persistence, tên gọi không phản ánh đúng ranh giới trách nhiệm.

## 3. Truy vết một chức năng thay vì đọc tên package

Cách đáng tin cậy để nhận diện MVC là chọn một chức năng cụ thể rồi truy vết từ tương tác đầu vào đến phản hồi cuối cùng.

Ví dụ, chức năng tìm kiếm sách:

1. Người dùng nhập từ khóa và gửi form.
2. Request đi vào route hoặc handler.
3. Thành phần tiếp nhận request binding từ khóa và quyết định use case cần gọi.
4. Use case hoặc Model/query service đọc dữ liệu.
5. Kết quả được chuyển thành dữ liệu phù hợp cho giao diện.
6. View render danh sách, trạng thái rỗng hoặc lỗi.
7. Người dùng chọn một sách hoặc thay đổi bộ lọc, tạo tương tác tiếp theo.

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant Controller as Thành phần tiếp nhận
    participant Service as Use case / Model service
    participant Repository as Repository
    participant DB as Database
    participant View as View / Template

    User->>Browser: Gửi từ khóa tìm kiếm
    Browser->>Controller: GET /books?keyword=java
    Controller->>Controller: Binding và kiểm tra input
    Controller->>Service: search(keyword)
    Service->>Repository: Tìm sách phù hợp
    Repository->>DB: Truy vấn
    DB-->>Repository: Kết quả
    Repository-->>Service: Danh sách kết quả
    Service-->>Controller: Search result
    Controller->>View: Model/ViewModel
    View-->>Browser: HTML
    Browser-->>User: Hiển thị danh sách
~~~

Sơ đồ này giúp nhận diện các vai trò trong một biến thể web MVC. Nếu luồng thực tế khác, hãy ghi lại điều đang xảy ra thay vì ép mã nguồn vào sơ đồ mong muốn.

### 3.1. Dấu vết cần tìm trong mã nguồn

| Câu hỏi | Dấu vết có thể tìm thấy |
|---|---|
| Tương tác bắt đầu ở đâu? | Route, handler, event listener, form action |
| Ai tiếp nhận input? | Controller, action handler, router callback |
| Ai điều phối hành động? | Controller gọi service/use case hoặc xử lý command |
| Trạng thái và quy tắc ở đâu? | Domain object, model service, repository/query layer |
| Ai chuẩn bị dữ liệu cho giao diện? | Controller, presenter, view-model mapper |
| Ai render kết quả? | Template, component tree, renderer |
| Thay đổi dữ liệu quay lại UI thế nào? | Redirect, response, observable state, data binding, event |
| Lỗi được chuyển thành giao diện ở đâu? | Exception handler, form binding, error state, error boundary |

Không nhất thiết tất cả dấu vết nằm trong một file. Hãy theo dõi lời gọi, dữ liệu trả về và các dependency qua nhiều lớp.

### 3.2. Dùng một luồng thành công và một luồng lỗi

Chỉ đọc luồng thành công có thể bỏ qua nơi validation và lỗi được xử lý. Hãy theo dõi ít nhất:

- Request hợp lệ trả dữ liệu.
- Request có input sai.
- Request không tìm thấy tài nguyên hoặc không đủ quyền.
- Trạng thái rỗng.
- Một thao tác cập nhật làm thay đổi dữ liệu và giao diện.

Những luồng này giúp phát hiện liệu Controller có chỉ điều phối hay đang chứa quá nhiều logic, View có truy cập dữ liệu ngoài hợp đồng hay Model có bị phụ thuộc vào giao diện.

## 4. Ví dụ: tên lớp phù hợp nhưng hành vi không đúng ranh giới

Xét một lớp có tên BookController:

~~~java
@Controller
@RequestMapping("/books")
public class BookController {
    private final JdbcTemplate jdbc;

    @GetMapping
    public String list(
        @RequestParam String keyword,
        Model model
    ) {
        var books = jdbc.query(
            "select * from books where title like ?",
            (rs, row) -> new Book(
                rs.getLong("id"),
                rs.getString("title")
            ),
            "%" + keyword + "%"
        );

        var visibleBooks = books.stream()
            .filter(book -> book.isPublished())
            .sorted(Comparator.comparing(Book::title))
            .toList();

        model.addAttribute("books", visibleBooks);
        return "books/list";
    }
}
~~~

Lớp có annotation và tên Controller, nhưng nó đang trực tiếp làm nhiều việc: truy vấn persistence, lọc theo trạng thái, sắp xếp dữ liệu và điều phối View. Trong ví dụ còn có vấn đề kỹ thuật: truy vấn ghép wildcard cần xử lý ký tự đặc biệt theo hợp đồng tìm kiếm; việc dùng entity trực tiếp có thể khiến Controller phụ thuộc sâu vào persistence.

Không thể chỉ từ đoạn code ngắn kết luận toàn bộ ứng dụng không phải MVC. Có thể vẫn có View và Model ở nơi khác. Nhưng có thể kết luận Controller này đang mang trách nhiệm vượt quá việc tiếp nhận và điều phối request.

Một cách tổ chức rõ ràng hơn:

~~~java
@Controller
@RequestMapping("/books")
public class BookController {
    private final SearchBooksUseCase searchBooks;

    public BookController(SearchBooksUseCase searchBooks) {
        this.searchBooks = searchBooks;
    }

    @GetMapping
    public String list(
        @RequestParam(defaultValue = "") String keyword,
        Model model
    ) {
        var result = searchBooks.search(keyword);
        model.addAttribute("books", result.items());
        model.addAttribute("keyword", keyword);
        return "books/list";
    }
}
~~~

Use case hoặc service xử lý việc tìm kiếm:

~~~java
@Service
public class SearchBooksService implements SearchBooksUseCase {
    private final BookRepository books;

    public SearchBooksService(BookRepository books) {
        this.books = books;
    }

    public SearchBooksResult search(String keyword) {
        var normalized = keyword == null ? "" : keyword.trim();
        var items = books.findPublishedByTitle(normalized);
        return new SearchBooksResult(items);
    }
}

public record SearchBooksResult(List<Book> items) {}
~~~

Ví dụ thứ hai làm ranh giới rõ hơn: Controller chuyển request thành lời gọi use case, service điều phối truy vấn và View nhận dữ liệu để render. Đây là một cách triển khai; không bắt buộc mọi ứng dụng phải có đúng các interface hoặc class như ví dụ.

## 5. Annotation và tên framework nói lên điều gì?

Framework thường cung cấp convention và cơ chế để triển khai một mẫu. Nhưng tên framework không xác nhận mọi phần của ứng dụng đều tuân thủ mẫu đó.

### 5.1. Spring MVC và @Controller

Spring MVC cung cấp DispatcherServlet, handler mapping, argument resolver, Controller, Model và ViewResolver. Một lớp có @Controller cho framework biết đây là thành phần xử lý request theo cơ chế MVC của Spring.

Tuy nhiên:

- @Controller không chứng minh Controller chỉ có trách nhiệm điều phối.
- Model của Spring MVC là đối tượng mang dữ liệu để View render; nó không đồng nghĩa domain model.
- @ResponseBody hoặc @RestController có thể trả JSON thay vì tên View template.
- Một ứng dụng Spring MVC vẫn có thể chứa service, repository, domain layer và adapter theo các kiểu kiến trúc khác.
- Cần xem cách Controller gọi nghiệp vụ, dữ liệu được chuẩn bị ở đâu và response được tạo thế nào.

Spring MVC là framework web hỗ trợ mô hình xử lý request MVC. Một ứng dụng sử dụng framework này có thể đồng thời áp dụng layered architecture hoặc Hexagonal Architecture.

### 5.2. Package controller/model/view không đủ

Cấu trúc sau chỉ cho biết cách tác giả đặt tên:

~~~text
src/main/java/
  controller/
  model/
  service/
  repository/
src/main/resources/
  templates/
~~~

Muốn xác nhận trách nhiệm cần xem dependency và luồng gọi:

- Controller có gọi repository trực tiếp không?
- Service có chứa quy tắc nghiệp vụ hay chỉ chuyển tiếp?
- Model có phải entity persistence, domain object hay ViewModel?
- Template có tự gọi service hoặc nhúng logic truy vấn không?
- Có nhiều loại Controller cho HTML, REST và message không?

Tên thư mục có thể hữu ích để định hướng nhưng không thay cho phân tích.

## 6. Phân biệt MVC với MVP và MVVM

MVC, MVP và MVVM đều tìm cách tách phần giao diện khỏi dữ liệu và logic điều khiển. Chúng có thể trông giống nhau trong một số dự án vì framework và cách tổ chức thực tế không đồng nhất.

| Tiêu chí | MVC | MVP | MVVM |
|---|---|---|---|
| Thành phần điều phối chính | Controller | Presenter | ViewModel |
| Vai trò View | Trình bày, phát sinh tương tác | Thường là view thụ động, gọi Presenter | Bind dữ liệu và command với ViewModel |
| Cách cập nhật UI | Tùy biến thể; Controller/Model/View phối hợp | Presenter cập nhật qua View interface | Data binding hoặc observer/reactive state |
| View phụ thuộc vào | Có thể biết Model hoặc nhận dữ liệu từ Controller | Thường phụ thuộc interface View | Thường bind với ViewModel |
| Kiểm thử | Kiểm tra luồng Controller/Model/View | Presenter dễ test qua mock View | ViewModel dễ test độc lập với UI framework |
| Dấu hiệu nhận diện | Có Controller tiếp nhận/điều phối và View trình bày Model | Presenter nắm logic trình bày và gọi View interface | ViewModel công bố state/command cho binding |

Không có một sơ đồ duy nhất được mọi framework gọi là MVC, MVP hoặc MVVM. Hãy dùng các đặc điểm này như dấu hiệu để so sánh, rồi xác nhận qua hành vi thực tế.

### 6.1. MVP: Presenter điều khiển View qua interface

Trong MVP, View thường là một interface hoặc thành phần thụ động. Presenter nhận tương tác từ View, gọi Model/service và chủ động yêu cầu View cập nhật.

~~~mermaid
flowchart LR
    User["Người dùng"] --> View["View"]
    View -->|"Event / callback"| Presenter["Presenter"]
    Presenter --> Model["Model / Service"]
    Model --> Presenter
    Presenter -->|"Gọi phương thức View"| View
~~~

Dấu hiệu thường gặp:

- Presenter giữ logic trình bày.
- Presenter có dependency đến interface View.
- View chuyển event cho Presenter.
- Presenter gọi các phương thức như showBooks, showError hoặc setLoading.

Nếu một lớp có tên BookController nhưng thực tế chỉ hoạt động như Presenter, nhận event từ View và gọi interface View để cập nhật, cần đánh giá hành vi trước khi gọi nó là Controller trong MVC.

### 6.2. MVVM: View bind với ViewModel

Trong MVVM, ViewModel công bố state và command; View liên kết dữ liệu với chúng. Khi ViewModel đổi state, UI có thể cập nhật qua data binding hoặc cơ chế reactive.

~~~mermaid
flowchart LR
    User["Người dùng"] --> View["View"]
    View <-->|"Data binding / commands"| VM["ViewModel"]
    VM --> Model["Model / Services"]
    Model --> VM
~~~

Dấu hiệu thường gặp:

- ViewModel không phụ thuộc trực tiếp vào widget hoặc template cụ thể.
- View bind vào property/state và command.
- Thay đổi state được framework quan sát để cập nhật UI.
- Logic trình bày thường nằm trong ViewModel thay vì Controller.

Một lớp có tên UserModel có thể thực chất là ViewModel nếu nó chứa state hiển thị, command và logic trình bày. Tên Model không đủ để phân loại nó là domain model hoặc MVC Model.

### 6.3. Có thể có kiến trúc pha trộn

Một ứng dụng có thể dùng MVC ở server và MVVM ở client:

- Spring MVC nhận request và render trang ban đầu.
- JavaScript phía trình duyệt dùng ViewModel hoặc store để quản lý state tương tác.
- REST endpoint trả JSON cho các lần cập nhật sau.

Không nên ép toàn bộ hệ thống vào một nhãn duy nhất nếu các lớp giao diện khác nhau dùng những cách tổ chức khác nhau. Có thể mô tả rõ: server-side web flow dùng MVC; một widget phía client dùng mô hình reactive/MVVM-like.

## 7. Page Controller và Front Controller không đồng nghĩa với MVC

Hai tên này thường xuất hiện cùng các hệ thống web MVC nhưng chúng mô tả trách nhiệm khác.

### 7.1. Page Controller

Page Controller là cách tổ chức trong đó một controller hoặc handler xử lý request cho một trang hay nhóm trang cụ thể. Nó có thể là một biến thể hoặc cách triển khai phần Controller trong MVC.

Dấu hiệu:

- Handler gắn với một trang hoặc endpoint cụ thể.
- Nó điều phối việc lấy dữ liệu và chọn template.
- Mỗi trang có thể có controller riêng.

Page Controller không tự xác định Model và View được tổ chức thế nào. Một hệ thống dùng Page Controller vẫn có thể là MVC nếu có các trách nhiệm tương ứng.

### 7.2. Front Controller

Front Controller là một điểm vào chung tiếp nhận request và phân phối đến handler phù hợp. Nó thường xử lý routing, middleware, xác thực, logging hoặc các bước chung.

~~~mermaid
flowchart TD
    Request["HTTP Request"] --> Front["Front Controller / Dispatcher"]
    Front --> Route{"Chọn handler"}
    Route --> A["Books Controller"]
    Route --> B["Orders Controller"]
    Route --> C["Account Controller"]
    A --> Response["View / Response"]
    B --> Response
    C --> Response
~~~

Front Controller có thể tồn tại cùng MVC. Ví dụ, DispatcherServlet của Spring nhận request rồi định tuyến đến handler/controller. Nó không thay thế toàn bộ vai trò Model, View và Controller; nó là cơ chế điều phối đầu vào ở cấp framework.

### 7.3. Vì sao tên Controller dễ gây nhầm?

Trong hệ thống có Front Controller, Page Controller, REST Controller và Presenter, nhiều lớp đều có thể chứa từ Controller. Chúng không nhất thiết có cùng vai trò.

Hãy hỏi:

- Lớp này có phải điểm vào chung hay handler cho một chức năng?
- Nó tiếp nhận giao thức nào?
- Nó gọi thành phần nào để thực hiện nghiệp vụ?
- Nó tạo View hay trả representation?
- Nó có giữ state và logic trình bày không?

Câu trả lời mới cho biết vai trò thực tế.

## 8. MVC không đồng nghĩa với layered architecture

Layered Architecture tổ chức ứng dụng theo các lớp trách nhiệm hoặc kỹ thuật, ví dụ presentation, application, domain và infrastructure. MVC tập trung vào cách tiếp nhận tương tác, quản lý Model và trình bày View.

Hai mô hình có thể kết hợp:

~~~mermaid
flowchart TB
    subgraph Presentation["Presentation Layer"]
      C["MVC Controller"]
      V["View / Template"]
    end
    subgraph Application["Application Layer"]
      S["Use Case / Service"]
    end
    subgraph Domain["Domain Layer"]
      M["Domain Model"]
    end
    subgraph Infrastructure["Infrastructure Layer"]
      R["Repository Adapter"]
      DB["Database"]
    end
    C --> S
    S --> M
    S --> R
    R --> DB
    C --> V
~~~

Trong sơ đồ này, MVC xuất hiện chủ yếu ở presentation layer; các lớp khác là cách tổ chức phần ứng dụng và hạ tầng. Không nên nói rằng layered architecture là một loại MVC hoặc MVC thay thế cho layered architecture.

Một dự án có thể có package controllers, services, repositories và entities. Đó là dấu hiệu của phân lớp theo kỹ thuật; để xác định MVC, vẫn cần truy vết quan hệ giữa Controller, Model và View.

## 9. MVC và Hexagonal Architecture nằm trên những trục khác nhau

Hexagonal Architecture tập trung vào lõi ứng dụng, port, adapter và hướng phụ thuộc. MVC tập trung vào tổ chức tương tác và trình bày. Một Controller web có thể là inbound adapter của Hexagonal Architecture đồng thời là Controller trong luồng MVC.

| Câu hỏi | MVC | Hexagonal Architecture |
|---|---|---|
| Ai nhận hành động từ người dùng? | Controller | Inbound adapter gọi inbound port |
| Ai trình bày kết quả? | View | Adapter trình bày/HTTP |
| Nghiệp vụ ở đâu? | Trong Model hoặc các thành phần nghiệp vụ liên quan tùy biến thể | Trong application/domain core |
| Database được truy cập thế nào? | Có thể qua repository/service | Qua outbound port và adapter |
| Trọng tâm phụ thuộc | Tách tiếp nhận, dữ liệu và trình bày | Adapter phụ thuộc vào abstraction của lõi |

Không thể kết luận một ứng dụng có Hexagonal Architecture chỉ vì có interface repository. Cũng không thể kết luận nó là MVC chỉ vì có lớp Controller. Cả hai cần được xác nhận qua ranh giới và hướng phụ thuộc thực tế.

## 10. Quy trình đánh giá một codebase

Khi được giao xác định một ứng dụng có dùng MVC hay không, hãy áp dụng quy trình có thể lặp lại.

### Bước 1: Chọn một use case có tương tác rõ

Chọn một chức năng có input và output quan sát được, ví dụ:

- Tìm kiếm sách.
- Cập nhật hồ sơ.
- Tạo đơn hàng.
- Đăng nhập.
- Xem chi tiết giao dịch.

Không bắt đầu bằng việc đếm số package có tên model hoặc controller.

### Bước 2: Tìm entry point

Xác định request, route, event hoặc callback đầu tiên. Ghi lại framework dispatch đến lớp nào và input được binding ở đâu.

### Bước 3: Theo dõi dữ liệu đi vào

Xác định request DTO, form object, command hoặc query được tạo. Kiểm tra ai xác thực input ở mức giao thức và ai áp dụng quy tắc nghiệp vụ.

### Bước 4: Theo dõi xử lý trạng thái

Tìm service, domain object, repository hoặc state store được gọi. Ghi rõ thành phần nào chứa quy tắc, thành phần nào chỉ đọc/ghi dữ liệu và thành phần nào là chi tiết persistence.

### Bước 5: Theo dõi dữ liệu đi ra

Xác định Controller nhận kết quả gì, có tạo ViewModel không, template hoặc component nào render. Kiểm tra View có truy cập trực tiếp service hoặc repository không.

### Bước 6: Theo dõi tương tác tiếp theo

Khi người dùng nhấn nút, đổi filter hoặc gửi form, request/event mới đi qua thành phần nào? State được giữ ở server, URL, session hay client? Việc cập nhật có tuân theo ranh giới tương tự không?

### Bước 7: So sánh hành vi với các mẫu gần giống

Nếu View gọi Presenter và Presenter điều khiển View qua interface, cân nhắc MVP. Nếu View bind vào state/command của ViewModel, cân nhắc MVVM. Nếu một handler chung chỉ dispatch đến các page controller, đó là dấu hiệu Front Controller kết hợp với handler cụ thể.

### Bước 8: Ghi kết luận và bằng chứng

Không chỉ ghi “dùng MVC”. Hãy mô tả:

- Phạm vi nào dùng MVC.
- Thành phần nào đóng vai trò Controller, Model và View.
- Luồng tương tác nào đã truy vết.
- Có pha trộn với pattern nào khác không.
- Bằng chứng nào chưa đủ để kết luận.

## 11. Ma trận bằng chứng để phân loại

Có thể dùng bảng sau khi review một module:

| Tiêu chí | Bằng chứng mạnh | Bằng chứng yếu hoặc không đủ |
|---|---|---|
| Controller | Nhận input, điều phối use case, chọn View/response | Chỉ có tên lớp kết thúc bằng Controller |
| Model | Đại diện state/quy tắc được luồng tương tác sử dụng | Chỉ có package model hoặc entity JPA |
| View | Render dữ liệu được cung cấp và phát sinh tương tác | Chỉ có thư mục templates hoặc file HTML |
| Quan hệ | Có thể truy vết hành động từ View qua Controller đến xử lý Model rồi quay về kết quả | Các lớp tồn tại nhưng không có quan hệ rõ |
| Phân tách | Trách nhiệm tiếp nhận, xử lý dữ liệu và trình bày có ranh giới nhận diện | Một lớp làm mọi việc, template tự truy cập dữ liệu |
| Biến thể | Luồng phù hợp với một biến thể MVC cụ thể và được mô tả rõ | Chỉ dựa vào tên framework hoặc tài liệu marketing |

Không phải mọi dự án đều có cấu trúc hoàn hảo. Có thể một ứng dụng đang áp dụng MVC nhưng có vi phạm ranh giới. Khi đó, mô tả chính xác hơn là “ứng dụng tổ chức theo MVC, nhưng Controller đang chứa truy vấn và logic nghiệp vụ” thay vì phủ nhận toàn bộ mẫu.

### 11.1. Mức độ tin cậy của kết luận

Có thể ghi kết luận theo ba mức:

- **Đủ bằng chứng:** đã truy vết được luồng input, điều phối, Model/state và View/response ở chức năng đại diện.
- **Bằng chứng một phần:** thấy một số vai trò nhưng chưa xác định được cách chúng phối hợp hoặc chỉ khảo sát một phần hệ thống.
- **Chưa đủ bằng chứng:** chỉ có tên package, annotation hoặc convention nhưng chưa truy vết được luồng thực thi.

Cách ghi này giúp reviewer khác biết điều gì đã được xác minh và điều gì chỉ là giả thuyết.

## 12. Dấu hiệu phân loại sai thường gặp

| Nhận định vội vàng | Vì sao chưa đủ | Cách xác minh |
|---|---|---|
| Có package controller nên là MVC | Package có thể chỉ là adapter HTTP | Truy vết Controller đến Model và View |
| Có JPA entity nên entity là MVC Model | Entity mô tả persistence mapping | Xác định state/quy tắc mà giao diện sử dụng |
| Có thư mục views nên là MVC | Template có thể không tham gia luồng controller-model | Xác định ai tạo dữ liệu và chọn template |
| Dùng Spring MVC nên mọi module đều theo MVC | Framework có thể chỉ được dùng cho HTTP/REST | Đánh giá từng luồng và từng module |
| REST Controller trả JSON chứng minh có View cổ điển | JSON serialization không giống template View truyền thống | Mô tả rõ response adapter và representation |
| Có class Presenter nhưng tên Controller | Vai trò có thể là MVP | Kiểm tra dependency đến View interface và hành vi cập nhật |
| Có ViewModel nên là MVVM | ViewModel cũng có thể chỉ là DTO cho template | Kiểm tra data binding, command và observer |
| Có DispatcherServlet nên DispatcherServlet là MVC Controller duy nhất | Nó là Front Controller/dispatcher cấp framework | Truy vết handler cụ thể và trách nhiệm tiếp theo |
| Service gọi repository nên là Model | Service có thể chỉ là application/use case layer | Phân biệt domain behavior, application orchestration và persistence |
| Có MVC trong tên project nên kiến trúc đúng MVC | Tên project không phản ánh mọi luồng | Kiểm tra code và runtime behavior |

## 13. Cải thiện cách đặt tên sau khi đã xác định vai trò

Tên tốt giúp người đọc hiểu trách nhiệm nhưng chỉ có giá trị khi phù hợp với hành vi. Sau khi phân tích, có thể đổi tên để giảm nhầm lẫn:

- Dùng BookPageController cho handler trang sách nếu muốn phân biệt với REST controller.
- Dùng BookRestController hoặc BookApiController cho adapter API.
- Dùng SearchBooksUseCase hoặc BookQueryService cho hành động ứng dụng.
- Dùng BookJpaEntity cho persistence entity.
- Dùng BookListViewModel cho dữ liệu phục vụ template.
- Dùng BookPresenter cho lớp thực sự giữ vai trò Presenter trong MVP.
- Dùng BookViewModel cho lớp state/command được View bind trong MVVM.

Không cần thêm hậu tố dài cho mọi lớp. Tên nên phản ánh trách nhiệm quan trọng nhất và tránh khiến người đọc suy ra sai pattern. Nếu một lớp có nhiều trách nhiệm, giải pháp có thể là tách lớp thay vì chỉ đổi tên.

### 13.1. Package nên phản ánh ranh giới có ý nghĩa

Một cấu trúc theo feature có thể như sau:

~~~text
books/
  web/
    BookPageController.java
    BookRestController.java
    BookListViewModel.java
  application/
    SearchBooksUseCase.java
    SearchBooksService.java
  domain/
    Book.java
    BookPublicationPolicy.java
  persistence/
    BookJpaEntity.java
    BookJpaRepository.java
~~~

Cấu trúc này là một gợi ý. Một dự án có thể đặt template ở resources/templates/books và adapter ở package khác. Không có tên folder nào tự chứng minh MVC; package chỉ giúp thể hiện ranh giới mà nhóm đã xác định.

## 14. Kiểm thử để xác nhận trách nhiệm

Test cũng là bằng chứng về ranh giới, nhưng tên test không đủ. Hãy xem test cô lập thành phần nào và kiểm tra hợp đồng gì.

| Loại test | Bằng chứng có thể cung cấp |
|---|---|
| Controller test | Request được binding, use case được gọi, View/response được chọn đúng |
| Model/domain test | Quy tắc và chuyển trạng thái hoạt động độc lập |
| View/template test | Dữ liệu được render đúng, escaping và cấu trúc giao diện phù hợp |
| Presenter test | Event đầu vào tạo lời gọi đúng đến View interface |
| ViewModel test | State và command hoạt động độc lập với framework UI |
| Integration test | Các adapter được nối đúng và luồng request hoạt động |
| End-to-end test | Người dùng hoàn thành tác vụ qua giao diện thực tế |

Ví dụ Controller test trong Spring:

~~~java
@WebMvcTest(BookController.class)
class BookControllerTest {
    @Autowired
    MockMvc mockMvc;

    @MockBean
    SearchBooksUseCase searchBooks;

    @Test
    void rendersBookList() throws Exception {
        given(searchBooks.search("java"))
            .willReturn(new SearchBooksResult(List.of()));

        mockMvc.perform(get("/books").param("keyword", "java"))
            .andExpect(status().isOk())
            .andExpect(view().name("books/list"))
            .andExpect(model().attributeExists("books"));
    }
}
~~~

Đây là ví dụ rút gọn; kiểu kết quả và cấu hình mock cần khớp với ứng dụng cụ thể. Test cho thấy Controller đóng vai trò adapter web: nó nhận request, gọi use case và chọn View. Nó không tự chứng minh toàn bộ ứng dụng tuân thủ MVC.

### 14.1. Test có thể phơi bày ranh giới bị phá vỡ

Nếu Controller test cần khởi động database thật chỉ để kiểm tra tên View, có thể Controller đang phụ thuộc quá sâu vào hạ tầng. Nếu template test cần gọi repository, View có thể đang tự truy cập dữ liệu. Nếu domain test phải dựng HttpServletRequest, domain có thể phụ thuộc giao thức web.

Đây là tín hiệu để xem lại dependency, không phải quy tắc tuyệt đối. Một số integration test cần hạ tầng thật để xác nhận wiring; điều quan trọng là unit test của từng trách nhiệm vẫn có thể tập trung vào hợp đồng của nó.

## 15. Những trường hợp khó phân loại

### 15.1. Một lớp vừa nhận request vừa chứa nghiệp vụ

Ứng dụng nhỏ có thể đặt validation và một phần logic trong Controller. Điều đó không tự động làm mất mọi đặc điểm MVC, nhưng cho thấy ranh giới đang mờ. Hãy ghi nhận mức độ trách nhiệm thực tế thay vì cố gắn nhãn “MVC chuẩn”.

### 15.2. View cập nhật Model trực tiếp

Một số biến thể MVC cho phép View hoặc thành phần UI tương tác trực tiếp với Model, đặc biệt trong ứng dụng desktop hoặc framework có observer. Điều đó không tự động biến ứng dụng thành MVP hoặc MVVM. Cần xem ai điều phối hành động và cách View nhận cập nhật.

### 15.3. Không có template View riêng

REST API có thể trả JSON và để client render giao diện. Trong server, Controller vẫn có thể đóng vai trò adapter nhận HTTP và gọi Model/use case, nhưng không có template View truyền thống. Hãy mô tả nó là kiến trúc web/API theo cách tổ chức hiện tại, thay vì tuyên bố toàn bộ luồng là MVC cổ điển chỉ vì dùng Spring MVC.

### 15.4. Client-side SPA

Một SPA có thể có router, component, store, service và view. Router không tự động là Controller; store không tự động là Model; component không tự động là View của MVC. Cần kiểm tra state flow, event handling, data binding và nơi giữ logic trình bày. Nhiều SPA thực tế gần MVVM hoặc unidirectional data flow hơn MVC cổ điển.

### 15.5. Framework sinh mã hoặc convention

Scaffold có thể sinh Controller, Model và View theo tên chuẩn. Đây là điểm khởi đầu, không bảo đảm mã được mở rộng vẫn giữ ranh giới. Khi dự án phát triển, cần kiểm tra những custom hook, callback, service và template mới có làm trách nhiệm chồng lấn hay không.

## 16. Checklist đánh giá trước khi gắn nhãn MVC

- [ ] Đã chọn một hoặc nhiều use case đại diện thay vì chỉ nhìn cấu trúc folder.
- [ ] Đã tìm được entry point và xác định ai tiếp nhận input.
- [ ] Đã truy vết thành phần điều phối hành động.
- [ ] Đã xác định state, dữ liệu và quy tắc mà luồng tương tác sử dụng.
- [ ] Đã tìm được View hoặc cơ chế trình bày response.
- [ ] Đã xác định cách dữ liệu được chuyển từ xử lý sang trình bày.
- [ ] Đã kiểm tra luồng lỗi, trạng thái rỗng và thao tác cập nhật.
- [ ] Đã phân biệt Controller với Front Controller, Page Controller và Presenter.
- [ ] Đã phân biệt Model với JPA entity, DTO và ViewModel.
- [ ] Đã kiểm tra View có truy cập trực tiếp service/repository không.
- [ ] Đã xác định hệ thống dùng MVC thuần, biến thể MVC hay kết hợp pattern khác.
- [ ] Kết luận có bằng chứng và nêu rõ phạm vi/mức độ tin cậy.

Không nên biến checklist thành điều kiện cứng rằng mọi ứng dụng phải có đúng ba lớp với đúng ba tên. Mục tiêu là xác định trách nhiệm và quan hệ, sau đó đánh giá mức độ tách biệt có phù hợp với độ phức tạp của ứng dụng hay không.

## 17. Cách viết kết luận kiến trúc có thể kiểm chứng

Một kết luận tốt nên mô tả bằng chứng thay vì chỉ dán nhãn.

Ví dụ kết luận chưa đủ:

> Dự án dùng MVC vì có các package controller, model và view.

Ví dụ kết luận có thể kiểm chứng:

> Luồng tìm kiếm sách dùng Spring MVC ở tầng web. BookController nhận query parameter, gọi SearchBooksUseCase và đưa kết quả vào Model để template books/list render HTML. Quy tắc tìm kiếm nằm trong application service và dữ liệu được truy vấn qua repository. Vì vậy, luồng trang sách có cách tổ chức MVC ở tầng trình bày; phần nghiệp vụ bên trong còn được phân lớp riêng.

Nếu có pha trộn:

> Trang quản lý đơn hàng dùng Controller và View theo MVC ở server. Một số thao tác cập nhật trên client dùng component state và data binding gần với MVVM. Hai cách tổ chức cùng tồn tại ở các phạm vi khác nhau.

Nếu chưa đủ bằng chứng:

> Codebase có package controller và model, nhưng chưa truy vết được quan hệ giữa các lớp này với View trong luồng thực thi. Chưa đủ cơ sở để kết luận toàn bộ module áp dụng MVC.

Cách viết này giúp nhóm khác review, xác minh và cập nhật kết luận khi hệ thống thay đổi.

## 18. Những lỗi thường gặp khi đánh giá kiến trúc

| Lỗi đánh giá | Tác hại | Cách khắc phục |
|---|---|---|
| Dựa vào hậu tố Controller | Gán sai vai trò cho Presenter hoặc handler khác | Xem input, dependency và output |
| Đồng nhất Model với entity database | Bỏ qua domain behavior và state khác | Xác định ý nghĩa dữ liệu và quy tắc |
| Đồng nhất View với file HTML | Bỏ qua renderer/component và data flow | Truy vết nơi dữ liệu được trình bày |
| Dựa vào tên framework | Kết luận quá rộng cho toàn bộ hệ thống | Đánh giá theo module/use case |
| Xem Front Controller là toàn bộ MVC | Nhầm dispatcher với controller nghiệp vụ | Theo dõi handler sau dispatcher |
| Gọi mọi ViewModel là MVVM | Nhầm DTO trình bày với state/command binding | Kiểm tra data binding và command |
| Coi mọi service là Model | Trộn application orchestration với domain model | Phân biệt use case, domain và persistence |
| Bỏ qua luồng lỗi | Không thấy ranh giới validation/error | Truy vết cả request lỗi và thành công |
| Áp đặt một biến thể MVC cho mọi framework | Đánh giá sai các triển khai hợp lệ | Nêu rõ biến thể và phạm vi |
| Chỉ đổi tên mà không tách trách nhiệm | Tên đẹp nhưng cấu trúc vẫn rối | Refactor dependency và behavior |

## 19. Tóm lược cách nhận diện

Để xác định một phần của ứng dụng có tổ chức theo MVC hay không, hãy bắt đầu từ một tương tác thực tế. Tìm thành phần nhận input, theo dõi nơi hành động được điều phối, xác định state và quy tắc được sử dụng, rồi tìm nơi kết quả được trình bày. Sau đó so sánh các quan hệ này với MVC và những mẫu gần giống như MVP, MVVM, Page Controller và Front Controller.

Tên package, tên lớp và annotation chỉ là manh mối. Chúng có thể được đặt đúng, đặt sai hoặc phản ánh convention của framework. Kết luận kiến trúc cần dựa trên luồng thực thi, trách nhiệm và hướng phụ thuộc. Khi mô tả cả phạm vi áp dụng lẫn bằng chứng, nhóm phát triển tránh được việc gắn nhãn sai và có cơ sở tốt hơn để cải thiện thiết kế.
