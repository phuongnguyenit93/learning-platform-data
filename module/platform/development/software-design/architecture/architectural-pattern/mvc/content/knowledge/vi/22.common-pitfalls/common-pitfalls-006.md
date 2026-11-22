# Lạm dụng lớp cơ sở và thành phần dùng chung

Khi một ứng dụng MVC có nhiều Controller, View và Model, nhóm phát triển thường muốn loại bỏ mã lặp bằng cách tạo lớp cơ sở hoặc thành phần dùng chung. Một `BaseController` có thể gom xử lý lỗi, lấy người dùng hiện tại và thêm dữ liệu chung vào View; một `BaseEntity` có thể chứa ID, thời gian tạo và người cập nhật; một fragment có thể dùng lại thanh tìm kiếm hoặc form; một `BaseService` có thể cung cấp các thao tác CRUD cho nhiều use case.

Tái sử dụng là cần thiết, nhưng trừu tượng hóa quá sớm hoặc quá rộng có thể làm kiến trúc khó hiểu hơn. Lớp con phải biết nhiều chi tiết của lớp cha, một thay đổi nhỏ ở thành phần dùng chung có thể ảnh hưởng hàng chục màn hình, và quy tắc riêng của từng use case bị ép vào một API tổng quát. Khi đó, mã lặp giảm nhưng phụ thuộc tăng.

Trong MVC, cần giữ rõ trách nhiệm: Controller điều phối request, Model bảo vệ trạng thái và quy tắc nghiệp vụ, View trình bày dữ liệu. Lớp cơ sở hoặc thành phần dùng chung chỉ có giá trị khi nó gom một trách nhiệm thực sự ổn định, có hợp đồng nhỏ và được nhiều nơi sử dụng theo cùng một cách. Nếu hai đoạn mã chỉ giống nhau về hình thức nhưng khác nhau về ý nghĩa hoặc lý do thay đổi, chúng chưa chắc nên dùng chung.

## Nhận diện các dạng lạm dụng thường gặp

| Dạng lạm dụng | Biểu hiện | Hệ quả |
|---|---|---|
| Base Controller quá lớn | Chứa service, repository, helper, logic xác thực, mapping và xử lý lỗi cho mọi Controller | Controller con phụ thuộc ngầm và khó hiểu luồng request |
| Kế thừa để chia sẻ vài dòng mã | Lớp con extends lớp cha chỉ để gọi một helper hoặc lấy một field | Quan hệ kiểu bị dùng sai mục đích; thay đổi lớp cha gây ảnh hưởng ngoài dự kiến |
| Base Model/Base Entity phình to | Mọi entity phải có cùng field, trạng thái hoặc lifecycle dù miền không yêu cầu | Domain model bị ép theo persistence/framework và mang dữ liệu không liên quan |
| Generic CRUD Service | Mọi use case bị đưa vào `create/update/delete/findAll` tổng quát | Quy tắc nghiệp vụ và quyền truy cập bị che khuất sau API chung |
| Shared View fragment quá thông minh | Fragment tự truy cập dữ liệu, tự quyết định quyền hoặc chứa nhiều nhánh theo từng trang | View phụ thuộc ngược vào nghiệp vụ và khó tái sử dụng |
| Shared utility thành nơi chứa mọi thứ | Một `CommonUtils` hoặc `AppHelper` có hàng chục phương thức không cùng trách nhiệm | Khó đặt tên, kiểm thử và thay đổi an toàn |
| Abstraction dùng một lần | Interface, factory hoặc hierarchy chỉ có một implementation và không có nhu cầu thay thế rõ | Tăng số lớp và gián tiếp mà không giảm phụ thuộc |

Điểm chung là một thành phần được gọi là “dùng chung” chỉ vì nhiều nơi có thể truy cập nó, không phải vì các nơi đó thực sự cần cùng một hợp đồng.

## Kế thừa và tái sử dụng không phải là một

Kế thừa mô tả quan hệ “là một” (is-a): một lớp con có thể được dùng ở nơi mong đợi lớp cha mà vẫn giữ đúng hợp đồng. Tái sử dụng mã chỉ là một lợi ích có thể có của kế thừa, không phải lý do đủ để tạo quan hệ cha–con.

Ví dụ, `AdminTaskController extends BaseController` không nhất thiết có nghĩa một AdminTaskController là một loại BaseController theo mô hình miền. Có thể lớp con chỉ muốn dùng `currentUser()` hoặc `addFlashMessage()`. Khi đó, dependency qua constructor, một collaborator hoặc một abstraction nhỏ thường thể hiện ý định tốt hơn.

### Dấu hiệu quan hệ kế thừa không đúng

