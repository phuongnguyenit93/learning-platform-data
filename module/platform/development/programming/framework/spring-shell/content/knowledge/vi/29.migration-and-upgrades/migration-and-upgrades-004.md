# Chuyển annotation legacy sang mô hình được phiên bản mới hỗ trợ

## 1. Vì sao cần chuyển khỏi annotation legacy?

Spring Shell 3.x có hai mô hình annotation cùng tồn tại. Mô hình legacy dùng `@ShellComponent`, `@ShellMethod` và `@ShellOption`. Mô hình annotation mới dùng `@Command` và `@Option`. Mô hình mới được giới thiệu từ các phiên bản Spring Shell 3.x để thống nhất cách khai báo command với `CommandRegistration` và chuẩn bị cho các thay đổi lớn ở Spring Shell 4.

Spring Shell 4 đã loại bỏ các annotation legacy. Những lớp hoặc method còn dùng `@ShellComponent`, `@ShellMethod`, `@ShellOption` và các annotation liên quan sẽ không biên dịch được sau khi nâng dependency lên 4.x. Ứng dụng cần chuyển sang `@Command`, `@Option`, `@Argument` và các annotation mới trong package `org.springframework.shell.core.command.annotation`.

Quá trình chuyển đổi có hai mốc cần phân biệt:

1. Chuyển từ annotation legacy sang annotation model mới ngay trên Spring Shell 3.4.x. Bước này giúp tách việc đổi mô hình command khỏi việc nâng major version.
2. Khi nâng lên Spring Shell 4.x, cập nhật package, tên thuộc tính và những thay đổi API mới của mô hình annotation.

Hướng dẫn migration chính thức khuyến nghị nâng ứng dụng lên bản Spring Shell 3.4.x mới nhất trước khi chuyển sang 4.x. Spring Shell 4 dựa trên Spring Framework 7 và hỗ trợ Spring Boot 4 trở lên.

## 2. Phân biệt ba thế hệ khai báo command

| Phiên bản/mô hình | Annotation trên bean | Annotation trên method | Annotation trên tham số |
|---|---|---|---|
| Legacy, Spring Shell 3.x | `@ShellComponent` | `@ShellMethod(key, value)` | `@ShellOption(value, defaultValue, ...)` |
| Annotation mới, Spring Shell 3.4 | `@Component`, có thể kết hợp class-level `@Command` | `@Command(command, description, ...)` | `@Option(longNames, shortNames, ...)` |
| Annotation mới, Spring Shell 4.x | `@Component` hoặc `@CommandGroup` | `@Command(name, description, ...)` | `@Option(longName, shortName, ...)`, `@Argument`, `@Arguments` |

Tên annotation `@Command` xuất hiện ở cả Spring Shell 3.4 và 4.x nhưng API không hoàn toàn giống nhau. Đừng chỉ đổi import rồi kỳ vọng source code giữ nguyên. Một số thuộc tính và cách nhóm command đã thay đổi giữa hai phiên bản.

## 3. Ghi nhận hành vi hiện tại trước khi sửa

Trước khi chuyển annotation, hãy lập danh sách command và ghi lại cú pháp người dùng đang sử dụng. Với mỗi command, kiểm tra:

- Tên chính, các alias và mô tả hiển thị trong `help`.
- Tên option, short option, alias option, giá trị mặc định và option bắt buộc.
- Tham số nào đang được hiểu là named option.
- Command nào có availability hoặc completion riêng.
- Command nào phụ thuộc trạng thái đăng nhập, cấu hình hoặc môi trường.
- Command nào chỉ chạy ở interactive mode hoặc chỉ dùng cho script.
- Exception và exit code mà script đang dựa vào.

Giữ một số lệnh mẫu làm kiểm thử hồi quy. Ví dụ, nếu trước khi chuyển đổi người dùng gọi `project create --name demo -p prod`, sau khi chuyển đổi cú pháp và kết quả cần giữ nguyên, trừ khi phiên bản mới yêu cầu bạn chủ động thay đổi contract.

## 4. Ví dụ legacy trong Spring Shell 3.x

