# So sánh hai phương án thiết kế và giải thích đánh đổi

Trong một ứng dụng Model–View–Controller (MVC), cùng một nghiệp vụ có thể được trình bày theo nhiều cách. Một ứng dụng quản lý sách có thể render HTML ở phía server bằng Controller, Model và template View; hoặc cung cấp REST API trả JSON để một frontend riêng dựng giao diện. Cả hai phương án đều có thể dùng chung application service, domain model và persistence. Khác biệt nằm ở ranh giới giao tiếp, nơi tạo giao diện, cách quản lý trạng thái và chi phí vận hành.

Bài thực hành này yêu cầu người học so sánh hai phương án cho cùng một bài toán, đưa ra quyết định dựa trên yêu cầu và giải thích các đánh đổi. Mục tiêu không phải tìm một kiến trúc luôn tốt hơn, mà là chứng minh lựa chọn phù hợp với bối cảnh cụ thể.

## 1. Bối cảnh bài tập

Một thư viện đang xây dựng ứng dụng nội bộ để nhân viên quản lý danh mục sách. Phiên bản đầu cần hỗ trợ:

- Xem danh sách sách, tìm kiếm theo tiêu đề, tác giả hoặc ISBN và phân trang.
- Xem chi tiết một cuốn sách.
- Tạo sách mới và sửa thông tin sách.
- Hiển thị lỗi validation rõ ràng và giữ lại dữ liệu đã nhập.
- Chỉ nhân viên có quyền quản lý danh mục mới được tạo hoặc sửa.
- Ghi nhận người tạo và thời điểm cập nhật.

Nhóm phát triển có kinh nghiệm Java và Spring. Phiên bản đầu phục vụ nhân viên trên trình duyệt máy tính. Nhóm muốn phát hành sớm với một đội nhỏ. Trong tương lai, thư viện có thể cần ứng dụng di động hoặc tích hợp với hệ thống đối tác để tra cứu danh mục.

Các giả định dùng trong bài:

1. Hệ thống nghiệp vụ và dữ liệu sách do backend Spring quản lý.
2. Nhân viên phải đăng nhập; thao tác ghi cần được kiểm tra quyền ở server.
3. Chưa có yêu cầu bắt buộc phải hỗ trợ nhiều frontend ngay trong phiên bản đầu.
4. Dữ liệu sách có thể tăng dần, vì vậy danh sách cần tìm kiếm và phân trang ở backend.
5. Chưa có quyết định về việc ứng dụng di động sẽ được triển khai vào thời điểm nào.

Những giả định này là đầu vào để lập luận. Nếu thay đổi một giả định, kết luận kiến trúc có thể thay đổi theo.

## 2. Hai phương án cần so sánh

### Phương án A: Server-side rendered MVC

Backend Spring MVC nhận request, gọi application service, đưa dữ liệu vào Spring UI Model và trả tên logic của View. View engine như Thymeleaf render HTML ở server rồi gửi trang hoàn chỉnh về trình duyệt.

Luồng điển hình:

~~~mermaid
sequenceDiagram
    actor Staff as Nhân viên
    participant Browser as Trình duyệt
    participant C as BookController
    participant A as Application Service
    participant R as Repository
    participant V as Thymeleaf View

    Staff->>Browser: Mở /books
    Browser->>C: GET /books
    C->>A: search(criteria)
    A->>R: Tìm sách và phân trang
    R-->>A: Page<BookListItem>
    A-->>C: Dữ liệu danh sách
    C->>V: View name + Model
    V-->>Browser: HTML đã render
    Browser-->>Staff: Hiển thị danh sách
~~~

Ví dụ Controller:

~~~java
@Controller
@RequestMapping("/books")
public class BookPageController {
    private final BookQueryService queryService;

    public BookPageController(BookQueryService queryService) {
        this.queryService = queryService;
    }