- Lớp con phải override phương thức của lớp cha chỉ để vô hiệu hóa hành vi không phù hợp.
- Lớp cha có nhiều hook như `beforeCreate`, `afterCreate`, `prepareAdminModel`, `configureForMobile` vì mỗi lớp con cần một biến thể khác nhau.
- Phương thức lớp cha có hành vi phụ thuộc vào field protected mà lớp con tự thay đổi.
- Lớp con không thể dùng ở nơi cần lớp cha mà không gây bất ngờ.
- Lớp cha thay đổi vì nhiều lý do không liên quan đến nhau.
- Muốn hiểu một hành động phải đọc cả lớp cha, lớp con và nhiều lớp trung gian.

Đây là các dấu hiệu vi phạm hoặc làm suy yếu nguyên tắc thay thế Liskov (LSP), tính đóng gói và phân chia trách nhiệm. Không phải mọi override đều sai; vấn đề là lớp con có giữ được hợp đồng mà lớp cha công bố hay không.

## Base Controller biến thành nơi chứa mọi logic

Một mẫu dễ gặp trong ứng dụng Spring MVC là tạo `BaseController` để các Controller kế thừa. Ban đầu lớp này chỉ có một helper nhỏ, sau đó lần lượt thêm repository, user service, permission service, mapper, message source, audit service và nhiều phương thức protected.

Ví dụ thiết kế có vấn đề:

```java
public abstract class BaseController {
    @Autowired
    protected TaskRepository taskRepository;

    @Autowired
    protected UserRepository userRepository;

    @Autowired
    protected PermissionService permissionService;

    @Autowired
    protected AuditService auditService;

    protected User currentUser() {
        return (User) SecurityContextHolder.getContext()
                .getAuthentication().getPrincipal();
    }

    protected void prepareCommonModel(Model model) {
        model.addAttribute("currentUser", currentUser());
        model.addAttribute("pendingTasks", taskRepository.countPending());
    }
}

@Controller
public class TaskController extends BaseController {
    @GetMapping("/tasks")
    public String list(Model model) {
        prepareCommonModel(model);
        model.addAttribute("tasks", taskRepository.findAll());
        return "tasks/list";
    }
}
```

Lớp con có quyền truy cập mọi field `protected`, nên có thể truy vấn database hoặc gọi permission service tùy ý. Dependency thật của `TaskController` bị ẩn trong lớp cha. Một Controller chỉ cần đọc danh sách công việc lại kế thừa cả audit và user repository. Khi `prepareCommonModel()` thay đổi, nhiều trang có thể bị ảnh hưởng dù chúng không cần dữ liệu mới.

Field injection còn làm dependency khó thấy trong constructor và khó tạo test độc lập. Việc truy cập trực tiếp `SecurityContextHolder` trong lớp cha cũng gắn Controller với một cách xác thực cụ thể.

### Chia sẻ theo trách nhiệm thay vì kế thừa

Nếu nhiều trang cần dữ liệu hiển thị chung, hãy tạo một thành phần có hợp đồng hẹp để cung cấp đúng dữ liệu đó. Nếu cần thông tin người dùng hiện tại, lấy principal ở ranh giới bảo mật hoặc dùng một abstraction chuyên trách. Nếu cần xử lý lỗi HTTP, dùng `@ControllerAdvice`. Nếu cần kiểm tra quyền, đặt chính sách ở application/domain layer hoặc method security theo đúng phạm vi.

Ví dụ Controller khai báo dependency rõ ràng:

```java
@Controller
@RequestMapping("/tasks")
public class TaskController {
    private final ListTasksQuery listTasks;
    private final TaskPageDataProvider pageDataProvider;

    public TaskController(
            ListTasksQuery listTasks,
            TaskPageDataProvider pageDataProvider) {
        this.listTasks = listTasks;
        this.pageDataProvider = pageDataProvider;
    }

    @GetMapping
    public String list(
            @AuthenticationPrincipal AppPrincipal principal,
            Model model) {
        model.addAttribute("pageData", pageDataProvider.forUser(principal.userId()));
        model.addAttribute("tasks", listTasks.handle(principal.userId()));
        return "tasks/list";
    }
}
```

`TaskPageDataProvider` chỉ nên tồn tại nếu dữ liệu chung thực sự có một ý nghĩa và cách tính ổn định. Nếu mỗi trang cần dữ liệu khác nhau, hãy để từng query/use case trả đúng dữ liệu trang đó thay vì tạo một provider tổng hợp ngày càng lớn.

## Lạm dụng BaseEntity và lớp cơ sở trong Domain Model