Một command theo legacy annotation model có thể được khai báo như sau:

~~~java
package com.example.cli.commands;

import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class ProjectCommands {

    @ShellMethod(
            key = "project create",
            value = "Tạo một project mới")
    public String create(
            @ShellOption(value = { "--name", "-n" }) String name,
            @ShellOption(value = "--profile", defaultValue = "dev") String profile) {
        return "Created project " + name + " with profile " + profile;
    }
}
~~~

Trong ví dụ này:

- `@ShellComponent` vừa đánh dấu component Spring vừa chỉ ra bean có thể chứa shell method.
- `key` xác định tên command; `value` là mô tả dùng trong help.
- `@ShellOption` xác định tên option và giá trị mặc định.
- Hai tên `--name` và `-n` là hai cách gọi cùng một option.

Ở legacy model, tham số method được tự động ánh xạ thành option theo tên tham số nếu không khai báo `@ShellOption`. Đừng mặc định rằng tham số của `@ShellMethod` sẽ tự trở thành positional argument theo cú pháp `command value`.

## 5. Chuyển sang annotation model mới trên Spring Shell 3.4

Spring Shell 3.4 cho phép thay legacy annotations bằng `@Component`, `@Command` và `@Option` mà chưa cần nâng lên 4.x.

~~~java
package com.example.cli.commands;

import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ProjectCommands {

    @Command(
            command = "project create",
            description = "Tạo một project mới",
            group = "Project Commands")
    public String create(
            @Option(longNames = "name", shortNames = 'n', required = true) String name,
            @Option(longNames = "profile", defaultValue = "dev") String profile) {
        return "Created project " + name + " with profile " + profile;
    }
}
~~~

Điểm cần chú ý:

- Package annotation ở Spring Shell 3.4 là `org.springframework.shell.command.annotation`.
- `@Command` dùng thuộc tính `command`, chưa phải `name`.
- `@Option` dùng `longNames` và `shortNames`, cả hai là dạng mảng.
- `@ShellComponent` được thay bằng stereotype Spring thông thường như `@Component` hoặc `@Service`.
- Vì `@Option.required` mặc định là `false`, cần đặt `required = true` cho những option trước đây bắt buộc trong legacy command.

Mô hình annotation mới của Spring Shell 3.4 cần được kích hoạt bằng `@EnableCommand` hoặc `@CommandScan`, kể cả khi ứng dụng dùng Spring Boot. Ví dụ khai báo tường minh:

~~~java
import com.example.cli.commands.ProjectCommands;

import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.annotation.EnableCommand;

@Configuration
@EnableCommand(ProjectCommands.class)
public class ShellCommandConfiguration {
}
~~~

Có thể dùng `@CommandScan` để quét package thay vì liệt kê từng class. Đảm bảo class command vẫn là Spring bean và không bị loại khỏi component scan.

### 5.1. Vì sao nên có bước trung gian này?

Nếu chuyển legacy annotation sang mô hình mới khi vẫn ở Spring Shell 3.4, bạn có thể kiểm tra riêng các khác biệt về tên command, option, default value và availability. Khi những test này đã ổn định, bước nâng lên 4.x chủ yếu còn là cập nhật API và những thay đổi major version.

## 6. Chuyển package và tên thuộc tính khi nâng lên Spring Shell 4

Spring Shell 4 chuyển annotation model sang package `org.springframework.shell.core.command.annotation`.

| Spring Shell 3.4 | Spring Shell 4 |
|---|---|
| `org.springframework.shell.command.annotation.Command` | `org.springframework.shell.core.command.annotation.Command` |
| `org.springframework.shell.command.annotation.Option` | `org.springframework.shell.core.command.annotation.Option` |
| `org.springframework.shell.command.annotation.EnableCommand` | `org.springframework.shell.core.command.annotation.EnableCommand` |
| `@Command(command = "project create")` | `@Command(name = "project create")` |
| `@Option(longNames = "name")` | `@Option(longName = "name")` |
| `@Option(shortNames = 'n')` | `@Option(shortName = 'n')` |

Ví dụ import trong Spring Shell 4:

~~~java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Arguments;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;
import org.springframework.shell.core.command.annotation.EnableCommand;
import org.springframework.shell.core.command.annotation.Option;
~~~

`@Command` trong Spring Shell 4 chỉ được đặt trên method. Không tiếp tục dùng `@Command` ở cấp class như cách đặt prefix mặc định trong annotation model 3.4.

## 7. Chuyển class-level @Command sang @CommandGroup

Trong annotation model Spring Shell 3.4, có thể đặt `@Command` trên class để định nghĩa prefix và group chung cho các method command trong class đó:

~~~java
// Spring Shell 3.4
@Command(command = "project", group = "Project Commands")
@Component
public class ProjectCommands {

    @Command(command = "list", description = "Liệt kê project")
    public String list() {
        return "project-a, project-b";
    }

    @Command(command = "status", description = "Xem trạng thái project")
    public String status() {
        return "ready";
    }
}
~~~

Trong Spring Shell 4, `@Command` không còn hỗ trợ ở cấp class. Dùng `@CommandGroup` để khai báo prefix và tên nhóm:

~~~java
// Spring Shell 4.0.2+
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;
import org.springframework.stereotype.Component;

@Component
@CommandGroup(prefix = "project", name = "Project Commands")
public class ProjectCommands {

    @Command(name = "list", description = "Liệt kê project")
    public String list() {
        return "project-a, project-b";
    }

    @Command(name = "status", description = "Xem trạng thái project")
    public String status() {
        return "ready";
    }
}
~~~

Người dùng vẫn gọi `project list` và `project status`. `@CommandGroup` được bổ sung từ Spring Shell 4.0.2. Nếu ứng dụng đang ở 4.0.0 hoặc 4.0.1, hãy khai báo tên command đầy đủ trên từng method và đặt `group` trên từng `@Command` thay vì dùng `@CommandGroup`.

## 8. Chuyển tham số thành option hoặc positional argument có chủ đích

Đây là bước dễ làm thay đổi cú pháp nhất. Trong legacy model, tham số method thường được ánh xạ thành option theo tên. Trong mô hình mới Spring Shell 4, hai loại tham số được khai báo tường minh:

- `@Option` đại diện cho named option, ví dụ `--name demo` hoặc `-n demo`.
- `@Argument(index = 0)` đại diện cho positional argument, ví dụ `project show demo`.
- `@Arguments` thu thập nhiều positional argument vào array hoặc collection.

Ví dụ giữ nguyên tham số `--name` từ legacy command:

~~~java
@Command(name = "project create", description = "Tạo một project mới")
public String create(
        @Option(shortName = 'n', longName = "name", required = true) String name,
        @Option(longName = "profile", defaultValue = "dev") String profile) {
    return "Created project " + name + " with profile " + profile;
}
~~~

Người dùng gọi:

~~~bash
project create --name demo --profile prod
project create -n demo
~~~

Nếu muốn có cú pháp positional, hãy khai báo rõ ràng:

~~~java
@Command(name = "project show", description = "Xem thông tin project")
public String show(
        @Argument(index = 0, description = "Mã project") String projectId) {
    return "Project: " + projectId;
}
~~~

Người dùng gọi `project show demo`. Đây là thay đổi contract nếu trước đây command nhận `--project-id demo`; chỉ thực hiện khi đã quyết định thay đổi cú pháp và cập nhật script, tài liệu cũng như test.

Để nhận nhiều tên tệp hoặc nhiều ID:

~~~java
import java.util.List;
import org.springframework.shell.core.command.annotation.Arguments;

@Command(name = "project remove-files", description = "Xóa các tệp được chỉ định")
public String removeFiles(
        @Arguments(description = "Danh sách đường dẫn") List<String> paths) {
    return "Received " + paths.size() + " paths";
}
~~~

Đừng chuyển mọi tham số cũ thành `@Argument` chỉ vì tên annotation mới có chữ argument. Hãy kiểm tra cách người dùng đang gọi command và giữ named option bằng `@Option` nếu đó là hành vi cũ.

## 9. Rà soát required, default value và aliases