    @GetMapping
    public String list(
            @RequestParam(required = false) String q,
            Pageable pageable,
            Model model
    ) {
        model.addAttribute("page", queryService.search(q, pageable));
        model.addAttribute("keyword", q);
        return "books/list";
    }
}
~~~

Trong ví dụ, Model là container key/value dành cho dữ liệu trình bày của request. Nó không phải Domain Model của sách. View name books/list là tên logic để ViewResolver tìm template tương ứng.

Khi tạo sách, Controller nhận form DTO, validation lỗi thì render lại form; thành công thì redirect đến trang chi tiết theo mẫu POST-Redirect-GET. Trình duyệt nhận HTML và điều hướng trang theo liên kết hoặc form.

### Phương án B: REST API và frontend riêng

Backend cung cấp các endpoint HTTP có hợp đồng JSON. Một frontend riêng, ví dụ ứng dụng JavaScript, gọi API, quản lý trạng thái giao diện và dựng HTML trong trình duyệt.

Luồng điển hình:

~~~mermaid
sequenceDiagram
    actor Staff as Nhân viên
    participant Browser as Trình duyệt
    participant UI as Frontend Application
    participant C as BookApiController
    participant A as Application Service
    participant R as Repository

    Staff->>Browser: Mở ứng dụng
    Browser->>UI: Tải frontend
    UI->>C: GET /api/books
    C->>A: search(criteria)
    A->>R: Tìm sách và phân trang
    R-->>A: Page<BookListItem>
    A-->>C: Dữ liệu danh sách
    C-->>UI: JSON response
    UI-->>Browser: Dựng giao diện
    Browser-->>Staff: Hiển thị danh sách
~~~

Ví dụ REST Controller:

~~~java
@RestController
@RequestMapping("/api/books")
public class BookApiController {
    private final BookQueryService queryService;

    public BookApiController(BookQueryService queryService) {
        this.queryService = queryService;
    }

    @GetMapping
    public Page<BookListResponse> list(
            @RequestParam(required = false) String q,
            Pageable pageable
    ) {
        return queryService.search(q, pageable)
                .map(BookListResponse::from);
    }
}
~~~

Ở đây, DTO được ghi thành JSON qua HttpMessageConverter. ViewResolver không tìm template cho response body. Frontend nhận JSON và quyết định cách hiển thị danh sách, trạng thái tải, lỗi và điều hướng.

Hai phương án có thể cùng gọi BookQueryService và BookCommandService. Việc chọn REST API không yêu cầu đưa quy tắc nghiệp vụ vào frontend; frontend chỉ là một adapter trình bày và tương tác.

## 3. Hợp đồng chức năng chung

Để so sánh công bằng, cả hai phương án phải đáp ứng cùng các hành vi nghiệp vụ:

| Hành động | Server-side rendered MVC | REST API + frontend |
|---|---|---|
| Danh sách | GET /books, render HTML | GET /api/books, trả JSON |
| Chi tiết | GET /books/{id}, render HTML | GET /api/books/{id}, trả JSON |
| Mở form tạo | GET /books/new, render form | Frontend mở màn hình form |
| Tạo sách | POST /books, redirect khi thành công | POST /api/books, trả kết quả JSON |
| Mở form sửa | GET /books/{id}/edit, render form | Frontend tải dữ liệu rồi mở form |
| Cập nhật | POST /books/{id}, redirect khi thành công | PUT /api/books/{id}, trả kết quả JSON |

Các URL là ví dụ. Điều quan trọng là mỗi phương án phải hỗ trợ cùng use case, quy tắc validation, phân quyền và dữ liệu.

## 4. Nhiệm vụ thực hành

Hãy làm việc theo nhóm nhỏ hoặc cá nhân. Ghi lại giả định trước khi chọn kiến trúc; không thay đổi yêu cầu giữa hai phương án để làm một phương án có vẻ tốt hơn.

### Nhiệm vụ 1: Xác định tiêu chí ra quyết định

