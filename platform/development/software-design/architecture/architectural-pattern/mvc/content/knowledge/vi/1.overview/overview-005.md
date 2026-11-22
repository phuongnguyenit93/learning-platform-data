# Nguồn gốc MVC và sự thay đổi khi áp dụng trên web

## 1. Vì sao MVC ra đời?

Model–View–Controller (MVC) là một mẫu kiến trúc dùng để tổ chức ứng dụng thành ba phần có trách nhiệm khác nhau: **Model** quản lý dữ liệu và quy tắc nghiệp vụ, **View** trình bày thông tin, còn **Controller** tiếp nhận và điều phối tương tác. Mục tiêu là giúp trạng thái và nghiệp vụ, giao diện, cùng cách người dùng điều khiển ứng dụng có thể thay đổi tương đối độc lập.

Ý tưởng MVC xuất hiện trong bối cảnh các hệ thống giao diện đồ họa tương tác, trước khi web phổ biến. Trong những ứng dụng này, một đối tượng nghiệp vụ có thể được trình bày theo nhiều cách: cùng một tài liệu có thể xuất hiện trong cửa sổ soạn thảo, danh sách tài liệu và bảng thuộc tính. Nếu dữ liệu, cách hiển thị và xử lý thao tác bị trộn lẫn trong một khối mã, việc thêm một cách trình bày mới hoặc thay đổi một thao tác dễ ảnh hưởng đến những phần còn lại.

MVC đưa ra cách phân chia trách nhiệm để giải quyết vấn đề đó. Dữ liệu và quy tắc cốt lõi được giữ trong Model; View chịu trách nhiệm thể hiện trạng thái; Controller chuyển thao tác của người dùng thành hành động trên Model hoặc điều khiển cách View phản hồi. Nhờ vậy, nhiều View có thể cùng làm việc với một Model, và cách tương tác có thể thay đổi mà không cần viết lại toàn bộ nghiệp vụ.

## 2. Bối cảnh lịch sử

MVC thường được gắn với công trình của **Trygve Reenskaug** tại Xerox PARC vào cuối thập niên 1970, trong quá trình phát triển môi trường Smalltalk. Reenskaug tìm cách tổ chức các ứng dụng tương tác sao cho người dùng có thể làm việc với các mô hình dữ liệu thông qua những cách trình bày và điều khiển khác nhau. Các ý tưởng này được phát triển trong hệ sinh thái Smalltalk và được biết đến rộng rãi hơn qua Smalltalk-80.

Điều cần ghi nhớ về lịch sử MVC không phải là một mốc năm duy nhất, mà là vấn đề thiết kế mà nó giải quyết: **tách mô hình của miền bài toán khỏi cách trình bày và cách tiếp nhận thao tác**. MVC được hình thành cho ứng dụng có giao diện tương tác và vòng đời chạy liên tục. Khi chuyển sang web, kiến trúc vẫn giữ mục tiêu phân tách trách nhiệm nhưng phải thích nghi với HTTP, trình duyệt và máy chủ.

## 3. Ba thành phần trong MVC cổ điển

### Model — trạng thái và quy tắc của miền bài toán

Model biểu diễn thông tin mà ứng dụng cần quản lý và các quy tắc chi phối thông tin đó. Tùy hệ thống, Model có thể bao gồm đối tượng miền, logic nghiệp vụ, trạng thái và các cơ chế truy cập dữ liệu.

Ví dụ trong ứng dụng quản lý sách, các khái niệm như Sách, Tác giả, trạng thái mượn và quy tắc không cho mượn một cuốn sách đã được mượn thuộc miền nghiệp vụ. Model không nên phụ thuộc vào màu sắc nút bấm hay cấu trúc HTML của một trang cụ thể.

Model không đồng nghĩa với một lớp ánh xạ cơ sở dữ liệu. Một entity chỉ chứa các trường dữ liệu có thể là một phần của Model, nhưng quy tắc nghiệp vụ và các hành vi của miền cũng cần được đặt ở vị trí phù hợp trong mô hình hoặc lớp dịch vụ miền.

### View — cách trình bày trạng thái