Một `BaseEntity` có thể hữu ích khi nhiều entity thực sự chia sẻ cùng một khái niệm định danh hoặc metadata lifecycle. Nhưng nếu mọi class đều phải kế thừa một lớp cơ sở chỉ vì muốn dùng chung `createdAt`, `updatedAt`, `tenantId`, `version`, `softDeleted`, `createdBy`, `updatedBy` và nhiều field khác, mô hình miền có thể bị ép theo cách lưu trữ.

Ví dụ:

```java
@MappedSuperclass
public abstract class BaseEntity {
    @Id
    @GeneratedValue
    protected Long id;

    protected Instant createdAt;
    protected Instant updatedAt;
    protected String createdBy;
    protected String updatedBy;
    protected boolean deleted;
    protected Long tenantId;
    @Version
    protected long version;
}
```

Không phải mọi entity đều có lifecycle giống nhau. Một `Money` hoặc `EmailAddress` là value object, không cần ID hay audit field. Một bản ghi cấu hình có thể không hỗ trợ soft delete. Một entity chỉ thuộc một tenant có thể không cần `tenantId` công khai trong mọi thao tác. Khi kế thừa BaseEntity quá rộng, code có thể vô tình cung cấp setter hoặc trạng thái không có ý nghĩa với một số đối tượng.

### Khi nào lớp cơ sở là hợp lý?

Lớp cơ sở có thể phù hợp khi:

- quan hệ cha–con phản ánh đúng khái niệm miền hoặc hợp đồng kỹ thuật;
- mọi lớp con cần cùng một invariant và cùng semantics;
- hành vi chung ổn định, ít phụ thuộc vào chi tiết lớp con;
- lớp cha có API nhỏ và không bắt lớp con biết field nội bộ;
- các lớp con có thể thay thế lớp cha mà không thay đổi kết quả mong đợi.

Ví dụ, một nhóm entity persistence có thể dùng `@MappedSuperclass` cho ID và optimistic version nếu mọi entity trong nhóm đều có cùng semantics. Tuy nhiên, audit metadata có thể được xử lý bằng auditing listener hoặc embedded value object; soft delete và tenant scoping cần được thiết kế theo yêu cầu thật của miền và persistence.

Không đưa tất cả field kỹ thuật vào một lớp chỉ để tránh lặp vài annotation. Một vài dòng mapping lặp lại có thể ít tốn kém hơn một hierarchy sai.

## Generic CRUD Service che khuất use case

Một `BaseCrudService<T, ID>` thường cung cấp `create`, `update`, `delete`, `findById` và `findAll`. Mẫu này có thể phù hợp cho dữ liệu quản trị đơn giản, nhưng dễ trở thành vấn đề khi được dùng làm nền cho mọi chức năng nghiệp vụ.

Ví dụ:

```java
public abstract class BaseCrudService<T, ID> {
    protected abstract JpaRepository<T, ID> repository();

    public T get(ID id) {
        return repository().findById(id).orElseThrow();
    }

    public T update(ID id, T entity) {
        T existing = get(id);
        copyFields(entity, existing);
        return repository().save(existing);
    }

    public void delete(ID id) {
        repository().delete(get(id));
    }
}
```

`update()` không cho biết trường nào được phép sửa, ai được sửa, trạng thái nào cho phép thay đổi hoặc cần phát sự kiện gì. `delete()` có thể bỏ qua quy tắc hủy đơn hàng, khóa tài khoản, lưu audit hoặc kiểm tra phụ thuộc. API tổng quát tạo cảm giác tái sử dụng nhưng không diễn đạt use case.

### Tách use case có ý nghĩa nghiệp vụ

Thay vì một `update()` chung, hãy tạo hành vi như `ChangeTaskTitle`, `AssignTask`, `CompleteTask` hoặc `CancelOrder`. Application service tải aggregate, kiểm tra actor/quyền, gọi hành vi Model và lưu thay đổi trong transaction.

```java
@Service
public class CompleteTaskService implements CompleteTaskUseCase {
    private final TaskRepository tasks;
    private final TaskAccessPolicy accessPolicy;

    public CompleteTaskService(
            TaskRepository tasks,
            TaskAccessPolicy accessPolicy) {
        this.tasks = tasks;
        this.accessPolicy = accessPolicy;
    }

    @Transactional
    public void handle(CompleteTaskCommand command) {
        Task task = tasks.findById(command.taskId())
                .orElseThrow(TaskNotFoundException::new);
        accessPolicy.ensureCanComplete(command.actorId(), task);
        task.complete();
        tasks.save(task);
    }
}
```

Repository abstraction vẫn có thể dùng chung theo hợp đồng persistence. Điều cần tránh là dùng một CRUD superclass để thay thế các quyết định nghiệp vụ khác nhau. Nếu nhiều thao tác thật sự có cùng semantics, có thể dùng helper nội bộ hoặc generic repository ở tầng phù hợp mà không làm mất tên use case.

