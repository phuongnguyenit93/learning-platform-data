# Ranh giới giữa View, ViewModel và bộ chuyển đổi dữ liệu

Trong MVC, View chịu trách nhiệm trình bày thông tin cho người dùng. Nhưng dữ liệu mà nghiệp vụ lưu trữ thường không có cấu trúc phù hợp để hiển thị trực tiếp: một đối tượng miền có thể chứa nhiều thuộc tính nội bộ, quan hệ đến các đối tượng khác và quy tắc không liên quan đến màn hình hiện tại. Nếu View phụ thuộc trực tiếp vào cấu trúc đó, giao diện sẽ khó thay đổi và có thể vô tình để lộ dữ liệu.

Một cách tổ chức rõ ràng là đặt một mô hình trình bày ở giữa phần nghiệp vụ và View. Mô hình này thường được gọi là **ViewModel** hoặc **presentation model**. **Bộ chuyển đổi dữ liệu (mapper)** chịu trách nhiệm biến dữ liệu từ phía nghiệp vụ thành cấu trúc mà View cần; ở chiều gửi dữ liệu, mapper có thể chuyển dữ liệu biểu mẫu thành lệnh ứng dụng. ViewModel và mapper tạo ra một hợp đồng tường minh giữa phần trình bày với phần còn lại của ứng dụng.

Cần phân biệt cách dùng từ trong từng framework. Trong Spring MVC, đối tượng **org.springframework.ui.Model** là nơi Controller đặt các thuộc tính để View sử dụng trong một request. Nó là một vùng chứa dữ liệu cho template, không phải một lớp ViewModel cụ thể và cũng không phải toàn bộ Model theo nghĩa kiến trúc MVC. Bài này dùng từ ViewModel theo nghĩa mô hình dữ liệu dành riêng cho một màn hình hoặc một phản hồi.

## 1. Ranh giới trách nhiệm của View, ViewModel và mapper

Ba khái niệm có quan hệ gần nhau nhưng giải quyết các vấn đề khác nhau:

| Thành phần | Trách nhiệm | Nên biết | Không nên sở hữu |
|---|---|---|---|
| **View** | Hiển thị dữ liệu và thu nhận tương tác | Cấu trúc ViewModel, trạng thái hiển thị, thông báo dành cho người dùng | Truy vấn cơ sở dữ liệu, quy tắc nghiệp vụ, quyết định phân quyền |
| **ViewModel** | Mô tả dữ liệu và trạng thái cần cho một View | Các trường mà màn hình cần, kiểu dữ liệu trình bày | Kết nối cơ sở dữ liệu, điều phối request, hành vi lưu nghiệp vụ |
| **Mapper** | Chuyển đổi giữa các cấu trúc dữ liệu ở hai ranh giới | Cấu trúc nguồn và đích, quy tắc chuyển đổi mang tính biểu diễn | Quyết định nghiệp vụ cốt lõi, truy cập dữ liệu, bỏ qua kiểm tra quyền |

Ví dụ, màn hình chi tiết công việc có thể cần tiêu đề, nhãn trạng thái, ngày đến hạn đã định dạng và thông tin có hiển thị nút chỉnh sửa hay không. Đối tượng miền Task có thể chứa mã trạng thái, thời điểm tạo, thông tin chủ sở hữu và nhiều dữ liệu nội bộ khác. ViewModel chỉ giữ những trường mà màn hình chi tiết cần.

View sử dụng ViewModel để dựng giao diện. Mapper chuyển dữ liệu từ đối tượng nghiệp vụ sang ViewModel. Controller hoặc dịch vụ trình bày phối hợp các thành phần để lấy dữ liệu và tạo phản hồi. Cách phân chia này giúp mỗi bên có một hợp đồng dễ hiểu.

### ViewModel không đồng nghĩa với mọi loại Model

Tên gọi Model xuất hiện ở nhiều cấp độ:

- **Domain Model** mô tả khái niệm, trạng thái và quy tắc nghiệp vụ.
- **Persistence Model / Entity** phản ánh cách dữ liệu được ánh xạ và lưu trữ, chẳng hạn một JPA entity.
- **Request Model / Form Object** mô tả dữ liệu nhận từ biểu mẫu hoặc request.
- **ViewModel / Presentation Model** mô tả dữ liệu mà một View cần để trình bày.
- **org.springframework.ui.Model** trong Spring MVC là vùng chứa thuộc tính được đưa vào View trong request hiện tại.

Các loại đối tượng này có thể có một số trường giống nhau, nhưng mục đích và vòng đời khác nhau. Không nên dùng chung một lớp chỉ vì nó có các thuộc tính trùng tên.

ViewModel trong bài này cũng không nhất thiết là ViewModel của kiến trúc MVVM. Trong MVVM, ViewModel thường còn giữ trạng thái tương tác và hành vi phục vụ binding với View. Trong ứng dụng Spring MVC truyền thống, một ViewModel có thể chỉ là một DTO bất biến được tạo cho một lần render.

## 2. Vì sao không nên đưa trực tiếp đối tượng nghiệp vụ vào View?

Truyền thẳng entity hoặc đối tượng miền vào template có vẻ tiện vì không cần viết lớp trung gian. Tuy nhiên, cách làm đó tạo ra một số rủi ro.

### 2.1. View phụ thuộc vào cấu trúc nội bộ

Giả sử entity Task đổi tên thuộc tính, thay quan hệ hoặc chuyển cách lưu trạng thái. Nếu template truy cập trực tiếp vào các thuộc tính đó, thay đổi lưu trữ có thể kéo theo thay đổi giao diện dù nhu cầu trình bày không đổi.

ViewModel tạo một hợp đồng ổn định hơn. Phần nghiệp vụ có thể thay đổi cách tổ chức nội bộ, mapper chịu trách nhiệm cập nhật việc chuyển đổi, còn View tiếp tục sử dụng những trường đã được cam kết.

### 2.2. Có thể để lộ dữ liệu ngoài ý muốn

Một entity có thể chứa email riêng tư, ghi chú nội bộ, mã định danh, thông tin kiểm toán hoặc các quan hệ không dành cho người dùng hiện tại. Khi trả nguyên entity ra View hoặc serialize trực tiếp thành JSON, một trường mới được thêm vào có thể vô tình trở thành dữ liệu công khai.

ViewModel dùng nguyên tắc cho phép rõ ràng: chỉ khai báo trường thực sự cần thiết cho phản hồi. Việc thêm thuộc tính vào entity không tự động làm thuộc tính đó xuất hiện trong giao diện hoặc API.

### 2.3. Có thể kích hoạt truy cập dữ liệu ngoài dự kiến

Với ORM có quan hệ tải lười, template đọc một thuộc tính liên kết có thể kích hoạt truy vấn bổ sung. Một danh sách nhiều phần tử có thể gây ra vấn đề N+1 query hoặc lỗi khi session đã đóng. ViewModel được dựng ở ranh giới ứng dụng giúp lấy đúng dữ liệu cần thiết trước khi render và tránh để template vô tình điều khiển truy cập cơ sở dữ liệu.

### 2.4. Khó biểu diễn đúng ngôn ngữ của giao diện

Đối tượng miền thường lưu mã trạng thái như OPEN, IN_PROGRESS hoặc DONE. View có thể cần nhãn tiếng Việt, ngày tháng theo múi giờ của người dùng, hoặc một cờ cho biết nút hành động có nên xuất hiện. Những giá trị trình bày này không nhất thiết là thuộc tính của đối tượng miền.

ViewModel có thể cung cấp statusLabel, dueDateText và canEdit. Nhờ vậy, View tập trung vào cách hiển thị thay vì tự diễn giải mã nghiệp vụ.

## 3. ViewModel nên được thiết kế như thế nào?

Một ViewModel tốt phản ánh nhu cầu của một View hoặc một nhóm View có hợp đồng giống nhau. Nó không cần sao chép toàn bộ cấu trúc của entity.

