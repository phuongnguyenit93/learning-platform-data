# Luồng dữ liệu, luồng điều khiển và hướng phụ thuộc trong MVC

Trong module **MODEL_VIEW_CONTROLLER**, người học cần hiểu cách một ứng dụng web tổ chức trạng thái và nghiệp vụ, trình bày dữ liệu, tiếp nhận tương tác, rồi xử lý request xuyên suốt các thành phần. Chủ đề này thuộc chương **Cấu trúc và quan hệ**: nó giải thích ba mối quan hệ thường bị nhầm lẫn trong MVC — dữ liệu đi đâu, quyền điều khiển chuyển cho ai, và mã nguồn được phép phụ thuộc vào thành phần nào.

MVC (Model–View–Controller) chia trách nhiệm thành Model, View và Controller. Tuy vậy, chỉ chia lớp theo ba tên gọi chưa đủ để tạo ra kiến trúc rõ ràng. Ta còn phải xác định hợp đồng dữ liệu giữa các thành phần, ranh giới xử lý biểu mẫu và lỗi, vị trí kiểm tra bảo mật, cũng như cách kiểm thử từng phần.

## 1. Ba khái niệm cần phân biệt

**Luồng dữ liệu (data flow)** mô tả dữ liệu được tạo ra, đọc, biến đổi và chuyển giao như thế nào. Ví dụ: dữ liệu từ biểu mẫu HTTP được chuyển thành lệnh tạo sách, được dùng để cập nhật Model, sau đó kết quả được chuyển thành dữ liệu hiển thị.

**Luồng điều khiển (control flow)** mô tả thành phần nào gọi thành phần nào, tại thời điểm nào và theo điều kiện nào. Ví dụ: bộ định tuyến chuyển request đến Controller; Controller gọi một ca sử dụng; sau khi ca sử dụng hoàn tất, Controller chọn kết quả phản hồi.

**Hướng phụ thuộc (dependency direction)** mô tả mã nguồn của một thành phần cần biết hoặc tham chiếu đến hợp đồng của thành phần nào. Đây là quan hệ ở mức thiết kế và biên dịch. Nó không nhất thiết trùng với chiều gọi hàm khi ứng dụng đang chạy.

| Góc nhìn | Câu hỏi chính | Ví dụ trong MVC |
|---|---|---|
| Luồng dữ liệu | Dữ liệu đi từ đâu đến đâu? | Form request → request DTO → command → Model → view model |
| Luồng điều khiển | Ai chuyển bước xử lý tiếp theo? | Router → Controller → application service → repository |
| Hướng phụ thuộc | Mã nguồn phụ thuộc vào hợp đồng nào? | Controller phụ thuộc vào interface của application service |

Ba góc nhìn có liên quan nhưng không thể thay thế cho nhau. Một lời gọi có thể đi từ Controller vào Model trong lúc chạy, trong khi Controller chỉ phụ thuộc vào một interface được định nghĩa ở tầng ứng dụng. Kết quả dữ liệu có thể đi ngược lại qua các lời gọi trả về mà không làm thay đổi hướng phụ thuộc của mã nguồn.

## 2. Vai trò của Model, View và Controller

| Thành phần | Trách nhiệm chính | Không nên gánh |
|---|---|---|
| **Model** | Biểu diễn trạng thái và quy tắc nghiệp vụ của ứng dụng; cung cấp thao tác đọc, thay đổi và bảo toàn tính hợp lệ của dữ liệu | Nhận biết route HTTP, dựng HTML hoặc xử lý chi tiết giao diện |
| **View** | Trình bày dữ liệu cho người dùng hoặc bên tiêu thụ; hiển thị trạng thái và lỗi theo hợp đồng được cung cấp | Tự quyết định quy tắc nghiệp vụ, quyền truy cập hoặc truy vấn cơ sở dữ liệu tùy tiện |
| **Controller** | Tiếp nhận tương tác/request, chuyển dữ liệu đầu vào thành lời gọi phù hợp, phối hợp xử lý và chọn kết quả phản hồi | Chứa toàn bộ nghiệp vụ, tự quản lý truy vấn phức tạp hoặc trở thành nơi lưu trạng thái lâu dài |