View chịu trách nhiệm chuyển dữ liệu cần thiết thành thứ người dùng có thể quan sát, chẳng hạn cửa sổ, bảng, biểu mẫu hoặc trang HTML. Một Model có thể có nhiều View: danh sách sách, trang chi tiết sách và báo cáo tồn kho có thể trình bày cùng dữ liệu theo các mục đích khác nhau.

View nên tập trung vào trình bày. Nếu View tự quyết định một giao dịch có hợp lệ hay không, hoặc tự thực hiện quy tắc nghiệp vụ quan trọng, trách nhiệm sẽ bị phân tán và khó kiểm thử.

### Controller — tiếp nhận và điều phối tương tác

Controller diễn giải thao tác từ người dùng, xác định hành động cần thực hiện và điều phối Model cùng View. Trong ứng dụng đồ họa cổ điển, Controller có thể nhận sự kiện chuột hoặc bàn phím. Trong ứng dụng web, Controller thường nhận một HTTP request đã được định tuyến.

Controller có thể đọc dữ liệu đầu vào, gọi nghiệp vụ, xử lý kết quả và chọn phản hồi. Controller nên giữ vai trò điều phối; những quy tắc phức tạp nên được đặt trong Model hoặc lớp nghiệp vụ phù hợp để có thể tái sử dụng và kiểm thử độc lập.

### Mối quan hệ giữa ba thành phần

Có thể hình dung trách nhiệm cơ bản như sau:

~~~mermaid
flowchart LR
    U[Người dùng] -->|Thao tác| C[Controller]
    C -->|Gọi hành vi / cập nhật| M[Model]
    M -->|Trạng thái hoặc dữ liệu| V[View]
    V -->|Hiển thị| U
~~~

Đây là sơ đồ khái niệm, không phải quy định rằng mọi triển khai MVC đều phải có đúng một chiều gọi như hình. Trong các biến thể khác nhau, View có thể quan sát thay đổi của Model, Controller có thể chọn View, hoặc framework có thể đảm nhận một phần điều phối. Điều quan trọng là ranh giới trách nhiệm vẫn rõ ràng.

## 4. Vì sao MVC phải thay đổi khi đi lên web?

Ứng dụng desktop cổ điển thường chạy trong một tiến trình liên tục. Giao diện có thể giữ trạng thái trong bộ nhớ, nhận sự kiện rồi cập nhật ngay trên màn hình. Ứng dụng web truyền thống lại hoạt động qua mô hình request–response:

1. Trình duyệt gửi một HTTP request đến máy chủ.
2. Máy chủ định tuyến request đến thành phần xử lý phù hợp.
3. Ứng dụng đọc dữ liệu đầu vào, thực hiện nghiệp vụ và có thể truy cập cơ sở dữ liệu.
4. Máy chủ trả về HTTP response, thường là HTML, redirect hoặc dữ liệu JSON.
5. Trình duyệt nhận response và cập nhật trang hoặc giao diện.

HTTP về cơ bản là giao thức không lưu trạng thái giữa các request. Máy chủ không thể mặc định rằng request tiếp theo đến từ cùng người dùng sẽ tiếp tục trong cùng một luồng xử lý hay cùng một đối tượng Controller còn nằm trong bộ nhớ. Vì thế, MVC trên web phải xác định rõ dữ liệu nào nằm trong request, dữ liệu nào được lưu bền vững, dữ liệu nào thuộc session hoặc cookie, và dữ liệu nào do trình duyệt quản lý.

Sự thay đổi này tạo ra khác biệt quan trọng: Controller web thường xử lý một request hoặc một hành động cụ thể rồi kết thúc. Trạng thái cần tồn tại lâu hơn phải được lưu ở nơi có chủ đích, ví dụ cơ sở dữ liệu, session, token hoặc phía client. Không nên dùng biến instance của Controller làm nơi giữ trạng thái riêng cho từng người dùng nếu framework có thể dùng chung Controller giữa nhiều request.

## 5. MVC trong ứng dụng web phía máy chủ

Trong mô hình web phía máy chủ, trình duyệt gửi request và máy chủ tạo response. Các framework web thường cung cấp router, cơ chế ánh xạ request đến Controller, công cụ binding dữ liệu, validation và bộ máy render View.

