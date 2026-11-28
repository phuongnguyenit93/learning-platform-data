# Chia lớp lệnh theo miền nghiệp vụ và khả năng tái sử dụng

Khi ứng dụng Spring Shell có nhiều command, cách tổ chức lớp ảnh hưởng trực tiếp đến khả năng mở rộng và bảo trì CLI. Một lớp chứa tất cả command có thể thuận tiện lúc đầu, nhưng sẽ nhanh chóng trở nên khó đọc khi ứng dụng có thêm miền nghiệp vụ, quy trình và người cùng phát triển. Ngược lại, tạo một lớp cho mỗi command cũng làm cấu trúc vụn vặt và tăng số lượng thành phần phải quản lý.

Một cách tổ chức cân bằng là nhóm command theo miền nghiệp vụ hoặc một nhóm use case có liên quan, sau đó đặt logic nghiệp vụ dùng chung trong application service. Lớp command tập trung vào giao diện dòng lệnh: nhận tham số, gọi use case và trình bày kết quả. Application service giữ quy trình nghiệp vụ để có thể được tái sử dụng từ nhiều command hoặc giao diện khác.

## 1. Vì sao cần chia lớp command?

Ở ứng dụng nhỏ, một lớp command có thể chỉ có vài phương thức. Khi CLI phát triển, các command thường mở rộng theo nhiều hướng:

- Nhiều miền nghiệp vụ như project, user, billing và system.
- Nhiều thao tác trong mỗi miền: tạo, xem, tìm kiếm, cập nhật, xóa và xuất dữ liệu.
- Các luồng tổng hợp cần gọi nhiều dịch vụ.
- Nhiều giao diện cùng sử dụng nghiệp vụ: CLI, REST API, tác vụ nền hoặc công cụ quản trị.

Nếu tất cả command nằm trong một lớp, các phụ thuộc sẽ dồn vào cùng một constructor, các phương thức khó tìm và thay đổi nhỏ có thể ảnh hưởng đến một lớp rất lớn. Nếu command tự chứa truy vấn repository và quy tắc nghiệp vụ, cùng một logic dễ bị sao chép khi thêm giao diện mới.

Chia lớp theo miền nghiệp vụ tạo ra ranh giới dễ hiểu: người đọc có thể tìm command liên quan đến project trong `ProjectCommands`, command quản lý người dùng trong `UserCommands`, và command tổng hợp trong `DashboardCommands`.

## 2. Chọn ranh giới theo miền nghiệp vụ

Một lớp command nên đại diện cho một nhóm thao tác có cùng ngữ cảnh nghiệp vụ và cùng đối tượng người dùng. Ví dụ:

| Lớp command | Trách nhiệm |
|---|---|
| `ProjectCommands` | Liệt kê, xem, tạo, lưu trữ project |
| `UserCommands` | Liệt kê, xem và thay đổi trạng thái người dùng |
| `ReportCommands` | Tạo và xuất báo cáo |
| `DashboardCommands` | Hiển thị thông tin tổng hợp từ nhiều miền |
| `SystemCommands` | Kiểm tra trạng thái và hiển thị thông tin vận hành |

Không nhất thiết mỗi entity phải có một lớp command. Hãy dựa vào nhóm hành vi mà người dùng cần thực hiện. Nếu hai đối tượng thường được thao tác trong cùng một quy trình và cùng ngữ cảnh, chúng có thể nằm trong một lớp. Nếu một lớp chứa các thao tác thuộc những miền khác nhau, có quy tắc bảo mật hoặc vòng đời khác nhau, đó là dấu hiệu nên tách.

Một số tiêu chí giúp quyết định:

- **Tính liên quan:** các command có thao tác trên cùng một miền hoặc phục vụ cùng một nhóm use case không?
- **Lý do thay đổi:** các command có thường thay đổi cùng nhau khi nghiệp vụ thay đổi không?
- **Phụ thuộc:** các command có cần cùng một nhóm service hay đang kéo theo quá nhiều phụ thuộc không liên quan?
- **Quyền hạn:** các command có cùng yêu cầu xác thực và phân quyền không?
- **Khả năng tìm kiếm:** người phát triển có thể đoán được command nằm ở lớp nào từ tên miền và hành động không?

