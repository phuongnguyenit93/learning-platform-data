# Bài tập tổng hợp từ đặc tả CLI đến công cụ có tài liệu và kiểm thử

Bài thực hành này đưa các phần của Spring Shell vào một sản phẩm nhỏ có thể chạy, lưu dữ liệu, hỗ trợ người dùng và được kiểm thử trước khi phát hành. Bạn sẽ xây dựng **Project CLI** để quản lý danh sách dự án: tạo dự án, xem chi tiết, liệt kê và lưu trữ dự án. Công cụ phải dùng được trong REPL, chạy một command từ terminal, thực thi script, trả output có cấu trúc, phân biệt lỗi bằng exit code và có hướng dẫn sử dụng.

Mục tiêu là hoàn thành một vòng phát triển có thể review:

1. Viết đặc tả CLI và tiêu chí chấp nhận.
2. Thiết kế domain, service và nơi lưu dữ liệu.
3. Khai báo command, converter và validation.
4. Hoàn thiện interactive, non-interactive và script mode.
5. Quy định output, exception và exit code.
6. Viết unit test, shell test và process test.
7. Đóng gói executable JAR và thử trên môi trường sạch.
8. Viết README, ví dụ script và checklist phát hành.

Các ví dụ lấy Spring Shell 3.1.6, Spring Boot 3.1.6 và Java 17 làm mốc. Nếu dự án dùng version khác, hãy đối chiếu API và dependency tương ứng trước khi sao chép mã.

## 1. Bài toán và phạm vi sản phẩm

Một nhóm phát triển cần một công cụ dòng lệnh nhỏ để theo dõi các dự án nội bộ. Người dùng cần tạo dự án, tìm theo mã, xem danh sách và lưu trữ dự án đã kết thúc. Công cụ phải dùng được khi người vận hành mở REPL, khi CI gọi một command và khi một script chạy nhiều thao tác liên tiếp.

Project CLI quản lý các trường:

| Trường | Kiểu | Quy tắc |
|---|---|---|
| Code | Chuỗi có định dạng | Bắt buộc, dạng `OPS-1024` |
| Name | Chuỗi | Bắt buộc, tối đa 60 ký tự |
| Owner | Chuỗi | Bắt buộc, tối đa 40 ký tự |
| Priority | Số nguyên | Từ 1 đến 5 |
| Status | Enum | `ACTIVE` hoặc `ARCHIVED` |

Mã dự án là duy nhất. Tạo trùng mã phải báo lỗi. Lưu trữ dự án không xóa dữ liệu; command chuyển trạng thái sang `ARCHIVED`. Gọi archive lần nữa trên một dự án đã lưu trữ không làm thay đổi kết quả.

Để capstone có thể chạy qua nhiều tiến trình, dữ liệu được lưu trong một file JSON. Adapter file phù hợp với công cụ cá nhân hoặc một tiến trình sử dụng tại một thời điểm. Nếu nhiều người hoặc nhiều tiến trình cùng cập nhật dữ liệu, cần thay adapter bằng database có transaction và cơ chế concurrency phù hợp.

## 2. Viết đặc tả CLI trước khi viết code

Đặc tả phải mô tả cú pháp mà người dùng sẽ gõ, chứ không chỉ mô tả tên method Java.

### 2.1. Command contract

| Command | Mục đích | Input | Kết quả thành công |
|---|---|---|---|
| `project create` | Tạo dự án | `--code`, `--name`, `--owner`, `--priority` | Mã dự án và trạng thái |
| `project show` | Xem một dự án | `--code` | Một bản ghi dự án |
| `project list` | Liệt kê dự án | `--limit`, `--format` | Bảng hoặc JSON |
| `project archive` | Lưu trữ dự án | `--code` | Trạng thái `ARCHIVED` |

Ví dụ cách gọi:

~~~text
project create --code OPS-1024 --name "Inventory API" --owner platform --priority 3
project show --code OPS-1024
project list --limit 20 --format TABLE
project list --limit 20 --format JSON
project archive --code OPS-1024
~~~

Command key và option name là giao diện công khai. Khi refactor implementation, giữ các tên này nếu không có quyết định breaking change.

### 2.2. Quy tắc input

- `--code`, `--name`, `--owner` là bắt buộc khi tạo dự án.
- `--priority` mặc định là `3`, giới hạn từ `1` đến `5`.
- `--limit` mặc định là `20`, giới hạn từ `1` đến `100`.
- `--format` mặc định là `TABLE`, nhận `TABLE` hoặc `JSON`.
- Code được chuẩn hóa thành chữ hoa trước khi lưu.
- Tên và owner được trim khoảng trắng ở hai đầu.
- Mã không tồn tại phải được phân biệt với mã đã tồn tại.
- Input không hợp lệ không được ghi dữ liệu.

### 2.3. Quy tắc output và exit code

| Tình huống | Message | Exit code non-interactive |
|---|---|---:|
| Thành công | Kết quả command | 0 |
| Cú pháp hoặc conversion không hợp lệ | Thông báo input | 2 theo mặc định parser |
| Không tìm thấy dự án | `Project not found` | 3 |
| Mã dự án đã tồn tại | `Project already exists` | 4 |
| Không đọc/ghi được store | `Project store error` | 5 |
| Lỗi không dự kiến | Thông báo an toàn | 1 |

Exit code `3`, `4`, `5` là contract của bài thực hành. Spring Shell 3.1.x có mặc định mã `2` cho lỗi parse option và `1` cho lỗi chung; ta bổ sung mã cho lỗi domain bằng exception resolver.

Exit code chỉ có ý nghĩa với non-interactive process. Trong REPL, command lỗi hiển thị message nhưng người dùng vẫn có thể tiếp tục làm việc.

### 2.4. Tiêu chí chấp nhận

Bài chỉ hoàn thành khi:

- Có thể tạo dự án và đọc lại dự án sau khi khởi động process mới.
- Mã trùng không ghi đè dự án cũ.
- Code sai định dạng bị từ chối trước khi ghi dữ liệu.
- Name rỗng và priority ngoài giới hạn bị validation từ chối.
- List trả về đúng thứ tự ổn định và giới hạn số hàng.
- JSON output parse được bằng công cụ JSON.
- Archive chuyển trạng thái và có tính idempotent.
- Cả REPL, non-interactive và script mode đều chạy được.
- Lỗi domain trả đúng exit code trong process thật.
- Test bao phủ converter, service, repository, command và process.
- JAR chạy được từ thư mục làm việc khác nếu store path được cấu hình tuyệt đối.
- README có đủ hướng dẫn build, chạy, cấu hình, script và xử lý lỗi.