Một luồng đọc danh sách sách có thể diễn ra như sau:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant R as Router
    participant C as BookController
    participant S as BookService
    participant D as Repository
    participant V as View
    B->>R: GET /books
    R->>C: Gọi action list
    C->>S: Yêu cầu danh sách sách
    S->>D: Truy vấn dữ liệu
    D-->>S: Các bản ghi sách
    S-->>C: Dữ liệu cần trình bày
    C->>V: Render view với model dữ liệu
    V-->>B: HTML response
~~~

Trong ví dụ này, **Router** chọn Controller/action dựa trên URL và HTTP method. Router là cơ chế định tuyến của ứng dụng, không phải thành phần thứ tư bắt buộc của định nghĩa MVC cổ điển. **BookController** tiếp nhận request và điều phối use case. **BookService** chứa hoặc gọi các quy tắc nghiệp vụ của trường hợp sử dụng. **Repository** chịu trách nhiệm truy cập dữ liệu; đây là cách tổ chức thường gặp trong ứng dụng web, không phải một trong ba thành phần gốc của MVC. **View** kết hợp dữ liệu với mẫu trình bày để tạo HTML.

Việc có thêm Service và Repository không làm mất MVC. Đây là cách phân chia sâu hơn bên trong phần xử lý và dữ liệu để Controller không phải chứa toàn bộ logic.

### Ví dụ: xử lý một biểu mẫu tạo sách

Khi người dùng gửi biểu mẫu tạo sách, trình duyệt có thể gửi:

~~~http
POST /books
Content-Type: application/x-www-form-urlencoded

title=Clean+Architecture&author=Robert+Martin
~~~

Một Controller có thể được tổ chức ở mức khái niệm như sau:

~~~java
@Controller
@RequestMapping("/books")
public class BookController {
    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @PostMapping
    public String create(
            @Valid @ModelAttribute CreateBookForm form,
            BindingResult errors) {
        if (errors.hasErrors()) {
            return "books/new";
        }

        bookService.create(form);
        return "redirect:/books";
    }
}
~~~

Đây là ví dụ theo phong cách Spring MVC. `@Controller` đánh dấu thành phần tiếp nhận request; `@PostMapping` ánh xạ HTTP POST; `@Valid` kích hoạt kiểm tra dữ liệu theo các ràng buộc đã khai báo; `BindingResult` chứa lỗi binding và validation. Khi dữ liệu không hợp lệ, Controller trả lại View biểu mẫu để người dùng sửa. Khi hợp lệ, Controller gọi nghiệp vụ và chuyển hướng đến danh sách.

Ví dụ này cũng cho thấy MVC web phải xử lý những việc ít nổi bật trong ứng dụng desktop: binding dữ liệu từ request, kiểm tra đầu vào, chọn status hoặc redirect phù hợp, và tránh xử lý lại biểu mẫu khi người dùng tải lại trang. Quy tắc nghiệp vụ như kiểm tra mã sách có bị trùng hay không vẫn cần được thực thi ở lớp nghiệp vụ hoặc miền, kể cả khi dữ liệu đã vượt qua validation ở biểu mẫu.

## 6. Các cách triển khai MVC trên web

MVC trên web không chỉ có một hình thức. Cùng một mục tiêu phân tách trách nhiệm có thể được triển khai theo nhiều cách.

| Cách triển khai | Cách tổ chức | Đặc điểm |
|---|---|---|
| MVC phía máy chủ với trang render | Controller xử lý request, Model cung cấp dữ liệu, View template tạo HTML | Máy chủ trả về trang HTML hoàn chỉnh hoặc một phần HTML |
| Model 2 với Servlet/JSP | Servlet thường đóng vai trò Controller; JavaBean hoặc lớp miền giữ dữ liệu; JSP trình bày | Cách tổ chức phổ biến trong ứng dụng Java web truyền thống |
| Front Controller | Nhiều request đi qua một điểm vào chung rồi được định tuyến đến handler phù hợp | Tập trung xử lý chung như xác thực, logging và điều phối |
| MVC ở phía trình duyệt | JavaScript quản lý Model, View và Controller trong ứng dụng chạy ở client | Giao diện có thể cập nhật mà không tải lại toàn bộ trang |
| Ứng dụng kết hợp | Máy chủ render trang ban đầu, client xử lý một số tương tác và gọi API | Phân chia trách nhiệm giữa server và browser tùy nhu cầu |

