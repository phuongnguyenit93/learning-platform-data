# Ánh xạ thao tác hoặc yêu cầu tới hành động

Trong module **MODEL_VIEW_CONTROLLER**, Controller là điểm tiếp nhận tương tác từ người dùng hoặc request từ một client, sau đó chuyển yêu cầu đó thành hành động phù hợp của ứng dụng. Trong web MVC, việc ánh xạ này thường dựa trên URL, HTTP method, tham số, kiểu nội dung và các điều kiện của endpoint. Một ánh xạ tốt giúp request đi đến đúng action, dữ liệu được diễn giải theo hợp đồng rõ ràng và kết quả được trả về nhất quán.

Bài học thuộc chương **Controller**. Trọng tâm là cách xác định action cho một thao tác, cách route kết nối request với phương thức Controller, cách lấy dữ liệu từ path/query/body/form, và cách xử lý trường hợp request không khớp hoặc không hợp lệ. Ta cũng sẽ xem xét bảo mật, lỗi ánh xạ và cách kiểm thử để bảo đảm mỗi thao tác đến đúng nơi.

## 1. Từ thao tác của người dùng đến action

Một thao tác trên giao diện thường bắt đầu bằng một sự kiện: người dùng mở trang chi tiết, tìm kiếm, gửi biểu mẫu, chọn một bộ lọc hoặc yêu cầu thay đổi trạng thái. View chuyển thao tác đó thành một request hoặc lời gọi phù hợp với giao thức mà ứng dụng sử dụng.

Controller tiếp nhận request và chọn hành động cần thực hiện. Với web MVC, một action thường là phương thức công khai của Controller được framework đăng ký thông qua cấu hình route hoặc annotation. Action nhận dữ liệu đầu vào, gọi dịch vụ ứng dụng và trả về một kết quả như View, redirect hoặc HTTP response.

Ví dụ trong ứng dụng quản lý sách:

| Thao tác | Request minh họa | Action được chọn | Kết quả mong đợi |
|---|---|---|---|
| Xem danh sách | GET /books | list hoặc search | Trang danh sách hoặc JSON |
| Xem một cuốn sách | GET /books/42 | detail | Trang chi tiết hoặc JSON |
| Tìm theo từ khóa | GET /books?q=java | search | Danh sách phù hợp |
| Mở biểu mẫu tạo | GET /books/new | newForm | Biểu mẫu rỗng |
| Gửi biểu mẫu tạo | POST /books | create | Tạo sách, sau đó redirect hoặc trả 201 |
| Đổi tên sách | PATCH /books/42 | update | Cập nhật và trả kết quả |
| Xóa sách | DELETE /books/42 | delete | Xóa hoặc trả kết quả phù hợp |
| Phát hành sách | POST /books/42/publish | publish | Thực hiện chuyển trạng thái |

Một thao tác nghiệp vụ có thể có nhiều request khác nhau. Ví dụ, “tạo sách” gồm request GET để mở form và request POST để gửi dữ liệu. Chúng phục vụ cùng một mục tiêu của người dùng nhưng cần hai action vì vai trò và dữ liệu đầu vào khác nhau.

Cũng cần phân biệt action với quy tắc nghiệp vụ. Action là điểm tiếp nhận và điều phối; việc một cuốn sách có được phép phát hành hay không phải do Model hoặc ca sử dụng quyết định. Controller không nên biến route thành nơi chứa toàn bộ chính sách.

## 2. Các bước để ánh xạ một request

Một request web thường đi qua nhiều bước trước khi phương thức action được gọi. Tùy framework, tên và thứ tự chính xác có thể khác nhau, nhưng luồng khái niệm phổ biến là:

1. Client gửi request gồm method, URL, header và có thể có body.
2. Server hoặc middleware xử lý các bước chung như giải mã request, logging, CORS, xác thực và giới hạn lưu lượng.
3. Router so khớp path và HTTP method với các route đã đăng ký.
4. Framework kiểm tra thêm các điều kiện của endpoint như route constraint, content type hoặc media type được hỗ trợ.
5. Model binding chuyển giá trị từ route, query, header hoặc body thành tham số của action.
6. Validation kiểm tra cấu trúc và ràng buộc đầu vào ở biên.
7. Framework gọi action nếu request vượt qua các bước cần thiết.
8. Action gọi dịch vụ ứng dụng, chuyển kết quả thành View hoặc HTTP response.
9. Middleware và server hoàn tất response gửi về client.

