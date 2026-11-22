# Kiểm tra quy tắc nghiệp vụ trong Model hoặc dịch vụ

Trong ứng dụng MVC, Controller tiếp nhận request và kiểm tra dữ liệu ở ranh giới web, nhưng những điều kiện quyết định một hành động có hợp lệ theo nghiệp vụ hay không cần được bảo vệ trong Model hoặc dịch vụ nghiệp vụ. Nếu chỉ đặt quy tắc trong Controller hay biểu mẫu, một API khác, tác vụ nền hoặc một luồng xử lý mới có thể vô tình bỏ qua chúng.

Ví dụ, biểu mẫu có thể kiểm tra người dùng đã nhập tiêu đề công việc và ngày đến hạn đúng định dạng. Nhưng việc một công việc có được hoàn thành hay không phụ thuộc trạng thái hiện tại; việc một nhân viên có được giao cho dự án hay không có thể phụ thuộc năng lực, vai trò và trạng thái dự án. Những quyết định này là quy tắc nghiệp vụ. Chúng phải được thực thi tại nơi mọi kênh gọi đều đi qua.

## Phân biệt kiểm tra đầu vào và kiểm tra quy tắc nghiệp vụ

Hai loại kiểm tra thường diễn ra gần nhau nhưng trả lời những câu hỏi khác nhau:

| Loại kiểm tra | Câu hỏi | Ví dụ | Nơi thường phù hợp |
|---|---|---|---|
| Chuyển đổi và validation đầu vào | Request có đúng định dạng và hợp đồng không? | `dueDate` parse được, tiêu đề không rỗng, số trang dương | Controller, binder, request DTO/form object |
| Quy tắc nghiệp vụ | Hành động có hợp lệ với trạng thái và chính sách hiện tại không? | Công việc có được hoàn thành không, người dùng có đủ hạn mức không? | Entity, value object, domain service hoặc application service phối hợp |
| Phân quyền | Chủ thể đã xác thực có được thực hiện hành động trên tài nguyên này không? | Người dùng có quyền sửa công việc của nhóm khác không? | Security layer và chính sách nghiệp vụ ở phía máy chủ |

Một giá trị có thể chuyển đổi thành số nguyên nhưng vẫn không hợp lệ với nghiệp vụ. Ví dụ, `quantity=0` là số hợp lệ về kiểu nhưng có thể vi phạm quy tắc số lượng phải lớn hơn 0. Tương tự, một request có đủ trường và đúng định dạng vẫn có thể bị từ chối vì công việc đã bị khóa.

Không nên dùng validation phía trình duyệt làm nơi bảo vệ quy tắc. Trình duyệt chỉ hỗ trợ trải nghiệm; client có thể gửi request trực tiếp. Controller có thể kiểm tra sớm để phản hồi rõ ràng, nhưng quy tắc quan trọng phải được thực thi trong Model hoặc dịch vụ được mọi kênh sử dụng.

## Đặt quy tắc ở Model khi quy tắc gắn với chính đối tượng

Model, đặc biệt là entity và value object, phù hợp để bảo vệ bất biến và hành vi thuộc về một khái niệm miền. Bất biến là điều kiện phải luôn đúng trong suốt vòng đời của đối tượng. Khi một hành động làm thay đổi trạng thái, đối tượng tự kiểm tra điều kiện trước khi cập nhật.

Ví dụ, một công việc có các trạng thái `OPEN`, `IN_PROGRESS`, `COMPLETED` và `CANCELLED`. Chỉ công việc đang thực hiện mới được hoàn thành; công việc đã hủy không thể được bắt đầu lại.

```java
public enum TaskStatus {
    OPEN,
    IN_PROGRESS,
    COMPLETED,
    CANCELLED
}
```