## Thành phần View dùng chung quá lớn

Trong ứng dụng server-side MVC, fragment/template component giúp tái sử dụng header, navigation, form field, pagination hoặc thông báo. Vấn đề xuất hiện khi một fragment nhận quá nhiều cờ và tự quyết định dữ liệu hoặc nghiệp vụ cho mọi trang.

Ví dụ fragment khó bảo trì:

```html
<div th:fragment="taskPanel(task, admin, compact, showOwner, allowEdit, showBilling)">
  <!-- Nhiều nhánh điều kiện cho từng loại màn hình -->
</div>
```

Nếu fragment có hàng loạt tham số boolean, rất khó biết tổ hợp nào hợp lệ. `admin=true` có thể làm hiện nút, `allowEdit=true` có thể ẩn nút khác, còn `showBilling` lại truy cập một object chỉ có ở trang quản trị. Fragment đã trở thành một component đa mục đích không có hợp đồng rõ.

### Chia fragment theo trách nhiệm trình bày

Tách các phần có ý nghĩa độc lập như:

- `page-header`: tiêu đề và breadcrumb;
- `form-field`: label, input và lỗi validation;
- `pagination`: liên kết trang dựa trên page metadata;
- `flash-messages`: thông báo tạm;
- `task-status-badge`: hiển thị trạng thái đã được chuẩn hóa.

Fragment nhận dữ liệu cần thiết qua tham số hoặc model attribute rõ ràng. Nó không gọi repository, không tự lấy principal từ security context và không quyết định quyền truy cập. Controller/use case cung cấp dữ liệu và quyền hiển thị; endpoint vẫn kiểm tra quyền khi nhận hành động.

Một fragment có thể nhận `canEdit` để ẩn/hiện nút, nhưng đó chỉ là quyết định trình bày. Không được xem cờ này là kiểm soát truy cập. Người dùng vẫn có thể gọi endpoint trực tiếp.

### Tránh fragment gắn với một trang cụ thể

Nếu fragment dùng các biến toàn cục hoặc tên attribute ngầm như `currentProject`, `selectedOrder`, `adminMode`, nó phụ thuộc vào trang gọi và khó tái sử dụng. Hãy truyền dữ liệu qua contract tường minh. Khi hai màn hình cần cách trình bày gần giống nhưng dữ liệu/ý nghĩa khác nhau, có thể tạo hai fragment nhỏ thay vì một fragment với nhiều cờ.

## Shared utility trở thành God Object

Các lớp `CommonUtils`, `ApplicationHelper`, `BaseManager` hoặc `GlobalContext` thường bắt đầu với vài hàm nhỏ rồi dần tích tụ logic không liên quan. Một lớp có thể vừa format ngày, đọc principal, gọi repository, gửi email, tạo URL, kiểm tra quyền và ghi audit.

Đây là dấu hiệu vi phạm Single Responsibility Principle (SRP): lớp có nhiều lý do để thay đổi. Nó cũng làm dependency khó quan sát vì bất kỳ phần nào cũng có thể gọi helper toàn cục.

Thay vì:

```java
CommonUtils.currentUser();
CommonUtils.formatDate(date);
CommonUtils.saveAudit(event);
CommonUtils.sendNotification(message);
```

Hãy đặt hành vi vào thành phần có tên theo trách nhiệm:

```java
currentActorProvider.currentActor();
dateFormatter.format(date);
auditRecorder.record(event);
notificationSender.send(message);
```

Không nhất thiết tạo interface cho mọi helper. Một class `DateFormatter` thuần có thể là final class với phương thức tĩnh hoặc instance đơn giản. Interface phù hợp khi cần thay implementation, cô lập phụ thuộc ngoài hoặc xác định một port của application layer.

## Chọn composition thay cho inheritance

Composition nghĩa là một đối tượng dùng một collaborator để thực hiện một trách nhiệm. Nó thường phù hợp khi mục tiêu là chia sẻ hành vi mà không khẳng định quan hệ kiểu cha–con.

Ví dụ, thay vì để nhiều Controller kế thừa `BaseController` để lấy thông tin actor, có thể inject một abstraction:

```java
public interface CurrentActorProvider {
    UserId currentUserId();
}
```

```java
@Component
public class SpringSecurityCurrentActorProvider
        implements CurrentActorProvider {

    @Override
    public UserId currentUserId() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null
                || !authentication.isAuthenticated()
                || !(authentication.getPrincipal() instanceof AppPrincipal principal)) {
            throw new UnauthenticatedException();
        }
        return principal.userId();
    }
}
```