Ví dụ, màn hình chi tiết công việc có thể dùng:

~~~java
public record TaskDetailsViewModel(
    String title,
    String statusLabel,
    String dueDateText,
    boolean canEdit
) {}
~~~

Các trường có ý nghĩa trực tiếp đối với màn hình:

- **title** là tiêu đề đã được chuẩn bị để hiển thị.
- **statusLabel** là nhãn trạng thái thân thiện với người dùng.
- **dueDateText** là ngày đến hạn đã được định dạng.
- **canEdit** cho biết giao diện có nên hiển thị điều khiển chỉnh sửa hay không.

Một ViewModel khác có thể phục vụ bảng danh sách công việc:

~~~java
public record TaskRowViewModel(
    long id,
    String title,
    String statusLabel,
    String dueDateText
) {}
~~~

Hai ViewModel này có thể cùng lấy dữ liệu từ Task nhưng phục vụ hai mục đích khác nhau. Màn hình chi tiết cần thông tin về khả năng chỉnh sửa; bảng danh sách có thể chỉ cần mã định danh để tạo liên kết và một số cột ngắn gọn.

Không nên tạo một ViewModel khổng lồ dùng cho mọi màn hình nếu mỗi màn hình cần tập trường và ý nghĩa khác nhau. Cũng không cần tạo lớp mới cho từng View nếu hợp đồng dữ liệu thực sự giống nhau và việc dùng chung không làm các màn hình phụ thuộc vào những trường không liên quan.

### 3.1. ViewModel thường là dữ liệu bất biến

ViewModel được tạo để mô tả kết quả của một lần chuẩn bị giao diện. Dùng record hoặc các trường chỉ đọc giúp hợp đồng rõ ràng và tránh View vô tình thay đổi trạng thái nghiệp vụ.

View có thể có trạng thái tương tác riêng như giá trị ô đang được chọn, tab đang mở hoặc thông báo đang hiển thị. Những trạng thái tạm thời đó không nhất thiết phải ghi ngược vào ViewModel phản hồi từ máy chủ. Cần phân biệt trạng thái hiển thị trong trình duyệt với trạng thái nghiệp vụ được lưu trong ứng dụng.

### 3.2. Không đưa hành vi nghiệp vụ vào ViewModel

ViewModel có thể chứa dữ liệu trình bày như nhãn, cờ hiển thị hoặc chuỗi đã định dạng. Nó không nên tự thực hiện thao tác lưu, quyết định giá bán, thay đổi trạng thái đơn hàng hay truy vấn repository.

Nếu ViewModel chứa phương thức như approveOrder() hoặc calculateFinalPrice(), cần xem lại liệu hành vi đó có thuộc dịch vụ nghiệp vụ hoặc Model hay không. ViewModel nên giúp View trình bày và điều khiển tương tác ở mức giao diện; Controller hoặc dịch vụ ứng dụng tiếp nhận hành động và thực hiện quy tắc tương ứng.

## 4. Mapper chuyển đổi dữ liệu ở đâu?

Mapper là thành phần chuyển một cấu trúc dữ liệu sang một cấu trúc khác. Trong MVC, mapper thường nằm ở ranh giới giữa mô hình nghiệp vụ và mô hình trình bày, hoặc giữa dữ liệu đầu vào và lệnh ứng dụng.

Có thể hình dung hai hướng:

~~~mermaid
flowchart TD
    subgraph READ["Luồng đọc: chuẩn bị View"]
        A["Controller"] --> B["Application Service"]
        B --> C["Domain Model"]
        C --> D["View Mapper"]
        D --> E["ViewModel"]
        E --> F["View"]
    end
    subgraph WRITE["Luồng ghi: tiếp nhận biểu mẫu"]
        G["View / Form"] --> H["Form Object"]
        H --> I["Validation"]
        I --> J["Input Mapper"]
        J --> K["Application Command"]
        K --> L["Application Service"]
        L --> M["Domain Model"]
    end