```java
public final class Task {
    private final TaskId id;
    private String title;
    private TaskStatus status;

    public Task(TaskId id, String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Tiêu đề không được để trống");
        }
        this.id = id;
        this.title = title.trim();
        this.status = TaskStatus.OPEN;
    }

    public void start() {
        if (status != TaskStatus.OPEN) {
            throw new TaskRuleViolation("Chỉ công việc đang mở mới có thể bắt đầu");
        }
        status = TaskStatus.IN_PROGRESS;
    }

    public void complete() {
        if (status != TaskStatus.IN_PROGRESS) {
            throw new TaskRuleViolation(
                    "Chỉ công việc đang thực hiện mới có thể hoàn thành");
        }
        status = TaskStatus.COMPLETED;
    }

    public void cancel() {
        if (status == TaskStatus.COMPLETED) {
            throw new TaskRuleViolation("Không thể hủy công việc đã hoàn thành");
        }
        status = TaskStatus.CANCELLED;
    }

    public void rename(String newTitle) {
        if (status == TaskStatus.CANCELLED) {
            throw new TaskRuleViolation("Không thể đổi tên công việc đã hủy");
        }
        if (newTitle == null || newTitle.isBlank()) {
            throw new TaskRuleViolation("Tiêu đề không được để trống");
        }
        title = newTitle.trim();
    }

    public TaskId id() { return id; }
    public String title() { return title; }
    public TaskStatus status() { return status; }
}
```

Các phương thức `start()`, `complete()`, `cancel()` và `rename()` mô tả hành vi theo ngôn ngữ nghiệp vụ. Mã gọi yêu cầu đối tượng thực hiện hành động thay vì tự đặt trạng thái bằng setter. Nhờ đó, quy tắc được giữ tại một nơi dù hành động đến từ web MVC, API, message consumer hay tác vụ nền.

### Bảo vệ bất biến trong constructor và factory

Những điều kiện phải đúng ngay khi tạo đối tượng nên được kiểm tra trong constructor hoặc factory. Ví dụ, `EmailAddress` không nên tồn tại với giá trị sai định dạng; `Money` không nên chứa đơn vị tiền tệ không hợp lệ hoặc số tiền âm nếu miền không cho phép.

```java
public record PositiveQuantity(int value) {
    public PositiveQuantity {
        if (value <= 0) {
            throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
        }
    }
}
```

Value object có thể làm cho trạng thái không hợp lệ khó biểu diễn hơn. Sau khi tạo thành công, các thành phần khác có thể dựa vào hợp đồng của kiểu đó mà không cần lặp lại kiểm tra cơ bản ở mọi nơi.

### Không biến entity thành nơi chứa mọi quy tắc

Một entity nên giữ những quy tắc gắn với trạng thái và hành vi của nó. Nếu quyết định cần phối hợp nhiều đối tượng hoặc chính sách, cố nhét tất cả vào một entity sẽ khiến entity phụ thuộc quá nhiều và khó kiểm thử. Khi đó, domain service hoặc application service phù hợp hơn.

## Dùng Domain Service khi quy tắc liên quan nhiều đối tượng

Domain service biểu diễn một quy tắc nghiệp vụ không tự nhiên thuộc về một entity hoặc value object cụ thể. Nó thường nhận các đối tượng hoặc dữ kiện miền, đánh giá chính sách và trả kết quả có ý nghĩa nghiệp vụ.

Ví dụ, quy tắc phân công công việc có thể phụ thuộc vào:

- dự án có đang hoạt động hay không;
- người được giao có còn là thành viên của dự án không;
- người đó có năng lực cần thiết không;
- số lượng công việc đang mở có vượt hạn mức không;
- công việc có yêu cầu quyền hoặc chứng chỉ đặc biệt không.

Không có một entity duy nhất sở hữu toàn bộ quyết định này. Một policy/domain service có thể diễn đạt quy tắc:

```java
public final class TaskAssignmentPolicy {
    public void ensureCanAssign(
            Project project,
            User assignee,
            Task task,
            int currentOpenTaskCount) {

        if (!project.isActive()) {
            throw new TaskRuleViolation("Không thể giao việc cho dự án đã đóng");
        }
        if (!project.hasMember(assignee.id())) {
            throw new TaskRuleViolation("Người được giao không thuộc dự án");
        }
        if (!assignee.hasSkill(task.requiredSkill())) {
            throw new TaskRuleViolation("Người được giao chưa có kỹ năng phù hợp");
        }
        if (currentOpenTaskCount >= assignee.openTaskLimit()) {
            throw new TaskRuleViolation("Người được giao đã đạt giới hạn công việc");
        }
    }
}
```

Policy trên nhận các dữ kiện đã được tải và kiểm tra. Nó không tự đọc HTTP request, truy cập session hay biết View nào đang hiển thị. Quy tắc vì thế có thể được gọi từ nhiều use case.

### Domain service có nên truy cập repository?

Một domain service nên tập trung vào quy tắc miền và thường dễ kiểm thử nhất khi nhận các dữ kiện cần thiết qua tham số. Application service có thể tải project, user, task và số lượng công việc qua repository rồi truyền chúng vào policy.

Một số kiến trúc cho phép domain service phụ thuộc repository hoặc domain abstraction khi đó là cách diễn đạt tự nhiên của miền. Tuy nhiên, nếu service trực tiếp phụ thuộc ORM, HTTP hoặc chi tiết hạ tầng, ranh giới nghiệp vụ sẽ khó giữ. Hãy phân biệt hợp đồng miền với implementation lưu trữ và chọn vị trí truy vấn sao cho dependency vẫn hướng về phía trong.

## Application Service phối hợp kiểm tra và thay đổi trạng thái

Application service tổ chức một use case hoàn chỉnh. Nó thường thực hiện các bước:

1. nhận command có kiểu và danh tính người thực hiện;
2. tải dữ liệu cần thiết qua repository;
3. kiểm tra quyền hoặc chính sách phụ thuộc ngữ cảnh;
4. gọi domain service hoặc hành vi của entity;
5. lưu thay đổi trong transaction thích hợp;
6. trả kết quả để Controller tạo response.

Ví dụ, use case giao công việc có thể phối hợp repository và policy:

```java
@Service
public class AssignTaskService {
    private final TaskRepository taskRepository;
    private final ProjectRepository projectRepository;
    private final UserRepository userRepository;
    private final TaskAssignmentPolicy assignmentPolicy;

    public AssignTaskService(
            TaskRepository taskRepository,
            ProjectRepository projectRepository,
            UserRepository userRepository,
            TaskAssignmentPolicy assignmentPolicy) {
        this.taskRepository = taskRepository;
        this.projectRepository = projectRepository;
        this.userRepository = userRepository;
        this.assignmentPolicy = assignmentPolicy;
    }

    @Transactional
    public void assign(AssignTaskCommand command, UserId actorId) {
        Task task = taskRepository.findById(command.taskId())
                .orElseThrow(TaskNotFoundException::new);
        Project project = projectRepository.findById(task.projectId())
                .orElseThrow(ProjectNotFoundException::new);
        User assignee = userRepository.findById(command.assigneeId())
                .orElseThrow(UserNotFoundException::new);

        project.ensureManager(actorId);
        int openCount = taskRepository.countOpenByAssignee(assignee.id());
        assignmentPolicy.ensureCanAssign(project, assignee, task, openCount);

        task.assignTo(assignee.id());
        taskRepository.save(task);
    }
}
```

Đoạn mã minh họa sự phân công: application service tải dữ liệu và phối hợp use case; project kiểm tra quyền quản lý; policy đánh giá điều kiện phân công; entity `Task` cập nhật người được giao; repository lưu kết quả. Trong hệ thống thực tế, cần định nghĩa rõ quy tắc nào thuộc quyền của `Project`, quy tắc nào thuộc policy và cách bảo vệ giới hạn khi có nhiều thao tác đồng thời.

