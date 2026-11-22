# Đặc tính không lưu trạng thái của HTTP và ảnh hưởng tới MVC

HTTP được thiết kế theo mô hình request–response không lưu trạng thái giao thức (stateless): mỗi request phải mang đủ thông tin để máy chủ hiểu và xử lý yêu cầu hiện tại. Máy chủ không cần dựa vào một kết nối đang mở hoặc một request trước đó để diễn giải request tiếp theo. Đặc tính này giúp giao thức đơn giản, dễ mở rộng và phù hợp với hệ thống phân tán.

Tuy nhiên, ứng dụng web thường cần nhớ người dùng đã đăng nhập, giỏ hàng có gì, biểu mẫu nhiều bước đang ở đâu hoặc một thao tác trước đã hoàn tất chưa. Những thông tin đó là **trạng thái ứng dụng**. Ứng dụng có thể lưu chúng trong session, cơ sở dữ liệu, cache hoặc gửi một phần thông tin qua cookie hay token. Vì vậy, HTTP stateless không có nghĩa là ứng dụng MVC không được lưu trạng thái.

Trong MVC trên web, mỗi request thường tạo một lần thực thi Controller độc lập. Controller phải đọc thông tin cần thiết từ request và các nguồn trạng thái được quản lý rõ ràng, gọi Model hoặc dịch vụ ứng dụng, rồi tạo response. Thiết kế tốt cần phân biệt dữ liệu chỉ tồn tại trong một request với trạng thái cần tồn tại qua nhiều request.

## 1. HTTP stateless có nghĩa là gì?

Một request HTTP chứa thông tin cần thiết để máy chủ xử lý yêu cầu, chẳng hạn:

- Phương thức HTTP như GET, POST, PUT, PATCH hoặc DELETE.
- Đường dẫn và query parameter xác định tài nguyên hoặc điều kiện truy vấn.
- Header mô tả kiểu dữ liệu, xác thực, cache và các tùy chọn khác.
- Body chứa dữ liệu gửi lên, nếu phương thức và hợp đồng endpoint sử dụng body.
- Cookie hoặc thông tin xác thực nếu ứng dụng cần liên kết request với người dùng hay phiên làm việc.

Máy chủ nhận request, xử lý và trả response. Khi request tiếp theo đến, giao thức không tự mang theo ngữ cảnh thực thi của request trước đó. Nếu ứng dụng cần biết hai request thuộc cùng một người dùng hoặc cùng một phiên, ứng dụng phải dùng một cơ chế nhận diện và lưu trạng thái riêng.

~~~mermaid
sequenceDiagram
    participant Browser as Trình duyệt
    participant Server as Máy chủ MVC
    participant Store as Kho trạng thái
    Browser->>Server: Request 1: GET /cart
    Server->>Store: Đọc giỏ hàng theo session/user
    Store-->>Server: Dữ liệu giỏ hàng
    Server-->>Browser: Response 1: HTML/JSON
    Note over Browser,Server: Request 2 là một request HTTP mới
    Browser->>Server: Request 2: POST /cart/items
    Server->>Store: Cập nhật giỏ hàng theo session/user
    Store-->>Server: Kết quả cập nhật
    Server-->>Browser: Response 2: redirect/JSON
~~~

Request thứ hai không tự biết request thứ nhất đã đọc giỏ hàng. Ứng dụng nhận diện người dùng hoặc phiên qua cookie, token hay dữ liệu xác thực khác, rồi truy xuất trạng thái từ kho phù hợp.

### 1.1. Stateless của giao thức khác với stateless của ứng dụng

Cần phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa |
|---|---|
| **HTTP stateless** | Giao thức không tự duy trì ngữ cảnh nghiệp vụ giữa các request |
| **Ứng dụng stateless theo request** | Mỗi request có thể được xử lý độc lập, không cần dữ liệu tạm nằm trong bộ nhớ của một instance cụ thể |
| **Ứng dụng có session** | Ứng dụng liên kết nhiều request bằng một phiên và lưu trạng thái phiên ở một nơi được quản lý |

Một ứng dụng vẫn có thể dùng HTTP stateless nhưng lưu session phía máy chủ. Session là cơ chế của ứng dụng được xây dựng trên HTTP, thường dựa vào một session identifier trong cookie.

Ngược lại, một ứng dụng dùng token không có nghĩa là toàn bộ hệ thống không có trạng thái. Dữ liệu nghiệp vụ vẫn được lưu trong cơ sở dữ liệu; token có thể cần tra cứu quyền, kiểm tra thu hồi hoặc truy xuất thông tin người dùng.

