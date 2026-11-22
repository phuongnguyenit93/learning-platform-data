# Sự khác biệt giữa MVC trên web và MVC tương tác cổ điển

Model–View–Controller (MVC) là cách tổ chức phần mềm thành ba trách nhiệm: quản lý trạng thái và quy tắc của ứng dụng, trình bày thông tin, và tiếp nhận rồi diễn giải tương tác của người dùng. Tuy nhiên, MVC được sử dụng trong nhiều môi trường khác nhau. Một ứng dụng desktop tương tác liên tục với người dùng có vòng đời và cách trao đổi dữ liệu khác với một ứng dụng web xử lý request qua HTTP.

Vì vậy, MVC trên web kế thừa ý tưởng phân tách Model, View và Controller, nhưng cách ba thành phần phối hợp đã thay đổi theo môi trường request–response, trình duyệt, mạng và máy chủ. Hiểu sự khác biệt này giúp thiết kế đúng ranh giới, tránh đưa tư duy của ứng dụng desktop vào Controller web hoặc coi mọi lớp mang tên Model là cùng một loại.

Bài học đặt MVC trên web trong bối cảnh chung của kiến trúc Model–View–Controller, tập trung vào vòng đời tương tác, vai trò của từng thành phần, quản lý trạng thái và cách các framework web hiện thực mô hình này.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Giải thích luồng tương tác liên tục trong MVC cổ điển và luồng request–response trong MVC trên web.
- So sánh vai trò của Model, View và Controller ở hai môi trường.
- Hiểu tác động của HTTP, tính stateless và ranh giới mạng đến vòng đời request.
- Phân biệt Domain Model với đối tượng Model dùng để truyền dữ liệu cho View trong framework web.
- Mô tả cách Controller web định tuyến, binding dữ liệu, gọi nghiệp vụ và chọn phản hồi.
- Nhận biết khi nào ứng dụng web có thêm MVC phía trình duyệt hoặc kiến trúc SPA.
- Chọn cách kiểm thử phù hợp với từng thành phần và luồng tương tác.

## 2. MVC tương tác cổ điển

MVC ra đời trong bối cảnh ứng dụng có giao diện đồ họa và một tiến trình tương tác đang chạy. Người dùng nhấn nút, gõ phím, kéo thả hoặc chọn mục; ứng dụng nhận sự kiện, cập nhật trạng thái và làm mới phần giao diện liên quan.

Trong cách tổ chức cổ điển, ba thành phần thường phối hợp như sau:

- **Model** quản lý trạng thái và quy tắc của ứng dụng. Nó không cần biết trạng thái đó được trình bày bằng cửa sổ, biểu đồ hay bảng.
- **View** đọc trạng thái từ Model và trình bày cho người dùng. Một Model có thể được hiển thị bởi nhiều View.
- **Controller** nhận sự kiện đầu vào và chuyển chúng thành hành động phù hợp trên Model hoặc điều khiển cách View phản hồi.

Một đặc điểm thường gặp là Model thông báo khi trạng thái thay đổi. Các View đang quan sát Model có thể nhận thông báo rồi cập nhật phần hiển thị tương ứng. Cơ chế Observer hoặc publish–subscribe thường được dùng để giảm phụ thuộc trực tiếp giữa Model và View.

### 2.1. Luồng sự kiện trong ứng dụng tương tác

Ví dụ một ứng dụng desktop hiển thị số dư tài khoản. Người dùng nhấn nút làm mới; Controller xử lý sự kiện, yêu cầu Model tải hoặc cập nhật dữ liệu; khi trạng thái thay đổi, View đang quan sát Model cập nhật số dư.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant View as View
    participant Controller as Controller
    participant Model as Model

    User->>View: Nhấn nút làm mới
    View->>Controller: Chuyển sự kiện giao diện
    Controller->>Model: Yêu cầu cập nhật số dư
    Model->>Model: Cập nhật trạng thái
    Model-->>View: Thông báo trạng thái thay đổi
    View->>Model: Đọc số dư mới
    View-->>User: Hiển thị số dư
~~~