### Phân biệt Application Service và Domain Service

| Tiêu chí | Application Service | Domain Service |
|---|---|---|
| Mục đích | Điều phối use case | Biểu diễn quy tắc nghiệp vụ |
| Thường làm việc với | Command, repository, transaction, port | Entity, value object và dữ kiện miền |
| Biết về HTTP/View? | Không nên | Không |
| Ví dụ | `AssignTaskService` | `TaskAssignmentPolicy` |
| Kiểm thử chính | Đúng thứ tự phối hợp và kết quả use case | Quy tắc quyết định đúng với dữ kiện đầu vào |

Không phải mọi quy tắc cần một service riêng. Nếu hành vi thuộc rõ một entity, đặt nó trong entity. Chỉ dùng domain service khi nó làm cho quy tắc dễ hiểu hơn và không có đối tượng tự nhiên nào sở hữu hành vi đó.

## Đưa kết quả nghiệp vụ về Controller và View

Controller không nên tự viết lại quy tắc nghiệp vụ sau khi nhận kết quả. Nó cần chuyển kết quả thành response phù hợp với giao thức web.

Ví dụ, một Controller gọi use case hoàn thành công việc:

```java
@PostMapping("/{id}/complete")
public String complete(
        @PathVariable long id,
        Principal principal,
        RedirectAttributes redirectAttributes) {
    try {
        completeTaskService.complete(
                new TaskId(id), userIdFrom(principal));
        redirectAttributes.addFlashAttribute(
                "message", "Công việc đã được hoàn thành");
        return "redirect:/tasks/" + id;
    } catch (TaskRuleViolation ex) {
        redirectAttributes.addFlashAttribute("error", ex.getMessage());
        return "redirect:/tasks/" + id;
    }
}
```

Ví dụ trên minh họa ánh xạ lỗi nghiệp vụ thành thông báo. Trong ứng dụng lớn, nên tập trung ánh xạ exception bằng `@ControllerAdvice` hoặc một cơ chế kết quả thống nhất thay vì lặp `try/catch` ở mọi handler. Với API, cùng lỗi nghiệp vụ có thể được chuyển thành mã lỗi ổn định và HTTP status thích hợp, chẳng hạn 409 khi trạng thái tài nguyên xung đột với hành động.

Thông báo cho người dùng nên giải thích điều họ có thể làm tiếp theo, nhưng không tiết lộ chi tiết nội bộ. Log phía máy chủ có thể giữ thông tin kỹ thuật cần thiết để điều tra.

## Quy tắc phụ thuộc dữ liệu hiện tại và vấn đề đồng thời

Một số quy tắc không thể được quyết định chỉ bằng dữ liệu trong request. Ví dụ, “không được đặt hai lịch trùng nhau” cần kiểm tra các lịch đã lưu. “Người dùng không được vượt hạn mức công việc” cần đếm trạng thái hiện tại. Application service có thể tải dữ liệu và domain service đánh giá điều kiện.

Tuy nhiên, kiểm tra trước rồi ghi sau có thể gặp race condition. Hai request đồng thời có thể cùng đọc rằng một người còn một chỗ trống, cả hai cùng vượt qua policy rồi cùng ghi thêm công việc. Kết quả cuối cùng vi phạm hạn mức dù mỗi request đều đã kiểm tra.

Với quy tắc cần bảo đảm trong môi trường đồng thời, phải bảo vệ quyết định tại thời điểm cập nhật trạng thái bằng cơ chế phù hợp:

- transaction với mức cô lập phù hợp;
- khóa lạc quan bằng version và retry khi có xung đột;
- khóa bi quan khi cần tuần tự hóa thao tác trên tài nguyên;
- constraint hoặc thao tác cập nhật nguyên tử ở cơ sở dữ liệu;
- reservation/locking chuyên biệt cho tài nguyên cần giữ chỗ.