~~~

Ở luồng đọc, mapper chuyển dữ liệu nghiệp vụ thành dữ liệu dành cho giao diện. Ở luồng ghi, dữ liệu biểu mẫu được binding vào một đối tượng đầu vào, được kiểm tra rồi chuyển thành command hoặc tham số ứng dụng. Hai hướng có mục đích khác nhau và thường nên dùng các kiểu dữ liệu riêng.

### 4.1. Mapper cho luồng đọc

Ví dụ mapper chuyển Task thành TaskDetailsViewModel:

~~~java
public class TaskViewMapper {

    public TaskDetailsViewModel toDetails(
        Task task,
        boolean canEdit
    ) {
        String statusLabel = switch (task.getStatus()) {
            case OPEN -> "Chưa bắt đầu";
            case IN_PROGRESS -> "Đang thực hiện";
            case DONE -> "Hoàn thành";
        };

        String dueDateText = task.getDueDate() == null
            ? "Chưa có thời hạn"
            : task.getDueDate().format(
                DateTimeFormatter.ofPattern("dd/MM/yyyy")
            );

        return new TaskDetailsViewModel(
            task.getTitle(),
            statusLabel,
            dueDateText,
            canEdit
        );
    }
}
~~~

Mapper nhận dữ liệu đã được lấy từ ứng dụng và chuyển các giá trị thành dạng View cần. Trong ví dụ, mã trạng thái được chuyển thành nhãn tiếng Việt và ngày được định dạng. Nếu cách trình bày ngày tháng thay đổi, có thể cập nhật mapper hoặc một thành phần định dạng dùng chung mà không cần sửa entity.

Định dạng ngày giờ thực tế cần cân nhắc múi giờ và locale của người dùng. Nếu ngày đến hạn là LocalDate thì không có phần múi giờ; nếu nguồn là Instant hoặc OffsetDateTime, cần chuyển sang múi giờ hiển thị trước khi định dạng. Quyết định múi giờ là một phần của hợp đồng trình bày, không nên để template tự đoán.

Cờ canEdit trong ví dụ được truyền vào mapper sau khi lớp ứng dụng hoặc thành phần phân quyền đã đánh giá ngữ cảnh. Mapper có thể đưa kết quả đó vào ViewModel, nhưng không phải nơi tự quyết định quyền truy cập. Khi người dùng gửi yêu cầu chỉnh sửa, máy chủ vẫn phải kiểm tra quyền trên request đó; ẩn nút trên giao diện không phải biện pháp bảo vệ.

### 4.2. Mapper cho dữ liệu biểu mẫu

Khi người dùng gửi biểu mẫu, dữ liệu nhận được là dữ liệu không đáng tin cậy. Nên binding vào một đối tượng đầu vào dành riêng cho biểu mẫu:

~~~java
public record UpdateTaskForm(
    @NotBlank
    @Size(max = 120)
    String title
) {}
~~~

Sau khi validation thành công, mapper chuyển form thành command:

~~~java
public record UpdateTaskCommand(String title) {}

public class TaskFormMapper {

    public UpdateTaskCommand toCommand(UpdateTaskForm form) {
        return new UpdateTaskCommand(form.title().trim());
    }
}
~~~

Controller điều phối request và chuyển tiếp command:

~~~java
@PostMapping("/{id}")
String update(
    @PathVariable long id,
    @Valid @ModelAttribute("form") UpdateTaskForm form,
    BindingResult errors
) {
    if (errors.hasErrors()) {
        return "tasks/edit";
    }

    taskService.update(id, taskFormMapper.toCommand(form));
    return "redirect:/tasks/" + id;
}
~~~

Ví dụ tập trung vào luồng dữ liệu; ứng dụng thực tế cần nạp lại các dữ liệu phụ của trang chỉnh sửa khi validation thất bại, đồng thời xử lý lỗi nghiệp vụ và lỗi không tìm thấy theo quy ước của ứng dụng.

