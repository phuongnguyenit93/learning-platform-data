# Giữ command mỏng và chuyển nghiệp vụ về service

Spring Shell cung cấp lớp giao tiếp dòng lệnh cho ứng dụng Spring. Một command nhận dữ liệu người dùng, chuyển dữ liệu đó tới chức năng ứng dụng và trình bày kết quả. Khi command đồng thời chứa quy tắc nghiệp vụ, truy vấn repository, điều khiển transaction và định dạng terminal, lớp giao tiếp sẽ khó kiểm thử và khó tái sử dụng.

Cách tổ chức phù hợp là giữ command mỏng và đặt nghiệp vụ trong service. Command chịu trách nhiệm hiểu cú pháp CLI, gọi đúng use case và chuyển kết quả thành thông tin dễ đọc. Service chịu trách nhiệm thực hiện use case, áp dụng quy tắc nghiệp vụ và phối hợp các thành phần dữ liệu hoặc hệ thống bên ngoài.

Bài học sử dụng Spring Shell 3.x với mô hình annotation legacy **@ShellComponent** và **@ShellMethod**. Các nguyên tắc phân lớp vẫn áp dụng khi đăng ký command bằng **CommandRegistration**.

## 1. Vì sao command nên mỏng?

Giả sử ứng dụng có command tạo dự án:

~~~text
project create --name inventory-api --owner platform
~~~

Command cần nhận hai option, gọi chức năng tạo dự án và hiển thị kết quả. Nếu viết toàn bộ công việc trong method command, code có thể nhanh chóng trở thành:

~~~java
@ShellComponent
public class ProjectCommands {

    @Autowired
    private ProjectRepository projectRepository;

    @ShellMethod("Create a project.")
    public String create(String name, String owner) {
        if (name == null || name.isBlank()) {
            return "Project name is required";
        }

        if (projectRepository.existsByName(name)) {
            return "Project already exists";
        }

        Project project = new Project();
        project.setName(name.trim());
        project.setOwner(owner);
        project.setStatus("ACTIVE");

        projectRepository.save(project);

        return "Created project " + project.getName();
    }
}
~~~

Ví dụ này có thể chạy, nhưng command đang làm nhiều việc:

- Nhận và kiểm tra dữ liệu CLI.
- Áp dụng quy tắc tên dự án.
- Kiểm tra tính duy nhất.
- Tạo entity và gán trạng thái nghiệp vụ.
- Gọi repository.
- Quyết định nội dung phản hồi.

Khi cần tạo dự án từ REST API, scheduler hoặc message consumer, các quy tắc này không thể dùng lại trực tiếp nếu chúng nằm trong command. Khi viết test, muốn kiểm tra quy tắc nghiệp vụ cũng phải khởi tạo hoặc mô phỏng lớp giao tiếp shell.

Tách service giúp mỗi lớp có một trách nhiệm rõ ràng. Command không cần biết dữ liệu được lưu ở đâu; service không cần biết người dùng đã nhập option theo cú pháp nào.

## 2. Phân chia trách nhiệm giữa command và service

| Thành phần | Trách nhiệm chính | Ví dụ |
|---|---|---|
| Spring Shell command | Nhận input, chuyển kiểu, gọi use case, trình bày output | project create --name inventory-api |
| Application service | Điều phối use case và transaction | ProjectService.createProject(...) |
| Domain model | Giữ trạng thái và quy tắc cốt lõi của domain | Project.rename(...) |
| Repository / gateway | Đọc ghi dữ liệu hoặc gọi hệ thống ngoài | ProjectRepository.save(...) |
| DTO / view model | Mang dữ liệu cần thiết qua ranh giới lớp | ProjectSummary |

Có thể hình dung luồng gọi như sau:

~~~mermaid
flowchart TD
    A["Người dùng nhập command"] --> B["ProjectCommands"]
    B --> C["Parse option và kiểm tra cú pháp"]
    C --> D["ProjectService"]
    D --> E["Áp dụng quy tắc nghiệp vụ"]
    E --> F["ProjectRepository"]
    F --> G["Database"]
    G --> H["ProjectSummary"]
    H --> B
    B --> I["Định dạng output cho terminal"]
    I --> J["Người dùng xem kết quả"]
~~~

Command là adapter của giao diện CLI. Service là điểm vào của use case trong ứng dụng. Repository và các gateway là chi tiết hạ tầng được service sử dụng thông qua dependency injection.

## 3. Command nên làm gì?