Luồng này diễn ra trong cùng ứng dụng hoặc cùng môi trường tiến trình. Không cần tạo một HTTP request cho mỗi lần nhấn nút. View và Controller có thể tồn tại trong suốt thời gian cửa sổ đang mở; Model cũng có thể được nhiều View quan sát.

### 2.2. Model có thể phục vụ nhiều View

Giả sử ứng dụng quản lý kho có một Model chứa số lượng hàng tồn. Cùng một Model có thể được trình bày bằng:

- Một bảng liệt kê số lượng theo sản phẩm.
- Một biểu đồ thể hiện mức tồn theo thời gian.
- Một nhãn cảnh báo khi hàng xuống dưới ngưỡng.
- Một cửa sổ chi tiết của sản phẩm đang chọn.

Khi số lượng tồn thay đổi, các View liên quan có thể được thông báo và cập nhật. Điều này giúp trạng thái nghiệp vụ không bị nhân bản thành nhiều bản riêng trong từng màn hình.

Không phải mọi biến thể MVC cổ điển đều dùng đúng một cơ chế thông báo. Một số thiết kế để View chủ động đọc Model khi cần; một số framework kết hợp Controller và View theo cách riêng. Observer là một cách triển khai phổ biến, không phải điều kiện bắt buộc duy nhất để một thiết kế được gọi là MVC.

### 2.3. Vòng đời và trạng thái

Ứng dụng tương tác cổ điển thường có vòng lặp sự kiện liên tục. Các đối tượng giao diện có thể giữ trạng thái như vị trí con trỏ, mục đang chọn, nội dung chưa lưu, trạng thái focus và trạng thái hoạt ảnh.

Model thường tồn tại trong bộ nhớ của tiến trình hoặc được truy cập qua các đối tượng dịch vụ trong cùng ứng dụng. Dữ liệu có thể được lưu lâu dài xuống tệp hoặc cơ sở dữ liệu, nhưng tương tác trên giao diện không cần khởi tạo lại toàn bộ luồng cho mỗi sự kiện.

Điều này tạo cảm giác phản hồi tức thời: sự kiện đi vào Controller, trạng thái thay đổi, View được cập nhật và người dùng tiếp tục thao tác trên cùng màn hình.

## 3. MVC trên web

Ứng dụng web có thêm ranh giới mạng giữa trình duyệt và máy chủ. Người dùng tương tác với HTML, CSS và JavaScript trong trình duyệt; khi cần trao đổi với máy chủ, trình duyệt gửi HTTP request. Máy chủ xử lý request rồi trả HTTP response.

Trong mô hình MVC web server-rendered phổ biến:

- **Controller** nhận request theo route và HTTP method, chuyển dữ liệu đầu vào thành tham số hoặc đối tượng request, gọi nghiệp vụ và quyết định loại response.
- **Model** đại diện cho dữ liệu và quy tắc nghiệp vụ mà request cần sử dụng. Tùy framework, tên Model có thể chỉ một nhóm đối tượng nghiệp vụ, dữ liệu phục vụ View hoặc toàn bộ phần dữ liệu của ứng dụng.
- **View** thường là template hoặc cơ chế tạo representation. Với giao diện HTML, View kết hợp dữ liệu được cung cấp để tạo HTML gửi về trình duyệt.

Trình duyệt hiển thị response và tiếp tục nhận tương tác. Một thao tác tiếp theo có thể gửi request mới đến máy chủ.

### 3.1. Luồng request–response

Ví dụ người dùng mở trang tạo đơn hàng, nhập dữ liệu rồi gửi biểu mẫu:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant Router as Router / Dispatcher
    participant Controller as Controller
    participant Service as Application Service
    participant Model as Domain Model
    participant View as Template View

    User->>Browser: Mở trang tạo đơn
    Browser->>Router: GET /orders/new
    Router->>Controller: Chuyển request đến action
    Controller->>View: Yêu cầu render form
    View-->>Browser: HTML response
    Browser-->>User: Hiển thị biểu mẫu

    User->>Browser: Nhập dữ liệu và gửi
    Browser->>Router: POST /orders
    Router->>Controller: Chuyển request đến action
    Controller->>Controller: Binding và kiểm tra đầu vào
    Controller->>Service: Gọi ca sử dụng
    Service->>Model: Thực hiện quy tắc nghiệp vụ
    Model-->>Service: Kết quả nghiệp vụ
    Service-->>Controller: Kết quả thao tác
    Controller-->>Browser: Redirect hoặc response
    Browser->>Router: GET trang kết quả (nếu redirect)
    Router->>Controller: Xử lý request mới
    Controller->>View: Chuẩn bị dữ liệu hiển thị
    View-->>Browser: HTML response
    Browser-->>User: Hiển thị kết quả