Không nên binding trực tiếp request vào entity rồi lưu ngay. Cách đó có thể khiến người dùng gửi thêm các trường mà biểu mẫu không dự định cho phép thay đổi, chẳng hạn ownerId, role hoặc trạng thái phê duyệt. Form Object giới hạn tập trường đầu vào; command thể hiện rõ thao tác mà ứng dụng cho phép thực hiện.

## 5. Phân biệt binding, validation và mapping

Ba bước này thường xảy ra gần nhau nhưng không thay thế nhau:

| Bước | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| **Binding** | Dữ liệu request có được đọc vào đúng trường và kiểu dữ liệu không? | Chuỗi từ ô title được gán vào UpdateTaskForm.title |
| **Validation** | Dữ liệu có đáp ứng điều kiện đầu vào không? | title không rỗng và tối đa 120 ký tự |
| **Mapping** | Dữ liệu hợp lệ được biểu diễn thành cấu trúc mà bước tiếp theo cần như thế nào? | UpdateTaskForm thành UpdateTaskCommand |

Validation đầu vào không thay thế quy tắc nghiệp vụ. Form có thể hợp lệ về định dạng nhưng thao tác vẫn không hợp lệ trong trạng thái hiện tại. Ví dụ, tiêu đề mới có độ dài đúng nhưng công việc đã khóa thì không được sửa. Quy tắc đó phải được kiểm tra trong nghiệp vụ, ngay cả khi request đã vượt qua validation.

Mapper cũng không nên âm thầm sửa dữ liệu theo cách làm thay đổi ý nghĩa nghiệp vụ. Chuẩn hóa khoảng trắng có thể là quy ước đầu vào rõ ràng; tự thay đổi giá trị tiền tệ, trạng thái hoặc quyền hạn trong mapper có thể che giấu quyết định nghiệp vụ và làm khó kiểm toán.

## 6. Xử lý lỗi và thông báo cho View

ViewModel có thể mang dữ liệu cần thiết để hiển thị trạng thái lỗi, nhưng cần giữ rõ nguồn gốc của lỗi.

- Lỗi binding xảy ra khi dữ liệu request không thể chuyển thành kiểu đích, chẳng hạn một chuỗi không phải số được gửi vào trường số.
- Lỗi validation xảy ra khi dữ liệu đã binding nhưng vi phạm điều kiện đầu vào.
- Lỗi nghiệp vụ xảy ra khi thao tác không hợp lệ với trạng thái hiện tại, chẳng hạn không thể sửa công việc đã khóa.
- Lỗi hạ tầng xảy ra khi hệ thống gặp sự cố truy cập dữ liệu hoặc dịch vụ phụ thuộc.

Controller chuyển các lỗi phù hợp thành phản hồi cho người dùng. Với lỗi biểu mẫu, View có thể hiển thị lại giá trị đã nhập và thông báo theo trường. Với lỗi nghiệp vụ, ứng dụng có thể trả thông báo có ý nghĩa hoặc mã trạng thái phù hợp. Chi tiết exception, câu SQL, stack trace hay thông tin nhạy cảm không nên được đưa vào ViewModel công khai.

Khi mapper tạo ViewModel cho trang lỗi, nó nên nhận thông tin lỗi đã được phân loại và chọn lọc. Không nên đưa nguyên đối tượng exception vào template để View tự đọc message hoặc phân tích loại lỗi kỹ thuật.

## 7. Bảo mật tại ranh giới ViewModel

ViewModel và Form Object hỗ trợ bảo mật khi được thiết kế như các hợp đồng cho phép rõ ràng. Chúng không tự tạo ra bảo mật nếu Controller vẫn chấp nhận dữ liệu tùy ý hoặc dịch vụ không kiểm tra quyền.

Một số nguyên tắc cần áp dụng:

1. **Chỉ xuất dữ liệu cần thiết.** ViewModel không chứa mật khẩu, token, dữ liệu cá nhân hoặc trường nội bộ chỉ vì entity có sẵn.
2. **Chỉ nhận trường được phép.** Form Object xác định rõ những trường mà người dùng có thể gửi. Không binding hàng loạt vào entity có nhiều thuộc tính nhạy cảm.
3. **Kiểm tra quyền ở phía máy chủ.** Cờ canEdit chỉ giúp View quyết định có hiển thị nút hay không. Endpoint và dịch vụ vẫn phải kiểm tra quyền khi nhận thao tác.
4. **Escape dữ liệu khi hiển thị.** View phải mã hóa đầu ra theo ngữ cảnh HTML, thuộc tính, URL hoặc JavaScript. ViewModel không thay thế cơ chế escape của template engine.
5. **Không tiết lộ lỗi nội bộ.** Chỉ đưa thông báo phù hợp với người dùng vào dữ liệu trình bày; ghi log kỹ thuật ở nơi được kiểm soát.
6. **Cân nhắc dữ liệu đa tenant.** Mapper chỉ nên nhận dữ liệu đã được truy xuất trong phạm vi người dùng hoặc tenant được phép. Việc bỏ một trường khỏi ViewModel không sửa được lỗi truy vấn lấy nhầm dữ liệu.

## 8. Mapper nên đơn giản và có thể kiểm thử

Mapper thường là thành phần có logic chuyển đổi thuần túy. Khi có thể, hãy giữ nó không phụ thuộc HTTP request, session, template engine hoặc repository. Một mapper nhận đầu vào và trả đầu ra rõ ràng sẽ dễ kiểm thử và dễ thay thế.

Có thể dùng hàm hoặc lớp thủ công cho chuyển đổi nhỏ. Với nhiều kiểu dữ liệu và ánh xạ lặp lại, thư viện như MapStruct có thể sinh mã chuyển đổi từ khai báo. Dù dùng cách nào, người phát triển vẫn phải xác định rõ trường nào được ánh xạ, trường nào bị bỏ qua và chuyển đổi nào có ý nghĩa.

Không nên biến mapper thành một dịch vụ tổng hợp. Nếu mapper phải gọi repository để tải quan hệ, kiểm tra quyền, tính giá hoặc thay đổi trạng thái, trách nhiệm đang bị trộn lẫn. Hãy lấy dữ liệu và thực hiện quy tắc qua dịch vụ ứng dụng trước, rồi chuyển kết quả cần thiết thành ViewModel.

### 8.1. Kiểm thử mapper

Vì mapper thường là mã chuyển đổi thuần túy, có thể kiểm tra bằng unit test:

~~~java
@Test
void mapsTaskStatusAndDueDateForDetailsView() {
    Task task = new Task(
        "Chuẩn bị báo cáo",
        TaskStatus.IN_PROGRESS,
        LocalDate.of(2026, 12, 5)
    );

    TaskDetailsViewModel result =
        new TaskViewMapper().toDetails(task, true);

    assertEquals("Chuẩn bị báo cáo", result.title());
    assertEquals("Đang thực hiện", result.statusLabel());
    assertEquals("05/12/2026", result.dueDateText());
    assertTrue(result.canEdit());
}
~~~

Các trường hợp nên kiểm tra gồm:

- Giá trị null hoặc không có dữ liệu tùy chọn.
- Mọi trạng thái nghiệp vụ có thể xuất hiện.
- Ngày giờ tại ranh giới ngày hoặc khi đổi múi giờ.
- Trường nhạy cảm không xuất hiện trong ViewModel.
- Dữ liệu biểu mẫu được chuẩn hóa theo đúng quy ước.
- Những trường đầu vào không được phép không thể đi vào command.

Ngoài unit test cho mapper, vẫn cần kiểm thử tích hợp Controller và View để xác minh tên thuộc tính, binding, validation, thông báo lỗi và phản hồi HTTP. Mapper đúng không bảo đảm template đang sử dụng đúng tên trường.

