# Thao tác truy vấn và thao tác thay đổi trạng thái

Trong một ứng dụng web theo MVC, Model chịu trách nhiệm cung cấp dữ liệu và thực hiện các quy tắc nghiệp vụ. Những tương tác với Model thường thuộc một trong hai nhóm: **truy vấn** để đọc thông tin và **thao tác thay đổi trạng thái** để làm cho ứng dụng chuyển sang một trạng thái mới.

Phân biệt hai nhóm này giúp thiết kế luồng request dễ hiểu, xác định đúng nơi đặt giao dịch, xử lý lỗi và bảo vệ dữ liệu. Nó cũng giúp người phát triển nhận ra một lỗi thiết kế phổ biến: một request có vẻ chỉ đọc nhưng lại âm thầm thay đổi dữ liệu, hoặc Controller tự sửa trạng thái mà bỏ qua quy tắc của Model.

## 1. Hai loại thao tác trong Model

### 1.1. Truy vấn: đọc và trả về thông tin

Truy vấn (query) yêu cầu ứng dụng cung cấp thông tin tại một thời điểm. Ví dụ:

- Lấy chi tiết một đơn hàng.
- Tìm các công việc đang chờ xử lý của người dùng.
- Đếm số thông báo chưa đọc.
- Tính tổng số tiền của giỏ hàng để hiển thị.
- Tìm kiếm sản phẩm theo từ khóa và bộ lọc.

Một truy vấn có thể đọc từ nhiều bảng, kết hợp dữ liệu hoặc tính toán kết quả. Điều quan trọng là nó không làm thay đổi trạng thái nghiệp vụ mà những request khác quan sát được. Kết quả có thể là một đối tượng miền, một projection hoặc một DTO dành cho View.

Ví dụ, truy vấn danh sách công việc có thể trả về mã, tiêu đề và trạng thái của từng công việc. View chỉ cần các trường này để hiển thị; nó không cần nhận toàn bộ đối tượng lưu trữ cùng các quan hệ nội bộ.

### 1.2. Thao tác thay đổi trạng thái: yêu cầu ứng dụng thực hiện một hành động

Thao tác thay đổi trạng thái thường được gọi là command. Nó yêu cầu ứng dụng thực hiện một hành động làm thay đổi trạng thái nghiệp vụ. Ví dụ:

- Tạo một đơn hàng.
- Đổi trạng thái công việc từ đang làm sang hoàn thành.
- Cập nhật địa chỉ giao hàng.
- Hủy một đặt chỗ.
- Ghi nhận một khoản thanh toán.

Một command cần tuân theo quy tắc nghiệp vụ. Không phải mọi yêu cầu cập nhật dữ liệu đều hợp lệ: đơn hàng đã giao có thể không được hủy; công việc đã đóng có thể không được chuyển về trạng thái đang làm; người dùng chỉ được thay đổi tài nguyên mà họ có quyền thao tác.

Command thường nhận một dữ liệu đầu vào mô tả ý định, kiểm tra điều kiện, thực hiện thay đổi trong một giao dịch và trả kết quả thực hiện. Kết quả có thể là mã định danh, trạng thái mới hoặc phiên bản dữ liệu. Phần đọc chi tiết sau khi thay đổi có thể được thực hiện bằng một truy vấn riêng.

### 1.3. So sánh hai loại thao tác

| Tiêu chí | Truy vấn (query) | Thay đổi trạng thái (command) |
|---|---|---|
| Mục đích | Cung cấp thông tin | Thực hiện một hành động |
| Tác động nghiệp vụ | Không làm đổi trạng thái nghiệp vụ | Làm đổi trạng thái nếu hợp lệ |
| Đầu vào | Điều kiện tìm kiếm, bộ lọc, mã định danh, phân trang | Ý định thay đổi và dữ liệu cần thiết |
| Đầu ra | Dữ liệu để đọc hoặc trình bày | Kết quả thực hiện, mã định danh hoặc trạng thái |
| Quy tắc cần kiểm tra | Phạm vi dữ liệu được phép xem, điều kiện truy vấn | Quyền thao tác, tính hợp lệ của chuyển trạng thái, bất biến nghiệp vụ |
| Giao dịch | Thường chỉ cần giao dịch đọc khi cần tính nhất quán | Thường cần giao dịch ghi để thay đổi nguyên tử |
| Ví dụ | Xem chi tiết công việc | Đánh dấu công việc hoàn thành |