Các thuộc tính của `@ShellOption` không phải lúc nào cũng có ánh xạ một-một. Dùng bảng sau để rà soát:

| Legacy | Annotation mới 3.4 | Annotation mới 4.x | Lưu ý |
|---|---|---|---|
| `@ShellOption(value = "--name")` | `@Option(longNames = "name")` | `@Option(longName = "name")` | Bỏ tiền tố `--` khỏi tên trong annotation. |
| `@ShellOption(value = "-n")` | `@Option(shortNames = 'n')` | `@Option(shortName = 'n')` | Short name là một ký tự. |
| `@ShellOption(defaultValue = "dev")` | `@Option(defaultValue = "dev")` | `@Option(defaultValue = "dev")` | Kiểm tra kết quả khi người dùng bỏ qua option. |
| `@ShellOption` bắt buộc | `@Option(required = true)` | `@Option(required = true)` | `required` của mô hình mới mặc định là `false`. |
| `@ShellOption(defaultValue = ShellOption.NULL)` | `@Option(required = false)` | `@Option(required = false)` | Kiểm tra cách service xử lý giá trị vắng mặt. |
| `@ShellOption(value = { "--name", "-n" })` | `@Option(longNames = "name", shortNames = 'n')` | `@Option(longName = "name", shortName = 'n')` | 4.x chỉ nhận một long name và một short name cho mỗi option. |
| `@ShellMethod(key = { "project create", "project new" })` | `@Command(command = "project create", alias = "project new")` | `@Command(name = "project create", alias = "project new")` | Giữ một tên chính và chuyển các tên gọi thay thế thành command alias. |

Spring Shell 3.4 cho phép nhiều tên long/short trong `@Option`. Spring Shell 4 giới hạn một short name và một long name cho mỗi option. Nếu legacy command có nhiều alias cho cùng một option, hãy chọn một cặp tên chính và lập kế hoạch tương thích cho script đang dùng alias cũ.

Alias của command vẫn có thể khai báo bằng thuộc tính `alias` của `@Command`. Không nhầm alias command với alias của option.

Thuộc tính `label` của `@Option` trong mô hình 3.4 cũng đã bị loại bỏ ở 4.x. Nếu label chỉ dùng để trình bày trong help, hãy chuyển nội dung cần thiết sang `description` của option hoặc `help` của command; không dựa vào `label` để sắp xếp hay nhóm option.

## 10. Chuyển availability và completion

### Availability

Trong annotation model Spring Shell 3, availability có thể được khai báo bằng annotation riêng bên cạnh `@Command`:

~~~java
// Spring Shell 3.x annotation model
@Command(command = "download")
@CommandAvailability("loginAvailabilityProvider")
public void downloadCommand() {
    // Download logic
}
~~~

Trong Spring Shell 4, tên bean cung cấp availability được đặt ngay trên `@Command`:

~~~java
@Command(
        name = "download",
        availabilityProvider = "loginAvailabilityProvider")
public void downloadCommand() {
    // Download logic
}
~~~

Giữ nguyên bean availability và kiểm thử cả hai trạng thái: command khả dụng sau khi đăng nhập và command không khả dụng trước khi đăng nhập. `@Command` trong 4.x tập trung các tùy chỉnh command vào một nơi.

### Completion

Trong Spring Shell 3, `@OptionValues` có thể gắn provider vào một tham số option. Mô hình Spring Shell 4 chuyển sang completion provider ở cấp command qua `@Command(completionProvider = "...")`. Provider mới nhận completion context để có thể xem option hiện tại và các giá trị đã nhập, nhờ đó hỗ trợ gợi ý phụ thuộc lẫn nhau giữa nhiều option.

Khi chuyển completion:

1. Xác định các option đang có gợi ý riêng.
2. Gom logic gợi ý vào một `CompletionProvider` phù hợp với command.
3. Đăng ký provider thành Spring bean.
4. Gắn tên bean bằng `completionProvider` trên `@Command`.
5. Kiểm thử gợi ý cho từng option và từng tổ hợp giá trị đã nhập.

Không giữ `@OptionValues` trong source code 4.x; annotation này đã bị loại bỏ.

