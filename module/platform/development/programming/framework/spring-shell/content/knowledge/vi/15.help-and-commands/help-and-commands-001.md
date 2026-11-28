# Lệnh help và cách khám phá nhóm lệnh

Trong một ứng dụng dòng lệnh, người dùng thường không nhớ hết tên command, option, argument và cách gọi từng chức năng. Spring Shell cung cấp command tích hợp **help** để tự khám phá giao diện của ứng dụng mà không cần mở tài liệu bên ngoài.

Người dùng có thể nhập **help** để xem danh sách command, nhập **help COMMAND** để đọc trợ giúp chi tiết, hoặc thêm **--help** hay **-h** sau command đang muốn tìm hiểu. Danh sách được tổ chức theo nhóm để người dùng nhận ra các chức năng liên quan. Mỗi command nên có mô tả ngắn và phần help chi tiết để giải thích cách sử dụng.

Bài này sử dụng mô hình command của Spring Shell 4.x. Trong dòng 4, **@Command** đánh dấu method command; **@CommandGroup** gom các method trong cùng class và có thể đặt prefix chung. Phân biệt nhóm hiển thị với prefix gọi lệnh là chìa khóa để thiết kế một CLI dễ khám phá.

## 1. Ba cách khám phá trợ giúp

Spring Shell cung cấp ba cách phổ biến để tìm hiểu command:

| Cách gọi | Mục đích | Khi nên dùng |
|---|---|---|
| **help** | Liệt kê các command đã đăng ký cùng mô tả ngắn | Chưa biết ứng dụng có chức năng nào |
| **help COMMAND** | Hiển thị hướng dẫn chi tiết của command | Muốn xem cú pháp, option, argument và alias |
| **COMMAND --help** hoặc **COMMAND -h** | Mở trợ giúp ngay từ command đang tìm hiểu | Đang biết tên lệnh nhưng chưa rõ cách gọi |

Ví dụ:

~~~text
help
help help
help version
version --help
version -h
~~~

Lệnh **help** là command tích hợp của Spring Shell. Khi nhập riêng **help**, shell hiển thị danh sách command mà registry đang quản lý và mô tả ngắn của từng command. Khi truyền tên command, phần trợ giúp chi tiết mô tả command làm gì, nhận tham số nào, kiểu dữ liệu gì và tham số có bắt buộc hay không.

Từ Spring Shell 4.0.4, **CommandHelpRenderer** tạo nội dung trợ giúp chi tiết dùng chung cho **help COMMAND** và option **--help** ngầm định của command. Nhờ vậy, hai cách gọi hiển thị cùng một cấu trúc help.

## 2. Hiểu cấu trúc trang trợ giúp chi tiết

Một trang help chi tiết thường có các phần:

| Phần | Nội dung |
|---|---|
| **NAME** | Tên command và mô tả ngắn |
| **DESCRIPTION** | Phần hướng dẫn dài hơn nếu command khai báo help |
| **SYNOPSIS** | Cú pháp gọi command, option và argument |
| **OPTIONS** | Tên option, kiểu dữ liệu, mô tả và tính bắt buộc |
| **ARGUMENTS** | Các positional argument, kiểu và mô tả |
| **ALIASES** | Tên gọi thay thế của command nếu có |

Ví dụ minh họa:

~~~text
NAME
    export - Xuất dữ liệu theo định dạng được chọn

DESCRIPTION
    Xuất các bản ghi trong khoảng thời gian chỉ định.
    Có thể chọn định dạng JSON hoặc CSV để tích hợp với hệ thống khác.

SYNOPSIS
    export --from LocalDate --to LocalDate [--format String]

OPTIONS
    --from LocalDate
        Ngày bắt đầu, định dạng yyyy-MM-dd
        [Required]

    --to LocalDate
        Ngày kết thúc, định dạng yyyy-MM-dd
        [Required]

    --format String
        Định dạng đầu ra: json hoặc csv
        [Optional]
~~~

Đây là ví dụ về hình thức nội dung; cách căn lề và cách ghi trạng thái bắt buộc có thể thay đổi theo template của phiên bản. Người dùng nên đọc phần synopsis trước để biết cách gọi, sau đó xem mô tả từng option và argument.

## 3. Viết mô tả ngắn và help chi tiết cho command