Trong Spring Shell 3.x, **@ShellComponent** đánh dấu bean có thể chứa command method. **@ShellMethod** đánh dấu method được gọi từ shell. Hai annotation này thuộc mô hình annotation legacy.

Một command thường làm các việc sau:

1. Khai báo tên command, mô tả và alias.
2. Khai báo argument hoặc option cần nhận.
3. Nhận giá trị đã được Spring Shell parse và chuyển đổi.
4. Gọi service tương ứng.
5. Chuyển kết quả thành chuỗi, bảng hoặc output phù hợp.
6. Chuyển exception nghiệp vụ thành thông báo CLI nếu cần.

Ví dụ:

~~~java
@ShellComponent
public class ProjectCommands {

    private final ProjectService projectService;

    public ProjectCommands(ProjectService projectService) {
        this.projectService = projectService;
    }

    @ShellMethod(
            value = "Create a project.",
            key = "project create")
    public String create(
            @ShellOption("--name") String name,
            @ShellOption("--owner") String owner) {

        ProjectSummary project =
                projectService.createProject(
                        new CreateProjectRequest(name, owner));

        return "Created project %d: %s"
                .formatted(project.id(), project.name());
    }
}
~~~

Method command ngắn và thể hiện được luồng chính: nhận hai option, gọi service, trình bày kết quả. Quy tắc tên dự án, trạng thái ban đầu và cách lưu dữ liệu nằm ở service hoặc domain.

### 3.1. Những việc không nên đặt trong command

Hạn chế đặt những phần sau trong command method:

- Truy vấn repository trực tiếp.
- Áp dụng nhiều bước nghiệp vụ thành một quy trình.
- Tính toán quy tắc giá, quyền hạn, trạng thái hoặc điều kiện chuyển đổi domain.
- Mở và quản lý transaction cho use case.
- Gọi trực tiếp nhiều hệ thống ngoài.
- Tạo entity và thay đổi trạng thái nghiệp vụ.
- Chứa vòng lặp xử lý dữ liệu lớn hoặc logic retry.
- Tự quản lý kết nối, file hoặc client hạ tầng.

Command vẫn có thể có logic trình bày như căn cột, chọn thông báo khi danh sách rỗng hoặc chuyển một DTO thành bảng. Đây là logic của giao diện CLI, không phải quy tắc nghiệp vụ.

## 4. Service chịu trách nhiệm gì?

Service biểu diễn một hành động có ý nghĩa đối với ứng dụng. Ví dụ:

- Tạo dự án.
- Đổi chủ sở hữu dự án.
- Tìm dự án theo ID.
- Đóng dự án.
- Phân công tác vụ.
- Tổng hợp trạng thái triển khai.

Một service có thể phối hợp nhiều repository hoặc gateway, kiểm tra quy tắc, điều khiển transaction và trả kết quả cho caller.

Ví dụ service tạo dự án:

~~~java
public record CreateProjectRequest(String name, String owner) {
}
~~~

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProjectService {

    private final ProjectRepository projectRepository;

    public ProjectService(ProjectRepository projectRepository) {
        this.projectRepository = projectRepository;
    }

    @Transactional
    public ProjectSummary createProject(CreateProjectRequest request) {
        String normalizedName = normalizeName(request.name());

        if (projectRepository.existsByName(normalizedName)) {
            throw new ProjectAlreadyExistsException(normalizedName);
        }

        Project project = Project.create(normalizedName, request.owner());

        Project saved = projectRepository.save(project);

        return new ProjectSummary(
                saved.getId(),
                saved.getName(),
                saved.getOwner(),
                saved.getStatus());
    }

    private String normalizeName(String name) {
        if (name == null || name.isBlank()) {
            throw new InvalidProjectNameException(
                    "Project name is required");
        }

        return name.trim();
    }
}
~~~

Service không nhận **Terminal**, **ShellContext**, **CompletionContext** hoặc các kiểu riêng của Spring Shell. Vì vậy, một thành phần khác có thể gọi **createProject()** mà không cần tạo phiên shell.

### 4.1. Dùng @Service để đăng ký bean

**@Service** là stereotype annotation của Spring, dùng để đánh dấu lớp thuộc tầng service. Nó được nhận diện trong quá trình component scanning như các stereotype khác.

Khi lớp ứng dụng được đặt trong package gốc phù hợp với **@SpringBootApplication**, Spring Boot có thể quét các package con và đăng ký bean **@Service**, **@Repository**, **@Component** và **@ShellComponent**.

Không cần tạo **new ProjectService(...)** trong command. Để Spring quản lý vòng đời bean và inject dependency qua constructor.