### 2.1. Model không đồng nghĩa với cơ sở dữ liệu

Model là phần mô tả dữ liệu và hành vi có ý nghĩa đối với ứng dụng. Tùy cách tổ chức, Model có thể bao gồm đối tượng miền (domain object), quy tắc nghiệp vụ, dịch vụ miền, hợp đồng truy cập dữ liệu và các mô hình đọc.

Cơ sở dữ liệu chỉ là một nơi lưu trữ. Bảng SQL, ORM entity hoặc bản ghi trả về từ truy vấn không tự động đại diện đầy đủ cho Model. Chẳng hạn, quy tắc “một cuốn sách đã phát hành không được xóa khi còn giao dịch mượn đang mở” là quy tắc nghiệp vụ; nó cần được bảo vệ trong miền hoặc ca sử dụng, chứ không thể chỉ dựa vào nút Xóa bị ẩn trên giao diện.

Trong một ứng dụng nhỏ, Model có thể được triển khai bằng các lớp đơn giản cùng DAO hoặc repository. Khi ứng dụng lớn hơn, nên tách ca sử dụng và cổng truy cập dữ liệu để nghiệp vụ không bị gắn chặt với framework hoặc hệ quản trị cơ sở dữ liệu.

### 2.2. View trình bày theo hợp đồng

View có thể là trang HTML phía máy chủ, giao diện phía trình duyệt, màn hình desktop hoặc bộ tuần tự hóa phản hồi JSON. Điểm chung là View nhận dữ liệu đã được chuẩn bị theo một hợp đồng phù hợp với việc trình bày.

Trong web MVC, Controller thường cung cấp một view model hoặc response DTO. View có thể định dạng ngày tháng, sắp xếp cách hiển thị nhãn và trình bày thông báo; nó không nên tự thực hiện quy tắc như tính giá bán hợp lệ hay quyết định người dùng có quyền sửa bản ghi hay không.

### 2.3. Controller điều phối request

Controller là điểm tiếp nhận tương tác. Với ứng dụng web, framework thường đảm nhiệm việc ánh xạ URL và HTTP method đến action của Controller, binding dữ liệu request, gọi bộ kiểm tra đầu vào và áp dụng các bộ lọc phù hợp.

Controller nên giữ phần điều phối ngắn gọn: xác định đầu vào, gọi đúng ca sử dụng, chuyển kết quả sang dạng phản hồi. Quy tắc nghiệp vụ nên nằm ở Model hoặc ca sử dụng mà Controller gọi đến. Cách tổ chức này giúp cùng một nghiệp vụ có thể được gọi từ HTTP API, tác vụ nền hoặc giao diện khác mà không phải sao chép logic.

## 3. Luồng dữ liệu qua một request web

Hãy xét chức năng quản lý sách. Người dùng mở danh sách sách, sau đó gửi biểu mẫu để tạo một cuốn sách mới.

### 3.1. Đọc dữ liệu

Một request đọc thường đi qua các bước sau:

1. Trình duyệt gửi request, ví dụ **GET /books?page=2**.
2. Router xác định Controller và action tương ứng.
3. Controller đọc tham số đã được binding, kiểm tra quyền truy cập và gọi ca sử dụng truy vấn danh sách.
4. Ca sử dụng lấy dữ liệu qua repository hoặc cổng truy vấn.
5. Kết quả được chuyển thành DTO dành cho việc đọc hoặc view model.
6. Controller trả về view/result; framework dựng HTML hoặc tuần tự hóa JSON.
7. Trình duyệt hiển thị kết quả.

Dữ liệu thường đi từ nơi lưu trữ về phía View. Nhưng luồng điều khiển đi theo các lời gọi từ Router đến Controller, rồi đến ca sử dụng và repository. Đây là lý do không nên dùng từ “luồng” mà không nói rõ đang đề cập đến dữ liệu hay điều khiển.

### 3.2. Ghi dữ liệu từ biểu mẫu

Với request ghi, dữ liệu đầu vào cần được xem là không đáng tin cậy, kể cả khi giao diện đã có kiểm tra JavaScript.