~~~

Khác với tương tác cổ điển, một lần gửi biểu mẫu tạo thành một request riêng. Máy chủ xử lý request, tạo response rồi hoàn tất lần xử lý đó. Nếu dùng mẫu Post/Redirect/Get (PRG), response sau POST yêu cầu trình duyệt chuyển đến một URL khác bằng GET; GET này là một request mới.

### 3.2. Route và HTTP method xác định điểm vào

Trong ứng dụng desktop, Controller thường nhận sự kiện từ một thành phần giao diện cụ thể như nút hoặc menu. Trong ứng dụng web, router hoặc dispatcher thường quyết định Controller action dựa trên URL, HTTP method và đôi khi cả content type hoặc các điều kiện định tuyến khác.

Ví dụ:

| Request | Mục đích thường gặp | Controller action |
|---|---|---|
| GET /orders | Xem danh sách đơn | Hiển thị danh sách |
| GET /orders/42 | Xem đơn cụ thể | Hiển thị chi tiết |
| GET /orders/new | Mở biểu mẫu | Hiển thị form |
| POST /orders | Tạo đơn mới | Xử lý dữ liệu tạo |
| GET /orders/42/edit | Mở form sửa | Hiển thị form sửa |
| POST /orders/42 hoặc PUT /orders/42 | Cập nhật đơn theo hợp đồng API | Xử lý cập nhật |
| DELETE /orders/42 | Xóa hoặc hủy tài nguyên theo hợp đồng | Xử lý yêu cầu xóa |

Các route chỉ là ví dụ minh họa. Framework có thể hỗ trợ method override từ form HTML hoặc dùng các HTTP method khác nhau tùy quy ước. Điều quan trọng là URL và method tạo nên hợp đồng giao tiếp của điểm vào.

### 3.3. Controller web xử lý một request

Controller web thường thực hiện một chuỗi công việc:

1. Nhận request đã được router chọn.
2. Đọc path variable, query parameter, header, cookie hoặc body theo hợp đồng.
3. Binding dữ liệu vào kiểu tham số hoặc request DTO.
4. Kiểm tra cấu trúc và các ràng buộc đầu vào.
5. Xác thực và kiểm tra quyền truy cập theo cấu hình ứng dụng.
6. Gọi ca sử dụng hoặc application service.
7. Chọn View, redirect hoặc response body thích hợp.
8. Trả response về cho máy khách.

Controller cần giữ vai trò điều phối. Nếu nó tự chứa toàn bộ quy tắc tính giá, chuyển trạng thái, kiểm tra quyền nghiệp vụ và truy cập dữ liệu, Controller sẽ phình to và khó tái sử dụng. Các quy tắc nghiệp vụ nên nằm trong Domain Model hoặc ca sử dụng phù hợp.

## 4. So sánh vai trò Model, View và Controller

Tên ba thành phần được giữ lại, nhưng ngữ cảnh thực thi làm thay đổi cách chúng phối hợp.

| Khía cạnh | MVC tương tác cổ điển | MVC trên web server-rendered |
|---|---|---|
| Điểm vào | Sự kiện bàn phím, chuột, thao tác giao diện | HTTP request được route theo URL và method |
| Controller | Diễn giải sự kiện và điều khiển hành động trong giao diện | Xử lý request, binding, gọi nghiệp vụ và chọn response |
| Model | Trạng thái và quy tắc của ứng dụng trong môi trường tương tác | Dữ liệu và quy tắc nghiệp vụ được dùng khi xử lý request; có thể phối hợp repository/service |
| View | Đối tượng giao diện đang hoạt động và đọc trạng thái Model | Template hoặc bộ tạo representation, thường tạo HTML cho response |
| Cập nhật View | Có thể nhận thông báo từ Model và cập nhật trực tiếp | Thường render response mới; cập nhật một phần qua AJAX hoặc cơ chế realtime |
| Giao tiếp | Thường nằm trong cùng tiến trình | Có ranh giới mạng giữa client và server |
| Vòng đời | Có thể kéo dài theo cửa sổ hoặc phiên tương tác | Mỗi request có vòng đời xử lý riêng; browser giữ phiên tương tác |
| Trạng thái tạm | Có thể giữ trực tiếp trong đối tượng giao diện hoặc Model | Phải quản lý rõ ở browser, session, token, server hoặc kho dữ liệu |
| Phản hồi | Thường diễn ra trong vòng lặp sự kiện | Phụ thuộc round trip mạng và thời gian xử lý server |