**Điểm cần nhớ:** HTTP không tự nhớ request trước, nhưng ứng dụng có thể chủ động lưu và khôi phục trạng thái giữa các request.

## 2. Ảnh hưởng của HTTP stateless tới luồng MVC

Trong ứng dụng MVC phía máy chủ, mỗi request thường được định tuyến đến một phương thức Controller. Phương thức đó nhận dữ liệu đầu vào, gọi Model hoặc application service, rồi trả View hoặc response.

Một request không nên phụ thuộc vào việc một phương thức Controller khác đã chạy trước đó trong cùng instance. Các bước cần thiết để xử lý request phải được xác định từ dữ liệu request, danh tính đã xác thực và trạng thái được truy xuất từ nguồn có thẩm quyền.

~~~mermaid
flowchart TD
    A["HTTP request độc lập"] --> B["Controller"]
    B --> C["Đọc path/query/body/cookie/principal"]
    C --> D["Application Service / Model"]
    D --> E["Database / Session Store / Cache"]
    E --> D
    D --> F["Kết quả nghiệp vụ"]
    F --> G["ViewModel / Response DTO"]
    G --> H["HTTP response"]
~~~

Điều này ảnh hưởng đến cách thiết kế từng thành phần:

- **Controller** không giữ dữ liệu request của người dùng trong field của đối tượng dùng chung. Nó đọc đầu vào ở từng lần gọi và chuyển dữ liệu cần thiết đến use case.
- **Model** và dịch vụ ứng dụng truy xuất trạng thái nghiệp vụ từ nguồn dữ liệu phù hợp, đồng thời bảo vệ quy tắc khi có nhiều request cùng thao tác.
- **View** hiển thị dữ liệu của response hiện tại. Nếu cần giữ trạng thái giao diện qua lần tải trang, ứng dụng phải quyết định lưu trạng thái đó ở URL, session, client storage hoặc máy chủ.
- **ViewModel/DTO** mang dữ liệu cho một response hoặc request cụ thể; nó không tự tồn tại sau khi request kết thúc.

### 2.1. Vòng đời request không phải vòng đời người dùng

Một người dùng có thể thực hiện nhiều request trong một phiên đăng nhập. Mỗi request có thể đi qua một instance Controller hoặc một máy chủ ứng dụng khác nhau, tùy cách triển khai.

Vì vậy, không nên xem field của Controller như nơi lưu trạng thái của người dùng. Trong Spring MVC, Controller thường là bean singleton. Nếu lưu **currentUser**, **currentCart** hoặc dữ liệu form vào field có thể thay đổi, nhiều request đồng thời sẽ ghi đè dữ liệu của nhau.

Ví dụ không an toàn:

~~~java
@Controller
class TaskController {
    private String currentUserName;

    @GetMapping("/profile")
    String profile(
        @AuthenticationPrincipal AppPrincipal principal,
        org.springframework.ui.Model viewModel
    ) {
        currentUserName = principal.name();
        viewModel.addAttribute("userName", currentUserName);
        return "profile";
    }
}
~~~

Field **currentUserName** được chia sẻ giữa các request vì Controller thường là singleton. Hai người dùng truy cập gần như đồng thời có thể ghi đè giá trị của nhau.

Cách phù hợp là dùng biến cục bộ hoặc tham số theo request:

~~~java
@Controller
class TaskController {

    @GetMapping("/profile")
    String profile(
        @AuthenticationPrincipal AppPrincipal principal,
        org.springframework.ui.Model viewModel
    ) {
        viewModel.addAttribute("userName", principal.name());
        return "profile";
    }
}
~~~

Đối tượng Model trong ví dụ là vùng chứa dữ liệu cho View của request hiện tại. Nó không phải kho lưu trạng thái dài hạn của người dùng.

## 3. Trạng thái nào thuộc request, session và cơ sở dữ liệu?

Không phải mọi dữ liệu đều cần được lưu lâu dài. Cần chọn nơi lưu theo thời gian sống, phạm vi chia sẻ và yêu cầu nhất quán.