Spring Shell 4 cung cấp hai thuộc tính quan trọng trong **@Command**:

- **description**: mô tả ngắn, dùng trong danh sách command.
- **help**: hướng dẫn dài hơn, xuất hiện trong phần DESCRIPTION của help chi tiết.

Không nên dùng cùng một câu dài cho cả hai. Description cần ngắn để người dùng quét danh sách nhanh; help có thể giải thích mục đích, thứ tự thao tác, ví dụ và giới hạn.

~~~java
import java.time.LocalDate;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ExportCommands {

    @Command(
            name = "export",
            description = "Xuất dữ liệu theo định dạng được chọn.",
            help = """
                    Xuất các bản ghi trong khoảng thời gian chỉ định.
                    Dùng --from và --to theo định dạng yyyy-MM-dd.
                    Chọn --format=json hoặc --format=csv.

                    Ví dụ:
                    export --from=2026-01-01 --to=2026-01-31 --format=csv
                    """
    )
    public String export(
            @Option(longName = "from", required = true) LocalDate from,
            @Option(longName = "to", required = true) LocalDate to,
            @Option(longName = "format", defaultValue = "json") String format) {

        return "Đang xuất dữ liệu từ " + from + " đến " + to
                + " theo định dạng " + format;
    }
}
~~~

Người dùng có thể khám phá command:

~~~text
help
help export
export --help
~~~

Trong ví dụ, **description** trả lời nhanh câu hỏi "lệnh này làm gì?". **help** giải thích thêm cách dùng và đưa ra ví dụ có thể sao chép. Các annotation trên tham số cho Spring Shell biết option nào bắt buộc, kiểu nào được nhận và giá trị mặc định là gì; help có thể dựa vào metadata đó để hiển thị synopsis và danh sách tham số.

Một help hữu ích nên trả lời được:

1. Command thực hiện công việc gì?
2. Người dùng cần cung cấp dữ liệu nào?
3. Định dạng đầu vào ra sao?
4. Có giá trị mặc định nào không?
5. Có tác động nào cần xác nhận hoặc điều kiện nào phải đáp ứng?
6. Có ví dụ gọi lệnh hoàn chỉnh không?

## 4. Gom command theo nhóm với @CommandGroup

Khi ứng dụng có nhiều command, danh sách phẳng khiến người dùng khó tìm chức năng. **@CommandGroup** gom các command liên quan vào cùng một nhóm. Annotation này được đặt trên class chứa các method command.

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
@CommandGroup(
        name = "Quản lý người dùng",
        prefix = "user",
        description = "Các thao tác quản lý tài khoản người dùng."
)
class UserCommands {

    @Command(
            name = "list",
            description = "Liệt kê người dùng.",
            help = "Hiển thị danh sách người dùng. Có thể lọc theo trạng thái."
    )
    public String list(
            @Option(longName = "active-only", defaultValue = "true")
            boolean activeOnly) {
        return "Danh sách người dùng, activeOnly=" + activeOnly;
    }

    @Command(
            name = "create",
            description = "Tạo người dùng mới.",
            alias = {"add", "new"},
            help = "Tạo một tài khoản mới từ tên người dùng được cung cấp."
    )
    public String create(
            @Option(longName = "name", required = true) String name) {
        return "Đã tạo người dùng " + name;
    }
}
~~~

Trong ví dụ:

- **name** đặt tên nhóm hiển thị trong help.
- **description** mô tả phạm vi của nhóm.
- **prefix** đặt tiền tố chung cho tên command.
- Các method **list** và **create** trở thành command **user list** và **user create**.

Người dùng có thể gọi:

~~~text
help
user list
user create --name=An
user add --name=An
user list --help
~~~

Alias **add** và **new** là các tên gọi thay thế của command **user create**. Help chi tiết có thể hiển thị alias để người dùng biết các cách gọi được hỗ trợ.

Danh sách help có thể trình bày nhóm theo dạng minh họa:

~~~text
AVAILABLE COMMANDS

Built-In Commands
    help: Show help about available commands
    clear: Clear the terminal screen
    version: Show version info

Quản lý người dùng
    user list: Liệt kê người dùng
    user create: Tạo người dùng mới
~~~

Tên nhóm giúp người dùng quét theo chức năng; tên command và description ngắn cho biết thao tác cụ thể trong nhóm đó.