~~~mermaid
flowchart TD
    A["Client gửi request"] --> B["Middleware / bộ lọc chung"]
    B --> C["Router so khớp path"]
    C --> D{"HTTP method phù hợp?"}
    D -- "Không" --> E["405 Method Not Allowed hoặc 404 theo cấu hình"]
    D -- "Có" --> F["Kiểm tra điều kiện endpoint"]
    F --> G["Model binding"]
    G --> H["Validation đầu vào"]
    H --> I{"Hợp lệ?"}
    I -- "Không" --> J["Trả lỗi validation"]
    I -- "Có" --> K["Gọi Controller action"]
    K --> L["Dịch vụ ứng dụng / Model"]
    L --> M["View, redirect hoặc HTTP response"]
    M --> N["Client nhận response"]
~~~

Sơ đồ mô tả trình tự khái niệm. Một số framework thực hiện authorization filter trước model binding; framework khác có thể tổ chức middleware, filter và exception handler theo pipeline riêng. Khi cần hiểu chính xác thứ tự, hãy dựa vào pipeline của framework đang sử dụng.

### 2.1. Router xác định endpoint

Router so sánh request với các mẫu route. Một route thường gồm:

- **Path template:** mẫu đường dẫn, ví dụ /books/{bookId}.
- **HTTP method:** GET, POST, PUT, PATCH hoặc DELETE.
- **Route values:** các giá trị được trích từ path, ví dụ bookId.
- **Constraints:** điều kiện cho tham số route, ví dụ bookId phải là UUID hoặc số nguyên.
- **Metadata:** tên route, chính sách phân quyền, phiên bản API hoặc các điều kiện khác tùy framework.

Một route có thể được khai báo theo quy ước tập trung hoặc đặt trực tiếp trên action. Route theo quy ước thường hữu ích khi ứng dụng có cấu trúc URL đồng nhất. Attribute/annotation routing hữu ích khi mỗi endpoint cần thể hiện rõ path và method ngay tại phương thức.

### 2.2. HTTP method góp phần chọn action

URL một mình chưa đủ để xác định hành động. Cùng một path có thể đại diện cho các thao tác khác nhau tùy HTTP method:

| Method | Ý nghĩa thường dùng | Ví dụ |
|---|---|---|
| GET | Đọc tài nguyên hoặc truy vấn | GET /books/42 |
| POST | Tạo tài nguyên hoặc thực hiện một thao tác | POST /books |
| PUT | Thay thế toàn bộ biểu diễn tài nguyên theo hợp đồng | PUT /books/42 |
| PATCH | Thay đổi một phần tài nguyên | PATCH /books/42 |
| DELETE | Yêu cầu xóa tài nguyên | DELETE /books/42 |

GET được thiết kế để đọc và phải an toàn theo ngữ nghĩa HTTP: chỉ gọi GET không được tạo ra thay đổi nghiệp vụ ngoài ý muốn. GET cũng nên có tính idempotent, nghĩa là gửi lặp lại cùng request không làm tăng thêm hiệu ứng nghiệp vụ.

PUT và DELETE cũng được định nghĩa là idempotent theo ngữ nghĩa HTTP. POST thường không idempotent; nếu client có thể gửi lại do timeout hoặc retry, ứng dụng cần cân nhắc khóa idempotency hoặc cơ chế chống tạo trùng. PATCH có thể idempotent hoặc không tùy cách thiết kế thao tác.

Không nên dùng GET cho thao tác xóa, thanh toán hoặc chuyển trạng thái chỉ vì nó thuận tiện để tạo liên kết. Trình duyệt, crawler, proxy hoặc công cụ prefetch có thể tự động gửi GET.

### 2.3. Điều kiện bổ sung của endpoint

Ngoài path và method, framework có thể phân biệt endpoint dựa trên:

- Content-Type của request, chẳng hạn application/json hoặc application/x-www-form-urlencoded.
- Accept header, thể hiện kiểu response client muốn nhận.
- Phiên bản API hoặc header tùy chỉnh.
- Route constraint, chẳng hạn chỉ nhận UUID.
- Chính sách xác thực và phân quyền.

