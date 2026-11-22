# MVC trong kiến trúc phân lớp

MVC (Model–View–Controller) và kiến trúc phân lớp giải quyết hai vấn đề có liên quan nhưng khác nhau. MVC tổ chức trách nhiệm trong phần trình bày và tương tác với người dùng: Controller tiếp nhận hành động, Model cung cấp dữ liệu và quy tắc liên quan, View hiển thị kết quả. Kiến trúc phân lớp tổ chức toàn bộ ứng dụng theo các nhóm trách nhiệm như trình bày, điều phối use case, nghiệp vụ và hạ tầng lưu trữ.

Vì vậy, MVC thường được đặt **bên trong lớp trình bày** của một ứng dụng phân lớp. Controller nhận HTTP request, chuyển dữ liệu thành lệnh ứng dụng, gọi application service; service điều phối nghiệp vụ trong Model và truy cập dữ liệu qua repository; View nhận ViewModel hoặc response DTO để hiển thị. Cách kết hợp này giữ cho giao diện không phải biết cách lưu dữ liệu, còn nghiệp vụ không phụ thuộc vào HTTP, template hay framework web.

Điểm cần nắm vững là MVC không thay thế kiến trúc phân lớp và cũng không có nghĩa toàn bộ ứng dụng chỉ gồm ba lớp Model, View, Controller. Một ứng dụng MVC có thể có nhiều lớp bên trong Model, nhiều dịch vụ ứng dụng và nhiều adapter hạ tầng. Việc xác định đúng ranh giới giúp hệ thống dễ thay đổi giao diện, kiểm thử nghiệp vụ và mở rộng cơ chế lưu trữ.

## 1. MVC và kiến trúc phân lớp giải quyết hai chiều tổ chức

MVC tập trung vào cách một yêu cầu của người dùng được tiếp nhận và trình bày:

- **Model:** dữ liệu và hành vi liên quan đến trạng thái/nghiệp vụ mà ứng dụng cần xử lý.
- **View:** cách biểu diễn dữ liệu cho người dùng, chẳng hạn trang HTML, template hoặc một dạng response.
- **Controller:** điểm tiếp nhận tương tác, chuyển đầu vào thành thao tác phù hợp và chọn kết quả trình bày.

Kiến trúc phân lớp tập trung vào cách chia ứng dụng theo trách nhiệm kỹ thuật và nghiệp vụ:

- **Presentation layer:** giao tiếp với người dùng hoặc client.
- **Application layer:** điều phối use case, transaction và các bước nghiệp vụ.
- **Domain layer:** mô hình hóa khái niệm, trạng thái, quy tắc và bất biến cốt lõi.
- **Infrastructure layer:** database, message broker, file storage, email client và các hệ thống bên ngoài.

Hai cách tổ chức này bổ sung cho nhau. MVC mô tả các vai trò trong phần giao tiếp; layered architecture mô tả các vùng trách nhiệm xuyên suốt ứng dụng.

~~~mermaid
flowchart TB
    subgraph P["Presentation layer — MVC"]
        V["View / Template"]
        C["Controller"]
        VM["Form / ViewModel / Response DTO"]
        C --> VM
        VM --> V
        V --> C
    end

    subgraph A["Application layer"]
        U["Use case / Application Service"]
        PORT["Repository Port / Gateway Port"]
    end

    subgraph D["Domain layer"]
        M["Domain Model"]
        RULE["Business Rules / Invariants"]
    end

    subgraph I["Infrastructure layer"]
        AD["Persistence / External Service Adapters"]
        DB[("Database")]
        EXT["External Services"]
    end

    C --> U
    U --> M
    M --> RULE
    U --> PORT
    AD -. "implements" .-> PORT
    AD --> DB
    AD --> EXT
~~~

Sơ đồ thể hiện ranh giới trách nhiệm. Khi dùng dependency inversion, application/domain định nghĩa các port mà nó cần; infrastructure cung cấp adapter triển khai các port đó. Ở runtime, application gọi interface và đối tượng adapter được inject sẽ thực hiện truy cập database hoặc dịch vụ ngoài.

## 2. Vì sao không nên coi MVC là toàn bộ kiến trúc?

Một ứng dụng nhỏ có thể bắt đầu với Controller, Model và View. Khi chức năng tăng lên, mỗi phần sẽ có nhiều trách nhiệm khác nhau:

- Controller cần binding, validation, phân quyền và điều hướng.
- Model có thể chứa entity, value object, quy tắc nghiệp vụ và trạng thái.
- View cần dữ liệu đã định dạng, phân trang và thông báo.
- Ứng dụng cần transaction, repository, cache, tích hợp dịch vụ ngoài và logging.