1. View gửi **POST /books** cùng các trường của biểu mẫu.
2. Framework binding request thành request DTO. Dữ liệu sai định dạng hoặc thiếu trường bắt buộc có thể bị từ chối ở bước này.
3. Controller kiểm tra trạng thái đăng nhập, quyền thực hiện và tính hợp lệ ở mức đầu vào.
4. Controller chuyển dữ liệu thành command thể hiện ý định nghiệp vụ, chẳng hạn **CreateBookCommand**.
5. Ca sử dụng kiểm tra quy tắc nghiệp vụ, tạo hoặc thay đổi đối tượng miền và yêu cầu lưu qua repository.
6. Repository adapter thực hiện thao tác với cơ sở dữ liệu trong phạm vi giao dịch thích hợp.
7. Ca sử dụng trả kết quả; Controller quyết định phản hồi thành công, chuyển hướng hoặc trả lỗi.
8. View hiển thị danh sách mới hoặc biểu mẫu kèm thông báo lỗi.

Với form HTML, mô hình **Post/Redirect/Get (PRG)** thường phù hợp: sau khi POST thành công, server trả redirect đến trang GET. Cách này giảm nguy cơ người dùng tải lại trang rồi gửi lại cùng biểu mẫu. Với API, phản hồi có thể là **201 Created** kèm địa chỉ tài nguyên vừa tạo. Hình thức cụ thể tùy hợp đồng HTTP của ứng dụng.

### 3.3. Sơ đồ dữ liệu

Sơ đồ dưới đây mô tả dữ liệu đi qua các bước chính. Mũi tên thể hiện hướng chuyển giao hoặc biến đổi dữ liệu, không phải quy tắc phụ thuộc mã nguồn.

~~~mermaid
flowchart LR
    U["Người dùng"] --> V["View / Form"]
    V --> R["HTTP Request"]
    R --> C["Controller"]
    C --> I["Request DTO / Command"]
    I --> A["Application Service"]
    A --> M["Model / Domain"]
    A --> P["Repository"]
    P --> DB[("Database")]
    DB --> P
    P --> A
    A --> O["Kết quả / Read DTO"]
    O --> C
    C --> VM["View Model / Response DTO"]
    VM --> V2["View / Serializer"]
    V2 --> U
~~~

Trong thực tế, dữ liệu không nhất thiết phải đi qua mọi kiểu đối tượng trên. Một truy vấn đơn giản có thể trả thẳng một read DTO; một ứng dụng nhỏ có thể chưa cần tách application service. Điều quan trọng là mỗi hợp đồng có mục đích rõ ràng và không làm lộ chi tiết nội bộ không cần thiết.

## 4. Luồng điều khiển và các điểm quyết định

Luồng điều khiển thường được khởi đầu bởi một sự kiện: request HTTP, thao tác trên giao diện hoặc thông điệp từ hệ thống khác. Với web MVC đồng bộ, trình tự phổ biến là:

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Browser as Trình duyệt / View
    participant Router as Router
    participant C as Controller
    participant A as Application Service
    participant D as Model / Domain
    participant Repo as Repository Port
    participant DB as Database

    User->>Browser: Gửi biểu mẫu tạo sách
    Browser->>Router: POST /books
    Router->>C: Chuyển request đến action
    C->>C: Binding, kiểm tra đầu vào và quyền
    C->>A: create(CreateBookCommand)
    A->>Repo: Kiểm tra dữ liệu cần thiết
    Repo->>DB: Truy vấn
    DB-->>Repo: Kết quả
    Repo-->>A: Dữ liệu miền
    A->>D: Thực thi quy tắc nghiệp vụ
    D-->>A: Trạng thái hợp lệ hoặc lỗi nghiệp vụ
    A->>Repo: Lưu thay đổi
    Repo->>DB: Ghi trong giao dịch
    DB-->>Repo: Kết quả lưu
    Repo-->>A: Hoàn tất
    A-->>C: Kết quả ca sử dụng
    C-->>Browser: Redirect hoặc HTTP response
    Browser-->>User: Hiển thị kết quả
~~~

Các điểm quyết định quan trọng trong chuỗi này gồm:

- **Route có hợp lệ không?** Nếu không có route phù hợp, request kết thúc bằng phản hồi không tìm thấy.
- **Người gửi đã xác thực chưa?** Nếu chưa, ứng dụng có thể yêu cầu đăng nhập.
- **Người gửi có quyền thao tác trên tài nguyên cụ thể không?** Quyền cần được kiểm tra theo người dùng và tài nguyên, không chỉ dựa trên việc giao diện có hiển thị nút thao tác.
- **Dữ liệu đầu vào có đúng cấu trúc không?** Lỗi binding hoặc validation được trả về theo hợp đồng của form/API.
- **Quy tắc nghiệp vụ có được thỏa mãn không?** Model hoặc ca sử dụng có thể từ chối thao tác dù request đúng định dạng.
- **Lưu trữ có thành công không?** Lỗi hạ tầng cần được xử lý ở ranh giới phù hợp và chuyển thành phản hồi an toàn.

Không phải request nào cũng chạy qua cùng một nhánh. Middleware, filter, interceptor hoặc bộ xử lý ngoại lệ có thể chạy trước, sau hoặc bao quanh action. Các cơ chế này thường dùng cho xác thực, ghi log, đo thời gian, xử lý giao dịch hoặc ánh xạ lỗi. Chúng bổ sung cho MVC, không thay thế trách nhiệm của Model, View và Controller.

### 4.1. Phân biệt lời gọi đồng bộ và sự kiện bất đồng bộ

Trong ví dụ trên, Controller gọi ca sử dụng và chờ kết quả. Một số ứng dụng dùng sự kiện hoặc hàng đợi cho công việc kéo dài, chẳng hạn gửi email sau khi tạo đơn hàng. Khi đó, ca sử dụng có thể ghi dữ liệu và phát một sự kiện; worker xử lý email sau đó.

Sự kiện bất đồng bộ làm thay đổi thời điểm hoàn tất và cách báo lỗi. Phản hồi HTTP có thể chỉ xác nhận yêu cầu đã được tiếp nhận, trong khi công việc nền vẫn đang chạy. Cần thiết kế trạng thái xử lý, retry và tính lặp an toàn (idempotency) rõ ràng; không nên khiến View giả định rằng mọi tác vụ nền đã hoàn thành ngay khi nhận phản hồi.

## 5. Hướng phụ thuộc giữa các thành phần

Luồng điều khiển khi chạy không tự động quyết định hướng phụ thuộc của mã nguồn. Ví dụ, framework gọi Controller thông qua route và cơ chế khởi tạo đối tượng. Controller có thể gọi một interface của tầng ứng dụng; lúc chạy, dependency injection cung cấp một lớp triển khai cụ thể. Vì thế, thành phần gọi ở runtime và thành phần mà mã nguồn tham chiếu không nhất thiết là một.

Trong một ứng dụng web MVC có tách tầng, có thể tổ chức quan hệ phụ thuộc như sau:

~~~mermaid
flowchart TB
    subgraph Presentation["Tầng trình bày"]
        Router["Framework / Router"] --> Controller["Controller"]
        Controller --> AppContract["Application Service Interface"]
        Controller --> VM["View Model"]
        View["View / Template"] --> VM
    end

    subgraph Application["Tầng ứng dụng và miền"]
        AppService["Application Service"] --> Domain["Domain Model"]
        AppService --> RepoPort["Repository Interface"]
        AppService -. "implements" .-> AppContract
    end

    subgraph Infrastructure["Tầng hạ tầng"]
        RepoAdapter["Repository Adapter"] -. "implements" .-> RepoPort
        RepoAdapter --> Database[("Database")]
    end
~~~

Trong sơ đồ này, mũi tên liền biểu diễn mã nguồn tham chiếu đến một hợp đồng hoặc thành phần; mũi tên nét đứt biểu diễn quan hệ triển khai interface. Đây là một cách tổ chức phổ biến, không phải cấu trúc bắt buộc của mọi biến thể MVC.

### 5.1. Các quy tắc phụ thuộc hữu ích