Cả hai loại đều cần kiểm soát quyền truy cập. Quyền xem một đơn hàng và quyền hủy đơn hàng là hai quyền khác nhau. Không nên cho rằng dữ liệu chỉ được đọc thì không cần kiểm tra quyền.

## 2. Luồng truy vấn và luồng thay đổi trạng thái trong MVC

Controller tiếp nhận request, chuyển đầu vào sang thao tác phù hợp trong Model, rồi chọn cách tạo phản hồi. Model thực hiện truy vấn hoặc xử lý command theo hợp đồng của nó.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Controller"]
    B --> C{"Loại thao tác?"}
    C -->|"Đọc"| D["Query trong Model"]
    D --> E["Repository / nguồn dữ liệu"]
    E --> D
    D --> F["DTO hoặc dữ liệu kết quả"]
    C -->|"Thay đổi"| G["Command trong Model"]
    G --> H["Kiểm tra quyền và quy tắc nghiệp vụ"]
    H --> I["Giao dịch ghi"]
    I --> J["Repository / nguồn dữ liệu"]
    J --> K["Kết quả command"]
    F --> L["Controller tạo phản hồi"]
    K --> L
    L --> M["View hoặc HTTP response"]
~~~

Hai luồng có điểm chung là đi qua Controller và sử dụng Model, nhưng cách xử lý khác nhau:

- Với truy vấn, Controller cung cấp tiêu chí đọc. Model lấy dữ liệu và trả kết quả để View trình bày.
- Với command, Controller chuyển ý định thay đổi. Model kiểm tra quy tắc, thực hiện thay đổi và trả kết quả. Controller chuyển kết quả thành phản hồi phù hợp.

Không nên để View gọi thẳng repository hoặc tự cập nhật đối tượng miền. View chỉ cần dữ liệu để hiển thị và gửi yêu cầu của người dùng. Controller là điểm tiếp nhận yêu cầu; Model là nơi bảo vệ quy tắc của ứng dụng.

## 3. Tổ chức thao tác trong Model

### 3.1. Đặt thao tác ở nơi sở hữu trách nhiệm

Trong ứng dụng nhỏ, truy vấn và thay đổi trạng thái có thể nằm trong cùng một dịch vụ ứng dụng. Khi số lượng chức năng tăng, có thể tách dịch vụ truy vấn và dịch vụ command để làm rõ mục đích và chính sách giao dịch.

Ví dụ:

- TaskQueryService cung cấp danh sách và chi tiết công việc.
- TaskCommandService xử lý tạo, cập nhật và chuyển trạng thái công việc.
- TaskRepository cung cấp khả năng đọc và lưu đối tượng.
- Task bảo vệ các quy tắc chuyển trạng thái của một công việc.

Việc tách hai dịch vụ giúp người đọc biết thao tác nào chỉ đọc và thao tác nào có thể thay đổi dữ liệu. Đây là một cách tổ chức mã, không phải yêu cầu bắt buộc phải tạo hai module, hai cơ sở dữ liệu hoặc hai dịch vụ triển khai riêng.

### 3.2. Trả dữ liệu phù hợp với nhu cầu của View

Không nên trả nguyên một đối tượng lưu trữ cho mọi màn hình. Một trang danh sách có thể chỉ cần mã, tiêu đề, trạng thái và ngày cập nhật. Trang chi tiết có thể cần thêm mô tả và người phụ trách.

Có thể định nghĩa DTO hoặc projection dành riêng cho kết quả truy vấn:

~~~java
public record TaskSummary(
    long id,
    String title,
    String status
) {}

public record TaskDetails(
    long id,
    String title,
    String description,
    String status,
    String assigneeName
) {}
~~~

Kết quả truy vấn như vậy có một hợp đồng rõ ràng. View không phải biết cấu trúc bảng hoặc các quan hệ nội bộ. Nó cũng giúp tránh vô tình trả về trường nhạy cảm như mã nội bộ, thông tin xác thực hoặc dữ liệu mà người dùng không được phép xem.

DTO cho View không phải lúc nào cũng trùng với đối tượng miền. Đối tượng miền ưu tiên bảo vệ trạng thái và quy tắc; DTO ưu tiên cung cấp dữ liệu phù hợp với một mục đích đọc cụ thể.

