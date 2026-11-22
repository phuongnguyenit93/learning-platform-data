# Chi phí phối hợp và giới hạn của việc chia thành ba thành phần

MVC (Model–View–Controller) tổ chức ứng dụng thành ba nhóm trách nhiệm: Model quản lý trạng thái và quy tắc của ứng dụng, View trình bày dữ liệu, còn Controller tiếp nhận tương tác và điều phối luồng xử lý. Cách chia này giúp một thay đổi ở giao diện ít làm xáo trộn nghiệp vụ, đồng thời giúp kiểm thử từng phần dễ hơn.

Tuy nhiên, việc tách thành ba thành phần tạo ra chi phí phối hợp. Một yêu cầu phải đi qua các ranh giới, dữ liệu phải tuân theo hợp đồng chung, và một thay đổi có thể cần cập nhật nhiều nơi. Vì vậy, MVC là cách quản lý độ phức tạp chứ không phải quy tắc rằng mọi chức năng đều phải có đúng ba lớp hoặc ba tệp riêng. Người thiết kế cần cân bằng lợi ích của việc phân tách với chi phí mà các ranh giới đó tạo ra.

## 1. Ba thành phần có trách nhiệm gì?

Trong ứng dụng web, có thể hiểu ba thành phần như sau:

| Thành phần | Trách nhiệm chính | Ví dụ |
|---|---|---|
| **Model** | Đại diện trạng thái, dữ liệu và quy tắc nghiệp vụ; cung cấp các thao tác mà ứng dụng cần thực hiện | Đối tượng đơn hàng, quy tắc tính tổng tiền, dịch vụ tạo đơn, kho lưu trữ |
| **View** | Biểu diễn dữ liệu thành nội dung mà người dùng hoặc máy khách có thể đọc | Trang HTML, mẫu hiển thị danh sách, cấu trúc JSON trả về API |
| **Controller** | Tiếp nhận yêu cầu, chuyển dữ liệu đầu vào, gọi nghiệp vụ phù hợp và chọn phản hồi | Đọc tham số từ HTTP request, gọi dịch vụ tạo đơn, trả trang kết quả hoặc chuyển hướng |

Model không nhất thiết là một lớp duy nhất. Trong một ứng dụng thực tế, phần Model có thể bao gồm đối tượng miền, dịch vụ ứng dụng và thành phần truy cập dữ liệu. Các thành phần này cùng phục vụ trạng thái và hành vi của ứng dụng, dù mỗi thành phần có trách nhiệm nội bộ riêng.

Tương tự, View không nhất thiết chỉ là tệp HTML. Với ứng dụng web trả JSON, phần biểu diễn phản hồi vẫn đảm nhận vai trò trình bày dữ liệu. Controller cũng không nên trở thành nơi chứa toàn bộ nghiệp vụ: nhiệm vụ của nó là điều phối yêu cầu tại ranh giới giao tiếp.

Cần chú ý đến cách một framework đặt tên. Chẳng hạn, tham số **Model** trong Spring MVC thường là nơi Controller đặt dữ liệu để mẫu giao diện sử dụng. Đối tượng đó là vật mang dữ liệu cho View trong một request; nó không đồng nghĩa với toàn bộ Model theo nghĩa kiến trúc MVC.

## 2. Chi phí phối hợp xuất hiện ở đâu?

### 2.1. Một yêu cầu phải đi qua nhiều ranh giới

Một request thường bắt đầu ở Controller, đi đến phần xử lý nghiệp vụ trong Model, có thể truy cập cơ sở dữ liệu, rồi quay lại Controller để tạo phản hồi cho View.

~~~mermaid
flowchart LR
    A["HTTP request"] --> B["Controller"]
    B --> C["Model / use case"]
    C --> D["Repository / dữ liệu"]
    D --> C
    C --> B
    B --> E["View / response"]
    E --> F["HTTP response"]
~~~

Mỗi lần chuyển giao đều cần quy định rõ dữ liệu nào được truyền, thao tác nào được gọi và lỗi nào có thể xuất hiện. Với ứng dụng nhỏ, số lần chuyển giao có thể nhiều hơn lượng nghiệp vụ thực sự cần xử lý. Khi đó, cấu trúc trở nên rườm rà: Controller chỉ chuyển tiếp một lời gọi, Model chỉ bọc một đối tượng dữ liệu, còn View chỉ hiển thị một trường.

