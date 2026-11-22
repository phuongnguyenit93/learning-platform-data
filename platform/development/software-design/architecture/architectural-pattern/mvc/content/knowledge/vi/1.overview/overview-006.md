# Phân biệt mẫu kiến trúc giao diện và kiến trúc toàn hệ thống

## Mục tiêu

MVC (Model–View–Controller) tổ chức cách một ứng dụng tiếp nhận tương tác, xử lý dữ liệu liên quan và tạo phản hồi cho người dùng. Nó giúp tách trạng thái và nghiệp vụ, phần trình bày, cùng phần điều phối đầu vào thành những trách nhiệm dễ hiểu và dễ kiểm thử.

Tuy nhiên, MVC chỉ giải quyết một phạm vi kiến trúc nhất định. Kiến trúc toàn hệ thống còn phải xác định các thành phần lớn của sản phẩm, ranh giới giữa chúng, cách chúng giao tiếp, cách dữ liệu được lưu trữ, cách hệ thống được triển khai và cách hệ thống đáp ứng những yêu cầu như bảo mật, khả năng mở rộng và độ tin cậy.

Hiểu rõ hai phạm vi này giúp chọn đúng công cụ cho đúng quyết định: dùng MVC để tổ chức luồng tương tác của một ứng dụng web, đồng thời đặt ứng dụng đó vào một kiến trúc tổng thể phù hợp với sản phẩm.

## 1. Hai khái niệm ở hai phạm vi khác nhau

### Mẫu kiến trúc giao diện

Mẫu kiến trúc giao diện mô tả cách tổ chức phần mềm trực tiếp phục vụ tương tác với người dùng hoặc với một giao diện lập trình. Nó trả lời những câu hỏi như:

- Thành phần nào tiếp nhận yêu cầu từ trình duyệt?
- Dữ liệu nào được đưa vào xử lý và dữ liệu nào được dùng để hiển thị?
- Quy tắc nghiệp vụ được gọi ở đâu?
- Ai quyết định nội dung phản hồi và cách trình bày lỗi?
- Làm thế nào để kiểm thử riêng việc xử lý yêu cầu và việc hiển thị?

MVC là một mẫu kiến trúc thường được dùng ở phạm vi này. Nó phân chia trách nhiệm thành Model, View và Controller. Mỗi thành phần có vai trò riêng, nhưng phối hợp để hoàn tất một tương tác.

Trong ứng dụng web, MVC thường được hiện thực theo luồng request–response: Controller nhận HTTP request, gọi phần xử lý phù hợp, chuẩn bị dữ liệu và trả về View hoặc một biểu diễn phản hồi như JSON. Cách hiện thực này có thể khác một số mô tả MVC cổ điển, nơi View quan sát thay đổi của Model và cập nhật khi trạng thái thay đổi.

### Kiến trúc toàn hệ thống

Kiến trúc toàn hệ thống mô tả cấu trúc và những quyết định kỹ thuật chi phối toàn bộ sản phẩm. Nó trả lời các câu hỏi ở phạm vi rộng hơn:

- Hệ thống gồm những ứng dụng, dịch vụ, tiến trình hoặc mô-đun nào?
- Ranh giới trách nhiệm và quyền sở hữu dữ liệu nằm ở đâu?
- Các thành phần giao tiếp qua HTTP, RPC, hàng đợi hay sự kiện?
- Hệ thống triển khai thành một ứng dụng, nhiều dịch vụ hay nhiều tiến trình?
- Cần đáp ứng yêu cầu về tải, độ trễ, tính sẵn sàng, khả năng phục hồi và bảo mật như thế nào?
- Các thành phần phụ thuộc vào nhau ra sao và thay đổi được phát hành như thế nào?

Ví dụ, một sản phẩm có thể được xây dựng theo kiến trúc layered monolith, modular monolith hoặc microservices. Mỗi lựa chọn quyết định cách chia hệ thống và cách triển khai. Bên trong một mô-đun hoặc một dịch vụ, nhóm phát triển vẫn có thể dùng MVC để tổ chức phần tiếp nhận và phản hồi yêu cầu.