Nếu gom tất cả vào ba nhóm MVC mà không có ranh giới bên trong, Controller dễ trở thành nơi chứa nghiệp vụ; Model có thể phụ thuộc trực tiếp vào database; View có thể tự truy vấn dữ liệu. Khi đó, tên MVC vẫn xuất hiện trong dự án nhưng khả năng phân tách trách nhiệm đã suy giảm.

Kiến trúc phân lớp bổ sung những ranh giới cần thiết để mỗi thành phần biết mình chịu trách nhiệm về điều gì và được phép phụ thuộc vào đâu.

### 2.1. MVC không đồng nghĩa với ba package

Không bắt buộc dự án phải có đúng ba package `model`, `view`, `controller`. Một tổ chức như vậy có thể phù hợp với ứng dụng rất nhỏ, nhưng trong ứng dụng lớn thường khó giữ các use case và module nghiệp vụ tách biệt.

Có thể tổ chức theo feature hoặc bounded context, bên trong mỗi feature lại chia presentation, application, domain và infrastructure. Cách này giúp các file liên quan đến một chức năng ở gần nhau mà vẫn giữ ranh giới kiến trúc.

## 3. Vai trò của từng lớp trong kiến trúc MVC phân lớp

### 3.1. Presentation layer: tiếp nhận và trình bày

Presentation layer chịu trách nhiệm chuyển đổi giao thức bên ngoài thành lời gọi ứng dụng và chuyển kết quả thành response.

Trong ứng dụng Spring MVC, phần này thường gồm:

- Controller nhận path variable, query parameter, form hoặc JSON.
- Request DTO/Form object mô tả dữ liệu client gửi.
- Validation đầu vào thuộc hợp đồng giao tiếp.
- ViewModel/Response DTO chứa dữ liệu cần hiển thị.
- View template hoặc serializer tạo HTML/JSON.
- Exception handler ánh xạ lỗi thành HTTP response.

Presentation layer không nên quyết định quy tắc nghiệp vụ cốt lõi hoặc tự viết SQL. Nó có thể kiểm tra dữ liệu đầu vào theo hợp đồng, nhưng Model vẫn phải bảo vệ bất biến vì use case có thể được gọi từ API khác, tác vụ nền hoặc test.

### 3.2. Application layer: điều phối use case

Application layer mô tả ứng dụng làm gì khi một hành động xảy ra. Ví dụ:

- Tạo công việc.
- Duyệt đơn hàng.
- Đổi trạng thái hồ sơ.
- Tìm danh sách theo bộ lọc.
- Hủy một tác vụ đang chờ.

Application service thường:
- Nhận command/query đã được chuẩn hóa.
- Kiểm tra các điều kiện điều phối của use case.
- Gọi domain model để thực hiện quy tắc.
- Gọi repository hoặc gateway qua interface.
- Quản lý ranh giới transaction.
- Trả kết quả ứng dụng cho adapter gọi nó.

Application layer không nên phụ thuộc vào HttpServletRequest, template engine hoặc loại response của Spring MVC. Một use case nên có thể được gọi từ Controller, message handler hoặc tác vụ nền mà không cần giả lập HTTP.

### 3.3. Domain layer: bảo vệ quy tắc nghiệp vụ

Domain layer chứa các khái niệm và quy tắc cốt lõi của miền nghiệp vụ. Ví dụ với quản lý công việc:

- Task và TaskStatus.
- Quy tắc tiêu đề không được rỗng.
- Chỉ công việc đang mở mới được hoàn tất.
- Công việc đã hủy không thể chuyển sang trạng thái đang xử lý.
- Value object như TaskId hoặc Priority.

Domain model không nên biết request đến từ trình duyệt, route nào gọi nó hoặc View nào hiển thị kết quả. Quy tắc phải đúng dù thao tác đến từ web, API, message consumer hay tác vụ định kỳ.

### 3.4. Infrastructure layer: chi tiết kỹ thuật

Infrastructure layer cung cấp cách thực thi các nhu cầu mà application/domain khai báo:

- JPA entity và Spring Data repository.
- JDBC, SQL hoặc ORM mapping.
- Adapter triển khai repository port.
- Kết nối database, cache và message broker.
- Email client, HTTP client hoặc object storage.
- Cấu hình kỹ thuật và tích hợp framework.

Infrastructure có thể phụ thuộc vào framework, database driver hoặc SDK của nhà cung cấp. Các tầng nghiệp vụ nên làm việc qua interface ổn định để không phải phụ thuộc trực tiếp vào các chi tiết này.