### 4.2. Có cần tạo interface cho mọi service không?

Không bắt buộc. Nếu chỉ có một triển khai và không có nhu cầu thay thế abstraction, có thể inject trực tiếp lớp **ProjectService**.

Tạo interface khi nó mang lại giá trị cụ thể, chẳng hạn:

- Có nhiều implementation theo môi trường.
- Module khác cần phụ thuộc vào hợp đồng ổn định.
- Muốn cô lập adapter hạ tầng qua abstraction.
- Có ranh giới module cần kiểm soát dependency.

Không nên tạo interface chỉ vì mọi lớp service đều phải có một interface. Abstraction không cần thiết làm code tăng thêm nhưng không cải thiện khả năng thay đổi.

## 5. Constructor injection giúp command và service rõ dependency

Spring Boot khuyến nghị constructor injection cho dependency bắt buộc. Với một constructor duy nhất, thường không cần gắn **@Autowired**.

Ví dụ:

~~~java
@Service
public class ProjectService {

    private final ProjectRepository projectRepository;
    private final AuditService auditService;

    public ProjectService(
            ProjectRepository projectRepository,
            AuditService auditService) {
        this.projectRepository = projectRepository;
        this.auditService = auditService;
    }
}
~~~

Lợi ích:

- Dependency được khai báo rõ ràng.
- Field có thể là **final**.
- Object không tồn tại trong trạng thái thiếu dependency bắt buộc.
- Unit test có thể tạo service với mock hoặc fake.
- Không cần reflection hoặc Spring context chỉ để gán field.

Command cũng sử dụng cùng cách:

~~~java
@ShellComponent
public class ProjectCommands {

    private final ProjectService projectService;

    public ProjectCommands(ProjectService projectService) {
        this.projectService = projectService;
    }
}
~~~

Tránh field injection trong các lớp nghiệp vụ nếu không có lý do đặc biệt. Field injection khiến dependency bị ẩn khỏi constructor và làm unit test cần thêm bước thiết lập object.

## 6. Giữ kiểu dữ liệu của Spring Shell ở ranh giới CLI

Spring Shell chịu trách nhiệm parse option và chuyển giá trị thành kiểu Java. Service nên nhận kiểu dữ liệu có ý nghĩa với use case.

Ví dụ command nhận ID:

~~~java
@ShellMethod("Show a project.")
public String show(@ShellOption("--id") Long id) {
    ProjectSummary project = projectService.getProject(id);
    return "%d %s".formatted(project.id(), project.name());
}
~~~

Service nhận **Long** và xử lý việc tìm dự án:

~~~java
@Service
public class ProjectService {

    private final ProjectRepository projectRepository;

    public ProjectService(ProjectRepository projectRepository) {
        this.projectRepository = projectRepository;
    }

    @Transactional(readOnly = true)
    public ProjectSummary getProject(Long id) {
        Project project = projectRepository.findById(id)
                .orElseThrow(() -> new ProjectNotFoundException(id));

        return ProjectSummary.from(project);
    }
}
~~~

Service không cần nhận toàn bộ chuỗi command hoặc token parser. Nếu một use case cần nhiều giá trị, tạo request object có tên trường rõ ràng.

Với request object đã khai báo ở phần trước, command chuyển các option thành request:

~~~java
@ShellMethod("Create a project.")
public String create(
        @ShellOption("--name") String name,
        @ShellOption("--owner") String owner) {

    ProjectSummary result = projectService.createProject(
            new CreateProjectRequest(name, owner));

    return "Created project " + result.id();
}
~~~

Cách này hữu ích khi một use case nhận nhiều trường hoặc được gọi từ nhiều adapter. Với một hành động rất đơn giản, các tham số riêng lẻ vẫn có thể dễ đọc hơn.

## 7. Phân biệt validation cú pháp và validation nghiệp vụ

Validation có thể diễn ra ở nhiều tầng. Chọn đúng tầng giúp thông báo lỗi có ý nghĩa và không lặp quy tắc.

| Loại kiểm tra | Nơi phù hợp | Ví dụ |
|---|---|---|
| Cú pháp CLI | Spring Shell parser | Option --id có thể chuyển thành Long |
| Bắt buộc theo giao diện | Command argument/option | Command yêu cầu --name |
| Ràng buộc use case | Service hoặc request validator | Tên dự án không được để trống |
| Quy tắc domain | Domain model | Không thể đóng dự án đã đóng |
| Ràng buộc lưu trữ | Database và repository | Tên dự án duy nhất |

Ví dụ người dùng nhập:

~~~text
project show --id abc
~~~