Không phải mọi quy tắc đều cần khóa. Chọn cơ chế theo mức độ tranh chấp, yêu cầu nhất quán và khả năng phục hồi. Domain service có thể đánh giá chính sách, nhưng tính đúng đắn khi nhiều request cùng chạy còn cần transaction và cơ chế lưu trữ bảo vệ.

## Đừng nhầm quy tắc nghiệp vụ với kiểm tra quyền

Phân quyền và quy tắc nghiệp vụ có thể phối hợp trong một use case nhưng cần được nhận diện rõ:

- **Authentication:** xác định người gửi request là ai.
- **Authorization:** xác định người đó có quyền truy cập endpoint hoặc tài nguyên không.
- **Business rule:** xác định hành động có hợp lệ theo trạng thái và chính sách miền không.

Ví dụ, người dùng đã đăng nhập có thể có quyền mở trang công việc nhưng không có quyền giao việc. Một trưởng nhóm có quyền giao việc vẫn không thể giao một công việc cho thành viên không thuộc dự án. Quyền quản lý có thể được kiểm tra trong security layer hoặc policy; điều kiện thành viên dự án là quy tắc nghiệp vụ.

Không tin `userId`, `role`, `isAdmin` hoặc `ownerId` do client gửi lên. Lấy danh tính từ ngữ cảnh đã xác thực, tải tài nguyên từ nguồn tin cậy và kiểm tra quyền phía máy chủ. Ẩn nút trên View chỉ là hỗ trợ trải nghiệm, không thay thế kiểm tra ở endpoint và dịch vụ.

## Kiểm thử quy tắc ở đúng ranh giới

Khi quy tắc được đặt đúng chỗ, có thể kiểm thử độc lập mà không cần khởi chạy toàn bộ ứng dụng MVC.

### Kiểm thử entity và value object

Kiểm tra bất biến và chuyển trạng thái:

- tiêu đề rỗng bị từ chối khi tạo;
- công việc đang thực hiện có thể hoàn thành;
- công việc đang mở không thể hoàn thành nếu quy tắc yêu cầu phải bắt đầu trước;
- công việc đã hủy không thể đổi tên;
- value object từ chối giá trị nằm ngoài miền hợp lệ.

```java
class TaskTest {
    @Test
    void completesTaskInProgress() {
        Task task = new Task(new TaskId(42L), "Viết tài liệu");
        task.start();

        task.complete();

        assertEquals(TaskStatus.COMPLETED, task.status());
    }

    @Test
    void rejectsCompletionWhenTaskIsOpen() {
        Task task = new Task(new TaskId(42L), "Viết tài liệu");

        assertThrows(TaskRuleViolation.class, task::complete);
    }
}
```

Đoạn kiểm thử giả định `TaskRuleViolation`, `TaskId` và các import JUnit tương ứng đã được định nghĩa. Nó gọi trực tiếp Model, không cần Controller, HTTP hay database.

### Kiểm thử domain service

Với policy phân công, cung cấp các đối tượng hoặc dữ kiện đại diện cho từng tình huống:

| Dữ kiện | Kết quả mong đợi |
|---|---|
| Dự án hoạt động, người dùng là thành viên, có kỹ năng và còn hạn mức | Cho phép phân công |
| Dự án đã đóng | Từ chối |
| Người được giao không thuộc dự án | Từ chối |
| Thiếu kỹ năng bắt buộc | Từ chối |
| Đã đạt giới hạn công việc | Từ chối |

Kiểm thử policy nên tập trung vào quyết định theo dữ kiện. Không cần mock HTTP request hoặc template vì chúng không liên quan đến quy tắc.

### Kiểm thử application service

Kiểm tra dịch vụ tải đúng đối tượng, kiểm tra quyền, gọi policy, gọi hành vi Model và lưu khi thành công. Với trường hợp policy từ chối, xác minh repository không lưu thay đổi. Với trường hợp không tìm thấy tài nguyên, xác minh use case trả lỗi phù hợp.