## 4. Phân biệt Model của MVC với Domain Model

Từ “Model” thường gây nhầm lẫn vì nó được dùng ở nhiều ngữ cảnh.

| Khái niệm | Ý nghĩa |
|---|---|
| MVC Model | Phần dữ liệu/trạng thái mà Controller và View sử dụng để biểu diễn một tương tác |
| Domain Model | Entity, value object và quy tắc mô hình hóa nghiệp vụ |
| Application Model | Dữ liệu hoặc kết quả phục vụ một use case |
| ViewModel | Cấu trúc dữ liệu được chuẩn bị riêng cho View |
| JPA Entity | Đối tượng được ORM ánh xạ với cấu trúc lưu trữ |

Các khái niệm này có thể liên quan nhưng không nhất thiết là cùng một object.

Ví dụ trong Spring MVC, tham số `org.springframework.ui.Model` là một vùng chứa attribute để Controller chuyển dữ liệu sang View. Nó không phải toàn bộ Domain Model và cũng không phải JPA Entity.

~~~java
@GetMapping("/tasks")
String list(Model model) {
    model.addAttribute("tasks", taskQueryService.findRecent());
    return "tasks/list";
}
~~~

Ở đây, Model là container cho dữ liệu render template. `taskQueryService` có thể trả về ViewModel hoặc DTO; Controller đưa kết quả vào attribute có tên tasks.

### 4.1. Vì sao không nên đưa JPA Entity thẳng vào View?

JPA Entity thường được thiết kế theo nhu cầu persistence và quan hệ dữ liệu. Nếu đưa trực tiếp entity vào template hoặc JSON response:

- View có thể vô tình kích hoạt lazy loading.
- Quan hệ hai chiều có thể gây vòng lặp khi serialize.
- Trường nội bộ có thể bị lộ.
- Thay đổi schema hoặc mapping có thể làm vỡ giao diện.
- Client có thể gửi lại các trường không được phép cập nhật.
- View có thể phụ thuộc vào cấu trúc domain/persistence quá sâu.

Nên tạo ViewModel hoặc Response DTO chứa đúng dữ liệu mà giao diện cần. Khi request cập nhật, dùng Request DTO hoặc Command riêng, không binding thẳng vào entity.

## 5. Quy tắc phụ thuộc giữa các lớp

Một kiến trúc phân lớp cần xác định rõ chiều phụ thuộc. Với cách tổ chức truyền thống, presentation gọi application, application gọi domain và các interface truy cập dữ liệu. Infrastructure triển khai các interface này.

~~~mermaid
flowchart TD
    P["Presentation"] --> A["Application"]
    A --> D["Domain"]
    I["Infrastructure"] -. "implements ports" .-> A
    I --> DB[("Database / External Systems")]
~~~

Các nguyên tắc hữu ích:

1. Presentation có thể phụ thuộc vào application contract.
2. Application có thể sử dụng domain model và các port cần thiết.
3. Domain không phụ thuộc vào Controller, View, Spring MVC hoặc database driver.
4. Infrastructure có thể phụ thuộc vào framework và triển khai port do tầng trong định nghĩa.
5. Không để View truy cập repository trực tiếp.
6. Không để application service nhận hoặc trả kiểu HTTP như ResponseEntity.
7. Không để domain exception phụ thuộc vào status code HTTP.

Cần phân biệt **chiều phụ thuộc mã nguồn** và **luồng gọi lúc chạy**. Lúc chạy, application service gọi repository interface; đối tượng thực tế được inject có thể là adapter nằm trong infrastructure. Dependency inversion giúp mã nguồn tầng trong không cần phụ thuộc vào implementation bên ngoài.

### 5.1. Layering nghiêm ngặt và layer mở

Một số hệ thống dùng strict layering: tầng chỉ được gọi tầng ngay dưới nó. Ví dụ presentation chỉ gọi application; application không được gọi trực tiếp infrastructure implementation.

Một số hệ thống cho phép tầng bỏ qua một số tầng (relaxed/open layering) để phục vụ nhu cầu cụ thể. Tuy nhiên, nếu Controller gọi thẳng repository trong khi use case có quy tắc, transaction hoặc phân quyền, logic dễ bị phân tán.

Không phải mọi truy vấn đều cần một service chỉ để chuyển tiếp. Có thể dùng query service hoặc application query handler gọn nhẹ. Điều quan trọng là mọi đường truy cập vẫn tuân thủ chính sách và không phá vỡ ranh giới trách nhiệm.

## 6. Luồng xử lý một request trong MVC phân lớp