Ví dụ, hai action cùng nhận POST /books có thể không hợp lệ nếu không có điều kiện phân biệt. Nếu một action chỉ nhận JSON và action kia chỉ nhận form URL encoded, framework có thể dùng consumes hoặc điều kiện content type để phân biệt. Tuy nhiên, nên giữ route dễ đoán và tránh nhiều endpoint cạnh tranh mà client khó hiểu.

## 3. Path, query, body và form cung cấp dữ liệu khác nhau

Sau khi route chọn được action, framework cần chuyển dữ liệu request vào các tham số của phương thức. Đây là quá trình **model binding**. Nguồn dữ liệu phổ biến gồm path, query string, header, body và form.

| Nguồn | Dùng để biểu diễn | Ví dụ |
|---|---|---|
| Path variable | Định danh hoặc phân cấp tài nguyên | /books/42 |
| Query parameter | Bộ lọc, tìm kiếm, sắp xếp, phân trang | /books?q=java&page=2 |
| Header | Metadata của giao thức hoặc client | If-Match, Accept-Language |
| Request body | Dữ liệu tạo/cập nhật theo hợp đồng | JSON chứa title và author |
| Form field | Dữ liệu người dùng gửi từ biểu mẫu HTML | title=Clean Code |
| Cookie/session | Thông tin phiên theo cơ chế đã cấu hình | Cookie định danh session |

### 3.1. Path variable định danh tài nguyên

Path thường mang định danh hoặc quan hệ cha-con. Ví dụ:

- GET /books/42: đọc sách có ID 42.
- GET /members/7/loans: đọc các khoản mượn của thành viên 7.
- DELETE /books/42: yêu cầu xóa sách 42.

Tham số path thường là bắt buộc. Nếu giá trị không đúng định dạng, request có thể không khớp route constraint hoặc model binding thất bại. Nếu đúng định dạng nhưng không có tài nguyên tương ứng, action hoặc tầng ứng dụng trả kết quả không tìm thấy.

Không nên lấy ID từ path rồi mặc định rằng người dùng có quyền truy cập tài nguyên đó. Định danh chỉ xác định đối tượng; authorization phải kiểm tra danh tính hiện tại có quyền thực hiện hành động trên đối tượng cụ thể hay không.

### 3.2. Query parameter điều khiển việc truy vấn

Query string phù hợp với tiêu chí đọc như tìm kiếm, lọc, phân trang và sắp xếp:

~~~text
GET /books?q=java&category=programming&page=2&size=20
~~~

Action có thể nhận các tham số:

~~~java
@GetMapping
public BookPageResponse search(
    @RequestParam(required = false) String q,
    @RequestParam(required = false) String category,
    @RequestParam(defaultValue = "0") int page,
    @RequestParam(defaultValue = "20") int size
) {
    return books.search(new SearchBooksQuery(q, category, page, size));
}
~~~

Giá trị query đến từ client nên cần kiểm tra giới hạn. Ví dụ, page không nên âm; size cần có mức tối đa; sort field phải nằm trong danh sách được cho phép. Không nối trực tiếp giá trị sort hoặc filter vào SQL.

Query parameter thường có thể xuất hiện trong URL, lịch sử trình duyệt và log. Không gửi mật khẩu, token bí mật hoặc dữ liệu nhạy cảm trong query string.

### 3.3. Request body mang dữ liệu tạo hoặc cập nhật

Với API JSON, body được deserialize thành request DTO. Ví dụ:

~~~http
POST /api/books
Content-Type: application/json
Accept: application/json

{
  "title": "Clean Code",
  "author": "Robert C. Martin",
  "isbn": "9780132350884"
}
~~~

Controller có thể nhận DTO:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<BookResponse> create(
    @Valid @RequestBody CreateBookRequest request
) {
    var result = books.create(
        new CreateBookCommand(request.title(), request.author(), request.isbn())
    );
    return ResponseEntity.status(HttpStatus.CREATED).body(result);
}
~~~

Request DTO chỉ nên chứa các trường mà client được phép gửi. Không deserialize trực tiếp vào đối tượng miền hoặc persistence entity nếu việc đó cho phép client sửa những trường như ownerId, status, createdAt hay role ngoài ý muốn. Đây là một biện pháp giảm rủi ro mass assignment.

### 3.4. Form binding trong ứng dụng HTML MVC