Không cần tách lớp chỉ vì một lớp có một số lượng phương thức nhất định. Hãy tách khi các command không còn cùng một trách nhiệm rõ ràng.

## 3. Tổ chức package theo miền nghiệp vụ

Có thể đặt các lớp command trong package riêng cho từng miền, đồng thời tổ chức application service và domain theo cùng cách:

```text
com.example.projectcli
├── ProjectCliApplication.java
├── command/
│   ├── project/
│   │   └── ProjectCommands.java
│   ├── user/
│   │   └── UserCommands.java
│   ├── report/
│   │   └── ReportCommands.java
│   ├── dashboard/
│   │   └── DashboardCommands.java
│   └── system/
│       └── SystemCommands.java
├── application/
│   ├── project/
│   │   └── ProjectApplicationService.java
│   ├── user/
│   │   └── UserApplicationService.java
│   ├── report/
│   │   └── ReportApplicationService.java
│   └── dashboard/
│       └── DashboardQueryService.java
├── domain/
│   ├── project/
│   └── user/
└── infrastructure/
    ├── persistence/
    └── integration/
```

Cấu trúc này giúp người phát triển lần theo một yêu cầu từ command đến use case và thành phần lưu trữ. Tên package chỉ là cách tổ chức mã nguồn; bản thân package không tạo ra ranh giới bảo mật hoặc ngăn các lớp gọi lẫn nhau. Các quy tắc phụ thuộc vẫn cần được thể hiện qua thiết kế và kiểm tra của dự án.

Với ứng dụng nhỏ, có thể bắt đầu bằng hai package `command` và `service`. Khi số miền tăng, tách theo miền nghiệp vụ. Không cần dựng đầy đủ mọi tầng nếu dự án chưa có nhu cầu.

## 4. Lớp command là adapter của CLI

Lớp command nên làm ba việc chính:

1. Nhận đầu vào từ Spring Shell.
2. Gọi application service tương ứng.
3. Chuyển kết quả thành nội dung phù hợp với terminal.

Ví dụ dưới đây dùng mô hình annotation Spring Shell 4.x từ phiên bản 4.0.2 trở lên: `@Command` đặt trên phương thức và `@CommandGroup` đặt prefix chung cho nhóm. Các import minh họa thuộc package `org.springframework.shell.core.command.annotation`.

```java
package com.example.projectcli.command.project;

import java.util.stream.Collectors;

import com.example.projectcli.application.project.ProjectApplicationService;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;
import org.springframework.stereotype.Component;

@Component
@CommandGroup(prefix = "project", name = "Project")
public class ProjectCommands {

    private final ProjectApplicationService projects;

    public ProjectCommands(ProjectApplicationService projects) {
        this.projects = projects;
    }

    @Command(name = "list", description = "Liệt kê các project")
    public String list() {
        var items = projects.listProjects();

        if (items.isEmpty()) {
            return "Chưa có project.";
        }

        return items.stream()
            .map(item -> item.id() + " - " + item.name())
            .collect(Collectors.joining(System.lineSeparator()));
    }

    @Command(name = "count", description = "Đếm số project")
    public String count() {
        return "Số project: " + projects.countProjects();
    }
}
```

Nhóm command có prefix `project`, nên người dùng gọi:

```text
project list
project count
```

Lớp này không truy cập trực tiếp repository, không tự kiểm tra toàn bộ quy tắc nghiệp vụ và không quản lý giao dịch. Nó chuyển yêu cầu sang `ProjectApplicationService` và định dạng kết quả cho CLI.

Nếu đang dùng Spring Shell 3.x declarative API, cần điều chỉnh theo API của dòng đó: annotation `@Command` dùng thuộc tính `command`, package khác và có thể đặt prefix/group ở cấp lớp. Không trộn import hoặc thuộc tính giữa 3.x và 4.x trong cùng project.

## 5. Đặt logic dùng chung trong application service