Xét chức năng tạo công việc:

1. View hiển thị form.
2. Người dùng gửi POST.
3. Controller binding dữ liệu vào Request DTO và kiểm tra validation.
4. Controller lấy danh tính đã xác thực từ security context.
5. Controller tạo command và gọi use case.
6. Application service mở transaction, gọi domain model và repository port.
7. Infrastructure adapter lưu dữ liệu qua ORM/database.
8. Application service trả kết quả.
9. Controller tạo redirect hoặc response DTO.
10. View hiển thị kết quả.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant V as View
    participant C as Controller
    participant A as Application Service
    participant D as Domain Model
    participant R as Repository Port
    participant I as Persistence Adapter
    participant DB as Database

    User->>V: Nhập thông tin công việc
    V->>C: POST /tasks
    C->>C: Binding + validation
    C->>A: CreateTaskCommand
    A->>D: Task.create(...)
    D-->>A: Task hợp lệ
    A->>R: save(task)
    R->>I: Gọi adapter triển khai port
    I->>DB: INSERT
    DB-->>I: Kết quả lưu
    I-->>A: Hoàn tất
    A-->>C: CreateTaskResult
    C-->>V: Redirect / response
    V-->>User: Hiển thị kết quả
~~~

Sơ đồ runtime có thể biểu diễn lời gọi qua interface và adapter. Trong triển khai, domain model thường được tạo hoặc thay đổi trước khi repository lưu; repository port thuộc application/domain tùy cách tổ chức. Điểm chính là Controller không tự điều khiển SQL và database không quyết định cách trình bày response.

### 6.1. Request và response là hợp đồng của presentation

Request DTO nên mô tả dữ liệu client được phép gửi. Response DTO hoặc ViewModel mô tả dữ liệu client được phép nhận. Không nên dùng cùng một entity cho cả hai chiều.

Ví dụ:
- CreateTaskRequest có title và dueDate.
- CreateTaskCommand có title, dueDate và ownerId lấy từ principal.
- CreateTaskResult có taskId và trạng thái kết quả.
- TaskDetailViewModel có title, statusLabel, dueDateText và các hành động được phép hiển thị.

Các kiểu này giúp tách giao thức khỏi nghiệp vụ và lưu trữ.

## 7. Ví dụ tổ chức package trong Spring MVC

Một cấu trúc theo feature và layer có thể như sau:

~~~text
com.example.tasks
├── presentation
│   └── web
│       ├── TaskController.java
│       ├── CreateTaskForm.java
│       └── TaskDetailViewModel.java
├── application
│   └── task
│       ├── CreateTaskUseCase.java
│       ├── CreateTaskCommand.java
│       ├── CreateTaskResult.java
│       ├── CreateTaskService.java
│       └── TaskRepositoryPort.java
├── domain
│   └── task
│       ├── Task.java
│       ├── TaskId.java
│       ├── TaskStatus.java
│       └── TaskDomainException.java
└── infrastructure
    └── persistence
        └── task
            ├── TaskJpaEntity.java
            ├── SpringDataTaskRepository.java
            ├── TaskRepositoryAdapter.java
            └── TaskPersistenceMapper.java
~~~

Tên package có thể thay đổi theo quy mô và quy ước dự án. Một dự án lớn có thể chia theo bounded context như `tasks`, `orders`, `identity`; bên trong mỗi module mới chia presentation/application/domain/infrastructure. Tránh tạo một package global `controllers`, `services`, `repositories` khổng lồ khiến các feature phụ thuộc chéo khó kiểm soát.

## 8. Ví dụ Controller chỉ điều phối giao tiếp

Form object đại diện dữ liệu người dùng nhập:

~~~java
public record CreateTaskForm(
    @NotBlank
    @Size(max = 120)
    String title
) {}
~~~

Controller nhận request và chuyển thành command:

~~~java
@Controller
@RequestMapping("/tasks")
class TaskController {
    private final CreateTaskUseCase createTask;

    TaskController(CreateTaskUseCase createTask) {
        this.createTask = createTask;
    }

    @GetMapping("/new")
    String newForm(Model model) {
        model.addAttribute("form", new CreateTaskForm(""));
        return "tasks/new";
    }

    @PostMapping
    String create(
        @Valid @ModelAttribute("form") CreateTaskForm form,
        BindingResult errors,
        @AuthenticationPrincipal AppPrincipal principal,
        RedirectAttributes redirect
    ) {
        if (errors.hasErrors()) {
            return "tasks/new";
        }

        CreateTaskCommand command = new CreateTaskCommand(
            form.title(),
            principal.userId()
        );

        CreateTaskResult result = createTask.handle(command);

        redirect.addFlashAttribute(
            "notice",
            "Đã tạo công việc."
        );

        return "redirect:/tasks/" + result.taskId();
    }
}
~~~