- Controller có thể phụ thuộc vào hợp đồng của ca sử dụng hoặc dịch vụ ứng dụng để yêu cầu thực hiện một hành động.
- View phụ thuộc vào hợp đồng dữ liệu trình bày, chẳng hạn view model. View không cần biết dữ liệu được lấy từ bảng nào hoặc repository nào.
- Ca sử dụng có thể phụ thuộc vào Model và interface repository. Adapter cụ thể chịu trách nhiệm giao tiếp với database hoặc dịch vụ bên ngoài.
- Model miền không nên import Controller, View, route HTTP hoặc lớp giao diện. Quy tắc nghiệp vụ cần tồn tại được ngay cả khi thay giao diện web bằng một giao diện khác.
- Chi tiết framework nên được giữ ở ranh giới tích hợp. Nếu đối tượng miền phải kế thừa lớp Controller hoặc sử dụng kiểu request HTTP để thực hiện quy tắc nghiệp vụ, ranh giới đã bị đảo lộn.

Với MVC cổ điển, View có thể đọc Model trực tiếp hoặc đăng ký nhận thông báo khi Model thay đổi. Trong một số framework web, Controller chuẩn bị dữ liệu rồi chuyển cho template. Những biến thể này khác nhau về cách phối hợp runtime, nhưng vẫn nên giữ nguyên tắc: nghiệp vụ không phụ thuộc vào cách trình bày.

### 5.2. Không nhầm hướng phụ thuộc với chiều dữ liệu trả về

Giả sử Controller gọi **books.findAll()** trên interface **BookApplicationService**. Kết quả danh sách được trả từ tầng ứng dụng về Controller rồi được chuyển cho View. Dữ liệu đi theo chiều trả về của lời gọi.

Tuy nhiên, mã nguồn Controller chỉ cần biết interface **BookApplicationService**. Nếu interface này thuộc tầng ứng dụng và lớp triển khai được đăng ký qua dependency injection, Controller không cần tham chiếu trực tiếp đến repository adapter hoặc database driver. Chiều dữ liệu trả về không làm Controller phụ thuộc ngược vào hạ tầng.

Tương tự, repository adapter có thể phụ thuộc vào interface repository để triển khai nó. Tầng ứng dụng gọi interface; tại runtime, đối tượng được inject là adapter cụ thể. Đây là cách giữ cho chính sách nghiệp vụ ổn định khi thay công nghệ lưu trữ.

## 6. Thiết kế hợp đồng dữ liệu

Mỗi ranh giới nên có kiểu dữ liệu phù hợp với mục đích. Trong ứng dụng quản lý sách, có thể phân biệt:

| Hợp đồng | Vai trò | Ví dụ trường |
|---|---|---|
| Request DTO | Nhận dữ liệu từ HTTP; phản ánh cấu trúc đầu vào bên ngoài | **title**, **author** |
| Command | Diễn đạt ý định nghiệp vụ cần thực hiện | **title**, **author** |
| Domain object | Giữ trạng thái và bảo vệ bất biến nghiệp vụ | **Book**, **BookId**, trạng thái phát hành |
| Read DTO | Trả dữ liệu tối ưu cho một truy vấn | **id**, **title**, **author** |
| View model | Cung cấp dữ liệu và trạng thái mà một View cần để trình bày | **books**, **pageTitle**, **message** |
| Response DTO | Định dạng dữ liệu công khai cho API | **id**, **title**, **links** |

Các kiểu này có thể trùng một phần trường, nhưng không nên gộp chúng chỉ vì cấu trúc hiện tại giống nhau. Request DTO là dữ liệu đến từ bên ngoài; domain object phải bảo vệ quy tắc; view model có thể chứa thông tin trình bày; response DTO là cam kết công khai của API. Khi một yêu cầu thay đổi, mỗi hợp đồng có thể thay đổi theo lý do riêng.

### 6.1. Ví dụ Java minh họa

Đoạn mã sau minh họa một Controller mỏng. Các kiểu phản hồi và lớp ứng dụng được rút gọn để tập trung vào ranh giới dữ liệu; import và chi tiết tích hợp framework được lược bỏ.

~~~java
public record CreateBookRequest(String title, String author) {}

public record CreateBookCommand(String title, String author) {}