### 3.3. Command mô tả ý định thay đổi

Đầu vào của command nên thể hiện hành động người dùng muốn thực hiện, chẳng hạn ChangeTaskStatus hoặc CancelOrder. Cách đặt tên này dễ hiểu hơn một phương thức chung chung như updateData.

~~~java
public record ChangeTaskStatusRequest(
    TaskStatus status
) {}

public record ChangeTaskStatusResult(
    long taskId,
    String currentStatus
) {}
~~~

Command không nên chứa những trường mà người dùng không có quyền tự quyết định, chẳng hạn mã chủ sở hữu, số tiền đã được máy chủ tính hoặc quyền quản trị. Những giá trị đó phải được xác định từ danh tính đã xác thực và dữ liệu nghiệp vụ đáng tin cậy ở phía máy chủ.

### 3.4. Quy tắc chuyển trạng thái thuộc về Model

Một command có thể được gọi từ nhiều nơi: trang web, API, tác vụ nền hoặc một luồng xử lý khác. Nếu quy tắc chỉ nằm trong Controller của một màn hình, các luồng khác có thể bỏ qua quy tắc đó.

Ví dụ, một công việc chỉ được chuyển sang hoàn thành khi nó đang ở trạng thái đang thực hiện. Quy tắc này nên được bảo vệ trong đối tượng miền hoặc dịch vụ nghiệp vụ:

~~~java
enum TaskStatus {
    OPEN,
    IN_PROGRESS,
    DONE,
    CANCELLED
}

final class Task {
    private final long id;
    private TaskStatus status;

    Task(long id, TaskStatus initialStatus) {
        if (initialStatus == null) {
            throw new IllegalArgumentException("Trạng thái ban đầu không hợp lệ");
        }
        this.id = id;
        this.status = initialStatus;
    }

    long id() {
        return id;
    }

    TaskStatus status() {
        return status;
    }

    void changeStatus(TaskStatus target) {
        if (target == null) {
            throw new IllegalArgumentException("Trạng thái đích không hợp lệ");
        }

        boolean allowed = switch (status) {
            case OPEN -> target == TaskStatus.IN_PROGRESS
                || target == TaskStatus.CANCELLED;
            case IN_PROGRESS -> target == TaskStatus.DONE
                || target == TaskStatus.CANCELLED;
            case DONE, CANCELLED -> false;
        };

        if (!allowed) {
            throw new IllegalStateException("Không thể chuyển sang trạng thái yêu cầu");
        }

        status = target;
    }
}
~~~

Ví dụ chỉ minh họa một số chuyển trạng thái. Trong ứng dụng thực tế, có thể biểu diễn các trạng thái và chuyển tiếp bằng một bảng quy tắc hoặc một state machine nếu quy trình phức tạp. Dù dùng cách nào, quy tắc phải được kiểm tra ở Model trước khi lưu trạng thái mới.

## 4. Ánh xạ truy vấn và command với HTTP

Trong ứng dụng web, các phương thức HTTP thường gợi ý loại thao tác mà request thực hiện:

| Phương thức | Mục đích thường gặp | Đặc tính |
|---|---|---|
| GET | Đọc danh sách hoặc chi tiết | An toàn theo ngữ nghĩa HTTP và có tính idempotent |
| HEAD | Đọc metadata của tài nguyên | An toàn, không trả phần thân phản hồi |
| POST | Tạo tài nguyên hoặc thực hiện một hành động | Thường không idempotent |
| PUT | Tạo hoặc thay thế trạng thái tài nguyên tại URI | Idempotent theo ngữ nghĩa HTTP |
| PATCH | Thay đổi một phần tài nguyên | Tính idempotent tùy cách định nghĩa thao tác |
| DELETE | Xóa tài nguyên | Idempotent theo ngữ nghĩa HTTP |

GET không nên được dùng để thay đổi trạng thái. Ví dụ, đường dẫn /tasks/42/complete được gọi bằng GET có thể bị trình duyệt, proxy hoặc công cụ quét tự động truy cập ngoài ý muốn. Một hành động thay đổi trạng thái cần dùng phương thức phù hợp như POST hoặc PATCH.