Đọc bối cảnh và chọn tối đa năm tiêu chí quan trọng nhất đối với phiên bản đầu. Có thể cân nhắc:

- Thời gian phát hành.
- Khối lượng công việc frontend và backend.
- Khả năng tái sử dụng backend cho ứng dụng di động.
- Trải nghiệm tìm kiếm, lọc và cập nhật từng phần của trang.
- Độ phức tạp triển khai, cấu hình và vận hành.
- Bảo mật phiên đăng nhập, CSRF, CORS và quản lý token.
- Khả năng kiểm thử và bảo trì.
- Khả năng truy cập, tải trang và hoạt động khi JavaScript bị tắt hoặc lỗi.

Không mặc định mọi tiêu chí có trọng số như nhau. Hãy giải thích vì sao tiêu chí nào quan trọng hơn trong bối cảnh thư viện.

### Nhiệm vụ 2: Vẽ hai luồng request

Với mỗi phương án, vẽ luồng cho hai hành động:

1. Nhân viên mở danh sách và tìm sách theo từ khóa.
2. Nhân viên gửi form tạo sách nhưng tiêu đề bị bỏ trống.

Sơ đồ phải chỉ rõ:

- Request đi vào thành phần nào.
- Thành phần nào gọi application service.
- Dữ liệu được truyền qua các tầng dưới dạng nào.
- Lỗi validation được trả về và hiển thị ra sao.
- Thành phần nào tạo HTML cuối cùng.

Nếu một sơ đồ không thể chỉ ra ai chịu trách nhiệm render giao diện hoặc ánh xạ lỗi, hãy bổ sung trước khi so sánh.

### Nhiệm vụ 3: So sánh hợp đồng và xử lý lỗi

Viết ví dụ cho thao tác tạo sách ở cả hai phương án.

Với server-side rendered MVC, thể hiện:

- Form DTO và validation.
- Model attribute chứa lỗi hoặc dữ liệu đã nhập.
- View được render lại khi form không hợp lệ.
- Redirect sau khi lưu thành công.

Với REST API, thể hiện:

- Request DTO và validation.
- JSON response khi thành công.
- Error response có mã lỗi và lỗi theo trường khi thất bại.
- Cách frontend gắn lỗi vào form.

Hãy trả lời: lỗi nào thuộc validation đầu vào, lỗi nào là quy tắc nghiệp vụ, và lỗi nào là lỗi hệ thống?

### Nhiệm vụ 4: Lập ma trận đánh đổi

Điền ma trận dưới đây. Mỗi ô phải có lý do dựa trên bối cảnh, không chỉ ghi “tốt”, “xấu” hoặc “nhanh”.

| Tiêu chí | Server-side rendered MVC | REST API + frontend riêng |
|---|---|---|
| Thời gian làm phiên bản đầu |  |  |
| Số phần cần triển khai và phát hành |  |  |
| Quản lý trạng thái giao diện |  |  |
| Tìm kiếm và cập nhật từng phần |  |  |
| Tái sử dụng cho mobile/đối tác |  |  |
| Validation và hiển thị lỗi |  |  |
| Bảo mật phiên và request ghi |  |  |
| Kiểm thử frontend/backend |  |  |
| SEO và chia sẻ trang công khai |  |  |
| Vận hành và quan sát lỗi |  |  |

### Nhiệm vụ 5: Đưa ra quyết định có điều kiện

Viết một quyết định kiến trúc ngắn gồm:

1. Phương án được chọn cho phiên bản đầu.
2. Ba lý do quan trọng nhất.
3. Hai đánh đổi mà nhóm chấp nhận.
4. Một rủi ro cần theo dõi sau khi phát hành.
5. Điều kiện cụ thể khiến nhóm xem xét chuyển sang phương án còn lại.