Giả sử thao tác liệt kê project cần được dùng từ command quản lý project và command dashboard. Không nên gọi trực tiếp phương thức command của lớp khác. Hãy đưa truy vấn vào application service để cả hai command gọi cùng một use case.

Ví dụ service:

```java
package com.example.projectcli.application.project;

import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class ProjectApplicationService {

    private final ProjectRepository repository;

    public ProjectApplicationService(ProjectRepository repository) {
        this.repository = repository;
    }

    public List<ProjectSummary> listProjects() {
        return repository.findAllSummaries();
    }

    public long countProjects() {
        return repository.count();
    }
}
```

`ProjectRepository` và `ProjectSummary` đại diện cho các thành phần của ứng dụng. Phần cài đặt truy vấn phụ thuộc vào công nghệ lưu trữ của dự án.

Command dashboard có thể sử dụng lại cùng service:

```java
package com.example.projectcli.command.dashboard;

import com.example.projectcli.application.project.ProjectApplicationService;
import com.example.projectcli.application.user.UserApplicationService;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;
import org.springframework.stereotype.Component;

@Component
@CommandGroup(prefix = "dashboard", name = "Dashboard")
public class DashboardCommands {

    private final ProjectApplicationService projects;
    private final UserApplicationService users;

    public DashboardCommands(
            ProjectApplicationService projects,
            UserApplicationService users) {
        this.projects = projects;
        this.users = users;
    }

    @Command(name = "summary", description = "Hiển thị số liệu tổng quan")
    public String summary() {
        return """
            Projects: %d
            Active users: %d
            """.formatted(
                projects.countProjects(),
                users.countActiveUsers()
            );
    }
}
```

Cả hai lớp command dùng cùng một application service. Quy tắc và cách truy vấn số project được triển khai tại một nơi, còn mỗi command quyết định cách trình bày kết quả phù hợp với mục đích của nó.

## 6. Tái sử dụng nghiệp vụ qua nhiều giao diện

Một application service không nên phụ thuộc vào Spring Shell. Khi service chỉ nhận dữ liệu đầu vào của use case và trả kết quả, nó có thể được sử dụng từ nhiều adapter:

```text
                   CLI
                    |
             ProjectCommands
                    |
                    v
              ProjectApplicationService
                    ^
                    |
             ProjectController
                    ^
                    |
                REST API

                    ^
                    |
             ScheduledJob
```

Ví dụ, thao tác tạo project có thể được gọi từ CLI và REST API. Hai adapter có thể có cách nhận đầu vào và trả lỗi khác nhau, nhưng cùng gọi một use case để bảo đảm quy tắc nghiệp vụ nhất quán.

Không đưa kiểu riêng của Spring Shell như `CommandContext`, `CommandOption` hoặc đối tượng terminal vào application service. Những kiểu này thuộc lớp giao diện CLI. Nếu service nhận chúng, service sẽ phụ thuộc vào Spring Shell và khó tái sử dụng ngoài CLI.

Thay vào đó, truyền kiểu dữ liệu nghiệp vụ hoặc request object:

```java
public record CreateProjectRequest(String name) {
}

public record ProjectSummary(String id, String name) {
}
```

Command chuyển đầu vào CLI thành `CreateProjectRequest`, gọi service và nhận `ProjectSummary`. Controller có thể tạo cùng request object từ JSON của REST API.

## 7. Khi một command cần phối hợp nhiều miền

Một số command không thuộc riêng một miền mà tổng hợp dữ liệu hoặc thực hiện quy trình đi qua nhiều miền. Ví dụ `dashboard summary` cần số project và số người dùng đang hoạt động.

Trong trường hợp đó, có thể tạo một application service dành cho use case tổng hợp:

```java
@Service
public class DashboardQueryService {

    private final ProjectApplicationService projects;
    private final UserApplicationService users;

    public DashboardQueryService(
            ProjectApplicationService projects,
            UserApplicationService users) {
        this.projects = projects;
        this.users = users;
    }

    public DashboardSummary loadSummary() {
        return new DashboardSummary(
            projects.countProjects(),
            users.countActiveUsers()
        );
    }
}
```