Chi phí lớn nhất thường không phải thời gian chạy của một lời gọi hàm nội bộ. Chi phí đáng kể hơn là thời gian đọc hiểu luồng xử lý, lần theo dữ liệu qua nhiều lớp và giữ cho các hợp đồng giữa chúng nhất quán.

### 2.2. Các thành phần phải thống nhất hợp đồng dữ liệu

Controller, Model và View thường sử dụng các dạng dữ liệu khác nhau vì mục đích khác nhau:

- Dữ liệu biểu mẫu mô tả những gì người dùng gửi lên.
- Lệnh hoặc tham số nghiệp vụ mô tả thao tác mà ứng dụng cần thực hiện.
- Đối tượng miền biểu diễn trạng thái và các quy tắc của nghiệp vụ.
- Dữ liệu dành cho View chỉ chứa những thông tin cần thiết để trình bày.

Việc chuyển đổi giữa các dạng dữ liệu giúp mỗi thành phần không phụ thuộc trực tiếp vào cấu trúc nội bộ của thành phần khác. Nhưng mỗi phép chuyển đổi cũng tạo thêm mã và thêm một hợp đồng cần duy trì.

Ví dụ, nếu View cần hiển thị tên khách hàng, Controller phải cung cấp trường đó trong dữ liệu dành cho View. Nếu tên trường bị đổi hoặc ý nghĩa của nó thay đổi, nơi tạo dữ liệu và nơi sử dụng dữ liệu phải được cập nhật đồng bộ. Một hợp đồng không rõ ràng dễ dẫn đến lỗi như View đọc trường không tồn tại, Controller truyền dữ liệu chưa được chuẩn hóa hoặc Model nhận đầu vào sai định dạng.

### 2.3. Một thay đổi có thể lan qua nhiều thành phần

Giả sử biểu mẫu tạo công việc đổi trường **title** thành **summary**. Thay đổi này có thể tác động đến:

1. View: tên trường nhập liệu và thông báo lỗi.
2. Controller: đối tượng nhận dữ liệu biểu mẫu và quy tắc binding.
3. Model hoặc dịch vụ ứng dụng: cách tiếp nhận lệnh tạo công việc.
4. Phần lưu trữ: tên thuộc tính hoặc ánh xạ dữ liệu, nếu cấu trúc lưu trữ cũng thay đổi.

Không phải thay đổi nào cũng cần chạm cả ba thành phần. Một giao diện đổi màu có thể chỉ tác động đến View; một quy tắc tính phí có thể chỉ tác động đến Model. Nhưng nếu hợp đồng dữ liệu giữa các phần thay đổi, các bên liên quan phải cùng được cập nhật.

Đây là chi phí phối hợp cốt lõi: các thành phần được tách ra để giảm phụ thuộc, nhưng vẫn phải cộng tác thông qua những hợp đồng ổn định.

### 2.4. Dễ phát sinh chuyển đổi và kiểm tra trùng lặp

Nếu ranh giới không được thiết kế rõ, cùng một dữ liệu có thể bị kiểm tra hoặc chuyển đổi ở nhiều nơi. Chẳng hạn, Controller kiểm tra chuỗi không rỗng, dịch vụ kiểm tra lại chuỗi không rỗng, rồi View tự viết thêm logic để quyết định có cho phép gửi biểu mẫu hay không.

Một số kiểm tra ở nhiều tầng là cần thiết vì chúng bảo vệ các ranh giới khác nhau. Kiểm tra định dạng đầu vào giúp phản hồi sớm cho người dùng; quy tắc trong Model bảo vệ tính hợp lệ của nghiệp vụ dù thao tác đến từ giao diện web, API hay một tác vụ nền. Tuy vậy, sao chép cùng một quy tắc ở nhiều nơi sẽ khiến các phiên bản dần khác nhau.

### 2.5. Kiểm thử và gỡ lỗi cần xét cả ranh giới

Tách thành phần giúp kiểm thử đơn vị tập trung hơn, nhưng không loại bỏ nhu cầu kiểm thử tích hợp. Một Model đúng vẫn có thể không hoạt động với Controller nếu Controller truyền sai dữ liệu. Một Controller trả đúng tên View vẫn có thể thất bại nếu View cần một thuộc tính mà Controller không cung cấp.