## 9. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Truyền entity trực tiếp vào View | Giao diện phụ thuộc cấu trúc lưu trữ và có thể lộ trường nội bộ | Tạo ViewModel theo nhu cầu màn hình |
| Dùng một DTO cho cả request và response | Trộn dữ liệu người dùng được phép gửi với dữ liệu máy chủ được phép xuất | Tách Form Object, Command và ViewModel khi mục đích khác nhau |
| Đặt quy tắc nghiệp vụ trong mapper | Quy tắc khó tái sử dụng và có thể bị bỏ qua ở luồng khác | Đưa quy tắc vào Model hoặc dịch vụ ứng dụng |
| Mapper tự truy vấn cơ sở dữ liệu | Khó dự đoán hiệu năng, khó kiểm thử và dễ tạo N+1 query | Nạp dữ liệu trong dịch vụ/repository rồi truyền vào mapper |
| Dùng ViewModel như nơi kiểm tra quyền | Ẩn nút bị nhầm thành bảo vệ endpoint | Kiểm tra quyền ở phía máy chủ trên từng thao tác |
| Tạo ViewModel dùng chung quá lớn | Mỗi View phụ thuộc vào trường không liên quan | Thiết kế theo nhu cầu của màn hình hoặc use case |
| Đưa exception thô vào View | Rò rỉ chi tiết kỹ thuật và thông tin nhạy cảm | Chuyển thành thông báo đã phân loại, an toàn cho người dùng |

## 10. Quy trình thiết kế ranh giới cho một màn hình

Khi xây dựng một màn hình mới, có thể tiến hành theo thứ tự sau:

1. Xác định thông tin và trạng thái mà View thực sự cần hiển thị.
2. Thiết kế ViewModel chỉ chứa những trường phục vụ hợp đồng đó.
3. Xác định nguồn dữ liệu và dịch vụ ứng dụng chịu trách nhiệm cung cấp chúng.
4. Viết mapper chuyển kết quả nghiệp vụ thành ViewModel; xử lý rõ giá trị tùy chọn, nhãn và định dạng.
5. Với biểu mẫu, thiết kế Form Object riêng và xác định các trường được phép nhận.
6. Binding và validation dữ liệu đầu vào trước khi tạo command hoặc gọi thao tác nghiệp vụ.
7. Giữ kiểm tra quyền và quy tắc trạng thái ở phía máy chủ.
8. Kiểm thử mapper, Controller, View và luồng request-response quan trọng.

Không phải mọi màn hình đều cần một lớp mapper riêng. Nếu chuyển đổi chỉ là một phép gán đơn giản, đặt nó ở nơi rõ ràng và dễ đọc có thể đủ. Khi logic chuyển đổi lặp lại, có nhiều định dạng hoặc cần kiểm thử độc lập, tách mapper sẽ có ích. Quyết định nên dựa trên độ phức tạp và giá trị của ranh giới.

## 11. Những điểm cần ghi nhớ

View chịu trách nhiệm trình bày; ViewModel mô tả dữ liệu dành cho giao diện; mapper chuyển dữ liệu giữa các hợp đồng. Ba thành phần này giúp giao diện ít phụ thuộc vào cấu trúc nội bộ của nghiệp vụ và lưu trữ, đồng thời làm rõ dữ liệu nào được phép xuất ra hoặc nhận vào.

ViewModel không phải bản sao của entity, mapper không phải nơi chứa nghiệp vụ, và cờ hiển thị trên giao diện không thay thế kiểm tra quyền ở máy chủ. Với luồng đọc, hãy chuẩn bị dữ liệu cần thiết rồi chuyển thành ViewModel trước khi render. Với luồng ghi, hãy binding vào Form Object, validation, chuyển thành command và để dịch vụ nghiệp vụ thực hiện thao tác.

Một ranh giới tốt giúp View dễ đọc, dữ liệu được kiểm soát và thay đổi nội bộ ít lan sang giao diện. Hãy thiết kế hợp đồng theo nhu cầu thực tế của từng màn hình, giữ chuyển đổi minh bạch và kiểm thử những điểm giao tiếp giữa các thành phần.