### Kiểm thử tích hợp và đồng thời

Một số quy tắc phụ thuộc truy vấn và transaction nên cần kiểm thử với repository/database thật hoặc môi trường thử nghiệm tương đương. Với hạn mức hoặc đặt chỗ, tạo hai request cạnh tranh và xác minh hệ thống không thể ghi cả hai khi điều đó vi phạm quy tắc. Unit test của policy không thể chứng minh cơ chế khóa hay constraint hoạt động đúng.

## Những cách đặt quy tắc dễ gây lỗi

- **Chỉ kiểm tra trong Controller:** endpoint khác hoặc tác vụ nền có thể bỏ qua quy tắc. Chuyển bất biến về Model hoặc dịch vụ nghiệp vụ dùng chung.
- **Chỉ kiểm tra trong View hoặc JavaScript:** client có thể bỏ qua giao diện. Kiểm tra lại ở phía máy chủ.
- **Đưa mọi quy tắc vào một service lớn:** service khó hiểu và khó kiểm thử. Tách hành vi thuộc entity, policy liên quan nhiều đối tượng và điều phối use case.
- **Entity chỉ có getter/setter:** mọi nơi có thể sửa trạng thái tùy ý. Dùng phương thức hành vi có tên nghiệp vụ và hạn chế setter công khai.
- **Domain service biết HTTP hoặc ORM:** quy tắc bị gắn với framework. Truyền kiểu miền và dữ kiện cần thiết qua hợp đồng rõ ràng.
- **Lặp cùng quy tắc ở nhiều endpoint:** các bản sao dễ lệch nhau. Dùng Model/policy làm nguồn quyết định chung; validation ở Controller chỉ hỗ trợ phản hồi sớm.
- **Kiểm tra trạng thái rồi ghi mà không bảo vệ đồng thời:** hai request có thể cùng vượt qua kiểm tra cũ. Dùng transaction, version hoặc constraint phù hợp.
- **Dùng exception cho mọi lỗi đầu vào:** lỗi parse và validation thông thường nên được biểu diễn qua cơ chế binding/validation; exception nghiệp vụ nên diễn đạt việc hành động không hợp lệ theo miền.

## Cách quyết định đặt quy tắc ở đâu

Khi gặp một điều kiện mới, hãy lần lượt tự hỏi:

1. Điều kiện chỉ phụ thuộc dữ liệu của một đối tượng hay trạng thái của chính nó? Nếu có, đặt hành vi và bất biến trong entity hoặc value object.
2. Điều kiện phối hợp nhiều khái niệm miền nhưng không thuộc tự nhiên một entity? Cân nhắc domain service hoặc policy.
3. Điều kiện yêu cầu tải dữ liệu, phối hợp nhiều repository, quản lý transaction hoặc gọi hệ thống ngoài? Đặt trình tự use case trong application service.
4. Điều kiện chỉ mô tả request có đúng kiểu, định dạng và giới hạn không? Đặt ở request DTO, binder hoặc validation tại ranh giới Controller.
5. Điều kiện có phụ thuộc danh tính và quyền truy cập không? Kiểm tra ở security layer và chính sách phía máy chủ.
6. Nhiều request đồng thời có thể làm điều kiện thay đổi giữa lúc kiểm tra và lúc ghi không? Bổ sung cơ chế bảo vệ transaction hoặc cập nhật nguyên tử.

Trong MVC, Controller nhận request và điều phối, nhưng Model hoặc dịch vụ nghiệp vụ phải là nơi bảo vệ quyết định quan trọng của miền. Entity giữ bất biến của chính nó; domain service diễn đạt chính sách liên quan nhiều đối tượng; application service tổ chức use case và transaction. Cách phân chia này giúp mọi kênh tương tác tuân theo cùng quy tắc và làm cho nghiệp vụ có thể kiểm thử độc lập với giao diện web.