Bảng này mô tả hai dạng phổ biến. Các framework và biến thể MVC có thể phân chia trách nhiệm khác nhau. Khi đọc một framework cụ thể, cần xem luồng thực thi và hợp đồng của framework thay vì chỉ dựa vào tên lớp.

## 5. Những thay đổi quan trọng khi chuyển sang môi trường web

### 5.1. Sự kiện giao diện được chuyển thành request

Trong ứng dụng tương tác cổ điển, một lần nhấn nút có thể gọi trực tiếp một phương thức của Controller trong cùng tiến trình. Trong ứng dụng web, trình duyệt có thể xử lý một số sự kiện hoàn toàn ở phía client; nếu cần máy chủ thực hiện nghiệp vụ, trình duyệt gửi request.

Ví dụ:

- Chọn một tab có thể chỉ thay đổi giao diện trong trình duyệt.
- Nhập nội dung vào ô tìm kiếm có thể lọc danh sách ở client.
- Nhấn “Lưu đơn hàng” thường gửi POST đến máy chủ.
- Nhấn “Hủy đơn” gửi request để máy chủ kiểm tra quyền và trạng thái rồi thực hiện nghiệp vụ.

Không phải mọi sự kiện trong trình duyệt đều cần một request. Việc phân biệt thao tác trình bày với thao tác cần dữ liệu hoặc quy tắc từ máy chủ giúp giảm round trip và giữ trách nhiệm đúng chỗ.

### 5.2. HTTP là stateless ở cấp giao thức

HTTP không tự duy trì trạng thái nghiệp vụ giữa hai request. Máy chủ không thể mặc nhiên giả định request tiếp theo đến từ cùng người dùng, cùng cửa sổ hoặc cùng đối tượng Controller đã xử lý request trước.

Nếu cần duy trì trạng thái giữa các lần tương tác, ứng dụng phải lựa chọn cơ chế rõ ràng:

- **Cơ sở dữ liệu:** lưu dữ liệu nghiệp vụ lâu dài như đơn hàng, hồ sơ và trạng thái quy trình.
- **Session:** giữ một lượng trạng thái tạm gắn với phiên người dùng, thường thông qua session cookie.
- **Cookie:** lưu một số thông tin phía trình duyệt theo chính sách bảo mật và dung lượng phù hợp.
- **Token:** mang thông tin xác thực hoặc tham chiếu đến trạng thái theo thiết kế của hệ thống.
- **Hidden field hoặc URL:** truyền dữ liệu cần thiết giữa các bước, nhưng mọi giá trị vẫn phải được xem là dữ liệu không đáng tin cậy và kiểm tra lại.
- **Browser state:** giữ trạng thái giao diện như tab đang chọn, nội dung đang gõ hoặc mục đang mở.

Stateless của HTTP không có nghĩa ứng dụng web không có trạng thái. Nó có nghĩa giao thức không tự giữ ngữ cảnh nghiệp vụ giữa các request; ứng dụng cần tái tạo hoặc tra cứu ngữ cảnh đó một cách có chủ đích.

### 5.3. Vòng đời Controller và đối tượng dùng chung

Trong một số ứng dụng cổ điển, Controller có thể tồn tại cùng View và giữ thông tin của phiên tương tác. Trong framework web, một action thường được gọi để xử lý một request cụ thể.