## 11. Những thay đổi liên quan đến command cần xử lý cùng lúc

Nâng major version còn tác động đến các API xung quanh command. Rà soát các mục sau nếu ứng dụng đang sử dụng chúng:

| API 3.x | Thay đổi ở 4.x |
|---|---|
| `@CommandAvailability` | Chuyển cấu hình vào `@Command(availabilityProvider = "...")`. |
| `@OptionValues` | Dùng `CompletionProvider` ở cấp command. |
| `InteractionMode` và cấu hình mode trên command | Bị loại bỏ; chọn interactive hoặc non-interactive mode khi khởi chạy shell. |
| `CommandExceptionResolver` | Thay bằng `ExitStatusExceptionMapper`. |
| `CommandHandlingResult` và `CommandExitCode` | Mô hình exit status mới dùng `ExitStatus`. |
| `@CommandScan` | Bị loại bỏ; Spring Boot tự bật command scanning. Ứng dụng không dùng Boot vẫn cần `@EnableCommand`. |
| Class-level `@Command` | Dùng `@CommandGroup` từ 4.0.2 hoặc khai báo tên đầy đủ trên từng method. |
| Nhiều short/long option names | Mỗi option trong 4.x chỉ có một short name và một long name. |

Ở Spring Shell 4, command không còn được đánh dấu riêng là interactive hoặc non-interactive. Ứng dụng chọn runner/mode khi khởi động; property `spring.shell.interactive.enabled=false` chuyển sang non-interactive mode. Vì vậy, hãy kiểm tra script tự động và phiên REPL sau khi nâng cấp.

Nếu ứng dụng tự xử lý exception và exit code, chuyển logic từ `CommandExceptionResolver` sang `ExitStatusExceptionMapper`. Test cần xác nhận mã thoát của các lỗi nghiệp vụ và lỗi hệ thống, vì script bên ngoài có thể đang phụ thuộc vào các mã đó.

## 12. Cập nhật module và package khi nâng lên Spring Shell 4

Không chỉ package annotation thay đổi. Spring Shell 4 cũng điều chỉnh cách chia module:

- `spring-shell-core` không còn phụ thuộc Spring Boot. Ứng dụng Spring Boot nên dùng starter Spring Shell hoặc khai báo `spring-shell-core-autoconfigure` phù hợp.
- `spring-shell-core` không còn phụ thuộc JLine. Nếu cần REPL dựa trên JLine, thêm `spring-shell-jline` hoặc starter cung cấp nó.
- `spring-shell-standard` và `spring-shell-standard-commands` được gộp vào `spring-shell-core`.
- `spring-shell-table` được gộp vào `spring-shell-jline`.
- `spring-shell-autoconfigure` đổi tên thành `spring-shell-core-autoconfigure`.
- API trong `org.springframework.shell` và `org.springframework.shell.standard` được chuyển vào các package con của `org.springframework.shell.core`.
- API bảng trong `org.springframework.shell.table` chuyển sang `org.springframework.shell.jline.tui.table`.

Nếu ứng dụng dùng starter, tránh thêm dependency cũ chỉ vì source code trước đây từng khai báo module riêng. Kiểm tra dependency tree để loại module đã gộp hoặc đổi tên, đồng thời xác nhận starter có cung cấp console provider mà ứng dụng mong đợi.

Nếu ứng dụng còn dùng programmatic registration qua `CommandRegistration` và `CommandCatalog`, đây là một nhánh migration riêng, không phải phép đổi annotation. Spring Shell 4 dùng `Command`/`Command.Builder` và `CommandRegistry` cho mô hình programmatic mới. Hãy kiểm kê và chuyển những registration này riêng, đồng thời giữ test cho command name, target, availability và exit status.

Với native image/GraalVM, migration guide ghi nhận annotation-based command registration chưa được hỗ trợ ở thời điểm Spring Shell 4.0.0; programmatic command model là hướng được hỗ trợ trong ghi chú đó. Nếu mục tiêu phát hành có native image, hãy xác minh tình trạng hỗ trợ của đúng bản Spring Shell đang dùng trước khi chọn mô hình khai báo.