**@CommandGroup** có từ Spring Shell 4.0.2. Trong Spring Shell 4, **@Command** chỉ đánh dấu method; **@CommandGroup** đánh dấu class và gom các method command thuộc class đó.

## 5. Phân biệt group và prefix

**Group** và **prefix** thường được khai báo cùng nhau nhưng có chức năng khác nhau:

| Thuộc tính | Tác dụng | Ảnh hưởng đến cú pháp gọi |
|---|---|---|
| **group** | Nhóm command trong danh sách help | Không tự thêm token vào tên command |
| **prefix** | Thêm phần đầu vào tên command | Có, người dùng phải nhập prefix |

Ví dụ khai báo:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class StatusCommands {

    @Command(name = "status", group = "Vận hành")
    public String status() {
        return "Hệ thống đang hoạt động";
    }
}
~~~

Command được xếp vào nhóm **Vận hành**, nhưng tên gọi vẫn là **status**.

Trong khi đó:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;
import org.springframework.stereotype.Component;

@Component
@CommandGroup(name = "Vận hành", prefix = "ops")
class OperationsCommands {

    @Command(name = "status", description = "Kiểm tra trạng thái hệ thống.")
    public String status() {
        return "Hệ thống đang hoạt động";
    }
}
~~~

Command có tên gọi **ops status**. Prefix là một phần của cú pháp, còn group là nhãn tổ chức trong help. Nếu một method khai báo **group** riêng, giá trị đó được ưu tiên cho command đó thay cho tên nhóm khai báo ở class; prefix của nhóm vẫn là quy tắc đặt tên.

## 6. Dùng global prefix trong Spring Shell 4.0.4

Khi muốn đặt namespace chung cho toàn bộ command do annotation khai báo, Spring Shell 4.0.4 bổ sung thuộc tính cấu hình **spring.shell.command.prefix**:

~~~yaml
spring:
  shell:
    command:
      prefix: myapp
~~~

Giả sử một class có:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class GeneralCommands {

    @Command(name = "status", description = "Kiểm tra trạng thái.")
    public String status() {
        return "OK";
    }
}
~~~

Command có thể được gọi dưới tên **myapp status**. Nếu class còn có **@CommandGroup(prefix = "user")**, prefix toàn cục và prefix nhóm được nối theo thứ tự:

~~~text
myapp user list
~~~

Global prefix chỉ áp dụng cho các method command do annotation khai báo. Các command tích hợp sẵn như **help**, **clear**, **version** và các bean **Command** được đăng ký bằng programmatic model không bị thay đổi bởi thuộc tính này.

Không nên chọn tên global prefix trùng với command tích hợp như **help**, **clear**, **version**, **script**, **history**, **exit** hoặc **quit**. Khi đó, tên command có prefix có thể làm cách gọi command tích hợp kèm đối số trở nên mơ hồ.

## 7. Tổ chức command bằng thuộc tính group ở method

Không bắt buộc mọi command trong một class phải thuộc cùng một nhóm. Có thể ghi đè group cho một method:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;
import org.springframework.stereotype.Component;

@Component
@CommandGroup(name = "Quản trị", prefix = "admin")
class AdministrationCommands {

    @Command(
            name = "users",
            description = "Quản lý tài khoản.",
            group = "Quản lý danh tính"
    )
    public String users() {
        return "Các thao tác tài khoản";
    }

    @Command(
            name = "health",
            description = "Kiểm tra sức khỏe dịch vụ."
    )
    public String health() {
        return "Tất cả dịch vụ đang hoạt động";
    }
}
~~~

Command **admin users** xuất hiện trong nhóm **Quản lý danh tính**. Command **admin health** sử dụng nhóm **Quản trị** của class. Nhờ vậy, một class có thể giữ các method liên quan về mặt triển khai nhưng help vẫn tổ chức chúng theo góc nhìn của người dùng.

Khi quyết định nhóm, hãy đặt tên theo công việc người dùng muốn hoàn thành, chẳng hạn **Quản lý người dùng**, **Triển khai**, **Giám sát** hoặc **Báo cáo**. Tránh đặt nhóm theo tên package hoặc tên class kỹ thuật nếu những tên đó không giúp người dùng hiểu chức năng.

## 8. Alias giúp người dùng khám phá cách gọi thay thế