Nếu option **id** có kiểu **Long**, Spring Shell không thể chuyển **abc** thành số. Đây là lỗi parse/conversion; method command có thể chưa được gọi.

Ngược lại:

~~~text
project create --name "   " --owner platform
~~~

Chuỗi vẫn có thể được parse thành **String**. Service phải kiểm tra tên sau khi chuẩn hóa và từ chối dữ liệu không hợp lệ theo quy tắc ứng dụng.

Không nên đặt quy tắc nghiệp vụ chỉ trong annotation của command. Nếu REST API hoặc batch job gọi cùng use case, chúng cũng phải tuân thủ quy tắc đó.

## 8. Transaction nên nằm ở ranh giới use case

Transaction thường thuộc service method điều phối một use case. Ví dụ, tạo dự án có thể cần lưu dự án và ghi lịch sử hoạt động trong cùng một transaction:

~~~java
@Service
public class ProjectService {

    private final ProjectRepository projectRepository;
    private final AuditRepository auditRepository;

    public ProjectService(
            ProjectRepository projectRepository,
            AuditRepository auditRepository) {
        this.projectRepository = projectRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public ProjectSummary createProject(CreateProjectRequest request) {
        Project project = Project.create(
                normalizeName(request.name()),
                request.owner());

        Project saved = projectRepository.save(project);

        auditRepository.save(
                AuditEntry.projectCreated(saved.getId()));

        return ProjectSummary.from(saved);
    }
}
~~~

Nếu transaction được đặt trong command, logic giao dịch sẽ gắn với một adapter CLI cụ thể. Một adapter khác có thể vô tình gọi service mà không có cùng ranh giới transaction.

Dùng **@Transactional(readOnly = true)** cho truy vấn chỉ đọc khi phù hợp với cách truy cập dữ liệu. Không đánh dấu read-only một cách máy móc nếu use case còn cập nhật trạng thái hoặc cần ghi audit.

Với lời gọi tới hệ thống ngoài như email hoặc message broker, transaction cơ sở dữ liệu không tự đảm bảo side effect ngoài database được rollback. Hãy chọn cơ chế phù hợp như outbox, retry hoặc xử lý idempotent nếu use case cần tính nhất quán đó.

## 9. Trả DTO hoặc kết quả ứng dụng thay vì để command phụ thuộc entity

Service có thể trả domain entity, nhưng với ranh giới giữa application và CLI, một DTO hoặc projection thường giúp command chỉ nhận đúng dữ liệu cần hiển thị.

Ví dụ:

~~~java
public record ProjectSummary(
        Long id,
        String name,
        String owner,
        ProjectStatus status) {

    public static ProjectSummary from(Project project) {
        return new ProjectSummary(
                project.getId(),
                project.getName(),
                project.getOwner(),
                project.getStatus());
    }
}
~~~

Command chỉ sử dụng các trường cần trình bày:

~~~java
@ShellMethod("Show a project.")
public String show(@ShellOption("--id") Long id) {
    ProjectSummary project = projectService.getProject(id);

    return """
            ID: %d
            Name: %s
            Owner: %s
            Status: %s
            """.formatted(
            project.id(),
            project.name(),
            project.owner(),
            project.status());
}
~~~

Lợi ích:

- Command không cần biết cấu trúc persistence entity.
- Không vô tình kích hoạt lazy loading khi format output.
- Có thể thay đổi schema database mà không buộc CLI thay đổi theo.
- Service kiểm soát dữ liệu nào được công khai qua use case.

DTO không nhất thiết phải tạo cho mọi method. Với kết quả đơn giản như **boolean**, **long** hoặc **String**, dùng kiểu đó trực tiếp nếu nó diễn đạt đúng kết quả.

## 10. Chuyển exception nghiệp vụ thành thông báo CLI

Service nên ném exception có ý nghĩa khi use case không thể hoàn thành theo quy tắc ứng dụng.

Ví dụ:

~~~java
public class ProjectNotFoundException extends RuntimeException {

    private final Long projectId;

    public ProjectNotFoundException(Long projectId) {
        super("Project not found: " + projectId);
        this.projectId = projectId;
    }