| Loại trạng thái | Ví dụ | Nơi lưu phù hợp |
|---|---|---|
| Dữ liệu riêng của request | Path variable, query, form đã binding, lỗi validation | Tham số Controller, request attribute, Model của request |
| Trạng thái phiên người dùng | ID giỏ hàng tạm, tiến trình wizard, thông tin phiên đăng nhập | Server-side session hoặc kho phiên dùng chung |
| Trạng thái nghiệp vụ lâu dài | Đơn hàng, công việc, hồ sơ, thanh toán | Cơ sở dữ liệu hoặc hệ thống lưu trữ có thẩm quyền |
| Trạng thái trình bày phía trình duyệt | Tab đang mở, bộ lọc chưa lưu, vị trí cuộn | URL, state của client, session storage hoặc local storage tùy nhu cầu |
| Dữ liệu tạm có thể tái tạo | Kết quả truy vấn, dữ liệu tham chiếu | Cache có chính sách hết hạn và làm mới |

### 3.1. Request scope

Request scope phù hợp với dữ liệu chỉ cần trong một lần xử lý HTTP, ví dụ:

- Thông tin người dùng hiện tại đã xác thực.
- Dữ liệu form vừa binding.
- Danh sách lỗi validation.
- ViewModel dùng để render một trang.
- Correlation ID phục vụ truy vết request.

Khi response hoàn tất, dữ liệu request scope không nên được xem là còn tồn tại cho request kế tiếp.

Trong Spring MVC, các tham số phương thức Controller, **BindingResult** và **org.springframework.ui.Model** thường là cách tự nhiên để xử lý dữ liệu của request hiện tại.

### 3.2. Session scope

Session dùng để liên kết nhiều request của cùng một phiên. Ví dụ, người dùng có thể thêm nhiều sản phẩm vào giỏ hàng rồi chuyển sang trang thanh toán. Ứng dụng cần biết các request đó cùng thao tác trên một giỏ hàng.

Một cách triển khai là lưu một session identifier ở cookie của trình duyệt và lưu dữ liệu phiên ở máy chủ hoặc một kho session dùng chung. Trình duyệt gửi cookie phù hợp theo phạm vi domain/path và chính sách cookie; máy chủ dùng identifier để tìm phiên.

Không nên mặc định lưu toàn bộ đối tượng nghiệp vụ lớn vào session. Có thể chỉ lưu **cartId** hoặc **wizardId** trong session, còn nội dung giỏ hàng hoặc bản nháp được lưu ở database. Cách này giảm kích thước session và dễ chia sẻ trạng thái giữa các instance ứng dụng.

### 3.3. Trạng thái nghiệp vụ lâu dài

Đơn hàng đã tạo, công việc đã hoàn thành hoặc giao dịch thanh toán không nên chỉ tồn tại trong session. Người dùng có thể đăng xuất, session hết hạn hoặc chuyển thiết bị. Dữ liệu cần tồn tại qua những sự kiện đó phải được lưu ở nơi có độ bền phù hợp.

Session có thể giữ một tham chiếu đến tài nguyên đang thao tác, nhưng cơ sở dữ liệu vẫn là nguồn dữ liệu có thẩm quyền. Mọi thao tác cập nhật phải xác minh người dùng có quyền truy cập tài nguyên đó.

## 4. Cookie, session và token giải quyết vấn đề gì?

HTTP stateless không cung cấp sẵn khái niệm người dùng đã đăng nhập. Ứng dụng cần một cơ chế để nhận diện request.

### 4.1. Cookie

Cookie là dữ liệu mà máy chủ yêu cầu trình duyệt lưu và gửi lại trong các request phù hợp. Cookie thường được dùng để mang session identifier hoặc một số tùy chọn phía client.

Một cookie session nên chứa mã nhận diện khó đoán, không nên chứa toàn bộ dữ liệu nhạy cảm của phiên. Các thuộc tính quan trọng:

- **Secure:** chỉ gửi cookie qua kết nối HTTPS.
- **HttpOnly:** JavaScript phía trang không đọc được cookie qua document.cookie.
- **SameSite:** kiểm soát một số trường hợp cookie được gửi trong request cross-site; có thể hỗ trợ giảm nguy cơ CSRF.
- **Path/Domain:** xác định phạm vi request mà cookie được gửi cùng.
- **Max-Age/Expires:** xác định thời hạn cookie ở phía trình duyệt.

Các thuộc tính này cần được cấu hình theo cách triển khai và luồng xác thực. HttpOnly giảm khả năng JavaScript đọc cookie nhưng không tự ngăn XSS; SameSite cũng không thay thế toàn bộ cơ chế chống CSRF.

### 4.2. Server-side session

Trong mô hình session phía máy chủ:

1. Người dùng đăng nhập thành công.
2. Máy chủ tạo session và gửi session identifier qua cookie.
3. Trình duyệt gửi cookie trong những request tiếp theo thuộc phạm vi.
4. Máy chủ tra session store để khôi phục ngữ cảnh phiên.
5. Khi logout hoặc hết hạn, session bị vô hiệu hóa theo chính sách.

Session store có thể là bộ nhớ cục bộ, Redis, database hoặc một hệ thống phân tán khác. Nếu ứng dụng chạy nhiều instance, lưu session chỉ trong bộ nhớ của một instance sẽ tạo phụ thuộc vào máy chủ đó. Có thể dùng session store dùng chung hoặc cơ chế affinity có chủ đích, nhưng affinity không thay thế yêu cầu quản lý vòng đời và khả năng phục hồi của session.

### 4.3. Token xác thực

Một số API dùng token trong header Authorization, ví dụ Bearer token. Token giúp client chứng minh danh tính hoặc quyền truy cập theo cơ chế xác thực đã thỏa thuận.

JWT có thể chứa claim và được xác minh chữ ký mà không cần tra session ở mỗi request. Tuy vậy:

- Token vẫn có thời hạn và cần kiểm tra issuer, audience, signature, expiry và các claim liên quan.
- Khi quyền người dùng thay đổi, token cũ có thể tiếp tục mang claim cũ cho đến khi hết hạn, trừ khi có cơ chế thu hồi hoặc tra cứu bổ sung.
- Token bị lộ có thể bị sử dụng cho đến khi hết hiệu lực hoặc bị vô hiệu hóa.
- Token không thay thế cơ sở dữ liệu nghiệp vụ và kiểm tra quyền trên từng tài nguyên.

Vì vậy, session và token là hai cách quản lý ngữ cảnh xác thực khác nhau; lựa chọn phụ thuộc loại client, yêu cầu thu hồi, bảo mật và kiến trúc triển khai.

## 5. MVC xử lý biểu mẫu qua nhiều request

Một biểu mẫu HTML thường tạo ra ít nhất hai request: GET để hiển thị form và POST để gửi dữ liệu. Hai request độc lập theo HTTP. Controller không thể dựa vào việc biến cục bộ của GET còn tồn tại khi POST đến.

Luồng thường gặp:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant Controller as Controller
    participant Model as Model / Service
    User->>Browser: Mở trang tạo công việc
    Browser->>Controller: GET /tasks/new
    Controller->>Model: Chuẩn bị dữ liệu tham chiếu
    Model-->>Controller: Dữ liệu cần thiết
    Controller-->>Browser: HTML + form
    User->>Browser: Nhập tiêu đề và gửi
    Browser->>Controller: POST /tasks
    Controller->>Controller: Binding và validation
    Controller->>Model: Tạo công việc
    Model-->>Controller: Kết quả
    Controller-->>Browser: Redirect
    Browser->>Controller: GET /tasks/{id}
    Controller-->>Browser: Trang chi tiết
~~~

### 5.1. Không dùng biến trong Controller để giữ form giữa GET và POST

Form cần được gửi lại trong POST hoặc được lưu trong session/draft nếu là quy trình nhiều bước. Không nên gán form vào field của Controller sau GET và mong POST sau đó đọc được field đó.

Ví dụ Spring MVC:

~~~java
@PostMapping("/tasks")
String create(
    @Valid @ModelAttribute("form") CreateTaskForm form,
    BindingResult errors,
    RedirectAttributes redirectAttributes
) {
    if (errors.hasErrors()) {
        return "tasks/new";
    }

    TaskResult created = taskService.create(form.title());
    redirectAttributes.addFlashAttribute(
        "notice", "Đã tạo công việc thành công."
    );

    return "redirect:/tasks/" + created.id();
}
~~~

Dữ liệu form được binding lại từ request POST. Nếu validation thất bại, Controller trả lại View cùng lỗi của request hiện tại. Nếu thành công, use case tạo tài nguyên và Controller chuyển hướng.

### 5.2. Post–Redirect–Get (PRG)

Post–Redirect–Get là mẫu xử lý phổ biến cho biểu mẫu:

1. Trình duyệt gửi POST.
2. Server xử lý và trả redirect.
3. Trình duyệt gửi GET đến URL đích.
4. Trang kết quả được hiển thị bằng GET.

PRG giúp khi người dùng refresh trang kết quả, trình duyệt tải lại GET thay vì hỏi gửi lại POST vừa tạo tài nguyên. Nó cũng tạo URL có thể bookmark hoặc chia sẻ cho trang kết quả.