Cần lưu ý rằng vòng đời object Controller phụ thuộc framework. Chẳng hạn, Spring MVC mặc định quản lý Controller dưới dạng singleton; cùng một instance có thể phục vụ nhiều request đồng thời. Vì vậy, không lưu dữ liệu riêng của request hoặc người dùng vào mutable instance field của Controller. Dữ liệu của request nên nằm trong tham số phương thức, đối tượng cục bộ hoặc thành phần có scope và đồng bộ phù hợp.

### 5.4. View web thường là một representation được tạo ra

Trong MVC tương tác cổ điển, View thường là đối tượng giao diện sống trong bộ nhớ và cập nhật khi Model thay đổi. Trong server-side web MVC, template thường được thực thi để tạo ra một response HTML. Khi request kết thúc, lần render đó đã hoàn tất; trình duyệt nhận HTML và xây dựng DOM để hiển thị.

Nếu Model thay đổi sau đó, trang HTML đã gửi không tự động thay đổi. Trình duyệt cần gửi request mới, tải dữ liệu mới, hoặc nhận thông tin qua một cơ chế realtime như WebSocket hay Server-Sent Events.

Điều này giải thích vì sao một trang web server-rendered thường được xem như ảnh chụp của dữ liệu tại thời điểm response được tạo, thay vì một View đang quan sát trực tiếp object Model ở máy chủ.

### 5.5. Ranh giới mạng làm thay đổi cách xử lý lỗi

Trong cùng tiến trình desktop, Controller có thể nhận được exception hoặc kết quả phương thức ngay lập tức. Trong web, request có thể gặp timeout, mất kết nối, bị gửi lại hoặc nhận response lỗi từ máy chủ.

Ứng dụng cần phân biệt:

- Lỗi dữ liệu đầu vào.
- Lỗi quy tắc nghiệp vụ.
- Lỗi xác thực hoặc phân quyền.
- Xung đột do trạng thái đã thay đổi.
- Lỗi mạng hoặc lỗi hạ tầng.

Với thao tác ghi dữ liệu, cần xem xét request lặp, giao dịch và tính idempotent. Việc trình duyệt không nhận được response không chứng minh máy chủ chưa thực hiện thao tác.

## 6. Ví dụ MVC web với Spring MVC

Spring MVC là một ví dụ về mô hình Controller nhận HTTP request, phối hợp với tầng nghiệp vụ và chọn template hoặc response body. Ví dụ dưới đây minh họa một luồng tạo đơn hàng server-rendered.

~~~java
import java.util.UUID;

import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/orders")
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/new")
    public String showForm(org.springframework.ui.Model viewModel) {
        viewModel.addAttribute("form", new CreateOrderForm());
        return "orders/new";
    }

    @PostMapping
    public String create(
            @Valid @ModelAttribute("form") CreateOrderForm form,
            BindingResult errors,
            org.springframework.ui.Model viewModel) {

        if (errors.hasErrors()) {
            return "orders/new";
        }

        OrderId id = orderService.create(
            new CreateOrderCommand(form.getProductCode(), form.getQuantity())
        );

        return "redirect:/orders/" + id.value();
    }

    @GetMapping("/{id}")
    public String show(
            @PathVariable UUID id,
            org.springframework.ui.Model viewModel) {

        viewModel.addAttribute("order", orderService.getDetails(id));
        return "orders/detail";
    }
}
~~~

Các kiểu CreateOrderForm, CreateOrderCommand, OrderId và OrderService đại diện cho các hợp đồng hoặc thành phần ứng dụng được lược bỏ phần khai báo để tập trung vào luồng MVC.

Có thể đọc ví dụ theo từng bước:

- GET /orders/new yêu cầu Controller chuẩn bị dữ liệu để hiển thị biểu mẫu.
- Template orders/new tạo HTML và trả về trình duyệt.
- POST /orders gửi dữ liệu biểu mẫu đến action create.
- Binding và validation kiểm tra dữ liệu trước khi gọi nghiệp vụ.
- OrderService thực hiện ca sử dụng và trả về định danh đơn hàng.
- Controller redirect sang URL chi tiết.
- GET /orders/{id} đọc dữ liệu cần thiết và render trang chi tiết.

Trong ví dụ này, tham số org.springframework.ui.Model là một đối tượng mang thuộc tính cho View. Nó không đồng nghĩa với Domain Model của nghiệp vụ. Đặt tên biến là viewModel giúp tránh nhầm lẫn khi đọc mã.