Lớp `DashboardCommands` chỉ cần gọi `DashboardQueryService` và trình bày `DashboardSummary`. Quy trình tổng hợp được đặt trong application layer nên có thể tái sử dụng từ một dashboard web hoặc tác vụ nền.

Không nên để `DashboardCommands` gọi `ProjectCommands.list()` hoặc `UserCommands.list()`. Phương thức command là adapter giao diện; gọi command này từ command khác khiến luồng nghiệp vụ phụ thuộc vào cách trình bày và có thể tạo vòng phụ thuộc giữa các lớp.

## 8. Phân biệt command group với tổ chức lớp Java

Spring Shell có metadata để nhóm command trong trợ giúp. Với API 4.x, `@CommandGroup` có thể đặt prefix và tên nhóm cho các command trong một lớp:

```java
@Component
@CommandGroup(prefix = "user", name = "User management")
public class UserCommands {

    @Command(name = "list", description = "Liệt kê người dùng")
    public String list() {
        // Gọi UserApplicationService
        return "Danh sách người dùng";
    }
}
```

Nhóm này giúp người dùng khám phá các lệnh như `user list`. Tuy nhiên, metadata nhóm và cấu trúc package/class là hai quyết định khác nhau:

- `@CommandGroup` điều khiển prefix và thông tin nhóm trong CLI.
- Package và tên lớp tổ chức mã nguồn cho người phát triển.
- Application service tổ chức use case và logic nghiệp vụ.
- Domain model thể hiện quy tắc và trạng thái nghiệp vụ.

Một lớp có thể được đặt trong package `command/project` và có `@CommandGroup(prefix = "project")`, nhưng Spring Shell không tự bảo đảm mọi command thuộc package đó đều nằm trong cùng một nhóm. Cần khai báo metadata theo API của phiên bản đang sử dụng.

Với Spring Shell 3.x, declarative `@Command` có thể đặt ở cấp lớp để khai báo prefix và group. Với 4.x, trách nhiệm này chuyển sang `@CommandGroup`; `@Command` chỉ đặt trên phương thức. Kiểm tra đúng API trước khi áp dụng ví dụ.

## 9. Đặt validation và xử lý lỗi đúng tầng

Tổ chức lớp command theo miền không có nghĩa mọi kiểm tra đều phải đặt trong command class. Hãy phân biệt:

| Loại kiểm tra | Nơi phù hợp | Ví dụ |
|---|---|---|
| Cú pháp và binding | Biên CLI / Spring Shell | Option có được truyền, chuỗi có chuyển thành số được không |
| Kiểm tra đầu vào sớm | Command adapter hoặc validator dùng chung | Chuỗi tên không rỗng, định dạng mã có đúng không |
| Quy tắc nghiệp vụ | Application service hoặc domain | Tên project có bị trùng, trạng thái hiện tại có cho phép lưu trữ không |
| Phân quyền | Lớp bảo mật và use case | Người dùng có quyền xóa project không |
| Trình bày lỗi | Command adapter | Chuyển lỗi thành thông báo ngắn, dễ hiểu cho terminal |

Một quy tắc nghiệp vụ phải được áp dụng dù use case được gọi từ CLI, REST API hay job. Vì vậy, không đặt kiểm tra duy nhất trong command method.

Command adapter có thể bắt exception đã được phân loại để chuyển thành thông báo phù hợp. Không nên sao chép cùng một khối xử lý lỗi ở mọi lớp command. Nếu cách chuyển đổi lỗi lặp lại nhiều lần, hãy dùng một thành phần trình bày hoặc cơ chế xử lý lỗi chung phù hợp với ứng dụng.

## 10. Chia sẻ thành phần trình bày có chọn lọc

Một số thao tác trình bày có thể lặp lại giữa các command, chẳng hạn định dạng bảng, ngày giờ hoặc danh sách. Có thể tạo formatter chuyên trách:

```java
import java.util.List;
import java.util.stream.Collectors;

import com.example.projectcli.application.project.ProjectSummary;
import org.springframework.stereotype.Component;

@Component
public class ProjectTableFormatter {

    public String format(List<ProjectSummary> projects) {
        if (projects.isEmpty()) {
            return "Chưa có project.";
        }

        return projects.stream()
            .map(project -> "%s | %s".formatted(
                project.id(),
                project.name()
            ))
            .collect(Collectors.joining(System.lineSeparator()));
    }
}
```

`ProjectCommands` có thể inject formatter này để giữ phần trình bày nhất quán. Formatter thuộc lớp giao diện, không nên trở thành nơi chứa truy vấn dữ liệu hoặc quy tắc nghiệp vụ.

Không nên tạo một lớp `CommonCommands` hoặc `Utils` khổng lồ chứa mọi hàm tiện ích. Hãy đặt thành phần dùng chung theo đúng trách nhiệm: formatter cho output, validator cho kiểm tra đầu vào có thể tái sử dụng, application service cho use case, và adapter cho tích hợp ngoài.

## 11. Dấu hiệu cho thấy cần tách hoặc gộp lớp

| Dấu hiệu | Hướng xử lý |
|---|---|
| Một lớp command có nhiều phương thức thuộc project và user, phụ thuộc vào nhiều service không liên quan | Tách thành các lớp theo miền |
| Nhiều command trong cùng miền dùng chung service và thay đổi cùng nhau | Giữ trong cùng lớp command |
| Một command cần phối hợp nhiều miền và có quy trình riêng | Tạo application service cho use case tổng hợp |
| Nhiều lớp command lặp cùng cách định dạng bảng | Tạo formatter dùng chung |
| Một lớp chỉ có một command rất đơn giản và không có nhóm liên quan | Có thể giữ lớp riêng hoặc gộp với lớp cùng trách nhiệm |
| Các command cùng tên miền nhưng có yêu cầu quyền hạn hoặc vòng đời rất khác nhau | Cân nhắc tách theo nhóm trách nhiệm hoặc khả năng quản lý |

Mục tiêu là giảm lý do thay đổi không liên quan trong cùng một lớp, đồng thời giữ các thao tác thường được tìm và phát triển cùng nhau ở gần nhau.

## 12. Kiểm thử theo ranh giới trách nhiệm

Khi tách command và application service, mỗi lớp có thể được kiểm thử ở mức phù hợp:

- **Application service:** kiểm tra quy tắc nghiệp vụ, phối hợp repository và hành vi khi dữ liệu không hợp lệ.
- **Command adapter:** kiểm tra command gọi đúng use case, chuyển đầu vào và tạo phản hồi CLI đúng.
- **Formatter:** kiểm tra output cho danh sách rỗng, dữ liệu bình thường và giá trị đặc biệt.
- **Tích hợp Spring Shell:** khởi tạo application context, xác nhận command được đăng ký và có thể gọi bằng tên dự kiến.

Không cần kiểm tra lại cùng một quy tắc nghiệp vụ ở mọi tầng. Service test xác minh quy tắc; kiểm thử command xác minh adapter nối CLI với service; kiểm thử tích hợp xác minh cấu hình đăng ký command.

Ví dụ, nếu đổi tên command từ `project list` sang `project ls`, kiểm thử ở lớp command hoặc tích hợp cần xác nhận tên mới được đăng ký và các alias cần duy trì vẫn hoạt động. Kiểm thử application service không cần quan tâm tên command.

## 13. Những lỗi tổ chức thường gặp

**Một lớp chứa mọi command.** Lớp nhanh chóng có quá nhiều phụ thuộc và nhiều lý do thay đổi. Chia theo miền nghiệp vụ hoặc nhóm use case có liên quan.

**Một lớp cho mỗi phương thức.** Cấu trúc quá vụn làm tăng số bean và khó tìm các command cùng ngữ cảnh. Gom những command có trách nhiệm liên quan.

**Command gọi command khác.** Điều này tạo phụ thuộc vào adapter CLI và dễ kéo theo logic trình bày. Chuyển use case dùng chung vào application service.