PRG không bảo đảm một thao tác chỉ chạy đúng một lần. Người dùng có thể nhấn nút hai lần, mạng có thể retry hoặc request có thể được gửi lại trước khi redirect được nhận. Với thao tác quan trọng, cần thêm cơ chế idempotency hoặc kiểm soát trùng lặp ở phía server.

### 5.3. Flash attribute và dữ liệu chỉ dùng sau redirect

Sau khi POST thành công, ứng dụng thường muốn hiển thị thông báo ở trang GET tiếp theo. Trong Spring MVC, RedirectAttributes có thể thêm flash attribute. Dữ liệu này được giữ tạm qua redirect rồi loại bỏ sau khi được lấy ở request đích.

Flash attribute phù hợp với thông báo như “Đã lưu thành công” hoặc lỗi nghiệp vụ cần hiển thị một lần. Không nên dùng flash attribute làm kho lưu trạng thái nghiệp vụ lâu dài.

## 6. Quy trình nhiều bước và trạng thái tạm

Một wizard đăng ký hoặc thanh toán có thể trải qua nhiều request: nhập thông tin, xác nhận, chọn phương thức và hoàn tất. Vì HTTP stateless, ứng dụng phải quyết định cách giữ tiến trình.

Có một số cách:

- **Lưu draft trong session:** phù hợp với dữ liệu tạm, thời gian sống ngắn và gắn với phiên.
- **Lưu draft trong database:** phù hợp khi người dùng cần tiếp tục trên thiết bị khác, cần kiểm toán hoặc dữ liệu có giá trị lâu dài.
- **Đưa trạng thái không nhạy cảm vào URL:** phù hợp với bộ lọc, trang hiện tại hoặc bước có thể chia sẻ/bookmark.
- **Dùng token tham chiếu có chữ ký hoặc mã định danh ngẫu nhiên:** chỉ khi có thiết kế rõ về xác minh, hết hạn và quyền truy cập.

Không nên gửi toàn bộ trạng thái quan trọng qua hidden input rồi tin rằng dữ liệu đó chưa bị sửa. Hidden input vẫn do client kiểm soát. Nếu client gửi **price=100** hoặc **role=ADMIN**, server phải bỏ qua hoặc xác minh theo dữ liệu có thẩm quyền.

Với Spring MVC, **@SessionAttributes** có thể giữ một số model attribute qua nhiều request trong phạm vi Controller. Khi quy trình hoàn tất, cần gọi **SessionStatus.setComplete()** để kết thúc trạng thái được quản lý. Cần cân nhắc timeout, nhiều tab đồng thời và việc người dùng mở hai wizard cùng lúc; một thuộc tính session đơn lẻ có thể bị hai luồng ghi đè.

## 7. Tính độc lập của request ảnh hưởng đến retry và thao tác lặp

Mạng không bảo đảm client luôn nhận được response. Server có thể đã xử lý xong POST nhưng kết nối bị đứt trước khi trình duyệt nhận kết quả. Client không biết chắc thao tác đã thành công hay chưa và có thể gửi lại.

HTTP định nghĩa ngữ nghĩa phương thức để client và server phối hợp:

| Phương thức | Ngữ nghĩa thường gặp | Lưu ý |
|---|---|---|
| GET | Đọc tài nguyên, được xem là safe | Không nên dùng để thay đổi trạng thái nghiệp vụ |
| POST | Gửi dữ liệu hoặc yêu cầu xử lý | Không mặc định idempotent; retry có thể tạo thao tác lặp |
| PUT | Tạo hoặc thay thế biểu diễn tại URI | Được định nghĩa là idempotent theo ngữ nghĩa HTTP |
| PATCH | Cập nhật một phần tài nguyên | Tính idempotent phụ thuộc cách định nghĩa thao tác |
| DELETE | Xóa tài nguyên | Được định nghĩa là idempotent theo ngữ nghĩa; response các lần gọi có thể khác nhau |

Idempotent nghĩa là thực hiện cùng một request nhiều lần có hiệu quả trạng thái cuối tương đương với thực hiện một lần. Điều đó không có nghĩa mọi lần gọi phải trả response giống hệt nhau hoặc không có log/tác dụng phụ kỹ thuật.

### 7.1. Idempotency key cho thao tác tạo quan trọng

Với thanh toán hoặc tạo đơn hàng, có thể dùng idempotency key. Client gửi một mã duy nhất cho một ý định thao tác; server lưu kết quả gắn với mã đó và trả lại kết quả cũ nếu cùng key được gửi lại theo quy tắc.