## 13. Lộ trình migration theo từng bước

1. **Kiểm kê command:** ghi lại key, alias, options, default, availability, completion, interaction mode và exit code hiện tại.
2. **Nâng lên Spring Shell 3.4.x mới nhất:** xử lý deprecation và lỗi tương thích trước khi đổi major version.
3. **Chuyển legacy annotation sang annotation model 3.4:** đổi `@ShellComponent` thành `@Component`, `@ShellMethod` thành `@Command`, `@ShellOption` thành `@Option`; bật đăng ký bằng `@EnableCommand` hoặc `@CommandScan`.
4. **Chạy test hồi quy trên 3.4.x:** kiểm tra `help`, tên command, options, default value, validation, availability và completion.
5. **Nâng nền tảng lên Spring Boot 4 và Spring Shell 4:** cập nhật BOM, starter và các module theo dependency model mới.
6. **Chuyển package và thuộc tính:** đổi package annotation sang `org.springframework.shell.core.command.annotation`, `command` thành `name`, `longNames`/`shortNames` thành `longName`/`shortName`.
7. **Chuyển grouping và tham số:** thay class-level `@Command` bằng `@CommandGroup`; phân loại rõ named options và positional arguments.
8. **Chuyển extension point:** gom availability và completion theo API mới, cập nhật exception mapper và exit status nếu có.
9. **Kiểm tra runner và dependency:** chọn interactive/non-interactive mode, JLine provider và module phù hợp.
10. **Chạy test tích hợp và smoke test:** thực thi command từ terminal, script, CI và môi trường triển khai thực tế.

Không gộp tất cả thay đổi vào một commit lớn nếu ứng dụng có nhiều command. Chuyển theo nhóm chức năng giúp xác định nhanh command nào thay đổi hành vi và giảm rủi ro khi rollback.

## 14. Kiểm thử sau khi chuyển đổi

Một bộ kiểm thử migration nên xác nhận contract trước và sau khi nâng cấp:

| Nhóm kiểm tra | Điều cần xác nhận |
|---|---|
| Registration | Mọi command nghiệp vụ được phát hiện; không có command bị đăng ký hai lần. |
| Command name | Tên chính và alias vẫn hoạt động. |
| Help | Description, group, help text và option được hiển thị đúng. |
| Required option | Thiếu option bắt buộc tạo lỗi như trước. |
| Default value | Bỏ qua option vẫn cho giá trị mặc định đúng. |
| Option alias | Short/long name được giữ hoặc có kế hoạch thay thế alias cũ. |
| Positional argument | `@Argument` có index đúng; không làm thay đổi cú pháp named option cũ. |
| Multi-value input | `@Arguments` nhận đủ số token theo thiết kế. |
| Validation | Constraint vẫn được thực thi trước khi gọi service. |
| Availability | Command bật/tắt theo trạng thái nghiệp vụ. |
| Completion | Gợi ý đúng với từng option và tổ hợp giá trị. |
| Exception/exit status | Message và exit code đúng cho script. |
| Execution mode | REPL và non-interactive runner khởi động đúng theo cấu hình. |
| Packaging | Executable JAR khởi động được trên JDK và Spring Boot mục tiêu. |

Ngoài unit test cho từng command, hãy chạy integration test qua shell test client hoặc khởi động JAR thật rồi gọi các lệnh quan trọng. Một command có thể compile thành công nhưng không được đăng ký do thiếu component scan hoặc cấu hình enable.

## 15. Lỗi migration thường gặp

**Chỉ đổi import nhưng giữ `key` hoặc `command`:** `@Command` của 4.x dùng `name`. Đổi cả package và thuộc tính.

**Giữ `@Command` ở class:** Spring Shell 4 chỉ cho phép `@Command` trên method. Dùng `@CommandGroup` hoặc đặt tên đầy đủ trên từng method.

**Quên đổi `@ShellComponent`:** annotation legacy đã bị loại bỏ. Dùng `@Component` hoặc stereotype Spring phù hợp.

**Dùng `longNames`/`shortNames` trên 4.x:** đây là tên thuộc tính của `@Option` trong 3.4. 4.x dùng `longName` và `shortName` dạng đơn.