Idempotent có nghĩa là thực hiện cùng một yêu cầu nhiều lần tạo ra cùng trạng thái đích như thực hiện một lần. Điều này đặc biệt quan trọng khi mạng lỗi khiến máy khách không biết máy chủ đã xử lý request hay chưa. PUT thường phù hợp khi máy khách gửi trạng thái mong muốn của tài nguyên. Một lệnh kiểu “tăng số lượng thêm một” gửi bằng PATCH có thể không idempotent vì mỗi lần gửi đều tăng thêm một đơn vị.

Với thao tác POST không idempotent như tạo thanh toán hoặc đặt chỗ, hệ thống có thể cần idempotency key để nhận diện các lần gửi lặp của cùng một ý định. Máy chủ lưu kết quả xử lý theo khóa đó và trả lại kết quả tương ứng khi nhận lại request hợp lệ. Cơ chế này cần được thiết kế cùng phạm vi người dùng, thời hạn lưu khóa và xử lý giao dịch.

Dù phương thức HTTP gợi ý ý nghĩa request, Controller vẫn phải gọi đúng thao tác trong Model. Đổi POST thành PATCH không tự động làm cho nghiệp vụ an toàn hoặc hợp lệ.

## 5. Ví dụ: xem công việc và đổi trạng thái công việc

Xét chức năng quản lý công việc. Người dùng có thể xem chi tiết một công việc và chuyển công việc từ đang thực hiện sang hoàn thành.

### 5.1. Truy vấn chi tiết

Dịch vụ truy vấn chỉ lấy dữ liệu cần thiết để hiển thị. Điều kiện truy vấn đồng thời giới hạn tài nguyên mà người dùng được phép xem.

~~~java
@Service
class TaskQueryService {
    private final TaskRepository repository;

    TaskQueryService(TaskRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    TaskDetails getDetails(long taskId, long actorId) {
        return repository.findDetailsVisibleTo(taskId, actorId)
            .orElseThrow(TaskNotFoundException::new);
    }
}
~~~

Tên phương thức findDetailsVisibleTo thể hiện rằng việc tìm kiếm đã gắn với phạm vi quyền xem. Có thể chọn trả 404 khi tài nguyên không tồn tại hoặc không hiển thị với người dùng để tránh tiết lộ sự tồn tại của tài nguyên. Chính sách phản hồi cần nhất quán với yêu cầu bảo mật của ứng dụng.

Thuộc tính readOnly trên giao dịch giúp thể hiện ý định đọc và có thể hỗ trợ framework hoặc nhà cung cấp persistence tối ưu thao tác. Nó không thay thế việc thiết kế truy vấn chỉ đọc và không phải một cơ chế bảo mật ngăn mọi thay đổi trong mọi cấu hình.

### 5.2. Thao tác thay đổi trạng thái

Dịch vụ command kiểm tra quyền, tải đối tượng, yêu cầu Model áp dụng quy tắc rồi hoàn tất thay đổi trong một giao dịch:

~~~java
@Service
class TaskCommandService {
    private final TaskRepository repository;

    TaskCommandService(TaskRepository repository) {
        this.repository = repository;
    }

    @Transactional
    ChangeTaskStatusResult changeStatus(
        long taskId,
        long actorId,
        TaskStatus target
    ) {
        Task task = repository.findForUpdateByIdAndOwnerId(taskId, actorId)
            .orElseThrow(TaskNotFoundException::new);

        task.changeStatus(target);

        return new ChangeTaskStatusResult(
            task.id(),
            task.status().name()
        );
    }
}
~~~

Ở đây, repository tìm công việc thuộc phạm vi người dùng và khóa hoặc kiểm soát bản ghi theo chiến lược đồng thời của ứng dụng. Phương thức changeStatus của đối tượng miền quyết định chuyển trạng thái có hợp lệ không. Giao dịch ghi bảo đảm việc thay đổi được lưu như một đơn vị công việc: nếu có lỗi trước khi commit, thay đổi cần được rollback.

Đoạn mã lược bỏ chi tiết ánh xạ ORM, định nghĩa repository và xử lý ngoại lệ. Với JPA, đối tượng được quản lý trong persistence context có thể được cập nhật khi transaction commit; không nhất thiết phải gọi save sau mỗi thay đổi. Cách lưu cụ thể phụ thuộc công nghệ truy cập dữ liệu.

### 5.3. Controller điều phối hai thao tác

Một Controller kiểu REST có thể ánh xạ truy vấn sang GET và thay đổi trạng thái sang PATCH:

~~~java
@RestController
@RequestMapping("/tasks")
class TaskController {
    private final TaskQueryService queries;
    private final TaskCommandService commands;