Không dùng lý do chung chung như “REST hiện đại hơn”, “MVC cũ hơn” hoặc “frontend tách riêng luôn dễ mở rộng hơn”. Mỗi nhận định phải gắn với yêu cầu, kỹ năng nhóm, cách triển khai hoặc kế hoạch sản phẩm.

## 5. Gợi ý hợp đồng tạo sách để đối chiếu

### 5.1. Form HTML trong server-side rendered MVC

Form gửi dữ liệu theo application/x-www-form-urlencoded hoặc multipart khi có file. Controller bind vào form DTO:

~~~java
public record CreateBookForm(
        @NotBlank @Size(max = 200) String title,
        @NotBlank @Size(max = 300) String author,
        @Size(max = 17) String isbn
) {}

@PostMapping("/books")
public String create(
        @Valid @ModelAttribute("form") CreateBookForm form,
        BindingResult errors,
        Model model,
        RedirectAttributes redirect
) {
    if (errors.hasErrors()) {
        return "books/create";
    }

    UUID id = createBookService.execute(
            new CreateBookCommand(
                    form.title(),
                    form.author(),
                    form.isbn()
            )
    );
    redirect.addFlashAttribute("notice", "Đã tạo sách.");
    return "redirect:/books/" + id;
}
~~~

BindingResult đứng ngay sau tham số được validate. Khi có lỗi, Controller trả lại View cùng form và lỗi. Khi thành công, redirect giúp trình duyệt thực hiện GET mới và tránh gửi lại POST khi refresh.

### 5.2. JSON trong REST API

API nhận JSON và trả status cùng representation rõ ràng:

~~~java
public record CreateBookRequest(
        @NotBlank @Size(max = 200) String title,
        @NotBlank @Size(max = 300) String author,
        @Size(max = 17) String isbn
) {}

public record CreateBookResponse(UUID id) {}

@PostMapping
public ResponseEntity<CreateBookResponse> create(
        @Valid @RequestBody CreateBookRequest request
) {
    UUID id = createBookService.execute(
            new CreateBookCommand(
                    request.title(),
                    request.author(),
                    request.isbn()
            )
    );
    URI location = URI.create("/api/books/" + id);
    return ResponseEntity.created(location)
            .body(new CreateBookResponse(id));
}
~~~

Frontend phải chuyển lỗi validation từ response thành thông báo ở từng trường. API nên có error contract ổn định, chẳng hạn dùng Problem Details với mã lỗi, thông điệp tổng quát và danh sách lỗi theo trường. Không gửi stack trace hoặc chi tiết SQL cho client.

Hai ví dụ chỉ thể hiện phần ranh giới HTTP. Cả hai đều phải dùng chung quy tắc nghiệp vụ trong application/domain layer; không coi validation phía trình duyệt là lớp bảo vệ dữ liệu.

## 6. Những đánh đổi cần phân tích

### 6.1. Thời gian phát hành và độ phức tạp hệ thống

Server-side rendered MVC thường cho phép một nhóm Java nhỏ triển khai Controller, service, repository và template trong cùng ứng dụng. Nhóm không phải xây dựng và phát hành một frontend riêng ngay từ đầu.

REST API + frontend riêng tạo thêm hợp đồng API, ứng dụng client, cấu hình build, tích hợp xác thực và quy trình phát hành. Chi phí ban đầu cao hơn, nhưng có thể phù hợp khi frontend cần phát triển độc lập hoặc có nhiều client thực sự.

Đừng chỉ đếm số repository hoặc số project. Hãy tính cả pipeline, cấu hình môi trường, log, theo dõi lỗi, quản lý phiên bản API và phối hợp giữa nhóm frontend/backend.

### 6.2. Trải nghiệm giao diện và trạng thái client

Server-side rendered MVC phù hợp với điều hướng trang, form nhập liệu và các thao tác CRUD truyền thống. Server chuẩn bị Model, View render HTML. Có thể bổ sung JavaScript cho những tương tác cần thiết mà không phải biến toàn bộ giao diện thành SPA.