~~~http
POST /api/orders
Idempotency-Key: 8c1f...unique-operation-key
Content-Type: application/json
~~~

Server cần ràng buộc key với người dùng, endpoint hoặc loại thao tác, lưu trạng thái xử lý và kết quả, đồng thời xử lý trường hợp hai request cùng key đến đồng thời. Chỉ thêm header mà không lưu và kiểm tra ở server thì không tạo ra idempotency.

### 7.2. PRG và idempotency giải quyết hai vấn đề khác nhau

PRG giảm việc trình duyệt gửi lại POST khi refresh trang kết quả. Idempotency bảo vệ thao tác trước request trùng lặp do double-click, retry, timeout hoặc client gửi lại. Các thao tác có hậu quả tài chính hoặc tạo dữ liệu quan trọng có thể cần cả hai.

## 8. Nhiều request đồng thời và cập nhật mất dữ liệu

HTTP stateless cho phép nhiều request độc lập được xử lý đồng thời. Hai tab trình duyệt hoặc hai người dùng có thể cùng đọc rồi cập nhật một tài nguyên. Nếu không kiểm soát, lần ghi sau có thể ghi đè thay đổi của lần ghi trước.

Ví dụ:

1. Request A đọc công việc với version 4.
2. Request B cũng đọc version 4.
3. A cập nhật tiêu đề và lưu thành version 5.
4. B cập nhật trạng thái dựa trên dữ liệu version 4 và ghi đè một phần thay đổi của A.

Có thể dùng optimistic locking với version hoặc timestamp. Khi cập nhật, server chỉ chấp nhận nếu phiên bản hiện tại vẫn bằng phiên bản mà client đã đọc.

Ví dụ với JPA:

~~~java
@Entity
class Task {
    @Id
    private Long id;

    @Version
    private long version;

    private String title;
}
~~~

Khi hai transaction cùng cập nhật một phiên bản, một transaction có thể thất bại do optimistic locking. Ứng dụng cần chuyển lỗi đó thành thông báo xung đột hoặc yêu cầu người dùng tải lại dữ liệu. Không nên tự động retry mọi thao tác nếu việc áp dụng lại có thể làm thay đổi ý nghĩa nghiệp vụ.

Đối với API, có thể dùng ETag và If-Match để kiểm tra phiên bản biểu diễn. Server chỉ thực hiện cập nhật nếu ETag còn khớp; nếu không, trả lỗi tiền điều kiện hoặc xung đột theo hợp đồng API.

## 9. Caching và HTTP stateless

Vì request GET mô tả tài nguyên cần đọc, HTTP có các cơ chế cache ở trình duyệt, proxy và CDN. Cache giúp giảm tải server và tăng tốc response, nhưng phải được cấu hình theo tính công khai và mức độ thay đổi của dữ liệu.

Một số header thường gặp:

- **Cache-Control:** quy định response có được cache không, cache ở đâu và trong bao lâu.
- **ETag:** mã đại diện cho phiên bản biểu diễn; client có thể gửi If-None-Match để hỏi nội dung có thay đổi không.
- **Last-Modified / If-Modified-Since:** dùng thời điểm sửa đổi để kiểm tra lại tài nguyên.
- **Vary:** chỉ ra header request nào ảnh hưởng đến cách tạo response, ví dụ Accept-Encoding.

Dữ liệu công khai, ít thay đổi có thể được cache lâu hơn. Dữ liệu cá nhân hoặc nhạy cảm cần chính sách thận trọng; có thể dùng **Cache-Control: private** hoặc **no-store** tùy yêu cầu. Không được để response chứa dữ liệu của một người dùng được dùng lại cho người khác qua shared cache.

Cache cũng là một nguồn trạng thái tạm. Dữ liệu cache có thể hết hạn hoặc bị loại bỏ, nên Model không được coi cache là nguồn dữ liệu có thẩm quyền nếu dữ liệu cần tồn tại lâu dài. Cần có chiến lược invalidation hoặc cập nhật cache khi nghiệp vụ thay đổi.

## 10. Bảo mật session và request

Khi dùng cookie hoặc session để liên kết request, ứng dụng cần bảo vệ cả định danh phiên và thao tác thay đổi trạng thái.

### 10.1. Session fixation và vòng đời session

Sau khi xác thực thành công, ứng dụng cần thay đổi session identifier hoặc dùng cơ chế bảo vệ session fixation của framework. Khi logout, session phía máy chủ cần được vô hiệu hóa và cookie tương ứng được xử lý theo cấu hình.