Controller chịu trách nhiệm:
- Binding và validation theo hợp đồng form.
- Lấy danh tính đã xác thực từ framework.
- Tạo command ứng dụng.
- Gọi use case.
- Chọn View hoặc redirect.

Controller không tự tạo SQL, không tự quyết định trạng thái hợp lệ của Task và không giữ transaction cho nhiều repository.

## 9. Application service điều phối use case

Use case có thể được khai báo qua interface:

~~~java
public interface CreateTaskUseCase {
    CreateTaskResult handle(CreateTaskCommand command);
}

public record CreateTaskCommand(
    String title,
    UUID ownerId
) {}

public record CreateTaskResult(
    UUID taskId,
    TaskStatus status
) {}
~~~

Implementation quản lý transaction và gọi domain:

~~~java
@Service
class CreateTaskService implements CreateTaskUseCase {
    private final TaskRepositoryPort tasks;

    CreateTaskService(TaskRepositoryPort tasks) {
        this.tasks = tasks;
    }

    @Transactional
    public CreateTaskResult handle(CreateTaskCommand command) {
        Task task = Task.create(
            command.title(),
            command.ownerId()
        );

        tasks.save(task);

        return new CreateTaskResult(
            task.id(),
            task.status()
        );
    }
}
~~~

Application service điều phối một use case. Nó có thể kiểm tra điều kiện truy cập, lấy dữ liệu cần thiết, gọi domain method và lưu kết quả. Quy tắc cốt lõi vẫn nên được đặt trong domain model hoặc policy tương ứng để các nguồn gọi khác nhau cùng tuân thủ.

Không cần tạo interface cho mọi service một cách máy móc. Interface hữu ích khi nó thể hiện port/use case, ranh giới module hoặc điểm thay thế implementation. Với service nội bộ đơn giản, một class cụ thể có thể đủ.

## 10. Domain Model không biết HTTP hoặc JPA

Một domain object có thể bảo vệ bất biến:

~~~java
public final class Task {
    private final UUID id;
    private final UUID ownerId;
    private String title;
    private TaskStatus status;

    private Task(UUID id, UUID ownerId, String title) {
        this.id = id;
        this.ownerId = ownerId;
        this.title = title;
        this.status = TaskStatus.OPEN;
    }

    public static Task create(String title, UUID ownerId) {
        if (title == null || title.isBlank()) {
            throw new TaskDomainException(
                "Task title is required"
            );
        }

        return new Task(
            UUID.randomUUID(),
            ownerId,
            title.trim()
        );
    }

    public void complete() {
        if (status != TaskStatus.OPEN) {
            throw new TaskDomainException(
                "Only open tasks can be completed"
            );
        }

        status = TaskStatus.DONE;
    }

    public UUID id() {
        return id;
    }

    public UUID ownerId() {
        return ownerId;
    }

    public String title() {
        return title;
    }

    public TaskStatus status() {
        return status;
    }
}
~~~

Ví dụ cố ý không dùng annotation của JPA hoặc kiểu Spring MVC trong domain. Infrastructure mapper chuyển đổi giữa Task và TaskJpaEntity. Nếu dự án chọn dùng JPA entity trực tiếp làm domain object, cần hiểu rõ trade-off: domain sẽ gắn với persistence framework hơn và việc kiểm thử/đổi storage có thể khó hơn.

Không nên chuyển mọi quy tắc thành validation ở Controller. Người dùng có thể gọi endpoint khác hoặc một message handler để thực hiện cùng use case; domain vẫn phải từ chối trạng thái không hợp lệ.

## 11. Repository Port và Persistence Adapter

Application layer định nghĩa nhu cầu lưu trữ:

~~~java
public interface TaskRepositoryPort {
    void save(Task task);
    Optional<Task> findById(UUID taskId);
}
~~~

Infrastructure triển khai port bằng Spring Data JPA:

~~~java
@Repository
class TaskRepositoryAdapter implements TaskRepositoryPort {
    private final SpringDataTaskRepository repository;
    private final TaskPersistenceMapper mapper;

    TaskRepositoryAdapter(
        SpringDataTaskRepository repository,
        TaskPersistenceMapper mapper
    ) {
        this.repository = repository;
        this.mapper = mapper;
    }

    @Override
    public void save(Task task) {
        repository.save(mapper.toEntity(task));
    }