Frontend riêng thuận tiện khi giao diện có nhiều trạng thái tương tác, cập nhật từng phần, thao tác liên tục hoặc cần chia sẻ component ở nhiều màn hình. Đổi lại, frontend phải quản lý loading, empty state, lỗi mạng, cache, đồng bộ dữ liệu và điều hướng.

### 6.3. Tái sử dụng cho nhiều client

REST API tạo hợp đồng dữ liệu có thể dùng cho web, mobile hoặc đối tác. Tuy vậy, một API chỉ hữu ích khi có client thứ hai hoặc nhu cầu tích hợp đủ rõ. Tạo API tổng quát quá sớm có thể dẫn đến versioning và tương thích ngược mà sản phẩm chưa cần.

Server-side rendered MVC vẫn có thể bổ sung API sau này. Nếu application service và domain không phụ thuộc View, nhóm có thể thêm REST Controller làm adapter mới mà không viết lại use case.

### 6.4. Bảo mật

Không phương án nào tự động an toàn hơn. Cả hai đều phải xác thực, kiểm tra quyền ở server, validate dữ liệu và bảo vệ dữ liệu đầu ra.

- Với xác thực bằng session cookie, form POST cần CSRF protection. Cookie nên có thuộc tính phù hợp như HttpOnly, Secure và SameSite theo mô hình triển khai.
- REST API dùng cookie vẫn cần xem xét CSRF. Dùng bearer token có thể thay đổi mô hình CSRF nhưng kéo theo yêu cầu lưu trữ, hết hạn, thu hồi và truyền token an toàn.
- Frontend tách origin có thể cần cấu hình CORS. CORS không thay thế authentication hoặc authorization.
- Ẩn nút sửa trong giao diện không bảo vệ endpoint; backend phải kiểm tra quyền cho từng thao tác.

So sánh cần nêu mô hình đăng nhập cụ thể thay vì gán đặc tính bảo mật cho tên kiến trúc.

### 6.5. Kiểm thử và chẩn đoán lỗi

Với server-side rendered MVC, có thể dùng MockMvc để kiểm tra route, model, View name, validation và redirect; bổ sung test render template khi cần.

Với REST API, có thể dùng MockMvc hoặc WebTestClient để kiểm tra status, header, JSON schema và error contract. Frontend cần test component, state, routing và tích hợp API. Khi lỗi xảy ra, nhóm cần theo dõi request từ browser qua frontend đến backend.

### 6.6. Hiệu năng và khả năng truy cập

HTML render ở server có thể hiển thị nội dung sớm và giảm lượng JavaScript cần tải. Tuy nhiên, mỗi lần điều hướng trang thường yêu cầu round trip để nhận HTML mới.

Frontend riêng có thể cập nhật một phần trang và tận dụng cache phía client. Nhưng lần tải đầu có thể cần tải bundle, khởi tạo ứng dụng rồi gọi API. Hiệu năng thực tế phụ thuộc kích thước payload, cache, mạng, query và cách triển khai.

Cả hai phương án đều có thể đạt khả năng truy cập tốt. Server-side rendering không tự động bảo đảm HTML accessible; frontend riêng cũng không mặc định kém truy cập. Cần kiểm tra semantic HTML, label, focus, keyboard navigation và thông báo lỗi.

## 7. Ma trận đánh giá có trọng số

Để quyết định có thể kiểm tra lại, hãy gán trọng số cho tiêu chí. Tổng trọng số bằng 100. Chấm mỗi phương án từ 1 đến 5:

- 1: đáp ứng kém trong bối cảnh này.
- 2: cần nhiều bổ sung hoặc có rủi ro đáng kể.
- 3: đáp ứng được với chi phí hợp lý.
- 4: phù hợp tốt.
- 5: rất phù hợp với yêu cầu đã nêu.

Mẫu bảng:

| Tiêu chí | Trọng số | SSR MVC (1–5) | REST + frontend (1–5) | Lý do/trọng số |
|---|---:|---:|---:|---|
| Phát hành sớm |  |  |  |  |
| Đội ngũ hiện tại |  |  |  |  |
| Tương tác giao diện |  |  |  |  |
| Nhiều client trong tương lai |  |  |  |  |
| Vận hành |  |  |  |  |
| Bảo mật theo mô hình đăng nhập |  |  |  |  |
| **Tổng** | **100** |  |  |  |

Điểm tổng có trọng số được tính bằng tổng của trọng số nhân với điểm từng tiêu chí. Nếu trọng số được nhập theo phần trăm, hai phương án có thể so sánh trực tiếp. Điểm số chỉ hỗ trợ thảo luận; nó không thay thế giải thích định tính hoặc các ràng buộc bắt buộc.

Không được gán trọng số cao cho tiêu chí “mobile tương lai” chỉ vì đó là khả năng có thể xảy ra. Hãy phân biệt yêu cầu đã cam kết, xác suất, thời điểm và chi phí thay đổi nếu nhu cầu thực sự xuất hiện.

## 8. Mẫu quyết định kiến trúc

Sau khi hoàn thành ma trận, viết một bản quyết định ngắn theo mẫu:

~~~text
Quyết định:
Chọn [phương án A hoặc B] cho phiên bản đầu.

Bối cảnh:
Nêu yêu cầu, người dùng, kỹ năng nhóm, thời hạn và kế hoạch client.

Lý do:
1. ...
2. ...
3. ...

Đánh đổi chấp nhận:
1. ...
2. ...

Rủi ro và cách theo dõi:
...

Điều kiện xem xét lại:
...

Hệ quả triển khai:
...
~~~

Một quyết định tốt nêu cả lợi ích lẫn chi phí. Nếu chọn SSR MVC, hãy nói rõ API cho mobile chưa được xây dựng và sẽ cần thêm adapter khi có nhu cầu. Nếu chọn REST + frontend, hãy giải thích vì sao lợi ích của frontend độc lập đủ bù chi phí build, phát hành, xác thực và kiểm thử bổ sung.

## 9. Gợi ý kết luận cho bối cảnh đề bài

Với giả định hiện tại, server-side rendered MVC là lựa chọn hợp lý cho phiên bản đầu: ứng dụng chủ yếu là CRUD nội bộ trên trình duyệt, nhóm có kỹ năng Java/Spring, cần phát hành sớm và chưa có cam kết về mobile. Spring MVC cùng Thymeleaf có thể đáp ứng danh sách, chi tiết và form; application service giữ use case độc lập để có thể bổ sung REST API sau.

Đánh đổi được chấp nhận là trải nghiệm điều hướng chủ yếu theo request/response trang và backend phải render HTML. Nếu sau này giao diện cần tương tác dày, nhiều màn hình cập nhật liên tục hoặc mobile/đối tác trở thành client được cam kết, nhóm có thể bổ sung REST adapter. Khi đó, domain và application layer đã tách biệt sẽ giảm phạm vi thay đổi.

REST API + frontend riêng sẽ hợp lý hơn nếu yêu cầu nhiều client đã chắc chắn, nhóm có năng lực frontend phù hợp, giao diện cần tương tác phong phú hoặc frontend và backend cần phát hành độc lập. Không nên chọn phương án này chỉ vì dự đoán mơ hồ rằng một ngày nào đó có thể cần ứng dụng di động.

Đây là kết luận có điều kiện từ các giả định của bài, không phải quy tắc chung cho mọi ứng dụng MVC.

## 10. Tiêu chí đánh giá bài làm

Giảng viên có thể dùng thang điểm 100:

| Hạng mục | Điểm | Bằng chứng cần có |
|---|---:|---|
| Hiểu đúng hai luồng kiến trúc | 20 | Sơ đồ đúng trách nhiệm Controller, service, View/API và client |
| So sánh dựa trên yêu cầu | 25 | Ma trận có lý do, gắn với bối cảnh |
| Phân tích hợp đồng và lỗi | 15 | Ví dụ form/JSON, validation và error mapping |
| Bảo mật và vận hành | 15 | Phân tích session/CSRF hoặc token/CORS, triển khai và kiểm thử |
| Quyết định và đánh đổi | 20 | Lý do, chi phí chấp nhận, rủi ro và điều kiện xem xét lại |
| Trình bày rõ ràng | 5 | Thuật ngữ nhất quán, sơ đồ dễ đọc, giả định minh bạch |

Một bài chỉ liệt kê ưu/nhược điểm chung mà không gắn với yêu cầu thư viện chưa đạt mức phân tích. Một bài đạt tốt cần chỉ ra tiêu chí nào quyết định lựa chọn, tiêu chí nào chỉ là yếu tố phụ và điều gì sẽ khiến quyết định thay đổi.

## 11. Câu hỏi tự kiểm tra

1. Trong SSR MVC, Model được truyền cho View có phải Domain Model không? Giải thích sự khác nhau.
2. Khi một method trong @RestController trả DTO, thành phần nào ghi JSON vào response?
3. Vì sao REST API không tự động làm cho ứng dụng hỗ trợ mobile tốt hơn nếu chưa có hợp đồng API ổn định?
4. Với session cookie, vì sao form POST cần xem xét CSRF dù backend dùng MVC hay REST?
5. Khi validation form sai, SSR MVC và REST API + frontend truyền lỗi tới người dùng theo những bước nào?
6. Nếu nhóm chọn SSR MVC trước, cần giữ ranh giới nào để có thể thêm REST adapter sau?
7. Khi nào chi phí frontend riêng trở nên đáng giá?
8. Vì sao điểm tổng có trọng số không thể thay thế quyết định và giải thích của nhóm?

## 12. Checklist hoàn thành

- [ ] Đã ghi rõ giả định và yêu cầu của phiên bản đầu.
- [ ] Đã mô tả hai phương án với cùng use case và cùng quy tắc nghiệp vụ.
- [ ] Đã vẽ luồng danh sách và luồng form lỗi cho cả hai phương án.
- [ ] Đã phân biệt Spring UI Model, Domain Model và JSON response DTO.
- [ ] Đã mô tả validation, error contract và cách hiển thị lỗi.
- [ ] Đã so sánh bảo mật theo mô hình xác thực cụ thể.
- [ ] Đã đánh giá triển khai, kiểm thử, vận hành và khả năng mở rộng.
- [ ] Đã chọn tiêu chí và trọng số có lý do.
- [ ] Đã nêu quyết định, đánh đổi, rủi ro và điều kiện xem xét lại.
- [ ] Đã tránh các kết luận tuyệt đối như “SPA luôn tốt hơn” hoặc “SSR luôn đơn giản hơn”.

## Kết luận

So sánh hai phương án thiết kế chỉ có giá trị khi chúng giải quyết cùng một bài toán và được đánh giá theo cùng các tiêu chí. Server-side rendered MVC tập trung render HTML ở server, thường phù hợp với ứng dụng CRUD nội bộ cần phát hành sớm. REST API kết hợp frontend riêng tạo ranh giới client/server rõ ràng và hỗ trợ nhiều client, nhưng bổ sung chi phí hợp đồng API, frontend, xác thực, kiểm thử và vận hành. Trong cả hai phương án, Controller vẫn là adapter; application service và domain model giữ quy tắc nghiệp vụ độc lập với cách trình bày. Quyết định tốt là quyết định giải thích được vì sao lợi ích phù hợp với bối cảnh, chi phí nào được chấp nhận và điều kiện nào sẽ khiến nhóm đánh giá lại.