    public Long getProjectId() {
        return projectId;
    }
}
~~~

Service phát sinh exception:

~~~java
@Transactional(readOnly = true)
public ProjectSummary getProject(Long id) {
    Project project = projectRepository.findById(id)
            .orElseThrow(() -> new ProjectNotFoundException(id));

    return ProjectSummary.from(project);
}
~~~

Lớp command có thể dùng **@ExceptionResolver** để chuyển exception thành thông báo thân thiện:

~~~java
import org.springframework.shell.command.annotation.ExceptionResolver;

@ExceptionResolver
public String handleProjectNotFound(
        ProjectNotFoundException exception) {

    return "Cannot find project with ID "
            + exception.getProjectId();
}
~~~

Quy tắc tìm dự án vẫn nằm trong service. Resolver chỉ quyết định cách biểu diễn lỗi trong giao diện shell.

Nếu cùng service được gọi từ REST API, adapter REST có thể ánh xạ exception sang HTTP status. Không nên đưa **CommandHandlingResult**, **ShellMessageBuilder** hoặc **Terminal** vào service chỉ để điều khiển output của một giao diện cụ thể.

Không bắt **Exception** rồi trả chuỗi chung trong mọi command. Cách đó dễ che mất lỗi lập trình, mất cause và khiến caller không thể phân biệt lỗi nghiệp vụ với lỗi hệ thống.

## 11. Định dạng output thuộc lớp command

Service trả dữ liệu có cấu trúc. Command quyết định hiển thị dữ liệu đó theo cách phù hợp với terminal.

Ví dụ service trả danh sách:

~~~java
@Transactional(readOnly = true)
public List<ProjectSummary> listProjects() {
    return projectRepository.findAll().stream()
            .map(ProjectSummary::from)
            .toList();
}
~~~

Command quyết định nội dung khi danh sách rỗng và cách nối các dòng:

~~~java
@ShellMethod("List projects.")
public String list() {
    List<ProjectSummary> projects = projectService.listProjects();

    if (projects.isEmpty()) {
        return "No projects found";
    }

    return projects.stream()
            .map(project -> "%d  %s  %s".formatted(
                    project.id(),
                    project.name(),
                    project.status()))
            .collect(Collectors.joining("\n"));
}
~~~

Nếu muốn dùng **TableBuilder**, command có thể chuyển danh sách DTO thành **TableModel** và trả bảng. Service không cần phụ thuộc vào **Table**, **TableBuilder** hoặc border style.

Quy tắc trình bày như căn lề, màu, bảng, spinner, prompt và câu thông báo thuộc giao diện CLI. Dữ liệu và quyết định nghiệp vụ vẫn do service cung cấp.

## 12. Không đưa Spring Shell API vào service

Một service nên hoạt động được khi không có terminal. Vì vậy, tránh những dependency sau trong lớp service:

- **Terminal** hoặc **TerminalUI**.
- **ShellContext**.
- **ComponentFlow**.
- **StringInputContext** hoặc selector context.
- **CompletionContext**.
- **CommandContext** hoặc parser token.
- **ShellMessageBuilder**.

Ví dụ không nên dùng:

~~~java
@Service
public class ProjectService {

    private final Terminal terminal;

    public ProjectService(Terminal terminal) {
        this.terminal = terminal;
    }

    public Project createProject() {
        // Hỏi tên dự án trực tiếp qua terminal.
        // ...
    }
}
~~~

Service này chỉ hoạt động khi có terminal tương tác và khó dùng trong test hoặc batch job.

Nên để command lấy input rồi gọi service:

~~~java
@ShellMethod("Create a project.")
public String create(
        @ShellOption("--name") String name,
        @ShellOption("--owner") String owner) {
    ProjectSummary project = projectService.createProject(
            new CreateProjectRequest(name, owner));
    return "Created " + project.name();
}
~~~

Nếu use case cần thêm thông tin từ người dùng, command có thể dùng **ComponentFlow** hoặc component nhập liệu để thu thập. Sau đó, chuyển các giá trị thành request object và gọi service. Service không cần biết dữ liệu đến từ prompt, option, file hay API.

## 13. Một service có thể phục vụ nhiều command

Không nên tạo một service riêng cho mỗi command nếu các command cùng thao tác trên một use case hoặc cùng một nhóm nghiệp vụ.

Ví dụ:

| Command | Service method |
|---|---|
| project create | createProject(...) |
| project show | getProject(...) |
| project list | listProjects(...) |
| project close | closeProject(...) |
| project rename | renameProject(...) |

Một **ProjectService** có thể cung cấp các use case liên quan. Khi service quá lớn, tách theo năng lực hoặc nhóm use case có ý nghĩa, chẳng hạn **ProjectQueryService** và **ProjectCommandService**.

Không nên tách service chỉ theo tên method hoặc số lượng command. Hãy xem các hành vi có chung quy tắc, transaction và dependency hay không.

## 14. Tổ chức package theo vai trò

Một cấu trúc đơn giản cho ứng dụng Spring Shell:

~~~text
com.example.projectcli
├── ProjectCliApplication.java
├── shell
│   ├── ProjectCommands.java
│   └── ProjectExceptionResolver.java
├── application
│   ├── ProjectService.java
│   ├── CreateProjectRequest.java
│   └── ProjectSummary.java
├── domain
│   ├── Project.java
│   ├── ProjectStatus.java
│   └── ProjectAlreadyExistsException.java
└── infrastructure
    └── persistence
        └── ProjectRepository.java
~~~

Ý nghĩa:

- **shell**: command, option, prompt, formatter và thông báo lỗi của CLI.
- **application**: điều phối use case và transaction.
- **domain**: quy tắc và trạng thái nghiệp vụ.
- **infrastructure**: database, repository implementation và tích hợp bên ngoài.

Với ứng dụng nhỏ, không cần tạo đủ mọi package ngay từ đầu. Có thể bắt đầu bằng **shell**, **service** và **repository**, sau đó tách domain hoặc application khi logic tăng lên.

Điều quan trọng là chiều phụ thuộc: lớp shell gọi service; service sử dụng abstraction cần thiết cho nghiệp vụ; service không phụ thuộc vào lớp shell.

## 15. Kiểm thử service độc lập với Spring Shell

Vì service không phụ thuộc terminal hoặc parser, có thể kiểm thử trực tiếp bằng JUnit và Mockito.

Ví dụ:

~~~java
@ExtendWith(MockitoExtension.class)
class ProjectServiceTests {