Controller có thể trả về tên template, redirect hoặc response body tùy loại endpoint. Với API, một action có thể trả DTO JSON thay vì tên View HTML. Ý tưởng phân tách trách nhiệm vẫn hữu ích dù representation không phải trang HTML.

## 7. MVC phía trình duyệt và ứng dụng SPA

Ứng dụng web hiện đại không phải lúc nào cũng render toàn bộ HTML ở máy chủ. Một SPA (Single-Page Application) thường tải một shell HTML và JavaScript ban đầu; sau đó client điều khiển điều hướng, cập nhật DOM và gửi request đến API để lấy hoặc ghi dữ liệu.

Trong trường hợp này có thể tồn tại hai ranh giới MVC hoặc các biến thể gần với MVC:

1. **Phía server:** Controller/API endpoint nhận HTTP request, gọi nghiệp vụ và trả JSON hoặc representation khác.
2. **Phía browser:** thành phần giao diện nhận sự kiện người dùng, cập nhật client-side state và render lại vùng giao diện.

~~~mermaid
flowchart LR
    subgraph Browser["Trình duyệt"]
        View["View / Components"]
        ClientController["Client Controller / Router"]
        ClientState["Client State"]
        View -->|"Sự kiện người dùng"| ClientController
        ClientController -->|"Cập nhật"| ClientState
        ClientState -->|"Render"| View
    end

    subgraph Server["Máy chủ"]
        Route["API Router"]
        ApiController["API Controller"]
        UseCase["Application Service"]
        Domain["Domain Model"]
        Route --> ApiController
        ApiController --> UseCase
        UseCase --> Domain
    end

    ClientController <-->|"HTTP request / JSON response"| Route
~~~

Một số điểm cần phân biệt:

- Client-side state có thể chứa dữ liệu phục vụ giao diện, nhưng không phải nguồn đáng tin cậy cho quy tắc bảo mật hoặc nghiệp vụ.
- API Controller vẫn cần xác thực, phân quyền, kiểm tra dữ liệu và gọi ca sử dụng.
- Browser View có thể cập nhật ngay khi state thay đổi mà không cần tải lại toàn bộ trang.
- Dữ liệu quan trọng vẫn cần được xác nhận và lưu ở phía máy chủ.
- Không phải mọi SPA đều tổ chức theo MVC; nhiều ứng dụng dùng MVVM, Flux, Redux hoặc cách tổ chức component khác.

SPA không làm mất đi request–response của HTTP khi gọi API. Nó bổ sung một vòng lặp tương tác phía trình duyệt, trong khi giao tiếp giữa browser và server vẫn đi qua ranh giới mạng.

## 8. So sánh cách quản lý trạng thái

Trạng thái là một trong những khác biệt có ảnh hưởng lớn nhất đến thiết kế.

| Loại trạng thái | Ứng dụng tương tác cổ điển | Ứng dụng web |
|---|---|---|
| Trạng thái nghiệp vụ | Có thể nằm trong Model trong bộ nhớ và được lưu lâu dài khi cần | Thường được đọc/ghi qua application service và kho dữ liệu |
| Trạng thái giao diện | Nằm trong đối tượng View hoặc Controller | Nằm trong DOM, JavaScript state, form hoặc URL |
| Trạng thái đăng nhập | Có thể gắn với phiên ứng dụng đang chạy | Cookie/session hoặc token theo cơ chế xác thực |
| Trạng thái nhiều bước | Có thể được giữ trong đối tượng phiên tương tác | Session, database draft, token hoặc dữ liệu client có kiểm tra |
| Trạng thái đồng thời | Thường được xử lý trong tiến trình hoặc qua đồng bộ hóa | Nhiều request và nhiều người dùng có thể cập nhật cùng tài nguyên |
| Trạng thái sau khi đóng giao diện | Có thể mất nếu chưa lưu | Có thể được khôi phục từ server, URL hoặc browser storage tùy thiết kế |