Trong Java web, mô hình Model 2 thường được nhắc đến khi giải thích MVC phía máy chủ: Servlet xử lý request và điều phối, còn JSP hiển thị kết quả. Các framework hiện đại có thể cung cấp một Front Controller chung, sau đó định tuyến đến Controller chuyên biệt. Nhờ đó, xử lý xuyên suốt như xác thực, logging và xử lý ngoại lệ có thể được tổ chức tập trung.

Ở ứng dụng một trang (Single-Page Application — SPA), trình duyệt tải ứng dụng JavaScript và quản lý nhiều trạng thái giao diện ở phía client. Các thành phần giao diện có thể đóng vai trò View, phần quản lý trạng thái đóng vai trò Model theo cách hiểu của ứng dụng, còn event handler hoặc controller điều phối tương tác. Tuy vậy, nhiều framework frontend hiện đại dùng component, unidirectional data flow hoặc các mô hình khác thay vì MVC cổ điển. Không nên gọi mọi ứng dụng có Model và View là MVC nếu không có ranh giới và cơ chế điều phối tương ứng.

## 7. So sánh MVC cổ điển và MVC web

| Khía cạnh | Ứng dụng tương tác cổ điển | Ứng dụng web phía máy chủ |
|---|---|---|
| Đầu vào | Sự kiện chuột, bàn phím và sự kiện giao diện | HTTP request, URL, query, path và body |
| Vòng đời xử lý | Tiến trình chạy liên tục, nhận nhiều sự kiện | Mỗi request được tiếp nhận và tạo một response |
| Trạng thái | Thường có thể giữ trong bộ nhớ của tiến trình | Phải xác định rõ trạng thái trong DB, session, cookie, token hoặc client |
| View | Cửa sổ, widget, bảng và biểu mẫu | HTML template, JSON hoặc nội dung phản hồi khác |
| Controller | Điều phối sự kiện giao diện | Điều phối request, nghiệp vụ và response |
| Cập nhật giao diện | Có thể cập nhật trực tiếp khi Model đổi | Thường gửi response mới; AJAX hoặc client rendering có thể cập nhật một phần |
| Điều hướng | Chuyển cửa sổ hoặc chế độ xem | URL, HTTP method, redirect và lịch sử trình duyệt |

Có thể thấy MVC không được bê nguyên xi từ desktop sang web. Ý tưởng phân tách vẫn còn, nhưng cách tiếp nhận tương tác, vòng đời Controller và quản lý trạng thái đã thay đổi theo đặc điểm của môi trường HTTP.

## 8. MVC, REST và kiến trúc nhiều tầng có liên quan thế nào?

MVC là mẫu tổ chức trách nhiệm trong ứng dụng. REST là một phong cách kiến trúc để thiết kế hệ thống phân tán dựa trên tài nguyên và giao thức như HTTP. Một API REST có thể được tổ chức bằng Controller, Model và các lớp nghiệp vụ, nhưng REST không đồng nghĩa với MVC.

Tương tự, kiến trúc nhiều tầng thường chia hệ thống thành các tầng như presentation, application, domain và infrastructure. MVC chủ yếu giúp tổ chức phần tương tác và trình bày; nó có thể được sử dụng bên trong một hệ thống nhiều tầng. Không nên xem Model, View và Controller là ba tầng triển khai tương đương một cách máy móc với mọi sơ đồ layered architecture.

Một ứng dụng web có thể đồng thời dùng MVC cho lớp giao diện, Service để điều phối use case, Repository để truy cập dữ liệu, và API theo nguyên tắc REST để giao tiếp với client. Các khái niệm này giải quyết những vấn đề khác nhau và có thể kết hợp.

## 9. Những nguyên tắc cần giữ khi áp dụng MVC trên web

**Giữ Controller tập trung vào điều phối.** Controller nên chuyển request thành lời gọi nghiệp vụ, sau đó chuyển kết quả thành response. Nếu một action chứa hàng loạt quy tắc nghiệp vụ, truy vấn dữ liệu, định dạng HTML và xử lý quyền truy cập, nó đang gánh quá nhiều trách nhiệm.