    @Override
    public Optional<Task> findById(UUID taskId) {
        return repository.findById(taskId)
            .map(mapper::toDomain);
    }
}
~~~

Adapter chịu trách nhiệm mapping và gọi persistence implementation. Application service chỉ biết TaskRepositoryPort, không cần biết JPA repository hoặc tên bảng.

Với ứng dụng nhỏ, có thể dùng Spring Data repository trực tiếp trong application service để giảm boilerplate. Khi đó, cần chấp nhận rằng application layer phụ thuộc framework/persistence abstraction. Không có một cấu trúc duy nhất phù hợp mọi dự án; mức tách lớp nên tương xứng với độ phức tạp và nhu cầu thay đổi.

## 12. View chỉ trình bày dữ liệu đã chuẩn bị

View không nên tự gọi repository hoặc chứa quy tắc nghiệp vụ. Controller hoặc query service chuẩn bị ViewModel:

~~~java
public record TaskDetailViewModel(
    UUID id,
    String title,
    String statusLabel,
    boolean canComplete
) {}
~~~

Một query service có thể kết hợp dữ liệu và quyền hiển thị:

~~~java
public TaskDetailViewModel getDetails(
    UUID taskId,
    AppPrincipal principal
) {
    Task task = tasks.findById(taskId)
        .orElseThrow(TaskNotFoundException::new);

    authorization.requireCanView(principal, task);

    return new TaskDetailViewModel(
        task.id(),
        task.title(),
        statusLabels.labelFor(task.status()),
        authorization.canComplete(principal, task)
    );
}
~~~

Ví dụ minh họa query service có thể đặt trong application layer. Việc tính `canComplete` để điều khiển hiển thị không thay thế kiểm tra quyền khi người dùng thực sự gửi lệnh hoàn tất; use case vẫn phải kiểm tra lại ở server.

View nhận dữ liệu và render:

~~~html
<h1 th:text="${task.title}">Tên công việc</h1>
<p th:text="${task.statusLabel}">Trạng thái</p>

<form th:if="${task.canComplete}"
      th:action="@{/tasks/{id}/complete(id=${task.id})}"
      method="post">
    <button type="submit">Hoàn tất</button>
</form>
~~~

View không cần biết Task được lưu trong PostgreSQL hay một hệ thống khác. Nó chỉ cần hợp đồng ViewModel ổn định.

## 13. Transaction và ranh giới use case

Trong kiến trúc phân lớp, transaction thường được đặt ở application service vì đây là nơi điều phối toàn bộ thao tác nghiệp vụ.

Ví dụ use case duyệt đơn có thể:
1. Tải đơn hàng.
2. Kiểm tra quyền và trạng thái.
3. Gọi domain method approve.
4. Lưu thay đổi.
5. Ghi lịch sử duyệt.

Nếu các thay đổi phải cùng thành công hoặc thất bại, chúng nằm trong cùng transaction. Controller không nên tự mở transaction cho từng repository hoặc giữ transaction xuyên suốt thời gian người dùng điền form.

Với Spring, `@Transactional` thường được đặt ở phương thức use case/application service. Cần chú ý proxy, self-invocation, rollback rule và propagation. Giao dịch không tự bao trùm email hoặc HTTP call tới dịch vụ ngoài; các tác dụng phụ quan trọng có thể cần after-commit event hoặc transactional outbox.

## 14. Validation và xử lý lỗi qua các lớp

Validation có thể diễn ra ở nhiều ranh giới nhưng không phải mọi loại validation có cùng mục đích:

- **Presentation validation:** kiểm tra request có đúng định dạng, trường bắt buộc và giới hạn kích thước hay không.
- **Application validation:** kiểm tra điều kiện use case, quyền và dữ liệu tham chiếu.
- **Domain validation:** bảo vệ bất biến, trạng thái và quy tắc nghiệp vụ.
- **Persistence constraints:** bảo vệ tính duy nhất, khóa ngoại, NOT NULL và các ràng buộc cuối cùng ở database.

Controller có thể dùng @Valid và BindingResult để trả lại form với lỗi theo trường. Application/domain có thể phát sinh exception nghiệp vụ. ControllerAdvice ánh xạ exception dùng chung thành HTTP response hoặc Error View.

Không nên để domain ném ResponseStatusException hoặc trả ResponseEntity, vì điều đó làm nghiệp vụ phụ thuộc giao thức HTTP. Tương tự, không nên để Controller bắt lỗi SQL rồi tự phân tích message database để quyết định thông báo.

## 15. Bảo mật cũng cần đi qua các ranh giới