Khi gỡ lỗi, người phát triển cần xác định lỗi phát sinh ở bước nhận request, kiểm tra đầu vào, xử lý nghiệp vụ, truy cập dữ liệu hay dựng phản hồi. Nếu luồng gọi bị chia thành quá nhiều lớp mỏng, việc lần theo lỗi có thể tốn thời gian hơn lợi ích mà cấu trúc mang lại.

## 3. Những giới hạn thường gặp của cách chia MVC

### 3.1. Tách quá mức đối với chức năng đơn giản

Một chức năng chỉ đọc một giá trị cấu hình và hiển thị lên trang có thể không cần nhiều lớp trung gian. Nếu mỗi thao tác đều tạo một Controller, một lớp Model, một dịch vụ, một giao diện repository và một lớp chuyển đổi riêng dù không có trách nhiệm độc lập, số lượng tệp tăng nhanh nhưng khả năng thay đổi an toàn không tăng tương ứng.

Dấu hiệu của việc tách quá mức:

- Controller chỉ gọi đúng một phương thức rồi trả kết quả, không có điều phối đáng kể.
- Các lớp trung gian không bổ sung quy tắc, hợp đồng hay điểm kiểm thử hữu ích.
- Người đọc phải mở nhiều tệp mới hiểu được một thao tác đơn giản.
- Mỗi thay đổi nhỏ đòi hỏi sửa nhiều lớp chỉ để chuyển cùng một dữ liệu.

Có thể bắt đầu với cấu trúc đơn giản, sau đó tách thêm khi một trách nhiệm thực sự phát triển hoặc cần được tái sử dụng. Số lượng lớp không phải thước đo chất lượng kiến trúc.

### 3.2. Controller phình to khi nghiệp vụ bị đặt sai chỗ

Controller thường biết nhiều về giao thức HTTP: đường dẫn, tham số, session, mã trạng thái và kiểu phản hồi. Nếu Controller đồng thời quyết định chính sách nghiệp vụ, tính toán giá, kiểm tra quyền theo quy tắc miền và thao tác trực tiếp với dữ liệu, nó sẽ trở nên khó kiểm thử và khó tái sử dụng.

Ví dụ, quy tắc “không cho phép hủy đơn hàng đã giao” nên được bảo vệ trong phần nghiệp vụ của Model hoặc dịch vụ ứng dụng. Nếu chỉ kiểm tra trong Controller của một trang web, một API hoặc tác vụ nền khác có thể vô tình bỏ qua quy tắc đó.

Controller nên xử lý những việc gắn với request và điều phối thao tác. Quy tắc quyết định trạng thái hợp lệ của nghiệp vụ cần được bảo vệ ở phần Model, nơi mọi luồng gọi có thể sử dụng chung.

### 3.3. View chứa logic nghiệp vụ

View cần một lượng logic trình bày nhất định, chẳng hạn định dạng ngày tháng, hiển thị trạng thái hoặc chọn nhánh hiển thị khi không có dữ liệu. Nhưng nếu View tự tính quyền được mua hàng, tự quyết định giảm giá hoặc thay đổi trạng thái đơn hàng, trách nhiệm nghiệp vụ đã bị đẩy sang giao diện.

Logic như vậy khó tái sử dụng khi ứng dụng có thêm một View khác, chẳng hạn trang quản trị hoặc API. View nên tập trung vào cách trình bày kết quả đã được chuẩn bị; nó không nên là nơi quyết định tính đúng đắn của nghiệp vụ.

### 3.4. Model trở thành một khối quá rộng hoặc bị phụ thuộc vào giao diện

Một Model chứa mọi thứ từ quy tắc nghiệp vụ, truy vấn cơ sở dữ liệu đến chi tiết HTML sẽ tạo ra một khối có nhiều lý do để thay đổi. Ngược lại, nếu Model chỉ là tập hợp các trường dữ liệu không có nơi bảo vệ quy tắc, nghiệp vụ có thể bị phân tán sang Controller và View.

