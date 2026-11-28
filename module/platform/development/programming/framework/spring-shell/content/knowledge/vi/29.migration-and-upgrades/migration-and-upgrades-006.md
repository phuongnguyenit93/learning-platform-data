# Thay nhóm lệnh ở cấp lớp bằng cơ chế tương ứng trong 4.x

Trong Spring Shell 3.x, annotation @Command có thể đặt ở cấp lớp để cung cấp tiền tố và thông tin nhóm dùng chung cho các method command bên trong. Từ Spring Shell 4, @Command chỉ còn dùng trên method. Cơ chế dành cho nhóm lệnh ở cấp lớp được tách thành annotation @CommandGroup.

Khi nâng cấp, cần chuyển đúng hai ý nghĩa khác nhau: tiền tố dùng để tạo đường dẫn command và tên nhóm dùng để gom command trong màn hình trợ giúp. @CommandGroup thể hiện rõ hai khái niệm này qua prefix và name. Bài sử dụng Spring Shell 4.0.4; @CommandGroup được giới thiệu từ 4.0.2.

## 1. Hiểu cách nhóm lệnh ở Spring Shell 3.x

Trong annotation model mới của Spring Shell 3.x, @Command có thể đặt ở cấp lớp hoặc method. Khi đặt ở lớp, các method command kế thừa một số metadata chung. Ví dụ:

~~~java
import org.springframework.shell.command.annotation.Command;

@Command(
        command = "github auth",
        group = "GitHub Authentication Commands")
class GitHubCommands {

    @Command(command = "login", description = "Đăng nhập GitHub")
    public String login() {
        return "Đã đăng nhập GitHub.";
    }

    @Command(command = "logout", description = "Đăng xuất GitHub")
    public String logout() {
        return "Đã đăng xuất GitHub.";
    }
}
~~~

Tiền tố github auth ở cấp lớp được ghép với tên command ở method. Người dùng gọi:

~~~text
github auth login
github auth logout
~~~

group là nhãn nhóm hiển thị khi liệt kê command hoặc xem trợ giúp. Nó không tạo thêm thành phần trong đường dẫn command. Tiền tố command mới quyết định phần đầu của tên lệnh.

## 2. Cách tương ứng trong Spring Shell 4.x

Trong Spring Shell 4, @Command chỉ được đặt trên method. Dùng @CommandGroup ở cấp lớp để khai báo tiền tố và nhóm dùng chung:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;

@CommandGroup(
        prefix = "github auth",
        name = "GitHub Authentication Commands")
class GitHubCommands {

    @Command(name = "login", description = "Đăng nhập GitHub")
    public String login() {
        return "Đã đăng nhập GitHub.";
    }

    @Command(name = "logout", description = "Đăng xuất GitHub")
    public String logout() {
        return "Đã đăng xuất GitHub.";
    }
}
~~~

Người dùng vẫn gọi cùng các lệnh:

~~~text
github auth login
github auth logout
~~~

@CommandGroup có ba thuộc tính:

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| prefix | Tiền tố được ghép vào tên các command trong lớp | github auth |
| name | Tên nhóm hiển thị trong help | GitHub Authentication Commands |
| description | Mô tả nhóm command | Quản lý đăng nhập và phiên GitHub |

@CommandGroup được đánh dấu là Spring component, vì vậy lớp vẫn cần nằm trong phạm vi component scan của ứng dụng. Annotation này vừa mô tả nhóm command vừa giúp Spring nhận diện class là bean.

## 3. Phân biệt prefix, group name và command name

Ba giá trị này có nhiệm vụ khác nhau. Đừng sao chép một chuỗi vào cả ba thuộc tính.

~~~java
@CommandGroup(
        prefix = "github auth",
        name = "GitHub Authentication Commands",
        description = "Quản lý xác thực GitHub")
class GitHubCommands {

    @Command(name = "login", description = "Đăng nhập GitHub")
    public String login() {
        return "Đã đăng nhập.";
    }
}
~~~

Trong ví dụ:

- prefix là github auth.
- name là GitHub Authentication Commands.
- @Command.name là login.
- Tên command đầy đủ là github auth login.

Nếu bỏ prefix, command sẽ chỉ có tên login; name của nhóm không tự trở thành tiền tố command. Ngược lại, nếu đặt prefix là github auth nhưng method name đã là github auth login, đường dẫn có thể bị lặp phần đầu. Hãy để prefix và method name chịu trách nhiệm cho những phần khác nhau của command path.

## 4. Bảng chuyển đổi từ 3.x sang 4.x

| Spring Shell 3.x | Spring Shell 4.x | Ghi chú |
|---|---|---|
| @Command(command = "github auth") trên class | @CommandGroup(prefix = "github auth") | Chuyển tiền tố command |
| @Command(group = "GitHub Authentication Commands") trên class | @CommandGroup(name = "GitHub Authentication Commands") | Chuyển nhãn nhóm |
| @Command(command = "login") trên method | @Command(name = "login") trên method | command đổi tên thành name |
| @Command(group = "Special Commands") trên method | @Command(group = "Special Commands") trên method | Có thể ghi đè nhóm của lớp |
| @Command(description = "...") trên method | @Command(description = "...") trên method | Mô tả command giữ ở method |

Ví dụ chuyển đổi ngắn:

~~~java
// Spring Shell 3.x
@Command(command = "customer admin", group = "Customer Administration")
class CustomerAdminCommands {
    @Command(command = "disable")
    public void disable() { }
}

// Spring Shell 4.x
@CommandGroup(prefix = "customer admin", name = "Customer Administration")
class CustomerAdminCommands {
    @Command(name = "disable")
    public void disable() { }
}
~~~

## 5. @CommandGroup được thêm từ Spring Shell 4.0.2

@CommandGroup không có trong 4.0.0 và 4.0.1. Javadoc đánh dấu annotation này Since: 4.0.2. Vì vậy, nếu ứng dụng đang ở 4.0.0 hoặc 4.0.1, hãy nâng ít nhất lên 4.0.2 trước khi dùng annotation này. Bài học sử dụng 4.0.4.

Không nhầm @CommandGroup với thuộc tính group trên @Command. Thuộc tính method-level group vẫn tồn tại trong 4.x và dùng để chỉ định nhóm riêng cho một command. @CommandGroup giúp khai báo tên nhóm mặc định và prefix chung cho các method trong một class.

## 6. Ghi đè group cho một command cụ thể

Thông thường, các command trong cùng lớp thuộc cùng một nhóm. Nếu một method có group riêng, giá trị method-level được ưu tiên cho command đó.

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;

@CommandGroup(prefix = "github", name = "GitHub Commands")
class GitHubCommands {

    @Command(name = "login", description = "Đăng nhập GitHub")
    public String login() {
        return "Đã đăng nhập.";
    }

    @Command(
            name = "token rotate",
            group = "Credential Management",
            description = "Thay token truy cập")
    public String rotateToken() {
        return "Đã yêu cầu thay token.";
    }
}
~~~

Trong ví dụ, cả hai command vẫn có prefix github. Command login thuộc nhóm mặc định GitHub Commands; command token rotate thuộc nhóm Credential Management. Thuộc tính group thay đổi nhãn nhóm, không thay đổi prefix.

## 7. Khi chỉ cần nhóm hiển thị, không cần prefix

Không phải ứng dụng 3.x nào cũng dùng class-level @Command để tạo tiền tố. Một số ứng dụng chỉ cần gom command vào cùng nhóm help. Khi đó, chỉ chuyển tên nhóm:

~~~java
@CommandGroup(name = "Customer Administration")
class CustomerCommands {

    @Command(name = "customer list")
    public String list() {
        return "Danh sách khách hàng.";
    }

    @Command(name = "customer disable")
    public String disable() {
        return "Đã vô hiệu hóa khách hàng.";
    }
}
~~~