## 3. Thiết kế kiến trúc

Tách command adapter khỏi nghiệp vụ và nơi lưu dữ liệu:

~~~mermaid
flowchart TD
    U["Người dùng / Script / CI"] --> R["Spring Shell runners"]
    R --> P["Parser và argument binding"]
    P --> C["ProjectCommands"]
    C --> CV["Converter và Bean Validation"]
    CV --> S["ProjectService"]
    S --> D["Domain model và business rules"]
    S --> RP["ProjectRepository"]
    RP --> J["JsonProjectRepository"]
    J --> F["projects.json"]
    C --> EH["CommandExceptionResolver"]
    EH --> O["Message và exit code"]
    C --> OUT["Table / JSON output"]
~~~

Các lớp có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
|---|---|
| `ProjectCode` | Chuẩn hóa và kiểm tra định dạng code |
| `Project` | Biểu diễn trạng thái dự án |
| `ProjectRepository` | Hợp đồng đọc và lưu dự án |
| `JsonProjectRepository` | Lưu dữ liệu vào file JSON |
| `ProjectService` | Quy tắc tạo, tìm, liệt kê và archive |
| `StringToProjectCodeConverter` | Chuyển token thành `ProjectCode` |
| `ProjectCommands` | Nhận input và trình bày kết quả |
| `ProjectCommandExceptionResolver` | Đổi lỗi domain thành message và exit code |

Command không đọc/ghi file trực tiếp. Repository không biết terminal. Service không phụ thuộc Spring Shell. Cách phân chia này giúp test nghiệp vụ mà không phải khởi chạy terminal.

## 4. Tạo project và khai báo dependency