Model cũng không nên buộc phải biết chi tiết của một trang cụ thể. Nếu một đối tượng lưu trữ được truyền thẳng ra View, các trường nội bộ có thể vô tình bị công khai hoặc khiến giao diện phụ thuộc vào cấu trúc cơ sở dữ liệu. Dữ liệu dành cho View nên được chọn lọc theo nhu cầu trình bày.

### 3.5. MVC không tự giải quyết mọi vấn đề kiến trúc

MVC chủ yếu tổ chức trách nhiệm trong ứng dụng. Nó không tự quyết định cách chia hệ thống thành microservice, cách triển khai nhiều máy chủ, cách xử lý hàng đợi, tính nhất quán dữ liệu hay chiến lược cache. Chia một ứng dụng thành Model, View và Controller không có nghĩa là phải triển khai ba dịch vụ độc lập.

MVC cũng không tự bảo đảm bảo mật. Controller cần xử lý request đúng cách và phối hợp với cơ chế xác thực, phân quyền; Model cần bảo vệ các quy tắc và quyền hạn liên quan đến nghiệp vụ; View cần escape đầu ra theo ngữ cảnh để tránh nội dung không tin cậy bị diễn giải như mã thực thi. Bảo mật cần được thiết kế xuyên suốt luồng xử lý.

## 4. Ví dụ: tạo một công việc từ biểu mẫu web

Xét chức năng cho phép người dùng nhập tiêu đề để tạo một công việc mới. Mỗi thành phần có thể đảm nhận phần việc sau:

- **View** hiển thị biểu mẫu, trường tiêu đề và lỗi nhập liệu.
- **Controller** nhận request, ràng buộc dữ liệu vào đối tượng biểu mẫu, kiểm tra lỗi đầu vào và gọi thao tác tạo công việc.
- **Model** thực hiện quy tắc tạo công việc, bảo vệ điều kiện hợp lệ và lưu dữ liệu.

Ví dụ dưới đây dùng phong cách Spring MVC để minh họa ranh giới trách nhiệm. Các import và cấu hình ứng dụng được lược bỏ để tập trung vào luồng xử lý.

~~~java
record CreateTaskForm(
    @NotBlank
    @Size(max = 120)
    String title
) {}

@Controller
@RequestMapping("/tasks")
class TaskController {
    private final TaskService taskService;

    TaskController(TaskService taskService) {
        this.taskService = taskService;
    }

    @GetMapping("/new")
    String newForm(org.springframework.ui.Model viewModel) {
        viewModel.addAttribute("form", new CreateTaskForm(""));
        return "tasks/new";
    }

    @PostMapping
    String create(
        @Valid @ModelAttribute("form") CreateTaskForm form,
        BindingResult errors
    ) {
        if (errors.hasErrors()) {
            return "tasks/new";
        }

        taskService.create(form.title());
        return "redirect:/tasks";
    }
}
~~~

Controller hiểu cấu trúc request và kết quả kiểm tra biểu mẫu. Khi dữ liệu không đạt yêu cầu đầu vào, nó trả lại View để người dùng sửa. Khi dữ liệu hợp lệ, nó chuyển thao tác cho dịch vụ nghiệp vụ. Controller không tự quyết định cách lưu công việc.

Phần Model có thể bảo vệ quy tắc của công việc và điều phối việc lưu trữ:

~~~java
final class Task {
    private final String title;

    Task(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Tiêu đề không được để trống");
        }
        this.title = title;
    }

    String title() {
        return title;
    }
}

interface TaskRepository {
    void save(Task task);
}

@Service
class TaskService {
    private final TaskRepository repository;

    TaskService(TaskRepository repository) {
        this.repository = repository;
    }

    void create(String rawTitle) {
        String normalizedTitle = rawTitle == null ? "" : rawTitle.trim();
        Task task = new Task(normalizedTitle);
        repository.save(task);
    }
}
~~~

Trong ví dụ, **@NotBlank** giúp phản hồi lỗi biểu mẫu sớm tại ranh giới web. Kiểm tra trong **Task** bảo vệ bất biến của đối tượng miền, kể cả khi công việc được tạo từ một luồng khác không đi qua Controller này. Hai kiểm tra có mục đích khác nhau; nếu quy tắc thay đổi, chúng cần được xem xét đồng bộ để tránh mâu thuẫn.