Alias cho phép một command có nhiều tên gọi. Trong Spring Shell 4, thuộc tính **alias** của **@Command** nhận một hoặc nhiều tên:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ResourceCommands {

    @Command(
            name = "remove",
            description = "Xóa một tài nguyên.",
            alias = {"delete", "rm"},
            help = "Xóa tài nguyên theo mã định danh."
    )
    public String remove(@Option(longName = "id", required = true) String id) {
        return "Đã xóa tài nguyên " + id;
    }
}
~~~

Người dùng có thể gọi:

~~~text
remove --id=asset-10
delete --id=asset-10
rm --id=asset-10
~~~

Alias nên ngắn, dễ nhớ và có ý nghĩa tương đương với tên chính. Không dùng alias để tạo các hành vi khác nhau cho cùng một command. Nếu hành vi khác nhau, hãy tạo command riêng để help mô tả chính xác.

Alias cũng có ích khi đổi tên command. Có thể giữ tên cũ như alias trong một giai đoạn chuyển tiếp, cập nhật help để thông báo tên mới rồi loại bỏ alias cũ theo chính sách tương thích.

## 9. Ẩn command khỏi danh sách khám phá

Thuộc tính **hidden** trong **@Command** cho phép đánh dấu command không cần xuất hiện trong danh sách trợ giúp thông thường:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class DiagnosticCommands {

    @Command(
            name = "debug-dump",
            description = "Xuất thông tin chẩn đoán nội bộ.",
            hidden = true
    )
    public String debugDump() {
        return "Thông tin chẩn đoán";
    }
}
~~~

Hidden phù hợp với command hỗ trợ, command chẩn đoán hoặc command chưa muốn quảng bá rộng rãi. Đây chỉ là cách điều chỉnh khả năng khám phá trong giao diện CLI. Ẩn command không thay thế xác thực và phân quyền; nếu command có thể truy cập hoặc thay đổi dữ liệu nhạy cảm, service vẫn phải kiểm tra quyền trước khi thực hiện.

Không nên ẩn một command thông thường chỉ vì help chưa được viết tốt. Hãy hoàn thiện description và help để người dùng có thể tự tìm hiểu. Ẩn chỉ nên dùng khi có lý do rõ ràng về trải nghiệm hoặc vận hành.

## 10. Khám phá command theo Availability và Completion

Help và completion giải quyết hai nhu cầu khác nhau:

- **help** cho biết command nào tồn tại, command làm gì và cú pháp ra sao.
- **completion** gợi ý token tiếp theo khi người dùng đang gõ lệnh trong shell tương tác dựa trên JLine.
- **AvailabilityProvider** cho biết command có thể thực thi trong trạng thái hiện tại hay không.

Ví dụ, command **download** có thể được đăng ký và hiển thị trong danh sách help nhưng chỉ thực thi sau khi đăng nhập. Help giúp người dùng biết command tồn tại; availability giải thích điều kiện để chạy; completion giúp người dùng nhập tên command và option nhanh hơn.

Không dùng hidden để biểu diễn trạng thái chưa sẵn sàng nếu người dùng cần biết command tồn tại và lý do chưa thể chạy. Trong trường hợp đó, giữ command trong registry và dùng availability provider để mô tả điều kiện.

## 11. Định nghĩa help cho command tạo bằng mã

Nếu ứng dụng đăng ký command bằng programmatic model, **Command.Builder** cũng có các thuộc tính để cung cấp metadata cho help:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;

@Configuration
class ReportCommandConfiguration {

    @Bean
    Command reportSummaryCommand() {
        return Command.builder()
                .name("report-summary")
                .group("Báo cáo")
                .description("Hiển thị tổng quan báo cáo.")
                .help("""
                        Hiển thị số lượng báo cáo theo trạng thái.
                        Command này không thay đổi dữ liệu.
                        """)
                .aliases("rpt-summary")
                .execute(context -> "Có 12 báo cáo đang chờ xử lý");
    }
}
~~~

Command được đăng ký trong registry và có metadata để help hiển thị. Vì vậy, dù dùng annotation model hay programmatic model, hãy cung cấp tên, nhóm, mô tả và hướng dẫn đầy đủ.

## 12. Tổ chức help cho ứng dụng có nhiều module