Session identifier có thể bị đánh cắp qua XSS, thiết bị dùng chung hoặc kênh truyền không an toàn. Vì vậy, cần HTTPS, cookie Secure/HttpOnly/SameSite phù hợp, thời hạn session hợp lý và kiểm soát quyền truy cập.

### 10.2. CSRF với xác thực dựa trên cookie

Trình duyệt tự gửi cookie trong những request phù hợp. Điều này tiện cho session login nhưng cũng có nghĩa một trang khác có thể tìm cách khiến trình duyệt gửi request đến ứng dụng đang đăng nhập. Nếu request thay đổi trạng thái không được bảo vệ, có thể phát sinh CSRF.

Các biện pháp thường dùng gồm CSRF token, kiểm tra origin/referer theo chính sách và SameSite cookie. SameSite là một lớp hỗ trợ, không phải lý do để bỏ qua thiết kế CSRF tổng thể. Không dùng GET để thực hiện thao tác thay đổi dữ liệu.

### 10.3. Không tin dữ liệu lưu ở client

Cookie, query parameter, hidden input, local storage và nội dung request đều có thể bị sửa. Có thể lưu một số dữ liệu trình bày hoặc tham chiếu phía client, nhưng server phải xác minh mọi thông tin quyết định quyền, giá trị giao dịch và trạng thái nghiệp vụ.

Nếu cần dữ liệu client không thể sửa mà không bị phát hiện, phải dùng chữ ký hoặc cơ chế xác thực toàn vẹn phù hợp; ngay cả khi có chữ ký, server vẫn cần kiểm tra thời hạn và quyền sử dụng.

## 11. Mở rộng ứng dụng nhiều instance

HTTP stateless hỗ trợ mô hình nhiều máy chủ vì mỗi request có thể được xử lý bởi bất kỳ instance nào có đủ cấu hình và dữ liệu cần thiết.

~~~mermaid
flowchart TD
    C["Client"] --> LB["Load Balancer"]
    LB --> A["MVC instance A"]
    LB --> B["MVC instance B"]
    LB --> D["MVC instance C"]
    A --> S["Database / Shared Session Store"]
    B --> S
    D --> S
~~~

Nếu session chỉ nằm trong RAM của instance A, request tiếp theo được chuyển đến instance B có thể không tìm thấy phiên. Các cách giải quyết:

- Dùng session store dùng chung hoặc cơ chế session phân tán.
- Lưu trạng thái nghiệp vụ trong database và chỉ giữ định danh cần thiết trong session.
- Dùng token phù hợp khi client và server có thể xác minh độc lập, đồng thời chấp nhận các đặc tính thu hồi và cập nhật quyền.
- Dùng sticky session khi có lý do vận hành rõ ràng, nhưng vẫn phải xử lý restart, failover và timeout.

Không nên hiểu stateless là không cần database, cache hoặc session store. Nó có nghĩa một instance không cần giữ toàn bộ ngữ cảnh request trước trong bộ nhớ cục bộ để xử lý request sau.

## 12. Kiểm thử MVC khi HTTP không lưu trạng thái

Kiểm thử nên xác minh mỗi request hoạt động đúng khi được cung cấp đủ đầu vào và ngữ cảnh cần thiết.

| Phạm vi | Nội dung cần xác minh |
|---|---|
| Controller | Binding, request parameter, cookie/session, response, redirect và mã trạng thái |
| Model / Use Case | Quy tắc nghiệp vụ độc lập với thứ tự gọi Controller |
| Session | Tạo, đọc, hết hạn, logout và xử lý nhiều request trong một phiên |
| Tích hợp | Request được xử lý ở instance khác vẫn truy xuất đúng trạng thái dùng chung |
| Bảo mật | CSRF, quyền truy cập tài nguyên, cookie và session fixation |
| Đồng thời | Hai request cùng cập nhật không âm thầm ghi đè dữ liệu |
| Cache | Response cá nhân không bị chia sẻ sai; ETag/Cache-Control đúng hợp đồng |

Một số kịch bản đáng kiểm thử:

- Gửi GET trực tiếp mà không cần gọi một phương thức Controller trước đó.
- Gửi POST sau khi tải lại trang và xác minh dữ liệu được binding từ request.
- Refresh sau redirect không tạo thêm tài nguyên.
- Gửi lại cùng idempotency key không tạo giao dịch thứ hai.
- Session hết hạn thì ứng dụng yêu cầu xác thực lại hoặc khôi phục quy trình theo chính sách.
- Hai request cập nhật cùng version tạo ra xung đột được xử lý rõ ràng.
- Response cá nhân không được cache công khai.
- Request không có quyền bị từ chối dù client sửa hidden input hoặc gọi endpoint trực tiếp.