public record BookRow(long id, String title, String author) {}

public record BookListView(List<BookRow> books, String message) {}

public interface BookApplicationService {
    List<BookRow> findAll();

    void create(CreateBookCommand command);
}

public final class BookController {
    private final BookApplicationService books;

    public BookController(BookApplicationService books) {
        this.books = books;
    }

    public BookListView index() {
        return new BookListView(books.findAll(), null);
    }

    public RedirectResult create(CreateBookRequest request) {
        var command = new CreateBookCommand(
            request.title(),
            request.author()
        );

        books.create(command);
        return RedirectResult.to("/books");
    }
}
~~~

Ở ví dụ này:

- Framework nhận HTTP request và chuyển dữ liệu đã binding thành **CreateBookRequest**.
- Controller chuyển request DTO thành **CreateBookCommand**, rồi gọi interface **BookApplicationService**.
- Application service thực thi quy tắc nghiệp vụ và làm việc với Model/repository.
- **BookRow** là dữ liệu đọc dành cho danh sách; nó không cần là ORM entity.
- **BookListView** là hợp đồng mà View sử dụng để hiển thị trang.

Trong mã thực tế, cần xử lý trường hợp request không hợp lệ, quyền truy cập, lỗi nghiệp vụ và lỗi hạ tầng. Có thể dùng Bean Validation ở biên HTTP, nhưng ca sử dụng vẫn phải bảo vệ quy tắc nghiệp vụ vì nó có thể được gọi từ nhiều điểm vào khác nhau. Không nên tin rằng mọi lời gọi đều đi qua một biểu mẫu đã được kiểm tra.

### 6.2. Chọn mức chuyển đổi vừa đủ

Chuyển đổi giữa request DTO, command, domain object và view model giúp ranh giới rõ ràng, nhưng mỗi lớp chuyển đổi cũng có chi phí. Không cần tạo một kiểu mới cho mọi bước nếu hai hợp đồng thực sự có cùng vòng đời và cùng ý nghĩa.

Nên tách kiểu dữ liệu khi có ít nhất một khác biệt có ý nghĩa: mức độ tin cậy, quyền sở hữu, quy tắc validation, khả năng thay đổi, mức độ công khai hoặc mục đích trình bày. Tránh cả hai cực đoan: dùng một ORM entity cho mọi tầng, hoặc tạo nhiều DTO giống hệt nhau mà không có lý do.

## 7. Biểu mẫu, lỗi và bảo mật ở đúng ranh giới

Luồng request cần xử lý dữ liệu không hợp lệ và truy cập trái phép một cách nhất quán.

### 7.1. Kiểm tra dữ liệu ở nhiều mức

- **Binding và validation đầu vào:** kiểm tra kiểu, định dạng, trường bắt buộc, giới hạn độ dài và cấu trúc request. Ví dụ, trang tạo sách yêu cầu tiêu đề không rỗng.
- **Quy tắc nghiệp vụ:** kiểm tra điều kiện phụ thuộc trạng thái miền. Ví dụ, không cho phép tạo mã ISBN đã tồn tại nếu nghiệp vụ yêu cầu duy nhất.
- **Ràng buộc lưu trữ:** database có thể bảo vệ tính duy nhất, khóa ngoại và các ràng buộc đồng thời. Đây là lớp bảo vệ cuối cùng cho tính toàn vẹn dữ liệu, không thay thế validation và quy tắc miền.

Khi dữ liệu không hợp lệ, phản hồi nên chỉ rõ trường hoặc điều kiện bị từ chối theo cách người dùng có thể xử lý. Không trả stack trace, câu lệnh SQL hoặc thông tin nhạy cảm ra View.

### 7.2. Kiểm tra xác thực và phân quyền

Xác thực trả lời câu hỏi “ai đang gửi request?”. Phân quyền trả lời “người này có được thực hiện hành động trên tài nguyên này không?”. Kiểm tra quyền phải dựa trên danh tính và tài nguyên thực tế. Việc ẩn nút sửa hoặc xóa trong View chỉ cải thiện trải nghiệm; người dùng vẫn có thể gửi HTTP request trực tiếp.