**Đặt `required` sai:** `@Option` mới mặc định không bắt buộc. Nếu option cũ bắt buộc, đặt `required = true` và kiểm thử trường hợp bỏ qua option.

**Biến named option thành positional argument:** tham số legacy thường được ánh xạ theo tên option. Chỉ dùng `@Argument` khi chủ đích thay đổi cú pháp gọi command.

**Quên đăng ký command trong ứng dụng không dùng Boot:** `@EnableCommand` vẫn cần thiết. Spring Boot 4 tự cấu hình scan; `@CommandScan` đã bị loại bỏ.

**Dùng completion hoặc availability API cũ:** chuyển `@OptionValues` sang `CompletionProvider`, và chuyển availability vào thuộc tính `availabilityProvider` của `@Command`.

**Cho rằng compile thành công nghĩa là migration hoàn tất:** cần kiểm tra help, completion, runner, exit code và command thực thi trong môi trường thật.

## 16. Checklist hoàn tất migration

- [ ] Ứng dụng đã nâng lên Spring Shell 3.4.x mới nhất trước khi chuyển major version.
- [ ] Không còn `@ShellComponent`, `@ShellMethod` hoặc `@ShellOption` trong source code dành cho Spring Shell 4.
- [ ] Các class command được Spring quản lý bằng `@Component`, `@Service` hoặc `@CommandGroup`.
- [ ] Mọi method command dùng `@Command(name = ...)`.
- [ ] Tham số named option dùng `@Option(longName, shortName, ...)`.
- [ ] Positional argument chỉ dùng khi đã xác định rõ cú pháp mới.
- [ ] Class-level prefix/group đã chuyển sang `@CommandGroup` hoặc tên command đầy đủ.
- [ ] Registration phù hợp: Boot 4 tự scan; ứng dụng không dùng Boot có `@EnableCommand`.
- [ ] Availability, completion, exception mapping và exit status đã chuyển API.
- [ ] Interactive/non-interactive runner được cấu hình và kiểm thử.
- [ ] Dependency tree không còn module cũ đã bị gộp hoặc đổi tên.
- [ ] Test hồi quy xác nhận command name, option, help và kết quả không đổi ngoài chủ đích.
- [ ] JAR hoặc artifact phát hành chạy được trên môi trường mục tiêu.

## Kết luận

Để chuyển annotation legacy sang mô hình được Spring Shell phiên bản mới hỗ trợ, hãy đi qua annotation model mới của Spring Shell 3.4 trước, sau đó mới nâng lên 4.x. Legacy `@ShellComponent`, `@ShellMethod` và `@ShellOption` được thay bằng bean Spring thông thường, `@Command` và `@Option`. Khi lên 4.x, chuyển package sang `org.springframework.shell.core.command.annotation`, đổi `command` thành `name`, đổi `longNames`/`shortNames` thành `longName`/`shortName`, và dùng `@CommandGroup` thay cho class-level `@Command`. Cuối cùng, xác nhận lại options, positional arguments, registration, availability, completion, runner và exit status bằng test hồi quy.

## Tài liệu tham khảo

- [Spring Shell – v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Spring Shell 3.4 – Reading Docs: Legacy và annotation model mới](https://docs.spring.io/spring-shell/reference/3.4/basics/reading.html)
- [Spring Shell 3.4 API – Command annotation](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/annotation/Command.html)
- [Spring Shell 3.4 API – Option annotation](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/annotation/Option.html)
- [Spring Shell 3.4 API – EnableCommand](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/annotation/EnableCommand.html)
- [Spring Shell 4 – Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html)
- [Spring Shell 4 – Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell 4 – Organizing Commands](https://docs.spring.io/spring-shell/reference/commands/organize.html)
- [Spring Shell 4 API – Command](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)
- [Spring Shell 4 API – CommandGroup](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/CommandGroup.html)
- [Spring Shell 4 API – Option](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html)
- [Spring Shell 4 API – Argument](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Argument.html)
- [Spring Shell 4 API – Arguments](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Arguments.html)