View có thể hiển thị biểu mẫu và lỗi như sau:

~~~html
<form method="post" th:action="@{/tasks}" th:object="${form}">
    <label for="title">Tiêu đề công việc</label>
    <input id="title" type="text" th:field="*{title}">
    <span th:if="${#fields.hasErrors('title')}"
          th:errors="*{title}"></span>
    <button type="submit">Tạo công việc</button>
</form>
~~~

Luồng xử lý cho thấy lợi ích và chi phí của MVC cùng xuất hiện. View không cần biết cách lưu dữ liệu; Model không cần biết biểu mẫu được trình bày ra sao; Controller kết nối hai phía. Đổi cách trình bày biểu mẫu có thể không ảnh hưởng đến Model. Nhưng nếu hợp đồng đầu vào đổi từ **title** sang một cấu trúc khác, Controller và View cần được cập nhật cùng nhau.

Ví dụ này cũng cho thấy tên **viewModel** trong Controller được dùng có chủ đích: đó là đối tượng mang dữ liệu cho View của Spring MVC, không phải toàn bộ phần Model chứa quy tắc nghiệp vụ.

## 5. Cách giảm chi phí phối hợp

### 5.1. Đặt ranh giới theo trách nhiệm và lý do thay đổi

Trước khi tạo một lớp mới, hãy xác định lớp đó sở hữu quyết định nào. Nếu một đoạn mã thay đổi vì quy tắc nghiệp vụ đổi, nó thường thuộc phần Model. Nếu thay đổi vì cách trình bày, nó thường thuộc View. Nếu thay đổi vì cách nhận request hoặc chọn phản hồi, nó thường thuộc Controller.

Một lớp mới hữu ích khi nó tạo ra ranh giới có ý nghĩa: có trách nhiệm rõ, có thể được kiểm thử độc lập hoặc được dùng bởi nhiều luồng. Nếu lớp chỉ chuyển tiếp dữ liệu mà không tạo ra lợi ích nào, hãy cân nhắc giữ cấu trúc đơn giản hơn.

### 5.2. Thiết kế hợp đồng nhỏ và rõ ràng

Dữ liệu đi qua ranh giới nên thể hiện đúng nhu cầu của bên nhận. Dùng đối tượng biểu mẫu hoặc DTO để nhận dữ liệu từ request; dùng đối tượng miền để bảo vệ quy tắc; dùng dữ liệu dành cho View để trình bày. Không đưa toàn bộ đối tượng lưu trữ ra ngoài chỉ vì tiện.

Hợp đồng cần làm rõ tên trường, kiểu dữ liệu, trường bắt buộc, ý nghĩa giá trị, lỗi có thể xảy ra và trách nhiệm xử lý lỗi. Khi hợp đồng nhỏ, thay đổi nội bộ của một thành phần ít ảnh hưởng đến phần còn lại.

### 5.3. Phân biệt kiểm tra đầu vào với quy tắc nghiệp vụ

Kiểm tra đầu vào tập trung vào việc dữ liệu gửi đến có đúng định dạng và đủ điều kiện để xử lý hay không. Quy tắc nghiệp vụ xác định thao tác có hợp lệ trong trạng thái hiện tại của ứng dụng hay không.

Ví dụ, chuỗi tiêu đề không được để trống là một điều kiện có thể kiểm tra ở biểu mẫu để người dùng nhận phản hồi nhanh, đồng thời được bảo vệ trong đối tượng miền. Nhưng điều kiện “công việc đã hoàn thành thì không được sửa tiêu đề” phải được kiểm tra trong nghiệp vụ vì nó phụ thuộc trạng thái của công việc.

### 5.4. Giữ lỗi có cấu trúc và xử lý đúng tầng

Model hoặc dịch vụ nghiệp vụ nên trả kết quả hoặc phát sinh lỗi có ý nghĩa đối với thao tác. Controller chuyển lỗi đó thành phản hồi phù hợp với giao thức: hiển thị lại biểu mẫu, trả mã trạng thái, chuyển hướng hoặc hiển thị trang lỗi. View trình bày thông báo đã được chuẩn bị.

Không nên để View tự phân tích thông báo lỗi kỹ thuật, cũng không nên trả chi tiết exception nội bộ cho người dùng. Thông báo cho người dùng cần rõ ràng; thông tin kỹ thuật phục vụ chẩn đoán nên được ghi log phù hợp.