Các tên command vẫn là customer list và customer disable. @CommandGroup.name chỉ quyết định nhóm hiển thị. Không thêm prefix = customer trong trường hợp này vì command name đã chứa phần đó; nếu thêm prefix, tên lệnh sẽ bị lặp thành customer customer list.

## 8. Nếu ứng dụng đang dùng legacy @ShellCommandGroup

Spring Shell 3.x có hai annotation model. Annotation model mới dùng @Command ở cấp lớp/method. Legacy model dùng @ShellComponent, @ShellMethod và có thể dùng @ShellCommandGroup ở cấp lớp hoặc package.

Ví dụ legacy:

~~~java
import org.springframework.shell.standard.ShellCommandGroup;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
@ShellCommandGroup("Customer Administration")
class CustomerCommands {

    @ShellMethod(key = "customer list", value = "Liệt kê khách hàng")
    public String list() {
        return "Danh sách khách hàng.";
    }
}
~~~

Trong Spring Shell 4, legacy annotations như @ShellComponent, @ShellMethod, @ShellOption và @ShellCommandGroup đã bị loại bỏ. Với ví dụ trên, chuyển sang:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;

@CommandGroup(name = "Customer Administration")
class CustomerCommands {

    @Command(name = "customer list", description = "Liệt kê khách hàng")
    public String list() {
        return "Danh sách khách hàng.";
    }
}
~~~

Ở đây chỉ đặt name, không đặt prefix, vì tên command đã là customer list. @ShellCommandGroup legacy chỉ xác định nhãn nhóm; không tự tạo command prefix. Nếu ứng dụng muốn có prefix chung, hãy thêm prefix một cách có chủ đích và điều chỉnh method command name tương ứng.

## 9. Di chuyển nhóm được khai báo ở cấp package

Legacy @ShellCommandGroup có thể đặt trong package-info.java để áp dụng nhãn nhóm cho các command của package. @CommandGroup trong 4.x có @Target(TYPE), nghĩa là chỉ đặt trên class.

Nếu trước đây package có:

~~~java
@ShellCommandGroup("Customer Administration")
package com.example.customer.commands;

import org.springframework.shell.standard.ShellCommandGroup;
~~~

Không thể chuyển nguyên annotation này sang package-info.java trong 4.x. Có hai hướng:

1. Tạo một hoặc nhiều class command theo nhóm chức năng và đặt @CommandGroup(name = "Customer Administration") trên từng class.
2. Nếu nhóm nhỏ và không cần class grouping, đặt group = "Customer Administration" trên từng method @Command.

Chọn cách tổ chức sao cho nhóm help phản ánh cấu trúc command dễ hiểu. Không tạo một class khổng lồ chỉ để gom mọi command của package nếu các command không có quan hệ chức năng.

## 10. Những metadata cấp lớp không tự động chuyển sang @CommandGroup

@CommandGroup chỉ có ba thuộc tính prefix, name và description. Nó không phải bản sao toàn bộ @Command cấp lớp trong 3.x.

Nếu class-level @Command cũ còn khai báo metadata khác, cần chuyển chúng tới method tương ứng:

| Metadata ở class-level 3.x | Cách xử lý trong 4.x |
|---|---|
| command | @CommandGroup(prefix = ...) |
| group | @CommandGroup(name = ...) |
| description | @CommandGroup(description = ...) nếu là mô tả nhóm; nếu là mô tả từng command thì đặt @Command(description = ...) ở method |
| alias | Chuyển alias cần thiết tới @Command(alias = ...) ở từng method; @CommandGroup không có alias prefix |
| hidden | Chuyển sang @Command(hidden = ...) cho từng command cần ẩn |
| interactionMode | Xem lại thiết kế vì InteractionMode đã bị loại bỏ trong 4.x; mode được chọn ở cấp shell |

Hãy kiểm tra từng thuộc tính class-level cũ thay vì chỉ thay annotation rồi xóa phần còn lại. Đặc biệt, class-level alias không có thuộc tính tương đương trên @CommandGroup; cần khai báo alias cụ thể cho từng command hoặc thiết kế alias command tường minh.