Controller hoặc application adapter nhận provider qua constructor. Trong nhiều use case, truyền `UserId`/`ActorContext` tường minh vào command còn rõ hơn việc service tự truy cập provider. `CurrentActorProvider` phù hợp ở ranh giới nơi cần chuyển context framework thành dữ liệu ứng dụng; không nên biến nó thành cách truy cập ngầm ở mọi tầng.

Composition có một số lợi ích:

- dependency được khai báo qua constructor và dễ nhìn thấy;
- mỗi collaborator có thể được kiểm thử riêng;
- một hành vi có thể được dùng ở nhiều lớp không cùng hierarchy;
- thay đổi một collaborator ít ảnh hưởng đến quan hệ kiểu;
- có thể kết hợp các implementation khác nhau theo cấu hình.

Tuy nhiên, composition cũng có chi phí: quá nhiều object nhỏ hoặc wrapper không có ý nghĩa sẽ làm luồng gọi khó theo dõi. Chỉ tách collaborator khi nó đại diện cho một trách nhiệm hoặc ranh giới phụ thuộc rõ.

## Dùng cơ chế framework cho cross-cutting concern

Một số hành vi thường bị đưa vào Base Controller vì nhiều endpoint cùng cần. Spring MVC/Spring Security cung cấp cơ chế chuyên biệt hơn:

| Nhu cầu dùng chung | Cơ chế phù hợp có thể dùng | Điều cần tránh |
|---|---|---|
| Ánh xạ exception thành HTTP response | `@ControllerAdvice`, `@ExceptionHandler` | Mỗi Controller tự catch mọi exception giống nhau |
| Xác thực và bảo vệ endpoint | Spring Security filter chain, method security | Base Controller tự kiểm tra token bằng code lặp |
| Ghi nhận request/correlation ID | Servlet Filter, observation/tracing | Mọi Controller tự tạo ID và ghi log |
| Xử lý tham số chung | `HandlerMethodArgumentResolver` hoặc `@ModelAttribute` phù hợp | Đọc request parameter ở nhiều lớp cha |
| Validation đầu vào | Bean Validation, validator chuyên biệt | Base Controller chứa mọi điều kiện validation |
| Transaction | `@Transactional` ở application service hoặc ranh giới phù hợp | Controller tự mở/đóng transaction |
| Audit | Application event, audit service hoặc interceptor phù hợp | Mọi lớp con gọi một phương thức protected không rõ semantics |
| Dữ liệu trình bày chung | View component/fragment với contract rõ | Một `prepareModel()` truy vấn nhiều nguồn cho mọi trang |

Framework hook cũng cần dùng có chủ đích. Không chuyển toàn bộ logic vào interceptor hoặc advice chỉ để tránh Controller. Một cross-cutting concern nên được đặt ở đúng ranh giới và giữ phạm vi nhỏ.

## Không biến interface dùng chung thành hợp đồng quá rộng

Lạm dụng không chỉ xảy ra với class cha. Một interface như `BaseCrudOperations<T>` có thể ép mọi service phải hỗ trợ `delete`, `findAll` hoặc `update`, dù một số aggregate không được xóa hoặc không có danh sách không phân trang.

Theo Interface Segregation Principle (ISP), client không nên phụ thuộc vào những phương thức nó không cần. Có thể tách các capability nhỏ hoặc định nghĩa port theo use case:

```java
public interface FindTaskDetails {
    Optional<TaskDetails> findDetails(TaskId id);
}

public interface SaveTask {
    void save(Task task);
}
```

Không cần tách interface chỉ để có nhiều file. Hãy bắt đầu từ nhu cầu của client và ranh giới kiến trúc. Một interface nhỏ có ý nghĩa tốt hơn một interface tổng quát mà implementation phải ném `UnsupportedOperationException` cho một nửa phương thức.

## Phân biệt trùng lặp thực sự với sự giống nhau tình cờ

Hai đoạn code có thể giống nhau về cú pháp nhưng khác nhau về lý do thay đổi. Ví dụ:

- form tạo công việc và form tạo hóa đơn đều có trường `title`, nhưng quy tắc validation và lifecycle khác nhau;
- hai Controller đều trả View tên `detail`, nhưng một trang có quyền xem theo owner còn trang kia theo tenant;
- hai entity đều có `createdAt`, nhưng một giá trị là thời điểm tạo bản ghi kỹ thuật, giá trị kia là thời điểm nghiệp vụ phát sinh;
- hai service đều có phương thức `delete`, nhưng một bên xóa bản nháp, bên kia phải hủy hợp đồng và phát sự kiện.