Một CLI lớn nên được thiết kế từ góc nhìn người dùng. Ví dụ một ứng dụng quản lý nền tảng có thể chia nhóm:

| Nhóm | Prefix gợi ý | Command mẫu |
|---|---|---|
| Quản lý người dùng | **user** | **user list**, **user create**, **user disable** |
| Quản lý dự án | **project** | **project list**, **project create**, **project archive** |
| Triển khai | **deploy** | **deploy start**, **deploy status**, **deploy rollback** |
| Giám sát | **monitor** | **monitor health**, **monitor metrics** |
| Báo cáo | **report** | **report generate**, **report export** |

Người dùng có thể bắt đầu bằng **help**, chọn nhóm theo nhiệm vụ, đọc mô tả command rồi gọi **--help** để xem tham số. Một prefix ngắn giúp cú pháp nhất quán; một group name dễ hiểu giúp danh sách trợ giúp dễ quét.

Tránh tạo quá nhiều nhóm nhỏ chỉ có một command nếu chúng không thể hiện một phạm vi chức năng riêng. Cũng tránh dồn mọi command vào một nhóm chung như **Other** hoặc **General**. Mỗi nhóm nên trả lời được câu hỏi: người dùng vào đây để hoàn thành loại công việc nào?

## 13. Khác biệt quan trọng giữa Spring Shell 3.x và 4.x

Khi chuyển code từ 3.x sang 4.x, cách tổ chức command group thay đổi:

| Spring Shell 3.x | Spring Shell 4.x |
|---|---|
| Có thể đặt **@Command** trên class để định nghĩa nhóm/prefix | Dùng **@CommandGroup** trên class |
| **@Command** có thể xuất hiện trên class và method theo mô hình cũ | **@Command** đánh dấu method command |
| Các tùy chỉnh command được chia qua nhiều annotation | Nhiều thuộc tính như **description**, **help**, **group**, **alias**, **hidden** nằm trong **@Command** |
| Group và prefix có thể được khai báo theo cơ chế cũ | **@CommandGroup(name, prefix)** gom method và tạo namespace |

Ví dụ chuyển đổi:

~~~java
// Mô hình cũ 3.x
@Command(command = "github auth", group = "GitHub Authentication")
class GitHubCommands {

    @Command(command = "login")
    public void login() {
    }
}
~~~

~~~java
// Mô hình 4.x
@Component
@CommandGroup(name = "GitHub Authentication", prefix = "github auth")
class GitHubCommands {

    @Command(name = "login", description = "Đăng nhập GitHub.")
    public void login() {
    }
}
~~~

Khi chuyển đổi, không giữ annotation class-level **@Command** của mô hình 3.x. Hãy chuyển metadata nhóm sang **@CommandGroup** và giữ **@Command** trên từng method.

Spring Shell 4.0.4 cũng sửa các lỗi liên quan đến help, bao gồm sự không nhất quán giữa **command --help** và **help command**, thiếu thông tin argument, cách hiển thị dấu ngoặc trong synopsis và nhận diện help khi command có option riêng. Nếu ứng dụng nâng từ bản 4.0.x cũ, hãy kiểm tra lại output help sau khi cập nhật.

## 14. Lỗi thường gặp khi thiết kế help

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Danh sách help có quá nhiều command | Không tổ chức group hoặc prefix | Gom command theo nhiệm vụ bằng **@CommandGroup** |
| Người dùng không hiểu command làm gì | Description quá ngắn, mơ hồ hoặc để trống | Viết mô tả bắt đầu bằng động từ và nêu kết quả |
| Help chi tiết không có hướng dẫn sử dụng | Chưa khai báo **help** | Bổ sung mục đích, cú pháp và ví dụ |
| Người dùng nhập sai option | Help không giải thích kiểu và định dạng | Khai báo option rõ ràng và bổ sung ví dụ |
| Prefix bị nhầm với group | Dùng group như thể nó thay đổi tên command | Nhớ rằng group chỉ tổ chức help; prefix thay đổi cú pháp gọi |
| Không gọi được command sau khi thêm prefix | Người dùng vẫn nhập tên cũ | Cập nhật ví dụ và tài liệu theo tên đầy đủ |
| Command bị ẩn ngoài ý muốn | Đặt **hidden = true** | Kiểm tra metadata của command |
| Người dùng dùng alias cũ không rõ hành vi | Alias không được mô tả hoặc có ý nghĩa khác tên chính | Chỉ tạo alias tương đương và kiểm tra trong help |
| Help và --help hiển thị khác nhau trên bản cũ | Lỗi ở phiên bản Spring Shell trước 4.0.4 | Nâng bản vá phù hợp và kiểm tra lại |
| Command nhạy cảm chỉ được ẩn | Nhầm hidden với phân quyền | Kiểm tra quyền ở application/domain service |