    @Mock
    ProjectRepository projectRepository;

    @InjectMocks
    ProjectService projectService;

    @Test
    void createsProjectAndReturnsSummary() {
        when(projectRepository.existsByName("inventory-api"))
                .thenReturn(false);

        when(projectRepository.save(any(Project.class)))
                .thenAnswer(invocation -> {
                    Project project = invocation.getArgument(0);
                    project.assignId(101L);
                    return project;
                });

        ProjectSummary result = projectService.createProject(
                new CreateProjectRequest("inventory-api", "platform"));

        assertThat(result.id()).isEqualTo(101L);
        assertThat(result.name()).isEqualTo("inventory-api");
        verify(projectRepository).save(any(Project.class));
    }

    @Test
    void rejectsDuplicateProjectName() {
        when(projectRepository.existsByName("inventory-api"))
                .thenReturn(true);

        assertThatThrownBy(() ->
                projectService.createProject(
                        new CreateProjectRequest("inventory-api", "platform")))
                .isInstanceOf(ProjectAlreadyExistsException.class);

        verify(projectRepository, never()).save(any());
    }
}
~~~

Test này tập trung vào quy tắc use case: tạo thành công và từ chối tên đã tồn tại. Không cần khởi tạo Spring Shell hoặc terminal.

Khi test service, nên xác minh hành vi quan trọng như:

- Quy tắc chuẩn hóa input.
- Điều kiện từ chối nghiệp vụ.
- Repository hoặc gateway được gọi đúng.
- Kết quả trả về chứa dữ liệu cần thiết.
- Exception có kiểu phù hợp.

Không nên kiểm tra chi tiết nội bộ không ảnh hưởng đến hành vi, chẳng hạn thứ tự gọi helper method riêng tư.

## 16. Kiểm thử command như một adapter CLI

Command có thể được kiểm thử riêng bằng Spring Shell test support. Mục tiêu là xác minh option được bind, service được gọi và kết quả được hiển thị.

Ví dụ định hướng:

~~~java
import static org.awaitility.Awaitility.await;
import static org.mockito.Mockito.when;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.autoconfigure.ShellTest;
import org.springframework.shell.test.ShellTestClient;

@ShellTest
class ProjectCommandsTests {

    @Autowired
    ShellTestClient client;

    @MockBean
    ProjectService projectService;

    @Test
    void createCommandCallsServiceAndDisplaysResult() {
        when(projectService.createProject(
                new CreateProjectRequest("inventory-api", "platform")))
                .thenReturn(new ProjectSummary(
                        101L,
                        "inventory-api",
                        "platform",
                        ProjectStatus.ACTIVE));

        var session = client.nonInterative(
                "project", "create",
                "--name", "inventory-api",
                "--owner", "platform")
                .run();

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("Created project 101"));
    }
}
~~~