Với thao tác thay đổi dữ liệu qua cookie session, cần áp dụng biện pháp chống CSRF phù hợp với framework. Khi hiển thị dữ liệu do người dùng nhập, View phải escape đầu ra theo ngữ cảnh để hạn chế XSS. Không đưa bí mật, token hoặc dữ liệu cá nhân không cần thiết vào view model hay log.

### 7.3. Giao dịch và lỗi

Một ca sử dụng ghi dữ liệu thường là ranh giới thích hợp để xác định giao dịch: hoặc toàn bộ thay đổi cần thiết được lưu thành công, hoặc trạng thái được rollback theo chính sách. Không nên mở giao dịch quá rộng rồi giữ nó trong lúc chờ người dùng hoặc gọi dịch vụ ngoài chậm.

Lỗi cần được ánh xạ tại ranh giới phù hợp. Lỗi đầu vào có thể quay lại form cùng thông báo; lỗi không tìm thấy có thể thành HTTP 404; xung đột nghiệp vụ có thể được biểu diễn bằng HTTP 409 hoặc mã lỗi miền theo hợp đồng API. Lỗi hệ thống cần được ghi nhận với mã tương quan để điều tra, trong khi phản hồi công khai chỉ cung cấp thông tin an toàn.

## 8. Trạng thái và vòng đời dữ liệu

Không phải mọi dữ liệu đều có cùng vòng đời. Phân biệt rõ các loại trạng thái giúp tránh rò rỉ dữ liệu giữa người dùng và lỗi đồng thời.

- **Trạng thái miền bền vững:** dữ liệu nghiệp vụ cần được lưu, ví dụ sách và trạng thái phát hành.
- **Trạng thái theo request:** dữ liệu chỉ cần trong một lần xử lý, ví dụ request DTO, kết quả validation và view model.
- **Trạng thái phiên hoặc người dùng:** dữ liệu gắn với phiên đăng nhập hoặc người dùng, ví dụ lựa chọn ngôn ngữ; cần kiểm soát thời hạn và quyền truy cập.
- **Trạng thái giao diện:** dữ liệu tạm thời như tab đang chọn hoặc nội dung chưa lưu, có thể tồn tại ở trình duyệt.

Không lưu dữ liệu riêng của một request vào field mutable dùng chung của Controller hoặc service singleton. Trong server xử lý đồng thời, nhiều request có thể dùng cùng một instance; trạng thái dùng chung không được cô lập có thể làm lẫn dữ liệu giữa người dùng. Nếu cần trạng thái lâu dài, hãy chọn nơi lưu trữ và khóa đồng bộ phù hợp với vòng đời của dữ liệu.

## 9. Những lỗi thiết kế thường gặp

| Dấu hiệu | Hệ quả | Hướng xử lý |
|---|---|---|
| Controller chứa truy vấn và quy tắc nghiệp vụ dài | Khó kiểm thử, khó tái sử dụng nghiệp vụ | Chuyển hành vi vào ca sử dụng hoặc Model phù hợp |
| View tự truy cập database | Trộn trình bày với truy cập dữ liệu, dễ phát sinh truy vấn khó kiểm soát | Cung cấp read DTO hoặc view model từ tầng xử lý |
| Model import kiểu HTTP hoặc lớp giao diện | Nghiệp vụ bị khóa vào một cách trình bày | Đưa kiểu HTTP về biên; dùng kiểu miền hoặc hợp đồng ứng dụng |
| Trả ORM entity trực tiếp ra API/View | Lộ cấu trúc lưu trữ, có thể lộ trường nhạy cảm hoặc gây tải dữ liệu ngoài ý muốn | Dùng response DTO hoặc view model có chủ đích |
| Dùng một DTO cho mọi tầng | Thay đổi API có thể làm ảnh hưởng miền và giao diện | Tách hợp đồng khi ý nghĩa hoặc vòng đời khác nhau |
| Chỉ kiểm tra quyền bằng cách ẩn nút trên View | Request trực tiếp có thể vượt qua giao diện | Kiểm tra quyền ở phía server cho từng tài nguyên và hành động |
| Lưu trạng thái request trong field dùng chung | Request đồng thời có thể ghi đè dữ liệu của nhau | Dùng biến cục bộ, đối tượng theo request hoặc kho trạng thái có kiểm soát |
| Controller gọi trực tiếp nhiều adapter cụ thể | Phụ thuộc hạ tầng lan vào tầng trình bày | Gom thao tác theo ca sử dụng và phụ thuộc vào interface phù hợp |