### 5.5. Kiểm thử theo ranh giới và kiểm thử luồng hoàn chỉnh

Có thể phân chia kiểm thử theo trách nhiệm:

| Phạm vi kiểm thử | Điều cần xác minh |
|---|---|
| Model / dịch vụ nghiệp vụ | Quy tắc, trạng thái hợp lệ, điều kiện từ chối và thao tác dữ liệu |
| Controller | Định tuyến, binding, xử lý lỗi đầu vào, phân quyền và loại phản hồi |
| View | Dữ liệu cần thiết được hiển thị, trạng thái rỗng và nội dung không tin cậy được xử lý an toàn |
| Tích hợp | Request thực tế đi qua các thành phần và tạo ra phản hồi đúng |

Kiểm thử đơn vị giúp phát hiện lỗi trong một trách nhiệm. Kiểm thử tích hợp xác minh hợp đồng giữa các trách nhiệm. Một số luồng quan trọng vẫn cần kiểm thử từ request đến response để phát hiện lỗi cấu hình, binding hoặc ánh xạ dữ liệu.

## 6. Khi nào lợi ích của MVC lớn hơn chi phí?

Việc tách ba thành phần thường có ích khi ứng dụng có nhiều luồng tương tác, quy tắc nghiệp vụ đáng kể, nhiều kiểu trình bày hoặc các phần thay đổi với nhịp độ khác nhau. Khi đó, ranh giới rõ ràng giúp giới hạn phạm vi thay đổi và hỗ trợ kiểm thử.

Ngược lại, với một chức năng rất nhỏ, ít quy tắc và chỉ có một cách trình bày, việc tạo quá nhiều lớp trung gian có thể làm tăng công sức đọc và bảo trì. Có thể bắt đầu bằng cấu trúc tối thiểu nhưng vẫn giữ nguyên tắc: giao diện không sở hữu nghiệp vụ, request không quyết định trực tiếp trạng thái miền, và dữ liệu được truyền qua các hợp đồng dễ hiểu.

Một số câu hỏi hữu ích trước khi tách thêm thành phần:

- Thành phần mới có một trách nhiệm riêng và lý do thay đổi riêng không?
- Nó có giảm phụ thuộc hoặc giúp kiểm thử dễ hơn không?
- Hợp đồng dữ liệu giữa bên gửi và bên nhận có rõ ràng không?
- Khi một trường hoặc quy tắc thay đổi, có thể xác định chính xác những nơi cần cập nhật không?
- Số lớp trung gian có khiến một luồng đơn giản trở nên khó lần theo không?
- Quy tắc nghiệp vụ có được bảo vệ dù request đến từ nhiều giao diện khác nhau không?

Nếu câu trả lời cho các câu hỏi này cho thấy ranh giới đang giúp kiểm soát thay đổi, việc phân tách có giá trị. Nếu các lớp chỉ tồn tại theo hình thức và không làm rõ trách nhiệm, nên đơn giản hóa.

## 7. Những điểm cần ghi nhớ

MVC giảm sự phụ thuộc trực tiếp giữa dữ liệu và nghiệp vụ, cách trình bày, cũng như cách tiếp nhận tương tác. Đổi lại, các thành phần phải phối hợp qua hợp đồng dữ liệu, luồng gọi và cách xử lý lỗi. Chi phí đó thể hiện ở mã chuyển đổi, việc cập nhật đồng bộ, kiểm thử tích hợp và thời gian lần theo request.

Chất lượng của MVC phụ thuộc vào ranh giới trách nhiệm, không phụ thuộc vào số lượng lớp hay thư mục. Model cần bảo vệ quy tắc ứng dụng; View cần tập trung vào trình bày; Controller cần điều phối request và phản hồi. Khi một thành phần ôm trách nhiệm của phần khác hoặc khi ứng dụng bị chia quá vụn, lợi ích của phân tách sẽ giảm.

Hãy dùng MVC để làm cho thay đổi dễ định vị, hợp đồng dễ hiểu và hành vi dễ kiểm thử. Chỉ tạo thêm ranh giới khi nó giải quyết được một vấn đề thực tế của ứng dụng.