Với server-rendered MVC, form HTML gửi các field theo tên. Controller nhận dữ liệu qua model binding:

~~~html
<form method="post" action="/books">
  <label for="title">Tên sách</label>
  <input id="title" name="title" required />

  <label for="author">Tác giả</label>
  <input id="author" name="author" required />

  <button type="submit">Lưu sách</button>
</form>
~~~

Controller Spring MVC có thể dùng @ModelAttribute:

~~~java
@PostMapping("/books")
public String create(
    @Valid @ModelAttribute("form") CreateBookForm form,
    BindingResult errors,
    RedirectAttributes redirect
) {
    if (errors.hasErrors()) {
        return "books/new";
    }

    books.create(new CreateBookCommand(form.title(), form.author(), form.isbn()));
    redirect.addFlashAttribute("message", "Đã tạo sách");
    return "redirect:/books";
}
~~~

Trong Spring MVC, BindingResult cần đứng ngay sau đối tượng được kiểm tra để action có thể nhận lỗi binding/validation theo cách thông thường. Form binding chỉ kiểm tra dữ liệu theo các ràng buộc đã khai báo; ca sử dụng và Model vẫn phải bảo vệ quy tắc nghiệp vụ.

## 4. Khai báo route và action trong Controller

Có nhiều cách tổ chức route. Với attribute routing, mỗi action khai báo trực tiếp path và method mà nó xử lý. Cách này giúp người đọc nhìn thấy hợp đồng HTTP ngay tại nơi điều phối.

### 4.1. Ví dụ Controller cho API

~~~java
@RestController
@RequestMapping("/api/books")
public class BookController {
    private final BookApplicationService books;

    public BookController(BookApplicationService books) {
        this.books = books;
    }

    @GetMapping
    public BookPageResponse list(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size
    ) {
        return books.list(page, size);
    }

    @GetMapping("/{bookId}")
    public BookResponse detail(@PathVariable UUID bookId) {
        return books.get(bookId);
    }

    @PostMapping
    public ResponseEntity<BookResponse> create(
        @Valid @RequestBody CreateBookRequest request,
        UriComponentsBuilder uriBuilder
    ) {
        var created = books.create(
            new CreateBookCommand(request.title(), request.author(), request.isbn())
        );

        var location = uriBuilder
            .path("/api/books/{id}")
            .buildAndExpand(created.id())
            .toUri();

        return ResponseEntity.created(location).body(created);
    }

    @PatchMapping("/{bookId}")
    public BookResponse update(
        @PathVariable UUID bookId,
        @Valid @RequestBody UpdateBookRequest request
    ) {
        return books.update(bookId, request);
    }

    @DeleteMapping("/{bookId}")
    public ResponseEntity<Void> delete(@PathVariable UUID bookId) {
        books.delete(bookId);
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/{bookId}/publish")
    public ResponseEntity<Void> publish(@PathVariable UUID bookId) {
        books.publish(bookId);
        return ResponseEntity.noContent().build();
    }
}
~~~

Ví dụ thể hiện một số quy tắc:

- @RequestMapping ở cấp lớp tạo tiền tố chung /api/books.
- @GetMapping, @PostMapping, @PatchMapping và @DeleteMapping ràng buộc action với HTTP method cụ thể.
- @PathVariable lấy định danh từ path.
- @RequestParam lấy bộ lọc hoặc phân trang từ query string.
- @RequestBody đọc biểu diễn JSON từ body.
- @Valid kích hoạt validation ở biên.
- ResponseEntity cho phép action kiểm soát status code và header như Location.

Các kiểu BookPageResponse, BookResponse, request DTO và BookApplicationService được lược bỏ phần triển khai. Trong ứng dụng thật, action cần ánh xạ các lỗi nghiệp vụ và lỗi không tìm thấy thành response phù hợp, thường thông qua exception handler tập trung.

### 4.2. Action cho HTML page

Với Controller trả View, action thường trả tên template hoặc ModelAndView:

~~~java
@Controller
@RequestMapping("/books")
public class BookPageController {
    private final BookApplicationService books;

    public BookPageController(BookApplicationService books) {
        this.books = books;
    }

    @GetMapping
    public String list(Model model) {
        model.addAttribute("books", books.listAll());
        return "books/list";
    }

    @GetMapping("/new")
    public String newForm(Model model) {
        model.addAttribute("form", new CreateBookForm());
        return "books/new";
    }