### So sánh nhanh

| Khía cạnh | Mẫu kiến trúc giao diện như MVC | Kiến trúc toàn hệ thống |
|---|---|---|
| Phạm vi | Một luồng tương tác, một ứng dụng giao diện hoặc một lớp tiếp nhận yêu cầu | Toàn bộ sản phẩm và các thành phần vận hành của nó |
| Câu hỏi chính | Ai nhận đầu vào, điều phối xử lý và trình bày kết quả? | Hệ thống gồm những phần nào và chúng phối hợp ra sao? |
| Đơn vị tổ chức | Model, View, Controller và các thành phần hỗ trợ | Ứng dụng, dịch vụ, mô-đun, kho dữ liệu, cổng tích hợp, hàng đợi và hạ tầng |
| Quyết định tiêu biểu | Cấu trúc controller, hợp đồng form, view model, cách trả lỗi | Ranh giới dịch vụ, giao thức, quyền sở hữu dữ liệu, triển khai và mở rộng |
| Chất lượng được quan tâm trực tiếp | Khả năng bảo trì, kiểm thử và thay đổi luồng tương tác | Hiệu năng tổng thể, độ tin cậy, bảo mật, khả năng mở rộng và vận hành |
| Ví dụ | Spring MVC xử lý yêu cầu đăng ký khóa học | Một nền tảng học tập gồm web app, dịch vụ thanh toán, dịch vụ thông báo và cơ sở dữ liệu |

Hai phạm vi có liên hệ nhưng không thay thế nhau. Một quyết định MVC không tự quyết định hệ thống phải dùng microservices, cơ sở dữ liệu nào hoặc triển khai ở đâu.

## 2. MVC tổ chức một tương tác như thế nào?

Ba thành phần của MVC có thể được hiểu qua trách nhiệm và ranh giới của chúng.

### Model — trạng thái và quy tắc liên quan đến dữ liệu

Model đại diện cho dữ liệu mà ứng dụng làm việc cùng và các quy tắc nghiệp vụ gắn với dữ liệu đó. Trong một ứng dụng đăng ký khóa học, những khái niệm như Khóa học, Học viên, Đăng ký và Sức chứa lớp thuộc miền nghiệp vụ.

Model không nên bị hiểu đơn giản là một lớp ánh xạ trực tiếp tới một bảng cơ sở dữ liệu. Tùy framework và cách tổ chức ứng dụng, từ “model” có thể được dùng cho nhiều loại đối tượng:

- Domain model biểu diễn khái niệm và quy tắc nghiệp vụ.
- Persistence entity biểu diễn dữ liệu được lưu trữ.
- Request DTO hoặc form object nhận dữ liệu người dùng gửi lên.
- View model chứa đúng dữ liệu mà màn hình cần trình bày.

Những đối tượng này có thể liên hệ với nhau, nhưng không nhất thiết phải là cùng một lớp. Dùng một đối tượng duy nhất cho mọi mục đích dễ làm rò rỉ cấu trúc lưu trữ ra giao diện và khiến hợp đồng HTTP phụ thuộc vào chi tiết nội bộ.

### View — trình bày kết quả

View chịu trách nhiệm biểu diễn dữ liệu cho người dùng hoặc bên gọi. Với ứng dụng web kết xuất phía máy chủ, View có thể là template HTML. Với API, phần biểu diễn phản hồi có thể là JSON. Với giao diện ứng dụng đơn trang, phần View thường nằm trong frontend và có thể gọi API từ một backend riêng.

View nên tập trung vào trình bày. Nó không nên tự truy vấn cơ sở dữ liệu hoặc tự thực thi quy tắc như kiểm tra một lớp học còn chỗ hay không. Khi cần hiển thị thông báo lỗi, View nhận thông tin lỗi đã được chuẩn bị và trình bày theo ngữ cảnh.

### Controller — tiếp nhận và điều phối

Controller tiếp nhận tương tác, chuyển đầu vào thành dữ liệu có cấu trúc, gọi ca sử dụng hoặc dịch vụ phù hợp, rồi chọn phản hồi cần trả về. Trong web MVC, controller thường gắn với route hoặc HTTP endpoint.