**Đặt quy tắc nghiệp vụ ở nơi có thể dùng lại.** Quy tắc như giới hạn số sách được mượn cần được thực thi dù thao tác đến từ biểu mẫu web, API hay tác vụ nền. Không đặt quy tắc quan trọng chỉ trong View hoặc JavaScript phía trình duyệt.

**Xác định ranh giới dữ liệu rõ ràng.** Dữ liệu nhận từ request cần được binding và validation. Dữ liệu trả cho View nên là dữ liệu cần thiết cho mục đích trình bày; không mặc định đưa toàn bộ entity hoặc trường nhạy cảm ra ngoài.

**Xử lý lỗi theo từng lớp.** Lỗi đầu vào có thể được trả về biểu mẫu cùng thông báo phù hợp. Lỗi nghiệp vụ cần được biểu diễn đủ rõ để Controller chọn response phù hợp. Lỗi hệ thống cần được ghi nhận và xử lý tập trung, tránh làm lộ stack trace hoặc thông tin nội bộ cho người dùng.

**Bảo vệ request và dữ liệu.** Việc chia Controller, Model, View không tự động tạo ra bảo mật. Ứng dụng vẫn phải xác thực người dùng, kiểm tra quyền trên từng tài nguyên, chống CSRF với biểu mẫu phù hợp, mã hóa đầu ra để hạn chế XSS, và không tin dữ liệu do client gửi lên.

**Kiểm thử theo trách nhiệm.** Kiểm thử Model hoặc Service cho quy tắc nghiệp vụ; kiểm thử Controller cho binding, điều phối và response; kiểm thử View cho cấu trúc trình bày khi cần; và kiểm thử tích hợp cho luồng request thực tế. Ranh giới MVC rõ ràng giúp xác định kiểm thử nên đặt ở đâu.

## 10. Những hiểu lầm thường gặp

- **“Model chỉ là bảng dữ liệu.”** Model đại diện cho trạng thái và khái niệm của miền bài toán; nó có thể bao gồm hành vi và quy tắc nghiệp vụ.
- **“Controller phải chứa toàn bộ logic.”** Controller là nơi tiếp nhận và điều phối. Logic phức tạp nên được đặt trong thành phần nghiệp vụ có trách nhiệm phù hợp.
- **“View có thể quyết định nghiệp vụ.”** View có thể định dạng hoặc ẩn/hiện phần trình bày, nhưng không phải nơi duy nhất thực thi quy tắc quan trọng.
- **“Mỗi URL bắt buộc phải có một Controller riêng.”** Router có thể ánh xạ nhiều route đến các action trong một Controller; cách chia phụ thuộc vào phạm vi trách nhiệm.
- **“MVC và REST là một.”** MVC tổ chức mã ứng dụng; REST định hướng cách thiết kế giao tiếp tài nguyên.
- **“Dùng framework MVC là tự động có kiến trúc tốt.”** Framework cung cấp cơ chế và quy ước. Chất lượng kiến trúc vẫn phụ thuộc vào cách đặt ranh giới, quản lý trạng thái, bảo vệ dữ liệu và kiểm thử.

## 11. Kết luận

MVC bắt nguồn từ nhu cầu tổ chức ứng dụng tương tác sao cho mô hình dữ liệu, cách trình bày và cách tiếp nhận thao tác có thể phát triển độc lập ở mức hợp lý. Khi áp dụng vào web, MVC thích nghi với giao thức HTTP bằng cách đưa request vào vai trò đầu vào, response vào vai trò đầu ra, và định tuyến vào quá trình chọn Controller. Vòng đời xử lý theo request khiến việc quản lý trạng thái, validation, lỗi, bảo mật và kiểm thử trở thành những phần thiết yếu của thiết kế.

Khi học MVC trong phát triển phần mềm web, hãy luôn lần theo một luồng hoàn chỉnh: request đến từ đâu, thành phần nào tiếp nhận, quy tắc nghiệp vụ được thực thi ở đâu, dữ liệu được lấy hoặc cập nhật thế nào, View hoặc response được tạo ra ra sao, và lỗi được phản hồi như thế nào. Hiểu được luồng này giúp áp dụng MVC có chủ đích thay vì chỉ chia mã thành ba thư mục mang tên Model, View và Controller.