Có thể tạo project Gradle với Java 17 và Spring Boot 3.1.6. Ví dụ `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.1.6'
    id 'io.spring.dependency-management' version '1.1.3'
}

group = 'com.example'
version = '0.1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.shell:spring-shell-starter:3.1.6'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.shell:spring-shell-test:3.1.6'
    testImplementation 'org.springframework.shell:spring-shell-test-autoconfigure:3.1.6'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Shell starter cung cấp parser, runner, terminal và command infrastructure. Validation starter cung cấp Jakarta Bean Validation provider. Test dependencies cung cấp JUnit, Spring test và shell test support.

Cấu trúc source đề xuất:

~~~text
project-cli/
├── build.gradle
├── settings.gradle
├── README.md
├── scripts/
│   └── bootstrap.shell
└── src/
    ├── main/
    │   ├── java/com/example/projectcli/
    │   │   ├── ProjectCliApplication.java
    │   │   ├── command/
    │   │   │   ├── ProjectCommands.java
    │   │   │   └── ProjectCommandExceptionResolver.java
    │   │   ├── domain/
    │   │   │   ├── Project.java
    │   │   │   ├── ProjectCode.java
    │   │   │   └── ProjectStatus.java
    │   │   ├── service/
    │   │   │   ├── ProjectService.java
    │   │   │   ├── ProjectNotFoundException.java
    │   │   │   ├── ProjectAlreadyExistsException.java
    │   │   │   └── ProjectStoreException.java
    │   │   └── store/
    │   │       ├── ProjectRepository.java
    │   │       └── JsonProjectRepository.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/projectcli/
            ├── domain/
            ├── service/
            ├── store/
            ├── command/
            └── process/
~~~

Giữ các package trong phạm vi component scan của class application. Nếu đặt class application ở package gốc `com.example.projectcli`, Spring Boot có thể scan các package con.

## 5. Cấu hình ứng dụng

Tạo `ProjectCliApplication`:

~~~java
package com.example.projectcli;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProjectCliApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProjectCliApplication.class, args);
    }
}
~~~

Cấu hình `application.yml`:

~~~yaml
spring:
  main:
    banner-mode: "off"
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: true
    script:
      enabled: true

project:
  store:
    path: ./data/projects.json
~~~

Trong Spring Shell 3.1.x, interactive, non-interactive và script runners được bật mặc định; khai báo rõ trong file giúp người bảo trì hiểu mode mà sản phẩm hỗ trợ. Runner sẽ chọn cách chạy phù hợp với input.

Đường dẫn store được cấu hình bằng `project.store.path`. Với máy cá nhân có thể dùng thư mục dữ liệu của người dùng; với CI hoặc scheduler nên truyền đường dẫn tuyệt đối bằng environment variable hoặc command-line property để không phụ thuộc working directory. Ví dụ trên dùng đường dẫn tương đối để dễ chạy lần đầu.

Không đặt dữ liệu dự án trong thư mục build vì lệnh clean hoặc thay artifact có thể xóa dữ liệu. Trong production, cần xác định backup, quyền truy cập file và chính sách lưu trữ.

## 6. Xây dựng domain model

### 6.1. ProjectCode

Code là value object. Constructor chuẩn hóa chữ hoa và từ chối format sai:

~~~java
package com.example.projectcli.domain;

import java.util.Locale;

public record ProjectCode(String value) {

    public ProjectCode {
        if (value == null) {
            throw new IllegalArgumentException("Project code is required");
        }

        value = value.trim().toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z]{3}-[0-9]{4}")) {
            throw new IllegalArgumentException(
                    "Project code must match AAA-1234");
        }
    }
}
~~~

Định dạng có ba chữ cái, dấu gạch nối và bốn chữ số. Chuẩn hóa nằm trong domain type để mọi caller đều nhận cùng một quy tắc, kể cả khi service được gọi từ test hoặc adapter khác.

### 6.2. Project và ProjectStatus

~~~java
package com.example.projectcli.domain;

public enum ProjectStatus {
    ACTIVE,
    ARCHIVED
}
~~~

~~~java
package com.example.projectcli.domain;

public record Project(
        String code,
        String name,
        String owner,
        int priority,
        ProjectStatus status) {
}
~~~

Repository lưu code ở dạng chuỗi canonical. Nhờ vậy JSON dễ đọc và không phụ thuộc cách Jackson serialize value object.

## 7. Tạo repository để lưu dữ liệu bền vững

### 7.1. Repository contract

~~~java
package com.example.projectcli.store;

import java.util.List;
import java.util.Optional;

import com.example.projectcli.domain.Project;

public interface ProjectRepository {

    List<Project> findAll();

    Optional<Project> findByCode(String code);

    Project save(Project project);
}
~~~

Service chỉ phụ thuộc interface này. Sau này có thể thay JSON file bằng JDBC hoặc API mà không cần đổi command.

### 7.2. Lỗi lưu trữ

~~~java
package com.example.projectcli.service;

public class ProjectStoreException extends RuntimeException {

    public ProjectStoreException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Không trả về danh sách rỗng khi file JSON hỏng. Danh sách rỗng là kết quả nghiệp vụ hợp lệ; file hỏng là lỗi lưu trữ. Hai trường hợp cần được phân biệt để người dùng không hiểu nhầm dữ liệu đã biến mất.

### 7.3. JSON repository

~~~java
package com.example.projectcli.store;

import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import com.example.projectcli.domain.Project;
import com.example.projectcli.service.ProjectStoreException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Repository;

@Repository
public class JsonProjectRepository implements ProjectRepository {

    private final ObjectMapper objectMapper;
    private final Path file;

    public JsonProjectRepository(
            ObjectMapper objectMapper,
            @Value("${project.store.path}") String filePath) {
        this.objectMapper = objectMapper;
        this.file = Paths.get(filePath).toAbsolutePath().normalize();
    }

    @Override
    public synchronized List<Project> findAll() {
        return List.copyOf(readAll());
    }

    @Override
    public synchronized Optional<Project> findByCode(String code) {
        return readAll().stream()
                .filter(project -> project.code().equals(code))
                .findFirst();
    }

    @Override
    public synchronized Project save(Project project) {
        List<Project> projects = readAll();
        projects.removeIf(existing ->
                existing.code().equals(project.code()));
        projects.add(project);
        writeAll(projects);
        return project;
    }

    private List<Project> readAll() {
        if (!Files.exists(file)) {
            return new ArrayList<>();
        }

        try {
            List<Project> projects = objectMapper.readValue(
                    file.toFile(),
                    new TypeReference<List<Project>>() {});
            return projects == null
                    ? new ArrayList<>()
                    : new ArrayList<>(projects);
        }
        catch (IOException ex) {
            throw new ProjectStoreException(
                    "Cannot read project store: " + file, ex);
        }
    }

    private void writeAll(List<Project> projects) {
        Path parent = file.getParent();

        try {
            Files.createDirectories(parent);
            Path temporary = Files.createTempFile(
                    parent, "projects-", ".tmp");

            try {
                objectMapper.writerWithDefaultPrettyPrinter()
                        .writeValue(temporary.toFile(), projects);

                try {
                    Files.move(
                            temporary,
                            file,
                            StandardCopyOption.ATOMIC_MOVE,
                            StandardCopyOption.REPLACE_EXISTING);
                }
                catch (AtomicMoveNotSupportedException ex) {
                    Files.move(
                            temporary,
                            file,
                            StandardCopyOption.REPLACE_EXISTING);
                }
            }
            finally {
                Files.deleteIfExists(temporary);
            }
        }
        catch (IOException ex) {
            throw new ProjectStoreException(
                    "Cannot write project store: " + file, ex);
        }
    }
}
~~~

Repository tạo thư mục cha khi cần. Khi ghi, nó viết vào file tạm cùng thư mục rồi thay file chính bằng move. Nếu filesystem không hỗ trợ atomic move, adapter dùng replace thông thường.

Các method được đồng bộ trong một instance để tránh hai thread trong cùng process ghi đồng thời. Cơ chế này không khóa giữa nhiều process. Vì vậy, bài thực hành giả định một process Project CLI cập nhật file tại một thời điểm. Không dùng adapter này như một database đồng thời cho nhiều người dùng.

## 8. Viết service và quy tắc nghiệp vụ

### 8.1. Domain exceptions

~~~java
package com.example.projectcli.service;

public class ProjectNotFoundException extends RuntimeException {

    public ProjectNotFoundException(String code) {
        super("Project not found: " + code);
    }
}
~~~

~~~java
package com.example.projectcli.service;

public class ProjectAlreadyExistsException extends RuntimeException {

    public ProjectAlreadyExistsException(String code) {
        super("Project already exists: " + code);
    }
}
~~~

### 8.2. ProjectService

~~~java
package com.example.projectcli.service;

import java.util.Comparator;
import java.util.List;

import com.example.projectcli.domain.Project;
import com.example.projectcli.domain.ProjectCode;
import com.example.projectcli.domain.ProjectStatus;
import com.example.projectcli.store.ProjectRepository;

import org.springframework.stereotype.Service;

@Service
public class ProjectService {

    private final ProjectRepository repository;

    public ProjectService(ProjectRepository repository) {
        this.repository = repository;
    }

    public Project create(
            ProjectCode code,
            String name,
            String owner,
            int priority) {

        if (repository.findByCode(code.value()).isPresent()) {
            throw new ProjectAlreadyExistsException(code.value());
        }

        Project project = new Project(
                code.value(),
                name.trim(),
                owner.trim(),
                priority,
                ProjectStatus.ACTIVE);

        return repository.save(project);
    }

    public Project find(ProjectCode code) {
        return repository.findByCode(code.value())
                .orElseThrow(() ->
                        new ProjectNotFoundException(code.value()));
    }

    public List<Project> list(int limit) {
        return repository.findAll().stream()
                .sorted(Comparator.comparing(Project::code))
                .limit(limit)
                .toList();
    }

    public Project archive(ProjectCode code) {
        Project current = find(code);

        if (current.status() == ProjectStatus.ARCHIVED) {
            return current;
        }

        Project archived = new Project(
                current.code(),
                current.name(),
                current.owner(),
                current.priority(),
                ProjectStatus.ARCHIVED);

        return repository.save(archived);
    }
}
~~~

Service chịu trách nhiệm kiểm tra trùng mã, tìm dự án và archive. Validation cú pháp ở command giúp phản hồi sớm; service vẫn kiểm tra quy tắc nghiệp vụ vì service có thể được gọi từ adapter khác.

Archive idempotent: gọi lại không làm dự án chuyển sang trạng thái khác hoặc tạo bản ghi mới. Đây là tính chất hữu ích cho script retry.

## 9. Đăng ký converter

Spring Shell nhận token dưới dạng văn bản và cần chuyển thành ProjectCode. Tạo converter:

~~~java
package com.example.projectcli.command;

import com.example.projectcli.domain.ProjectCode;

import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
public class StringToProjectCodeConverter
        implements Converter<String, ProjectCode> {

    @Override
    public ProjectCode convert(String source) {
        return new ProjectCode(source);
    }
}
~~~

Converter được component scan thành bean. ConversionService của Spring sử dụng cặp source/target type để tìm converter phù hợp.

Converter chỉ chuẩn hóa và kiểm tra định dạng. Nó không truy vấn repository để xác định mã có tồn tại hay không. Tồn tại/không tồn tại là quy tắc nghiệp vụ thuộc service.

## 10. Viết command và định dạng output

### 10.1. OutputFormat

~~~java
package com.example.projectcli.command;

public enum OutputFormat {
    TABLE,
    JSON
}
~~~

### 10.2. ProjectCommands

~~~java
package com.example.projectcli.command;

import java.util.List;
import java.util.Locale;

import com.example.projectcli.domain.Project;
import com.example.projectcli.domain.ProjectCode;
import com.example.projectcli.service.ProjectService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class ProjectCommands {

    private final ProjectService service;
    private final ObjectMapper objectMapper;

    public ProjectCommands(
            ProjectService service,
            ObjectMapper objectMapper) {
        this.service = service;
        this.objectMapper = objectMapper;
    }

    @ShellMethod(
            key = "project create",
            value = "Create a project.")
    public String create(
            @ShellOption("--code") ProjectCode code,
            @ShellOption("--name")
            @NotBlank
            @Size(max = 60) String name,
            @ShellOption("--owner")
            @NotBlank
            @Size(max = 40) String owner,
            @ShellOption(value = "--priority", defaultValue = "3")
            @Min(1)
            @Max(5) int priority) {

        Project project = service.create(
                code, name, owner, priority);

        return "Created project " + project.code()
                + " (" + project.status() + ")";
    }

    @ShellMethod(
            key = "project show",
            value = "Show a project.")
    public String show(
            @ShellOption("--code") ProjectCode code)
            throws JsonProcessingException {

        Project project = service.find(code);

        return objectMapper.writerWithDefaultPrettyPrinter()
                .writeValueAsString(project);
    }

    @ShellMethod(
            key = "project list",
            value = "List projects.")
    public String list(
            @ShellOption(value = "--limit", defaultValue = "20")
            @Min(1)
            @Max(100) int limit,
            @ShellOption(value = "--format", defaultValue = "TABLE")
            OutputFormat format)
            throws JsonProcessingException {

        List<Project> projects = service.list(limit);

        if (format == OutputFormat.JSON) {
            return objectMapper.writeValueAsString(projects);
        }

        return renderTable(projects);
    }

    @ShellMethod(
            key = "project archive",
            value = "Archive a project.")
    public String archive(
            @ShellOption("--code") ProjectCode code) {

        Project project = service.archive(code);
        return "Archived project " + project.code();
    }

    private String renderTable(List<Project> projects) {
        if (projects.isEmpty()) {
            return "No projects found.";
        }

        StringBuilder output = new StringBuilder();

        output.append(String.format(
                Locale.ROOT,
                "%-12s %-24s %-16s %-8s %-10s%n",
                "CODE", "NAME", "OWNER", "PRIORITY", "STATUS"));

        for (Project project : projects) {
            output.append(String.format(
                    Locale.ROOT,
                    "%-12s %-24s %-16s %-8d %-10s%n",
                    project.code(),
                    project.name(),
                    project.owner(),
                    project.priority(),
                    project.status()));
        }

        return output.toString();
    }
}
~~~

Command chỉ điều phối service và định dạng kết quả. Nó không biết file JSON nằm ở đâu. Nếu thay repository bằng database, command không cần đổi.

Tên option và default được ghi trực tiếp trong annotation. Bean Validation kiểm tra name, owner và priority sau khi input đã được bind. ProjectCode converter kiểm tra định dạng code trước khi method chạy.

Nếu format enum không chuyển đổi được theo cách người dùng nhập, hãy quy định rõ TABLE và JSON trong help/README hoặc bổ sung converter riêng. Đừng giả định mọi parser đều tự chuẩn hóa enum theo cùng một quy tắc.

## 11. Ánh xạ lỗi thành message và exit code

Spring Shell 3.1.x hỗ trợ CommandExceptionResolver. Resolver trả về CommandHandlingResult có thể chứa message và exit code.

~~~java
package com.example.projectcli.command;

import com.example.projectcli.service.ProjectAlreadyExistsException;
import com.example.projectcli.service.ProjectNotFoundException;
import com.example.projectcli.service.ProjectStoreException;

import org.springframework.shell.command.CommandExceptionResolver;
import org.springframework.shell.command.CommandHandlingResult;
import org.springframework.stereotype.Component;

@Component
public class ProjectCommandExceptionResolver
        implements CommandExceptionResolver {

    @Override
    public CommandHandlingResult resolve(Exception exception) {
        if (exception instanceof ProjectNotFoundException) {
            return CommandHandlingResult.of(
                    exception.getMessage(), 3);
        }

        if (exception instanceof ProjectAlreadyExistsException) {
            return CommandHandlingResult.of(
                    exception.getMessage(), 4);
        }

        if (exception instanceof ProjectStoreException) {
            return CommandHandlingResult.of(
                    "Project store error: " + exception.getMessage(),
                    5);
        }

        return null;
    }
}
~~~

Trả về null khi resolver này không xử lý exception để resolver tiếp theo tiếp tục. Không bắt mọi exception rồi gán cùng một mã nếu ứng dụng cần phân biệt parse error, domain error và lỗi hệ thống.

Trong Spring Shell 3.1.x, exit code của CommandHandlingResult có ý nghĩa ở non-interactive mode. Khi người dùng chạy REPL, resolver hiển thị message để họ tiếp tục. Kiểm tra mã thực tế bằng process test; đừng suy ra từ message.

Nếu muốn lỗi store không tiết lộ đường dẫn hoặc chi tiết nội bộ, log cause ở phía ứng dụng và chỉ trả message an toàn cho người dùng. Ví dụ trên hiển thị path để thuận tiện cho bài thực hành; sản phẩm thật nên cân nhắc mức thông tin phù hợp.

## 12. Kiểm tra cấu hình runner và các mode chạy

Spring Shell 3.1.x có ba runner:

- InteractiveShellRunner mở REPL.
- NonInteractiveShellRunner chạy command được truyền qua arguments.
- ScriptShellRunner thực thi các command trong file script.

Các runner của Spring Shell 3.1.x được bật mặc định; có thể bật/tắt bằng các thuộc tính:

- `spring.shell.interactive.enabled`
- `spring.shell.noninteractive.enabled`
- `spring.shell.script.enabled`

### 12.1. Interactive REPL

Chạy ứng dụng không kèm command arguments trong terminal:

~~~bash
java -jar build/libs/project-cli-0.1.0.jar
~~~

Sau đó nhập:

~~~text
shell:> help
shell:> project create --code OPS-1024 --name "Inventory API" --owner platform --priority 3
shell:> project list
shell:> project show --code OPS-1024
shell:> project archive --code OPS-1024
shell:> exit
~~~

REPL giữ cùng ApplicationContext trong suốt phiên. Người dùng có thể chạy nhiều command mà không phải khởi động JVM lại.

### 12.2. Non-interactive command

Truyền command và option sau tên JAR:

~~~bash
java -jar build/libs/project-cli-0.1.0.jar project list --limit 20 --format JSON
~~~

Một process chạy một command rồi kết thúc. Đây là mode phù hợp cho shell script và CI. Dữ liệu được lưu trong file nên command tiếp theo ở process mới vẫn đọc được dự án đã tạo.

### 12.3. Script mode

Tạo file `scripts/bootstrap.shell`:

~~~text
// Create sample projects
project create --code OPS-1001 --name "Inventory API" --owner platform --priority 3
project create --code OPS-1002 --name "Billing Worker" --owner finance --priority 4
project list --limit 50 --format TABLE
~~~

Trong Spring Shell 3.1.6, ScriptShellRunner nhận process argument bắt đầu bằng ký tự `@` và coi phần còn lại là đường dẫn script:

~~~bash
java -jar build/libs/project-cli-0.1.0.jar @scripts/bootstrap.shell
~~~

Script runner chạy các command theo thứ tự trong file rồi kết thúc process. Bảo đảm script path đúng với working directory hiện tại; khi chạy từ scheduler, nên dùng đường dẫn tuyệt đối hoặc đặt working directory rõ ràng.

Kiểm tra hành vi khi một command trong script lỗi bằng process test. Không giả định script sẽ dừng hay tiếp tục theo mong muốn nếu chưa xác minh version và runner đang dùng.

### 12.4. Phân biệt runner với command

Một command có thể được gọi trong nhiều mode, nhưng một số command tương tác chỉ có ý nghĩa trong REPL. Ví dụ command thoát shell không có ý nghĩa như một nghiệp vụ non-interactive.

Đặc tả mode cho command nếu cần. Với Project CLI, bốn command nghiệp vụ phải hoạt động trong REPL, non-interactive và script.

## 13. Kiểm thử theo từng lớp

Không dùng một test duy nhất để kiểm tra toàn bộ sản phẩm. Mỗi lớp cần test phù hợp.

| Lớp | Mục tiêu | Công cụ |
|---|---|---|
| Value object | Format và normalization của ProjectCode | JUnit |
| Converter | String thành ProjectCode | JUnit |
| Service | Duplicate, not found, archive idempotent | JUnit/Mockito |
| Repository | JSON read/write và lỗi file | JUnit, @TempDir |
| Shell command | Registration, parsing, validation, output | @ShellTest, ShellTestClient |
| Process | stdout, stderr, exit code và shutdown | ProcessBuilder |

### 13.1. Test ProjectCode và converter

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class ProjectCodeTests {

    @Test
    void normalizesCodeToUppercase() {
        assertThat(new ProjectCode("ops-1024").value())
                .isEqualTo("OPS-1024");
    }

    @Test
    void rejectsInvalidFormat() {
        assertThatThrownBy(() -> new ProjectCode("bad-code"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Test converter độc lập:

~~~java
class StringToProjectCodeConverterTests {

    private final StringToProjectCodeConverter converter =
            new StringToProjectCodeConverter();

    @Test
    void convertsValidCode() {
        assertThat(converter.convert("ops-1024").value())
                .isEqualTo("OPS-1024");
    }

    @Test
    void rejectsInvalidCode() {
        assertThatThrownBy(() -> converter.convert("invalid"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Hai test này xác minh logic domain và converter. Chúng chưa chứng minh Spring đã đăng ký converter hoặc shell đang dùng ConversionService phù hợp.

### 13.2. Test service

Dùng fake repository đơn giản hoặc Mockito để kiểm tra quy tắc nghiệp vụ:

~~~java
@Test
void createRejectsDuplicateCode() {
    ProjectRepository repository = mock(ProjectRepository.class);
    ProjectService service = new ProjectService(repository);

    when(repository.findByCode("OPS-1024"))
            .thenReturn(Optional.of(existingProject()));

    assertThatThrownBy(() -> service.create(
            new ProjectCode("OPS-1024"),
            "Inventory API",
            "platform",
            3))
            .isInstanceOf(ProjectAlreadyExistsException.class);

    verify(repository, never()).save(any());
}
~~~

Test archive idempotent:

~~~java
@Test
void archivingArchivedProjectDoesNotWriteAgain() {
    Project archived = new Project(
            "OPS-1024",
            "Inventory API",
            "platform",
            3,
            ProjectStatus.ARCHIVED);

    ProjectRepository repository = mock(ProjectRepository.class);
    when(repository.findByCode("OPS-1024"))
            .thenReturn(Optional.of(archived));

    ProjectService service = new ProjectService(repository);

    assertThat(service.archive(new ProjectCode("OPS-1024")))
            .isEqualTo(archived);

    verify(repository, never()).save(any());
}
~~~

Các ví dụ giả định test có helper tạo Project fixture và static imports của Mockito/AssertJ. Trong test thật, giữ fixture rõ ràng để reviewer thấy trạng thái ban đầu.

### 13.3. Test JSON repository

Dùng thư mục tạm để không ghi vào home directory thật:

~~~java
@TempDir
Path tempDir;

@Test
void savesAndReadsProject() {
    ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();
    Path file = tempDir.resolve("projects.json");

    JsonProjectRepository repository =
            new JsonProjectRepository(mapper, file.toString());

    Project project = new Project(
            "OPS-1024",
            "Inventory API",
            "platform",
            3,
            ProjectStatus.ACTIVE);

    repository.save(project);

    assertThat(repository.findByCode("OPS-1024"))
            .contains(project);
}
~~~

Nếu dùng ObjectMapper do Spring Boot cấu hình, test context có thể inject mapper đó thay vì tạo mapper thủ công. Mục tiêu là test được persistence và đảm bảo file được tạo ở đúng path.

Bổ sung test file JSON lỗi hoặc không đọc được. Repository phải ném ProjectStoreException thay vì giả vờ trả về danh sách rỗng.

## 14. Shell test với ShellTestClient

Spring Shell cung cấp test support để mô phỏng người dùng gửi command và đọc terminal screen.

Với Spring Shell 3.1.x, non-interactive method có spelling `nonInterative`. Dùng đúng tên API của dependency dự án.

Ví dụ:

~~~java
import static org.awaitility.Awaitility.await;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.concurrent.TimeUnit;

import com.example.projectcli.domain.Project;
import com.example.projectcli.domain.ProjectStatus;
import com.example.projectcli.service.ProjectService;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
class ProjectCommandTests {

    @Autowired
    ShellTestClient client;

    @MockBean
    ProjectService projectService;

    @Test
    void listCommandDisplaysProjects() {
        when(projectService.list(20)).thenReturn(List.of(
                new Project("OPS-1024", "Inventory API",
                        "platform", 3, ProjectStatus.ACTIVE)));

        var session = client.nonInterative(
                "project", "list",
                "--limit", "20",
                "--format", "TABLE")
                .run();

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("CODE")
                        .containsText("NAME"));
    }
}
~~~

Dùng Awaitility vì shell có thể cập nhật screen bất đồng bộ. Không đọc screen ngay sau run rồi giả định output đã hoàn tất.

### 14.1. Kiểm tra validation

Gửi input không hợp lệ:

~~~java
import static org.awaitility.Awaitility.await;
import static org.mockito.Mockito.verifyNoInteractions;

import java.util.concurrent.TimeUnit;

import com.example.projectcli.service.ProjectService;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
class ProjectValidationCommandTests {

    @Autowired
    ShellTestClient client;

    @MockBean
    ProjectService projectService;

    @Test
    void blankNameIsRejectedBeforeServiceCall() {
        var session = client.nonInterative(
                "project", "create",
                "--code", "OPS-1024",
                "--name", "",
                "--owner", "platform",
                "--priority", "3")
                .run();

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("must not be blank"));

        verifyNoInteractions(projectService);
    }
}
~~~

Test này kiểm tra message validation và xác minh service không được gọi. Nếu ứng dụng tùy biến message hoặc locale, thay đoạn text assertion bằng một thông báo ổn định do ứng dụng định nghĩa.

### 14.2. Kiểm tra converter

~~~java
import static org.awaitility.Awaitility.await;
import static org.mockito.Mockito.when;

import java.util.concurrent.TimeUnit;

import com.example.projectcli.domain.Project;
import com.example.projectcli.domain.ProjectCode;
import com.example.projectcli.domain.ProjectStatus;
import com.example.projectcli.service.ProjectService;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
class ProjectCodeConversionCommandTests {

    @Autowired
    ShellTestClient client;

    @MockBean
    ProjectService projectService;

    @Test
    void convertsLowercaseCodeBeforeCallingService() {
        when(projectService.find(new ProjectCode("OPS-1024")))
                .thenReturn(new Project("OPS-1024", "Inventory API",
                        "platform", 3, ProjectStatus.ACTIVE));
        var session = client.nonInterative(
                "project", "show",
                "--code", "ops-1024")
                .run();

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("OPS-1024"));
    }
}
~~~

Test này stub service theo ProjectCode canonical và xác minh shell chuyển `ops-1024` thành `OPS-1024` trước khi gọi service. Nhờ vậy test kiểm tra được converter qua đường command thực tế.

### 14.3. Kiểm tra script runner

Có thể kiểm tra script runner bằng process integration test dùng file script tạm. Không nên chỉ gọi ScriptShellRunner trực tiếp nếu mục tiêu là xác minh executable đã cấu hình đúng runner.

## 15. Process test cho exit code

ShellTestClient kiểm tra command trong phiên shell giả lập. Để kiểm tra exit code của hệ điều hành, chạy executable trong process riêng.

Ví dụ test lỗi not found:

~~~java
@Test
void missingProjectReturnsExitCodeThree() throws Exception {
    Path stdout = tempDir.resolve("stdout.txt");
    Path stderr = tempDir.resolve("stderr.txt");

    Process process = new ProcessBuilder(
            javaExecutable,
            "-jar",
            cliJar.toString(),
            "project", "show",
            "--code", "OPS-9999")
            .redirectOutput(stdout.toFile())
            .redirectError(stderr.toFile())
            .start();

    boolean finished = process.waitFor(15, TimeUnit.SECONDS);
    if (!finished) {
        process.destroyForcibly();
        process.waitFor(5, TimeUnit.SECONDS);
        fail("CLI process did not finish within timeout");
    }

    assertThat(process.exitValue()).isEqualTo(3);
    String output = Files.readString(stdout) + Files.readString(stderr);
    assertThat(output)
            .contains("Project not found: OPS-9999");
}
~~~

Test cần cung cấp `javaExecutable`, `cliJar`, `tempDir` và các import tương ứng. Dùng file redirect để tránh deadlock khi process ghi nhiều dữ liệu vào pipe mà test chưa đọc.

Viết thêm test thành công với exit code `0`, lỗi duplicate với `4`, lỗi store với `5` và parser error theo mapping của framework. Không chỉ kiểm tra message: caller của executable thường quyết định hành động tiếp theo dựa vào exit code.

## 16. Xác minh output máy đọc được

Chạy:

~~~bash
java -jar build/libs/project-cli-0.1.0.jar project list --format JSON
~~~

Output cần là JSON hợp lệ. Kiểm tra bằng công cụ JSON:

~~~bash
java -jar build/libs/project-cli-0.1.0.jar project list --format JSON > projects.json
jq . projects.json
~~~

Nếu stdout có banner hoặc log, parser có thể thất bại. Tắt banner như cấu hình ở trên và cấu hình logging phù hợp. Nếu cần giữ log chẩn đoán, định tuyến log ra file hoặc stream riêng theo cấu hình đã kiểm tra.

Một contract output nên ghi rõ:

- JSON schema và tên field.
- Cách biểu diễn enum.
- Null và field thiếu.
- Encoding.
- Newline cuối.
- Diagnostic ở stderr.
- Có hay không ANSI color.

Không dùng snapshot raw toàn màn hình cho JSON nếu có thể parse JSON và so sánh cấu trúc.

## 17. Viết script vận hành

Ví dụ `scripts/bootstrap.shell`:

~~~text
// Initial data for a new environment
project create --code OPS-1001 --name "Inventory API" --owner platform --priority 3
project create --code OPS-1002 --name "Billing Worker" --owner finance --priority 4
project list --limit 100 --format TABLE
~~~

Chạy:

~~~bash
java -jar build/libs/project-cli-0.1.0.jar @scripts/bootstrap.shell
~~~

Script có thể chạy lặp lại và gặp lỗi duplicate. Nếu muốn script idempotent, phải thiết kế rõ cách xử lý duplicate: bỏ qua khi đã tồn tại, dùng command upsert, hoặc kiểm tra trước khi create. Không nên âm thầm coi mọi duplicate là thành công nếu caller cần phát hiện cấu hình sai.

Khi chạy trong CI:

- Dùng working directory xác định.
- Dùng path tuyệt đối cho script và store nếu cần.
- Ghi log command và exit code.
- Không truyền secret trên command line nếu process list có thể hiển thị arguments.
- Đặt timeout cho job.
- Lưu artifact hoặc backup nếu command thay đổi dữ liệu quan trọng.

## 18. Đóng gói executable JAR

Build và test:

~~~bash
./gradlew clean test bootJar
~~~

Artifact thường nằm ở:

~~~text
build/libs/project-cli-0.1.0.jar
~~~

Chạy từ terminal:

~~~bash
java -jar build/libs/project-cli-0.1.0.jar help
java -jar build/libs/project-cli-0.1.0.jar project list
~~~

Kiểm tra executable JAR trên môi trường sạch có Java 17 nhưng không có IDE, không có classpath từ Gradle và không có file cấu hình phát triển ngoài dự kiến.

Nếu cần phân phối ZIP, cấu trúc có thể là:

~~~text
project-cli-0.1.0/
├── project-cli.jar
├── README.md
├── config/
│   └── application-example.yml
├── scripts/
│   ├── bootstrap.shell
│   ├── project-list.sh
│   └── project-list.ps1
└── LICENSE
~~~

Không đóng gói file dữ liệu cá nhân hoặc store JSON của môi trường phát triển vào artifact phát hành.

### 18.1. Script wrapper cho Linux/macOS

Ví dụ `project-cli.sh`:

~~~bash
#!/usr/bin/env sh
set -eu

APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec java -jar "$APP_DIR/project-cli.jar" "$@"
~~~

Wrapper xác định thư mục chứa JAR và chuyển tiếp nguyên vẹn arguments. Sau khi đóng gói, cấp quyền thực thi cho file shell script.

### 18.2. Script wrapper cho Windows PowerShell

~~~powershell
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& java -jar (Join-Path $AppDir "project-cli.jar") @args
exit $LASTEXITCODE
~~~

Wrapper cần giữ exit code của Java process. Nếu PowerShell script luôn trả `0`, CI có thể đánh dấu thành công dù command đã thất bại.

## 19. Viết README cho người dùng

README nên hướng dẫn người dùng chưa biết source code vẫn cài và sử dụng được.

Một cấu trúc đề xuất:

~~~markdown
# Project CLI

Project CLI quản lý dự án từ terminal.

## Requirements

- Java 17 hoặc tương thích với runtime đã build.
- Quyền đọc/ghi thư mục lưu dữ liệu.

## Build

./gradlew clean test bootJar

## Start interactive shell

java -jar project-cli.jar

## Commands

project create --code OPS-1024 --name "Inventory API" --owner platform
project show --code OPS-1024
project list --format TABLE
project list --format JSON
project archive --code OPS-1024

## Data location

Default: ./data/projects.json

Override with project.store.path.

## Script mode

java -jar project-cli.jar @scripts/bootstrap.shell

## Exit codes

0 success
2 command parsing error
3 project not found
4 duplicate project code
5 project store error

## Troubleshooting

Check Java version, store path permissions, command help and exit code.
~~~

README phải khớp với command key, default và exit code thực tế. Nếu thay option hoặc output schema, cập nhật README cùng test contract.

## 20. Viết help và ví dụ sử dụng

Spring Shell có built-in help. Sau khi chạy REPL:

~~~text
shell:> help
shell:> help project create
shell:> help project list
~~~

Mỗi command cần description ngắn và option name dễ hiểu. README cung cấp ví dụ hoàn chỉnh; help giải thích cú pháp ngay trong ứng dụng.

Kiểm tra:

- Command có xuất hiện trong help không?
- Option có hiển thị đúng tên và kiểu không?
- Required/optional có dễ nhận ra không?
- Default có được giải thích không?
- Ví dụ có chạy được với artifact mới build không?
- Alias có được ghi trong tài liệu nếu có?

Không xem help là tài liệu duy nhất. Automation thường dùng README hoặc runbook mà không mở REPL.

## 21. Quy trình hoàn thiện capstone

Thực hiện theo thứ tự để mỗi giai đoạn có đầu ra review được:

| Giai đoạn | Đầu ra | Điều kiện qua bước |
|---|---|---|
| Đặc tả | Command contract và acceptance criteria | Cú pháp, lỗi và output rõ |
| Thiết kế | Sơ đồ lớp và repository contract | Command không chứa persistence logic |
| Project setup | Build file và application config | Dependency/runtime đồng bộ |
| Domain | ProjectCode, Project, status | Format và invariant có test |
| Persistence | Repository JSON | Dữ liệu còn sau process restart |
| Service | Create/show/list/archive | Quy tắc nghiệp vụ có unit test |
| Shell adapter | Commands, converter, validation | Command chạy qua parser |
| Error policy | Exception resolver và exit code | Process trả đúng mã |
| Execution | REPL, non-interactive, script | Cả ba mode được kiểm tra |
| Test | Unit, shell, repository, process | Regression quan trọng được bảo vệ |
| Packaging | Executable JAR và wrapper | Chạy trên môi trường sạch |
| Documentation | README, script, help | Người dùng có thể tự chạy |

Không bắt đầu đóng gói khi repository chỉ hoạt động bằng dữ liệu test trong memory. Hãy kiểm tra dữ liệu tồn tại sau khi process kết thúc và khởi động lại.

## 22. Những lỗi thường gặp khi tích hợp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Converter không chạy | Converter không phải bean hoặc sai target type | Test ConversionService và shell command |
| Validation không chạy | Thiếu provider hoặc constraint sai kiểu | Kiểm tra validation starter và Jakarta imports |
| Dữ liệu biến mất sau mỗi lần gọi | Repository chỉ dùng memory | Test process restart và file store |
| Store file không được tạo | Parent directory không có quyền ghi | Kiểm tra path và filesystem permissions |
| JSON không parse được | Banner/log chen vào stdout | Redirect stdout/stderr và kiểm tra output |
| Exit code luôn là 0 | Exception resolver không trả CommandHandlingResult đúng | ProcessBuilder test |
| Script không chạy | Script runner tắt hoặc argument không bắt đầu bằng @ | Kiểm tra runner và đường dẫn file |
| Script dùng nhầm store | Environment variable hoặc working directory khác | Kiểm tra resolved path trong profile chẩn đoán |
| Process không thoát | Thread nền hoặc runner sai mode | Kiểm tra context lifecycle và process timeout |
| Test shell đọc screen quá sớm | Output bất đồng bộ | Dùng Awaitility |
| Test repository ghi vào home thật | Không dùng @TempDir | Dùng path tạm cho từng test |
| Hai process ghi đè dữ liệu | File adapter không có inter-process lock | Chỉ cho một writer hoặc chuyển sang database |

## 23. Bài kiểm tra cuối cùng trên môi trường sạch

Sau khi build, tạo một thư mục làm việc mới và chạy các kịch bản sau:

1. Gọi help và kiểm tra bốn command xuất hiện.
2. Tạo dự án OPS-1024.
3. Gọi một process mới để show OPS-1024.
4. Gọi list với TABLE và JSON.
5. Dùng JSON parser xác minh output.
6. Thử tạo lại OPS-1024 và kiểm tra exit code `4`.
7. Show một code không tồn tại và kiểm tra exit code `3`.
8. Thử code sai format và kiểm tra lỗi conversion.
9. Thử name rỗng và priority bằng `0`.
10. Archive dự án và gọi archive lần thứ hai.
11. Chạy bootstrap script.
12. Đổi project.store.path sang một thư mục tạm và xác minh dữ liệu được ghi đúng nơi.
13. Chạy wrapper Linux/macOS hoặc PowerShell và xác minh exit code được truyền tiếp.
14. Chạy lại toàn bộ unit, shell và process tests.

Ghi lại môi trường kiểm tra: Java version, OS, artifact version, store path, command và exit code. Điều này giúp tái hiện lỗi khi phát hành.

## 24. Checklist Definition of Done

- [ ] Đặc tả command và acceptance criteria được lưu.
- [ ] Bốn command create/show/list/archive được đăng ký.
- [ ] ProjectCode được chuẩn hóa và converter hoạt động.
- [ ] Validation kiểm tra name, owner, priority và limit.
- [ ] Service bảo vệ duplicate, not found và archive idempotency.
- [ ] Repository JSON lưu dữ liệu bền vững.
- [ ] File ghi qua temporary file và replace.
- [ ] Output TABLE và JSON có thể sử dụng.
- [ ] Exception resolver trả message và exit code đúng.
- [ ] REPL chạy được trong terminal.
- [ ] Non-interactive command chạy được từ process mới.
- [ ] Script runner thực thi file script.
- [ ] Unit test cho domain, converter và service.
- [ ] Repository test dùng thư mục tạm.
- [ ] Shell test kiểm tra parser, validation và output.
- [ ] Process test kiểm tra exit code và timeout.
- [ ] Executable JAR được tạo bằng bootJar.
- [ ] Wrapper giữ nguyên arguments và exit code.
- [ ] README và script ví dụ khớp với artifact.
- [ ] Đã thử trên môi trường sạch.
- [ ] Giới hạn file store một writer được ghi rõ.

## 25. Mở rộng sau capstone

Sau khi hoàn thành phiên bản đầu, có thể mở rộng theo từng nhu cầu:

- Thay JSON repository bằng Spring Data JDBC hoặc JPA.
- Thêm search theo owner, status và priority.
- Thêm pagination và sort.
- Thêm CSV export và import.
- Thêm shell completion cho code và status.
- Thêm availability để chặn command khi chưa cấu hình store.
- Thêm audit log cho create/archive.
- Thêm backup và restore.
- Thêm native image nếu startup/footprint là yêu cầu thực tế.
- Thêm process-level compatibility tests vào CI.

Mỗi tính năng mới cần cập nhật command contract, help, README và test. Tránh thêm option chỉ vì có thể thêm; chỉ thêm khi có use case và quy tắc rõ.

## 26. Kết luận

Capstone Project CLI hoàn thành một vòng phát triển Spring Shell từ đặc tả đến công cụ có thể phân phối. Đặc tả định nghĩa command key, option, default, output và lỗi. Domain/service bảo vệ quy tắc nghiệp vụ. Converter và validation xử lý input ở ranh giới shell. Repository lưu dữ liệu qua nhiều lần chạy. Runner hỗ trợ REPL, một command non-interactive và script.

Unit test bảo vệ logic nhỏ; shell test xác minh parser, registration và màn hình; process test xác minh exit code, stream và vòng đời executable. Cuối cùng, executable JAR, wrapper và README biến project thành công cụ người khác có thể cài và sử dụng.

Hãy xem README, help, command syntax, output schema và exit code là một phần của sản phẩm. Khi một trong các hợp đồng đó thay đổi, hãy cập nhật test và tài liệu trong cùng một thay đổi.

## Tài liệu tham khảo

- [Spring Shell 3.1.6 Reference Documentation](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html)
- [Spring Shell 3.1 API: ScriptShellRunner](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/jline/ScriptShellRunner.html)
- [Spring Shell 3.1 API: CommandHandlingResult](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandHandlingResult.html)
- [Spring Shell 3.1 API: CommandExceptionResolver](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandExceptionResolver.html)
- [Spring Shell 3.1 API: ShellTestClient](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/test/ShellTestClient.html)
- [Spring Boot 3.1 Reference Documentation](https://docs.spring.io/spring-boot/docs/3.1.x/reference/html/)
- [Spring Framework: Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework: Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)