Một dấu hiệu cần xem xét là **fat controller**: action có nhiều nhánh nghiệp vụ, tự phối hợp nhiều repository, quản lý giao dịch và định dạng kết quả cùng lúc. Có thể bắt đầu bằng cách xác định phần nào là kiểm tra giao thức HTTP, phần nào là quy tắc nghiệp vụ, phần nào là truy cập dữ liệu và phần nào là trình bày; sau đó đặt từng trách nhiệm vào đúng ranh giới.

## 10. Kiểm thử theo luồng và theo hướng phụ thuộc

Có thể kiểm thử MVC ở nhiều mức, mỗi mức xác nhận một loại hợp đồng:

1. **Unit test cho Model/domain:** kiểm tra bất biến và quy tắc nghiệp vụ mà không cần HTTP hoặc database thật.
2. **Test cho application service:** kiểm tra một ca sử dụng gọi đúng cổng cần thiết, xử lý kết quả và lỗi; repository giả có thể được dùng để kiểm soát dữ liệu.
3. **Test cho Controller:** kiểm tra request được binding, validation và quyền được áp dụng, command được tạo đúng, kết quả HTTP hoặc view được chọn phù hợp.
4. **Test cho View:** kiểm tra dữ liệu được trình bày đúng, thông báo lỗi xuất hiện và nội dung đầu vào được escape.
5. **Integration test:** gửi request qua router/framework đến tầng lưu trữ thử nghiệm để xác nhận các hợp đồng hoạt động cùng nhau.

Ngoài test hành vi, có thể kiểm tra quy tắc phụ thuộc bằng công cụ phân tích kiến trúc hoặc kiểm tra package. Ví dụ, package domain không được import package controller, template hoặc adapter cơ sở dữ liệu cụ thể. Loại kiểm tra này giúp ngăn một thay đổi nhỏ vô tình làm đảo chiều phụ thuộc.

Khi điều tra một lỗi, hãy lần theo ba câu hỏi riêng: dữ liệu sai ở bước nào, quyền điều khiển đi vào nhánh nào, và thành phần nào đang phụ thuộc trực tiếp vào chi tiết gây ra lỗi. Cách phân tích này giúp xác định đúng ranh giới cần sửa thay vì chỉ thêm điều kiện vào action hiện tại.

## 11. Checklist khi thiết kế một luồng MVC

- [ ] Mỗi request có route và Controller/action chịu trách nhiệm rõ ràng.
- [ ] Dữ liệu đầu vào có hợp đồng riêng và được kiểm tra ở biên.
- [ ] Quy tắc nghiệp vụ được bảo vệ trong Model hoặc ca sử dụng, kể cả khi có nhiều điểm gọi.
- [ ] Controller điều phối và chọn phản hồi; không ôm toàn bộ nghiệp vụ.
- [ ] View nhận dữ liệu trình bày có chủ đích và không tự truy cập lưu trữ.
- [ ] Hướng phụ thuộc của mã nguồn đi về các hợp đồng ổn định; miền không phụ thuộc vào giao diện hoặc framework web.
- [ ] Phân quyền được kiểm tra ở phía server trên tài nguyên cụ thể.
- [ ] Giao dịch, lỗi và trạng thái được đặt đúng theo vòng đời của ca sử dụng.
- [ ] Có kiểm thử cho quy tắc miền, Controller, View và ít nhất các luồng tích hợp quan trọng.

Khi ba khái niệm được tách bạch, MVC trở thành một cấu trúc có thể giải thích và kiểm tra: luồng dữ liệu cho biết thông tin được chuyển đổi ra sao, luồng điều khiển cho biết request được điều phối thế nào, còn hướng phụ thuộc cho biết mã nguồn có thể thay đổi mà không kéo theo những thành phần nào.