## 11. Đăng ký command sau khi chuyển sang 4.x

@CommandGroup được meta-annotated với @Component, nhưng class vẫn cần nằm trong phạm vi scan của Spring. Các method @Command phải thuộc một Spring-managed bean.

Với Spring Boot 4 và Spring Shell 4, command scanning được auto-configuration bật tự động. Không cần thêm @CommandScan như mô hình 3.x. Nếu không dùng Spring Boot, dùng @EnableCommand để bật command discovery.

Ví dụ ứng dụng Spring Boot:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
class SpringShellApplication {

    public static void main(String[] args) {
        SpringApplication.run(SpringShellApplication.class, args);
    }
}
~~~

Đặt class GitHubCommands trong package được @SpringBootApplication scan. Nếu component scan bị giới hạn hoặc loại package command bằng excludeFilters, command sẽ không được đăng ký dù annotation đúng.

## 12. Nếu dùng programmatic command registration

@CommandGroup áp dụng cho annotation-based command class. Nếu ứng dụng định nghĩa command bằng Command.Builder, hãy khai báo tên command đầy đủ và group ngay trên builder:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.ExitStatus;

@Bean
Command githubLoginCommand() {
    return Command.builder()
            .name("github auth login")
            .group("GitHub Authentication Commands")
            .execute(context -> {
                context.outputWriter().println("Đã đăng nhập GitHub.");
                return ExitStatus.OK;
            });
}
~~~

Trong mô hình này, name(...) là đường dẫn command đầy đủ; group(...) là nhãn hiển thị. Không có class-level @CommandGroup để tự thêm prefix cho command được tạo theo cách programmatic.

## 13. Các lỗi thường gặp khi migration

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| @Command không biên dịch trên class | 4.x chỉ cho phép annotation trên method | Thay annotation class bằng @CommandGroup |
| Không tìm thấy @CommandGroup | Đang dùng 4.0.0/4.0.1 hoặc dependency không đúng | Nâng lên 4.0.2 trở lên và kiểm tra module core |
| Command có prefix lặp hai lần | Prefix đã nằm trong method name nhưng vẫn thêm @CommandGroup.prefix | Chọn một nơi chịu trách nhiệm cho prefix |
| Tên nhóm help bị đổi thành tên command | Đã chuyển nhầm group sang prefix | Chuyển nhãn sang name, prefix chỉ dùng cho đường dẫn |
| Command không xuất hiện | Class không được Spring scan hoặc chưa bật command discovery trong non-Boot app | Kiểm tra component scan hoặc @EnableCommand |
| Một command bị xếp sai nhóm | Method có @Command(group = ...) ghi đè group cấp lớp | Kiểm tra group ở method |
| Alias cũ biến mất | @CommandGroup không có alias | Chuyển alias xuống từng method |
| Package-level group không còn tác dụng | @CommandGroup chỉ target class | Chuyển metadata lên class hoặc method |

## 14. Quy trình migration an toàn

Thực hiện theo thứ tự để giảm khả năng thay đổi command contract ngoài ý muốn:

1. Ghi lại tên command đầy đủ hiện tại, nhãn nhóm help và alias.
2. Xác định class đang dùng annotation model mới @Command hay legacy @ShellCommandGroup/@ShellMethod.
3. Tách prefix khỏi nhãn nhóm; không suy ra prefix từ group name.
4. Thay class-level @Command bằng @CommandGroup(prefix, name, description).
5. Đổi method-level @Command(command = ...) thành @Command(name = ...).
6. Chuyển các metadata còn lại như alias, hidden và mô tả về method.
7. Với legacy package-level group, chia nhóm vào các class hoặc đặt group trên method.
8. Kiểm tra Spring component scan và command registration.
9. Chạy help và help cho từng command để kiểm tra tên, nhóm và mô tả.
10. Chạy smoke test các command cũ bằng chính cú pháp CLI trước khi phát hành.

## 15. Kiểm thử sau khi chuyển nhóm lệnh