MVC phân lớp giúp xác định nơi đặt kiểm soát bảo mật:

- Authentication filter xác định danh tính request.
- Controller binding request và lấy principal đã xác thực.
- Application service kiểm tra quyền thực hiện use case.
- Domain bảo vệ bất biến không thể bị bỏ qua.
- Repository query giới hạn dữ liệu theo tenant/owner khi phù hợp.
- Database constraint và quyền tối thiểu bảo vệ dữ liệu ở tầng lưu trữ.
- ViewModel chỉ trả các trường người dùng được phép xem.

Ẩn nút trong View không phải là phân quyền. Client có thể gọi endpoint trực tiếp. Mọi thao tác thay đổi hoặc đọc dữ liệu nhạy cảm phải được kiểm tra ở server, trong use case hoặc policy phù hợp.

Không đưa entity đầy đủ ra response nếu có trường nội bộ. Không nhận ownerId hoặc role từ form rồi tin đó là quyền của người dùng. Application service cần lấy danh tính từ security context đáng tin cậy và áp dụng quyền trên tài nguyên cụ thể.

## 16. Kiểm thử theo ranh giới kiến trúc

Mỗi lớp có thể được kiểm thử với phạm vi phù hợp:

| Phạm vi | Loại test | Điều cần xác minh |
|---|---|---|
| Domain | Unit test | Quy tắc, bất biến, chuyển trạng thái |
| Application | Unit/service test | Điều phối use case, gọi đúng port, transaction policy qua integration test |
| Persistence adapter | Integration test | Mapping, SQL/JPQL, constraint, transaction và database |
| Controller | MVC slice test | Binding, validation, status, redirect, ViewModel |
| Toàn luồng | MVC integration test | HTTP request đi qua service và lưu đúng dữ liệu |
| Security | Integration/security test | Quyền theo vai trò, owner và tenant |

Ví dụ:
- Domain test xác minh Task đã hủy không thể hoàn tất.
- Application test xác minh use case từ chối người không có quyền.
- Repository integration test xác minh truy vấn chỉ trả task của tenant tương ứng.
- Controller test xác minh form lỗi được render lại và giữ dữ liệu.
- MVC integration test xác minh POST tạo task trả response đúng và database có bản ghi sau commit.

Không nên mock tất cả dependency trong một test rồi gọi đó là kiểm thử tích hợp. Cũng không cần dùng database thật cho mọi quy tắc thuần domain; unit test sẽ nhanh và tập trung hơn.

## 17. Các cách tổ chức phổ biến và trade-off

### 17.1. MVC trong layered architecture truyền thống

Cấu trúc thường thấy:

~~~text
Presentation (Controller / View)
            |
            v
Application / Service
            |
            v
Domain / Business Model
            |
            v
Persistence / Repository
            |
            v
Database
~~~

Ưu điểm:
- Dễ hiểu với ứng dụng CRUD và web server truyền thống.
- Ranh giới trách nhiệm tương đối rõ.
- Dễ onboarding khi quy ước nhất quán.

Trade-off:
- Nếu mọi tầng chỉ chuyển tiếp lời gọi, có thể tạo nhiều lớp không có giá trị.
- Nếu application phụ thuộc trực tiếp vào framework persistence, khó thay đổi adapter.
- Nếu domain chỉ là cấu trúc dữ liệu, quy tắc có thể trôi vào service hoặc Controller.

### 17.2. MVC với Ports and Adapters

Trong cách tổ chức này, presentation và infrastructure là adapter; application/domain nằm bên trong và định nghĩa các port cần thiết.

~~~mermaid
flowchart LR
    WEB["Web MVC Adapter"] --> IN["Input Port / Use Case"]
    IN --> CORE["Application + Domain"]
    CORE --> OUT["Output Port"]
    OUT -. "implemented by" .-> DBAD["Database Adapter"]
    DBAD --> DB[("Database")]
~~~

Ưu điểm:
- Use case ít phụ thuộc framework và database.
- Có thể thay web adapter bằng API hoặc message adapter.
- Dễ mock port trong unit test và thay adapter trong integration test.

Trade-off:
- Nhiều interface, mapper và adapter hơn.
- Có thể quá nặng với ứng dụng nhỏ.
- Cần kỷ luật dependency và mapping để tránh boilerplate không cần thiết.

### 17.3. Tổ chức theo feature kết hợp layer

Ví dụ:

~~~text
tasks/
  presentation/
  application/
  domain/
  infrastructure/

orders/
  presentation/
  application/
  domain/
  infrastructure/
~~~