Một ứng dụng web không nên coi session là nơi lưu mọi dữ liệu nghiệp vụ. Session phù hợp với một số trạng thái tạm và ngữ cảnh người dùng, nhưng dữ liệu quan trọng cần có chính sách lưu trữ, phân quyền, hết hạn và đồng bộ riêng.

Tương tự, không nên tin dữ liệu client gửi lại chỉ vì máy chủ từng tạo nó. Hidden field, query parameter và local storage đều có thể bị sửa. Máy chủ cần kiểm tra quyền, trạng thái và tính hợp lệ tại thời điểm xử lý.

## 9. Hệ quả đối với thiết kế và kiểm thử

### 9.1. Phân chia trách nhiệm

Khi thiết kế web MVC:

- Giữ Controller tập trung vào HTTP, binding, điều phối và lựa chọn response.
- Đặt quy tắc nghiệp vụ trong Domain Model hoặc ca sử dụng.
- Dùng DTO hoặc form model để định nghĩa dữ liệu được phép nhận và trả.
- Dùng View hoặc template để trình bày dữ liệu.
- Dùng repository hoặc adapter phù hợp để truy cập dữ liệu lưu trữ.
- Không lưu trạng thái request hoặc người dùng vào field dùng chung của Controller.

Các ranh giới này giúp cùng một ca sử dụng có thể được gọi từ web form, API, tác vụ nền hoặc message consumer mà không phải sao chép quy tắc nghiệp vụ.

### 9.2. Kiểm thử MVC tương tác cổ điển

Các nhóm kiểm thử thường tập trung vào:

- Model: trạng thái, hành vi và bất biến.
- Controller: sự kiện đầu vào được chuyển thành hành động phù hợp.
- View: dữ liệu Model được trình bày đúng.
- Tương tác: Model thay đổi thì View được cập nhật theo cơ chế đã thiết kế.

Có thể dùng test double cho Model hoặc bộ phát sự kiện để kiểm tra Controller và View mà không cần dựng toàn bộ giao diện.

### 9.3. Kiểm thử web MVC

Trong ứng dụng web, cần kiểm tra thêm hợp đồng HTTP và ranh giới mạng:

- Router chọn đúng Controller theo URL và method.
- Binding và validation tạo kết quả đúng.
- Controller gọi ca sử dụng với dữ liệu đã chuẩn hóa.
- Response có status, header, redirect hoặc body phù hợp.
- View được render với đúng thuộc tính.
- Lỗi nghiệp vụ và lỗi hệ thống được chuyển thành response an toàn.
- Xác thực, phân quyền và CSRF được kiểm tra ở các luồng liên quan.

Với Spring MVC, MockMvc có thể kiểm tra request mapping, model, view và response mà không cần mở cổng HTTP thật. Kiểm thử tích hợp vẫn cần thiết cho các thành phần như cơ sở dữ liệu, bảo mật và cấu hình server.

### 9.4. Kiểm thử ứng dụng SPA

Ngoài kiểm thử API server, SPA cần kiểm tra:

- Component render đúng theo client state.
- Sự kiện người dùng cập nhật state đúng.
- Điều hướng client-side và URL hoạt động nhất quán.
- Trạng thái loading, success, empty và error được trình bày đúng.
- Request lỗi hoặc timeout không làm giao diện rơi vào trạng thái không thể phục hồi.
- Quyền và quy tắc nghiệp vụ vẫn được máy chủ xác nhận.

Không nên xem kiểm thử component là thay thế cho kiểm thử API hoặc kiểm thử tích hợp toàn luồng.

## 10. Những hiểu lầm thường gặp

### MVC trên web giống hệt MVC desktop

Cả hai giữ ý tưởng phân tách Model, View và Controller, nhưng môi trường và vòng đời khác nhau. Desktop thường có event loop liên tục và View đang hoạt động; server-side web MVC thường xử lý request rồi tạo response.

### HTTP stateless nghĩa là ứng dụng không có trạng thái

HTTP không tự lưu ngữ cảnh nghiệp vụ giữa các request. Ứng dụng vẫn có thể dùng session, cookie, token, database hoặc browser state. Điều quan trọng là phải xác định trạng thái được lưu ở đâu và ai có quyền thay đổi.

### Controller web là nơi chứa toàn bộ nghiệp vụ