Một test tốt cần xác nhận cả command path và metadata nhóm. Ví dụ với Spring Shell 4:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;
import org.springframework.test.context.ContextConfiguration;

@ShellTest
@ContextConfiguration(classes = SpringShellApplication.class)
class GitHubCommandsTests {

    @Autowired
    ShellTestClient client;

    @Test
    void executesCommandWithGroupPrefix() throws Exception {
        var screen = client.sendCommand("github auth login");

        ShellAssertions.assertThat(screen)
                .containsText("Đã đăng nhập GitHub.");
    }
}
~~~

Ngoài test execution, hãy kiểm tra help output để bảo đảm hai command được liệt kê dưới nhóm GitHub Authentication Commands. Nếu cần xác nhận group metadata ở mức unit, có thể kiểm tra command registry sau khi context khởi tạo; tuy nhiên, test help output phản ánh gần hơn trải nghiệm người dùng.

## 16. Bài tập thực hành

Một ứng dụng Spring Shell 3.x có class ProjectCommands:

~~~java
@Command(command = "project admin", group = "Project Administration")
class ProjectCommands {

    @Command(command = "create")
    public String create() { return "created"; }

    @Command(command = "archive")
    public String archive() { return "archived"; }
}
~~~

Hãy chuyển sang Spring Shell 4.0.4 và thực hiện:

1. Dùng @CommandGroup để giữ prefix project admin và group name Project Administration.
2. Chuyển method command sang @Command(name = ...).
3. Thêm mô tả riêng cho từng command.
4. Thêm một command project audit thuộc nhóm Audit Commands nhưng vẫn giữ prefix phù hợp.
5. Kiểm tra help và project admin create/project admin archive.
6. Viết shell test xác nhận command path cũ vẫn chạy.
7. Thử bỏ prefix và giải thích sự khác nhau giữa tên nhóm help và tên command.
8. Nếu class cũ có alias, hãy khai báo alias mới ở từng method và kiểm tra lại.

Kết quả cần nộp: source trước/sau, bảng ánh xạ prefix/group/name, test command execution và output help sau migration.

## 17. Checklist trước khi hoàn tất migration

- [ ] Đã xác định phiên bản Spring Shell cũ và phiên bản 4.x đích.
- [ ] Nếu dùng @CommandGroup, phiên bản đích từ 4.0.2 trở lên.
- [ ] Không còn đặt @Command trên class trong source 4.x.
- [ ] Mỗi command method dùng @Command(name = ...).
- [ ] Prefix cũ được chuyển sang @CommandGroup.prefix.
- [ ] Nhãn nhóm cũ được chuyển sang @CommandGroup.name.
- [ ] Group method-level được giữ hoặc ghi đè có chủ đích.
- [ ] Không nhân đôi prefix trong method command name.
- [ ] Alias, hidden, description và metadata khác đã được rà soát riêng.
- [ ] Legacy @ShellCommandGroup đã được thay bằng @CommandGroup hoặc @Command(group = ...).
- [ ] Package-level grouping đã được chuyển lên class/method.
- [ ] Command class nằm trong component scan.
- [ ] Spring Boot 4 auto-scanning hoặc @EnableCommand cho non-Boot app được cấu hình đúng.
- [ ] Help output, command path và test execution đều giữ đúng contract mong đợi.

## Tài liệu tham khảo

- [Spring Shell — v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Spring Shell 4.0.4 API — CommandGroup](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/CommandGroup.html)
- [Spring Shell 4.0.4 API — Command](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)
- [Spring Shell 4.0.4 — Organizing Commands](https://docs.spring.io/spring-shell/reference/commands/organize.html)
- [Spring Shell 3.3 — Annotation Command Registration](https://docs.spring.io/spring-shell/reference/3.3/commands/registration/annotation.html)
- [Spring Shell 3.3 — Legacy Annotation Model](https://docs.spring.io/spring-shell/reference/3.3/commands/registration/legacyannotation.html)
- [Spring Shell 3.3 API — ShellCommandGroup](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/ShellCommandGroup.html)
- [Spring Shell 4.0.4 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html)