Nếu gộp quá sớm, abstraction phải thêm tham số, cờ hoặc hook để xử lý khác biệt. Đây thường là dấu hiệu các khái niệm không thực sự chung.

Một quy tắc hữu ích là chờ đến khi có vài trường hợp thực tế và hiểu rõ điều gì ổn định trước khi tạo abstraction. Tuy nhiên, không cần chờ lặp lại một lỗ hổng bảo mật hoặc logic nguy hiểm mới tách thành phần; các chính sách cần thống nhất như kiểm tra quyền hoặc mã hóa dữ liệu nên được tập trung sớm khi hợp đồng đã rõ.

## Đánh giá abstraction trước khi tạo

Trước khi tạo lớp cơ sở, component dùng chung hoặc helper, hãy trả lời:

1. **Cùng ý nghĩa hay chỉ giống cú pháp?** Các nơi sử dụng có cùng quy tắc và cùng lý do thay đổi không?
2. **Hợp đồng ổn định là gì?** Người dùng thành phần cần biết điều gì và không cần biết điều gì?
3. **Có quan hệ is-a thực sự không?** Nếu không, composition có diễn đạt tốt hơn không?
4. **Có thể thay thế không?** Lớp con/implementation có giữ cùng semantics và invariant không?
5. **Ai sở hữu dữ liệu?** Thành phần dùng chung có đang truy cập ngầm repository, request, session hoặc global state không?
6. **Có nhiều lý do thay đổi không?** Thành phần có đang gom presentation, nghiệp vụ, persistence và security không?
7. **Phạm vi ảnh hưởng là gì?** Một thay đổi có thể làm hỏng bao nhiêu Controller/View/use case?
8. **Có thể kiểm thử độc lập không?** Có thể tạo instance với dependency rõ ràng và xác minh hành vi không?
9. **Có cơ chế framework phù hợp không?** Filter, interceptor, advice, validator hoặc component có giải quyết đúng ranh giới không?
10. **Chi phí abstraction có thấp hơn lợi ích không?** Một vài dòng lặp có thể dễ hiểu hơn hierarchy tổng quát.

## Refactor Base Controller phình to

Không cần viết lại toàn bộ ứng dụng trong một lần. Có thể giảm phụ thuộc theo từng nhóm:

1. **Lập danh sách field và phương thức được lớp con dùng.** Phân biệt helper trình bày, truy cập security, repository, audit và logic nghiệp vụ.
2. **Đưa dependency ngầm ra constructor.** Trước hết chuyển field injection sang constructor injection để nhìn rõ Controller thực sự cần gì.
3. **Tách cross-cutting concern.** Chuyển exception mapping sang `@ControllerAdvice`, authentication sang Spring Security, request correlation sang filter/observation.
4. **Tạo collaborator nhỏ cho phần thực sự dùng chung.** Ví dụ `TaskPageDataProvider` hoặc `CurrentActorProvider`, với contract cụ thể.
5. **Chuyển quy tắc vào use case/Model.** Controller chỉ parse request, tạo command, gọi use case và chọn response.
6. **Thu hẹp lớp cha.** Nếu lớp cha chỉ còn một hợp đồng thực sự ổn định, cân nhắc giữ; nếu không, xóa hierarchy sau khi các client đã chuyển.
7. **Kiểm thử từng route bị ảnh hưởng.** Bao gồm response, quyền truy cập, model attribute, validation, lỗi và redirect.

### Tránh thay Base Controller bằng một God Service

Một refactor thất bại thường chỉ chuyển `BaseController` thành `CommonControllerService` có hàng chục phương thức. Đổi tên không làm trách nhiệm nhỏ hơn. Hãy chia theo capability và use case; mỗi collaborator nên có một mục đích dễ giải thích.

## Refactor Shared View Component

Với fragment hoặc component dùng chung:

1. Liệt kê tất cả tham số, cờ và model attribute mà component đọc.
2. Xác định phần nào là trình bày thuần, phần nào đang truy cập nghiệp vụ hoặc persistence.
3. Chuyển truy vấn và quyết định quyền ra Controller/use case.
4. Định nghĩa input/output rõ ràng cho fragment.
5. Tách component theo trách nhiệm như form field, pagination, status badge hoặc navigation.
6. Giữ component có thể render bằng dữ liệu giả nhỏ trong test.
7. Kiểm tra các trang sử dụng sau khi thay đổi để phát hiện CSS, accessibility và behavior bị ảnh hưởng.

Nếu hai fragment khác nhau ở hầu hết nhánh điều kiện, hãy cân nhắc tách chúng. Trùng một vài dòng markup thường rẻ hơn một component có hàng chục cờ.

## Kiểm thử để phát hiện tác động lan truyền