Controller là điểm vào của giao thức web. Nó không nên trở thành nơi chứa tất cả quy tắc của hệ thống. Đưa nghiệp vụ vào ca sử dụng và Domain Model giúp tái sử dụng, kiểm thử và giữ nhất quán giữa các điểm vào.

### Model luôn là một lớp duy nhất

Trong framework web, từ Model có thể chỉ đối tượng dữ liệu đưa vào View, Domain Model, mô hình đọc hoặc phần dữ liệu của ứng dụng. Cần xem ngữ cảnh của API framework để biết chính xác lớp đang nói đến.

### View chỉ là trình duyệt

Trình duyệt là môi trường hiển thị và tương tác. Trong server-side MVC, View thường là template phía máy chủ tạo HTML; trong SPA, component phía client có thể đóng vai trò View. JSON response cũng là một representation được API công bố, dù nó không phải template HTML.

### Mọi tương tác trình duyệt đều phải gửi request

Nhiều thao tác như mở tab, thu gọn panel hoặc lọc một danh sách đã tải có thể xử lý ở client. Chỉ gửi request khi cần dữ liệu, xác nhận hoặc hành động ở máy chủ.

### Model tự động cập nhật mọi View trên web

Một response HTML đã gửi không tự thay đổi khi dữ liệu server đổi. Muốn cập nhật giao diện đang mở, client cần tải lại, gọi API, polling hoặc nhận thông báo qua cơ chế realtime.

## 11. Quy trình chọn cách tổ chức MVC cho ứng dụng web

Khi thiết kế một chức năng, hãy đi theo các bước sau:

1. **Xác định nơi tương tác diễn ra.** Người dùng thao tác trên ứng dụng desktop, trang HTML server-rendered hay SPA?
2. **Xác định điểm vào.** Sự kiện giao diện, route và HTTP method hay API endpoint?
3. **Xác định trạng thái.** Phần nào là trạng thái giao diện, phần nào là dữ liệu nghiệp vụ, phần nào cần tồn tại qua nhiều request?
4. **Đặt quy tắc vào Model hoặc ca sử dụng.** Đảm bảo cùng nghiệp vụ không phụ thuộc vào một Controller duy nhất.
5. **Định nghĩa hợp đồng request và response.** Dùng form model/DTO và representation phù hợp với client.
6. **Chọn cách render hoặc cập nhật View.** Template server-side, client-side component hay kết hợp cả hai?
7. **Thiết kế xử lý request lặp và đồng thời.** Xem xét giao dịch, version, idempotency và quyền truy cập.
8. **Kiểm thử theo ranh giới.** Kiểm tra nghiệp vụ, routing, binding, response, View và luồng tích hợp.

Trước khi hoàn thành, hãy tự hỏi:

- Controller đang nhận sự kiện nội bộ hay HTTP request?
- Request có thể được xử lý độc lập mà không dựa vào field trạng thái của Controller không?
- Dữ liệu nào cần lưu giữa các request và được lưu ở đâu?
- View có được cập nhật từ một response mới hay từ client state?
- Domain Model có phụ thuộc vào template, HTTP hoặc JavaScript không?
- Cùng một ca sử dụng có thể được gọi từ API hoặc tác vụ nền không?
- Các lỗi mạng, request lặp và cập nhật đồng thời đã được xem xét chưa?

## 12. Kết luận

MVC tương tác cổ điển tổ chức một vòng lặp sự kiện liên tục: Controller nhận thao tác, Model thay đổi trạng thái và View có thể được thông báo để cập nhật ngay trong ứng dụng. MVC trên web giữ nguyên ý tưởng phân tách trách nhiệm nhưng đặt chúng vào luồng request–response qua HTTP: router chọn Controller, Controller gọi nghiệp vụ và chọn response, View thường tạo representation gửi về trình duyệt.

Sự khác biệt về vòng đời, trạng thái và ranh giới mạng ảnh hưởng đến cách thiết kế Controller, View, lưu trữ và kiểm thử. Khi hiểu rõ các điểm này, có thể xây dựng ứng dụng server-rendered hoặc SPA mà vẫn giữ quy tắc nghiệp vụ độc lập, hợp đồng giao tiếp rõ ràng và trải nghiệm tương tác nhất quán.