Cách này giữ các phần liên quan của một feature ở gần nhau. Có thể áp dụng khi hệ thống có nhiều module nghiệp vụ. Cần xác định module nào được phép gọi module nào và tránh phụ thuộc vòng.

## 18. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Coi MVC là toàn bộ kiến trúc ứng dụng | Thiếu ranh giới use case, domain và infrastructure | Đặt MVC trong presentation layer |
| Controller chứa nghiệp vụ và SQL | Khó kiểm thử, tái sử dụng và thay đổi giao diện | Chuyển điều phối sang application, quy tắc sang domain |
| View truy cập repository | Giao diện phụ thuộc persistence và khó kiểm soát truy vấn | Chuẩn bị ViewModel trước khi render |
| Đưa JPA Entity trực tiếp vào View/API | Lộ trường, lazy loading và coupling | Dùng Request/Response DTO hoặc ViewModel |
| Domain phụ thuộc Spring MVC | Nghiệp vụ bị gắn với HTTP/framework | Dùng kiểu và exception độc lập giao thức |
| Application service chỉ chuyển tiếp vô nghĩa | Tăng boilerplate mà không tạo ranh giới | Chỉ tạo abstraction khi có ý nghĩa use case/port |
| Infrastructure chứa quy tắc nghiệp vụ | Logic bị gắn với database hoặc SDK | Đưa bất biến về domain/application |
| Controller gọi thẳng repository để bỏ qua use case | Quyền, transaction và quy tắc không nhất quán | Gọi application service/query handler |
| Ẩn nút được xem là phân quyền | Endpoint vẫn có thể bị gọi trực tiếp | Kiểm tra quyền ở server |
| Tổ chức package chỉ theo loại file | Feature phụ thuộc chéo và khó thay đổi | Cân nhắc tổ chức theo feature/module và layer |

## 19. Quy trình thiết kế một chức năng MVC phân lớp

Khi xây dựng chức năng mới, có thể tiến hành theo trình tự:

1. Xác định hành động người dùng và use case nghiệp vụ.
2. Xác định request contract và response/ViewModel.
3. Thiết kế Controller chỉ xử lý giao tiếp, binding và điều hướng.
4. Định nghĩa application service/use case để điều phối.
5. Đặt quy tắc và bất biến vào domain model hoặc domain policy.
6. Xác định port cần cho lưu trữ hoặc dịch vụ ngoài.
7. Viết infrastructure adapter triển khai port.
8. Đặt transaction quanh use case cần tính nguyên tử.
9. Áp dụng validation, authorization và error mapping ở đúng ranh giới.
10. Kiểm thử domain, application, persistence và HTTP flow theo rủi ro.
11. Kiểm tra chiều phụ thuộc và bảo đảm không có vòng phụ thuộc giữa module.

Không nhất thiết phải tạo mọi lớp ngay từ đầu. Với chức năng nhỏ, một service và repository rõ ràng có thể đủ. Khi nghiệp vụ phức tạp hoặc có nhiều adapter, tách port, domain service và persistence mapper sẽ có giá trị hơn.

## 20. Những điểm cần ghi nhớ

MVC tổ chức trách nhiệm trình bày và tương tác; kiến trúc phân lớp tổ chức toàn bộ ứng dụng theo trách nhiệm. Trong ứng dụng web MVC, Controller và View thường thuộc presentation layer. Application service điều phối use case, Domain Model bảo vệ quy tắc, còn infrastructure cung cấp persistence và tích hợp kỹ thuật.

Model của MVC không đồng nghĩa với JPA Entity hay toàn bộ Domain Model. Trong Spring MVC, `org.springframework.ui.Model` chỉ là vùng chứa dữ liệu cho View. Hãy dùng Request DTO, Command, Result DTO và ViewModel để tách hợp đồng giao tiếp khỏi nghiệp vụ và lưu trữ.

Giữ dependency hướng vào các quy tắc cốt lõi; Controller không tự viết SQL, View không truy cập repository, domain không phụ thuộc HTTP và application service không trả kiểu response của framework. Đặt transaction quanh use case, kiểm tra quyền ở server và kiểm thử mỗi ranh giới bằng loại test phù hợp.

Khi kết hợp đúng hai cách tổ chức, MVC đảm nhiệm việc tiếp nhận và trình bày tương tác, còn kiến trúc phân lớp giữ cho nghiệp vụ và dữ liệu độc lập với chi tiết giao diện. Ứng dụng nhờ đó có thể thay template, thêm API hoặc thay adapter lưu trữ mà không phải viết lại các quy tắc nghiệp vụ cốt lõi.