Thành phần dùng chung cần test hợp đồng của chính nó và kiểm tra một số client tiêu biểu. Không nhất thiết test lại mọi dòng code của mọi lớp con, nhưng phải kiểm tra các biến thể quan trọng.

| Thành phần | Unit/contract test | Kiểm thử tích hợp hoặc regression |
|---|---|---|
| Base class hợp lệ | Hợp đồng chung và hành vi mặc định | Một số lớp con đại diện giữ đúng semantics |
| Shared service | Input/output, lỗi, giới hạn và side effect | Use case thực tế gọi đúng collaborator |
| View fragment | Tham số, trạng thái rỗng, escape và nhánh trình bày | Các trang chính render đúng sau refactor |
| `@ControllerAdvice` | Ánh xạ lỗi và response schema | Endpoint trả đúng status/body cho lỗi đại diện |
| Security/interceptor | Chính sách và phạm vi áp dụng | Route công khai, route bảo vệ và route ngoại lệ |
| BaseEntity/mapping | Invariant và mapping cần thiết | Persistence, auditing, optimistic locking và migration |

### Kiểm thử contract cho lớp cha

Nếu vẫn cần một abstract base class, có thể viết test contract dùng chung cho các implementation để xác minh chúng tuân thủ cùng quy tắc. Test cần tập trung vào API công khai và semantics, không kiểm tra protected field hoặc thứ tự gọi nội bộ.

Nếu các lớp con liên tục phải override để bỏ qua test contract, đó là tín hiệu hierarchy không còn phù hợp. Hãy cân nhắc composition hoặc chia interface theo capability.

### Kiểm thử hồi quy cho Controller và View

Khi thay `BaseController`, kiểm tra tối thiểu:

- route và HTTP method vẫn như hợp đồng;
- request binding và validation vẫn đúng;
- model attribute cần cho template vẫn có;
- authentication/authorization không bị nới lỏng;
- business rejection và technical error được ánh xạ đúng;
- redirect và flash message vẫn hoạt động;
- template không phụ thuộc vào attribute ngầm đã bị bỏ.

Một test chỉ xác minh trang trả 200 có thể bỏ sót việc dữ liệu quan trọng không còn trong model hoặc nút hành động bị hiển thị sai.

## Ví dụ quyết định nên dùng gì

| Nhu cầu | Lựa chọn thường phù hợp | Vì sao |
|---|---|---|
| Nhiều Controller cần cùng cách ánh xạ lỗi | `@ControllerAdvice` | Framework cung cấp hook đúng ở ranh giới MVC |
| Nhiều use case cần kiểm tra cùng một policy | Domain/application policy được inject | Quy tắc có tên, có thể test và dùng ngoài HTTP |
| Nhiều trang cần cùng header tĩnh | Shared fragment/component | Đây là trách nhiệm trình bày |
| Nhiều Controller cần principal hiện tại | `@AuthenticationPrincipal` hoặc abstraction nhỏ ở web adapter | Dependency bảo mật rõ ràng, không cần hierarchy |
| Nhiều entity có cùng ID/version semantics | Base class hoặc mapping composition có kiểm soát | Có hợp đồng kỹ thuật thực sự chung |
| Nhiều use case có thao tác giống nhau nhưng quy tắc khác | Use case riêng, có thể dùng helper nội bộ | Giữ tên và semantics nghiệp vụ |
| Nhiều component cần format ngày | Formatter thuần hoặc service định dạng | Không cần kế thừa Controller/View |
| Nhiều client cần cùng use case | Application service dùng chung qua adapter riêng | UI/API không sở hữu bản sao nghiệp vụ |

## Những sai lầm cần tránh khi tái sử dụng

- **Kế thừa chỉ để lấy một helper:** tạo quan hệ kiểu giả. Inject collaborator hoặc dùng hàm thuần.
- **Base Controller giữ mọi dependency:** lớp con có quyền truy cập quá rộng và dependency bị ẩn. Khai báo dependency cụ thể ở constructor.
- **Lớp cha có nhiều protected field:** đóng gói bị phá vỡ và lớp con phụ thuộc nội bộ. Giữ API nhỏ, ưu tiên composition.
- **BaseEntity chứa mọi metadata:** entity bị ép theo persistence. Chỉ chia sẻ field có semantics chung.
- **Generic CRUD thay thế use case:** bỏ qua invariant và quyền. Dùng hành vi có tên nghiệp vụ.
- **Fragment có quá nhiều boolean:** hợp đồng khó hiểu và số tổ hợp tăng. Chia component theo trách nhiệm.
- **CommonUtils thành God Object:** nhiều lý do thay đổi và phụ thuộc ngầm. Chia theo capability.
- **Tạo abstraction chỉ vì hai đoạn code giống nhau:** bỏ qua khác biệt về ý nghĩa. Xác định cùng lý do thay đổi trước.
- **Dùng interface cho mọi class:** tạo gián tiếp không có lợi ích. Chỉ trừu tượng hóa khi có ranh giới hoặc nhu cầu thay thế.
- **Thay một lớp cha lớn bằng một service lớn:** chỉ chuyển vị trí của vấn đề. Giữ mỗi thành phần có một trách nhiệm.
- **Không kiểm thử các client dùng chung:** thay đổi lan truyền không được phát hiện. Có contract test và regression test đại diện.