**Sao chép nghiệp vụ giữa các command.** Khi quy tắc thay đổi, các bản sao dễ không đồng nhất. Đặt quy tắc trong service hoặc domain.

**Command truy cập trực tiếp repository.** Lớp CLI bị gắn với lưu trữ và có thể bỏ qua use case, giao dịch hoặc quy tắc nghiệp vụ. Hãy gọi application service.

**Dùng CommandGroup thay cho thiết kế lớp.** Nhóm hiển thị trong trợ giúp không tạo ranh giới mã nguồn. Vẫn cần package và class có trách nhiệm rõ ràng.

**Tạo CommonService chứa mọi thứ.** Thành phần dùng chung không có một trách nhiệm rõ ràng sẽ trở thành điểm tập trung phụ thuộc. Tách service theo use case và miền.

**Đưa CommandContext vào application service.** Điều này làm nghiệp vụ phụ thuộc Spring Shell và khó tái sử dụng. Chuyển dữ liệu cần thiết thành request object hoặc kiểu miền.

**Trình bày dữ liệu miền trực tiếp.** Entity có thể chứa nhiều trường nội bộ hoặc quan hệ phức tạp. Dùng DTO hoặc projection phù hợp với output CLI.

## 14. Quy trình tổ chức command cho một miền mới

Khi bổ sung miền nghiệp vụ, có thể làm theo trình tự:

1. Xác định các thao tác mà người dùng cần thực hiện trong miền đó.
2. Nhóm các thao tác liên quan vào một lớp command.
3. Chọn prefix và tên nhóm trợ giúp phù hợp với quy ước CLI.
4. Định nghĩa application service cho từng use case cần thiết.
5. Đưa quy tắc nghiệp vụ và truy cập dữ liệu vào đúng tầng.
6. Inject service vào command bằng constructor injection.
7. Định dạng kết quả tại CLI hoặc formatter dùng chung.
8. Kiểm tra command đăng ký đúng, tên và alias không xung đột.
9. Kiểm thử service và command adapter ở đúng ranh giới.

Khi command mới cần phối hợp nhiều miền, hãy xác định đó là một use case tổng hợp và đặt phần điều phối trong application layer. Cách này giữ các lớp command độc lập và giúp quy trình được tái sử dụng.

## 15. Checklist thiết kế

- [ ] Các command được nhóm theo miền nghiệp vụ hoặc nhóm use case liên quan.
- [ ] Tên lớp và package giúp người phát triển tìm command dễ dàng.
- [ ] Mỗi lớp command có trách nhiệm và nhóm phụ thuộc rõ ràng.
- [ ] Command adapter chỉ xử lý đầu vào, gọi use case và trình bày kết quả.
- [ ] Quy tắc nghiệp vụ nằm trong application service hoặc domain.
- [ ] Nhiều command có thể dùng chung application service.
- [ ] Command không gọi trực tiếp phương thức command của lớp khác.
- [ ] Use case tổng hợp được tổ chức ở application layer.
- [ ] `CommandContext` và kiểu terminal không rò rỉ vào domain/application service.
- [ ] Formatter và validator dùng chung có trách nhiệm cụ thể.
- [ ] Metadata `@CommandGroup` và `@Command` khớp với phiên bản Spring Shell.
- [ ] Service và command adapter được kiểm thử theo ranh giới riêng.

## 16. Tài liệu tham khảo

- [Spring Shell 4 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html): mô hình đăng ký command và cách Spring Shell phát hiện command.
- [Spring Shell 4 — Command annotation API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html): metadata khai báo trên phương thức command.
- [Spring Shell 4 — CommandGroup API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/CommandGroup.html): prefix và metadata nhóm command.

Chia command theo miền nghiệp vụ giúp CLI có cấu trúc dễ hiểu khi số lượng chức năng tăng lên. Khả năng tái sử dụng đến từ việc đặt use case và quy tắc nghiệp vụ trong các application service độc lập với Spring Shell. Khi command class đóng vai trò adapter mỏng, cùng một nghiệp vụ có thể phục vụ nhiều lệnh và nhiều loại giao diện mà không cần sao chép logic.