## 15. Kiểm thử khả năng khám phá command

Help là một phần của giao diện sản phẩm nên cần được kiểm thử như một hành vi người dùng:

1. **Danh sách command:** nhập **help**, xác nhận command và mô tả xuất hiện đúng nhóm.
2. **Help chi tiết:** nhập **help COMMAND**, xác nhận NAME, DESCRIPTION, SYNOPSIS, OPTIONS, ARGUMENTS và ALIASES phù hợp.
3. **Option help:** nhập **COMMAND --help** và **COMMAND -h**, xác nhận nội dung nhất quán với help command.
4. **Command group:** xác nhận command thuộc đúng group và prefix được ghép đúng.
5. **Alias:** gọi command bằng tên chính và alias, xác nhận cùng hành vi.
6. **Hidden:** xác nhận command ẩn không xuất hiện trong danh sách khám phá thông thường; kiểm tra quyền riêng nếu command có tác động nhạy cảm.
7. **Global prefix:** xác nhận command annotation có prefix toàn cục, còn built-in command vẫn gọi bằng tên mặc định.
8. **Metadata tham số:** kiểm tra kiểu dữ liệu, trạng thái bắt buộc/tùy chọn, giá trị mặc định và mô tả.
9. **Không có help text:** command vẫn hiển thị synopsis và metadata tham số cần thiết.
10. **Nâng phiên bản:** so sánh output trước và sau khi cập nhật Spring Shell, đặc biệt với command có nhiều argument hoặc option.

Nên có ít nhất một kiểm thử tích hợp dùng **ShellTestClient** để chạy thật các lệnh help. Unit test cho method command không đủ để xác nhận renderer, registry và metadata phối hợp đúng.

## 16. Quy trình khám phá dành cho người dùng CLI

Một người mới có thể tự làm quen ứng dụng theo trình tự:

1. Gõ **help** để xem các nhóm chức năng.
2. Chọn nhóm phù hợp với công việc cần làm.
3. Đọc mô tả ngắn để tìm command phù hợp.
4. Gõ **help COMMAND** hoặc **COMMAND --help** để xem cú pháp.
5. Kiểm tra option bắt buộc, kiểu dữ liệu và ví dụ.
6. Nếu cần, dùng alias đã được công bố để gọi command nhanh hơn.
7. Trong shell tương tác có JLine, nhấn Tab để nhận gợi ý tên command và option.

Một CLI tốt giúp người dùng tự tìm được command mà không cần ghi nhớ toàn bộ danh sách lệnh. Nhóm rõ ràng, description ngắn gọn, help chi tiết và prefix nhất quán tạo thành một giao diện có thể tự khám phá.

## Tài liệu tham khảo

- [Spring Shell — Built-in Help](https://docs.spring.io/spring-shell/reference/commands/builtin/help.html) — lệnh help, danh sách command, help chi tiết và cách dùng -h/--help.
- [Spring Shell — Organizing Commands](https://docs.spring.io/spring-shell/reference/commands/organize.html) — group, **@CommandGroup**, prefix và global command prefix.
- [Spring Shell 4.0.4 API — Command annotation](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html) — **description**, **help**, **group**, **alias** và **hidden**.
- [Spring Shell 4.0.4 API — CommandGroup annotation](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/CommandGroup.html) — tên nhóm, mô tả nhóm và prefix.
- [Spring Shell 4.0.4 API — CommandHelpRenderer](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandHelpRenderer.html) — cấu trúc help chi tiết dùng chung cho help command và option help.
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) — thay đổi từ class-level **@Command** sang **@CommandGroup**.
- [Spring Shell 4.0.4 Release Notes](https://github.com/spring-projects/spring-shell/releases/tag/v4.0.4) — global command prefix và các sửa lỗi liên quan đến help.