## Checklist review trước khi merge

- Quan hệ kế thừa phản ánh đúng quan hệ is-a và giữ được hợp đồng của lớp cha.
- Lớp cha không chứa dependency hoặc state không cần thiết cho lớp con.
- Controller khai báo dependency rõ ràng qua constructor.
- View không gọi repository hoặc tự quyết định quy tắc nghiệp vụ.
- Domain Model không bị ép kế thừa một lớp chỉ để tái sử dụng vài field kỹ thuật.
- Generic service không che khuất tên và semantics của use case.
- Shared fragment có input rõ, ít cờ và không chứa truy vấn nghiệp vụ.
- Cross-cutting concern dùng đúng hook framework khi phù hợp.
- Không tạo God Object mới sau khi refactor.
- Abstraction có nhiều client thực sự cùng hợp đồng hoặc có lý do thay thế rõ.
- Test bao phủ hợp đồng chung và các client/route quan trọng.
- Thay đổi có phạm vi ảnh hưởng xác định và không làm suy yếu authorization.

## Quy trình chọn mức tái sử dụng

Khi thấy mã lặp, hãy tiến hành theo thứ tự:

1. **Hiểu lý do lặp:** xác định hai đoạn mã cùng ý nghĩa hay chỉ trùng cấu trúc.
2. **Tìm ranh giới sở hữu:** nghiệp vụ, giao diện, persistence, security hay hạ tầng chịu trách nhiệm?
3. **Đặt tên cho hợp đồng:** mô tả điều thành phần đảm bảo và điều nó không đảm bảo.
4. **Chọn cơ chế:** hàm thuần, collaborator, policy, component/fragment, framework hook, interface hoặc inheritance.
5. **Giữ API nhỏ:** tránh nhiều boolean, protected field và hook không rõ nghĩa.
6. **Kiểm tra thay thế:** implementation/lớp con có giữ semantics chung không?
7. **Đánh giá phụ thuộc:** client có cần biết chi tiết nội bộ của thành phần không?
8. **Viết test hợp đồng:** xác minh hành vi chung và các nhánh quan trọng.
9. **Refactor từng bước:** chuyển client, kiểm thử regression rồi mới loại bỏ mã cũ.
10. **Đo lại chi phí:** số lớp, dependency và độ khó hiểu có thực sự giảm không?

## Câu hỏi tự đánh giá

1. Vì sao kế thừa để chia sẻ vài dòng helper có thể tạo coupling lớn hơn lợi ích?
2. Dấu hiệu nào cho thấy một `BaseController` đã trở thành nơi chứa mọi logic?
3. Khi nào `@MappedSuperclass` hợp lý và khi nào BaseEntity đang ép mô hình miền?
4. Vì sao generic CRUD service có thể bỏ qua invariant và quyền của use case?
5. Một shared View fragment nên nhận dữ liệu qua hợp đồng nào và không nên tự làm gì?
6. Composition khác inheritance ở cách biểu diễn quan hệ và phụ thuộc ra sao?
7. Khi nào nên dùng `@ControllerAdvice`, filter, interceptor hoặc policy thay cho lớp cha?
8. Làm thế nào phân biệt trùng lặp thực sự với sự giống nhau tình cờ?
9. Cần kiểm thử những gì khi refactor thành phần được nhiều Controller/View dùng chung?
10. Vì sao thay `BaseController` bằng `CommonService` lớn không giải quyết được vấn đề gốc?

Tái sử dụng tốt trong MVC bắt đầu từ một hợp đồng chung có ý nghĩa, không phải từ việc tìm mọi dòng code giống nhau. Kế thừa phù hợp khi có quan hệ thay thế thực sự; composition phù hợp khi chỉ cần phối hợp một trách nhiệm; shared View component phù hợp khi hợp đồng trình bày ổn định; framework hook phù hợp cho cross-cutting concern. Khi Controller, Model và View giữ đúng trách nhiệm, thành phần dùng chung sẽ giảm lặp mà không tạo ra phụ thuộc ngầm hoặc làm thay đổi một nơi lan rộng ngoài dự kiến.