    @PostMapping
    public String create(
        @Valid @ModelAttribute("form") CreateBookForm form,
        BindingResult errors,
        RedirectAttributes redirect
    ) {
        if (errors.hasErrors()) {
            return "books/new";
        }

        var id = books.create(
            new CreateBookCommand(form.title(), form.author(), form.isbn())
        );
        redirect.addFlashAttribute("message", "Đã tạo sách " + id);
        return "redirect:/books";
    }
}
~~~

Ở đây, GET /books/new chỉ chuẩn bị form. POST /books thực hiện lệnh tạo. Khi validation thất bại, action trả lại template cùng lỗi. Khi thành công, action redirect để trình duyệt thực hiện GET tiếp theo.

### 4.3. Quy ước route và tên action

Tên phương thức action có thể là list, detail, create hoặc publish; tên đó giúp người đọc hiểu mục đích. Tuy nhiên, tên method Java không tự động là URL nếu framework sử dụng annotation routing. URL công khai phải được xem là hợp đồng với client.

Khi thiết kế route:

- Dùng danh từ cho tài nguyên và cấu trúc phân cấp có ý nghĩa, ví dụ /books/{bookId}/loans.
- Dùng HTTP method để phân biệt đọc, tạo, cập nhật và xóa.
- Dùng endpoint hành động có chủ đích cho thao tác miền không diễn đạt tốt bằng CRUD, ví dụ POST /books/{bookId}/publish.
- Giữ cách đặt tên nhất quán giữa các tài nguyên cùng loại.
- Tránh route mơ hồ hoặc quá nhiều alias cho cùng một thao tác nếu không có nhu cầu tương thích.
- Đặt route cụ thể trước route tổng quát khi framework dùng thứ tự đăng ký để phân giải.

Không cần ép mọi nghiệp vụ thành CRUD. Một hành động như approve, cancel hoặc publish có thể là một lệnh riêng vì nó biểu diễn chuyển trạng thái và có quy tắc riêng.

## 5. Binding, validation và chọn action là ba việc khác nhau

Các lỗi thường gặp xuất hiện khi trộn việc chọn endpoint với việc chuyển đổi và kiểm tra dữ liệu.

**Routing** trả lời: request này thuộc endpoint/action nào?

**Binding** trả lời: giá trị từ request được chuyển thành tham số hoặc DTO như thế nào?

**Validation** trả lời: dữ liệu đã binding có thỏa các ràng buộc đầu vào hay không?

Ví dụ, request PUT /books/abc có thể không khớp route nếu bookId yêu cầu UUID. Request PUT /books/{uuid} có thể khớp route nhưng body JSON sai cú pháp, khiến deserialize thất bại. Body có thể deserialize thành DTO nhưng title rỗng, khiến validation thất bại. Cả ba trường hợp đều xảy ra trước hoặc trong quá trình gọi action, nhưng bản chất và cách phản hồi khác nhau.

| Tình huống | Giai đoạn | Phản hồi thường gặp |
|---|---|---|
| Không có path nào khớp | Routing | 404 Not Found |
| Path có nhưng method không hỗ trợ | Method matching | 405 Method Not Allowed |
| Route value sai kiểu hoặc body không parse được | Constraint / binding | 400 Bad Request hoặc 404 tùy framework |
| Thiếu trường hoặc vi phạm validation | Validation | 400 với chi tiết lỗi hoặc trả lại form |
| Không đăng nhập | Authentication | 401 hoặc redirect đến trang đăng nhập |
| Đã đăng nhập nhưng không có quyền | Authorization | 403 Forbidden |
| Không tìm thấy tài nguyên | Use case / Model | 404 Not Found |
| Vi phạm quy tắc hoặc xung đột trạng thái | Use case / Model | 409 Conflict hoặc mã lỗi miền |
| Lỗi ngoài dự kiến | Exception handling | 500 Internal Server Error |

Status code chính xác phụ thuộc loại ứng dụng, hợp đồng API và cấu hình framework. Với HTML MVC, lỗi xác thực thường có thể dẫn đến redirect; với API, thường trả status code và error body.

### 5.1. Validation ở biên không thay thế quy tắc nghiệp vụ

Validation ở Controller phù hợp với kiểm tra cấu trúc: chuỗi có bắt buộc không, ngày có đúng định dạng không, số lượng có nằm trong giới hạn request không. Những kiểm tra này giúp client nhận phản hồi sớm.

Quy tắc nghiệp vụ có thể phụ thuộc trạng thái hiện tại của hệ thống: một sách đã được cho mượn không thể bị xóa; một đơn hàng đã giao không thể bị hủy. Các quy tắc này phải được thực thi trong Model hoặc ca sử dụng, vì hành động có thể được gọi từ nhiều adapter khác nhau.

### 5.2. Không dùng binding tự do cho toàn bộ đối tượng

Nếu framework tự động bind mọi field của một Entity, client có thể gửi thêm các field mà form không hiển thị. Ví dụ, request có thể chèn ownerId, approved, role hoặc price. Đây là rủi ro mass assignment.

Nên tạo request DTO chỉ gồm các trường được phép chỉnh sửa. Application Service nhận command rõ nghĩa và Model kiểm tra trạng thái. Nếu có field do server quản lý, hãy gán nó từ danh tính hoặc ngữ cảnh tin cậy ở phía server.

## 6. Xử lý trường hợp route trùng hoặc mơ hồ

Khi số lượng endpoint tăng, các route có thể chồng lấn. Ví dụ:

- /books/new
- /books/{bookId}

Nếu route tổng quát nhận mọi chuỗi, từ new có thể bị hiểu là bookId. Có thể giải quyết bằng route constraint yêu cầu UUID hoặc số nguyên, hoặc dùng cấu trúc route rõ ràng. Đừng dựa vào thứ tự ngẫu nhiên hoặc hành vi ngầm của framework.

Một số nguyên nhân mơ hồ khác:

- Hai action cùng path và method nhưng không có điều kiện phân biệt.
- Route template khác nhau về cách viết nhưng cùng khớp một request sau chuẩn hóa.
- Route catch-all bắt quá nhiều path.
- Route versioning hoặc content negotiation được cấu hình không nhất quán.
- Một endpoint cũ và endpoint mới cùng nhận request mà không có chính sách ưu tiên rõ ràng.

Khi route không khớp, hãy phân biệt 404 với 405. 404 có nghĩa không tìm được endpoint/tài nguyên theo cách xử lý hiện tại. 405 có nghĩa path được nhận diện nhưng method không được hỗ trợ; response thường nên cung cấp Allow header liệt kê method được phép. Một số framework hoặc cấu hình bảo mật có thể che giấu endpoint và trả 404, vì vậy cần hiểu chính sách thực tế của ứng dụng.

## 7. Ánh xạ action và bảo mật

Route là bề mặt công khai của ứng dụng. Bất kỳ client nào cũng có thể tự tạo request, bỏ qua nút bấm hoặc JavaScript trên giao diện. Vì vậy, việc ánh xạ action cần kết hợp với kiểm soát truy cập và bảo vệ dữ liệu.

### 7.1. Xác thực và phân quyền

- **Authentication** xác định danh tính người gửi request.
- **Authorization** quyết định danh tính đó có quyền thực hiện hành động trên tài nguyên cụ thể hay không.

Có thể áp dụng chính sách ở cấp route hoặc Controller, nhưng với quyền phụ thuộc dữ liệu, cần kiểm tra cả tài nguyên đã tải. Ví dụ, người dùng có quyền sửa sách của thư viện mình nhưng không được sửa sách thuộc thư viện khác. Chỉ kiểm tra role chung có thể chưa đủ.

### 7.2. CSRF và cookie session

Nếu ứng dụng dùng cookie session để xác thực, trình duyệt có thể tự gửi cookie kèm request. Một trang độc hại có thể tìm cách khiến trình duyệt của người dùng gửi request thay đổi dữ liệu. Form POST cần token chống CSRF hoặc cơ chế bảo vệ tương đương theo framework. Không dùng GET cho hành động thay đổi dữ liệu.

### 7.3. Kiểm tra quyền sở hữu và IDOR

Không được xem một ID khó đoán là biện pháp phân quyền. Nếu người dùng thay /books/42 thành /books/43 và đọc được tài nguyên của người khác, ứng dụng mắc lỗi truy cập trực tiếp đối tượng không an toàn (IDOR/BOLA). Mỗi action đọc hoặc thay đổi tài nguyên cần kiểm tra quyền theo đối tượng cụ thể.

### 7.4. Giới hạn dữ liệu và chống lạm dụng

Các action tìm kiếm, export, upload hoặc tạo tài nguyên cần giới hạn kích thước và tần suất phù hợp. Phân trang phải có giới hạn page size; upload phải kiểm tra loại, kích thước và vị trí lưu; action tốn tài nguyên cần rate limit hoặc quota khi cần. Không để query parameter do client cung cấp điều khiển trực tiếp tên bảng, tên cột hoặc câu lệnh hệ thống.

## 8. Phản hồi sau khi action hoàn tất

Sau khi gọi dịch vụ ứng dụng, Controller cần chọn loại response phù hợp với kiểu client và hợp đồng endpoint.

| Kết quả | HTML MVC | API |
|---|---|---|
| Đọc thành công | Render View | 200 OK với representation |
| Tạo thành công | Redirect đến trang chi tiết/danh sách | 201 Created, thường kèm Location |
| Cập nhật thành công | Redirect hoặc render kết quả | 200 OK hoặc 204 No Content |
| Xóa thành công | Redirect đến danh sách | 204 No Content hoặc kết quả theo hợp đồng |
| Dữ liệu không hợp lệ | Trả form kèm lỗi | 400 Bad Request hoặc 422 theo quy ước API |
| Không đăng nhập | Redirect login | 401 Unauthorized |
| Không có quyền | Trang 403 | 403 Forbidden |
| Không tìm thấy | Trang 404 | 404 Not Found |

### 8.1. Post/Redirect/Get

Với form HTML, sau POST thành công, Controller thường redirect sang GET. Đây là mẫu Post/Redirect/Get (PRG). Nó giúp việc refresh trang kết quả không gửi lại form POST lần nữa.

Thông báo ngắn hạn có thể được lưu trong flash attribute/session để hiển thị ở request GET tiếp theo. Không nên dùng query string để truyền dữ liệu nhạy cảm hoặc nhét toàn bộ trạng thái form vào URL.

### 8.2. Location và mã trạng thái khi tạo tài nguyên

API tạo tài nguyên thường trả 201 Created và Location trỏ đến tài nguyên mới. Client có thể dùng URL đó để đọc tài nguyên vừa tạo. Nếu thao tác chỉ chấp nhận một công việc bất đồng bộ, 202 Accepted có thể phù hợp; response nên cung cấp cách theo dõi trạng thái nếu hợp đồng yêu cầu.

### 8.3. Content negotiation

Header Accept cho biết client muốn nhận định dạng nào; Content-Type cho biết định dạng body gửi lên. Một endpoint có thể chỉ hỗ trợ JSON hoặc có thể hỗ trợ nhiều kiểu representation. Hãy công bố rõ định dạng được chấp nhận. Nếu request gửi media type không được hỗ trợ, server có thể trả 415 Unsupported Media Type; nếu response không thể tạo theo Accept được yêu cầu, có thể trả 406 Not Acceptable.

## 9. Những lỗi thiết kế thường gặp

| Dấu hiệu | Hệ quả | Cách cải thiện |
|---|---|---|
| Một action xử lý nhiều thao tác không liên quan dựa vào query flag | Route khó hiểu, kiểm thử nhiều nhánh, khó kiểm soát quyền | Tách endpoint/action theo ý định và method |
| Dùng GET để thay đổi trạng thái | Crawler, prefetch hoặc refresh có thể kích hoạt thay đổi ngoài ý muốn | Dùng POST/PATCH/DELETE phù hợp |
| Controller bind trực tiếp persistence entity | Client có thể sửa field ngoài dự kiến | Dùng request DTO và command |
| Action tự đọc header, parse body và chuyển đổi thủ công mọi trường | Lặp logic, bỏ qua cơ chế binding/validation chuẩn | Dùng model binding có kiểm soát và DTO |
| Route tổng quát che route cụ thể | URL như /new bị hiểu thành ID | Dùng route constraint hoặc cấu trúc route rõ |
| Dựa vào việc ẩn nút trên View để bảo vệ action | Client có thể gọi endpoint trực tiếp | Kiểm tra authorization ở server |
| Một Controller có quá nhiều action thuộc nhiều tài nguyên | Trách nhiệm không rõ và khó bảo trì | Chia Controller theo tài nguyên hoặc nhóm use case |
| Trả lỗi khác nhau tùy action cho cùng một loại tình huống | Client khó xử lý và giao diện không nhất quán | Chuẩn hóa exception handler và error response |
| Cho phép page size hoặc filter không giới hạn | Tăng tải và có thể gây cạn tài nguyên | Validate, giới hạn và rate limit |
| Route chỉ được kiểm tra qua happy path | Endpoint trùng, method sai hoặc binding lỗi bị bỏ sót | Viết route test và negative test |

Một action nên thể hiện một ý định rõ ràng. Nếu phương thức có nhiều nhánh như “nếu mode=delete thì xóa, nếu mode=update thì cập nhật, còn lại thì tạo”, hãy xem xét tách thành các action riêng với route và method tương ứng.

## 10. Kiểm thử ánh xạ route và action

Kiểm thử Controller không chỉ xác nhận nội dung trả về. Cần xác nhận request đúng được đưa đến đúng action và request sai bị từ chối theo hợp đồng.

Các nhóm kiểm thử hữu ích:

1. **Route matching:** path và method đúng gọi action dự kiến.
2. **Route constraint:** ID sai định dạng không được chuyển nhầm sang action khác.
3. **Model binding:** path, query, header và body được gán đúng tham số.
4. **Validation:** dữ liệu sai không gọi ca sử dụng ghi dữ liệu.
5. **Authorization:** người dùng không có quyền không thể đọc hoặc thay đổi tài nguyên.
6. **Response contract:** status code, header, redirect, Location và body đúng như cam kết.
7. **Error mapping:** lỗi không tìm thấy, xung đột nghiệp vụ và lỗi ngoài dự kiến được ánh xạ nhất quán.
8. **Content negotiation:** kiểu nội dung không được hỗ trợ bị từ chối đúng cách.

Ví dụ các ca test cho endpoint tạo sách:

| Request | Kết quả cần xác minh |
|---|---|
| POST /api/books với JSON hợp lệ | Action create được gọi; trả 201 và Location |
| POST /api/books với title rỗng | Trả lỗi validation; không gọi application service |
| POST /api/books với body JSON hỏng | Trả lỗi request; không gọi action nghiệp vụ |
| GET /api/books/UUID-hợp-lệ | Gọi action detail với đúng ID |
| GET /api/books/không-phải-UUID | Route constraint hoặc binding từ chối |
| DELETE /api/books/{id} khi không có quyền | Trả 403 hoặc phản hồi theo chính sách; không xóa |
| GET /api/books/{id} không tồn tại | Trả 404 |

Có thể dùng MockMvc trong Spring để kiểm tra route, binding, validation và response mà không cần khởi chạy toàn bộ hệ thống. Integration test có thể bổ sung để kiểm tra security filter, serialization và cấu hình thực tế. Test của application service vẫn cần riêng để kiểm tra quy tắc use case.

## 11. Checklist khi thiết kế ánh xạ action

- [ ] Mỗi thao tác có route và HTTP method diễn đạt đúng ý nghĩa.
- [ ] Path định danh tài nguyên; query thể hiện tiêu chí đọc; body/form chứa dữ liệu theo hợp đồng.
- [ ] Route constraint loại bỏ giá trị sai định dạng và giảm nguy cơ mơ hồ.
- [ ] Action có trách nhiệm điều phối rõ ràng và gọi dịch vụ ứng dụng phù hợp.
- [ ] Request DTO chỉ chứa các trường client được phép gửi.
- [ ] Binding và validation được kiểm tra trước khi gọi use case ghi dữ liệu.
- [ ] Quy tắc nghiệp vụ vẫn được bảo vệ trong Model hoặc dịch vụ ứng dụng.
- [ ] Authentication và authorization được áp dụng cho từng hành động và tài nguyên.
- [ ] Response status, header, redirect và error body nhất quán với hợp đồng.
- [ ] Có route test cho trường hợp hợp lệ, method sai, ID sai, dữ liệu sai và không có quyền.

Khi route, method, dữ liệu đầu vào và action được xác định rõ, Controller trở thành ranh giới điều phối dễ đọc: mỗi request có một nơi tiếp nhận, mỗi thao tác gọi đúng ca sử dụng, và kết quả được trả về theo hợp đồng mà client có thể dự đoán.