## 13. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Cho rằng HTTP stateless nghĩa là không dùng session | Không quản lý được trạng thái đăng nhập hoặc quy trình nhiều bước | Chọn session, database hoặc token theo vòng đời dữ liệu |
| Lưu dữ liệu người dùng vào field Controller singleton | Request đồng thời có thể ghi đè dữ liệu của nhau | Dùng biến cục bộ, request scope hoặc kho trạng thái phù hợp |
| Đưa toàn bộ nghiệp vụ vào session | Dữ liệu dễ mất, khó đồng bộ và phình session | Lưu dữ liệu nghiệp vụ trong database; session giữ tham chiếu cần thiết |
| Tin hidden input hoặc cookie do client gửi | Người dùng có thể sửa quyền, giá hoặc trạng thái | Xác minh phía server và dùng dữ liệu có thẩm quyền |
| Nghĩ PRG bảo đảm không tạo trùng | Double-click hoặc retry vẫn có thể tạo nhiều bản ghi | Dùng idempotency key hoặc ràng buộc duy nhất phù hợp |
| Chỉ lưu session trong RAM một instance | Request sang instance khác mất ngữ cảnh | Dùng shared session store hoặc thiết kế stateless phù hợp |
| Cache response cá nhân như dữ liệu công khai | Rò rỉ dữ liệu giữa người dùng | Thiết lập Cache-Control và Vary đúng cách |
| Không kiểm soát cập nhật đồng thời | Lost update và trạng thái không nhất quán | Optimistic locking, version hoặc cơ chế đồng bộ thích hợp |

## 14. Quy trình thiết kế một luồng MVC qua nhiều request

Khi xây dựng chức năng web cần giữ trạng thái, có thể tiến hành theo thứ tự:

1. Xác định mỗi request cần thông tin gì để xử lý độc lập.
2. Phân loại dữ liệu theo request, session, client state và trạng thái nghiệp vụ lâu dài.
3. Chọn nơi lưu cho từng loại dữ liệu dựa trên vòng đời, quyền truy cập và yêu cầu nhất quán.
4. Xác định cách nhận diện người dùng hoặc phiên: cookie, session hay token.
5. Thiết kế Controller để binding request, gọi use case và tạo response rõ ràng.
6. Với form POST, cân nhắc PRG; với thao tác quan trọng, thiết kế idempotency.
7. Với nhiều request cùng sửa tài nguyên, xác định cách phát hiện xung đột phiên bản.
8. Đặt chính sách cache theo tính công khai và độ nhạy cảm của response.
9. Bảo vệ session, CSRF, quyền truy cập và dữ liệu client gửi lên.
10. Kiểm thử request độc lập, session hết hạn, retry, concurrency và triển khai nhiều instance.

## 15. Những điểm cần ghi nhớ

HTTP stateless có nghĩa mỗi request là một đơn vị giao tiếp độc lập ở cấp giao thức. Máy chủ không tự nhớ ngữ cảnh nghiệp vụ của request trước. Ứng dụng MVC vẫn có thể lưu trạng thái bằng session, cookie, token, database hoặc cache, nhưng phải chọn đúng nơi theo vòng đời và yêu cầu nhất quán.

Controller nên xử lý mỗi request từ dữ liệu đầu vào và ngữ cảnh đã xác thực, không giữ trạng thái người dùng trong field dùng chung. Model và dịch vụ ứng dụng lấy trạng thái có thẩm quyền, bảo vệ quy tắc khi có request đồng thời; View hiển thị kết quả của response hiện tại.

PRG giúp tránh gửi lại POST khi refresh trang kết quả nhưng không thay thế idempotency. Session giúp nối nhiều request nhưng cần quản lý vòng đời và khả năng mở rộng. Cache tăng hiệu năng nhưng phải bảo vệ dữ liệu cá nhân. Cookie và token giúp nhận diện request nhưng không thay thế kiểm tra quyền và validation phía server.

Khi thiết kế MVC trên web, hãy xem mỗi request là một lần xử lý mới, xác định rõ trạng thái nào cần được khôi phục và bảo đảm mọi quyết định nghiệp vụ quan trọng được kiểm tra ở phía máy chủ.