Trong Spring Shell 3.1.6, tên method trên API là `nonInterative` (có lỗi chính tả trong tên method). Hãy dùng đúng tên được cung cấp bởi phiên bản đang cài. Test chờ output bất đồng bộ bằng Awaitility để tránh giả định màn hình đã cập nhật ngay sau `run()`. Mục tiêu kiểm thử vẫn là tách hai câu hỏi:

- Service có áp dụng đúng quy tắc nghiệp vụ không?
- Command có nhận input và trình bày kết quả đúng không?

Nếu command chỉ là adapter mỏng, test command không cần lặp lại toàn bộ các test nghiệp vụ của service.

## 17. Kiểm thử tích hợp cho transaction và persistence

Unit test với mock không chứng minh repository và transaction hoạt động đúng trong database thật. Nên có một số integration test tập trung vào ranh giới persistence:

- Tạo dự án và đọc lại được.
- Tên trùng bị từ chối theo ràng buộc thực tế.
- Nếu ghi audit thất bại trong cùng transaction, dữ liệu chính được rollback theo thiết kế.
- Truy vấn danh sách trả đúng projection.
- Các truy vấn đọc không làm thay đổi trạng thái dữ liệu.

Có thể dùng **@DataJpaTest** cho repository và **@SpringBootTest** cho use case tích hợp. Chỉ dùng test đầy đủ context khi cần xác minh wiring, transaction hoặc tích hợp nhiều thành phần.

Không cần khởi chạy terminal thật cho mọi test persistence. Terminal là chi tiết của adapter CLI.

## 18. Xử lý lỗi và mã thoát ở ranh giới phù hợp

Một lỗi nghiệp vụ như **ProjectNotFoundException** có thể được command resolver chuyển thành thông báo dễ hiểu. Trong non-interactive mode, ứng dụng cũng cần trả mã thoát khác **0** nếu use case thất bại để script hoặc CI nhận biết.

Service không nên tự gọi **System.exit()**. Service chỉ báo kết quả hoặc ném exception. Lớp shell và cấu hình exit code chịu trách nhiệm chuyển lỗi thành phản hồi CLI.

Ví dụ quy ước:

| Tình huống | Service | Command / shell |
|---|---|---|
| Tạo thành công | Trả ProjectSummary | In ID và tên |
| Không tìm thấy | Ném ProjectNotFoundException | Hiển thị thông báo và mã lỗi |
| Tên trùng | Ném ProjectAlreadyExistsException | Báo tên đã tồn tại |
| Option sai kiểu | Chưa gọi service | Parser báo lỗi |
| Lỗi database | Ném hoặc truyền tiếp exception | Hiển thị thông báo tổng quát, ghi log chi tiết |

Không biến mọi exception thành thông báo thành công. Nếu một command lỗi nhưng resolver trả mã thoát **0**, pipeline có thể hiểu nhầm tác vụ đã hoàn thành.

## 19. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách tổ chức tốt hơn |
|---|---|---|
| Inject repository vào @ShellComponent | Command gắn chặt với persistence | Inject service |
| Viết toàn bộ quy tắc trong @ShellMethod | Khó tái sử dụng và test | Đưa use case vào service |
| Service gọi System.out.println() | Service phụ thuộc giao diện console | Trả dữ liệu để command trình bày |
| Service nhận Terminal hoặc ShellContext | Không thể chạy độc lập với CLI | Nhận request object hoặc tham số Java |
| Command tự mở transaction cho nghiệp vụ | Transaction gắn với adapter | Đặt transaction ở service |
| Service trả chuỗi đã định dạng terminal | API service bị khóa vào một giao diện | Trả DTO hoặc kết quả có cấu trúc |
| Lặp lại validation ở nhiều command | Quy tắc không nhất quán | Đặt quy tắc use case trong service/domain |
| Bắt mọi exception trong command | Che lỗi và mất cause | Bắt lỗi có chủ đích hoặc dùng resolver |
| Tạo một service cho mỗi command | Phân mảnh không cần thiết | Nhóm use case theo năng lực nghiệp vụ |
| Test tất cả bằng @SpringBootTest | Test chậm và khó xác định lỗi | Unit test service, test shell và integration test riêng |

## 20. Bài thực hành: tách command project thành service

Bắt đầu với command **project create** đang truy cập trực tiếp **ProjectRepository**.

Yêu cầu:

1. Tạo **ProjectService** được đánh dấu **@Service**.
2. Chuyển kiểm tra tên trống và tên trùng vào service.
3. Tạo **CreateProjectRequest** nếu use case nhận nhiều trường.
4. Tạo **ProjectSummary** làm kết quả trả về.
5. Dùng constructor injection trong cả command và service.
6. Đặt **@Transactional** trên service method ghi dữ liệu.
7. Để command chỉ nhận option, gọi service và định dạng output.
8. Tạo exception nghiệp vụ riêng cho tên trùng và không tìm thấy.
9. Viết unit test cho service bằng mock repository.
10. Viết test shell để xác minh option và output.
11. Viết integration test cho repository hoặc transaction nếu use case cần.
12. Chạy command từ REPL và non-interactive mode để xác minh cùng use case hoạt động ở cả hai cách gọi.

Luồng mong đợi:

~~~text
shell:> project create --name inventory-api --owner platform
Created project 101: inventory-api

shell:> project list
ID   Name           Owner      Status
101  inventory-api  platform   ACTIVE

shell:> project create --name inventory-api --owner platform
Project already exists: inventory-api
~~~

Sau khi hoàn thành, thử gọi **ProjectService** từ một test hoặc một adapter khác. Nếu service vẫn hoạt động mà không cần tạo **Terminal** hoặc chạy Spring Shell, ranh giới trách nhiệm đã được tách hợp lý.

## 21. Checklist trước khi hoàn thiện

- [ ] @ShellComponent chỉ chứa các command method và logic trình bày liên quan.
- [ ] @ShellMethod khai báo rõ tên, mô tả và option.
- [ ] Command không truy cập repository trực tiếp.
- [ ] Service được đăng ký bằng @Service hoặc stereotype phù hợp.
- [ ] Dependency bắt buộc được inject qua constructor.
- [ ] Service không phụ thuộc Terminal, ShellContext hoặc API riêng của Spring Shell.
- [ ] Quy tắc nghiệp vụ được kiểm tra trong service/domain.
- [ ] Transaction nằm ở ranh giới use case phù hợp.
- [ ] Service trả DTO hoặc kiểu kết quả có cấu trúc.
- [ ] Command định dạng chuỗi, bảng và thông báo cho terminal.
- [ ] Exception nghiệp vụ có kiểu rõ ràng và giữ nguyên cause khi cần.
- [ ] Exception resolver chỉ chuyển lỗi thành phản hồi CLI.
- [ ] Không dùng System.exit() trong service hoặc command method.
- [ ] Có unit test độc lập cho service.
- [ ] Có test cho command input/output.
- [ ] Có integration test cho persistence hoặc transaction quan trọng.

## 22. Kết luận

Một command Spring Shell nên là lớp điều phối mỏng giữa người dùng và ứng dụng. Nó nhận option, gọi service và trình bày kết quả. Service thực hiện use case, áp dụng quy tắc nghiệp vụ, phối hợp repository hoặc gateway và quản lý transaction.

Dùng **@ShellComponent** và **@ShellMethod** để khai báo command, **@Service** để đăng ký service, cùng constructor injection để thể hiện dependency. Giữ kiểu dữ liệu của Spring Shell ở ranh giới CLI và để service trả kết quả có cấu trúc giúp cùng một nghiệp vụ có thể được gọi từ shell, REST API, scheduler hoặc batch job.

Khi tách đúng trách nhiệm, test service không cần terminal; test command chỉ cần xác minh input và output. Ứng dụng nhờ đó dễ thay đổi, dễ kiểm thử và không bị khóa vào một cách tương tác duy nhất.

## Tài liệu tham khảo

- [Spring Shell 3.1 API: ShellComponent](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/standard/ShellComponent.html)
- [Spring Shell 3.1 API: ShellMethod](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/standard/ShellMethod.html)
- [Spring Shell 3.1 API: ShellOption](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/standard/ShellOption.html)
- [Spring Shell 3.1 API: ExceptionResolver](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/annotation/ExceptionResolver.html)
- [Spring Shell 3.1 API: ShellTestClient](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/test/ShellTestClient.html)
- [Spring Shell 3.1 API: ShellTest](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/test/autoconfigure/ShellTest.html)
- [Spring Shell 3.3 Reference: Legacy Annotation](https://docs.spring.io/spring-shell/reference/3.3/commands/registration/legacyannotation.html)
- [Spring Shell 3.1.6 Reference Documentation](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html)
- [Spring Shell 3.1.6 Reference: Testing](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html)
- [Spring Boot: Spring Beans and Dependency Injection](https://docs.spring.io/spring-boot/reference/using/spring-beans-and-dependency-injection.html)
- [Spring Framework: Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework: Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Shell 3.1 API: CommandExceptionResolver](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandExceptionResolver.html)
- [Spring Shell 3.1 API: CommandHandlingResult](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandHandlingResult.html)