    TaskController(
        TaskQueryService queries,
        TaskCommandService commands
    ) {
        this.queries = queries;
        this.commands = commands;
    }

    @GetMapping("/{id}")
    TaskDetails details(
        @PathVariable long id,
        @AuthenticationPrincipal AppUser actor
    ) {
        return queries.getDetails(id, actor.id());
    }

    @PatchMapping("/{id}/status")
    ChangeTaskStatusResult changeStatus(
        @PathVariable long id,
        @RequestBody ChangeTaskStatusRequest request,
        @AuthenticationPrincipal AppUser actor
    ) {
        return commands.changeStatus(
            id,
            actor.id(),
            request.status()
        );
    }
}
~~~

Controller không tự thay đổi trường status. Nó lấy danh tính người dùng từ ngữ cảnh xác thực, chuyển request thành lời gọi nghiệp vụ và trả kết quả. Nếu dùng View HTML thay cho JSON, Controller có thể trả tên template hoặc redirect sau khi command thành công. Phần Model vẫn chịu trách nhiệm về quy tắc và trạng thái.

Trong ví dụ, ChangeTaskStatusRequest cần được định nghĩa và kiểm tra dữ liệu đầu vào. Nếu trạng thái gửi lên không thuộc tập giá trị hợp lệ, Controller hoặc lớp binding có thể trả lỗi đầu vào. Nếu trạng thái hợp lệ về cú pháp nhưng không hợp lệ theo quy tắc chuyển trạng thái, Model từ chối thao tác.

## 6. Giao dịch, tính nhất quán và xử lý đồng thời

### 6.1. Giao dịch bao quanh một thao tác nghiệp vụ

Một command thường gồm nhiều bước cần thành công hoặc thất bại cùng nhau. Ví dụ, khi xác nhận đơn hàng, hệ thống có thể cập nhật trạng thái đơn, ghi nhận các dòng đơn hàng và tạo bản ghi thanh toán nội bộ. Nếu chỉ một phần được lưu, trạng thái dữ liệu có thể không nhất quán.

Giao dịch cơ sở dữ liệu giúp nhóm các thay đổi liên quan thành một đơn vị nguyên tử. Ranh giới giao dịch thường đặt ở dịch vụ ứng dụng thực hiện use case, bao quanh các thao tác đọc cần thiết và ghi dữ liệu.

Không nên mở một giao dịch rồi giữ nó trong suốt thời gian người dùng điền biểu mẫu hoặc chờ xác nhận. Giao dịch nên ngắn, bao quanh công việc phía máy chủ cần được thực hiện nhất quán.

### 6.2. Truy vấn cần một quan điểm dữ liệu nhất quán

Một trang chi tiết có thể cần đọc thông tin từ nhiều bảng. Nếu các truy vấn được thực hiện ở những thời điểm khác nhau trong khi dữ liệu đang thay đổi, kết quả có thể phản ánh các thời điểm khác nhau. Khi nghiệp vụ yêu cầu một ảnh chụp dữ liệu nhất quán, cần chọn mức cô lập giao dịch và cách truy vấn phù hợp.

Với danh sách lớn, truy vấn nên giới hạn cột cần đọc, phân trang và sắp xếp ổn định. Các quan hệ được tải không hợp lý có thể tạo ra vấn đề N+1 hoặc đọc nhiều dữ liệu hơn nhu cầu của View. Đây là vấn đề hiệu năng của đường đọc; cần đo và tối ưu theo truy vấn thực tế.

### 6.3. Hai request có thể cùng thay đổi một tài nguyên

Giả sử hai người quản lý cùng mở một công việc. Người thứ nhất đánh dấu hoàn thành; người thứ hai hủy công việc dựa trên dữ liệu cũ. Nếu cả hai command đều ghi mà không kiểm soát đồng thời, một thay đổi có thể ghi đè thay đổi còn lại.

Một số cách xử lý phổ biến:

- **Khóa lạc quan:** lưu phiên bản của bản ghi. Khi cập nhật, hệ thống chỉ ghi nếu phiên bản vẫn đúng; nếu có request khác đã cập nhật, thao tác hiện tại nhận xung đột.
- **Khóa bi quan:** khóa bản ghi trong giao dịch khi cần ngăn các thao tác xung đột cùng cập nhật.
- **Điều kiện cập nhật:** chỉ cập nhật khi trạng thái hiện tại còn thỏa mãn điều kiện, ví dụ chỉ chuyển từ IN_PROGRESS sang DONE.

Với khóa lạc quan trong JPA, trường version có thể được đánh dấu bằng @Version. Khi phát hiện xung đột, Controller có thể trả HTTP 409 Conflict và yêu cầu người dùng tải lại dữ liệu. Việc thử lại tự động chỉ phù hợp khi nghiệp vụ cho phép và có chiến lược xử lý xung đột rõ ràng.

### 6.4. Tác động bên ngoài giao dịch

Một command đôi khi cần gửi email, phát thông báo hoặc gọi dịch vụ thanh toán. Những tác động này không tự động nằm trong giao dịch cơ sở dữ liệu. Nếu gửi email trước khi transaction commit rồi transaction rollback, người dùng có thể nhận thông báo về một thay đổi chưa từng được lưu.

Với tác động quan trọng, có thể ghi một sự kiện hoặc bản ghi outbox trong cùng giao dịch với thay đổi nghiệp vụ, rồi một tiến trình khác gửi thông báo sau khi commit. Cách này giúp giảm rủi ro mất sự kiện hoặc gửi thông báo sai thời điểm. Không nên giữ transaction cơ sở dữ liệu mở trong lúc chờ một dịch vụ mạng bên ngoài.

## 7. Kiểm tra đầu vào, quyền truy cập và lỗi

Truy vấn và command đều cần kiểm tra dữ liệu, nhưng mục đích kiểm tra khác nhau.

- **Kiểm tra đầu vào:** xác minh kiểu dữ liệu, định dạng, trường bắt buộc và giới hạn độ dài. Có thể thực hiện tại Controller hoặc lớp nhận request.
- **Kiểm tra quy tắc nghiệp vụ:** xác minh thao tác có hợp lệ với trạng thái hiện tại không. Phải được bảo vệ trong Model hoặc dịch vụ nghiệp vụ.
- **Kiểm tra quyền truy cập:** xác minh người dùng được xem hoặc thay đổi tài nguyên nào. Cần áp dụng cho cả query và command.
- **Kiểm tra tính nhất quán:** xác minh dữ liệu chưa bị thay đổi theo cách làm cho thao tác hiện tại không còn hợp lệ. Có thể cần giao dịch, khóa hoặc kiểm tra phiên bản.

Không nên tin các giá trị quyền hạn hoặc trạng thái do trình duyệt gửi lên. Máy chủ cần xác định người dùng từ phiên hoặc token đã xác thực, tải tài nguyên trong phạm vi được phép và áp dụng quy tắc trước khi lưu.

Lỗi nên được chuyển thành phản hồi phù hợp:

| Tình huống | Cách phản hồi thường dùng |
|---|---|
| Request sai định dạng hoặc thiếu trường bắt buộc | 400 Bad Request hoặc 422 Unprocessable Content theo quy ước API |
| Không tìm thấy tài nguyên hoặc không hiển thị trong phạm vi người dùng | 404 Not Found |
| Đã xác thực nhưng không có quyền thao tác | 403 Forbidden, nếu chính sách cho phép tiết lộ tài nguyên |
| Chuyển trạng thái vi phạm quy tắc nghiệp vụ | 409 Conflict hoặc lỗi nghiệp vụ được ánh xạ theo hợp đồng API |
| Phiên bản dữ liệu đã thay đổi | 409 Conflict |
| Lỗi ngoài dự kiến | 500 Internal Server Error với mã theo dõi phù hợp |

Phản hồi cho người dùng nên giải thích điều họ có thể làm tiếp theo. Không trả stack trace, câu truy vấn SQL hoặc thông tin cấu hình nội bộ trong response. Chi tiết kỹ thuật cần được ghi log có kiểm soát để phục vụ chẩn đoán.

## 8. Phân biệt CQS và CQRS

Nguyên tắc Command–Query Separation (CQS) khuyến khích một thao tác ở cấp phương thức tập trung vào một mục đích: hoặc trả về thông tin, hoặc yêu cầu thay đổi trạng thái. Theo cách diễn đạt chặt chẽ của CQS, command không đồng thời trả về dữ liệu truy vấn; trong dịch vụ ứng dụng, kết quả thực hiện như mã định danh hoặc phiên bản mới vẫn có thể được trả riêng mà không gộp việc đọc chi tiết vào command. Ví dụ, phương thức getTaskDetails đọc dữ liệu; phương thức completeTask thực hiện thay đổi. Việc phân biệt này làm hợp đồng của phương thức dễ hiểu và dễ kiểm thử.

Command Query Responsibility Segregation (CQRS) mở rộng ý tưởng phân tách trách nhiệm đọc và ghi ở cấp kiến trúc. Trong một hệ thống CQRS, mô hình đọc và mô hình ghi có thể được thiết kế riêng, thậm chí dùng các cấu trúc lưu trữ khác nhau để phục vụ yêu cầu riêng.

Không phải ứng dụng MVC nào cũng cần CQRS. Nhiều ứng dụng có thể dùng chung cơ sở dữ liệu và cùng hệ thống Model, chỉ tách rõ phương thức query và command. CQRS có thêm chi phí đồng bộ dữ liệu, vận hành và xử lý nhất quán cuối cùng; chỉ nên áp dụng khi nhu cầu đọc và ghi thực sự khác biệt đáng kể.

Có thể phân biệt ở mức khái quát:

| Cách tiếp cận | Phạm vi phân tách | Hệ quả |
|---|---|---|
| CQS | Mục đích của phương thức | Một phương thức tập trung vào đọc hoặc thay đổi |
| Tách query và command trong Model | Nhóm dịch vụ hoặc use case | Hợp đồng, quyền và giao dịch rõ hơn |
| CQRS | Mô hình kiến trúc đọc và ghi | Có thể có mô hình dữ liệu và đường triển khai riêng |

## 9. Kiểm thử truy vấn và command

Hai loại thao tác cần các trường hợp kiểm thử khác nhau.

### 9.1. Kiểm thử truy vấn

- Trả đúng dữ liệu khi tài nguyên tồn tại và người dùng có quyền xem.
- Không trả dữ liệu thuộc người dùng hoặc tổ chức khác.
- Xử lý đúng trường hợp không có kết quả.
- Bộ lọc, phân trang và sắp xếp hoạt động đúng.
- Không làm thay đổi trạng thái nghiệp vụ sau khi truy vấn.

### 9.2. Kiểm thử command

- Thực hiện thay đổi khi dữ liệu và trạng thái hiện tại hợp lệ.
- Từ chối chuyển trạng thái không được phép.
- Từ chối người dùng không có quyền.
- Không để lại thay đổi một phần khi giao dịch thất bại.
- Xử lý đúng hai request cạnh tranh trên cùng tài nguyên.
- Gửi hoặc ghi nhận tác động phụ theo đúng thời điểm commit.

Kiểm thử đơn vị cho Model có thể xác minh quy tắc chuyển trạng thái mà không cần chạy web server. Kiểm thử tích hợp xác minh giao dịch và repository hoạt động đúng. Kiểm thử Controller xác minh HTTP method, binding, quyền truy cập và cách ánh xạ lỗi. Với luồng quan trọng, kiểm thử từ request đến response giúp xác minh hợp đồng giữa các thành phần.

## 10. Những điểm cần ghi nhớ

Truy vấn cung cấp thông tin và không làm thay đổi trạng thái nghiệp vụ. Command thể hiện ý định thực hiện một hành động và phải tuân theo quy tắc, quyền truy cập cùng chính sách giao dịch của ứng dụng.

Trong MVC, Controller nhận request và điều phối thao tác; Model thực hiện truy vấn hoặc bảo vệ thay đổi trạng thái; View trình bày kết quả. Truy vấn nên trả dữ liệu vừa đủ cho nhu cầu đọc. Command nên mô tả ý định rõ ràng, kiểm tra điều kiện và thực hiện thay đổi nguyên tử khi cần.

Tách rõ hai loại thao tác giúp tránh việc request đọc vô tình gây thay đổi dữ liệu, giúp quy tắc nghiệp vụ không bị phân tán vào giao diện và giúp xử lý đồng thời, lỗi cùng kiểm thử có chủ đích. CQS là nguyên tắc hữu ích để bắt đầu; CQRS là lựa chọn kiến trúc rộng hơn, chỉ cần thiết khi mô hình đọc và ghi có nhu cầu khác biệt thực sự.