Controller có thể thực hiện kiểm tra đầu vào ở ranh giới, nhưng không nên trở thành nơi chứa toàn bộ nghiệp vụ. Các quy tắc như giới hạn số học viên, điều kiện đăng ký hoặc tính phí nên được xử lý ở lớp nghiệp vụ/domain hoặc application service để có thể tái sử dụng từ nhiều loại giao diện.

### Luồng request–response điển hình

Một yêu cầu đăng ký khóa học có thể đi qua các bước sau:

    Trình duyệt
        |
        | POST /registrations
        v
    Router / Dispatcher
        |
        v
    RegistrationController
        |
        | kiểm tra cấu trúc đầu vào, gọi ca sử dụng
        v
    RegistrationService
        |
        | áp dụng quy tắc nghiệp vụ
        v
    Domain Model / Repository
        |
        | kết quả xử lý
        v
    RegistrationController
        |
        | chuẩn bị View Model hoặc response DTO
        v
    View / JSON Serializer
        |
        v
    HTTP Response

Luồng này cho thấy MVC điều phối một tương tác. Nó không mô tả toàn bộ cách cơ sở dữ liệu được triển khai, dịch vụ thanh toán giao tiếp ra sao hay hệ thống được phân vùng khi tải tăng.

## 3. Đặt MVC bên trong kiến trúc lớn hơn

Hãy xét một nền tảng học tập có các khả năng xem khóa học, đăng ký, thanh toán và gửi thông báo. Có nhiều cách tổ chức toàn hệ thống:

- Với layered monolith, các chức năng có thể cùng nằm trong một ứng dụng, được phân lớp giao diện, nghiệp vụ và truy cập dữ liệu.
- Với modular monolith, các chức năng được chia thành mô-đun có ranh giới rõ ràng nhưng vẫn được triển khai cùng một đơn vị.
- Với microservices, đăng ký, thanh toán và thông báo có thể là các dịch vụ triển khai độc lập, mỗi dịch vụ sở hữu dữ liệu và giao tiếp qua API hoặc sự kiện.

Trong cả ba phương án, phần web tiếp nhận yêu cầu vẫn có thể dùng MVC. Ví dụ, RegistrationController nhận yêu cầu đăng ký và gọi RegistrationService. Service này có thể là một lớp trong cùng ứng dụng hoặc một thành phần giao tiếp với dịch vụ đăng ký từ xa. Lựa chọn đó thuộc kiến trúc toàn hệ thống.

    Người dùng
        |
        v
    Web Application
      [MVC: Controller / View / Model]
        |
        v
    Application Service
        |
        +------> Course Module ------> Course Database
        |
        +------> Registration Service -> Registration Database
        |
        +------> Payment Service ------> Payment Provider
        |
        +------> Notification Service -> Message Queue

Sơ đồ chỉ minh họa một khả năng tổ chức. Trong một hệ thống monolith, các mô-đun và kho dữ liệu có thể nằm trong cùng một tiến trình hoặc cơ sở dữ liệu. Trong hệ thống phân tán, chúng có thể được triển khai và vận hành độc lập. MVC không áp đặt phương án nào trong số đó.

Cũng cần phân biệt MVC với kiến trúc frontend/backend. Một frontend đơn trang có thể dùng một mẫu tổ chức giao diện riêng ở phía trình duyệt, trong khi backend cung cấp REST API. Backend có thể dùng MVC để tổ chức controller và phần phản hồi, hoặc dùng một cách tổ chức khác. Tên MVC trong một framework không có nghĩa toàn bộ frontend, backend và hạ tầng đều đang tuân theo cùng một cấu trúc MVC.

## 4. Ví dụ: xử lý biểu mẫu đăng ký khóa học

Giả sử người học gửi biểu mẫu đăng ký gồm mã khóa học và mã học viên.

**Ở phạm vi MVC**, nhóm phát triển cần xác định:

1. Controller nào nhận yêu cầu POST và ràng buộc dữ liệu biểu mẫu?
2. Hợp đồng đầu vào có những trường nào, kiểu dữ liệu nào và giới hạn nào?
3. Thành phần nghiệp vụ nào xác nhận khóa học còn chỗ và học viên đủ điều kiện?
4. Khi thành công, ứng dụng chuyển hướng hay trả JSON?
5. Khi thất bại, lỗi trường dữ liệu và lỗi nghiệp vụ được hiển thị thế nào?

Một controller Spring MVC giản lược có thể trông như sau:

    @Controller
    @RequestMapping("/registrations")
    class RegistrationController {
        private final RegistrationService service;

        RegistrationController(RegistrationService service) {
            this.service = service;
        }

        @PostMapping
        String register(
                @Valid @ModelAttribute RegistrationForm form,
                BindingResult errors,
                Model viewModel) {

            if (errors.hasErrors()) {
                return "registrations/new";
            }

            service.register(form.studentId(), form.courseId());
            return "redirect:/registrations/success";
        }
    }

Đây là ví dụ rút gọn để minh họa ranh giới trách nhiệm. RegistrationForm là hợp đồng nhận dữ liệu từ biểu mẫu. Controller nhận và kiểm tra lỗi đầu vào, sau đó gọi RegistrationService. Service và domain model chịu trách nhiệm áp dụng quy tắc đăng ký. View hiển thị biểu mẫu hoặc kết quả.

**Ở phạm vi kiến trúc toàn hệ thống**, những câu hỏi khác xuất hiện:

- RegistrationService chạy trong cùng ứng dụng web hay là dịch vụ độc lập?
- Thông tin chỗ trống được quản lý ở dịch vụ khóa học hay dịch vụ đăng ký?
- Thanh toán được gọi đồng bộ hay phát sự kiện để xử lý sau?
- Nếu thanh toán thành công nhưng phản hồi bị mất, hệ thống tránh ghi nhận đăng ký hai lần như thế nào?
- Dữ liệu đăng ký được sao lưu, giám sát và triển khai ra sao?

Controller không nên tự giải quyết các quyết định phân tán này. Nó gọi một ca sử dụng thông qua hợp đồng rõ ràng; kiến trúc tổng thể quyết định thành phần nào cung cấp hợp đồng và cách lời gọi được thực hiện.

## 5. Hợp đồng dữ liệu, lỗi, bảo mật và kiểm thử ở đúng lớp

Phân biệt phạm vi kiến trúc giúp đặt từng trách nhiệm vào nơi phù hợp.

| Mối quan tâm | Trong luồng MVC | Ở phạm vi toàn hệ thống |
|---|---|---|
| Hợp đồng dữ liệu | Form/request DTO, view model, response DTO và quy tắc ràng buộc | Hợp đồng API giữa dịch vụ, schema sự kiện và chính sách tương thích phiên bản |
| Xử lý lỗi | Lỗi nhập liệu, lỗi nghiệp vụ cần phản hồi cho người dùng, ánh xạ lỗi HTTP | Retry, timeout, circuit breaker, xử lý sự cố liên dịch vụ và quan sát lỗi |
| Bảo mật | Xác thực đầu vào, kiểm tra quyền trên thao tác, CSRF, escape dữ liệu đầu ra | Danh tính dịch vụ, quản lý bí mật, phân vùng mạng, chính sách truy cập và kiểm toán |
| Kiểm thử | Unit test cho controller/service, kiểm thử validation và render view | Contract test giữa dịch vụ, integration test, kiểm thử tải và kiểm thử khả năng phục hồi |

Các lớp cần phối hợp. Ví dụ, controller có thể xác nhận người dùng đã đăng nhập và có quyền gọi thao tác; application service vẫn cần bảo đảm quy tắc nghiệp vụ được thực thi dù thao tác được gọi từ giao diện khác. View phải escape dữ liệu khi hiển thị để tránh chèn mã độc. Ở cấp hệ thống, thông tin xác thực giữa các dịch vụ và quản lý bí mật cần được thiết kế đồng bộ.

Một cách phân lớp thường gặp là:

- Controller xử lý giao thức và đầu vào của giao diện.
- Application service điều phối ca sử dụng.
- Domain model thực thi các quy tắc nghiệp vụ cốt lõi.
- Repository hoặc adapter đảm nhiệm việc truy cập hệ thống lưu trữ hay dịch vụ bên ngoài.
- View hoặc serializer tạo biểu diễn phản hồi.

Cấu trúc cụ thể có thể thay đổi theo framework. Điều quan trọng là hợp đồng và trách nhiệm rõ ràng, không phải số lượng lớp hay tên package.

## 6. Những nhầm lẫn thường gặp

**“Dùng MVC nghĩa là hệ thống đã có kiến trúc hoàn chỉnh.”**  
Không đúng. MVC giúp tổ chức một phần luồng tương tác. Hệ thống vẫn cần quyết định về phân lớp, mô-đun, dữ liệu, tích hợp, triển khai và vận hành.

**“Model chính là cơ sở dữ liệu.”**  
Không chính xác. Model là khái niệm về trạng thái và quy tắc của ứng dụng. Entity lưu trữ chỉ là một cách biểu diễn dữ liệu; request DTO và view model có mục đích khác.

**“Controller nên chứa toàn bộ nghiệp vụ vì nó nhận request.”**  
Cách làm này khiến controller phình to, khó tái sử dụng và khó kiểm thử. Controller nên điều phối; quy tắc nghiệp vụ thuộc domain hoặc application service phù hợp.

**“Có ba thành phần MVC thì phải có đúng ba package hoặc ba lớp.”**  
MVC là cách phân chia trách nhiệm, không phải quy định cứng về cấu trúc thư mục. Một hệ thống có thể có nhiều controller, nhiều view, nhiều model và các lớp hỗ trợ.

**“MVC quyết định ứng dụng là monolith hay microservices.”**  
Không. Đây là quyết định ở cấp kiến trúc toàn hệ thống. Một ứng dụng monolith hoặc một dịch vụ trong hệ microservices đều có thể tổ chức phần giao diện bằng MVC.

## 7. Cách xác định một quyết định thuộc phạm vi nào

Khi xem xét một thay đổi, hãy xác định câu hỏi mà thay đổi đó cần trả lời:

- Nếu câu hỏi là “form nhận dữ liệu gì?”, “controller nào xử lý route này?”, “màn hình hiển thị lỗi ra sao?” hoặc “view cần dữ liệu nào?”, đó thường là quyết định trong phạm vi MVC.
- Nếu câu hỏi là “dịch vụ nào sở hữu dữ liệu đăng ký?”, “thanh toán giao tiếp qua API hay sự kiện?”, “dịch vụ được triển khai độc lập thế nào?” hoặc “hệ thống chịu lỗi khi một dịch vụ ngừng hoạt động ra sao?”, đó là quyết định ở cấp kiến trúc toàn hệ thống.
- Nếu một quyết định chạm cả hai phạm vi, hãy mô tả rõ hợp đồng giữa chúng. Chẳng hạn, MVC có thể trả trạng thái “đang xử lý” cho người dùng, còn kiến trúc hệ thống quyết định việc xử lý đăng ký được thực hiện bất đồng bộ qua hàng đợi.

Cách phân biệt này giúp tránh đưa chi tiết hạ tầng vào controller hoặc để giao diện tự quyết định các quy tắc thuộc nghiệp vụ và hệ thống.

## Kết luận

MVC là mẫu kiến trúc tổ chức trách nhiệm trong luồng tương tác: Controller tiếp nhận và điều phối, Model đại diện trạng thái cùng quy tắc liên quan, còn View trình bày kết quả. Kiến trúc toàn hệ thống xác định cấu trúc rộng hơn của sản phẩm, ranh giới thành phần, giao tiếp, dữ liệu, triển khai và các thuộc tính vận hành.

MVC có thể là một phần của kiến trúc layered monolith, modular monolith hoặc microservices. Khi thiết kế ứng dụng web, hãy dùng MVC để làm rõ đường đi của request và response; đồng thời đưa ra các quyết định về dịch vụ, dữ liệu và vận hành ở đúng phạm vi kiến trúc toàn hệ thống.
